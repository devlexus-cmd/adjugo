"""Moteur de recherche, lot 1 « Dire juste » : réunion des chantiers Sources et Services (docs/MOTEUR_LOT1.md,
section « Réunion des chantiers »).

Vérifications de bout en bout, sur des réponses RÉELLES lues le 21/10/2026 (aucun réseau pendant les tests) :
  - tests/fixtures/moteur_lot1_reunion/boamp_recherches_2026-10-21.json : trois recherches faites PAR LE CODE de la
    réunion (BoampSource.search) sur l'API publique du BOAMP, chaque requête gardée telle qu'envoyée, avec les lignes
    reçues (« voirie » dans le 29 ; outre-mer 971 et 974 ; Corse 2A et 2B) ;
  - tests/fixtures/moteur_lot1_reunion/boamp_rectifie_puis_annule.json : l'avis 26-83249 (Guadeloupe), son
    rectificatif 26-84145 (28/08/2026) et son annulation 26-89465 (15/09/2026) ;
  - les jeux d'essai réels des deux chantiers (Mégalis « voirie », avis et suites du BOAMP du 21/10/2026).
Corps des suites réduit au bloc rectificatif/annulation, contacts retirés ; corps européen (eForms) retiré.

Quand une requête du code n'est pas celle qui a été enregistrée (autres départements, code d'avant le lot), l'API est
SIMULÉE sur les mêmes lignes réelles : filtre exact des départements (le « like » du BOAMP compare des valeurs
entières : « 2A » ne trouve pas « 20A »), des avis visés (annonce_lie, idweb) et des dates. Chaque test échoue sur
0afc1ed, sur le défaut qu'il couvre (docs/MOTEUR_LOT1.md, § Réunion, « Preuve »).
"""
import json
import pathlib
import re
from datetime import date

import httpx
import pytest

from app.core.database import SessionLocal

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
REUNION = FIX / "moteur_lot1_reunion"
RECHERCHES = json.loads((REUNION / "boamp_recherches_2026-10-21.json").read_text(encoding="utf-8"))["recherches"]
CAS = json.loads((REUNION / "boamp_rectifie_puis_annule.json").read_text(encoding="utf-8"))
SOURCES = json.loads((FIX / "boamp_suites_2026-10-21.json").read_text(encoding="utf-8"))
LE_21_10 = date(2026, 10, 21)


def _figer(monkeypatch, jour=LE_21_10):
    """« Aujourd'hui » figé pour la recherche du BOAMP et le tri des marchés clôturés (même effet sur 0afc1ed, qui
    lisait date.today() directement, et sur la réunion, qui passe par _aujourdhui())."""
    class _Jour(date):
        @classmethod
        def today(cls):
            return cls(jour.year, jour.month, jour.day)

    from app.sourcing import search as search_mod
    from app.sourcing.sources import boamp
    monkeypatch.setattr(boamp, "date", _Jour)
    monkeypatch.setattr(search_mod, "date", _Jour)
    search_mod._CB.clear()


class _Rep:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"results": self._rows}


def _deps_demandes(where: str) -> set:
    return set(re.findall(r'code_departement like "([^"]+)"', where))


def _api(monkeypatch, avis, suites, jour=LE_21_10, enregistrees=None):
    """API BOAMP simulée sur des lignes réelles. `enregistrees` : {where: lignes} des requêtes réellement faites par le
    code (réponse rendue telle quelle). Sinon : avis encore ouverts au jour dit et du département demandé ; suites
    parues au plus tard ce jour-là, qui visent un avis demandé (annonce_lie), plus les rectificatifs récents du
    même département si le code les demande ; relecture d'avis par idweb, avec les annulations qui les visent."""
    from app.sourcing import http
    appels = []
    lignes = {r["idweb"]: r for r in list(avis) + list(suites)}
    jour_iso = jour.isoformat()

    def parues(rows):
        return [dict(r) for r in rows if (r.get("dateparution") or "")[:10] <= jour_iso]

    def fake(url, params=None, timeout=12, tries=3, headers=None):
        p = dict(params or {})
        appels.append(p)
        w = p.get("where", "")
        if enregistrees and w in enregistrees:
            return _Rep([dict(r) for r in enregistrees[w]])
        deps = _deps_demandes(w)

        def dans(r):
            return not deps or bool(deps & {str(d) for d in (r.get("code_departement") or [])})
        if "datelimitereponse >=" in w:
            borne = re.search(r"datelimitereponse >= date'(\d{4}-\d{2}-\d{2})'", w).group(1)
            return _Rep([r for r in parues(avis) if dans(r) and (r.get("datelimitereponse") or "")[:10] >= borne])
        if w.startswith("idweb in"):
            ids = set(re.findall(r'"(\d{2}-\d+)"', w.split(" OR ")[0]))
            rows = [r for r in parues(lignes.values()) if r["idweb"] in ids and r.get("nature") != "ANNULATION"]
            rows += [r for r in parues(suites) if (r.get("nature") == "ANNULATION" or r.get("etat") == "ANNULATION")
                     and set(r.get("annonce_lie") or []) & ids]
            return _Rep(rows)
        m = re.search(r"annonce_lie in \(([^)]*)\)", w)
        ids = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
        rows = [r for r in parues(suites) if set(r.get("annonce_lie") or []) & ids]
        if 'nature="RECTIFICATIF" AND dateparution' in w:
            vus = {r["idweb"] for r in rows}
            rows += [r for r in parues(suites) if r.get("nature") == "RECTIFICATIF" and dans(r) and r["idweb"] not in vus]
        return _Rep(rows)

    monkeypatch.setattr(http, "get_with_retry", fake)
    return appels


