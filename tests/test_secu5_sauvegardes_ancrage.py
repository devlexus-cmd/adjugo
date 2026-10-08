"""Non-régression — audit cyber oct. 2026, vague 3 : sauvegardes chiffrées + ancrage du journal.

Sauvegardes (rang 13) :
  • aller-retour chiffrement → déchiffrement sur plusieurs Mo, en flux, via les scripts ;
  • refus avec une autre clé, un mauvais mot de passe, un bloc altéré, un fichier tronqué ;
  • sans BACKUP_PUBLIC_KEY (ou clé invalide) : la sauvegarde part en clair, avec avertissement.
Ancrage du journal d'audit :
  • l'ancrage enregistre les têtes, l'engagement et le jeton ;
  • la suppression de la dernière entrée après l'ancrage est détectée (et reste signalée) ;
  • un effacement RGPD légitime après l'ancrage n'est PAS signalé (piège déjà rencontré) ;
  • une autorité d'horodatage injoignable donne un ancrage sans jeton, sans exception ;
  • la requête RFC 3161 est un DER valide, identique à `openssl ts -query`.
"""
import base64
import gzip
import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import backup_crypto as bc
from app.services.audit_anchor import _post_tsa as _ORIGINAL_POST   # vrai client, avant tout monkeypatch


# ─── Aides ────────────────────────────────────────────────────────────────────────────

def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _tok(uid):
    from app.core.security import create_access_token
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        return create_access_token(data={"sub": str(uid), "tv": int(u.token_version or 0)})
    finally:
        db.close()


def _register(client, prefix="anc"):
    from app.models import User
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": prefix, "company_name": prefix + " SARL"})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        return u.id
    finally:
        db.close()


def _member(client, owner_id, prefix="sal"):
    from app.core.security import hash_password
    from app.models import User
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=_h(_tok(owner_id)), json={"email": email, "full_name": prefix})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        u.hashed_password = hash_password("motdepasse123")
        db.commit()
        return u.id
    finally:
        db.close()


def _delete_account(client, uid):
    return client.post("/api/rgpd/delete-account", headers=_h(_tok(uid)),
                       json={"password": "motdepasse123", "confirm": "SUPPRIMER"})


def _record(**kw):
    from app.services import audit
    db = _db()
    try:
        audit.record(db, **kw)
    finally:
        db.close()


def _chain(uid):
    from app.services import audit
    db = _db()
    try:
        return audit.verify_chain(db, uid)
    finally:
        db.close()


def _last_entry_id(owner_id):
    from app.models import AuditLog
    db = _db()
    try:
        return db.query(AuditLog.id).filter(AuditLog.owner_id == owner_id).order_by(AuditLog.id.desc()).first()[0]
    finally:
        db.close()


def _delete_entry(entry_id):
    from app.models import AuditLog
    db = _db()
    try:
        db.query(AuditLog).filter(AuditLog.id == entry_id).delete()
        db.commit()
    finally:
        db.close()


def _anchor(now=None):
    from app.services.audit_anchor import run_anchor
    db = _db()
    try:
        return run_anchor(db, now=now)
    finally:
        db.close()


class _MemStorage:
    """Stockage objet en mémoire (même interface que app.services.storage)."""
    def __init__(self):
        self.objects = {}

    def save(self, key, content, content_type=None):
        self.objects[key] = bytes(content)
        return key

    def load(self, key):
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]

    def delete(self, key):
        self.objects.pop(key, None)

    def list_keys(self, prefix=""):
        return [k for k in self.objects if k.startswith(prefix)]


