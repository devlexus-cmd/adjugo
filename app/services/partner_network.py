"""
Adjugo — Réseau de partenaires (co-traitance v2, vague 3 « vrai réseau ») : profils,
vérifications publiques, visibilité, historique réel, RGPD, re-vérification bornée.

Invariants (ne jamais les casser) :
  - OPT-IN : un profil n'est visible que s'il a été PUBLIÉ par un admin de l'organisation
    (SIRET à 14 chiffres, entreprise active vérifiée dans SIRENE il y a moins de 30 jours)
    ET VALIDÉ par un administrateur Adjugo (l'identité : le compte représente bien cette
    entreprise). Toute modification du SIRET retire la publication et la validation.
  - AUCUN ORACLE pour un compte non publié : ni compteur filtré, ni « un seul profil par
    SIREN », ni repli SIRENE amputé des membres du réseau.
  - CONFIANCE VÉRIFIABLE : SIRENE, BODACC, DECP, dépôts réels sur Adjugo. Chaque vérification
    est datée ; un échec réseau donne « non vérifié » (None), jamais une absence prouvée.
  - AUCUN profil de démonstration : la colonne is_demo existe (schéma) mais aucun n'est créé,
    et toute requête du réseau les exclut (ainsi que le compte démo).
  - RÉCIPROCITÉ : pour voir l'annuaire et les profils correspondants, il faut avoir publié le
    sien. hidden_from_sirens s'applique DANS LES DEUX SENS.
  - ANONYMAT DES RECHERCHES : un profil ne sait jamais qui l'a cherché (compteur mensuel
    anonyme) ; le journal network.* n'est écrit que sur le tenant du CHERCHEUR.
  - PROCESS UNIQUE : appels HTTP externes bornés (timeout 5 s, 1 essai, 3 en parallèle,
    budget global), caches et plafonds en mémoire (cohérents : un seul worker, sans Redis).
  - 0 LLM.
"""
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, func, or_

logger = logging.getLogger("adjugo")

HTTP_TIMEOUT = 5.0             # secondes, par appel externe (SIRENE / BODACC / DECP)
VERIFY_BUDGET_S = 8.0          # budget global d'une vérification (3 appels en parallèle)
VERIFY_COOLDOWN_S = 600        # au plus une vérification toutes les 10 min par profil
PUBLISH_MAX_AGE_DAYS = 30      # vérification SIRENE de moins de 30 jours pour publier
CRON_BATCH = 25                # profils re-vérifiés par exécution du cron
CRON_BUDGET_S = 90.0           # budget temps d'une exécution du cron
MAX_VISIBLE_SCAN = 2000        # borne de lecture des profils publiés par requête
MAX_HIDDEN = 100
MAX_METIERS = 12
MAX_DEPARTEMENTS = 30
MAX_CPV = 20
MAX_REFERENCES = 5

ADMIN_NOTIFY_DAY_CAP = 30      # emails « demande de validation » envoyés à Adjugo par jour
ADMIN_NOTIFY_PROFILE_S = 3600  # au plus un email par profil et par heure
ADMIN_FALLBACK_EMAIL = "contact@adjugo.pro"

VALIDATION_PENDING = "en_attente"
VALIDATION_OK = "validee"
VALIDATION_REFUSED = "refusee"

SIRENE_API = "https://recherche-entreprises.api.gouv.fr/search"
SOURCE_SIRENE = "SIRENE (recherche-entreprises.api.gouv.fr)"
ROLES = ("cotraitant", "sous_traitant", "mandataire")
DISPONIBILITES = ("disponible", "limitee", "complet")
NETWORK_SOURCE = "reseau_adjugo"


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _period(now: Optional[datetime] = None) -> str:
    return (now or utcnow_naive()).strftime("%Y-%m")


def clean_siren(v) -> str:
    digits = re.sub(r"\D", "", str(v or ""))
    return digits[:9] if len(digits) in (9, 14) else ""


def clean_siret(v) -> str:
    digits = re.sub(r"\D", "", str(v or ""))
    return digits if len(digits) == 14 else ""


# ── HTTP (un seul point d'entrée, simulé dans les tests) ──────────────────────────────

def _http_get(url: str, params: dict, timeout: float = HTTP_TIMEOUT) -> dict:
    """GET JSON, UN essai, timeout court. Lève en cas d'erreur (réseau, HTTP ≠ 200, JSON)."""
    import httpx
    r = httpx.get(url, params=params, timeout=timeout, headers={"User-Agent": "Adjugo/1.0 (+https://adjugo.fr)"})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("réponse inattendue")
    return data


# ── Vérifications publiques (tri-état : ok / introuvable / erreur) ────────────────────

def fetch_sirene(siren: str, now: Optional[datetime] = None) -> dict:
    """État de l'entreprise dans SIRENE. statut ∈ ok | introuvable | erreur | siren_invalide.
    etat = 'actif' | 'cesse' | None. 'cesse' UNIQUEMENT si l'API répond (200) pour CE SIREN
    exact avec etat_administratif = 'C' (seul cas qui autorise une dépublication)."""
    now = now or utcnow_naive()
    out = {"etat": None, "date_creation": None, "categorie": None, "est_rge": None,
           "est_qualiopi": None, "est_personne_physique": None,
           "checked_at": now.isoformat(timespec="seconds"), "source": SOURCE_SIRENE, "statut": "erreur"}
    siren = clean_siren(siren)
    if not siren:
        out["statut"] = "siren_invalide"
        return out
    try:
        data = _http_get(SIRENE_API, {"q": siren, "per_page": 1, "page": 1})
    except Exception as e:
        logger.info("SIRENE indisponible pour %s : %s", siren, type(e).__name__)
        return out
    results = data.get("results") or []
    top = results[0] if results and isinstance(results[0], dict) else None
    if not top or re.sub(r"\D", "", str(top.get("siren") or "")) != siren:
        out["statut"] = "introuvable"
        return out
    etat_ul = str(top.get("etat_administratif") or "").upper()
    siege = top.get("siege") if isinstance(top.get("siege"), dict) else {}
    comp = top.get("complements") if isinstance(top.get("complements"), dict) else {}
    out.update({
        "statut": "ok",
        "etat": "actif" if etat_ul == "A" else ("cesse" if etat_ul == "C" else None),
        "date_creation": top.get("date_creation") or None,
        "categorie": top.get("categorie_entreprise") or None,
        "est_rge": comp.get("est_rge") if isinstance(comp.get("est_rge"), bool) else None,
        "est_qualiopi": comp.get("est_qualiopi") if isinstance(comp.get("est_qualiopi"), bool) else None,
        "est_personne_physique": str(top.get("nature_juridique") or "") == "1000",
        "nom": (top.get("nom_complet") or top.get("nom_raison_sociale") or "")[:255],
        "siret_siege": str(siege.get("siret") or ""),
        "code_postal": str(siege.get("code_postal") or "")[:10],
        "ville": str(siege.get("libelle_commune") or "")[:120],
        "naf": str(top.get("activite_principale") or "")[:10],
    })
    return out


