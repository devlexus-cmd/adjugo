# -*- coding: utf-8 -*-
"""
Dossier commercial interne d'Adjugo (PDF) — destiné au directeur commercial.
Rendu reportlab (platypus). Numérotation de sections automatique + sommaire auto.
Sortie : /Users/eliot/Downloads/Adjugo_Dossier_Commercial.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, PageBreak)
from reportlab.platypus.doctemplate import NextPageTemplate
from reportlab.lib.styles import ParagraphStyle
import html as _html

BLUE = HexColor("#1B4FFF"); INK = HexColor("#0A1730"); INK2 = HexColor("#3D4A63")
MUTED = HexColor("#5A6573"); LINE = HexColor("#E6E9F0"); SOFT = HexColor("#F4F6FB")
BLUEBG = HexColor("#EDF1FF"); WARN = HexColor("#FBF6E9"); WARNBD = HexColor("#E6C870")
GREENBG = HexColor("#E7F5EE"); GREENBD = HexColor("#1D9E75")
OUT = "/Users/eliot/Downloads/Adjugo_Dossier_Commercial.pdf"

def E(s): return _html.escape(str(s), quote=False).replace("\n", "<br/>")

S = {}
S['h1'] = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=20, textColor=BLUE, spaceBefore=2, spaceAfter=10, leading=24)
S['h2'] = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=14, textColor=INK, spaceBefore=16, spaceAfter=6, leading=18)
S['h3'] = ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=11.5, textColor=INK, spaceBefore=11, spaceAfter=3, leading=15)
S['p'] = ParagraphStyle('p', fontName='Helvetica', fontSize=10, textColor=INK2, spaceAfter=7, leading=15.5, alignment=TA_LEFT)
S['bul'] = ParagraphStyle('bul', parent=S['p'], leftIndent=14, bulletIndent=2, spaceAfter=4)
S['lead'] = ParagraphStyle('lead', fontName='Helvetica', fontSize=11.5, textColor=INK, spaceAfter=9, leading=17)
S['small'] = ParagraphStyle('small', fontName='Helvetica', fontSize=8.5, textColor=MUTED, leading=12, spaceAfter=4)
S['cell'] = ParagraphStyle('cell', fontName='Helvetica', fontSize=9, textColor=INK2, leading=13)
S['cellh'] = ParagraphStyle('cellh', fontName='Helvetica-Bold', fontSize=9, textColor=white, leading=13)
S['quote'] = ParagraphStyle('quote', fontName='Helvetica-Oblique', fontSize=12, textColor=INK, leading=18, leftIndent=10, spaceBefore=4, spaceAfter=4)
S['callh'] = ParagraphStyle('callh', fontName='Helvetica-Bold', fontSize=10, textColor=INK, spaceAfter=3, leading=14)
S['callp'] = ParagraphStyle('callp', fontName='Helvetica', fontSize=9.5, textColor=INK2, leading=14)
S['toc'] = ParagraphStyle('toc', fontName='Helvetica', fontSize=10.5, textColor=INK2, leading=19)
S['tocb'] = ParagraphStyle('tocb', fontName='Helvetica-Bold', fontSize=10.5, textColor=INK, leading=19)
S['kpival'] = ParagraphStyle('kpival', fontName='Helvetica-Bold', fontSize=14, textColor=BLUE, alignment=TA_CENTER, leading=16)
S['kpilab'] = ParagraphStyle('kpilab', fontName='Helvetica', fontSize=7.5, textColor=MUTED, alignment=TA_CENTER, leading=10)

def para(txt, st='p'): return Paragraph(txt, S[st])

def callout(title, body, kind='blue'):
    bg = {'blue':BLUEBG,'warn':WARN,'green':GREENBG,'soft':SOFT}[kind]
    bd = {'blue':BLUE,'warn':WARNBD,'green':GREENBD,'soft':LINE}[kind]
    flow = []
    if title: flow.append(Paragraph(title, S['callh']))
    body = body if isinstance(body,(list,tuple)) else [body]
    for b in body: flow.append(Paragraph(b if '<' in b else E(b), S['callp']))
    t = Table([[flow]], colWidths=[165*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),bg),('LINEBEFORE',(0,0),(0,-1),2.2,bd),
        ('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    return t

def table(headers, rows, widths):
    data = [[Paragraph(E(h), S['cellh']) for h in headers]]
    for r in rows:
        data.append([Paragraph(c if '<' in str(c) else E(c), S['cell']) for c in r])
    t = Table(data, colWidths=[w*mm for w in widths], repeatRows=1)
    st = [('BACKGROUND',(0,0),(-1,0),BLUE),('GRID',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
          ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
          ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]
    for i in range(1,len(data)):
        if i%2==0: st.append(('BACKGROUND',(0,i),(-1,i),SOFT))
    t.setStyle(TableStyle(st)); return t

def kpis(items):
    row = []
    for lab,val in items:
        inner = Table([[Paragraph(E(val),S['kpival'])],[Paragraph(E(lab),S['kpilab'])]], colWidths=[38*mm])
        inner.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
            ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2)]))
        row.append(inner)
    t = Table([row], colWidths=[(165/len(row))*mm]*len(row))
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),SOFT),('BOX',(0,0),(-1,-1),0.5,LINE),
        ('INNERGRID',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    return t

story = []; A = story.append
toc_entries = []; _sec = [0]
def SECTION(title):
    _sec[0]+=1; toc_entries.append((str(_sec[0]), title))
    A(para("%d. %s" % (_sec[0], E(title)), 'h1'))
def H2(t): A(para(t,'h2'))
def H3(t): A(para(t,'h3'))
def P(t): A(para(t,'p'))
def LEAD(t): A(para(t,'lead'))
def SMALL(t): A(para(t,'small'))
def Q(t): A(Paragraph(E(t), S['quote']))
def BR(): A(PageBreak())
def SP(h=6): A(Spacer(1,h))
def BUL(items):
    for it in items: A(Paragraph(it if '<' in it else E(it), S['bul'], bulletText='•'))
def CALL(t,b,k='blue'): A(callout(t,b,k)); SP(8)
def TBL(h,r,w): A(table(h,r,w)); SP(8)
def KPI(items): A(kpis(items)); SP(8)

# ===================== 1. À LIRE EN PREMIER =====================
SECTION("À lire en premier")
LEAD("Ce document est ton dossier de référence pour vendre Adjugo. Ce n'est pas une plaquette : c'est ce "
     "qui doit te permettre de t'<b>approprier</b> le produit, le marché, la technique et la vision — au "
     "point d'en parler comme si tu l'avais construit.")
P("Adjugo aide les <b>PME</b> à répondre aux <b>marchés publics</b> : les trouver, décider lesquels valent "
  "le coup, préparer le dossier, et — c'est notre cœur — s'<b>allier à d'autres PME</b> pour gagner des "
  "marchés trop gros pour une seule entreprise. Le tout sur des <b>données réelles et vérifiables</b>, "
  "jamais inventées.")
CALL("Comment utiliser ce dossier",
     ["Lis-le en entier une fois, puis reviens aux sections « boîte à outils » (pitch, objections, démo) "
      "avant chaque rendez-vous.",
      "Encadrés <b>bleus</b> = arguments clés. <b>Jaunes</b> = à ne pas survendre. <b>Verts</b> = ce qui est "
      "déjà fait et solide.",
      "Règle d'or, la même que celle du produit : <b>ne jamais avancer un chiffre qu'on ne peut pas sourcer</b>. "
      "Les chiffres de ce dossier le sont (voir la section « Sources & méthode »)."], 'blue')
BR()

# ===================== 2. LE PROBLÈME =====================
SECTION("Le problème qu'on résout")
P("Chaque année, l'État, les collectivités, les hôpitaux, les bailleurs publics achètent des travaux et "
  "des services via des <b>marchés publics</b>. Pour une PME, c'est un gisement de chiffre d'affaires "
  "récurrent et solvable. Mais y répondre est un parcours du combattant.")
H3("Ce que vit une PME aujourd'hui")
BUL([
    "<b>Trouver les bons appels d'offres</b> : éclatés sur de multiples plateformes (BOAMP, JOUE/TED, "
    "profils d'acheteurs régionaux). On en rate, ou on perd des heures à éplucher.",
    "<b>Savoir si ça vaut le coup</b> : un DCE fait des dizaines de pages. Beaucoup de PME répondent à des "
    "marchés qu'elles ne pouvaient pas gagner — du temps perdu.",
    "<b>Monter le dossier</b> : formulaires CERFA (DC1, DC2, DC4…), mémoire technique, attestations, "
    "chiffrage. Une pièce manquante et le pli est écarté.",
    "<b>Les marchés trop gros</b> : seules, beaucoup de PME ne cochent pas les critères (CA exigé, "
    "qualifications). La solution — le <b>groupement</b> — est mal connue et compliquée à organiser.",
])
CALL("Le coût caché", "Le vrai problème n'est pas « répondre », c'est <b>répondre aux bons marchés, vite, et "
     "complet</b>. Le temps passé sur un dossier perdant est volé à la production. Adjugo transforme ce "
     "temps en décisions et en dossiers prêts.", 'blue')
BR()

# ===================== 3. LE MARCHÉ EN CHIFFRES =====================
SECTION("Le marché en chiffres (sources officielles)")
P("Ces chiffres sont issus du recensement de l'<b>Observatoire économique de la commande publique (OECP)</b> "
  "et des avis officiels sur les seuils. Ils sont datés et sourcés (voir la dernière section). Le marché "
  "est immense, récurrent — et structurellement favorable à notre positionnement.")
KPI([("Commande publique 2023", "170+ Md€"), ("Contrats recensés (2023)", "243 731"),
     ("PME, en nombre", "~60 %"), ("PME, en valeur", "~30 %")])
H3("Ce que disent ces chiffres")
BUL([
    "<b>Un marché énorme et en croissance</b> : plus de <b>170 milliards d'euros</b> et <b>243 731 contrats</b> "
    "recensés en 2023 (en hausse en nombre comme en valeur sur 2022).",
    "<b>Les collectivités territoriales</b> sont les plus gros donneurs d'ordre (près de 195 000 contrats en "
    "2023) — un terrain de proximité idéal pour des PME régionales.",
    "<b>Répartition par nature</b> (2023, en nombre) : environ 40 % de services, 32 % de fournitures, "
    "28 % de travaux. Adjugo couvre les trois, avec une force naturelle sur les travaux.",
    "<b>Le déséquilibre clé</b> : les PME remportent environ <b>60 % des marchés en nombre</b>, mais seulement "
    "de l'ordre de <b>30 % en valeur</b>. Autrement dit, elles gagnent beaucoup de petits marchés et peu de "
    "gros — parce que les gros exigent du CA et des qualifications qu'elles n'ont pas seules.",
])
CALL("Pourquoi ce déséquilibre EST notre marché",
     "C'est exactement le créneau d'Adjugo. Mieux cibler (pour ne pas perdre de temps) <b>et</b> se "
     "regrouper (pour accéder aux marchés en valeur) : c'est notre proposition. Le « ~30 % en valeur » des "
     "PME est précisément ce que le <b>Consortium as a Service</b> veut faire grandir.", 'blue')
H3("Les seuils en vigueur (depuis le 1er janvier 2026)")
P("Comprendre les seuils aide à parler le langage de l'acheteur et à expliquer où se trouvent les marchés "
  "selon leur taille :")
TBL(["Type de marché", "Dispense de publicité possible", "Procédure formalisée à partir de"],
    [["Travaux", "moins de 100 000 € HT", "5 404 000 € HT (+ publication au JOUE)"],
     ["Fournitures & services", "moins de 60 000 € HT (depuis le 1er avril 2026)",
      "216 000 € HT (collectivités) — 143 000 € HT (État)"]],
    [38, 62, 65])
SMALL("Seuils relevés par l'avis publié au JORF du 13 janvier 2026 (annexe n° 2 du Code de la commande "
      "publique). Les seuils européens sont révisés tous les deux ans.")
BR()

# ===================== 4. CE QU'EST ADJUGO =====================
SECTION("Ce qu'est Adjugo")
LEAD("Adjugo est un logiciel en ligne (SaaS) qui accompagne une PME sur toute la chaîne de réponse aux "
     "marchés publics — de la veille au dépôt — et qui lui permet de <b>répondre à plusieurs</b> quand le "
     "marché l'exige.")
H3("Le pitch en une phrase")
Q("« Adjugo, c'est le copilote des PME pour gagner des marchés publics — seules ou en groupement — sur des "
  "données 100 % réelles. »")
H3("Le cœur : le « Consortium as a Service »")
P("La plupart des outils s'arrêtent à la veille ou à la génération de documents. Notre <b>ADN</b>, ce qui "
  "nous rend différents, c'est la <b>co-traitance cloisonnée</b> : permettre à plusieurs PME de préparer "
  "<b>ensemble</b> une réponse, chacune apportant sa part (références, chiffrage, lot), <b>sans jamais voir "
  "les données des autres</b>. Le mandataire assemble, l'IA fusionne, et le DC4 est généré.")
CALL("Pourquoi c'est puissant à vendre",
     ["<b>Effet réseau</b> : plus il y a de PME sur Adjugo, plus elles peuvent se trouver et s'allier. La "
      "valeur grandit avec la communauté.",
      "<b>Besoin réel et non couvert</b> : monter un groupement à la main est pénible et risqué. On le rend "
      "simple et traçable.",
      "<b>Accès à des marchés inaccessibles en solo</b> : on ne vend pas « un outil de plus », on vend "
      "l'accès à des marchés plus gros — la part en valeur que les PME ne captent pas aujourd'hui."], 'blue')
BR()

# ===================== 5. FONDATIONS TECHNIQUES =====================
SECTION("Nos fondations techniques (le socle de confiance)")
P("Tu n'as pas besoin d'être ingénieur pour vendre Adjugo, mais tu dois pouvoir expliquer <b>sur quoi on "
  "est basé</b> — c'est exactement ce qui nous différencie d'un « ChatGPT des appels d'offres ».")
H2("5.1 Des données réelles, officielles et sourcées")
P("Tout ce qu'Adjugo affiche vient de <b>sources publiques officielles</b>, avec la source, la date et un "
  "lien vers l'avis d'origine. On ne « génère » pas d'appels d'offres : on va les chercher là où ils sont "
  "publiés.")
TBL(["Source", "Ce que c'est", "Ce qu'on en tire"],
    [["BOAMP", "Bulletin officiel des annonces des marchés publics (France)", "Les AO publiés, national et local"],
     ["TED / JOUE", "Journal officiel européen (Tenders Electronic Daily)", "Les marchés au-dessus des seuils UE"],
     ["DECP", "Données essentielles de la commande publique (État, Licence Ouverte)", "Les marchés attribués → radar des renouvellements"],
     ["SIRENE / Recherche d'entreprises", "Base officielle des entreprises (INSEE)", "Vérifier un co-traitant : SIRET, NAF, dirigeants"],
     ["BODACC", "Annonces civiles et commerciales", "Détecter une procédure collective (red flag)"],
     ["Délibérations open-data", "Comptes-rendus des conseils municipaux/interco", "La veille amont : repérer un projet en amont de l'AO"]],
    [34, 74, 57])
CALL("L'argument", "« Adjugo ne vous demande pas de lui faire confiance : chaque donnée est <b>tracée "
     "jusqu'à sa source officielle</b>. »", 'blue')
H2("5.2 La règle anti-hallucination")
P("Les IA classiques inventent quand elles ne savent pas. Pour des marchés publics, inacceptable : une "
  "fausse date limite et la PME perd le marché. Adjugo applique une règle stricte : <b>une donnée est "
  "réelle et sourcée, ou marquée « inconnu »</b>. Jamais comblée, jamais inventée.")
CALL("Retourner l'objection « IA »", "Face à un prospect méfiant de l'IA : « justement, Adjugo est construit "
     "pour <b>ne pas</b> halluciner — il préfère dire « je ne sais pas » plutôt qu'inventer. »", 'blue')
H2("5.3 Un scoring déterministe et explicable")
P("Le score Go/No-Go n'est pas une boîte noire : c'est un <b>barème explicite</b> (métier, zone, budget, "
  "qualifications, capacité financière…). Chaque point est justifié, et le même dossier donne toujours le "
  "même score.")
BUL(["<b>Transparent</b> : la PME voit pourquoi c'est 82/100 ou 34/100, critère par critère.",
     "<b>Reproductible</b> : pas de hasard, pas de dérive d'un jour à l'autre.",
     "<b>Honnête</b> : tant que la PME n'a pas renseigné ses critères, pas de score trompeur."])
H2("5.4 Souveraineté, hébergement et sécurité")
BUL(["<b>Données en Union européenne</b> : base de données et fichiers (avec sauvegardes) hébergés en UE.",
     "<b>Cloisonnement strict</b> (multi-tenant) : les données d'une PME ne sont jamais visibles par une "
     "autre — c'est ce qui rend la co-traitance cloisonnée possible.",
     "<b>Sécurité</b> : HTTPS/TLS, mots de passe hachés, sauvegardes quotidiennes chiffrées, supervision, "
     "journal d'accès traçable.",
     "<b>Cadre juridique complet</b> : mentions légales, CGV, confidentialité et <b>DPA (art. 28 RGPD)</b> publiés.",
     "<b>Souveraineté du moteur IA</b> : architecture découplée du fournisseur. Aujourd'hui Anthropic "
     "(Claude) ; demain un moteur souverain français (Mistral) peut être branché sans réécrire les agents."])
CALL("Déjà en place", "Hébergement UE, sauvegardes automatiques, e-mails, supervision, pages légales + DPA : "
     "<b>tout est en production et vérifié</b>. Livré, pas promis.", 'green')
H2("5.5 L'architecture, en clair")
P("Pour répondre sans bluffer : Adjugo est une application web sécurisée. Un <b>back-end</b> (interroge les "
  "sources officielles, applique les barèmes, génère les documents) et un <b>front-end</b> (l'interface). "
  "Documents et base de données stockés <b>en UE</b>. L'IA n'intervient que pour la rédaction et l'analyse — "
  "jamais pour inventer une donnée factuelle.")
CALL("Ce que tu peux dire sans risque", "« C'est une application web sécurisée, hébergée en Europe, basée "
     "sur les bases officielles de la commande publique, qui n'utilise l'IA que pour vous faire gagner du "
     "temps de rédaction — pas pour inventer des faits. » Au-delà, propose un échange avec l'équipe produit "
     "plutôt que d'improviser.", 'warn')
BR()

# ===================== 6. FONCTIONNALITÉS =====================
SECTION("Les fonctionnalités et leur valeur")
P("Chaque brique, regroupée par moment du parcours, avec <b>ce qu'elle fait</b> et son <b>argument de vente</b>.")
H2("Trouver les bons marchés")
H3("Veille AO (sourcing)")
P("Cherche les AO réels sur BOAMP et TED selon les critères de la PME. Chaque résultat affiche sa source et "
  "un lien vers l'avis officiel. <b>Valeur :</b> on arrête de rater des marchés et de perdre des heures.")
H3("Veille amont (signaux d'investissement)")
P("Détecte dans les délibérations des collectivités les <b>projets en préparation</b>, avant la publication "
  "de l'AO, avec citation de la source. <b>Valeur :</b> prendre une longueur d'avance (rencontrer "
  "l'acheteur, se positionner) pendant que les concurrents attendent.")
H3("Radar des renouvellements")
P("À partir des marchés attribués (DECP), calcule quand un contrat arrive à échéance et sera republié. "
  "<b>Valeur :</b> savoir des mois à l'avance quels marchés se rouvrent. Affiche la raison sociale de "
  "l'acheteur, pas un numéro.")
H2("Décider vite et juste")
H3("Analyse du DCE + score Go/No-Go")
P("Extrait l'essentiel d'un DCE (objet, montant, délais, critères, pièces, clauses à risque) et calcule un "
  "score déterministe. <b>Valeur :</b> en minutes, la PME sait si elle doit y aller, et pourquoi.")
CALL("À ne pas survendre", "Adjugo <b>aide à décider</b> : il ne décide pas à la place de la PME et ne "
     "garantit pas de gagner. Présente le score comme une <b>recommandation</b> qui éclaire l'expert.", 'warn')
H2("Préparer un dossier complet")
H3("Chiffrage, DPGF/BPU")
P("Estimation à partir des tâches et des prix de journée, et décomposition de prix. <b>Valeur :</b> un "
  "chiffrage cohérent et présentable, sans repartir de zéro.")
H3("Génération des CERFA et du mémoire technique")
P("Produit DC1, DC2, DC4, ATTRI1, DUME pré-remplis, et une base de mémoire technique. Documents régénérés à "
  "la volée, à valider et signer. <b>Valeur :</b> fini les formulaires à la main, moins de risque d'oubli.")
H3("Coffre-fort, checklist de pré-dépôt, alertes")
P("Range les pièces, compare avec ce que le marché exige, alerte sur les attestations qui expirent. "
  "<b>Valeur :</b> un dossier complet, à l'heure, sans pièce périmée.")
H3("Export du dossier complet")
P("Assemble en un clic tout le dossier (CERFA, mémoire, pièces) en archive ZIP. <b>Valeur :</b> du "
  "« préparé » au « déposable » en une action.")
H2("S'allier (le cœur d'Adjugo)")
H3("Co-traitants vérifiés")
P("Identifie de vrais partenaires (métier, zone) via les bases officielles, et signale les <b>red flags</b> "
  "(procédure collective via BODACC). <b>Valeur :</b> trouver le bon allié, éviter une entreprise en difficulté.")
H3("Consortium / co-traitance cloisonnée + DC4")
P("Le mandataire invite des partenaires via un lien sécurisé. Chacun apporte sa part <b>sans voir celle des "
  "autres</b>. L'IA fusionne, le <b>DC4</b> est généré. <b>Valeur :</b> répondre à des marchés trop gros pour "
  "une seule PME, proprement. Notre meilleur argument.")
H3("Espace de co-construction (mémoire fusionné)")
P("Un espace partagé pour répartir les lots et bâtir un mémoire commun. <b>Valeur :</b> organiser le "
  "groupement comme une équipe, pas comme un échange d'e-mails.")
H2("Piloter et professionnaliser")
H3("Pipeline AO et analytics gagné/perdu")
P("Suit les marchés par statut et calcule le taux de réussite (où l'on gagne / où l'on perd). "
  "<b>Valeur :</b> piloter sa prospection publique comme un commercial pilote son pipe.")
H3("Base de connaissances (mémoire d'entreprise indexée)")
P("La PME dépose ses mémoires, fiches RSE, méthodologies ; Adjugo les rend interrogeables et <b>cite la "
  "source exacte</b> (anti-hallucination jusque dans le RAG). <b>Valeur :</b> réutiliser son savoir-faire.")
H3("Devis & factures, contacts (CRM)")
P("Devis/factures (mention franchise de TVA) et carnet de contacts. <b>Valeur :</b> l'essentiel de la "
  "gestion au même endroit que la réponse aux marchés.")
H2("Le cadre (confiance & conformité)")
H3("RGPD by design")
P("Export et suppression de compte en autonomie, journal d'accès traçable, DPA publié. <b>Valeur :</b> un "
  "argument de sérieux face à des PME qui confient des documents sensibles.")
BR()

# ===================== 7. EXEMPLE CONCRET =====================
SECTION("Un exemple concret, de bout en bout")
P("Pour t'approprier la chaîne complète, déroule ce cas réaliste (c'est exactement ce que montre le compte "
  "de démonstration). <b>Bâtiment de l'Ouest</b>, PME de couverture/étanchéité en Bretagne (14 salariés).")
BUL([
    "<b>Veille AO</b> : Adjugo remonte une « réfection de toiture d'un groupe scolaire » à 480 k€ à Quimper. "
    "Source BOAMP, lien vers l'avis.",
    "<b>Décision</b> : score Go <b>87/100</b> — métier, zone et qualifications alignés. Adjugo signale les "
    "clauses à risque (retenue de garantie, pénalités) et les leviers de négociation.",
    "<b>Préparation</b> : chiffrage + DPGF, génération des CERFA (DC1, DC2, ATTRI1), checklist de pré-dépôt "
    "qui passe au vert, export du dossier.",
    "<b>Le cas du gros marché</b> : un second marché, la réhabilitation d'un gymnase à Lorient (1,25 M€), "
    "exige une qualification <b>désamiantage SS3</b> que la PME n'a pas — et un CA supérieur au sien. "
    "Seule, c'est No-Go.",
    "<b>Le réflexe Adjugo</b> : on identifie un co-traitant <b>désamianteur vérifié</b> (SIRET, qualifs, pas "
    "de red flag), on l'invite sur le marché. Il apporte sa part (références SS3, chiffrage de son lot) sans "
    "voir le reste du dossier. L'IA fusionne, le <b>DC4</b> est généré.",
    "<b>Résultat</b> : un marché à 1,25 M€ devient accessible — du chiffre d'affaires que la PME n'aurait "
    "jamais touché seule.",
])
CALL("L'histoire à raconter en RDV", "Cette séquence — « petit marché gagné seul, gros marché gagné en "
     "groupement » — résume Adjugo en deux minutes. C'est elle qu'il faut dérouler en démo.", 'blue')
BR()

# ===================== 8. POSITIONNEMENT DÉFENDABLE =====================
SECTION("Ce qui nous rend défendable")
P("Le marché des outils autour des appels d'offres existe. Voici comment se situer honnêtement, sans dénigrer.")
TBL(["Catégorie d'acteurs", "Ce qu'ils font", "Ce qu'Adjugo apporte en plus"],
    [["Plateformes de veille / alerte AO", "Envoient des alertes d'appels d'offres",
      "On ne s'arrête pas à l'alerte : analyse, décision, dossier, et surtout le groupement"],
     ["Outils IA génériques", "Rédigent à partir d'un prompt", "Données réelles sourcées + anti-hallucination + scoring déterministe"],
     ["Cabinets / AMO marchés publics", "Accompagnent au cas par cas (humain)", "Industrialise et démocratise à coût SaaS, en gardant l'humain aux commandes"],
     ["Faire seul (Excel, à la main)", "Gratuit mais chronophage et risqué", "Gain de temps, complétude du dossier, accès aux marchés en groupement"]],
    [40, 55, 70])
H3("Nos trois avantages défendables (moats)")
BUL([
    "<b>La confiance par construction</b> : anti-hallucination + traçabilité des sources. Difficile à imiter "
    "pour qui a bâti son produit sur une IA générative non contrainte.",
    "<b>Le déterminisme explicable</b> : un barème transparent, pas une boîte noire — rassurant pour un "
    "acheteur public comme pour la PME.",
    "<b>L'effet réseau du CaaS</b> : chaque PME supplémentaire enrichit le vivier de co-traitants. Plus on "
    "grandit, plus c'est dur à rattraper. C'est notre avantage de long terme."])
BR()

# ===================== 9. VISION =====================
SECTION("La vision : le réseau Adjugo")
LEAD("Aujourd'hui, Adjugo est un excellent copilote individuel. Demain, c'est un <b>réseau</b> où les PME "
     "se trouvent et gagnent ensemble.")
BUL([
    "<b>L'effet réseau du CaaS</b> : chaque PME agrandit le vivier de co-traitants. La valeur d'Adjugo croît "
    "avec la communauté — c'est un avantage défendable.",
    "<b>Couverture des sources élargie</b> : au-delà de BOAMP/TED/DECP, intégrer plus de profils d'acheteurs "
    "et de plateformes régionales pour ne rien laisser passer.",
    "<b>Plus d'automatisation utile</b> : pré-remplissage toujours plus complet, assistance au mémoire, suivi "
    "proactif des échéances.",
    "<b>Souveraineté</b> : proposer un moteur IA français/européen aux acteurs sensibles à ce sujet."])
Q("« Seules, les PME se font écarter des gros marchés. Ensemble, via Adjugo, elles les gagnent. »")
CALL("En pitch", "La vision se vend comme une <b>trajectoire</b> : « vous n'achetez pas un outil, vous "
     "rejoignez un réseau qui va vous ouvrir des marchés inaccessibles seul. » Les premiers entrants en "
     "bénéficient le plus.", 'blue')
BR()

# ===================== 10. ÉTAT D'ESPRIT =====================
SECTION("Notre état d'esprit aujourd'hui")
P("Tu portes aussi une culture, à incarner en rendez-vous — elle nous distingue autant que les fonctionnalités.")
H3("Exigence de vérité")
P("On préfère dire « inconnu » plutôt qu'inventer. Pas de bullshit, pas de chiffre sorti du chapeau — ni "
  "dans le produit, ni dans la vente. Notre marque de fabrique.")
H3("Déterminisme et transparence")
P("On explique nos scores, on cite nos sources. La PME doit toujours comprendre <b>pourquoi</b>. L'IA est un "
  "assistant, jamais un oracle.")
H3("Proximité PME et terrain")
P("Pensé par et pour des gens qui connaissent la réalité d'une PME (BTP, services) en région. On construit "
  "avec les premiers utilisateurs, on itère vite, on écoute.")
H3("Sobriété et indépendance")
P("Structure légère, choix techniques sobres, coûts maîtrisés. On avance par la valeur livrée, pas par "
  "l'esbroufe. On reste maîtres de notre techno (moteur IA interchangeable).")
CALL("À transmettre en clientèle", "« On ne vous promet pas la lune. On vous donne des données vraies, des "
     "outils qui marchent, et on construit avec vous. » Cette honnêteté est un <b>argument</b>.", 'blue')
BR()

# ===================== 11. CE QU'ON FAIT AUJOURD'HUI =====================
SECTION("Ce qu'on fait aujourd'hui pour y arriver")
H3("Le produit est prêt pour les premières PME")
P("L'infrastructure de production est en place et vérifiée : hébergement UE, base de données, sauvegardes "
  "quotidiennes, e-mails transactionnels, supervision des erreurs, mode démo sécurisé. Le cadre juridique "
  "(mentions, CGV, confidentialité, DPA) est publié.")
CALL("Déjà livré et vérifié",
     ["Toute la chaîne fonctionne de bout en bout : veille → Go/No-Go → chiffrage → CERFA (dont le DC4 du "
      "consortium) → dossier exporté.",
      "Un <b>compte de démonstration complet</b> existe : une PME fictive réaliste (marchés gagnés/perdus, "
      "consortium, documents) pour montrer la valeur sans inscription."], 'green')
H3("Le modèle économique")
TBL(["Formule", "Prix / mois", "Pour qui", "Inclus"],
    [["Découverte", "0 €", "Découvrir, tester", "Veille + 2 analyses d'AO / mois"],
     ["Pro", "129 €", "PME qui répond régulièrement", "Veille + 30 analyses + génération de dossier"],
     ["Business", "199 €", "PME active, groupements", "Veille + 100 analyses + fonctions de groupement"],
     ["Enterprise", "Sur devis", "Grandes structures, volumes", "Sur-mesure, fonctionnalités dédiées"]],
    [28, 24, 52, 61])
P("Au-delà du quota inclus, chaque analyse supplémentaire = <b>5 €</b> (franchise de TVA — aucune TVA "
  "facturée). Abonnements sans engagement, résiliables à tout moment.")
H3("La phase actuelle : recrutement des PME beta")
P("Le logiciel est fini pour démarrer. La priorité : <b>recruter les premières PME beta</b> par contact "
  "direct, recueillir leurs retours et affiner. C'est ici que tu entres en jeu.")
BR()

# ===================== 12. PROCESSUS DE VENTE =====================
SECTION("Le processus de vente, étape par étape")
P("Une trame simple pour transformer un contact en client, puis en ambassadeur.")
TBL(["Étape", "Objectif", "Le bon geste"],
    [["1. Cibler", "Choisir des PME pertinentes", "BTP/services en région qui répondent déjà un peu (voir cibles, section suivante)"],
     ["2. Accrocher", "Créer l'intérêt", "Partir du problème (« combien de temps sur des dossiers perdants ? »), pas des fonctionnalités"],
     ["3. Démontrer", "Provoquer le « waouh »", "La démo : un AO réel, puis le groupement + DC4 généré en direct"],
     ["4. Essayer", "Lever le risque", "Offre Découverte gratuite — on commence sans engagement"],
     ["5. Onboarder", "Activer", "Profil entreprise + critères + 1re analyse réelle ensemble dans les premiers jours"],
     ["6. Convertir", "Passer au payant", "Quand un marché pertinent est identifié : Pro/Business pour générer le dossier"],
     ["7. Étendre", "Faire grandir le réseau", "Inviter ses co-traitants habituels → ils deviennent à leur tour utilisateurs"]],
    [26, 47, 92])
CALL("Ce qui fait signer", "Un <b>marché concret et pertinent</b> identifié pendant le rendez-vous, plus la "
     "promesse du <b>groupement</b>. Vendre une capacité abstraite convainc moins que « regardez, CE "
     "marché-là, vous pourriez le gagner avec Adjugo ».", 'blue')
BR()

# ===================== 13. BOÎTE À OUTILS =====================
SECTION("Boîte à outils du commercial")
H2("13.1 Le pitch")
H3("En 30 secondes")
Q("« Vous êtes une PME et les marchés publics vous prennent un temps fou pour un résultat incertain ? "
  "Adjugo trouve les bons appels d'offres, vous dit en minutes lesquels valent le coup, prépare votre "
  "dossier, et — c'est unique — vous permet de vous allier à d'autres PME pour gagner des marchés trop gros "
  "pour vous seul. Le tout sur des données 100 % officielles, jamais inventées. »")
H3("En 2 minutes (structure)")
BUL(["<b>Le problème</b> : trouver, trier, monter le dossier, et les gros marchés inaccessibles en solo.",
     "<b>La promesse</b> : un copilote sur toute la chaîne + la co-traitance simplifiée.",
     "<b>La preuve</b> : données officielles sourcées, scoring transparent, anti-hallucination, hébergé en UE.",
     "<b>Le « waouh »</b> : la démo — monter un groupement et générer le DC4 en direct.",
     "<b>L'offre</b> : on commence gratuitement (Découverte), sans engagement."])
H2("13.2 Réponses aux objections")
TBL(["Objection", "Réponse"],
    [["« L'IA, ça invente n'importe quoi. »",
      "Justement : Adjugo est construit pour NE PAS halluciner. Donnée réelle et sourcée, ou « inconnu ». "
      "Le score est un barème transparent, pas une boîte noire."],
     ["« Mes données sont sensibles. »",
      "Hébergement en UE, cloisonnement strict, RGPD, DPA publié. Vous exportez ou supprimez vos données quand vous voulez."],
     ["« Ça va remplacer mon expertise. »",
      "Non. Adjugo prépare et éclaire ; vous décidez, validez, signez. Un copilote, pas un pilote automatique."],
     ["« On n'a pas le temps d'apprendre un outil. »",
      "Démarrage gratuit, parcours guidé, compte de démo. La première analyse prend quelques minutes."],
     ["« C'est cher. »",
      "Découverte est à 0 €. Un seul marché gagné rembourse des années. Au-delà du quota, 5 € l'analyse — jamais bloqué."],
     ["« On répond déjà seuls. »",
      "Parfait — et les marchés trop gros ? Adjugo vous fait répondre en groupement. C'est du CA que vous ne touchez pas aujourd'hui."],
     ["« Les marchés publics, c'est pas pour nous. »",
      "60 % des marchés en nombre vont déjà aux PME (OECP 2023). Le frein, c'est le temps et les gros dossiers — exactement ce qu'on enlève."],
     ["« On a déjà une plateforme de veille. »",
      "Tant mieux pour les alertes. Mais après l'alerte ? L'analyse, le dossier, le groupement — c'est là qu'Adjugo agit."]],
    [54, 111])
H2("13.3 Le parcours de démo qui claque")
P("Connecte-toi au compte de démonstration (bouton « Voir la démo », sans inscription) et déroule :")
BUL(["<b>1. Veille AO</b> : des appels d'offres réels avec leur source officielle.",
     "<b>2. Une fiche AO « Go »</b> : le score détaillé, les clauses à risque, les pièces exigées.",
     "<b>3. Le consortium (marché de Lorient)</b> : l'invitation d'un co-traitant, sa contribution soumise, "
     "et la génération du <b>DC4</b> — le moment fort.",
     "<b>4. Le dossier</b> : la checklist qui passe au vert et l'export du dossier complet.",
     "<b>5. Le tableau de bord</b> : le pipeline et le taux de réussite (gagné/perdu)."])
CALL("Conseil démo", "Laisse le prospect parler de SES marchés et montre la fonctionnalité qui répond à SON "
     "cas. « Regardez, sur votre type de marché… » convainc plus qu'une démo générique.", 'blue')
H2("13.4 Cibles prioritaires")
BUL(["PME du <b>BTP et second œuvre</b> (couverture, étanchéité, rénovation énergétique, désamiantage…) : "
     "marchés publics fréquents, groupements naturels.",
     "PME de <b>services</b> récurrents aux collectivités.",
     "Entreprises <b>en région</b> qui répondent déjà un peu et veulent industrialiser.",
     "Têtes de réseau, fédérations, groupements d'employeurs : porte d'entrée vers plusieurs PME d'un coup."])
BR()

# ===================== 14. LEXIQUE =====================
SECTION("Lexique express")
TBL(["Terme", "Définition simple"],
    [["AO", "Appel d'offres : la consultation par laquelle un acheteur public sélectionne une entreprise."],
     ["DCE", "Dossier de consultation des entreprises : le « cahier des charges » complet du marché."],
     ["DC1 / DC2", "Formulaires de candidature (lettre de candidature / déclaration du candidat)."],
     ["DC4", "Déclaration de sous-traitance / co-traitance — clé pour les groupements."],
     ["ATTRI1", "Acte d'engagement : l'offre signée, avec le montant."],
     ["DUME", "Document unique de marché européen (candidature simplifiée à l'échelle UE)."],
     ["DPGF / BPU", "Décomposition du prix global et forfaitaire / bordereau des prix unitaires."],
     ["Mémoire technique", "La note décrivant comment l'entreprise exécutera le marché — souvent décisive."],
     ["Go / No-Go", "La décision de répondre ou non ; Adjugo la score."],
     ["Co-traitance / groupement", "Plusieurs entreprises répondent ensemble à un même marché."],
     ["Mandataire", "L'entreprise qui pilote le groupement et porte la candidature commune."],
     ["MAPA", "Marché à procédure adaptée : sous les seuils formalisés, procédure plus souple."],
     ["Procédure formalisée", "Au-dessus des seuils : règles strictes de publicité et de mise en concurrence."],
     ["BOAMP / TED / DECP", "Sources officielles : marchés FR / marchés UE / marchés attribués."],
     ["OECP", "Observatoire économique de la commande publique (les chiffres officiels du secteur)."],
     ["RGPD / DPA", "Protection des données / accord de sous-traitance des données (art. 28)."]],
    [33, 132])
BR()

# ===================== 15. SOURCES & MÉTHODE =====================
SECTION("Sources & méthode")
P("Cohérent avec notre règle anti-hallucination, voici les sources des chiffres cités. Avant d'avancer un "
  "chiffre à l'écrit en clientèle, vérifie-le ici.")
H3("Volume et structure du marché")
BUL(["Recensement OECP 2023 (243 731 contrats, plus de 170 Md€ ; répartition PME/ETI/GE ; nature) — "
     "Observatoire économique de la commande publique, economie.gouv.fr (DAJ) et achats-durables.gouv.fr.",
     "Part des PME (~60 % en nombre, ~30 % en valeur, notamment sur les marchés &gt; 90 000 € HT) — synthèses "
     "OECP / Sénat / DAJ « guide de bonnes pratiques pour faciliter l'accès des TPE-PME »."])
H3("Seuils en vigueur")
BUL(["Seuils de procédure formalisée applicables depuis le 1er janvier 2026 : 216 000 € HT (fournitures/"
     "services, collectivités), 143 000 € HT (État), 5 404 000 € HT (travaux) ; dispense jusqu'à 100 000 € HT "
     "(travaux) et 60 000 € HT (fournitures/services, depuis le 1er avril 2026) — avis publié au JORF du "
     "13 janvier 2026, economie.gouv.fr (DAJ)."])
SMALL("Note : les chiffres de marché correspondent au dernier recensement OECP disponible (2023) et peuvent "
      "évoluer. Les seuils européens sont révisés tous les deux ans. En cas de doute, demander une fiche "
      "chiffrée actualisée à l'équipe avant un usage écrit en clientèle.")
SP(10)
CALL("Un dernier mot", "Adjugo n'est pas « un outil d'IA de plus ». C'est un produit honnête, basé sur des "
     "données vraies, qui résout un vrai problème de PME et ouvre — via le réseau — des marchés inaccessibles "
     "seul. Vends la <b>confiance</b> et l'<b>accès</b> : nos deux forces. Bonne prospection.", 'blue')

# ===================== RENDER =====================
def _footer(canvas, doc):
    canvas.saveState(); w,h = A4
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.5); canvas.line(20*mm,14*mm,w-20*mm,14*mm)
    canvas.setFont('Helvetica',8); canvas.setFillColor(MUTED)
    canvas.drawString(20*mm,9.5*mm,"Adjugo — Dossier commercial interne · confidentiel")
    canvas.drawRightString(w-20*mm,9.5*mm,"p. %d" % (doc.page-1))
    canvas.restoreState()

def _cover(canvas, doc):
    canvas.saveState(); w,h = A4
    canvas.setFillColor(BLUE); canvas.rect(0,h-150*mm,w,150*mm,fill=1,stroke=0)
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold',46); canvas.drawString(22*mm,h-58*mm,"adjugo")
    canvas.setFont('Helvetica-Bold',25); canvas.drawString(22*mm,h-86*mm,"Dossier commercial")
    canvas.setFont('Helvetica',14)
    canvas.drawString(22*mm,h-98*mm,"Tout ce qu'il faut s'approprier pour prospecter,")
    canvas.drawString(22*mm,h-106*mm,"pitcher et convaincre.")
    canvas.setFont('Helvetica',10.5); canvas.setFillColor(INK2)
    canvas.drawString(22*mm,h-172*mm,"Destiné à la direction commerciale — usage interne")
    canvas.drawString(22*mm,h-180*mm,"Édité par PADIS (Eliot Viegas) · juin 2026")
    canvas.setFont('Helvetica',9); canvas.setFillColor(MUTED)
    canvas.drawString(22*mm,h-200*mm,"Produit, fondations techniques, fonctionnalités, marché chiffré,")
    canvas.drawString(22*mm,h-206*mm,"vision, état d'esprit, processus de vente — et boîte à outils.")
    canvas.restoreState()

toc_flow = [Paragraph("Sommaire", S['h1']), Spacer(1,6)]
for num,title in toc_entries:
    row = Table([[Paragraph(num,S['tocb']), Paragraph(E(title),S['toc'])]], colWidths=[12*mm,153*mm])
    row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    toc_flow.append(row)
toc_flow.append(PageBreak())

full = [NextPageTemplate('body'), Spacer(1,1), PageBreak()] + toc_flow + story
doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm,
                      bottomMargin=20*mm, title="Adjugo — Dossier commercial interne", author="PADIS — Adjugo")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main')
doc.addPageTemplates([PageTemplate(id='cover', frames=[frame], onPage=_cover),
                      PageTemplate(id='body', frames=[frame], onPage=_footer)])
doc.build(full)
print("PDF généré :", OUT, "| sections:", len(toc_entries))
