"""
Textes VISIBLES de l'interface et des courriels (réorganisation, vague 0 « dire juste » ; contrat :
docs/REORGANISATION_V1.md, § 0).

Extraction sans dépendance, volontairement simple et prudente :
  - HTML : texte entre les balises (commentaires, <style> et <script> retirés), attributs lus par une personne
    (title, placeholder, aria-label, alt, label, content), chaînes des liaisons Vue (:title="…", {{ … }}) et des
    scripts intégrés ;
  - JavaScript : littéraux de chaîne (commentaires et expressions régulières retirés), sauf les chaînes qui
    ressemblent à une clé ou à un chemin (« dpgf_lot », « /api/… ») ;
  - Python : chaînes des fonctions qui envoient un courriel, et messages d'erreur rendus à l'écran
    (HTTPException), docstrings et journaux exclus.

MOTS_BANNIS : la liste de l'étude (§ 9, critère de fin de la vague 1). Les clés internes, noms de champs et
pages juridiques ne sont pas des textes visibles ; les rares exceptions assumées sont listées, avec leur raison,
dans EXCEPTIONS (tests/test_reorganisation_v1_socle.py).
"""
import ast
import re

MOTS_BANNIS = [
    ("co-traitant", re.compile(r"co-?trait", re.I)),
    ("consortium", re.compile(r"consortium", re.I)),
    ("AO", re.compile(r"(?<![A-Za-zÀ-ÿ])AOs?(?![A-Za-zÀ-ÿ])")),
    ("mémoire", re.compile(r"m[ée]moires?\b", re.I)),
    ("maître d'ouvrage", re.compile(r"ma[iî]tres? d['’]ouvrage", re.I)),
    ("agent", re.compile(r"\bagents?\b", re.I)),
    ("cockpit", re.compile(r"cockpit", re.I)),
    ("DPGF", re.compile(r"dpgf", re.I)),
    ("CERFA", re.compile(r"cerfa", re.I)),
    ("SIRENE", re.compile(r"sirene", re.I)),
    ("GO/NO-GO", re.compile(r"(?<![A-Za-z])(GO|NO-GO|No-Go|no-go|Go/No)(?![A-Za-z])")),
]
_CLE = re.compile(r"[\w./:#?=&{}$-]*")      # clé, identifiant, chemin : pas un texte lu par une personne


# Dans une chaîne qui fabrique du HTML (invite.html, composants) : ces attributs ne sont pas lus par une personne.
_ATTR_TECHNIQUES = re.compile(r"""\s(?:id|class|for|name|role|type|tabindex|style|href|src|aria-(?:labelledby|"""
                              r"""controls|describedby)|data-[\w-]+)=(?:"[^"]*"|'[^']*')""")


def mots_bannis(texte: str) -> list:
    t = _ATTR_TECHNIQUES.sub(" ", texte)
    return [nom for nom, rx in MOTS_BANNIS if rx.search(t)]


def _regex_possible(src: str, i: int) -> bool:
    k = i - 1
    while k >= 0 and src[k] in " \t\r\n":
        k -= 1
    if k < 0 or src[k] in "(,=:[!&|?{};+-*%<>~^":
        return True
    return bool(re.search(r"(return|typeof|case|in|of|delete|void|throw|new)$", src[max(0, k - 8):k + 1]))


