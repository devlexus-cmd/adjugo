"""
Vérifie HORS LIGNE un ou plusieurs ancrages du journal d'audit (anchors/AAAA-MM-JJ.json,
téléchargés depuis le stockage) et prépare la vérification du jeton d'horodatage.

    venv/bin/python scripts/anchor_verify.py 2026-10-08.json
    venv/bin/python scripts/anchor_verify.py 2026-10-07.json 2026-10-08.json \\
        --engagement <engagement reçu par email>

Contrôles :
  1. l'engagement est recalculé à partir du contenu (têtes, anomalies, lien précédent) ;
  2. avec plusieurs fichiers : chacun doit citer l'engagement du précédent ;
  3. --engagement : comparaison avec la valeur reçue par email (copie hors infrastructure) ;
  4. le jeton de l'autorité est écrit à côté (AAAA-MM-JJ.tsr) et la commande openssl qui
     vérifie sa signature est affichée.
"""
import argparse
import base64
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.audit_anchor import commitment_of, parse_tsr, validate  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vérifie des ancrages du journal d'audit Adjugo.")
    ap.add_argument("fichiers", nargs="+", help="fichiers anchors/AAAA-MM-JJ.json")
    ap.add_argument("--engagement", help="engagement reçu par email, pour le DERNIER fichier")
    args = ap.parse_args(argv)

    docs = []
    for p in args.fichiers:
        with open(os.path.expanduser(p), encoding="utf-8") as f:
            docs.append((os.path.expanduser(p), json.load(f)))
    docs.sort(key=lambda d: d[1].get("date", ""))
    bad = 0
    prev = None
    for path, doc in docs:
        why = validate(doc)
        status = "cohérent" if not why else f"INCOHÉRENT : {why}"
        print(f"{doc.get('date')} : {status} ; engagement {doc.get('commitment')}")
        bad += bool(why)
        if prev is not None and doc.get("previous") != prev.get("commitment"):
            print(f"  ATTENTION : ne cite pas l'ancrage du {prev.get('date')} (ancrage manquant ou remplacé)")
            bad += 1
        if doc.get("anomalies"):
            print(f"  ATTENTION : {len(doc['anomalies'])} chaîne(s) signalées comme ayant perdu des entrées")
        tsa = doc.get("tsa") or {}
        if tsa.get("ok") and tsa.get("response_b64"):
            raw = base64.b64decode(tsa["response_b64"])
            tsr = os.path.splitext(path)[0] + ".tsr"
            with open(tsr, "wb") as f:
                f.write(raw)
            info = parse_tsr(raw)
            print(f"  jeton : {tsa.get('url')}, horodaté {info['gen_time']} → {tsr}")
            print("  vérification de la signature (certificats de l'autorité : https://freetsa.org/files/) :")
            print(f"    openssl ts -verify -digest {commitment_of(doc)} -in {tsr} "
                  "-CAfile cacert.pem -untrusted tsa.crt")
        else:
            print(f"  pas de jeton d'horodatage ({tsa.get('error') or 'inconnu'})")
        prev = doc
    if args.engagement:
        last = docs[-1][1]
        same = args.engagement.strip().lower() == (last.get("commitment") or "")
        print(f"Engagement reçu par email : {'identique' if same else 'DIFFÉRENT'} ({last.get('date')})")
        bad += not same
    print("Résultat : " + ("tout est cohérent." if not bad else f"{bad} problème(s) détecté(s)."))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
