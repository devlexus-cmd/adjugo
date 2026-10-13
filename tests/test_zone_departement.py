"""« Où vous gagnez / perdez », par département : le département vient du code postal du lieu
d'exécution, sinon du numéro écrit entre parenthèses (« Angers (49) ») ; jamais d'une année."""
from types import SimpleNamespace

import pytest

from app.routers.agent import _zone


def _p(lieu):
    return SimpleNamespace(ai_analysis={"details": {"lieu_execution": lieu}})


@pytest.mark.parametrize("lieu, attendu", [
    ("49100 Angers", "49"),
    ("Angers (49)", "49"),
    ("Anjoumont ( 49 )", "49"),
    ("Ajaccio (2A)", "2A"),
    ("Bastia (2b)", "2B"),
    ("20200 Bastia", "2B"),
    ("Saint-Denis (974)", "974"),
    ("97400 Saint-Denis", "974"),
    ("Brest (29) — 29200 Brest", "29"),
    ("Livraison en 2024", "Inconnu"),
    ("Travaux (2024)", "Inconnu"),
    ("12 rue de la Paix", "Inconnu"),
    ("Lot (3)", "Inconnu"),
    ("", "Inconnu"),
])
def test_zone(lieu, attendu):
    assert _zone(_p(lieu)) == attendu


def test_avertissement_capacites_declarees_sans_doublon():
    """« Répondre à plusieurs ? » : une seule phrase sur les capacités déclarées, en tête ; celle qui
    nomme le partenaire si le barème l'a écrite, sinon la phrase générale."""
    from app.services.groupement_verdict import WARN_DECLARE, with_declare_warning
    nommee = "Verdict fondé sur des capacités déclarées par vous (Breizh) — à confirmer auprès du partenaire"
    w = with_declare_warning([{"source": "declare"}], ["Autre remarque", nommee, WARN_DECLARE])
    assert w == [nommee, "Autre remarque"]
    assert with_declare_warning([{"source": "saisi"}], ["Autre remarque"]) == [WARN_DECLARE, "Autre remarque"]
    assert with_declare_warning([{"source": "sirene"}], ["Autre remarque", WARN_DECLARE]) == ["Autre remarque"]
