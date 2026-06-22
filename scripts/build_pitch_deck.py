# -*- coding: utf-8 -*-
"""
Pitch deck Adjugo — candidature The Square (EuraTechnologies). Format slides paysage.
Rendu reportlab. Sortie : /Users/eliot/Downloads/Adjugo_Pitch_Deck_The_Square.pdf
"""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak)
from reportlab.platypus.doctemplate import NextPageTemplate
from reportlab.lib.styles import ParagraphStyle
import html as _html

BLUE=HexColor("#1B4FFF"); INK=HexColor("#0A1730"); INK2=HexColor("#3D4A63"); MUTED=HexColor("#5A6573")
LINE=HexColor("#E6E9F0"); SOFT=HexColor("#F4F6FB"); BLUEBG=HexColor("#EDF1FF"); GREENBD=HexColor("#1D9E75")
PW, PH = landscape(A4)
OUT="/Users/eliot/Downloads/Adjugo_Pitch_Deck_The_Square.pdf"
def E(s): return _html.escape(str(s),quote=False).replace("\n","<br/>")

S={}
S['kick']=ParagraphStyle('kick',fontName='Helvetica-Bold',fontSize=11,textColor=BLUE,spaceAfter=4,leading=13)
S['title']=ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=27,textColor=INK,spaceAfter=4,leading=31)
S['sub']=ParagraphStyle('sub',fontName='Helvetica',fontSize=14,textColor=INK2,spaceAfter=10,leading=19)
S['big']=ParagraphStyle('big',fontName='Helvetica-Bold',fontSize=18,textColor=INK,leading=24,spaceBefore=4,spaceAfter=8)
S['bul']=ParagraphStyle('bul',fontName='Helvetica',fontSize=14,textColor=INK2,leading=21,leftIndent=16,bulletIndent=2,spaceAfter=8)
S['note']=ParagraphStyle('note',fontName='Helvetica-Oblique',fontSize=10,textColor=MUTED,leading=13,spaceBefore=6)
S['cell']=ParagraphStyle('cell',fontName='Helvetica',fontSize=12,textColor=INK2,leading=16)
S['cellb']=ParagraphStyle('cellb',fontName='Helvetica-Bold',fontSize=12.5,textColor=INK,leading=16)
S['kpiv']=ParagraphStyle('kpiv',fontName='Helvetica-Bold',fontSize=22,textColor=BLUE,alignment=TA_CENTER,leading=24)
S['kpil']=ParagraphStyle('kpil',fontName='Helvetica',fontSize=10,textColor=MUTED,alignment=TA_CENTER,leading=13)
S['pillt']=ParagraphStyle('pillt',fontName='Helvetica-Bold',fontSize=13,textColor=INK,leading=16,spaceAfter=2)
S['pilld']=ParagraphStyle('pilld',fontName='Helvetica',fontSize=10.5,textColor=INK2,leading=14)

story=[]; A=story.append
def kicker(n,label): A(Paragraph("%s · %02d" % (E(label), n), S['kick']))
def title(t): A(Paragraph(E(t), S['title']))
def sub(t): A(Paragraph(t if '<' in t else E(t), S['sub']))
def big(t): A(Paragraph(t if '<' in t else E(t), S['big']))
def bullets(items):
    for it in items: A(Paragraph(it if '<' in it else E(it), S['bul'], bulletText='▪'))
def note(t): A(Paragraph(E(t), S['note']))
def SP(h=8): A(Spacer(1,h))
def NEXT(): A(PageBreak())

