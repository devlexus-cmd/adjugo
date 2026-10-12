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
    membre du groupement par son invitation. Le texte commun passe par UN seul accès
    (`versions_communes`) : export, compteur, blocage, limites, mention IA, dossier commun, RGPD ;
  • quota (décision 6a) : le dossier complet compte pour UNE analyse, débitée à la première action
    de l'IA ; elle comprend la première rédaction de chaque partie du plan (au plus autant que de
    parties actives) ; toute autre rédaction est une refonte, gratuite jusqu'à
    ATELIER_REGEN_GRATUITES fois par dossier (défaut 10), au-delà une analyse chacune, après accord
    exprès. Tant que la tâche qui porte l'analyse tourne, aucune autre action de l'IA ne démarre.
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
from app.services import faits_sources as fs
from app.services import memoire_export as me

logger = logging.getLogger("adjugo")

# ── Constantes ────────────────────────────────────────────────────────────────────────

A_ECRIRE, BROUILLON, RELU, VALIDE, A_REVALIDER = "a_ecrire", "brouillon", "relu", "valide", "a_revalider"
STATUTS = {A_ECRIRE: "À écrire", BROUILLON: "Brouillon", RELU: "Relue", VALIDE: "Validée",
           A_REVALIDER: "À revalider"}       # le sujet est la partie : « Relue », « Validée »
IA, UTILISATEUR, RACCOURCI = "ia", "utilisateur", "raccourci"
ORIGINES = {IA: "Rédigé avec Adjugo", UTILISATEUR: "Écrit ou modifié par vous", RACCOURCI: "Raccourci avec Adjugo"}
AUTEUR_ORG, AUTEUR_INVITATION = "organisation", "invitation"

TEXTE_MAX = 60000              # caractères par partie
INTITULE_MAX = 200
SECTIONS_MAX = 60
DOSSIER_ACHETEUR_MAX = 80000   # ANCIENNE lecture (dossier lu avant la lecture intégrale) : texte remis à l'IA
CADRE_MAX = 60000
LECTURE_MAX = 120000           # ANCIENNE lecture d'une pièce (comme l'import d'avant)


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return v if v > 0 else default
    except ValueError:
        return default


# Lecture INTÉGRALE (app/services/dce_texte.py) : à chaque partie, l'IA reçoit TOUS les règlements
# et TOUS les cadres de réponse en entier (dans DOSSIER_COMMUN_MAX caractères, ≈ 80 000 tokens, mis
# en cache de prompt d'une partie à l'autre), puis les PASSAGES_PAR_PARTIE passages des autres pièces
# les plus proches de la partie (recherche sans IA dans toutes les pièces lues).
DOSSIER_COMMUN_MAX = _env_int("ATELIER_DOSSIER_MAX_CARACTERES", 240000)
PASSAGES_PAR_PARTIE = _env_int("ATELIER_PASSAGES", 8)
CADRE_PLAN_MAX = 200000        # cadre de réponse lu pour construire le plan (lecture intégrale)
PIECES_AFFICHEES_MAX = 400     # pièces listées à l'écran (comme le plafond de la lecture)

JOB_REDIGER = "atelier_rediger"
JOB_RACCOURCIR = "atelier_raccourcir"
JOB_KINDS = (JOB_REDIGER, JOB_RACCOURCIR)

MSG_IA_PANNE = ("La rédaction n'a pas abouti : le service d'IA est indisponible pour le moment. Rien n'a été "
                "débité, réessayez dans quelques minutes.")
MSG_IRREGULIERE = "L'acheteur peut juger votre offre irrégulière."
MSG_DCE_CHANGE = ("Le dossier du marché a été importé de nouveau depuis la création du plan : vous pouvez "
                  "reconstruire le plan.")
MSG_DCE_ABSENT = ("Aucun dossier du marché importé : Adjugo rédige sans le règlement ni le cadre de réponse. "
                  "Importez-le sur la page du marché pour que le plan et le texte suivent l'acheteur.")
MSG_NON_VALIDE = "Dossier de présentation non validé"
# Couverture HONNÊTE de ce que lit le moteur (écran « Pièces du dossier de l'acheteur lues par Adjugo »).
MSG_LECTURE_ANCIENNE = ("Ce dossier a été lu avant la lecture intégrale : Adjugo remet à l'IA le règlement et le "
                        "cadre de réponse, puis seulement le début des autres pièces. Pour qu'il soit lu en entier, "
                        "relancez « Ré-analyser » sur la page du marché (compte pour une analyse).")
MSG_LECTURE_EXTRAIT = ("Seul le début du dossier du marché est disponible (le fichier n'est plus lisible) : "
                       "importez-le de nouveau sur la page du marché pour qu'il soit lu en entier.")
MSG_LECTURE_EN_COURS = ("La lecture intégrale du dossier du marché n'est pas encore terminée : en attendant, Adjugo "
                        "remet à l'IA le règlement, le cadre de réponse et le début des autres pièces.")
REMISES = {"entiere": "remise en entier à chaque partie",
           "debut": "début remis à chaque partie, le reste par passages",
           "passages": "passages choisis pour chaque partie"}

# Dérogation à l'export (décision 2b) : une raison choisie + un texte libre court. Seules les
# raisons qui répondent à ce qui bloque sont proposées (et acceptées).
RAISONS_DEROGATION = {
    "completerai_dans_word": "Je compléterai ces passages dans le fichier Word avant de déposer.",
    "relu_moi_meme": "J'ai relu ces faits moi-même.",
    "reduirai_dans_word": "Je réduirai le texte dans le fichier Word avant de déposer.",
    "redigerai_dans_word": "J'écrirai ces parties dans le fichier Word avant de déposer.",
    "partenaire_dans_word": "J'ajouterai la partie du partenaire dans le fichier Word avant de déposer.",
    "depot_en_l_etat": "Je dépose en l'état, en connaissance de cause.",
    "autre": "Autre raison.",
}
_RAISONS_PAR_BLOCAGE = {
    "a_completer": "completerai_dans_word",
    "faits_a_relire": "relu_moi_meme",
    "limite_depassee": "reduirai_dans_word",
    "parties_vides": "redigerai_dans_word",
    "attente_partenaire": "partenaire_dans_word",
}
DEROGATION_TEXTE_MIN, DEROGATION_TEXTE_MAX = 3, 300
MSG_PREMIERE_EN_COURS = ("Adjugo termine la première rédaction de ce dossier (celle qui compte pour l'analyse) : "
                         "attendez qu'elle se termine avant d'en lancer une autre.")


def derogations_possibles(gate: dict) -> list:
    """[{code, libelle}] des raisons qui répondent à CE qui bloque (aucune si rien ne bloque ou
    si le dossier n'a aucune partie)."""
    codes = [r["code"] for r in (gate or {}).get("raisons") or []]
    if not codes or "dossier_vide" in codes:
        return []
    keep = [_RAISONS_PAR_BLOCAGE[c] for c in codes if c in _RAISONS_PAR_BLOCAGE]
    keep += ["depot_en_l_etat", "autre"]
    return [{"code": k, "libelle": RAISONS_DEROGATION[k]} for k in dict.fromkeys(keep)]


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


def versions_communes(db, sections: list, lecteur: Lecteur) -> dict:
    """LE texte qu'un lecteur partage, partie par partie : la version courante des parties dont il
    est l'auteur ; pour la partie d'un autre auteur (vague 4 : un partenaire), SEULEMENT la version
    validée (envoyée), sinon rien. Seul accès au texte pour l'export, le compteur, le blocage, les
    limites, la mention IA, le dossier commun et l'export RGPD : un brouillon non envoyé ne sort
    jamais de chez son auteur."""
    propres = [s for s in sections if peut_voir_prive(s, lecteur)]
    autres = [s for s in sections if not peut_voir_prive(s, lecteur)]
    out = _courantes(db, propres)
    ids = [s.validated_version_id for s in autres if s.validated_version_id]
    if ids:
        by_id = {v.id: v for v in db.query(DossierSectionVersion).filter(DossierSectionVersion.id.in_(ids)).all()}
        for s in autres:
            v = by_id.get(s.validated_version_id)
            if v is not None and v.section_id == s.id:
                out[s.id] = v
    return out


def en_attente_d_un_partenaire(sections: list, lecteur: Lecteur, communes: dict) -> list:
    """Parties d'un autre auteur dont le texte n'a pas encore été envoyé (validé)."""
    return [s for s in sections if not peut_voir_prive(s, lecteur) and communes.get(s.id) is None]


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


def cle_lecture(project: Project) -> str:
    """La lecture intégrale rangée du marché (Project.dce_file_key) : change à chaque nouvelle
    lecture (ré-import, ré-analyse qui complète une lecture inachevée)."""
    return str(getattr(project, "dce_file_key", None) or "")


def _lecture_integrale(project: Project, content: bytes):
    """La lecture intégrale rangée, SEULEMENT si elle est celle du fichier importé le plus récent
    (même empreinte) et qu'au moins une pièce a du texte ; sinon None (ancienne analyse, lecture
    d'un fichier précédent, lecture encore en cours, stockage illisible)."""
    from app.services import dce_texte
    try:
        payload = dce_texte.charger(project)
    except Exception:       # noqa: BLE001
        payload = None
    if not payload or not any((p.get("texte") or "").strip() for p in payload.get("pieces") or []):
        return None
    if payload.get("source_empreinte") != hashlib.sha256(content or b"").hexdigest():
        return None
    return payload


def _piece_affichee(i: int, p: dict, remis: dict) -> dict:
    """Une pièce telle que l'écran la montre : statut de LECTURE (lue en entier, en partie, non lue
    et pourquoi) et ce que le moteur en remet à l'IA."""
    from app.services import dce_lecture as lec
    from app.services import dce_pieces as dp
    statut = p.get("statut") or lec.NON_LU
    if i in remis:
        remise = "entiere" if remis[i] else "debut"
    elif (p.get("texte") or "").strip():
        remise = "passages"
    else:
        remise = ""
    raison = "" if statut == lec.LU else str(p.get("detail") or lec.raison_texte(p.get("raison")) or "")[:300]
    return {"nom": str(p.get("nom") or "")[:200], "type": p.get("type") or dp.AUTRE,
            "libelle": p.get("libelle") or dp.label(p.get("type")), "statut": statut, "raison": raison,
            "pages": p.get("pages"), "pages_lues": p.get("pages_lues"), "caracteres": int(p.get("caracteres") or 0),
            "lu_en_entier": statut == lec.LU, "remise": remise, "remise_libelle": REMISES.get(remise, "")}


