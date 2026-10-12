"""
L'ATELIER du dossier de présentation (rédaction, vague 2 — étude §6.4 G + A0).

Le « mémoire technique » de l'acheteur, rédigé section par section, relu, corrigé, validé puis
exporté en Word et en PDF. Ce module porte toute la logique serveur ; le routeur
(app/routers/atelier.py) ne fait que contrôler l'accès et traduire les erreurs.

Doctrine (étude §7) appliquée ici :
  • un fait ne vient jamais de l'IA : l'IA reçoit la LISTE DES FAITS AUTORISÉS (savoir-faire,
    profil, équipe — noms masqués —, chiffrage sans prix, apports soumis des partenaires) ; tout
    autre fait doit être écrit « [À compléter : …] ». Après chaque texte, un contrôle SANS IA
    (app/services/faits_a_relire.py) renvoie « à relire » tout chiffre, certification, nom propre
    ou matériel absent de ces sources. Le dossier de l'acheteur n'en fait JAMAIS partie ;
  • le cadre de l'acheteur commande : le plan suit le cadre imposé ou la grille retrouvée dans le
    règlement (app/services/atelier_plan.py) ; jamais de critère, de poids ni d'ordre inventés ;
  • le dirigeant reste l'auteur : chaque texte est une NOUVELLE version (aucune n'est jamais
    effacée) ; une partie validée puis modifiée repasse « à revalider » ;
  • rien d'interne ne part chez l'acheteur : l'export est refusé tant qu'il reste un
    « [À compléter] », un fait à relire non traité, une partie vide ou une limite dépassée, sauf
    dérogation explicite enregistrée au journal chaîné (décision 2b) ;
  • la matière PRIVÉE d'une partie (sources, extraits, faits à relire, versions de travail) n'est
    lue que par son AUTEUR (`peut_voir_prive`) : aujourd'hui l'organisation, demain (vague 4) un
    membre du groupement par son invitation ;
  • quota (décision 6a) : le dossier complet compte pour UNE analyse, débitée à la première action
    de l'IA ; refaire une partie est gratuit jusqu'à ATELIER_REGEN_GRATUITES fois par dossier
    (défaut 10), au-delà chaque nouvelle rédaction compte pour une analyse, après accord exprès.
    Remboursement si l'IA tombe en panne. Le coût réel est mesuré (cost_meter) et cumulé sur le
    dossier (jamais montré au client) ;
  • mention « Préparé avec assistance IA » dans les propriétés du fichier SEULEMENT si l'IA a
    réellement servi (décision 9a), annoncée avant l'export.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified

from app.models import (Company, DossierPresentation, DossierSection, DossierSectionVersion, Job, Project,
                        User, utcnow)
from app.services import atelier_export as ax
from app.services import atelier_plan as ap
from app.services import faits_a_relire as far
from app.services import memoire_export as me

logger = logging.getLogger("adjugo")

# ── Constantes ────────────────────────────────────────────────────────────────────────

A_ECRIRE, BROUILLON, RELU, VALIDE, A_REVALIDER = "a_ecrire", "brouillon", "relu", "valide", "a_revalider"
STATUTS = {A_ECRIRE: "À écrire", BROUILLON: "Brouillon", RELU: "Relu", VALIDE: "Validé",
           A_REVALIDER: "À revalider"}
IA, UTILISATEUR, RACCOURCI = "ia", "utilisateur", "raccourci"
ORIGINES = {IA: "Rédigé avec Adjugo", UTILISATEUR: "Écrit ou modifié par vous", RACCOURCI: "Raccourci avec Adjugo"}
AUTEUR_ORG, AUTEUR_INVITATION = "organisation", "invitation"

TEXTE_MAX = 60000              # caractères par partie
INTITULE_MAX = 200
SECTIONS_MAX = 60
DOSSIER_ACHETEUR_MAX = 80000   # texte du dossier de l'acheteur remis à l'IA (règlement + cadre en tête)
CADRE_MAX = 60000
LECTURE_MAX = 120000           # lecture d'une pièce (comme l'import)

JOB_REDIGER = "atelier_rediger"
JOB_RACCOURCIR = "atelier_raccourcir"
JOB_KINDS = (JOB_REDIGER, JOB_RACCOURCIR)

MSG_IA_PANNE = ("La rédaction n'a pas abouti : le service d'IA est indisponible pour le moment. Rien n'a été "
                "débité, réessayez dans quelques minutes.")
MSG_IRREGULIERE = "L'acheteur peut juger votre offre irrégulière."
MSG_DCE_CHANGE = ("Le dossier du marché a été importé de nouveau depuis la création du plan : vous pouvez "
                  "reconstruire le plan.")
MSG_NON_VALIDE = "Dossier de présentation non validé"

# Dérogation à l'export (décision 2b) : une raison choisie + un texte libre court.
RAISONS_DEROGATION = {
    "completerai_dans_word": "Je compléterai ces passages dans le fichier Word avant de déposer.",
    "relu_moi_meme": "J'ai relu ces faits moi-même.",
    "depot_en_l_etat": "Je dépose en l'état, en connaissance de cause.",
    "autre": "Autre raison.",
}
DEROGATION_TEXTE_MIN, DEROGATION_TEXTE_MAX = 3, 300


def regen_gratuites() -> int:
    """Refaire une partie : gratuit jusqu'à ce plafond par dossier (décision 6a). Réglable par la
    variable d'environnement ATELIER_REGEN_GRATUITES (défaut 10 ; 5 si le coût mesuré l'impose)."""
    try:
        return max(0, int(os.getenv("ATELIER_REGEN_GRATUITES", "10")))
    except ValueError:
        return 10


class AtelierError(Exception):
    """Erreur métier, affichable telle quelle (status HTTP, code stable, message, détails)."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def detail(self) -> dict:
        return dict(self.extra, code=self.code, message=self.message)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(microsecond=0).isoformat()


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normaliser_texte(t) -> str:
    s = _CTRL.sub("", str(t or "").replace("\r\n", "\n").replace("\r", "\n"))
    return s.strip()


def empreinte(texte: str) -> str:
    return hashlib.sha256(normaliser_texte(texte).encode("utf-8")).hexdigest()


def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ── Qui lit, qui écrit (préparation de la vague 4) ────────────────────────────────────

class Lecteur:
    """Celui qui lit ou écrit : l'organisation propriétaire (vague 2) ou, en vague 4, un membre
    du groupement identifié par son invitation."""

    def __init__(self, kind: str, owner_id: int, user_id: Optional[int] = None, invite_id: Optional[int] = None,
                 email: str = ""):
        self.kind, self.owner_id, self.user_id, self.invite_id, self.email = kind, owner_id, user_id, invite_id, email

    @classmethod
    def organisation(cls, owner_id: int, user: Optional[User] = None) -> "Lecteur":
        return cls(AUTEUR_ORG, owner_id, user_id=getattr(user, "id", None), email=getattr(user, "email", "") or "")


def peut_voir_prive(section: DossierSection, lecteur: Lecteur) -> bool:
    """La matière privée d'une partie (sources, extraits, faits à relire, versions de travail)
    n'est lue que par son auteur. Le chef de file ne lit jamais celle d'un partenaire."""
    if section.author_kind == AUTEUR_INVITATION:
        return lecteur.kind == AUTEUR_INVITATION and lecteur.invite_id is not None \
            and lecteur.invite_id == section.author_invite_id
    return lecteur.kind == AUTEUR_ORG and lecteur.owner_id == section.owner_id


def peut_ecrire(section: DossierSection, lecteur: Lecteur) -> bool:
    return peut_voir_prive(section, lecteur)


# ── Le dossier de l'acheteur, lu sans IA (C0 : règlement et cadre en entier) ──────────

_LECTURES = {}            # cache de process : clé → lecture (borné)
_LECTURES_MAX = 32


def _dce_document(db, project: Project, member_ids: list):
    from app.models import Document
    return (db.query(Document)
            .filter(Document.user_id.in_(member_ids), Document.project_id == project.id,
                    Document.folder == "DCE", Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc(), Document.id.desc()).first())


def cle_dossier_acheteur(db, project: Project, member_ids: list) -> str:
    """Identifie le dossier du marché lu (sans le relire) : le fichier importé le plus récent,
    sinon l'extrait gardé par l'analyse."""
    doc = _dce_document(db, project, member_ids)
    if doc is not None:
        return f"fichier:{doc.id}:{doc.file_key}"
    a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
    ex = str(a.get("dce_excerpt") or "")
    if ex.strip():
        return "extrait:" + hashlib.sha256(ex.encode("utf-8")).hexdigest()[:24]
    return "aucun"


def lire_dossier_acheteur(db, project: Project, member_ids: list) -> dict:
    """Lecture du dossier du marché, pièce par pièce, SANS IA : {cle, source, nom_fichier,
    pieces: [{nom, type, libelle, caracteres, lu_en_entier}], cadre, texte}. `texte` est ce que
    l'IA lit : règlement et cadre de réponse en tête et en entier, le reste borné. Ne lève pas."""
    from app.services import dce_pieces as dp
    cle = cle_dossier_acheteur(db, project, member_ids)
    if cle in _LECTURES:
        return dict(_LECTURES[cle])
    out = {"cle": cle, "source": "aucun", "nom_fichier": "", "pieces": [], "cadre": "", "texte": "",
           "lu_le": _now_iso()}
    pieces = []
    if cle.startswith("fichier:"):
        doc = _dce_document(db, project, member_ids)
        try:
            from app.services.analysis import extract_dce_pieces
            from app.services.storage import get_storage
            content = get_storage().load(doc.file_key)
            pieces, _archive = extract_dce_pieces(doc.name, content, max_chars=LECTURE_MAX)
            out.update(source="fichier", nom_fichier=str(doc.name or "")[:200])
        except Exception as e:      # noqa: BLE001 — fichier illisible : repli sur l'extrait
            logger.warning("atelier : lecture du dossier du marché impossible (projet %s) : %s",
                           project.id, type(e).__name__)
            pieces = []
    if not pieces:
        a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
        ex = str(a.get("dce_excerpt") or "")
        if ex.strip():
            pieces = [{"nom": p["nom"], "texte": p["texte"], "type": p["type"], "complet": False}
                      for p in dp.typed_pieces(ex) if (p.get("texte") or "").strip()]
            out["source"] = "extrait"
    if pieces:
        cadre = "\n\n".join(p.get("texte") or "" for p in pieces if p.get("type") == dp.CADRE)
        texte, meta = dp.compose(pieces, DOSSIER_ACHETEUR_MAX)
        out.update(cadre=cadre[:CADRE_MAX], texte=texte,
                   pieces=[{"nom": str(m.get("nom") or "")[:200], "type": m.get("type"),
                            "libelle": m.get("libelle"), "caracteres": int(m.get("caracteres") or 0),
                            "lu_en_entier": bool(m.get("lu_en_entier"))} for m in meta][:30])
    if len(_LECTURES) >= _LECTURES_MAX:
        _LECTURES.pop(next(iter(_LECTURES)), None)
    _LECTURES[cle] = dict(out)
    return out


def _analysis(project: Project) -> dict:
    return project.ai_analysis if isinstance(project.ai_analysis, dict) else {}


def _en_groupement(db, project: Project) -> bool:
    try:
        from app.services.groupement_members import active_invites
        return bool(active_invites(db, project.id))
    except Exception:       # noqa: BLE001
        return False


