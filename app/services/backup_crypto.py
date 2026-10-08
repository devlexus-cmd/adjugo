"""
Chiffrement applicatif des sauvegardes (audit cyber oct. 2026, rang 13).

Principe : chiffrement HYBRIDE à clé publique. Le serveur ne détient que la clé PUBLIQUE
(variable BACKUP_PUBLIC_KEY) : il sait chiffrer, jamais déchiffrer. La clé privée est
générée et conservée hors ligne par le fondateur (scripts/backup_keygen.py) et ne sert
qu'à la restauration (scripts/backup_decrypt.py). Une fuite des identifiants du stockage,
ou de Railway entier, ne donne donc plus accès au contenu des sauvegardes.

Dépendance unique : `cryptography` (déjà présente via python-jose[cryptography]).

────────────────────────────────────────────────────────────────────────────────────────
Format de fichier « ADJUGOBK » version 1 (extension .json.gz.enc)
────────────────────────────────────────────────────────────────────────────────────────
En-tête, 144 octets, entiers en gros-boutiste :

  offset taille champ
     0     8   magie            b"ADJUGOBK"
     8     1   version          0x01
     9    32   empreinte        SHA-256 de la clé publique X25519 destinataire (32 o bruts)
    41    32   clé éphémère     clé publique X25519 éphémère (une par fichier)
    73    12   nonce d'enveloppe
    85    48   clé enveloppée   AES-256-GCM(KEK, nonce d'enveloppe, DEK, aad = octets 0..72)
   133     4   taille de bloc   octets de texte clair par bloc (≤ 16 Mio)
   137     7   préfixe de nonce aléatoire

  DEK = clé de données AES-256-GCM, 32 octets aléatoires, propre au fichier.
  KEK = HKDF-SHA256(X25519(éphémère_privée, destinataire_publique),
                    sel = clé éphémère ‖ clé destinataire, info = b"adjugo-backup v1 kek").

Puis une suite d'enregistrements, jusqu'au bloc final inclus :

  1 octet  drapeau   0x00 = bloc intermédiaire, 0x01 = bloc final
  4 octets L         longueur du chiffré (tag de 16 o inclus), L ≤ taille de bloc + 16
  L octets chiffré   AES-256-GCM(DEK, nonce = préfixe(7) ‖ compteur(4) ‖ drapeau(1),
                                 aad = en-tête complet de 144 octets)

Le compteur (0, 1, 2…) et le drapeau sont dans le nonce : un bloc déplacé, retiré,
dupliqué ou une fin tronquée est refusé au déchiffrement ; l'en-tête est authentifié
par chaque bloc (aad). Le bloc final peut être vide (fichier vide, ou taille multiple
exacte de la taille de bloc). Aucune donnée n'est admise après le bloc final.

Chiffrement et déchiffrement travaillent en flux (un bloc en mémoire à la fois).
"""
import base64
import hashlib
import io
import os
import re
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"ADJUGOBK"
VERSION = 1
HEADER_LEN = 144
DEFAULT_CHUNK = 1 << 20            # 1 Mio de texte clair par bloc
MAX_CHUNK = 16 << 20
TAG_LEN = 16
_KEK_INFO = b"adjugo-backup v1 kek"
_FLAG_MORE, _FLAG_FINAL = 0, 1

# Fichier de clé privée (texte court, imprimable sur papier) — voir save/load_private_key.
KEY_PREFIX = "ADJUGO-BACKUP-KEY-1:"
_KEY_AAD = b"ADJUGO-BACKUP-KEY-1"
SCRYPT_LOG2N = 17                  # 2^17, r=8, p=1 : 128 Mio, ~0,5-1 s sur un Mac récent


class BackupCryptoError(Exception):
    """Erreur lisible (en français) : fichier illisible, mauvaise clé, données altérées."""


# ─── Clé publique ─────────────────────────────────────────────────────────────────────

