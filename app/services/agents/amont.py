"""
AGENT VEILLE AMONT — détection PROFONDE de signaux d'investissement.

À partir d'une délibération, d'un budget, d'un PPI ou d'un débat d'orientation
budgétaire (DOB), l'IA détecte les PROJETS D'INVESTISSEMENT FUTURS susceptibles de
déboucher sur un marché public — des mois AVANT sa publication.

Profondeur (vs simple détection) :
- phase du projet (idée → étude → programmation → financement voté → concours → imminent),
- échéance estimée de publication de l'AO,
- financement cité (DETR, DSIL, autofinancement, subventions…),
- MATURITÉ 0-100 : probabilité estimée qu'un marché public en découle réellement,
- domaine (bâtiment, voirie/VRD, réseaux, énergie, espaces verts, numérique, équipement…).

Ciblage : l'entreprise peut cibler des DOMAINES ; la détection les priorise et le
scoring booste les correspondances. Anti-hallucination : rien n'est inventé, chaque
signal porte un extrait du texte ; maturité/phase déduites uniquement des indices présents.
"""
import re
from app.services.llm import complete_json

DOMAINES = ["bâtiment", "voirie / VRD", "réseaux (eau, assainissement, énergie)",
            "espaces verts / aménagement", "énergie / rénovation énergétique",
            "numérique / télécom", "équipement / mobilier", "études / maîtrise d'œuvre"]

SYSTEM = """Tu es un analyste senior de la commande publique, spécialisé dans la
détection AMONT. À partir d'un document de collectivité (délibération, compte-rendu,
budget primitif, plan pluriannuel d'investissement, débat d'orientation budgétaire),
tu repères les PROJETS D'INVESTISSEMENT FUTURS susceptibles de déboucher sur un marché
public, et tu évalues leur MATURITÉ (probabilité qu'un appel d'offres suive).

RÈGLES STRICTES (anti-hallucination) :
- N'extrais QUE des projets réellement présents dans le document.
- N'invente JAMAIS de budget, de date, de financement ni de projet.
- Maturité et phase sont DÉDUITES des indices du texte (montant voté, AP/CP ouvertes,
  étude lancée, concours, calendrier) — sois prudent, n'exagère pas.
- Chaque projet porte un extrait COURT et fidèle (traçabilité).
- S'il n'y a aucun projet d'investissement, renvoie une liste vide.
Réponds en JSON strict, sans texte autour."""


def _focus(domaines) -> str:
    if not domaines:
        return ""
    d = ", ".join(str(x) for x in domaines)
    return (f"\n\nL'entreprise cible en priorité les domaines : {d}. "
            "Repère TOUS les projets, mais sois particulièrement attentif et exhaustif "
            "sur ces domaines (y compris les signaux faibles).")


_PROJ_SHAPE = """{
      "intitule": "intitulé court et clair du projet",
      "type_projet": "construction|réhabilitation|extension|voirie|réseaux|aménagement|équipement|rénovation énergétique|étude|autre",
      "domaine": "bâtiment|voirie / VRD|réseaux|espaces verts / aménagement|énergie / rénovation énergétique|numérique / télécom|équipement|études / maîtrise d'œuvre|autre",
      "budget": <nombre en euros si cité, sinon null>,
      "budget_texte": "le montant tel que cité (ex. « 8 M€ HT »), sinon \\"\\"",
      "localisation": "commune / lieu si précisé, sinon \\"\\"",
      "phase": "idée|étude|programmation|financement voté|concours|imminent",
      "echeance_ao": "estimation de la période de publication de l'AO (ex. « S2 2026 », « 2027 »), sinon \\"\\"",
      "financement": "sources de financement citées (DETR, DSIL, subvention région, autofinancement…), sinon \\"\\"",
      "maturite": <0-100 : probabilité estimée qu'un marché public en découle, fondée sur la phase et les indices>,
      "metiers": ["métiers / corps d'état concernés"],
      "extrait": "citation courte et fidèle du document justifiant le projet"
    }"""


def detect_projets(text: str, lang_name: str = None, domaines=None) -> dict:
    """Retourne {collectivite, projets:[...]} détectés en profondeur dans le document."""
    if not text or len(text) < 60:
        return {"collectivite": "", "projets": []}
    lang = f" Rédige les valeurs textuelles en {lang_name}." if (lang_name and lang_name != "français") else ""
    user = f"""Analyse ce document de collectivité et renvoie EXACTEMENT ce JSON :
{{
  "collectivite": "nom de la collectivité émettrice (mairie, communauté, département, région)",
  "projets": [
    {_PROJ_SHAPE}
  ]
}}{lang}{_focus(domaines)}

DOCUMENT :
{text[:18000]}"""
    from app.services.llm import LLMUnavailable
    try:
        data = complete_json(SYSTEM, user, max_tokens=2800, temperature=0.1)
    except LLMUnavailable:
        raise   # panne IA → le routeur rembourse + 503 (pas un faux « rien détecté » facturé)
    except Exception:
        return {"collectivite": "", "projets": []}
    if not isinstance(data, dict):
        return {"collectivite": "", "projets": []}
    projets = [_clean(p) for p in (data.get("projets") or []) if isinstance(p, dict) and (p.get("intitule") or "").strip()]
    return {"collectivite": (data.get("collectivite") or "").strip(), "projets": projets}