def fetch_bodacc(siren: str, now: Optional[datetime] = None) -> dict:
    """Dernier avis de procédure collective publié au BODACC pour ce SIREN.
    found = True (avis trouvé) | False (AUCUN avis trouvé : « aucun avis trouvé au JJ/MM »,
    jamais « aucune procédure ») | None (non vérifié : service indisponible)."""
    from app.sourcing.sources.bodacc import BODACC
    now = now or utcnow_naive()
    out = {"found": None, "ongoing": None, "nature": None, "date": None, "url": None,
           "checked_at": now.isoformat(timespec="seconds"), "statut": "erreur"}
    siren = clean_siren(siren)
    if not siren:
        out["statut"] = "siren_invalide"
        return out
    params = {"where": f'familleavis="collective" and registre like "{siren}"',
              "order_by": "dateparution desc", "limit": 1}
    try:
        data = _http_get(BODACC, params)
    except Exception as e:
        logger.info("BODACC indisponible pour %s : %s", siren, type(e).__name__)
        return out
    results = data.get("results") or []
    out["statut"] = "ok"
    if not results:
        out.update({"found": False, "ongoing": False})
        return out
    rec = results[0] if isinstance(results[0], dict) else {}
    jug = rec.get("jugement")
    if isinstance(jug, str):
        try:
            import json
            jug = json.loads(jug)
        except Exception:
            jug = {}
    jug = jug if isinstance(jug, dict) else {}
    famille = str(jug.get("famille") or rec.get("typeavis_lib") or "").strip()
    nature = str(jug.get("nature") or famille or "Procédure collective").strip()
    closed = "clôture" in famille.lower() or "clôture" in nature.lower()
    out.update({"found": True, "ongoing": not closed, "nature": nature[:160],
                "date": str(jug.get("date") or rec.get("dateparution") or "")[:10] or None,
                "url": rec.get("url_complete") or "https://www.bodacc.fr"})
    return out


def fetch_decp(siren: str, now: Optional[datetime] = None) -> dict:
    """Marchés publics publiés dans DECP avec ce SIREN comme titulaire. count = nombre de
    marchés DISTINCTS lus (≤ 100 lignes) → « au moins N » ; None = non vérifié."""
    from app.services.decp import API
    now = now or utcnow_naive()
    out = {"count": None, "last_date": None, "checked_at": now.isoformat(timespec="seconds"), "statut": "erreur"}
    siren = clean_siren(siren)
    if not siren:
        out["statut"] = "siren_invalide"
        return out
    params = {"limit": 100, "select": "objet,datenotification,acheteur_id",
              "where": f'startswith(titulaire_id_1, "{siren}")', "order_by": "-datenotification"}
    try:
        data = _http_get(API, params)
    except Exception as e:
        logger.info("DECP indisponible pour %s : %s", siren, type(e).__name__)
        return out
    rows = [r for r in (data.get("results") or []) if isinstance(r, dict)]
    # Un marché multi-lots apparaît plusieurs fois : on dédoublonne → borne INFÉRIEURE honnête.
    keys = {((r.get("objet") or "").strip().lower()[:80], str(r.get("acheteur_id") or ""),
             str(r.get("datenotification") or "")[:10]) for r in rows}
    out.update({"statut": "ok", "count": len(keys),
                "last_date": (str(rows[0].get("datenotification") or "")[:10] or None) if rows else None})
    return out


def run_checks(siren: str, now: Optional[datetime] = None) -> dict:
    """Les 3 vérifications EN PARALLÈLE, budget global VERIFY_BUDGET_S. Un appel qui dépasse
    le budget compte comme une erreur (non vérifié). Ne lève jamais."""
    now = now or utcnow_naive()
    fns = {"sirene": fetch_sirene, "bodacc": fetch_bodacc, "decp": fetch_decp}
    res = {}
    ex = ThreadPoolExecutor(max_workers=3)
    try:
        futs = {ex.submit(fn, siren, now): key for key, fn in fns.items()}
        done, _pending = wait(futs, timeout=VERIFY_BUDGET_S)
        for fut, key in futs.items():
            if fut in done:
                try:
                    res[key] = fut.result()
                    continue
                except Exception:
                    pass
            res[key] = {"statut": "erreur", "checked_at": now.isoformat(timespec="seconds")}
    finally:
        ex.shutdown(wait=False)    # jamais d'attente au-delà du budget (timeouts HTTP courts)
    return res


def apply_checks(profile, res: dict, now: Optional[datetime] = None) -> dict:
    """Applique les résultats au profil. Un résultat en ERREUR (ou introuvable) ne remplace
    JAMAIS une vérification précédente réussie (elle reste affichée avec SA date) ; sans
    précédent, le champ reste None (« non vérifié »). Renvoie un résumé par vérification."""
    from app.services.partner_matching import bodacc_label, decp_label, sirene_label, jjmm
    now = now or utcnow_naive()
    summary = {}
    s = res.get("sirene") or {}
    if s.get("statut") == "ok":
        profile.verified_sirene = {k: s.get(k) for k in (
            "etat", "date_creation", "categorie", "est_rge", "est_qualiopi", "est_personne_physique",
            "checked_at", "source", "nom", "code_postal", "ville", "naf")}
        profile.verified_at = now
        # Identité OFFICIELLE (le nom affiché est celui du registre, jamais un texte libre).
        if s.get("nom"):
            profile.name = s["nom"][:255]
        if s.get("code_postal") and not (profile.postal_code or "").strip():
            profile.postal_code = s["code_postal"][:10]
        if s.get("ville") and not (profile.city or "").strip():
            profile.city = s["ville"][:120]
        if not (profile.departement or "").strip() and profile.postal_code:
            from app.services.dce_scoring import _dept
            profile.departement = (_dept(profile.postal_code) or "")[:3]
        summary["sirene"] = {"statut": "ok", "label": sirene_label(profile.verified_sirene)}
    else:
        prev = profile.verified_sirene if isinstance(profile.verified_sirene, dict) else None
        msg = {"introuvable": "SIREN introuvable dans SIRENE : vérifiez le SIRET du profil entreprise.",
               "siren_invalide": "SIRET à 14 chiffres manquant dans le profil entreprise."}.get(
            s.get("statut"), "SIRENE momentanément indisponible : réessayez plus tard.")
        if prev and prev.get("checked_at"):
            msg += f" La vérification du {jjmm(prev.get('checked_at'))} est conservée."
        summary["sirene"] = {"statut": s.get("statut") or "erreur", "label": sirene_label(prev), "message": msg}

    for key, attr, label_fn, name in (("bodacc", "verified_bodacc", bodacc_label, "BODACC"),
                                      ("decp", "verified_decp", decp_label, "DECP")):
        r = res.get(key) or {}
        if r.get("statut") == "ok":
            setattr(profile, attr, {k: v for k, v in r.items() if k != "statut"})
            summary[key] = {"statut": "ok", "label": label_fn(getattr(profile, attr))}
        else:
            prev = getattr(profile, attr) if isinstance(getattr(profile, attr), dict) else None
            msg = f"{name} momentanément indisponible : non vérifié."
            if prev and prev.get("checked_at"):
                msg = f"{name} momentanément indisponible : la vérification du {jjmm(prev.get('checked_at'))} est conservée."
            summary[key] = {"statut": r.get("statut") or "erreur", "label": label_fn(prev), "message": msg}
    return summary


