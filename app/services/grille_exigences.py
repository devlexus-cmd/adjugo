"""
« Comment vous serez noté », suite : ce que le dossier DEMANDE au candidat (rédaction, vague 5 — C2 complet
de l'étude, § 6.3). Contrat : docs/REDACTION_V5.md, section C2.

Tout est repéré SANS IA dans le texte déjà extrait, toujours avec la phrase mot pour mot (procédé de
clauses_groupement : chaque phrase repasse par citation_guard contre le texte intégral du dossier) :

  • les EXIGENCES : « le mémoire comprendra… », « le candidat devra… », « il est demandé… », les questions
    d'un cadre de réponse (« Décrivez… ») et les listes qu'elles ouvrent. L'IA de l'analyse peut en
    PROPOSER d'autres (details.exigences_memoire) : seulement des phrases, gardées si elles sont retrouvées
    mot pour mot ; leur libellé est tiré de la phrase, jamais écrit par l'IA ;
  • « traitée » : la règle EXPLICITE (traitement) qui remplace toute note de conformité donnée par l'IA —
    une exigence est traitée quand le texte d'une partie du dossier reprend ses mots principaux ;
  • l'ENVIRONNEMENT, en information neutre : où il apparaît dans la notation ;
  • l'interdiction de répondre à la fois seul et en groupement, ou dans plusieurs groupements (R2142-21) ;
  • la mention de l'INTELLIGENCE ARTIFICIELLE (le mode « sans IA » est alors proposé) ;
  • les QUESTIONS À POSER À L'ACHETEUR quand le dossier se contredit ou reste flou, chacune avec sa phrase,
    et la date limite des questions si le règlement la donne. Adjugo n'envoie rien : l'entreprise pose les
    questions elle-même sur la plateforme de l'acheteur.

Fonctions pures : ni IA, ni réseau, ni base. On ne dit jamais « vérifié » : on dit où la phrase a été
trouvée.
"""
import copy
import math
import re
from datetime import date, timedelta
from typing import Optional

from app.services import dce_pieces as dp

EXIGENCES_MAX = 40
LIBELLE_MAX = 160
LISTE_MAX = 15
QUESTIONS_MAX = 8
IA_EXIGENCES_MAX = 10
IA_QUESTIONS_MAX = 3
CLES_MAX = 8

REPERAGE = "reperage"          # repérée par Adjugo, sans IA
IA = "ia"                      # phrase proposée par l'IA de l'analyse, retrouvée mot pour mot
UTILISATEUR = "utilisateur"    # ajoutée par l'utilisateur (phrase retrouvée mot pour mot)

TRAITEE = "traitee"
A_TRAITER = "a_traiter"
TRAITEE_SELON_VOUS = "traitee_selon_vous"
RETIREE = "retiree"

CHOIX_EXIGENCE = ("ecarte", "traitee", "annule")
CHOIX_QUESTION = ("ecarte", "annule")

REGLE_TRAITEE = ("Une exigence est comptée comme traitée quand le texte d'une partie du dossier reprend ses mots "
                 "principaux : tous s'il y en a un ou deux, sinon au moins la moitié (et au moins deux). Les "
                 "« [À compléter] » ne comptent pas. C'est un repérage de mots, pas une relecture : relisez "
                 "chaque exigence. Vous pouvez la dire traitée vous-même, ou la retirer si ce n'est pas une "
                 "exigence.")
MSG_ENV = "L'environnement compte dans la note : voici où il apparaît dans le règlement."
MSG_QUESTIONS = "Adjugo n'envoie rien : c'est vous qui posez les questions sur la plateforme de l'acheteur"
MSG_SANS_QUESTION = ("Adjugo n'a repéré ni contradiction ni point flou sur ce qu'il contrôle (pondération, "
                     "sous-critères, limites, visite, cadre de réponse, date limite, intelligence artificielle). "
                     "Le règlement fait foi.")
MSG_IA_INTERDIT = ("Le règlement écarte l'intelligence artificielle : lisez la phrase. Adjugo vous propose de rédiger "
                   "ce dossier sans IA : vous écrivez vous-même ; le contrôle des faits et la liste des exigences "
                   "continuent.")
MSG_IA_DECLARER = ("Le règlement demande de signaler l'usage de l'intelligence artificielle : lisez la phrase. Si "
                   "l'IA vous aide, dites-le comme le règlement le demande. Vous pouvez aussi rédiger ce dossier "
                   "sans IA.")
MSG_IA_MENTION = ("Le règlement parle d'intelligence artificielle : lisez la phrase. Vous pouvez rédiger ce dossier "
                  "sans IA.")
MSG_IA_PERMIS = ("Le règlement admet l'intelligence artificielle : lisez la phrase. Vous restez libre de rédiger ce "
                 "dossier sans IA.")
MSG_IA_PARTENAIRE = ("Le règlement parle d'intelligence artificielle : lisez la phrase. Le chef de file choisit si le "
                     "dossier se rédige sans IA ; Adjugo vous le dira dans vos parties.")
MSG_SEUL_ET_GROUPEMENT = ("Le règlement interdit de répondre à la fois seul et en groupement : une même entreprise ne "
                          "peut pas déposer les deux offres.")
MSG_PLUSIEURS_GROUPEMENTS = "Le règlement interdit d'être membre de plusieurs groupements pour ce marché."
MSG_MANDATAIRE = "Le règlement interdit d'être chef de file de plus d'un groupement pour ce marché."


# ── Petits outils ────────────────────────────────────────────────────────────────────

def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fold(s) -> str:
    return dp.fold(s)


def _gn():
    from app.services import grille_notation as gn
    return gn


def _guard(text: str, phrase: str, min_len: int = 12) -> str:
    from app.services.analysis import citation_guard
    return citation_guard(text, phrase, min_len=min_len)


def _source(p) -> str:
    return _gn()._source_label(p)


def _clip_phrase(p, s: int, e: int, a: int = None, b: int = None) -> tuple:
    """(début, phrase) de [s, e) bornée à PHRASE_MAX autour de [a, b), sur des limites de mots."""
    gn = _gn()
    a = s if a is None else a
    b = min(e, a + 1) if b is None else b
    s2, e2 = gn._clip(p.flat, s, e, a, b)
    raw = p.flat[s2:e2]
    lead = len(raw) - len(raw.lstrip())
    return s2 + lead, raw.strip()


