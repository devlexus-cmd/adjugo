"""
Le DOSSIER DE GROUPEMENT cloisonné (rédaction, vague 4 — étude § 6.8 B) : chacun écrit sa part, chez lui.

Contrat : docs/REDACTION_V4_GROUPEMENT.md. Ce module est le SEUL point d'écriture de la répartition
(« Qui écrit quoi »), des brouillons des partenaires, des textes communs de leurs parties et de la
validation du dossier assemblé. Les routeurs (app/routers/atelier_groupement.py) ne font que
contrôler l'accès et traduire les erreurs (`atelier.AtelierError`).

Doctrine (étude § 7) appliquée ici :
  • la matière reste chez son propriétaire : le brouillon d'un partenaire, ses sources, ses extraits et
    ses faits avec leur source sont rangés à part (table dossier_parts_brouillons), lus seulement par
    SON accès (lien de l'invitation, ou compte qui a rattaché ce lien). Le chef de file reçoit le texte
    ENVOYÉ (une version commune de la partie, `partage`), ses faits à relire SANS leur source et des
    COMPTEURS de sources par type — jamais une source, jamais un extrait ;
  • un fait ne vient jamais de l'IA : l'aide de l'IA du partenaire ne reçoit que SES faits (sans compte :
    ce qu'il a déclaré dans sa contribution, « déclaré par vous » ; avec un compte Adjugo : ses preuves,
    son profil et son savoir-faire, interrogés avec SES droits) et le dossier de l'acheteur (« exigé
    par l'acheteur »), et le contrôle des faits (A) tourne chez lui, sur SES faits. Jamais la matière
    du chef de file ni celle d'un autre membre (aucune lecture croisée : rag.retrieve_multi n'est
    appelé qu'avec les comptes de l'organisation du partenaire) ;
  • c'est le partenaire qui lance son aide de l'IA : la tâche a un propriétaire distinct (portée
    « partenaire », invite_id, AUCUN compte propriétaire) et ne se lit qu'avec son accès ; un membre de
    l'organisation du chef de file reçoit 404 sur /api/jobs/{id} ;
  • facturation (décisions 4a et 6a) : UNE fonction, `facturer_aide_partenaire`, débite le quota du chef de
    file (un dossier complet = 1 analyse, refaire une partie gratuit jusqu'à ATELIER_REGEN_GRATUITES, plus
    un plafond par partie), dans une portée de facturation technique propre à l'invitation
    (`tenant_scope("inv:<id>")`), avec le garde-fou de l'essai du chef de file et le remboursement si
    l'IA tombe ; tout refus lié au forfait du chef de file rend au partenaire un message NEUTRE ;
  • personne ne change la part d'un autre en silence : le chef de file qui modifie une part (ou l'écrit à
    la place d'un partenaire absent) la fait passer « à revalider par » son auteur, avec l'avant et
    l'après ; toute modification d'un texte commun après la validation du dossier assemblé la fait
    repasser « à revalider » (même mécanisme que la convention périmée) ; tout est inscrit au journal
    chaîné ;
  • aucun temps réel : un seul process, aucune connexion permanente, pas de suggestions.
"""
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified

from app.models import (Company, DossierPartBrouillon, DossierPresentation, DossierRepartition, DossierSection,
                        DossierSectionVersion, DossierValidation, Job, Project, ProjectContribution, ProjectInvite,
                        User, utcnow)
from app.services import atelier as at
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from app.services import memoire_export as me

logger = logging.getLogger("adjugo")

AtelierError = at.AtelierError

# ── Vocabulaire ───────────────────────────────────────────────────────────────────────

CHEF, PARTENAIRE = "chef_de_file", "partenaire"
REDACTEURS = (CHEF, PARTENAIRE)
A_REDIGER, EN_COURS, ENVOYEE, A_REVALIDER, VALIDEE = "a_rediger", "en_cours", "envoyee", "a_revalider", "validee"
STATUTS = {A_REDIGER: "À rédiger", EN_COURS: "En cours", ENVOYEE: "Envoyée", A_REVALIDER: "À revalider",
           VALIDEE: "Validée"}
# Partie tirée du groupement (assemblage, app/services/atelier_assemblage.py) : personne ne la rédige, on la
# valide (« Organisation du groupement » : le chef de file ; « Qui fait quoi » : chaque membre).
A_VALIDER = "a_valider"
STATUTS[A_VALIDER] = "À valider"
ECRIT_PAR_PARTENAIRE, ECRIT_PAR_CHEF = "partenaire", "chef_de_file"
PORTEE_PARTENAIRE = "partenaire"
JOB_REDIGER = "partenaire_rediger"
JOB_RACCOURCIR = "partenaire_raccourcir"
JOB_KINDS = (JOB_REDIGER, JOB_RACCOURCIR)
ORIGINES = {"ia": "Rédigé avec Adjugo", "utilisateur": "Écrit ou modifié par vous", "raccourci": "Raccourci avec Adjugo",
            "acceptee": "Texte du chef de file accepté par vous", "retablie": "Votre version rétablie"}
# Compteurs de sources par type du texte d'une partie (ce que le chef de file reçoit, sans les sources).
TYPES_COMPTEURS = ("documents", "declare", "public", "estimation", "calcul", "acheteur")
_TYPE_COMPTEUR = {fs.T_DOCUMENTS: "documents", fs.T_JUSTIFICATIF: "documents", fs.T_DECLARE: "declare",
                  fs.T_VOUS: "declare", fs.T_PUBLIC: "public", fs.T_ESTIMATION: "estimation",
                  fs.T_CALCUL: "calcul", fs.T_ACHETEUR: "acheteur", fs.T_PARTENAIRE: "declare"}

# Phrases à l'écran (françaises, sans jargon ; les bulles (i) sont dans le contrat).
AVERTISSEMENT_ENVOI = "Ce texte sera lu par le chef de file et par les autres membres du groupement."
MSG_LECTURE = ("Le dossier assemblé est en lecture seule : vous y lisez le texte que chaque membre a envoyé. Les "
               "documents, sources et brouillons de chacun restent privés.")
MSG_AIDE_INDISPONIBLE = ("L'aide d'Adjugo n'est pas disponible pour cette partie en ce moment. Vous pouvez "
                         "l'écrire vous-même : votre texte sera contrôlé de la même façon.")
MSG_AIDE_OCCUPEE = ("Adjugo prépare une autre partie de ce dossier : réessayez dans quelques minutes, ou écrivez "
                    "votre partie vous-même.")
MSG_PLAFOND = ("Vous avez utilisé l'aide d'Adjugo {n} fois pour cette partie : écrivez la suite vous-même, votre "
               "texte sera contrôlé de la même façon.")
MSG_IA_PANNE = ("La rédaction n'a pas abouti : le service d'IA est indisponible pour le moment. Réessayez dans "
                "quelques minutes.")
MSG_PAS_DE_DOSSIER = "Le chef de file n'a pas encore préparé le dossier de présentation commun."
MSG_MODE_LIEN = ("Sans compte Adjugo, l'aide d'Adjugo s'appuie sur ce que vous avez déclaré dans votre part et sur le "
                 "dossier de l'acheteur.")
MSG_MODE_COMPTE = ("Avec votre compte Adjugo, l'aide d'Adjugo s'appuie aussi sur vos preuves, votre profil et votre "
                   "savoir-faire, consultés avec vos seuls droits.")
TEXTE_MAX = at.TEXTE_MAX
BASE_DEFAUT = object()           # « paramètre non fourni » (PUT partiel)
DEMANDE_INTERVALLE = timedelta(minutes=15)
PURGE_JOURS = 30                 # brouillons d'une invitation expirée depuis plus longtemps : effacés


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return v if v > 0 else default
    except ValueError:
        return default


def plafond_partie() -> int:
    """Aides de l'IA permises au partenaire PAR PARTIE (décisions 4a et 6a ; ATELIER_PARTENAIRE_AIDES_PAR_PARTIE,
    défaut 3 : la première rédaction et deux refontes). Elles comptent aussi dans le plafond du dossier."""
    return _env_int("ATELIER_PARTENAIRE_AIDES_PAR_PARTIE", 3)


def tenant_partenaire(invite_id: int) -> str:
    """Portée de facturation TECHNIQUE propre à l'invitation (plafonds et disjoncteurs de l'IA séparés de
    ceux du chef de file) ; le coût est rangé au compte de facturation du chef de file (budget_ia)."""
    return f"inv:{int(invite_id)}"


def _iso(dt) -> Optional[str]:
    return at._iso(dt)


def _jour(d) -> Optional[str]:
    return d.isoformat() if isinstance(d, date) else None


def _sha(payload) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _journal(db, *, action: str, project_id: int, owner_id: int, actor: str, actor_kind: str, detail: str = "",
             invite_id=None, target_type: str = "dossier_section", target_id=None, ip: str = "", meta=None) -> None:
    from app.services import audit
    audit.record(db, action=action, owner_id=owner_id, project_id=project_id, actor=(actor or "")[:160],
                 actor_kind=actor_kind, target_type=target_type, target_id=target_id, detail=(detail or "")[:255],
                 ip=ip or "", meta=meta, invite_id=invite_id)


def _titre(dossier: DossierPresentation, section: DossierSection, rangs: Optional[dict] = None) -> str:
    return at._flat(section.intitule)[:160]


# ── Membres du groupement qui peuvent rédiger ─────────────────────────────────────────

def _contribution(db, invite_id: int) -> Optional[ProjectContribution]:
    return db.query(ProjectContribution).filter(ProjectContribution.invite_id == invite_id).first()


def nom_partenaire(inv: Optional[ProjectInvite], c: Optional[ProjectContribution] = None) -> str:
    return at._flat((c.company_name if c is not None else "") or (inv.company_name if inv is not None else "")
                    or "Un partenaire")[:160]


def peut_rediger(db, inv: ProjectInvite) -> tuple:
    """(oui/non, raison) : un partenaire rédige une partie s'il est MEMBRE du groupement (invitation active,
    non expirée, co-traitant — un sous-traitant n'est pas membre —, co-construction ouverte) et, invitation
    du réseau, s'il l'a acceptée."""
    from app.routers.invites import _is_expired, _network_pending
    # Raisons écrites pour se lire seules (« Le Gall Électricité : son lien a expiré ») ou après « Ce partenaire
    # ne peut pas rédiger : ».
    if inv is None or inv.revoked or inv.declined_at is not None:
        return False, "il n'est plus membre du groupement"
    if _is_expired(inv.expires_at):
        return False, "son lien a expiré"
    if (inv.role or "cotraitant") != "cotraitant":
        return False, "un sous-traitant n'est pas membre du groupement"
    if not getattr(inv, "can_contribute", True):
        return False, "la co-construction n'est pas ouverte sur son lien"
    if _network_pending(inv, db):
        return False, "il n'a pas encore accepté l'invitation"
    return True, ""


def membres(db, project: Project) -> list:
    """[{invite_id, nom, lot, role, peut_rediger, raison, par_email}] des invitations actives du marché, dans
    l'ordre d'invitation. Le lot d'une invitation du réseau sans réponse n'est pas lu (sa part est invisible du
    chef de file). `par_email` : « Demander les parts » peut lui écrire (une adresse sur son lien) — un
    booléen seulement, jamais l'adresse (celle d'une invitation du réseau reste masquée)."""
    from app.routers.invites import _is_email
    from app.services.groupement_members import active_invites, visible_contributions
    invites = active_invites(db, project.id)
    contribs = visible_contributions(db, project.id, invites)
    out = []
    for inv in invites:
        c = contribs.get(inv.id)
        ok, raison = peut_rediger(db, inv)
        out.append({"invite_id": inv.id, "nom": nom_partenaire(inv, c), "lot": at._flat(c.lot if c else "")[:255],
                    "role": inv.role or "cotraitant", "peut_rediger": ok, "raison": raison,
                    "par_email": bool(_is_email(inv.recipient or ""))})
    return out


MSG_SANS_GROUPEMENT = ("Ce marché n'a aucun partenaire du groupement : invitez d'abord un partenaire depuis la page "
                       "du marché. Sans groupement, l'atelier reste celui de votre seule entreprise.")


def indicateur(db, project: Project, dossier: Optional[DossierPresentation]) -> dict:
    """Pour l'atelier du chef de file (`atelier.etat`) : le marché est-il en groupement, et « Qui écrit quoi »
    est-il préparé ? Sans IA, sans écriture, deux requêtes. `onglet` : l'atelier montre l'onglet « Qui écrit
    quoi » (au moins un partenaire co-traitant actif, ou une répartition déjà préparée — le chef de file y
    reprend alors les parties d'un partenaire parti). Un marché sans groupement : tout à faux, l'atelier
    reste exactement celui d'une seule entreprise."""
    from app.services.groupement_members import active_invite_filter
    from sqlalchemy import or_
    n = (db.query(ProjectInvite.id).filter(ProjectInvite.project_id == project.id, active_invite_filter(),
                                            or_(ProjectInvite.role == "cotraitant", ProjectInvite.role.is_(None),
                                                ProjectInvite.role == "")).count())
    actif = repartition_active(db, dossier)
    return {"onglet": bool(n or actif), "actif": bool(actif), "membres": int(n)}


# ── Pré-remplissage SANS IA du rédacteur : lot du membre ↔ critère de la partie ─────────

_GENERIQUES = {
    "travaux", "travail", "marche", "marches", "chantier", "chantiers", "entreprise", "entreprises", "offre", "offres",
    "prestation", "prestations", "oeuvre", "ouvrage", "ouvrages", "general", "generale", "generales", "generaux",
    "technique", "techniques", "moyens", "humains", "materiel", "materiels", "methode", "methodes",
    "methodologie", "organisation", "presentation", "partie", "parties", "dossier", "candidat", "memoire",
    "valeur", "critere", "criteres", "notation", "delai", "delais", "qualite", "planning", "phase", "phases",
    "ensemble", "objet", "realisation", "execution", "intervention", "interventions", "demarche", "gestion",
    "presentez", "decrivez", "precisez", "indiquez", "detaillez", "candidats", "groupement", "membres", "membre",
    "mission", "missions", "projet", "projets", "pages", "maximum", "minimum", "cadre", "reponse", "dispositions",
    "mesures", "propose", "proposees", "proposes", "mises", "place", "suivi", "controle", "ainsi", "notamment",
}


def _mots(texte: str) -> set:
    return {w for w in re.findall(r"[a-z]{5,}", far.fold(texte or "")) if w not in _GENERIQUES}


def _proches(a: str, b: str) -> bool:
    """« couverture » ↔ « couvreur », « plomberie » ↔ « plombier » : même début (5 lettres, ou 4 pour
    deux mots longs). Sans IA, sans dictionnaire."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 5 or (n >= 4 and len(a) >= 8 and len(b) >= 8)


def _correspondances(lot: str, section: DossierSection) -> list:
    """Mots du lot retrouvés (même début) dans l'intitulé, le critère ou la question de la partie."""
    cible = _mots(" ".join([section.intitule or "", section.critere or "", (section.question or "")[:1500]]
                           + [str(p.get("intitule") or "") for p in (section.parents or []) if isinstance(p, dict)]))
    out = []
    for w in sorted(_mots(lot)):
        hit = next((c for c in sorted(cible) if _proches(w, c)), None)
        if hit:
            out.append(hit)
    return list(dict.fromkeys(out))


def proposition(section: DossierSection, candidats: list) -> dict:
    """Le rédacteur proposé pour une partie, avec sa raison (affichée telle quelle). `candidats` : les
    membres qui peuvent rédiger (`membres`, peut_rediger). Le chef de file par défaut ; un partenaire
    seulement si son lot, et lui seul, se retrouve dans la partie."""
    titre = far.fold(section.intitule or "")
    if "groupement" in titre:
        return {"redacteur": CHEF, "invite_id": None, "nom": "", "lot": "", "mots": [],
                "message": "Partie sur le groupement : le chef de file la rédige."}
    scores = []
    for m in candidats:
        if not m.get("peut_rediger") or not m.get("lot"):
            continue
        mots = _correspondances(m["lot"], section)
        if mots:
            scores.append((len(mots), m, mots))
    if not scores:
        return {"redacteur": CHEF, "invite_id": None, "nom": "", "lot": "", "mots": [],
                "message": "Proposé au chef de file : aucun lot de partenaire ne correspond à cette partie."}
    scores.sort(key=lambda x: -x[0])
    if len(scores) > 1 and scores[0][0] == scores[1][0]:
        return {"redacteur": CHEF, "invite_id": None, "nom": "", "lot": "", "mots": [],
                "message": "Proposé au chef de file : plusieurs lots correspondent à cette partie, choisissez qui la "
                           "rédige."}
    _n, m, mots = scores[0]
    cite = ", ".join(f"« {w} »" for w in mots[:3])
    return {"redacteur": PARTENAIRE, "invite_id": m["invite_id"], "nom": m["nom"], "lot": m["lot"], "mots": mots[:5],
            "message": f"Proposé d'après le lot de {m['nom']} (« {m['lot'][:80]} ») : {cite} dans la partie."}


# ── Lecture : répartition, statut, textes communs ────────────────────────────────────

LECTEUR_NEUTRE = at.Lecteur("membre", 0)       # ni l'organisation ni une invitation : le texte COMMUN seul


def repartitions(db, dossier: DossierPresentation) -> dict:
    """{section_id: DossierRepartition} du dossier."""
    return {r.section_id: r for r in db.query(DossierRepartition).filter(DossierRepartition.dossier_id == dossier.id)}


def repartition_active(db, dossier: Optional[DossierPresentation]) -> bool:
    if dossier is None:
        return False
    return db.query(DossierRepartition.id).filter(DossierRepartition.dossier_id == dossier.id).first() is not None


def textes_communs(db, sections: list) -> dict:
    """{section_id: version} du dossier ASSEMBLÉ, tel que le lit chaque membre : pour la partie d'un
    partenaire, son texte commun (envoyé, ou écrit par le chef de file), sinon son texte validé ; pour une
    partie du chef de file, son texte VALIDÉ seulement (ses brouillons restent chez lui)."""
    return at.versions_communes(db, sections, LECTEUR_NEUTRE)


def _commune(db, section: DossierSection) -> Optional[DossierSectionVersion]:
    """Version COURANTE de la partie si elle est commune (texte d'un partenaire ou écrit sur sa partie)."""
    if not section.current_version_id:
        return None
    v = db.get(DossierSectionVersion, section.current_version_id)
    return v if v is not None and v.section_id == section.id and bool(v.partage) else None


def _versions_communes_de(db, section: DossierSection) -> list:
    return (db.query(DossierSectionVersion).filter(DossierSectionVersion.section_id == section.id,
                                                   DossierSectionVersion.partage.is_(True))
            .order_by(DossierSectionVersion.numero.desc(), DossierSectionVersion.id.desc()).all())


def _avant(db, section: DossierSection, cur: Optional[DossierSectionVersion]) -> Optional[DossierSectionVersion]:
    """Le dernier texte ÉCRIT PAR LE PARTENAIRE avant le texte courant (l'« avant » d'une modification du
    chef de file), de cette même invitation."""
    if cur is None:
        return None
    for v in _versions_communes_de(db, section):
        if v.id != cur.id and v.ecrit_par == ECRIT_PAR_PARTENAIRE and v.author_invite_id == section.author_invite_id \
                and (v.numero or 0) < (cur.numero or 0):
            return v
    return None


def a_un_brouillon(db, section_id: int, invite_id: Optional[int]) -> bool:
    if not invite_id:
        return False
    return db.query(DossierPartBrouillon.id).filter(DossierPartBrouillon.section_id == section_id,
                                                    DossierPartBrouillon.invite_id == invite_id).first() is not None


