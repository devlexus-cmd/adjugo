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


# Ce que l'IA reçoit EN ENTIER (règlement + cadre de réponse), et le budget minimal laissé aux
# fenêtres ciblées sur les autres pièces. Borne haute de l'entrée ≈ 84 000 caractères.
SELECT_PRIORITY_MAX = 60000
SELECT_REST_MIN = 24000


def select_dce_content(text: str, head: int = 9000, budget: int = 30000, window: int = 700) -> str:
    """
    Sélection pertinente du DCE plutôt qu'une troncature aveugle des N premiers caractères.

    Dossier assemblé pièce par pièce (« === nom === », cf. extract_dce_text) : le règlement de
    la consultation et le cadre de réponse, reconnus sans IA, sont remis EN ENTIER (dans la
    limite de SELECT_PRIORITY_MAX), puis chaque autre pièce reçoit des fenêtres ciblées
    autour des clauses sensibles, avec un budget partagé équitablement.

    Texte d'un seul tenant sans règlement reconnu : comportement historique — tête du dossier
    (objet, acheteur, contexte) puis fenêtres autour des CLAUSES SENSIBLES (pénalités, retenue
    de garantie, critères de pondération, délais…) où qu'elles se trouvent. Ainsi une clause de
    pénalité située page 180 d'un CCAP est bien analysée. Budget borné pour la fenêtre de contexte.
    """
    text = text or ""
    if len(text) <= budget:
        return text
    try:
        out = _select_by_piece(text, head, budget, window)
        if out:
            return out
    except Exception:
        pass
    return _select_windows(text, head, budget, window)


