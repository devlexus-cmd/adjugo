from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime
from pydantic import BaseModel, field_validator
from typing import Optional, List
from app.core.database import get_db, Base
from app.core.security import get_current_user
from app.core.org import member_ids
from app.services.dce_scoring import _dept   # Corse 2A/2B & DOM-TOM 97x à l'import d'un partenaire
from app.models import User

class Cotraitant(Base):
    __tablename__ = "cotraitants"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    siret = Column(String)
    code_ape = Column(String)
    forme_juridique = Column(String)
    representant_legal = Column(String)
    address = Column(String)
    postal_code = Column(String)
    city = Column(String)
    email = Column(String)
    phone = Column(String)
    tva_intracom = Column(String)
    ca_n1 = Column(Float, default=0)
    ca_n2 = Column(Float, default=0)
    ca_n3 = Column(Float, default=0)
    effectif = Column(Integer, default=0)
    qualifications = Column(String)
    # Champs de matching (moteur de suggestion de co-traitance)
    specialites = Column(String, default="")   # "Électricité, CFO/CFA, Domotique"
    codes_cpv = Column(String, default="")      # "45310000, 45315100"
    departement = Column(String, default="")    # "29"
    # ── Capacités étiquetées (score de groupement) ──
    # D'où viennent ca_n1/effectif/qualifications de ce partenaire ? 'declare' = saisi par
    # l'utilisateur SUR son partenaire (étiquette « déclaré par vous le … ») · 'rne' = vérifié
    # SIRENE/RNE · 'contribution' = déclaré par le partenaire lui-même dans sa part · 'reseau'.
    references = Column(JSON, default=list)
    capacites_source = Column(String(20), default="declare")
    capacites_updated_at = Column(DateTime, nullable=True)


class ProjectCotraitant(Base):
    """Liaison sous-traitant ↔ appel d'offres (un co-traitant du réseau peut
    être rattaché à plusieurs AO, un AO a plusieurs sous-traitants)."""
    __tablename__ = "project_cotraitants"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    cotraitant_id = Column(Integer, ForeignKey("cotraitants.id"))
    role = Column(String, default="sous_traitant")   # mandataire | cotraitant | sous_traitant
    lot = Column(String, default="")
    # Métrique de moat : d'où vient ce partenaire ?
    #   "discover" = suggéré par Adjugo (découverte SIRENE) · "reseau" = carnet d'adresses du Client
    #   "simulation" = retenu depuis « Répondre à plusieurs ? » · "reseau_adjugo" (vague 3)
    source = Column(String, default="reseau")
    # UNIFICATION « membre du groupement » : un rattachement SANS invite_id est un CANDIDAT
    # retenu ; dès que l'invitation est créée, invite_id est posé et l'invitation ACTIVE
    # (revoked=false ET declined_at IS NULL) devient LE membre (cf. groupement_members).
    invite_id = Column(Integer, nullable=True, index=True)


class CotraitantCreate(BaseModel):
    name: str
    siret: Optional[str] = ""
    code_ape: Optional[str] = ""
    forme_juridique: Optional[str] = ""
    representant_legal: Optional[str] = ""
    address: Optional[str] = ""
    postal_code: Optional[str] = ""
    city: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    tva_intracom: Optional[str] = ""
    ca_n1: Optional[float] = 0
    ca_n2: Optional[float] = 0
    ca_n3: Optional[float] = 0
    effectif: Optional[int] = 0
    qualifications: Optional[str] = ""
    specialites: Optional[str] = ""
    codes_cpv: Optional[str] = ""
    departement: Optional[str] = ""
    # Score de groupement : références + provenance des capacités (ca_n1/effectif/qualifs).
    references: Optional[list] = None
    capacites_source: Optional[str] = None   # declare | rne | contribution | reseau (défaut 'declare')

    @field_validator("siret")
    @classmethod
    def _validate_siret(cls, v):
        return _clean_siret(v)

    @field_validator("capacites_source")
    @classmethod
    def _validate_source(cls, v):
        if v in (None, ""):
            return None
        if v not in CAPACITES_SOURCES:
            raise ValueError("capacites_source doit valoir declare, rne, contribution ou reseau.")
        return v


