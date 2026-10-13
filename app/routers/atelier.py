"""
Router de l'ATELIER du dossier de présentation (rédaction, vague 2).

Contrat complet : docs/REDACTION_V2_API.md. Toute la logique est dans app/services/atelier.py ;
ici : contrôle d'accès (le marché doit appartenir à l'organisation de l'utilisateur, sinon 404),
lecture des corps de requête et traduction des erreurs métier en réponses HTTP structurées
(`detail` = {code, message, …}).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.http import content_disposition
from app.core.org import data_owner_id, member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import DossierSection, DossierSectionVersion, Job, Project, User
from app.services import atelier as at
from app.services import atelier_plan as ap

router = APIRouter(prefix="/api/atelier", tags=["Atelier du dossier de présentation"])


def _err(e: at.AtelierError):
    return HTTPException(e.status, e.detail())


def _nf(code: str, message: str):
    return HTTPException(404, {"code": code, "message": message})


class _Acces:
    def __init__(self, db: Session, user: User, project_id: int):
        self.db, self.user = db, user
        self.mids = member_ids(user, db)
        self.project = db.query(Project).filter(Project.id == project_id, Project.user_id.in_(self.mids)).first()
        if self.project is None:
            raise _nf("marche_introuvable", "Marché introuvable.")
        self.owner_id = data_owner_id(user, db)
        self.lecteur = at.Lecteur.organisation(self.owner_id, user)
        self.dossier = at.get_dossier(db, self.project.id, self.owner_id)

    def exiger_dossier(self):
        if self.dossier is None:
            raise _nf("dossier_introuvable", "Le dossier de présentation de ce marché n'est pas encore créé.")
        return self.dossier

    def section(self, sid: int, active: bool = True) -> DossierSection:
        d = self.exiger_dossier()
        s = self.db.get(DossierSection, sid)
        if s is None or s.dossier_id != d.id:
            raise _nf("partie_introuvable", "Partie introuvable.")
        if active and s.retiree_at is not None:
            raise HTTPException(409, {"code": "partie_retiree",
                                      "message": "Cette partie a été retirée du plan : remettez-la d'abord."})
        return s

    def contexte(self) -> at.Contexte:
        return at.Contexte(self.db, self.project, self.owner_id, self.mids)

    def etat(self) -> dict:
        return at.etat(self.db, self.project, self.exiger_dossier(), self.lecteur, self.mids)


def _section(acc: _Acces, s: DossierSection) -> dict:
    d = acc.exiger_dossier()
    act = at.sections_actives(acc.db, d)
    rang = at._rangs(d, act).get(s.id, "")
    return at.section_out(acc.db, d, s, rang, acc.lecteur, at.version_courante(acc.db, s), None)


# ── Le dossier ────────────────────────────────────────────────────────────────────────

@router.get("/{project_id}")
def lire(project_id: int, base: str = "auto", current_user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    """État complet de l'atelier ; sans dossier : le plan PROPOSÉ (rien n'est enregistré)."""
    acc = _Acces(db, current_user, project_id)
    if acc.dossier is None:
        prop = at.proposition(db, acc.project, acc.mids, base=base if base in ap.BASES else "auto")
        return {"dossier": None, "projet": {"id": acc.project.id, "nom": acc.project.name},
                "proposition": prop, "quota": at.quota_out(at.DossierPresentation(analyse_debitee=False,
                                                                                    regenerations=0,
                                                                                    regenerations_payantes=0))}
    return acc.etat()


class CreerIn(BaseModel):
    base: str = "auto"


@router.post("/{project_id}", status_code=201)
@limiter.limit("60/hour")
def creer(request: Request, project_id: int, body: Optional[CreerIn] = None,
          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    base = (body.base if body else "auto")
    if base not in ap.BASES:
        raise HTTPException(422, {"code": "base_invalide", "message": "Plan inconnu : auto, grille, cadre ou libre."})
    try:
        acc.dossier = at.creer_dossier(db, acc.project, acc.owner_id, current_user, acc.mids, base=base)
    except at.AtelierError as e:
        raise _err(e)
    return acc.etat()


class PlanIn(BaseModel):
    base: str = "auto"
    remplacer: bool = False


@router.post("/{project_id}/plan")
@limiter.limit("60/hour")
def reconstruire(request: Request, project_id: int, body: PlanIn, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    if body.base not in ap.BASES:
        raise HTTPException(422, {"code": "base_invalide", "message": "Plan inconnu : auto, grille, cadre ou libre."})
    try:
        at.reconstruire_plan(db, acc.project, acc.exiger_dossier(), current_user, acc.mids, base=body.base,
                             remplacer=body.remplacer, lecteur=acc.lecteur)
    except at.AtelierError as e:
        raise _err(e)
    return acc.etat()


@router.post("/{project_id}/plan/grille")
@limiter.limit("60/hour")
def appliquer_grille(request: Request, project_id: int, current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """« Comment vous serez noté » a changé depuis le plan : ajoute une partie par critère confirmé
    depuis et reprend les poids, SANS rien retirer ni reconstruire (aucune IA, aucun débit)."""
    acc = _Acces(db, current_user, project_id)
    try:
        res = at.appliquer_grille(db, acc.project, acc.exiger_dossier(), acc.lecteur)
    except at.AtelierError as e:
        raise _err(e)
    return dict(acc.etat(), application=res)


class OptionsIn(BaseModel):
    page_garde: Optional[bool] = None
    sommaire: Optional[bool] = None


@router.put("/{project_id}/options")
def options(project_id: int, body: OptionsIn, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    return {"options": at.definir_options(db, acc.exiger_dossier(), body.page_garde, body.sommaire)}


@router.get("/{project_id}/compteur")
def compteur(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    st = acc.etat()
    return {"compteur": st["compteur"], "sections": [{"id": s["id"], "titre": s["titre"], "compteur": s["compteur"]}
                                                     for s in st["sections"]],
            "limites": st["limites"], "blocage": st["blocage"]}


# ── Les parties ───────────────────────────────────────────────────────────────────────

class AjoutIn(BaseModel):
    intitule: str = Field(..., max_length=400)
    apres_section_id: Optional[int] = None


@router.post("/{project_id}/sections", status_code=201)
@limiter.limit("600/hour")
def ajouter(request: Request, project_id: int, body: AjoutIn, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    try:
        s = at.ajouter_section(db, acc.exiger_dossier(), body.intitule, body.apres_section_id)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


class ModifIn(BaseModel):
    intitule: Optional[str] = Field(None, max_length=400)
    position: Optional[int] = None


@router.patch("/{project_id}/sections/{section_id}")
@limiter.limit("600/hour")
def modifier(request: Request, project_id: int, section_id: int, body: ModifIn,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.modifier_section(db, acc.exiger_dossier(), s, acc.lecteur, intitule=body.intitule, position=body.position)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


@router.delete("/{project_id}/sections/{section_id}")
@limiter.limit("600/hour")
def retirer(request: Request, project_id: int, section_id: int, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.retirer_section(db, acc.exiger_dossier(), s, acc.lecteur)
    except at.AtelierError as e:
        raise _err(e)
    return {"ok": True, "section_id": s.id, "retiree": True}


@router.post("/{project_id}/sections/{section_id}/remettre")
@limiter.limit("600/hour")
def remettre(request: Request, project_id: int, section_id: int, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id, active=False)
    try:
        at.remettre_section(db, acc.exiger_dossier(), s, acc.lecteur)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


@router.get("/{project_id}/sections/{section_id}")
def lire_section(project_id: int, section_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Une partie et l'historique de ses versions (sans les textes : voir /versions/{id})."""
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id, active=False)
    out = _section(acc, s)
    if at.peut_voir_prive(s, acc.lecteur) or at.est_generee(s):
        # Partie tirée du groupement (vague 4) : toutes ses versions sont communes (aucune matière privée).
        out["versions"] = [at._version_out(v, False, texte=False) for v in at.versions(db, s)]
    else:
        out["versions"] = []
    return out


