"""
Compte de DÉMONSTRATION — la rédaction (vagues 1 à 3), sans IA ni réseau.

Depuis la fermeture de la démo publique (08/10/2026), la grille « Comment vous serez noté », la lecture
intégrale du dossier, « Mes preuves » et l'atelier du dossier de présentation sont arrivés : le compte démo
les montrait vides. seed_redaction(db, user, proj_by_key) les remplit sur le marché « toiture », avec
les VRAIS moteurs déterministes de l'application (aucun chiffre ni statut codé en dur) :

  1. le dossier du marché, FICTIF (règlement, cadre de mémoire, CCAP, CCTP, décomposition du prix), mis
     en PDF puis lu EN ENTIER par app/services/dce_lecture.py et rangé comme après un vrai import
     (« Dossier lu en entier : 5 pièces, N pages ») ; la grille « Comment vous serez noté » est construite
     et contrôlée par grille_notation (via analysis.finalize_analysis), le score par score_dce ;
  2. « Mes preuves » de Bâtiment de l'Ouest (app/services/preuves.py, seul point d'écriture) :
     références trouvées dans les documents, qualification avec justificatif, équipe (CV minimal, jamais
     remis à l'IA), matériel, chiffres clés, une estimation propre au marché et une fiche proposée ;
  3. l'atelier : plan tiré de la grille (app/services/atelier.py), textes FICTIFS écrits pour la démo avec
     leurs renvois ([F#] preuves, [S#] « Mon savoir-faire », [C#] chiffrage), CV insérés et faits contrôlés
     SANS IA exactement comme après une rédaction (faits_sources.inserer_cv puis controler, mode « ia »).
     Trois parties validées, une relue, une à finir : l'écran montre un dossier crédible et ce qui reste.

Tout est fictif et le dit : chaque page du dossier porte le bandeau BANDEAU ; l'acheteur n'y est jamais
nommé. Fichiers rangés sous des clés stables et liées au contenu (« demo/… ») : rien ne s'accumule dans
le stockage d'un redémarrage à l'autre. Appelé par demo_seed.ensure_demo dans sa propre transaction.
"""
import hashlib
import logging
import zipfile
from datetime import date, timedelta
from io import BytesIO

logger = logging.getLogger("adjugo")

BANDEAU = ("Dossier fictif de démonstration : l'acheteur, le marché et les chiffres ne correspondent à aucune "
           "consultation réelle.")
DCE_NOM = "DCE — Réfection toiture groupe scolaire Jean Moulin.zip"
_DOSSIER_ZIP = "DCE groupe scolaire Jean Moulin"
_VERSION = "3"            # à incrémenter si le texte du dossier change (nouvelles clés de stockage)

# ── 1. Le dossier du marché (fictif) ──────────────────────────────────────────────────────────────
# « ## » = intertitre. Une ligne par critère : la grille lit chaque ligne comme une ligne de tableau.

# Exigences de l'analyse (chiffre d'affaires minimum, qualifications, variantes), écrites mot pour mot dans
# le règlement : l'analyse les cite (details.exigences_sources) et la garde des citations les vérifie contre
# le dossier entier. Jamais une exigence affichée sans la phrase du dossier qui la porte.
EXIGENCE_CA = ("Le candidat justifie d'un chiffre d'affaires annuel moyen d'au moins 1 500 000 € HT sur les trois "
               "derniers exercices.")
JUSTIFICATION_CA = ("Ce niveau, supérieur au double du montant estimé, est justifié par les conditions d'exécution : "
                    "travaux en site occupé, concentrés sur les vacances scolaires.")
EXIGENCE_QUALIFICATIONS = ("Le candidat justifie d'une qualification Qualibat 3212 ou équivalente et de la mention "
                           "RGE.")
EXIGENCE_VARIANTES = "Les variantes sont autorisées sur les matériaux d'étanchéité."
# Rédaction, vague 5 (C2 complet) : ce que « Comment vous serez noté » repère sans IA dans ce règlement — la
# règle des candidatures multiples (R2142-21), une phrase sur l'intelligence artificielle (une exigence que le
# dossier déjà rédigé ne traite pas encore) et la date limite des questions.
PHRASE_CANDIDATURES = ("Un même opérateur économique ne peut pas présenter plusieurs offres en agissant à la fois en "
                       "qualité de candidat individuel et de membre d'un groupement.")
PHRASE_IA = "Le mémoire technique indique si le candidat a eu recours à un outil d'intelligence artificielle pour le rédiger."
PHRASE_QUESTIONS = "Les questions des candidats sont posées sur la plateforme au plus tard le 18 décembre 2026 à 12h00."

