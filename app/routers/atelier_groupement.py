"""
Router du DOSSIER DE GROUPEMENT cloisonné (rédaction, vague 4 — « Qui écrit quoi »).

Contrat complet : docs/REDACTION_V4_GROUPEMENT.md. Toute la logique est dans
app/services/atelier_groupement.py ; ici : contrôle d'accès et traduction des erreurs métier
(`detail` = {code, message, …}).

Chef de file (compte, portée organisation — le marché doit appartenir à son organisation, sinon 404) :
  GET  /api/atelier/{pid}/repartition                       « Qui écrit quoi »
  POST /api/atelier/{pid}/repartition                       préparer (pré-remplissage sans IA)
  GET  /api/atelier/{pid}/repartition/{sid}                 une partie : texte commun, avant / après
  PUT  /api/atelier/{pid}/repartition/{sid}                 rédacteur, longueur conseillée, date limite
  PUT  /api/atelier/{pid}/repartition/{sid}/texte           modifier la part d'un partenaire (à revalider)
  POST /api/atelier/{pid}/repartition/demander              « Demander les parts »
  POST /api/atelier/{pid}/repartition/valider-dossier       valider le dossier assemblé
  GET  /api/atelier/{pid}/repartition/dossier               le dossier assemblé, « Prêt à déposer », note interne
  POST /api/atelier/{pid}/repartition/harmoniser            « Harmoniser le ton » (IA : transitions seulement)

Partenaire — par le lien de son invitation (/api/invite/{token}/redaction…) ou par le compte qui a
rattaché ce lien (/api/shared/{project_id}/redaction…, mêmes sous-routes) :
  GET  …/redaction                                          ses parties, son brouillon, l'état du dossier
  GET  …/redaction/dossier                                  le dossier assemblé, en lecture (décision 3a)
  GET  …/redaction/sections/{sid}                           une de SES parties (+ historique de ses brouillons)
  GET  …/redaction/sections/{sid}/brouillons/{bid}          un de SES brouillons précédents, avec son texte
  PUT  …/redaction/sections/{sid}/brouillon                 « J'écris moi-même »
  POST …/redaction/sections/{sid}/faits/{fid}               relu par vous / à relire
  POST …/redaction/sections/{sid}/aide                      « Rédiger avec Adjugo » (tâche de fond)
  GET  …/redaction/taches/{job_id}                          SA tâche (404 pour quiconque d'autre)
  POST …/redaction/sections/{sid}/envoyer                   envoyer (« Ce texte sera lu par… »)
  POST …/redaction/sections/{sid}/valider                   valider le texte commun de sa partie
  POST …/redaction/sections/{sid}/retablir                  rétablir sa version
  POST …/redaction/dossier/valider                          valider le dossier assemblé
  GET  …/redaction/export                                   ses brouillons et ses textes envoyés (portabilité)
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import DossierSection, Project, User
from app.services import atelier as at
from app.services import atelier_groupement as ag

router = APIRouter(tags=["Dossier de groupement (rédaction, vague 4)"])


def _err(e: at.AtelierError):
    return HTTPException(e.status, e.detail())


def _ip(request: Request) -> str:
    from app.services.audit import client_ip
    return client_ip(request)


# Démo (vitrine en lecture guidée, app/core/demo_guard.py) : défense en profondeur DANS les routes, derrière
# le garde central. Le compte démo ne prépare ni ne modifie le dossier de groupement de la vitrine partagée,
# n'envoie aucun email (un envoi prévient le chef de file ; une modification prévient le partenaire) et ne
# lance aucune aide de l'IA ; le lien partenaire de la démo n'écrit rien (refusé AVANT tout autre contrôle).
DEMO_ACTION = "préparer votre dossier de présentation"
DEMO_ACTION_PART = "co-construire une réponse avec vos partenaires"


def _refuser_demo(user: User, action: str = DEMO_ACTION) -> None:
    """Défense en profondeur, derrière le garde central : la vitrine de la démo ne change pas."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(user, action)


# ── Chef de file ─────────────────────────────────────────────────────────────────────

