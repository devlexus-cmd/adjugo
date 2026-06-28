"""
INDICE D'INFRUCTUOSITÉ (côté ACHETEUR) — Pilier 2.

Évalue, pour un LOT, le RISQUE qu'aucune offre (ou trop peu d'offres recevables) ne soit
remise — l'inverse d'un « bon score ». DÉTERMINISTE et explicable (même esprit que
`app/services/dce_scoring.score_dce` : barème ouvert, contribution par critère, détail
traçable). Un score ÉLEVÉ = RISQUE ÉLEVÉ ; on l'affiche explicitement en « risque % ».

Entrée = signaux MESURÉS par le moteur de sourcing (aucune invention) :
  - nb_capables       : PME au score d'adéquation ≥ seuil sur ce lot/territoire
  - nb_capacite_prouvee : PME ayant déjà remporté un marché public (DECP)
  - nb_local          : PME implantées dans le département d'exécution
  - nb_sain           : PME sans procédure collective en cours (BODACC)
  - nb_groupement     : PME pouvant former un groupement (synergie suffisante)

Tout cela alimente des CONSEILS actionnables (générés ailleurs) : allotir, assouplir un
critère, allonger le délai, faire du sourcing, encourager un groupement.
"""

# Barème de RISQUE (somme des max = 100). Plus de points = plus de risque.
_MAX = {"vivier": 35, "capacite": 25, "densite": 20, "sante": 10, "groupement": 10}


def _risk_vivier(nb: int) -> tuple:
    table = {0: 35, 1: 28, 2: 20, 3: 12, 4: 6}
    r = table.get(nb, 0)
    if nb == 0:
        d = "Aucune PME capable identifiée sur ce lot — infructuosité très probable."
    elif nb <= 2:
        d = f"Seulement {nb} PME capable(s) — concurrence insuffisante, offres fragiles."
    elif nb <= 4:
        d = f"{nb} PME capables — concurrence limitée mais possible."
    else:
        d = f"{nb} PME capables — vivier suffisant."
    return r, d


def _risk_capacite(nb: int) -> tuple:
    table = {0: 25, 1: 15, 2: 8}
    r = table.get(nb, 0)
    if nb == 0:
        d = "Aucune PME du vivier n'a d'historique de marché public gagné (DECP)."
    elif nb <= 2:
        d = f"{nb} PME avec une capacité prouvée (marchés déjà remportés, DECP)."
    else:
        d = f"{nb} PME avec capacité prouvée — antériorité solide."
    return r, d


def _risk_densite(nb: int) -> tuple:
    # Mesure le VIVIER MOBILISABLE sur la zone d'exécution (probabilité d'offres de
    # proximité), PAS une préférence pour le local (qui serait illégale à l'attribution).
    table = {0: 20, 1: 12, 2: 6}
    r = table.get(nb, 0)
    if nb == 0:
        d = "Aucune PME capable sur la zone d'exécution — peu d'offres de proximité attendues."
    elif nb <= 2:
        d = f"{nb} PME capable(s) sur la zone d'exécution — vivier de proximité limité."
    else:
        d = f"{nb} PME capables sur la zone d'exécution — vivier de proximité suffisant."
    return r, d


def _risk_sante(nb_capables: int, nb_sain: int) -> tuple:
    if nb_capables <= 0:
        return _MAX["sante"], "Vivier vide : santé financière non évaluable."
    fragiles = max(0, nb_capables - nb_sain)
    r = round(_MAX["sante"] * fragiles / nb_capables)
    if fragiles == 0:
        d = "Aucune procédure collective en cours détectée parmi les PME capables (BODACC)."
    else:
        d = f"{fragiles}/{nb_capables} PME capable(s) en procédure collective (BODACC) — fragilité."
    return r, d


def _risk_groupement(nb_capables: int, nb_groupement: int) -> tuple:
    # Un groupement RÉDUIT le risque quand le vivier solo est mince.
    if nb_capables >= 3:
        return 0, "Vivier solo suffisant : le groupement n'est pas nécessaire."
    if nb_groupement >= 1:
        return 3, f"{nb_groupement + 1} PME peuvent se grouper — atténue le risque sur un lot mince."
    return _MAX["groupement"], "Vivier mince et aucun groupement viable identifié."


def score_infructuosite(lot_label: str, signals: dict) -> dict:
    """Renvoie {lot, risque 0-100, niveau, breakdown[], signaux}. Déterministe."""
    s = signals or {}
    nb_capables = int(s.get("nb_capables") or 0)
    nb_cap_prouvee = int(s.get("nb_capacite_prouvee") or 0)
    nb_local = int(s.get("nb_local") or 0)
    nb_sain = int(s.get("nb_sain") or 0)
    nb_groupement = int(s.get("nb_groupement") or 0)

    items = []
    for key, (r, d) in {
        "vivier": _risk_vivier(nb_capables),
        "capacite": _risk_capacite(nb_cap_prouvee),
        "densite": _risk_densite(nb_local),
        "sante": _risk_sante(nb_capables, nb_sain),
        "groupement": _risk_groupement(nb_capables, nb_groupement),
    }.items():
        items.append({"key": key, "label": _LABELS[key], "risque": r, "max": _MAX[key], "detail": d})

    risque = min(100, sum(i["risque"] for i in items))
    return {
        "lot": lot_label,
        "risque": risque,
        "niveau": niveau(risque),
        "breakdown": items,
        "signaux": {"nb_capables": nb_capables, "nb_capacite_prouvee": nb_cap_prouvee,
                    "nb_local": nb_local, "nb_sain": nb_sain, "nb_groupement": nb_groupement},
    }


_LABELS = {
    "vivier": "Vivier de PME capables",
    "capacite": "Capacité prouvée (DECP)",
    "densite": "Vivier sur la zone d'exécution",
    "sante": "Santé financière du vivier",
    "groupement": "Capacité de groupement",
}


def niveau(risque: int) -> str:
    if risque < 25:
        return "faible"
    if risque < 50:
        return "modéré"
    if risque < 75:
        return "élevé"
    return "critique"


def agreger(lots: list) -> dict:
    """Risque global = le PIRE lot prime (un seul lot infructueux fait échouer le marché),
    pondéré par la moyenne pour ne pas sur-réagir à un lot mineur."""
    risques = [int(l.get("risque") or 0) for l in (lots or []) if isinstance(l, dict)]
    if not risques:
        return {"risque": 0, "niveau": "faible", "pire_lot": None}
    pire = max(risques)
    moyenne = round(sum(risques) / len(risques))
    glob = round(0.6 * pire + 0.4 * moyenne)
    pire_lot = next((l.get("lot") for l in lots
                     if isinstance(l, dict) and int(l.get("risque") or 0) == pire), None)
    return {"risque": glob, "niveau": niveau(glob), "pire_lot": pire_lot}
