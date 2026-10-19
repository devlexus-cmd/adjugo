"""
L'ASSEMBLAGE du dossier de groupement (rédaction, vague 4, chantier 3 — étude § 6.8 B, parcours 4 et 5).

Contrat : docs/REDACTION_V4_GROUPEMENT.md § 17. Ce module n'est appelé QUE par
app/services/atelier_groupement.py (et par l'atelier pour ses deux crochets : la validation d'une partie
tirée du groupement, et le rafraîchissement avant toute lecture du texte commun) : il reste derrière le
seul point d'entrée du dossier de groupement.

1. Assemblage SANS IA, dans l'ordre du cadre de l'acheteur (le plan de l'atelier). Deux parties en plus,
   TIRÉES DU GROUPEMENT (dossier_sections.author_kind = 'groupement'), écrites par Adjugo sans IA, jamais
   à la main :
     • « Organisation du groupement » : forme, chef de file (et ses pouvoirs), répartition des parts —
       tirée de la convention EN VIGUEUR (générée et à jour). Pas de convention, ou convention périmée :
       on le dit (« [À compléter : …] », qui bloque l'export) au lieu d'inventer. Aucun prix : le dossier
       de présentation n'est pas l'offre de prix ;
     • « Qui fait quoi dans le groupement » : la complémentarité des membres (part, qualifications,
       moyens), tirée de ce que chacun a DÉCLARÉ ou JUSTIFIÉ — le libellé « justifiée » / « déclarée » de
       chaque qualification est rendu à l'écran, jamais écrit dans le fichier de l'acheteur. Elle ne liste
       JAMAIS ce qui manque au chef de file (ni à personne) : seulement ce que chacun apporte. La
       justification du groupement (décision 09-D-18 de l'Autorité de la concurrence : pourquoi répondre à
       plusieurs) reste une NOTE INTERNE au chef de file, jamais exportée, jamais montrée aux partenaires.
   Elles se placent en tête du dossier (après la partie du plan qui parle du groupement, s'il y en a une) ;
   le chef de file peut les retirer ou les remettre. Leur texte suit les faits à chaque lecture (convention
   régénérée, part d'un membre modifiée) : une partie validée puis changée repasse « à revalider ».
2. Validation : « Organisation » est validée par le chef de file (une fois la convention validée par tous
   les membres) ; « Qui fait quoi » par CHAQUE membre (chef de file et partenaires qui rédigent), sur son
   empreinte (dossier_validations, membre_cle « qfq:… »). Tout est inscrit au journal chaîné.
3. « Harmoniser le ton » (option, IA) : l'IA écrit seulement une phrase de transition au début des parties
   qui suivent la part d'un AUTRE membre. Le texte d'un membre n'est jamais réécrit : la phrase est ajoutée
   devant, en paragraphe séparé (une transition d'une harmonisation précédente est remplacée, jamais
   empilée). Toute phrase qui apporte un fait absent du dossier avant l'harmonisation (nombre, date,
   certification, nom propre, matériel, quantité, engagement…) est refusée automatiquement, sans IA (le
   repérage des faits du contrôle A). Une partie touchée repasse « à revalider » par son auteur (avant et
   après côte à côte, rétablissement possible). Débit : une refonte du dossier (décision 6a), rendue si
   l'IA tombe ou si aucune phrase n'est retenue ; noms des salariés masqués, aucun CV envoyé à l'IA.
"""
import logging
import re
from datetime import date
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified

from app.models import (Company, ContributionPiece, DossierPresentation, DossierSection, DossierSectionVersion,
                        DossierValidation, Job, Project, ProjectInvite, User, utcnow)
from app.services import atelier as at
from app.services import atelier_groupement as ag
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from app.services import memoire_export as me

logger = logging.getLogger("adjugo")

AtelierError = at.AtelierError

ORGA, QFQ = at.GEN_ORGANISATION, at.GEN_QUI_FAIT_QUOI
GENEREES = (ORGA, QFQ)
INTITULES = {ORGA: "Organisation du groupement", QFQ: "Qui fait quoi dans le groupement"}
PREFIXE_QFQ = "qfq:"            # dossier_validations.membre_cle d'une validation de « Qui fait quoi »
A_VALIDER = "a_valider"
JOB_HARMONISER = at.JOB_HARMONISER

MSG_ORGA = ("Cette partie reprend la convention de groupement : la forme, le chef de file et la répartition. Elle "
            "se met à jour toute seule, sans IA.")
MSG_QFQ = ("Cette partie montre ce que chaque membre apporte : sa part, ses qualifications, ses moyens. Chaque membre "
           "la valide. Les mentions « justifiée » et « déclarée » restent à l'écran : elles ne partent pas chez "
           "l'acheteur.")
MSG_NOTE_INTERNE = ("Note interne, jamais exportée ni montrée aux partenaires : pourquoi répondre en groupement, utile "
                    "si l'acheteur ou un concurrent pose la question.")
MSG_ORGA_EN_ATTENTE = ("La convention attend encore l'accord de : {noms}. Cette partie se valide une fois la "
                       "convention validée par tous les membres.")
LIB_JUSTIFIEE, LIB_DECLAREE = "justifiée", "déclarée"


def _val(v, n: int = 200) -> str:
    """Valeur insérée dans un texte tiré du groupement : une ligne, sans caractère qui changerait le texte
    (Markdown, renvois entre crochets, tableaux)."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(v if v is not None else ""))
    s = re.sub(r"[\[\]*_`#|<>]", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:n]


# ── Les parties tirées du groupement : où elles sont, où elles vont ──────────────────

def generees(db, dossier: DossierPresentation, actives: bool = True) -> dict:
    """{ORGA|QFQ: partie} du dossier (la première de chaque genre)."""
    q = db.query(DossierSection).filter(DossierSection.dossier_id == dossier.id,
                                        DossierSection.author_kind == at.AUTEUR_GROUPEMENT)
    if actives:
        q = q.filter(DossierSection.retiree_at.is_(None))
    out = {}
    for s in q.order_by(DossierSection.id.asc()).all():
        out.setdefault(s.source_plan, s)
    return out


def qfq_de(db, dossier: Optional[DossierPresentation]) -> Optional[DossierSection]:
    return generees(db, dossier).get(QFQ) if dossier is not None else None


def _ancre(autres: list) -> int:
    """Rang où placer les parties tirées du groupement : juste après la partie du plan qui parle du
    groupement (« Présentation du groupement »…), sinon en tête du dossier."""
    for i, s in enumerate(autres):
        if "groupement" in far.fold(s.intitule or ""):
            return i + 1
    return 0


def placer_generees(db, dossier: DossierPresentation) -> None:
    """Remet les parties tirées du groupement à leur place, l'ordre du cadre de l'acheteur restant intact
    pour toutes les autres."""
    act = at.sections_actives(db, dossier)
    gen = sorted([s for s in act if at.est_generee(s)],
                 key=lambda s: GENEREES.index(s.source_plan) if s.source_plan in GENEREES else 9)
    if not gen:
        return
    autres = [s for s in act if not at.est_generee(s)]
    k = _ancre(autres)
    change = False
    for i, s in enumerate(autres[:k] + gen + autres[k:]):
        if s.ordre != i:
            s.ordre = i
            change = True
    if change:
        db.commit()


def assurer_generees(db, project: Project, dossier: DossierPresentation) -> dict:
    """Crée les deux parties tirées du groupement si elles n'ont JAMAIS existé (une partie retirée par le
    chef de file n'est jamais recréée), à leur place, puis écrit leur texte. Idempotent."""
    toutes = generees(db, dossier, actives=False)
    n_act = len(at.sections_actives(db, dossier))
    crees = 0
    for kind in GENEREES:
        if kind in toutes or n_act + crees >= at.SECTIONS_MAX:
            continue
        db.add(DossierSection(dossier_id=dossier.id, project_id=dossier.project_id, owner_id=dossier.owner_id,
                              ordre=n_act + crees, numero="", intitule=INTITULES[kind], niveau=1, parents=[],
                              question="", source_plan=kind, critere="", critere_id="", poids="", poids_source="",
                              partie_de_critere=False, lot="", limite=[], author_kind=at.AUTEUR_GROUPEMENT,
                              author_invite_id=None, statut=at.A_ECRIRE, lock_version=0))
        crees += 1
    if crees:
        db.commit()
        placer_generees(db, dossier)
    rafraichir_generees(db, project, dossier)
    return {"crees": crees}