def _lu_integral(out: dict, payload: dict) -> dict:
    from app.services import dce_lecture as lec
    from app.services import dce_pieces as dp
    from app.services import dce_texte
    pieces = payload.get("pieces") or []
    rem = dce_texte.pieces_remises(payload, DOSSIER_COMMUN_MAX)
    remis = {x["index"]: x["entier"] for x in rem["pieces"]}
    cadre = "\n\n".join(p.get("texte") or "" for p in pieces if p.get("type") == dp.CADRE)
    cov = lec.couverture(payload)
    cadre = cadre[:CADRE_PLAN_MAX]
    out.update(integral=True, texte="", cadre=cadre, cadre_decoupable=ap.cadre_decoupable(cadre),
               couverture={"complet": bool(cov.get("complet")), "message": cov.get("message") or ""},
               message_lecture="",
               pieces=[_piece_affichee(i, p, remis) for i, p in enumerate(pieces)][:PIECES_AFFICHEES_MAX])
    return out


def _lecture_en_cours(db, project: Project) -> bool:
    """Une lecture en tâche de fond tourne VRAIMENT pour ce marché : l'état « en cours » ET sa tâche
    en attente ou en cours (comme la page du marché). Une lecture morte au redémarrage du serveur
    (tâche passée en erreur, état du marché resté « en cours ») n'est plus dite « pas encore terminée »."""
    wf = project.workflow if isinstance(project.workflow, dict) else {}
    st = wf.get("lecture") if isinstance(wf.get("lecture"), dict) else {}
    if st.get("etat") != "en_cours" or not st.get("job_id"):
        return False
    try:
        j = db.get(Job, int(st["job_id"]))
    except (TypeError, ValueError):
        return False
    return bool(j is not None and j.status in ("pending", "running"))


def lire_dossier_acheteur(db, project: Project, member_ids: list, integrale: bool = True) -> dict:
    """Lecture du dossier du marché, pièce par pièce, SANS IA : {cle, lecture_cle, source,
    nom_fichier, integral, pieces, couverture, message_lecture, cadre, texte}. Ne lève pas.

    • Lecture INTÉGRALE rangée pour le fichier importé le plus récent (app/services/dce_texte.py) :
      `integral` vrai, chaque pièce avec son statut de lecture (lue en entier, en partie, non lue et
      pourquoi) et ce que le moteur en remet à l'IA ; `texte` vide — le moteur le compose à chaque
      rédaction depuis la lecture rangée (règlements et cadres en entier, passages du reste).
    • Sinon (dossier lu avant la lecture intégrale, lecture en cours) : ANCIENNE lecture bornée,
      `texte` = règlement et cadre de réponse en tête et en entier, le reste borné, et un message
      honnête qui dit comment obtenir la lecture intégrale."""
    from app.services import dce_pieces as dp
    cle = cle_dossier_acheteur(db, project, member_ids)
    lec_cle = cle_lecture(project)
    # Clé du cache : le fichier, la lecture rangée, le mode, et l'état de la lecture en tâche de fond
    # (« lecture en cours » ne doit pas rester affiché après un échec qui ne range rien).
    en_cours = _lecture_en_cours(db, project)
    ck = f"{cle}|{lec_cle}|{'i' if integrale else 'a'}|{'c' if en_cours else ''}"
    if ck in _LECTURES:
        return dict(_LECTURES[ck])
    out = {"cle": cle, "lecture_cle": lec_cle, "source": "aucun", "nom_fichier": "", "integral": False,
           "pieces": [], "couverture": None, "message_lecture": "", "cadre": "", "cadre_decoupable": False,
           "texte": "", "lu_le": _now_iso()}
    pieces = []
    if cle.startswith("fichier:"):
        doc = _dce_document(db, project, member_ids)
        try:
            from app.services.storage import get_storage
            content = get_storage().load(doc.file_key)
            out.update(source="fichier", nom_fichier=str(doc.name or "")[:200])
            payload = _lecture_integrale(project, content) if integrale else None
            if payload is not None:
                _lu_integral(out, payload)
                _garder(ck, out)
                return out
            from app.services.analysis import extract_dce_pieces
            pieces, _archive = extract_dce_pieces(doc.name, content, max_chars=LECTURE_MAX)
            out["message_lecture"] = MSG_LECTURE_EN_COURS if en_cours else MSG_LECTURE_ANCIENNE
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
            out["message_lecture"] = MSG_LECTURE_EXTRAIT
    if pieces:
        cadre = "\n\n".join(p.get("texte") or "" for p in pieces if p.get("type") == dp.CADRE)
        texte, meta = dp.compose(pieces, DOSSIER_ACHETEUR_MAX)
        out.update(cadre=cadre[:CADRE_MAX], texte=texte, cadre_decoupable=ap.cadre_decoupable(cadre[:CADRE_MAX]),
                   pieces=[{"nom": str(m.get("nom") or "")[:200], "type": m.get("type"),
                            "libelle": m.get("libelle"), "caracteres": int(m.get("caracteres") or 0),
                            "lu_en_entier": bool(m.get("lu_en_entier")),
                            # Ancienne lecture : « en entier » = remis en entier à l'IA, rien de plus.
                            "statut": "lu_en_entier" if m.get("lu_en_entier") else "lu_en_partie",
                            "raison": "" if m.get("lu_en_entier") else "seul le début est remis à l'IA",
                            "remise": "entiere" if m.get("lu_en_entier") else "debut"}
                           for m in meta][:30])
    _garder(ck, out)
    return out


def _garder(ck: str, out: dict) -> None:
    if len(_LECTURES) >= _LECTURES_MAX:
        _LECTURES.pop(next(iter(_LECTURES)), None)
    _LECTURES[ck] = dict(out)


def _oublier_lectures(cle: str) -> None:
    for k in [k for k in _LECTURES if k.split("|", 1)[0] == cle]:
        _LECTURES.pop(k, None)


def dce_lu_en_base(lu: dict) -> dict:
    """Ce que le dossier garde de la lecture (dossier_presentations.dce_lu) : jamais le texte d'une
    lecture intégrale, ni celui de ses cadres de réponse (il reste dans le stockage du marché,
    supprimé avec lui ; le plan le relit de là). Seul est gardé si le cadre se découpe en questions
    (`cadre_decoupable`, pour proposer la base « cadre » sans le relire à chaque affichage)."""
    out = dict(lu or {})
    if out.get("integral"):
        out["texte"] = ""
        out["cadre"] = ""
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

def _plan(db, project: Project, member_ids: list, lu: dict, base: str) -> dict:
    return ap.build_plan(_analysis(project), lu.get("cadre") or "", base=base,
                         en_groupement=_en_groupement(db, project),
                         dossier_present=(lu.get("cle") or "aucun") != "aucun")


def proposition(db, project: Project, member_ids: list, base: str = "auto") -> dict:
    """Plan proposé (sans IA, sans rien enregistrer)."""
    return _plan(db, project, member_ids, lire_dossier_acheteur(db, project, member_ids), base)


def _plan_meta(plan: dict, base: str, cle_dce: str = "") -> dict:
    return {"source": plan.get("source"), "message": plan.get("message") or "",
            "fichier_impose": bool(plan.get("fichier_impose")), "message_fichier": plan.get("message_fichier") or "",
            "avertissement_fichier": plan.get("avertissement_fichier") or "",
            "cadre_non_decoupe": bool(plan.get("cadre_non_decoupe")),
            "criteres_hors_dossier": plan.get("criteres_hors_dossier") or [],
            "dossier_present": plan.get("dossier_present", True) is not False,
            # Ce que le plan a lu : le dossier du marché (clé) et la grille (lignes, poids) — pour
            # dire ensuite ce qui a changé, sans confondre avec la lecture que le moteur rafraîchit.
            "cle_dce": cle_dce, "grille": plan.get("grille") or [],
            "limites": plan.get("limites") or {}, "base_demandee": base, "construit_le": _now_iso()}


def _section_from_plan(dossier: DossierPresentation, s: dict, ordre: int) -> DossierSection:
    return DossierSection(
        dossier_id=dossier.id, project_id=dossier.project_id, owner_id=dossier.owner_id, ordre=ordre,
        numero=str(s.get("numero") or "")[:20], intitule=str(s.get("intitule") or "")[:300],
        niveau=int(s.get("niveau") or 1), parents=s.get("parents") or [], question=str(s.get("question") or ""),
        source_plan=str(s.get("source_plan") or ap.LIBRE)[:12], critere=str(s.get("critere") or "")[:300],
        critere_id=str(s.get("critere_id") or "")[:20], poids=str(s.get("poids") or "")[:40],
        poids_source=str(s.get("poids_source") or "")[:20] if s.get("poids") else "",
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
    plan = _plan(db, project, member_ids, lu, base)
    d = DossierPresentation(project_id=project.id, owner_id=owner_id, created_by_user_id=user.id,
                            plan_source=plan["source"], plan_meta=_plan_meta(plan, base, lu.get("cle") or ""),
                            dce_lu=dce_lu_en_base(lu), analyse_debitee=False, regenerations=0, regenerations_payantes=0,
                            premieres_incluses=0, options_export={"page_garde": True, "sommaire": True}, version=0)
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
                      base: str = "auto", remplacer: bool = False, lecteur: Optional[Lecteur] = None) -> DossierPresentation:
    """Reconstruit le plan. Les parties actuelles QUE LE LECTEUR PEUT ÉCRIRE sont RETIRÉES (jamais
    supprimées : leurs versions restent consultables et peuvent être remises) ; si l'une a déjà du
    texte, l'utilisateur doit le confirmer (remplacer=True). La partie d'un partenaire (vague 4)
    reste dans le plan : on ne retire jamais la part d'un autre."""
    lecteur = lecteur or Lecteur.organisation(dossier.owner_id, user)
    act = sections_actives(db, dossier)
    miennes = [s for s in act if peut_ecrire(s, lecteur)]
    _verifier_aucune_tache(db, miennes)
    if _a_du_texte(db, [s.id for s in miennes]) and not remplacer:
        raise AtelierError(409, "plan_remplacement_a_confirmer",
                           "Des parties ont déjà du texte. Reconstruire le plan les retire (leurs textes restent "
                           "dans l'historique et peuvent être remis) : confirmez pour continuer.")
    _oublier_lectures(cle_dossier_acheteur(db, project, member_ids))
    lu = lire_dossier_acheteur(db, project, member_ids)
    plan = _plan(db, project, member_ids, lu, base)
    now = utcnow()
    for s in miennes:
        s.retiree_at = now
    dossier.plan_source = plan["source"]
    dossier.plan_meta = _plan_meta(plan, base, lu.get("cle") or "")
    dossier.dce_lu = dce_lu_en_base(lu)
    dossier.version = (dossier.version or 0) + 1
    gardees = [s for s in act if s not in miennes]
    n = 0
    for n, s in enumerate(plan["sections"][:max(0, SECTIONS_MAX - len(gardees))]):
        db.add(_section_from_plan(dossier, s, n))
    for i, s in enumerate(gardees):
        s.ordre = n + 1 + i
    db.commit()
    db.refresh(dossier)
    return dossier


