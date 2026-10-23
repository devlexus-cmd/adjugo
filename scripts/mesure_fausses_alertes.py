#!/usr/bin/env python3
"""
Mesure des FAUSSES ALERTES de « Chaque fait a sa source » sur de vrais mémoires (rédaction, vague 3 —
étude § 6.5, calibration ; § 8, « V3 terminée quand… »).

Objectif : moins d'une fausse alerte par page sur les 20 mémoires de calibration des PME en test.
Tant que cet objectif n'est pas mesuré et atteint, les libellés positifs restent éteints dans l'atelier
(ATELIER_LIBELLES_SOURCES non posé) : seul l'affichage « à relire » est montré.

AUCUNE DONNÉE dans le dépôt : ce script lit un dossier LOCAL préparé par Mathys, avec l'accord écrit de
chaque PME (doctrine § 7, règle 10 : aucun mémoire réel sans accord écrit), et REFUSE un dossier source ou
une sortie situés dans le dépôt (public) : les mémoires et les phrases relevées n'y sont jamais écrits.
Rien n'est envoyé à l'IA ni sur le réseau : tout le contrôle est fait sans IA (app/services/faits_sources.py).

Dossier attendu, HORS du dépôt (un sous-dossier par mémoire, anonymisé) :

    ~/adjugo-calibration/
      pme01/
        accord.json      {"accord_ecrit_le": "2026-11-02", "valable_jusqu_au": "2027-03-01", "anonymise": true}
        memoire.docx     le mémoire tel qu'il a été déposé (.docx, .pdf, .md ou .txt)
        sources/         les documents de l'entreprise qu'Adjugo aurait eus (.docx, .pdf, .md, .txt)
        profil.json      (facultatif) {"nom": "PME 01", "effectif": 12, "qualifications": ["Qualibat 3194"],
                          "references": [{"intitule": "…", "client": "…", "annee": 2024, "montant": 85000}],
                          "equipe": [{"nom": "…", "fonction": "…", "qualifications": "…"}]}
        preuves.json     (facultatif) [{"nature": "materiel", "valeur": {"designation": "Nacelle", "quantite": 2},
                          "type_source": "declare"}]
        dce/             (facultatif) les pièces du dossier de l'acheteur
        pages.txt        (facultatif) nombre de pages du mémoire déposé (sinon estimé : 450 mots par page)

Un mémoire sans accord.json valable (accord écrit, date de fin non dépassée, anonymisé) est IGNORÉ.

Étapes :

  1. python scripts/mesure_fausses_alertes.py preparer ~/adjugo-calibration --sortie ~/adjugo-mesure
       → alertes.csv (une ligne par alerte : mémoire, partie, phrase, fait, type, message),
         sources.csv (une ligne par fait relié à une source : son libellé — « trouvé dans vos documents »,
         « calculé à partir de vos faits »… —, le renvoi, l'extrait ou le détail du calcul) et
         memoires.csv (pages, faits relevés, faits avec une source, alertes) ;
  2. Mathys remplit la colonne « verdict » :
       • de alertes.csv : « fausse » (le fait est bien dans les sources, ou ce n'est pas un fait) ou
         « vraie » (fait absent des sources : une invention ou un oubli de source) ;
       • de sources.csv : « juste » (le libellé dit vrai : le fait est bien écrit à cet endroit, ou le
         calcul est bien celui de la phrase) ou « faux » (libellé positif faux : le pire défaut, celui
         qui fait passer une invention pour sourcée) ;
  3. python scripts/mesure_fausses_alertes.py bilan ~/adjugo-mesure
       → fausses alertes par page (par mémoire et en tout), libellés positifs faux par type, inventions
         détectées, part des faits avec une source, et la décision (objectif atteint ou non : moins d'une
         fausse alerte par page ET aucun « trouvé dans vos documents » faux, sur 20 mémoires annotés) ;
  4. python scripts/mesure_fausses_alertes.py pieges
       → le jeu de 50 phrases piégées (aucune présentée comme « trouvé dans vos documents »).

Le protocole « omissions et inventions » (part des faits avec une source, inventions détectées) peut être
publié à partir de mesure/bilan.json, qui ne contient AUCUN texte des mémoires.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

MOTS_PAR_PAGE = 450
OBJECTIF = 1.0              # moins d'une fausse alerte par page
EXTENSIONS = (".docx", ".pdf", ".md", ".txt", ".odt")
COLONNES_ALERTES = ["memoire", "partie", "numero", "type", "fait", "phrase", "message", "detail", "verdict",
                    "commentaire"]
COLONNES_MEMOIRES = ["memoire", "pages", "pages_estimees", "faits", "avec_source", "alertes", "engagements"]
COLONNES_SOURCES = ["memoire", "partie", "numero", "type", "fait", "phrase", "source_type", "renvoi", "libelle",
                    "cite", "extrait", "detail", "verdict", "commentaire"]
# Libellés positifs faux tolérés, par type de source, pour allumer les libellés. « trouvé dans vos
# documents » (et « justificatif déposé ») : AUCUN — c'est le libellé qui ferait passer une invention pour
# un fait de l'entreprise. À revoir seulement avec Mathys, par écrit, jamais en silence.
FAUX_TOLERES = {"documents": 0, "justificatif": 0}


class HorsDuDepot(SystemExit):
    """Un dossier de calibration ou de mesure dans le dépôt (public) : refusé."""


def hors_du_depot(chemin: str, role: str) -> str:
    """Le chemin absolu, s'il est HORS du dépôt ; sinon refus (les mémoires des PME, confiés sous accord
    écrit pour une durée limitée, ne doivent jamais pouvoir être publiés par un « git add »)."""
    absolu = os.path.realpath(os.path.expanduser(chemin))
    depot = os.path.realpath(RACINE)
    if absolu == depot or absolu.startswith(depot + os.sep):
        raise HorsDuDepot(f"Le dossier {role} « {chemin} » est dans le dépôt Adjugo : choisissez un dossier hors du "
                          "dépôt (par exemple ~/adjugo-calibration et ~/adjugo-mesure).")
    return absolu


# ── Lecture du dossier ────────────────────────────────────────────────────────────────

def accord_valable(dossier: str, jour: date = None) -> tuple:
    """(True, "") si l'accord écrit est là, anonymisé et encore valable ; sinon (False, raison)."""
    jour = jour or date.today()
    p = os.path.join(dossier, "accord.json")
    if not os.path.exists(p):
        return False, "pas d'accord écrit (accord.json)"
    try:
        a = json.load(open(p, encoding="utf-8"))
        ecrit = date.fromisoformat(str(a.get("accord_ecrit_le"))[:10])
        fin = date.fromisoformat(str(a.get("valable_jusqu_au"))[:10])
    except (ValueError, TypeError, OSError, json.JSONDecodeError):
        return False, "accord.json illisible (dates AAAA-MM-JJ attendues)"
    if a.get("anonymise") is not True:
        return False, "mémoire non déclaré anonymisé"
    if ecrit > jour:
        return False, "date d'accord dans le futur"
    if fin < jour:
        return False, f"accord expiré le {fin.isoformat()}"
    return True, ""


