"""
« À relire » (rédaction, vague 2 — A0 de l'étude, §6.4), SANS IA.

Doctrine (étude §7, règles 1 à 3) : un fait ne vient jamais de l'IA, et le dossier de l'acheteur
n'appuie JAMAIS une phrase sur l'entreprise. Ici, dans chaque phrase qui parle de l'entreprise,
on repère :
  • les chiffres (avec leur unité : « 33 % », « 12 compagnons », « sous 24 h », « 2015 ») ;
  • les nombres écrits en lettres (« douze compagnons », « zéro accident ») ;
  • les certifications et qualifications (« ISO 14001 », « Qualibat 1312 », « RGE », « certifiés ») ;
  • les noms propres (« Mairie de Lorient », « PEFC ») ;
  • le matériel (« nacelle », « échafaudage », « mini-pelle »…) ;
et on renvoie comme « à relire » tout fait ABSENT des sources de l'entreprise (savoir-faire,
profil, équipe, chiffrage, ou texte écrit par l'utilisateur lui-même), avec le message
« Adjugo ne trouve pas d'où vient ce fait : relisez-le. »

Qui parle de quoi (étude §6.5, appliqué dès A0) : une phrase parle de l'entreprise si elle
contient « nous », « notre », « nos » ou le nom de l'entreprise. Sinon, elle parle du marché
SEULEMENT si elle rapporte ce que demande une pièce du dossier ou l'acheteur (« Le CCTP prévoit… »,
« Selon le règlement, … », « Le maître d'ouvrage impose… » : un sujet qui désigne une pièce ou
l'acheteur ET un verbe d'exigence). Dans une partie sur les moyens, les références ou la qualité,
c'est la seule exception. Ailleurs, une phrase qui décrit le lieu ou l'opération (« Le site
comprend… », « La commune souhaite… ») parle aussi du marché ; mais « Le marché sera exécuté par
15 compagnons » ou « Le site sera sécurisé par 4 agents » parlent de l'entreprise. Dans le doute :
phrase sur l'entreprise (le côté le plus strict).

Tableaux : une ligne est contrôlée en entier (ses cases ne sont pas jetées) ; un nombre seul dans
une case prend pour unité le libellé de la ligne (« Compagnons couvreurs | 15 » : 15 compagnons).
Noms propres : en tête de phrase ou de case, deux mots à majuscule au moins (« Paul Durand »,
« Vinci Construction ») ; « M. », « Mme », « Dr »… ne coupent pas la phrase.

RIEN n'est jamais marqué comme bon (aucun libellé positif avant la vague 3) : ce module ne rend
QUE des faits à relire. Une invention sans chiffre, nom ni certification passe : on le dit.
"""
import hashlib
import re
import unicodedata

from app.services.dce_pieces import fold as _fold_same     # repli de MÊME longueur (positions)

MESSAGE = "Adjugo ne trouve pas d'où vient ce fait : relisez-le."
A_RELIRE = "a_relire"
RELU = "relu_par_vous"

CHIFFRE = "chiffre"
EN_LETTRES = "nombre_en_lettres"
CERTIFICATION = "certification"
NOM_PROPRE = "nom_propre"
MATERIEL = "materiel"

RESTE = "reste"            # faits au-delà de MAX_FAITS : comptés (et bloquants), pas détaillés
MAX_FAITS = 2000           # garde-fou de stockage : au-delà, un seul élément « reste » les compte
PHRASE_MAX = 300
MSG_RESTE = ("Et {n} autres faits à relire, non détaillés : découpez ou raccourcissez cette partie pour les "
             "voir.")


