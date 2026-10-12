"""
« Partir de vos anciens dossiers » (rédaction, vague 3, chantier I — étude § 6.6).

La TPE importe ses anciens mémoires, sa plaquette et ses attestations dans « Mon savoir-faire » ;
Adjugo PROPOSE des fiches de preuves (références, qualifications, matériel, chiffres clés), chacune
avec le PASSAGE EXACT où il l'a trouvée ; l'utilisateur COCHE ce qu'il garde. Les fiches cochées
deviennent des preuves « trouvé dans vos documents » du socle (app/services/preuves.py, seul point
d'écriture de la table `preuves`). Contrat : docs/REDACTION_V3_IMPORT.md.

Doctrine (étude § 7) appliquée ici :
  1. Un fait ne vient JAMAIS de l'IA. L'IA propose ; tout le reste est fait SANS IA :
       • le passage doit être retrouvé tel quel dans le texte du document (même tolérance que
         citation_guard : casse, accents, espaces, apostrophes) — sinon la proposition est écartée ;
       • chaque champ ne dit rien de plus que son passage : chaque chiffre, année, nom propre,
         certification et matériel y figure (pv.elements_hors_passage), et chaque mot porteur de
         sens des champs écrits y figure aussi (une reformulation de l'IA n'est jamais gardée) ;
         un champ facultatif qui en dit plus est retiré, un champ obligatoire qui en dit plus
         écarte la fiche ;
       • le rôle (seul, en groupement…), la possession (en propre, en location), un montant HT et
         une date de fin de validité ne sont gardés que si le passage les écrit ;
       • rien n'est accepté sans l'utilisateur : chaque fiche est « proposée », à cocher.
  2. Qui affirme quoi : un passage qui rapporte ce qu'un acheteur, un CCTP ou un règlement demande
     n'appuie jamais une fiche sur l'entreprise (écarté) ; un document qui est une pièce du dossier
     d'un acheteur (règlement, CCAP, CCTP) n'est pas lu.
  3. On ne dit jamais « vérifié » : on dit où on a trouvé le fait.
  9. CV et noms des salariés jamais envoyés à l'IA : un document qui ressemble à un CV n'est jamais
     lu ; les passages d'un document qui ressemblent à un CV sont retirés avant l'envoi ; les noms
     connus (profil, fiches « Équipe ») ET les noms de personnes repérés dans le document (« M.
     Kerjean », « Conducteur de travaux : Anne Le Floch ») sont remplacés par des étiquettes avant
     l'appel (pii_scope), puis remis en clair sans IA. Aucune fiche « Équipe » n'est proposée par
     l'IA : elles se saisissent dans « Mes preuves ».

Coût (règle d'Eliot : économiser l'IA sans jamais baisser la qualité) : une lecture par document,
résultats gardés (relancer sur le même document ne rappelle pas l'IA) ; seuls les paragraphes qui
portent un fait (un chiffre, un nom propre, une certification, du matériel, ou un mot comme
« référence », « client », « matériel », « qualification ») partent à l'IA — un paragraphe sans
aucun de ces éléments ne peut donner aucune fiche ; tâche de fond, espace facturé (tenant_scope),
budget de l'essai vérifié avant, gratuit jusqu'à FICHES_DOCUMENTS_PAR_MOIS documents par mois et par
organisation (défaut 20, réglable) ; si l'IA tombe, rien n'est proposé et la lecture n'est pas
comptée (elle est rendue).
"""
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Optional

from app.models import Job, KnowledgeDoc, Preuve, User
from app.services import preuves as pv

logger = logging.getLogger("adjugo")

TACHE = "fiches_preuves"            # route de l'IA (app/services/llm.py, _TABLE)
JOB_KIND = "fiches_preuves"         # tâche de fond (table jobs)
JOB_KINDS = (JOB_KIND,)
OPERATION = "fiches"                # budget de l'essai (app/services/budget_ia.py, ENVELOPPES)

NATURES_IA = (pv.REFERENCE, pv.QUALIFICATION, pv.MATERIEL, pv.CHIFFRE_CLE)   # jamais « Équipe »
SEGMENT_MAX = 60_000                # caractères envoyés par appel (paragraphes entiers)
SEGMENT_MIN_COUPE = 8_000           # en dessous, une réponse coupée n'est plus redécoupée
COUPES_MAX = 2                      # une partie trop dense est relue en deux, au plus deux fois
SORTIE_MAX = 8_000                  # tokens de sortie par appel
FICHES_PAR_APPEL = 40
FICHES_PAR_DOCUMENT = 120
PARALLELE = 3

# Statuts d'un document pour l'écran.
A_LIRE, EN_COURS, LU, ECHEC = "a_lire", "en_cours", "lu", "echec"
DOC_CV, DOC_ACHETEUR, DOC_VIDE = "cv", "piece_acheteur", "rien_a_lire"

MSG_CV = ("Ce document ressemble à un CV : Adjugo ne l'envoie jamais à l'IA. Les fiches « Équipe » se "
          "saisissent à la main dans « Mes preuves ».")
MSG_ACHETEUR = ("Ce document ressemble à une pièce du dossier d'un acheteur (règlement, CCAP, CCTP) : il dit "
                "ce que l'acheteur demande, pas ce que fait votre entreprise. Adjugo n'en tire aucune fiche.")
MSG_VIDE = ("Adjugo ne trouve dans ce document aucun chiffre, nom, certification ni matériel : il n'y a rien "
            "à proposer.")
MSG_PANNE = ("L'IA n'a pas pu lire ce document : rien n'a été proposé et cette lecture n'est pas comptée. "
             "Réessayez dans quelques minutes.")
MSG_INTROUVABLE = "Document introuvable dans « Mon savoir-faire »."
MSG_EMAIL = "Confirmez votre adresse email pour utiliser cette fonctionnalité."

