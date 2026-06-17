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
    by_user = defaultdict(list)   # user_id -> [(search_name, [tenders])]
    for s in searches:
        if s.frequency == "manuelle":
            continue
        fresh = run_one_saved_search(s, db, mark=True)
        if fresh:
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
    projets = detect_from_deliberations(records)   # détection partagée (1 appel IA)

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
                maturite=_num_or_none(p.get("maturite")),
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