def fold(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").replace("‘", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


# ── Découpage en phrases (Markdown simple : titres, listes, tableaux) ───────────────────

_TODO = re.compile(r"\[\s*[ÀAà]\s+compl[ée]ter[^\]]*\]", re.IGNORECASE)
# Renvois internes : extraits [S1] et, depuis la vague 3, faits numérotés [F3], [P1], [E1], [C1], [G1]
# (app/services/faits_sources.py) — jamais des faits, retirés avant le repérage.
_CITE = re.compile(r"\[\s*[FSPECG]\s*\d[^\]]{0,40}\]")
_MD = re.compile(r"\*\*|__|`|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)")


# Titre de civilité ou initiale (« M. », « Mme », « Dr. », « J. ») : jamais une fin de phrase.
_ABREV = re.compile(r"(?:^|[\s(«\"'])(?:M|MM|Mme|Mmes|Mlle|Mlles|Me|Mes|Dr|Pr|Mgr|St|Ste|[A-ZÀ-Ý])\.$")
CASE = " ; "               # séparateur des cases d'une ligne de tableau (ligne contrôlée en entier)


def _couper(line: str) -> list:
    """Phrases d'une ligne : coupe après « . ! ? ; », jamais après un titre ou une initiale."""
    out = []
    for piece in re.split(r"(?<=[.!?;])\s+(?=\S)", line):
        if out and _ABREV.search(out[-1]):
            out[-1] = out[-1] + " " + piece
        else:
            out.append(piece)
    return out


def phrases(texte: str) -> list:
    """[(phrase, est_titre, est_ligne_de_tableau)] dans l'ordre du texte. Les passages « [À compléter …] »
    et les renvois « [S1] » sont retirés (ce ne sont pas des faits). Une ligne de tableau est UNE
    phrase (ses cases jointes par « ; ») : un nombre seul dans une case n'est jamais perdu."""
    out = []
    for raw in str(texte or "").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or re.match(r"^\|?\s*:?-{2,}[-:|\s]*$", line):
            continue
        titre = bool(re.match(r"^#{1,6}\s", line))
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+", "", line)
        tableau = line.startswith("|") and line.count("|") >= 2
        if tableau:
            cells = [_MD.sub("", _CITE.sub("", _TODO.sub(" ", c))).strip() for c in line.strip("|").split("|")]
            line = CASE.join(c for c in cells if c)
        line = _TODO.sub(" ", line)
        line = _CITE.sub("", line)
        line = _MD.sub("", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        if titre or tableau:
            out.append((line, titre, tableau))
            continue
        for ph in _couper(line):
            ph = ph.strip()
            if len(ph) >= 3 or re.search(r"\d", ph):
                out.append((ph, False, False))
    return out


# ── De qui parle la phrase ────────────────────────────────────────────────────────────

_ENTREPRISE = re.compile(r"\b(?:nous|notre|nos|l'entreprise|la societe|notre societe|le candidat|"
                         r"notre groupement|le groupement|nos equipes|notre equipe)\b")
# Une pièce du dossier ou l'acheteur, en sujet (« Le CCTP… », « Le maître d'ouvrage… »).
_PIECE = (r"(?:cctp|ccap|ccag|rc\b|reglement(?: de (?:la )?consultation)?|dossier de (?:la )?consultation|dce\b|"
          r"cahier des (?:charges|clauses (?:techniques|administratives) particulieres)|programme fonctionnel|"
          r"maitre d'ouvrage|maitre d'oeuvre|maitrise d'ouvrage|maitrise d'oeuvre|acheteur|pouvoir adjudicateur)")
_DET = r"(?:le |la |les |l'|ce |cette )?"
# … et un verbe d'exigence (ce que la pièce ou l'acheteur demande) peu après le sujet.
_EXIGE = re.compile(r"\b(?:prevoi\w*|prevu\w*|impos\w*|exig\w*|demand\w*|prescri\w*|fix(?:e|ent|es|ee|ees)|"
                    r"precise\w*|indiqu\w*|requier\w*|requis\w*|stipul\w*|mentionn\w*|attend\w*|souhait\w*|"
                    r"defini\w*|decri\w*|limite\w*|interdi\w*|autorise\w*)\b")
_MARCHE_PIECE = re.compile(r"^" + _DET + _PIECE + r"(?P<suite>.{0,90})")
_MARCHE_SELON = re.compile(r"^(?:selon|d'apres|comme (?:le |la |l')?(?:prevoit|precise|indique|exige))\s+"
                           + _DET + _PIECE + r"\b")
# Hors des parties sur l'entreprise : le lieu ou l'opération, décrits (jamais « exécuté par… »).
_LIEU = (r"(?:site|batiments? existants?|batiment|commune|ville|mairie|collectivite|departement|region|"
         r"marche|operation|programme|consultation|terrain|parcelle|etablissement|ecole|groupe scolaire|projet)")
_DECRIT = re.compile(r"\b(?:comprend|comprennent|compte|comptent|comporte|comportent|se (?:situe|trouve)\w*|"
                     r"(?:est|sont) (?:situe|implante|constitue|compose)\w*|porte sur|portent sur|concerne\w*|"
                     r"consiste\w*|accueille\w*|s'etend\w*|date\w* de|represente\w*|totalise\w*|mesure\w*|"
                     r"vise\w*|a pour objet|ont pour objet|souhaite\w*|prevoi\w*|impose\w*|exige\w*|"
                     r"demande\w*)\b")
_MARCHE_LIEU = re.compile(r"^" + _DET + _LIEU + r"\b(?P<suite>.{0,70})")
# … sauf si elle cite des moyens (personnes, matériel, certification) : c'est alors l'entreprise
# (« Le projet comprend une équipe de 15 compagnons »).
_RESSOURCES = re.compile(r"\b(?:compagnons?|salaries?|ouvriers?|agents?|techniciens?|equipes?|personnes?|"
                         r"collaborateurs?|chefs? d'equipe|chefs? de chantier|conducteurs? de travaux|"
                         r"sous-traitants?|interimaires?|apprentis?|effectifs?|encadrants?)\b")
_SECTION_ENTREPRISE = re.compile(r"moyens?\b|humain|materiel|equipe|effectif|encadrement|personnel|reference|"
                                 r"experience|qualite|certification|qualification|securite|environnement|\brse\b|"
                                 r"presentation de l'entreprise|presentation du groupement|savoir[- ]faire|"
                                 r"competence|organigramme|garantie")


def section_sur_l_entreprise(*libelles) -> bool:
    return any(_SECTION_ENTREPRISE.search(fold(x)) for x in libelles if x)


def _rapporte_une_exigence(low: str) -> bool:
    """« Le CCTP prévoit… », « Le maître d'ouvrage impose… », « Selon le règlement, … »."""
    if _MARCHE_SELON.match(low):
        return True
    m = _MARCHE_PIECE.match(low)
    return bool(m and _EXIGE.search(m.group("suite")))


def _decrit_le_lieu(low: str) -> bool:
    """« Le site comprend… », « La commune souhaite… » ; jamais « Le marché sera exécuté par… »."""
    m = _MARCHE_LIEU.match(low)
    if not (m and _DECRIT.search(m.group("suite"))):
        return False
    return not (re.search(r"\bpar\s+(?:\d|[a-z]+ \d)", low) or _RESSOURCES.search(low) or _CERT.search(low)
                or _MATERIEL.search(low))


def parle_entreprise(phrase: str, noms_entreprise=(), section_entreprise: bool = False) -> bool:
    low = fold(phrase)
    if _ENTREPRISE.search(low):
        return True
    for n in noms_entreprise or ():
        fn = fold(n)
        if len(fn) >= 3 and re.search(r"(?<!\w)" + re.escape(fn) + r"(?!\w)", low):
            return True
    # Ce que demande une pièce du dossier ou l'acheteur (sans « nous » ni le nom de
    # l'entreprise) : une phrase sur le marché, même dans une partie sur les moyens.
    if _rapporte_une_exigence(low):
        return False
    if section_entreprise:
        return True        # partie sur les moyens, les références, la qualité : l'entreprise
    if _decrit_le_lieu(low):
        return False
    return True            # doute : le côté le plus strict


# ── Repérage des faits ────────────────────────────────────────────────────────────────

_UNIT_WORDS = (r"%|pour ?cent|€|k€|m€|eur\b|euros?\b|ht\b|ttc\b|m2|m²|m3|m³|ml\b|km\b|kg\b|tonnes?\b|t\b|"
               r"h\b|heures?\b|jours?\b|j\b|semaines?\b|mois\b|ans?\b|annees?\b|"
               # un mot (accents compris : « 3 équipes », « 2 bâtiments » ont bien une unité)
               r"[a-zà-öø-ÿœ][a-zà-öø-ÿœ'\-]{2,}")
# Unité COLLÉE au nombre (« 1200m² », « 30t », « 15km », « 48h », « 3j ») ou ordinal (« 1er », « 3e », « 2nde ») :
# le même fait qu'écrit avec une espace (vague 4, revue : ces formes échappaient au repérage).
_COLLES = (r"m²|m2|m³|m3|ml|km|cm|mm|kg|kwh|kw|kva|mwh|mw|tonnes?|t|h\d{2}|h|j|min|mn|ans?|mois|jours?|k€|m€|"
           r"er|re|ère|ere|ème|eme|e|nde|nd")
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:[   .]\d{3})+|\d+)(?:[.,](\d+))?"
                     r"(?:(?![\w])(?:\s?(" + _UNIT_WORDS + r"))?|(" + _COLLES + r")(?![\w]))", re.IGNORECASE)