# ── Le plan ───────────────────────────────────────────────────────────────────────────

def proposition(db, project: Project, member_ids: list, base: str = "auto") -> dict:
    """Plan proposé (sans IA, sans rien enregistrer)."""
    lu = lire_dossier_acheteur(db, project, member_ids)
    return ap.build_plan(_analysis(project), lu.get("cadre") or "", base=base,
                         en_groupement=_en_groupement(db, project))


def _plan_meta(plan: dict, base: str) -> dict:
    return {"source": plan.get("source"), "message": plan.get("message") or "",
            "fichier_impose": bool(plan.get("fichier_impose")), "message_fichier": plan.get("message_fichier") or "",
            "cadre_non_decoupe": bool(plan.get("cadre_non_decoupe")),
            "criteres_hors_dossier": plan.get("criteres_hors_dossier") or [],
            "limites": plan.get("limites") or {}, "base_demandee": base, "construit_le": _now_iso()}


def _section_from_plan(dossier: DossierPresentation, s: dict, ordre: int) -> DossierSection:
    return DossierSection(
        dossier_id=dossier.id, project_id=dossier.project_id, owner_id=dossier.owner_id, ordre=ordre,
        numero=str(s.get("numero") or "")[:20], intitule=str(s.get("intitule") or "")[:300],
        niveau=int(s.get("niveau") or 1), parents=s.get("parents") or [], question=str(s.get("question") or ""),
        source_plan=str(s.get("source_plan") or ap.LIBRE)[:12], critere=str(s.get("critere") or "")[:300],
        critere_id=str(s.get("critere_id") or "")[:20], poids=str(s.get("poids") or "")[:40],
        partie_de_critere=bool(s.get("partie_de_critere")), lot="", limite=s.get("limite") or [],
        author_kind=AUTEUR_ORG, author_invite_id=None, statut=A_ECRIRE, lock_version=0)


def get_dossier(db, project_id: int, owner_id: int) -> Optional[DossierPresentation]:
    return db.query(DossierPresentation).filter(DossierPresentation.project_id == project_id,
                                                DossierPresentation.owner_id == owner_id).first()


def creer_dossier(db, project: Project, owner_id: int, user: User, member_ids: list,
                  base: str = "auto") -> DossierPresentation:
    """Crée le dossier de présentation du marché et ses parties, à partir du plan proposé."""
    from sqlalchemy.exc import IntegrityError
    if get_dossier(db, project.id, owner_id) is not None:
        raise AtelierError(409, "dossier_existe", "Le dossier de présentation de ce marché existe déjà.")
    lu = lire_dossier_acheteur(db, project, member_ids)
    plan = ap.build_plan(_analysis(project), lu.get("cadre") or "", base=base,
                         en_groupement=_en_groupement(db, project))
    d = DossierPresentation(project_id=project.id, owner_id=owner_id, created_by_user_id=user.id,
                            plan_source=plan["source"], plan_meta=_plan_meta(plan, base), dce_lu=lu,
                            analyse_debitee=False, regenerations=0, regenerations_payantes=0,
                            options_export={"page_garde": True, "sommaire": True}, version=0)
    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AtelierError(409, "dossier_existe", "Le dossier de présentation de ce marché existe déjà.")
    for i, s in enumerate(plan["sections"][:SECTIONS_MAX]):
        db.add(_section_from_plan(d, s, i))
    db.commit()
    db.refresh(d)
    return d


def sections_actives(db, dossier: DossierPresentation) -> list:
    return (db.query(DossierSection)
            .filter(DossierSection.dossier_id == dossier.id, DossierSection.retiree_at.is_(None))
            .order_by(DossierSection.ordre.asc(), DossierSection.id.asc()).all())


def sections_retirees(db, dossier: DossierPresentation) -> list:
    return (db.query(DossierSection)
            .filter(DossierSection.dossier_id == dossier.id, DossierSection.retiree_at.isnot(None))
            .order_by(DossierSection.retiree_at.desc(), DossierSection.id.desc()).all())


def _a_du_texte(db, section_ids) -> bool:
    if not section_ids:
        return False
    return db.query(DossierSectionVersion.id).filter(DossierSectionVersion.section_id.in_(section_ids)).first() \
        is not None


def reconstruire_plan(db, project: Project, dossier: DossierPresentation, user: User, member_ids: list,
                      base: str = "auto", remplacer: bool = False) -> DossierPresentation:
    """Reconstruit le plan. Les parties actuelles sont RETIRÉES (jamais supprimées : leurs versions
    restent consultables et peuvent être remises) ; si l'une a déjà du texte, l'utilisateur doit
    le confirmer (remplacer=True)."""
    _verifier_aucune_tache(db, sections_actives(db, dossier))
    act = sections_actives(db, dossier)
    if _a_du_texte(db, [s.id for s in act]) and not remplacer:
        raise AtelierError(409, "plan_remplacement_a_confirmer",
                           "Des parties ont déjà du texte. Reconstruire le plan les retire (leurs textes restent "
                           "dans l'historique et peuvent être remis) : confirmez pour continuer.")
    _LECTURES.pop(cle_dossier_acheteur(db, project, member_ids), None)
    lu = lire_dossier_acheteur(db, project, member_ids)
    plan = ap.build_plan(_analysis(project), lu.get("cadre") or "", base=base,
                         en_groupement=_en_groupement(db, project))
    now = utcnow()
    for s in act:
        s.retiree_at = now
    dossier.plan_source = plan["source"]
    dossier.plan_meta = _plan_meta(plan, base)
    dossier.dce_lu = lu
    dossier.version = (dossier.version or 0) + 1
    for i, s in enumerate(plan["sections"][:SECTIONS_MAX]):
        db.add(_section_from_plan(dossier, s, i))
    db.commit()
    db.refresh(dossier)
    return dossier


def _renumeroter(db, dossier: DossierPresentation) -> None:
    for i, s in enumerate(sections_actives(db, dossier)):
        s.ordre = i


def ajouter_section(db, dossier: DossierPresentation, intitule: str, apres_id: Optional[int] = None) -> DossierSection:
    intitule = _flat(intitule)[:INTITULE_MAX]
    if len(intitule) < 2:
        raise AtelierError(422, "intitule_invalide", "Donnez un intitulé à cette partie.")
    act = sections_actives(db, dossier)
    if len(act) >= SECTIONS_MAX:
        raise AtelierError(422, "trop_de_parties", f"Un dossier compte au plus {SECTIONS_MAX} parties.")
    pos = len(act)
    if apres_id is not None:
        idx = next((i for i, s in enumerate(act) if s.id == apres_id), None)
        if idx is None:
            raise AtelierError(404, "partie_introuvable", "Partie introuvable.")
        pos = idx + 1
    s = DossierSection(dossier_id=dossier.id, project_id=dossier.project_id, owner_id=dossier.owner_id,
                       ordre=pos, numero="", intitule=intitule, niveau=1, parents=[], question="",
                       source_plan=ap.UTILISATEUR, critere="", critere_id="", poids="", partie_de_critere=False,
                       lot="", limite=[], author_kind=AUTEUR_ORG, statut=A_ECRIRE, lock_version=0)
    for x in act[pos:]:
        x.ordre = (x.ordre or 0) + 1
    db.add(s)
    db.flush()
    act.insert(pos, s)
    for i, x in enumerate(act):
        x.ordre = i
    db.commit()
    db.refresh(s)
    return s