def _renumeroter(db, dossier: DossierPresentation) -> None:
    for i, s in enumerate(sections_actives(db, dossier)):
        s.ordre = i


def _place_dans_le_cadre(act: list, section: DossierSection) -> int:
    """Rang où remettre une question du cadre imposé : avant la première question du cadre dont le
    numéro est plus grand (le cadre de l'acheteur commande l'ordre)."""
    k = ap._num_key(section.numero or "")
    for i, x in enumerate(act):
        if x.source_plan == ap.CADRE and ap._num_key(x.numero or "") > k:
            return i
    return len(act)


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
    act = sections_actives(db, dossier)
    if dossier.plan_source == ap.CADRE and section.source_plan == ap.CADRE:
        # Le cadre imposé commande : la question reprend SA place (son numéro), pas la dernière.
        act.insert(_place_dans_le_cadre(act, section), section)
    else:
        act.append(section)
    section.retiree_at = None
    for i, x in enumerate(act):
        x.ordre = i
    db.commit()
    db.refresh(section)
    return section


# ── La grille a changé depuis le plan (« Comment vous serez noté ») ───────────────────

def changements_grille(project: Project, dossier: DossierPresentation, actives: list, retirees: list) -> Optional[dict]:
    """Ce qui a changé dans « Comment vous serez noté » depuis le plan : critères confirmés depuis
    (à AJOUTER au plan, jamais en reconstruisant tout), poids confirmés ou modifiés, critères qui ne
    sont plus retenus. None quand rien n'a changé ou quand le plan suit le cadre imposé (le cadre
    commande, la grille n'y crée pas de partie)."""
    if dossier.plan_source == ap.CADRE:
        return None
    lignes = ap.lignes_techniques(_analysis(project))
    par_id = {ln["id"]: ln for ln in lignes}
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    # Connus : rattachés à une partie (même retirée) ou déjà lus quand le plan a été construit
    # (un plan simple choisi exprès ne fait pas réapparaître les critères qu'il a laissés de côté).
    connus = {str(s.critere_id) for s in list(actives) + list(retirees) if s.critere_id}
    connus |= {str(x[0]) for x in (meta.get("grille") or []) if isinstance(x, (list, tuple)) and x}
    nouveaux = [{"id": ln["id"], "critere": ln["critere"], "poids": ln["poids"], "poids_source": ln["poids_source"]}
                for ln in lignes if ln["id"] not in connus]
    poids, plus_retenus = [], []
    for s in actives:
        if not s.critere_id or s.author_kind != AUTEUR_ORG:
            continue
        ln = par_id.get(str(s.critere_id))
        if ln is None:
            if s.source_plan == ap.GRILLE or s.partie_de_critere:
                plus_retenus.append({"section_id": s.id, "critere": s.critere})
            continue
        change = ln["poids"] != (s.poids or "") or (bool(s.poids_source) and ln["poids_source"] != s.poids_source)
        if change:
            poids.append({"section_id": s.id, "critere": s.critere, "ancien": s.poids or "", "nouveau": ln["poids"],
                          "poids_source": ln["poids_source"]})
    if not (nouveaux or poids or plus_retenus):
        return None
    parts = []
    if nouveaux:
        n = len(nouveaux)
        parts.append(("Un critère a été confirmé" if n == 1 else f"{n} critères ont été confirmés")
                     + " dans « Comment vous serez noté » depuis la création du plan : "
                     + ", ".join(f"« {x['critere']} »" for x in nouveaux[:6]) + ".")
    noms_poids = list(dict.fromkeys(x["critere"] for x in poids))       # un critère découpé : dit une fois
    if noms_poids:
        parts.append(("Le poids retenu pour " if len(noms_poids) == 1 else "Les poids retenus pour ")
                     + ", ".join(f"« {c} »" for c in noms_poids[:6])
                     + (" a changé dans « Comment vous serez noté »." if len(noms_poids) == 1
                        else " ont changé dans « Comment vous serez noté »."))
    noms_retires = list(dict.fromkeys(x["critere"] for x in plus_retenus))
    if noms_retires:
        parts.append(", ".join(f"« {c} »" for c in noms_retires[:6])
                     + (" n'est plus retenu" if len(noms_retires) == 1 else " ne sont plus retenus")
                     + (" : vous pouvez retirer la partie." if len(plus_retenus) == 1 else
                        " : vous pouvez retirer les parties qui s'y rattachent."))
    return {"nouveaux": nouveaux, "poids": poids, "plus_retenus": plus_retenus, "message": " ".join(parts),
            "peut_appliquer": bool(nouveaux or poids)}


def appliquer_grille(db, project: Project, dossier: DossierPresentation, lecteur: Lecteur) -> dict:
    """Met le plan à jour d'après « Comment vous serez noté » SANS rien retirer : une partie de plus
    par critère confirmé depuis (à la fin du plan, déplaçable), le poids et sa provenance repris
    pour les parties existantes. Aucune IA, aucun débit."""
    if dossier.plan_source == ap.CADRE:
        raise AtelierError(409, "plan_du_cadre", "Le plan suit le cadre de réponse de l'acheteur : la grille n'y "
                                                 "ajoute pas de partie.")
    act = sections_actives(db, dossier)
    ch = changements_grille(project, dossier, act, sections_retirees(db, dossier))
    if not ch or not ch["peut_appliquer"]:
        raise AtelierError(409, "rien_a_appliquer", "Le plan suit déjà « Comment vous serez noté ».")
    if len(act) + len(ch["nouveaux"]) > SECTIONS_MAX:
        raise AtelierError(422, "trop_de_parties", f"Un dossier compte au plus {SECTIONS_MAX} parties.")
    par_id = {ln["id"]: ln for ln in ap.lignes_techniques(_analysis(project))}
    for x in ch["poids"]:
        s = next((y for y in act if y.id == x["section_id"]), None)
        if s is not None and peut_ecrire(s, lecteur):
            s.poids, s.poids_source = x["nouveau"][:40], (x["poids_source"] or "")[:20] if x["nouveau"] else ""
            s.lock_version = (s.lock_version or 0) + 1
    rang = len(act)
    for x in ch["nouveaux"]:
        db.add(_section_from_plan(dossier, ap.section_de_critere(par_id[x["id"]]), rang))
        rang += 1
    meta = dict(dossier.plan_meta) if isinstance(dossier.plan_meta, dict) else {}
    meta["grille"] = ap.empreinte_grille(_analysis(project))
    if ch["nouveaux"]:
        meta["message"] = ("Plan construit d'après le dossier du marché, complété par les critères que vous avez "
                           "confirmés dans « Comment vous serez noté ».")
    dossier.plan_meta = meta
    flag_modified(dossier, "plan_meta")
    dossier.version = (dossier.version or 0) + 1
    db.commit()
    return {"ajoutees": len(ch["nouveaux"]), "poids_mis_a_jour": len(ch["poids"])}


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
    # Vos faits sont vos déclarations ; un fait déjà à relire le reste, un fait relié à sa source la
    # garde (vague 3, app/services/faits_sources.py).
    faits = fs.controler(t, ctx.fiches_de_version(db, base), acheteur=None, noms_entreprise=ctx.noms_entreprise,
                         section_entreprise=section_sur_l_entreprise(section), mode="utilisateur",
                         anciens=(base.faits if base else []), base_texte=(base.texte if base else ""))
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
    Adjugo ne dit jamais qu'un fait est bon : c'est l'utilisateur qui déclare l'avoir relu. Un fait
    relié à sa source ne se « relit » pas (409), sauf si sa source n'est plus utilisable : il
    redevient alors à relire, comme à l'écran."""
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
    if hit.get("type") == far.RESTE:
        raise AtelierError(409, "faits_non_detailles", "Ces faits ne sont pas détaillés : découpez ou raccourcissez la "
                                                       "partie pour les relire un par un.")
    if hit.get("statut") == fs.AVEC_SOURCE:
        val = _valides_de(db, section.owner_id, section.project_id, [faits])
        if fs.ajuster([hit], val)[0].get("statut") == fs.AVEC_SOURCE:
            raise AtelierError(409, "fait_avec_source", "Ce fait est déjà relié à l'endroit où Adjugo l'a trouvé.")
        i = faits.index(hit)
        faits[i] = hit = fs.source_perdue(hit)
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


# ── Vague 3 (A) : relire les sources d'une partie, ajouter une source à un fait ─────────

def _valides_de(db, owner_id: int, project_id: Optional[int], faits_listes) -> dict:
    """Preuves et extraits encore utilisables pour ces listes de faits (relu à chaque lecture)."""
    from app.services import preuves as pv
    try:
        return fs.valides(db, owner_id, pv.membres(db, owner_id), project_id, faits_listes)
    except Exception as e:      # noqa: BLE001 — au pire, rien n'est ajusté (jamais bloquant)
        logger.warning("atelier : validité des sources illisible (compte %s) : %s", owner_id, type(e).__name__)
        return None