CAPACITES_SOURCES = ("declare", "rne", "contribution", "reseau")
_CAPACITY_FIELDS = ("ca_n1", "effectif", "qualifications")


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean_siret(v):
    """Normalise (sans espaces/points) ET valide un SIRET. Renvoie la forme CANONIQUE —
    stockée et comparée telle quelle, sinon deux écritures du même SIRET (« 123 456… » vs
    « 123456… ») créaient des doublons et un SIRET non conforme s'imprimait sur les CERFA."""
    if not v:
        return ""
    s = str(v).replace(" ", "").replace(".", "").strip()
    if s.isdigit() and len(s) != 14:
        raise ValueError("Le SIRET doit comporter exactement 14 chiffres.")
    return s

router = APIRouter(prefix="/api/cotraitants", tags=["Co-traitants"])


def _refuser_demo(user) -> None:
    """Défense en profondeur (middleware démo) : les partenaires de la vitrine partagée et leurs
    rattachements aux marchés ne changent pas (le groupement de Kerhel en dépend). Ajouter un
    partenaire reste permis : la remise à neuf automatique l'efface entre deux présentations."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(user, "gérer vos partenaires")

@router.get("/")
def list_cotraitants(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Cotraitant).filter(Cotraitant.user_id.in_(member_ids(current_user, db))).all()

@router.post("/")
def create_cotraitant(data: CotraitantCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = data.model_dump()
    # Capacités saisies par l'utilisateur SUR son partenaire → 'declare' (étiquette « déclaré
    # par vous le … »), sauf provenance explicite ('rne' = vérifié SIRENE, etc.).
    payload["references"] = payload.get("references") or []
    payload["capacites_source"] = payload.get("capacites_source") or "declare"
    ct = Cotraitant(user_id=current_user.id, capacites_updated_at=_utcnow(), **payload)
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct

@router.put("/{ct_id}")
def update_cotraitant(ct_id: int, data: CotraitantCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    ct = db.query(Cotraitant).filter(Cotraitant.id == ct_id, Cotraitant.user_id.in_(member_ids(current_user, db))).first()
    if not ct:
        raise HTTPException(404, "Partenaire introuvable")
    # exclude_unset : un PUT partiel ne réécrit plus les champs non transmis avec leur défaut.
    changes = data.model_dump(exclude_unset=True)
    explicit_source = changes.pop("capacites_source", None)
    if "references" in changes and changes["references"] is None:
        changes["references"] = []
    caps_changed = any(k in changes and changes[k] != getattr(ct, k) for k in _CAPACITY_FIELDS)
    for k, v in changes.items():
        setattr(ct, k, v)
    # Les capacités ont changé à la main → elles redeviennent « déclarées par vous », datées
    # (sauf provenance explicite, ex. 'rne' après une re-vérification SIRENE).
    if explicit_source:
        ct.capacites_source = explicit_source
        ct.capacites_updated_at = _utcnow()
    elif caps_changed:
        ct.capacites_source = "declare"
        ct.capacites_updated_at = _utcnow()
    db.commit()
    db.refresh(ct)
    return ct


@router.delete("/{ct_id}")
def delete_cotraitant(ct_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    ct = db.query(Cotraitant).filter(Cotraitant.id == ct_id, Cotraitant.user_id.in_(member_ids(current_user, db))).first()
    if not ct:
        raise HTTPException(404, "Partenaire introuvable")
    # On purge les liaisons aux AO (sinon ProjectCotraitant pointe vers un partenaire supprimé).
    link_ids = [lk.id for lk in db.query(ProjectCotraitant).filter(ProjectCotraitant.cotraitant_id == ct.id).all()]
    _release_convention_links(db, link_ids, current_user)
    db.query(ProjectCotraitant).filter(ProjectCotraitant.cotraitant_id == ct.id).delete()
    db.delete(ct)
    db.commit()
    return {"ok": True}


def _release_convention_links(db: Session, link_ids: list, user) -> None:
    """Un partenaire « hors ligne » d'une convention de groupement ne peut pas disparaître en
    silence : la convention concernée devient caduque (composition modifiée) et sa ligne
    d'accord est retirée (sinon la clé étrangère bloquerait la suppression)."""
    if not link_ids:
        return
    try:
        from app.models import GroupementSignature, Project
        from app.services.groupement_convention import perimer
        rows = db.query(GroupementSignature).filter(GroupementSignature.cotraitant_link_id.in_(link_ids)).all()
        for pid in {r.project_id for r in rows}:
            p = db.query(Project).filter(Project.id == pid).first()
            if p is not None:
                perimer(db, p, "partenaire hors ligne retiré du marché", actor=f"user:{user.id}", actor_kind="owner")
        db.query(GroupementSignature).filter(GroupementSignature.cotraitant_link_id.in_(link_ids)).delete(
            synchronize_session=False)
        db.flush()
    except Exception:
        pass


