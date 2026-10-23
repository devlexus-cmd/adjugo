"""
Adjugo - Router criteres de matching etendus
Stocke les criteres supplementaires en JSON pour flexibilite.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, Float, String, JSON, ForeignKey, Boolean, false as sa_false
from pydantic import BaseModel, field_validator
from typing import Optional
from app.core.database import get_db, Base
from app.core.security import get_current_user
from app.core.org import data_owner_id
from app.models import User

# Modele etendu
try:
    from app.models import MatchingCriteria as ExistingCriteria
except ImportError:
    ExistingCriteria = None


class MatchingCriteriaExt(Base):
    __tablename__ = "matching_criteria_ext"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    # Budget
    budget_min = Column(Float, default=10000)
    budget_max = Column(Float, default=500000)
    ca_ratio_max = Column(Float, default=30)
    avance_min = Column(Float, default=5)
    delai_paiement_max = Column(Integer, default=60)
    # Geographie
    max_distance_km = Column(Integer, default=100)
    departements = Column(String, default="")
    regions = Column(String, default="")
    # Types
    types_marche = Column(String, default="Travaux, Services")
    procedures_acceptees = Column(String, default="MAPA, AOO")
    lot_min = Column(Float, default=5000)
    codes_cpv = Column(String, default="")
    # Technique
    qualifications = Column(String, default="")
    certifications = Column(String, default="")
    specialites = Column(String, default="")
    effectif_max_marche = Column(Integer, default=0)
    # Risques
    penalty_max = Column(Float, default=10)
    garantie_max = Column(Float, default=5)
    retenue_garantie_max = Column(Float, default=5)
    delai_reponse_min = Column(Integer, default=15)
    excluded_keywords = Column(String, default="")
    # Seuils
    go_threshold = Column(Integer, default=75)
    nogo_threshold = Column(Integer, default=40)
    # Montant que je porte seul (€ HT), réorganisation vague 2a (A3) : le plus gros marché, ou la plus grosse partie
    # d'un marché, que l'entreprise réalise seule, DÉCLARÉ par elle. VIDE par défaut (NULL), jamais déduit de
    # budget_max (500 000 € par défaut, une fourchette de préférence) ni d'un autre champ. Aujourd'hui il n'entre dans
    # aucun calcul (ni classement, ni note, ni filtre, ni consigne de l'IA) : l'étude ne s'en sert que pour signaler
    # « à plusieurs » quand une partie dépasse ce montant (innovation A du moteur, derrière un interrupteur). Migration
    # c4montantseul. Contrat : docs/REORGANISATION_V2A.md, section A3.
    montant_porte_seul = Column(Float, nullable=True)
    # « Je ne sais pas » (réorganisation, vague 2b, B1 ; migration c5priseenmain) : l'entreprise a répondu à la question
    # « Jusqu'à quel montant répondez-vous seul ? » sans donner de montant. Distinct d'un champ VIDE (jamais répondu) ;
    # jamais vrai en même temps qu'un montant. Comme le montant, il n'entre dans aucun calcul : la liste d'activation
    # (« Dire ce que vous faites et où », app/services/prise_en_main.py) lit seulement qu'une réponse a été donnée.
    montant_porte_seul_inconnu = Column(Boolean, default=False, nullable=True, server_default=sa_false())


MONTANT_SEUL_MAX = 10_000_000_000      # 10 milliards d'euros HT : au-delà, une faute de frappe


class CriteriaUpdate(BaseModel):
    budget_min: Optional[float] = 10000
    budget_max: Optional[float] = 500000
    ca_ratio_max: Optional[float] = 30
    avance_min: Optional[float] = 5
    delai_paiement_max: Optional[int] = 60
    max_distance_km: Optional[int] = 100
    departements: Optional[str] = ""
    regions: Optional[str] = ""
    types_marche: Optional[str] = "Travaux, Services"
    procedures_acceptees: Optional[str] = "MAPA, AOO"
    lot_min: Optional[float] = 5000
    codes_cpv: Optional[str] = ""
    qualifications: Optional[str] = ""
    certifications: Optional[str] = ""
    specialites: Optional[str] = ""
    effectif_max_marche: Optional[int] = 0
    penalty_max: Optional[float] = 10
    garantie_max: Optional[float] = 5
    retenue_garantie_max: Optional[float] = 5
    delai_reponse_min: Optional[int] = 15
    excluded_keywords: Optional[str] = ""
    go_threshold: Optional[int] = 75
    nogo_threshold: Optional[int] = 40
    # Vide par défaut ; envoyé vide (None), il est EFFACÉ ; absent de la requête (ancienne page), il est gardé.
    montant_porte_seul: Optional[float] = None
    # « Je ne sais pas » (vague 2b) : vrai efface le montant ; un montant donné le remet à faux ; absent, il est gardé.
    montant_porte_seul_inconnu: Optional[bool] = None

    # Un champ numérique laissé VIDE dans le formulaire arrive en "" (v-model.number)
    # → Pydantic refusait tout l'enregistrement (422). On accepte le vide = None,
    # et l'endpoint conserve alors la valeur existante / le défaut (jamais d'erreur).
    @field_validator("budget_min", "budget_max", "ca_ratio_max", "avance_min",
                     "delai_paiement_max", "max_distance_km", "lot_min",
                     "effectif_max_marche", "penalty_max", "garantie_max",
                     "retenue_garantie_max", "delai_reponse_min",
                     "go_threshold", "nogo_threshold", "montant_porte_seul", mode="before")
    @classmethod
    def _empty_num_to_none(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, float) and v != v:   # NaN
            return None
        return v


router = APIRouter(prefix="/api/criteria", tags=["Criteres de matching"])


def _criteres_out(c) -> dict:
    """Les critères tels que la page les lit (ligne absente : les valeurs par défaut). « Je ne sais pas » est toujours un
    booléen (jamais None) : faux tant que l'entreprise ne l'a pas choisi."""
    result = CriteriaUpdate().model_dump() if c is None else {f: getattr(c, f, None) for f in CriteriaUpdate.model_fields}
    result["montant_porte_seul_inconnu"] = bool(result.get("montant_porte_seul_inconnu"))
    return result


def ce_que_je_cherche_dit(db: Session, owner_id: int) -> dict:
    """Pour la liste d'activation (réorganisation, vague 2b, B1 ; app/services/prise_en_main.py) : l'entreprise a-t-elle
    dit son métier, sa zone et ce qu'elle porte seule ? Lecture seule, rien n'est déduit : métier = spécialités ou
    codes CPV saisis ; zone = départements saisis ; montant = un montant donné OU « Je ne sais pas » coché. Ce n'est
    pas un calcul sur le montant (il n'entre toujours dans aucun classement, aucune note, aucun filtre)."""
    c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == owner_id).first()
    if c is None:
        return {"metier": False, "zone": False, "montant": False}
    txt = lambda v: bool(str(v or "").strip())
    return {"metier": txt(c.specialites) or txt(c.codes_cpv), "zone": txt(c.departements),
            "montant": c.montant_porte_seul is not None or bool(c.montant_porte_seul_inconnu)}


