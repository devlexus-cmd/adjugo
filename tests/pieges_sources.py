"""
Jeu de CALIBRATION de « Chaque fait a sa source » (rédaction, vague 3 — étude § 6.5).

Au moins 50 phrases PIÉGÉES, écrites comme l'IA les écrirait (avec ou sans renvoi), sur des sources
fictives : copies d'exigences en « nous », objectifs du dossier repris, paraphrases, calculs exacts et
faux, unités écrites autrement, nombres en lettres, matériel et certifications absents, noms absents,
renvois faux, mauvais type de source, tableaux. Règle : AUCUN piège n'est jamais présenté comme
« trouvé dans vos documents » (ni comme « justificatif déposé »), et chaque piège est À RELIRE.

Aucune donnée réelle : entreprise, documents et dossier de l'acheteur sont inventés pour le test.
Utilisé par tests/test_redaction_v3_sources.py et par scripts/mesure_fausses_alertes.py --pieges.
"""
from app.services import faits_sources as fs

DOC = ("Références récentes\n"
       "En 2024, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), "
       "réalisée seule par notre équipe de 6 couvreurs.\n"
       "Nous disposons de 2 nacelles articulées et d'un échafaudage de 300 m2.\n"
       "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345).\n"
       "Livraison de 12 m3 de béton et de 3 tonnes d'acier sur le chantier de Brest.\n")

DCE = ("REGLEMENT DE LA CONSULTATION\n"
       "Les entreprises devront être certifiées ISO 14001. Le délai d'intervention en cas de fuite est de 48 heures. "
       "Le titulaire mobilisera au moins 4 compagnons. La garantie des travaux est de 12 mois. "
       "Objectif : réduire de 30 % les déchets de chantier et zéro accident. "
       "Le CCTP prévoit 450 m2 de couverture en zinc. Une habilitation électrique B1V est exigée. "
       "Le chantier se situe à Brest. Les entreprises devront disposer d'une grue mobile. "
       "Le candidat justifiera de la certification MASE. Les matériaux biosourcés représenteront 50 % du lot. "
       "Le titulaire interviendra sous 24 h.\n")

NOMS = ["Breizh Couverture"]


def fiches() -> list:
    """Sources fictives de l'entreprise, numérotées et typées comme la rédaction les remet."""
    F = fs.Fiche
    return [
        F("F1", fs.T_DOCUMENTS, fs.LIB_TROUVE,
          "Référence : Réfection de la toiture de l'école Jules Ferry ; acheteur : Mairie de Quimper ; année 2024 ; "
          "montant 85 000 € HT ; réalisé seul", extra=["85 000 € HT"], preuve_id=1, nature="reference",
          extrait="En 2024, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT)"),
        F("F2", fs.T_DOCUMENTS, fs.LIB_TROUVE, "Matériel : Nacelle articulée ; quantité : 2 ; en propre",
          extra=["2 Nacelle articulée"], preuve_id=2, nature="materiel",
          extrait="Nous disposons de 2 nacelles articulées"),
        F("F3", fs.T_DECLARE, fs.LIB_DECLARE, "Qualification : Qualibat 3194 ; valable jusqu'au 31/12/2027",
          preuve_id=3, nature="qualification"),
        F("F4", fs.T_PUBLIC, "marché attribué, source publique DECP",
          "Référence : Couverture du gymnase ; acheteur : Commune de Plougastel ; année 2022 ; montant 120 000 € HT ; "
          "réalisé seul", extra=["120 000 € HT"], preuve_id=4, nature="reference"),
        F("F5", fs.T_ESTIMATION, fs.LIB_ESTIMATION, "Chiffre clé : Durée du chantier : 6 semaines",
          extra=["6 semaines Durée du chantier"], preuve_id=5, nature="chiffre_cle"),
        F("F6", fs.T_DECLARE, fs.LIB_DECLARE, "Équipe : Yann Tanguy, Conducteur de travaux ; 15 ans d'expérience",
          extra=["15 ans d'expérience"], preuve_id=6, nature="salarie",
          valeur={"nom": "Yann Tanguy", "fonction": "Conducteur de travaux", "experience_annees": 15}),
    ] + fs.fiches_contexte(
        "Entreprise : Breizh Couverture (SARL), Lorient.\n"
        "Effectif : 12 (salariés, personnes, collaborateurs, compagnons, employés).\n"
        "Chiffre d'affaires N-1 : 1200000 €.",
        "- Hélène Le Gall, Chef de chantier ; qualifications : BTS Bâtiment, 10 ans",
        "- [Préparation] Installation de chantier : 3 jours\n- [Couverture] Pose du zinc : 15 jours\n"
        "Charge totale : 18 jours.\n- [Levage] Location grue mobile : 2 jours", []
    ) + fs.fiches_extraits([{"ref": "S1", "doc_name": "Mémoire 2024", "chunk_id": 51, "text": DOC}])


