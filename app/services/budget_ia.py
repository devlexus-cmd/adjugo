"""
Coût réel de l'IA par compte, garde-fou de l'ESSAI GRATUIT et alerte interne des forfaits payants.

Mesure (tous usages) : chaque appel réussi à l'IA (llm.messages_create : analyses, lecture en deux
temps, questions, atelier, questionnaire, chiffrage, veille, côté acheteur) est relevé ici avec son
coût réel au tarif public du modèle appelé (app/services/tarifs_ia.py). Le relevé est rattaché au
COMPTE DE FACTURATION : le propriétaire de l'organisation, qui porte le forfait (quota._billing_user),
pour le mois en cours, et marqué « essai » si ce compte est en essai gratuit. Un appel mutualisé (la
veille planifiée, faite une fois pour tous les abonnés) est compté à la plateforme (`mutualise()`).
Le relevé est fait en mémoire pendant l'appel (jamais d'écriture en base dans le chemin de l'appel,
qui ne doit ni ralentir ni échouer pour cela), puis écrit en base (table usage_ia) par un fil dédié,
quelques instants plus tard ; les lectures ajoutent ce qui n'est pas encore écrit (process unique).

Garde-fou de l'essai (comptes en essai actif SEULEMENT) : avant de lancer une opération d'IA,
`verifier(user, db, operation, estimation_eur)` compare le coût déjà engagé pendant l'essai, plus une
estimation PRUDENTE de l'opération, au budget de l'essai (TRIAL_AI_BUDGET_EUR, 15 € par défaut) ;
au-delà, refus propre (402) AVANT tout appel et tout débit, avec un message clair et l'invitation à
choisir un forfait. Une opération commencée va toujours au bout : aucun appel n'est jamais coupé en
cours de route (jamais un dossier à moitié lu). Aucun montant n'est jamais montré au client : l'écran
reçoit au plus un état « ok » / « proche » / « atteint ».

Essai terminé sans formule payante : `verifier` refuse aussi (402, code « essai_termine »,
quota.exiger_ia) : toutes les fonctions d'IA sont en pause jusqu'à la souscription d'un forfait.

Forfaits payants (pro, business, et tout forfait autre que « starter ») : AUCUN plafond, aucun
changement de comportement. Seule une ALERTE interne (journal, route /api/admin/usage-ia) signale
une organisation dont le coût IA du mois dépasse PAID_AI_ALERT_RATIO × le prix de son forfait.
"""
import contextvars
import logging
import math
import threading
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger("adjugo")

PLATEFORME = "plateforme"
ACHETEUR_ANONYME = "acheteur:anonyme"
CODE_LIMITE = "essai_limite_usage"
MSG_LIMITE = ("Votre essai gratuit a atteint sa limite d'usage : les fonctions d'IA sont en pause. "
              "Choisissez un forfait (Pro ou Business) pour continuer. Vos marchés, documents et "
              "dossiers restent accessibles.")
MSG_DEPASSE = ("Cette opération dépasserait la limite d'usage de votre essai gratuit. Choisissez un forfait "
               "(Pro ou Business) pour la lancer ; les questions sur vos dossiers restent possibles.")
MSG_PROCHE = ("Votre essai gratuit approche de sa limite d'usage. Pour continuer sans interruption, "
              "choisissez un forfait.")


def _settings():
    return get_settings()


def _f(name, default):
    try:
        v = float(getattr(_settings(), name, default))
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


def budget_essai_eur() -> float:
    return _f("TRIAL_AI_BUDGET_EUR", 15.0)


