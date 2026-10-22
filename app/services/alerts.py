"""
Alertes d'expiration des documents du coffre-fort.
Envoie un digest par utilisateur (escalade 30 j → 7 j → jour J),
en marquant les flags pour ne pas renvoyer deux fois la même alerte.
"""
import logging
import re
from app.schemas import safe_link_url as _safe_link
from datetime import date
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models import Document, SavedSearch, Company, User
from app.services.email import send_email

logger = logging.getLogger("adjugo")


def _demo_user_ids(db: Session) -> set:
    """Comptes démo publics (vitrine en lecture guidée) : AUCUN email ni appel IA ne part
    pour eux depuis les tâches planifiées — ni relance vers les partenaires fictifs des
    projets démo (adresses d'entreprises réelles possibles), ni digest, ni veille IA."""
    try:
        from sqlalchemy import func
        from app.services.demo_seed import DEMO_EMAIL
        return {uid for (uid,) in db.query(User.id).filter(
            func.lower(User.email) == DEMO_EMAIL).all()}
    except Exception:
        return set()


def _comptes_non_confirmes(db: Session) -> set:
    """Comptes dont l'adresse email n'est pas confirmée. LA notion unique des tâches planifiées.

    Vers un tiers (relecture de la vague 2b) : aucune tâche planifiée n'écrit à un tiers pour eux (rappel de la part,
    alerte d'attestations ; relance des parties du dossier de présentation, atelier_groupement.relancer_parts, depuis la
    contre-relecture), comme l'invitation elle-même, qui ne part par courriel que si l'expéditeur a confirmé son adresse
    (anti-spam par comptes jetables, invites._create_invite) — sinon le rappel planifié, qui porte le lien, devenait
    l'invitation complète envoyée à la place du compte.

    Vers le compte lui-même (réunion du 22/10, décision 2 : une seule règle) : aucun courriel planifié vers une adresse
    non confirmée, qui peut être celle d'un tiers (faute de frappe au changement d'adresse) — ni alerte de marchés
    (run_tender_alerts, moteur lot 1), ni « Demandez vos notes » (carnet_notes.envoyer_rappels), ni récapitulatif
    « pièces à renouveler » (run_document_expiry_alerts), ni récapitulatif des attestations des partenaires
    (_piece_alerts_due), ni veille amont (run_amont_alerts, masquée aujourd'hui). Rien n'y est marqué envoyé ni « déjà
    vu » : ils partent au premier passage après la confirmation (« Demandez vos notes » seulement dans ses 14 jours,
    carnet_notes.COURRIEL_FIN_JOURS ; la veille amont, avec les délibérations qu'elle lit à ce passage). Les comptes
    d'avant la vérification d'email ont été confirmés par sa migration (j4k5l6m7n8o9)."""
    try:
        from sqlalchemy import or_
        return {uid for (uid,) in db.query(User.id).filter(
            or_(User.email_verified.is_(None), User.email_verified == False)).all()}   # noqa: E712
    except Exception:
        return set()


def _due_alert(doc, days: int, today=None):
    """Retourne (label, flags_à_marquer) pour l'alerte due, ou None. Paliers : 30 jours, 7 jours, le jour même (et
    après). Le libellé est celui de la liste de Mes documents (app.services.pieces_fin.etat_fin), en minuscule."""
    from app.services.pieces_fin import ALERTE_JOURS, etat_fin
    fin = etat_fin(doc.expiration_date, today) if getattr(doc, "expiration_date", None) else None
    libelle = (fin["libelle"] if fin else "")
    libelle = (libelle[:1].lower() + libelle[1:]) if libelle else ""
    if days <= 0 and not doc.alert_day_sent:
        return (libelle or ("expire aujourd'hui" if days == 0 else "expirée"),
                ["alert_day_sent", "alert_7_sent", "alert_30_sent"])
    if days <= 7 and not doc.alert_7_sent:
        return (libelle or f"expire dans {days} jours", ["alert_7_sent", "alert_30_sent"])
    if days <= ALERTE_JOURS and not doc.alert_30_sent:
        return (libelle or f"expire dans {days} jours", ["alert_30_sent"])
    return None


from app.models import STATUTS_CLOS as _CLOSED      # marché déposé ou clos : plus de relance (vague 2a : « depose »)


def _status_value(project) -> str:
    st = getattr(project, "status", None)
    return st.value if hasattr(st, "value") else str(st or "")


def _fr(d) -> str:
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d or "")


