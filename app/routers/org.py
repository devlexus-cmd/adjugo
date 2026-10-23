"""
Espace équipe / organisation : voir les membres, inviter un collègue (qui partagera
projets, contacts et co-traitants), renommer l'organisation, retirer un membre.
"""
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, hash_password, create_access_token
from app.core.ratelimit import limiter
from app.core.org import ensure_org
from app.models import User, Organization
from app.services import audit

router = APIRouter(prefix="/api/org", tags=["Équipe / Organisation"])


def _plan_member_limit(db, org) -> int:
    owner = db.query(User).filter(User.id == org.owner_id).first()
    plan = (getattr(owner.plan, "value", None) or str(owner.plan or "starter")) if owner else "starter"
    return get_settings().PLAN_LIMITS.get(plan, {}).get("members", 2)


def _reassign_models():
    """Modèles métier dont les lignes (par user_id) restent à l'org au retrait d'un
    membre. Résolus paresseusement et tolérants aux absents (Cotraitant vit hors
    app.models)."""
    mods = []
    try:
        from app.models import (Project, Contact, Document, Invoice, KnowledgeDoc,
                                KnowledgeChunk, Signal, Job)
        # KnowledgeChunk DOIT suivre KnowledgeDoc sinon le RAG du membre parti devient
        # orphelin (l'index interroge KnowledgeChunk.user_id).
        # Job : les résultats IA (mémoires, questionnaires, war rooms) sont bâtis sur le
        # savoir-faire COMMUN de l'org → ils restent à l'org ; sinon l'ex-membre les relisait.
        mods += [Project, Contact, Document, Invoice, KnowledgeDoc, KnowledgeChunk, Signal, Job]
    except Exception:
        pass
    try:
        from app.routers.cotraitants import Cotraitant
        mods.append(Cotraitant)
    except Exception:
        pass
    return mods


def _reassign_member_data(db, from_user_id: int, to_user_id: int) -> int:
    """Réassigne au propriétaire les données métier créées par un membre qu'on retire,
    pour qu'elles RESTENT dans l'organisation. Ne touche pas au profil (Company) ni au
    quota du membre. Retourne le nombre de lignes réassignées."""
    total = 0
    for M in _reassign_models():
        if not hasattr(M, "user_id"):
            continue
        try:
            total += db.query(M).filter(M.user_id == from_user_id).update(
                {M.user_id: to_user_id}, synchronize_session=False)
        except Exception:
            pass
    db.flush()
    return total


class InviteIn(BaseModel):
    email: EmailStr
    full_name: Optional[str] = ""