def statut_de(db, section: DossierSection, rep: Optional[DossierRepartition] = None) -> str:
    """Statut CALCULÉ d'une partie (jamais stocké : impossible d'être incohérent) :
       à rédiger · en cours · envoyée · à revalider (par l'auteur) · validée ; une partie tirée du
       groupement : à valider · à revalider · validée."""
    if at.est_generee(section):
        from app.services import atelier_assemblage as asm
        return asm.statut(db, section)
    if section.author_kind != at.AUTEUR_INVITATION:
        return {at.A_ECRIRE: A_REDIGER, at.BROUILLON: EN_COURS, at.RELU: EN_COURS, at.VALIDE: VALIDEE,
                at.A_REVALIDER: A_REVALIDER}.get(section.statut or at.A_ECRIRE, EN_COURS)
    cur = _commune(db, section)
    if cur is None:
        return EN_COURS if a_un_brouillon(db, section.id, section.author_invite_id) else A_REDIGER
    if section.statut == at.VALIDE and section.validated_hash == cur.empreinte:
        return VALIDEE
    if cur.ecrit_par == ECRIT_PAR_CHEF or section.statut == at.A_REVALIDER:
        return A_REVALIDER
    return ENVOYEE


def mention(db, section: DossierSection, nom: str) -> str:
    """« Rédigé par le chef de file, à valider par X » / « Modifié par le chef de file, à revalider par X »."""
    if section.author_kind != at.AUTEUR_INVITATION:
        return ""
    cur = _commune(db, section)
    if cur is None or cur.ecrit_par != ECRIT_PAR_CHEF:
        return ""
    valide = section.statut == at.VALIDE and section.validated_hash == cur.empreinte
    if _avant(db, section, cur) is None:
        return (f"Rédigé par le chef de file, validé par {nom}" if valide else
                f"Rédigé par le chef de file, à valider par {nom}")
    return (f"Modifié par le chef de file, validé par {nom}" if valide else
            f"Modifié par le chef de file, à revalider par {nom}")


def empreinte_dossier(db, dossier: DossierPresentation, sections: Optional[list] = None) -> str:
    """Empreinte du DOSSIER ASSEMBLÉ : l'ordre, l'intitulé, l'auteur et l'empreinte du texte commun de chaque
    partie. Toute modification d'un texte commun la change."""
    sections = sections if sections is not None else at.sections_actives(db, dossier)
    com = textes_communs(db, sections)
    return _sha([(s.id, s.ordre, s.intitule, s.author_kind, s.author_invite_id or 0,
                  (com[s.id].empreinte if com.get(s.id) is not None else "")) for s in sections])


def _version_commune_out(v: Optional[DossierSectionVersion], texte: bool = True) -> Optional[dict]:
    """Un texte COMMUN, tel que tout membre peut le lire : jamais de source, jamais d'extrait."""
    if v is None:
        return None
    out = {"version_id": v.id, "numero": v.numero, "ecrit_par": v.ecrit_par or "", "empreinte": v.empreinte,
           "ia": bool(v.ia), "coupe": bool(v.coupe), "cree_le": _iso(v.created_at),
           "a_completer": len(me.placeholders(v.texte or "")),
           "faits_a_relire": far.non_traites(v.faits or []) if bool(v.partage) else None,
           "compteurs": (v.compteurs if isinstance(v.compteurs, dict) else None) if bool(v.partage) else None}
    if texte:
        out["texte"] = v.texte or ""
    return out


# ── Faits et compteurs d'un texte de partenaire ──────────────────────────────────────

def faits_communs(faits) -> list:
    """Ce qui part avec le texte ENVOYÉ : les faits À RELIRE (non traités), dans la forme d'A0, SANS leur
    source ni leur détail — pour que l'export du chef de file les bloque (décision 2b) sans rien dire de
    la matière du partenaire. Un fait relu par le partenaire ou relié à sa source n'est pas transmis."""
    out = []
    for x in faits or []:
        if not isinstance(x, dict) or x.get("statut") in (far.RELU, fs.AVEC_SOURCE):
            continue
        y = {k: x.get(k) for k in ("id", "fait", "type", "phrase", "message", "statut", "a_propos") if k in x}
        if x.get("type") == far.RESTE:
            y["nombre"] = int(x.get("nombre") or 0)
        out.append(y)
    return out


def compteurs(faits) -> dict:
    """Compteurs de sources PAR TYPE d'un texte (ce que le chef de file reçoit) : {par_type: {documents,
    declare, public, estimation, calcul, acheteur}, avec_source, a_relire, engagements}."""
    par = {k: 0 for k in TYPES_COMPTEURS}
    a_relire, eng, avec = 0, 0, 0
    for x in faits or []:
        if not isinstance(x, dict):
            continue
        if x.get("statut") == fs.AVEC_SOURCE:
            t = _TYPE_COMPTEUR.get(str((x.get("source") or {}).get("type") or ""))
            if t:
                par[t] += 1
                avec += 1
            continue
        if x.get("type") == fs.ENGAGEMENT:
            if x.get("statut") != far.RELU:
                eng += 1
            continue
        if x.get("statut") == far.A_RELIRE:
            a_relire += max(1, int(x.get("nombre") or 1)) if x.get("type") == far.RESTE else 1
    return {"par_type": par, "avec_source": avec, "a_relire": a_relire, "engagements": eng}


# ── Ce que l'IA du partenaire peut utiliser : SES faits, jamais ceux d'un autre ───────

def fiches_depot_par_lien(db, inv: ProjectInvite) -> list:
    """EMPLACEMENT de l'option (a) de la décision 5 (documents privés déposés par lien magique), PAS
    CONSTRUITE : l'avis du conseil sur qui est responsable du traitement n'est pas encore donné. Le jour
    venu, elle rendra les fiches des preuves rangées sous le tenant du marché avec proprietaire_kind
    'invitation' et proprietaire_invite_id = inv.id (le schéma de « Mes preuves » les prévoit déjà ; ni le
    chef de file ni preuves.faits_autorises ne les lisent). Aujourd'hui : rien."""
    return []


class ContextePartenaire:
    """Les faits autorisés d'UN partenaire pour SA partie (vague 4, décision 5) :
      • sans compte (lien magique) : ce qu'il a déclaré dans sa part (lot, qualifications, références,
        capacités, présentation), « déclaré par vous » ;
      • avec le compte Adjugo qui a rattaché son lien : en plus, SES preuves [F#], son profil [P#], son
        équipe [E#] (noms masqués avant l'IA) et des extraits de SON savoir-faire [S#], interrogés avec les
        seuls droits de son organisation.
    Jamais le profil, les preuves, le savoir-faire, le chiffrage ni les apports du chef de file ou d'un autre
    membre ; jamais le dossier de l'acheteur comme source d'une phrase sur l'entreprise."""

    def __init__(self, db, acces: "Acces"):
        from app.core.org import data_owner_id, member_ids
        from app.services.preuves import membres as membres_org, personnes
        self._db = db
        self.inv = acces.inv
        self.project_id = acces.project.id
        c = _contribution(db, acces.inv.id)
        self.contribution = c
        self.nom = nom_partenaire(acces.inv, c)
        self.lot = at._flat(c.lot if c else "")[:255]
        self.owner_id = None
        self.member_ids = []
        self.company = None
        self.team = []
        self.preuves_team = []
        u = acces.user if acces.mode == "compte" else None
        if u is not None:
            owner = data_owner_id(u, db)
            mids = member_ids(u, db)
            chef = set(membres_org(db, acces.dossier.owner_id)) | {acces.dossier.owner_id}
            # Garde-fou : un compte qui appartiendrait (ou serait passé) à l'organisation du chef de file
            # n'apporte RIEN de son organisation (aucune lecture croisée possible par ce chemin).
            if owner not in chef and not (set(mids) & chef):
                self.owner_id, self.member_ids = owner, list(mids)
                self.company = db.query(Company).filter(Company.user_id == owner).first()
                self.team = [m for m in ((self.company.team if self.company else None) or []) if isinstance(m, dict)]
                self.preuves_team = personnes(db, [owner])
        self.noms_entreprise = [x for x in (self.nom, getattr(self.company, "name", "") or "") if x]
        self._fiches = None

    @property
    def avec_compte(self) -> bool:
        return self.owner_id is not None

    def profil(self) -> str:
        """Ce que le partenaire a DÉCLARÉ dans sa part, ligne par ligne (+ son profil avec un compte)."""
        c = self.contribution
        lines = [f"Entreprise : {self.nom}" + (f" (lot : {self.lot})" if self.lot else "") + "."]
        if c is not None:
            quals = [at._flat(q.get("name") or q.get("nom")) if isinstance(q, dict) else at._flat(q)
                     for q in (c.qualifications or [])]
            quals = [q for q in quals if q]
            if quals:
                lines.append("Qualifications et certifications : " + " ; ".join(quals[:30]) + ".")
            for r in (c.references or [])[:30]:
                if not isinstance(r, dict) or not at._flat(r.get("intitule")):
                    continue
                parts = [at._flat(r.get("intitule"))]
                if r.get("client"):
                    parts.append("client " + at._flat(r.get("client")))
                if at._fmt_nombre(r.get("montant")):
                    parts.append("montant " + at._fmt_nombre(r.get("montant")) + " €")
                if r.get("annee"):
                    parts.append("année " + at._flat(r.get("annee")))
                lines.append("Référence : " + ", ".join(parts) + ".")
            cap = c.capacites if isinstance(c.capacites, dict) else {}
            if at._fmt_nombre(cap.get("effectif")):
                lines.append(f"Effectif : {at._fmt_nombre(cap.get('effectif'))} (salariés, personnes, collaborateurs, "
                             "compagnons, employés).")
            if at._fmt_nombre(cap.get("ca_n1")):
                lines.append(f"Chiffre d'affaires N-1 : {at._fmt_nombre(cap.get('ca_n1'))} €.")
            if at._flat(c.memoire_paragraph):
                lines.append("Présentation écrite par vous : " + at._flat(c.memoire_paragraph)[:3000])
        if self.company is not None:
            from app.services.preuves import aujourd_hui
            from app.services.preuves_reprise import cles_gerees
            try:
                gerees = cles_gerees(self._db, self.owner_id)
            except Exception:       # noqa: BLE001
                gerees = set()
            extra = at._profil_texte(self.company, exclure=gerees, jour=aujourd_hui())
            lines += [ln for ln in extra.split("\n")[1:] if ln.strip()]
        return "\n".join(lines)

    def equipe(self) -> str:
        return at._equipe_texte(self.team) if self.team else ""

    def faits_autorises(self) -> dict:
        return {"profil": self.profil(), "equipe": self.equipe(), "chiffrage": "", "partenaires": ""}

    def fiches(self, db, pseudonymiseur=None) -> list:
        """Les faits autorisés du partenaire, numérotés et typés (renvois [F#], [P#], [E#])."""
        if self._fiches is None or pseudonymiseur is not None:
            out = []
            if self.avec_compte:
                try:
                    out += fs.fiches_preuves(db, self.owner_id, project_id=None, pseudonymiseur=pseudonymiseur)
                except Exception as e:      # noqa: BLE001 — ses preuves illisibles : sa part déclarée suffit
                    logger.warning("groupement : preuves du partenaire illisibles (invitation %s) : %s",
                                   self.inv.id, type(e).__name__)
            out += fs.fiches_contexte(self.profil(), self.equipe(), "", [])
            out += fiches_depot_par_lien(db, self.inv)
            self._fiches = out
        return list(self._fiches)

    def extraits(self, db, requete: str, k: int = 6) -> list:
        """Extraits de SON savoir-faire (compte seulement), jamais un CV, jamais d'une autre organisation."""
        if not self.avec_compte or not self.member_ids:
            return []
        from app.services import rag
        try:
            return rag.retrieve_multi(db, list(self.member_ids), requete, k=k, relevance=True)
        except Exception as e:      # noqa: BLE001
            logger.warning("groupement : savoir-faire du partenaire illisible (invitation %s) : %s",
                           self.inv.id, type(e).__name__)
            return []

    def fiches_de_brouillon(self, db, b: Optional[DossierPartBrouillon]) -> list:
        """Fiches pour relire un brouillon déjà écrit : les siennes + les extraits qu'il cite (relus dans
        son organisation seulement)."""
        out = self.fiches(db)
        if b is None or not self.avec_compte:
            return out
        ids = []
        refs = {}
        for x in (b.sources or []):
            if isinstance(x, dict) and str(x.get("ref") or "").startswith(fs.EXTRAIT) and x.get("chunk_id"):
                refs[x["ref"]] = x
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
                chunks.append({"ref": ref, "chunk_id": c.id, "text": c.text or "", "doc_name": x.get("doc_name") or ""})
        return out + fs.fiches_extraits(chunks)

    def pseudonymiseur(self, textes=()):
        """Noms de SON équipe (profil, fiches « Équipe ») et noms de personnes repérés sans IA dans ce qui
        part à l'IA : masqués avant l'appel (doctrine § 7, règle 9)."""
        from app.services.fiches_import import equipe_avec_noms_reperes
        from app.services.pii import from_team
        return from_team(equipe_avec_noms_reperes(self.team + self.preuves_team, textes, exclure=self.noms_entreprise))


# ── L'espace PRIVÉ du lien : une clé que seul le navigateur du partenaire détient ─────
# Le lien d'une invitation manuelle a été remis au chef de file (pour qu'il le transmette) : le lien seul
# ne prouve donc pas qu'on est le partenaire. Sa matière privée (brouillons, sources, extraits, résultat de
# ses tâches) et ses actions (écrire, lancer l'aide de l'IA, envoyer, valider) exigent en plus la CLÉ de
# son espace, tirée au hasard à la première ouverture et rendue UNE fois à son navigateur (le serveur n'en
# garde que l'empreinte). Elle se récupère avec le code envoyé à l'adresse de l'invitation (brouillons
# gardés) ; sinon l'espace se RÉINITIALISE, et ses brouillons non envoyés sont alors EFFACÉS : celui qui
# réinitialise ne lit jamais rien (inscrit au journal du membre). Par le compte qui a rattaché le lien,
# aucune clé : le compte suffit.

ENTETE_CLE = "X-Adjugo-Espace"
MSG_CLE_REQUISE = ("Ouvrez votre espace privé sur cet appareil pour lire vos brouillons et rédiger votre partie.")
MSG_ESPACE_OUVERT = ("Votre espace privé est déjà ouvert sur un autre appareil. Saisissez le code reçu par email "
                     "pour l'ouvrir ici, ou réinitialisez-le : vos brouillons non envoyés seront alors effacés (vos "
                     "textes envoyés restent).")
MSG_ESPACE_COMPTE = ("Ce lien est rattaché à un compte Adjugo : rédigez vos parties depuis ce compte, dans « Partagé "
                     "avec moi ». Vos brouillons y sont, sans rien à ouvrir.")
MSG_CODE_REQUIS = ("Votre invitation vise une adresse email : recevez un code à cette adresse pour ouvrir votre espace "
                   "privé sur cet appareil.")
MSG_RATTACHER_ESPACE = ("Ce lien a déjà servi à rédiger dans un espace privé. Pour le rattacher à votre compte, ouvrez-le "
                        "dans le navigateur où vous rédigez votre partie, puis choisissez « Ouvrir dans mon Adjugo ». "
                        "Sur cet appareil, vous pouvez aussi réinitialiser d'abord votre espace privé : vos brouillons "
                        "non envoyés seront alors effacés.")


def _hash_cle(cle: str) -> str:
    return hashlib.sha256(("adjugo-espace:" + (cle or "")).encode("utf-8")).hexdigest()


def par_le_compte(inv: ProjectInvite) -> bool:
    """Le lien est rattaché à un compte Adjugo (« Partagé avec moi ») : sa matière privée et ses actions passent
    par ce compte seulement. Le chef de file détient le lien d'une invitation : par le lien, plus aucun espace."""
    return bool(getattr(inv, "accepted_by_user_id", None))


def cle_valide(inv: ProjectInvite, cle: Optional[str]) -> bool:
    """La clé de l'espace privé du lien. Un lien rattaché à un compte n'a plus d'espace par le lien : une clé prise
    avant le rattachement (par qui que ce soit, le chef de file compris) ne vaut plus rien."""
    import hmac
    if par_le_compte(inv):
        return False
    h = getattr(inv, "espace_hash", "") or ""
    return bool(h and cle) and hmac.compare_digest(_hash_cle(str(cle).strip()), h)


def _verifier_code(db, inv: ProjectInvite, code: str) -> None:
    """Le code reçu à l'adresse de l'invitation (otp/request) : il prouve l'adresse, comme otp/verify."""
    from app.routers.invites import _OTP_MAX_ATTEMPTS, _binding_required, _hash_otp, _is_expired, _mark_network_accepted
    if not _binding_required(inv) or not inv.otp_hash or not inv.otp_expires_at or _is_expired(inv.otp_expires_at):
        raise AtelierError(400, "code_absent", "Aucun code en attente : demandez d'abord un code.")
    if (inv.otp_attempts or 0) >= _OTP_MAX_ATTEMPTS:
        raise AtelierError(429, "trop_de_tentatives", "Trop de tentatives. Demandez un nouveau code.")
    if _hash_otp(str(code).strip()) != inv.otp_hash:
        inv.otp_attempts = (inv.otp_attempts or 0) + 1
        db.commit()
        raise AtelierError(400, "code_incorrect", "Code incorrect.")
    inv.otp_hash, inv.otp_expires_at = "", None
    inv.verified_at, inv.verified_email = utcnow(), inv.recipient
    _mark_network_accepted(inv)


def ouvrir_espace(db, inv: ProjectInvite, *, code: Optional[str] = None, reinitialiser: bool = False,
                  ip: str = "") -> dict:
    """Ouvre l'espace privé du lien et rend sa clé (une seule fois) :
      • lien rattaché à un compte Adjugo : refusé (403 « espace_par_le_compte ») — le compte suffit, et le chef
        de file qui détient le lien n'ouvre rien à sa place ;
      • première ouverture : une nouvelle clé ; quand le lien vise une adresse, seulement avec le code reçu à
        cette adresse (409 « code_requis » sinon) : celui qui a seulement le lien n'ouvre rien ;
      • déjà ouvert, avec le code reçu à l'adresse de l'invitation (otp/request) : une nouvelle clé,
        brouillons GARDÉS (l'adresse est prouvée) ;
      • déjà ouvert, `reinitialiser` : une nouvelle clé, brouillons non envoyés EFFACÉS ;
      • sinon 409 « espace_deja_ouvert »."""
    import secrets
    from app.routers.invites import _binding_required, _guest_actor, _invite_is_demo
    if _invite_is_demo(inv, db):
        raise AtelierError(403, "demo", "La démo est en lecture guidée : commencez votre essai gratuit de 30 jours pour co-construire "
                                        "une réponse avec vos partenaires.")
    if par_le_compte(inv):
        raise AtelierError(403, "espace_par_le_compte", MSG_ESPACE_COMPTE)
    effaces = 0
    mode = "ouverture"
    if not getattr(inv, "espace_hash", ""):
        if _binding_required(inv):
            if not code:
                raise AtelierError(409, "code_requis", MSG_CODE_REQUIS, code_possible=True)
            _verifier_code(db, inv, code)
    else:
        if code:
            _verifier_code(db, inv, code)
            mode = "code"
        elif reinitialiser:
            effaces = db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == inv.id).delete(
                synchronize_session=False)
            # Celui qui réinitialise n'a rien prouvé : l'adresse de l'invitation est à prouver de nouveau
            # (par le code envoyé au partenaire) avant d'envoyer ou de valider quoi que ce soit en son nom.
            inv.verified_at, inv.verified_email = None, ""
            mode = "reinitialisation"
        else:
            raise AtelierError(409, "espace_deja_ouvert", MSG_ESPACE_OUVERT,
                               code_possible=bool(_binding_required(inv)))
    cle = secrets.token_urlsafe(24)
    inv.espace_hash = _hash_cle(cle)
    db.commit()
    action = {"ouverture": "redaction.espace_ouvert", "code": "redaction.espace_rouvert",
              "reinitialisation": "redaction.espace_reinitialise"}[mode]
    detail = {"ouverture": "Espace privé ouvert", "code": "Espace privé rouvert sur un autre appareil (code reçu "
                                                         "par email)",
              "reinitialisation": f"Espace privé réinitialisé : {effaces} brouillon{'s' if effaces > 1 else ''} "
                                  f"effacé{'s' if effaces > 1 else ''}"}[mode]
    d = dossier_du_marche(db, db.get(Project, inv.project_id), inv.owner_id) if inv.project_id else None
    _journal(db, action=action, project_id=inv.project_id, owner_id=(d.owner_id if d else inv.owner_id),
             actor=_guest_actor(inv), actor_kind="guest", invite_id=inv.id, target_type="invite", target_id=inv.id,
             ip=ip, detail=detail)
    return {"cle": cle, "entete": ENTETE_CLE, "brouillons_effaces": int(effaces or 0)}