def run_cotraitance_reminders(db: Session) -> dict:
    """Relance les partenaires invités qui n'ont PAS soumis leur part, à l'approche de la
    date limite. Idempotent par palier (reminder_stage : 1 = J-3 envoyée, 2 = J-1 envoyée)
    → un partenaire reçoit au plus une relance par palier. Process unique sans Redis :
    appelé par cron (POST /api/admin/run-cotraitance-reminders).

    Sans doublon (vague 4) : si le même partenaire a aussi des attestations à mettre à jour
    (coffre croisé, paliers J-7 / J-3), elles sont AJOUTÉES à cette relance (un seul email) et
    l'alerte d'attestations du jour n'en renvoie pas un second. De même, ses parties du dossier de
    présentation à relancer ce jour (rédaction, vague 4) sont ajoutées à ce rappel, et la relance des
    parties ne lui écrit pas une seconde fois. Plus aucune relance une fois le marché marqué déposé
    (statut envoyé) ou clos."""
    from datetime import datetime, timezone
    from app.models import Project, ProjectInvite, ProjectContribution, Company

    def _is_email(v):
        return bool(v) and "@" in str(v) and "." in str(v).split("@")[-1]

    from app.services.groupement_members import active_invite_filter

    today = datetime.now(timezone.utc).date()
    try:
        piece_due = _piece_alerts_due(db, today)
    except Exception as e:
        logger.warning("relances co-traitance : calcul des attestations impossible : %s", e)
        piece_due = []
    pieces_by_invite = {a["inv"].id: a for a in piece_due}
    merged = set()
    # Rédaction, vague 4 : les parties du dossier de présentation à relancer ce jour, ajoutées au rappel de la part
    # du MÊME partenaire (un seul email) ; les autres partent ensuite par relancer_parts.
    try:
        from app.services.atelier_groupement import lignes_relance, parts_a_relancer
        parts_due = parts_a_relancer(db, today)
    except Exception as e:
        logger.warning("relances co-traitance : parties du dossier de présentation non lues : %s", e)
        db.rollback()
        parts_due, lignes_relance = {}, None
    parts_merged = set()
    from app.core.config import get_settings
    from app.services.email_invitation import rappel_part
    base_url = (get_settings().APP_BASE_URL or "").rstrip("/")
    invites = db.query(ProjectInvite).filter(
        active_invite_filter(),
        ProjectInvite.can_contribute.is_(True)).all()
    scanned, reminded = 0, 0
    demo_ids = _demo_user_ids(db)
    non_confirmes = _comptes_non_confirmes(db)
    for inv in invites:
        # Jamais pour la démonstration ; jamais pour un chef de file dont l'adresse n'est pas confirmée.
        if not _is_email(inv.recipient) or inv.owner_id in demo_ids or inv.owner_id in non_confirmes:
            continue
        project = db.query(Project).filter(Project.id == inv.project_id,
                                           Project.deleted_at.is_(None)).first()
        if not project or not project.deadline or _status_value(project) in _CLOSED:
            continue
        # deadline peut être un date OU un datetime selon les enregistrements → on normalise.
        deadline = project.deadline
        deadline_date = deadline.date() if isinstance(deadline, datetime) else deadline
        days_left = (deadline_date - today).days
        if days_left < 0:
            continue   # échéance passée : plus de relance
        # Part déjà soumise ? pas de relance.
        c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
        if c and c.status == "submitted":
            continue
        scanned += 1
        # Palier à envoyer : J-1 (stage 2) prioritaire, sinon J-3 (stage 1).
        stage = inv.reminder_stage or 0
        target = None
        if days_left <= 1 and stage < 2:
            target = 2
        elif days_left <= 3 and stage < 1:
            target = 1
        if not target:
            continue
        company = db.query(Company).filter(Company.user_id == inv.owner_id).first()
        # Vague 2b (B4) : rappel en HTML avec sa version texte (app/services/email_invitation.py), qui mène à
        # « Votre part dans [marché] » par le lien de l'invitation (avant : « via votre lien Adjugo », sans lien).
        # « au groupement de Breizh Couverture » / « du chef de file » (jamais « de le chef de file »).
        extra = pieces_by_invite.get(inv.id)
        parts = parts_due.get(inv.id) if lignes_relance else None
        mail = rappel_part(chef=(company.name if company else "") or "", marche=project.name,
                           url=(f"{base_url}/invite/{inv.token}" if base_url else ""), date_limite=deadline_date,
                           jours_restants=days_left, attestations=(extra["problems"] if extra else ()),
                           parties=(lignes_relance(parts) if parts else ()))
        if send_email(inv.recipient, mail["objet"], mail["texte"], html=mail["html"]):
            inv.reminder_stage = target
            reminded += 1
            if extra:
                merged.add(inv.id)
            if parts:
                for _s, r, c, _p in parts:
                    r.relance_palier = c
                parts_merged.add(inv.id)
    db.commit()
    pieces_alerted = _run_piece_expiry_alerts(db, today, due=piece_due, merged=merged)
    result = {"scanned": scanned, "reminded": reminded, "pieces_alerted": pieces_alerted,
              "pieces_merged": len(merged), "parts_fusionnees": len(parts_merged)}
    # Rédaction, vague 4 : parties du dossier de présentation pas encore envoyées, à J-2 puis le jour de
    # leur date limite interne (un palier par partie, jamais deux fois ; jamais un second email au partenaire
    # dont le rappel ci-dessus les portait déjà).
    try:
        from app.services.atelier_groupement import relancer_parts
        result.update(relancer_parts(db, today, deja=parts_merged, non_confirmes=non_confirmes))
    except Exception as e:
        db.rollback()
        logger.warning("relances co-traitance : parts du dossier de présentation non relancées : %s", e)
    logger.info("relances co-traitance : %s", result)
    return result


