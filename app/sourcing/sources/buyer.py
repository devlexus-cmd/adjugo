"""
Intelligence marché — profil acheteur.

À partir d'un nom d'acheteur, agrège son historique de publication réel sur BOAMP
(source officielle, déjà intégrée, provenance tracée) : volume total, volume 12 mois,
secteurs (descripteurs) récurrents, zones, derniers avis. Sert à juger si un acheteur
est récurrent (= meilleur lead). Aucune donnée inventée : tout vient de l'API publique.

NB : la liste des concurrents qui REMPORTENT (données DECP des marchés attribués) est une
enrichissement futur — non incluse ici faute d'API consolidée fiable, jamais simulée.
"""
import logging
from datetime import date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("adjugo")
API = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"
_H = {"User-Agent": "AdjugoBot/1.0"}


class BuyerProfileSource:
    name = "BOAMP"

    def _get(self, params: dict) -> dict:
        with httpx.Client(timeout=10, headers=_H) as c:
            r = c.get(API, params=params)
            r.raise_for_status()
            return r.json()

    def _count(self, where: str) -> int:
        try:
            return int(self._get({"where": where, "limit": 1}).get("total_count", 0))
        except Exception:
            return 0

    def _group(self, where: str, field: str, n: int = 6) -> list[dict]:
        try:
            js = self._get({"where": where, "group_by": field,
                            "select": f"{field}, count(*) as n", "order_by": "-n", "limit": n})
            out = []
            for row in js.get("results", []):
                label = row.get(field)
                if isinstance(label, list):
                    label = ", ".join(str(x) for x in label if x)
                if label:
                    out.append({"label": str(label), "n": row.get("n", 0)})
            return out
        except Exception:
            return []

    def profile(self, acheteur: Optional[str]) -> Optional[dict]:
        """Profil de publication d'un acheteur, ou None si introuvable / source KO."""
        name = (acheteur or "").replace('"', " ").strip()
        if len(name) < 3:
            return None
        where = f'nomacheteur like "{name}"'
        total = self._count(where)
        if total == 0:
            return None

        since = (date.today() - timedelta(days=365)).isoformat()
        recent_12m = self._count(f'{where} AND dateparution >= "{since}"')

        secteurs = self._group(where, "descripteur_libelle")
        zones = self._group(where, "code_departement")

        recents = []
        try:
            js = self._get({"where": where, "order_by": "-dateparution", "limit": 5,
                            "select": "objet,dateparution,datelimitereponse,url_avis,idweb"})
            for r in js.get("results", []):
                idweb = str(r.get("idweb") or "")
                recents.append({
                    "objet": (r.get("objet") or "").strip()[:140],
                    "date": (r.get("dateparution") or "")[:10] or None,
                    "echeance": (r.get("datelimitereponse") or "")[:10] or None,
                    "url": r.get("url_avis") or f"https://www.boamp.fr/avis/detail/{idweb}",
                })
        except Exception:
            pass

        search_url = ('https://www.boamp.fr/pages/recherche/?disjunctive.nomacheteur'
                      f'&refine.nomacheteur={httpx.QueryParams({"v": name})["v"]}')
        return {
            "acheteur": name,
            "total_publies": total,
            "publies_12m": recent_12m,
            "recurrent": recent_12m >= 3,
            "top_secteurs": secteurs,
            "zones": zones,
            "recents": recents,
            "source": self.name,
            "source_url": "https://www.boamp.fr",
            "search_url": search_url,
            "fetched_at": date.today().isoformat(),
        }