def unite_de(m) -> str:
    """L'unité d'un nombre repéré par _NUMBER : écrite après une espace (groupe 3) ou collée (groupe 4)."""
    return (m.group(3) or m.group(4) or "") if m else ""


_WORDS = {"zero": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
          "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
          "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "septante": 70,
          "huitante": 80, "nonante": 90, "cent": 100, "cents": 100, "mille": 1000, "million": 1e6,
          "millions": 1e6, "milliard": 1e9, "milliards": 1e9, "dizaine": 10, "dizaines": 10, "douzaine": 12,
          "quinzaine": 15, "vingtaine": 20, "trentaine": 30, "centaine": 100, "centaines": 100}
_WORD_RE = re.compile(r"(?<![\w'])((?:" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")"
                      r"(?:-(?:et-)?(?:un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|"
                      r"quatorze|quinze|seize|vingts?|cents?))*)(?![\w'])")
# « neuf » est un nombre devant ce qu'il compte (« neuf ans d'expérience », « neuf compagnons ») ; ailleurs, c'est
# l'adjectif (« un bâtiment neuf ») : jamais un fait.
_NEUF = re.compile(r"(?<![\w'-])neuf(?=\s+(?:ans?|annees?|mois|semaines?|jours?|heures?|fois|salaries?|personnes?|"
                   r"compagnons?|collaborateurs?|employes?|ouvriers?|techniciens?|agents?|ingenieurs?|encadrants?|"
                   r"conducteurs?|chefs?|equipes?|chantiers?|references?|projets?|sites?|lots?|batiments?|logements?|"
                   r"engins?|vehicules?|camions?|bennes?|nacelles?|machines?|grues?)\b)")
