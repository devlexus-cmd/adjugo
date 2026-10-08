"""
Adjugo — Journal d'accès (RGPD).

Trace de qui consulte/télécharge quoi, et quand. Surtout : les accès des co-traitants
externes invités via un lien bridé. C'est la preuve de traçabilité exigible (RGPD /
confidentialité des dossiers de candidature).

Ce que garantit le journal, dit exactement :
  • chaque entrée est chaînée par hachage à la précédente du même owner_id : toute
    modification, insertion ou suppression d'une entrée AU MILIEU de la chaîne est
    détectée par verify_chain ;
  • la suppression des DERNIÈRES entrées (queue de chaîne) laisse un préfixe valide : elle
    n'est détectée que par comparaison au dernier ancrage quotidien horodaté
    (app/services/audit_anchor.py). Les entrées écrites depuis cet ancrage (moins de
    24 h) ne sont donc pas couvertes ;
  • le hachage n'est pas une signature : un accès en écriture à la base permet de tout
    recalculer. Ce sont l'ancrage horodaté par une autorité externe et sa copie hors
    infrastructure qui rendent une telle réécriture détectable.

Principe : un échec d'écriture du journal NE DOIT JAMAIS faire échouer l'action
métier sous-jacente — on isole donc l'écriture et on avale toute exception.
"""
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("adjugo")


def _ts(dt) -> str:
    """Timestamp canonique : UTC naïf à la microseconde. Indispensable car selon le
    backend created_at est tz-aware (Python/utcnow) ou naïf (relu de SQLite) — sans
    normalisation le hash diffère entre écriture et relecture."""
    if dt is None:
        return ""
    try:
        if dt.tzinfo is not None:
            from datetime import timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat(timespec="microseconds")
    except Exception:
        return str(dt)


def _entry_payload(a) -> str:
    """Représentation canonique d'une entrée pour le hash (ordre stable)."""
    return "|".join(str(x) for x in (
        a.id, _ts(a.created_at), a.owner_id, a.project_id, a.actor, a.actor_kind,
        a.action, a.target_type, a.target_id, a.detail, a.ip,
    ))


def _hash(prev_hash: str, a) -> str:
    return hashlib.sha256(((prev_hash or "") + _entry_payload(a)).encode("utf-8")).hexdigest()


def client_ip(request) -> str:
    """IP réelle du client derrière le proxy Railway, NON spoofable (dernier hop XFF).
    Voir app.core.ratelimit.real_client_ip — source unique de vérité."""
    try:
        from app.core.ratelimit import real_client_ip
        return (real_client_ip(request) or "")[:45]
    except Exception:
        try:
            return (request.client.host if request.client else "")[:45]
        except Exception:
            return ""


