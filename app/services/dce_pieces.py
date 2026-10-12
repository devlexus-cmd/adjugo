"""
Lecture pièce par pièce du dossier du marché (rédaction, vague 1 — C0).

Pourquoi : l'IA ne lisait pas « le dossier complet ». Dans un ZIP, les PDF passaient avant
les Word, par ordre alphabétique, jusqu'au plafond de caractères : un cadre de réponse .docx
rangé derrière un gros CCTP disparaissait, et avec CCTP.pdf + RC.pdf + Cadre_reponse.docx
c'était le règlement de la consultation lui-même qui sautait (sonde de l'étude rédaction, §2).

Ici, SANS IA :
  • chaque pièce est reconnue par son nom puis, à défaut, par ses premières lignes
    (règlement de consultation, cadre de réponse, CCAP, CCTP, bordereaux de prix, acte
    d'engagement, autre) ;
  • l'ordre de LECTURE d'une archive commence par le règlement et le cadre de réponse ;
  • l'assemblage du texte (`compose`) garde le règlement et le cadre EN ENTIER, puis partage
    équitablement le reste du plafond entre les autres pièces (un CCTP de 900 articles ne
    fait plus disparaître l'acte d'engagement ni le bordereau).
Les plafonds de sécurité de l'extraction (octets, pages, temps, OCR) restent ceux
d'app.services.analysis, appliqués pièce par pièce.

Module SANS dépendance applicative (bibliothèque standard seulement) : importé par
analysis.py et grille_notation.py sans risque d'import circulaire.
"""
import re
import unicodedata

# ── Types de pièces ──────────────────────────────────────────────────────────────────

REGLEMENT = "reglement"
CADRE = "cadre"
CCAP = "ccap"
CCTP = "cctp"
BORDEREAU = "bordereau"
ACTE_ENGAGEMENT = "acte_engagement"
AUTRE = "autre"

TYPES = (REGLEMENT, CADRE, CCAP, CCTP, BORDEREAU, ACTE_ENGAGEMENT, AUTRE)

LABELS = {
    REGLEMENT: "Règlement de la consultation",
    CADRE: "Cadre de réponse",
    CCAP: "Clauses administratives (CCAP)",
    CCTP: "Clauses techniques (CCTP)",
    BORDEREAU: "Bordereau de prix",
    ACTE_ENGAGEMENT: "Acte d'engagement",
    AUTRE: "Autre pièce",
}

# Pièces lues EN PREMIER et EN ENTIER (la grille de notation et le cadre imposé y sont).
PRIORITAIRES = (REGLEMENT, CADRE)

# Ordre de LECTURE dans une archive (avant de connaître le contenu) : règlement, cadre, puis
# les pièces au nom inconnu (souvent un règlement mal nommé), et les gros cahiers en dernier.
_READ_RANK = {REGLEMENT: 0, CADRE: 1, AUTRE: 2, ACTE_ENGAGEMENT: 3, CCAP: 4, BORDEREAU: 5, CCTP: 6}
# Ordre d'ASSEMBLAGE du texte remis à l'analyse.
_COMPOSE_RANK = {REGLEMENT: 0, CADRE: 1, ACTE_ENGAGEMENT: 2, CCAP: 3, CCTP: 4, BORDEREAU: 5, AUTRE: 6}


def read_rank(kind: str) -> int:
    return _READ_RANK.get(kind, 2)


def compose_rank(kind: str) -> int:
    return _COMPOSE_RANK.get(kind, 6)


# ── Normalisation ────────────────────────────────────────────────────────────────────

def fold(s: str) -> str:
    """Minuscules sans accents, MÊME LONGUEUR que l'entrée (caractère par caractère) :
    une position trouvée dans la version repliée vaut dans l'original."""
    out = []
    for c in str(s or ""):
        d = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
        if len(d) != 1:
            d = c
        lo = d.lower()
        out.append(lo if len(lo) == 1 else d)
    t = "".join(out)
    return t.replace("’", "'").replace("‘", "'").replace("ʼ", "'")


def _name_key(name: str) -> str:
    """Nom de fichier → mots séparés par des espaces, sans extension ni accents."""
    base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"\.(pdf|docx?|odt|txt|md|csv|xlsx?|ods|zip)$", "", base, flags=re.IGNORECASE)
    base = fold(base)
    base = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", base)      # « RC2026 » → « rc 2026 »
    return " " + re.sub(r"[^a-z0-9']+", " ", base).strip() + " "