def _periode(dt=None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m")


# ── Appels mutualisés (veille planifiée) : comptés à la plateforme, jamais à un client ──────
_MUTUALISE = contextvars.ContextVar("adjugo_ia_mutualise", default=None)


class mutualise:
    """`with mutualise("veille amont planifiée"):` — les appels passés dans la portée sont comptés
    à la plateforme (un seul appel sert tous les abonnés) : ni le budget d'un essai ni le coût du
    mois d'une organisation ne les portent."""

    def __init__(self, libelle: str = ""):
        self.libelle = libelle or "appel mutualisé"
        self._token = None

    def __enter__(self):
        self._token = _MUTUALISE.set(self.libelle)
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _MUTUALISE.reset(self._token)
        return False


# ── Relevé en mémoire, écrit en base par un fil dédié ──────────────────────────────────────
_LOCK = threading.Lock()            # protège _ATTENTE et _EN_COURS (courtes sections, sans E/S)
_ECRITURE = threading.Lock()        # une seule écriture en base à la fois (fil dédié ou vider())
_ATTENTE = []                       # relevés pas encore écrits
_EN_COURS = {}                      # lot en cours d'écriture : n° → relevés (comptés tant que non validés)
_EVENT = threading.Event()
_FIL = {"t": None, "lot": 0, "echecs": 0, "dernier_avertissement": 0.0}
_ATTENTE_MAX = 200_000              # borne mémoire (une panne prolongée de la base) : regroupement


def enregistrer_appel(tenant, modele: str, cout_eur: float, tokens_entree: int, tokens_sortie: int) -> None:
    """Chemin de l'appel à l'IA : relevé en mémoire, sans base, sans exception."""
    try:
        e = {"tenant": tenant, "mutualise": _MUTUALISE.get() is not None, "cout": float(cout_eur or 0.0),
             "tin": int(tokens_entree or 0), "tout": int(tokens_sortie or 0), "periode": _periode(),
             "modele": str(modele or "")[:60]}
        with _LOCK:
            if len(_ATTENTE) >= _ATTENTE_MAX:
                _regrouper_attente()
            _ATTENTE.append(e)
        _demarrer_fil()
        _EVENT.set()
    except Exception:       # noqa: BLE001
        pass


def _regrouper_attente() -> None:
    """(Sous _LOCK.) Fusionne les relevés d'un même tenant et d'un même mois : la mémoire reste bornée
    même si la base est indisponible longtemps ; aucun coût n'est perdu."""
    g = {}
    for e in _ATTENTE:
        k = (repr(e["tenant"]), e["mutualise"], e["periode"])
        if k in g:
            x = g[k]
            x["cout"] += e["cout"]
            x["tin"] += e["tin"]
            x["tout"] += e["tout"]
            x["n"] = x.get("n", 1) + e.get("n", 1)
        else:
            g[k] = dict(e)
    _ATTENTE[:] = list(g.values())


def _demarrer_fil() -> None:
    t = _FIL["t"]
    if t is not None and t.is_alive():
        return
    with _LOCK:
        t = _FIL["t"]
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_boucle, name="adjugo-cout-ia", daemon=True)
        _FIL["t"] = t
    t.start()


def _boucle() -> None:
    pause = 0.5
    while True:
        _EVENT.wait(5.0)
        _EVENT.clear()
        try:
            _ecrire(timeout=None)
            pause = 0.5
        except Exception as e:      # noqa: BLE001 — base indisponible : on réessaie plus tard
            _FIL["echecs"] += 1
            now = time.monotonic()
            if now - _FIL["dernier_avertissement"] > 60:
                _FIL["dernier_avertissement"] = now
                logger.warning("Écriture du coût IA en base différée (%s) : %d relevé(s) en attente.",
                               type(e).__name__, len(_ATTENTE))
            time.sleep(pause)
            pause = min(30.0, pause * 2)
            _EVENT.set()


def _ecrire(timeout=None) -> int:
    """Écrit en base tout ce qui attend. Renvoie le nombre de relevés écrits."""
    if timeout is None:
        _ECRITURE.acquire()
    elif not _ECRITURE.acquire(timeout=timeout):
        return 0
    try:
        with _LOCK:
            if not _ATTENTE:
                return 0
            _FIL["lot"] += 1
            n = _FIL["lot"]
            lot = list(_ATTENTE)
            _ATTENTE.clear()
            _EN_COURS[n] = lot
        try:
            alertes = _persister(lot)
        except Exception:
            with _LOCK:
                _EN_COURS.pop(n, None)
                _ATTENTE[:0] = lot          # remis en tête, rien n'est perdu
            raise
        with _LOCK:
            _EN_COURS.pop(n, None)          # retiré APRÈS la validation : jamais compté zéro fois
        for a in alertes:
            _verifier_alerte(*a)
        return len(lot)
    finally:
        _ECRITURE.release()


