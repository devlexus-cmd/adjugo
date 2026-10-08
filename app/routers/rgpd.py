"""
RGPD — droits de l'utilisateur sur ses données (art. 15/17/20 RGPD) :
  • GET  /api/rgpd/export          → portabilité : toutes ses données en JSON.
  • POST /api/rgpd/delete-account  → effacement : suppression du compte et des données.

L'effacement est déclenché par l'utilisateur LUI-MÊME, sur SES propres données, après
confirmation de son mot de passe. Action irréversible.
"""
import json
import logging
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, verify_password
from app.core.ratelimit import limiter
from app.models import User

router = APIRouter(prefix="/api/rgpd", tags=["RGPD — mes données"])
logger = logging.getLogger("adjugo")


def _ser(obj, cols) -> dict:
    out = {}
    for c in cols:
        v = getattr(obj, c, None)
        out[c] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


@router.get("/export")
@limiter.limit("6/hour")
def export_my_data(request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Portabilité (art. 20) : un export JSON téléchargeable de toutes les données du compte."""
    from app.models import (Company, MatchingCriteria, Project, Contact, Document,
                            Invoice, Signal, SavedSearch)
    uid = current_user.id
    data = {
        "export_genere_le": datetime.utcnow().isoformat() + "Z",
        "compte": _ser(current_user, ["id", "email", "full_name", "plan", "org_id",
                                      "org_role", "created_at"]),
    }

    def dump(model, cols, label):
        try:
            rows = db.query(model).filter(model.user_id == uid).all()
            data[label] = [_ser(r, cols) for r in rows]
        except Exception:
            data[label] = []

    comp = db.query(Company).filter(Company.user_id == uid).first()
    data["profil_entreprise"] = _ser(comp, ["name", "siret", "code_ape", "forme_juridique",
        "representant_legal", "address", "city", "postal_code", "tva_intracom", "email",
        "phone", "ca_n1", "ca_n2", "ca_n3", "effectif", "qualifications", "references"]) if comp else None
    crit = db.query(MatchingCriteria).filter(MatchingCriteria.user_id == uid).first()
    data["criteres"] = _ser(crit, ["specialites", "departements", "budget_min", "budget_max"]) if crit else None
    dump(Project, ["id", "name", "client", "budget", "status", "deadline", "match_score",
                   "go_decision", "created_at"], "appels_offres")
    dump(Contact, ["id", "name", "email", "phone", "organization", "created_at"], "contacts")
    dump(Document, ["id", "name", "category", "file_size", "expiration_date", "created_at"], "documents_coffre_fort")
    dump(Invoice, ["id", "type", "client_name", "total_ttc", "created_at"], "factures")
    dump(Signal, ["id", "intitule", "collectivite", "pertinence", "created_at"], "signaux_veille")
    dump(SavedSearch, ["id", "name", "query", "frequency", "created_at"], "alertes")
    # Simulations « Répondre à plusieurs ? » : portées par owner_id (= data_owner_id), pas user_id.
    try:
        from app.models import GroupementSimulation
        rows = db.query(GroupementSimulation).filter(GroupementSimulation.owner_id == uid).all()
        data["simulations_groupement"] = [_ser(r, ["id", "project_id", "score_seul", "score_groupement",
                                                   "decision", "created_at"]) for r in rows]
    except Exception:
        data["simulations_groupement"] = []
    # Conventions de groupement (tenant = owner_id) et accords que CE compte a enregistrés.
    try:
        from app.models import GroupementConvention, GroupementSignature
        rows = db.query(GroupementConvention).filter(GroupementConvention.owner_id == uid).all()
        data["conventions_groupement"] = [_ser(r, ["id", "project_id", "forme", "mandataire_solidaire", "status",
                                                   "version", "total_offre_ht", "content_hash", "frozen_at",
                                                   "created_at"]) for r in rows]
        rows = db.query(GroupementSignature).filter(GroupementSignature.user_id == uid).all()
        data["accords_convention"] = [_ser(r, ["convention_id", "project_id", "company_name", "signataire_nom",
                                               "signataire_qualite", "status", "identity_level", "signed_at"])
                                      for r in rows]
    except Exception:
        data["conventions_groupement"], data["accords_convention"] = [], []

    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return Response(content=payload, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="mes_donnees_adjugo.json"'})


class DeleteIn(BaseModel):
    password: str
    confirm: str = ""   # doit valoir "SUPPRIMER"


@router.post("/delete-account")
@limiter.limit("3/hour")
def delete_account(request: Request, data: DeleteIn,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Effacement (art. 17) : supprime le compte et ses données. Irréversible.
    Confirmé par le mot de passe + le mot « SUPPRIMER ». Suppression ORDONNÉE (enfants
    avant parents) pour respecter les clés étrangères en une seule transaction."""
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "Mot de passe incorrect")
    if (data.confirm or "").strip().upper() != "SUPPRIMER":
        raise HTTPException(400, "Tapez SUPPRIMER pour confirmer")
    from app.models import Organization
    uid = current_user.id

    # On résout l'organisation par l'APPARTENANCE (org_id), pas seulement la propriété : un
    # MEMBRE a aussi un org_id. Sinon, pour un membre, `org` valait None et on enchaînait le
    # hard-delete de ses Project/Contact/Document/… — or ce sont des données d'ENTREPRISE
    # partagées (un commercial partait avec les AO de toute la boîte par la porte RGPD).
    org = (db.query(Organization).filter(Organization.id == current_user.org_id).first()
           if current_user.org_id else None)
    is_owner = bool(org and org.owner_id == uid)

    if is_owner:
        others = db.query(User).filter(User.org_id == org.id, User.id != uid).count()
        if others:
            raise HTTPException(409, "Transférez d'abord la propriété de l'organisation à un "
                                     "autre membre (ou retirez les membres) avant de supprimer votre compte.")

    # MEMBRE d'une organisation tierce : on RÉASSIGNE ses dossiers au propriétaire (comme le
    # retrait de membre) — l'effacement RGPD de la personne physique n'impose pas de détruire
    # les registres de la personne morale — puis on n'efface QUE ses données strictement perso.
    if org and not is_owner:
        try:
            _erase_member(db, uid, org.owner_id)
            db.commit()
        except Exception:
            db.rollback()
            # Détail technique (SQL, tables, paramètres) au journal serveur UNIQUEMENT.
            logger.exception("RGPD : effacement du compte membre %s en échec", uid)
            raise HTTPException(500, _DELETE_FAILED)
        return {"ok": True, "message": "Compte supprimé ; les données de l'entreprise ont été conservées."}

    # Propriétaire SOLO (ou compte sans organisation) : ses données sont strictement les
    # siennes → effacement complet et ordonné (enfants avant parents).
    try:
        file_keys = _erase_solo(db, uid, org.id if org else None)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("RGPD : effacement du compte %s en échec", uid)
        raise HTTPException(500, _DELETE_FAILED)
    # Fichiers du stockage (Kbis, attestations, DCE, pièces des partenaires…) : supprimés
    # APRÈS le commit — jamais avant (un rollback laisserait des lignes sans fichier).
    _purge_files(db, file_keys)
    return {"ok": True, "message": "Compte et données supprimés."}


