"""
Compte de DÉMONSTRATION — le groupement du gymnase de Kerhel, de bout en bout, sans IA ni réseau.

Le marché vitrine du groupement (Kerhel Agglomération, 1 250 000 € HT, Breizh Désamiantage sur le lot 1)
s'arrêtait à « Réunir les parts » : convention « Pas encore préparée », forme du groupement « Non vérifié »,
« Avant de déposer : 1 contrôle sur 4 ». La session démo ne peut rien écrire : tout ce qu'un visiteur doit
pouvoir montrer est rempli ici, avec les VRAIS moteurs de l'application (comme demo_redaction.py pour le
marché « toiture ») :

  1. seed_dossier (AVANT le calcul du groupement, qui lit les exigences citées) : le dossier du marché,
     FICTIF (règlement, CCAP, CCTP, décomposition du prix), mis en PDF puis lu EN ENTIER par dce_lecture ;
     l'analyse passe par analysis.finalize_analysis : chiffre d'affaires, qualification SS3, cumul des
     capacités et forme du groupement sont cités, et la garde des citations vérifie chaque phrase contre
     le dossier entier ; « Comment vous serez noté » et le score sont recalculés sans IA ;
  2. seed_convention (APRÈS l'invitation et la part du partenaire) : le dossier rangé dans le coffre du
     marché ; la convention préparée comme le ferait le chef de file (forme laissée au choix par le
     règlement : conjoint, chef de file solidaire comme la phrase citée le demande ; pouvoirs par défaut ;
     sa part : lots 2 et 3) ; GÉNÉRÉE par le code de la route (offre figée, empreinte) ; validée par le
     chef de file puis par le partenaire (mêmes fonctions que les routes d'accord, niveau d'identité
     réellement prouvé) ; formulaires DC1, DC2 et ATTRI1 remplis APRÈS elle (même fonction que la route
     des formulaires) ; journal chaîné écrit comme par les routes. « Avant de déposer » : 3 contrôles sur 4,
     l'attestation URSSAF du chef de file expirant avant la date limite (alerte gardée volontairement).
     Le marché n'est pas marqué déposé.

Tout est fictif et le dit : chaque page du dossier porte le bandeau de demo_redaction ; l'acheteur n'est
jamais nommé dans les pièces. Clés de stockage liées au contenu : rien ne s'accumule d'un démarrage à
l'autre. Chaque étape est appelée par demo_seed.ensure_demo dans SA transaction (un seul commit) : un échec
laisse le reste de la vitrine intact.
"""
import copy
import logging

logger = logging.getLogger("adjugo")

DCE_NOM = "DCE — Réhabilitation énergétique du gymnase municipal.zip"
_DOSSIER_ZIP = "DCE gymnase municipal"
PREFIXE = "kerhel"          # clés de stockage : demo/dce_kerhel_<empreinte>.zip, demo/lecture/kerhel_…
_VERSION = "1"              # à incrémenter si le texte du dossier change (nouvelles clés de stockage)

# ── 1. Le dossier du marché (fictif) ──────────────────────────────────────────────────────────────
# Exigences de l'analyse, écrites mot pour mot dans le règlement : l'analyse les cite
# (details.exigences_sources, details.forme_groupement) et la garde des citations les vérifie contre le
# dossier entier. Jamais une exigence affichée sans la phrase du dossier qui la porte.
EXIGENCE_CA = ("Le candidat justifie d'un chiffre d'affaires annuel moyen d'au moins 3 000 000 € HT sur les trois "
               "derniers exercices.")
JUSTIFICATION_CA = ("Ce niveau, supérieur au double du montant estimé, est justifié par les risques particuliers du "
                    "retrait d'amiante dans un équipement public.")
EXIGENCE_QUALIFICATIONS = ("Le candidat justifie d'une qualification désamiantage SS3 et d'une certification amiante "
                           "sous-section 3, en cours de validité.")
EXIGENCE_CAPACITES = "En cas de groupement, les capacités des membres sont appréciées globalement."
# Formule usuelle des règlements : forme au choix, chef de file (mandataire) solidaire en conjoint.
EXIGENCE_FORME = ("Le groupement peut être conjoint ou solidaire ; s'il est conjoint, le mandataire est solidaire de "
                  "chacun des membres du groupement pour ses obligations contractuelles à l'égard de l'acheteur.")