# Pourquoi une proposition a été écartée (affiché en résumé, sans IA).
ECARTS = {
    "passage_introuvable": "passage non retrouvé tel quel dans le document",
    "valeur_hors_passage": "fiche qui disait plus que son passage",
    "exigence_acheteur": "passage qui rapporte une exigence d'un acheteur",
    "equipe": "fiche sur une personne (les fiches « Équipe » se saisissent à la main)",
    "incomplete": "fiche incomplète",
    "passage_trop_long": "passage trop long",
    "trop_de_fiches": "trop de fiches pour un seul document",
}


class ImportError_(Exception):
    """Erreur métier affichable telle quelle (status HTTP, code stable, message)."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def detail(self) -> dict:
        return dict(self.extra, code=self.code, message=self.message)


# ── Réglages ────────────────────────────────────────────────────────────────────────────

def plafond_mensuel() -> int:
    """Documents lus gratuitement par mois et par organisation (FICHES_DOCUMENTS_PAR_MOIS, défaut 20 ;
    0 : fonction en pause)."""
    try:
        return max(0, int(os.getenv("FICHES_DOCUMENTS_PAR_MOIS", "20")))
    except ValueError:
        return 20


def _debut_du_mois() -> datetime:
    """Premier jour du mois en cours (UTC, sans fuseau : format des dates en base), comme le quota."""
    n = datetime.now(timezone.utc)
    return datetime(n.year, n.month, 1)


# ── Le document : à lire, CV, pièce d'un acheteur ───────────────────────────────────────

def _fold(s) -> str:
    from app.services.faits_a_relire import fold
    return fold(s)


_NOM_CV = re.compile(r"(?:^|[^a-z0-9])(?:cv|c v|curriculum(?: vitae)?)(?:$|[^a-z0-9])")
_TITRE_CV = re.compile(r"^\s*(?:curriculum\s+vitae|c\.?\s?v\.?)\s*(?:$|[:\-–—]|\s+(?:de|du)\s)", re.IGNORECASE)
# Marques d'un CV : fortes (propres à un CV) et faibles (coordonnées, rubriques). Les coordonnées de
# l'entreprise dans une plaquette (téléphone, courriel) ne suffisent jamais à faire un CV.
_CV_FORTS = [re.compile(p) for p in (
    r"curriculum vitae", r"date de naissance", r"\bnee? le \d", r"\bnee? en (?:19|20)\d\d", r"nationalite",
    r"situation familiale", r"\bcelibataire\b", r"\bmarie(?:e)?,? \d+ enfants?", r"\bpermis [abc]\b",
    r"experiences? professionnelles?", r"parcours professionnel", r"centres? d'interets?", r"\bloisirs\b",
    r"\bage ?: ?\d", r"\b\d{2} ans\b,? (?:marie|celibataire)")]
_CV_FAIBLES = [re.compile(p) for p in (
    r"(?<!\d)0[1-9](?:[ .]?\d{2}){4}(?!\d)|[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}",
    r"\bformations? ?:", r"\blangues? ?:", r"\bcompetences ?:", r"\bdiplomes? ?:")]


def _bloc_cv(bloc: str) -> bool:
    """Un passage qui ressemble à un CV : titré « CV » / « Curriculum vitae », deux marques propres à
    un CV (date de naissance, situation familiale, expérience professionnelle, loisirs…), ou une
    marque propre et deux rubriques ou coordonnées."""
    low = _fold(bloc)
    if _TITRE_CV.match(bloc or "") or "curriculum vitae" in low:
        return True
    forts = sum(1 for rx in _CV_FORTS if rx.search(low))
    faibles = sum(1 for rx in _CV_FAIBLES if rx.search(low))
    return forts >= 2 or (forts >= 1 and faibles >= 2)


def _blocs(texte: str) -> list:
    """Paragraphes du document (lignes vides), un long paragraphe sans ligne vide étant regroupé par
    lignes en blocs de 1 500 caractères environ. Chaque bloc est un morceau CONTIGU du texte."""
    out = []
    for para in re.split(r"\n[ \t]*\n+", str(texte or "")):
        if not para.strip():
            continue
        if len(para) <= 2500:
            out.append(para)
            continue
        cur = []
        n = 0
        for ligne in para.split("\n"):
            while len(ligne) > 2500:                      # ligne interminable (PDF sans retours)
                coupe = ligne.rfind(" ", 0, 1500)
                coupe = coupe if coupe > 500 else 1500
                if cur:
                    out.append("\n".join(cur))
                    cur, n = [], 0
                out.append(ligne[:coupe])
                ligne = ligne[coupe:].lstrip()
            cur.append(ligne)
            n += len(ligne) + 1
            if n >= 1500:
                out.append("\n".join(cur))
                cur, n = [], 0
        if cur:
            out.append("\n".join(cur))
    return [b for b in out if b.strip()]


def est_cv(doc: KnowledgeDoc) -> bool:
    """Un document qui ressemble à un CV n'est JAMAIS envoyé à l'IA (décision 8) : nom de fichier
    (« CV_Yann_Tanguy.pdf », « Curriculum vitae »), titre en tête, ou texte fait surtout de passages
    de CV."""
    nom = " " + re.sub(r"[^a-z0-9]+", " ", _fold(doc.name or "")) + " "
    if _NOM_CV.search(nom):
        return True
    texte = doc.text or ""
    tete = texte.lstrip()[:200]
    if _TITRE_CV.match(tete) or "curriculum vitae" in _fold(texte[:1500]):
        return True
    blocs = _blocs(texte)
    total = sum(len(b) for b in blocs) or 1
    cv = sum(len(b) for b in blocs if _bloc_cv(b))
    return cv / total >= 0.4


_VOIX_ENTREPRISE = re.compile(r"\b(?:nous|notre|nos)\b")
_NOM_ENTREPRISE = re.compile(r"\b(?:memoire|offre|reponse|candidature|references?|plaquette|presentation)\b")


def est_piece_acheteur(doc: KnowledgeDoc) -> bool:
    """Règlement, CCAP ou CCTP (titre en tête, ou nom en toutes lettres), sans « nous », « notre »
    ni « nos » en première page : le dossier d'un acheteur n'appuie jamais un fait sur l'entreprise.
    Un ancien mémoire (« Mémoire – réponse au CCTP », ou qui parle à la première personne) reste lu."""
    from app.services import dce_pieces as dp
    acheteur = (dp.REGLEMENT, dp.CCAP, dp.CCTP)
    texte = doc.text or ""
    par_nom, sur = dp.classify_name(doc.name or "")
    if dp.classify_head(texte) not in acheteur and not (sur and par_nom in acheteur):
        return False
    if _NOM_ENTREPRISE.search(" " + re.sub(r"[^a-z0-9']+", " ", _fold(doc.name or "")) + " "):
        return False
    return not _VOIX_ENTREPRISE.search(_fold(texte[:dp.HEAD_CHARS]))


_MOTS_UTILES = re.compile(
    r"\b(?:references?|clients?|maitres? d'ouvrage|maitrise d'ouvrage|acheteurs?|realis\w*|livr\w*|"
    r"materiels?|engins?|parc|outillages?|vehicules?|equipements?|qualifi\w*|certifi\w*|labels?|labellis\w*|"
    r"agre\w*|habilit\w*|attestations?|effectifs?|salaries?|compagnons?|chiffre d'affaires|atelier|depot|"
    r"surface|capacite)\b")


def _utile(bloc: str) -> bool:
    """Le bloc peut-il porter un fait (sans IA) ? Un chiffre, une certification, du matériel, un nom
    propre (même repérage que « à relire »), ou un mot qui annonce une référence, un matériel, une
    qualification ou un effectif. Un bloc sans rien de cela ne peut donner aucune fiche : il ne part
    pas à l'IA (économie sans perte)."""
    from app.services import faits_a_relire as far
    if re.search(r"\d", bloc):
        return True
    low = _fold(bloc)
    if far._CERT.search(low) or far._CERT_GENERIQUE.search(low) or far._MATERIEL.search(low) \
            or _MOTS_UTILES.search(low):
        return True
    for ph, _titre, tableau in far.phrases(bloc):
        if any(kind == far.NOM_PROPRE for _f, kind, _k in far._facts_in(ph, tableau=tableau)):
            return True
    return False