# ─── Effacement : implémentation ──────────────────────────────────────────────────────
#
# Ordre = ENFANTS → PARENTS, pour respecter les clés étrangères appliquées par Postgres en
# production (sans ON DELETE) : une seule ligne oubliée faisait échouer TOUT l'effacement
# (500) — le droit à l'effacement devenait inopérant. Graphe des FK (app.models) :
#   contribution_pieces → project_contributions → project_invites → projects / users
#   project_cotraitants → projects, cotraitants ; groupement_simulations → projects, users
#   audit_logs, documents, invoices, generated_docs → projects ; documents.parent_id → documents
#   knowledge_chunks → knowledge_docs ; co_members → co_spaces ; jobs, feedback → users
#   users.org_id ↔ organizations.owner_id (cycle)

_DELETE_FAILED = ("La suppression n'a pas pu aboutir. Réessayez dans quelques minutes "
                  "ou contactez le support : rien n'a été effacé.")


def _models():
    import app.models as M
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant   # hors app.models
    return M, Cotraitant, ProjectCotraitant


def _ids(db, col, *conds) -> list:
    from sqlalchemy import or_
    conds = [c for c in conds if c is not None]
    if not conds:
        return []
    return [r[0] for r in db.query(col).filter(or_(*conds)).all()]


def _del(db, model, *conds) -> None:
    """DELETE … WHERE c1 OR c2 … (conditions None ignorées ; rien si aucune condition)."""
    from sqlalchemy import or_
    conds = [c for c in conds if c is not None]
    if conds:
        db.query(model).filter(or_(*conds)).delete(synchronize_session=False)


