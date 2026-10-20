"""
Adjugo — Membres et ÉTAT d'un groupement (co-traitance v2, source de vérité unique).

Avant cette vague, QUATRE notions de « membre » coexistaient (annuaire Cotraitant,
rattachement ProjectCotraitant, invitation ProjectInvite + contribution, profil réseau) et
13 requêtes filtraient `revoked` à la main : un partenaire qui DÉCLINE restait compté dans
la checklist, le cockpit, les CERFA… Ici, UNE définition :

    membre du groupement = invitation ACTIVE (revoked = false ET declined_at IS NULL)
                           + le mandataire (owner du projet)

Un ProjectCotraitant SANS invite_id est un CANDIDAT retenu (annuaire / SIRENE / simulation),
pas un membre. TOUT le code (checklist, cockpit, my_consortiums, cerfa, redaction, report,
export, convention, signatures) doit passer par `active_invites` / `active_invite_filter`.

L'ÉTAT du groupement n'est jamais stocké : `groupement_state()` le DÉRIVE des faits
(verdict, simulation retenue, invitations, parts, prix de lot, offre figée, convention,
dépôt). Rien à resynchroniser, impossible d'être incohérent.
"""
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Project, ProjectContribution, ProjectInvite


# ── Membres ──────────────────────────────────────────────────────────────────────────

def is_active_invite(inv) -> bool:
    """Une invitation compte comme membre si elle n'est ni révoquée ni déclinée."""
    return bool(inv) and not bool(getattr(inv, "revoked", False)) \
        and getattr(inv, "declined_at", None) is None


def active_invite_filter():
    """Condition SQLAlchemy réutilisable dans toute requête sur ProjectInvite
    (équivalent de l'ancien `ProjectInvite.revoked.is_(False)`, déclin inclus)."""
    return and_(ProjectInvite.revoked.is_(False), ProjectInvite.declined_at.is_(None))


def active_invites(db: Session, project_id: int) -> list:
    """Invitations ACTIVES d'un projet, dans l'ordre de création (= les membres)."""
    return db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id, active_invite_filter()
    ).order_by(ProjectInvite.created_at.asc()).all()


def active_invite_ids(db: Session, project_id: int) -> list:
    return [i.id for i in active_invites(db, project_id)]


# ── Qui entre dans les formulaires officiels (DC1, DC2, DC4, convention) ─────────────────
# Étude organisation, décision 4 : AUCUNE entreprise tierce n'entre dans un DC1/DC2 sans avoir accepté
# une invitation. Un rattachement au marché (ProjectCotraitant) ne suffit plus :
#   - sous-traitant (rôle « sous_traitant », déclaré EXPLICITEMENT par le candidat) → DC4 ;
#   - partenaire / chef de file → seulement si son invitation est active ET acceptée.

def invitation_acceptee(inv, contrib=None) -> bool:
    """Le partenaire a ACCEPTÉ l'invitation : depuis son compte (lien réclamé), par une réponse positive
    du réseau, ou en soumettant sa part. Une invitation seulement créée, envoyée ou ouverte ne suffit pas ;
    révoquée ou déclinée, jamais."""
    if not is_active_invite(inv):
        return False
    if getattr(inv, "accepted_by_user_id", None) or getattr(inv, "network_accepted_at", None):
        return True
    return contrib is not None and getattr(contrib, "status", "") == "submitted"


def _est_sous_traitant(role) -> bool:
    return str(role or "").strip().lower().replace("-", "_") == "sous_traitant"


_CHAMPS_FORMULAIRE = ("name", "siret", "code_ape", "forme_juridique", "representant_legal", "address",
                      "city", "postal_code", "email", "phone", "tva_intracom", "ca_n1", "ca_n2", "ca_n3",
                      "effectif", "specialites", "departement")