def _piece_window_start(deadline_date, palier: str):
    """Début de la fenêtre d'un palier pour CETTE date limite (J-7 ou J-3) : une alerte déjà
    journalisée depuis ce jour vaut pour tout le palier (et non pour la seule journée)."""
    from datetime import datetime, timedelta
    d = deadline_date - timedelta(days=3 if palier == "J-3" else 7)
    return datetime(d.year, d.month, d.day)


def _piece_alerts_due(db: Session, today) -> list:
    """Alertes d'attestations DUES (coffre-fort croisé) : à J-7 puis J-3 de la date limite, chaque
    membre dont une attestation est MANQUANTE ou EXPIRE AVANT la date limite. Une seule alerte
    par (invitation, palier, date limite) : l'entrée AuditLog `piece.expiring` (invite_id +
    detail « J-7 … » / « J-3 … ») posée depuis le début du palier vaut pour tout le palier —
    auparavant l'alerte repartait CHAQUE JOUR du palier (doublons). Ne lève jamais."""
    from datetime import datetime, timedelta
    from app.models import AuditLog, Project, Company, User
    from app.services.groupement_members import active_invites
    try:
        from app.routers.invites import coffre_croise, _PIECE_LABELS, tenant_owner_id
    except Exception:
        return []

    def _is_email(v):
        return bool(v) and "@" in str(v) and "." in str(v).split("@")[-1]

    out = []
    horizon = today + timedelta(days=7)
    try:
        projects = db.query(Project).filter(
            Project.deleted_at.is_(None), Project.deadline.isnot(None),
            Project.deadline >= today, Project.deadline <= horizon).all()
    except Exception:
        return []
    demo_ids = _demo_user_ids(db)
    non_confirmes = _comptes_non_confirmes(db)
    labels = dict(_PIECE_LABELS)
    for project in projects:
        if project.user_id in demo_ids or _status_value(project) in _CLOSED:
            continue
        invites = active_invites(db, project.id)
        if not invites:
            continue
        deadline = project.deadline
        deadline_date = deadline.date() if isinstance(deadline, datetime) else deadline
        days_left = (deadline_date - today).days
        palier = "J-3" if days_left <= 3 else "J-7"
        window = _piece_window_start(deadline_date, palier)
        try:
            grid = coffre_croise(db, project, invites, viewer_invite_id=None, for_owner=True)
        except Exception:
            continue
        owner_user = db.query(User).filter(User.id == project.user_id).first()
        # Une adresse non confirmée ne reçoit rien (elle peut être celle d'un tiers, posée sur un compte jetable).
        owner_email = (owner_user.email if owner_user and _is_email(owner_user.email)
                       and owner_user.id not in non_confirmes else None)
        # Propriétaire CANONIQUE du tenant (porteur du profil entreprise et de la chaîne
        # d'audit) — jamais project.user_id brut si un membre a créé le marché.
        tenant_oid = tenant_owner_id(project, db)
        if tenant_oid in non_confirmes:
            continue                # chef de file sans adresse confirmée : aucune alerte vers ses partenaires
        company = (db.query(Company).filter(Company.user_id == tenant_oid).first()
                   or db.query(Company).filter(Company.user_id == project.user_id).first())
        du_chef = f"de {company.name}" if company and company.name else "du chef de file"
        by_id = {i.id: i for i in invites}
        for m in grid.get("members", []):
            inv = by_id.get(m.get("invite_id"))
            if not inv:
                continue
            problems = []
            for key, st in (m.get("pieces") or {}).items():
                s_ = st.get("status")
                if s_ == "manquant":
                    problems.append(f"{labels.get(key, key)} à fournir")
                elif s_ == "expire_avant_limite":
                    exp = st.get("expiration_date")
                    try:
                        exp = _fr(datetime.fromisoformat(exp).date()) if exp else exp
                    except Exception:
                        pass
                    problems.append(f"{labels.get(key, key)} expire le {exp} (avant la date limite)")
                elif s_ == "expire":
                    problems.append(f"{labels.get(key, key)} a expiré")
            if not problems:
                continue
            already = db.query(AuditLog.id).filter(
                AuditLog.invite_id == inv.id, AuditLog.action == "piece.expiring",
                AuditLog.detail.like(f"{palier}%"), AuditLog.created_at >= window).first()
            if already:
                continue
            out.append({"project": project, "deadline_date": deadline_date, "palier": palier,
                        "inv": inv, "who": m.get("company") or inv.company_name or "Partenaire",
                        "problems": problems, "du_chef": du_chef, "owner_email": owner_email,
                        "tenant_oid": tenant_oid})
    return out