def rafraichir_generees(db, project: Project, dossier: DossierPresentation) -> int:
    """Le texte des parties tirées du groupement suit les faits (convention, parts des membres) : une
    nouvelle version quand il change (l'historique reste entier), « à revalider » si elle était validée.
    Sans IA. Renvoie le nombre de parties mises à jour."""
    secs = generees(db, dossier)
    if not secs:
        return 0
    n = 0
    for kind, s in secs.items():
        if kind == ORGA:
            texte, _info = organisation(db, project, dossier)
        elif kind == QFQ:
            texte, _info = qui_fait_quoi(db, project, dossier)
        else:
            continue
        if _ecrire(db, project, dossier, s, texte):
            n += 1
    if n:
        ag.apres_changement_commun(db, project, dossier, "partie tirée du groupement mise à jour")
    if ORGA in secs:
        synchroniser_orga(db, secs[ORGA])
    if QFQ in secs:
        synchroniser_qfq(db, project, dossier, secs[QFQ])
    return n


def _ecrire(db, project: Project, dossier: DossierPresentation, section: DossierSection, texte: str) -> bool:
    t = at.normaliser_texte(texte)
    emp = at.empreinte(t)
    cur = at.version_courante(db, section)
    if cur is not None and cur.empreinte == emp:
        return False                # le cas courant : rien à écrire, aucun verrou pris
    section = at._verrouiller(db, section)      # deux lectures simultanées n'écrivent qu'une version
    cur = at.version_courante(db, section)
    if cur is not None and cur.empreinte == emp:
        db.commit()                 # écrite entre-temps par une autre lecture : le verrou est rendu
        return False
    premiere = cur is None
    v = at.ajouter_version(db, section, texte=t, origine=at.GENERE, ia=False, sources=[], faits=[],
                           base_version_id=cur.id if cur else None, auteur_user_id=None, partage=True,
                           ecrit_par=at.GENERE, compteurs=None)
    db.commit()
    if not premiere:
        ag._journal(db, action="redaction.partie_groupement_a_jour", project_id=project.id,
                    owner_id=dossier.owner_id, actor="system", actor_kind="system", target_id=section.id,
                    detail=f"Partie mise à jour d'après le groupement : {section.intitule}",
                    meta={"partie": section.source_plan, "version": v.numero, "empreinte": v.empreinte})
    return True


# ── « Organisation du groupement » : tirée de la convention en vigueur ───────────────

def _convention(db, project: Project):
    from app.services import groupement_convention as gc
    conv = gc.get_convention(db, project.id)
    if conv is not None:
        try:
            gc.refresh(db, project, conv)     # filet : une convention qui ne correspond plus aux faits est périmée
        except Exception as e:      # noqa: BLE001
            logger.warning("assemblage : fraîcheur de la convention non contrôlée (projet %s) : %s", project.id,
                           type(e).__name__)
    return conv


def _accords_en_attente(db, conv) -> list:
    from app.services import groupement_convention as gc
    return [s.company_name or "un membre" for s in gc.signatures_of(db, conv) if s.status not in ("signed", "hors_ligne")]


def convention_info(db, project: Project, conv=None) -> dict:
    from app.services import groupement_convention as gc
    conv = conv if conv is not None else _convention(db, project)
    statut = conv.status if conv is not None else "aucune"
    out = {"statut": statut, "libelle": gc.STATUS_LABELS.get(statut, ""), "version": (conv.version if conv else None),
           "toutes_validees": statut == "signee", "en_vigueur": statut in gc.ACTIVE, "accords_en_attente": []}
    if conv is not None and statut == "a_signer":
        out["accords_en_attente"] = _accords_en_attente(db, conv)
    return out


def organisation(db, project: Project, dossier: DossierPresentation) -> tuple:
    """(texte, info). Le texte est tiré de la convention EN VIGUEUR (générée, à jour) : forme, chef de file et
    ses pouvoirs, répartition des parts (sans aucun prix). Sinon il le dit, sans rien inventer."""
    from app.services import groupement_convention as gc
    conv = _convention(db, project)
    info = {"convention": convention_info(db, project, conv), "membres": [], "message": MSG_ORGA}
    if conv is None or conv.status not in gc.ACTIVE:
        raison = {"aucune": "la convention de groupement n'est pas encore préparée",
                  "draft": "la convention de groupement n'est pas encore générée",
                  "perimee": "la convention de groupement n'est plus à jour : une part, un prix ou la composition "
                             "a changé depuis sa génération"}.get(conv.status if conv is not None else "aucune",
                                                                  "la convention de groupement n'est pas prête")
        info["message"] = (raison[:1].upper() + raison[1:] + ". Générez-la dans « Monter le groupement » et faites-la "
                           "valider par chaque membre : cette partie la reprendra.")
        return (f"[À compléter : {raison}. Générez-la dans « Monter le groupement » puis faites-la valider par chaque "
                "membre : la forme du groupement, le chef de file et la répartition seront repris ici.]"), info
    built = gc.build_context(db, project, conv, gc._company_for(db, project), version=conv.version or 0)
    ctx = built["ctx"]
    members = ctx.get("members") or []
    lead = next((m for m in members if m.get("role") == "mandataire"), None)
    lead_nom = _val((lead or {}).get("company")) or "[À compléter : nom du chef de file]"
    forme = ctx.get("forme") or ""
    L = []
    if forme in gc.FORMES:
        f = gc.FORMES[forme]
        L.append(f"**Forme du groupement.** {f['terme']} : {f['phrase'][:1].lower() + f['phrase'][1:]}. "
                 f"{f['explication']}")
        if forme == "conjoint" and ctx.get("mandataire_solidaire"):
            L.append("Le chef de file est mandataire solidaire : devant l'acheteur, il garantit la bonne exécution "
                     "de la part de chaque autre membre.")
    else:
        L.append("**Forme du groupement.** [À compléter : forme du groupement à choisir dans la convention]")
    L += ["", f"**Chef de file (mandataire).** {lead_nom} est le mandataire du groupement. Les membres lui ont donné "
              "pouvoir pour :"]
    hab = ctx.get("habilitation") or gc.default_habilitation()
    L += [f"- {h['texte']} ;" for h in gc.HABILITATION if hab.get(h["key"])]
    L += ["", "**Répartition des parts.** Chaque membre exécute la part qui lui revient :"]
    for m in members:
        nom = _val(m.get("company")) or "Un membre"
        role = "chef de file (mandataire)" if m.get("role") == "mandataire" else "co-traitant"
        lot = _val(m.get("lot"), 255) or f"[À compléter : part de {nom}]"
        L.append(f"- {nom}, {role} : {lot}.")
        info["membres"].append({"nom": nom, "role": role, "lot": _val(m.get("lot"), 255),
                                "invite_id": m.get("invite_id")})
    if conv.status == "a_signer":
        info["message"] = MSG_ORGA_EN_ATTENTE.format(noms=", ".join(info["convention"]["accords_en_attente"])
                                                     or "un membre")
    else:
        info["message"] = MSG_ORGA + f" Convention version {conv.version or 1}, validée par tous les membres."
    return "\n".join(L).strip(), info


# ── « Qui fait quoi dans le groupement » : ce que chaque membre apporte ──────────────

_GENERIQUES_QUALIF = {"qualification", "qualifications", "qualif", "certification", "certificat", "certifie",
                      "attestation", "label", "labels", "mention", "niveau", "copie", "scan", "pdf", "jpg", "jpeg",
                      "png", "doc", "docx", "des", "les", "une", "pour", "par", "sur", "avec", "dans"}


