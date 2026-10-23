"""
Demandes d'accès / de démonstration (page publique /demande-acces).

Remplace la démo publique sans mot de passe (décision fondateur, 08/10/2026). Le visiteur
laisse ses coordonnées ; la demande part par email à l'adresse de contact d'Adjugo
(CONTACT_EMAIL, défaut contact@adjugo.pro), avec « Répondre à » = l'adresse du demandeur.

Anti-abus (même doctrine que l'audit cyber) :
  • AUCUN email n'est envoyé à l'adresse saisie (sinon le formulaire anonyme devenait un
    canal d'envoi d'emails signés Adjugo vers n'importe qui) — confirmation à l'écran ;
  • champ piège invisible (robots) ; limites par IP ;
  • valeurs bornées, sans saut de ligne dans les champs d'une ligne (objet de l'email).
Rien n'est stocké en base : la demande vit dans la boîte de contact. Si l'envoi échoue, le
visiteur le sait (503) et reçoit l'adresse pour écrire directement.
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.ratelimit import limiter

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/contact", tags=["Site"])

PROFILS = {
    "entreprise": "Entreprise (TPE, PME, artisan)",
    "collectivite": "Collectivité ou acheteur public",
    "autre": "Autre",
}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_PHONE = re.compile(r"^[0-9+().\s-]{6,30}$")


def contact_email() -> str:
    return (os.getenv("CONTACT_EMAIL") or "contact@adjugo.pro").strip()


# Page de réservation Cal.com d'Eliot (lien public, non secret). BOOKING_URL la remplace ;
# BOOKING_URL=off (ou vide) masque le bouton de réservation.
DEFAULT_BOOKING_URL = "https://cal.com/eliot-viegas-adjugo/reservez-ma-demo-adjugo"


def booking_url():
    """Lien de prise de rendez-vous (Cal.com, Calendly…) — https uniquement."""
    from app.schemas import safe_link_url
    raw = os.environ.get("BOOKING_URL")
    u = (DEFAULT_BOOKING_URL if raw is None else raw).strip()
    if u.lower() in ("", "off", "non", "none"):
        return None
    return u if u.lower().startswith("https://") and safe_link_url(u, 500) else None


def _line(v: str) -> str:
    """Champ d'une ligne : espaces normalisés, aucun caractère de contrôle."""
    return " ".join(_CTRL.sub(" ", v or "").split())


class DemandeIn(BaseModel):
    prenom: str = Field(..., max_length=80)
    nom: str = Field(..., max_length=80)
    email: EmailStr
    organisation: str = Field(..., max_length=160)
    telephone: str = Field("", max_length=30)
    profil: Literal["entreprise", "collectivite", "autre"] = "entreprise"
    message: str = Field("", max_length=2000)
    site_web: str = Field("", max_length=200)   # piège à robots : invisible pour un humain

    @field_validator("prenom", "nom", "organisation")
    @classmethod
    def _requis(cls, v):
        v = _line(v)
        if not v:
            raise ValueError("Champ obligatoire.")
        return v

    @field_validator("telephone")
    @classmethod
    def _tel(cls, v):
        v = _line(v)
        if v and not _PHONE.match(v):
            raise ValueError("Numéro de téléphone invalide.")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return str(v).strip().lower()

    @field_validator("message")
    @classmethod
    def _msg(cls, v):
        # Sauts de ligne conservés (corps du mail), autres contrôles retirés.
        return re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", v or "").strip()


@router.get("/config")
def config():
    """Ce dont la page a besoin : le lien de rendez-vous (s'il existe) et l'adresse de repli."""
    return {"booking_url": booking_url(), "email": contact_email()}


@router.post("/demande-acces")
@limiter.limit("5/hour")
@limiter.limit("20/day")
def demande_acces(request: Request, data: DemandeIn):
    if data.site_web.strip():
        # Robot : on répond comme si tout allait bien, sans rien envoyer.
        logger.info("demande d'accès ignorée (champ piège rempli)")
        return {"ok": True}
    profil = PROFILS[data.profil]
    sujet = f"Demande d'accès — {data.organisation} ({profil})"[:150]
    quand = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    lignes = [
        "Nouvelle demande d'accès depuis adjugo.pro",
        "",
        f"Nom : {data.prenom} {data.nom}",
        f"Email : {data.email}",
        f"Téléphone : {data.telephone or 'non renseigné'}",
        f"Structure : {data.organisation}",
        f"Profil : {profil}",
        f"Reçue le : {quand}",
        "",
        "Message :",
        data.message or "(aucun message)",
        "",
        "Répondre à cet email écrit directement à la personne.",
    ]
    from app.services import email as _email
    ok = False
    try:
        ok = _email.send_email(contact_email(), sujet, "\n".join(lignes), reply_to=data.email)
    except Exception:
        ok = False
    if not ok:
        logger.warning("demande d'accès NON transmise (envoi email en échec) profil=%s", data.profil)
        raise HTTPException(503, f"L'envoi n'a pas abouti. Réessayez dans un instant ou écrivez-nous "
                                 f"directement à {contact_email()}.")
    logger.info("demande d'accès transmise profil=%s", data.profil)
    return {"ok": True}