def nom_cle(s) -> str:
    """Nom d'entreprise comparable : sans accents, minuscules, espaces simples (même rapprochement
    que l'écran, qui compare les noms sans tenir compte de la casse)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(t.lower().split())


def etat_invitation(inv, contrib=None) -> Optional[str]:
    """« acceptee », « envoyee », « declinee », « retiree », ou None sans invitation."""
    if inv is None:
        return None
    if getattr(inv, "revoked", False):
        return "retiree"
    if getattr(inv, "declined_at", None) is not None:
        return "declinee"
    return "acceptee" if invitation_acceptee(inv, contrib) else "envoyee"


def _accords_hors_ligne(db: Session, project_id: int) -> dict:
    """{link_id: statut de son accord} des partenaires SANS invitation inscrits « hors ligne » sur une
    convention générée et à jour (« hors_ligne » = accord DÉCLARÉ recueilli par le chef de file, sinon
    « pending »). Seule exception à l'invitation acceptée : l'accord est déclaré par le chef de file
    (imprimé tel quel dans la convention), jamais présumé."""
    try:
        from app.services import groupement_convention as gc
        conv = gc.get_convention(db, project_id)
        if conv is None or conv.status not in gc.ACTIVE:
            return {}
        project = db.get(Project, project_id)
        if project is not None:
            gc.refresh(db, project, conv)          # texte périmé : les accords deviennent caducs
        if conv.status not in gc.ACTIVE:
            return {}
        return {s.cotraitant_link_id: s.status for s in gc.signatures_of(db, conv) if s.cotraitant_link_id}
    except Exception:
        return {}


def etat_des_liens(db: Session, project_id: int) -> dict:
    """{link_id: {"formulaires": bool, "invitation": état|None, "accord_hors_ligne": bool,
    "hors_ligne_en_attente": bool}} : le rattachement entre-t-il dans les formulaires officiels, et
    pourquoi ?
      - sous-traitant déclaré (DC4) : oui, sauf si l'invitation qu'il porte est déclinée ou retirée ;
      - partenaire : oui si son invitation est acceptée, ou si une AUTRE invitation acceptée de ce marché
        vise la même entreprise (même nom donné par le chef de file, ou même SIRET dans la part soumise :
        invitation créée sans lien, avant cette correction) ; ou si son accord hors ligne est déclaré
        sur la convention à jour ; non dans tous les autres cas."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id).all()
    if not links:
        return {}
    cts = {c.id: c for c in db.query(Cotraitant).filter(
        Cotraitant.id.in_([lk.cotraitant_id for lk in links] or [0])).all()}
    invs = {i.id: i for i in db.query(ProjectInvite).filter(ProjectInvite.project_id == project_id).all()}
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id).all()}
    # Invitations acceptées EN PARTENAIRE (un sous-traitant qui accepte n'entre pas au DC1 par ce biais).
    acceptees = [i for i in invs.values() if not _est_sous_traitant(i.role)
                 and invitation_acceptee(i, contribs.get(i.id))]
    noms_acceptes = {nom_cle(i.company_name) for i in acceptees if nom_cle(i.company_name)}
    sirets_acceptes = {str(getattr(contribs.get(i.id), "siret", "") or "").strip() for i in acceptees} - {""}
    hors_ligne = None
    out = {}
    for lk in links:
        inv = invs.get(getattr(lk, "invite_id", None))
        etat = etat_invitation(inv, contribs.get(inv.id) if inv is not None else None)
        hl = attente = False
        if _est_sous_traitant(lk.role):
            ok = etat not in ("declinee", "retiree")
        elif etat == "acceptee":
            ok = True
        else:
            ct = cts.get(lk.cotraitant_id)
            siret = str(getattr(ct, "siret", "") or "").strip()
            ok = bool(ct is not None and ((nom_cle(ct.name) and nom_cle(ct.name) in noms_acceptes)
                                          or (siret and siret in sirets_acceptes)))
            if ok:
                etat = "acceptee"
            elif inv is None:
                if hors_ligne is None:
                    hors_ligne = _accords_hors_ligne(db, project_id)
                hl = ok = hors_ligne.get(lk.id) == "hors_ligne"
                attente = lk.id in hors_ligne and not hl
        out[lk.id] = {"formulaires": bool(ok), "invitation": etat, "accord_hors_ligne": hl,
                      "hors_ligne_en_attente": attente}
    return out