def _api_enregistree(monkeypatch, nom):
    """Les réponses réelles de la recherche `nom` (requêtes du code du 21/10/2026), et l'API simulée sur les mêmes
    lignes pour toute autre requête."""
    rech = RECHERCHES[nom]
    enregistrees = {q["params"]["where"]: q["results"] for q in rech["requetes"]}
    principales = [r for q in rech["requetes"] if "datelimitereponse >=" in q["params"]["where"] for r in q["results"]]
    relues = [r for q in rech["requetes"] if q["params"]["where"].startswith("idweb in") for r in q["results"]]
    suites = [r for q in rech["requetes"] if "annonce_lie in" in q["params"]["where"]
              and not q["params"]["where"].startswith("idweb in") for r in q["results"]]
    # Une ligne relue est un avis dont la date limite initiale est passée : la simulation la rend par sa référence.
    return _api(monkeypatch, principales, suites + relues, enregistrees=enregistrees)


def _cartes(client, auth, **requete):
    r = client.post("/api/sourcing/search", json=requete, headers=auth["headers"])
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["errors"] == [], corps["errors"]
    return {t["provenance"]["official_ref"]: t for t in corps["tenders"]}


def _zone(carte):
    return next(c for c in carte["score"]["breakdown"] if c["key"] == "zone")["status"]


# ═══ Corse : le BOAMP écrit « 20A » / « 20B » ════════════════════════════════════════════════════════════════