def _release_claims(db, uid: int) -> None:
    """Invitations RÉCLAMÉES par ce compte chez d'autres mandataires : on libère le lien
    (sinon il devenait définitivement non réclamable — 409 — et la FK bloquait l'effacement)."""
    from app.models import GroupementSignature, ProjectInvite
    db.query(ProjectInvite).filter(ProjectInvite.accepted_by_user_id == uid).update(
        {ProjectInvite.accepted_by_user_id: None}, synchronize_session=False)
    # Accords de convention enregistrés depuis ce compte : la preuve (date, empreinte, niveau
    # d'identité) reste au registre du groupement, mais le lien vers le compte effacé tombe.
    db.query(GroupementSignature).filter(GroupementSignature.user_id == uid).update(
        {GroupementSignature.user_id: None}, synchronize_session=False)


def _erase_personal_rows(db, uid: int) -> None:
    """Données strictement PERSONNELLES (jamais des registres d'entreprise) : supprimées
    dans les deux parcours (membre comme propriétaire solo)."""
    M, _, _ = _models()
    _del(db, M.Feedback, M.Feedback.user_id == uid)            # email + message libre
    cospace_ids = _ids(db, M.CoSpace.id, M.CoSpace.owner_id == uid)
    _del(db, M.CoMember, M.CoMember.user_id == uid,
         M.CoMember.space_id.in_(cospace_ids) if cospace_ids else None)
    _del(db, M.CoSpace, M.CoSpace.owner_id == uid)
    from app.routers.criteria_v2 import MatchingCriteriaExt          # hors app.models
    for model in (M.SavedSearch, M.Company, M.MatchingCriteria, MatchingCriteriaExt):
        _del(db, model, model.user_id == uid)


def _erase_member(db, uid: int, owner_id: int) -> None:
    """MEMBRE d'une organisation : ses dossiers sont des registres de la personne morale →
    réassignés au propriétaire (comme le retrait de membre) ; seules ses données
    personnelles sont effacées."""
    from app.routers.org import _reassign_member_data
    _reassign_member_data(db, uid, owner_id)
    # Filet : quoi que fasse _reassign_member_data (tolérant aux absents), aucune ligne métier
    # ne doit rester pointée sur le compte supprimé (sinon FK → échec de l'effacement).
    M, Cotraitant, _ = _models()
    for model in (M.Job, M.Project, M.Contact, M.Document, M.Invoice, M.KnowledgeDoc,
                  M.KnowledgeChunk, M.Signal, Cotraitant):
        db.query(model).filter(model.user_id == uid).update(
            {model.user_id: owner_id}, synchronize_session=False)
    # Co-traitance et simulations portées par ce membre → suivent le propriétaire
    # (registres du tenant : on ne les détruit pas, on ne les laisse pas orphelins).
    for model in (M.ProjectInvite, M.ProjectContribution, M.ContributionPiece,
                  M.GroupementSimulation, M.GroupementConvention, M.GroupementSignature):
        db.query(model).filter(model.owner_id == uid).update(
            {model.owner_id: owner_id}, synchronize_session=False)
    # JOURNAL D'AUDIT : JAMAIS réécrit. owner_id entre dans le hash de chaque entrée et la
    # chaîne est tenue par owner_id → déplacer une entrée chaînée cassait la chaîne de
    # l'entreprise (fausse alerte de falsification). Seules les entrées historiques NON
    # chaînées situées en queue des deux chaînes suivent le propriétaire (sans effet sur
    # aucune vérification) ; le reste garde son owner_id et la ligne users est anonymisée.
    _move_unchained_tail(db, uid, owner_id)
    _release_claims(db, uid)
    _erase_personal_rows(db, uid)
    _drop_or_anonymize_user(db, uid)


def _move_unchained_tail(db, uid: int, owner_id: int) -> None:
    """Entrées d'audit NON chaînées (antérieures au chaînage) de `uid` rattachées au
    propriétaire, uniquement si elles sont plus récentes que TOUTE entrée de `owner_id` et
    que toute entrée chaînée de `uid` : ni l'une ni l'autre chaîne n'en est affectée."""
    from sqlalchemy import func, or_
    from app.models import AuditLog
    top_owner = db.query(func.max(AuditLog.id)).filter(AuditLog.owner_id == owner_id).scalar() or 0
    top_chained = db.query(func.max(AuditLog.id)).filter(
        AuditLog.owner_id == uid, AuditLog.entry_hash.isnot(None), AuditLog.entry_hash != "").scalar() or 0
    floor = max(top_owner, top_chained)
    db.query(AuditLog).filter(
        AuditLog.owner_id == uid, AuditLog.id > floor,
        or_(AuditLog.entry_hash.is_(None), AuditLog.entry_hash == ""),
    ).update({AuditLog.owner_id: owner_id}, synchronize_session=False)


