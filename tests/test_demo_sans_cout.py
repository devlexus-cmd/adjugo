"""
Démo À JOUR et SANS COÛT (chantier du 13/10/2026, avant de redonner la démo à Mathys).

1. Garde-fous de coût. COUTS liste TOUTES les routes qui peuvent appeler l'IA, envoyer un email,
   téléverser un fichier ou écrire chez un tiers (Stripe, réseau, diffusion) ; SANS_COUT classe toutes
   les autres routes d'écriture, avec la raison. Un test d'inventaire échoue dès qu'une route d'écriture
   n'est classée nulle part : toute nouvelle route doit être examinée ici. Chaque route à coût est
   appelée par la session démo (PME et collectivités) AVEC le garde central (app/core/demo_guard.py),
   puis SANS lui (défense en profondeur) : jamais d'appel à l'IA (llm.messages_create), d'email, de
   fichier rangé, ni d'écriture chez un tiers. Les affichages (toutes les routes GET) restent ouverts et
   sans coût.
2. Démo à jour (app/services/demo_redaction.py) : analyse avec grille « Comment vous serez noté » et
   couverture « Dossier lu en entier », « Mes preuves », dossier de présentation déjà rédigé ; seed
   idempotent, rejouable, sans IA ni réseau, isolé dans sa transaction ; vitrine du groupement (Kerhel) intacte.
3. Lien privé de démonstration (docs/DEMO_LIEN_PRIVE.md) : démo publique fermée, les sessions ouvertes
   par le lien voient la même démo à jour, avec les mêmes refus et sans coût ; clé changée, coupées.

IA simulée (coupée), emails et réseau coupés : aucun appel réel.
"""
import io
import pathlib
import re
import sys
from dataclasses import dataclass

import pytest

from app.core.database import SessionLocal

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"


@dataclass(frozen=True)
class Cout:
    methode: str
    chemin: str               # chemin déclaré dans FastAPI (sert aussi à l'inventaire)
    nature: str               # ia | email | fichier | tiers | compte
    attendu: str = "refus"    # refus (403 « lecture guidée », ou 410) | ouvert (réponse utile, sans coût)
    corps: object = None      # JSON, ("fichier", champs du formulaire) ou ("form", champs)
    session: str = "pme"      # pme | acheteur | lien (lien partenaire de la démo, sans session)
    params: tuple = ()        # ((paramètre du chemin, clé du contexte), …)
    query: str = ""
    lectures: bool = False    # lectures de données publiques permises (open data), jamais d'écriture

    @property
    def id(self) -> str:
        return f"{self.methode} {self.chemin}{('?' + self.query) if self.query else ''} [{self.attendu}]"


_P = (("project_id", "toiture"),)
_L = (("project_id", "lorient"),)
_S = (("project_id", "toiture"), ("section_id", "sid"))
_T = (("token", "token"),)
_TS = _T + (("section_id", "sid"),)                     # lien partenaire de la démo, une partie
_LS = (("project_id", "lorient"), ("section_id", "sid"))  # « Partagé avec moi » (le compte démo n'en a aucun)
_TENDER = "tender"          # remplacé par un avis (voir _corps)

COUTS = [
    # ── IA ──────────────────────────────────────────────────────────────────────────────────────────
    Cout("POST", "/api/sourcing/analyze", "ia", corps={"tender": "reel"}),
    Cout("POST", "/api/sourcing/analyze", "ia", "ouvert", corps={"tender": "demo"}),   # analyse rédigée, sans IA
    Cout("POST", "/api/sourcing/analyze-upload", "ia", corps=("fichier", {"project_id": "toiture"})),
    Cout("POST", "/api/sourcing/reanalyze", "ia", corps=("form", {"project_id": "toiture"})),
    Cout("POST", "/api/sourcing/renewals", "ia", corps={"query": "toiture", "departements": ["44"]}),
    Cout("POST", "/api/sourcing/ask", "ia", corps={"project_id": "toiture", "question": "Quel est le délai ?"}),
    Cout("POST", "/api/chiffrage/{project_id}/estimate", "ia", corps={"distance_km": 10}, params=_P),
    Cout("POST", "/api/knowledge/questionnaire", "ia", corps={"questions": ["Quelles sont vos références ?"]}),
    Cout("POST", "/api/knowledge/{doc_id}/fiches", "ia", corps={}, params=(("doc_id", "kb"),)),
    Cout("POST", "/api/knowledge/memoire", "ia", corps={"dce_text": "x" * 100}),
    Cout("POST", "/api/knowledge/memoire-upload", "ia", corps=("fichier", {})),
    Cout("POST", "/api/amont/analyze-text", "ia", corps={"text": "Le conseil approuve la rénovation. " * 4}),
    Cout("POST", "/api/amont/analyze-upload", "ia", corps=("fichier", {})),
    Cout("POST", "/api/amont/scan", "ia", corps={"departements": ["44"]}),
    Cout("POST", "/api/amont/auto", "ia", corps={"enabled": True}),
    Cout("POST", "/api/atelier/{project_id}/sections/{section_id}/rediger", "ia", corps={}, params=_S),
    Cout("POST", "/api/atelier/{project_id}/sections/{section_id}/raccourcir", "ia", corps={}, params=_S),
    Cout("POST", "/api/atelier/{project_id}/rediger", "ia", corps={}, params=_P),
    Cout("POST", "/api/dce/generate", "ia", session="acheteur",
         corps={"objet": "Réfection de la toiture de l'école", "type_marche": "travaux", "montant_estime": 300000}),
    Cout("POST", "/api/dce/sourcing", "ia", "ouvert", session="acheteur", lectures=True,
         corps={"lots": [{"intitule": "Couverture", "montant": 200000}], "departement": "44"}),
    # Rédaction, vague 4 : l'aide de l'IA du partenaire (par le lien de la vitrine, ou « Partagé avec moi ») et
    # « Harmoniser le ton » du chef de file (assemblage).
    Cout("POST", "/api/atelier/{project_id}/repartition/harmoniser", "ia", corps={}, params=_P),
    Cout("POST", "/api/invite/{token}/redaction/sections/{section_id}/aide", "ia", session="lien",
         corps={"action": "rediger"}, params=_TS),
    Cout("POST", "/api/shared/{project_id}/redaction/sections/{section_id}/aide", "ia", corps={"action": "rediger"},
         params=_LS),
    # ── Emails ──────────────────────────────────────────────────────────────────────────────────────
    Cout("POST", "/api/projects/{project_id}/invites", "email",
         corps={"recipient": "partenaire@exemple.invalid", "company_name": "Partenaire"}, params=_L),
    Cout("POST", "/api/projects/{project_id}/invites/{invite_id}/resend", "email",
         params=_L + (("invite_id", "invite"),)),
    Cout("DELETE", "/api/projects/{project_id}/invites/{invite_id}", "email", params=_L + (("invite_id", "invite"),)),
    Cout("POST", "/api/projects/{project_id}/offre/figer", "email", params=_L),
    Cout("PUT", "/api/projects/{project_id}/groupement/convention", "email", corps={"forme": "conjoint"}, params=_L),
    Cout("POST", "/api/projects/{project_id}/groupement/convention/generer", "email", corps={}, params=_L),
    Cout("POST", "/api/projects/{project_id}/groupement/convention/valider", "email",
         corps={"content_hash": "0" * 64, "signataire_nom": "Compte Démo", "signataire_qualite": "Gérant",
                "accepte": True}, params=_L),
    Cout("POST", "/api/invite/{token}/convention/valider", "email", session="lien",
         corps={"content_hash": "0" * 64, "signataire_nom": "Soizic Morvan", "accepte": True}, params=_T),
    Cout("POST", "/api/projects/{project_id}/reseau/invitations", "email", corps={"profile_id": "a" * 32}, params=_L),
    Cout("POST", "/api/projects/{project_id}/reseau/invitations-sirene", "email",
         corps={"siret": "12345678900011"}, params=_L),
    Cout("POST", "/api/org/invite", "email", corps={"email": "collegue@exemple.invalid", "full_name": "Collègue"}),
    Cout("PUT", "/api/auth/me", "email", corps={"email": "autre@exemple.invalid"}),
    Cout("POST", "/api/auth/resend-verification", "email"),
    Cout("POST", "/api/auth/forgot-password", "email", "ouvert", session="aucune", corps={"email": "demo"}),
    Cout("POST", "/api/feedback", "email", "ouvert", corps={"message": "Retour d'un visiteur", "kind": "idee"}),
    Cout("POST", "/api/invite/{token}/otp/request", "email", "ouvert", session="lien", params=_T),
    Cout("POST", "/api/invite/{token}/contribution/submit", "email", "ouvert", session="lien", params=_T),
    Cout("POST", "/api/invite/{token}/decline", "email", session="lien", params=_T),
    # Rédaction, vague 4 : « Demander les parts », part modifiée par le chef de file (le partenaire est
    # prévenu), part envoyée par un partenaire (le chef de file est prévenu).
    Cout("POST", "/api/atelier/{project_id}/repartition/demander", "email", corps={}, params=_L),
    Cout("PUT", "/api/atelier/{project_id}/repartition/{section_id}/texte", "email",
         corps={"texte": "Texte écrit par le chef de file.", "base_version_id": None}, params=_S),
    Cout("POST", "/api/invite/{token}/redaction/sections/{section_id}/envoyer", "email", session="lien",
         corps={"brouillon_id": 1, "avertissement_lu": True}, params=_TS),
    Cout("POST", "/api/shared/{project_id}/redaction/sections/{section_id}/envoyer", "email",
         corps={"brouillon_id": 1, "avertissement_lu": True}, params=_LS),
    # ── Téléversements (et fichiers rangés) ─────────────────────────────────────────────────────────
    Cout("POST", "/api/documents/", "fichier", corps=("fichier", {"category": "kbis"})),
    Cout("PUT", "/api/documents/{doc_id}/replace", "fichier", corps=("fichier", {}), params=(("doc_id", "doc"),)),
    Cout("POST", "/api/knowledge/upload", "fichier", corps=("fichier", {"kind": "memoire"})),
    Cout("POST", "/api/knowledge/text", "fichier", corps={"name": "Note", "text": "Méthodologie de chantier. " * 4}),
    Cout("POST", "/api/sourcing/documents", "fichier", corps={"project_id": "toiture"}),
    Cout("POST", "/api/atelier/{project_id}/export", "fichier", corps={"format": "docx"}, params=_P),
    Cout("POST", "/api/invite/{token}/contribution/piece", "fichier", session="lien", corps=("fichier", {}),
         params=_T),
    Cout("POST", "/api/invite/{token}/contribution/piece/from-vault", "fichier",       # compte + lien de la démo
         corps={"document_id": "doc"}, params=_T),
    # ── Écritures chez un tiers ─────────────────────────────────────────────────────────────────────
    Cout("POST", "/api/stripe/create-checkout", "tiers", query="plan=pro"),
    Cout("POST", "/api/stripe/overage", "tiers", query="enabled=true"),
    Cout("POST", "/api/stripe/portal", "tiers"),
    Cout("POST", "/api/reseau/profil/verifier", "tiers"),
    Cout("POST", "/api/reseau/profil/publier", "tiers", corps={"accepte": True}),
    Cout("POST", "/api/saved-searches/{search_id}/run", "tiers", "ouvert", params=(("search_id", "search"),)),
    Cout("POST", "/api/acheteur/dce/{dce_id}/diffuser", "tiers", session="acheteur", corps={"nb_pme": 12},
         params=(("dce_id", "dce"),)),
    # ── Le compte de la vitrine ─────────────────────────────────────────────────────────────────────
    Cout("POST", "/api/rgpd/delete-account", "compte", corps={"password": "faux", "confirm": "SUPPRIMER"}),
    Cout("POST", "/api/auth/change-password", "compte", corps={"current_password": "faux", "new_password": "x" * 12}),
    Cout("POST", "/api/acheteur/rgpd/effacer", "compte", session="acheteur", corps={"password": "faux"}),
]