def kpiband(items):
    row=[]
    for v,l in items:
        inner=Table([[Paragraph(E(v),S['kpiv'])],[Paragraph(E(l),S['kpil'])]],colWidths=[60*mm])
        inner.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        row.append(inner)
    t=Table([row],colWidths=[(250/len(row))*mm]*len(row))
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),SOFT),('BOX',(0,0),(-1,-1),0.5,LINE),
        ('INNERGRID',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    A(t); SP(10)

def chain(steps, last):
    cells=[]
    for s in steps:
        cells.append(Paragraph("<b>%s</b>" % E(s), S['cell']))
        cells.append(Paragraph("→", S['cellb']))
    cells.append(Paragraph("<b>%s</b>" % E(last), S['cellb']))
    n=len(cells)
    widths=[]
    for i in range(n):
        widths.append(8*mm if i%2 and i<n-1 else (250-8*(len(steps)))/(len(steps)+1)*mm)
    t=Table([cells], colWidths=widths)
    style=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,0),(-1,-1),'CENTER'),
           ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]
    for i in range(0,n,2):
        bg = BLUEBG if i<n-1 else HexColor("#1B4FFF")
        style.append(('BACKGROUND',(i,0),(i,0),bg))
        style.append(('BOX',(i,0),(i,0),0.5,LINE))
    t.setStyle(TableStyle(style)); A(t); SP(10)

def pillars(items):
    cells=[]
    for ttl,desc in items:
        inner=[Paragraph(E(ttl),S['pillt']),Paragraph(E(desc),S['pilld'])]
        cells.append(inner)
    t=Table([cells],colWidths=[(250/len(items))*mm]*len(items))
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),SOFT),('BOX',(0,0),(-1,-1),0.5,LINE),
        ('INNERGRID',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    A(t); SP(10)

def team(members):
    rows=[]
    for nom,role,ecole in members:
        rows.append([Paragraph("<b>%s</b>"%E(nom),S['cellb']),
                     Paragraph(E(role),S['cell']),
                     Paragraph(E(ecole),S['cell'])])
    t=Table(rows,colWidths=[70*mm,90*mm,90*mm])
    st=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),('GRID',(0,0),(-1,-1),0.5,LINE),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12),
        ('BACKGROUND',(0,0),(0,-1),BLUEBG)]
    t.setStyle(TableStyle(st)); A(t); SP(10)

# ===== SLIDES =====
# 2. Problème
kicker(2,"Le problème"); title("Répondre aux marchés publics : un parcours du combattant")
bullets(["<b>Trouver</b> les bons appels d'offres : éclatés sur des dizaines de plateformes — on en rate.",
         "<b>Trier</b> : un dossier de consultation fait des dizaines de pages. On répond à des marchés qu'on ne pouvait pas gagner.",
         "<b>Monter le dossier</b> : CERFA, mémoire, attestations, chiffrage. Une pièce manquante = pli écarté.",
         "<b>Les gros marchés</b> sont inaccessibles à une PME seule (CA, qualifications exigés)."])
big("Résultat : les PME passent à côté de marchés qu'elles pourraient gagner."); NEXT()

# 3. Marché
kicker(3,"Le marché"); title("Immense — et structurellement favorable aux PME mal outillées")
kpiband([("≈ 2 000 Md€","commande publique UE / an (~14 % du PIB)"),
         ("170+ Md€","France, 2023"),
         ("~60 % / ~30 %","des marchés PME : en nombre / en valeur")])
bullets(["Acheteurs partout — État, collectivités, hôpitaux, bailleurs : des besoins <b>récurrents et solvables</b>.",
         "Même cadre juridique dans toute l'UE (directives, TED, DUME) → un marché <b>réplicable</b> au-delà de la France."])
big("Les PME gagnent beaucoup de petits marchés, peu de gros — faute de CA et de qualifications. <b>C'est exactement notre créneau.</b>")
note("Sources : Commission européenne (2018) ; recensement OECP 2023. Cadre commun à l'UE : directives, TED, DUME."); NEXT()