def acheteur() -> "fs.Acheteur":
    return fs.Acheteur([("Règlement de la consultation", DCE)])


# (phrase écrite par l'IA, fait piégé (morceau du fait relevé), partie sur les moyens ?)
PIEGES = [
    # 1. Copies d'exigences de l'acheteur, écrites en « nous ».
    ("Nous sommes certifiés ISO 14001 [F3].", "ISO 14001", False),
    ("Nous intervenons sous 48 heures en cas de fuite [S1].", "48 heures", False),
    ("Nous mobiliserons 4 compagnons sur le chantier [P2].", "4 compagnons", False),
    ("Nous assurons une garantie de 12 mois sur nos travaux [F1].", "12 mois", False),
    ("Nous disposons de l'habilitation B1V.", "B1V", False),
    ("Nous disposons d'une grue mobile pour le levage.", "grue", False),
    ("Notre entreprise est certifiée MASE.", "MASE", False),
    ("Nous utiliserons 50 % de matériaux biosourcés.", "50 %", False),
    # 2. Objectifs du dossier repris comme des faits sur l'entreprise.
    ("Nous réduirons de 30 % les déchets de chantier.", "30 %", False),
    ("Notre démarche vise zéro accident sur le chantier.", "zéro", False),
    ("Nous atteindrons 100 % de tri des déchets.", "100 %", False),
    ("Nous couvrirons les 450 m2 de toiture en zinc.", "450 m2", False),
    # 3. Paraphrases avec un autre nombre.
    ("Notre équipe compte quinze salariés [P2].", "quinze", False),
    ("Nous comptons plus de 20 collaborateurs.", "20 collaborateurs", False),
    ("Notre conducteur de travaux a 20 ans d'expérience [F6].", "20 ans", False),
    ("Nous avons réalisé la toiture de l'école Jules Ferry en 2023 [F1].", "2023", False),
    ("Ce chantier pour la Mairie de Quimper s'élevait à 95 000 € HT [F1].", "95 000", False),
    ("Nous disposons de 3 nacelles articulées [F2].", "3 nacelles", False),
    # 4. Calculs faux (les calculs exacts sont plus bas, hors pièges).
    ("Nos 6 couvreurs représentent 60 % de nos 12 salariés [S1][P2].", "60 %", False),
    ("L'installation (3 jours) et la pose (15 jours) font au total 20 jours [C1][C2].", "20 jours", False),
    ("Nos 2 nacelles représentent 40 % de notre parc de 5 engins [F2].", "40 %", False),
    ("Nos références cumulées dépassent 500 000 € HT [F1][F4].", "500 000", False),
    # 5. Unités écrites autrement (même nombre, autre chose).
    ("Nous avons livré 12 tonnes de béton à Brest [S1].", "12 tonnes", False),
    ("Notre échafaudage couvre 300 m3 [S1].", "300 m3", False),
    ("Le chantier de l'école Jules Ferry a duré 85 jours [F1].", "85 jours", False),
    ("La durée du chantier sera de 6 mois [F5].", "6 mois", False),
    ("Notre conducteur de travaux a 15 mois d'ancienneté [F6].", "15 mois", False),
    ("Notre chiffre d'affaires atteint 12 M€ [P3].", "12 M€", False),
    ("Nous employons 12 intérimaires [P2].", "12 intérimaires", False),
    # 6. Nombres en lettres.
    ("Nous disposons de trois nacelles articulées [F2].", "trois", False),
    ("Notre équipe de vingt compagnons interviendra sur le site [P2].", "vingt", False),
    ("Nos deux conducteurs de travaux encadreront le chantier [E1].", "deux", False),
    # 7. Matériel absent.
    ("Nous mobiliserons notre mini-pelle pour les accès.", "mini-pelle", False),
    ("Un drone permettra l'inspection des toitures [S1].", "drone", True),
    ("Notre camion grue assurera le levage des bacs.", "camion", False),
    # 8. Certifications et qualifications absentes.
    ("Nous sommes titulaires de la qualification Qualibat 1312 [F3].", "Qualibat 1312", False),
    ("Nous sommes RGE.", "RGE", False),
    ("Notre entreprise est certifiée ISO 45001.", "ISO 45001", False),
    ("Nos compagnons sont titulaires du CACES R486.", "CACES", False),
    ("Nous sommes labellisés PEFC.", "PEFC", False),
    # 9. Noms propres absents.
    ("Nous avons rénové la toiture de la Mairie de Brest en 2024 [F1].", "Mairie de Brest", False),
    ("Nous travaillons depuis dix ans avec Vinci Construction.", "Vinci Construction", False),
    ("Le chantier sera encadré par Paul Durand.", "Paul Durand", False),
    ("Nous avons couvert le gymnase de la Commune de Plougastel en 2021 [F4].", "2021", False),
    # 10. Renvois faux ou inexistants.
    ("Nous sommes qualifiés Qualibat 9999 [F99].", "Qualibat 9999", False),
    ("Notre effectif atteint 14 personnes [F2].", "14 personnes", False),
    # 11. Mauvais type de source (votre estimation n'appuie que des délais, effectifs, quantités).
    ("Nous possédons une grue mobile [C4].", "grue", False),
    ("Nous avons 18 salariés [C3].", "18 salariés", False),
    # 12. Phrase sur l'entreprise déguisée en phrase sur le marché.
    ("Le titulaire, c'est-à-dire notre entreprise, mobilisera 4 compagnons.", "4 compagnons", False),
    ("Le chantier sera réalisé par 15 compagnons.", "15 compagnons", False),
    ("Le marché sera exécuté par 4 compagnons de notre équipe [P2].", "4 compagnons", False),
    # 13. Phrase sur le marché, mal recopiée du dossier de l'acheteur.
    ("Le CCTP prévoit 500 m2 de couverture en zinc.", "500 m2", False),
    ("Le règlement exige la certification ISO 9001.", "ISO 9001", False),
    # 14. Une phrase, un fait juste et un fait inventé.
    ("Nous disposons de 2 nacelles articulées et d'une grue mobile [F2].", "grue", False),
    ("Notre équipe de 12 salariés compte 4 conducteurs de travaux [P2].", "4 conducteurs", False),
    # 15. Engagement et délai inventé.
    ("Nous garantissons une intervention sous 24 h.", "24 h", False),
    # 16. Tableaux.
    ("| Moyens | Quantité |\n|---|---|\n| Nacelles articulées | 3 |", "3", True),
    ("| Effectif | Nombre |\n|---|---|\n| Compagnons | 15 |", "15", True),
    # 17. Année de création.
    ("Créée en 1998, notre entreprise intervient dans tout le Finistère.", "1998", False),
    ("Notre entreprise réalise chaque année 40 chantiers de couverture [P1].", "40 chantiers", False),
    # 18. Calculs inventés à partir des nombres des faits cités, absents de la phrase (revue de la vague 3) :
    #     un calcul n'est accepté que s'il est ÉCRIT dans la phrase.
    ("Nous mobiliserons au total 14 compagnons sur ce chantier [P2][F2].", "14 compagnons", False),
    ("Nous valorisons 17 % de nos déchets de chantier [P2][F2].", "17 %", False),
    ("Le chantier durera au total 45 jours [C1][C2].", "45 jours", False),
    ("Nous mobiliserons au total 24 compagnons [P2][F2].", "24 compagnons", False),
    ("Nous réduirons nos consommations d'eau de 15 % [S1].", "15 %", False),
    ("Nous assurons l'ensemble du chantier en 5 jours [C1][C4].", "5 jours", False),
    ("Nos 6 couvreurs représentent 2 % de l'effectif régional [S1].", "2 %", False),
    ("Nous recyclons 64 % de nos déchets [S1].", "64 %", False),
    ("Nous valorisons 20 % de nos déchets de chantier [C1][C2].", "20 %", False),
    ("Nos 2 nacelles et nos 12 salariés, soit 14 moyens, seront sur place [F2][P2].", "14 moyens", False),
    # 19. Certification générique sans objet commun : jamais reliée à une qualification quelconque.
    ("Nous sommes agréés pour le retrait de l'amiante.", "agréés", False),
    ("Notre entreprise est certifiée pour le désamiantage [S1].", "certifiée", False),
    ("Nous sommes certifiés depuis 2024 [S1].", "certifiés", False),
    ("Nos couvreurs sont labellisés pour la pose de panneaux solaires [F3].", "labellisés", False),
    ("Nous sommes labellisés Reconnu Garant de l'Environnement [S1].", "labellisés", False),
    # 20. « 12 de nos compagnons » : le nombre compte le nom qui suit (jamais « 12 m3 de béton »).
    ("Nous mobiliserons 3 de nos compagnons sur ce chantier [S1].", "3", False),
    ("Plus de 300 de nos chantiers ont été livrés à l'heure [S1].", "300", False),
    ("Deux de nos conducteurs de travaux encadreront le chantier [S1].", "Deux", False),
    ("Nous comptons 3 de nos tonnes de stock en atelier [S1].", "3", False),
    # 21. Engagements sans chiffre : à confirmer.
    ("Notre entreprise s'engage à livrer le chantier avant la rentrée.", "s'engage à", False),
    ("Breizh Couverture s'engage à remettre le DOE en fin de chantier.", "s'engage à", False),
    ("Nous promettons une intervention rapide en cas d'urgence.", "promettons", False),
    ("Nous intervenons dans l'heure en cas d'urgence.", "dans l'heure", False),
    ("Nous livrerons les travaux sans aucune réserve.", "sans aucune réserve", False),
    ("Nous nous obligeons à respecter le planning.", "nous obligeons", False),
]

