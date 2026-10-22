"""
Adjugo — Routes d'authentification
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from sqlalchemy import func

from datetime import timedelta, datetime, timezone

from app.core.database import get_db
from app.core.security import (hash_password, verify_password, create_access_token,
                               get_current_user, decode_token, needs_rehash, DUMMY_HASH)
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.models import User, Company, MatchingCriteria
from app.schemas import UserCreate, UserLogin, Token, UserOut, RegisterOut
from app.services.email import send_email
from app.services.email_templates import verify_email_html

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


VERIFY_LINK_HOURS = 48
# Ce qui suit la confirmation (vague 2b, décision 12 (a)) : la même phrase à l'écran (app.html,
# ecran-confirmation-email) et dans le courriel de confirmation (texte et HTML).
APRES_CONFIRMATION = "Une fois confirmé, vous entrez votre SIRET et vous voyez les marchés de votre zone."


def _norm_email(e) -> str:
    return (str(e or "")).strip().lower()


# Plafond PAR COMPTE des emails de confirmation (inscription, renvoi, changement d'adresse).
# Sans lui, un compte d'essai non confirmé changeait d'adresse en boucle et faisait envoyer
# des emails « Adjugo » signés SPF/DKIM à n'importe qui. En mémoire : process unique (cf.
# invariants), une remise à zéro au redémarrage reste acceptable.
VERIFY_MAILS_PER_DAY = 5
_VERIFY_SENT: dict[int, list[float]] = {}
_VERIFY_LOCK = __import__("threading").Lock()


def _verify_mail_budget(user_id: int, consume: bool) -> bool:
    import time
    now = time.time()
    with _VERIFY_LOCK:
        recent = [t for t in _VERIFY_SENT.get(user_id, []) if now - t < 86400]
        ok = len(recent) < VERIFY_MAILS_PER_DAY
        if ok and consume:
            recent.append(now)
        _VERIFY_SENT[user_id] = recent
        return ok


def clean_full_name(v) -> str:
    """Nom affiché : sans caractères de contrôle, borné. Il apparaît dans des emails."""
    v = "".join(ch for ch in str(v or "") if ch.isprintable()).strip()
    return v[:120]


def _suite_apres_confirmation(user: User) -> str:
    """La phrase APRES_CONFIRMATION, seulement quand elle est vraie : l'entreprise n'a pas encore de SIRET (compte
    neuf). Une adresse changée, ou un collègue d'une entreprise déjà renseignée, ne reçoit pas « vous entrez votre
    SIRET ». Lue dans la fiche de l'entreprise de l'organisation (data_owner_id)."""
    try:
        from sqlalchemy.orm import object_session
        from app.core.org import data_owner_id
        db = object_session(user)
        if db is None:
            return APRES_CONFIRMATION
        row = db.query(Company.siret).filter(Company.user_id == data_owner_id(user, db)).first()
        return "" if (row and (row[0] or "").strip()) else APRES_CONFIRMATION
    except Exception:
        return APRES_CONFIRMATION


def _verify_mail_rendre(user_id: int) -> None:
    """Un envoi compté qui n'est pas parti (courriel coupé, service d'envoi en panne) est rendu au plafond du jour :
    le plafond compte les courriels réellement envoyés, cinq pannes de suite n'épuisent pas la journée."""
    with _VERIFY_LOCK:
        lst = _VERIFY_SENT.get(user_id) or []
        if lst:
            lst.pop()


def _send_verification(user: User) -> bool:
    """Génère un lien signé (48 h) et envoie l'email de confirmation. Silencieux si l'email
    est désactivé/échoue → ne bloque JAMAIS l'inscription. Renvoie vrai si le courriel est PARTI
    (valeur de send_email) ; sinon faux, et l'envoi manqué est rendu au plafond du jour.
    Le jeton porte `purpose` (jamais accepté comme session, cf. get_current_user) et
    l'ADRESSE à prouver : un ancien lien ne peut pas confirmer une adresse changée depuis."""
    if not _verify_mail_budget(user.id, consume=True):
        return False
    parti = False
    try:
        token = create_access_token(data={"sub": str(user.id), "purpose": "verify_email",
                                          "email": _norm_email(user.email)},
                                    expires_delta=timedelta(hours=VERIFY_LINK_HOURS))
        base = (get_settings().APP_BASE_URL or "https://adjugo.pro").rstrip("/")
        link = f"{base}/app?verify={token}"
        suite = _suite_apres_confirmation(user)
        parti = bool(send_email(user.email, "Confirmez votre adresse email — Adjugo",
                                "Bienvenue sur Adjugo !\n\nConfirmez votre adresse email (lien valable 48 heures) :\n"
                                f"{link}\n\n" + (suite + "\n\n" if suite else "")
                                + "Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.\n\n— Adjugo",
                                html=verify_email_html(link, user.full_name or "", suite)))
    except Exception:
        parti = False
    if not parti:
        _verify_mail_rendre(user.id)
    return parti


