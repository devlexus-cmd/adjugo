"""
Adjugo - CERFA Overlay v4 FINAL
Coordonnees precises relevees sur les grilles officielles.
Support co-traitants pour DC1 section E et DC2 multiples.
"""
import io, os, datetime
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates"
)
BLACK = HexColor("#111111")
W, H = A4  # 595.28 x 841.89


def _text(c, x, y, text, size=9, bold=False):
    if not text:
        return
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(BLACK)
    c.drawString(x, H - y, str(text))


def _multiline(c, x, y, text, size=9, bold=False, line_height=13):
    if not text:
        return
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(BLACK)
    for i, line in enumerate(str(text).split("\n")):
        c.drawString(x, H - y - (i * line_height), line)


def _checkbox(c, cx, cy, size=9.5):
    """Dessine un « X » CENTRÉ dans la case dont le centre (origine en haut) est (cx, cy).
    cx/cy = centre réel de la case relevé sur le template (pas le coin)."""
    c.setFont("Helvetica-Bold", size)
    c.setFillColor(BLACK)
    cap = 0.70 * size  # hauteur de capitale approx. d'un X
    c.drawCentredString(cx, H - cy - 0.5 * cap, "X")


def create_overlay(fields_by_page):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for page_num in sorted(fields_by_page.keys()):
        for item in fields_by_page[page_num]:
            if item.get("type") == "checkbox":
                _checkbox(c, item["x"], item["y"], item.get("size", 9.5))
            elif item.get("type") == "multiline":
                _multiline(c, item["x"], item["y"], item.get("text", ""),
                           size=item.get("size", 9), bold=item.get("bold", False),
                           line_height=item.get("line_height", 13))
            else:
                _text(c, item["x"], item["y"], item.get("text", ""),
                      size=item.get("size", 9), bold=item.get("bold", False))
        c.showPage()
    c.save()
    return buf