# 4. Solution
kicker(4,"La solution"); title("Adjugo : le copilote des PME sur toute la chaîne")
chain(["Veille AO","Go / No-Go","Dossier (CERFA, DUME)","Dépôt"], "+ S'allier")
bullets(["Des <b>données 100 % officielles</b> (BOAMP, TED, DECP, SIRENE), reliées à l'avis source — vérifiables d'un clic.",
         "De la <b>détection</b> du marché jusqu'au <b>dossier prêt à déposer</b>, en passant par la décision Go/No-Go et le chiffrage.",
         "Et surtout : la possibilité de <b>répondre à plusieurs</b> (co-traitance) — ce que personne d'autre ne propose."])
big("Tout au même endroit : on remplace le bricolage entre dix outils et le temps perdu."); NEXT()

# 5. Coeur / différenciateur
kicker(5,"Notre ADN"); title("Le Consortium as a Service")
big("Plusieurs PME répondent <b>ensemble</b> à un marché — chacune apporte sa part (références, chiffrage, lot) <b>sans jamais voir les données des autres</b>. L'IA fusionne, le DC4 est généré.")
bullets(["On ouvre l'accès aux marchés <b>trop gros pour une PME seule</b> — la part en valeur qu'elles ne captent pas.",
         "<b>Cloisonnement strict</b> : chaque membre ne voit que sa part. C'est la confiance qui rend le groupement possible.",
         "<b>Effet réseau</b> : chaque PME agrandit le vivier de co-traitants — la valeur grandit avec la communauté."])
big("Un besoin réel et non couvert : monter un groupement à la main est pénible et risqué. On le rend <b>simple et traçable</b>."); NEXT()

# 6. Produit
kicker(6,"Le produit"); title("Ce qu'Adjugo fait, concrètement")
bullets(["<b>Trouver</b> — veille BOAMP (France) + TED (Europe), radar des contrats en fin d'échéance, alertes e-mail, et veille « amont » : les projets repérés dans les délibérations, des mois avant l'appel d'offres.",
         "<b>Décider</b> — analyse du dossier de consultation, score de compatibilité, clauses à risque + leviers de négociation, questions/réponses sur le marché.",
         "<b>Chiffrer</b> — estimation à partir de vos tarifs réels, tableau de prix (DPGF/BPU) exportable, frais de déplacement.",
         "<b>Préparer</b> — formulaires officiels (DC1, DC2, DC4, DUME), mémoire technique rédigé depuis votre savoir-faire, liste des pièces à fournir.",
         "<b>Répondre à plusieurs</b> — groupements cloisonnés, invitations sécurisées, fusion des contributions par l'IA, tableau de bord de préparation.",
         "<b>Piloter</b> — suivi des marchés, coffre-fort des pièces (alertes d'expiration), contacts, devis &amp; factures, multi-utilisateurs."])
note("Produit en ligne sur adjugo.pro · IA souveraine Mistral · hébergé en UE, conforme RGPD (CGV, confidentialité, DPA publiés)."); NEXT()

# 7. Pourquoi nous gagnons
kicker(7,"Avantage défendable"); title("Ce qui nous rend difficiles à copier")
pillars([("Souveraineté & conformité","IA souveraine (Mistral, FR), hébergement et données en UE — pensé pour le secteur public."),
         ("Déterminisme explicable","Le scoring Go/No-Go est un barème transparent, pas une boîte noire."),
         ("Effet réseau (CaaS)","Chaque PME — et demain chaque collectivité — enrichit le réseau : un moat qui grandit avec nous.")])
big("Notre vrai fossé, c'est le <b>réseau</b> : chaque PME et chaque collectivité qui rejoint Adjugo le rend plus utile aux autres — un avantage qui grandit avec nous."); NEXT()

# 8. Business model
kicker(8,"Modèle économique"); title("Un SaaS PME aujourd'hui, un revenu côté collectivités demain")
bullets(["<b>Face PME (revenus actuels)</b> : abonnement Découverte 0 € · Pro 129 € · Business 199 € /mois, + 5 € l'analyse au-delà du quota — jamais de blocage.",
         "<b>Face collectivités (phase 2)</b> : abonnement acheteur pour sourcer des PME locales et structurer des groupements — d'abord en pilotes, puis récurrent.",
         "<b>Canal viral intégré</b> : on invite ses co-traitants sur un marché → ils découvrent Adjugo et deviennent à leur tour utilisateurs.",
         "<b>Modèle réplicable pays par pays</b> : même moteur, on branche les sources locales et on ouvre un nouveau marché."])