def modifier_section(db, dossier: DossierPresentation, section: DossierSection, lecteur: Lecteur,
                     intitule: Optional[str] = None, position: Optional[int] = None) -> DossierSection:
    """Intitulé et place d'une partie. Le cadre de l'acheteur commande : une partie du cadre
    imposé garde son numéro, son intitulé et sa place ; une partie de la grille garde l'intitulé
    du critère."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    if intitule is not None:
        if section.source_plan in (ap.CADRE, ap.GRILLE):
            raise AtelierError(409, "intitule_impose",
                               "Cet intitulé vient du dossier de l'acheteur : il ne se modifie pas.")
        t = _flat(intitule)[:INTITULE_MAX]
        if len(t) < 2:
            raise AtelierError(422, "intitule_invalide", "Donnez un intitulé à cette partie.")
        section.intitule = t
    if position is not None:
        if dossier.plan_source == ap.CADRE:
            raise AtelierError(409, "ordre_impose",
                               "L'ordre des parties suit le cadre de réponse de l'acheteur : il ne se modifie pas.")
        act = [s for s in sections_actives(db, dossier) if s.id != section.id]
        pos = max(0, min(int(position), len(act)))
        act.insert(pos, section)
        for i, x in enumerate(act):
            x.ordre = i
    section.lock_version = (section.lock_version or 0) + 1
    db.commit()
    db.refresh(section)
    return section


def retirer_section(db, dossier: DossierPresentation, section: DossierSection, lecteur: Lecteur) -> None:
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    _verifier_aucune_tache(db, [section])
    section.retiree_at = utcnow()
    db.flush()
    _renumeroter(db, dossier)
    db.commit()


def remettre_section(db, dossier: DossierPresentation, section: DossierSection, lecteur: Lecteur) -> DossierSection:
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    if section.retiree_at is None:
        return section
    if len(sections_actives(db, dossier)) >= SECTIONS_MAX:
        raise AtelierError(422, "trop_de_parties", f"Un dossier compte au plus {SECTIONS_MAX} parties.")
    section.retiree_at = None
    section.ordre = 10 ** 6
    db.flush()
    _renumeroter(db, dossier)
    db.commit()
    db.refresh(section)
    return section


# ── Les versions ──────────────────────────────────────────────────────────────────────

def versions(db, section: DossierSection) -> list:
    return (db.query(DossierSectionVersion).filter(DossierSectionVersion.section_id == section.id)
            .order_by(DossierSectionVersion.numero.desc(), DossierSectionVersion.id.desc()).all())


def version_courante(db, section: DossierSection) -> Optional[DossierSectionVersion]:
    if not section.current_version_id:
        return None
    v = db.get(DossierSectionVersion, section.current_version_id)
    return v if v is not None and v.section_id == section.id else None


def ajouter_version(db, section: DossierSection, *, texte: str, origine: str, ia: bool, sources=None,
                    faits=None, coupe: bool = False, base_version_id: Optional[int] = None,
                    restaure_de: Optional[int] = None, auteur_user_id: Optional[int] = None,
                    job_id: Optional[int] = None) -> DossierSectionVersion:
    """Ajoute une version (jamais de mise à jour ni de suppression d'une version) et fait évoluer
    le statut : une partie validée dont le texte change repasse « à revalider » ; si le texte
    redevient exactement celui qui a été validé, elle redevient « validée »."""
    from sqlalchemy import func
    n = db.query(func.max(DossierSectionVersion.numero)).filter(
        DossierSectionVersion.section_id == section.id).scalar() or 0
    texte = normaliser_texte(texte)[:TEXTE_MAX]
    v = DossierSectionVersion(
        section_id=section.id, dossier_id=section.dossier_id, project_id=section.project_id,
        owner_id=section.owner_id, numero=n + 1, texte=texte, origine=origine, ia=bool(ia),
        sources=sources or [], faits=faits or [], empreinte=empreinte(texte), coupe=bool(coupe),
        base_version_id=base_version_id, restaure_de=restaure_de, author_kind=section.author_kind,
        author_invite_id=section.author_invite_id, auteur_user_id=auteur_user_id, job_id=job_id)
    db.add(v)
    db.flush()
    section.current_version_id = v.id
    if section.validated_version_id:
        section.statut = VALIDE if v.empreinte == section.validated_hash else A_REVALIDER
    else:
        section.statut = BROUILLON
    section.lock_version = (section.lock_version or 0) + 1
    return v


# Une phrase de l'IA reprise dans le texte (8 mots d'affilée) : l'IA a servi.
_SHINGLE = 8


def _shingles(texte: str) -> set:
    w = re.findall(r"\w+", far.fold(texte))
    return {" ".join(w[i:i + _SHINGLE]) for i in range(0, max(0, len(w) - _SHINGLE + 1))}


def ia_a_servi(texte: str, textes_ia: list) -> bool:
    """Le texte reprend-il au moins une suite de 8 mots d'un texte de l'IA ? (côté prudent :
    au moindre emprunt, la mention « Préparé avec assistance IA » est due)."""
    mine = _shingles(texte)
    flat = " ".join(re.findall(r"\w+", far.fold(texte)))
    for t in textes_ia or []:
        theirs = _shingles(t)
        if theirs:
            if mine & theirs:
                return True
        else:
            # Texte de l'IA très court (moins de 8 mots) : repris tel quel ?
            court = " ".join(re.findall(r"\w+", far.fold(t)))
            if court and court in flat:
                return True
    return False


def _textes_ia(db, section: DossierSection) -> list:
    return [v.texte or "" for v in versions(db, section) if v.ia]


def _verrouiller(db, section: DossierSection) -> DossierSection:
    """Relit la partie en la verrouillant jusqu'à la fin de la transaction (Postgres : SELECT … FOR
    UPDATE ; sans effet sur SQLite, qui sérialise déjà les écritures) : deux enregistrements
    simultanés ne peuvent pas partir de la même version courante."""
    return (db.query(DossierSection).filter(DossierSection.id == section.id)
            .populate_existing().with_for_update().first() or section)


def _verifier_aucune_tache(db, sections: list) -> None:
    for s in sections:
        if s.job_id:
            j = db.get(Job, s.job_id)
            if j is not None and j.status in ("pending", "running"):
                raise AtelierError(409, "redaction_en_cours",
                                   f"Adjugo rédige « {s.intitule} » en ce moment : attendez la fin de la rédaction.",
                                   section_id=s.id, job_id=j.id)


def _verifier_base(section: DossierSection, base_version_id) -> None:
    cur = section.current_version_id or None
    base = int(base_version_id) if base_version_id not in (None, "", 0) else None
    if cur != base:
        raise AtelierError(409, "texte_modifie_entre_temps",
                           "Le texte de cette partie a changé depuis que vous l'avez ouvert : rechargez-le avant "
                           "d'enregistrer (votre texte n'a pas été perdu de votre écran).",
                           section_id=section.id, version_courante_id=cur)


def enregistrer_texte(db, ctx: "Contexte", section: DossierSection, lecteur: Lecteur, texte: str,
                      base_version_id) -> DossierSectionVersion:
    """« J'écris moi-même » / modification : nouvelle version, aucune IA. Les faits que
    l'utilisateur écrit lui-même sont ses déclarations ; un fait déjà « à relire » qui reste dans
    le texte reste à relire."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    section = _verrouiller(db, section)
    if section.retiree_at is not None:
        raise AtelierError(409, "partie_retiree", "Cette partie a été retirée du plan : remettez-la d'abord.")
    _verifier_aucune_tache(db, [section])
    _verifier_base(section, base_version_id)
    t = normaliser_texte(texte)
    if len(t) > TEXTE_MAX:
        raise AtelierError(422, "texte_trop_long", f"Une partie compte au plus {TEXTE_MAX} caractères.")
    base = version_courante(db, section)
    if base is not None and base.empreinte == empreinte(t):
        return base
    ia = ia_a_servi(t, _textes_ia(db, section))
    faits = far.controle(t, ctx.sources_entreprise, declares=[t], anciens=(base.faits if base else []),
                         reprise="phrase", noms_entreprise=ctx.noms_entreprise,
                         section_entreprise=section_sur_l_entreprise(section))
    v = ajouter_version(db, section, texte=t, origine=UTILISATEUR, ia=ia, sources=(base.sources if base and ia else []),
                        faits=faits, base_version_id=base.id if base else None, auteur_user_id=lecteur.user_id)
    db.commit()
    db.refresh(v)
    return v


def restaurer_version(db, ctx: "Contexte", section: DossierSection, lecteur: Lecteur, version_id: int,
                      base_version_id) -> DossierSectionVersion:
    """Remet un ancien texte : c'est une NOUVELLE version (copie), l'historique reste entier."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    section = _verrouiller(db, section)
    _verifier_aucune_tache(db, [section])
    _verifier_base(section, base_version_id)
    src = db.get(DossierSectionVersion, int(version_id))
    if src is None or src.section_id != section.id:
        raise AtelierError(404, "version_introuvable", "Version introuvable.")
    cur = version_courante(db, section)
    if cur is not None and cur.empreinte == src.empreinte:
        return cur
    # Les faits relevés pour CE texte valent tels quels (y compris ceux que vous aviez relus).
    faits = [dict(x) for x in (src.faits or []) if isinstance(x, dict)]
    v = ajouter_version(db, section, texte=src.texte or "", origine=src.origine, ia=src.ia,
                        sources=src.sources or [], faits=faits, coupe=src.coupe,
                        base_version_id=cur.id if cur else None, restaure_de=src.id, auteur_user_id=lecteur.user_id)
    db.commit()
    db.refresh(v)
    return v


def marquer_relu(db, section: DossierSection, lecteur: Lecteur, version_id: int) -> DossierSection:
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    if not section.current_version_id or section.current_version_id != int(version_id):
        raise AtelierError(409, "texte_modifie_entre_temps",
                           "Le texte de cette partie a changé : rechargez-le avant de le marquer comme relu.",
                           section_id=section.id, version_courante_id=section.current_version_id)
    if section.statut != VALIDE:
        section.statut = RELU
    section.lock_version = (section.lock_version or 0) + 1
    db.commit()
    db.refresh(section)
    return section


def valider(db, project: Project, section: DossierSection, lecteur: Lecteur, version_id: int,
            ip: str = "") -> DossierSection:
    """Le dirigeant valide CE texte (identifié par sa version) : qui, quand, empreinte ; inscrit
    au journal chaîné. Une modification ultérieure le fera repasser « à revalider »."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    section = _verrouiller(db, section)
    _verifier_aucune_tache(db, [section])
    v = version_courante(db, section)
    if v is None or v.id != int(version_id):
        raise AtelierError(409, "texte_modifie_entre_temps",
                           "Le texte de cette partie a changé : rechargez-le avant de le valider.",
                           section_id=section.id, version_courante_id=section.current_version_id)
    if not (v.texte or "").strip():
        raise AtelierError(422, "partie_vide", "Cette partie n'a pas de texte à valider.")
    section.statut = VALIDE
    section.validated_version_id = v.id
    section.validated_hash = v.empreinte
    section.validated_at = utcnow()
    section.validated_by = lecteur.user_id
    section.lock_version = (section.lock_version or 0) + 1
    db.commit()
    from app.services import audit
    audit.record(db, action="atelier.partie_validee", owner_id=section.owner_id, project_id=project.id,
                 actor=lecteur.email, actor_kind="user", target_type="dossier_section", target_id=section.id,
                 detail=f"Partie validée : {section.intitule}"[:255], ip=ip,
                 meta={"version": v.numero, "empreinte": v.empreinte})
    db.refresh(section)
    return section


