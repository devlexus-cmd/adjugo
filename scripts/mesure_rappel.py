#!/usr/bin/env python3
"""
Mesure de départ du RAPPEL du moteur de recherche (lot 1 « Dire juste », point 9 ; étude moteur § 4.4, point 1).

Le rappel : la part des marchés GAGNÉS par une PME (selon la DECP), passés AVEC une annonce, qu'Adjugo lui aurait
montrés avec ses critères. C'est la seule mesure honnête de « ne rater aucun petit marché ». Elle est REJOUABLE :
la liste des marchés est relevée une fois (étape 1), puis mesurée avant et après chaque vague (étape 3) avec les
règles du code de ce moment-là.

Ne tourne jamais en production : c'est un outil de poste, lancé à la main. Aucune IA. Le réseau ne sert qu'à
l'étape « collecter » (lecture publique de la DECP, en-tête honnête d'Adjugo, une requête par seconde au plus) ;
les étapes suivantes ne lisent que des fichiers.

AUCUNE DONNÉE dans le dépôt : le numéro d'un entrepreneur individuel est une donnée personnelle. Le script REFUSE
un fichier d'entrée ou un dossier de sortie situés dans le dépôt (public).

Entrée (préparée par Mathys avec les PME en test), un CSV UTF-8 HORS du dépôt, séparé par « ; » ou « , » :

    pme;siren;mots_cles;departements;type_marche
    PME 01;123456789;couverture, zinguerie;29,56;travaux

  - pme : un nom court ou un pseudonyme ;
  - siren : 9 chiffres (un SIRET de 14 chiffres est ramené à son SIREN) ;
  - mots_cles : les mots que la PME cherche (« Ce que je cherche », ou ses alertes), séparés par des virgules ;
  - departements : sa zone, séparée par des virgules (vide : toute la France) ;
  - type_marche : travaux, services, fournitures, ou vide.

Étapes :

  1. python scripts/mesure_rappel.py collecter ~/adjugo-rappel/pme.csv --sortie ~/adjugo-rappel/depart [--jusqu-au AAAA-MM-JJ]
       → marches.csv : une ligne par marché gagné (titulaire, ou co-titulaire en 2e ou 3e position), notifié dans
         les 12 mois avant la date (par défaut aujourd'hui), dédoublonné (un marché écrit sur plusieurs lignes DECP
         n'est compté qu'une fois). La colonne « publicite » est lue dans la procédure publiée : « avec »
         (procédure formalisée, ou adaptée au-dessus du seuil de dispense de publicité : 100 000 € HT en travaux,
         60 000 € HT sinon), « sans » (écrit dans la procédure), « inconnue » (procédure adaptée sous ce seuil, ou
         procédure absente : la DECP ne dit pas s'il y a eu une annonce). Une copie de pme.csv est rangée à côté.
         Un marches.csv existant n'est jamais écrasé (il porte les vérifications de Mathys).
  2. Mathys remplit, pour chaque marché « avec » ou « inconnue », la colonne « avis_vu » :
       « oui »  l'annonce était visible dans une source qu'Adjugo lit (BOAMP, Mégalis, TED) : lien dans « lien_avis » ;
       « non »  l'annonce n'était dans aucune de ces sources (journal, site de l'acheteur, autre plateforme) ;
       « sans_publicite »  vérifié : il n'y a pas eu d'annonce (le marché sort du calcul) ;
       vide     pas encore vérifié.
  3. python scripts/mesure_rappel.py mesurer ~/adjugo-rappel/depart [--etiquette avant-lot1] [--pme autre.csv]
       → rappel_<etiquette>.csv (une ligne par marché : mots, zone, type, source, verdict et raison) et
         bilan_<etiquette>.json (rappel par PME et en tout ; en FOURCHETTE [bas, haut] tant que des lignes ne sont
         pas vérifiées). bilan_*.json ne contient que des comptes : ni objet, ni numéro d'entreprise.

Verdict d'un marché (hors « sans publicité ») :
  - « montré » : les mots, la zone et le type de la PME le retiennent, ET son annonce était dans une source lue ;
  - « manqué » : un critère l'écarte, OU son annonce n'était dans aucune source lue (avis_vu = non) ;
  - « indéterminé » : un critère ne peut pas être lu dans la DECP (zone inconnue…), ou avis_vu n'est pas rempli.
  rappel bas = montrés / total ; rappel haut = (montrés + indéterminés) / total. Tout vérifié : bas = haut.

Les règles rejouées sont celles du code (c'est ce qui rend la mesure rejouable) :
  - mots : la règle de la recherche BOAMP (app/sourcing/sources/boamp.py) — mots de 3 lettres au moins, 6 au plus,
    combinés en OU, ceux de plus de 4 lettres cherchés par leur début (« plombier » → « plomb… ») — appliquée à
    l'objet publié dans la DECP. Le test tests/test_moteur_lot1_services.py vérifie que les motifs sont ceux que
    la recherche envoie au BOAMP. NON VÉRIFIÉ : l'équivalence exacte avec l'opérateur « like » d'OpenDataSoft
    (découpage en mots, accents) ; et le BOAMP lit aussi son vocabulaire interne (descripteur), absent de la DECP :
    un « mots : non » peut donc sous-estimer ce que la recherche aurait trouvé (la raison le dit) ;
  - zone : le lieu d'exécution DECP ramené à son département sur le code complet (app/services/decp.py :
    outre-mer sur 3 chiffres, Corse « 2A » / « 2B ») ; un code postal corse « 20… » ou un lieu régional, national
    ou absent rend la zone « inconnue » (on ne devine pas) ;
  - type : déduit du code CPV du marché (45 : travaux ; 03 à 44 et 48 : fournitures ; 49 à 98 : services) ;
    sans code, le type est « inconnu » (la recherche garde les marchés de nature inconnue).
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

FENETRE_JOURS = 365
SEUIL_TRAVAUX = 100_000          # dispense de publicité, travaux (décret 2025-1386, étude moteur § 5.1)
SEUIL_AUTRES = 60_000            # dispense de publicité, fournitures et services (même source)
PAGE = 100                       # lignes par requête DECP
PAGES_MAX = 10                   # 1 000 lignes au plus par entreprise
INTERVALLE_S = 1.0               # une requête par seconde au plus
SELECT = ("id,objet,montant,datenotification,dureemois,nature,procedure,acheteur_id,lieuexecution_code,"
          "lieuexecution_typecode,codecpv,source,titulaire_id_1,titulaire_id_2,titulaire_id_3")
COLONNES_MARCHES = ["pme", "siren", "role", "id_decp", "date_notification", "objet", "acheteur_id", "montant",
                    "procedure", "publicite", "lieu_code", "lieu_type", "cpv", "source_decp", "avis_vu",
                    "lien_avis", "commentaire"]
COLONNES_RAPPEL = ["pme", "id_decp", "date_notification", "objet", "publicite", "mots", "zone", "type", "source",
                   "verdict", "raison"]
TYPES_LIEU_DEPARTEMENT = ("code departement", "code postal", "code commune", "code canton")


class HorsDuDepot(SystemExit):
    """Un fichier d'entrée ou un dossier de sortie dans le dépôt (public) : refusé."""