# ── Sous-traitants rattachés à un appel d'offres ─────────────────────────────────

ATTACH_PARTENAIRE_REFUS = ("Un partenaire du groupement s'invite depuis la page du marché : il n'entre dans "
                           "les formulaires officiels qu'après avoir accepté. Ici, seul un sous-traitant "
                           "(DC4) peut être ajouté.")


class AttachRequest(BaseModel):
    cotraitant_id: Optional[int] = None      # depuis le réseau existant
    company: Optional[dict] = None           # ou une entreprise réelle (SIRENE) à créer + lier
    role: Optional[str] = "sous_traitant"
    lot: Optional[str] = ""


def _own_project(project_id, user, db):
    from app.models import Project
    p = db.query(Project).filter(Project.id == project_id,
                                 Project.user_id.in_(member_ids(user, db))).first()
    if not p:
        raise HTTPException(404, "Appel d'offres introuvable")
    return p


@router.get("/project/{project_id}")
def list_project_cotraitants(project_id: int, current_user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    _own_project(project_id, current_user, db)
    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id).all()
    # Une seule requête (pas une par lien) + cloisonnement : le partenaire affiché doit
    # appartenir au réseau de l'organisation, comme partout ailleurs.
    ids = member_ids(current_user, db)
    cts = {c.id: c for c in db.query(Cotraitant).filter(
        Cotraitant.id.in_([lk.cotraitant_id for lk in links] or [0]),
        Cotraitant.user_id.in_(ids)).all()}
    # « formulaires » : l'entreprise figure-t-elle dans les formulaires officiels (sous-traitant déclaré,
    # ou partenaire dont l'invitation est acceptée) ? Faux = pas encore d'accord, l'écran propose d'inviter.
    # « invitation » : acceptee | envoyee | declinee | retiree | None (l'écran propose d'inviter à nouveau
    # après un refus ou un retrait) ; « accord_hors_ligne » : accord déclaré par le chef de file.
    from app.services.groupement_members import etat_des_liens
    etats = etat_des_liens(db, project_id)
    out = []
    for lk in links:
        ct = cts.get(lk.cotraitant_id)
        if not ct:
            continue
        e = etats.get(lk.id) or {}
        out.append({"link_id": lk.id, "role": lk.role, "lot": lk.lot,
                    "formulaires": bool(e.get("formulaires")), "invitation": e.get("invitation"),
                    "accord_hors_ligne": bool(e.get("accord_hors_ligne")),
                    "hors_ligne_en_attente": bool(e.get("hors_ligne_en_attente")),
                    "invite_id": getattr(lk, "invite_id", None), "source": lk.source or "reseau",
                    "id": ct.id, "name": ct.name, "siret": ct.siret, "code_ape": ct.code_ape,
                    "city": ct.city, "departement": ct.departement, "specialites": ct.specialites,
                    "effectif": ct.effectif, "ca_n1": ct.ca_n1, "qualifications": ct.qualifications or "",
                    "capacites_source": ct.capacites_source or "declare",
                    "capacites_updated_at": ct.capacites_updated_at.isoformat() if ct.capacites_updated_at else None})
    return out


