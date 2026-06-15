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
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(0.4 * (2 ** i))
    raise last


def safe_terms(q: str) -> str:
    """Assainit une requête utilisateur avant interpolation dans un `where` ODSQL :
    on ne garde que lettres/chiffres/espaces/traits — neutralise guillemets et opérateurs."""
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ÿ \-']", " ", str(q or ""))
    return re.sub(r"\s+", " ", cleaned).strip()
