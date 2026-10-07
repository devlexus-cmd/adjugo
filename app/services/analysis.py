"""
Adjugo - Service d'analyse IA des DCE
Prompt expert marches publics francais.
Utilise le profil entreprise + criteres Go/No-Go pour un matching precis.
"""
import json
import re
import unicodedata
from app.core.config import get_settings
from app.services.llm import client  # client Anthropic LAZY partagé (pas d'instanciation à l'import)

settings = get_settings()

# Termes des clauses sensibles : souvent dans le CCAP, en fin de DCE — on garantit
# qu'elles sont vues par l'analyse même dans un dossier de plusieurs centaines de pages.
# Étendu (co-traitance v2) aux clauses de GROUPEMENT (forme conjoint/solidaire, mandataire,
# appréciation des capacités en groupement, références, effectif) : sans ça, la clause
# « chaque membre doit satisfaire individuellement » page 140 du RC n'entrait jamais dans
# la fenêtre du LLM → exigence invisible → score de groupement faussement optimiste.
_RISK_TERMS = re.compile(
    r"p[ée]nalit|retenue de garantie|garantie [aà] premi[èe]re demande|cautionnement|"
    r"avance|d[ée]lai d'ex[ée]cution|d[ée]lai de remise|crit[èe]res? d['e]|pond[ée]ration|"
    r"notation|valeur technique|prix|reconduction|tranche|variante|sous-trait|"
    r"assurance|qualification|certificat|RGE|capacit[ée]|chiffre d'affaires|"
    r"groupement|conjoint|solidaire|mandataire|co-?traitan|r[ée]f[ée]rences?|effectif",
    re.IGNORECASE,
)


# ── Garde anti-hallucination des CITATIONS du DCE ─────────────────────────────────────
# Le LLM « recopie » des phrases du DCE (CA exigé, forme de groupement imposée…). Une
# phrase reformulée ou inventée serait affichée comme une citation → mensonge au client.
# Règle : un extrait n'est conservé QUE s'il est une sous-chaîne du texte intégral (après
# normalisation tolérante : casse, accents, espaces, apostrophes). Sinon '' (jamais affiché).

_QUOTE_CHARS = "«»\"“”„‘’'"


def _norm_citation(s) -> str:
    """Forme normalisée pour la comparaison : minuscules, accents retirés (NFKD), apostrophes
    typographiques → ', suites d'espaces/retours → un espace. Ne lève jamais."""
    try:
        t = unicodedata.normalize("NFKD", str(s or ""))
        t = "".join(c for c in t if not unicodedata.combining(c))
        t = t.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
        t = t.replace("“", '"').replace("”", '"').replace("„", '"')
        t = t.replace(" ", " ").replace(" ", " ")
        t = re.sub(r"\s+", " ", t.lower()).strip()
        return t
    except Exception:
        return ""


def citation_guard(text_integral: str, extrait: str, min_len: int = 12) -> str:
    """Renvoie l'extrait d'ORIGINE (trim, sans guillemets d'encadrement, ≤ 400 caractères)
    s'il est RÉELLEMENT une sous-chaîne du texte intégral du DCE (comparaison normalisée :
    casse, accents, espaces multiples, apostrophes typographiques tolérés) ET s'il fait au
    moins `min_len` caractères utiles ; sinon ''. Jamais d'exception."""
    try:
        ex = str(extrait or "").strip()
        # Tolérance : l'IA encadre souvent sa citation de guillemets « » ou "" → retirés.
        ex = ex.strip(_QUOTE_CHARS + " \t\r\n")
        if not ex:
            return ""
        ex = ex[:400].strip()
        nx = _norm_citation(ex)
        if len(nx) < max(1, int(min_len)):
            return ""
        nt = _norm_citation(text_integral)
        if not nt or nx not in nt:
            return ""
        return ex
    except Exception:
        return ""


# Exigences dont le DCE doit être CITÉ (clé → présente dans details.exigences_sources).
_EXIGENCE_KEYS = ("ca_minimum_requis", "qualifications_requises", "references_requises",
                  "effectif_minimum_requis", "capacites_groupement")
