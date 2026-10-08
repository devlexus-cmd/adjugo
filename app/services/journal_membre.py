"""
Adjugo — Journal MEMBRE vérifiable (co-traitance v2, vague 4).

Jusqu'ici, chaque membre d'un groupement voyait SA projection du journal (« qui a vu quoi ») et
un booléen « chaîne intacte » calculé par Adjugo : c'était « infalsifiable tenu par Adjugo ».
Ce module rend la promesse vérifiable PAR LE MEMBRE, sans jamais lui montrer une donnée qu'il
n'a pas le droit de voir (ni IP, ni email, ni identifiant interne d'un autre membre).

Ce que fait le serveur (GET …/journal/integrity) :
  1. relit les entrées qui concernent le membre (ses entrées + événements de groupement du
     marché, exactement la projection du journal) dans l'ordre de la chaîne ;
  2. pour CHACUNE, recalcule son empreinte (`audit._hash(prev_hash, entrée)`, le même calcul
     qu'à l'écriture) et vérifie qu'elle est bien reliée à l'entrée qui la précède dans la
     chaîne du chef de file (prev_hash = empreinte de l'entrée précédente du même tenant) ;
  3. vérifie la chaîne COMPLÈTE du tenant (audit.verify_chain, mis en cache) et la compare au
     dernier ancrage quotidien horodaté (audit_anchor) : le verdict cite sa date.

Ce que peut refaire le membre HORS LIGNE (export JSON) :
  • chaque entrée porte un SCEAU = sha256("adjugo-sceau-v1|" + entry_hash). Le sceau engage
    l'empreinte réelle de l'entrée sans la révéler : connaître entry_hash et prev_hash d'une
    entrée permettrait de retrouver par force brute l'IP du chef de file (espace IPv4 réduit) —
    le sceau, à sens unique, l'empêche ;
  • les entrées sont enchaînées en une sous-chaîne propre au membre :
        maillon_0 = ""
        maillon_n = sha256(maillon_{n-1} + "|" + n + "|" + at + "|" + action + "|" + qui + "|" + sceau_n)
    et l'EMPREINTE du journal du membre = maillon_N ;
  • le membre recalcule les maillons à partir du fichier (sha256, rien d'autre) ; s'il garde un
    export, tout export ultérieur doit le PROLONGER : mêmes entrées n ≤ N_ancien, même
    maillon_N_ancien. Une entrée modifiée, supprimée ou une chaîne réécrite par Adjugo (toute
    réécriture change les entry_hash, donc les sceaux) devient visible par simple comparaison.

Limites, dites exactement (renvoyées aussi dans `limites`) : le sceau ne permet pas au membre de
recalculer lui-même l'empreinte d'une entrée (il faudrait l'IP et l'acteur exacts, qu'il ne doit
pas voir) : la vérification entrée par entrée est faite par Adjugo, la comparaison d'exports par
le membre. Les entrées écrites depuis le dernier ancrage (moins de 24 h) ne sont couvertes que par
l'export que le membre a lui-même conservé. Le hachage n'est pas une signature.

Version figée « adjugo-journal-membre-v1 » : l'ensemble des événements de groupement projetés
(GROUP_EVENTS) et le format des maillons ne changent plus sans changer de version (ajouter un
événement ANCIEN ferait apparaître des entrées au milieu de la sous-chaîne et casserait la
comparaison des exports). Process unique : résultats mis en cache en mémoire (TTL court),
nombre d'entrées borné, aucun appel externe, aucun appel LLM.
"""
import hashlib
import io
import json
import logging
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger("adjugo")

SCHEMA = "adjugo-journal-membre-v1"
SCEAU_PREFIX = "adjugo-sceau-v1|"
MAX_ENTRIES = 2000              # borne dure (une part ≈ quelques dizaines d'entrées)
_INTEGRITY_TTL = 60             # s — résultat par invitation (route invitée à 30/min)
_TENANT_TTL = 300               # s — verify_chain = full-scan du tenant
_CACHE_MAX = 2000

INTEGRITY_LABEL = "Journal vérifiable : toute modification ou suppression d'entrée est détectable"

