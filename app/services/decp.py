"""
RADAR DES ÉCHÉANCES — version DECP (Données Essentielles de la Commande Publique).

Source : DECP consolidées de l'État (data.economie.gouv.fr, arrêté 22/12/2022, Licence
Ouverte Etalab → réutilisation/rediffusion autorisées). Couvre les marchés attribués de
TOUS les profils acheteurs (AWS, achatpublic, PLACE, régions…), pas seulement BOAMP, et
y compris le SOUS-SEUIL.

Avantage clé vs la version BOAMP+LLM : la DURÉE (dureemois) et la DATE DE NOTIFICATION
sont des champs STRUCTURÉS RÉELS → l'échéance est calculée de façon 100 % DÉTERMINISTE
(aucune estimation LLM, aucune consommation de quota, aucune hallucination possible).
"""
import logging
from datetime import date, timedelta
from functools import lru_cache

from app.sourcing.http import safe_terms, get_with_retry
from app.services.renewal import _score, _parse  # scoring + parsing partagés

logger = logging.getLogger("adjugo")


@lru_cache(maxsize=4096)
def _acheteur_name(siren: str) -> str:
    """SIREN (9 chiffres) → raison sociale via l'annuaire public des entreprises
    (gratuit, sans clé). Mis en cache : un même acheteur n'est résolu qu'une fois.
    Retourne '' en cas d'échec → le repli « SIRET … » est géré par l'appelant."""
    if not (siren and len(siren) == 9 and siren.isdigit()):
        return ""
    try:
        from app.services.registre import lookup_company
        return (lookup_company(siren) or {}).get("name", "") or ""
    except Exception:
        return ""

API = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/decp-2022-marches-valides/records"
SELECT = ("objet,montant,datenotification,dureemois,nature,procedure,acheteur_id,"
          "lieuexecution_code,lieuexecution_typecode,codecpv,source,titulaire_id_1")


def _fetch(query: str, departements, cpv=None, per: int = 100) -> list:
    q = safe_terms(query) or "travaux"   # neutralise l'injection ODSQL
    today = date.today()
    start = (today - timedelta(days=int(5 * 365))).isoformat()       # notifié il y a ≤ 5 ans
    end = (today - timedelta(days=int(0.5 * 365))).isoformat()        # … et ≥ 6 mois
    obj = f'objet like "{q}"'
    if cpv:
        codes = [str(c).strip()[:4] for c in cpv if str(c).strip()[:4].isdigit()]
        if codes:
            obj = "(" + obj + " OR " + " OR ".join(f'codecpv like "{c}"' for c in codes[:5]) + ")"
    where = (f'{obj} AND dureemois > 0 '
             f"AND datenotification >= date'{start}' AND datenotification <= date'{end}'")
    # Filtre département CÔTÉ SERVEUR (startswith sur le code lieu d'exécution : matche
    # dept "29", communes "29232", CP "29000") → on ramène les marchés de la zone, pas
    # 100 lignes nationales filtrées ensuite.
    safe_deps = [d for d in (departements or []) if d.isdigit() or d in ("2A", "2B")]
    if safe_deps:
        clause = " OR ".join(f'startswith(lieuexecution_code, "{d}")' for d in safe_deps[:6])
        where = f"({where}) AND ({clause})"
    params = {"limit": min(per, 100), "order_by": "-datenotification",
              "where": where, "select": SELECT}
    r = get_with_retry(API, params=params, timeout=14)
    return r.json().get("results", []) or []


def detect_renewals_decp(query: str, departements, criteria: dict, domaines=None) -> dict:
    """Marchés attribués (DECP) dont le contrat arrive bientôt à terme → fenêtre d'attaque.
    Déterministe : fin = date_notification + durée réelle. Aucun LLM."""
    deps = [str(d).strip()[:2] for d in (departements or []) if str(d).strip()]
    try:
        rows = _fetch(query, deps, cpv=(criteria or {}).get("codes_cpv"))
    except Exception as e:
        logger.warning("Radar échéances DECP indisponible : %s", e)
        return {"count": 0, "renewals": [], "errors": [f"DECP indisponible : {e}"], "source": "DECP"}
    if not rows:
        return {"count": 0, "renewals": [], "errors": [], "source": "DECP"}

    today = date.today()
    win_start, win_end = today - timedelta(days=180), today + timedelta(days=550)
    out, seen = [], set()
    # Budget de résolution SIRET→raison sociale par appel (au-delà : repli « SIRET … »).
    # Borné pour ne pas allonger le radar ; le cache LRU absorbe les acheteurs récurrents.
    resolved, RESOLVE_CAP = {}, 30

    def _name_for(aid: str) -> str:
        siren = aid[:9]
        if siren in resolved:
            return resolved[siren]
        if len(resolved) >= RESOLVE_CAP:
            return ""
        nm = _acheteur_name(siren)
        resolved[siren] = nm
        return nm

    for row in rows:
        # Dédup : un marché multi-lots/multi-titulaires apparaît plusieurs fois.
        k = ((row.get("objet") or "").lower()[:80], str(row.get("acheteur_id") or ""))
        if k in seen:
            continue
        seen.add(k)
        notif = _parse(row.get("datenotification"))
        duree = row.get("dureemois")
        if not notif or not isinstance(duree, (int, float)) or duree <= 0:
            continue
        dep = (str(row.get("lieuexecution_code") or "")[:2])
        if deps and dep not in deps:                       # filtre département côté client
            continue
        fin = notif + timedelta(days=int(duree * 30.4))
        renouv = fin - timedelta(days=120)                  # republication ~4 mois avant la fin
        if not (win_start <= renouv <= win_end):
            continue
        acheteur_id = str(row.get("acheteur_id") or "")
        acheteur_nom = _name_for(acheteur_id) if acheteur_id else ""
        acheteur_label = acheteur_nom or (("SIRET " + acheteur_id) if acheteur_id else "Acheteur public")
        r = {"objet": (row.get("objet") or "").strip()[:400],
             "acheteur": acheteur_label,
             "dept": dep, "lieu": dep, "date_attribution": str(row.get("datenotification") or "")[:10]}
        score = _score(r, criteria, domaines, renouv, today)
        out.append({
            "idweb": str(row.get("id") or acheteur_id or notif.isoformat()),
            "objet": r["objet"], "acheteur": r["acheteur"], "lieu": dep, "dept": dep,
            "date_attribution": r["date_attribution"],
            "duree_mois": int(duree), "duree_estimee": False,        # durée RÉELLE, pas estimée
            "type_contrat": (row.get("nature") or ""),
            "montant": row.get("montant"),
            "source_plateforme": (row.get("source") or ""),
            "fin_estimee": fin.isoformat(), "renouvellement_estime": renouv.isoformat(),
            "score": score,
            # Lien réel vers l'acheteur (annuaire public des entreprises, gratuit).
            "url": (f"https://annuaire-entreprises.data.gouv.fr/etablissement/{acheteur_id}"
                    if acheteur_id else ""),
        })
    out.sort(key=lambda x: (x["score"], x["renouvellement_estime"]), reverse=True)
    return {"count": len(out), "renewals": out, "errors": [], "source": "DECP"}