_RC = ("01 - Règlement de la consultation.pdf", "RÈGLEMENT DE LA CONSULTATION", [
    "Réfection de la toiture et de l'étanchéité du groupe scolaire Jean Moulin",
    "Marché public de travaux passé selon une procédure adaptée.",
    "## Article 1 — Objet de la consultation",
    "La consultation porte sur la réfection complète de la toiture et de l'étanchéité du groupe scolaire "
    "Jean Moulin : dépose de la couverture existante, isolation thermique, membrane d'étanchéité bicouche, "
    "zinguerie et évacuation des eaux pluviales. Le marché est passé en lot unique.",
    "## Article 2 — Conditions de participation",
    EXIGENCE_CA + " " + JUSTIFICATION_CA,
    EXIGENCE_QUALIFICATIONS,
    PHRASE_CANDIDATURES,
    "## Article 3 — Délai d'exécution",
    "Le délai d'exécution est de 5 mois à compter de l'ordre de service. Les travaux en toiture au droit des "
    "salles de classe sont réalisés pendant les vacances scolaires.",
    "## Article 4 — Visite du site",
    "La visite du site est recommandée. Elle se fait sur rendez-vous, avant le 15 décembre 2026.",
    "## Article 5 — Contenu de l'offre",
    "Chaque candidat remet l'acte d'engagement complété, la décomposition du prix global et forfaitaire et "
    "un mémoire technique.",
    "Le mémoire technique compte 12 pages au maximum, page de garde comprise, en police Arial de taille 11. "
    "Un cadre de mémoire technique est joint au dossier à titre indicatif.",
    PHRASE_IA,
    "## Article 6 — Variantes",
    EXIGENCE_VARIANTES,
    "## Article 7 — Jugement des offres",
    "Les offres sont jugées sur les critères pondérés suivants, dont le total fait 100 %.",
    "1.1 Méthodologie d'exécution des travaux de couverture et d'étanchéité : 25 %.",
    "1.2 Organisation du chantier en site occupé et sécurité : 15 %.",
    "1.3 Moyens humains et matériels affectés au chantier : 10 %.",
    "1.4 Planning d'exécution : 5 %.",
    "1.5 Gestion environnementale du chantier : 5 %.",
    "2. Prix des prestations : 40 %.",
    "Les sous-critères 1.1 à 1.5 forment la valeur technique, appréciée au vu du mémoire technique. Le prix "
    "est apprécié au vu de la décomposition du prix global et forfaitaire.",
    "## Article 8 — Clause sociale d'insertion",
    "Le titulaire réalise au moins 200 heures d'insertion sociale pendant l'exécution du marché.",
    "## Article 9 — Remise des offres",
    "Les offres sont remises par voie dématérialisée avant le 30 décembre 2026 à 12h00.",
    PHRASE_QUESTIONS,
])

_CADRE = ("02 - Cadre de mémoire technique.pdf", "CADRE DE MÉMOIRE TECHNIQUE", [
    "Ce cadre est fourni à titre indicatif. Le candidat peut présenter son mémoire dans un autre ordre.",
    "1. Méthodologie d'exécution",
    "1.1 Dépose de la couverture existante et préparation du support",
    "Décrivez les étapes de dépose, le contrôle du support et le traitement des déchets de dépose.",
    "1.2 Isolation et étanchéité",
    "Présentez le complexe d'isolation et d'étanchéité et le traitement des relevés et des points singuliers.",
    "2. Organisation du chantier en site occupé",
    "Présentez le phasage des travaux avec l'activité de l'école, les protections collectives et les accès.",
    "3. Moyens humains et matériels",
    "Présentez l'encadrement, les équipes et le matériel affectés au chantier.",
    "4. Planning d'exécution",
    "Joignez un planning par phase, calé sur les vacances scolaires.",
    "5. Gestion environnementale du chantier",
    "Décrivez le tri et la valorisation des déchets et les mesures de réduction des nuisances.",
])

_CCAP = ("03 - CCAP.pdf", "CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES", [
    "## Article 1 — Prix",
    "Le marché est traité à prix global et forfaitaire.",
    "## Article 2 — Avance et paiement",
    "Une avance de 10 % est versée au titulaire. Les sommes dues sont payées dans un délai de 30 jours.",
    "## Article 3 — Retenue de garantie",
    "Une retenue de garantie de 5 % est appliquée. Elle peut être remplacée par une garantie à première "
    "demande ou par une caution personnelle et solidaire.",
    "## Article 4 — Pénalités de retard",
    "En cas de retard, le titulaire subit une pénalité de 1/1000 du montant hors taxes du marché par jour de "
    "retard, plafonnée à 10 % de ce montant.",
    "## Article 5 — Sous-traitance",
    "La sous-traitance est autorisée. Chaque sous-traitant est déclaré au moyen du formulaire DC4.",
    "## Article 6 — Assurances",
    "Le titulaire justifie d'une assurance de responsabilité civile professionnelle et d'une garantie "
    "décennale couvrant les travaux d'étanchéité.",
])

