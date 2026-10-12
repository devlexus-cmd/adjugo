"""
Compte démo public = « vitrine en lecture guidée » (décision fondateur, audit cyber oct. 2026).

Le compte démo (demo@adjugo.fr) s'ouvre en un clic, sans mot de passe : n'importe qui en
détient une session. Il garde tout l'affichage et les interactions SANS COÛT (navigation,
simulation de groupement, filtres, chiffrage manuel, CERFA…), mais ne peut plus :
  (a) faire envoyer un email (invitations partenaire / équipe, relances, changement d'email…),
  (b) téléverser un fichier,
  (c) lancer un appel IA payant (hors analyses canned des marchés DEMO-),
  (d) supprimer le compte, toucher à l'abonnement, à l'équipe ou à l'organisation.

Mise en œuvre CENTRALE : un middleware (enregistré dans app/main.py) consulte une liste
explicite de (méthode, motif de route). Seules les requêtes qui tombent dans cette liste
sont examinées : on identifie alors le porteur du Bearer avec les fonctions d'auth
existantes (lecture seule) et on renvoie 403 si c'est le compte démo. Toute autre requête
passe sans aucun coût supplémentaire. Défense en profondeur : consume_analysis (quota.py)
refuse aussi tout appel IA du compte démo (les analyses DEMO- ne passent jamais par là).
"""
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

_ID = r"[^/]+"


def _p(path: str) -> "re.Pattern":
    """Motif de route FastAPI → regex ancrée ({param} = un segment, « / » final optionnel)."""
    rx = re.sub(r"\{[^}]+\}", _ID, path.rstrip("/"))
    return re.compile(rf"^{rx}/?$")


# (méthode, motif, action affichée : « créez votre compte gratuit pour <action> »)
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
    # « Mes preuves » (rédaction, vague 3) : toute écriture (la vitrine partagée ne change pas).
    ("POST",   "/api/preuves",                                "renseigner vos preuves"),
    ("PATCH",  "/api/preuves/{id}",                           "renseigner vos preuves"),
    ("DELETE", "/api/preuves/{id}",                           "renseigner vos preuves"),
    ("POST",   "/api/preuves/{id}/accepter",                  "renseigner vos preuves"),
    ("POST",   "/api/preuves/{id}/retirer",                   "renseigner vos preuves"),
    ("POST",   "/api/knowledge/{doc_id}/fiches",              "proposer des fiches à partir de vos documents"),
    ("POST",   "/api/amont/analyze-text",                     "lancer une analyse IA"),
    ("POST",   "/api/amont/scan",                             "lancer une analyse IA"),
    # (d) compte, abonnement, équipe, organisation
    ("POST",   "/api/rgpd/delete-account",                    "gérer votre compte"),
    ("POST",   "/api/stripe/create-checkout",                 "vous abonner"),
    ("POST",   "/api/stripe/overage",                         "gérer votre abonnement"),
    ("POST",   "/api/stripe/portal",                          "gérer votre abonnement"),
    ("PUT",    "/api/org",                                    "gérer votre organisation"),
    ("DELETE", "/api/org/members/{mid}",                      "gérer votre équipe"),
    ("PUT",    "/api/org/members/{mid}/role",                 "gérer votre équipe"),
    ("POST",   "/api/org/transfer-ownership",                 "gérer votre équipe"),
]
_RULES = [(m, _p(path), action) for m, path, action in _BLOCKED]


def demo_message(action: str) -> str:
    return f"La démo est en lecture guidée : créez votre compte gratuit pour {action}."


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