_CERT = re.compile(
    r"\biso\s?\d{3,5}(?:[-:]\d{1,4})?\b|\bqualibat\b(?:\s?\d{3,4})?|\brge\b|\bqualifelec\b|\bmase\b|\bohsas\b|"
    r"\bqualipv\b|\bqualit'?enr\b|\bqualipac\b|\bqualibois\b|\bqualisol\b|\bcertibat\b|\bcefri\b|\bqualiopi\b|"
    r"\becolabel\b|\bpefc\b|\bfsc\b|\bhqe\b|\bbreeam\b|\bleed\b|\bcaces\b(?:\s?r?\s?\d{3})?|"
    r"\bsous[- ]section\s?[34]\b|\bss\s?[34]\b|\bhabilitations?\s+(?:electriques?\s+)?[a-z]{0,2}\d[a-z0-9]{0,3}\b|"
    r"\bnf\s?(?:en\s?)?\d{2,5}\b|\bqualification\s+\d{3,4}\b|\bopqibi\b|\bopqcm\b|\bafnor\b|\bbureau veritas\b")
_CERT_GENERIQUE = re.compile(r"\bcertifi(?:e|ee|es|ees|cation|cations)\b|\blabellis(?:e|ee|es|ees)\b|"
                             r"\bagre(?:e|ee|es|ees|ment)\b")
_MATERIEL = re.compile(
    r"\b(?:nacelles?|echafaudages?|grues?|mini[- ]?pelles?|pelles? mecaniques?|pelleteuses?|tractopelles?|"
    r"chariots? (?:telescopiques?|elevateurs?)|manuscopiques?|camions?(?: grue| benne)?|bennes?|compresseurs?|"
    r"groupes? electrogenes?|betonnieres?|malaxeurs?|foreuses?|carotteuses?|drones?|stations? totales?|"
    r"theodolites?|plateformes? elevatrices?|pemp|monte[- ]materiaux|monte[- ]charges?|treuils?|fourgons?|"
    r"vehicules? utilitaires?|engins?|extracteurs?|deshumidificateurs?|compacteurs?|rouleaux? compresseurs?|"
    r"niveleuses?|chargeuses?|dumpers?|pompes? a beton|centrales? a beton|lignes? de vie|filets? de securite|"
    r"camera thermique|detecteurs?|lasers?|aspirateurs?|robots?|unites? de decontamination|marteaux?[- ]piqueurs?|"
    r"perforateurs?|meuleuses?|disqueuses?|tronconneuses?|deprimogenes?|filtres? absolus?|"
    r"nettoyeurs? haute pression|balayeuses?|cribleuses?|concasseurs?|broyeurs?)\b")
_PROPRE = re.compile(r"(?<![\w'’-])([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][\wÀ-ÿ'’]*(?:[ -](?:de |du |des |d'|la |le )?"
                     r"[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][\wÀ-ÿ'’]*)*)")
_PROPRE_IGNORES = {
    # Sigles du dossier et de la commande publique, mots institutionnels courants.
    "cctp", "ccap", "rc", "dce", "dpgf", "bpu", "dqe", "ppsps", "pgc", "paq", "soged", "sosed", "doe", "diuo", "epi",
    "epc", "btp", "pme", "tpe", "tva", "ht", "ttc", "csps", "opc", "moe", "moa", "erp", "pmr", "vrd", "cvc", "bet",
    "tce", "rse", "qse", "qhse", "dict", "dt", "pv", "ccag", "ccag-travaux", "ao", "dc1", "dc2", "dc4", "attri1",
    "code", "travail", "etat", "republique", "france", "europe", "union", "ministere", "prefecture", "conseil",
    "agence", "office", "service", "direction", "maitre", "monsieur", "madame", "internet", "lundi", "mardi",
    "mercredi", "jeudi", "vendredi", "samedi", "dimanche", "article", "annexe", "lot", "phase", "tranche",
    "nous", "notre", "nos", "le", "la", "les", "l", "un", "une", "des", "ce", "cette", "ces", "pour", "dans",
    "afin", "en", "au", "aux", "chaque", "tout", "tous", "toute", "toutes", "chef", "chantier", "cadre",
    "reponse", "partie", "question", "planning", "methodologie", "moyens", "qualite", "securite",
}