def hors_du_depot(chemin: str, role: str) -> str:
    """Le chemin absolu, s'il est HORS du dépôt ; sinon refus (numéros d'entreprise, dont ceux d'entrepreneurs
    individuels : jamais publiables par un « git add »)."""
    absolu = os.path.realpath(os.path.expanduser(chemin))
    depot = os.path.realpath(RACINE)
    if absolu == depot or absolu.startswith(depot + os.sep):
        raise HorsDuDepot(f"Le {role} « {chemin} » est dans le dépôt Adjugo : choisissez un emplacement hors du dépôt "
                          "(par exemple ~/adjugo-rappel).")
    return absolu


def _plie(s: str) -> str:
    """Minuscules, sans accents."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# ── Les règles rejouées ────────────────────────────────────────────────────────────────────────────

def motifs(requete: str) -> list:
    """Les motifs que la recherche BOAMP envoie pour une requête (même découpage que
    app/sourcing/sources/boamp.py) : [(motif, préfixe ?)]. « plombier » → ("plomb", True) ; « VRD » → ("VRD", False)."""
    from app.sourcing.http import safe_terms
    raw = safe_terms(requete)
    termes = [t for t in raw.split(" ") if len(t) >= 3][:6] or ["travaux"]
    out = []
    for t in termes:
        out.append((t, False) if len(t) <= 4 else (t[:max(4, len(t) - 3)], True))
    return out


def mots_retenus(objet: str, requete: str) -> bool:
    """L'objet publié contient-il un mot de la requête (règle de la recherche BOAMP, en OU) ?"""
    mots = [m for m in re.split(r"[^0-9a-z]+", _plie(objet)) if m]
    for motif, prefixe in motifs(requete):
        p = _plie(motif)
        if any((m.startswith(p) if prefixe else m == p) for m in mots):
            return True
    return False