def _drop_or_anonymize_user(db, uid: int) -> None:
    """Supprime la ligne users… sauf si le journal d'audit (chaîné, donc intouchable) la
    référence encore : on l'ANONYMISE alors (plus aucune donnée personnelle, connexion
    impossible, sessions coupées) — conforme au droit à l'effacement, et la preuve
    d'intégrité de l'entreprise reste vérifiable."""
    import secrets
    from app.core.security import hash_password
    import app.models as M
    # Toute ligne qui pointe encore vers le compte (journal chaîné, ou registre d'entreprise
    # qu'on n'a pas pu rattacher) empêcherait la suppression (clé étrangère) : on anonymise.
    still_referenced = any(
        db.query(model.id).filter(model.owner_id == uid).first() is not None
        for model in (M.AuditLog, M.ProjectInvite, M.ProjectContribution, M.ContributionPiece,
                      M.GroupementSimulation, M.GroupementConvention)
    ) or db.query(M.Project.id).filter(M.Project.user_id == uid).first() is not None   # pierres tombales
    if not still_referenced:
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        return
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return
    u.email = f"deleted-{uid}@invalid"
    u.hashed_password = hash_password(secrets.token_urlsafe(32))
    u.full_name = ""
    u.is_active = False
    u.is_admin = False
    u.email_verified = False
    u.token_version = (u.token_version or 0) + 1
    u.org_id = None
    u.org_role = "membre"
    u.stripe_customer_id = None
    u.overage_enabled = False
    u.amont_alerts_enabled = False
    u.reset_token_hash = ""
    u.reset_expires_at = None
    db.flush()