def merge_overlay(template_path, overlay_buf):
    template = PdfReader(template_path)
    overlay = PdfReader(overlay_buf)
    writer = PdfWriter()
    for i, page in enumerate(template.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def fmt_eur(n):
    return "{:,.2f} EUR".format(n).replace(",", " ")


def fmt_int(n):
    return "{:,.0f}".format(n).replace(",", " ")


def fmt_pct(n):
    """Taux en % sans décimale superflue : 0 → '0', 20 → '20', 5.5 → '5,5'."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return "0"
    return (("{:.1f}".format(f)).rstrip("0").rstrip(".")).replace(".", ",")


# ================================================================
# PARE-FEU DE VALIDATION — champs critiques sans lesquels un pli est
# mécaniquement rejeté (signature vide, identité incomplète). Utilisé par
# le routeur CERFA (422) et par build_dossier (avertissement bloquant).
# ================================================================
REQUIRED_COMPANY_FIELDS = {
    "name": "Dénomination de l'entreprise",
    "siret": "SIRET",
    "representant_legal": "Nom et qualité du représentant légal (signataire)",
    "address": "Adresse du siège",
    "city": "Ville",
}


def missing_company_fields(c) -> list:
    """Retourne la liste des libellés des champs critiques manquants."""
    c = c or {}
    return [label for k, label in REQUIRED_COMPANY_FIELDS.items()
            if not str(c.get(k) or "").strip()]


# ================================================================
# DC1 - LETTRE DE CANDIDATURE (6 pages)
# ================================================================
def generate_dc1(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "dc1.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC1", c, p)

    d = datetime.date.today().strftime("%d/%m/%Y")
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    cotraitants = p.get("cotraitants", [])
    is_groupement = len(cotraitants) > 0

    fields = {
        # Page 1: A - acheteur (y=460), B - objet (y=612)
        0: [
            {"x": 42, "y": 470, "text": p.get("client", ""), "size": 10, "bold": True},
            {"x": 42, "y": 622, "text": p.get("name", ""), "size": 10, "bold": True},
        ],
        # Page 2: C - cocher "pour le marche public" (centre case relevé)
        1: [
            {"type": "checkbox", "x": 76.8, "y": 92.3},
        ],
        # Page 3: D - candidat seul OU groupement
        2: [],
        # Page 4: (suite E)
        3: [],
        # Page 5: F1 - declaration honneur (x=240, y=201), F3 - DC2 (x=71, y=540)
        4: [
            {"type": "checkbox", "x": 245.0, "y": 205.7},
            {"type": "checkbox", "x": 75.7, "y": 545.0},
        ],
        # Page 6: mandataire (si groupement)
        5: [],
    }

    # Page 3 - candidat
    if not is_groupement:
        # Candidat seul
        fields[2] = [
            {"type": "checkbox", "x": 76.7, "y": 81.1},
            {"x": 60, "y": 160, "text": c.get("name", ""), "size": 10, "bold": True},
            {"x": 60, "y": 205, "text": addr, "size": 9},
            {"x": 60, "y": 253, "text": c.get("email", ""), "size": 9},
            {"x": 60, "y": 300, "text": c.get("phone", ""), "size": 9},
            {"x": 60, "y": 357, "text": c.get("siret", ""), "size": 10, "bold": True},
        ]
    else:
        # Groupement - cocher groupement, pas seul
        # "Le candidat est un groupement" checkbox is lower on page 3
        fields[2] = [
            # On remplit quand meme les infos du mandataire (nous)
            {"x": 60, "y": 160, "text": c.get("name", "") + " (mandataire)", "size": 10, "bold": True},
            {"x": 60, "y": 205, "text": addr, "size": 9},
            {"x": 60, "y": 253, "text": c.get("email", ""), "size": 9},
            {"x": 60, "y": 300, "text": c.get("phone", ""), "size": 9},
            {"x": 60, "y": 357, "text": c.get("siret", ""), "size": 10, "bold": True},
        ]

        # Page 3 Section E - tableau des membres du groupement
        # Le tableau commence environ y=500 sur page 3, puis continue page 4
        table_y = 520
        row_height = 45

        # Ajouter le mandataire en premier dans le tableau
        mandataire_text = c.get("name", "") + "\n" + addr + "\n" + str(c.get("email", "")) + " - " + str(c.get("phone", "")) + "\nSIRET: " + str(c.get("siret", ""))
        fields[2].append({"type": "multiline", "x": 80, "y": table_y, "text": mandataire_text, "size": 7, "line_height": 10})

        # Ajouter les co-traitants
        for i, ct in enumerate(cotraitants):
            ct_y = table_y + (i + 1) * row_height
            ct_addr = (str(ct.get("address", "")) + " " + str(ct.get("postal_code", "")) + " " + str(ct.get("city", ""))).strip()
            ct_text = str(ct.get("name", "")) + "\n" + ct_addr + "\n" + str(ct.get("email", "")) + " - " + str(ct.get("phone", "")) + "\nSIRET: " + str(ct.get("siret", ""))

            if ct_y < 750:  # Reste sur page 3
                fields[2].append({"type": "multiline", "x": 80, "y": ct_y, "text": ct_text, "size": 7, "line_height": 10})
            else:  # Deborde sur page 4
                overflow_y = 100 + (ct_y - 750)
                fields[3].append({"type": "multiline", "x": 80, "y": overflow_y, "text": ct_text, "size": 7, "line_height": 10})

        # Page 6 - mandataire si groupement
        fields[5] = [
            {"x": 60, "y": 108, "text": c.get("name", ""), "size": 10, "bold": True},
            {"x": 60, "y": 155, "text": addr, "size": 9},
            {"x": 60, "y": 195, "text": c.get("email", ""), "size": 9},
            {"x": 60, "y": 230, "text": c.get("phone", ""), "size": 9},
            {"x": 60, "y": 275, "text": c.get("siret", ""), "size": 10, "bold": True},
        ]

    return merge_overlay(tpl, create_overlay(fields))


# ================================================================
# DC2 - DECLARATION DU CANDIDAT (3 pages)
# Genere un DC2 par membre (mandataire + co-traitants)
# ================================================================
def generate_dc2(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "dc2.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC2", c, p)

    cotraitants = p.get("cotraitants", [])
    members = [c] + cotraitants  # Mandataire + co-traitants

    if len(members) == 1:
        return _generate_single_dc2(tpl, c, p)
    else:
        # Generer un DC2 pour chaque membre et les fusionner
        writer = PdfWriter()
        for member in members:
            pdf_bytes = _generate_single_dc2(tpl, member, p)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()


def _generate_single_dc2(tpl, c, p):
    d = datetime.date.today().strftime("%d/%m/%Y")
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    name = c.get("name", "")
    siret = c.get("siret", "")

    # Bloc C1 : nom, adresse, email, tel, siret sur plusieurs lignes
    c1_text = name + "\n" + addr + "\n" + str(c.get("email", "")) + "\n" + str(c.get("phone", "")) + "\nSIRET : " + siret

    fields = {
        # Page 1
        0: [
            # A - pouvoir adjudicateur
            {"x": 42, "y": 315, "text": p.get("client", ""), "size": 10, "bold": True},
            # B - objet du marche
            {"x": 42, "y": 415, "text": p.get("name", ""), "size": 10, "bold": True},
            # C1 - nom, adresse, email, tel, siret
            {"type": "multiline", "x": 42, "y": 553, "text": c1_text, "size": 9, "bold": False, "line_height": 14},
            # Forme juridique
            {"x": 42, "y": 635, "text": c.get("forme_juridique", ""), "size": 9},
            # Representant
            {"x": 107, "y": 715, "text": c.get("representant_legal", ""), "size": 9, "bold": True},
        ],
        # Page 2: D1 - CA (3 colonnes)
        # Colonnes: x=171 (N-3), x=299 (N-2), x=427 (N-1) — ligne CA global y=670
        1: [
            {"x": 55, "y": 670, "text": fmt_int(c.get("ca_n1", 0) or 0), "size": 8},
            {"x": 185, "y": 670, "text": fmt_int(c.get("ca_n2", 0) or 0), "size": 8},
            {"x": 315, "y": 670, "text": fmt_int(c.get("ca_n3", 0) or 0), "size": 8},
        ],
        # Page 3: D2 - NON redressement (centre case relevé)
        2: [
            {"type": "checkbox", "x": 180.7, "y": 107.4},
        ],
    }

    return merge_overlay(tpl, create_overlay(fields))


# ================================================================
# DC4 - DECLARATION DE SOUS-TRAITANCE (9 pages)
# ================================================================
def generate_dc4(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "dc4.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC4", c, p)

    d = datetime.date.today().strftime("%d/%m/%Y")
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()

    fields = {
        # Page 1: A - acheteur + B - objet
        0: [
            {"x": 42, "y": 420, "text": p.get("client", ""), "size": 10, "bold": True},
            {"x": 42, "y": 545, "text": p.get("name", ""), "size": 10, "bold": True},
        ],
        # Page 2: C - cocher "document annexe à l'offre" (centre case relevé), D - titulaire
        1: [
            {"type": "checkbox", "x": 77.8, "y": 140.6},
            # D - valeurs placées sous chaque libellé (positions relevées à la grille)
            {"x": 44, "y": 370, "text": c.get("name", ""), "size": 10, "bold": True},
            {"x": 44, "y": 425, "text": addr, "size": 9},
            {"x": 44, "y": 457, "text": c.get("email", ""), "size": 9},
            {"x": 44, "y": 487, "text": c.get("phone", ""), "size": 9},
            {"x": 44, "y": 525, "text": c.get("siret", ""), "size": 9, "bold": True},
            {"x": 44, "y": 575, "text": c.get("forme_juridique", ""), "size": 9},
        ],
        2: [], 3: [], 4: [], 5: [], 6: [],
        # Page 8: M - Signatures
        7: [
            {"x": 55, "y": 622, "text": "A " + str(c.get("city", "")), "size": 9},
            {"x": 170, "y": 622, "text": "le " + d, "size": 9},
            {"x": 305, "y": 622, "text": "A " + str(c.get("city", "")), "size": 9},
            {"x": 420, "y": 622, "text": "le " + d, "size": 9},
        ],
        8: [],
    }

    return merge_overlay(tpl, create_overlay(fields))


# ================================================================
# ATTRI1 - ACTE D'ENGAGEMENT (7 pages)
# ================================================================
def generate_attri1(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "attri1.pdf")
    if not os.path.exists(tpl):
        return _fallback("ATTRI1", c, p)

    d = datetime.date.today().strftime("%d/%m/%Y")
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    budget = p.get("budget", 0) or 0
    # Taux de TVA piloté par le projet. Défaut 0 % : la majorité des marchés
    # publics FR sont hors-champ TVA (art. 293 B du CGI). Un 20 % codé en dur
    # produisait un montant TTC d'engagement FAUX par défaut.
    rate = p.get("tva_rate", 0) or 0
    tva = budget * rate / 100.0
    ttc = budget + tva
    tva_label = (fmt_pct(rate) + " %") if rate else "0 % — TVA non applicable (art. 293 B CGI)"

    # Bloc identification pour page 2
    ident_text = str(c.get("name", "")) + "\n" + addr + "\n" + str(c.get("email", "")) + " - " + str(c.get("phone", "")) + "\nSIRET : " + str(c.get("siret", ""))

    fields = {
        # Page 1: A - Objet + case "ensemble du marche"
        0: [
            {"x": 42, "y": 415, "text": p.get("name", ""), "size": 10, "bold": True},
            {"type": "checkbox", "x": 91.2, "y": 518.6, "size": 9.7},
        ],
        # Page 2: B1 - Engagement + prix
        1: [
            # Case "engage la société" (candidat = personne morale) + dénomination sur sa ligne
            {"type": "checkbox", "x": 133.6, "y": 324.5, "size": 9.7},
            {"x": 158, "y": 327, "text": (str(c.get("name", "")) + " — SIRET " + str(c.get("siret", ""))).strip(" —"), "size": 8, "bold": True},
            # TVA (taux réel du projet, 0 % par défaut — art. 293 B CGI)
            {"x": 226, "y": 521, "text": tva_label, "size": 8 if rate == 0 else 9},
            # Montant HT chiffres
            {"x": 230, "y": 563, "text": fmt_eur(budget), "size": 9, "bold": True},
            # Montant TTC chiffres
            {"x": 210, "y": 622, "text": fmt_eur(ttc), "size": 9, "bold": True},
        ],
        # Page 3: B4 - Avance NON (centre case relevé)
        2: [
            {"type": "checkbox", "x": 360.5, "y": 560.9, "size": 9.7},
        ],
        # Page 4: C1 - Signature titulaire
        # Tableau C1: col1=x35 (nom), col2=x267 (lieu/date), col3=x402 (signature)
        # Ligne y=207-258
        3: [
            {"x": 40, "y": 225, "text": c.get("representant_legal", ""), "size": 8, "bold": True},
            {"x": 40, "y": 238, "text": "Repr. legal - " + str(c.get("name", "")), "size": 7},
            {"x": 270, "y": 225, "text": str(c.get("city", "")) + ", le " + d, "size": 8},
        ],
        # Page 5: D - Acheteur
        4: [
            {"x": 42, "y": 438, "text": p.get("client", ""), "size": 10, "bold": True},
        ],
        # Page 6
        5: [
            {"x": 130, "y": 142, "text": "A " + str(c.get("city", "")), "size": 9},
            {"x": 300, "y": 142, "text": "le " + d, "size": 9},
        ],
        6: [],
    }

    return merge_overlay(tpl, create_overlay(fields))


# ================================================================
# FALLBACK
# ================================================================
def _fallback(title, c, p):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="T", fontSize=14, fontName="Helvetica-Bold", alignment=TA_CENTER))
    e = [
        Paragraph(title + " - Template introuvable", s["T"]),
        Spacer(1, 10 * mm),
        Paragraph("Entreprise : " + str(c.get("name", "")), s["Normal"]),
        Paragraph("SIRET : " + str(c.get("siret", "")), s["Normal"]),
        Paragraph("Marche : " + str(p.get("name", "")), s["Normal"]),
    ]
    doc.build(e)
    return buf.getvalue()


# ================================================================
# DUME - Document Unique de Marché Européen (pré-rempli)
# Aide au remplissage du e-DUME officiel à partir du profil entreprise.
# Ce n'est pas le formulaire officiel : c'est un brouillon structuré à reporter.
# ================================================================
def generate_dume(c, p, lang_name=None):
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as _colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm)
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="DumeTitle", fontSize=15, fontName="Helvetica-Bold", spaceAfter=4))
    s.add(ParagraphStyle(name="DumeSub", fontSize=8.5, textColor=_colors.HexColor("#555555"), spaceAfter=10))
    s.add(ParagraphStyle(name="H", fontSize=11, fontName="Helvetica-Bold",
                         textColor=_colors.HexColor("#2C5BD8"), spaceBefore=10, spaceAfter=5))
    body = s["Normal"]; body.fontSize = 9; body.leading = 13

    def kv(rows):
        t = Table([[Paragraph("<b>" + k + "</b>", body), Paragraph(str(v or "—"), body)] for k, v in rows],
                  colWidths=[55 * mm, 110 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, _colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    quals = c.get("qualifications") or []
    refs = c.get("references") or []
    addr = " ".join(str(c.get(k, "") or "") for k in ("address", "postal_code", "city")).strip()
    ca_n1 = c.get("ca_n1") or 0
    eff = c.get("effectif") or 0
    pme = "Oui (PME au sens UE)" if (eff and eff < 250) else ("Non / à préciser" if eff else "À préciser")

    from app.services.dume_labels import dume_translator
    tr = dume_translator(lang_name)

    e = [
        Paragraph(tr("DUME — Document Unique de Marché Européen"), s["DumeTitle"]),
        Paragraph(tr("Brouillon pré-rempli par Adjugo à partir de votre profil. À reporter sur le "
                     "e-DUME officiel. Vérifiez chaque champ avant dépôt."), s["DumeSub"]),

        Paragraph(tr("Partie I — Procédure et acheteur"), s["H"]),
        kv([(tr("Objet du marché"), p.get("name")), (tr("Acheteur public"), p.get("client")),
            (tr("Référence"), p.get("reference"))]),

        Paragraph(tr("Partie II — Identité de l'opérateur économique"), s["H"]),
        kv([(tr("Dénomination"), c.get("name")), (tr("SIRET"), c.get("siret")),
            (tr("Code APE/NAF"), c.get("code_ape")), (tr("Forme juridique"), c.get("forme_juridique")),
            (tr("Adresse"), addr), (tr("Représentant légal"), c.get("representant_legal")),
            (tr("TVA intracom."), c.get("tva_intracom")),
            (tr("Contact"), (str(c.get("email", "") or "") + "  " + str(c.get("phone", "") or "")).strip()),
            (tr("Microentreprise / PME"), pme), (tr("Effectif"), eff or "—")]),

        Paragraph(tr("Partie III — Motifs d'exclusion"), s["H"]),
        Paragraph(tr("L'opérateur déclare sur l'honneur n'entrer dans aucun des cas d'interdiction de "
                     "soumissionner prévus par le droit applicable (condamnations pénales, manquements "
                     "fiscaux ou sociaux, liquidation judiciaire, etc.)."), body),
    ]

    e.append(Paragraph(tr("Partie IV — Critères de sélection"), s["H"]))
    e.append(Paragraph("<b>" + tr("A. Capacité économique et financière") + "</b>", body))
    e.append(kv([(tr("Chiffre d'affaires N-1"), fmt_eur(ca_n1) if ca_n1 else "—"),
                 (tr("Chiffre d'affaires N-2"), fmt_eur(c.get("ca_n2") or 0) if c.get("ca_n2") else "—"),
                 (tr("Chiffre d'affaires N-3"), fmt_eur(c.get("ca_n3") or 0) if c.get("ca_n3") else "—")]))
    e.append(Spacer(1, 4))
    e.append(Paragraph("<b>" + tr("B. Capacité technique et professionnelle — qualifications") + "</b>", body))
    if quals:
        for q in quals[:12]:
            nom = q.get("name") if isinstance(q, dict) else str(q)
            det = q.get("detail", "") if isinstance(q, dict) else ""
            exp = q.get("expiration", "") if isinstance(q, dict) else ""
            line = "• " + str(nom) + (" — " + str(det) if det else "") + ((" (" + str(exp) + ")") if exp else "")
            e.append(Paragraph(line, body))
    else:
        e.append(Paragraph("• " + tr("Aucune qualification renseignée dans le profil."), body))
    e.append(Spacer(1, 4))
    e.append(Paragraph("<b>" + tr("C. Références de marchés similaires") + "</b>", body))
    if refs:
        for r in refs[:12]:
            if isinstance(r, dict):
                line = "• " + str(r.get("name", "")) + " — " + str(r.get("client", "")) + \
                       (" (" + fmt_eur(r.get("value")) + ")" if r.get("value") else "") + \
                       (" — " + str(r.get("year")) if r.get("year") else "")
            else:
                line = "• " + str(r)
            e.append(Paragraph(line, body))
    else:
        e.append(Paragraph("• " + tr("Aucune référence renseignée dans le profil."), body))

    e += [
        Paragraph(tr("Partie VI — Déclarations finales"), s["H"]),
        Paragraph(tr("Le signataire atteste l'exactitude des informations ci-dessus et accepte de fournir, "
                     "sur demande de l'acheteur, les certificats et documents justificatifs correspondants."), body),
        Spacer(1, 8 * mm),
        kv([(tr("Fait à"), c.get("city")), (tr("Le"), datetime.date.today().strftime("%d/%m/%Y")),
            (tr("Signature (nom, qualité)"), c.get("representant_legal"))]),
    ]
    doc.build(e)
    return buf.getvalue()


# ================================================================
# FORMULAIRES NATIONAUX (piloté par spec) — brouillons pré-remplis fidèles
# au modèle officiel de chaque pays (PL, PT, IT, NL, RO). On présente toujours
# « brouillon à reporter sur le modèle officiel », jamais le formulaire officiel.
# ================================================================
def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _resolve_source(key, c, p):
    import datetime as _dt
    addr = " ".join(str(c.get(k, "") or "") for k in ("address", "postal_code", "city")).strip()
    m = {
        "company.name": c.get("name"),
        "company.vat": c.get("siret") or c.get("tva_intracom"),
        "company.code_ape": c.get("code_ape"),
        "company.forme_juridique": c.get("forme_juridique"),
        "company.address": addr,
        "company.representant_legal": c.get("representant_legal"),
        "company.email": c.get("email"),
        "company.phone": c.get("phone"),
        "company.ca_n1": fmt_eur(c.get("ca_n1")) if c.get("ca_n1") else None,
        "company.ca_n2": fmt_eur(c.get("ca_n2")) if c.get("ca_n2") else None,
        "company.ca_n3": fmt_eur(c.get("ca_n3")) if c.get("ca_n3") else None,
        "company.effectif": c.get("effectif"),
        "company.city": c.get("city"),
        "project.objet": p.get("name"),
        "project.acheteur": p.get("client"),
        "project.reference": p.get("reference"),
        "date.today": _dt.date.today().strftime("%d/%m/%Y"),
    }
    return m.get(key)  # None pour "manual" / clé inconnue → champ à remplir


def generate_national_form(c, p, spec):
    """Génère le brouillon pré-rempli d'un formulaire national à partir d'une spec
    (sections + champs mappés aux données Adjugo). Voir app/services/national_forms.py."""
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as _colors
    import datetime as _dt

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm)
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="NFTitle", fontSize=14, fontName="Helvetica-Bold", spaceAfter=4))
    s.add(ParagraphStyle(name="NFSub", fontSize=8.5, textColor=_colors.HexColor("#555555"), spaceAfter=10))
    s.add(ParagraphStyle(name="NFH", fontSize=11, fontName="Helvetica-Bold",
                         textColor=_colors.HexColor("#2C5BD8"), spaceBefore=10, spaceAfter=5))
    body = s["Normal"]; body.fontSize = 9; body.leading = 13

    def kv(rows):
        t = Table(rows, colWidths=[70 * mm, 95 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, _colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    e = [Paragraph(_esc(spec.get("form_name", "")), s["NFTitle"]),
         Paragraph(_esc(spec.get("intro_note", "")), s["NFSub"])]
    for sec in spec.get("sections", []):
        if sec.get("title"):
            e.append(Paragraph(_esc(sec["title"]), s["NFH"]))
        rows = []
        for fld in sec.get("fields", []):
            val = _resolve_source(fld.get("source", ""), c, p)
            rows.append([Paragraph("<b>" + _esc(fld.get("label", "")) + "</b>", body),
                         Paragraph(_esc(val if val not in (None, "") else "—"), body)])
        if rows:
            e.append(kv(rows))
    if spec.get("declaration_lines"):
        e.append(Spacer(1, 6))
        for line in spec["declaration_lines"]:
            e.append(Paragraph("• " + _esc(line), body))
    sig = spec.get("signature_labels", {}) or {}
    e.append(Spacer(1, 8 * mm))
    e.append(kv([
        [Paragraph("<b>" + _esc(sig.get("place", "Lieu")) + "</b>", body), Paragraph(_esc(c.get("city") or "—"), body)],
        [Paragraph("<b>" + _esc(sig.get("date", "Date")) + "</b>", body), Paragraph(_dt.date.today().strftime("%d/%m/%Y"), body)],
        [Paragraph("<b>" + _esc(sig.get("signatory", "Signature")) + "</b>", body), Paragraph(_esc(c.get("representant_legal") or "—"), body)],
    ]))
    if spec.get("official_url"):
        e.append(Spacer(1, 4))
        e.append(Paragraph(_esc("→ " + spec["official_url"]), s["NFSub"]))
    doc.build(e)
    return buf.getvalue()


# ================================================================
# DÉCLARATION SUR L'HONNEUR (art. R2143-3 CMP)
# Pièce universellement exigée par l'acheteur public ; son absence invalide
# le pli. Adjugo la génère pré-remplie, prête à dater et signer.
# ================================================================
_HONNEUR_POINTS = [
    "ne pas entrer dans l'un des cas d'interdiction de soumissionner mentionnés aux "
    "articles L2141-1 à L2141-5 et L2141-7 à L2141-11 du Code de la commande publique "
    "(condamnations pénales, faillite/liquidation judiciaire, manquements graves, etc.) ;",
    "être en règle au regard des articles L5212-1 à L5212-11 du Code du travail relatifs "
    "à l'obligation d'emploi des travailleurs handicapés ;",
    "avoir, au 31 décembre de l'année précédant le lancement de la consultation, souscrit "
    "les déclarations fiscales et sociales incombant à l'entreprise et acquitté les impôts, "
    "taxes et cotisations sociales exigibles (ou constitué les garanties équivalentes) ;",
    "que les renseignements et documents fournis dans la candidature et l'offre sont exacts ;",
    "m'engager, si l'entreprise est retenue, à produire dans le délai imparti les certificats "
    "et attestations prévus aux articles R2143-6 à R2143-10 du Code de la commande publique.",
]


def generate_attestation_honneur(c, p):
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as _colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=16 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            title="Déclaration sur l'honneur")
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="HTitle", fontSize=14, fontName="Helvetica-Bold", spaceAfter=2, alignment=1))
    s.add(ParagraphStyle(name="HSub", fontSize=8.5, textColor=_colors.HexColor("#555555"),
                         spaceAfter=12, alignment=1))
    s.add(ParagraphStyle(name="HH", fontSize=10.5, fontName="Helvetica-Bold",
                         textColor=_colors.HexColor("#2C5BD8"), spaceBefore=10, spaceAfter=5))
    body = s["Normal"]; body.fontSize = 9.5; body.leading = 14
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()

    def kv(rows):
        t = Table([[Paragraph("<b>" + k + "</b>", body), Paragraph(_esc(v) or "—", body)] for k, v in rows],
                  colWidths=[55 * mm, 110 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, _colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    e = [
        Paragraph("DÉCLARATION SUR L'HONNEUR", s["HTitle"]),
        Paragraph("Article R2143-3 du Code de la commande publique", s["HSub"]),

        Paragraph("Identité du candidat", s["HH"]),
        kv([("Dénomination", c.get("name")), ("Forme juridique", c.get("forme_juridique")),
            ("SIRET", c.get("siret")), ("Adresse", addr),
            ("Représentant légal", c.get("representant_legal"))]),

        Paragraph("Objet de la consultation", s["HH"]),
        kv([("Marché", p.get("name")), ("Acheteur public", p.get("client")),
            ("Référence", p.get("reference"))]),

        Spacer(1, 6),
        Paragraph("Je soussigné(e), représentant légal de l'entreprise désignée ci-dessus, "
                  "agissant en son nom et pour son compte, déclare sur l'honneur :", body),
        Spacer(1, 4),
    ]
    for pt in _HONNEUR_POINTS:
        e.append(Paragraph("•&nbsp;&nbsp;" + pt, body))
        e.append(Spacer(1, 2))

    e += [
        Spacer(1, 4),
        Paragraph("Fait pour servir et valoir ce que de droit.", body),
        Spacer(1, 10 * mm),
        kv([("Fait à", c.get("city")), ("Le", datetime.date.today().strftime("%d/%m/%Y")),
            ("Nom et qualité du signataire", c.get("representant_legal")), ("Signature", "")]),
        Spacer(1, 6),
        Paragraph("<font size=7 color='#888888'>Document pré-rempli par Adjugo à partir de votre "
                  "profil. Vérifiez chaque mention, datez et signez avant dépôt.</font>", body),
    ]
    doc.build(e)
    return buf.getvalue()


GENERATORS = {
    "dc1": generate_dc1,
    "dc2": generate_dc2,
    "dc4": generate_dc4,
    "attri1": generate_attri1,
    "honneur": generate_attestation_honneur,
    "dume": generate_dume,
}
