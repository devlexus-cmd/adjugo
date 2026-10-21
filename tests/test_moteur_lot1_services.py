"""
Lot 1 « Dire juste », partie serveur, chantier « Services » (contrat : docs/MOTEUR_LOT1.md, section « Services »).

Points de la note de décisions du 21/10/2026 : 4 bis (outre-mer dans les fins de contrat), 5 (partenaires : panne de
la DECP, « PME seulement »), 6 (alertes de marchés : plus de tri caché par la note, « hebdomadaire », références
avec leur source), 7 (veille masquée fermée), 8 (repli payant de l'onglet « À venir » noté dans le journal), 9 (outil
rejouable de mesure du rappel).

Jeux d'essai : de vraies réponses publiques lues le 21/10/2026 (DECP, BOAMP ; en-tête AdjugoBot), rangées dans
tests/fixtures/moteur_lot1_services/, numéros des titulaires remplacés par des numéros fictifs. Les tests tournent
SANS réseau : toute lecture est remplacée par ces fichiers, et l'IA est simulée.
"""
import csv
import json
import logging
import pathlib
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.core.database import SessionLocal

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "moteur_lot1_services"
JOUR = date(2026, 10, 21)          # jour de lecture des jeux d'essai


def _fixture(nom: str) -> dict:
    return json.loads((FIX / nom).read_text(encoding="utf-8"))


class _Jour(date):
    @classmethod
    def today(cls):
        return cls(JOUR.year, JOUR.month, JOUR.day)


class _Rep:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _user(email):
    from app.models import User
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


# ═══ 4 bis. Outre-mer dans les fins de contrat ═══════════════════════════════════════════════════════════════

def test_fins_de_contrat_sur_le_code_complet_974_ne_voit_plus_971_corse_et_metropole_inchangees(monkeypatch):
    from app.services import decp
    lignes = _fixture("decp_dep_974.json")["results"] + _fixture("decp_dep_971.json")["results"]
    corse = _fixture("decp_dep_2A.json")["results"]
    demandes = []

    def _fetch(query, departements, cpv=None, per=100):
        demandes.append(list(departements))
        return lignes + corse

    monkeypatch.setattr(decp, "_fetch", _fetch)
    monkeypatch.setattr(decp, "_acheteur_name", lambda siren: "")
    monkeypatch.setattr(decp, "date", _Jour)

    res = decp.detect_renewals_decp("travaux", ["974"], {})
    assert demandes[-1] == ["974"]                       # avant : « 97 », toute l'outre-mer demandée à la DECP
    assert res["renewals"], res
    assert {r["dept"] for r in res["renewals"]} == {"974"}
    objets_971 = {r["objet"].strip()[:60] for r in _fixture("decp_dep_971.json")["results"]}
    assert not [r for r in res["renewals"] if r["objet"][:60] in objets_971]

    # Guadeloupe : 971 seul, jamais 974.
    res = decp.detect_renewals_decp("travaux", ["971"], {})
    assert res["renewals"] and {r["dept"] for r in res["renewals"]} == {"971"}

    # Corse intacte : « 2A » reste « 2A » ; un code postal corse (« 20… ») n'est pas deviné 2A.
    res = decp.detect_renewals_decp("travaux", ["2A"], {})
    assert demandes[-1] == ["2A"] and {r["dept"] for r in res["renewals"]} == {"2A"}
    assert decp.code_departement("20110") == "20" and not decp.dans_les_departements("20110", ["2A"])

    # Métropole inchangée ; « 6 » saisi seul est lu « 06 » (forme unique d'Adjugo).
    assert [decp.code_departement(x) for x in ("29", "29232", "29000", "6", "06", "2A", "2b", "97432", "974", "97")] \
        == ["29", "29", "29", "06", "06", "2A", "2B", "974", "974", "97"]
    assert decp.dans_les_departements("29232", ["29"]) and decp.dans_les_departements("97432", ["974"])
    assert not decp.dans_les_departements("97110", ["974"])
    assert decp.dans_les_departements("97110", ["97"])   # « 97 » saisi : toute l'outre-mer, comme avant