def texte_a_lire(doc: KnowledgeDoc) -> dict:
    """Ce qui partira à l'IA (avant masquage des noms) : les blocs utiles, hors passages de CV,
    regroupés en parties de SEGMENT_MAX caractères au plus (paragraphes entiers).
    → {"parties": [str], "caracteres": int, "caracteres_document": int, "blocs_cv": int}."""
    blocs = _blocs(doc.text or "")
    garde, n_cv = [], 0
    for b in blocs:
        if _bloc_cv(b):
            n_cv += 1
            continue
        if _utile(b):
            garde.append(b.strip("\n"))
    parties, cur, n = [], [], 0
    for b in garde:
        if cur and n + len(b) + 2 > SEGMENT_MAX:
            parties.append("\n\n".join(cur))
            cur, n = [], 0
        cur.append(b)
        n += len(b) + 2
    if cur:
        parties.append("\n\n".join(cur))
    return {"parties": parties, "caracteres": sum(len(p) for p in parties),
            "caracteres_document": len(doc.text or ""), "blocs_cv": n_cv}


_CACHE_STATUT = {}          # (id, longueur, empreinte) → statut : le texte d'un document ne change jamais
_CACHE_MAX = 2000


def statut_document(doc: KnowledgeDoc) -> Optional[str]:
    """DOC_CV, DOC_ACHETEUR, DOC_VIDE, ou None (lisible). Mémorisé : le texte d'un document de « Mon
    savoir-faire » ne change jamais après son import."""
    t = doc.text or ""
    cle = (doc.id, len(t), hash(t[:2000]), hash(doc.name or ""))
    if cle in _CACHE_STATUT:
        return _CACHE_STATUT[cle]
    if est_cv(doc):
        st = DOC_CV
    elif est_piece_acheteur(doc):
        st = DOC_ACHETEUR
    elif not texte_a_lire(doc)["parties"]:
        st = DOC_VIDE
    else:
        st = None
    if len(_CACHE_STATUT) >= _CACHE_MAX:
        _CACHE_STATUT.pop(next(iter(_CACHE_STATUT)), None)
    _CACHE_STATUT[cle] = st
    return st


_MSG_STATUT = {DOC_CV: MSG_CV, DOC_ACHETEUR: MSG_ACHETEUR, DOC_VIDE: MSG_VIDE}

# ── Date du document (suggestion, SANS IA, que l'utilisateur confirme) ─────────────────

_MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
         "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
_DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-]((?:19|20)\d\d)(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)((?:19|20)\d\d)-(\d{2})-(\d{2})(?!\d)")
_DATE_MOIS = re.compile(r"\b(?:(1er|\d{1,2}) )?(" + "|".join(_MOIS) + r") ((?:19|20)\d\d)(?!\d)")
_ANNEE = re.compile(r"(?<!\d)((?:199|20\d)\d)(?!\d)")


def _dates_ecrites(texte: str) -> list:
    """Dates écrites dans un texte (« 12/03/2021 », « 2021-03-12 », « 12 mars 2021 », « mars 2021 »)."""
    low = _fold(texte)
    out = []
    for m in _DATE_NUM.finditer(low):
        out.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for m in _DATE_ISO.finditer(low):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _DATE_MOIS.finditer(low):
        j = 1 if not m.group(1) or m.group(1) == "1er" else int(m.group(1))
        out.append((int(m.group(3)), _MOIS[m.group(2)], j))
    dates = []
    for a, mo, j in out:
        try:
            dates.append(date(a, mo, j))
        except ValueError:
            continue
    return dates


def date_suggeree(doc: KnowledgeDoc, jour: Optional[date] = None) -> Optional[str]:
    """La date la plus récente écrite en première page (et pas dans le futur), sinon le 1er janvier
    de l'année la plus récente écrite en première page ; None si rien. Une suggestion : c'est
    l'utilisateur qui la confirme ou la corrige avant la lecture."""
    jour = jour or pv.aujourd_hui()
    tete = (doc.text or "")[:4000]
    dates = [d for d in _dates_ecrites(tete) if date(1990, 1, 1) <= d <= jour]
    if dates:
        return max(dates).isoformat()
    annees = [int(a) for a in _ANNEE.findall(tete) if 1990 <= int(a) <= jour.year]
    return date(max(annees), 1, 1).isoformat() if annees else None