def zone(lieu_code: str, lieu_type: str, departements: list) -> str:
    """« oui », « non » ou « inconnue » : le lieu d'exécution DECP est-il dans la zone de la PME ?"""
    from app.services.decp import code_departement, dans_les_departements
    if not departements:
        return "oui"
    code = str(lieu_code or "").strip().upper()
    if not code or _plie(lieu_type) not in TYPES_LIEU_DEPARTEMENT:
        return "inconnue"
    voulus = [code_departement(d) for d in departements if str(d).strip()]
    if dans_les_departements(code, voulus):
        return "oui"
    if code_departement(code) == "20" and any(v in ("2A", "2B") for v in voulus):
        return "inconnue"                          # code postal corse : 2A ou 2B, on ne le devine pas
    return "non"


def type_du_cpv(cpv: str) -> str:
    """travaux / fournitures / services d'après la division CPV, ou "" si le code est absent."""
    d = re.sub(r"\D", "", str(cpv or ""))[:2]
    if len(d) < 2:
        return ""
    n = int(d)
    if n == 45:
        return "travaux"
    if 3 <= n <= 44 or n == 48:
        return "fournitures"
    if 49 <= n <= 98:
        return "services"
    return ""


def type_retenu(cpv: str, type_marche: str) -> str:
    voulu = _plie(type_marche).strip()
    if voulu not in ("travaux", "services", "fournitures"):
        return "oui"                               # pas de filtre de type
    t = type_du_cpv(cpv)
    if not t:
        return "inconnu"
    return "oui" if t == voulu else "non"


def publicite(procedure: str, montant, cpv: str) -> str:
    """« avec », « sans » ou « inconnue », d'après la procédure et le montant publiés."""
    p = _plie(procedure)
    if not p.strip():
        return "inconnue"
    if "sans publicite" in p:
        return "sans"
    if "adaptee" in p:
        try:
            m = float(montant)
        except (TypeError, ValueError):
            return "inconnue"
        seuil = SEUIL_TRAVAUX if type_du_cpv(cpv) in ("travaux", "") else SEUIL_AUTRES
        return "avec" if m >= seuil else "inconnue"
    return "avec"                                  # appel d'offres, négociée avec publicité, dialogue, concours…


# ── Entrée ─────────────────────────────────────────────────────────────────────────────────────────

def _liste(v: str) -> list:
    return [x.strip() for x in re.split(r"[,;]", str(v or "")) if x.strip()]


def lire_pme(chemin: str) -> list:
    """Les PME du CSV : [{pme, siren, mots_cles, departements, type_marche}] ; une ligne sans SIREN valable est
    signalée et ignorée."""
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        texte = f.read()
    entete = texte.splitlines()[0] if texte else ""
    sep = ";" if entete.count(";") >= entete.count(",") else ","
    out, ignorees = [], []
    for i, ligne in enumerate(csv.DictReader(texte.splitlines(), delimiter=sep), start=2):
        ligne = {(k or "").strip().lower(): (v or "").strip() for k, v in ligne.items()}
        siren = re.sub(r"\D", "", ligne.get("siren", ""))
        siren = siren[:9] if len(siren) in (9, 14) else ""
        if not siren:
            ignorees.append(i)
            continue
        out.append({"pme": ligne.get("pme") or f"PME {len(out) + 1:02d}", "siren": siren,
                    "mots_cles": _liste(ligne.get("mots_cles", "")),
                    "departements": _liste(ligne.get("departements", "")),
                    "type_marche": ligne.get("type_marche", "")})
    if ignorees:
        print(f"  lignes ignorées (SIREN de 9 chiffres attendu) : {', '.join(map(str, ignorees))}")
    return out


