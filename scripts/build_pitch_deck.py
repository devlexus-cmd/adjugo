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
bullets(["Des <b>données 100 % officielles et sourcées</b> (BOAMP, TED, DECP, SIRENE) — jamais inventées.",
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
kicker(6,"Le produit"); title("Un logiciel fini et commercialisable")
bullets(["<b>Chaîne complète</b> : veille AO → analyse Go/No-Go → chiffrage → génération des CERFA (dont le DC4) → dossier complet exporté.",
         "<b>Toutes les fonctionnalités opérationnelles</b> : veille amont, co-traitance cloisonnée, base de connaissances, coffre-fort, pipeline, devis &amp; factures.",
         "<b>Moteur IA souverain : Mistral</b> (IA française) — analyse et rédaction, bridé par un garde-fou anti-hallucination : jamais une donnée factuelle inventée.",
         "Hébergé en <b>Union européenne</b>, conforme RGPD (CGV, confidentialité, DPA publiés), avec sauvegardes et supervision."])
big("Le produit est prêt à être <b>commercialisé</b>."); NEXT()

# 7. Pourquoi nous gagnons
kicker(7,"Avantage défendable"); title("Ce qui nous rend difficiles à copier")
pillars([("Confiance par construction","Anti-hallucination : donnée réelle et sourcée, ou « inconnu ». Jamais inventée."),
         ("Déterminisme explicable","Le scoring Go/No-Go est un barème transparent, pas une boîte noire."),
         ("Effet réseau (CaaS)","Chaque PME enrichit le réseau de co-traitants — un moat qui grandit avec nous.")])
big("Et un <b>moteur IA souverain — Mistral, IA française</b> — hébergé en UE, conforme RGPD, anti-hallucination par construction : un atout décisif face aux acheteurs publics."); NEXT()

# 8. Business model
kicker(8,"Modèle économique"); title("Un SaaS récurrent, doublé d'un effet réseau")
bullets(["<b>Abonnement</b> : Découverte 0 € · Pro 129 € · Business 199 € /mois · Enterprise sur devis.",
         "<b>À l'usage</b> : au-delà du quota inclus, 5 € l'analyse supplémentaire — la PME n'est jamais bloquée.",
         "<b>Canal viral intégré</b> : on invite ses co-traitants sur un marché → ils découvrent Adjugo et deviennent à leur tour utilisateurs.",
         "<b>Modèle réplicable pays par pays</b> : même moteur, on branche les sources locales et on ouvre un nouveau marché."])
big("Le réseau (co-traitance) crée la <b>rétention</b> et un coût d'acquisition qui baisse avec la croissance."); NEXT()

# 9. Traction
kicker(9,"Où on en est"); title("Des utilisateurs engagés et des prospects payeurs")
kpiband([("~10","PME utilisatrices"),("Co-construction","retours &amp; améliorations"),("1ers RDV","clients payeurs posés")])
bullets(["<b>Environ 10 PME</b> utilisent le logiciel en échange de leurs <b>retours</b> et de leur <b>aide pour les améliorations</b>.",
         "<b>Premiers rendez-vous clients payeurs</b> déjà posés.",
         "Socle prêt : hébergement UE, sauvegardes, e-mails, supervision, cadre légal complet (CGV, confidentialité, DPA).",
         "Prochaine étape : convertir les premiers payants, puis lancer l'expansion européenne."]); NEXT()

# 10. Vision / Europe
kicker(10,"La vision"); title("Devenir la plateforme n°1 des marchés publics en Europe")
big("Objectif sur les 6 mois du programme : être déployés sur <b>3 pays</b> — Belgique, Pays-Bas, Espagne.")
bullets(["<b>Un réseau à deux faces</b> : côté PME, répondre (seul ou en groupement) ; côté <b>collectivités</b>, sourcer des PME locales qualifiées et structurer des groupements. Plus chaque face grandit, plus l'autre a de la valeur.",
         "<b>Déjà pan-européen techniquement</b> : TED (sourcing UE) est intégré, et le <b>DUME</b> — la candidature valable dans toute l'UE — est déjà généré.",
         "Localiser = brancher les plateformes nationales (PLACSP, e-Procurement, TenderNed) + la langue. Pas de refonte."]); NEXT()

# 11. Équipe
kicker(11,"L'équipe"); title("Deux fondateurs bretons, complémentaires, amis depuis le collège")
team([("Eliot Viegas","Tech & Produit","Centrale Nantes / Audencia"),
      ("Mathys Guéna","Business & Développement","ITEEM — Centrale Lille / SKEMA · basé à Lille")])
bullets(["Eliot pilote le <b>produit et la tech</b> ; Mathys pilote le <b>business et le développement commercial</b>.",
         "Deux cursus ingénieur-manager (Centrale Nantes/Audencia, Centrale Lille/SKEMA) : on parle <b>produit ET marché</b>."])
big("Confiance longue durée, double compétence ingénieur × business, et un fondateur <b>déjà ancré à Lille</b>."); NEXT()

# 12. Ambition / clôture
kicker(12,"Notre ambition"); title("La plateforme n°1 des marchés publics en Europe")
big("Notre cap : un <b>réseau Adjugo</b> au service des <b>deux côtés</b> du marché — les <b>PME</b> qui répondent (seules ou en groupement) et les <b>collectivités</b> qui sourcent local. L'infrastructure européenne de la commande publique.")
bullets(["France d'abord, puis <b>3 pays</b> (Belgique, Pays-Bas, Espagne) pendant les 6 mois du programme.",
         "Prochaines briques pour passer à l'échelle : premiers <b>pilotes collectivités</b>, accès aux <b>APIs des marchés régionaux</b>, et un <b>premier commercial</b>."])
big("Faire gagner les PME, ensemble — et rapprocher PME et acheteurs publics partout en Europe."); NEXT()

# ===== RENDER =====
def _foot(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica-Bold',11); canvas.setFillColor(BLUE)
    canvas.drawString(16*mm, 10*mm, "adjugo")
    canvas.setFont('Helvetica',8.5); canvas.setFillColor(MUTED)
    canvas.drawCentredString(PW/2, 10*mm, "The Square — EuraTechnologies · candidature 2026")
    canvas.drawRightString(PW-16*mm, 10*mm, "%02d" % doc.page)
    canvas.restoreState()

def _cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BLUE); canvas.rect(0,0,PW,PH,fill=1,stroke=0)
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold',64); canvas.drawString(24*mm, PH-78*mm, "adjugo")
    canvas.setFont('Helvetica-Bold',22)
    canvas.drawString(24*mm, PH-100*mm, "Le réseau qui fait gagner aux PME")
    canvas.drawString(24*mm, PH-112*mm, "des marchés publics — ensemble.")
    canvas.setFont('Helvetica-Oblique',14)
    canvas.drawString(24*mm, PH-128*mm, "Win public tenders. Together.")
    canvas.setFont('Helvetica',12)
    canvas.drawString(24*mm, PH-160*mm, "Eliot Viegas  ·  Mathys Guéna")
    canvas.drawString(24*mm, PH-170*mm, "Candidature The Square — EuraTechnologies  ·  juin 2026")
    canvas.restoreState()

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