_CCTP = ("04 - CCTP couverture et étanchéité.pdf", "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES", [
    "## Article 1 — Description des ouvrages",
    "La toiture du groupe scolaire couvre une surface de 1 850 m² répartie sur trois bâtiments reliés par "
    "des préaux. Le support est une dalle en béton.",
    "## Article 2 — Dépose",
    "La couverture existante est déposée par zones successives. Les déchets de dépose sont triés et évacués "
    "vers des filières agréées, avec bordereaux de suivi.",
    "## Article 3 — Isolation et étanchéité",
    "Le complexe comprend un pare-vapeur, un isolant thermique de résistance thermique au moins égale à 6 et "
    "une membrane d'étanchéité bicouche en bitume élastomère.",
    "Les relevés d'étanchéité ont une hauteur d'au moins 15 cm au-dessus de la protection.",
    "## Article 4 — Zinguerie et eaux pluviales",
    "Les naissances, descentes et trop-pleins sont remplacés. La zinguerie est réalisée en zinc naturel.",
    "## Article 5 — Sécurité et site occupé",
    "L'école reste en activité pendant les travaux. Les zones de travail sont séparées des cheminements des "
    "élèves. Des protections collectives sont posées en périphérie avant toute intervention en toiture.",
    "## Article 6 — Essais et réception",
    "Un essai d'étanchéité est réalisé avant la réception. Le titulaire remet le dossier des ouvrages "
    "exécutés à la réception.",
])

_DPGF = ("05 - Décomposition du prix global et forfaitaire.pdf", "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE", [
    "Le candidat complète chaque poste. Les montants sont exprimés en euros hors taxes.",
    "Poste 1 — Installation de chantier, sécurité et protections",
    "Poste 2 — Dépose de la couverture existante et évacuation des déchets",
    "Poste 3 — Isolation thermique et membrane d'étanchéité",
    "Poste 4 — Zinguerie, relevés et évacuations des eaux pluviales",
    "Poste 5 — Essais, levée des réserves et dossier des ouvrages exécutés",
    "Total hors taxes, TVA et total toutes taxes comprises.",
])

PIECES = (_RC, _CADRE, _CCAP, _CCTP, _DPGF)

# Critères « proposés par l'IA » (recopiés tels quels du règlement) : la grille les contrôle SANS IA.
CRITERES = [
    {"critere": "Méthodologie d'exécution des travaux de couverture et d'étanchéité", "ponderation": "25 %",
     "extrait": "1.1 Méthodologie d'exécution des travaux de couverture et d'étanchéité : 25 %."},
    {"critere": "Organisation du chantier en site occupé et sécurité", "ponderation": "15 %",
     "extrait": "1.2 Organisation du chantier en site occupé et sécurité : 15 %."},
    {"critere": "Moyens humains et matériels affectés au chantier", "ponderation": "10 %",
     "extrait": "1.3 Moyens humains et matériels affectés au chantier : 10 %."},
    {"critere": "Planning d'exécution", "ponderation": "5 %", "extrait": "1.4 Planning d'exécution : 5 %."},
    {"critere": "Gestion environnementale du chantier", "ponderation": "5 %",
     "extrait": "1.5 Gestion environnementale du chantier : 5 %."},
    {"critere": "Prix des prestations", "ponderation": "40 %", "extrait": "2. Prix des prestations : 40 %."},
]

# Question « proposée par l'IA » (recopiée du règlement, comme les critères) : la grille la contrôle SANS IA —
# phrase retrouvée mot pour mot, aucun nombre absent de cette phrase.
QUESTIONS_ACHETEUR = [
    {"question": "Le règlement demande d'indiquer le recours à un outil d'intelligence artificielle : faut-il le "
                 "préciser dans le mémoire technique lui-même, ou suffit-il d'une mention jointe à l'offre ?",
     "extraits": [PHRASE_IA]},
]


def _pdf(titre: str, paragraphes: list) -> bytes:
    """Une pièce en PDF texte (lisible sans OCR), le bandeau « fictif » en pied de chaque page. Octets
    STABLES d'un appel à l'autre (invariant) : la clé de stockage suit le contenu."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    c.setTitle(titre)
    c.setAuthor("")
    w, h = A4
    marge = 22 * mm
    larg = w - 2 * marge
    bas = 24 * mm
    y = [h - 26 * mm]

    def pied():
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColorRGB(0.42, 0.42, 0.42)
        c.drawString(marge, 13 * mm, BANDEAU)
        c.setFillColorRGB(0, 0, 0)

    def ligne(txt, police, taille, interligne):
        if y[0] < bas:
            pied()
            c.showPage()
            y[0] = h - 26 * mm
        c.setFont(police, taille)
        c.drawString(marge, y[0], txt)
        y[0] -= interligne

    for t in simpleSplit(titre, "Helvetica-Bold", 14, larg):
        ligne(t, "Helvetica-Bold", 14, 18)
    y[0] -= 6
    for p in paragraphes:
        inter = p.startswith("## ")
        txt = p[3:] if inter else p
        police, taille = ("Helvetica-Bold", 10.5) if inter else ("Helvetica", 10)
        if inter:
            y[0] -= 4
        for t in simpleSplit(txt, police, taille, larg):
            ligne(t, police, taille, 13.5)
        y[0] -= 4
    pied()
    c.showPage()
    c.save()
    return buf.getvalue()


def dossier_zip(pieces=None, dossier: str = None) -> bytes:
    """Le dossier du marché, en archive ZIP (dates fixes : octets stables). Par défaut celui du marché
    « toiture » ; `pieces` / `dossier` servent au dossier fictif du gymnase de Kerhel (demo_groupement)."""
    pieces = PIECES if pieces is None else pieces
    dossier = _DOSSIER_ZIP if dossier is None else dossier
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, titre, paras in pieces:
            zi = zipfile.ZipInfo(f"{dossier}/{nom}", date_time=(2026, 10, 1, 9, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, _pdf(titre, paras))
    return buf.getvalue()


def lecture_dossier(nom: str, contenu: bytes) -> dict:
    """La lecture INTÉGRALE d'un dossier, par le vrai moteur (sans IA, sans OCR : PDF texte)."""
    from app.services.dce_lecture import lire_dossier
    lecture = lire_dossier(nom, contenu, mode="direct")
    lecture["source_empreinte"] = hashlib.sha256(contenu).hexdigest()
    return lecture