def test_corse_les_avis_du_boamp_enfin_trouves_sous_2A_et_2B(client, auth, monkeypatch):
    """Recherche réelle du 21/10/2026 : 19 avis ouverts en Corse au BOAMP, tous écrits « 20A » ou « 20B ».
    Avant (0afc1ed comme les deux chantiers) : une recherche « 2A » demandait « 2A » au BOAMP et ne trouvait rien,
    et un avis « 20A » sortait de toute zone. Après : la Corse est lue sous ses deux formes, et ramenée à « 2A »."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.scoring import score_tender
    from app.sourcing.sources.boamp import BoampSource
    _figer(monkeypatch)
    appels = _api_enregistree(monkeypatch, "corse_2A_2B")
    lu = {r["idweb"]: r["code_departement"] for r in RECHERCHES["corse_2A_2B"]["requetes"][0]["results"]}
    assert len(lu) == 19 and {d for v in lu.values() for d in v} <= {"20A", "20B", "69", "75"}

    corse_du_sud = _cartes(client, auth, query="", departements=["2A"], limit=50)
    # 26-91505 est la version européenne rectifiée de 26-88364 : une seule fiche, sous la référence de l'avis initial.
    attendus = {i for i, v in lu.items() if "20A" in v} - {"26-91505"} | {"26-88364"}
    assert set(corse_du_sud) == attendus and len(attendus) == 13, sorted(corse_du_sud)   # avant : aucune carte
    w = appels[0]["where"]
    assert 'code_departement like "2A"' in w and 'code_departement like "20A"' in w and '"2B"' not in w
    assert [r["official_ref"] for r in corse_du_sud["26-88364"]["rectificatifs"]] == ["26-91505"]
    assert {"26-101468", "26-92531", "26-92059", "26-99523"} <= set(corse_du_sud)
    assert all("2A" in t["departements"] and not any(d.startswith("20") for d in t["departements"])
               for t in corse_du_sud.values())

    haute_corse = _cartes(client, auth, query="", departements=["2B"], limit=50)
    assert set(haute_corse) == {i for i, v in lu.items() if "20B" in v}
    assert "26-100536" in haute_corse and "26-100536" not in corse_du_sud          # Haute-Corse seule
    assert "26-101468" in corse_du_sud and "26-101468" not in haute_corse          # Corse-du-Sud seule
    assert "26-99523" in corse_du_sud and "26-99523" in haute_corse                # les deux départements
    # Le rectificatif de 26-95985 (« Au lieu de 30/10/2026 à 12h00, lire 02/11/2026 à 12h00 », 26-102488) est lu.
    assert haute_corse["26-95985"]["date_limite"] == "2026-11-02"
    assert [r["official_ref"] for r in haute_corse["26-95985"]["rectificatifs"]] == ["26-102488"]

    # La zone de la note : une entreprise qui cherche en « 2A » voit ces avis « dans votre zone ».
    t = next(x for x in BoampSource().search(TenderCriteria(query="", departements=["2A"], limit=50))
             if x.provenance.official_ref == "26-101468")
    zone = next(c for c in score_tender(t, {}, {"departements": "2A"}).breakdown if c.key == "zone")
    assert t.departements == ["2A"] and zone.status == "ok", zone

    # Le repli payant de l'onglet « À venir » (avis d'attribution du BOAMP) demande lui aussi les deux formes.
    from app.services import renewal
    from app.sourcing import http
    vus = []
    monkeypatch.setattr(http, "get_with_retry", lambda url, params=None, **k: vus.append(params) or _Rep([]))
    renewal._fetch_attributions("voirie", ["2B"])
    assert 'code_departement like "2B"' in vus[0]["where"] and 'code_departement like "20B"' in vus[0]["where"]


# ═══ Outre-mer : 974 n'est plus 971, sur les avis réels ══════════════════════════════════════════════════════

def test_outre_mer_974_n_est_plus_971_sur_la_recherche_reelle(client, auth, monkeypatch):
    """Recherche réelle du 21/10/2026 sur 971 et 974 (43 avis ouverts), pour une entreprise de La Réunion (code
    postal 97400). Avant : tout l'outre-mer était « dans votre zone », et un avis annulé restait affiché."""
    from app.sourcing.base import TenderCriteria, TenderSource
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources.boamp import BoampSource
    _figer(monkeypatch)
    appels = _api_enregistree(monkeypatch, "outremer_971_974")
    assert client.put("/api/company/", headers=auth["headers"],
                      json={"name": "Entreprise de La Réunion (essai)", "postal_code": "97400"}).status_code == 200

    t = _cartes(client, auth, query="", departements=["971", "974"], limit=50)
    assert _zone(t["26-101170"]) == "ok"                 # Petite-Île (974)
    assert _zone(t["26-101957"]) == "ok"                 # 976 et 974
    assert _zone(t["26-101682"]) == "partiel"            # Bouillante (971) : avant, « dans votre zone »
    assert _zone(t["26-100178"]) == "partiel"            # Guyane, Martinique, Guadeloupe
    # Les suites du BOAMP, sur les mêmes avis réels :
    assert "26-99092" not in t and "26-101552" in t      # annulé le 14/10 (26-99478) ; relancé le 19/10
    assert [a["where"] for a in appels] == [q["params"]["where"] for q in RECHERCHES["outremer_971_974"]["requetes"]]
    assert t["26-92595"]["date_limite"] == "2026-10-30"  # « fixée au 30 octobre 2026 à 12H00 » (26-99887)
    assert t["26-92595"]["date_limite_initiale"] == "2026-10-23"
    assert t["26-82275"]["date_limite"] == "2026-10-21"  # repoussé deux fois (26-93361, 26-96200), repris
    assert [r["official_ref"] for r in t["26-82275"]["rectificatifs"]] == ["26-93361", "26-96200"]
    assert t["26-76317"]["date_limite"] == "2026-11-02"  # version européenne 26-94574, rendue seule
    assert "26-94574" not in t and "26-86226" not in t
    # Rectificatif européen publié sans date structurée (26-101691, forme observée le 21/10) : « non précisée ».
    assert t["26-95108"]["date_limite"] is None and t["26-95108"]["date_limite_rectifiee_non_lue"] is True
    assert t["26-95108"]["date_limite_initiale"] == "2026-10-21"

    # « 974 » seul : aucune carte de la Guadeloupe (l'API simulée filtre comme le BOAMP) ; l'avis annulé reste retiré.
    reunion = _cartes(client, auth, query="", departements=["974"], limit=50)
    assert reunion and all("974" in c["departements"] for c in reunion.values())
    assert "26-99092" not in reunion and "26-101170" in reunion and "26-98477" in reunion

    # Le filet de sécurité de la recherche, sur les avis réels rendus par une source qui ne filtre pas le
    # département : « 974 » garde 974 (seul ou avec d'autres) et écarte 971, 972, 973. Avant : « 97 », tout passait.
    reels = BoampSource().search(TenderCriteria(query="", departements=["971", "974"], limit=50))

    class _SansFiltre(TenderSource):
        name = "Essai sans filtre de département"

        def search(self, criteria):
            return [x.model_copy(deep=True) for x in reels]

    garde = TenderSearchService([_SansFiltre()]).search(TenderCriteria(departements=["974"]), {}, {})["tenders"]
    assert garde and all("974" in x.departements for x in garde)
    assert len(garde) == sum(1 for x in reels if "974" in x.departements)