def lire_fichier(chemin: str) -> str:
    """Texte d'un fichier (.docx, .pdf, .odt, .md, .txt), sans IA."""
    if chemin.lower().endswith((".md", ".txt")):
        return open(chemin, encoding="utf-8", errors="replace").read()
    from app.services.analysis import extract_dce_text
    with open(chemin, "rb") as f:
        contenu = f.read()
    return extract_dce_text(os.path.basename(chemin), contenu, max_chars=2_000_000) or ""


def _fichiers(dossier: str) -> list:
    if not os.path.isdir(dossier):
        return []
    return sorted(os.path.join(dossier, n) for n in os.listdir(dossier) if n.lower().endswith(EXTENSIONS))


def _memoire(dossier: str) -> str:
    for n in sorted(os.listdir(dossier)):
        if n.lower().startswith("memoire") and n.lower().endswith(EXTENSIONS):
            return os.path.join(dossier, n)
    return ""


def _profil_lignes(profil: dict) -> tuple:
    """(profil, équipe) au format de l'atelier (app/services/atelier._profil_texte, _equipe_texte)."""
    p = profil or {}
    lignes = []
    if p.get("nom"):
        lignes.append(f"Entreprise : {p['nom']}.")
    if p.get("effectif"):
        lignes.append(f"Effectif : {int(p['effectif'])} (salariés, personnes, collaborateurs, compagnons, employés).")
    for k, lab in (("ca_n1", "Chiffre d'affaires N-1"), ("ca_n2", "Chiffre d'affaires N-2")):
        if p.get(k):
            lignes.append(f"{lab} : {p[k]} €.")
    quals = [str(q.get("nom") if isinstance(q, dict) else q) for q in (p.get("qualifications") or []) if q]
    if quals:
        lignes.append("Qualifications et certifications : " + " ; ".join(quals) + ".")
    for r in p.get("references") or []:
        if isinstance(r, dict) and r.get("intitule"):
            parts = [str(r["intitule"])]
            if r.get("client"):
                parts.append("client " + str(r["client"]))
            if r.get("montant"):
                parts.append(f"montant {r['montant']} €")
            if r.get("annee"):
                parts.append(f"année {r['annee']}")
            lignes.append("Référence : " + ", ".join(parts) + ".")
    equipe = []
    for m in p.get("equipe") or []:
        if isinstance(m, dict) and m.get("nom"):
            s = f"- {m['nom']}, {m.get('fonction') or 'membre de l équipe'}"
            if m.get("qualifications"):
                s += f" ; qualifications : {m['qualifications']}"
            equipe.append(s)
    return "\n".join(lignes), "\n".join(equipe)


