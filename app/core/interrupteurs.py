"""
Interrupteurs de fonctions, lus dans l'environnement À CHAQUE APPEL (comme DEMO_PUBLIC) : on
les bascule dans Railway sans toucher au code, et les tests les règlent avec monkeypatch.setenv.

- PROJETS_A_VENIR (défaut 0) : l'écran « Projets à venir », son bloc de l'accueil et sa veille
  automatique (scan des délibérations + courriels). Masqués jusqu'à la vague 1 de l'étude veille :
  l'écran actuel montre des actes anciens d'autres régions classés « Pertinent ». Le code et les
  données restent en place.
- PLACE_ACTIF (défaut 0) : la plateforme PLACE (achats de l'État). Ses conditions d'utilisation
  interdisent la reprise des avis : elle n'est plus interrogée tant que l'AIFE n'a pas donné son
  autorisation écrite (docs/AUTORISATIONS_PLATEFORMES.md).
"""
import os

_OUI = ("1", "true", "yes", "oui", "on")


def _actif(nom: str) -> bool:
    return (os.getenv(nom, "") or "").strip().lower() in _OUI


def projets_a_venir_actif() -> bool:
    return _actif("PROJETS_A_VENIR")


def place_actif() -> bool:
    return _actif("PLACE_ACTIF")
