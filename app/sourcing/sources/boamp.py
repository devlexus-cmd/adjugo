"""
Source AO : BOAMP (Bulletin Officiel des Annonces de Marchés Publics).
API open data v2.1 — https://www.boamp.fr/api/explore/v2.1
Aucune clé requise. Données réelles, traçables par idweb + url_avis.
"""
import re
import logging
from datetime import date
from typing import Optional

import httpx

from app.sourcing.base import TenderSource, TenderCriteria
from app.sourcing.schemas import NormalizedTender, Provenance

logger = logging.getLogger("adjugo")
API = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"
SELECT = ("idweb,objet,nomacheteur,code_departement,dateparution,datelimitereponse,"
          "descripteur_libelle,descripteur_code,nature_libelle,famille_libelle,"
          "url_avis,type_marche,procedure_libelle")


class BoampSource(TenderSource):
    name = "BOAMP"
    supported_filters = {"query", "departements"}

    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        from app.sourcing.http import safe_terms
        q = safe_terms(criteria.query) or "travaux"   # neutralise l'injection ODSQL
        where = f'objet like "{q}" OR descripteur_libelle like "{q}"'
        if criteria.departements:
            deps = " OR ".join(f'code_departement like "{d}"' for d in criteria.departements)
            where = f"({where}) AND ({deps})"
        if getattr(criteria, "type_marche", "") in ("TRAVAUX", "SERVICES", "FOURNITURES"):
            where = f'({where}) AND type_marche like "{criteria.type_marche}"'
        # On ne remonte que les AO ENCORE OUVERTS (date limite de réponse non passée).
        # Exclut de fait les avis d'attribution / clôturés → crédibilité du sourcing.
        where = f"({where}) AND datelimitereponse >= date'{date.today().isoformat()}'"
        params = {"limit": min(criteria.limit, 50), "order_by": "-dateparution",
                  "where": where, "select": SELECT}
        try:
            from app.sourcing.http import get_with_retry
            r = get_with_retry(API, params=params, timeout=12)   # retry + backoff
            rows = r.json().get("results", [])
        except Exception as e:
            logger.warning("BOAMP indisponible : %s", e)
            raise
        return [self._normalize(row) for row in rows]

    def _normalize(self, r: dict) -> NormalizedTender:
        idweb = str(r.get("idweb", "") or "")
        deps = r.get("code_departement") or []
        if not isinstance(deps, list):
            deps = [str(deps)]
        desc = r.get("descripteur_libelle") or []
        codes = r.get("descripteur_code") or []
        url_avis = r.get("url_avis", "") or f"https://www.boamp.fr/avis/detail/{idweb}"

        t = NormalizedTender(
            objet=(r.get("objet") or "").strip()[:400] or "Objet non précisé",
            acheteur=_as_str(r.get("nomacheteur")),
            cpv=[str(c) for c in (codes if isinstance(codes, list) else [codes]) if c],
            date_publication=(r.get("dateparution") or "")[:10] or None,
            date_limite=(r.get("datelimitereponse") or "")[:10] or None,
            lieu=", ".join(desc) if isinstance(desc, list) and desc else None,
            departements=[str(d) for d in deps if d],
            procedure=_as_str(r.get("procedure_libelle")),
            nature=_as_str(r.get("type_marche")) or _as_str(r.get("nature_libelle")),
            dce_url=None,  # rempli à l'analyse profonde si accessible
            provenance=Provenance(source=self.name, source_url=url_avis, official_ref=idweb),
            raw=r,
        )
        t.confidence = self._confidence(t)
        t.dedup_key = _dedup_key(t)
        return t

    @staticmethod
    def _confidence(t: NormalizedTender) -> float:
        """Confiance = complétude des champs clés (jamais un nombre arbitraire)."""
        keys = [t.objet and t.objet != "Objet non précisé", t.acheteur,
                t.date_limite, bool(t.departements), bool(t.cpv), t.procedure]
        present = sum(1 for k in keys if k)
        return round(present / len(keys), 2)

    def fetch_dce(self, tender: NormalizedTender) -> Optional[str]:
        """Tente de récupérer le texte réel du DCE. Retourne None si inaccessible
        (jamais de DCE inventé en repli)."""
        url = tender.provenance.source_url
        if not url:
            return None
        try:
            with httpx.Client(follow_redirects=True, timeout=20,
                              headers={"User-Agent": "AdjugoBot/1.0 (+https://adjugo.fr)"}) as c:
                resp = c.get(url)
                if resp.status_code != 200:
                    return None
                pdf_links = re.findall(r'href="([^"]+\.pdf[^"]*)"', resp.text, re.I)
                for link in pdf_links[:5]:
                    if link.startswith("/"):
                        link = "https://www.boamp.fr" + link
                    try:
                        p = c.get(link, timeout=20)
                        if p.status_code == 200 and "pdf" in p.headers.get("content-type", "").lower():
                            from app.services.analysis import extract_text_from_pdf
                            txt = extract_text_from_pdf(p.content)
                            if txt and len(txt) > 300 and not txt.startswith("Erreur"):
                                return txt
                    except Exception:
                        continue
                # Pas de PDF DCE exploitable → None (l'avis sera analysé à part,
                # honnêtement labellisé « DCE non accessible »). Jamais de DCE inventé.
                return None
        except Exception as e:
            logger.info("DCE BOAMP non récupéré (%s) : %s", url, e)
            return None


def _as_str(v) -> Optional[str]:
    """Coerce un champ BOAMP (parfois liste) en string, ou None."""
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return ", ".join(parts) or None
    return str(v).strip() or None


def _dedup_key(t: NormalizedTender) -> str:
    base = re.sub(r"[^a-z0-9]", "", (t.objet or "").lower())[:40]
    ach = re.sub(r"[^a-z0-9]", "", (t.acheteur or "").lower())[:20]
    return f"{base}|{ach}|{t.date_limite or ''}"
