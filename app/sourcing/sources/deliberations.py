"""
Source VEILLE AMONT : délibérations de collectivités via l'open data (OpenDataSoft).
Hub fédéré data.opendatasoft.com — gratuit, sans clé. MULTI-PAYS.

Adjugo VA CHERCHER lui-même les délibérations récentes :
 - France : jeux curés + découverte automatique sur le hub.
 - Italie / Espagne : jeux curés (Bologna, Junta Castilla y León) — démarrage de
   l'auto-collecte à l'étranger, là où c'est le plus simple.
L'agent IA est multilingue ; le pré-filtre « investissement » l'est aussi.
"""
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

logger = logging.getLogger("adjugo")
HUB = "https://data.opendatasoft.com/api/explore/v2.1/catalog/datasets"
_H = {"User-Agent": "AdjugoBot/1.0"}

# Mots-clés investissement / travaux — FR + IT + ES + racines communes.
INVEST = re.compile(
    r"travaux|construction|construire|réhabilit|rehabilit|rénovation|renovation|voirie|"
    r"aménag|amenag|extension|réfection|refection|acquisition|réseau|reseau|école|ecole|"
    r"gymnase|crèche|creche|stade|piscine|médiathèque|mediatheque|bâtiment|batiment|"
    r"équipement|equipement|ZAC|requalification|restructuration|assainissement|éclairage|"
    r"eclairage|parking|pont|"
    # Italien
    r"lavori|costruzione|ristruttur|riqualific|edificio|edifici|scuola|asilo|palestra|"
    r"strada|strade|impianto|manutenzione|opere|appalto|piscina|parcheggio|ponte|"
    # Espagnol
    r"obras|construcci|rehabilitaci|reforma|edificio|colegio|escuela|polideportivo|"
    r"carretera|alumbrado|saneamiento|adquisici|equipamiento|pabellón|pabellon|urbanizaci",
    re.I)

# Jeux par pays. dep = département (FR) pour le filtrage régional.
COUNTRIES = {
    "FR": [
        {"id": "deliberations-2023@cachan", "coll": "Ville de Cachan (94)", "dep": "94"},
        {"id": "deliberations-conseil-2021-et-2022@tco-lareunion", "coll": "Territoire de l'Ouest (974)", "dep": "974"},
        {"id": "deliberation-de-la-ville-de-la-possession-novembre-2024@lareunion", "coll": "Ville de La Possession (974)", "dep": "974"},
        {"id": "deliberation-de-la-ville-de-la-possession-aout-2024@lareunion", "coll": "Ville de La Possession (974)", "dep": "974"},
    ],
    "IT": [
        {"id": "delibere-di-giunta@bologna", "coll": "Comune di Bologna"},
        {"id": "delibere-e-odg-del-consiglio-comunale@bologna", "coll": "Comune di Bologna"},
    ],
    "ES": [
        {"id": "acuerdos-de-consejos-de-gobierno@jcyl", "coll": "Junta de Castilla y León"},
    ],
}

_DISCOVERED = None
_MAX_DATASETS = 16
_OBJ_HINTS = ("objet", "intitul", "affaire", "libell", "sujet", "titre",
              "oggetto", "titolo", "descrizione",           # IT
              "titulo", "asunto", "descripcion", "acuerdo",  # ES
              "onderwerp", "betreff", "title")               # NL/DE/EN
_DATE_HINTS = ("date", "data", "fecha", "datum", "seduta")


def _field(rec, hints):
    for k, v in rec.items():
        if isinstance(v, str) and v.strip() and any(x in k.lower() for x in hints):
            return v.strip()
    return ""


def _objet(rec):
    return _field(rec, _OBJ_HINTS)


def _date(rec):
    return _field(rec, _DATE_HINTS)[:10]


def _coll_from_id(did):
    portal = did.split("@")[-1] if "@" in did else did.split("@")[0]
    return portal.replace("-", " ").strip().title()


def _dep_from(text):
    m = re.search(r"\((\d{3}|\d{2}|2[AB])\)", str(text)) or re.search(r"\b(\d{2,3})\d{3}\b", str(text))
    return m.group(1) if m else ""


def _doc_link(rec):
    """Lien vers la délibération / document associé, s'il figure dans l'enregistrement."""
    named = ("url", "lien", "enlace", "document", "pdf", "link", "permalink",
             "atto", "fichier", "file", "acte")
    for k, v in rec.items():
        if isinstance(v, str) and v.startswith("http") and any(x in k.lower() for x in named):
            return v
    for v in rec.values():   # à défaut, toute URL présente
        if isinstance(v, str) and v.startswith("http"):
            return v
    return ""


def _discover(limit=18):
    global _DISCOVERED
    if _DISCOVERED is not None:
        return _DISCOVERED
    try:
        r = httpx.get(HUB, params={"where": 'title like "délibération" OR title like "deliberation"',
                                   "limit": 60, "order_by": "records_count DESC"}, timeout=12, headers=_H)
        ids = [d.get("dataset_id") for d in r.json().get("results", [])
               if d.get("dataset_id") and (((d.get("metas", {}) or {}).get("default", {}) or {}).get("records_count") or 0) >= 25]
        _DISCOVERED = ids[:limit]
    except Exception as e:
        logger.info("Découverte délibérations indisponible : %s", e)
        _DISCOVERED = []
    return _DISCOVERED


def _fetch_one(did, coll, dep, pays, per):
    try:
        r = httpx.get(f"{HUB}/{did}/records", params={"limit": min(per, 100)}, timeout=10, headers=_H)
        if r.status_code != 200:
            return []
        rows = r.json().get("results", [])
    except Exception:
        return []
    out = []
    for rec in rows:
        objet = _objet(rec)
        if not objet or len(objet) < 8:
            continue
        collectivite = (rec.get("coll_nom") or rec.get("collectivite") or coll or _coll_from_id(did)).strip()
        dataset_url = f"https://data.opendatasoft.com/explore/dataset/{did}/table/"
        out.append({
            "objet": objet, "collectivite": collectivite, "pays": pays,
            "dept": dep or _dep_from(collectivite) or _dep_from(rec.get("code_postal", "")) or "",
            "date": _date(rec), "source": did.split("@")[0].replace("-", " "),
            "url": _doc_link(rec) or dataset_url,
        })
    return out


class DeliberationSource:
    name = "Délibérations (open data)"

    def fetch_recent(self, country: str = "FR", per: int = 40, only_invest: bool = True) -> list[dict]:
        country = (country or "FR").upper()
        tasks, seen = [], set()
        for d in COUNTRIES.get(country, []):
            seen.add(d["id"]); tasks.append((d["id"], d["coll"], d.get("dep", ""), country))
        if country == "FR":
            for did in _discover():
                if did not in seen:
                    seen.add(did); tasks.append((did, "", "", "FR"))
        tasks = tasks[:_MAX_DATASETS]
        if not tasks:
            return []

        records = []
        try:
            with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
                futs = [ex.submit(_fetch_one, did, coll, dep, pays, per) for did, coll, dep, pays in tasks]
                for f in as_completed(futs, timeout=28):
                    try:
                        records.extend(f.result() or [])
                    except Exception:
                        continue
        except Exception as e:
            logger.info("Fetch délibérations partiel : %s", e)

        out, seen_o = [], set()
        for r in records:
            if only_invest and not INVEST.search(r["objet"]):
                continue
            k = r["objet"].lower()[:90]
            if k in seen_o:
                continue
            seen_o.add(k)
            out.append(r)
        return out

    @staticmethod
    def countries() -> list:
        return list(COUNTRIES.keys())