def lecture_toiture(contenu: bytes) -> dict:
    """La lecture INTÉGRALE du dossier du marché « toiture »."""
    return lecture_dossier(DCE_NOM, contenu)


def analyse_toiture(base: dict, lecture: dict, company: dict, criteria: dict) -> dict:
    """L'analyse du marché « toiture » telle qu'après l'import de son dossier : l'extraction (rédigée pour
    la démo, critères recopiés du règlement) passe par le post-traitement DÉTERMINISTE de l'application
    (finalize_analysis : citations vérifiées contre le texte intégral, grille « Comment vous serez noté »,
    score et verdict), puis reçoit la couverture de la lecture — exactement comme analyse_dossier."""
    import copy
    from app.services import dce_lecture as lec
    from app.services.analysis import finalize_analysis
    texte, _meta = lec.texte_integral(lecture)
    mani = lec.manifeste(lecture)
    ext = copy.deepcopy(base)
    det = dict(ext.get("details") or {})
    det["criteres_attribution"] = copy.deepcopy(CRITERES)     # sous-critères tels qu'écrits au règlement
    det["questions_acheteur"] = copy.deepcopy(QUESTIONS_ACHETEUR)
    # Phrases exactes du règlement (comme l'extraction les rend) : vérifiées plus bas par la garde des
    # citations sur le texte intégral, elles s'affichent sous « Le dossier dit ».
    det["exigences_sources"] = {"ca_minimum_requis": EXIGENCE_CA,
                                "qualifications_requises": EXIGENCE_QUALIFICATIONS}
    ext["details"] = det
    out = finalize_analysis(ext, texte, company, criteria, mani["pieces"])
    for k in ("summary", "source", "pieces_requises", "lead_score"):
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


def _sauver_si_absent(storage, key: str, data: bytes, mime: str) -> None:
    try:
        storage.load(key)
        return
    except Exception:       # noqa: BLE001 — absent (ou illisible) : on le range
        pass
    storage.save(key, data, mime)


def ranger_lecture(project, contenu: bytes, lecture: dict, prefixe: str = "toiture",
                   version: str = None) -> str:
    """Le fichier du dossier et sa lecture intégrale rangés dans le stockage, sous des clés liées au
    contenu (relancer le seed ne crée aucun fichier), la lecture rattachée au marché
    (Project.dce_file_key). Renvoie la clé du fichier du dossier."""
    import gzip
    import json
    from app.services import dce_texte
    from app.services.storage import get_storage
    storage = get_storage()
    h = hashlib.sha256(contenu).hexdigest()[:16]
    zkey = f"demo/dce_{prefixe}_{h}.zip"
    _sauver_si_absent(storage, zkey, contenu, "application/zip")
    # Même format que dce_texte.sauver, sous une clé stable (sauver tire une clé neuve à chaque appel).
    lkey = f"demo/{dce_texte.FOLDER_KEY}/{prefixe}_{h}_{version or _VERSION}.json.gz"
    try:
        storage.load(lkey)
    except Exception:       # noqa: BLE001 — absente : on la range
        data = gzip.compress(json.dumps(dce_texte._payload(lecture), ensure_ascii=False).encode("utf-8"),
                             compresslevel=6)
        storage.save(lkey, data, "application/gzip")
    project.dce_file_key = lkey
    return zkey


def ranger_document(db, user, project, contenu: bytes, nom: str = None, prefixe: str = "toiture") -> None:
    """Le fichier du dossier dans le coffre du marché (dossier « DCE »), comme après un vrai import.
    Clé liée au contenu : le fichier est rangé une seule fois."""
    from app.models import DocCategory, Document
    from app.services.storage import get_storage
    h = hashlib.sha256(contenu).hexdigest()[:16]
    zkey = f"demo/dce_{prefixe}_{h}.zip"
    _sauver_si_absent(get_storage(), zkey, contenu, "application/zip")
    doc = (db.query(Document).filter(Document.user_id == user.id, Document.project_id == project.id,
                                     Document.folder == "DCE").order_by(Document.id.desc()).first())
    if doc is None:
        doc = Document(user_id=user.id, project_id=project.id, folder="DCE", category=DocCategory.autre)
        db.add(doc)
    doc.name = nom or DCE_NOM
    doc.file_key = zkey
    doc.file_size = len(contenu)
    doc.mime_type = "application/zip"
    db.flush()