def traiter_fait(db, section: DossierSection, lecteur: Lecteur, fait_id: str, statut: str) -> dict:
    """« Relu par vous » (ou retour à « à relire ») sur un fait signalé de la version courante.
    Adjugo ne dit jamais qu'un fait est bon : c'est l'utilisateur qui déclare l'avoir relu."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    if statut not in (far.RELU, far.A_RELIRE):
        raise AtelierError(422, "statut_invalide", "Statut inconnu.")
    v = version_courante(db, section)
    if v is None:
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    faits = [dict(x) for x in (v.faits or []) if isinstance(x, dict)]
    hit = next((x for x in faits if x.get("id") == fait_id), None)
    if hit is None:
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    if statut == far.RELU:
        hit.update(statut=far.RELU, relu_par=lecteur.user_id, relu_le=_now_iso())
    else:
        hit["statut"] = far.A_RELIRE
        hit.pop("relu_par", None)
        hit.pop("relu_le", None)
    v.faits = faits
    flag_modified(v, "faits")
    section.lock_version = (section.lock_version or 0) + 1
    db.commit()
    return hit


# ── Le contexte de l'entreprise : faits autorisés et sources (jamais le dossier de l'acheteur) ─

def section_sur_l_entreprise(section: DossierSection) -> bool:
    libelles = [section.intitule, section.critere] + [p.get("intitule") for p in (section.parents or [])
                                                       if isinstance(p, dict)]
    return far.section_sur_l_entreprise(*libelles)


def _fmt_nombre(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if not f:
        return ""
    return str(int(f)) if f.is_integer() else str(f).replace(".", ",")


def _profil_texte(c: Optional[Company]) -> str:
    if c is None:
        return ""
    lines = [f"Entreprise : {c.name or ''}" + (f" ({c.forme_juridique})" if c.forme_juridique else "")
             + (f", {c.city}" if c.city else "") + "."]
    if c.effectif:
        n = int(c.effectif)
        lines.append(f"Effectif : {n} (salariés, personnes, collaborateurs, compagnons, employés).")
    for lab, val in (("Chiffre d'affaires N-1", c.ca_n1), ("Chiffre d'affaires N-2", c.ca_n2),
                     ("Chiffre d'affaires N-3", c.ca_n3)):
        s = _fmt_nombre(val)
        if s:
            lines.append(f"{lab} : {s} €.")
    quals = []
    for q in (c.qualifications or []):
        if isinstance(q, dict):
            name = _flat(q.get("name") or q.get("nom"))
            det = _flat(q.get("detail"))
            if name:
                quals.append(name + (f" ({det})" if det else ""))
        elif q:
            quals.append(_flat(q))
    if quals:
        lines.append("Qualifications et certifications : " + " ; ".join(quals) + ".")
    for r in (c.references or []):
        if not isinstance(r, dict):
            continue
        parts = [_flat(r.get("name") or r.get("intitule"))]
        if r.get("client"):
            parts.append("client " + _flat(r.get("client")))
        if _fmt_nombre(r.get("value") or r.get("montant")):
            parts.append("montant " + _fmt_nombre(r.get("value") or r.get("montant")) + " €")
        if r.get("year") or r.get("annee"):
            parts.append("année " + _flat(r.get("year") or r.get("annee")))
        if parts[0]:
            lines.append("Référence : " + ", ".join(p for p in parts if p) + ".")
    return "\n".join(lines)


def _equipe_texte(team) -> str:
    out = []
    for m in team or []:
        if not isinstance(m, dict) or not _flat(m.get("nom")):
            continue
        s = f"- {_flat(m.get('nom'))}, {_flat(m.get('fonction')) or 'membre de l équipe'}"
        if _flat(m.get("qualifications")):
            s += f" ; qualifications : {_flat(m.get('qualifications'))}"
        if _flat(m.get("references")):
            s += f" ; références : {_flat(m.get('references'))}"
        out.append(s)
    return "\n".join(out)


def _chiffrage_texte(estimate) -> str:
    """Phases, tâches et jours du chiffrage : AUCUN prix."""
    if not isinstance(estimate, dict) or not estimate.get("lignes"):
        return ""
    lines = []
    for ln in estimate.get("lignes") or []:
        if not isinstance(ln, dict):
            continue
        j = _fmt_nombre(ln.get("jours"))
        lines.append(f"- [{_flat(ln.get('phase'))}] {_flat(ln.get('tache'))}" + (f" : {j} jours" if j else ""))
    tot = _fmt_nombre(estimate.get("jours_total"))
    if tot:
        lines.append(f"Charge totale : {tot} jours.")
    return "\n".join(lines)


def _apports_partenaires(db, project_id: int) -> tuple:
    """Parts SOUMISES des partenaires actifs (jamais de prix) + comptes des partenaires (pour
    masquer les noms de leurs salariés)."""
    try:
        from app.models import ProjectContribution, ProjectInvite
        from app.services.groupement_members import active_invite_filter
        pairs = db.query(ProjectContribution, ProjectInvite.accepted_by_user_id).join(
            ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
            ProjectContribution.project_id == project_id, ProjectContribution.status == "submitted",
            active_invite_filter()).all()
    except Exception:       # noqa: BLE001
        return [], []
    out, uids = [], []
    for c, uid in pairs:
        if uid:
            uids.append(uid)
        refs = "; ".join(_flat(r.get("intitule")) + (f", client {_flat(r.get('client'))}" if r.get("client") else "")
                         + (f", année {_flat(r.get('annee'))}" if r.get("annee") else "")
                         for r in (c.references or []) if isinstance(r, dict) and r.get("intitule"))
        quals = ", ".join(_flat(q) for q in (c.qualifications or []) if q)
        s = f"- {c.company_name or 'Partenaire'} (lot : {c.lot or 'non précisé'})"
        if quals:
            s += f" ; qualifications : {quals}"
        if refs:
            s += f" ; références : {refs}"
        if c.memoire_paragraph:
            s += f" ; apport rédigé par le partenaire : {_flat(c.memoire_paragraph)[:3000]}"
        out.append({"nom": c.company_name or "", "texte": s})
    return out, uids


class Contexte:
    """Ce que l'atelier sait de l'entreprise pour un marché : faits autorisés (remis à l'IA) et
    sources de l'entreprise (contrôle « à relire », sans IA). Le dossier de l'acheteur n'est
    JAMAIS une source de l'entreprise."""

    def __init__(self, db, project: Project, owner_id: int, member_ids: list):
        from app.services.pii import team_of_users
        self.project_id = project.id
        self.owner_id = owner_id
        self.member_ids = list(member_ids)
        comp = db.query(Company).filter(Company.user_id == owner_id).first()
        self.company = comp
        self.profil = _profil_texte(comp)
        self.team = [m for m in ((comp.team if comp else None) or []) if isinstance(m, dict)]
        self.equipe = _equipe_texte(self.team)
        self.chiffrage = _chiffrage_texte(project.estimate)
        self.partenaires, partner_uids = _apports_partenaires(db, project.id)
        self.partner_team = team_of_users(db, partner_uids) if partner_uids else []
        self.noms_entreprise = [x for x in ([comp.name if comp else ""] + [p["nom"] for p in self.partenaires]) if x]
        self.sources_entreprise = [self.profil, self.equipe, self.chiffrage] + [p["texte"] for p in self.partenaires]

    def faits_autorises(self) -> dict:
        return {"profil": self.profil, "equipe": self.equipe, "chiffrage": self.chiffrage,
                "partenaires": "\n".join(p["texte"] for p in self.partenaires)}

    def pseudonymiseur(self):
        from app.services.pii import from_team
        return from_team(self.team + self.partner_team)


# ── Compteur, limites et blocage de l'export ──────────────────────────────────────────

def numero_affiche(dossier: DossierPresentation, section: DossierSection, rang: int) -> str:
    """Numéros du cadre imposé tels quels ; sinon le rang dans le plan (1, 2, 3…). Une partie
    ajoutée par l'utilisateur dans un plan du cadre n'a pas de numéro (le cadre commande)."""
    if dossier.plan_source == ap.CADRE:
        return section.numero if section.source_plan == ap.CADRE else ""
    return str(rang)


def _rangs(dossier: DossierPresentation, sections: list) -> dict:
    out, r = {}, 0
    for s in sections:
        r += 1
        out[s.id] = numero_affiche(dossier, s, r)
    return out


def options_export(dossier: DossierPresentation) -> dict:
    o = dossier.options_export if isinstance(dossier.options_export, dict) else {}
    return {"page_garde": o.get("page_garde", True) is not False, "sommaire": o.get("sommaire", True) is not False}


def _limites_doc(dossier: DossierPresentation) -> dict:
    lim = (dossier.plan_meta or {}).get("limites") if isinstance(dossier.plan_meta, dict) else None
    return lim if isinstance(lim, dict) else {}


def contexte_rendu(db, project: Project, dossier: DossierPresentation, sections: list, courantes: dict,
                   avec_logo: bool = True) -> dict:
    """Ce que l'export et le compteur rendent : titre du règlement, marché, acheteur, candidat,
    parties (numéro et intitulé du cadre, texte courant), police du règlement, mention IA."""
    a = _analysis(project)
    det = a.get("details") if isinstance(a.get("details"), dict) else {}
    comp = db.query(Company).filter(Company.user_id == dossier.owner_id).first()
    rangs = _rangs(dossier, sections)
    secs, ia = [], False
    for s in sections:
        v = courantes.get(s.id)
        if v is not None and v.ia:
            ia = True
        secs.append({"id": s.id, "numero": rangs.get(s.id, ""), "intitule": s.intitule,
                     "parents": (s.parents or []) if dossier.plan_source == ap.CADRE and s.source_plan == ap.CADRE
                     else [], "texte": (v.texte if v is not None else "") or ""})
    opts = options_export(dossier)
    return {"titre": me.memoire_label(a), "marche": _flat(det.get("intitule_marche") or project.name)[:300],
            "acheteur": _flat(det.get("acheteur") or project.client)[:300],
            "entreprise": _flat(comp.name if comp else "")[:300], "date": ax.mois_annee(),
            "logo": _logo(db, dossier) if avec_logo else None, "sections": secs,
            "police_rendu": ax.police(_limites_doc(dossier)), "ia": ia,
            "page_garde": opts["page_garde"], "sommaire": opts["sommaire"]}


def _logo(db, dossier: DossierPresentation) -> Optional[bytes]:
    """Logo de l'entreprise : le document du coffre-fort (hors marché) dont le nom contient
    « logo », en PNG ou JPEG, de moins de 2 Mo. Aucun sinon."""
    try:
        from app.models import Document
        from app.core.org import member_ids
        from app.services.storage import get_storage
        owner = db.get(User, dossier.owner_id)
        ids = member_ids(owner, db) if owner is not None else [dossier.owner_id]
        doc = (db.query(Document).filter(Document.user_id.in_(ids), Document.project_id.is_(None),
                                         Document.deleted_at.is_(None), Document.name.ilike("%logo%"),
                                         Document.mime_type.in_(["image/png", "image/jpeg"]),
                                         Document.file_size <= 2 * 1024 * 1024)
               .order_by(Document.created_at.desc()).first())
        if doc is None:
            return None
        data = get_storage().load(doc.file_key)
        return data if data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff" else None
    except Exception:       # noqa: BLE001 — jamais bloquant
        return None


def _courantes(db, sections: list) -> dict:
    ids = [s.current_version_id for s in sections if s.current_version_id]
    if not ids:
        return {}
    rows = db.query(DossierSectionVersion).filter(DossierSectionVersion.id.in_(ids)).all()
    by_id = {v.id: v for v in rows}
    return {s.id: by_id.get(s.current_version_id) for s in sections if s.current_version_id in by_id}


def _cle_compteur(ctx: dict) -> str:
    pol = ctx.get("police_rendu") or {}
    payload = {"s": [(x["id"], x["numero"], x["intitule"], x["parents"], empreinte(x["texte"]))
                     for x in ctx.get("sections") or []],
               "p": [pol.get("famille"), pol.get("taille")], "g": ctx.get("page_garde"), "t": ctx.get("sommaire"),
               "m": [ctx.get("titre"), ctx.get("marche"), ctx.get("acheteur"), ctx.get("entreprise")],
               "l": bool(ctx.get("logo")), "v": 1}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()


def compteur(db, project: Project, dossier: DossierPresentation, sections: list, courantes: dict,
             ctx: Optional[dict] = None) -> dict:
    """Mots, caractères, pages et lignes estimées par partie et au total (mis en cache pour un
    même état du texte). Les pages sont celles du PDF produit avec la police du règlement : une
    page Word n'est pas calculable exactement, on dit « environ »."""
    ctx = ctx or contexte_rendu(db, project, dossier, sections, courantes)
    cle = _cle_compteur(ctx)
    cache = dossier.compteur if isinstance(dossier.compteur, dict) else {}
    if cache.get("cle") == cle and isinstance(cache.get("resultat"), dict):
        return cache["resultat"]
    try:
        res = ax.compteur(ctx)
    except Exception as e:      # noqa: BLE001 — le compteur ne doit jamais casser l'atelier
        logger.warning("atelier : compteur impossible (dossier %s) : %s", dossier.id, type(e).__name__)
        res = {"sections": [dict(ax.compter_texte(x["texte"]), id=x["id"], pages_estimees=None,
                                 lignes_estimees=None) for x in ctx.get("sections") or []],
               "total": None, "police": None}
    pol = res.get("police") or {}
    res["environ"] = True
    res["message"] = ("Pages estimées avec la police demandée par le règlement"
                      + (f" ({pol.get('famille')} {pol.get('taille')})" if pol.get("connue") else
                         f" (aucune police n'est imposée : {pol.get('famille', ax.POLICE_DEFAUT)} "
                         f"{pol.get('taille', ax.TAILLE_DEFAUT)})")
                      + " : une page Word n'est pas calculable exactement, le nombre de pages est approximatif.")
    dossier.compteur = {"cle": cle, "resultat": res}
    flag_modified(dossier, "compteur")
    db.commit()
    return res


_UNITE = {"pages": ("page", "pages"), "mots": ("mot", "mots"), "caracteres": ("caractère", "caractères"),
          "lignes": ("ligne", "lignes")}


def _pluriel(n, kind: str) -> str:
    one, many = _UNITE.get(kind, (kind, kind))
    try:
        return one if float(n) <= 1 else many
    except (TypeError, ValueError):
        return many


def _fmt(n) -> str:
    if isinstance(n, float):
        return (str(int(n)) if n.is_integer() else str(n)).replace(".", ",")
    return str(n)


def _mesure(kind: str, c: dict, total: bool):
    if not isinstance(c, dict):
        return None
    if kind == "pages":
        return c.get("pages") if total else c.get("pages_estimees")
    if kind == "mots":
        return c.get("mots")
    if kind == "caracteres":
        return c.get("caracteres")
    if kind == "lignes":
        return c.get("lignes_estimees")
    return None


def evaluer_limites(dossier: DossierPresentation, sections: list, rangs: dict, cpt: dict) -> list:
    """Chaque limite repérée dans le dossier (vague 1), comparée au texte : [{portee, section_id,
    titre, type, valeur, mesure, depassee, phrase, source, message, avertissement}]. Seules les
    limites sur le dossier de présentation lui-même ou sur une question du cadre sont contrôlées."""
    out = []
    by_sec = {x.get("id"): x for x in (cpt.get("sections") or [])}
    total = cpt.get("total") or {}
    lims = _limites_doc(dossier)
    o = options_export(dossier)
    inclus = [x for x, on in (("page de garde", o["page_garde"]), ("sommaire", o["sommaire"])) if on]
    suffixe = f" ({' et '.join(inclus)} compris)." if inclus else "."
    for x in lims.get("document") or []:
        k = x.get("type")
        m = _mesure(k, total, True)
        out.append(_limite_out(x, "document", None, "Dossier de présentation", k, m, suffixe))
    for s in sections:
        for x in (s.limite or []):
            if not isinstance(x, dict):
                continue
            k = x.get("type")
            m = _mesure(k, by_sec.get(s.id) or {}, False)
            titre = ax.titre_section({"numero": rangs.get(s.id, ""), "intitule": s.intitule})
            out.append(_limite_out(x, "section", s.id, titre, k, m))
    return out


def _limite_out(x: dict, portee: str, sid, titre: str, kind: str, mesure, suffixe: str = ".") -> dict:
    valeur = x.get("valeur")
    dep = isinstance(mesure, (int, float)) and isinstance(valeur, (int, float)) and mesure > valeur
    unite = _pluriel(valeur, kind)
    if mesure is None:
        msg = f"{titre} : {_fmt(valeur)} {unite} au plus (mesure indisponible)."
    elif kind == "pages":
        msg = (f"{titre} : environ {_fmt(mesure)} {_pluriel(mesure, kind)} pour {_fmt(valeur)} {unite} au plus"
               + suffixe)
    else:
        msg = f"{titre} : {_fmt(mesure)} {_pluriel(mesure, kind)} pour {_fmt(valeur)} {unite} au plus."
    return {"portee": portee, "section_id": sid, "titre": titre, "type": kind, "valeur": valeur,
            "mesure": mesure, "environ": kind in ("pages", "lignes"), "depassee": bool(dep),
            "phrase": x.get("phrase") or "", "source": x.get("source") or "", "message": msg,
            "avertissement": MSG_IRREGULIERE if dep else ""}


def etat_hash(dossier: DossierPresentation, sections: list, courantes: dict, limites: list) -> str:
    """Empreinte de l'état exporté (textes, faits traités, options, limites) : une dérogation ne
    vaut que pour CET état ; au moindre changement, l'export se contrôle de nouveau."""
    payload = {"o": options_export(dossier), "l": [(x["portee"], x["section_id"], x["type"], x["valeur"], x["mesure"])
                                                   for x in limites],
               "s": [(s.id, s.ordre, s.intitule, (courantes.get(s.id).empreinte if courantes.get(s.id) else ""),
                      sorted((f.get("id"), f.get("statut")) for f in ((courantes.get(s.id).faits or [])
                                                                       if courantes.get(s.id) else [])
                             if isinstance(f, dict)))
                     for s in sections]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()


def blocage(dossier: DossierPresentation, sections: list, courantes: dict, rangs: dict, limites: list) -> dict:
    """Ce qui empêche l'export (décision 2b) et ce qui reste à signaler. {bloque, raisons, etat_hash,
    derogation (valable pour cet état) | None, avertissements}."""
    raisons = []
    trous, faits, vides, non_valides = [], [], [], []
    for s in sections:
        v = courantes.get(s.id)
        titre = ax.titre_section({"numero": rangs.get(s.id, ""), "intitule": s.intitule})
        texte = (v.texte if v is not None else "") or ""
        if not texte.strip():
            vides.append({"section_id": s.id, "titre": titre})
        n = len(me.placeholders(texte))
        if n:
            trous.append({"section_id": s.id, "titre": titre, "nombre": n})
        nf = far.non_traites(v.faits if v is not None else [])
        if nf:
            faits.append({"section_id": s.id, "titre": titre, "nombre": nf})
        if s.statut != VALIDE:
            non_valides.append({"section_id": s.id, "titre": titre, "statut": s.statut})
    if not sections:
        raisons.append({"code": "dossier_vide", "message": "Le dossier de présentation n'a aucune partie.",
                        "sections": []})
    if vides:
        raisons.append({"code": "parties_vides", "nombre": len(vides), "sections": vides,
                        "message": f"{len(vides)} partie{'s' if len(vides) > 1 else ''} sans texte."})
    if trous:
        n = sum(x["nombre"] for x in trous)
        raisons.append({"code": "a_completer", "nombre": n, "sections": trous,
                        "message": f"Il reste {n} passage{'s' if n > 1 else ''} « À compléter »."})
    if faits:
        n = sum(x["nombre"] for x in faits)
        raisons.append({"code": "faits_a_relire", "nombre": n, "sections": faits,
                        "message": (f"{n} fait{'s' if n > 1 else ''} à relire "
                                    f"{'n’ont' if n > 1 else 'n’a'} pas été traité{'s' if n > 1 else ''}.")})
    dep = [x for x in limites if x["depassee"]]
    if dep:
        raisons.append({"code": "limite_depassee", "nombre": len(dep), "limites": dep,
                        "message": ("Une limite fixée par le règlement est dépassée." if len(dep) == 1 else
                                    f"{len(dep)} limites fixées par le règlement sont dépassées."),
                        "avertissement": MSG_IRREGULIERE})
    eh = etat_hash(dossier, sections, courantes, limites)
    der = dossier.derogation if isinstance(dossier.derogation, dict) else None
    codes = {r["code"] for r in raisons}
    valide = bool(der and der.get("etat_hash") == eh and codes <= set(der.get("raisons") or []) and raisons
                  and "dossier_vide" not in codes)
    avert = []
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    if meta.get("fichier_impose"):
        avert.append({"code": "fichier_impose", "message": (meta.get("message_fichier") or
                                                           "Ce marché impose son propre fichier de réponse.")
                      + (" Ce fichier Word reprend l'ordre, les numéros et les intitulés de son cadre : recopiez-y "
                         "votre texte." if dossier.plan_source == ap.CADRE else
                         " Recopiez-y votre texte : ne déposez pas ce fichier Word seul.")})
    if non_valides:
        avert.append({"code": "non_valide", "nombre": len(non_valides), "sections": non_valides,
                      "message": (f"{MSG_NON_VALIDE} : {len(non_valides)} partie"
                                  f"{'s' if len(non_valides) > 1 else ''} à valider.")})
    return {"bloque": bool(raisons), "raisons": raisons, "etat_hash": eh,
            "derogation": _derogation_out(der) if valide else None,
            "peut_exporter": (not raisons) or valide, "avertissements": avert}


def _derogation_out(der: dict) -> dict:
    return {"raison": der.get("raison"), "raison_libelle": RAISONS_DEROGATION.get(der.get("raison"), ""),
            "texte": der.get("texte") or "", "raisons": der.get("raisons") or [], "le": der.get("le"),
            "avertissement": der.get("avertissement") or ""}


def enregistrer_derogation(db, project: Project, dossier: DossierPresentation, gate: dict, lecteur: Lecteur,
                           raison: str, texte: str, etat: str, ip: str = "") -> dict:
    """Dérogation explicite (décision 2b) pour l'état exact présenté à l'utilisateur ; inscrite au
    journal chaîné AVANT d'être retenue (sans inscription, pas de dérogation)."""
    from app.models import AuditLog
    from app.services import audit
    if raison not in RAISONS_DEROGATION:
        raise AtelierError(422, "raison_invalide", "Choisissez une raison.")
    t = _flat(texte)
    if not (DEROGATION_TEXTE_MIN <= len(t) <= DEROGATION_TEXTE_MAX):
        raise AtelierError(422, "texte_invalide",
                           f"Expliquez en quelques mots ({DEROGATION_TEXTE_MIN} à {DEROGATION_TEXTE_MAX} caractères).")
    if not gate["raisons"]:
        raise AtelierError(409, "rien_a_deroger", "Rien n'empêche l'export : aucune dérogation n'est nécessaire.")
    if "dossier_vide" in {r["code"] for r in gate["raisons"]}:
        raise AtelierError(409, "dossier_vide", "Le dossier de présentation n'a aucune partie.")
    if etat != gate["etat_hash"]:
        raise AtelierError(409, "etat_modifie", "Le dossier a changé depuis l'affichage : relisez ce qui bloque.",
                           etat_hash=gate["etat_hash"])
    codes = [r["code"] for r in gate["raisons"]]
    avert = MSG_IRREGULIERE if "limite_depassee" in codes else ""
    resume = {r["code"]: r.get("nombre", 0) for r in gate["raisons"]}
    audit.record(db, action="atelier.derogation_export", owner_id=dossier.owner_id, project_id=project.id,
                 actor=lecteur.email, actor_kind="user", target_type="dossier_presentation", target_id=dossier.id,
                 detail=f"Dérogation à l'export : {RAISONS_DEROGATION[raison]}"[:255], ip=ip,
                 meta={"raisons": codes, "detail": resume, "raison": raison, "texte": t, "etat_hash": etat,
                       "avertissement": avert})
    entry = (db.query(AuditLog).filter(AuditLog.owner_id == dossier.owner_id,
                                       AuditLog.action == "atelier.derogation_export",
                                       AuditLog.target_id == dossier.id)
             .order_by(AuditLog.id.desc()).first())
    if entry is None or (entry.meta or {}).get("etat_hash") != etat:
        raise AtelierError(503, "journal_indisponible",
                           "La dérogation n'a pas pu être inscrite au journal : réessayez dans un instant.")
    dossier.derogation = {"etat_hash": etat, "raisons": codes, "raison": raison, "texte": t,
                          "par": lecteur.user_id, "le": _now_iso(), "avertissement": avert, "journal_id": entry.id}
    flag_modified(dossier, "derogation")
    db.commit()
    return _derogation_out(dossier.derogation)


# ── Quota (décision 6a) ───────────────────────────────────────────────────────────────

def quota_out(dossier: DossierPresentation) -> dict:
    cap = regen_gratuites()
    used = int(dossier.regenerations or 0)
    left = max(0, cap - used)
    if not dossier.analyse_debitee:
        msg = ("La première rédaction avec Adjugo compte pour 1 analyse de votre forfait, une seule fois pour tout "
               f"le dossier. Ensuite, refaire une partie est gratuit {cap} fois.")
        prochaine = 1
    elif left:
        msg = f"Refaire une partie est gratuit : encore {left} fois sur {cap} pour ce dossier."
        prochaine = 0
    else:
        msg = (f"Vous avez refait {cap} parties gratuitement. Chaque nouvelle rédaction d'une partie déjà rédigée "
               "compte maintenant pour 1 analyse.")
        prochaine = 1
    return {"analyse_debitee": bool(dossier.analyse_debitee), "regenerations_gratuites": cap,
            "regenerations_utilisees": used, "regenerations_restantes": left,
            "regenerations_payantes": int(dossier.regenerations_payantes or 0), "message": msg,
            "prochaine_refonte_coute": prochaine}


def _deja_redigee_par_ia(db, section: DossierSection) -> bool:
    return db.query(DossierSectionVersion.id).filter(
        DossierSectionVersion.section_id == section.id,
        DossierSectionVersion.origine.in_([IA, RACCOURCI])).first() is not None


def _debiter(db, user: User, dossier: DossierPresentation, sections: list, accepte_debit: bool) -> dict:
    """Décide et applique le débit d'une action de l'IA. Renvoie le relevé (pour rembourser).
    Toutes les analyses dues sont prises AVANT de toucher au dossier : si l'une est refusée
    (quota atteint), celles déjà prises sont rendues et rien ne change."""
    from app.core.quota import consume_analysis, refund_analysis
    releve = {"analyse": False, "sections": {}}
    cap = regen_gratuites()
    premiere = not dossier.analyse_debitee
    # Première action de l'IA sur ce dossier : 1 analyse pour tout le dossier ; toutes les parties
    # de cette action sont incluses (aucune n'est une « refonte »).
    regen = [] if premiere else [s for s in sections if _deja_redigee_par_ia(db, s)]
    free_left = max(0, cap - int(dossier.regenerations or 0))
    payantes = max(0, len(regen) - free_left)
    if payantes and not accepte_debit:
        raise AtelierError(409, "debit_a_confirmer",
                           f"Vous avez refait {cap} parties gratuitement : "
                           + ("cette nouvelle rédaction compte pour 1 analyse de votre forfait."
                              if payantes == 1 else
                              f"ces nouvelles rédactions comptent pour {payantes} analyses de votre forfait.")
                           + " Confirmez pour continuer.", cout=payantes)
    dues = (1 if premiere else 0) + payantes
    prises = 0
    try:
        for _ in range(dues):
            consume_analysis(user, db)
            prises += 1
    except Exception:
        db.rollback()
        for _ in range(prises):
            refund_analysis(user, db)
        raise
    if premiere:
        dossier.analyse_debitee = True
        releve["analyse"] = True
    for i, s in enumerate(regen):
        if i < free_left:
            dossier.regenerations = int(dossier.regenerations or 0) + 1
            releve["sections"][str(s.id)] = "gratuite"
        else:
            dossier.regenerations_payantes = int(dossier.regenerations_payantes or 0) + 1
            releve["sections"][str(s.id)] = "payante"
    for s in sections:
        releve["sections"].setdefault(str(s.id), "incluse")
    return releve


def rembourser(db, job: Job, section_ids_en_echec=None) -> None:
    """Rend ce qu'une action de l'IA a débité, quand elle n'a rien produit : tout (job en échec)
    ou les seules parties en échec (échec partiel). Idempotent (le relevé est marqué rendu)."""
    from app.core.quota import refund_analysis
    res = job.result if isinstance(job.result, dict) else {}
    releve = res.get("_debit") if isinstance(res.get("_debit"), dict) else None
    if not releve or releve.get("rendu"):
        return
    dossier = db.get(DossierPresentation, int(releve.get("dossier_id") or 0))
    user = db.get(User, job.user_id)
    tout = section_ids_en_echec is None
    ids = {str(i) for i in (section_ids_en_echec or [])}
    rendu = dict(releve.get("rendus") or {})
    for sid, kind in (releve.get("sections") or {}).items():
        if not (tout or sid in ids) or sid in rendu:
            continue
        if kind == "gratuite" and dossier is not None:
            dossier.regenerations = max(0, int(dossier.regenerations or 0) - 1)
        elif kind == "payante":
            if dossier is not None:
                dossier.regenerations_payantes = max(0, int(dossier.regenerations_payantes or 0) - 1)
            if user is not None:
                refund_analysis(user, db)
        rendu[sid] = kind
    if tout and releve.get("analyse") and not releve.get("analyse_rendue"):
        if dossier is not None:
            dossier.analyse_debitee = False
        if user is not None:
            refund_analysis(user, db)
        releve["analyse_rendue"] = True
    releve["rendus"] = rendu
    if tout:
        releve["rendu"] = True
    job.result = dict(res, _debit=releve)
    flag_modified(job, "result")
    db.commit()


# ── Le moteur : rédiger / raccourcir en tâche de fond ─────────────────────────────────

def cible_mots(section: DossierSection, cpt_section: Optional[dict], texte: str = "") -> Optional[int]:
    """Longueur visée d'après la limite de la partie, quand elle est connue (sinon None)."""
    mots = (cpt_section or {}).get("mots") or len(re.findall(r"\w+", texte or ""))
    pages = (cpt_section or {}).get("pages_estimees") or 0
    for x in section.limite or []:
        if not isinstance(x, dict) or not isinstance(x.get("valeur"), (int, float)):
            continue
        v, k = x["valeur"], x.get("type")
        if k == "mots":
            return max(30, int(v * 0.95))
        if k == "caracteres":
            return max(30, int(v / 6.5 * 0.95))
        if k == "lignes":
            return max(30, int(v * 11 * 0.95))
        if k == "pages":
            per = (mots / pages) if pages and mots else 450
            return max(30, int(v * per * 0.92))
    return None


def _requete(section: DossierSection) -> str:
    return " ".join(x for x in (section.intitule, section.critere, _flat(section.question)[:300]) if x)


def _partie_ia(dossier: DossierPresentation, section: DossierSection, numero: str, autres: list, ctx: Contexte,
               chunks: list, dossier_acheteur: str, cible: Optional[int]) -> dict:
    return {"titre": section.intitule, "numero": numero, "question": section.question or "",
            "critere": section.critere or "", "poids": section.poids or "",
            "partie_de_critere": bool(section.partie_de_critere), "source_plan": section.source_plan,
            "cible_mots": cible, "faits": ctx.faits_autorises(), "chunks": chunks,
            "dossier_acheteur": dossier_acheteur, "autres_parties": autres}


def lancer(db, user: User, project: Project, dossier: DossierPresentation, sections: list, action: str,
           lecteur: Lecteur, member_ids: list, cible: Optional[int] = None, accepte_debit: bool = False) -> Job:
    """Lance « Rédiger avec Adjugo » (une ou plusieurs parties) ou « Raccourcir » (une partie) en
    tâche de fond. Débite selon la décision 6a, rembourse si l'IA tombe en panne."""
    from app.services.jobs import create_job, run_in_thread
    if action not in (JOB_REDIGER, JOB_RACCOURCIR):
        raise AtelierError(422, "action_inconnue", "Action inconnue.")
    if not sections:
        raise AtelierError(422, "aucune_partie", "Aucune partie à rédiger.")
    sections = [_verrouiller(db, s) for s in sections]
    for s in sections:
        if not peut_ecrire(s, lecteur):
            raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
        if s.retiree_at is not None:
            raise AtelierError(409, "partie_retiree", "Cette partie a été retirée du plan : remettez-la d'abord.")
    _verifier_aucune_tache(db, sections)
    cibles = {}
    if action == JOB_RACCOURCIR:
        s = sections[0]
        v = version_courante(db, s)
        if v is None or not (v.texte or "").strip():
            raise AtelierError(422, "partie_vide", "Il n'y a pas encore de texte à raccourcir dans cette partie.")
        n = len(re.findall(r"\w+", v.texte or ""))
        if cible is None:
            cc = (dossier.compteur or {}).get("resultat", {}) if isinstance(dossier.compteur, dict) else {}
            cs = next((x for x in (cc.get("sections") or []) if x.get("id") == s.id), None)
            cible = cible_mots(s, cs, v.texte) or max(30, int(n * 0.7))
        cible = int(cible)
        if cible < 30:
            raise AtelierError(422, "cible_invalide", "Visez au moins 30 mots.")
        if cible >= n:
            raise AtelierError(422, "deja_assez_court",
                               f"Le texte compte déjà {n} mots, pour {cible} visés : rien à raccourcir.")
        cibles[s.id] = cible
    releve = _debiter(db, user, dossier, sections, accepte_debit)
    titre = sections[0].intitule if len(sections) == 1 else f"{len(sections)} parties"
    label = ("Dossier de présentation : rédaction de « " if action == JOB_REDIGER
             else "Dossier de présentation : raccourcir « ") + titre[:120] + " »"
    job = create_job(db, user.id, action, label)
    releve.update(dossier_id=dossier.id, rendu=False)
    job.result = {"_debit": releve}
    for s in sections:
        s.job_id = job.id
    db.commit()
    ids = [s.id for s in sections]
    jid, pid, owner, mids = job.id, project.id, dossier.owner_id, list(member_ids)
    uid = user.id

    def _work(jdb):
        return _executer(jdb, jid, pid, owner, mids, uid, ids, action, cibles)

    def _on_error(jdb, j):
        rembourser(jdb, j)
        _liberer(jdb, ids, j.id)

    run_in_thread(jid, _work, on_error=_on_error, tenant_id=owner, error_message=MSG_IA_PANNE)
    return db.get(Job, jid)


def liberer_job(db, job_id: int) -> None:
    """Parties encore rattachées à une tâche terminée ou interrompue : libérées."""
    rows = db.query(DossierSection).filter(DossierSection.job_id == job_id).all()
    for s in rows:
        s.job_id = None
    if rows:
        db.commit()


def _liberer(db, section_ids: list, job_id: int) -> None:
    for s in db.query(DossierSection).filter(DossierSection.id.in_(section_ids)).all():
        if s.job_id == job_id:
            s.job_id = None
    db.commit()


def _executer(db, job_id: int, project_id: int, owner_id: int, member_ids: list, user_id: int, section_ids: list,
              action: str, cibles: dict) -> dict:
    """Dans le fil de la tâche de fond (tenant_scope posé par run_in_thread) : prépare tout avec
    la base, appelle l'IA SANS base (noms masqués, coût mesuré, espace facturé reposé dans chaque
    fil), puis enregistre chaque texte comme une nouvelle version, avec ses faits à relire."""
    from concurrent.futures import ThreadPoolExecutor
    from app.services import rag
    from app.services.agents import memoire as moteur
    from app.services.llm import LLMUnavailable, cost_meter, map_in_context, pii_scope
    project = db.get(Project, project_id)
    dossier = get_dossier(db, project_id, owner_id)
    if project is None or dossier is None:
        raise RuntimeError("dossier introuvable")
    act = sections_actives(db, dossier)
    rangs = _rangs(dossier, act)
    sections = [s for s in act if s.id in section_ids]
    ctx = Contexte(db, project, owner_id, member_ids)
    lu = dossier.dce_lu if isinstance(dossier.dce_lu, dict) else {}
    if lu.get("cle") != cle_dossier_acheteur(db, project, member_ids) or not lu.get("texte"):
        lu = lire_dossier_acheteur(db, project, member_ids)
        dossier.dce_lu = lu
        flag_modified(dossier, "dce_lu")
        db.commit()
    dossier_acheteur = lu.get("texte") or ""
    taches = []
    for s in sections:
        base = version_courante(db, s)
        if action == JOB_RACCOURCIR:
            taches.append({"sid": s.id, "base": base, "texte": base.texte if base else "", "chunks": [],
                           "cible": cibles.get(s.id), "titre": s.intitule})
            continue
        chunks = rag.retrieve_multi(db, member_ids, _requete(s), k=6, relevance=True)
        autres = [ax.titre_section({"numero": rangs.get(x.id, ""), "intitule": x.intitule}) for x in act if x.id != s.id]
        cible = cible_mots(s, None)
        taches.append({"sid": s.id, "base": base, "chunks": chunks,
                       "partie": _partie_ia(dossier, s, rangs.get(s.id, ""), autres, ctx, chunks, dossier_acheteur,
                                            cible)})

    def _un(t):
        if action == JOB_RACCOURCIR:
            return moteur.raccourcir_partie(t["texte"], t["cible"], titre=t["titre"], billing_id=owner_id)
        return moteur.rediger_partie(t["partie"], billing_id=owner_id)

    label = "atelier : rédiger" if action == JOB_REDIGER else "atelier : raccourcir"
    with pii_scope(ctx.pseudonymiseur()), cost_meter(label, owner_id) as cm:
        if len(taches) == 1:
            resultats = [_un(taches[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(taches))) as ex:
                resultats = map_in_context(ex, _un, taches)
    # Enregistrement (nouvelle session de lecture : la tâche a pu durer plusieurs minutes).
    dossier = get_dossier(db, project_id, owner_id)
    _cumuler_cout(dossier, cm.summary())
    sortie, echecs = [], []
    for t, r in zip(taches, resultats):
        s = db.get(DossierSection, t["sid"])
        if s is None:
            continue
        if r.get("erreur") or not (r.get("texte") or "").strip():
            echecs.append(s.id)
            if s.job_id == job_id:
                s.job_id = None
            sortie.append({"section_id": s.id, "ok": False})
            continue
        base = t["base"]
        texte = r["texte"]
        if action == JOB_RACCOURCIR:
            faits = far.controle(texte, ctx.sources_entreprise, declares=[t["texte"]],
                                 anciens=(base.faits if base else []), reprise="fait",
                                 noms_entreprise=ctx.noms_entreprise, section_entreprise=section_sur_l_entreprise(s))
            sources = (base.sources or []) if base else []
            refs = {f"S{n}" for n in rag.cited_refs(texte)}
            sources = [x for x in sources if x.get("ref") in refs]
            v = ajouter_version(db, s, texte=texte, origine=RACCOURCI, ia=True, sources=sources, faits=faits,
                                coupe=bool(r.get("coupe")), base_version_id=base.id if base else None,
                                auteur_user_id=user_id, job_id=job_id)
        else:
            src = ctx.sources_entreprise + [c.get("text") or "" for c in t["chunks"]]
            faits = far.controle(texte, src, declares=[], anciens=(base.faits if base else []), reprise="phrase",
                                 noms_entreprise=ctx.noms_entreprise, section_entreprise=section_sur_l_entreprise(s))
            v = ajouter_version(db, s, texte=texte, origine=IA, ia=True, sources=r.get("sources") or [], faits=faits,
                                coupe=bool(r.get("coupe")), base_version_id=base.id if base else None,
                                auteur_user_id=user_id, job_id=job_id)
        if s.job_id == job_id:
            s.job_id = None
        sortie.append({"section_id": s.id, "ok": True, "version_id": v.id, "statut": s.statut,
                       "coupe": bool(r.get("coupe")), "a_completer": len(me.placeholders(texte)),
                       "faits_a_relire": far.non_traites(faits), "extraits_fournis": len(t["chunks"])})
    db.commit()
    if echecs and len(echecs) == len(taches):
        raise LLMUnavailable("Service IA indisponible : aucune partie rédigée.")
    j = db.get(Job, job_id)
    if echecs and j is not None:
        rembourser(db, j, section_ids_en_echec=echecs)
        db.refresh(j)
    debit = (j.result or {}).get("_debit") if j is not None and isinstance(j.result, dict) else None
    return {"sections": sortie, "echecs": len(echecs), "_debit": debit,
            "message": ("" if not echecs else
                        f"{len(echecs)} partie{'s' if len(echecs) > 1 else ''} n'a pas pu être rédigée "
                        "(service d'IA indisponible) : rien n'a été débité pour elle, réessayez.")}


def _cumuler_cout(dossier: Optional[DossierPresentation], summary: dict) -> None:
    """Coût IA réel cumulé sur le dossier (décision 6a : ramener le plafond à 5 si un dossier complet
    coûte plus qu'une analyse hors forfait). Interne, jamais montré au client."""
    if dossier is None or not isinstance(summary, dict):
        return
    cur = dossier.cout_ia if isinstance(dossier.cout_ia, dict) else {}
    usd = summary.get("cout_estime_usd")
    out = {"appels": int(cur.get("appels") or 0) + int(summary.get("appels") or 0),
           "tokens_entree": int(cur.get("tokens_entree") or 0) + int(summary.get("tokens_entree") or 0),
           "tokens_sortie": int(cur.get("tokens_sortie") or 0) + int(summary.get("tokens_sortie") or 0),
           "cout_estime_usd": (round(float(cur.get("cout_estime_usd") or 0) + float(usd), 5)
                               if usd is not None and cur.get("cout_estime_usd", 0) is not None else None),
           "fournisseur": summary.get("fournisseur")}
    dossier.cout_ia = out
    flag_modified(dossier, "cout_ia")


def tache_en_cours(db, section: DossierSection) -> Optional[dict]:
    if not section.job_id:
        return None
    j = db.get(Job, section.job_id)
    if j is None or j.status not in ("pending", "running"):
        return None
    return {"job_id": j.id, "action": "rediger" if j.kind == JOB_REDIGER else "raccourcir", "statut": j.status}


def job_public(j: Job) -> dict:
    """Vue client d'une tâche de l'atelier (sans le relevé de débit interne)."""
    from app.services.jobs import job_out
    out = job_out(j)
    if isinstance(out.get("result"), dict):
        out["result"] = {k: v for k, v in out["result"].items() if not k.startswith("_")}
    return out


# ── Export ────────────────────────────────────────────────────────────────────────────

MIMES = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "pdf": "application/pdf"}


def nom_fichier(project: Project, fmt: str) -> str:
    return f"{me.file_stem(me.memoire_label(_analysis(project)))}.{fmt}"


def apercu_export(project: Project, dossier: DossierPresentation, ctx: dict) -> dict:
    """Ce que l'utilisateur voit AVANT l'export : nom du fichier, propriétés (dont la mention IA),
    police, options."""
    pol = ctx.get("police_rendu") or {}
    ia = bool(ctx.get("ia"))
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    return {"nom_fichier_docx": nom_fichier(project, "docx"), "nom_fichier_pdf": nom_fichier(project, "pdf"),
            "titre": ctx.get("titre"), "ia_utilisee": ia, "mention_ia": ax.IA_MENTION if ia else "",
            "proprietes": {"titre": ctx.get("titre"), "auteur": "", "sujet": ax.IA_MENTION if ia else "",
                           "mots_cles": "assistance IA" if ia else ""},
            "message_ia": ("Des textes ont été préparés avec l'aide d'Adjugo : le fichier le dira dans ses propriétés "
                           f"(« {ax.IA_MENTION} »)." if ia else
                           "Aucun texte n'a été préparé avec l'IA : le fichier n'en porte aucune mention."),
            "police": {k: pol.get(k) for k in ("famille", "taille", "connue", "phrase")},
            "options": options_export(dossier), "fichier_impose": bool(meta.get("fichier_impose")),
            "plan_du_cadre": dossier.plan_source == ap.CADRE, "logo": bool(ctx.get("logo"))}


def exporter(db, user: User, project: Project, dossier: DossierPresentation, fmt: str, lecteur: Lecteur,
             etat: Optional[str] = None, ip: str = "") -> tuple:
    """(octets, nom du fichier, type) — ou AtelierError 409 « export_bloque » avec les raisons."""
    if fmt not in MIMES:
        raise AtelierError(422, "format_invalide", "Format inconnu : docx ou pdf.")
    sections = sections_actives(db, dossier)
    cour = _courantes(db, sections)
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    lims = evaluer_limites(dossier, sections, rangs, cpt)
    gate = blocage(dossier, sections, cour, rangs, lims)
    if not gate["peut_exporter"]:
        raise AtelierError(409, "export_bloque",
                           "L'export est bloqué : " + " ".join(r["message"] for r in gate["raisons"]),
                           raisons=gate["raisons"], etat_hash=gate["etat_hash"],
                           derogations_possibles=[{"code": k, "libelle": v} for k, v in RAISONS_DEROGATION.items()]
                           if "dossier_vide" not in {r["code"] for r in gate["raisons"]} else [])
    if etat and etat != gate["etat_hash"]:
        raise AtelierError(409, "etat_modifie", "Le dossier a changé depuis l'affichage : relisez-le avant d'exporter.",
                           etat_hash=gate["etat_hash"])
    data = ax.to_docx(ctx) if fmt == "docx" else ax.to_pdf(ctx)[0]
    nom = nom_fichier(project, fmt)
    dossier.dernier_export = {"le": _now_iso(), "par": user.id, "format": fmt, "nom": nom,
                              "empreinte": hashlib.sha256(data).hexdigest(), "ia": bool(ctx.get("ia")),
                              "derogation": bool(gate["derogation"]), "etat_hash": gate["etat_hash"]}
    flag_modified(dossier, "dernier_export")
    db.commit()
    _archiver(db, user, project, dossier, nom, data, fmt, cour)
    from app.services import audit
    audit.record(db, action="atelier.export", owner_id=dossier.owner_id, project_id=project.id, actor=lecteur.email,
                 actor_kind="user", target_type="dossier_presentation", target_id=dossier.id,
                 detail=f"Dossier de présentation exporté ({fmt})", ip=ip,
                 meta={"format": fmt, "empreinte": dossier.dernier_export["empreinte"], "ia": bool(ctx.get("ia")),
                       "derogation": bool(gate["derogation"])})
    return data, nom, MIMES[fmt]


def _archiver(db, user: User, project: Project, dossier: DossierPresentation, nom: str, data: bytes, fmt: str,
              cour: dict) -> None:
    """Range le fichier exporté dans le dossier du marché (« Mémoire technique ») et met à jour
    l'état lu par la liste des pièces. Jamais bloquant."""
    try:
        from app.services.dossier import replace_in_dossier
        replace_in_dossier(db, user.id, project.id, "Mémoire technique", nom, data, MIMES[fmt])
        wf = dict(project.workflow) if isinstance(project.workflow, dict) else {}
        prev = wf.get("dossier_presentation") if isinstance(wf.get("dossier_presentation"), dict) else {}
        fichiers = [x for x in (prev.get("fichiers") or []) if x != nom] + [nom]
        n = sum(len(me.placeholders(v.texte if v else "")) for v in cour.values())
        wf["dossier_presentation"] = {"nom": me.memoire_label(_analysis(project)), "fichiers": fichiers[-4:],
                                      "a_completer": n, "coupe": False, "genere_le": _now_iso(), "source": "atelier"}
        project.workflow = wf
        flag_modified(project, "workflow")
        db.commit()
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("atelier : archivage de l'export impossible (projet %s) : %s", project.id, type(e).__name__)


def _validees_de_preference(db, sections: list, cour: dict) -> tuple:
    """Texte retenu pour le dossier commun : la version VALIDÉE de chaque partie quand elle existe
    (le dirigeant l'a approuvée), sinon le texte courant. Renvoie (versions retenues, parties
    modifiées depuis leur validation)."""
    ids = [s.validated_version_id for s in sections if s.validated_version_id]
    by_id = {v.id: v for v in db.query(DossierSectionVersion).filter(DossierSectionVersion.id.in_(ids)).all()} \
        if ids else {}
    out, modifiees = {}, []
    for s in sections:
        v = by_id.get(s.validated_version_id) if s.validated_version_id else None
        if v is not None and v.section_id == s.id:
            out[s.id] = v
            if s.current_version_id and s.current_version_id != v.id:
                modifiees.append(s)
        elif s.id in cour:
            out[s.id] = cour[s.id]
    return out, modifiees


def dossier_commun(db, project: Project, owner_id: int) -> dict:
    """Pour le dossier commun (ZIP / formulaires) : {files: {"docx": (nom, octets), "pdf": (nom, octets)},
    markdown, etat: {a_completer, coupe} | None, warnings}. Le texte vient de l'ATELIER (le moteur
    de l'ancien « dossier complet » est retiré) : la version VALIDÉE de chaque partie de
    préférence, sinon le texte courant avec l'avertissement BLOQUANT « dossier de présentation non
    validé ». Mêmes règles que l'export : rien n'est joint si l'export est bloqué sans dérogation."""
    out = {"files": {}, "markdown": "", "etat": None, "warnings": []}
    dossier = get_dossier(db, project.id, owner_id)
    if dossier is None:
        out["warnings"].append("BLOQUANT — Dossier de présentation non rédigé : préparez-le dans l'atelier (étape "
                               "« Préparer » du marché), puis validez chaque partie.")
        return out
    sections = sections_actives(db, dossier)
    cour, modifiees = _validees_de_preference(db, sections, _courantes(db, sections))
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    gate = blocage(dossier, sections, cour, rangs, evaluer_limites(dossier, sections, rangs, cpt))
    md = "\n\n".join(f"## {ax.titre_section(x)}\n\n{ax.texte_export(x['texte'])}".strip()
                      for x in ctx["sections"])
    out["markdown"] = md
    out["etat"] = {"a_completer": sum(len(me.placeholders(x["texte"])) for x in ctx["sections"]),
                   "coupe": any(bool(v.coupe) for v in cour.values() if v is not None)}
    if not gate["peut_exporter"]:
        out["warnings"].append("BLOQUANT — Dossier de présentation non joint : "
                               + " ".join(r["message"] for r in gate["raisons"])
                               + " Traitez ces points dans l'atelier, ou enregistrez-y une dérogation.")
        return out
    sans_validation = [s for s in sections if not s.validated_version_id]
    if sans_validation:
        n = len(sans_validation)
        out["warnings"].append(f"BLOQUANT — {MSG_NON_VALIDE} : {n} partie{'s' if n > 1 else ''} à valider. "
                               "Validez chaque partie dans l'atelier avant de déposer.")
    if modifiees:
        out["warnings"].append("Dossier de présentation : " + ", ".join(
            f"« {ax.titre_section({'numero': rangs.get(s.id, ''), 'intitule': s.intitule})} »" for s in modifiees[:6])
            + (" a été modifiée" if len(modifiees) == 1 else " ont été modifiées")
            + " depuis la validation : le dossier joint le texte VALIDÉ. Revalidez dans l'atelier pour joindre le "
              "nouveau texte.")
    if gate["derogation"]:
        out["warnings"].append("Dossier de présentation joint avec une dérogation enregistrée : "
                               + " ".join(r["message"] for r in gate["raisons"])
                               + (f" {MSG_IRREGULIERE}" if gate["derogation"].get("avertissement") else ""))
    out["files"] = {"docx": (nom_fichier(project, "docx"), ax.to_docx(ctx)),
                    "pdf": (nom_fichier(project, "pdf"), ax.to_pdf(ctx)[0])}
    return out


# ── Vue d'ensemble (GET) ──────────────────────────────────────────────────────────────

def _version_out(v: DossierSectionVersion, prive: bool, texte: bool = True) -> dict:
    out = {"id": v.id, "numero": v.numero, "origine": v.origine, "origine_libelle": ORIGINES.get(v.origine, ""),
           "ia": bool(v.ia), "empreinte": v.empreinte, "coupe": bool(v.coupe), "cree_le": _iso(v.created_at),
           "auteur_user_id": v.auteur_user_id, "restaure_de": v.restaure_de,
           "a_completer": len(me.placeholders(v.texte or "")), "faits_a_relire": far.non_traites(v.faits)}
    if texte:
        out["texte"] = v.texte or ""
    if prive:
        out["sources"] = v.sources or []
        out["faits"] = v.faits or []
    return out


def section_out(db, dossier: DossierPresentation, s: DossierSection, rang_affiche: str, lecteur: Lecteur,
                courante: Optional[DossierSectionVersion], cpt_section: Optional[dict]) -> dict:
    prive = peut_voir_prive(s, lecteur)
    out = {"id": s.id, "ordre": s.ordre, "numero": s.numero, "numero_affiche": rang_affiche,
           "intitule": s.intitule, "titre": ax.titre_section({"numero": rang_affiche, "intitule": s.intitule}),
           "niveau": s.niveau, "parents": s.parents or [], "question": s.question or "",
           "source_plan": s.source_plan, "critere": s.critere or "", "critere_id": s.critere_id or "",
           "poids": s.poids or "", "partie_de_critere": bool(s.partie_de_critere), "lot": s.lot or "",
           "limite": s.limite or [],
           "auteur": {"type": s.author_kind, "invite_id": s.author_invite_id,
                      "libelle": "Votre entreprise" if s.author_kind == AUTEUR_ORG else "Un partenaire du groupement"},
           "statut": s.statut, "statut_libelle": STATUTS.get(s.statut, s.statut),
           "intitule_modifiable": s.source_plan not in (ap.CADRE, ap.GRILLE) and prive,
           "peut_ecrire": peut_ecrire(s, lecteur), "prive_visible": prive,
           "redaction_en_cours": tache_en_cours(db, s),
           "validation": ({"version_id": s.validated_version_id, "empreinte": s.validated_hash,
                           "le": _iso(s.validated_at), "par": s.validated_by} if s.validated_version_id else None),
           "lock_version": s.lock_version, "retiree": s.retiree_at is not None}
    if prive:
        out["version_courante"] = _version_out(courante, True) if courante is not None else None
        out["nb_versions"] = db.query(DossierSectionVersion.id).filter(
            DossierSectionVersion.section_id == s.id).count()
    else:
        # Auteur partenaire (vague 4) : seul le texte VALIDÉ (envoyé) est commun, avec ses compteurs.
        vv = db.get(DossierSectionVersion, s.validated_version_id) if s.validated_version_id else None
        out["version_courante"] = _version_out(vv, False) if vv is not None else None
    v = out["version_courante"]
    out["a_completer"] = v["a_completer"] if v else 0
    out["faits_a_relire"] = v["faits_a_relire"] if v else 0
    out["compteur"] = ({k: cpt_section.get(k) for k in ("mots", "caracteres", "pages_estimees", "lignes_estimees")}
                       if cpt_section else None)
    return out


def etat(db, project: Project, dossier: DossierPresentation, lecteur: Lecteur, member_ids: list) -> dict:
    sections = sections_actives(db, dossier)
    cour = _courantes(db, sections)
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    lims = evaluer_limites(dossier, sections, rangs, cpt)
    gate = blocage(dossier, sections, cour, rangs, lims)
    by_sec = {x.get("id"): x for x in (cpt.get("sections") or [])}
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    lu = dossier.dce_lu if isinstance(dossier.dce_lu, dict) else {}
    a_change = bool(lu.get("cle")) and lu.get("cle") != cle_dossier_acheteur(db, project, member_ids)
    retirees = [{"id": s.id, "intitule": s.intitule, "retiree_le": _iso(s.retiree_at),
                 "nb_versions": db.query(DossierSectionVersion.id).filter(
                     DossierSectionVersion.section_id == s.id).count()}
                for s in sections_retirees(db, dossier) if peut_voir_prive(s, lecteur)]
    return {
        "projet": {"id": project.id, "nom": project.name},
        "dossier": {"id": dossier.id, "plan_source": dossier.plan_source, "version": dossier.version,
                    "cree_le": _iso(dossier.created_at), "maj_le": _iso(dossier.updated_at),
                    "plan": {k: meta.get(k) for k in ("source", "message", "fichier_impose", "message_fichier",
                                                      "cadre_non_decoupe", "criteres_hors_dossier", "limites",
                                                      "base_demandee", "construit_le")},
                    "dernier_export": dossier.dernier_export or None},
        "sections": [section_out(db, dossier, s, rangs.get(s.id, ""), lecteur, cour.get(s.id), by_sec.get(s.id))
                     for s in sections],
        "sections_retirees": retirees,
        "compteur": {"total": cpt.get("total"), "police": cpt.get("police"), "environ": True,
                     "message": cpt.get("message")},
        "limites": lims,
        "blocage": gate,
        "quota": quota_out(dossier),
        "export": apercu_export(project, dossier, ctx),
        "dossier_acheteur": {"source": lu.get("source") or "aucun", "nom_fichier": lu.get("nom_fichier") or "",
                             "pieces": [{k: p.get(k) for k in ("nom", "libelle", "lu_en_entier")}
                                        for p in (lu.get("pieces") or [])],
                             "a_change": a_change, "message": MSG_DCE_CHANGE if a_change else ""},
        "statuts": STATUTS,
        "derogations_possibles": [{"code": k, "libelle": v} for k, v in RAISONS_DEROGATION.items()],
    }


def definir_options(db, dossier: DossierPresentation, page_garde=None, sommaire=None) -> dict:
    o = options_export(dossier)
    if page_garde is not None:
        o["page_garde"] = bool(page_garde)
    if sommaire is not None:
        o["sommaire"] = bool(sommaire)
    dossier.options_export = o
    flag_modified(dossier, "options_export")
    db.commit()
    return o


# ── Mesure de la décision 11 : combien de dossiers importés imposent leur fichier ──────

def mesurer_import(project: Project, analysis: dict) -> None:
    """Posé à chaque import RÉEL du dossier du marché (fichier analysé) : la mesure ne lit que
    l'agrégat (/metrics). N'écrit rien si la grille n'a pas été construite."""
    try:
        if not isinstance(analysis, dict) or not analysis.get("dce_available"):
            return
        det = analysis.get("details") if isinstance(analysis.get("details"), dict) else {}
        g = det.get("grille_notation")
        if not isinstance(g, dict):
            return
        project.dce_importe_le = utcnow()
        project.dce_fichier_impose = bool((g.get("contraintes") or {}).get("fichier_impose"))
    except Exception:       # noqa: BLE001 — une mesure ne casse jamais une analyse payée
        pass


def mesure_fichier_impose(db) -> dict:
    from sqlalchemy import func
    total = db.query(func.count(Project.id)).filter(Project.dce_importe_le.isnot(None)).scalar() or 0
    imp = db.query(func.count(Project.id)).filter(Project.dce_importe_le.isnot(None),
                                                  Project.dce_fichier_impose.is_(True)).scalar() or 0
    return {"dossiers_importes": int(total), "fichier_impose": int(imp),
            "part": round(imp / total, 4) if total else None, "seuil_decision": 0.2}