LIMITES = [
    "La vérification entrée par entrée est faite par Adjugo ; vous pouvez la compléter hors ligne "
    "en comparant deux exports successifs de votre journal.",
    "Les entrées écrites depuis la dernière empreinte quotidienne (moins de 24 h) ne sont couvertes "
    "que par l'export que vous avez conservé.",
    "Le journal ne montre jamais l'adresse IP ni l'email des autres membres : leurs entrées sont "
    "engagées par un sceau, pas révélées.",
]

# Événements « de groupement » visibles par TOUS les membres (pas seulement le concerné).
# Ensemble FIGÉ pour la version v1 (voir la docstring) : seules des actions NOUVELLES (sans
# entrée ancienne) peuvent y entrer sans changer de version.
GROUP_EVENTS = frozenset({
    "offer.frozen", "offer.unfrozen", "groupement.retenue", "convention.generated",
    "convention.signed", "invite.created", "invite.revoked", "invite.declined",
    # Vague 2 (convention) : caducité et accord hors ligne, visibles de tous les membres.
    "convention.perimee", "convention.hors_ligne",
    # Vague 4 (dépôt) : le chef de file marque le dossier déposé (ou annule ce marquage).
    "groupement.depose", "groupement.depot_annule",
})

# Libellés en français simple (zéro jargon) selon QUI a agi, vu depuis le membre.
LABELS_ME = {
    "guest.view_project": "Vous avez consulté le dossier",
    "guest.download_doc": "Vous avez téléchargé une pièce du dossier",
    "guest.submit_contribution": "Vous avez soumis votre part",
    "guest.upload_piece": "Vous avez déposé une pièce",
    "guest.update_piece": "Vous avez mis à jour une pièce (type ou date de validité)",
    "guest.capacites_updated": "Vous avez mis à jour vos capacités",
    "guest.otp_request": "Vous avez demandé un code de vérification",
    "guest.otp_verified": "Vous avez vérifié votre adresse email",
    "invite.claimed": "Vous avez rattaché ce dossier à votre compte",
    "invite.declined": "Vous avez décliné l'invitation",
    "offer.unfrozen": "Votre modification a défigé l'offre commune",
    # Vague 2 : « accord enregistré », jamais « signature électronique ».
    "convention.signed": "Vous avez validé la convention (accord enregistré)",
    "convention.perimee": "Votre modification a rendu la convention caduque : elle doit être régénérée",
    "guest.download_convention": "Vous avez téléchargé la convention",
    # Vague 4
    "guest.export_journal": "Vous avez exporté votre journal",
}
LABELS_OWNER = {
    "owner.view_contribution": "Le mandataire a consulté votre part",
    "owner.download_piece": "Le mandataire a téléchargé votre pièce",
    "owner.view_piece": "Le mandataire a consulté votre pièce",
    "invite.created": "Le mandataire vous a invité",
    "invite.resent": "Le mandataire vous a renvoyé l'invitation",
    "invite.revoked": "Le mandataire vous a retiré du groupement",
    "offer.frozen": "Le mandataire a figé l'offre commune",
    "offer.unfrozen": "Le mandataire a défigé l'offre commune",
    "groupement.retenue": "Le mandataire a retenu la composition du groupement",
    "convention.generated": "Le mandataire a généré la convention de groupement",
    "convention.signed": "Le mandataire a validé la convention (accord enregistré)",
    "convention.perimee": "La convention n'est plus à jour : le mandataire doit la régénérer",
    "convention.hors_ligne": "Le mandataire a enregistré l'accord hors ligne d'un partenaire",
    "piece.expiring": "Adjugo vous a alerté : une attestation manque ou expire",
    # Vague 4
    "groupement.depose": "Le mandataire a marqué le dossier comme déposé",
    "groupement.depot_annule": "Le mandataire a annulé le marquage « déposé »",
}
LABELS_PARTNER = {
    "invite.created": "Un partenaire a été invité",
    "invite.declined": "Un partenaire a décliné",
    "invite.revoked": "Un partenaire a été retiré",
    "convention.signed": "Un partenaire a validé la convention (accord enregistré)",
    "offer.unfrozen": "L'offre commune a été défigée (part d'un partenaire modifiée)",
    "convention.perimee": "La convention n'est plus à jour (part d'un partenaire modifiée)",
}
# Événements de groupement dont le détail (sans donnée personnelle) peut être montré à tous.
_DETAIL_OK = ("offer.frozen", "convention.generated", "convention.hors_ligne")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")     # même règle que invites._is_email


