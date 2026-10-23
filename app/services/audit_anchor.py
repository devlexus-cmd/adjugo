"""
Ancrage externe de la tête du journal d'audit (audit cyber oct. 2026, vague 3).

Pourquoi : le journal est chaîné par hachage par owner_id (app/services/audit.py). Une
entrée MODIFIÉE ou retirée au milieu casse la chaîne, mais la suppression des DERNIÈRES
entrées laisse un préfixe parfaitement valide : rien ne la trahissait.

Principe (tâche quotidienne POST /api/admin/run-audit-anchor) :
  1. tête de chaque chaîne = id + hash de la dernière entrée chaînée, et nombre d'entrées ;
  2. toutes les têtes forment UN engagement : SHA-256 d'un JSON canonique trié, qui inclut
     aussi l'engagement de l'ancrage précédent (les ancrages forment eux-mêmes une chaîne) ;
  3. cet engagement est horodaté par une autorité publique RFC 3161 (ANCHOR_TSA_URL). La
     réponse brute est conservée telle quelle, NON vérifiée ici : la vérification se fait
     hors ligne avec `openssl ts -verify` (voir docs/GO_LIVE.md, scripts/anchor_verify.py) ;
  4. le tout est déposé dans le stockage objet sous anchors/AAAA-MM-JJ.json et, si
     ANCHOR_EMAIL est posée, l'engagement part par email (copie hors de l'infrastructure).

Vérification (verify_chain → check_chain) : chaque chaîne est comparée au DERNIER ancrage.
Si la tête ancrée n'existe plus, au même id avec le même hash (ou si des entrées antérieures
manquent), le journal est signalé rompu : « des entrées antérieures au … ont disparu ».

Pertes LÉGITIMES, jamais signalées :
  • effacement RGPD postérieur à l'ancrage : le compte est alors supprimé, ou anonymisé
    (email « deleted-<id>@invalid », inactif, sans organisation — rgpd._drop_or_anonymize_user,
    posé dans la MÊME transaction que la suppression des entrées : pas de fenêtre de course).
    Une chaîne ancrée alors que le compte était DÉJÀ effacé reste vérifiée strictement :
    aucun parcours légitime ne retire ensuite les entrées qui lui restent ;
  • compte démo (réinitialisé à chaque démarrage).
Le statut de chaque propriétaire est relevé AVANT les têtes : un effacement concurrent
ne peut produire qu'un statut « actif » (tolérant), jamais une fausse alerte.

Une tête disparue détectée par la tâche (et non légitime) est REPORTÉE telle quelle dans le
nouvel ancrage (liste « anomalies ») : l'alerte ne s'efface pas d'elle-même au lendemain.

Limites assumées : les entrées écrites depuis le dernier ancrage (moins de 24 h) ne sont
pas couvertes ; un attaquant qui contrôle AUSSI le stockage peut retirer les ancrages côté
serveur — d'où la copie par email et le jeton de l'autorité, vérifiables hors ligne.
La chaîne « système » (owner_id vide) n'est pas ancrée : elle n'est vérifiée nulle part.
"""
import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("adjugo")

PREFIX = "anchors/"
SCHEMA = "adjugo-audit-anchor-v1"
COMMITTED = ("schema", "date", "created_at", "heads", "previous", "anomalies")
_KEY_RX = re.compile(r"^anchors/(\d{4}-\d{2}-\d{2})\.json$")
ACTIVE, ERASED, DEMO = "active", "erased", "demo"

TSA_TIMEOUT = 6.0                 # secondes, budget TOTAL de l'appel à l'autorité
_MAX_TSR = 256 * 1024
_CACHE = {"at": 0.0, "doc": None}
_TTL_HIT, _TTL_MISS = 600, 120    # process unique : cache mémoire du dernier ancrage


def _storage():
    from app.services.storage import get_storage
    return get_storage()


def _settings():
    from app.core.config import get_settings
    return get_settings()