def vider(timeout: float = 10.0) -> bool:
    """Écrit tout de suite ce qui attend (route d'administration, tests). Vrai si tout est écrit."""
    try:
        _ecrire(timeout=timeout)
    except Exception as e:      # noqa: BLE001
        logger.warning("Écriture du coût IA en base impossible pour l'instant : %s", type(e).__name__)
        _EVENT.set()
    with _LOCK:
        return not _ATTENTE and not _EN_COURS


def _releves_non_ecrits() -> list:
    with _LOCK:
        out = list(_ATTENTE)
        for lot in _EN_COURS.values():
            out.extend(lot)
    return out


# ── Compte de facturation d'un appel ────────────────────────────────────────────────────────

def _plan(user) -> str:
    p = getattr(user, "plan", "starter")
    return p.value if hasattr(p, "value") else str(p or "starter")


def est_payant(user) -> bool:
    """Forfait payant : tout forfait autre que « starter » (pro, business, et tout forfait à venir)."""
    return _plan(user) not in ("starter", "")


def essai_actif(user) -> bool:
    """Compte de facturation en essai gratuit en cours (règle unique : quota.essai_actif)."""
    from app.core.quota import essai_actif as _essai_actif
    return _essai_actif(user)


def _tenant_entier(tenant):
    if isinstance(tenant, bool):
        return None
    if isinstance(tenant, int):
        return tenant
    if isinstance(tenant, str) and tenant.strip().isdigit():
        return int(tenant.strip())
    return None


def _compte(db, tenant, mutualise_: bool = False, cache=None, strict: bool = False) -> dict:
    """{compte, billing_user_id, org_id, essai} du tenant d'un appel. strict (écriture en base) : une
    lecture impossible est propagée (le lot sera réécrit plus tard) plutôt que de ranger le coût sur
    un compte deviné ; sinon (lecture du garde-fou), repli sur le tenant lui-même."""
    if mutualise_ or tenant is None:
        return {"compte": PLATEFORME, "billing_user_id": None, "org_id": None, "essai": False}
    key = repr(tenant)
    if cache is not None and key in cache:
        return cache[key]
    out = {"compte": PLATEFORME, "billing_user_id": None, "org_id": None, "essai": False}
    tid = _tenant_entier(tenant)
    if tid is None:
        s = str(tenant)
        if s.startswith("dce:ach:") and s[8:].strip().isdigit():
            out = dict(out, compte=f"acheteur:{int(s[8:])}")
        elif s.startswith("dce:"):
            out = dict(out, compte=ACHETEUR_ANONYME)       # jamais d'adresse IP en base
        elif s.startswith("inv:") and s[4:].strip().isdigit():
            # Aide de l'IA d'un PARTENAIRE du groupement (rédaction, vague 4) : portée technique propre à son
            # invitation (plafonds et disjoncteurs séparés), coût rangé au compte de facturation du CHEF DE
            # FILE (décision 4a : son quota, et le budget de son essai, s'appliquent).
            try:
                from app.models import ProjectInvite, User
                from app.core.quota import _billing_user
                inv = db.get(ProjectInvite, int(s[4:]))
                u = db.get(User, inv.owner_id) if inv is not None else None
                if u is not None:
                    b = _billing_user(u, db)
                    out = {"compte": f"u{b.id}", "billing_user_id": b.id, "org_id": getattr(b, "org_id", None),
                           "essai": essai_actif(b), "payant": est_payant(b)}
            except Exception:       # noqa: BLE001
                if strict:
                    raise
    else:
        try:
            from app.models import User
            from app.core.quota import _billing_user
            u = db.get(User, tid)
            if u is not None:
                b = _billing_user(u, db)
                out = {"compte": f"u{b.id}", "billing_user_id": b.id, "org_id": getattr(u, "org_id", None),
                       "essai": essai_actif(b), "payant": est_payant(b)}
            else:
                out = dict(out, compte=f"u{tid}", billing_user_id=tid)
        except Exception:       # noqa: BLE001
            if strict:
                raise
            out = dict(out, compte=f"u{tid}", billing_user_id=tid)
    if cache is not None:
        cache[key] = out
    return out