BATCH_SYSTEM = """Tu tries des intitulés de délibérations / lignes budgétaires de
collectivités pour ne garder que les PROJETS D'INVESTISSEMENT / TRAVAUX futurs
susceptibles de déboucher sur un marché public (construction, réhabilitation,
voirie/VRD, réseaux, équipements, aménagement, ZAC, rénovation énergétique, études).
Tu ÉVALUES la maturité (probabilité d'AO) à partir des indices présents. Tu ÉCARTES le
fonctionnement courant (subventions sans travaux, RH, conventions, tarifs, motions).
N'invente jamais de budget ni de date. Réponds en JSON strict."""


def detect_from_deliberations(records: list, lang_name: str = None, domaines=None) -> list:
    """Détecte (en profondeur) les projets d'investissement dans un lot d'intitulés
    récupérés en open data. Un seul appel IA. Projets enrichis de leur source."""
    records = (records or [])[:80]
    if not records:
        return []
    lang = f" Rédige en {lang_name}." if (lang_name and lang_name != "français") else ""
    lines = "\n".join(f"{i}. [{r.get('collectivite','')}] {r.get('objet','')}" for i, r in enumerate(records))
    user = f"""Voici des intitulés de délibérations / lignes budgétaires (numérotés).
Renvoie EXACTEMENT ce JSON :
{{"projets": [
  {{"index": <numéro de la ligne>,
    "intitule": "intitulé reformulé clair du projet",
    "type_projet": "construction|réhabilitation|voirie|réseaux|aménagement|équipement|rénovation énergétique|étude|autre",
    "domaine": "bâtiment|voirie / VRD|réseaux|espaces verts / aménagement|énergie / rénovation énergétique|numérique / télécom|équipement|études / maîtrise d'œuvre|autre",
    "budget": <euros si un montant figure, sinon null>, "budget_texte": "montant cité ou \\"\\"",
    "localisation": "lieu si présent, sinon \\"\\"",
    "phase": "idée|étude|programmation|financement voté|concours|imminent",
    "echeance_ao": "estimation période de l'AO ou \\"\\"",
    "financement": "financement cité ou \\"\\"",
    "maturite": <0-100 probabilité qu'un AO suive>,
    "metiers": ["métiers concernés"]}}
]}}
Ne garde QUE les vrais projets d'investissement/travaux ; ignore le reste.{lang}{_focus(domaines)}

INTITULÉS :
{lines}"""
    from app.services.llm import LLMUnavailable
    try:
        data = complete_json(BATCH_SYSTEM, user, max_tokens=3200, temperature=0.1)
    except LLMUnavailable:
        raise   # panne IA → remboursement côté routeur ; le cron l'attrape (dégradation gracieuse)
    except Exception:
        return []
    out = []
    for p in (data.get("projets") or []):
        if not isinstance(p, dict) or not (p.get("intitule") or "").strip():
            continue
        idx = p.get("index")
        rec = records[idx] if isinstance(idx, int) and 0 <= idx < len(records) else {}
        p = _clean(p)
        p["collectivite"] = (p.get("collectivite") or rec.get("collectivite") or "").strip()
        p["date"] = rec.get("date", "")
        p["source"] = rec.get("source", "open data")
        p["url"] = rec.get("url", "")
        p["dept"] = rec.get("dept", "")
        if not p.get("extrait"):
            p["extrait"] = rec.get("objet", "")
        # Ancrage anti-hallucination : la source ici n'est qu'un INTITULÉ (titre nu).
        p = _anchor(p, rec.get("objet", ""), title_only=True)
        out.append(p)
    return out


def _clean(p: dict) -> dict:
    """Normalise les champs profonds (bornage maturité, defaults)."""
    try:
        m = int(float(p.get("maturite"))) if p.get("maturite") not in (None, "") else None
    except (ValueError, TypeError):
        m = None
    p["maturite"] = max(0, min(100, m)) if m is not None else None
    for k in ("domaine", "phase", "echeance_ao", "financement"):
        p[k] = (str(p.get(k) or "")).strip()
    return p


