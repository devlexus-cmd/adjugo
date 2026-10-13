"""
Tâches d'administration / cron.
  - POST /api/admin/run-alerts : scanne les documents expirants et envoie les alertes.
    Protégé par l'en-tête X-Cron-Secret == CRON_SECRET (ou DEMO_MODE en dev).
    À appeler quotidiennement depuis un planificateur (cron, Vercel Cron…).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services.alerts import (run_document_expiry_alerts, run_tender_alerts, run_amont_alerts,
                                 run_cotraitance_reminders)

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["Administration"])


@router.get("/storage-diag")
def storage_diag(current_user: User = Depends(get_current_user)):
    """Diagnostic du stockage (sans exposer les secrets) : ce que le serveur voit
    réellement + un test d'écriture/lecture sur le bucket. RÉSERVÉ aux administrateurs."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    s = settings

    def mask(v):
        v = v or ""
        return {"length": len(v), "preview": (v[:3] + "…" + v[-2:]) if len(v) > 6 else ("*" * len(v))}

    info = {
        "backend": s.STORAGE_BACKEND,
        "bucket": s.S3_BUCKET,
        "endpoint": s.S3_ENDPOINT_URL,
        "region": s.S3_REGION,
        "access_key": mask(s.AWS_ACCESS_KEY_ID),                 # attendu length=32 pour R2
        "secret_key_length": len(s.AWS_SECRET_ACCESS_KEY or ""),  # attendu 64
    }
    try:
        from app.services.storage import get_storage
        st = get_storage()
        key = f"_diag/{current_user.id}.txt"
        st.save(key, b"adjugo-diag", "text/plain")
        ok = st.load(key) == b"adjugo-diag"
        st.delete(key)
        info["test"] = "OK — écriture/lecture/suppression réussies" if ok else "ÉCHEC — relecture incohérente"
    except Exception as e:
        info["test"] = "ÉCHEC"
        info["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return info


def _check_cron(request: Request):
    # Endpoints cron PUBLICS (sans login) : on EXIGE toujours le secret. Plus de
    # contournement DEMO_MODE — sinon, secret vide + DEMO_MODE=True rendait run-alerts /
    # run-tender-alerts / run-amont-alerts (emails + IA) déclenchables par n'importe qui.
    import secrets as _secrets
    secret = settings.CRON_SECRET
    if not secret:
        raise HTTPException(403, "CRON_SECRET non configuré")
    provided = request.headers.get("x-cron-secret", "")
    # Comparaison à temps constant sur des OCTETS : compare_digest refuse deux str non ASCII
    # (TypeError → erreur 500 au lieu d'un refus propre).
    if not _secrets.compare_digest(provided.encode("utf-8", "surrogateescape"), secret.encode("utf-8")):
        raise HTTPException(403, "Secret cron invalide")


@router.post("/run-backup")
def run_backup_now(current_user: User = Depends(get_current_user)):
    """Déclenche une sauvegarde immédiate de la base vers R2. Réservé à l'administrateur.
    (La sauvegarde tourne aussi toute seule chaque jour via le planificateur.)"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    from app.services.backup import run_backup
    return run_backup(keep=settings.BACKUP_KEEP)


@router.get("/backups")
def list_backups(current_user: User = Depends(get_current_user)):
    """Liste les sauvegardes présentes dans R2 (preuve que le filet fonctionne)."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    from app.services.storage import get_storage
    from app.services.backup import PREFIX, is_backup_key
    keys = sorted([k for k in get_storage().list_keys(PREFIX) if is_backup_key(k)], reverse=True)
    return {"count": len(keys), "backups": keys[:30],
            "encrypted": sum(1 for k in keys if k.endswith(".enc"))}


@router.post("/run-alerts")
def run_alerts(request: Request, db: Session = Depends(get_db)):
    _check_cron(request)
    return run_document_expiry_alerts(db)


@router.post("/run-tender-alerts")
def run_tender_alerts_endpoint(request: Request, db: Session = Depends(get_db)):
    """Veille AO : rejoue les recherches sauvegardées et notifie les nouveaux marchés."""
    _check_cron(request)
    return run_tender_alerts(db)


@router.post("/run-amont-alerts")
def run_amont_alerts_endpoint(request: Request, db: Session = Depends(get_db)):
    """Veille AMONT : va chercher les délibérations, détecte les projets d'investissement
    et notifie chaque utilisateur de ses nouveaux projets pertinents (avant l'AO)."""
    _check_cron(request)
    return run_amont_alerts(db)


@router.post("/run-cotraitance-reminders")
def run_cotraitance_reminders_endpoint(request: Request, db: Session = Depends(get_db)):
    """Relance les partenaires d'un groupement qui n'ont pas soumis leur part, à J-3 puis
    J-1 de la date limite (idempotent par palier). À cron-er quotidiennement."""
    _check_cron(request)
    return run_cotraitance_reminders(db)


@router.post("/run-trash-purge")
def run_trash_purge_endpoint(request: Request, db: Session = Depends(get_db)):
    """Vide la corbeille du coffre-fort : documents supprimés depuis plus de 30 jours
    (ligne + fichier du stockage + anciennes versions). À cron-er quotidiennement."""
    _check_cron(request)
    from app.routers.rgpd import purge_trash
    from app.services.analyse_partagee import purger
    res = purge_trash(db)
    # Rédaction, vague 4 : brouillons des partenaires d'une invitation expirée (ou retirée : filet) et
    # tâches terminées des partenaires, au-delà de 30 jours.
    from app.services.atelier_groupement import purger as purger_parts
    res.update(purger_parts(db))
    # Analyse partagée : extractions plus resservies depuis ANALYSE_PARTAGEE_JOURS jours, mesures anciennes.
    res.update(purger(db))
    return res


@router.post("/run-partner-network")
@limiter.limit("12/hour")
def run_partner_network_endpoint(request: Request, db: Session = Depends(get_db)):
    """Réseau de partenaires (vague 3) : re-vérifie SIRENE / BODACC / DECP des 25 profils
    publiés vérifiés le plus anciennement (timeouts courts, budget temps borné). Dépublie
    UNIQUEMENT sur une réponse positive « cessé » de SIRENE, jamais sur une erreur réseau.
    À cron-er chaque semaine."""
    _check_cron(request)
    from app.services.partner_network import run_partner_network
    return run_partner_network(db)


@router.post("/run-audit-anchor")
def run_audit_anchor_endpoint(request: Request, db: Session = Depends(get_db)):
    """Ancre la tête du journal d'audit : dernière entrée (id + hash) et nombre d'entrées
    de chaque chaîne, réunis en un engagement SHA-256 horodaté par une autorité RFC 3161,
    déposé sous anchors/AAAA-MM-JJ.json (+ email si ANCHOR_EMAIL). Rend détectable la
    suppression des DERNIÈRES entrées. Ne lève jamais : une autorité injoignable donne un
    ancrage sans jeton, avec la raison. À cron-er quotidiennement."""
    _check_cron(request)
    from app.services.audit_anchor import run_anchor
    return run_anchor(db)


# ── Réseau de partenaires : validation de l'identité des profils (décision fondateur) ────
# La vérification SIRENE prouve que l'entreprise existe et est active, pas que le compte la
# représente. Une demande de publication arrive ici ; un administrateur Adjugo (is_admin)
# rapproche le compte (nom, email) de l'identité SIRENE, puis valide (le profil devient
# visible) ou refuse avec un motif (affiché à l'entreprise). Un conflit de SIREN (un autre
# profil publié ou en attente pour la même entreprise) n'est visible QUE d'ici.
import re as _re
from typing import Optional as _Optional

from pydantic import BaseModel as _BaseModel


class ReseauValiderIn(_BaseModel):
    remplacer: bool = False      # retirer l'autre profil publié pour le même SIREN


class ReseauRefuserIn(_BaseModel):
    motif: str = ""


_MOTIF_CTRL = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _require_platform_admin(user: User) -> None:
    from app.services.demo_search import is_demo
    if not getattr(user, "is_admin", False) or is_demo(user):
        raise HTTPException(403, "Réservé à l'administrateur")


def _pending_profile(db: Session, profile_id: str):
    from app.models import PartnerProfile
    from app.services import partner_network as pn
    pid = str(profile_id or "").strip()
    if not _re.fullmatch(r"[0-9a-f]{32}", pid):
        raise HTTPException(404, "Demande introuvable.")
    p = db.query(PartnerProfile).filter(PartnerProfile.public_id == pid).first()
    if not p:
        raise HTTPException(404, "Demande introuvable.")
    if (p.validation_status or "") != pn.VALIDATION_PENDING:
        raise HTTPException(409, {"code": "deja_traitee",
                                  "message": "Cette demande n'est plus en attente (déjà traitée, annulée, "
                                             "ou SIRET modifié par l'entreprise)."})
    return p


@router.get("/mesures/redaction")
def mesures_redaction(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Décision 11 de l'étude « rédaction » : part des dossiers importés dont le règlement impose
    son propre fichier de réponse (on passe au remplissage du fichier de l'acheteur dès qu'un
    dossier sur cinq le fait). Agrégat seulement, réservé à l'administrateur de la plateforme."""
    _require_platform_admin(current_user)
    from app.services.atelier import mesure_fichier_impose
    return mesure_fichier_impose(db)


@router.get("/reseau/validations")
@limiter.limit("120/hour")
def reseau_validations(request: Request, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Demandes de publication en attente (les plus anciennes d'abord), avec l'identité
    SIRENE, le nom et l'email du compte, et les conflits de SIREN."""
    _require_platform_admin(current_user)
    from app.services import partner_network as pn
    return {"en_attente": pn.validation_queue(db),
            "explication": ("Vérifiez que le compte représente bien l'entreprise : nom et adresse email du compte "
                            "rapprochés de l'identité SIRENE (domaine de l'email, nom du dirigeant, au besoin un "
                            "appel au numéro public de l'entreprise). Valider rend la fiche visible ; refuser "
                            "affiche votre motif à l'entreprise.")}


@router.post("/reseau/validations/{profile_id}/valider")
@limiter.limit("120/hour")
def reseau_valider(request: Request, profile_id: str, body: _Optional[ReseauValiderIn] = None,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_platform_admin(current_user)
    from app.services import audit
    from app.services import partner_network as pn
    p = _pending_profile(db, profile_id)
    vs = p.verified_sirene if isinstance(p.verified_sirene, dict) else {}
    if not p.siren or vs.get("etat") != "actif":
        raise HTTPException(409, {"code": "verification_requise",
                                  "message": "L'entreprise n'est pas (ou plus) vérifiée active dans SIRENE : "
                                             "refusez la demande avec un motif, ou attendez une nouvelle vérification."})
    conflits = [o for o in pn.siren_conflicts(db, p) if o.visible]
    if conflits and not (body and body.remplacer):
        raise HTTPException(409, {"code": "conflit_siren",
                                  "message": "Un autre profil est déjà publié pour ce SIREN. Validez avec « Remplacer » "
                                             "pour le retirer du réseau, ou refusez cette demande.",
                                  "conflits": [{"profile_id": o.public_id, "name": o.name or ""} for o in conflits]})
    now = pn.utcnow_naive()
    retires = []
    for o in conflits:
        o.visible = False
        o.validation_status = pn.VALIDATION_REFUSED
        o.validation_siren = ""
        o.validated_at = now
        o.validated_by = current_user.id
        o.validation_motif = ("Fiche retirée : après vérification, Adjugo a attribué cette entreprise à un autre "
                              "compte. Contactez-nous si c'est une erreur.")
        retires.append((o.id, o.user_id))
    db.flush()          # retirer d'abord l'autre fiche (index unique « un profil publié par SIREN »)
    p.validation_status = pn.VALIDATION_OK
    p.validation_siren = p.siren
    p.validated_at = now
    p.validated_by = current_user.id
    p.validation_motif = ""
    if not pn.publish_validated(db, p, now):
        raise HTTPException(409, {"code": "conflit_siren",
                                  "message": "Un autre profil vient d'être publié pour ce SIREN : rechargez la liste."})
    db.refresh(p)
    for oid, ouid in retires:
        audit.record(db, action="network.profile_unpublished", owner_id=ouid, actor="adjugo", actor_kind="system",
                     target_type="partner_profile", target_id=oid,
                     detail="retiré par Adjugo : entreprise attribuée à un autre compte après vérification")
    audit.record(db, action="network.profile_validated", owner_id=p.user_id, actor="adjugo", actor_kind="system",
                 target_type="partner_profile", target_id=p.id,
                 detail="identité validée par Adjugo : profil publié")
    return {"ok": True, "message": "Profil validé : il est maintenant visible dans le réseau.",
            "profile_id": p.public_id, "retires": len(retires)}


@router.post("/reseau/validations/{profile_id}/refuser")
@limiter.limit("120/hour")
def reseau_refuser(request: Request, profile_id: str, body: ReseauRefuserIn,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_platform_admin(current_user)
    from app.services import audit
    from app.services import partner_network as pn
    motif = _MOTIF_CTRL.sub("", body.motif or "").strip()
    if len(motif) < 5:
        raise HTTPException(422, "Indiquez le motif du refus (il sera affiché à l'entreprise).")
    if len(motif) > 300:
        raise HTTPException(422, "Motif trop long : 300 caractères au plus.")
    p = _pending_profile(db, profile_id)
    p.visible = False
    p.validation_status = pn.VALIDATION_REFUSED
    p.validation_siren = ""
    p.validated_at = pn.utcnow_naive()
    p.validated_by = current_user.id
    p.validation_motif = motif
    db.commit()
    audit.record(db, action="network.profile_refused", owner_id=p.user_id, actor="adjugo", actor_kind="system",
                 target_type="partner_profile", target_id=p.id, detail="publication refusée par Adjugo")
    return {"ok": True, "message": "Demande refusée : l'entreprise voit votre motif sur son profil.",
            "profile_id": p.public_id}


# ── IA : diagnostic du routage et surveillance de la qualité (chantier R) ─────────────────────
# Réservé à l'administrateur de la plateforme. JAMAIS de clé dans les réponses : seulement le nom de
# la variable lue (« MISTRAL_API_KEY_ADJUGO », « ANTHROPIC_API_KEY ») et si elle est présente.

@router.get("/ia/diagnostic")
@limiter.limit("60/hour")
def ia_diagnostic(request: Request, verifier: bool = True, current_user: User = Depends(get_current_user)):
    """Quels fournisseurs sont configurés, quelle tâche part où (et maintenant, vu les clés et les
    disjoncteurs), si Mistral Large 4 est servi sur le point d'accès UE (models.list, vérifié en direct
    si `verifier`), le dernier état des secours, et ce qu'il reste à faire (messages)."""
    _require_platform_admin(current_user)
    from app.services import llm
    return llm.diagnostic(verifier=verifier)


@router.get("/ia/qualite")
@limiter.limit("120/hour")
def ia_qualite(request: Request, current_user: User = Depends(get_current_user)):
    """Qualité de l'IA par fournisseur et par tâche depuis le démarrage : JSON invalides, réponses
    coupées, refus, citations rejetées, abstentions, bascules de secours, délais, alertes."""
    _require_platform_admin(current_user)
    from app.services import llm_qualite
    return llm_qualite.instantane()


@router.get("/analyse-partagee")
@limiter.limit("120/hour")
def analyse_partagee_mesure(request: Request, current_user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Analyse partagée (interne, jamais montré aux clients), réservé à l'administrateur de la
    plateforme : dossiers et avis analysés, contenus distincts, doublons entre organisations (contenu
    normalisé, et clé exacte de l'extraction), extractions resservies et coût d'IA évité. Agrégats
    seulement : aucune organisation, aucun dossier, aucune empreinte n'est listé."""
    _require_platform_admin(current_user)
    from app.services.analyse_partagee import mesure
    return mesure(db)


@router.get("/usage-ia")
@limiter.limit("120/hour")
def usage_ia(request: Request, periode: str = "", current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Coût réel de l'IA (interne, jamais montré aux clients), réservé à l'administrateur de la
    plateforme : budget consommé par chaque essai gratuit en cours (avec ses analyses sur 30), coût du
    mois des organisations payantes et leurs alertes (seuil PAID_AI_ALERT_RATIO × prix du forfait,
    jamais de blocage), coût de la plateforme (appels mutualisés) et du côté acheteur."""
    _require_platform_admin(current_user)
    p = (periode or "").strip()
    if p and not _re.fullmatch(r"\d{4}-\d{2}", p):
        raise HTTPException(422, "Période attendue : AAAA-MM.")
    from app.services.budget_ia import releve_admin
    return releve_admin(db, periode=p or None)
