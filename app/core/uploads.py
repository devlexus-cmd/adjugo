"""Lecture BORNÉE des fichiers téléversés (helper unique pour toutes les routes d'upload).

Pourquoi : `await file.read()` / `file.file.read()` matérialisent TOUT le corps envoyé en
mémoire avant le contrôle de taille. Sur le process unique (1 worker sans Redis), un
corps de plusieurs Go suffit à faire tomber l'API pour tous les clients. Ici on ne lit
jamais plus que la limite + 1 octet : au-delà, c'est un 413 immédiat.

Même patron que `invites._read_upload` (lecture `read(MAX + 1)`), factorisé.
"""
from fastapi import HTTPException, UploadFile

MB = 1024 * 1024
# Plafond des imports de dossier (DCE, base de connaissances, délibérations) : un vrai DCE
# zippé (RC + CCAP + CCTP + DPGF + plans) tient largement sous 50 Mo.
DOSSIER_MAX_BYTES = 50 * MB


def _check(content: bytes, max_bytes: int) -> bytes:
    if not content:
        raise HTTPException(400, "Fichier vide.")
    if len(content) > max_bytes:
        raise HTTPException(413, f"Fichier trop volumineux ({max_bytes // MB} Mo max).")
    return content


def read_upload_limited(file: UploadFile, max_bytes: int = DOSSIER_MAX_BYTES) -> bytes:
    """Version SYNCHRONE (routes `def`) : lit au plus `max_bytes + 1` octets.
    400 si vide, 413 si la limite est dépassée — sans jamais charger le surplus."""
    return _check(file.file.read(max_bytes + 1), max_bytes)


async def aread_upload_limited(file: UploadFile, max_bytes: int = DOSSIER_MAX_BYTES) -> bytes:
    """Version ASYNCHRONE (routes `async def`) : même borne, lecture déportée hors de la
    boucle d'événements par Starlette quand le fichier a basculé sur disque."""
    return _check(await file.read(max_bytes + 1), max_bytes)