# ── Accès d'un partenaire ────────────────────────────────────────────────────────────

class Acces:
    """L'accès d'UN partenaire à la rédaction du dossier commun d'UN marché : par le lien de son invitation
    (mode « lien », avec la clé de son espace privé pour sa matière privée et ses actions), ou par le compte
    Adjugo qui a rattaché ce lien (mode « compte »). Il ne voit et n'écrit que SES parties, et lit le dossier
    assemblé (décision 3a)."""

    def __init__(self, db, inv: ProjectInvite, project: Project, dossier: DossierPresentation,
                 user: Optional[User] = None, mode: str = "lien", cle: Optional[str] = None):
        self.db, self.inv, self.project, self.dossier = db, inv, project, dossier
        self.user = user if mode == "compte" else None
        self.mode = mode
        self.cle_ok = mode == "compte" or cle_valide(inv, cle)
        self.lecteur = at.Lecteur(at.AUTEUR_INVITATION, dossier.owner_id,
                                  user_id=getattr(self.user, "id", None), invite_id=inv.id)

    @property
    def invite_id(self) -> int:
        return self.inv.id

    @property
    def acteur(self) -> str:
        return (self.inv.company_name or "invité")[:160]


def dossier_du_marche(db, project: Project, owner_hint: Optional[int] = None) -> Optional[DossierPresentation]:
    """Le dossier de présentation du marché, porté par le tenant du chef de file."""
    from app.routers.invites import tenant_owner_id
    owners = [o for o in dict.fromkeys([tenant_owner_id(project, db), owner_hint]) if o]
    for o in owners:
        d = at.get_dossier(db, project.id, o)
        if d is not None:
            return d
    return None


def acces_partenaire(db, inv: ProjectInvite, project: Project, user: Optional[User] = None,
                     mode: str = "lien", cle: Optional[str] = None) -> Acces:
    """Contrôles communs aux deux chemins (le lien lui-même — révoqué, décliné, expiré — est contrôlé par
    l'appelant : invites._valid_invite, journal_membre._shared_invite). Un sous-traitant n'est pas membre :
    même réponse qu'un dossier inexistant. Invitation du réseau pas encore acceptée : aperçu minimal. Un
    compte de l'organisation du chef de file n'est jamais le partenaire (même réponse qu'un dossier
    inexistant), même s'il avait rattaché le lien avant d'y entrer."""
    from app.routers.invites import _network_pending
    if (inv.role or "cotraitant") != "cotraitant":
        raise AtelierError(404, "dossier_commun_introuvable", MSG_PAS_DE_DOSSIER)
    if _network_pending(inv, db):
        raise AtelierError(403, "apercu_minimal", "Acceptez d'abord l'invitation pour lire et rédiger le dossier "
                                                  "commun.")
    d = dossier_du_marche(db, project, inv.owner_id)
    if d is None or not repartition_active(db, d):
        raise AtelierError(404, "dossier_commun_introuvable", MSG_PAS_DE_DOSSIER)
    if mode == "compte" and user is not None:
        from app.core.org import member_ids
        from app.services.preuves import membres as membres_org
        chef = set(membres_org(db, d.owner_id)) | {d.owner_id, inv.owner_id}
        if set(member_ids(user, db)) & chef:
            raise AtelierError(404, "dossier_commun_introuvable", MSG_PAS_DE_DOSSIER)
    return Acces(db, inv, project, d, user=user, mode=mode, cle=cle)


def _exiger_espace(acces: Acces) -> None:
    """La matière privée et les actions du partenaire exigent la clé de son espace (mode « lien ») ; un lien
    rattaché à un compte n'en a plus : son compte suffit."""
    if not acces.cle_ok:
        compte = acces.mode == "lien" and par_le_compte(acces.inv)
        raise AtelierError(403, "cle_espace_requise", MSG_ESPACE_COMPTE if compte else MSG_CLE_REQUISE,
                           espace_ouvert=bool(getattr(acces.inv, "espace_hash", "")), par_le_compte=compte)


def _exiger_ecriture(acces: Acces) -> None:
    from app.routers.invites import _invite_is_demo
    _exiger_espace(acces)
    if not getattr(acces.inv, "can_contribute", True):
        raise AtelierError(403, "co_construction_fermee", "La co-construction n'est pas activée pour ce lien.")
    if _invite_is_demo(acces.inv, acces.db):
        raise AtelierError(403, "demo", "La démo est en lecture guidée : commencez votre essai gratuit de 30 jours pour "
                                        "co-construire une réponse avec vos partenaires.")


def _exiger_identite(acces: Acces) -> None:
    """Envoyer un texte ou valider engage l'entreprise : même exigence d'identité que l'envoi de la part
    (adresse prouvée par code quand le lien vise une adresse, ou compte vérifié qui a rattaché le lien)."""
    from app.routers.invites import _binding_required
    u = acces.user
    if u is not None and acces.inv.accepted_by_user_id == u.id and getattr(u, "email_verified", False):
        return
    if _binding_required(acces.inv) and not acces.inv.verified_at:
        raise AtelierError(403, "identity_unverified", "Vérifiez votre adresse email avant d'envoyer ou de valider "
                                                       "votre partie.")


def parties_de(db, acces: Acces) -> list:
    """[(partie, répartition)] des parties ACTIVES confiées à ce partenaire, dans l'ordre du plan."""
    reps = (db.query(DossierRepartition).filter(DossierRepartition.dossier_id == acces.dossier.id,
                                                DossierRepartition.redacteur == PARTENAIRE,
                                                DossierRepartition.invite_id == acces.invite_id).all())
    by_sid = {r.section_id: r for r in reps}
    out = []
    for s in at.sections_actives(db, acces.dossier):
        r = by_sid.get(s.id)
        if r is not None and s.author_kind == at.AUTEUR_INVITATION and s.author_invite_id == acces.invite_id:
            out.append((s, r))
    return out


def _partie(db, acces: Acces, section_id: int) -> tuple:
    """SA partie, sinon 404 (la partie d'un autre membre n'existe pas pour lui)."""
    for s, r in parties_de(db, acces):
        if s.id == int(section_id):
            return s, r
    raise AtelierError(404, "partie_introuvable", "Partie introuvable.")


def _toujours_sienne(db, acces: Acces, section: DossierSection, rep: DossierRepartition) -> None:
    """Relue SOUS VERROU (la partie et sa ligne de répartition) : la partie est toujours la sienne. Le chef de file
    a pu la reprendre ou la confier à un autre entre la lecture et le verrou : rien n'est écrit (404)."""
    if rep.redacteur != PARTENAIRE or rep.invite_id != acces.invite_id or section.author_kind != at.AUTEUR_INVITATION \
            or section.author_invite_id != acces.invite_id or section.retiree_at is not None:
        db.rollback()
        raise AtelierError(404, "partie_introuvable", "Partie introuvable.")


def _du_compte(acces: Acces, b: Optional[DossierPartBrouillon]) -> bool:
    """Un brouillon écrit DEPUIS le compte du partenaire (ses preuves, son savoir-faire) ne se lit ni ne s'utilise
    par le lien : seulement depuis ce compte."""
    return b is not None and bool(b.auteur_user_id) and acces.mode != "compte"


MSG_COMMUN_MODIFIE = ("Le texte commun de cette partie a changé entre-temps (modifié par le chef de file, par exemple) : "
                      "relisez-le avant d'enregistrer ou d'envoyer. Votre saisie est gardée sur votre écran.")


def _exiger_commun_vu(section: DossierSection, commun: Optional[DossierSectionVersion], base_version_id) -> None:
    """Verrou optimiste sur le TEXTE COMMUN : l'écran dit quelle version il a montrée (`base_version_id`, None si
    rien n'était envoyé). Une modification du chef de file arrivée entre-temps n'est jamais remplacée en silence."""
    if base_version_id is BASE_DEFAUT:
        return
    vu = int(base_version_id) if base_version_id not in (None, "", 0) else None
    if (commun.id if commun is not None else None) != vu:
        raise AtelierError(409, "texte_modifie_entre_temps", MSG_COMMUN_MODIFIE,
                           version_courante_id=commun.id if commun is not None else None)


def _matiere_visible(acces: Acces, b: DossierPartBrouillon) -> tuple:
    """(sources, faits avec leur source) d'un brouillon, tels que CET accès peut les lire. Depuis le compte : les
    extraits et les preuves de l'organisation ACTUELLE du compte seulement — un membre retiré de l'organisation du
    partenaire ne relit plus ses extraits, ses documents ni ses preuves (comme `fiches_de_brouillon`)."""
    if acces.mode != "compte" or acces.user is None:
        return list(b.sources or []), fs.avec_source(b.faits or [])
    return _matiere_du_compte(acces.db, acces.user, b)


def _matiere_du_compte(db, user: User, b: DossierPartBrouillon) -> tuple:
    """(sources, faits avec leur source) d'un brouillon lus par CE compte : les extraits et les preuves de son
    organisation ACTUELLE seulement (vue, historique, export de la partie, export RGPD du compte)."""
    sources = list(b.sources or [])
    faits_src = fs.avec_source(b.faits or [])
    if not b.auteur_user_id or user is None:
        return sources, faits_src
    chunks, preuves = set(), set()
    for x in sources + [f.get("source") or {} for f in faits_src]:
        if isinstance(x, dict):
            if str(x.get("chunk_id") or "").isdigit():
                chunks.add(int(x["chunk_id"]))
            if str(x.get("preuve_id") or "").isdigit():
                preuves.add(int(x["preuve_id"]))
    if not chunks and not preuves:
        return sources, faits_src
    from app.core.org import data_owner_id, member_ids
    from app.models import KnowledgeChunk, Preuve
    vis_c = {r[0] for r in db.query(KnowledgeChunk.id).filter(KnowledgeChunk.id.in_(list(chunks) or [-1]),
                                                              KnowledgeChunk.user_id.in_(member_ids(user, db)))}
    vis_p = {r[0] for r in db.query(Preuve.id).filter(Preuve.id.in_(list(preuves) or [-1]),
                                                      Preuve.owner_id == data_owner_id(user, db))}

    def _ok(x):
        if not isinstance(x, dict):
            return True
        if str(x.get("chunk_id") or "").isdigit() and int(x["chunk_id"]) not in vis_c:
            return False
        return not (str(x.get("preuve_id") or "").isdigit() and int(x["preuve_id"]) not in vis_p)
    return [x for x in sources if _ok(x)], [f for f in faits_src if _ok(f.get("source") or {})]


# ── Brouillons privés du partenaire ──────────────────────────────────────────────────

def brouillons(db, section_id: int, invite_id: int) -> list:
    return (db.query(DossierPartBrouillon).filter(DossierPartBrouillon.section_id == section_id,
                                                  DossierPartBrouillon.invite_id == invite_id)
            .order_by(DossierPartBrouillon.numero.desc(), DossierPartBrouillon.id.desc()).all())


def brouillon_courant(db, section_id: int, invite_id: int) -> Optional[DossierPartBrouillon]:
    return (db.query(DossierPartBrouillon).filter(DossierPartBrouillon.section_id == section_id,
                                                  DossierPartBrouillon.invite_id == invite_id)
            .order_by(DossierPartBrouillon.numero.desc(), DossierPartBrouillon.id.desc()).first())


def _ajouter_brouillon(db, section: DossierSection, invite_id: int, *, texte: str, origine: str, ia: bool,
                       sources=None, faits=None, coupe: bool = False, base_id=None, base_version_id=None,
                       auteur_user_id=None, job_id=None) -> DossierPartBrouillon:
    from sqlalchemy import func
    n = db.query(func.max(DossierPartBrouillon.numero)).filter(DossierPartBrouillon.section_id == section.id,
                                                               DossierPartBrouillon.invite_id == invite_id).scalar() or 0
    t = at.normaliser_texte(texte)[:TEXTE_MAX]
    b = DossierPartBrouillon(section_id=section.id, dossier_id=section.dossier_id, project_id=section.project_id,
                             owner_id=section.owner_id, invite_id=invite_id, numero=n + 1, texte=t, origine=origine,
                             ia=bool(ia), sources=sources or [], faits=faits or [], compteurs=compteurs(faits),
                             empreinte=at.empreinte(t), coupe=bool(coupe), base_id=base_id,
                             base_version_id=base_version_id, auteur_user_id=auteur_user_id, job_id=job_id)
    db.add(b)
    db.flush()
    return b


def _brouillon_out(b: Optional[DossierPartBrouillon], acces: Acces, texte: bool = True) -> Optional[dict]:
    """Le brouillon PRIVÉ, pour son seul auteur. Un brouillon écrit depuis le compte (ses preuves, son
    savoir-faire) ne se lit jamais par le lien, ni son texte ni ses sources (None) ; depuis le compte, seuls les
    extraits et les preuves de l'organisation actuelle du compte sont rendus (`_matiere_visible`)."""
    if b is None or _du_compte(acces, b):
        return None
    lib = fs.libelles_actifs()
    sources, faits_src = _matiere_visible(acces, b)
    out = {"id": b.id, "numero": b.numero, "origine": b.origine, "origine_libelle": ORIGINES.get(b.origine, ""),
           "ia": bool(b.ia), "coupe": bool(b.coupe), "empreinte": b.empreinte, "cree_le": _iso(b.created_at),
           "base_version_id": b.base_version_id, "a_completer": len(me.placeholders(b.texte or "")),
           "faits_a_relire": far.non_traites(b.faits or []), "faits": fs.a_relire(b.faits or []),
           "controle": at.controle_out(b.faits or [], lib),
           "compteurs": b.compteurs if isinstance(b.compteurs, dict) else compteurs(b.faits),
           "sources": sources, "sources_depuis_le_compte": False}
    if lib:
        out["faits_sources"] = faits_src
    if texte:
        out["texte"] = b.texte or ""
    return out


def enregistrer_brouillon(db, acces: Acces, section_id: int, texte: str, base_brouillon_id,
                          base_version_id=BASE_DEFAUT) -> DossierPartBrouillon:
    """« J'écris moi-même » : un NOUVEAU brouillon privé, aucune IA. Ses faits sont contrôlés sur SES faits :
    ce qu'il écrit lui-même est sa déclaration ; un fait déjà à relire le reste — y compris un fait que le chef de
    file a mis dans le texte commun dont il part (« Partir du texte du chef de file »). `base_version_id` : le
    texte commun que son écran lui montrait (verrou optimiste, `_exiger_commun_vu`)."""
    _exiger_ecriture(acces)
    section, rep = _partie(db, acces, section_id)
    rep = _verrouiller_rep(db, rep)
    section = at._verrouiller(db, section)
    _toujours_sienne(db, acces, section, rep)
    cur = brouillon_courant(db, section.id, acces.invite_id)
    base = int(base_brouillon_id) if base_brouillon_id not in (None, "", 0) else None
    if (cur.id if cur else None) != base or _du_compte(acces, cur):
        raise AtelierError(409, "brouillon_modifie", "Votre texte a changé depuis que vous l'avez ouvert : rechargez-le "
                                                     "avant d'enregistrer (votre saisie n'a pas été perdue de votre écran).",
                           brouillon_courant_id=cur.id if cur and not _du_compte(acces, cur) else None)
    commun = _commune(db, section)
    _exiger_commun_vu(section, commun, base_version_id)
    t = at.normaliser_texte(texte)
    if len(t) > TEXTE_MAX:
        raise AtelierError(422, "texte_trop_long", f"Une partie compte au plus {TEXTE_MAX} caractères.")
    if cur is not None and cur.empreinte == at.empreinte(t):
        db.commit()                 # rien à écrire : les verrous sont rendus
        return cur
    ctx = ContextePartenaire(db, acces)
    textes_ia = [b.texte or "" for b in brouillons(db, section.id, acces.invite_id) if b.ia]
    ia = at.ia_a_servi(t, textes_ia)
    anciens = list((cur.faits if cur is not None else (commun.faits if commun is not None else [])) or [])
    if commun is not None and cur is not None and commun.ecrit_par == ECRIT_PAR_CHEF and commun.empreinte != cur.empreinte:
        # Le texte commun écrit (ou retouché) par le chef de file : ses faits à relire le restent chez le partenaire
        # (ses propres faits, plus bas dans la liste, gardent ce qu'il en a dit).
        anciens = [dict(x) for x in (commun.faits or []) if isinstance(x, dict)] + anciens
    base_texte = (cur.texte if cur is not None else (commun.texte if commun is not None else "")) or ""
    faits = fs.controler(t, ctx.fiches_de_brouillon(db, cur), acheteur=None, noms_entreprise=ctx.noms_entreprise,
                         section_entreprise=at.section_sur_l_entreprise(section), mode="utilisateur",
                         anciens=anciens, base_texte=base_texte)
    b = _ajouter_brouillon(db, section, acces.invite_id, texte=t, origine="utilisateur", ia=ia,
                           sources=(cur.sources if cur is not None and ia else []), faits=faits,
                           base_id=cur.id if cur else None, base_version_id=commun.id if commun else None,
                           auteur_user_id=getattr(acces.user, "id", None))
    db.commit()
    db.refresh(b)
    return b


def traiter_fait(db, acces: Acces, section_id: int, fait_id: str, statut: str, ip: str = "") -> dict:
    """« Relu par vous » (ou retour à « à relire ») sur un fait de SON brouillon courant. Adjugo ne dit
    jamais qu'un fait est bon : c'est le partenaire qui déclare l'avoir relu. Quand son brouillon EST le texte
    commun, sa relecture vaut pour le texte commun (lu par le chef de file, qui bloque l'export) : elle engage
    l'entreprise comme un envoi — même exigence d'identité (contre-relecture : après une réinitialisation, le chef
    de file qui détient le lien recopiait le texte commun dans un brouillon et effaçait ses faits à relire) — et elle
    est inscrite au journal chaîné."""
    _exiger_ecriture(acces)
    if statut not in (far.RELU, far.A_RELIRE):
        raise AtelierError(422, "statut_invalide", "Statut inconnu.")
    section, _rep = _partie(db, acces, section_id)
    b = brouillon_courant(db, section.id, acces.invite_id)
    if _du_compte(acces, b):
        b = None                    # écrit depuis le compte : ne se traite jamais par le lien
    faits = [dict(x) for x in ((b.faits if b else None) or []) if isinstance(x, dict)]
    hit = next((x for x in faits if x.get("id") == fait_id), None)
    if b is None or hit is None:
        raise AtelierError(404, "fait_introuvable", "Ce fait n'est plus dans le texte : rechargez la partie.")
    cur = _commune(db, section)
    vaut_pour_le_commun = cur is not None and bool(b.empreinte) and cur.empreinte == b.empreinte
    if vaut_pour_le_commun:
        _exiger_identite(acces)
    if hit.get("type") == far.RESTE:
        raise AtelierError(409, "faits_non_detailles", "Ces faits ne sont pas détaillés : découpez ou raccourcissez la "
                                                       "partie pour les relire un par un.")
    if hit.get("statut") == fs.AVEC_SOURCE:
        raise AtelierError(409, "fait_avec_source", "Ce fait est déjà relié à l'endroit où Adjugo l'a trouvé.")
    if statut == far.RELU:
        hit.update(statut=far.RELU, relu_par=getattr(acces.user, "id", None), relu_le=at._now_iso())
    else:
        hit["statut"] = far.A_RELIRE
        hit.pop("relu_par", None)
        hit.pop("relu_le", None)
    b.faits = faits
    b.compteurs = compteurs(faits)
    flag_modified(b, "faits")
    flag_modified(b, "compteurs")
    # Son brouillon EST le texte commun (texte envoyé, ou texte du chef de file qu'il a validé) : sa relecture
    # vaut pour le texte commun, que lit le chef de file (faits à relire SANS source, compteurs) et qui bloque
    # l'export tant qu'un fait reste à relire. Le texte ne change pas : son empreinte, ses validations et celle
    # du dossier assemblé non plus.
    if vaut_pour_le_commun:
        avant = far.non_traites(cur.faits or [])
        cur.faits = faits_communs(faits)
        cur.compteurs = compteurs(faits)
        flag_modified(cur, "faits")
        flag_modified(cur, "compteurs")
        apres = far.non_traites(cur.faits or [])
    db.commit()
    if vaut_pour_le_commun and avant != apres:
        titre = _titre(acces.dossier, section)
        _journal(db, action="redaction.fait_relu" if statut == far.RELU else "redaction.fait_a_relire",
                 project_id=acces.project.id, owner_id=acces.dossier.owner_id, actor=acces.acteur, actor_kind="guest",
                 invite_id=acces.invite_id, target_id=section.id, ip=ip,
                 detail=(f"Fait relu par le partenaire dans le texte envoyé : {titre}" if statut == far.RELU
                         else f"Fait remis à relire par le partenaire dans le texte envoyé : {titre}"),
                 meta={"faits_a_relire": apres, "par_le": acces.mode})
    return hit