@router.get("/")
def get_criteria(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == data_owner_id(current_user, db)).first()
    return _criteres_out(c)


@router.put("/")
def update_criteria(data: CriteriaUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "régler vos critères")      # défense en profondeur (middleware démo)
    seul = data.montant_porte_seul
    if seul is not None and not (0 <= seul <= MONTANT_SEUL_MAX):
        raise HTTPException(400, "Le montant que vous portez seul est un montant positif, en euros HT.")
    c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == data_owner_id(current_user, db)).first()
    if not c:
        c = MatchingCriteriaExt(user_id=data_owner_id(current_user, db))
        db.add(c)
    for k, v in data.model_dump().items():
        if k == "montant_porte_seul":
            # Seulement s'il est dans la requête : vide (None) l'efface, une valeur la remplace. Une page plus ancienne
            # qui ne l'envoie pas ne l'efface jamais.
            if k in data.model_fields_set:
                c.montant_porte_seul = v
            continue
        if k == "montant_porte_seul_inconnu":
            if k in data.model_fields_set and v is not None:
                c.montant_porte_seul_inconnu = bool(v)
            continue
        if v is None:
            # Champ TEXTE explicitement vidé → on l'EFFACE (l'utilisateur doit pouvoir
            # retirer ses spécialités/départements/CPV). Champ numérique laissé vide → on
            # garde la valeur en place / le défaut (un nombre ne se « vide » pas en base).
            if "str" in str(CriteriaUpdate.model_fields[k].annotation):
                setattr(c, k, "")
            elif k in ("go_threshold", "nogo_threshold"):
                # Seuil vidé : le défaut que dit le champ vide (« 75 (défaut) », « 40 (défaut) »), pas l'ancienne
                # valeur gardée en silence (contrôle des bugs, 22/10).
                setattr(c, k, CriteriaUpdate.model_fields[k].default)
            continue
        setattr(c, k, v)
    # Une seule réponse à la fois (vague 2b) : un montant donné retire « Je ne sais pas » ; « Je ne sais pas » coché (sans
    # montant dans la même requête) efface le montant. Une page qui n'envoie ni l'un ni l'autre ne change rien.
    if c.montant_porte_seul is not None and "montant_porte_seul" in data.model_fields_set:
        c.montant_porte_seul_inconnu = False
    elif c.montant_porte_seul_inconnu:
        c.montant_porte_seul = None
    db.commit()
    db.refresh(c)
    return _criteres_out(c)