# Toutes les autres routes d'écriture : aucune n'appelle l'IA, n'envoie d'email, ne téléverse ni n'écrit
# chez un tiers pour la session démo. « vitrine » = bloquée par le garde (la vitrine partagée ne change
# pas) ; « interaction » = ouverte, sans coût ; « hors démo » = jamais une session démo.
_V = "vitrine : écriture bloquée par le garde démo, sans coût"
_I = "interaction sans coût (base de données seulement)"
_H = "hors démo : pas de session démo sur cette route"
_LD = "lien partenaire de la démo : refusé dans la route avant tout autre contrôle (aucune IA, aucun email)"
SANS_COUT = {
    ("POST", "/api/auth/register"): _H, ("POST", "/api/auth/verify-email"): _H, ("POST", "/api/auth/login"): _H,
    ("POST", "/api/auth/demo"): "connexion à la démo (aucun email, aucune IA)",
    ("POST", "/api/auth/demo/lien"): "vérification de la clé du lien privé de démonstration (n'ouvre aucune session)",
    ("POST", "/api/auth/reset-password"): _H, ("POST", "/api/auth/google/exchange"): _H,
    # Vitrine PARTAGÉE entre les présentations (tests/test_demo_remise_a_neuf.py) : supprimer ou modifier un
    # marché, un document, le profil, les critères, les partenaires est refusé à la démo ; seul le changement
    # d'étape d'un marché reste ouvert (filtré dans la route).
    ("POST", "/api/projects/"): _I,
    ("PUT", "/api/projects/{project_id}"): ("vitrine : seul le changement d'étape (status) reste ouvert à la démo, "
                                           "tout autre champ est refusé dans la route"),
    ("DELETE", "/api/projects/{project_id}"): _V, ("POST", "/api/projects/{project_id}/restore"): _I,
    ("PATCH", "/api/documents/{doc_id}"): _V, ("DELETE", "/api/documents/{doc_id}"): _V,
    ("POST", "/api/documents/{doc_id}/restore"): _I,
    ("POST", "/api/invoices/"): _I, ("PUT", "/api/invoices/{invoice_id}"): _I,
    ("POST", "/api/invoices/{invoice_id}/convert"): _I,
    ("POST", "/api/contacts/"): _I, ("PUT", "/api/contacts/{contact_id}"): _I,
    ("DELETE", "/api/contacts/{contact_id}"): _I,
    ("POST", "/api/company/"): _V, ("PUT", "/api/company/"): _V, ("PUT", "/api/criteria/"): _V,
    ("POST", "/api/cerfa/{project_id}/{doc_type}"): "formulaire rempli sans IA, rien n'est rangé",
    ("POST", "/api/stripe/webhook"): "hors démo : appel signé de Stripe",
    ("POST", "/api/cotraitants/"): _I + " (un partenaire ajouté s'efface à la remise à neuf)",
    ("PUT", "/api/cotraitants/{ct_id}"): _V,
    ("DELETE", "/api/cotraitants/{ct_id}"): _V, ("POST", "/api/cotraitants/project/{project_id}"): _V,
    ("DELETE", "/api/cotraitants/project/{project_id}/{link_id}"): _V,
    ("POST", "/api/projects/{project_id}/groupement/simulate"): "simulation déterministe (score de groupement)",
    # Groupement de la vitrine (Kerhel) : convention validée par tous ; retenir une autre composition, retirer
    # le plan ou défiger l'offre la rendrait caduque pour chaque visiteur (tests/test_demo_groupement_kerhel.py).
    ("POST", "/api/projects/{project_id}/groupement/retenir"): _V,
    ("DELETE", "/api/projects/{project_id}/groupement/plan"): _V,
    ("POST", "/api/projects/{project_id}/groupement/deposer"): _V,
    ("DELETE", "/api/projects/{project_id}/groupement/deposer"): _V,
    ("POST", "/api/projects/{project_id}/groupement/convention/relire-dce"): _V + " (0 IA)",
    ("POST", "/api/projects/{project_id}/groupement/convention/hors-ligne/{link_id}"): _V,
    ("POST", "/api/export/{project_id}"): "archive du dossier composée à la volée, sans IA ni rangement",
    ("PUT", "/api/chiffrage/{project_id}"): "recalcul déterministe",
    ("PUT", "/api/chiffrage/{project_id}/review"): _I,
    ("POST", "/api/registre/import"): "lecture du registre public SIRENE puis base de données",
    ("POST", "/api/admin/run-backup"): "administrateur de la plateforme seulement (la démo est refusée)",
    ("POST", "/api/admin/run-alerts"): "administrateur seulement", ("POST", "/api/admin/run-tender-alerts"): "administrateur seulement",
    ("POST", "/api/admin/run-amont-alerts"): "administrateur seulement",
    ("POST", "/api/admin/run-cotraitance-reminders"): "administrateur seulement",
    ("POST", "/api/admin/run-trash-purge"): "administrateur seulement",
    ("POST", "/api/admin/run-partner-network"): "administrateur seulement",
    ("POST", "/api/admin/run-audit-anchor"): "administrateur seulement",
    ("POST", "/api/admin/reseau/validations/{profile_id}/valider"): "administrateur seulement",
    ("POST", "/api/admin/reseau/validations/{profile_id}/refuser"): "administrateur seulement",
    ("POST", "/api/sourcing/market-estimate"): "repère de prix déterministe (données publiques DECP)",
    ("POST", "/api/sourcing/groupement"): "composition déterministe (registre public SIRENE)",
    ("POST", "/api/sourcing/search"): "démo : marchés fictifs déjà notés, sans appel au BOAMP",
    ("POST", "/api/sourcing/grille/choix"): _I + " (0 IA)",
    ("POST", "/api/sourcing/cotraitants"): "recherche déterministe (registre public SIRENE)",
    ("POST", "/api/saved-searches/"): _I, ("PUT", "/api/saved-searches/{search_id}"): _I,
    ("DELETE", "/api/saved-searches/{search_id}"): _I,
    ("PUT", "/api/org/"): _V, ("DELETE", "/api/org/members/{member_id}"): _V,
    ("PUT", "/api/org/members/{member_id}/role"): _V, ("POST", "/api/org/transfer-ownership"): _V,
    ("DELETE", "/api/amont/{signal_id}"): _I, ("DELETE", "/api/knowledge/{doc_id}"): _I,
    ("POST", "/api/knowledge/search"): "recherche dans « Mon savoir-faire », sans IA",
    ("POST", "/api/preuves/reprise"): _V, ("POST", "/api/preuves"): _V, ("PATCH", "/api/preuves/{preuve_id}"): _V,
    ("POST", "/api/preuves/{preuve_id}/accepter"): _V, ("POST", "/api/preuves/{preuve_id}/retirer"): _V,
    ("DELETE", "/api/preuves/{preuve_id}"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/inserer-preuve"): _V,
    ("POST", "/api/atelier/{project_id}"): _V, ("POST", "/api/atelier/{project_id}/plan"): _V,
    ("POST", "/api/atelier/{project_id}/plan/grille"): _V, ("PUT", "/api/atelier/{project_id}/options"): _V,
    ("POST", "/api/atelier/{project_id}/sections"): _V,
    ("PATCH", "/api/atelier/{project_id}/sections/{section_id}"): _V,
    ("DELETE", "/api/atelier/{project_id}/sections/{section_id}"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/remettre"): _V,
    ("PUT", "/api/atelier/{project_id}/sections/{section_id}/texte"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/restaurer"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/relu"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/valider"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/faits/{fait_id}"): _V,
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/controle"): _V + " (0 IA)",
    ("POST", "/api/atelier/{project_id}/sections/{section_id}/faits/{fait_id}/source"): _V + " (0 IA)",
    ("POST", "/api/atelier/{project_id}/derogation"): _V,
    # Rédaction, vague 4 : « Qui écrit quoi » (chef de file) et parts des partenaires — refusées par le garde
    # ET dans la route (tests/test_redaction_v4_chef_de_file.py) ; le lien partenaire de la vitrine n'écrit rien.
    ("POST", "/api/atelier/{project_id}/repartition"): _V + " (0 IA : pré-remplissage d'après les lots)",
    ("PUT", "/api/atelier/{project_id}/repartition/{section_id}"): _V,
    ("POST", "/api/atelier/{project_id}/repartition/valider-dossier"): _V,
    ("POST", "/api/invite/{token}/redaction/espace"): _LD,
    ("PUT", "/api/invite/{token}/redaction/sections/{section_id}/brouillon"): _LD,
    ("POST", "/api/invite/{token}/redaction/sections/{section_id}/faits/{fait_id}"): _LD,
    ("POST", "/api/invite/{token}/redaction/sections/{section_id}/valider"): _LD,
    ("POST", "/api/invite/{token}/redaction/sections/{section_id}/retablir"): _LD,
    ("POST", "/api/invite/{token}/redaction/dossier/valider"): _LD,
    ("PUT", "/api/shared/{project_id}/redaction/sections/{section_id}/brouillon"): _V + " (« Partagé avec moi »)",
    ("POST", "/api/shared/{project_id}/redaction/sections/{section_id}/faits/{fait_id}"): _V + " (« Partagé avec moi »)",
    ("POST", "/api/shared/{project_id}/redaction/sections/{section_id}/valider"): _V + " (« Partagé avec moi »)",
    ("POST", "/api/shared/{project_id}/redaction/sections/{section_id}/retablir"): _V + " (« Partagé avec moi »)",
    ("POST", "/api/shared/{project_id}/redaction/dossier/valider"): _V + " (« Partagé avec moi »)",
    ("PUT", "/api/invite/{token}/contribution"): "lien partenaire de la démo : refusé dans la route (part figée par la convention)",
    ("PUT", "/api/invite/{token}/contribution/detail"): "lien partenaire de la démo : refusé dans la route",
    ("POST", "/api/invite/{token}/otp/verify"): "lien partenaire : vérification d'un code (aucun envoi)",
    ("POST", "/api/invite/{token}/search"): "lien partenaire : recherche publique (BOAMP), sans IA",
    ("PATCH", "/api/invite/{token}/contribution/piece/{piece_id}"): "lien partenaire de la démo : refusé dans la route",
    ("DELETE", "/api/invite/{token}/contribution/piece/{piece_id}"): "lien partenaire de la démo : refusé dans la route",
    ("DELETE", "/api/projects/{project_id}/offre/figer"): _V,
    ("POST", "/api/invite/{token}/claim"): "lien nominatif : réservé au compte de l'adresse invitée",
    ("PUT", "/api/reseau/profil"): _V, ("DELETE", "/api/reseau/profil"): _V,
    ("DELETE", "/api/reseau/profil/publier"): _V,
    ("POST", "/api/dce/estimer-budget"): "repère de budget déterministe (données publiques DECP)",
    ("POST", "/api/dce/preview-procedure"): "calcul déterministe des seuils",
    ("POST", "/api/dce/export"): "rendu du DCE fourni, sans IA",
    ("POST", "/api/dce/avis"): "avis assemblé sans IA",
    ("POST", "/api/acheteur/register"): _H, ("POST", "/api/acheteur/login"): _H,
    ("POST", "/api/acheteur/demo"): "connexion à la démo collectivités (aucun email, aucune IA)",
    ("POST", "/api/acheteur/dce"): "vitrine collectivités : refusé dans la route",
    ("POST", "/api/acheteur/dce/{dce_id}/statut"): "vitrine collectivités : refusé dans la route",
    ("DELETE", "/api/acheteur/dce/{dce_id}"): "vitrine collectivités : refusé dans la route",
    ("POST", "/api/contact/demande-acces"): ("formulaire public, sans session : un email vers l'adresse fixe "
                                             "d'Adjugo seulement (tests/test_demande_acces.py)"),
}


# ── Contexte de la démo et espions ─────────────────────────────────────────────────────────────────

def _db():
    return SessionLocal()


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def _vitrine_remise_a_neuf(client):
    """Ce module touche à la vitrine (marché ajouté, garde coupé…) : elle est remise à neuf avant et
    après, comme au démarrage du serveur."""
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()
    yield
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()


def _sessions(client, corps=None):
    """Ouvre une session démo PME puis une session démo collectivités (corps : clé du lien privé)."""
    r = client.post("/api/auth/demo", json=corps)
    assert r.status_code == 200, r.text
    pme = _h(r.json()["access_token"])
    r = client.post("/api/acheteur/demo", json=corps)
    assert r.status_code == 200, r.text
    return pme, _h(r.json()["access_token"])


@pytest.fixture(scope="module")
def demo(client):
    """Sessions démo (PME, collectivités) et identifiants de la vitrine."""
    pme, ach = _sessions(client)
    return {"pme": pme, "acheteur": ach, "ctx": _contexte()}


def _contexte() -> dict:
    """Identifiants de la vitrine telle qu'elle est en base (ils changent à chaque remise à neuf)."""
    from app.models import (Acheteur, AcheteurDce, Document, DossierPresentation, DossierSection,
                            KnowledgeDoc, Preuve, Project, ProjectInvite, SavedSearch, User)
    from app.services.acheteur_demo_seed import DEMO_EMAIL as ACH_EMAIL
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        projets = db.query(Project).filter(Project.user_id == u.id).all()
        toiture = next(p for p in projets if p.name.startswith("Réfection toiture"))
        lorient = next(p for p in projets if "Kerhel" in p.name)
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == toiture.id).one()
        sid = db.query(DossierSection).filter(DossierSection.dossier_id == d.id).order_by(DossierSection.ordre).first().id
        inv = db.query(ProjectInvite).filter(ProjectInvite.project_id == lorient.id).first()
        a = db.query(Acheteur).filter(Acheteur.email == ACH_EMAIL).one()
        ctx = {"uid": u.id, "toiture": toiture.id, "lorient": lorient.id, "sid": sid,
               "invite": inv.id, "token": inv.token,
               "doc": db.query(Document).filter(Document.user_id == u.id, Document.name.like("Extrait Kbis%")).first().id,
               "kb": db.query(KnowledgeDoc).filter(KnowledgeDoc.user_id == u.id).first().id,
               "preuve": db.query(Preuve).filter(Preuve.owner_id == u.id).first().id,
               "search": db.query(SavedSearch).filter(SavedSearch.user_id == u.id).first().id,
               "dce": db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).first().id}
    finally:
        db.close()
    return ctx