def verification_age_days(profile, now: Optional[datetime] = None) -> Optional[int]:
    if not profile.verified_at:
        return None
    now = now or utcnow_naive()
    va = profile.verified_at
    if va.tzinfo is not None:
        va = va.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0, (now - va).days)


# ── Profil : dict, visibilité, contexte du chercheur ──────────────────────────────────

def new_public_id() -> str:
    return uuid.uuid4().hex


def profile_dict(p) -> dict:
    """Profil → dict consommé par le service PUR partner_matching (aucun champ privé ne sort
    de partner_matching.public_card)."""
    return {
        "public_id": p.public_id, "name": p.name or "", "siren": p.siren or "", "siret": p.siret or "",
        "postal_code": p.postal_code or "", "city": p.city or "", "departement": p.departement or "",
        "metiers": list(p.metiers or []), "codes_cpv": list(p.codes_cpv or []),
        "departements": list(p.departements or []), "roles_acceptes": list(p.roles_acceptes or []),
        "disponibilite": p.disponibilite or "", "dispo_jusqua": p.dispo_jusqua,
        "lot_max_eur": p.lot_max_eur, "presentation": p.presentation or "",
        "references_publiques": list(p.references_publiques or []), "declared_at": p.declared_at,
        "verified_sirene": p.verified_sirene, "verified_bodacc": p.verified_bodacc,
        "verified_decp": p.verified_decp, "verified_at": p.verified_at,
        "groupements_deposes": int(p.groupements_deposes or 0),
        "groupements_checked_at": p.groupements_checked_at,
        # Date de la validation de l'identité par Adjugo POUR LE SIREN ACTUEL (sinon None).
        "identite_validee_le": p.validated_at if identity_validated(p) else None,
    }


def _demo_user_ids(db) -> set:
    from app.models import User
    from app.services.demo_search import DEMO_EMAIL
    return {r[0] for r in db.query(User.id).filter(func.lower(User.email) == DEMO_EMAIL).all()}


def org_member_ids(db, user_id: int) -> list:
    from app.models import User
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return [user_id]
    if not u.org_id:
        return [u.id]
    return [r[0] for r in db.query(User.id).filter(User.org_id == u.org_id).all()] or [u.id]


def own_profile(db, owner_id: int):
    from app.models import PartnerProfile
    return db.query(PartnerProfile).filter(PartnerProfile.user_id == owner_id).first()


def searcher_context(db, user) -> dict:
    """Qui cherche : organisation, profil, SIREN, publié ?, liste de masquage."""
    from app.core.org import data_owner_id, member_ids
    from app.models import Company
    from app.services.demo_search import is_demo
    owner = data_owner_id(user, db)
    prof = own_profile(db, owner)
    siren = (prof.siren if prof and prof.siren else "") or ""
    if not siren:
        comp = db.query(Company).filter(Company.user_id == owner).first()
        siren = clean_siren(comp.siret if comp else "")
    demo = is_demo(user)
    published = bool(prof and prof.visible and not prof.is_demo and not demo)
    return {"owner_id": owner, "member_ids": member_ids(user, db), "profile": prof,
            "siren": siren, "published": published, "is_demo": demo,
            "hidden": set(prof.hidden_from_sirens or []) if prof else set()}


def hidden_pair(ctx: dict, p) -> bool:
    """Masquage DANS LES DEUX SENS : le profil me masque, ou je le masque."""
    mine = ctx.get("siren") or ""
    theirs = p.siren or ""
    if mine and mine in set(p.hidden_from_sirens or []):
        return True
    if theirs and theirs in (ctx.get("hidden") or set()):
        return True
    return False


def visible_profiles(db, ctx: dict, metiers=None, departement: str = "") -> list:
    """Profils PUBLIÉS visibles par ce chercheur : jamais démo, jamais le sien (ni un profil
    du même SIREN), jamais une paire masquée. Borné (MAX_VISIBLE_SCAN), ordre stable.
    `metiers` (clés) et `departement` (code normalisé : 29, 2A, 974) : filtres faits EN BASE
    avant la borne, pour que la borne ne coupe pas les profils utiles — métier = texte JSON
    contenant la clé ; département = zones déclarées (texte JSON contenant le code) OU
    département du siège, comme le filtre exact appliqué ensuite par l'annuaire. Borne
    atteinte → ctx["tronque"] = True (signalé à l'écran, jamais un résultat amputé en silence)."""
    from sqlalchemy import String, cast
    from app.models import PartnerProfile
    excluded = set(ctx.get("member_ids") or []) | {ctx.get("owner_id")} | _demo_user_ids(db)
    q = db.query(PartnerProfile).filter(
        PartnerProfile.visible.is_(True), PartnerProfile.is_demo.isnot(True),
        ~PartnerProfile.user_id.in_([i for i in excluded if i is not None] or [0]),
    )
    keys = sorted({str(m) for m in (metiers or []) if m and re.fullmatch(r"[a-z0-9_]{1,40}", str(m))})
    if keys:
        q = q.filter(or_(*[cast(PartnerProfile.metiers, String).like(f'%"{k}"%') for k in keys]))
    dep = str(departement or "").strip().upper()
    if dep and re.fullmatch(r"\d{2,3}|2[AB]", dep):
        q = q.filter(or_(cast(PartnerProfile.departements, String).like(f'%"{dep}"%'),
                         PartnerProfile.departement == dep))
    else:
        dep = ""
    rows = q.order_by(PartnerProfile.id.asc()).limit(MAX_VISIBLE_SCAN).all()
    if len(rows) >= MAX_VISIBLE_SCAN:
        ctx["tronque"] = True
        logger.warning("réseau : borne de %s profils atteinte (filtre métier : %s, département : %s)",
                       MAX_VISIBLE_SCAN, keys or "aucun", dep or "aucun")
    mine = ctx.get("siren") or ""
    return [p for p in rows if not (mine and p.siren == mine) and not hidden_pair(ctx, p)]


