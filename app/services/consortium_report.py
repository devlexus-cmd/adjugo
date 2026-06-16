"""
Compte-rendu de consortium (PDF, partageable) — Réseau Adjugo.

Synthèse de l'état d'un groupement : partenaires, lots couverts, complétude de chaque
part, pièces reçues, % de réponse commune prête (calcul déterministe), et ce qu'il reste
à compléter. Même style reportlab que les CERFA / la DPGF.
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ACCENT = colors.HexColor("#1B4FFF")
_INK = colors.HexColor("#0A1730")
_LINE = colors.HexColor("#DCE2EC")
_HEAD = colors.HexColor("#F1F4F9")
_MUTED = colors.HexColor("#5A6573")
_OK = colors.HexColor("#1A7F4B")
_WARN = colors.HexColor("#9A6700")


def _p(text, style):
    return Paragraph(str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def generate_consortium_report_pdf(project_name: str, mandataire: str, data: dict,
                                   contributions: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm, title="Compte-rendu consortium")
    base = getSampleStyleSheet()["Normal"]
    st = ParagraphStyle("body", parent=base, fontSize=9.5, leading=13, textColor=_INK)
    muted = ParagraphStyle("muted", parent=st, textColor=_MUTED, fontSize=8.5)
    h1 = ParagraphStyle("h1", parent=st, fontSize=17, leading=20, textColor=_INK, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=st, fontSize=11.5, leading=14, textColor=_ACCENT, spaceBefore=10, spaceAfter=4)
    cell = ParagraphStyle("cell", parent=st, fontSize=8.7, leading=11)
    cellh = ParagraphStyle("cellh", parent=cell, textColor=_MUTED, fontName="Helvetica-Bold", fontSize=8)

    r = data.get("readiness", {}) or {}
    parts = data.get("partners", []) or []
    lots = data.get("lots", []) or []
    pct = r.get("pct", 0)

    el = []
    el.append(_p("Compte-rendu de consortium", h1))
    el.append(_p("Réseau Adjugo — co-traitance cloisonnée", muted))
    el.append(Spacer(1, 7))
    el.append(_p(f"<b>{project_name}</b>", st))
    el.append(_p(f"Mandataire : {mandataire or '—'} · édité le {date.today().strftime('%d/%m/%Y')}", muted))
    el.append(Spacer(1, 9))

    # Synthèse / readiness
    pct_col = _OK if pct >= 80 else (_WARN if pct >= 45 else colors.HexColor("#C0392B"))
    synth = Table([[
        _p(f"<font color='{pct_col.hexval()[2:]}'><b>{pct}%</b></font>", ParagraphStyle("big", parent=st, fontSize=22)),
        _p("réponse commune prête", st),
        _p(f"{r.get('submitted', 0)}/{r.get('invited', 0)} partenaire(s) ont contribué<br/>{r.get('lots', 0)} lot(s) couvert(s)", muted),
    ]], colWidths=[24 * mm, 45 * mm, 110 * mm])
    synth.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6, _LINE),
                               ("BACKGROUND", (0, 0), (-1, -1), _HEAD), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    el.append(synth)

    # Lots couverts
    if lots:
        el.append(_p("Lots couverts", h2))
        rows = [[_p("Lot", cellh), _p("Couvert par", cellh)]]
        for l in lots:
            rows.append([_p(l.get("lot", ""), cell), _p(", ".join(l.get("partners", [])), cell)])
        t = Table(rows, colWidths=[55 * mm, 124 * mm])
        t.setStyle(_grid())
        el.append(t)

    # Partenaires
    el.append(_p("Partenaires", h2))
    rows = [[_p("Entreprise", cellh), _p("Rôle", cellh), _p("Lot", cellh), _p("Statut", cellh), _p("Pièces", cellh), _p("Prêt", cellh)]]
    for p in parts:
        stt = {"submitted": "Soumise", "draft": "Brouillon"}.get(p.get("status"), "En attente")
        rows.append([_p(p.get("company", ""), cell),
                     _p("Sous-traitant" if p.get("role") == "sous_traitant" else "Co-traitant", cell),
                     _p(p.get("lot") or "—", cell), _p(stt, cell),
                     _p(str(p.get("pieces_count", 0)), cell), _p(f"{p.get('completeness', 0)}%", cell)])
    t = Table(rows, colWidths=[55 * mm, 26 * mm, 38 * mm, 24 * mm, 16 * mm, 20 * mm])
    t.setStyle(_grid())
    el.append(t)

    # Détail des contributions soumises
    subs = [c for c in (contributions or []) if c.get("status") == "submitted"]
    if subs:
        el.append(_p("Apports détaillés (parts soumises)", h2))
        for c in subs:
            el.append(_p(f"<b>{c.get('company_name', '')}</b> — lot : {c.get('lot') or '(non précisé)'}", st))
            if c.get("qualifications"):
                el.append(_p("Qualifications : " + ", ".join(str(q) for q in c["qualifications"]), muted))
            refs = [r.get("intitule", "") for r in (c.get("references") or []) if isinstance(r, dict) and r.get("intitule")]
            if refs:
                el.append(_p("Références : " + " · ".join(refs), muted))
            if c.get("chiffrage_note"):
                el.append(_p("Approche prix : " + c["chiffrage_note"], muted))
            if c.get("memoire_paragraph"):
                el.append(_p("Mémoire : " + c["memoire_paragraph"][:600], muted))
            el.append(Spacer(1, 5))

    # À compléter
    missing = r.get("missing", []) or []
    if missing:
        el.append(_p("À compléter", h2))
        for m in missing:
            el.append(_p("• " + m, ParagraphStyle("miss", parent=muted, textColor=_WARN)))

    el.append(Spacer(1, 12))
    el.append(_p("Document généré par Adjugo. Les % et statuts sont calculés de façon déterministe à partir des "
                 "contributions reçues — aucune donnée inventée.", ParagraphStyle("foot", parent=muted, fontSize=7.5)))

    doc.build(el)
    return buf.getvalue()


def _grid():
    return TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, _LINE),
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