def _date_dans(d: date, passage: str) -> bool:
    return d in _dates_ecrites(passage)


# ── Noms de personnes repérés dans le document (masqués avant l'IA, en plus de l'équipe) ─────

_PRENOM_NOM = (r"[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][a-zà-öø-ÿ]+(?:-[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][a-zà-öø-ÿ]+)?"
               r"(?:\s+(?:[Ll]e|[Ll]a|[Dd]e|[Dd]u|[Dd]')?\s?[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-Za-zà-öø-ÿÀ-Ý'’\-]+){1,2}")
_CIVILITE = re.compile(r"(?<![\w])(?:M\.|Mme|Mlle|Monsieur|Madame|Mademoiselle)\s+((?:[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]"
                       r"[A-Za-zà-öø-ÿÀ-Ý'’\-]+)(?:\s+(?:[Ll]e |[Ll]a |[Dd]e |[Dd]u |[Dd]')?[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]"
                       r"[A-Za-zà-öø-ÿÀ-Ý'’\-]+){0,2})")
_FONCTION = (r"(?:chef(?:fe)? de (?:chantier|projet|travaux|chantiers)|chef(?:fe)? d['’]équipe|"
             r"conduct(?:eur|rice) de travaux|compagnon|ouvri(?:er|ère)|charpentier|couvreur|maçon|plombier|"
             r"électricien|menuisier|peintre|technicien(?:ne)?|ingénieur(?:e)?|gérant(?:e)?|dirigeant(?:e)?|"
             r"président(?:e)?|directeur|directrice|responsable [a-zéèêà ]{3,30}|apprenti(?:e)?|"
             r"assistant(?:e)?|comptable|secrétaire|encadrant(?:e)?|référent(?:e)?)")
_NOM_PUIS_FONCTION = re.compile(r"(?<![\w’'])(" + _PRENOM_NOM + r")\s*(?:,|\(|–|—|-|:)\s*(?i:" + _FONCTION + ")")
_FONCTION_PUIS_NOM = re.compile(r"(?i:" + _FONCTION + r")\s*(?::|–|—|-|,)\s*(?:M\.\s|Mme\s)?(" + _PRENOM_NOM
                                + r")(?![\w])")
_PAR_NOM = re.compile(r"(?i:sous la (?:conduite|direction|responsabilit[ée]) d[e']|encadr[ée]e?s? par|dirig[ée]e?s? par|"
                      r"suivie?s? par|pilot[ée]e?s? par|men[ée]e?s? par|coordonn[ée]e?s? par)\s*(" + _PRENOM_NOM
                      + r")(?![\w])")
_PAS_UN_NOM = {"mairie", "ville", "commune", "departement", "region", "conseil", "societe", "sarl", "sas", "eurl",
               "ecole", "college", "lycee", "centre", "office", "habitat", "agence", "groupe", "entreprise",
               "communaute", "metropole", "syndicat", "chantier", "projet", "travaux", "service", "direction",
               "batiment", "residence", "salle", "rue", "avenue", "place", "le", "la", "les", "nous", "notre"}


def noms_probables(texte: str) -> list:
    """Noms de personnes écrits dans le document, sans IA : après une civilité (« M. Kerjean »,
    « Mme Anne Le Floch »), accolés à une fonction (« Yann Tanguy, conducteur de travaux »,
    « Chef de chantier : Paul Durand »), ou après « sous la conduite de », « dirigé par »… Ils sont
    masqués comme ceux de l'équipe (pii_scope)."""
    t = str(texte or "")
    vus, out = set(), []

    def _ajoute(n):
        n = re.sub(r"\s+", " ", n).strip(" ,;:-–—'’")
        mots = [w for w in re.split(r"[\s\-’']+", _fold(n)) if w]
        if not mots or any(w in _PAS_UN_NOM for w in mots[:1]) or len(n) < 3 or len(n) > 80:
            return
        k = _fold(n)
        if k not in vus:
            vus.add(k)
            out.append(n)

    for m in _CIVILITE.finditer(t):
        _ajoute(m.group(1))
    for rx in (_NOM_PUIS_FONCTION, _FONCTION_PUIS_NOM, _PAR_NOM):
        for m in rx.finditer(t):
            _ajoute(m.group(1))
    return out[:300]


def pseudonymiseur(db, owner_id: int, parties: list):
    """Noms connus (profil, fiches « Équipe ») + noms repérés dans ce qui part à l'IA."""
    from app.services.pii import from_team, team_of_users
    equipe = team_of_users(db, [owner_id])
    connus = {_fold(m.get("nom")) for m in equipe if isinstance(m, dict)}
    for n in noms_probables("\n\n".join(parties)):
        if _fold(n) not in connus:
            equipe.append({"nom": n, "fonction": "Personne"})
            connus.add(_fold(n))
    return from_team(equipe)


# ── L'appel à l'IA ────────────────────────────────────────────────────────────────────────

