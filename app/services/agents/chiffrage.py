"""
AGENT CHIFFRAGE — devis estimatif d'une réponse à un appel d'offres.

L'IA PROPOSE un découpage de la prestation en tâches (méthodologie calquée sur la
demande du DCE), avec un profil de prestation et un nombre de jours par tâche. Le PRIX
est ensuite calculé de façon DÉTERMINISTE — jours × tarif(profil) × majoration distance —
jamais sorti du LLM (cohérent avec la charte anti-hallucination d'Adjugo).
"""
from app.services.llm import complete_json, MODEL_FAST

# Profils par défaut proposés à une entreprise qui n'a rien configuré.
DEFAULT_RATES = [
    {"label": "Étude / conception", "rate": 650},
    {"label": "Production / édition", "rate": 450},
    {"label": "Encadrement / direction", "rate": 850},
    {"label": "Exécution / terrain", "rate": 400},
]

_SYSTEM = """Tu es un chiffreur expert en marchés publics français. À partir d'un appel
d'offres, tu découpes la prestation à réaliser en TÂCHES concrètes et réalistes, organisées
en phases (préparation, étude/conception, production, contrôle/qualité, livraison…).

Pour CHAQUE tâche, tu donnes :
- un "profil" de prestation choisi STRICTEMENT dans la liste fournie,
- une estimation prudente du nombre de "jours" (nombre, décimales autorisées).

Tu NE donnes JAMAIS de prix ni de tarif (le prix est calculé séparément, pas par toi).
Tu restes réaliste : ni gonflé, ni sous-estimé. Tu réponds en JSON strict, sans texte autour."""


def propose_tasks(details: dict, rate_labels: list, lang_name: str = None) -> list:
    """L'IA découpe l'AO en tâches {phase, tache, profil, jours}. Liste vide si échec."""
    profiles = " | ".join(rate_labels) if rate_labels else " | ".join(r["label"] for r in DEFAULT_RATES)
    lang = f"\nRédige les libellés en {lang_name}." if (lang_name and lang_name != "français") else ""
    user = f"""APPEL D'OFFRES :
- Intitulé : {details.get('intitule_marche', '')}
- Type : {details.get('type_marche', '')}
- Lieu d'exécution : {details.get('lieu_execution', '')}
- Délai d'exécution : {details.get('delai_execution', '')}
- Allotissement : {details.get('allotissement', '')}
- Critères d'attribution : {details.get('criteres_attribution', '')}
- Exigences RSE : {details.get('critere_rse', '')}

PROFILS DE PRESTATION DISPONIBLES (choisis-en un par tâche) : {profiles}

Découpe la réponse en 5 à 12 tâches. Réponds EXACTEMENT ce JSON :
{{"taches": [{{"phase": "...", "tache": "intitulé court et concret", "profil": "<un des profils ci-dessus>", "jours": <nombre>}}]}}{lang}"""
    try:
        data = complete_json(_SYSTEM, user, max_tokens=1800, temperature=0.2)
    except Exception:
        return []
    out = []
    for t in (data.get("taches") or []):
        if not isinstance(t, dict):
            continue
        try:
            days = max(0.0, float(t.get("jours") or 0))
        except (ValueError, TypeError):
            days = 0.0
        tache = str(t.get("tache", "")).strip()[:200]
        if tache:
            out.append({"phase": str(t.get("phase", "")).strip()[:80], "tache": tache,
                        "profil": str(t.get("profil", "")).strip()[:80], "jours": round(days, 1)})
    return out


def compute_estimate(tasks: list, day_rates: list, distance_km: float = 0,
                     threshold_km: float = 50, surcharge_pct: float = 0) -> dict:
    """Calcul DÉTERMINISTE et explicable du devis. Aucun appel LLM.
    day_rates : [{label, rate}]. Majoration appliquée si distance_km > threshold_km."""
    rate_by = {}
    for r in (day_rates or []):
        try:
            rate_by[str(r.get("label", ""))] = float(r.get("rate") or 0)
        except (ValueError, TypeError):
            continue
    positives = [v for v in rate_by.values() if v > 0]
    default_rate = round(sum(positives) / len(positives)) if positives else 500

    over = bool(distance_km and threshold_km and float(distance_km) > float(threshold_km))
    surcharge = (float(surcharge_pct or 0) / 100.0) if over else 0.0

    lignes, total = [], 0
    for t in (tasks or []):
        days = float(t.get("jours", 0) or 0)
        rate = rate_by.get(t.get("profil", ""), default_rate)
        montant = round(days * rate * (1 + surcharge))   # arrondi à la ligne
        total += montant                                 # le total = somme des lignes (cohérent)
        lignes.append({"phase": t.get("phase", ""), "tache": t.get("tache", ""),
                       "profil": t.get("profil", ""), "jours": round(days, 1),
                       "tarif": round(rate), "montant": montant})
    jours = round(sum(float(t.get("jours", 0) or 0) for t in (tasks or [])), 1)
    return {
        "lignes": lignes,
        "total_ht": round(total),
        "jours_total": jours,
        "tarif_moyen": round(total / jours) if jours else 0,
        "distance_km": round(float(distance_km or 0)),
        "majoration_pct": round(surcharge * 100),
        "deterministe": True,
    }
