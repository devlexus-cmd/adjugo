"""
Adjugo — RAG à traçabilité (base de connaissances entreprise).

L'entreprise dépose ses documents (mémoires passés, RSE, méthodologies…). On les
découpe en chunks indexés. À la génération, on récupère les chunks pertinents par
BM25 (pur Python, aucune dépendance ni clé externe) et on les fournit à l'IA comme
SEULE source autorisée. Chaque réponse cite le chunk exact → anti-hallucination.

Choix d'implémentation : BM25 lexical plutôt qu'embeddings, pour rester souverain,
sans appel réseau, déterministe et explicable (cohérent avec la charte Adjugo).
"""
import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from app.models import KnowledgeDoc, KnowledgeChunk

# Mots vides FR (réduit le bruit lexical du BM25)
_STOP = set("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me
meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta
te tes toi ton tu un une vos votre vous c d j l a m n s t y ete etre avoir fait sont est
plus tres etc afin ainsi cette cet leurs comme entre selon dont chaque tout tous toute
toutes lors apres avant sous aussi donc alors quel quelle quels quelles
""".split())

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list:
    out = []
    for w in _TOKEN_RE.findall((text or "").lower()):
        if len(w) > 2 and w not in _STOP:
            out.append(w)
    return out


# ── Détection de structure juridique (Article 4.2, Titres, Annexes…) ─────────
_KW_HEAD = re.compile(r"^\s*(article|titre|chapitre|section|annexe|partie|pr[ée]ambule|sous[- ]?article)\b",
                      re.IGNORECASE)
_NUM_MULTI = re.compile(r"^\s*(\d+(?:\.\d+){1,4})[\.\)]?\s+\S")          # 4.2, 4.2.1 …
_NUM_SIMPLE = re.compile(r"^\s*(\d+)[\.\)]\s+[A-ZÀ-Ÿ]")                   # 4. PÉNALITÉS, 1) Objet
_CAPS = re.compile(r"^[A-ZÀ-Ÿ0-9][A-ZÀ-Ÿ0-9 ,\-/'’()]{3,79}$")


def _heading(line: str):
    """Renvoie (niveau, libellé) si la ligne est un titre de section, sinon None."""
    s = line.strip()
    if not s or len(s) > 120:
        return None
    m = _NUM_MULTI.match(s)
    if m:
        return (1 + m.group(1).count("."), s)
    if _KW_HEAD.match(s):
        return (1, s)
    if _NUM_SIMPLE.match(s):
        return (2, s)
    if _CAPS.match(s) and not s.endswith((".", ":", ";")) and any(c.isalpha() for c in s):
        return (1, s)
    return None


def _paragraph_chunks(text: str, target: int, overlap: int) -> list:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= target:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= target:
                buf = p
            else:
                sent = re.split(r"(?<=[.!?])\s+", p)
                cur = ""
                for s in sent:
                    if len(cur) + len(s) + 1 <= target:
                        cur = (cur + " " + s).strip()
                    else:
                        if cur:
                            chunks.append(cur)
                        cur = s[:target]
                buf = cur
    if buf:
        chunks.append(buf)
    if overlap > 0 and len(chunks) > 1:
        out = [chunks[0]]
        for i in range(1, len(chunks)):
            out.append((chunks[i - 1][-overlap:] + " … " + chunks[i]).strip())
        chunks = out
    return chunks


def chunk_text(text: str, target: int = 900, overlap: int = 150) -> list:
    """Découpe STRUCTURELLE : respecte la hiérarchie juridique (Article 4.2 et ses
    sous-clauses ne sont pas séparés de leur titre). Chaque chunk porte son fil d'Ariane
    de section → l'IA ne perd jamais le contexte contractuel. Fallback paragraphe si le
    document n'est pas structuré (fiche RSE, prose libre)."""
    text = re.sub(r"[ \t]+", " ", (text or "").strip())
    if not text:
        return []
    lines = text.split("\n")
    crumbs = {}          # niveau -> titre courant
    sections = []        # (fil_d_ariane, corps)
    body = []

    def _flush():
        if body and any(l.strip() for l in body):
            path = " › ".join(crumbs[k] for k in sorted(crumbs) if crumbs.get(k))
            sections.append((path, "\n".join(body).strip()))

    n_head = 0
    for line in lines:
        h = _heading(line)
        if h:
            n_head += 1
            _flush()
            body = []
            level, label = h
            crumbs[level] = label
            for k in [k for k in crumbs if k > level]:
                crumbs.pop(k, None)
        else:
            body.append(line)
    _flush()

    # Document non/peu structuré → chunker paragraphe simple
    if n_head < 2:
        return [c for c in _paragraph_chunks(text, target, overlap) if len(c) > 40]

    chunks = []
    for path, corps in sections:
        prefix = f"[{path}]\n" if path else ""
        for c in _paragraph_chunks(corps, max(200, target - len(prefix)), overlap):
            chunks.append((prefix + c).strip())
    return [c for c in chunks if len(c) > 40]


# ── Indexation ──────────────────────────────────────────────────────────────
def index_document(db: Session, user_id: int, name: str, text: str, kind: str = "autre") -> KnowledgeDoc:
    chunks = chunk_text(text)
    doc = KnowledgeDoc(user_id=user_id, name=name[:300], kind=kind,
                       text=(text or "")[:400000], char_count=len(text or ""),
                       n_chunks=len(chunks))
    db.add(doc)
    db.flush()  # pour récupérer doc.id
    for i, ck in enumerate(chunks):
        db.add(KnowledgeChunk(doc_id=doc.id, user_id=user_id, ordinal=i,
                              text=ck, doc_name=name[:300]))
    db.commit()
    db.refresh(doc)
    return doc


# ── Recherche BM25 (avec cache de tokenisation par utilisateur) ──────────────
# Tokeniser toute la base à CHAQUE requête est en O(N) coûteux. On met en cache les
# chunks DÉJÀ tokenisés par user, invalidés via une empreinte (nombre + max id) — ce
# qui évite de re-tokeniser à chaque appel. Plafonné pour borner la RAM ; au-delà,
# la vraie solution à l'échelle est un index Postgres full-text (GIN tsvector).
from sqlalchemy import func as _func

_TOK_CACHE = {}          # user_id -> (empreinte, [rows tokenisées])
_TOK_CACHE_MAX = 8000    # plafond de chunks mis en cache par user


def _fingerprint(db, user_id: int):
    row = db.query(_func.count(KnowledgeChunk.id), _func.max(KnowledgeChunk.id)) \
            .filter(KnowledgeChunk.user_id == user_id).first()
    return (row[0] or 0, row[1] or 0)


def _tokenized_rows(db, user_id: int) -> list:
    """[(id, doc_id, doc_name, ordinal, user_id, tokens, text)] avec cache invalidé à
    l'indexation (empreinte = nombre de chunks + id max)."""
    fp = _fingerprint(db, user_id)
    cached = _TOK_CACHE.get(user_id)
    if cached and cached[0] == fp:
        return cached[1]
    rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.user_id == user_id).all()
    out = [(r.id, r.doc_id, r.doc_name, r.ordinal, r.user_id, _tokens(r.text), r.text) for r in rows]
    if fp[0] <= _TOK_CACHE_MAX:
        _TOK_CACHE[user_id] = (fp, out)
    return out


