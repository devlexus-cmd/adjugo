"""
La banque de questions de l'entretien chantier (rédaction, vague 5 — D de l'étude, § 6.9), SANS IA.

Environ 40 questions pour le BTP, chacune DÉCLENCHÉE par des mots trouvés dans le dossier de l'acheteur
(site occupé, établissement recevant du public, école, travail de nuit, amiante, plomb, voirie, co-activité,
Architectes des Bâtiments de France, phasage, déchets, bruit…). Pour chaque question :
  • `declencheurs` : expressions cherchées dans le texte REPLIÉ du dossier (minuscules, sans accents, même
    longueur que l'original : dce_pieces.fold) ; la phrase du dossier autour du premier mot trouvé est la
    phrase qui MOTIVE la question, montrée telle quelle (retrouvée mot pour mot, citation_guard) ;
  • `criteres` : débuts de mots cherchés dans les critères de « Comment vous serez noté », DANS L'ORDRE : le
    premier qui correspond donne le critère concerné, et son poids classe la question ;
  • `parties` : débuts de mots cherchés dans les parties du plan (intitulé, critère, question du cadre) pour
    trouver la PARTIE CONCERNÉE (celle qui reçoit la réponse, ou « [À compléter : …] » si la question est
    sautée) ;
  • `lots` : débuts de mots cherchés dans le lot des partenaires du groupement (la question est proposée au
    partenaire dont le lot, et lui seul, correspond) ;
  • `a_completer` : ce qui manque quand la question est sautée (« [À compléter : chef de chantier] ») ;
  • `famille` « environnement » : l'environnement déclenche TOUJOURS une question (§ 6.9) ;
  • `type_reponse` « equipe » : la réponse se choisit dans la liste « Équipe » de « Mes preuves » (jamais le
    CV à l'IA), ou s'écrit.
L'ordre de la banque est la priorité à poids égal : les contraintes propres au site d'abord, les questions
générales ensuite. Mathys valide la banque avec les 7 PME (risque de l'étude) : la modifier ne demande
aucune migration (les questions déjà posées gardent leur texte et leur numéro).
"""

ENVIRONNEMENT = "environnement"
TEXTE, EQUIPE = "texte", "equipe"


def _q(code, theme, question, declencheurs, criteres, parties, a_completer, *, lots=(), famille="",
       type_reponse=TEXTE, aide=""):
    return {"code": code, "theme": theme, "question": question, "declencheurs": list(declencheurs),
            "criteres": list(criteres), "parties": list(parties), "lots": list(lots), "a_completer": a_completer,
            "famille": famille, "type_reponse": type_reponse, "aide": aide}


# Débuts de mots communs (critères et parties).
_ORGA = ["site occup", "organis", "securi", "methodolog"]
_METHODO = ["methodolog", "execution", "technique", "organis"]
_ENV = ["environ", "dechet", "developpement durable", "nuisanc", "ecolog"]