def _chunks(seq, n=500):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ─── DER minimal (requête RFC 3161 + lecture de la réponse, sans dépendance) ──────────

_SHA256_ALG = bytes.fromhex("300d06096086480165030402010500")   # SEQ { OID sha256, NULL }


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _der(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(content)) + content


def _der_uint(v: int) -> bytes:
    """INTEGER positif, encodage minimal (0x00 de tête si le bit de poids fort est à 1)."""
    return _der(0x02, v.to_bytes(v.bit_length() // 8 + 1, "big"))


def build_tsq(digest: bytes, nonce=None) -> bytes:
    """TimeStampReq (RFC 3161 §2.4.1) : version 1, messageImprint {sha256, digest},
    nonce optionnel, certReq TRUE (le jeton embarque le certificat de l'autorité)."""
    if len(digest) != 32:
        raise ValueError("empreinte SHA-256 attendue (32 octets)")
    body = _der(0x02, b"\x01") + _der(0x30, _SHA256_ALG + _der(0x04, digest))
    if nonce is not None:
        body += _der_uint(int(nonce))
    body += b"\x01\x01\xff"
    return _der(0x30, body)


def der_tlv(buf: bytes, pos: int = 0):
    """(tag, début du contenu, fin du contenu) de l'élément DER situé à `pos`."""
    if pos + 2 > len(buf):
        raise ValueError("DER tronqué")
    tag, ln = buf[pos], buf[pos + 1]
    pos += 2
    if ln & 0x80:
        k = ln & 0x7F
        if k == 0 or k > 4 or pos + k > len(buf):
            raise ValueError("longueur DER invalide")
        ln = int.from_bytes(buf[pos:pos + k], "big")
        pos += k
    if pos + ln > len(buf):
        raise ValueError("DER tronqué")
    return tag, pos, pos + ln


def der_children(buf: bytes, start: int, end: int) -> list:
    out, pos = [], start
    while pos < end:
        t, s, e = der_tlv(buf, pos)
        out.append((t, s, e))
        pos = e
    return out


def parse_tsr(tsr: bytes) -> dict:
    """Lecture STRUCTURELLE d'une TimeStampResp (aucune vérification de signature) :
    statut, puis dans le jeton l'empreinte horodatée, la date (genTime) et le nonce."""
    t, s, e = der_tlv(tsr, 0)
    top = der_children(tsr, s, e)
    st = der_children(tsr, top[0][1], top[0][2])
    status = int.from_bytes(tsr[st[0][1]:st[0][2]], "big", signed=True)
    out = {"status": status, "imprint": None, "gen_time": None, "nonce": None}
    if len(top) < 2:
        return out
    ci = der_children(tsr, top[1][1], top[1][2])                   # ContentInfo
    sd = der_children(tsr, ci[1][1], ci[1][2])[0]                   # [0] → SignedData
    eci = der_children(tsr, sd[1], sd[2])[2]                        # encapContentInfo
    wrap = der_children(tsr, eci[1], eci[2])[1]                     # [0] → OCTET STRING
    octet = der_children(tsr, wrap[1], wrap[2])[0]
    tst = tsr[octet[1]:octet[2]]
    t2, s2, e2 = der_tlv(tst, 0)
    f = der_children(tst, s2, e2)                                   # TSTInfo
    mi = der_children(tst, f[2][1], f[2][2])
    out["imprint"] = tst[mi[1][1]:mi[1][2]]
    out["gen_time"] = tst[f[4][1]:f[4][2]].decode("ascii", "replace")
    for (tg, a, b) in f[5:]:
        if tg == 0x02:                                              # seul INTEGER après genTime
            out["nonce"] = int.from_bytes(tst[a:b], "big", signed=True)
            break
    return out


def _post_tsa(url: str, body: bytes, timeout: float) -> bytes:
    """POST application/timestamp-query, budget de temps TOTAL borné (pas seulement par
    phase) : une autorité lente ne retient jamais le thread plus de `timeout` secondes."""
    import httpx
    deadline = time.monotonic() + timeout
    to = httpx.Timeout(timeout, connect=min(3.0, timeout))
    with httpx.Client(timeout=to, follow_redirects=False) as c:
        with c.stream("POST", url, content=body, headers={
                "Content-Type": "application/timestamp-query",
                "Accept": "application/timestamp-reply"}) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > _MAX_TSR:
                    raise RuntimeError("réponse trop volumineuse")
                if time.monotonic() > deadline:
                    raise TimeoutError("délai dépassé")
            return bytes(buf)


def request_timestamp(digest: bytes, url: str = None, timeout: float = TSA_TIMEOUT) -> dict:
    """Demande un jeton d'horodatage. Ne lève jamais : en cas d'échec, {"ok": False,
    "error": <raison>} — l'ancrage est enregistré quand même, sans jeton."""
    url = (url if url is not None else (_settings().ANCHOR_TSA_URL or "")).strip()
    out = {"url": url, "ok": False}
    if not url:
        out["error"] = "aucune autorité configurée (ANCHOR_TSA_URL vide)"
        return out
    nonce = secrets.randbits(64)
    tsq = build_tsq(digest, nonce)
    # Les délais httpx s'appliquent par opération (connexion, chaque lecture…) : un fil dédié
    # borne la durée TOTALE vue par l'appelant, quoi que fasse l'autorité.
    box = {}

    def _call():
        try:
            box["tsr"] = _post_tsa(url, tsq, timeout)
        except Exception as e:
            box["err"] = e
    th = threading.Thread(target=_call, name="tsa-anchor", daemon=True)
    th.start()
    th.join(timeout + 1.0)
    if th.is_alive():
        out["error"] = "autorité injoignable : délai dépassé"
        return out
    if "err" in box or "tsr" not in box:
        e = box.get("err")
        out["error"] = f"autorité injoignable : {type(e).__name__} {str(e)[:150]}".strip()
        return out
    tsr = box["tsr"]
    try:
        info = parse_tsr(tsr)
    except Exception:
        out["error"] = "réponse illisible de l'autorité"
        return out
    if info["status"] not in (0, 1):
        out["error"] = f"demande refusée par l'autorité (statut {info['status']})"
        return out
    if info["imprint"] != digest or (info["nonce"] is not None and info["nonce"] != nonce):
        out["error"] = "jeton incohérent (empreinte ou nonce différents)"
        return out
    out.update(ok=True, gen_time=info["gen_time"], nonce=str(nonce),
               response_b64=base64.b64encode(tsr).decode("ascii"))
    return out


# ─── Engagement ───────────────────────────────────────────────────────────────────────

def canonical(doc: dict) -> bytes:
    """JSON canonique : clés triées, sans espaces, ASCII — reproductible partout."""
    return json.dumps({k: doc[k] for k in COMMITTED}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True).encode("ascii")


def commitment_of(doc: dict) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def validate(doc) -> str:
    """'' si l'ancrage est cohérent ; sinon la raison (fichier altéré ou abîmé)."""
    try:
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            return "schéma inconnu"
        if commitment_of(doc) != doc.get("commitment"):
            return "engagement recalculé différent (fichier modifié)"
        for h in doc["heads"]:
            if not (isinstance(h["owner_id"], int) and isinstance(h["last_id"], int)
                    and isinstance(h["last_hash"], str) and isinstance(h["entries"], int)):
                return "tête mal formée"
        tsa = doc.get("tsa") or {}
        if tsa.get("ok"):
            info = parse_tsr(base64.b64decode(tsa.get("response_b64") or ""))
            if info["imprint"] != bytes.fromhex(doc["commitment"]):
                return "jeton d'horodatage sans rapport avec l'engagement"
        return ""
    except Exception as e:
        return f"ancrage illisible ({type(e).__name__})"


# ─── Lecture des ancrages ─────────────────────────────────────────────────────────────

def _list_days(storage) -> list:
    days = []
    for k in storage.list_keys(PREFIX):
        k = k.replace("\\", "/")
        m = _KEY_RX.match(k)
        if m:
            days.append((m.group(1), k))
    return sorted(days, reverse=True)


def _latest(storage, before: str = None):
    """Dernier ancrage COHÉRENT (antérieur au jour `before` si fourni)."""
    for day, key in [d for d in _list_days(storage) if before is None or d[0] < before][:7]:
        try:
            doc = json.loads(storage.load(key).decode("utf-8"))
        except Exception as e:
            logger.error("ancrage %s illisible : %s", key, type(e).__name__)
            continue
        why = validate(doc)
        if why:
            logger.error("ancrage %s ignoré : %s", key, why)
            continue
        return doc
    return None


def _set_cache(doc) -> None:
    if doc is not None:
        doc = dict(doc)
        doc["_by_owner"] = {h["owner_id"]: h for h in doc.get("heads", [])}
    _CACHE.update(at=time.monotonic(), doc=doc)


def reset_cache() -> None:
    _CACHE.update(at=0.0, doc=None)


def latest_anchor():
    """Dernier ancrage cohérent, mis en cache (process unique). None si aucun ou si le
    stockage est indisponible — la vérification continue alors sans comparaison."""
    hit = _CACHE["doc"]
    if _CACHE["at"] and time.monotonic() - _CACHE["at"] < (_TTL_HIT if hit else _TTL_MISS):
        return hit
    doc = None
    try:
        doc = _latest(_storage())
    except Exception as e:
        logger.warning("ancrage du journal : lecture impossible (%s)", type(e).__name__)
    _set_cache(doc)
    return _CACHE["doc"]


# ─── Statut des propriétaires (pertes légitimes) ──────────────────────────────────────

def _status_of(uid, email, is_active, org_id) -> str:
    from app.services.demo_search import DEMO_EMAIL
    em = (email or "").strip().lower()
    # Marque posée par rgpd._drop_or_anonymize_user, et par elle seule (un utilisateur ne
    # peut ni se désactiver ni confirmer une adresse en « .invalid »).
    if (not is_active) and org_id is None and em == f"deleted-{uid}@invalid":
        return ERASED
    if em == DEMO_EMAIL:
        return DEMO
    return ACTIVE


def owner_status(db, owner_id) -> str:
    from app.models import User
    r = db.query(User.id, User.email, User.is_active, User.org_id).filter(User.id == owner_id).first()
    if r is None:
        return ERASED              # ligne supprimée : seul l'effacement RGPD le fait
    return _status_of(*r)


def _owner_statuses(db, ids) -> dict:
    from app.models import User
    out = {oid: ERASED for oid in ids}
    for chunk in _chunks(ids):
        for r in db.query(User.id, User.email, User.is_active, User.org_id).filter(User.id.in_(chunk)).all():
            out[r[0]] = _status_of(*r)
    return out


def loss_is_legit(db, head: dict) -> bool:
    """La tête ancrée a disparu : est-ce un effacement prévu par l'application ?"""
    if head.get("status") == DEMO:
        return True
    now = owner_status(db, head["owner_id"])
    if now == DEMO:
        return True
    # Effacé APRÈS l'ancrage → légitime. Déjà effacé au moment de l'ancrage → plus aucune
    # suppression légitime possible : comparaison stricte.
    return now == ERASED and head.get("status") != ERASED


# ─── Têtes actuelles ──────────────────────────────────────────────────────────────────

def _chained(AuditLog):
    return (AuditLog.entry_hash.isnot(None), AuditLog.entry_hash != "", AuditLog.owner_id.isnot(None))


def current_heads(db) -> dict:
    """{owner_id: {last_id, last_hash, entries}} : dernière entrée CHAÎNÉE de chaque chaîne."""
    from sqlalchemy import func
    from app.models import AuditLog
    rows = db.query(AuditLog.owner_id, func.max(AuditLog.id), func.count(AuditLog.id)).filter(
        *_chained(AuditLog)).group_by(AuditLog.owner_id).all()
    hashes = {}
    for chunk in _chunks([r[1] for r in rows]):
        hashes.update(dict(db.query(AuditLog.id, AuditLog.entry_hash).filter(AuditLog.id.in_(chunk)).all()))
    return {int(oid): {"last_id": int(mid), "last_hash": hashes.get(mid) or "", "entries": int(n)}
            for oid, mid, n in rows}


def _entries_by_id(db, ids) -> dict:
    from app.models import AuditLog
    out = {}
    for chunk in _chunks(ids):
        for i, oid, h in db.query(AuditLog.id, AuditLog.owner_id, AuditLog.entry_hash).filter(
                AuditLog.id.in_(chunk)).all():
            out[i] = (oid, h or "")
    return out


# ─── Tâche quotidienne ────────────────────────────────────────────────────────────────

def run_anchor(db, now: datetime = None) -> dict:
    """Point d'entrée du cron. Ne lève jamais."""
    try:
        return _run_anchor(db, now or datetime.now(timezone.utc))
    except Exception as e:
        logger.exception("ancrage du journal en échec")
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def _run_anchor(db, now: datetime) -> dict:
    from app.models import AuditLog
    from sqlalchemy import distinct
    day = now.astimezone(timezone.utc).date().isoformat()
    storage = _storage()
    key = f"{PREFIX}{day}.json"
    try:                                     # un seul ancrage horodaté par jour (idempotent)
        today = json.loads(storage.load(key).decode("utf-8"))
        if not validate(today) and (today.get("tsa") or {}).get("ok"):
            return {"ok": True, "skipped": "déjà ancré aujourd'hui", "date": day, "key": key,
                    "commitment": today["commitment"]}
    except Exception:
        pass
    prev = _latest(storage, before=day)

    # Statuts AVANT les têtes (voir docstring du module : aucune fausse alerte possible).
    ids = [r[0] for r in db.query(distinct(AuditLog.owner_id)).filter(*_chained(AuditLog)).all()]
    statuses = _owner_statuses(db, ids)
    heads = {oid: {"owner_id": oid, **h, "status": statuses.get(oid, ACTIVE), "since": day}
             for oid, h in current_heads(db).items()}

    anomalies = []
    if prev:
        present = _entries_by_id(db, [h["last_id"] for h in prev["heads"]])
        for ph in prev["heads"]:
            got = present.get(ph["last_id"])
            if got and got[0] == ph["owner_id"] and got[1] == ph["last_hash"]:
                continue
            if loss_is_legit(db, ph):
                continue
            anomalies.append({k: ph[k] for k in ("owner_id", "last_id", "last_hash", "since")})
            heads[ph["owner_id"]] = dict(ph)      # la tête disparue reste la référence
    doc = {"schema": SCHEMA, "date": day, "created_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
           "heads": sorted(heads.values(), key=lambda h: h["owner_id"]),
           "previous": prev["commitment"] if prev else "", "anomalies": anomalies}
    digest = hashlib.sha256(canonical(doc)).digest()
    doc["commitment"] = digest.hex()
    doc["tsa"] = request_timestamp(digest)

    res = {"ok": True, "date": day, "key": key, "chains": len(doc["heads"]),
           "commitment": doc["commitment"], "previous": doc["previous"] or None,
           "timestamped": bool(doc["tsa"].get("ok")), "tsa_error": doc["tsa"].get("error"),
           "anomalies": len(anomalies)}
    try:
        storage.save(key, json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"), "application/json")
        _set_cache(doc)
    except Exception as e:
        res.update(ok=False, error=f"dépôt de l'ancrage impossible ({type(e).__name__})")
        logger.error("ancrage du journal : dépôt impossible (%s)", type(e).__name__)
    res["emailed"] = _send_email(doc)
    if anomalies:
        logger.error("ancrage du journal : %d chaîne(s) ont perdu leurs dernières entrées : %s",
                     len(anomalies), [a["owner_id"] for a in anomalies])
    if not res["timestamped"]:
        logger.warning("ancrage du journal sans horodatage : %s", res["tsa_error"])
    logger.info("ancrage du journal %s : %d chaînes, engagement %s", day, res["chains"], doc["commitment"][:16])
    return res


def _fr(day: str) -> str:
    try:
        y, m, d = day.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return day or ""


def _send_email(doc: dict) -> bool:
    to = (_settings().ANCHOR_EMAIL or "").strip()
    if not to:
        return False
    tsa = doc.get("tsa") or {}
    lines = [
        "Empreinte quotidienne du journal d'audit Adjugo.",
        "",
        f"Date : {_fr(doc['date'])} (UTC {doc['created_at']})",
        f"Engagement (SHA-256) : {doc['commitment']}",
        f"Engagement précédent : {doc['previous'] or 'aucun'}",
        f"Chaînes couvertes : {len(doc['heads'])}",
        "Horodatage indépendant : " + (f"obtenu ({tsa.get('url')}, {tsa.get('gen_time')})" if tsa.get("ok")
                                       else f"non obtenu ({tsa.get('error')})"),
    ]
    if doc.get("anomalies"):
        lines += ["", f"ATTENTION : {len(doc['anomalies'])} chaîne(s) ont perdu des entrées depuis "
                      "l'empreinte précédente (détail dans le fichier d'ancrage du jour)."]
    lines += ["", "Conservez cet email : il prouve, hors de l'infrastructure Adjugo, l'état du journal "
                  f"à cette date (fichier {PREFIX}{doc['date']}.json, procédure dans docs/GO_LIVE.md)."]
    try:
        from app.services.email import send_email
        return bool(send_email(to, f"Adjugo : empreinte du journal du {_fr(doc['date'])}", "\n".join(lines)))
    except Exception as e:
        logger.warning("ancrage du journal : email non envoyé (%s)", type(e).__name__)
        return False


# ─── Comparaison d'une chaîne au dernier ancrage (appelée par audit.verify_chain) ─────

def check_chain(db, owner_id, rows, upto_id=None) -> dict:
    """`rows` = entrées de la chaîne déjà chargées par verify_chain (id croissants)."""
    res = {"anchor_date": None, "anchor_timestamped": False, "anchor_checked": False,
           "truncated": False, "missing_since": None, "missing_id": None}
    if owner_id is None:
        return res
    anchor = latest_anchor()
    if not anchor:
        return res
    res["anchor_date"] = anchor.get("date")
    res["anchor_timestamped"] = bool((anchor.get("tsa") or {}).get("ok"))
    head = anchor["_by_owner"].get(owner_id)
    if not head or (upto_id is not None and head["last_id"] > upto_id):
        return res                      # chaîne née après l'ancrage, ou hors du préfixe vérifié
    hid = head["last_id"]
    row = next((a for a in rows if a.id == hid), None)
    n = sum(1 for a in rows if a.entry_hash and a.id <= hid)
    if row is not None and (row.entry_hash or "") == head["last_hash"] and n >= head["entries"]:
        res["anchor_checked"] = True
        return res
    if loss_is_legit(db, head):
        return res
    res.update(anchor_checked=True, truncated=True, missing_since=head.get("since") or anchor.get("date"),
               missing_id=hid)
    return res


def message(res: dict) -> str:
    """Phrase d'état, en français simple, pour une chaîne ou une organisation."""
    if res.get("truncated"):
        return f"Des entrées antérieures au {_fr(res.get('missing_since'))} ont disparu du journal."
    if not res.get("intact"):
        return "Une entrée du journal a été modifiée ou supprimée."
    if res.get("anchor_checked") and res.get("anchor_timestamped"):
        return (f"Journal intact. Son empreinte du {_fr(res.get('anchor_date'))} a été horodatée "
                "par une autorité indépendante.")
    if res.get("anchor_checked"):
        return f"Journal intact, conforme à son empreinte du {_fr(res.get('anchor_date'))}."
    return "Journal intact."