# ── Envoyer, valider, rétablir (le partenaire) ───────────────────────────────────────

def _verrouiller_rep(db, rep: DossierRepartition) -> DossierRepartition:
    return (db.query(DossierRepartition).filter(DossierRepartition.id == rep.id)
            .populate_existing().with_for_update().first() or rep)


def _job_en_cours(db, job_id) -> Optional[Job]:
    if not job_id:
        return None
    j = db.get(Job, job_id)
    return j if j is not None and j.status in ("pending", "running") else None


def _origine_commune(origine: str) -> str:
    return origine if origine in (at.IA, at.RACCOURCI) else at.UTILISATEUR


def envoyer(db, acces: Acces, section_id: int, brouillon_id: int, avertissement_lu: bool, ip: str = "",
            base_version_id=BASE_DEFAUT) -> DossierSection:
    """Le partenaire ENVOIE son brouillon courant : il devient le texte COMMUN de la partie (une version
    `partage` de l'atelier), lu par le chef de file et par les autres membres. Rien de privé ne part : ni
    source, ni extrait — ses faits à relire (sans leur source) et ses compteurs de sources par type. Il en
    est prévenu avant (`avertissement_lu`, décision 3a). Une modification du chef de file arrivée depuis que
    son écran a montré le texte commun (`base_version_id`), ou depuis l'écriture de son brouillon, n'est jamais
    remplacée en silence (409 « texte_modifie_entre_temps » : l'écran montre l'avant et l'après)."""
    _exiger_ecriture(acces)
    _exiger_identite(acces)
    if not avertissement_lu:
        raise AtelierError(422, "avertissement_requis", AVERTISSEMENT_ENVOI)
    section, rep = _partie(db, acces, section_id)
    rep = _verrouiller_rep(db, rep)
    section = at._verrouiller(db, section)
    _toujours_sienne(db, acces, section, rep)
    if _job_en_cours(db, rep.job_id) is not None:
        raise AtelierError(409, "aide_en_cours", "Adjugo rédige cette partie en ce moment : attendez la fin de la "
                                                 "rédaction avant d'envoyer.")
    b = brouillon_courant(db, section.id, acces.invite_id)
    if b is None or b.id != int(brouillon_id or 0) or _du_compte(acces, b):
        raise AtelierError(409, "brouillon_modifie", "Votre texte a changé : rechargez-le avant de l'envoyer.",
                           brouillon_courant_id=b.id if b and not _du_compte(acces, b) else None)
    if not (b.texte or "").strip():
        raise AtelierError(422, "partie_vide", "Cette partie n'a pas de texte à envoyer.")
    cur = _commune(db, section)
    if base_version_id is not BASE_DEFAUT:
        _exiger_commun_vu(section, cur, base_version_id)
    elif cur is not None and cur.ecrit_par == ECRIT_PAR_CHEF and b.base_version_id != cur.id \
            and b.empreinte != cur.empreinte:
        # Écran qui ne dit pas ce qu'il a montré : un brouillon écrit AVANT la modification du chef de file ne la
        # remplace pas sans qu'il l'ait vue.
        raise AtelierError(409, "texte_modifie_entre_temps", MSG_COMMUN_MODIFIE, version_courante_id=cur.id)
    if cur is not None and cur.empreinte == b.empreinte and cur.ecrit_par == ECRIT_PAR_PARTENAIRE:
        # Même texte : seuls ses faits traités depuis et ses compteurs sont rafraîchis.
        cur.faits = faits_communs(b.faits)
        cur.compteurs = compteurs(b.faits)
        flag_modified(cur, "faits")
        flag_modified(cur, "compteurs")
        section.lock_version = (section.lock_version or 0) + 1
        nouveau = False
    else:
        at.ajouter_version(db, section, texte=b.texte or "", origine=_origine_commune(b.origine), ia=bool(b.ia),
                           sources=[], faits=faits_communs(b.faits), coupe=bool(b.coupe),
                           base_version_id=cur.id if cur else None, auteur_user_id=None, partage=True,
                           ecrit_par=ECRIT_PAR_PARTENAIRE, compteurs=compteurs(b.faits))
        nouveau = True
    db.commit()
    from app.routers.invites import _mark_network_accepted
    _mark_network_accepted(acces.inv)
    db.commit()
    _journal(db, action="redaction.part_envoyee", project_id=acces.project.id, owner_id=acces.dossier.owner_id,
             actor=acces.acteur, actor_kind="guest", invite_id=acces.invite_id, target_id=section.id, ip=ip,
             detail=f"Partie envoyée : {_titre(acces.dossier, section)}",
             meta={"nouveau_texte": nouveau, "compteurs": compteurs(b.faits)})
    apres_changement_commun(db, acces.project, acces.dossier, f"partie « {_titre(acces.dossier, section)} » envoyée",
                            actor=acces.acteur, actor_kind="guest", ip=ip, invite_id=acces.invite_id)
    _notifier_chef(db, acces, section)
    db.refresh(section)
    return section


def valider_part(db, acces: Acces, section_id: int, version_id: int, ip: str = "") -> DossierSection:
    """Le partenaire VALIDE le texte commun courant de sa partie (le sien, ou celui que le chef de file a
    écrit ou modifié : il l'accepte). Pour un texte du chef de file, le contrôle des faits tourne d'abord
    chez lui, sur SES faits : ce qu'il ne peut pas sourcer reste à relire (rien n'est blanchi). « Qui fait quoi
    dans le groupement » (assemblage) se valide par le même geste."""
    _exiger_ecriture(acces)
    _exiger_identite(acces)
    from app.services import atelier_assemblage as asm
    qfq = asm.qfq_de(db, acces.dossier)
    if qfq is not None and qfq.id == int(section_id or 0):
        return asm.valider(db, acces.project, acces.dossier, qfq, membre=PARTENAIRE, invite_id=acces.invite_id,
                           user_id=getattr(acces.user, "id", None), version_id=version_id, actor=acces.acteur,
                           actor_kind="guest", ip=ip)
    section, rep = _partie(db, acces, section_id)
    rep = _verrouiller_rep(db, rep)
    section = at._verrouiller(db, section)
    _toujours_sienne(db, acces, section, rep)
    cur = _commune(db, section)
    if cur is None or cur.id != int(version_id or 0):
        raise AtelierError(409, "texte_modifie_entre_temps", "Le texte de cette partie a changé : rechargez-le avant de "
                                                             "le valider.",
                           version_courante_id=cur.id if cur else None)
    if not (cur.texte or "").strip():
        raise AtelierError(422, "partie_vide", "Cette partie n'a pas de texte à valider.")
    if cur.ecrit_par == ECRIT_PAR_CHEF:
        ctx = ContextePartenaire(db, acces)
        der = brouillon_courant(db, section.id, acces.invite_id)
        if _du_compte(acces, der):
            der = None
        faits = fs.controler(cur.texte or "", ctx.fiches_de_brouillon(db, der), acheteur=None,
                             noms_entreprise=ctx.noms_entreprise, section_entreprise=at.section_sur_l_entreprise(section),
                             mode="ia", anciens=((der.faits if der else None) or []) + list(cur.faits or []))
        faits = _garder_ses_declarations(db, acces, section, faits)
        _ajouter_brouillon(db, section, acces.invite_id, texte=cur.texte or "", origine="acceptee", ia=bool(cur.ia),
                           sources=[], faits=faits, base_id=der.id if der else None, base_version_id=cur.id,
                           auteur_user_id=getattr(acces.user, "id", None))
        cur.faits = faits_communs(faits)
        cur.compteurs = compteurs(faits)
        flag_modified(cur, "faits")
        flag_modified(cur, "compteurs")
    section.statut = at.VALIDE
    section.validated_version_id = cur.id
    section.validated_hash = cur.empreinte
    section.validated_at = utcnow()
    # Jamais l'identifiant du compte d'un autre membre dans ce que lit le chef de file : qui a validé, c'est
    # l'auteur de la partie (l'invitation), inscrit au journal.
    section.validated_by = None
    section.lock_version = (section.lock_version or 0) + 1
    db.commit()
    _journal(db, action="redaction.part_validee", project_id=acces.project.id, owner_id=acces.dossier.owner_id,
             actor=acces.acteur, actor_kind="guest", invite_id=acces.invite_id, target_id=section.id, ip=ip,
             detail=f"Partie validée : {_titre(acces.dossier, section)}",
             meta={"version": cur.numero, "empreinte": cur.empreinte, "ecrit_par": cur.ecrit_par})
    rafraichir_validations(db, acces.project, acces.dossier)
    db.refresh(section)
    return section


def _garder_ses_declarations(db, acces: Acces, section: DossierSection, faits: list) -> list:
    """Le partenaire valide un texte écrit ou retouché par le chef de file (ou une phrase de transition) : ses
    propres phrases, inchangées, gardent ce qu'il en avait dit (« déclaré par vous ») — seul ce que le chef de file a
    ajouté ou modifié est à relire. Un fait garde l'identifiant de sa phrase : même fait, même phrase."""
    siens = {}
    for b in brouillons(db, section.id, acces.invite_id):            # du plus récent au plus ancien
        if _du_compte(acces, b):
            continue
        for x in (b.faits or []):
            if isinstance(x, dict) and x.get("id") and x.get("statut") == fs.AVEC_SOURCE \
                    and (x.get("source") or {}).get("type") == fs.T_VOUS:
                siens.setdefault(x["id"], x)
    if not siens:
        return faits
    return [dict(siens[x["id"]]) if isinstance(x, dict) and x.get("statut") == far.A_RELIRE and x.get("id") in siens
            else x for x in faits]


def retablir(db, acces: Acces, section_id: int, base_version_id, version_id=None, ip: str = "") -> DossierSection:
    """Le partenaire RÉTABLIT sa version après une modification du chef de file : son texte d'avant
    redevient le texte commun (nouvelle version, l'historique reste entier)."""
    _exiger_ecriture(acces)
    _exiger_identite(acces)
    section, rep = _partie(db, acces, section_id)
    rep = _verrouiller_rep(db, rep)
    section = at._verrouiller(db, section)
    _toujours_sienne(db, acces, section, rep)
    cur = _commune(db, section)
    if cur is None or cur.id != int(base_version_id or 0):
        raise AtelierError(409, "texte_modifie_entre_temps", "Le texte de cette partie a changé : rechargez-le.",
                           version_courante_id=cur.id if cur else None)
    if cur.ecrit_par != ECRIT_PAR_CHEF:
        raise AtelierError(409, "rien_a_retablir", "Le texte courant est déjà le vôtre.")
    if version_id not in (None, "", 0):
        src = db.get(DossierSectionVersion, int(version_id))
        if src is None or src.section_id != section.id or not bool(src.partage) \
                or src.ecrit_par != ECRIT_PAR_PARTENAIRE or src.author_invite_id != acces.invite_id:
            raise AtelierError(404, "version_introuvable", "Version introuvable.")
    else:
        src = _avant(db, section, cur)
        if src is None:
            raise AtelierError(409, "rien_a_retablir", "Vous n'avez pas encore envoyé de texte pour cette partie : "
                                                      "écrivez-le, ou validez celui du chef de file.")
    at.ajouter_version(db, section, texte=src.texte or "", origine=src.origine, ia=bool(src.ia), sources=[],
                       faits=[dict(x) for x in (src.faits or []) if isinstance(x, dict)], coupe=bool(src.coupe),
                       base_version_id=cur.id, restaure_de=src.id, auteur_user_id=None, partage=True,
                       ecrit_par=ECRIT_PAR_PARTENAIRE, compteurs=src.compteurs)
    db.commit()
    _journal(db, action="redaction.part_retablie", project_id=acces.project.id, owner_id=acces.dossier.owner_id,
             actor=acces.acteur, actor_kind="guest", invite_id=acces.invite_id, target_id=section.id, ip=ip,
             detail=f"Version du partenaire rétablie : {_titre(acces.dossier, section)}",
             meta={"version_retablie": src.numero})
    apres_changement_commun(db, acces.project, acces.dossier, f"partie « {_titre(acces.dossier, section)} » rétablie",
                            actor=acces.acteur, actor_kind="guest", ip=ip, invite_id=acces.invite_id)
    db.refresh(section)
    return section


def _notifier_chef(db, acces: Acces, section: DossierSection) -> None:
    """Prévient le chef de file qu'une partie est arrivée (best-effort, anti-rafale)."""
    try:
        from app.routers.invites import _mandataire_email, _notify_allowed, _send_mails_async
        to = _mandataire_email(acces.dossier.owner_id, db)
        if not to or not _notify_allowed(("redaction_envoi", acces.invite_id)):
            return
        from app.core.config import get_settings
        base = (get_settings().APP_BASE_URL or "").rstrip("/")
        nom = nom_partenaire(acces.inv, _contribution(db, acces.invite_id))
        _send_mails_async([(to, f"{nom} a envoyé sa partie — {acces.project.name[:60]}",
                            f"Bonjour,\n\n{nom} vient d'envoyer sa partie « {_titre(acces.dossier, section)} » du "
                            f"dossier de présentation du marché « {acces.project.name} ».\n\nRelisez-la dans "
                            f"l'atelier, onglet « Qui écrit quoi » :\n{base}/app\n\n— Adjugo")])
    except Exception:       # noqa: BLE001
        pass


# ── L'aide de l'IA du partenaire : facturation, tâche, exécution ─────────────────────

def _payeur(db, dossier: DossierPresentation) -> Optional[User]:
    """Le compte de facturation du chef de file (propriétaire de l'organisation qui porte le dossier)."""
    from app.core.quota import _billing_user
    owner = db.get(User, dossier.owner_id)
    return _billing_user(owner, db) if owner is not None else None


def _deja_ia(db, section: DossierSection) -> bool:
    """La partie a-t-elle déjà été rédigée par l'IA (atelier, ou brouillon de l'IA d'un partenaire) ?"""
    if at._deja_redigee_par_ia(db, section):
        return True
    return db.query(DossierPartBrouillon.id).filter(DossierPartBrouillon.section_id == section.id,
                                                    DossierPartBrouillon.ia.is_(True),
                                                    DossierPartBrouillon.origine.in_(["ia", "raccourci"])
                                                    ).first() is not None


def facturer_aide_partenaire(db, acces: Acces, section: DossierSection, job_id: int, estimation_eur: float) -> dict:
    """LA fonction de facturation de l'aide de l'IA d'un partenaire (décisions 4a et 6a), appelée UNE fois
    par tâche, AVANT tout appel à l'IA :
      • le quota débité est celui du CHEF DE FILE (son compte de facturation) : la première action de l'IA
        sur le dossier compte pour 1 analyse, la première rédaction d'une partie y est comprise, refaire une
        partie est gratuit jusqu'à ATELIER_REGEN_GRATUITES fois par dossier — JAMAIS d'analyse en plus au nom
        du partenaire (une refonte payante est refusée) ;
      • son essai : le budget de l'essai du chef de file s'applique ; essai terminé, forfait inactif, quota
        atteint, compte de démonstration : refus ;
      • la portée de facturation technique est propre à l'invitation (`tenant_partenaire`), posée par la
        tâche de fond (plafonds et disjoncteurs de l'IA séparés de ceux du chef de file) ;
      • remboursement si l'IA tombe : `atelier.rembourser` sur le relevé rendu ici (payeur_id).
    Tout refus est rendu au partenaire avec un message NEUTRE (« aide_indisponible ») qui ne révèle rien du
    forfait, du quota ni de l'essai du chef de file ; il peut toujours écrire lui-même."""
    from fastapi import HTTPException
    payeur = _payeur(db, acces.dossier)
    if payeur is None:
        raise AtelierError(409, "aide_indisponible", MSG_AIDE_INDISPONIBLE)
    try:
        from app.services.budget_ia import verifier
        verifier(payeur, db, "atelier", estimation_eur)
        releve = at._debiter(db, payeur, acces.dossier, [section], False, job_id, estimation_eur, deja_ia=_deja_ia)
    except AtelierError as e:
        db.rollback()
        if e.code in ("premiere_redaction_en_cours", "reessayer"):
            raise AtelierError(409, "aide_occupee", MSG_AIDE_OCCUPEE)
        raise AtelierError(409, "aide_indisponible", MSG_AIDE_INDISPONIBLE)
    except HTTPException:
        db.rollback()
        raise AtelierError(409, "aide_indisponible", MSG_AIDE_INDISPONIBLE)
    releve.update(dossier_id=acces.dossier.id, rendu=False, portee=PORTEE_PARTENAIRE, invite_id=acces.invite_id,
                  section_id=section.id, tenant=tenant_partenaire(acces.invite_id))
    return releve