def _is_email(s) -> bool:
    return bool(_EMAIL_RE.match((s or "").strip()))


def _ts(dt) -> str:
    from app.services.audit import _ts as audit_ts
    return audit_ts(dt)


def _fr_dt(dt) -> str:
    if dt is None:
        return ""
    try:
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%d/%m/%Y à %H:%M (UTC)")
    except Exception:
        return str(dt)


def _fr_day(day: str) -> str:
    try:
        y, m, d = str(day)[:10].split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return str(day or "")


# ── Projection (source unique : route journal, intégrité, exports) ─────────────────────

def member_query(db, inv):
    """Entrées qui concernent le membre : les siennes + les événements de groupement du marché.
    Invitation RÉSEAU pas encore acceptée (vague 3) : ses entrées seulement — l'aperçu minimal
    ne montre pas la composition du groupement, le journal non plus (ni sa vérification)."""
    from app.models import AuditLog
    from app.routers.invites import _network_pending      # import local : pas de cycle
    cond = (AuditLog.invite_id == inv.id)
    if not _network_pending(inv, db):
        cond = cond | (AuditLog.action.in_(sorted(GROUP_EVENTS)))
    return db.query(AuditLog).filter(AuditLog.project_id == inv.project_id, cond)


def partner_names(db, inv, rows) -> dict:
    """Noms d'entreprise des AUTRES invitations citées (pour les événements de groupement)."""
    from app.models import ProjectInvite
    other_ids = {r.invite_id for r in rows if r.invite_id and r.invite_id != inv.id}
    if not other_ids:
        return {}
    return {i.id: (i.company_name or "") for i in db.query(ProjectInvite).filter(
        ProjectInvite.id.in_(list(other_ids))).all()}


def project_row(r, inv, names: dict):
    """Projection d'UNE entrée vers le membre : {at, action, label, who, detail} ou None.
    SANS ip, SANS email, SANS identifiant interne ; l'acteur devient « vous » / « mandataire »
    / « partenaire »."""
    mine = (r.invite_id == inv.id)
    if mine and r.actor_kind == "guest":
        who, label = "vous", LABELS_ME.get(r.action, r.action)
        detail = r.detail or ""
    elif mine:                                   # le mandataire (ou Adjugo) a agi sur MA part
        who, label = "mandataire", LABELS_OWNER.get(r.action, r.action)
        detail = r.detail or ""
        if r.action in ("owner.download_piece", "owner.view_piece") and detail:
            label = f"{label} « {detail} »"
    elif r.action in GROUP_EVENTS and r.actor_kind in ("guest", "system") and r.invite_id:
        who, label = "partenaire", LABELS_PARTNER.get(r.action, r.action)
        detail = names.get(r.invite_id, "") or ""
    elif r.action in GROUP_EVENTS:
        who, label = "mandataire", LABELS_OWNER.get(r.action, r.action)
        # invite.created / invite.revoked concernent un AUTRE membre → libellé partenaire.
        if r.action in ("invite.created", "invite.revoked", "invite.declined"):
            who, label = "partenaire", LABELS_PARTNER.get(r.action, r.action)
        detail = names.get(r.invite_id, "") if r.invite_id else (
            r.detail if r.action in _DETAIL_OK else "")
        # Un sous-traitant n'est pas membre du groupement : il ne reçoit jamais le total de
        # l'offre commune (règle de la vague 2), pas même dans le détail du journal.
        if r.action == "offer.frozen" and (getattr(inv, "role", "") or "") == "sous_traitant":
            detail = ""
    else:
        return None
    # Jamais un email en clair dans la projection (anciennes entrées : actor/detail = email).
    if _is_email(detail):
        detail = ""
    return {"at": r.created_at.isoformat() if r.created_at else None,
            "action": r.action, "label": label, "who": who, "detail": (detail or "")[:255]}