def test_onglet_a_venir_demande_le_code_complet_et_note_la_zone_d_outre_mer(client, auth, monkeypatch):
    from app.services import decp, renewal
    demandes = []

    def _fetch(query, departements, cpv=None, per=100):
        demandes.append(list(departements))
        return _fixture("decp_dep_974.json")["results"] + _fixture("decp_dep_971.json")["results"]

    monkeypatch.setattr(decp, "_fetch", _fetch)
    monkeypatch.setattr(decp, "_acheteur_name", lambda siren: "")
    monkeypatch.setattr(decp, "date", _Jour)
    monkeypatch.setattr(renewal, "detect_renewals", lambda *a, **k: pytest.fail("aucun repli payant attendu"))
    r = client.post("/api/sourcing/renewals", headers=auth["headers"],
                    json={"query": "travaux", "departements": ["974"]})
    assert r.status_code == 200, r.text
    assert demandes == [["974"]]                         # avant : la route coupait à « 97 »
    assert {x["dept"] for x in r.json()["renewals"]} == {"974"}

    # La note de zone d'une fin de contrat suit la même règle (« Ce que je cherche » : 974).
    renouv = JOUR + timedelta(days=60)
    dans = renewal._score({"objet": "travaux", "dept": "974"}, {"departements": "974"}, None, renouv, JOUR)
    hors = renewal._score({"objet": "travaux", "dept": "971"}, {"departements": "974"}, None, renouv, JOUR)
    assert dans - hors == 25 - 6                         # avant : 974 et 971 notés pareil (« 97 »)
    assert renewal._score({"objet": "travaux", "dept": "06"}, {"departements": "6"}, None, renouv, JOUR) == dans
    assert renewal._score({"objet": "travaux", "dept": "29"}, {"departements": "29,56"}, None, renouv, JOUR) == dans


# ═══ 5. Partenaires : une panne de la DECP n'est plus lue « 0 marché » ; « PME seulement » ═══════════════════

def test_panne_de_la_decp_jamais_lue_zero_marche(client, auth, monkeypatch):
    from app.services import decp
    from app.sourcing.schemas import NormalizedCompany, Provenance
    from app.sourcing.search import CompanySearchService
    from app.sourcing.sources.sirene import SireneSource
    from app.routers import sourcing

    def _panne(*a, **k):
        raise httpx.ConnectError("DECP injoignable")

    monkeypatch.setattr(decp, "get_with_retry", _panne)
    with pytest.raises(Exception) as panne:
        decp.wins_by_siren("900000001")                  # avant : {"count": 0, …}, une absence affirmée
    assert type(panne.value).__name__ == "DecpIndisponible"
    monkeypatch.setattr(decp, "get_with_retry", lambda *a, **k: _Rep({"results": []}))   # réponse sans compte
    with pytest.raises(decp.DecpIndisponible):
        decp.wins_by_siren("900000001")
    # La DECP répond : le compte lu est rendu tel quel, zéro compris.
    monkeypatch.setattr(decp, "get_with_retry", lambda *a, **k: _Rep({"total_count": 0, "results": []}))
    assert decp.wins_by_siren("900000001") == {"count": 0, "last_date": "", "domains": []}

    def _entreprise(siren):
        return NormalizedCompany(nom=f"Entreprise {siren}", siren=siren, departement="29",
                                 provenance=Provenance(source="SIRENE", source_url="", official_ref=siren))

    class _Registre(SireneSource):
        def search(self, **k):
            return [_entreprise("900000011"), _entreprise("900000012")]

    def _wins(siren):
        if siren == "900000011":
            raise decp.DecpIndisponible("ConnectError")
        return {"count": 0, "last_date": "", "domains": []}

    monkeypatch.setattr(decp, "wins_by_siren", _wins)
    res = CompanySearchService([_Registre()]).discover(activity="electricite", departement="29")
    par = {c.siren: c for c in res["companies"]}
    assert par["900000011"].past_wins is None            # inconnu (avant : 0)
    assert par["900000012"].past_wins == 0               # lu : zéro

    # Sur la page du marché : la note ne dit jamais « aucun marché gagné » sans l'avoir lu.
    from app.models import Project
    db = SessionLocal()
    try:
        p = Project(user_id=_user(auth["email"]).id, name="Marché de test (partenaires)")
        db.add(p)
        db.commit()
        pid = p.id
    finally:
        db.close()
    monkeypatch.setattr(sourcing, "COMPANY_SOURCES", [_Registre()])
    monkeypatch.setattr(sourcing, "RED_FLAG_SOURCE", None)
    r = client.post("/api/sourcing/cotraitants", headers=auth["headers"],
                    json={"project_id": pid, "activity": "electricite", "departement": "29"})
    assert r.status_code == 200, r.text
    notes = {c["siren"]: (c["synergy"] or {}).get("note") for c in r.json()["companies"]}
    assert notes["900000011"] == sourcing.NOTE_MARCHES_NON_VERIFIES
    assert notes["900000012"] == "Aucun marché public gagné trouvé en source DECP pour ce SIRET."
    assert {c["siren"]: c["past_wins"] for c in r.json()["companies"]} == {"900000011": None, "900000012": 0}