def lancer_aide(db, acces: Acces, section_id: int, action: str = "rediger", cible: Optional[int] = None) -> Job:
    """« Rédiger avec Adjugo à partir de mes documents » (ou « Raccourcir ») : lancé PAR le partenaire, sur
    SA partie, en tâche de fond. La tâche n'a aucun compte propriétaire : elle appartient à son invitation
    (portée « partenaire ») et ne se lit qu'avec son accès."""
    from app.services.jobs import run_in_thread
    _exiger_ecriture(acces)
    # C'est le partenaire qui lance son aide de l'IA, jamais celui qui détient seulement le lien : même exigence
    # d'identité qu'envoyer et valider (adresse prouvée par code quand le lien vise une adresse).
    _exiger_identite(acces)
    if action not in ("rediger", "raccourcir"):
        raise AtelierError(422, "action_inconnue", "Action inconnue.")
    kind = JOB_REDIGER if action == "rediger" else JOB_RACCOURCIR
    section, rep = _partie(db, acces, section_id)
    rep = _verrouiller_rep(db, rep)
    section = at._verrouiller(db, section)
    _toujours_sienne(db, acces, section, rep)
    if _job_en_cours(db, rep.job_id) is not None:
        raise AtelierError(409, "aide_en_cours", "Adjugo rédige déjà cette partie : attendez la fin de la rédaction.")
    cap = plafond_partie()
    if int(rep.aides_ia or 0) >= cap:
        raise AtelierError(409, "plafond_partie", MSG_PLAFOND.format(n=cap))
    ctx = ContextePartenaire(db, acces)
    base = brouillon_courant(db, section.id, acces.invite_id)
    if kind == JOB_RACCOURCIR:
        if base is None or not (base.texte or "").strip() or _du_compte(acces, base):
            raise AtelierError(422, "partie_vide", "Il n'y a pas encore de texte à raccourcir dans cette partie.")
        # Aucun CV ne part à l'IA, par le lien comme par le compte : la forme d'un CV inséré suffit à le
        # reconnaître, même sans compte (aucune fiche « Équipe » connue).
        from app.services.preuves_atelier import refuser_cv_pour_ia
        refuser_cv_pour_ia(db, ctx.owner_id or 0, base.texte)
        n = len(re.findall(r"\w+", base.texte or ""))
        cible = int(cible) if cible else (rep.longueur_mots or at.cible_mots(section, None, base.texte)
                                          or max(30, int(n * 0.7)))
        if cible < 30:
            raise AtelierError(422, "cible_invalide", "Visez au moins 30 mots.")
        if cible >= n:
            raise AtelierError(422, "deja_assez_court", f"Le texte compte déjà {n} mots, pour {cible} visés : rien à "
                                                        "raccourcir.")
    from app.services.budget_ia import estimer_atelier
    estimation = estimer_atelier(1, raccourcir=(kind == JOB_RACCOURCIR))
    label = ("Votre partie : rédaction de « " if kind == JOB_REDIGER else "Votre partie : raccourcir « ") \
        + (section.intitule or "")[:120] + " »"
    job = Job(user_id=None, portee=PORTEE_PARTENAIRE, invite_id=acces.invite_id, kind=kind, status="pending",
              label=label[:255])
    db.add(job)
    db.flush()
    rep.job_id = job.id
    rep.aides_ia = int(rep.aides_ia or 0) + 1
    jid, rid = job.id, rep.id
    db.commit()
    try:
        releve = facturer_aide_partenaire(db, acces, section, jid, estimation)
    except Exception:
        db.rollback()
        _annuler(db, jid, rid)
        raise
    job = db.get(Job, jid)
    job.result = {"_debit": releve}
    db.commit()
    args = dict(job_id=jid, invite_id=acces.invite_id, section_id=section.id, kind=kind, cible=cible,
                user_id=getattr(acces.user, "id", None), mode=acces.mode)

    def _work(jdb):
        return _executer(jdb, **args)

    def _on_error(jdb, j):
        at.rembourser(jdb, j)
        liberer_job(jdb, j.id, rendre_aide=True)

    run_in_thread(jid, _work, on_error=_on_error, tenant_id=tenant_partenaire(acces.invite_id),
                  error_message=MSG_IA_PANNE)
    return db.get(Job, jid)


def _annuler(db, job_id: int, rep_id: int) -> None:
    """Facturation refusée : la tâche n'a jamais démarré, elle disparaît et l'aide est rendue."""
    try:
        rep = db.get(DossierRepartition, rep_id)
        if rep is not None and rep.job_id == job_id:
            rep.job_id = None
            rep.aides_ia = max(0, int(rep.aides_ia or 0) - 1)
        j = db.get(Job, job_id)
        if j is not None:
            db.delete(j)
        db.commit()
    except Exception:       # noqa: BLE001 — au pire, la reprise au démarrage la clôt
        db.rollback()


def liberer_job(db, job_id: int, rendre_aide: bool = False) -> None:
    """Tâche de partenaire terminée, en échec ou interrompue : la partie est libérée (et l'aide rendue si
    l'IA n'a rien produit)."""
    rows = db.query(DossierRepartition).filter(DossierRepartition.job_id == job_id).all()
    for r in rows:
        r.job_id = None
        if rendre_aide:
            r.aides_ia = max(0, int(r.aides_ia or 0) - 1)
    if rows:
        db.commit()


class _Indisponible(RuntimeError):
    pass


def _executer(db, *, job_id: int, invite_id: int, section_id: int, kind: str, cible: Optional[int], user_id,
              mode: str) -> dict:
    """Dans le fil de la tâche de fond (portée de facturation de l'invitation posée par run_in_thread) :
    prépare tout avec la base, appelle l'IA SANS base (noms masqués, coût mesuré), puis range le texte dans
    un NOUVEAU brouillon privé du partenaire, avec ses faits contrôlés sur SES sources."""
    from app.services.agents import memoire as moteur
    from app.services.llm import LLMUnavailable, cost_meter, pii_scope
    inv = db.get(ProjectInvite, invite_id)
    project = db.get(Project, inv.project_id) if inv is not None else None
    if inv is None or project is None or project.deleted_at is not None or not peut_rediger(db, inv)[0]:
        raise _Indisponible("invitation retirée")
    dossier = dossier_du_marche(db, project, inv.owner_id)
    section = db.get(DossierSection, section_id)
    if dossier is None or section is None or section.dossier_id != dossier.id or section.retiree_at is not None \
            or section.author_invite_id != invite_id:
        raise _Indisponible("partie retirée")
    user = db.get(User, user_id) if user_id else None
    acces = Acces(db, inv, project, dossier, user=user, mode=mode if user is not None else "lien")
    ctx = ContextePartenaire(db, acces)
    rep = db.query(DossierRepartition).filter(DossierRepartition.section_id == section.id).first()
    base = brouillon_courant(db, section.id, invite_id)
    tenant = tenant_partenaire(invite_id)
    act = at.sections_actives(db, dossier)
    rangs = at._rangs(dossier, act)
    chunks, partie, acheteur = [], None, None
    fiches_ent = ctx.fiches(db)
    if kind == JOB_REDIGER:
        dossier_acheteur, payload, entiers, lu = "", None, set(), {}
        if getattr(inv, "can_view_docs", True):
            from app.services.preuves import membres as membres_org
            mids_chef = membres_org(db, dossier.owner_id)
            lu = at.lire_dossier_acheteur(db, project, mids_chef)
            dossier_acheteur, payload, entiers = at._dossier_pour_ia(project, lu)
            if lu.get("integral") and payload is None:
                lu = at.lire_dossier_acheteur(db, project, mids_chef, integrale=False)
                dossier_acheteur = lu.get("texte") or ""
            acheteur = at._acheteur(project, lu, payload)
        chunks = ctx.extraits(db, at._requete(section))
    textes = [f.texte for f in fiches_ent] + [c.get("text") or "" for c in chunks]
    if kind == JOB_RACCOURCIR and base is not None:
        textes.append(base.texte or "")
    pz = ctx.pseudonymiseur(textes)
    fiches_ent = ctx.fiches(db, pseudonymiseur=pz)
    if kind == JOB_REDIGER:
        autres = [ax_titre(rangs.get(x.id, ""), x.intitule) for x in act if x.id != section.id]
        cible_ia = (rep.longueur_mots if rep is not None and rep.longueur_mots else None) or at.cible_mots(section, None)
        partie = at._partie_ia(dossier, section, rangs.get(section.id, ""), autres, ctx, chunks, dossier_acheteur,
                               cible_ia, passages_acheteur=at._passages_pour_ia(project, payload, section, entiers),
                               fiches=fiches_ent)
        partie["membre_groupement"] = {"nom": ctx.nom, "lot": ctx.lot}
    with pii_scope(pz), cost_meter("groupement : aide du partenaire", tenant) as cm:
        if kind == JOB_RACCOURCIR:
            r = moteur.raccourcir_partie(base.texte if base else "", int(cible or 0), titre=section.intitule,
                                         billing_id=tenant)
        else:
            r = moteur.rediger_partie(partie, billing_id=tenant)
    if r.get("erreur") or not (r.get("texte") or "").strip():
        raise LLMUnavailable("Service IA indisponible : partie non rédigée.")
    # Enregistrement (relu : la tâche a pu durer plusieurs minutes ; l'invitation a pu être retirée).
    db.expire_all()
    inv = db.get(ProjectInvite, invite_id)
    section = db.get(DossierSection, section_id)
    dossier = db.get(DossierPresentation, dossier.id)
    at._cumuler_cout(dossier, cm.summary())
    db.commit()
    if inv is None or not peut_rediger(db, inv)[0] or section is None or section.author_invite_id != invite_id \
            or section.retiree_at is not None:
        liberer_job(db, job_id)
        j = db.get(Job, job_id)
        return {"sections": [{"section_id": section_id, "ok": False}], "echecs": 1,
                "message": "Cette partie ne vous est plus confiée : le texte n'a pas été gardé.",
                "_debit": (j.result or {}).get("_debit") if j is not None and isinstance(j.result, dict) else None}
    texte = r["texte"]
    fiches_tout = fiches_ent + fs.fiches_extraits(chunks)
    if kind == JOB_RACCOURCIR:
        faits = fs.controler(texte, ctx.fiches_de_brouillon(db, base), acheteur=None,
                             noms_entreprise=ctx.noms_entreprise, section_entreprise=at.section_sur_l_entreprise(section),
                             mode="raccourci", anciens=(base.faits if base else []), base_texte=base.texte if base else "")
        sources = (base.sources or []) if base else []
        from app.services import rag
        refs = {f"S{n}" for n in rag.cited_refs(texte)} | {x for x in fs.refs_de(texte) if x.startswith("S")}
        sources = [x for x in sources if x.get("ref") in refs]
        origine = "raccourci"
    else:
        texte = fs.inserer_cv(texte, fiches_tout)
        faits = fs.controler(texte, fiches_tout, acheteur=acheteur, noms_entreprise=ctx.noms_entreprise,
                             section_entreprise=at.section_sur_l_entreprise(section), mode="ia",
                             anciens=(base.faits if base else []))
        sources = r.get("sources") or []
        origine = "ia"
    commun = _commune(db, section)
    b = _ajouter_brouillon(db, section, invite_id, texte=texte, origine=origine, ia=True, sources=sources, faits=faits,
                           coupe=bool(r.get("coupe")), base_id=base.id if base else None,
                           base_version_id=commun.id if commun else None, auteur_user_id=user_id if mode == "compte"
                           else None, job_id=job_id)
    rep = db.query(DossierRepartition).filter(DossierRepartition.section_id == section.id).first()
    if rep is not None and rep.job_id == job_id:
        rep.job_id = None
    db.commit()
    j = db.get(Job, job_id)
    debit = (j.result or {}).get("_debit") if j is not None and isinstance(j.result, dict) else None
    return {"sections": [{"section_id": section.id, "ok": True, "brouillon_id": b.id, "coupe": bool(r.get("coupe")),
                          "a_completer": len(me.placeholders(texte)), "faits_a_relire": far.non_traites(faits),
                          "extraits_fournis": len(chunks)}],
            "echecs": 0, "message": "", "_debit": debit}


def ax_titre(numero: str, intitule: str) -> str:
    from app.services import atelier_export as ax
    return ax.titre_section({"numero": numero, "intitule": intitule})


def tache(db, acces: Acces, job_id: int) -> dict:
    """La tâche d'un partenaire, lue avec SON accès seulement (sinon 404, comme une tâche inexistante) ; par le
    lien, avec la clé de son espace."""
    _exiger_espace(acces)
    j = db.query(Job).filter(Job.id == int(job_id), Job.portee == PORTEE_PARTENAIRE,
                             Job.invite_id == acces.invite_id, Job.kind.in_(JOB_KINDS)).first()
    if j is None:
        raise AtelierError(404, "tache_introuvable", "Cette tâche est introuvable.")
    return at.job_public(j)


def _tache_en_cours_out(db, rep: DossierRepartition) -> Optional[dict]:
    j = _job_en_cours(db, rep.job_id)
    if j is None:
        return None
    return {"job_id": j.id, "action": "rediger" if j.kind == JOB_REDIGER else "raccourcir", "statut": j.status}


# ── Le chef de file : répartir, demander, modifier une part ──────────────────────────

def activer(db, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, reproposer: bool = False,
            ip: str = "") -> dict:
    """Prépare « Qui écrit quoi » : une ligne par partie active, rédacteur pré-rempli SANS IA (lot ↔
    critère), longueur conseillée tirée de la limite de la partie. Idempotent ; `reproposer` refait la
    proposition des seules lignes jamais choisies à la main et encore sans texte."""
    cands = membres(db, project)
    reps = repartitions(db, dossier)
    if not reps and not any((m.get("role") or "cotraitant") == "cotraitant" for m in cands):
        # Un marché sans groupement : rien à répartir, l'atelier reste celui d'une seule entreprise.
        raise AtelierError(409, "pas_de_groupement", MSG_SANS_GROUPEMENT)
    crees, reproposees = 0, 0
    for s in at.sections_actives(db, dossier):
        if at.est_generee(s):
            continue                # tirée du groupement : personne ne la rédige
        r = reps.get(s.id)
        prop = proposition(s, cands)
        if r is None:
            r = DossierRepartition(dossier_id=dossier.id, section_id=s.id, project_id=project.id,
                                   owner_id=dossier.owner_id, redacteur=CHEF, choix="propose", proposition=prop,
                                   longueur_mots=at.cible_mots(s, None), relance_palier=0, aides_ia=0, lock_version=0)
            db.add(r)
            db.flush()
            crees += 1
            if prop["redacteur"] == PARTENAIRE and _sans_texte(db, s):
                _changer_auteur(db, s, r, PARTENAIRE, prop["invite_id"])
        elif reproposer and r.choix == "propose" and _sans_texte(db, s):
            r.proposition = prop
            flag_modified(r, "proposition")
            if (r.redacteur, r.invite_id) != (prop["redacteur"], prop["invite_id"]):
                _changer_auteur(db, s, r, prop["redacteur"], prop["invite_id"])
                reproposees += 1
    db.commit()
    _journal(db, action="redaction.repartition", project_id=project.id, owner_id=dossier.owner_id,
             actor=lecteur.email or f"user:{lecteur.user_id}", actor_kind="owner", target_type="dossier_presentation",
             target_id=dossier.id, ip=ip, detail="Répartition des parties préparée (proposition sans IA)",
             meta={"crees": crees, "reproposees": reproposees})
    _journal_confiees(db, project, dossier, lecteur, ip)
    apres_changement_commun(db, project, dossier, "répartition des parties", actor=lecteur.email or "",
                            actor_kind="owner", ip=ip)
    # Assemblage (chantier 3) : « Organisation du groupement » et « Qui fait quoi », tirées du groupement.
    from app.services import atelier_assemblage as asm
    gen = asm.assurer_generees(db, project, dossier)
    return {"crees": crees, "reproposees": reproposees, "parties_du_groupement": gen["crees"]}


def _journal_confiees(db, project, dossier, lecteur, ip) -> None:
    """Une entrée par partie confiée à un partenaire, une seule fois (son journal de membre)."""
    from app.models import AuditLog
    reps = repartitions(db, dossier)
    for s in at.sections_actives(db, dossier):
        r = reps.get(s.id)
        if r is None or r.redacteur != PARTENAIRE or not r.invite_id:
            continue
        deja = db.query(AuditLog.id).filter(AuditLog.project_id == project.id, AuditLog.invite_id == r.invite_id,
                                            AuditLog.action == "redaction.partie_confiee",
                                            AuditLog.target_id == s.id).first()
        if deja is None:
            _journal(db, action="redaction.partie_confiee", project_id=project.id, owner_id=dossier.owner_id,
                     actor=lecteur.email or f"user:{lecteur.user_id}", actor_kind="owner", invite_id=r.invite_id,
                     target_id=s.id, ip=ip, detail=f"Partie confiée : {_titre(dossier, s)}")


def _sans_texte(db, section: DossierSection) -> bool:
    """Aucun texte (ni version de l'atelier, ni brouillon de partenaire) : la changer de mains ne touche à rien."""
    if db.query(DossierSectionVersion.id).filter(DossierSectionVersion.section_id == section.id).first() is not None:
        return False
    return db.query(DossierPartBrouillon.id).filter(DossierPartBrouillon.section_id == section.id).first() is None


def _changer_auteur(db, section: DossierSection, rep: DossierRepartition, redacteur: str, invite_id) -> None:
    """La partie change de rédacteur : son texte courant et sa validation sont MIS DE CÔTÉ (l'historique
    reste entier) — jamais le brouillon privé du chef de file chez un partenaire, jamais le texte d'un
    partenaire comme texte du chef de file sans qu'il le reprenne lui-même. Le nouveau rédacteur part de zéro :
    rien ne lui a encore été demandé (« Demander les parts », relances) et l'aide de l'IA de la partie lui est
    entière (le plafond du dossier, lui, ne bouge pas)."""
    if (rep.redacteur, rep.invite_id) != (redacteur, invite_id if redacteur == PARTENAIRE else None):
        rep.demandee_le = None
        rep.relance_palier = 0
        rep.aides_ia = 0
    rep.redacteur = redacteur
    rep.invite_id = invite_id if redacteur == PARTENAIRE else None
    section.author_kind = at.AUTEUR_INVITATION if redacteur == PARTENAIRE else at.AUTEUR_ORG
    section.author_invite_id = invite_id if redacteur == PARTENAIRE else None
    section.current_version_id = None
    section.validated_version_id = None
    section.validated_hash = ""
    section.validated_at = None
    section.validated_by = None
    section.statut = at.A_ECRIRE
    section.lock_version = (section.lock_version or 0) + 1
    rep.lock_version = (rep.lock_version or 0) + 1


