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
     lu ; les passages de CV (une section « CV » d'un ancien mémoire, une date de naissance…) et, sous
     un titre « Moyens humains », « Équipe », « Encadrement »…, les lignes de tableau et les lignes qui
     nomment une personne sont retirés avant l'envoi (`lignes_privees`) ; les noms connus (profil,
     fiches « Équipe ») ET les noms de personnes repérés dans le document (« M. Kerjean »,
     « Conducteur de travaux : Anne Le Floch », une case de tableau, « Encadrement : X et Y ») sont
     remplacés par des étiquettes avant l'appel (pii_scope), puis remis en clair sans IA. Aucune fiche
     « Équipe » n'est proposée par l'IA : elles se saisissent dans « Mes preuves ». Sur les AUTRES
     chemins vers l'IA (rédaction, questionnaire), `sans_cv` écarte les extraits de CV et
     `equipe_avec_noms_reperes` masque les mêmes noms.

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
import threading
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
SEGMENT_MIN_COUPE = 8_000           # en dessous, une réponse coupée n'est plus relue
COUPES_MAX = 2                      # une partie trop dense est relue au plus deux fois
APPELS_PAR_PARTIE = 1 + COUPES_MAX  # appels au plus pour UNE partie (estimation du budget de l'essai)
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
    "equipe": "fiche sur une personne (les fiches\u00a0« Équipe\u00a0» se saisissent à la main)",
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


# Marques qui suffisent SEULES : une date de naissance, une nationalité ou une situation familiale ne
# s'écrivent que dans un CV (jamais dans une plaquette ni dans un mémoire).
_CV_SEULS = [re.compile(p) for p in (
    r"date de naissance", r"\bnee? le \d", r"\bnee? le (?:1er|\d{1,2}) [a-z]+ (?:19|20)\d\d", r"nationalite",
    r"situation familiale", r"\bmarie(?:e)?,? \d+ enfants?", r"\bcelibataire\b")]


def _bloc_cv(bloc: str) -> bool:
    """Un passage qui ressemble à un CV : titré « CV » / « Curriculum vitae », une marque qui suffit seule
    (date de naissance, nationalité, situation familiale), deux marques propres à un CV (expérience
    professionnelle, loisirs, permis…), ou une marque propre et deux rubriques ou coordonnées."""
    low = _fold(bloc)
    if _TITRE_CV.match(bloc or "") or "curriculum vitae" in low:
        return True
    if any(rx.search(low) for rx in _CV_SEULS):
        return True
    forts = sum(1 for rx in _CV_FORTS if rx.search(low))
    faibles = sum(1 for rx in _CV_FAIBLES if rx.search(low))
    return forts >= 2 or (forts >= 1 and faibles >= 2)


# ── Sections d'un document : CV en annexe, moyens humains (jamais envoyés à l'IA) ────────────────

_TITRE_SECTION_CV = re.compile(r"(?:^|[^a-z0-9])(?:cv|c\.v\.|curriculum(?: vitae)?)(?:$|[^a-z0-9])")
_RUBRIQUE_CV = re.compile(r"^(?:experiences?|parcours|formations?|diplomes?|competences|langues?|loisirs|"
                          r"centres? d'interets?|permis|habilitations?|qualifications?|references? "
                          r"(?:professionnelles|personnelles)|etat civil|coordonnees|profil)\b")
_TITRE_RH = re.compile(r"\b(?:moyens humains|ressources humaines|equipes?|encadrement|organigramme|personnel|"
                       r"effectifs?|composition de l'equipe|intervenants|nos collaborateurs)\b")
_SECTION_CV_MAX = 80               # lignes au plus dans une section de CV (sans titre de fin repéré)


def _titre(ligne: str) -> bool:
    """Une ligne qui ressemble à un titre : courte, sans ponctuation finale, sans « | »."""
    t = (ligne or "").strip()
    if not (3 <= len(t) <= 90) or t.startswith("|") or re.search(r"[.;,!?]$", t):
        return False
    if len(t.split()) > 12 or not re.search(r"[A-Za-zÀ-ÿ]", t):
        return False
    return bool(re.match(r"^(?:[#*\-•]+\s*)?(?:\d+(?:\.\d+)*[.)]?\s+)?[A-ZÀ-Ý0-9«]", t))


def _ligne_nom(ligne: str) -> bool:
    """Une ligne qui n'est qu'un nom de personne (« Yann Tanguy », « Anne LE FLOCH »)."""
    t = re.sub(r"^[#*\-•\s]+", "", (ligne or "").strip()).strip(" :")
    m = re.fullmatch(_PRENOM_NOM_LIGNE, t)
    return bool(m) and _fold(t.split()[0]) not in _PAS_UN_NOM


def _a_un_nom(ligne: str) -> bool:
    """La ligne contient-elle un nom de personne probable (deux mots à majuscule — « Jean-Yves Le Goff »,
    « Soizic Le Bris » —, hors mots d'ouverture et noms d'organismes) ?"""
    from app.services.faits_a_relire import _OUVERTURE
    if noms_probables(ligne):
        return True
    for m in re.finditer(r"(?<![\w’'])(" + _PRENOM_NOM + r")(?![\w])", ligne or ""):
        premier = _fold(re.split(r"[\s\-]", m.group(1))[0])
        if premier not in _PAS_UN_NOM and premier not in _OUVERTURE:
            return True
    return False


# Un titre qui OUVRE une autre partie du document (fin d'une section de CV ou « équipe ») : numéroté,
# « Annexe… », en capitales, ou une rubrique d'un mémoire. Un nom, une fonction ou une rubrique de CV
# n'en est pas un.
_TITRE_MEMOIRE = re.compile(r"\b(?:moyens? materiels?|materiels?|methodolog\w*|references?|qualite|securite|"
                            r"environnement|planning|organisation|presentation|attestations?|annexes?|"
                            r"chantiers? realises?|realisations?|prix|delais?|garanties?|sommaire|"
                            r"memoire technique|offre|propositions?|approvisionnement|dechets|nos moyens)\b")