def test_pme_seulement_sur_les_deux_recherches_de_partenaires(client, auth, monkeypatch):
    from app.models import Project
    from app.sourcing.sources import sirene
    from app.services import decp
    params = []

    def _get(self, p):
        params.append(dict(p))
        return []

    monkeypatch.setattr(sirene.SireneSource, "_get", _get)
    monkeypatch.setattr(decp, "wins_by_siren", lambda s: pytest.fail("aucune entreprise : aucune lecture DECP"))
    db = SessionLocal()
    try:
        p = Project(user_id=_user(auth["email"]).id, name="Rénovation de l'école (test PME)",
                    ai_analysis={"details": {"allotissement": "Lot 1 : Électricité ; Lot 2 : Plomberie",
                                             "lieu_execution": "29000 Quimper"}})
        db.add(p)
        db.commit()
        pid = p.id
    finally:
        db.close()

    # « Chercher » des partenaires depuis la page du marché.
    r = client.post("/api/sourcing/cotraitants", headers=auth["headers"],
                    json={"project_id": pid, "activity": "electricite", "departement": "29"})
    assert r.status_code == 200, r.text
    assert params and all(x.get("categorie_entreprise") == "PME" for x in params), params

    # La répartition proposée partie par partie (optimiseur de groupement).
    params.clear()
    r = client.post("/api/sourcing/groupement", headers=auth["headers"], json={"project_id": pid})
    assert r.status_code == 200, r.text
    assert r.json()["n_lots"] == 2
    assert params and all(x.get("categorie_entreprise") == "PME" for x in params), params


# ═══ 6. Alertes de marchés ═══════════════════════════════════════════════════════════════════════════════

def _marche(ref, score, source="BOAMP", objet=None, aussi=(), date_limite="2026-11-30"):
    from app.sourcing.schemas import NormalizedTender, Provenance, Score
    objet = objet or f"Travaux de voirie {ref}"
    t = NormalizedTender(objet=objet, acheteur="Brest métropole", date_limite=date_limite, departements=["29"],
                         provenance=Provenance(source=source, source_url=f"https://www.boamp.fr/avis/detail/{ref}",
                                               official_ref=ref),
                         score=Score(total=score), dedup_key=f"{objet.lower().replace(' ', '')[:40]}|brest|{date_limite}")
    t.also_seen_in = [Provenance(source=s, source_url="", official_ref=r) for s, r in aussi]
    return t


_ALERTES_CREEES = []


@pytest.fixture(autouse=True)
def _alertes_eteintes_apres_le_test():
    """Les alertes créées ici sont éteintes après chaque test : un autre test qui lance l'appel programmé des alertes
    ne les rejoue jamais (aucune recherche réelle)."""
    yield
    if _ALERTES_CREEES:
        from app.models import SavedSearch
        db = SessionLocal()
        try:
            db.query(SavedSearch).filter(SavedSearch.id.in_(_ALERTES_CREEES)).update(
                {SavedSearch.active: False}, synchronize_session=False)
            db.commit()
        finally:
            db.close()
        _ALERTES_CREEES.clear()


def _alerte(email, **cols):
    from app.models import SavedSearch
    db = SessionLocal()
    try:
        s = SavedSearch(user_id=_user(email).id, name=cols.pop("name", "Voirie"), query="voirie",
                        departements=["29"], active=True, **cols)
        db.add(s)
        db.commit()
        _ALERTES_CREEES.append(s.id)
        return s.id
    finally:
        db.close()


