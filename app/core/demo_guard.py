"""
Compte démo public = « vitrine en lecture guidée » (décision fondateur, audit cyber oct. 2026).

Le compte démo (demo@adjugo.fr) s'ouvre en un clic, sans mot de passe : n'importe qui en
détient une session. Il garde tout l'affichage et les interactions SANS COÛT (navigation,
simulation de groupement, filtres, chiffrage manuel, CERFA…), mais ne peut plus :
  (a) faire envoyer un email (invitations partenaire / équipe, relances, changement d'email…),
  (b) téléverser un fichier,
  (c) lancer un appel IA payant (hors analyses canned des marchés DEMO-),
  (d) supprimer le compte, toucher à l'abonnement, à l'équipe ou à l'organisation,
  (e) abîmer la vitrine PARTAGÉE entre les présentations : supprimer ou modifier un marché (seul le
      changement d'étape reste permis), un document, le profil entreprise, les critères, les
      partenaires et leurs rattachements aux marchés. Entre deux présentations, la vitrine est en
      plus recréée automatiquement (app/services/demo_remise.py).

Mise en œuvre CENTRALE : un middleware (enregistré dans app/main.py) consulte une liste
explicite de (méthode, motif de route). Seules les requêtes qui tombent dans cette liste
sont examinées : on identifie alors le porteur du Bearer avec les fonctions d'auth
existantes (lecture seule) et on renvoie 403 si c'est le compte démo. Toute autre requête
passe sans aucun coût supplémentaire. Défense en profondeur : consume_analysis et exiger_ia
(quota.py, appelés avant tout appel IA) refusent aussi le compte démo (les analyses DEMO- ne
passent jamais par là) ; llm.messages_create refuse tout appel fait dans l'espace du compte démo ;
refuser_demo() est posé dans les routes qui téléversent, envoient un email ou écrivent chez un
tiers. La liste complète des routes à coût et la preuve qu'aucune ne coûte rien à la démo :
tests/test_demo_sans_cout.py (toute nouvelle route d'écriture doit y être classée).
"""
import hashlib
import hmac
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("adjugo")


def demo_public() -> bool:
    """Démo publique sans mot de passe : FERMÉE par défaut (décision fondateur, 08/10/2026 :
    « aucun concurrent ne montre son logiciel comme ça » → parcours « demander un accès »).
    Réactivable sans code via DEMO_PUBLIC=1. Fermée, les routes de connexion démo répondent
    404 et toute session démo déjà ouverte est refusée (401)."""
    return os.getenv("DEMO_PUBLIC", "").strip().lower() in ("1", "true", "yes", "oui")


# ── Lien privé de démonstration (13/10/2026) ─────────────────────────────────────────────
# La démo reste fermée au public ; Eliot la redonne à qui il veut (Mathys, prospection) par un
# lien https://adjugo.pro/demo#<clé>. La clé est dans le FRAGMENT : le navigateur ne l'envoie
# jamais au serveur dans l'adresse (ni journaux d'accès, ni Referer) ; la page /demo la lit,
# l'efface de la barre d'adresse et l'envoie dans le CORPS d'un POST. Voir docs/DEMO_LIEN_PRIVE.md.
#
# Révocation : une session ouverte par le lien porte l'empreinte de la clé (revendication
# « dl » du jeton). Elle n'est acceptée que si cette empreinte est celle de la clé ACTUELLE :
# changer ou retirer DEMO_LIEN_CLE coupe toutes les sessions ouvertes avec l'ancienne clé.
# Les sessions ouvertes par DEMO_PUBLIC=1 (sans « dl ») gardent leur comportement.
# La clé n'est JAMAIS journalisée : le corps des requêtes ne part pas chez Sentry, et la valeur
# exacte de la clé est masquée dans tout journal (app.core.redact).
DEMO_LIEN_MIN = 32      # en dessous, la clé est ignorée : lien fermé
DEMO_LIEN_CLAIM = "dl"


def demo_lien_cle() -> str:
    """Clé du lien privé (DEMO_LIEN_CLE), ou "" si absente ou trop courte (lien fermé)."""
    v = (os.getenv("DEMO_LIEN_CLE") or "").strip()
    return v if len(v) >= DEMO_LIEN_MIN else ""