def _run_piece_expiry_alerts(db: Session, today, due=None, merged=None) -> int:
    """Coffre-fort croisé (E) : envoie les alertes d'attestations dues (voir _piece_alerts_due) —
    un email au membre (sauf si son alerte a déjà été jointe à sa relance de part, `merged`) et
    UN récapitulatif par marché au mandataire (plus un email par partenaire). Journalise
    `piece.expiring` (visible du membre). Best-effort : aucune exception ne remonte au cron."""
    from app.services import audit

    def _is_email(v):
        return bool(v) and "@" in str(v) and "." in str(v).split("@")[-1]

    if due is None:
        try:
            due = _piece_alerts_due(db, today)
        except Exception:
            return 0
    merged = set(merged or ())
    alerted = 0
    by_project = {}
    from app.core.config import get_settings
    base_url = (get_settings().APP_BASE_URL or "").rstrip("/")
    for a in due:
        inv, project = a["inv"], a["project"]
        lines = "\n".join(f"- {p}" for p in a["problems"])
        if _is_email(inv.recipient) and inv.id not in merged:
            # Vague 2b (B4) : l'espace du partenaire est « Votre part dans [marché] » ; le lien de l'invitation y mène.
            ou = (f"depuis votre part dans ce marché :\n{base_url}/invite/{inv.token}" if base_url
                  else "depuis votre part dans ce marché (votre lien d'invitation).")
            send_email(
                inv.recipient,
                f"Attestations à mettre à jour avant le {_fr(a['deadline_date'])} — {project.name[:50]}",
                f"Bonjour,\n\nPour le marché « {project.name} » (date limite : {_fr(a['deadline_date'])}), "
                f"le groupement {a['du_chef']} a besoin de vos attestations à jour :\n{lines}\n\n"
                f"Déposez-les {ou}\n\n— Adjugo")
        # Chaîné sous le propriétaire du tenant (sinon l'entrée sortait de la chaîne
        # d'intégrité de l'entreprise quand un membre a créé le marché).
        audit.record(db, action="piece.expiring", owner_id=a["tenant_oid"], project_id=project.id,
                     actor="adjugo", actor_kind="system", target_type="invite", target_id=inv.id,
                     detail=f"{a['palier']} (date limite {_fr(a['deadline_date'])})", invite_id=inv.id)
        alerted += 1
        by_project.setdefault(project.id, []).append(a)
    for alerts in by_project.values():
        a0 = alerts[0]
        if not a0["owner_email"]:
            continue
        project = a0["project"]
        blocks = "\n\n".join(f"{a['who']} :\n" + "\n".join(f"- {p}" for p in a["problems"]) for a in alerts)
        n = len(alerts)
        send_email(
            a0["owner_email"],
            f"{n} partenaire{'s' if n > 1 else ''} : attestation(s) à surveiller — {project.name[:50]}",
            f"Bonjour,\n\nSur le marché « {project.name} » (date limite : {_fr(a0['deadline_date'])}), "
            f"des pièces ne sont pas prêtes pour le dépôt :\n\n{blocks}\n\n"
            f"Les partenaires concernés ont été prévenus. Suivez leurs pièces sur la page de ce marché, "
            f"dans Adjugo.\n\n— Adjugo")
    return alerted


def run_document_expiry_alerts(db: Session) -> dict:
    # Jour de Paris et libellés de la liste : le courriel dit la même chose que Mes documents (app.services.pieces_fin).
    from app.services.pieces_fin import jour_paris, jj_mm_aaaa
    today = jour_paris()
    docs = db.query(Document).filter(
        Document.expiration_date.isnot(None),
        Document.parent_id.is_(None),
        Document.deleted_at.is_(None),
    ).all()

    by_user = defaultdict(list)   # user -> [(doc, days, label, flags)]
    scanned = 0
    for doc in docs:
        scanned += 1
        days = (doc.expiration_date - today).days
        due = _due_alert(doc, days, today)
        if due:
            label, flags = due
            by_user[doc.user].append((doc, days, label, flags))

    notified, alerts = 0, 0
    demo_ids = _demo_user_ids(db)
    # Réunion du 22/10, décision 2 (une seule règle pour les courriels planifiés vers le compte lui-même) : rien vers une
    # adresse non confirmée. Aucun drapeau n'est posé : le récapitulatif part au premier passage après la confirmation,
    # avec les pièces dues ce jour-là (palier du jour, _due_alert).
    non_confirmes = _comptes_non_confirmes(db)
    for user, items in by_user.items():
        if not user or not user.email or user.id in demo_ids or user.id in non_confirmes:
            continue
        lines = [f"• {d.name} : {label} (date de fin : {jj_mm_aaaa(d.expiration_date)})" for d, _, label, _ in items]
        n = len(items)
        un = n == 1
        text = ("Bonjour,\n\n" + ("Une pièce de Mes documents arrive à sa date de fin :" if un
                                  else "Des pièces de Mes documents arrivent à leur date de fin :")
                + "\n\n" + "\n".join(lines) + "\n\n" + ("Remplacez-la" if un else "Remplacez-les")
                + " dans Adjugo (Mes documents) avant vos prochains dépôts : une attestation périmée "
                "peut faire écarter une candidature.\n\n— Adjugo")
        sent = send_email(user.email, f"Adjugo — {n} {'pièce à renouveler' if n == 1 else 'pièces à renouveler'}", text)
        # On ne marque les flags que si l'email est parti, pour pouvoir rejouer
        # une fois le SMTP configuré.
        if sent:
            for doc, _, _, flags in items:
                for f in flags:
                    setattr(doc, f, True)
            notified += 1
            alerts += len(items)
    db.commit()
    result = {"scanned": scanned, "users_notified": notified, "alerts_sent": alerts}
    logger.info("alertes expiration : %s", result)
    return result