def recontroler(db, ctx: "Contexte", project: Project, section: DossierSection, lecteur: Lecteur,
                commit: bool = True) -> DossierSectionVersion:
    """Relit les sources de la version courante, SANS IA et sans changer le texte : une preuve
    ajoutée relie le fait qu'elle contient, une preuve retirée ou expirée le rend à relire. « Relu
    par vous » est gardé pour le même fait dans la même phrase ; vos déclarations restent les vôtres."""
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    section = _verrouiller(db, section)
    _verifier_aucune_tache(db, [section])
    v = version_courante(db, section)
    if v is None or not (v.texte or "").strip():
        raise AtelierError(422, "partie_vide", "Cette partie n'a pas encore de texte.")
    ecrit_par_vous = v.origine == UTILISATEUR
    acheteur = None if ecrit_par_vous else acheteur_du_marche(db, project, ctx.member_ids)
    faits = fs.controler(v.texte or "", ctx.fiches_de_version(db, v), acheteur=acheteur,
                         noms_entreprise=ctx.noms_entreprise, section_entreprise=section_sur_l_entreprise(section),
                         mode="utilisateur" if ecrit_par_vous else "ia", anciens=v.faits or [])
    v.faits = faits
    flag_modified(v, "faits")
    section.lock_version = (section.lock_version or 0) + 1
    if commit:
        db.commit()
        db.refresh(v)
    return v


def _fait_a_relire(db, section: DossierSection, fait_id: str) -> tuple:
    v = version_courante(db, section)
    if v is None:
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    hit = next((x for x in (v.faits or []) if isinstance(x, dict) and x.get("id") == fait_id), None)
    if hit is None or hit.get("type") == far.RESTE:
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    if hit.get("type") == fs.ENGAGEMENT:
        raise AtelierError(409, "engagement", "Un engagement ne se prouve pas par une fiche : confirmez-le, corrigez-le "
                                              "ou retirez-le.")
    return v, dict(hit)


def candidats_source(db, ctx: "Contexte", section: DossierSection, lecteur: Lecteur, fait_id: str) -> dict:
    """Pour « Ajouter une source » : les preuves utilisables qui CONTIENNENT ce fait (même valeur et
    même unité, même certification, nom ou matériel), et la fiche « déclaré par vous » proposée."""
    if not peut_voir_prive(section, lecteur):
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    _v, hit = _fait_a_relire(db, section, fait_id)
    from app.services import preuves as pv
    preuves = [{"ref": f.ref, "id": f.preuve_id, "nature": f.nature, "texte": f.texte, "source_libelle": f.libelle}
               for f in ctx.fiches(db) if f.ref.startswith(fs.PREUVE) and fs.fiche_contient(f, hit)]
    prop = fs.proposition_declaration(hit)
    return {"fait": {k: hit.get(k) for k in ("id", "fait", "type", "phrase", "statut")}, "preuves": preuves,
            "proposition": prop,
            "natures": [{"code": n, "libelle": pv.NATURE_LIBELLES[n], "champs": list(pv.CHAMPS[n]),
                         "requis": list(pv.REQUIS[n])} for n in prop.get("natures") or []]}


def ajouter_source(db, ctx: "Contexte", project: Project, section: DossierSection, lecteur: Lecteur, fait_id: str,
                   *, preuve_id=None, nature: str = None, valeur: dict = None, user: Optional[User] = None) -> dict:
    """« Ajouter une source » à un fait à relire, SANS IA et sans toucher au texte : relier une
    preuve utilisable qui le contient, ou le DÉCLARER (nouvelle preuve « déclaré par vous », dans
    « Mes preuves »). La fiche doit contenir le fait tel qu'il est écrit, sinon rien n'est créé.
    Puis la partie est recontrôlée : tout fait que la fiche contient y est relié."""
    from app.services import preuves as pv
    if not peut_ecrire(section, lecteur):
        raise AtelierError(403, "partie_d_un_partenaire", "Cette partie est rédigée par un partenaire.")
    _v, hit = _fait_a_relire(db, section, fait_id)
    if preuve_id not in (None, ""):
        f = next((x for x in ctx.fiches(db) if x.ref.startswith(fs.PREUVE) and str(x.preuve_id) == str(preuve_id)),
                 None)
        if f is None:
            raise AtelierError(404, "preuve_introuvable", "Preuve introuvable, ou plus utilisable (retirée ou "
                                                          "expirée).")
        if not fs.fiche_contient(f, hit):
            raise AtelierError(422, "preuve_sans_ce_fait",
                               f"Cette preuve ne contient pas « {hit.get('fait')} » : choisissez-en une autre, ou "
                               "corrigez le texte.")
    else:
        propre = pv.valider_valeur(nature, valeur)
        essai = fs.Fiche("F0", fs.T_DECLARE, fs.LIB_DECLARE, pv.texte_de(nature, propre),
                         extra=fs._adjacents(nature, propre), nature=nature, valeur=propre)
        if not fs.fiche_contient(essai, hit):
            raise AtelierError(422, "fiche_sans_ce_fait",
                               f"Cette fiche ne contient pas « {hit.get('fait')} » tel qu'il est écrit (même nombre, "
                               "même unité) : corrigez la fiche, ou corrigez le texte.")
        pv.creer(db, ctx.owner_id, nature=nature, valeur=propre, type_source=pv.DECLARE, origine="saisie",
                 user=user, commit=False)
        ctx._fiches = None          # la nouvelle preuve fait partie des faits autorisés
    v = recontroler(db, ctx, project, section, lecteur, commit=False)
    db.commit()
    db.refresh(v)
    nouveau = next((x for x in (v.faits or []) if isinstance(x, dict) and x.get("id") == fait_id), None)
    return nouveau or hit


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
        # Noms des fiches « Équipe » de « Mes preuves » (vague 3) : masqués eux aussi avant l'IA.
        from app.services.preuves import personnes
        self.preuves_team = personnes(db, [owner_id])
        self.noms_entreprise = [x for x in ([comp.name if comp else ""] + [p["nom"] for p in self.partenaires]) if x]
        self.sources_entreprise = [self.profil, self.equipe, self.chiffrage] + [p["texte"] for p in self.partenaires]

    def faits_autorises(self) -> dict:
        return {"profil": self.profil, "equipe": self.equipe, "chiffrage": self.chiffrage,
                "partenaires": "\n".join(p["texte"] for p in self.partenaires)}

    def pseudonymiseur(self):
        from app.services.pii import from_team
        return from_team(self.team + self.preuves_team + self.partner_team)

    # ── Vague 3 (A) : les faits NUMÉROTÉS et TYPÉS (app/services/faits_sources.py) ──
    def fiches(self, db, pseudonymiseur=None) -> list:
        """Les faits autorisés de l'entreprise pour ce marché, numérotés et typés : preuves
        utilisables de « Mes preuves » [F#] (numéros stables), profil [P#], équipe du profil [E#],
        chiffrage [C#] (votre estimation), apports envoyés par les partenaires [G#]. Les extraits de
        « Mon savoir-faire » [S#] s'y ajoutent partie par partie. Jamais le dossier de l'acheteur."""
        if getattr(self, "_fiches", None) is None or pseudonymiseur is not None:
            try:
                preuves = fs.fiches_preuves(db, self.owner_id, project_id=self.project_id,
                                            pseudonymiseur=pseudonymiseur)
            except Exception as e:      # noqa: BLE001 — « Mes preuves » illisible : le reste suffit
                logger.warning("atelier : preuves illisibles (compte %s) : %s", self.owner_id, type(e).__name__)
                preuves = []
            self._fiches = preuves + fs.fiches_contexte(self.profil, self.equipe, self.chiffrage, self.partenaires)
        return list(self._fiches)

    def fiches_de_version(self, db, v) -> list:
        """Fiches pour relire une version déjà écrite : celles de l'entreprise, plus les extraits
        de « Mon savoir-faire » qu'elle cite ou dont un fait dépend (relus par leur numéro, dans
        l'organisation seulement ; un morceau retiré ne revient pas)."""
        out = self.fiches(db)
        if v is None:
            return out
        refs = {}
        for x in (v.sources or []):
            if isinstance(x, dict) and str(x.get("ref") or "").startswith(fs.EXTRAIT) and x.get("chunk_id"):
                refs[x["ref"]] = x
        for x in fs.avec_source(v.faits):
            src = x.get("source") or {}
            if str(src.get("ref") or "").startswith(fs.EXTRAIT) and src.get("chunk_id"):
                refs.setdefault(src["ref"], {"ref": src["ref"], "chunk_id": src["chunk_id"],
                                             "doc_name": src.get("doc_nom") or ""})
        ids = []
        for x in refs.values():
            try:
                ids.append(int(x["chunk_id"]))
            except (TypeError, ValueError):
                pass
        if not ids:
            return out
        from app.models import KnowledgeChunk
        rows = {c.id: c for c in db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(ids),
                                                                 KnowledgeChunk.user_id.in_(self.member_ids)).all()}
        chunks = []
        for ref, x in sorted(refs.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0):
            c = rows.get(int(x["chunk_id"])) if str(x["chunk_id"]).isdigit() else None
            if c is not None:
                chunks.append({"ref": ref, "chunk_id": c.id, "text": c.text or "",
                               "doc_name": x.get("doc_name") or ""})
        return out + fs.fiches_extraits(chunks)


def _acheteur(project: Project, lu: dict, payload: Optional[dict]) -> "fs.Acheteur":
    """Le dossier de l'acheteur, pièce par pièce, pour rapprocher les phrases sur le marché (et dire
    qu'un fait d'une phrase sur l'entreprise vient de lui). Lecture intégrale : toutes les pièces
    lues ; sinon le texte de l'ancienne lecture ; rien si aucun dossier n'est importé."""
    pieces = []
    if payload:
        pieces = [(p.get("libelle") or p.get("nom") or "", p.get("texte") or "") for p in payload.get("pieces") or []
                  if (p.get("texte") or "").strip()]
    elif (lu or {}).get("texte"):
        pieces = [("Dossier de l'acheteur", lu.get("texte") or "")]
    return fs.Acheteur(pieces)


def acheteur_du_marche(db, project: Project, member_ids: list) -> "fs.Acheteur":
    """Le dossier de l'acheteur tel qu'il est maintenant (recontrôle d'une partie)."""
    lu = lire_dossier_acheteur(db, project, member_ids)
    payload = None
    if lu.get("integral"):
        from app.services import dce_texte
        try:
            payload = dce_texte.charger(project)
        except Exception:       # noqa: BLE001
            payload = None
        if not payload:
            lu = lire_dossier_acheteur(db, project, member_ids, integrale=False)
    return _acheteur(project, lu, payload)


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


