"""
Noms des salariés : jamais envoyés au service d'IA (doctrine § 7, règle 9).

Avant chaque appel à l'IA, le nom de chaque personne de l'équipe (« Yann Tanguy ») est remplacé
par une étiquette stable tirée de sa fonction (« [Chef de chantier 1] ») ; la réponse de l'IA est
ensuite remise en clair, SANS IA, par simple remplacement de l'étiquette par le nom.

Le remplacement est fait au point d'entrée central (app.services.llm.messages_create) dès qu'un
`pii_scope` est actif : tout appel passé dans la portée est couvert, y compris les appels internes
(fusion des apports d'un groupement, contrôle de conformité) et le texte des documents du
savoir-faire (un CV déposé, par exemple).

Ce qui est reconnu, sans tenir compte des accents ni de la casse :
- le nom complet, dans les deux ordres (« Yann Tanguy », « TANGUY Yann », « CV_Yann_Tanguy.pdf ») :
  étiquette de la personne, remise en clair par son nom complet ;
- chaque morceau du nom employé seul (« M. Tanguy », « Mme Le Gall », « Yann »), s'il commence par
  une majuscule et hors mot composé (« Saint-Martin » n'est pas touché pour un salarié nommé
  Martin) : étiquette neutre « [Nom N] », remise en clair TELLE QUELLE. Rien n'est donc attribué
  à la mauvaise personne (un « M. Martin » de la mairie reste « M. Martin ») ;
- un morceau qui est aussi un mot courant (« Petit », « Claire ») n'est masqué seul que derrière
  une civilité (« M. Petit »).

- une adresse e-mail qui contient un morceau du nom, quelle que soit la casse
  (« yann.tanguy@btp-breizh.fr », « ytanguy29@gmail.com ») : remplacée en entier par une
  étiquette « [Courriel N] », remise en clair telle quelle.

Limites assumées : un nom écrit autrement (initiale seule, faute de frappe) n'est pas reconnu ; un
prénom qui est aussi un mot courant (« Claire », « Pierre ») n'est masqué seul que derrière une
civilité ; les autres informations d'un CV (téléphone, adresse postale) ne sont pas masquées.
"""
import re
import threading
import unicodedata
from typing import Iterable, Optional

# Particules jamais masquées seules (trop courantes) : « Le Gall » est reconnu en entier et par « Gall ».
_PARTICULES = {"le", "la", "les", "de", "du", "des", "d", "l", "van", "von", "der", "den", "da", "di",
               "del", "dos", "ben", "bin", "el", "al", "mc", "mac", "st", "ste", "saint", "sainte"}

# Noms et prénoms qui sont aussi des mots courants : seuls, ils ne sont masqués que derrière une
# civilité (le nom complet, lui, l'est toujours).
_MOTS_COURANTS = {
    "petit", "petite", "grand", "grande", "blanc", "blanche", "noir", "brun", "roux", "rouge", "bon",
    "bonne", "fort", "long", "court", "doux", "gros", "jeune", "beau", "franc", "vincent", "laurent",
    "marchand", "boucher", "boulanger", "charpentier", "couvreur", "masson", "mercier", "meunier",
    "berger", "chevalier", "fontaine", "bois", "lac", "rivière", "riviere", "maison", "lemaire",
    "pierre", "claire", "rose", "olive", "marguerite", "aime", "victoire", "constant", "prudent",
    "juste", "sage", "parfait", "colombe", "france", "paris", "salle", "page", "porte", "roche",
}
_CIVILITE = re.compile(r"(?:\bM\.|\bMM\.|\bMme|\bMlle|\bMr|\bMonsieur|\bMadame|\bMademoiselle|\bDr\.?|\bMe)\s*$")

_ACCENTS = {
    "a": "aàâäáãå", "e": "eéèêë", "i": "iîïíì", "o": "oôöóòõ", "u": "uûüùú",
    "c": "cç", "y": "yÿý", "n": "nñ",
}

# Étiquette : crochets + libellé court ; rien qui puisse casser un JSON ou une balise.
_LABEL_BAD = re.compile(r"[\[\]{}<>\"\\|#*_`]+")
_HINT = ("Les noms de personnes sont remplacés par des étiquettes entre crochets (par exemple "
         "« {ex} » ou « [Nom 1] »). Recopie ces étiquettes telles quelles, crochets compris, sans les "
         "modifier et sans inventer de nom.")