_FORMES_GROUPEMENT = ("non_specifie", "libre", "conjoint", "solidaire")
_NON_SPECIFIE = "Non specifie dans le DCE"


def _normalize_exigences(details: dict, text_integral: str) -> dict:
    """Post-traitement DÉTERMINISTE des exigences de groupement extraites par l'IA :
    - chaque citation (exigences_sources.*, forme_groupement.extrait) passe par citation_guard
      sur le texte INTÉGRAL (pas la fenêtre envoyée au LLM) → '' si non vérifiable ;
    - exigences_sources : toujours un dict des 5 clés (str) ;
    - forme_groupement : toujours {"imposee": l'une des 4 valeurs, "extrait": str} ;
    - capacites_groupement / references_requises / effectif_minimum_requis absents → non spécifié ;
    - details["exigences_verifiees"] = {clé: bool(extrait non vide après garde)}.
    Ne lève jamais (données LLM sales → valeurs neutres)."""
    if not isinstance(details, dict):
        return {}
    try:
        raw_src = details.get("exigences_sources")
        raw_src = raw_src if isinstance(raw_src, dict) else {}
        sources = {}
        for k in _EXIGENCE_KEYS:
            v = raw_src.get(k)
            if isinstance(v, (list, tuple)):
                v = " ".join(str(x) for x in v if x)
            elif isinstance(v, dict):
                v = v.get("extrait") or v.get("texte") or ""
            sources[k] = citation_guard(text_integral, v)
        details["exigences_sources"] = sources

        fg = details.get("forme_groupement")
        if isinstance(fg, str):                     # l'IA a parfois renvoyé « conjoint » tout court
            fg = {"imposee": fg, "extrait": ""}
        fg = fg if isinstance(fg, dict) else {}
        imposee = _norm_citation(fg.get("imposee")).replace(" ", "_").replace("-", "_")
        if imposee not in _FORMES_GROUPEMENT:
            imposee = "non_specifie"
        fg_extrait = fg.get("extrait")
        if isinstance(fg_extrait, (list, tuple)):
            fg_extrait = " ".join(str(x) for x in fg_extrait if x)
        details["forme_groupement"] = {"imposee": imposee,
                                       "extrait": citation_guard(text_integral, fg_extrait)}

        for k in ("capacites_groupement", "references_requises", "effectif_minimum_requis"):
            v = details.get(k)
            if isinstance(v, (list, tuple)):
                v = "; ".join(str(x) for x in v if x)
            if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, (dict, bool)):
                details[k] = _NON_SPECIFIE
            else:
                details[k] = str(v).strip()

        verifiees = {k: bool(sources.get(k)) for k in _EXIGENCE_KEYS}
        verifiees["forme_groupement"] = bool(details["forme_groupement"]["extrait"])
        details["exigences_verifiees"] = verifiees
    except Exception:
        details.setdefault("exigences_sources", {k: "" for k in _EXIGENCE_KEYS})
        details.setdefault("forme_groupement", {"imposee": "non_specifie", "extrait": ""})
        details.setdefault("exigences_verifiees", {k: False for k in _EXIGENCE_KEYS + ("forme_groupement",)})
    return details


