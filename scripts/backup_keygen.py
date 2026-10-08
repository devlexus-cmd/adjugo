"""
Génère la paire de clés de chiffrement des sauvegardes Adjugo.

À lancer sur ton Mac, JAMAIS sur Railway :

    venv/bin/python scripts/backup_keygen.py
    venv/bin/python scripts/backup_keygen.py --sortie ~/Documents/adjugo-cle-sauvegardes.txt

  • la clé PRIVÉE est écrite dans un fichier local (droits 600), chiffrée par un mot de
    passe demandé ici (scrypt + AES-256-GCM). Elle ne sert qu'à RESTAURER une sauvegarde ;
  • la clé PUBLIQUE est affichée : à coller dans Railway, variable BACKUP_PUBLIC_KEY.
    Elle n'est pas secrète : elle permet seulement de chiffrer.

Sans la clé privée ET son mot de passe, les sauvegardes chiffrées sont définitivement
illisibles, y compris pour Adjugo. Procédure complète : docs/GO_LIVE.md.
"""
import argparse
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402

from app.services import backup_crypto as bc  # noqa: E402

MIN_PASSWORD = 12
DEFAULT_OUT = "~/adjugo-cle-sauvegardes.txt"


def generate(path: str, password: str, log2n: int = bc.SCRYPT_LOG2N) -> X25519PrivateKey:
    """Crée le fichier de clé privée (refuse d'écraser) et vérifie qu'il se relit."""
    priv = X25519PrivateKey.generate()
    text = bc.save_private_key(priv, password, log2n=log2n)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    with open(path, encoding="utf-8") as f:
        again = bc.load_private_key(f.read(), password)
    probe = b"adjugo: controle de la paire de cles"
    if bc.decrypt_bytes(bc.encrypt_bytes(probe, priv.public_key()), again) != probe:
        raise RuntimeError("contrôle de la paire de clés en échec")
    return priv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Génère la clé de chiffrement des sauvegardes Adjugo.")
    ap.add_argument("--sortie", default=DEFAULT_OUT,
                    help=f"fichier de clé privée à créer (défaut : {DEFAULT_OUT})")
    args = ap.parse_args(argv)
    path = os.path.abspath(os.path.expanduser(args.sortie))
    if os.path.exists(path):
        print(f"Le fichier {path} existe déjà. Refus de l'écraser : des sauvegardes en dépendent "
              "peut-être. Choisis un autre nom avec --sortie.", file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.dirname(path)):
        print(f"Dossier introuvable : {os.path.dirname(path)}", file=sys.stderr)
        return 1

    print("Choisis un mot de passe long (une phrase de plusieurs mots, par exemple).")
    print("Il sera demandé à chaque restauration. Sans lui, la clé est inutilisable.\n")
    pw = getpass.getpass(f"Mot de passe de la clé ({MIN_PASSWORD} caractères minimum) : ")
    if len(pw) < MIN_PASSWORD:
        print(f"Mot de passe trop court ({len(pw)} caractères).", file=sys.stderr)
        return 1
    if getpass.getpass("Confirme le mot de passe : ") != pw:
        print("Les deux saisies diffèrent. Rien n'a été créé.", file=sys.stderr)
        return 1

    print("\nGénération et contrôle de la clé (quelques secondes)…")
    priv = generate(path, pw)
    pub = priv.public_key()
    pem = pub.public_bytes(serialization.Encoding.PEM,
                           serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    print(f"\nClé privée écrite : {path} (lisible par toi seul)")
    print(f"Empreinte de la clé : {bc.fingerprint_hex(pub)}")
    print("\nÀ coller dans Railway (service de l'API, onglet Variables) :\n")
    print(f"BACKUP_PUBLIC_KEY={bc.public_key_line(pub)}")
    print("\nForme PEM équivalente, si un outil la demande :\n")
    print(pem)
    print("À faire maintenant :")
    print("  1. Range le mot de passe dans ton gestionnaire de mots de passe, avec le contenu")
    print("     du fichier de clé (il fait 4 lignes).")
    print("  2. Fais une copie hors ligne du fichier : impression papier ou clé USB rangée à part.")
    print("     Le fichier seul ne suffit pas : il faut aussi le mot de passe.")
    print("  3. Colle BACKUP_PUBLIC_KEY dans Railway, puis fais le test de restauration décrit")
    print("     dans docs/GO_LIVE.md. Ne mets JAMAIS le fichier de clé privée sur Railway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
