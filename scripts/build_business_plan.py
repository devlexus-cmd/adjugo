# -*- coding: utf-8 -*-
"""
Business Plan simplifié Adjugo — candidature The Square (EuraTechnologies).
A4 portrait, multi-pages. Rendu reportlab.
Sortie : /Users/eliot/Downloads/Adjugo_Business_Plan_The_Square.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, ListFlowable, ListItem)
from reportlab.lib.styles import ParagraphStyle
import html as _html

BLUE=HexColor("#1B4FFF"); INK=HexColor("#0A1730"); INK2=HexColor("#3D4A63"); MUTED=HexColor("#5A6573")
LINE=HexColor("#E6E9F0"); SOFT=HexColor("#F4F6FB"); BLUEBG=HexColor("#EDF1FF"); GREEN=HexColor("#1D9E75")
PW, PH = A4
MX = 18*mm
OUT="/Users/eliot/Downloads/Adjugo_Business_Plan_The_Square.pdf"
def E(s): return _html.escape(str(s),quote=False).replace("\n","<br/>")

S={}
S['h1']=ParagraphStyle('h1',fontName='Helvetica-Bold',fontSize=16,textColor=INK,spaceBefore=4,spaceAfter=7,leading=19)
S['kick']=ParagraphStyle('kick',fontName='Helvetica-Bold',fontSize=9.5,textColor=BLUE,spaceAfter=3,leading=12)
S['body']=ParagraphStyle('body',fontName='Helvetica',fontSize=10.5,textColor=INK2,leading=15.5,spaceAfter=7,alignment=TA_JUSTIFY)
S['bul']=ParagraphStyle('bul',fontName='Helvetica',fontSize=10.5,textColor=INK2,leading=15,spaceAfter=4)
S['note']=ParagraphStyle('note',fontName='Helvetica-Oblique',fontSize=8.8,textColor=MUTED,leading=12,spaceBefore=4)
S['cell']=ParagraphStyle('cell',fontName='Helvetica',fontSize=9.5,textColor=INK2,leading=13)
S['cellb']=ParagraphStyle('cellb',fontName='Helvetica-Bold',fontSize=9.5,textColor=INK,leading=13)
S['cellw']=ParagraphStyle('cellw',fontName='Helvetica-Bold',fontSize=9.5,textColor=white,leading=13)
# cover
S['ctitle']=ParagraphStyle('ctitle',fontName='Helvetica-Bold',fontSize=40,textColor=INK,leading=42,spaceAfter=6)
S['ctag']=ParagraphStyle('ctag',fontName='Helvetica',fontSize=15,textColor=INK2,leading=21,spaceAfter=4)
S['cmeta']=ParagraphStyle('cmeta',fontName='Helvetica',fontSize=10.5,textColor=MUTED,leading=16)
S['cbadge']=ParagraphStyle('cbadge',fontName='Helvetica-Bold',fontSize=10.5,textColor=BLUE,leading=14)

def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(t, S['bul']), leftIndent=10, value='•') for t in items],
        bulletType='bullet', bulletColor=BLUE, bulletFontSize=8, leftIndent=12, spaceBefore=0, spaceAfter=4)

def kv_table(rows, col0=42*mm):
    w = PW-2*MX
    data=[[Paragraph(f"<b>{E(k)}</b>", S['cellb']), Paragraph(E(v), S['cell'])] for k,v in rows]
    t=Table(data, colWidths=[col0, w-col0])
    t.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LINEBELOW',(0,0),(-1,-2),0.5,LINE),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),6),
    ]))
    return t

def grid_table(header, rows, widths):
    data=[[Paragraph(E(h), S['cellw']) for h in header]]
    for r in rows:
        data.append([Paragraph(E(r[0]), S['cellb'])]+[Paragraph(E(c), S['cell']) for c in r[1:]])
    t=Table(data, colWidths=widths)
    st=[('BACKGROUND',(0,0),(-1,0),INK),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,1),(-1,-1),0.5,LINE),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[white,SOFT])]
    t.setStyle(TableStyle(st)); return t

def section(kick, title, *flows):
    out=[Paragraph(E(kick), S['kick']), Paragraph(E(title), S['h1'])]
    out.extend(flows); out.append(Spacer(1, 7*mm)); return out

# ---------- doc ----------
def header_footer(canvas, doc):
    canvas.saveState()
    if doc.page>1:
        canvas.setFont('Helvetica-Bold',9); canvas.setFillColor(BLUE)
        canvas.drawString(MX, PH-12*mm, "Adjugo")
        canvas.setFont('Helvetica',8); canvas.setFillColor(MUTED)
        canvas.drawRightString(PW-MX, PH-12*mm, "Business Plan simplifié — The Square")
        canvas.setStrokeColor(LINE); canvas.setLineWidth(0.5)
        canvas.line(MX, PH-14*mm, PW-MX, PH-14*mm)
        canvas.setFillColor(MUTED); canvas.setFont('Helvetica',8)
        canvas.drawCentredString(PW/2, 10*mm, f"{doc.page}")
    canvas.restoreState()

doc=BaseDocTemplate(OUT, pagesize=A4, leftMargin=MX, rightMargin=MX, topMargin=20*mm, bottomMargin=16*mm, title="Adjugo — Business Plan simplifié")
frame=Frame(MX, 16*mm, PW-2*MX, PH-36*mm, id='main', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
cover=Frame(MX, 16*mm, PW-2*MX, PH-32*mm, id='cover', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([
    PageTemplate(id='cover', frames=[cover], onPage=header_footer),
    PageTemplate(id='main', frames=[frame], onPage=header_footer),
])

st=[]
# ---- COVER ----
st.append(Spacer(1, 30*mm))
st.append(Paragraph("CANDIDATURE — THE SQUARE · EURATECHNOLOGIES", S['cbadge']))
st.append(Spacer(1, 6*mm))
st.append(Paragraph("Adjugo", S['ctitle']))
st.append(Paragraph("Le copilote des marchés publics — de la veille au dépôt du dossier.<br/>"
                    "Et le réseau qui fait répondre les PME <b>ensemble</b>.", S['ctag']))
st.append(Spacer(1, 10*mm))
st.append(Paragraph("<b>Business Plan simplifié</b>", ParagraphStyle('x',fontName='Helvetica-Bold',fontSize=14,textColor=BLUE)))
st.append(Spacer(1, 4*mm))
st.append(Paragraph("Ambition : devenir la plateforme n°1 des marchés publics en Europe, "
                    "et bâtir un véritable réseau Adjugo au service des PME <b>et</b> des collectivités.", S['cmeta']))
st.append(Spacer(1, 14*mm))
st.append(Paragraph("Eliot Viegas — technique &amp; produit&nbsp;&nbsp;·&nbsp;&nbsp;Mathys Guena — business &amp; développement", S['cmeta']))
st.append(Paragraph("Produit en ligne : adjugo.pro&nbsp;&nbsp;·&nbsp;&nbsp;Lille / Bretagne&nbsp;&nbsp;·&nbsp;&nbsp;Juin 2026", S['cmeta']))
st.append(PageBreak())

# ---- 1. PROBLÈME ----
st += section("01 — Le problème",
    "Répondre à un marché public, c'est un parcours du combattant",
    Paragraph("La commande publique pèse environ <b>160 Md€/an en France</b> et près de "
              "<b>2 000 Md€/an en Europe</b> (~14&nbsp;% du PIB). C'est un débouché énorme — mais quasi inaccessible "
              "pour une PME sans service dédié.", S['body']),
    bullets([
        "<b>Trouver</b> les bons marchés : ils sont éparpillés sur des dizaines de plateformes.",
        "<b>Comprendre</b> des dossiers de 100+ pages (règlement, cahiers des charges) écrits en langage administratif.",
        "<b>Monter</b> un dossier lourd : formulaires officiels, attestations, pièces à jour, sous peine de rejet.",
        "<b>Chiffrer juste</b>, et le plus souvent <b>répondre seul</b> — donc perdre face aux grands groupes.",
    ]),
    Paragraph("Résultat : les PME s'autocensurent. Et en face, les <b>collectivités</b> reçoivent trop peu d'offres "
              "de PME locales qualifiées — moins de concurrence, moins d'ancrage territorial, un achat public moins durable.", S['body']),
)

# ---- 2. SOLUTION ----
st += section("02 — La solution",
    "Adjugo : un copilote qui fait le chemin complet, en ligne et déjà fonctionnel",
    Paragraph("Adjugo (adjugo.pro) accompagne une PME du premier marché jusqu'au dépôt du dossier, "
              "en cinq étapes simples — sans jargon, accessible à un artisan comme à un bureau d'études :", S['body']),
    bullets([
        "<b>Trouver des marchés</b> — veille sur les sources officielles (BOAMP en France, TED pour toute l'Europe).",
        "<b>Décider</b> — l'IA analyse le dossier et donne une <b>compatibilité en %</b> avec l'entreprise (on informe, on ne décide pas à sa place).",
        "<b>Estimer le prix</b> — chiffrage à partir des tarifs réels de l'entreprise, tableau de prix exportable.",
        "<b>Préparer les documents</b> — formulaires officiels pré-remplis + dossier de présentation rédigé <b>à partir du savoir-faire réel</b> de l'entreprise.",
        "<b>Répondre à plusieurs</b> — monter un groupement et assembler une réponse commune.",
    ]),
    Paragraph("Un module de <b>veille amont</b> détecte même les projets d'investissement dans les délibérations des "
              "collectivités, <b>des mois avant</b> la publication de l'appel d'offres.", S['body']),
    Paragraph("Toutes les données proviennent des <b>sources officielles</b> (BOAMP, TED, registre SIRENE) et restent "
              "reliées à l'avis d'origine — vérifiables d'un clic. Le tout porté par une <b>IA souveraine française "
              "(Mistral)</b>, hébergée en UE — un atout de conformité décisif pour le secteur public.", S['body']),
)

# ---- 3. RÉSEAU ----
st += section("03 — L'avantage : le réseau Adjugo",
    "Pas un simple outil — un réseau à deux faces",
    Paragraph("Notre différenciation profonde, c'est le <b>réseau</b> que l'outil construit :", S['body']),
    bullets([
        "<b>Côté PME — répondre ensemble.</b> Plusieurs PME se groupent sur un marché trop gros pour elles seules. "
        "Chacune apporte sa part via un lien sécurisé, <b>sans jamais voir les données des autres</b> ; l'IA fusionne "
        "le tout en une réponse commune. Le cloisonnement est garanti par construction.",
        "<b>Côté collectivités — sourcer local.</b> À terme, les acheteurs publics viennent sur Adjugo pour trouver des "
        "PME locales qualifiées et structurer des groupements : plus d'offres reçues, plus d'ancrage territorial, "
        "un achat plus durable.",
    ]),
    Paragraph("Les deux faces se renforcent : plus de PME sur le réseau = plus de valeur pour les collectivités, et "
              "inversement. C'est un <b>effet de réseau</b> défendable, difficile à copier par un simple logiciel de veille.", S['body']),
    Paragraph("Phase 1 (maintenant) : produit PME + premiers pilotes collectivités. Phase 2 : produit acheteur dédié.", S['note']),
)

# ---- 4. MARCHÉ + BUSINESS MODEL ----
st += section("04 — Marché & modèle économique",
    "Un marché immense, un modèle SaaS clair",
    Paragraph("<b>Marché.</b> ~160 Md€/an en France, ~2 000 Md€/an en Europe. Cible initiale : les PME du BTP, des "
              "services et des études — artisans, indépendants, TPE/PME. Notre moteur s'appuie déjà sur TED : il est "
              "<b>européen dès le départ</b>.", S['body']),
    Paragraph("<b>Modèle.</b> Abonnement SaaS, sans engagement, avec paiement à l'usage au-delà du quota :", S['body']),
    grid_table(
        ["Offre", "Prix", "Inclus"],
        [["Découverte", "0 €/mois", "2 analyses/mois · recherche BOAMP réelle · 1 utilisateur"],
         ["Pro", "129 €/mois", "30 analyses · savoir-faire + rédaction IA sourcée · partenaires vérifiés · formulaires officiels"],
         ["Business", "199 €/mois", "100 analyses · multi-utilisateurs · multi-pays · API · support prioritaire"]],
        [30*mm, 24*mm, PW-2*MX-54*mm]),
    Paragraph("Au-delà du quota : 5 €/analyse (jamais de blocage). Revenus additionnels à venir : volet acheteur "
              "(collectivités) et services du réseau.", S['note']),
)

# ---- 5. TRACTION + ROADMAP ----
st += section("05 — Traction & feuille de route",
    "Le produit existe déjà — la beta est lancée",
    bullets([
        "<b>Produit en ligne et fonctionnel</b> (adjugo.pro), données réelles branchées (BOAMP, TED, registre SIRENE).",
        "<b>Beta PME en cours</b> (objectif 5 à 10) — Bretagne, région parisienne, Lille.",
        "<b>Conformité</b> : pages légales et RGPD en ligne (dont l'accord de traitement / DPA).",
        "<b>Coût d'infrastructure maîtrisé</b> et 0 salaire fondateur au démarrage → burn minimal.",
    ]),
    Paragraph("<b>Feuille de route 6 mois</b> (alignée sur les KPIs) :", S['body']),
    bullets([
        "Convertir la beta en PME payantes et industrialiser l'acquisition.",
        "Ouvrir le 1er marché européen : la <b>Belgique</b> (francophone, frontalière, depuis Lille).",
        "Signer <b>3 pilotes collectivités</b> pour amorcer la face acheteur du réseau.",
    ]),
)

# ---- 6. EXPANSION ----
st += section("06 — Expansion européenne",
    "France d'abord, puis l'Europe — la techno est déjà prête",
    Paragraph("Séquence : <b>France</b> (base) → <b>Belgique</b> → <b>Pays-Bas</b> &amp; <b>Espagne</b>. "
              "Comme TED couvre déjà toute l'UE, l'expansion n'est pas une refonte technique : la localisation se résume "
              "à la <b>langue</b> et aux <b>plateformes nationales de dépôt</b>. L'objectif à The Square : être présent "
              "sur au moins <b>3 pays</b> à 6 mois.", S['body']),
)

# ---- 7. ÉQUIPE ----
st += section("07 — L'équipe",
    "Deux fondateurs complémentaires, qui se connaissent depuis le collège",
    kv_table([
        ("Eliot Viegas", "Technique & produit (Audencia / Centrale Nantes). Conçoit et opère la plateforme."),
        ("Mathys Guena", "Business & développement (l'iteem — SKEMA / Centrale Lille). Basé à Lille."),
        ("Le binôme", "Deux Bretons, amis de longue date. Profils tech + business qui se complètent. "
                       "Pas de salaire fondateur au démarrage : on construit avant de coûter."),
    ]),
)

# ---- 8. CONCURRENCE ----
st += section("08 — Concurrence & différenciation",
    "Les autres couvrent un bout du chemin. Nous, le chemin entier — plus le réseau",
    Paragraph("Les solutions existantes traitent une étape isolée : veille d'appels d'offres, plateformes côté "
              "acheteur, ou agences de réponse facturées au dossier. Aucune ne réunit ce que fait Adjugo :", S['body']),
    bullets([
        "Le <b>bout-en-bout</b> : trouver → décider → estimer → préparer → déposer, dans un seul outil.",
        "Le <b>réseau de groupements cloisonnés</b> (répondre à plusieurs en sécurité).",
        "Le <b>two-sided</b> PME ↔ collectivités, qui crée un effet de réseau.",
        "Une <b>IA souveraine (Mistral, française)</b>, hébergée en UE — un atout de conformité pour le secteur public.",
    ]),
)

# ---- 9. FINANCIER ----
st += section("09 — Financier simplifié",
    "Burn minimal, croissance par l'usage — projections prudentes",
    grid_table(
        ["Indicateur", "Aujourd'hui", "+6 mois", "+12 mois"],
        [["PME payantes", "beta (5–10 testeurs)", "30–40", "~100"],
         ["MRR (€)", "0", "~4–5 k", "~12–15 k"],
         ["Pilotes collectivités", "0", "3 (lettres d'intention)", "premiers contrats"],
         ["Pays ouverts", "1 (France)", "2 (FR + Belgique)", "3–4"],
         ["Burn mensuel", "faible (infra + API)", "faible (0 salaire fondateur)", "1ers recrutements"]],
        [38*mm, 38*mm, 40*mm, PW-2*MX-116*mm]),
    Paragraph("Chiffres présentés comme <b>hypothèses</b> de travail, à confirmer pendant le programme. "
              "Le modèle est volontairement frugal : on atteint la rentabilité unitaire dès les premiers abonnements.", S['note']),
)

# ---- 10. DEMANDE ----
st += section("10 — Pourquoi The Square & notre demande",
    "Le bon accélérateur, au bon endroit, au bon moment",
    Paragraph("EuraTechnologies est LE hub B2B et govtech des Hauts-de-France — région frontalière de la Belgique, "
              "et là où vit Mathys. C'est exactement l'écosystème dont Adjugo a besoin. Ce qu'on attend du programme :", S['body']),
    bullets([
        "L'<b>accès au réseau public</b> (collectivités, région) pour amorcer la face acheteur du réseau Adjugo.",
        "L'<b>accompagnement go-to-market B2B</b> et la structuration de l'expansion européenne.",
        "La <b>crédibilité institutionnelle</b> pour signer nos premiers pilotes collectivités.",
        "Le <b>cadre</b> pour passer de deux fondateurs étudiants à une vraie entreprise qui scale.",
    ]),
    Paragraph("Adjugo, c'est l'ambition de devenir la plateforme n°1 des marchés publics en Europe — et The Square "
              "est l'endroit pour la mettre sur orbite.", S['body']),
)

doc.build(st)
print("OK ->", OUT)