def ranger_dossier(db, user, project, contenu: bytes, lecture: dict) -> None:
    """Le fichier du dossier dans le coffre du marché (dossier « DCE ») et sa lecture intégrale rangée
    (Project.dce_file_key), sous des clés liées au contenu : relancer le seed ne crée aucun fichier."""
    ranger_lecture(project, contenu, lecture)
    ranger_document(db, user, project, contenu)


# ── 2. « Mon savoir-faire » complété et « Mes preuves » ────────────────────────────────────────────

REFERENCES_DOC = "Liste de références — travaux similaires (2022-2025)"
REFERENCES_TEXTE = [
    "Réfection de la couverture de l'école élémentaire — Ville de Bréhaut — 2024 — 96 000 € HT — réalisé seul.",
    "Étanchéité-toiture du centre technique municipal — Ville de Lesparrac — 2023 — 182 000 € HT — réalisé seul.",
    "Rénovation thermique d'un groupe scolaire, lot couverture et isolation — Ville de Castelmorin — 2023 — "
    "145 000 € HT — en groupement conjoint.",
]


def _kb_refs(db, uid):
    """Ajoute à « Mon savoir-faire » la liste de références de l'entreprise (fictive), découpée en un
    passage par référence : les preuves « trouvé dans vos documents » s'y appuient."""
    from app.models import KnowledgeChunk, KnowledgeDoc
    full = "\n\n".join(REFERENCES_TEXTE)
    kd = KnowledgeDoc(user_id=uid, name=REFERENCES_DOC, kind="reference", text=full, char_count=len(full),
                      n_chunks=len(REFERENCES_TEXTE))
    db.add(kd)
    db.flush()
    for i, t in enumerate(REFERENCES_TEXTE):
        db.add(KnowledgeChunk(doc_id=kd.id, user_id=uid, ordinal=i, text=t, doc_name=REFERENCES_DOC))
    db.flush()
    return kd


def _doc_kb(db, uid, debut: str):
    from app.models import KnowledgeDoc
    return (db.query(KnowledgeDoc).filter(KnowledgeDoc.user_id == uid, KnowledgeDoc.name.like(debut + "%"))
            .order_by(KnowledgeDoc.id.desc()).first())


def _chunk(db, uid, doc, contient: str):
    from app.models import KnowledgeChunk
    if doc is None:
        return None
    for c in (db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id, KnowledgeChunk.user_id == uid)
              .order_by(KnowledgeChunk.ordinal).all()):
        if contient in (c.text or ""):
            return c
    return None