@pytest.fixture
def espions(monkeypatch):
    """Coupe et relève tout ce qui coûte : appels à l'IA (llm.messages_create, et plus bas), emails
    (jusqu'aux transports), fichiers rangés (stockage local et objet), réseau sortant (httpx, requests,
    urllib, SMTP). L'IA est simulée : coupée, jamais appelée pour de vrai."""
    import smtplib
    import urllib.error
    import urllib.request

    import httpx
    import requests

    from app.services import email as em
    from app.services import llm
    from app.services import storage as st
    vu = {"ia": [], "email": [], "fichier": [], "reseau": []}

    def ia(*a, **k):
        vu["ia"].append(k.get("tache") or "?")
        raise llm.LLMUnavailable("IA simulée : coupée pour ce test.")

    def envoi(to, *a, **k):
        vu["email"].append(to)
        return True

    orig_ia, orig_envoi = llm.messages_create, em.send_email
    for mod in list(sys.modules.values()):
        attrs = getattr(mod, "__dict__", None)
        if not attrs or not str(getattr(mod, "__name__", "")).startswith("app."):
            continue
        for nom, val in list(attrs.items()):
            if val is orig_ia:
                monkeypatch.setattr(mod, nom, ia)
            elif val is orig_envoi:
                monkeypatch.setattr(mod, nom, envoi)
    monkeypatch.setattr(llm, "_essayer", lambda *a, **k: ia(tache="_essayer"))
    monkeypatch.setattr(llm, "client", lambda: ia(tache="client"))
    monkeypatch.setattr(em, "is_enabled", lambda: True)
    monkeypatch.setattr(em, "_send_via_brevo_api", lambda to, *a, **k: envoi(to))
    monkeypatch.setattr(em, "_send_via", lambda host, port, mode, msg, **k: envoi(msg["To"]))
    from app.routers import invites
    monkeypatch.setattr(invites, "_send_mails_async", lambda mails: [envoi(m[0]) for m in mails])

    def range_(self, key, content, content_type=None):
        vu["fichier"].append(key)
        return key
    monkeypatch.setattr(st.LocalStorage, "save", range_)
    monkeypatch.setattr(st.S3Storage, "save", range_)

    def httpx_coupe(self, request):
        vu["reseau"].append((request.method, request.url.host))
        raise httpx.ConnectError("réseau coupé (test)", request=request)

    async def httpx_coupe_async(self, request):
        return httpx_coupe(self, request)

    def requests_coupe(self, request, **k):
        vu["reseau"].append((request.method, request.url))
        raise requests.ConnectionError("réseau coupé (test)")

    def urlopen_coupe(req, *a, **k):
        vu["reseau"].append((req.get_method() if hasattr(req, "get_method") else "GET", str(getattr(req, "full_url", req))))
        raise urllib.error.URLError("réseau coupé (test)")

    def smtp_coupe(*a, **k):
        vu["reseau"].append(("SMTP", str(a[:1])))
        raise OSError("réseau coupé (test)")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", httpx_coupe)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", httpx_coupe_async)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", requests_coupe)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_coupe)
    monkeypatch.setattr(smtplib, "SMTP", smtp_coupe)
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtp_coupe)
    return vu