def liens_dans_les_formulaires(db: Session, project_id: int) -> dict:
    """{link_id: bool} : le rattachement entre-t-il dans les formulaires officiels ? (cf. etat_des_liens)."""
    return {k: v["formulaires"] for k, v in etat_des_liens(db, project_id).items()}


def lien_a_inviter(db: Session, project_id: int, company_name: str, link_id: Optional[int] = None):
    """Rattachement du marché que concerne une NOUVELLE invitation : celui désigné par `link_id`, à
    défaut le seul rattachement de même nom d'entreprise. Jamais un sous-traitant, jamais un
    rattachement dont l'invitation est encore active (envoyée ou acceptée). None sinon."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    q = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id)
    if link_id:
        cands = q.filter(ProjectCotraitant.id == link_id).all()
    else:
        cle = nom_cle(company_name)
        if not cle:
            return None
        links = q.all()
        cts = {c.id: c for c in db.query(Cotraitant).filter(
            Cotraitant.id.in_([lk.cotraitant_id for lk in links] or [0])).all()}
        cands = [lk for lk in links if cts.get(lk.cotraitant_id) is not None
                 and nom_cle(cts[lk.cotraitant_id].name) == cle]
    libres = []
    for lk in cands:
        if _est_sous_traitant(lk.role):
            continue
        if lk.invite_id:
            cur = db.query(ProjectInvite).filter(ProjectInvite.id == lk.invite_id,
                                                 ProjectInvite.project_id == project_id).first()
            if cur is not None and is_active_invite(cur):
                continue
        libres.append(lk)
    return libres[0] if len(libres) == 1 else None


def cotraitants_pour_formulaires(db: Session, project_id: int) -> dict:
    """Entreprises rattachées au marché qui PEUVENT figurer dans les formulaires officiels, au format
    attendu par les générateurs (role/lot venant du rattachement). Renvoie {"lignes": [...],
    "ecartes": [noms], "hors_ligne_en_attente": [noms]} : les écartés (partenaires sans invitation
    acceptée) et les partenaires hors ligne dont l'accord n'est pas encore déclaré sont nommés pour
    un avertissement, jamais imprimés."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id).order_by(
        ProjectCotraitant.id.asc()).all()
    cts = {c.id: c for c in db.query(Cotraitant).filter(
        Cotraitant.id.in_([lk.cotraitant_id for lk in links] or [0])).all()}
    etats = etat_des_liens(db, project_id)
    lignes, ecartes, attente = [], [], []
    for lk in links:
        ct = cts.get(lk.cotraitant_id)
        if ct is None:
            continue
        e = etats.get(lk.id) or {}
        if not e.get("formulaires"):
            (attente if e.get("hors_ligne_en_attente") else ecartes).append(ct.name or "Partenaire")
            continue
        row = {k: (getattr(ct, k, "") or "") for k in _CHAMPS_FORMULAIRE}
        row["role"] = lk.role or "cotraitant"
        row["lot"] = lk.lot or ""
        lignes.append(row)
    return {"lignes": lignes, "ecartes": ecartes, "hors_ligne_en_attente": attente}


AVERT_SANS_ACCORD = ("{noms} : pas encore d'invitation acceptée, absent des formulaires officiels. "
                     "Invitez-le depuis la page du marché ; il y entrera quand il aura accepté.")
AVERT_HORS_LIGNE_EN_ATTENTE = ("{noms} : accord hors ligne pas encore déclaré, absent des formulaires officiels "
                               "(DC1, DC2). Cochez son accord dans la convention quand vous l'aurez recueilli.")


