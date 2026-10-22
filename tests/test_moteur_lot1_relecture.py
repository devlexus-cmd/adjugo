"""Moteur de recherche, lot 1 « Dire juste » : relecture de la partie serveur (docs/MOTEUR_LOT1.md, section
« Relecture »). Une remarque, un test ; chacun échoue sur 0afc1ed (production) et sur ef5c096 (réunion des chantiers),
sauf mention.

Jeux d'essai RÉELS, sans réseau pendant les tests :
  - tests/fixtures/moteur_lot1_relecture/boamp_travaux_2026-10-21.json : une recherche « travaux » sans département,
    limite 25 (celle des alertes), faite PAR LE CODE le 21/10/2026 sur l'API publique du BOAMP (en-tête AdjugoBot) :
    les avis, leurs suites (100 lignes), la relecture des 50 premiers avis initiaux ; corps des suites réduit au bloc
    « rectificatif », un nom et une adresse de contact retirés ;
  - tests/fixtures/moteur_lot1_relecture/boamp_questions_26-100294.json : l'avis 26-100294 (limite le 23/10/2026) et
    son seul rectificatif 26-100865 (16/10/2026), qui ne change que le délai des questions, relus le 21/10/2026 ;
  - les jeux d'essai de la réunion (tests/fixtures/moteur_lot1_reunion/) et du chantier Services.
"""
import json
import logging
import pathlib
import re
from datetime import date

import pytest

from app.core.database import SessionLocal

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
RELECTURE = FIX / "moteur_lot1_relecture"
TRAVAUX = json.loads((RELECTURE / "boamp_travaux_2026-10-21.json").read_text(encoding="utf-8"))["requetes"]
QUESTIONS = json.loads((RELECTURE / "boamp_questions_26-100294.json").read_text(encoding="utf-8"))
REUNION = json.loads((FIX / "moteur_lot1_reunion" / "boamp_recherches_2026-10-21.json").read_text(encoding="utf-8"))["recherches"]
LE_21_10 = date(2026, 10, 21)


class _Jour(date):
    @classmethod
    def today(cls):
        return cls(LE_21_10.year, LE_21_10.month, LE_21_10.day)


def _figer(monkeypatch):
    from app.sourcing import search as search_mod
    from app.sourcing.sources import boamp
    monkeypatch.setattr(boamp, "date", _Jour)
    monkeypatch.setattr(search_mod, "date", _Jour)
    search_mod._CB.clear()


class _Rep:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"results": [dict(r) for r in self._rows]}


# Relecture des avis initiaux, sous ses deux formes : « (idweb in (…) AND datelimitereponse < date'…') OR … »
# (après la relecture du lot) ou « idweb in (…) OR … » (ef5c096). 0afc1ed n'en fait aucune.
_RELU = re.compile(r"^\(?idweb in \(([^)]*)\)(?: AND datelimitereponse < date'(\d{4}-\d{2}-\d{2})'\))? OR ")


def _relue(w):
    m = _RELU.match(w)
    return (set(re.findall(r'"(\d{2}-\d+)"', m.group(1))), m.group(2)) if m else None


def _date_passee(r, borne):
    d = (r.get("datelimitereponse") or "")[:10]
    return borne is None or (bool(d) and d < borne)


