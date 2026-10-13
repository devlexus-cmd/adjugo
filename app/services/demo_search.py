"""Résultats de « Trouver des marchés » pour le compte DÉMO.

Le vrai BOAMP renvoie une liste vide sur une requête démo (le compte n'a pas de
spécialités qui alimentent la requête) → la recherche paraissait cassée. On sert
donc une liste canned d'appels d'offres réalistes (villes variées partout en
France, déjà pré-notés), et l'analyse de l'un d'eux renvoie une analyse rédigée
canned — sans appel LLM ni consommation de quota. Uniquement pour la vitrine.
"""
from app.services.demo_seed import _analysis, DEMO_EMAIL
from app.sourcing.schemas import NormalizedTender, Provenance, Score

_P = lambda *paras: (chr(10) * 2).join(paras)   # paragraphes -> texte avec sauts de ligne


def is_demo(user) -> bool:
    return (getattr(user, "email", "") or "").strip().lower() == DEMO_EMAIL


# 5 AO démo : villes variées (grandes + moyennes), métiers couverture/étanchéité/rénovation.
_TENDERS = [
    dict(ref="DEMO-01", montant=380000.0, dept="31", pieces=[
            "Attestation Qualibat 3212 (en cours de validité)", "Attestation RGE",
            "Mémoire technique — méthodologie de couverture", "3 références de toitures scolaires (< 3 ans)",
            "Attestation d'assurance décennale", "DC1, DC2 et attestations fiscales et sociales"],
        summary="Réfection de la toiture d'un groupe scolaire à Toulouse — lot unique, 380 k€, valeur technique prépondérante. Métier, zone et qualifications alignés : cible prioritaire.",
        details={
            "intitule_marche": "Réfection de la toiture du groupe scolaire Jean-Jaurès",
            "acheteur": "Toulouse Métropole",
            "contact": {"nom": "Direction de la commande publique", "fonction": "Marchés bâtiment", "email": "marches@toulouse-metropole.fr", "telephone": "05 61 22 29 22"},
            "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
            "budget_estime": "380 000 EUR HT", "date_limite": "16/01/2027 à 12h00",
            "delai_execution": "4 mois — hors période scolaire", "lieu_execution": "Toulouse (31)", "allotissement": "Lot unique",
            "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}],
            "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 10%",
            "avance": "Avance de 10%", "sous_traitance": "Autorisée — déclaration DC4",
            "variantes": "Autorisées sur les matériaux de couverture", "critere_rse": "Oui — clause d'insertion (120 h)",
            "ca_minimum_requis": "CA > 800 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212", "RGE"],
            "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
            "visite_obligatoire": "Recommandée, sur rendez-vous",
            "points_attention": ["Critère technique prépondérant (60%) — soigner le mémoire", "Travaux à réaliser hors présence des élèves (vacances)", "Clause d'insertion de 120 h à sécuriser"],
            "recommandation": _P(
                "Réfection de la toiture d'un groupe scolaire à Toulouse, en lot unique pour 380 000 € HT, portée par Toulouse Métropole. C'est une cible prioritaire : l'objet est au cœur de votre métier (couverture), le chantier est dans votre zone d'intervention et les qualifications exigées (Qualibat 3212, RGE) sont détenues. Le chiffre d'affaires minimum demandé (800 k€ sur 3 ans) est largement dans vos cordes : la recevabilité ne pose aucun problème.",
                "L'attribution se joue sur la valeur technique, qui pèse 60 % contre 40 % pour le prix. Ce marché ne se gagne donc pas au moins-disant, mais sur la qualité du mémoire technique : méthodologie de dépose et de pose, traitement des points singuliers, et surtout gestion d'un chantier en site scolaire occupé. C'est ce dernier point qui fait souvent la différence — un rétroplanning calé sur les vacances scolaires, une commande de matériaux anticipée et une équipe dédiée rassurent l'acheteur sur le respect du calendrier.",
                "Deux clauses méritent une action : la retenue de garantie de 5 % (à remplacer par une caution bancaire de substitution pour préserver la trésorerie) et la clause d'insertion de 120 heures (à sécuriser en conventionnant en amont une structure locale). En synthèse : foncez, en investissant prioritairement le mémoire technique et la maîtrise du planning."),
        }),
    dict(ref="DEMO-02", montant=520000.0, dept="44", pieces=[
            "Attestation Qualibat 3212", "Attestation RGE", "Mémoire technique — étanchéité de toiture-terrasse",
            "3 références de toitures-terrasses (< 3 ans)", "Attestation d'assurance décennale",
            "DC1, DC2 et attestations à jour"],
        summary="Étanchéité d'une toiture-terrasse de gymnase à Nantes — 520 k€, lot unique. Cœur de métier, zone et qualifications alignés : très bonne cible.",
        details={
            "intitule_marche": "Réfection de l'étanchéité de la toiture-terrasse du gymnase municipal",
            "acheteur": "Nantes Métropole",
            "contact": {"nom": "Service commande publique", "fonction": "Marchés travaux", "email": "commande.publique@nantesmetropole.fr", "telephone": "02 40 99 48 48"},
            "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
            "budget_estime": "520 000 EUR HT", "date_limite": "09/01/2027 à 17h00",
            "delai_execution": "5 mois", "lieu_execution": "Nantes (44)", "allotissement": "Lot unique",
            "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "55%"}, {"critere": "Prix", "ponderation": "45%"}],
            "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 10%",
            "avance": "Avance de 10%", "sous_traitance": "Autorisée — déclaration DC4",
            "variantes": "Autorisées sur le complexe d'étanchéité", "critere_rse": "Oui — valorisation des déchets de chantier",
            "ca_minimum_requis": "CA > 1 000 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212", "RGE"],
            "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
            "visite_obligatoire": "Recommandée",
            "points_attention": ["Étanchéité de toiture-terrasse — soigner les relevés et points singuliers", "Équipement recevant du public — sécurité et phasage", "Valeur technique majoritaire (55%)"],
            "recommandation": _P(
                "Réfection de l'étanchéité de la toiture-terrasse d'un gymnase à Nantes, en lot unique pour 520 000 € HT, portée par Nantes Métropole. Marché en plein cœur de votre métier (étanchéité), dans votre zone la plus proche, avec des qualifications détenues (Qualibat 3212, RGE). Le chiffre d'affaires minimum (1 M€) est atteignable au regard de votre CA : la candidature est parfaitement recevable.",
                "La valeur technique pèse 55 % : c'est le mémoire qui décide. Il faut y détailler le complexe d'étanchéité retenu, le traitement des relevés, des évacuations d'eaux pluviales et des points singuliers, ainsi que la gestion d'un équipement recevant du public (sécurité, phasage si le gymnase reste partiellement ouvert). La possibilité de variantes sur le complexe est une opportunité : proposer une solution mieux-disante techniquement peut faire l'écart.",
                "Sur le plan administratif, la retenue de garantie de 5 % se neutralise par une caution de substitution. Le critère RSE porte sur la valorisation des déchets de chantier — un point facile à traiter et à valoriser dans l'offre. En synthèse : très bonne cible, à travailler sérieusement côté mémoire technique ; la visite de site, bien que seulement recommandée, est conseillée pour fiabiliser le diagnostic de l'existant."),
        }),
    dict(ref="DEMO-03", montant=880000.0, dept="69", pieces=[
            "Qualification RGE", "Mémoire technique — rénovation énergétique et couverture",
            "Bilan carbone de l'entreprise", "Attestation d'assurance décennale",
            "Références de rénovations énergétiques", "DC1, DC2, DC4 (co-traitance)"],
        summary="Rénovation énergétique et couverture d'un collège à Lyon — 880 k€, 2 lots. En zone et sur votre métier, mais CA exigé élevé : candidature en groupement à étudier.",
        details={
            "intitule_marche": "Rénovation énergétique et réfection de couverture du collège Ampère",
            "acheteur": "Département du Rhône",
            "contact": {"nom": "Direction des collèges", "fonction": "Marchés travaux", "email": "marches@rhone.fr", "telephone": "04 72 61 76 00"},
            "type_marche": "Travaux", "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
            "budget_estime": "880 000 EUR HT", "date_limite": "23/01/2027 à 12h00",
            "delai_execution": "8 mois", "lieu_execution": "Lyon (69)",
            "allotissement": "Lot 1 : Isolation et rénovation énergétique ; Lot 2 : Couverture et étanchéité",
            "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "50%"}, {"critere": "Prix", "ponderation": "50%"}],
            "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour",
            "avance": "Avance de 10%", "sous_traitance": "Autorisée", "variantes": "Non autorisées",
            "critere_rse": "Oui — bilan carbone exigé",
            "ca_minimum_requis": "CA > 2 000 000 EUR sur 3 ans", "qualifications_requises": ["RGE", "Qualibat 3212"],
            "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
            "visite_obligatoire": "Obligatoire — sur créneaux",
            "points_attention": ["CA exigé (2 M€) supérieur à votre CA N-1", "Deux lots complémentaires — opportunité de groupement", "Bilan carbone exigé"],
            "recommandation": _P(
                "Rénovation énergétique et réfection de couverture d'un collège à Lyon, pour 880 000 € HT, allotie en deux lots (isolation/énergie et couverture/étanchéité), portée par le Département du Rhône. Le marché est en zone et sur votre cœur de métier : l'opportunité est réelle. Un seul verrou de recevabilité : le chiffre d'affaires minimum demandé (2 M€ sur 3 ans) dépasse votre CA N-1.",
                "La bonne stratégie est le groupement : répondre à plusieurs permet de cumuler les chiffres d'affaires — le verrou saute — et de couvrir proprement les deux lots (un spécialiste isolation/énergie sur le lot 1, votre entreprise sur le lot 2 couverture/étanchéité). La sous-traitance est autorisée, mais un groupement conjoint est ici plus solide, car il partage la responsabilité et rassure l'acheteur sur la capacité globale.",
                "Le bilan carbone exigé est un point à ne pas négliger : préparez-le en amont, il conditionne la recevabilité et nourrit le critère RSE. La visite est obligatoire, sur créneaux — à réserver dès la parution. En synthèse : à étudier sérieusement, en groupement de préférence ; seul, la barre de CA vous écarte, alors qu'à plusieurs c'est un marché à 880 k€ à portée de main."),
        }),
    dict(ref="DEMO-04", montant=265000.0, dept="59", pieces=[
            "Attestation Qualibat 3212", "Mémoire technique — couverture et zinguerie",
            "3 références de couvertures de bâtiments publics", "Attestation d'assurance décennale",
            "DC1, DC2 et attestations fiscales et sociales"],
        summary="Réfection de la couverture et zinguerie d'une médiathèque à Lille — 265 k€, lot unique. Cœur de métier, zone et qualifications alignés : bonne cible.",
        details={
            "intitule_marche": "Réfection de la couverture et de la zinguerie de la médiathèque",
            "acheteur": "Métropole Européenne de Lille",
            "contact": {"nom": "Service marchés publics", "fonction": "Marchés travaux", "email": "marchespublics@lillemetropole.fr", "telephone": "03 20 21 22 23"},
            "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
            "budget_estime": "265 000 EUR HT", "date_limite": "13/01/2027 à 12h00",
            "delai_execution": "3 mois", "lieu_execution": "Lille (59)", "allotissement": "Lot unique",
            "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "50%"}, {"critere": "Prix", "ponderation": "50%"}],
            "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 8%",
            "avance": "Avance de 10%", "sous_traitance": "Autorisée — déclaration DC4",
            "variantes": "Non autorisées", "critere_rse": "Oui — clause d'insertion (80 h)",
            "ca_minimum_requis": "CA > 600 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212"],
            "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
            "visite_obligatoire": "Recommandée",
            "points_attention": ["Bâtiment recevant du public maintenu en activité", "Zinguerie et raccords soignés", "Prix et technique à parité (50/50)"],
            "recommandation": _P(
                "Réfection de la couverture et de la zinguerie de la médiathèque, à Lille, en lot unique pour 265 000 € HT, portée par la Métropole Européenne de Lille. Couverture/zinguerie en plein cœur de votre métier, dans votre zone, avec la qualification Qualibat 3212 détenue et un chiffre d'affaires minimum (600 k€) aisément couvert : la recevabilité est acquise.",
                "Les critères prix et valeur technique sont à parité (50/50). Sur ce type de marché, l'offre gagnante est celle qui présente le meilleur rapport qualité/prix : un mémoire technique soigné (traitement de la zinguerie, des raccords et des évacuations d'un bâtiment probablement ancien) doublé d'un prix maîtrisé. La médiathèque restant ouverte au public, la gestion du chantier — phasage, sécurité, propreté, limitation du bruit — doit être explicitement traitée.",
                "Deux points administratifs : la retenue de garantie de 5 % (caution de substitution) et la clause d'insertion de 80 heures (à conventionner en amont avec une structure locale). En synthèse : bonne cible, à jouer sur l'équilibre technique/prix ; ne pas surinvestir la marge, mais ne pas non plus brader — c'est le rapport qualité/prix qui décide ici."),
        }),
    dict(ref="DEMO-05", montant=1150000.0, dept="67", pieces=[
            "Qualification désamiantage SS3 (ou co-traitant)", "Plan de retrait amiante",
            "Mémoire technique", "Bilan carbone", "Attestation de visite obligatoire",
            "DC1, DC2, DC4 (co-traitance)"],
        summary="Désamiantage et réfection de couverture d'un bâtiment communal à Strasbourg — 1,15 M€. En zone et sur votre métier, mais qualification SS3 non détenue : réponse en groupement à étudier.",
        details={
            "intitule_marche": "Désamiantage et réfection de couverture d'un bâtiment communal",
            "acheteur": "Eurométropole de Strasbourg",
            "contact": {"nom": "Direction de la construction", "fonction": "Marchés travaux", "email": "marches@strasbourg.eu", "telephone": "03 68 98 50 00"},
            "type_marche": "Travaux", "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
            "budget_estime": "1 150 000 EUR HT", "date_limite": "27/01/2027 à 12h00",
            "delai_execution": "7 mois", "lieu_execution": "Strasbourg (67)",
            "allotissement": "Lot 1 : Désamiantage ; Lot 2 : Couverture et étanchéité",
            "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "50%"}, {"critere": "Prix", "ponderation": "50%"}],
            "garanties_exigees": "Retenue de garantie 5% + garantie à première demande", "penalites": "1/1000 du montant HT par jour",
            "avance": "Avance de 5%", "sous_traitance": "Autorisée", "variantes": "Non autorisées",
            "critere_rse": "Oui — bilan carbone exigé",
            "ca_minimum_requis": "CA > 2 500 000 EUR sur 3 ans", "qualifications_requises": ["Qualification désamiantage SS3", "Qualibat 3212"],
            "assurances_requises": ["RC Professionnelle", "Garantie décennale", "Assurance amiante"],
            "visite_obligatoire": "Obligatoire",
            "points_attention": ["Qualification désamiantage SS3 exigée (non détenue)", "CA minimum (2,5 M€) supérieur à votre CA", "Garantie à première demande"],
            "recommandation": _P(
                "Désamiantage et réfection de couverture d'un bâtiment communal à Strasbourg, pour 1,15 M€ HT, alloti en deux lots (désamiantage, puis couverture/étanchéité), porté par l'Eurométropole. Le marché est en zone et le lot couverture est dans votre métier, mais deux verrous conditionnent la recevabilité et un troisième pèse sur la trésorerie.",
                "Premier verrou : la qualification désamiantage sous-section 3 (SS3), exigée et non détenue en interne. Deuxième verrou : le chiffre d'affaires minimum demandé (2,5 M€ sur 3 ans), supérieur à votre CA. Répondre seul est donc impossible. À cela s'ajoute une garantie à première demande, appelable sans justification, qui engage lourdement la trésorerie.",
                "La stratégie est claire : répondre en groupement conjoint avec un désamianteur certifié SS3. Il prend le lot 1, apporte la qualification manquante, et le groupement cumule les chiffres d'affaires — les deux verrous sautent. Vous conservez le lot couverture/étanchéité, votre cœur de métier. Sur la garantie à première demande, proposer une caution bancaire classique en substitution. La visite est obligatoire. En synthèse : à étudier, mais uniquement à plusieurs — seul, il est hors d'atteinte ; en groupement, un marché à 1,15 M€ devient accessible."),
        }),
]