# ── Veille AO : alertes sur recherches sauvegardées ──────────────────────────────

# Mémoire des marchés déjà vus, par alerte (last_seen_refs) : UNE entrée par marché, ses références jointes par
# _SEP_REFS ; ordre gardé, du plus ancien au plus récent ; 500 marchés au plus, comme avant le lot 1.
_REFS_GARDEES = 500
_SEP_REFS = " + "            # absent des références (chiffres, tirets), des clés de fusion et des noms de source
# Courriel : 10 marchés au plus par alerte (décision 11 : « comme aujourd'hui »), le reste est compté.
_MARCHES_PAR_ALERTE = 10


def _jetons(entree) -> list:
    """Les références d'une entrée de la mémoire (une entrée ancienne n'en a qu'une, nue)."""
    return [j for j in str(entree or "").split(_SEP_REFS) if j]


def _memoriser(deja: list, vus: list) -> list:
    """Nouvelle mémoire : chaque marché vu à ce passage passe en fin de liste, avec toutes ses références (celles
    d'aujourd'hui et celles de son entrée précédente, forme ancienne comprise) ; les autres entrées gardent leur
    ordre. `vus` : [(références nouvelles, toutes ses clés)] dans l'ordre de la recherche."""
    entrees = list(deja)
    for nouvelles, cles in vus:
        gardees, jetons = [], list(nouvelles)
        for e in entrees:
            je = _jetons(e)
            if cles.intersection(je):
                jetons += je            # la même entrée : fusionnée, jamais comptée deux fois
            else:
                gardees.append(e)
        entrees = gardees + [_SEP_REFS.join(dict.fromkeys(jetons))]
    return entrees


def _refs_du_marche(t) -> tuple:
    """(références nouvelles, références anciennes) d'un marché trouvé (lot 1, point 6).

    Nouvelle forme : « SOURCE|référence », pour l'avis lui-même ET pour chaque source où le même marché a été vu
    (also_seen_in) : un marché fusionné BOAMP + Mégalis n'est pas renvoyé le jour où l'ordre des sources change,
    et un numéro de consultation Mégalis égal à un numéro d'avis BOAMP ne masque plus un autre marché. Sans
    référence officielle, la clé de fusion (objet, acheteur, date limite) préfixée par la source.
    Rectificatifs du BOAMP rattachés à l'avis (chantier Sources) : leurs références sont celles du même marché.
    Avant le lot 1, un rectificatif au format européen était une carte à part, sous sa propre référence ; une
    alerte qui l'a déjà envoyé ne renvoie donc pas l'avis qui le porte maintenant (réunion des chantiers).
    Forme ancienne (avant le lot 1, gardée en mémoire par les alertes en service) : la référence nue, ou la clé
    nue ; elle reste reconnue pour ne rien renvoyer deux fois."""
    nouvelles, anciennes = [], []
    for prov in ([t.provenance] + list(getattr(t, "also_seen_in", None) or [])
                 + list(getattr(t, "rectificatifs", None) or [])):
        ref = (getattr(prov, "official_ref", "") or "").strip()
        src = (getattr(prov, "source", "") or "").strip() or "?"
        if ref:
            nouvelles.append(f"{src}|{ref}")
            anciennes.append(ref)
        elif t.dedup_key:
            nouvelles.append(f"{src}|{t.dedup_key}")
    if t.dedup_key:
        anciennes.append(t.dedup_key)
    return list(dict.fromkeys(nouvelles)), list(dict.fromkeys(anciennes))