def seed_preuves(db, user, toiture_id) -> dict:
    """« Mes preuves » : chaque fiche passe par pv.creer / pv.proposer (contrôle du passage, champs,
    numéros). Renvoie {clé: Preuve} pour les renvois des textes de l'atelier. Numéros stables : toutes
    les preuves du compte démo sont effacées avant (effacer_tout), puis recréées dans le même ordre."""
    from app.models import Document
    from app.services import preuves as pv
    uid = user.id
    pv.effacer_tout(db, uid)
    db.flush()
    today = pv.aujourd_hui()
    refs = _kb_refs(db, uid)
    rse = _doc_kb(db, uid, "Politique RSE")
    out = {}

    def passage(doc, contient):
        c = _chunk(db, uid, doc, contient)
        return {"doc_id": doc.id, "passage": contient} if c is not None else None

    def creer(cle, nature, valeur, type_source=pv.DECLARE, source=None, **kw):
        if type_source == pv.DOCUMENTS and not source:
            type_source, source = pv.DECLARE, None       # document absent : déclaré par vous
        out[cle] = pv.creer(db, uid, nature=nature, valeur=valeur, type_source=type_source, source=source,
                            user=user, commit=False, **kw)

    creer("ref_brehaut", pv.REFERENCE,
          {"objet": "Réfection de la couverture de l'école élémentaire", "acheteur": "Ville de Bréhaut",
           "annee": 2024, "montant_ht": 96000, "role": "seul"},
          pv.DOCUMENTS, passage(refs, REFERENCES_TEXTE[0]), date_source=date(2025, 1, 15))
    creer("ref_lesparrac", pv.REFERENCE,
          {"objet": "Étanchéité-toiture du centre technique municipal", "acheteur": "Ville de Lesparrac",
           "annee": 2023, "montant_ht": 182000, "role": "seul"},
          pv.DOCUMENTS, passage(refs, REFERENCES_TEXTE[1]), date_source=date(2025, 1, 15))
    creer("ref_castelmorin", pv.REFERENCE,
          {"objet": "Rénovation thermique d'un groupe scolaire (lot couverture/isolation)",
           "acheteur": "Ville de Castelmorin", "annee": 2023, "montant_ht": 145000, "role": "groupement_conjoint"})
    qualibat = (db.query(Document).filter(Document.user_id == uid, Document.name.like("Certificat Qualibat%"),
                                          Document.deleted_at.is_(None)).first())
    q_fin = (qualibat.expiration_date if qualibat is not None and qualibat.expiration_date
             else today + timedelta(days=26))
    if qualibat is not None:
        creer("qualibat", pv.QUALIFICATION,
              {"nom": "Qualibat 3212", "organisme": "Qualibat", "detail": "Étanchéité de toiture par éléments"},
              pv.DOCUMENTS, {"document_id": qualibat.id}, date_fin_validite=q_fin)
    else:
        creer("qualibat", pv.QUALIFICATION,
              {"nom": "Qualibat 3212", "organisme": "Qualibat", "detail": "Étanchéité de toiture par éléments"},
              date_fin_validite=q_fin)
    rge = (db.query(Document).filter(Document.user_id == uid, Document.name.like("Attestation RGE%"),
                                     Document.deleted_at.is_(None)).first())
    r_fin = rge.expiration_date if rge is not None and rge.expiration_date else today + timedelta(days=240)
    creer("rge", pv.QUALIFICATION, {"nom": "RGE", "detail": "Reconnu garant de l'environnement"},
          pv.DOCUMENTS, {"document_id": rge.id} if rge is not None else None, date_fin_validite=r_fin)
    creer("conducteur", pv.SALARIE,
          {"nom": "Yann Tanguy", "fonction": "Conducteur de travaux", "experience_annees": 18,
           "diplomes": "BTS Bâtiment", "chantiers": "12 réfections de toitures scolaires"})
    creer("chef_equipe", pv.SALARIE,
          {"nom": "Erwan Le Bris", "fonction": "Chef d'équipe étanchéité", "experience_annees": 12,
           "diplomes": "BP Couverture", "chantiers": "Pose de membrane sur 20 000 m² de toitures-terrasses"})
    creer("qse", pv.SALARIE,
          {"nom": "Sophie Hénaff", "fonction": "Responsable QSE / RSE", "diplomes": "Diplôme d'ingénieur",
           "qualifications": "RGE", "chantiers": "Clauses d'insertion de 8 marchés publics"})
    creer("nacelles", pv.MATERIEL, {"designation": "Nacelle articulée de 16 m", "quantite": 2,
                                    "possession": "propriete"})
    creer("monte_materiaux", pv.MATERIEL, {"designation": "Monte-matériaux", "quantite": 1,
                                           "possession": "location"})
    creer("effectif", pv.CHIFFRE_CLE, {"libelle": "Effectif", "valeur": 14, "unite": "salariés", "annee": 2026})
    creer("insertion", pv.CHIFFRE_CLE,
          {"libelle": "Heures d'insertion réalisées", "valeur": 1040, "unite": "heures", "annee": 2025},
          pv.DOCUMENTS, passage(rse, "1 040 heures réalisées en 2025") if rse is not None else None,
          date_source=date(2026, 1, 10))
    if toiture_id:
        creer("compagnons", pv.CHIFFRE_CLE,
              {"libelle": "Compagnons sur le chantier au plus fort de l'activité", "valeur": 6,
               "unite": "compagnons"},
              pv.ESTIMATION, {"project_id": toiture_id, "detail": "Prévu pour ce marché"})
    # « Partir de vos anciens dossiers » : une fiche PROPOSÉE (à cocher par l'utilisateur).
    memoire = _doc_kb(db, uid, _MEMOIRE)
    pas = passage(memoire, "12 réfections de toitures scolaires conduites sur les 5 dernières années") \
        if memoire is not None else None
    if pas is not None:
        p, _creee = pv.proposer(db, uid, nature=pv.CHIFFRE_CLE,
                                valeur={"libelle": "Réfections de toitures scolaires", "valeur": 12,
                                        "unite": "réfections de toitures scolaires"},
                                type_source=pv.DOCUMENTS, source=pas, date_source=date(2024, 9, 2),
                                origine="import_document", user=user, commit=False)
        out["proposee"] = p
    db.flush()
    return out


# ── 3. L'atelier du dossier de présentation (déjà rédigé) ─────────────────────────────────────────
# Textes FICTIFS écrits pour la démo, dans la forme que rend le moteur de rédaction : un renvoi à la fin
# de chaque phrase qui s'appuie sur un fait ([F#] « Mes preuves », [S#] « Mon savoir-faire », [C#]
# chiffrage), « [CV F#] » seul sur sa ligne pour le CV d'une personne (inséré tel quel, sans IA). Les
# « {clé} » sont résolus vers les numéros RÉELS des preuves créées (clés de seed_preuves). Les faits sont
# ensuite contrôlés par faits_sources.controler, comme après une vraie rédaction.
# extraits : (renvoi, début du nom du document de « Mon savoir-faire », passage contenu dans le morceau).

