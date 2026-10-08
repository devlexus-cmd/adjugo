"""Type MIME des fichiers stockés (coffre-fort, pièces de co-traitance, dossier d'AO).

Règle (audit cyber oct. 2026, vague 3) : le Content-Type d'un fichier n'est JAMAIS celui
annoncé par le navigateur qui l'a envoyé. Il est dérivé de l'extension, par une table fixe ;
toute extension absente de la table donne `application/octet-stream`. Ainsi un « x.pdf »
déclaré `text/html` est servi en `application/pdf`, et rien n'est jamais servi en
`text/html` ni en `image/svg+xml` (qui exécuteraient du script dans le navigateur).

Au téléchargement : `X-Content-Type-Options: nosniff` partout, et `Content-Disposition:
attachment` pour tout ce qui n'est ni un PDF ni une image.
"""
import os

from app.core.http import content_disposition

DEFAULT_MIME = "application/octet-stream"

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".zip": "application/zip",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}

# Seuls types qu'un navigateur peut afficher sans risque (pas de script) : affichage
# possible ; tout le reste est forcé en téléchargement.
INLINE_SAFE = frozenset({"application/pdf", "image/png", "image/jpeg"})

# Fichiers produits par le serveur lui-même (sauvegardes, diagnostic) sans extension
# connue : leur type déclaré est conservé s'il est inoffensif.
_SERVER_TYPES = frozenset({"application/gzip", "application/json", "text/plain"})


def _ext(name) -> str:
    return os.path.splitext(str(name or ""))[1].lower()


def mime_for(name) -> str:
    """Type MIME dérivé de l'extension d'un nom ou d'une clé de stockage."""
    return MIME_BY_EXT.get(_ext(name), DEFAULT_MIME)


def storage_content_type(key, declared=None) -> str:
    """Content-Type posé sur l'objet stocké (S3/R2) : dérivé de l'extension de la clé ;
    le type déclaré n'est gardé que pour un fichier serveur sans extension connue et
    s'il fait partie des types inoffensifs."""
    derived = mime_for(key)
    if derived != DEFAULT_MIME:
        return derived
    d = str(declared or "").split(";")[0].strip().lower()
    return d if d in _SERVER_TYPES else DEFAULT_MIME


def is_inline_safe(mime) -> bool:
    return str(mime or "").split(";")[0].strip().lower() in INLINE_SAFE


def download_name(name, key) -> str:
    """Nom proposé au téléchargement : celui du document, avec l'extension RÉELLE du fichier
    (un document renommé « facture.html » se télécharge en « facture.html.pdf »)."""
    n = os.path.basename(str(name or "").strip()) or "document"
    ext = _ext(key)
    if ext and _ext(n) != ext:
        n += ext
    return n


def file_headers(name, key, inline: bool = False) -> dict:
    """En-têtes de téléchargement : nosniff toujours ; `attachment` sauf PDF/image demandé
    en affichage."""
    disp = "inline" if (inline and is_inline_safe(mime_for(key))) else "attachment"
    return {"Content-Disposition": content_disposition(download_name(name, key), disp),
            "X-Content-Type-Options": "nosniff"}