# Pièges dont le fait piégé est un ENGAGEMENT (il doit être relevé comme tel, « à confirmer »).
ENGAGEMENTS = [p for p in PIEGES if p[1] in ("s'engage à", "promettons", "dans l'heure", "sans aucune réserve",
                                             "nous obligeons")]

# Contrôles HORS pièges : des faits justes, reliés au bon endroit (sinon l'outil ne servirait à rien).
JUSTES = [
    ("Nous disposons de 2 nacelles articulées [F2].", "2 nacelles", fs.T_DOCUMENTS),
    ("En 2024, nous avons refait la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT) [F1].",
     "Mairie de Quimper", fs.T_DOCUMENTS),
    ("Notre équipe compte 12 salariés [P2].", "12 salariés", fs.T_DECLARE),
    ("La pose du zinc durera 15 jours [C2].", "15 jours", fs.T_ESTIMATION),
    ("Nos 6 couvreurs représentent 50 % de nos 12 salariés [S1][P2].", "50 %", fs.T_CALCUL),
    ("L'installation (3 jours) et la pose (15 jours) font au total 18 jours [C1][C2].", "18 jours", fs.T_CALCUL),
    ("Notre chiffre d'affaires atteint 1,2 M€ [P3].", "1,2 M€", fs.T_DECLARE),
    ("Nous avons couvert le gymnase de la Commune de Plougastel en 2022 [F4].", "Commune de Plougastel", fs.T_PUBLIC),
    ("Nous sommes qualifiés Qualibat 3194 [F3].", "Qualibat 3194", fs.T_DECLARE),
    ("Le CCTP prévoit 450 m2 de couverture en zinc.", "450 m2", fs.T_ACHETEUR),
]