def _fin_de_section(t: str) -> bool:
    low = _fold(t)
    if re.match(r"^(?:[#*\-•]+\s*)?(?:\d+(?:\.\d+)*[.)]?\s+\S|annexe|chapitre|partie|article|section)\b", low):
        return True
    lettres = re.sub(r"[^A-Za-zÀ-ÿ]", "", t)
    if len(lettres) >= 6 and lettres.upper() == lettres:
        return True
    return bool(_TITRE_MEMOIRE.search(low))


# Une rubrique de CV écrite SEULE sur sa ligne, en titre (« EXPÉRIENCE », « Formation », « Compétences : »,
# « Parcours », « Atouts ») : sa sorte (le parcours et l'expérience comptent pour une).
_RUBRIQUES_SEULES = {
    "experience": "experience", "experiences": "experience", "experience professionnelle": "experience",
    "experiences professionnelles": "experience", "parcours": "experience", "parcours professionnel": "experience",
    "formation": "formation", "formations": "formation", "diplome": "formation", "diplomes": "formation",
    "formation et diplomes": "formation", "formations et diplomes": "formation", "diplomes et formations": "formation",
    "competences": "competences", "competences techniques": "competences", "competences cles": "competences",
    "langue": "langues", "langues": "langues", "loisirs": "loisirs", "centre d interet": "loisirs",
    "centres d interet": "loisirs", "centres d interets": "loisirs", "atouts": "atouts", "qualites": "atouts",
    "savoir etre": "atouts", "etat civil": "etat_civil", "coordonnees": "coordonnees"}
_FONCTION_EN_TETE = None
_CV_TETE_MAX = 8                  # lignes non vides entre le nom et la première rubrique
_CV_FIN_MAX = 15                  # lignes gardées au plus après la dernière rubrique


def _rubrique_seule(ligne: str) -> str:
    t = (ligne or "").strip()
    if not t or len(t) > 60:
        return ""
    k = re.sub(r"[^a-z ]+", " ", _fold(re.sub(r"^[#*\-•\s\d.)]+", "", t)))
    return _RUBRIQUES_SEULES.get(re.sub(r"\s+", " ", k).strip(), "")


def _personne_en_tete(lignes: list, i: int) -> bool:
    """La ligne `i` n'est qu'un nom de PERSONNE (pas d'une entreprise) : prénom courant (« Yann TANGUY »,
    « TANGUY Yann »), ou nom suivi de sa fonction sur la ligne d'après (« Anne Le Floch » / « Cheffe de chantier »)."""
    global _FONCTION_EN_TETE
    if not _nom_seul(lignes[i]):
        return False
    toks = re.sub(r"^[#*\-•\s]+", "", (lignes[i] or "").strip()).strip(" :").split()
    if _prenom(toks[0]) or (toks[0].isupper() and _prenom(toks[-1])):
        return True
    if _FONCTION_EN_TETE is None:
        _FONCTION_EN_TETE = re.compile(r"^(?i:" + _FONCTION + r")")
    suite = next((x.strip() for x in lignes[i + 1:i + 3] if x.strip()), "")
    return bool(_FONCTION_EN_TETE.match(suite))


def _nom_seul(ligne: str) -> bool:
    """Une ligne qui n'est qu'un nom propre (« Gwenhaël KERJEAN »), jamais celui d'un organisme (« Breizh
    Couverture ») : peut-être une personne, peut-être une entreprise au nom sans mot d'organisme."""
    t = re.sub(r"^[#*\-•\s]+", "", (ligne or "").strip()).strip(" :")
    if not t or not _ligne_nom(t) or len(t) > 60:
        return False
    mots = [w for w in re.split(r"[\s\-’']+", _fold(t)) if w]
    return not any(w in _MOTS_ORGANISME for w in mots)


# Un titre numéroté ou une annexe (« 2. Moyens matériels », « Annexe 3 ») : une autre partie du document commence.
# Jamais une année (« 2015 - 2024 : conducteur de travaux »).
_TITRE_NUMEROTE = re.compile(r"^(?:[#*\-•]+\s*)?(?:\d{1,2}(?:\.\d{1,2})*[.)]\s*[A-Za-zÀ-ÿ]|\d{1,2}(?:\.\d{1,2})+\s+"
                             r"[A-Za-zÀ-ÿ]|(?:annexe|chapitre|partie|article)\b)", re.IGNORECASE)


def _autre_partie(ligne: str) -> bool:
    """« 2. Moyens matériels », « 3.1 Organisation », « Annexe 3 » : jamais une année, un téléphone ni « 15 ans »."""
    t = (ligne or "").strip()
    return _titre(t) and bool(_TITRE_NUMEROTE.match(t))


# Une ligne de parcours : une période (« 2015 - 2024 », « 2018-2024 », « 06/2015 – 09/2020 », « 2019 à ce jour »).
_PERIODE = re.compile(r"^\s*(?:[#*\-•]+\s*)?(?:de\s+|du\s+)?(?:\d{1,2}/)?(?:19|20)\d\d\s*(?:-|–|—|à|a|au)\s*"
                      r"(?:(?:\d{1,2}/)?(?:19|20)\d\d|aujourd|ce jour|present|actuel|maintenant)", re.IGNORECASE)
