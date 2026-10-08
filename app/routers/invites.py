"""
Adjugo — Partage d'un appel d'offres avec un co-traitant externe (vue bridée).

Le mandataire génère un lien secret limité à UN projet. Le co-traitant l'ouvre
SANS compte et n'accède qu'à une vue restreinte de ce seul projet (résumé + pièces
partagées). Chaque consultation/téléchargement est tracé dans le journal d'accès
(RGPD). La portée est TOUJOURS contrainte côté serveur à `invite.project_id` :
aucune route invité ne lit jamais une autre donnée du tenant.
"""
import base64
import io
import mimetypes
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import get_db
from app.core.org import data_owner_id, member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import (AuditLog, Company, ContributionPiece, Document, Organization, Project,
                        ProjectContribution, ProjectInvite, User, utcnow)
from app.schemas import safe_link_url
from app.services import audit
from app.services.groupement_members import (active_invite_filter, active_invites,
                                             groupement_state, submitted_contributions,
                                             total_offre_ht)
from app.services.storage import get_storage

router = APIRouter(tags=["Co-traitance"])
_settings = get_settings()

import hashlib

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_TTL_MIN = 15
_OTP_MAX_ATTEMPTS = 5


def _is_email(s) -> bool:
    return bool(_EMAIL_RE.match((s or "").strip()))


def _binding_required(inv) -> bool:
    """Le binding d'identité OTP s'applique UNIQUEMENT si l'email est configuré ET le
    destinataire est une adresse. Sinon : flux inchangé, zéro friction (l'ADN CaaS).
    Jamais pour une invitation de la démo publique : aucun code n'y est envoyé."""
    try:
        from app.services import email as _email
        if not (_email.is_enabled() and _is_email(getattr(inv, "recipient", ""))):
            return False
        from sqlalchemy.orm import object_session
        sess = object_session(inv)
        return not (sess is not None and _invite_is_demo(inv, sess))
    except Exception:
        return False


_DEMO_INVITE_MSG = ("La démo est en lecture guidée : créez votre compte gratuit pour "
                    "co-construire une réponse avec vos partenaires.")


def _invite_is_demo(inv, db: Session) -> bool:
    """Vrai si l'invitation appartient au compte démo public (vitrine) : aucun email ne doit
    partir de ses liens invités, et ses pièces ne sont pas modifiables (vitrine partagée)."""
    try:
        from app.services.demo_search import is_demo
        owner = db.query(User).filter(User.id == inv.owner_id).first()
        return bool(owner and is_demo(owner))
    except Exception:
        return False


def _refuse_if_demo_invite(inv, db: Session) -> None:
    if _invite_is_demo(inv, db):
        raise HTTPException(403, _DEMO_INVITE_MSG)


def _mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return e
    user, _, dom = e.partition("@")
    return ((user[0] + "***") if user else "***") + "@" + dom


def _audit_email_detail(inv) -> str:
    """Détail d'audit des codes de vérification. Le journal complet est lisible par le chef de
    file : pour une invitation RÉSEAU (adresse remplie par Adjugo et masquée), on n'y écrit
    même pas l'adresse masquée (le domaine suffirait à identifier l'entreprise)."""
    if (getattr(inv, "source", "") or "") == "reseau_adjugo":
        return ""
    return _mask_email(inv.recipient)


def _send_mails_async(mails: list) -> None:
    """Envoie une liste de (destinataire, sujet, texte) dans un thread démon : les
    notifications de groupement sont best-effort et ne doivent JAMAIS retenir la réponse
    HTTP (un SMTP lent bloquait 45 s le figement de l'offre). Les valeurs sont capturées
    AVANT le thread : aucune session DB n'y est utilisée."""
    if not mails:
        return
    import threading

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


def _hash_otp(code: str) -> str:
    return hashlib.sha256(("adjugo-otp:" + (code or "")).encode("utf-8")).hexdigest()


def _send_invite_email(inv, project, base_url: str) -> bool:
    """Envoie le lien d'invitation au co-traitant. No-op gracieux si email désactivé.
    Horodate l'envoi réussi (emailed_at) → le mandataire voit si le mail est parti."""
    if not _is_email(inv.recipient):
        return False
    try:
        from app.services import email as _email
        url = base_url.rstrip("/") + f"/invite/{inv.token}"
        who = inv.company_name or "votre entreprise"
        subj = f"Invitation à co-traiter sur un marché — {project.name[:60]}"
        text = (f"Bonjour,\n\nVous êtes invité(e) à rejoindre le groupement pour répondre au "
                f"marché « {project.name} » sur Adjugo, en tant que {who}.\n\n"
                f"Accédez à votre espace dédié (cloisonné à ce seul dossier) :\n{url}\n\n"
                f"Vous n'y voyez que ce dossier et votre propre contribution — jamais les "
                f"données des autres partenaires.\n\n— Adjugo, le réseau des PME")
        sent = _email.send_email(inv.recipient, subj, text)
        if sent:
            inv.emailed_at = utcnow()
        return sent
    except Exception:
        return False


def _mandataire_email(owner_id: int, db: Session) -> Optional[str]:
    """Email du mandataire (propriétaire du tenant) pour les notifications de groupement.
    Aucun pour le compte démo public (la démo n'envoie jamais d'email)."""
    u = db.query(User).filter(User.id == owner_id).first()
    if u:
        from app.services.demo_search import is_demo
        if is_demo(u):
            return None
        # Adresse non prouvée = jamais de notification : sinon on posait l'adresse d'un
        # tiers sur son compte puis on faisait soumettre une part en boucle (spam Adjugo).
        if not getattr(u, "email_verified", False):
            return None
    return (u.email if u and _is_email(u.email or "") else None)


# Anti-rafale des notifications par invitation (process unique : en mémoire suffit).
_NOTIFY_LAST: dict = {}
_NOTIFY_LOCK = __import__("threading").Lock()
NOTIFY_MIN_INTERVAL_S = 30 * 60


def _notify_allowed(key) -> bool:
    import time
    now = time.time()
    with _NOTIFY_LOCK:
        last = _NOTIFY_LAST.get(key)
        if last is not None and now - last < NOTIFY_MIN_INTERVAL_S:
            return False
        _NOTIFY_LAST[key] = now
        if len(_NOTIFY_LAST) > 20000:      # borne mémoire
            _NOTIFY_LAST.clear()
        return True


def _notify_part_submitted(inv, contribution, db: Session) -> None:
    """Prévient le mandataire par email qu'une part vient d'être soumise (best-effort).
    Un dirigeant ne rafraîchit pas Adjugo toute la journée : sans ça, il peut rater une
    part reçue à la veille du dépôt."""
    try:
        to = _mandataire_email(inv.owner_id, db)
        if not to or not _notify_allowed(("part_submitted", inv.id)):
            return
        from app.services import email as _email
        project = db.query(Project).filter(Project.id == inv.project_id).first()
        pname = (project.name if project else "votre marché")
        who = contribution.company_name or inv.company_name or "Un partenaire"
        # X/Y partenaires prêts (parts soumises / invitations actives du projet).
        total = len(active_invites(db, inv.project_id))
        done = len(submitted_contributions(db, inv.project_id))
        base = (_settings.APP_BASE_URL or "").rstrip("/")
        subj = f"{who} a soumis sa part — {pname[:60]}"
        text = (f"Bonjour,\n\n{who} vient de soumettre sa part sur le marché « {pname} ».\n"
                f"Partenaires prêts : {done}/{total}.\n\n"
                f"Ouvrez le cockpit du groupement pour assembler la réponse commune :\n{base}/app\n\n"
                f"— Adjugo")
        _email.send_email(to, subj, text)
    except Exception:
        pass


def _notify_partner_received(inv, db: Session) -> None:
    """Accusé de réception au partenaire après soumission (best-effort) : une trace écrite
    rassure un dirigeant qui vient d'envoyer une pièce engageante à un marché public."""
    try:
        if not _is_email(inv.recipient) or _invite_is_demo(inv, db):
            return
        if not _notify_allowed(("part_received", inv.id)):
            return
        from app.services import email as _email
        project = db.query(Project).filter(Project.id == inv.project_id).first()
        pname = (project.name if project else "le marché")
        owner_company = db.query(Company).filter(Company.user_id == inv.owner_id).first()
        chef = (owner_company.name if owner_company and owner_company.name else "le chef de file")
        subj = f"Votre part a bien été transmise — {pname[:60]}"
        text = (f"Bonjour,\n\nVotre part sur le marché « {pname} » a bien été transmise à "
                f"{chef}.\n\nVous pouvez encore l'ajuster (texte et pièces) jusqu'à la date "
                f"limite via votre lien. Toute modification après envoi repasse votre part en "
                f"brouillon : pensez à la re-soumettre.\n\n— Adjugo, le réseau des PME")
        _email.send_email(inv.recipient, subj, text)
    except Exception:
        pass
_ALLOWED_EXT = {e.strip().lower() for e in _settings.ALLOWED_UPLOAD_EXT.split(",") if e.strip()}
_MAX_BYTES = _settings.MAX_UPLOAD_MB * 1024 * 1024


def _read_upload(file: UploadFile) -> tuple:
    """Valide extension + taille d'un fichier téléversé par un invité ; (contenu, ext)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if _ALLOWED_EXT and ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Type de fichier non autorisé ({ext or 'inconnu'}).")
    # Lecture BORNÉE : on ne charge jamais plus de la limite +1 octet en mémoire (l'upload
    # vient d'un invité non authentifié → un fichier géant ne doit pas gonfler le process).
    content = file.file.read(_MAX_BYTES + 1)
    if not content:
        raise HTTPException(400, "Fichier vide")
    if len(content) > _MAX_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux (max {_settings.MAX_UPLOAD_MB} Mo)")
    return content, ext


def _safe_mime(filename: str) -> str:
    """Type MIME DÉRIVÉ de l'extension (jamais le Content-Type fourni par le client) :
    l'extension étant en liste blanche (pdf/png/doc…), on ne peut jamais servir du
    text/html → pas de XSS au téléchargement. Repli neutre forçant le download.
    Table FIXE (app.core.mime), pas `mimetypes` qui dépend de la machine."""
    from app.core.mime import mime_for
    return mime_for(filename)


def _attachment_headers(name: str) -> dict:
    """Content-Disposition robuste : pas d'injection d'en-tête possible via le nom de
    fichier (guillemets/CRLF). Repli ASCII + variante RFC 5987 (filename*)."""
    base = os.path.basename(name or "fichier")
    ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", base) or "fichier"
    return {"Content-Disposition":
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(base, safe='')}",
            "X-Content-Type-Options": "nosniff"}

# Sous-ensemble SÛR de l'analyse exposé au co-traitant : FAITS PUBLICS du marché (déjà
# dans l'avis publié), de quoi comprendre et préparer sa part — SANS la stratégie interne
# du mandataire (score, faiblesses) NI le montant estimé (= cible de prix : un co-traitant
# pourrait s'en servir pour caler son lot ; il chiffre sa part sur sa propre base).
#
# IMPORTANT : on MAPPE les clés RÉELLES de l'analyse (intitule_marche, lieu_execution,
# delai_execution…) vers les clés attendues par la vue co-traitant (invite.html : objet, lieu,
# duree…). Sans ce mapping, l'objet/le lieu/la durée n'apparaissaient JAMAIS (clés muettes) et
# le partenaire devait redemander ces infos par email — l'inverse de l'espace autonome promis.
_SAFE_KEY_MAP = {
    "intitule_marche": "objet", "objet": "objet",
    "acheteur": "acheteur",
    "lieu_execution": "lieu", "lieu": "lieu",
    "delai_execution": "duree", "duree": "duree", "delais": "delais",
    "type_marche": "type_marche",
    "nature_marche": "procedure", "procedure": "procedure",
    "allotissement": "allotissement",
    "criteres_attribution": "criteres_attribution",
    "date_limite": "date_limite",
}


# ── Sérialisation bridée ─────────────────────────────────────────────────────
def _safe_analysis(ai_analysis) -> dict:
    if not isinstance(ai_analysis, dict):
        return {}
    details = ai_analysis.get("details") if isinstance(ai_analysis.get("details"), dict) else ai_analysis
    if not isinstance(details, dict):
        return {}
    out = {}
    for real_key, front_key in _SAFE_KEY_MAP.items():
        if front_key in out:                       # 1ère clé non vide gagne (clé réelle avant alias)
            continue
        v = details.get(real_key)
        if v not in (None, "", [], {}):
            out[front_key] = v
    return out


def _plan_breakdown_ok(breakdown, key: str) -> bool:
    """Lit le statut EN GROUPEMENT d'un critère du plan (dict {clé: {...}} ou liste
    [{key|critere, status_groupement}]) → booléen. Tolérant : le plan vient d'un autre
    service (groupement_scoring) et peut être absent ou partiel."""
    try:
        if isinstance(breakdown, dict):
            item = breakdown.get(key)
            return isinstance(item, dict) and item.get("status_groupement") == "ok"
        if isinstance(breakdown, list):
            for item in breakdown:
                if isinstance(item, dict) and (item.get("key") == key or item.get("critere") == key):
                    return item.get("status_groupement") == "ok"
    except Exception:
        pass
    return False


def _label_of(x) -> str:
    """Un apport/manque du plan est soit une chaîne, soit {key,label} → libellé lisible."""
    if isinstance(x, dict):
        return str(x.get("label") or x.get("key") or "")
    return str(x or "")


def _for_member(inv: ProjectInvite, project: Project, db: Session) -> dict:
    """Vue co-traitant « Pourquoi vous dans ce groupement » : le % COMMUN (jamais le score
    seul du mandataire), SON apport, les seuils en booléens (jamais les chiffres des
    autres), l'étape du groupement SANS has_price des autres, et le total SEULEMENT une
    fois l'offre figée."""
    st = groupement_state(project, db)
    plan = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()

    # Rapprochement de MON entrée dans plan.members : invite_id, sinon siret, sinon nom.
    my_siret = (c.siret if c and c.siret else "").strip()
    my_name = ((c.company_name if c and c.company_name else inv.company_name) or "").strip().lower()
    mine = None
    for m in (plan.get("members") or []):
        if not isinstance(m, dict):
            continue
        if m.get("invite_id") and m.get("invite_id") == inv.id:
            mine = m
            break
    if mine is None and my_siret:
        mine = next((m for m in (plan.get("members") or []) if isinstance(m, dict)
                     and str(m.get("siret") or "").strip() == my_siret), None)
    if mine is None and my_name:
        mine = next((m for m in (plan.get("members") or []) if isinstance(m, dict)
                     and str(m.get("name") or "").strip().lower() == my_name), None)
    # Apports = clés de critères ('metier', 'capacite'…) → libellés lisibles via le breakdown.
    breakdown = plan.get("breakdown")
    label_by_key = {}
    try:
        items = breakdown.values() if isinstance(breakdown, dict) else (breakdown or [])
        for it in items:
            if isinstance(it, dict) and (it.get("key") or it.get("critere")):
                label_by_key[it.get("key") or it.get("critere")] = it.get("label") or ""
        if isinstance(breakdown, dict):
            for k, it in breakdown.items():
                if isinstance(it, dict):
                    label_by_key.setdefault(k, it.get("label") or "")
    except Exception:
        label_by_key = {}
    my_apport = []
    for a in ((mine or {}).get("apporte") or []):
        key = a.get("key") if isinstance(a, dict) else str(a or "")
        if not key:
            continue
        label = (a.get("label") if isinstance(a, dict) else None) or label_by_key.get(key) or key
        my_apport.append({"key": key, "label": label})

    n_members = int(st.get("n_members") or 0)
    # Total de l'offre : membres du groupement seulement. Jamais un sous-traitant ; et, une fois la
    # convention générée, seulement un signataire (un lien ajouté après la génération ne l'a pas).
    sees_total = bool(st.get("offer_frozen")) and (inv.role or "") != "sous_traitant"
    if sees_total:
        try:
            from app.services import groupement_convention as _gc
            _conv = _gc.get_convention(db, project.id)
            if _conv is not None and _conv.status in ("a_signer", "signee", "perimee"):
                sees_total = any(s.invite_id == inv.id for s in _gc.signatures_of(db, _conv))
        except Exception:
            sees_total = False
    return {
        "state": {
            "state": st.get("state"), "label": st.get("label"), "index": st.get("index"),
            "steps": st.get("steps"), "n_members": n_members, "n_submitted": st.get("n_submitted"),
            "offer_frozen": bool(st.get("offer_frozen")),
            "total_offre_ht": st.get("total_offre_ht") if sees_total else None,
            "frozen_at": st.get("frozen_at") if sees_total else None,
            # Liste des membres RÉDUITE : jamais has_price / prix d'un autre.
            "members": [{"company": m.get("company"), "role": m.get("role"), "status": m.get("status")}
                        for m in (st.get("members") or [])],
            # Vague 2 : stepper 1→5 + résumé de la convention (statuts et compteurs seulement).
            "etape": st.get("etape"), "etapes": st.get("etapes"),
            "convention": st.get("convention"),
        },
        "my_apport": my_apport,
        "score_groupement": project.groupement_score,     # le % COMMUN, jamais match_score
        "gaps_combles": [_label_of(g) for g in (plan.get("gaps_combles") or []) if _label_of(g)],
        "seuils": {"ca_cumule_ok": _plan_breakdown_ok(breakdown, "capacite"),
                   "qualifs_ok": _plan_breakdown_ok(breakdown, "qualifs")},
        # À 2 membres (mandataire + 1 partenaire), le total révèle la part de l'autre.
        "warning_two_members": (n_members + 1) == 2,
        "my_capacites": (c.capacites if c and isinstance(c.capacites, dict) else None),
    }