def run_one_saved_search(s: SavedSearch, db: Session, mark: bool = True) -> list:
    """Rejoue UNE recherche sauvegardée, renvoie les NOUVEAUX marchés (non déjà notifiés), dans l'ordre de
    la recherche. Décision 11 (lot 1) : plus AUCUN marché écarté à cause de sa note calculée avant le dossier
    (le seuil reviendra réglable et annoncé, avec le barème corrigé). Met à jour last_run / last_seen_refs
    si mark."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.routers.sourcing import _tender_sources
    from app.services.profile import company_dict, criteria_dict
    from app.models import utcnow

    company = db.query(Company).filter(Company.user_id == s.user_id).first()
    gonogo = criteria_dict(s.user_id, db)
    countries = s.countries or []
    crit = TenderCriteria(query=s.query or "", cpv=s.cpv or [],
                          departements=s.departements or [], countries=countries,
                          montant_min=s.montant_min, montant_max=s.montant_max, limit=25,
                          type_marche=getattr(s, "type_marche", "") or "")
    try:
        result = TenderSearchService(_tender_sources(countries)).search(crit, company_dict(company), gonogo)
    except Exception as e:
        logger.warning("veille : recherche %s en échec : %s", s.id, e)
        return []

    deja = [e for e in (s.last_seen_refs or []) if isinstance(e, str) and e]
    seen = {j for e in deja for j in _jetons(e)}
    fresh, vus = [], []
    for t in result["tenders"]:
        nouvelles, anciennes = _refs_du_marche(t)
        if not nouvelles:
            continue
        cles = set(nouvelles) | set(anciennes)
        vus.append((nouvelles, cles))
        if cles & seen:
            continue
        seen |= cles                    # un même marché rendu deux fois par la recherche n'est listé qu'une fois
        # « ref » : la référence de l'avis telle qu'avant le lot 1 (rendue par « Tester » une alerte, API
        # inchangée) ; la forme « SOURCE|référence » ne sert qu'à la mémoire (last_seen_refs).
        fresh.append({
            "objet": t.objet, "acheteur": t.acheteur, "score": t.score.total if t.score else 0,
            "date_limite": t.date_limite, "lieu": t.lieu,
            "source": t.provenance.source, "url": t.provenance.source_url,
            "ref": t.provenance.official_ref or t.dedup_key,
        })

    if mark:
        # Tous les marchés vus sont mémorisés, une entrée par marché. L'ordre est GARDÉ (plus ancien d'abord) et un
        # marché encore présent repasse en fin de liste : seuls les marchés les plus anciens, que la recherche ne
        # rend plus, sortent de la mémoire. Avant le lot 1, la liste repassait par un ensemble et la coupe à 500
        # retirait des références au hasard, dont celles de marchés encore ouverts, renvoyés ensuite.
        s.last_seen_refs = _memoriser(deja, vus)[-_REFS_GARDEES:]
        s.last_run = utcnow()
    return fresh


def _jour_paris_de(moment):
    """Jour de Paris d'un horodatage enregistré en UTC (naïf ou non)."""
    from datetime import timezone
    from app.services.pieces_fin import _tz_paris
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    tz = _tz_paris()
    return moment.astimezone(tz).date() if tz is not None else moment.date()


def _hebdomadaire_pas_encore_due(s: SavedSearch, aujourdhui) -> bool:
    """« Hebdomadaire » réellement appliqué (lot 1, point 6) : une alerte hebdomadaire déjà servie repart
    7 jours de Paris après son dernier passage, quelle que soit l'heure de l'appel programmé. Jamais servie :
    elle part au premier passage."""
    if (s.frequency or "") != "hebdomadaire" or not s.last_run:
        return False
    try:
        return (aujourdhui - _jour_paris_de(s.last_run)).days < 7
    except Exception:           # horodatage illisible : on sert l'alerte plutôt que de la taire
        return False