# ── Étape 1 : collecter (réseau : DECP seulement) ─────────────────────────────────────────────────

def _cle(r: dict) -> tuple:
    """Un marché écrit sur plusieurs lignes DECP (plusieurs parties, plusieurs titulaires) n'est compté qu'une fois
    (même règle que app/services/partner_network.fetch_decp)."""
    return ((r.get("objet") or "").strip().lower()[:80], str(r.get("acheteur_id") or ""),
            str(r.get("datenotification") or "")[:10])


def _role(r: dict, siren: str) -> str:
    if str(r.get("titulaire_id_1") or "").startswith(siren):
        return "titulaire"
    return "co-titulaire"


def lire_decp(siren: str, debut: date, fin: date, get=None, pause=time.sleep) -> list:
    """Les lignes DECP où le SIREN est titulaire 1, 2 ou 3, notifiées entre debut et fin (bornes comprises)."""
    from app.services.decp import API, where_titulaire
    from app.sourcing.sources.atexo import USER_AGENT
    if get is None:
        from app.sourcing.http import get_with_retry as get
    where = (f"({where_titulaire(siren)}) AND datenotification >= date'{debut.isoformat()}' "
             f"AND datenotification <= date'{fin.isoformat()}'")
    lignes = []
    for page in range(PAGES_MAX):
        params = {"limit": PAGE, "offset": page * PAGE, "order_by": "-datenotification", "where": where,
                  "select": SELECT}
        data = get(API, params=params, timeout=20, headers={"User-Agent": USER_AGENT}).json()
        res = [r for r in (data.get("results") or []) if isinstance(r, dict)]
        lignes += res
        pause(INTERVALLE_S)
        if len(res) < PAGE or len(lignes) >= int(data.get("total_count") or 0):
            break
    return lignes


def collecter(entree: str, sortie: str, jusqu_au: date = None, get=None, pause=time.sleep) -> dict:
    entree = hors_du_depot(entree, "fichier d'entrée")
    sortie = hors_du_depot(sortie, "dossier de sortie")
    os.makedirs(sortie, exist_ok=True)
    chemin = os.path.join(sortie, "marches.csv")
    if os.path.exists(chemin):
        raise SystemExit(f"{chemin} existe déjà (il porte les vérifications de Mathys) : choisissez un autre dossier.")
    fin = jusqu_au or date.today()
    debut = fin - timedelta(days=FENETRE_JOURS)
    pmes = lire_pme(entree)
    lignes, par_pme = [], {}
    for p in pmes:
        vus = set()
        for r in lire_decp(p["siren"], debut, fin, get=get, pause=pause):
            notifie = str(r.get("datenotification") or "")[:10]
            if not (debut.isoformat() <= notifie <= fin.isoformat()):
                continue                           # même borne que la requête, vérifiée ici aussi
            k = _cle(r)
            if k in vus:
                continue
            vus.add(k)
            lignes.append({
                "pme": p["pme"], "siren": p["siren"], "role": _role(r, p["siren"]),
                "id_decp": str(r.get("id") or ""), "date_notification": str(r.get("datenotification") or "")[:10],
                "objet": (r.get("objet") or "").strip()[:400], "acheteur_id": str(r.get("acheteur_id") or ""),
                "montant": r.get("montant") if r.get("montant") is not None else "",
                "procedure": r.get("procedure") or "",
                "publicite": publicite(r.get("procedure"), r.get("montant"), r.get("codecpv")),
                "lieu_code": str(r.get("lieuexecution_code") or ""),
                "lieu_type": r.get("lieuexecution_typecode") or "", "cpv": r.get("codecpv") or "",
                "source_decp": r.get("source") or "", "avis_vu": "", "lien_avis": "", "commentaire": ""})
        par_pme[p["pme"]] = len(vus)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_MARCHES, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    with open(entree, encoding="utf-8-sig") as src, open(os.path.join(sortie, "pme.csv"), "w", encoding="utf-8") as dst:
        dst.write(src.read())
    with open(os.path.join(sortie, "collecte.json"), "w", encoding="utf-8") as f:
        json.dump({"du": debut.isoformat(), "au": fin.isoformat(), "pme": len(pmes), "marches": len(lignes),
                   "par_pme": par_pme, "source": "DECP (decp-2022-marches-valides), lecture publique"},
                  f, ensure_ascii=False, indent=2)
    return {"pme": len(pmes), "marches": len(lignes), "du": debut.isoformat(), "au": fin.isoformat()}


