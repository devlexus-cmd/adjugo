"""Déprécié — le connecteur Mégalis est désormais une instance du connecteur générique
`AtexoSource` (cf. app/sourcing/sources/atexo.py). Conservé pour rétro-compatibilité."""
from app.sourcing.sources.atexo import MEGALIS, AtexoSource  # noqa: F401

# Alias rétro-compatible : MegalisSource() renvoyait une source Mégalis.
def MegalisSource():
    return MEGALIS
