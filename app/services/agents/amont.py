"""
AGENT VEILLE AMONT — détection de signaux d'investissement.

À partir d'une délibération ou d'un compte-rendu de collectivité, l'IA détecte les
PROJETS D'INVESTISSEMENT FUTURS (construction, réhabilitation, voirie, équipement…)
susceptibles de donner lieu à un appel d'offres — des mois AVANT sa publication.

Règle anti-hallucination : on n'extrait QUE des projets réellement mentionnés dans le
document. Aucun budget, date ou projet inventé. Chaque signal porte un extrait du texte.
La pertinence vs l'entreprise est calculée de façon déterministe et explicable.
"""
import re
from app.services.llm import complete_json

SYSTEM = """Tu es un analyste de la commande publique spécialisé dans la détection
amont. À partir d'une délibération ou d'un compte-rendu de conseil (municipal,
communautaire, départemental, régional), tu repères les PROJETS D'INVESTISSEMENT
FUTURS susceptibles de déboucher sur un marché public : construction, réhabilitation,
extension, voirie/VRD, réseaux, équipements, aménagement, gros entretien.

RÈGLES STRICTES :
- N'extrais QUE des projets réellement présents dans le document.
- N'invente JAMAIS de budget, de date, de localisation ni de projet.
- Si un montant est cité, reporte-le ; sinon budget = null.
- Pour chaque projet, fournis un extrait COURT et fidèle du document (traçabilité).
- S'il n'y a aucun projet d'investissement, renvoie une liste vide.
Réponds en JSON strict, sans texte autour."""


def detect_projets(text: str, lang_name: str = None) -> dict:
    """Retourne {collectivite, projets:[...]} détectés dans le document."""
    if not text or len(text) < 60:
        return {"collectivite": "", "projets": []}
    lang = f" Rédige les valeurs textuelles en {lang_name}." if (lang_name and lang_name != "français") else ""
    user = f"""Analyse ce document de collectivité et renvoie EXACTEMENT ce JSON :
{{
  "collectivite": "nom de la collectivité émettrice (mairie, communauté, département, région)",
  "projets": [
    {{
      "intitule": "intitulé court du projet",
      "type_projet": "construction|réhabilitation|voirie|réseaux|équipement|aménagement|autre",
      "budget": <nombre en euros si cité, sinon null>,
      "budget_texte": "le montant tel que cité (ex. « 8 M€ HT »), sinon \"\"",
      "localisation": "commune / lieu si précisé, sinon \"\"",
      "calendrier": "échéance estimée de l'AO si déductible du texte, sinon \"\"",
      "metiers": ["métiers BTP concernés, ex. maçonnerie, électricité, CVC, VRD"],
      "extrait": "citation courte et fidèle du document justifiant le projet"
    }}
  ]
}}{lang}

DOCUMENT :
{text[:16000]}"""
    try:
        data = complete_json(SYSTEM, user, max_tokens=2200, temperature=0.1)
    except Exception:
        return {"collectivite": "", "projets": []}
    if not isinstance(data, dict):
        return {"collectivite": "", "projets": []}
    projets = data.get("projets") or []
    # garde-fou : ne garde que des entrées avec un intitulé
    projets = [p for p in projets if isinstance(p, dict) and (p.get("intitule") or "").strip()]
    return {"collectivite": (data.get("collectivite") or "").strip(), "projets": projets}


BATCH_SYSTEM = """Tu tries des intitulés de délibérations de collectivités pour ne garder
que les PROJETS D'INVESTISSEMENT / TRAVAUX futurs susceptibles de déboucher sur un marché
public (construction, réhabilitation, voirie/VRD, réseaux, équipements, aménagement, ZAC,
gros entretien). Tu ÉCARTES le fonctionnement courant : subventions sans travaux, ressources
humaines, conventions administratives, tarifs, motions, finances générales. N'invente jamais
de budget. Réponds en JSON strict."""