@pytest.fixture
def garde_coupe(monkeypatch):
    """Simule un trou dans le garde central (le middleware ne bloque plus rien)."""
    import app.core.demo_guard as g
    monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)


def _avis(reel: bool) -> dict:
    from app.services.demo_search import search_results
    t = search_results()[0].model_dump(exclude={"raw"})
    if reel:
        t["provenance"]["official_ref"] = "26-123456"
    return t


def _appel(client, demo, c: Cout):
    ctx = demo["ctx"]
    url = c.chemin.format(**{p: ctx[k] for p, k in c.params}) + (("?" + c.query) if c.query else "")
    headers = {"pme": demo["pme"], "acheteur": demo["acheteur"]}.get(c.session, {})
    kw = {}
    corps = c.corps
    if isinstance(corps, tuple):
        mode, champs = corps
        data = {k: str(ctx.get(v, v)) for k, v in champs.items()}
        kw["data"] = data
        if mode == "fichier":
            kw["files"] = {"file": ("dossier.pdf", io.BytesIO(PDF), "application/pdf")}
    elif isinstance(corps, dict):
        body = dict(corps)
        if "tender" in body:
            body["tender"] = _avis(body["tender"] == "reel")
        for k in ("project_id", "document_id"):
            if isinstance(body.get(k), str) and body[k] in ctx:
                body[k] = ctx[body[k]]
        if body.get("email") == "demo":
            from app.services.demo_seed import DEMO_EMAIL
            body["email"] = DEMO_EMAIL
        kw["json"] = body
    return client.request(c.methode, url, headers=headers, **kw)


def _sans_cout(vu: dict, c: Cout, garde: bool = True):
    from app.routers.feedback import _FOUNDER
    assert vu["ia"] == [], f"{c.id} : appel à l'IA {vu['ia']}"
    emails = [e for e in vu["email"] if not (c.chemin == "/api/feedback" and e == _FOUNDER)]
    assert emails == [], f"{c.id} : email envoyé à {emails}"
    assert vu["fichier"] == [], f"{c.id} : fichier rangé {vu['fichier']}"
    ecritures = [x for x in vu["reseau"] if x[0] not in ("GET", "HEAD")]
    assert ecritures == [], f"{c.id} : écriture chez un tiers {ecritures}"
    if garde and not c.lectures:
        assert vu["reseau"] == [], f"{c.id} : appel réseau {vu['reseau']}"


_MSG_DEMO = ("lecture guidée", "démonstration", "Compte de démonstration")


def _refus_demo(r, c: Cout):
    if c.chemin.startswith("/api/knowledge/memoire") and r.status_code == 410:
        return                         # route retirée (remplacée par l'atelier) : rien n'est fait
    assert r.status_code == 403, (c.id, r.status_code, r.text)
    d = r.json().get("detail")
    d = d if isinstance(d, str) else str(d)
    assert any(m in d for m in _MSG_DEMO), (c.id, d)


# ── 1. Inventaire : toute route d'écriture est classée ─────────────────────────────────────────────

def _routes_d_ecriture():
    from fastapi.routing import APIRoute
    from app.main import app
    return {(m, r.path) for r in app.routes if isinstance(r, APIRoute)
            for m in r.methods if m not in ("GET", "HEAD", "OPTIONS")}


def test_inventaire_toutes_les_routes_d_ecriture_sont_classees():
    ecritures = _routes_d_ecriture()
    couts = {(c.methode, c.chemin) for c in COUTS}
    assert not (couts & set(SANS_COUT)), "une route ne peut pas être à la fois à coût et sans coût"
    manquantes = sorted(ecritures - couts - set(SANS_COUT))
    assert not manquantes, ("Routes d'écriture non classées : peuvent-elles coûter à la démo (IA, email, "
                            f"fichier, tiers) ? Classez-les dans COUTS ou SANS_COUT : {manquantes}")
    perimees = sorted((couts | set(SANS_COUT)) - ecritures)
    assert not perimees, f"Routes classées qui n'existent plus : {perimees}"


def test_chaque_regle_du_garde_vise_une_route_reelle():
    from app.core.demo_guard import _RULES
    ecritures = _routes_d_ecriture()
    for m, rx, action in _RULES:
        assert any(m == m2 and rx.match(p2) for m2, p2 in ecritures), (m, rx.pattern, action)


