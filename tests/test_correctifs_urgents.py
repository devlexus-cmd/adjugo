"""Correctifs urgents d'octobre 2026 (études moteur, organisation, veille, rédaction).

Un test par correctif ; chacun échouait avant la correction. Aucun réseau réel, IA simulée.
  1. BOAMP : les départements 01 à 09 sont demandés sous les deux formes (« 06 » et « 6 »).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"


def _static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


# ═══ 1. BOAMP : « nettoyage » + 06 renvoie des avis ════════════════════════════════════════════

class _Rep:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"results": self._rows}


def _boamp_capture(monkeypatch, rows):
    """Remplace l'appel HTTP du BOAMP : garde la requête construite, rend `rows` si la requête
    demande la forme « 6 » (comme le vrai BOAMP, qui enregistre « 6 » et non « 06 »)."""
    import app.sourcing.http as http
    vues = []

    def fake(url, params=None, timeout=12, **kw):
        vues.append(params)
        where = (params or {}).get("where", "")
        return _Rep(rows if 'code_departement like "6"' in where else [])

    monkeypatch.setattr(http, "get_with_retry", fake)
    return vues


_AVIS_VENCE = {
    "idweb": "26-101010", "objet": "Nettoyage des bâtiments communaux", "nomacheteur": "Ville de Vence",
    "code_departement": ["6"], "dateparution": "2026-10-10", "datelimitereponse": "2099-11-06",
    "descripteur_libelle": ["Nettoyage"], "descripteur_code": ["123"], "type_marche": "SERVICES",
    "procedure_libelle": "Procédure adaptée", "url_avis": "https://www.boamp.fr/avis/detail/26-101010",
}


def test_boamp_departement_06_interroge_les_deux_formes(monkeypatch):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources.boamp import BoampSource
    vues = _boamp_capture(monkeypatch, [_AVIS_VENCE])
    crit = TenderCriteria(query="nettoyage", departements=["06"], limit=15)
    res = TenderSearchService([BoampSource()]).search(crit, {}, {})
    where = vues[0]["where"]
    assert 'code_departement like "06"' in where and 'code_departement like "6"' in where
    # L'avis remonte, ramené à la forme unique « 06 », et passe le filtre de département.
    assert res["count"] == 1 and res["tenders"][0].acheteur == "Ville de Vence"
    assert res["tenders"][0].departements == ["06"]


def test_boamp_departements_hors_01_09_inchanges(monkeypatch):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource, dept_canonique, formes_boamp
    vues = _boamp_capture(monkeypatch, [])
    BoampSource().search(TenderCriteria(query="voirie", departements=["29", "2A", "974"]))
    where = vues[0]["where"]
    for f in ("29", "2A", "974"):
        assert f'code_departement like "{f}"' in where
    assert 'code_departement like "9"' not in where and 'like "2"' not in where
    assert formes_boamp("06") == ["06", "6"] and formes_boamp("29") == ["29"]
    assert dept_canonique("6") == "06" and dept_canonique("974") == "974" and dept_canonique("2a") == "2A"
    # « 6 » saisi seul est compris comme « 06 ».
    assert TenderCriteria(departements=["6"]).departements == ["06"]