def repartir(db, project: Project, dossier: DossierPresentation, section: DossierSection, lecteur: at.Lecteur, *,
             redacteur=BASE_DEFAUT, invite_id=BASE_DEFAUT, longueur_mots=BASE_DEFAUT, date_limite=BASE_DEFAUT,
             confirmer: bool = False, lock_version=None, ip: str = "") -> DossierRepartition:
    """Le chef de file choisit qui rédige la partie, sa longueur conseillée et sa date limite interne.
    Confier une partie qui a déjà du texte demande `confirmer` : ce texte est mis de côté (il reste dans
    l'historique). Une partie en cours de rédaction par l'IA ne change pas de mains. Une partie tirée du
    groupement n'a pas de rédacteur."""
    if at.est_generee(section):
        raise AtelierError(409, "partie_du_groupement", at.MSG_PARTIE_GROUPEMENT)
    if section.retiree_at is not None:
        raise AtelierError(409, "partie_retiree", "Cette partie a été retirée du plan : remettez-la d'abord.")
    reps = repartitions(db, dossier)
    rep = reps.get(section.id)
    if rep is None:
        rep = DossierRepartition(dossier_id=dossier.id, section_id=section.id, project_id=project.id,
                                 owner_id=dossier.owner_id, redacteur=(PARTENAIRE if section.author_kind ==
                                                                        at.AUTEUR_INVITATION else CHEF),
                                 invite_id=section.author_invite_id, choix="manuel",
                                 proposition=proposition(section, membres(db, project)),
                                 longueur_mots=at.cible_mots(section, None), relance_palier=0, aides_ia=0,
                                 lock_version=0)
        db.add(rep)
        db.flush()
    rep = _verrouiller_rep(db, rep)
    if lock_version is not None and int(lock_version) != int(rep.lock_version or 0):
        raise AtelierError(409, "repartition_modifiee", "La répartition de cette partie a changé entre-temps : rechargez-la.",
                           lock_version=rep.lock_version)
    section = at._verrouiller(db, section)
    avant = (rep.redacteur, rep.invite_id)
    changements = {}
    if redacteur is not BASE_DEFAUT or invite_id is not BASE_DEFAUT:
        red = redacteur if redacteur is not BASE_DEFAUT else rep.redacteur
        iid = invite_id if invite_id is not BASE_DEFAUT else rep.invite_id
        if red not in REDACTEURS:
            raise AtelierError(422, "redacteur_invalide", "Choisissez le chef de file ou un partenaire du groupement.")
        if red == PARTENAIRE:
            inv = db.get(ProjectInvite, int(iid or 0)) if iid else None
            if inv is None or inv.project_id != project.id:
                raise AtelierError(404, "partenaire_introuvable", "Partenaire introuvable sur ce marché.")
            ok, raison = peut_rediger(db, inv)
            if not ok:
                raise AtelierError(409, "partenaire_indisponible", f"Ce partenaire ne peut pas rédiger : {raison}.")
            iid = inv.id
        else:
            iid = None
        if (red, iid) != avant:
            if _job_en_cours(db, rep.job_id) is not None or _job_en_cours(db, section.job_id) is not None:
                raise AtelierError(409, "redaction_en_cours", "Cette partie est en cours de rédaction : réessayez dans "
                                                              "quelques minutes.")
            if not _sans_texte(db, section) and not confirmer:
                raise AtelierError(409, "changement_a_confirmer",
                                   "Cette partie a déjà du texte. La confier à quelqu'un d'autre met ce texte de côté (il "
                                   "reste dans l'historique) : confirmez pour continuer.")
            _changer_auteur(db, section, rep, red, iid)
            rep.choix = "manuel"
            changements["redacteur"] = {"avant": avant[0], "apres": red}
    if longueur_mots is not BASE_DEFAUT:
        if longueur_mots in (None, "", 0):
            rep.longueur_mots = None
        else:
            v = int(longueur_mots)
            if not 30 <= v <= 20000:
                raise AtelierError(422, "longueur_invalide", "Indiquez une longueur entre 30 et 20 000 mots.")
            rep.longueur_mots = v
        changements["longueur_mots"] = rep.longueur_mots
    if date_limite is not BASE_DEFAUT:
        if date_limite in (None, ""):
            rep.date_limite = None
        else:
            try:
                d = date_limite if isinstance(date_limite, date) else date.fromisoformat(str(date_limite)[:10])
            except ValueError:
                raise AtelierError(422, "date_invalide", "Date limite illisible.")
            rep.date_limite = d
            rep.relance_palier = 0
        changements["date_limite"] = _jour(rep.date_limite)
    rep.lock_version = (rep.lock_version or 0) + 1
    db.commit()
    titre = _titre(dossier, section)
    acteur = lecteur.email or f"user:{lecteur.user_id}"
    if "redacteur" in changements:
        if avant[0] == PARTENAIRE and avant[1]:
            _journal(db, action="redaction.partie_reprise", project_id=project.id, owner_id=dossier.owner_id,
                     actor=acteur, actor_kind="owner", invite_id=avant[1], target_id=section.id, ip=ip,
                     detail=f"Partie confiée à un autre rédacteur : {titre}")
        if rep.redacteur == PARTENAIRE and rep.invite_id:
            _journal(db, action="redaction.partie_confiee", project_id=project.id, owner_id=dossier.owner_id,
                     actor=acteur, actor_kind="owner", invite_id=rep.invite_id, target_id=section.id, ip=ip,
                     detail=f"Partie confiée : {titre}")
        apres_changement_commun(db, project, dossier, f"rédacteur de « {titre} » changé", actor=acteur,
                                actor_kind="owner", ip=ip)
    if changements:
        _journal(db, action="redaction.repartition", project_id=project.id, owner_id=dossier.owner_id, actor=acteur,
                 actor_kind="owner", invite_id=rep.invite_id if rep.redacteur == PARTENAIRE else None,
                 target_id=section.id, ip=ip, detail=f"Répartition modifiée : {titre}", meta=changements)
    db.refresh(rep)
    return rep


def modifier_part(db, project: Project, dossier: DossierPresentation, section: DossierSection, user: User,
                  texte: str, base_version_id, ip: str = "") -> DossierSection:
    """Le chef de file MODIFIE la part d'un partenaire, ou l'ÉCRIT à la place d'un partenaire absent : un
    nouveau texte commun (« écrit par le chef de file »), aucune IA, qui passe « à revalider par » le
    partenaire (avant et après côte à côte). Aucune source du chef de file n'appuie un fait sur le
    partenaire : tout fait sur lui reste à relire jusqu'à ce que LUI le valide sur ses propres faits."""
    if at.est_generee(section):
        raise AtelierError(409, "partie_du_groupement", at.MSG_PARTIE_GROUPEMENT)
    reps = repartitions(db, dossier)
    rep = reps.get(section.id)
    if rep is None or rep.redacteur != PARTENAIRE or section.author_kind != at.AUTEUR_INVITATION:
        raise AtelierError(409, "pas_une_part_de_partenaire", "Cette partie est la vôtre : écrivez-la dans l'atelier.")
    if section.retiree_at is not None:
        raise AtelierError(409, "partie_retiree", "Cette partie a été retirée du plan : remettez-la d'abord.")
    section = at._verrouiller(db, section)
    cur = _commune(db, section)
    base = int(base_version_id) if base_version_id not in (None, "", 0) else None
    if (cur.id if cur else None) != base:
        raise AtelierError(409, "texte_modifie_entre_temps", "Le texte de cette partie a changé depuis que vous l'avez "
                                                             "ouvert : rechargez-le (votre saisie n'a pas été perdue de "
                                                             "votre écran).",
                           version_courante_id=cur.id if cur else None)
    t = at.normaliser_texte(texte)
    if not t:
        raise AtelierError(422, "partie_vide", "Écrivez un texte.")
    if len(t) > TEXTE_MAX:
        raise AtelierError(422, "texte_trop_long", f"Une partie compte au plus {TEXTE_MAX} caractères.")
    if cur is not None and cur.empreinte == at.empreinte(t):
        return section
    inv = db.get(ProjectInvite, section.author_invite_id)
    nom = nom_partenaire(inv, _contribution(db, section.author_invite_id))
    from app.services.preuves import membres as membres_org
    acheteur = at.acheteur_du_marche(db, project, membres_org(db, dossier.owner_id))
    faits = fs.controler(t, [], acheteur=acheteur, noms_entreprise=[nom], section_entreprise=at.section_sur_l_entreprise(section),
                         mode="ia", anciens=(cur.faits if cur else []))
    ia = at.ia_a_servi(t, [v.texte or "" for v in _versions_communes_de(db, section) if v.ia])
    redigee = _avant(db, section, cur) is not None or (cur is not None and cur.ecrit_par == ECRIT_PAR_PARTENAIRE)
    at.ajouter_version(db, section, texte=t, origine=at.UTILISATEUR, ia=ia, sources=[], faits=faits_communs(faits),
                       base_version_id=cur.id if cur else None, auteur_user_id=user.id, partage=True,
                       ecrit_par=ECRIT_PAR_CHEF, compteurs=None)
    db.commit()
    titre = _titre(dossier, section)
    action = "redaction.part_modifiee" if redigee else "redaction.part_redigee_par_chef"
    _journal(db, action=action, project_id=project.id, owner_id=dossier.owner_id, actor=user.email or f"user:{user.id}",
             actor_kind="owner", invite_id=section.author_invite_id, target_id=section.id, ip=ip,
             detail=(f"Partie modifiée par le chef de file, à revalider : {titre}" if redigee else
                     f"Partie rédigée par le chef de file, à valider : {titre}"))
    apres_changement_commun(db, project, dossier, f"partie « {titre} » modifiée par le chef de file",
                            actor=user.email or "", actor_kind="owner", ip=ip)
    _notifier_partenaire(db, project, inv, titre, redigee)
    db.refresh(section)
    return section


def _notifier_partenaire(db, project: Project, inv: Optional[ProjectInvite], titre: str, modifiee: bool) -> None:
    try:
        from app.routers.invites import _invite_is_demo, _is_email, _notify_allowed, _send_mails_async
        if inv is None or not _is_email(inv.recipient) or _invite_is_demo(inv, db):
            return
        if not _notify_allowed(("redaction_modif", inv.id)):
            return
        from app.core.config import get_settings
        base = (get_settings().APP_BASE_URL or "").rstrip("/")
        quoi = "a modifié votre partie" if modifiee else "a rédigé à votre place la partie"
        _send_mails_async([(inv.recipient, f"Votre partie est à valider — {project.name[:60]}",
                            f"Bonjour,\n\nLe chef de file {quoi} « {titre} » du dossier de présentation du marché "
                            f"« {project.name} ». Relisez-la : vous pouvez la valider ou rétablir votre version.\n\n"
                            f"Votre lien Adjugo :\n{base}/invite/{inv.token}\n\n— Adjugo")])
    except Exception:       # noqa: BLE001
        pass


def comparer(db, section: DossierSection) -> dict:
    """L'avant (le dernier texte du partenaire) et l'après (le texte courant) d'une partie de partenaire :
    deux textes COMMUNS, jamais un brouillon."""
    cur = _commune(db, section)
    av = _avant(db, section, cur) if cur is not None and cur.ecrit_par == ECRIT_PAR_CHEF else None
    return {"avant": _version_commune_out(av), "apres": _version_commune_out(cur)}


def _a_faire(db, section: DossierSection, rep: DossierRepartition) -> str:
    """Ce qu'on attend du partenaire sur cette partie, pour l'email de « Demander les parts »."""
    if statut_de(db, section, rep) != A_REVALIDER:
        return ""
    cur = _commune(db, section)
    if cur is not None and cur.ecrit_par == ECRIT_PAR_CHEF:
        return " : texte du chef de file, à relire et valider"
    return " : à revalider"


def demander_parts(db, project: Project, dossier: DossierPresentation, user: User, invite_ids=None, ip: str = "") -> dict:
    """« Demander les parts » : un email à chaque partenaire qui a des parties à rédiger, en cours ou à
    revalider, avec leur liste et la date limite interne. Mêmes garde-fous d'envoi que les relances de la
    co-traitance (routeur : démo refusée, adresse du chef de file confirmée) : anti-rafale de 15 min par
    partenaire (un email PARTI seulement), même plafond quotidien que les invitations et leurs renvois
    (`invites._daily_invite_count`, une entrée de journal par partenaire sollicité), jamais d'email pour la
    démonstration ni sans adresse. Chaque demande partie est inscrite au journal chaîné (journal du membre :
    « partie demandée »)."""
    from app.core.config import get_settings
    from app.routers.invites import DAILY_INVITE_CAP, _daily_invite_count, _invite_is_demo, _is_email
    from app.services import email as _email
    base = (get_settings().APP_BASE_URL or "").rstrip("/")
    now = utcnow()
    voulues = set(int(x) for x in invite_ids) if invite_ids else None
    reps = repartitions(db, dossier)
    par_invite = {}
    for s in at.sections_actives(db, dossier):
        r = reps.get(s.id)
        if r is None or r.redacteur != PARTENAIRE or not r.invite_id:
            continue
        if voulues is not None and r.invite_id not in voulues:
            continue
        if statut_de(db, s, r) in (A_REDIGER, EN_COURS, A_REVALIDER):
            par_invite.setdefault(r.invite_id, []).append((s, r))
    demandees, sans_adresse, recentes, plafond = [], [], [], []
    chef = db.query(Company).filter(Company.user_id == dossier.owner_id).first()
    de = f"{chef.name}" if chef and chef.name else "Le chef de file"
    for iid, lignes in par_invite.items():
        inv = db.get(ProjectInvite, iid)
        nom = nom_partenaire(inv, _contribution(db, iid))
        if inv is None or not peut_rediger(db, inv)[0]:
            continue
        if not _is_email(inv.recipient) or _invite_is_demo(inv, db):
            sans_adresse.append({"invite_id": iid, "nom": nom})
            continue
        last = max((r.demandee_le for _s, r in lignes if r.demandee_le), default=None)
        if last is not None:
            last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last < DEMANDE_INTERVALLE:
                recentes.append({"invite_id": iid, "nom": nom})
                continue
        if _daily_invite_count(user, db) >= DAILY_INVITE_CAP:
            db.rollback()                   # libère le verrou de l'organisation pris pour compter
            plafond.append({"invite_id": iid, "nom": nom})
            continue
        liste = "\n".join(f"- « {_titre(dossier, s)} »" + _a_faire(db, s, r)
                          + (f" (date limite interne : {r.date_limite.strftime('%d/%m/%Y')})" if r.date_limite else "")
                          for s, r in lignes)
        sent = _email.send_email(inv.recipient, f"Votre partie du dossier de présentation — {project.name[:60]}",
                                 f"Bonjour,\n\n{de} attend votre partie du dossier de présentation du "
                                 f"marché « {project.name} » :\n{liste}\n\nÉcrivez-la vous-même ou avec l'aide d'Adjugo, "
                                 f"depuis votre lien :\n{base}/invite/{inv.token}\n\nVos documents et vos brouillons "
                                 f"restent privés : seul le texte que vous envoyez est lu par le groupement.\n\n— Adjugo")
        if sent:
            # L'anti-rafale ne compte qu'un email PARTI : un envoi échoué se retente aussitôt (comme le
            # renvoi d'une invitation, qui n'horodate que l'envoi réussi). La demande vaut relance du palier en
            # cours (J-2, jour J) : la relance planifiée ne repart pas juste après.
            jour = datetime.now(timezone.utc).date()
            for _s, r in lignes:
                r.demandee_le = now
                r.relance_palier = max(int(r.relance_palier or 0), _palier(r.date_limite, jour))
        db.commit()
        if sent:
            _journal(db, action="redaction.parts_demandees", project_id=project.id, owner_id=dossier.owner_id,
                     actor=user.email or f"user:{user.id}", actor_kind="owner", invite_id=iid,
                     target_type="dossier_presentation", target_id=dossier.id, ip=ip,
                     detail=f"Parties demandées : {len(lignes)}", meta={"email": True, "parties": len(lignes)})
        demandees.append({"invite_id": iid, "nom": nom, "parties": len(lignes), "email_parti": bool(sent)})
    return {"demandees": demandees, "sans_adresse": sans_adresse, "deja_demandees": recentes,
            "plafond_atteint": plafond}


def _palier(date_limite: Optional[date], today: date) -> int:
    """Palier de relance d'une partie à ce jour : 1 = J-2, 2 = jour J (0 avant J-2 ou sans date limite)."""
    if not isinstance(date_limite, date):
        return 0
    jours = (date_limite - today).days
    return 2 if jours <= 0 else (1 if jours <= 2 else 0)


def parts_a_relancer(db, today: Optional[date] = None) -> dict:
    """{invite_id: [(partie, répartition, palier, marché)]} des parties à relancer ce jour : pas encore envoyées, à
    J-2 puis le jour de leur date limite interne, un palier par partie, jamais deux fois ; jamais une partie
    demandée le jour même (« Demander les parts » vient d'écrire) ; rien après le dépôt ou la clôture du marché.
    Lecture seule : la relance de la co-traitance y ajoute ces parties à SON rappel (un seul email)."""
    today = today or datetime.now(timezone.utc).date()
    rows = (db.query(DossierRepartition).filter(DossierRepartition.redacteur == PARTENAIRE,
                                                DossierRepartition.invite_id.isnot(None),
                                                DossierRepartition.date_limite.isnot(None),
                                                DossierRepartition.relance_palier < 2).all())
    groupes = {}
    for r in rows:
        jours = (r.date_limite - today).days
        cible = _palier(r.date_limite, today)
        if jours < 0 or cible <= (r.relance_palier or 0):
            continue
        if r.demandee_le is not None and r.demandee_le.date() >= today:
            continue
        s = db.get(DossierSection, r.section_id)
        p = db.get(Project, r.project_id)
        st = getattr(p, "status", None)
        st = st.value if hasattr(st, "value") else str(st or "")
        if s is None or s.retiree_at is not None or p is None or p.deleted_at is not None \
                or st in ("envoye", "gagne", "perdu", "abandonne"):
            continue
        if statut_de(db, s, r) not in (A_REDIGER, EN_COURS):
            continue
        groupes.setdefault(r.invite_id, []).append((s, r, cible, p))
    return groupes


def liste_relance(lignes: list) -> str:
    return "\n".join(f"- « {at._flat(s.intitule)[:160]} » (date limite interne : {r.date_limite.strftime('%d/%m/%Y')})"
                     for s, r, _c, _p in lignes)


def relancer_parts(db, today: Optional[date] = None, deja=()) -> dict:
    """Relance planifiée (appelée par la relance de la co-traitance, POST /api/admin/run-cotraitance-reminders) :
    un email par partenaire dont une partie n'est pas encore envoyée, à J-2 puis le jour de sa date limite
    interne ; un palier par partie (relance_palier : 1 = J-2, 2 = jour J), jamais deux fois ; rien après le
    dépôt ou la clôture du marché, rien pour la démonstration. `deja` : les partenaires dont le rappel de la
    co-traitance de cette tournée portait déjà la liste de leurs parties (jamais deux emails)."""
    from app.core.config import get_settings
    from app.routers.invites import _invite_is_demo, _is_email
    from app.services import email as _email
    base = (get_settings().APP_BASE_URL or "").rstrip("/")
    relances = 0
    for iid, lignes in parts_a_relancer(db, today).items():
        if iid in set(deja or ()):
            continue
        inv = db.get(ProjectInvite, iid)
        if inv is None or not peut_rediger(db, inv)[0] or not _is_email(inv.recipient) or _invite_is_demo(inv, db):
            continue
        p = lignes[0][3]
        if _email.send_email(inv.recipient, f"Rappel — votre partie du dossier de présentation ({p.name[:50]})",
                             f"Bonjour,\n\nIl reste à envoyer votre partie du dossier de présentation du marché "
                             f"« {p.name} » :\n{liste_relance(lignes)}\n\nVotre lien Adjugo :\n{base}/invite/{inv.token}"
                             f"\n\n— Adjugo"):
            for _s, r, c, _p in lignes:
                r.relance_palier = c
            relances += 1
    db.commit()
    return {"parts_relancees": relances}


# ── Vues ─────────────────────────────────────────────────────────────────────────────

def _section_base_out(dossier: DossierPresentation, s: DossierSection, rang: str) -> dict:
    """Ce que tout membre peut lire d'une partie : ce que l'acheteur note, avec la phrase du règlement."""
    return {"section_id": s.id, "numero_affiche": rang, "titre": ax_titre(rang, s.intitule), "intitule": s.intitule,
            "critere": s.critere or "", "poids": s.poids or "", "poids_source": (s.poids_source or "") if s.poids else "",
            "question": s.question or "", "source_plan": s.source_plan, "limite": s.limite or [],
            "partie_de_critere": bool(s.partie_de_critere)}


