#!/usr/bin/env python3
"""Régénère les empreintes SRI des scripts servis (co-traitance v2, vague 4).

À lancer depuis la racine du dépôt après TOUTE modification d'un fichier app/static/*.js ou
app/static/vendor/* :

    python scripts/sri_update.py          # réécrit les attributs integrity + le manifeste
    python scripts/sri_update.py --check  # ne modifie rien ; code 1 si une empreinte est périmée

Met à jour :
  • l'attribut integrity="sha384-…" de chaque <script src="/static/…"> des pages servies
    (app.html, invite.html, acheteur.html, acheteur-landing.html) ;
  • app/static/sri-manifest.json, publié pour la page sécurité (et servi tel quel).
Aucune dépendance : bibliothèque standard seulement (le module app.core.sri n'importe rien
d'autre que la bibliothèque standard).
"""
import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_sri():
    # Chargé par chemin : pas besoin d'importer le paquet app (ni sa configuration).
    spec = importlib.util.spec_from_file_location("adjugo_sri", os.path.join(_ROOT, "app", "core", "sri.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv) -> int:
    sri = _load_sri()
    if "--check" in argv:
        rep = sri.stale_report()
        if rep["pages"] or not rep["manifeste_a_jour"]:
            print("Empreintes SRI périmées :", ", ".join(rep["pages"]) or "-",
                  "| manifeste à jour :", rep["manifeste_a_jour"])
            print(f"Corrigez avec : {sri.REGEN_CMD}")
            return 1
        print("Empreintes SRI à jour.")
        return 0
    changed = sri.regenerate()
    print("Mis à jour : " + ", ".join(changed) if changed else "Rien à changer : empreintes déjà à jour.")
    for path, info in sri.compute_manifest()["fichiers"].items():
        print(f"  {path}  {info['integrity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
