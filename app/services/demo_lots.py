"""
Compte de DÉMONSTRATION — plusieurs lots, un seul effort (rédaction, vague 6 — J), sans IA ni réseau.

Un marché FICTIF réparti en trois lots, l'école maternelle Les Hirondelles de la Ville de Trémorvan, auquel
Bâtiment de l'Ouest répond sur DEUX lots (lot 2 couverture et zinguerie, lot 3 étanchéité des toitures-terrasses).
Tout passe par les VRAIS moteurs déterministes de l'application (comme app/services/demo_redaction.py) :
  1. le dossier du marché (règlement, deux CCTP de lot, décomposition du prix), mis en PDF puis lu EN ENTIER par
     dce_lecture ; l'analyse passe par analysis.finalize_analysis (citations vérifiées, grille « Comment vous serez
     noté », score) ;
  2. l'atelier : lots repérés dans le règlement (atelier_lots.reperer), lots 2 et 3 choisis, plan construit sans IA
     — une partie COMMUNE (gestion environnementale) et, pour chaque lot, ses parties propres (méthodologie, moyens) ;
     textes FICTIFS écrits pour la démo avec leurs renvois, faits contrôlés sans IA comme après une rédaction ;
  3. ce que la démo montre : le lot 2 prêt à exporter (fichier nommé comme le règlement l'exige), le lot 3 encore en
     préparation (une partie à écrire), la partie commune reprise telle quelle dans les deux fichiers, les limites de
     pages contrôlées lot par lot, l'entretien chantier préparé.
Rien n'est écrit dans les textes du marché « toiture ». Tout est fictif et le dit (bandeau de chaque page). Appelé par
demo_seed.ensure_demo dans SA transaction : un échec laisse le reste de la vitrine intact.
"""
import copy
import hashlib
import logging
import zipfile
from io import BytesIO

logger = logging.getLogger("adjugo")

CLE = "ecole"
NOM = "Restructuration — École maternelle Les Hirondelles (3 lots)"
CLIENT = "Ville de Trémorvan"
DCE_NOM = "DCE — École maternelle Les Hirondelles.zip"
_DOSSIER_ZIP = "DCE école maternelle Les Hirondelles"
_VERSION = "1"            # à incrémenter si le texte du dossier change (nouvelles clés de stockage)
LOTS_CHOISIS = ("2", "3")
REGLE_NOMMAGE = "Chaque mémoire est remis dans un fichier nommé « Lot X - Mémoire technique - Nom du candidat »."
LIMITE = "Le mémoire technique compte 6 pages au maximum par lot, page de garde comprise."
POLICE = "Il est rédigé en police Arial de taille 11."

_RC = ("01 - Règlement de la consultation.pdf", "RÈGLEMENT DE LA CONSULTATION", [
    "Restructuration de l'école maternelle Les Hirondelles",
    "Marché public de travaux passé selon une procédure adaptée.",
    "## Article 1 — Objet et allotissement",
    "La consultation porte sur la restructuration de l'école maternelle Les Hirondelles : désamiantage, réfection de "
    "la couverture et étanchéité des toitures-terrasses. Les travaux sont répartis en trois lots :",
    "Lot 1 : Désamiantage",
    "Lot 2 : Couverture et zinguerie",
    "Lot 3 : Étanchéité des toitures-terrasses",
    "## Article 2 — Délai d'exécution",
    "Le délai d'exécution est de 4 mois à compter de l'ordre de service. Les travaux en toiture au droit des salles "
    "de classe sont réalisés pendant les vacances scolaires.",
    "## Article 3 — Contenu de l'offre",
    "Pour chaque lot, le candidat remet l'acte d'engagement, la décomposition du prix global et forfaitaire et un "
    "mémoire technique propre au lot.",
    LIMITE,
    POLICE,
    REGLE_NOMMAGE,
    "## Article 4 — Jugement des offres",
    "Pour chacun des lots, les offres sont jugées sur les critères pondérés suivants, dont le total fait 100 %.",
    "1. Valeur technique : 60 %.",
    "1.1 Méthodologie d'exécution des travaux du lot : 30 %.",
    "1.2 Moyens humains et matériels affectés au lot : 20 %.",
    "1.3 Gestion environnementale du chantier : 10 %.",
    "2. Prix des prestations : 40 %.",
    "La valeur technique est appréciée au vu du mémoire technique du lot. Le prix est apprécié au vu de la "
    "décomposition du prix global et forfaitaire du lot.",
    "## Article 5 — Remise des offres",
    "Les offres sont remises par voie dématérialisée avant le 15 janvier 2027 à 12h00.",
])