def journal_entries(db, inv, limit: int = 200) -> list:
    """Le journal tel que le membre le lit (plus récent d'abord)."""
    from app.models import AuditLog
    rows = member_query(db, inv).order_by(AuditLog.created_at.desc()).limit(limit).all()
    names = partner_names(db, inv, rows)
    out = []
    for r in rows:
        e = project_row(r, inv, names)
        if e is not None:
            out.append(e)
    return out


# ── Caches (process unique) ────────────────────────────────────────────────────────────

_TENANT_CACHE: dict = {}        # owner_id → (ts, verify_chain result)
_INTEGRITY_CACHE: dict = {}     # invite_id → (ts, result)


def reset_caches() -> None:
    _TENANT_CACHE.clear()
    _INTEGRITY_CACHE.clear()


def forget(invite_id) -> None:
    """Oublie le verdict en cache d'une invitation (une entrée vient de s'ajouter)."""
    _INTEGRITY_CACHE.pop(invite_id, None)


def _put(cache: dict, key, value) -> None:
    if len(cache) >= _CACHE_MAX:
        cache.clear()            # borne mémoire simple : le cache se reconstruit
    cache[key] = (time.monotonic(), value)


def _get(cache: dict, key, ttl: int):
    hit = cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def tenant_result(db, owner_id) -> dict:
    """verify_chain du tenant (full-scan + comparaison au dernier ancrage), en cache 5 min."""
    hit = _get(_TENANT_CACHE, owner_id, _TENANT_TTL)
    if hit is not None:
        return hit
    from app.services import audit
    try:
        res = audit.verify_chain(db, owner_id)
    except Exception as e:
        logger.warning("journal membre : vérification du tenant impossible (%s)", type(e).__name__)
        res = {"intact": False, "truncated": False, "anchor_date": None, "anchor_timestamped": False,
               "anchor_checked": False, "error": True}
    _put(_TENANT_CACHE, owner_id, res)
    return res


# ── Vérification de la sous-chaîne du membre ───────────────────────────────────────────

def _predecessors(db, rows) -> dict:
    """{id: entry_hash de l'entrée PRÉCÉDENTE de la même chaîne (même owner_id)} — exactement le
    maillon que audit.record a lu à l'écriture. Une requête fenêtrée (LAG) par chaîne, bornée à
    l'id maximal concerné ; SQLite ≥ 3.25 et Postgres."""
    from sqlalchemy import func, select
    from app.models import AuditLog
    by_owner = {}
    for r in rows:
        by_owner.setdefault(r.owner_id, []).append(r.id)
    out = {}
    for oid, ids in by_owner.items():
        cond = AuditLog.owner_id.is_(None) if oid is None else (AuditLog.owner_id == oid)
        # Fenêtre bornée à la période du membre : de l'entrée qui précède sa première entrée
        # jusqu'à sa dernière (jamais tout l'historique du tenant).
        before = db.query(func.max(AuditLog.id)).filter(cond, AuditLog.id < min(ids)).scalar()
        lower = before if before is not None else min(ids)
        lag = func.lag(AuditLog.entry_hash).over(order_by=AuditLog.id.asc())
        sub = select(AuditLog.id.label("id"), lag.label("pred")).where(
            cond, AuditLog.id >= lower, AuditLog.id <= max(ids)).subquery()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for rid, pred in db.execute(select(sub.c.id, sub.c.pred).where(sub.c.id.in_(chunk))).all():
                out[rid] = pred or ""
    return out


def sceau_of(entry_hash: str) -> str:
    return _sha(SCEAU_PREFIX + (entry_hash or ""))


def maillon_of(prev: str, n: int, at: str, action: str, qui: str, sceau: str) -> str:
    return _sha(f"{prev}|{n}|{at}|{action}|{qui}|{sceau}")


def _anchor():
    try:
        from app.services.audit_anchor import latest_anchor
        return latest_anchor()
    except Exception:
        return None