def _faits_tels_quels(v) -> list:
    return (v.faits or []) if v is not None else []


def etat_hash(dossier: DossierPresentation, sections: list, courantes: dict, limites: list, faits_de=None) -> str:
    """Empreinte de l'état exporté (textes, faits traités, options, limites) : une dérogation ne
    vaut que pour CET état ; au moindre changement, l'export se contrôle de nouveau. `faits_de` :
    les faits d'une version tels qu'ils sont lus (une source perdue rend un fait à relire)."""
    fd = faits_de or _faits_tels_quels
    payload = {"o": options_export(dossier), "l": [(x["portee"], x["section_id"], x["type"], x["valeur"], x["mesure"])
                                                   for x in limites],
               "s": [(s.id, s.ordre, s.intitule, (courantes.get(s.id).empreinte if courantes.get(s.id) else ""),
                      sorted((f.get("id"), f.get("statut")) for f in (fd(courantes.get(s.id))
                                                                       if courantes.get(s.id) else [])
                             if isinstance(f, dict)))
                     for s in sections]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()


def blocage(dossier: DossierPresentation, sections: list, courantes: dict, rangs: dict, limites: list,
            attente: Optional[list] = None, faits_de=None) -> dict:
    """Ce qui empêche l'export (décision 2b) et ce qui reste à signaler. {bloque, raisons, etat_hash,
    derogation (valable pour cet état) | None, avertissements}. `courantes` est le texte COMMUN
    (versions_communes) ; `attente` : parties d'un partenaire dont le texte n'est pas encore envoyé."""
    raisons = []
    trous, faits, vides, non_valides, partenaires = [], [], [], [], []
    attente_ids = {s.id for s in (attente or [])}
    for s in sections:
        v = courantes.get(s.id)
        titre = ax.titre_section({"numero": rangs.get(s.id, ""), "intitule": s.intitule})
        texte = (v.texte if v is not None else "") or ""
        if s.id in attente_ids:
            partenaires.append({"section_id": s.id, "titre": titre})
            continue
        if not texte.strip():
            vides.append({"section_id": s.id, "titre": titre})
        n = len(me.placeholders(texte))
        if n:
            trous.append({"section_id": s.id, "titre": titre, "nombre": n})
        nf = far.non_traites((faits_de or _faits_tels_quels)(v) if v is not None else [])
        if nf:
            faits.append({"section_id": s.id, "titre": titre, "nombre": nf})
        # La partie d'un partenaire est commune quand il l'a envoyée (validée) : rien à valider ici.
        if s.statut != VALIDE and s.author_kind == AUTEUR_ORG:
            non_valides.append({"section_id": s.id, "titre": titre, "statut": s.statut})
    if not sections:
        raisons.append({"code": "dossier_vide", "message": "Le dossier de présentation n'a aucune partie.",
                        "sections": []})
    if vides:
        raisons.append({"code": "parties_vides", "nombre": len(vides), "sections": vides,
                        "message": f"{len(vides)} partie{'s' if len(vides) > 1 else ''} sans texte."})
    if partenaires:
        n = len(partenaires)
        raisons.append({"code": "attente_partenaire", "nombre": n, "sections": partenaires,
                        "message": (f"{n} partie{'s' if n > 1 else ''} en attente du partenaire qui "
                                    f"{'les rédige' if n > 1 else 'la rédige'}.")})
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
    eh = etat_hash(dossier, sections, courantes, limites, faits_de=faits_de)
    der = dossier.derogation if isinstance(dossier.derogation, dict) else None
    codes = {r["code"] for r in raisons}
    valide = bool(der and der.get("etat_hash") == eh and codes <= set(der.get("raisons") or []) and raisons
                  and "dossier_vide" not in codes)
    avert = []
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    if meta.get("fichier_impose"):
        # Une seule phrase par cas (décision 11) : jamais deux consignes accolées.
        avert.append({"code": "fichier_impose",
                      "message": ap.avertissement_fichier(True, dossier.plan_source)})
    if non_valides:
        avert.append({"code": "non_valide", "nombre": len(non_valides), "sections": non_valides,
                      "message": (f"{MSG_NON_VALIDE} : {len(non_valides)} partie"
                                  f"{'s' if len(non_valides) > 1 else ''} à valider.")})
    return {"bloque": bool(raisons), "raisons": raisons, "etat_hash": eh,
            "derogation": _derogation_out(der) if valide else None,
            "peut_exporter": (not raisons) or valide, "avertissements": avert}


def faits_lus(db, dossier: DossierPresentation, project: Project, courantes: dict):
    """Les faits d'une version tels que l'export les lit : un fait relié à une preuve retirée ou
    expirée (ou à un extrait retiré) redevient à relire et bloque l'export comme les autres."""
    listes = [v.faits for v in courantes.values() if v is not None and fs.avec_source(v.faits)]
    if not listes:
        return None
    val = _valides_de(db, dossier.owner_id, project.id, listes)
    return (lambda v: fs.ajuster(v.faits or [], val)) if val else None


def sources_faits_out(db, owner_id: int) -> dict:
    """Ce que l'écran dit des sources (vague 3) : libellés activés ou non, la bulle (i), et les
    preuves acceptées qu'Adjugo n'utilise pas (expirée, document retiré) avec la raison."""
    try:
        from app.services import preuves as pv
        ecartees = [{k: x.get(k) for k in ("ref", "id", "nature", "raison", "message")}
                    for x in pv.faits_ecartes(db, owner_id)][:50]
    except Exception:       # noqa: BLE001
        ecartees = []
    return {"libelles": fs.libelles_actifs(), "bulle": fs.BULLE, "preuves_ecartees": ecartees}


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
    if raison not in {x["code"] for x in derogations_possibles(gate)}:
        raise AtelierError(422, "raison_invalide", "Choisissez une des raisons proposées.")
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

def quota_out(dossier: DossierPresentation, n_parties: Optional[int] = None) -> dict:
    cap = regen_gratuites()
    used = int(dossier.regenerations or 0)
    left = max(0, cap - used)
    if not dossier.analyse_debitee:
        msg = ("La première rédaction avec Adjugo compte pour 1 analyse de votre forfait, une seule fois pour tout "
               f"le dossier : chaque partie du plan y est comprise une fois. Ensuite, refaire une partie est gratuit "
               f"{cap} fois.")
        prochaine = 1
    elif left:
        msg = f"Refaire une partie est gratuit : encore {left} fois sur {cap} pour ce dossier."
        prochaine = 0
    else:
        msg = (f"Les {cap} refontes gratuites de ce dossier sont utilisées : refaire une partie, ou rédiger une partie "
               "de plus que celles comprises dans l'analyse, compte maintenant pour 1 analyse.")
        prochaine = 1
    out = {"analyse_debitee": bool(dossier.analyse_debitee), "regenerations_gratuites": cap,
           "regenerations_utilisees": used, "regenerations_restantes": left,
           "regenerations_payantes": int(dossier.regenerations_payantes or 0), "message": msg,
           "prochaine_refonte_coute": prochaine, "premieres_incluses": int(dossier.premieres_incluses or 0)}
    if n_parties is not None:
        out["premieres_restantes"] = max(0, int(n_parties) - int(dossier.premieres_incluses or 0))
    return out


def _deja_redigee_par_ia(db, section: DossierSection) -> bool:
    return db.query(DossierSectionVersion.id).filter(
        DossierSectionVersion.section_id == section.id,
        DossierSectionVersion.origine.in_([IA, RACCOURCI])).first() is not None


def _msg_debit(cap: int, free_left: int, payantes: int) -> str:
    cout = ("cette rédaction compte pour 1 analyse de votre forfait." if payantes == 1 else
            f"ces rédactions comptent pour {payantes} analyses de votre forfait.")
    if free_left:
        tete = (f"Il reste {free_left} refonte{'s' if free_left > 1 else ''} gratuite{'s' if free_left > 1 else ''} "
                f"pour ce dossier ; au-delà, ")
    else:
        tete = f"Les {cap} refontes gratuites de ce dossier sont utilisées : "
    return (tete + cout + " (Une refonte : refaire une partie déjà rédigée, ou rédiger une partie de plus que celles "
            "comprises dans l'analyse du dossier.) Confirmez pour continuer.")


def _verifier_premiere_en_cours(db, d: DossierPresentation, job_id: int) -> None:
    """Tant que la tâche qui porte l'analyse du dossier tourne, aucune autre action de l'IA : si
    elle tombait en panne, son analyse serait rendue et l'autre rédaction serait gratuite."""
    jid = d.job_analyse_id
    if d.analyse_debitee and jid and jid != job_id:
        j = db.get(Job, jid)
        if j is not None and j.status in ("pending", "running"):
            raise AtelierError(409, "premiere_redaction_en_cours", MSG_PREMIERE_EN_COURS, job_id=jid)


def _debiter(db, user: User, dossier: DossierPresentation, sections: list, accepte_debit: bool,
             job_id: int, estimation_eur: Optional[float] = None) -> dict:
    """Décide et applique le débit d'une action de l'IA (décision 6a). Renvoie le relevé (pour
    rembourser).
      • la 1re action de l'IA sur le dossier : 1 analyse pour tout le dossier ;
      • la 1re rédaction d'une partie est comprise dans cette analyse, au plus une fois par partie
        du plan (au plus le nombre de parties actives) ; au-delà — partie ajoutée puis retirée,
        plan reconstruit — c'est une refonte : le plafond ne se contourne pas ;
      • refaire une partie (refonte) : gratuit jusqu'au plafond par dossier, puis 1 analyse chacune
        après accord exprès.
    Le dossier est relu verrouillé et réservé par une mise à jour CONDITIONNELLE (rien n'a changé
    depuis la lecture) AVANT de prendre les analyses : deux requêtes simultanées ne débitent jamais
    deux fois la première analyse. Si une analyse est refusée (quota atteint), tout est rendu."""
    from sqlalchemy import func, update
    from app.core.quota import consume_analysis, refund_analysis
    D = DossierPresentation
    for _essai in range(5):
        d = (db.query(D).filter(D.id == dossier.id).populate_existing().with_for_update().first())
        if d is None:
            raise AtelierError(404, "dossier_introuvable", "Le dossier de présentation de ce marché n'existe plus.")
        _verifier_premiere_en_cours(db, d, job_id)
        cap = regen_gratuites()
        premiere = not d.analyse_debitee
        n_act = len(sections_actives(db, d))
        incl0, regen0, pay0 = int(d.premieres_incluses or 0), int(d.regenerations or 0), int(d.regenerations_payantes or 0)
        place = max(0, n_act - incl0)
        incluses, regen = [], []
        for s in sections:
            if not _deja_redigee_par_ia(db, s) and place > 0:
                incluses.append(s)
                place -= 1
            else:
                regen.append(s)
        free_left = max(0, cap - regen0)
        payantes = max(0, len(regen) - free_left)
        if payantes and not accepte_debit:
            raise AtelierError(409, "debit_a_confirmer", _msg_debit(cap, free_left, payantes), cout=payantes)
        gratuites = len(regen) - payantes
        vals = {"premieres_incluses": incl0 + len(incluses), "regenerations": regen0 + gratuites,
                "regenerations_payantes": pay0 + payantes}
        if premiere:
            vals.update(analyse_debitee=True, job_analyse_id=job_id)
        res = db.execute(update(D).where(
            D.id == d.id, func.coalesce(D.analyse_debitee, False) == bool(d.analyse_debitee),
            func.coalesce(D.premieres_incluses, 0) == incl0, func.coalesce(D.regenerations, 0) == regen0,
            func.coalesce(D.regenerations_payantes, 0) == pay0).values(**vals)
            .execution_options(synchronize_session=False))
        if res.rowcount == 1:
            db.commit()
            break
        db.rollback()                       # une autre requête est passée entre-temps : on relit
    else:
        raise AtelierError(409, "reessayer", "Le dossier a été modifié au même moment : réessayez.")
    dues = (1 if premiere else 0) + payantes
    prises = 0
    try:
        for _ in range(dues):
            consume_analysis(user, db, "atelier", estimation_eur)
            prises += 1
    except Exception:
        db.rollback()
        for _ in range(prises):
            refund_analysis(user, db)
        undo = {"premieres_incluses": D.premieres_incluses - len(incluses),
                "regenerations": D.regenerations - gratuites,
                "regenerations_payantes": D.regenerations_payantes - payantes}
        if premiere:
            undo.update(analyse_debitee=False, job_analyse_id=None)
        db.execute(update(D).where(D.id == d.id).values(**undo).execution_options(synchronize_session=False))
        db.commit()
        raise
    releve = {"analyse": premiere, "sections": {}}
    for s in incluses:
        releve["sections"][str(s.id)] = "incluse"
    for i, s in enumerate(regen):
        releve["sections"][str(s.id)] = "gratuite" if i < gratuites else "payante"
    return releve


def _autre_texte_de_l_ia(db, dossier_id: int, job_id: int) -> bool:
    return db.query(DossierSectionVersion.id).filter(
        DossierSectionVersion.dossier_id == dossier_id, DossierSectionVersion.ia.is_(True),
        DossierSectionVersion.job_id.isnot(None), DossierSectionVersion.job_id != job_id).first() is not None


def rembourser(db, job: Job, section_ids_en_echec=None) -> None:
    """Rend ce qu'une action de l'IA a débité, quand elle n'a rien produit : tout (job en échec)
    ou les seules parties en échec (échec partiel). Idempotent (le relevé est marqué rendu).
    L'analyse du dossier n'est jamais rendue si une autre action a déjà produit un texte de l'IA
    sur ce dossier (l'IA a servi : elle reste due)."""
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
        if kind == "incluse" and dossier is not None:
            dossier.premieres_incluses = max(0, int(dossier.premieres_incluses or 0) - 1)
        elif kind == "gratuite" and dossier is not None:
            dossier.regenerations = max(0, int(dossier.regenerations or 0) - 1)
        elif kind == "payante":
            if dossier is not None:
                dossier.regenerations_payantes = max(0, int(dossier.regenerations_payantes or 0) - 1)
            if user is not None:
                refund_analysis(user, db)
        rendu[sid] = kind
    if tout and releve.get("analyse") and not releve.get("analyse_rendue"):
        if dossier is not None and _autre_texte_de_l_ia(db, dossier.id, job.id):
            releve["analyse_conservee"] = True
        else:
            if dossier is not None:
                dossier.analyse_debitee = False
                if dossier.job_analyse_id == job.id:
                    dossier.job_analyse_id = None
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
               chunks: list, dossier_acheteur: str, cible: Optional[int], passages_acheteur: str = "",
               fiches: Optional[list] = None) -> dict:
    """Ce que le moteur remet à l'IA pour une partie. `fiches` : les faits autorisés NUMÉROTÉS et
    typés (vague 3) — l'IA cite leur renvoi [F3], [P1]… ; l'ancien bloc `faits` reste pour mémoire."""
    out = {"titre": section.intitule, "numero": numero, "question": section.question or "",
           "critere": section.critere or "", "poids": section.poids or "",
           "poids_source": (section.poids_source or "") if section.poids else "",
           "partie_de_critere": bool(section.partie_de_critere), "source_plan": section.source_plan,
           "cible_mots": cible, "faits": ctx.faits_autorises(), "chunks": chunks,
           "dossier_acheteur": dossier_acheteur, "passages_acheteur": passages_acheteur, "autres_parties": autres}
    if fiches is not None:
        out["fiches"] = fs.lignes_ia(fiches, _requete(section))
    return out