_CCTP2 = ("02 - CCTP lot 2 couverture et zinguerie.pdf", "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES — LOT 2", [
    "## Article 1 — Description des ouvrages",
    "La couverture de l'école est en ardoise naturelle sur une charpente en bois. La zinguerie est réalisée en zinc "
    "naturel.",
    "## Article 2 — Dépose et repose",
    "La couverture existante est déposée par zones successives ; chaque zone est refermée en fin de journée.",
    "## Article 3 — Site occupé",
    "L'école reste en activité pendant les travaux : les zones de travail sont séparées des cheminements des élèves.",
])

_CCTP3 = ("03 - CCTP lot 3 étanchéité.pdf", "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES — LOT 3", [
    "## Article 1 — Description des ouvrages",
    "Les toitures-terrasses du préau et de la salle de motricité reçoivent un isolant thermique et une membrane "
    "d'étanchéité bicouche en bitume élastomère.",
    "## Article 2 — Relevés et points singuliers",
    "Les relevés d'étanchéité et les traversées de toiture sont traités avant la pose de la protection.",
    "## Article 3 — Déchets",
    "Les déchets de dépose sont triés et évacués vers des filières agréées, avec bordereaux de suivi.",
])

_DPGF = ("04 - Décomposition du prix par lot.pdf", "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE", [
    "Le candidat complète chaque poste du ou des lots auxquels il répond. Les montants sont exprimés en euros hors "
    "taxes.",
    "Lot 2 — Dépose et repose de la couverture en ardoise",
    "Lot 2 — Zinguerie et évacuation des eaux pluviales",
    "Lot 3 — Isolation et membrane d'étanchéité des toitures-terrasses",
    "Total hors taxes par lot, TVA et total toutes taxes comprises.",
])

PIECES = (_RC, _CCTP2, _CCTP3, _DPGF)

# Critères « proposés par l'IA » (recopiés tels quels du règlement) : la grille les contrôle SANS IA.
CRITERES = [
    {"critere": "Valeur technique", "ponderation": "60 %", "extrait": "1. Valeur technique : 60 %.",
     "sous_criteres": [
         {"critere": "Méthodologie d'exécution des travaux du lot", "ponderation": "30 %",
          "extrait": "1.1 Méthodologie d'exécution des travaux du lot : 30 %."},
         {"critere": "Moyens humains et matériels affectés au lot", "ponderation": "20 %",
          "extrait": "1.2 Moyens humains et matériels affectés au lot : 20 %."},
         {"critere": "Gestion environnementale du chantier", "ponderation": "10 %",
          "extrait": "1.3 Gestion environnementale du chantier : 10 %."}]},
    {"critere": "Prix des prestations", "ponderation": "40 %", "extrait": "2. Prix des prestations : 40 %."},
]