def load_public_key(text: str) -> X25519PublicKey:
    """Lit la clé publique telle que collée dans Railway. Formats admis : PEM complet,
    PEM dont les retours à la ligne sont devenus « \\n » ou des espaces, ou la seule
    ligne base64 (ce qu'affiche scripts/backup_keygen.py)."""
    s = (text or "").strip().replace("\\n", "\n")
    if not s:
        raise BackupCryptoError("clé publique vide")
    body = re.sub(r"-----(BEGIN|END) PUBLIC KEY-----", "", s)
    body = re.sub(r"\s+", "", body)
    try:
        der = base64.b64decode(body, validate=True)
        key = serialization.load_der_public_key(der)
    except Exception:
        raise BackupCryptoError("clé publique illisible (attendu : la ligne affichée par "
                                "scripts/backup_keygen.py)")
    if not isinstance(key, X25519PublicKey):
        raise BackupCryptoError("clé publique d'un type inattendu (attendu : X25519, "
                                "générée par scripts/backup_keygen.py)")
    return key


def public_key_line(pub: X25519PublicKey) -> str:
    """Forme d'une ligne de la clé publique (base64 du DER SubjectPublicKeyInfo)."""
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def _raw_public(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def fingerprint(pub: X25519PublicKey) -> bytes:
    """Empreinte d'une clé publique : SHA-256 de ses 32 octets bruts."""
    return hashlib.sha256(_raw_public(pub)).digest()


def fingerprint_hex(pub: X25519PublicKey) -> str:
    """Empreinte courte affichable (16 caractères) pour reconnaître la clé utilisée."""
    return fingerprint(pub).hex()[:16]


def _kek(shared: bytes, eph_raw: bytes, rcpt_raw: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph_raw + rcpt_raw,
                info=_KEK_INFO).derive(shared)


# ─── Flux ─────────────────────────────────────────────────────────────────────────────

def _read_exact(src, n: int) -> bytes:
    """Lit n octets (moins seulement en fin de flux), même sur un flux qui rend peu à peu."""
    parts, got = [], 0
    while got < n:
        b = src.read(n - got)
        if not b:
            break
        parts.append(b)
        got += len(b)
    return b"".join(parts)


def _nonce(prefix: bytes, counter: int, flag: int) -> bytes:
    return prefix + struct.pack(">IB", counter, flag)


def encrypt_stream(src, dst, pub: X25519PublicKey, chunk_size: int = DEFAULT_CHUNK) -> int:
    """Chiffre `src` (flux binaire lisible) vers `dst` (flux inscriptible). Renvoie le
    nombre d'octets écrits. Un seul bloc en mémoire à la fois."""
    if not (1 <= chunk_size <= MAX_CHUNK):
        raise ValueError("taille de bloc invalide")
    rcpt_raw = _raw_public(pub)
    eph = X25519PrivateKey.generate()
    eph_raw = _raw_public(eph.public_key())
    kek = _kek(eph.exchange(pub), eph_raw, rcpt_raw)
    dek = AESGCM.generate_key(bit_length=256)
    wrap_nonce = os.urandom(12)
    head = MAGIC + bytes([VERSION]) + hashlib.sha256(rcpt_raw).digest() + eph_raw + wrap_nonce
    wrapped = AESGCM(kek).encrypt(wrap_nonce, dek, head[:73])
    prefix = os.urandom(7)
    header = head + wrapped + struct.pack(">I", chunk_size) + prefix
    assert len(header) == HEADER_LEN
    dst.write(header)
    written = len(header)
    aead = AESGCM(dek)
    counter = 0
    buf = _read_exact(src, chunk_size)
    while True:
        nxt = _read_exact(src, chunk_size) if len(buf) == chunk_size else b""
        flag = _FLAG_FINAL if not nxt else _FLAG_MORE
        ct = aead.encrypt(_nonce(prefix, counter, flag), buf, header)
        dst.write(struct.pack(">BI", flag, len(ct)))
        dst.write(ct)
        written += 5 + len(ct)
        if flag == _FLAG_FINAL:
            return written
        counter += 1
        if counter >= 2 ** 32:
            raise ValueError("fichier trop volumineux pour ce format")
        buf = nxt


def read_header(src) -> dict:
    """Lit et contrôle l'en-tête (sans clé privée) : version, empreinte de la clé."""
    header = _read_exact(src, HEADER_LEN)
    if len(header) < HEADER_LEN or header[:8] != MAGIC:
        raise BackupCryptoError("ce fichier n'est pas une sauvegarde chiffrée Adjugo")
    if header[8] != VERSION:
        raise BackupCryptoError(f"version de format inconnue : {header[8]}")
    chunk_size = struct.unpack(">I", header[133:137])[0]
    if not (1 <= chunk_size <= MAX_CHUNK):
        raise BackupCryptoError("en-tête invalide (taille de bloc)")
    return {"header": header, "fingerprint": header[9:41], "eph": header[41:73],
            "wrap_nonce": header[73:85], "wrapped": header[85:133],
            "chunk_size": chunk_size, "prefix": header[137:144]}


def decrypt_stream(src, dst, priv: X25519PrivateKey) -> int:
    """Déchiffre `src` vers `dst`. Renvoie le nombre d'octets clairs écrits. Lève
    BackupCryptoError (message en français) si la clé est mauvaise, si un bloc a été
    altéré, déplacé ou retiré, ou si le fichier est tronqué."""
    h = read_header(src)
    pub = priv.public_key()
    rcpt_raw = _raw_public(pub)
    if hashlib.sha256(rcpt_raw).digest() != h["fingerprint"]:
        raise BackupCryptoError(
            "cette sauvegarde a été chiffrée avec une autre clé (empreinte attendue "
            f"{h['fingerprint'].hex()[:16]}, clé fournie {fingerprint_hex(pub)})")
    header = h["header"]
    try:
        kek = _kek(priv.exchange(X25519PublicKey.from_public_bytes(h["eph"])), h["eph"], rcpt_raw)
        dek = AESGCM(kek).decrypt(h["wrap_nonce"], h["wrapped"], header[:73])
    except (InvalidTag, ValueError):
        raise BackupCryptoError("clé de déchiffrement refusée (mauvaise clé ou en-tête altéré)")
    aead = AESGCM(dek)
    limit = h["chunk_size"] + TAG_LEN
    counter, out = 0, 0
    while True:
        rec = _read_exact(src, 5)
        if len(rec) < 5:
            raise BackupCryptoError("fichier tronqué : la fin de la sauvegarde manque")
        flag, length = struct.unpack(">BI", rec)
        if flag not in (_FLAG_MORE, _FLAG_FINAL) or not (TAG_LEN <= length <= limit):
            raise BackupCryptoError(f"bloc n° {counter} invalide (fichier altéré)")
        ct = _read_exact(src, length)
        if len(ct) < length:
            raise BackupCryptoError("fichier tronqué : la fin de la sauvegarde manque")
        try:
            pt = aead.decrypt(_nonce(h["prefix"], counter, flag), ct, header)
        except InvalidTag:
            raise BackupCryptoError(f"bloc n° {counter} altéré : la sauvegarde a été modifiée")
        dst.write(pt)
        out += len(pt)
        if flag == _FLAG_FINAL:
            if src.read(1):
                raise BackupCryptoError("données en trop après la fin de la sauvegarde")
            return out
        counter += 1


def encrypt_bytes(data: bytes, pub: X25519PublicKey, chunk_size: int = DEFAULT_CHUNK) -> bytes:
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, pub, chunk_size)
    return out.getvalue()