class _Chef:
    def __init__(self, db: Session, user: User, project_id: int):
        from app.routers.atelier import _Acces
        self.acc = _Acces(db, user, project_id)
        self.db, self.user, self.project = db, user, self.acc.project

    @property
    def dossier(self):
        return self.acc.exiger_dossier()

    def section(self, sid: int) -> DossierSection:
        return self.acc.section(sid)


@router.get("/api/atelier/{project_id}/repartition")
def chef_lire(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _Chef(db, current_user, project_id)
    return ag.vue_chef(db, c.project, c.dossier)


# Déclarée AVANT /repartition/{section_id} (sinon « dossier » serait lu comme un numéro de partie).
@router.get("/api/atelier/{project_id}/repartition/dossier")
def chef_dossier(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le dossier assemblé tel que le lit le chef de file (assemblage, docs/REDACTION_V4_GROUPEMENT.md § 17) :
    l'ordre du cadre, les parties tirées du groupement, « Prêt à déposer » et ce qui manque, plus la note
    interne (jamais exportée, jamais montrée aux partenaires)."""
    c = _Chef(db, current_user, project_id)
    if not ag.repartition_active(db, c.dossier):
        raise HTTPException(404, {"code": "groupement_non_prepare",
                                  "message": "Préparez d'abord « Qui écrit quoi » pour assembler le dossier du groupement."})
    return ag.dossier_assemble(db, c.project, c.dossier, pour_chef=True)


class ActiverIn(BaseModel):
    reproposer: bool = False


@router.post("/api/atelier/{project_id}/repartition")
@limiter.limit("60/hour")
def chef_activer(request: Request, project_id: int, body: Optional[ActiverIn] = None,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    c = _Chef(db, current_user, project_id)
    try:
        res = ag.activer(db, c.project, c.dossier, c.acc.lecteur, reproposer=bool(body and body.reproposer),
                         ip=_ip(request))
    except at.AtelierError as e:
        raise _err(e)
    return dict(ag.vue_chef(db, c.project, c.dossier), preparation=res)


@router.get("/api/atelier/{project_id}/repartition/{section_id}")
def chef_detail(project_id: int, section_id: int, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    c = _Chef(db, current_user, project_id)
    s = c.section(section_id)
    try:
        return ag.detail_chef(db, c.project, c.dossier, s)
    except at.AtelierError as e:
        raise _err(e)


class RepartirIn(BaseModel):
    redacteur: Optional[str] = None
    invite_id: Optional[int] = None
    longueur_mots: Optional[int] = None
    date_limite: Optional[date] = None
    confirmer: bool = False
    lock_version: Optional[int] = None


@router.put("/api/atelier/{project_id}/repartition/{section_id}")
@limiter.limit("600/hour")
def chef_repartir(request: Request, project_id: int, section_id: int, body: RepartirIn,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    c = _Chef(db, current_user, project_id)
    s = c.section(section_id)
    champs = body.model_fields_set
    kw = {}
    if "redacteur" in champs or "invite_id" in champs:
        kw["redacteur"] = body.redacteur if "redacteur" in champs else ag.BASE_DEFAUT
        kw["invite_id"] = body.invite_id if "invite_id" in champs else ag.BASE_DEFAUT
    if "longueur_mots" in champs:
        kw["longueur_mots"] = body.longueur_mots
    if "date_limite" in champs:
        kw["date_limite"] = body.date_limite
    try:
        ag.repartir(db, c.project, c.dossier, s, c.acc.lecteur, confirmer=body.confirmer,
                    lock_version=body.lock_version, ip=_ip(request), **kw)
        return ag.detail_chef(db, c.project, c.dossier, s)
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)


class TexteChefIn(BaseModel):
    texte: str = Field("", max_length=at.TEXTE_MAX + 2000)
    base_version_id: Optional[int] = None


@router.put("/api/atelier/{project_id}/repartition/{section_id}/texte")
@limiter.limit("600/hour")
def chef_modifier_part(request: Request, project_id: int, section_id: int, body: TexteChefIn,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le chef de file modifie la part d'un partenaire, ou l'écrit à sa place : « à revalider par » lui (le
    partenaire en est prévenu par email : jamais pour la démo)."""
    _refuser_demo(current_user)
    c = _Chef(db, current_user, project_id)
    s = c.section(section_id)
    try:
        ag.modifier_part(db, c.project, c.dossier, s, current_user, body.texte, body.base_version_id, ip=_ip(request))
        return ag.detail_chef(db, c.project, c.dossier, s)
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)


class DemanderIn(BaseModel):
    invite_ids: Optional[List[int]] = None


@router.post("/api/atelier/{project_id}/repartition/demander")
@limiter.limit("20/hour")
def chef_demander(request: Request, project_id: int, body: Optional[DemanderIn] = None,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Demander les parts » : un email à chaque partenaire qui a des parties à rédiger ou à revalider."""
    from app.routers.invites import _refuse_demo_sender, _require_verified_sender
    _refuse_demo_sender(current_user)
    _require_verified_sender(current_user)
    c = _Chef(db, current_user, project_id)
    return ag.demander_parts(db, c.project, c.dossier, current_user, invite_ids=(body.invite_ids if body else None),
                             ip=_ip(request))


class ValiderDossierIn(BaseModel):
    empreinte: Optional[str] = Field(None, max_length=64)


@router.post("/api/atelier/{project_id}/repartition/valider-dossier")
@limiter.limit("60/hour")
def chef_valider_dossier(request: Request, project_id: int, body: Optional[ValiderDossierIn] = None,
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    c = _Chef(db, current_user, project_id)
    try:
        v = ag.valider_dossier(db, c.project, c.dossier, membre=ag.CHEF, user_id=current_user.id,
                               empreinte_vue=(body.empreinte if body else None),
                               actor=current_user.email or f"user:{current_user.id}", actor_kind="owner",
                               ip=_ip(request))
    except at.AtelierError as e:
        raise _err(e)
    return {"validation": v, "pret": ag.pret(db, c.project, c.dossier)}


class HarmoniserIn(BaseModel):
    accepte_debit: bool = False


@router.post("/api/atelier/{project_id}/repartition/harmoniser", status_code=202)
@limiter.limit("10/hour")
def chef_harmoniser(request: Request, project_id: int, body: Optional[HarmoniserIn] = None,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Harmoniser le ton » : l'IA propose une phrase de transition au début des parties qui suivent la part d'un
    autre membre ; toute phrase qui apporte un fait absent du dossier est refusée sans IA ; les parties touchées
    repassent « à revalider » par leur auteur. Tâche de fond : suivre /api/atelier/{pid}/taches/{job_id}."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "rédiger avec Adjugo")
    if not getattr(current_user, "email_verified", True):
        raise HTTPException(403, {"code": "email_non_confirme",
                                  "message": "Confirmez votre adresse email pour utiliser cette fonctionnalité."})
    c = _Chef(db, current_user, project_id)
    try:
        job = ag.lancer_harmonisation(db, current_user, c.project, c.dossier, c.acc.lecteur, c.acc.mids,
                                      accepte_debit=bool(body and body.accepte_debit))
    except at.AtelierError as e:
        raise _err(e)
    db.refresh(c.dossier)
    return {"tache": at.job_public(job), "quota": at.quota_out(c.dossier)}


# ── Partenaire : résolution de l'accès (lien ou compte) ──────────────────────────────

def _project_of(inv, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    if not p:
        raise HTTPException(404, "Projet introuvable ou retiré")
    return p


def _par_lien(token: str, db: Session, request: Request, ecrire: bool = False) -> ag.Acces:
    """Le lien de l'invitation, et la clé de l'espace privé du partenaire (en-tête X-Adjugo-Espace) :
    sans clé valide, seul ce qui est commun se lit (ses parties, les textes envoyés, le dossier assemblé).
    `ecrire` : une écriture par le lien de la démo est refusée avant tout autre contrôle (lecture guidée)."""
    from app.routers.invites import _invite_is_demo, _valid_invite
    inv = _valid_invite(token, db)          # révoqué → 404, décliné ou expiré → 410 : l'accès est coupé
    if ecrire and _invite_is_demo(inv, db):
        from app.core.demo_guard import demo_message
        raise HTTPException(403, {"code": "demo", "message": demo_message(DEMO_ACTION_PART)})
    try:
        return ag.acces_partenaire(db, inv, _project_of(inv, db), mode="lien",
                                   cle=request.headers.get(ag.ENTETE_CLE))
    except at.AtelierError as e:
        raise _err(e)


def _par_compte(project_id: int, user: User, db: Session) -> ag.Acces:
    """Le compte qui a rattaché le lien (« Partagé avec moi »). Les routes d'écriture refusent la démo elles-mêmes
    (`_refuser_demo`, derrière le garde central)."""
    from app.routers.journal_membre import _shared_invite
    inv, project = _shared_invite(project_id, user, db)     # lien rattaché à CE compte, actif, non expiré
    try:
        return ag.acces_partenaire(db, inv, project, user=user, mode="compte")
    except at.AtelierError as e:
        raise _err(e)


def _faire(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except at.AtelierError as e:
        raise _err(e)


class BrouillonIn(BaseModel):
    texte: str = Field("", max_length=at.TEXTE_MAX + 2000)
    base_brouillon_id: Optional[int] = None


class FaitIn(BaseModel):
    statut: str


class AideIn(BaseModel):
    action: str = "rediger"
    cible_mots: Optional[int] = None


class EnvoyerIn(BaseModel):
    brouillon_id: int
    avertissement_lu: bool = False


class ValiderIn(BaseModel):
    version_id: int


class RetablirIn(BaseModel):
    base_version_id: int
    version_id: Optional[int] = None


# Implémentations communes aux deux chemins (le lien, le compte).

def _vue(acces, db):
    return ag.vue_partenaire(db, acces)


def _dossier(acces, db):
    return ag.dossier_assemble(db, acces.project, acces.dossier, pour_invite_id=acces.invite_id)


def _section(acces, db, sid):
    return _faire(ag.detail_partenaire, db, acces, sid)


def _brouillon_lu(acces, db, sid, bid):
    return _faire(ag.brouillon_du_partenaire, db, acces, sid, bid)


def _brouillon(acces, db, sid, body: BrouillonIn):
    _faire(ag.enregistrer_brouillon, db, acces, sid, body.texte, body.base_brouillon_id)
    return _section(acces, db, sid)


def _fait(acces, db, sid, fid, body: FaitIn):
    fait = _faire(ag.traiter_fait, db, acces, sid, fid[:40], body.statut)
    return {"fait": fait, "section": _section(acces, db, sid)}


def _aide(acces, db, sid, body: Optional[AideIn]):
    job = _faire(ag.lancer_aide, db, acces, sid, (body.action if body else "rediger"),
                 (body.cible_mots if body else None))
    return {"tache": at.job_public(job), "section_id": sid}


def _tache(acces, db, job_id):
    return _faire(ag.tache, db, acces, job_id)


def _envoyer(acces, db, sid, body: EnvoyerIn, ip):
    _faire(ag.envoyer, db, acces, sid, body.brouillon_id, body.avertissement_lu, ip=ip)
    return _section(acces, db, sid)


def _valider(acces, db, sid, body: ValiderIn, ip):
    _faire(ag.valider_part, db, acces, sid, body.version_id, ip=ip)
    return _section(acces, db, sid)


def _retablir(acces, db, sid, body: RetablirIn, ip):
    _faire(ag.retablir, db, acces, sid, body.base_version_id, version_id=body.version_id, ip=ip)
    return _section(acces, db, sid)


def _valider_dossier(acces, db, body: Optional[ValiderDossierIn], ip):
    try:
        ag._exiger_ecriture(acces)
        ag._exiger_identite(acces)
        v = ag.valider_dossier(db, acces.project, acces.dossier, membre=ag.PARTENAIRE, invite_id=acces.invite_id,
                               user_id=getattr(acces.user, "id", None), empreinte_vue=(body.empreinte if body else None),
                               actor=acces.acteur, actor_kind="guest", ip=ip)
    except at.AtelierError as e:
        raise _err(e)
    return {"validation": v, "pret": ag.pret(db, acces.project, acces.dossier)}


def _export(acces, db):
    import json
    _faire(ag._exiger_espace, acces)
    payload = json.dumps(ag.exporter_invitation(db, acces.inv, sources_du_compte=(acces.mode == "compte")),
                         ensure_ascii=False, indent=2, default=str)
    return Response(content=payload, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="ma_partie_adjugo.json"',
                             "Cache-Control": "no-store"})


# ── Partenaire par le LIEN de son invitation ─────────────────────────────────────────

L = "/api/invite/{token}/redaction"


class EspaceIn(BaseModel):
    code: Optional[str] = Field(None, max_length=12)
    reinitialiser: bool = False


@router.post(L + "/espace")
@limiter.limit("20/hour")
def lien_espace(token: str, request: Request, body: Optional[EspaceIn] = None, db: Session = Depends(get_db)):
    """Ouvre l'espace privé du lien sur cet appareil et rend sa clé, UNE fois (à garder dans le navigateur, à
    renvoyer dans l'en-tête X-Adjugo-Espace) : première ouverture ; ou avec le code reçu par email (brouillons
    gardés) ; ou en réinitialisant (brouillons non envoyés effacés)."""
    acces = _par_lien(token, db, request, ecrire=True)
    return _faire(ag.ouvrir_espace, db, acces.inv, code=(body.code if body else None),
                  reinitialiser=bool(body and body.reinitialiser), ip=_ip(request))


@router.get(L)
@limiter.limit("120/minute")
def lien_vue(token: str, request: Request, db: Session = Depends(get_db)):
    return _vue(_par_lien(token, db, request), db)


@router.get(L + "/dossier")
@limiter.limit("60/minute")
def lien_dossier(token: str, request: Request, db: Session = Depends(get_db)):
    return _dossier(_par_lien(token, db, request), db)


@router.get(L + "/sections/{section_id}")
@limiter.limit("120/minute")
def lien_section(token: str, section_id: int, request: Request, db: Session = Depends(get_db)):
    return _section(_par_lien(token, db, request), db, section_id)


@router.get(L + "/sections/{section_id}/brouillons/{brouillon_id}")
@limiter.limit("120/minute")
def lien_brouillon_lu(token: str, section_id: int, brouillon_id: int, request: Request, db: Session = Depends(get_db)):
    return _brouillon_lu(_par_lien(token, db, request), db, section_id, brouillon_id)


@router.put(L + "/sections/{section_id}/brouillon")
@limiter.limit("90/minute")
def lien_brouillon(token: str, section_id: int, body: BrouillonIn, request: Request, db: Session = Depends(get_db)):
    return _brouillon(_par_lien(token, db, request, ecrire=True), db, section_id, body)


@router.post(L + "/sections/{section_id}/faits/{fait_id}")
@limiter.limit("300/hour")
def lien_fait(token: str, section_id: int, fait_id: str, body: FaitIn, request: Request,
              db: Session = Depends(get_db)):
    return _fait(_par_lien(token, db, request, ecrire=True), db, section_id, fait_id, body)


@router.post(L + "/sections/{section_id}/aide", status_code=202)
@limiter.limit("20/hour")
def lien_aide(token: str, section_id: int, request: Request, body: Optional[AideIn] = None,
              db: Session = Depends(get_db)):
    return _aide(_par_lien(token, db, request, ecrire=True), db, section_id, body)


@router.get(L + "/taches/{job_id}")
@limiter.limit("120/minute")
def lien_tache(token: str, job_id: int, request: Request, db: Session = Depends(get_db)):
    return _tache(_par_lien(token, db, request), db, job_id)


@router.post(L + "/sections/{section_id}/envoyer")
@limiter.limit("60/hour")
def lien_envoyer(token: str, section_id: int, body: EnvoyerIn, request: Request, db: Session = Depends(get_db)):
    return _envoyer(_par_lien(token, db, request, ecrire=True), db, section_id, body, _ip(request))


@router.post(L + "/sections/{section_id}/valider")
@limiter.limit("60/hour")
def lien_valider(token: str, section_id: int, body: ValiderIn, request: Request, db: Session = Depends(get_db)):
    return _valider(_par_lien(token, db, request, ecrire=True), db, section_id, body, _ip(request))


@router.post(L + "/sections/{section_id}/retablir")
@limiter.limit("60/hour")
def lien_retablir(token: str, section_id: int, body: RetablirIn, request: Request, db: Session = Depends(get_db)):
    return _retablir(_par_lien(token, db, request, ecrire=True), db, section_id, body, _ip(request))


@router.post(L + "/dossier/valider")
@limiter.limit("30/hour")
def lien_valider_dossier(token: str, request: Request, body: Optional[ValiderDossierIn] = None,
                         db: Session = Depends(get_db)):
    return _valider_dossier(_par_lien(token, db, request, ecrire=True), db, body, _ip(request))


@router.get(L + "/export")
@limiter.limit("10/hour")
def lien_export(token: str, request: Request, db: Session = Depends(get_db)):
    return _export(_par_lien(token, db, request), db)


# ── Partenaire par le COMPTE Adjugo qui a rattaché son lien (« Partagé avec moi ») ───

C = "/api/shared/{project_id}/redaction"


@router.get(C)
@limiter.limit("120/minute")
def compte_vue(project_id: int, request: Request, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return _vue(_par_compte(project_id, current_user, db), db)


@router.get(C + "/dossier")
@limiter.limit("60/minute")
def compte_dossier(project_id: int, request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return _dossier(_par_compte(project_id, current_user, db), db)


@router.get(C + "/sections/{section_id}")
@limiter.limit("120/minute")
def compte_section(project_id: int, section_id: int, request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return _section(_par_compte(project_id, current_user, db), db, section_id)


@router.get(C + "/sections/{section_id}/brouillons/{brouillon_id}")
@limiter.limit("120/minute")
def compte_brouillon_lu(project_id: int, section_id: int, brouillon_id: int, request: Request,
                        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _brouillon_lu(_par_compte(project_id, current_user, db), db, section_id, brouillon_id)


@router.put(C + "/sections/{section_id}/brouillon")
@limiter.limit("90/minute")
def compte_brouillon(project_id: int, section_id: int, body: BrouillonIn, request: Request,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _brouillon(_par_compte(project_id, current_user, db), db, section_id, body)


@router.post(C + "/sections/{section_id}/faits/{fait_id}")
@limiter.limit("300/hour")
def compte_fait(project_id: int, section_id: int, fait_id: str, body: FaitIn, request: Request,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _fait(_par_compte(project_id, current_user, db), db, section_id, fait_id, body)


@router.post(C + "/sections/{section_id}/aide", status_code=202)
@limiter.limit("20/hour")
def compte_aide(project_id: int, section_id: int, request: Request, body: Optional[AideIn] = None,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, "rédiger avec Adjugo")
    if not getattr(current_user, "email_verified", True):
        raise HTTPException(403, {"code": "email_non_confirme",
                                  "message": "Confirmez votre adresse email pour utiliser cette fonctionnalité."})
    return _aide(_par_compte(project_id, current_user, db), db, section_id, body)


@router.get(C + "/taches/{job_id}")
@limiter.limit("120/minute")
def compte_tache(project_id: int, job_id: int, request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return _tache(_par_compte(project_id, current_user, db), db, job_id)


@router.post(C + "/sections/{section_id}/envoyer")
@limiter.limit("60/hour")
def compte_envoyer(project_id: int, section_id: int, body: EnvoyerIn, request: Request,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _envoyer(_par_compte(project_id, current_user, db), db, section_id, body, _ip(request))


@router.post(C + "/sections/{section_id}/valider")
@limiter.limit("60/hour")
def compte_valider(project_id: int, section_id: int, body: ValiderIn, request: Request,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _valider(_par_compte(project_id, current_user, db), db, section_id, body, _ip(request))


@router.post(C + "/sections/{section_id}/retablir")
@limiter.limit("60/hour")
def compte_retablir(project_id: int, section_id: int, body: RetablirIn, request: Request,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _retablir(_par_compte(project_id, current_user, db), db, section_id, body, _ip(request))


@router.post(C + "/dossier/valider")
@limiter.limit("30/hour")
def compte_valider_dossier(project_id: int, request: Request, body: Optional[ValiderDossierIn] = None,
                           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _valider_dossier(_par_compte(project_id, current_user, db), db, body, _ip(request))


@router.get(C + "/export")
@limiter.limit("10/hour")
def compte_export(project_id: int, request: Request, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return _export(_par_compte(project_id, current_user, db), db)