def _dossier_pour_ia(project: Project, lu: dict) -> tuple:
    """Ce que le moteur remet à l'IA, commun à toutes les parties : (texte, lecture rangée ou None,
    numéros des pièces remises en entier). Lecture intégrale : l'avertissement de ce qui est remis
    (règlements et cadres en entier, le reste par passages, pièces non lues ; jamais de remarque sur
    la lecture dans le texte rendu à l'acheteur), puis TOUS les règlements et TOUS les
    cadres de réponse en entier. Ancienne lecture : son texte borné. ("", None, set()) si la lecture
    rangée est devenue illisible (l'appelant relit alors l'ancienne)."""
    if not lu.get("integral"):
        return lu.get("texte") or "", None, set()
    from app.services import dce_texte
    try:
        payload = dce_texte.charger(project)
    except Exception:       # noqa: BLE001
        payload = None
    if not payload or not any((p.get("texte") or "").strip() for p in payload.get("pieces") or []):
        return "", None, set()
    rem = dce_texte.pieces_remises(payload, DOSSIER_COMMUN_MAX)
    # Note PROPRE à l'atelier (son texte va à l'acheteur) : ce qui est remis en entier, par passages,
    # non lu — jamais « dossier lu en entier », jamais de remarque sur la lecture dans le texte.
    note = dce_texte.note_remise(payload, rem, pour_acheteur=True)
    return (note + "\n\n" + rem["texte"]).strip(), payload, set(rem["entiers"])


def _passages_pour_ia(project: Project, payload: Optional[dict], section: DossierSection, entiers: set) -> str:
    """Passages des AUTRES pièces les plus proches de la partie (recherche sans IA dans toutes les
    pièces lues, pièces remises en entier écartées), avec leur pièce et leur page. Sans repère entre
    crochets : rien qui puisse finir dans le texte rendu à l'acheteur."""
    if not payload:
        return ""
    from app.services import dce_texte
    try:
        hits = dce_texte.passages(project, _requete(section), k=PASSAGES_PAR_PARTIE, payload=payload,
                                  exclude_pieces=entiers)
    except Exception as e:      # noqa: BLE001 — la partie se rédige alors avec le règlement et le cadre
        logger.warning("atelier : recherche dans le dossier du marché impossible (projet %s) : %s",
                       project.id, type(e).__name__)
        return ""
    out = []
    for h in hits:
        pg = f", page {h['page']}" if h.get("page") else ""
        out.append(f"Pièce « {h.get('piece') or ''} » ({h.get('libelle') or ''}{pg}) :\n<<<\n"
                   f"{(h.get('texte') or '').strip()}\n>>>")
    return "\n\n".join(out)


def lancer(db, user: User, project: Project, dossier: DossierPresentation, sections: list, action: str,
           lecteur: Lecteur, member_ids: list, cible: Optional[int] = None, accepte_debit: bool = False) -> Job:
    """Lance « Rédiger avec Adjugo » (une ou plusieurs parties) ou « Raccourcir » (une partie) en
    tâche de fond. Débite selon la décision 6a, rembourse si l'IA tombe en panne."""
    from app.services.jobs import run_in_thread
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
    # Essai gratuit : la limite d'usage est vérifiée AVANT de lancer, que la rédaction soit débitée ou
    # comprise (refaire une partie gratuitement coûte aussi un appel à l'IA). Sans effet pour un
    # forfait payant. Une rédaction lancée va toujours au bout.
    from app.services.budget_ia import estimer_atelier, verifier
    estimation = estimer_atelier(len(sections), raccourcir=(action == JOB_RACCOURCIR))
    verifier(user, db, "atelier", estimation)
    titre = sections[0].intitule if len(sections) == 1 else f"{len(sections)} parties"
    label = ("Dossier de présentation : rédaction de « " if action == JOB_REDIGER
             else "Dossier de présentation : raccourcir « ") + titre[:120] + " »"
    # La tâche et la réservation des parties dans LA MÊME transaction que le verrou des parties :
    # une seconde requête sur la même partie voit la tâche (« rédaction en cours »).
    job = Job(user_id=user.id, kind=action, status="pending", label=label[:255])
    db.add(job)
    db.flush()
    for s in sections:
        s.job_id = job.id
    jid = job.id
    db.commit()
    ids = [s.id for s in sections]
    try:
        releve = _debiter(db, user, dossier, sections, accepte_debit, jid, estimation)
    except Exception:
        db.rollback()
        _annuler_tache(db, jid, ids)
        raise
    job = db.get(Job, jid)
    releve.update(dossier_id=dossier.id, rendu=False)
    job.result = {"_debit": releve}
    db.commit()
    jid, pid, owner, mids = job.id, project.id, dossier.owner_id, list(member_ids)
    uid = user.id

    def _work(jdb):
        return _executer(jdb, jid, pid, owner, mids, uid, ids, action, cibles)

    def _on_error(jdb, j):
        rembourser(jdb, j)
        _liberer(jdb, ids, j.id)

    run_in_thread(jid, _work, on_error=_on_error, tenant_id=owner, error_message=MSG_IA_PANNE)
    return db.get(Job, jid)


