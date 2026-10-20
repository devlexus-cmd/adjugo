"""
Adjugo - Checklist intelligente
Compare les pieces requises (extraites par l'IA) avec les documents du coffre-fort.
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User, Project, Document

router = APIRouter(prefix="/api/checklist", tags=["Checklist intelligente"])

SIGNATURE_AIDE = "À signer si le règlement l'exige ; sinon, signature à l'attribution."

# Pieces standards des marches publics.
# `help` = comment l'obtenir (passe d'« assistant » à « accompagnement »).
# `help_url` = source officielle. `required` peut être réévalué selon le marché
# (travaux → décennale, groupement → pouvoir) dans get_checklist().
PIECES_STANDARD = [
    {"id": "kbis", "name": "Extrait Kbis ou équivalent", "category": "administratif", "required": True,
     "help": "Extrait de moins de 3 mois : à commander en ligne sur MonIdenum ou Infogreffe.",
     "help_url": "https://www.infogreffe.fr/"},
    # Signature : exigée au dépôt SEULEMENT si le règlement de la consultation l'impose ; sinon
    # seul l'attributaire signe, à l'attribution (fiche DAJ « signature électronique », FT51).
    {"id": "dc1", "name": "DC1 - Lettre de candidature", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo, pré-rempli avec votre profil. " + SIGNATURE_AIDE},
    {"id": "dc2", "name": "DC2 - Déclaration du candidat", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo (CA, références, qualifications). À vérifier. " + SIGNATURE_AIDE},
    {"id": "honneur", "name": "Déclaration sur l'honneur (R2143-3)", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo. Pièce OBLIGATOIRE : son absence invalide le pli. " + SIGNATURE_AIDE},
    {"id": "attri1", "name": "ATTRI1 - Acte d'engagement", "category": "cerfa", "required": True,
     "help": ("Généré automatiquement par Adjugo à partir du chiffrage. Vérifiez le taux de TVA et le montant. "
              "Il se signe à l'attribution du marché, sauf si le règlement demande de le signer dès le dépôt.")},
    {"id": "attestation_fiscale", "name": "Attestation de régularité fiscale", "category": "fiscal", "required": True,
     "help": "À télécharger sur votre espace professionnel impots.gouv.fr (rubrique « Attestation fiscale »).",
     "help_url": "https://www.impots.gouv.fr/"},
    {"id": "attestation_sociale", "name": "Attestation de régularité sociale (URSSAF)", "category": "fiscal", "required": True,
     "help": "Attestation de vigilance à télécharger sur votre compte urssaf.fr (valable 6 mois).",
     "help_url": "https://www.urssaf.fr/"},
    {"id": "rc_pro", "name": "Attestation d'assurance RC professionnelle", "category": "assurances", "required": True,
     "help": "À demander à votre assureur (attestation de l'année en cours mentionnant l'activité)."},
    {"id": "rc_decennale", "name": "Attestation d'assurance décennale", "category": "assurances", "required": False,
     "help": "Obligatoire sur les marchés de TRAVAUX (bâtiment). À demander à votre assureur décennale."},
    {"id": "certif_qualibat", "name": "Certificat Qualibat / qualification", "category": "qualifications", "required": False,
     "help": "Certificat en cours de validité délivré par Qualibat/Qualifelec selon votre métier.",
     "help_url": "https://www.qualibat.com/"},
    {"id": "references", "name": "Liste des références / travaux similaires", "category": "administratif", "required": True,
     "help": ("Préparez la liste de vos travaux similaires (objet, client, année, montant) et déposez-la dans "
              "« Mes documents » : Adjugo ne la remplit pas à votre place.")},
    {"id": "moyens_humains", "name": "Déclaration des moyens humains", "category": "administratif", "required": False,
     "help": "Effectif, organigramme, CV des intervenants clés : souvent demandés dans le dossier de présentation."},
    {"id": "moyens_techniques", "name": "Déclaration des moyens techniques", "category": "administratif", "required": False,
     "help": "Matériel, équipements, moyens logistiques : à détailler dans le dossier de présentation."},
    {"id": "rib", "name": "Relevé d'identité bancaire (RIB)", "category": "administratif", "required": True,
     "help": "RIB au nom de l'entreprise, à télécharger depuis votre banque en ligne."},
    {"id": "pouvoir", "name": "Pouvoir du signataire", "category": "administratif", "required": False,
     "help": "Délégation de pouvoir si le signataire n'est pas le représentant légal. OBLIGATOIRE pour le chef de file d'un groupement."},
    {"id": "dc4", "name": "DC4 - Déclaration de sous-traitance", "category": "cerfa", "required": False,
     "help": "Généré par Adjugo si vous déclarez un sous-traitant. À compléter avec sa part du marché."},
    {"id": "memoire_technique", "name": "Dossier de présentation", "category": "technique", "required": True,
     # alias (jamais affiché) : les noms que le règlement donne à cette pièce, pour ne pas la proposer en double.
     "alias": "memoire technique offre technique note methodologique",
     "help": ("Préparé par Adjugo (Word et PDF, dans le dossier du marché) quand vous générez le dossier. "
              "À relire et compléter : c'est lui qui fait la note technique, et vous restez responsable de son contenu.")},
    {"id": "dpgf", "name": "Tableau de prix (bordereau ou décomposition des prix)", "category": "technique", "required": True,
     "alias": "dpgf bpu dqe dpu decomposition du prix global et forfaitaire bordereau des prix unitaires",
     "help": ("Adjugo fournit une estimation détaillée (PDF) depuis le chiffrage. Si le dossier du marché "
              "contient son propre tableau de prix, c'est lui qu'il faut remplir et déposer.")},
    {"id": "planning", "name": "Planning prévisionnel", "category": "technique", "required": False,
     "help": "Calendrier d'exécution (Gantt). Demandé sur les marchés de travaux et certaines prestations."},
]

CADRE_IMPOSE_NOTE = ("L'acheteur impose son propre cadre de réponse : recopiez-y ce texte, ne déposez pas le "
                     "fichier Word d'Adjugo seul.")

# Mots-clés détectant un marché de TRAVAUX (→ décennale + planning obligatoires).
_TRAVAUX_KW = ("travaux", "batiment", "bâtiment", "construction", "rénovation", "renovation",
               "réhabilitation", "rehabilitation", "voirie", "vrd", "btp", "chantier",
               "maçonnerie", "maconnerie", "gros œuvre", "gros oeuvre", "couverture",
               "charpente", "menuiserie", "génie civil", "genie civil", "démolition",
               "demolition", "terrassement", "isolation", "toiture", "plomberie", "électricité")


def _is_travaux(project) -> bool:
    """Heuristique : le marché relève-t-il des travaux ? (intitulé + analyse IA)."""
    hay = (project.name or "").lower()
    a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
    det = a.get("details", {}) if isinstance(a.get("details"), dict) else {}
    hay += " " + " ".join(str(det.get(k, "")) for k in ("intitule_marche", "objet", "domaine"))
    hay += " " + str(a.get("domaine", "")) + " " + str(a.get("secteur", ""))
    hay = hay.lower()
    return any(kw in hay for kw in _TRAVAUX_KW)


def _invitations_actives(project, db) -> list:
    """Invitations ACTIVES du marché (ni révoquées, ni déclinées) — source unique de vérité des membres."""
    try:
        from app.services.groupement_members import active_invites
        return active_invites(db, project.id)
    except Exception:
        return []


def _is_groupement(project, db, invites=None) -> bool:
    """Le marché est-il porté en groupement ? (au moins un partenaire invité). Relecture de la vague 2a : un
    sous-traitant n'est pas membre du groupement (il relève du DC4) ; inviter seulement un sous-traitant ne fait pas
    un groupement (ni pouvoir du chef de file, ni convention)."""
    from app.services.groupement_convention import _is_sous_traitant
    invites = _invitations_actives(project, db) if invites is None else invites
    return any(not _is_sous_traitant(getattr(i, "role", None)) for i in invites)


def _convention_item(project, db) -> dict:
    """Item « Convention de groupement validée » : ok seulement si TOUS les membres ont
    enregistré leur accord sur le texte à jour ; sinon « manquant » + ce qu'il reste à faire."""
    note, status = "À préparer : la convention de groupement, sur la page du marché.", "manquant"
    try:
        from app.services import groupement_convention as gc
        conv = gc.get_convention(db, project.id)
        if conv is not None:
            gc.refresh(db, project, conv)
            sigs = gc.signatures_of(db, conv)
            n_ok = sum(1 for s in sigs if s.status in ("signed", "hors_ligne"))
            if conv.status == "signee":
                status, note = "ok", f"Validée par tous les membres (version {conv.version})."
            elif conv.status == "a_signer":
                note = f"Générée : accords enregistrés {n_ok} sur {len(sigs)}. Relancez les membres qui n'ont pas validé."
            elif conv.status == "perimee":
                note = "Plus à jour (une part, un prix ou la composition a changé) : régénérez-la."
            else:
                note = "Brouillon : choisissez la forme du groupement puis générez la convention."
    except Exception:
        pass
    return {
        "id": "convention_groupement", "name": "Convention de groupement validée par tous les membres",
        "category": "groupement", "required": True, "from_ia": False,
        "help": ("Générée par Adjugo (carte « Convention et accords », page du marché) ; chaque membre la valide depuis "
                 "son espace. Modèle à faire relire par un conseil : ce n'est pas un conseil juridique."),
        "help_url": None, "context_note": note, "status": status,
        "document_name": None, "document_id": None, "expired": False,
    }