# ═══ BOAMP : un avis rectifié, puis annulé ══════════════════════════════════════════════════════════════════

# 26-83249 (Collège Maurice Satineau, Guadeloupe) : publié le 25/08/2026, limite le 16/09 ; rectifié le 28/08
# (26-84145) ; annulé le 15/09 (26-89465). La recherche, rejouée le 01/09 puis le 15/09 sur ces lignes réelles.

def test_avis_rectifie_reste_affiche_avec_son_rectificatif(client, auth, monkeypatch):
    """01/09 : rectifié, toujours ouvert. Son rectificatif ne parle pas de la date limite : la date reste, et il est
    listé avec son lien. Son texte dit « Le marché est annulé » : ce n'est pas un avis d'annulation, on ne le lit pas
    comme tel (seul l'avis d'annulation retire un marché ; limite connue, docs/MOTEUR_LOT1.md, § Réunion)."""
    avis, suites = CAS["avis"], CAS["suites"]
    assert [r["idweb"] for r in avis] == ["26-83249"] and [r["idweb"] for r in suites] == ["26-84145", "26-89465"]
    _figer(monkeypatch, date(2026, 9, 1))
    _api(monkeypatch, avis, suites, jour=date(2026, 9, 1))
    t = _cartes(client, auth, query="voyages scolaires", departements=["971"])
    assert set(t) == {"26-83249"} and t["26-83249"]["date_limite"] == "2026-09-16"
    # Avant : le rectificatif n'était jamais lu (ni rattaché, ni listé).
    assert [r["official_ref"] for r in t["26-83249"].get("rectificatifs") or []] == ["26-84145"]
    assert t["26-83249"]["rectifie_le"] == "2026-08-28" and t["26-83249"]["date_limite_initiale"] is None
    assert t["26-83249"]["date_limite_rectifiee_non_lue"] is False


def test_avis_rectifie_puis_annule_retire(client, auth, monkeypatch):
    """15/09 : l'annulation est parue ; la limite du 16/09 n'est pas passée. Avant : l'avis annulé restait affiché."""
    avis, suites = CAS["avis"], CAS["suites"]
    _figer(monkeypatch, date(2026, 9, 15))
    _api(monkeypatch, avis, suites, jour=date(2026, 9, 15))
    assert _cartes(client, auth, query="voyages scolaires", departements=["971"]) == {}
    # Témoin : le même jour, sans son annulation, il serait encore affiché (c'est l'annulation qui le retire).
    _api(monkeypatch, avis, [s for s in suites if s["idweb"] != "26-89465"], jour=date(2026, 9, 15))
    assert set(_cartes(client, auth, query="voyages scolaires", departements=["971"])) == {"26-83249"}


# ═══ Alertes : sur les marchés réels, plus rien de caché ; un avis rectifié jamais renvoyé ════════════════════

_ALERTES = []