_COORDONNEES = re.compile(r"(?<!\d)0[1-9](?:[ .]?\d{2}){4}(?!\d)|[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE)


def _cv_sans_titre(lignes: list) -> set:
    """Les lignes d'un CV écrit SANS le mot « CV » : un nom seul sur sa ligne, suivi (à moins de _CV_TETE_MAX
    lignes) de rubriques de CV écrites seules sur leur ligne (expérience ou parcours, formation, compétences,
    langues, loisirs, atouts…), chacune à moins de _CV_FIN_MAX lignes de la précédente, jamais au-delà d'un titre
    numéroté ou d'une annexe :
      • nom d'une PERSONNE (prénom courant, ou nom suivi de sa fonction) : deux sortes de rubriques suffisent ;
      • autre nom propre (prénom rare : « Gwenhaël KERJEAN ») : trois sortes, ou deux avec des coordonnées sous le
        nom (téléphone, adresse email) et une ligne de parcours (« 2015 - 2024 … »), et jamais « nous », « notre »,
        « nos » — une plaquette (« Breizh Désamiantage », « Compétences », « Formations ») n'est pas un CV.
    Du nom jusqu'au bloc qui suit la dernière rubrique (premier saut de ligne, titre d'une autre partie ou autre
    nom ; au plus _CV_FIN_MAX lignes)."""
    out = set()
    n, i = len(lignes), 0
    while i < n:
        if not (lignes[i] or "").strip() or not _nom_seul(lignes[i]):
            i += 1
            continue
        personne = _personne_en_tete(lignes, i)
        rubs, sortes, non_vides, depuis = [], set(), 0, 0
        coord, periode = False, False
        for j in range(i + 1, min(n, i + 1 + _SECTION_CV_MAX)):
            tj = (lignes[j] or "").strip()
            if not tj:
                continue
            non_vides += 1
            depuis += 1
            k = _rubrique_seule(tj)
            if k:
                if not rubs and non_vides > _CV_TETE_MAX:
                    break
                rubs.append(j)
                sortes.add(k)
                depuis = 0
                continue
            if (not rubs and non_vides > _CV_TETE_MAX) or depuis > _CV_FIN_MAX or _autre_partie(tj):
                break
            if rubs and _personne_en_tete(lignes, j):
                break                               # le CV d'une autre personne commence
            if not rubs and _COORDONNEES.search(tj):
                coord = True
            if rubs and _PERIODE.match(tj):
                periode = True
        if not rubs or not (len(sortes) >= (2 if personne else 3) or (len(sortes) >= 2 and coord and periode)):
            i += 1
            continue
        # Un nom propre qui n'est pas sûrement une personne, et des rubriques écrites à la première personne du
        # pluriel (« Nos équipes sont formées… ») : la plaquette d'une entreprise, pas un CV.
        if not personne and any(_VOIX_ENTREPRISE.search(_fold(lignes[x] or "")) for x in range(i, rubs[-1] + 4)
                                if x < n):
            i += 1
            continue
        j, contenu = rubs[-1] + 1, False
        while j < n and j <= rubs[-1] + _CV_FIN_MAX:
            tj = (lignes[j] or "").strip()
            if not tj:
                if contenu:
                    break
            elif _personne_en_tete(lignes, j) or (_titre(tj) and not re.match(r"^\d", tj) and _fin_de_section(tj)
                                                   and not _rubrique_seule(tj)) or _autre_partie(tj):
                break
            else:
                contenu = True
            j += 1
        out.update(range(i, j))
        i = j
    return out


def lignes_privees(texte: str) -> dict:
    """Lignes du document qui ne partent JAMAIS à l'IA (décision 8, doctrine § 7 règle 9), sans IA :
      • « cv » : une SECTION de CV — un titre court qui contient « CV » ou « curriculum », n'importe où
        (« Annexe 3 : CV du conducteur de travaux »), marque les lignes suivantes jusqu'au titre qui
        ouvre une autre partie du document (numéroté, « Annexe… », en capitales, rubrique d'un mémoire ;
        jamais un nom, une fonction, une date de naissance ni une rubrique de CV), au plus
        _SECTION_CV_MAX lignes ; un paragraphe qui ressemble à un CV (`_bloc_cv`, une date de naissance
        suffit) et ses voisins (le nom au-dessus, les rubriques en dessous) ;
      • « rh » : sous un titre « Moyens humains », « Équipe », « Encadrement », « Organigramme »,
        « Personnel », « Effectif »… (sans « matériel »), chaque ligne de tableau et chaque ligne qui
        contient un nom de personne (les fiches « Équipe » se saisissent à la main ; un effectif écrit
        sans nom reste lu).
    → {"cv": set(numéros de lignes), "rh": set(numéros de lignes)}."""
    lignes = str(texte or "").split("\n")
    cv, rh = set(), set()
    mode, debut = None, 0
    for i, ligne in enumerate(lignes):
        t = ligne.strip()
        low = _fold(t)
        if _titre(t) and not _ligne_nom(t):
            if _TITRE_SECTION_CV.search(low):
                mode, debut = "cv", i
                cv.add(i)
                continue
            if _TITRE_RH.search(low) and "materiel" not in low and mode != "cv":
                mode, debut = "rh", i
                continue
            if mode is not None and _fin_de_section(t) and not _RUBRIQUE_CV.match(
                    re.sub(r"^[#*\-•\s\d.)]+", "", low)):
                mode = None
        if mode == "cv":
            if i - debut > _SECTION_CV_MAX:
                mode = None
            else:
                cv.add(i)
                continue
        if mode == "rh" and t and (t.startswith("|") or _a_un_nom(t)):
            rh.add(i)
    # Un paragraphe qui ressemble à un CV, et ses voisins.
    paras, cur = [], []
    for i, ligne in enumerate(lignes):
        if ligne.strip():
            cur.append(i)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    for k, para in enumerate(paras):
        if not _bloc_cv("\n".join(lignes[i] for i in para)):
            continue
        cv.update(para)
        if k > 0 and len(paras[k - 1]) <= 2 and all(_ligne_nom(lignes[i]) for i in paras[k - 1]):
            cv.update(paras[k - 1])          # le nom au-dessus
        for suite in paras[k + 1:k + 4]:
            bloc = "\n".join(lignes[i] for i in suite)
            lowb = _fold(bloc)
            if _RUBRIQUE_CV.match(re.sub(r"^[#*\-•\s\d.)]+", "", lowb)) \
                    or any(rx.search(lowb) for rx in _CV_FAIBLES + _CV_FORTS):
                cv.update(suite)
            else:
                break
    # Un CV écrit sans le mot « CV » (un nom, puis « EXPÉRIENCE », « FORMATION », « COMPÉTENCES »…).
    cv |= _cv_sans_titre(lignes)
    return {"cv": cv, "rh": rh - cv}


def texte_sans_lignes_privees(texte: str) -> tuple:
    """(texte où les lignes privées sont vidées — mêmes paragraphes —, nombre de caractères de CV retirés)."""
    lignes = str(texte or "").split("\n")
    priv = lignes_privees(texte)
    n_cv = sum(len(lignes[i]) for i in priv["cv"])
    for i in priv["cv"] | priv["rh"]:
        lignes[i] = ""
    return "\n".join(lignes), n_cv


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
    total = sum(len(b) for b in _blocs(texte)) or 1
    _t, n_cv = texte_sans_lignes_privees(texte)
    return n_cv / total >= 0.4


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
    texte, _n = texte_sans_lignes_privees(doc.text or "")
    avant = _blocs(doc.text or "")
    blocs = _blocs(texte)
    garde, n_cv = [], max(0, len(avant) - len(blocs))
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
_CACHE_LOCK = threading.Lock()


def statut_document(doc: KnowledgeDoc) -> Optional[str]:
    """DOC_CV, DOC_ACHETEUR, DOC_VIDE, ou None (lisible). Mémorisé : le texte d'un document de « Mon
    savoir-faire » ne change jamais après son import."""
    t = doc.text or ""
    cle = (doc.id, len(t), hash(t[:2000]), hash(doc.name or ""))
    with _CACHE_LOCK:
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
    with _CACHE_LOCK:
        if len(_CACHE_STATUT) >= _CACHE_MAX:
            _CACHE_STATUT.pop(next(iter(_CACHE_STATUT)), None)
        _CACHE_STATUT[cle] = st
    return st


_MSG_STATUT = {DOC_CV: MSG_CV, DOC_ACHETEUR: MSG_ACHETEUR, DOC_VIDE: MSG_VIDE}


# ── Aucun CV vers l'IA, sur TOUS les chemins (rédaction, dossier de groupement, questionnaire) ─────

_CACHE_PRIVE = {}           # (id, longueur, nom) → (est un CV, lignes de CV repliées) : le texte ne change pas
_LIGNE_CV_MIN = 12          # une ligne de CV plus courte (« Formations ») ne sert pas à reconnaître un extrait


def _norm_espaces(s) -> str:
    return re.sub(r"\s+", " ", _fold(s)).strip()


def _prive(doc: KnowledgeDoc) -> tuple:
    cle = (doc.id, int(doc.char_count or len(doc.text or "")), doc.name or "")
    with _CACHE_LOCK:
        if cle in _CACHE_PRIVE:
            return _CACHE_PRIVE[cle]
    texte = doc.text or ""
    lignes = texte.split("\n")
    cv = est_cv(doc)
    lcv = frozenset(_norm_espaces(lignes[i]) for i in lignes_privees(texte)["cv"]
                    if len(_norm_espaces(lignes[i])) >= _LIGNE_CV_MIN)
    with _CACHE_LOCK:
        if len(_CACHE_PRIVE) >= _CACHE_MAX:
            _CACHE_PRIVE.pop(next(iter(_CACHE_PRIVE)), None)
        _CACHE_PRIVE[cle] = (cv, lcv)
    return cv, lcv


def sans_cv(db, chunks: list) -> list:
    """Les extraits de « Mon savoir-faire » qui peuvent partir à l'IA (décision 8, doctrine § 7 règle 9) :
    jamais un extrait d'un document qui ressemble à un CV (le même jugement que « Partir de vos anciens
    dossiers » : statut « cv »), jamais un extrait qui contient un passage de CV (section « CV » d'un
    ancien mémoire, date de naissance…). Sans IA ; l'ordre est gardé."""
    if not chunks:
        return []
    ids = {c.get("doc_id") for c in chunks if isinstance(c, dict) and c.get("doc_id")}
    docs = {d.id: d for d in db.query(KnowledgeDoc).filter(KnowledgeDoc.id.in_(list(ids))).all()} if ids else {}
    out = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        texte = str(c.get("text") or c.get("texte") or "")
        if _bloc_cv(texte):
            continue
        d = docs.get(c.get("doc_id"))
        if d is not None:
            cv, lignes = _prive(d)
            if cv:
                continue
            if lignes:
                plat = _norm_espaces(texte)
                if any(x in plat for x in lignes):
                    continue
        out.append(c)
    return out

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
# Les fonctions (mots fixes) : sans « responsable … », qui se lit à part.
_FONCTION_MOTS = (r"chef(?:fe)? de (?:chantier|projet|travaux|chantiers|site|atelier)|chef(?:fe)? d['’](?:équipe|atelier)|"
                  r"conduct(?:eur|rice) de travaux|compagnon|ouvri(?:er|ère)|charpentier|couvreur|maçon|plombier|"
                  r"électricien|menuisier|peintre|technicien(?:ne)?|ingénieur(?:e)?|co-?gérant(?:e)?|gérant(?:e)?|"
                  r"dirigeant(?:e)?|président(?:e)?|directeur|directrice|apprenti(?:e)?|assistant(?:e)?|comptable|"
                  r"secrétaire|encadrant(?:e)?|référent(?:e)?|associé(?:e)?|fondat(?:eur|rice)|"
                  r"interlocut(?:eur|rice)(?: unique)?|chargée? d['’]affaires|opérat(?:eur|rice)")
_FONCTION = r"(?:" + _FONCTION_MOTS + r"|responsable [a-zéèêà ]{3,30})"
# « X, notre gérant », « X (notre conductrice de travaux) » : un déterminant peut séparer le nom de sa fonction.
_DET = r"(?:(?:notre|nos|son|sa|leur|le|la|l['’]|un|une)\s+)?"
_NOM_PUIS_FONCTION = re.compile(r"(?<![\w’'])(" + _PRENOM_NOM + r")\s*(?:,|\(|–|—|-|:)\s*" + _DET + r"(?i:" + _FONCTION
                                + ")")
_FONCTION_PUIS_NOM = re.compile(r"(?i:" + _FONCTION + r")\s*(?::|–|—|-|,)\s*(?:M\.\s|Mme\s)?(" + _PRENOM_NOM
                                + r")(?![\w])")
# « Notre gérant Pierre Martin », « le conducteur de travaux Yann Tanguy » : la fonction suivie du nom, sans
# ponctuation (« responsable » seulement suivi de mots en minuscules : « responsable environnement Anne Le Floch »).
_FONCTION_ESPACE_NOM = re.compile(r"(?:(?i:" + _FONCTION_MOTS + r")|(?i:responsable)(?: [a-zéèêàç]+){1,3})\s+"
                                  r"(?:M\.\s|Mme\s)?(" + _PRENOM_NOM + r")(?![\w])")
_PAR = (r"(?i:sous la (?:conduite|direction|responsabilit[ée]) d[e']|encadr[ée]e?s? par|dirig[ée]e?s? par|"
        r"suivie?s? par|pilot[ée]e?s? par|men[ée]e?s? par|coordonn[ée]e?s? par|assur[ée]e?s? par|"
        r"r[ée]alis[ée]e?s? par|anim[ée]e?s? par|g[ée]r[ée]e?s? par|tenue?s? par|reprise? par|"
        r"(?:fond|cr[ée])[ée]e?s?(?: en \d{4})? par)")
_PAR_NOM = re.compile(_PAR + r"\s*(" + _PRENOM_NOM + r")(?![\w])")
# « assuré par Gwenola Riou et Loïc Cadiou », « créée par X, Y et Z » : chaque nom de la suite.
_PAR_NOMS = re.compile(_PAR + r"\s*((?:" + _PRENOM_NOM + r")(?:\s*(?:,|\bet\b|&)\s*(?:" + _PRENOM_NOM + r"))+)(?![\w])")
_PRENOM_NOM_LIGNE = re.compile(_PRENOM_NOM)
# « Jean-Yves Le Goff, 15 ans d'expérience » : un nom suivi d'une ancienneté.
_NOM_PUIS_ANS = re.compile(r"(?<![\w’'])(" + _PRENOM_NOM + r")\s*(?:,|\(|–|—|-|:)\s*\d{1,2}\s*ans\b")
# Une suite de noms après « : » (« Encadrement : Gwenaël Kerhervé et Soizic Le Bris »).
_LISTE_NOMS = re.compile(r":\s*((?:" + _PRENOM_NOM + r")(?:\s*(?:,|et|&)\s*(?:" + _PRENOM_NOM + r"))*)(?=\s*(?:[.;,)]|$|\n))")
# Un mot qui fait d'une suite de mots à majuscule un ORGANISME, pas une personne.
_MOTS_ORGANISME = {"couverture", "construction", "constructions", "batiment", "batiments", "btp", "menuiserie",
                   "charpente", "charpentes", "metropole", "habitat", "services", "groupe", "industrie", "energie",
                   "energies", "renovation", "zinguerie", "plomberie", "electricite", "peinture", "maconnerie",
                   "travaux", "ingenierie", "conseil", "agglomeration", "communaute", "region", "departement",
                   "immobilier", "logement", "solutions", "environnement", "sarl", "sas", "eurl", "scop", "sa",
                   "france", "ouest", "est", "nord", "sud", "atlantique", "armor", "bretagne", "finistere",
                   "morbihan", "agence", "bureau", "cabinet", "architectes", "architecture", "etudes", "technique",
                   "techniques", "lycee", "college", "ecole", "mairie", "hopital", "clinique", "gymnase",
                   "mediatheque", "piscine", "residence", "eglise", "chapelle", "salle", "centre", "parc", "zone",
                   "rue", "avenue", "boulevard", "place", "quai", "chemin", "route", "allee", "impasse"}
_PAS_UN_NOM = {"mairie", "ville", "commune", "departement", "region", "conseil", "societe", "sarl", "sas", "eurl",
               "ecole", "college", "lycee", "centre", "office", "habitat", "agence", "groupe", "entreprise",
               "communaute", "metropole", "syndicat", "chantier", "projet", "travaux", "service", "direction",
               "batiment", "residence", "salle", "rue", "avenue", "place", "le", "la", "les", "nous", "notre"}


# Prénoms courants (sans accents, en minuscules), français et bretons : par le lien d'un partenaire sans compte,
# aucune équipe n'est connue ; un « Prénom Nom » dont le prénom est l'un d'eux est alors pris pour une personne
# (`noms_probables(etendu=True)`), où qu'il soit écrit (« Jean-Marc Riou pilote nos chantiers »).
_PRENOMS = set("""
adele adrien agathe agnes aime alain alan alexandra alexandre alexis alice alain aline amandine amelie anais andre
andree angelique anne annick annie anthony antoine antonin armel armelle arnaud arthur aude audrey aurelie aurelien
axel aziliz baptiste barbara bastien beatrice benedicte benjamin benoit bernadette bernard bertrand blandine bleuenn
brieuc brigitte bruno camille capucine carole caroline catherine cecile celine chantal charles charlotte chloe
christian christelle christine christophe claire claude clement clemence colette coralie corentin cyril cyrille
damien daniel danielle david delphine denis denise didier dominique dylan edith edouard elisa elisabeth elise
elodie eloise emeline emile emilie emma emmanuel emmanuelle enora eric erwan erwann estelle etienne eugene eva
evelyne fabien fabienne fabrice fanny florence florent florian francis franck francois francoise frederic
frederique gael gaelle gaetan gaud gaid gabriel gabrielle genevieve georges gerard gilbert gilles gisele glenn
goulven gregoire gregory guenael guenole guillaume gurvan guy gwen gwenael gwenaelle gwendal gwendoline gwenn
gwenola gwenole helene henri herve hugo hugues ines irene isabelle jacqueline jacques jakez jean jeanne jeannine
jeremie jeremy jerome joel joelle johan jonathan jordan joseph josette josiane julie julien juliette justine katell
kevin klervi laetitia laura laurence laurent lea leo leon leonie lionel lise loic loig louis louise luc lucas
lucie lucien ludovic madeleine mael maela maelle maeva maiwenn malo manon marc marcel marguerite maria marie
marine marion martine mathieu mathilde mathis matthieu maud maurice maxime melanie melissa michel michele micheline
mickael mikael monique morgan morgane muriel myriam nadine nathalie nathan nicolas nicole noel noemie nolwenn
nolwen oceane odile olivier pascal pascale patrice patricia patrick paul paule pauline per perrine philippe pierre
pierrick quentin rachel raphael raymond regis remi renan rene riwal robert roger romain ronan rozenn sabine
sabrina samuel sandra sandrine sarah sebastien serge severine simon simone solene solenn sophie soizic stephane
stephanie suzanne sylvain sylvie tanguy thibault thibaut thierry thomas tifenn tristan tudal tugdual valentin
valerie vanessa veronique victor vincent virginie vivien xavier yann yannick yoann youenn yvan yves yvette yvon
yvonne zoe
""".split())
# Un mot juste avant un « Prénom Nom » qui en fait le nom d'un LIEU ou d'un établissement (« école Jules Ferry »,
# « rue Victor Hugo », « collège Jean Moulin ») : ce n'est pas une personne de l'entreprise.
# (Liste propre : pas les mots d'organisme comme « est » ou « sa », qui précèdent aussi un nom de personne.)
_AVANT_UN_LIEU = {"ecole", "college", "lycee", "groupe", "scolaire", "universite", "faculte", "iut", "campus", "creche",
                  "ehpad", "foyer", "residence", "hopital", "clinique", "mairie", "eglise", "chapelle", "salle",
                  "gymnase", "mediatheque", "bibliotheque", "piscine", "stade", "complexe", "centre", "espace",
                  "maison", "pole", "halle", "halles", "musee", "theatre", "institut", "fondation", "caserne", "gare",
                  "port", "parc", "jardin", "square", "zone", "quartier", "cite", "ilot", "lotissement", "pont", "rue",
                  "avenue", "boulevard", "place", "quai", "chemin", "route", "allee", "impasse", "cours", "esplanade",
                  "promenade", "saint", "sainte", "st", "ste"}
_PRENOM_NOM_DEBUT = re.compile(_PRENOM_NOM + r"(?![\w])")
_NOM_PUIS_PRENOM = re.compile(r"(?<![\w’'])([A-ZÀ-Ý]{2,}(?:[\s\-][A-ZÀ-Ý]{2,})?)\s+"
                              r"([A-ZÀ-Ý][a-zà-öø-ÿ]+(?:-[A-ZÀ-Ý][a-zà-öø-ÿ]+)?)(?![\w])")


_OUVERTURE_NOM: set = set()


def _ouverture_nom() -> set:
    """Mots d'ouverture d'une phrase (« Avec », « Pour », « Contact »…), jamais le début d'un nom de personne."""
    if not _OUVERTURE_NOM:
        from app.services.faits_a_relire import _OUVERTURE
        _OUVERTURE_NOM.update(set(_OUVERTURE) | {"contact", "interlocuteur", "interlocutrice", "fondee", "fonde",
                                                 "creee", "cree", "merci", "bonjour", "madame", "monsieur"})
    return _OUVERTURE_NOM


def _prenom(mot: str) -> bool:
    return _fold(re.split(r"[\-’']", mot or "")[0]) in _PRENOMS


def _noms_par_prenom(t: str) -> list:
    """« Prénom Nom » (« Pierre Martin », « Jean-Marc Riou », « Yann TANGUY ») et « NOM Prénom » (« TANGUY Yann »),
    quand le prénom est un prénom courant ; jamais derrière un mot de lieu ou d'établissement."""
    out = []
    # Chaque mot à majuscule qui est un prénom courant ouvre un « Prénom Nom » possible (même au milieu d'une suite de
    # mots à majuscule : « Contact Sophie Bernard »).
    # Un article ou une préposition élidés peuvent le précéder (« l'aide d'Anne Le Floch »).
    for w in re.finditer(r"(?<![\w’'\-])(?:[dDlL]['’])?([A-ZÀ-Ý][a-zà-öø-ÿ]+(?:-[A-ZÀ-Ý][a-zà-öø-ÿ]+)?)", t):
        if not _prenom(w.group(1)):
            continue
        m = _PRENOM_NOM_DEBUT.match(t, w.start(1))
        if m is None:
            continue
        # Le mot juste avant, sans son article élidé (« l'école Jules Ferry », « l'espace Pierre Loti »).
        avant = re.findall(r"[\w\-]+", t[max(0, w.start() - 40):w.start()])
        if avant and _fold(avant[-1]) in _AVANT_UN_LIEU:
            continue
        out.append(m.group(0))
    for m in _NOM_PUIS_PRENOM.finditer(t):
        if _prenom(m.group(2)) and len(m.group(1)) >= 3:
            out.append(m.group(1) + " " + m.group(2))
    return out


def noms_probables(texte: str, etendu: bool = False) -> list:
    """Noms de personnes écrits dans le document, sans IA : après une civilité (« M. Kerjean »,
    « Mme Anne Le Floch »), accolés à une fonction (« Yann Tanguy, conducteur de travaux », « Pierre Martin,
    notre gérant », « Chef de chantier : Paul Durand », « Notre gérant Pierre Martin »), ou après « sous la
    conduite de », « dirigé par », « assuré par », « fondée en 2009 par »… (une suite « X et Y » comprise).
    `etendu` (aucune équipe connue : le lien d'un partenaire sans compte) : en plus, tout « Prénom Nom » dont le
    prénom est courant (`_PRENOMS`). Ils sont masqués comme ceux de l'équipe (pii_scope). Un repérage sans IA ne
    trouve pas tout : un nom écrit autrement peut lui échapper."""
    t = str(texte or "")
    vus, out = set(), []

    def _ajoute(n):
        n = re.sub(r"\s+", " ", n).strip(" ,;:-–—'’")
        # Un mot d'ouverture pris avec le nom en début de phrase (« Avec Thomas Le Bihan, responsable… ») n'en fait
        # pas partie : sinon « Avec » serait masqué partout.
        ws = n.split(" ")
        while len(ws) > 2 and _fold(ws[0]) in _ouverture_nom():
            ws = ws[1:]
        n = " ".join(ws)
        mots = [w for w in re.split(r"[\s\-’']+", _fold(n)) if w]
        if not mots or any(w in _PAS_UN_NOM for w in mots[:1]) or len(n) < 3 or len(n) > 80:
            return
        if any(w in _MOTS_ORGANISME for w in mots):
            return                      # « Breizh Couverture », « Brest Métropole Habitat » : un organisme
        k = _fold(n)
        if k not in vus:
            vus.add(k)
            out.append(n)

    for m in _CIVILITE.finditer(t):
        _ajoute(m.group(1))
    for rx in (_NOM_PUIS_FONCTION, _FONCTION_PUIS_NOM, _FONCTION_ESPACE_NOM, _PAR_NOM, _NOM_PUIS_ANS):
        for m in rx.finditer(t):
            _ajoute(m.group(1))
    for m in _PAR_NOMS.finditer(t):
        for n in re.split(r"\s*(?:,|\bet\b|&)\s*", m.group(1)):
            if n.strip():
                _ajoute(n)
    if etendu:
        for n in _noms_par_prenom(t):
            _ajoute(n)
    # Une case de tableau qui n'est qu'un nom (« | Jean-Yves Le Goff | Chef de chantier | 15 ans | »).
    for ligne in t.split("\n"):
        if ligne.strip().startswith("|"):
            for case in ligne.strip().strip("|").split("|"):
                c = case.strip()
                if c and _PRENOM_NOM_LIGNE.fullmatch(c):
                    _ajoute(c)
    # Une suite de noms après « : » (« Encadrement : Gwenaël Kerhervé et Soizic Le Bris. »).
    for m in _LISTE_NOMS.finditer(t):
        for n in re.split(r"\s*(?:,|\bet\b|&)\s*", m.group(1)):
            if n.strip():
                _ajoute(n)
    return out[:300]


def equipe_avec_noms_reperes(equipe: list, textes, exclure=(), etendu: bool = False) -> list:
    """L'équipe connue + les noms de personnes repérés dans ces textes (sans IA), pour le pseudonymiseur
    d'un appel : un nom écrit dans un ancien mémoire, une fiche ou un extrait part masqué, comme ceux
    de l'équipe (doctrine § 7, règle 9). `exclure` : les noms qui ne sont jamais des personnes (le nom
    de l'entreprise et de ses partenaires : c'est le sujet du texte). `etendu` : repérage élargi aux prénoms
    courants (aucune équipe connue, voir `noms_probables`)."""
    out = [m for m in (equipe or []) if isinstance(m, dict)]
    connus = {_fold(m.get("nom")) for m in out}
    jamais = [_fold(x) for x in (exclure or ()) if x and len(_fold(x)) >= 3]
    for n in noms_probables("\n\n".join(str(x or "") for x in (textes or []) if x), etendu=etendu):
        fn = _fold(n)
        if any(fn == j or fn in j or j in fn for j in jamais):
            continue
        if fn not in connus:
            out.append({"nom": n, "fonction": "Personne"})
            connus.add(_fold(n))
    return out


def pseudonymiseur(db, owner_id: int, parties: list):
    """Noms connus (profil, fiches « Équipe ») + noms repérés dans ce qui part à l'IA."""
    from app.services.pii import from_team, team_of_users
    return from_team(equipe_avec_noms_reperes(team_of_users(db, [owner_id]), parties))


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
6. Les fiches dans l'ordre du document.

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


def appels_au_plus(parties: list) -> int:
    """Appels à l'IA au plus pour lire ces parties (`_appel`) : une partie assez longue pour être relue
    peut coûter APPELS_PAR_PARTIE appels, une courte un seul. C'est CE nombre que l'estimation du
    budget de l'essai compte, au prix d'une partie pleine chacun (prudent)."""
    return sum(APPELS_PAR_PARTIE if len(p or "") >= SEGMENT_MIN_COUPE else 1 for p in parties or [])


def _fiches_completes(texte: str) -> list:
    """Les fiches COMPLÈTES d'une réponse coupée (JSON tronqué) : rien de ce qui est déjà écrit n'est jeté."""
    import json
    t = str(texte or "")
    m = re.search(r'"fiches"\s*:\s*\[', t)
    if not m:
        return []
    dec, pos, out = json.JSONDecoder(), m.end(), []
    while True:
        while pos < len(t) and t[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(t) or t[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(t, pos)
        except ValueError:
            break
        if isinstance(obj, dict):
            out.append(obj)
    return out[:FICHES_PAR_APPEL]


def _reste_apres(partie: str, fiches: list) -> Optional[str]:
    """La suite de la partie à relire après une réponse coupée : à partir du paragraphe du dernier
    passage retrouvé (l'IA propose les fiches dans l'ordre du document). None si aucun passage n'est
    retrouvé ; "" si tout a été lu."""
    t = _Texte(partie)
    fin = -1
    for f in fiches:
        loc = t.localiser(str(f.get("passage") or "")) if isinstance(f, dict) else None
        if loc is not None:
            fin = max(fin, loc[1])
    if fin < 0:
        return None
    debut = partie.rfind("\n\n", 0, fin)
    debut = debut + 2 if debut >= 0 else fin
    if debut <= 0:
        debut = fin
    return partie[debut:] if partie[debut:].strip() else ""


def _appel(partie: str, rang: int, total: int, reste_appels: Optional[list] = None) -> list:
    """Une partie du document → propositions brutes de l'IA, en APPELS_PAR_PARTIE appels au plus.
    Réponse coupée (partie trop dense) : les fiches déjà complètes sont gardées (rien n'est jeté) et la
    lecture reprend au paragraphe du dernier passage retrouvé ; si aucune fiche n'est complète, la
    partie est relue en deux moitiés (paragraphes entiers). Une réponse illisible lève une erreur (rien
    n'est proposé, la lecture est rendue)."""
    from app.services import llm
    reste_appels = reste_appels if reste_appels is not None else [APPELS_PAR_PARTIE]
    reste_appels[0] -= 1
    resp = llm.messages_create(
        tache=TACHE, json_attendu=True, max_tokens=SORTIE_MAX, system=CONSIGNES,
        messages=[{"role": "user", "content": f"Document à lire (partie {rang} sur {total}) :\n<<<\n{partie}\n>>>"}])
    texte = (resp.content[0].text if getattr(resp, "content", None) else "") or ""
    if getattr(resp, "stop_reason", "") == "max_tokens":
        gardees = _fiches_completes(texte)
        if reste_appels[0] > 0 and len(partie) >= SEGMENT_MIN_COUPE:
            suite = _reste_apres(partie, gardees) if gardees else None
            if suite is not None:
                return gardees + (_appel(suite, rang, total, reste_appels) if suite.strip() else [])
            if reste_appels[0] >= 2:
                a, b = _moities(partie)
                if a and b:
                    moitie = reste_appels[0] // 2
                    reste_appels[0] = 0
                    return gardees + _appel(a, rang, total, [moitie]) + _appel(b, rang, total, [moitie])
        if gardees:
            return gardees              # plus d'appel possible : ce qui est complet est gardé
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


# Libellé d'un chiffre clé : quelques mots de catégorie admis SEULEMENT si le passage dit la même
# chose avec ses mots (« Effectif » pour « 12 salariés »). Liste fermée : un chiffre n'est jamais
# rangé sous une autre catégorie que celle que le passage écrit (85 chantiers ≠ chiffre d'affaires).
_CATEGORIES = {
    "effectif": r"salari|compagnon|personnes|employe|collaborat|ouvrier|effectif|equipe",
    "effectifs": r"salari|compagnon|personnes|employe|collaborat|ouvrier|effectif|equipe",
    "chiffre": r"chiffre d'affaires|\bca\b",
    "affaires": r"chiffre d'affaires|\bca\b",
    "surface": r"m2|m²|metres? carres|surface",
    "creation": r"\bcree|creation|fonde|fondation|depuis (?:19|20)\d\d",
    "anciennete": r"\bcree|creation|fonde|fondation|depuis (?:19|20)\d\d|anciennete",
}


def mots_hors_passage(valeur_txt: str, passage: str, champ: str = "") -> list:
    """Mots porteurs de sens d'un champ écrit qui n'apparaissent pas dans le passage (repliés, à la
    racine près : « réalisée » / « réalisé », « toitures » / « toiture »). Une reformulation de l'IA
    (« rénovation » pour « réfection ») n'est jamais gardée. Le libellé d'un chiffre clé admet en plus
    un mot de catégorie que le passage justifie (_CATEGORIES)."""
    low = _fold(passage)
    mots_p = set()
    for w in re.findall(r"[a-z0-9]+", low):
        mots_p.add(w)
        mots_p.add(_racine(w))
    out = []
    for w in re.findall(r"[a-z]+", _fold(valeur_txt)):
        if len(w) < 4 or w in _MOTS_VIDES:
            continue
        if w in mots_p or _racine(w) in mots_p:
            continue
        if champ == "libelle" and w in _CATEGORIES and re.search(_CATEGORIES[w], low):
            continue
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
        trop = pv.elements_hors_passage(nature, val, ext, champs=[k])
        if not trop and isinstance(v, str) and k in _TXT:
            trop = mots_hors_passage(v, ext, k)
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
    # Essai : la limite d'usage est vérifiée AVANT (estimation prudente : le pire de `_appel`, chaque
    # appel au prix d'une partie pleine) ; essai terminé sans forfait : 402 (budget_ia.verifier appelle
    # quota.exiger_ia).
    budget_ia.verifier(user, db, OPERATION, budget_ia.estimer(OPERATION, n=appels_au_plus(lecture["parties"])))
    lim = plafond_mensuel()
    if lectures_du_mois(db, owner_id) >= lim:
        raise ImportError_(429, "plafond_atteint", _msg_plafond(lim))
    job = Job(user_id=user.id, kind=JOB_KIND, status="pending",
              label=f"Fiches proposées : « {(doc.name or 'Document')[:200]} »"[:255],
              result={"doc_id": doc.id, "date_document": ds.isoformat() if ds else None})
    db.add(job)
    db.commit()
    db.refresh(job)
    # Deux demandes au même moment : une seule lecture par document (la plus ancienne garde la
    # main), et le plafond tient (seules les lectures au-delà des `lim` premières du mois sont
    # refusées, jamais toutes).
    premiere = _derniere_lecture(db, owner_id, doc.id)
    du_mois = [j.id for j in _jobs(db, owner_id, _debut_du_mois()) if j.status != "error"]
    if (premiere is not None and premiere.id != job.id) or job.id not in du_mois[:lim]:
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
