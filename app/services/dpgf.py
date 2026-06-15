"""
Génération de la DPGF (Décomposition du Prix Global et Forfaitaire) et du BPU
(Bordereau des Prix Unitaires) à partir du chiffrage estimatif — au format PDF
(reportlab, cohérent avec les CERFA). Les montants viennent du calcul déterministe.
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


def _eur(v) -> str:
    return f"{int(round(v or 0)):,}".replace(",", " ") + " €"


def generate_dpgf_pdf(estimate: dict, company_name: str, project_name: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm, title="DPGF")
    base = getSampleStyleSheet()["Normal"]
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=15, textColor=_INK)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12, textColor=_ACCENT, spaceBefore=2)
    sub = ParagraphStyle("sub", parent=base, fontSize=9, textColor=_MUTED, leading=13)
    cell = ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11, textColor=_INK)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
    story = []

    story.append(Paragraph(company_name or "Entreprise", h1))
    story.append(Paragraph("Décomposition du Prix Global et Forfaitaire (DPGF)", h2))
    story.append(Paragraph(f"Marché : {project_name or ''}", sub))
    story.append(Paragraph(f"Établi le {date.today().strftime('%d/%m/%Y')}", sub))
    story.append(Spacer(1, 7 * mm))

    rows = [[Paragraph("N°", cellb), Paragraph("Désignation de la prestation", cellb),
             Paragraph("Phase", cellb), Paragraph("Unité", cellb), Paragraph("Qté", cellb),
             Paragraph("P.U. HT", cellb), Paragraph("Montant HT", cellb)]]
    for i, l in enumerate(estimate.get("lignes", []), 1):
        rows.append([Paragraph(str(i), cell), Paragraph(l.get("tache", ""), cell),
                     Paragraph(l.get("phase", ""), cell), Paragraph("jour", cell),
                     Paragraph(str(l.get("jours", "")), cell),
                     Paragraph(_eur(l.get("tarif")), cell), Paragraph(_eur(l.get("montant")), cell)])
    rows.append(["", "", "", "", "", Paragraph("Total HT", cellb),
                 Paragraph(_eur(estimate.get("total_ht")), cellb)])

    table = Table(rows, colWidths=[9 * mm, 64 * mm, 27 * mm, 13 * mm, 11 * mm, 22 * mm, 27 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, _ACCENT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, _LINE),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, _INK),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    note = "Prix nets — TVA non applicable, art. 293 B du CGI."
    maj = estimate.get("majoration_pct") or 0
    if maj:
        note += f" Inclut une majoration de {maj} % (chantier à {estimate.get('distance_km')} km)."
    story.append(Paragraph(note, sub))

    rates = estimate.get("rates_used") or []
    if rates:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Bordereau des Prix Unitaires (BPU) — tarifs journaliers", h2))
        brows = [[Paragraph("Profil de prestation", cellb), Paragraph("Unité", cellb), Paragraph("P.U. HT", cellb)]]
        for r in rates:
            brows.append([Paragraph(r.get("label", ""), cell), Paragraph("jour", cell),
                          Paragraph(_eur(r.get("rate")), cell)])
        bt = Table(brows, colWidths=[113 * mm, 20 * mm, 27 * mm], repeatRows=1)
        bt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, _ACCENT),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(bt)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Document généré par Adjugo à titre d'aide à la décision. "
                           "Le candidat reste responsable de la vérification et de l'engagement des prix.", sub))
    doc.build(story)
    return buf.getvalue()
