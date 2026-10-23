"""Recherche de PARTENAIRES (co-traitance) : des PME du département, pas des grands groupes.

Constat (vérification navigateur, 11/10/2026) : pour un lot « exécution dans le 56 », le
registre proposait SNEF (Marseille), SPIE (Saint-Ouen), CHUBB (Cergy)… L'API filtre le
département sur les ÉTABLISSEMENTS et l'affichage reprenait la ville du SIÈGE.
Désormais : catégorie INSEE « PME » (micro-entreprises comprises) et établissement local.
Aucun appel réseau : l'API SIRENE est simulée.
"""
import pytest


def _result(siren, nom, cat, siege_cp, siege_ville, local=None):
    e = {"siren": siren, "nom_complet": nom, "categorie_entreprise": cat, "etat_administratif": "A",
         "activite_principale": "43.21A", "nature_juridique": "5710",
         "siege": {"siret": siren + "00011", "code_postal": siege_cp, "libelle_commune": siege_ville,
                   "adresse": f"1 rue du Siège {siege_cp} {siege_ville}", "etat_administratif": "A"},
         "complements": {}, "finances": {}}
    if local:
        e["matching_etablissements"] = [{"siret": siren + "00099", "code_postal": local[0],
                                         "libelle_commune": local[1], "adresse": f"ZA {local[0]} {local[1]}",
                                         "etat_administratif": "A"}]
    return e


@pytest.fixture
def api(monkeypatch):
    from app.sourcing.sources.sirene import SireneSource
    calls = []

    def fake_get(self, params):
        calls.append(dict(params))
        return [_result("552100554", "GRAND GROUPE ELEC", "GE", "13015", "MARSEILLE 15EME", local=("56270", "PLOEMEUR")),
                _result("811234567", "ELEC DU GOLFE", "PME", "56000", "VANNES")]
    monkeypatch.setattr(SireneSource, "_get", fake_get)
    return calls


def test_filtre_pme_seulement_si_demande(api):
    from app.sourcing.sources.sirene import SireneSource
    SireneSource().search(activity="electricite", departement="56", pme_only=True)
    SireneSource().search(activity="electricite", departement="56")
    assert api[0].get("categorie_entreprise") == "PME"
    assert "categorie_entreprise" not in api[1]        # sourcing des collectivités : inchangé


def test_etablissement_du_departement_et_non_le_siege(api):
    from app.sourcing.sources.sirene import SireneSource
    res = SireneSource().search(activity="electricite", departement="56")
    gg = next(c for c in res if c.nom == "GRAND GROUPE ELEC")
    assert gg.ville == "PLOEMEUR" and gg.code_postal == "56270" and gg.siret.endswith("00099")
    pme = next(c for c in res if c.nom == "ELEC DU GOLFE")
    assert pme.ville == "VANNES"                        # pas d'établissement listé : siège conservé


def test_recherche_de_partenaires_du_groupement_en_pme(api, monkeypatch):
    import app.services.groupement_verdict as gv
    gv._SIRENE_CACHE.clear()
    monkeypatch.setattr("app.sourcing.search.CompanySearchService._enrich_red_flags", lambda self, c: None)
    gv._discover_sirene("electricite", "56", [])
    assert api and api[-1].get("categorie_entreprise") == "PME" and api[-1].get("departement") == "56"


def test_annuaire_perso_decouverte_en_pme_locales(monkeypatch):
    import app.services.registre as registre
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"total_results": 1, "results": [
                _result("552100554", "GRAND GROUPE ELEC", "GE", "13015", "MARSEILLE 15EME", local=("56270", "PLOEMEUR"))]}

    class C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            seen.update(params or {})
            return R()
    monkeypatch.setattr(registre, "_client", lambda *a, **k: C())
    out = registre.discover_cotraitants(activity="electricite", departement="56")
    assert seen.get("categorie_entreprise") == "PME"
    assert out["results"][0]["city"] == "PLOEMEUR" and out["results"][0]["departement"] == "56"