def _erase_solo(db, uid: int, org_id) -> list:
    """Propriétaire SOLO : effacement complet. Retourne les clés de fichiers du stockage à
    purger APRÈS commit."""
    M, Cotraitant, ProjectCotraitant = _models()
    pids = _ids(db, M.Project.id, M.Project.user_id == uid)          # corbeille incluse
    in_p = (lambda col: col.in_(pids) if pids else None)

    # Fichiers à purger (collectés AVANT d'effacer les lignes qui les référencent).
    keys = []
    keys += _ids(db, M.Document.file_key, M.Document.user_id == uid, in_p(M.Document.project_id))
    keys += _ids(db, M.ContributionPiece.file_key, M.ContributionPiece.owner_id == uid,
                 in_p(M.ContributionPiece.project_id))
    keys += _ids(db, M.GeneratedDoc.file_key, in_p(M.GeneratedDoc.project_id))
    keys += _ids(db, M.Project.dce_file_key, M.Project.user_id == uid)

    _release_claims(db, uid)
    # 0) Registres portés par uid sur des marchés qui NE SONT PLUS les siens (ex-fondateur
    #    ayant transféré la propriété, données anciennes) : ils appartiennent à l'entreprise
    #    du marché → rattachés à son propriétaire actuel, jamais effacés.
    _hand_over_foreign_rows(db, uid, pids)
    # 0 bis) conventions de groupement : accords (FK vers invitations / liaisons) puis conventions.
    _ct_ids0 = _ids(db, Cotraitant.id, Cotraitant.user_id == uid)
    _link_ids0 = _ids(db, ProjectCotraitant.id, in_p(ProjectCotraitant.project_id),
                      ProjectCotraitant.cotraitant_id.in_(_ct_ids0) if _ct_ids0 else None)
    _del(db, M.GroupementSignature, in_p(M.GroupementSignature.project_id),
         M.GroupementSignature.cotraitant_link_id.in_(_link_ids0) if _link_ids0 else None)
    _del(db, M.GroupementConvention, in_p(M.GroupementConvention.project_id))
    # 1) co-traitance (pièces → contributions → liaisons → journal → invitations)
    _del(db, M.ContributionPiece, in_p(M.ContributionPiece.project_id))
    _del(db, M.ProjectContribution, in_p(M.ProjectContribution.project_id))
    ct_ids = _ids(db, Cotraitant.id, Cotraitant.user_id == uid)
    _del(db, ProjectCotraitant, in_p(ProjectCotraitant.project_id),
         ProjectCotraitant.cotraitant_id.in_(ct_ids) if ct_ids else None)
    # Marchés du compte sur lesquels une AUTRE entreprise a des entrées chaînées (transfert
    # de propriété, ex-membre…) : les effacer casserait la preuve d'intégrité de cette
    # entreprise. Leur contenu part quand même ; la ligne reste en pierre tombale vide.
    shared = set()
    if pids:
        shared = {r[0] for r in db.query(M.AuditLog.project_id).filter(
            M.AuditLog.project_id.in_(pids), M.AuditLog.owner_id != uid).distinct().all()}
    _erase_own_audit(db, uid, pids, keep_pids=shared)
    _del(db, M.ProjectInvite, in_p(M.ProjectInvite.project_id))
    # 2) enfants directs des projets
    _del(db, M.GroupementSimulation, in_p(M.GroupementSimulation.project_id))
    _del(db, M.GeneratedDoc, in_p(M.GeneratedDoc.project_id))
    _del(db, M.Invoice, M.Invoice.user_id == uid, in_p(M.Invoice.project_id))
    # Documents : toutes versions d'un coup (parent_id auto-référent, vérifié en fin d'instruction).
    _del(db, M.Document, M.Document.user_id == uid, in_p(M.Document.project_id))
    # 3) savoir-faire, travaux IA, données personnelles
    kd_ids = _ids(db, M.KnowledgeDoc.id, M.KnowledgeDoc.user_id == uid)
    _del(db, M.KnowledgeChunk, M.KnowledgeChunk.user_id == uid,
         M.KnowledgeChunk.doc_id.in_(kd_ids) if kd_ids else None)
    _del(db, M.KnowledgeDoc, M.KnowledgeDoc.user_id == uid)
    _del(db, M.Job, M.Job.user_id == uid)                      # mémoires/questionnaires générés
    _erase_personal_rows(db, uid)
    # 4) projets, puis les données métier restantes
    q = db.query(M.Project).filter(M.Project.user_id == uid)
    if shared:
        q = q.filter(~M.Project.id.in_(shared))
        _tombstone_projects(db, list(shared))
    q.delete(synchronize_session=False)
    for model in (M.Contact, Cotraitant, M.Signal):
        _del(db, model, model.user_id == uid)
    # 5) cycle users ↔ organizations : on détache l'utilisateur, on supprime son organisation
    #    perso (owner_id → users), puis l'utilisateur — valide quelles que soient les FK posées.
    db.query(User).filter(User.id == uid).update({User.org_id: None}, synchronize_session=False)
    if org_id:
        db.query(M.Organization).filter(M.Organization.id == org_id).delete(synchronize_session=False)
    db.query(M.Organization).filter(M.Organization.owner_id == uid).update(
        {M.Organization.owner_id: None}, synchronize_session=False)
    _drop_or_anonymize_user(db, uid)
    return [k for k in dict.fromkeys(keys) if k]


def _hand_over_foreign_rows(db, uid: int, pids: list) -> None:
    """Invitations, parts, pièces et simulations dont owner_id == uid mais posées sur un
    marché qui n'appartient plus à uid → réaffectées au propriétaire du tenant du marché."""
    M, _, _ = _models()
    from app.routers.invites import tenant_owner_id
    owners = {}
    for model in (M.ContributionPiece, M.ProjectContribution, M.ProjectInvite, M.GroupementSimulation,
                  M.GroupementConvention, M.GroupementSignature):
        q = db.query(model.project_id).filter(model.owner_id == uid)
        if pids:
            q = q.filter(~model.project_id.in_(pids))
        for (proj_id,) in q.distinct().all():
            if proj_id is None:
                continue
            if proj_id not in owners:
                proj = db.query(M.Project).filter(M.Project.id == proj_id).first()
                owners[proj_id] = tenant_owner_id(proj, db) if proj else None
            new_owner = owners[proj_id]
            if new_owner and new_owner != uid:
                db.query(model).filter(model.owner_id == uid, model.project_id == proj_id).update(
                    {model.owner_id: new_owner}, synchronize_session=False)