CONSIGNES = """Tu aides une petite entreprise du bâtiment à retrouver, dans SES PROPRES anciens documents \
(mémoires techniques, plaquette, attestations), les faits qu'elle pourra citer dans ses prochaines réponses aux \
marchés publics. Tu PROPOSES des fiches ; l'entreprise cochera celles qui sont justes.

Règles absolues :
1. Tu n'inventes rien. Chaque fiche recopie un PASSAGE du document, mot pour mot, sans rien changer (ni \
ponctuation, ni majuscules), sans points de suspension, en un seul morceau continu : une à trois phrases, ou une \
ligne de tableau, 500 caractères au plus.
2. Les champs de la fiche ne contiennent QUE des mots, des chiffres et des noms écrits dans ce passage : recopie \
les mots du passage, ne reformule pas. Un champ que le passage ne dit pas reste absent. Ne déduis jamais une \
année, un montant, un client, un rôle ou une date.
3. Seulement des faits sur l'entreprise elle-même : ce qu'elle a réalisé, ses qualifications, son matériel, ses \
chiffres. Jamais ce qu'un acheteur, un CCTP ou un règlement demande ou prévoit.
4. Aucune fiche sur une personne : ni nom de salarié, ni CV, ni expérience individuelle. Les étiquettes entre \
crochets (par exemple « [Chef de chantier 1] » ou « [Nom 1] ») restent telles quelles.
5. Pas de doublon : un même fait, une seule fiche.

Types de fiches et champs (noms exacts) :
- "reference" (un chantier ou un marché réalisé) : objet (obligatoire), acheteur, lieu, annee (nombre), \
montant_ht (nombre en euros, seulement si le passage dit HT ou ne précise pas ; si le passage dit TTC, pas de \
montant), role ("seul", "groupement_conjoint", "groupement_solidaire" ou "sous_traitant", seulement si le passage \
le dit), description.
- "qualification" (qualification, certification, label, agrément) : nom (obligatoire, par exemple « Qualibat \
3194 »), organisme, numero, detail ; et "date_fin_validite" (AAAA-MM-JJ) à côté des champs, seulement si la date \
de fin est écrite dans le passage.
- "materiel" : designation (obligatoire), quantite (nombre entier), caracteristiques, possession ("propriete" \
ou "location", seulement si le passage le dit).
- "chiffre_cle" (effectif, chiffre d'affaires, surface d'atelier…) : libelle (obligatoire), valeur (nombre), \
unite, annee.

Réponds UNIQUEMENT par un objet JSON :
{"fiches": [{"nature": "reference", "champs": {"objet": "…", "acheteur": "…", "annee": 2024}, "passage": "…"}]}
""" + f"{FICHES_PAR_APPEL} fiches au plus. S'il n'y a rien à proposer : " + '{"fiches": []}.'


def _appel(partie: str, rang: int, total: int, profondeur: int = 0) -> list:
    """Une partie du document → propositions brutes de l'IA. Réponse coupée (partie trop dense) :
    la partie est relue en deux moitiés (paragraphes entiers), au plus COUPES_MAX fois. Une réponse
    illisible lève une erreur (rien n'est proposé, la lecture est rendue)."""
    from app.services import llm
    resp = llm.messages_create(
        tache=TACHE, json_attendu=True, max_tokens=SORTIE_MAX, system=CONSIGNES,
        messages=[{"role": "user", "content": f"Document à lire (partie {rang} sur {total}) :\n<<<\n{partie}\n>>>"}])
    texte = (resp.content[0].text if getattr(resp, "content", None) else "") or ""
    if getattr(resp, "stop_reason", "") == "max_tokens" and profondeur < COUPES_MAX \
            and len(partie) >= SEGMENT_MIN_COUPE:
        a, b = _moities(partie)
        if a and b:
            return _appel(a, rang, total, profondeur + 1) + _appel(b, rang, total, profondeur + 1)
    data = llm.parse_json(texte)
    fiches = data.get("fiches") if isinstance(data, dict) else None
    if not isinstance(fiches, list):
        raise ValueError("réponse sans liste de fiches")
    return [f for f in fiches if isinstance(f, dict)][:FICHES_PAR_APPEL]