def verify_member(db, inv, use_cache: bool = True) -> dict:
    """Recalcule la sous-chaîne du membre et rend le verdict (voir la docstring du module)."""
    if use_cache:
        hit = _get(_INTEGRITY_CACHE, inv.id, _INTEGRITY_TTL)
        if hit is not None:
            return hit
    from app.models import AuditLog
    from app.services import audit
    q = member_query(db, inv).order_by(AuditLog.id.asc())
    rows = q.limit(MAX_ENTRIES + 1).all()
    tronque = len(rows) > MAX_ENTRIES
    rows = rows[:MAX_ENTRIES]
    names = partner_names(db, inv, rows)
    preds = _predecessors(db, rows) if rows else {}

    owners = sorted({r.owner_id for r in rows if r.owner_id is not None})
    tenants = {oid: tenant_result(db, oid) for oid in owners}
    anchor = _anchor()
    heads = (anchor or {}).get("_by_owner") or {}

    chaine, maillon = [], ""
    n_ok = n_bad = n_unchained = n_covered = 0
    first_bad = None
    for n, r in enumerate(rows, start=1):
        proj = project_row(r, inv, names) or {"label": r.action, "who": "", "detail": ""}
        if not r.entry_hash:
            statut = "non_chainee"
            n_unchained += 1
        else:
            hash_ok = audit._hash(r.prev_hash or "", r) == r.entry_hash
            link_ok = (r.prev_hash or "") == preds.get(r.id, "")
            statut = "verifiee" if (hash_ok and link_ok) else "alteree"
            if statut == "verifiee":
                n_ok += 1
            else:
                n_bad += 1
                if first_bad is None:
                    first_bad = {"n": n, "at": r.created_at.isoformat() if r.created_at else None,
                                 "label": proj["label"]}
        head = heads.get(r.owner_id)
        couverte = bool(head and r.entry_hash and r.id <= head.get("last_id", -1))
        n_covered += int(couverte)
        at = _ts(r.created_at)
        sceau = sceau_of(r.entry_hash)
        maillon = maillon_of(maillon, n, at, r.action, proj["who"], sceau)
        chaine.append({"n": n, "at": at, "action": r.action, "qui": proj["who"],
                       "label": proj["label"], "detail": proj.get("detail", ""),
                       "sceau": sceau, "maillon": maillon, "statut": statut,
                       "couverte_par_ancrage": couverte})

    journal_ok = all(bool(t.get("intact")) for t in tenants.values())
    truncated = any(bool(t.get("truncated")) for t in tenants.values())
    if not rows:
        verdict, perimetre = "vide", None
    elif n_bad:
        verdict, perimetre = "altere", "vos_entrees"
    elif not journal_ok:
        verdict, perimetre = "altere", "journal"
    else:
        verdict, perimetre = "intact", None

    ancrage = None
    if anchor and anchor.get("date"):
        horodate = bool((anchor.get("tsa") or {}).get("ok"))
        ancrage = {"date": anchor.get("date"), "date_label": _fr_day(anchor.get("date")),
                   "horodate": horodate, "entrees_couvertes": n_covered}
        if n_covered:
            ancrage["message"] = (
                f"{n_covered} entrée{'s' if n_covered > 1 else ''} antérieure{'s' if n_covered > 1 else ''} "
                f"au {_fr_day(anchor.get('date'))} {'sont' if n_covered > 1 else 'est'} aussi "
                f"couverte{'s' if n_covered > 1 else ''} par l'empreinte quotidienne du journal"
                + (", horodatée par une autorité indépendante." if horodate else "."))
        else:
            ancrage["message"] = (f"Dernière empreinte quotidienne du journal : {_fr_day(anchor.get('date'))}"
                                  + (" (horodatée par une autorité indépendante)." if horodate else "."))

    msg = _message(verdict, perimetre, len(rows), n_ok, n_unchained, first_bad, truncated, ancrage)
    res = {
        "schema": SCHEMA,
        "verdict": verdict,
        "verdict_label": {"intact": "Intact", "altere": "Altéré", "vide": "Aucune entrée"}[verdict],
        "perimetre": perimetre,
        "message": msg,
        "integrity_label": INTEGRITY_LABEL,
        "verifie_le": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
        "entrees": {"total": len(rows), "verifiees": n_ok, "alterees": n_bad, "non_chainees": n_unchained},
        "premiere_alteration": first_bad,
        "journal_complet_intact": journal_ok and not truncated,
        "ancrage": ancrage,
        "empreinte": maillon,
        "tronque": tronque,
        "limites": list(LIMITES),
        "chaine": chaine,
    }
    _put(_INTEGRITY_CACHE, inv.id, res)
    return res