def _rejouer(sid, mark=True):
    from app.models import SavedSearch
    from app.services.alerts import run_one_saved_search
    db = SessionLocal()
    try:
        s = db.get(SavedSearch, sid)
        fresh = run_one_saved_search(s, db, mark=mark)
        db.commit()
        return fresh, list(s.last_seen_refs or [])
    finally:
        db.close()


def _recherche(monkeypatch, tenders):
    from app.sourcing import search
    monkeypatch.setattr(search.TenderSearchService, "search",
                        lambda self, crit, company=None, gonogo=None: {"tenders": list(tenders()), "errors": []})


def test_alerte_n_ecarte_plus_un_marche_a_cause_de_sa_note_avant_dossier(client, auth, monkeypatch):
    sid = _alerte(auth["email"], frequency="quotidienne", min_score=70)
    _recherche(monkeypatch, lambda: [_marche("26-90336", 90), _marche("26-96286", 30)])
    fresh, _ = _rejouer(sid, mark=False)
    assert [f["objet"] for f in fresh] == ["Travaux de voirie 26-90336", "Travaux de voirie 26-96286"]
    # « Tester » l'alerte (aperçu) dit le même compte.
    r = client.post(f"/api/saved-searches/{sid}/run", headers=auth["headers"])
    assert r.status_code == 200 and r.json()["new_matches"] == 2, r.text


def test_references_avec_leur_source_anciennes_reconnues_rien_renvoye_deux_fois(client, auth, monkeypatch):
    from app.models import SavedSearch
    sid = _alerte(auth["email"], frequency="quotidienne")
    db = SessionLocal()
    try:
        s = db.get(SavedSearch, sid)
        # Mémoire d'une alerte en service avant le lot 1 : références nues, de la plus ancienne à la plus récente.
        s.last_seen_refs = [f"25-{i}" for i in range(1, 41)] + ["26-90336"]
        db.commit()
    finally:
        db.close()

    # Jour 1 : l'avis déjà vu (référence ancienne) est vu sur le BOAMP ET sur Mégalis : il n'est pas renvoyé.
    jour = {"n": 1}

    def _tenders():
        if jour["n"] == 1:
            return [_marche("26-90336", 80, aussi=[("Mégalis Bretagne", "2734871")]), _marche("26-98235", 60)]
        # Jour 2 : le BOAMP ne répond pas ; le même marché n'est rendu que par Mégalis (son numéro de consultation).
        return [_marche("2734871", 80, source="Mégalis Bretagne", objet="Travaux de voirie 26-90336"),
                _marche("26-98235", 60)]

    _recherche(monkeypatch, _tenders)
    fresh, memoire = _rejouer(sid)
    assert [f["ref"] for f in fresh] == ["BOAMP|26-98235"]
    # Une entrée par marché, chaque référence avec le nom de sa source, l'ancienne forme fusionnée dans son entrée,
    # l'ordre gardé (plus ancien d'abord) et les marchés vus aujourd'hui en fin de liste.
    assert memoire[:40] == [f"25-{i}" for i in range(1, 41)]
    assert memoire[40:] == ["BOAMP|26-90336 + Mégalis Bretagne|2734871 + 26-90336", "BOAMP|26-98235"]
    jour["n"] = 2
    fresh, memoire = _rejouer(sid)
    assert fresh == []                                    # avant : le marché revenait par sa référence Mégalis
    assert len(memoire) == 42
    r = client.get("/api/saved-searches/", headers=auth["headers"])
    assert next(a for a in r.json() if a["id"] == sid)["matches_seen"] == 42   # des marchés, pas des références

    # Une référence Mégalis égale à un ancien numéro nu d'un AUTRE marché ne le masque plus une fois migré.
    _recherche(monkeypatch, lambda: [_marche("26-98235", 60, source="TED", objet="Fourniture de mobilier scolaire")])
    fresh, _ = _rejouer(sid, mark=False)
    assert [f["ref"] for f in fresh] == ["TED|26-98235"]


