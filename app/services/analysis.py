"""
Adjugo - Service d'analyse IA des DCE
Prompt expert marches publics francais.
Utilise le profil entreprise + criteres Go/No-Go pour un matching precis.
"""
import json
import re
from app.core.config import get_settings
from app.services.llm import client  # client Anthropic LAZY partagé (pas d'instanciation à l'import)

settings = get_settings()

# Termes des clauses sensibles : souvent dans le CCAP, en fin de DCE — on garantit
# qu'elles sont vues par l'analyse même dans un dossier de plusieurs centaines de pages.
_RISK_TERMS = re.compile(
    r"p[ée]nalit|retenue de garantie|garantie [aà] premi[èe]re demande|cautionnement|"
    r"avance|d[ée]lai d'ex[ée]cution|d[ée]lai de remise|crit[èe]res? d['e]|pond[ée]ration|"
    r"notation|valeur technique|prix|reconduction|tranche|variante|sous-trait|"
    r"assurance|qualification|certificat|RGE|capacit[ée]|chiffre d'affaires",
    re.IGNORECASE,
)


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
    "recommandation": "Recommandation detaillee sur la strategie a adopter...",
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
- La "recommandation" est un conseil strategique concret (300 caracteres max)
- "clauses_risque" liste les clauses contractuelles a surveiller : penalites, retenue de garantie, garantie a premiere demande, avance, delais d'execution intenables, revision de prix figee, assurances exigees, criteres financiers (CA mini). Pour CHAQUE clause notable :
  * "niveau" vaut "faible", "moyen" ou "eleve"
  * Tu DOIS comparer aux seuils de l'entreprise fournis dans les criteres (penalites max, garantie max, retenue max, avance min, delai de reponse min) : marque "eleve" des qu'un seuil est depasse, et dis-le explicitement dans "pourquoi"
  * "levier_negociation" propose une contre-proposition concrete et actionnable (article du CCP si pertinent)
  * Renvoie une liste vide [] si aucune clause notable, n'invente jamais
- Pour "contact" : n'extrais le nom/email/telephone QUE s'ils figurent dans le DCE (souvent dans le reglement de consultation, rubrique "renseignements"). Si rien n'est indique, laisse les champs vides "" — n'invente JAMAIS de contact.
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
            raise ValueError("PDF illisible (document scanné/protégé ?) ou vide.")
        return txt[:max_chars]

    if name.endswith(".zip") or content[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except Exception:
            raise ValueError("Archive ZIP corrompue ou illisible.")
        parts, files_done = [], 0
        # PDF d'abord (le cœur du DCE), triés par nom
        names = sorted(zf.namelist(), key=lambda n: (not n.lower().endswith(".pdf"), n.lower()))
        for n in names:
            if n.endswith("/") or os.path.basename(n).startswith("."):
                continue
            if not n.lower().endswith(".pdf"):
                continue
            try:
                data = zf.read(n)
                t = extract_text_from_pdf(data)
                if t and not t.startswith("Erreur") and len(t) > 30:
                    parts.append(f"=== {os.path.basename(n)} ===\n{t}")
                    files_done += 1
            except Exception:
                continue
            if sum(len(p) for p in parts) > max_chars or files_done >= 12:
                break
        if not parts:
            raise ValueError("Aucun PDF exploitable dans l'archive (DCE scanné ou autres formats ?).")
        return "\n\n".join(parts)[:max_chars]

    raise ValueError("Format non supporté. Importez le DCE en PDF ou en archive ZIP.")


def analyze_dce(file_bytes, company=None, criteria=None):
    """Analyse un DCE (PDF) avec Claude."""
    text = extract_text_from_pdf(file_bytes)

    if not text or len(text) < 50:
        return {
            "match_score": 0,
            "go_decision": "no_go",
            "summary": "Impossible d'extraire le texte du PDF. Le document est peut-etre scanne ou protege.",
            "details": {}
        }
    return analyze_dce_text(text, company, criteria)


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

        result = json.loads(response_text)

        # Valider les champs obligatoires
        if "match_score" not in result:
            result["match_score"] = 50
        if "go_decision" not in result:
            result["go_decision"] = "a_etudier"
        if "summary" not in result:
            result["summary"] = "Analyse terminee."
        if "details" not in result:
            result["details"] = {}

        # SCORE GO/NO-GO DÉTERMINISTE : l'IA a EXTRAIT les faits ci-dessus ; le score est
        # recalculé par un barème ouvert et reproductible (jamais laissé au LLM).
        from app.services.dce_scoring import score_dce
        det = score_dce(result.get("details") or {}, company, criteria)
        result["match_score"] = det["score"]
        result["go_decision"] = det["go_decision"]
        result["score_breakdown"] = det["breakdown"]
        result["score_deterministe"] = True
        return result

    except json.JSONDecodeError:
        return {
            "match_score": 50,
            "go_decision": "a_etudier",
            "summary": response_text[:500] if response_text else "Erreur de format dans la reponse IA.",
            "details": {}
        }
    except Exception as e:
        return {
            "match_score": 0,
            "go_decision": "no_go",
            "summary": f"Erreur d'analyse : {str(e)}",
            "details": {}
        }