def fiches_du_dossier(dossier: str) -> tuple:
    """(fiches, noms de l'entreprise, dossier de l'acheteur) d'un mémoire de calibration."""
    from app.services import faits_sources as fs
    from app.services import preuves as pv
    from app.services.rag import chunk_text
    profil = {}
    if os.path.exists(os.path.join(dossier, "profil.json")):
        profil = json.load(open(os.path.join(dossier, "profil.json"), encoding="utf-8"))
    fiches = []
    if os.path.exists(os.path.join(dossier, "preuves.json")):
        for i, x in enumerate(json.load(open(os.path.join(dossier, "preuves.json"), encoding="utf-8")), start=1):
            nature = x.get("nature")
            valeur = pv.valider_valeur(nature, x.get("valeur") or {})
            ts = x.get("type_source") or pv.DECLARE
            t = {pv.DOCUMENTS: fs.T_DOCUMENTS, pv.DECLARE: fs.T_DECLARE, pv.PUBLIC: fs.T_PUBLIC,
                 pv.ESTIMATION: fs.T_ESTIMATION}.get(ts, fs.T_DECLARE)
            lib = {fs.T_DOCUMENTS: fs.LIB_TROUVE, fs.T_DECLARE: fs.LIB_DECLARE, fs.T_PUBLIC: fs.LIB_PUBLIC,
                   fs.T_ESTIMATION: fs.LIB_ESTIMATION}[t]
            fiches.append(fs.Fiche(f"F{i}", t, lib, pv.texte_de(nature, valeur), extra=fs._adjacents(nature, valeur),
                                   nature=nature, valeur=valeur))
    lignes, equipe = _profil_lignes(profil)
    fiches += fs.fiches_contexte(lignes, equipe, "", [])
    chunks = []
    for chemin in _fichiers(os.path.join(dossier, "sources")):
        for c in chunk_text(lire_fichier(chemin)):
            chunks.append({"text": c, "doc_name": os.path.basename(chemin)})
    fiches += fs.fiches_extraits(chunks)
    pieces = [(os.path.basename(c), lire_fichier(c)) for c in _fichiers(os.path.join(dossier, "dce"))]
    noms = [profil.get("nom")] if profil.get("nom") else []
    return fiches, noms, fs.Acheteur(pieces) if pieces else None