_EMAIL = re.compile(r"(?<![\w.%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}\.)+[A-Za-z]{2,24}\b")


def _plain(s) -> str:
    """Minuscule, sans accents, apostrophes et tirets ramenés à une espace, espaces réduits."""
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[’'`\-_]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _clean_name(s) -> str:
    t = re.sub(r"[\x00-\x1f\"\\\[\]{}<>]", " ", str(s or ""))
    return re.sub(r"\s+", " ", t).strip()[:120]


def _char_class(ch: str) -> str:
    low = ch.lower()
    for base, variants in _ACCENTS.items():
        if low in variants:
            return "[" + variants + variants.upper() + "]"
    if ch in "-’'_" or ch.isspace():
        return r"[\s\-’'_]+"     # « Yann Tanguy », « Jean-Pierre », « CV_Yann_Tanguy.pdf »
    return re.escape(ch)


def _pattern(phrase: str) -> str:
    return "".join(_char_class(c) for c in phrase)


def _tokens(name: str) -> list:
    return [t for t in re.split(r"\s+", name) if t]


class Pseudonymizer:
    """Remplace les noms connus par des étiquettes et les remet en clair (sans IA)."""

    def __init__(self, people: Optional[Iterable] = None):
        self._to_label = {}       # forme normalisée (_plain) → étiquette
        self._first_upper = set()  # formes normalisées « mot seul » : majuscule initiale exigée
        self._back = {}           # étiquette (minuscule) → texte remis en clair
        self.labels = []          # [(étiquette, nom)] dans l'ordre de l'équipe
        self._rx = None
        self._mail_tokens = set()  # morceaux de nom cherchés dans les adresses e-mail
        self._mails = {}          # adresse (minuscule) → étiquette « [Courriel N] »
        self._lock = threading.Lock()
        self._build([p for p in (people or []) if isinstance(p, dict)])

    # ── Construction ──────────────────────────────────────────────────────────
    def _build(self, people: list) -> None:
        persons, counters = [], {}
        for p in people:
            name = _clean_name(p.get("nom") or p.get("name"))
            if len(_plain(name)) < 2:
                continue
            persons.append((name, p.get("fonction") or p.get("role") or ""))
        all_tokens = {_plain(t) for n, _f in persons for t in _tokens(n)}
        for name, fonction in persons:
            if _plain(name) in self._to_label:    # même personne saisie deux fois : une étiquette
                continue
            role = _LABEL_BAD.sub(" ", str(fonction or "")).strip()
            role = re.sub(r"\s+", " ", role)[:40].strip(" .,;:-")
            # Une fonction qui contient un nom de l'équipe ne sert pas d'étiquette (elle le ferait fuir).
            if not role or any(w in all_tokens for w in _plain(role).split()
                               if len(w) > 1 and w not in _PARTICULES):
                role = "Collaborateur"
            role = role[0].upper() + role[1:]
            key = _plain(role)
            counters[key] = counters.get(key, 0) + 1
            label = f"[{role} {counters[key]}]"
            self.labels.append((label, name))
            self._back[label.lower()] = name
            toks = _tokens(name)
            forms = {_plain(name)}
            if len(toks) >= 2:
                forms.add(_plain(" ".join(toks[1:] + toks[:1])))   # « Tanguy Yann », « Le Gall Jean »
            for f in forms:
                self._to_label.setdefault(f, label)
        # Morceaux du nom employés SEULS (« M. Tanguy », « Mme Le Gall », « Yann ») : étiquette
        # neutre « [Nom N] », remise en clair telle quelle. Jamais l'étiquette de la personne : un
        # « M. Martin » du dossier de l'acheteur ne doit pas devenir notre chef de chantier.
        n_tok = 0
        for name, _f in persons:
            toks = _tokens(name)
            parts = list(toks)
            if len(toks) >= 3:
                parts.append(" ".join(toks[1:]))                  # nom de famille composé : « Le Gall »
            for t in sorted(parts, key=len, reverse=True):
                pt = _plain(t)
                if pt in self._to_label or len(pt) < 2 or all(w in _PARTICULES for w in pt.split()):
                    continue
                n_tok += 1
                neutral = f"[Nom {n_tok}]"
                self._back[neutral.lower()] = t
                self._to_label[pt] = neutral
                self._first_upper.add(pt)
        for name, _f in persons:
            for t in _tokens(name):
                for w in _plain(t).split():
                    if len(w) >= 3 and w not in _PARTICULES:
                        self._mail_tokens.add(w)
        if self._to_label:
            alts = sorted(self._to_label.keys(), key=len, reverse=True)
            body = "|".join(_pattern(a) for a in alts)
            # Bornes : ni lettre ni chiffre, ni tiret, ni apostrophe collée (mot composé) ; le
            # tiret bas reste une séparation (noms de fichiers : « CV_Yann_Tanguy.pdf »).
            self._rx = re.compile(r"(?<![^\W_])(?<!-)(?:" + body + r")(?![^\W_]|-|['’][^\W_])",
                                  re.IGNORECASE)

    # ── API ───────────────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return self._rx is not None

    def label_of(self, name: str) -> str:
        return self._to_label.get(_plain(name), "")

    def _mask_mails(self, text: str) -> str:
        """Adresses e-mail qui contiennent un morceau d'un nom de l'équipe → « [Courriel N] »."""
        def _sub(m):
            raw = m.group(0)
            local = _plain(raw.split("@", 1)[0].replace(".", " "))
            flat = local.replace(" ", "")
            if not any(t in flat for t in self._mail_tokens):
                return raw
            with self._lock:
                label = self._mails.get(raw.lower())
                if label is None:
                    label = f"[Courriel {len(self._mails) + 1}]"
                    self._mails[raw.lower()] = label
                    self._back[label.lower()] = raw
            return label
        return _EMAIL.sub(_sub, text)

    def uses_labels(self, text: str) -> bool:
        """Le texte contient-il une étiquette posée par ce pseudonymiseur ?"""
        t = str(text or "")
        return any(lbl in t for lbl, _n in self.labels) or "[Nom " in t or "[Courriel " in t

    def mask(self, text: str) -> str:
        if not self._rx or not text:
            return text or ""
        text = self._mask_mails(str(text))

        def _sub(m):
            raw = m.group(0)
            key = _plain(raw)
            label = self._to_label.get(key)
            if not label:
                return raw
            if key in self._first_upper and not raw[:1].isupper():
                return raw          # « martin » minuscule (nom commun) : laissé tel quel
            # Mot seul qui est aussi un mot courant (« Petit », « Claire », « Pierre ») : masqué
            # seulement derrière une civilité (« M. Petit ») ; sinon « Petit chantier » en début de
            # phrase deviendrait, une fois remis en clair, « Jean Petit chantier ».
            if key in _MOTS_COURANTS and not _CIVILITE.search(m.string[max(0, m.start() - 14):m.start()]):
                return raw
            return label
        return self._rx.sub(_sub, str(text))

    def unmask(self, text: str) -> str:
        if not self._back or not text:
            return text or ""
        with self._lock:
            back = dict(self._back)
        rx = re.compile("|".join(re.escape(k) for k in sorted(back, key=len, reverse=True)),
                        re.IGNORECASE)
        return rx.sub(lambda m: back.get(m.group(0).lower(), m.group(0)), str(text))

    def hint(self) -> str:
        ex = self.labels[0][0] if self.labels else "[Chef de chantier 1]"
        return _HINT.format(ex=ex)

    def mask_content(self, content):
        """Contenu façon Anthropic : texte, ou liste de blocs {"type": "text", "text": …}."""
        if isinstance(content, str):
            return self.mask(content)
        if isinstance(content, list):
            out = []
            for b in content:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    b = dict(b, text=self.mask(b["text"]))
                out.append(b)
            return out
        return content


def from_team(team) -> Pseudonymizer:
    return Pseudonymizer(team if isinstance(team, list) else [])


def team_of_users(db, user_ids: Iterable) -> list:
    """Équipes (profil entreprise) des organisations de ces comptes, sans doublon."""
    out, seen = [], set()
    try:
        from app.models import Company, User
        from app.core.org import data_owner_id
        owners = set()
        for uid in {u for u in (user_ids or []) if u}:
            u = db.get(User, uid)
            owners.add(data_owner_id(u, db) if u is not None else uid)
        for c in db.query(Company).filter(Company.user_id.in_(list(owners))).all() if owners else []:
            for m in (c.team or []):
                if isinstance(m, dict):
                    k = _plain(m.get("nom"))
                    if k and k not in seen:
                        seen.add(k)
                        out.append(m)
    except Exception:
        import logging
        logging.getLogger("adjugo").warning("équipe introuvable pour masquer les noms (comptes %s)", user_ids)
    return out