def _details_of(t) -> dict:
    return dict(t["details"])   # recommandation est déjà une chaîne (via _P)


def search_results() -> list:
    """Liste NormalizedTender canned (avec score d'adéquation pré-calculé)."""
    out = []
    for t in _TENDERS:
        a = _analysis(_details_of(t), t["summary"], t["ref"], t["pieces"])
        out.append(NormalizedTender(
            objet=t["details"]["intitule_marche"],
            acheteur=t["details"]["acheteur"],
            montant_estime=t["montant"],
            date_limite=t["details"].get("date_limite"),
            lieu=t["details"].get("lieu_execution"),
            departements=[t["dept"]],
            cpv=["45261000"],
            procedure=t["details"].get("nature_marche"),
            nature="Travaux",
            provenance=Provenance(source="BOAMP", source_url="/static/demo/avis-boamp.html", official_ref=t["ref"]),
            confidence=0.9,
            score=Score(total=a["match_score"], breakdown=a["score_breakdown"], fit_assessable=True),
        ))
    return out


def analysis_for(ref: str):
    """Analyse canned d'un AO démo (réutilise _analysis, sans LLM ni quota)."""
    t = next((x for x in _TENDERS if x["ref"] == ref), None)
    if not t:
        return None
    return _analysis(_details_of(t), t["summary"], ref, t["pieces"])