def _message(verdict, perimetre, total, n_ok, n_unchained, first_bad, truncated, ancrage) -> str:
    if verdict == "vide":
        return "Aucune entrée pour l'instant."
    if verdict == "altere" and perimetre == "vos_entrees":
        when = ""
        if first_bad and first_bad.get("at"):
            try:
                when = " (entrée du " + _fr_dt(datetime.fromisoformat(first_bad["at"])) + \
                       f" : « {first_bad.get('label', '')} »)"
            except Exception:
                when = ""
        return ("Une entrée de votre journal a été modifiée, ou une entrée voisine supprimée"
                f"{when}. Signalez-le au chef de file et à Adjugo.")
    if verdict == "altere":
        what = "tronqué (des entrées ont disparu)" if truncated else "modifié"
        return (f"Vos entrées sont cohérentes, mais le journal du chef de file a été {what} : "
                "l'ensemble ne peut pas être garanti. Signalez-le à Adjugo.")
    s = "s" if n_ok > 1 else ""
    out = (f"Journal intact : {n_ok} entrée{s} vérifiée{s} une à une, "
           "aucune modification ni suppression détectée.")
    if n_unchained:
        out += (f" {n_unchained} entrée{'s' if n_unchained > 1 else ''} ancienne{'s' if n_unchained > 1 else ''}, "
                "antérieure(s) au chaînage du journal, ne peu" + ("vent" if n_unchained > 1 else "t")
                + " pas être vérifiée" + ("s." if n_unchained > 1 else "."))
    if ancrage and ancrage.get("entrees_couvertes"):
        out += " " + ancrage["message"]
    return out


# ── Exports (JSON / PDF) ───────────────────────────────────────────────────────────────

ALGORITHME = {
    "nom": SCHEMA,
    "sceau": "sceau = sha256(\"adjugo-sceau-v1|\" + empreinte de l'entrée dans le journal du chef de file), en hexadécimal",
    "maillon": "maillon_0 = \"\" ; maillon_n = sha256(maillon_(n-1) + \"|\" + n + \"|\" + at + \"|\" + action + \"|\" + qui + \"|\" + sceau_n), en hexadécimal (texte UTF-8)",
    "empreinte": "empreinte du journal = maillon de la dernière entrée",
    "verification_hors_ligne": [
        "Recalculer chaque maillon à partir des champs n, at, action, qui et sceau de ce fichier : il doit être identique au maillon indiqué, et le dernier à l'empreinte.",
        "Comparer avec un export plus ancien : chaque entrée n de l'ancien export doit se retrouver à l'identique (même at, action, qui, sceau, maillon) dans le nouveau, et le maillon de sa dernière entrée doit être identique. Sinon, une entrée a été modifiée ou supprimée.",
    ],
}


def export_payload(db, inv, project, company: str = "") -> dict:
    """Export JSON du journal du membre : projection + sous-chaîne + verdict + algorithme."""
    res = verify_member(db, inv, use_cache=False)
    return {
        "schema": SCHEMA,
        "exporte_le": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
        "marche": (getattr(project, "name", "") or "")[:500],
        "membre": (company or getattr(inv, "company_name", "") or "")[:255],
        "verdict": {k: res[k] for k in ("verdict", "verdict_label", "perimetre", "message",
                                        "entrees", "premiere_alteration", "journal_complet_intact",
                                        "ancrage", "tronque")},
        "integrity_label": INTEGRITY_LABEL,
        "empreinte": res["empreinte"],
        "algorithme": ALGORITHME,
        "limites": res["limites"],
        "entrees": [{k: e[k] for k in ("n", "at", "action", "qui", "label", "detail", "sceau",
                                       "maillon", "statut")} for e in res["chaine"]],
    }