def _annuler_tache(db, job_id: int, section_ids: list) -> None:
    """Débit refusé (accord à donner, quota atteint, première rédaction en cours) : la tâche n'a
    jamais démarré, elle disparaît et ses parties sont libérées."""
    try:
        _liberer(db, section_ids, job_id)
        j = db.get(Job, job_id)
        if j is not None:
            db.delete(j)
        db.commit()
    except Exception:       # noqa: BLE001 — au pire, la reprise au démarrage la clôt
        db.rollback()


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
    dossier_acheteur, payload, entiers = "", None, set()
    if action == JOB_REDIGER:
        # Le dossier du marché tel qu'il est MAINTENANT : relu si le fichier a changé ou si une
        # nouvelle lecture intégrale a été rangée (ré-analyse, lecture en tâche de fond terminée).
        lu = dossier.dce_lu if isinstance(dossier.dce_lu, dict) else {}
        if (lu.get("cle") != cle_dossier_acheteur(db, project, member_ids)
                or (lu.get("lecture_cle") or "") != cle_lecture(project)
                or not (lu.get("texte") or lu.get("integral"))):
            lu = lire_dossier_acheteur(db, project, member_ids)
            dossier.dce_lu = dce_lu_en_base(lu)
            flag_modified(dossier, "dce_lu")
            db.commit()
        dossier_acheteur, payload, entiers = _dossier_pour_ia(project, lu)
        if lu.get("integral") and payload is None:
            # Lecture rangée devenue illisible : l'ancienne lecture, bornée, plutôt que rien.
            lu = lire_dossier_acheteur(db, project, member_ids, integrale=False)
            dossier_acheteur = lu.get("texte") or ""
    # Vague 3 (A) : les faits autorisés NUMÉROTÉS et typés ; les noms de l'équipe sont masqués par
    # CE pseudonymiseur (le même pour les lignes remises à l'IA et pour la portée de l'appel).
    pz = ctx.pseudonymiseur()
    fiches_ent = ctx.fiches(db, pseudonymiseur=pz)
    acheteur = _acheteur(project, lu, payload) if action == JOB_REDIGER else None
    taches = []
    for s in sections:
        base = version_courante(db, s)
        if action == JOB_RACCOURCIR:
            taches.append({"sid": s.id, "base": base, "texte": base.texte if base else "", "chunks": [],
                           "cible": cibles.get(s.id), "titre": s.intitule,
                           "fiches": ctx.fiches_de_version(db, base)})
            continue
        chunks = rag.retrieve_multi(db, member_ids, _requete(s), k=6, relevance=True)
        autres = [ax.titre_section({"numero": rangs.get(x.id, ""), "intitule": x.intitule}) for x in act if x.id != s.id]
        cible = cible_mots(s, None)
        fiches = fiches_ent + fs.fiches_extraits(chunks)
        taches.append({"sid": s.id, "base": base, "chunks": chunks, "fiches": fiches,
                       "partie": _partie_ia(dossier, s, rangs.get(s.id, ""), autres, ctx, chunks, dossier_acheteur,
                                            cible, passages_acheteur=_passages_pour_ia(project, payload, s, entiers),
                                            fiches=fiches_ent)})

    def _un(t):
        if action == JOB_RACCOURCIR:
            return moteur.raccourcir_partie(t["texte"], t["cible"], titre=t["titre"], billing_id=owner_id)
        return moteur.rediger_partie(t["partie"], billing_id=owner_id)

    label = "atelier : rédiger" if action == JOB_REDIGER else "atelier : raccourcir"
    with pii_scope(pz), cost_meter(label, owner_id) as cm:
        if len(taches) == 1:
            resultats = [_un(taches[0])]
        else:
            # Le dossier de l'acheteur commun (jusqu'à DOSSIER_COMMUN_MAX caractères) est mis en cache
            # de prompt : le cache n'existe qu'une fois la première réponse commencée. Lancées ensemble,
            # les 3 premières parties l'écriraient chacune (2 × le prix d'entrée pour un cache d'une
            # heure, tâche « redaction » de app.services.llm) ; la première partie part donc SEULE, les
            # suivantes (en parallèle) le relisent à 0,05 × (Sonnet 5.5).
            premiers = []
            if action == JOB_REDIGER and dossier_acheteur.strip():
                premiers = [_un(taches[0])]
            reste = taches[len(premiers):]
            with ThreadPoolExecutor(max_workers=min(3, len(reste))) as ex:
                resultats = premiers + list(map_in_context(ex, _un, reste))
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
            # « Raccourcir » n'ajoute rien et ne blanchit rien : un fait garde ce qu'il était.
            faits = fs.controler(texte, t["fiches"], acheteur=None, noms_entreprise=ctx.noms_entreprise,
                                 section_entreprise=section_sur_l_entreprise(s), mode="raccourci",
                                 anciens=(base.faits if base else []), base_texte=t["texte"])
            sources = (base.sources or []) if base else []
            refs = {f"S{n}" for n in rag.cited_refs(texte)} | {x for x in fs.refs_de(texte) if x.startswith("S")}
            sources = [x for x in sources if x.get("ref") in refs]
            v = ajouter_version(db, s, texte=texte, origine=RACCOURCI, ia=True, sources=sources, faits=faits,
                                coupe=bool(r.get("coupe")), base_version_id=base.id if base else None,
                                auteur_user_id=user_id, job_id=job_id)
        else:
            # Le CV d'une personne est inséré tel quel, sans IA (décision 8a), puis tout est contrôlé.
            texte = fs.inserer_cv(texte, t["fiches"])
            faits = fs.controler(texte, t["fiches"], acheteur=acheteur, noms_entreprise=ctx.noms_entreprise,
                                 section_entreprise=section_sur_l_entreprise(s), mode="ia",
                                 anciens=(base.faits if base else []))
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
    n = len(echecs)
    return {"sections": sortie, "echecs": n, "_debit": debit,
            "message": ("" if not n else
                        "1 partie n'a pas pu être rédigée (service d'IA indisponible) : rien n'a été débité pour "
                        "elle, réessayez." if n == 1 else
                        f"{n} parties n'ont pas pu être rédigées (service d'IA indisponible) : rien n'a été "
                        "débité pour elles, réessayez.")}


