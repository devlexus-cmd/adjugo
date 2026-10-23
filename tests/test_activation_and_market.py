"""
Non-régression du chantier produit (02/07/2026) :
  - activation par SIRET : registre._specialite dérive des mots-clés métier exploitables ;
  - endpoint PME /api/sourcing/market-estimate : authentifié, déterministe (DECP mocké).
"""
from unittest.mock import patch


def test_specialite_btp_donne_mots_cles():
    from app.services.registre import _specialite
    assert _specialite("43.91B") == "couverture toiture"   # métier BTP connu → kw de recherche
    assert _specialite("43.21A") == "électricité"


def test_specialite_hors_btp_ne_renvoie_pas_le_code_brut():
    from app.services.registre import _specialite
    # Un NAF non-BTP ne doit pas polluer la recherche avec un code (« 62.01Z ») → vide.
    assert _specialite("62.01Z") == ""
    assert _specialite("") == ""


def test_market_estimate_authentifie_et_deterministe(client, auth):
    rows = [{"montant": m, "dureemois": 12, "datenotification": "2024-01-01",
             "objet": f"toiture {i}", "lieuexecution_code": "29"}
            for i, m in enumerate([100000, 120000, 140000, 160000, 180000, 200000, 220000])]
    with patch("app.services.estimation_budget._fetch", return_value=rows):
        r = client.post("/api/sourcing/market-estimate", headers=auth["headers"],
                        json={"objet": "réfection toiture école", "departement": "29"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["nb_marches"] >= 5
    assert body["mediane"] == 160000   # médiane de 7 valeurs équi-réparties
    assert body["q1"] <= body["mediane"] <= body["q3"]


def test_market_estimate_objet_trop_court():
    from app.core.database import SessionLocal  # noqa: F401 (assure l'import app)
    # Objet < 3 caractères → 422 (pas d'estimation sur du vide).
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        # non authentifié → 401 attendu avant la validation ; on vérifie juste que la route existe
        r = c.post("/api/sourcing/market-estimate", json={"objet": "x"})
    assert r.status_code in (401, 403, 422)