def controler(phrase: str, section_entreprise: bool = False) -> list:
    return fs.controler(phrase, fiches(), acheteur=acheteur(), noms_entreprise=NOMS,
                        section_entreprise=section_entreprise, mode="ia")


def fait_de(items: list, morceau: str) -> list:
    """Les éléments relevés dont le fait contient `morceau` (accents et casse près)."""
    from app.services.faits_a_relire import fold
    m = fold(morceau)
    return [x for x in items if m and m in fold(x.get("fait"))]


def bilan_pieges() -> dict:
    """{pieges, presentes_comme_documents, non_signales, details} — l'objectif : 0 et 0."""
    docs, muets, details = [], [], []
    for phrase, morceau, sect in PIEGES:
        items = controler(phrase, sect)
        hits = fait_de(items, morceau)
        en_doc = [x for x in hits if (x.get("source") or {}).get("type") in (fs.T_DOCUMENTS, fs.T_JUSTIFICATIF)]
        if en_doc:
            docs.append(phrase)
        if not any(x.get("statut") == fs.A_RELIRE for x in hits):
            muets.append(phrase)
        details.append({"phrase": phrase, "piege": morceau,
                        "releves": [(x["fait"], x["statut"], (x.get("source") or {}).get("type")) for x in items]})
    return {"pieges": len(PIEGES), "presentes_comme_documents": docs, "non_signales": muets, "details": details}