EXIGENCE_VISITE = ("La visite du site est obligatoire. Elle a lieu le 5 décembre 2026 à 14 h ; l'attestation de "
                   "visite remise à cette occasion est jointe à l'offre, sous peine d'irrecevabilité.")

_RC = ("01 - Règlement de la consultation.pdf", "RÈGLEMENT DE LA CONSULTATION", [
    "Réhabilitation énergétique et désamiantage du gymnase municipal",
    "Marché public de travaux passé selon la procédure de l'appel d'offres ouvert.",
    "## Article 1 — Objet et allotissement",
    "La consultation porte sur la réhabilitation énergétique et le désamiantage du gymnase municipal. Les "
    "travaux sont répartis en trois lots : lot 1, désamiantage et retrait d'amiante ; lot 2, isolation thermique "
    "et rénovation énergétique ; lot 3, gros œuvre et étanchéité.",
    "Les candidats présentent une offre pour un ou plusieurs lots. Le délai d'exécution est de 9 mois à compter "
    "de l'ordre de service.",
    "## Article 2 — Conditions de participation",
    EXIGENCE_CA + " " + JUSTIFICATION_CA,
    EXIGENCE_QUALIFICATIONS,
    EXIGENCE_CAPACITES,
    "Chaque candidat, et chaque membre d'un groupement, justifie d'une assurance de responsabilité civile "
    "professionnelle, d'une garantie décennale et d'une assurance couvrant les travaux sur matériaux amiantés.",
    "## Article 3 — Candidature en groupement",
    "Les candidats peuvent se présenter seuls ou en groupement d'entreprises.",
    EXIGENCE_FORME,
    "Une même entreprise ne peut pas être mandataire de plus d'un groupement pour ce marché.",
    "## Article 4 — Visite du site",
    EXIGENCE_VISITE,
    "## Article 5 — Contenu de l'offre",
    "Chaque candidat remet l'acte d'engagement complété, la décomposition du prix global et forfaitaire, un "
    "mémoire technique, le plan de retrait de l'amiante et le bilan carbone de l'entreprise.",
    "## Article 6 — Variantes",
    "Les variantes ne sont pas autorisées.",
    "## Article 7 — Jugement des offres",
    "Les offres sont jugées sur les critères pondérés suivants, dont le total fait 100 %.",
    "1. Prix : 50 %.",
    "2. Valeur technique : 50 %.",
    "La valeur technique est appréciée au vu du mémoire technique : méthode de retrait de l'amiante, "
    "organisation du chantier, performance énergétique visée et bilan carbone. Le prix est apprécié au vu de la "
    "décomposition du prix global et forfaitaire.",
    "## Article 8 — Remise des offres",
    "Les offres sont remises par voie dématérialisée avant le 20 décembre 2026 à 17h00.",
])

_CCAP = ("02 - CCAP.pdf", "CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES", [
    "## Article 1 — Prix",
    "Chaque lot est traité à prix global et forfaitaire.",
    "## Article 2 — Paiement",
    "Les sommes dues sont payées dans un délai de 30 jours. En cas de groupement conjoint, chaque membre est "
    "payé directement pour la part qui lui revient.",
    "## Article 3 — Garanties",
    "Une retenue de garantie de 5 % est appliquée. Le titulaire fournit en outre une garantie à première demande.",
    "## Article 4 — Pénalités de retard",
    "En cas de retard, le titulaire subit une pénalité de 1/1000 du montant hors taxes du marché par jour de "
    "retard.",
    "## Article 5 — Sous-traitance",
    "La sous-traitance est autorisée. Chaque sous-traitant est déclaré au moyen du formulaire DC4.",
    "## Article 6 — Assurances",
    "Le titulaire justifie d'une assurance de responsabilité civile professionnelle, d'une garantie décennale "
    "et d'une assurance couvrant les travaux sur matériaux amiantés.",
    "## Article 7 — Bilan carbone",
    "Le titulaire remet le bilan carbone de son entreprise avec son offre, puis le bilan des émissions du "
    "chantier à la réception des travaux.",
])

