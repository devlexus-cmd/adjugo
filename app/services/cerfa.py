"""
Adjugo - CERFA Overlay v4 FINAL
Coordonnees precises relevees sur les grilles officielles.
Support co-traitants pour DC1 section E et DC2 multiples.
"""
import io, os
from xml.sax.saxutils import escape as _xml_escape
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



def _jour_fr() -> str:
    """Le jour imprimé sur les formulaires (« Fait à …, le … », lieu et date du titulaire) : celui de Paris, comme les
    documents lus par une TPE (app/services/format.py), jamais le jour UTC du serveur, qui est la veille entre 0 h et
    2 h à Paris (contrôle des bugs, deuxième passe). Lu à chaque appel (pieces_fin.jour_paris)."""
    from app.services import pieces_fin
    return pieces_fin.jour_paris().strftime("%d/%m/%Y")

def _esc(s) -> str:
    """Échappe une valeur DYNAMIQUE (nom d'entreprise, objet du marché…) avant de l'insérer
    dans un Paragraph reportlab, qui interprète un mini-HTML : « A & B <Sàrl> » cassait la
    génération ou injectait du balisage. Le balisage voulu (<b>…</b>) reste hors de l'appel."""
    return _xml_escape(str(s if s is not None else ""))


# Référence imprimée sur les pièces remises à l'acheteur (DUME, déclaration sur l'honneur, formulaires
# nationaux) : celle de l'avis publié que l'analyse a lu (source officielle), jamais le numéro interne
# d'Adjugo. Sans avis connu, le champ reste à compléter par l'entreprise.
REFERENCE_A_COMPLETER = "À compléter (référence de la consultation donnée par l'acheteur)"


def reference_consultation(analysis) -> "str | None":
    """« avis BOAMP n° 26-123456 » d'après `ai_analysis.source`, sinon None (champ à compléter)."""
    src = analysis.get("source") if isinstance(analysis, dict) else None
    if not isinstance(src, dict):
        return None
    ref = " ".join(str(src.get("official_ref") or "").split())[:60]
    if not ref:
        return None
    nom = " ".join(str(src.get("source") or "").split())[:30]
    return f"avis {nom} n° {ref}" if nom else ref


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


def _ca(v) -> str:
    """Chiffre d'affaires pour une case du DC2 : vide si inconnu ou nul (jamais « 0 »)."""
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return ""
    return fmt_int(f) if f > 0 else ""


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


# ── Rôles : co-traitant (MEMBRE du groupement) vs sous-traitant ──────────────
# Distinction JURIDIQUE : un co-traitant est membre du groupement (DC1 section E + un
# DC2), un sous-traitant N'EST PAS membre (il relève du DC4). Les confondre produit des
# pièces invalides. On tolère les variantes d'orthographe du rôle.
def _is_soustraitant(m) -> bool:
    return str((m or {}).get("role", "")).strip().lower().replace("-", "_") == "sous_traitant"


def _groupement_members(cotraitants):
    """Co-traitants MEMBRES du groupement (hors sous-traitants → DC4)."""
    return [ct for ct in (cotraitants or []) if not _is_soustraitant(ct)]


def _soustraitants(cotraitants):
    return [ct for ct in (cotraitants or []) if _is_soustraitant(ct)]