# Mot qui suit un nombre sans en être l'unité (« en 2015 nous… », « 3 à 5 », « 12 et plus »).
_PAS_UNITE = {"de", "des", "du", "et", "a", "au", "aux", "en", "le", "la", "les", "sur", "par", "pour", "dans",
              "ou", "avec", "une", "un", "nous", "vous", "ils", "elles", "il", "elle", "on", "notre", "nos",
              "votre", "vos", "qui", "que", "dont", "son", "sa", "ses", "leur", "leurs", "ce", "cette", "ces",
              "est", "sont", "sera", "seront", "ont", "plus", "moins", "environ", "chacun", "chacune"}


# « 12 de nos compagnons », « 300 de nos chantiers », « deux de nos conducteurs » : le nombre compte le
# nom qui suit « de nos » (vague 3, revue) — sans cela, il serait relevé SANS unité et se rapprocherait
# de n'importe quelle valeur égale (« 12 m3 de béton »).
_DE_NOS = re.compile(r"^\s*(?:de|d['’])\s*(?:nos|vos|leurs|ses|mes|ces)\s+"
                     r"(?:(?:propres|anciens|anciennes|nouveaux|nouvelles|principaux|principales|meilleurs|"
                     r"meilleures|fideles|fidèles|propre)\s+)?([a-zà-öø-ÿœ][a-zà-öø-ÿœ'’\-]{2,})", re.IGNORECASE)


def _unite_apres_de(suite: str) -> str:
    """Le nom compté après « de nos » (« 12 de nos compagnons » → « compagnons »), ou ""."""
    m = _DE_NOS.match(suite or "")
    if not m:
        return ""
    f = fold(m.group(1))
    if f in _PAS_UNITE or f in _WORDS:
        return ""
    return m.group(1)


def _num_value(intpart: str, dec: str = None) -> float:
    s = re.sub(r"[   .]", "", intpart)
    try:
        return float(s + ("." + dec if dec else ""))
    except ValueError:
        return float("nan")


def _word_value(tok: str) -> float:
    parts = [p for p in fold(tok).split("-") if p and p != "et"]
    total, cur = 0.0, 0.0
    small = {"un": 1, "une": 1, "neuf": 9, **{k: v for k, v in _WORDS.items() if v < 100}}
    for p in parts:
        p2 = p[:-1] if p in ("vingts", "cents") else p
        if p2 in ("cent",):
            cur = (cur or 1) * 100
        elif p2 in ("mille",):
            total += (cur or 1) * 1000
            cur = 0
        elif p2 in ("million", "millions", "milliard", "milliards"):
            total += (cur or 1) * _WORDS[p2]
            cur = 0
        elif p2 in small:
            cur += small[p2]
        elif p2 in _WORDS:
            cur += _WORDS[p2]
    return total + cur


def _unit_key(u: str) -> str:
    u = fold(u or "")
    if not u:
        return ""
    if u in ("%", "pour cent", "pourcent"):
        return "%"
    if u in ("€", "eur", "euro", "euros", "k€", "m€"):
        return "€"
    return re.sub(r"s$", "", u)[:5]


# Mots qui ouvrent une phrase sans être un nom propre (« Le », « Nous », « Pour »…).
_OUVERTURE = {
    "le", "la", "les", "l", "un", "une", "des", "du", "de", "ce", "cet", "cette", "ces", "nous", "notre", "nos",
    "votre", "vos", "leur", "leurs", "son", "sa", "ses", "mon", "ma", "mes", "il", "elle", "ils", "elles", "on",
    "pour", "dans", "en", "au", "aux", "a", "chaque", "tout", "tous", "toute", "toutes", "afin", "sur", "sous",
    "par", "avec", "selon", "depuis", "apres", "avant", "pendant", "lors", "puis", "ensuite", "enfin", "ainsi",
    "grace", "et", "ou", "mais", "donc", "si", "quand", "comme", "chez", "entre", "vers", "outre", "aussi",
}
_TITRE_CIVIL = re.compile(r"(?:^|[\s(«\"'])(?:M|MM|Mme|Mmes|Mlle|Me|Dr|Pr|Mgr|[A-ZÀ-Ý])\.\s$")


def _debuts(phrase: str) -> set:
    """Positions où commence une proposition : début de la phrase, de chaque case d'un tableau,
    après « : » ou une ponctuation forte (jamais après « M. », « Dr. » ou une initiale)."""
    out = {len(phrase) - len(phrase.lstrip(" «\"'(“-•"))}
    for m in re.finditer(r"[:.!?;]\s+[«\"'(“]?", phrase):
        if m.group(0).startswith(".") and _TITRE_CIVIL.search(phrase[:m.start() + 1] + " "):
            continue
        out.add(m.end())
    return out