# ── Étape 3 : mesurer (sans réseau) ────────────────────────────────────────────────────────────────

def verdict(m: dict, p: dict) -> dict:
    """Le verdict d'un marché pour une PME : mots, zone, type, source, verdict, raison."""
    pub = m.get("publicite") or "inconnue"
    vu = _plie(m.get("avis_vu")).strip().replace(" ", "_")
    mots = "oui" if mots_retenus(m.get("objet", ""), " ".join(p.get("mots_cles") or [])) else "non"
    zn = zone(m.get("lieu_code"), m.get("lieu_type"), p.get("departements") or [])
    ty = type_retenu(m.get("cpv"), p.get("type_marche"))
    source = {"oui": "oui", "non": "non"}.get(vu, "à vérifier")
    out = {"mots": mots, "zone": zn, "type": ty, "source": source}
    if pub == "sans" or vu == "sans_publicite":
        return dict(out, verdict="hors calcul", raison="sans publicité")
    ecarte = [n for n, v in (("mots", mots), ("zone", zn), ("type", ty)) if v == "non"]
    if source == "non":
        ecarte.append("source")
    if ecarte:
        raison = "écarté par : " + ", ".join(ecarte)
        if "mots" in ecarte:
            raison += " (objet DECP seul ; le vocabulaire interne du BOAMP n'est pas dans la DECP)"
        return dict(out, verdict="manqué", raison=raison)
    inconnus = [n for n, v in (("zone", zn), ("type", ty)) if v in ("inconnue", "inconnu")]
    if source == "à vérifier":
        inconnus.append("avis à vérifier")
    if pub == "inconnue" and source != "oui":
        inconnus.append("publicité inconnue")
    if inconnus:
        return dict(out, verdict="indéterminé", raison="non lu : " + ", ".join(dict.fromkeys(inconnus)))
    return dict(out, verdict="montré", raison="")


def _taux(n: int, total: int):
    return round(n / total, 3) if total else None