def avertissement_sans_accord(ecartes: list) -> str:
    """Phrase d'avertissement pour les entreprises écartées des formulaires (vide si aucune)."""
    noms = [n for n in (ecartes or []) if n]
    if not noms:
        return ""
    return AVERT_SANS_ACCORD.format(noms=", ".join(noms[:5]) + (" et d'autres" if len(noms) > 5 else ""))


def avertissements_formulaires(form: dict) -> list:
    """Avertissements à joindre à tout formulaire officiel produit (dossier, ZIP, formulaire seul) :
    qui n'y figure pas, et pourquoi. `form` = résultat de cotraitants_pour_formulaires."""
    out = []
    a = avertissement_sans_accord((form or {}).get("ecartes"))
    if a:
        out.append(a)
    attente = [n for n in ((form or {}).get("hors_ligne_en_attente") or []) if n]
    if attente:
        out.append(AVERT_HORS_LIGNE_EN_ATTENTE.format(noms=", ".join(attente[:5])))
    return out


def visible_contributions(db: Session, project_id: int, invites: list, viewer_invite_id: Optional[int] = None) -> dict:
    """{invite_id: part} des parts que le chef de file et les AUTRES membres peuvent lire. La part
    d'une invitation du RÉSEAU sans réponse (ou déclinée) en est retirée : brouillon saisi pendant
    l'aperçu minimal, que seul son auteur (`viewer_invite_id`) voit (invites._owner_hides_part).
    Elle est alors traitée comme absente : nom de l'invitation, aucun champ de la part (ni nom
    saisi, ni SIRET, ni adresse, ni représentant), statut « invité »."""
    from app.routers.invites import _owner_hides_part      # import local : pas de cycle
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id).all()}
    for inv in invites:
        c = contribs.get(inv.id)
        if c is not None and inv.id != viewer_invite_id and _owner_hides_part(inv, c):
            contribs.pop(inv.id)
    return contribs


def submitted_contributions(db: Session, project_id: int) -> list:
    """Parts SOUMISES des membres ACTIFS uniquement (jamais celles d'un partenaire révoqué
    ou qui a décliné) — base du mémoire fusionné, des CERFA, du ZIP, de la convention."""
    return db.query(ProjectContribution).join(
        ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
        ProjectContribution.project_id == project_id,
        ProjectContribution.status == "submitted",
        active_invite_filter()).all()


# ── État du groupement (dérivé) ───────────────────────────────────────────────────────
# Étapes, dans l'ordre du parcours « Répondre à plusieurs » :
STATES = ["seul", "potentiel", "composition", "invitation", "parts_completes",
          "convention_a_signer", "pret_a_deposer", "depose"]

STATE_LABELS = {
    "seul": "Analysé seul",
    "potentiel": "Bon potentiel en groupement",
    "composition": "Composition retenue",
    "invitation": "Partenaires invités",
    "parts_completes": "Toutes les parts reçues",
    "convention_a_signer": "Convention à valider",   # « accord enregistré », pas une signature électronique
    "pret_a_deposer": "Prêt à déposer",
    "depose": "Déposé",
}


def _plan(project) -> dict:
    p = getattr(project, "groupement_plan", None)
    return p if isinstance(p, dict) else {}