def record(db, *, action: str, owner_id: Optional[int] = None,
           project_id: Optional[int] = None, actor: str = "", actor_kind: str = "",
           target_type: str = "", target_id: Optional[int] = None,
           detail: str = "", ip: str = "", meta: Optional[dict] = None,
           invite_id: Optional[int] = None) -> None:
    """Écrit une entrée d'audit, chaînée par hash (tamper-evidence). Best-effort.

    `invite_id` = invitation concernée (journal MEMBRE : projection par simple filtre).
    Volontairement HORS du payload haché (`_entry_payload`) pour ne pas invalider la
    chaîne des entrées existantes — c'est un index de projection, pas une preuve."""
    try:
        from app.models import AuditLog, utcnow
        now = utcnow()
        # UTC NAÏF (vague 4) : un datetime avec fuseau est converti par Postgres dans le fuseau
        # de la SESSION avant d'être rangé dans une colonne sans fuseau — sur une base réglée
        # en Europe/Paris, la valeur relue différait de 1-2 h de celle hachée et toute la chaîne
        # semblait altérée. Naïf UTC : la valeur rangée est exactement celle qui est hachée,
        # quel que soit le fuseau (identique à l'existant sur une base en UTC).
        if now.tzinfo is not None:
            from datetime import timezone as _tz
            now = now.astimezone(_tz.utc).replace(tzinfo=None)
        entry = AuditLog(
            created_at=now,        # figé explicitement : doit être identique au hash
            action=action[:60], owner_id=owner_id, project_id=project_id,
            actor=(actor or "")[:160], actor_kind=(actor_kind or "")[:20],
            target_type=(target_type or "")[:40], target_id=target_id,
            detail=(detail or "")[:255], ip=(ip or "")[:45], meta=meta,
            invite_id=invite_id,
        )
        # Écritures SÉRIALISÉES par tenant, de l'INSERT jusqu'au COMMIT : sans ce verrou, deux
        # écritures simultanées (deux partenaires qui ouvrent leur lien au même instant) lisaient
        # le même maillon précédent → chaîne « fourchue » et verdict « altéré » à tort.
        # Verrou consultatif TRANSACTIONNEL (relâché par le commit ci-dessous) ; Postgres
        # détecte les interblocages qu'il formerait avec des verrous de lignes. SQLite sérialise
        # déjà les écritures : rien à faire.
        try:
            if db.get_bind().dialect.name == "postgresql":
                from sqlalchemy import text as _text
                db.execute(_text("SELECT pg_advisory_xact_lock(:ns, :k)"),
                           {"ns": _AUDIT_LOCK_NS, "k": int(owner_id or 0)})
        except Exception as e:      # le verrou ne doit jamais empêcher la journalisation
            logger.warning("audit: verrou de chaîne indisponible : %s", type(e).__name__)
        db.add(entry)
        db.flush()   # obtient l'id avant de calculer le hash
        # Maillon précédent du même tenant : la chaîne lie chaque entrée à la suivante.
        prev = db.query(AuditLog).filter(
            AuditLog.owner_id == owner_id, AuditLog.id < entry.id,
        ).order_by(AuditLog.id.desc()).first()
        entry.prev_hash = (prev.entry_hash if prev else "")
        entry.entry_hash = _hash(entry.prev_hash, entry)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("audit: écriture du journal échouée (%s) : %s", action, e)


def _anchor_fields(db, owner_id, rows, upto_id) -> dict:
    try:
        from app.services.audit_anchor import check_chain
        return check_chain(db, owner_id, rows, upto_id)
    except Exception as e:      # la vérification ne doit jamais tomber à cause de l'ancrage
        logger.warning("audit: comparaison au dernier ancrage impossible : %s", type(e).__name__)
        return {"anchor_date": None, "anchor_timestamped": False, "anchor_checked": False,
                "truncated": False, "missing_since": None, "missing_id": None}


def _message(res: dict) -> str:
    try:
        from app.services.audit_anchor import message
        return message(res)
    except Exception:
        return "Journal intact." if res.get("intact") else "Le journal a été altéré."


_AUDIT_LOCK_NS = 7041          # espace de noms du verrou consultatif (journal d'audit)
_FORK_WINDOW = 64              # fourches de concurrence : maillon pris parmi les entrées récentes