def test_les_routes_a_cout_de_la_session_pme_sont_bloquees_par_le_garde():
    """Le garde central refuse toute route à coût de la session PME, sauf celles servies sans coût
    (analyse d'un marché fictif, mot de passe oublié, avis au fondateur, aperçu d'une alerte), les
    routes du lien partenaire (refusées dans la route : un lien de la démo n'a pas de session) et
    l'analyse d'un avis réel (refusée plus bas, par le quota : l'avis fictif doit rester servi)."""
    from app.core.demo_guard import blocked_action
    for c in COUTS:
        if (c.session != "pme" or c.attendu != "refus" or c.chemin == "/api/sourcing/analyze"
                or c.chemin.startswith("/api/invite/")):
            continue
        url = re.sub(r"\{[^}]+\}", "7", c.chemin)
        assert blocked_action(c.methode, url.lower()), c.id


# ── 2. Démo à jour : écrans remplis (vitrine fraîche, avant les appels qui la touchent) ────────────────────────────────

def test_analyse_du_marche_grille_et_couverture(client, demo):
    pid = demo["ctx"]["toiture"]
    p = client.get(f"/api/projects/{pid}", headers=demo["pme"]).json()
    a = p["ai_analysis"]
    assert a["couverture"]["complet"] is True
    assert a["couverture"]["message"].startswith("Dossier lu en entier : 5 pièces")
    g = a["details"]["grille_notation"]
    assert [x["statut"] for x in g["criteres"]] == ["retrouve"] * 6
    assert [x["poids_retenu"] for x in g["criteres"]] == ["25 %", "15 %", "10 %", "5 %", "5 %", "40 %"]
    assert g["controle_total"]["statut"] == "ok" and g["ponderation"]["statut"] == "ponderes"
    assert all(x.get("phrase") for x in g["criteres"])                    # phrase retrouvée dans le règlement
    assert {x["type"] for x in g["contraintes"]["limites"]} == {"pages", "police"}
    assert p["match_score"] == 87 and p["go_decision"] == "go"            # même barème qu'avant
    lec = client.get(f"/api/sourcing/lecture/{pid}", headers=demo["pme"]).json()
    assert lec["integral"] is True and lec["couverture"]["totaux"]["lues_en_entier"] == 5


def test_dossier_du_marche_fictif_et_lu_en_entier(client, demo):
    from app.services import demo_redaction as dr
    from app.services.dce_lecture import lire_dossier
    lec = lire_dossier(dr.DCE_NOM, dr.dossier_zip(), mode="direct")
    assert len(lec["pieces"]) == 5 and all(p["statut"] == "lu_en_entier" for p in lec["pieces"])
    assert all(dr.BANDEAU[:40] in re.sub(r"\s+", " ", p["texte"]) for p in lec["pieces"])
    assert dr.dossier_zip() == dr.dossier_zip()                            # octets stables (clé de stockage)
    st = client.get(f"/api/atelier/{demo['ctx']['toiture']}", headers=demo["pme"]).json()
    da = st["dossier_acheteur"]
    assert da["integral"] is True and da["couverture"]["complet"] is True and len(da["pieces"]) == 5
    assert {p["type"] for p in da["pieces"]} == {"reglement", "cadre", "ccap", "cctp", "bordereau"}


def test_atelier_deja_redige(client, demo):
    st = client.get(f"/api/atelier/{demo['ctx']['toiture']}", headers=demo["pme"]).json()
    d = st["dossier"]
    assert d["plan_source"] == "grille"
    secs = st["sections"]
    assert [s["intitule"].split(" ")[0] for s in secs] == ["Méthodologie", "Organisation", "Moyens", "Planning",
                                                           "Gestion"]
    assert [s["poids"] for s in secs] == ["25 %", "15 %", "10 %", "5 %", "5 %"]
    assert all(s["poids_source"] == "reglement" for s in secs)
    assert [s["statut"] for s in secs] == ["valide", "brouillon", "valide", "relu", "valide"]
    assert all(s["version_courante"]["origine"] == "ia" and s["version_courante"]["texte"] for s in secs)
    # Ce qui reste à faire : un engagement à confirmer, un fait à relire ; deux parties à valider.
    raisons = {r["code"]: r for r in st["blocage"]["raisons"]}
    assert set(raisons) == {"faits_a_relire"} and raisons["faits_a_relire"]["nombre"] == 2
    a_relire = [f for s in secs for f in s["version_courante"]["faits"]]
    assert sorted(f["type"] for f in a_relire) == ["chiffre", "engagement"]
    assert any("7 semaines" in f["fait"] for f in a_relire)
    assert {x["code"] for x in st["derogations_possibles"]} >= {"relu_moi_meme", "depot_en_l_etat", "autre"}
    assert st["export"]["mention_ia"] == "Préparé avec assistance IA"
    assert st["limites"] and st["limites"][0]["valeur"] == 12 and not st["limites"][0]["depassee"]
    assert st["quota"]["analyse_debitee"] is True
    assert [x["critere"] for x in d["plan"]["criteres_hors_dossier"]] == ["Prix des prestations"]
    assert st["dossier_acheteur"]["a_change"] is False


def test_atelier_faits_relies_a_leurs_sources(demo):
    """Chaque renvoi des textes désigne une source réelle de la démo ; les faits sont reliés à
    « Mes preuves », « Mon savoir-faire », au chiffrage ou au dossier de l'acheteur (sans IA)."""
    from app.models import DossierSectionVersion, Preuve
    from app.services import faits_sources as fs
    db = _db()
    try:
        num = {p.numero for p in db.query(Preuve).filter(Preuve.owner_id == demo["ctx"]["uid"],
                                                          Preuve.statut == "acceptee").all()}
        vs = db.query(DossierSectionVersion).filter(DossierSectionVersion.project_id == demo["ctx"]["toiture"]).all()
        assert len(vs) == 5
        types = set()
        for v in vs:
            for ref in fs.refs_de(v.texte):
                if ref.startswith("F"):
                    assert int(ref[1:]) in num, ref
            sources = {x["ref"] for x in v.sources or []}
            assert {r for r in fs.refs_de(v.texte) if r.startswith("S")} <= sources
            for f in fs.avec_source(v.faits):
                types.add(f["source"]["type"])
        assert types >= {"documents", "justificatif", "declare", "estimation", "acheteur"}
        n_source = sum(len(fs.avec_source(v.faits)) for v in vs)
        assert n_source >= 30
    finally:
        db.close()


def test_equipe_cv_insere_sans_ia_et_jamais_remis_a_l_ia(demo):
    from app.core.org import member_ids
    from app.models import DossierSection, DossierSectionVersion, Project, User
    from app.services import atelier as at
    db = _db()
    try:
        u = db.get(User, demo["ctx"]["uid"])
        p = db.get(Project, demo["ctx"]["toiture"])
        s = (db.query(DossierSection).filter(DossierSection.project_id == p.id,
                                             DossierSection.intitule.like("Moyens%")).one())
        v = db.get(DossierSectionVersion, s.current_version_id)
        assert "**Yann Tanguy**" in v.texte and "**Erwan Le Bris**" in v.texte     # CV insérés tels quels
        ctx = at.Contexte(db, p, u.id, member_ids(u, db))
        pz = ctx.pseudonymiseur([f.texte for f in ctx.fiches(db)])
        lignes = [f.ligne_ia() for f in ctx.fiches(db, pseudonymiseur=pz) if f.nature == "salarie"]
        assert len(lignes) == 3
        for ln in lignes:
            for interdit in ("Tanguy", "Le Bris", "Hénaff", "BTS", "BP Couverture", "18 ans"):
                assert interdit not in ln, ln
    finally:
        db.close()


def test_mes_preuves_remplies(client, demo):
    r = client.get("/api/preuves", headers=demo["pme"]).json()
    pr = r["preuves"]
    par = {}
    for p in pr:
        par.setdefault(p["nature"], []).append(p)
    assert len(par["reference"]) == 3 and len(par["qualification"]) == 2 and len(par["salarie"]) == 3
    assert len(par["materiel"]) == 2 and len(par["chiffre_cle"]) == 4
    libelles = {p["source_libelle"] for p in pr}
    assert {"trouvé dans vos documents", "justificatif déposé", "déclaré par vous", "votre estimation"} <= libelles
    assert [p["statut"] for p in pr if p["statut"] != "acceptee"] == ["proposee"]
    assert all(p["utilisable"] for p in pr if p["statut"] == "acceptee")
    qualibat = next(p for p in par["qualification"] if p["valeur"]["nom"] == "Qualibat 3212")
    assert qualibat["source_libelle"] == "justificatif déposé" and qualibat["jours_restants"] is not None
    doc = next(p for p in par["reference"] if p["source_libelle"] == "trouvé dans vos documents")
    pas = client.get(f"/api/preuves/{doc['id']}/passage", headers=demo["pme"])
    assert pas.status_code == 200 and "Ville de Bréhaut" in pas.json()["passage"]
    assert client.get(f"/api/atelier/{demo['ctx']['toiture']}/preuves", headers=demo["pme"]).status_code == 200
    for p in par["salarie"]:
        assert set(p["valeur"]) <= {"nom", "fonction", "experience_annees", "diplomes", "qualifications", "chantiers"}