@router.get("/{project_id}/sections/{section_id}/versions/{version_id}")
def lire_version(project_id: int, section_id: int, version_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id, active=False)
    v = db.get(DossierSectionVersion, version_id)
    if v is None or v.section_id != s.id:
        raise _nf("version_introuvable", "Version introuvable.")
    if not at.peut_voir_prive(s, acc.lecteur) and v.id != s.validated_version_id and not bool(v.partage):
        # Matière privée d'un autre auteur (vague 4) : même réponse qu'une version inexistante. Un texte
        # COMMUN (envoyé par le partenaire, ou écrit par le chef de file sur sa partie) se lit, sans source.
        raise _nf("version_introuvable", "Version introuvable.")
    return at._version_out(v, at.peut_voir_prive(s, acc.lecteur))


class TexteIn(BaseModel):
    texte: str = Field("", max_length=at.TEXTE_MAX + 2000)
    base_version_id: Optional[int] = None


@router.put("/{project_id}/sections/{section_id}/texte")
@limiter.limit("1200/hour")
def ecrire(request: Request, project_id: int, section_id: int, body: TexteIn,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« J'écris moi-même » ou modification : une NOUVELLE version, aucune IA."""
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.enregistrer_texte(db, acc.contexte(), s, acc.lecteur, body.texte, body.base_version_id)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


class RestaurerIn(BaseModel):
    version_id: int
    base_version_id: Optional[int] = None


@router.post("/{project_id}/sections/{section_id}/restaurer")
@limiter.limit("600/hour")
def restaurer(request: Request, project_id: int, section_id: int, body: RestaurerIn,
              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.restaurer_version(db, acc.contexte(), s, acc.lecteur, body.version_id, body.base_version_id)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


class VersionIn(BaseModel):
    version_id: int


@router.post("/{project_id}/sections/{section_id}/relu")
@limiter.limit("600/hour")
def relu(request: Request, project_id: int, section_id: int, body: VersionIn,
         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.marquer_relu(db, s, acc.lecteur, body.version_id)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


@router.post("/{project_id}/sections/{section_id}/valider")
@limiter.limit("600/hour")
def valider(request: Request, project_id: int, section_id: int, body: VersionIn,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.audit import client_ip
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.valider(db, acc.project, s, acc.lecteur, body.version_id, ip=client_ip(request))
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


class FaitIn(BaseModel):
    statut: str


@router.post("/{project_id}/sections/{section_id}/faits/{fait_id}")
@limiter.limit("1200/hour")
def traiter_fait(request: Request, project_id: int, section_id: int, fait_id: str, body: FaitIn,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        fait = at.traiter_fait(db, s, acc.lecteur, fait_id[:40], body.statut)
    except at.AtelierError as e:
        raise _err(e)
    return {"fait": fait, "section": _section(acc, s)}


# ── Vague 3 (A) : « Chaque fait a sa source » — sans IA, sans toucher au texte ─────────

def _err_preuve(e):
    return HTTPException(e.status, e.detail())


@router.post("/{project_id}/sections/{section_id}/controle")
@limiter.limit("300/hour")
def recontroler(request: Request, project_id: int, section_id: int, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Relit les sources de la partie (une preuve ajoutée, retirée ou expirée), sans IA."""
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        at.recontroler(db, acc.contexte(), acc.project, s, acc.lecteur)
    except at.AtelierError as e:
        raise _err(e)
    return _section(acc, s)


@router.get("/{project_id}/sections/{section_id}/faits/{fait_id}/sources")
def sources_possibles(project_id: int, section_id: int, fait_id: str, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Pour « Ajouter une source » : les preuves qui contiennent ce fait et la fiche proposée."""
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        return at.candidats_source(db, acc.contexte(), s, acc.lecteur, fait_id[:40])
    except at.AtelierError as e:
        raise _err(e)


class SourceIn(BaseModel):
    preuve_id: Optional[int] = None
    nature: Optional[str] = None
    valeur: Optional[dict] = None


@router.post("/{project_id}/sections/{section_id}/faits/{fait_id}/source")
@limiter.limit("300/hour")
def ajouter_source(request: Request, project_id: int, section_id: int, fait_id: str, body: SourceIn,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Relie le fait à une preuve qui le contient, ou le déclare (nouvelle preuve « déclaré par
    vous ») ; puis la partie est recontrôlée. Jamais l'IA, jamais une modification du texte."""
    from app.services import preuves as pv
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    if body.preuve_id is None and not body.nature:
        raise HTTPException(422, {"code": "source_requise",
                                  "message": "Choisissez une preuve, ou déclarez ce fait avec une fiche."})
    try:
        fait = at.ajouter_source(db, acc.contexte(), acc.project, s, acc.lecteur, fait_id[:40],
                                 preuve_id=body.preuve_id, nature=body.nature, valeur=body.valeur or {},
                                 user=current_user)
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)
    except pv.PreuveError as e:
        db.rollback()
        raise _err_preuve(e)
    return {"fait": fait, "section": _section(acc, s)}


# ── Le moteur (tâches de fond) ────────────────────────────────────────────────────────

class RedigerIn(BaseModel):
    accepte_debit: bool = False


class RaccourcirIn(BaseModel):
    cible_mots: Optional[int] = None
    accepte_debit: bool = False


class RedigerToutIn(BaseModel):
    section_ids: Optional[List[int]] = None
    accepte_debit: bool = False


def _lancer(acc: _Acces, sections: list, action: str, cible=None, accepte_debit=False) -> dict:
    if not getattr(acc.user, "email_verified", True):
        raise HTTPException(403, {"code": "email_non_confirme",
                                  "message": "Confirmez votre adresse email pour utiliser cette fonctionnalité."})
    try:
        job = at.lancer(acc.db, acc.user, acc.project, acc.exiger_dossier(), sections, action, acc.lecteur, acc.mids,
                        cible=cible, accepte_debit=accepte_debit)
    except at.AtelierError as e:
        raise _err(e)
    acc.db.refresh(acc.dossier)
    return {"tache": at.job_public(job), "quota": at.quota_out(acc.dossier),
            "section_ids": [s.id for s in sections]}


@router.post("/{project_id}/sections/{section_id}/rediger", status_code=202)
@limiter.limit("60/hour")
def rediger(request: Request, project_id: int, section_id: int, body: Optional[RedigerIn] = None,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Rédiger avec Adjugo » une partie (tâche de fond : suivre /taches/{job_id})."""
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    return _lancer(acc, [s], at.JOB_REDIGER, accepte_debit=bool(body and body.accepte_debit))


@router.post("/{project_id}/sections/{section_id}/raccourcir", status_code=202)
@limiter.limit("60/hour")
def raccourcir(request: Request, project_id: int, section_id: int, body: Optional[RaccourcirIn] = None,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    s = acc.section(section_id)
    return _lancer(acc, [s], at.JOB_RACCOURCIR, cible=(body.cible_mots if body else None),
                   accepte_debit=bool(body and body.accepte_debit))


@router.post("/{project_id}/rediger", status_code=202)
@limiter.limit("30/hour")
def rediger_tout(request: Request, project_id: int, body: Optional[RedigerToutIn] = None,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rédige plusieurs parties d'un coup (par défaut : toutes celles « à écrire »)."""
    acc = _Acces(db, current_user, project_id)
    d = acc.exiger_dossier()
    act = at.sections_actives(db, d)
    if body and body.section_ids:
        want = set(body.section_ids)
        secs = [s for s in act if s.id in want]
        if len(secs) != len(want):
            raise _nf("partie_introuvable", "Partie introuvable.")
    else:
        secs = [s for s in act if s.statut == at.A_ECRIRE and at.peut_ecrire(s, acc.lecteur)]
    if not secs:
        raise HTTPException(422, {"code": "aucune_partie", "message": "Aucune partie à rédiger."})
    return _lancer(acc, secs, at.JOB_REDIGER, accepte_debit=bool(body and body.accepte_debit))


@router.get("/{project_id}/taches/{job_id}")
def tache(project_id: int, job_id: int, current_user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    acc = _Acces(db, current_user, project_id)
    # Jamais la tâche d'un partenaire (vague 4 : portée « partenaire », aucun compte propriétaire).
    j = db.query(Job).filter(Job.id == job_id, Job.user_id.in_(acc.mids), Job.kind.in_(at.JOB_KINDS),
                             or_(Job.portee.is_(None), Job.portee != "partenaire")).first()
    d = acc.dossier
    debit = ((j.result or {}).get("_debit") or {}) if j is not None and isinstance(j.result, dict) else {}
    if j is None or d is None or int(debit.get("dossier_id") or 0) != d.id:
        raise _nf("tache_introuvable", "Cette tâche est introuvable.")
    return at.job_public(j)


# ── Blocage, dérogation, export ───────────────────────────────────────────────────────

class DerogationIn(BaseModel):
    raison: str
    texte: str = Field("", max_length=600)
    etat_hash: str = Field(..., max_length=64)


@router.post("/{project_id}/derogation")
@limiter.limit("60/hour")
def deroger(request: Request, project_id: int, body: DerogationIn, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    from app.services.audit import client_ip
    acc = _Acces(db, current_user, project_id)
    st = acc.etat()
    try:
        der = at.enregistrer_derogation(db, acc.project, acc.dossier, st["blocage"], acc.lecteur, body.raison,
                                        body.texte, body.etat_hash, ip=client_ip(request))
    except at.AtelierError as e:
        raise _err(e)
    return {"derogation": der, "blocage": acc.etat()["blocage"]}


class ExportIn(BaseModel):
    format: str = "docx"
    etat_hash: Optional[str] = Field(None, max_length=64)


@router.post("/{project_id}/export")
@limiter.limit("60/hour")
def exporter(request: Request, project_id: int, body: ExportIn, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Le fichier Word ou PDF (octets) — ou 409 « export_bloque » avec les raisons."""
    from app.core.demo_guard import refuser_demo
    from app.services.audit import client_ip
    # Défense en profondeur : l'export range le fichier dans le dossier du marché (vitrine partagée).
    refuser_demo(current_user, "préparer votre dossier de présentation")
    acc = _Acces(db, current_user, project_id)
    try:
        data, nom, mime = at.exporter(db, current_user, acc.project, acc.exiger_dossier(), body.format, acc.lecteur,
                                      etat=body.etat_hash, ip=client_ip(request))
    except at.AtelierError as e:
        raise _err(e)
    return Response(content=data, media_type=mime, headers={"Content-Disposition": content_disposition(nom)})
