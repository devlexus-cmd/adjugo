# -*- coding: utf-8 -*-
"""
Sélectionne les 100 PME les plus COMPATIBLES avec Adjugo parmi les 420 extraites.
Score = pertinence du métier vis-à-vis des marchés publics × adéquation de la taille
(capacité à répondre / candidat naturel au groupement). Équilibre régional.
Entrée : Adjugo_Prospection_PME.csv  ·  Sortie : Adjugo_Prospection_PME_Top100.csv
"""
import csv, json

SRC = "/Users/eliot/Downloads/Adjugo_Prospection_PME.csv"
OUT = "/Users/eliot/Downloads/Adjugo_Prospection_PME_Top100.csv"
JSON_OUT = "/tmp/adjugo_top100.json"

# Pertinence du métier pour les MARCHÉS PUBLICS (0-3).
METIER_W = {
    "Autres ouvrages de génie civil": 3, "Réseaux pour fluides": 3, "Réseaux électriques": 3,
    "Construction de routes": 3, "Travaux d'étanchéité": 3, "Travaux de couverture": 3,
    "Maçonnerie générale / gros œuvre": 3, "Terrassements": 3, "Travaux de terrassement": 3,
    "Démolition": 3, "Construction d'autres bâtiments": 3,
    "Travaux d'installation électrique": 2, "Plomberie / chauffage": 2, "Isolation": 2,
    "Menuiserie bois et PVC": 2, "Menuiserie métallique": 2, "Plâtrerie": 2,
    "Peinture et vitrerie": 2, "Revêtement des sols et des murs": 2, "Travaux de charpente": 2,
    "Autres travaux de finition": 2, "Travaux de montage de structures": 2,
    "Autres travaux spécialisés": 2, "Autres travaux d'installation": 2, "Aménagement paysager": 2,
    "Construction de maisons individuelles": 1, "Location avec opérateur": 1,
}
MET_REASON = {3: "métier très exposé aux marchés publics (infrastructures, bâtiments publics)",
              2: "métier courant dans les marchés publics de bâtiment",
              1: "marché plutôt privé, mais éligible aux marchés publics"}
SIZE_W = {"20-49": 3.0, "10-19": 2.7, "50-99": 2.5, "6-9": 1.7, "100-199": 1.6,
          "200-249": 1.2, "3-5": 1.2}
def size_reason(e):
    if e in ("20-49", "10-19"): return "taille idéale pour répondre aux AO et se grouper"
    if e == "50-99": return "structure capable de porter des marchés et des groupements"
    if e in ("6-9", "3-5"): return "petite structure : la co-traitance lui ouvre des marchés plus gros"
    if e in ("100-199", "200-249"): return "déjà structurée : Adjugo industrialise ses réponses"
    return "taille à confirmer"

QUOTAS = {"Bretagne": 35, "Ile-de-France": 45, "Hauts-de-France (Lille)": 20}

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
for r in rows:
    mw = METIER_W.get(r["Activite (NAF)"], 1)
    eff = r["Effectif (salaries)"]
    sw = SIZE_W.get(eff, 1.0)
    r["_score"] = round((mw + sw) / 6 * 10, 1)
    r["Score compatibilite (/10)"] = r["_score"]
    r["Pourquoi (besoin)"] = "%s, %s sal. — %s ; %s." % (
        r["Activite (NAF)"], eff, MET_REASON[mw], size_reason(eff))

selected = []
for region, quota in QUOTAS.items():
    pool = sorted([r for r in rows if r["Region"] == region], key=lambda x: -x["_score"])
    selected += pool[:quota]
selected.sort(key=lambda x: (x["Region"], -x["_score"]))

cols = ["Region", "Departement", "Raison sociale", "Ville", "Code postal", "Activite (NAF)",
        "Effectif (salaries)", "Score compatibilite (/10)", "Pourquoi (besoin)",
        "Dirigeant (registre public)", "SIREN", "Fiche annuaire",
        "Site web", "Telephone", "Email", "LinkedIn dirigeant"]
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in selected:
        r.setdefault("Site web", ""); r.setdefault("Telephone", "")
        r.setdefault("Email", ""); r.setdefault("LinkedIn dirigeant", "")
        w.writerow(r)

# Liste pour l'enrichissement contact (recherche web)
mini = [{"i": i, "nom": r["Raison sociale"], "ville": r["Ville"],
         "cp": r["Code postal"], "siren": r["SIREN"]} for i, r in enumerate(selected)]
json.dump(mini, open(JSON_OUT, "w", encoding="utf-8"), ensure_ascii=False)

from collections import Counter
print("Top 100 :", len(selected), "| par région :", dict(Counter(r["Region"] for r in selected)))
print("Score moyen : %.1f/10 | min %.1f | max %.1f" % (
    sum(r["_score"] for r in selected)/len(selected),
    min(r["_score"] for r in selected), max(r["_score"] for r in selected)))
print("CSV :", OUT)
print("JSON enrichissement :", JSON_OUT)
print("\n--- top 8 (aperçu) ---")
for r in sorted(selected, key=lambda x:-x["_score"])[:8]:
    print("%.1f" % r["_score"], "|", r["Raison sociale"][:30].ljust(30), "|", r["Ville"][:14].ljust(14),
          "|", r["Activite (NAF)"][:24].ljust(24), "| eff", r["Effectif (salaries)"])