def test_vitrine_de_lorient_intacte(client, demo):
    pid = demo["ctx"]["lorient"]
    p = client.get(f"/api/projects/{pid}", headers=demo["pme"]).json()
    assert p["go_decision"] == "go_groupement" and p["groupement_score"] > p["match_score"]
    c = client.get(f"/api/projects/{pid}/contributions", headers=demo["pme"]).json()
    assert [x["company_name"] for x in c] == ["Breizh Désamiantage"] and c[0]["status"] == "submitted"
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=demo["pme"]).json()
    # Groupement montré jusqu'au dépôt (tests/test_demo_groupement_kerhel.py) : convention validée par tous.
    assert st["state"] == "pret_a_deposer" and st["convention_status"] == "signee"
    assert client.get(f"/api/invite/{demo['ctx']['token']}").status_code == 200


# ── 3. Aucun coût, avec puis sans le garde central ────────────────────────────────────────────────

@pytest.mark.parametrize("c", COUTS, ids=[c.id for c in COUTS])
def test_route_a_cout_ne_coute_rien_a_la_demo(client, demo, espions, c):
    r = _appel(client, demo, c)
    if c.attendu == "refus":
        _refus_demo(r, c)
    else:
        assert r.status_code < 500 or c.lectures, (c.id, r.status_code, r.text[:300])
    _sans_cout(espions, c)


@pytest.mark.parametrize("c", [c for c in COUTS if c.session == "pme"], ids=[c.id for c in COUTS if c.session == "pme"])
def test_route_a_cout_ne_coute_rien_meme_sans_le_garde(client, demo, espions, garde_coupe, c):
    """Défense en profondeur : même si le garde central était contourné, la route refuse elle-même
    (quota, exiger_ia, refuser_demo, liens de la démo) ou n'envoie rien."""
    r = _appel(client, demo, c)
    assert r.status_code < 500, (c.id, r.status_code, r.text[:300])
    _sans_cout(espions, c, garde=False)


def test_la_demo_ouverte_reste_utile(client, demo, espions):
    """Les routes à coût servies à la démo SANS coût rendent bien leur contenu."""
    r = _appel(client, demo, next(c for c in COUTS if c.attendu == "ouvert" and c.chemin == "/api/sourcing/analyze"))
    assert r.status_code == 200 and r.json()["score"] is not None and r.json()["details"].get("acheteur")
    c = next(c for c in COUTS if c.chemin == "/api/saved-searches/{search_id}/run")
    r = _appel(client, demo, c)
    assert r.status_code == 200 and r.json()["new_matches"] >= 1
    assert all(t["ref"].startswith("DEMO-") for t in r.json()["tenders"])
    assert client.post(f"/api/invite/{demo['ctx']['token']}/otp/request").json()["sent"] is False
    _sans_cout(espions, c)


def test_affichages_de_la_demo_sans_cout(client, demo, espions):
    """Toutes les routes de lecture (GET) restent ouvertes à la démo, et aucune ne coûte rien
    (seules des lectures de registres publics peuvent partir, jamais une écriture)."""
    from fastapi.routing import APIRoute
    from app.main import app
    ctx = demo["ctx"]
    valeurs = {"project_id": ctx["toiture"], "token": ctx["token"], "preuve_id": ctx["preuve"],
               "section_id": ctx["sid"], "doc_id": ctx["doc"], "dce_id": ctx["dce"]}
    vus = 0
    for r in app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods or not r.path.startswith("/api/"):
            continue
        url = re.sub(r"\{([^}]+)\}", lambda m: str(valeurs.get(m.group(1), 0)), r.path)
        h = demo["acheteur"] if r.path.startswith("/api/acheteur/") else demo["pme"]
        rep = client.get(url, headers=h, follow_redirects=False)
        non_configure = r.path.startswith("/api/auth/google/") and rep.status_code == 503
        assert rep.status_code < 500 or non_configure, (r.path, rep.status_code, rep.text[:200])
        vus += 1
    assert vus > 80
    assert espions["ia"] == [] and espions["email"] == [] and espions["fichier"] == []
    assert [x for x in espions["reseau"] if x[0] not in ("GET", "HEAD")] == []


def test_dernier_rempart_aucun_appel_ia_dans_l_espace_demo(demo, monkeypatch):
    """Même un appel direct au moteur, dans l'espace du compte démo, est refusé avant tout envoi."""
    from app.services import llm
    appels = []
    monkeypatch.setattr(llm, "_essayer", lambda *a, **k: appels.append(1))
    with llm.tenant_scope(demo["ctx"]["uid"]), pytest.raises(llm.LLMUnavailable) as e:
        llm.messages_create(tache="questions", max_tokens=5, messages=[{"role": "user", "content": "x"}])
    assert "lecture guidée" in str(e.value) and appels == []


# ── 4. Seed rejouable, sans IA, isolé ; textes fictifs ──────────────────────────────────────────

def _photo(db, uid):
    from app.models import (Document, DossierPresentation, DossierSection, DossierSectionVersion, KnowledgeDoc,
                            Preuve, Project)
    pids = [p.id for p in db.query(Project).filter(Project.user_id == uid).all()]
    return {
        "projets": sorted(p.name for p in db.query(Project).filter(Project.user_id == uid).all()),
        "documents": sorted((d.name, d.file_key) for d in db.query(Document).filter(Document.user_id == uid).all()),
        "kb": sorted(k.name for k in db.query(KnowledgeDoc).filter(KnowledgeDoc.user_id == uid).all()),
        "preuves": sorted((p.numero, p.nature, p.statut, p.type_source) for p in
                          db.query(Preuve).filter(Preuve.owner_id == uid).all()),
        "dossiers": db.query(DossierPresentation).filter(DossierPresentation.project_id.in_(pids)).count(),
        "parties": sorted((s.intitule, s.statut) for s in
                          db.query(DossierSection).filter(DossierSection.project_id.in_(pids)).all()),
        "textes": sorted(v.empreinte for v in
                         db.query(DossierSectionVersion).filter(DossierSectionVersion.project_id.in_(pids)).all()),
        "dossier_marche": sorted(p.dce_file_key or "" for p in db.query(Project).filter(Project.user_id == uid).all()),
    }


def test_seed_idempotent_rejouable_deux_fois_sans_ia_ni_fichier_nouveau(demo, espions):
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        avant = _photo(db, demo["ctx"]["uid"])
        espions["fichier"].clear()
        for _ in range(2):
            ensure_demo(db, force=True)
            assert _photo(db, demo["ctx"]["uid"]) == avant
    finally:
        db.close()
    assert espions["ia"] == [] and espions["email"] == [] and espions["reseau"] == []
    assert espions["fichier"] == []        # clés liées au contenu : rien de neuf à ranger au redémarrage
    assert avant["dossiers"] == 1 and len(avant["parties"]) == 5 and len(avant["preuves"]) == 14
    assert [n for n, *_ in avant["preuves"]] == list(range(1, 15))       # numéros stables F1 à F14


def test_seed_redaction_isole_dans_sa_transaction(demo, monkeypatch):
    """Un échec de la partie rédaction laisse le reste de la vitrine intact (et l'analyse d'origine)."""
    from app.models import DossierPresentation, Preuve, Project
    from app.services import demo_redaction as dr
    from app.services.demo_seed import ensure_demo

    def panne():
        raise RuntimeError("panne simulée")
    monkeypatch.setattr(dr, "dossier_zip", panne)
    db = _db()
    try:
        u = ensure_demo(db, force=True)
        projets = db.query(Project).filter(Project.user_id == u.id).all()
        assert len(projets) == 6
        toiture = next(p for p in projets if p.name.startswith("Réfection toiture"))
        assert "grille_notation" not in (toiture.ai_analysis or {}).get("details", {})
        assert toiture.match_score == 87
        assert db.query(DossierPresentation).filter(DossierPresentation.project_id == toiture.id).count() == 0
        assert db.query(Preuve).filter(Preuve.owner_id == u.id).count() == 0
        lorient = next(p for p in projets if "Kerhel" in p.name)
        assert lorient.go_decision == "go_groupement"
    finally:
        db.close()
    monkeypatch.undo()
    db = _db()
    try:
        ensure_demo(db, force=True)       # et tout revient au redémarrage suivant
        assert db.query(Preuve).filter(Preuve.owner_id == demo["ctx"]["uid"]).count() == 14
    finally:
        db.close()