def _moities(partie: str) -> tuple:
    blocs = partie.split("\n\n")
    if len(blocs) < 2:
        milieu = partie.rfind("\n", 0, len(partie) // 2)
        if milieu <= 0:
            milieu = len(partie) // 2
        return partie[:milieu], partie[milieu:]
    total, acc = len(partie), 0
    for i, b in enumerate(blocs):
        acc += len(b) + 2
        if acc >= total / 2:
            return "\n\n".join(blocs[:i + 1]), "\n\n".join(blocs[i + 1:])
    return "\n\n".join(blocs[:-1]), blocs[-1]


# ── Les propositions, contrôlées SANS IA ─────────────────────────────────────────────────

_MOTS_VIDES = {
    "dans", "pour", "avec", "sans", "sous", "vers", "chez", "entre", "depuis", "pendant", "selon", "leur", "leurs",
    "notre", "votre", "nous", "vous", "elle", "elles", "sont", "etre", "avoir", "fait", "faite", "faits", "faites",
    "tout", "tous", "toute", "toutes", "cette", "celle", "ceux", "celui", "dont", "ainsi", "plus", "moins", "tres",
    "aussi", "comme", "mais", "donc", "puis", "lors", "afin", "avant", "apres", "deux", "trois", "quatre", "cinq",
    "annee", "annees", "montant", "acheteur", "client", "lieu", "objet", "role", "description", "realise",
    "realisee", "realises", "realisees", "travaux", "chantier", "chantiers", "marche", "marches", "pour", "une",
    "des", "les", "aux", "par", "sur",
}
_TXT = ("objet", "description", "designation", "caracteristiques", "detail", "libelle", "unite", "acheteur", "lieu",
        "nom", "organisme", "numero")


def _racine(mot: str) -> str:
    return mot[:5] if len(mot) > 5 else mot


def mots_hors_passage(valeur_txt: str, passage: str) -> list:
    """Mots porteurs de sens d'un champ écrit qui n'apparaissent pas dans le passage (repliés, à la
    racine près : « réalisée » / « réalisé », « toitures » / « toiture »). Une reformulation de l'IA
    (« rénovation » pour « réfection ») n'est jamais gardée."""
    mots_p = set()
    for w in re.findall(r"[a-z0-9]+", _fold(passage)):
        mots_p.add(w)
        mots_p.add(_racine(w))
    out = []
    for w in re.findall(r"[a-z]+", _fold(valeur_txt)):
        if len(w) < 4 or w in _MOTS_VIDES:
            continue
        if w not in mots_p and _racine(w) not in mots_p:
            out.append(w)
    return out


_ROLE_MOTS = {"seul": r"\bseule?s?\b|\ben propre\b|\btitulaire unique\b", "groupement_conjoint": r"\bconjoint",
              "groupement_solidaire": r"\bsolidaire", "sous_traitant": r"\bsous[- ]?trait"}
_POSSESSION_MOTS = {"propriete": r"\bproprie|\ben propre\b|\bnous appartien", "location": r"\blocation|\blou(?:e|es|ee|ees|ons)\b"}


def _champs_propres(nature: str, champs) -> dict:
    """Seulement les champs de la nature (liste fermée du socle), et seulement des valeurs simples."""
    out = {}
    if not isinstance(champs, dict):
        return out
    permis = pv.CHAMPS.get(nature, {})
    for k, v in champs.items():
        if k not in permis or str(k).lower() in pv._CV_INTERDITS:
            continue
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def _parle_de_l_entreprise(passage: str) -> bool:
    """Au moins une phrase du passage parle de l'entreprise (ou d'un fait non attribué) : un
    passage qui ne fait que rapporter ce que demande un acheteur ou une pièce de son dossier
    (« Le CCTP impose une nacelle de 16 m ») n'appuie jamais une fiche sur l'entreprise."""
    from app.services import faits_a_relire as far
    phs = [ph for ph, _t, _tab in far.phrases(passage)]
    return not phs or any(far.parle_entreprise(ph, section_entreprise=True) for ph in phs)


class _Texte:
    """Texte du document, avec sa table de correspondance construite une fois (même recherche que
    pv.localiser : exacte, puis à la casse, aux accents, aux espaces et aux apostrophes près)."""

    def __init__(self, texte: str):
        self.t = str(texte or "")
        self._map = None

    def localiser(self, passage: str):
        from app.services.analysis import _norm_citation, _norm_with_map
        ext = str(passage or "").strip().strip("«»\"“”„ ")
        nx = _norm_citation(ext)
        if len(nx) < pv.PASSAGE_MIN or not self.t:
            return None
        i = self.t.find(ext)
        if i >= 0:
            return i, i + len(ext)
        if self._map is None:
            self._map = _norm_with_map(self.t)
        nt, pos = self._map
        j = nt.find(nx)
        if j < 0 or j + len(nx) - 1 >= len(pos):
            return None
        return pos[j], pos[j + len(nx) - 1] + 1


def controler(nature, champs, passage, texte: "_Texte", date_fin=None) -> tuple:
    """(valeur gardée, passage tel qu'écrit dans le document, date de fin gardée, motif) — sans IA.
    motif None : la fiche peut être proposée ; sinon le code de l'écart (ECARTS)."""
    if nature == pv.SALARIE:
        return None, None, None, "equipe"
    if nature not in NATURES_IA:
        return None, None, None, "incomplete"
    loc = texte.localiser(passage)
    if loc is None:
        return None, None, None, "passage_introuvable"
    ext = texte.t[loc[0]:loc[1]]
    if len(ext) > pv.PASSAGE_MAX:
        return None, None, None, "passage_trop_long"
    if not _parle_de_l_entreprise(ext):
        return None, None, None, "exigence_acheteur"
    low = _fold(ext)
    val = _champs_propres(nature, champs)
    if nature == pv.REFERENCE:
        if "role" in val and not re.search(_ROLE_MOTS.get(str(val["role"]), r"(?!)"), low):
            val.pop("role")
        if "montant_ht" in val and re.search(r"\bttc\b", low) and not re.search(r"\bh\.?t\.?\b|hors tax", low):
            val.pop("montant_ht")                    # un montant TTC n'est jamais présenté comme HT
    if nature == pv.MATERIEL and "possession" in val \
            and not re.search(_POSSESSION_MOTS.get(str(val["possession"]), r"(?!)"), low):
        val.pop("possession")
    for k in list(val):
        v = val[k]
        trop = pv.elements_hors_passage(nature, {k: v}, ext)
        if not trop and isinstance(v, str) and k in _TXT:
            trop = mots_hors_passage(v, ext)
        if trop:
            if k in pv.REQUIS.get(nature, ()):
                return None, None, None, "valeur_hors_passage"
            val.pop(k)
    try:
        val = pv.valider_valeur(nature, val)
    except pv.PreuveError:
        return None, None, None, "incomplete"
    fin = None
    if nature == pv.QUALIFICATION and date_fin:
        try:
            d = date.fromisoformat(str(date_fin)[:10])
            fin = d if _date_dans(d, ext) else None   # une date de fin non écrite n'est jamais gardée
        except ValueError:
            fin = None
    return val, ext, fin, None


# ── État, lancement, exécution ──────────────────────────────────────────────────────────

def _membres(db, owner_id: int) -> list:
    return pv.membres(db, owner_id)


def document(db, owner_id: int, doc_id) -> Optional[KnowledgeDoc]:
    try:
        did = int(doc_id)
    except (TypeError, ValueError):
        return None
    return db.query(KnowledgeDoc).filter(KnowledgeDoc.id == did,
                                         KnowledgeDoc.user_id.in_(_membres(db, owner_id))).first()


def _jobs(db, owner_id: int, depuis: Optional[datetime] = None) -> list:
    q = db.query(Job).filter(Job.kind.in_(JOB_KINDS), Job.user_id.in_(_membres(db, owner_id)))
    if depuis is not None:
        q = q.filter(Job.created_at >= depuis)
    return q.order_by(Job.id.asc()).all()


def _doc_du_job(j: Job) -> Optional[int]:
    r = j.result if isinstance(j.result, dict) else {}
    try:
        return int(r.get("doc_id")) if r.get("doc_id") is not None else None
    except (TypeError, ValueError):
        return None


def lectures_du_mois(db, owner_id: int) -> int:
    """Documents lus ce mois-ci par l'organisation (une lecture tombée en panne est rendue)."""
    return sum(1 for j in _jobs(db, owner_id, _debut_du_mois()) if j.status != "error")


def plafond(db, owner_id: int) -> dict:
    lim = plafond_mensuel()
    n = lectures_du_mois(db, owner_id)
    return {"limite": lim, "utilises": n, "restants": max(0, lim - n)}


def _derniere_lecture(db, owner_id: int, doc_id: int) -> Optional[Job]:
    """La lecture qui compte pour ce document : en cours ou terminée (la plus ancienne), sinon le
    dernier échec."""
    jobs = [j for j in _jobs(db, owner_id) if _doc_du_job(j) == doc_id]
    vivantes = [j for j in jobs if j.status != "error"]
    if vivantes:
        return vivantes[0]
    return jobs[-1] if jobs else None


def _statut_lecture(j: Optional[Job]) -> str:
    if j is None:
        return A_LIRE
    return {"pending": EN_COURS, "running": EN_COURS, "done": LU}.get(j.status, ECHEC)


def fiches_du_document(db, owner_id: int, doc_id: int) -> list:
    return (pv._q_org(db, owner_id).filter(Preuve.source_doc_id == doc_id, Preuve.origine == "import_document")
            .order_by(Preuve.numero.asc()).all())


def _lecture_out(j: Optional[Job]) -> Optional[dict]:
    if j is None:
        return None
    r = j.result if isinstance(j.result, dict) else {}
    st = _statut_lecture(j)
    out = {"statut": st, "job_id": j.id, "date_document": r.get("date_document"),
           "lu_le": pv._iso(j.updated_at) if st == LU else None}
    if st == LU:
        ecarts = {k: int(v) for k, v in (r.get("raisons") or {}).items() if k in ECARTS and v}
        out.update(proposees=int(r.get("proposees") or 0), deja=int(r.get("deja") or 0),
                   ecartees=sum(ecarts.values()),
                   ecarts=[{"code": k, "libelle": ECARTS[k], "nombre": n} for k, n in ecarts.items()])
    if st == ECHEC:
        out["message"] = MSG_PANNE
    return out


def etat_document(db, owner_id: int, doc: KnowledgeDoc) -> dict:
    """Tout ce que l'écran affiche pour un document : statut, lecture, fiches (preuve_out du socle)."""
    j = _derniere_lecture(db, owner_id, doc.id)
    bloque = statut_document(doc) if j is None or j.status == "error" else None
    ps = fiches_du_document(db, owner_id, doc.id)
    etat = pv._Etat(db, owner_id, ps)
    jour = pv.aujourd_hui()
    return {
        "document": {"id": doc.id, "nom": doc.name, "statut": bloque or _statut_lecture(j),
                     "message": _MSG_STATUT.get(bloque) if bloque else None,
                     "date_suggeree": date_suggeree(doc, jour)},
        "lecture": _lecture_out(j),
        "fiches": [pv.preuve_out(db, p, etat, jour) for p in ps],
        "plafond": plafond(db, owner_id),
    }


def etat_documents(db, owner_id: int) -> dict:
    """Résumé par document de l'organisation (pour la liste « Mon savoir-faire »)."""
    from sqlalchemy import func
    docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.user_id.in_(_membres(db, owner_id))).all()
    jobs = _jobs(db, owner_id)
    par_doc = {}
    for j in jobs:
        d = _doc_du_job(j)
        if d is None:
            continue
        cur = par_doc.get(d)
        if cur is None or (cur.status == "error" and j.status != "error") or \
                (cur.status == "error" and j.status == "error" and j.id > cur.id):
            par_doc[d] = j
    comptes = {}
    for doc_id, statut, n in (db.query(Preuve.source_doc_id, Preuve.statut, func.count(Preuve.id))
                              .filter(Preuve.owner_id == owner_id, Preuve.proprietaire_invite_id == 0,
                                      Preuve.origine == "import_document", Preuve.statut != pv.SUPPRIMEE,
                                      Preuve.source_doc_id.isnot(None))
                              .group_by(Preuve.source_doc_id, Preuve.statut).all()):
        comptes.setdefault(doc_id, {})[statut] = int(n)
    out = {}
    for doc in docs:
        j = par_doc.get(doc.id)
        st = _statut_lecture(j)
        if st in (A_LIRE, ECHEC):
            st = statut_document(doc) or st
        c = comptes.get(doc.id, {})
        out[str(doc.id)] = {"statut": st, "a_cocher": c.get(pv.PROPOSEE, 0), "cochees": c.get(pv.ACCEPTEE, 0)}
    return {"documents": out, "plafond": plafond(db, owner_id)}