_MEMOIRE = "Mémoire technique — Réfection toiture école de Bréhaut"
_RSE = "Politique RSE"

PARTIES = [
    {"critere_debut": "Méthodologie", "statut": "valide",
     "extraits": [("S1", _MEMOIRE, "Méthodologie d'étanchéité")],
     "texte": [
         "Bâtiment de l'Ouest conduit la réfection étape par étape : dépose soignée de la couverture existante, "
         "contrôle du support, pose d'un pare-vapeur et d'une isolation thermique, puis membrane d'étanchéité "
         "bicouche soudée [S1].",
         "Le CCTP prévoit un isolant de résistance thermique au moins égale à 6 et des relevés d'une hauteur d'au "
         "moins 15 cm.",
         "Les relevés et la zinguerie sont traités comme des points singuliers : chaque raccord est contrôlé "
         "avant la fermeture de la zone [S1].",
         "La couverture existante est déposée par zones successives, de façon à ne jamais laisser une salle de "
         "classe sans protection en fin de journée.",
         "Nous avons appliqué cette méthode à la réfection de la couverture de l'école élémentaire de la Ville "
         "de Bréhaut en 2024 {ref_brehaut} et à l'étanchéité-toiture du centre technique municipal de la Ville "
         "de Lesparrac en 2023 {ref_lesparrac}.",
         "L'entreprise est qualifiée Qualibat 3212 pour l'étanchéité de toiture par éléments {qualibat}.",
     ]},
    {"critere_debut": "Organisation", "statut": "brouillon",
     "extraits": [("S1", _MEMOIRE, "Sécurité et chantier en site occupé"), ("S2", _RSE, "Sécurité et conditions")],
     "texte": [
         "Le phasage suit l'activité de l'école : les zones situées au droit des salles de classe sont traitées "
         "pendant les vacances scolaires, les autres en dehors des heures d'entrée et de sortie des élèves.",
         "Avant toute intervention en toiture, nous posons des protections collectives en périphérie : "
         "garde-corps et filets [S1].",
         "Les zones de stockage et les accès du chantier sont séparés des cheminements des élèves par des "
         "clôtures pleines.",
         "Nous nous engageons à nettoyer les abords chaque soir et à évacuer les déchets en filière agréée [S1].",
         "Un point hebdomadaire avec la direction de l'école ajuste le phasage aux sorties scolaires et aux "
         "événements prévus.",
         "En 2025, l'entreprise n'a connu aucun accident avec arrêt [S2].",
     ]},
    {"critere_debut": "Moyens", "statut": "valide", "extraits": [],
     "texte": [
         "L'encadrement du chantier est confié à notre conducteur de travaux, qui compte 18 ans d'expérience "
         "{conducteur}.",
         "[CV {conducteur_n}]",
         "La pose de l'étanchéité est conduite par notre chef d'équipe étanchéité, qui compte 12 ans "
         "d'expérience {chef_equipe}.",
         "[CV {chef_equipe_n}]",
         "Notre responsable QSE suit la sécurité, la qualité et les clauses sociales du chantier {qse}.",
         "Au plus fort de l'activité, 6 compagnons travaillent sur le chantier {compagnons}.",
         "L'entreprise compte 14 salariés {effectif}.",
         "Nous disposons en propre de 2 nacelles articulées de 16 m {nacelles} et louons un monte-matériaux "
         "{monte_materiaux}.",
     ]},
    {"critere_debut": "Planning", "statut": "relu", "extraits": [],
     "texte": [
         "Selon le règlement de la consultation, le délai d'exécution est de 5 mois à compter de l'ordre de "
         "service.",
         "Notre estimation compte 12 jours de travail pour la préparation et l'installation de chantier [C1], "
         "60 jours de travail pour la dépose de la couverture existante [C3], 150 jours de travail pour "
         "l'isolation et l'étanchéité [C4] puis 45 jours de travail pour la zinguerie et l'évacuation des eaux "
         "pluviales [C5].",
         "Les essais d'étanchéité, la levée des réserves et la réception comptent 8 jours de travail [C6].",
         "Les travaux au droit des salles de classe sont regroupés sur 7 semaines pendant les vacances d'été.",
     ]},
    {"critere_debut": "Gestion environnementale", "statut": "valide",
     "extraits": [("S1", _MEMOIRE, "Engagements environnementaux"), ("S2", _RSE, "Démarche environnementale"),
                  ("S3", _RSE, "Insertion sociale")],
     "texte": [
         "Les déchets de chantier sont triés sur place et valorisés dans des filières adaptées [S1].",
         "Nous recourons à des isolants biosourcés lorsque le CCTP le permet [S1].",
         "Bâtiment de l'Ouest est une entreprise reconnue RGE {rge} et suit son bilan carbone chaque année [S2].",
         "Les tournées des véhicules sont optimisées pour limiter les trajets entre le dépôt et le chantier [S2].",
         "Le règlement demande au moins 200 heures d'insertion sociale pendant l'exécution du marché.",
         "Nous conventionnons pour cela une structure d'insertion par l'activité économique locale [S3].",
         "En 2025, nous avons réalisé 1 040 heures d'insertion sur nos marchés publics {insertion}.",
     ]},
]