def _couper(s: str, n: int = LIBELLE_MAX) -> str:
    s = _flat(s)
    if len(s) <= n:
        return s
    cut = s.rfind(" ", 0, n)
    return (s[:cut] if cut > n // 2 else s[:n]).rstrip(" ,;:") + "…"


# ── Les mots principaux d'une exigence (règle « traitée ») ─────────────────────────────

_MOTS_VIDES = {
    "de", "des", "du", "la", "le", "les", "et", "en", "au", "aux", "un", "une", "par", "pour", "sur", "dans", "avec",
    "sans", "ou", "a", "l", "d", "qui", "que", "quoi", "dont", "se", "sa", "son", "ses", "leur", "leurs", "ce", "cet",
    "cette", "ces", "il", "ils", "elle", "elles", "est", "sont", "sera", "seront", "etre", "avoir", "ont", "y", "ne",
    "pas", "plus", "tres", "tout", "tous", "toute", "toutes", "chaque", "ainsi", "afin", "lors", "selon", "entre",
    "vers", "chez", "sous", "apres", "avant", "pendant", "notre", "nos", "votre", "vos", "mon", "mes", "ton", "tes",
    "lui", "eux", "meme", "memes", "autre", "autres", "tel", "telle", "tels", "telles", "si", "non", "oui", "cas",
}
# Mots qui se trouvent dans presque toute exigence : ils ne disent pas ce qui est demandé.
_GENERIQUES = {
    "candidat", "candidats", "soumissionnaire", "soumissionnaires", "memoire", "memoires", "technique", "techniques",
    "offre", "offres", "dossier", "dossiers", "document", "documents", "notamment", "ensemble", "suivant", "suivants",
    "suivante", "suivantes", "element", "elements", "mise", "oeuvre", "prevu", "prevue", "prevus", "prevues",
    "propose", "proposee", "proposes", "proposees", "envisage", "envisagee", "envisages", "envisagees", "cadre",
    "reponse", "reponses", "partie", "parties", "egalement", "obligatoirement", "imperativement", "particulier",
    "particuliere", "precisement", "clairement", "marche", "marches", "prestation", "prestations", "travaux",
    "presenter", "presente", "presentera", "presentez", "preciser", "precise", "precisera", "precisez", "decrire",
    "decrit", "decrira", "decrivez", "detailler", "detaille", "detaillera", "detaillez", "detaillee", "detailles",
    "detaillees", "indiquer", "indique", "indiquera", "indiquez", "fournir", "fournit", "fournira", "fournissez",
    "joindre", "joint", "joindra", "joignez", "proposer", "proposera", "proposez", "exposer", "expose", "exposera",
    "exposez", "expliquer", "explique", "expliquera", "expliquez", "developper", "developpe", "developpera",
    "developpez", "demontrer", "demontre", "demontrera", "demontrez", "justifier", "justifie", "justifiera",
    "justifiez", "mentionner", "mentionne", "mentionnera", "mentionnez", "comprendre", "comprend", "comprendra",
    "comporter", "comporte", "comportera", "contenir", "contient", "contiendra", "faire", "fait", "fera",
    "apparaitre", "permettant", "permettre", "devra", "devront", "doit", "doivent", "demande", "demandee",
    "attendu", "attendue", "exige", "exigee", "manière", "maniere", "facon", "modalite", "modalites", "description",
    "presentation", "precision", "precisions", "detail", "details", "liste", "lister", "listez", "citer", "citez",
    "donner", "donnez", "identifier", "identifiez", "notice", "note", "fiche", "titre", "objet", "cours",
    "page", "pages", "maximum", "minimum", "caracteres", "mots", "lignes", "espaces", "compris", "comprises",
    "inclus", "incluses", "police", "taille", "format",
}
# Mots présents dans presque tout mémoire du BTP : ils restent des mots principaux de l'exigence (« une présentation
# de l'entreprise », « l'organisation du chantier » gardent leur sens), mais la règle « traitée » ne les compte pas
# quand l'exigence a au moins deux autres mots principaux : « la gestion des déchets du chantier » n'est pas traitée
# par une partie qui parle du chantier sans jamais nommer les déchets (`cles_traitement`).
_COURANTS_BTP = re.compile(r"\b(?:chantiers?|entreprises?)\b")


def cles(texte: str) -> list:
    """Les mots principaux d'une exigence, réduits à leur début (5 lettres : « déchets » ↔ « déchet »),
    sans mots vides ni mots qu'on trouve dans toute exigence. Au plus CLES_MAX, dans l'ordre du texte."""
    out = []
    for w in re.split(r"[^a-z0-9]+", _fold(texte)):
        if len(w) < 3 or w in _MOTS_VIDES or w in _GENERIQUES or w.isdigit():
            continue
        st = w[:5] if len(w) > 5 else w
        if st in _GENERIQUES:
            continue
        if st not in out:
            out.append(st)
        if len(out) >= CLES_MAX:
            break
    return out


def cles_traitement(texte: str) -> list:
    """Les mots principaux que la règle « traitée » cherche dans une partie : ceux de `cles`, sans « chantier » ni
    « entreprise » quand il en reste au moins deux autres (jamais une exigence ramenée à un seul mot)."""
    autres = cles(_COURANTS_BTP.sub(" ", _fold(texte)))
    return autres if len(autres) >= 2 else cles(texte)


def requis(k: int) -> int:
    """Mots principaux à retrouver dans une partie : tous s'il y en a un ou deux, sinon au moins la
    moitié, et au moins deux."""
    if k <= 2:
        return k
    return max(2, int(math.ceil(k / 2.0)))


_A_COMPLETER = re.compile(r"\[\s*a completer[^\]]*\]")


def _corpus(texte: str) -> str:
    """Texte d'une partie, replié, sans les « [À compléter : …] » (un trou ne traite rien)."""
    return _A_COMPLETER.sub(" ", _fold(texte or ""))


def _presents(corpus: str, ks: list) -> list:
    return [k for k in ks if re.search(r"(?<![a-z0-9])" + re.escape(k), corpus)]


# ── Repérage des exigences ───────────────────────────────────────────────────────────

_SUJ_CAND = (r"(?:le|les|chaque|tout|tous les) (?:candidats?|soumissionnaires?|concurrents?"
             r"|operateurs? economiques?)")
_SUJ_MEM = (r"(?:le|ce|son|leur|ledit) (?:memoire(?: technique| justificatif| explicatif)?|dossier technique"
            r"|offre technique|note (?:methodologique|technique|de presentation)|projet technique|document technique)")
_CONJ = ("presente|presentent|presentera|presenteront|precise|precisent|precisera|preciseront|decrit|decrivent|"
         "decrira|decriront|detaille|detaillent|detaillera|detailleront|indique|indiquent|indiquera|indiqueront|"
         "expose|exposent|exposera|exposeront|explique|expliquent|expliquera|expliqueront|developpe|developpent|"
         "developpera|developperont|demontre|demontrent|demontrera|demontreront|joint|joignent|joindra|joindront|"
         "fournit|fournissent|fournira|fourniront|mentionne|mentionnent|mentionnera|mentionneront|comprend|"
         "comprennent|comprendra|comprendront|comporte|comportent|comportera|comporteront|contient|contiennent|"
         "contiendra|contiendront|fait apparaitre|font apparaitre|fera apparaitre|feront apparaitre|repond|"
         "repondent|repondra|repondront|traite|traitent|traitera|traiteront|aborde|abordent|abordera|aborderont|"
         "identifie|identifient|identifiera|identifieront|specifie|specifient|specifiera|specifieront|justifie|"
         "justifient|justifiera|justifieront|propose|proposent|proposera|proposeront|s'engage|s'engagent|"
         "s'engagera|s'engageront|produit|produisent|produira|produiront|liste|listent|listera|listeront")
_INF = ("presenter|preciser|decrire|detailler|indiquer|exposer|expliquer|developper|demontrer|joindre|fournir|"
        "mentionner|comprendre|comporter|contenir|faire apparaitre|repondre|traiter|aborder|lister|identifier|"
        "specifier|justifier|proposer|produire|transmettre|renseigner|completer|apporter|s'engager|prevoir|"
        "garantir|decliner|exposer|definir|chiffrer|planifier|organiser")
_MODAL = (r"(?:devra|devront|doit|doivent|est tenu de|sont tenus de|est invite a|sont invites a|s'attachera a|"
          r"s'attacheront a|veillera a|veilleront a|est prie de|sont pries de|a l'obligation de|ont l'obligation de)")
_ADV = (r"(?:(?:notamment|egalement|obligatoirement|imperativement|clairement|en particulier|precisement|"
        r"explicitement|au minimum|a minima|aussi|en outre|par ailleurs|y)\s+)*")
_P_SUJET = re.compile(r"\b(?:" + _SUJ_CAND + "|" + _SUJ_MEM + r")\b(?P<gap>[^.;:!?]{0,70}?)\b(?P<verbe>"
                      + _MODAL + r"\s+" + _ADV + r"(?:" + _INF + r")|(?:" + _CONJ + r"))\b")
_GAP_NON = re.compile(r"\b(?:peut|peuvent|pourra|pourront|pourrait|libres?|possibilite|retenue?s?|attributaires?"
                      r"|titulaires?|pressentie?s?|admise?s?|ne|n'|qui|lorsqu|si|souhaite|souhaitent|interesse)\b|n'")
_P_IMPERSONNEL = re.compile(r"\bil (?:est|sera) (?:expressement |egalement |notamment |en outre )?"
                            r"(?P<verbe>demande|attendu|exige|souhaite|requis|impose)\b(?: (?:aux?|au) (?:candidats?|"
                            r"soumissionnaires?))?(?: (?:de|d'|que))?")
_P_APPARTIENT = re.compile(r"\bil appartient (?:au|aux) (?:candidats?|soumissionnaires?) (?:de |d')")
_P_ATTENTION = re.compile(r"\bune attention particuliere (?:sera|est) (?:portee|apportee|accordee)(?: (?:a|aux?|sur))?")
_P_FIGURER = re.compile(r"\b(?:doi(?:t|vent)|devr(?:a|ont)) (?:obligatoirement |imperativement )?(?:figurer|apparaitre)"
                        r" (?:dans|au sein) (?:du|le|son|leur) (?:memoire|offre|dossier)")
_IMPERATIFS = ("decrivez|presentez|precisez|indiquez|detaillez|joignez|expliquez|listez|justifiez|fournissez|exposez|"
               "proposez|demontrez|identifiez|developpez|citez|donnez|mentionnez|decrire|presenter|preciser|indiquer|"
               "detailler|joindre|expliquer|lister|justifier|fournir|exposer|proposer|demontrer|identifier|developper|"
               "citer|mentionner")
# Une question du cadre : « Question 2 : Décrivez… », « 2.1 Présentez… », « - Précisez… » ou « Décrivez… » seul.
_P_IMPERATIF = re.compile(r"(?:(?:question|q)\s*(?:n\s?[°o]\s*)?\d[\d.]*\s*[:.\-–—)]?\s*"
                          r"|\d{1,2}(?:\.\d{1,2}){0,3}[.)]?\s*[:\-–—]?\s*|[-–—•▪*]\s*)?(?P<verbe>" + _IMPERATIFS + r")\b"
                          # … suivi de ce qui est demandé (« Décrivez LA méthode »), jamais « Décrire ne suffit pas ».
                          r"(?=\s+(?:l'|d'|qu'|(?:le|la|les|un|une|des|du|votre|vos|son|sa|ses|leur|leurs|comment|"
                          r"pourquoi|quels?|quelles?|si|tout|toute|tous|toutes|chaque|ici|ci-dessous|en|dans|precisement|"
                          r"notamment|clairement|brievement|succinctement)\b))")

# Ce qui n'est pas du contenu du dossier de présentation : pièces administratives, prix, dépôt, forme.
_ADMIN = re.compile(
    r"\bdc ?[124]\b|\bdume\b|\bkbis\b|extrait k|\burssaf\b|attestations? (?:fiscales?|sociales?|d'assurances?|de "
    r"regularite|sur l'honneur|de vigilance)|assurances? (?:responsabilite|decennale|rc)\b|polices? d'assurance"
    r"|\brib\b|releve d'identite|acte d'engagement|\battri ?1\b|lettre de candidature|declaration (?:sur l'honneur|du "
    r"candidat)|pouvoirs? (?:du|de la) (?:signataire|personne)|habilitation (?:du|de la) (?:signataire|mandataire)"
    r"|\bsigne(?:e|s|es)?\b|signature|certificat (?:de signature|electronique)|bordereau|\bdpgf\b|\bbpu\b|\bdqe\b"
    r"|decomposition (?:du|de|des) prix|detail (?:quantitatif|estimatif)|sous-detail|\bprix\b|\bmontants?\b"
    r"|chiffres? d'affaires|capacites? (?:economiques?|financieres?|professionnelles?)|bilans? (?:comptables?|"
    r"financiers?)|liasses? fiscales?|langue francaise|redige(?:e|s|es)? en (?:langue )?francais|\beuros?\b"
    r"|format (?:pdf|word|docx|papier|numerique)|dematerialis|plateforme|profil d'acheteur|\bdepot\b|remise des "
    r"(?:offres?|plis)|copie de sauvegarde|\bplis?\b|date limite|heure limite|delai de validite|\bvisites?\b"
    r"|\bvariantes?\b|prestations? supplementaires? eventuelles?|\bpse\b|offres? (?:conformes?|completes?|regulieres?)"
    r"|candidats? (?:retenus?|attributaires?|"
    r"pressentis?)|\battributaires?\b|titulaire du marche|\bdc4\b|sous-traitants? (?:declares?|presentes?)")


_LIMITE_EXPR = re.compile(r"\([^)]*\)|\b\d[\d  .]*\s*(?:pages?|feuillets?|mots|caracteres|lignes?)\b"
                          r"|\bpolice\b[^,;.]*|\b(?:arial|calibri|times new roman|marianne|verdana)\b[^,;.]*")


def _limite_seule(objet: str) -> bool:
    """Ce qui est demandé ne fait que limiter la longueur ou la police (« au maximum 10 pages ») : c'est
    déjà dans « Ce que le dossier impose ». « l'encadrement du chantier (2 pages maximum) » demande bien
    quelque chose : l'encadrement."""
    low = _fold(objet or "")
    if not (_gn()._LIMIT_WORDS.search(low) or re.search(r"\bpolice\b|\bpages?\b|\bmots\b|\bcaracteres\b", low)):
        return False
    return not cles(_LIMITE_EXPR.sub(" ", low))


_JUSTIFIER_DE = re.compile(r"\bjustifi\w* (?:d'|de |du |des )")
_RUBRIQUE = re.compile(r"\b(?:article|chapitre)\s+\d{1,2}(?:\.\d{1,2})*\s*[-–—:.]?\s*(?P<t>[a-z][a-z' ,]{2,70})")
_RUBRIQUE_CANDIDATURE = re.compile(r"conditions? de participation|candidature|capacites?|justificatifs?|pieces? (?:a "
                                   r"fournir par|de la candidature|administratives)|selection des candidats"
                                   r"|recevabilite|situation juridique|habilitations?")


# Un titre qui nomme AUSSI l'offre ou le mémoire (« Présentation des candidatures et des offres », « 5.2 Contenu de
# l'offre ») n'est pas un article sur la candidature : le contenu du mémoire y est souvent décrit.
_RUBRIQUE_OFFRE = re.compile(r"\boffres?\b|\bmemoires?\b|\bplis?\b|projet technique|proposition technique")
# Un sous-titre numéroté en tête de ligne (« 5.1 Pièces de la candidature », « 5.2 Contenu de l'offre »).
_SOUS_RUBRIQUE = re.compile(r"[ \t]*\d{1,2}(?:\.\d{1,2}){1,3}\.?\s*[-–—:.)]?\s*(?P<t>[a-z][a-z' ,]{2,70})")
_TITRE_COUPE = re.compile(r"\b(?:de|des|du|la|le|les|et|ou|a|au|aux|en|pour|sur|d'|l')\s*$")


def _titre_candidature(t: str) -> Optional[bool]:
    """True : titre sur la candidature ; False : sur l'offre ou le mémoire (même s'il nomme aussi les candidatures) ;
    None : ni l'un ni l'autre."""
    if _RUBRIQUE_OFFRE.search(t):
        return False
    if _RUBRIQUE_CANDIDATURE.search(t):
        return True
    return None


def sous_titre_candidature(low: str, pos: int, debuts: list) -> bool:
    """La position `pos` du texte replié `low` est-elle sous un titre sur la CANDIDATURE ? `debuts` : débuts de ligne
    triés. Le titre le plus proche décide : un sous-titre numéroté (« 5.2 Contenu de l'offre ») avant l'article qui
    l'englobe ; un sous-titre ni sur l'une ni sur l'autre laisse décider l'article. Le titre est lu sur SA ligne
    (prolongée d'une ligne s'il est coupé après « de », « des »…), jamais dans la phrase qui le suit. Partagé avec
    l'entretien chantier (entretien_chantier._sous_article_candidature)."""
    import bisect
    lo = max(0, pos - 4000)

    def fin(x: int) -> int:
        i = bisect.bisect_right(debuts, x)
        return debuts[i] - 1 if i < len(debuts) else len(low)

    def titre(a: int, b: int) -> str:
        t = low[a:min(b, fin(a))]
        if _TITRE_COUPE.search(t) and fin(a) < len(low):
            t = (t + " " + low[fin(a) + 1:fin(fin(a) + 1)])[:90]
        return t
    titres = [(m.start(), titre(m.start("t"), m.end("t")), True) for m in _RUBRIQUE.finditer(low, lo, pos)]
    for d in debuts[bisect.bisect_left(debuts, lo):]:
        if d >= pos:
            break
        m = _SOUS_RUBRIQUE.match(low, d)
        if not m:
            continue
        ligne = low[d:fin(d)].strip()
        if len(ligne) > 90 or re.search(r"[.;:,]$", ligne):
            continue                        # une phrase numérotée (« 9.1 Le candidat devra… ») n'est pas un titre
        titres.append((d, titre(m.start("t"), m.end("t")), False))
    titres.sort(key=lambda x: x[0])
    for _d, t, article in reversed(titres):
        v = _titre_candidature(t)
        if v is not None:
            return v
        if article:
            return False
    return False


def _rubrique_candidature(p, pos: int) -> bool:
    """La phrase est-elle dans un article sur la CANDIDATURE (conditions de participation, capacités, pièces
    administratives) ? Ce qu'il demande se prouve par des pièces, pas dans le dossier de présentation. Un article
    « Présentation des candidatures et des offres » n'en est pas un ; sous lui, « 5.1 Pièces de la candidature »
    l'est, « 5.2 Contenu de l'offre » non (sous_titre_candidature)."""
    return sous_titre_candidature(p.low, pos, _unites(p).debuts)


def _exclue(low: str) -> bool:
    gn = _gn()
    if _ADMIN.search(low) or _JUSTIFIER_DE.search(low):
        return True
    if gn._CADRE_MENTION.search(low) and gn._OBLIG.search(low):
        return True                       # « le cadre de réponse doit être utilisé » : déjà dit plus haut
    return False


_TETE_OBJET = re.compile(
    r"^(?:\s|,|:|;|-)*(?:(?:notamment|egalement|en particulier|clairement|precisement|obligatoirement|imperativement|"
    r"de maniere (?:detaillee|precise|claire)|en detail|ci-apres|ci-dessous|aussi|en outre|par ailleurs|"
    r"dans (?:son|le|leur) (?:memoire|offre|dossier)(?: technique)?|a l'appui de (?:son|leur) offre|"
    r"au sein de (?:son|leur) memoire(?: technique)?|au candidat|aux candidats|au soumissionnaire|de|d'|que|qu')"
    r"(?:\s|,|:|-)*)+")


def _objet(p, a: int, e: int) -> tuple:
    """Ce qui est demandé : le texte de [a, e) sans ses mots d'introduction. (début, texte)."""
    low = p.low
    m = _TETE_OBJET.match(low, a, e)
    s = m.end() if m else a
    while s < e and p.flat[s] in " ,:;-–—":
        s += 1
    return s, p.flat[s:e].strip().rstrip(" .;:")


_MARQUE_LISTE = re.compile(r"\s*(?:[-–—•▪◦*·>]|o(?=\s)|[a-h][).]|[ivx]{1,4}[).]|\d{1,2}[).](?!\d)|\d{1,2}\.\d{1,2}[.)]?)\s+")


_TITRE_LIGNE = re.compile(r"(?:article|chapitre|titre|section|annexe|partie)\s+[0-9ivx]{1,4}\b|\d{1,2}(?:\.\d{1,2})*[.)]?\s+\S")


class _Unites:
    """Découpe une pièce en unités : fins de phrase (. ; ! ? suivis d'un blanc), retours à la ligne suivis
    d'une marque de liste (« - », « a) », « 1) »…), et retours à la ligne qui ferment un TITRE (ligne courte
    sans ponctuation finale, « Article 5 - Contenu de l'offre ») ou qui en ouvrent un. Un retour à la ligne
    ordinaire (mise en page d'un PDF) ne coupe pas une phrase."""

    def __init__(self, p):
        import bisect
        self.p, self._bisect = p, bisect
        coupes = {c + 1 for c in p.cuts}
        br = p.breaks
        for i, n in enumerate(br):
            if _MARQUE_LISTE.match(p.low, n + 1):
                coupes.add(n + 1)
                continue
            debut = br[i - 1] + 1 if i else 0
            ligne = p.flat[debut:n].strip()
            suite = p.flat[n + 1:n + 2]
            fin = br[i + 1] if i + 1 < len(br) else len(p.flat)
            suivante = p.low[n + 1:fin].strip()
            titre_avant = (0 < len(ligne) <= 70 and not re.search(r"[,;:(\-–—]$|\b(?:de|du|des|la|le|les|et|ou|a|en|au|aux"
                                                                 r"|d'|l'|un|une|pour|par|sur|dans)$", _fold(ligne))
                           and (suite[:1].isupper() or suite[:1].isdigit()))
            titre_apres = bool(_TITRE_LIGNE.match(suivante)) and len(suivante) <= 90
            if titre_avant or titre_apres or ligne.endswith(":"):
                coupes.add(n + 1)
        self.starts = sorted(x for x in coupes if 0 < x < len(p.flat))
        self.breakset = set(p.breaks)
        self.cutset = set(p.cuts)
        self.debuts = [0] + [n + 1 for n in p.breaks]       # débuts de ligne (titres, sous-titres)

    def phrase(self, a: int, b: int) -> tuple:
        """(début, phrase) de l'unité qui contient [a, b), bornée à PHRASE_MAX autour de [a, b)."""
        s, _e = self.bornes(a)
        _s2, e = self.bornes(max(a, b - 1))
        return _clip_phrase(self.p, s, e, a, b)

    def bornes(self, pos: int) -> tuple:
        i = self._bisect.bisect_right(self.starts, pos)
        s = self.starts[i - 1] if i else 0
        e = self.starts[i] if i < len(self.starts) else len(self.p.flat)
        return s, e

    def suivante(self, e: int) -> Optional[tuple]:
        if e >= len(self.p.flat):
            return None
        return self.bornes(e)

    def debut_de_ligne(self, pos: int) -> bool:
        """Début du texte, d'une ligne ou d'une phrase (« Décrivez… » ouvre une question du cadre)."""
        return pos == 0 or (pos - 1) in self.breakset or (pos - 1) in self.cutset


_UNITES = {}


def _unites(p) -> "_Unites":
    """Les unités d'une pièce, calculées une fois par construction de grille (clé : l'objet pièce)."""
    u = _UNITES.get(id(p))
    if u is None or u.p is not p:
        if len(_UNITES) > 64:
            _UNITES.clear()
        u = _UNITES[id(p)] = _Unites(p)
    return u


def _scope_exigences(P: list) -> list:
    prio = [p for p in P if p.type in (dp.REGLEMENT, dp.CADRE)]
    if prio:
        return prio + [p for p in P if p.type == dp.AUTRE]
    return [p for p in P if p.type not in (dp.BORDEREAU, dp.ACTE_ENGAGEMENT)] or P


_MENTION_CANDIDAT = re.compile(r"\bcandidats?\b|\bsoumissionnaires?\b|\bmemoire\b|dans (?:son |leur |l')offre")


def _ajouter(out: list, vues: set, p, s: int, phrase: str, texte: str, origine: str, intro: str = "") -> None:
    key = _fold(_flat(phrase))
    if not key or key in vues:
        return
    for x in out:                      # une phrase déjà contenue dans une autre (ou l'inverse) : une seule fois
        k2 = x["_cle"]
        if key in k2 or k2 in key:
            return
    vues.add(key)
    texte = _couper(texte or phrase)
    if not cles(texte):
        return                          # « un mémoire technique » : rien de précis n'est demandé
    out.append({"texte": texte, "phrase": phrase, "intro": intro, "source": _source(p), "origine": origine,
                "_cle": key, "_pos": (p.idx, s)})


def _items_liste(U: "_Unites", e: int, intro: str, out: list, vues: set, text: str) -> int:
    """Les éléments d'une liste ouverte par une phrase qui finit par « : ». Renvoie leur nombre."""
    p = U.p
    n, cur = 0, U.suivante(e)
    inline = None
    while cur is not None and n < LISTE_MAX:
        s, e2 = cur
        seg = p.flat[s:e2]
        m = _MARQUE_LISTE.match(p.low, s)
        if m:
            a = m.end()
        elif inline is None and n == 0 and seg.rstrip().endswith(";"):
            inline, a = True, s        # liste en ligne : « … comprendra : a ; b ; c. »
        elif inline:
            a = s
        else:
            break
        a2, obj = _objet(p, a, e2)
        st, phrase = _clip_phrase(p, a2, e2)
        if _demande_facultative(p.low[s:e2], 0):
            phrase = ""                  # « - à titre facultatif, des photographies » : pas une exigence
        obj = _sans_le_facultatif(obj)
        if phrase and len(phrase) >= 4 and not _exclue(_fold(phrase)) and _guard(text, phrase, min_len=4):
            _ajouter(out, vues, p, st, phrase, obj, REPERAGE, intro=intro)
            n += 1
        if inline and not seg.rstrip().endswith(";"):
            break
        cur = U.suivante(e2)
    return n


# « Le candidat n'est pas tenu de… », « il n'est pas demandé… » : une phrase niée n'est pas une exigence.
_NIEE = re.compile(r"\b(?:n'est pas|ne sont pas|n'a pas|ne sera pas|n'y a pas)\b[^.;]{0,25}"
                   r"(?:demande|exige|tenu|attendu|oblig)")
# « Le candidat peut présenter… », « est libre de… » : une faculté n'est pas une exigence (phrase proposée par l'IA,
# que le repérage n'aurait pas retenue : son sujet n'est suivi d'aucun verbe d'exigence).
_FACULTE = re.compile(r"\b(?:" + _SUJ_CAND + "|" + _SUJ_MEM + r")\b[^.;:!?]{0,70}?\b(?:peut|peuvent|pourra|pourront"
                      r"|pourrait|est libre|sont libres|a la possibilite|ont la possibilite|a la faculte|ont la faculte)\b")
# « à titre facultatif », « de manière (façon) facultative », « facultativement » : ce qui est facultatif n'est pas
# exigé. Le mot seul (« (annexes facultatives) », « la visite est facultative ») ne rend pas la demande facultative.
_FACULTATIF = re.compile(r"\b(?:a titre facultatif|de (?:maniere|facon) facultative|facultativement)\b")
_MOT = re.compile(r"[a-z]{2,}")
_FIN_COORDINATION = re.compile(r"[\s,;]*(?:\b(?:et|ou|ainsi que)\b)?[\s,;]*$")


def _demande_facultative(low: str, fin: int) -> bool:
    """La DEMANDE elle-même est-elle facultative ? `fin` : fin du verbe d'exigence dans `low` (0 : élément de liste).
    Oui quand l'expression qualifie le sujet ou le verbe (« à titre facultatif, le candidat présentera… »,
    « présentera, à titre facultatif, ses certificats ») ou TOUT l'objet (« … un planning, à titre facultatif. »).
    Non quand un élément facultatif est coordonné à d'autres (« la méthodologie et, de manière facultative, des
    photographies ») : seul cet élément sort du libellé (`_sans_le_facultatif`)."""
    if _FACULTATIF.search(low, 0, fin):
        return True
    m = _FACULTATIF.search(low, fin)
    if m is None:
        return False
    gap = low[fin:m.start()]
    mm = _MARQUE_LISTE.match(gap) if fin == 0 else None
    gap = gap[mm.end():] if mm else gap
    t = _TETE_OBJET.match(gap)
    if not _MOT.search(gap[t.end():] if t else gap):
        return True                         # juste après le verbe, ou en tête de l'élément de liste
    return not _MOT.search(low[m.end():])   # en fin de phrase : tout l'objet est facultatif


def _sans_le_facultatif(obj: str) -> str:
    """Le libellé sans l'élément facultatif coordonné (« la méthodologie de dépose, les moyens humains affectés et,
    de façon facultative, un reportage photographique » → « la méthodologie de dépose, les moyens humains
    affectés »). Le texte du dossier, coupé, jamais réécrit ; la phrase citée reste entière."""
    m = _FACULTATIF.search(_fold(obj or ""))
    if m is None:
        return obj
    head = _FIN_COORDINATION.sub("", obj[:m.start()]).strip()
    return head if cles(head) else obj


def _fin_du_verbe(low: str) -> int:
    """Fin du premier verbe d'exigence de `low` (0 s'il n'y en a pas : un élément de liste)."""
    fins = [m.end() for m in (rx.search(low) for rx in (_P_SUJET, _P_IMPERSONNEL, _P_APPARTIENT, _P_ATTENTION,
                                                         _P_FIGURER)) if m]
    return min(fins) if fins else 0


def _annonce(p, s: int) -> Optional[tuple]:
    """L'unité qui annonce la liste dont l'unité commençant à `s` est un élément (« Le candidat joindra à son mémoire
    technique : » puis « - les fiches techniques… »), ou None."""
    U = _unites(p)
    cur = s
    for _i in range(LISTE_MAX + 1):
        if cur <= 0:
            return None
        ps, pe = U.bornes(cur - 1)
        prec = p.flat[ps:pe].rstrip()
        if prec.endswith(":"):
            return ps, pe
        if _MARQUE_LISTE.match(p.low, ps) or prec.endswith(";"):
            cur = ps
            continue
        return None
    return None


def _ecartee_comme_au_reperage(p, pos: int) -> bool:
    """Une phrase PROPOSÉE par l'IA passe les mêmes exclusions que le repérage (contrat C2.2) : relue dans son
    unité du dossier — et, pour un élément de liste, avec la phrase qui annonce la liste (comme le repérage) —, elle
    est écartée si elle est niée, facultative (le sujet « peut », la demande « à titre facultatif »), sous un article
    sur la candidature, ou si elle vient du CCTP ou du CCAP sans parler du candidat ni du mémoire."""
    s, e = _unites(p).bornes(pos)
    low = p.low[s:e]
    an = _annonce(p, s)
    intro = p.low[an[0]:an[1]] if an else ""
    ctx = f"{intro} {low}" if intro else low
    if _NIEE.search(ctx):
        return True
    if _demande_facultative(low, _fin_du_verbe(low)) or (intro and _demande_facultative(intro, _fin_du_verbe(intro))):
        return True
    sujets = list(_P_SUJET.finditer(ctx))
    if any(_GAP_NON.search(m.group("gap") or "") for m in sujets):
        return True                         # « le candidat retenu devra… », « le candidat peut… présenter » : écartée
    if not sujets and _FACULTE.search(ctx):
        return True                         # « le candidat peut présenter… » : aucun verbe d'exigence après le sujet
    if _rubrique_candidature(p, pos):
        return True
    return p.type in (dp.CCTP, dp.CCAP) and not _MENTION_CANDIDAT.search(ctx)


def _reperer(P: list, text: str) -> list:
    out, vues = [], set()
    for p in _scope_exigences(P):
        U = _unites(p)
        faits = set()
        candidats = []
        for rx, kind in ((_P_SUJET, "sujet"), (_P_IMPERSONNEL, "impersonnel"), (_P_APPARTIENT, "appartient"),
                         (_P_ATTENTION, "attention"), (_P_FIGURER, "figurer")):
            for m in rx.finditer(p.low):
                candidats.append((m.start(), m.end(), kind, m))
        if p.type == dp.CADRE or re.search(r"\bquestion\b", p.low[:2000]):
            for m in _P_IMPERATIF.finditer(p.low):
                a = m.start()
                if U.debut_de_ligne(a):
                    candidats.append((a, m.end(), "imperatif", m))
        candidats.sort(key=lambda x: x[0])
        for a, b, kind, m in candidats:
            s, e = U.bornes(a)
            if (s, e) in faits:
                continue
            if kind == "sujet":
                if _GAP_NON.search(m.group("gap") or ""):
                    continue
                if p.type in (dp.CCTP, dp.CCAP) and not _MENTION_CANDIDAT.search(p.low[s:e]):
                    continue
            if kind == "imperatif":
                s = a
            if _rubrique_candidature(p, a):
                continue
            low = p.low[s:e]
            if _NIEE.search(low) or _demande_facultative(low, max(0, b - s)):
                continue                         # niée, ou facultative (« à titre facultatif ») : pas une exigence
            if _exclue(low):
                continue
            phrase_s, phrase = _clip_phrase(p, s, e, a, b)
            if not phrase or not _guard(text, phrase):
                continue
            o_s, obj = _objet(p, b, e)
            obj = _sans_le_facultatif(obj)
            annonce = bool(re.fullmatch(r"(?:les |des )?(?:elements?|points?|informations?|pieces?|documents?|rubriques?"
                                        r"|themes?|sujets?) (?:suivante?s?|ci-apres|ci-dessous)", _fold(obj or "")))
            if annonce:
                obj = ""                         # « les éléments suivants : » n'est qu'une annonce
            if p.flat[s:e].rstrip().endswith(":"):
                n = _items_liste(U, e, phrase, out, vues, text)
                faits.add((s, e))
                if n:
                    continue
                if not obj:
                    continue
            elif annonce:
                # « … comprendra les éléments ci-dessous. » : une annonce, jamais une exigence ; la liste qui suit
                # (s'il y en a une) est lue comme après « : », sinon chaque phrase suivante est repérée seule.
                _items_liste(U, e, phrase, out, vues, text)
                faits.add((s, e))
                continue
            if _limite_seule(obj):
                faits.add((s, e))
                continue
            _ajouter(out, vues, p, phrase_s, phrase, obj, REPERAGE)
            faits.add((s, e))
    out.sort(key=lambda x: x["_pos"])
    return out[:EXIGENCES_MAX]


def _libelle_de_phrase(p, s: int, e: int) -> str:
    """Le libellé d'une phrase proposée par l'IA : l'objet après le verbe d'exigence quand on le trouve,
    sinon la phrase elle-même. Jamais un mot de l'IA."""
    low = p.low
    for rx in (_P_SUJET, _P_IMPERSONNEL, _P_APPARTIENT, _P_ATTENTION, _P_FIGURER, _P_IMPERATIF):
        m = rx.search(low, s, e)
        if m:
            _o, obj = _objet(p, m.end(), e)
            obj = _sans_le_facultatif(obj)
            if obj and cles(obj):
                return obj
    return p.flat[s:e].strip().rstrip(" .;:")


def _proposees_ia(details: dict, P: list, text: str, out: list) -> None:
    raw = (details or {}).get("exigences_memoire")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return
    gn = _gn()
    vues = {x["_cle"] for x in out}
    ok, ko = 0, 0
    scope = [p for p in P if p.type not in (dp.BORDEREAU, dp.ACTE_ENGAGEMENT)] or P
    for x in list(raw)[:IA_EXIGENCES_MAX * 2]:
        ex = x.get("extrait") or x.get("phrase") if isinstance(x, dict) else x
        if not isinstance(ex, str) or not ex.strip():
            continue
        verifie = _guard(text, ex)
        if not verifie:
            ko += 1
            continue
        vp, vpos, orig = gn._locate(verifie, scope)
        if vp is None:
            ko += 1
            continue
        if _ecartee_comme_au_reperage(vp, vpos):
            ko += 1                          # retrouvée, mais ce n'est pas une exigence : comptée comme un écart
            continue
        ok += 1
        low = _fold(orig)
        libelle = _libelle_de_phrase(vp, vpos, vpos + len(orig))
        if _exclue(low) or _limite_seule(libelle):
            continue
        before = len(out)
        _ajouter(out, vues, vp, vpos, orig, libelle, IA)
        if len(out) > before and sum(1 for y in out if y["origine"] == IA) >= IA_EXIGENCES_MAX:
            break
    try:
        from app.services import llm_qualite as _q
        if ok or ko:
            _q.noter_citations(ok, ko)
    except Exception:       # noqa: BLE001
        pass


def exigences(P: list, text: str, details: Optional[dict] = None) -> dict:
    """Les exigences du dossier : repérées sans IA, puis celles que l'IA a proposées (phrase retrouvée mot
    pour mot), dans l'ordre du dossier. {liste: [{id, texte, phrase, intro, source, origine}], compteurs}."""
    out = _reperer(P, text)
    _proposees_ia(details or {}, P, text, out)
    out.sort(key=lambda x: x["_pos"])
    out = out[:EXIGENCES_MAX]
    liste = []
    for i, x in enumerate(out, 1):
        liste.append({"id": f"e{i}", "texte": x["texte"], "phrase": x["phrase"], "intro": x.get("intro") or "",
                      "source": x["source"], "origine": x["origine"]})
    return {"liste": liste}


# ── Choix de l'utilisateur, compteurs ───────────────────────────────────────────────

def _choix(x: dict) -> str:
    return ((x or {}).get("choix_utilisateur") or {}).get("choix") or ""


def refresh(ex: Optional[dict]) -> Optional[dict]:
    if not isinstance(ex, dict):
        return ex
    lst = [x for x in ex.get("liste") or [] if isinstance(x, dict)]
    ex["compteurs"] = {"total": sum(1 for x in lst if _choix(x) != "ecarte"),
                       "reperees": sum(1 for x in lst if x.get("origine") == REPERAGE),
                       "proposees_ia": sum(1 for x in lst if x.get("origine") == IA),
                       "ajoutees": sum(1 for x in lst if x.get("origine") == UTILISATEUR),
                       "retirees": sum(1 for x in lst if _choix(x) == "ecarte"),
                       "traitees_selon_vous": sum(1 for x in lst if _choix(x) == "traitee")}
    return ex


def appliquer_choix(grille: dict, kind: str, element_id: str, choix: str, when: str = "") -> dict:
    """NOUVELLE grille où l'exigence (kind « exigence ») ou la question (« question ») porte le choix :
    exigence « ecarte » (ce n'est pas une exigence : hors du compte), « traitee » (vous la dites traitée),
    « annule » ; question « ecarte » (retirée de la liste), « annule ». ValueError (message affichable)."""
    if not isinstance(grille, dict):
        raise ValueError("Aucune grille de notation pour ce marché : ré-analysez le dossier.")
    g = copy.deepcopy(grille)
    if kind == "exigence":
        if choix not in CHOIX_EXIGENCE:
            raise ValueError("Choix inconnu.")
        bloc = g.get("exigences") if isinstance(g.get("exigences"), dict) else None
    elif kind == "question":
        if choix not in CHOIX_QUESTION:
            raise ValueError("Choix inconnu.")
        bloc = g.get("questions_acheteur") if isinstance(g.get("questions_acheteur"), dict) else None
    else:
        raise ValueError("Élément inconnu.")
    if bloc is None:
        raise ValueError("Cette liste n'existe pas encore pour ce marché : relisez le dossier.")
    x = next((y for y in bloc.get("liste") or [] if isinstance(y, dict) and y.get("id") == element_id), None)
    if x is None:
        raise ValueError("Cet élément n'existe plus : rechargez la page.")
    if choix == "annule":
        x.pop("choix_utilisateur", None)
    else:
        x["choix_utilisateur"] = {"choix": choix, "le": when}
    if kind == "exigence":
        refresh(bloc)
    return g


def ajouter_exigence(grille: dict, text: str, phrase: str, when: str = "") -> dict:
    """Ajoute une exigence que l'utilisateur a lue dans le dossier : sa phrase doit y être retrouvée mot
    pour mot (citation_guard), sinon ValueError. Le libellé est tiré de la phrase."""
    if not isinstance(grille, dict):
        raise ValueError("Aucune grille de notation pour ce marché : ré-analysez le dossier.")
    ph = _flat(phrase)[:400]
    if len(ph) < 12:
        raise ValueError("Collez la phrase du dossier, telle qu'elle est écrite (au moins quelques mots).")
    if not text:
        raise ValueError("Le dossier du marché n'est plus lisible : importez-le de nouveau.")
    verifie = _guard(text, ph)
    if not verifie:
        raise ValueError("Adjugo ne retrouve pas cette phrase dans le dossier du marché : collez-la telle qu'elle "
                         "est écrite.")
    gn = _gn()
    P = gn._pieces(text)
    vp, vpos, orig = gn._locate(verifie, P)
    g = copy.deepcopy(grille)
    bloc = g.get("exigences") if isinstance(g.get("exigences"), dict) else {"liste": []}
    lst = [x for x in bloc.get("liste") or [] if isinstance(x, dict)]
    key = _fold(_flat(orig or verifie))
    if any(_fold(_flat(x.get("phrase"))) == key for x in lst):
        raise ValueError("Cette exigence est déjà dans la liste.")
    libelle = _libelle_de_phrase(vp, vpos, vpos + len(orig)) if vp is not None else verifie
    n = 1 + sum(1 for x in lst if str(x.get("id") or "").startswith("u"))
    lst.append({"id": f"u{n}", "texte": _couper(libelle), "phrase": orig or verifie, "intro": "",
                "source": _source(vp) if vp is not None else "", "origine": UTILISATEUR,
                "ajoutee_le": when})
    bloc["liste"] = lst
    g["exigences"] = refresh(bloc)
    return g


def carry_over(previous: Optional[dict], fresh: Optional[dict], text: Optional[str] = None) -> Optional[dict]:
    """Ré-analyse ou relecture : les choix sur une exigence ou une question de même phrase sont repris, et
    les exigences ajoutées par l'utilisateur restent si leur phrase est encore dans le dossier (`text` : le
    texte intégral du nouveau dossier ; sans lui, elles ne sont pas reprises : une exigence affichée porte
    toujours une phrase retrouvée dans le dossier)."""
    if not isinstance(fresh, dict) or not isinstance(previous, dict):
        return fresh
    for k in ("exigences", "questions_acheteur"):
        old = previous.get(k) if isinstance(previous.get(k), dict) else {}
        new = fresh.get(k) if isinstance(fresh.get(k), dict) else None
        if new is None:
            continue
        ch = {}
        for x in old.get("liste") or []:
            if isinstance(x, dict) and x.get("choix_utilisateur"):
                ch[_cle_element(x)] = x["choix_utilisateur"]
        for x in new.get("liste") or []:
            c = ch.get(_cle_element(x))
            if c:
                x["choix_utilisateur"] = dict(c)
        if k == "exigences":
            vues = {_cle_element(x) for x in new.get("liste") or []}
            for x in old.get("liste") or []:
                if not (isinstance(x, dict) and x.get("origine") == UTILISATEUR) or _cle_element(x) in vues:
                    continue
                if text and _guard(text, x.get("phrase") or ""):
                    new.setdefault("liste", []).append(dict(x))
            refresh(new)
    return fresh


def _cle_element(x: dict) -> str:
    ph = x.get("phrase") or ""
    if not ph and x.get("phrases"):
        ph = " ".join(y.get("phrase") or "" for y in x["phrases"] if isinstance(y, dict))
    return (x.get("code") or "") + "|" + _fold(_flat(ph))


# ── « Traitée » : la règle explicite (remplace toute note de conformité) ──────────────

def traitement(grille: Optional[dict], parties: list) -> dict:
    """Pour chaque exigence : traitée (et dans quelle partie), à traiter, traitée selon vous, retirée.
    parties : [{id, titre, texte}] — le texte que le LECTEUR voit (jamais le brouillon d'un autre).
    Règle (REGLE_TRAITEE) : une exigence est traitée quand le texte d'une partie, sans ses « [À compléter] »,
    reprend assez de ses mots principaux (cles / requis). La meilleure partie l'emporte (plus de mots
    retrouvés, puis la première du plan). Sans IA."""
    bloc = (grille or {}).get("exigences") if isinstance(grille, dict) else None
    lst = [x for x in (bloc or {}).get("liste") or [] if isinstance(x, dict)]
    corpus = [(p.get("id"), p.get("titre") or "", _corpus(p.get("texte") or "")) for p in parties or []
              if (p.get("texte") or "").strip()]
    out, traitees, total, manquantes = [], 0, 0, []
    for x in lst:
        ch = _choix(x)
        row = {"id": x.get("id"), "texte": x.get("texte") or "", "phrase": x.get("phrase") or "",
               "intro": x.get("intro") or "", "source": x.get("source") or "", "origine": x.get("origine") or "",
               "statut": A_TRAITER, "partie": None, "choix": ch}
        if ch == "ecarte":
            row["statut"] = RETIREE
            out.append(row)
            continue
        total += 1
        ks = cles_traitement(x.get("texte") or "") or cles_traitement(x.get("phrase") or "")
        need = requis(len(ks))
        best = None
        for pid, titre, c in corpus:
            hits = _presents(c, ks)
            if need and len(hits) >= need and (best is None or len(hits) > best[0]):
                best = (len(hits), pid, titre)
        if best is not None:
            row["statut"] = TRAITEE
            row["partie"] = {"section_id": best[1], "titre": best[2]}
        elif ch == "traitee":
            row["statut"] = TRAITEE_SELON_VOUS
        if row["statut"] in (TRAITEE, TRAITEE_SELON_VOUS):
            traitees += 1
        else:
            manquantes.append({"id": row["id"], "texte": row["texte"]})
        out.append(row)
    return {"liste": out, "total": total, "traitees": traitees, "manquantes": manquantes,
            "message": message_traitement(traitees, total), "message_manque": message_manque(manquantes),
            "regle": REGLE_TRAITEE}


def message_traitement(n: int, m: int) -> str:
    if not m:
        return ""
    if n == m:
        return ("L'exigence repérée est traitée dans le dossier" if m == 1
                else f"Les {m} exigences repérées sont traitées dans le dossier")
    return f"{n} exigence{'s' if n > 1 else ''} traitée{'s' if n > 1 else ''} sur {m}"


def message_manque(manq: list) -> str:
    if not manq:
        return ""
    if len(manq) <= 3:
        return "Il manque : " + ", ".join(
            f"« {x['texte']} »" for x in manq) + "."
    return f"Il en manque {len(manq)} : voir la liste."


# ── L'environnement, en information neutre ───────────────────────────────────────────

_ENV = re.compile(r"environnement|ecolog|developpement durable|bilan carbone|empreinte carbone|\bcarbone\b|decarbon"
                  r"|gaz a effet de serre|emissions? de (?:co2|gaz)|biodiversite|economie circulaire|\breemploi\b"
                  r"|recycl|valorisation des dechets|gestion des dechets|tri des dechets|\bdechets\b|biosource"
                  r"|performance energetique|sobriete|transition ecologique|nuisances")
_NOTATION = re.compile(r"crit[e]res?|sous-crit|ponder|\bnote(?:e|es|s)?\b|notation|bareme|appreci|evalu|\bjuge"
                       r"|\bpoints?\b|\d\s*%")


def environnement(lines: list, P: list) -> dict:
    """Où l'environnement apparaît dans la notation : critères et sous-critères dont le nom ou la phrase en
    parle, puis phrases de la partie « critères » du règlement. Neutre : aucun conseil, aucune note."""
    gn = _gn()
    lieux, vues = [], set()

    def _ajout(kind, libelle, poids, phrase, source):
        k = _fold(_flat(phrase or libelle))
        if not k or k in vues or len(lieux) >= 6:
            return
        vues.add(k)
        lieux.append({"type": kind, "libelle": _flat(libelle)[:160], "poids": _flat(poids)[:40],
                      "phrase": phrase or "", "source": source or ""})
    for ln in lines or []:
        if not isinstance(ln, dict) or (ln.get("choix_utilisateur") or {}).get("choix") == "ecarte":
            continue
        if _ENV.search(_fold(ln.get("critere") or "")) or _ENV.search(_fold(ln.get("phrase") or "")):
            _ajout("critere", ln.get("critere"), ln.get("poids_retenu") or ln.get("poids"), ln.get("phrase"),
                   ln.get("source"))
        for sc in ln.get("sous_criteres") or []:
            if _ENV.search(_fold(sc.get("critere") or "")) or _ENV.search(_fold(sc.get("phrase") or "")):
                _ajout("sous_critere", sc.get("critere"), sc.get("poids"), sc.get("phrase"), sc.get("source"))
    rc = [p for p in P if p.type == dp.REGLEMENT] or P
    for p in rc:
        for z0, z1 in gn._crit_zones(p):
            for m in _ENV.finditer(p.low, z0, z1):
                s, e = _unites(p).bornes(m.start())
                # Seulement une phrase qui parle de la notation (« la valeur environnementale est appréciée au
                # regard du bilan carbone ») : une exigence ou une clause d'exécution n'est pas « dans la note ».
                if not _NOTATION.search(p.low[s:e]):
                    continue
                _st, ph = _unites(p).phrase(m.start(), m.end())
                if ph:
                    _ajout("phrase", "", "", ph, _source(p))
    dans = bool(lieux)
    return {"dans_la_note": dans, "message": MSG_ENV if dans else "", "lieux": lieux}


# ── Répondre seul ET en groupement, ou dans plusieurs groupements (R2142-21) ──────────

_INTERDIT = re.compile(r"interdit|\bne (?:peut|peuvent|pourra|pourront|saurait|sauraient|doit|doivent)\b|n'est pas "
                       r"(?:autorise|admis|possible|permis)|pas autorise|non autorise|\brefuse|\bexclu|n'est pas admis"
                       r"|ne sera pas acceptee?|ne seront pas acceptees?|irrecevable|sous peine|pas possible"
                       r"|est prohibee?|s'interdit")
_PERMIS = re.compile(r"n'interdit pas|n'est pas interdit|ne s'oppose pas|(?:est|sont) (?:autorisee?s?|admise?s?|"
                     r"possibles?|permise?s?)\b(?! a condition)|peu(?:t|vent) presenter plusieurs|sans restriction"
                     r"|est libre|sont libres")
_SEUL_GRP = re.compile(r"(?:a la fois|en meme temps|simultanement)\s+(?:en (?:qualite|tant) (?:de|que)\s+)?"
                       r"(?:candidats?|soumissionnaires?|operateurs?(?: economiques?)?)\s+(?:individuels?|isoles?|"
                       r"seuls?)[^.;]{0,90}?(?:membres?|groupements?)"
                       r"|(?:individuellement|a titre individuel|isolement)\s+et\s+(?:en (?:qualite de )?membres? d'un "
                       r"|en |au sein d'un |comme membres? d'un )?groupement"
                       r"|candidats? individuels? et (?:de |en qualite de )?membres? d'un (?:ou plusieurs )?groupement")
_PLUS_GRP = re.compile(r"membres? de plusieurs groupements|membres? de plus d'un groupement"
                       r"|(?:a|dans|au sein de) plusieurs groupements")
_MANDAT = re.compile(r"mandataires? de (?:plus d'un|plusieurs) groupements?")


def candidatures_multiples(P: list) -> dict:
    """Ce que le règlement interdit sur les candidatures multiples, avec la phrase : répondre à la fois seul
    et en groupement, être membre de plusieurs groupements (R2142-21), être chef de file de plusieurs
    groupements. Une phrase qui le permet n'est jamais lue comme une interdiction."""
    scope = [p for p in P if p.type in (dp.REGLEMENT, dp.AUTRE)] or P
    out = {"seul_et_groupement": None, "plusieurs_groupements": None, "mandataire_unique": None, "messages": []}
    for p in scope:
        for key, rx in (("seul_et_groupement", _SEUL_GRP), ("plusieurs_groupements", _PLUS_GRP),
                        ("mandataire_unique", _MANDAT)):
            if out[key] is not None:
                continue
            for m in rx.finditer(p.low):
                s, e = _unites(p).bornes(m.start())
                low = p.low[s:e]
                if _PERMIS.search(low) or not _INTERDIT.search(low):
                    continue
                _st, ph = _unites(p).phrase(m.start(), m.end())
                if ph:
                    out[key] = {"phrase": ph, "source": _source(p)}
                    break
    for key, msg in (("seul_et_groupement", MSG_SEUL_ET_GROUPEMENT), ("plusieurs_groupements", MSG_PLUSIEURS_GROUPEMENTS),
                     ("mandataire_unique", MSG_MANDATAIRE)):
        if out[key] is not None:
            out["messages"].append({"code": key, "message": msg, "phrase": out[key]["phrase"],
                                    "source": out[key]["source"]})
    return out


# ── L'intelligence artificielle dans le règlement ─────────────────────────────────────

_IA = re.compile(r"intelligence artificielle|\bia\b|\bias\b|\bchatgpt\b|chat gpt|\bllm\b|modeles? de langage"
                 r"|agents? conversationnels?|generateurs? (?:de|automatiques? de) (?:texte|contenu)s?"
                 r"|outils? de generation (?:automatique )?(?:de )?(?:texte|contenu)s?|redaction automatique"
                 r"|redige(?:e|s|es)? automatiquement|generee?s? automatiquement")
_IA_INTERDIT = re.compile(r"sans (?:recours|recourir|utilis|l'aide|l'usage|faire appel|l'emploi)|interdit|proscrit|exclu"
                          r"|\bne (?:doit|doivent|devra|devront|peut|peuvent|pourra|pourront)\b(?: pas| en aucun cas)?"
                          r"(?: etre)? (?:recourir|utilis|faire appel|genere|redige|produit|elabore|issu|realise)"
                          r"|n'est pas (?:autorise|admis|accepte)|pas (?:autorise|admis)|ne sera pas (?:accepte|admis)"
                          r"|\brefus|\brejet|irreguli|s'interdit|s'abstien")
# Une phrase qui PERMET l'IA (« n'est pas interdit », « est autorisé, sans restriction ») n'est jamais lue comme une
# interdiction : l'expression est retirée avant de chercher une interdiction dans la phrase.
_IA_PERMIS = re.compile(r"n'(?:est|sont) pas (?:interdite?s?|proscrite?s?|exclue?s?|prohibee?s?)|n'interdit pas"
                        r"|ne (?:proscrit|exclut|prohibe) pas|ne s'oppose pas|(?<!n')(?:est|sont) (?:autorisee?s?|admise?s?|"
                        r"permise?s?|acceptee?s?)\b(?! (?:a condition|sous reserve|que si|uniquement|seulement))"
                        r"|sans restriction|(?<!ne )peu(?:t|vent) (?:recourir|utiliser|faire appel|s'aider)")
_IA_SIGNALER = re.compile(r"\b(?:signal|indiqu|declar|mentionn|precis)\w*")
_IA_OFFRE = re.compile(r"memoire|offre|redig|redaction|reponse|candidat|soumissionnaire|dossier|document")
_IA_DECLARER = re.compile(r"(?:indique|indiquer|indiquera|precise|preciser|precisera|declare|declarer|declarera|"
                          r"signale|signaler|signalera|mentionne|mentionner|mentionnera|fait apparaitre|faire "
                          r"apparaitre)\b[^.;]{0,80}(?:recours|utilis|usage|aide|emploi)")


def _suite_signale(p, e: int) -> bool:
    """La phrase qui suit un « ; » demande-t-elle de le signaler (« … n'est pas interdit ; le candidat le signale ») ?"""
    if not p.flat[:e].rstrip().endswith(";"):
        return False
    nxt = _unites(p).suivante(e)
    return bool(nxt and re.search(r"\b(?:le|l')\s*(?:signal|indiqu|declar|mentionn|precis)\w*", p.low[nxt[0]:nxt[1]]))


def mention_ia(P: list) -> dict:
    """Le règlement (ou le cadre, l'avis) parle-t-il d'intelligence artificielle ? Les phrases, et leur
    nature : « interdit » (sans recours à…), « declarer » (indiquer l'usage), « permis » (« n'est pas interdit »,
    « est autorisé » : jamais lue comme une interdiction, et aucune question à l'acheteur), « mention » sinon. Le
    mode « sans IA » est alors proposé pour ce dossier (au choix de l'entreprise quand le règlement l'admet)."""
    scope = [p for p in P if p.type in (dp.REGLEMENT, dp.CADRE, dp.AUTRE)] or P
    phrases, nature, vues = [], "", set()
    for p in scope:
        for m in _IA.finditer(p.low):
            s, e = _unites(p).bornes(m.start())
            low = p.low[s:e]
            _st, ph = _unites(p).phrase(m.start(), m.end())
            k = _fold(ph)
            if not ph or k in vues or not _IA_OFFRE.search(low):
                continue
            vues.add(k)
            permis = bool(_IA_PERMIS.search(low))
            reste = _IA_PERMIS.sub(" ", low) if permis else low
            if _IA_INTERDIT.search(reste):
                n = "interdit"
            elif _IA_DECLARER.search(reste) or (permis and _IA_SIGNALER.search(reste)):
                n = "declarer"
            elif permis and _suite_signale(p, e):
                n = "declarer"               # « n'est pas interdit ; le candidat le signale dans son offre »
                _st, ph2 = _unites(p).phrase(m.start(), _unites(p).suivante(e)[1])
                ph = ph2 or ph               # la phrase montrée va jusqu'à la demande de le signaler
            else:
                n = "permis" if permis else "mention"
            phrases.append({"phrase": ph, "source": _source(p), "nature": n})
            if len(phrases) >= 4:
                break
        if len(phrases) >= 4:
            break
    if phrases:
        natures = {x["nature"] for x in phrases}
        nature = next(x for x in ("interdit", "declarer", "mention", "permis") if x in natures)
    msg = {"interdit": MSG_IA_INTERDIT, "declarer": MSG_IA_DECLARER, "mention": MSG_IA_MENTION,
           "permis": MSG_IA_PERMIS}.get(nature, "")
    return {"mentionne": bool(phrases), "nature": nature, "phrases": phrases, "message": msg,
            "propose_sans_ia": bool(phrases)}


# ── Dates écrites dans le dossier ─────────────────────────────────────────────────────

_MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
         "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
_DATE_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b")
_DATE_LET = re.compile(r"\b(1er|\d{1,2})\s+(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre"
                       r"|novembre|decembre)\s+(\d{4})\b")


def _dates_pos(low: str) -> list:
    """[(début, fin, date)] des dates écrites dans `low`, dans l'ordre du texte."""
    out = []
    for m in _DATE_NUM.finditer(low):
        try:
            y = int(m.group(3))
            y = y + 2000 if y < 100 else y
            out.append((m.start(), m.end(), date(y, int(m.group(2)), int(m.group(1)))))
        except ValueError:
            continue
    for m in _DATE_LET.finditer(low):
        try:
            j = 1 if m.group(1) == "1er" else int(m.group(1))
            out.append((m.start(), m.end(), date(int(m.group(3)), _MOIS[m.group(2)], j)))
        except (ValueError, KeyError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def _dates(low: str) -> list:
    return [d for _a, _b, d in _dates_pos(low)]


# Après « N jours avant la date limite de remise des offres » : « , soit le 05/12/2026 » (« c'est-à-dire le »,
# « à savoir le », « soit jusqu'au ») donne la date des QUESTIONS, écrite ; « , fixée au 15/12/2026 » (« prévue le »,
# « des offres du ») donne celle de la REMISE. Sans l'une ou l'autre introduction, la date n'est classée nulle part.
_INTRO_DATE_QUESTIONS = re.compile(r"\b(?:soit|c'est-a-dire|c-a-d|a savoir|autrement dit)\b")
_INTRO_DATE_REMISE = re.compile(r"\b(?:fixee?s?|prevue?s?|arretee?s?|programmee?s?|indiquee?s?|mentionnee?s?)\b"
                                r"|^\W*(?:(?:des|de l'|de vos) (?:offres?|plis)\W*)?(?:du|le)\W*$")


def _dates_apres_le_delai(apres: str) -> tuple:
    """(dates des questions, dates de remise) écrites après le délai « N jours avant la date limite de remise »."""
    q, r, last = [], [], 0
    for a, b, d in _dates_pos(apres):
        gap = apres[last:a]
        if _INTRO_DATE_QUESTIONS.search(gap):
            q.append(d)
        elif _INTRO_DATE_REMISE.search(gap):
            r.append(d)
        last = b
    return q, r


def _fr(d: date) -> str:
    return d.strftime("%d/%m/%Y")


_REMISE = re.compile(r"date (?:et heure )?limites? (?:de |d')?(?:remise|reception|depot) (?:des |de l'|de vos )?(?:offres?|plis)"
                     r"|(?:remise|reception|depot) des (?:offres|plis)[^.;]{0,60}?(?:au plus tard|avant"
                     r"|jusqu'au)|(?:offres|plis) (?:sont|seront|doivent etre|devront etre) (?:remis|deposes|"
                     r"transmis|recus)[^.;]{0,80}?(?:au plus tard|avant|jusqu'au)")
_REPORT = re.compile(r"\breport|initialement|modifi|prolong|decale|repousse")


def dates_remise(P: list) -> list:
    """Dates limites de remise des offres ÉCRITES dans le règlement ou l'avis : [(date, phrase, source)],
    une par date différente."""
    scope = [p for p in P if p.type in (dp.REGLEMENT, dp.AUTRE)] or P
    vues, out = set(), []
    for p in scope:
        for m in _REMISE.finditer(p.low):
            s0, e0 = _unites(p).bornes(m.start())
            if _REPORT.search(p.low[s0:e0]):
                return []                       # une date reportée : deux dates ne se contredisent pas
            s, e = _unites(p).bornes(m.start())
            ds = _dates(p.low[m.start():e])
            if not ds:
                continue
            d = ds[0]
            lu = p.low[s:e]
            rel = _Q_RELATIF.search(lu) if _Q_SUJET.search(lu) else None
            if rel and rel.start() <= m.start() - s <= rel.end() and d in _dates_apres_le_delai(lu[rel.end():])[0]:
                continue                        # « … avant la date limite de remise des offres, soit le 07/12/2026 »
                                                # : la date des QUESTIONS, pas celle de la remise
            if d in vues:
                continue
            vues.add(d)
            _st, ph = _unites(p).phrase(m.start(), m.end())
            if ph:
                out.append((d, ph, _source(p)))
    return out


_Q_SUJET = re.compile(r"\bquestions?\b|demandes? (?:de |d')(?:renseignements?|precisions?|complements? "
                      r"d'information|informations?|eclaircissements?)|renseignements? complementaires?"
                      r"|precisions? complementaires?")
_Q_POSER = re.compile(r"\b(?:poser|posees?|poses|adresser|adressees?|transmettre|transmises?|formuler|formulees?"
                      r"|envoyer|envoyees?|faire parvenir|parvenir|deposer|deposees?|recues?|recevables?|"
                      r"presenter|presentees?|peu(?:t|vent) (?:etre )?(?:posees?|adressees?))\b")
_Q_RELATIF = re.compile(r"(\d{1,2})\s+jours?\s+(francs?\s+|calendaires?\s+|ouvres?\s+|ouvrables?\s+)?(?:au moins\s+)?"
                        r"avant\s+(?:la\s+)?(?:date\s+(?:limite\s+)?(?:de\s+|d')?(?:remise|reception|depot)|remise|"
                        r"limite|date limite)")
_Q_TEMPS = re.compile(r"au plus tard|avant le|jusqu'au|jusqu'a|\d{1,2}\s+jours?")


def date_limite_questions(P: list, remises: Optional[list] = None) -> Optional[dict]:
    """La date limite pour poser ses questions à l'acheteur, si le règlement la donne : la phrase, la date
    écrite (ou le délai « N jours avant la date limite de remise »), et une date calculée seulement si le
    délai est en jours simples et qu'une seule date de remise est écrite dans le dossier (dit comme tel)."""
    scope = [p for p in P if p.type in (dp.REGLEMENT, dp.AUTRE)] or P
    for p in scope:
        for m in _Q_SUJET.finditer(p.low):
            s, e = _unites(p).bornes(m.start())
            low = p.low[s:e]
            if not (_Q_POSER.search(low) and _Q_TEMPS.search(low)):
                continue
            if re.search(r"\breponses?\b", low) and not re.search(r"\b(?:poser|posees?|adresser|adressees?|formuler|"
                                                                     r"formulees?|transmettre|transmises?)\b", low):
                continue
            _st, ph = _unites(p).phrase(m.start(), m.end())
            if not ph:
                continue
            rel = _Q_RELATIF.search(low)
            # « … au plus tard 6 jours avant la date limite de remise des offres, fixée au 15/12/2026 » : la date
            # écrite APRÈS le délai est celle de la REMISE des offres. La date des questions est écrite avant le délai
            # (« au plus tard le 05/12/2026, soit 10 jours avant… ») ou après lui introduite par « soit le »,
            # « c'est-à-dire le » (« … 10 jours avant la date limite de remise, soit le 05/12/2026 ») : écrite dans le
            # règlement, rien n'est calculé. Une date après le délai sans l'une ni l'autre introduction : rien n'est
            # calculé, la phrase est montrée.
            q_apres, r_apres = _dates_apres_le_delai(low[rel.end():]) if rel else ([], [])
            ds = (_dates(low[:rel.start()]) or q_apres) if rel else _dates(low)
            out = {"phrase": ph, "source": _source(p), "date": ds[0].isoformat() if ds else None,
                   "jours_avant": None, "type_jours": "", "date_calculee": None, "message": ""}
            if ds:
                out["message"] = f"Date limite pour poser vos questions : {_fr(ds[0])}, écrite dans le règlement."
                return out
            if rel:
                n = int(rel.group(1))
                kind = _fold(rel.group(2) or "").strip()
                out["jours_avant"], out["type_jours"] = n, kind
                out["message"] = ("Date limite pour poser vos questions : " + rel.group(0).strip()
                                  + " (phrase du règlement ci-dessous).")
                rem = [x[0] for x in (remises if remises is not None else dates_remise(P))]
                if not rem:
                    apres = sorted(set(r_apres))
                    rem = apres if len(apres) == 1 else []   # la date de remise écrite dans la même phrase
                if len(rem) == 1 and (not kind or kind.startswith("calendaire")):
                    d = rem[0] - timedelta(days=n)
                    out["date_calculee"] = d.isoformat()
                    out["message"] = (f"Date limite pour poser vos questions : le {_fr(d)}, calculée par Adjugo "
                                      f"({n} jours avant la date limite de remise du {_fr(rem[0])}) : vérifiez-la.")
                return out
    return None


# ── Les questions à poser à l'acheteur ────────────────────────────────────────────────

def _q(code: str, sujet: str, question: str, phrases: list, motif: str = "", origine: str = REPERAGE) -> dict:
    return {"code": code, "sujet": sujet, "question": question, "motif": motif, "origine": origine,
            "phrases": [x for x in phrases if x.get("phrase")][:3]}


def _num(v) -> str:
    return _gn()._fmt_total(float(v))


def _poids_hors_grille(g: dict, P: list) -> bool:
    """Un poids est-il écrit dans la partie « critères » du règlement HORS des phrases des critères et des
    sous-critères retrouvés ? (Adjugo a peut-être manqué un critère : pas de question à l'acheteur.)"""
    gn = _gn()
    connues = []
    for ln in g.get("criteres") or []:
        if ln.get("phrase"):
            connues.append(_fold(_flat(ln["phrase"])))
        for sc in ln.get("sous_criteres") or []:
            if sc.get("phrase"):
                connues.append(_fold(_flat(sc["phrase"])))
    connues = [c for c in connues if len(c) >= 4]
    for p in [x for x in P if x.type == dp.REGLEMENT] or P:
        zones = gn._crit_zones(p)
        if not zones:
            continue
        spans = []
        for c in connues:
            i = p.low.find(c)
            while i >= 0:
                spans.append((i, i + len(c)))
                i = p.low.find(c, i + 1)
        for z0, z1 in zones:
            for _v, _u, _raw, a, b in gn._weights_in(p.flat[z0:z1]):
                a, b = a + z0, b + z0
                if not any(s0 <= a and b <= s1 for s0, s1 in spans):
                    return True
    return False


def questions_acheteur(g: dict, P: list, text: str, details: Optional[dict] = None) -> dict:
    """Questions à poser à l'acheteur quand le dossier se contredit ou reste flou, chacune avec la phrase en
    cause, puis la date limite des questions. Repérées SANS IA ; l'IA de l'analyse peut en proposer
    (details.questions_acheteur) : gardées seulement si leur phrase est retrouvée mot pour mot et que
    chaque nombre de la question est écrit dans cette phrase."""
    out = []
    crit = [ln for ln in g.get("criteres") or [] if isinstance(ln, dict)]
    cpt = g.get("compteurs") or {}
    ct = g.get("controle_total") or {}
    # 1. Les poids des critères ne font pas le total annoncé (tous retrouvés, rien d'autre dans la zone).
    plan = [ln for ln in crit if ln.get("dans_le_plan")]
    if (ct.get("statut") == "ecart" and ct.get("attendu") is not None and ct.get("total") is not None
            and not int(cpt.get("a_verifier") or 0) and plan
            and all(ln.get("poids_source") == "reglement" for ln in plan) and not _poids_hors_grille(g, P)):
        u = "%" if ct.get("unite") == "%" else "points"
        ph = [{"phrase": ln.get("phrase"), "source": ln.get("source")} for ln in plan]
        if g.get("total_annonce"):
            ph.insert(0, {"phrase": g["total_annonce"].get("phrase"), "source": g["total_annonce"].get("source")})
        out.append(_q("total_poids", "Pondération des critères",
                      f"Les poids des critères indiqués dans le règlement font {_num(ct['total'])} {u} au total, et non "
                      f"{_num(ct['attendu'])} {u}. Pouvez-vous confirmer la pondération des critères ?", ph))
    # 2. Les sous-critères ne font pas le poids de leur critère.
    for ln in crit:
        cs = ln.get("controle_sous") or {}
        if cs.get("statut") == "ecart" and cs.get("total") is not None and cs.get("attendu") is not None:
            u = "%" if cs.get("unite") == "%" else "points"
            ph = [{"phrase": ln.get("phrase"), "source": ln.get("source")}] + [
                {"phrase": sc.get("phrase"), "source": sc.get("source")} for sc in ln.get("sous_criteres") or []]
            out.append(_q("total_sous", "Pondération des sous-critères",
                          f"Les sous-critères de « {ln.get('critere')} » font {_num(cs['total'])} {u} au total, alors "
                          f"que le critère vaut {_num(cs['attendu'])} {u}. Pouvez-vous confirmer leur répartition ?",
                          ph))
    c = g.get("contraintes") or {}
    cadre = c.get("cadre") or {}
    # 3. Le cadre de réponse est imposé mais ne figure pas dans le dossier.
    if c.get("fichier_impose") and not cadre.get("fourni") and (cadre.get("obligatoire") or {}).get("phrase"):
        ob = cadre["obligatoire"]
        out.append(_q("cadre_absent", "Cadre de réponse",
                      "Le règlement impose un cadre de réponse qui ne figure pas parmi les pièces du dossier. Pouvez-vous "
                      "indiquer où le trouver, ou le transmettre ?", [ob],
                      motif="À poser si vous ne le trouvez pas sur la plateforme de l'acheteur."))
    # 4. Deux limites différentes pour le mémoire entier.
    docs = [x for x in c.get("limites") or [] if isinstance(x, dict) and not x.get("objet")
            and x.get("type") in ("pages", "mots", "caracteres", "lignes") and isinstance(x.get("valeur"), (int, float))]
    for kind in ("pages", "mots", "caracteres", "lignes"):
        vals = {}
        for x in docs:
            if x["type"] != kind:
                continue
            if re.search(r"annexe|\bhors\b|compris|inclus|\bpar\b|chaque|\bcv\b|reference", _fold(x.get("phrase") or "")):
                continue
            vals.setdefault(x["valeur"], x)
        if len(vals) >= 2:
            a, b = sorted(vals)[:2]
            unite = {"pages": "pages", "mots": "mots", "caracteres": "caractères", "lignes": "lignes"}[kind]
            out.append(_q("limites", "Longueur du dossier de présentation",
                          f"Le dossier indique deux limites différentes pour le mémoire : {_num(a)} {unite} et "
                          f"{_num(b)} {unite}. Laquelle s'applique ?", [vals[a], vals[b]]))
            break
    # 5. La visite est dite obligatoire à un endroit, facultative à un autre.
    vis = c.get("visite") if isinstance(c.get("visite"), dict) else None
    if vis and vis.get("phrase"):
        fac = _visite_facultative(P)
        if fac is not None:
            out.append(_q("visite", "Visite du site",
                          "Le dossier dit à un endroit que la visite est obligatoire, et à un autre qu'elle ne l'est "
                          "pas. Pouvez-vous préciser si la visite est obligatoire ?",
                          [{"phrase": vis.get("phrase"), "source": vis.get("source")}, fac]))
    # 6. Deux dates limites de remise différentes (sans pièce modificative qui les expliquerait).
    rem = dates_remise(P)
    modif = any(re.search(r"modif|rectif|additif|erratum|report", _fold(p.nom)) for p in P)
    if len(rem) >= 2 and not modif:
        (d1, p1, s1), (d2, p2, s2) = sorted(rem)[:2]
        out.append(_q("date_remise", "Date limite de remise",
                      f"Le dossier donne deux dates limites de remise des offres : le {_fr(d1)} et le {_fr(d2)}. "
                      "Laquelle fait foi ?", [{"phrase": p1, "source": s1}, {"phrase": p2, "source": s2}]))
    # 7. L'intelligence artificielle est évoquée sans règle claire.
    ia = g.get("ia") or {}
    if ia.get("mentionne") and ia.get("nature") == "mention":
        out.append(_q("ia", "Intelligence artificielle",
                      "Le règlement évoque l'intelligence artificielle sans dire ce qui est admis. Un outil d'aide à "
                      "la rédaction, dont le candidat relit, corrige et valide chaque phrase, est-il admis ?",
                      [{"phrase": x.get("phrase"), "source": x.get("source")} for x in ia.get("phrases") or []]))
    _questions_ia(details or {}, P, text, out)
    out = out[:QUESTIONS_MAX]
    for i, x in enumerate(out, 1):
        x["id"] = f"q{i}"
    dl = date_limite_questions(P, rem)
    message = MSG_QUESTIONS + (f", avant le {_fr(date.fromisoformat(dl['date']))}." if dl and dl.get("date") else ".")
    return {"liste": out, "date_limite": dl, "message": message if out else "",
            "message_vide": MSG_SANS_QUESTION if not out else ""}


_FACULT_VISITE = re.compile(r"\bvisites?\b[^.;]{0,60}?(?:facultatives?|n'est pas obligatoire|ne sont pas obligatoires|"
                            r"non obligatoires?|libres?|conseillee?s?|recommandee?s?)|pas de visite obligatoire")


def _visite_facultative(P: list) -> Optional[dict]:
    for p in P:
        for m in _FACULT_VISITE.finditer(p.low):
            s, e = _unites(p).bornes(m.start())
            if re.search(r"medical|maintenance|entretien|reception", p.low[s:e]):
                continue
            _st, ph = _unites(p).phrase(m.start(), m.end())
            if ph:
                return {"phrase": ph, "source": _source(p)}
    return None


_CHIFFRES = re.compile(r"\d+(?:[.,]\d+)?")


def _questions_ia(details: dict, P: list, text: str, out: list) -> None:
    raw = details.get("questions_acheteur")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return
    gn = _gn()
    deja = {_fold(_flat(y.get("phrase"))) for x in out for y in x.get("phrases") or []}
    n = 0
    for x in list(raw)[:IA_QUESTIONS_MAX * 2]:
        if not isinstance(x, dict) or n >= IA_QUESTIONS_MAX:
            continue
        q = _flat(x.get("question"))[:300]
        if len(q) < 15 or not q.endswith("?"):
            continue
        ex = x.get("extraits") if isinstance(x.get("extraits"), (list, tuple)) else [x.get("extrait")]
        phrases = []
        for e in ex[:2]:
            v = _guard(text, e) if isinstance(e, str) else ""
            if not v:
                continue
            vp, _vpos, orig = gn._locate(v, P)
            if vp is not None:
                phrases.append({"phrase": orig, "source": _source(vp)})
        if not phrases or any(_fold(_flat(y["phrase"])) in deja for y in phrases):
            continue
        dispo = set(_CHIFFRES.findall(" ".join(_fold(y["phrase"]) for y in phrases)))
        if set(_CHIFFRES.findall(_fold(q))) - dispo:
            continue                     # un nombre de la question n'est écrit dans aucune phrase : écartée
                                         # (des nombres entiers, comparés un à un : « 1 » n'est pas dans « 10 »)
        out.append(_q("ia_proposee", "Point à éclaircir", q, phrases, origine=IA))
        n += 1


# ── Tout ensemble (appelé par grille_notation.build_grille) ───────────────────────────

def construire(g: dict, P: list, text: str, details: Optional[dict] = None) -> dict:
    """Ajoute à la grille (déjà construite : critères, sous-critères, contraintes) ce que le dossier demande.
    Ne lève jamais : un repérage qui échoue laisse sa rubrique vide."""
    details = details if isinstance(details, dict) else {}
    try:
        g["exigences"] = refresh(exigences(P, text, details))
    except Exception:       # noqa: BLE001 — repérage facultatif, l'analyse payée ne casse jamais
        g["exigences"] = refresh({"liste": []})
    for key, fn in (("environnement", lambda: environnement(g.get("criteres") or [], P)),
                    ("candidatures_multiples", lambda: candidatures_multiples(P)),
                    ("ia", lambda: mention_ia(P))):
        try:
            g[key] = fn()
        except Exception:   # noqa: BLE001
            g[key] = None
    try:
        g["questions_acheteur"] = questions_acheteur(g, P, text, details)
    except Exception:       # noqa: BLE001
        g["questions_acheteur"] = {"liste": [], "date_limite": None, "message": "", "message_vide": ""}
    return g


def public(g: dict) -> dict:
    """Vue des partenaires du groupement (lecture seule) : exigences (texte, phrase, retirée ou non),
    environnement, candidatures multiples, IA. Les questions à l'acheteur restent au chef de file, qui les
    pose ; aucun choix daté, aucun nom de fichier au-delà du libellé de la pièce. Grille d'avant la vague 5
    (sans ces rubriques) : rien — l'écran ne dit pas « aucune exigence » d'un dossier qui n'a pas été relu."""
    if not isinstance(g.get("exigences"), dict):
        return {}
    ex = g.get("exigences") if isinstance(g.get("exigences"), dict) else {}
    env = g.get("environnement") if isinstance(g.get("environnement"), dict) else {}
    cm = g.get("candidatures_multiples") if isinstance(g.get("candidatures_multiples"), dict) else {}
    ia = g.get("ia") if isinstance(g.get("ia"), dict) else {}
    return {
        "exigences": [{"id": x.get("id"), "texte": str(x.get("texte") or "")[:LIBELLE_MAX + 2],
                       "phrase": str(x.get("phrase") or "")[:400], "retiree": _choix(x) == "ecarte"}
                      for x in ex.get("liste") or [] if isinstance(x, dict)][:EXIGENCES_MAX + 10],
        "environnement": {"dans_la_note": bool(env.get("dans_la_note")), "message": env.get("message") or "",
                          "lieux": [{"libelle": x.get("libelle", ""), "poids": x.get("poids", ""),
                                     "phrase": x.get("phrase", "")} for x in env.get("lieux") or []][:6]},
        "candidatures_multiples": [{"code": x.get("code"), "message": x.get("message"), "phrase": x.get("phrase")}
                                   for x in cm.get("messages") or [] if isinstance(x, dict)],
        "ia": {"mentionne": bool(ia.get("mentionne")), "nature": ia.get("nature") or "",
               "message": MSG_IA_PARTENAIRE if ia.get("mentionne") else "",
               "phrases": [{"phrase": x.get("phrase", "")} for x in ia.get("phrases") or []][:4]},
    }
