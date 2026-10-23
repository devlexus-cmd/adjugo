"""
Dates écrites en français dans les sources publiques : pages Atexo (Mégalis, PLACE) et rectificatifs
du BOAMP (lot 1 « Dire juste », chantier Sources, docs/MOTEUR_LOT1.md).

Règles (anti-hallucination) :
- Un mois n'est reconnu que par une TABLE EXPLICITE de ses formes : jamais une coupe à quelques lettres
  (l'ancienne coupe à 4 lettres manquait « Oct. », « Nov. », « Déc. », « Fév. », « Avr. » ; une coupe à
  3 lettres confondrait « juin » et « juillet »). Une forme absente de la table ne donne aucune date.
- Une date sans année n'est jamais complétée ; une date impossible (31 novembre) n'est jamais rendue.
- Les formes réellement observées sur une page publique, et celles seulement construites, sont listées
  dans le contrat (docs/MOTEUR_LOT1.md, § Sources, point 1).
"""
import re
import unicodedata
from datetime import date
from typing import Optional

# Forme écrite (minuscules, sans point final) -> numéro du mois. Avec et sans accent : les plateformes
# n'écrivent pas toutes les accents (« Aout », « Dec »). Aucune forme ambiguë : « juin » ≠ « juil ».
MOIS = {
    "janvier": 1, "janv": 1,
    "février": 2, "fevrier": 2, "févr": 2, "fevr": 2, "fév": 2, "fev": 2,
    "mars": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7, "juill": 7,
    "août": 8, "aout": 8,
    "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "décembre": 12, "decembre": 12, "déc": 12, "dec": 12,
}

# « 7 Déc. 2026 », « 1er novembre 2026 », « lundi 09 novembre 2026 » ; l'année est facultative ici
# pour pouvoir COMPTER les dates sans année (jamais complétées, voir mentions()).
_TEXTUELLE = re.compile(r"(?<![\w])(\d{1,2})(?:er)?\s+([^\W\d_]+)\.?(?:\s+(\d{4}))?(?![\w])", re.UNICODE)
# « 03/11/2026 », « 28/10/2026 » ; « 30/10 » (sans année) est compté, jamais complété.
_NUMERIQUE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def mois(mot) -> int:
    """Numéro du mois d'un mot (« Déc. », « OCT », « février »), 0 si la forme n'est pas dans la table."""
    m = _nfc(str(mot or "")).strip().lower().rstrip(".").strip()
    return MOIS.get(m, 0)


def date_iso(jour, num_mois, annee) -> Optional[str]:
    """« AAAA-MM-JJ » si la date existe au calendrier, sinon None."""
    try:
        return date(int(annee), int(num_mois), int(jour)).isoformat()
    except (TypeError, ValueError):
        return None


def date_textuelle(jour, mot_mois, annee) -> Optional[str]:
    """Une date écrite « 7 », « Déc. », « 2026 » (cases séparées d'une page Atexo)."""
    m = mois(mot_mois)
    if not m or not str(annee or "").strip().isdigit():
        return None
    return date_iso(str(jour).strip(), m, str(annee).strip())


def mentions(texte) -> list:
    """Toutes les dates citées dans un texte, dans l'ordre : liste de (jour, mois, année ou None).
    Un mot qui n'est pas un mois de la table n'est pas une date (« 2 lots 2027 », « 12 rue … »)."""
    t = _nfc(str(texte or ""))
    out = []
    for m in _TEXTUELLE.finditer(t):
        num = mois(m.group(2))
        if num:
            out.append((m.start(), int(m.group(1)), num, int(m.group(3)) if m.group(3) else None))
    for m in _NUMERIQUE.finditer(t):
        j, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= j <= 31:
            out.append((m.start(), j, mo, int(m.group(3)) if m.group(3) else None))
    out.sort(key=lambda x: x[0])
    return [(j, mo, a) for _, j, mo, a in out]


def date_unique(texte) -> Optional[str]:
    """La date d'un texte qui n'en cite qu'UNE (même jour et même mois, répétés ou non), avec son année.
    Plusieurs dates différentes, une date sans année ou impossible : None (jamais de choix au hasard)."""
    ms = mentions(texte)
    jours = {(j, mo) for j, mo, _ in ms}
    if len(jours) != 1:
        return None
    annees = {a for _, _, a in ms}
    if None in annees or len(annees) != 1:
        return None
    (j, mo), a = next(iter(jours)), next(iter(annees))
    return date_iso(j, mo, a)


def derniere_date_textuelle(texte) -> Optional[str]:
    """Date limite d'un bloc de résultat Atexo lu en texte : la DERNIÈRE date « jour mois année » du bloc
    (la date de mise en ligne vient avant la clôture). Si ce dernier groupe n'est pas une date connue,
    rien : on ne se rabat jamais sur une date plus haut dans le bloc (ce serait la date de mise en ligne)."""
    t = _nfc(str(texte or ""))
    groupes = [m for m in _TEXTUELLE.finditer(t) if m.group(3)]
    if not groupes:
        return None
    d = groupes[-1]
    return date_textuelle(d.group(1), d.group(2), d.group(3))
