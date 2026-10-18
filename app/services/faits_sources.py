"""
« Chaque fait a sa source » (rédaction, vague 3 — A de l'étude, § 6.5), SANS IA.

Contrat : docs/REDACTION_V3_SOURCES.md. Socle des preuves : app/services/preuves.py
(docs/REDACTION_V3_PREUVES.md). Le contrôle « à relire » de la vague 2 (A0,
app/services/faits_a_relire.py) fournit le découpage en phrases et le REPÉRAGE des faits ; ce module
y ajoute le RAPPROCHEMENT fait par fait avec des sources NUMÉROTÉES et TYPÉES.

1. Des faits numérotés et typés (`fiches`). Chaque fait remis à l'IA a un renvoi, un type de source
   et ce qu'il peut appuyer :
     [F3]  une preuve enregistrée de « Mes preuves » (numéro STABLE, jamais réutilisé) : « trouvé dans
           vos documents » (passage), « justificatif déposé », « déclaré par vous », « source
           publique », « votre estimation » ;
     [S2]  un extrait de « Mon savoir-faire » remis pour la partie : « trouvé dans vos documents » ;
     [P1]  une ligne du profil de l'entreprise : « déclaré par vous » ;
     [E1]  une personne de l'équipe du profil (nom masqué avant l'IA) : « déclaré par vous » ;
     [C1]  une ligne du chiffrage du marché : « votre estimation » (délais, effectifs prévus,
           quantités SEULEMENT) ;
     [G1]  l'apport envoyé par un partenaire du groupement : « déclaré par votre partenaire » — il
           n'appuie qu'une phrase qui nomme ce partenaire (ou qui le cite), et une phrase qui nomme un
           partenaire sans parler de « nous » ne s'appuie que sur son apport (qui affirme quoi).
   Le préfixe F est réservé aux preuves enregistrées ; les autres sont construits à la volée pour
   une rédaction. Le dossier de l'acheteur (« exigé par l'acheteur ») n'a pas de renvoi : il n'appuie
   JAMAIS une phrase sur l'entreprise, seulement une phrase sur le marché, l'acheteur ou le chantier.
2. L'IA cite le renvoi de chaque fait qu'elle utilise ; tout autre fait s'écrit « [À compléter : …] ».
   Le CV d'une personne n'est jamais remis à l'IA : elle écrit « [CV F7] », Adjugo l'insère tel quel.
3. Le contrôle, phrase par phrase, sans IA (`controler`) :
     • de qui parle la phrase (règle stricte d'A0 : « nous », le nom de l'entreprise, une partie sur
       les moyens… ; dans le doute, l'entreprise) ;
     • repérage des faits (A0) : nombres et unités, nombres en lettres, années, certifications, noms
       propres, matériel ;
     • rapprochement : chaque fait d'une phrase sur l'entreprise doit se retrouver dans un fait
       CITÉ dans la phrase, du BON type (une estimation n'appuie que des nombres) — à défaut, dans
       un fait autorisé non cité (l'IA oublie parfois le renvoi), avec la même exigence de type et
       d'unité. Un nombre se rapproche avec SON unité (« 12 salariés » ≠ « 12 mois ») ; un nombre
       écrit sans unité ne se relie jamais par sa seule valeur (un mot commun est exigé) ; une
       certification générique (« agréés », « certifiée ») seulement à un fait cité qui dit le même mot
       et le même objet ; un fait trouvé seulement dans le dossier de l'acheteur reste à relire (« il ne
       prouve rien sur votre entreprise ») ; une phrase sur le marché se rapproche du dossier de
       l'acheteur ;
     • recalcul : un pourcentage ou un total absent tel quel est recalculé SEULEMENT à partir des
       nombres écrits dans la phrase et reliés à une source (jamais des autres nombres des faits cités,
       jamais un produit) ; s'il ne tombe pas juste, il est signalé ;
     • engagements (« nous garantissons », « l'entreprise s'engage à », « zéro accident », « 100 % »,
       « sous 24 h », « dans l'heure ») : à confirmer.
4. Les renvois sont retirés à l'export (app/services/memoire_export.clean_markdown).

Ce qui est rendu pour une version (colonne `faits`, PRIVÉE) : la LISTE de tous les faits relevés,
chacun avec `statut` ∈ {a_relire, relu_par_vous, avec_source} et `source` (None, ou d'où il vient).
Les éléments à relire gardent la forme d'A0 (id, fait, type, phrase, message, statut) : le blocage de
l'export, le « relu par vous » et l'écran d'A0 continuent de marcher.

Libellés positifs (« trouvé dans vos documents »…) et compteur « Faits avec une source : 7 sur 8 » :
affichés SEULEMENT si ATELIER_LIBELLES_SOURCES=1 (étude § 6.5, calibration : le jeu de 50 phrases
piégées passe — tests/test_redaction_v3_sources.py — et la mesure des fausses alertes sur 20 vrais
mémoires reste à faire, scripts/mesure_fausses_alertes.py). Jusque-là, seul l'affichage d'A0 (« à
relire ») est montré. On ne dit JAMAIS « vérifié » : on dit où le fait a été trouvé.

Limites assumées (à dire dans la bulle (i)) : une invention sans chiffre, nom, certification ni
matériel passe ; un document peut être périmé ; le contrôle dit où un fait est ÉCRIT, pas qu'il est vrai.
"""
import itertools
import os
import re
from typing import Iterable, Optional

from app.services import faits_a_relire as far
from app.services.dce_pieces import fold as _fold_same     # repli de MÊME longueur (positions)

# ── Vocabulaire ───────────────────────────────────────────────────────────────────────

PREFIXES = "FSPECG"
PREUVE, EXTRAIT, PROFIL, EQUIPE, CHIFFRAGE, PARTENAIRE = "F", "S", "P", "E", "C", "G"

# Types de source affichés (jamais « vérifié »).
T_DOCUMENTS = "documents"          # passage d'un document de l'entreprise
T_JUSTIFICATIF = "justificatif"    # justificatif déposé (lié, pas lu)
T_DECLARE = "declare"              # déclaré par vous (preuve, profil, équipe)
T_PUBLIC = "public"                # source publique datée (références, qualifications)
T_ESTIMATION = "estimation"        # votre estimation (délais, effectifs prévus, quantités)
T_PARTENAIRE = "partenaire"        # apport envoyé par un partenaire du groupement
T_ACHETEUR = "acheteur"            # dossier de l'acheteur : phrases sur le marché SEULEMENT
T_CALCUL = "calcul"                # recalculé à partir des faits de la phrase et des faits cités
T_VOUS = "vous"                    # écrit par vous dans ce texte (votre déclaration)

LIB_TROUVE = "trouvé dans vos documents"
LIB_JUSTIFICATIF = "justificatif déposé"
LIB_DECLARE = "déclaré par vous"
LIB_PUBLIC = "source publique"
LIB_ESTIMATION = "votre estimation"
LIB_PARTENAIRE = "déclaré par votre partenaire"
LIB_ACHETEUR = "dans le dossier de l'acheteur"
LIB_CALCUL = "calculé à partir de vos faits"
LIB_VOUS = "déclaré par vous"
LIB_ENGAGEMENT = "à confirmer : engagement qui vous liera pendant le chantier"

# Ce que chaque type peut appuyer (étude § 6.5, tableau) — pour une phrase sur l'entreprise.
APPUIE_ENTREPRISE = {T_DOCUMENTS, T_JUSTIFICATIF, T_DECLARE, T_PUBLIC, T_ESTIMATION, T_PARTENAIRE}

AVEC_SOURCE = "avec_source"        # relié à sa source (n'est PAS « vrai » : on dit où il est écrit)
A_RELIRE, RELU = far.A_RELIRE, far.RELU
ENGAGEMENT = "engagement"          # type d'un élément « à confirmer »
ENTREPRISE, MARCHE = "entreprise", "marche"

MESSAGE = far.MESSAGE
MSG_ENGAGEMENT = "À confirmer : engagement qui vous liera pendant le chantier."
MSG_MARCHE = "Adjugo ne retrouve pas ce fait dans le dossier de l'acheteur : relisez-le."
DET_ACHETEUR = ("Ce fait figure dans le dossier de l'acheteur : il ne prouve rien sur votre entreprise.")
DET_ESTIMATION = ("Ce fait n'apparaît que dans votre estimation, qui ne vaut que pour des délais, des effectifs "
                  "prévus ou des quantités.")
DET_SOURCE_PERDUE = ("La source de ce fait n'est plus utilisable (preuve retirée ou expirée, document retiré) : "
                     "relisez-le ou ajoutez une source.")
DET_RENVOI_INCONNU = "Le renvoi {ref} ne correspond à aucun fait remis à Adjugo."
MAX_SOURCES = 2000                 # garde-fou de stockage des faits avec une source (par version)
EXTRAIT_MAX = 240