@router.post("/project/{project_id}")
def attach_cotraitant(project_id: int, req: AttachRequest,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    _own_project(project_id, current_user, db)
    # Étude organisation, décision 4 : ajouter directement une entreprise au marché, c'est DÉCLARER UN
    # SOUS-TRAITANT (DC4). Un partenaire du groupement (ou un chef de file) s'invite : il n'entre dans
    # les formulaires officiels qu'après avoir accepté. Plus aucun rattachement sans accord.
    if (req.role or "sous_traitant") != "sous_traitant":
        raise HTTPException(422, ATTACH_PARTENAIRE_REFUS)

    # 1) Résoudre / créer le co-traitant (réseau)
    ids = member_ids(current_user, db)
    ct = None
    if req.cotraitant_id:
        ct = db.query(Cotraitant).filter(Cotraitant.id == req.cotraitant_id,
                                         Cotraitant.user_id.in_(ids)).first()
        if not ct:
            raise HTTPException(404, "Partenaire introuvable")
    elif req.company:
        c = req.company
        # Même validation/normalisation que le chemin Pydantic : le SIRET arrive ici en dict
        # libre (découverte SIRENE) et alimente les CERFA DC1/DC2/DC4 → il doit être conforme.
        try:
            siret = _clean_siret(c.get("siret"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if siret:
            ct = db.query(Cotraitant).filter(Cotraitant.user_id.in_(ids),
                                             Cotraitant.siret == siret).first()
        if not ct:
            ct = Cotraitant(user_id=current_user.id, name=c.get("name") or c.get("nom") or "Sous-traitant",
                            siret=siret, code_ape=c.get("code_ape") or c.get("naf"),
                            city=c.get("city") or c.get("ville"),
                            departement=(_dept(c.get("postal_code") or c.get("code_postal") or "")
                                         or c.get("departement") or ""),   # Corse/DOM-TOM corrects

                            specialites=c.get("specialites") or c.get("naf_label") or "",
                            effectif=c.get("effectif") or 0,
                            # Découverte SIRENE : effectif du registre → capacités « vérifiées
                            # SIRENE le … » (jamais un CA : non publié = à demander).
                            references=[], capacites_source="rne", capacites_updated_at=_utcnow())
            db.add(ct); db.commit(); db.refresh(ct)
    else:
        raise HTTPException(400, "Indiquez le partenaire (cotraitant_id) ou le nom de l'entreprise (company).")

    # 2) Éviter un doublon de liaison
    exists = db.query(ProjectCotraitant).filter(
        ProjectCotraitant.project_id == project_id,
        ProjectCotraitant.cotraitant_id == ct.id).first()
    if exists:
        # Un partenaire INVITÉ ne devient pas sous-traitant en silence (son invitation porte son rôle).
        if getattr(exists, "invite_id", None) and (exists.role or "") != "sous_traitant":
            raise HTTPException(409, "Cette entreprise est invitée comme partenaire de ce marché : "
                                     "son rôle se règle depuis son invitation.")
        exists.role = "sous_traitant"
        exists.lot = req.lot or exists.lot
        db.commit()
        return {"link_id": exists.id, "cotraitant_id": ct.id, "name": ct.name}

    # Provenance pour la métrique de moat : une entreprise fournie via `company`
    # vient de la découverte SIRENE (suggérée par Adjugo) ; via `cotraitant_id`, du réseau.
    link_source = "discover" if (req.company and not req.cotraitant_id) else "reseau"
    link = ProjectCotraitant(project_id=project_id, cotraitant_id=ct.id,
                             role=req.role or "sous_traitant", lot=req.lot or "", source=link_source)
    db.add(link); db.commit(); db.refresh(link)
    return {"link_id": link.id, "cotraitant_id": ct.id, "name": ct.name}


@router.delete("/project/{project_id}/{link_id}")
def detach_cotraitant(project_id: int, link_id: int,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    _own_project(project_id, current_user, db)
    link = db.query(ProjectCotraitant).filter(ProjectCotraitant.id == link_id,
                                              ProjectCotraitant.project_id == project_id).first()
    if not link:
        raise HTTPException(404, "Liaison introuvable")
    _release_convention_links(db, [link.id], current_user)
    db.delete(link); db.commit()
    return {"ok": True}