def _unite_de_ligne(phrase: str) -> str:
    """Ligne de tableau : le libellé (première case sans chiffre) sert d'unité aux nombres seuls."""
    for c in phrase.split(CASE):
        if c.strip() and not re.search(r"\d", c):
            w = re.findall(r"[a-z][a-z'\-]{2,}", fold(c))
            if w:
                return w[0]
    return ""


def _facts_in(phrase: str, tableau: bool = False) -> list:
    """[(fait tel qu'écrit, type, clé de rapprochement)] d'une phrase (ou d'une ligne de tableau)."""
    out, taken = [], []
    low = _fold_same(phrase)
    unite_ligne = _unite_de_ligne(phrase) if tableau else ""

    def _free(a, b):
        return all(b <= x or a >= y for x, y in taken)

    for m in _CERT.finditer(low):
        if _free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            out.append((phrase[m.start():m.end()], CERTIFICATION,
                        re.sub(r"[\s\-:']", "", m.group(0))))
    if not any(t == CERTIFICATION for _f, t, _k in out):
        m = _CERT_GENERIQUE.search(low)
        if m:
            taken.append((m.start(), m.end()))
            out.append((m.group(0), CERTIFICATION, "certifi" if m.group(0).startswith("certif") else m.group(0)[:6]))
    for m in _NUMBER.finditer(phrase):
        a, b = m.span()
        if not _free(a, b):
            continue
        val = _num_value(m.group(1), m.group(2))
        if val != val:      # NaN
            continue
        unit = unite_de(m)
        # Unité = un mot qui suit le nombre ; un mot vide (« de », « et ») n'en est pas une.
        if unit and fold(unit) in _PAS_UNITE:
            unit = ""
            b = m.end(2) if m.group(2) else m.end(1)
        if not unit:
            unit = _unite_apres_de(phrase[b:])         # « 12 de nos compagnons » : 12 compagnons
        if not unit and unite_ligne:
            unit = unite_ligne           # « Compagnons couvreurs ; 15 » : 15 compagnons
        taken.append((a, b))
        out.append((phrase[a:b].strip(), CHIFFRE, (val, _unit_key(unit))))
    for m in _WORD_RE.finditer(low):
        if not _free(m.start(), m.end()):
            continue
        taken.append((m.start(), m.end()))
        after = low[m.end():m.end() + 25].split()
        unit = after[0] if after and after[0] not in ("de", "des", "d'", "et", "a", ";", ":") else ""
        if not unit:
            unit = _unite_apres_de(phrase[m.end():])   # « deux de nos conducteurs »
        if not unit and unite_ligne:
            unit = unite_ligne
        out.append((phrase[m.start():m.end()], EN_LETTRES,
                    (_word_value(m.group(1)), _unit_key(unit))))
    for m in _NEUF.finditer(low):
        if not _free(m.start(), m.end()):
            continue
        taken.append((m.start(), m.end()))
        after = low[m.end():m.end() + 25].split()
        out.append((phrase[m.start():m.end()], EN_LETTRES, (9.0, _unit_key(after[0] if after else ""))))
    for m in _MATERIEL.finditer(low):
        if _free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            stem = re.sub(r"s\b", "", m.group(0))[:12]
            out.append((phrase[m.start():m.end()], MATERIEL, stem))
    # Noms propres : un mot à majuscule (hors sigles du dossier) au fil de la phrase ; en tête de
    # phrase, de case ou après « : », au moins deux mots à majuscule (« Paul Durand », « Vinci
    # Construction », « Mairie de Lorient ») après les mots d'ouverture (« Le », « Nous »…).
    debuts = _debuts(phrase)
    for m in _PROPRE.finditer(phrase):
        a, b = m.span()
        if not _free(a, b):
            continue
        tok = m.group(1).strip()
        if a in debuts:
            mots = tok.split(" ")
            while mots and fold(mots[0]).strip("'’") in _OUVERTURE:
                mots = mots[1:]
            while mots and fold(mots[0]) in ("de", "du", "des", "d'", "la", "le"):
                mots = mots[1:]
            majuscules = [w for w in mots if w[:1].isupper() and fold(w) not in _OUVERTURE]
            if len(majuscules) < 2:
                continue
            tok = " ".join(mots)
            a = b - len(tok)
        words = [w for w in re.split(r"[ \-]", fold(tok)) if w]
        if not words or all(w in _PROPRE_IGNORES or len(w) < 2 for w in words):
            continue
        taken.append((a, b))
        out.append((tok, NOM_PROPRE, fold(tok)))
    return out