def _persister(lot: list) -> list:
    """Ajoute le lot à usage_ia (une ligne par compte, mois et essai). Renvoie les alertes à vérifier."""
    from sqlalchemy import update
    from app.core.database import SessionLocal
    from app.models import UsageIA
    db = SessionLocal()
    try:
        cache, groupes = {}, {}
        for e in lot:
            c = _compte(db, e["tenant"], e["mutualise"], cache, strict=True)
            k = (c["compte"], e["periode"], bool(c["essai"]))
            g = groupes.setdefault(k, {"billing_user_id": c["billing_user_id"], "org_id": c["org_id"],
                                       "payant": bool(c.get("payant")), "cout": 0.0, "n": 0, "tin": 0, "tout": 0})
            g["cout"] += e["cout"]
            g["n"] += int(e.get("n", 1))
            g["tin"] += e["tin"]
            g["tout"] += e["tout"]
        db.rollback()                       # fin des lectures : la transaction d'écriture part d'ici
        now = datetime.now(timezone.utc)
        for (compte, periode, essai), g in groupes.items():
            q = update(UsageIA).where(UsageIA.compte == compte, UsageIA.periode == periode,
                                      UsageIA.essai == essai)
            res = db.execute(q.values(cout_eur=UsageIA.cout_eur + g["cout"], appels=UsageIA.appels + g["n"],
                                      tokens_entree=UsageIA.tokens_entree + g["tin"],
                                      tokens_sortie=UsageIA.tokens_sortie + g["tout"], updated_at=now)
                             .execution_options(synchronize_session=False))
            if res.rowcount == 0:
                db.add(UsageIA(compte=compte, billing_user_id=g["billing_user_id"], org_id=g["org_id"],
                               periode=periode, essai=essai, cout_eur=g["cout"], appels=g["n"],
                               tokens_entree=g["tin"], tokens_sortie=g["tout"], created_at=now, updated_at=now))
                db.flush()
        db.commit()
        return [(compte, g["billing_user_id"], periode) for (compte, periode, essai), g in groupes.items()
                if not essai and g["payant"] and g["billing_user_id"]]
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Lectures (base + relevés pas encore écrits) ───────────────────────────────────────────

def _non_ecrits_pour(db, billing_id: int, periode=None) -> float:
    total, cache = 0.0, {}
    for e in _releves_non_ecrits():
        if e["mutualise"] or (periode and e["periode"] != periode):
            continue
        if _compte(db, e["tenant"], False, cache).get("billing_user_id") == billing_id:
            total += e["cout"]
    return total


def cout_essai_eur(db, billing_user) -> float:
    """Coût IA engagé pendant l'essai par ce compte de facturation (interne)."""
    from sqlalchemy import func
    from app.models import UsageIA
    base = db.query(func.coalesce(func.sum(UsageIA.cout_eur), 0.0)).filter(
        UsageIA.compte == f"u{billing_user.id}", UsageIA.essai.is_(True)).scalar() or 0.0
    # Pas encore écrits : comptés à l'essai si le compte est en essai (c'est ainsi qu'ils seront écrits).
    extra = _non_ecrits_pour(db, billing_user.id) if essai_actif(billing_user) else 0.0
    return float(base) + extra


def cout_mois_eur(db, billing_user, periode=None, essai=None) -> float:
    """Coût IA du mois pour ce compte (essai compris ou non selon `essai` ; None = tout)."""
    from sqlalchemy import func
    from app.models import UsageIA
    periode = periode or _periode()
    q = db.query(func.coalesce(func.sum(UsageIA.cout_eur), 0.0)).filter(
        UsageIA.compte == f"u{billing_user.id}", UsageIA.periode == periode)
    if essai is not None:
        q = q.filter(UsageIA.essai.is_(bool(essai)))
    base = float(q.scalar() or 0.0)
    if essai is None or bool(essai) == essai_actif(billing_user):
        base += _non_ecrits_pour(db, billing_user.id, periode)
    return base


# ── Estimation prudente d'une opération, avant de la lancer ───────────────────────────────

