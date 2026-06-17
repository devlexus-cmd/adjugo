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


def _inline(s: str) -> str:
    """Échappe le HTML puis convertit le gras/italique/code Markdown en balises reportlab."""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
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


def markdown_to_pdf(md: str, title: str = "Document") -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf, title)
    st = _styles()
    flow, bullets = [], []

    def flush():
        for b in bullets:
            flow.append(Paragraph(b, st["bullet"], bulletText="•"))
        bullets.clear()

    for raw in (md or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush(); flow.append(Spacer(1, 5)); continue
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            flush(); lvl = min(len(h.group(1)), 3)
            flow.append(Paragraph(_inline(h.group(2)), st[lvl])); continue
        b = re.match(r"^[-*+]\s+(.*)", line)
        if b:
            bullets.append(_inline(b.group(1))); continue
        n = re.match(r"^(\d+)\.\s+(.*)", line)
        if n:
            flush(); flow.append(Paragraph(f"<b>{n.group(1)}.</b> " + _inline(n.group(2)), st["body"])); continue
        flush(); flow.append(Paragraph(_inline(line), st["body"]))
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
