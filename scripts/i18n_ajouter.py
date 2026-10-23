#!/usr/bin/env python3
"""Ajoute (ou remplace) des traductions néerlandaises et espagnoles dans app/static/i18n.js.

Décision 16 de l'étude « organisation du logiciel » : à CHAQUE renommage d'un libellé visible, le nouveau libellé
français reçoit sa traduction (le dictionnaire est indexé sur le texte français exact, voir translateDOM dans
app.js). Usage, depuis la racine du dépôt :

    python scripts/i18n_ajouter.py ajouts.json      # {"Libellé français": {"nl": "…", "es": "…"}, …}
    python scripts/i18n_ajouter.py --check          # code 1 si une clé n'a pas ses deux langues

Le fichier garde exactement sa forme (une ligne de commentaire, puis l'objet JSON compact) : les anciennes clés ne
sont jamais retirées (un ancien libellé peut encore s'afficher ailleurs). Ensuite : python scripts/sri_update.py.
Bibliothèque standard seulement.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN = os.path.join(_ROOT, "app", "static", "i18n.js")
_PRE = "window.ADJUGO_I18N = "
LANGUES = ("nl", "es")


def lire():
    with open(CHEMIN, encoding="utf-8") as f:
        tete, corps = f.read().split("\n", 1)
    assert corps.startswith(_PRE), "forme inattendue de i18n.js"
    return tete, json.loads(corps[len(_PRE):].rstrip().rstrip(";"))


def ecrire(tete, d):
    with open(CHEMIN, "w", encoding="utf-8") as f:
        f.write(tete + "\n" + _PRE + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + ";\n")


def main(argv) -> int:
    tete, d = lire()
    if "--check" in argv:
        manque = sorted(set(d["nl"]) ^ set(d["es"]))
        if manque:
            print("Clés sans leurs deux langues :", ", ".join(manque))
            return 1
        print(f"{len(d['nl'])} clés, néerlandais et espagnol.")
        return 0
    with open(argv[0], encoding="utf-8") as f:
        ajouts = json.load(f)
    for fr, tr in ajouts.items():
        for lg in LANGUES:
            assert tr.get(lg), f"« {fr} » : traduction {lg} manquante"
            d[lg][fr] = tr[lg]
    ecrire(tete, d)
    print(f"{len(ajouts)} libellé(s) traduit(s) ; {len(d['nl'])} clés.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