# opération → (caractères envoyés, tokens de sortie demandés, caractères écrits dans le cache).
# Enveloppes hautes, tirées des plafonds du code (consignes comprises).
ENVELOPPES = {
    "analyse": (110_000, 6000, 0),            # avis ou dossier analysé d'un seul tenant (A1)
    "question": (16_000, 1200, 60_000),       # règlements en entier (cache écrit) + 8 passages
    "chiffrage": (8_000, 1800, 0),
    "veille": (180_000, 3200, 0),             # 80 délibérations récentes au plus (amont)
    "deliberation": (22_000, 2800, 0),        # délibération importée ou collée (18 000 car. lus)
    "renouvellements": (60_000, 2600, 0),
    "questionnaire": (14_000, 600, 0),        # PAR question
    "partie": (40_000, 4000, 0),              # une partie de l'atelier, hors dossier commun
    "raccourcir": (45_000, 4000, 0),
    # PAR APPEL de la lecture d'un ancien document pour proposer des fiches (une partie pleine : 60 000
    # caractères au plus + consignes ; app/services/fiches_import.py : SEGMENT_MAX, SORTIE_MAX) ; une partie
    # dense peut coûter jusqu'à APPELS_PAR_PARTIE appels (fiches_import.appels_au_plus).
    "fiches": (64_000, 8000, 0),
}
# opération → tâche du routage (app/services/llm.py, _TABLE) : le modèle, le point d'accès, la
# réflexion et la durée du cache comptés sont ceux de CETTE tâche, secours compris.
TACHE_DE = {
    "analyse": "analyse",
    "question": "questions",
    "chiffrage": "chiffrage",
    "veille": "veille",
    "deliberation": "deliberation",
    "renouvellements": "renouvellements",
    "questionnaire": "questionnaire",
    "partie": "redaction",
    "raccourcir": "raccourcir",
    "fiches": "fiches_preuves",
}


def _zone_estimee(cible) -> str:
    """Point d'accès compté pour une estimation : celui que Mistral utiliserait maintenant, sans
    appel réseau ; tout ce qui n'est pas le mondial est compté au prix de l'UE (+10 %, prudent)."""
    from app.services import llm
    if cible.fournisseur != llm.MISTRAL:
        return ""
    try:
        z = llm.point_acces_mistral(verifier=False).get("zone") or "ue"
    except Exception:       # noqa: BLE001
        z = "ue"
    return "mondial" if z == "mondial" else "ue"


def estimer_appel(tache: str, caracteres: int, tokens_sortie: int, caracteres_cache_ecrits: int = 0,
                  caracteres_cache_lus: int = 0) -> float:
    """Coût estimé (€) d'UN appel de la tâche, au plus : le modèle de la route (table du routage,
    variables LLM_TACHE_*, LLM_PROVIDER, LLM_ROUTAGE) ET son secours s'il est configuré, le plus cher
    des deux ; plafond de sortie tel qu'il serait envoyé (découpage du modèle, réserve de réflexion) ;
    point d'accès de Mistral (UE : +10 %) ; durée du cache de la route (rédaction : une heure, écrite
    à 2 × l'entrée). Même table des prix que le coût mesuré (app/services/tarifs_ia.py)."""
    from app.services import llm, tarifs_ia
    r = llm.route(tache)
    cibles = [r.primaire]
    if r.secours is not None and llm._disponible(r.secours.fournisseur):
        cibles.append(r.secours)
    best = 0.0
    for c in cibles:
        ttl = r.reglages(c.fournisseur).cache_ttl if c.fournisseur == llm.ANTHROPIC else "5m"
        e = tarifs_ia.estimer_eur(c.modele, caracteres, llm.plafond_sortie(c, r, tokens_sortie),
                                  caracteres_cache_ecrits=caracteres_cache_ecrits,
                                  caracteres_cache_lus=caracteres_cache_lus, zone=_zone_estimee(c), ttl=ttl,
                                  sortie_envoyee=True)
        best = max(best, e)
    return best


