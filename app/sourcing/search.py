"""
Orchestration multi-sources : interroge toutes les sources en parallèle,
déduplique, fusionne les provenances, score. Les erreurs de source sont
remontées (jamais masquées, jamais remplacées par de l'inventé).
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Optional

from app.sourcing.base import TenderSource, TenderCriteria, CompanySource
from app.sourcing.schemas import NormalizedTender, NormalizedCompany, SourceError
from app.sourcing.scoring import score_tender, score_company

logger = logging.getLogger("adjugo")


class TenderSearchService:
    def __init__(self, sources: list[TenderSource]):
        self.sources = sources

    def search(self, criteria: TenderCriteria, company: Optional[dict] = None,
               gonogo: Optional[dict] = None) -> dict:
        tenders: list[NormalizedTender] = []
        errors: list[SourceError] = []

        with ThreadPoolExecutor(max_workers=max(1, len(self.sources))) as ex:
            futs = {ex.submit(s.search, criteria): s for s in self.sources}
            for fut in as_completed(futs):
                src = futs[fut]
                try:
                    tenders.extend(fut.result())
                except Exception as e:
                    errors.append(SourceError(source=src.name, message=str(e)[:200]))

        deduped = _dedup_tenders(tenders)
        # On n'affiche JAMAIS un AO dont la date limite de réponse est passée
        # (crédibilité). Les AO sans date connue sont conservés (récents/non parsés).
        before = len(deduped)
        deduped = [t for t in deduped if not _is_closed(t.date_limite)]
        closed = before - len(deduped)

        for t in deduped:
            t.score = score_tender(t, company, gonogo)
        deduped.sort(key=lambda t: (t.score.total if t.score else 0), reverse=True)

        return {
            "tenders": deduped,
            "errors": errors,
            "sources_queried": [s.name for s in self.sources],
            "count": len(deduped),
            "closed_filtered": closed,
        }


def _is_closed(date_limite) -> bool:
    """True si la date limite de réponse est passée (AO clôturé)."""
    if not date_limite:
        return False
    try:
        d = datetime.strptime(str(date_limite)[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    return d < date.today()


def _dedup_tenders(tenders: list[NormalizedTender]) -> list[NormalizedTender]:
    """Fusionne les AO identiques (même réf officielle OU même clé floue).
    Le doublon enrichit `also_seen_in` et augmente la confiance (concordance)."""
    by_ref: dict[str, NormalizedTender] = {}
    by_key: dict[str, NormalizedTender] = {}
    out: list[NormalizedTender] = []

    for t in tenders:
        ref = t.provenance.official_ref
        existing = (by_ref.get(ref) if ref else None) or by_key.get(t.dedup_key)
        if existing:
            existing.also_seen_in.append(t.provenance)
            existing.confidence = min(1.0, round(existing.confidence + 0.1, 2))  # concordance
            # compléter les champs manquants à partir du doublon (jamais écraser)
            for f in ("acheteur", "montant_estime", "date_limite", "dce_url", "procedure"):
                if getattr(existing, f) in (None, "", []) and getattr(t, f) not in (None, "", []):
                    setattr(existing, f, getattr(t, f))
        else:
            out.append(t)
            if ref:
                by_ref[ref] = t
            by_key[t.dedup_key] = t
    return out


class CompanySearchService:
    def __init__(self, sources: list[CompanySource], red_flag_source=None):
        self.sources = sources
        # Source de red-flag financier (BODACC) : enrichissement, jamais bloquant.
        self.red_flag_source = red_flag_source

    def discover(self, activity: str = "", departement: str = "", query: str = "",
                 limit: int = 12, tender_departements: Optional[list] = None,
                 need_label: str = "") -> dict:
        companies: list[NormalizedCompany] = []
        errors: list[SourceError] = []
        for s in self.sources:
            try:
                companies.extend(s.search(activity=activity, departement=departement,
                                          query=query, limit=limit))
            except Exception as e:
                errors.append(SourceError(source=s.name, message=str(e)[:200]))

        # Dédup par SIREN
        seen, deduped = set(), []
        for c in companies:
            if c.siren and c.siren in seen:
                continue
            if c.siren:
                seen.add(c.siren)
            deduped.append(c)

        # Enrichissement red-flag BODACC (procédure collective) en parallèle —
        # AVANT le scoring pour que le plafond s'applique. Échec = dégradation
        # silencieuse (le co-traitant n'est juste pas flaggé), jamais inventé.
        self._enrich_red_flags(deduped)

        for c in deduped:
            c.score = score_company(c, need_label or activity, tender_departements)
        deduped.sort(key=lambda c: (c.score.total if c.score else 0), reverse=True)
        return {"companies": deduped, "errors": errors, "count": len(deduped)}

    def _enrich_red_flags(self, companies: list[NormalizedCompany]) -> None:
        rf = self.red_flag_source
        if not rf:
            return
        targets = [c for c in companies if c.siren]
        if not targets:
            return
        try:
            with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
                futs = {ex.submit(rf.check, c.siren): c for c in targets}
                for fut in as_completed(futs, timeout=12):
                    c = futs[fut]
                    try:
                        info = fut.result()
                    except Exception:
                        continue
                    if not info:
                        continue
                    label = info["nature"]
                    if info.get("date"):
                        label += f" ({info['date']})"
                    if info.get("ongoing"):
                        # procédure en cours → red-flag déterminant (plafonne le score)
                        c.procedure_collective = label
                    else:
                        # procédure clôturée → information, sans plafond
                        c.red_flags = list(c.red_flags) + [f"Procédure collective clôturée : {label}"]
        except Exception as e:
            logger.info("Enrichissement BODACC partiel/indisponible : %s", e)

    def verify_siret(self, siret: str) -> Optional[NormalizedCompany]:
        for s in self.sources:
            c = s.get_by_siret(siret)
            if c:
                return c
        return None