def run_tender_alerts(db: Session) -> dict:
    """Cron veille : rejoue toutes les recherches actives et envoie un digest par user."""
    searches = db.query(SavedSearch).filter(SavedSearch.active.is_(True)).all()
    # On ne marque « déjà vu » QUE pour les users joignables par email : sinon les marchés d'un
    # user sans email étaient marqués vus puis jamais notifiés (perdus quand il ajoute son email).
    # Joignable = adresse CONFIRMÉE (relecture du lot 1) : une adresse jamais confirmée peut être celle d'un tiers,
    # et la décision 11 (plus aucun marché écarté par sa note) multipliait les courriels vers elle. Rien n'est
    # perdu : sans marquer « déjà vu », ces marchés partent au premier passage après la confirmation. Les comptes
    # d'avant la vérification des adresses sont confirmés (migration j4k5l6m7n8o9). Réunion du 22/10 : les comptes non
    # confirmés sont ceux de _comptes_non_confirmes, la même notion que les rappels de co-traitance (vague 2b).
    emailed = ({uid for (uid,) in db.query(User.id).filter(User.email.isnot(None)).all()}
               - _comptes_non_confirmes(db))
    by_user = defaultdict(list)   # user_id -> [(search_name, [tenders])]
    demo_ids = _demo_user_ids(db)
    from app.services.pieces_fin import jour_paris
    aujourdhui, en_attente = jour_paris(), 0
    for s in searches:
        if s.frequency == "manuelle" or s.user_id in demo_ids:
            continue
        if _hebdomadaire_pas_encore_due(s, aujourdhui):
            en_attente += 1
            continue
        has_email = s.user_id in emailed
        fresh = run_one_saved_search(s, db, mark=has_email)
        if fresh and has_email:
            by_user[s.user_id].append((s.name, fresh))

    notified, total = 0, 0
    for user_id, blocks in by_user.items():
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.email or not user.email_verified:
            continue
        lines = ["Bonjour,\n\nVotre veille Adjugo a repéré de nouveaux appels d'offres :\n"]
        for name, tenders in blocks:
            lines.append(f"\n● {name} ({len(tenders)} nouveau(x)) :")
            for t in tenders[:_MARCHES_PAR_ALERTE]:
                ech = f" — clôture {t['date_limite']}" if t.get("date_limite") else ""
                # Décision 8 (réorganisation) : pas de note sur 100 avant le dossier du marché ; l'ordre de la
                # liste (le plus adapté d'abord) suffit. Ce que promet la vitrine : objet, acheteur, date limite, lien.
                lines.append(f"   • {t['objet'][:90]} — {t.get('acheteur') or 'acheteur n/d'}{ech}\n     {t['url']}")
            reste = len(tenders) - _MARCHES_PAR_ALERTE
            if reste > 0:
                # Rien n'est caché en silence (moteur § 7, règle 8) : les marchés au-delà des 10 premiers sont comptés.
                lines.append(f"   … et {reste} {'autre marché' if reste == 1 else 'autres marchés'} : relancez cette "
                             "recherche dans Adjugo pour les voir tous.")
            total += len(tenders)
        lines.append("\n\nConnectez-vous à Adjugo pour les analyser.\n\n— Adjugo")
        if send_email(user.email, f"Adjugo — {sum(len(t) for _, t in blocks)} nouvel(s) appel(s) d'offres", "\n".join(lines)):
            notified += 1
    db.commit()
    result = {"searches_run": len(searches), "users_notified": notified, "new_matches": total,
              "weekly_not_due": en_attente}
    # Rédaction, vague 6 (F) : rappel « Demandez vos notes » 2 jours après le passage à « Perdu », par courriel
    # seulement aux utilisateurs qui ont des alertes actives (une fois par marché, jamais à l'acheteur) et, depuis la
    # réunion du 22/10 (décision 2), une adresse confirmée, comme l'alerte de marchés ci-dessus.
    try:
        from app.services.carnet_notes import envoyer_rappels
        result.update(envoyer_rappels(db))
    except Exception as e:      # noqa: BLE001 — la veille ne casse jamais pour ce rappel
        db.rollback()
        logger.warning("rappels « Demandez vos notes » en échec : %s", type(e).__name__)
    logger.info("alertes veille AO : %s", result)
    return result