def test_textes_de_la_demo_fictifs_et_sans_jargon():
    from app.services import demo_redaction as dr
    textes = [t for _n, titre, paras in dr.PIECES for t in [titre] + paras]
    textes += [t for p in dr.PARTIES for t in p["texte"]] + dr.REFERENCES_TEXTE + [dr.BANDEAU]
    tout = "\n".join(textes)
    assert "fictif" in dr.BANDEAU.lower()
    for mot in ("consortium", "signer", "signature", "signé", "mandataire", "Go/No-Go", "No-Go"):
        assert mot.lower() not in tout.lower(), mot
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", tout)
    # L'acheteur n'est jamais nommé dans le dossier fictif du marché.
    pieces = "\n".join(t for _n, titre, paras in dr.PIECES for t in [titre] + paras)
    for ville in ("Bordeaux", "Ville de", "Mairie", "Métropole"):
        assert ville not in pieces, ville


def test_vitrine_sans_jargon(client):
    """Ce que la vitrine affiche (synthèses, recommandations, marchés de « Trouver des marchés ») parle
    simplement : pas de « No-Go », pas de « consortium », pas de « mandataire »."""
    from app.models import Project, User
    from app.services.demo_search import _TENDERS
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        textes = []
        for p in db.query(Project).filter(Project.user_id == u.id).all():
            a = p.ai_analysis or {}
            textes += [p.ai_summary or "", a.get("summary") or "", (a.get("details") or {}).get("recommandation") or ""]
    finally:
        db.close()
    textes += [t["summary"] for t in _TENDERS] + [t["details"]["recommandation"] for t in _TENDERS]
    tout = "\n".join(textes).lower()
    for mot in ("no-go", "consortium", "mandataire"):
        assert mot not in tout, mot


# ── 5. Lien privé de démonstration : démo publique fermée, la démo complète par le lien ──────────

def _cle_neuve(sauf: str = "") -> str:
    """Clé neuve, même forme que la commande de docs/DEMO_LIEN_PRIVE.md (jamais écrite dans le dépôt)."""
    import secrets
    while True:
        cle = secrets.token_urlsafe(33)
        if cle != sauf:
            return cle


@pytest.fixture
def lien_prive(client, monkeypatch):
    """Comme en production depuis le 13/10/2026 : DEMO_PUBLIC absent, DEMO_LIEN_CLE posée. Vitrine
    remise à neuf, comme au démarrage du serveur."""
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    cle = _cle_neuve()
    monkeypatch.setenv("DEMO_LIEN_CLE", cle)
    return cle


# Écrans de la démo à jour (section 2), rejoués avec les sessions ouvertes par le lien privé.
_ECRANS_PME = (test_analyse_du_marche_grille_et_couverture, test_dossier_du_marche_fictif_et_lu_en_entier,
               test_atelier_deja_redige, test_mes_preuves_remplies, test_vitrine_de_lorient_intacte)


def test_lien_prive_de_bout_en_bout(client, lien_prive, espions, monkeypatch):
    """Démo publique fermée + lien privé : /demo, bonne clé, session entreprises puis session
    collectivités, écrans de la démo remplis, routes à coût refusées, aucun appel à l'IA, aucun email,
    aucun fichier rangé ; puis clé changée : toutes les sessions du lien sont coupées."""
    cle = lien_prive
    # Sans la clé, rien ne s'ouvre (démo publique fermée).
    for route in ("/api/auth/demo", "/api/acheteur/demo", "/api/auth/demo/lien"):
        assert client.post(route).status_code == 404
    page = client.get("/demo")
    assert page.status_code == 200 and "Espace entreprises" in page.text and cle not in page.text
    assert client.post("/api/auth/demo/lien", json={"cle": cle}).json() == {"ok": True}

    # Espace entreprises, puis espace collectivités.
    pme, ach = _sessions(client, {"cle": cle})
    d = {"pme": pme, "acheteur": ach, "ctx": _contexte()}
    assert client.get("/api/auth/me", headers=pme).json()["email"] == "demo@adjugo.fr"
    assert len(client.get("/api/projects/", headers=pme).json()) == 6
    r = client.post("/api/sourcing/search", headers=pme, json={"query": "toiture"}).json()
    assert r["count"] >= 1 and all(t["provenance"]["official_ref"].startswith("DEMO-") for t in r["tenders"])
    for ecran in _ECRANS_PME:
        ecran(client, d)
    assert client.get("/api/acheteur/me", headers=ach).json()["demo"] is True
    assert len(client.get("/api/acheteur/dce", headers=ach).json()) == 2
    test_affichages_de_la_demo_sans_cout(client, d, espions)      # toutes les lectures, sans coût

    # Les routes à coût restent refusées (ou servies sans coût) pour les sessions du lien.
    for c in COUTS:
        # Contrôle route par route (lectures de registres publics, avis au fondateur : permis sur leur
        # seule route) ; IA, email et fichier sont refusés à chaque appel, donc jamais cumulés.
        espions["reseau"].clear()
        espions["email"].clear()
        rep = _appel(client, d, c)
        if c.attendu == "refus":
            _refus_demo(rep, c)
        else:
            assert rep.status_code < 500 or c.lectures, (c.id, rep.status_code, rep.text[:300])
        _sans_cout(espions, c)

    # Clé changée : les deux sessions du lien sont coupées, l'ancienne clé n'ouvre plus rien.
    monkeypatch.setenv("DEMO_LIEN_CLE", _cle_neuve(sauf=cle))
    perime = "Ce lien de démonstration n'est plus valide."
    for url in ("/api/auth/me", "/api/projects/", f"/api/atelier/{d['ctx']['toiture']}", "/api/preuves"):
        rep = client.get(url, headers=pme)
        assert rep.status_code == 401 and rep.json()["detail"] == perime, url
    for url in ("/api/acheteur/me", "/api/acheteur/dce"):
        rep = client.get(url, headers=ach)
        assert rep.status_code == 401 and rep.json()["detail"] == perime, url
    assert client.post("/api/sourcing/ask", headers=pme, json={"question": "?"}).status_code == 401
    for route in ("/api/auth/demo", "/api/acheteur/demo", "/api/auth/demo/lien"):
        assert client.post(route, json={"cle": cle}).status_code == 404
    assert espions["ia"] == [] and espions["email"] == [] and espions["fichier"] == []


# ── 6. Revue avant de remettre la démo (13/10/2026) : fictive de bout en bout, exigences citées ──────────

# Collectivités et organismes RÉELS qu'une version précédente de la démo nommait (avec des contacts
# inventés sur leurs vrais domaines). Aucun ne doit revenir, ni en base ni dans les données du seed.
# (Les entreprises fictives, elles, sont installées dans de vraies villes : Nantes, Lorient, Lille, Tours, Lyon.)
_REELS = ("Bordeaux", "Lorient Agglomération", "Lorient (56)", "Niort", "Nantes Métropole", "La Rochelle",
          "Toulouse", "Nice (06)", "Nice Côte", "Angers", "Colmar", "SGAMI", "Limoges", "Limousin", "Chartres",
          "Clermont", "Millau", "Lanester", "Métropole Européenne de Lille", "Lille (59)", "Strasbourg",
          "Eurométropole", "Département du Rhône", "collège Ampère", "Quimper", "Pey-Berland", "Claude-Bernard",
          "interieur.gouv")
_TEL = re.compile(r"(?<!\d)0[1-9](?:[ .]?\d{2}){4}(?!\d)")
_COURRIEL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def _lignes(rows) -> str:
    import json
    out = []
    for r in rows:
        out.append(json.dumps({c.name: getattr(r, c.name) for c in r.__table__.columns},
                              ensure_ascii=False, default=str))
    return "\n".join(out)


