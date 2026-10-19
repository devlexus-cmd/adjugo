"""
Zones stables de app.html (réorganisation de l'interface, vague 1, point 1.0).

Les tests découpaient app.html entre deux commentaires (« <!-- ░░ ATELIER … » jusqu'à
« <!-- ░░ PIPELINE … »), ou entre deux libellés visibles. Réordonner la page, renommer un libellé
ou déplacer une carte cassait alors tout un module de test, ou pire, découpait en silence une autre
zone. Chaque zone porte maintenant un attribut `data-test="nom"` sur son élément racine :
`zone(HTML, "nom")` rend cet élément entier (balise ouvrante jusqu'à sa balise fermante), où qu'il
soit dans la page. Le contrat (noms, règles) est dans docs/REORGANISATION_V1.md.

Lecture seule, sans dépendance : un simple comptage des balises de même nom, commentaires HTML
ignorés. Un repère absent ou en double fait échouer le test qui le demande, avec un message clair.
"""
import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _masque_commentaires(s: str) -> str:
    """Même longueur, commentaires remplacés par des espaces : les positions restent justes."""
    return _COMMENT.sub(lambda m: " " * len(m.group(0)), s)


def _bornes(src: str, masque: str, debut_attr: int, nom: str):
    debut = masque.rfind("<", 0, debut_attr)
    m = re.match(r"<([a-zA-Z][\w-]*)", masque[debut:])
    assert m, f"repère data-test=\"{nom}\" hors d'une balise"
    tag = m.group(1).lower()
    fin_ouvrante = masque.index(">", debut_attr) + 1
    ouvre = re.compile(r"<" + re.escape(tag) + r"(?=[\s>/])", re.I)
    ferme = re.compile(r"</" + re.escape(tag) + r"\s*>", re.I)
    profondeur, i = 1, fin_ouvrante
    while profondeur:
        mo, mf = ouvre.search(masque, i), ferme.search(masque, i)
        assert mf, f"balise <{tag}> du repère « {nom} » jamais refermée"
        if mo and mo.start() < mf.start():
            profondeur += 1
            i = mo.end()
        else:
            profondeur -= 1
            i = mf.end()
    return debut, i


def zones(src: str, nom: str) -> list:
    """Toutes les zones qui portent `data-test="nom"` (dans l'ordre de la page)."""
    masque = _masque_commentaires(src)
    out = []
    for m in re.finditer(r'\bdata-test="' + re.escape(nom) + r'"', masque):
        a, b = _bornes(src, masque, m.start(), nom)
        out.append(src[a:b])
    return out


def zone(src: str, nom: str) -> str:
    """La zone unique qui porte `data-test="nom"` : son élément racine, de la balise ouvrante à sa
    balise fermante. Échoue si le repère manque ou s'il est posé deux fois."""
    z = zones(src, nom)
    assert z, f"repère data-test=\"{nom}\" introuvable (voir docs/REORGANISATION_V1.md)"
    assert len(z) == 1, f"repère data-test=\"{nom}\" posé {len(z)} fois : un repère est unique"
    return z[0]


def sans_reperes(src: str) -> str:
    """Le même texte sans les attributs data-test : pour les tests qui comparent une balise exacte
    (« <div v-if=… class=… »), indépendamment des repères posés dessus."""
    return re.sub(r' data-test="[a-z0-9-]+"', "", src)


def noms(src: str) -> list:
    """Tous les repères posés, dans l'ordre de la page (commentaires exclus)."""
    return re.findall(r'\bdata-test="([a-z0-9-]+)"', _masque_commentaires(src))