BULLE = ("Adjugo relie chaque chiffre, nom, certification et engagement à l'endroit où il l'a trouvé. Il ne "
         "sait pas si ce document est à jour, et il ne juge pas les phrases générales : relisez-les.")


def libelles_actifs() -> bool:
    """Libellés positifs et compteur « Faits avec une source » : seulement après la calibration
    (étude § 6.5). Désactivés par défaut : l'écran garde l'affichage d'A0 (« à relire »)."""
    return os.environ.get("ATELIER_LIBELLES_SOURCES", "").strip().lower() in ("1", "true", "oui", "yes")


# ── Renvois [F3], [S2], [P1]… ─────────────────────────────────────────────────────────

_REF = re.compile(r"\[\s*([FSPECG]\s*\d{1,4}(?:\s*[,;]\s*(?:[FSPECG]\s*)?\d{1,4})*)\s*\]")
_REF_ITEM = re.compile(r"([FSPECG])?\s*(\d{1,4})")
_CV = re.compile(r"^[ \t]*[-*•]?[ \t]*\[\s*CV\s+F\s*(\d{1,4})\s*\][ \t]*\.?[ \t]*$", re.MULTILINE | re.IGNORECASE)
_CV_INLINE = re.compile(r"\[\s*CV\s+F\s*(\d{1,4})\s*\]", re.IGNORECASE)


def refs_de(texte: str) -> list:
    """Renvois cités, dans l'ordre (« [F3, F4] » et « [F3; 4] » compris), sans doublon."""
    out = []
    for m in _REF.finditer(str(texte or "")):
        pref = ""
        for p, n in _REF_ITEM.findall(m.group(1)):
            pref = p or pref
            r = f"{pref}{int(n)}"
            if pref and r not in out:
                out.append(r)
    return out


def _sans_refs(s: str) -> str:
    return _REF.sub("", s)


# ── Phrases avec leurs renvois (même découpage qu'A0) ────────────────────────────────

def _normaliser_refs(line: str) -> str:
    # « [F3; F4] » → « [F3, F4] » : le point-virgule ne doit pas couper la phrase.
    return _REF.sub(lambda m: "[" + re.sub(r"\s*;\s*", ", ", m.group(1)) + "]", line)


