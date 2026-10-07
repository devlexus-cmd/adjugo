"""
Alertes d'expiration des documents du coffre-fort.
Envoie un digest par utilisateur (escalade 30 j → 7 j → jour J),
en marquant les flags pour ne pas renvoyer deux fois la même alerte.
"""
import logging
import re
from datetime import date
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models import Document, SavedSearch, Company, User
from app.services.email import send_email

logger = logging.getLogger("adjugo")


def _due_alert(doc, days: int):
    """Retourne (label, flags_à_marquer) pour l'alerte due, ou None."""
    if days <= 0 and not doc.alert_day_sent:
        return ("expire aujourd'hui" if days == 0 else "a expiré",
                ["alert_day_sent", "alert_7_sent", "alert_30_sent"])
    if days <= 7 and not doc.alert_7_sent:
        return (f"expire dans {days} j", ["alert_7_sent", "alert_30_sent"])
    if days <= 30 and not doc.alert_30_sent:
        return (f"expire dans {days} j", ["alert_30_sent"])
    return None


def run_cotraitance_reminders(db: Session) -> dict:
    """Relance les partenaires invités qui n'ont PAS soumis leur part, à l'approche de la
    date limite. Idempotent par palier (reminder_stage : 1 = J-3 envoyée, 2 = J-1 envoyée)
    → un partenaire reçoit au plus une relance par palier. Process unique sans Redis :
    appelé par cron (POST /api/admin/run-cotraitance-reminders)."""
    from datetime import datetime, timezone
    from app.models import Project, ProjectInvite, ProjectContribution, Company

    def _is_email(v):
        return bool(v) and "@" in str(v) and "." in str(v).split("@")[-1]

    from app.services.groupement_members import active_invite_filter

    today = datetime.now(timezone.utc).date()
    invites = db.query(ProjectInvite).filter(
        active_invite_filter(),
        ProjectInvite.can_contribute.is_(True)).all()
    scanned, reminded = 0, 0
    for inv in invites:
        if not _is_email(inv.recipient):
            continue
        project = db.query(Project).filter(Project.id == inv.project_id,
                                           Project.deleted_at.is_(None)).first()
        if not project or not project.deadline:
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
        chef = (company.name if company and company.name else "le chef de file")
        base = "il vous reste 1 jour" if days_left <= 1 else f"il vous reste {days_left} jours"
        subj = f"Rappel — {base} pour votre part ({project.name[:50]})"
        text = (f"Bonjour,\n\n{base} pour ajouter votre part au groupement de {chef} sur le "
                f"marché « {project.name} » (date limite : {deadline_date}).\n\n"
                f"Complétez et soumettez votre part via votre lien Adjugo. Sans elle, votre "
                f"entreprise ne figurera pas dans la réponse commune.\n\n— Adjugo, le réseau des PME")
        if send_email(inv.recipient, subj, text):
            inv.reminder_stage = target
            reminded += 1
    db.commit()
    pieces_alerted = _run_piece_expiry_alerts(db, today)
    result = {"scanned": scanned, "reminded": reminded, "pieces_alerted": pieces_alerted}
    logger.info("relances co-traitance : %s", result)
    return result