def _api(monkeypatch, principal, suites, relues):
    """L'API du BOAMP rejouée sur des lignes réelles : la requête principale rend `principal` (page par page), celle
    des suites les lignes qui visent un avis demandé (plus les rectificatifs récents si le code les demande), la
    relecture les avis demandés (bornés à la date publiée passée quand le code le demande) et leurs annulations."""
    from app.sourcing import http
    appels = []

    def fake(url, params=None, timeout=12, tries=3, headers=None):
        p = dict(params or {})
        appels.append(p)
        w = p.get("where", "")
        if "datelimitereponse >=" in w:
            o, n = int(p.get("offset") or 0), int(p.get("limit") or 15)
            return _Rep(principal[o:o + n])
        rel = _relue(w)
        if rel:
            ids, borne = rel
            return _Rep([r for r in relues if r["idweb"] in ids and _date_passee(r, borne)]
                        + [s for s in suites if s.get("nature") == "ANNULATION" and set(s.get("annonce_lie") or []) & ids])
        m = re.search(r"annonce_lie in \(([^)]*)\)", w)
        ids = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
        rows = [s for s in suites if set(s.get("annonce_lie") or []) & ids]
        if 'nature="RECTIFICATIF" AND dateparution' in w:
            rows += [s for s in suites if s.get("nature") == "RECTIFICATIF" and not set(s.get("annonce_lie") or []) & ids]
        return _Rep(rows)

    monkeypatch.setattr(http, "get_with_retry", fake)
    return appels


# ═══ 1. La relecture ne reprend que les avis dont la date publiée est passée ═════════════════════════════════

def test_relecture_ne_reprend_que_les_avis_dont_la_date_publiee_est_passee(monkeypatch, caplog):
    """Recherche réelle « travaux », limite 25 (les alertes). ef5c096 relisait tout avis rectifié dont la nouvelle date
    n'est pas passée : 75 fiches au lieu de 25, dont 35 avis encore ouverts sous leur ancienne date (déjà trouvés sur
    leur propre page), et 14 avis visés jamais relus (plafond de 50, sans ligne de journal), dont 26-82275 (limite
    publiée le 30/09, repoussée au 07/10 puis au 21/10 par 26-96200), l'exemple « repris » de la réunion. Après : seuls les avis dont
    la date publiée est passée sont repris, tous les avis visés sont demandés."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources.boamp import BoampSource
    _figer(monkeypatch)
    principal, suites, relus_le_21 = (q["results"] for q in TRAVAUX)
    ouverts = {r["idweb"] for r in relus_le_21 if (r.get("datelimitereponse") or "")[:10] >= "2026-10-21"}
    passes = {r["idweb"] for r in relus_le_21 if (r.get("datelimitereponse") or "")[:10] < "2026-10-21"}
    assert len(principal) == 25 and len(relus_le_21) == 50 and len(ouverts) == 35 and len(passes) == 15
    # 26-82275 n'est pas dans la relecture enregistrée (au-delà des 50) : sa ligne réelle vient de la réunion.
    r82275 = next(r for q in REUNION["outremer_971_974"]["requetes"] for r in q["results"] if r["idweb"] == "26-82275")
    assert r82275["datelimitereponse"][:10] == "2026-09-30"
    appels = _api(monkeypatch, principal, suites, relus_le_21 + [r82275])

    with caplog.at_level(logging.INFO, logger="adjugo"):
        res = TenderSearchService([BoampSource()]).search(TenderCriteria(query="travaux", limit=25), {}, {})
    cartes = {t.provenance.official_ref: t for t in res["tenders"]}
    principaux = {r["idweb"] for r in principal}
    # Un rectificatif européen de la page prend la référence de son avis initial (une fiche par procédure).
    europeens = {lien for r in principal if r.get("etat") == "RECTIFICATIF" and r.get("nature") == "APPEL_OFFRE"
                 for lien in r.get("annonce_lie") or []}
    repris = set(cartes) - principaux - europeens

    assert not (repris & ouverts), sorted(repris & ouverts)        # ef5c096 : les 35
    assert "26-82275" in repris and cartes["26-82275"].date_limite == "2026-10-21"
    assert cartes["26-82275"].date_limite_initiale == "2026-09-30"
    assert repris == passes | {"26-82275"}                         # les 15 relus le 21/10 dont la date est passée
    assert len(res["tenders"]) == 25 + 16                          # ef5c096 : 75 ; 0afc1ed : 25, aucun repris
    assert res["has_more"] is True                                 # la page de 25 lignes est pleine
    # La relecture : une seule requête, bornée à la date publiée passée, qui demande TOUS les avis visés.
    relecture = [a["where"] for a in appels if _relue(a["where"])]
    assert len(relecture) == 1
    assert "datelimitereponse < date'2026-10-21'" in relecture[0].split(" OR (")[0]
    demandes, _ = _relue(relecture[0])
    # 65 depuis le contrôle des bugs du 22/10 : 26-99040 (« remise des offre », au singulier) est lu comme changeant
    # la date limite de 26-89213 (au 30/10/2026), qui est donc demandé lui aussi ; avant, 64 (26-89213 oublié).
    assert len(demandes) == 65 and "26-82275" in demandes and "26-89213" in demandes and passes <= demandes
    assert not any("non relus" in x.getMessage() for x in caplog.records)


def test_relecture_plafonnee_jamais_en_silence(monkeypatch, caplog):
    """Cas CONSTRUIT : 120 avis initiaux visés par des rectificatifs récents (plus que le plafond de 100). Le journal
    dit combien ne sont pas relus ; aucun n'est inventé."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource
    _figer(monkeypatch)
    suites = [{"idweb": f"26-{200000 + i}", "annonce_lie": [f"26-{100000 + i}"], "nature": "RECTIFICATIF",
               "etat": "RECTIFICATIF", "famille": "FNS", "dateparution": "2026-10-20",
               "donnees": json.dumps({"FNSimple": {"suite": {"infosRectif":
                                      "Rubrique : Date et heure limites de réception des plis, "
                                      "Au lieu de 19/10/2026 à 12h00, lire 05/11/2026 à 12h00"}}})}
              for i in range(120)]
    appels = _api(monkeypatch, [], suites, [])
    with caplog.at_level(logging.INFO, logger="adjugo"):
        assert BoampSource().search(TenderCriteria(query="travaux", limit=25)) == []
    demandes, _ = _relue(next(a["where"] for a in appels if _relue(a["where"])))
    assert len(demandes) == 100
    assert any("plafond de 100 atteint ; 20 non relus" in x.getMessage() for x in caplog.records)