# ── Rapprochement avec les sources de l'entreprise ────────────────────────────────────

class Sources:
    """Sources de l'ENTREPRISE (jamais le dossier de l'acheteur), repliées une fois."""

    def __init__(self, textes):
        self.low = fold(" \n ".join(str(t or "") for t in (textes or []) if t))
        self.compact = re.sub(r"[\s\-:']", "", self.low)
        self.nums = []        # (valeur, fenêtre autour)
        raw = " \n ".join(str(t or "") for t in (textes or []) if t)
        for m in _NUMBER.finditer(raw):
            v = _num_value(m.group(1), m.group(2))
            if v == v:
                self.nums.append((v, fold(raw[max(0, m.start() - 60):m.end() + 60])))
        for m in _WORD_RE.finditer(self.low):
            self.nums.append((_word_value(m.group(1)), self.low[max(0, m.start() - 60):m.end() + 60]))
        for m in _NEUF.finditer(self.low):
            self.nums.append((9.0, self.low[max(0, m.start() - 60):m.end() + 60]))

    def has_number(self, val: float, unit: str) -> bool:
        for v, win in self.nums:
            if abs(v - val) < 1e-9:
                if not unit or unit in ("%", "€"):
                    if not unit or unit in win.replace("pour cent", "%").replace("euro", "€"):
                        return True
                    continue
                if re.search(r"(?<![a-z])" + re.escape(unit), win):
                    return True
        return False

    def has(self, kind: str, key) -> bool:
        if kind in (CHIFFRE, EN_LETTRES):
            val, unit = key
            return self.has_number(val, unit)
        if kind == CERTIFICATION:
            return bool(key) and key in self.compact
        if kind == MATERIEL:
            return bool(key) and key in self.low
        if kind == NOM_PROPRE:
            return bool(key) and re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", self.low) is not None
        return False


def _fid(kind: str, fait: str, phrase: str) -> str:
    return hashlib.sha1(f"{kind}|{fold(fait)}|{fold(phrase)}".encode("utf-8")).hexdigest()[:12]


_NUMERIQUES = (CHIFFRE, EN_LETTRES)


def _valeur(fait: str):
    m = _NUMBER.search(str(fait or ""))
    if m:
        v = _num_value(m.group(1), m.group(2))
        return v if v == v else None
    m = _WORD_RE.search(fold(fait))
    return _word_value(m.group(1)) if m else None


def cle_souple(kind: str, fait: str) -> tuple:
    """Le MÊME fait quelle que soit son écriture : valeur d'un nombre (en chiffres ou en lettres,
    quel que soit le mot qui le suit : « quinze compagnons » = « 15 couvreurs »), sigle compact
    d'une certification (« ISO 14001 » = « ISO14001 »), matériel au singulier, nom replié."""
    f = fold(fait)
    if kind in _NUMERIQUES:
        v = _valeur(fait)
        return ("n", round(v, 6)) if v is not None else (kind, f)
    if kind == CERTIFICATION:
        return ("c", re.sub(r"[\s\-:'.]", "", f))
    if kind == MATERIEL:
        return ("m", re.sub(r"s\b", "", f)[:12])
    return (kind, f)


def cle_stricte(x: dict) -> tuple:
    """Le même fait AVEC son unité (« 15 compagnons » ≠ « 15 nacelles ») : sert à reprendre le
    statut « relu par vous », jamais à décider qu'un fait n'est plus à relire."""
    kind, fait = x.get("type", ""), x.get("fait", "")
    if kind in _NUMERIQUES:
        for f2, k2, key in _facts_in(x.get("phrase") or "", tableau=CASE in (x.get("phrase") or "")):
            if k2 in _NUMERIQUES and fold(f2) == fold(fait):
                return ("n", round(key[0], 6), key[1])
        v = _valeur(fait)
        return ("n", round(v, 6) if v is not None else fold(fait), "")
    return cle_souple(kind, fait)


def _meme_fait(cle_nouveau: tuple, cles_anciennes: set, unite_nouveau: str, avec_unite: bool,
               unites_anciennes: dict) -> bool:
    if cle_nouveau not in cles_anciennes:
        return False
    if not avec_unite or cle_nouveau[0] != "n":
        return True
    # Écrit par l'utilisateur : même valeur ET unité compatible (« quinze compagnons » →
    # « 15 compagnons » reste à relire ; « 12 salariés » n'est pas « 12 mois »).
    olds = unites_anciennes.get(cle_nouveau, set())
    return not unite_nouveau or "" in olds or unite_nouveau in olds