# ================================================================
# DC1 - LETTRE DE CANDIDATURE (6 pages)
# ================================================================
def generate_dc1(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "dc1.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC1", c, p)

    d = _jour_fr()
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    # SECTION E = membres du GROUPEMENT uniquement. Les sous-traitants sont exclus ici
    # (ils sont déclarés au DC4), sinon un sous-traitant apparaissait à tort comme membre.
    cotraitants = _groupement_members(p.get("cotraitants", []))
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
        # Groupement : on COCHE « Le candidat est un groupement d'entreprises » (case relevée
        # sur dc1.pdf — centre x=76.7 aligné sur la case « seul », y=389.5 = milieu de la ligne
        # à y≈384). On NE remplit PAS les champs du candidat individuel (section « se présente
        # seul ») : le groupement est décrit par le TABLEAU des membres (section E) + la page
        # mandataire. Sans cette case, le formulaire ne déclarait JAMAIS le groupement.
        fields[2] = [
            {"type": "checkbox", "x": 76.7, "y": 389.5},
        ]
        # Forme du groupement et mandataire solidaire (cases relevées sur dc1.pdf) : SEULEMENT
        # si une convention de groupement générée les fixe — jamais devinées.
        grp = p.get("groupement") if isinstance(p.get("groupement"), dict) else {}
        forme = grp.get("forme") or ""
        if forme == "conjoint":
            fields[2].append({"type": "checkbox", "x": 105.15, "y": 415.65})
            # « En cas de groupement conjoint, le mandataire est solidaire : Non / Oui »
            fields[2].append({"type": "checkbox", "x": 247.05 if grp.get("mandataire_solidaire") else 105.15,
                              "y": 476.4})
        elif forme == "solidaire":
            fields[2].append({"type": "checkbox", "x": 247.05, "y": 415.65})

        # Section E — tableau des membres : 4 lignes (2 en bas de la page 3, y≈650-752 ; 2 en
        # haut de la page 4, y≈23-125), colonnes « N° du lot » | identité | prestations.
        # (Avant : écrit à y=520, PAR-DESSUS l'en-tête du tableau.)
        rows = [(2, 649.6), (2, 700.6), (3, 22.7), (3, 73.7)]
        members = [c] + list(cotraitants)
        shown = members if len(members) <= len(rows) else members[:len(rows) - 1]
        for (page, top), m in zip(rows, shown):
            fields[page] += _dc1_member_row(m, top, mandataire=(m is c), conjoint=(forme != "solidaire"),
                                            lot_override=(grp.get("mandataire") or {}).get("lot") if m is c else None)
        if len(members) > len(rows):
            rest = members[len(rows) - 1:]
            page, top = rows[-1]
            fields[page].append({"type": "multiline", "x": 82, "y": top + 10, "size": 6.8, "line_height": 9.5,
                                 "text": "\n".join(_wrap("Autres membres : " + ", ".join(_one(r.get("name"), 60) for r in rest), 62)[:3]
                                                   + ["(détail : convention de groupement jointe)"])})

        # Section G — désignation du mandataire : nom en bas de la page 5 (ligne vide sous
        # « Nom commercial… »), puis adresse / courriel / téléphone / SIRET page 6, chacun sur
        # la ligne vide sous son libellé (avant : décalés d'un cran, sur les libellés).
        fields[4].append({"x": 64, "y": 770.5, "text": _one(c.get("name", ""), 80), "size": 9, "bold": True})
        fields[5] = [
            {"x": 64, "y": 68, "text": _one(addr, 95), "size": 9},
            {"x": 64, "y": 115, "text": _one(c.get("email", ""), 95), "size": 9},
            {"x": 64, "y": 161, "text": _one(c.get("phone", ""), 40), "size": 9},
            {"x": 64, "y": 219, "text": _one(c.get("siret", ""), 20), "size": 10, "bold": True},
        ]

    return merge_overlay(tpl, create_overlay(fields))


def _one(v, n: int = 120) -> str:
    """Valeur sur UNE ligne (aucun saut de ligne ni caractère de contrôle), bornée."""
    import re as _re
    s = _re.sub(r"[\x00-\x1f\x7f]", " ", str(v if v is not None else ""))
    return _re.sub(r"\s+", " ", s).strip()[:n]


def _wrap(text: str, width: int) -> list:
    import textwrap
    return textwrap.wrap(_one(text, 1000), width=width) or [""]


def _lot_number(lot) -> str:
    import re as _re
    m = _re.search(r"\blot\s*(?:n\s*[°o]\s*)?(\d{1,3})\b", str(lot or ""), _re.IGNORECASE)
    return m.group(1) if m else ""


