"""
ESTIMATION BUDGÉTAIRE (côté ACHETEUR) — fourchette de prix de référence.

À partir des marchés SIMILAIRES réellement attribués (DECP, montants structurés réels),
on calcule une fourchette robuste (interquartile) et une médiane comme repère pour fixer
le montant estimé. 100 % DÉTERMINISTE (pas de LLM), sourcé, non contraignant : un repère
de marché, pas une estimation contractuelle.
"""
import logging
import statistics

from app.services.decp import _fetch

logger = logging.getLogger("adjugo")

# Bornes de filtrage des montants DECP aberrants (0, erreurs de saisie, méga-marchés
# nationaux qui fausseraient la médiane locale).
_MIN_MONTANT = 500.0
_MAX_MONTANT = 80_000_000.0


def estimer_budget(objet: str, departement: str = "", cpv=None) -> dict:
    """Renvoie une estimation {ok, nb_marches, mediane, q1, q3, min, max, exemples} basée
    sur les marchés comparables (DECP). `ok=False` si trop peu de comparables."""
    deps = [str(departement).strip()[:2]] if str(departement or "").strip() else []
    try:
        rows = _fetch(objet or "", deps, cpv=cpv, per=100)
    except Exception as e:
        logger.info("estimation budget indisponible : %s", e)
        return {"ok": False, "nb_marches": 0, "error": str(e)[:160]}

    montants, exemples, seen = [], [], set()
    for r in rows:
        try:
            m = float(r.get("montant"))
        except (TypeError, ValueError):
            m = None
        if m is None or not (_MIN_MONTANT <= m <= _MAX_MONTANT):
            continue
        montants.append(m)
        key = (r.get("objet") or "").lower()[:60]
        if len(exemples) < 6 and key not in seen:
            seen.add(key)
            exemples.append({
                "objet": (r.get("objet") or "").strip()[:90],
                "montant": round(m),
                "date": str(r.get("datenotification") or "")[:7],
                "duree_mois": r.get("dureemois"),
                "dept": (str(r.get("lieuexecution_code") or "")[:2]),
            })

    if len(montants) < 3:
        return {"ok": False, "nb_marches": len(montants),
                "message": "Pas assez de marchés comparables pour estimer (élargissez l'objet ou le territoire)."}

    montants.sort()
    n = len(montants)
    return {
        "ok": True,
        "nb_marches": n,
        "departement": deps[0] if deps else None,
        "mediane": round(statistics.median(montants)),
        "q1": round(montants[max(0, n // 4)]),
        "q3": round(montants[min(n - 1, (3 * n) // 4)]),
        "min": round(montants[0]),
        "max": round(montants[-1]),
        "exemples": exemples,
    }