def vue_chef(db, project: Project, dossier: DossierPresentation) -> dict:
    """« Qui écrit quoi » côté chef de file : pour chaque partie, son rédacteur (et la proposition sans IA),
    sa longueur conseillée, sa date limite interne, son statut, la mention « rédigé par le chef de file, à
    valider par X », le texte commun (identifiant, empreinte, compteurs : jamais une source) ; puis
    l'empreinte du dossier assemblé, les validations des membres et « Prêt à déposer »."""
    rafraichir_validations(db, project, dossier)
    cands = membres(db, project)
    noms = {m["invite_id"]: m["nom"] for m in cands}
    reps = repartitions(db, dossier)
    act = at.sections_actives(db, dossier)
    rangs = at._rangs(dossier, act)
    com = textes_communs(db, act)
    sections = []
    from app.services import atelier_assemblage as asm
    for s in act:
        if at.est_generee(s):
            sections.append(asm.ligne_chef(db, project, dossier, s, rangs.get(s.id, "")))
            continue
        r = reps.get(s.id)
        prop = (r.proposition if r is not None and isinstance(r.proposition, dict) else None) or proposition(s, cands)
        red = (r.redacteur if r is not None else (PARTENAIRE if s.author_kind == at.AUTEUR_INVITATION else CHEF))
        iid = (r.invite_id if r is not None else s.author_invite_id) if red == PARTENAIRE else None
        nom = noms.get(iid) or (nom_partenaire(db.get(ProjectInvite, iid), _contribution(db, iid)) if iid else "")
        st = statut_de(db, s, r)
        cur = _commune(db, s) if s.author_kind == at.AUTEUR_INVITATION else None
        envoyees = [v for v in _versions_communes_de(db, s) if v.ecrit_par == ECRIT_PAR_PARTENAIRE] \
            if s.author_kind == at.AUTEUR_INVITATION else []
        out = dict(_section_base_out(dossier, s, rangs.get(s.id, "")),
                   enregistre=r is not None,
                   redacteur={"type": red, "invite_id": iid, "nom": nom if red == PARTENAIRE else "Chef de file"},
                   proposition=prop, choix=(r.choix if r is not None else "propose"),
                   longueur_mots=(r.longueur_mots if r is not None else at.cible_mots(s, None)),
                   date_limite=_jour(r.date_limite) if r is not None else None,
                   demandee_le=_iso(r.demandee_le) if r is not None else None,
                   statut=st, statut_libelle=STATUTS[st], mention=mention(db, s, nom),
                   envoyee_le=_iso(envoyees[0].created_at) if envoyees else None,
                   validation=({"version_id": s.validated_version_id, "empreinte": s.validated_hash,
                                "le": _iso(s.validated_at)} if s.validated_version_id else None),
                   texte_commun=_version_commune_out(cur if cur is not None else com.get(s.id), texte=False),
                   lock_version=(r.lock_version if r is not None else 0))
        sections.append(out)
    return {"actif": bool(reps), "membres": cands, "sections": sections,
            "dossier": {"empreinte": empreinte_dossier(db, dossier, act), "validations": validations_out(db, dossier),
                        "pret": pret(db, project, dossier, act)},
            "statuts": STATUTS, "avertissement_envoi": AVERTISSEMENT_ENVOI, "plafond_aide_par_partie": plafond_partie(),
            # « Harmoniser le ton » (assemblage) : proposé seulement s'il y a des parts de membres différents à relier.
            "harmoniser": {"message": asm.MSG_HARMONISER,
                           "jonctions": len(asm.jonctions(db, dossier)) if reps else 0}}


def detail_chef(db, project: Project, dossier: DossierPresentation, section: DossierSection) -> dict:
    """Une partie, côté chef de file : sa ligne de « Qui écrit quoi », son texte commun en entier et, si le
    chef de file l'a modifiée, l'avant et l'après côte à côte. Jamais un brouillon ni une source. Une partie
    tirée du groupement : son texte, d'où il vient, ses validations et (« Qui fait quoi ») la note interne."""
    if at.est_generee(section):
        from app.services import atelier_assemblage as asm
        rafraichir_validations(db, project, dossier)
        act = at.sections_actives(db, dossier)
        if section.id not in {s.id for s in act}:
            raise AtelierError(404, "partie_introuvable", "Partie introuvable.")
        rang = at._rangs(dossier, act).get(section.id, "")
        return dict(asm.ligne_chef(db, project, dossier, section, rang),
                    **asm.detail(db, project, dossier, section, pour="chef"))
    vue = vue_chef(db, project, dossier)
    ligne = next((x for x in vue["sections"] if x["section_id"] == section.id), None)
    if ligne is None:
        raise AtelierError(404, "partie_introuvable", "Partie introuvable.")
    cur = _commune(db, section) if section.author_kind == at.AUTEUR_INVITATION else None
    return dict(ligne, texte_commun=_version_commune_out(cur), comparaison=comparer(db, section) if cur else None)


def dossier_assemble(db, project: Project, dossier: DossierPresentation, pour_invite_id: Optional[int] = None,
                     pour_chef: bool = False) -> dict:
    """Le DOSSIER ASSEMBLÉ, en lecture, tel que le lit chaque membre (décision 3a) : l'ordre du cadre de
    l'acheteur, chaque partie avec son rédacteur, son statut et son texte commun (le texte envoyé par un
    partenaire ; le texte validé du chef de file) — jamais un brouillon, une source, un extrait, ni rien du
    forfait, du quota ou des dérogations du chef de file."""
    rafraichir_validations(db, project, dossier)
    act = at.sections_actives(db, dossier)
    rangs = at._rangs(dossier, act)
    com = textes_communs(db, act)
    noms = at._noms_auteurs(db, act)
    chef = db.query(Company).filter(Company.user_id == dossier.owner_id).first()
    nom_chef = (chef.name if chef and chef.name else "") or "Chef de file"
    parties = []
    from app.services import atelier_assemblage as asm
    for s in act:
        v = com.get(s.id)
        if at.est_generee(s):
            parties.append(asm.partie_assemblee(db, project, dossier, s, _section_base_out(dossier, s, rangs.get(s.id, "")),
                                                v, pour_invite_id=pour_invite_id))
            continue
        part = s.author_kind == at.AUTEUR_INVITATION
        st = statut_de(db, s)
        item = dict(_section_base_out(dossier, s, rangs.get(s.id, "")),
                    redacteur={"type": PARTENAIRE if part else CHEF,
                               "nom": (noms.get(s.author_invite_id) or "Un partenaire") if part else nom_chef,
                               "vous": bool(part and pour_invite_id and s.author_invite_id == pour_invite_id)},
                    statut=st, statut_libelle=STATUTS[st], texte=(v.texte if v is not None else None),
                    a_completer=len(me.placeholders(v.texte or "")) if v is not None else 0)
        if part and v is not None and bool(v.partage):
            item["faits_a_relire"] = far.non_traites(v.faits or [])
            item["compteurs"] = v.compteurs if isinstance(v.compteurs, dict) else None
            item["ecrit_par"] = v.ecrit_par or ""
        parties.append(item)
    out = {"marche": {"id": project.id, "nom": project.name}, "chef_de_file": nom_chef, "message": MSG_LECTURE,
           "empreinte": empreinte_dossier(db, dossier, act), "parties": parties,
           "validations": validations_out(db, dossier), "pret": pret(db, project, dossier, act)}
    if pour_chef:
        # La justification du groupement (décision 09-D-18) : au chef de file SEUL, jamais exportée.
        out["note_interne"] = asm.note_interne(db, project)
        out["harmoniser"] = {"message": asm.MSG_HARMONISER, "jonctions": len(asm.jonctions(db, dossier))}
    return out


POIDS_LIBELLES = {"reglement": "écrit dans le règlement", "utilisateur": "lu dans le règlement par le chef de file"}


def note_acheteur(project: Project, section: DossierSection) -> dict:
    """Ce que l'acheteur note pour une partie, comme la carte « Comment vous serez noté » (chantier du
    partenaire) : le critère, son poids TEL QU'ÉCRIT et d'où il vient, la phrase du règlement RETROUVÉE dans le
    dossier (celle de la grille, jamais reformulée) et la question du cadre de réponse. Sans IA ; rien de plus
    que la grille que le partenaire lit déjà."""
    from app.services import atelier_plan as ap
    phrase = ""
    try:
        lignes = ap.lignes_techniques(at._analysis(project))
    except Exception:       # noqa: BLE001 — grille illisible : la partie garde son critère et sa question
        lignes = []
    if section.critere_id:
        ln = next((x for x in lignes if x.get("id") == section.critere_id), None)
        phrase = at._flat((ln or {}).get("phrase"))
    question = at._flat(section.question)
    if not phrase and section.source_plan == ap.GRILLE:
        phrase = question                         # partie tirée d'un critère : sa question EST la phrase
    if question == phrase:
        question = ""
    poids = section.poids or ""
    src = (section.poids_source or "") if poids else ""
    # Partie sans critère (plan tiré du cadre de réponse) : les critères techniques de la grille, tels
    # qu'écrits (le mémoire est jugé sur eux), sans prétendre les rattacher à cette partie.
    grille = []
    if not section.critere:
        for ln in lignes[:6]:
            p = at._flat(ln.get("poids"))
            s = (ln.get("poids_source") or "") if p else ""
            grille.append({"critere": at._flat(ln.get("critere"))[:200], "poids": p[:40], "poids_source": s,
                           "poids_libelle": POIDS_LIBELLES.get(s, ""),
                           "phrase": at._flat(ln.get("phrase"))[:ap.QUESTION_MAX]})
    return {"critere": section.critere or "", "poids": poids, "poids_source": src,
            "poids_libelle": POIDS_LIBELLES.get(src, ""), "phrase": phrase[:ap.QUESTION_MAX],
            "question": question[:ap.QUESTION_MAX], "source_plan": section.source_plan or "",
            "grille": [g for g in grille if g["critere"]]}


MSG_MODE_SIMPLE = ("Mode simple : le paragraphe de votre part (« Paragraphe pour le dossier de présentation ») reste "
                   "disponible, tel que vous l'avez écrit. Vous pouvez partir de ce texte pour rédiger une partie.")
MSG_IDENTITE = ("Avant d'envoyer ou de valider, un code à 6 chiffres vous sera envoyé par email pour confirmer votre "
                "identité.")


def resume_partenaire(db, inv: ProjectInvite) -> Optional[dict]:
    """Pour « Partagé avec moi » : combien de parties sont confiées à ce partenaire et combien attendent quelque
    chose de lui (à rédiger, en cours, à revalider). Statuts seulement ; None si le dossier n'est pas préparé."""
    try:
        from app.routers.invites import _network_pending
        if (inv.role or "cotraitant") != "cotraitant" or not inv.project_id or _network_pending(inv, db):
            return None             # sous-traitant, ou invitation du réseau pas encore acceptée (aperçu limité)
        project = db.get(Project, inv.project_id)
        d = dossier_du_marche(db, project, inv.owner_id) if project is not None else None
        if d is None or not repartition_active(db, d):
            return None
        reps = (db.query(DossierRepartition).filter(DossierRepartition.dossier_id == d.id,
                                                    DossierRepartition.redacteur == PARTENAIRE,
                                                    DossierRepartition.invite_id == inv.id).all())
        n, a_faire, a_revalider, a_valider = 0, 0, 0, 0
        for r in reps:
            s = db.get(DossierSection, r.section_id)
            if s is None or s.retiree_at is not None or s.author_invite_id != inv.id:
                continue
            n += 1
            st = statut_de(db, s, r)
            a_faire += st in (A_REDIGER, EN_COURS)
            a_revalider += st == A_REVALIDER
            a_valider += st == ENVOYEE          # envoyée : le chef de file attend encore sa validation
        return ({"parties": n, "a_faire": a_faire, "a_revalider": a_revalider, "a_valider": a_valider}
                if n else None)
    except Exception:       # noqa: BLE001 — la liste « Partagé avec moi » ne casse jamais pour ce résumé
        return None


def vue_partenaire(db, acces: Acces) -> dict:
    """Ce que voit un partenaire : SES parties (ce que l'acheteur note, la longueur conseillée, la date limite
    interne, son brouillon PRIVÉ avec ses sources, le texte commun, l'avant et l'après d'une modification du
    chef de file, l'aide de l'IA restante) et l'état du dossier assemblé. Jamais la partie, le brouillon ni
    la source d'un autre membre ; jamais rien du forfait du chef de file."""
    rafraichir_validations(db, acces.project, acces.dossier)
    act = at.sections_actives(db, acces.dossier)
    rangs = at._rangs(acces.dossier, act)
    cap = plafond_partie()
    parties = []
    for s, r in parties_de(db, acces):
        b = brouillon_courant(db, s.id, acces.invite_id)
        cur = _commune(db, s)
        st = statut_de(db, s, r)
        nom = nom_partenaire(acces.inv, _contribution(db, acces.invite_id))
        parties.append(dict(_section_base_out(acces.dossier, s, rangs.get(s.id, "")),
                            note=note_acheteur(acces.project, s),
                            longueur_mots=r.longueur_mots, date_limite=_jour(r.date_limite),
                            statut=st, statut_libelle=STATUTS[st], mention=mention(db, s, nom),
                            brouillon=_brouillon_out(b, acces) if acces.cle_ok else None,
                            texte_commun=_version_commune_out(cur),
                            comparaison=comparer(db, s) if cur is not None and cur.ecrit_par == ECRIT_PAR_CHEF else None,
                            validation=({"version_id": s.validated_version_id, "empreinte": s.validated_hash,
                                         "le": _iso(s.validated_at)} if s.validated_version_id else None),
                            aide={"utilisees": int(r.aides_ia or 0), "plafond": cap,
                                  "restantes": max(0, cap - int(r.aides_ia or 0)),
                                  "en_cours": _tache_en_cours_out(db, r) if acces.cle_ok else None}))
    ma = _validation_de(db, acces.dossier, f"invitation:{acces.invite_id}")
    emp = empreinte_dossier(db, acces.dossier, act)
    # Assemblage : « Qui fait quoi dans le groupement », que chaque membre valide aussi.
    from app.services import atelier_assemblage as asm
    qfq = asm.qfq_de(db, acces.dossier)
    qfq_bloc = asm.detail(db, acces.project, acces.dossier, qfq, pour="partenaire",
                          invite_id=acces.invite_id) if qfq is not None else None
    qfq_ok = qfq_bloc is None or ((qfq_bloc.get("ma_validation") or {}).get("statut") == "valide")
    from app.routers.invites import _binding_required
    compte = acces.mode == "lien" and par_le_compte(acces.inv)
    espace = {"cle_valide": bool(acces.cle_ok), "ouvert": bool(getattr(acces.inv, "espace_hash", "")),
              "entete": ENTETE_CLE,
              "code_possible": bool(_binding_required(acces.inv)) if acces.mode == "lien" and not compte else False,
              # Lien rattaché à un compte : aucun espace par le lien, le compte suffit (« Partagé avec moi »).
              "par_le_compte": compte,
              "message": "" if acces.cle_ok else (MSG_ESPACE_COMPTE if compte else MSG_CLE_REQUISE)}
    contrib = _contribution(db, acces.invite_id)
    ctx = ContextePartenaire(db, acces)
    try:
        _exiger_identite(acces)
        a_prouver = False
    except AtelierError:
        a_prouver = True
    return {"marche": {"id": acces.project.id, "nom": acces.project.name},
            "mode": acces.mode, "espace": espace, "message_mode": MSG_MODE_COMPTE if ctx.avec_compte else MSG_MODE_LIEN,
            "avertissement_envoi": AVERTISSEMENT_ENVOI, "peut_ecrire": bool(getattr(acces.inv, "can_contribute", True)),
            # SA part (nom et lot déclarés par lui) : rien d'un autre membre.
            "membre": {"nom": ctx.nom, "lot": ctx.lot},
            # Envoyer et valider engagent l'entreprise : un code reçu par email d'abord, quand le lien vise
            # une adresse pas encore prouvée (l'écran le dit avant d'envoyer).
            "identite": {"a_prouver": a_prouver, "message": MSG_IDENTITE if a_prouver else ""},
            # Le petit texte de sa part (mode simple) : le sien, déjà lu tel quel par le chef de file.
            "mode_simple": {"petit_texte": ((contrib.memoire_paragraph if contrib is not None else "") or "")[:TEXTE_MAX],
                            "message": MSG_MODE_SIMPLE},
            "parties": parties, "statuts": STATUTS, "origines": ORIGINES, "qui_fait_quoi": qfq_bloc,
            "dossier": {"empreinte": emp, "ma_validation": _validation_out(ma, emp),
                        # Un co-traitant à qui aucune partie n'est confiée valide aussi le dossier assemblé (après
                        # « Qui fait quoi »), comme le serveur l'attend pour « Prêt à déposer ».
                        "peut_valider": all(p["statut"] == VALIDEE for p in parties) and qfq_ok,
                        "pret": pret(db, acces.project, acces.dossier, act)}}


def detail_partenaire(db, acces: Acces, section_id: int) -> dict:
    """Une partie du partenaire, avec l'historique de SES brouillons (sans leurs textes) ; ou « Qui fait quoi
    dans le groupement », qu'il valide aussi."""
    from app.services import atelier_assemblage as asm
    qfq = asm.qfq_de(db, acces.dossier)
    if qfq is not None and qfq.id == int(section_id):
        rafraichir_validations(db, acces.project, acces.dossier)
        return asm.detail(db, acces.project, acces.dossier, qfq, pour="partenaire", invite_id=acces.invite_id)
    vue = vue_partenaire(db, acces)
    ligne = next((x for x in vue["parties"] if x["section_id"] == int(section_id)), None)
    if ligne is None:
        raise AtelierError(404, "partie_introuvable", "Partie introuvable.")
    ligne["brouillons"] = ([x for x in (_brouillon_out(b, acces, texte=False)
                                        for b in brouillons(db, int(section_id), acces.invite_id)) if x is not None]
                           if acces.cle_ok else [])
    return ligne


def brouillon_du_partenaire(db, acces: Acces, section_id: int, brouillon_id: int) -> dict:
    """Un de SES brouillons précédents, avec son texte (« Reprendre ce texte ») : aucune génération n'écrase un
    texte sans en garder une version qu'on peut reprendre (doctrine § 7, règle 8). Matière privée : lue avec SON
    accès seulement (par le lien, avec la clé de son espace) ; le brouillon d'une autre partie ou d'un autre
    membre n'existe pas pour lui (404)."""
    _exiger_espace(acces)
    section, _rep = _partie(db, acces, section_id)
    try:
        bid = int(brouillon_id)
    except (TypeError, ValueError):
        bid = 0
    b = (db.query(DossierPartBrouillon).filter(DossierPartBrouillon.id == bid,
                                               DossierPartBrouillon.section_id == section.id,
                                               DossierPartBrouillon.invite_id == acces.invite_id).first())
    out = _brouillon_out(b, acces) if b is not None else None
    if out is None:
        raise AtelierError(404, "brouillon_introuvable", "Brouillon introuvable.")
    return out


# ── Validation du dossier assemblé (même mécanisme que la convention périmée) ────────

def _validation_de(db, dossier: DossierPresentation, cle: str) -> Optional[DossierValidation]:
    return db.query(DossierValidation).filter(DossierValidation.dossier_id == dossier.id,
                                              DossierValidation.membre_cle == cle).first()


def _validation_out(v: Optional[DossierValidation], empreinte_now: str) -> Optional[dict]:
    if v is None:
        return None
    valide = v.statut == "valide" and v.empreinte == empreinte_now
    return {"statut": "valide" if valide else "a_revalider", "statut_libelle": "Validé" if valide else "À revalider",
            "empreinte": v.empreinte, "le": _iso(v.valide_le), "perime_le": _iso(v.perime_le)}


def validations_out(db, dossier: DossierPresentation) -> list:
    emp = empreinte_dossier(db, dossier)
    noms = {}
    out = []
    for v in db.query(DossierValidation).filter(DossierValidation.dossier_id == dossier.id).order_by(DossierValidation.id):
        if str(v.membre_cle or "").startswith("qfq:"):
            continue                # validation de « Qui fait quoi » (assemblage), pas du dossier assemblé
        if v.invite_id and v.invite_id not in noms:
            noms[v.invite_id] = nom_partenaire(db.get(ProjectInvite, v.invite_id), _contribution(db, v.invite_id))
        out.append(dict(_validation_out(v, emp), membre=v.membre,
                        nom=(noms.get(v.invite_id) if v.invite_id else "Chef de file"), invite_id=v.invite_id))
    return out


def perimer_validations(db, project: Project, dossier: DossierPresentation, raison: str, *, actor: str = "system",
                        actor_kind: str = "system", ip: str = "", invite_id=None) -> int:
    """Le dossier assemblé a changé : toute validation d'un membre sur une AUTRE empreinte repasse « à
    revalider » (journalisé, visible de tous les membres). Idempotent. Ne lève jamais."""
    try:
        emp = empreinte_dossier(db, dossier)
        rows = db.query(DossierValidation).filter(DossierValidation.dossier_id == dossier.id,
                                                  DossierValidation.statut == "valide",
                                                  ~DossierValidation.membre_cle.like("qfq:%"),
                                                  DossierValidation.empreinte != emp).all()
        if not rows:
            return 0
        now = utcnow()
        for v in rows:
            v.statut = "a_revalider"
            v.perime_le = now
        db.commit()
        _journal(db, action="redaction.dossier_a_revalider", project_id=project.id, owner_id=dossier.owner_id,
                 actor=actor or "system", actor_kind=actor_kind or "system", invite_id=invite_id,
                 target_type="dossier_presentation", target_id=dossier.id, ip=ip,
                 detail=f"Dossier assemblé modifié ({raison}) : à revalider"[:255], meta={"validations": len(rows)})
        return len(rows)
    except Exception as e:      # noqa: BLE001
        logger.warning("groupement : péremption des validations impossible (dossier %s) : %s",
                       getattr(dossier, "id", "?"), type(e).__name__)
        try:
            db.rollback()
        except Exception:       # noqa: BLE001
            pass
        return 0