def _erase_own_audit(db, uid: int, pids: list, keep_pids=()) -> None:
    """Journal d'audit d'un compte solo. On n'efface QUE ses entrées personnelles (sur ses
    propres marchés, ou sans marché), et seulement en QUEUE de sa chaîne : tout ce qui
    précède la dernière entrée rattachée à une autre entreprise (marché d'autrui, ou
    période où il était propriétaire avant un transfert) est conservé intact — la chaîne
    reste vérifiable par cette entreprise. Les entrées sur ses propres marchés, supprimés
    ici, partent dans tous les cas (clé étrangère vers projects)."""
    from sqlalchemy import func, or_, false
    from app.models import AuditLog
    foreign = db.query(func.max(AuditLog.id)).filter(AuditLog.owner_id == uid, AuditLog.project_id.isnot(None))
    if pids:
        foreign = foreign.filter(~AuditLog.project_id.in_(pids))
    boundary = foreign.scalar() or 0
    # Ancien propriétaire d'une organisation : tout son journal antérieur au transfert est
    # celui de l'entreprise (y compris les entrées sans marché : équipe, rôles…).
    last_transfer = db.query(func.max(AuditLog.id)).filter(
        AuditLog.action == "team.ownership_transferred", AuditLog.actor == f"user:{uid}").scalar()
    if last_transfer:
        before = db.query(func.max(AuditLog.id)).filter(
            AuditLog.owner_id == uid, AuditLog.id < last_transfer).scalar() or 0
        boundary = max(boundary, before)
    conds = [(AuditLog.owner_id == uid) & (AuditLog.id > boundary)
             & (AuditLog.project_id.is_(None) | (AuditLog.project_id.in_(pids) if pids else false()))]
    # Marchés dont le journal porte AUSSI des entrées chaînées sous une autre entreprise
    # (`keep_pids`) : ces entrées-là ne sont jamais touchées, le marché reste en pierre tombale.
    gone = [p for p in (pids or []) if p not in set(keep_pids or ())]
    if gone:
        conds.append(AuditLog.project_id.in_(gone))
    db.query(AuditLog).filter(or_(*conds)).delete(synchronize_session=False)


def _purge_files(db, keys) -> int:
    """Supprime du stockage (R2/S3 ou disque) les fichiers dont plus AUCUNE ligne ne parle.
    Best-effort : un échec est journalisé (clé seulement) mais ne remonte jamais au client —
    la suppression en base est déjà validée."""
    keys = [k for k in dict.fromkeys(keys or []) if k]
    if not keys:
        return 0
    import app.models as M
    from app.services.storage import get_storage
    still = set()
    try:
        for col in (M.Document.file_key, M.ContributionPiece.file_key, M.GeneratedDoc.file_key,
                    M.Project.dce_file_key):
            still |= {r[0] for r in db.query(col).filter(col.in_(keys)).all()}
    except Exception:
        logger.exception("Purge stockage : vérification des références impossible")
        return 0
    storage, n = get_storage(), 0
    for k in keys:
        if k in still:
            continue   # encore référencé (ex. clé partagée) : on ne détruit pas le fichier d'autrui
        try:
            storage.delete(k)
            n += 1
        except Exception as e:
            logger.warning("Purge stockage : échec sur %s : %s", k, type(e).__name__)
    return n


TRASH_RETENTION_DAYS = 30