def _num_or_none(v):
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def run_amont_alerts(db: Session) -> dict:
    """Cron VEILLE AMONT : Adjugo va chercher les délibérations récentes, l'IA détecte
    les projets d'investissement (une fois), puis chaque utilisateur reçoit ses nouveaux
    projets PERTINENTS par email (scoring selon son profil)."""
    # « Projets à venir » masqué (PROJETS_A_VENIR=0) jusqu'à la vague 1 de l'étude veille : aucun scan,
    # aucun appel à l'IA, aucun courriel. Les abonnements (amont_alerts_enabled) et signaux sont gardés.
    from app.core.interrupteurs import projets_a_venir_actif
    if not projets_a_venir_actif():
        return {"scanned": 0, "users_notified": 0, "new_signals": 0, "desactive": True}
    from app.sourcing.sources.deliberations import DeliberationSource
    from app.services.agents.amont import detect_from_deliberations, score_pertinence
    from app.services.profile import criteria_dict
    from app.models import Signal

    # Personne n'a activé la veille auto → aucun scan (zéro appel IA inutile). Un compte dont l'essai
    # est terminé sans forfait n'est pas servi : les fonctions d'IA sont en pause (quota.exiger_ia).
    # Réunion du 22/10, décision 2 : une adresse non confirmée n'est pas servie (aucun courriel, aucun projet enregistré
    # pour elle) ; elle l'est au premier passage après la confirmation, avec les délibérations que la veille lit alors.
    from app.core.quota import _billing_user, essai_termine
    demo_ids = _demo_user_ids(db)
    non_confirmes = _comptes_non_confirmes(db)
    opted = [u for u in db.query(User).filter(User.email.isnot(None),
                                              User.amont_alerts_enabled.is_(True)).all()
             if u.id not in demo_ids and u.id not in non_confirmes and not essai_termine(_billing_user(u, db))]
    if not opted:
        return {"scanned": 0, "users_notified": 0, "new_signals": 0, "opted_in": 0}

    records = DeliberationSource().fetch_recent(per=40, only_invest=True)
    if not records:
        return {"scanned": 0, "users_notified": 0, "new_signals": 0}
    # Domaines de l'ensemble des abonnés (dérivés des spécialités) → la détection
    # partagée priorise les domaines réellement suivis par la cohorte (parité scan manuel).
    cohort_domaines = sorted({d for u in opted
                              for d in re.split(r"[,;]", str(criteria_dict(u.id, db).get("specialites", "") or ""))
                              if d.strip()})
    from app.services.llm import tenant_scope
    from app.services.budget_ia import mutualise
    try:
        # Un scope (auditabilité, disjoncteur) pour l'appel mutualisé ; son coût est celui de la
        # plateforme (un seul appel sert tous les abonnés) : jamais imputé au budget d'un essai.
        with tenant_scope(opted[0].id), mutualise("veille amont planifiée"):
            projets = detect_from_deliberations(records, domaines=cohort_domaines or None)
    except Exception as e:
        # detect_from_deliberations propage désormais une panne IA → dégradation gracieuse du
        # cron (pas de crash ni de spam) ; le batch n'a pas de quota à rembourser.
        logger.warning("veille amont (cron) : détection IA indisponible : %s", e)
        return {"scanned": len(records), "users_notified": 0, "new_signals": 0}

    notified, total = 0, 0
    for user in opted:
        criteria = criteria_dict(user.id, db)
        # MatchingCriteriaExt n'a pas de colonne « domaines » : on dérive le boost domaine
        # des SPÉCIALITÉS du profil (parité réelle avec le scan manuel, où le boost vient
        # des domaines cochés). Sinon criteria.get("domaines") restait toujours None.
        domaines = (criteria.get("domaines") or criteria.get("domaines_cibles")
                    or [s.strip() for s in re.split(r"[,;]", str(criteria.get("specialites", "") or ""))
                        if s.strip()] or None)
        existing = {((s.intitule or "").lower()[:80], (s.collectivite or "").lower())
                    for s in db.query(Signal).filter(Signal.user_id == user.id).all()}
        new_pertinent = []
        for p in projets:
            intitule = (p.get("intitule") or "").strip()
            coll = (p.get("collectivite") or "").strip()
            if not intitule:
                continue
            key = (intitule.lower()[:80], coll.lower())
            if key in existing:
                continue
            existing.add(key)
            # Parité avec le scan manuel : boost domaine par utilisateur.
            score, label = score_pertinence(p, criteria, domaines)
            db.add(Signal(
                user_id=user.id, intitule=intitule[:500], type_projet=(p.get("type_projet") or "")[:120],
                budget=_num_or_none(p.get("budget")), budget_texte=(p.get("budget_texte") or "")[:120],
                localisation=(p.get("localisation") or "")[:255], collectivite=coll[:255],
                calendrier=(p.get("calendrier") or "")[:255], metiers=p.get("metiers") or [],
                # Champs de PROFONDEUR : étaient perdus en mode auto (incohérence cron/manuel).
                domaine=(p.get("domaine") or "")[:80], phase=(p.get("phase") or "")[:40],
                echeance_ao=(p.get("echeance_ao") or "")[:120], financement=(p.get("financement") or "")[:255],
                maturite=(int(p["maturite"]) if isinstance(p.get("maturite"), (int, float)) else None),
                extrait=(p.get("extrait") or "")[:2000], pertinence=label, pertinence_score=score,
                source_name=(f"Délibération · {p['source']}" if p.get("source") else "Délibération (open data)")[:255],
                source_url=(_safe_link(p.get("url"), 700) or ""), source_date=(p.get("date") or "")[:40],
            ))
            total += 1
            if label == "pertinent":
                new_pertinent.append((score, intitule, coll, p.get("budget_texte") or "", p.get("url") or ""))
        try:
            db.commit()
        except Exception:
            db.rollback()   # une contrainte ne doit pas casser la veille des autres users
            continue
        if new_pertinent:
            new_pertinent.sort(reverse=True)
            lines = ["Bonjour,\n\nVotre veille amont Adjugo a repéré de nouveaux projets d'investissement, "
                     "en amont de l'appel d'offres :\n"]
            for score, intitule, coll, b, url in new_pertinent[:12]:
                lines.append(f"   • {intitule[:90]} — {coll}{(' · ' + b) if b else ''}")
                if url:
                    lines.append(f"     {url}")
            lines.append("\n\nConnectez-vous à Adjugo (Trouver des marchés, onglet « Projets à venir ») pour les exploiter.\n\n— Adjugo")
            if send_email(user.email, f"Adjugo — {len(new_pertinent)} projet(s) détecté(s) en amont", "\n".join(lines)):
                notified += 1
    result = {"scanned": len(records), "users_notified": notified, "new_signals": total}
    logger.info("alertes veille amont : %s", result)
    return result