def estimer(operation: str = "analyse", n: int = 1) -> float:
    """Coût estimé (€) d'une opération, au plus ; n = nombre d'unités (questions, parties)."""
    op = operation if operation in ENVELOPPES else "analyse"
    chars, sortie, cache = ENVELOPPES[op]
    return round(max(1, int(n or 1)) * estimer_appel(TACHE_DE[op], chars, sortie, caracteres_cache_ecrits=cache), 6)


def estimer_atelier(n_parties: int, raccourcir: bool = False) -> float:
    """« Rédiger » n parties : le dossier de l'acheteur commun (jusqu'à DOSSIER_COMMUN_MAX caractères)
    écrit une fois dans le cache (une heure, route « redaction ») puis relu par les autres parties ;
    « Raccourcir » : une partie."""
    if raccourcir:
        return estimer("raccourcir")
    try:
        from app.services.atelier import DOSSIER_COMMUN_MAX
        commun = int(DOSSIER_COMMUN_MAX)
    except Exception:       # noqa: BLE001
        commun = 240_000
    n = max(1, int(n_parties or 1))
    chars, sortie, _c = ENVELOPPES["partie"]
    tache = TACHE_DE["partie"]
    premier = estimer_appel(tache, chars, sortie, caracteres_cache_ecrits=commun)
    autres = estimer_appel(tache, chars, sortie, caracteres_cache_lus=commun) * (n - 1)
    return round(premier + autres, 6)


def estimer_import(lecture: dict, plan_info: dict = None) -> float:
    """Analyse d'un dossier lu en entier : d'un seul tenant (tâche « analyse »), ou en deux temps
    (chaque partie lue par la tâche « lecture_pieces », puis la synthèse, tâche « analyse »). Pages
    encore à lire (scans) : 3 000 caractères chacune."""
    from app.services import analyse_dossier as ad, analysis as an
    from app.services.dce_lecture import totaux
    plan_info = plan_info or {}
    chars = int(plan_info.get("caracteres") or totaux(lecture).get("caracteres") or 0)
    if (lecture or {}).get("a_poursuivre"):
        t = totaux(lecture)
        chars += max(0, int(t.get("pages") or 0) - int(t.get("pages_lues") or 0)) * 3000
    budget = int(plan_info.get("budget_caracteres") or 0) or ad.budget_caracteres(20_000)
    tache_analyse = getattr(an, "ANALYSE_TACHE", "analyse")
    # Analyse en deux temps (app.services.analyse_partagee) : la partie propre à l'entreprise est un
    # appel de plus (l'extraction, le profil, la compatibilité). L'estimation compte TOUJOURS
    # l'extraction comme neuve : prudente, et identique que l'extraction soit resservie ou non.
    from app.services import analyse_partagee as _ap
    entreprise = (estimer_appel(tache_analyse, 40_000, getattr(an, "ENTREPRISE_MAX_TOKENS", 2000))
                  if _ap.actif() else 0.0)
    if chars <= budget:
        return round(estimer_appel(tache_analyse, chars + 20_000, an.ANALYSE_MAX_TOKENS) + entreprise, 6)
    seg_chars = max(1, int(ad.SEGMENT_TOKENS * ad.CARACTERES_PAR_TOKEN))
    n_pieces = len((lecture or {}).get("pieces") or [])
    appels = math.ceil(chars / seg_chars) + math.ceil(max(1, n_pieces) / max(1, ad.GROUPE_MAX_PIECES))
    appels = min(ad.MAX_APPELS, appels) + min(ad.RELANCES_MAX, math.ceil(appels / 4))
    # Sortie : 40 informations au plus par partie (≈ 5 200 tokens), plafond de l'appel au-delà.
    # Une estimation par appel (le seuil de prix d'une requête longue s'applique appel par appel).
    par_appel = max(1, math.ceil((chars + appels * 6000) / appels))
    lecture_cout = appels * estimer_appel(ad.TACHE_PIECES, par_appel, min(ad.PIECES_MAX_TOKENS, 5200))
    synthese = estimer_appel(tache_analyse, int(ad.BUDGET_TOKENS * ad.CARACTERES_PAR_TOKEN), an.ANALYSE_MAX_TOKENS)
    return round(lecture_cout + synthese + entreprise, 6)


# ── Le garde-fou ───────────────────────────────────────────────────────────────────────────