DETAILS = {
    "intitule_marche": "Restructuration de l'école maternelle Les Hirondelles",
    "acheteur": CLIENT, "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)",
    "forme_prix": "Prix global et forfaitaire, par lot", "budget_estime": "640 000 EUR HT",
    "date_limite": "15/01/2027 à 12h00", "delai_execution": "4 mois à compter de l'ordre de service",
    "lieu_execution": "Trémorvan (44)",
    "allotissement": "Lot 1 : Désamiantage ; Lot 2 : Couverture et zinguerie ; Lot 3 : Étanchéité des toitures-terrasses",
    "sous_traitance": "Autorisée", "variantes": "Non autorisées", "critere_rse": "Non",
    "qualifications_requises": ["Qualibat 3212"], "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
    "visite_obligatoire": "Non",
    "pieces_requises": [{"nom": "Mémoire technique", "disponible": False},
                        {"nom": "Décomposition du prix global et forfaitaire", "disponible": False}],
    "points_attention": ["Un mémoire technique par lot, 6 pages au plus chacun",
                         "Nom des fichiers imposé par le règlement", "Travaux en toiture pendant les vacances scolaires"],
    "recommandation": ("Restructuration d'une école maternelle répartie en trois lots, pour 640 000 € HT. Les lots 2 "
                       "(couverture et zinguerie) et 3 (étanchéité des toitures-terrasses) sont au cœur de votre "
                       "métier ; le lot 1 (désamiantage) demande une qualification que vous n'avez pas.\n\nLe "
                       "règlement demande un mémoire technique propre à chaque lot, de 6 pages au plus, et impose le "
                       "nom de chaque fichier. La grille est la même pour chacun des lots : valeur technique 60 % "
                       "(méthodologie, moyens, gestion environnementale), prix 40 %.\n\nEn synthèse : répondez aux lots "
                       "2 et 3 ensemble. La partie sur la gestion environnementale du chantier vaut pour les deux lots : "
                       "rédigée une fois, elle figure dans les deux mémoires."),
    "clauses_risque": [],
}

# Textes FICTIFS (même forme que la sortie du moteur de rédaction) : « {clé} » = renvoi à une preuve de « Mes preuves »
# (résolu vers son numéro réel), [S#] = extrait de « Mon savoir-faire » remis à la partie.
_MEMOIRE = "Mémoire technique — Réfection toiture école de Bréhaut"
_RSE = "Politique RSE"
PARTIES = [
    {"debut": "Méthodologie", "lot": "2", "statut": "valide",
     "extraits": [("S1", _MEMOIRE, "Méthodologie d'étanchéité")],
     "texte": [
         "Bâtiment de l'Ouest conduit la réfection de la couverture zone par zone : dépose soignée des éléments "
         "existants, contrôle de la charpente, puis pose de la couverture neuve et de sa zinguerie [S1].",
         "Le CCTP du lot 2 prévoit une couverture en ardoise naturelle et une zinguerie en zinc naturel.",
         "Chaque zone est refermée en fin de journée, de façon à ne jamais laisser une salle de classe sans "
         "protection.",
         "Les raccords de zinguerie sont traités comme des points singuliers et contrôlés avant la fermeture de la "
         "zone [S1].",
         "Nous avons appliqué cette méthode à la réfection de la couverture de l'école élémentaire de la Ville de "
         "Bréhaut en 2024 {ref_brehaut}.",
     ]},
    {"debut": "Moyens", "lot": "2", "statut": "valide", "extraits": [],
     "texte": [
         "L'encadrement du chantier est confié à notre conducteur de travaux, qui compte 18 ans d'expérience "
         "{conducteur}.",
         "[CV {conducteur_n}]",
         "L'entreprise compte 14 salariés {effectif}.",
         "Nous disposons en propre de 2 nacelles articulées de 16 m {nacelles} et louons un monte-matériaux "
         "{monte_materiaux}.",
     ]},
    {"debut": "Méthodologie", "lot": "3", "statut": "brouillon",
     "extraits": [("S1", _MEMOIRE, "Méthodologie d'étanchéité")],
     "texte": [
         "Sur les toitures-terrasses, nous posons un pare-vapeur, l'isolant thermique puis une membrane "
         "d'étanchéité bicouche soudée [S1].",
         "Les relevés et les traversées de toiture sont traités avant la pose de la protection, comme le demande le "
         "CCTP du lot 3.",
         "L'entreprise est qualifiée Qualibat 3212 pour l'étanchéité de toiture par éléments {qualibat}.",
     ]},
    {"debut": "Gestion environnementale", "lot": "", "statut": "valide",
     "extraits": [("S1", _MEMOIRE, "Engagements environnementaux"), ("S2", _RSE, "Démarche environnementale")],
     "texte": [
         "Les déchets de chantier sont triés sur place et valorisés dans des filières adaptées [S1].",
         "Bâtiment de l'Ouest est une entreprise reconnue RGE {rge} et suit son bilan carbone chaque année [S2].",
         "Les tournées des véhicules sont optimisées pour limiter les trajets entre le dépôt et le chantier [S2].",
         "Les livraisons sont regroupées en dehors des heures d'entrée et de sortie des élèves.",
     ]},
]