def _empreinte(cle: str) -> str:
    """16 premiers caractères d'un HMAC-SHA256 de la clé (clé du HMAC : SECRET_KEY). Elle ne
    permet pas de retrouver la clé et ne se fabrique pas sans SECRET_KEY."""
    from app.core.config import get_settings
    k = (get_settings().SECRET_KEY or "").encode("utf-8")
    return hmac.new(k, b"adjugo-demo-lien:" + cle.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def demo_lien_empreinte() -> str:
    """Empreinte de la clé ACTUELLE, ou "" si le lien est fermé."""
    cle = demo_lien_cle()
    return _empreinte(cle) if cle else ""


def demo_lien_valide(cle) -> bool:
    """Vrai si `cle` est la clé du lien privé (comparaison à temps constant). Lien fermé
    (variable absente ou trop courte), clé vide ou d'un autre type : False."""
    attendue = demo_lien_cle()
    if not attendue or not isinstance(cle, str):
        return False
    fournie = cle.strip()
    if not fournie:
        return False
    # Sur des octets : compare_digest sur des chaînes non ASCII lève TypeError.
    return hmac.compare_digest(fournie.encode("utf-8"), attendue.encode("utf-8"))


def demo_ouverture(cle) -> Optional[dict]:
    """Revendications à ajouter au jeton d'une session démo, ou None si la démo ne s'ouvre
    pas (les routes répondent alors 404, comme une démo fermée : rien ne révèle le lien).
    Clé valide → session « lien privé » (révocable) ; sinon démo publique si DEMO_PUBLIC=1."""
    if demo_lien_valide(cle):
        return {DEMO_LIEN_CLAIM: demo_lien_empreinte()}
    if demo_public():
        return {}
    return None


def demo_lien_jeton_valide(payload: dict) -> bool:
    """Jeton ouvert par le lien privé : son empreinte est-elle celle de la clé ACTUELLE ?"""
    dl = (payload or {}).get(DEMO_LIEN_CLAIM)
    actuelle = demo_lien_empreinte()
    if not actuelle or not isinstance(dl, str) or not dl:
        return False
    return hmac.compare_digest(dl.encode("utf-8"), actuelle.encode("utf-8"))


def demo_session_valide(payload: dict) -> bool:
    """Une session du compte démo (PME ou collectivités) est-elle encore acceptée ?
    Ouverte par le lien privé (revendication « dl ») : seulement si la clé n'a pas changé.
    Ouverte autrement (démo publique) : seulement si la démo publique est ouverte."""
    if (payload or {}).get(DEMO_LIEN_CLAIM):
        return demo_lien_jeton_valide(payload)
    return demo_public()


DEMO_LIEN_PERIME = "Ce lien de démonstration n'est plus valide."

_ID = r"[^/]+"


def _p(path: str) -> "re.Pattern":
    """Motif de route FastAPI → regex ancrée ({param} = un segment, « / » final optionnel)."""
    rx = re.sub(r"\{[^}]+\}", _ID, path.rstrip("/"))
    return re.compile(rf"^{rx}/?$")


# (méthode, motif, action affichée : « commencez votre essai gratuit de 30 jours pour <action> »)
_BLOCKED = [
    # (a) envois d'emails
    ("POST",   "/api/projects/{pid}/invites",                 "inviter un partenaire"),
    ("POST",   "/api/projects/{pid}/invites/{iid}/resend",    "relancer un partenaire"),
    ("DELETE", "/api/projects/{pid}/invites/{iid}",           "retirer un partenaire"),     # mail « accès retiré »
    ("POST",   "/api/projects/{pid}/offre/figer",             "figer l'offre commune"),     # prévient les partenaires
    # Convention de groupement (vague 2) : toutes les écritures (la génération envoie aussi
    # « convention à valider » aux partenaires ; la vitrine partagée ne doit pas changer).
    ("PUT",    "/api/projects/{pid}/groupement/convention",            "monter un groupement"),
    ("POST",   "/api/projects/{pid}/groupement/convention/relire-dce", "monter un groupement"),
    ("POST",   "/api/projects/{pid}/groupement/convention/generer",    "monter un groupement"),
    ("POST",   "/api/projects/{pid}/groupement/convention/valider",    "monter un groupement"),
    ("POST",   "/api/projects/{pid}/groupement/convention/hors-ligne/{lid}", "monter un groupement"),
    # Composition retenue et offre figée du groupement de la vitrine : les défaire (ou retenir une
    # autre composition) rendrait caduque la convention validée par tous, pour chaque visiteur.
    ("POST",   "/api/projects/{pid}/groupement/retenir",       "monter un groupement"),
    ("DELETE", "/api/projects/{pid}/groupement/plan",          "monter un groupement"),
    ("DELETE", "/api/projects/{pid}/offre/figer",              "monter un groupement"),
    # Réseau de partenaires (vague 3) : la démo ne publie rien, n'invite personne du réseau et
    # ne voit aucun profil réel (réciprocité : il faudrait un profil publié).
    ("PUT",    "/api/reseau/profil",                          "rejoindre le réseau de partenaires"),
    ("DELETE", "/api/reseau/profil",                          "rejoindre le réseau de partenaires"),
    ("POST",   "/api/reseau/profil/verifier",                 "rejoindre le réseau de partenaires"),
    ("POST",   "/api/reseau/profil/publier",                  "rejoindre le réseau de partenaires"),
    ("DELETE", "/api/reseau/profil/publier",                  "rejoindre le réseau de partenaires"),
    ("POST",   "/api/projects/{pid}/reseau/invitations",      "inviter un partenaire"),
    ("POST",   "/api/projects/{pid}/reseau/invitations-sirene", "inviter un partenaire"),
    # Dépôt (vague 4) : change le statut du marché et écrit dans le journal de tous les membres.
    ("POST",   "/api/projects/{pid}/groupement/deposer",      "marquer un dossier déposé"),
    ("DELETE", "/api/projects/{pid}/groupement/deposer",      "marquer un dossier déposé"),
    # Détail chiffré seul (vague 4, DPGF de lot) : écriture dans la part d'un partenaire.
    ("PUT",    "/api/invite/{token}/contribution/detail",     "modifier le détail de votre chiffrage"),
    ("POST",   "/api/org/invite",                             "inviter un collègue"),
    ("PUT",    "/api/auth/me",                                "modifier le profil du compte"),  # changement d'email
    ("POST",   "/api/auth/change-password",                   "choisir un mot de passe"),
    ("POST",   "/api/auth/resend-verification",               "recevoir des emails"),
    # « Mon avis » reste ouvert à la démo : le message ne part qu'au fondateur (adresse fixe,
    # 20/h), jamais vers un tiers — et l'avis d'un visiteur de la démo a de la valeur.
    ("POST",   "/api/amont/auto",                             "activer la veille automatique"),
    # (b) téléversements de fichiers
    ("POST",   "/api/documents",                              "déposer des documents"),
    ("PUT",    "/api/documents/{did}/replace",                "déposer des documents"),
    ("POST",   "/api/sourcing/analyze-upload",                "analyser vos propres fichiers"),
    ("POST",   "/api/amont/analyze-upload",                   "analyser vos propres fichiers"),
    ("POST",   "/api/knowledge/upload",                       "enrichir votre savoir-faire"),
    ("POST",   "/api/knowledge/memoire-upload",               "générer un mémoire technique"),
    # (c) appels IA payants (l'analyse des marchés DEMO- reste servie, sans IA)
    ("POST",   "/api/sourcing/reanalyze",                     "lancer une analyse IA"),
    ("POST",   "/api/sourcing/renewals",                      "lancer une analyse IA"),
    ("POST",   "/api/sourcing/ask",                           "poser vos questions à l'IA"),
    ("POST",   "/api/sourcing/documents",                     "générer vos documents"),
    ("POST",   "/api/chiffrage/{pid}/estimate",               "obtenir une estimation de chiffrage"),
    ("POST",   "/api/knowledge/text",                         "enrichir votre savoir-faire"),
    ("POST",   "/api/knowledge/memoire",                      "générer un mémoire technique"),
    ("POST",   "/api/knowledge/questionnaire",                "remplir un questionnaire avec l'IA"),
    # Atelier du dossier de présentation (rédaction, vague 2) : les actions de l'IA, et toute
    # écriture (la vitrine est partagée entre visiteurs : elle ne doit pas changer). La démo
    # garde la lecture : le plan proposé à partir du dossier du marché.
    ("POST",   "/api/atelier/{pid}/sections/{sid}/rediger",   "rédiger avec Adjugo"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/raccourcir", "rédiger avec Adjugo"),
    ("POST",   "/api/atelier/{pid}/rediger",                  "rédiger avec Adjugo"),
    ("POST",   "/api/atelier/{pid}",                          "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/plan",                     "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/plan/grille",              "préparer votre dossier de présentation"),
    ("PUT",    "/api/atelier/{pid}/options",                  "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections",                 "préparer votre dossier de présentation"),
    ("PATCH",  "/api/atelier/{pid}/sections/{sid}",           "préparer votre dossier de présentation"),
    ("DELETE", "/api/atelier/{pid}/sections/{sid}",           "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/remettre",  "préparer votre dossier de présentation"),
    ("PUT",    "/api/atelier/{pid}/sections/{sid}/texte",     "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/restaurer", "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/relu",      "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/valider",   "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/faits/{fid}", "préparer votre dossier de présentation"),
    # Vague 3 (A) : relier un fait à sa source (crée une preuve « déclaré par vous »), recontrôler.
    ("POST",   "/api/atelier/{pid}/sections/{sid}/faits/{fid}/source", "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/controle",  "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/derogation",               "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/export",                   "préparer votre dossier de présentation"),
    # Rédaction, vague 4 : le dossier de groupement (« Qui écrit quoi », parts des partenaires).
    ("POST",   "/api/atelier/{pid}/repartition",              "préparer votre dossier de présentation"),
    ("PUT",    "/api/atelier/{pid}/repartition/{sid}",        "préparer votre dossier de présentation"),
    ("PUT",    "/api/atelier/{pid}/repartition/{sid}/texte",  "préparer votre dossier de présentation"),
    ("POST",   "/api/atelier/{pid}/repartition/demander",     "inviter un partenaire"),
    ("POST",   "/api/atelier/{pid}/repartition/valider-dossier", "préparer votre dossier de présentation"),
    # Assemblage (vague 4, chantier 3) : « Harmoniser le ton » appelle l'IA (phrases de transition).
    ("POST",   "/api/atelier/{pid}/repartition/harmoniser",   "rédiger avec Adjugo"),
    ("PUT",    "/api/shared/{pid}/redaction/sections/{sid}/brouillon", "co-construire une réponse"),
    ("POST",   "/api/shared/{pid}/redaction/sections/{sid}/faits/{fid}", "co-construire une réponse"),
    ("POST",   "/api/shared/{pid}/redaction/sections/{sid}/aide", "rédiger avec Adjugo"),
    ("POST",   "/api/shared/{pid}/redaction/sections/{sid}/envoyer", "co-construire une réponse"),
    ("POST",   "/api/shared/{pid}/redaction/sections/{sid}/valider", "co-construire une réponse"),
    ("POST",   "/api/shared/{pid}/redaction/sections/{sid}/retablir", "co-construire une réponse"),
    ("POST",   "/api/shared/{pid}/redaction/dossier/valider", "co-construire une réponse"),
    # « Mes preuves » (rédaction, vague 3) : toute écriture (la vitrine partagée ne change pas).
    ("POST",   "/api/preuves",                                "renseigner vos preuves"),
    ("PATCH",  "/api/preuves/{id}",                           "renseigner vos preuves"),
    ("DELETE", "/api/preuves/{id}",                           "renseigner vos preuves"),
    ("POST",   "/api/preuves/{id}/accepter",                  "renseigner vos preuves"),
    ("POST",   "/api/preuves/{id}/retirer",                   "renseigner vos preuves"),
    ("POST",   "/api/knowledge/{doc_id}/fiches",              "proposer des fiches à partir de vos documents"),
    ("POST",   "/api/preuves/reprise",                        "renseigner vos preuves"),
    ("POST",   "/api/atelier/{pid}/sections/{sid}/inserer-preuve", "préparer votre dossier de présentation"),
    ("POST",   "/api/amont/analyze-text",                     "lancer une analyse IA"),
    ("POST",   "/api/amont/scan",                             "lancer une analyse IA"),
    # Rédaction, vague 5 (C2 complet) : exigences retirées, ajoutées ou dites traitées, questions à l'acheteur
    # retirées, relecture du dossier (0 IA) : écritures dans la grille de la vitrine partagée.
    ("POST",   "/api/sourcing/grille/element",                "préparer votre dossier de présentation"),
    ("POST",   "/api/sourcing/grille/exigence",               "préparer votre dossier de présentation"),
    ("POST",   "/api/sourcing/grille/relire",                 "préparer votre dossier de présentation"),
    # (d) compte, abonnement, équipe, organisation
    ("POST",   "/api/rgpd/delete-account",                    "gérer votre compte"),
    ("POST",   "/api/stripe/create-checkout",                 "vous abonner"),
    ("POST",   "/api/stripe/overage",                         "gérer votre abonnement"),
    ("POST",   "/api/stripe/portal",                          "gérer votre abonnement"),
    ("PUT",    "/api/org",                                    "gérer votre organisation"),
    ("DELETE", "/api/org/members/{mid}",                      "gérer votre équipe"),
    ("PUT",    "/api/org/members/{mid}/role",                 "gérer votre équipe"),
    ("POST",   "/api/org/transfer-ownership",                 "gérer votre équipe"),
    # (e) vitrine partagée entre les présentations : ce qu'un visiteur y supprime ou modifie resterait
    # pour les suivants (la remise à neuf automatique, app/services/demo_remise.py, ne passe qu'après
    # une période sans aucune session démo). Le changement d'étape d'un marché reste permis : PUT
    # /api/projects/{pid} est filtré DANS la route (seul le champ « status » passe pour la démo).
    ("DELETE", "/api/projects/{pid}",                         "supprimer un marché"),
    ("PATCH",  "/api/documents/{did}",                        "gérer vos documents"),
    ("DELETE", "/api/documents/{did}",                        "gérer vos documents"),
    ("POST",   "/api/company",                                "modifier le profil de votre entreprise"),
    ("PUT",    "/api/company",                                "modifier le profil de votre entreprise"),
    ("PUT",    "/api/criteria",                               "régler vos critères"),
    ("PUT",    "/api/cotraitants/{cid}",                      "gérer vos partenaires"),
    ("DELETE", "/api/cotraitants/{cid}",                      "gérer vos partenaires"),
    ("POST",   "/api/cotraitants/project/{pid}",              "gérer vos partenaires"),
    ("DELETE", "/api/cotraitants/project/{pid}/{lid}",        "gérer vos partenaires"),
]
_RULES = [(m, _p(path), action) for m, path, action in _BLOCKED]


def demo_message(action: str) -> str:
    return f"La démo est en lecture guidée : commencez votre essai gratuit de 30 jours pour {action}."


def blocked_action(method: str, path: str) -> Optional[str]:
    """Action bloquée pour le compte démo sur (méthode, chemin), ou None si autorisée."""
    method = (method or "").upper()
    for m, rx, action in _RULES:
        if m == method and rx.match(path or ""):
            return action
    return None


def is_demo_user(user) -> bool:
    """Même règle que la recherche/analyse démo (une seule source de vérité)."""
    from app.services.demo_search import is_demo
    return is_demo(user)


def refuser_demo(user, action: str) -> None:
    """Défense en profondeur, DANS la route, derrière le middleware : 403 « lecture guidée » pour le
    compte démo. Posée sur les routes qui téléversent, envoient un email ou écrivent chez un tiers
    (Stripe) : si le middleware était un jour contourné, la route refuserait encore."""
    if is_demo_user(user):
        from fastapi import HTTPException
        raise HTTPException(403, demo_message(action))


def bearer_is_demo(authorization: str) -> bool:
    """Vrai si l'en-tête Authorization porte une session VALIDE du compte démo.
    Réutilise get_current_user (mêmes contrôles : signature, expiration, purpose, tv…) en
    lecture seule. Jeton absent/invalide → False : la route répondra elle-même (401)."""
    auth = authorization or ""
    if not auth.lower().startswith("bearer "):
        return False
    token = auth[7:].strip()
    if not token:
        return False
    from fastapi import HTTPException
    from app.core.database import SessionLocal
    from app.core.security import get_current_user
    db = SessionLocal()
    try:
        user = get_current_user(token=token, db=db)
        return is_demo_user(user)
    except HTTPException:
        return False
    except Exception as e:   # jamais de 500 à cause du garde : la route décidera
        logger.warning("demo_guard : identification impossible : %s", e)
        return False
    finally:
        db.close()


_SLASHES = re.compile(r"/{2,}")


def routed_path(scope) -> str:
    """Chemin RÉELLEMENT routé, lu dans le scope ASGI (root_path retiré), normalisé pour la
    comparaison : barres obliques multiples fusionnées, minuscules.

    Jamais `request.url.path` : Starlette le reconstruit à partir de l'en-tête Host, que le
    client contrôle (« Host: x/y » donnait « /y/api/org/invite » et la règle ne s'appliquait
    plus, alors que le routeur servait bien /api/org/invite). Le scope, lui, contient déjà le
    chemin décodé (%2F → /) tel que le routeur le voit. La normalisation ne peut que
    BLOQUER davantage (le routeur est sensible à la casse et ne fusionne pas les « // »)."""
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return _SLASHES.sub("/", path).lower()


async def demo_guard_middleware(request, call_next):
    """Middleware HTTP : 403 en français pour les actions interdites au compte démo."""
    action = blocked_action(request.method, routed_path(request.scope))
    if action:
        from starlette.concurrency import run_in_threadpool
        if await run_in_threadpool(bearer_is_demo, request.headers.get("authorization", "")):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": demo_message(action)})
    return await call_next(request)
