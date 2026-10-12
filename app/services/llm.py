"""
Adjugo — Couche IA centralisée : ROUTAGE PAR TÂCHE, secours croisé, coût, surveillance.

Tous les appels IA de l'application passent par messages_create() (ou complete / complete_ex /
complete_json qui l'appellent), avec le format de requête Anthropic (system + messages) et le NOM
DE LA TÂCHE (`tache=`). La table _TABLE ci-dessous dit, pour chaque tâche, quel fournisseur et quel
modèle la traitent, avec quels réglages, et vers qui basculer si ce fournisseur fait défaut :

  • lecture et extraction de documents (analyse du dossier, y compris la lecture en deux temps,
    exigences, délibérations de la veille, renouvellements) → Mistral Large 4 (`mistral-large-4`,
    préversion publique du 06/10/2026 ; JAMAIS l'alias mistral-large-latest, qui désigne Large 3),
    secours Claude Sonnet 5.5 si Mistral est absent, en panne, en erreur de modèle, coupé ou si son
    JSON est illisible ;
  • questions-réponses, rédaction (atelier), questionnaire, chiffrage, côté acheteur → Claude Sonnet
    5.5 (`claude-sonnet-5-5`), secours Mistral Large 4 si Anthropic est en panne (et si la clé
    Mistral existe).

Mistral n'est utilisé QUE pour les tâches routées vers lui (ou en secours), et seulement si sa clé
est présente : MISTRAL_API_KEY_ADJUGO (lue en priorité), ou MISTRAL_API_KEY (compatibilité). La
présence d'une clé ne fait plus RIEN basculer d'autre (l'ancien mode « auto » envoyait tout chez
Mistral Large 3 dès qu'une MISTRAL_API_KEY existait). LLM_PROVIDER=anthropic|mistral force encore
toutes les tâches chez un seul fournisseur, mais le diagnostic d'administration et le journal de
démarrage le disent. LLM_ROUTAGE=ancien revient en une minute à l'ancien routage (Claude Sonnet 4.6
et Haiku 4.5, réglages d'origine, aucun secours).

Ce que la couche garantit pour CHAQUE appel, quel que soit le fournisseur (secours compris) : noms
des salariés masqués (pii_scope) avant l'envoi, espace facturé (tenant_scope), plafonds de tokens,
disjoncteurs (par fournisseur et par espace), places limitées (sémaphore de process), coût mesuré
(cost_meter), surveillance de la qualité (app.services.llm_qualite). Les garde-fous des appelants
(citations vérifiées, anti-invention, remboursement si l'IA tombe) ne dépendent pas du fournisseur :
la réponse est rendue sous la même forme (resp.content[0].text, resp.usage, resp.stop_reason).

Claude Sonnet 5.5 (documentation Anthropic relue le 12/10/2026) : toute valeur de temperature,
top_p ou top_k renvoie une erreur 400 → jamais envoyées ; la réponse peut commencer par des blocs
de réflexion → seuls les blocs de type « text » sont lus ; réflexion et effort passés par
`extra_body` (SDK épinglé en 0.34, qui transmet tel quel et lit les blocs inconnus sans erreur) ;
la réflexion compte dans max_tokens ; le découpage produit ≈ 30 % de tokens en plus que Sonnet 4.6.
"""
import contextvars
import datetime as _dt
import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from anthropic import Anthropic

from app.core.config import get_settings
from app.services import llm_qualite as qualite

settings = get_settings()
logger = logging.getLogger("adjugo")

# Verrou des mutations d'état partagé (compteurs, disjoncteurs) : le pool de jobs et
# les requêtes concurrentes mettent à jour ces dicts ; `x += 1` n'est pas atomique.
_LOCK = threading.Lock()

ANTHROPIC = "anthropic"
MISTRAL = "mistral"

# Modèles de l'ANCIEN routage (LLM_ROUTAGE=ancien) — aussi le modèle par défaut d'un appel sans tâche.
MODEL = "claude-sonnet-4-6"        # raisonnement (analyse, stratégie)
MODEL_FAST = "claude-haiku-4-5"    # rapide (questions, lecture des pièces)
# Modèles du routage par tâche (identifiants exacts, vérifiés le 12/10/2026) — surchargeables.
MODELE_SONNET_DEFAUT = "claude-sonnet-5-5"
MODELE_MISTRAL_DEFAUT = "mistral-large-4"


def modele_sonnet() -> str:
    return (os.getenv("LLM_MODELE_SONNET") or "").strip() or MODELE_SONNET_DEFAUT


def modele_mistral() -> str:
    return (os.getenv("LLM_MODELE_MISTRAL") or "").strip() or MODELE_MISTRAL_DEFAUT


# Délais & reprises : un appel IA ne doit pas bloquer un worker indéfiniment.
_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))     # secondes par appel
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
# Plafond de sortie envoyé (la réflexion compte dedans) : payé à l'usage, pas au plafond.
_MAX_SORTIE = int(os.getenv("LLM_MAX_SORTIE", "64000"))

_client: Optional[Anthropic] = None


class LLMUnavailable(RuntimeError):
    """Service IA momentanément indisponible (circuit ouvert, plafond atteint, fournisseur absent)."""


class LLMRefus(LLMUnavailable):
    """Le modèle a refusé de répondre (stop_reason « refusal ») et aucun secours n'a pu le faire.
    Sous-classe de LLMUnavailable : les appelants remboursent et proposent de réessayer."""


