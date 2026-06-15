"""
RADAR DES ÉCHÉANCES — détecter les marchés publics qui arrivent à terme.

Au-delà de la veille sur les AO ouverts, on traque les marchés DÉJÀ ATTRIBUÉS dont
le contrat arrive bientôt à échéance : ils seront re-publiés. L'entreprise peut alors
se positionner auprès de l'acheteur AVANT la republication officielle (avantage temporel).

Données : avis d'attribution BOAMP (réels, traçables par idweb + lien). La durée est
extraite du texte quand elle est citée, sinon ESTIMÉE par type de contrat — et toujours
labellisée « estimation ». Aucune date ni titulaire inventé (anti-hallucination).
"""
import logging
from datetime import date, timedelta

import httpx

from app.services.llm import complete_json
from app.services.agents.amont import _words, _deps, _dep_of  # helpers de scoring partagés

logger = logging.getLogger("adjugo")
API = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"
SELECT = "idweb,objet,nomacheteur,code_departement,dateparution,descripteur_libelle,url_avis,annonce_lie"

# Durées par défaut (mois) quand non citée — bornes prudentes du droit des marchés publics.
_DEFAULT_DUREE = {"accord-cadre": 48, "marché": 30, None: 36}


def _fetch_attributions(query: str, departements, per: int = 50) -> list:
    q = (query or "travaux").replace('"', " ").strip()
    today = date.today()
    start = (today - timedelta(days=int(5 * 365))).isoformat()   # attribué il y a ≤ 5 ans
    end = (today - timedelta(days=int(1.5 * 365))).isoformat()   # … et ≥ 1,5 an (zone de renouvellement)
    where = f'nature="ATTRIBUTION" AND (objet like "{q}" OR descripteur_libelle like "{q}")'
    if departements:
        deps = " OR ".join(f'code_departement like "{d}"' for d in departements)
        where = f"({where}) AND ({deps})"
    where += f" AND dateparution >= date'{start}' AND dateparution <= date'{end}'"
    params = {"limit": min(per, 60), "order_by": "-dateparution", "where": where, "select": SELECT}
    r = httpx.get(API, params=params, timeout=14)
    r.raise_for_status()
    out = []
    for row in r.json().get("results", []):
        deps = row.get("code_departement") or []
        if not isinstance(deps, list):
            deps = [str(deps)]
        desc = row.get("descripteur_libelle") or []
        idweb = str(row.get("idweb", "") or "")
        out.append({
            "idweb": idweb,
            "objet": (row.get("objet") or "").strip()[:400],
            "acheteur": _as_str(row.get("nomacheteur")),
            "dept": (deps[0] if deps else ""),
            "lieu": ", ".join(desc) if isinstance(desc, list) and desc else "",
            "date_attribution": (row.get("dateparution") or "")[:10],
            "url": row.get("url_avis") or (f"https://www.boamp.fr/avis/detail/{idweb}" if idweb else ""),
        })
    return out


_SYS = """Tu analyses des avis d'attribution de marchés publics pour estimer quand le
contrat arrivera à échéance (donc quand un nouveau marché sera publié). Pour chaque avis :
- garde-le s'il s'agit d'un marché de travaux/services/fournitures pertinent (sinon écarte) ;
- extrais la DURÉE en mois UNIQUEMENT si elle est explicitement déductible de l'objet
  (ex. « accord-cadre de 4 ans », « 36 mois »), sinon null (on estimera) ;
- indique le type (accord-cadre / marché) si déductible, sinon null.
N'invente JAMAIS de durée ni de titulaire. Réponds en JSON strict."""


def detect_renewals(query: str, departements, criteria: dict, domaines=None, lang_name: str = None) -> dict:
    """Renvoie les marchés attribués dont le renouvellement est proche (fenêtre d'attaque)."""
    try:
        records = _fetch_attributions(query, departements)
    except Exception as e:
        logger.warning("Radar échéances : BOAMP indisponible : %s", e)
        return {"count": 0, "renewals": [], "errors": [f"BOAMP indisponible : {e}"]}
    if not records:
        return {"count": 0, "renewals": [], "errors": []}

    lines = "\n".join(f"{i}. [{r['acheteur'] or ''}] {r['objet']}" for i, r in enumerate(records))
    user = f"""Avis d'attribution (numérotés). Renvoie EXACTEMENT ce JSON :
{{"avis": [
  {{"index": <n>, "garder": true|false, "duree_mois": <int ou null>, "type": "accord-cadre|marché|null"}}
]}}

LISTE :
{lines}"""
    try:
        data = complete_json(_SYS, user, max_tokens=2600, temperature=0.1)
        enrich = {a.get("index"): a for a in (data.get("avis") or []) if isinstance(a, dict)}
    except Exception as e:
        logger.warning("Radar échéances : enrichissement IA en échec : %s", e)
        enrich = {}

    today = date.today()
    win_start, win_end = today - timedelta(days=180), today + timedelta(days=550)  # fenêtre d'attaque
    out = []
    for i, r in enumerate(records):
        info = enrich.get(i, {})
        if enrich and info.get("garder") is False:
            continue
        aw = _parse(r["date_attribution"])
        if not aw:
            continue
        duree = info.get("duree_mois")
        ctype = info.get("type") if info.get("type") in ("accord-cadre", "marché") else None
        estimated = duree is None
        if not isinstance(duree, (int, float)) or duree <= 0:
            duree = _DEFAULT_DUREE.get(ctype, 36)
        fin = aw + timedelta(days=int(duree * 30.4))
        renouv = fin - timedelta(days=120)   # republication anticipée ~4 mois avant la fin
        if not (win_start <= renouv <= win_end):
            continue
        score = _score(r, criteria, domaines, renouv, today)
        out.append({
            "idweb": r["idweb"], "objet": r["objet"], "acheteur": r["acheteur"],
            "lieu": r["lieu"], "dept": r["dept"], "date_attribution": r["date_attribution"],
            "duree_mois": int(duree), "duree_estimee": estimated, "type_contrat": ctype or "",
            "fin_estimee": fin.isoformat(), "renouvellement_estime": renouv.isoformat(),
            "score": score, "url": r["url"],
        })
    out.sort(key=lambda x: (x["score"], x["renouvellement_estime"]), reverse=True)
    return {"count": len(out), "renewals": out, "errors": []}


def _score(r, criteria, domaines, renouv, today) -> int:
    """Score 0-100 : pertinence métier/domaine (45) · zone (25) · imminence (30)."""
    criteria = criteria or {}
    hay = (str(r.get("objet", "")) + " " + str(r.get("lieu", ""))).lower()
    specs = [s.strip().lower() for s in str(criteria.get("specialites", "")).replace(";", ",").split(",") if s.strip()]
    doms = [str(d).lower() for d in (domaines or [])]
    if (doms and any(_words(d) & _words(hay) for d in doms)) or (specs and any(_words(s) & _words(hay) for s in specs)):
        metier = 45
    elif not specs and not doms:
        metier = 27
    else:
        metier = 10
    deps = _deps(criteria.get("departements"))
    zone = 25 if (deps and r.get("dept") in deps) else (15 if not deps else 6)
    days = (renouv - today).days
    imminence = 30 if days <= 90 else (24 if days <= 270 else 16)  # plus c'est proche, plus c'est chaud
    return min(100, metier + zone + imminence)


def _parse(s):
    try:
        from datetime import datetime
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _as_str(v):
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip()) or None
    return str(v).strip() or None