big("Le réseau à deux faces crée la <b>rétention</b> et un coût d'acquisition qui baisse avec la croissance."); NEXT()

# 9. Traction
kicker(9,"Où on en est"); title("Un produit en ligne, déjà testé par de vraies PME")
kpiband([("7","PME en test"),("Co-construction","retours &amp; améliorations"),("Hackathon","EuraTech · 13 juin")])
bullets(["<b>7 PME</b> testent aujourd'hui le logiciel et nous font des <b>retours</b> qui nous font avancer chaque semaine.",
         "Présenté au <b>hackathon vibe coding d'EuraTechnologies</b> (13 juin) — c'est là qu'on a repris et élargi le projet.",
         "Socle prêt : hébergement UE, sauvegardes, e-mails, supervision, cadre légal complet (CGV, confidentialité, DPA).",
         "Prochaine étape : convertir les premiers payants, puis lancer l'expansion européenne."]); NEXT()

# 10. Vision / Europe
kicker(10,"La vision"); title("Devenir la plateforme n°1 des marchés publics en Europe")
big("Objectif sur les 6 mois du programme : être déployés sur <b>3 pays</b> — Belgique, Pays-Bas, Espagne.")
bullets(["<b>Un réseau à deux faces</b> : côté PME, répondre (seul ou en groupement) ; côté <b>collectivités</b>, sourcer des PME locales qualifiées et structurer des groupements. Plus chaque face grandit, plus l'autre a de la valeur.",
         "<b>Déjà pan-européen techniquement</b> : TED (sourcing UE) est intégré, et le <b>DUME</b> — la candidature valable dans toute l'UE — est déjà généré.",
         "Localiser = brancher les plateformes nationales (PLACSP, e-Procurement, TenderNed) + la langue. Pas de refonte."]); NEXT()

# 11. Équipe
kicker(11,"L'équipe"); title("Deux fondateurs bretons, complémentaires, amis depuis dix ans")
team([("Eliot Viegas","Tech & Produit","Centrale Nantes · basé à Nantes"),
      ("Mathys Guéna","Business & Développement","Centrale Lille & SKEMA · basé à Lille")])
bullets(["Eliot pilote le <b>produit et la tech</b> ; Mathys pilote le <b>business et le développement commercial</b>.",
         "Deux cursus ingénieur-manager (Centrale Nantes, Centrale Lille &amp; SKEMA) : on parle <b>produit ET marché</b>."])
big("Et une histoire vraie : Eliot a vu sa mère, <b>muséographe</b>, perdre un temps fou sur ses appels d'offres — et renoncer à des marchés faute de moyens. <b>Adjugo est né de cette frustration.</b>"); NEXT()

# 12. Ambition / clôture
kicker(12,"Notre ambition"); title("La plateforme n°1 des marchés publics en Europe")
big("Notre cap : un <b>réseau Adjugo</b> au service des <b>deux côtés</b> du marché — les <b>PME</b> qui répondent (seules ou en groupement) et les <b>collectivités</b> qui sourcent local. L'infrastructure européenne de la commande publique.")
bullets(["France d'abord, puis <b>3 pays</b> (Belgique, Pays-Bas, Espagne) pendant les 6 mois du programme.",
         "Prochaines briques pour passer à l'échelle : premiers <b>pilotes collectivités</b>, accès aux <b>APIs des marchés régionaux</b>, et un <b>premier commercial</b>."])
big("Faire gagner les PME, ensemble — et rapprocher PME et acheteurs publics partout en Europe."); NEXT()