def select_dce_content(text: str, head: int = 9000, budget: int = 30000, window: int = 700) -> str:
    """
    Sélection pertinente du DCE plutôt qu'une troncature aveugle des N premiers caractères.

    On conserve toujours la tête du dossier (objet, acheteur, contexte) puis, dans tout
    le reste du document, on extrait des fenêtres autour des CLAUSES SENSIBLES (pénalités,
    retenue de garantie, critères de pondération, délais…) où qu'elles se trouvent. Ainsi
    une clause de pénalité située page 180 d'un CCAP est bien analysée — ce qu'une coupe à
    15 000 caractères manquait systématiquement. Budget borné pour la fenêtre de contexte.
    """
    text = text or ""
    if len(text) <= budget:
        return text
    head_part = text[:head]
    rest = text[head:]
    # Repère les fenêtres autour de chaque occurrence de terme sensible.
    spans = []
    for m in _RISK_TERMS.finditer(rest):
        a = max(0, m.start() - window // 3)
        b = min(len(rest), m.end() + window)
        if spans and a <= spans[-1][1] + 120:   # fusionne les fenêtres proches
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    picked, used = [], 0
    room = budget - head
    for a, b in spans:
        if used >= room:
            break
        seg = rest[a:b]
        if used + len(seg) > room:
            seg = seg[: room - used]
        picked.append(seg)
        used += len(seg)
    if not picked:
        # Aucune clause sensible repérée : on reprend une coupe simple jusqu'au budget.
        return text[:budget]
    return head_part + "\n\n[… extraits ciblés des clauses sensibles, ailleurs dans le DCE …]\n\n" + \
        "\n[…]\n".join(picked)

SYSTEM_PROMPT = """Tu es un expert en marches publics francais, specialise dans l'analyse des Dossiers de Consultation des Entreprises (DCE). Tu travailles pour un logiciel appele Adjugo qui aide les entreprises du BTP et des services a repondre aux appels d'offres.

Ton role est d'analyser le DCE fourni et de produire une analyse structuree et actionnable.

Tu dois TOUJOURS repondre en JSON valide, sans texte avant ou apres. Voici le format exact attendu :

{
  "match_score": 75,
  "go_decision": "go",
  "summary": "Resume en 3-4 phrases de l'appel d'offres...",
  "details": {
    "intitule_marche": "Nom exact du marche",
    "acheteur": "Nom de l'acheteur / pouvoir adjudicateur",
    "contact": {"nom": "Nom de la personne a contacter pour les questions (si indique)", "fonction": "Fonction / service", "email": "Email de contact", "telephone": "Telephone"},
    "type_marche": "Travaux / Services / Fournitures",
    "nature_marche": "Marche a procedure adaptee (MAPA) / Appel d'offres ouvert / etc.",
    "forme_prix": "Prix global et forfaitaire / Prix unitaires / Mixte",
    "budget_estime": "150 000 EUR HT",
    "date_limite": "15/06/2026 a 12h00",
    "delai_execution": "6 mois a compter de l'ordre de service",
    "lieu_execution": "Quimper (29)",
    "allotissement": "Lot unique / Lot 1 : Gros oeuvre, Lot 2 : Electricite...",
    "criteres_attribution": [
      {"critere": "Prix", "ponderation": "60%"},
      {"critere": "Valeur technique", "ponderation": "40%"}
    ],
    "garanties_exigees": "Garantie a premiere demande 5% / Retenue de garantie 5%",
    "penalites": "1/1000 du montant HT par jour de retard, plafonnees a 10%",
    "avance": "Avance de 10% si marche > 50 000 EUR",
    "sous_traitance": "Autorisee / Interdite / Limitee a 30%",
    "variantes": "Autorisees / Non autorisees",
    "critere_rse": "Oui - clause d'insertion sociale / Non",
    "ca_minimum_requis": "CA > 300 000 EUR sur 3 ans / Non specifie",
    "qualifications_requises": ["Qualibat 1312", "RGE"],
    "references_requises": "ex. 3 references de travaux similaires sur 5 ans / Non specifie dans le DCE",
    "effectif_minimum_requis": "ex. 10 salaries / Non specifie dans le DCE",
    "capacites_groupement": "cumul admis / chaque membre doit satisfaire individuellement / mandataire seul / Non specifie dans le DCE",
    "forme_groupement": {"imposee": "non_specifie | libre | conjoint | solidaire", "extrait": "phrase litterale du DCE ou vide"},
    "exigences_sources": {"ca_minimum_requis": "phrase litterale du DCE ou vide", "qualifications_requises": "", "references_requises": "", "effectif_minimum_requis": "", "capacites_groupement": ""},
    "assurances_requises": ["RC Professionnelle", "Decennale"],
    "visite_obligatoire": "Oui, le 01/06/2026 a 14h / Non",
    "pieces_requises": [
      {"nom": "DC1 - Lettre de candidature", "disponible": true},
      {"nom": "DC2 - Declaration du candidat", "disponible": true},
      {"nom": "Kbis de moins de 3 mois", "disponible": false},
      {"nom": "Attestation URSSAF", "disponible": false},
      {"nom": "Attestation fiscale", "disponible": false},
      {"nom": "Attestation assurance RC Pro", "disponible": false},
      {"nom": "Attestation assurance decennale", "disponible": false},
      {"nom": "Memoire technique", "disponible": false},
      {"nom": "DPGF / Bordereau des prix", "disponible": false},
      {"nom": "Planning previsionnel", "disponible": false},
      {"nom": "Certificat Qualibat", "disponible": false},
      {"nom": "References de travaux similaires", "disponible": false}
    ],
    "points_attention": [
      "Delai tres court - 6 mois pour un chantier complexe",
      "Penalites elevees - 1/1000 par jour",
      "Visite obligatoire le 01/06"
    ],
    "recommandation": "Analyse redigee en 3 a 4 paragraphes (180 a 350 mots), separes par une ligne vide : (1) de quoi parle le marche et ce qu'il exige, (2) les attentes de l'acheteur et la mecanique d'attribution, (3) les points techniques et administratifs a maitriser et les clauses a negocier, (4) la strategie et la recommandation finale",
    "clauses_risque": [
      {"clause": "Penalites de retard", "niveau": "eleve", "pourquoi": "1/1000 du HT par jour plafonnees a 10%, au-dela du seuil tolere par l'entreprise", "levier_negociation": "Demander un plafond a 5% et une franchise de 5 jours ouvres"},
      {"clause": "Retenue de garantie", "niveau": "moyen", "pourquoi": "Retenue de 5% sur 1 an immobilise la tresorerie", "levier_negociation": "Proposer une caution bancaire de substitution (art. R2191-33)"}
    ]
  }
}

Regles importantes :
- "match_score" est un entier entre 0 et 100
- "go_decision" est "go", "no_go" ou "a_etudier"
- Pour les pieces_requises, "disponible" est true pour les CERFA (DC1, DC2, DC4, ATTRI1) car le logiciel les genere automatiquement, et false pour le reste
- Les "points_attention" sont les elements de risque ou les contraintes particulieres
- La "recommandation" est une ANALYSE REDIGEE et substantielle, PAS un resume d'une phrase : 3 a 4 paragraphes, entre 180 et 350 mots (jamais moins de 180), separes par une ligne vide (double saut de ligne \n\n). Structure attendue : (1) de quoi parle le marche et ce qu'il demande concretement ; (2) les attentes de l'acheteur et la mecanique d'attribution (poids des criteres, ce qui fait gagner) ; (3) les points techniques et administratifs a maitriser + les clauses a negocier ; (4) la strategie et la recommandation finale (y aller ou non, comment, seul ou en groupement). Reste factuel et fonde UNIQUEMENT sur le DCE fourni — n'invente jamais un chiffre, une exigence ou une echeance. Sur une simple annonce (pas de DCE complet), reste plus prudent mais redige quand meme une analyse structuree de ce qui est connu.
- "clauses_risque" liste les clauses contractuelles a surveiller : penalites, retenue de garantie, garantie a premiere demande, avance, delais d'execution intenables, revision de prix figee, assurances exigees, criteres financiers (CA mini). Pour CHAQUE clause notable :
  * "niveau" vaut "faible", "moyen" ou "eleve"
  * Tu DOIS comparer aux seuils de l'entreprise fournis dans les criteres (penalites max, garantie max, retenue max, avance min, delai de reponse min) : marque "eleve" des qu'un seuil est depasse, et dis-le explicitement dans "pourquoi"
  * "levier_negociation" propose une contre-proposition concrete et actionnable (article du CCP si pertinent)
  * Renvoie une liste vide [] si aucune clause notable, n'invente jamais
- Pour "contact" : n'extrais le nom/email/telephone QUE s'ils figurent dans le DCE (souvent dans le reglement de consultation, rubrique "renseignements"). Si rien n'est indique, laisse les champs vides "" — n'invente JAMAIS de contact.
- Exigences de candidature et de GROUPEMENT ("ca_minimum_requis", "qualifications_requises", "references_requises", "effectif_minimum_requis", "capacites_groupement", "forme_groupement") : n'extrais QUE si c'est ecrit dans le DCE, sinon "Non specifie dans le DCE". "capacites_groupement" dit comment les capacites sont appreciees quand plusieurs entreprises repondent ensemble : "cumul admis" (les capacites des membres s'additionnent), "chaque membre doit satisfaire individuellement", "mandataire seul", ou "Non specifie dans le DCE". "forme_groupement.imposee" vaut "conjoint" ou "solidaire" UNIQUEMENT si le reglement impose cette forme, "libre" s'il laisse le choix, "non_specifie" sinon.
- Pour CHAQUE extrait ("exigences_sources".*, "forme_groupement.extrait") : recopie LITTERALEMENT la phrase du DCE (300 caracteres maximum), sans reformuler, sans resumer, sans corriger. Laisse "" si l'information n'est pas dans le DCE. Un extrait qui n'est pas une copie exacte du DCE sera rejete.
- Si une information n'est pas dans le DCE, indique "Non specifie dans le DCE"
- Extrais TOUTES les pieces demandees dans le reglement de consultation"""


def build_user_prompt(text, company=None, criteria=None, lang_name=None):
    """Construit le prompt utilisateur avec le contexte entreprise."""
    prompt = "Analyse le DCE suivant et produis l'analyse JSON.\n\n"

    if company:
        prompt += "=== PROFIL DE L'ENTREPRISE CANDIDATE ===\n"
        if company.get("name"):
            prompt += f"Denomination : {company['name']}\n"
        if company.get("siret"):
            prompt += f"SIRET : {company['siret']}\n"
        if company.get("code_ape"):
            prompt += f"Code APE : {company['code_ape']}\n"
        if company.get("forme_juridique"):
            prompt += f"Forme juridique : {company['forme_juridique']}\n"
        if company.get("city"):
            prompt += f"Ville : {company['city']}\n"
        if company.get("ca_n1"):
            prompt += f"CA N-1 : {company['ca_n1']:,.0f} EUR\n"
        if company.get("ca_n2"):
            prompt += f"CA N-2 : {company['ca_n2']:,.0f} EUR\n"
        if company.get("ca_n3"):
            prompt += f"CA N-3 : {company['ca_n3']:,.0f} EUR\n"
        if company.get("effectif"):
            prompt += f"Effectif : {company['effectif']} salaries\n"
        prompt += "\n"

    if criteria:
        prompt += "=== CRITERES GO/NO-GO DE L'ENTREPRISE ===\n"
        if criteria.get("budget_min"):
            prompt += f"Budget minimum acceptable : {criteria['budget_min']:,.0f} EUR\n"
        if criteria.get("budget_max"):
            prompt += f"Budget maximum acceptable : {criteria['budget_max']:,.0f} EUR\n"
        if criteria.get("max_distance_km"):
            prompt += f"Distance max : {criteria['max_distance_km']} km\n"
        if criteria.get("penalty_max"):
            prompt += f"Penalites de retard max acceptables : {criteria['penalty_max']}%\n"
        if criteria.get("garantie_max"):
            prompt += f"Garantie a premiere demande max acceptable : {criteria['garantie_max']}%\n"
        if criteria.get("retenue_garantie_max"):
            prompt += f"Retenue de garantie max acceptable : {criteria['retenue_garantie_max']}%\n"
        if criteria.get("avance_min"):
            prompt += f"Avance minimale souhaitee : {criteria['avance_min']}%\n"
        if criteria.get("delai_reponse_min"):
            prompt += f"Delai de remise minimal acceptable : {criteria['delai_reponse_min']} jours\n"
        if criteria.get("go_threshold"):
            prompt += f"Seuil Go : score >= {criteria['go_threshold']}%\n"
        if criteria.get("nogo_threshold"):
            prompt += f"Seuil No-Go : score < {criteria['nogo_threshold']}%\n"
        if criteria.get("excluded_keywords"):
            prompt += f"Mots-cles a exclure : {criteria['excluded_keywords']}\n"
        prompt += "\n"
        prompt += "Utilise ces criteres pour ajuster le match_score et la go_decision.\n"
        prompt += "Si le budget du marche est hors des limites, penalise le score.\n"
        prompt += "Si le lieu d'execution est trop loin, penalise le score.\n"
        prompt += "Compare IMPERATIVEMENT penalites/retenue de garantie/garantie/avance/delai du DCE a ces "
        prompt += "seuils et renseigne le tableau clauses_risque (niveau eleve si un seuil est depasse).\n\n"

    if lang_name and lang_name.lower() != "français":
        prompt += (f"=== LANGUE DE SORTIE ===\nRédige TOUTES les valeurs textuelles "
                   f"(summary, recommandation, points_attention, details.*, clauses_risque : "
                   f"clause/pourquoi/levier_negociation) en {lang_name}. Conserve les CLÉS JSON "
                   f"et les énumérations en l'état (go_decision: go/no_go/a_etudier ; "
                   f"niveau: faible/moyen/eleve).\n\n")

    prompt += "=== CONTENU DU DCE ===\n"
    selected = select_dce_content(text)
    prompt += selected
    if len(selected) < len(text):
        prompt += ("\n\n[... DCE volumineux : tête du dossier + extraits ciblés des clauses "
                   "sensibles (pénalités, garanties, critères, délais) sélectionnés dans "
                   "l'ensemble du document. Analyse sur la base de ces éléments.]")

    return prompt


def extract_text_from_pdf(file_bytes):
    """Extrait le texte d'un PDF."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
        return text.strip()
    except Exception as e:
        return f"Erreur extraction PDF : {str(e)}"


def _ocr_pdf(content: bytes, max_pages: int = 15) -> str:
    """OCR de repli pour les DCE SCANNÉS (PDF image, fréquents chez les petites
    collectivités). Gracieux : retourne '' si l'OCR n'est pas disponible (binaire
    tesseract/poppler absent) — le code appelant retombe alors sur l'erreur claire."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception:
        return ""
    try:
        images = convert_from_bytes(content, dpi=200)
    except Exception:
        return ""
    out = []
    for img in images[:max_pages]:
        try:
            out.append(pytesseract.image_to_string(img, lang="fra"))
        except Exception:
            try:
                out.append(pytesseract.image_to_string(img))   # repli langue par défaut
            except Exception:
                pass
    return "\n\n".join(t for t in out if t).strip()


def _extract_docx(data: bytes) -> str:
    """Extrait le texte d'un .docx (Word), tableaux compris. Gracieux si python-docx absent."""
    try:
        import io
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text]
        for tbl in d.tables:
            for row in tbl.rows:
                cells = [c.text for c in row.cells if c.text]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_dce_text(filename: str, content: bytes, max_chars: int = 40000) -> str:
    """
    Extrait le texte d'un DCE réel : PDF unique OU archive ZIP de plusieurs PDF.
    Lève ValueError avec un message clair si illisible/vide/non supporté.
    """
    import io, os, zipfile
    name = (filename or "").lower()

    if name.endswith(".pdf") or content[:5] == b"%PDF-":
        txt = extract_text_from_pdf(content)
        if not txt or txt.startswith("Erreur") or len(txt) < 30:
            # PDF sans couche texte → tentative OCR (document scanné).
            ocr = _ocr_pdf(content)
            if ocr and len(ocr) >= 30:
                return ocr[:max_chars]
            raise ValueError("PDF illisible (document scanné/protégé ?) ou vide. "
                             "Si c'est un scan, l'OCR n'a rien pu extraire.")
        return txt[:max_chars]

    if name.endswith(".docx"):   # AVANT le ZIP : un .docx est aussi une archive PK
        t = _extract_docx(content)
        if t and len(t) >= 20:
            return t[:max_chars]
        raise ValueError("Document Word illisible ou vide. Exportez-le en PDF si le souci persiste.")

    if name.endswith((".txt", ".md", ".csv")):
        t = content.decode("utf-8", errors="replace").strip()
        if t:
            return t[:max_chars]
        raise ValueError("Fichier texte vide ou illisible.")

    if name.endswith(".zip") or content[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except Exception:
            raise ValueError("Archive ZIP corrompue ou illisible.")
        parts, files_done = [], 0
        _OKEXT = (".pdf", ".docx", ".txt", ".md", ".csv")
        # PDF d'abord (le cœur du DCE), puis Word/texte ; triés par nom
        names = sorted(zf.namelist(), key=lambda n: (not n.lower().endswith(".pdf"), n.lower()))
        for n in names:
            ln = n.lower()
            if n.endswith("/") or os.path.basename(n).startswith("."):
                continue
            if not ln.endswith(_OKEXT):
                continue
            try:
                data = zf.read(n)
                if ln.endswith(".pdf"):
                    t = extract_text_from_pdf(data)
                    if not (t and not t.startswith("Erreur") and len(t) > 30):
                        t = _ocr_pdf(data)   # PDF scanné dans l'archive → OCR de repli
                elif ln.endswith(".docx"):
                    t = _extract_docx(data)
                else:
                    t = data.decode("utf-8", errors="replace")
                if t and not t.startswith("Erreur") and len(t) > 30:
                    parts.append(f"=== {os.path.basename(n)} ===\n{t}")
                    files_done += 1
            except Exception:
                continue
            if sum(len(p) for p in parts) > max_chars or files_done >= 25:
                break
        if not parts:
            raise ValueError("Aucun fichier exploitable dans l'archive (PDF scanné ou format non géré ?).")
        return "\n\n".join(parts)[:max_chars]

    raise ValueError("Format non supporté. Importez le dossier en PDF, Word (.docx), texte ou archive ZIP.")


def _detect_groupement(details: dict, company: dict = None) -> dict:
    """Détecte si le marché est une OPPORTUNITÉ DE GROUPEMENT (répondre à plusieurs),
    de façon DÉTERMINISTE à partir des faits extraits — jamais inventé :
    (a) marché alloti, (b) qualification exigée que l'entreprise n'affiche pas,
    (c) CA minimum requis supérieur au CA de l'entreprise."""
    import re
    company = company or {}
    raisons = []
    allot = str(details.get("allotissement") or "").lower()
    # Détecte l'allotissement sous ses formulations courantes : énumération « Lot 1… Lot 2… »
    # MAIS aussi « 3 lots », « marché alloti en 4 lots », etc. (les sorties LLM réelles).
    n = re.search(r"\b(\d+)\s+lots?\b", allot)
    multi = (n and int(n.group(1)) >= 2) or allot.count("lot ") >= 2 or "lot 2" in allot
    if "lot unique" in allot and allot.count("lot ") < 2:
        multi = False
    if multi:
        raisons.append("Marché alloti : vous pouvez répondre à plusieurs, un partenaire par lot.")
    reqs = details.get("qualifications_requises") or []
    own_q = str(company.get("qualifications") or "").lower()
    if isinstance(reqs, list) and own_q:
        manquantes = [q for q in reqs if isinstance(q, str) and q.strip()
                      and not any(t for t in re.split(r"[\s/]+", q.lower()) if len(t) > 2 and t in own_q)]
        if manquantes:
            raisons.append("Qualification(s) exigée(s) que vous n'affichez pas ("
                           + ", ".join(manquantes[:3]) + ") — un partenaire peut les apporter.")
    cam = str(details.get("ca_minimum_requis") or "")
    m = re.search(r"(\d[\d\s  .]{3,})", cam)
    req_ca = int(re.sub(r"\D", "", m.group(1))) if m else 0
    ca = company.get("ca_n1") or 0
    if req_ca and ca and req_ca > ca:
        raisons.append("CA minimum exigé supérieur au vôtre — un groupement additionne les capacités.")
    # Exigences de groupement (copie brute des faits extraits) : c'est le routeur qui calcule
    # le score de groupement (app.services.groupement_scoring) — ici on ne fait que transmettre.
    fg = details.get("forme_groupement")
    if not isinstance(fg, dict):
        fg = {"imposee": str(fg or "non_specifie"), "extrait": ""} if fg else \
             {"imposee": "non_specifie", "extrait": ""}
    exigences = {
        "ca_minimum_requis": details.get("ca_minimum_requis") or "",
        "qualifications_requises": reqs if isinstance(reqs, list) else ([reqs] if reqs else []),
        "references_requises": details.get("references_requises") or "Non specifie dans le DCE",
        "effectif_minimum_requis": details.get("effectif_minimum_requis") or "Non specifie dans le DCE",
        "capacites_groupement": details.get("capacites_groupement") or "Non specifie dans le DCE",
        "forme_groupement": fg,
    }
    return {"recommande": bool(raisons), "raisons": raisons[:3], "exigences": exigences}


def analyze_dce_text(text, company=None, criteria=None, lang_name=None):
    """Analyse un DCE depuis du texte brut (notice BOAMP, DCE déjà extrait...).
    lang_name : langue de rédaction des valeurs textuelles (adaptation par pays)."""
    if not text or len(text) < 50:
        return {
            "match_score": 0,
            "go_decision": "a_etudier",
            "summary": "Contenu insuffisant pour une analyse fiable.",
            "details": {}
        }

    # Construire le prompt
    user_prompt = build_user_prompt(text, company, criteria, lang_name)

    try:
        from app.services.llm import messages_create
        response = messages_create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            temperature=0,  # extraction reproductible (le score, lui, est déterministe)
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extraire le JSON de la reponse
        response_text = response.content[0].text.strip()

        # Nettoyer le JSON si necessaire
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Réponse « bavarde » (texte autour du JSON) : on repêche le premier objet JSON
            # complet plutôt que de jeter une analyse déjà payée par le client.
            start = response_text.find("{")
            if start < 0:
                raise
            result, _ = json.JSONDecoder().raw_decode(response_text[start:])

        # Valider les champs obligatoires
        if "match_score" not in result:
            result["match_score"] = 50
        if "go_decision" not in result:
            result["go_decision"] = "a_etudier"
        if "summary" not in result:
            result["summary"] = "Analyse terminee."
        if "details" not in result or not isinstance(result.get("details"), dict):
            result["details"] = {}

        # GARDE ANTI-HALLUCINATION des citations : chaque extrait « recopié » par l'IA est
        # vérifié contre le texte INTÉGRAL du DCE (pas la fenêtre envoyée au LLM) ; un extrait
        # non retrouvé devient '' (jamais affiché). Exigences de groupement normalisées.
        _normalize_exigences(result["details"], text)

        # SCORE GO/NO-GO DÉTERMINISTE : l'IA a EXTRAIT les faits ci-dessus ; le score est
        # recalculé par un barème ouvert et reproductible (jamais laissé au LLM).
        from app.services.dce_scoring import score_dce
        det = score_dce(result.get("details") or {}, company, criteria)
        result["match_score"] = det["score"]
        result["go_decision"] = det["go_decision"]
        result["score_breakdown"] = det["breakdown"]
        result["score_deterministe"] = True
        # Auto-flag « opportunité de groupement » (déterministe, n'altère pas le score)
        result["groupement"] = _detect_groupement(result.get("details") or {}, company)
        return result

    except json.JSONDecodeError:
        # Le LLM a bien RÉPONDU mais dans un format illisible : verdict NEUTRE honnête
        # (« à étudier »), jamais un faux NO-GO.
        return {
            "match_score": 50,
            "go_decision": "a_etudier",
            "summary": response_text[:500] if response_text else "Erreur de format dans la reponse IA.",
            "details": {}
        }
    except Exception:
        # PANNE de l'IA (timeout, coupure réseau, 5xx/429 du fournisseur, plafond de tokens,
        # disjoncteur ouvert…) : on NE fabrique JAMAIS un verdict — un faux « NO-GO » serait
        # mensonger ET débiterait le client pour rien. On PROPAGE : les appelants (sourcing)
        # remboursent le quota (refund_analysis) et renvoient un 503 « réessayez ». Avant, seul
        # LLMUnavailable remontait ; une vraie erreur SDK (avant l'ouverture du disjoncteur à
        # 5 échecs) retournait un faux NO-GO facturé — c'est ce trou qu'on ferme ici.
        raise