def verifier(user, db, operation: str = "analyse", estimation_eur: float = None, n: int = 1) -> None:
    """Refus propre (402) AVANT l'opération si le compte de facturation est en essai et que le coût
    engagé plus l'estimation prudente dépasse le budget de l'essai, ou si son essai est terminé sans
    formule payante (quota.exiger_ia : toutes les fonctions d'IA en pause). Sans effet pour tout autre
    compte (forfaits payants : aucun plafond). Jamais de montant dans la réponse."""
    from app.core.quota import _billing_user, exiger_ia
    exiger_ia(user, db)
    billing = _billing_user(user, db) if db is not None else user
    if not essai_actif(billing):
        return
    budget = budget_essai_eur()
    if budget <= 0:
        return
    est = float(estimation_eur) if estimation_eur is not None else estimer(operation, n)
    conso = cout_essai_eur(db, billing)
    if conso + est > budget:
        logger.info("Essai gratuit : « %s » refusée avant tout appel (compte u%s) : %.4f € engagés + %.4f € "
                    "estimés > budget de %.2f €.", operation, billing.id, conso, est, budget)
        epuise = operation == "question" or conso + estimer("question") > budget
        raise HTTPException(402, {"code": CODE_LIMITE, "message": MSG_LIMITE if epuise else MSG_DEPASSE})


def etat_essai(db, billing_user) -> str:
    """« ok » / « proche » / « atteint » (aucun montant) pour l'écran du compteur d'essai."""
    if db is None or not essai_actif(billing_user):
        return "ok"
    budget = budget_essai_eur()
    if budget <= 0:
        return "ok"
    try:
        conso = cout_essai_eur(db, billing_user)
    except Exception:       # noqa: BLE001
        return "ok"
    if conso + estimer("question") > budget:
        return "atteint"
    if conso >= _f("TRIAL_AI_BUDGET_PROCHE", 0.8) * budget or conso + estimer("analyse") > budget:
        return "proche"
    return "ok"


# ── Alerte interne des forfaits payants (jamais de blocage) ────────────────────────────────

def _prix_forfait(plan: str) -> float:
    prix = getattr(_settings(), "PLAN_PRICES_EUR", None) or {}
    try:
        if plan in prix and float(prix[plan]) > 0:
            return float(prix[plan])
        vals = [float(v) for v in prix.values() if float(v) > 0]
        return max(vals) if vals else 199.99
    except (TypeError, ValueError):
        return 199.99


def seuil_alerte_eur(user) -> float:
    ratio = _f("PAID_AI_ALERT_RATIO", 0.5)
    return round(ratio * _prix_forfait(_plan(user)), 2) if ratio > 0 else 0.0


def _verifier_alerte(compte: str, billing_id: int, periode: str) -> None:
    """Après écriture : coût du mois d'une organisation payante au-delà du seuil → une alerte au
    journal (une fois par mois) et la date gardée pour /api/admin/usage-ia. Ne bloque rien."""
    try:
        from sqlalchemy import update
        from app.core.database import SessionLocal
        from app.models import UsageIA, User
        db = SessionLocal()
        try:
            u = db.get(User, billing_id)
            if u is None or not est_payant(u):
                return
            seuil = seuil_alerte_eur(u)
            if seuil <= 0:
                return
            row = db.query(UsageIA).filter(UsageIA.compte == compte, UsageIA.periode == periode,
                                           UsageIA.essai.is_(False)).first()
            if row is None or row.alerte_le is not None or float(row.cout_eur or 0) <= seuil:
                return
            res = db.execute(update(UsageIA).where(UsageIA.id == row.id, UsageIA.alerte_le.is_(None))
                             .values(alerte_le=datetime.now(timezone.utc)).execution_options(synchronize_session=False))
            db.commit()
            if res.rowcount == 1:
                logger.warning("ALERTE coût IA : organisation du compte u%s (forfait %s) à %.2f € ce mois (%s), "
                               "au-delà du seuil de %.2f € (%.0f %% du prix du forfait). Aucun blocage.",
                               billing_id, _plan(u), float(row.cout_eur or 0), periode, seuil,
                               _f("PAID_AI_ALERT_RATIO", 0.5) * 100)
        finally:
            db.close()
    except Exception as e:      # noqa: BLE001 — l'alerte ne casse jamais l'écriture du relevé
        logger.warning("Vérification de l'alerte de coût IA impossible : %s", type(e).__name__)