def _fake_tsr(digest, nonce, status=0, gen_time=b"20261008030000Z"):
    """TimeStampResp minimale mais structurellement conforme (RFC 3161 / CMS), sans signature."""
    from app.services.audit_anchor import _SHA256_ALG, _der, _der_uint
    tst = _der(0x30, _der(0x02, b"\x01") + _der(0x06, bytes.fromhex("2a030401"))
               + _der(0x30, _SHA256_ALG + _der(0x04, digest)) + _der_uint(4242)
               + _der(0x18, gen_time) + _der_uint(nonce))
    eci = _der(0x30, _der(0x06, bytes.fromhex("2a864886f70d0109100104")) + _der(0xA0, _der(0x04, tst)))
    sd = _der(0x30, _der(0x02, b"\x03") + _der(0x31, _der(0x30, _SHA256_ALG)) + eci + _der(0x31, b""))
    token = _der(0x30, _der(0x06, bytes.fromhex("2a864886f70d010702")) + _der(0xA0, sd))
    return _der(0x30, _der(0x30, _der(0x02, bytes([status]))) + token)


def _decode_tsq(body):
    from app.services.audit_anchor import der_children, der_tlv
    t, s, e = der_tlv(body)
    assert t == 0x30 and e == len(body)
    kids = der_children(body, s, e)
    return body, kids


def _fake_post(url, body, timeout):
    """Autorité factice : répond un jeton accordé pour l'empreinte et le nonce demandés."""
    from app.services.audit_anchor import der_children
    _, kids = _decode_tsq(body)
    mi = der_children(body, kids[1][1], kids[1][2])
    digest = body[mi[1][1]:mi[1][2]]
    nonce = int.from_bytes(body[kids[2][1]:kids[2][2]], "big")
    return _fake_tsr(digest, nonce)


@pytest.fixture
def anchor_env(monkeypatch):
    """Ancrages dans un stockage en mémoire, autorité factice, cache vidé avant/après."""
    from app.core.config import get_settings
    from app.services import audit_anchor
    st = _MemStorage()
    monkeypatch.setattr(audit_anchor, "_storage", lambda: st)
    monkeypatch.setattr(audit_anchor, "_post_tsa", _fake_post)
    monkeypatch.setattr(get_settings(), "ANCHOR_TSA_URL", "https://tsa.invalid/tsr")
    monkeypatch.setattr(get_settings(), "ANCHOR_EMAIL", "")
    audit_anchor.reset_cache()
    yield st
    audit_anchor.reset_cache()


@pytest.fixture
def fk_on():
    """Clés étrangères appliquées comme sous PostgreSQL en production."""
    from sqlalchemy import event
    from app.core.database import engine

    def _on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
    event.listen(engine, "connect", _on)
    engine.dispose()
    yield
    event.remove(engine, "connect", _on)
    engine.dispose()


def _keypair(tmp_path, password="phrase de passe solide"):
    from scripts.backup_keygen import generate
    path = str(tmp_path / "cle.txt")
    priv = generate(path, password, log2n=14)          # scrypt allégé pour la vitesse des tests
    with open(path, encoding="utf-8") as f:
        return priv, path, f.read()


# ═══ 1. Sauvegardes chiffrées ═════════════════════════════════════════════════════════

