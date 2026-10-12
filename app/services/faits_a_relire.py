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
contient « nous », « notre », « nos » ou le nom de l'entreprise ; sinon, elle parle du marché si
elle commence par « le CCTP », « le maître d'ouvrage », « le site »… ; sinon (section sur les
moyens, les références ou la qualité, ou simple doute) : phrase sur l'entreprise.

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

MAX_FAITS = 60
PHRASE_MAX = 300


def fold(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").replace("‘", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


# ── Découpage en phrases (Markdown simple : titres, listes, tableaux) ───────────────────

_TODO = re.compile(r"\[\s*[ÀAà]\s+compl[ée]ter[^\]]*\]", re.IGNORECASE)
_CITE = re.compile(r"\[\s*S\s*\d[^\]]{0,40}\]")
_MD = re.compile(r"\*\*|__|`|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)")


def phrases(texte: str) -> list:
    """[(phrase, est_titre)] dans l'ordre du texte. Les passages « [À compléter …] » et les renvois
    « [S1] » sont retirés (ce ne sont pas des faits)."""
    out = []
    for raw in str(texte or "").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or re.match(r"^\|?\s*:?-{2,}", line):
            continue
        titre = bool(re.match(r"^#{1,6}\s", line))
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+", "", line)
        if line.startswith("|"):
            line = " ; ".join(c.strip() for c in line.strip("|").split("|") if c.strip())
        line = _TODO.sub(" ", line)
        line = _CITE.sub("", line)
        line = _MD.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if titre:
            out.append((line, True))
            continue
        for ph in re.split(r"(?<=[.!?;])\s+(?=\S)", line):
            ph = ph.strip()
            if len(ph) >= 3:
                out.append((ph, False))
    return out


# ── De qui parle la phrase ────────────────────────────────────────────────────────────

_ENTREPRISE = re.compile(r"\b(?:nous|notre|nos|l'entreprise|la societe|notre societe|le candidat|"
                         r"notre groupement|le groupement|nos equipes|notre equipe)\b")
_MARCHE = re.compile(r"^(?:le |la |les |l'|selon le |selon la |conformement au |conformement a la )?"
                     r"(?:cctp|ccap|rc\b|reglement|dossier de (?:la )?consultation|dce\b|maitre d'ouvrage|"
                     r"maitre d'oeuvre|maitrise d'ouvrage|maitrise d'oeuvre|acheteur|pouvoir adjudicateur|"
                     r"commune|ville\b|mairie|collectivite|departement|region|site\b|batiment existant|"
                     r"marche\b|cahier des charges|programme\b|consultation)")
_SECTION_ENTREPRISE = re.compile(r"moyens?\b|humain|materiel|equipe|effectif|encadrement|personnel|reference|"
                                 r"experience|qualite|certification|qualification|securite|environnement|\brse\b|"
                                 r"presentation de l'entreprise|presentation du groupement|savoir[- ]faire|"
                                 r"competence|organigramme|garantie")


def section_sur_l_entreprise(*libelles) -> bool:
    return any(_SECTION_ENTREPRISE.search(fold(x)) for x in libelles if x)


def parle_entreprise(phrase: str, noms_entreprise=(), section_entreprise: bool = False) -> bool:
    low = fold(phrase)
    if _ENTREPRISE.search(low):
        return True
    for n in noms_entreprise or ():
        fn = fold(n)
        if len(fn) >= 3 and re.search(r"(?<!\w)" + re.escape(fn) + r"(?!\w)", low):
            return True
    # « Le CCTP prévoit… », « Le maître d'ouvrage impose… » (sans « nous » ni le nom de
    # l'entreprise) : une phrase sur le marché, même dans une partie sur les moyens.
    if _MARCHE.match(low):
        return False
    if section_entreprise:
        return True
    return True            # doute : le côté le plus strict


# ── Repérage des faits ────────────────────────────────────────────────────────────────

_UNIT_WORDS = (r"%|pour ?cent|€|k€|m€|eur\b|euros?\b|ht\b|ttc\b|m2|m²|m3|m³|ml\b|km\b|kg\b|tonnes?\b|t\b|"
               r"h\b|heures?\b|jours?\b|j\b|semaines?\b|mois\b|ans?\b|annees?\b|[a-z][a-z'\-]{2,}")
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:[   .]\d{3})+|\d+)(?:[.,](\d+))?(?![\w])"
                     r"(?:\s?(" + _UNIT_WORDS + r"))?", re.IGNORECASE)
_WORDS = {"zero": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
          "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
          "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "septante": 70,
          "huitante": 80, "nonante": 90, "cent": 100, "cents": 100, "mille": 1000, "million": 1e6,
          "millions": 1e6, "milliard": 1e9, "milliards": 1e9, "dizaine": 10, "dizaines": 10, "douzaine": 12,
          "quinzaine": 15, "vingtaine": 20, "trentaine": 30, "centaine": 100, "centaines": 100}
_WORD_RE = re.compile(r"(?<![\w'])((?:" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")"
                      r"(?:-(?:et-)?(?:un|une|deux|trois|quatre|cinq|six|sept|huit|dix|onze|douze|treize|"
                      r"quatorze|quinze|seize|vingts?|cents?))*)(?![\w'])")
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
    r"camera thermique|detecteurs?|lasers?)\b")
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


