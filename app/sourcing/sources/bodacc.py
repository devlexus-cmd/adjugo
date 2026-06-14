"""
Source red-flag : BODACC (annonces commerciales officielles, DILA).
https://bodacc-datadila.opendatasoft.com — open data, sans clé.

Sert UNIQUEMENT à détecter une procédure collective en cours (sauvegarde,
redressement, liquidation judiciaire) pour un SIREN donné. C'est le signal de
fiabilité le plus déterminant sur un co-traitant : on ne l'invente jamais, on le
lit dans l'avis publié, avec sa date et le lien vers l'annonce.
"""
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("adjugo")
BODACC = ("https://bodacc-datadila.opendatasoft.com/api/explore/v2.1"
          "/catalog/datasets/annonces-commerciales/records")


class BodaccSource:
    name = "BODACC"

    def check(self, siren: Optional[str]) -> Optional[dict]:
        """Renvoie l'avis de procédure collective le plus récent pour ce SIREN,
        ou None si aucun / source indisponible (jamais inventé).

        Retour : {nature, famille, date, url, ongoing} où `ongoing` est False quand
        le dernier avis est une clôture (procédure terminée → pas de cap)."""
        siren = (siren or "").strip()
        if not siren or len(siren) != 9 or not siren.isdigit():
            return None
        params = {
            "where": f'familleavis="collective" and registre like "{siren}"',
            "order_by": "dateparution desc",
            "limit": 1,
        }
        try:
            with httpx.Client(timeout=8, headers={"User-Agent": "AdjugoBot/1.0"}) as c:
                r = c.get(BODACC, params=params)
                r.raise_for_status()
                results = r.json().get("results", [])
        except Exception as e:
            logger.info("BODACC indisponible pour %s : %s", siren, e)
            return None
        if not results:
            return None

        rec = results[0]
        jug = rec.get("jugement")
        if isinstance(jug, str):
            try:
                jug = json.loads(jug)
            except Exception:
                jug = {}
        jug = jug or {}
        famille = (jug.get("famille") or rec.get("typeavis_lib") or "").strip()
        nature = (jug.get("nature") or famille or "Procédure collective").strip()
        closed = "clôture" in famille.lower() or "clôture" in nature.lower()
        return {
            "nature": nature,
            "famille": famille,
            "date": jug.get("date") or rec.get("dateparution"),
            "url": rec.get("url_complete") or "https://www.bodacc.fr",
            "ongoing": not closed,
        }