@pytest.fixture(autouse=True)
def _alertes_eteintes_apres_le_test():
    """Les alertes créées ici sont éteintes après chaque test (aucun autre test ne les rejoue)."""
    yield
    if _ALERTES:
        from app.models import SavedSearch
        db = SessionLocal()
        try:
            db.query(SavedSearch).filter(SavedSearch.id.in_(_ALERTES)).update({SavedSearch.active: False},
                                                                             synchronize_session=False)
            db.commit()
        finally:
            db.close()
        _ALERTES.clear()


def _alerte(email, **cols):
    from app.models import SavedSearch, User
    db = SessionLocal()
    try:
        uid = db.query(User).filter(User.email == email).first().id
        s = SavedSearch(user_id=uid, active=True, frequency="quotidienne", **cols)
        db.add(s)
        db.commit()
        _ALERTES.append(s.id)
        return s.id
    finally:
        db.close()


def _megalis_page_reelle(monkeypatch):
    """Mégalis Bretagne : la page réelle de la recherche « voirie » du 21/10/2026 (chantier Sources), sans réseau."""
    from app.sourcing.sources import atexo
    for nom in ("_REFUS", "_CACHE", "_RYTHME"):
        getattr(atexo, nom).clear()
    monkeypatch.setattr(atexo, "_INTERVALLE_MIN", 0.0)
    html = (FIX / "megalis_resultats_2026-10-21.html").read_text(encoding="utf-8")

    class _R:
        status_code, text, url = 200, html, "https://marches.megalis.bretagne.bzh/"

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **k):
            return _R()

        def post(self, url, **k):
            raise RuntimeError("pas de page 2 dans le jeu d'essai")

    monkeypatch.setattr(httpx, "Client", _Client)


def test_alerte_reelle_contient_les_marches_que_sa_note_cachait(client, auth, monkeypatch):
    """L'alerte « Voirie Finistère » (voirie, 29), telle que l'écran la crée (sans seuil propre), d'une entreprise qui
    a enregistré « Ce que je cherche » (seuil « bon potentiel » : 75 par défaut). Rejouée sur les marchés réels du
    21/10/2026 : 5 avis du BOAMP et 2 consultations de Mégalis. Avant : leur note avant dossier (60 à 67) était sous
    le seuil, l'alerte n'envoyait RIEN. Après : les 7 partent, les dates Mégalis sont lues, chaque référence porte
    sa source."""
    from app.services import alerts
    from app.services.profile import criteria_dict
    _figer(monkeypatch)
    assert client.put("/api/criteria/", headers=auth["headers"], json={}).status_code == 200
    _api_enregistree(monkeypatch, "voirie_29")
    _megalis_page_reelle(monkeypatch)
    sid = _alerte(auth["email"], name="Voirie Finistère", query="voirie", departements=["29"])

    reel = alerts.run_one_saved_search
    monkeypatch.setattr(alerts, "run_one_saved_search",
                        lambda s, db, mark=True: reel(s, db, mark) if s.id == sid else [])
    envoyes = []
    monkeypatch.setattr(alerts, "send_email",
                        lambda to, sujet, texte, *a, **k: envoyes.append((to, sujet, texte)) or True)
    alerts.run_tender_alerts(SessionLocal())

    mien = [e for e in envoyes if e[0] == auth["email"]]
    assert len(mien) == 1, envoyes
    texte = mien[0][2]
    assert "● Voirie Finistère (7 nouveau(x)) :" in texte
    for objet in ("VOIRIE COMMUNALE DE MELLAC", "Travaux d'aménagement de la Voie Romaine",
                  "Accord-cadre de travaux d'enrobés", "Construction du bâtiment du patronage laïque",
                  "Aménagement du parking de la piscine municipale",
                  "TRAVAUX DE RENFORCEMENT 2027-2028 DE LA VOIRIE COMMUNALE", "Travaux de voirie - Programme 2026"):
        assert objet in texte, objet
    assert "clôture 2026-12-07" in texte and "clôture 2026-11-19" in texte      # dates Mégalis lues (chantier Sources)
    assert "/100" not in texte and "… et " not in texte

    db = SessionLocal()
    try:
        from app.models import SavedSearch
        memoire = list(db.get(SavedSearch, sid).last_seen_refs or [])
        seuil = criteria_dict(db.get(SavedSearch, sid).user_id, db).get("go_threshold")
    finally:
        db.close()
    assert seuil == 75
    assert {e.split(" + ")[0] for e in memoire} == {
        "BOAMP|26-99804", "BOAMP|26-98864", "BOAMP|26-96920", "BOAMP|26-95577", "BOAMP|26-93634",
        "Mégalis Bretagne|242387", "Mégalis Bretagne|242908"}
    # Leur note avant dossier : toutes sous le seuil « bon potentiel » de l'entreprise (ce qui les cachait avant).
    _api_enregistree(monkeypatch, "voirie_29")
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.routers.sourcing import _tender_sources
    db = SessionLocal()
    try:
        gonogo = criteria_dict(db.get(SavedSearch, sid).user_id, db)
    finally:
        db.close()
    notes = [t.score.total for t in TenderSearchService(_tender_sources([])).search(
        TenderCriteria(query="voirie", departements=["29"], limit=25), {}, gonogo)["tenders"]]
    assert len(notes) == 7 and max(notes) < seuil, notes