TRONQUE_MSG = ("Le réseau compte plus de profils que ce qu'une recherche peut parcourir : "
               "précisez le métier ou le département pour voir tous les partenaires correspondants.")


def find_visible(db, ctx: dict, public_id: str):
    """Un profil précis, SEULEMENT s'il est visible pour ce chercheur (sinon None → 404)."""
    from app.models import PartnerProfile
    pid = str(public_id or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", pid):
        return None
    p = db.query(PartnerProfile).filter(PartnerProfile.public_id == pid).first()
    if not p or not p.visible or p.is_demo:
        return None
    excluded = set(ctx.get("member_ids") or []) | {ctx.get("owner_id")} | _demo_user_ids(db)
    if p.user_id in excluded:
        return None
    if ctx.get("siren") and p.siren == ctx["siren"]:
        return None
    if hidden_pair(ctx, p):
        return None
    return p


def find_visible_by_siren(db, ctx: dict, siren: str):
    """Le profil PUBLIÉ d'un SIREN précis (au plus un : index unique partiel), SEULEMENT s'il
    est visible pour ce chercheur (mêmes règles que find_visible), sinon None. Requête ciblée :
    jamais coupée par la borne de lecture de visible_profiles."""
    from app.models import PartnerProfile
    s = clean_siren(siren)
    if not s:
        return None
    p = db.query(PartnerProfile).filter(PartnerProfile.siren == s, PartnerProfile.visible.is_(True),
                                        PartnerProfile.is_demo.isnot(True)).order_by(PartnerProfile.id.asc()).first()
    return find_visible(db, ctx, p.public_id) if p else None


TRONQUE_POOL_MSG = ("Réseau Adjugo : plus de profils de ce métier que ce qu'une recherche peut parcourir, "
                    "certains partenaires du réseau ne sont pas proposés ici.")


# ── Compteur ANONYME d'apparitions ────────────────────────────────────────────────────
# Dédoublonnage en mémoire (process unique) : un même chercheur ne compte qu'une fois par
# profil et par mois (un redémarrage peut recompter une fois — limite assumée). AUCUNE trace
# de QUI a cherché n'est écrite côté profil.
_APPEAR_SEEN: dict = {}
_APPEAR_LOCK = threading.Lock()


def count_appearances(db, searcher_owner_id: int, profile_ids) -> int:
    from app.models import PartnerProfile
    period = _period()
    fresh = []
    with _APPEAR_LOCK:
        if len(_APPEAR_SEEN) > 50000:
            _APPEAR_SEEN.clear()
        for pid in sorted({int(i) for i in (profile_ids or []) if i is not None}):
            key = (searcher_owner_id, pid, period)
            if key in _APPEAR_SEEN:
                continue
            _APPEAR_SEEN[key] = True
            fresh.append(pid)
    if not fresh:
        return 0
    try:
        db.query(PartnerProfile).filter(PartnerProfile.id.in_(fresh)).update({
            PartnerProfile.appearances_count: case(
                (PartnerProfile.appearances_period == period,
                 func.coalesce(PartnerProfile.appearances_count, 0) + 1), else_=1),
            PartnerProfile.appearances_period: period,
            PartnerProfile.updated_at: PartnerProfile.updated_at,     # pas une « mise à jour » du profil
        }, synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("compteur d'apparitions non mis à jour : %s", e)
        return 0
    return len(fresh)


def appearances_this_month(p) -> int:
    return int(p.appearances_count or 0) if (p.appearances_period or "") == _period() else 0


# ── Plafonds par organisation (en plus du limiter par IP) ─────────────────────────────
_QUOTA: dict = {}
_QUOTA_LOCK = threading.Lock()


def owner_quota_ok(owner_id: int, kind: str, cap: int) -> bool:
    """Plafond quotidien par organisation (le limiter slowapi est par IP : une org derrière
    un NAT ou un scraper multi-IP le contourneraient)."""
    day = utcnow_naive().strftime("%Y-%m-%d")
    key = (owner_id, kind, day)
    with _QUOTA_LOCK:
        if len(_QUOTA) > 20000:
            _QUOTA.clear()
        n = _QUOTA.get(key, 0)
        if n >= cap:
            return False
        _QUOTA[key] = n + 1
        return True


# ── Historique RÉEL (COUNT) et groupements déposés ────────────────────────────────────

_DEPOSE_STATUSES = ("envoye", "gagne", "perdu")


def _status_values():
    from app.models import ProjectStatus
    return [ProjectStatus.envoye, ProjectStatus.gagne, ProjectStatus.perdu]


def _counts_for(db, invite_filter, project_filter) -> dict:
    """COUNT réels : invitations actives, parts soumises, marchés déposés / gagnés / perdus
    (marché compté s'il porte au moins une part SOUMISE d'un membre actif). Aucun identifiant,
    aucun nom, aucun email ne sort d'ici."""
    from app.models import Project, ProjectContribution, ProjectInvite, ProjectStatus
    from app.services.groupement_members import active_invite_filter
    base = db.query(ProjectInvite).join(Project, Project.id == ProjectInvite.project_id).filter(
        invite_filter, project_filter, active_invite_filter(), Project.deleted_at.is_(None))
    n_inv = base.count()
    sub = db.query(ProjectInvite.id).join(Project, Project.id == ProjectInvite.project_id).join(
        ProjectContribution, ProjectContribution.invite_id == ProjectInvite.id).filter(
        invite_filter, project_filter, active_invite_filter(), Project.deleted_at.is_(None),
        ProjectContribution.status == "submitted")
    n_sub = sub.count()

    def _n_projects(statuses):
        return db.query(func.count(func.distinct(Project.id))).select_from(ProjectInvite).join(
            Project, Project.id == ProjectInvite.project_id).join(
            ProjectContribution, ProjectContribution.invite_id == ProjectInvite.id).filter(
            invite_filter, project_filter, active_invite_filter(), Project.deleted_at.is_(None),
            ProjectContribution.status == "submitted", Project.status.in_(statuses)).scalar() or 0

    return {"invitations_actives": int(n_inv), "parts_soumises": int(n_sub),
            "marches_deposes": int(_n_projects(_status_values())),
            "gagnes": int(_n_projects([ProjectStatus.gagne])),
            "perdus": int(_n_projects([ProjectStatus.perdu]))}


def historique(db, org_ids: list, profile=None) -> dict:
    """Dans les deux sens : comme chef de file (marchés de l'organisation) et comme partenaire
    (invitations reçues via le réseau ou réclamées par un compte de l'organisation)."""
    from app.models import Project, ProjectInvite
    org_ids = list(org_ids or []) or [0]
    lead = _counts_for(db, ProjectInvite.id.isnot(None), Project.user_id.in_(org_ids))
    conds = [ProjectInvite.accepted_by_user_id.in_(org_ids)]
    if profile is not None:
        conds.append(ProjectInvite.partner_profile_id == profile.id)
    member = _counts_for(db, or_(*conds), ~Project.user_id.in_(org_ids))
    return {"comme_chef_de_file": {"invitations_actives": lead["invitations_actives"],
                                   "parts_recues": lead["parts_soumises"],
                                   "marches_deposes": lead["marches_deposes"],
                                   "gagnes": lead["gagnes"], "perdus": lead["perdus"]},
            "comme_partenaire": member}


def historique_avec(db, my_org_ids: list, my_profile, other) -> dict:
    """COUNT entre MON organisation et CELLE d'un profil du réseau, dans les deux sens."""
    from app.models import Project, ProjectInvite
    other_org = org_member_ids(db, other.user_id)
    mine = list(my_org_ids or []) or [0]
    # Moi chef de file, eux membres.
    a = _counts_for(db, or_(ProjectInvite.partner_profile_id == other.id,
                            ProjectInvite.accepted_by_user_id.in_(other_org)),
                    Project.user_id.in_(mine))
    # Eux chef de file, moi membre.
    conds = [ProjectInvite.accepted_by_user_id.in_(mine)]
    if my_profile is not None:
        conds.append(ProjectInvite.partner_profile_id == my_profile.id)
    b = _counts_for(db, or_(*conds), Project.user_id.in_(other_org))
    return {k: int(a[k]) + int(b[k]) for k in a}


def count_groupements(db, org_ids: list, profile_id: Optional[int] = None, own_siren: str = "") -> tuple:
    """(nombre, date du plus récent) de marchés DISTINCTS au statut envoyé / gagné / perdu
    portant au moins une part soumise d'un membre actif, où l'organisation est :
      - chef de file AVEC une AUTRE organisation : invitation acceptée par un compte hors de
        l'organisation, ou adressée au profil réseau d'une autre organisation ;
      - ou membre du groupement d'une AUTRE organisation (invitation réseau de son profil, ou
        lien réclamé par un de ses comptes).
    L'autre entreprise doit en plus être DISTINCTE de façon vérifiable, sinon un compte relais
    (2e compte gratuit, sans SIRET) suffisait à fabriquer le badge :
      - chef de file : la part soumise porte un SIREN à 9 chiffres différent du sien, ou
        l'invitation vise (ou a été acceptée par) une organisation dont l'identité est validée
        par Adjugo sous un autre SIREN ;
      - membre : le chef de file a un SIRET à 9 chiffres différent du sien dans son profil
        entreprise, ou une identité validée par Adjugo sous un autre SIREN.
    Le statut « déposé » reste DÉCLARATIF (renseigné par le chef de file) : le badge le dit."""
    from app.models import Company, PartnerProfile, Project, ProjectContribution, ProjectInvite
    from app.services.groupement_members import active_invite_filter
    org = list(org_ids or []) or [0]
    others_profiles = db.query(PartnerProfile.id).filter(~PartnerProfile.user_id.in_(org))
    lead_side = and_(Project.user_id.in_(org), or_(
        and_(ProjectInvite.accepted_by_user_id.isnot(None), ~ProjectInvite.accepted_by_user_id.in_(org)),
        ProjectInvite.partner_profile_id.in_(others_profiles)))
    member_conds = [ProjectInvite.accepted_by_user_id.in_(org)]
    if profile_id is not None:
        member_conds.append(ProjectInvite.partner_profile_id == profile_id)
    member_side = and_(~Project.user_id.in_(org), or_(*member_conds))
    rows = db.query(Project.id, Project.updated_at, Project.user_id, ProjectContribution.siret,
                    ProjectInvite.accepted_by_user_id, ProjectInvite.partner_profile_id).select_from(
        ProjectInvite).join(Project, Project.id == ProjectInvite.project_id).join(
        ProjectContribution, ProjectContribution.invite_id == ProjectInvite.id).filter(
        active_invite_filter(), Project.deleted_at.is_(None), ProjectContribution.status == "submitted",
        Project.status.in_(_status_values()), or_(lead_side, member_side)).all()

    def _company_siren(uids) -> str:
        for (siret,) in db.query(Company.siret).filter(Company.user_id.in_(list(uids) or [0])).all():
            if clean_siren(siret):
                return clean_siren(siret)
        return ""

    mine = clean_siren(own_siren) or _company_siren(org)
    orgs: dict = {}
    validated: dict = {}

    def _org_of(uid) -> tuple:
        if uid not in orgs:
            orgs[uid] = tuple(sorted(org_member_ids(db, uid)))
        return orgs[uid]

    def _validated_elsewhere(uids: tuple) -> bool:
        """Organisation dont l'identité est validée par Adjugo sous un SIREN autre que le sien."""
        if uids not in validated:
            ps = db.query(PartnerProfile).filter(PartnerProfile.user_id.in_(list(uids) or [0])).all()
            validated[uids] = any(identity_validated(x) and x.siren != mine for x in ps)
        return validated[uids]

    kept = {}
    for pid, upd, lead_uid, part_siret, acc_uid, prof_id in rows:
        if lead_uid in org:
            s = clean_siren(part_siret)
            ok = bool(s and s != mine)
            if not ok and acc_uid is not None and acc_uid not in org:
                ok = _validated_elsewhere(_org_of(acc_uid))
            if not ok and prof_id is not None:
                prof = db.query(PartnerProfile).filter(PartnerProfile.id == prof_id).first()
                ok = bool(prof is not None and prof.user_id not in org
                          and _validated_elsewhere(_org_of(prof.user_id)))
        else:
            lead_org = _org_of(lead_uid)
            s = _company_siren(lead_org)
            ok = bool(s and s != mine) or _validated_elsewhere(lead_org)
        if ok:
            kept[pid] = upd
    dates = [d for d in kept.values() if d is not None]
    return len(kept), (max(dates) if dates else None)


def recompute_groupements(db, profile) -> int:
    """groupements_deposes = COUNT recalculé (jamais saisi), daté (groupements_checked_at)."""
    n, last = count_groupements(db, org_member_ids(db, profile.user_id), profile.id, profile.siren or "")
    profile.groupements_deposes = n
    profile.last_groupement_at = last
    profile.groupements_checked_at = utcnow_naive()
    return n


# ── Invitation réseau : « a répondu ? » (email masqué, aperçu minimal) ───────────────

def network_invite_responded(inv, db=None) -> bool:
    """Une invitation réseau est « répondue » quand le partenaire l'a acceptée depuis son
    compte (claim), a prouvé son adresse (code) ou a soumis sa part. Décliner n'est PAS une
    acceptation : l'adresse reste masquée."""
    if (getattr(inv, "source", "") or "") != NETWORK_SOURCE:
        return True
    if getattr(inv, "accepted_by_user_id", None) or getattr(inv, "verified_at", None):
        return True
    if db is not None:
        from app.models import ProjectContribution
        c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
        if c and c.status == "submitted":
            return True
    return False


def network_recipient(db, profile) -> str:
    """Adresse du compte qui porte le profil (propriétaire de l'organisation), remplie CÔTÉ
    SERVEUR. '' si le compte n'a pas d'adresse utilisable."""
    from app.models import User
    u = db.query(User).filter(User.id == profile.user_id).first()
    if not u or not u.is_active:
        return ""
    e = (u.email or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) or e.endswith("@invalid"):
        return ""
    return e[:255]


# ── RGPD : effacement / transfert ─────────────────────────────────────────────────────

def scrub_network_invites(db, profile_id: int) -> int:
    """À l'effacement d'un profil : l'adresse du partenaire disparaît des invitations réseau
    (stockées dans le tenant des chefs de file) et le lien vers le profil effacé tombe."""
    from app.models import ProjectInvite
    n = db.query(ProjectInvite).filter(ProjectInvite.partner_profile_id == profile_id).update(
        {ProjectInvite.recipient: "", ProjectInvite.verified_email: "",
         ProjectInvite.partner_profile_id: None}, synchronize_session=False)
    return int(n or 0)


def erase_profile(db, profile) -> None:
    scrub_network_invites(db, profile.id)
    db.delete(profile)
    db.flush()


def erase_profiles_of(db, user_id: int) -> int:
    """Effacement du compte (RGPD) : son profil (et l'adresse des invitations qui le visent),
    puis, PAR VALEUR, son adresse dans les invitations RÉSEAU (remplies par Adjugo, jamais
    saisies par un chef de file) : après un transfert de propriété, le profil ne pointe plus
    vers ce compte, mais les invitations auxquelles il a répondu portaient son adresse."""
    from app.models import PartnerProfile, ProjectInvite, User
    rows = db.query(PartnerProfile).filter(PartnerProfile.user_id == user_id).all()
    for p in rows:
        erase_profile(db, p)
    # Traces du compte dans la validation d'autres profils (demandeur, administrateur Adjugo).
    db.query(PartnerProfile).filter(PartnerProfile.validation_requested_by == user_id).update(
        {PartnerProfile.validation_requested_by: None}, synchronize_session=False)
    db.query(PartnerProfile).filter(PartnerProfile.validated_by == user_id).update(
        {PartnerProfile.validated_by: None}, synchronize_session=False)
    u = db.query(User).filter(User.id == user_id).first()
    email = ((u.email if u else "") or "").strip().lower()
    if email:
        db.query(ProjectInvite).filter(ProjectInvite.source == NETWORK_SOURCE,
                                       func.lower(ProjectInvite.recipient) == email).update(
            {ProjectInvite.recipient: ""}, synchronize_session=False)
        db.query(ProjectInvite).filter(ProjectInvite.source == NETWORK_SOURCE,
                                       func.lower(ProjectInvite.verified_email) == email).update(
            {ProjectInvite.verified_email: ""}, synchronize_session=False)
    return len(rows)


def transfer_profile(db, old_owner_id: int, new_owner_id: int) -> None:
    """Transfert de propriété d'organisation : le profil suit le nouveau propriétaire
    (user_id UNIQUE → un éventuel profil personnel du nouveau propriétaire est effacé avant,
    adresses retirées des invitations réseau comprises). Les invitations réseau du profil
    auxquelles l'entreprise n'a pas encore répondu sont réadressées au nouveau propriétaire :
    il peut les accepter, et l'ancienne adresse n'est plus sollicitée (relances comprises)."""
    from app.models import PartnerProfile, ProjectInvite
    if not db.query(PartnerProfile.id).filter(PartnerProfile.user_id == old_owner_id).first():
        return
    erase_profiles_of_profile_only(db, new_owner_id)
    db.query(PartnerProfile).filter(PartnerProfile.user_id == old_owner_id).update(
        {PartnerProfile.user_id: new_owner_id}, synchronize_session=False)
    db.flush()
    p = own_profile(db, new_owner_id)
    if p is None:
        return
    rcpt = network_recipient(db, p)
    for inv in db.query(ProjectInvite).filter(ProjectInvite.partner_profile_id == p.id,
                                              ProjectInvite.source == NETWORK_SOURCE).all():
        if network_invite_responded(inv, db):
            continue
        inv.recipient = rcpt
        inv.verified_email = ""
        inv.otp_hash = ""             # un code envoyé à l'ancienne adresse ne vaut plus
        inv.otp_expires_at = None
    db.flush()


def erase_profiles_of_profile_only(db, user_id: int) -> int:
    """Profil(s) d'un compte effacé(s), SANS toucher aux autres invitations de son adresse
    (transfert : le compte continue d'exister)."""
    from app.models import PartnerProfile
    rows = db.query(PartnerProfile).filter(PartnerProfile.user_id == user_id).all()
    for p in rows:
        erase_profile(db, p)
    return len(rows)


def export_profile(db, user_id: int) -> Optional[dict]:
    p = own_profile(db, user_id)
    if not p:
        return None
    out = {}
    for c in p.__table__.columns:
        if c.name == "validated_by":      # identifiant interne d'un administrateur Adjugo
            continue
        v = getattr(p, c.name)
        out[c.name] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


# ── Identité : SIRET, validation par Adjugo ───────────────────────────────────────────
# La vérification SIRENE prouve que l'entreprise existe et est active, PAS que le compte la
# représente. Décision du fondateur : une publication passe « en attente de validation » et un
# administrateur Adjugo (User.is_admin) la valide ou la refuse. Toute modification du SIRET
# (profil entreprise) retire la publication ET la validation. « Un seul profil publié par
# SIREN » n'est jamais révélé à l'entreprise : le conflit est traité par l'administrateur.

def _reset_validation(p) -> None:
    p.validation_status = ""
    p.validation_siren = ""
    p.validation_requested_at = None
    p.validation_requested_by = None
    p.validated_at = None
    p.validated_by = None
    p.validation_motif = ""


def sync_siret(p, siret: str) -> Optional[str]:
    """Le SIRET du profil suit le profil entreprise (source unique). S'il change :
    vérifications, publication et validation Adjugo remises à zéro. Renvoie un message."""
    siret = clean_siret(siret)
    if (p.siret or "") == siret:
        return None
    was_visible = bool(p.visible)
    was_pending = (p.validation_status or "") == VALIDATION_PENDING
    had = bool(p.siret)
    if had:
        p.verified_sirene = None
        p.verified_bodacc = None
        p.verified_decp = None
        p.verified_at = None
    p.visible = False
    _reset_validation(p)
    p.siret = siret
    p.siren = siret[:9] if siret else ""
    if was_visible:
        return ("Le SIRET de votre profil entreprise a changé : publication retirée. Vérifiez à nouveau "
                "votre entreprise, puis demandez une nouvelle validation à Adjugo.")
    if was_pending:
        return ("Le SIRET de votre profil entreprise a changé : la demande de validation est annulée. "
                "Vérifiez à nouveau votre entreprise, puis renvoyez la demande.")
    if had:
        return "Le SIRET de votre profil entreprise a changé : vérifiez à nouveau votre entreprise."
    return None


def on_company_saved(db, owner_id: int) -> Optional[str]:
    """Appelé après chaque enregistrement du profil entreprise (PUT/POST /api/company) : un
    SIRET modifié retire la publication et exige une nouvelle validation. Ne lève jamais."""
    try:
        from app.models import Company
        from app.services import audit
        p = own_profile(db, owner_id)
        if p is None:
            return None
        comp = db.query(Company).filter(Company.user_id == owner_id).first()
        was_visible = bool(p.visible)
        msg = sync_siret(p, comp.siret if comp else "")
        if msg is None:
            return None
        if comp and comp.name:
            p.name = comp.name[:255]          # le nom officiel était celui de l'ancien SIREN
        db.commit()
        if was_visible:
            audit.record(db, action="network.profile_unpublished", owner_id=owner_id, actor="system",
                         actor_kind="system", target_type="partner_profile", target_id=p.id,
                         detail="SIRET du profil entreprise modifié : nouvelle validation Adjugo requise")
        return msg
    except Exception as e:
        db.rollback()
        logger.warning("synchronisation du SIRET du profil réseau en échec : %s", e)
        return None


def identity_validated(p) -> bool:
    """Identité validée par Adjugo POUR LE SIREN ACTUEL du profil."""
    return bool(p is not None and (p.validation_status or "") == VALIDATION_OK and p.siren
                and (p.validation_siren or "") == p.siren)


def request_validation(p, user_id: int, now: Optional[datetime] = None) -> None:
    p.validation_status = VALIDATION_PENDING
    p.validation_requested_at = now or utcnow_naive()
    p.validation_requested_by = user_id
    p.validation_motif = ""
    p.validated_at = None
    p.validated_by = None
    p.visible = False


def publish_validated(db, p, now: Optional[datetime] = None) -> bool:
    """Rend visible un profil dont l'identité est validée. False si un autre profil du même
    SIREN vient d'être publié (index unique partiel) : rien n'est publié."""
    from sqlalchemy.exc import IntegrityError
    p.visible = True
    p.is_demo = False
    p.published_at = now or utcnow_naive()
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def siren_conflicts(db, p) -> list:
    """Autres profils du même SIREN publiés ou en attente (vue ADMINISTRATEUR uniquement)."""
    from app.models import PartnerProfile
    if not p.siren:
        return []
    return db.query(PartnerProfile).filter(PartnerProfile.siren == p.siren, PartnerProfile.id != p.id).filter(
        or_(PartnerProfile.visible.is_(True), PartnerProfile.validation_status == VALIDATION_PENDING)).order_by(
        PartnerProfile.id.asc()).limit(20).all()


def _account(db, uid) -> Optional[dict]:
    from app.models import User
    if not uid:
        return None
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return None
    return {"nom": u.full_name or "", "email": u.email or "", "email_confirme": bool(u.email_verified),
            "inscrit_le": u.created_at.isoformat() if getattr(u, "created_at", None) else None}


def admin_item(db, p) -> dict:
    """Une demande, vue par l'ADMINISTRATEUR ADJUGO : identité SIRENE, nom et email du compte
    (seul l'administrateur les voit : c'est ce qu'il doit rapprocher), conflits de SIREN."""
    from app.models import Company
    vs = p.verified_sirene if isinstance(p.verified_sirene, dict) else {}
    comp = db.query(Company).filter(Company.user_id == p.user_id).first()
    owner = _account(db, p.user_id)
    req = _account(db, p.validation_requested_by) if p.validation_requested_by not in (None, p.user_id) else None
    conflits = []
    for o in siren_conflicts(db, p):
        acc = _account(db, o.user_id) or {}
        conflits.append({"profile_id": o.public_id, "name": o.name or "",
                         "statut": "publie" if o.visible else "en_attente",
                         "compte_nom": acc.get("nom", ""), "compte_email": acc.get("email", "")})
    siren = p.siren or ""
    return {
        "profile_id": p.public_id, "name": p.name or "", "siren": siren, "siret": p.siret or "",
        "demande_le": p.validation_requested_at.isoformat() if p.validation_requested_at else None,
        "entreprise_declaree": {"nom": (comp.name if comp else "") or "", "siret": (comp.siret if comp else "") or "",
                                "code_postal": (comp.postal_code if comp else "") or "",
                                "ville": (comp.city if comp else "") or ""},
        "sirene": {"nom": vs.get("nom") or "", "etat": vs.get("etat"), "siret_siege": vs.get("siret_siege") or "",
                   "code_postal": vs.get("code_postal") or "", "ville": vs.get("ville") or "",
                   "naf": vs.get("naf") or "", "date_creation": vs.get("date_creation"),
                   "checked_at": vs.get("checked_at"),
                   "lien_annuaire": (f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}"
                                     if re.fullmatch(r"\d{9}", siren) else None)},
        "compte": owner, "demandeur": req, "conflits": conflits,
        "publication": _publication_preview(p),
    }


def _publication_preview(p) -> dict:
    """Ce que l'annuaire affichera si la demande est validée (déclaratif, tel que saisi) :
    l'administrateur valide l'IDENTITÉ, mais voit aussi le texte avant sa première publication."""
    from app.services.partner_matching import trade_labels
    labels = trade_labels()
    refs = []
    for r in (p.references_publiques if isinstance(p.references_publiques, list) else [])[:10]:
        if isinstance(r, dict):
            txt = " — ".join(str(x) for x in (r.get("intitule"), r.get("client"), r.get("annee")) if x not in (None, ""))
            if txt:
                refs.append(txt[:300])
    return {
        "metiers": [labels.get(m, m) for m in (p.metiers if isinstance(p.metiers, list) else []) if m],
        "departements": [str(d) for d in (p.departements if isinstance(p.departements, list) else []) if d],
        "roles": [str(r) for r in (p.roles_acceptes if isinstance(p.roles_acceptes, list) else []) if r],
        "presentation": (p.presentation or "")[:300],
        "references": refs,
    }


def validation_queue(db, limit: int = 200) -> list:
    from app.models import PartnerProfile
    rows = db.query(PartnerProfile).filter(PartnerProfile.validation_status == VALIDATION_PENDING,
                                           PartnerProfile.is_demo.isnot(True)).order_by(
        PartnerProfile.validation_requested_at.asc(), PartnerProfile.id.asc()).limit(
        max(1, min(int(limit), 500))).all()
    return [admin_item(db, p) for p in rows]


# Notification de l'équipe Adjugo (best-effort, jamais bloquante, plafonnée).
_ADMIN_NOTIFY: dict = {"day": "", "n": 0, "last": {}}
_ADMIN_NOTIFY_LOCK = threading.Lock()


def admin_recipients() -> list:
    from app.core.config import get_settings
    raw = get_settings().ADMIN_EMAILS or ""
    out = [e.strip() for e in raw.split(",") if re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", e.strip())]
    return out[:5] or [ADMIN_FALLBACK_EMAIL]


def _send_async(mails: list) -> None:
    """Envoi dans un fil démon (valeurs capturées avant : aucune session de base dans le fil)."""
    if not mails:
        return

    def _run():
        try:
            from app.services import email as _email
            for to, subj, text in mails:
                try:
                    _email.send_email(to, subj, text)
                except Exception:
                    pass
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def notify_admins_validation(p) -> bool:
    """Email « demande de validation » aux administrateurs Adjugo (ADMIN_EMAILS, à défaut
    contact@adjugo.pro). Plafonds : ADMIN_NOTIFY_DAY_CAP par jour, un par profil et par heure.
    Contenu minimal (nom, SIREN) : le reste se lit dans la vue d'administration."""
    day = utcnow_naive().strftime("%Y-%m-%d")
    now = time.time()
    with _ADMIN_NOTIFY_LOCK:
        if _ADMIN_NOTIFY["day"] != day:
            _ADMIN_NOTIFY.update({"day": day, "n": 0, "last": {}})
        last = _ADMIN_NOTIFY["last"].get(p.id)
        if _ADMIN_NOTIFY["n"] >= ADMIN_NOTIFY_DAY_CAP or (last and now - last < ADMIN_NOTIFY_PROFILE_S):
            return False
        _ADMIN_NOTIFY["n"] += 1
        _ADMIN_NOTIFY["last"][p.id] = now
    # Nom saisi par l'entreprise : une ligne, sans caractère de contrôle (un saut de ligne dans
    # l'objet faisait échouer l'envoi SMTP, et l'email ne partait pas).
    nom = re.sub(r"[\x00-\x1f\x7f]+", " ", p.name or "").strip()
    subj = f"Réseau Adjugo : profil à valider — {(nom or 'entreprise')[:60]}"
    text = ("Bonjour,\n\nUne entreprise demande la publication de son profil partenaire sur le réseau Adjugo.\n\n"
            f"Nom : {nom[:255] or 'non renseigné'}\nSIREN : {p.siren or 'non renseigné'}\n\n"
            "Vérifiez que le compte représente bien cette entreprise, puis validez ou refusez la demande "
            "dans Adjugo > Administration > Profils du réseau à valider.\n\n— Adjugo")
    _send_async([(to, subj, text) for to in admin_recipients()])
    return True


# ── Suggestion d'interface (boucle de croissance, AUCUN email) ────────────────────────

SUGGESTION = {
    "code": "publier_profil_reseau",
    "titre": "Faites-vous trouver pour des groupements",
    "message": ("Publiez votre profil partenaire : les entreprises qui cherchent un partenaire pour "
                "un marché pourront vous trouver et vous inviter. Gratuit, vous choisissez ce qui est "
                "visible et pouvez le retirer à tout moment."),
    "cible": "reseau.profil",
}


def suggest_profile(db, user) -> Optional[dict]:
    """Simple suggestion d'interface (jamais d'email) si l'organisation n'a pas encore de
    profil publié. None pour le compte démo."""
    try:
        from app.core.org import data_owner_id
        from app.services.demo_search import is_demo
        if is_demo(user):
            return None
        p = own_profile(db, data_owner_id(user, db))
        if p and (p.visible or (p.validation_status or "") == VALIDATION_PENDING):
            return None
        return dict(SUGGESTION)
    except Exception:
        return None


# ── Cron : re-vérification bornée ─────────────────────────────────────────────────────

def run_partner_network(db, limit: int = CRON_BATCH, budget_s: float = CRON_BUDGET_S) -> dict:
    """Re-vérifie les profils PUBLIÉS les plus anciennement vérifiés (au plus `limit`, budget
    temps borné). Dépublication UNIQUEMENT sur une réponse positive « cessé » de SIRENE pour
    le SIREN exact — JAMAIS sur une erreur réseau, un SIREN introuvable ou un avis BODACC."""
    from app.models import PartnerProfile
    from app.services import audit
    t0 = time.monotonic()
    # Tri sur la dernière fois qu'Adjugo a REGARDÉ le profil : tentative du cron ou vérification
    # lancée par l'entreprise (last_check_at, à défaut verified_at), jamais regardé d'abord. Un
    # profil que SIRENE ne confirme pas ne garde donc plus la tête de file chaque semaine, et un
    # profil tout juste vérifié ne passe pas devant un profil vérifié il y a des mois.
    seen_at = func.coalesce(PartnerProfile.last_check_at, PartnerProfile.verified_at)
    rows = db.query(PartnerProfile).filter(
        PartnerProfile.visible.is_(True), PartnerProfile.is_demo.isnot(True),
    ).order_by(seen_at.is_(None).desc(), seen_at.asc(),
               PartnerProfile.id.asc()).limit(max(0, min(int(limit), CRON_BATCH))).all()
    stats = {"checked": 0, "sirene_ok": 0, "errors": 0, "unpublished": 0, "skipped_budget": 0}
    for p in rows:
        if time.monotonic() - t0 > budget_s:
            stats["skipped_budget"] += 1
            continue
        now = utcnow_naive()
        try:
            p.last_check_at = now
            res = run_checks(p.siren, now)
            apply_checks(p, res, now)
            stats["checked"] += 1
            s = res.get("sirene") or {}
            if s.get("statut") == "ok":
                stats["sirene_ok"] += 1
            else:
                stats["errors"] += 1
            if s.get("statut") == "ok" and s.get("etat") == "cesse":
                p.visible = False
                stats["unpublished"] += 1
            recompute_groupements(db, p)
            db.commit()
            if s.get("statut") == "ok" and s.get("etat") == "cesse":
                audit.record(db, action="network.profile_unpublished", owner_id=p.user_id,
                             actor="system", actor_kind="system", target_type="partner_profile",
                             target_id=p.id, detail="SIRENE indique que l'entreprise a cessé son activité")
        except Exception as e:
            db.rollback()
            stats["errors"] += 1
            logger.warning("re-vérification du profil réseau %s en échec : %s", p.id, e)
            try:          # la tentative compte quand même (sinon ce profil reste en tête)
                db.query(PartnerProfile).filter(PartnerProfile.id == p.id).update(
                    {PartnerProfile.last_check_at: now}, synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
    return stats