def _piece_name(ap) -> str:
    """Nom d'une pièce exigée (l'analyse donne une chaîne ou {"nom": …}) ; '' sinon."""
    if isinstance(ap, str):
        return ap.strip()
    if isinstance(ap, dict):
        return str(ap.get("nom") or "").strip()
    return ""


def pieces_requises(analysis) -> list:
    """Pièces exigées par le dossier. L'analyse les range dans `details.pieces_requises` ; les
    analyses plus anciennes (ou importées) les avaient à la racine : lues en repli. La clé peut
    valoir null (IA) : toujours une liste, jamais d'erreur."""
    if not isinstance(analysis, dict):
        return []
    det = analysis.get("details") if isinstance(analysis.get("details"), dict) else {}
    for src in (det.get("pieces_requises"), analysis.get("pieces_requises")):
        if isinstance(src, list) and src:
            return [p for p in src if _piece_name(p)]
    return []


def _norm(s: str) -> str:
    """Minuscule + sans accents : un document nommé « décennale » doit matcher le
    mot-clé « decennale ». Sans ça, l'accent casse silencieusement la détection."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Mots qui ne distinguent pas une pièce d'une autre (« Attestation de … », « Certificat … en cours de validité »).
_MOTS_VIDES = frozenset("""
a au aux avec ce ces d de des du en et l la le les ou par pour sa sans ses son sur un une votre vos
attestation attestations certificat certificats certification justificatif justificatifs document documents piece pieces
copie copies original obligatoire obligatoires exige exigee exiges exigees fourni fournie fournir signe signee cours validite
valide valable
""".split())


def _mots(texte) -> list:
    """Les mots d'un nom, sans accents ni casse, chiffres séparés des lettres (« iso27001 » → iso, 27001), sans le
    « s » du pluriel."""
    import re as _re
    out = []
    for m in _re.findall(r"[a-z]+|[0-9]+", _norm(texte)):
        out.append(m[:-1] if len(m) > 3 and m.endswith("s") and not m.isdigit() else m)
    return out


def _mots_significatifs(piece_name) -> list:
    return [m for m in _mots(piece_name) if len(m) > 1 and m not in _MOTS_VIDES]


def match_document(piece_name, documents):
    """Verifie si un document du coffre-fort correspond a la piece demandee.

    Deux façons de reconnaître un document : les mots-clés d'une pièce standard (« urssaf », « kbis »…), ou — pour
    toute pièce, d'abord celles que l'analyse lit dans le dossier (« Attestation de visite obligatoire »,
    « Certificat ISO 27001 ») — un nom qui porte TOUS les mots significatifs de la pièce (« Visite obligatoire »,
    « ISO 27001 », « iso27001 »). Relecture de la vague 2a : sans mot-clé, une pièce exigée n'était jamais reconnue,
    même sous son nom exact. Tous les mots, jamais un seul : « … régularité fiscale » ne reconnaît pas « … régularité
    sociale »."""
    piece_lower = _norm(piece_name)
    mots_piece = _mots_significatifs(piece_name)
    keywords = {
        "kbis": ["kbis", "extrait k", "registre commerce"],
        "dc1": ["dc1", "lettre de candidature"],
        "dc2": ["dc2", "declaration du candidat"],
        "dc4": ["dc4", "sous-traitance"],
        "attri1": ["attri1", "acte d'engagement", "acte engagement"],
        "attestation_fiscale": ["fiscal", "impot", "dgfip", "regularite fiscale"],
        "attestation_sociale": ["urssaf", "social", "cotisation", "regularite sociale"],
        "rc_pro": ["rc pro", "responsabilite civile", "assurance pro"],
        "rc_decennale": ["decennale", "garantie decennale"],
        "certif_qualibat": ["qualibat", "qualification", "certification", "qualif", "rge", "qualifelec"],
        "references": ["reference", "travaux similaires", "experience"],
        "moyens_humains": ["moyens humains", "effectif", "personnel", "organigramme"],
        "moyens_techniques": ["moyens techniques", "materiel", "equipement"],
        "rib": ["rib", "bancaire", "iban", "identite bancaire"],
        "pouvoir": ["pouvoir", "habilitation", "delegation"],
        # « memoire » seul : le fichier généré porte le nom du règlement (« Mémoire justificatif »…).
        "memoire_technique": ["memoire technique", "memoire", "offre technique", "methodologi",
                              "note technique", "dossier de presentation"],
        "dpgf": ["dpgf", "bordereau", "prix unitaire", "decomposition"],
        "planning": ["planning", "calendrier", "delai", "gantt"],
    }

    familles = [terms for key, terms in keywords.items() if key in piece_lower or any(t in piece_lower for t in terms)]
    fallback = None   # un document qui matche mais est expiré : gardé en repli seulement
    for doc in documents:
        doc_name = _norm(doc.name)
        doc_cat = _norm(getattr(doc.category, "value", doc.category))

        # Chercher par mots-cles, puis par les mots de la pièce (relecture de la vague 2a)
        trouve = any(any(t in doc_name or t in doc_cat for t in terms) for terms in familles)
        if not trouve and mots_piece:
            mots_doc = set(_mots(doc.name))
            trouve = all(m in mots_doc for m in mots_piece)
        if trouve:
            # Vraie date d'expiration (la colonne days_until_expiration n'existe PAS sur
            # le modèle → hasattr renvoyait toujours False → AUCUNE pièce jamais « périmée »).
            expired = (doc.expiration_date is not None and doc.expiration_date < date.today())
            hit = {"found": True, "document_id": doc.id,
                   "document_name": doc.name, "expired": expired}
            # Un document VALIDE prime : sinon une vieille version expirée masquait
            # une pièce à jour présente dans le coffre-fort (checklist « périmée » à tort).
            if not expired:
                return hit
            fallback = fallback or hit

    return fallback or {"found": False}


@router.get("/{project_id}")
def get_checklist(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ids = member_ids(current_user, db)
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(ids)
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")
    return checklist_du_marche(db, project, ids)


def checklist_du_marche(db: Session, project: Project, ids) -> dict:
    """La liste des pièces d'un marché, calculée pour l'organisation `ids` (ses comptes). Partagée par la route
    et par « Prêt à déposer » d'une entreprise seule (réorganisation, vague 2a, A2 : groupement_members) : une
    seule vérité, celle de la carte « Pièces à fournir »."""
    project_id = project.id
    # MÊME périmètre que l'export ZIP : documents de CE marché + pièces générales du coffre-fort
    # (project_id NULL), jamais ceux d'un AUTRE marché, ni corbeille ni versions remplacées —
    # sinon la checklist coche « ok » des pièces qui ne seront pas dans le pli de CE marché.
    documents = db.query(Document).filter(
        Document.user_id.in_(ids),
        Document.deleted_at.is_(None),
        Document.parent_id.is_(None),
        ((Document.project_id == project_id) | (Document.project_id.is_(None))),
    ).all()

    # L'ancienne archive brute du mémoire (« memoire_technique.md », texte avec renvois internes)
    # n'a jamais compté comme pièce déposable : elle ne la valide pas non plus aujourd'hui.
    documents = [d for d in documents if d.name != "memoire_technique.md"]

    # Construire la checklist
    checklist = []

    # Pièces exigées par le dossier (extraites par l'analyse), lues là où l'analyse les range.
    ai_pieces = pieces_requises(project.ai_analysis)

    # Contexte du marché : réévalue les pièces « conditionnelles » en obligatoires.
    is_travaux = _is_travaux(project)
    _invites = _invitations_actives(project, db)
    is_groupement = _is_groupement(project, db, _invites)
    contextual = {}
    if is_travaux:
        contextual["rc_decennale"] = "Marché de travaux : assurance décennale obligatoire."
        contextual["planning"] = "Marché de travaux : planning d'exécution généralement exigé."
    if is_groupement:
        contextual["pouvoir"] = "Groupement : pouvoir / habilitation du chef de file obligatoire."
        contextual["dc4"] = "Groupement avec sous-traitance : DC4 à prévoir le cas échéant."
    elif _invites:
        contextual["dc4"] = "Sous-traitant invité : DC4 à prévoir le cas échéant."
    # DPGF/BPU imposé par l'acheteur : si une trame figure dans les pièces requises du DCE,
    # il faut la compléter telle quelle — le modèle Adjugo ne sert alors que de chiffrage.
    _pieces_txt = " ".join(_piece_name(ap) for ap in ai_pieces).lower()
    if any(k in _pieces_txt for k in ("dpgf", "bordereau", "bpu", "décomposition", "decomposition")):
        contextual["dpgf"] = ("Tableau de prix imposé par l'acheteur (trouvé dans le dossier du marché) : "
                              "téléchargez-le et complétez-le, n'envoyez pas l'estimation d'Adjugo seule.")
    # Cadre de réponse imposé par le règlement (grille « Comment vous serez noté ») : le fichier
    # Word d'Adjugo ne se dépose pas seul.
    _det = (project.ai_analysis or {}).get("details") if isinstance(project.ai_analysis, dict) else None
    _gn = (_det or {}).get("grille_notation") if isinstance(_det, dict) else None
    _cadre_impose = isinstance(_gn, dict) and bool((_gn.get("contraintes") or {}).get("fichier_impose"))
    if _cadre_impose:
        contextual["memoire_technique"] = CADRE_IMPOSE_NOTE

    # Combiner pieces standard + pieces IA
    seen_ids = set()
    all_pieces = [dict(p) for p in PIECES_STANDARD]
    for p in all_pieces:
        if p["id"] in contextual:
            p["required"] = True
            p["context_note"] = contextual[p["id"]]

    # Le dossier de présentation porte le nom du règlement quand il y est retrouvé mot pour mot.
    from app.services.memoire_export import DEFAULT_LABEL, memoire_label, is_memoire_name
    _label = memoire_label(project.ai_analysis)
    for p in all_pieces:
        if p["id"] == "memoire_technique" and _label != DEFAULT_LABEL:
            p["name"] = f"Dossier de présentation ({_label[0].lower() + _label[1:]})"

    # Ajouter les pieces IA qui ne sont pas dans la liste standard
    for ap in ai_pieces:
        name = _piece_name(ap)
        # Le mémoire, sous quelque nom que ce soit (« Mémoire justificatif »…), EST la pièce
        # « Dossier de présentation » ci-dessus : pas de doublon.
        if is_memoire_name(name):
            continue
        # _norm (sans accents) : « Références » de l'IA dédoublonne bien « references »
        # standard — sinon la pièce apparaissait en double et faussait le % de complétion.
        if name and not any(_norm(name) in _norm(p["name"] + " " + p.get("alias", "")) for p in all_pieces):
            all_pieces.append({
                "id": "ia_" + str(len(all_pieces)),
                "name": name,
                "category": "ia",
                "required": True,
                "from_ia": True,
            })

    # Groupement : « convention de groupement validée par tous les membres » (vague 2). Statut
    # calculé depuis la convention réelle (jamais deviné) ; avertit, ne bloque rien.
    # Relecture de la vague 2a : seulement pour un marché qui a un groupement (un partenaire invité, ou une convention
    # qui compte des membres) — une convention restée en brouillon sans partenaire n'en fait pas un (a_un_groupement).
    try:
        from app.services.groupement_convention import get_convention as _gconv
        from app.services.groupement_members import a_un_groupement
        _a_grp = a_un_groupement(_invites, _gconv(db, project.id))
    except Exception:
        _a_grp = is_groupement
    convention_item = _convention_item(project, db) if _a_grp else None

    for piece in all_pieces:
        match = match_document(piece["name"], documents)
        item = {
            "id": piece["id"],
            "name": piece["name"],
            "category": piece.get("category", "autre"),
            "required": piece.get("required", False),
            "from_ia": piece.get("from_ia", False),
            "help": piece.get("help"),
            "help_url": piece.get("help_url"),
            "context_note": piece.get("context_note"),
            "status": "ok" if match["found"] else "manquant",
            "document_name": match.get("document_name"),
            "document_id": match.get("document_id"),
            "expired": match.get("expired", False),
        }

        if item["expired"]:
            item["status"] = "expire"

        # Dossier de présentation préparé par Adjugo mais encore troué ou coupé : il n'est PAS
        # « disponible » (jamais de « prêt » sur un texte incomplet).
        if piece["id"] == "memoire_technique" and item["status"] == "ok":
            _dp = (project.workflow or {}).get("dossier_presentation") if isinstance(project.workflow, dict) else None
            if isinstance(_dp, dict) and item["document_name"] in (_dp.get("fichiers") or []):
                n_todo = int(_dp.get("a_completer") or 0) - (1 if _dp.get("coupe") else 0)
                if _dp.get("coupe") or n_todo > 0:
                    item["status"] = "a_completer"
                    parts = []
                    if _dp.get("coupe"):
                        parts.append("texte coupé avant la fin")
                    if n_todo > 0:
                        parts.append(f"{n_todo} passage{'s' if n_todo > 1 else ''} « À compléter »")
                    n_hl = n_todo + (1 if _dp.get("coupe") else 0)    # mentions surlignées dans le fichier
                    item["context_note"] = ("Préparé par Adjugo, à terminer avant le dépôt : " + " et ".join(parts)
                                            + (" (passages surlignés dans le fichier Word et le PDF)." if n_hl > 1
                                               else " (passage surligné dans le fichier Word et le PDF).")
                                            + (" " + CADRE_IMPOSE_NOTE if _cadre_impose else ""))

        # Les CERFA sont toujours "ok" car generables
        if piece["category"] == "cerfa":
            item["status"] = "generable"

        checklist.append(item)

    if convention_item:
        checklist.append(convention_item)

    # Stats
    total = len(checklist)
    ok = len([c for c in checklist if c["status"] in ("ok", "generable")])
    manquant = len([c for c in checklist if c["status"] == "manquant"])
    expire = len([c for c in checklist if c["status"] == "expire"])
    a_completer = len([c for c in checklist if c["status"] == "a_completer"])

    return {
        "project_id": project_id,
        "project_name": project.name,
        "context": {"travaux": is_travaux, "groupement": is_groupement},
        "checklist": checklist,
        "stats": {
            "total": total,
            "ok": ok,
            "manquant": manquant,
            "expire": expire,
            "a_completer": a_completer,
            "completion": round(ok / total * 100) if total > 0 else 0,
        }
    }