# ── Relevé pour l'administration (montants internes) ──────────────────────────────────────

def releve_admin(db, periode: str = None, limite: int = 200) -> dict:
    from sqlalchemy import func
    from app.models import UsageIA, User, Organization
    from app.core.quota import _trial_used, _limit, _trial_days_left
    vider(timeout=5.0)
    periode = periode or _periode()
    budget = budget_essai_eur()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def _org_nom(u):
        try:
            if getattr(u, "org_id", None):
                o = db.get(Organization, u.org_id)
                if o is not None:
                    return o.name or ""
        except Exception:       # noqa: BLE001
            pass
        return ""

    essais = []
    q = (db.query(User).filter(User.trial_ends_at.isnot(None), User.trial_ends_at > now)
         .order_by(User.id.desc()).limit(max(1, int(limite))))
    for u in q.all():
        if not essai_actif(u):
            continue
        if getattr(u, "org_id", None):
            o = db.get(Organization, u.org_id)
            if o is not None and o.owner_id and o.owner_id != u.id:
                continue                         # membre : son essai est celui du propriétaire
        conso = cout_essai_eur(db, u)
        essais.append({"compte": f"u{u.id}", "email": u.email, "organisation": _org_nom(u),
                       "analyses_utilisees": _trial_used(u), "analyses_comprises": _limit(u),
                       "jours_restants": _trial_days_left(u), "cout_ia_eur": round(conso, 4),
                       "budget_eur": budget, "part_budget": round(conso / budget, 4) if budget > 0 else None,
                       "etat": etat_essai(db, u)})
    essais.sort(key=lambda x: x["cout_ia_eur"], reverse=True)

    payants = []
    rows = (db.query(UsageIA).filter(UsageIA.periode == periode, UsageIA.essai.is_(False),
                                     UsageIA.billing_user_id.isnot(None))
            .order_by(UsageIA.cout_eur.desc()).limit(max(1, int(limite))).all())
    for r in rows:
        u = db.get(User, r.billing_user_id)
        if u is None or not est_payant(u):
            continue
        seuil = seuil_alerte_eur(u)
        cout = float(r.cout_eur or 0)
        payants.append({"compte": r.compte, "email": u.email, "organisation": _org_nom(u), "forfait": _plan(u),
                        "cout_ia_mois_eur": round(cout, 4), "seuil_alerte_eur": seuil,
                        "au_dela_du_seuil": bool(seuil and cout > seuil),
                        "alerte_le": r.alerte_le.isoformat() if r.alerte_le else None,
                        "appels": int(r.appels or 0)})
    autres = {}
    for compte, cout, appels in (db.query(UsageIA.compte, func.sum(UsageIA.cout_eur), func.sum(UsageIA.appels))
                                 .filter(UsageIA.periode == periode, UsageIA.billing_user_id.is_(None))
                                 .group_by(UsageIA.compte).all()):
        autres[compte] = {"cout_ia_mois_eur": round(float(cout or 0), 4), "appels": int(appels or 0)}
    total = db.query(func.coalesce(func.sum(UsageIA.cout_eur), 0.0)).filter(UsageIA.periode == periode).scalar()
    return {"periode": periode, "budget_essai_eur": budget, "seuil_alerte_ratio": _f("PAID_AI_ALERT_RATIO", 0.5),
            "cout_ia_total_mois_eur": round(float(total or 0), 4), "essais": essais,
            "forfaits_payants": payants, "plateforme_et_acheteurs": autres,
            "explication": ("Coût réel des appels à l'IA au tarif public des fournisseurs (interne, jamais montré "
                            "aux clients). Essais : budget de l'essai consommé (au-delà, les fonctions d'IA "
                            "s'arrêtent avant de commencer une opération). Forfaits payants : jamais bridés ; "
                            "une alerte est notée quand le coût du mois dépasse le seuil.")}