# Motifs « en toutes lettres » (sûrs) et abréviations (à confirmer par le contenu).
_NAME_STRONG = (
    # « Règlement » seul vaut règlement de la consultation (« 01_Reglement.pdf »), mais pas
    # « Règlement de voirie », « Règlement du PLU », « règlement des comptes » (CCAP)…
    (REGLEMENT, r"reglement (particulier )?(de |du )?(la )?consult|reglement de (la )?mise en concurrence"
                r"|\breglement\b(?! (?:de |du |des |d'|interieur|sanitaire|general|municipal|local))"),
    (CADRE, r"cadre (de |du )?(la )?(reponse|memoire)|cadre (technique|de reponse technique)|trame (de |du )?(la )?(reponse|memoire)"
            r"|modele (de |du )?memoire|questionnaire( technique)?|memoire technique|cadre memoire"),
    (CCAP, r"cahier (des )?clauses administratives|clauses administratives particulieres"),
    (CCTP, r"cahier (des )?clauses techniques|clauses techniques particulieres|cahier (des )?charges"),
    (BORDEREAU, r"bordereau (des |de )?prix|decomposition (du |de |des )?prix|detail quantitatif|detail estimatif"
                r"|prix unitaires|devis quantitatif"),
    (ACTE_ENGAGEMENT, r"acte d ?'? ?engagement"),
)
_NAME_ABBR = (
    (REGLEMENT, r"\b(rc|rdc|rpc)\b"),
    (CADRE, r"\b(crt|cmt|crmt|cdrt)\b"),
    (CCAP, r"\b(ccap|cca)\b"),
    (CCTP, r"\b(cctp|cdc|cct|cdct)\b"),
    (BORDEREAU, r"\b(dpgf|bpu|dqe|dpu|cdpgf)\b"),
    (ACTE_ENGAGEMENT, r"\b(ae|attri ?1)\b"),
)
# Titres reconnus dans les premières lignes (jamais d'abréviation seule : « le présent RC »).
_HEAD = (
    (REGLEMENT, r"reglement (particulier )?(de |du )?(la )?consultation"),
    (CADRE, r"cadre (de |du )?(la )?(reponse|memoire)|trame (de |du )?(la )?(reponse|memoire)|questionnaire technique"
            r"|cadre technique de reponse"),
    (CCAP, r"cahier des clauses administratives particulieres"),
    (CCTP, r"cahier des clauses techniques particulieres|cahier des charges"),
    (BORDEREAU, r"decomposition du prix global|bordereau des prix|detail quantitatif estimatif|bordereau de prix"),
    (ACTE_ENGAGEMENT, r"acte d'engagement"),
)
HEAD_CHARS = 2000


def _matches(patterns, s: str) -> list:
    """[(type, position)] du premier repérage de chaque type, dans l'ordre du texte."""
    out = []
    for kind, pat in patterns:
        m = re.search(pat, s)
        if m:
            out.append((kind, m.start()))
    return sorted(out, key=lambda x: x[1])


def _earliest(patterns, s: str):
    found = _matches(patterns, s)
    return found[0][0] if found else None


_ANNEXE = re.compile(r"\bannexe")


def _annexe_du_reglement(s: str, found: list):
    """« Annexe 1 au règlement de la consultation – Cadre de réponse », « Annexe_1_RC_DPGF » : la
    pièce est l'ANNEXE (cadre, bordereau…), pas le règlement qu'elle cite. Renvoie son type, ou
    None si ce n'est pas le cas."""
    if not _ANNEXE.search(s) or not any(k == REGLEMENT for k, _p in found):
        return None
    autres = [x for x in found if x[0] != REGLEMENT]
    return autres[0][0] if autres else None


def classify_name(name: str):
    """(type, sûr) d'après le NOM seul. sûr=False pour une abréviation (RC, AE…)."""
    k = _name_key(name)
    strong, abbr = _matches(_NAME_STRONG, k), _matches(_NAME_ABBR, k)
    annexe = _annexe_du_reglement(k, strong + abbr)
    if annexe:
        return annexe, True
    if strong:
        return strong[0][0], True
    if abbr:
        return abbr[0][0], False
    return AUTRE, False


def classify_head(text: str) -> str:
    """Type d'après les PREMIÈRES lignes (le titre arrive en tête) ; AUTRE si rien. Une annexe
    titrée « Annexe 2 au règlement de la consultation – Cadre de réponse technique » est un
    cadre de réponse."""
    head = re.sub(r"\s+", " ", fold((text or "")[:HEAD_CHARS]))
    found = _matches(_HEAD, head)
    if found and found[0][0] == REGLEMENT:
        lead = head[max(0, found[0][1] - 40):found[0][1]]
        if _ANNEXE.search(lead):
            autres = [x for x in found if x[0] != REGLEMENT and x[1] - found[0][1] < 200]
            if autres:
                return autres[0][0]
            abbr = [x for x in _matches(_NAME_ABBR, head[found[0][1]:found[0][1] + 200]) if x[0] != REGLEMENT]
            if abbr:
                return abbr[0][0]
    return found[0][0] if found else AUTRE