_CCTP = ("03 - CCTP.pdf", "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES", [
    "## Article 1 — Description du bâtiment",
    "Le gymnase, construit en 1974, compte une salle de sport de 1 200 m², des vestiaires et une "
    "toiture-terrasse de 1 450 m². Il est fermé au public pendant toute la durée des travaux.",
    "## Article 2 — Lot 1 : désamiantage et retrait d'amiante",
    "Le repérage avant travaux a identifié de l'amiante dans les plaques de couverture, les colles de faïence "
    "des vestiaires et les joints des menuiseries.",
    "Le retrait est réalisé en sous-section 3, sous confinement, selon le plan de retrait validé. Des mesures "
    "d'empoussièrement précèdent la restitution de chaque zone. Les déchets amiantés sont suivis par bordereau "
    "jusqu'à leur élimination.",
    "## Article 3 — Lot 2 : isolation thermique et rénovation énergétique",
    "Les murs sont isolés par l'extérieur, les menuiseries remplacées et la ventilation reprise.",
    "## Article 4 — Lot 3 : gros œuvre et étanchéité",
    "Le lot comprend la reprise des maçonneries dégradées, l'isolation de la toiture-terrasse et la pose d'une "
    "membrane d'étanchéité bicouche, relevés compris.",
    "## Article 5 — Coordination entre les lots",
    "Les lots 2 et 3 n'interviennent dans une zone qu'après sa restitution par le lot 1, au vu des mesures "
    "d'empoussièrement.",
])

_DPGF = ("04 - Décomposition du prix global et forfaitaire.pdf", "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE", [
    "Le candidat complète chaque poste du ou des lots auxquels il répond. Les montants sont exprimés en euros "
    "hors taxes.",
    "Lot 1 — Installation du chantier de retrait et confinement",
    "Lot 1 — Retrait des matériaux amiantés, mesures et évacuation des déchets",
    "Lot 2 — Isolation des murs par l'extérieur",
    "Lot 2 — Remplacement des menuiseries et reprise de la ventilation",
    "Lot 3 — Reprise des maçonneries",
    "Lot 3 — Isolation et étanchéité de la toiture-terrasse",
    "Total hors taxes par lot, TVA et total toutes taxes comprises.",
])

PIECES = (_RC, _CCAP, _CCTP, _DPGF)

# Critères tels qu'écrits au règlement (mêmes noms que l'analyse d'origine : le score ne bouge pas).
CRITERES = [
    {"critere": "Prix", "ponderation": "50 %", "extrait": "1. Prix : 50 %."},
    {"critere": "Valeur technique", "ponderation": "50 %", "extrait": "2. Valeur technique : 50 %."},
]

# ── 2. Le groupement (choix du chef de file, accords) ─────────────────────────────────────────────
PART_CHEF_DE_FILE_HT = 970000.0          # 1 250 000 − 280 000 (lot 1 de Breizh Désamiantage)
LOT_CHEF_DE_FILE = ("Lots 2 et 3 — Isolation thermique et rénovation énergétique ; gros œuvre et "
                    "étanchéité")
ACCORD_CHEF_DE_FILE = ("Gwénaël Le Bihan", "Gérant")      # nom et qualité saisis à l'accord
FORMULAIRES = ("dc1", "dc2", "attri1")


def dossier_zip() -> bytes:
    """Le dossier fictif du marché, en archive ZIP (octets stables : la clé de stockage suit le contenu)."""
    from app.services import demo_redaction as dr
    return dr.dossier_zip(PIECES, _DOSSIER_ZIP)