def dossier_zip() -> bytes:
    """Le dossier du marché, en archive ZIP (octets stables : la clé de stockage suit le contenu)."""
    from app.services import demo_redaction as dr
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, titre, paras in PIECES:
            zi = zipfile.ZipInfo(f"{_DOSSIER_ZIP}/{nom}", date_time=(2026, 10, 1, 9, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, dr._pdf(titre, paras))
    return buf.getvalue()


def analyse(lecture: dict, company: dict, criteria: dict, base: dict) -> dict:
    """L'analyse du marché telle qu'après l'import de son dossier : post-traitement DÉTERMINISTE de l'application
    (finalize_analysis : citations vérifiées contre le texte intégral, grille, score), puis la couverture de la
    lecture — exactement comme demo_redaction.analyse_toiture."""
    from app.services import dce_lecture as lec
    from app.services.analysis import finalize_analysis
    texte, _meta = lec.texte_integral(lecture)
    mani = lec.manifeste(lecture)
    ext = copy.deepcopy(base)
    det = dict(ext.get("details") or {})
    det["criteres_attribution"] = copy.deepcopy(CRITERES)
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


def preuves_par_cle(db, uid: int) -> dict:
    """Les preuves de « Mes preuves » du compte démo (créées par demo_redaction.seed_preuves), retrouvées par ce
    qu'elles disent — jamais un numéro codé en dur."""
    from app.models import Preuve
    from app.services import preuves as pv
    out = {}
    regles = {
        "ref_brehaut": (pv.REFERENCE, "acheteur", "Ville de Bréhaut"),
        "conducteur": (pv.SALARIE, "fonction", "Conducteur de travaux"),
        "chef_equipe": (pv.SALARIE, "fonction", "Chef d'équipe étanchéité"),
        "qualibat": (pv.QUALIFICATION, "nom", "Qualibat 3212"),
        "rge": (pv.QUALIFICATION, "nom", "RGE"),
        "nacelles": (pv.MATERIEL, "designation", "Nacelle articulée de 16 m"),
        "monte_materiaux": (pv.MATERIEL, "designation", "Monte-matériaux"),
        "effectif": (pv.CHIFFRE_CLE, "libelle", "Effectif"),
    }
    rows = db.query(Preuve).filter(Preuve.owner_id == uid).all()
    for cle, (nature, champ, val) in regles.items():
        p = next((r for r in rows if r.nature == nature and isinstance(r.valeur, dict)
                  and str(r.valeur.get(champ) or "") == val and r.statut == pv.ACCEPTEE), None)
        if p is not None:
            out[cle] = p
    return out


def seed_lots(db, user, proj_by_key: dict) -> None:
    """Point d'entrée (demo_seed.ensure_demo) : le marché à plusieurs lots, son dossier lu en entier, son atelier.
    Une seule transaction : en cas d'échec, l'appelant annule tout (la vitrine garde ses autres marchés)."""
    from app.core.org import data_owner_id, member_ids
    from app.models import DossierPresentation, Project, ProjectStatus, utcnow
    from app.services import atelier as at
    from app.services import atelier_lots as al
    from app.services import demo_redaction as dr
    from app.services import faits_sources as fs
    from app.services.demo_seed import _COMPANY, _CRITERIA, _analysis, _date_limite
    base = _analysis(copy.deepcopy(DETAILS), "Restructuration d'une école maternelle en trois lots — couverture et "
                                              "étanchéité au cœur de votre métier : répondre aux lots 2 et 3 ensemble.",
                     "DEMO-26100517", ["Mémoire technique par lot (6 pages au plus)", "Décomposition du prix par lot",
                                       "Certificat Qualibat 3212"])
    contenu = dossier_zip()
    lecture = dr.lecture_dossier(DCE_NOM, contenu)
    a = analyse(lecture, _COMPANY, _CRITERIA, base)
    project = Project(user_id=user.id, name=NOM, client=CLIENT, budget=640000, status=ProjectStatus.en_cours,
                      source_url=a["source"]["source_url"], match_score=a.get("match_score"),
                      go_decision=a.get("go_decision"), ai_summary=a.get("summary"), ai_analysis=a,
                      deadline=_date_limite(a.get("details")))
    db.add(project)
    db.flush()
    proj_by_key[CLE] = project.id
    dr.ranger_lecture(project, contenu, lecture, prefixe=CLE, version=_VERSION)
    dr.ranger_document(db, user, project, contenu, nom=DCE_NOM, prefixe=CLE)
    mids = member_ids(user, db)
    at._oublier_lectures(at.cle_dossier_acheteur(db, project, mids))
    # L'atelier : lots repérés dans le règlement (sans IA), lots 2 et 3 choisis — comme at.creer_dossier, sans son
    # commit (tout le seed reste UNE transaction).
    owner = data_owner_id(user, db)
    lu = at.lire_dossier_acheteur(db, project, mids)
    reperes = at.lots_reperes(db, project, mids, lu=lu)
    lots = al.choisir(reperes.get("lots") or [], list(LOTS_CHOISIS))
    plan = at._plan(db, project, mids, lu, "auto", lots=lots)
    d = DossierPresentation(project_id=project.id, owner_id=owner, created_by_user_id=user.id,
                            plan_source=plan["source"], plan_meta=at._plan_meta(plan, "auto", lu.get("cle") or ""),
                            dce_lu=at.dce_lu_en_base(lu), analyse_debitee=False, regenerations=0,
                            regenerations_payantes=0, premieres_incluses=0,
                            options_export={"page_garde": True, "sommaire": True}, version=0)
    db.add(d)
    db.flush()
    for i, sp in enumerate(plan["sections"][:at.SECTIONS_MAX]):
        db.add(at._section_from_plan(d, sp, i))
    db.flush()
    preuves = preuves_par_cle(db, user.id)
    ctx = at.Contexte(db, project, owner, mids)
    acheteur = at.acheteur_du_marche(db, project, mids)
    fiches_ent = ctx.fiches(db)
    sections = at.sections_actives(db, d)
    for s in sections:
        partie = next((p for p in PARTIES if s.intitule.startswith(p["debut"]) and (s.lot or "") == p["lot"]), None)
        if partie is None:
            continue
        chunks = dr._extraits(db, user.id, {"extraits": partie["extraits"]})
        fiches = fiches_ent + fs.fiches_extraits(chunks)
        texte = fs.inserer_cv(dr._texte(partie, preuves), fiches)
        faits = fs.controler(texte, fiches, acheteur=acheteur, noms_entreprise=ctx.noms_entreprise,
                             section_entreprise=at.section_sur_l_entreprise(s), mode="ia", anciens=[], lots=ctx.lots)
        sources = [{"ref": c["ref"], "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
                    "extrait": c["text"][:240]} for c in chunks]
        v = at.ajouter_version(db, s, texte=texte, origine=at.IA, ia=True, sources=sources, faits=faits,
                               auteur_user_id=user.id)
        if partie["statut"] == "valide":
            s.statut = at.VALIDE
            s.validated_version_id, s.validated_hash = v.id, v.empreinte
            s.validated_at, s.validated_by = utcnow(), user.id
    d.analyse_debitee = True
    d.premieres_incluses = len(sections)
    db.flush()
    # L'entretien chantier du marché (questions de la banque, sans IA), quelques réponses fictives.
    from app.services.demo_entretien import seed_entretien
    seed_entretien(db, user, project, d, preuves)
    db.commit()
    logger.info("Vitrine démo : marché à plusieurs lots (%s) — %d parties, lots %s.", NOM, len(sections),
                ", ".join(LOTS_CHOISIS))


def empreinte() -> str:
    """Empreinte du dossier fictif (contrôle de rejouabilité : mêmes octets d'un démarrage à l'autre)."""
    return hashlib.sha256(dossier_zip()).hexdigest()
