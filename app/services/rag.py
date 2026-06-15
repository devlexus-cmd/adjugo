"""
Adjugo — RAG à traçabilité (base de connaissances entreprise).

L'entreprise dépose ses documents (mémoires passés, RSE, méthodologies…). On les
découpe en chunks indexés. À la génération, on récupère les chunks pertinents par
BM25 (pur Python, aucune dépendance ni clé externe) et on les fournit à l'IA comme
SEULE source autorisée. Chaque réponse cite le chunk exact → anti-hallucination.

Choix d'implémentation : BM25 lexical plutôt qu'embeddings, pour rester souverain,
sans appel réseau, déterministe et explicable (cohérent avec la charte Adjugo).
"""
import heapq
import math
import os
import re
import time
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


# ── Recherche BM25 via INDEX INVERSÉ (par utilisateur, mis en cache) ──────────
# Scanner toute la base à chaque requête est en O(N). On construit, par user, un
# index inversé {terme → postings (doc, fréquence)} avec df et longueurs précalculées.
# Une requête ne touche alors QUE les chunks contenant au moins un terme cherché
# (O(postings concernés)), pas l'ensemble du corpus. L'index est invalidé via une
# empreinte (nombre de chunks + id max) à chaque (ré)indexation. 100 % souverain,
# sans embeddings ni réseau, portable SQLite↔Postgres. Au-delà du plafond RAM,
# l'évolution naturelle est un index Postgres GIN (tsvector) — même structure.
from sqlalchemy import func as _func

_IDX_CACHE = {}          # user_id -> (empreinte, index, expiration)  [ordre préservé]
_IDX_CACHE_MAX = 8000    # plafond de chunks indexés en RAM par user
_IDX_CACHE_USERS = int(os.getenv("RAG_CACHE_USERS", "200"))   # plafond d'users cachés
_IDX_CACHE_TTL = float(os.getenv("RAG_CACHE_TTL", "1800"))    # péremption (s) : 30 min
_K1, _B = 1.5, 0.75


def _fingerprint(db, user_id: int):
    row = db.query(_func.count(KnowledgeChunk.id), _func.max(KnowledgeChunk.id)) \
            .filter(KnowledgeChunk.user_id == user_id).first()
    return (row[0] or 0, row[1] or 0)


def _build_index(rows: list) -> dict:
    """Construit l'index inversé d'un corpus de chunks (objets KnowledgeChunk)."""
    meta, doc_len, postings, df, total_len = [], [], {}, Counter(), 0
    for i, r in enumerate(rows):
        toks = _tokens(r.text)
        meta.append((r.id, r.doc_id, r.doc_name, r.ordinal, r.user_id, r.text))
        dl = len(toks)
        doc_len.append(dl)
        total_len += dl
        for w, c in Counter(toks).items():
            postings.setdefault(w, []).append((i, c))
            df[w] += 1
    N = len(meta)
    return {"meta": meta, "doc_len": doc_len, "postings": postings, "df": df,
            "N": N, "total_len": total_len, "avgdl": (total_len / N) if N else 0.0}


def _index_for(db, user_id: int) -> dict:
    """Index inversé de l'utilisateur, avec cache invalidé à l'indexation."""
    fp = _fingerprint(db, user_id)
    now = time.monotonic()
    cached = _IDX_CACHE.get(user_id)
    if cached and cached[0] == fp and cached[2] > now:   # empreinte ET fraîcheur (TTL)
        return cached[1]
    rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.user_id == user_id).all()
    idx = _build_index(rows)
    if fp[0] <= _IDX_CACHE_MAX:
        # Éviction bornée : N tenants max (FIFO), plus péremption temporelle (TTL).
        _IDX_CACHE.pop(user_id, None)
        while len(_IDX_CACHE) >= _IDX_CACHE_USERS:
            _IDX_CACHE.pop(next(iter(_IDX_CACHE)), None)
        _IDX_CACHE[user_id] = (fp, idx, now + _IDX_CACHE_TTL)
    return idx


def _merge_indexes(indexes: list) -> dict:
    """Fusionne plusieurs index par-user (Merged Brain) en réutilisant leur cache,
    avec ré-indexation des postings par décalage. df/idf recalculés sur l'union."""
    meta, doc_len, postings, df, total_len = [], [], {}, Counter(), 0
    for idx in indexes:
        offset = len(meta)
        meta.extend(idx["meta"])
        doc_len.extend(idx["doc_len"])
        total_len += idx["total_len"]
        for w, plist in idx["postings"].items():
            tgt = postings.setdefault(w, [])
            for i, tf in plist:
                tgt.append((offset + i, tf))
        for w, c in idx["df"].items():
            df[w] += c
    N = len(meta)
    return {"meta": meta, "doc_len": doc_len, "postings": postings, "df": df,
            "N": N, "total_len": total_len, "avgdl": (total_len / N) if N else 0.0}


def _bm25_indexed(idx: dict, query: str, k: int) -> list:
    """BM25 par accumulation sur l'index inversé : ne visite que les postings des
    termes de la requête. Renvoie [(score, meta_tuple)] trié décroissant, top-k."""
    N = idx["N"]
    if not N:
        return []
    q = list(dict.fromkeys(_tokens(query)))     # termes uniques de la requête
    if not q:
        return []
    avgdl = idx["avgdl"] or 1.0
    df, postings, doc_len = idx["df"], idx["postings"], idx["doc_len"]
    scores = {}
    for w in q:
        plist = postings.get(w)
        if not plist:
            continue
        idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
        for i, tf in plist:
            dl = doc_len[i]
            scores[i] = scores.get(i, 0.0) + idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avgdl))
    if not scores:
        return []
    top = heapq.nlargest(k, scores.items(), key=lambda kv: kv[1])
    return [(s, idx["meta"][i]) for i, s in top]


def retrieve(db: Session, user_id: int, query: str, k: int = 6, min_score: float = 0.0) -> list:
    """Renvoie les k chunks les plus pertinents pour `query` dans la base de l'utilisateur."""
    out = []
    for s, t in _bm25_indexed(_index_for(db, user_id), query, k):
        if s < min_score:
            continue
        out.append({"chunk_id": t[0], "doc_id": t[1], "doc_name": t[2],
                    "ordinal": t[3], "text": t[5], "score": round(s, 3)})
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
    en réutilisant l'index inversé caché de chaque user. Chaque résultat porte son user_id."""
    if not user_ids:
        return []
    indexes = [_index_for(db, uid) for uid in dict.fromkeys(user_ids)]
    out = []
    for s, t in _bm25_indexed(_merge_indexes(indexes), query, k):
        out.append({"chunk_id": t[0], "doc_id": t[1], "doc_name": t[2], "user_id": t[4],
                    "text": t[5], "score": round(s, 3)})
    return out


def sources_block_attributed(chunks: list, names_by_user: dict) -> str:
    """Bloc de sources numérotées avec ATTRIBUTION par entreprise (Merged Brain)."""
    lines = []
    for i, c in enumerate(chunks, 1):
        company = names_by_user.get(c.get("user_id"), "Entreprise")
        lines.append(f"[S{i}] (entreprise: {company} · doc: « {c['doc_name']} »)\n{c['text']}")
    return "\n\n".join(lines)
