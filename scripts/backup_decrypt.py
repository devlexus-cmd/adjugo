"""
Déchiffre une sauvegarde Adjugo (.json.gz.enc) pour la restaurer. À lancer sur ton Mac.

    venv/bin/python scripts/backup_decrypt.py adjugo-20261009-030000.json.gz.enc
    venv/bin/python scripts/backup_decrypt.py fichier.enc --cle ~/adjugo-cle-sauvegardes.txt \\
        --sortie restauration.json.gz

Le mot de passe de la clé est demandé au clavier. Le déchiffrement se fait en flux (un
bloc d'1 Mio à la fois) : une grosse sauvegarde ne charge pas la mémoire. Le fichier de
sortie n'apparaît qu'une fois le déchiffrement complet et authentifié (jamais de fichier
partiel en cas d'altération ou de troncature). Ensuite, sauf --sans-verification, le
contenu est relu (gzip + JSON) et résumé : c'est le test de restauration minimal.

Restauration complète dans une base : voir docs/GO_LIVE.md.
"""
import argparse
import getpass
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services import backup_crypto as bc  # noqa: E402

DEFAULT_KEY = "~/adjugo-cle-sauvegardes.txt"


def decrypt_file(src_path: str, dst_path: str, key_text: str, password: str) -> int:
    """Déchiffre src → dst (écriture atomique). Lève bc.BackupCryptoError si refus."""
    with open(src_path, "rb") as src:
        head = bc.read_header(src)
    expected = head["fingerprint"].hex()[:16]
    have = bc.key_file_fingerprint(key_text)
    if have != expected:
        raise bc.BackupCryptoError(
            f"cette sauvegarde a été chiffrée avec une autre clé (empreinte {expected}, "
            f"ta clé : {have})")
    priv = bc.load_private_key(key_text, password)
    tmp = dst_path + ".partiel"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(src_path, "rb") as src, os.fdopen(fd, "wb") as dst:
            n = bc.decrypt_stream(src, dst, priv)
        os.replace(tmp, dst_path)
        return n
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def summarize(path: str) -> dict:
    with gzip.open(path, "rb") as f:
        data = json.load(f)
    tables = data.get("tables") or {}
    return {"generated_at": data.get("generated_at"), "schema_version": data.get("schema_version"),
            "tables": len(tables), "rows": sum(len(v or []) for v in tables.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Déchiffre une sauvegarde Adjugo.")
    ap.add_argument("sauvegarde", help="fichier .json.gz.enc téléchargé depuis le stockage")
    ap.add_argument("--cle", default=DEFAULT_KEY, help=f"fichier de clé privée (défaut : {DEFAULT_KEY})")
    ap.add_argument("--sortie", help="fichier .json.gz à créer (défaut : nom de la sauvegarde sans .enc)")
    ap.add_argument("--sans-verification", action="store_true", help="ne pas relire le contenu déchiffré")
    args = ap.parse_args(argv)

    src = os.path.abspath(os.path.expanduser(args.sauvegarde))
    key_path = os.path.abspath(os.path.expanduser(args.cle))
    dst = os.path.abspath(os.path.expanduser(args.sortie)) if args.sortie else (
        src[:-4] if src.endswith(".enc") else src + ".json.gz")
    if os.path.exists(dst):
        print(f"{dst} existe déjà : choisis un autre nom avec --sortie.", file=sys.stderr)
        return 1
    try:
        with open(key_path, encoding="utf-8") as f:
            key_text = f.read()
    except OSError as e:
        print(f"Fichier de clé illisible : {key_path} ({e.strerror})", file=sys.stderr)
        return 1
    try:
        password = getpass.getpass("Mot de passe de la clé : ")
        n = decrypt_file(src, dst, key_text, password)
    except bc.BackupCryptoError as e:
        print(f"Refus : {e}.", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Erreur de fichier : {e}", file=sys.stderr)
        return 1
    print(f"Sauvegarde déchiffrée : {dst} ({n} octets)")
    if not args.sans_verification:
        try:
            s = summarize(dst)
        except Exception as e:
            print(f"Déchiffrée, mais contenu illisible ({type(e).__name__}) : sauvegarde à ne pas "
                  "considérer comme valide.", file=sys.stderr)
            return 3
        print(f"Contenu relu : sauvegarde du {s['generated_at']}, {s['tables']} tables, "
              f"{s['rows']} lignes (format {s['schema_version']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