def purge_trash(db, older_than_days: int = TRASH_RETENTION_DAYS) -> dict:
    """Vide la corbeille du coffre-fort : documents supprimés depuis plus de N jours —
    ligne ET fichier, avec toutes leurs anciennes versions (chaîne parent_id). Appelé par
    le cron quotidien POST /api/admin/run-trash-purge (process unique, sans Redis)."""
    from datetime import timedelta, timezone
    from app.models import Document
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=int(older_than_days))
    try:
        roots = _ids(db, Document.id, (Document.deleted_at.isnot(None)) & (Document.deleted_at < cutoff))
        if not roots:
            res = {"purged_documents": 0, "deleted_files": 0}
            res.update(_purge_trashed_projects(db, cutoff))     # la corbeille des marchés aussi
            return res
        # Anciennes versions = enfants (parent_id → version plus récente), transitivement.
        ids, frontier = set(roots), set(roots)
        while frontier:
            rows = db.query(Document.id, Document.deleted_at).filter(
                Document.parent_id.in_(list(frontier))).all()
            # Une ancienne version restaurée entre-temps n'est JAMAIS effacée avec la tête :
            # elle est détachée et redevient un document courant.
            live = {r[0] for r in rows if r[1] is None} - ids
            if live:
                db.query(Document).filter(Document.id.in_(list(live))).update(
                    {Document.parent_id: None}, synchronize_session=False)
            children = {r[0] for r in rows if r[1] is not None} - ids
            ids |= children
            frontier = children
        ids = list(ids)
        keys = _ids(db, Document.file_key, Document.id.in_(ids))
        db.query(Document).filter(Document.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Purge de la corbeille en échec")
        return {"purged_documents": 0, "deleted_files": 0, "error": "purge interrompue"}
    res = {"purged_documents": len(ids), "deleted_files": _purge_files(db, keys)}
    res.update(_purge_trashed_projects(db, cutoff))
    return res


PURGED_MARKER = {"purged": True}


def _tombstone_projects(db, pids: list) -> None:
    """Vide une ligne projects sans la supprimer (le journal chaîné la référence) : plus aucun
    contenu, marquée purgée, à la corbeille (invisible des listes, restauration → 410)."""
    from app.models import Project, utcnow
    if not pids:
        return
    db.query(Project).filter(Project.id.in_(pids)).update({
        Project.name: "Marché supprimé", Project.client: None, Project.ai_summary: None,
        Project.ai_analysis: PURGED_MARKER, Project.estimate: None, Project.workflow: {},
        Project.source_url: None, Project.dce_file_key: None, Project.groupement_plan: None,
        Project.groupement_score: None, Project.match_score: None, Project.go_decision: None,
        Project.outcome_reason: None, Project.competitor_winner: None, Project.budget: 0,
    }, synchronize_session=False)
    db.query(Project).filter(Project.id.in_(pids), Project.deleted_at.is_(None)).update(
        {Project.deleted_at: utcnow()}, synchronize_session=False)


def _purge_trashed_projects(db, cutoff) -> dict:
    """Corbeille des MARCHÉS : au-delà de la rétention, le CONTENU d'un marché supprimé est
    effacé définitivement (dossier, analyses, pièces des partenaires, documents générés,
    invitations, simulations, fichiers du stockage). La ligne projects reste en « pierre
    tombale » vide : le journal d'audit chaîné référence project_id, et ce champ entre dans
    le hachage — supprimer ou réécrire ces entrées casserait la preuve d'intégrité.
    Les factures (pièces comptables) sont conservées, détachées du marché."""
    M, Cotraitant, ProjectCotraitant = _models()
    try:
        pids = [p for p, a in db.query(M.Project.id, M.Project.ai_analysis).filter(
            M.Project.deleted_at.isnot(None), M.Project.deleted_at < cutoff).all()
            if a != PURGED_MARKER]
        if not pids:
            return {"purged_projects": 0, "deleted_project_files": 0}
        keys = []
        keys += _ids(db, M.Document.file_key, M.Document.project_id.in_(pids))
        keys += _ids(db, M.ContributionPiece.file_key, M.ContributionPiece.project_id.in_(pids))
        keys += _ids(db, M.GeneratedDoc.file_key, M.GeneratedDoc.project_id.in_(pids))
        keys += _ids(db, M.Project.dce_file_key, M.Project.id.in_(pids))
        _del(db, M.GroupementSignature, M.GroupementSignature.project_id.in_(pids))
        _del(db, M.GroupementConvention, M.GroupementConvention.project_id.in_(pids))
        _del(db, M.ContributionPiece, M.ContributionPiece.project_id.in_(pids))
        _del(db, M.ProjectContribution, M.ProjectContribution.project_id.in_(pids))
        _del(db, ProjectCotraitant, ProjectCotraitant.project_id.in_(pids))
        _del(db, M.ProjectInvite, M.ProjectInvite.project_id.in_(pids))
        _del(db, M.GroupementSimulation, M.GroupementSimulation.project_id.in_(pids))
        _del(db, M.GeneratedDoc, M.GeneratedDoc.project_id.in_(pids))
        _del(db, M.Document, M.Document.project_id.in_(pids))
        db.query(M.Invoice).filter(M.Invoice.project_id.in_(pids)).update(
            {M.Invoice.project_id: None}, synchronize_session=False)
        _tombstone_projects(db, pids)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Purge des marchés à la corbeille en échec")
        return {"purged_projects": 0, "deleted_project_files": 0, "error": "purge des marchés interrompue"}
    return {"purged_projects": len(pids), "deleted_project_files": _purge_files(db, keys)}
