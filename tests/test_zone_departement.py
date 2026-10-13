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