def _dc1_member_row(m, top: float, mandataire: bool, conjoint: bool, lot_override=None) -> list:
    """Une ligne du tableau E du DC1 : n° de lot | identité (4 lignes) | prestations."""
    addr = _one(" ".join(str(m.get(k, "") or "") for k in ("address", "postal_code", "city")), 70)
    contact = " - ".join(x for x in (_one(m.get("email"), 40), _one(m.get("phone"), 20)) if x)
    ident = [_one(m.get("name"), 55) + (" (mandataire)" if mandataire else ""), addr, contact,
             ("SIRET : " + _one(m.get("siret"), 20)) if _one(m.get("siret")) else ""]
    out = [{"type": "multiline", "x": 82, "y": top + 10, "text": "\n".join(x for x in ident if x),
            "size": 6.8, "line_height": 9.8}]
    lot = lot_override if lot_override is not None else m.get("lot")
    if _lot_number(lot):
        out.append({"x": 44, "y": top + 12, "text": _lot_number(lot), "size": 8, "bold": True})
    if conjoint and _one(lot):
        out.append({"type": "multiline", "x": 302, "y": top + 10, "size": 7, "line_height": 9.8,
                    "text": "\n".join(_wrap(lot, 58)[:4])})
    return out


# ================================================================
# DC2 - DECLARATION DU CANDIDAT (3 pages)
# Genere un DC2 par membre (mandataire + co-traitants)
# ================================================================
def generate_dc2(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "dc2.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC2", c, p)

    # Un DC2 par MEMBRE du groupement (mandataire + co-traitants) — PAS les sous-traitants,
    # qui ne sont pas membres du groupement (ils relèvent du DC4).
    cotraitants = _groupement_members(p.get("cotraitants", []))
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
    d = _jour_fr()
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    name = c.get("name", "")
    siret = c.get("siret", "")

    # Bloc C1 : nom, adresse, email, tel, siret sur plusieurs lignes. Lignes vides retirées et
    # interligne resserré : 5 lignes à 14 pt débordaient sur le libellé « Forme juridique ».
    c1_lines = [_one(name, 90), _one(addr, 90), _one(c.get("email", ""), 90), _one(c.get("phone", ""), 40),
                "SIRET : " + _one(siret, 20)]
    c1_text = "\n".join(x for x in c1_lines if x and x != "SIRET : ") or _one(name, 90)

    fields = {
        # Page 1
        0: [
            # A - pouvoir adjudicateur
            {"x": 42, "y": 315, "text": p.get("client", ""), "size": 10, "bold": True},
            # B - objet du marche
            {"x": 42, "y": 415, "text": p.get("name", ""), "size": 10, "bold": True},
            # C1 - nom, adresse, email, tel, siret
            {"type": "multiline", "x": 42, "y": 553, "text": c1_text, "size": 8.5, "bold": False, "line_height": 11},
            # Forme juridique
            {"x": 42, "y": 635, "text": c.get("forme_juridique", ""), "size": 9},
            # Personne ayant le pouvoir d'engager le membre : « nom, prénom et qualité » (la
            # qualité vient de la part du partenaire / de la convention de groupement).
            {"x": 107, "y": 715, "text": _one(", ".join(x for x in (_one(c.get("representant_legal", ""), 80),
                                                                    _one(c.get("signataire_qualite", ""), 60)) if x), 110),
             "size": 9, "bold": True},
        ],
        # Page 2: D1 - CA global, ligne y≈672. Les 3 colonnes « Exercice » du template dc2.pdf
        # sont aux entêtes x≈174 / 303 / 431 (relevé fitz) → on place la valeur DANS chaque
        # colonne (avant, ca_n1 atterrissait à x=55 DANS le libellé de ligne et la 3ᵉ colonne
        # restait vide). Ordre gauche→droite = du plus ANCIEN (N-3) au plus RÉCENT (N-1).
        # CA inconnu (partenaire qui ne l'a pas déclaré) → case VIDE, jamais « 0 » inventé.
        1: [
            {"x": 185, "y": 672, "text": _ca(c.get("ca_n3")), "size": 8},
            {"x": 315, "y": 672, "text": _ca(c.get("ca_n2")), "size": 8},
            {"x": 443, "y": 672, "text": _ca(c.get("ca_n1")), "size": 8},
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
    """UN DC4 par SOUS-TRAITANT déclaré (role == sous_traitant) : section D = titulaire/
    candidat (c), section E = identité du sous-traitant, section F = nature des prestations
    (son lot). Sans sous-traitant, on produit un DC4 « titulaire seul » (section E à
    compléter à la main) — le dossier ne l'inclut de toute façon qu'en cas de sous-traitance."""
    tpl = os.path.join(TEMPLATES_DIR, "dc4.pdf")
    if not os.path.exists(tpl):
        return _fallback("DC4", c, p)

    subs = _soustraitants(p.get("cotraitants", []))
    if not subs:
        return _generate_single_dc4(tpl, c, None, p)

    writer = PdfWriter()
    for sub in subs:
        reader = PdfReader(io.BytesIO(_generate_single_dc4(tpl, c, sub, p)))
        for page in reader.pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _generate_single_dc4(tpl, c, sub, p):
    d = _jour_fr()
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
        # Page 3 (idx 2): E - identité du SOUS-TRAITANT (positions relevées sous chaque
        # libellé du template, alignées sur la section D).
        2: [], 3: [], 4: [], 5: [], 6: [],
        # Page 8 : M - Signatures. Lieu et date sur les lignes « A …, le … » du sous-traitant (x 77,9) et du titulaire
        # (x 326), à 459,6 points du bas du modèle (382 depuis le haut) ; la zone de l'acheteur, plus bas, reste vide.
        # Le sous-traitant a sa ville à lui, ou une ligne à remplir (contrôle des bugs, deuxième passe : les quatre
        # textes tombaient sous « Le représentant de l'acheteur », la ville du titulaire dans les deux colonnes).
        7: ([{"x": 87, "y": 382, "text": str((sub or {}).get("city") or ""), "size": 9},
             {"x": 192, "y": 382, "text": d, "size": 9}] if sub else [])
           + [{"x": 336, "y": 382, "text": str(c.get("city", "")), "size": 9},
              {"x": 428, "y": 382, "text": d, "size": 9}],
        8: [],
    }

    if sub:
        s_addr = (str(sub.get("address", "")) + " " + str(sub.get("postal_code", "")) + " " + str(sub.get("city", ""))).strip()
        fields[2] = [
            {"x": 44, "y": 216, "text": str(sub.get("name", "")), "size": 10, "bold": True},
            {"x": 44, "y": 253, "text": s_addr, "size": 9},
            {"x": 44, "y": 289, "text": str(sub.get("email", "")), "size": 9},
            {"x": 44, "y": 336, "text": str(sub.get("phone", "")), "size": 9},
            {"x": 44, "y": 382, "text": str(sub.get("siret", "")), "size": 9, "bold": True},
            {"x": 44, "y": 437, "text": str(sub.get("forme_juridique", "")), "size": 9},
        ]
        # Section F (page idx 3) : nature des prestations sous-traitées = lot du sous-traitant.
        lot = str(sub.get("lot", "")).strip()
        if lot:
            fields[3] = [{"type": "multiline", "x": 44, "y": 225, "text": lot, "size": 9, "line_height": 13}]

    return merge_overlay(tpl, create_overlay(fields))


# ================================================================
# ATTRI1 - ACTE D'ENGAGEMENT (7 pages)
# ================================================================
def generate_attri1(c, p):
    tpl = os.path.join(TEMPLATES_DIR, "attri1.pdf")
    if not os.path.exists(tpl):
        return _fallback("ATTRI1", c, p)

    d = _jour_fr()
    addr = (str(c.get("address", "")) + " " + str(c.get("postal_code", "")) + " " + str(c.get("city", ""))).strip()
    try:
        budget = max(0.0, float(p.get("budget", 0) or 0))   # négatif (chiffrage erroné) → traité « non chiffré »
    except (TypeError, ValueError):
        budget = 0.0
    # ATTRI1 = ACTE D'ENGAGEMENT : le montant est l'OFFRE DE PRIX juridiquement engageante du
    # candidat. S'il n'y a pas de chiffrage réel, on n'imprime PAS « 0 € » ni un budget supposé
    # de l'acheteur : on laisse « À COMPLÉTER » pour ne jamais engager un prix inventé/faux.
    has_price = budget > 0
    rate = p.get("tva_rate", 0) or 0
    tva = budget * rate / 100.0
    ttc = budget + tva
    tva_label = (fmt_pct(rate) + " %") if rate else "0 % — TVA non applicable (art. 293 B CGI)"
    montant_ht_txt = fmt_eur(budget) if has_price else "À COMPLÉTER (chiffrez le marché)"
    montant_ttc_txt = fmt_eur(ttc) if has_price else "À COMPLÉTER"

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
            # Montant HT chiffres (offre du candidat — « À COMPLÉTER » si non chiffré)
            {"x": 230, "y": 563, "text": montant_ht_txt, "size": 9 if has_price else 6, "bold": True},
            # Montant TTC chiffres
            {"x": 210, "y": 622, "text": montant_ttc_txt, "size": 9 if has_price else 6, "bold": True},
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
        # Page 6 : la fin de la partie D, lieu, date et signature de l'ACHETEUR, qu'il remplit à l'attribution. Rien n'y
        # est écrit (contrôle des bugs, deuxième passe : la ville du candidat et le jour de création du document
        # tombaient sur sa ligne « A : …, le … »). Le lieu et la date du candidat sont en C1 (page 4).
        5: [],
        6: [],
    }

    cotraitants = _groupement_members(p.get("cotraitants", []))
    if cotraitants:
        _attri1_groupement(fields, c, cotraitants, p, d)

    return merge_overlay(tpl, create_overlay(fields))