def test_memoire_bornee_aux_plus_anciens_jamais_au_hasard(auth, monkeypatch):
    from app.models import SavedSearch
    borne = 500                                           # la borne d'avant le lot 1, inchangée
    sid = _alerte(auth["email"], frequency="quotidienne")
    db = SessionLocal()
    try:
        s = db.get(SavedSearch, sid)
        s.last_seen_refs = ["26-1"] + [f"25-{i}" for i in range(2, borne + 1)]
        db.commit()
    finally:
        db.close()
    # « 26-1 », le plus ancien, est encore ouvert : il reste en mémoire ; « 25-2 », le suivant, sort.
    _recherche(monkeypatch, lambda: [_marche("26-1", 50), _marche("26-2", 50)])
    fresh, memoire = _rejouer(sid)
    assert [f["ref"] for f in fresh] == ["BOAMP|26-2"]
    assert len(memoire) == borne
    assert memoire[-2:] == ["BOAMP|26-1 + 26-1", "BOAMP|26-2"]
    assert memoire[0] == "25-3" and "25-2" not in memoire


def test_hebdomadaire_reellement_applique(auth, monkeypatch):
    from app.models import SavedSearch
    from app.services import alerts
    maintenant = datetime.now(timezone.utc)
    hebdo = _alerte(auth["email"], name="Hebdo", frequency="hebdomadaire")
    quoti = _alerte(auth["email"], name="Quotidienne", frequency="quotidienne")
    jamais = _alerte(auth["email"], name="Hebdo neuve", frequency="hebdomadaire")
    db = SessionLocal()
    try:
        db.get(SavedSearch, hebdo).last_run = maintenant - timedelta(days=2)
        db.get(SavedSearch, quoti).last_run = maintenant - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    rejouees = []
    monkeypatch.setattr(alerts, "run_one_saved_search", lambda s, db, mark=True: rejouees.append(s.id) or [])
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: True)
    res = alerts.run_tender_alerts(SessionLocal())
    assert hebdo not in rejouees                          # avant : servie chaque jour, comme une quotidienne
    assert quoti in rejouees and jamais in rejouees
    assert res["weekly_not_due"] >= 1
    db = SessionLocal()
    try:
        db.get(SavedSearch, hebdo).last_run = maintenant - timedelta(days=7)
        db.commit()
    finally:
        db.close()
    rejouees.clear()
    alerts.run_tender_alerts(SessionLocal())
    assert hebdo in rejouees


def test_courriel_compte_les_marches_au_dela_des_dix_premiers(auth, monkeypatch):
    from app.services import alerts
    sid = _alerte(auth["email"], name="Voirie Finistère", frequency="quotidienne")
    douze = [{"objet": f"Travaux de voirie n° {i}", "acheteur": "Brest métropole", "score": 50,
              "date_limite": "2026-11-30", "lieu": "29", "source": "BOAMP", "url": f"https://www.boamp.fr/avis/{i}",
              "ref": f"BOAMP|26-{i}"} for i in range(12)]
    monkeypatch.setattr(alerts, "run_one_saved_search", lambda s, db, mark=True: douze if s.id == sid else [])
    envoyes = []
    monkeypatch.setattr(alerts, "send_email", lambda to, sujet, texte, *a, **k: envoyes.append((to, sujet, texte)) or True)
    alerts.run_tender_alerts(SessionLocal())
    mien = [e for e in envoyes if e[0] == auth["email"]]
    assert len(mien) == 1
    texte = mien[0][2]
    assert "● Voirie Finistère (12 nouveau(x)) :" in texte
    assert texte.count("   • Travaux de voirie n° ") == 10
    assert "   … et 2 autres marchés : relancez cette recherche dans Adjugo pour les voir tous." in texte
    assert "/100" not in texte


# ═══ 7. La veille masquée refuse proprement, sans rien débiter ═══════════════════════════════════════════════