def _jetons(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", far.fold(s or "")) if len(w) >= 2 and w not in _GENERIQUES_QUALIF}


def _justifiee_par(qualif: str, pieces: list) -> bool:
    """Une qualification DÉCLARÉE par un partenaire est « justifiée » quand il a joint à sa part un
    justificatif de type qualification, encore valable, dont le nom porte TOUS ses mots distinctifs
    (« Qualibat 1552 » ↔ « Qualibat_1552_2026.pdf »). Côté prudent : sinon, « déclarée »."""
    mots = _jetons(qualif)
    if not mots:
        return False
    jour = date.today()
    for p in pieces:
        if (p.piece_type or "") != "qualification":
            continue
        if isinstance(p.expiration_date, date) and p.expiration_date < jour:
            continue
        if mots <= _jetons(p.name or ""):
            return True
    return False


def _qualif_nom(q) -> str:
    if isinstance(q, dict):
        return _val(q.get("name") or q.get("nom") or "", 160)
    return _val(q, 160)


def _chef(db, project: Project, dossier: DossierPresentation, lot: str) -> dict:
    """Ce que le CHEF DE FILE apporte : son profil, et « Mes preuves » (qualifications et matériel acceptés,
    encore valables). Jamais ce qui lui manque."""
    from app.services import preuves as pv
    comp = db.query(Company).filter(Company.user_id == dossier.owner_id).first()
    nom = _val(comp.name if comp else "")
    quals, vus = [], set()
    try:
        faits = pv.faits_autorises(db, dossier.owner_id, natures=[pv.QUALIFICATION, pv.MATERIEL],
                                   project_id=project.id)
    except Exception:       # noqa: BLE001 — « Mes preuves » illisible : le profil suffit
        faits = []
    materiel = []
    for f in faits:
        v = f.get("valeur") or {}
        if f.get("nature") == pv.QUALIFICATION:
            libelle = _val(v.get("nom"), 160)
            cle = far.fold(libelle)
            if libelle and cle not in vus:
                vus.add(cle)
                quals.append({"libelle": libelle, "justifiee": f.get("type_source") in (pv.DOCUMENTS, pv.PUBLIC)})
        elif f.get("nature") == pv.MATERIEL:
            d = _val(v.get("designation"), 120)
            if d and far.fold(d) not in {far.fold(x) for x in materiel}:
                materiel.append(d)
    from app.services.preuves import aujourd_hui
    jour = aujourd_hui()
    for q in ((comp.qualifications if comp else None) or []):
        libelle = _qualif_nom(q)
        if not libelle or far.fold(libelle) in vus:
            continue
        if isinstance(q, dict) and at._expiree(q.get("expiration"), jour):
            continue
        vus.add(far.fold(libelle))
        quals.append({"libelle": libelle, "justifiee": False})
    eff = int(comp.effectif or 0) if comp is not None and (comp.effectif or 0) > 0 else None
    return {"cle": ag.CHEF, "invite_id": None, "nom": nom, "role": "chef_de_file", "lot": _val(lot, 255),
            "qualifications": quals, "effectif": eff, "materiel": materiel[:6], "part_envoyee": True}


def _partenaires(db, project: Project) -> list:
    """Ce que chaque PARTENAIRE (co-traitant, membre actif) apporte, tel qu'il l'a déclaré dans sa part
    ENVOYÉE (jamais un brouillon, jamais un sous-traitant, jamais une invitation du réseau sans réponse)."""
    from app.services.groupement_members import active_invites, visible_contributions
    invites = active_invites(db, project.id)
    contribs = visible_contributions(db, project.id, invites)
    out = []
    for inv in invites:
        if (inv.role or "cotraitant") != "cotraitant":
            continue
        from app.routers.invites import _network_pending
        if _network_pending(inv, db):
            continue
        c = contribs.get(inv.id)
        nom = _val(ag.nom_partenaire(inv, c))
        envoyee = c is not None and c.status == "submitted"
        m = {"cle": f"invitation:{inv.id}", "invite_id": inv.id, "nom": nom, "role": "partenaire",
             "lot": "", "qualifications": [], "effectif": None, "materiel": [], "part_envoyee": envoyee}
        if envoyee:
            pieces = db.query(ContributionPiece).filter(ContributionPiece.contribution_id == c.id).all()
            m["lot"] = _val(c.lot, 255)
            vus = set()
            for q in (c.qualifications or []):
                libelle = _qualif_nom(q)
                if libelle and far.fold(libelle) not in vus:
                    vus.add(far.fold(libelle))
                    m["qualifications"].append({"libelle": libelle, "justifiee": _justifiee_par(libelle, pieces)})
            cap = c.capacites if isinstance(c.capacites, dict) else {}
            try:
                eff = int(float(cap.get("effectif"))) if cap.get("effectif") not in (None, "") else None
            except (TypeError, ValueError):
                eff = None
            m["effectif"] = eff if eff and eff > 0 else None
        out.append(m)
    return out


def _hors_ligne(db, project: Project, conv) -> list:
    """Partenaires rattachés sans invitation, inclus dans la convention par le chef de file : leur part
    seulement (rien d'autre n'est déclaré par eux dans Adjugo)."""
    if conv is None:
        return []
    from app.services import groupement_convention as gc
    params = gc.merged_params(conv, project)
    cands = {o["link_id"]: o for o in gc.offline_candidates(db, project)}
    out = []
    for e in (params.get("membres_hors_ligne") or []):
        o = cands.get(e.get("link_id")) if isinstance(e, dict) else None
        if o is None:
            continue
        out.append({"cle": f"hors_ligne:{o['link_id']}", "invite_id": None, "nom": _val(o.get("company")),
                    "role": "hors_ligne", "lot": _val(e.get("lot") or o.get("lot"), 255), "qualifications": [],
                    "effectif": None, "materiel": [], "part_envoyee": True})
    return out


def _effectif(n: int) -> str:
    return f"{n} salarié{'s' if n > 1 else ''}"


def qui_fait_quoi(db, project: Project, dossier: DossierPresentation) -> tuple:
    """(texte, info). Ce que chaque membre APPORTE : sa part, ses qualifications, ses moyens — tels qu'il les
    a déclarés ou justifiés. Jamais une liste de manques (ni du chef de file, ni d'un autre). Les libellés
    « justifiée » / « déclarée » sont dans `info`, pour l'écran ; le texte (celui du fichier) n'en porte pas."""
    from app.services import groupement_convention as gc
    conv = gc.get_convention(db, project.id)
    lot_chef = gc.merged_params(conv, project).get("lot_mandataire") if conv is not None else ""
    membres = [_chef(db, project, dossier, lot_chef or "")] + _partenaires(db, project) + _hors_ligne(db, project, conv)
    L = [f"Le groupement réunit {len(membres)} entreprises. Chacune intervient sur sa part, avec ses qualifications "
         "et ses moyens :" if len(membres) > 1 else "Le groupement intervient avec les qualifications et les moyens "
                                                     "suivants :"]
    for m in membres:
        nom = m["nom"] or ("[À compléter : nom de votre entreprise, dans votre profil]" if m["role"] == "chef_de_file"
                           else "Un membre")
        role = {"chef_de_file": "chef de file (mandataire)", "partenaire": "co-traitant",
                "hors_ligne": "co-traitant"}[m["role"]]
        L += ["", f"**{nom}**, {role}"]
        if not m["part_envoyee"]:
            L.append(f"- [À compléter : la part de {nom} n'est pas encore envoyée (part du marché, qualifications, "
                     "moyens)]")
            continue
        if m["lot"]:
            L.append(f"- Part : {m['lot']}.")
        elif m["role"] == "chef_de_file":
            L.append("- Part : [À compléter : votre part (chef de file), à indiquer dans la convention de "
                     "« Monter le groupement »]")
        else:
            L.append(f"- Part : [À compléter : part de {nom}]")
        if m["qualifications"]:
            L.append("- Qualifications : " + ", ".join(q["libelle"] for q in m["qualifications"]) + ".")
        moyens = ([_effectif(m["effectif"])] if m["effectif"] else []) + list(m["materiel"])
        if moyens:
            L.append("- Moyens : " + ", ".join(moyens) + ".")
    for m in membres:
        for q in m["qualifications"]:
            q["statut_libelle"] = LIB_JUSTIFIEE if q["justifiee"] else LIB_DECLAREE
    info = {"membres": membres, "message": MSG_QFQ}
    return "\n".join(L).strip(), info


def note_interne(db, project: Project) -> dict:
    """La justification du groupement (décision 09-D-18) : POUR LE CHEF DE FILE SEUL, jamais exportée, jamais
    montrée aux partenaires (elle peut dire ce qu'il ne pouvait pas faire seul)."""
    plan = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
    lignes = []
    if plan and not plan.get("auto"):
        s1, s2 = plan.get("score_seul"), plan.get("score_groupement")
        if s1 is not None and s2 is not None:
            lignes.append(f"« Répondre à plusieurs ? » : {s1} % seul, {s2} % avec le groupement retenu.")
        for g in (plan.get("gaps_combles") or [])[:8]:
            if not isinstance(g, dict):
                continue
            par = ", ".join(_val(x, 80) for x in (g.get("apporte_par") or []) if x)
            exige = _val(g.get("required"), 160)
            lignes.append(f"{_val(g.get('label'), 80)}" + (f" (exigé : {exige})" if exige else "")
                          + (f" : apporté par {par}." if par else "."))
    if not lignes:
        lignes.append("Aucune composition retenue dans « Répondre à plusieurs ? » : retenez-la pour garder la trace "
                      "de ce que chaque partenaire apporte.")
    return {"message": MSG_NOTE_INTERNE, "lignes": lignes}


# ── Validation des parties tirées du groupement ──────────────────────────────────────

def attendus(db, project: Project) -> list:
    """Les membres qui valident « Qui fait quoi » (les mêmes que pour le dossier assemblé) : le chef de file
    et les partenaires qui peuvent rédiger. [(clé, invite_id, nom)]."""
    comp = None
    try:
        from app.routers.invites import tenant_owner_id
        comp = db.query(Company).filter(Company.user_id == tenant_owner_id(project, db)).first()
    except Exception:       # noqa: BLE001
        pass
    out = [(ag.CHEF, None, "Chef de file" if comp is None or not comp.name else _val(comp.name))]
    out += [(f"invitation:{m['invite_id']}", m["invite_id"], m["nom"]) for m in ag.membres(db, project)
            if m["peut_rediger"]]
    return out


def _qfq_vals(db, dossier: DossierPresentation) -> dict:
    return {v.membre_cle[len(PREFIXE_QFQ):]: v for v in db.query(DossierValidation).filter(
        DossierValidation.dossier_id == dossier.id, DossierValidation.membre_cle.like(PREFIXE_QFQ + "%"))}


def qfq_validations(db, project: Project, dossier: DossierPresentation, section: Optional[DossierSection] = None) -> list:
    """[{membre, invite_id, nom, statut valide|a_revalider|a_faire, statut_libelle, le}] de « Qui fait quoi »."""
    section = section or qfq_de(db, dossier)
    cur = at.version_courante(db, section) if section is not None else None
    vals = _qfq_vals(db, dossier)
    out = []
    for cle, iid, nom in attendus(db, project):
        v = vals.get(cle)
        if v is None:
            st = "a_faire"
        elif cur is not None and v.statut == "valide" and v.empreinte == cur.empreinte:
            st = "valide"
        else:
            st = "a_revalider"
        out.append({"membre": ag.PARTENAIRE if iid else ag.CHEF, "invite_id": iid, "nom": nom, "statut": st,
                    "statut_libelle": {"a_faire": "À valider", "valide": "Validé", "a_revalider": "À revalider"}[st],
                    "le": at._iso(v.valide_le) if v is not None else None})
    return out


def a_valide_qfq(db, project: Project, dossier: DossierPresentation, cle: str) -> bool:
    return any(x["statut"] == "valide" and ((x["invite_id"] is None and cle == ag.CHEF)
                                            or (x["invite_id"] and cle == f"invitation:{x['invite_id']}"))
               for x in qfq_validations(db, project, dossier))


def synchroniser_qfq(db, project: Project, dossier: DossierPresentation, section: DossierSection) -> None:
    """« Qui fait quoi » est VALIDÉE quand chaque membre attendu a validé SON texte courant (empreinte) ; une
    validation sur un autre texte repasse « à revalider ». L'état de la partie suit (export, dossier commun)."""
    cur = at.version_courante(db, section)
    now = utcnow()
    change = False
    for v in _qfq_vals(db, dossier).values():
        if v.statut == "valide" and (cur is None or v.empreinte != cur.empreinte):
            v.statut, v.perime_le = "a_revalider", now
            change = True
    vals = qfq_validations(db, project, dossier, section)
    tous = (cur is not None and bool((cur.texte or "").strip()) and not me.placeholders(cur.texte or "")
            and bool(vals) and all(x["statut"] == "valide" for x in vals))
    if tous and not (section.statut == at.VALIDE and section.validated_version_id == cur.id):
        section.statut = at.VALIDE
        section.validated_version_id, section.validated_hash = cur.id, cur.empreinte
        section.validated_at, section.validated_by = now, None
        section.lock_version = (section.lock_version or 0) + 1
        change = True
    elif not tous and section.statut == at.VALIDE:
        section.statut = at.A_REVALIDER      # un membre de plus à attendre, ou un texte changé
        section.lock_version = (section.lock_version or 0) + 1
        change = True
    if change:
        db.commit()


def _orga_tient(db, section: DossierSection) -> bool:
    """« Organisation du groupement » validée par le chef de file vaut pour LA convention qu'il avait sous les yeux,
    validée par tous : une convention régénérée (autre version), en attente d'accords ou périmée la fait repasser
    « à revalider », même si le texte de la partie est identique (le prix, par exemple, n'y figure pas)."""
    from app.services import groupement_convention as gc
    conv = gc.get_convention(db, section.project_id)
    d = db.get(DossierPresentation, section.dossier_id)
    meta = (d.plan_meta or {}).get("orga_validation") if d is not None and isinstance(d.plan_meta, dict) else None
    return bool(conv is not None and conv.status == "signee" and isinstance(meta, dict)
                and meta.get("convention_id") == conv.id and meta.get("version") == (conv.version or 0))


def statut(db, section: DossierSection) -> str:
    """Statut d'une partie tirée du groupement : validée · à revalider (validée puis changée) · à valider."""
    cur = at.version_courante(db, section)
    if cur is None:
        return ag.A_REDIGER
    if section.statut == at.VALIDE and section.validated_hash == cur.empreinte:
        if section.source_plan == ORGA and not _orga_tient(db, section):
            return ag.A_REVALIDER
        return ag.VALIDEE
    if section.statut == at.A_REVALIDER:
        return ag.A_REVALIDER
    return A_VALIDER


def synchroniser_orga(db, section: DossierSection) -> None:
    """L'état stocké de « Organisation du groupement » suit sa convention (export, dossier commun) : validée par le
    chef de file, puis convention changée → « à revalider »."""
    if section.statut == at.VALIDE and not _orga_tient(db, section):
        section.statut = at.A_REVALIDER
        section.lock_version = (section.lock_version or 0) + 1
        db.commit()


def valider(db, project: Project, dossier: DossierPresentation, section: DossierSection, *, membre: str,
            invite_id=None, user_id=None, version_id=None, actor: str = "", actor_kind: str = "owner",
            ip: str = "") -> DossierSection:
    """Un membre valide une partie tirée du groupement, sur SON texte courant (version) :
      • « Organisation du groupement » : le chef de file, une fois la convention validée par tous ;
      • « Qui fait quoi dans le groupement » : chaque membre attendu (chef de file, partenaires qui rédigent).
    Une partie encore « à compléter » ne se valide pas. Inscrit au journal chaîné."""
    if not at.est_generee(section) or section.dossier_id != dossier.id or section.retiree_at is not None:
        raise AtelierError(404, "partie_introuvable", "Partie introuvable.")
    rafraichir_generees(db, project, dossier)
    db.refresh(section)
    cur = at.version_courante(db, section)
    if cur is None or cur.id != int(version_id or 0):
        raise AtelierError(409, "texte_modifie_entre_temps", "Le texte de cette partie a changé : relisez-le avant de "
                                                             "le valider.",
                           version_courante_id=cur.id if cur else None)
    if me.placeholders(cur.texte or ""):
        raise AtelierError(409, "partie_incomplete", "Cette partie n'est pas encore complète (passages « À compléter ») "
                                                     ": elle se complète toute seule quand la convention et les parts "
                                                     "des membres sont prêtes.")
    titre = at._flat(section.intitule)[:160]
    if section.source_plan == ORGA:
        if membre != ag.CHEF:
            raise AtelierError(403, "reserve_au_chef_de_file", "Cette partie se valide par le chef de file : elle "
                                                               "reprend la convention que chaque membre a validée.")
        conv = _convention(db, project)
        if conv is None or conv.status != "signee":
            noms = _accords_en_attente(db, conv) if conv is not None and conv.status == "a_signer" else []
            raise AtelierError(409, "convention_a_valider", MSG_ORGA_EN_ATTENTE.format(noms=", ".join(noms))
                               if noms else "La convention doit d'abord être générée et validée par tous les membres.")
        section = at._verrouiller(db, section)
        section.statut = at.VALIDE
        section.validated_version_id, section.validated_hash = cur.id, cur.empreinte
        section.validated_at, section.validated_by = utcnow(), user_id
        section.lock_version = (section.lock_version or 0) + 1
        # La convention validée qu'il avait sous les yeux : une autre ensuite fera repasser la partie « à revalider ».
        meta = dict(dossier.plan_meta) if isinstance(dossier.plan_meta, dict) else {}
        meta["orga_validation"] = {"convention_id": conv.id, "version": conv.version or 0}
        dossier.plan_meta = meta
        flag_modified(dossier, "plan_meta")
        db.commit()
    else:
        cle = ag.CHEF if membre == ag.CHEF else f"invitation:{int(invite_id)}"
        if cle not in {c for c, _i, _n in attendus(db, project)}:
            raise AtelierError(403, "membre_non_attendu", "Seuls les membres du groupement qui rédigent valident cette "
                                                          "partie.")
        from sqlalchemy.exc import IntegrityError
        for _essai in range(2):         # deux validations simultanées du même membre : une seule ligne
            v = _qfq_vals(db, dossier).get(cle)
            if v is None:
                v = DossierValidation(dossier_id=dossier.id, project_id=project.id, owner_id=dossier.owner_id,
                                      membre=membre, membre_cle=PREFIXE_QFQ + cle,
                                      invite_id=(int(invite_id) if membre == ag.PARTENAIRE else None))
                db.add(v)
            v.empreinte, v.statut, v.valide_le, v.perime_le, v.user_id = (cur.empreinte, "valide", utcnow(), None,
                                                                          user_id)
            try:
                db.commit()
                break
            except IntegrityError:
                db.rollback()
        synchroniser_qfq(db, project, dossier, section)
    ag._journal(db, action="redaction.partie_groupement_validee", project_id=project.id, owner_id=dossier.owner_id,
                actor=actor, actor_kind=actor_kind, invite_id=(invite_id if membre == ag.PARTENAIRE else None),
                target_id=section.id, ip=ip, detail=f"Partie validée : {titre}",
                meta={"partie": section.source_plan, "version": cur.numero, "empreinte": cur.empreinte})
    db.refresh(section)
    return section


def valider_par_le_chef(db, project: Project, section: DossierSection, lecteur: at.Lecteur, version_id,
                        ip: str = "") -> DossierSection:
    """Le chef de file valide une partie tirée du groupement depuis l'atelier (POST …/sections/{sid}/valider)."""
    if lecteur.kind != at.AUTEUR_ORG or lecteur.owner_id != section.owner_id:
        raise at.refus_ecriture(section)
    dossier = db.get(DossierPresentation, section.dossier_id)
    return valider(db, project, dossier, section, membre=ag.CHEF, user_id=lecteur.user_id, version_id=version_id,
                   actor=lecteur.email or f"user:{lecteur.user_id}", actor_kind="owner", ip=ip)


# ── Ce que lisent les membres ────────────────────────────────────────────────────────

def _texte_out(v: Optional[DossierSectionVersion]) -> Optional[dict]:
    if v is None:
        return None
    return {"version_id": v.id, "numero": v.numero, "empreinte": v.empreinte, "cree_le": at._iso(v.created_at),
            "a_completer": len(me.placeholders(v.texte or "")), "texte": v.texte or ""}


def detail(db, project: Project, dossier: DossierPresentation, section: DossierSection, *, pour: str = "chef",
           invite_id=None) -> dict:
    """Une partie tirée du groupement, telle que la lit un membre : son texte, d'où il vient (convention,
    parts), ses qualifications avec leur libellé (« justifiée » / « déclarée »), qui l'a validée. La note
    interne (justification du groupement) n'est rendue qu'au chef de file."""
    cur = at.version_courante(db, section)
    st = statut(db, section)
    out = {"section_id": section.id, "genere": section.source_plan, "intitule": section.intitule,
           "titre": section.intitule, "statut": st, "statut_libelle": STATUTS_GENERES.get(st, ""),
           "texte_commun": _texte_out(cur), "lock_version": section.lock_version or 0}
    if section.source_plan == ORGA:
        _t, info = organisation(db, project, dossier)
        out.update(message=info["message"], convention=info["convention"], membres=info["membres"],
                   valide_par="chef_de_file",
                   validation=({"version_id": section.validated_version_id, "empreinte": section.validated_hash,
                                "le": at._iso(section.validated_at)} if section.validated_version_id else None))
    else:
        _t, info = qui_fait_quoi(db, project, dossier)
        cles = ("nom", "role", "lot", "qualifications", "effectif", "materiel", "part_envoyee") \
            + (("invite_id",) if pour == "chef" else ())
        membres = [{k: m[k] for k in cles} for m in info["membres"]]
        vals = qfq_validations(db, project, dossier, section)
        out.update(message=info["message"], membres=membres, valide_par="chaque_membre", validations=vals)
        cle = ag.CHEF if pour == "chef" else f"invitation:{invite_id}"
        moi = next((x for x in vals if (x["invite_id"] is None and cle == ag.CHEF)
                    or (x["invite_id"] and cle == f"invitation:{x['invite_id']}")), None)
        out["ma_validation"] = moi
        if pour == "chef":
            out["note_interne"] = note_interne(db, project)
    return out


STATUTS_GENERES = {ag.A_REDIGER: "À rédiger", A_VALIDER: "À valider", ag.A_REVALIDER: "À revalider",
                   ag.VALIDEE: "Validée"}


def _et(noms: list) -> str:
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def part_out(db, s: DossierSection) -> dict:
    """Le statut d'une partie tirée du groupement pour l'onglet « Rédaction » du chef de file (le même que dans « Qui
    écrit quoi ») et ce qu'elle attend de LUI : `a_valider_par_vous` (le bouton « Valider ») ; « Validée par vous ; à
    valider par X » quand sa validation de « Qui fait quoi » est faite et qu'un partenaire doit encore la donner."""
    st = statut(db, s)
    out = {"statut": st, "statut_libelle": STATUTS_GENERES.get(st, ""), "mention": "", "a_valider_par_vous": False}
    cur = at.version_courante(db, s)
    if st == ag.VALIDEE or cur is None or me.placeholders(cur.texte or ""):
        return out
    if s.source_plan == ORGA:
        from app.services import groupement_convention as gc
        conv = gc.get_convention(db, s.project_id)
        if conv is not None and conv.status == "signee":
            out["a_valider_par_vous"] = True
        elif conv is not None and conv.status == "a_signer":
            noms = _accords_en_attente(db, conv)
            if noms:
                out["mention"] = "La convention attend encore l'accord de " + _et(noms)
        return out
    project, dossier = db.get(Project, s.project_id), db.get(DossierPresentation, s.dossier_id)
    vals = qfq_validations(db, project, dossier, s)
    moi = next((x for x in vals if x["invite_id"] is None), None)
    if moi is None or moi["statut"] != "valide":
        out["a_valider_par_vous"] = True
        return out
    autres = [x["nom"] for x in vals if x["invite_id"] and x["statut"] != "valide"]
    if autres:
        out["mention"] = "Validée par vous ; à valider par " + _et(autres)
    return out


def ligne_chef(db, project: Project, dossier: DossierPresentation, s: DossierSection, rang: str) -> dict:
    """La ligne de « Qui écrit quoi » d'une partie tirée du groupement (personne ne la rédige)."""
    cur = at.version_courante(db, s)
    st = statut(db, s)
    out = dict(ag._section_base_out(dossier, s, rang), enregistre=False,
               redacteur={"type": at.AUTEUR_GROUPEMENT, "invite_id": None,
                          "nom": at.LIBELLES_GENERES.get(s.source_plan, "Tirée du groupement")},
               proposition=None, choix="genere", longueur_mots=None, date_limite=None, demandee_le=None,
               statut=st, statut_libelle=STATUTS_GENERES.get(st, ""), mention="", envoyee_le=None,
               validation=({"version_id": s.validated_version_id, "empreinte": s.validated_hash,
                            "le": at._iso(s.validated_at)} if s.validated_version_id else None),
               texte_commun=ag._version_commune_out(cur, texte=False), lock_version=s.lock_version or 0,
               genere=s.source_plan, message=(MSG_ORGA if s.source_plan == ORGA else MSG_QFQ))
    if s.source_plan == QFQ:
        out["validations"] = qfq_validations(db, project, dossier, s)
    return out


def partie_assemblee(db, project: Project, dossier: DossierPresentation, s: DossierSection, base: dict,
                     v: Optional[DossierSectionVersion], pour_invite_id=None) -> dict:
    st = statut(db, s)
    item = dict(base, redacteur={"type": at.AUTEUR_GROUPEMENT,
                                 "nom": at.LIBELLES_GENERES.get(s.source_plan, "Tirée du groupement"), "vous": False},
                statut=st, statut_libelle=STATUTS_GENERES.get(st, ""), texte=(v.texte if v is not None else None),
                a_completer=len(me.placeholders(v.texte or "")) if v is not None else 0, genere=s.source_plan)
    if s.source_plan == QFQ:
        item["validations"] = qfq_validations(db, project, dossier, s)
        _t, info = qui_fait_quoi(db, project, dossier)
        item["membres"] = [{k: m[k] for k in ("nom", "role", "lot", "qualifications", "effectif", "materiel",
                                              "part_envoyee")} for m in info["membres"]]
    else:
        item["convention"] = convention_info(db, project)
    return item


# ── « Harmoniser le ton » : des transitions, rien d'autre ────────────────────────────

TRANSITION_MOTS_MAX = 40
JONCTIONS_MAX = 30
EXTRAIT = 700
MSG_HARMONISER = ("Adjugo propose une phrase de transition au début des parties qui suivent la part d'un autre membre. "
                  "Le texte de chaque membre ne change pas. Une phrase qui apporterait un fait (chiffre, date, nom, "
                  "qualification, matériel, engagement…) absent du dossier est refusée. Chaque partie touchée repasse "
                  "« à revalider » par son auteur.")
_MOIS = ("janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre|lundi|mardi|mercredi|"
         "jeudi|vendredi|samedi|dimanche|trimestre|semestre|printemps|automne|hiver|quinzaine|"
         # une fréquence est un engagement de calendrier (« un suivi quotidien »)
         "quotidien(?:ne)?s?|quotidiennement|hebdomadaires?|mensuel(?:le)?s?|annuel(?:le)?s?|journaliers?|"
         "journalieres?|chaque (?:jour|semaine|mois|annee)|tous les (?:jours|mois|ans)|"
         # une période relative est un engagement de calendrier (« dès la rentrée », « l'an prochain », « la nuit »)
         "rentree|an prochain|annee prochaine|mois prochain|semaine prochaine|nuits?|nocturnes?|week-ends?|weekends?|"
         "jour meme|lendemain|matinees?|soirees?|toussaint|noel|paques|"
         # … comme une période de l'année (« pendant les vacances scolaires », « avant l'été », « la période
         # estivale ») ou un délai compté depuis un acte du marché (« dès la signature du marché ») — contre-relecture
         "vacances|conges|jours? feries?|feries?|(?:l'|en |cet |d'|cette )ete|estivale?s?|estivaux|"
         "(?:fin|debut) d'annee|(?:fin|debut) de (?:mois|semaine|journee)|"
         "des (?:la |le |l')?(?:signature|notification|ordre de service|attribution|commande|demarrage|debut|lancement)|"
         "(?:a compter|a partir|apres|avant) (?:de la |du |de l'|la |le |l')(?:signature|notification|ordre de service|"
         "attribution|commande)")
_DATE = re.compile(r"(?<![a-z])(?:" + _MOIS + r")(?![a-z])")
_QUANTITE = re.compile(r"(?<![a-z])(?:moitie|tiers|quart|double|triple|quadruple|dizaines?|douzaines?|vingtaines?|"
                       r"trentaines?|centaines?|milliers?|millions?|milliards?|totalite|integralite|"
                       # la totalité ou la constance, dites autrement (« sans aucune sous-traitance », « toujours »)
                       r"aucune?s?|entierement|integralement|exclusivement|systematiques?|systematiquement|"
                       r"sans exception|toujours|jamais|en permanence|en continu)(?![a-z])")
# Un rang (« le premier désamianteur », « leader »), un superlatif ou une exclusivité (« le seul », « l'unique »,
# « le meilleur », « la référence ») est un fait sur l'entreprise, comme un nombre.
_RANG = re.compile(r"(?<![a-z])(?:premier|premiere|premiers|premieres|deuxieme|second|seconde|troisieme|quatrieme|"
                   r"cinquieme|sixieme|septieme|huitieme|neuvieme|dixieme|centieme|leaders?|numero un|n° ?1|"
                   r"seule?s?|uniques?|uniquement|meilleure?s?|le mieux|champions?|incontournables?|"
                   r"inegalee?s?|sans (?:egal|equivalent|pareil)|hors pair|reconnue?s?|renommee?s?|excellence|"
                   r"exceptionnel(?:le)?s?|specialistes?|expert(?:e|s|es)?|exclusi(?:f|ve|fs|ves|vite)|"
                   r"(?:la|une|entreprise de|acteur de|actrice de) reference|"
                   r"(?:le|la|les|au) (?:plus|moins) [a-z]{3,}|plus (?:grande?s?|importante?s?|ancienne?s?))(?![a-z])")
# Locutions de transition qui ne classent rien (« dans un second temps », « en premier lieu », « le premier volet »,
# « la première partie ») : retirées avant de chercher un rang (contre-relecture : elles étaient refusées).
_CONNECTEURS_RANG = re.compile(
    r"(?<![a-z])(?:en (?:premier|second|dernier) lieu|en premier|dans un (?:premier|second|deuxieme|troisieme|dernier) "
    r"temps|(?:un|le|ce|du|au) (?:premier|second|deuxieme|troisieme|dernier) (?:volet|temps|point|axe|aspect|"
    r"chapitre|sujet|theme|niveau de lecture)|(?:une|la|cette|de la|a la) (?:premiere|seconde|deuxieme|troisieme|"
    r"derniere) (?:partie|section|sous-partie|question))(?![a-z])")
# Un engagement, même à la troisième personne (« le groupement garantit », « une garantie décennale »), un délai
# (« en moins d'une heure », « sous 48 heures ») ou une organisation du travail (« en astreinte », « en horaires
# décalés », « sans sous-traitance ») : jamais dans une transition.
_ENGAGE_T = re.compile(r"(?<![a-z])(?:garanti(?:t|ssent|ssons|e|es|r)|garanties?|s'engage(?:nt)?|engagements?|"
                       r"assure(?:nt)?|promet(?:tent)?|en moins d|dans l'heure|sous (?:\w+ )?(?:heures?|jours?|"
                       r"huitaine|quinzaine)|immediatement|sans delai|au plus tard|zero (?:defaut|reserve|accident)|"
                       r"delais?|astreintes?|permanences?|horaires? (?:decales?|de nuit|de jour|adaptes?|amenages?)|"
                       r"heures? creuses|en dehors des heures|hors (?:des )?heures|sous-trait\w*)"
                       r"(?![a-z])")
# Mots qui ouvrent une phrase sans être un nom (la première lettre d'une phrase est toujours capitale).
_OUVRANTS = {
    "a", "afin", "ainsi", "apres", "au", "aux", "avant", "avec", "c'est", "ce", "ces", "cet", "cette", "chacun",
    "chacune", "chaque", "comme", "concernant", "conformement", "cote", "d", "dans", "de", "des", "du", "elle",
    "elles", "en", "enfin", "ensuite", "entre", "et", "il", "ils", "l", "la", "le", "les", "leur", "leurs",
    "lorsque", "mais", "ou", "outre", "par", "parallelement", "pour", "puis", "quant", "s", "sa", "sans", "selon",
    "ses", "son", "sur", "tandis", "tout", "toute", "toutes", "tous", "un", "une", "voici", "pareillement",
    "complementairement", "dorenavant", "desormais", "egalement", "de meme", "en outre", "partant", "suivant",
}


def controle_transition(texte: str, sources_avant) -> dict:
    """Une phrase de transition proposée par l'IA, contrôlée SANS IA avant d'entrer dans le dossier :
    {ok, texte, raison, faits: [{fait, type}]}. Refusée si elle n'est pas une transition (plusieurs phrases,
    trop longue, titre, liste, renvoi, « [À compléter] »…) ou si elle apporte UN fait absent du dossier avant
    l'harmonisation : nombre (en chiffres ou en lettres, pourcentage, montant, durée), date ou moment, quantité
    (« une centaine »), certification ou qualification, nom propre (en tête ou au fil de la phrase), matériel,
    engagement (« sans retard », « nous garantissons »…). `sources_avant` : les textes du dossier avant."""
    src = sources_avant if isinstance(sources_avant, far.Sources) else far.Sources(list(sources_avant or []))
    t = re.sub(r"\s+", " ", str(texte or "")).strip().strip("\"'«» ").strip()
    out = {"ok": False, "texte": t, "raison": "", "faits": []}
    if not t:
        out["raison"] = "Phrase vide."
        return out
    if re.search(r"[\[\]{}<>#|`*_\\@]|https?://|www\.", t) or re.match(r"^(?:[-+•>]|\d{1,2}[.)])\s", t):
        out["raison"] = "Ce n'est pas une phrase de transition (renvoi, titre, liste ou mise en forme)."
        return out
    mots = re.findall(r"\w+", t)
    if len(mots) > TRANSITION_MOTS_MAX:
        out["raison"] = f"Phrase trop longue ({len(mots)} mots, {TRANSITION_MOTS_MAX} au plus)."
        return out
    if len([p for p in far._couper(t) if len(p.strip()) > 2]) > 2:
        out["raison"] = "Une transition tient en une phrase."
        return out
    faits = []
    low_src = src.low
    mots_src = set(re.findall(r"[a-z0-9']+", low_src))
    for ph, _titre, tableau in far.phrases(t):
        for fait, kind, key in far._facts_in(ph, tableau=tableau):
            if not src.has(kind, key):
                faits.append({"fait": fait, "type": kind})
        eng = fs.engagement(ph)
        if eng and far.fold(eng) not in low_src:
            faits.append({"fait": eng, "type": fs.ENGAGEMENT})
        m = re.match(r"\s*([A-ZÀ-ÖØ-Þ][\wÀ-ÿ'’-]*)", ph)
        if m:
            w = far.fold(m.group(1)).replace("’", "'")
            if w not in _OUVRANTS and w.split("'")[0] not in _OUVRANTS and w not in mots_src \
                    and not any(f["fait"].startswith(m.group(1)) for f in faits):
                faits.append({"fait": m.group(1), "type": far.NOM_PROPRE})
    low = far.fold(t)
    sans_connecteurs = _CONNECTEURS_RANG.sub(lambda x: " " * len(x.group(0)), low)
    for rx, kind in ((_DATE, "date"), (_QUANTITE, "quantite"), (_RANG, far.EN_LETTRES), (_ENGAGE_T, fs.ENGAGEMENT)):
        for mm in rx.finditer(sans_connecteurs if rx is _RANG else low):
            if not re.search(r"(?<![a-z])" + re.escape(mm.group(0)) + r"(?![a-z])", low_src):
                faits.append({"fait": t[mm.start():mm.end()], "type": kind})
    # Filet : un nombre écrit en chiffres que le dossier ne contient pas est un fait ajouté, quelle que soit sa forme
    # (collé à son unité, ordinal, heure…).
    for mm in re.finditer(r"\d+(?:[.,]\d+)?", t):
        if not re.search(r"(?<![\d.,])" + re.escape(mm.group(0)) + r"(?![\d])", low_src) \
                and not any(mm.group(0) in f["fait"] for f in faits):
            faits.append({"fait": mm.group(0), "type": far.CHIFFRE})
    vus, uniq = set(), []
    for f in faits:
        k = (f["type"], far.fold(f["fait"]))
        if k not in vus:
            vus.add(k)
            uniq.append(f)
    out["faits"] = uniq
    if uniq:
        out["raison"] = ("Phrase refusée : elle apporte " + ", ".join(f"« {f['fait']} »" for f in uniq[:4])
                         + (" et d'autres faits" if len(uniq) > 4 else "") + ", absent" + ("s" if len(uniq) > 1 else "")
                         + " du dossier avant l'harmonisation.")
        return out
    out["ok"] = True
    return out


def _auteur(s: DossierSection) -> tuple:
    return (s.author_kind, s.author_invite_id or 0)


def _transitions(dossier: DossierPresentation) -> dict:
    meta = dossier.plan_meta if isinstance(dossier.plan_meta, dict) else {}
    t = meta.get("transitions")
    return dict(t) if isinstance(t, dict) else {}


def _corps(texte: str, ancienne: Optional[str]) -> str:
    """Le texte du membre sans la transition qu'une harmonisation précédente y avait ajoutée (jamais
    empilées) : seulement si le texte commence EXACTEMENT par elle."""
    t = texte or ""
    if ancienne and t.startswith(ancienne + "\n\n"):
        return t[len(ancienne) + 2:]
    return t


def jonctions(db, dossier: DossierPresentation) -> list:
    """Les jonctions à harmoniser : entre deux parties qui se suivent (parties tirées du groupement mises à
    part), qui ont du texte et dont les AUTEURS diffèrent. [{suivante, precedente, base, vprec}]."""
    act = at.sections_actives(db, dossier)
    com = at.versions_communes(db, act, at.Lecteur.organisation(dossier.owner_id))
    seq = [(s, com[s.id]) for s in act
           if not at.est_generee(s) and com.get(s.id) is not None and (com[s.id].texte or "").strip()]
    out = []
    for (p, vp), (n, vn) in zip(seq, seq[1:]):
        if _auteur(p) != _auteur(n):
            out.append({"suivante": n, "precedente": p, "base": vn, "vprec": vp})
    return out[:JONCTIONS_MAX]


def _en_cours(db, dossier: DossierPresentation, owner_ids: list) -> Optional[Job]:
    for j in db.query(Job).filter(Job.kind == JOB_HARMONISER, Job.status.in_(["pending", "running"]),
                                  Job.user_id.in_(list(owner_ids) or [-1])).all():
        res = j.result if isinstance(j.result, dict) else {}
        if int(((res.get("_debit") or {}).get("dossier_id")) or 0) == dossier.id:
            return j
    return None


def lancer_harmonisation(db, user: User, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur,
                         member_ids: list, accepte_debit: bool = False) -> Job:
    """« Harmoniser le ton » : lancé par le chef de file (son dossier), en tâche de fond. Débit : une refonte du
    dossier (décision 6a ; la 1re action de l'IA du dossier compte pour 1 analyse), rendue si l'IA tombe ou si
    aucune phrase n'est retenue."""
    from app.services.jobs import run_in_thread
    at.exiger_ia_permise(dossier)               # vague 5 : dossier « sans IA », aucune harmonisation par l'IA
    if not ag.repartition_active(db, dossier):
        raise AtelierError(409, "groupement_non_prepare", "Préparez d'abord « Qui écrit quoi » : l'harmonisation relie "
                                                          "les parts des membres du groupement.")
    if _en_cours(db, dossier, member_ids) is not None:
        raise AtelierError(409, "harmonisation_en_cours", "Adjugo harmonise déjà ce dossier : attendez la fin.")
    js = jonctions(db, dossier)
    if not js:
        raise AtelierError(422, "rien_a_harmoniser", "Rien à harmoniser : il faut au moins deux parties qui se suivent, "
                                                     "écrites par des membres différents, avec du texte.")
    at._verifier_aucune_tache(db, [j["suivante"] for j in js if j["suivante"].author_kind == at.AUTEUR_ORG])
    from app.services.budget_ia import estimer, verifier
    estimation = estimer("harmoniser")         # enveloppe tirée de ses plafonds (JONCTIONS_MAX × deux extraits)
    verifier(user, db, "atelier", estimation)
    plan = [{"section_id": j["suivante"].id, "base_version_id": j["base"].id, "precedente_id": j["precedente"].id}
            for j in js]
    job = Job(user_id=user.id, kind=JOB_HARMONISER, status="pending",
              label="Dossier de présentation : harmoniser le ton entre les parts")
    db.add(job)
    db.commit()
    jid = job.id
    try:
        releve = at._debiter(db, user, dossier, [js[0]["suivante"]], accepte_debit, jid, estimation,
                             deja_ia=lambda _db, _s: True)
    except Exception:
        db.rollback()
        j = db.get(Job, jid)
        if j is not None:
            db.delete(j)
            db.commit()
        raise
    job = db.get(Job, jid)
    releve.update(dossier_id=dossier.id, rendu=False)
    job.result = {"_debit": releve}
    db.commit()
    pid, owner, mids, uid = project.id, dossier.owner_id, list(member_ids), user.id

    def _work(jdb):
        return _executer(jdb, job_id=jid, project_id=pid, owner_id=owner, member_ids=mids, user_id=uid, plan=plan)

    def _on_error(jdb, j):
        at.rembourser(jdb, j)

    run_in_thread(jid, _work, on_error=_on_error, tenant_id=owner, error_message=at.MSG_IA_PANNE)
    return db.get(Job, jid)


def _extrait(texte: str, fin: bool) -> str:
    t = re.sub(r"\s+", " ", me.clean_markdown(texte or "")).strip()
    if len(t) <= EXTRAIT:
        return t
    return ("… " + t[-EXTRAIT:]) if fin else (t[:EXTRAIT] + " …")


def _proprietaire(db, owner_id: int, s: DossierSection) -> int:
    """Le tenant dont « Mes preuves » connaît l'équipe de l'auteur de la partie : le chef de file, ou l'organisation du
    compte qui a rattaché le lien du partenaire (0 : partenaire sans compte, aucune fiche « Équipe » connue)."""
    if s.author_kind != at.AUTEUR_INVITATION:
        return owner_id
    inv = db.get(ProjectInvite, s.author_invite_id) if s.author_invite_id else None
    u = db.get(User, inv.accepted_by_user_id) if inv is not None and inv.accepted_by_user_id else None
    if u is None:
        return 0
    from app.core.org import data_owner_id
    return data_owner_id(u, db)


MSG_PASSAGE_CV = "(passage non transmis : il contient un CV)"


def _sans_cv(db, proprietaire: int, texte: str, fin: bool) -> str:
    """Aucun CV ne part à l'IA (doctrine § 7, règle 9). Le CV est repéré sur le texte TEL QU'ÉCRIT (sa forme tient
    aux lignes, que l'extrait aplatit) : les blocs en forme de CV sont retirés avant l'extrait ; s'il reste un CV
    reconnaissable (une ligne d'une fiche « Équipe » de l'auteur), le passage n'est pas transmis."""
    from app.services import preuves_atelier as pa
    try:
        t = pa.retirer_cv_par_forme(texte or "")
        reste = pa.cv_presents(db, proprietaire or 0, t)
    except Exception:       # noqa: BLE001 — dans le doute, rien
        return MSG_PASSAGE_CV
    return MSG_PASSAGE_CV if reste else _extrait(t, fin)


def _executer(db, *, job_id: int, project_id: int, owner_id: int, member_ids: list, user_id: int, plan: list) -> dict:
    """Dans le fil de la tâche de fond (espace facturé du chef de file) : prépare les extraits, appelle l'IA
    SANS base (noms masqués), contrôle chaque phrase sans IA, puis ajoute les phrases retenues — chacune au
    début de SA partie, si cette partie n'a pas changé entre-temps."""
    from app.services.agents import memoire as moteur
    from app.services.llm import LLMUnavailable, cost_meter, pii_scope
    project = db.get(Project, project_id)
    dossier = at.get_dossier(db, project_id, owner_id)
    if project is None or dossier is None:
        raise RuntimeError("dossier introuvable")
    act = at.sections_actives(db, dossier)
    by_id = {s.id: s for s in act}
    com = at.versions_communes(db, act, at.Lecteur.organisation(owner_id))
    rangs = at._rangs(dossier, act)
    anciennes = _transitions(dossier)
    auteurs, items = {}, []
    for p in plan:
        n, prec = by_id.get(p["section_id"]), by_id.get(p["precedente_id"])
        base = com.get(p["section_id"])
        if n is None or prec is None or base is None or base.id != p["base_version_id"]:
            continue
        for s in (prec, n):
            auteurs.setdefault(_auteur(s), f"membre {chr(65 + len(auteurs))}")
        corps = _corps(base.texte or "", anciennes.get(str(n.id)))
        vp = com.get(prec.id)
        items.append({"id": str(n.id), "titre": ag.ax_titre(rangs.get(n.id, ""), n.intitule),
                      "titre_precedent": ag.ax_titre(rangs.get(prec.id, ""), prec.intitule),
                      "auteur": auteurs[_auteur(n)], "auteur_precedent": auteurs[_auteur(prec)],
                      "fin_precedente": _sans_cv(db, _proprietaire(db, owner_id, prec), vp.texte if vp else "", True),
                      "debut": _sans_cv(db, _proprietaire(db, owner_id, n), corps, False)})
    if not items:
        j = db.get(Job, job_id)
        debit = None
        if j is not None:
            at.rembourser(db, j)
            db.refresh(j)
            debit = (j.result or {}).get("_debit") if isinstance(j.result, dict) else None
        # Le relevé reste dans le résultat : la tâche se relit par sa route (portée du dossier), et l'écran montre
        # le message.
        return {"transitions": [], "ajoutees": 0, "refusees": 0, "_debit": debit,
                "message": "Les parties ont changé pendant la préparation : rien n'a été harmonisé, rien n'est décompté."}
    ctx = at.Contexte(db, project, owner_id, member_ids)
    # Noms des salariés de TOUS les partenaires qui ont un compte (profil, fiches « Équipe »), part de co-traitance
    # soumise ou non : masqués seulement, rien n'est montré au chef de file.
    from app.services.fiches_import import equipe_avec_noms_reperes
    from app.services.groupement_members import active_invites
    from app.services.pii import from_team, team_of_users
    uids = [i.accepted_by_user_id for i in active_invites(db, project.id) if i.accepted_by_user_id]
    equipes = team_of_users(db, uids) if uids else []
    textes = [x["fin_precedente"] for x in items] + [x["debut"] for x in items]
    pz = from_team(equipe_avec_noms_reperes(ctx.team + ctx.preuves_team + ctx.partner_team + equipes, textes,
                                            exclure=ctx.noms_entreprise))
    with pii_scope(pz), cost_meter("atelier : harmoniser", owner_id) as cm:
        r = moteur.harmoniser_transitions(items, billing_id=owner_id)
    if r.get("erreur"):
        raise LLMUnavailable("Service IA indisponible : rien n'a été harmonisé.")
    # Enregistrement (relu : la tâche a pu durer) — le dossier tel qu'il est maintenant.
    db.expire_all()
    dossier = at.get_dossier(db, project_id, owner_id)
    at._cumuler_cout(dossier, cm.summary())
    db.commit()
    act = at.sections_actives(db, dossier)
    com = at.versions_communes(db, act, at.Lecteur.organisation(owner_id))
    sources_avant = [(v.texte or "") for v in com.values() if v is not None] + [s.intitule or "" for s in act]
    src = far.Sources(sources_avant)
    proposees = r.get("transitions") or {}
    sortie, ajoutees, refusees = [], 0, 0
    touchees_partenaires = []
    anciennes = _transitions(dossier)
    for p in plan:
        sid = p["section_id"]
        t = proposees.get(str(sid))
        if not t:
            continue
        ctl = controle_transition(t, src)
        s = db.get(DossierSection, sid)
        base = com.get(sid)
        if not ctl["ok"]:
            refusees += 1
            sortie.append({"section_id": sid, "ok": False, "texte": ctl["texte"], "raison": ctl["raison"],
                           "faits": ctl["faits"]})
            continue
        if s is None or s.retiree_at is not None or base is None or base.id != p["base_version_id"]:
            sortie.append({"section_id": sid, "ok": False, "texte": ctl["texte"],
                           "raison": "La partie a changé pendant l'harmonisation : elle n'a pas été touchée.",
                           "faits": []})
            continue
        corps = _corps(base.texte or "", anciennes.get(str(sid)))
        nouveau = ctl["texte"] + "\n\n" + corps
        v = _ajouter_transition(db, project, dossier, s, base, nouveau, ctl["texte"], user_id, job_id)
        if v is None:
            continue
        anciennes[str(sid)] = ctl["texte"]
        ajoutees += 1
        sortie.append({"section_id": sid, "ok": True, "texte": ctl["texte"], "version_id": v.id})
        if s.author_kind == at.AUTEUR_INVITATION:
            touchees_partenaires.append(s)
    dossier = db.get(DossierPresentation, dossier.id)
    meta = dict(dossier.plan_meta) if isinstance(dossier.plan_meta, dict) else {}
    meta["transitions"] = anciennes
    dossier.plan_meta = meta
    flag_modified(dossier, "plan_meta")
    db.commit()
    user = db.get(User, user_id)
    acteur = (user.email if user is not None else "") or f"user:{user_id}"
    for s in touchees_partenaires:
        titre = at._flat(s.intitule)[:160]
        ag._journal(db, action="redaction.transition_ajoutee", project_id=project.id, owner_id=dossier.owner_id,
                    actor=acteur, actor_kind="owner", invite_id=s.author_invite_id, target_id=s.id,
                    detail=f"Phrase de transition ajoutée au début de votre partie, à revalider : {titre}")
        ag._notifier_partenaire(db, project, db.get(ProjectInvite, s.author_invite_id), titre, True)
    ag._journal(db, action="redaction.harmonisation", project_id=project.id, owner_id=dossier.owner_id, actor=acteur,
                actor_kind="owner", target_type="dossier_presentation", target_id=dossier.id,
                detail=(f"Ton harmonisé : {ajoutees} phrase{'s' if ajoutees > 1 else ''} de transition ajoutée"
                        f"{'s' if ajoutees > 1 else ''}, {refusees} refusée{'s' if refusees > 1 else ''}"),
                meta={"ajoutees": ajoutees, "refusees": refusees})
    if ajoutees:
        ag.apres_changement_commun(db, project, dossier, "ton harmonisé (phrases de transition)", actor=acteur,
                                   actor_kind="owner")
    j = db.get(Job, job_id)
    if not ajoutees and j is not None:
        at.rembourser(db, j)            # rien de retenu : rien n'est décompté
        db.refresh(j)
    debit = (j.result or {}).get("_debit") if j is not None and isinstance(j.result, dict) else None
    if ajoutees:
        msg = (f"{ajoutees} phrase{'s' if ajoutees > 1 else ''} de transition ajoutée{'s' if ajoutees > 1 else ''}"
               + (f", {refusees} refusée{'s' if refusees > 1 else ''} (fait absent du dossier)" if refusees else "")
               + ". Les parties touchées repassent « à revalider » par leur auteur.")
    else:
        msg = ("Aucune phrase de transition retenue" + (f" ({refusees} refusée{'s' if refusees > 1 else ''} : fait "
                                                         "absent du dossier)" if refusees else "")
               + " : le dossier n'a pas changé, rien n'est décompté.")
    return {"transitions": sortie, "ajoutees": ajoutees, "refusees": refusees, "message": msg, "_debit": debit}


def _ajouter_transition(db, project: Project, dossier: DossierPresentation, s: DossierSection,
                        base: DossierSectionVersion, texte: str, transition: str, user_id: int,
                        job_id: int) -> Optional[DossierSectionVersion]:
    """La phrase entre dans la partie comme une NOUVELLE version : le corps du membre est intact, ses sources
    et ses faits gardés ; un fait de la phrase absent de CETTE partie est à relire. Une partie d'un partenaire
    reçoit un texte commun « écrit par le chef de file » : à revalider par lui (avant / après, rétablir)."""
    s = at._verrouiller(db, s)
    if s.current_version_id != base.id:
        db.rollback()
        return None
    noms = [ag.nom_partenaire(db.get(ProjectInvite, s.author_invite_id))] if s.author_invite_id else []
    extra = far.a_relire(transition, [base.texte or ""], noms_entreprise=noms,
                         section_entreprise=at.section_sur_l_entreprise(s))
    faits = [dict(x) for x in (base.faits or []) if isinstance(x, dict)] + extra
    if s.author_kind == at.AUTEUR_INVITATION:
        v = at.ajouter_version(db, s, texte=texte, origine=at.HARMONISE, ia=True, sources=[],
                               faits=ag.faits_communs(faits), coupe=bool(base.coupe), base_version_id=base.id,
                               auteur_user_id=user_id, job_id=job_id, partage=True, ecrit_par=ag.ECRIT_PAR_CHEF,
                               compteurs=base.compteurs)
    else:
        v = at.ajouter_version(db, s, texte=texte, origine=at.HARMONISE, ia=True, sources=base.sources or [],
                               faits=faits, coupe=bool(base.coupe), base_version_id=base.id, auteur_user_id=user_id,
                               job_id=job_id)
    db.commit()
    return v