def classify_piece(name: str, text: str = "") -> str:
    """Type d'une pièce, sans IA : le nom en toutes lettres prime ; une abréviation cède devant
    un titre contraire dans les premières lignes ; un nom muet laisse parler le contenu."""
    by_name, sure = classify_name(name)
    if sure:
        return by_name
    by_head = classify_head(text) if text else AUTRE
    if by_name != AUTRE:
        return by_head if by_head not in (AUTRE, by_name) else by_name
    return by_head


def label(kind: str) -> str:
    return LABELS.get(kind, LABELS[AUTRE])


# ── Texte assemblé : en-têtes « === nom === » ─────────────────────────────────────────

HEADER_RE = re.compile(r"^=== (.{1,200}?) ===[ \t]*$", re.MULTILINE)


def header(name: str) -> str:
    n = re.sub(r"[\r\n]+", " ", str(name or "pièce")).strip()[:200] or "pièce"
    return f"=== {n} ==="


def split_pieces(text: str) -> list:
    """Découpe un texte assemblé par `compose` en [{nom, texte, debut}] (debut = position du
    corps dans le texte). Sans en-tête : une seule pièce au nom vide."""
    text = text or ""
    ms = list(HEADER_RE.finditer(text))
    if not ms:
        return [{"nom": "", "texte": text, "debut": 0}]
    out = []
    pre = text[:ms[0].start()].strip()
    if pre:
        out.append({"nom": "", "texte": text[:ms[0].start()], "debut": 0})
    for i, m in enumerate(ms):
        start = m.end() + 1 if text[m.end():m.end() + 1] == "\n" else m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out.append({"nom": m.group(1), "texte": text[start:end], "debut": start})
    return out


def typed_pieces(text: str) -> list:
    """split_pieces + type et libellé de chaque pièce (même classement qu'à l'extraction)."""
    out = []
    for p in split_pieces(text):
        k = classify_piece(p["nom"], p["texte"])
        out.append(dict(p, type=k, libelle=label(k)))
    return out


def water_fill(lengths: list, budget: int) -> list:
    """Partage équitable d'un budget : les petites pièces passent en entier, les grosses se
    partagent le reste à parts égales. Renvoie l'allocation de chaque pièce (même ordre)."""
    alloc = [0] * len(lengths)
    left = max(0, int(budget))
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    n = len(order)
    for rank, i in enumerate(order):
        share = left // max(1, (n - rank))
        give = min(lengths[i], share)
        alloc[i] = give
        left -= give
    return alloc


def compose(pieces: list, max_chars: int, headers: bool = None):
    """Assemble les pièces en un texte borné à `max_chars`.

    pieces : [{nom, texte, type?, complet?}] dans l'ordre de lecture. Le règlement et le cadre
    de réponse passent EN PREMIER et EN ENTIER (dans la limite du plafond, partagé entre eux
    s'ils le dépassent ensemble) ; les autres pièces se partagent équitablement ce qui reste.
    headers : en-tête « === nom === » devant chaque pièce (défaut : dès qu'il y a 2 pièces).
    Renvoie (texte, meta) — meta : [{nom, type, libelle, caracteres, lu_en_entier}] dans
    l'ordre du texte."""
    items = []
    for idx, p in enumerate(pieces or []):
        t = p.get("texte") or ""
        k = p.get("type") or classify_piece(p.get("nom", ""), t)
        items.append({"nom": p.get("nom") or "", "texte": t, "type": k, "idx": idx,
                      "complet": p.get("complet", True)})
    items.sort(key=lambda x: (compose_rank(x["type"]), x["idx"]))
    with_headers = (len(items) > 1) if headers is None else bool(headers)
    sep = "\n\n"

    def _cost(x):
        return len(header(x["nom"])) + 1 if with_headers else 0

    budget = max(0, int(max_chars))
    prio = [x for x in items if x["type"] in PRIORITAIRES]
    rest = [x for x in items if x["type"] not in PRIORITAIRES]
    alloc = {}
    room = budget - sum(_cost(x) for x in items) - len(sep) * max(0, len(items) - 1)
    a = water_fill([len(x["texte"]) for x in prio], max(0, room))
    for x, n in zip(prio, a):
        alloc[x["idx"]] = n
    room -= sum(a)
    b = water_fill([len(x["texte"]) for x in rest], max(0, room))
    for x, n in zip(rest, b):
        alloc[x["idx"]] = n

    parts, meta = [], []
    for x in items:
        n = alloc.get(x["idx"], 0)
        if n <= 0 and x["texte"]:
            meta.append({"nom": x["nom"], "type": x["type"], "libelle": label(x["type"]),
                         "caracteres": 0, "lu_en_entier": False})
            continue
        body = x["texte"][:n]
        parts.append((header(x["nom"]) + "\n" + body) if with_headers else body)
        meta.append({"nom": x["nom"], "type": x["type"], "libelle": label(x["type"]),
                     "caracteres": len(body),
                     "lu_en_entier": bool(x["complet"]) and len(body) >= len(x["texte"])})
    return sep.join(parts)[:budget], meta