def _date_document(v) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        d = date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ImportError_(422, "date_invalide", "Date du document attendue au format AAAA-MM-JJ.")
    if d > pv.aujourd_hui() or d < date(1950, 1, 1):
        raise ImportError_(422, "date_invalide", "La date du document ne peut pas être dans le futur.")
    return d


def lancer(db, user: User, owner_id: int, doc_id, date_document=None) -> tuple:
    """« Proposer des fiches à partir de ce document ». → (état du document, lecture lancée ?).
    Une seule lecture par document : déjà lu ou en cours, l'état est rendu sans appeler l'IA.
    Contrôles AVANT tout appel : document de l'organisation, ni CV ni pièce d'un acheteur, adresse
    confirmée, essai terminé ou limite d'usage de l'essai (402), plafond du mois (429)."""
    from app.core.quota import _is_demo
    from app.services import budget_ia
    from app.services.jobs import run_in_thread
    doc = document(db, owner_id, doc_id)
    if doc is None:
        raise ImportError_(404, "document_introuvable", MSG_INTROUVABLE)
    if _is_demo(user):
        from app.core.demo_guard import demo_message
        raise ImportError_(403, "demo", demo_message("proposer des fiches à partir de vos documents"))
    j = _derniere_lecture(db, owner_id, doc.id)
    if j is not None and j.status != "error":
        return etat_document(db, owner_id, doc), False             # une lecture par document
    bloque = statut_document(doc)
    if bloque:
        raise ImportError_(422, "document_" + bloque, _MSG_STATUT[bloque])
    ds = _date_document(date_document)
    if user.email_verified is False:              # adresse pas encore confirmée (comme le quota)
        raise ImportError_(403, "adresse_a_confirmer", MSG_EMAIL)
    lecture = texte_a_lire(doc)
    # Essai : la limite d'usage est vérifiée AVANT (estimation prudente : chaque partie au plus) ;
    # essai terminé sans forfait : 402 (budget_ia.verifier appelle quota.exiger_ia).
    budget_ia.verifier(user, db, OPERATION, budget_ia.estimer(OPERATION, n=len(lecture["parties"])))
    lim = plafond_mensuel()
    if lectures_du_mois(db, owner_id) >= lim:
        raise ImportError_(429, "plafond_atteint", _msg_plafond(lim))
    job = Job(user_id=user.id, kind=JOB_KIND, status="pending",
              label=f"Fiches proposées : « {(doc.name or 'Document')[:200]} »"[:255],
              result={"doc_id": doc.id, "date_document": ds.isoformat() if ds else None})
    db.add(job)
    db.commit()
    db.refresh(job)
    # Deux demandes au même moment : une seule lecture par document, et le plafond tient.
    premiere = _derniere_lecture(db, owner_id, doc.id)
    if (premiere is not None and premiere.id != job.id) or lectures_du_mois(db, owner_id) > lim:
        db.delete(job)
        db.commit()
        if premiere is not None and premiere.id != job.id:
            return etat_document(db, owner_id, doc), False
        raise ImportError_(429, "plafond_atteint", _msg_plafond(lim))
    jid, did, uid = job.id, doc.id, user.id

    def _work(jdb):
        return executer(jdb, jid, owner_id, did, uid, ds)

    def _rien(jdb, j):
        """La lecture est gratuite : rien à rembourser au quota d'analyses. En échec, elle n'est plus
        comptée dans le plafond du mois (elle est rendue) et peut être relancée."""
        return None

    run_in_thread(jid, _work, on_error=_rien, tenant_id=owner_id, error_message=MSG_PANNE)
    return etat_document(db, owner_id, doc), True