# ═══ 2. « Charger plus » se juge sur les lignes reçues, pas sur les fiches ═════════════════════════════════

def test_charger_plus_reste_propose_quand_une_page_perd_un_avis_annule(client, auth, monkeypatch):
    """Vraie réponse du BOAMP du 21/10/2026 (43 avis « travaux » 971 + 974, BOAMP seul : ni Mégalis ni TED en
    outre-mer), par la route de l'écran, 15 par page. La page 2 perd 26-99092, annulé par 26-99478 : ef5c096 y
    rendait has_more=False, et les 13 avis ouverts de la page 3 n'étaient plus atteignables. 0afc1ed affichait
    l'avis annulé."""
    _figer(monkeypatch)
    rec = REUNION["outremer_971_974"]["requetes"]
    principal = rec[0]["results"]
    suites = [r for q in rec[1:] if "donnees" in (q["params"].get("select") or "") for r in q["results"]]
    relues = [r for q in rec[1:] if q["params"]["where"].startswith("idweb in") for r in q["results"]]
    assert len(principal) == 43
    _api(monkeypatch, principal, suites, relues)
    pages, vues = [], []
    for offset in (0, 15, 30):
        r = client.post("/api/sourcing/search", headers=auth["headers"],
                        json={"query": "", "departements": ["971", "974"], "limit": 15, "offset": offset})
        assert r.status_code == 200, r.text
        refs = [t["provenance"]["official_ref"] for t in r.json()["tenders"]]
        pages.append((refs, r.json()["has_more"]))
        vues += refs
    assert "26-99092" not in pages[1][0] and "26-101552" in vues            # annulé, retiré ; sa relance reste
    assert pages[0][1] is True and pages[1][1] is True, pages              # ef5c096 : page 2 sans « Charger plus »
    assert pages[2][1] is False and len(pages[2][0]) == 13                 # la dernière page : 13 lignes, la fin
    assert len(vues) == len(set(vues))                                     # aucun avis montré deux fois
    assert "26-92595" in pages[2][0]                                       # repoussé au 30/10, page 3