def analyse_kerhel(base: dict, lecture: dict, company: dict, criteria: dict) -> dict:
    """L'analyse du marché telle qu'après l'import de son dossier : l'extraction (rédigée pour la démo,
    phrases recopiées du règlement) passe par le post-traitement DÉTERMINISTE de l'application
    (finalize_analysis : citations vérifiées contre le texte intégral, grille « Comment vous serez noté »,
    score), puis reçoit la couverture de la lecture — exactement comme analyse_toiture."""
    from app.services import dce_lecture as lec
    from app.services.analysis import finalize_analysis
    texte, _meta = lec.texte_integral(lecture)
    mani = lec.manifeste(lecture)
    ext = copy.deepcopy(base)
    det = dict(ext.get("details") or {})
    det["criteres_attribution"] = copy.deepcopy(CRITERES)
    det["capacites_groupement"] = "cumul admis"
    det["exigences_sources"] = {"ca_minimum_requis": EXIGENCE_CA,
                                "qualifications_requises": EXIGENCE_QUALIFICATIONS,
                                "capacites_groupement": EXIGENCE_CAPACITES}
    det["forme_groupement"] = {"imposee": "libre", "extrait": EXIGENCE_FORME}
    ext["details"] = det
    out = finalize_analysis(ext, texte, company, criteria, mani["pieces"])
    for k in ("summary", "source", "pieces_requises"):
        if k in base:
            out[k] = copy.deepcopy(base[k])
    out["lead_score"] = {"total": out["match_score"], "breakdown": out["score_breakdown"],
                         "note": (out.get("summary") or "")[:140]}
    out["dce_available"] = True
    out["lecture"] = mani
    cov = lec.couverture(lecture)
    cov["mode"] = "integral"
    out["couverture"] = cov
    out["mode_lecture"] = "integral"
    out["dce_excerpt"] = texte[:30000]
    return out


def seed_dossier(db, user, proj_by_key: dict) -> None:
    """Étape 1 (avant le calcul du groupement) : le dossier du marché lu en entier, l'analyse citée.
    UNE transaction : en cas d'échec, l'appelant annule tout (le marché garde l'analyse d'origine)."""
    from app.models import Project
    from app.services import demo_redaction as dr
    from app.services.demo_seed import _COMPANY, _CRITERIA
    pid = proj_by_key.get("lorient")
    project = db.get(Project, pid) if pid else None
    if project is None:
        return
    contenu = dossier_zip()
    lecture = dr.lecture_dossier(DCE_NOM, contenu)
    analyse = analyse_kerhel(project.ai_analysis or {}, lecture, _COMPANY, _CRITERIA)
    project.ai_analysis = analyse
    project.match_score = analyse.get("match_score")
    project.go_decision = analyse.get("go_decision")      # « Bon potentiel en groupement » : calculé ensuite
    project.ai_summary = analyse.get("summary") or project.ai_summary
    dr.ranger_lecture(project, contenu, lecture, prefixe=PREFIXE, version=_VERSION)
    db.commit()


