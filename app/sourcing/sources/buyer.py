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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("adjugo")
API = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"
_H = {"User-Agent": "AdjugoBot/1.0"}
_TIMEOUT = 6   # par appel BOAMP — échec rapide plutôt que de geler une requête

# Cache des profils acheteur (l'historique bouge lentement) : évite de refaire 5 appels
# BOAMP à CHAQUE ouverture d'AO — c'était la cause des blocages. Borné + TTL.
_CACHE = {}
_CACHE_TTL = 3600
_CACHE_MAX = 500
_LOCK = threading.Lock()


class BuyerProfileSource:
    name = "BOAMP"

    def _get(self, params: dict) -> dict:
        with httpx.Client(timeout=_TIMEOUT, headers=_H) as c:
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

    def _recents(self, where: str) -> list:
        try:
            js = self._get({"where": where, "order_by": "-dateparution", "limit": 5,
                            "select": "objet,dateparution,datelimitereponse,url_avis,idweb"})
            out = []
            for r in js.get("results", []):
                idweb = str(r.get("idweb") or "")
                out.append({
                    "objet": (r.get("objet") or "").strip()[:140],
                    "date": (r.get("dateparution") or "")[:10] or None,
                    "echeance": (r.get("datelimitereponse") or "")[:10] or None,
                    "url": r.get("url_avis") or f"https://www.boamp.fr/avis/detail/{idweb}",
                })
            return out
        except Exception:
            return []

    def profile(self, acheteur: Optional[str]) -> Optional[dict]:
        """Profil de publication d'un acheteur (CACHÉ), ou None si introuvable / source KO."""
        name = (acheteur or "").replace('"', " ").strip()
        if len(name) < 3:
            return None
        now = time.monotonic()
        with _LOCK:
            ent = _CACHE.get(name)
            if ent and ent[0] > now:
                return ent[1]
        result = self._build(name)
        with _LOCK:
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.pop(next(iter(_CACHE)), None)
            _CACHE[name] = (now + _CACHE_TTL, result)   # on cache aussi l'absence (None)
        return result

    def _build(self, name: str) -> Optional[dict]:
        where = f'nomacheteur like "{name}"'
        total = self._count(where)
        if total == 0:
            return None

        since = (date.today() - timedelta(days=365)).isoformat()
        # Les 4 requêtes restantes sont indépendantes → en PARALLÈLE (≈ 1 appel, pas 4).
        with ThreadPoolExecutor(max_workers=4) as ex:
            f_12m = ex.submit(self._count, f'{where} AND dateparution >= "{since}"')
            f_sect = ex.submit(self._group, where, "descripteur_libelle")
            f_zone = ex.submit(self._group, where, "code_departement")
            f_rec = ex.submit(self._recents, where)
            recent_12m = f_12m.result()
            secteurs = f_sect.result()
            zones = f_zone.result()
            recents = f_rec.result()

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