def verify_export(doc: dict) -> dict:
    """Vérification HORS LIGNE d'un export (implémentation de référence, stdlib seule) :
    recalcule les maillons. Renvoie {ok, empreinte, erreur_n}."""
    prev = ""
    for e in doc.get("entrees") or []:
        prev = maillon_of(prev, int(e["n"]), e["at"], e["action"], e["qui"], e["sceau"])
        if prev != e.get("maillon"):
            return {"ok": False, "empreinte": None, "erreur_n": e.get("n")}
    return {"ok": prev == (doc.get("empreinte") or ""), "empreinte": prev, "erreur_n": None}


def prolonge(ancien: dict, nouveau: dict) -> bool:
    """Le nouvel export prolonge-t-il l'ancien (aucune entrée modifiée ni supprimée) ?"""
    a, b = ancien.get("entrees") or [], nouveau.get("entrees") or []
    if len(b) < len(a):
        return False
    keys = ("n", "at", "action", "qui", "sceau", "maillon")
    return all({k: x.get(k) for k in keys} == {k: y.get(k) for k in keys} for x, y in zip(a, b))


_WHO = {"vous": "Vous", "mandataire": "Mandataire", "partenaire": "Partenaire"}


def export_pdf(payload: dict) -> bytes:
    """PDF lisible du journal du membre (valeurs échappées). La preuve vérifiable est le JSON."""
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def e(v):
        return escape(str(v if v is not None else ""))

    ink, muted, line, head = (colors.HexColor("#0A1730"), colors.HexColor("#5A6573"),
                              colors.HexColor("#DCE2EC"), colors.HexColor("#F1F4F9"))
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, textColor=ink, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12, textColor=ink)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9.5, textColor=muted)
    cell = ParagraphStyle("c", parent=body, fontSize=8, leading=10)
    mono = ParagraphStyle("m", parent=cell, fontName="Courier", fontSize=7, leading=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Journal du groupement", author="Adjugo")
    v = payload.get("verdict") or {}
    story = [
        Paragraph("Journal du groupement — qui a vu quoi", h1),
        Paragraph(f"Marché : {e(payload.get('marche'))}", body),
        Paragraph(f"Partenaire : {e(payload.get('membre'))}", body),
        Paragraph(f"Exporté le {e(_fr_dt(_parse_iso(payload.get('exporte_le'))))}", body),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>Vérification : {e(v.get('verdict_label'))}</b> — {e(v.get('message'))}", body),
        Paragraph(e(payload.get("integrity_label")), small),
        Spacer(1, 4 * mm),
    ]
    data = [[Paragraph("<b>n</b>", cell), Paragraph("<b>Date (UTC)</b>", cell), Paragraph("<b>Qui</b>", cell),
             Paragraph("<b>Événement</b>", cell), Paragraph("<b>Sceau</b>", cell)]]
    for x in payload.get("entrees") or []:
        label = x.get("label") or ""
        if x.get("detail"):
            label += f" · {x['detail']}"
        if x.get("statut") == "alteree":
            label += " — ALTÉRÉE"
        data.append([Paragraph(e(x.get("n")), cell), Paragraph(e(_fr_dt(_parse_iso(x.get("at")))), cell),
                     Paragraph(e(_WHO.get(x.get("qui"), x.get("qui") or "")), cell),
                     Paragraph(e(label), cell), Paragraph(e((x.get("sceau") or "")[:16]), mono)])
    if len(data) == 1:
        data.append([Paragraph("", cell), Paragraph("", cell), Paragraph("", cell),
                     Paragraph("Aucune entrée pour l'instant.", cell), Paragraph("", cell)])
    t = Table(data, colWidths=[9 * mm, 34 * mm, 22 * mm, 85 * mm, 28 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, line),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 5 * mm),
              Paragraph(f"Empreinte de votre journal : <font name='Courier'>{e(payload.get('empreinte'))}</font>", small),
              Paragraph("Pour vérifier vous-même : téléchargez l'export JSON et conservez-le. Chaque export "
                        "suivant doit reprendre à l'identique toutes ses entrées et la même empreinte pour "
                        "sa dernière entrée ; sinon, une entrée a été modifiée ou supprimée. Algorithme : "
                        f"{e(ALGORITHME['maillon'])}.", small)]
    for lim in payload.get("limites") or []:
        story.append(Paragraph("• " + e(lim), small))
    doc.build(story)
    return buf.getvalue()


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).rstrip("Z"))
    except Exception:
        return None


def export_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