def seed_convention(db, user, proj_by_key: dict) -> None:
    """Étape 2 (après l'invitation et la part du partenaire) : dossier dans le coffre du marché,
    convention préparée, générée, validée par les deux membres, formulaires officiels remplis après elle.
    UNE transaction (un seul commit), puis le journal chaîné, écrit comme par les routes."""
    from app.core.org import member_ids
    from app.models import Project, ProjectContribution, ProjectStatus
    from app.routers import convention as rc
    from app.routers.cerfa import produire_formulaire
    from app.routers.invites import _guest_actor, tenant_owner_id
    from app.services import audit
    from app.services import demo_redaction as dr
    from app.services import groupement_convention as gc
    from app.services.atelier import _oublier_lectures, cle_dossier_acheteur
    from app.services.groupement_members import active_invites
    pid = proj_by_key.get("lorient")
    project = db.get(Project, pid) if pid else None
    if project is None:
        return
    invites = [i for i in active_invites(db, project.id) if (i.role or "cotraitant") != "sous_traitant"]
    if not invites:
        return
    owner_ids = member_ids(user, db)

    # Le dossier du marché dans son coffre (dossier « DCE »), comme après un vrai import.
    dr.ranger_document(db, user, project, dossier_zip(), nom=DCE_NOM, prefixe=PREFIXE)
    _oublier_lectures(cle_dossier_acheteur(db, project, owner_ids))

    # Ce que fait le chef de file dans « Monter le groupement » : la forme lue dans le règlement est
    # proposée d'office (nouveau_brouillon) ; laissée au choix, il retient « chacun responsable de sa
    # part » (conjoint) et coche le chef de file solidaire que la phrase citée demande ; pouvoirs par
    # défaut ; sa part (prix de vente et lots) — paramètres passés par la validation de la route.
    conv = gc.get_convention(db, project.id) or rc.nouveau_brouillon(db, project)
    fi = gc.forme_imposee(project)
    if conv.forme not in gc.FORMES:
        conv.forme = "conjoint"
    extrait = (fi.get("extrait") or "").lower()
    conv.mandataire_solidaire = conv.forme == "conjoint" and "mandataire" in extrait and "solidaire" in extrait
    conv.habilitation = gc.default_habilitation()
    params = dict(conv.params or {})
    params.update(gc.validate_params({"part_mandataire_ht": PART_CHEF_DE_FILE_HT,
                                      "lot_mandataire": LOT_CHEF_DE_FILE}))
    conv.params = params
    db.flush()

    # Génération (= figer l'offre commune) : le code de POST …/groupement/convention/generer.
    company = gc._company_for(db, project)
    built = rc.contexte_generation(db, project, conv, company)
    rc.appliquer_generation(db, project, conv, built, owner_ids)
    db.flush()
    sigs = gc.signatures_of(db, conv)

    # Accord du chef de file, depuis son compte (POST …/convention/valider) : adresse confirmée exigée.
    if not getattr(user, "email_verified", False):
        raise RuntimeError("compte démo sans adresse confirmée : accord du chef de file impossible")
    nom, qualite = ACCORD_CHEF_DE_FILE
    rc._check_valider_body(rc.ValiderIn(content_hash=conv.content_hash or "", signataire_nom=nom,
                                        signataire_qualite=qualite, accepte=True), conv)
    chef = next(s for s in sigs if gc.member_kind(s) == "mandataire")
    rc.enregistrer_accord(chef, conv, nom=nom, qualite=qualite, identity_level="compte_verifie",
                          email=user.email or "", user_id=user.id)

    # Accord de chaque partenaire, par son lien (POST /api/invite/{token}/convention/valider) : le niveau
    # d'identité est celui que le lien prouve réellement (aucune vérification simulée).
    for inv in invites:
        sig = next(s for s in sigs if s.invite_id == inv.id)
        part = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
        p_nom = (part.representant_legal if part else "") or sig.signataire_nom or ""
        p_qualite = (part.signataire_qualite if part else "") or ""
        rc._check_valider_body(rc.ValiderIn(content_hash=conv.content_hash or "", signataire_nom=p_nom,
                                            signataire_qualite=p_qualite, accepte=True), conv)
        level, email = rc._identity_level(inv, None)
        rc.enregistrer_accord(sig, conv, nom=p_nom, qualite=p_qualite, identity_level=level, email=email,
                              user_id=None)
    db.flush()
    if not rc.tous_d_accord(db, conv):
        raise RuntimeError("convention de la démo : un accord manque")

    # Formulaires officiels remplis APRÈS la convention (POST /api/cerfa/{id}/{type}) : ils reprennent ses
    # membres, parts, prix, forme et pouvoirs ; « Avant de déposer » vérifie qu'ils datent d'après elle.
    for doc_type in FORMULAIRES:
        produire_formulaire(db, project, company, doc_type)
    project.status = ProjectStatus.en_cours        # réponse en préparation (pas encore déposée)
    db.commit()
    db.refresh(conv)

    # Journal chaîné (après le commit, comme les routes) : offre figée, convention générée, accords.
    owner = tenant_owner_id(project, db)
    rc.journaliser_generation(db, project, conv, actor=f"user:{user.id}")
    audit.record(db, action="convention.signed", owner_id=owner, project_id=project.id,
                 actor=f"user:{user.id}", actor_kind="owner", target_type="convention", target_id=conv.id,
                 detail=f"version {conv.version} — empreinte {(conv.content_hash or '')[:12]}")
    for inv in invites:
        part = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
        audit.record(db, action="convention.signed", owner_id=owner, project_id=project.id,
                     actor=_guest_actor(inv), actor_kind="guest", target_type="convention", target_id=conv.id,
                     invite_id=inv.id, detail=((part.company_name if part else "") or inv.company_name or "")[:255])
    logger.info("Vitrine démo : groupement Kerhel validé par les %d membres (convention v%s, %s HT).",
                len(sigs), conv.version, gc.eur(conv.total_offre_ht))
