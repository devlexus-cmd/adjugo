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
# Sous ce nombre de comparables, des quartiles n'ont pas de sens (un seul gros marché peut
# faire basculer la procédure recommandée). On exige un minimum honnête.
_MIN_COMPARABLES = 5


def _trim_iqr(values: list) -> list:
    """Retire les montants aberrants (règle de Tukey, 1,5 × IQR) : un méga-marché isolé ne
    doit pas tirer Q3 ni la fourchette vers le haut. Ne retire jamais tout."""
    if len(values) < 4:
        return values
    s = sorted(values)
    qs = statistics.quantiles(s, n=4, method="inclusive")
    q1, q3 = qs[0], qs[2]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [v for v in s if lo <= v <= hi] or s


def estimer_budget(objet: str, departement: str = "", cpv=None, duree_mois=None) -> dict:
    """Renvoie une estimation {ok, nb_marches, mediane, q1, q3, min, max, periode, exemples}
    basée sur les marchés comparables (DECP). `ok=False` si trop peu de comparables.
    Si `duree_mois` est fourni, on écarte les comparables de durée trop dissemblable
    (hors [0,5× ; 2×]) pour ne pas mélanger des marchés de portée différente."""
    deps = [str(departement).strip()[:2]] if str(departement or "").strip() else []
    try:
        target_dur = float(duree_mois) if duree_mois not in (None, "") else None
        if target_dur is not None and target_dur <= 0:
            target_dur = None
    except (ValueError, TypeError):
        target_dur = None
    try:
        rows = _fetch(objet or "", deps, cpv=cpv, per=100)
    except Exception as e:
        logger.info("estimation budget indisponible : %s", e)
        return {"ok": False, "nb_marches": 0, "error": str(e)[:160]}

    montants, exemples, seen, annees = [], [], set(), []
    for r in rows:
        try:
            m = float(r.get("montant"))
        except (TypeError, ValueError):
            m = None
        if m is None or not (_MIN_MONTANT <= m <= _MAX_MONTANT):
            continue
        try:
            d = float(r.get("dureemois")) if r.get("dureemois") not in (None, "") else None
        except (ValueError, TypeError):
            d = None
        # Durée trop dissemblable de la cible → marché non comparable, on l'écarte.
        if target_dur and d and not (0.5 * target_dur <= d <= 2.0 * target_dur):
            continue
        montants.append(m)
        annee = str(r.get("datenotification") or "")[:4]
        if annee.isdigit():
            annees.append(annee)
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

    montants = _trim_iqr(montants)   # retire les méga-marchés isolés qui fausseraient Q3
    if len(montants) < _MIN_COMPARABLES:
        return {"ok": False, "nb_marches": len(montants),
                "message": "Pas assez de marchés comparables fiables pour estimer "
                           "(élargissez l'objet ou le territoire, ou retirez la contrainte de durée)."}

    montants.sort()
    n = len(montants)
    try:
        qs = statistics.quantiles(montants, n=4, method="inclusive")   # vrais Q1/Q3
        q1, q3 = round(qs[0]), round(qs[2])
    except Exception:
        q1, q3 = round(montants[max(0, n // 4)]), round(montants[min(n - 1, (3 * n) // 4)])
    return {
        "ok": True,
        "nb_marches": n,
        "departement": deps[0] if deps else None,
        "mediane": round(statistics.median(montants)),
        "q1": q1, "q3": q3,
        "min": round(montants[0]),
        "max": round(montants[-1]),
        "periode": (f"{min(annees)}–{max(annees)}" if annees else None),
        "duree_filtree": bool(target_dur),
        "convention": "Montants HT, totaux du marché. Repère de marché non actualisé de "
                      "l'inflation — à ajuster.",
        "exemples": exemples,
    }