def _num_value(intpart: str, dec: str = None) -> float:
    s = re.sub(r"[   .]", "", intpart)
    try:
        return float(s + ("." + dec if dec else ""))
    except ValueError:
        return float("nan")


def _word_value(tok: str) -> float:
    parts = [p for p in fold(tok).split("-") if p and p != "et"]
    total, cur = 0.0, 0.0
    small = {"un": 1, "une": 1, **{k: v for k, v in _WORDS.items() if v < 100}}
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


def _facts_in(phrase: str) -> list:
    """[(fait tel qu'écrit, type, clé de rapprochement)] d'une phrase."""
    out, taken = [], []
    low = _fold_same(phrase)

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
        unit = m.group(3) or ""
        # Unité = un mot qui suit le nombre ; un mot vide (« de », « et ») n'en est pas une.
        if unit and fold(unit) in _PAS_UNITE:
            unit = ""
            b = m.end(2) if m.group(2) else m.end(1)
        taken.append((a, b))
        out.append((phrase[a:b].strip(), CHIFFRE, (val, _unit_key(unit))))
    for m in _WORD_RE.finditer(low):
        if not _free(m.start(), m.end()):
            continue
        taken.append((m.start(), m.end()))
        after = low[m.end():m.end() + 25].split()
        unit = after[0] if after and after[0] not in ("de", "des", "d'", "et", "a") else ""
        out.append((phrase[m.start():m.end()], EN_LETTRES,
                    (_word_value(m.group(1)), _unit_key(unit))))
    for m in _MATERIEL.finditer(low):
        if _free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            stem = re.sub(r"s\b", "", m.group(0))[:12]
            out.append((phrase[m.start():m.end()], MATERIEL, stem))
    # Noms propres : majuscule hors début de phrase, sigles hors liste du dossier.
    start = len(phrase) - len(phrase.lstrip(" «\"'(“-•"))
    for m in _PROPRE.finditer(phrase):
        a, b = m.span()
        if a <= start or not _free(a, b):
            continue
        tok = m.group(1).strip()
        words = [w for w in re.split(r"[ \-]", fold(tok)) if w]
        if not words or all(w in _PROPRE_IGNORES or len(w) < 2 for w in words):
            continue
        prev = phrase[max(0, a - 2):a]
        if re.search(r"[:.!?]\s?$", prev):          # début de proposition après « : »
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


def _key(kind: str, fait: str) -> str:
    return f"{kind}|{fold(fait)}"


def a_relire(texte: str, sources_entreprise, *, noms_entreprise=(), section_entreprise: bool = False) -> list:
    """Faits « à relire » d'un texte : [{id, fait, type, phrase, message, statut}]. Les sources sont
    celles de l'ENTREPRISE (textes). Le dossier de l'acheteur ne doit JAMAIS y figurer."""
    src = sources_entreprise if isinstance(sources_entreprise, Sources) else Sources(sources_entreprise)
    out, seen = [], set()
    for ph, titre in phrases(texte):
        if titre or not parle_entreprise(ph, noms_entreprise, section_entreprise):
            continue
        for fait, kind, key in _facts_in(ph):
            if src.has(kind, key):
                continue
            fid = _fid(kind, fait, ph)
            if fid in seen:
                continue
            seen.add(fid)
            out.append({"id": fid, "fait": fait[:120], "type": kind, "phrase": ph[:PHRASE_MAX],
                        "message": MESSAGE, "statut": A_RELIRE})
            if len(out) >= MAX_FAITS:
                return out
    return out


def controle(texte: str, sources_entreprise, *, declares=(), anciens=(), reprise: str = "phrase",
             noms_entreprise=(), section_entreprise: bool = False) -> list:
    """Faits à relire d'une NOUVELLE version.
    • declares : textes écrits par l'utilisateur (ses déclarations) — un fait qui y figure ne vient
      pas de l'IA : il n'est pas signalé… sauf s'il était déjà « à relire » dans `anciens` ;
    • anciens : faits de la version de départ ; un fait encore présent garde son traitement
      (reprise='phrase' : même fait dans la même phrase ; reprise='fait' : même fait).
    """
    src_all = Sources(list(sources_entreprise or []) + list(declares or []))
    items = a_relire(texte, src_all, noms_entreprise=noms_entreprise, section_entreprise=section_entreprise)
    anciens = [x for x in (anciens or []) if isinstance(x, dict)]
    if anciens:
        old_keys = {_key(x.get("type", ""), x.get("fait", "")) for x in anciens}
        strict = a_relire(texte, Sources(sources_entreprise), noms_entreprise=noms_entreprise,
                          section_entreprise=section_entreprise)
        ids = {x["id"] for x in items}
        for x in strict:
            if x["id"] not in ids and _key(x["type"], x["fait"]) in old_keys:
                items.append(x)
                ids.add(x["id"])
        by_id = {x.get("id"): x for x in anciens}
        by_key = {}
        for x in anciens:
            by_key.setdefault(_key(x.get("type", ""), x.get("fait", "")), x)
        for x in items:
            old = by_id.get(x["id"]) or (by_key.get(_key(x["type"], x["fait"])) if reprise == "fait" else None)
            if old and old.get("statut") == RELU:
                x.update(statut=RELU, relu_par=old.get("relu_par"), relu_le=old.get("relu_le"))
    return items[:MAX_FAITS]


def non_traites(faits) -> int:
    return sum(1 for x in (faits or []) if isinstance(x, dict) and x.get("statut") != RELU)