def _cumuler_cout(dossier: Optional[DossierPresentation], summary: dict) -> None:
    """Coût IA réel cumulé sur le dossier (décision 6a : ramener le plafond à 5 si un dossier complet
    coûte plus qu'une analyse hors forfait). Interne, jamais montré au client."""
    if dossier is None or not isinstance(summary, dict):
        return
    cur = dossier.cout_ia if isinstance(dossier.cout_ia, dict) else {}
    usd = summary.get("cout_estime_usd")

    def _somme(k):
        return int(cur.get(k) or 0) + int(summary.get(k) or 0)
    # tokens_entree = entrée HORS cache ; le dossier de l'acheteur commun passe par le cache de prompt
    # (Sonnet 5.5 : écrit à 2 × le prix d'entrée pour 1 h, relu à 0,05 ×) : compté à part, pour lire
    # le volume réel envoyé.
    out = {"appels": _somme("appels"), "tokens_entree": _somme("tokens_entree"),
           "tokens_cache_ecrits": _somme("tokens_cache_ecrits"), "tokens_cache_lus": _somme("tokens_cache_lus"),
           "tokens_sortie": _somme("tokens_sortie"),
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
    cour = versions_communes(db, sections, lecteur)          # jamais le brouillon d'un autre auteur
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    lims = evaluer_limites(dossier, sections, rangs, cpt)
    gate = blocage(dossier, sections, cour, rangs, lims, attente=en_attente_d_un_partenaire(sections, lecteur, cour),
                   faits_de=faits_lus(db, dossier, project, cour))
    if not gate["peut_exporter"]:
        raise AtelierError(409, "export_bloque",
                           "L'export est bloqué : " + " ".join(r["message"] for r in gate["raisons"]),
                           raisons=gate["raisons"], etat_hash=gate["etat_hash"],
                           derogations_possibles=derogations_possibles(gate))
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


def _validees_de_preference(db, sections: list, communes: dict, lecteur: Lecteur) -> tuple:
    """Texte retenu pour le dossier commun : la version VALIDÉE de chaque partie quand elle existe
    (le dirigeant l'a approuvée), sinon le texte commun (versions_communes : le texte courant de SES
    parties, rien pour la partie d'un partenaire qui n'a rien envoyé). Renvoie (versions retenues,
    parties modifiées depuis leur validation)."""
    ids = [s.validated_version_id for s in sections if s.validated_version_id]
    by_id = {v.id: v for v in db.query(DossierSectionVersion).filter(DossierSectionVersion.id.in_(ids)).all()} \
        if ids else {}
    out, modifiees = {}, []
    for s in sections:
        v = by_id.get(s.validated_version_id) if s.validated_version_id else None
        if v is not None and v.section_id == s.id:
            out[s.id] = v
            if peut_voir_prive(s, lecteur) and s.current_version_id and s.current_version_id != v.id:
                modifiees.append(s)
        elif s.id in communes:
            out[s.id] = communes[s.id]
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
        out["warnings"].append("BLOQUANT — Dossier de présentation non rédigé : préparez-le dans l'atelier (sur la "
                               "page du marché, carte « Dossier de présentation »), puis validez chaque partie.")
        return out
    lecteur = Lecteur.organisation(owner_id)
    sections = sections_actives(db, dossier)
    communes = versions_communes(db, sections, lecteur)
    cour, modifiees = _validees_de_preference(db, sections, communes, lecteur)
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    gate = blocage(dossier, sections, cour, rangs, evaluer_limites(dossier, sections, rangs, cpt),
                   attente=en_attente_d_un_partenaire(sections, lecteur, cour),
                   faits_de=faits_lus(db, dossier, project, cour))
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
    sans_validation = [s for s in sections if not s.validated_version_id and s.author_kind == AUTEUR_ORG]
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

def controle_out(faits, libelles: Optional[bool] = None) -> dict:
    """Le compteur « Faits avec une source : 7 sur 8 » d'une version (vague 3) — seulement quand
    les libellés positifs sont activés (ATELIER_LIBELLES_SOURCES=1, après la calibration) ; sinon
    {"libelles": false} et l'écran garde l'affichage d'A0 (« à relire » seulement)."""
    lib = fs.libelles_actifs() if libelles is None else libelles
    b = fs.bilan(faits)
    if not lib or b is None:
        return {"libelles": False}
    return dict(b, libelles=True)


def _version_out(v: DossierSectionVersion, prive: bool, texte: bool = True, valides: Optional[dict] = None) -> dict:
    """Une version. `faits` : les faits À RELIRE (ou relus par vous), forme d'A0 ; avec les libellés
    activés, `faits_sources` : les faits reliés à leur source (où Adjugo les a trouvés) et `controle` :
    le compteur. `valides` : sources encore utilisables (un fait dont la preuve a été retirée ou a
    expiré redevient à relire)."""
    faits = fs.ajuster(v.faits or [], valides) if valides else (v.faits or [])
    out = {"id": v.id, "numero": v.numero, "origine": v.origine, "origine_libelle": ORIGINES.get(v.origine, ""),
           "ia": bool(v.ia), "empreinte": v.empreinte, "coupe": bool(v.coupe), "cree_le": _iso(v.created_at),
           "auteur_user_id": v.auteur_user_id, "restaure_de": v.restaure_de,
           "a_completer": len(me.placeholders(v.texte or "")), "faits_a_relire": far.non_traites(faits)}
    if texte:
        out["texte"] = v.texte or ""
    if prive:
        lib = fs.libelles_actifs()
        out["sources"] = v.sources or []
        out["faits"] = fs.a_relire(faits)
        out["controle"] = controle_out(faits, lib)
        if lib:
            out["faits_sources"] = fs.avec_source(faits)
    return out


def section_out(db, dossier: DossierPresentation, s: DossierSection, rang_affiche: str, lecteur: Lecteur,
                courante: Optional[DossierSectionVersion], cpt_section: Optional[dict],
                valides: Optional[dict] = None) -> dict:
    prive = peut_voir_prive(s, lecteur)
    if prive and valides is None and courante is not None and fs.avec_source(courante.faits):
        valides = _valides_de(db, s.owner_id, s.project_id, [courante.faits])
    out = {"id": s.id, "ordre": s.ordre, "numero": s.numero, "numero_affiche": rang_affiche,
           "intitule": s.intitule, "titre": ax.titre_section({"numero": rang_affiche, "intitule": s.intitule}),
           "niveau": s.niveau, "parents": s.parents or [], "question": s.question or "",
           "source_plan": s.source_plan, "critere": s.critere or "", "critere_id": s.critere_id or "",
           "poids": s.poids or "", "poids_source": (s.poids_source or "") if s.poids else "",
           "partie_de_critere": bool(s.partie_de_critere), "lot": s.lot or "",
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
        out["version_courante"] = _version_out(courante, True, valides=valides) if courante is not None else None
        out["nb_versions"] = db.query(DossierSectionVersion.id).filter(
            DossierSectionVersion.section_id == s.id).count()
    else:
        # Auteur partenaire (vague 4) : seul le texte VALIDÉ (envoyé) est commun, avec ses compteurs.
        vv = db.get(DossierSectionVersion, s.validated_version_id) if s.validated_version_id else None
        out["version_courante"] = _version_out(vv, False) if vv is not None else None
    v = out["version_courante"]
    out["a_completer"] = v["a_completer"] if v else 0
    out["faits_a_relire"] = v["faits_a_relire"] if v else 0
    out["controle"] = (v.get("controle") if v and prive else None) or {"libelles": False}
    out["compteur"] = ({k: cpt_section.get(k) for k in ("mots", "caracteres", "pages_estimees", "lignes_estimees")}
                       if cpt_section else None)
    return out


def savoir_faire(db, member_ids: list) -> dict:
    """« Mon savoir-faire » de l'organisation : vide, Adjugo écrira surtout des « [À compléter] »."""
    try:
        from app.models import KnowledgeChunk
        vide = db.query(KnowledgeChunk.id).filter(KnowledgeChunk.user_id.in_(list(member_ids))).first() is None
    except Exception:       # noqa: BLE001
        vide = False
    return {"vide": vide, "message": ("Ajoutez d'anciens dossiers ou des fiches dans « Mon savoir-faire » : sans eux, "
                                      "Adjugo écrira surtout des « [À compléter] ».") if vide else ""}


_CHAMPS_PIECE = ("nom", "libelle", "type", "lu_en_entier", "statut", "raison", "pages", "pages_lues", "remise",
                 "remise_libelle")


def dossier_acheteur_out(lu: dict, cle_now: str, a_change: bool) -> dict:
    """« Pièces du dossier de l'acheteur lues par Adjugo » : la couverture HONNÊTE de ce que lit le
    moteur — chaque pièce lue en entier, en partie ou non lue (et pourquoi), ce qui en est remis à
    l'IA ; une ancienne lecture le dit et dit comment obtenir la lecture intégrale."""
    absent = cle_now == "aucun"
    cov = lu.get("couverture") if isinstance(lu.get("couverture"), dict) else None
    return {"source": (lu.get("source") or "aucun") if not absent else "aucun",
            "present": not absent, "nom_fichier": lu.get("nom_fichier") or "",
            "integral": bool(lu.get("integral")) and not absent,
            "couverture": ({"complet": bool(cov.get("complet")), "message": str(cov.get("message") or "")}
                           if cov and not absent else None),
            "message_lecture": "" if absent else str(lu.get("message_lecture") or ""),
            "pieces": [] if absent else [{k: p.get(k) for k in _CHAMPS_PIECE if k in p}
                                         for p in (lu.get("pieces") or []) if isinstance(p, dict)],
            "a_change": a_change, "message": MSG_DCE_CHANGE if a_change else "",
            "message_absent": MSG_DCE_ABSENT if absent else ""}


def etat(db, project: Project, dossier: DossierPresentation, lecteur: Lecteur, member_ids: list) -> dict:
    sections = sections_actives(db, dossier)
    cour = versions_communes(db, sections, lecteur)          # jamais le brouillon d'un autre auteur
    ctx = contexte_rendu(db, project, dossier, sections, cour)
    cpt = compteur(db, project, dossier, sections, cour, ctx=ctx)
    rangs = _rangs(dossier, sections)
    lims = evaluer_limites(dossier, sections, rangs, cpt)
    val = _valides_de(db, dossier.owner_id, project.id,
                      [v.faits for v in cour.values() if v is not None and fs.avec_source(v.faits)])
    gate = blocage(dossier, sections, cour, rangs, lims, attente=en_attente_d_un_partenaire(sections, lecteur, cour),
                   faits_de=(lambda v: fs.ajuster(v.faits or [], val)) if val else None)
    by_sec = {x.get("id"): x for x in (cpt.get("sections") or [])}
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    lu = dossier.dce_lu if isinstance(dossier.dce_lu, dict) else {}
    # Le dossier du marché lu POUR LE PLAN (pas la lecture que le moteur rafraîchit à chaque rédaction).
    cle_plan = meta.get("cle_dce") or lu.get("cle") or ""
    cle_now = cle_dossier_acheteur(db, project, member_ids)
    a_change = bool(cle_plan) and cle_plan != cle_now
    # Ce que le moteur lira à la prochaine rédaction (et non une lecture périmée) : relu (cache du
    # process) si le fichier a changé ou si une nouvelle lecture intégrale a été rangée depuis.
    lu_aff = lu
    if (lu.get("cle") != cle_now or (lu.get("lecture_cle") or "") != cle_lecture(project)
            or (lu.get("message_lecture") == MSG_LECTURE_EN_COURS) != _lecture_en_cours(db, project)):
        lu_aff = lire_dossier_acheteur(db, project, member_ids)
    retirees_rows = sections_retirees(db, dossier)
    retirees = [{"id": s.id, "intitule": s.intitule, "retiree_le": _iso(s.retiree_at),
                 "nb_versions": db.query(DossierSectionVersion.id).filter(
                     DossierSectionVersion.section_id == s.id).count()}
                for s in retirees_rows if peut_voir_prive(s, lecteur)]
    return {
        "projet": {"id": project.id, "nom": project.name},
        "dossier": {"id": dossier.id, "plan_source": dossier.plan_source, "version": dossier.version,
                    "cree_le": _iso(dossier.created_at), "maj_le": _iso(dossier.updated_at),
                    "plan": dict({k: meta.get(k) for k in ("source", "message", "fichier_impose", "message_fichier",
                                                           "avertissement_fichier", "cadre_non_decoupe",
                                                           "criteres_hors_dossier", "limites", "base_demandee",
                                                           "construit_le")},
                                 bases=ap.bases_disponibles(_analysis(project), (lu_aff.get("cadre") or ""),
                                                            decoupable=lu_aff.get("cadre_decoupable")),
                                 criteres_en_attente=ap.criteres_a_verifier(_analysis(project)),
                                 message_en_attente=(ap.msg_a_verifier(ap.criteres_a_verifier(_analysis(project)))
                                                     if dossier.plan_source != ap.CADRE else "")),
                    "dernier_export": dossier.dernier_export or None},
        "sections": [section_out(db, dossier, s, rangs.get(s.id, ""), lecteur, cour.get(s.id), by_sec.get(s.id),
                                 valides=val)
                     for s in sections],
        "sections_retirees": retirees,
        "compteur": {"total": cpt.get("total"), "police": cpt.get("police"), "environ": True,
                     "message": cpt.get("message")},
        "limites": lims,
        "blocage": gate,
        "quota": quota_out(dossier, n_parties=len(sections)),
        "export": apercu_export(project, dossier, ctx),
        "dossier_acheteur": dossier_acheteur_out(lu_aff, cle_now, a_change),
        "grille": changements_grille(project, dossier, sections, retirees_rows),
        "savoir_faire": savoir_faire(db, member_ids),
        "statuts": STATUTS,
        "derogations_possibles": derogations_possibles(gate),
        "sources_faits": sources_faits_out(db, dossier.owner_id),
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