def detect_from_deliberations(records: list, lang_name: str = None) -> list:
    """Détecte les projets d'investissement dans un lot d'intitulés de délibérations
    récupérés en open data. Un seul appel IA. Renvoie les projets enrichis de leur source."""
    records = (records or [])[:70]
    if not records:
        return []
    lang = f" Rédige en {lang_name}." if (lang_name and lang_name != "français") else ""
    lines = "\n".join(f"{i}. [{r.get('collectivite','')}] {r.get('objet','')}" for i, r in enumerate(records))
    user = f"""Voici des intitulés de délibérations (numérotés). Renvoie EXACTEMENT ce JSON :
{{"projets": [
  {{"index": <numéro de la ligne>, "intitule": "intitulé reformulé clair du projet",
    "type_projet": "construction|réhabilitation|voirie|réseaux|équipement|aménagement|autre",
    "budget": <euros si un montant figure, sinon null>, "budget_texte": "montant cité ou \"\"",
    "localisation": "lieu si présent, sinon \"\"",
    "metiers": ["métiers BTP concernés"]}}
]}}
Ne garde QUE les vrais projets d'investissement/travaux ; ignore le reste.{lang}

INTITULÉS :
{lines}"""
    try:
        data = complete_json(BATCH_SYSTEM, user, max_tokens=2600, temperature=0.1)
    except Exception:
        return []
    out = []
    for p in (data.get("projets") or []):
        if not isinstance(p, dict) or not (p.get("intitule") or "").strip():
            continue
        idx = p.get("index")
        rec = records[idx] if isinstance(idx, int) and 0 <= idx < len(records) else {}
        p["collectivite"] = (p.get("collectivite") or rec.get("collectivite") or "").strip()
        p["date"] = rec.get("date", "")
        p["source"] = rec.get("source", "open data")
        p["url"] = rec.get("url", "")
        p["dept"] = rec.get("dept", "")
        if not p.get("extrait"):
            p["extrait"] = rec.get("objet", "")
        out.append(p)
    return out


def score_pertinence(projet: dict, criteria: dict) -> tuple:
    """Score 0-100 de pertinence du projet pour l'entreprise (déterministe, explicable).
    Renvoie (score, label) avec label pertinent | a_etudier | faible."""
    criteria = criteria or {}
    hay = " ".join(str(projet.get(k, "")) for k in ("intitule", "type_projet", "localisation"))
    hay += " " + " ".join(str(m) for m in (projet.get("metiers") or []))
    hay = hay.lower()

    # 1) Métier (50) — recoupement avec les spécialités du profil
    specs = [s.strip().lower() for s in re.split(r"[,;]", str(criteria.get("specialites", ""))) if s.strip()]
    if not specs:
        metier = 30  # profil sans spécialité → on ne pénalise pas
    elif any(_words(s) & _words(hay) for s in specs):
        metier = 50
    else:
        metier = 0

    # 2) Zone (30) — département du projet vs départements ciblés
    deps = _deps(criteria.get("departements"))
    loc_dep = _dep_of(projet.get("localisation", ""))
    if not deps:
        zone = 18
    elif loc_dep and loc_dep in deps:
        zone = 30
    elif loc_dep:
        zone = 6
    else:
        zone = 14  # localisation inconnue

    # 3) Budget (20) — dans la fourchette visée
    bmin, bmax = criteria.get("budget_min"), criteria.get("budget_max")
    b = projet.get("budget")
    if b is None:
        budget = 12
    elif (bmin in (None, 0) or b >= bmin) and (bmax in (None, 0) or b <= bmax):
        budget = 20
    else:
        budget = 8

    score = min(100, metier + zone + budget)
    label = "pertinent" if score >= 62 else ("a_etudier" if score >= 38 else "faible")
    return score, label


def _words(s: str) -> set:
    return {w for w in re.split(r"\W+", str(s).lower()) if len(w) > 3}


def _deps(v) -> list:
    if isinstance(v, list):
        return [str(x).strip()[:2] for x in v if str(x).strip()]
    return [d.strip()[:2] for d in re.split(r"[,;\s]+", str(v or "")) if d.strip()]


def _dep_of(localisation: str) -> str:
    m = re.search(r"\b(\d{2})\d{3}\b", str(localisation))   # code postal → département
    return m.group(1) if m else ""
