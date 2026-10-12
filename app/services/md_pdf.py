"""
Rendu Markdown / texte → PDF (reportlab) pour le dossier commun. Les utilisateurs
ne savent pas ouvrir un .md : le mémoire et les fiches partent en PDF lisibles,
au même style que les CERFA / la DPGF.
"""
import io
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_INK = colors.HexColor("#0A1730")
_ACCENT = colors.HexColor("#1B4FFF")
_MUTED = colors.HexColor("#5A6573")


# Échappements Markdown « \* \_ \` \\ \# \[ \] » (option `md_escapes`) : une valeur dynamique
# (nom d'entreprise, lot…) contenant « * » ou « _ » reste un TEXTE, jamais une mise en forme.
# Désactivé par défaut : comportement inchangé pour les autres documents (mémoire, DCE).
_ESC_RE = re.compile(r"\\([\\*_`#\[\]])")
_ESC_BASE = 0xE000   # zone Unicode à usage privé : jamais présente dans un texte réel
_ESC_BACK = re.compile("[-]")


def _inline(s: str, escapes: bool = False) -> str:
    """Échappe le HTML puis convertit le gras/italique/code Markdown en balises reportlab."""
    if escapes:
        s = _ESC_RE.sub(lambda m: chr(_ESC_BASE + ord(m.group(1))), s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    if escapes:
        s = _ESC_BACK.sub(lambda m: chr(ord(m.group(0)) - _ESC_BASE), s)
    return s


def _doc(buf, title):
    return SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=16 * mm, rightMargin=16 * mm, title=title)


def _styles():
    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle("body", parent=base, fontSize=10, leading=14.5, textColor=_INK, spaceAfter=4)
    return {
        "body": body,
        "bullet": ParagraphStyle("bul", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=2),
        1: ParagraphStyle("h1", parent=body, fontSize=18, leading=22, textColor=_INK, spaceBefore=2, spaceAfter=6),
        2: ParagraphStyle("h2", parent=body, fontSize=13.5, leading=17, textColor=_ACCENT, spaceBefore=10, spaceAfter=3),
        3: ParagraphStyle("h3", parent=body, fontSize=11.5, leading=15, textColor=_INK, spaceBefore=7, spaceAfter=2),
    }


# Tableaux Markdown (« | a | b | » + ligne « |---|---| ») : rendus en vrai tableau quand
# `tables=True` (dossier de présentation). Désactivé par défaut : la convention et le DCE gardent
# leur rendu à l'octet près.
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LINE = colors.HexColor("#DCE2EC")
_HEAD = colors.HexColor("#F1F4F9")
# Passage « [À compléter …] » : surligné, pour qu'aucun trou ne passe inaperçu à la relecture.
_TODO_RE = re.compile(r"\[\s*[ÀAà]\s+compl[ée]ter[^\]]*\]", re.IGNORECASE)


def split_table_row(line: str) -> list:
    """« | a | b | » → ["a", "b"] (les « \\| » restent du texte)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]


def is_table_start(lines: list, i: int) -> bool:
    return (i + 1 < len(lines) and bool(_TABLE_ROW.match(lines[i]))
            and bool(_TABLE_SEP.match(lines[i + 1])) and "|" in lines[i + 1])


def _mark_todo(s: str) -> str:
    return _TODO_RE.sub(lambda m: f"<font backColor='#FFF1A8'><b>{m.group(0)}</b></font>", s)


def _table_flowable(header: list, rows: list, st, e: bool, width: float):
    from reportlab.platypus import Table, TableStyle
    n = max([len(header)] + [len(r) for r in rows] + [1])
    cell = ParagraphStyle("cell", parent=st["body"], fontSize=8.8, leading=11.5, spaceAfter=0)
    cellh = ParagraphStyle("cellh", parent=cell, fontName="Helvetica-Bold")

    def _row(vals, style):
        vals = list(vals) + [""] * (n - len(vals))
        return [Paragraph(_mark_todo(_inline(v, e)), style) for v in vals[:n]]
    data = [_row(header, cellh)] + [_row(r, cell) for r in rows]
    t = Table(data, colWidths=[width / n] * n, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, _LINE), ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def markdown_to_pdf(md: str, title: str = "Document", md_escapes: bool = False,
                    tables: bool = False) -> bytes:
    """`md_escapes=True` : honore les échappements « \\* \\_ \\` \\\\ \\# \\[ \\] » (texte littéral).
    `tables=True` : tableaux Markdown rendus en tableau, et passages « [À compléter …] » surlignés."""
    e = bool(md_escapes)
    buf = io.BytesIO()
    doc = _doc(buf, title)
    st = _styles()
    flow, bullets = [], []
    mark = _mark_todo if tables else (lambda s: s)

    def flush():
        for b in bullets:
            flow.append(Paragraph(b, st["bullet"], bulletText="•"))
        bullets.clear()

    lines = (md or "").split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        line = raw.rstrip()
        if tables and is_table_start(lines, i - 1):
            flush()
            header = split_table_row(line)
            i += 1                                   # ligne « |---|---| »
            rows = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                rows.append(split_table_row(lines[i]))
                i += 1
            flow.append(_table_flowable(header, rows, st, e, doc.width))
            flow.append(Spacer(1, 5))
            continue
        if not line.strip():
            flush(); flow.append(Spacer(1, 5)); continue
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            flush(); lvl = min(len(h.group(1)), 3)
            flow.append(Paragraph(mark(_inline(h.group(2), e)), st[lvl])); continue
        b = re.match(r"^[-*+]\s+(.*)", line)
        if b:
            bullets.append(mark(_inline(b.group(1), e))); continue
        n = re.match(r"^(\d+)\.\s+(.*)", line)
        if n:
            flush(); flow.append(Paragraph(f"<b>{n.group(1)}.</b> " + mark(_inline(n.group(2), e)), st["body"])); continue
        flush(); flow.append(Paragraph(mark(_inline(line, e)), st["body"]))
    flush()
    if not flow:
        flow.append(Paragraph("(document vide)", st["body"]))
    doc.build(flow)
    return buf.getvalue()


def text_to_pdf(text: str, title: str = "Document") -> bytes:
    """Texte brut → PDF. Les soulignements ASCII (==== / ----) deviennent des titres."""
    buf = io.BytesIO()
    doc = _doc(buf, title)
    st = _styles()
    flow = []
    lines = (text or "").split("\n")
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            flow.append(Spacer(1, 4)); continue
        if re.match(r"^[=\-_]{3,}$", line.strip()):   # ligne de soulignement → on saute
            continue
        # une ligne suivie d'un soulignement ==== est un titre
        is_title = (i + 1 < len(lines) and re.match(r"^[=]{3,}$", lines[i + 1].strip()))
        flow.append(Paragraph(_inline(line), st[2] if is_title else st["body"]))
    if not flow:
        flow.append(Paragraph("(vide)", st["body"]))
    doc.build(flow)
    return buf.getvalue()