BANQUE = [
    # ── Le site et ses occupants ────────────────────────────────────────────────────────────────────
    _q("site_occupe", "cohabitation avec les occupants",
       "Le site reste occupé pendant les travaux : comment organisez-vous la cohabitation avec les occupants "
       "(accès séparés, horaires, information) ?",
       [r"\bsites? occupes?\b", r"\blocaux occupes\b", r"\ben site occupe\b", r"\breste(?:ra|nt)? en (?:activite|fonctionnement|service)\b",
        r"\bmaintien de l'activite\b", r"\ben presence des (?:occupants|usagers|eleves|residents|agents|habitants)\b",
        r"\bpendant les travaux,? (?:l'etablissement|le batiment|l'ecole|les locaux) reste"],
       ["site occup", "occup", "organis", "securi", "methodolog"], ["site occup", "occup", "organis", "cohabit", "methodolog"],
       "cohabitation avec les occupants"),
    _q("ecole", "livraisons et accès aux heures des élèves",
       "Le dossier signale une école ou des enfants à proximité : comment organisez-vous les livraisons et les "
       "accès aux heures d'entrée et de sortie des élèves ?",
       [r"\becoles?\b", r"\bgroupe scolaire\b", r"\beleves\b", r"\betablissement scolaire\b", r"\bcolleges?\b",
        r"\blycees?\b", r"\bcreches?\b", r"\bmaternelles?\b", r"\bcantine\b", r"\bcour de recreation\b"],
       ["site occup", "organis", "securi", "acces", "methodolog"], ["site occup", "organis", "acces", "livrais", "securi"],
       "livraisons et accès aux heures des élèves"),
    _q("erp", "sécurité du public pendant les travaux",
       "Le bâtiment reçoit du public : quelles mesures prenez-vous pour la sécurité du public pendant les "
       "travaux (balisage, cheminements, issues de secours) ?",
       [r"\betablissements? recevant du public\b", r"\berp\b", r"\bouvert au public\b", r"\baccueil du public\b",
        r"\bdes usagers\b", r"\bdu public\b"],
       ["securi", "organis", "site occup", "methodolog"], ["securi", "organis", "public", "site occup"],
       "sécurité du public pendant les travaux"),
    _q("personnes_fragiles", "précautions envers les personnes fragiles",
       "Le bâtiment accueille des personnes fragiles : quelles précautions prenez-vous (poussières, bruit, "
       "hygiène, circulations) ?",
       [r"\behpad\b", r"\bhopital\b", r"\betablissements? de sante\b", r"\bcliniques?\b", r"\bmaisons? de retraite\b",
        r"\bresidents\b", r"\bpatients\b", r"\bpersonnes agees\b"],
       ["securi", "organis", "site occup", "nuisanc", "methodolog"], ["securi", "organis", "site occup", "nuisanc"],
       "précautions envers les personnes fragiles"),
    _q("nuit", "travaux de nuit ou en horaires décalés",
       "Le dossier prévoit des travaux de nuit, le week-end ou en horaires décalés : comment organisez-vous ces "
       "interventions (équipes, éclairage, bruit) ?",
       [r"\btrava(?:il|ux) de nuit\b", r"\bnocturnes?\b", r"\bhoraires decales\b", r"\ben dehors des heures d'ouverture\b",
        r"\ble week-end\b", r"\bles week-ends\b", r"\bweek-ends?\b", r"\bla nuit\b"],
       ["organis", "planning", "delai", "methodolog"], ["organis", "planning", "horair", "methodolog"],
       "organisation des travaux de nuit ou en horaires décalés"),
    # ── Matériaux dangereux ─────────────────────────────────────────────────────────────────────────
    _q("amiante", "traitement de l'amiante",
       "Le dossier mentionne de l'amiante : qui réalise le retrait ou l'encapsulage, sous quelle certification, et "
       "comment protégez-vous les compagnons et les occupants ?",
       [r"\bamiante\b", r"\bdesamiant", r"\bdta\b", r"\bsous-section [34]\b", r"\bss ?[34]\b"],
       ["securi", "methodolog", "technique", "organis"], ["amiant", "desamiant", "securi", "methodolog", "depose"],
       "traitement de l'amiante", lots=["amiant", "desamiant", "deconstruct", "demolit"]),
    _q("plomb", "protection contre le plomb",
       "Le dossier mentionne du plomb : quelles mesures prenez-vous pour protéger les compagnons et les occupants ?",
       [r"\bplomb\b", r"\bcrep\b", r"\bpeintures? au plomb\b"],
       ["securi", "methodolog", "technique"], ["plomb", "securi", "methodolog", "peintur"],
       "protection contre le plomb", lots=["peintur", "plomb"]),
    # ── Le domaine public et les autres entreprises ─────────────────────────────────────────────────
    _q("voirie", "circulation et signalisation sur la voie publique",
       "Les travaux touchent la voie publique : comment organisez-vous la circulation, la signalisation et les "
       "autorisations de voirie ?",
       [r"\bvoiries?\b", r"\bvoie publique\b", r"\bchaussees?\b", r"\btrottoirs?\b", r"\barretes? de circulation\b",
        r"\bdomaine public\b", r"\bsignalisation temporaire\b", r"\bcirculation des vehicules\b"],
       ["organis", "securi", "methodolog"], ["voiri", "circulat", "signalis", "organis", "securi"],
       "circulation et signalisation sur la voie publique", lots=["voiri", "vrd", "terrassem", "reseau"]),
    _q("coactivite", "coordination avec les autres entreprises",
       "D'autres entreprises interviennent en même temps : comment coordonnez-vous la co-activité sur le chantier ?",
       [r"\bco-?activite\b", r"\bcoordonnateur sps\b", r"\bcoordination sps\b", r"\bplan general de coordination\b",
        r"\bpgc\b", r"\bautres? (?:entreprises|corps d'etat|lots)\b", r"\binterfaces? entre (?:les )?lots\b"],
       ["organis", "securi", "methodolog", "planning"], ["coordin", "organis", "interfac", "securi"],
       "coordination avec les autres entreprises"),
    _q("abf", "prescriptions des Architectes des Bâtiments de France",
       "Le site relève des Architectes des Bâtiments de France : comment tenez-vous compte de leurs prescriptions "
       "(matériaux, teintes, échantillons) ?",
       [r"\barchitectes? des batiments de france\b", r"\babf\b", r"\bmonuments? historiques?\b", r"\bsite patrimonial\b",
        r"\bperimetre (?:protege|des abords)\b", r"\bsecteur sauvegarde\b"],
       ["technique", "methodolog", "qualit", "materia"], ["materia", "methodolog", "patrimoin", "technique"],
       "prise en compte des prescriptions des Architectes des Bâtiments de France"),
    # ── Organisation et méthode ─────────────────────────────────────────────────────────────────────
    _q("phasage", "phasage des travaux",
       "Le dossier demande un phasage : quelles phases prévoyez-vous, et dans quel ordre ?",
       [r"\bphasages?\b", r"\bpar phases?\b", r"\btranches? (?:de travaux|fonctionnelles?)\b", r"\bpar zones?\b",
        r"\bzones? successives?\b", r"\bpar etapes\b", r"\bphases? de travaux\b"],
       ["phas", "organis", "planning", "methodolog"], ["phas", "organis", "planning", "methodolog"],
       "phasage des travaux"),
    _q("acces_toiture", "accès à la toiture",
       "Comment accéderez-vous à la toiture et y monterez-vous les matériaux (escalier, échafaudage, "
       "monte-matériaux) ?",
       [r"\btoitures?\b", r"\btoitures?-terrasses?\b",
        r"\bcouvertures? (?:existante|en (?:zinc|ardoises?|tuiles?|bac)|zinc|ardoise|tuile|bac acier)",
        r"\betancheite (?:de (?:la )?toiture|des toitures|bicouche|multicouche|bitum)", r"\bcharpentes?\b"],
       ["methodolog", "execution", "technique", "organis"], ["toitur", "couvert", "etanch", "methodolog", "execution"],
       "accès à la toiture", lots=["couvert", "couvreur", "toitur", "etanch", "charpent", "zingu"]),
    _q("hauteur", "protection contre les chutes de hauteur",
       "Comment protégez-vous le travail en hauteur (protections collectives, nacelles, échafaudages) ?",
       [r"\btravail en hauteur\b", r"\btravaux en hauteur\b", r"\bprotections? collectives?\b", r"\bgarde-corps\b",
        r"\bechafaudages?\b", r"\bnacelles?\b", r"\bchutes? de hauteur\b", r"\bfilets?\b"],
       ["securi", "prevent", "organis", "methodolog"], ["securi", "prevent", "organis", "methodolog"],
       "protection contre les chutes de hauteur", lots=["couvert", "couvreur", "toitur", "facad", "charpent", "etanch"]),
    _q("intemperies", "protection contre les intempéries",
       "Comment protégez-vous les ouvrages et les locaux contre les intempéries pendant les travaux (bâchage, mise "
       "hors d'eau) ?",
       [r"\bintemperies\b", r"\bmise hors d'eau\b", r"\bhors d'eau\b", r"\bbachage\b", r"\bprotections? provisoires?\b",
        r"\betancheite provisoire\b"],
       ["methodolog", "execution", "technique", "organis"], ["methodolog", "execution", "intemper", "organis"],
       "protection contre les intempéries", lots=["couvert", "couvreur", "toitur", "etanch"]),
    _q("depose", "méthode de dépose ou de démolition",
       "Le dossier prévoit de la dépose ou de la démolition : quelle méthode retenez-vous, et comment "
       "protégez-vous les existants ?",
       [r"\bdemolitions?\b", r"\bdepose (?:de|des|du|d')", r"\bcurage\b", r"\bdeconstruction\b"],
       ["methodolog", "execution", "technique"], ["depos", "demolit", "methodolog", "execution"],
       "méthode de dépose ou de démolition", lots=["demolit", "deconstruct", "desamiant", "curage"]),
    _q("reseaux", "repérage et protection des réseaux",
       "Des réseaux existants sont signalés : comment les repérez-vous et les protégez-vous (déclarations avant "
       "travaux, marquage) ?",
       [r"\breseaux existants\b", r"\bdict\b", r"\bdt-dict\b", r"\breseaux enterres\b", r"\bconcessionnaires\b",
        r"\bcanalisations?\b"],
       ["securi", "methodolog", "technique"], ["reseau", "methodolog", "securi"],
       "repérage et protection des réseaux", lots=["vrd", "reseau", "terrassem", "plomb", "electr"]),
    _q("continuite", "continuité des services pendant les travaux",
       "Des installations doivent rester en service (eau, électricité, chauffage, ascenseur) : comment évitez-vous "
       "les coupures ?",
       [r"\bmaintien en service\b", r"\bcontinuite (?:de|du) service\b", r"\bsans interruption\b", r"\bcoupures?\b",
        r"\bmaintien (?:du chauffage|de l'alimentation|des reseaux)\b"],
       ["organis", "methodolog", "site occup", "technique"], ["organis", "methodolog", "continu"],
       "continuité des services pendant les travaux", lots=["electr", "plomb", "chauff", "genie climat", "ascens"]),
    _q("poussieres", "confinement des poussières",
       "Comment confinez-vous les poussières dans les locaux occupés ou voisins ?",
       [r"\bpoussieres?\b", r"\bconfinement\b", r"\bprotection des locaux\b"],
       ["nuisanc", "environ", "organis", "site occup"], ["nuisanc", "poussier", "organis", "site occup", "environ"],
       "confinement des poussières"),
    _q("incendie", "prévention de l'incendie pendant les travaux",
       "Les travaux demandent des points chauds (soudure, chalumeau) : comment prévenez-vous l'incendie (permis de "
       "feu, surveillance après travaux) ?",
       [r"\bpermis de feu\b", r"\bpoints? chauds?\b", r"\bsoudures?\b", r"\bchalumeau\b", r"\bsecurite incendie\b"],
       ["securi", "methodolog", "prevent"], ["securi", "incend", "methodolog"],
       "prévention de l'incendie pendant les travaux", lots=["etanch", "couvert", "plomb", "metall", "serrur"]),
    _q("levage", "organisation des levages",
       "Le chantier demande des levages (grue, camion-grue) : comment les organisez-vous ?",
       [r"\bgrues?\b", r"\blevages?\b", r"\bcamion-grue\b", r"\bmanutention\b"],
       ["securi", "methodolog", "organis", "moyens"], ["levag", "methodolog", "organis", "moyens", "materiel"],
       "organisation des levages"),
    _q("acces_site", "accès au site et livraisons",
       "Comment accéderez-vous au site (accès des véhicules, horaires de livraison, stationnement des engins) ?",
       [r"\bacces (?:au|du) (?:site|chantier)\b", r"\bacces restreints?\b", r"\bacces limites?\b", r"\bgabarit\b",
        r"\bhauteur limitee\b", r"\blivraisons?\b", r"\bapprovisionnements?\b"],
       ["organis", "methodolog", "securi"], ["acces", "livrais", "organis", "installation"],
       "accès au site et livraisons"),
    _q("installations", "base vie et zones de stockage",
       "Où installerez-vous la base vie et les zones de stockage, et comment les séparez-vous des occupants ?",
       [r"\binstallations? de chantier\b", r"\bbase vie\b", r"\bcantonnements?\b", r"\bzones? de stockage\b",
        r"\baires? de stockage\b", r"\bemprise (?:du|de) chantier\b"],
       ["organis", "securi", "methodolog"], ["installation", "organis", "stockag", "base vie"],
       "base vie et zones de stockage"),
    # ── Environnement (l'environnement déclenche toujours une question) ─────────────────────────────
    _q("dechets", "tri et filières des déchets",
       "Où partent vos déchets de chantier, et comment les triez-vous ?",
       [r"\bdechets?\b", r"\btri\b", r"\bvalorisation\b", r"\bfilieres?\b", r"\bbordereaux? de suivi\b", r"\bbsd\b",
        r"\bsoged\b", r"\brecyclage\b"],
       ["environ", "dechet", "developpement durable", "ecolog"], ["dechet", "environ", "developpement durable", "tri"],
       "tri et filières des déchets", famille=ENVIRONNEMENT),
    _q("bruit", "limitation du bruit et des nuisances",
       "Le dossier parle de bruit ou de nuisances : quelles mesures prenez-vous pour les limiter (horaires, "
       "matériel, information des riverains) ?",
       [r"\bbruits?\b", r"\bnuisances?\b", r"\bnuisances sonores\b", r"\bvibrations?\b", r"\briverains\b"],
       ["nuisanc", "environ", "site occup", "organis"], ["nuisanc", "environ", "bruit", "site occup", "organis"],
       "limitation du bruit et des nuisances", famille=ENVIRONNEMENT),
    _q("reemploi", "réemploi et matériaux biosourcés",
       "Le dossier encourage le réemploi ou les matériaux biosourcés : lesquels proposez-vous sur ce chantier ?",
       [r"\breemploi\b", r"\bbiosources?\b", r"\bmateriaux recycles\b", r"\beconomie circulaire\b", r"\bbas carbone\b"],
       ["environ", "developpement durable", "materia", "technique"], ["environ", "materia", "reemploi", "technique"],
       "réemploi et matériaux biosourcés", famille=ENVIRONNEMENT),
    _q("transports", "transports et émissions du chantier",
       "Comment limitez-vous les transports et les émissions du chantier (approvisionnements, véhicules) ?",
       [r"\bemissions? (?:de (?:gaz|co2|carbone|polluants)|polluantes)\b", r"\bbilan carbone\b", r"\bempreinte carbone\b", r"\bcircuits? courts?\b",
        r"\bvehicules? propres?\b", r"\bgaz a effet de serre\b"],
       ["environ", "developpement durable", "ecolog"], ["environ", "transport", "carbone"],
       "transports et émissions du chantier", famille=ENVIRONNEMENT),
    _q("pollution", "prévention des pollutions",
       "Comment évitez-vous la pollution des sols et de l'eau (laitances, hydrocarbures, eaux de lavage) ?",
       [r"\bpollutions?\b", r"\blaitances?\b", r"\bhydrocarbures\b", r"\beaux de lavage\b",
        r"\brejets? (?:dans|d'eaux?|au reseau|polluants)\b"],
       ["environ", "developpement durable", "ecolog"], ["environ", "pollut"],
       "prévention des pollutions", famille=ENVIRONNEMENT),
    _q("vegetation", "protection des arbres et espaces verts",
       "Des arbres ou des espaces verts sont à protéger : comment les préservez-vous pendant les travaux ?",
       [r"\barbres?\b", r"\bespaces? verts?\b", r"\bvegetation\b", r"\bplantations?\b", r"\bbiodiversite\b"],
       ["environ", "developpement durable", "ecolog"], ["environ", "arbre", "espaces verts"],
       "protection des arbres et espaces verts", famille=ENVIRONNEMENT, lots=["espaces verts", "paysag"]),
    _q("environnement", "mesures environnementales du chantier",
       "Quelles mesures environnementales prenez-vous sur ce chantier (déchets, matériaux, transports, "
       "consommations) ?",
       [r"\benvironnement(?:ale?s?)?\b", r"\bdeveloppement durable\b", r"\bchantier (?:propre|vert|a faibles nuisances)\b",
        r"\bcharte (?:chantier|environnement)\b", r"\becologique\b"],
       ["environ", "developpement durable", "ecolog", "dechet"], ["environ", "developpement durable", "dechet"],
       "mesures environnementales du chantier", famille=ENVIRONNEMENT),
    # ── Moyens humains ──────────────────────────────────────────────────────────────────────────────
    _q("chef_chantier", "chef de chantier",
       "Qui sera le chef de chantier ?",
       [r"\bchefs? de chantier\b", r"\bconducteurs? de travaux\b", r"\bencadrement\b", r"\bmoyens humains\b",
        r"\binterlocuteurs?\b", r"\bresponsable (?:du|de) chantier\b", r"\bpersonnel affecte\b", r"\borganigramme\b",
        r"\breferent\b"],
       ["moyens humains", "humain", "encadrement", "moyens", "organis"],
       ["encadrement", "chef de chantier", "moyens humains", "humain", "equipe", "personnel", "moyens"],
       "chef de chantier", type_reponse=EQUIPE,
       aide="Choisissez une personne de « Mes preuves » (rubrique Équipe) : son nom n'est jamais envoyé à l'IA, et "
            "son CV s'insère tel quel. Vous pouvez aussi l'écrire."),
    _q("sous_traitance", "sous-traitance prévue",
       "Faites-vous appel à des sous-traitants sur ce chantier, et pour quelles tâches ?",
       [r"\bsous-traitances?\b", r"\bsous-traitants?\b", r"\bdc4\b"],
       ["moyens", "organis", "humain"], ["moyens", "sous-trait", "organis", "equipe"],
       "sous-traitance prévue"),
    _q("insertion", "réalisation des heures d'insertion",
       "Le marché comporte une clause d'insertion : comment réalisez-vous ces heures (embauche, structure "
       "d'insertion, sous-traitance) ?",
       [r"\bclauses? (?:sociales?|d'insertion)\b", r"\bheures d'insertion\b", r"\binsertion (?:sociale|professionnelle)\b"],
       ["social", "insertion", "rse", "environ", "developpement durable"],
       ["insertion", "social", "rse", "moyens humains", "developpement durable"],
       "réalisation des heures d'insertion"),
    # ── Délais et planning ──────────────────────────────────────────────────────────────────────────
    _q("periodes", "planning calé sur les périodes imposées",
       "Le dossier impose des périodes de travaux (vacances, saisons, fermetures) : comment calez-vous votre "
       "planning dessus ?",
       [r"\bvacances scolaires\b", r"\bperiode estivale\b", r"\bpendant les vacances\b",
        r"\bperiodes? imposees?\b", r"\bcalendrier impose\b", r"\bfermeture (?:annuelle|estivale)\b"],
       ["planning", "delai", "calendrier", "organis"], ["planning", "delai", "calendrier", "phas"],
       "planning calé sur les périodes imposées"),
    _q("delai", "tenue du délai",
       "Le dossier fixe un délai d'exécution : comment le tenez-vous (effectif, tâches menées en parallèle) ?",
       [r"\bdelais? d'execution\b", r"\bdelai global\b", r"\bdate d'achevement\b",
        r"\bdelai (?:contractuel|imparti)\b"],
       ["delai", "planning", "calendrier"], ["planning", "delai", "calendrier"],
       "tenue du délai d'exécution"),
    # ── Visite, qualité, fin de chantier ────────────────────────────────────────────────────────────
    _q("visite", "constats de la visite du site",
       "Avez-vous visité le site, et qu'y avez-vous relevé (accès, contraintes, état des existants) ?",
       [r"\bvisites? (?:du site|des lieux|obligatoires?|recommandees?|sur site)\b", r"\bvisite prealable\b"],
       ["methodolog", "technique", "organis"], ["methodolog", "organis", "technique", "visite"],
       "constats de la visite du site"),
    _q("controles", "contrôles et essais avant réception",
       "Quels contrôles et quels essais réalisez-vous en cours de chantier et avant la réception ?",
       [r"\bessais?\b", r"\bautocontroles?\b", r"\bcontroles? qualite\b", r"\bplan d'assurance qualite\b", r"\bpaq\b",
        r"\bfiches? de controle\b", r"\breception\b"],
       ["qualit", "controle", "methodolog", "technique"], ["qualit", "controle", "essai", "methodolog", "reception"],
       "contrôles et essais avant réception"),
    _q("doe", "dossier des ouvrages exécutés",
       "Comment préparez-vous le dossier des ouvrages exécutés et les documents de fin de chantier ?",
       [r"\bdossiers? des ouvrages executes\b", r"\bdoe\b", r"\bdiuo\b", r"\bplans de recolement\b"],
       ["qualit", "methodolog", "technique"], ["qualit", "reception", "methodolog", "fin de chantier"],
       "dossier des ouvrages exécutés"),
    _q("materiaux", "matériaux et produits proposés",
       "Quels matériaux et quels produits proposez-vous pour les ouvrages principaux ?",
       [r"\bfiches? techniques?\b", r"\bavis techniques?\b", r"\bou equivalent\b", r"\bechantillons?\b",
        r"\breferences? (?:de|des) produits?\b", r"\bmarques?\b"],
       ["technique", "materia", "qualit", "methodolog"], ["materia", "produit", "technique", "methodolog"],
       "matériaux et produits proposés"),
    _q("garantie", "interventions pendant la garantie de parfait achèvement",
       "Comment intervenez-vous pendant l'année de parfait achèvement (interlocuteur, délai d'intervention) ?",
       [r"\bparfait achevement\b", r"\blevee des reserves\b", r"\bservice apres-vente\b", r"\bmaintenance\b"],
       ["qualit", "technique", "methodolog", "organis"], ["qualit", "garantie", "reception", "methodolog"],
       "interventions pendant la garantie de parfait achèvement"),
    _q("information", "information des riverains et des usagers",
       "Comment informez-vous les riverains et les usagers du déroulement du chantier ?",
       [r"\binformation des (?:riverains|usagers|habitants)\b", r"\bpanneaux? de chantier\b", r"\bconcertation\b"],
       ["organis", "nuisanc", "site occup", "environ"], ["organis", "communic", "site occup", "riverain"],
       "information des riverains et des usagers"),
    _q("securite", "sécurité des compagnons",
       "Comment organisez-vous la sécurité de vos compagnons sur ce chantier (accueil sécurité, équipements, "
       "plan de prévention) ?",
       [r"\bppsps\b", r"\bplan de prevention\b", r"\bprevention des risques\b", r"\bhygiene et securite\b",
        r"\bsecurite\b"],
       ["securi", "prevent", "organis", "methodolog"], ["securi", "prevent", "organis"],
       "sécurité des compagnons"),
]

PAR_CODE = {q["code"]: q for q in BANQUE}
assert len(PAR_CODE) == len(BANQUE), "code en double dans la banque de l'entretien chantier"