def _bm25(trows: list, query: str, k: int) -> list:
    N = len(trows)
    if not N:
        return []
    q = _tokens(query)
    if not q:
        return []
    avgdl = sum(len(t[5]) for t in trows) / N
    df = Counter()
    for t in trows:
        for w in set(t[5]):
            df[w] += 1
    k1, b = 1.5, 0.75
    scored = []
    for t in trows:
        toks = t[5]
        if not toks:
            continue
        tf = Counter(toks)
        dl = len(toks)
        s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * (tf[w] * (k1 + 1)) / (tf[w] + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scored.append((s, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


def retrieve(db: Session, user_id: int, query: str, k: int = 6, min_score: float = 0.0) -> list:
    """Renvoie les k chunks les plus pertinents pour `query` dans la base de l'utilisateur."""
    out = []
    for s, t in _bm25(_tokenized_rows(db, user_id), query, k):
        out.append({"chunk_id": t[0], "doc_id": t[1], "doc_name": t[2],
                    "ordinal": t[3], "text": t[6], "score": round(s, 3)})
    return out


def sources_block(chunks: list) -> str:
    """Formate les chunks récupérés en bloc de sources numérotées [S1], [S2]…
    à injecter dans le prompt. L'IA ne doit citer QUE ces sources."""
    lines = []
    for i, c in enumerate(chunks, 1):
        lines.append(f"[S{i}] (source: « {c['doc_name']} »)\n{c['text']}")
    return "\n\n".join(lines)


# ── Récupération MULTI-ENTREPRISES (Merged Brain) ────────────────────────────
def retrieve_multi(db: Session, user_ids: list, query: str, k: int = 8) -> list:
    """Récupère les chunks les plus pertinents à travers PLUSIEURS bases (co-traitance),
    en réutilisant le cache de tokenisation par user. Chaque résultat porte son user_id."""
    if not user_ids:
        return []
    trows = []
    for uid in dict.fromkeys(user_ids):
        trows.extend(_tokenized_rows(db, uid))
    out = []
    for s, t in _bm25(trows, query, k):
        out.append({"chunk_id": t[0], "doc_id": t[1], "doc_name": t[2], "user_id": t[4],
                    "text": t[6], "score": round(s, 3)})
    return out


def sources_block_attributed(chunks: list, names_by_user: dict) -> str:
    """Bloc de sources numérotées avec ATTRIBUTION par entreprise (Merged Brain)."""
    lines = []
    for i, c in enumerate(chunks, 1):
        company = names_by_user.get(c.get("user_id"), "Entreprise")
        lines.append(f"[S{i}] (entreprise: {company} · doc: « {c['doc_name']} »)\n{c['text']}")
    return "\n\n".join(lines)