# Réponse de « Renvoyer l'email de vérification » quand le courriel n'est pas parti (affichée telle quelle par l'écran
# plein « Confirmez votre adresse email » et par les boutons « Renvoyer l'email de confirmation »). Avant : « Email de
# confirmation renvoyé. » dans ce cas aussi.
MSG_VERIF_NON_PARTIE = ("L'email de confirmation n'a pas pu partir pour l'instant. Réessayez dans un instant ; "
                        "si cela continue, écrivez-nous.")


@router.post("/register", response_model=RegisterOut, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    """Créer un nouveau compte utilisateur."""
    # data.email est déjà normalisé (minuscules) par le schéma. Le doublon se teste en
    # INSENSIBLE à la casse pour couvrir d'éventuelles anciennes lignes en casse mixte.
    if db.query(User).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    fn = clean_full_name(data.full_name)
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=fn,
        org_role="admin",
        # Essai gratuit 30 jours sans carte : accès niveau Pro jusqu'à cette date, puis
        # blocage tant qu'aucun abonnement (cf. app/core/quota.py). Compte historique = NULL.
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(user)
    db.flush()

    # Créer l'organisation (espace de travail) dont l'utilisateur est propriétaire. Repli si le
    # nom complet est vide (sinon on créait une organisation nommée « Équipe » + espace).
    from app.models import Organization
    org_name = data.company_name or (f"Équipe {fn}" if fn else "Mon organisation")
    org = Organization(name=org_name, owner_id=user.id)
    db.add(org)
    db.flush()
    user.org_id = org.id

    # Créer le profil entreprise si un nom est fourni
    if data.company_name:
        company = Company(user_id=user.id, name=data.company_name)
        db.add(company)

    # Créer les critères par défaut
    criteria = MatchingCriteria(user_id=user.id)
    db.add(criteria)

    db.commit()
    db.refresh(user)

    # Email de confirmation. Choix du 24/06, gardé (décision 12 (a) de l'étude « organisation du logiciel », vague 2b) :
    # tant que l'adresse n'est pas confirmée, l'application affiche un écran plein « Confirmez votre adresse email »
    # (app.html, `ecran-confirmation-email`) qui dit la suite (APRES_CONFIRMATION) et revérifie seul la confirmation
    # (au retour sur l'onglet, puis à intervalle croissant tant qu'il est ouvert : GET /api/auth/me). Le serveur ne s'en
    # remet pas à cet écran : sans adresse confirmée, il refuse toute analyse d'un marché (consume_analysis,
    # app/core/quota.py : 403), les rédactions de l'atelier, de l'entretien et des fiches de Mon savoir-faire (403
    # « email_non_confirme »), l'invitation d'un membre du réseau, la demande de publication du profil partenaire,
    # l'accord donné sur une convention et l'acceptation d'un lien nominatif (403) ; il n'envoie aucun courriel au nom
    # d'Adjugo vers un tiers (invitation d'un partenaire ou d'un collègue : le lien reste à copier ; ni le rappel
    # planifié de la part ni l'alerte d'attestations à ses partenaires : app/services/alerts.py,
    # _comptes_non_confirmes ; ni la relance planifiée des parties du dossier de présentation ni « Votre partie est à
    # valider » quand il écrit la partie d'un partenaire : app/services/atelier_groupement.py, relancer_parts et
    # _notifier_partenaire). Seule exception, à la demande de qui ouvre le lien : le code qui vérifie l'adresse du
    # partenaire (sans le lien ; 8 par jour au plus pour une organisation non confirmée : invites._otp_cap_reached),
    # puis, une fois cette adresse vérifiée, l'accusé de sa part envoyée. Vers le compte lui-même, une seule règle
    # (réunion du 22/10, décision 2) : aucune tâche planifiée n'écrit à une adresse non confirmée, qui peut être celle
    # d'un tiers (faute de frappe au changement d'adresse) — ni les alertes de marchés (alerts.run_tender_alerts), ni
    # « Demandez vos notes » (carnet_notes.envoyer_rappels), ni le récapitulatif « pièces à renouveler »
    # (alerts.run_document_expiry_alerts), ni celui des attestations de ses partenaires (alerts._piece_alerts_due), ni la
    # veille amont, masquée (alerts.run_amont_alerts) ; une seule fonction, alerts._comptes_non_confirmes. Rien n'y est
    # marqué envoyé ni « déjà vu » : ils partent au premier passage après la confirmation, « Demandez vos notes »
    # seulement dans ses 14 jours (carnet_notes.COURRIEL_FIN_JOURS), sauf deux exceptions (relecture des décisions du
    # 22/10, docstring d'alerts._comptes_non_confirmes) : le récapitulatif des attestations d'un marché créé par un
    # collègue non confirmé, quand le propriétaire du compte l'est (l'alerte du partenaire, partie quand même, est notée
    # pour tout le palier : le collègue confirmé n'a que le récapitulatif du palier suivant) ; la veille amont, qui
    # n'enregistre aucun projet pour une adresse non confirmée et ne reprend ensuite que ceux des délibérations qu'elle
    # lit alors. Un collègue invité (org.invite_member) est créé non confirmé et ne reçoit aucun lien de confirmation, ni
    # à l'invitation ni à la connexion : l'écran plein le bloque jusqu'à « Renvoyer l'email de vérification ». La règle
    # porte sur les tâches planifiées : les courriels que le compte demande lui-même, comme la confirmation de l'adresse
    # ou le mot de passe oublié, partent comme avant. Ne vérifient PAS
    # l'adresse : les appels qui passent seulement par exiger_ia (questions sur un marché déjà analysé, estimation du
    # prix, veille) ; ils restent bornés par le garde-fou de l'essai (docs/REORGANISATION_V2B.md, B1, laissé). Le jeton
    # est rendu quand même : il sert à renvoyer l'email, à revérifier la confirmation et à se déconnecter.
    _send_verification(user)

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    # Boucle de croissance (vague 3) : suggestion d'INTERFACE « publiez votre profil partenaire », affichée après
    # l'inscription — aucun email n'est envoyé pour ça. Vague 2b : notée sur le serveur (users.suggestion_reseau), elle
    # s'affiche aussi dans l'onglet ouvert par le lien de confirmation, jusqu'à ce qu'on la ferme.
    from app.services.prise_en_main import proposer_suggestion_reseau
    return {"access_token": token, "token_type": "bearer", "suggest_profile": proposer_suggestion_reseau(db, user)}


class VerifyIn(BaseModel):
    token: str


@router.post("/verify-email")
@limiter.limit("30/hour")
def verify_email(request: Request, data: VerifyIn, db: Session = Depends(get_db)):
    """Confirme l'adresse à partir du lien signé reçu par email."""
    try:
        payload = decode_token(data.token)
    except Exception:
        raise HTTPException(400, "Lien de vérification invalide ou expiré.")
    if payload.get("purpose") != "verify_email":
        raise HTTPException(400, "Lien de vérification invalide.")
    try:
        uid = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Lien de vérification invalide.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(404, "Compte introuvable.")
    # Le lien ne prouve QUE l'adresse à laquelle il a été envoyé. Sans ce contrôle, rejouer le
    # lien de l'ancienne adresse « prouvait » une nouvelle adresse qui n'avait rien reçu.
    token_email = _norm_email(payload.get("email"))
    if not token_email:
        # Lien émis avant la liaison à l'adresse : on ne peut pas savoir ce qu'il prouve.
        # Compte DÉJÀ confirmé : rien à prouver, on le dit simplement (pas d'erreur).
        if user.email_verified:
            return {"ok": True, "message": "Votre adresse est déjà confirmée."}
        raise HTTPException(400, "Ce lien de confirmation n'est plus valable. "
                                 "Demandez un nouveau lien depuis votre espace.")
    if token_email != _norm_email(user.email):
        raise HTTPException(400, "Ce lien concerne une ancienne adresse email. "
                                 "Demandez un nouveau lien depuis votre espace.")
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    return {"ok": True, "message": "Adresse email confirmée. Merci !"}


@router.post("/resend-verification")
@limiter.limit("3/hour")
def resend_verification(request: Request, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Renvoie l'email de confirmation au compte connecté."""
    if current_user.email_verified:
        return {"ok": True, "message": "Votre adresse est déjà confirmée."}
    if not _verify_mail_budget(current_user.id, consume=False):
        raise HTTPException(status_code=429, detail="Plusieurs emails de confirmation sont déjà partis "
                                                    "aujourd'hui. Vérifiez vos spams ou réessayez demain.")
    # « Renvoyé » seulement si le courriel est parti : l'écran affiche cette réponse telle quelle.
    if not _send_verification(current_user):
        return {"ok": False, "message": MSG_VERIF_NON_PARTIE}
    return {"ok": True, "message": "Email de confirmation renvoyé."}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Connexion — retourne un JWT."""
    # Recherche insensible à la casse : couvre les comptes créés avant la normalisation.
    user = db.query(User).filter(func.lower(User.email) == data.email).first()
    # Anti-énumération par timing : on exécute TOUJOURS un PBKDF2 (sur un faux hash si l'email
    # est inconnu) → la réponse « identifiants incorrects » prend le même temps, qu'un compte
    # existe ou non. Sinon le court-circuit révélait par chronométrie quels emails ont un compte.
    pwd_ok = verify_password(data.password, user.hashed_password if user else DUMMY_HASH)
    if not user or not pwd_ok:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    # Migration transparente du hachage vers la cible OWASP courante (les anciens hash 100k
    # restent vérifiables et sont remplacés au login réussi).
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(data.password)
        db.commit()

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


class DemoLienIn(BaseModel):
    """Corps des routes de démonstration : la clé du lien privé (jamais dans l'adresse)."""
    cle: str = Field(default="", max_length=256)


@router.post("/demo/lien")
@limiter.limit("60/hour")
def demo_lien_verifier(request: Request, data: Optional[DemoLienIn] = None):
    """Page /demo : la clé du lien privé est-elle valide ? N'ouvre aucune session. Lien
    fermé ou clé fausse : 404, comme une route inexistante (rien ne révèle le lien)."""
    from app.core.demo_guard import demo_lien_valide
    if not demo_lien_valide(data.cle if data else ""):
        raise HTTPException(status_code=404, detail="Not Found")
    return {"ok": True}


@router.post("/demo", response_model=Token)
@limiter.limit("30/hour")
def demo_login(request: Request, data: Optional[DemoLienIn] = None, db: Session = Depends(get_db)):
    """Connexion au compte de DÉMONSTRATION (sans mot de passe) — données pré-remplies.
    Le compte démo est un BAC À SABLE (réinitialisé à chaque démarrage, aucune donnée client
    réelle), en lecture guidée (demo_guard). Il s'ouvre si la démo publique est rouverte
    (DEMO_PUBLIC=1) ou avec la clé du lien privé (corps de la requête, DEMO_LIEN_CLE) ; sinon
    404. Le contournement du cron admin via DEMO_MODE a été fermé séparément (CRON_SECRET)."""
    from app.core.demo_guard import demo_ouverture
    extra = demo_ouverture(data.cle if data else "")
    if extra is None:
        raise HTTPException(status_code=404, detail="Not Found")
    # Nouvelle présentation après une période sans aucune session démo : la vitrine partagée est
    # recréée AVANT d'ouvrir la session (app/services/demo_remise.py ; jamais bloquant).
    from app.services.demo_remise import remettre_a_neuf_si_inactive
    remettre_a_neuf_si_inactive(db)
    from app.services.demo_seed import ensure_demo
    user = ensure_demo(db)   # crée le compte démo s'il n'existe pas encore
    token = create_access_token(data={**extra, "sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Récupérer le profil de l'utilisateur connecté."""
    return current_user


@router.put("/me", response_model=UserOut)
@limiter.limit("10/hour")
def update_me(
    request: Request,
    full_name: str = None,
    email: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour le profil."""
    # Le compte démo est partagé et public : son identité ne change jamais (sinon un visiteur
    # détournait l'adresse de la démo et recevait les emails qui lui sont destinés).
    from app.services.demo_search import is_demo
    if is_demo(current_user) and (email or full_name):
        raise HTTPException(status_code=403, detail="La démo est en lecture guidée : commencez votre essai "
                                                    "gratuit de 30 jours pour modifier un profil.")
    if full_name:
        full_name = clean_full_name(full_name)
        if full_name:
            current_user.full_name = full_name
    if email:
        # Normalisé comme à l'inscription/connexion : sinon « Jean@X.fr » créait un doublon
        # de « jean@x.fr » et l'utilisateur ne pouvait plus se reconnecter.
        email = _norm_email(email)
        # Même validation de format qu'à l'inscription (EmailStr) : sinon une valeur qui n'est
        # pas une adresse était enregistrée (compte inconnectable, emails vers le vide).
        try:
            from pydantic import TypeAdapter, EmailStr
            TypeAdapter(EmailStr).validate_python(email)
            if len(email) > 255:
                raise ValueError("trop long")
        except Exception:
            raise HTTPException(status_code=400, detail="Adresse email invalide. Vérifiez la saisie.")
        existing = db.query(User).filter(func.lower(User.email) == email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email déjà utilisé")
        if email != (current_user.email or "").strip().lower():
            if not _verify_mail_budget(current_user.id, consume=False):
                raise HTTPException(status_code=429, detail="Trop de changements d'adresse aujourd'hui. "
                                                            "Réessayez demain ou écrivez-nous.")
            # Nouvelle adresse = adresse NON prouvée : sans ça, on vérifiait une adresse
            # puis on la remplaçait par n'importe laquelle en restant « vérifié ».
            current_user.email = email
            current_user.email_verified = False
    db.commit()
    db.refresh(current_user)
    if email and not current_user.email_verified:
        _send_verification(current_user)
    return current_user


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=Token)
@limiter.limit("10/hour")
def change_password(request: Request, data: PasswordChange,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Change le mot de passe (notamment pour un membre invité qui doit remplacer son
    mot de passe provisoire). Invalide les autres sessions (token_version) et renvoie un
    token frais pour la session courante."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    if len(data.new_password or "") < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit faire au moins 8 caractères")
    current_user.hashed_password = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 0) + 1  # coupe les autres sessions
    db.commit()
    db.refresh(current_user)
    token = create_access_token(data={"sub": str(current_user.id), "tv": int(current_user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


# ── Mot de passe oublié (réinitialisation par email) ─────────────────────────
import hashlib as _hashlib
import secrets as _secrets
from datetime import datetime as _dt, timedelta as _td, timezone as _tz


def _hash_reset(t: str) -> str:
    return _hashlib.sha256(("adjugo-reset:" + (t or "")).encode("utf-8")).hexdigest()


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, data: ForgotIn, db: Session = Depends(get_db)):
    """Envoie un lien de réinitialisation à l'adresse, SI elle correspond à un compte.
    Réponse identique dans tous les cas (on ne révèle pas l'existence d'un compte)."""
    # Insensible à la casse : un compte créé en casse mixte (« Jean.Dupont@… ») recevait
    # SILENCIEUSEMENT aucun email (le .lower() ne matchait pas la ligne stockée).
    user = db.query(User).filter(func.lower(User.email) == (data.email or "").strip().lower()).first()
    # Compte démo public : jamais d'email (vitrine en lecture guidée) — réponse identique.
    from app.services.demo_search import is_demo
    # Idem pour un compte désactivé/effacé (anonymisé) : il ne peut plus se connecter.
    if user and (is_demo(user) or not user.is_active):
        user = None
    if user:
        raw = _secrets.token_urlsafe(32)
        user.reset_token_hash = _hash_reset(raw)
        user.reset_expires_at = _dt.now(_tz.utc) + _td(hours=1)
        db.commit()
        try:
            from app.services.email import send_email
            from app.services.email_templates import reset_password_html
            from app.core.config import get_settings
            base = (get_settings().APP_BASE_URL or "https://adjugo.pro").rstrip("/")
            link = f"{base}/app?reset={raw}"
            send_email(user.email, "Réinitialisation de votre mot de passe Adjugo",
                       f"Bonjour,\n\nVous avez demandé à réinitialiser votre mot de passe Adjugo.\n"
                       f"Cliquez sur ce lien (valable 1 heure) :\n{link}\n\n"
                       f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\n— Adjugo",
                       html=reset_password_html(link, user.full_name or ""))
        except Exception:
            pass
    return {"ok": True, "message": "Si un compte existe pour cette adresse, un email vient d'être envoyé."}


@router.post("/reset-password", response_model=Token)
@limiter.limit("10/hour")
def reset_password(request: Request, data: ResetIn, db: Session = Depends(get_db)):
    """Pose un nouveau mot de passe à partir d'un token reçu par email. Invalide les
    autres sessions et connecte directement (token frais)."""
    if len(data.new_password or "") < 8:
        raise HTTPException(400, "Le mot de passe doit faire au moins 8 caractères")
    h = _hash_reset((data.token or "").strip())
    user = db.query(User).filter(User.reset_token_hash == h, User.reset_token_hash != "").first()
    exp = getattr(user, "reset_expires_at", None) if user else None
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=_tz.utc)
    if not user or not exp or exp <= _dt.now(_tz.utc):
        raise HTTPException(400, "Lien de réinitialisation invalide ou expiré. Recommencez.")
    user.hashed_password = hash_password(data.new_password)
    user.reset_token_hash = ""
    user.reset_expires_at = None
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}
