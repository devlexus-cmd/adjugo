"""
Compte-rendu du groupement (PDF) — DOCUMENT INTERNE AU CHEF DE FILE.

Synthèse de l'état d'un groupement : partenaires, lots couverts, éléments fournis de chaque
part, pièces reçues, parts reçues (calcul déterministe), et ce qu'il reste à compléter. Même
style reportlab que les formulaires officiels et l'estimation détaillée.

Réorganisation (décision 8) : « N sur M », jamais un pourcentage ni « N/M » ; « Partenaire du
groupement », jamais « Co-traitant » (comme la page du marché).

Seule l'organisation du chef de file le télécharge, et il reprend ce qu'elle voit déjà à
l'écran (l'ancien libellé « partageable » était trompeur). Ce n'est pas une pièce remise à
l'acheteur.

DOCTRINE DE VISIBILITÉ (oct. 2026) : le chef de file peut le transférer → jamais un prix par
membre (prix de lot, approche prix, décomposition). Seul le total de l'offre commune FIGÉE.
"""
import io
from xml.sax.saxutils import escape as _xml_escape

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



def _jour_mois_paris(frozen_at) -> str:
    """« 23/10 » : le jour de Paris d'un horodatage ISO (UTC s'il est naïf) ; le texte tel quel s'il ne se lit pas."""
    from datetime import datetime, timezone
    brut = str(frozen_at or "")
    try:
        dt = datetime.fromisoformat(brut)
    except ValueError:
        return brut[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    from app.services.format import _tz_paris
    tz = _tz_paris()
    return dt.astimezone(tz if tz is not None else timezone.utc).strftime("%d/%m")

def _e(value) -> str:
    """Valeur dynamique échappée (« A & B <Sàrl> » ne casse ni n'injecte de balisage)."""
    return _xml_escape(str(value if value is not None else ""))


def _p(text, style):
    """Texte brut : TOUT est échappé."""
    return Paragraph(_e(text or ""), style)


def _m(markup, style):
    """Balisage voulu (<b>, <font>, <br/>) : les valeurs dynamiques y sont passées par _e()."""
    return Paragraph(markup, style)


# Les éléments d'une part, ceux que compte le suivi du groupement (même liste que `_partner_flags`,
# app/routers/invites.py) : chacun est fourni ou non, sans pondération ni pourcentage.
ELEMENTS = {"submitted": "part envoyée", "lot": "lot précisé", "references": "références",
            "memoire": "paragraphe du dossier de présentation", "qualifications": "qualifications"}


def elements_fournis(p: dict) -> int:
    """Nombre d'éléments fournis d'une part, lus dans la vue du suivi (`partners` du cockpit)."""
    faits = {"submitted": p.get("status") == "submitted", "lot": bool(str(p.get("lot") or "").strip()),
             "references": bool(p.get("has_references")), "memoire": bool(p.get("has_memoire")),
             "qualifications": bool(p.get("qualifications_count"))}
    return sum(1 for k in ELEMENTS if faits[k])


def generate_consortium_report_pdf(project_name: str, mandataire: str, data: dict,
                                   contributions: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm, title="Compte-rendu du groupement")
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
    recues, invitees = int(r.get("submitted", 0) or 0), int(r.get("invited", 0) or 0)

    el = []
    el.append(_p("Compte-rendu du groupement", h1))
    el.append(_p("Document interne au chef de file — ne fait pas partie du dossier remis à l'acheteur", muted))
    el.append(Spacer(1, 7))
    el.append(_m(f"<b>{_e(project_name)}</b>", st))
    from app.services import pieces_fin       # le jour de Paris, jamais le jour UTC du serveur (format.py)
    el.append(_p(f"Chef de file : {mandataire or '—'} · édité le {pieces_fin.jour_paris().strftime('%d/%m/%Y')}",
                 muted))
    el.append(Spacer(1, 9))

    # Synthèse : les parts reçues, « N sur M » (comme la page du marché).
    col = _OK if invitees and recues >= invitees else (_WARN if recues else colors.HexColor("#C0392B"))
    synth = Table([[
        _m(f"<font color='#{col.hexval()[2:]}'><b>{_e(recues)} sur {_e(invitees)}</b></font>",
           ParagraphStyle("big", parent=st, fontSize=20, leading=24)),
        _p("parts reçues" if invitees > 1 else "part reçue", st),
        _m(f"{_e(r.get('lots', 0))} lot(s) couvert(s)", muted),
    ]], colWidths=[36 * mm, 45 * mm, 98 * mm])
    synth.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6, _LINE),
                               ("BACKGROUND", (0, 0), (-1, -1), _HEAD), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    el.append(synth)

    # Offre commune figée (seul montant imprimé, le document pouvant être transféré : le TOTAL).
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    if state.get("offer_frozen") and state.get("total_offre_ht") is not None:
        # Le jour de Paris de l'instant figé (UTC naïf côté serveur), comme le texte de la convention (« figée le … (heure
        # de Paris) ») ; le total au centime, comme la convention et l'acte d'engagement (groupement_convention.eur),
        # jamais arrondi à l'euro (contrôle des bugs, deuxième passe).
        frozen_fr = _jour_mois_paris(state.get("frozen_at"))
        from app.services.groupement_convention import eur
        el.append(_p(f"Offre commune figée le {frozen_fr} : total {eur(state['total_offre_ht'])} HT", h2))

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
    rows = [[_p("Entreprise", cellh), _p("Rôle", cellh), _p("Lot", cellh), _p("Statut", cellh), _p("Pièces", cellh),
             _p("Éléments fournis", cellh)]]
    for p in parts:
        stt = {"submitted": "Soumise", "draft": "Brouillon"}.get(p.get("status"), "En attente")
        rows.append([_p(p.get("company", ""), cell),
                     _p("Sous-traitant" if p.get("role") == "sous_traitant" else "Partenaire du groupement", cell),
                     _p(p.get("lot") or "—", cell), _p(stt, cell),
                     _p(str(p.get("pieces_count", 0)), cell), _p(f"{elements_fournis(p)} sur {len(ELEMENTS)}", cell)])
    t = Table(rows, colWidths=[50 * mm, 30 * mm, 36 * mm, 22 * mm, 16 * mm, 25 * mm])
    t.setStyle(_grid())
    el.append(t)

    # Détail des contributions soumises
    subs = [c for c in (contributions or []) if c.get("status") == "submitted"]
    if subs:
        el.append(_p("Apports détaillés (parts soumises)", h2))
        for c in subs:
            el.append(_m(f"<b>{_e(c.get('company_name', ''))}</b> — lot : {_e(c.get('lot') or '(non précisé)')}", st))
            if c.get("qualifications"):
                el.append(_p("Qualifications : " + ", ".join(str(q) for q in c["qualifications"]), muted))
            refs = [r.get("intitule", "") for r in (c.get("references") or []) if isinstance(r, dict) and r.get("intitule")]
            if refs:
                el.append(_p("Références : " + " · ".join(refs), muted))
            # DOCTRINE DE VISIBILITÉ : ce compte-rendu peut être transféré → AUCUN prix par membre
            # (ni approche prix, ni prix de lot, ni décomposition). Seul le total de l'offre
            # commune FIGÉE apparaît (bloc « Offre commune » ci-dessous).
            if c.get("memoire_paragraph"):
                el.append(_p("Paragraphe pour le dossier de présentation : " + c["memoire_paragraph"][:600], muted))
            el.append(Spacer(1, 5))

    # À compléter
    missing = r.get("missing", []) or []
    if missing:
        el.append(_p("À compléter", h2))
        for m in missing:
            el.append(_p("• " + m, ParagraphStyle("miss", parent=muted, textColor=_WARN)))

    el.append(Spacer(1, 12))
    el.append(_p("Document généré par Adjugo. Les comptes et statuts sont calculés de façon déterministe à partir "
                 "des parts reçues — aucune donnée inventée. Éléments fournis : " + ", ".join(ELEMENTS.values()) + ".",
                 ParagraphStyle("foot", parent=muted, fontSize=7.5)))

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