# ===== RENDER =====
# Logo Adjugo (viseur/cible) reproduit en vectoriel — cohérent avec favicon.svg
def _bullseye(c, cx, cy, r, col, sw=None):
    sw = sw or r*0.22
    c.setLineWidth(sw); c.setStrokeColor(col)
    c.setStrokeAlpha(0.42); c.circle(cx, cy, r, stroke=1, fill=0)
    c.setStrokeAlpha(0.72); c.circle(cx, cy, r*0.6, stroke=1, fill=0)
    c.setStrokeAlpha(1); c.setFillColor(col); c.setFillAlpha(1)
    c.circle(cx, cy, r*0.26, stroke=0, fill=1)
    c.setStrokeAlpha(1); c.setFillAlpha(1)

def _wordmark(c, x, y, fs, col):   # « adjug » + viseur en guise de « o »
    c.setFont('Helvetica-Bold', fs); c.setFillColor(col); c.setFillAlpha(1)
    c.drawString(x, y, "adjug")
    w = c.stringWidth("adjug", 'Helvetica-Bold', fs)
    r = fs*0.27
    _bullseye(c, x + w + r*1.02, y + r, r, col, sw=r*0.30)

def _logomark(c, x, y, s, square_col, mark_col):   # icône carrée arrondie
    c.setFillColor(square_col); c.setFillAlpha(1)
    c.roundRect(x, y, s, s, s*0.23, fill=1, stroke=0)
    _bullseye(c, x+s/2, y+s/2, s*0.30, mark_col, sw=s*0.30*0.22)

def _foot(canvas, doc):
    c=canvas; c.saveState()
    s=5.6*mm; bx=16*mm; by=8.0*mm
    _logomark(c, bx, by, s, BLUE, white)
    _wordmark(c, bx+s+2.4*mm, by+s*0.18, 10.5, BLUE)
    c.setFont('Helvetica',8.5); c.setFillColor(MUTED); c.setFillAlpha(1)
    c.drawCentredString(PW/2, 10*mm, "The Square — EuraTechnologies · candidature 2026")
    c.drawRightString(PW-16*mm, 10*mm, "%02d" % doc.page)
    c.restoreState()

def _cover(canvas, doc):
    c=canvas; c.saveState()
    c.setFillColor(BLUE); c.rect(0,0,PW,PH,fill=1,stroke=0)
    s=24*mm; ix=24*mm; iy=PH-60*mm
    _logomark(c, ix, iy, s, white, BLUE)
    _wordmark(c, ix+s+9*mm, iy+s*0.30, 42, white)
    c.setFillColor(white); c.setFillAlpha(1)
    c.setFont('Helvetica-Bold',22)
    c.drawString(24*mm, PH-94*mm, "Le réseau qui fait gagner aux PME")
    c.drawString(24*mm, PH-106*mm, "des marchés publics — ensemble.")
    c.setFont('Helvetica',13)
    c.drawString(24*mm, PH-122*mm, "Le copilote des marchés publics — de la veille jusqu'au dépôt du dossier.")
    c.setFont('Helvetica',12)
    c.drawString(24*mm, PH-156*mm, "Eliot Viegas  ·  Mathys Guéna")
    c.drawString(24*mm, PH-166*mm, "Candidature The Square — EuraTechnologies  ·  juin 2026")
    c.restoreState()

frame=Frame(16*mm, 18*mm, PW-32*mm, PH-46*mm, id='m')
title_frame=frame
doc=BaseDocTemplate(OUT, pagesize=landscape(A4), leftMargin=16*mm, rightMargin=16*mm,
                    topMargin=20*mm, bottomMargin=18*mm, title="Adjugo — Pitch deck (The Square)",
                    author="Adjugo — Eliot Viegas & Mathys Guéna")
doc.addPageTemplates([PageTemplate(id='cover',frames=[frame],onPage=_cover),
                      PageTemplate(id='body',frames=[frame],onPage=_foot)])
full=[NextPageTemplate('body'), Spacer(1,1), PageBreak()] + story
doc.build(full)
print("Deck généré :", OUT)