def _nettoyer(s: str) -> str:
    s = _sans_refs(far._TODO.sub(" ", s))
    s = far._CITE.sub("", s)
    s = far._MD.sub("", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _que_des_refs(s: str) -> bool:
    return bool(_REF.search(s)) and not re.sub(r"[\s.;,!?]", "", _sans_refs(s))


def phrases(texte: str) -> list:
    """[{phrase, refs, titre, tableau}] dans l'ordre du texte. `phrase` est EXACTEMENT celle d'A0
    (far.phrases) ; `refs` = renvois cités dans la phrase (un renvoi isolé après le point, ou en
    tête de la phrase suivante, appartient à la phrase qui précède)."""
    out = []
    for raw in str(texte or "").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or re.match(r"^\|?\s*:?-{2,}[-:|\s]*$", line):
            continue
        titre = bool(re.match(r"^#{1,6}\s", line))
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+", "", line)
        line = _normaliser_refs(line)
        tableau = line.startswith("|") and line.count("|") >= 2
        if tableau:
            cells = [_nettoyer(c) for c in line.strip("|").split("|")]
            ph = far.CASE.join(c for c in cells if c)
            if ph:
                out.append({"phrase": ph, "refs": refs_de(line), "titre": titre, "tableau": True})
            continue
        line = far._TODO.sub(" ", line)
        if titre:
            ph = _nettoyer(line)
            if ph:
                out.append({"phrase": ph, "refs": refs_de(line), "titre": True, "tableau": False})
            continue
        pieces = []
        for pc in far._couper(line):
            m = re.match(r"^((?:\s*\[[^\]]*\])+)\s*(.*)$", pc)
            if pieces and _que_des_refs(pc):
                pieces[-1][1].extend(refs_de(pc))
                continue
            if pieces and m and _REF.search(m.group(1)) and not _sans_refs(m.group(1)).strip():
                pieces[-1][1].extend(refs_de(m.group(1)))      # renvoi en tête : celui de la phrase d'avant
                pc = m.group(2)
            pieces.append([pc, refs_de(pc)])
        for pc, refs in pieces:
            ph = _nettoyer(pc)
            if len(ph) >= 3 or re.search(r"\d", ph):
                out.append({"phrase": ph, "refs": list(dict.fromkeys(refs)), "titre": False, "tableau": False})
    return out


# ── Nombres : valeur ET unité ─────────────────────────────────────────────────────────

_PERSONNES = {"salar", "compa", "perso", "colla", "emplo", "agent", "ouvri", "techn", "effec", "etp"}
_SYN = {"heure": "h", "j": "jour", "sem": "semai", "annee": "an", "t": "tonne", "m²": "m2", "m³": "m3"}


def _unite(u5: str) -> str:
    """Clé d'unité d'A0 (5 lettres) ramenée à une famille : « salariés », « compagnons »,
    « personnes »… → personnes ; « heures » → h ; « années » → an."""
    u = (u5 or "").strip()
    if u in _PERSONNES:
        return "personnes"
    return _SYN.get(u, u)


def _mult(fait: str) -> float:
    f = far.fold(fait)
    if re.search(r"\d\s?k\s?€|\bk\s?eur\b|\bkeur\b", f):
        return 1000.0
    if re.search(r"\d\s?m\s?€|\bm\s?eur\b|\bmeur\b|\bmillions?\b", f):
        return 1e6
    if re.search(r"\bmilliards?\b", f):
        return 1e9
    return 1.0


def cle_nombre(kind: str, fait: str, key) -> tuple:
    """(valeur, unité) d'un fait chiffré d'A0, avec les multiplicateurs (« 85 k€ » = 85 000 €)."""
    try:
        val, u5 = key
    except (TypeError, ValueError):
        return None, ""
    m = _mult(fait) if kind == far.CHIFFRE else 1.0
    u = _unite(u5)
    if u in ("milli",):         # « 1,2 million » : l'unité vient après (« d'euros ») — inconnue
        u = ""
    return round(float(val) * m, 6), u


def _egal(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


_COUPE_CLAUSE = re.compile(r"[;\n|]|[.!?](?=\s)")
_MOT = re.compile(r"[a-z0-9€%][a-z0-9€%'\-]*")


class Index:
    """Une source (fiche, extrait, pièce du dossier de l'acheteur) indexée UNE fois : nombres avec
    leur unité (le mot qui suit, sinon le libellé de la même proposition : « Effectif : 12 »),
    certifications, noms, matériel."""

    def __init__(self, texte: str, extra: Iterable = (), large: bool = False):
        import bisect
        self.texte = str(texte or "")
        raw = "\n".join([self.texte] + [str(x) for x in (extra or ()) if x])
        self.raw = raw
        self.low = far.fold(raw)
        self.compact = re.sub(r"[\s\-:'.]", "", self.low)
        same = _fold_same(raw)
        self.same = same
        self.nums = []       # (valeur, unité, contexte, début, fin) — positions dans raw
        self.large = bool(large)
        self.clauses = {}    # début d'un nombre → mots de TOUTE sa proposition (clés d'unité)
        self.brutes = {}     # début d'un nombre → son unité telle qu'écrite (clé d'A0 : « compa », « salar »)
        bornes = [0] + [m.end() for m in _COUPE_CLAUSE.finditer(same)] + [len(same) + 1]

        tout = ({_unite(re.sub(r"s$", "", w)[:5]) for w in _MOT.findall(same) if not w.isdigit()} if large
                else None)

        def _ctx(a, b, avec_suite: bool):
            if tout is not None:        # une fiche courte : un seul fait, tous ses mots en sont le contexte
                return tout
            i = bisect.bisect_right(bornes, a) - 1
            d, f = bornes[max(0, i)], bornes[min(len(bornes) - 1, i + 1)]
            avant = _MOT.findall(same[max(d, a - 80):a])[-6:]
            apres = _MOT.findall(same[b:min(f, b + 60)])[:6] if avec_suite else []
            return {_unite(re.sub(r"s$", "", w)[:5]) for w in avant + apres}

        def _clause(a):
            if tout is not None:
                return tout
            i = bisect.bisect_right(bornes, a) - 1
            d, f = bornes[max(0, i)], bornes[min(len(bornes) - 1, i + 1)]
            return {_unite(re.sub(r"s$", "", w)[:5]) for w in _MOT.findall(same[d:f]) if not w.isdigit()}

        taken = []
        for m in far._NUMBER.finditer(raw):
            v = far._num_value(m.group(1), m.group(2))
            if v != v:
                continue
            unit = far.unite_de(m)
            b = m.end()
            if unit and far.fold(unit) in far._PAS_UNITE:
                unit = ""
                b = m.end(2) if m.group(2) else m.end(1)
            u = _unite(far._unit_key(unit))
            mult = _mult(raw[m.start():b])
            if u == "milli":
                u = ""
            self.nums.append((round(v * mult, 6), u, _ctx(m.start(), b, not unit), m.start(), b))
            self.clauses[m.start()] = _clause(m.start())
            self.brutes[m.start()] = far._unit_key(unit)
            taken.append((m.start(), b))
        for m in far._WORD_RE.finditer(same):
            if any(not (m.end() <= x or m.start() >= y) for x, y in taken):
                continue
            after = same[m.end():m.end() + 25].split()
            unit = after[0] if after and after[0] not in ("de", "des", "d'", "et", "a", ";", ":") else ""
            u = _unite(far._unit_key(unit))
            self.nums.append((far._word_value(m.group(1)), u, _ctx(m.start(), m.end(), not unit), m.start(),
                              m.end()))
            self.clauses[m.start()] = _clause(m.start())
            self.brutes[m.start()] = far._unit_key(unit)
        self.certs = [(re.sub(r"[\s\-:'.]", "", m.group(0)), m.start(), m.end()) for m in far._CERT.finditer(same)]
        self.par_valeur = {}         # valeur arrondie → nombres (un gros dossier : pas de parcours complet)
        for x in self.nums:
            self.par_valeur.setdefault(round(x[0], 4), []).append(x)

    def nombre(self, val: float, unite: str, mots: Optional[set] = None, brute: str = "") -> Optional[tuple]:
        """(début, fin) du nombre `val` avec une unité compatible, ou None.
        Avec une unité dans le fait : la même juste après le nombre, ou, si le nombre n'en a pas, dans
        le libellé de la même proposition (« Effectif : 12 » = « 12 salariés »).
        Sans unité dans le fait (« 12 sur ce chantier ») : la valeur ne suffit JAMAIS quand on connaît
        les mots de la phrase (`mots`) — un nombre de la source avec une unité ne convient que si la
        phrase la nomme (« 3 + 15, au total 18 jours » ↔ « 3 jours ») ; un nombre de la source sans
        unité, que si la phrase et sa proposition ont un mot en commun. `mots` None (dossier de
        l'acheteur) : la valeur suffit.
        Dans un EXTRAIT de document (pas une fiche), une durée, une mesure, un montant, un pourcentage ou
        un nombre de personnes revient souvent avec un autre sens : il faut en plus un mot commun entre
        la phrase et la proposition de la source (« 3 tonnes de stock » ≠ « 3 tonnes d'acier livrées ») ;
        pour des personnes, le même mot suffit aussi (« 9 compagnons » ↔ « 9 compagnons couvreurs »,
        `brute` : l'unité telle qu'écrite dans la phrase), sauf le mot « personnes », trop général
        (« 6 personnes formées » n'est pas « 6 personnes sur ce chantier »)."""
        if val is None:
            return None
        for v, u, ctx, a, b in self.par_valeur.get(round(val, 4), ()):
            if not _egal(v, val):
                continue
            if unite:
                if not (u == unite or (not u and unite in ctx)):
                    continue
                if mots is not None and not self.large and unite in _MESURES \
                        and not (self.clauses.get(a, set()) - {unite}) & mots \
                        and not (unite == "personnes" and brute and brute != "perso" and self.brutes.get(a) == brute):
                    continue
                return a, b
            if mots is None or (u and u in mots) or (not u and ctx & mots):
                return a, b
        return None

    def unite_a(self, pos) -> str:
        """L'unité du nombre de la source à cette position (« 3 jours » → « jour »), ou ""."""
        if not pos:
            return ""
        for _v, u, _c, a, _b in self.nums:
            if a == pos[0]:
                return u
        return ""

    def generique(self, key: str, objets: set) -> Optional[tuple]:
        """Une certification générique (« agréés », « certifiée », « labellisés ») n'est appuyée que si la
        source emploie le MÊME mot générique ET, dans la même proposition, un objet commun avec la
        phrase (« agréés pour le retrait de l'amiante » ↔ « agrément amiante »). Jamais une
        qualification quelconque (« Qualibat 3194 » n'appuie pas « certifiée pour le désamiantage »)."""
        rx = _FAMILLE_GENERIQUE.get(_famille_generique(key))
        if rx is None or not objets:
            return None
        for m in rx.finditer(self.same):
            d = max([0] + [x.end() for x in _COUPE_CLAUSE.finditer(self.same, 0, m.start())])
            f = _COUPE_CLAUSE.search(self.same, m.end())
            clause = self.same[d:f.start() if f else len(self.same)]
            if _objets(clause) & objets:
                return m.start(), m.end()
        return None

    def trouve(self, kind: str, key, fait: str = "", mots: Optional[set] = None) -> Optional[tuple]:
        """Position (début, fin) du fait dans la source ((-1, -1) : présent, position inconnue), ou None.
        Une certification générique ne se trouve jamais ici (voir `generique`)."""
        if kind in (far.CHIFFRE, far.EN_LETTRES):
            v, u = cle_nombre(kind, fait, key)
            brute = key[1] if isinstance(key, tuple) and len(key) == 2 else ""
            return self.nombre(v, u, mots, brute=brute)
        if kind == far.CERTIFICATION:
            if not key or key in _CERT_GENERIQUES:
                return None
            for k, a, b in self.certs:
                if k == key:
                    return a, b
            # Écrit autrement (« ISO-14001 ») : le sigle compact, seulement s'il est assez long pour ne
            # pas se trouver au milieu d'un autre mot (« RGE » dans « charge », « MASE » dans « base »).
            if len(key) >= 6 or re.search(r"\d", key):
                return (-1, -1) if key in self.compact else None
            return (-1, -1) if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", self.low) else None
        if kind == far.MATERIEL:
            return self._pos(key) if key and key in self.low else None
        if kind == far.NOM_PROPRE:
            if key and re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", self.low):
                return self._pos(key)
            return None
        return None

    def _pos(self, key: str) -> tuple:
        i = self.same.find(key)
        return (i, i + len(key)) if i >= 0 else (-1, -1)

    def extrait(self, pos: Optional[tuple], n: int = EXTRAIT_MAX) -> str:
        """Le passage de la source autour du fait (tel qu'il y est écrit)."""
        t = self.texte
        if not t:
            return ""
        if not pos or pos[0] < 0 or pos[0] >= len(t):
            s = re.sub(r"\s+", " ", t[:n]).strip()
            return s + (" …" if len(t) > n else "")
        a, b = pos
        d = max(0, a - n // 2)
        f = min(len(t), max(b, a) + n // 2)
        s = re.sub(r"\s+", " ", t[d:f]).strip()
        return ("… " if d > 0 else "") + s + (" …" if f < len(t) else "")


_CERT_GENERIQUES = {"certifi", "labell", "agree", "agreme", "agrees", "agre"}
# Unités qui reviennent souvent avec un autre sens dans un long document (voir Index.nombre).
_MESURES = {"h", "jour", "semai", "mois", "an", "%", "€", "m2", "m3", "ml", "km", "kg", "tonne", "litre", "metre",
            "minut", "personnes"}
_FAMILLE_GENERIQUE = {"certifi": re.compile(r"\bcertifi\w*"), "label": re.compile(r"\blabel\w*"),
                      "agre": re.compile(r"\bagre(?:e|ee|es|ees|ment|ments)\b")}
# Mots trop généraux pour dire l'OBJET d'une certification générique.
_OBJETS_VIDES = {"entreprise", "societe", "equipe", "compagnon", "salarie", "personnel", "travaux", "chantier",
                 "pose", "realisation", "activite", "metier", "domaine", "secteur", "prestation", "ensemble",
                 "annee", "depuis", "sommes", "etre", "avons", "avoir", "toute", "tous", "notre", "nous", "leur",
                 "pour", "dans", "avec", "selon", "certifie", "certification", "certificat", "labellise", "label",
                 "agree", "agrement", "qualifie", "qualification", "organisme", "numero", "valable", "jusqu"}


def _famille_generique(key: str) -> str:
    k = str(key or "")
    return "certifi" if k.startswith("certif") else "label" if k.startswith("label") else \
        "agre" if k.startswith("agre") else ""


def _objets(texte: str) -> set:
    """Mots porteurs de sens (racines de 6 lettres) d'un texte replié, hors mots vides et généraux."""
    out = set()
    for w in re.findall(r"[a-z]{4,}", far.fold(texte)):
        w2 = re.sub(r"s$", "", w)
        if {w, w2} & (_OBJETS_VIDES | _MOTS_VIDES_CTX):
            continue
        out.add(w2[:6])
    return out


# ── Les fiches : faits numérotés et typés remis à l'IA ────────────────────────────────

class Fiche:
    """Un fait autorisé : renvoi, type de source, texte (rapprochement), texte pour l'IA."""

    def __init__(self, ref: str, type_source: str, libelle: str, texte: str, texte_ia: str = None, *,
                 extra=(), lien: str = "", doc_nom: str = "", extrait: str = "", preuve_id=None, chunk_id=None,
                 nature: str = "", valeur: Optional[dict] = None, proprietaire: str = "", document_id=None):
        self.ref, self.type, self.libelle = ref, type_source, libelle
        self.texte = str(texte or "")
        self.texte_ia = self.texte if texte_ia is None else str(texte_ia or "")
        self.extra = tuple(extra or ())
        self.lien, self.doc_nom, self.extrait = lien or "", doc_nom or "", extrait or ""
        self.preuve_id, self.chunk_id = preuve_id, chunk_id
        self.nature, self.valeur = nature or "", dict(valeur or {})
        self.proprietaire = proprietaire or ""
        self.document_id = document_id
        self._idx = None

    @property
    def index(self) -> Index:
        if self._idx is None:
            # Une fiche (preuve, profil, équipe, chiffrage, apport) dit UN fait : tous ses mots en sont le
            # contexte. Un extrait de document [S#] : seulement la proposition autour du nombre.
            self._idx = Index(self.texte, self.extra, large=not self.ref.startswith(EXTRAIT))
        return self._idx

    def appuie(self, kind: str) -> bool:
        """Le BON type : une estimation n'appuie que des nombres (délais, effectifs prévus,
        quantités) ; les autres sources de l'entreprise appuient tout fait sur elle."""
        if self.type not in APPUIE_ENTREPRISE:
            return False
        if self.type == T_ESTIMATION:
            return kind in (far.CHIFFRE, far.EN_LETTRES)
        return True

    def source(self, pos=None, cite: bool = True) -> dict:
        """D'où vient le fait : renvoi, type, libellé, lien, document et passage (privés)."""
        out = {"ref": self.ref, "type": self.type, "libelle": self.libelle, "cite": bool(cite)}
        if self.lien:
            out["lien"] = self.lien
        if self.doc_nom:
            out["doc_nom"] = self.doc_nom[:200]
        if self.type == T_JUSTIFICATIF:
            ex = ""
        elif self.extrait:
            ex = self.extrait
        else:
            ex = self.index.extrait(pos)
        if ex:
            out["extrait"] = ex[:EXTRAIT_MAX + 8]
        if self.preuve_id:
            out["preuve_id"] = self.preuve_id
        if self.chunk_id:
            out["chunk_id"] = self.chunk_id
        if self.document_id:
            out["document_id"] = self.document_id
        if self.proprietaire:
            out["partenaire"] = self.proprietaire[:120]
        return out

    def ligne_ia(self) -> str:
        """« [F3] (trouvé dans vos documents) Référence : … » — ce que l'IA lit (jamais un CV)."""
        lib = self.libelle
        if self.type == T_ESTIMATION:
            lib += " : seulement pour des délais, des effectifs prévus ou des quantités"
        s = f"[{self.ref}] ({lib}) {self.texte_ia}".strip()
        if self.nature == "salarie" and self.ref.startswith(PREUVE):
            s += f" — CV : écris « [CV {self.ref}] » seul sur une ligne pour l'insérer tel quel."
        return s


def _adjacents(nature: str, v: dict) -> list:
    """Chaînes où le nombre est collé à ce qu'il compte (« 2 nacelle articulée ») : la quantité d'un
    matériel, la valeur d'un chiffre clé, l'expérience d'une personne, le montant d'une référence."""
    from app.services import preuves as pv
    out = []
    if nature == pv.MATERIEL and v.get("quantite") is not None:
        out.append(f"{v['quantite']} {v.get('designation', '')}")
    elif nature == pv.CHIFFRE_CLE and v.get("valeur") is not None:
        out.append(f"{pv._nombre(v['valeur'])} {v.get('unite', '')} {v.get('libelle', '')}".strip())
        out.append(f"{pv._nombre(v['valeur'])} {v.get('libelle', '')}".strip())
    elif nature == pv.SALARIE and v.get("experience_annees") is not None:
        out.append(f"{v['experience_annees']} ans d'expérience")
    elif nature == pv.REFERENCE and v.get("montant_ht") is not None:
        out.append(f"{pv._nombre(v['montant_ht'])} € HT")
    return out


def fiches_preuves(db, owner_id: int, project_id: Optional[int] = None, pseudonymiseur=None) -> list:
    """Les preuves UTILISABLES de l'organisation (pv.faits_autorises), en fiches [F<numéro>]."""
    from app.services import preuves as pv
    out = []
    for f in pv.faits_autorises(db, owner_id, project_id=project_id):
        src = f.get("source") or {}
        if f["type_source"] == pv.DOCUMENTS:
            t = T_DOCUMENTS if src.get("passage") else T_JUSTIFICATIF
            lien = src.get("lien_passage") or src.get("lien_justificatif") or ""
            doc = src.get("doc_nom") or src.get("document_nom") or ""
            extrait = (src.get("passage") or "")[:EXTRAIT_MAX]
        else:
            t = {pv.DECLARE: T_DECLARE, pv.PUBLIC: T_PUBLIC, pv.ESTIMATION: T_ESTIMATION}.get(f["type_source"],
                                                                                            T_DECLARE)
            lien = src.get("url") or ""
            doc = src.get("nom") or ""
            extrait = ""
        out.append(Fiche(f["ref"], t, f["source_libelle"], f["texte"], pv.texte_pour_ia(f, pseudonymiseur),
                         extra=_adjacents(f["nature"], f.get("valeur") or {}), lien=lien, doc_nom=doc,
                         extrait=extrait, preuve_id=f["id"], nature=f["nature"], valeur=f.get("valeur") or {},
                         document_id=src.get("document_id") if t == T_JUSTIFICATIF else None))
    return out


def fiches_contexte(profil: str, equipe: str, chiffrage: str, partenaires: list) -> list:
    """Profil [P#] (déclaré par vous), équipe du profil [E#] (déclaré par vous ; les noms sont
    masqués avant l'IA par pii_scope), chiffrage [C#] (votre estimation), apports envoyés par les
    partenaires [G#] (déclaré par votre partenaire). Construits pour une rédaction."""
    out = []
    for i, ln in enumerate([x.strip() for x in str(profil or "").split("\n") if x.strip()], start=1):
        out.append(Fiche(f"{PROFIL}{i}", T_DECLARE, LIB_DECLARE, ln))
    for i, ln in enumerate([x.strip().lstrip("- ").strip() for x in str(equipe or "").split("\n") if x.strip()],
                           start=1):
        out.append(Fiche(f"{EQUIPE}{i}", T_DECLARE, LIB_DECLARE, ln))
    for i, ln in enumerate([x.strip().lstrip("- ").strip() for x in str(chiffrage or "").split("\n") if x.strip()],
                           start=1):
        out.append(Fiche(f"{CHIFFRAGE}{i}", T_ESTIMATION, LIB_ESTIMATION, ln))
    for i, p in enumerate([p for p in (partenaires or []) if isinstance(p, dict) and p.get("texte")], start=1):
        out.append(Fiche(f"{PARTENAIRE}{i}", T_PARTENAIRE, LIB_PARTENAIRE, str(p["texte"]).lstrip("- ").strip(),
                         proprietaire=str(p.get("nom") or "")))
    return out


def fiches_extraits(chunks: list) -> list:
    """Extraits de « Mon savoir-faire » remis pour la partie : [S1]… (trouvé dans vos documents)."""
    out = []
    for i, c in enumerate(chunks or [], start=1):
        if not isinstance(c, dict):
            continue
        ref = str(c.get("ref") or f"{EXTRAIT}{i}")
        out.append(Fiche(ref, T_DOCUMENTS, LIB_TROUVE, c.get("text") or c.get("texte") or "",
                         doc_nom=c.get("doc_name") or "", chunk_id=c.get("chunk_id")))
    return out


LIGNES_IA_MAX = int(os.environ.get("ATELIER_FAITS_MAX_CARACTERES", "12000") or 12000)
_MOTS_VIDES = {"pour", "dans", "avec", "sans", "sous", "votre", "notre", "leurs", "cette", "chaque", "entre",
               "partie", "dossier", "presentez", "decrivez", "precisez", "indiquez", "candidat", "chantier"}


def lignes_ia(fiches: list, requete: str = "", budget: int = None) -> list:
    """Les lignes « [F3] (type) fait » remises à l'IA pour une partie (les extraits [S#] ont leur
    propre bloc). Toutes, si elles tiennent dans le budget (≈ 12 000 caractères) ; sinon, les preuves
    les plus proches de la partie (mots communs, sans IA) d'abord, dans l'ordre de leurs numéros.
    Le profil, l'équipe, le chiffrage et les partenaires sont toujours remis."""
    budget = int(budget or LIGNES_IA_MAX)
    fs_ = [f for f in fiches or [] if isinstance(f, Fiche) and not f.ref.startswith(EXTRAIT)]
    lignes = {f.ref: f.ligne_ia() for f in fs_}
    if sum(len(x) + 1 for x in lignes.values()) <= budget:
        return [lignes[f.ref] for f in fs_]
    mots = {w for w in re.findall(r"[a-z0-9]{4,}", far.fold(requete)) if w not in _MOTS_VIDES}
    garde = {f.ref for f in fs_ if not f.ref.startswith(PREUVE)}
    reste = budget - sum(len(lignes[r]) + 1 for r in garde)

    def _score(f):
        w = set(re.findall(r"[a-z0-9]{4,}", far.fold(f.texte_ia)))
        return (-len(mots & w), f.ref)
    for f in sorted((f for f in fs_ if f.ref.startswith(PREUVE)), key=_score):
        n = len(lignes[f.ref]) + 1
        if n <= reste:
            garde.add(f.ref)
            reste -= n
    return [lignes[f.ref] for f in fs_ if f.ref in garde]


class Acheteur:
    """Le dossier de l'acheteur, pièce par pièce : n'appuie QUE les phrases sur le marché, et sert
    à dire qu'un fait d'une phrase sur l'entreprise vient de lui (« il ne prouve rien »)."""

    def __init__(self, pieces: Iterable):
        self.pieces = []
        for nom, texte in pieces or ():
            if str(texte or "").strip():
                self.pieces.append((str(nom or "")[:200], Index(texte)))

    @property
    def disponible(self) -> bool:
        return bool(self.pieces)

    def trouve(self, kind, key, fait):
        for nom, idx in self.pieces:
            pos = idx.trouve(kind, key, fait)
            if pos is not None:
                out = {"ref": "", "type": T_ACHETEUR, "libelle": LIB_ACHETEUR, "cite": False,
                       "extrait": idx.extrait(pos)[:EXTRAIT_MAX + 8]}
                if nom:
                    out["doc_nom"] = nom
                return out
        return None


# ── Engagements, calculs ──────────────────────────────────────────────────────────────

_NB_LETTRES = (r"(?:\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|dix|douze|quinze|vingt|trente|quarante(?:-huit)?|"
               r"soixante(?:-douze)?)")
# Formules qui ENGAGENT l'entreprise (étude § 6.5) ; « afin de garantir la sécurité » n'en est pas une.
_ENGAGE = re.compile(
    r"\bnous nous engageons\b|\bnous vous engageons\b|\bs'engage(?:nt)? a\b|\bnous (?:vous )?garantissons\b|"
    r"\bnous (?:vous )?promettons\b|\bnous nous obligeons\b|\bnous (?:nous )?astreignons\b|"
    r"\bnous (?:pouvons|savons|allons) (?:vous )?garantir\b|\bnous (?:vous )?assurons (?:que|une?|le|la|les)\b|"
    r"\b(?:delais?|interventions?|resultats?|qualite|performances?|disponibilite|prix|duree) garanti(?:e|s|es)?\b|"
    r"\bzero (?:accident|defaut|reserve|dechet|retard|incident|nuisance|plainte|sinistre|panne)s?\b|"
    r"(?<![\d,.])100 ?%|"
    r"\bsous " + _NB_LETTRES + r"[ -]?(?:h\b|heures?\b|jours?\b|j\b|semaines?\b)|"
    r"\bdans (?:un delai de |les )\d+ ?(?:h\b|heures?\b|jours?\b|j\b|semaines?\b)|"
    r"\b24 ?h ?/ ?24\b|\b7 ?j ?/ ?7\b|\bau plus tard\b|\bdans l'heure\b|\bsans faute\b|"
    r"\bsans (?:aucun |aucune )?(?:retard|surcout|interruption|nuisance|reserve)s?\b")


def engagement(phrase: str) -> Optional[str]:
    """La formule d'engagement d'une phrase (telle qu'écrite), ou None."""
    m = _ENGAGE.search(_fold_same(phrase))
    return phrase[m.start():m.end()] if m else None


_TOTAL = re.compile(r"\b(?:au total|en tout|soit|total|totalis\w*|cumul\w*|au global|ensemble|somme)\b")


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}".replace(",", " ")
    return (f"{x:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def _decimales(fait: str) -> int:
    m = re.search(r"\d[.,](\d+)", fait or "")
    return len(m.group(1)) if m else 0


def _annee(a: float, ua: str) -> bool:
    return not ua and 1900 <= a <= 2100 and float(a).is_integer()


def _dedoublonner(pool: list, v: float, n: int) -> list:
    """Nombres distincts (une année n'entre jamais dans un calcul), sans le nombre recalculé."""
    out, vus = [], []
    for a, ua in pool:
        if a is None or _egal(a, v) or _annee(a, ua) or any(_egal(a, b) for b, _ub in vus):
            continue
        vus.append((a, ua))
        out.append((a, ua))
        if len(out) >= n:
            break
    return out


# Familles d'unités compatibles dans un calcul : des personnes (« 6 couvreurs sur 12 salariés ») ou du
# matériel (« 2 nacelles et 4 camions, soit 6 engins ») ; jamais des personnes avec du matériel.
_METIERS = {"personnes", "couvr", "charp", "macon", "plomb", "elect", "menui", "peint", "plaqu", "carre", "chauf",
            "soude", "zingu", "condu", "chef", "ingen", "appre", "inter", "encad", "monte", "terra", "manoe"}
_MATERIELS = {"nacel", "echaf", "grue", "pelle", "mini-", "camio", "benne", "compr", "engin", "machi", "vehic",
              "fourg", "chari", "treui", "foreu", "carot", "drone", "laser", "pompe", "roule", "dumpe", "charg",
              "group", "malax", "nivel", "tract", "pelle"}


def _famille(u: str) -> str:
    if not u:
        return ""
    if u in _METIERS:
        return "personnes"
    if u in _MATERIELS:
        return "materiel"
    return u


def _compatibles(ua: str, ub: str) -> bool:
    return bool(ua and ub) and (ua == ub or _famille(ua) == _famille(ub))


def recalcul(v: float, u: str, fait: str, phrase_low: str, phrase: list, cites: list = ()) -> tuple:
    """Un pourcentage ou un total absent tel quel, recalculé SEULEMENT à partir des nombres ÉCRITS dans
    la phrase et reliés chacun à une source (`phrase` : (valeur, unité), l'unité d'un nombre écrit seul
    étant celle de sa source) — jamais à partir des autres nombres des faits cités (`cites`, ignoré :
    « 12 + 2 font 14 » tiré d'un effectif et d'une quantité de nacelles n'est pas un calcul de la phrase).
      • un pourcentage : ses deux nombres sont dans la phrase, d'unités compatibles (« 6 couvreurs sur
        12 salariés » font 50 %) ;
      • un total : la phrase dit « au total », « soit »…, et la SOMME de ses nombres de même unité
        (ou de même famille : personnes, matériel) tombe juste (« 3 jours et 15 jours, au total 18
        jours ») ; jamais un produit, jamais un sous-ensemble choisi pour tomber juste.
    (ok, détail) ; ok None = rien à recalculer. « Ne tombe pas juste » n'est dit que si la phrase
    donne elle-même ses deux nombres : sinon, le fait reste simplement à relire."""
    propres = _dedoublonner(phrase, v, 8)
    if u == "%":
        dec = _decimales(fait)
        tol = 0.5 * (10 ** -dec) + 1e-9
        paires = []
        for (a, ua), (b, ub) in itertools.permutations(propres, 2):
            # Une part d'un tout : « 6 couvreurs sur 12 salariés ». Jamais un nombre sur lui-même.
            if b <= 0 or a >= b or ua == "%" or ub == "%" or not _compatibles(ua, ub):
                continue
            paires.append((a, b))
        for a, b in paires:
            if abs(100.0 * a / b - v) <= tol:
                return True, f"{_fmt(a)} sur {_fmt(b)} font {_fmt(round(100.0 * a / b, dec))} %"
        if len(paires) == 1:
            a, b = paires[0]
            return False, (f"Le calcul ne tombe pas juste : {_fmt(a)} sur {_fmt(b)} font "
                           f"{_fmt(round(100.0 * a / b, max(dec, 0)))} %, pas {_fmt(v)} %.")
        return None, ""
    if not _TOTAL.search(phrase_low) or not u:
        return None, ""
    termes = [a for a, ua in propres if ua != "%" and _compatibles(ua, u)]
    if len(termes) < 2:
        return None, ""
    if _egal(sum(termes), v):
        return True, " + ".join(_fmt(x) for x in termes) + f" font {_fmt(v)}"
    if len(termes) == 2:
        return False, (f"Le total ne tombe pas juste : {_fmt(termes[0])} + {_fmt(termes[1])} font "
                       f"{_fmt(termes[0] + termes[1])}, pas {_fmt(v)}.")
    return None, ""


# ── Le contrôle ───────────────────────────────────────────────────────────────────────

def _fid(kind: str, fait: str, phrase: str) -> str:
    return far._fid(kind, fait, phrase)


def _nom_connu(key: str, noms: list) -> bool:
    """Le nom de l'entreprise ou d'un partenaire n'est pas un fait à sourcer : c'est le sujet."""
    for n in noms:
        if key and (key == n or key in n or (len(n) >= 4 and n in key)):
            return True
    return False


def _item(kind, fait, phrase, statut, message, a_propos, source=None, detail="") -> dict:
    out = {"id": _fid(kind, fait, phrase), "fait": str(fait)[:120], "type": kind, "phrase": phrase[:far.PHRASE_MAX],
           "message": message, "statut": statut, "a_propos": a_propos, "source": source}
    if detail:
        out["detail"] = detail
    return out


def est_controle_a(faits) -> bool:
    """Les faits d'une version ont-ils été relevés par A (et non par A0) ?"""
    fs = [x for x in (faits or []) if isinstance(x, dict) and x.get("type") != far.RESTE]
    return bool(fs) and all("source" in x for x in fs)


def _cle(x: dict) -> tuple:
    return far.cle_souple(x.get("type", ""), x.get("fait", ""))


def _unite_fait(x: dict) -> str:
    st = far.cle_stricte(x)
    return st[2] if len(st) == 3 else ""


_GENERIQUES = {"", "h", "jour", "semai", "mois", "an", "%"}
_MOTS_VIDES_CTX = {"nous", "notre", "nos", "votre", "vos", "pour", "dans", "avec", "sans", "sous", "sur", "chez",
                   "cette", "ces", "leur", "leurs", "depuis", "plus", "moins", "tous", "toutes", "tout", "chaque",
                   "sera", "seront", "sont", "avons", "disposons", "dispose", "comptons", "compte", "entre",
                   "apres", "avant", "ainsi", "afin", "aussi", "environ", "elle", "elles", "ils", "lors",
                   "sommes", "etre", "avoir", "etes", "serons", "ferons", "fera", "faire", "fait", "faits",
                   "permet", "permettra", "permettent", "assure", "assurons", "assurera", "assureront",
                   "mobiliserons", "mobilisons", "mobilise", "mobilisera", "proposons", "propose", "realisons",
                   "realiserons", "intervenons", "interviendra", "interviendrons", "utiliserons", "utilisons",
                   "mettons", "mettrons", "atteint", "atteindra", "represente", "representent", "dont", "celui",
                   "celle", "ceux", "lequel", "laquelle", "lesquels", "chacun", "chacune", "encore", "deja"}
_PRIORITE = {T_DOCUMENTS: 0, T_JUSTIFICATIF: 1, T_PUBLIC: 2, T_DECLARE: 3, T_ESTIMATION: 4, T_PARTENAIRE: 5}


def _priorite(f) -> tuple:
    return (_PRIORITE.get(f.type, 9), 0 if f.ref.startswith(PREUVE) else 1)


def _mots_contexte(phrase: str, fait: str) -> set:
    """Mots porteurs de sens de la phrase, hors le fait lui-même (pour un rapprochement non cité)."""
    du_fait = {re.sub(r"s$", "", w) for w in re.findall(r"[a-z0-9]{3,}", far.fold(fait))}
    return {re.sub(r"s$", "", w) for w in re.findall(r"[a-z]{4,}", far.fold(phrase))
            if w not in _MOTS_VIDES_CTX} - du_fait


def _cles_mots(mots: set) -> set:
    """Les mots de la phrase ramenés aux clés d'unité de l'Index (« compagnons » → personnes)."""
    return {_unite(w[:5]) for w in mots or ()}


def _fallback_permis(kind: str, fait: str, key, mots: set, f) -> bool:
    """Un fait que l'IA n'a pas cité ne se relie à un fait remis que si le rapprochement ne tient pas du
    hasard : un nombre sans unité, une durée ou un pourcentage exigent un mot commun entre la phrase
    et la fiche (« La pose durera 15 jours » et « Pose du zinc : 15 jours »)."""
    if kind not in (far.CHIFFRE, far.EN_LETTRES):
        return True
    _v, u = cle_nombre(kind, fait, key)
    if u not in _GENERIQUES:
        return True
    autres = {re.sub(r"s$", "", w) for w in re.findall(r"[a-z]{4,}", far.fold(f.texte))}
    return bool(mots & autres)


class _Anciens:
    """Ce que la version de départ disait de chaque fait (pour le reprendre, jamais pour blanchir)."""

    def __init__(self, anciens):
        self.items = [x for x in (anciens or []) if isinstance(x, dict) and x.get("type") != far.RESTE]
        self.schema_a = est_controle_a(self.items)
        self.par_id = {x.get("id"): x for x in self.items}
        self.relire, self.unites, self.source, self.engagements = {}, {}, {}, {}
        for x in self.items:
            if x.get("type") == ENGAGEMENT:
                self.engagements.setdefault(far.fold(x.get("fait")), x)
                continue
            c = _cle(x)
            if x.get("statut") == AVEC_SOURCE and isinstance(x.get("source"), dict):
                self.source.setdefault(c, x)
            elif x.get("statut") in (A_RELIRE, RELU):
                self.relire.setdefault(c, x)
                self.unites.setdefault(c, set()).add(_unite_fait(x))

    def etait_a_relire(self, it: dict, avec_unite: bool) -> bool:
        """Même fait (même valeur ; écrit par vous : unité compatible) déjà à relire ou relu."""
        return far._meme_fait(_cle(it), set(self.relire), _unite_fait(it), avec_unite, self.unites)


_SOURCES_FICHES = (T_DOCUMENTS, T_JUSTIFICATIF, T_DECLARE, T_PUBLIC, T_ESTIMATION, T_PARTENAIRE)


def controler(texte: str, fiches: list, *, acheteur: Optional[Acheteur] = None, noms_entreprise=(),
              section_entreprise: bool = False, mode: str = "ia", anciens=(), base_texte: str = "") -> list:
    """Tous les faits relevés d'un texte, chacun relié à sa source ou à relire (voir le module).

    mode :
      • « ia »          : texte rédigé par l'IA ; un fait non rapproché est à relire ; un fait qui
                          avait une source dans `anciens` et n'en a plus le dit (source perdue) ;
      • « raccourci »   : l'IA a raccourci `base_texte` ; un fait non rapproché garde ce qu'il était
                          dans `anciens` (sa source, ou à relire), sinon il est à relire
                          (« Raccourcir » n'ajoute rien et ne blanchit rien) ;
      • « utilisateur » : texte écrit ou modifié par vous ; un fait déjà à relire le reste, même
                          réécrit ; un fait qui avait une source la garde ; les autres sont VOS
                          déclarations ; un engagement que vous écrivez vous-même est le vôtre.
    « Relu par vous » est repris pour le même fait dans la même phrase (« raccourci » : le même fait
    avec la même unité, où qu'il soit). Le dossier de l'acheteur (`acheteur`) n'appuie JAMAIS une
    phrase sur l'entreprise ; sans lui (None), une phrase sur le marché n'est rapprochée de rien."""
    fiches = [f for f in (fiches or []) if isinstance(f, Fiche)]
    par_ref = {f.ref: f for f in fiches}
    noms = [far.fold(n) for n in (noms_entreprise or []) if n and len(far.fold(n)) >= 3]
    # Qui affirme quoi entre membres du groupement : l'apport d'un partenaire n'appuie que les phrases
    # qui le nomment ; une phrase qui nomme un partenaire (sans « nous ») ne s'appuie que sur son apport.
    partenaires = {far.fold(f.proprietaire) for f in fiches if f.type == T_PARTENAIRE and len(far.fold(f.proprietaire)) >= 3}
    les_notres = [n for n in noms if n not in partenaires]
    anc = _Anciens(anciens)
    base_src = far.Sources([base_texte]) if base_texte else None
    out, seen = [], set()

    def _ajoute(it):
        if it["id"] in seen:
            return
        seen.add(it["id"])
        old = anc.par_id.get(it["id"])
        if it["statut"] == A_RELIRE and old and old.get("statut") == RELU:
            it.update(statut=RELU, relu_par=old.get("relu_par"), relu_le=old.get("relu_le"))
        out.append(it)

    def _vous(kind, fait, ph, a_propos, detail=""):
        src = {"ref": "", "type": T_VOUS, "libelle": LIB_VOUS, "cite": False}
        if detail:
            src["detail"] = detail
        return _item(kind, fait, ph, AVEC_SOURCE, LIB_VOUS, a_propos, source=src)

    def _reprise(old_src):
        """La source d'un fait de la version de départ, si elle tient encore : votre déclaration, le
        dossier de l'acheteur, ou un fait encore remis (rafraîchi) ; None si elle est perdue."""
        osrc = dict(old_src.get("source") or {})
        if osrc.get("type") in (T_VOUS, T_ACHETEUR):
            return osrc
        f = par_ref.get(osrc.get("ref") or "")
        if f is not None and osrc.get("type") in _SOURCES_FICHES:
            return f.source(None, cite=False)
        return None

    def _sans_source(kind, fait, key, ph, a_propos, detail):
        """Aucune source dans ce texte : ce que le fait était, votre déclaration, ou à relire."""
        msg = MESSAGE if a_propos == ENTREPRISE else MSG_MARCHE
        it = _item(kind, fait, ph, A_RELIRE, msg, a_propos, detail=detail)
        c = _cle(it)
        old_src = anc.source.get(c) if anc.schema_a else None
        if mode == "utilisateur":
            if anc.etait_a_relire(it, avec_unite=True):
                return it
            if old_src is not None:
                osrc = _reprise(old_src)
                if osrc is not None:
                    return _item(kind, fait, ph, AVEC_SOURCE, osrc.get("libelle") or LIB_VOUS, a_propos, source=osrc)
                it["detail"] = DET_SOURCE_PERDUE        # sa preuve a été retirée ou a expiré
                return it
            return _vous(kind, fait, ph, a_propos)
        if mode == "raccourci":
            if old_src is not None:
                osrc = _reprise(old_src)
                if osrc is not None:
                    return _item(kind, fait, ph, AVEC_SOURCE, osrc.get("libelle") or LIB_VOUS, a_propos, source=osrc)
                it["detail"] = DET_SOURCE_PERDUE
                return it
            if anc.etait_a_relire(it, avec_unite=False):
                old = anc.relire.get(c)
                if old and old.get("statut") == RELU and far.cle_stricte(old) == far.cle_stricte(it):
                    it.update(statut=RELU, relu_par=old.get("relu_par"), relu_le=old.get("relu_le"))
                return it
            if not anc.schema_a and base_src is not None and base_src.has(kind, key):
                # Texte de départ relevé avant la vague 3 (A0) : ce fait n'y était pas à relire.
                return _vous(kind, fait, ph, a_propos, detail="repris du texte de départ")
            return it
        # « ia » : à relire ; une source qui existait et n'existe plus est dite.
        if old_src is not None and (old_src.get("source") or {}).get("type") in _SOURCES_FICHES:
            it["detail"] = DET_SOURCE_PERDUE
        return it

    for p in phrases(texte):
        ph, refs = p["phrase"], p["refs"]
        if p["titre"]:
            continue
        sur_entreprise = far.parle_entreprise(ph, noms_entreprise, section_entreprise)
        a_propos = ENTREPRISE if sur_entreprise else MARCHE
        low = far.fold(ph)
        nommes = {n for n in partenaires if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low)}
        de_nous = bool(far._ENTREPRISE.search(low)) or any(
            re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low) for n in les_notres)
        if nommes and not de_nous:
            permises = [f for f in fiches if f.type == T_PARTENAIRE and far.fold(f.proprietaire) in nommes]
        else:
            permises = [f for f in fiches if f.type != T_PARTENAIRE or far.fold(f.proprietaire) in nommes]
        citees = [par_ref[r] for r in refs if r in par_ref and (par_ref[r] in permises or par_ref[r].type == T_PARTENAIRE)]
        inconnus = [r for r in refs if r not in par_ref]
        # Nombres ÉCRITS dans la phrase et reliés à une source (le recalcul ne prend rien d'autre) :
        # (valeur, unité) — l'unité d'un nombre écrit seul (« 3 + 15 ») est celle de sa source.
        pool = []
        releves = []
        for fait, kind, key in far._facts_in(ph, tableau=p["tableau"]):
            if kind == far.NOM_PROPRE and _nom_connu(key, noms):
                continue
            src, detail, unite_src = None, "", ""
            if sur_entreprise:
                # 1. Un fait CITÉ dans la phrase, du bon type ; 2. à défaut, un fait remis non cité.
                autres = sorted((f for f in permises if f not in citees), key=_priorite)
                mots = _mots_contexte(ph, fait)
                cles = _cles_mots(mots)
                generique = kind == far.CERTIFICATION and key in _CERT_GENERIQUES
                objets = _objets(ph) - _objets(fait) if generique else set()
                for groupe, cite in ((citees, True), (autres, False)):
                    for f in groupe:
                        if not f.appuie(kind):
                            continue
                        if generique:
                            # « agréés », « certifiée », « labellisés » : jamais par un fait non cité ;
                            # un fait cité seulement s'il dit le même mot ET le même objet.
                            pos = f.index.generique(key, objets) if cite else None
                        else:
                            if not cite and not _fallback_permis(kind, fait, key, mots, f):
                                continue
                            pos = f.index.trouve(kind, key, fait, mots=cles)
                        if pos is not None:
                            src = f.source(pos, cite=cite)
                            if kind in (far.CHIFFRE, far.EN_LETTRES):
                                unite_src = f.index.unite_a(pos)
                            break
                    if src is not None:
                        break
                if src is None:
                    if any(f.type == T_ESTIMATION and f.index.trouve(kind, key, fait, mots=cles) is not None
                           for f in fiches):
                        detail = DET_ESTIMATION
                    elif acheteur is not None and acheteur.trouve(kind, key, fait) is not None:
                        detail = DET_ACHETEUR           # copie d'une exigence : ne prouve rien sur vous
                    elif inconnus:
                        detail = DET_RENVOI_INCONNU.format(ref=", ".join(inconnus))
            elif acheteur is not None:
                src = acheteur.trouve(kind, key, fait)  # phrase sur le marché : le dossier de l'acheteur
            if src is not None and sur_entreprise and kind in (far.CHIFFRE, far.EN_LETTRES):
                v_, u_ = cle_nombre(kind, fait, key)
                pool.append((v_, u_ or unite_src))
            releves.append((fait, kind, key, src, detail))
        for fait, kind, key, src, detail in releves:
            if src is None and sur_entreprise and kind in (far.CHIFFRE, far.EN_LETTRES):
                v, u = cle_nombre(kind, fait, key)
                ok, det = recalcul(v, u, fait, low, pool)
                if ok and mode == "raccourci" and (base_src is None or not base_src.has(kind, key)):
                    ok, det = None, ""      # « Raccourcir » n'ajoute aucun nombre, même calculé
                if ok:
                    src = {"ref": "", "type": T_CALCUL, "libelle": LIB_CALCUL, "cite": False, "detail": det}
                elif ok is False:
                    detail = det
            if src is not None:
                _ajoute(_item(kind, fait, ph, AVEC_SOURCE, src["libelle"], a_propos, source=src))
            else:
                _ajoute(_sans_source(kind, fait, key, ph, a_propos, detail))
        # Engagement : à confirmer (jamais pour une phrase sur le marché, ni pour VOTRE texte).
        if sur_entreprise:
            eng = engagement(ph)
            if eng:
                it = _item(ENGAGEMENT, eng, ph, A_RELIRE, MSG_ENGAGEMENT, ENTREPRISE)
                if mode != "utilisateur" or it["id"] in anc.par_id or far.fold(eng) in anc.engagements:
                    if mode == "raccourci" and it["id"] not in anc.par_id:
                        old = anc.engagements.get(far.fold(eng))
                        if old and old.get("statut") == RELU:
                            it.update(statut=RELU, relu_par=old.get("relu_par"), relu_le=old.get("relu_le"))
                    _ajoute(it)
    a_rel = [x for x in out if x["statut"] != AVEC_SOURCE]
    sources = [x for x in out if x["statut"] == AVEC_SOURCE][:MAX_SOURCES]
    return far._plafonner(a_rel) + sources


# ── Lecture : ce qui est montré, ce qui bloque ────────────────────────────────────────

def a_relire(faits) -> list:
    """Les éléments à relire ou relus par vous (forme d'A0), dans l'ordre."""
    return [x for x in (faits or []) if isinstance(x, dict) and x.get("statut") != AVEC_SOURCE]


def avec_source(faits) -> list:
    return [x for x in (faits or []) if isinstance(x, dict) and x.get("statut") == AVEC_SOURCE]


def bilan(faits) -> Optional[dict]:
    """« Faits avec une source : 7 sur 8 » d'une version relevée par A (None sinon). Les
    engagements à confirmer ne sont pas des faits : ils sont comptés à part."""
    fs = [x for x in (faits or []) if isinstance(x, dict)]
    if fs and not est_controle_a(fs):
        return None
    n = sum(1 for x in fs if x.get("type") not in (ENGAGEMENT,) and x.get("type") != far.RESTE)
    n += sum(int(x.get("nombre") or 0) for x in fs if x.get("type") == far.RESTE)
    k = sum(1 for x in fs if x.get("statut") == AVEC_SOURCE)
    e = sum(1 for x in fs if x.get("type") == ENGAGEMENT and x.get("statut") != RELU)
    return {"total": n, "avec_source": k, "sans_source": n - k, "engagements": e,
            "message": f"Faits avec une source : {k} sur {n}" if n else ""}


def refs_utilisees(faits) -> dict:
    """Renvois F et extraits S dont dépend une version (pour relire leur validité)."""
    f, s = set(), set()
    for x in avec_source(faits):
        src = x.get("source") or {}
        r = str(src.get("ref") or "")
        if r.startswith(PREUVE) and src.get("preuve_id"):
            f.add(int(src["preuve_id"]))
        elif r.startswith(EXTRAIT) and src.get("chunk_id"):
            try:
                s.add(int(src["chunk_id"]))
            except (TypeError, ValueError):
                pass
    return {"preuves": f, "extraits": s}


def ajuster(faits, valides: Optional[dict]) -> list:
    """Un fait relié à une preuve devenue inutilisable (retirée, expirée, document disparu) ou à un
    extrait dont le document a été retiré redevient À RELIRE (à la lecture, sans rien réécrire) :
    rien n'est présenté comme sourcé sur une source qui n'existe plus. `valides` =
    {"preuves": ids utilisables, "extraits": ids des morceaux encore présents} ; None = tel quel."""
    if not valides:
        return list(faits or [])
    out = []
    for x in faits or []:
        if not isinstance(x, dict) or x.get("statut") != AVEC_SOURCE:
            out.append(x)
            continue
        src = x.get("source") or {}
        r = str(src.get("ref") or "")
        perdu = (r.startswith(PREUVE) and src.get("preuve_id") and int(src["preuve_id"]) not in valides["preuves"]) or \
                (r.startswith(EXTRAIT) and src.get("chunk_id") and int(src["chunk_id"]) not in valides["extraits"])
        if not perdu:
            out.append(x)
            continue
        out.append(source_perdue(x))
    return out


def source_perdue(x: dict) -> dict:
    """Le même fait (même identifiant), redevenu à relire : sa source n'est plus utilisable."""
    return dict(x, statut=A_RELIRE, source=None, detail=DET_SOURCE_PERDUE,
                message=MESSAGE if x.get("a_propos", ENTREPRISE) == ENTREPRISE else MSG_MARCHE)


def valides(db, owner_id: int, member_ids: list, project_id: Optional[int], faits_listes: Iterable) -> dict:
    """Preuves et extraits encore utilisables, pour les renvois des versions données."""
    from app.services import preuves as pv
    from app.models import KnowledgeChunk
    pids, cids = set(), set()
    for fs in faits_listes:
        r = refs_utilisees(fs)
        pids |= r["preuves"]
        cids |= r["extraits"]
    ok_p, ok_c = set(), set()
    if pids:
        ok_p = {f["id"] for f in pv.faits_autorises(db, owner_id, project_id=project_id) if f["id"] in pids}
    if cids:
        ok_c = {r[0] for r in db.query(KnowledgeChunk.id).filter(KnowledgeChunk.id.in_(list(cids)),
                                                                 KnowledgeChunk.user_id.in_(list(member_ids))).all()}
    return {"preuves": ok_p, "extraits": ok_c}


# ── CV : insérés tels quels, sans IA (décision 8a) ─────────────────────────────────────

def cv_texte(fiche: Fiche) -> str:
    """Le CV minimal d'une fiche « Équipe », en Markdown, chaque ligne avec son renvoi (pour que le
    contrôle relie chaque fait à la fiche). Jamais remis à l'IA.

    Les lignes du CV sont CELLES de « Mes preuves » (`preuves_atelier.lignes_cv`, E1) : un CV inséré
    par « [CV F2] » et un CV inséré par « Insérer une fiche » s'écrivent pareil, et le garde-fou de
    « Raccourcir » (`preuves_atelier.refuser_cv_pour_ia`) les reconnaît tous les deux."""
    from app.services.preuves_atelier import lignes_cv
    v = fiche.valeur or {}
    r = f" [{fiche.ref}]"
    fonction = str(v.get("fonction") or "")
    if len(fonction) > 1 and fonction[:1].isupper() and fonction[1:2].islower():
        fonction = fonction[:1].lower() + fonction[1:]       # « Maëlys Kerbrat, conductrice de travaux »
    lignes = [f"**{v.get('nom', '')}**, {fonction}{r}"]
    lignes += [f"- {ln}{r}" for ln in lignes_cv(v)]
    return "\n".join(lignes)


def inserer_cv(texte: str, fiches: list) -> str:
    """Remplace chaque « [CV F7] » par le CV de la fiche « Équipe » F7, tel quel ; un renvoi qui ne
    désigne pas une fiche « Équipe » utilisable devient « [À compléter : CV de la personne] »."""
    par_ref = {f.ref: f for f in fiches or [] if isinstance(f, Fiche) and f.nature == "salarie"
               and f.ref.startswith(PREUVE)}

    def _sub(m):
        f = par_ref.get(f"{PREUVE}{int(m.group(1))}")
        return cv_texte(f) if f is not None else "[À compléter : CV de la personne]"
    t = _CV.sub(lambda m: _sub(m), str(texte or ""))
    return _CV_INLINE.sub(lambda m: "\n" + _sub(m) + "\n", t)


# ── « Ajouter une source » ─────────────────────────────────────────────────────────────

def fiche_contient(fiche: Fiche, item: dict) -> bool:
    """La fiche contient-elle CE fait (même valeur et même unité, même certification, nom, matériel) ?"""
    kind, fait = item.get("type", ""), item.get("fait", "")
    if kind == ENGAGEMENT or not fait:
        return False
    phrase = item.get("phrase") or fait

    def _dans(f2, key, ph):
        if not fiche.appuie(kind):
            return False
        if kind == far.CERTIFICATION and key in _CERT_GENERIQUES:
            return fiche.index.generique(key, _objets(ph) - _objets(f2)) is not None
        return fiche.index.trouve(kind, key, f2, mots=_cles_mots(_mots_contexte(ph, f2))) is not None
    for f2, k2, key in far._facts_in(phrase, tableau=far.CASE in phrase):
        if k2 == kind and far.fold(f2) == far.fold(fait):
            return _dans(f2, key, phrase)
    for f2, k2, key in far._facts_in(fait):
        if k2 == kind:
            return _dans(f2, key, fait)
    return False


def proposition_declaration(item: dict) -> dict:
    """La fiche « déclaré par vous » proposée pour un fait à relire (l'utilisateur la corrige
    avant de l'enregistrer) : {natures, nature, valeur}."""
    kind, fait, phrase = item.get("type", ""), str(item.get("fait") or ""), str(item.get("phrase") or "")
    if kind in (far.CHIFFRE, far.EN_LETTRES):
        v, u = None, ""
        for f2, k2, key in far._facts_in(phrase, tableau=far.CASE in phrase):
            if k2 == kind and far.fold(f2) == far.fold(fait):
                v, u = cle_nombre(kind, f2, key)
                break
        unite = ""
        # Le mot compté : celui qui suit le nombre (« 15 compagnons » → « compagnons »).
        if kind == far.CHIFFRE:
            m = far._NUMBER.match(fait.strip())
            mot = far.unite_de(m)
        else:
            m = re.search(re.escape(fait) + r"\s+([^\s\d.,;:()]{2,30})", phrase)
            mot = m.group(1) if m else ""
        if far.fold(mot) in far._PAS_UNITE:
            mot = ""
        if u == "%":
            unite, libelle = "%", "Part"
        elif u == "€":
            unite, libelle = "€", "Montant"
        elif u in ("h", "jour", "semai", "mois", "an"):
            unite, libelle = mot or u, "Délai"
        else:
            libelle = (mot[:1].upper() + mot[1:]) if mot else "Chiffre"
        val = {"libelle": libelle[:120]}
        if v is not None:
            val["valeur"] = int(v) if float(v).is_integer() else v
        if unite:
            val["unite"] = unite[:40]
        return {"natures": ["chiffre_cle"], "nature": "chiffre_cle", "valeur": val}
    if kind == far.CERTIFICATION:
        nom = fait
        if far.fold(fait)[:4] in ("cert", "labe", "agre"):
            # « agréés pour le retrait de l'amiante » : le mot générique ET son objet (sinon la fiche ne
            # dirait pas de quoi l'entreprise est agréée, et ne pourrait appuyer la phrase).
            i = far.fold(phrase).find(far.fold(fait))
            if i >= 0:
                nom = re.split(r"[.;:!?]", phrase[i:])[0].strip()
        return {"natures": ["qualification"], "nature": "qualification", "valeur": {"nom": nom[:200]}}
    if kind == far.MATERIEL:
        return {"natures": ["materiel"], "nature": "materiel", "valeur": {"designation": fait[:200]}}
    if kind == far.NOM_PROPRE:
        return {"natures": ["reference", "salarie"], "nature": "reference",
                "valeur": {"objet": "", "acheteur": fait[:200]}}
    return {"natures": [], "nature": "", "valeur": {}}