def a_relire(texte: str, sources_entreprise, *, noms_entreprise=(), section_entreprise: bool = False) -> list:
    """Faits « à relire » d'un texte : [{id, fait, type, phrase, message, statut}], TOUS (au-delà
    de MAX_FAITS, un dernier élément « reste » les compte : l'export reste bloqué). Les sources
    sont celles de l'ENTREPRISE (textes). Le dossier de l'acheteur ne doit JAMAIS y figurer."""
    src = sources_entreprise if isinstance(sources_entreprise, Sources) else Sources(sources_entreprise)
    out, seen = [], set()
    for ph, titre, tableau in phrases(texte):
        if titre or not parle_entreprise(ph, noms_entreprise, section_entreprise):
            continue
        for fait, kind, key in _facts_in(ph, tableau=tableau):
            if src.has(kind, key):
                continue
            fid = _fid(kind, fait, ph)
            if fid in seen:
                continue
            seen.add(fid)
            out.append({"id": fid, "fait": fait[:120], "type": kind, "phrase": ph[:PHRASE_MAX],
                        "message": MESSAGE, "statut": A_RELIRE})
    return out


def _plafonner(items: list) -> list:
    """Garde-fou de stockage : au-delà de MAX_FAITS, les faits non détaillés sont COMPTÉS dans un
    élément « reste » (toujours à relire, jamais « relu » : il bloque l'export comme les autres)."""
    if len(items) <= MAX_FAITS:
        return items
    n = len(items) - MAX_FAITS
    return items[:MAX_FAITS] + [{"id": RESTE, "fait": "", "type": RESTE, "phrase": "", "nombre": n,
                                 "message": MSG_RESTE.format(n=n), "statut": A_RELIRE}]


def controle(texte: str, sources_entreprise, *, declares=(), anciens=(), reprise: str = "phrase",
             noms_entreprise=(), section_entreprise: bool = False) -> list:
    """Faits à relire d'une NOUVELLE version.
    • declares : textes qui ne viennent pas de l'IA (ce que l'utilisateur a écrit, ou le texte de
      départ de « Raccourcir ») — un fait qui y figure n'est pas signalé… sauf s'il était déjà
      « à relire » ou relu dans `anciens` : il le reste, même réécrit (« quinze » → « 15 »,
      « ISO 14001 » → « ISO14001 ») ;
    • anciens : faits de la version de départ ; un fait encore présent garde son traitement
      « relu par vous » (reprise='phrase' : même fait dans la même phrase ; reprise='fait' : même
      fait avec la même unité, où qu'il soit — « Raccourcir » réécrit les phrases).
    Rapprochement d'un ancien fait : reprise='fait' (l'IA a réécrit) → même valeur quel que soit
    le mot qui suit ; sinon (l'utilisateur a écrit) → même valeur et unité compatible."""
    src_all = Sources(list(sources_entreprise or []) + list(declares or []))
    items = a_relire(texte, src_all, noms_entreprise=noms_entreprise, section_entreprise=section_entreprise)
    anciens = [x for x in (anciens or []) if isinstance(x, dict) and x.get("type") != RESTE]
    if anciens:
        cles = set()
        unites = {}
        for x in anciens:
            c = cle_souple(x.get("type", ""), x.get("fait", ""))
            cles.add(c)
            st = cle_stricte(x)
            unites.setdefault(c, set()).add(st[2] if len(st) == 3 else "")
        strict = a_relire(texte, Sources(sources_entreprise), noms_entreprise=noms_entreprise,
                          section_entreprise=section_entreprise)
        ids = {x["id"] for x in items}
        for x in strict:
            if x["id"] in ids:
                continue
            st = cle_stricte(x)
            if _meme_fait(cle_souple(x["type"], x["fait"]), cles, st[2] if len(st) == 3 else "",
                          reprise != "fait", unites):
                items.append(x)
                ids.add(x["id"])
        by_id = {x.get("id"): x for x in anciens}
        by_cle = {}
        for x in anciens:
            if x.get("statut") == RELU:
                by_cle.setdefault(cle_stricte(x), x)
        for x in items:
            old = by_id.get(x["id"]) or (by_cle.get(cle_stricte(x)) if reprise == "fait" else None)
            if old and old.get("statut") == RELU:
                x.update(statut=RELU, relu_par=old.get("relu_par"), relu_le=old.get("relu_le"))
    return _plafonner(items)


AVEC_SOURCE = "avec_source"     # vague 3 (A) : fait relié à sa source — jamais « à relire »


def non_traites(faits) -> int:
    """Faits à relire non traités (un élément « reste » compte pour tous les faits qu'il résume).
    Depuis la vague 3, la liste peut aussi porter les faits reliés à leur source (A) : ignorés ici."""
    n = 0
    for x in faits or []:
        if not isinstance(x, dict) or x.get("statut") in (RELU, AVEC_SOURCE):
            continue
        n += max(1, int(x.get("nombre") or 1)) if x.get("type") == RESTE else 1
    return n