def _msg_plafond(lim: int) -> str:
    if lim <= 0:
        return "La proposition de fiches est en pause pour le moment."
    return (f"Vous avez fait lire {lim} documents ce mois-ci, la limite gratuite par organisation. Elle repart "
            "le 1er du mois prochain.")


def executer(db, job_id: int, owner_id: int, doc_id: int, user_id: int, date_source: Optional[date]) -> dict:
    """Dans le fil de la tâche de fond (tenant_scope posé par run_in_thread) : lit le document
    (noms masqués, coût mesuré), puis contrôle chaque proposition SANS IA et l'enregistre comme
    preuve « proposée » (pv.proposer). Une partie illisible fait échouer toute la lecture : rien
    n'est proposé à moitié, et la lecture est rendue."""
    from concurrent.futures import ThreadPoolExecutor
    from app.services.llm import cost_meter, map_in_context, pii_scope
    doc = document(db, owner_id, doc_id)
    if doc is None:
        raise RuntimeError("document introuvable")
    lecture = texte_a_lire(doc)
    parties = lecture["parties"]
    pz = pseudonymiseur(db, owner_id, parties)
    total = len(parties)
    with pii_scope(pz), cost_meter("fiches : lecture d'un document", owner_id) as cm:
        if total <= 1:
            brutes = [_appel(p, i + 1, total) for i, p in enumerate(parties)]
        else:
            with ThreadPoolExecutor(max_workers=min(PARALLELE, total)) as ex:
                brutes = map_in_context(ex, lambda x: _appel(x[1], x[0] + 1, total), list(enumerate(parties)))
    user = db.get(User, user_id)
    texte = _Texte(doc.text or "")
    raisons, proposees, deja = {}, 0, 0
    vues = set()
    n = 0
    for lot in brutes:
        for f in lot:
            n += 1
            if n > FICHES_PAR_DOCUMENT:
                raisons["trop_de_fiches"] = raisons.get("trop_de_fiches", 0) + 1
                continue
            nature = str(f.get("nature") or "").strip().lower()
            champs = f.get("champs") if isinstance(f.get("champs"), dict) else {}
            fin = f.get("date_fin_validite") or champs.get("date_fin_validite")
            val, ext, fin_ok, motif = controler(nature, champs, str(f.get("passage") or ""), texte, fin)
            if motif:
                raisons[motif] = raisons.get(motif, 0) + 1
                continue
            cle = (nature, pv.empreinte_de(nature, val))
            if cle in vues:
                continue
            vues.add(cle)
            try:
                p, creee = pv.proposer(db, owner_id, nature=nature, valeur=val, type_source=pv.DOCUMENTS,
                                       source={"doc_id": doc.id, "passage": ext}, date_source=date_source,
                                       date_fin_validite=fin_ok, origine="import_document", user=user)
            except pv.PreuveError as e:
                db.rollback()
                code = e.code if e.code in ECARTS else ("incomplete" if e.code.startswith("champ") else None)
                if code is None and e.code == "trop_de_preuves":
                    code = "trop_de_fiches"
                raisons[code or "incomplete"] = raisons.get(code or "incomplete", 0) + 1
                continue
            if creee:
                proposees += 1
            else:
                deja += 1
    logger.info("fiches : document %s lu (%s parties, %s/%s caractères envoyés) : %s proposées, %s déjà là, "
                "%s écartées", doc.id, total, lecture["caracteres"], lecture["caracteres_document"], proposees, deja,
                sum(raisons.values()))
    return {"doc_id": doc.id, "doc_nom": doc.name, "date_document": date_source.isoformat() if date_source else None,
            "proposees": proposees, "deja": deja, "raisons": raisons,
            "_lecture": {"parties": total, "caracteres": lecture["caracteres"],
                         "caracteres_document": lecture["caracteres_document"], "blocs_cv": lecture["blocs_cv"],
                         "noms_masques": len(pz.labels) if getattr(pz, "labels", None) else 0},
            "_cout": {"appels": cm.calls, "tokens_entree": cm.input_tokens, "tokens_sortie": cm.output_tokens}}