def _run_piece_expiry_alerts(db: Session, today) -> int:
    """Coffre-fort croisé (E) : à J-7 puis J-3 de la date limite, prévient chaque membre dont
    une attestation est MANQUANTE ou EXPIRE AVANT la date limite (+ le mandataire).
    Idempotent par (invitation, jour, palier) via une entrée AuditLog `piece.expiring`
    (invite_id + detail « J-7 » / « J-3 ») — une seule exécution par palier et par jour,
    sans Redis (process unique). Best-effort : aucune exception ne remonte au cron."""
    from datetime import datetime, timedelta
    from app.models import AuditLog, Project, ProjectInvite, Company, User
    from app.services import audit
    from app.services.groupement_members import active_invites
    try:
        from app.routers.invites import coffre_croise, _PIECE_LABELS
    except Exception:
        return 0

    def _is_email(v):
        return bool(v) and "@" in str(v) and "." in str(v).split("@")[-1]

    alerted = 0
    horizon = today + timedelta(days=7)
    try:
        projects = db.query(Project).filter(
            Project.deleted_at.is_(None), Project.deadline.isnot(None),
            Project.deadline >= today, Project.deadline <= horizon).all()
    except Exception:
        return 0
    day_start = datetime(today.year, today.month, today.day)
    for project in projects:
        invites = active_invites(db, project.id)
        if not invites:
            continue
        deadline = project.deadline
        deadline_date = deadline.date() if isinstance(deadline, datetime) else deadline
        days_left = (deadline_date - today).days
        palier = "J-3" if days_left <= 3 else "J-7"
        try:
            grid = coffre_croise(db, project, invites, viewer_invite_id=None, for_owner=True)
        except Exception:
            continue
        labels = dict(_PIECE_LABELS)
        owner_user = db.query(User).filter(User.id == project.user_id).first()
        owner_email = owner_user.email if owner_user and _is_email(owner_user.email) else None
        company = db.query(Company).filter(Company.user_id == project.user_id).first()
        chef = (company.name if company and company.name else "le mandataire")
        by_id = {i.id: i for i in invites}
        for m in grid.get("members", []):
            inv = by_id.get(m.get("invite_id"))
            if not inv:
                continue
            problems = []
            for key, st in (m.get("pieces") or {}).items():
                s = st.get("status")
                if s == "manquant":
                    problems.append(f"{labels.get(key, key)} manquante")
                elif s == "expire_avant_limite":
                    problems.append(f"{labels.get(key, key)} expire le {st.get('expiration_date')} "
                                    f"(avant la date limite)")
                elif s == "expire":
                    problems.append(f"{labels.get(key, key)} expirée")
            if not problems:
                continue
            # Idempotence : déjà alerté aujourd'hui pour ce palier → on saute.
            already = db.query(AuditLog).filter(
                AuditLog.invite_id == inv.id, AuditLog.action == "piece.expiring",
                AuditLog.detail == palier, AuditLog.created_at >= day_start).first()
            if already:
                continue
            who = m.get("company") or inv.company_name or "Partenaire"
            lines = "\n".join(f"- {p}" for p in problems)
            if _is_email(inv.recipient):
                send_email(
                    inv.recipient,
                    f"Attestations à mettre à jour avant le {deadline_date} — {project.name[:50]}",
                    f"Bonjour,\n\nPour le marché « {project.name} » (date limite : {deadline_date}), "
                    f"le groupement de {chef} a besoin de vos attestations à jour :\n{lines}\n\n"
                    f"Déposez-les depuis votre espace Adjugo (votre lien d'invitation).\n\n— Adjugo")
            if owner_email:
                send_email(
                    owner_email,
                    f"{who} : attestation(s) à surveiller — {project.name[:50]}",
                    f"Bonjour,\n\nSur le marché « {project.name} » (date limite : {deadline_date}), "
                    f"les pièces de {who} ne sont pas prêtes pour le dépôt :\n{lines}\n\n"
                    f"Le partenaire a été prévenu. Suivez le coffre-fort croisé dans le cockpit du "
                    f"groupement.\n\n— Adjugo")
            audit.record(db, action="piece.expiring", owner_id=project.user_id, project_id=project.id,
                         actor="adjugo", actor_kind="system", target_type="invite", target_id=inv.id,
                         detail=palier, invite_id=inv.id)
            alerted += 1
    return alerted


def run_document_expiry_alerts(db: Session) -> dict:
    today = date.today()
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
        due = _due_alert(doc, days)
        if due:
            label, flags = due
            by_user[doc.user].append((doc, days, label, flags))

    notified, alerts = 0, 0
    for user, items in by_user.items():
        if not user or not user.email:
            continue
        lines = [f"• {d.name} — {label} (échéance {d.expiration_date})" for d, _, label, _ in items]
        text = ("Bonjour,\n\nCertaines pièces de votre coffre-fort Adjugo arrivent à "
                "échéance :\n\n" + "\n".join(lines) +
                "\n\nPensez à les renouveler pour rester éligible aux appels d'offres.\n\n— Adjugo")
        sent = send_email(user.email, f"Adjugo — {len(items)} document(s) à renouveler", text)
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