def groupement_state(project: Project, db: Session) -> dict:
    """Dérive l'étape courante du groupement et les compteurs utiles au stepper.

    Renvoie {state, label, index, members:[{invite_id, company, status, prix_lot_ht?}],
             n_members, n_submitted, n_with_price, offer_frozen, total_offre_ht,
             convention_status, warnings:[]}.
    - `members` : invitations actives (membres), avec le statut de leur part ;
      prix_lot_ht n'est inclus que si `include_prices=True` (vue mandataire) — ici on
      renvoie seulement un booléen `has_price` pour rester sûr par défaut.
    """
    plan = _plan(project)
    invites = active_invites(db, project.id)
    contribs = visible_contributions(db, project.id, invites)   # réseau sans réponse : part absente

    members, n_submitted, n_with_price = [], 0, 0
    for inv in invites:
        c = contribs.get(inv.id)
        submitted = bool(c and c.status == "submitted")
        has_price = bool(c and c.prix_lot_ht is not None)
        n_submitted += int(submitted)
        n_with_price += int(submitted and has_price)
        members.append({
            "invite_id": inv.id,
            "company": (c.company_name if c and c.company_name else inv.company_name) or "Partenaire",
            "role": inv.role or "cotraitant",
            "status": "submitted" if submitted else ("draft" if c else "invited"),
            "has_price": has_price,
            "viewed": bool(inv.view_count),
        })

    offre = plan.get("offre") if isinstance(plan.get("offre"), dict) else {}
    offer_frozen = bool(offre.get("frozen_at"))
    convention_status, convention = "", None   # vague 2 : lu depuis groupement_conventions
    conv = None
    try:
        from app.models import GroupementConvention, GroupementSignature
        conv = db.query(GroupementConvention).filter(
            GroupementConvention.project_id == project.id).first()
        convention_status = conv.status if conv else ""
        if conv is not None:
            active = conv.status in ("a_signer", "signee")
            sigs = db.query(GroupementSignature.status).filter(
                GroupementSignature.convention_id == conv.id).all() if active else []
            convention = {
                "id": conv.id, "status": conv.status, "version": conv.version or 0,
                "forme": conv.forme or "",
                "n_signataires": len(sigs),
                "n_accords": sum(1 for (s,) in sigs if s in ("signed", "hors_ligne")),
                "toutes_validees": conv.status == "signee",
                "frozen_at": conv.frozen_at.isoformat() if conv.frozen_at and active else None,
            }
    except Exception:
        convention_status, convention, conv = "", None, None

    status = getattr(project, "status", None)
    status_v = status.value if hasattr(status, "value") else str(status or "")
    decision = getattr(project, "go_decision", None) or ""
    # Composition RETENUE par le mandataire (POST /groupement/retenir) — un plan calculé
    # automatiquement à l'analyse (plan.auto=True) ne vaut pas composition : l'état reste
    # « potentiel » tant que l'utilisateur n'a rien choisi.
    retained = (not plan.get("auto")) and bool(plan.get("members")) and any(
        m.get("kind") != "lead" for m in (plan.get("members") or []) if isinstance(m, dict))

    n = len(invites)
    # Une convention générée peut ne compter que des partenaires « hors ligne » (rattachés
    # sans invitation) : le groupement existe alors même sans invitation active.
    has_members = bool(n) or convention_status in ("a_signer", "signee")
    if status_v in CLOSED_STATUSES and has_members:
        state = "depose"
    elif has_members and convention_status == "signee":
        state = "pret_a_deposer"
    elif has_members and convention_status in ("a_signer",):
        state = "convention_a_signer"
    elif n and n_submitted == n and n_with_price == n:
        state = "parts_completes"
    elif n:
        state = "invitation"
    elif retained:
        state = "composition"
    elif decision == "go_groupement" or plan.get("gaps"):
        state = "potentiel"
    else:
        state = "seul"

    warnings = list(plan.get("warnings") or []) if isinstance(plan.get("warnings"), list) else []
    label = STATE_LABELS.get(state, state)
    pret = None
    if state in ("pret_a_deposer", "depose") and conv is not None:
        pret = _pret_a_deposer(project, db, conv, invites)
        if state == "pret_a_deposer" and not pret["pret"]:
            label = "Convention validée — derniers contrôles avant dépôt"
    idx = STATES.index(state)
    return {
        "state": state, "label": label, "index": idx,
        "steps": [{"key": s, "label": STATE_LABELS[s]} for s in STATES],
        # Stepper « 1→5 » (étapes du parcours) — dérivé des 8 états ci-dessus.
        "etape": _etape_of(state), "etapes": _etapes(state),
        "members": members, "n_members": n, "n_submitted": n_submitted, "n_with_price": n_with_price,
        "offer_frozen": offer_frozen,
        "total_offre_ht": offre.get("total_ht") if offer_frozen else None,
        "frozen_at": offre.get("frozen_at") if offer_frozen else None,
        "convention_status": convention_status,
        "convention": convention,
        "pret": pret,
        "warnings": warnings,
    }


