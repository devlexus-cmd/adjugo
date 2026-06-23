# -*- coding: utf-8 -*-
"""
Liste de prospection PME (BTP) pour Adjugo — données réelles via l'API publique
Recherche d'entreprises (annuaire-entreprises / data.gouv, gratuite, sans clé).
Cibles : PME du bâtiment dont le SIÈGE est en Bretagne, Île-de-France, Nord.
Sortie : /Users/eliot/Downloads/Adjugo_Prospection_PME.csv
"""
import csv, json, time, ssl, urllib.request, urllib.parse

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()
    CTX.check_hostname = False
    CTX.verify_mode = ssl.CERT_NONE

API = "https://recherche-entreprises.api.gouv.fr/search"
OUT = "/Users/eliot/Downloads/Adjugo_Prospection_PME.csv"

REGIONS = {
    "Bretagne": ["22", "29", "35", "56"],
    "Ile-de-France": ["75", "92", "93", "94", "78", "91", "95", "77"],
    "Hauts-de-France (Lille)": ["59", "62"],
}
# Tranches d'effectif retenues = PME employeuses (3 à 249 salariés). On écarte les
# 0-2 salariés (NN, 00, 01) et les ETI/GE.
KEEP_EFF = {"02", "03", "11", "12", "21", "22", "31"}
EFF_LABEL = {"02": "3-5", "03": "6-9", "11": "10-19", "12": "20-49",
             "21": "50-99", "22": "100-199", "31": "200-249"}
NAF_LABEL = {
    "41.20A": "Construction de maisons individuelles", "41.20B": "Construction d'autres bâtiments",
    "43.11Z": "Démolition", "43.12A": "Terrassements", "43.12B": "Travaux de terrassement",
    "43.21A": "Travaux d'installation électrique", "43.22A": "Plomberie / chauffage",
    "43.22B": "Plomberie / chauffage", "43.29A": "Isolation", "43.29B": "Autres travaux d'installation",
    "43.31Z": "Plâtrerie", "43.32A": "Menuiserie bois et PVC", "43.32B": "Menuiserie métallique",
    "43.33Z": "Revêtement des sols et des murs", "43.34Z": "Peinture et vitrerie",
    "43.39Z": "Autres travaux de finition", "43.91A": "Travaux de charpente",
    "43.91B": "Travaux de couverture", "43.99A": "Travaux d'étanchéité",
    "43.99B": "Travaux de montage de structures", "43.99C": "Maçonnerie générale / gros œuvre",
    "43.99D": "Autres travaux spécialisés", "43.99E": "Location avec opérateur",
    "42.11Z": "Construction de routes", "42.21Z": "Réseaux pour fluides",
    "42.22Z": "Réseaux électriques", "42.99Z": "Autres ouvrages de génie civil",
    "81.30Z": "Aménagement paysager",
}

def fetch(dep, page):
    q = {"section_activite_principale": "F", "departement": dep, "etat_administratif": "A",
         "categorie_entreprise": "PME", "per_page": "25", "page": str(page)}
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "AdjugoProspection/1.0"})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return json.load(r)

def dirigeant(r):
    for d in (r.get("dirigeants") or []):
        nom = (d.get("nom") or "").strip()
        prenoms = (d.get("prenoms") or "").strip()
        if nom:
            return (prenoms.split(" ")[0] + " " + nom).strip() if prenoms else nom
        if d.get("denomination"):
            return d["denomination"]
    return ""

rows = []
seen = set()
for region, deps in REGIONS.items():
    kept_region = 0
    for dep in deps:
        kept_dep = 0
        for page in range(1, 13):
            if kept_dep >= 30:
                break
            try:
                data = fetch(dep, page)
            except Exception as e:
                print("  ! %s p%d : %s" % (dep, page, e)); break
            results = data.get("results") or []
            if not results:
                break
            for r in results:
                siren = r.get("siren")
                if not siren or siren in seen:
                    continue
                s = r.get("siege") or {}
                cp = str(s.get("code_postal") or "")
                if cp[:2] != dep:                       # siège réellement dans le département
                    continue
                eff = str(r.get("tranche_effectif_salarie") or "")
                seen.add(siren)
                naf = r.get("activite_principale") or ""
                rows.append({
                    "Region": region,
                    "Departement": dep,
                    "Raison sociale": r.get("nom_complet") or r.get("nom_raison_sociale") or "",
                    "Ville": s.get("libelle_commune") or "",
                    "Code postal": cp,
                    "Activite (NAF)": NAF_LABEL.get(naf, naf),
                    "Code NAF": naf,
                    "Effectif (salaries)": EFF_LABEL.get(eff, eff),
                    "Dirigeant (registre public)": dirigeant(r),
                    "SIREN": siren,
                    "Fiche annuaire": "https://annuaire-entreprises.data.gouv.fr/entreprise/%s" % siren,
                })
                kept_dep += 1; kept_region += 1
                if kept_dep >= 30:                       # plafond par département
                    break
            if kept_dep >= 30:
                break
            time.sleep(0.25)
        print("  %s (%s) : %d PME" % (region, dep, kept_dep))
    print("== %s : %d PME ==" % (region, kept_region))

# tri : région, département, effectif décroissant (les plus gros d'abord)
order = {v: i for i, v in enumerate(["200-249","100-199","50-99","20-49","10-19","6-9","3-5"])}
rows.sort(key=lambda x: (x["Region"], x["Departement"], order.get(x["Effectif (salaries)"], 99)))

cols = ["Region","Departement","Raison sociale","Ville","Code postal","Activite (NAF)",
        "Code NAF","Effectif (salaries)","Dirigeant (registre public)","SIREN","Fiche annuaire"]
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)
print("\nCSV généré : %s | %d PME au total" % (OUT, len(rows)))