def decrypt_bytes(blob: bytes, priv: X25519PrivateKey) -> bytes:
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(blob), out, priv)
    return out.getvalue()


def is_encrypted(blob_or_head: bytes) -> bool:
    return bytes(blob_or_head[:8]) == MAGIC


# ─── Fichier de clé privée (protégé par mot de passe) ─────────────────────────────────
#
# Une seule ligne « ADJUGO-BACKUP-KEY-1:<base64> » (≈ 150 caractères, imprimable), où le
# base64 contient : clé publique (32) ‖ sel (16) ‖ log2(N) (1) ‖ r (1) ‖ p (1) ‖ nonce (12)
# ‖ AES-256-GCM(scrypt(mot de passe), clé privée brute 32 o) (48). Le scrypt (128 Mio) rend
# une attaque par force brute du mot de passe coûteuse — bien plus que le PBKDF2 à 2 048
# itérations d'une clé PEM chiffrée classique.

def save_private_key(priv: X25519PrivateKey, password: str, log2n: int = SCRYPT_LOG2N) -> str:
    """Renvoie le contenu texte du fichier de clé privée, chiffré par le mot de passe."""
    if not password:
        raise ValueError("mot de passe requis")
    pub_raw = _raw_public(priv.public_key())
    salt, nonce = os.urandom(16), os.urandom(12)
    r, p = 8, 1
    k = Scrypt(salt=salt, length=32, n=2 ** log2n, r=r, p=p).derive(password.encode("utf-8"))
    raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    ct = AESGCM(k).encrypt(nonce, raw, _KEY_AAD + pub_raw)
    payload = pub_raw + salt + bytes([log2n, r, p]) + nonce + ct
    fp = hashlib.sha256(pub_raw).hexdigest()[:16]
    return ("# Clé privée de déchiffrement des sauvegardes Adjugo. NE JAMAIS la mettre sur Railway.\n"
            f"# Empreinte de la clé publique : {fp}\n"
            "# Protégée par mot de passe (scrypt + AES-256-GCM) : sans lui, ce fichier est inutilisable.\n"
            f"{KEY_PREFIX}{base64.b64encode(payload).decode('ascii')}\n")


