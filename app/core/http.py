"""Utilitaires HTTP transverses."""
import re
import unicodedata
from urllib.parse import quote


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """En-tête Content-Disposition robuste.

    Les en-têtes HTTP sont encodés en latin-1 : un nom de fichier contenant « — »
    (tiret cadratin), une apostrophe courbe ou certains accents fait crasher la
    réponse (UnicodeEncodeError). On fournit donc un nom ASCII de repli + un
    `filename*` encodé en UTF-8 (RFC 5987), lu par tous les navigateurs modernes.
    """
    name = (filename or "document").strip() or "document"
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", ascii_name).strip() or "document"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