def client() -> Anthropic:
    """Client Anthropic paresseux (évite de planter à l'import si pas de clé)."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY,
                            timeout=_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


_CLIENT_REEL = client


# ── Clés et disponibilité des fournisseurs (jamais la valeur d'une clé dans un journal) ────────

_NOMS_CLE_MISTRAL = ("MISTRAL_API_KEY_ADJUGO", "MISTRAL_API_KEY")


def _cle_mistral() -> tuple:
    """(valeur, nom de la variable) : MISTRAL_API_KEY_ADJUGO en priorité, MISTRAL_API_KEY ensuite."""
    for nom in _NOMS_CLE_MISTRAL:
        v = (getattr(settings, nom, "") or "").strip()
        if v:
            return v, nom
    return "", ""


def _use_mistral() -> bool:
    """Mistral est-il UTILISABLE (clé présente) ? Ne décide plus de rien d'autre : seules les tâches
    routées vers Mistral (ou en secours) y partent."""
    return bool(_cle_mistral()[0])


def _anthropic_disponible() -> bool:
    # Sans clé, le vrai client échouerait sur le réseau : absent (secours, ou 503 propre).
    return bool((settings.ANTHROPIC_API_KEY or "").strip()) or client is not _CLIENT_REEL


def _disponible(fournisseur: str) -> bool:
    return _use_mistral() if fournisseur == MISTRAL else _anthropic_disponible()


# ── Familles de modèles ─────────────────────────────────────────────────────────────────────────

_RE_CLAUDE = re.compile(r"^claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d+))?")


def _version_claude(modele: str):
    m = _RE_CLAUDE.match((modele or "").strip().lower())
    if not m:
        return None
    return m.group(1), (int(m.group(2)), int(m.group(3) or 0))


def _nouvelle_generation(modele: str) -> bool:
    """Claude 4.7 et suivants : découpage ≈ +30 % de tokens, sampling refusé (temperature → 400 sur
    Sonnet 5.5), réflexion active par défaut sur la génération 5."""
    v = _version_claude(modele)
    return bool(v and v[1] >= (4, 7))


def fournisseur_du_modele(modele: str) -> str:
    m = (modele or "").strip().lower()
    if m.startswith(("mistral", "magistral", "ministral", "codestral", "devstral", "pixtral", "open-mistral")):
        return MISTRAL
    return ANTHROPIC


# Tokens produits pour un même texte, rapportés à l'ancien découpage de Claude (Sonnet 4.6) :
# ≈ +30 % pour Claude 4.7 et suivants (page des prix Anthropic, 12/10/2026). Mistral : non publié
# pour le français → 1,3 aussi pour les plafonds de sortie (prudent : payé à l'usage), 1,0 pour les
# estimations de coût (hypothèse du comparatif).
FACTEUR_DECOUPAGE_NOUVEAU = float(os.getenv("LLM_FACTEUR_DECOUPAGE", "1.3"))


def facteur_decoupage(modele: str) -> float:
    return FACTEUR_DECOUPAGE_NOUVEAU if _nouvelle_generation(modele) else 1.0


def _facteur_plafond(modele: str) -> float:
    if fournisseur_du_modele(modele) == MISTRAL:
        return FACTEUR_DECOUPAGE_NOUVEAU
    return facteur_decoupage(modele)


# ── ROUTAGE PAR TÂCHE ───────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Reglages:
    """Réglages d'un fournisseur pour une tâche.
    reflexion (Claude 5.x) : « between_tools » (pas de réflexion préalable : le plus bas sur Sonnet
    5.5 ; « disabled » sur les modèles qui l'acceptent) ou « adaptive » (réflexion selon la demande,
    réglage par défaut de Sonnet 5.5). effort : low | medium | high (défaut de Sonnet 5.5) | xhigh |
    max. reserve_reflexion : tokens ajoutés à max_tokens quand la réflexion est active (elle compte
    dedans). cache_ttl : « 5m » ou « 1h » pour les blocs marqués cache (cached_text_block).
    raisonnement (Mistral) : valeur de reasoning_effort, vide = non envoyé (réglage du modèle)."""
    reflexion: str = ""
    effort: str = ""
    reserve_reflexion: int = 0
    cache_ttl: str = "5m"
    raisonnement: str = ""


@dataclass(frozen=True)
class Cible:
    fournisseur: str
    modele: str


@dataclass(frozen=True)
class Route:
    tache: str
    libelle: str
    primaire: Cible
    secours: Optional[Cible] = None
    secours_sur: frozenset = frozenset()
    json: bool = False
    anthropic: Reglages = field(default_factory=Reglages)
    mistral: Reglages = field(default_factory=Reglages)
    origine: str = "table"

    def reglages(self, fournisseur: str) -> Reglages:
        return self.mistral if fournisseur == MISTRAL else self.anthropic


# Motifs de bascule vers le secours.
MOTIFS = {
    "absent": "fournisseur non configuré (clé absente)",
    "panne": "fournisseur en panne ou injoignable",
    "modele": "erreur de modèle ou de requête",
    "coupe": "réponse coupée (plafond de sortie)",
    "json": "réponse JSON illisible",
    "refus": "refus du modèle",
}
_SUR_MISTRAL = frozenset({"absent", "panne", "modele", "coupe", "json"})
# Lecture des pièces : une réponse coupée est relue en deux moitiés par l'appelant (analyse_dossier).
_SUR_MISTRAL_LECTURE = frozenset({"absent", "panne", "modele", "json"})
_SUR_ANTHROPIC = frozenset({"absent", "panne", "modele", "refus"})

_BT_HIGH = Reglages("between_tools", "high")
_BT_MEDIUM = Reglages("between_tools", "medium")

# tâche → libellé, fournisseur du routage par tâche, JSON attendu, réglages Claude, motifs de
# bascule, modèle de l'ANCIEN routage (celui que chaque appel utilisait avant le 12/10/2026).
_TABLE = {
    "analyse": dict(
        libelle="Analyse d'un avis ou d'un dossier de consultation (et synthèse de la lecture en deux temps)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_HIGH, secours_sur=_SUR_MISTRAL, ancien=MODEL),
    "lecture_pieces": dict(
        libelle="Lecture des pièces une à une (premier temps de la lecture en deux temps)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_HIGH, secours_sur=_SUR_MISTRAL_LECTURE, ancien=MODEL_FAST),
    "exigences": dict(
        libelle="Exigences relevées dans le dossier (dossier de présentation complet)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_HIGH, secours_sur=_SUR_MISTRAL, ancien=MODEL),
    "veille": dict(
        libelle="Veille des délibérations (tri des intitulés)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_MEDIUM, secours_sur=_SUR_MISTRAL, ancien=MODEL),
    "deliberation": dict(
        libelle="Délibération importée (projets détectés)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_HIGH, secours_sur=_SUR_MISTRAL, ancien=MODEL),
    "renouvellements": dict(
        libelle="Renouvellements de marchés (radar des échéances)",
        fournisseur=MISTRAL, json=True, anthropic=_BT_MEDIUM, secours_sur=_SUR_MISTRAL, ancien=MODEL),
    "questions": dict(
        libelle="Questions sur le dossier du marché",
        fournisseur=ANTHROPIC, json=True, anthropic=_BT_MEDIUM, secours_sur=_SUR_ANTHROPIC, ancien=MODEL_FAST),
    "redaction": dict(
        libelle="Rédaction d'une partie du dossier de présentation (atelier, dossier complet)",
        fournisseur=ANTHROPIC, json=False,
        anthropic=Reglages("adaptive", "high", reserve_reflexion=8000, cache_ttl="1h"),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "raccourcir": dict(
        libelle="Raccourcir une partie rédigée",
        fournisseur=ANTHROPIC, json=False, anthropic=_BT_HIGH, secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "plan": dict(
        libelle="Plan du dossier de présentation complet",
        fournisseur=ANTHROPIC, json=True, anthropic=_BT_HIGH, secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "controle": dict(
        libelle="Contrôle de conformité du dossier de présentation",
        fournisseur=ANTHROPIC, json=True, anthropic=Reglages("adaptive", "high", reserve_reflexion=6000),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "questionnaire": dict(
        libelle="Questionnaire (réponses courtes sourcées)",
        fournisseur=ANTHROPIC, json=False, anthropic=_BT_HIGH, secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "chiffrage": dict(
        libelle="Chiffrage (découpage en tâches et en jours)",
        fournisseur=ANTHROPIC, json=True, anthropic=Reglages("adaptive", "medium", reserve_reflexion=4000),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "repartition": dict(
        libelle="Répartition des lots dans un groupement",
        fournisseur=ANTHROPIC, json=True, anthropic=Reglages("adaptive", "medium", reserve_reflexion=4000),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "acheteur_dce": dict(
        libelle="Acheteur : cœur du DCE (objet, lots, critères)",
        fournisseur=ANTHROPIC, json=True, anthropic=Reglages("adaptive", "high", reserve_reflexion=8000),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
    "acheteur_annexes": dict(
        libelle="Acheteur : volets administratifs et CCTP",
        fournisseur=ANTHROPIC, json=True, anthropic=Reglages("adaptive", "high", reserve_reflexion=8000),
        secours_sur=_SUR_ANTHROPIC, ancien=MODEL_FAST),
    "acheteur_conseils": dict(
        libelle="Acheteur : conseils de sourcing",
        fournisseur=ANTHROPIC, json=True, anthropic=_BT_MEDIUM, secours_sur=_SUR_ANTHROPIC, ancien=MODEL),
}
TACHES = tuple(_TABLE)

_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def routage_mode() -> str:
    """« nouveau » (routage par tâche, défaut) ou « ancien » (Sonnet 4.6 / Haiku 4.5, réglages
    d'origine, aucun secours). Une seule variable : LLM_ROUTAGE=ancien, puis redémarrage."""
    v = (os.getenv("LLM_ROUTAGE") or getattr(settings, "LLM_ROUTAGE", "") or "nouveau").strip().lower()
    return "ancien" if v in ("ancien", "v1", "old", "retour", "4.6") else "nouveau"


def forcage() -> str:
    """« anthropic » | « mistral » si LLM_PROVIDER force toutes les tâches chez un seul fournisseur,
    sinon « » (auto ou vide = routage par tâche ; plus aucune bascule sur la seule présence d'une clé)."""
    v = (os.getenv("LLM_PROVIDER") or getattr(settings, "LLM_PROVIDER", "") or "auto").strip().lower()
    return v if v in (ANTHROPIC, MISTRAL) else ""


def _resolve_provider() -> str:
    """Compatibilité : fournisseur forcé, ou « par_tache »."""
    return forcage() or "par_tache"


def _env_tache(tache: str, suffixe: str = "") -> str:
    return (os.getenv(f"LLM_TACHE_{tache.upper()}{suffixe}") or "").strip()


def _parse_cible(v: str, defaut_fournisseur: str = "") -> Optional[Cible]:
    """« mistral:mistral-large-4 », « anthropic:claude-sonnet-5-5 » ou un nom de modèle seul."""
    v = (v or "").strip()
    if not v or v.lower() in ("aucun", "non", "none", "0", "off"):
        return None
    if ":" in v:
        f, m = v.split(":", 1)
        f = f.strip().lower()
        if f not in (ANTHROPIC, MISTRAL):
            f = fournisseur_du_modele(m)
        return Cible(f, m.strip())
    return Cible(fournisseur_du_modele(v) if not defaut_fournisseur else defaut_fournisseur, v)


def _modele_defaut(fournisseur: str, ancien: str) -> str:
    if fournisseur == MISTRAL:
        return modele_mistral()
    return ancien if routage_mode() == "ancien" else modele_sonnet()


def _secours_actif() -> bool:
    return (os.getenv("LLM_SECOURS") or "1").strip().lower() not in ("0", "false", "non", "no", "off")


def _reglages_env(tache: str, base: Reglages) -> Reglages:
    eff = _env_tache(tache, "_EFFORT").lower()
    refl = _env_tache(tache, "_REFLEXION").lower()
    cache = _env_tache(tache, "_CACHE").lower()
    res = _env_tache(tache, "_RESERVE")
    rais = _env_tache(tache, "_RAISONNEMENT").lower()
    kw = dict(reflexion=base.reflexion, effort=base.effort, reserve_reflexion=base.reserve_reflexion,
              cache_ttl=base.cache_ttl, raisonnement=base.raisonnement)
    if eff in _EFFORTS or eff == "aucun":
        kw["effort"] = "" if eff == "aucun" else eff
    if refl in ("between_tools", "adaptive", "aucune"):
        kw["reflexion"] = "" if refl == "aucune" else refl
    if cache in ("5m", "1h"):
        kw["cache_ttl"] = cache
    if res.isdigit():
        kw["reserve_reflexion"] = int(res)
    if rais:
        kw["raisonnement"] = "" if rais == "aucun" else rais
    return Reglages(**kw)


def route(tache: Optional[str], modele: Optional[str] = None) -> Route:
    """La route EFFECTIVE d'une tâche : table, puis variables d'environnement, puis forçage."""
    mode = routage_mode()
    spec = _TABLE.get(tache or "")
    if spec is None:
        # Appel sans tâche (ou tâche inconnue) : le modèle demandé, chez son fournisseur, sans secours.
        m = modele or MODEL
        r = Route(tache or "sans_tache", "Appel direct (sans tâche)", Cible(fournisseur_du_modele(m), m),
                  origine="direct")
    elif mode == "ancien":
        m = spec["ancien"]
        if tache == "lecture_pieces" and (os.getenv("ANALYSE_MODELE_PIECES") or "").strip():
            m = os.getenv("ANALYSE_MODELE_PIECES").strip()
        r = Route(tache, spec["libelle"], Cible(fournisseur_du_modele(m), m), json=spec["json"], origine="ancien")
    else:
        f = spec["fournisseur"]
        prim = Cible(f, _modele_defaut(f, spec["ancien"]))
        autre = ANTHROPIC if f == MISTRAL else MISTRAL
        sec = Cible(autre, _modele_defaut(autre, spec["ancien"]))
        r = Route(tache, spec["libelle"], prim, sec, spec["secours_sur"], spec["json"],
                  anthropic=spec["anthropic"], mistral=Reglages(), origine="table")
        if tache == "lecture_pieces" and (os.getenv("ANALYSE_MODELE_PIECES") or "").strip():
            c = _parse_cible(os.getenv("ANALYSE_MODELE_PIECES"))
            r = _remplacer(r, primaire=c, origine="env")
    if spec is not None:
        p = _parse_cible(_env_tache(tache))
        if p is not None:
            r = _remplacer(r, primaire=p, origine="env")
        s_env = _env_tache(tache, "_SECOURS")
        if s_env:
            s = _parse_cible(s_env)
            sur = r.secours_sur or (_SUR_MISTRAL if r.primaire.fournisseur == MISTRAL else _SUR_ANTHROPIC)
            r = _remplacer(r, secours=s, secours_sur=sur if s else frozenset(), origine="env")
        r = _remplacer(r, anthropic=_reglages_env(tache, r.anthropic), mistral=_reglages_env(tache, r.mistral))
    if r.secours is not None and (not _secours_actif() or r.secours == r.primaire):
        r = _remplacer(r, secours=None, secours_sur=frozenset())
    fz = forcage()
    if fz:
        if r.primaire.fournisseur != fz:
            if r.secours is not None and r.secours.fournisseur == fz:
                prim = r.secours
            else:
                prim = Cible(fz, _modele_defaut(fz, (spec or {}).get("ancien", MODEL)))
            r = _remplacer(r, primaire=prim)
        r = _remplacer(r, secours=None, secours_sur=frozenset(), origine="force")
        if fz == MISTRAL and not _use_mistral():
            # Forçage sans clé : jamais de panne due à un réglage → Anthropic.
            m = _modele_defaut(ANTHROPIC, (spec or {}).get("ancien", MODEL))
            r = _remplacer(r, primaire=Cible(ANTHROPIC, m))
    return r


def _remplacer(r: Route, **kw) -> Route:
    d = {k: getattr(r, k) for k in ("tache", "libelle", "primaire", "secours", "secours_sur", "json",
                                     "anthropic", "mistral", "origine")}
    d.update(kw)
    return Route(**d)


# ── Point d'accès Mistral : UE si le modèle y est servi, sinon mondial (décidé à l'exécution) ──

MISTRAL_URL_UE = "https://api.eu.mistral.ai/v1"
MISTRAL_URL_MONDIAL = "https://api.mistral.ai/v1"
_PA_TTL_OK = float(os.getenv("MISTRAL_VERIF_TTL_S", "21600"))      # nouvelle vérification toutes les 6 h
_PA_TTL_ECHEC = 300.0
_PA_LOCK = threading.Lock()
_PA = {"decision": "", "verifie": False, "presents": {}, "nombre_modeles": None, "erreur": "",
       "verifie_le": "", "prochain": 0.0}


def _mode_point_acces() -> str:
    v = (os.getenv("MISTRAL_POINT_ACCES") or getattr(settings, "MISTRAL_POINT_ACCES", "") or "auto").strip().lower()
    if v in ("ue", "eu", "europe"):
        return "ue"
    if v in ("mondial", "global", "monde"):
        return "mondial"
    return "auto"


def _url_personnalisee() -> str:
    u = (os.getenv("MISTRAL_BASE_URL") or getattr(settings, "MISTRAL_BASE_URL", "") or "").strip().rstrip("/")
    return u if u and u not in (MISTRAL_URL_MONDIAL, MISTRAL_URL_UE) else ""


def _modeles_mistral_routes() -> set:
    out = set()
    for t in TACHES:
        r = route(t)
        for c in (r.primaire, r.secours):
            if c is not None and c.fournisseur == MISTRAL:
                out.add(c.modele)
    return out or {modele_mistral()}


def verifier_modeles_ue(timeout: float = 8.0) -> dict:
    """GET /v1/models sur le point d'accès UE (models.list) : les modèles routés vers Mistral y
    sont-ils servis ? Ne lève jamais ; aucune clé dans le résultat."""
    cle, _nom = _cle_mistral()
    if not cle:
        return {"verifie": False, "erreur": "clé Mistral absente", "presents": {}}
    try:
        r = httpx.get(MISTRAL_URL_UE + "/models", headers={"Authorization": f"Bearer {cle}"}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        ids = set()
        for m in items or []:
            if isinstance(m, dict):
                if m.get("id"):
                    ids.add(str(m["id"]))
                for a in m.get("aliases") or []:
                    ids.add(str(a))
        besoins = _modeles_mistral_routes()
        return {"verifie": True, "presents": {m: (m in ids) for m in sorted(besoins)},
                "nombre_modeles": len(items or []), "erreur": ""}
    except Exception as e:      # noqa: BLE001
        st = getattr(getattr(e, "response", None), "status_code", None)
        return {"verifie": False, "presents": {}, "erreur": type(e).__name__ + (f" (HTTP {st})" if st else "")}


def point_acces_mistral(verifier: bool = True) -> dict:
    """{mode, zone (« ue » | « mondial » | « personnalise »), url, raison, verifie}. En mode auto, la
    décision est prise par models.list sur le point d'accès UE (au plus toutes les 6 h ; toutes les 5 min
    après un échec de vérification, en restant sur l'UE en attendant)."""
    perso = _url_personnalisee()
    if perso:
        return {"mode": "personnalise", "zone": "personnalise", "url": perso,
                "raison": "MISTRAL_BASE_URL fixé à une adresse particulière", "verifie": False}
    mode = _mode_point_acces()
    if mode == "ue":
        return {"mode": "ue", "zone": "ue", "url": MISTRAL_URL_UE, "raison": "MISTRAL_POINT_ACCES=ue", "verifie": False}
    if mode == "mondial":
        return {"mode": "mondial", "zone": "mondial", "url": MISTRAL_URL_MONDIAL,
                "raison": "MISTRAL_POINT_ACCES=mondial", "verifie": False}
    now = time.monotonic()
    with _PA_LOCK:
        snap = dict(_PA)
    if snap["decision"] and now < snap["prochain"]:
        return _pa_out(snap)
    if not (verifier and _use_mistral()):
        return {"mode": "auto", "zone": "ue", "url": MISTRAL_URL_UE, "verifie": False,
                "raison": "point d'accès UE par défaut (disponibilité du modèle pas encore vérifiée)"}
    res = verifier_modeles_ue()
    with _PA_LOCK:
        _PA["verifie_le"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _PA["erreur"] = res.get("erreur") or ""
        _PA["nombre_modeles"] = res.get("nombre_modeles")
        if res.get("verifie"):
            _PA["verifie"] = True
            _PA["presents"] = dict(res.get("presents") or {})
            absents = [m for m, ok in _PA["presents"].items() if not ok]
            _PA["decision"] = "mondial" if absents else "ue"
            _PA["prochain"] = now + _PA_TTL_OK
            if absents:
                logger.warning("Mistral : %s non servi(s) sur le point d'accès UE → point d'accès mondial.",
                               ", ".join(absents))
        else:
            _PA["verifie"] = False
            _PA["decision"] = "ue"
            _PA["prochain"] = now + _PA_TTL_ECHEC
            logger.warning("Mistral : vérification des modèles du point d'accès UE impossible (%s) ; "
                           "point d'accès UE gardé, nouvelle vérification dans 5 minutes.", _PA["erreur"])
        snap = dict(_PA)
    return _pa_out(snap)


def _pa_out(snap: dict) -> dict:
    ue = snap["decision"] == "ue"
    if snap["verifie"]:
        raison = ("modèles routés vers Mistral servis sur le point d'accès UE (vérifié par models.list)" if ue else
                  "un modèle routé vers Mistral n'est pas servi sur le point d'accès UE (models.list)")
    else:
        raison = "point d'accès UE par défaut (vérification impossible : " + (snap["erreur"] or "inconnue") + ")"
    return {"mode": "auto", "zone": "ue" if ue else "mondial", "url": MISTRAL_URL_UE if ue else MISTRAL_URL_MONDIAL,
            "raison": raison, "verifie": bool(snap["verifie"]), "presents": dict(snap["presents"]),
            "verifie_le": snap["verifie_le"]}


def _marquer_absent_ue(modele: str) -> None:
    """Le point d'accès UE a répondu « modèle inconnu » : les appels suivants passent par le mondial."""
    if _mode_point_acces() != "auto" or _url_personnalisee():
        return
    with _PA_LOCK:
        if _PA["decision"] in ("", "ue"):
            _PA["decision"] = "mondial"
            _PA["verifie"] = True
            _PA["presents"] = dict(_PA["presents"], **{modele: False})
            _PA["prochain"] = time.monotonic() + _PA_TTL_OK
            _PA["verifie_le"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            logger.warning("Mistral : %s refusé par le point d'accès UE → point d'accès mondial pour les "
                           "appels suivants.", modele)


def _reinitialiser_point_acces() -> None:
    with _PA_LOCK:
        _PA.update(decision="", verifie=False, presents={}, nombre_modeles=None, erreur="", verifie_le="",
                   prochain=0.0)


def modele_effectif(model: Optional[str] = None, tache: Optional[str] = None) -> str:
    """Modèle appelé EN PREMIER pour une tâche (ou, sans tâche, pour le modèle demandé), vu la table,
    les variables et le forçage : route(tache, model).primaire.modele."""
    try:
        return route(tache, model).primaire.modele
    except Exception:       # noqa: BLE001
        return model or MODEL


# ── Cache de prompt (Anthropic) ─────────────────────────────────────────────────
# Le SDK épinglé (anthropic 0.34) transmet tel quel un bloc {"type": "text", "text": …,
# "cache_control": {"type": "ephemeral"}} (clé inconnue de son type conservée, « ttl » compris) et
# l'API l'accepte sans en-tête bêta. Durée 5 minutes, ou 1 heure (« ttl »: « 1h ») pour les tâches
# dont la route le demande (rédaction : le dossier de l'acheteur commun à toutes les parties).
# Prix (Sonnet 5.5) : écriture 1,25 × l'entrée (5 min) ou 2 × (1 h), lecture 0,05 ×. Longueur minimale
# d'un préfixe mis en cache : 512 tokens (Sonnet 5.5), 1 024 (Sonnet 4.6), 4 096 (Haiku 4.5).
# Mistral ignore le marquage (contenu aplati). Coupure : LLM_PROMPT_CACHE=0.
PROMPT_CACHE = os.getenv("LLM_PROMPT_CACHE", "1").strip().lower() not in ("0", "false", "non", "no")


def cached_text_block(text: str) -> dict:
    """Bloc de texte marqué pour le cache de prompt (préfixe stable : consigne, règlement)."""
    blk = {"type": "text", "text": text or ""}
    if PROMPT_CACHE:
        blk["cache_control"] = {"type": "ephemeral"}
    return blk


def _avec_ttl(req: dict, ttl: str) -> dict:
    """Copie de la requête dont chaque marquage de cache porte la durée demandée (toutes les durées
    identiques : la règle « les plus longues d'abord » est respectée d'office)."""
    def blocs(content):
        if not isinstance(content, list):
            return content
        out = []
        for b in content:
            if isinstance(b, dict) and isinstance(b.get("cache_control"), dict):
                b = dict(b, cache_control={"type": "ephemeral", "ttl": ttl})
            out.append(b)
        return out
    req = dict(req)
    if isinstance(req.get("system"), list):
        req["system"] = blocs(req["system"])
    req["messages"] = [dict(m, content=blocs(m.get("content"))) if isinstance(m, dict) else m
                       for m in (req.get("messages") or [])]
    return req


# ── Réponse normalisée (forme Anthropic) ────────────────────────────────────────

class _Usage:
    __slots__ = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
                 "cache_creation_1h")

    def __init__(self, i, o, cache_read=0, cache_write=0, cache_write_1h=0):
        self.input_tokens = i or 0
        self.output_tokens = o or 0
        self.cache_read_input_tokens = cache_read or 0
        self.cache_creation_input_tokens = cache_write or 0
        self.cache_creation_1h = cache_write_1h or 0


class _Block:
    __slots__ = ("type", "text")

    def __init__(self, text):
        self.type = "text"
        self.text = text or ""


class _Resp:
    """Réponse compatible Anthropic (resp.content[0].text, resp.usage.*, resp.stop_reason) : UN seul
    bloc, le texte de la réponse (blocs de réflexion écartés), quel que soit le fournisseur.
    modele : modèle demandé par la route ; model : modèle renvoyé par le fournisseur quand il le dit
    (c'est son prix qui est compté : cost_meter, budget de l'essai) ; zone : point d'accès Mistral
    réellement utilisé (« ue » : +10 %)."""
    __slots__ = ("content", "usage", "stop_reason", "stop_details", "fournisseur", "modele", "tache",
                 "bascule", "zone", "model")

    def __init__(self, text, usage, stop_reason="end_turn", stop_details=None, fournisseur="", modele="",
                 tache="", zone="", model=None):
        self.content = [_Block(text)]
        self.usage = usage
        self.stop_reason = stop_reason
        self.stop_details = stop_details
        self.fournisseur = fournisseur
        self.modele = modele
        self.tache = tache
        self.bascule = None
        self.zone = zone
        self.model = model


def _int_or_zero(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _champ(obj, nom):
    if isinstance(obj, dict):
        return obj.get(nom)
    return getattr(obj, nom, None)


# Motifs d'arrêt ramenés au contrat Anthropic : « max_tokens » = réponse coupée (seul motif que les
# garde-fous anti-troncature des appelants testent).
_COUPES = {"max_tokens", "length", "model_length", "model_context_window_exceeded"}


def _normaliser_anthropic(resp, modele: str, tache: str) -> _Resp:
    blocs = getattr(resp, "content", None) or []
    texte = "".join(getattr(b, "text", "") or "" for b in blocs
                    if (getattr(b, "type", "text") or "text") == "text")
    stop = getattr(resp, "stop_reason", "") or "end_turn"
    stop = "max_tokens" if stop in _COUPES else stop
    u = getattr(resp, "usage", None)
    cc = _champ(u, "cache_creation") if u is not None else None
    usage = _Usage(_int_or_zero(_champ(u, "input_tokens")), _int_or_zero(_champ(u, "output_tokens")),
                   _int_or_zero(_champ(u, "cache_read_input_tokens")),
                   _int_or_zero(_champ(u, "cache_creation_input_tokens")),
                   _int_or_zero(_champ(cc, "ephemeral_1h_input_tokens")) if cc is not None else 0)
    m_rendu = getattr(resp, "model", None)
    return _Resp(texte, usage, stop, getattr(resp, "stop_details", None), ANTHROPIC, modele, tache,
                 model=m_rendu if isinstance(m_rendu, str) and m_rendu.strip() else None)


def _flatten_content(content) -> str:
    """Le contenu Anthropic peut être une str ou une liste de blocs ; Mistral veut une str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            (b.get("text", "") if isinstance(b, dict) else str(b)) for b in content
        )
    return "" if content is None else str(content)


def _to_openai_messages(system, messages) -> list:
    out = []
    if system:
        out.append({"role": "system", "content": _flatten_content(system)})
    for m in (messages or []):
        out.append({"role": m.get("role", "user"),
                    "content": _flatten_content(m.get("content"))})
    return out


class MistralErreur(RuntimeError):
    def __init__(self, message, status_code=None, corps=""):
        super().__init__(message)
        self.status_code = status_code
        self.corps = corps


def _mistral_create(model=None, max_tokens=1024, temperature=None, system="", messages=None,
                    json_attendu=False, raisonnement="", base_url=None, **_ignored):
    """Appel HTTP de l'API Mistral (compatible OpenAI), ré-emballé en réponse façon Anthropic.
    Point d'accès : UE si le modèle y est servi, sinon mondial (point_acces_mistral). JSON garanti
    dans sa syntaxe par response_format quand la tâche attend du JSON. Reprises sur 429 / 5xx /
    coupure réseau (LLM_MAX_RETRIES)."""
    pa = {"zone": "personnalise", "url": base_url} if base_url else point_acces_mistral()
    modele = model or modele_mistral()
    payload = {"model": modele, "max_tokens": int(max_tokens or 1024),
               "messages": _to_openai_messages(system, messages)}
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if json_attendu:
        payload["response_format"] = {"type": "json_object"}
    if raisonnement:
        payload["reasoning_effort"] = raisonnement
    cle, _nom = _cle_mistral()
    url = pa["url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cle}", "Content-Type": "application/json"}
    r = None
    for essai in range(_MAX_RETRIES + 1):
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        except (httpx.TransportError, httpx.TimeoutException):
            if essai >= _MAX_RETRIES:
                raise
            time.sleep(min(4.0, 0.5 * (2 ** essai)))
            continue
        st = getattr(r, "status_code", 200)
        if isinstance(st, int) and (st == 429 or st >= 500) and essai < _MAX_RETRIES:
            time.sleep(min(4.0, 0.5 * (2 ** essai)))
            continue
        break
    st = getattr(r, "status_code", 200)
    if isinstance(st, int) and st >= 400:
        corps = ""
        try:
            corps = (r.text or "")[:300]
        except Exception:
            pass
        raise MistralErreur(f"Mistral HTTP {st}", st, corps)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    c = (choice.get("message") or {}).get("content")
    if isinstance(c, list):      # modèle qui raisonne : blocs « thinking » écartés, seul le texte compte
        text = "".join(str(x.get("text") or "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    else:
        text = c or ""
    u = data.get("usage") or {}
    pt, ct = _int_or_zero(u.get("prompt_tokens")), _int_or_zero(u.get("completion_tokens"))
    lus = _int_or_zero((u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("num_cached_tokens"))
    fr = choice.get("finish_reason") or "stop"
    if fr == "error":
        raise MistralErreur("Mistral : réponse en erreur", 502, "")
    stop = "max_tokens" if fr in _COUPES else ("end_turn" if fr == "stop" else fr)
    return _Resp(text, _Usage(max(0, pt - lus), ct, cache_read=lus), stop, None, MISTRAL, modele, "",
                 zone=pa.get("zone") or "", model=str(data.get("model") or "") or None)


# ── Compteurs de tokens : global (par process) + PAR TENANT ──────────────────
TOKENS = {"input": 0, "output": 0, "calls": 0}
# Plafond global de tokens cumulés par process. 0 = désactivé.
_TOKEN_HARD_CAP = int(os.getenv("LLM_TOKEN_HARD_CAP", "0"))
# Plafond PAR TENANT (anti « voisin bruyant » : un client ne peut pas épuiser le
# budget des autres). 0 = désactivé. Le tenant courant est porté par un contextvar,
# positionné au début d'un job / d'une requête (cf. tenant_scope).
_TOKEN_CAP_PER_TENANT = int(os.getenv("LLM_TOKEN_CAP_PER_TENANT", "0"))
_TENANT_TOKENS = {}          # tenant_id -> tokens cumulés (borné en nombre de tenants)
_TENANT_TOKENS_MAX = 5000
_CURRENT_TENANT = contextvars.ContextVar("adjugo_tenant", default=None)


class tenant_scope:
    """Délimite le tenant courant pour l'attribution/plafond des tokens IA.
    Usage : `with tenant_scope(user_id): ...`. Sûr en thread (contextvar)."""
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self._token = None

    def __enter__(self):
        self._token = _CURRENT_TENANT.set(self.tenant_id)
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _CURRENT_TENANT.reset(self._token)
        return False


def tenant_usage(tenant_id) -> int:
    return _TENANT_TOKENS.get(tenant_id, 0)


# ── Limite GLOBALE d'appels IA simultanés (process unique, sans Redis) ─────────
# 4 tâches de fond × 6 sections rédigées en parallèle = jusqu'à 24 appels à la fois, plus les
# requêtes directes : de quoi saturer le fournisseur (429 en cascade, disjoncteur ouvert pour
# tous). Un sémaphore de process borne le nombre d'appels EN VOL ; les suivants attendent leur
# tour (au plus LLM_SLOT_WAIT secondes, puis LLMUnavailable → la tâche échoue et le quota est
# remboursé par le mécanisme existant). Réglable : LLM_MAX_CONCURRENT (défaut prudent : 6).
# Sans interblocage : la place n'est tenue QUE pendant l'appel HTTP au fournisseur (jamais
# pendant qu'un appelant attend d'autres appels), et un appel imbriqué dans le même fil
# (réentrance) ne redemande pas de place. Un secours prend sa propre place, après avoir rendu
# celle de l'appel qui a échoué.
_MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "6")))
_SLOT_WAIT = float(os.getenv("LLM_SLOT_WAIT", "300"))
_SLOTS = threading.BoundedSemaphore(_MAX_CONCURRENT)
_SLOT_LOCAL = threading.local()
_INFLIGHT = {"now": 0, "peak": 0, "waits": 0, "timeouts": 0}


def _in_event_loop() -> bool:
    """Vrai si ce fil fait tourner la boucle asyncio du serveur : y attendre une place figerait
    TOUTES les requêtes (process unique) — on n'y attend jamais."""
    try:
        import asyncio
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class _llm_slot:
    """Une place parmi LLM_MAX_CONCURRENT, réentrante dans un même fil."""

    def __enter__(self):
        depth = getattr(_SLOT_LOCAL, "depth", 0)
        if depth == 0:
            if not _SLOTS.acquire(blocking=False):
                with _LOCK:
                    _INFLIGHT["waits"] += 1
                # Filet : un appel fait depuis la boucle d'événements (route async qui aurait
                # oublié run_in_threadpool) n'attend pas — il échoue tout de suite, proprement.
                if _in_event_loop():
                    with _LOCK:
                        _INFLIGHT["timeouts"] += 1
                    logger.warning("Appel IA refusé : aucune place libre, et l'appel vient de la boucle d'événements.")
                    raise LLMUnavailable("Service IA très demandé en ce moment. Réessayez dans quelques minutes.")
                if not _SLOTS.acquire(timeout=_SLOT_WAIT):
                    with _LOCK:
                        _INFLIGHT["timeouts"] += 1
                    logger.warning("Appel IA abandonné : aucune place libre après %ss (%s appels en cours).",
                                   _SLOT_WAIT, _INFLIGHT["now"])
                    raise LLMUnavailable("Service IA très demandé en ce moment. Réessayez dans quelques minutes.")
            with _LOCK:
                _INFLIGHT["now"] += 1
                _INFLIGHT["peak"] = max(_INFLIGHT["peak"], _INFLIGHT["now"])
        _SLOT_LOCAL.depth = depth + 1
        return self

    def __exit__(self, *exc):
        _SLOT_LOCAL.depth -= 1
        if _SLOT_LOCAL.depth == 0:
            with _LOCK:
                _INFLIGHT["now"] -= 1
            _SLOTS.release()
        return False


def concurrency_snapshot() -> dict:
    """Appels IA en vol / plafond / pic / attentes — pour /metrics."""
    with _LOCK:
        return dict(_INFLIGHT, max=_MAX_CONCURRENT)


# ── Noms des salariés masqués avant l'IA (doctrine : ils ne partent jamais) ────
# `with pii_scope(pseudonymiseur):` → tout appel passé dans la portée voit ses textes masqués
# (« Yann Tanguy » → « [Chef de chantier 1] ») et sa réponse remise en clair SANS IA. Voir
# app/services/pii.py. Comme tenant_scope, la portée est un contextvar : les fils d'un
# ThreadPoolExecutor ne l'héritent pas → utiliser map_in_context() ci-dessous. Le masquage est
# fait UNE fois, avant le choix du fournisseur : un secours reçoit la même requête masquée.
_PII = contextvars.ContextVar("adjugo_pii", default=None)


class pii_scope:
    def __init__(self, pseudonymizer):
        active = pseudonymizer is not None and getattr(pseudonymizer, "active", False)
        self.pz = pseudonymizer if active else None
        self._token = None

    def __enter__(self):
        self._token = _PII.set(self.pz) if self.pz is not None else None
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _PII.reset(self._token)
        return False


def _mask_request(pz, kwargs: dict) -> dict:
    """Copie de la requête dont tous les textes (consigne + messages) sont masqués ; ajoute à la
    consigne la règle « recopie les étiquettes » dès qu'une étiquette y figure."""
    kw = dict(kwargs)
    kw["messages"] = [dict(m, content=pz.mask_content(m.get("content"))) if isinstance(m, dict) else m
                      for m in (kwargs.get("messages") or [])]
    system = pz.mask_content(kwargs.get("system") or "")
    flat = _flatten_content(system) + " " + " ".join(
        _flatten_content(m.get("content")) for m in kw["messages"] if isinstance(m, dict))
    if pz.uses_labels(flat):
        hint = pz.hint()
        system = (system + "\n\n" + hint) if isinstance(system, str) else (list(system) + [{"type": "text", "text": hint}])
    if system or "system" in kwargs:
        kw["system"] = system
    return kw


def _unmask_response(pz, resp):
    """Remet les noms en clair dans la réponse (simple remplacement, sans IA)."""
    try:
        for b in (getattr(resp, "content", None) or []):
            if isinstance(getattr(b, "text", None), str):
                b.text = pz.unmask(b.text)
        return resp
    except Exception:
        # Objet non modifiable : on ré-emballe (mêmes attributs que ceux lus par les appelants).
        text = pz.unmask("".join(getattr(b, "text", "") or "" for b in (getattr(resp, "content", None) or [])))
        out = _Resp(text, getattr(resp, "usage", None) or _Usage(0, 0), getattr(resp, "stop_reason", "end_turn"),
                    getattr(resp, "stop_details", None), getattr(resp, "fournisseur", "") or "",
                    getattr(resp, "modele", "") or "", getattr(resp, "tache", "") or "",
                    zone=getattr(resp, "zone", "") or "", model=getattr(resp, "model", None))
        out.bascule = getattr(resp, "bascule", None)
        return out


# ── Coût IA d'un traitement complet (journalisé) ──────────────────────────────────
# `with cost_meter("dossier de réponse", tenant_id):` cumule appels, tokens et coût de tous les
# appels passés dans la portée (fils compris, via map_in_context), puis JOURNALISE le total. Rien
# n'est montré au client.
# Le coût de CHAQUE appel est calculé UNE seule fois, dans _track_usage : au tarif public du modèle
# réellement appelé (celui que renvoie le fournisseur, sinon celui de la route), au point d'accès
# réellement utilisé (Mistral UE : +10 %), cache compris (lecture ; écriture de 5 minutes ou d'une
# heure), secours compris (chaque essai facturé — réponse coupée ou JSON illisible puis secours —
# compte). Ce même montant va au cost_meter ET au relevé du compte facturé (app/services/budget_ia.py :
# budget de l'essai gratuit, alerte des forfaits payants), que l'appel soit ou non dans un cost_meter.
# Seule table des prix : app/services/tarifs_ia.py (Anthropic, Mistral Large 4 soldé puis normal,
# surcoût UE ; un modèle inconnu y est compté au prix du plus cher, jamais sous-estimé).
# Les tokens comptés sont ceux RENVOYÉS par l'API : le découpage propre à chaque modèle (≈ +30 % pour
# Claude 4.7 et suivants par rapport à Sonnet 4.6) y est donc déjà ; estimer_cout() l'applique aux
# estimations faites à partir d'un nombre de caractères.
from app.services import tarifs_ia as _tarifs      # noqa: E402 — la table des prix n'importe pas llm


def prix_mistral(modele: str, jour: Optional[_dt.date] = None) -> Optional[tuple]:
    """(entrée, sortie, cache lu) en $ par million au point d'accès mondial (Large 4 : prix soldé
    jusqu'à MISTRAL_SOLDE_JUSQU_AU, puis normal) ; None si le modèle Mistral n'est pas connu."""
    return _tarifs.prix_mistral(modele, jour)


def prix_modele(modele: str, zone: str = "") -> Optional[dict]:
    """Prix en $ par million de tokens : {entree, sortie, cache_lu, cache_ecrit_5m, cache_ecrit_1h}."""
    return _tarifs.prix_modele(modele, zone)


def cout_usd(modele: str, tin: int, tout: int, cache_lu: int = 0, cache_ecrit: int = 0,
             cache_ecrit_1h: int = 0, zone: str = "") -> Optional[float]:
    """tin = entrée hors cache ; cache_ecrit = TOUS les tokens écrits dans le cache, dont
    cache_ecrit_1h écrits pour une heure. None si le modèle n'a pas de tarif connu (le coût MESURÉ
    d'un appel, lui, compte un modèle inconnu au prix du plus cher : tarifs_ia.cout_usd)."""
    if not _tarifs.connu(modele):
        return None
    return _tarifs.cout_usd(modele, tin, tout, cache_lu, cache_ecrit, cache_ecrit_1h, zone)


CARACTERES_PAR_TOKEN = 3.3      # français, ancien découpage de Claude (hypothèse du comparatif)


def tokens_estimes(caracteres: int, modele: str) -> int:
    """Tokens d'un texte pour un modèle : caractères / 3,3, × 1,3 pour Claude 4.7 et suivants."""
    return int(math.ceil(max(0, caracteres) / CARACTERES_PAR_TOKEN * facteur_decoupage(modele)))


def estimer_cout(modele: str, caracteres_entree: int, tokens_sortie_base: int, caracteres_cache_lus: int = 0,
                 caracteres_cache_ecrits: int = 0, ttl: str = "5m", zone: str = "",
                 tokens_reflexion: int = 0) -> Optional[float]:
    """Estimation (en $) d'un appel à partir de CARACTÈRES : le découpage du modèle est appliqué
    (×1,3 pour Sonnet 5.5) à l'entrée comme à la sortie (tokens_sortie_base au découpage de Sonnet 4.6).
    La réflexion (tokens_reflexion) est facturée comme de la sortie. Hypothèses de la documentation
    (3,3 caractères par token) ; le garde-fou de l'essai, lui, estime plus prudemment
    (budget_ia.estimer*, 3,0 caractères par token)."""
    f = facteur_decoupage(modele)
    ecrits = tokens_estimes(caracteres_cache_ecrits, modele)
    return cout_usd(modele, tokens_estimes(caracteres_entree, modele),
                    int(math.ceil(tokens_sortie_base * f)) + int(tokens_reflexion),
                    tokens_estimes(caracteres_cache_lus, modele), ecrits, ecrits if ttl == "1h" else 0, zone)


_METER = contextvars.ContextVar("adjugo_cost_meter", default=None)


class cost_meter:
    def __init__(self, label: str, tenant_id=None, log: bool = True):
        self.label = label
        self.tenant_id = tenant_id
        self.log = log
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.cache_write_1h_tokens = 0
        self.truncated = 0
        self.fallbacks = 0
        self.by_model = {}
        self._usd = 0.0
        self.sans_tarif = False
        self.provider = ""
        self._parent = None
        self._token = None
        self._t0 = 0.0

    def add(self, model: str, tin: int, tout: int, stop_reason: str = "",
            cache_read: int = 0, cache_write: int = 0, cache_write_1h: int = 0, zone: str = "",
            fallback: bool = False, cout: Optional[float] = None) -> None:
        """tin = tokens d'entrée hors cache ; cache_read / cache_write = tokens d'entrée lus dans
        le cache / écrits dans le cache (dont cache_write_1h pour une heure) ; zone « ue » : point
        d'accès européen de Mistral (+10 %) ; cout : coût de l'appel en $ déjà calculé par
        _track_usage (le même que celui relevé pour le compte facturé), sinon calculé ici."""
        self.calls += 1
        self.input_tokens += tin
        self.output_tokens += tout
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write
        self.cache_write_1h_tokens += cache_write_1h
        if stop_reason == "max_tokens":
            self.truncated += 1
        if fallback:
            self.fallbacks += 1
        key = (model or "?") + ("@ue" if zone == "ue" else "")
        m = self.by_model.setdefault(key, [0, 0, 0, 0, 0, 0])
        m[0] += 1
        m[1] += tin
        m[2] += tout
        m[3] += cache_read
        m[4] += cache_write
        m[5] += cache_write_1h
        if cout is None:
            cout = _tarifs.cout_usd(model, tin, tout, cache_read, cache_write, cache_write_1h, zone)
        self._usd += float(cout or 0.0)
        if not _tarifs.connu(model):
            self.sans_tarif = True
        if self._parent is not None:          # un traitement inclus compte aussi dans l'englobant
            self._parent.add(model, tin, tout, stop_reason, cache_read, cache_write, cache_write_1h, zone, fallback,
                             cout)

    def cost_usd(self):
        """Coût en $ au tarif public du modèle réellement appelé, cumulé appel par appel (zone, cache
        et secours compris ; app/services/tarifs_ia.py). Un modèle sans tarif connu est compté au prix
        du plus cher (jamais sous-estimé) et le journal le signale."""
        return round(self._usd, 5)

    def cost_eur(self):
        return round(self._usd * _tarifs.taux_usd_eur(), 5)

    def fournisseurs(self) -> str:
        fs = sorted({fournisseur_du_modele(k.partition("@")[0]) for k in self.by_model})
        return "+".join(fs) if fs else (forcage() or "aucun")

    def summary(self) -> dict:
        return {"traitement": self.label, "appels": self.calls, "tokens_entree": self.input_tokens,
                "tokens_sortie": self.output_tokens, "tokens_cache_lus": self.cache_read_tokens,
                "tokens_cache_ecrits": self.cache_write_tokens,
                "tokens_cache_ecrits_1h": self.cache_write_1h_tokens, "reponses_coupees": self.truncated,
                "bascules_de_secours": self.fallbacks,
                "cout_estime_usd": self.cost_usd(), "cout_estime_eur": self.cost_eur(),
                "modele_sans_tarif": self.sans_tarif, "fournisseur": self.fournisseurs(),
                "par_modele": {k: {"appels": v[0], "tokens_entree": v[1], "tokens_sortie": v[2],
                                   "tokens_cache_lus": v[3], "tokens_cache_ecrits": v[4],
                                   "tokens_cache_ecrits_1h": v[5]}
                               for k, v in self.by_model.items()},
                "duree_s": round(time.monotonic() - self._t0, 1) if self._t0 else None}

    def __enter__(self):
        self._parent = _METER.get()
        self._token = _METER.set(self)
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, *exc):
        if self._token is not None:
            _METER.reset(self._token)
        if self.log:
            s = self.summary()
            cost = s["cout_estime_usd"]
            logger.info("Coût IA « %s » (espace %s)%s : %d appel(s), %d tokens en entrée (+ %d lus et %d écrits "
                        "dans le cache, dont %d pour 1 h), %d en sortie, %s, %d réponse(s) coupée(s), "
                        "%d bascule(s) de secours, %ss — détail %s",
                        self.label, self.tenant_id, " [échec]" if exc_type else "", s["appels"],
                        s["tokens_entree"], s["tokens_cache_lus"], s["tokens_cache_ecrits"],
                        s["tokens_cache_ecrits_1h"], s["tokens_sortie"],
                        (f"environ {cost:.4f} $" + (" (modèle sans tarif connu : compté au prix du plus cher)"
                                                    if s["modele_sans_tarif"] else "")),
                        s["reponses_coupees"], s["bascules_de_secours"], s["duree_s"], s["par_modele"])
        return False


def map_in_context(executor, fn, items) -> list:
    """executor.map qui PROPAGE les contextvars du fil appelant (espace facturé, noms masqués,
    compteur de coût) à chaque tâche. Chaque tâche reçoit sa propre copie du contexte, prise
    ici, dans le fil appelant (un même Context ne peut pas être entré par deux fils à la fois)."""
    items = list(items)
    ctxs = [contextvars.copy_context() for _ in items]
    return list(executor.map(lambda pair: pair[0].run(fn, pair[1]), zip(ctxs, items)))


# ── Latence des appels IA (histogramme Prometheus) ───────────────────────────
_LAT_BUCKETS = [0.5, 1, 2, 5, 10, 30]
_LAT = {"counts": {b: 0 for b in _LAT_BUCKETS}, "sum": 0.0, "count": 0}


def _record_latency(dt: float) -> None:
    """Histogramme cumulatif (le=bucket) de la durée des appels IA réussis."""
    _LAT["sum"] += dt
    _LAT["count"] += 1
    for b in _LAT_BUCKETS:
        if dt <= b:
            _LAT["counts"][b] += 1


def latency_snapshot() -> dict:
    """Copie cohérente de l'histogramme de latence pour /metrics."""
    with _LOCK:
        return {"buckets": dict(_LAT["counts"]), "sum": _LAT["sum"], "count": _LAT["count"]}


def _modele_reponse(model: str, resp) -> str:
    """Modèle réellement appelé : celui que renvoie le fournisseur (s'il a un tarif connu), sinon
    celui de la route."""
    m = getattr(resp, "model", None)
    if isinstance(m, str) and m.strip() and _tarifs.connu(m):
        return m.strip()
    return model or MODEL


def _track_usage(model: str, resp, ttl: str = "5m", fallback: bool = False):
    """Compteurs (global, par tenant, cost_meter) et coût de l'appel, calculé ICI une seule fois.
    Renvoie le relevé (modèle réel, tokens hors cache, sortie, cache lus, cache écrits, coût en $)
    porté ensuite au compte facturé (_relever_cout), ou None."""
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return None
        tin = _int_or_zero(getattr(u, "input_tokens", 0))
        tout = _int_or_zero(getattr(u, "output_tokens", 0))
        # Cache de prompt : tokens d'entrée lus / écrits dans le cache, comptés À PART de
        # input_tokens par l'API (champs absents du type Usage du SDK 0.34, lus s'ils sont là).
        cr = _int_or_zero(getattr(u, "cache_read_input_tokens", 0))
        cw = _int_or_zero(getattr(u, "cache_creation_input_tokens", 0))
        cw1 = _int_or_zero(getattr(u, "cache_creation_1h", 0))
        if cw and not cw1 and ttl == "1h":
            cw1 = cw              # détail par durée absent : la durée demandée par la route
        used = tin + cr + cw + tout
        TOKENS["input"] += tin + cr + cw
        TOKENS["output"] += tout
        TOKENS["calls"] += 1
        reel = _modele_reponse(model, resp)
        zone = getattr(resp, "zone", "") or ""
        # LE coût de l'appel : modèle réel, point d'accès réel, cache (5 min / 1 h) — compté tel quel
        # au cost_meter et au compte facturé (budget de l'essai).
        cout = _tarifs.cout_usd(reel, tin, tout, cr, cw, cw1, zone)
        meter = _METER.get()
        if meter is not None:
            meter.add(reel, tin, tout, getattr(resp, "stop_reason", "") or "", cr, cw, cw1, zone, fallback, cout)
        tid = _CURRENT_TENANT.get()
        if tid is not None:
            if tid not in _TENANT_TOKENS and len(_TENANT_TOKENS) >= _TENANT_TOKENS_MAX:
                _TENANT_TOKENS.pop(next(iter(_TENANT_TOKENS)), None)   # éviction FIFO bornée
            _TENANT_TOKENS[tid] = _TENANT_TOKENS.get(tid, 0) + used
        return (reel, tin, tout, cr, cw, cout)
    except Exception:
        return None


def _relever_cout(tid, releve) -> None:
    """Coût réel de l'appel (celui que _track_usage a calculé et porté au cost_meter), relevé pour le
    compte facturé, en euros (hors du verrou ; ne lève jamais)."""
    if not releve:
        return
    try:
        from app.services import budget_ia
        reel, tin, tout, cr, cw, cout = releve
        budget_ia.enregistrer_appel(tid, reel, round(float(cout or 0.0) * _tarifs.taux_usd_eur(), 6),
                                    tin + cr + cw, tout)
    except Exception as e:      # noqa: BLE001 — la mesure ne casse jamais un appel réussi
        logger.warning("Relevé du coût IA impossible : %s", type(e).__name__)


# ── Disjoncteurs (circuit breaker) PAR FOURNISSEUR + PAR TENANT ──────────────
# Par fournisseur : après N échecs consécutifs (panne API), on ouvre le circuit pendant un
# cooldown → échec rapide (ou bascule directe vers le secours). Un succès le referme. _CB est
# celui d'Anthropic (nom historique, lu par /metrics) ; Mistral a le sien : une panne de l'un
# n'arrête jamais l'autre.
# Par tenant : un client dont LES appels échouent (entrées pathologiques) voit SON
# circuit s'ouvrir, sans pénaliser les autres — isolation « voisin bruyant » au niveau
# résilience, pas seulement coût.
_CB = {"fails": 0, "open_until": 0.0}
_CB_MISTRAL = {"fails": 0, "open_until": 0.0}
_CB_THRESHOLD = int(os.getenv("LLM_CB_THRESHOLD", "5"))
_CB_COOLDOWN = float(os.getenv("LLM_CB_COOLDOWN", "30"))
_TENANT_CB = {}          # tenant_id -> {"fails": int, "open_until": float}  (borné)
_TENANT_CB_MAX = 5000
_TCB_THRESHOLD = int(os.getenv("LLM_TENANT_CB_THRESHOLD", "4"))


def _cb(fournisseur: str) -> dict:
    return _CB_MISTRAL if fournisseur == MISTRAL else _CB


def _tenant_cb(tid):
    cb = _TENANT_CB.get(tid)
    if cb is None:
        if len(_TENANT_CB) >= _TENANT_CB_MAX:
            _TENANT_CB.pop(next(iter(_TENANT_CB)), None)
        cb = _TENANT_CB[tid] = {"fails": 0, "open_until": 0.0}
    return cb


def _cb_echec(fournisseur: str, now: float) -> None:
    with _LOCK:
        cb = _cb(fournisseur)
        cb["fails"] += 1
        if cb["fails"] >= _CB_THRESHOLD and cb["open_until"] <= now:
            cb["open_until"] = time.monotonic() + _CB_COOLDOWN
            logger.error("Disjoncteur IA %s ouvert après %s échecs — pause %ss.", fournisseur, cb["fails"], _CB_COOLDOWN)


def _cb_succes(fournisseur: str) -> None:
    cb = _cb(fournisseur)
    if cb["fails"]:
        logger.info("Disjoncteur IA %s refermé (appel réussi après %s échecs).", fournisseur, cb["fails"])
    cb["fails"] = 0
    cb["open_until"] = 0.0


def _tenant_echec(tid, now: float) -> None:
    if tid is None:
        return
    with _LOCK:
        tcb = _tenant_cb(tid)
        tcb["fails"] += 1
        if tcb["fails"] >= _TCB_THRESHOLD and tcb["open_until"] <= now:
            tcb["open_until"] = time.monotonic() + _CB_COOLDOWN
            logger.warning("Disjoncteur IA ouvert pour le tenant %s après %s échecs.", tid, tcb["fails"])


# ── Appel d'un fournisseur ───────────────────────────────────────────────────

def _thinking_pour(modele: str, reg: Reglages) -> Optional[dict]:
    """Réglage de réflexion envoyé (Claude 5.x seulement ; jamais aux anciens modèles)."""
    if not _nouvelle_generation(modele) or reg.reflexion != "between_tools":
        return None          # « adaptive » = réglage par défaut des modèles 5.x : rien à envoyer
    if reg.effort in ("xhigh", "max"):
        return None          # between_tools / disabled refusés à ces niveaux (400) → adaptatif
    v = _version_claude(modele)
    fam, ver = v
    if fam == "sonnet" and ver >= (5, 5):
        return {"type": "between_tools"}        # Sonnet 5.5 refuse « disabled »
    if (fam, ver) in (("haiku", (5, 5)), ("sonnet", (5, 0)), ("opus", (5, 0))):
        return {"type": "disabled"}
    return None


def plafond_sortie(cible: Cible, r: Route, max_tokens, relance_coupe: bool = False) -> int:
    """max_tokens RÉELLEMENT envoyé au fournisseur de `cible` pour la route `r` : découpage du modèle
    (× 1,3 pour Claude 4.7 et suivants et pour Mistral), réserve de réflexion quand elle est active
    (elle compte dans max_tokens), double pour la relance d'une réponse coupée, borné par
    LLM_MAX_SORTIE. Le même calcul sert à l'appel et aux estimations du garde-fou de l'essai."""
    modele = cible.modele
    mt = _int_or_zero(max_tokens) or 1024
    if cible.fournisseur == MISTRAL:
        reg = r.reglages(MISTRAL)
        mt = int(math.ceil(mt * _facteur_plafond(modele))) + (max(0, reg.reserve_reflexion) if reg.raisonnement else 0)
    elif _nouvelle_generation(modele):
        reg = r.reglages(ANTHROPIC)
        mt = int(math.ceil(mt * facteur_decoupage(modele)))
        if _thinking_pour(modele, reg) is None and _version_claude(modele)[1] >= (5, 0):
            # Réflexion adaptative (réglage par défaut des modèles 5.x) : elle compte dans max_tokens.
            mt += max(0, reg.reserve_reflexion) or 4000
    if relance_coupe:
        mt *= 2
    return max(1, min(mt, _MAX_SORTIE))


def _requete_anthropic(cible: Cible, r: Route, kwargs: dict, relance_coupe: bool) -> dict:
    req = dict(kwargs)
    modele = cible.modele
    req["model"] = modele
    reg = r.reglages(ANTHROPIC)
    if _nouvelle_generation(modele):
        for p in ("temperature", "top_p", "top_k"):
            req.pop(p, None)                 # Sonnet 5.5 : toute valeur → erreur 400
        th = _thinking_pour(modele, reg)
        extra = dict(req.pop("extra_body", None) or {})
        if th is not None:
            extra["thinking"] = th
        if reg.effort in _EFFORTS:
            extra["output_config"] = dict(extra.get("output_config") or {}, effort=reg.effort)
        if extra:
            req["extra_body"] = extra
    req["max_tokens"] = plafond_sortie(Cible(ANTHROPIC, modele), r, kwargs.get("max_tokens"), relance_coupe)
    if reg.cache_ttl == "1h" and PROMPT_CACHE:
        req = _avec_ttl(req, "1h")
    return req


def _appel_anthropic(cible: Cible, r: Route, kwargs: dict, relance_coupe: bool) -> _Resp:
    req = _requete_anthropic(cible, r, kwargs, relance_coupe)
    resp = client().messages.create(**req)
    return _normaliser_anthropic(resp, cible.modele, r.tache)


def _appel_mistral(cible: Cible, r: Route, kwargs: dict, json_attendu: bool, relance_coupe: bool) -> _Resp:
    reg = r.reglages(MISTRAL)
    mt = plafond_sortie(Cible(MISTRAL, cible.modele), r, kwargs.get("max_tokens"), relance_coupe)
    temp = kwargs.get("temperature")
    resp = _mistral_create(model=cible.modele, max_tokens=mt, temperature=temp,
                           system=kwargs.get("system") or "", messages=kwargs.get("messages") or [],
                           json_attendu=json_attendu, raisonnement=reg.raisonnement)
    resp.tache = r.tache
    return resp


def _motif_exception(e: Exception) -> str:
    st = getattr(e, "status_code", None)
    if st is None:
        st = getattr(getattr(e, "response", None), "status_code", None)
    if st in (400, 404, 422):
        return "modele"
    return "panne"


def _modele_inconnu(e: Exception) -> bool:
    """Réponse Mistral « modèle inconnu » (et non une autre erreur de requête)."""
    if getattr(e, "status_code", None) == 404:
        return True
    corps = (getattr(e, "corps", "") or "").lower()
    return "invalid_model" in corps or ("model" in corps and any(
        x in corps for x in ("not found", "invalid model", "does not exist", "unknown model", "not available")))


def _json_valide(texte: str) -> bool:
    try:
        parse_json(texte)
        return True
    except Exception:
        return False


_MSG_INDISPONIBLE = "Service IA temporairement indisponible (circuit global ouvert). Réessayez sous peu."
_MSG_ABSENT = "Service IA non configuré pour le moment. Réessayez plus tard."
_MSG_REFUS = "L'IA n'a pas pu traiter cette demande. Réessayez ou reformulez-la."


def _essayer(cible: Cible, r: Route, kwargs: dict, json_attendu: bool, relance_coupe: bool, est_secours: bool):
    """Un essai chez un fournisseur. Renvoie (état, réponse, exception, compte_pour_l_espace) ;
    état : « ok » | « absent » | « panne » | « modele » | « coupe » | « json » | « refus »."""
    f = cible.fournisseur
    if not _disponible(f):
        return "absent", None, LLMUnavailable(_MSG_ABSENT), False
    now = time.monotonic()
    if _cb(f)["open_until"] > now:
        return "panne", None, LLMUnavailable(_MSG_INDISPONIBLE), False
    t0 = time.monotonic()
    try:
        # Place limitée tenue pendant le SEUL appel au fournisseur (LLMUnavailable si aucune ne
        # se libère : levée avant d'avoir appelé, elle ne compte pas comme une panne ci-dessous).
        with _llm_slot():
            t0 = time.monotonic()
            if f == MISTRAL:
                resp = _appel_mistral(cible, r, kwargs, json_attendu, relance_coupe)
            else:
                resp = _appel_anthropic(cible, r, kwargs, relance_coupe)
    except LLMUnavailable:
        raise
    except Exception as e:       # noqa: BLE001 — classé, compté, puis secours ou propagation
        dt = time.monotonic() - t0
        motif = _motif_exception(e)
        if f == MISTRAL and motif == "modele" and _modele_inconnu(e):
            _marquer_absent_ue(cible.modele)
        _cb_echec(f, now)
        qualite.noter_appel(f, r.tache, cible.modele, dt, "erreur")
        return motif, None, e, True
    dt = time.monotonic() - t0
    coupee = resp.stop_reason == "max_tokens"
    refus = resp.stop_reason == "refusal"
    jinv = bool(json_attendu and not coupee and not refus and not _json_valide(resp.content[0].text))
    with _LOCK:
        _cb_succes(f)
        _record_latency(dt)
        releve = _track_usage(cible.modele, resp, r.reglages(f).cache_ttl if f == ANTHROPIC else "5m", est_secours)
    # Tout essai facturé (réussi, coupé, JSON illisible, refusé ; principal ou secours) est relevé pour
    # le compte facturé, au même coût que celui du cost_meter : le budget de l'essai compte tout.
    _relever_cout(_CURRENT_TENANT.get(), releve)
    qualite.noter_appel(f, r.tache, cible.modele, dt, "refus" if refus else "ok", coupee, jinv)
    qualite.marquer_dernier(f, r.tache)
    if refus:
        return "refus", resp, LLMRefus(_MSG_REFUS), False
    if coupee:
        return "coupe", resp, None, False
    if jinv:
        return "json", resp, None, False
    return "ok", resp, None, False


def messages_create(tache: Optional[str] = None, json_attendu: Optional[bool] = None, **kwargs):
    """Point d'entrée CENTRAL vers l'IA : route de la tâche, secours croisé, disjoncteurs
    (fournisseur + tenant), plafonds (global ET par tenant), noms masqués, suivi de l'usage et de
    la qualité. Tous les appels passent par ici.
    tache : nom de la tâche (TACHES) — sans tâche, le modèle demandé (`model=`) chez son fournisseur.
    json_attendu : la réponse doit être un JSON (défaut : ce que dit la route)."""
    now = time.monotonic()
    tid = _CURRENT_TENANT.get()
    if tid is not None and _TENANT_CB.get(tid, {}).get("open_until", 0.0) > now:
        raise LLMUnavailable("Service IA momentanément indisponible pour votre espace. Réessayez sous peu.")
    if _TOKEN_HARD_CAP and (TOKENS["input"] + TOKENS["output"]) >= _TOKEN_HARD_CAP:
        logger.error("Plafond de tokens IA GLOBAL atteint (%s) — appels refusés.", _TOKEN_HARD_CAP)
        raise LLMUnavailable("Plafond de tokens IA atteint pour ce processus.")
    if _TOKEN_CAP_PER_TENANT and tid is not None and _TENANT_TOKENS.get(tid, 0) >= _TOKEN_CAP_PER_TENANT:
        logger.warning("Plafond de tokens IA atteint pour le tenant %s (%s) — appel refusé.",
                       tid, _TOKEN_CAP_PER_TENANT)
        raise LLMUnavailable("Plafond de tokens IA atteint pour votre espace. Réessayez plus tard.")
    pz = _PII.get()
    if pz is not None:
        kwargs = _mask_request(pz, kwargs)      # aucun nom de salarié ne part au fournisseur (secours compris)
    r = route(tache, kwargs.get("model"))
    jatt = r.json if json_attendu is None else bool(json_attendu)
    essais = [r.primaire] + ([r.secours] if r.secours is not None else [])
    repli, motif_prec, bascule = None, "", None
    erreur_reelle, erreur_autre = None, None      # exception d'un vrai appel / d'un essai sans appel
    for i, cible in enumerate(essais):
        etat, resp, exc, appel_reel = _essayer(cible, r, kwargs, jatt, i > 0 and motif_prec == "coupe", i > 0)
        if etat == "ok":
            with _LOCK:
                if tid is not None and tid in _TENANT_CB:
                    _TENANT_CB[tid]["fails"] = 0
                    _TENANT_CB[tid]["open_until"] = 0.0
            resp.bascule = bascule
            return _unmask_response(pz, resp) if pz is not None else resp
        if resp is not None and etat in ("coupe", "json"):
            repli = resp                          # exploitable par l'appelant si le secours échoue
        if exc is not None:
            if appel_reel:
                erreur_reelle = exc
            elif erreur_autre is None:
                erreur_autre = exc
        sec = r.secours
        if (i == 0 and sec is not None and etat in r.secours_sur and _disponible(sec.fournisseur)
                and _cb(sec.fournisseur)["open_until"] <= time.monotonic()):
            # Bascule : même requête (déjà masquée), mêmes garde-fous en aval ; seul le fournisseur change.
            detail = ("" if exc is None else type(exc).__name__)
            qualite.noter_bascule(r.tache, cible.fournisseur, sec.fournisseur, etat, detail, cible.modele, sec.modele)
            motif_prec, bascule = etat, etat
            continue
        break
    if repli is not None:
        repli.bascule = bascule
        return _unmask_response(pz, repli) if pz is not None else repli
    if erreur_reelle is not None:
        _tenant_echec(tid, now)
        raise erreur_reelle
    raise erreur_autre if erreur_autre is not None else LLMUnavailable(_MSG_INDISPONIBLE)


def complete_ex(system: str, user, max_tokens: int = 3000, temperature: float = 0.2,
                model: Optional[str] = None, tache: Optional[str] = None,
                json_attendu: Optional[bool] = None) -> tuple:
    """Comme complete() mais renvoie (texte, stop_reason) : permet à l'appelant de détecter
    une réponse TRONQUÉE (stop_reason == "max_tokens") au lieu de la prendre pour complète.
    `user` : texte, ou liste de blocs (dont un bloc mis en cache)."""
    resp = messages_create(
        tache=tache,
        json_attendu=json_attendu,
        model=model or MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip(), getattr(resp, "stop_reason", "end_turn")


def complete(system: str, user, max_tokens: int = 3000, temperature: float = 0.2,
             model: Optional[str] = None, tache: Optional[str] = None,
             json_attendu: Optional[bool] = None) -> str:
    """Appel texte simple. Retourne le texte de la réponse."""
    return complete_ex(system, user, max_tokens=max_tokens, temperature=temperature, model=model,
                       tache=tache, json_attendu=json_attendu)[0]


def complete_json(system: str, user, max_tokens: int = 3000, temperature: float = 0.2,
                  tache: Optional[str] = None) -> dict:
    """Appel attendant un JSON. Nettoie les fences markdown et parse robustement."""
    raw = complete(system, user, max_tokens=max_tokens, temperature=temperature, tache=tache, json_attendu=True)
    return parse_json(raw)


def parse_json(raw: str) -> dict:
    """Parse un JSON potentiellement entouré de ```json ... ``` ou de texte."""
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Dernier recours : décoder le PREMIER objet équilibré à partir du premier « { »
        # (raw_decode s'arrête à la fin de l'objet), au lieu d'un regex greedy `\{.*\}` qui
        # sur-capture jusqu'à la dernière accolade (et échoue dès qu'il y a du texte après).
        start = text.find("{")
        if start != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[start:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Réponse LLM non JSON: {raw[:200]}")


# ── État des fournisseurs, pages juridiques, diagnostic d'administration ──────

def fournisseurs_utilises() -> dict:
    """Fournisseurs qui peuvent RECEVOIR des données avec la configuration actuelle (tâche principale
    ou secours), et pour quoi. Aucun réseau."""
    out = {ANTHROPIC: {"principal": [], "secours": []}, MISTRAL: {"principal": [], "secours": []}}
    for t in TACHES:
        r = route(t)
        if _disponible(r.primaire.fournisseur) or r.primaire.fournisseur == ANTHROPIC:
            out[r.primaire.fournisseur]["principal"].append(t)
        if r.secours is not None and _disponible(r.secours.fournisseur):
            out[r.secours.fournisseur]["secours"].append(t)
    if not _use_mistral():
        out[MISTRAL] = {"principal": [], "secours": []}
    return out


def etat_juridique(verifier: bool = True) -> dict:
    """Ce que les pages juridiques doivent dire du traitement par l'IA (sans aucune clé)."""
    fu = fournisseurs_utilises()
    mistral = bool(fu[MISTRAL]["principal"] or fu[MISTRAL]["secours"])
    anthropic = bool(fu[ANTHROPIC]["principal"] or fu[ANTHROPIC]["secours"]) or not mistral
    pa = point_acces_mistral(verifier=verifier) if mistral else None
    return {"anthropic": anthropic, "mistral": mistral, "mistral_zone": (pa or {}).get("zone", ""),
            "mistral_url": (pa or {}).get("url", ""),
            "mistral_entrainement_desactive": bool(getattr(settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", False)),
            "taches": fu}


def active_provider() -> dict:
    """Résumé public (sans secret) — /api/llm/info."""
    fu = fournisseurs_utilises()
    actifs = [f for f in (ANTHROPIC, MISTRAL) if fu[f]["principal"] or fu[f]["secours"]] or [ANTHROPIC]
    labels = {ANTHROPIC: "Claude (Anthropic)", MISTRAL: "Mistral Large (Mistral AI)"}
    return {"provider": actifs[0] if len(actifs) == 1 else "mixte", "fournisseurs": actifs,
            "routage": routage_mode(), "label": " et ".join(labels[f] for f in actifs),
            "sovereign": False, "model": route("redaction").primaire.modele,
            "model_fast": route("questions").primaire.modele}


def resume_routage() -> list:
    """Phrases du journal de démarrage (aucune clé, aucun réseau)."""
    lignes = []
    _v, nom = _cle_mistral()
    mode = routage_mode()
    fz = forcage()
    if mode == "ancien":
        lignes.append("IA — ANCIEN routage (LLM_ROUTAGE=ancien) : Claude Sonnet 4.6 et Haiku 4.5, sans secours.")
    else:
        par = {}
        for t in TACHES:
            r = route(t)
            par.setdefault(f"{r.primaire.fournisseur}:{r.primaire.modele}", []).append(t)
        lignes.append("IA — routage par tâche : " + " ; ".join(f"{k} ← {', '.join(v)}" for k, v in par.items()))
    if fz:
        lignes.append(f"IA — LLM_PROVIDER={fz} : TOUTES les tâches partent chez {fz} (routage par tâche et "
                      "secours désactivés).")
    if nom:
        lignes.append(f"IA — clé Mistral lue dans {nom}."
                      + ("" if nom == "MISTRAL_API_KEY_ADJUGO" else " (nom historique, accepté par compatibilité)"))
        if not getattr(settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", False):
            lignes.append("IA — ATTENTION : désinscription de l'entraînement chez Mistral non confirmée "
                          "(MISTRAL_ENTRAINEMENT_DESACTIVE) ; les pages juridiques le disent.")
    else:
        lignes.append("IA — aucune clé Mistral : les tâches routées vers Mistral partent chez Claude (secours).")
    return lignes


def diagnostic(verifier: bool = True) -> dict:
    """Diagnostic d'administration : SANS JAMAIS afficher de clé (ni valeur, ni extrait, ni longueur)."""
    cle_m, nom_m = _cle_mistral()
    cle_a = bool((settings.ANTHROPIC_API_KEY or "").strip())
    mode = routage_mode()
    fz = forcage()
    now = time.monotonic()
    messages = []
    if fz:
        messages.append(f"LLM_PROVIDER={fz} : toutes les tâches partent chez {fz} ; le routage par tâche et les "
                        "secours croisés sont désactivés. Retirez la variable (ou mettez « auto ») pour les rétablir.")
    if mode == "ancien":
        messages.append("LLM_ROUTAGE=ancien : ancien routage (Claude Sonnet 4.6 et Haiku 4.5, réglages d'origine, "
                        "aucun secours). Retirez la variable pour revenir au routage par tâche.")
    if not cle_a:
        messages.append("Clé Anthropic absente (ANTHROPIC_API_KEY) : questions et rédaction impossibles.")
    pa = point_acces_mistral(verifier=verifier) if cle_m else None
    if cle_m:
        if nom_m == "MISTRAL_API_KEY":
            messages.append("Clé Mistral lue dans MISTRAL_API_KEY (nom historique) : préférez MISTRAL_API_KEY_ADJUGO.")
        if not getattr(settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", False):
            messages.append("Désinscription de l'entraînement chez Mistral NON confirmée : désactivez « Anonymous "
                            "improvement data » (console Mistral, Admin > Privacy), puis posez "
                            "MISTRAL_ENTRAINEMENT_DESACTIVE=1. Tant que ce n'est pas fait, les pages juridiques le disent "
                            "et dpa.html / securite.html restent à corriger (docs/IA_FOURNISSEURS_PAGES_JURIDIQUES.md).")
        if pa and pa.get("zone") == "mondial":
            messages.append("Mistral passe par le point d'accès MONDIAL (api.mistral.ai) : " + pa.get("raison", ""))
    else:
        messages.append("Aucune clé Mistral (MISTRAL_API_KEY_ADJUGO) : les tâches routées vers Mistral partent chez "
                        "Claude Sonnet 5.5 (secours).")
    autres = [n for n in _NOMS_CLE_MISTRAL if (getattr(settings, n, "") or "").strip() and n != nom_m]
    if autres:
        messages.append(f"{', '.join(autres)} est aussi renseignée mais n'est pas lue ({nom_m} a la priorité).")
    taches = []
    for t in TACHES:
        r = route(t)
        effectif = r.primaire
        raison = ""
        if not _disponible(r.primaire.fournisseur):
            effectif, raison = (r.secours, "secours : fournisseur principal non configuré") if (
                r.secours and "absent" in r.secours_sur and _disponible(r.secours.fournisseur)) else (None, "aucun fournisseur")
        elif _cb(r.primaire.fournisseur)["open_until"] > now:
            effectif, raison = (r.secours, "secours : disjoncteur du fournisseur principal ouvert") if r.secours else (
                None, "disjoncteur ouvert")
        reg = r.reglages(r.primaire.fournisseur)
        taches.append({
            "tache": t, "libelle": r.libelle, "origine": r.origine,
            "fournisseur": r.primaire.fournisseur, "modele": r.primaire.modele,
            "reglages": {"reflexion": reg.reflexion or "réglage du modèle", "effort": reg.effort or "réglage du modèle",
                         "cache": reg.cache_ttl if r.primaire.fournisseur == ANTHROPIC else "non utilisé",
                         "json": r.json},
            "secours": ({"fournisseur": r.secours.fournisseur, "modele": r.secours.modele,
                         "si": [MOTIFS[m] for m in sorted(r.secours_sur)]} if r.secours else None),
            "part_maintenant_chez": ({"fournisseur": effectif.fournisseur, "modele": effectif.modele}
                                     if effectif is not None else None),
            "note": raison,
        })
    with _PA_LOCK:
        verif = dict(_PA)
    verif.pop("prochain", None)
    return {
        "routage": mode, "forcage_llm_provider": fz or None,
        "fournisseurs": {
            ANTHROPIC: {"configure": cle_a, "variable": "ANTHROPIC_API_KEY" if cle_a else None,
                        "disjoncteur": "ouvert" if _CB["open_until"] > now else "fermé",
                        "echecs_consecutifs": _CB["fails"]},
            MISTRAL: {"configure": bool(cle_m), "variable": nom_m or None,
                      "variables_acceptees": list(_NOMS_CLE_MISTRAL),
                      "point_acces": pa, "verification_ue": verif if cle_m else None,
                      "large4_sur_ue": ((verif.get("presents") or {}).get(modele_mistral()) if cle_m else None),
                      "entrainement_desinscription_confirmee": bool(getattr(settings, "MISTRAL_ENTRAINEMENT_DESACTIVE",
                                                                            False)),
                      "disjoncteur": "ouvert" if _CB_MISTRAL["open_until"] > now else "fermé",
                      "echecs_consecutifs": _CB_MISTRAL["fails"]},
        },
        "taches": taches,
        "secours": {"actifs": _secours_actif() and not fz and mode != "ancien",
                    "derniere_bascule": qualite.derniere_bascule() or None,
                    "bascules": qualite.instantane()["bascules"]},
        "messages": messages,
    }