def _invite_public(inv: ProjectInvite, project: Project, owner_company: Optional[Company],
                   docs: list, db: Session = None) -> dict:
    out = {
        "project": {
            "name": project.name,
            "client": project.client,
            # NB : on N'expose PAS `ai_summary` — il est éditorialisé et peut révéler la
            # décision interne du mandataire (Go/No-Go, faiblesses). On ne donne que des
            # FAITS sur le marché (objet, lots, critères, échéance).
            "deadline": project.deadline.isoformat() if project.deadline else None,
            # Assaini à la LECTURE : une valeur ancienne (antérieure à la validation) ne
            # ressort jamais en « javascript: » dans l'espace cloisonné du partenaire.
            "source_url": safe_link_url(project.source_url),
            "analysis": _safe_analysis(project.ai_analysis),
        },
        "mandataire": (owner_company.name if owner_company else "") or "",
        "invited": {"recipient": inv.recipient, "company": inv.company_name,
                    "role": inv.role or "cotraitant"},
        "can_view_docs": bool(inv.can_view_docs),
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "documents": docs,
        "shared_at": inv.created_at.isoformat() if inv.created_at else None,
    }
    if db is not None:
        try:
            out["for_member"] = _for_member(inv, project, db)
        except Exception:
            out["for_member"] = None
    # Invitation RÉSEAU pas encore acceptée : APERÇU MINIMAL (objet, lots, lieu, échéance,
    # chef de file) — ni acheteur, ni lien de l'avis, ni pièces. Protège le chef de file d'un
    # concurrent déguisé tant que le partenaire n'a pas accepté depuis son compte.
    if _network_pending(inv, db):
        out["project"]["client"] = None
        out["project"]["source_url"] = None
        out["project"]["analysis"] = {k: v for k, v in (out["project"].get("analysis") or {}).items()
                                      if k != "acheteur"}
        out["documents"] = []
        out["can_view_docs"] = False
        # Ni composition du groupement, ni score commun avant acceptation (stratégie du chef de file).
        out["for_member"] = None
        out["apercu_minimal"] = True
        out["apercu_message"] = ("Aperçu limité : acceptez l'invitation depuis votre compte Adjugo pour voir "
                                 "le dossier complet (acheteur, pièces du marché).")
    else:
        out["apercu_minimal"] = False
    return out


# ── Côté MANDATAIRE (authentifié) ────────────────────────────────────────────
class InviteCreate(BaseModel):
    recipient: str = ""
    company_name: str = ""
    role: str = "cotraitant"        # cotraitant | sous_traitant
    can_view_docs: bool = True
    can_contribute: bool = True     # autorise la co-construction (apport de sa part)
    expires_days: int = 30          # 0 = sans expiration


def _owned_project(pid: int, user: User, db: Session) -> Project:
    # Portée ORGANISATION : un coéquipier accède au même AO (cohérent avec la liste
    # « Mes marchés », le chiffrage, les CERFA, l'export). Sans ça, un membre ouvrant
    # l'AO d'un collègue recevait un 404 alors qu'il le voyait dans la liste.
    p = db.query(Project).filter(
        Project.id == pid, Project.user_id.in_(member_ids(user, db)), Project.deleted_at.is_(None)
    ).first()
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def _invite_state(inv: ProjectInvite, contribution: "ProjectContribution" = None) -> str:
    """État CALCULÉ d'une invitation, du plus définitif au plus initial :
    revoked | declined | expired | submitted | draft | viewed | sent."""
    if inv.revoked:
        return "revoked"
    if getattr(inv, "declined_at", None):
        return "declined"
    if _is_expired(inv.expires_at):
        return "expired"
    if contribution and contribution.status == "submitted":
        return "submitted"
    if contribution:
        return "draft"
    if inv.view_count:
        return "viewed"
    return "sent"


def _is_network_invite(inv) -> bool:
    return (getattr(inv, "source", "") or "") == "reseau_adjugo"


def _network_responded(inv, contribution=None) -> bool:
    """Invitation RÉSEAU « répondue » : acceptée depuis le compte du partenaire (claim),
    adresse prouvée par code, ou part soumise. Décliner n'est pas accepter."""
    if not _is_network_invite(inv):
        return True
    return bool(getattr(inv, "accepted_by_user_id", None) or getattr(inv, "verified_at", None)
                or (contribution is not None and contribution.status == "submitted"))


def _network_pending(inv, db: Session = None) -> bool:
    """Invitation réseau pas encore acceptée → aperçu minimal côté partenaire."""
    if not _is_network_invite(inv):
        return False
    c = None
    if db is not None:
        c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    return not _network_responded(inv, c)


def _serialize_invite(inv: ProjectInvite, contribution: "ProjectContribution" = None, db: Session = None) -> dict:
    declined_at = getattr(inv, "declined_at", None)
    # Invitation RÉSEAU (vague 3) : l'adresse a été remplie CÔTÉ SERVEUR et reste MASQUÉE au
    # chef de file tant que le partenaire n'a pas répondu ; le lien n'est jamais remis au chef
    # de file (Adjugo l'envoie au partenaire, qui le retrouve aussi dans son espace).
    network = _is_network_invite(inv)
    if network and contribution is None and db is not None:
        contribution = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    masked = network and not _network_responded(inv, contribution)
    return {
        "id": inv.id,
        "token": None if network else inv.token,
        "path": None if network else f"/invite/{inv.token}",
        "recipient": "" if masked else inv.recipient,
        "recipient_masque": bool(masked),
        "company_name": inv.company_name,
        "role": inv.role or "cotraitant",
        "can_view_docs": bool(inv.can_view_docs),
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "revoked": bool(inv.revoked),
        "declined_at": declined_at.isoformat() if declined_at else None,
        "source": getattr(inv, "source", None) or "manuel",
        "state": _invite_state(inv, contribution),
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "view_count": inv.view_count or 0,
        "last_viewed_at": inv.last_viewed_at.isoformat() if inv.last_viewed_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        # emailed_at = le lien a réellement été envoyé par email (sinon : à transmettre à la main).
        "emailed_at": inv.emailed_at.isoformat() if getattr(inv, "emailed_at", None) else None,
        "contribution_status": (contribution.status if contribution else None),
        # Prix de lot renseigné sur sa part ? (booléen seulement ici ; le montant est dans
        # /contributions et le cockpit, vue mandataire.)
        "has_price": bool(contribution and contribution.prix_lot_ht is not None),
    }


DAILY_INVITE_CAP = 30


def _refuse_demo_sender(user: User) -> None:
    """Défense en profondeur (en plus du garde central) : la démo n'envoie JAMAIS d'email."""
    from app.services.demo_search import is_demo
    if is_demo(user):
        raise HTTPException(403, "La démo est en lecture guidée : créez votre compte gratuit "
                                 "pour inviter un partenaire.")


def _check_daily_invite_cap(user: User, db: Session) -> None:
    """Anti-spam : au plus DAILY_INVITE_CAP invitations créées par organisation sur 24 h
    glissantes (toutes les invitations du tenant, quel que soit le membre qui les crée)."""
    if getattr(user, "org_id", None):
        # Verrou de ligne : deux créations simultanées ne contournent pas le plafond.
        db.query(Organization).filter(Organization.id == user.org_id).with_for_update().first()
    since = utcnow() - timedelta(hours=24)
    owners = list(set(member_ids(user, db)) | {data_owner_id(user, db)})
    n = db.query(ProjectInvite).filter(ProjectInvite.owner_id.in_(owners),
                                       ProjectInvite.created_at >= since).count()
    # Les RENVOIS comptent aussi : sinon une seule invitation renvoyée en boucle permettait
    # d'envoyer des emails sans limite depuis l'adresse d'Adjugo.
    n += db.query(AuditLog).filter(AuditLog.owner_id.in_(owners), AuditLog.action == "invite.resent",
                                   AuditLog.created_at >= since).count()
    if n >= DAILY_INVITE_CAP:
        raise HTTPException(429, f"Vous avez atteint la limite de {DAILY_INVITE_CAP} invitations "
                                 f"par jour. Réessayez demain.")


def _create_invite(db: Session, project: Project, current_user: User, request: Request, *,
                   recipient: str = "", company_name: str = "", role: str = "cotraitant",
                   can_view_docs: bool = True, can_contribute: bool = True, expires_days: int = 30,
                   source: str = "manuel", partner_profile_id: Optional[int] = None,
                   mailer=None) -> tuple:
    """Crée l'invitation (lien secret), la journalise, envoie l'email si l'expéditeur a
    confirmé son adresse, et défige l'offre si besoin. Renvoie (invitation, email_parti).
    Factorisé (vague 3) SANS changer le comportement de POST /invites : les contrôles d'accès,
    de démo et de plafond restent à la charge de l'appelant. `mailer(inv, project, base_url)`
    remplace l'email standard (invitation réseau : texte dédié, adresse jamais montrée)."""
    # owner_id = propriétaire CANONIQUE de l'organisation (porteur du profil entreprise).
    # Toute la co-traitance d'un même tenant converge ainsi sur un seul owner_id : la vue
    # invité (nom du mandataire = Company.user_id == owner_id) et la chaîne d'audit
    # restent correctes quel que soit le membre qui crée le lien.
    owner = data_owner_id(current_user, db)
    inv = ProjectInvite(
        token=secrets.token_urlsafe(32),
        project_id=project.id, owner_id=owner,
        recipient=(recipient or "").strip()[:255],
        company_name=(company_name or "").strip()[:255],
        role=(role if role in ("cotraitant", "sous_traitant") else "cotraitant"),
        can_view_docs=bool(can_view_docs),
        can_contribute=bool(can_contribute),
        # Borné à [1, 365] j : days=0 → lien permanent (voulu) ; une valeur énorme faisait
        # planter timedelta (OverflowError 500), une valeur négative créait un lien déjà expiré.
        expires_at=(utcnow() + timedelta(days=min(int(expires_days), 365)))
                   if expires_days and expires_days > 0 else None,
        source=(source or "manuel")[:20],
        partner_profile_id=partner_profile_id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    # detail = nom d'entreprise seulement (jamais l'email : l'entrée est projetée dans le
    # journal des AUTRES membres comme « un partenaire a été invité »).
    audit.record(db, action="invite.created", owner_id=owner, project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="invite", target_id=inv.id, invite_id=inv.id,
                 detail=(inv.company_name or "")[:255],
                 ip=audit.client_ip(request))
    # Envoi du lien par email au destinataire (si adresse + SMTP configuré). Renseigne
    # emailed_at → on commit APRÈS l'envoi pour le persister.
    # Lien toujours créé ; l'EMAIL ne part que si l'expéditeur a confirmé sa propre adresse
    # (anti-spam via comptes jetables). Sinon : lien à copier, comme sans adresse.
    send = mailer or _send_invite_email
    emailed = (send(inv, project, _settings.APP_BASE_URL or str(request.base_url))
               if getattr(current_user, "email_verified", False) else False)
    db.commit()
    db.refresh(inv)
    # Un nouveau membre rend caduc un total figé (il ne couvre plus tout le groupement).
    _unfreeze_offer_if_needed(db, project.id, f"nouveau partenaire invité ({inv.company_name or 'sans nom'})",
                              actor=f"user:{current_user.id}", actor_kind="owner",
                              ip=audit.client_ip(request), invite_id=inv.id)
    return inv, emailed


@router.post("/api/projects/{project_id}/invites")
def create_invite(project_id: int, body: InviteCreate, request: Request,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Génère un lien d'invitation co-traitant pour ce projet (mandataire only)."""
    _refuse_demo_sender(current_user)
    project = _owned_project(project_id, current_user, db)
    _check_daily_invite_cap(current_user, db)
    inv, emailed = _create_invite(db, project, current_user, request,
                                  recipient=body.recipient, company_name=body.company_name,
                                  role=body.role, can_view_docs=body.can_view_docs,
                                  can_contribute=body.can_contribute, expires_days=body.expires_days)
    out = _serialize_invite(inv)
    out["url"] = str(request.base_url).rstrip("/") + out["path"]
    out["emailed"] = emailed
    return out


@router.get("/api/projects/{project_id}/invites")
def list_invites(project_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    # L'AO est vérifié au périmètre organisation ci-dessus ; on scope donc par project_id
    # (et non par owner_id) pour que tout coéquipier voie les mêmes invitations/contributions.
    _owned_project(project_id, current_user, db)
    rows = db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id
    ).order_by(ProjectInvite.created_at.desc()).all()
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id).all()}
    return [_serialize_invite(r, contribs.get(r.id), db=db) for r in rows]


RESEND_MIN_INTERVAL = timedelta(minutes=15)


def _require_verified_sender(user: User) -> None:
    """Un email d'invitation part sous le nom d'Adjugo vers un tiers : l'expéditeur doit
    avoir prouvé sa propre adresse (sinon un compte jetable devient un canal de spam)."""
    if not getattr(user, "email_verified", False):
        raise HTTPException(403, "Confirmez d'abord votre adresse email (lien reçu à l'inscription) "
                                 "pour envoyer des invitations par email. En attendant, copiez le lien.")