def _attri1_groupement(fields: dict, c: dict, cotraitants: list, p: dict, d: str) -> None:
    """ATTRI1 d'un GROUPEMENT : « l'ensemble des membres s'engagent » (B1), forme et répartition
    des prestations avec le prix de vente de chaque part (B2, groupement conjoint), mandataire
    désigné et habilitation (C2), signataires (tableau page 5). Forme, habilitation et prix ne
    sont imprimés QUE s'ils viennent d'une convention de groupement générée (jamais devinés) :
    l'acte d'engagement dit alors exactement la même chose que la convention."""
    grp = p.get("groupement") if isinstance(p.get("groupement"), dict) else {}
    forme = grp.get("forme") or ""
    hab = grp.get("habilitation") if isinstance(grp.get("habilitation"), dict) else {}
    lead = dict(c)
    lead.update({k: v for k, v in (grp.get("mandataire") or {}).items() if k in ("lot", "prix_lot_ht")})
    members = [lead] + list(cotraitants)

    # B1 : la case « L'ensemble des membres du groupement s'engagent » au lieu de « engage la société ».
    fields[1] = [f for f in fields[1] if not (f.get("type") == "checkbox" and f.get("x") == 133.6)
                 and f.get("y") != 327]
    fields[1].append({"type": "checkbox", "x": 91.15, "y": 407.95, "size": 9.7})
    lines = [_one(m.get("name"), 60) + (" — SIRET " + _one(m.get("siret"), 20) if _one(m.get("siret")) else "")
             + (" (mandataire)" if m is lead else "") for m in members]
    if len(lines) > 3:
        lines = lines[:2] + [f"et {len(members) - 2} autre(s) membre(s) : voir la convention de groupement jointe"]
    for i, ln in enumerate(lines):
        fields[1].append({"x": 46, "y": 454 + i * 11.5, "text": ln, "size": 7.5, "bold": i == 0})

    # B2 : nature du groupement + répartition (groupement conjoint : désignation, prestation, montant HT).
    if forme == "conjoint":
        fields[2].append({"type": "checkbox", "x": 91.15, "y": 101.25, "size": 9.7})
        rows = [209.8, 260.8, 311.9]
        shown = members if len(members) <= len(rows) else members[:len(rows) - 1]
        for top, m in zip(rows, shown):
            fields[2].append({"type": "multiline", "x": 40, "y": top + 11, "size": 7, "line_height": 9.5,
                              "text": "\n".join([_one(m.get("name"), 55), "SIRET : " + _one(m.get("siret"), 20)]
                                                + (["(mandataire)"] if m is lead else []))})
            if _one(m.get("lot")):
                fields[2].append({"type": "multiline", "x": 266, "y": top + 11, "size": 7, "line_height": 9.5,
                                  "text": "\n".join(_wrap(m.get("lot"), 42)[:4])})
            if m.get("prix_lot_ht") is not None:
                fields[2].append({"x": 450, "y": top + 14, "text": fmt_eur(float(m["prix_lot_ht"])),
                                  "size": 8, "bold": True})
        if len(members) > len(rows):
            fields[2].append({"type": "multiline", "x": 40, "y": rows[-1] + 11, "size": 7, "line_height": 9.5,
                              "text": f"Et {len(members) - len(rows) + 1} autre(s) membre(s) :\nvoir l'annexe de "
                                      "répartition de la\nconvention de groupement jointe"})
    elif forme == "solidaire":
        fields[2].append({"type": "checkbox", "x": 247.05, "y": 101.25, "size": 9.7})

    # C1 (titulaire individuel) ne concerne pas un groupement : on le laisse vide.
    fields[3] = [f for f in fields[3] if f.get("y") not in (225, 238)]
    # C2 : mandataire désigné (ligne vide sous « [Indiquer le nom commercial…] »).
    fields[3].append({"x": 46, "y": 348, "text": _one(c.get("name"), 80), "size": 9, "bold": True})
    if _one(c.get("siret")):
        fields[3].append({"x": 46, "y": 359.5, "text": "SIRET : " + _one(c.get("siret"), 20), "size": 8})
    if forme == "conjoint":
        # « En cas de groupement conjoint, le mandataire du groupement est : conjoint / solidaire »
        fields[3].append({"type": "checkbox", "x": 247.05 if grp.get("mandataire_solidaire") else 91.15,
                          "y": 418.3, "size": 9.7})
    if hab:
        if hab.get("signer_candidature_offre"):
            # « ont donné mandat au mandataire, qui signe le présent acte d'engagement » :
            # pour signer + représenter + coordonner ; (+) modifications ultérieures.
            fields[3].append({"type": "checkbox", "x": 48.55, "y": 453.35, "size": 9.7})
            fields[3].append({"type": "checkbox", "x": 91.15, "y": 487.05, "size": 9.7})
            if hab.get("signer_modifications"):
                fields[3].append({"type": "checkbox", "x": 91.15, "y": 532.45, "size": 9.7})
        else:
            # « Les membres du groupement, qui signent le présent acte d'engagement » :
            fields[3].append({"type": "checkbox", "x": 48.55, "y": 610.45, "size": 9.7})
            if hab.get("representer", True):
                fields[3].append({"type": "checkbox", "x": 91.15, "y": 644.35, "size": 9.7})
            if hab.get("signer_modifications"):
                fields[3].append({"type": "checkbox", "x": 91.15, "y": 679.75, "size": 9.7})

    # Page 5 : tableau des signataires du groupement (5 lignes). Mandataire habilité à signer
    # seul → une ligne ; sinon une ligne par membre. Sans convention : la ligne du mandataire.
    sig_rows = [69.7, 120.7, 171.9, 222.9, 273.9]
    signers = [lead] if (not hab or hab.get("signer_candidature_offre")) else members
    nom_par = {s.get("company"): s for s in (grp.get("signataires") or []) if isinstance(s, dict)}
    for top, m in zip(sig_rows, signers[:len(sig_rows)]):
        s = nom_par.get(m.get("name")) or {}
        nom = _one(s.get("nom") or m.get("representant_legal"), 60)
        qual = _one(s.get("qualite") or m.get("signataire_qualite"), 50)
        fields[4].append({"x": 40, "y": top + 14, "text": ", ".join(x for x in (nom, qual) if x), "size": 8, "bold": True})
        fields[4].append({"x": 40, "y": top + 26, "text": _one(m.get("name"), 55)
                          + (" — mandataire, pour le groupement" if (m is lead and len(signers) == 1) else ""), "size": 7})
        if m is lead:
            fields[4].append({"x": 272, "y": top + 14, "text": _one(c.get("city"), 30) + ", le " + d, "size": 8})


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
        Paragraph(_esc(title) + " - Template introuvable", s["T"]),
        Spacer(1, 10 * mm),
        Paragraph("Entreprise : " + _esc(c.get("name", "")), s["Normal"]),
        Paragraph("SIRET : " + _esc(c.get("siret", "")), s["Normal"]),
        Paragraph("Marche : " + _esc(p.get("name", "")), s["Normal"]),
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
        t = Table([[Paragraph("<b>" + k + "</b>", body), Paragraph(_esc(v or "—"), body)] for k, v in rows],
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
    _tr = dume_translator(lang_name)

    def tr(fr: str) -> str:   # libellé traduit, échappé (il entre dans un Paragraph)
        return _esc(_tr(fr))

    e = [
        Paragraph(tr("DUME — Document Unique de Marché Européen"), s["DumeTitle"]),
        Paragraph(tr("Brouillon pré-rempli par Adjugo à partir de votre profil. À reporter sur le "
                     "e-DUME officiel. Vérifiez chaque champ avant dépôt."), s["DumeSub"]),

        Paragraph(tr("Partie I — Procédure et acheteur"), s["H"]),
        kv([(tr("Objet du marché"), p.get("name")), (tr("Acheteur public"), p.get("client")),
            (tr("Référence"), p.get("reference") or REFERENCE_A_COMPLETER)]),

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
            e.append(Paragraph(_esc(line), body))
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
            e.append(Paragraph(_esc(line), body))
    else:
        e.append(Paragraph("• " + tr("Aucune référence renseignée dans le profil."), body))

    e += [
        Paragraph(tr("Partie VI — Déclarations finales"), s["H"]),
        Paragraph(tr("Le signataire atteste l'exactitude des informations ci-dessus et accepte de fournir, "
                     "sur demande de l'acheteur, les certificats et documents justificatifs correspondants."), body),
        Spacer(1, 8 * mm),
        kv([(tr("Fait à"), c.get("city")), (tr("Le"), _jour_fr()),
            (tr("Signature (nom, qualité)"), c.get("representant_legal"))]),
    ]
    doc.build(e)
    return buf.getvalue()


# ================================================================
# FORMULAIRES NATIONAUX (piloté par spec) — brouillons pré-remplis fidèles
# au modèle officiel de chaque pays (PL, PT, IT, NL, RO). On présente toujours
# « brouillon à reporter sur le modèle officiel », jamais le formulaire officiel.
# ================================================================
def _resolve_source(key, c, p):
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
        "date.today": _jour_fr(),
    }
    return m.get(key)  # None pour "manual" / clé inconnue → champ à remplir


def generate_national_form(c, p, spec):
    """Génère le brouillon pré-rempli d'un formulaire national à partir d'une spec
    (sections + champs mappés aux données Adjugo). Voir app/services/national_forms.py."""
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as _colors

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
        [Paragraph("<b>" + _esc(sig.get("date", "Date")) + "</b>", body), Paragraph(_jour_fr(), body)],
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
            ("Référence", p.get("reference") or REFERENCE_A_COMPLETER)]),

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
        kv([("Fait à", c.get("city")), ("Le", _jour_fr()),
            ("Nom et qualité du signataire", c.get("representant_legal")), ("Signature", "")]),
        Spacer(1, 6),
        Paragraph("<font size=7 color='#888888'>Document pré-rempli par Adjugo à partir de votre "
                  "profil. Vérifiez chaque mention. À signer si le règlement de la consultation l'exige ; "
                  "sinon, signature à l'attribution.</font>", body),
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