def test_alerte_un_rectificatif_europeen_deja_envoye_n_est_jamais_renvoye(client, auth, monkeypatch):
    """Avant le lot, un rectificatif au format européen était une carte à part : 26-101544 (version rectifiée de
    26-93829, « Fourniture de carburant… », Loiret) a pu partir sous sa propre référence. Après le lot, la même
    procédure est UNE fiche, sous la référence de l'avis initial, son rectificatif rattaché. L'alerte qui avait
    envoyé 26-101544 le reconnaît : rien n'est renvoyé, et sa mémoire garde les deux références."""
    from app.models import SavedSearch
    from app.services.alerts import run_one_saved_search
    _figer(monkeypatch)
    avis = {r["idweb"]: r for r in SOURCES["avis"]}
    _api(monkeypatch, [avis["26-101544"]], [])
    sid = _alerte(auth["email"], name="Carburant Loiret", query="carburant", departements=["45"])
    db = SessionLocal()
    try:
        db.get(SavedSearch, sid).last_seen_refs = ["26-101544"]        # mémoire d'avant le lot : référence nue
        db.commit()
        s = db.get(SavedSearch, sid)
        frais = run_one_saved_search(s, db, mark=True)
        db.commit()
        memoire = list(s.last_seen_refs or [])
    finally:
        db.close()
    assert frais == []
    assert memoire == ["BOAMP|26-93829 + BOAMP|26-101544 + 26-101544"], memoire


# ═══ Une seule règle des départements dans les deux chantiers ═══════════════════════════════════════════════

def test_meme_regle_des_departements_dans_la_recherche_la_note_et_les_fins_de_contrat():
    """Les deux chantiers ont chacun leur fonction (recherche : base.dept_cle ; fins de contrat :
    decp.code_departement ; avis du BOAMP : dept_canonique ; note : code postal) : elles disent la même chose."""
    from app.services.decp import code_departement, dans_les_departements
    from app.sourcing.base import dans_departements, dept_cle
    from app.sourcing.scoring import _dep_du_code_postal
    from app.sourcing.sources.boamp import dept_canonique
    for saisi, attendu in (("6", "06"), ("06", "06"), ("29", "29"), ("2A", "2A"), ("2b", "2B"), ("974", "974"),
                           ("971", "971"), ("976", "976"), ("97", "97")):
        assert dept_cle(saisi) == code_departement(saisi) == attendu, saisi
    for boamp, attendu in (("6", "06"), ("974", "974"), ("20A", "2A"), ("20B", "2B"), ("2A", "2A"), ("75", "75")):
        assert dept_canonique(boamp) == attendu, boamp
    for cp, attendu in (("97400", "974"), ("97110", "971"), ("29200", "29"), ("06000", "06"), ("20000", "20")):
        assert _dep_du_code_postal(cp) == code_departement(cp) == attendu, cp
    for avis, voulus, oui in (("974", ["974"], True), ("971", ["974"], False), ("974", ["97"], True),
                              ("2A", ["2A"], True), ("2B", ["2A"], False), ("06", ["6"], True)):
        assert dans_departements(avis, voulus) is oui, (avis, voulus)
    for lieu, voulus, oui in (("97432", ["974"], True), ("97110", ["974"], False), ("97110", ["97"], True),
                              ("2A", ["2A"], True), ("20110", ["2A"], False), ("06088", ["06"], True)):
        assert dans_les_departements(lieu, voulus) is oui, (lieu, voulus)


def test_contrat_section_reunion():
    doc = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    assert "## Réunion des chantiers" in doc and "## Ce qui change pour le client : la liste complète" in doc
    for mot in ("20A", "26-83249", "26-89465", "26-101544", "26-101691", "24-65513", "non vérifié"):
        assert mot in doc, mot