def test_chiffrement_aller_retour_plusieurs_mo_en_flux(tmp_path):
    from scripts.backup_decrypt import decrypt_file
    priv, key_path, key_text = _keypair(tmp_path)
    assert oct(os.stat(key_path).st_mode & 0o777) == "0o600"        # fichier de clé protégé
    assert "ADJUGO-BACKUP-KEY-1:" in key_text and bc.SCRYPT_LOG2N >= 17
    # 6 Mio + reliquat : plusieurs blocs, dernier bloc partiel ; contenu mi-aléatoire mi-répétitif.
    data = os.urandom(3 << 20) + (b"adjugo " * 500_000) + os.urandom(12345)
    src, enc, out = tmp_path / "dump.json.gz", tmp_path / "dump.json.gz.enc", tmp_path / "restaure.json.gz"
    src.write_bytes(data)
    pub = bc.load_public_key(bc.public_key_line(priv.public_key()))
    with open(src, "rb") as fi, open(enc, "wb") as fo:
        written = bc.encrypt_stream(fi, fo, pub)
    blob = enc.read_bytes()
    assert written == len(blob) and blob[:8] == b"ADJUGOBK" and blob[8] == 1
    n_chunks = -(-len(data) // bc.DEFAULT_CHUNK)
    assert len(blob) == bc.HEADER_LEN + len(data) + n_chunks * (5 + bc.TAG_LEN)
    assert data[:4096] not in blob                                  # rien en clair
    assert decrypt_file(str(enc), str(out), key_text, "phrase de passe solide") == len(data)
    assert hashlib.sha256(out.read_bytes()).digest() == hashlib.sha256(data).digest()
    # Taille exactement multiple d'un bloc, et fichier vide : bloc final vide, aller-retour exact.
    for d in (b"", os.urandom(2 * bc.DEFAULT_CHUNK)):
        assert bc.decrypt_bytes(bc.encrypt_bytes(d, pub), priv) == d


def test_dechiffrement_refuse_mauvaise_cle_mot_de_passe_alteration_troncature(tmp_path):
    from scripts.backup_decrypt import decrypt_file
    priv, _, key_text = _keypair(tmp_path)
    other_dir = tmp_path / "autre"
    other_dir.mkdir()
    other, _, other_text = _keypair(other_dir)
    blob = bc.encrypt_bytes(os.urandom(2_500_000), priv.public_key())
    enc = tmp_path / "s.json.gz.enc"
    enc.write_bytes(blob)
    out = tmp_path / "s.json.gz"
    # Une autre clé : refus clair, avant même le mot de passe.
    with pytest.raises(bc.BackupCryptoError, match="autre clé"):
        decrypt_file(str(enc), str(out), other_text, "phrase de passe solide")
    with pytest.raises(bc.BackupCryptoError, match="autre clé"):
        bc.decrypt_bytes(blob, other)
    # Bonne clé, mauvais mot de passe.
    with pytest.raises(bc.BackupCryptoError, match="mot de passe incorrect"):
        decrypt_file(str(enc), str(out), key_text, "pas le bon")
    # Un octet modifié dans le 2e bloc, puis un fichier tronqué : refus, aucun fichier partiel.
    bad = bytearray(blob)
    bad[bc.HEADER_LEN + 5 + bc.DEFAULT_CHUNK + 16 + 5 + 100] ^= 0x01
    enc.write_bytes(bytes(bad))
    with pytest.raises(bc.BackupCryptoError, match="altéré"):
        decrypt_file(str(enc), str(out), key_text, "phrase de passe solide")
    enc.write_bytes(blob[:-7])
    with pytest.raises(bc.BackupCryptoError, match="tronqué"):
        decrypt_file(str(enc), str(out), key_text, "phrase de passe solide")
    enc.write_bytes(blob[:bc.HEADER_LEN + 5 + bc.DEFAULT_CHUNK + 16])   # coupé net après un bloc
    with pytest.raises(bc.BackupCryptoError, match="tronqué"):
        decrypt_file(str(enc), str(out), key_text, "phrase de passe solide")
    enc.write_bytes(blob + b"\x00")
    with pytest.raises(bc.BackupCryptoError, match="en trop"):
        decrypt_file(str(enc), str(out), key_text, "phrase de passe solide")
    assert not out.exists() and not os.path.exists(str(out) + ".partiel")
    with pytest.raises(bc.BackupCryptoError, match="pas une sauvegarde chiffrée"):
        bc.decrypt_bytes(gzip.compress(b"{}"), priv)


def test_keygen_refuse_d_ecraser_une_cle(tmp_path, monkeypatch):
    import scripts.backup_keygen as kg
    _, key_path, _ = _keypair(tmp_path)
    with pytest.raises(FileExistsError):
        kg.generate(key_path, "phrase de passe solide", log2n=14)
    monkeypatch.setattr(kg.getpass, "getpass", lambda *_a, **_k: "phrase de passe solide")
    assert kg.main(["--sortie", key_path]) == 1


def test_cle_publique_acceptee_sous_toutes_ses_formes(tmp_path):
    from cryptography.hazmat.primitives import serialization
    priv, _, _ = _keypair(tmp_path)
    pub = priv.public_key()
    pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    for form in (pem, pem.replace("\n", "\\n"), pem.replace("\n", " "), bc.public_key_line(pub)):
        assert bc.fingerprint(bc.load_public_key(form)) == bc.fingerprint(pub)
    with pytest.raises(bc.BackupCryptoError):
        bc.load_public_key("n'importe quoi")


@pytest.fixture
def backup_env(monkeypatch):
    from app.core.config import get_settings
    from app.services import backup, storage
    st = _MemStorage()
    monkeypatch.setattr(storage, "get_storage", lambda: st)
    monkeypatch.setattr(backup, "_backend_is_object", lambda: True)
    monkeypatch.setattr(get_settings(), "BACKUP_PUBLIC_KEY", "")
    return st


def test_sauvegarde_sans_cle_configuree_reste_en_clair_avec_avertissement(backup_env, caplog):
    from app.services.backup import run_backup
    with caplog.at_level(logging.WARNING, logger="adjugo"):
        r = run_backup(keep=14)
    assert r["ok"] is True and r["encrypted"] is False
    assert r["key"].endswith(".json.gz") and "BACKUP_PUBLIC_KEY absente" in r["warning"]
    assert any("non chiffrée" in m for m in caplog.messages)
    dump = json.loads(gzip.decompress(backup_env.objects[r["key"]]))
    assert "users" in dump["tables"] and dump["schema_version"] == "logical-v1"


def test_sauvegarde_chiffree_avec_la_cle_publique(backup_env, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services.backup import restore_backup, run_backup
    priv, _, _ = _keypair(tmp_path)
    monkeypatch.setattr(get_settings(), "BACKUP_PUBLIC_KEY", bc.public_key_line(priv.public_key()))
    for old in ("backups/adjugo-20200101-000000.json.gz", "backups/adjugo-20200102-000000.json.gz.enc"):
        backup_env.save(old, b"ancienne")
    r = run_backup(keep=2)
    assert r["ok"] is True and r["encrypted"] is True and "warning" not in r
    assert r["key"].endswith(".json.gz.enc") and r["key_fingerprint"] == bc.fingerprint_hex(priv.public_key())
    blob = backup_env.objects[r["key"]]
    assert blob[:8] == b"ADJUGOBK" and b'"tables"' not in blob
    dump = json.loads(gzip.decompress(bc.decrypt_bytes(blob, priv)))
    assert "audit_logs" in dump["tables"] and r["pruned"] == 1
    assert sorted(backup_env.list_keys("backups/")) == ["backups/adjugo-20200102-000000.json.gz.enc", r["key"]]
    # La restauration refuse un fichier encore chiffré, avec la marche à suivre.
    with pytest.raises(ValueError, match="backup_decrypt"):
        restore_backup(blob, None)


def test_cle_publique_invalide_ne_bloque_jamais_la_sauvegarde(backup_env, monkeypatch, caplog):
    from app.core.config import get_settings
    from app.services.backup import run_backup
    monkeypatch.setattr(get_settings(), "BACKUP_PUBLIC_KEY", "collée de travers")
    with caplog.at_level(logging.WARNING, logger="adjugo"):
        r = run_backup(keep=14)
    assert r["ok"] is True and r["encrypted"] is False and "invalide" in r["warning"]
    assert r["key"].endswith(".json.gz")


# ═══ 2. Ancrage externe de la tête du journal ═════════════════════════════════════════

def test_requete_horodatage_der_valide():
    from app.services.audit_anchor import build_tsq, der_children
    digest = hashlib.sha256(b"engagement").digest()
    nonce = 0xF1E2D3C4B5A69788                      # bit de poids fort à 1 : octet 0x00 de tête
    body, kids = _decode_tsq(build_tsq(digest, nonce))
    assert [k[0] for k in kids] == [0x02, 0x30, 0x02, 0x01]
    assert body[kids[0][1]:kids[0][2]] == b"\x01"                              # version v1
    alg, hashed = der_children(body, kids[1][1], kids[1][2])
    oid, null = der_children(body, alg[1], alg[2])
    assert body[oid[1]:oid[2]] == bytes.fromhex("608648016503040201")         # 2.16.840.1.101.3.4.2.1
    assert null[0] == 0x05 and null[1] == null[2]                              # paramètres NULL
    assert hashed[0] == 0x04 and body[hashed[1]:hashed[2]] == digest
    raw_nonce = body[kids[2][1]:kids[2][2]]
    assert raw_nonce[0] == 0 and int.from_bytes(raw_nonce, "big") == nonce
    assert body[kids[3][1]:kids[3][2]] == b"\xff"                              # certReq TRUE
    assert len(build_tsq(digest, None)) == len(body) - 2 - len(raw_nonce)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl indisponible")
def test_requete_horodatage_identique_a_openssl(tmp_path):
    from app.services.audit_anchor import build_tsq, der_children
    digest = hashlib.sha256(b"adjugo").digest()
    q1, q2 = tmp_path / "a.tsq", tmp_path / "b.tsq"
    base = ["openssl", "ts", "-query", "-digest", digest.hex(), "-sha256", "-cert"]
    subprocess.run(base + ["-no_nonce", "-out", str(q1)], check=True, capture_output=True)
    assert build_tsq(digest, None) == q1.read_bytes()
    subprocess.run(base + ["-out", str(q2)], check=True, capture_output=True)
    ref, kids = _decode_tsq(q2.read_bytes())
    assert build_tsq(digest, int.from_bytes(ref[kids[2][1]:kids[2][2]], "big")) == ref


def test_ancrage_enregistre_les_tetes_et_l_engagement(client, anchor_env, monkeypatch):
    from app.core.config import get_settings
    from app.models import AuditLog
    from app.services import audit_anchor
    sent = []
    monkeypatch.setattr(get_settings(), "ANCHOR_EMAIL", "ancrage@test.fr")
    monkeypatch.setattr("app.services.email.send_email", lambda to, subj, text, html=None: sent.append((to, subj, text)) or True)
    O = _register(client, "tete")
    for i in range(3):
        _record(action="offer.frozen", owner_id=O, actor=f"t{i}", actor_kind="owner")
    now = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    r = _anchor(now)
    assert r["ok"] is True and r["timestamped"] is True and r["anomalies"] == 0 and r["emailed"] is True
    assert r["key"] == "anchors/2026-10-08.json"
    doc = json.loads(anchor_env.objects[r["key"]])
    assert audit_anchor.validate(doc) == "" and doc["commitment"] == r["commitment"]
    assert doc["commitment"] == hashlib.sha256(audit_anchor.canonical(doc)).hexdigest()
    db = _db()
    try:
        last = db.query(AuditLog).filter(AuditLog.owner_id == O).order_by(AuditLog.id.desc()).first()
        head = next(h for h in doc["heads"] if h["owner_id"] == O)
        assert head == {"owner_id": O, "last_id": last.id, "last_hash": last.entry_hash,
                        "entries": 3, "status": "active", "since": "2026-10-08"}
    finally:
        db.close()
    info = audit_anchor.parse_tsr(base64.b64decode(doc["tsa"]["response_b64"]))
    assert info["imprint"] == bytes.fromhex(doc["commitment"]) and str(info["nonce"]) == doc["tsa"]["nonce"]
    # Email court : la date et l'engagement, rien d'autre de sensible.
    to, subj, text = sent[0]
    assert to == "ancrage@test.fr" and "08/10/2026" in subj and doc["commitment"] in text
    assert "@test.fr" not in text
    # Idempotent dans la journée ; le lendemain, l'ancrage cite le précédent.
    assert _anchor(now + timedelta(hours=2))["skipped"]
    r2 = _anchor(now + timedelta(days=1))
    assert r2["previous"] == r["commitment"]
    # Intégrité exposée : champs ajoutés, format d'origine conservé.
    integ = client.get("/api/audit/integrity", headers=_h(_tok(O))).json()
    for k in ("owner_id", "entries", "chained_entries", "intact", "broken_at_id", "chains"):
        assert k in integ
    assert integ["intact"] is True and integ["anchor_checked"] is True and integ["truncated"] is False
    assert integ["anchor_date"] == "2026-10-09" and "horodatée par une autorité indépendante" in integ["message"]


def test_suppression_de_la_derniere_entree_apres_ancrage_detectee(client, anchor_env):
    from app.services import audit_anchor
    O = _register(client, "queue")
    for i in range(4):
        _record(action="guest.view_project", owner_id=O, actor=f"p{i}", actor_kind="guest")
    now = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    assert _anchor(now)["ok"] is True
    assert _chain(O)["intact"] is True
    _delete_entry(_last_entry_id(O))
    # Sans ancrage, le préfixe restant paraît parfaitement valide (le défaut d'origine)…
    audit_anchor.reset_cache()
    saved = dict(anchor_env.objects)
    anchor_env.objects.clear()
    assert _chain(O)["intact"] is True
    # … avec l'ancrage, la disparition est signalée.
    anchor_env.objects.update(saved)
    audit_anchor.reset_cache()
    res = _chain(O)
    assert res["intact"] is False and res["truncated"] is True and res["missing_since"] == "2026-10-08"
    assert res["message"] == "Des entrées antérieures au 08/10/2026 ont disparu du journal."
    integ = client.get("/api/audit/integrity", headers=_h(_tok(O))).json()
    assert integ["intact"] is False and integ["truncated"] is True and "ont disparu" in integ["message"]
    # Une nouvelle entrée puis l'ancrage du lendemain ne « blanchissent » pas la suppression :
    # la tête disparue est reportée et signalée en anomalie.
    _record(action="guest.view_project", owner_id=O, actor="apres", actor_kind="guest")
    r2 = _anchor(now + timedelta(days=1))
    assert r2["anomalies"] == 1
    doc2 = json.loads(anchor_env.objects[r2["key"]])
    assert [a["owner_id"] for a in doc2["anomalies"]] == [O]
    assert next(h for h in doc2["heads"] if h["owner_id"] == O)["since"] == "2026-10-08"
    integ = client.get("/api/audit/integrity", headers=_h(_tok(O))).json()
    assert integ["intact"] is False and integ["missing_since"] == "2026-10-08"


def test_effacement_rgpd_legitime_apres_ancrage_non_signale(client, anchor_env, fk_on):
    """Ex-fondateur F (propriété transférée à R, puis retiré) qui a écrit de nouvelles entrées
    sur SON marché, puis efface son compte : la queue de sa chaîne disparaît légitimement.
    R vérifie encore la chaîne de F (historique de l'entreprise) : aucune fausse alerte."""
    from app.models import AuditLog, User
    F = _register(client, "fondanc")
    R = _member(client, F, "repanc")
    p = client.post("/api/projects/", headers=_h(_tok(F)), json={"name": "AO Ecole", "client": "Ville"}).json()
    for _ in range(3):
        _record(action="offer.frozen", owner_id=F, project_id=p["id"], actor="fondateur", actor_kind="owner")
    assert client.post("/api/org/transfer-ownership", headers=_h(_tok(F)), json={"new_owner_id": R}).status_code == 200
    assert client.delete(f"/api/org/members/{F}", headers=_h(_tok(R))).status_code == 200
    mine = client.post("/api/projects/", headers=_h(_tok(F)), json={"name": "AO perso"}).json()["id"]
    for _ in range(2):
        _record(action="offer.frozen", owner_id=F, project_id=mine, actor="fondateur", actor_kind="owner")
    tail = _last_entry_id(F)
    now = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    r = _anchor(now)
    doc = json.loads(anchor_env.objects[r["key"]])
    assert next(h for h in doc["heads"] if h["owner_id"] == F)["last_id"] == tail
    before = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert before["intact"] is True and F in [c["owner_id"] for c in before["chains"]]

    assert _delete_account(client, F).status_code == 200
    db = _db()
    try:
        assert db.query(AuditLog).filter(AuditLog.id == tail).first() is None   # queue effacée
        u = db.get(User, F)
        assert u is not None and u.email == f"deleted-{F}@invalid"              # anonymisé
    finally:
        db.close()
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is True and integ["truncated"] is False, integ
    assert F in [c["owner_id"] for c in integ["chains"]]
    r2 = _anchor(now + timedelta(days=1))
    assert r2["anomalies"] == 0
    doc2 = json.loads(anchor_env.objects[r2["key"]])
    head_f = next(h for h in doc2["heads"] if h["owner_id"] == F)
    assert head_f["status"] == "erased" and head_f["last_id"] < tail
    # Compte DÉJÀ effacé au moment de l'ancrage : plus aucune suppression n'est légitime.
    _delete_entry(head_f["last_id"])
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is False and integ["truncated"] is True


def test_effacement_solo_et_compte_demo_non_signales(client, anchor_env, fk_on):
    from app.models import User
    from app.services.demo_search import DEMO_EMAIL
    U = _register(client, "soloanc")
    pid = client.post("/api/projects/", headers=_h(_tok(U)), json={"name": "AO solo"}).json()["id"]
    _record(action="offer.frozen", owner_id=U, project_id=pid, actor="x", actor_kind="owner")
    _record(action="team.role_changed", owner_id=U, actor="x", actor_kind="owner")
    db = _db()
    try:
        demo = db.query(User).filter(User.email == DEMO_EMAIL).first().id
    finally:
        db.close()
    _record(action="guest.view_project", owner_id=demo, actor="vitrine", actor_kind="guest")
    now = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    _anchor(now)
    assert _delete_account(client, U).status_code == 200
    _delete_entry(_last_entry_id(demo))                 # comme la réinitialisation de la démo
    db = _db()
    try:
        assert db.get(User, U) is None                  # effacement complet : ligne supprimée
    finally:
        db.close()
    assert _chain(U)["intact"] is True and _chain(U)["truncated"] is False
    assert _chain(demo)["truncated"] is False
    assert _anchor(now + timedelta(days=1))["anomalies"] == 0


def test_autorite_injoignable_ancrage_sans_jeton_sans_exception(client, anchor_env, monkeypatch):
    from app.core.config import get_settings
    from app.services import audit_anchor
    O = _register(client, "tsa")
    _record(action="offer.frozen", owner_id=O, actor="x", actor_kind="owner")
    # Vraie pile réseau (httpx), port fermé en local : échec immédiat, aucune exception.
    monkeypatch.setattr(audit_anchor, "_post_tsa", _ORIGINAL_POST)
    monkeypatch.setattr(get_settings(), "ANCHOR_TSA_URL", "http://127.0.0.1:9/tsr")
    t0 = time.monotonic()
    r = _anchor(datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc))
    assert time.monotonic() - t0 < audit_anchor.TSA_TIMEOUT + 2
    assert r["ok"] is True and r["timestamped"] is False and "injoignable" in r["tsa_error"]
    doc = json.loads(anchor_env.objects[r["key"]])
    assert doc["tsa"]["ok"] is False and "response_b64" not in doc["tsa"]
    assert audit_anchor.validate(doc) == "" and any(h["owner_id"] == O for h in doc["heads"])
    res = _chain(O)
    assert res["intact"] is True and res["anchor_checked"] is True and res["anchor_timestamped"] is False
    assert "conforme à son empreinte du 08/10/2026" in res["message"]
    # Autres échecs de l'autorité : exception quelconque, réponse illisible, refus, jeton faux.
    digest = hashlib.sha256(b"x").digest()
    for post, attendu in (
        (lambda *a: (_ for _ in ()).throw(RuntimeError("panne")), "injoignable"),
        (lambda *a: b"pas du DER", "illisible"),
        (lambda u, b, t: _fake_tsr(digest, 1, status=2), "refusée"),
        (lambda u, b, t: _fake_tsr(hashlib.sha256(b"autre").digest(), 1), "incohérent"),
    ):
        monkeypatch.setattr(audit_anchor, "_post_tsa", post)
        out = audit_anchor.request_timestamp(digest, url="https://tsa.invalid/tsr")
        assert out["ok"] is False and attendu in out["error"]
    # Autorité qui traîne : la durée totale reste bornée, quel que soit le comportement réseau.
    monkeypatch.setattr(audit_anchor, "_post_tsa", lambda u, b, t: time.sleep(3) or b"")
    t0 = time.monotonic()
    out = audit_anchor.request_timestamp(digest, url="https://tsa.invalid/tsr", timeout=0.2)
    assert time.monotonic() - t0 < 2 and out["ok"] is False and "délai dépassé" in out["error"]
    monkeypatch.setattr(get_settings(), "ANCHOR_TSA_URL", "")
    assert "aucune autorité" in audit_anchor.request_timestamp(digest)["error"]


def test_route_cron_protegee_et_jamais_en_echec(client, anchor_env, monkeypatch):
    from app.core.config import get_settings
    from app.services import audit_anchor
    monkeypatch.setattr(get_settings(), "CRON_SECRET", "secret-ancrage-test")
    assert client.post("/api/admin/run-audit-anchor").status_code == 403
    assert client.post("/api/admin/run-audit-anchor", headers={"X-Cron-Secret": "faux"}).status_code == 403
    r = client.post("/api/admin/run-audit-anchor", headers={"X-Cron-Secret": "secret-ancrage-test"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # Même une panne interne inattendue ne fait pas échouer le cron.
    monkeypatch.setattr(audit_anchor, "current_heads", lambda db: 1 / 0)
    audit_anchor.reset_cache()
    anchor_env.objects.clear()
    r = client.post("/api/admin/run-audit-anchor", headers={"X-Cron-Secret": "secret-ancrage-test"})
    assert r.status_code == 200 and r.json()["ok"] is False and "ZeroDivisionError" in r.json()["error"]


def test_ancrage_altere_ignore_et_script_de_verification(client, anchor_env, tmp_path, caplog):
    from app.services import audit_anchor
    from scripts.anchor_verify import main as verify_main
    O = _register(client, "alt")
    _record(action="offer.frozen", owner_id=O, actor="x", actor_kind="owner")
    now = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    r1 = _anchor(now)
    r2 = _anchor(now + timedelta(days=1))
    d1, d2 = (json.loads(anchor_env.objects[k]) for k in (r1["key"], r2["key"]))
    p1, p2 = tmp_path / "2026-10-08.json", tmp_path / "2026-10-09.json"
    p1.write_text(json.dumps(d1))
    p2.write_text(json.dumps(d2))
    assert verify_main([str(p1), str(p2), "--engagement", d2["commitment"]]) == 0
    assert (tmp_path / "2026-10-09.tsr").exists()
    assert verify_main([str(p2), "--engagement", "0" * 64]) == 1
    # Fichier d'ancrage modifié sans recalcul : ignoré côté serveur (repli sur le précédent),
    # et dénoncé par le script hors ligne.
    d2["heads"] = [h for h in d2["heads"] if h["owner_id"] != O]
    anchor_env.objects[r2["key"]] = json.dumps(d2).encode()
    p2.write_text(json.dumps(d2))
    audit_anchor.reset_cache()
    with caplog.at_level(logging.ERROR, logger="adjugo"):
        latest = audit_anchor.latest_anchor()
    assert latest["date"] == "2026-10-08" and any("ignoré" in m for m in caplog.messages)
    assert verify_main([str(p1), str(p2)]) == 1