def parties(texte: str) -> list:
    """[(intitulé, texte)] : le mémoire découpé à ses titres (Markdown « # » ou ligne en capitales)."""
    out, titre, buf = [], "", []
    for ligne in str(texte or "").replace("\r", "\n").split("\n"):
        brut = ligne.strip()
        est_titre = bool(re.match(r"^#{1,6}\s+\S", brut)) or (
            8 <= len(brut) <= 90 and brut.upper() == brut and re.search(r"[A-Z]{4,}", brut) is not None
            and not re.search(r"[.;:]$", brut))
        if est_titre:
            if buf:
                out.append((titre, "\n".join(buf)))
            titre, buf = re.sub(r"^#{1,6}\s+", "", brut), []
        else:
            buf.append(ligne)
    if buf:
        out.append((titre, "\n".join(buf)))
    return [(t, x) for t, x in out if x.strip()]


# ── Étape 1 : préparer les alertes à annoter ──────────────────────────────────────────

def preparer(racine: str, sortie: str, jour: date = None) -> dict:
    from app.services import atelier_export as ax
    from app.services import faits_a_relire as far
    from app.services import faits_sources as fs
    racine = hors_du_depot(racine, "des mémoires")
    sortie = hors_du_depot(sortie, "de sortie")
    os.makedirs(sortie, exist_ok=True)
    alertes, sources, memoires, ignores = [], [], [], []
    for nom in sorted(os.listdir(racine)):
        dossier = os.path.join(racine, nom)
        if not os.path.isdir(dossier):
            continue
        ok, raison = accord_valable(dossier, jour)
        if not ok:
            ignores.append({"memoire": nom, "raison": raison})
            continue
        chemin = _memoire(dossier)
        if not chemin:
            ignores.append({"memoire": nom, "raison": "aucun fichier memoire.*"})
            continue
        texte = lire_fichier(chemin)
        fiches, noms, acheteur = fiches_du_dossier(dossier)
        tous = []
        n_alerte = n_source = 0
        for intitule, corps in parties(texte):
            items = fs.controler(corps, fiches, acheteur=acheteur, noms_entreprise=noms,
                                 section_entreprise=far.section_sur_l_entreprise(intitule), mode="ia")
            tous += items
            for x in fs.a_relire(items):
                if x.get("type") == far.RESTE:
                    continue
                n_alerte += 1
                alertes.append({"memoire": nom, "partie": intitule[:120], "numero": n_alerte, "type": x["type"],
                                "fait": x["fait"], "phrase": x["phrase"], "message": x["message"],
                                "detail": x.get("detail", ""), "verdict": "", "commentaire": ""})
            # Les libellés POSITIFS aussi : ce sont eux que l'annotation doit pouvoir dire faux.
            for x in fs.avec_source(items):
                src = x.get("source") or {}
                n_source += 1
                sources.append({"memoire": nom, "partie": intitule[:120], "numero": n_source, "type": x["type"],
                                "fait": x["fait"], "phrase": x["phrase"], "source_type": src.get("type", ""),
                                "renvoi": src.get("ref", ""), "libelle": src.get("libelle", ""),
                                "cite": "oui" if src.get("cite") else "non", "extrait": src.get("extrait", ""),
                                "detail": src.get("detail", ""), "verdict": "", "commentaire": ""})
        b = fs.bilan(tous) or {"total": 0, "avec_source": 0, "engagements": 0}
        mots = ax.compter_texte(texte)["mots"]
        pages = ""
        if os.path.exists(os.path.join(dossier, "pages.txt")):
            pages = open(os.path.join(dossier, "pages.txt"), encoding="utf-8").read().strip()
        memoires.append({"memoire": nom, "pages": pages, "pages_estimees": round(max(1.0, mots / MOTS_PAR_PAGE), 1),
                         "faits": b["total"], "avec_source": b["avec_source"], "alertes": n_alerte,
                         "engagements": b["engagements"]})
    with open(os.path.join(sortie, "alertes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_ALERTES)
        w.writeheader()
        w.writerows(alertes)
    with open(os.path.join(sortie, "sources.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_SOURCES)
        w.writeheader()
        w.writerows(sources)
    with open(os.path.join(sortie, "memoires.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_MEMOIRES)
        w.writeheader()
        w.writerows(memoires)
    return {"memoires": len(memoires), "alertes": len(alertes), "sources": len(sources), "ignores": ignores}


# ── Étape 3 : le bilan ────────────────────────────────────────────────────────────────

def bilan(sortie: str) -> dict:
    """Fausses alertes par page, libellés positifs faux par type, inventions détectées, part des faits avec
    une source. N'écrit dans bilan.json AUCUN texte de mémoire : seulement des nombres."""
    sortie = hors_du_depot(sortie, "de sortie")
    with open(os.path.join(sortie, "memoires.csv"), encoding="utf-8") as f:
        memoires = list(csv.DictReader(f))
    with open(os.path.join(sortie, "alertes.csv"), encoding="utf-8") as f:
        alertes = list(csv.DictReader(f))
    par = {m["memoire"]: {"pages": float(m["pages"] or m["pages_estimees"] or 1), "faits": int(m["faits"] or 0),
                          "avec_source": int(m["avec_source"] or 0), "fausses": 0, "vraies": 0, "non_annotees": 0}
           for m in memoires}
    for a in alertes:
        m = par.get(a["memoire"])
        if m is None:
            continue
        v = (a.get("verdict") or "").strip().lower()
        if v.startswith("faus"):
            m["fausses"] += 1
        elif v.startswith("vra"):
            m["vraies"] += 1
        else:
            m["non_annotees"] += 1
    # Les libellés positifs : juste / faux, par type de source (le fichier manque : rien n'est mesuré).
    libelles, sources_lues = {}, os.path.exists(os.path.join(sortie, "sources.csv"))
    if sources_lues:
        with open(os.path.join(sortie, "sources.csv"), encoding="utf-8") as f:
            for x in csv.DictReader(f):
                if x.get("memoire") not in par:
                    continue
                t = libelles.setdefault(x.get("source_type") or "", {"justes": 0, "faux": 0, "non_annotes": 0})
                v = (x.get("verdict") or "").strip().lower()
                if v.startswith("jus"):
                    t["justes"] += 1
                elif v.startswith("fau"):
                    t["faux"] += 1
                else:
                    t["non_annotes"] += 1
    pages = sum(m["pages"] for m in par.values()) or 1.0
    fausses = sum(m["fausses"] for m in par.values())
    faits = sum(m["faits"] for m in par.values())
    out = {
        "memoires": len(par),
        "pages": round(pages, 1),
        "fausses_alertes": fausses,
        "fausses_alertes_par_page": round(fausses / pages, 3),
        "inventions_ou_oublis_detectes": sum(m["vraies"] for m in par.values()),
        "alertes_non_annotees": sum(m["non_annotees"] for m in par.values()),
        "part_des_faits_avec_une_source": round(sum(m["avec_source"] for m in par.values()) / faits, 3) if faits else None,
        "par_memoire": {k: {"pages": v["pages"], "fausses_par_page": round(v["fausses"] / (v["pages"] or 1), 3),
                            "vraies": v["vraies"], "non_annotees": v["non_annotees"]} for k, v in par.items()},
        "objectif": OBJECTIF,
        "libelles_positifs": libelles,
        "libelles_positifs_faux": sum(t["faux"] for t in libelles.values()),
        "libelles_positifs_non_annotes": sum(t["non_annotes"] for t in libelles.values()),
        "faux_toleres": FAUX_TOLERES,
    }
    trop_de_faux = any(libelles.get(k, {}).get("faux", 0) > n for k, n in FAUX_TOLERES.items())
    out["libelles_documents_faux"] = sum(libelles.get(k, {}).get("faux", 0) for k in FAUX_TOLERES)
    out["objectif_atteint"] = (out["alertes_non_annotees"] == 0 and len(par) >= 20 and sources_lues
                               and out["libelles_positifs_non_annotes"] == 0 and not trop_de_faux
                               and out["fausses_alertes_par_page"] < OBJECTIF)
    with open(os.path.join(sortie, "bilan.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def _decision(b: dict) -> str:
    if b["alertes_non_annotees"]:
        return f"Bilan provisoire : {b['alertes_non_annotees']} alertes ne sont pas encore annotées (colonne « verdict »)."
    if b.get("libelles_positifs_non_annotes"):
        return (f"Bilan provisoire : {b['libelles_positifs_non_annotes']} faits avec une source ne sont pas encore "
                "annotés (sources.csv, colonne « verdict »).")
    if b.get("libelles_documents_faux"):
        return (f"Objectif NON atteint : {b['libelles_documents_faux']} « trouvé dans vos documents » faux. On garde "
                "l'affichage « à relire » sans libellé positif, et on corrige le contrôle avant toute nouvelle mesure.")
    if b["memoires"] < 20:
        return (f"Bilan provisoire : {b['memoires']} mémoires sur les 20 prévus. Les libellés positifs restent "
                "éteints.")
    if b["objectif_atteint"]:
        return (f"Objectif atteint : {b['fausses_alertes_par_page']} fausse alerte par page (moins de 1). Les "
                "libellés positifs peuvent être activés : ATELIER_LIBELLES_SOURCES=1.")
    return (f"Objectif NON atteint : {b['fausses_alertes_par_page']} fausse alerte par page. On garde l'affichage "
            "« à relire » sans libellé positif, sans assouplir le contrôle en silence.")


def pieges() -> dict:
    sys.path.insert(0, os.path.join(RACINE, "tests"))
    import pieges_sources as ps
    return ps.bilan_pieges()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mesure des fausses alertes de « Chaque fait a sa source » (sans IA).")
    sub = ap.add_subparsers(dest="etape", required=True)
    p1 = sub.add_parser("preparer", help="relève les alertes de chaque mémoire (accord écrit exigé)")
    p1.add_argument("dossier", help="dossier des mémoires, HORS du dépôt (par exemple ~/adjugo-calibration)")
    p1.add_argument("--sortie", default=os.path.join("~", "adjugo-mesure"),
                    help="dossier de sortie, HORS du dépôt (défaut ~/adjugo-mesure)")
    p2 = sub.add_parser("bilan", help="compte les fausses alertes annotées")
    p2.add_argument("sortie")
    sub.add_parser("pieges", help="le jeu de 50 phrases piégées")
    a = ap.parse_args(argv)
    if a.etape == "preparer":
        r = preparer(a.dossier, a.sortie)
        print(f"{r['memoires']} mémoires lus : {r['alertes']} alertes à annoter dans {a.sortie}/alertes.csv, "
              f"{r['sources']} faits avec une source à annoter dans {a.sortie}/sources.csv.")
        for x in r["ignores"]:
            print(f"  ignoré : {x['memoire']} ({x['raison']})")
        return 0
    if a.etape == "bilan":
        b = bilan(a.sortie)
        print(json.dumps({k: v for k, v in b.items() if k != "par_memoire"}, ensure_ascii=False, indent=2))
        print(_decision(b))
        return 0
    r = pieges()
    print(f"{r['pieges']} pièges : {len(r['presentes_comme_documents'])} présentés comme « trouvé dans vos "
          f"documents », {len(r['non_signales'])} non signalés.")
    return 0 if not r["presentes_comme_documents"] and not r["non_signales"] else 1


if __name__ == "__main__":
    sys.exit(main())