class RenameIn(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None


def _org(user, db) -> Organization:
    oid = ensure_org(user, db)
    return db.query(Organization).filter(Organization.id == oid).first()


@router.get("/countries")
def adapted_countries(current_user: User = Depends(get_current_user)):
    """Pays pour lesquels Adjugo est pleinement adapté (donnée entreprise complète)."""
    from app.core.countries import COUNTRIES_FULL
    return [{"code": c["code"], "nom": c["nom"], "lang": c["lang"], "devise": c["devise"]}
            for c in COUNTRIES_FULL]


@router.get("/")
def get_org(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.countries import country_config
    org = _org(current_user, db)
    members = db.query(User).filter(User.org_id == org.id).order_by(User.created_at).all()
    cfg = country_config(org.country)
    return {
        "id": org.id, "name": org.name, "owner_id": org.owner_id,
        "is_owner": org.owner_id == current_user.id,
        "my_role": current_user.org_role or "membre",
        "can_invite": org.owner_id == current_user.id or (current_user.org_role or "") == "admin",
        "member_limit": _plan_member_limit(db, org),
        "country": cfg["code"], "country_nom": cfg["nom"],
        "lang": cfg["lang"], "devise": cfg["devise"],
        "members": [{
            "id": m.id, "full_name": m.full_name, "email": m.email,
            "role": m.org_role or "membre", "is_owner": m.id == org.owner_id,
            "is_me": m.id == current_user.id,
        } for m in members],
    }


@router.put("/")
@limiter.limit("60/hour")
def update_org(data: RenameIn, request: Request, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    from app.core.countries import is_supported, country_config
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut modifier l'organisation")
    if data.name:
        org.name = data.name.strip() or org.name
    if data.country:
        cc = data.country.strip().upper()
        if not is_supported(cc):
            raise HTTPException(400, "Pays non pris en charge pour l'adaptation complète")
        org.country = cc
    db.commit()
    cfg = country_config(org.country)
    return {"id": org.id, "name": org.name, "country": cfg["code"],
            "lang": cfg["lang"], "devise": cfg["devise"]}


@router.post("/invite", status_code=201)
@limiter.limit("30/hour")
def invite_member(data: InviteIn, request: Request, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Invite un collègue dans l'organisation. Crée son compte avec un mot de passe
    provisoire (retourné une seule fois) à lui transmettre, et envoie un email si SMTP."""
    # Défense en profondeur (en plus du garde central) : la démo n'envoie JAMAIS d'email.
    from app.services.demo_search import is_demo
    if is_demo(current_user):
        raise HTTPException(403, "La démo est en lecture guidée : commencez votre essai gratuit de 30 jours "
                                 "pour inviter un collègue.")
    org = _org(current_user, db)
    if org.owner_id != current_user.id and (current_user.org_role or "") != "admin":
        raise HTTPException(403, "Seul un administrateur peut inviter des membres")

    # Verrou de ligne sur l'org : sérialise les invitations concurrentes pour que le
    # contrôle de limite (count) ne soit pas contournable par deux POST simultanés.
    db.query(Organization).filter(Organization.id == org.id).with_for_update().first()
    # (Testé AVANT la limite d'offre : message exact même quand l'équipe est pleine.)
    # Forme canonique (minuscules, partie locale incluse) comme à l'inscription/connexion, et
    # doublon testé INSENSIBLE à la casse : sinon « TARGET@x.fr » créait un 2e compte pour une
    # adresse déjà inscrite (« target@x.fr ») → connexion/réinitialisation imprévisibles.
    email_norm = str(data.email).strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if existing:
        if existing.org_id == org.id:
            raise HTTPException(400, "Cette personne fait déjà partie de l'organisation")
        raise HTTPException(400, "Cet email est déjà associé à un autre compte")

    # Limite de membres selon l'offre du propriétaire (appliquée, plus seulement affichée).
    limit = _plan_member_limit(db, org)
    n_members = db.query(User).filter(User.org_id == org.id).count()
    if n_members >= limit:
        raise HTTPException(402, f"Votre offre est limitée à {limit} membre(s). "
                                 f"Passez à une offre supérieure pour agrandir l'équipe.")

    temp_password = secrets.token_urlsafe(9)
    from datetime import datetime, timedelta, timezone
    from app.core.quota import TRIAL_DAYS
    from app.routers.auth import clean_full_name
    member = User(
        email=email_norm,
        hashed_password=hash_password(temp_password),
        # Nom nettoyé et borné comme à l'inscription (clean_full_name) : il s'affiche dans l'équipe et entre dans des
        # courriels et des noms d'organisation. Avant : caractères de contrôle gardés, et au-delà de 255 caractères
        # (largeur de la colonne) l'invitation échouait sur PostgreSQL (500).
        full_name=clean_full_name(data.full_name) or email_norm.split("@")[0],
        org_id=org.id, org_role="membre",
        # Tout NOUVEAU compte a une date de fin d'essai, quel que soit le mode de création (app/core/quota.py ; CGV
        # 3.5 ; comme l'inscription par mot de passe ou par Google). Tant qu'il est membre, seul le forfait du
        # propriétaire compte (quota._billing_user) ; retiré de l'organisation, il n'est pas un compte « historique »
        # sans fin d'essai (5 analyses gratuites par mois sans fin, IA jamais en pause, aucune limite d'usage).
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    audit.record(db, action="team.member_invited", owner_id=org.owner_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="user", target_id=member.id, detail=member.email[:255],
                 ip=audit.client_ip(request))

    # Email best-effort (no-op si SMTP non configuré). On signale au front si l'email
    # n'est pas parti → le propriétaire sait qu'il doit transmettre le mot de passe.
    emailed = False
    try:
        from app.services.email import send_email
        # Un email part au nom d'Adjugo vers un tiers : l'expéditeur doit avoir prouvé sa
        # propre adresse. Sinon, le mot de passe provisoire est affiché à transmettre.
        if not getattr(current_user, "email_verified", False):
            raise RuntimeError("expéditeur non confirmé")
        # Un compte peut n'avoir aucun nom (champ facultatif à l'inscription, compte Google sans nom) : la phrase garde
        # un sujet (contrôle des bugs, deuxième passe : « Bonjour,  vous invite à rejoindre… »).
        qui = (current_user.full_name or "").strip() or "Un collègue"
        emailed = send_email(member.email, f"Invitation à rejoindre {org.name} sur Adjugo",
                   f"Bonjour,\n\n{qui} vous invite à rejoindre l'espace "
                   f"« {org.name} » sur Adjugo.\n\nIdentifiant : {member.email}\n"
                   f"Mot de passe provisoire : {temp_password}\n\nConnectez-vous puis "
                   f"changez votre mot de passe (menu Réglages, puis Mon compte).\n\n— Adjugo")
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("Email d'invitation non envoyé à %s : %s", member.email, e)

    return {"id": member.id, "email": member.email, "full_name": member.full_name,
            "temp_password": temp_password, "emailed": emailed}


@router.delete("/members/{member_id}")
@limiter.limit("30/hour")
def remove_member(member_id: int, request: Request, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Retire un membre de l'organisation (lui recrée un espace personnel → il perd
    immédiatement l'accès aux données de l'organisation)."""
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut retirer un membre")
    if member_id == current_user.id:
        raise HTTPException(400, "Vous ne pouvez pas vous retirer vous-même")
    member = db.query(User).filter(User.id == member_id, User.org_id == org.id).first()
    if not member:
        raise HTTPException(404, "Membre introuvable")
    # Les dossiers que le membre a créés appartiennent à l'ENTREPRISE : on les réassigne
    # au propriétaire avant de sortir le membre (sinon l'org perdait l'accès — un
    # commercial partait avec ses AO). On NE déplace PAS son profil entreprise (Company).
    reassigned = _reassign_member_data(db, member.id, org.owner_id)
    # Nouvel espace personnel vierge pour l'ancien membre.
    new_org = Organization(name=f"Équipe {member.full_name}", owner_id=member.id)
    db.add(new_org)
    db.flush()
    member.org_id = new_org.id
    member.org_role = "admin"
    member.token_version = (member.token_version or 0) + 1   # coupe ses sessions en cours
    db.commit()
    audit.record(db, action="team.member_removed", owner_id=org.owner_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="user", target_id=member.id,
                 detail=f"{member.email} — {reassigned} élément(s) réassigné(s)"[:255],
                 ip=audit.client_ip(request))
    return {"ok": True, "reassigned": reassigned}


class RoleIn(BaseModel):
    role: str  # admin | membre


@router.put("/members/{member_id}/role")
@limiter.limit("60/hour")
def set_member_role(member_id: int, data: RoleIn, request: Request,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Change le rôle d'un membre (admin/membre). Réservé au propriétaire. Un admin peut
    inviter des membres ; le propriétaire reste seul à pouvoir retirer/transférer."""
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut changer les rôles")
    role = (data.role or "").strip().lower()
    if role not in ("admin", "membre"):
        raise HTTPException(400, "Rôle invalide (admin ou membre)")
    member = db.query(User).filter(User.id == member_id, User.org_id == org.id).first()
    if not member:
        raise HTTPException(404, "Membre introuvable")
    if member.id == org.owner_id:
        raise HTTPException(400, "Le propriétaire est administrateur par défaut")
    member.org_role = role
    db.commit()
    audit.record(db, action="team.role_changed", owner_id=org.owner_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="user", target_id=member.id,
                 detail=f"{member.email} → {role}"[:255], ip=audit.client_ip(request))
    return {"ok": True, "id": member.id, "role": role}


def _transferer_facturation(db, ancien: User, nouveau: User) -> None:
    """Le compte de facturation est le propriétaire de l'organisation (quota._billing_user : quota, écran Abonnement,
    /api/stripe/status ; docs/ESSAI_GARDE_FOU.md) : au transfert, ce qui se facture passe de l'ancien au nouveau.
    Déplacés (l'ancien retombe sans forfait) : forfait, client Stripe (le webhook retrouve le compte par lui),
    paiement à l'usage et son compteur, compteurs d'analyses du mois, unités de dépassement envoyées à Stripe (lignes
    `jobs`, annulables si l'analyse est remboursée). Copiés (l'ancien garde les siens : s'il quitte un jour
    l'organisation, il reste soumis à son essai, jamais un compte sans fin d'essai) : fin d'essai, analyses de
    l'essai. Le relevé du coût de l'IA (usage_ia : limite d'usage de l'essai, alerte des forfaits) suit lui aussi."""
    import logging
    from app.models import Job, PlanType, UsageIA
    from app.services.billing_usage import UNITE_KIND
    if nouveau.stripe_customer_id and nouveau.stripe_customer_id != ancien.stripe_customer_id:
        # Client Stripe propre au nouveau propriétaire (paiement fait par un collègue avant le 22/10) : remplacé par
        # celui de l'organisation ; noté pour pouvoir le retrouver (il porte aussi user_id dans ses métadonnées).
        logging.getLogger("adjugo").warning("transfert de propriété : client Stripe %s du compte %s remplacé par %s",
                                            nouveau.stripe_customer_id, nouveau.id, ancien.stripe_customer_id)
    for champ, defaut in (("plan", PlanType.starter), ("stripe_customer_id", None), ("overage_enabled", False),
                          ("overage_count", 0), ("analyses_used_this_month", 0), ("analyses_period", "")):
        valeur = getattr(ancien, champ)
        setattr(nouveau, champ, defaut if valeur is None else valeur)
        setattr(ancien, champ, defaut)
    nouveau.trial_ends_at = ancien.trial_ends_at
    nouveau.trial_analyses_used = int(ancien.trial_analyses_used or 0)
    db.flush()
    ancien_c, nouveau_c = f"u{ancien.id}", f"u{nouveau.id}"
    for r in db.query(UsageIA).filter(UsageIA.compte == ancien_c).all():
        cible = db.query(UsageIA).filter(UsageIA.compte == nouveau_c, UsageIA.periode == r.periode,
                                         UsageIA.essai == r.essai).first()
        if cible is None:
            r.compte, r.billing_user_id, r.org_id = nouveau_c, nouveau.id, nouveau.org_id
            continue
        # Même période, même nature (essai ou non) : une seule ligne (contrainte compte, période, essai).
        cible.cout_eur = float(cible.cout_eur or 0) + float(r.cout_eur or 0)
        cible.appels = int(cible.appels or 0) + int(r.appels or 0)
        cible.tokens_entree = int(cible.tokens_entree or 0) + int(r.tokens_entree or 0)
        cible.tokens_sortie = int(cible.tokens_sortie or 0) + int(r.tokens_sortie or 0)
        cible.alerte_le = cible.alerte_le or r.alerte_le
        cible.billing_user_id = nouveau.id
        db.delete(r)
    db.flush()
    db.query(Job).filter(Job.user_id == ancien.id, Job.kind == UNITE_KIND).update(
        {Job.user_id: nouveau.id}, synchronize_session=False)
    db.flush()


class TransferIn(BaseModel):
    new_owner_id: int


@router.post("/transfer-ownership")
@limiter.limit("20/hour")
def transfer_ownership(data: TransferIn, request: Request,
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Transfère la propriété de l'organisation à un autre membre (continuité si le
    fondateur part). Seul le propriétaire actuel peut le faire."""
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut transférer la propriété")
    target = db.query(User).filter(User.id == data.new_owner_id, User.org_id == org.id).first()
    if not target:
        raise HTTPException(404, "Ce membre n'appartient pas à l'organisation")
    if target.id == current_user.id:
        raise HTTPException(400, "Vous êtes déjà propriétaire")
    org.owner_id = target.id
    target.org_role = "admin"
    # L'ancien propriétaire devient administrateur, ce que dit la fenêtre de transfert (app.js, orgTransfer : « Vous
    # deviendrez simple administrateur. ») : il invite encore des collègues ; seul le nouveau propriétaire retire,
    # change les rôles, transfère et modifie l'organisation. Avant : « membre », contre le texte affiché.
    current_user.org_role = "admin"
    # L'ancien propriétaire perd ses droits → on révoque ses sessions en cours pour que
    # la baisse d'autorité prenne effet immédiatement (pas seulement au prochain login).
    current_user.token_version = (current_user.token_version or 0) + 1
    # Le compte de facturation change avec le propriétaire : forfait, client Stripe, essai et relevé du coût de l'IA
    # le suivent. Avant, une organisation Pro redevenait « starter » (5 analyses), un essai terminé transféré à un
    # collègue rouvrait l'IA, et le webhook Stripe ne mettait plus l'organisation à jour.
    _transferer_facturation(db, current_user, target)
    # data_owner_id() bascule sur le nouveau propriétaire : on DOIT migrer avec lui les
    # données portées par le tenant, sinon elles deviennent orphelines/invisibles pour TOUTE
    # l'organisation (fiche entreprise, critères Go/No-Go, co-traitance). On ne touche PAS
    # AuditLog (sa chaîne de hash deviendrait invérifiable).
    from app.models import (Company, MatchingCriteria, CoSpace, ProjectInvite, ProjectContribution,
                            ContributionPiece, GroupementSimulation, GroupementConvention,
                            GroupementSignature)
    from app.routers.criteria_v2 import MatchingCriteriaExt
    old_id, new_id = current_user.id, target.id
    # (a) mono-propriétaire UNIQUE(user_id) : purger une éventuelle ligne du nouveau owner
    #     (issue de son usage perso/inscription) avant de réaffecter, pour éviter une collision.
    for M in (Company, MatchingCriteria, MatchingCriteriaExt):
        db.query(M).filter(M.user_id == new_id).delete(synchronize_session=False)
        db.query(M).filter(M.user_id == old_id).update({M.user_id: new_id}, synchronize_session=False)
    # (b) co-traitance et simulations « Répondre à plusieurs ? » (owner_id = tenant
    #     mandataire) : simple réaffectation — sinon elles restaient à l'ex-propriétaire
    #     (invisibles pour l'org, et effacées avec son compte).
    # Dossiers de présentation de l'atelier (rédaction, vague 2) : portés par le tenant aussi.
    from app.models import (DepotLienDocument, DepotLienEspace, DossierPartBrouillon, DossierPresentation,
                            DossierRepartition, DossierSection, DossierSectionVersion, DossierValidation,
                            EntretienQuestion)
    # Documents déposés par les liens des partenaires (décision 5 a) : owner_id = tenant du marché (cycle de vie).
    # Entretien chantier (rédaction, vague 5) : porté par le tenant comme l'atelier.
    for M in (CoSpace, ProjectInvite, ProjectContribution, ContributionPiece, GroupementSimulation,
              GroupementConvention, GroupementSignature, DossierPresentation, DossierSection,
              DossierSectionVersion, DossierRepartition, DossierPartBrouillon, DossierValidation,
              DepotLienEspace, DepotLienDocument, EntretienQuestion):
        db.query(M).filter(M.owner_id == old_id).update({M.owner_id: new_id}, synchronize_session=False)
    # « Mes preuves » (rédaction, vague 3, owner_id = tenant) : elles suivent le nouveau propriétaire.
    from app.services.preuves import transferer as _transferer_preuves
    _transferer_preuves(db, old_id, new_id)
    # (c) profil partenaire du réseau (vague 3, user_id UNIQUE = data_owner_id) : il suit le
    #     nouveau propriétaire, sinon il devenait orphelin et inéditable par l'organisation.
    from app.services.partner_network import transfer_profile
    transfer_profile(db, old_id, new_id)
    db.commit()
    audit.record(db, action="team.ownership_transferred", owner_id=org.owner_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="user", target_id=target.id, detail=(target.email or "")[:255],
                 ip=audit.client_ip(request))
    # On vient d'incrémenter token_version → l'ancien jeton est invalide. On renvoie un jeton
    # FRAIS (comme le changement de mot de passe) pour que l'ex-propriétaire reste connecté en
    # tant qu'admin, au lieu d'être éjecté vers l'écran de login dès le prochain appel (401).
    db.refresh(current_user)
    fresh = create_access_token(data={"sub": str(current_user.id),
                                      "tv": int(current_user.token_version or 0)})
    return {"ok": True, "owner_id": org.owner_id, "access_token": fresh}
