"""HTTP partagé pour les sources open-data : retry avec backoff + assainissement
des requêtes (les APIs gouv. ont des micro-coupures ; une seule ne doit pas renvoyer
zéro résultat). Distingue « source en panne » (lève) de « zéro résultat »."""
import re
import time

import httpx


def get_with_retry(url: str, params: dict = None, timeout: float = 12, tries: int = 3,
                   headers: dict = None):
    """GET avec 2-3 essais et backoff exponentiel. Lève la dernière erreur si tout échoue."""
    last = None
    for i in range(tries):
        try:
            r = httpx.get(url, params=params, timeout=timeout, headers=headers)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            # Erreur 4xx (hors 408/429) = non récupérable (mauvaise requête) → on ne rejoue pas.
            sc = e.response.status_code
            if 400 <= sc < 500 and sc not in (408, 429):
                raise
            last = e
            if i < tries - 1:
                time.sleep(0.4 * (2 ** i))
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(0.4 * (2 ** i))   # 0.4s, 0.8s
    raise last


def post_with_retry(url: str, json: dict = None, timeout: float = 15, tries: int = 3,
                    headers: dict = None):
    last = None
    for i in range(tries):
        try:
            r = httpx.post(url, json=json, timeout=timeout, headers=headers)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            sc = e.response.status_code
            if 400 <= sc < 500 and sc not in (408, 429):
                raise   # non récupérable → pas de réessai
            last = e
            if i < tries - 1:
                time.sleep(0.4 * (2 ** i))
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(0.4 * (2 ** i))
    raise last


def safe_terms(q: str, max_len: int = 200) -> str:
    """Assainit une requête utilisateur avant interpolation dans un `where` ODSQL.
    On ne garde que lettres/chiffres/espaces/traits — et surtout PAS l'apostrophe ni le
    guillemet, qui délimitent les chaînes ODSQL (neutralise toute évasion). Longueur bornée."""
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ÿ \-]", " ", str(q or ""))
    return re.sub(r"\s+", " ", cleaned).strip()[:max_len]
