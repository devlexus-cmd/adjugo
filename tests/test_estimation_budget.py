"""Tests déterministes de l'estimation budgétaire (DECP) — _fetch est stubbé : aucun réseau.
Couvre le seuil de comparables, le filtrage des bornes/durée, l'IQR et les quartiles."""
from unittest.mock import patch

from app.services.estimation_budget import estimer_budget, _trim_iqr, _MIN_COMPARABLES

_PATCH = "app.services.estimation_budget._fetch"


def _rows(montants, duree=12, annee="2024"):
    return [{"montant": m, "dureemois": duree, "datenotification": f"{annee}-01-01",
             "objet": f"objet {i}", "lieuexecution_code": "29"} for i, m in enumerate(montants)]


def test_trop_peu_de_comparables_ok_false():
    with patch(_PATCH, return_value=_rows([1000, 2000, 3000])):
        r = estimer_budget("nettoyage", "29")
    assert r["ok"] is False and r["nb_marches"] < _MIN_COMPARABLES


def test_quartiles_sur_echantillon_connu():
    montants = [100000, 120000, 140000, 160000, 180000, 200000, 220000]
    with patch(_PATCH, return_value=_rows(montants)):
        r = estimer_budget("nettoyage", "29")
    assert r["ok"] is True
    assert r["mediane"] == 160000
    assert r["min"] == 100000 and r["max"] == 220000
    assert r["q1"] <= r["mediane"] <= r["q3"]
    assert r["periode"] == "2024–2024"


def test_montants_hors_bornes_filtres():
    # 100 € (sous le plancher) et un méga-marché (au-dessus du plafond) sont écartés.
    montants = [100, 120000, 140000, 160000, 180000, 200000, 999_999_999]
    with patch(_PATCH, return_value=_rows(montants)):
        r = estimer_budget("nettoyage", "29")
    assert r["ok"] is True
    assert r["min"] >= 500 and r["max"] <= 80_000_000


def test_trim_iqr_retire_aberrant_mais_jamais_tout():
    assert 5_000_000 not in _trim_iqr([100, 110, 120, 130, 140, 150, 160, 5_000_000])
    assert _trim_iqr([1, 2]) == [1, 2]


def test_filtre_par_duree():
    # Une durée très différente (60 mois) est écartée quand la cible est 12 mois.
    rows = _rows([120000, 140000, 160000, 180000, 200000], duree=12) + _rows([5_000_000], duree=60)
    with patch(_PATCH, return_value=rows):
        r = estimer_budget("nettoyage", "29", duree_mois=12)
    assert r["ok"] is True and r["duree_filtree"] is True
    assert r["max"] <= 1_000_000   # le marché de 60 mois (5 M€) est exclu


def test_exemples_dedupliques_et_bornes():
    with patch(_PATCH, return_value=_rows([100000, 120000, 140000, 160000, 180000, 200000])):
        r = estimer_budget("nettoyage", "29")
    assert r["ok"] is True
    assert 0 < len(r["exemples"]) <= 6
    assert "convention" in r and "HT" in r["convention"]