# Étapes du parcours (stepper 1→5) : regroupement des 8 états dérivés. L'ordre suit la
# machine à états : la convention (annexe de répartition) a besoin du prix de chaque part,
# donc « Réunir les parts » précède « Monter le groupement » — le brouillon de convention
# (forme, habilitation) peut toutefois être préparé dès l'étape 2.
ETAPES = [
    ("reperer", "Repérer le marché", ["seul", "potentiel"]),
    ("trouver", "Trouver les partenaires", ["composition", "invitation"]),
    ("reunir", "Réunir les parts", ["parts_completes"]),
    ("monter", "Monter le groupement", ["convention_a_signer"]),
    ("deposer", "Déposer", ["pret_a_deposer", "depose"]),
]


def _etape_of(state: str) -> int:
    for i, (_k, _l, states) in enumerate(ETAPES, start=1):
        if state in states:
            return i
    return 1


def _etapes(state: str) -> list:
    cur = _etape_of(state)
    out = []
    for i, (key, label, states) in enumerate(ETAPES, start=1):
        if i < cur or (state == "depose" and i == cur):
            st = "fait"
        elif i == cur:
            st = "en_cours"
        else:
            st = "a_faire"
        out.append({"n": i, "key": key, "label": label, "states": states, "status": st})
    return out


from app.models import STATUTS_DEPOSES as CLOSED_STATUSES   # « depose » (état 8) et au-delà (vague 2a)

# Contrôles de l'étape 5, dans l'ordre d'affichage (libellés pour le front et les emails).
DEPOT_CHECKS = [
    ("parts_soumises", "Parts de tous les partenaires soumises, avec leur prix de vente"),
    ("attestations_ok", "Attestations de tous les membres valides à la date limite"),
    ("convention_signee", "Convention validée par tous les membres"),
    ("cerfa_generes", "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention"),
]


def _naive(dt):
    if dt is not None and getattr(dt, "tzinfo", None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _fr_date(d) -> str:
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d or "")


def _lead_attestations(db: Session, project, deadline) -> tuple:
    """Attestations du CHEF DE FILE (membre du groupement) d'après son coffre-fort Adjugo (pièces
    de l'organisation, hors corbeille, sans projet ou rattachées à ce marché) : même classement et
    même règle de validité que pour les partenaires (coffre_croise). Renvoie (problèmes, absentes) :
    une pièce expirée ou qui expire avant la date limite est un MANQUE ; une pièce absente du
    coffre-fort n'est qu'un avertissement (le chef de file peut la gérer hors d'Adjugo)."""
    from datetime import date
    from app.core.org import member_ids
    from app.models import Document, User
    from app.routers.invites import (_EXPECTED_BASE, _PIECE_LABELS, _dce_requires_qualification,
                                     _piece_status, vault_doc_type)
    owner = db.get(User, project.user_id) if project.user_id else None
    if owner is None:
        return [], []
    ids = member_ids(owner, db)
    docs = db.query(Document).filter(
        Document.user_id.in_(ids), Document.parent_id.is_(None), Document.deleted_at.is_(None),
        (Document.project_id.is_(None)) | (Document.project_id == project.id)).limit(500).all()
    expected = list(_EXPECTED_BASE) + (["qualification"] if _dce_requires_qualification(project) else [])
    by_type = {}
    for d in docs:
        by_type.setdefault(vault_doc_type(d), []).append(d)
    problems, missing = [], []
    for key in expected:
        cands = by_type.get(key) or []
        label = _PIECE_LABELS.get(key, key)
        if not cands:
            missing.append(label)
            continue
        best = max(cands, key=lambda d: (d.expiration_date or date.max))
        status = _piece_status(best, deadline)
        if status == "expire":
            problems.append(f"Votre {label} (coffre-fort) a expiré")
        elif status == "expire_avant_limite":
            problems.append(f"Votre {label} (coffre-fort) expire avant la date limite")
    return problems, missing