@router.post("/api/projects/{project_id}/invites/{invite_id}/resend")
@limiter.limit("20/hour")
def resend_invite(project_id: int, invite_id: int, request: Request,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Renvoie le mail d'invitation SUR LE MÊME lien (sans changer le token) : relance un
    partenaire silencieux ou rattrape un mail tombé en spam, sans casser l'URL déjà partagée.
    Bornes anti-spam : adresse de l'expéditeur confirmée, 1 renvoi par lien toutes les 15 min,
    renvois comptés dans le plafond quotidien de l'organisation, 20 renvois/h par IP."""
    _refuse_demo_sender(current_user)
    _require_verified_sender(current_user)
    project = _owned_project(project_id, current_user, db)
    inv = db.query(ProjectInvite).filter(
        ProjectInvite.id == invite_id, ProjectInvite.project_id == project_id).first()
    if not inv:
        raise HTTPException(404, "Invitation introuvable")
    if inv.revoked:
        raise HTTPException(400, "Ce lien a été révoqué — créez une nouvelle invitation.")
    if getattr(inv, "declined_at", None):
        raise HTTPException(400, "Ce partenaire a décliné l'invitation — créez une nouvelle invitation.")
    if not _is_email(inv.recipient):
        raise HTTPException(400, "Aucune adresse email sur ce lien — copiez-le et transmettez-le à la main.")
    last = inv.emailed_at
    if last is not None:
        last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < RESEND_MIN_INTERVAL:
            raise HTTPException(429, "Invitation déjà envoyée il y a moins de 15 minutes. "
                                     "Laissez un peu de temps au partenaire avant de relancer.")
    _check_daily_invite_cap(current_user, db)
    sender = _send_invite_email
    if _is_network_invite(inv):
        # Relance d'une invitation RÉSEAU : même texte que l'envoi initial (adresse jamais
        # montrée au chef de file, rappel « comment ne plus être sollicité »).
        from app.routers.cotraitants import ProjectCotraitant
        from app.routers.reseau import _network_mailer
        lk = db.query(ProjectCotraitant).filter(ProjectCotraitant.invite_id == inv.id).first()
        chef = db.query(Company).filter(Company.user_id == inv.owner_id).first()
        sender = _network_mailer((lk.lot if lk else "") or "", (chef.name if chef else "") or "")
    sent = sender(inv, project, _settings.APP_BASE_URL or str(request.base_url))
    db.commit()
    if sent:
        audit.record(db, action="invite.resent", owner_id=inv.owner_id, project_id=project_id,
                     actor=f"user:{current_user.id}", actor_kind="owner",
                     target_type="invite", target_id=inv.id, invite_id=inv.id,
                     detail=(inv.company_name or "")[:255], ip=audit.client_ip(request))
    return {"sent": sent, "emailed_at": inv.emailed_at.isoformat() if inv.emailed_at else None}


@router.delete("/api/projects/{project_id}/invites/{invite_id}")
def revoke_invite(project_id: int, invite_id: int, request: Request,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Révoque un lien : le co-traitant perd l'accès immédiatement."""
    # Contrôle d'accès = appartenance de l'AO à l'organisation (l'ancien filtre owner_id
    # servait de garde ; on le remplace par la vérification de périmètre explicite).
    _owned_project(project_id, current_user, db)
    inv = db.query(ProjectInvite).filter(
        ProjectInvite.id == invite_id, ProjectInvite.project_id == project_id
    ).first()
    if not inv:
        raise HTTPException(404, "Invitation introuvable")
    already_out = bool(inv.revoked or getattr(inv, "declined_at", None))
    inv.revoked = True
    # On éjecte AUSSI la contribution liée : sinon elle reste « submitted » et continue d'être
    # injectée dans le dossier final (mémoire fusionné, CERFA DC1/DC2, ZIP) → un partenaire
    # explicitement retiré du groupement repartait dans le pli déposé à l'acheteur.
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if c and c.status == "submitted":
        c.status = "draft"
        c.submitted_at = None
    db.commit()
    _unfreeze_offer_if_needed(db, inv.project_id, f"{inv.company_name or 'un partenaire'} retiré",
                              actor=f"user:{current_user.id}", actor_kind="owner",
                              ip=audit.client_ip(request))
    audit.record(db, action="invite.revoked", owner_id=inv.owner_id, project_id=project_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="invite", target_id=inv.id, invite_id=inv.id,
                 detail=(inv.company_name or "")[:255],
                 ip=audit.client_ip(request))
    # Notifie le partenaire que son accès est coupé (s'il a une adresse + SMTP configuré).
    # Inutile s'il avait déjà décliné / était déjà révoqué.
    emailed = False
    if _is_email(inv.recipient) and not already_out and getattr(current_user, "email_verified", False):
        try:
            from app.services import email as _email
            proj = db.query(Project).filter(Project.id == project_id).first()
            emailed = _email.send_email(
                inv.recipient, "Accès à un dossier Adjugo retiré",
                f"Bonjour,\n\nVotre accès au dossier « {proj.name if proj else 'partagé'} » sur "
                f"Adjugo a été retiré par le mandataire. Vous n'y avez plus accès.\n\n— Adjugo")
        except Exception:
            emailed = False
    return {"ok": True, "notified": emailed}


@router.get("/api/projects/{project_id}/audit")
def project_audit(project_id: int, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), limit: int = 200):
    """Journal d'accès du projet (RGPD) — qui a consulté/téléchargé quoi, et quand."""
    _owned_project(project_id, current_user, db)
    rows = db.query(AuditLog).filter(
        AuditLog.project_id == project_id
    ).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()
    return [{
        "id": r.id, "at": r.created_at.isoformat() if r.created_at else None,
        "actor": r.actor, "actor_kind": r.actor_kind, "action": r.action,
        "target_type": r.target_type, "target_id": r.target_id,
        "detail": r.detail, "ip": r.ip,
    } for r in rows]


@router.get("/api/audit/integrity")
def audit_integrity(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vérifie l'intégrité du journal d'audit du tenant (chaîne de hash). Preuve RGPD
    que la traçabilité n'a pas été altérée."""
    # La chaîne d'audit du tenant est portée par le propriétaire canonique de l'org ; on
    # vérifie AUSSI les chaînes héritées encore référencées (anciens propriétaires après un
    # transfert, comptes effacés) : owner_id étant haché, elles ne sont jamais fusionnées.
    return audit.verify_org_chains(db, _org_chain_owner_ids(current_user, db))


def _org_chain_owner_ids(current_user: User, db: Session) -> list:
    """Propriétaire actuel d'abord, puis les porteurs de chaînes de l'historique de l'org :
    (a) anciens propriétaires, remontés de proche en proche par les entrées
        « team.ownership_transferred » (actor = « user:<ancien> ») ;
    (b) membres actuels, ou comptes effacés-anonymisés, ayant des entrées sur les marchés
        de l'organisation. Jamais la chaîne d'une autre entreprise active."""
    current = data_owner_id(current_user, db)
    ids, frontier = [current], [current]
    members_now = set(member_ids(current_user, db))
    out = [current]
    for _ in range(50):   # borne de sécurité (transferts en chaîne)
        if not frontier:
            break
        rows = db.query(AuditLog.id, AuditLog.actor).filter(
            AuditLog.action == "team.ownership_transferred",
            AuditLog.owner_id.in_(frontier)).all()
        nxt = []
        # Borne = DERNIER transfert sortant de cet ancien propriétaire (aller-retour K→L→K→L :
        # le premier transfert laissait sa dernière période dans l'org sans vérification).
        last = {}
        for (tid, actor) in rows:
            m = re.fullmatch(r"user:(\d+)", (actor or "").strip())
            if m:
                last[int(m.group(1))] = max(tid, last.get(int(m.group(1)), 0))
        for old, tid in sorted(last.items(), key=lambda kv: kv[1]):
            if old not in ids:
                ids.append(old)
                nxt.append(old)
                u = db.query(User).filter(User.id == old).first()
                erased = bool(u) and (not u.is_active) and u.org_id is None
                # Ancien propriétaire toujours membre (ou effacé) : toute sa chaîne. S'il dirige
                # désormais une AUTRE entreprise : seul le préfixe d'avant le transfert (jamais
                # le journal de sa nouvelle entreprise).
                out.append(old if (old in members_now or erased or not u) else (old, tid))
        frontier = nxt
    try:
        members = set(member_ids(current_user, db))
        pids = [r[0] for r in db.query(Project.id).filter(Project.user_id.in_(list(members))).all()]
        if pids:
            others = {r[0] for r in db.query(AuditLog.owner_id).filter(
                AuditLog.project_id.in_(pids), AuditLog.owner_id.isnot(None)).distinct().all()}
            others -= set(ids)
            if others:
                for u in db.query(User).filter(User.id.in_(list(others))).all():
                    erased = (not u.is_active) and u.org_id is None
                    if u.id in members or erased:
                        ids.append(u.id)
                        out.append(u.id)
    except Exception:
        pass
    return out


# ── Côté CO-TRAITANT INVITÉ (NON authentifié — jeton dans l'URL) ─────────────
def _is_expired(dt) -> bool:
    """Comparaison robuste : la base peut renvoyer un datetime naïf (UTC implicite)."""
    if not dt:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= datetime.now(timezone.utc)


def _valid_invite(token: str, db: Session) -> ProjectInvite:
    inv = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
    if not inv or inv.revoked:
        raise HTTPException(404, "Lien invalide ou révoqué")
    if getattr(inv, "declined_at", None):
        raise HTTPException(410, "Vous avez décliné cette invitation. Contactez le mandataire pour la rouvrir.")
    if _is_expired(inv.expires_at):
        raise HTTPException(410, "Ce lien de partage a expiré")
    return inv


def _guest_actor(inv) -> str:
    """Acteur journalisé pour un invité : TOUJOURS le nom d'entreprise, JAMAIS l'email
    (le journal est projeté vers les autres membres)."""
    return (inv.company_name or "invité")[:160]


def tenant_owner_id(project: Project, db: Session) -> int:
    """Propriétaire CANONIQUE du tenant d'un projet (= propriétaire de l'organisation du
    créateur), celui sous lequel est chaînée toute la traçabilité du dossier (invitations,
    parts, offre figée…). Jamais `project.user_id` brut : si un MEMBRE a créé le marché, ses
    entrées sortiraient de la chaîne d'intégrité de l'entreprise et disparaîtraient avec son
    compte. Repli sur le créateur s'il n'a pas (encore) d'organisation."""
    try:
        creator = db.query(User).filter(User.id == project.user_id).first()
        oid = getattr(creator, "org_id", None)
        if oid:
            owner = db.query(Organization.owner_id).filter(Organization.id == oid).scalar()
            if owner:
                return owner
    except Exception:
        pass
    return project.user_id


def _unfreeze_offer_if_needed(db: Session, project_id: int, reason: str, *, actor: str = "",
                              actor_kind: str = "guest", ip: str = "", invite_id=None) -> bool:
    """Si l'offre commune est figée et qu'une part change (prix, retour en brouillon,
    membre retiré), on la DÉFIGE : le total révélé aux membres ne doit jamais être faux.
    Réassigne un NOUVEAU dict (colonne JSON : la mutation en place n'est pas détectée)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    # Vague 2 : la même cause (part, prix, composition, part du mandataire) rend la convention
    # de groupement CADUQUE (status 'perimee', tracé convention.perimee) — même si l'offre
    # n'était plus figée. Best-effort, ne lève jamais.
    if project is not None:
        try:
            from app.services.groupement_convention import concerns_convention, perimer as _perimer_convention
            # Un sous-traitant (hors groupement) n'est ni dans la convention ni dans l'offre
            # qu'elle fige : sa part ne défige rien et ne rend rien caduc.
            if not concerns_convention(db, project, invite_id):
                return False
            _perimer_convention(db, project, (f"part de {reason} modifiée" if actor_kind == "guest" else reason),
                                actor=actor, actor_kind=actor_kind, ip=ip, invite_id=invite_id)
        except Exception:
            pass
    plan = project.groupement_plan if project and isinstance(project.groupement_plan, dict) else None
    if not plan or not isinstance(plan.get("offre"), dict) or not plan["offre"].get("frozen_at"):
        return False
    new_plan = {k: v for k, v in plan.items() if k != "offre"}
    project.groupement_plan = new_plan
    db.commit()
    audit.record(db, action="offer.unfrozen", owner_id=tenant_owner_id(project, db), project_id=project.id,
                 actor=actor, actor_kind=actor_kind, target_type="project", target_id=project.id,
                 detail=(f"part de {reason}" if actor_kind == "guest" else reason)[:255],
                 ip=ip, invite_id=invite_id)
    return True


@router.get("/api/invite/{token}")
@limiter.limit("120/minute")
def guest_view(token: str, request: Request, db: Session = Depends(get_db)):
    """Vue bridée du projet partagé (aucune autre donnée du tenant n'est lisible)."""
    inv = _valid_invite(token, db)
    project = db.query(Project).filter(
        Project.id == inv.project_id, Project.deleted_at.is_(None)
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable ou retiré")
    owner_company = db.query(Company).filter(Company.user_id == inv.owner_id).first()

    docs = []
    if inv.can_view_docs:
        # Versions remplacées (parent_id posé) EXCLUES : ce que le mandataire a remplacé
        # disparaît aussi pour le partenaire (même règle que le coffre-fort et l'export).
        rows = db.query(Document).filter(
            Document.project_id == inv.project_id, Document.deleted_at.is_(None),
            Document.parent_id.is_(None)
        ).order_by(Document.created_at.desc()).all()
        docs = [{"id": d.id, "name": d.name,
                 "category": d.category.value if hasattr(d.category, "value") else str(d.category or ""),
                 "folder": d.folder or "", "size": d.file_size or 0} for d in rows]

    # Compteur de vues + trace d'accès
    inv.view_count = (inv.view_count or 0) + 1
    inv.last_viewed_at = utcnow()
    db.commit()
    audit.record(db, action="guest.view_project", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest",
                 target_type="project", target_id=inv.project_id, invite_id=inv.id,
                 detail=(inv.company_name or "")[:255], ip=audit.client_ip(request))
    return _invite_public(inv, project, owner_company, docs, db=db)


@router.get("/api/invite/{token}/doc/{doc_id}")
@limiter.limit("60/minute")
def guest_download(token: str, doc_id: int, request: Request, db: Session = Depends(get_db)):
    """Télécharge une pièce partagée — STRICTEMENT limitée au projet de l'invitation."""
    inv = _valid_invite(token, db)
    if not inv.can_view_docs:
        raise HTTPException(403, "Le partage des pièces n'est pas autorisé pour ce lien")
    if _network_pending(inv, db):
        raise HTTPException(403, "Acceptez d'abord l'invitation depuis votre compte Adjugo pour télécharger "
                                 "les pièces du marché.")
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.project_id == inv.project_id,
        Document.deleted_at.is_(None), Document.parent_id.is_(None)
    ).first()
    if not doc or not doc.file_key:
        raise HTTPException(404, "Pièce introuvable")
    audit.record(db, action="guest.download_doc", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", invite_id=inv.id,
                 target_type="document", target_id=doc.id, detail=(doc.name or "")[:255],
                 ip=audit.client_ip(request))
    storage = get_storage()
    signed = storage.url(doc.file_key, filename=doc.name)
    if signed:
        return RedirectResponse(signed)
    try:
        content = storage.load(doc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    return StreamingResponse(
        io.BytesIO(content),
        media_type=_safe_mime(doc.file_key),     # jamais doc.mime_type (type annoncé par le client)
        headers=_attachment_headers(doc.name),
    )


# ── CO-CONSTRUCTION : l'invité apporte SA part (cloisonnée) ──────────────────
# Cœur du réseau Adjugo : chaque PME contribue à un dossier commun sans jamais
# voir les données des autres. La contribution est liée à l'invitation (1-1) ;
# l'invité ne lit/écrit JAMAIS que la sienne.
def _piece_dict(pc: ContributionPiece, viewer: str = "member") -> dict:
    out = {"id": pc.id, "name": pc.name, "size": pc.file_size or 0,
           "created_at": pc.created_at.isoformat() if pc.created_at else None,
           "piece_type": getattr(pc, "piece_type", "") or "",
           "expiration_date": pc.expiration_date.isoformat() if getattr(pc, "expiration_date", None) else None}
    if viewer == "member":
        # L'id du Document d'origine (coffre-fort PERSONNEL du partenaire) n'est jamais
        # révélé au mandataire : seule la copie jointe existe pour lui.
        out["source_document_id"] = getattr(pc, "source_document_id", None)
    return out


def _serialize_contribution(c: ProjectContribution, db: Session = None, viewer: str = "member") -> dict:
    """Sérialise une part. DOCTRINE DE VISIBILITÉ :
    - `prix_lot_ht` (prix de VENTE du lot) : visible du membre ET du mandataire ;
    - `detail_chiffre` (enveloppe chiffrée : décomposition/coûts/marges) : UNIQUEMENT pour
      viewer == 'member' (routes /api/invite/{token}/…). Pour le mandataire (viewer ==
      'owner'), la clé est ABSENTE (pas null) et remplacée par `has_detail_chiffre`.
    - `chiffrage_note` (ancienne approche prix en clair) n'est plus JAMAIS sérialisé."""
    pieces = []
    if db is not None:
        pieces = [_piece_dict(p, viewer) for p in db.query(ContributionPiece).filter(
            ContributionPiece.contribution_id == c.id).order_by(ContributionPiece.created_at.asc()).all()]
    out = {
        "id": c.id, "company_name": c.company_name, "role": c.role, "lot": c.lot,
        "siret": c.siret or "", "forme_juridique": c.forme_juridique or "",
        "address": c.address or "", "postal_code": c.postal_code or "", "city": c.city or "",
        "references": c.references or [], "qualifications": c.qualifications or [],
        "memoire_paragraph": c.memoire_paragraph or "",
        "contact": c.contact or {}, "status": c.status,
        "note_au_mandataire": getattr(c, "note_au_mandataire", "") or "",
        "prix_lot_ht": c.prix_lot_ht,
        "representant_legal": getattr(c, "representant_legal", "") or "",
        "signataire_qualite": getattr(c, "signataire_qualite", "") or "",
        "capacites": c.capacites if isinstance(c.capacites, dict) else None,
        "version": c.version or 0,
        "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "pieces": pieces,
        # Checklist des pièces administratives : le partenaire voit en direct ce qu'il a
        # fourni et ce qu'il lui reste à déposer (même logique que la vue mandataire).
        "pieces_checklist": _classify_partner_pieces([p["name"] for p in pieces],
                                                     [p["piece_type"] for p in pieces]),
    }
    if viewer == "member":
        out["detail_chiffre"] = c.detail_chiffre if isinstance(c.detail_chiffre, dict) and c.detail_chiffre else None
    else:
        out["has_detail_chiffre"] = bool(isinstance(c.detail_chiffre, dict) and c.detail_chiffre)
    return out


def _get_or_create_contribution(inv: ProjectInvite, db: Session) -> ProjectContribution:
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if c is None:
        c = ProjectContribution(
            invite_id=inv.id, project_id=inv.project_id, owner_id=inv.owner_id,
            company_name=inv.company_name or "", role=inv.role or "cotraitant",
        )
        db.add(c)
        try:
            db.commit()
            db.refresh(c)
        except IntegrityError:
            # invite_id est UNIQUE : deux requêtes concurrentes (2 onglets, GET /contribution
            # + /otp/status en parallèle) peuvent tenter l'INSERT ensemble → on récupère la
            # contribution créée par l'autre au lieu de renvoyer un 500.
            db.rollback()
            c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
            if c is None:
                raise
    return c


# ── Enveloppe chiffrée (detail_chiffre) : le serveur n'en vérifie que la FORME ──────────
# {ciphertext (base64 ≤ 200 000 car.), iv (base64 de 12 octets → 16 car.), alg 'A256GCM',
#  kdf 'PBKDF2-SHA256', kdf_salt (base64), kdf_iter ≥ 100 000, key_fingerprint ≤ 64,
#  updated_at ISO}. Clés EXACTES, rien de plus, rien de moins. Jamais déchiffrée ici.
_ENVELOPE_KEYS = {"ciphertext", "iv", "alg", "kdf", "kdf_salt", "kdf_iter", "key_fingerprint", "updated_at"}
_ENVELOPE_ERR = "Enveloppe chiffrée invalide"
_B64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _is_b64(s, max_len: int = None) -> bool:
    if not isinstance(s, str) or not s or (max_len and len(s) > max_len) or not _B64_RE.match(s):
        return False
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False


def _validate_envelope(v):
    """None / {} → None (efface). Sinon : enveloppe STRICTE, sinon ValueError (→ 422)."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError(_ENVELOPE_ERR)
    if not v:
        return None
    if set(v.keys()) != _ENVELOPE_KEYS:
        raise ValueError(_ENVELOPE_ERR)
    if not _is_b64(v["ciphertext"], 200_000):
        raise ValueError(_ENVELOPE_ERR)
    if not (_is_b64(v["iv"]) and len(v["iv"]) == 16 and len(base64.b64decode(v["iv"])) == 12):
        raise ValueError(_ENVELOPE_ERR)
    if v["alg"] != "A256GCM" or v["kdf"] != "PBKDF2-SHA256":
        raise ValueError(_ENVELOPE_ERR)
    if not _is_b64(v["kdf_salt"], 256):
        raise ValueError(_ENVELOPE_ERR)
    if not isinstance(v["kdf_iter"], int) or isinstance(v["kdf_iter"], bool) or v["kdf_iter"] < 100_000:
        raise ValueError(_ENVELOPE_ERR)
    if not isinstance(v["key_fingerprint"], str) or not v["key_fingerprint"] or len(v["key_fingerprint"]) > 64:
        raise ValueError(_ENVELOPE_ERR)
    if not isinstance(v["updated_at"], str) or not v["updated_at"]:
        raise ValueError(_ENVELOPE_ERR)
    try:
        datetime.fromisoformat(v["updated_at"].replace("Z", "+00:00"))
    except Exception:
        raise ValueError(_ENVELOPE_ERR)
    return dict(v)


class ContributionSave(BaseModel):
    company_name: Optional[str] = None
    lot: Optional[str] = None
    siret: Optional[str] = None
    forme_juridique: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    references: Optional[list] = None
    qualifications: Optional[list] = None
    # chiffrage_note (approche prix en clair) n'est PLUS accepté : un client qui l'envoie
    # encore est ignoré silencieusement (pydantic ignore les champs inconnus).
    memoire_paragraph: Optional[str] = None
    contact: Optional[dict] = None
    note_au_mandataire: Optional[str] = None   # mot libre du partenaire au chef de file
    # ── Doctrine de visibilité ──
    prix_lot_ht: Optional[float] = None        # prix de VENTE du lot (clair, vu du mandataire)
    detail_chiffre: Optional[dict] = None      # enveloppe chiffrée (jamais lue côté serveur)
    representant_legal: Optional[str] = None
    signataire_qualite: Optional[str] = None
    capacites: Optional[dict] = None           # {ca_n1: float|None, effectif: int|None}
    version: Optional[int] = None     # verrou optimiste : la version chargée par le client

    @field_validator("prix_lot_ht")
    @classmethod
    def _prix(cls, v):
        if v is None:
            return None
        v = float(v)
        if v != v or v < 0 or v > 1e10:   # NaN, négatif, absurde
            raise ValueError("Le prix du lot doit être compris entre 0 et 10 milliards d'euros HT.")
        return v

    @field_validator("detail_chiffre")
    @classmethod
    def _env(cls, v):
        return _validate_envelope(v)

    @field_validator("capacites")
    @classmethod
    def _cap(cls, v):
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("Capacités invalides")
        out = {}
        ca = v.get("ca_n1")
        eff = v.get("effectif")
        if ca is not None:
            try:
                ca = float(ca)
            except (TypeError, ValueError):
                raise ValueError("Chiffre d'affaires invalide")
            if ca != ca or ca < 0 or ca > 1e11:
                raise ValueError("Chiffre d'affaires invalide")
        if eff is not None:
            if isinstance(eff, bool):
                raise ValueError("Effectif invalide")
            try:
                eff = int(eff)
            except (TypeError, ValueError):
                raise ValueError("Effectif invalide")
            if eff < 0 or eff > 1_000_000:
                raise ValueError("Effectif invalide")
        out["ca_n1"] = ca
        out["effectif"] = eff
        return out


def _sync_annuaire_capacites(inv: ProjectInvite, c: ProjectContribution, db: Session) -> None:
    """Si le mandataire a ce partenaire dans « Mes partenaires » (même SIRET, à défaut même
    nom), ses capacités DÉCLARÉES PAR LE PARTENAIRE LUI-MÊME remplacent celles saisies par
    le mandataire (capacites_source='contribution' : plus fiable). Best-effort."""
    try:
        from app.routers.cotraitants import Cotraitant
        owner = db.query(User).filter(User.id == inv.owner_id).first()
        if not owner:
            return
        from app.routers.cotraitants import ProjectCotraitant
        ids = member_ids(owner, db)
        q = db.query(Cotraitant).filter(Cotraitant.user_id.in_(ids))
        # JAMAIS par nom (un invité pourrait, avec un jeton seul, réécrire les capacités
        # « vérifiées » d'un AUTRE partenaire de l'annuaire = fausse provenance). Seulement :
        # (1) le rattachement de CE projet lié à CETTE invitation, (2) à défaut le SIRET exact
        # d'un partenaire RATTACHÉ à ce projet.
        row = None
        link = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == inv.project_id,
                                                  ProjectCotraitant.invite_id == inv.id).first()
        if link:
            row = q.filter(Cotraitant.id == link.cotraitant_id).first()
        siret = (c.siret or "").strip()
        if row is None and siret:
            linked_ids = [lk.cotraitant_id for lk in db.query(ProjectCotraitant).filter(
                ProjectCotraitant.project_id == inv.project_id).all()]
            if linked_ids:
                row = q.filter(Cotraitant.siret == siret, Cotraitant.id.in_(linked_ids)).first()
        if row is None:
            return
        cap = c.capacites or {}
        if cap.get("ca_n1") is not None:
            row.ca_n1 = float(cap["ca_n1"])
        if cap.get("effectif") is not None:
            row.effectif = int(cap["effectif"])
        if c.qualifications:
            row.qualifications = ", ".join(str(q) for q in c.qualifications if q)[:2000]
        row.capacites_source = "contribution"
        row.capacites_updated_at = utcnow()
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


@router.get("/api/invite/{token}/contribution")
@limiter.limit("120/minute")
def guest_get_contribution(token: str, request: Request, db: Session = Depends(get_db)):
    """Récupère (ou initialise) la contribution de CET invité — la sienne uniquement."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    return _serialize_contribution(_get_or_create_contribution(inv, db), db)


@router.put("/api/invite/{token}/contribution")
@limiter.limit("90/minute")
def guest_save_contribution(token: str, body: ContributionSave, request: Request, db: Session = Depends(get_db)):
    """Enregistre le brouillon de la contribution de cet invité (ses champs uniquement)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    c = _get_or_create_contribution(inv, db)
    # Verrou optimiste OBLIGATOIRE et ATOMIQUE. La version est exigée (un client qui
    # l'omettait écrasait silencieusement la saisie d'un autre). On « réserve » la
    # transition de version par un UPDATE ... WHERE version = attendue, exécuté en une
    # seule instruction SQL : deux PUT concurrents lisant la même version ne peuvent pas
    # passer tous les deux (le 2ᵉ matche 0 ligne → 409). Cela ferme la fenêtre TOCTOU
    # du simple read-then-write.
    if body.version is None:
        raise HTTPException(428, "Version requise (verrou optimiste). Rechargez la contribution.")
    expected = int(body.version)
    claimed = db.query(ProjectContribution).filter(
        ProjectContribution.id == c.id,
        ProjectContribution.version == expected,
    ).update({ProjectContribution.version: expected + 1}, synchronize_session="fetch")
    if not claimed:
        db.rollback()
        raise HTTPException(409, "Cette contribution a été modifiée ailleurs entre-temps. "
                                 "Rechargez pour récupérer la dernière version avant de réenregistrer.")
    if body.company_name is not None:
        c.company_name = body.company_name.strip()[:255]
    if body.lot is not None:
        c.lot = body.lot.strip()[:255]
    if body.siret is not None:
        c.siret = body.siret.strip()[:20]
    if body.forme_juridique is not None:
        c.forme_juridique = body.forme_juridique.strip()[:80]
    if body.address is not None:
        c.address = body.address.strip()[:255]
    if body.postal_code is not None:
        c.postal_code = body.postal_code.strip()[:10]
    if body.city is not None:
        c.city = body.city.strip()[:120]
    if body.references is not None:
        c.references = body.references[:50]
    if body.qualifications is not None:
        c.qualifications = body.qualifications[:50]
    if body.memoire_paragraph is not None:
        c.memoire_paragraph = body.memoire_paragraph[:12000]
    if body.contact is not None:
        c.contact = {k: str(v)[:255] for k, v in (body.contact or {}).items()
                     if k in ("nom", "email", "telephone")}
    if body.note_au_mandataire is not None:
        c.note_au_mandataire = body.note_au_mandataire[:2000]
    # ── Doctrine de visibilité ──
    fields = body.model_fields_set
    was_submitted = (c.status == "submitted")
    price_changed = False
    if "prix_lot_ht" in fields:                  # None explicite = effacer
        price_changed = (c.prix_lot_ht != body.prix_lot_ht)
        c.prix_lot_ht = body.prix_lot_ht
    if "detail_chiffre" in fields:               # None / {} = effacer ; sinon enveloppe validée
        c.detail_chiffre = body.detail_chiffre
    if body.representant_legal is not None:
        c.representant_legal = body.representant_legal.strip()[:255]
    if body.signataire_qualite is not None:
        c.signataire_qualite = body.signataire_qualite.strip()[:120]
    capacites_changed = False
    if body.capacites is not None:
        old = c.capacites if isinstance(c.capacites, dict) else {}
        if (old.get("ca_n1"), old.get("effectif")) != (body.capacites.get("ca_n1"), body.capacites.get("effectif")):
            capacites_changed = True
            c.capacites = {"ca_n1": body.capacites.get("ca_n1"), "effectif": body.capacites.get("effectif"),
                           "declared_at": utcnow().isoformat()}
    if c.status == "submitted":            # toute modif après soumission repasse en brouillon
        c.status = "draft"
        c.submitted_at = None
    # La version a déjà été incrémentée atomiquement par le claim ci-dessus (→ expected+1).
    db.commit()
    # Offre figée + prix modifié ou part repassée en brouillon → on défige (total obsolète).
    if price_changed or was_submitted:
        _unfreeze_offer_if_needed(db, inv.project_id, c.company_name or inv.company_name or "un partenaire",
                                  actor=_guest_actor(inv), actor_kind="guest",
                                  ip=audit.client_ip(request), invite_id=inv.id)
    if capacites_changed:
        audit.record(db, action="guest.capacites_updated", owner_id=inv.owner_id,
                     project_id=inv.project_id, actor=_guest_actor(inv), actor_kind="guest",
                     target_type="contribution", target_id=c.id, invite_id=inv.id,
                     detail=(c.company_name or inv.company_name or "")[:255], ip=audit.client_ip(request))
        _sync_annuaire_capacites(inv, c, db)
    return _serialize_contribution(c, db)


# ── Binding d'identité par OTP email (sécurité « industrielle ») ─────────────
class OtpVerify(BaseModel):
    code: str = ""


@router.get("/api/invite/{token}/otp/status")
@limiter.limit("120/minute")
def guest_otp_status(token: str, request: Request, db: Session = Depends(get_db)):
    """Indique au front si une vérification d'identité est requise pour soumettre, et si
    elle est déjà faite. Si l'email n'est pas configuré, aucune vérification (flux libre)."""
    inv = _valid_invite(token, db)
    # `pending` = un code valide a déjà été envoyé et n'est pas expiré → le front le réutilise
    # au lieu de rappeler /otp/request (qui consomme la limite 6/h et bloquerait le partenaire).
    # _is_expired et non `> utcnow()` : relu en base, otp_expires_at est NAÏF alors
    # qu'utcnow() est aware → TypeError (500) dès la 2e requête sans cette précaution.
    pending = bool(inv.otp_hash and inv.otp_expires_at and not _is_expired(inv.otp_expires_at))
    return {"required": _binding_required(inv),
            "verified": bool(inv.verified_at),
            "pending": pending,
            "email_masked": _mask_email(inv.recipient) if _is_email(inv.recipient) else ""}


OTP_DAILY_CAP_VERIFIED = 40     # codes envoyés / 24 h / organisation mandataire
OTP_DAILY_CAP_UNVERIFIED = 8    # mandataire qui n'a pas prouvé son adresse : très bas


def _otp_cap_reached(inv, db: Session) -> bool:
    """Plafond quotidien des codes envoyés par organisation : la limite par lien (6/h) ne
    suffisait pas, un compte jetable multipliait les liens vers autant d'adresses."""
    owner = db.query(User).filter(User.id == inv.owner_id).first()
    cap = OTP_DAILY_CAP_VERIFIED if (owner and owner.email_verified) else OTP_DAILY_CAP_UNVERIFIED
    since = utcnow() - timedelta(hours=24)
    n = db.query(AuditLog).filter(AuditLog.owner_id == inv.owner_id,
                                  AuditLog.action == "guest.otp_request",
                                  AuditLog.created_at >= since).count()
    return n >= cap


@router.post("/api/invite/{token}/otp/request")
@limiter.limit("6/hour")
def guest_otp_request(token: str, request: Request, db: Session = Depends(get_db)):
    """Envoie un code à 6 chiffres à l'adresse destinataire de l'invitation, pour prouver
    que l'invité la contrôle avant de soumettre sa part."""
    inv = _valid_invite(token, db)
    if not _binding_required(inv):   # (dont : invitation de la démo → jamais d'envoi)
        return {"sent": False, "reason": "Vérification non requise pour ce lien."}
    # Idempotence : si un code valide est DÉJÀ en attente, on ne le régénère pas (sinon le code
    # déjà reçu par le partenaire serait invalidé à chaque clic « Soumettre », et le plafond
    # 6/h finirait par le verrouiller). Il réutilise le code reçu.
    if inv.otp_hash and inv.otp_expires_at and not _is_expired(inv.otp_expires_at):
        return {"sent": True, "already": True,
                "email_masked": _mask_email(inv.recipient) if _is_email(inv.recipient) else ""}
    if _otp_cap_reached(inv, db):
        return {"sent": False,
                "reason": "Trop de codes envoyés aujourd'hui pour ce groupement. Réessayez demain "
                          "ou demandez au mandataire de vous renvoyer l'invitation.",
                "email_masked": _mask_email(inv.recipient) if _is_email(inv.recipient) else ""}
    code = f"{secrets.randbelow(1_000_000):06d}"
    inv.otp_hash = _hash_otp(code)
    inv.otp_expires_at = utcnow() + timedelta(minutes=_OTP_TTL_MIN)
    inv.otp_attempts = 0
    db.commit()
    from app.services import email as _email
    sent = _email.send_email(
        inv.recipient,
        "Votre code de vérification Adjugo",
        f"Votre code pour valider votre contribution au groupement : {code}\n\n"
        f"Il expire dans {_OTP_TTL_MIN} minutes. Si vous n'êtes pas à l'origine de cette "
        f"demande, ignorez ce message.")
    if not sent:
        # L'email n'est pas parti : on EFFACE le code en attente, sinon l'invité restait
        # bloqué (état « pending » 15 min) avec un code qu'il n'a jamais reçu.
        inv.otp_hash = None
        inv.otp_expires_at = None
        db.commit()
        return {"sent": False,
                "reason": "L'envoi du code a échoué. Réessayez dans un instant.",
                "email_masked": _mask_email(inv.recipient) if _is_email(inv.recipient) else ""}
    audit.record(db, action="guest.otp_request", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", target_type="invite",
                 target_id=inv.id, invite_id=inv.id, detail=_audit_email_detail(inv),
                 ip=audit.client_ip(request))
    return {"sent": True, "email_masked": _mask_email(inv.recipient), "ttl_min": _OTP_TTL_MIN}


@router.post("/api/invite/{token}/otp/verify")
@limiter.limit("20/hour")
def guest_otp_verify(token: str, body: OtpVerify, request: Request, db: Session = Depends(get_db)):
    """Vérifie le code reçu par email → marque l'identité de l'invité comme prouvée."""
    inv = _valid_invite(token, db)
    if not _binding_required(inv):
        return {"verified": True}
    if not inv.otp_hash or not inv.otp_expires_at:
        raise HTTPException(400, "Aucun code en attente. Demandez d'abord un code.")
    if _is_expired(inv.otp_expires_at):
        raise HTTPException(410, "Code expiré. Demandez-en un nouveau.")
    if (inv.otp_attempts or 0) >= _OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives. Demandez un nouveau code.")
    if _hash_otp((body.code or "").strip()) != inv.otp_hash:
        inv.otp_attempts = (inv.otp_attempts or 0) + 1
        db.commit()
        raise HTTPException(400, "Code incorrect.")
    inv.verified_at = utcnow()
    inv.verified_email = inv.recipient
    inv.otp_hash = ""
    inv.otp_expires_at = None
    db.commit()
    audit.record(db, action="guest.otp_verified", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", target_type="invite",
                 target_id=inv.id, invite_id=inv.id, detail=_audit_email_detail(inv),
                 ip=audit.client_ip(request))
    return {"verified": True}


@router.post("/api/invite/{token}/contribution/submit")
@limiter.limit("30/minute")
def guest_submit_contribution(token: str, request: Request, db: Session = Depends(get_db)):
    """Soumet la contribution au mandataire (et la rend disponible pour la fusion IA)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    # Binding d'identité : si requis (email configuré + destinataire = adresse), l'invité
    # doit avoir prouvé son adresse avant de soumettre. La saisie/brouillon reste libre.
    if _binding_required(inv) and not inv.verified_at:
        raise HTTPException(status_code=403,
                            detail={"code": "identity_unverified",
                                    "message": "Vérifiez votre adresse email avant de soumettre votre part."})
    c = _get_or_create_contribution(inv, db)
    c.status = "submitted"
    c.submitted_at = utcnow()
    db.commit()
    audit.record(db, action="guest.submit_contribution", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest",
                 target_type="contribution", target_id=c.id, invite_id=inv.id,
                 detail=(c.company_name or inv.company_name or "")[:255], ip=audit.client_ip(request))
    # Notifications best-effort (aucune ne doit casser la soumission) : le mandataire est
    # prévenu qu'une part est arrivée, le partenaire reçoit un accusé de réception.
    _notify_part_submitted(inv, c, db)
    _notify_partner_received(inv, db)
    return _serialize_contribution(c, db)


# ── Déclin : le partenaire sort du groupement de lui-même ─────────────────────
@router.post("/api/invite/{token}/decline")
@limiter.limit("10/hour")
def guest_decline(token: str, request: Request, db: Session = Depends(get_db)):
    """Le partenaire DÉCLINE l'invitation : il sort du groupement (checklist, cockpit,
    CERFA, dossier) sans que le mandataire ait à révoquer. Le lien devient inutilisable
    (410) ; le mandataire peut créer une nouvelle invitation s'il veut le rouvrir."""
    inv = _valid_invite(token, db)           # déjà décliné → 410, révoqué → 404
    _refuse_if_demo_invite(inv, db)          # vitrine partagée : on ne la ferme pas aux suivants
    inv.declined_at = utcnow()
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if c and c.status == "submitted":
        c.status = "draft"
        c.submitted_at = None
    db.commit()
    _unfreeze_offer_if_needed(db, inv.project_id, inv.company_name or "un partenaire",
                              actor=_guest_actor(inv), actor_kind="guest",
                              ip=audit.client_ip(request), invite_id=inv.id)
    audit.record(db, action="invite.declined", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", target_type="invite",
                 target_id=inv.id, invite_id=inv.id, detail=(inv.company_name or "")[:255],
                 ip=audit.client_ip(request))
    # Email best-effort au mandataire.
    try:
        to = _mandataire_email(inv.owner_id, db)
        if to:
            from app.services import email as _email
            project = db.query(Project).filter(Project.id == inv.project_id).first()
            pname = (project.name if project else "votre marché")
            who = inv.company_name or "Un partenaire"
            _send_mails_async([(
                to, f"{who} a décliné l'invitation — {pname[:60]}",
                f"Bonjour,\n\n{who} a décliné l'invitation à rejoindre le groupement sur le marché "
                f"« {pname} ». Sa part ne figurera pas dans la réponse commune.\n\n"
                f"Vous pouvez inviter un autre partenaire depuis le cockpit du groupement.\n\n— Adjugo")])
    except Exception:
        pass
    return {"ok": True}


# ── Découverte d'appels d'offres pour l'invité (NON facturée, lecture seule) ──
# L'invité goûte au sourcing : il cherche des AO publics, mais « analyser / ajouter »
# l'invitera à créer son compte (conversion). Aucune dépense, aucune donnée du tenant.
class GuestSearch(BaseModel):
    query: str = ""
    departements: list = []
    countries: list = []
    montant_min: float = 0
    montant_max: float = 0
    limit: int = 20


@router.post("/api/invite/{token}/search")
@limiter.limit("30/hour")
def guest_search(token: str, body: GuestSearch, request: Request, db: Session = Depends(get_db)):
    """Recherche d'AO publics pour l'invité (découverte). Pas de LLM, pas de quota."""
    _valid_invite(token, db)
    from app.routers.sourcing import _tender_sources
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    countries = [c for c in (body.countries or ["FR"]) if c] or ["FR"]
    crit = TenderCriteria(query=(body.query or "").strip()[:200], departements=body.departements or [],
                          montant_min=body.montant_min or None, montant_max=body.montant_max or None,
                          limit=min(max(int(body.limit or 20), 1), 30), countries=countries)
    try:
        result = TenderSearchService(_tender_sources(countries)).search(crit, {}, {})
    except Exception:
        raise HTTPException(503, "La recherche est momentanément indisponible. Réessayez.")
    return {"count": result.get("count", 0),
            "tenders": [t.model_dump(exclude={"raw"}) for t in result.get("tenders", [])]}


# ── Pièces administratives du co-traitant (DC2, attestations…) ───────────────
_MAX_PIECES_PER_CONTRIB = 20


def _guest_piece(token: str, piece_id: int, db: Session):
    """Résout (invite, contribution, piece) en garantissant que la pièce appartient
    bien à la contribution de CE jeton — jamais celle d'un autre co-traitant."""
    inv = _valid_invite(token, db)
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if not c:
        raise HTTPException(404, "Aucune contribution")
    pc = db.query(ContributionPiece).filter(
        ContributionPiece.id == piece_id, ContributionPiece.contribution_id == c.id).first()
    if not pc:
        raise HTTPException(404, "Pièce introuvable")
    return inv, c, pc


_PIECE_TYPE_VALUES = ("kbis", "fiscale", "sociale", "assurance", "rib", "qualification", "autre")


def _parse_expiration(s) -> Optional[date]:
    """ISO 'AAAA-MM-JJ' → date ; '' / None → None ; autre → 422."""
    if s is None or str(s).strip() == "":
        return None
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        raise HTTPException(422, "Date d'expiration invalide (format attendu : AAAA-MM-JJ).")


def _check_piece_type(t) -> str:
    t = (t or "").strip().lower()
    if t and t not in _PIECE_TYPE_VALUES:
        raise HTTPException(422, "Type de pièce inconnu (kbis, fiscale, sociale, assurance, rib, qualification, autre).")
    return t


def _after_piece_change(inv, c, db: Session, request: Request) -> None:
    """Ajout/retrait d'une pièce après soumission → part en brouillon (+ offre défigée)."""
    was_submitted = (c.status == "submitted")
    if was_submitted:
        c.status = "draft"
        c.submitted_at = None
    db.commit()
    if was_submitted:
        _unfreeze_offer_if_needed(db, inv.project_id, c.company_name or inv.company_name or "un partenaire",
                                  actor=_guest_actor(inv), actor_kind="guest",
                                  ip=audit.client_ip(request), invite_id=inv.id)


@router.post("/api/invite/{token}/contribution/piece")
@limiter.limit("30/minute")
def guest_upload_piece(token: str, request: Request, file: UploadFile = File(...),
                       piece_type: str = Form(None), expiration_date: str = Form(None),
                       db: Session = Depends(get_db)):
    """Le co-traitant téléverse UNE de ses pièces administratives (scopée à sa part).
    Classée automatiquement (kbis / fiscale / sociale / assurance / rib / qualification)
    d'après son nom si `piece_type` n'est pas fourni ; `expiration_date` ISO optionnelle."""
    inv = _valid_invite(token, db)
    _refuse_if_demo_invite(inv, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    c = _get_or_create_contribution(inv, db)
    if db.query(ContributionPiece).filter(ContributionPiece.contribution_id == c.id).count() >= _MAX_PIECES_PER_CONTRIB:
        raise HTTPException(400, f"Maximum {_MAX_PIECES_PER_CONTRIB} pièces par partenaire.")
    ptype = _check_piece_type(piece_type)
    exp = _parse_expiration(expiration_date)
    content, ext = _read_upload(file)
    safe_mime = _safe_mime(file.filename)        # type dérivé de l'extension, pas du client
    file_key = f"{inv.owner_id}/cotraitant/{uuid.uuid4().hex}{ext}"
    get_storage().save(file_key, content, safe_mime)
    name = os.path.basename(file.filename or "piece")[:500]
    pc = ContributionPiece(
        contribution_id=c.id, project_id=inv.project_id, owner_id=inv.owner_id,
        name=name, file_key=file_key, file_size=len(content), mime_type=safe_mime[:100],
        piece_type=(ptype or _classify_piece_type(name)), expiration_date=exp)
    db.add(pc)
    # Cohérence avec le PUT : ajouter une pièce après soumission repasse la part en
    # brouillon, sinon le pli « soumis » que le mandataire croit figé change en douce.
    _after_piece_change(inv, c, db, request)
    db.refresh(pc)
    audit.record(db, action="guest.upload_piece", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", invite_id=inv.id,
                 target_type="piece", target_id=pc.id, detail=(pc.name or "")[:255],
                 ip=audit.client_ip(request))
    return _piece_dict(pc)


class PiecePatch(BaseModel):
    piece_type: Optional[str] = None
    expiration_date: Optional[str] = None   # ISO AAAA-MM-JJ ; '' = effacer


@router.patch("/api/invite/{token}/contribution/piece/{piece_id}")
@limiter.limit("60/minute")
def guest_patch_piece(token: str, piece_id: int, body: PiecePatch, request: Request,
                      db: Session = Depends(get_db)):
    """Le co-traitant corrige le TYPE et/ou la DATE D'EXPIRATION de SA pièce (coffre croisé)."""
    inv, c, pc = _guest_piece(token, piece_id, db)
    _refuse_if_demo_invite(inv, db)
    fields = body.model_fields_set
    if "piece_type" in fields:
        pc.piece_type = _check_piece_type(body.piece_type) or "autre"
    if "expiration_date" in fields:
        pc.expiration_date = _parse_expiration(body.expiration_date)
    db.commit()
    db.refresh(pc)
    # Journalisé : une date d'expiration corrigée change le statut du coffre croisé vu par
    # tous les membres — le journal du membre doit le refléter.
    audit.record(db, action="guest.update_piece", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="piece", target_id=pc.id, invite_id=inv.id,
                 detail=(pc.name or "")[:255], ip=audit.client_ip(request))
    return _piece_dict(pc)


class FromVault(BaseModel):
    document_id: int


@router.post("/api/invite/{token}/contribution/piece/from-vault")
@limiter.limit("30/minute")
def guest_piece_from_vault(token: str, body: FromVault, request: Request,
                           current_user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """« Joindre depuis mon coffre-fort » : le partenaire AVEC COMPTE (lien réclamé) joint
    un Document de SON coffre-fort personnel. Le fichier est COPIÉ dans le tenant du
    mandataire (clé {owner}/cotraitant/…) : le Document d'origine n'est jamais exposé."""
    inv = _valid_invite(token, db)
    _refuse_if_demo_invite(inv, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    if not inv.accepted_by_user_id or inv.accepted_by_user_id != current_user.id:
        raise HTTPException(403, "Réclamez d'abord ce lien avec votre compte pour joindre une pièce "
                                 "depuis votre coffre-fort.")
    doc = db.query(Document).filter(
        Document.id == body.document_id,
        Document.user_id.in_(member_ids(current_user, db)),
        Document.deleted_at.is_(None)).first()
    if not doc or not doc.file_key:
        raise HTTPException(404, "Document introuvable dans votre coffre-fort")
    c = _get_or_create_contribution(inv, db)
    if db.query(ContributionPiece).filter(ContributionPiece.contribution_id == c.id).count() >= _MAX_PIECES_PER_CONTRIB:
        raise HTTPException(400, f"Maximum {_MAX_PIECES_PER_CONTRIB} pièces par partenaire.")
    storage = get_storage()
    try:
        content = storage.load(doc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    if not content:
        raise HTTPException(410, "Fichier vide")
    ext = os.path.splitext(doc.file_key or doc.name or "")[1].lower() or os.path.splitext(doc.name or "")[1].lower()
    file_key = f"{inv.owner_id}/cotraitant/{uuid.uuid4().hex}{ext}"
    safe_mime = _safe_mime(file_key)     # extension réelle du fichier, pas le nom (renommable)
    storage.save(file_key, content, safe_mime)
    cat = doc.category.value if hasattr(doc.category, "value") else str(doc.category or "")
    ptype = {"fiscal": "", "assurances": "assurance", "qualifications": "qualification"}.get(cat, "")
    ptype = ptype or _classify_piece_type(doc.name or "")
    if cat == "fiscal" and ptype not in ("fiscale", "sociale"):
        ptype = "fiscale"
    pc = ContributionPiece(
        contribution_id=c.id, project_id=inv.project_id, owner_id=inv.owner_id,
        name=os.path.basename(doc.name or "piece")[:500], file_key=file_key,
        file_size=len(content), mime_type=safe_mime[:100],
        piece_type=ptype, expiration_date=doc.expiration_date, source_document_id=doc.id)
    db.add(pc)
    _after_piece_change(inv, c, db, request)
    db.refresh(pc)
    audit.record(db, action="guest.upload_piece", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", invite_id=inv.id,
                 target_type="piece", target_id=pc.id,
                 detail=f"{(pc.name or '')[:200]} (depuis mon coffre-fort)"[:255],
                 ip=audit.client_ip(request))
    return _piece_dict(pc)


@router.get("/api/invite/{token}/contribution/piece/{piece_id}")
@limiter.limit("60/minute")
def guest_download_piece(token: str, piece_id: int, request: Request, db: Session = Depends(get_db)):
    """Le co-traitant re-télécharge SA pièce."""
    inv, c, pc = _guest_piece(token, piece_id, db)
    return _stream_piece(pc)


@router.delete("/api/invite/{token}/contribution/piece/{piece_id}")
@limiter.limit("30/minute")
def guest_delete_piece(token: str, piece_id: int, request: Request, db: Session = Depends(get_db)):
    """Le co-traitant retire SA pièce."""
    inv, c, pc = _guest_piece(token, piece_id, db)
    _refuse_if_demo_invite(inv, db)
    try:
        get_storage().delete(pc.file_key)
    except Exception:
        pass
    db.delete(pc)
    # Comme le PUT : retirer une pièce après soumission repasse la part en brouillon
    # (le pli déposé ne doit pas perdre une pièce en silence après « soumission »).
    _after_piece_change(inv, c, db, request)
    return {"ok": True}


def _stream_piece(pc: ContributionPiece):
    storage = get_storage()
    signed = storage.url(pc.file_key, filename=pc.name)
    if signed:
        return RedirectResponse(signed)
    try:
        content = storage.load(pc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    return StreamingResponse(io.BytesIO(content),
                             media_type=_safe_mime(pc.file_key),
                             headers=_attachment_headers(pc.name))


@router.get("/api/projects/{project_id}/contribution-pieces/{piece_id}")
def owner_download_piece(project_id: int, piece_id: int, request: Request,
                         current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Le mandataire télécharge une pièce d'un co-traitant (scopée à SON projet)."""
    _owned_project(project_id, current_user, db)
    pc = db.query(ContributionPiece).filter(
        ContributionPiece.id == piece_id, ContributionPiece.project_id == project_id).first()
    if not pc:
        raise HTTPException(404, "Pièce introuvable")
    cb = db.query(ProjectContribution).filter(ProjectContribution.id == pc.contribution_id).first()
    # invite_id → l'entrée apparaît dans le JOURNAL DU MEMBRE concerné (« le mandataire a
    # téléchargé votre pièce « … » ») : la confiance est vérifiable, pas déclarée.
    audit.record(db, action="owner.download_piece", owner_id=pc.owner_id, project_id=project_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="piece", target_id=pc.id, detail=(pc.name or "")[:255],
                 invite_id=(cb.invite_id if cb else None), ip=audit.client_ip(request))
    return _stream_piece(pc)


def _record_owner_views(db: Session, project_id: int, owner_id: int, actor: str, ip: str,
                        contribs: list) -> None:
    """`owner.view_contribution` : UNE entrée par part et par heure au plus (dédoublonnée
    sur la dernière entrée même action / même part / même tenant). Le journal du membre
    dit « le mandataire a consulté votre part » sans devenir du bruit à chaque rafraîchissement."""
    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        for c in contribs:
            if not c or not c.invite_id:
                continue
            recent = db.query(AuditLog).filter(
                AuditLog.owner_id == owner_id, AuditLog.action == "owner.view_contribution",
                AuditLog.target_id == c.id, AuditLog.created_at >= since).first()
            if recent:
                continue
            audit.record(db, action="owner.view_contribution", owner_id=owner_id, project_id=project_id,
                         actor=actor, actor_kind="owner", target_type="contribution",
                         target_id=c.id, invite_id=c.invite_id,
                         detail=(c.company_name or "")[:255], ip=ip)
    except Exception:
        pass


@router.get("/api/projects/{project_id}/contributions")
def list_contributions(project_id: int, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Toutes les contributions des co-traitants de CE projet (toute l'organisation).
    Vue MANDATAIRE : prix de lot en clair, enveloppe chiffrée ABSENTE (has_detail_chiffre),
    et chaque consultation est journalisée vers le membre (owner.view_contribution)."""
    _owned_project(project_id, current_user, db)
    rows = db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id
    ).order_by(ProjectContribution.updated_at.desc()).all()
    active_ids = {i.id for i in active_invites(db, project_id)}
    _record_owner_views(db, project_id, data_owner_id(current_user, db), f"user:{current_user.id}", "",
                        [c for c in rows if c.invite_id in active_ids])
    return [_serialize_contribution(c, db, viewer="owner") for c in rows]


# Pondération de complétude d'UNE part de partenaire (somme = 1.0). Déterministe et
# explicable : le % de préparation n'est jamais "deviné" par l'IA, c'est un calcul.
_READINESS_WEIGHTS = {"submitted": 0.40, "lot": 0.15, "references": 0.15,
                      "memoire": 0.20, "qualifications": 0.10}


def _partner_flags(c) -> dict:
    return {
        "submitted": bool(c and c.status == "submitted"),
        "lot": bool(c and c.lot and c.lot.strip()),
        "references": bool(c and c.references),
        "memoire": bool(c and c.memoire_paragraph),
        "qualifications": bool(c and c.qualifications),
    }


def _partner_score(flags: dict) -> float:
    return min(1.0, sum(_READINESS_WEIGHTS[k] for k, v in flags.items() if v))


# Pièces administratives attendues de CHAQUE membre d'un groupement (au-delà des
# CERFA mutualisés). Permet au mandataire de voir, par partenaire, ce qui manque.
_PARTNER_PIECE_TYPES = [
    # Mots-clés resserrés : « registre » seul matchait « registre_de_securite.pdf ».
    ("kbis", "Kbis", ("kbis", "extrait k", "registre du commerce", "registre commerce", "rcs")),
    ("fiscale", "Attest. fiscale", ("fiscal", "impot", "impôt", "dgfip")),
    ("sociale", "Attest. sociale (URSSAF)", ("urssaf", "vigilance", "cotisation", "attestation sociale")),
    ("assurance", "Assurance (RC/décennale)", ("assurance", "rc pro", "responsabilite civile", "responsabilité civile", "decennale", "décennale")),
    ("rib", "RIB", ("rib", "iban", "releve d'identite bancaire", "relevé d'identité bancaire")),
]


# Types reconnus par NOM (classification à l'upload) : les 5 attendus + la qualification
# (exigée seulement si le DCE demande des qualifications — cf. coffre_croise).
_PIECE_TYPE_KEYWORDS = _PARTNER_PIECE_TYPES + [
    ("qualification", "Qualification / certificat",
     ("qualibat", "qualif", "certificat", "rge", "opqibi", "qualifelec", "iso")),
]
_PIECE_LABELS = {key: label for key, label, _kw in _PIECE_TYPE_KEYWORDS}
_PIECE_LABELS["autre"] = "Autre pièce"


def _classify_piece_type(name: str) -> str:
    """Clé de type ('kbis', 'sociale', 'qualification'…) déduite du nom, '' si inconnu."""
    n = (name or "").lower()
    for key, _label, kw in _PIECE_TYPE_KEYWORDS:
        if any(k in n for k in kw):
            return key
    return ""


def _classify_partner_pieces(names: list, piece_types: list = None) -> dict:
    """À partir des noms (et, si connus, des types posés par le déposant) des pièces d'un
    partenaire, déduit quels types administratifs attendus sont présents/absents.
    Renvoie aussi `types` : {nom: clé} pour chaque pièce reconnue."""
    low = [(n or "").lower() for n in names]
    types = list(piece_types or [])
    types += [""] * (len(low) - len(types))
    have, missing, by_name = [], [], {}
    for key, label, kw in _PARTNER_PIECE_TYPES:
        present = False
        for i, n in enumerate(low):
            t = (types[i] or "").strip().lower()
            if (t == key) or (t in ("", "autre") and any(k in n for k in kw)):
                present = True
                by_name[names[i]] = key
        (have if present else missing).append(label)
    for i, n in enumerate(names):
        if n not in by_name:
            k = (types[i] or "").strip().lower() or _classify_piece_type(n)
            if k:
                by_name[n] = k
    return {"have": have, "missing": missing, "types": by_name}


# ── Coffre-fort croisé (E) : statut des attestations de chaque membre ─────────
_EXPECTED_BASE = ["kbis", "fiscale", "sociale", "assurance", "rib"]


def _dce_requires_qualification(project) -> bool:
    try:
        a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
        details = a.get("details") if isinstance(a.get("details"), dict) else a
        reqs = details.get("qualifications_requises") if isinstance(details, dict) else None
        return bool(reqs)
    except Exception:
        return False


def _piece_status(pc, deadline) -> str:
    """present | valide_jusquau | expire_avant_limite | expire (manquant = pas de pièce)."""
    exp = getattr(pc, "expiration_date", None)
    if not exp:
        return "present"
    today = date.today()
    if exp < today:
        return "expire"
    if deadline and exp < deadline:
        return "expire_avant_limite"
    return "valide_jusquau"


def coffre_croise(db: Session, project, invites: list, viewer_invite_id: Optional[int],
                  for_owner: bool) -> dict:
    """Grille membres × pièces en STATUT seulement. Chaque membre voit le statut des
    attestations de TOUS (c'est le point du coffre croisé : savoir avant la date limite
    que l'URSSAF d'un partenaire expire), mais jamais le fichier ni même son nom
    (name/piece_id uniquement pour sa propre ligne ou pour le mandataire)."""
    deadline = project.deadline
    if isinstance(deadline, datetime):
        deadline = deadline.date()
    expected_keys = list(_EXPECTED_BASE) + (["qualification"] if _dce_requires_qualification(project) else [])
    expected = [{"key": k, "label": _PIECE_LABELS.get(k, k)} for k in expected_keys]

    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project.id).all()}
    pieces_by_contrib = {}
    for pc in db.query(ContributionPiece).filter(ContributionPiece.project_id == project.id).all():
        pieces_by_contrib.setdefault(pc.contribution_id, []).append(pc)

    members, alerts, all_complete = [], [], True
    for inv in invites:
        c = contribs.get(inv.id)
        company = (c.company_name if c and c.company_name else inv.company_name) or "Partenaire"
        is_me = (viewer_invite_id is not None and inv.id == viewer_invite_id)
        show_detail = for_owner or is_me
        pieces = {}
        complete = True
        for key in expected_keys:
            # Meilleure pièce du type : la plus tardive en expiration (ou sans date).
            cands = []
            for pc in pieces_by_contrib.get(c.id, []) if c else []:
                t = (getattr(pc, "piece_type", "") or "").strip().lower()
                if t == key or (t in ("", "autre") and _classify_piece_type(pc.name) == key):
                    cands.append(pc)
            if not cands:
                pieces[key] = {"status": "manquant"}
                complete = False
                alerts.append(f"{_PIECE_LABELS.get(key, key)} manquante : {company}")
                continue
            best = max(cands, key=lambda p: (p.expiration_date or date.max))
            status = _piece_status(best, deadline)
            entry = {"status": status}
            if best.expiration_date:
                entry["expiration_date"] = best.expiration_date.isoformat()
            if show_detail:
                entry["name"] = best.name
                entry["piece_id"] = best.id
            pieces[key] = entry
            if status in ("expire", "expire_avant_limite"):
                complete = False
                alerts.append(f"{_PIECE_LABELS.get(key, key)} de {company} "
                              + ("a expiré" if status == "expire" else "expire avant la date limite"))
        all_complete = all_complete and complete
        row = {"company": company, "role": inv.role or "cotraitant", "is_me": is_me,
               "pieces": pieces, "complete": complete}
        if for_owner:
            row["invite_id"] = inv.id
        members.append(row)
    return {"deadline": deadline.isoformat() if deadline else None, "expected": expected,
            "members": members, "all_complete": bool(invites) and all_complete, "alerts": alerts}


@router.get("/api/projects/{project_id}/coffre-croise")
def owner_coffre_croise(project_id: int, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Grille du coffre-fort croisé, vue mandataire (noms/ids de pièces inclus)."""
    project = _owned_project(project_id, current_user, db)
    return coffre_croise(db, project, active_invites(db, project.id), viewer_invite_id=None, for_owner=True)


@router.get("/api/invite/{token}/coffre-croise")
@limiter.limit("60/minute")
def guest_coffre_croise(token: str, request: Request, db: Session = Depends(get_db)):
    """Grille du coffre-fort croisé, vue membre : statuts de tous, détail de SA ligne seulement."""
    inv = _valid_invite(token, db)
    project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(404, "Projet introuvable ou retiré")
    if _network_pending(inv, db):        # aperçu minimal : pas la composition du groupement
        raise HTTPException(403, "Acceptez d'abord l'invitation depuis votre compte Adjugo pour voir "
                                 "les attestations du groupement.")
    return coffre_croise(db, project, active_invites(db, project.id), viewer_invite_id=inv.id, for_owner=False)


@router.get("/api/consortiums")
def my_consortiums(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tous les consortiums du mandataire (AO avec ≥1 partenaire) — pour l'accueil.
    Agrège partenaires, parts soumises, pièces et % de réponse prête par AO."""
    # Périmètre ORGANISATION : agrège les consortiums de toute l'équipe (comme la liste
    # des marchés et le tableau de bord), pas seulement ceux portés par le compte courant.
    ids = member_ids(current_user, db)
    invites = db.query(ProjectInvite).filter(
        ProjectInvite.owner_id.in_(ids), active_invite_filter()).all()
    if not invites:
        return {"consortiums": [], "active": 0, "partners_total": 0, "submitted_total": 0}
    pids = {i.project_id for i in invites}
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.owner_id.in_(ids),
        ProjectContribution.project_id.in_(pids)).all()}
    piece_counts = {}
    for pc in db.query(ContributionPiece).filter(
            ContributionPiece.owner_id.in_(ids),
            ContributionPiece.project_id.in_(pids)).all():
        piece_counts[pc.contribution_id] = piece_counts.get(pc.contribution_id, 0) + 1
    projects = {p.id: p for p in db.query(Project).filter(
        Project.id.in_(pids), Project.user_id.in_(ids), Project.deleted_at.is_(None)).all()}

    by_project = {}
    for inv in invites:
        by_project.setdefault(inv.project_id, []).append(inv)

    out, partners_total, submitted_total = [], 0, 0
    for pid, invs in by_project.items():
        proj = projects.get(pid)
        if not proj:
            continue
        total_score = submitted = pieces = 0
        for inv in invs:
            c = contribs.get(inv.id)
            flags = _partner_flags(c)
            total_score += _partner_score(flags)
            if flags["submitted"]:
                submitted += 1
            if c:
                pieces += piece_counts.get(c.id, 0)
        n = len(invs)
        partners_total += n
        submitted_total += submitted
        out.append({
            "project_id": pid, "project": proj.name,
            "status": proj.status.value if hasattr(proj.status, "value") else str(proj.status or ""),
            "deadline": proj.deadline.isoformat() if proj.deadline else None,
            "partners": n, "submitted": submitted, "pieces": pieces,
            "readiness_pct": round(100 * total_score / n) if n else 0,
        })
    out.sort(key=lambda x: (-x["submitted"], -x["readiness_pct"]))
    return {"consortiums": out, "active": len(out),
            "partners_total": partners_total, "submitted_total": submitted_total}


@router.get("/api/projects/{project_id}/consortium")
def consortium_cockpit(project_id: int, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Cockpit du consortium (mandataire) : partenaires × lots, complétude de chaque part,
    et % de réponse commune PRÊTE — calcul DÉTERMINISTE (jamais inventé).
    Doctrine : le mandataire voit le PRIX DE LOT de chaque membre (prix_lot_ht), jamais la
    décomposition. Inclut l'état dérivé du groupement (`state`) et le coffre croisé (`coffre`)."""
    project = _owned_project(project_id, current_user, db)
    invites = active_invites(db, project_id)       # membres = invitations actives (ni révoquées ni déclinées)
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id).all()}
    piece_counts, piece_names, piece_types = {}, {}, {}
    for pc in db.query(ContributionPiece).filter(
            ContributionPiece.project_id == project_id).all():
        piece_counts[pc.contribution_id] = piece_counts.get(pc.contribution_id, 0) + 1
        piece_names.setdefault(pc.contribution_id, []).append(pc.name or "")
        piece_types.setdefault(pc.contribution_id, []).append(getattr(pc, "piece_type", "") or "")
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()

    partners, lots, missing, total_score = [], {}, [], 0.0
    for inv in invites:
        c = contribs.get(inv.id)
        lot_clean = (c.lot.strip() if c and c.lot else "")   # évite une clé de lot vide/espaces
        flags = _partner_flags(c)
        score = _partner_score(flags)                          # borné [0,1]
        total_score += score
        name = (c.company_name if c and c.company_name else inv.company_name) or "Partenaire"
        pclass = _classify_partner_pieces(piece_names.get(c.id, []) if c else [],
                                          piece_types.get(c.id, []) if c else [])
        has_price = bool(c and c.prix_lot_ht is not None)
        partners.append({
            "invite_id": inv.id,
            "company": name, "role": inv.role or "cotraitant",
            "lot": lot_clean, "status": (c.status if c else "invited"),
            "has_references": flags["references"], "has_memoire": flags["memoire"],
            "has_price": has_price,
            "prix_lot_ht": (c.prix_lot_ht if has_price else None),      # vue mandataire
            "has_detail_chiffre": bool(c and isinstance(c.detail_chiffre, dict) and c.detail_chiffre),
            "capacites": (c.capacites if c and isinstance(c.capacites, dict) else None),
            "qualifications_count": len(c.qualifications or []) if c else 0,
            "pieces_count": (piece_counts.get(c.id, 0) if c else 0),
            "pieces_have": pclass["have"], "pieces_missing": pclass["missing"],
            "completeness": round(score * 100),
        })
        if lot_clean:
            lots.setdefault(lot_clean, []).append(name)
        # File des manques (concrets, actionnables) — le plus bloquant d'abord.
        if not flags["submitted"]:
            missing.append(f"{name} n'a pas encore soumis sa part")
        elif not has_price:
            missing.append(f"{name} : prix de lot manquant")
        elif not flags["memoire"]:
            missing.append(f"{name} : paragraphe de mémoire manquant")
        elif not flags["lot"]:
            missing.append(f"{name} : lot/périmètre non précisé")
        elif not flags["references"]:
            missing.append(f"{name} : aucune référence renseignée")
        elif pclass["missing"]:
            # Part soumise mais pièces administratives obligatoires absentes du membre.
            missing.append(f"{name} : pièce(s) à fournir — {', '.join(pclass['missing'][:3])}")

    # Conformité (politique : AVERTIR, pas bloquer) — un lot ne peut avoir qu'UN attributaire
    # en groupement conjoint : on signale tout lot revendiqué par plusieurs partenaires.
    for k, names in lots.items():
        if len(names) > 1:
            missing.insert(0, f"Lot « {k} » revendiqué par {len(names)} partenaires "
                              f"({', '.join(names[:3])}) — un lot ne peut avoir qu'un seul attributaire")

    # Coffre croisé : attestations manquantes / expirant avant la date limite.
    coffre = coffre_croise(db, project, invites, viewer_invite_id=None, for_owner=True)
    for a in coffre.get("alerts", []):
        if a not in missing:
            missing.append(a)

    # Journal membre : « le mandataire a consulté votre part » (1 entrée / part / heure).
    _record_owner_views(db, project_id, data_owner_id(current_user, db), f"user:{current_user.id}", "",
                        [contribs.get(inv.id) for inv in invites])

    n = len(invites)
    pct = round(100 * total_score / n) if n else 0
    state = groupement_state(project, db)
    return {
        "partners": partners,
        "lots": [{"lot": k, "partners": v} for k, v in lots.items()],
        "readiness": {
            "invited": n,
            "submitted": sum(1 for p in partners if p["status"] == "submitted"),
            "lots": len(lots),
            "pct": pct,
            "missing": missing[:12],
        },
        "mandataire": {
            "company": (company.name if company else "") or "",
            "qualifications": len(company.qualifications or []) if company else 0,
        },
        "state": state,
        "coffre": coffre,
        "offre": {
            "frozen": bool(state.get("offer_frozen")),
            "total_ht": state.get("total_offre_ht"),
            "frozen_at": state.get("frozen_at"),
            "total_ht_estime": total_offre_ht(project, db),   # None si un membre n'a pas de prix
            "lead_total_ht": (float(project.estimate.get("total_ht"))
                              if isinstance(project.estimate, dict) and project.estimate.get("total_ht") is not None
                              else None),
            "warning_two_members": (n + 1) == 2,
        },
    }


# ── Figer l'offre commune (minimal, vague 1) ─────────────────────────────────
class FreezeBody(BaseModel):
    lead_total_ht: Optional[float] = None    # part du mandataire si pas de chiffrage (estimate)


@router.post("/api/projects/{project_id}/offre/figer")
def freeze_offer(project_id: int, request: Request, body: FreezeBody = None,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fige l'offre commune : total = prix de lot de chaque membre (part soumise) + part du
    mandataire. C'est SEULEMENT à partir de là que les membres voient le total (avec
    l'avertissement « à 2 membres, le total révèle la part de l'autre »)."""
    project = _owned_project(project_id, current_user, db)
    # Vague 2 : « Figer l'offre » est fusionné avec la génération de la convention. Une
    # convention générée porte déjà l'offre figée : la re-figer ici la désynchroniserait.
    from app.services.groupement_convention import get_convention as _get_conv
    _conv = _get_conv(db, project_id)
    if _conv is not None and _conv.status in ("a_signer", "signee"):
        raise HTTPException(409, {"code": "convention_generee",
                                  "message": "L'offre est déjà figée par la convention de groupement. Pour la "
                                             "modifier, régénérez la convention."})
    if _conv is not None:
        # Brouillon ou convention périmée : l'offre ne se fige QUE par la génération (qui révèle le
        # total en même temps que l'annexe). Figer ici révélait le total et les nouveaux prix aux
        # partenaires avant toute convention (doctrine de visibilité, relecture vague 2).
        raise HTTPException(409, {"code": "convention_a_generer",
                                  "message": "Avec une convention de groupement, l'offre se fige en générant la "
                                             "convention (« Monter le groupement »)."})
    invites = active_invites(db, project_id)
    if not invites:
        raise HTTPException(422, "Aucun partenaire actif : invitez au moins un partenaire avant de figer l'offre.")
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id).all()}
    manques = []
    for inv in invites:
        c = contribs.get(inv.id)
        name = (c.company_name if c and c.company_name else inv.company_name) or "Partenaire"
        if not c or c.status != "submitted":
            manques.append(f"{name} n'a pas encore soumis sa part")
        elif c.prix_lot_ht is None:
            manques.append(f"{name} : prix de lot manquant")
    if manques:
        raise HTTPException(422, {"message": "Impossible de figer l'offre : il manque des éléments.",
                                  "missing": manques})
    lead = body.lead_total_ht if body and body.lead_total_ht is not None else None
    if lead is not None and (lead < 0 or lead > 1e10):
        raise HTTPException(422, "Part du mandataire invalide.")
    total = total_offre_ht(project, db, lead_total=lead)
    if total is None:
        raise HTTPException(422, "Impossible de calculer le total : vérifiez les prix de lot.")
    est = project.estimate if isinstance(project.estimate, dict) else {}
    lead_total = lead if lead is not None else (
        float(est["total_ht"]) if est.get("total_ht") is not None else None)
    if lead_total is None:
        # Sans la part du mandataire, le « total de l'offre commune » envoyé aux membres
        # serait faux (somme des seules parts des partenaires).
        raise HTTPException(422, {"message": "Indiquez votre propre part (€ HT) : aucun chiffrage "
                                             "n'est enregistré pour ce marché.",
                                  "missing": ["Votre part (mandataire) : montant € HT"]})
    frozen_at = utcnow().isoformat()
    parts = [{"invite_id": inv.id,
              "company": (contribs[inv.id].company_name or inv.company_name or "Partenaire"),
              "prix_lot_ht": float(contribs[inv.id].prix_lot_ht)} for inv in invites]
    plan = dict(project.groupement_plan) if isinstance(project.groupement_plan, dict) else {}
    plan["offre"] = {"total_ht": total, "frozen_at": frozen_at, "parts": parts, "lead_total_ht": lead_total}
    project.groupement_plan = plan          # NOUVEAU dict : SQLAlchemy détecte le changement
    db.commit()
    audit.record(db, action="offer.frozen", owner_id=data_owner_id(current_user, db), project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner", target_type="project",
                 target_id=project.id, detail=f"total {total:,.0f} € HT".replace(",", " ")[:255],
                 ip=audit.client_ip(request))
    # Emails best-effort à chaque membre — hors requête (jamais bloquant).
    try:
        base = (_settings.APP_BASE_URL or "").rstrip("/")
        total_txt = f"{total:,.0f}".replace(",", " ")
        mails = [(inv.recipient, f"L'offre commune est figée — {project.name[:60]}",
                  f"Bonjour,\n\nLe mandataire a figé l'offre commune du groupement sur le marché "
                  f"« {project.name} » : total {total_txt} € HT.\n\n"
                  f"Retrouvez le détail dans votre espace : {base}/invite/{inv.token}\n\n— Adjugo")
                 for inv in invites if _is_email(inv.recipient)]
        from app.services.demo_search import is_demo
        if not is_demo(current_user):          # la démo n'envoie jamais d'email
            _send_mails_async(mails)
    except Exception:
        pass
    return {"ok": True, "total_ht": total, "frozen_at": frozen_at, "n_members": len(invites),
            "warning_two_members": (len(invites) + 1) == 2}


@router.delete("/api/projects/{project_id}/offre/figer")
def unfreeze_offer(project_id: int, request: Request,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Défige l'offre commune (le total n'est plus montré aux membres)."""
    _owned_project(project_id, current_user, db)
    done = _unfreeze_offer_if_needed(db, project_id, "défigée par le mandataire",
                                     actor=f"user:{current_user.id}", actor_kind="owner",
                                     ip=audit.client_ip(request))
    return {"ok": True, "was_frozen": done}


# ── Journal MEMBRE (D) : projection « qui a vu quoi » pour UNE invitation ────
# Événements « de groupement » visibles par TOUS les membres (pas seulement le concerné).
GROUP_EVENTS = {"offer.frozen", "offer.unfrozen", "groupement.retenue", "convention.generated",
                "convention.signed", "invite.created", "invite.revoked", "invite.declined",
                # Vague 2 (convention) : caducité et accord hors ligne, visibles de tous les membres.
                "convention.perimee", "convention.hors_ligne"}

# Libellés en français simple (zéro jargon) selon QUI a agi, vu depuis le membre.
_JOURNAL_LABELS_ME = {
    "guest.view_project": "Vous avez consulté le dossier",
    "guest.download_doc": "Vous avez téléchargé une pièce du dossier",
    "guest.submit_contribution": "Vous avez soumis votre part",
    "guest.upload_piece": "Vous avez déposé une pièce",
    "guest.update_piece": "Vous avez mis à jour une pièce (type ou date de validité)",
    "guest.capacites_updated": "Vous avez mis à jour vos capacités",
    "guest.otp_request": "Vous avez demandé un code de vérification",
    "guest.otp_verified": "Vous avez vérifié votre adresse email",
    "invite.claimed": "Vous avez rattaché ce dossier à votre compte",
    "invite.declined": "Vous avez décliné l'invitation",
    "offer.unfrozen": "Votre modification a défigé l'offre commune",
    # Vague 2 : « accord enregistré », jamais « signature électronique ».
    "convention.signed": "Vous avez validé la convention (accord enregistré)",
    "convention.perimee": "Votre modification a rendu la convention caduque : elle doit être régénérée",
    "guest.download_convention": "Vous avez téléchargé la convention",
}
_JOURNAL_LABELS_OWNER = {
    "owner.view_contribution": "Le mandataire a consulté votre part",
    "owner.download_piece": "Le mandataire a téléchargé votre pièce",
    "owner.view_piece": "Le mandataire a consulté votre pièce",
    "invite.created": "Le mandataire vous a invité",
    "invite.resent": "Le mandataire vous a renvoyé l'invitation",
    "invite.revoked": "Le mandataire vous a retiré du groupement",
    "offer.frozen": "Le mandataire a figé l'offre commune",
    "offer.unfrozen": "Le mandataire a défigé l'offre commune",
    "groupement.retenue": "Le mandataire a retenu la composition du groupement",
    "convention.generated": "Le mandataire a généré la convention de groupement",
    "convention.signed": "Le mandataire a validé la convention (accord enregistré)",
    "convention.perimee": "La convention n'est plus à jour : le mandataire doit la régénérer",
    "convention.hors_ligne": "Le mandataire a enregistré l'accord hors ligne d'un partenaire",
    "piece.expiring": "Adjugo vous a alerté : une attestation manque ou expire",
}
_JOURNAL_LABELS_PARTNER = {
    "invite.created": "Un partenaire a été invité",
    "invite.declined": "Un partenaire a décliné",
    "invite.revoked": "Un partenaire a été retiré",
    "convention.signed": "Un partenaire a validé la convention (accord enregistré)",
    "offer.unfrozen": "L'offre commune a été défigée (part d'un partenaire modifiée)",
    "convention.perimee": "La convention n'est plus à jour (part d'un partenaire modifiée)",
}


_CHAIN_CACHE: dict = {}        # owner_id → (ts, intact) — process unique, TTL 5 min
_CHAIN_TTL = 300


def _chain_intact_cached(db: Session, owner_id: int) -> bool:
    """verify_chain = full-scan + re-hash de TOUT le journal du tenant : sur une route invitée
    à 60/min ce serait un DoS trivial de l'unique worker → résultat mis en cache 5 min."""
    import time as _time
    hit = _CHAIN_CACHE.get(owner_id)
    now = _time.time()
    if hit and now - hit[0] < _CHAIN_TTL:
        return hit[1]
    try:
        intact = bool(audit.verify_chain(db, owner_id).get("intact"))
    except Exception:
        intact = False
    _CHAIN_CACHE[owner_id] = (now, intact)
    return intact


@router.get("/api/invite/{token}/journal")
@limiter.limit("60/minute")
def guest_journal(token: str, request: Request, db: Session = Depends(get_db)):
    """Journal « qui a vu quoi » DU MEMBRE : ses entrées (invite_id = la sienne) + les
    événements de groupement du projet. Projection SANS ip, SANS email, SANS target_id
    d'un autre ; l'acteur devient « vous » / « mandataire » / « partenaire »."""
    inv = _valid_invite(token, db)
    if _network_pending(inv, db):
        # Invitation réseau pas encore acceptée : SES entrées seulement (pas la composition).
        cond = (AuditLog.invite_id == inv.id)
    else:
        cond = ((AuditLog.invite_id == inv.id) | (AuditLog.action.in_(list(GROUP_EVENTS))))
    rows = db.query(AuditLog).filter(
        AuditLog.project_id == inv.project_id, cond
    ).order_by(AuditLog.created_at.desc()).limit(200).all()
    # Noms d'entreprise des autres invitations (pour les événements de groupement).
    other_ids = {r.invite_id for r in rows if r.invite_id and r.invite_id != inv.id}
    names = {}
    if other_ids:
        names = {i.id: (i.company_name or "") for i in db.query(ProjectInvite).filter(
            ProjectInvite.id.in_(other_ids)).all()}
    out = []
    for r in rows:
        mine = (r.invite_id == inv.id)
        if mine and r.actor_kind == "guest":
            who, label = "vous", _JOURNAL_LABELS_ME.get(r.action, r.action)
            detail = r.detail or ""
        elif mine:                                   # le mandataire (ou Adjugo) a agi sur MA part
            who, label = "mandataire", _JOURNAL_LABELS_OWNER.get(r.action, r.action)
            detail = r.detail or ""
            if r.action in ("owner.download_piece", "owner.view_piece") and detail:
                label = f"{label} « {detail} »"
        elif r.action in GROUP_EVENTS and r.actor_kind in ("guest", "system") and r.invite_id:
            who, label = "partenaire", _JOURNAL_LABELS_PARTNER.get(r.action, r.action)
            detail = names.get(r.invite_id, "") or ""
        elif r.action in GROUP_EVENTS:
            who, label = "mandataire", _JOURNAL_LABELS_OWNER.get(r.action, r.action)
            # invite.created / invite.revoked concernent un AUTRE membre → libellé partenaire.
            if r.action in ("invite.created", "invite.revoked", "invite.declined"):
                who, label = "partenaire", _JOURNAL_LABELS_PARTNER.get(r.action, r.action)
            detail = names.get(r.invite_id, "") if r.invite_id else (
                r.detail if r.action in ("offer.frozen", "convention.generated", "convention.hors_ligne") else "")
        else:
            continue
        # Jamais un email en clair dans la projection (anciennes entrées : actor = email).
        if _is_email(detail):
            detail = ""
        out.append({"at": r.created_at.isoformat() if r.created_at else None,
                    "action": r.action, "label": label, "who": who, "detail": (detail or "")[:255]})
    try:
        chained = _chain_intact_cached(db, inv.owner_id)
    except Exception:
        chained = False
    return {"entries": out, "chained": chained,
            "integrity_label": "Journal infalsifiable tenu par Adjugo (chaîne de hachage)"}


# ── Notifications (activité des partenaires, in-app) ─────────────────────────
# Pas de modèle dédié : on s'appuie sur audit_logs (déjà rempli). Le mandataire voit
# l'activité de ses co-traitants sur TOUS ses AO d'un coup d'œil.
_NOTIF_LABELS = {
    "guest.submit_contribution": "a soumis sa part",
    "guest.upload_piece": "a déposé une pièce",
    "guest.view_project": "a consulté le dossier",
    "invite.declined": "a décliné l'invitation",
    "guest.capacites_updated": "a mis à jour ses capacités",
    "convention.signed": "a validé la convention de groupement",
}


@router.get("/api/notifications")
def notifications(current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), days: int = 21):
    """Activité récente des co-traitants sur les AO du mandataire (in-app, sans email)."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 90)))
    ids = member_ids(current_user, db)
    rows = db.query(AuditLog).filter(
        AuditLog.owner_id.in_(ids), AuditLog.actor_kind == "guest",
        AuditLog.action.in_(list(_NOTIF_LABELS)),
        AuditLog.created_at >= since
    ).order_by(AuditLog.created_at.desc()).limit(40).all()
    pids = {r.project_id for r in rows if r.project_id}
    names = {}
    if pids:
        names = {p.id: p.name for p in db.query(Project).filter(
            Project.id.in_(pids), Project.user_id.in_(ids)).all()}
    return [{
        "id": r.id, "at": r.created_at.isoformat() if r.created_at else None,
        "project_id": r.project_id, "project": names.get(r.project_id, "Appel d'offres"),
        "actor": r.actor or "Un partenaire", "action": r.action,
        "label": _NOTIF_LABELS.get(r.action, r.action), "detail": r.detail or "",
    } for r in rows]


# ── Compte-à-compte : « Partagé avec moi » ───────────────────────────────────
# Si l'invité possède un compte Adjugo, il réclame le lien → l'AO partagé apparaît
# dans SON espace (il contribue en tant que lui-même, pas en invité bridé).
def _shared_item(inv: ProjectInvite, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    owner_company = db.query(Company).filter(Company.user_id == inv.owner_id).first()
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    out = {
        "token": inv.token, "project_id": inv.project_id,
        "project": (project.name if project else "Appel d'offres"),
        "mandataire": (owner_company.name if owner_company else "") or "",
        "role": inv.role or "cotraitant",
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "contribution_status": (c.status if c else None),
        "deadline": project.deadline.isoformat() if project and project.deadline else None,
    }
    # Vague 2 : étape du groupement (stepper 1→5) et « convention à valider » pour CE membre.
    # Statuts seulement : jamais de prix, jamais le score seul du mandataire.
    out["groupement"] = None
    if project is not None:
        try:
            st = groupement_state(project, db)
            from app.models import GroupementSignature
            conv = st.get("convention") or {}
            sig = None
            if conv.get("id"):
                sig = db.query(GroupementSignature).filter(
                    GroupementSignature.convention_id == conv["id"],
                    GroupementSignature.invite_id == inv.id).first()
            out["groupement"] = {
                "state": st.get("state"), "label": st.get("label"), "index": st.get("index"),
                "etape": st.get("etape"), "etapes": st.get("etapes"),
                "convention_status": conv.get("status") or "",
                "a_valider": bool(sig is not None and conv.get("status") == "a_signer" and sig.status == "pending"),
            }
        except Exception:
            out["groupement"] = None
    return out


@router.post("/api/invite/{token}/claim")
def claim_invite(token: str, request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Un titulaire de compte réclame un lien → l'AO entre dans son « Partagé avec moi »."""
    inv = _valid_invite(token, db)
    if inv.owner_id in member_ids(current_user, db):
        raise HTTPException(400, "Vous êtes le mandataire de ce partage.")
    if inv.accepted_by_user_id and inv.accepted_by_user_id != current_user.id:
        raise HTTPException(409, "Ce lien a déjà été réclamé par un autre compte.")
    # Binding d'identité : si le lien cible une adresse précise, seul le compte de CETTE
    # adresse peut le réclamer (le secret de l'URL ne suffit plus à usurper le partenaire).
    if _is_email(inv.recipient):
        if (current_user.email or "").strip().lower() != inv.recipient.strip().lower():
            raise HTTPException(403, f"Ce lien est réservé à {_mask_email(inv.recipient)}. "
                                     f"Connectez-vous avec ce compte pour l'accepter.")
        # …et cette adresse doit être PROUVÉE : sinon n'importe qui pouvait créer un compte
        # avec l'email du partenaire (jamais confirmé) et verrouiller le lien à sa place.
        if not getattr(current_user, "email_verified", False):
            raise HTTPException(403, "Confirmez d'abord votre adresse email (lien reçu par mail) "
                                     "pour accepter ce partage nominatif.")
    if not inv.accepted_by_user_id:
        inv.accepted_by_user_id = current_user.id
        db.commit()
        audit.record(db, action="invite.claimed", owner_id=inv.owner_id, project_id=inv.project_id,
                     actor=(inv.company_name or "invité")[:160],
                     actor_kind="guest", target_type="invite", target_id=inv.id, invite_id=inv.id,
                     detail="", ip=audit.client_ip(request))
    out = _shared_item(inv, db)
    # Boucle de croissance (vague 3) : simple SUGGESTION d'interface « publiez votre profil
    # partenaire » si l'organisation n'en a pas de publié — jamais d'email non sollicité.
    from app.services.partner_network import suggest_profile
    out["suggest_profile"] = suggest_profile(db, current_user)
    return out


@router.get("/api/shared")
def shared_with_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les AO partagés AVEC moi (liens que j'ai réclamés). Pour « Partagé avec moi »."""
    rows = db.query(ProjectInvite).filter(
        ProjectInvite.accepted_by_user_id == current_user.id,
        active_invite_filter()).order_by(ProjectInvite.created_at.desc()).all()
    return [_shared_item(inv, db) for inv in rows if not _is_expired(inv.expires_at)]


# ── Aperçu du dossier commun (ce que contiendra le ZIP) — sans le générer ────
@router.get("/api/projects/{project_id}/dossier-preview")
def dossier_preview(project_id: int, current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Liste les fichiers que contiendra le dossier commun, SANS lancer la génération
    (pas de LLM, pas de quota) — pour voir avant d'exporter."""
    _owned_project(project_id, current_user, db)
    files = [
        {"name": "memoire_technique.pdf", "kind": "Mémoire technique (savoir-faire fusionnés)"},
        {"name": "cerfa/DC1.pdf", "kind": "CERFA — lettre de candidature (groupement)"},
        {"name": "cerfa/DC2.pdf", "kind": "CERFA — déclaration du candidat"},
        {"name": "cerfa/ATTRI1.pdf", "kind": "CERFA — acte d'engagement"},
        {"name": "synthese_groupement.pdf", "kind": "Composition du groupement"},
        {"name": "fiche_appel_offres.pdf", "kind": "Fiche récapitulative de l'AO"},
    ]
    # Exclut les partenaires RÉVOQUÉS ou qui ont DÉCLINÉ (comme build_dossier) : l'aperçu
    # doit refléter exactement le ZIP réellement assemblé, jamais les pièces d'un partenaire sorti.
    rows = db.query(ContributionPiece, ProjectContribution).join(
        ProjectContribution, ContributionPiece.contribution_id == ProjectContribution.id).join(
        ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
        ContributionPiece.project_id == project_id,
        ProjectContribution.status == "submitted",
        active_invite_filter()).all()
    for pc, cb in rows:
        co = (cb.company_name or "cotraitant")
        files.append({"name": f"pieces_cotraitants/{co}/{pc.name}",
                      "kind": f"Pièce — {co}", "size": pc.file_size or 0})
    n_pieces = len(rows)
    # Vague 2 : la convention de groupement générée (texte figé + accords) part dans le dossier.
    try:
        from app.services.groupement_convention import STATUS_LABELS, get_convention
        _conv = get_convention(db, project_id)
        if _conv is not None and _conv.status in ("a_signer", "signee"):
            files.append({"name": "convention_groupement.pdf",
                          "kind": f"Convention de groupement v{_conv.version} — {STATUS_LABELS.get(_conv.status, '')}"})
    except Exception:
        pass
    return {"files": files, "count": len(files), "pieces_count": n_pieces}


# ── Compte-rendu PDF du consortium (synthèse partageable) ────────────────────
@router.get("/api/projects/{project_id}/consortium/report")
def consortium_report(project_id: int, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    project = _owned_project(project_id, current_user, db)
    data = consortium_cockpit(project_id, current_user, db)
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    # Cloisonnement : le compte-rendu est « partageable » → il ne doit JAMAIS exposer
    # l'apport d'un partenaire RÉVOQUÉ/DÉCLINÉ, ni AUCUN prix par membre (doctrine de
    # visibilité : le PDF n'imprime que le total de l'offre FIGÉE). Vue owner : enveloppe absente.
    contribs = [_serialize_contribution(c, db, viewer="owner") for c in db.query(ProjectContribution).join(
        ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
        ProjectContribution.project_id == project_id,
        active_invite_filter()).all()]
    from app.services.consortium_report import generate_consortium_report_pdf
    pdf = generate_consortium_report_pdf(project.name, (company.name if company else ""), data, contribs)
    safe = re.sub(r'[^A-Za-z0-9._ -]', "_", (project.name or "consortium"))[:50]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Compte-rendu_{safe}.pdf"'})