def chaines_js(src: str) -> list:
    """[(ligne, chaîne)] : littéraux de chaîne d'un source JavaScript (commentaires et regex retirés)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "/" and _regex_possible(src, i):
            j, classe = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    classe = True
                elif src[j] == "]":
                    classe = False
                elif src[j] == "/" and not classe:
                    break
                j += 1
            i = j + 1
            continue
        if c in "'\"`":
            j, buf = i + 1, []
            while j < n and src[j] != c:
                if src[j] == "\\":
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if c != "`" and src[j] == "\n":
                    break
                buf.append(src[j])
                j += 1
            out.append((src.count("\n", 0, i) + 1, "".join(buf)))
            i = j + 1
            continue
        i += 1
    return out


def textes_js(src: str) -> list:
    return [(ln, t) for ln, t in chaines_js(src) if not _CLE.fullmatch(t)]


_ATTR_LUS = ("title", "placeholder", "aria-label", "alt", "label", "content")


def textes_html(src: str) -> list:
    """[(ligne, texte)] lus par une personne dans une page HTML (gabarit Vue compris)."""
    blanc = lambda m: "\n" * m.group(0).count("\n")   # noqa: E731 — garde les numéros de ligne
    s = re.sub(r"<!--.*?-->", blanc, src, flags=re.S)
    s = re.sub(r"<style\b.*?</style>", blanc, s, flags=re.S | re.I)
    res, scripts = [], []

    def _script(m):
        scripts.append((s.count("\n", 0, m.start()) + 1, m.group(1)))
        return blanc(m)
    s = re.sub(r"<script\b[^>]*>(.*?)</script>", _script, s, flags=re.S | re.I)
    for ln0, corps in scripts:
        res += [(ln0 + ln - 1, t) for ln, t in textes_js(corps)]
    for m in re.finditer(r"<([a-zA-Z][\w-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", s):
        ln = s.count("\n", 0, m.start()) + 1
        for a in re.finditer(r"([:@\w.-]+)\s*=\s*(\"[^\"]*\"|'[^']*')", m.group(2)):
            nom, val = a.group(1), a.group(2)[1:-1]
            if nom in _ATTR_LUS:
                res.append((ln, val))
            elif nom.startswith(":") or nom.startswith("v-bind:"):
                res += [(ln, t) for _l, t in textes_js(val)]
    texte = re.sub(r"<(?:[a-zA-Z/!](?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", lambda m: blanc(m) + " ", s)
    for ln, ligne in enumerate(texte.split("\n"), 1):
        for morceau in re.split(r"(\{\{.*?\}\})", ligne):
            if morceau.startswith("{{"):
                res += [(ln, t) for _l, t in textes_js(morceau[2:-2])]
            elif morceau.strip():
                res.append((ln, morceau))
    return res


# ── Python : courriels et messages d'erreur ──────────────────────────────────────────────────────

def _docstrings(arbre) -> set:
    ids = set()
    for node in ast.walk(arbre):
        corps = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and corps \
                and isinstance(corps[0], ast.Expr) and isinstance(getattr(corps[0], "value", None), ast.Constant) \
                and isinstance(corps[0].value.value, str):
            ids.add(id(corps[0].value))
    return ids


def _nom_appel(call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _chaines(node, exclus) -> list:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in exclus:
            out.append((n.lineno, n.value))
    return out


def textes_courriels(src: str) -> list:
    """[(ligne, chaîne)] des fonctions qui envoient un courriel (send_email, _send_mails_async), hors docstrings
    et hors appels de journalisation."""
    arbre = ast.parse(src)
    exclus = _docstrings(arbre)
    for n in ast.walk(arbre):          # journaux : jamais lus par le destinataire
        if isinstance(n, ast.Call) and _nom_appel(n) in ("info", "warning", "error", "exception", "debug"):
            exclus |= {id(x) for x in ast.walk(n)}
    out = []
    for fn in ast.walk(arbre):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            appels = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                      and _nom_appel(c) in ("send_email", "_send_mails_async", "_send_email")]
            if appels:
                out += [(ln, t) for ln, t in _chaines(fn, exclus) if not _CLE.fullmatch(t)]
    return sorted(set(out))


def messages_erreur(src: str) -> list:
    """[(ligne, chaîne)] des messages d'erreur rendus à l'écran (arguments de HTTPException)."""
    arbre = ast.parse(src)
    out = []
    for c in ast.walk(arbre):
        if isinstance(c, ast.Call) and _nom_appel(c) == "HTTPException":
            for a in list(c.args[1:]) + [k.value for k in c.keywords if k.arg == "detail"]:
                out += [(ln, t) for ln, t in _chaines(a, set()) if not _CLE.fullmatch(t)]
    return out