def verify_chain(db, owner_id: int, upto_id: int = None) -> dict:
    """Revérifie la chaîne de hash d'un tenant : recalcule chaque maillon et détecte toute
    entrée modifiée, supprimée ou réordonnée À L'INTÉRIEUR de la chaîne ; puis compare la
    chaîne au dernier ancrage quotidien pour détecter la disparition des DERNIÈRES entrées
    (hors entrées écrites depuis cet ancrage, et hors effacement RGPD légitime).
    `upto_id` : ne vérifie que le PRÉFIXE de la chaîne (entrées d'id ≤ upto_id) — un préfixe
    d'une chaîne de hachage reste vérifiable seul (cas d'un ancien propriétaire parti fonder
    une autre entreprise : seule sa période dans l'organisation la concerne).
    Champs ajoutés (rétrocompatibles) : anchor_date, anchor_timestamped, anchor_checked,
    truncated, missing_since, message."""
    from app.models import AuditLog
    q = db.query(AuditLog).filter(AuditLog.owner_id == owner_id)
    if upto_id is not None:
        q = q.filter(AuditLog.id <= upto_id)
    rows = q.order_by(AuditLog.id.asc()).all()
    prev = ""
    broken_at = None
    forks = 0
    recent = []          # empreintes des dernières entrées chaînées (ordre d'id)
    for a in rows:
        # Entrées historiques (avant l'activation du chaînage) : pas de hash → on saute.
        if not a.entry_hash:
            prev = ""
            recent = []
            continue
        link = a.prev_hash or ""
        # Contenu de l'entrée : toujours recalculé (toute modification est détectée).
        if _hash(link, a) != a.entry_hash:
            broken_at = a.id
            break
        if link != prev:
            # Fourche due à deux écritures simultanées (avant le verrou de chaîne) : le maillon
            # pointe vers une entrée RÉCENTE qui existe bien. Une entrée supprimée au milieu de
            # la chaîne reste détectée (son empreinte n'existe plus nulle part).
            if link and link in recent:
                forks += 1
            else:
                broken_at = a.id
                break
        prev = a.entry_hash
        recent.append(a.entry_hash)
        if len(recent) > _FORK_WINDOW:
            recent.pop(0)
    chained = [a for a in rows if a.entry_hash]
    res = {
        "owner_id": owner_id,
        "entries": len(rows),
        "chained_entries": len(chained),
        "intact": broken_at is None,
        "broken_at_id": broken_at,
        "forks": forks,      # écritures simultanées anciennes, tolérées (voir ci-dessus)
    }
    res.update(_anchor_fields(db, owner_id, rows, upto_id))
    missing_id = res.pop("missing_id", None)
    if res.get("truncated"):
        res["intact"] = False
        if res["broken_at_id"] is None:
            res["broken_at_id"] = missing_id
    res["message"] = _message(res)
    return res


def verify_org_chains(db, owner_ids) -> dict:
    """Vérifie TOUTES les chaînes d'une organisation : celle du propriétaire actuel (premier
    de `owner_ids`) ET celles encore référencées par son historique (anciens propriétaires
    après un transfert, comptes effacés-anonymisés…). Le journal d'un tenant n'est pas
    réécrit au transfert (owner_id est haché) : sans cette agrégation, l'historique
    antérieur échappait à la vérification. Renvoie le format de verify_chain (agrégé) +
    le détail par chaîne dans « chains »."""
    # Éléments : un owner_id, ou (owner_id, upto_id) pour ne vérifier qu'un préfixe.
    ids, upto = [], {}
    for item in owner_ids or []:
        oid, lim = (item if isinstance(item, (tuple, list)) else (item, None))
        if oid is None:
            continue
        if oid not in ids:
            ids.append(oid)
            upto[oid] = lim
        elif upto.get(oid) is not None and lim is None:
            upto[oid] = None                      # une vérification complète l'emporte
    chains = [verify_chain(db, oid, upto.get(oid)) for oid in ids]
    broken = next((c for c in chains if not c["intact"]), None)
    truncated = next((c for c in chains if c.get("truncated")), None)
    res = {
        "owner_id": ids[0] if ids else None,
        "entries": sum(c["entries"] for c in chains),
        "chained_entries": sum(c["chained_entries"] for c in chains),
        "intact": broken is None,
        "broken_at_id": broken["broken_at_id"] if broken else None,
        "chains": chains,
        "anchor_date": next((c["anchor_date"] for c in chains if c.get("anchor_date")), None),
        "anchor_timestamped": any(c.get("anchor_timestamped") for c in chains),
        "anchor_checked": any(c.get("anchor_checked") for c in chains),
        "truncated": truncated is not None,
        "missing_since": truncated["missing_since"] if truncated else None,
    }
    res["message"] = broken["message"] if broken else _message(res)
    return res
