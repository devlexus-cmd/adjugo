"""
Orchestration multi-sources : interroge toutes les sources en parallèle,
déduplique, fusionne les provenances, score. Les erreurs de source sont
remontées (jamais masquées, jamais remplacées par de l'inventé).
"""
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import date, datetime
from typing import Optional

from app.sourcing.base import TenderSource, TenderCriteria, CompanySource
from app.sourcing.schemas import NormalizedTender, NormalizedCompany, SourceError
from app.sourcing.scoring import score_tender, score_company

logger = logging.getLogger("adjugo")

# Délai DUR d'une recherche : au-delà, on rend ce qui a répondu et on marque les sources
# lentes en « délai dépassé » — une source lente/HS ne paralyse jamais la recherche.
_SEARCH_DEADLINE = float(os.getenv("SOURCING_DEADLINE", "14"))

# Disjoncteur par source : après N échecs/timeouts consécutifs, on saute la source pendant
# un cooldown (fail-fast) au lieu de réattendre son timeout à chaque recherche.
_CB = {}
_CB_LOCK = threading.Lock()
_CB_THRESHOLD = int(os.getenv("SOURCING_CB_THRESHOLD", "3"))
_CB_COOLDOWN = float(os.getenv("SOURCING_CB_COOLDOWN", "120"))


def _cb_open(name: str) -> bool:
    with _CB_LOCK:
        cb = _CB.get(name)
        return bool(cb and cb["open_until"] > time.monotonic())


def _cb_fail(name: str) -> None:
    with _CB_LOCK:
        cb = _CB.setdefault(name, {"fails": 0, "open_until": 0.0})
        cb["fails"] += 1
        if cb["fails"] >= _CB_THRESHOLD:
            cb["open_until"] = time.monotonic() + _CB_COOLDOWN
            logger.warning("Disjoncteur sourcing ouvert pour « %s » (%s échecs) — pause %ss.",
                           name, cb["fails"], _CB_COOLDOWN)


def _cb_ok(name: str) -> None:
    with _CB_LOCK:
        _CB[name] = {"fails": 0, "open_until": 0.0}

logger = logging.getLogger("adjugo")


class TenderSearchService:
    def __init__(self, sources: list[TenderSource]):
        self.sources = sources

    def search(self, criteria: TenderCriteria, company: Optional[dict] = None,
               gonogo: Optional[dict] = None) -> dict:
        tenders: list[NormalizedTender] = []
        errors: list[SourceError] = []

        # Disjoncteur : on saute les sources en panne (fail-fast, pas de réattente).
        active = [s for s in self.sources if not _cb_open(s.name)]
        for s in self.sources:
            if _cb_open(s.name):
                errors.append(SourceError(source=s.name, message="temporairement indisponible (trop d'échecs récents)"))

        ex = ThreadPoolExecutor(max_workers=max(1, len(active) or 1))
        futs = {ex.submit(s.search, criteria): s for s in active}
        try:
            for fut in as_completed(futs, timeout=_SEARCH_DEADLINE):
                src = futs[fut]
                try:
                    tenders.extend(fut.result())
                    _cb_ok(src.name)
                except Exception as e:
                    errors.append(SourceError(source=src.name, message=str(e)[:200]))
                    _cb_fail(src.name)
        except FuturesTimeout:
            pass
        # Sources non terminées au délai → délai dépassé (et on ne BLOQUE pas dessus).
        for fut, src in futs.items():
            if not fut.done():
                errors.append(SourceError(source=src.name, message="délai dépassé"))
                _cb_fail(src.name)
                fut.cancel()
        ex.shutdown(wait=False)

        # « has_more » se calcule sur le BRUT récupéré (avant dédup/filtres) : si au moins
        # une source a rempli une page, il reste probablement des résultats — sinon le
        # filtrage serveur (date passée, montant) faisait croire à tort qu'on était au bout.
        raw_more = len(tenders) >= max(1, getattr(criteria, "limit", 20))

        deduped = _dedup_tenders(tenders)
        # On n'affiche JAMAIS un AO dont la date limite de réponse est passée
        # (crédibilité). Les AO sans date connue sont conservés (récents/non parsés).
        before = len(deduped)
        deduped = [t for t in deduped if not _is_closed(t.date_limite)]
        closed = before - len(deduped)

        # Filtre montant DEMANDÉ par l'utilisateur : on n'écarte QUE les avis dont le
        # montant est CONNU et hors fourchette (les avis sans montant — le cas le plus
        # fréquent en open data — sont conservés, sinon on masquerait presque tout).
        mn = getattr(criteria, "montant_min", None)
        mx = getattr(criteria, "montant_max", None)
        amount_filtered = 0
        if mn is not None or mx is not None:
            kept = []
            for t in deduped:
                m = t.montant_estime
                if m is not None and ((mn is not None and m < mn) or (mx is not None and m > mx)):
                    amount_filtered += 1
                    continue
                kept.append(t)
            deduped = kept

        # Filtre TYPE DE MARCHÉ en post-traitement (filet de sécurité) : on n'écarte
        # QUE les avis dont la nature est CONNUE et différente (Travaux/Services/
        # Fournitures côté BOAMP). Les natures non catégorisées (TED = « Marché
        # européen », déjà filtré à la source via contract-nature) sont conservées.
        tm = (getattr(criteria, "type_marche", "") or "").strip().upper()
        if tm in ("TRAVAUX", "SERVICES", "FOURNITURES"):
            _KNOWN = ("TRAVAUX", "SERVICES", "FOURNITURES")
            kept = []
            for t in deduped:
                n = (getattr(t, "nature", "") or "").strip().upper()
                if n not in _KNOWN or n == tm:
                    kept.append(t)
            deduped = kept

        for t in deduped:
            t.score = score_tender(t, company, gonogo)
        deduped.sort(key=lambda t: (t.score.total if t.score else 0), reverse=True)

        return {
            "tenders": deduped,
            "errors": errors,
            "sources_queried": [s.name for s in self.sources],
            "count": len(deduped),
            "closed_filtered": closed,
            "amount_filtered": amount_filtered,
            "has_more": raw_more,
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
        # Enrichissement DECP : marchés publics RÉELLEMENT gagnés (capacité réelle),
        # borné aux meilleurs candidats pour la latence. Échec = dégradation silencieuse.
        self._enrich_decp_wins(deduped[:12])
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

    def _enrich_decp_wins(self, companies: list[NormalizedCompany]) -> None:
        """Enrichit chaque entreprise avec son historique de marchés publics gagnés (DECP).
        En parallèle, avec un budget de temps borné. Échec = pas d'enrichissement (jamais inventé)."""
        targets = [c for c in companies if c.siren]
        if not targets:
            return
        from app.services.decp import wins_by_siren
        try:
            with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
                futs = {ex.submit(wins_by_siren, c.siren): c for c in targets}
                for fut in as_completed(futs, timeout=10):
                    c = futs[fut]
                    try:
                        w = fut.result()
                    except Exception:
                        continue
                    c.past_wins = int(w.get("count") or 0)
                    c.last_win_date = w.get("last_date") or None
                    c.win_domains = list(w.get("domains") or [])
        except Exception as e:
            logger.info("Enrichissement DECP (marchés gagnés) partiel/indisponible : %s", e)

    def verify_siret(self, siret: str) -> Optional[NormalizedCompany]:
        for s in self.sources:
            c = s.get_by_siret(siret)
            if c:
                return c
        return None
