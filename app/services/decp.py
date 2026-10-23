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
import re
from datetime import date, timedelta
from functools import lru_cache

from app.sourcing.http import safe_terms, get_with_retry
from app.services.renewal import _score, _parse  # scoring + parsing partagés

logger = logging.getLogger("adjugo")


class DecpIndisponible(Exception):
    """La DECP n'a pas répondu (ou a répondu sans compte lisible) : le résultat est INCONNU, jamais
    « 0 marché » (moteur § 7, règle 5 : jamais d'absence affirmée sans vérification)."""


def code_departement(code) -> str:
    """Département d'un code de lieu (code du département, code postal ou code commune), sur son code
    COMPLET : deux chiffres en métropole (« 6 » → « 06 », « 29232 » → « 29 »), trois en outre-mer
    (« 97432 » → « 974 », jamais « 97 »), Corse « 2A » / « 2B » inchangée. Un code postal corse
    (« 20110 ») reste « 20 », comme avant : il ne dit pas 2A ou 2B, on ne le devine pas."""
    s = str(code or "").strip().upper()
    if not s:
        return ""
    if s.isdigit() and len(s) == 1:
        return s.zfill(2)
    if s[:2] in ("2A", "2B"):
        return s[:2]
    if s[:2] in ("97", "98") and len(s) >= 3 and s[:3].isdigit():
        return s[:3]
    return s[:2]


def dans_les_departements(code_lieu, departements) -> bool:
    """Le lieu d'exécution DECP est-il dans un des départements voulus ? Même règle que le filtre envoyé
    à la DECP (startswith sur le code lieu) : « 974 » garde 97432 et écarte 97110 ; « 29 » garde 29, 29232
    et 29000. Sans département voulu, tout lieu convient."""
    if not departements:
        return True
    lieu = str(code_lieu or "").strip().upper()
    return any(lieu.startswith(str(d)) for d in departements if str(d))


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
        # cpv peut arriver en CHAÎNE ("45211000") ou en LISTE : sans normalisation, itérer
        # une chaîne parcourait ses CARACTÈRES ("4","5",…) → filtre CPV neutralisé (matche tout).
        # Une chaîne peut porter plusieurs codes (« Ce que je cherche » : « 45211000, 45300000 ») : découpée comme
        # le fait le reste du produit (scoring, réseau) ; avant, seul le premier code était lu (contrôle des bugs).
        cpv_list = re.split(r"[,;\s]+", cpv) if isinstance(cpv, str) else list(cpv)
        codes = [str(c).strip()[:4] for c in cpv_list if str(c).strip()[:4].isdigit()]
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


def _cle_fin_de_contrat(acheteur_id: str, objet_court: str) -> str:
    """Identifiant d'une fin de contrat DECP : le SIRET de l'acheteur et une empreinte courte de l'objet (les 80
    premiers caractères en minuscules, comme le dédoublonnage)."""
    import hashlib
    empreinte = hashlib.sha1(objet_court.encode("utf-8")).hexdigest()[:12]
    return f"{acheteur_id or 'DECP'}-{empreinte}"


def detect_renewals_decp(query: str, departements, criteria: dict, domaines=None) -> dict:
    """Marchés attribués (DECP) dont le contrat arrive bientôt à terme → fenêtre d'attaque.
    Déterministe : fin = date_notification + durée réelle. Aucun LLM."""
    # Outre-mer : code COMPLET (974 ≠ 971) ; la Corse (« 2A ») et la métropole ne changent pas.
    deps = list(dict.fromkeys(code_departement(d) for d in (departements or []) if str(d).strip()))
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
        # Borne HAUTE : un dureemois aberrant (erreur de saisie DECP, ex. 999999999) ferait
        # planter timedelta (OverflowError) et abandonnerait TOUT le radar déterministe → on
        # ignore juste ce row (240 mois = 20 ans, plafond réaliste des marchés publics).
        if not notif or not isinstance(duree, (int, float)) or not (0 < duree <= 240):
            continue
        code_lieu = str(row.get("lieuexecution_code") or "")
        if not dans_les_departements(code_lieu, deps):     # filtre département côté client
            continue
        dep = code_departement(code_lieu)
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
            # Clé d'UNE fin de contrat (carte de l'écran, rond d'attente de « Préparer à plusieurs ») : la clé de
            # dédoublonnage, unique dans la liste. La DECP n'est pas interrogée sur son champ « id » (numéro propre à
            # l'acheteur, réutilisé d'un marché à l'autre) : avant, le repli sur le SIRET de l'acheteur donnait la même
            # clé à tous ses contrats (contrôle des bugs, 22/10).
            "idweb": _cle_fin_de_contrat(acheteur_id, k[0]),
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


def where_titulaire(siren: str) -> str:
    """Clause ODSQL : le SIREN figure comme titulaire 1, 2 OU 3 (rédaction, vague 5, E2 : un marché
    remporté en groupement porte souvent l'entreprise en titulaire 2 ou 3). `siren` : 9 chiffres.

    Le SIREN est RÉDUIT à ses chiffres avant interpolation (comme les départements/CPV filtrés
    ailleurs) : jamais de caractère arbitraire injecté dans la requête ODSQL. Un SIREN vide/illisible
    donne une clause qui ne matche rien (plutôt que de ramener tous les marchés)."""
    s = "".join(ch for ch in str(siren or "") if ch.isdigit())[:9]
    if not s:
        return "titulaire_id_1 is null and titulaire_id_1 is not null"
    return " or ".join(f'startswith(titulaire_id_{i}, "{s}")' for i in (1, 2, 3))


def wins_by_siren(siren: str) -> dict:
    """Marchés publics attribués à une entreprise (via DECP, titulaire 1, 2 ou 3). Signal de capacité
    déterministe et sourcé — « cette entreprise a déjà remporté ce type de marché » (l'attribution ne
    prouve ni l'exécution ni sa qualité). Retourne {count, last_date, domains} (familles CPV
    2 chiffres) quand la DECP a répondu. Une panne lève DecpIndisponible : le compte est alors
    INCONNU (« non vérifié »), jamais un « 0 marché » (lot 1 « Dire juste », point 5)."""
    siren = "".join(ch for ch in str(siren or "") if ch.isdigit())[:9]
    if len(siren) != 9:
        return {"count": 0, "last_date": "", "domains": []}
    try:
        params = {"limit": 20, "select": "codecpv,datenotification",
                  "where": where_titulaire(siren),
                  "order_by": "-datenotification"}
        data = get_with_retry(API, params=params, timeout=8).json()
    except Exception as e:
        # Le numéro n'est pas écrit dans le journal : celui d'un entrepreneur individuel est une donnée personnelle.
        logger.info("DECP wins_by_siren indisponible : %s", type(e).__name__)
        raise DecpIndisponible(type(e).__name__) from e
    if not isinstance(data, dict) or not isinstance(data.get("total_count"), int):
        logger.info("DECP wins_by_siren : réponse sans compte lisible")
        raise DecpIndisponible("réponse sans compte")
    rows = data.get("results", []) or []
    fams = set()
    for row in rows:
        digits = "".join(ch for ch in str(row.get("codecpv") or "") if ch.isdigit())
        if len(digits) >= 2:
            fams.add(digits[:2])
    last = str((rows[0].get("datenotification") if rows else "") or "")[:10]
    return {"count": int(data["total_count"]), "last_date": last, "domains": sorted(fams)}