def test_adresses_de_la_veille_masquee_refusent_sans_debiter(client, auth, monkeypatch):
    import app.routers.amont as amont_router
    from app.services import llm
    monkeypatch.delenv("PROJETS_A_VENIR", raising=False)
    lectures, appels_ia = [], []

    class _Deliberations:
        def fetch_recent(self, *a, **k):
            lectures.append(1)
            return []

    monkeypatch.setattr(amont_router, "DeliberationSource", _Deliberations)
    monkeypatch.setattr(amont_router, "detect_projets", lambda *a, **k: appels_ia.append(1) or {"projets": []})
    monkeypatch.setattr(amont_router, "detect_from_deliberations", lambda *a, **k: appels_ia.append(1) or [])
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: appels_ia.append(1) or {})
    h = auth["headers"]
    avant = _user(auth["email"])
    texte = "Délibération du conseil municipal : rénovation de l'école élémentaire prévue en 2027, lot voirie."
    reps = [client.post("/api/amont/scan", headers=h, json={"departements": ["29"]}),
            client.post("/api/amont/analyze-text", headers=h, json={"text": texte}),
            client.post("/api/amont/analyze-upload", headers=h,
                        files={"file": ("deliberation.txt", texte.encode(), "text/plain")})]
    for r in reps:
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == amont_router.FERMEE
    r = client.post("/api/amont/auto", headers=h, json={"enabled": True})
    assert r.status_code == 404 and r.json()["detail"] == amont_router.FERMEE_AUTO
    # Retirer son accord reste toujours possible ; l'état se lit toujours.
    assert client.post("/api/amont/auto", headers=h, json={"enabled": False}).json() == {"enabled": False}
    assert client.get("/api/amont/auto", headers=h).json()["enabled"] is False
    apres = _user(auth["email"])
    assert lectures == [] and appels_ia == []
    assert (apres.trial_analyses_used or 0) == (avant.trial_analyses_used or 0)
    assert (apres.analyses_used_this_month or 0) == (avant.analyses_used_this_month or 0)
    assert not apres.amont_alerts_enabled

    # Interrupteur allumé (vague 1 de la veille) : les adresses répondent comme avant.
    monkeypatch.setenv("PROJETS_A_VENIR", "1")
    assert client.post("/api/amont/analyze-text", headers=h, json={"text": "trop court"}).status_code == 422
    r = client.post("/api/amont/scan", headers=h, json={"departements": ["29"]})
    assert r.status_code == 200 and r.json()["count"] == 0 and lectures == [1]
    assert client.post("/api/amont/auto", headers=h, json={"enabled": True}).json() == {"enabled": True}
    assert client.post("/api/amont/auto", headers=h, json={"enabled": False}).json() == {"enabled": False}


# ═══ 8. Le repli payant de l'onglet « À venir » est noté dans le journal ═════════════════════════════════════

def test_repli_payant_note_dans_le_journal_sans_donnee_personnelle(client, auth, monkeypatch, caplog):
    from app.services import decp, renewal
    from app.sourcing import http as sourcing_http
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {
        "count": 0, "renewals": [], "errors": ["DECP indisponible : ConnectError"], "source": "DECP"})
    boamp = _fixture("boamp_attributions_29.json")
    monkeypatch.setattr(sourcing_http, "get_with_retry", lambda *a, **k: _Rep(boamp))
    # IA simulée : la durée n'est lue que pour le premier avis ; les autres gardent une durée estimée par type.
    monkeypatch.setattr(renewal, "complete_json", lambda *a, **k: {"avis": [
        {"index": 0, "garder": True, "duree_mois": 24, "type": "marché"},
        {"index": 1, "garder": False}, {"index": 2, "garder": True}, {"index": 3, "garder": True}]})
    monkeypatch.setattr(renewal, "date", _Jour)
    avant = _user(auth["email"])
    with caplog.at_level(logging.INFO, logger="adjugo"):
        r = client.post("/api/sourcing/renewals", headers=auth["headers"],
                        json={"query": "voirie", "departements": ["29"]})
    assert r.status_code == 200, r.text
    fins = r.json()["renewals"]
    assert fins and {f["idweb"] for f in fins} <= {"25-34232", "25-10734", "25-8460"}
    lignes = [x.getMessage() for x in caplog.records if "repli payant « À venir »" in x.getMessage()]
    assert len(lignes) == 1, lignes
    ligne = lignes[0]
    estimees = sum(1 for f in fins if f["duree_estimee"])
    assert "motif=DECP indisponible" in ligne and "départements=29" in ligne
    assert f"fins de contrat trouvées={len(fins)} (durée lue {len(fins) - estimees}, durée estimée {estimees})" in ligne
    assert "analyse débitée" in ligne
    assert "avis BOAMP=" + ",".join(f["idweb"] for f in fins) in ligne
    # Sans donnée personnelle : ni adresse, ni identifiant, ni mots tapés.
    u = _user(auth["email"])
    assert auth["email"] not in ligne and auth["email"].split("@")[0] not in ligne
    assert f"user {u.id}" not in ligne and "voirie" not in ligne
    debit = ((u.trial_analyses_used or 0) - (avant.trial_analyses_used or 0)
             + (u.analyses_used_this_month or 0) - (avant.analyses_used_this_month or 0))
    assert debit >= 1                                     # le repli reste payant (décision 12), annoncé à l'écran plus tard

    # Rien trouvé : remboursé, et noté aussi.
    caplog.clear()
    monkeypatch.setattr(sourcing_http, "get_with_retry", lambda *a, **k: _Rep({"results": []}))
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"count": 0, "renewals": [], "errors": []})
    with caplog.at_level(logging.INFO, logger="adjugo"):
        r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie"})
    assert r.status_code == 200
    lignes = [x.getMessage() for x in caplog.records if "repli payant « À venir »" in x.getMessage()]
    assert len(lignes) == 1 and "motif=DECP sans résultat" in lignes[0] and "analyse remboursée" in lignes[0]
    assert "fins de contrat trouvées=0" in lignes[0] and "départements=aucun" in lignes[0]