def apres_changement_commun(db, project: Project, dossier, raison: str, *, actor: str = "system",
                            actor_kind: str = "system", ip: str = "", invite_id=None) -> int:
    """À appeler après tout changement d'un texte commun (envoi, modification du chef de file, rétablissement,
    validation d'une partie du chef de file, changement de rédacteur, retrait d'un partenaire)."""
    if not isinstance(dossier, DossierPresentation):
        dossier = db.get(DossierPresentation, int(dossier or 0))
    if dossier is None or not repartition_active(db, dossier):
        return 0
    return perimer_validations(db, project, dossier, raison, actor=actor, actor_kind=actor_kind, ip=ip,
                               invite_id=invite_id)


def rafraichir_validations(db, project: Project, dossier: DossierPresentation) -> None:
    """Filet de sécurité à la lecture (comme la convention) : une validation dont l'empreinte ne correspond
    plus au dossier assemblé passe « à revalider », avec trace. Avant : les parties tirées du groupement
    suivent la convention et les parts des membres (assemblage)."""
    try:
        from app.services import atelier_assemblage as asm
        asm.rafraichir_generees(db, project, dossier)
    except Exception as e:      # noqa: BLE001 — au pire, le texte de la dernière lecture
        db.rollback()
        logger.warning("groupement : parties tirées du groupement non rafraîchies (dossier %s) : %s",
                       getattr(dossier, "id", "?"), type(e).__name__)
    perimer_validations(db, project, dossier, "le dossier assemblé a changé depuis la validation")


def valider_dossier(db, project: Project, dossier: DossierPresentation, *, membre: str, invite_id=None, user_id=None,
                    empreinte_vue: Optional[str] = None, actor: str = "", actor_kind: str = "owner",
                    ip: str = "") -> dict:
    """Un membre (chef de file compris) VALIDE le dossier assemblé qu'il a lu, sur SON empreinte, après
    avoir validé chacune de ses parties (et « Qui fait quoi dans le groupement » ; le chef de file aussi
    « Organisation du groupement »). Toute modification ensuite le fait repasser « à revalider »."""
    from app.services import atelier_assemblage as asm
    rafraichir_validations(db, project, dossier)
    act = at.sections_actives(db, dossier)
    emp = empreinte_dossier(db, dossier, act)
    if empreinte_vue and empreinte_vue != emp:
        raise AtelierError(409, "dossier_modifie", "Le dossier assemblé a changé depuis que vous l'avez lu : relisez-le "
                                                   "avant de le valider.", empreinte=emp)
    if membre == PARTENAIRE:
        miennes = [s for s in act if s.author_kind == at.AUTEUR_INVITATION and s.author_invite_id == invite_id]
    else:
        miennes = [s for s in act if s.author_kind == at.AUTEUR_ORG or (at.est_generee(s) and s.source_plan == asm.ORGA)]
    rest = [{"section_id": s.id, "titre": at._flat(s.intitule)[:160]} for s in miennes if statut_de(db, s) != VALIDEE]
    qfq = next((s for s in act if at.est_generee(s) and s.source_plan == asm.QFQ), None)
    cle_qfq = f"invitation:{int(invite_id)}" if membre == PARTENAIRE else CHEF
    if qfq is not None and not asm.a_valide_qfq(db, project, dossier, cle_qfq):
        rest.append({"section_id": qfq.id, "titre": at._flat(qfq.intitule)[:160]})
    if rest:
        raise AtelierError(409, "parties_a_valider", f"Validez d'abord vos parties ({len(rest)} restante"
                                                     f"{'s' if len(rest) > 1 else ''}).", sections=rest)
    cle = f"invitation:{int(invite_id)}" if membre == PARTENAIRE else CHEF
    v = _validation_de(db, dossier, cle)
    if v is None:
        v = DossierValidation(dossier_id=dossier.id, project_id=project.id, owner_id=dossier.owner_id, membre=membre,
                              membre_cle=cle, invite_id=invite_id if membre == PARTENAIRE else None)
        db.add(v)
    v.empreinte, v.statut, v.valide_le, v.perime_le, v.user_id = emp, "valide", utcnow(), None, user_id
    db.commit()
    _journal(db, action="redaction.dossier_valide", project_id=project.id, owner_id=dossier.owner_id,
             actor=actor, actor_kind=actor_kind, invite_id=invite_id if membre == PARTENAIRE else None,
             target_type="dossier_presentation", target_id=dossier.id, ip=ip,
             detail="Dossier assemblé validé", meta={"empreinte": emp})
    return _validation_out(v, emp)


def pret(db, project: Project, dossier: DossierPresentation, sections: Optional[list] = None) -> dict:
    """« Prêt à déposer » : « Sections validées 4 sur 5 », la validation du dossier assemblé par chaque
    membre (chef de file + partenaires qui peuvent rédiger) et la liste de ce qui manque (« manques » :
    qui doit rédiger, valider ou revalider quoi)."""
    act = sections if sections is not None else at.sections_actives(db, dossier)
    n = len(act)
    statuts = {s.id: statut_de(db, s) for s in act}
    k = sum(1 for s in act if statuts[s.id] == VALIDEE)
    emp = empreinte_dossier(db, dossier, act)
    vals = {v.membre_cle: v for v in db.query(DossierValidation).filter(DossierValidation.dossier_id == dossier.id)
            if not str(v.membre_cle or "").startswith("qfq:")}
    attendus = [("chef_de_file", None, "Chef de file")] + [
        (f"invitation:{m['invite_id']}", m["invite_id"], m["nom"]) for m in membres(db, project) if m["peut_rediger"]]
    mem = []
    for cle, iid, nom in attendus:
        v = vals.get(cle)
        st = "a_faire" if v is None else ("valide" if v.statut == "valide" and v.empreinte == emp else "a_revalider")
        mem.append({"membre": PARTENAIRE if iid else CHEF, "invite_id": iid, "nom": nom, "statut": st})
    manques = _manques(db, project, dossier, act, statuts, mem)
    return {"sections_validees": k, "sections_total": n, "message": f"Sections validées {k} sur {n}",
            "membres": mem, "manques": manques,
            "complet": bool(n) and k == n and all(m["statut"] == "valide" for m in mem)}


_VERBES = {A_REDIGER: "à rédiger par", EN_COURS: "en cours chez", ENVOYEE: "à valider par",
           A_REVALIDER: "à revalider par", A_VALIDER: "à valider par"}


def _manques(db, project: Project, dossier: DossierPresentation, act: list, statuts: dict, mem: list) -> list:
    """Ce qui manque pour « Prêt à déposer », partie par partie puis membre par membre : « « 3. Démarche
    environnementale » : à valider par Breizh Désamiantage ». Jamais ce qui manque au chef de file comme
    entreprise (capacités, qualifications) : seulement les gestes de rédaction et de validation."""
    from app.services import atelier_assemblage as asm
    rangs = at._rangs(dossier, act)
    noms = {m["invite_id"]: m["nom"] for m in membres(db, project)}
    out = []
    for s in act:
        st = statuts.get(s.id) or statut_de(db, s)
        if st == VALIDEE:
            continue
        if at.est_generee(s):
            if s.source_plan == asm.QFQ:
                qui = [("le chef de file" if x["invite_id"] is None else x["nom"])
                       for x in asm.qfq_validations(db, project, dossier, s) if x["statut"] != "valide"]
            else:
                qui = ["le chef de file"]
            verbe = _VERBES.get(st, "à valider par")
        elif s.author_kind == at.AUTEUR_INVITATION:
            qui = [noms.get(s.author_invite_id) or nom_partenaire(db.get(ProjectInvite, s.author_invite_id))]
            verbe = _VERBES.get(st, "à valider par")
        else:
            qui = ["le chef de file"]
            verbe = "à rédiger par" if st == A_REDIGER else ("à revalider par" if st == A_REVALIDER else "à valider par")
        titre = ax_titre(rangs.get(s.id, ""), s.intitule)
        if not qui:
            continue
        out.append({"section_id": s.id, "titre": titre, "statut": st, "statut_libelle": STATUTS.get(st, ""),
                    "qui": qui, "message": f"« {titre} » : {verbe} {' et '.join(qui) if len(qui) <= 2 else ', '.join(qui)}"})
    for m in mem:
        if m["statut"] == "valide":
            continue
        qui = "le chef de file" if m["membre"] == CHEF else m["nom"]
        verbe = "à revalider par" if m["statut"] == "a_revalider" else "à valider par"
        out.append({"section_id": None, "titre": "Dossier assemblé", "statut": m["statut"],
                    "statut_libelle": "À revalider" if m["statut"] == "a_revalider" else "À valider",
                    "qui": [qui], "message": f"Dossier assemblé : {verbe} {qui}"})
    return out


# ── RGPD : effacement, retrait d'une invitation, export, purge ───────────────────────

def effacer_dossiers(db, dossier_ids: list) -> None:
    """Effacement des dossiers (compte du chef de file, corbeille) : validations, brouillons des partenaires
    et répartition partent AVEC le dossier, ainsi que les tâches des partenaires de ces marchés."""
    from sqlalchemy import or_
    if not dossier_ids:
        return
    pids = [r[0] for r in db.query(DossierPresentation.project_id).filter(DossierPresentation.id.in_(dossier_ids))]
    # Rattachées par dossier_id OU par partie (section_id), quelles que soient leurs autres colonnes.
    sids = [r[0] for r in db.query(DossierSection.id).filter(DossierSection.dossier_id.in_(dossier_ids))]
    db.query(DossierValidation).filter(DossierValidation.dossier_id.in_(dossier_ids)).delete(synchronize_session=False)
    db.query(DossierPartBrouillon).filter(or_(DossierPartBrouillon.dossier_id.in_(dossier_ids),
                                              DossierPartBrouillon.section_id.in_(sids or [-1]))).delete(
        synchronize_session=False)
    db.query(DossierRepartition).filter(or_(DossierRepartition.dossier_id.in_(dossier_ids),
                                            DossierRepartition.section_id.in_(sids or [-1]))).delete(
        synchronize_session=False)
    if pids:
        iids = [r[0] for r in db.query(ProjectInvite.id).filter(ProjectInvite.project_id.in_(pids))]
        if iids:
            db.query(Job).filter(Job.portee == PORTEE_PARTENAIRE, Job.invite_id.in_(iids)).delete(
                synchronize_session=False)


def retirer_invitation(db, inv: ProjectInvite, raison: str, *, actor: str = "", actor_kind: str = "owner",
                       ip: str = "") -> int:
    """Invitation RETIRÉE par le chef de file ou DÉCLINÉE par le partenaire : l'accès est déjà coupé (les
    routes refusent une invitation inactive) ; ses brouillons privés sont EFFACÉS (personne d'autre ne peut
    les lire, ils n'ont plus d'usage) ; ses parties reviennent au chef de file, à rédiger — le texte qu'il
    avait envoyé n'y reste pas, il demeure seulement dans l'historique de la partie ; sa validation du
    dossier assemblé et ses tâches terminées sont effacées. Renvoie le nombre de parties reprises."""
    try:
        reps = db.query(DossierRepartition).filter(DossierRepartition.invite_id == inv.id).all()
        n = 0
        dossiers = set()
        for r in reps:
            s = db.get(DossierSection, r.section_id)
            if s is not None:
                _changer_auteur(db, s, r, CHEF, None)
            r.choix = "manuel"
            r.job_id = None
            n += 1
            dossiers.add(r.dossier_id)
        db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == inv.id).delete(synchronize_session=False)
        db.query(DossierValidation).filter(DossierValidation.invite_id == inv.id).delete(synchronize_session=False)
        db.query(Job).filter(Job.portee == PORTEE_PARTENAIRE, Job.invite_id == inv.id,
                             Job.status.in_(["done", "error"])).delete(synchronize_session=False)
        db.commit()
        project = db.get(Project, inv.project_id)
        for did in dossiers:
            d = db.get(DossierPresentation, did)
            if d is None or project is None:
                continue
            _journal(db, action="redaction.parts_reprises", project_id=project.id, owner_id=d.owner_id,
                     actor=actor or "system", actor_kind=actor_kind, invite_id=inv.id,
                     target_type="dossier_presentation", target_id=d.id, ip=ip,
                     detail=f"{n} partie{'s' if n > 1 else ''} reprise{'s' if n > 1 else ''} par le chef de file ({raison})")
            apres_changement_commun(db, project, d, f"partenaire {raison}", actor=actor or "system",
                                    actor_kind=actor_kind, ip=ip)
        return n
    except Exception as e:      # noqa: BLE001 — l'accès est coupé par ailleurs ; la purge rattrape
        logger.warning("groupement : retrait de l'invitation %s incomplet : %s", getattr(inv, "id", "?"),
                       type(e).__name__)
        db.rollback()
        return 0


def effacer_compte(db, uid: int) -> int:
    """Effacement du compte d'un PARTENAIRE : les brouillons écrits depuis ce compte (qui citent ses preuves
    et son savoir-faire) sont effacés avec lui ; le texte qu'il a ENVOYÉ reste dans le dossier du chef de
    file (c'est la part commune de l'offre, reçue par le groupement). Renvoie le nombre de brouillons effacés."""
    if not uid:
        return 0
    return db.query(DossierPartBrouillon).filter(DossierPartBrouillon.auteur_user_id == uid).delete(
        synchronize_session=False)


def exporter_chef(db, owner_id: int) -> list:
    """Export RGPD du chef de file : la répartition et les validations de ses dossiers (le texte commun des
    parties est déjà dans l'export des dossiers de présentation). Jamais un brouillon de partenaire."""
    out = []
    for d in db.query(DossierPresentation).filter(DossierPresentation.owner_id == owner_id).all():
        reps = repartitions(db, d)
        if not reps:
            continue
        lignes = []
        for s in at.sections_actives(db, d):
            r = reps.get(s.id)
            if r is None:
                continue
            lignes.append({"partie": s.intitule, "redacteur": r.redacteur, "invite_id": r.invite_id,
                           "longueur_mots": r.longueur_mots, "date_limite": _jour(r.date_limite),
                           "demandee_le": _iso(r.demandee_le), "statut": statut_de(db, s, r)})
        from app.services import atelier_assemblage as asm
        p = db.get(Project, d.project_id)
        out.append({"dossier_id": d.id, "project_id": d.project_id, "repartition": lignes,
                    "validations": validations_out(db, d),
                    "validations_qui_fait_quoi": asm.qfq_validations(db, p, d) if p is not None and asm.qfq_de(db, d)
                    else []})
    return out


def exporter_invitation(db, inv: ProjectInvite, sources_du_compte: bool = True, acces: Optional["Acces"] = None,
                        compte: Optional[User] = None) -> dict:
    """Portabilité pour un partenaire : SES brouillons (texte, sources, faits) et les textes qu'il a envoyés.
    Par le lien (`sources_du_compte` faux), un brouillon écrit depuis le compte (ses preuves, son savoir-faire)
    n'est pas rendu : il ne se lit que depuis ce compte. Avec `acces` (compte) ou `compte` (export RGPD du compte),
    seuls les extraits et les preuves de l'organisation actuelle du compte (`_matiere_du_compte`)."""
    bro = []
    for b in (db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == inv.id)
              .order_by(DossierPartBrouillon.id).all()):
        if not sources_du_compte and b.auteur_user_id:
            continue
        sources, faits = list(b.sources or []), list(b.faits or [])
        if acces is not None or compte is not None:
            sources, faits_src = (_matiere_visible(acces, b) if acces is not None
                                  else _matiere_du_compte(db, compte, b))
            faits = [x for x in faits if not (isinstance(x, dict) and x.get("statut") == fs.AVEC_SOURCE)
                     or x in faits_src]
        bro.append({"section_id": b.section_id, "numero": b.numero, "origine": b.origine, "texte": b.texte or "",
                    "sources": sources, "faits": faits, "compteurs": b.compteurs, "cree_le": _iso(b.created_at)})
    env = [{"section_id": v.section_id, "numero": v.numero, "texte": v.texte or "", "envoye_le": _iso(v.created_at)}
           for v in db.query(DossierSectionVersion).filter(DossierSectionVersion.project_id == inv.project_id,
                                                           DossierSectionVersion.partage.is_(True),
                                                           DossierSectionVersion.ecrit_par == ECRIT_PAR_PARTENAIRE,
                                                           DossierSectionVersion.author_invite_id == inv.id)
           .order_by(DossierSectionVersion.id).all()]
    return {"project_id": inv.project_id, "brouillons": bro, "textes_envoyes": env}


def exporter_partenaire(db, uid: int) -> list:
    """Export RGPD d'un compte PARTENAIRE : ses brouillons et ses textes envoyés, pour chaque lien qu'il a
    rattaché (et les brouillons écrits depuis ce compte)."""
    iids = {r[0] for r in db.query(ProjectInvite.id).filter(ProjectInvite.accepted_by_user_id == uid)}
    iids |= {r[0] for r in db.query(DossierPartBrouillon.invite_id).filter(DossierPartBrouillon.auteur_user_id == uid)}
    out = []
    compte = db.get(User, uid)
    for iid in sorted(iids):
        inv = db.get(ProjectInvite, iid)
        if inv is not None:
            # Comme la route d'export de la partie : un membre retiré de l'organisation du partenaire n'y retrouve ni
            # les extraits, ni les documents, ni les preuves de son ancienne organisation (contre-relecture).
            out.append(exporter_invitation(db, inv, compte=compte))
    return out


def purger(db, jours: int = PURGE_JOURS) -> dict:
    """Purge quotidienne (POST /api/admin/run-trash-purge) : brouillons des invitations retirées ou déclinées
    (filet), ou expirées depuis plus de `jours` jours ; tâches terminées des partenaires de plus de `jours`
    jours."""
    from sqlalchemy import or_
    limite = utcnow() - timedelta(days=int(jours))
    morts = [r[0] for r in db.query(ProjectInvite.id).filter(or_(
        ProjectInvite.revoked.is_(True), ProjectInvite.declined_at.isnot(None),
        (ProjectInvite.expires_at.isnot(None)) & (ProjectInvite.expires_at < limite)))]
    n = 0
    if morts:
        n = db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id.in_(morts)).delete(
            synchronize_session=False)
    t = db.query(Job).filter(Job.portee == PORTEE_PARTENAIRE, Job.status.in_(["done", "error"]),
                             Job.created_at < limite).delete(synchronize_session=False)
    db.commit()
    return {"brouillons_partenaires_effaces": int(n or 0), "taches_partenaires_effacees": int(t or 0)}


# ── Assemblage (chantier 3 : app/services/atelier_assemblage.py, derrière ce module) ──

def lancer_harmonisation(db, user: User, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur,
                         member_ids: list, accepte_debit: bool = False) -> Job:
    """« Harmoniser le ton » (chef de file) : des phrases de transition, rien d'autre (docs § 17.1, point 5)."""
    from app.services import atelier_assemblage as asm
    return asm.lancer_harmonisation(db, user, project, dossier, lecteur, member_ids, accepte_debit=accepte_debit)


def valider_generee_par_le_chef(db, project: Project, section: DossierSection, lecteur: at.Lecteur, version_id,
                                ip: str = "") -> DossierSection:
    """Le chef de file valide une partie tirée du groupement depuis l'atelier (docs § 17.1, points 2 à 4)."""
    from app.services import atelier_assemblage as asm
    return asm.valider_par_le_chef(db, project, section, lecteur, version_id, ip=ip)