def mesurer(dossier: str, etiquette: str = "", pme: str = None) -> dict:
    dossier = hors_du_depot(dossier, "dossier de mesure")
    chemin_pme = hors_du_depot(pme, "fichier d'entrée") if pme else os.path.join(dossier, "pme.csv")
    criteres = {p["pme"]: p for p in lire_pme(chemin_pme)}
    with open(os.path.join(dossier, "marches.csv"), encoding="utf-8-sig", newline="") as f:
        marches = list(csv.DictReader(f, delimiter=";"))
    etiquette = re.sub(r"[^0-9A-Za-z_-]+", "-", etiquette or date.today().isoformat()).strip("-") or "mesure"
    lignes, par = [], {}
    for m in marches:
        p = criteres.get(m.get("pme"))
        if p is None:
            continue
        v = verdict(m, p)
        lignes.append({"pme": m.get("pme"), "id_decp": m.get("id_decp"), "date_notification": m.get("date_notification"),
                       "objet": m.get("objet"), "publicite": m.get("publicite"), **v})
        t = par.setdefault(m.get("pme"), {"montres": 0, "manques": 0, "indetermines": 0, "hors_calcul": 0,
                                          "manques_par_raison": {}})
        if v["verdict"] == "montré":
            t["montres"] += 1
        elif v["verdict"] == "manqué":
            t["manques"] += 1
            for r in v["raison"].split(" (")[0].replace("écarté par : ", "").split(", "):
                t["manques_par_raison"][r] = t["manques_par_raison"].get(r, 0) + 1
        elif v["verdict"] == "indéterminé":
            t["indetermines"] += 1
        else:
            t["hors_calcul"] += 1
    for t in par.values():
        total = t["montres"] + t["manques"] + t["indetermines"]
        t.update(total=total, rappel_bas=_taux(t["montres"], total),
                 rappel_haut=_taux(t["montres"] + t["indetermines"], total))
    tot = {k: sum(t[k] for t in par.values()) for k in ("montres", "manques", "indetermines", "hors_calcul", "total")}
    raisons = {}
    for t in par.values():
        for r, n in t["manques_par_raison"].items():
            raisons[r] = raisons.get(r, 0) + n
    bilan = {"etiquette": etiquette, "mesure_le": date.today().isoformat(), "pme": len(par), **tot,
             "rappel_bas": _taux(tot["montres"], tot["total"]),
             "rappel_haut": _taux(tot["montres"] + tot["indetermines"], tot["total"]),
             "manques_par_raison": raisons, "par_pme": par,
             "regles": "app/sourcing/sources/boamp.py (mots), app/services/decp.py (zone), CPV (type)"}
    with open(os.path.join(dossier, f"rappel_{etiquette}.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_RAPPEL, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    with open(os.path.join(dossier, f"bilan_{etiquette}.json"), "w", encoding="utf-8") as f:
        json.dump(bilan, f, ensure_ascii=False, indent=2)
    return bilan


def _phrase(b: dict) -> str:
    if not b["total"]:
        return "Aucun marché à mesurer (aucun marché gagné avec publicité dans la fenêtre)."
    bas, haut = round(100 * (b["rappel_bas"] or 0)), round(100 * (b["rappel_haut"] or 0))
    if b["indetermines"]:
        return (f"Rappel entre {bas} % et {haut} % sur {b['total']} marchés : {b['indetermines']} restent à vérifier "
                "(colonne « avis_vu » de marches.csv, ou critère illisible dans la DECP).")
    return f"Rappel : {bas} % ({b['montres']} marchés montrés sur {b['total']})."


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mesure du rappel du moteur de recherche (sans IA, hors production).")
    sub = ap.add_subparsers(dest="etape", required=True)
    p1 = sub.add_parser("collecter", help="relève dans la DECP les marchés gagnés par chaque PME (réseau)")
    p1.add_argument("entree", help="CSV des PME, HORS du dépôt (pme;siren;mots_cles;departements;type_marche)")
    p1.add_argument("--sortie", required=True, help="dossier de sortie, HORS du dépôt")
    p1.add_argument("--jusqu-au", dest="jusqu_au", default="", help="fin de la fenêtre de 12 mois (AAAA-MM-JJ)")
    p2 = sub.add_parser("mesurer", help="rejoue les règles d'Adjugo sur la liste relevée (sans réseau)")
    p2.add_argument("dossier")
    p2.add_argument("--etiquette", default="", help="nom de la mesure (par exemple avant-lot1)")
    p2.add_argument("--pme", default=None, help="autre CSV de critères (sinon la copie rangée à la collecte)")
    a = ap.parse_args(argv)
    if a.etape == "collecter":
        jusqu = date.fromisoformat(a.jusqu_au) if a.jusqu_au else None
        r = collecter(a.entree, a.sortie, jusqu)
        print(f"{r['pme']} PME, {r['marches']} marchés gagnés du {r['du']} au {r['au']} : {a.sortie}/marches.csv "
              "(colonne « avis_vu » à remplir).")
        return 0
    b = mesurer(a.dossier, a.etiquette, a.pme)
    print(_phrase(b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