# ═══ 3. Corse : un code postal « 20… » couvre 2A et 2B ═══════════════════════════════════════════════════════

def test_corse_entreprise_au_code_postal_corse_voit_les_avis_corses_dans_sa_zone():
    """Avis corses réels du BOAMP (21/10/2026), entreprise corse sans département saisi. 0afc1ed : zone « ok » (« 20A »
    coupé à « 20 »), mais l'avis gardait « 20A ». ef5c096 : « Hors zone (2A) », note en baisse de 33 points."""
    from app.sourcing.scoring import score_tender
    from app.sourcing.sources.boamp import BoampSource
    lignes = {r["idweb"]: r for r in REUNION["corse_2A_2B"]["requetes"][0]["results"]}
    attendu = {"26-101468": ["2A"], "26-101638": ["69", "2B", "2A"], "26-100536": ["2B"]}
    for idweb, deps in attendu.items():
        t = BoampSource()._normalize(lignes[idweb])
        assert t.departements == deps, (idweb, t.departements)            # 0afc1ed : « 20A », « 20B »
        for cp in ("20090", "20200"):
            zone = next(c for c in score_tender(t, {"postal_code": cp}, {}).breakdown if c.key == "zone")
            assert zone.status == "ok" and zone.points == zone.max_points, (idweb, cp, zone)
    # Saisi, « 2A » reste distinct de « 2B » ; un avis hors de Corse reste hors zone pour une entreprise corse.
    t2b = BoampSource()._normalize(lignes["26-100536"])
    assert next(c for c in score_tender(t2b, {}, {"departements": "2A"}).breakdown if c.key == "zone").status == "partiel"
    from app.sourcing.base import dans_departements
    assert dans_departements("13", ["20"]) is False and dans_departements("2B", ["20"]) is True


# ═══ 4. Un rectificatif du délai des questions laisse la date limite ═════════════════════════════════════════