def _texte(partie: dict, preuves: dict) -> str:
    """Le texte de la partie, renvois résolus vers les numéros réels des preuves ; une phrase dont la
    preuve manque (seed partiel) est retirée plutôt que de citer un renvoi inconnu."""
    vals = {}
    for k, p in preuves.items():
        vals[k] = f"[F{p.numero}]"
        vals[k + "_n"] = f"F{p.numero}"
    out = []
    for ph in partie["texte"]:
        try:
            out.append(ph.format(**vals))
        except KeyError:
            continue
    return "\n\n".join(out)


def _extraits(db, uid, partie: dict) -> list:
    """Les morceaux de « Mon savoir-faire » remis à la partie (forme de rag.retrieve_multi)."""
    out = []
    for ref, doc_debut, contient in partie["extraits"]:
        c = _chunk(db, uid, _doc_kb(db, uid, doc_debut), contient)
        if c is not None:
            out.append({"ref": ref, "chunk_id": c.id, "text": c.text or "", "doc_name": c.doc_name or ""})
    return out


def seed_atelier(db, user, project, preuves: dict):
    """Crée le dossier de présentation du marché (plan tiré de la grille) et une version « Rédigé avec
    Adjugo » par partie, contrôlée sans IA. Renvoie le dossier."""
    from app.core.org import data_owner_id, member_ids
    from app.models import DossierPresentation, utcnow
    from app.services import atelier as at
    from app.services import faits_sources as fs
    mids = member_ids(user, db)
    owner = data_owner_id(user, db)
    # Comme at.creer_dossier (même plan, mêmes champs), sans son commit : tout le seed reste UNE transaction.
    lu = at.lire_dossier_acheteur(db, project, mids)
    plan = at._plan(db, project, mids, lu, "auto")
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
    ctx = at.Contexte(db, project, owner, mids)
    acheteur = at.acheteur_du_marche(db, project, mids)
    fiches_ent = ctx.fiches(db)
    sections = at.sections_actives(db, d)
    for s in sections:
        partie = next((p for p in PARTIES if (s.critere or s.intitule).startswith(p["critere_debut"])), None)
        if partie is None:
            continue
        chunks = _extraits(db, user.id, partie)
        fiches = fiches_ent + fs.fiches_extraits(chunks)
        texte = fs.inserer_cv(_texte(partie, preuves), fiches)
        faits = fs.controler(texte, fiches, acheteur=acheteur, noms_entreprise=ctx.noms_entreprise,
                             section_entreprise=at.section_sur_l_entreprise(s), mode="ia", anciens=[])
        sources = [{"ref": c["ref"], "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
                    "extrait": c["text"][:240]} for c in chunks]
        v = at.ajouter_version(db, s, texte=texte, origine=at.IA, ia=True, sources=sources, faits=faits,
                               auteur_user_id=user.id)
        if partie["statut"] == "valide":
            s.statut = at.VALIDE
            s.validated_version_id, s.validated_hash = v.id, v.empreinte
            s.validated_at, s.validated_by = utcnow(), user.id
        elif partie["statut"] == "relu":
            s.statut = at.RELU
    # La première rédaction a compté pour 1 analyse (une fois pour tout le dossier, chaque partie comprise).
    d.analyse_debitee = True
    d.premieres_incluses = len(sections)
    db.flush()
    return d


def seed_redaction(db, user, proj_by_key: dict) -> None:
    """Point d'entrée (demo_seed.ensure_demo) : dossier du marché lu en entier, « Mes preuves », atelier.
    Une seule transaction : en cas d'échec, l'appelant annule tout (le marché garde l'analyse d'origine)."""
    from app.core.org import member_ids
    from app.models import Project
    from app.services.atelier import _oublier_lectures, cle_dossier_acheteur
    from app.services.demo_seed import _COMPANY, _CRITERIA
    pid = proj_by_key.get("toiture")
    project = db.get(Project, pid) if pid else None
    if project is None:
        return
    contenu = dossier_zip()
    lecture = lecture_toiture(contenu)
    analyse = analyse_toiture(project.ai_analysis or {}, lecture, _COMPANY, _CRITERIA)
    project.ai_analysis = analyse
    project.match_score = analyse.get("match_score")
    project.go_decision = analyse.get("go_decision")
    project.ai_summary = analyse.get("summary") or project.ai_summary
    ranger_dossier(db, user, project, contenu, lecture)
    _oublier_lectures(cle_dossier_acheteur(db, project, member_ids(user, db)))
    preuves = seed_preuves(db, user, project.id)
    seed_atelier(db, user, project, {k: p for k, p in preuves.items() if k != "proposee"})
    db.commit()