def _select_by_piece(text: str, head: int, budget: int, window: int) -> str:
    """Sélection pièce par pièce ; '' si aucun règlement ni cadre n'est reconnu (repli)."""
    from app.services import dce_pieces as _dp
    pieces = _dp.typed_pieces(text)
    prio = [p for p in pieces if p["type"] in _dp.PRIORITAIRES]
    if not prio:
        return ""
    rest = [p for p in pieces if p["type"] not in _dp.PRIORITAIRES]
    alloc = _dp.water_fill([len(p["texte"]) for p in prio], SELECT_PRIORITY_MAX)
    out, overflow = [], []
    for p, n in zip(prio, alloc):
        body = p["texte"].strip("\n")
        complet = n >= len(p["texte"])
        out.append(f"=== {p['nom'] or 'dossier'} : {p['libelle'].lower()}, "
                   f"{'lu en entier' if complet else 'début'} ===\n{body[:n]}")
        if not complet:
            overflow.append(dict(p, texte=p["texte"][n:], libelle=p["libelle"] + " (suite)"))
    rest = overflow + rest
    used = sum(len(x) for x in out)
    rest_budget = max(SELECT_REST_MIN, budget - used)
    rest = [p for p in rest if p["texte"].strip()]
    if rest:
        shares = _dp.water_fill([len(p["texte"]) for p in rest], rest_budget)
        picked = []
        for p, share in zip(rest, shares):
            if share <= 0:
                continue
            body = p["texte"]
            if len(body) > share:
                body = _select_windows(body, head=min(head, max(500, share // 4)), budget=share, window=window)
                tag = "extraits ciblés"
            else:
                tag = "lu en entier"
            picked.append(f"=== {p['nom'] or 'dossier'} : {p['libelle'].lower()}, {tag} ===\n{body.strip()}")
        if picked:
            out.append("[… autres pièces du dossier : extraits ciblés des clauses sensibles "
                       "(pénalités, garanties, critères, délais) …]")
            out.extend(picked)
    return "\n\n".join(out)


def _select_windows(text: str, head: int = 9000, budget: int = 30000, window: int = 700) -> str:
    """Tête + fenêtres autour des clauses sensibles (sélection historique, d'un seul tenant)."""
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
      {"critere": "Prix", "ponderation": "60 %", "extrait": "ligne ou phrase litterale du reglement qui cite ce critere et son poids"},
      {"critere": "Valeur technique", "ponderation": "40 %", "extrait": "ligne ou phrase litterale du reglement"}
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
- "criteres_attribution" : les criteres de jugement des OFFRES ecrits dans le reglement de la consultation (criteres principaux seulement, pas les sous-criteres), dans l'ORDRE ou le reglement les cite. "ponderation" : le poids TEL QU'ECRIT dans le reglement ("60 %", "40 points"...), ou "" si le reglement ne donne pas de poids. N'invente JAMAIS de poids ni d'ordre d'importance. "extrait" : recopie LITTERALEMENT la ligne ou la phrase du reglement qui cite ce critere (avec son poids s'il existe), 300 caracteres maximum, sans reformuler ; "" si tu ne la trouves pas. Un extrait qui n'est pas une copie exacte du DCE sera rejete.
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
        prompt += ("\n\n[... DCE volumineux : règlement de la consultation et cadre de réponse "
                   "remis en entier quand ils sont reconnus (sinon tête du dossier), puis extraits "
                   "ciblés des clauses sensibles (pénalités, garanties, critères, délais) dans les "
                   "autres pièces. Analyse sur la base de ces éléments.]")

    return prompt


# ── Extraction de texte BORNÉE (anti-bombe de décompression / PDF géant) ─────────
# Process unique (1 worker sans Redis) : un seul fichier piégé ne doit jamais pouvoir
# épuiser la mémoire ou le CPU pour tous les clients. Tout est donc plafonné AVANT lecture :
#   • ZIP : chaque fichier lu en flux borné (jamais zf.read sans limite), budget cumulé
#     sur l'archive entière, ZIP imbriqué accepté sur 1 seul niveau, nombre d'entrées borné ;
#   • DOCX (archive elle aussi) : tailles décompressées vérifiées avant python-docx ;
#   • PDF : nombre de pages lues borné + arrêt dès que le volume de texte utile est atteint ;
#   • OCR : seules les premières pages sont RENDUES (pas toutes puis tronquées), page par
#     page, résolution réduite pour les formats géants, budget de pages partagé dans un ZIP.
# Un vrai DCE (RC + CCAP + CCTP + DPGF + plans, ~30 Mo zippés) reste très en dessous.
_MB = 1024 * 1024
ZIP_MEMBER_MAX_BYTES = 40 * _MB      # un fichier de l'archive, une fois décompressé
ZIP_TOTAL_MAX_BYTES = 160 * _MB      # cumul décompressé lu dans toute l'archive
ZIP_MAX_ENTRIES = 2000               # entrées déclarées (un DCE en compte quelques dizaines)
ZIP_MAX_DEPTH = 1                    # ZIP dans le ZIP : oui ; ZIP dans un ZIP dans un ZIP : non
ZIP_MAX_FILES = 25                   # fichiers réellement exploités (inchangé)
DOCX_PART_MAX_BYTES = 40 * _MB       # une partie d'un .docx (image, XML…) décompressée
DOCX_XML_MAX_BYTES = 25 * _MB        # une partie XML (document.xml…) décompressée
DOCX_XML_TOTAL_MAX_BYTES = 40 * _MB  # tout le XML parsé par python-docx
DOCX_TOTAL_MAX_BYTES = 120 * _MB     # cumul décompressé d'un .docx
PDF_MAX_PAGES = 600                  # pages dont on extrait la couche texte
PDF_TIME_BUDGET_S = 25.0             # temps CPU max d'extraction texte par dossier (archive comprise)
PDF_PAGE_TIME_S = 6.0                # tranche de temps max pour UNE page (interrompue en cours)
PDF_PAGE_CONTENT_MAX_BYTES = 2 * _MB # contenu décompressé d'une page (flux + formulaires) ;
                                     # une page de texte pèse quelques Ko, l'analyse ≈ 1 s/Mo
PDF_DOC_CONTENT_MAX_BYTES = 12 * _MB # cumul décompressé sur un dossier (archive comprise)
PDF_PAGE_MAX_STREAMS = 500           # flux concaténés dans /Contents d'une seule page
PDF_PAGE_MAX_FORMS = 500             # formulaires (XObject /Form) distincts sous une page
OCR_MAX_PAGES = 15                   # pages scannées OCR-isées par PDF (inchangé)
OCR_TOTAL_MAX_PAGES = 30             # pages OCR-isées au total sur une archive
OCR_DPI = 200
OCR_MAX_SIDE_PX = 4000               # plus grand côté d'une page rendue (A4 @200 dpi ≈ 2339)
OCR_TIMEOUT_S = 60                   # rendu d'UNE page par poppler


# Seules compressions dont zipfile borne la sortie à la taille demandée.
_ZIP_SAFE_COMPRESSION = (0, 8)       # ZIP_STORED, ZIP_DEFLATED


class _Budget:
    """Budget partagé sur une extraction (archive imbriquée comprise)."""
    def __init__(self):
        self.bytes_left = ZIP_TOTAL_MAX_BYTES
        self.ocr_pages_left = OCR_TOTAL_MAX_PAGES
        self.skipped_big = 0        # fichiers ignorés car trop volumineux décompressés
        self.skipped_nested = 0     # archives ignorées car imbriquées trop profondément
        import time as _t
        self.deadline = _t.monotonic() + PDF_TIME_BUDGET_S   # partagé par tous les PDF de l'archive
        self.pdf_content_left = PDF_DOC_CONTENT_MAX_BYTES     # idem, en octets de contenu décompressé
        self.pdf_heavy_pages = 0    # pages sautées car trop lourdes (plans vectoriels, bombes)


def _zip_entry_count_ok(content: bytes) -> bool:
    """Lit le nombre d'entrées DÉCLARÉ dans l'enregistrement de fin d'archive AVANT de
    construire ZipFile (qui matérialise un objet par entrée)."""
    import io, zipfile
    try:
        endrec = zipfile._EndRecData(io.BytesIO(content))   # API interne stable (3.8 → 3.14)
        if endrec is None:
            return True                                     # ZipFile lèvera son erreur claire
        return int(endrec[zipfile._ECD_ENTRIES_TOTAL]) <= ZIP_MAX_ENTRIES
    except Exception:
        return True


def _read_member_limited(zf, info, limit: int) -> bytes:
    """Lit un membre d'archive en flux, jamais plus de `limit` + 1 octets en mémoire.
    Retourne None si le membre dépasse la limite (taille déclarée OU réelle) ou s'il
    utilise une compression autre que « stockée »/deflate : bzip2/LZMA décompressent un
    bloc entier d'un coup, sans plafond de sortie (contournement de la lecture bornée)."""
    if info.file_size > limit or info.compress_type not in _ZIP_SAFE_COMPRESSION:
        return None
    with zf.open(info) as fh:
        # zipfile tronque la sortie à la taille DÉCLARÉE ; on ne demande donc jamais plus que
        # celle-ci (+1) : un en-tête qui ment « 1 Ko » ne fait décompresser que ~1 Ko.
        data = fh.read(min(info.file_size, limit) + 1)
    if len(data) > limit:
        return None
    return data


def _docx_sizes_ok(data: bytes) -> bool:
    """Un .docx est une archive : on vérifie ses tailles décompressées AVANT python-docx
    (qui charge toutes les parties en mémoire et parse le XML)."""
    import io, zipfile
    try:
        if not _zip_entry_count_ok(data):
            return False
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            total = xml_total = 0
            for i in z.infolist():
                if i.compress_type not in _ZIP_SAFE_COMPRESSION:
                    return False
                is_xml = i.filename.lower().endswith((".xml", ".rels"))
                if i.file_size > (DOCX_XML_MAX_BYTES if is_xml else DOCX_PART_MAX_BYTES):
                    return False
                total += i.file_size
                xml_total += i.file_size if is_xml else 0
                if total > DOCX_TOTAL_MAX_BYTES or xml_total > DOCX_XML_TOTAL_MAX_BYTES:
                    return False
        return True
    except Exception:
        return False   # archive illisible → python-docx échouerait de toute façon


def _page_content_key(page):
    """Identité des flux de contenu d'une page (références indirectes). Deux pages qui
    pointent vers le MÊME flux ont le même texte : inutile de le redécompresser."""
    try:
        raw = page.raw_get("/Contents") if hasattr(page, "raw_get") else page.get("/Contents")
        if hasattr(raw, "idnum"):
            return ((raw.idnum, raw.generation),)
        refs = []
        for x in (raw or []):
            if not hasattr(x, "idnum"):
                return None                       # flux direct : pas de clé fiable
            refs.append((x.idnum, x.generation))
        return tuple(refs) or None
    except Exception:
        return None


class _PdfAbort(BaseException):
    """Interruption d'une page trop coûteuse. BaseException EXPRÈS : pypdf avale `Exception`
    autour des formulaires (XObject), une Exception ordinaire ne remonterait pas."""


def _stream_size(s, limit: int) -> int:
    """Taille décompressée d'un flux, mesurée sans jamais produire plus de `limit` + 1 octets
    pour le cas courant (Flate). Les autres filtres passent par pypdf (plafonné par flux)."""
    import zlib
    try:
        flt = s.get("/Filter")
        flt = flt.get_object() if flt is not None else None
        if isinstance(flt, list):
            flt = flt[0] if len(flt) == 1 else tuple(flt)
        enc = getattr(s, "_data", None)
        if flt is None and isinstance(enc, (bytes, bytearray)):
            return len(enc)
        if flt in ("/FlateDecode", "/Fl") and isinstance(enc, (bytes, bytearray)):
            try:
                return len(zlib.decompressobj().decompress(bytes(enc), limit + 1))
            except zlib.error:
                pass                               # flux abîmé : pypdf sait parfois le réparer
        return len(s.get_data())
    except Exception:
        return 0


def _page_content_bytes(page, limit: int) -> int:
    """Ce que extract_text va réellement analyser : les flux de /Contents ET les formulaires
    (XObject /Form, récursivement, chacun compté une fois). Renvoie dès que `limit` est
    dépassé (bombe « une page = des milliers de flux » ou « formulaire géant »)."""
    total = 0
    try:
        contents = page.get("/Contents")
        contents = contents.get_object() if contents is not None else None
        streams = []
        if isinstance(contents, list):
            if len(contents) > PDF_PAGE_MAX_STREAMS:
                return limit + 1
            streams = [c.get_object() for c in contents]
        elif contents is not None:
            streams = [contents]
        for st in streams:
            total += _stream_size(st, limit - total)
            if total > limit:
                return total
        # Formulaires référencés par les ressources (héritées des nœuds parents au besoin).
        res, node, hops = None, page, 0
        while node is not None and hops < 32:
            if "/Resources" in node:
                res = node["/Resources"].get_object()
                break
            node = node.get("/Parent")
            node = node.get_object() if node is not None else None
            hops += 1
        seen, todo = set(), [res]
        while todo:
            r = todo.pop()
            if not hasattr(r, "get"):
                continue
            xo = r.get("/XObject")
            xo = xo.get_object() if xo is not None else None
            if not hasattr(xo, "items"):
                continue
            for _name, ref in xo.items():
                key = (ref.idnum, ref.generation) if hasattr(ref, "idnum") else id(ref)
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > PDF_PAGE_MAX_FORMS:
                    return limit + 1
                f = ref.get_object()
                if not hasattr(f, "get") or f.get("/Subtype") != "/Form":
                    continue                       # image : extract_text ne la décode pas
                total += _stream_size(f, limit - total)
                if total > limit:
                    return total
                sub = f.get("/Resources")
                if sub is not None:
                    todo.append(sub.get_object())
        return total
    except Exception:
        return total


def extract_text_from_pdf(file_bytes, max_pages: int = PDF_MAX_PAGES, max_chars: int = None,
                          deadline: float = None, budget: "_Budget" = None):
    """Extrait le texte d'un PDF — au plus `max_pages` pages, arrêt dès `max_chars`
    caractères (le texte au-delà serait de toute façon tronqué par l'appelant).
    Garde-fous CPU et mémoire (process unique) :
      • une page qui réutilise un flux déjà lu est sautée (« toutes les pages pointent vers
        le même flux de 74 Mo ») ;
      • une page dont le contenu décompressé (flux + formulaires) dépasse
        PDF_PAGE_CONTENT_MAX_BYTES est sautée, et le cumul est plafonné par dossier ;
      • chaque page dispose d'une tranche de temps, contrôlée PENDANT l'analyse (à chaque
        opérateur, y compris dans les formulaires appelés en boucle) ;
      • l'extraction s'arrête au-delà du budget de temps global (partagé par une archive)."""
    import time
    if budget is not None:
        deadline = budget.deadline
    if deadline is None:
        deadline = time.monotonic() + PDF_TIME_BUDGET_S
    content_left = budget.pdf_content_left if budget is not None else PDF_DOC_CONTENT_MAX_BYTES
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        parts, total, seen = [], 0, set()
        n = min(len(reader.pages), max_pages)
        for i in range(n):
            if time.monotonic() > deadline:
                break
            page = reader.pages[i]
            key = _page_content_key(page)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            size = _page_content_bytes(page, min(PDF_PAGE_CONTENT_MAX_BYTES, content_left))
            if size > PDF_PAGE_CONTENT_MAX_BYTES or size > content_left:
                # Page trop lourde (plan vectoriel, bombe) ou budget presque épuisé : on la
                # saute, les pages de texte (quelques Ko) suivantes passent encore.
                if budget is not None:
                    budget.pdf_heavy_pages += 1
                continue
            content_left -= size
            page_deadline = min(deadline, time.monotonic() + PDF_PAGE_TIME_S)
            cap = (max_chars - total + 2000) if max_chars else 2_000_000
            frags, got = [], [0]

            def _before(_op, _args, _cm, _tm):
                if time.monotonic() > page_deadline:
                    raise _PdfAbort()

            def _text(t, _cm, _tm, _font, _size):
                if t:
                    room = cap - got[0]
                    got[0] += len(t)
                    if got[0] <= cap:
                        frags.append(t)
                    else:
                        if room > 0:
                            frags.append(t[:room])
                        raise _PdfAbort()

            try:
                page_text = page.extract_text(visitor_operand_before=_before, visitor_text=_text)
            except _PdfAbort:
                page_text = "".join(frags)         # ce qui a été lu avant l'interruption
            if page_text:
                parts.append(page_text)
                total += len(page_text) + 2
                if max_chars and total >= max_chars:
                    break
        return "\n\n".join(parts).strip()
    except Exception as e:
        return f"Erreur extraction PDF : {str(e)}"
    finally:
        if budget is not None:
            budget.pdf_content_left = content_left


OCR_MIN_DPI = 10                     # en dessous, on borne directement en pixels (size=)


def _ocr_side_pt(page) -> float:
    """Plus grand côté de la page en points, tel que poppler le rendra : valeurs ABSOLUES
    (une MediaBox inversée [9500 9500 0 0] donne chez pypdf une largeur NÉGATIVE, alors que
    poppler remet les coins dans l'ordre et rend une page de 132 pouces), × /UserUnit s'il
    agrandit la page. 0.0 si la taille est illisible ou absurde (→ rendu borné en pixels)."""
    try:
        import math
        b = page.mediabox
        side = max(abs(float(b.right) - float(b.left)), abs(float(b.top) - float(b.bottom)))
        try:
            uu = float(page.get("/UserUnit", 1) or 1)
        except Exception:
            uu = 1.0
        if math.isfinite(uu) and uu > 1:
            side *= uu
        return side if math.isfinite(side) and side > 0 else 0.0
    except Exception:
        return 0.0


def _ocr_dpi_for(page) -> int:
    """Résolution de rendu : 200 dpi, réduite pour qu'une page géante (affiche, plan A0,
    format piégé 200×200 pouces) ne produise jamais une image de plusieurs Go.
    0 si la taille de la page est inconnue : l'appelant borne alors en pixels (size=)."""
    side_pt = _ocr_side_pt(page)
    if side_pt <= 0:
        return 0
    return min(OCR_DPI, int(OCR_MAX_SIDE_PX * 72 / side_pt))


def _ocr_render_kw(page) -> dict:
    """Paramètres de rendu poppler pour UNE page. Cas normal : dpi calculé. Si pypdf ne lit
    pas la page (page=None), si sa taille est inconnue ou si elle est si grande que même
    OCR_MIN_DPI dépasserait le plafond : size=OCR_MAX_SIDE_PX (pdf2image → pdftoppm
    -scale-to), borne en pixels du plus grand côté, quelle que soit la boîte déclarée."""
    dpi = _ocr_dpi_for(page) if page is not None else 0
    if dpi >= OCR_MIN_DPI:
        return {"dpi": dpi}
    return {"dpi": OCR_DPI // 2, "size": OCR_MAX_SIDE_PX}


def _ocr_pdf(content: bytes, max_pages: int = OCR_MAX_PAGES, budget: "_Budget" = None) -> str:
    """OCR de repli pour les DCE SCANNÉS (PDF image, fréquents chez les petites
    collectivités). Gracieux : retourne '' si l'OCR n'est pas disponible (binaire
    tesseract/poppler absent) — le code appelant retombe alors sur l'erreur claire.
    BORNÉ : poppler ne rend QUE les premières pages (first_page/last_page), une à la fois,
    au lieu de rendre tout le PDF en images puis d'en garder 15."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception:
        return ""
    if budget is not None:
        max_pages = min(max_pages, budget.ocr_pages_left)
    if max_pages <= 0:
        return ""
    pages = None
    try:
        import io
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(content)).pages
        max_pages = min(max_pages, len(pages))
    except Exception:
        pages = None   # PDF que pypdf ne lit pas : poppler borne quand même via last_page
    out = []
    for num in range(1, max_pages + 1):
        try:
            page = pages[num - 1] if pages is not None else None
        except Exception:
            page = None
        kw = dict(_ocr_render_kw(page), first_page=num, last_page=num)
        try:
            try:
                images = convert_from_bytes(content, timeout=OCR_TIMEOUT_S, **kw)
            except TypeError:      # pdf2image ancien sans `timeout` : on garde la borne de pages
                images = convert_from_bytes(content, **kw)
        except Exception:
            break
        if not images:
            break          # au-delà de la dernière page
        if budget is not None:
            budget.ocr_pages_left -= 1
        for img in images[:1]:
            try:
                out.append(pytesseract.image_to_string(img, lang="fra"))
            except Exception:
                try:
                    out.append(pytesseract.image_to_string(img))   # repli langue par défaut
                except Exception:
                    pass
        del images
    return "\n\n".join(t for t in out if t).strip()


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCX_MAX_BLOCKS = 20000             # paragraphes + lignes de tableau parcourus dans un .docx


def _roman(n: int) -> str:
    vals = ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
            (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))
    out, n = "", max(1, min(int(n), 3999))
    for v, r in vals:
        while n >= v:
            out += r
            n -= v
    return out


def _fmt_list_number(n: int, fmt: str) -> str:
    """Numéro d'un niveau de liste Word selon son format (w:numFmt)."""
    fmt = fmt or "decimal"
    if fmt == "bullet":
        return "-"
    if fmt == "none":
        return ""
    if fmt == "decimalZero":
        return f"{n:02d}"
    if fmt in ("lowerLetter", "upperLetter"):
        k = max(1, n)
        s = chr(ord("a") + (k - 1) % 26) * ((k - 1) // 26 + 1)
        return s.upper() if fmt == "upperLetter" else s
    if fmt in ("lowerRoman", "upperRoman"):
        r = _roman(n)
        return r.upper() if fmt == "upperRoman" else r
    return str(n)


class _DocxNumbering:
    """Rejoue la numérotation AUTOMATIQUE des listes Word (« Question 1 », « 2.1 », « a) »),
    absente de paragraph.text : sans elle, un cadre de réponse perdait ses numéros de
    questions. Gère les formats courants, les niveaux, les styles numérotés (titres) et les
    redémarrages (startOverride). Tout écart de format → numéro décimal (jamais d'exception)."""

    def __init__(self, doc):
        self.nums, self.abstracts, self.style_num = {}, {}, {}
        self.counters, self.started = {}, set()
        try:
            root = doc.part.numbering_part.element
            for an in root.findall(_W_NS + "abstractNum"):
                lvls = {}
                for lvl in an.findall(_W_NS + "lvl"):
                    il = int(lvl.get(_W_NS + "ilvl") or 0)
                    f, t, st, ps = (lvl.find(_W_NS + x) for x in ("numFmt", "lvlText", "start", "pStyle"))
                    lvls[il] = {"fmt": f.get(_W_NS + "val") if f is not None else "decimal",
                                "text": t.get(_W_NS + "val") if t is not None else f"%{il + 1}.",
                                "start": int(st.get(_W_NS + "val")) if st is not None else 1,
                                "pstyle": ps.get(_W_NS + "val") if ps is not None else None}
                self.abstracts[an.get(_W_NS + "abstractNumId")] = lvls
            for num in root.findall(_W_NS + "num"):
                a = num.find(_W_NS + "abstractNumId")
                ov = {}
                for o in num.findall(_W_NS + "lvlOverride"):
                    so = o.find(_W_NS + "startOverride")
                    if so is not None:
                        ov[int(o.get(_W_NS + "ilvl") or 0)] = int(so.get(_W_NS + "val"))
                self.nums[num.get(_W_NS + "numId")] = (a.get(_W_NS + "val") if a is not None else None, ov)
        except Exception:
            self.nums, self.abstracts = {}, {}
        try:
            styles = {}
            for st in doc.styles.element.findall(_W_NS + "style"):
                sid = st.get(_W_NS + "styleId")
                ppr = st.find(_W_NS + "pPr")
                npr = ppr.find(_W_NS + "numPr") if ppr is not None else None
                based = st.find(_W_NS + "basedOn")
                styles[sid] = (self._numpr(npr), based.get(_W_NS + "val") if based is not None else None)
            for sid in styles:
                cur, hops = sid, 0
                while cur in styles and hops < 10:
                    npr, based = styles[cur]
                    if npr and npr[0]:
                        self.style_num[sid] = npr
                        break
                    cur, hops = based, hops + 1
        except Exception:
            self.style_num = {}

    @staticmethod
    def _numpr(npr):
        if npr is None:
            return None
        nid, il = npr.find(_W_NS + "numId"), npr.find(_W_NS + "ilvl")
        return (nid.get(_W_NS + "val") if nid is not None else None,
                int(il.get(_W_NS + "val")) if il is not None else None)

    def prefix(self, p_el) -> str:
        try:
            ppr = p_el.find(_W_NS + "pPr")
            direct = self._numpr(ppr.find(_W_NS + "numPr")) if ppr is not None else None
            sid = None
            if ppr is not None:
                ps = ppr.find(_W_NS + "pStyle")
                sid = ps.get(_W_NS + "val") if ps is not None else None
            from_style = self.style_num.get(sid) if sid else None
            num_id = (direct[0] if direct and direct[0] else None) or (from_style[0] if from_style else None)
            if not num_id or num_id == "0" or num_id not in self.nums:
                return ""
            abs_id, overrides = self.nums[num_id]
            lvls = self.abstracts.get(abs_id) or {}
            il = direct[1] if direct and direct[1] is not None else (from_style[1] if from_style else None)
            if il is None:
                il = next((k for k, v in lvls.items() if sid and v.get("pstyle") == sid), 0)
            il = max(0, min(int(il), 8))
            st = self.counters.setdefault(abs_id, {})
            if num_id not in self.started:
                self.started.add(num_id)
                for k, v in overrides.items():
                    st[k] = v - 1
            lv = lvls.get(il) or {"fmt": "decimal", "text": f"%{il + 1}.", "start": 1}
            st[il] = st.get(il, lv["start"] - 1) + 1
            for k in [k for k in st if k > il]:
                del st[k]
            if lv["fmt"] == "bullet":
                return "- "

            def _sub(m):
                k = int(m.group(1)) - 1
                lk = lvls.get(k) or {"fmt": "decimal", "start": 1}
                return _fmt_list_number(st.get(k, lk.get("start", 1)), lk.get("fmt"))
            txt = re.sub(r"%([1-9])", _sub, lv.get("text") or "")
            return (txt.strip() + " ") if txt.strip() else ""
        except Exception:
            return ""


def _docx_blocks(doc) -> list:
    """Texte du corps d'un .docx DANS L'ORDRE du document : paragraphes (avec leur numéro de
    liste), tableaux ligne par ligne (« cellule | cellule », fusion verticale lue une fois) et
    contrôles de contenu (w:sdt) — un cadre de réponse range souvent ses questions dans des
    tableaux ou des zones de saisie."""
    from docx.text.paragraph import Paragraph
    numbering = _DocxNumbering(doc)
    out, seen = [], [0]

    def _para(el, parent) -> str:
        t = Paragraph(el, parent).text
        return (numbering.prefix(el) + t) if t else ""

    def _walk(container, parent):
        for el in container.iterchildren():
            if seen[0] > _DOCX_MAX_BLOCKS:
                return
            tag = el.tag
            if tag == _W_NS + "p":
                seen[0] += 1
                t = _para(el, parent)
                if t:
                    out.append(t)
            elif tag == _W_NS + "tbl":
                for tr in el.iterchildren(_W_NS + "tr"):
                    seen[0] += 1
                    if seen[0] > _DOCX_MAX_BLOCKS:
                        return
                    cells = []
                    for tc in tr.iterchildren(_W_NS + "tc"):
                        tcpr = tc.find(_W_NS + "tcPr")
                        vm = tcpr.find(_W_NS + "vMerge") if tcpr is not None else None
                        if vm is not None and (vm.get(_W_NS + "val") or "continue") == "continue":
                            continue        # suite d'une fusion verticale : déjà lue au-dessus
                        txt = "\n".join(x for x in (_para(p, parent) for p in tc.iterchildren(_W_NS + "p")) if x)
                        if txt:
                            cells.append(txt)
                    if cells:
                        out.append(" | ".join(cells))
            elif tag == _W_NS + "sdt":
                content = el.find(_W_NS + "sdtContent")
                if content is not None:
                    _walk(content, parent)

    _walk(doc.element.body, doc._body)
    return out


def _extract_docx(data: bytes) -> str:
    """Extrait le texte d'un .docx (Word), tableaux compris, DANS L'ORDRE du document et avec
    la numérotation automatique des listes (numéros des questions d'un cadre de réponse).
    Gracieux si python-docx absent. Tailles décompressées vérifiées AVANT ouverture (un .docx
    est une archive ZIP)."""
    if not _docx_sizes_ok(data):
        return ""
    try:
        import io
        import docx
        d = docx.Document(io.BytesIO(data))
    except Exception:
        return ""
    try:
        return "\n".join(_docx_blocks(d)).strip()
    except Exception:
        # Repli historique : paragraphes puis tableaux (sans numérotation).
        try:
            parts = [p.text for p in d.paragraphs if p.text]
            for tbl in d.tables:
                for row in tbl.rows:
                    cells = [c.text for c in row.cells if c.text]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts).strip()
        except Exception:
            return ""


_ZIP_OKEXT = (".pdf", ".docx", ".txt", ".md", ".csv")


def _extract_zip(content: bytes, max_chars: int, budget: "_Budget", depth: int, parts: list) -> None:
    """Parcourt une archive (et au plus 1 niveau d'archive imbriquée) en ajoutant à
    `parts` une pièce {nom, texte, type, complet} par fichier exploitable. Toute lecture est
    bornée par `budget`.

    Lecture PIÈCE PAR PIÈCE (rédaction, vague 1) : le règlement de la consultation et le
    cadre de réponse sont lus EN PREMIER (reconnus par leur nom, sans IA), puis les pièces au
    nom inconnu, l'acte d'engagement, le CCAP, les bordereaux, et le CCTP en dernier. Chaque
    pièce a son propre plafond (`max_chars`) et la lecture totale reste bornée à
    2 × `max_chars` : un gros CCTP ne fait plus disparaître le règlement ni le cadre."""
    import io, os, time, zipfile
    from app.services import dce_pieces as _dp
    if not _zip_entry_count_ok(content):
        raise ValueError("Archive ZIP trop complexe (trop de fichiers). "
                         "Importez directement les pièces utiles (RC, CCAP, CCTP, DPGF).")
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception:
        raise ValueError("Archive ZIP corrompue ou illisible.")
    read_cap = 2 * max(1, int(max_chars))
    with zf:
        # Règlement et cadre d'abord, archives imbriquées en dernier ; à rang égal, PDF puis
        # Word/texte, puis par nom (ordre stable, reproductible d'un import à l'autre).
        def _rank(i):
            ln = i.filename.lower()
            if ln.endswith(".zip"):
                return (9, 2, ln)
            kind, _sure = _dp.classify_name(os.path.basename(i.filename))
            return (_dp.read_rank(kind), 0 if ln.endswith(".pdf") else 1, ln)
        for info in sorted(zf.infolist(), key=_rank):
            if _chars(parts) > read_cap or len(parts) >= ZIP_MAX_FILES or budget.bytes_left <= 0:
                break
            n = info.filename
            ln = n.lower()
            if info.is_dir() or os.path.basename(n).startswith("."):
                continue
            is_zip = ln.endswith(".zip")
            if not (ln.endswith(_ZIP_OKEXT) or is_zip):
                continue
            if is_zip and depth >= ZIP_MAX_DEPTH:
                budget.skipped_nested += 1
                continue
            if info.compress_type not in _ZIP_SAFE_COMPRESSION:
                continue    # bzip2/LZMA : sortie non bornable → ignoré (format non géré)
            try:
                data = _read_member_limited(zf, info, min(ZIP_MEMBER_MAX_BYTES, budget.bytes_left))
                if data is None:
                    budget.skipped_big += 1
                    continue
                budget.bytes_left -= len(data)
                if is_zip:
                    _extract_zip(data, max_chars, budget, depth + 1, parts)
                    continue
                # Plafond PAR PIÈCE (et jamais au-delà du plafond de lecture total).
                remaining = max(0, min(max_chars, read_cap - _chars(parts))) + 1
                complet = True
                if ln.endswith(".pdf"):
                    heavy_before = budget.pdf_heavy_pages
                    t = extract_text_from_pdf(data, max_chars=remaining, budget=budget)
                    # Budget de temps épuisé pendant cette pièce : elle n'a peut-être pas été lue en entier.
                    if time.monotonic() > budget.deadline:
                        complet = False
                    # PDF scanné dans l'archive → OCR de repli. Pas pour un PDF dont on a sauté
                    # des pages trop lourdes (plans vectoriels) : l'OCR y serait long et inutile.
                    if (not (t and not t.startswith("Erreur") and len(t) > 30)
                            and budget.pdf_heavy_pages == heavy_before):
                        t = _ocr_pdf(data, budget=budget)
                elif ln.endswith(".docx"):
                    t = _extract_docx(data)
                else:
                    t = data[:remaining * 4].decode("utf-8", errors="replace")
                del data
                if t and not t.startswith("Erreur") and len(t) > 30:
                    base = os.path.basename(n)
                    body = t[:remaining - 1] if len(t) >= remaining else t
                    parts.append({"nom": base, "texte": body,
                                  "type": _dp.classify_piece(base, body),
                                  "complet": complet and len(t) < remaining})
            except ValueError:
                continue    # archive imbriquée illisible : on passe aux autres pièces
            except Exception:
                continue


def _chars(parts: list) -> int:
    return sum(len(p["texte"]) if isinstance(p, dict) else len(p) for p in parts)


def _single_piece(filename: str, text: str, max_chars: int) -> list:
    from app.services import dce_pieces as _dp
    import os
    base = os.path.basename((filename or "").replace("\\", "/"))
    body = text[:max_chars]
    return [{"nom": base, "texte": body, "type": _dp.classify_piece(base, body),
             "complet": len(text) < max_chars}]


def extract_dce_pieces(filename: str, content: bytes, max_chars: int = 40000) -> tuple:
    """Lecture PIÈCE PAR PIÈCE d'un dossier : renvoie (pieces, archive) où pieces =
    [{nom, texte, type, complet}] (type reconnu sans IA, cf. app.services.dce_pieces) et
    archive = True pour un ZIP. Lève ValueError avec un message clair si illisible/vide/non
    supporté. Mémoire et CPU BORNÉS quel que soit le fichier (cf. plafonds ci-dessus)."""
    name = (filename or "").lower()

    if name.endswith(".pdf") or content[:5] == b"%PDF-":
        txt = extract_text_from_pdf(content, max_chars=max_chars)
        if not txt or txt.startswith("Erreur") or len(txt) < 30:
            # PDF sans couche texte → tentative OCR (document scanné).
            ocr = _ocr_pdf(content)
            if ocr and len(ocr) >= 30:
                return _single_piece(filename, ocr, max_chars), False
            raise ValueError("PDF illisible (document scanné/protégé ?) ou vide. "
                             "Si c'est un scan, l'OCR n'a rien pu extraire.")
        return _single_piece(filename, txt, max_chars), False

    if name.endswith(".docx"):   # AVANT le ZIP : un .docx est aussi une archive PK
        if not _docx_sizes_ok(content):
            raise ValueError("Document Word trop volumineux ou illisible. Exportez-le en PDF puis réessayez.")
        t = _extract_docx(content)
        if t and len(t) >= 20:
            return _single_piece(filename, t, max_chars), False
        raise ValueError("Document Word illisible ou vide. Exportez-le en PDF si le souci persiste.")

    if name.endswith((".txt", ".md", ".csv")):
        t = content[:max_chars * 4].decode("utf-8", errors="replace").strip()
        if t:
            return _single_piece(filename, t, max_chars), False
        raise ValueError("Fichier texte vide ou illisible.")

    if name.endswith(".zip") or content[:2] == b"PK":
        budget = _Budget()
        parts = []
        _extract_zip(content, max_chars, budget, 0, parts)
        if not parts:
            if budget.skipped_big:
                raise ValueError("Un fichier de l'archive est trop volumineux une fois décompressé "
                                 f"({ZIP_MEMBER_MAX_BYTES // _MB} Mo max par fichier). "
                                 "Importez directement les pièces utiles (RC, CCAP, CCTP, DPGF).")
            if budget.skipped_nested:
                raise ValueError("Archive trop imbriquée (un ZIP dans un ZIP dans un ZIP). "
                                 "Décompressez-la puis importez les pièces ou un seul ZIP.")
            raise ValueError("Aucun fichier exploitable dans l'archive (PDF scanné ou format non géré ?).")
        return parts, True

    raise ValueError("Format non supporté. Importez le dossier en PDF, Word (.docx), texte ou archive ZIP.")


def extract_dce_text(filename: str, content: bytes, max_chars: int = 40000, with_pieces: bool = False):
    """
    Extrait le texte d'un DCE réel : PDF unique OU archive ZIP de plusieurs pièces.
    Lève ValueError avec un message clair si illisible/vide/non supporté.
    Mémoire et CPU BORNÉS quel que soit le fichier (cf. plafonds ci-dessus).

    Archive : une pièce par fichier, précédée de « === nom === ». Le règlement de la
    consultation et le cadre de réponse viennent EN PREMIER et EN ENTIER ; les autres pièces
    se partagent équitablement le reste du plafond (app.services.dce_pieces.compose).
    with_pieces=True → (texte, meta) avec meta = [{nom, type, libelle, caracteres,
    lu_en_entier}] (ce qui a été lu, pièce par pièce, pour l'écran).
    """
    from app.services import dce_pieces as _dp
    pieces, archive = extract_dce_pieces(filename, content, max_chars=max_chars)
    text, meta = _dp.compose(pieces, max_chars, headers=archive)
    return (text, meta) if with_pieces else text


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


def analyze_dce_text(text, company=None, criteria=None, lang_name=None, pieces=None):
    """Analyse un DCE depuis du texte brut (notice BOAMP, DCE déjà extrait...).
    lang_name : langue de rédaction des valeurs textuelles (adaptation par pays).
    pieces : ce qui a été lu, pièce par pièce (meta de extract_dce_text(with_pieces=True)),
    repris tel quel dans la grille « Comment vous serez noté »."""
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

        # « COMMENT VOUS SEREZ NOTÉ » (rédaction, vague 1) : critères retrouvés dans le texte
        # avec leur phrase (citation_guard), poids TEL QU'ÉCRIT, contrôle du total et ce que le
        # dossier impose (cadre de réponse, limites, visite) — tout est vérifié SANS IA. Une
        # erreur ici ne casse jamais l'analyse déjà payée : la grille est simplement absente.
        try:
            from app.services.grille_notation import build_grille
            result["details"]["grille_notation"] = build_grille(result["details"], text, pieces=pieces)
        except Exception as e:      # noqa: BLE001
            import logging
            logging.getLogger("adjugo").warning("grille de notation non construite : %s", type(e).__name__)

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
