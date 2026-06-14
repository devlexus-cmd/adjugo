"""
Tests du moteur de sourcing — normalisation, provenance, dédup, scoring.
Fixtures enregistrées (payloads réels figés) → aucun appel réseau.
"""
from app.sourcing.sources.boamp import BoampSource
from app.sourcing.sources.sirene import SireneSource
from app.sourcing.search import _dedup_tenders, TenderSearchService
from app.sourcing.scoring import score_tender, score_company

# Payload BOAMP réel figé (avec champs en LISTE qui avaient cassé la 1re version)
BOAMP_ROW = {
    "idweb": "26-57883", "objet": "Rénovation des toitures du collège",
    "nomacheteur": "Département du Finistère", "code_departement": ["29"],
    "dateparution": "2026-06-01", "datelimitereponse": "2026-07-08T12:00:00+00:00",
    "descripteur_libelle": ["Toiture", "Couverture"], "descripteur_code": ["345"],
    "type_marche": ["TRAVAUX"], "procedure_libelle": ["Procédure adaptée"],
    "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:26-57883",
}

SIRENE_ROW = {
    "siren": "842206807", "nom_complet": "BP ELECTRICITE",
    "activite_principale": "43.21A", "tranche_effectif_salarie": "11",
    "date_creation": "2018-01-01",
    "siege": {"siret": "84220680700013", "code_postal": "29830",
              "libelle_commune": "LAMPAUL-PLOUDALMEZEAU", "adresse": "1 rue X",
              "etat_administratif": "A"},
}


def test_boamp_normalize_handles_list_fields():
    t = BoampSource()._normalize(BOAMP_ROW)
    assert t.objet.startswith("Rénovation")
    assert t.acheteur == "Département du Finistère"
    assert t.departements == ["29"]
    assert t.nature == "TRAVAUX"            # liste coercée en string
    assert t.procedure == "Procédure adaptée"
    assert t.provenance.source == "BOAMP"
    assert t.provenance.official_ref == "26-57883"
    assert "boamp.fr" in t.provenance.source_url
    assert t.confidence > 0


def test_boamp_missing_montant_is_unknown_not_invented():
    t = BoampSource()._normalize(BOAMP_ROW)
    assert t.montant_estime is None        # non publié → None, pas comblé
    sc = score_tender(t, {"postal_code": "29000"},
                      {"departements": "29", "specialites": "rénovation"})
    montant = next(c for c in sc.breakdown if c.key == "montant")
    assert montant.status == "inconnu" and montant.points == 0


def test_sirene_normalize_verified_siret_and_effectif():
    c = SireneSource()._normalize(SIRENE_ROW)
    assert c.nom == "BP ELECTRICITE"
    assert c.siret == "84220680700013" and c.siret_verified is True
    assert c.naf == "43.21A" and c.naf_label == "Électricité"
    assert c.effectif == 15                # tranche "11" → 15
    assert c.departement == "29"
    assert c.provenance.source == "SIRENE"
    assert "annuaire-entreprises" in c.provenance.source_url


def test_dedup_merges_same_official_ref():
    t1 = BoampSource()._normalize(BOAMP_ROW)
    # même AO, 2e source, mais montant présent ici → doit compléter t1
    t2 = BoampSource()._normalize(BOAMP_ROW)
    t2.montant_estime = 250000
    t2.provenance.source = "DECP"
    merged = _dedup_tenders([t1, t2])
    assert len(merged) == 1                          # dédupliqué
    assert merged[0].montant_estime == 250000        # champ manquant complété
    assert len(merged[0].also_seen_in) == 1          # 2e provenance conservée
    assert merged[0].confidence >= t1.confidence     # concordance → confiance +


TED_ROW = {
    "publication-number": "370456-2024",
    "notice-title": {"fra": ["Rénovation du système de chauffage du collège"]},
    "buyer-name": {"fra": ["AREA."]},
    "place-of-performance": ["FRK27", "FRA"],
    "classification-cpv": ["45331210", "45311000"],
    "links": {"html": {"FRA": "https://ted.europa.eu/fr/notice/-/detail/370456-2024"},
              "pdf": {"FRA": "https://ted.europa.eu/fr/notice/370456-2024/pdf"}},
}


def test_ted_normalize_multilingual_and_cpv():
    from app.sourcing.sources.ted import TedSource, _in_scope
    t = TedSource()._normalize(TED_ROW)
    assert t.objet.startswith("Rénovation")        # titre FR extrait du multilingue
    assert t.acheteur == "AREA."
    assert t.cpv == ["45331210", "45311000"]        # vrais codes CPV
    assert t.provenance.source == "TED"
    assert t.provenance.official_ref == "370456-2024"
    assert t.dce_url and "pdf" in t.dce_url
    # Périmètre pays : France incluse, Danemark exclu (filtrage multi-pays TED)
    fr = ("FR", "FRA")
    assert _in_scope(["FRK27", "FRA"], fr) and not _in_scope(["DK02"], fr)


def test_ted_multi_country_scope():
    from app.sourcing.sources.ted import _in_scope, _place_label, EU_COUNTRIES
    assert len(EU_COUNTRIES) >= 27          # UE-27 + EEE
    de = ("DE", "DEU")
    assert _in_scope(["DEA12"], de) and not _in_scope(["ES611"], de)
    assert _place_label(["DEA12"]).startswith("Allemagne")
    assert _place_label(["EL30"]).startswith("Grèce")   # NUTS grec « EL »


def test_company_score_unknown_when_no_naf():
    row = dict(SIRENE_ROW); row["activite_principale"] = None
    c = SireneSource()._normalize(row)
    sc = score_company(c, "Électricité", ["29"])
    act = next(x for x in sc.breakdown if x.key == "activite")
    assert act.status == "inconnu" and act.points == 0


def test_search_service_aggregates_and_scores():
    # Source factice (pas de réseau) renvoyant le payload figé
    class FakeSource(BoampSource):
        def search(self, criteria):
            return [self._normalize(BOAMP_ROW)]
    svc = TenderSearchService([FakeSource()])
    from app.sourcing.base import TenderCriteria
    out = svc.search(TenderCriteria(query="x"), {"postal_code": "29000"},
                     {"departements": "29", "specialites": "rénovation"})
    assert out["count"] == 1
    assert out["tenders"][0].score.total > 0
    assert out["errors"] == []