def _anchor(p: dict, source_text: str, title_only: bool) -> dict:
    """Anti-hallucination : un BUDGET et un FINANCEMENT sont des faits — ils ne survivent
    que s'ils sont réellement présents dans le texte source. En mode « titre nu » (scan
    de délibérations), on interdit en plus toute ÉCHÉANCE d'AO devinée (un titre ne la
    porte jamais de façon fiable). La maturité/phase restent des ESTIMATIONS assumées."""
    src = (source_text or "")
    src_l = src.lower()
    # Budget = FAIT MONÉTAIRE : ne survit que si un vrai MONTANT figure dans la source (€/k€/
    # M€/euros…). Un simple chiffre (millésime « 2024 », n° de délibération) ne suffisait pas
    # → un budget HALLUCINÉ par l'IA passait pour un fait sourcé. Garde-fou monétaire strict.
    has_money = bool(re.search(r"\d[\d\s.,]*\s*(?:€|k€|m€|md€|eur\b|euros?|millions?)", src_l))
    if p.get("budget") is not None and not has_money:
        p["budget"] = None
    if (p.get("budget_texte") or "") and not has_money:
        p["budget_texte"] = ""
    # Financement : ne garder que si un terme de financement apparaît dans la source.
    if p.get("financement"):
        fin_terms = ("subvention", "fonds", "dotation", "detr", "dsil", "emprunt", "feder",
                     "région", "departement", "état", "etat", "autofinancement", "europ", "prêt")
        if not any(t in src_l for t in fin_terms):
            p["financement"] = ""
    # Mode « titre nu » (scan de délibérations) : un intitulé ne porte JAMAIS de façon fiable
    # un montant ni une échéance d'AO → on les efface systématiquement (zéro budget deviné).
    if title_only:
        p["echeance_ao"] = ""
        p["budget"] = None
        p["budget_texte"] = ""
    return p


# ── Scoring déterministe (métier 40 · zone 25 · budget 15 · maturité 20) ──────
def score_pertinence(projet: dict, criteria: dict, domaines=None) -> tuple:
    """Score 0-100 de pertinence pour l'entreprise (déterministe, explicable).
    Intègre la MATURITÉ (probabilité d'AO) et le ciblage par DOMAINE."""
    criteria = criteria or {}
    hay = " ".join(str(projet.get(k, "")) for k in ("intitule", "type_projet", "domaine", "localisation"))
    hay += " " + " ".join(str(m) for m in (projet.get("metiers") or []))
    hay = hay.lower()

    # 1) Métier / domaine (40) — spécialités OU domaine ciblé
    specs = [s.strip().lower() for s in re.split(r"[,;]", str(criteria.get("specialites", ""))) if s.strip()]
    dom_targets = [str(d).lower() for d in (domaines or [])]
    dom_match = bool(dom_targets) and any(_words(d) & _words(hay) for d in dom_targets)
    if dom_match:
        metier = 40
    elif not specs:
        metier = 24
    elif any(_words(s) & _words(hay) for s in specs):
        metier = 40
    else:
        metier = 0

    # 2) Zone (25) — on lit d'ABORD le département réel propagé par la source (dept),
    # sinon on retombe sur un parsing de la localisation (le champ dept était ignoré).
    deps = _deps(criteria.get("departements"))
    loc_dep = (str(projet.get("dept") or "").strip()[:2] or _dep_of(projet.get("localisation", "")))
    if not deps:
        zone = 15
    elif loc_dep and loc_dep in deps:
        zone = 25
    elif loc_dep:
        zone = 5
    else:
        zone = 12

    # 3) Budget (15)
    bmin, bmax = criteria.get("budget_min"), criteria.get("budget_max")
    b = projet.get("budget")
    if b is None:
        budget = 9
    elif (bmin in (None, 0) or b >= bmin) and (bmax in (None, 0) or b <= bmax):
        budget = 15
    else:
        budget = 6

    # 4) Maturité / probabilité d'AO (20)
    mat = projet.get("maturite")
    if mat is None:
        mat = _maturite_from_phase(projet.get("phase", ""))
    maturite = round(20 * max(0, min(100, mat)) / 100)

    score = min(100, metier + zone + budget + maturite)
    label = "pertinent" if score >= 62 else ("a_etudier" if score >= 38 else "faible")
    return score, label


_PHASE_MAT = {"imminent": 90, "concours": 80, "financement voté": 75,
              "programmation": 55, "étude": 35, "idée": 20}


def _maturite_from_phase(phase: str) -> int:
    return _PHASE_MAT.get(str(phase or "").strip().lower(), 45)


def _words(s: str) -> set:
    return {w for w in re.split(r"\W+", str(s).lower()) if len(w) > 3}


def _deps(v) -> list:
    if isinstance(v, list):
        return [str(x).strip()[:2] for x in v if str(x).strip()]
    return [d.strip()[:2] for d in re.split(r"[,;\s]+", str(v or "")) if d.strip()]


def _dep_of(localisation: str) -> str:
    m = re.search(r"\b(\d{2})\d{3}\b", str(localisation))
    return m.group(1) if m else ""