def run_one_saved_search(s: SavedSearch, db: Session, mark: bool = True) -> list:
    """Rejoue UNE recherche sauvegardée, renvoie les NOUVEAUX AO pertinents
    (non déjà notifiés, score ≥ seuil). Met à jour last_run / last_seen_refs si mark."""
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

    seen = set(s.last_seen_refs or [])
    threshold = s.min_score if s.min_score is not None else (gonogo.get("go_threshold") or 0)
    fresh = []
    for t in result["tenders"]:
        ref = t.provenance.official_ref or t.dedup_key
        if not ref or ref in seen:
            continue
        score = t.score.total if t.score else 0
        if score < threshold:
            continue
        fresh.append({
            "objet": t.objet, "acheteur": t.acheteur, "score": score,
            "date_limite": t.date_limite, "lieu": t.lieu,
            "source": t.provenance.source, "url": t.provenance.source_url, "ref": ref,
        })

    if mark:
        # On mémorise TOUS les refs vus (même sous le seuil) pour ne pas re-notifier.
        all_refs = [t.provenance.official_ref or t.dedup_key for t in result["tenders"]]
        s.last_seen_refs = list(dict.fromkeys(list(seen) + [r for r in all_refs if r]))[-500:]
        s.last_run = utcnow()
    return fresh


def run_tender_alerts(db: Session) -> dict:
    """Cron veille : rejoue toutes les recherches actives et envoie un digest par user."""
    searches = db.query(SavedSearch).filter(SavedSearch.active.is_(True)).all()
    # On ne marque « déjà vu » QUE pour les users joignables par email : sinon les marchés d'un
    # user sans email étaient marqués vus puis jamais notifiés (perdus quand il ajoute son email).
    emailed = {uid for (uid,) in db.query(User.id).filter(User.email.isnot(None)).all()}
    by_user = defaultdict(list)   # user_id -> [(search_name, [tenders])]
    for s in searches:
        if s.frequency == "manuelle":
            continue
        has_email = s.user_id in emailed
        fresh = run_one_saved_search(s, db, mark=has_email)
        if fresh and has_email:
            by_user[s.user_id].append((s.name, fresh))

    notified, total = 0, 0
    for user_id, blocks in by_user.items():
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.email:
            continue
        lines = ["Bonjour,\n\nVotre veille Adjugo a repéré de nouveaux appels d'offres :\n"]
        for name, tenders in blocks:
            lines.append(f"\n● {name} ({len(tenders)} nouveau(x)) :")
            for t in tenders[:10]:
                ech = f" — clôture {t['date_limite']}" if t.get("date_limite") else ""
                lines.append(f"   • [{t['score']}/100] {t['objet'][:90]} — {t.get('acheteur') or 'acheteur n/d'}{ech}\n     {t['url']}")
            total += len(tenders)
        lines.append("\n\nConnectez-vous à Adjugo pour les analyser.\n\n— Adjugo")
        if send_email(user.email, f"Adjugo — {sum(len(t) for _, t in blocks)} nouvel(s) appel(s) d'offres", "\n".join(lines)):
            notified += 1
    db.commit()
    result = {"searches_run": len(searches), "users_notified": notified, "new_matches": total}
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
    from app.sourcing.sources.deliberations import DeliberationSource
    from app.services.agents.amont import detect_from_deliberations, score_pertinence
    from app.services.profile import criteria_dict
    from app.models import Signal

    # Personne n'a activé la veille auto → aucun scan (zéro appel IA inutile).
    opted = db.query(User).filter(User.email.isnot(None), User.amont_alerts_enabled.is_(True)).all()
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
    try:
        with tenant_scope(opted[0].id):   # un scope (auditabilité/quota) pour l'appel mutualisé
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
                source_url=(p.get("url") or "")[:700], source_date=(p.get("date") or "")[:40],
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
                lines.append(f"   • [{score}/100] {intitule[:90]} — {coll}{(' · ' + b) if b else ''}")
                if url:
                    lines.append(f"     {url}")
            lines.append("\n\nConnectez-vous à Adjugo (onglet Veille amont) pour les exploiter.\n\n— Adjugo")
            if send_email(user.email, f"Adjugo — {len(new_pertinent)} projet(s) détecté(s) en amont", "\n".join(lines)):
                notified += 1
    result = {"scanned": len(records), "users_notified": notified, "new_signals": total}
    logger.info("alertes veille amont : %s", result)
    return result