# ═══ 9. L'outil rejouable de mesure du rappel ════════════════════════════════════════════════════════════════

def _outil():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mesure_rappel", ROOT / "scripts" / "mesure_rappel.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mesure_du_rappel_rejouable_sans_reseau(tmp_path):
    mr = _outil()
    entree = tmp_path / "pme.csv"
    entree.write_text("pme;siren;mots_cles;departements;type_marche\n"
                      "PME 01;90000000100012;voirie, routier, réseaux, assainissement;2A,2B;travaux\n"
                      "PME 02;12;;;\n", encoding="utf-8")
    page = _fixture("decp_titulaire_900000001.json")
    requetes = []

    def _get(url, params=None, timeout=None, headers=None):
        requetes.append((url, dict(params), dict(headers or {})))
        return _Rep(page)

    sortie = tmp_path / "depart"
    r = mr.collecter(str(entree), str(sortie), date(2026, 10, 21), get=_get, pause=lambda s: None)
    # Une seule entreprise valable ; la DECP lue par l'en-tête honnête, titulaire 1, 2 ou 3, sur 12 mois.
    assert len(requetes) == 1
    url, params, headers = requetes[0]
    assert url.endswith("decp-2022-marches-valides/records")
    assert headers["User-Agent"].startswith("AdjugoBot/1.0") and "contact@adjugo.pro" in headers["User-Agent"]
    for i in (1, 2, 3):
        assert f'startswith(titulaire_id_{i}, "900000001")' in params["where"]
    assert "datenotification >= date'2025-10-21'" in params["where"]
    marches = list(csv.DictReader((sortie / "marches.csv").open(encoding="utf-8"), delimiter=";"))
    # Le jeu d'essai renvoie aussi des marchés de 2024 : écartés (hors des 12 mois) ; doublons comptés une fois.
    assert all("2025-10-21" <= m["date_notification"] <= "2026-10-21" for m in marches)
    cles = [(m["objet"].lower()[:80], m["acheteur_id"], m["date_notification"]) for m in marches]
    assert len(cles) == len(set(cles)) == 8
    assert {m["role"] for m in marches} == {"titulaire"}
    def _m(debut, liste):
        return [x for x in liste if x["objet"].startswith(debut)]
    assert {m["publicite"] for m in _m("Travaux courants de maintenance", marches)} == {"avec"}   # appel d'offres
    assert _m("Elargissement du pont", marches)[0]["publicite"] == "avec"        # adaptée, 244 374 € de travaux
    assert json.loads((sortie / "collecte.json").read_text(encoding="utf-8"))["marches"] == 8
    with pytest.raises(SystemExit):                                       # jamais écraser les vérifications
        mr.collecter(str(entree), str(sortie), date(2026, 10, 21), get=_get, pause=lambda s: None)

    # Mesure de départ, avant toute vérification : la Corse se lit « 2A » ou « 20… » (inconnue), en fourchette.
    b = mr.mesurer(str(sortie), "avant-lot1")
    assert (b["total"], b["montres"], b["manques"], b["indetermines"]) == (8, 0, 3, 5)
    assert b["rappel_bas"] == 0.0 and b["rappel_haut"] == 0.625
    # Mathys vérifie les annonces : la mesure est rejouée sur la même liste.
    for m in marches:
        m["avis_vu"] = "non" if m["objet"].startswith("DENSIFICATION") else "oui"
    with (sortie / "marches.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=mr.COLONNES_MARCHES, delimiter=";")
        w.writeheader()
        w.writerows(marches)
    b = mr.mesurer(str(sortie), "verifie")
    lignes = list(csv.DictReader((sortie / "rappel_verifie.csv").open(encoding="utf-8"), delimiter=";"))
    assert {x["verdict"] for x in _m("Travaux courants de maintenance", lignes)} == {"montré"}   # « 2A », routier
    station = _m("Construction d'une station", lignes)[0]
    assert station["verdict"] == "manqué" and station["raison"].startswith("écarté par : mots")  # aucun mot cherché
    assert _m("DENSIFICATION", lignes)[0]["raison"] == "écarté par : source"   # annonce hors des sources lues
    assert _m("Elargissement du pont", lignes)[0]["verdict"] == "manqué"       # « pont » : pas un mot cherché
    quasquara = _m("Réhabilitation réseau", lignes)
    assert len(quasquara) == 2 and {x["zone"] for x in quasquara} == {"inconnue"}   # code postal corse 20142
    assert {x["verdict"] for x in quasquara} == {"indéterminé"}
    assert (b["total"], b["montres"], b["manques"], b["indetermines"]) == (8, 2, 4, 2)
    assert (b["rappel_bas"], b["rappel_haut"]) == (0.25, 0.5)
    assert b["manques_par_raison"] == {"mots": 3, "source": 1}
    # Le bilan ne contient que des comptes : ni objet, ni numéro d'entreprise.
    bilan = (sortie / "bilan_verifie.json").read_text(encoding="utf-8")
    assert "900000001" not in bilan and "station" not in bilan.lower()
    assert "Rappel entre" in mr._phrase(b) or "Rappel :" in mr._phrase(b)


def test_mesure_du_rappel_refuse_le_depot_et_suit_la_regle_de_la_recherche_boamp(tmp_path, monkeypatch):
    mr = _outil()
    with pytest.raises(mr.HorsDuDepot):
        mr.collecter(str(ROOT / "pme.csv"), str(tmp_path / "x"), get=lambda *a, **k: None)
    with pytest.raises(mr.HorsDuDepot):
        mr.collecter(str(tmp_path / "pme.csv"), str(ROOT / "mesure"), get=lambda *a, **k: None)
    # Les motifs rejoués sont ceux que la recherche envoie au BOAMP (app/sourcing/sources/boamp.py).
    from app.sourcing import http as sourcing_http
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource
    vus = []
    monkeypatch.setattr(sourcing_http, "get_with_retry",
                        lambda url, params=None, **k: vus.append(params) or _Rep({"results": []}))
    for requete in ("plombier chauffagiste", "VRD enrobés", "toiture zinc ardoise couverture étanchéité bardage x",
                    "", "élagage"):
        vus.clear()
        BoampSource().search(TenderCriteria(query=requete))
        where = vus[0]["where"]
        attendus = mr.motifs(requete)
        assert attendus
        for motif, prefixe in attendus:
            assert f'objet like "{motif}{"*" if prefixe else ""}"' in where, (requete, motif, where)
        assert where.count("objet like ") == len(attendus)
    assert mr.mots_retenus("Réfection des enrobés de la RD 12", "VRD enrobés")
    assert mr.mots_retenus("Travaux de plomberie sanitaire", "plombier")
    assert not mr.mots_retenus("Travaux de couverture", "VRD")
    assert mr.zone("97432", "Code postal", ["974"]) == "oui" and mr.zone("97110", "Code postal", ["974"]) == "non"
    assert mr.zone("53", "Code région", ["53"]) == "inconnue" and mr.zone("", "", ["29"]) == "inconnue"
    assert mr.type_du_cpv("45233141-9") == "travaux" and mr.type_du_cpv("90510000-5") == "services"
    assert mr.type_du_cpv("44611600-2") == "fournitures" and mr.type_du_cpv("") == ""
    assert mr.publicite("Marché passé sans publicité ni mise en concurrence préalable", 89447, "45111100-9") == "sans"
    assert mr.publicite("Procédure adaptée", 75950, "75200000-8") == "avec"       # services au-dessus de 60 000 €
    assert mr.publicite("Procédure adaptée", 60991, "45210000-2") == "inconnue"   # travaux sous 100 000 €
    assert mr.publicite("", 500000, "45210000-2") == "inconnue"