def _key_payload(text: str) -> bytes:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    s = re.sub(r"\s+", "", "".join(lines))
    if not s.startswith(KEY_PREFIX):
        raise BackupCryptoError("fichier de clé privée non reconnu (attendu : ADJUGO-BACKUP-KEY-1)")
    try:
        payload = base64.b64decode(s[len(KEY_PREFIX):], validate=True)
    except Exception:
        raise BackupCryptoError("fichier de clé privée illisible (base64 invalide)")
    if len(payload) != 32 + 16 + 3 + 12 + 48:
        raise BackupCryptoError("fichier de clé privée incomplet")
    return payload


def key_file_fingerprint(text: str) -> str:
    """Empreinte courte de la clé publique d'un fichier de clé (sans mot de passe)."""
    return hashlib.sha256(_key_payload(text)[:32]).hexdigest()[:16]


def load_private_key(text: str, password: str) -> X25519PrivateKey:
    payload = _key_payload(text)
    pub_raw, salt = payload[:32], payload[32:48]
    log2n, r, p = payload[48], payload[49], payload[50]
    nonce, ct = payload[51:63], payload[63:]
    if not (10 <= log2n <= 22) or not (1 <= r <= 32) or not (1 <= p <= 16):
        raise BackupCryptoError("fichier de clé privée invalide (paramètres)")
    k = Scrypt(salt=salt, length=32, n=2 ** log2n, r=r, p=p).derive((password or "").encode("utf-8"))
    try:
        raw = AESGCM(k).decrypt(nonce, ct, _KEY_AAD + pub_raw)
    except InvalidTag:
        raise BackupCryptoError("mot de passe incorrect (ou fichier de clé altéré)")
    priv = X25519PrivateKey.from_private_bytes(raw)
    if _raw_public(priv.public_key()) != pub_raw:
        raise BackupCryptoError("fichier de clé privée incohérent")
    return priv