def test_rectificatif_du_delai_des_questions_garde_la_date_de_l_avis(monkeypatch):
    """26-100865 ne change que le délai des questions (« … 10 jours calendaires avant la date limite fixée pour la
    réception des offres », lire « 7 jours ») : la date limite de 26-100294 reste le 23/10/2026. ef5c096 : « limite
    non précisée » (la date limite citée comme repère était lue comme changée). 0afc1ed : rectificatif jamais lu."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource, lire_rectificatif
    _figer(monkeypatch)
    avis, rect = QUESTIONS["avis"], QUESTIONS["rectificatif"]
    assert rect["annonce_lie"] == ["26-100294"] and "avant la date limite fixée pour la réception des offres" in rect["donnees"]
    assert lire_rectificatif(rect)["concerne"] is False
    _api(monkeypatch, [avis], [rect], [])
    (t,) = BoampSource().search(TenderCriteria(query="plan de référence", departements=["82"], limit=15))
    assert t.date_limite == "2026-10-23" and t.date_limite_initiale is None
    assert t.date_limite_rectifiee_non_lue is False
    assert [p.official_ref for p in t.rectificatifs] == ["26-100865"]
    # Cas CONSTRUIT sur les textes réels : un rectificatif qui change la date ET cite la date limite comme repère d'un
    # autre délai donne toujours la nouvelle date.
    construit = dict(rect, donnees=json.dumps({"FNSimple": {"suite": {"infosRectif": [
        "Rubrique : Date et heure limites de réception des plis, Au lieu de 23/10/2026 à 12h00, lire 06/11/2026 à 12h00",
        json.loads(rect["donnees"])["FNSimple"]["suite"]["infosRectif"]]}}}, ensure_ascii=False))
    assert lire_rectificatif(construit) == {"concerne": True, "date": "2026-11-06", "forme": "texte"}


# ═══ 5. « Durée lue » : seulement un nombre de mois rendu par l'IA ═══════════════════════════════════════════

def test_duree_lue_seulement_si_l_ia_rend_un_nombre_de_mois(client, auth, monkeypatch, caplog):
    """Repli payant de l'onglet « À venir » sur de vrais avis d'attribution du BOAMP (29), IA simulée qui répond 0,
    « 36 » et null au lieu d'une durée, et 24 pour un avis. 0afc1ed et ef5c096 : 0 et « 36 » remplacés par la durée
    par défaut mais dits « réels » (« durée 36 mois (réelle) » à l'écran, « durée lue » au journal)."""
    from app.services import decp, renewal
    from app.sourcing import http as sourcing_http
    boamp = json.loads((FIX / "moteur_lot1_services" / "boamp_attributions_29.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"count": 0, "renewals": [], "errors": []})
    monkeypatch.setattr(sourcing_http, "get_with_retry", lambda *a, **k: _Rep(boamp["results"]))
    monkeypatch.setattr(renewal, "complete_json", lambda *a, **k: {"avis": [
        {"index": 0, "garder": True, "duree_mois": 0}, {"index": 1, "garder": True, "duree_mois": "36"},
        {"index": 2, "garder": True, "duree_mois": None}, {"index": 3, "garder": True, "duree_mois": 24}]})
    monkeypatch.setattr(renewal, "date", _Jour)
    with caplog.at_level(logging.INFO, logger="adjugo"):
        r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie", "departements": ["29"]})
    assert r.status_code == 200, r.text
    fins = {f["idweb"]: f for f in r.json()["renewals"]}
    assert set(fins) == {"25-34232", "25-32908", "25-10734", "25-8460"}
    assert [fins[i]["duree_estimee"] for i in ("25-34232", "25-32908", "25-10734")] == [True, True, True]
    assert fins["25-8460"]["duree_estimee"] is False and fins["25-8460"]["duree_mois"] == 24
    assert all(fins[i]["duree_mois"] == 36 for i in ("25-34232", "25-32908", "25-10734"))
    ligne = next(x.getMessage() for x in caplog.records if "repli payant « À venir »" in x.getMessage())
    assert "fins de contrat trouvées=4 (durée lue 1, durée estimée 3)" in ligne
    from app.services.renewal import detect_renewals
    monkeypatch.setattr(renewal, "_fetch_attributions", lambda *a, **k: [
        {"idweb": "25-8460", "objet": "x", "acheteur": "", "dept": "29", "lieu": "", "date_attribution": "2025-01-23",
         "url": ""}])
    monkeypatch.setattr(renewal, "complete_json", lambda *a, **k: {"avis": [{"index": 0, "duree_mois": True}]})
    assert detect_renewals("voirie", ["29"], {})["renewals"][0]["duree_estimee"] is True     # un booléen n'est pas une durée


# ═══ 6. Alertes : jamais vers une adresse non confirmée, rien de perdu ════════════════════════════════════════

_ALERTES = []


@pytest.fixture(autouse=True)
def _alertes_eteintes_apres_le_test():
    """Les alertes créées ici sont éteintes après chaque test : aucun autre test ne les rejoue (aucun réseau)."""
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


def test_alerte_jamais_vers_une_adresse_non_confirmee_rien_de_perdu(client, auth, monkeypatch):
    """L'alerte réelle « voirie » 29 du 21/10/2026 (7 marchés notés de 60 à 67), d'un compte dont l'adresse n'est pas
    confirmée : aucun courriel (ef5c096 : un courriel de 7 marchés vers l'adresse non prouvée), et rien n'est marqué
    « déjà vu ». Une fois l'adresse confirmée, les 7 partent. 0afc1ed : aucun courriel (tous sous le seuil de 75), mais
    les 7 marqués « déjà vus » dès le premier passage, donc jamais envoyés ensuite."""
    from app.models import SavedSearch, User
    from app.services import alerts
    from tests.test_moteur_lot1_reunion import _api_enregistree, _figer as _figer_reunion, _megalis_page_reelle
    _figer_reunion(monkeypatch)
    assert client.put("/api/criteria/", headers=auth["headers"], json={}).status_code == 200
    _api_enregistree(monkeypatch, "voirie_29")
    _megalis_page_reelle(monkeypatch)
    sid = _alerte(auth["email"], name="Voirie Finistère", query="voirie", departements=["29"])

    def _adresse_confirmee(oui):
        db = SessionLocal()
        try:
            db.query(User).filter(User.email == auth["email"]).first().email_verified = oui
            db.commit()
        finally:
            db.close()

    reel = alerts.run_one_saved_search
    monkeypatch.setattr(alerts, "run_one_saved_search", lambda s, db, mark=True: reel(s, db, mark) if s.id == sid else [])
    envoyes = []
    monkeypatch.setattr(alerts, "send_email", lambda to, sujet, texte, *a, **k: envoyes.append((to, texte)) or True)
    try:
        _adresse_confirmee(False)
        alerts.run_tender_alerts(SessionLocal())
        assert [e for e in envoyes if e[0] == auth["email"]] == []
        db = SessionLocal()
        try:
            assert not (db.get(SavedSearch, sid).last_seen_refs or [])      # rien de marqué « déjà vu »
        finally:
            db.close()
        _adresse_confirmee(True)
        alerts.run_tender_alerts(SessionLocal())
    finally:
        _adresse_confirmee(True)
    mien = [e for e in envoyes if e[0] == auth["email"]]
    assert len(mien) == 1 and "● Voirie Finistère (7 nouveau(x)) :" in mien[0][1], envoyes


# ═══ 7. « Tester » une alerte : la référence de l'avis, comme avant ════════════════════════════════════════════

def test_tester_une_alerte_rend_la_reference_nue(client, auth, monkeypatch):
    """« Tester » (POST /api/saved-searches/{id}/run) liste aussi les marchés sous le seuil (décision 11 ; 0afc1ed n'en
    rend qu'un), et `tenders[].ref` reste la référence de l'avis (ef5c096 : « BOAMP|26-… »), la source à part."""
    from app.models import SavedSearch, User
    from app.sourcing import search
    from app.sourcing.schemas import NormalizedTender, Provenance, Score
    db = SessionLocal()
    try:
        uid = db.query(User).filter(User.email == auth["email"]).first().id
        s = SavedSearch(user_id=uid, name="Voirie", query="voirie", departements=["29"], active=False,
                        frequency="quotidienne", min_score=70)
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()

    def _marche(ref, note):
        return NormalizedTender(objet=f"Travaux de voirie {ref}", acheteur="Brest métropole", departements=["29"],
                                date_limite="2026-11-30", score=Score(total=note), dedup_key=f"voirie{ref}|brest|",
                                provenance=Provenance(source="BOAMP", source_url=f"https://www.boamp.fr/pages/avis/?q=idweb:{ref}",
                                                      official_ref=ref))
    monkeypatch.setattr(search.TenderSearchService, "search", lambda self, crit, company=None, gonogo=None: {
        "tenders": [_marche("26-90336", 90), _marche("26-96286", 30)], "errors": []})
    r = client.post(f"/api/saved-searches/{sid}/run", headers=auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["new_matches"] == 2
    assert [(t["source"], t["ref"]) for t in r.json()["tenders"]] == [("BOAMP", "26-90336"), ("BOAMP", "26-96286")]


# ═══ Contrat ═════════════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_section_relecture():
    doc = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    assert "## Relecture" in doc
    for mot in ("26-82275", "26-100865", "26-99092", "Outre-mer, repli payant", "seuil de compatibilité",
                "adresse confirmée", "has_more", "À valider par Eliot"):
        assert mot in doc, mot