def _donnees_de_la_demo() -> str:
    """Tout ce que la vitrine contient (PME et collectivités), tel qu'en base, plus les marchés de
    « Trouver des marchés » et le dossier fictif du marché « toiture »."""
    import json
    from app.models import (Acheteur, AcheteurDce, Company, Contact, CoMember, CoSpace, Document, Invoice,
                            KnowledgeChunk, KnowledgeDoc, Preuve, Project, ProjectContribution, ProjectInvite,
                            Signal, User)
    from app.routers.cotraitants import Cotraitant
    from app.services import demo_redaction as dr
    from app.services.acheteur_demo_seed import DEMO_EMAIL as ACH_EMAIL
    from app.services.demo_search import search_results
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        pids = [p.id for p in db.query(Project).filter(Project.user_id == u.id).all()]
        spaces = db.query(CoSpace).filter(CoSpace.owner_id == u.id).all()
        a = db.query(Acheteur).filter(Acheteur.email == ACH_EMAIL).one()
        tout = [_lignes(db.query(M).filter(M.user_id == u.id).all())
                for M in (Project, Company, Contact, Invoice, Signal, KnowledgeDoc, KnowledgeChunk, Document,
                          Cotraitant)]
        tout += [_lignes(db.query(Preuve).filter(Preuve.owner_id == u.id).all()),
                 _lignes(db.query(ProjectContribution).filter(ProjectContribution.project_id.in_(pids)).all()),
                 _lignes(db.query(ProjectInvite).filter(ProjectInvite.project_id.in_(pids)).all()),
                 _lignes(spaces),
                 _lignes(db.query(CoMember).filter(CoMember.space_id.in_([s.id for s in spaces])).all()),
                 _lignes([a]), _lignes(db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).all())]
    finally:
        db.close()
    tout.append(json.dumps([t.model_dump(mode="json", exclude={"raw"}) for t in search_results()], ensure_ascii=False))
    from app.services.demo_search import _TENDERS
    tout.append(json.dumps(_TENDERS, ensure_ascii=False))
    tout.append("\n".join(t for _n, titre, paras in dr.PIECES for t in [titre] + paras))
    tout.append("\n".join(t for p in dr.PARTIES for t in p["texte"]) + "\n".join(dr.REFERENCES_TEXTE))
    return "\n".join(tout)


def test_demo_entierement_fictive(client, demo):
    """Aucune collectivité réelle, aucun contact sur un vrai domaine, aucun numéro de téléphone : la démo
    remise pour la prospection ne prête rien (contact, marché, référence) à un organisme qui existe."""
    from app.services.acheteur_demo_seed import ensure_demo_acheteur
    db = _db()
    try:
        ensure_demo_acheteur(db)
    finally:
        db.close()
    tout = _donnees_de_la_demo()
    for nom in _REELS:
        assert nom not in tout, nom
    domaines = {m.group(1).lower() for m in _COURRIEL.finditer(tout)}
    assert domaines and all(d.endswith(".exemple") or d in ("adjugo.fr", "collectivites.adjugo.fr")
                            for d in domaines), sorted(domaines)
    assert not _TEL.findall(tout), _TEL.findall(tout)[:5]


def test_panneau_acheteur_de_la_demo_sans_boamp(client, demo, espions):
    """« Votre client (l'acheteur) » : jamais une requête au BOAMP pour la démo (acheteur fictif), donc
    jamais les vrais avis d'une collectivité réelle à côté d'un marché inventé."""
    for acheteur in ("Ville de Marvejac", "Ville de Bordeaux"):
        r = client.get("/api/sourcing/buyer-profile", params={"acheteur": acheteur}, headers=demo["pme"])
        assert r.status_code == 200 and r.json() == {"acheteur": acheteur, "found": False, "demo": True}
    assert espions["reseau"] == []
    html = (STATIC / "app.html").read_text(encoding="utf-8")
    assert 'v-else-if="ao.buyer && ao.buyer.demo"' in html and "Acheteur fictif de la démonstration" in html


def test_exigences_du_marche_toiture_citees_par_son_dossier(client, demo):
    """« Dossier lu en entier » : chaque exigence affichée (chiffre d'affaires minimum, qualifications,
    variantes) est écrite dans le règlement fictif, citée et vérifiée ; « Répondre à plusieurs ? » montre
    la phrase du dossier sous le chiffre d'affaires exigé."""
    from app.services import demo_redaction as dr
    from app.services.analysis import citation_guard
    from app.services.dce_lecture import lire_dossier
    pid = _contexte()["toiture"]       # relu en base : un test précédent a pu remettre la vitrine à neuf (Postgres ne réutilise pas les identifiants)
    det = client.get(f"/api/projects/{pid}", headers=demo["pme"]).json()["ai_analysis"]["details"]
    assert det["exigences_verifiees"]["ca_minimum_requis"] is True
    assert det["exigences_verifiees"]["qualifications_requises"] is True
    assert det["exigences_sources"]["ca_minimum_requis"] == dr.EXIGENCE_CA
    assert det["exigences_sources"]["qualifications_requises"] == dr.EXIGENCE_QUALIFICATIONS
    texte = "\n".join(p["texte"] for p in lire_dossier(dr.DCE_NOM, dr.dossier_zip(), mode="direct")["pieces"])
    for phrase in (dr.EXIGENCE_CA, dr.JUSTIFICATION_CA, dr.EXIGENCE_QUALIFICATIONS, dr.EXIGENCE_VARIANTES):
        assert citation_guard(texte, phrase), phrase
    # Ce que la fiche affiche correspond à ce que le règlement écrit.
    assert "1 500 000" in det["ca_minimum_requis"] and "1 500 000" in dr.EXIGENCE_CA
    assert all(q in dr.EXIGENCE_QUALIFICATIONS for q in det["qualifications_requises"])
    assert "matériaux d'étanchéité" in det["variantes"] and "matériaux d'étanchéité" in dr.EXIGENCE_VARIANTES
    # « Répondre à plusieurs ? » : le chiffre d'affaires exigé, avec la phrase du dossier.
    b = client.get(f"/api/projects/{pid}/groupement/besoins", headers=demo["pme"]).json()
    ca = next(g for g in b["gaps"] if g["key"] == "capacite")
    assert ca["severity"] == "bloquant" and ca["extrait"] == dr.EXIGENCE_CA
    # La recommandation dit la même chose que la carte : seul, la candidature serait écartée.
    assert "sans être rédhibitoire" not in det["recommandation"]
    assert "Seul, la candidature serait écartée" in det["recommandation"]


def test_rge_reliee_a_son_justificatif_et_pas_proposee_en_double(client, demo):
    """« Mes preuves » : la qualification RGE est reliée à l'« Attestation RGE » de Mes documents (comme
    Qualibat) ; elle n'est donc plus proposée une seconde fois dans « Voir et reprendre »."""
    pr = client.get("/api/preuves", headers=demo["pme"]).json()["preuves"]
    rge = next(p for p in pr if p["nature"] == "qualification" and p["valeur"]["nom"] == "RGE")
    assert rge["source_libelle"] == "justificatif déposé" and rge["jours_restants"] is not None
    rep = client.get("/api/preuves/reprise", headers=demo["pme"]).json()
    assert not [e for e in rep["elements"] if e["nature"] == "qualification"], rep["elements"]
    assert rep["a_reprendre"] == len(rep["elements"])


def test_dce_de_la_demo_collectivites_remplaces_quand_le_seed_change(client):
    """La démo collectivités d'un serveur déjà en service (DCE d'exemple d'avant, avec une commune réelle)
    reçoit les nouveaux DCE d'exemple au prochain accès ; sinon rien ne bouge (mêmes lignes)."""
    from app.models import Acheteur, AcheteurDce
    from app.services import acheteur_demo_seed as ads
    db = _db()
    try:
        a = ads.ensure_demo_acheteur(db)
        db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).delete(synchronize_session=False)
        db.add(AcheteurDce(acheteur_id=a.id, objet="Rénovation de l'école des Tilleuls à Quimper (29)",
                           payload={"objet": "Rénovation de l'école des Tilleuls à Quimper (29)"}))
        db.commit()
        ads.ensure_demo_acheteur(db)
        rows = db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).order_by(AcheteurDce.id).all()
        attendus = ads._items()
        assert len(rows) == len(attendus) == 2
        assert sorted(r.objet for r in rows) == sorted(it["objet"] for it in attendus)
        assert all("Quimper" not in _lignes([r]) for r in rows)
        ids = [r.id for r in rows]
        ads.ensure_demo_acheteur(db)
        assert [r.id for r in db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id)
                .order_by(AcheteurDce.id).all()] == ids                       # idempotent
        assert db.query(Acheteur).filter(Acheteur.email == ads.DEMO_EMAIL).one().nom_collectivite.startswith(
            "Mairie de Démoville")
    finally:
        db.close()