def depot_readiness(project, db: Session, conv=None, invites: Optional[list] = None) -> dict:
    """« Prêt à déposer » (étape 5), FIABLE et calculable à tout moment (pas seulement quand la
    convention est validée) : parts soumises + attestations valides à la date limite + convention
    validée par tous + formulaires officiels DC1/DC2/ATTRI1 générés APRÈS la convention.

    Avertir, pas bloquer : renvoie {checks, libelles, pret, n_ok, n_total, pct, manques,
    avertissements} ; seul `pret` (les 4 contrôles) vaut « Prêt à déposer ». `pct` est conservé
    pour l'écran actuel : préférer « n_ok / n_total contrôles » (un seul pourcentage affiché dans
    le produit : le score de groupement)."""
    from datetime import date, datetime
    if invites is None:
        invites = active_invites(db, project.id)
    if conv is None:
        try:
            from app.models import GroupementConvention
            conv = db.query(GroupementConvention).filter(GroupementConvention.project_id == project.id).first()
        except Exception:
            conv = None
    checks, manques, avert = {}, [], []

    # 1) Parts : chaque co-traitant ACTIF a soumis sa part avec un prix de vente. Un sous-traitant
    #    n'est pas membre du groupement (DC4) : son retard est un avertissement, pas un manque.
    contribs = visible_contributions(db, project.id, invites)   # réseau sans réponse : part absente
    parts_ok = True
    for inv in invites:
        c = contribs.get(inv.id)
        name = (c.company_name if c and c.company_name else inv.company_name) or "Un partenaire"
        missing = None
        if not c or c.status != "submitted":
            missing = f"Part de {name} pas encore soumise"
        elif c.prix_lot_ht is None:
            missing = f"Part de {name} : prix de vente du lot manquant"
        if not missing:
            continue
        if (inv.role or "cotraitant") == "sous_traitant":
            avert.append(f"{missing} (sous-traitant : hors convention, utile pour le DC4)")
        else:
            parts_ok = False
            manques.append(missing)
    checks["parts_soumises"] = parts_ok

    # 2) Attestations de tous les membres, valides à la date limite (coffre-fort croisé).
    deadline = project.deadline
    if isinstance(deadline, datetime):
        deadline = deadline.date()
    if invites:
        try:
            from app.routers.invites import coffre_croise
            cc = coffre_croise(db, project, invites, viewer_invite_id=None, for_owner=True)
            checks["attestations_ok"] = bool(cc.get("all_complete"))
            if not checks["attestations_ok"]:
                # Toutes les alertes (l'écran en montre 3 puis « et N autres » : N doit être exact),
                # les attestations expirées ou expirant avant la date limite d'abord.
                items = list(cc.get("alert_items") or [])
                manques += [a["text"] for a in items if a.get("kind") != "a_fournir"]
                manques += [a["text"] for a in items if a.get("kind") == "a_fournir"]
        except Exception:
            checks["attestations_ok"] = False
            manques.append("Attestations des partenaires : vérification impossible pour l'instant")
    else:
        checks["attestations_ok"] = True       # aucun partenaire invité : rien à suivre ici
    # 2 bis) Le chef de file est membre du groupement : ses propres attestations comptent aussi.
    try:
        lead_problems, lead_missing = _lead_attestations(db, project, deadline)
    except Exception:
        lead_problems, lead_missing = [], []
        avert.append("Vos propres attestations n'ont pas pu être vérifiées pour l'instant : contrôlez "
                     "votre coffre-fort avant le dépôt")
    if lead_problems:
        checks["attestations_ok"] = False
        manques += lead_problems
    if lead_missing:
        avert.append("Vos propres attestations ne sont pas toutes dans votre coffre-fort Adjugo (absentes : "
                     + ", ".join(lead_missing) + ") : vérifiez-les vous-même avant le dépôt")
    hors_ligne = 0
    if conv is not None:
        try:
            from app.models import GroupementSignature
            hors_ligne = db.query(GroupementSignature).filter(
                GroupementSignature.convention_id == conv.id,
                GroupementSignature.cotraitant_link_id.isnot(None)).count()
        except Exception:
            hors_ligne = 0
    if hors_ligne:
        avert.append(f"{hors_ligne} partenaire(s) hors ligne : Adjugo ne suit pas leurs attestations, "
                     "vérifiez-les vous-même avant le dépôt")
    if deadline is None:
        avert.append("Date limite du marché inconnue : la validité des attestations est vérifiée à "
                     "aujourd'hui seulement")
    elif deadline < date.today():
        avert.append(f"La date limite du marché ({_fr_date(deadline)}) est dépassée")

    # 3) Convention validée par tous les membres.
    checks["convention_signee"] = bool(conv is not None and conv.status == "signee")
    if not checks["convention_signee"]:
        if conv is None or conv.status == "draft":
            manques.append("Convention de groupement à générer puis à faire valider par tous les membres")
        elif conv.status == "perimee":
            manques.append("Convention plus à jour : à régénérer puis à faire valider")
        else:
            manques.append("Convention à faire valider par tous les membres")

    # 4) Formulaires officiels générés APRÈS la (dernière) génération de la convention.
    try:
        from app.models import GeneratedDoc
        since = _naive(conv.frozen_at) if (conv is not None and conv.status in ("a_signer", "signee")) else None
        ok = True
        for dt in ("dc1", "dc2", "attri1"):
            g = db.query(GeneratedDoc).filter(GeneratedDoc.project_id == project.id,
                                              GeneratedDoc.doc_type == dt).first()
            stamp = _naive((g.updated_at or g.created_at) if g else None)
            fresh = bool(g) and g.status in ("pret", "signe") and since is not None \
                and stamp is not None and stamp >= since
            if not fresh:
                ok = False
                manques.append(f"Formulaire {dt.upper()} à (re)générer après la convention")
        checks["cerfa_generes"] = ok
    except Exception:
        checks["cerfa_generes"] = False

    ordered = {k: bool(checks.get(k)) for k, _label in DEPOT_CHECKS}
    n_ok = sum(1 for v in ordered.values() if v)
    return {
        "checks": ordered,
        "libelles": {k: label for k, label in DEPOT_CHECKS},
        "pret": n_ok == len(ordered),
        "n_ok": n_ok, "n_total": len(ordered),
        "pct": round(100 * n_ok / len(ordered)),
        "manques": manques,
        "avertissements": avert,
    }


def _pret_a_deposer(project, db: Session, conv, invites: list) -> dict:
    """Compatibilité (vague 2) : voir depot_readiness."""
    return depot_readiness(project, db, conv=conv, invites=invites)


def total_offre_ht(project: Project, db: Session, lead_total: Optional[float] = None) -> Optional[float]:
    """Total de l'offre commune = prix de lot de chaque membre (part soumise) + part du
    mandataire (estimate.total_ht ou valeur fournie). None si un membre n'a pas de prix."""
    parts = []
    for c in submitted_contributions(db, project.id):
        if c.prix_lot_ht is None:
            return None
        parts.append(float(c.prix_lot_ht))
    if lead_total is None:
        est = project.estimate if isinstance(project.estimate, dict) else {}
        try:
            lead_total = float(est.get("total_ht")) if est.get("total_ht") is not None else None
        except (TypeError, ValueError):
            lead_total = None
    if lead_total is not None:
        parts.append(float(lead_total))
    return round(sum(parts), 2) if parts else None
