"""
AGENT RÉDACTEUR DE DCE (côté ACHETEUR public) — Pilier 1 du produit collectivités.

À partir d'un BESOIN décrit en langage normal par un acheteur (objet, type de marché,
montant estimé, durée, lieu, contraintes), l'IA produit un PROJET de Dossier de
Consultation des Entreprises (DCE) cohérent et conforme :
  - synthèse du besoin,
  - allotissement proposé, TAILLÉ pour être atteignable par des PME / groupements
    (ADN Adjugo : allotir pour faire entrer les PME → moins d'infructueux),
  - critères de sélection + pondération + grille (dont critère environnemental),
  - projet de CCTP (clauses techniques),
  - points clés du CCAP + CCAG applicable + clause de dérogations (R2112-3),
  - clauses environnementales / sociales (obligation ferme au 21 août 2026),
  - pièces du DCE et pièces de candidature, conseils acheteur et garde-fous légaux.

Trois principes repris du reste d'Adjugo :
  1. Ce qui est JURIDIQUEMENT SENSIBLE (type de procédure selon les seuils) est calculé
     de façon DÉTERMINISTE ici (pas confié au LLM), puis injecté comme contrainte.
  2. Le LLM rédige l'éditorial, mais le résultat est un PROJET à faire valider — jamais
     un acte juridique définitif (disclaimer porté jusque dans l'UI).
  3. VITESSE : la génération est SPLITTÉE en 2 appels PARALLÈLES — la structure (Sonnet,
     raisonnement juridique) et le CCTP (Haiku, prose rapide) — pour diviser la latence.
     Chaque thread RE-POSE `tenant_scope` (le contextvar n'est pas hérité par le pool).

Seuils & dates VÉRIFIÉS au 28/06/2026 (décret n°2025-1386 du 29/12/2025 pour les
dispenses ; règlements délégués UE publiés au JOUE le 23/10/2025 pour le formalisé ;
art. 35 loi n°2021-1104 « Climat & Résilience » pour l'obligation environnementale).
Tous surchargeables par variable d'environnement — tenir l'outil à jour fait partie du
produit (prochaine révision des seuils formalisés : 1er janvier 2028).
"""
import os
from concurrent.futures import ThreadPoolExecutor
from app.services.llm import complete, complete_json, parse_json, tenant_scope, MODEL_FAST, LLMUnavailable

# ── Seuils de DISPENSE de publicité/mise en concurrence — gré à gré (€ HT) ────
# Par TYPE depuis 2026 (art. R2122-8 CCP). Travaux 100 000 € (pérenne, 1er janv. 2026) ;
# fournitures/services 60 000 € (1er avril 2026 ; 40 000 € entre janv. et mars 2026).
SEUIL_DISPENSE_TRAVAUX = float(os.getenv("DCE_SEUIL_DISPENSE_TRAVAUX", "100000"))
SEUIL_DISPENSE_FCS = float(os.getenv("DCE_SEUIL_DISPENSE_FCS", "60000"))

# ── Seuils de PROCÉDURE FORMALISÉE (€ HT), valeurs 2026-2027 ──────────────────
# Cible = COLLECTIVITÉS / autres pouvoirs adjudicateurs : F/S 216 000 € (≠ 140 000 €
# pour l'État/pouvoirs adjudicateurs centraux). Travaux 5 404 000 € (identique partout).
SEUIL_FORMALISE_FCS = float(os.getenv("DCE_SEUIL_FCS", "216000"))
SEUIL_FORMALISE_TRAVAUX = float(os.getenv("DCE_SEUIL_TRAVAUX", "5404000"))

# Seuils de PUBLICITÉ (MAPA) — distincts : mise en ligne des documents sur le profil
# acheteur dès 60 000 € (R2132-2) ; publication d'un avis BOAMP/JAL dès 90 000 €.
SEUIL_PUB_PROFIL = 60000.0
SEUIL_PUB_AVIS = 90000.0

SEUIL_REF_LABEL = os.getenv(
    "DCE_SEUIL_LABEL",
    "seuils 2026-2027 (en vigueur au 1er janvier 2026 ; dispenses relevées par décret "
    "n°2025-1386) — valeurs « collectivités » — à revérifier à la date de publication")

# Obligation environnementale ferme (art. 35 loi Climat & Résilience).
DATE_OBLIG_ENV = "21 août 2026"

_TYPES = {"travaux", "fournitures", "services"}
# Marqueurs pour vérifier qu'un critère environnemental est bien présent (déterministe).
_ENV_MARKERS = ("environnement", "écolog", "ecolog", "carbone", "co2", "énerg", "energ",
                "rse", "durable", "biosourc", "déchet", "dechet", "climat")


def procedure_recommandee(montant, type_marche: str) -> dict:
    """Détermine la procédure adaptée au montant (DÉTERMINISTE, hors LLM).

    Renvoie un dict explicable : type, code, justification, seuil de référence,
    niveau de publicité conseillé, délai indicatif et note de délai. Le montant peut
    être None (procédure adaptée prudente, montant à préciser)."""
    t = (type_marche or "").strip().lower()
    t = t if t in _TYPES else "services"
    seuil_disp = SEUIL_DISPENSE_TRAVAUX if t == "travaux" else SEUIL_DISPENSE_FCS
    seuil_form = SEUIL_FORMALISE_TRAVAUX if t == "travaux" else SEUIL_FORMALISE_FCS
    libelle_type = "travaux" if t == "travaux" else "fournitures/services"

    try:
        m = float(montant) if montant not in (None, "") else None
    except (ValueError, TypeError):
        m = None
    if m is not None and m < 0:          # un montant négatif n'a pas de sens → non précisé
        m = None

    if m is None:
        return {
            "type": "Procédure adaptée (MAPA)", "code": "mapa",
            "justification": "Montant estimé non précisé : par défaut, procédure adaptée. "
                             f"Précisez le montant — au-delà du seuil formalisé ({_eur(seuil_form)} HT "
                             f"pour des {libelle_type}, valeur collectivités), la procédure formalisée "
                             "devient obligatoire ; en deçà du seuil de dispense "
                             f"({_eur(seuil_disp)} HT), le gré à gré est possible.",
            "seuil_reference": SEUIL_REF_LABEL,
            "publicite": "Publicité adaptée à l'objet et au montant (à confirmer une fois le montant connu)",
            "delai_min_jours": None,
            "delai_note": "Délai à proportionner à la complexité (pas de minimum réglementaire en MAPA).",
        }
    if m < seuil_disp:
        return {
            "type": "Gré à gré (sans publicité ni mise en concurrence préalable)", "code": "mna",
            "justification": f"Montant estimé {_eur(m)} HT, inférieur au seuil de dispense de "
                             f"{_eur(seuil_disp)} HT ({libelle_type}, art. R2122-8 CCP). Dispense possible, "
                             "MAIS : bon usage des deniers publics (plusieurs devis conseillés) et "
                             "interdiction de scinder artificiellement le besoin pour rester sous le seuil.",
            "seuil_reference": SEUIL_REF_LABEL,
            "publicite": "Non obligatoire (mise en concurrence informelle / 3 devis conseillés)",
            "delai_min_jours": None,
            "delai_note": "Pas de formalisme imposé ; laissez un délai raisonnable de réponse.",
        }
    if m < seuil_form:
        # Publicité MAPA : deux seuils distincts (profil acheteur 60 k€ / avis 90 k€).
        if m >= SEUIL_PUB_AVIS:
            pub = ("Avis obligatoire au BOAMP ou dans un JAL (≥ 90 000 € HT) ET documents de "
                   "consultation en ligne sur le profil acheteur (≥ 60 000 € HT, R2132-2)")
        elif m >= SEUIL_PUB_PROFIL:
            pub = ("Documents de consultation à mettre en ligne sur le profil acheteur "
                   "(≥ 60 000 € HT, R2132-2) ; publicité adaptée à l'objet")
        else:
            pub = "Publicité adaptée à l'objet et au montant"
        return {
            "type": "Procédure adaptée (MAPA)", "code": "mapa",
            "justification": f"Montant estimé {_eur(m)} HT, entre le seuil de dispense ({_eur(seuil_disp)} HT) "
                             f"et le seuil formalisé ({_eur(seuil_form)} HT, {libelle_type}, valeur "
                             "collectivités). Vous organisez librement la procédure, dans le respect des "
                             "principes de la commande publique (publicité et mise en concurrence réelles).",
            "seuil_reference": SEUIL_REF_LABEL, "publicite": pub,
            "delai_min_jours": None,
            "delai_note": "Aucun délai réglementaire en MAPA ; la DAJ recommande ≈ 22 jours pour un MAPA "
                          "publié, à proportionner à la complexité (un délai trop court pénalise les PME).",
        }
    return {
        "type": "Appel d'offres (procédure formalisée)", "code": "formalise",
        "justification": f"Montant estimé {_eur(m)} HT, au-dessus du seuil formalisé de {_eur(seuil_form)} HT "
                         f"({libelle_type}, valeur collectivités) : procédure formalisée obligatoire "
                         "(appel d'offres ouvert par défaut), publication au BOAMP et au JOUE.",
        "seuil_reference": SEUIL_REF_LABEL,
        "publicite": "Avis au BOAMP + JOUE (profil acheteur dématérialisé)",
        "delai_min_jours": 35,
        "delai_note": "35 jours (envoi de l'avis) en AO ouvert ; réductions possibles : 30 j si remise "
                      "électronique des offres, 15 j avec avis de préinformation ou urgence justifiée "
                      "(art. R2161-2 et s. CCP).",
    }


def _eur(v) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", " ") + " €"
    except (ValueError, TypeError):
        return str(v)


# ── Prompt CŒUR (Sonnet) : raisonnement juridique (allotissement + critères) ──
_SYSTEM_CORE = f"""Tu es un acheteur public senior français (rédacteur de marchés publics),
expert du Code de la commande publique (CCP). Tu aides une COLLECTIVITÉ à rédiger un
PROJET de Dossier de Consultation des Entreprises (DCE) clair, complet et conforme.

PRINCIPES À RESPECTER :
- Conformité CCP : liberté d'accès, égalité de traitement, transparence. JAMAIS de
  préférence locale (illégale) ni de critère excluant de fait les PME. Ne jamais
  scinder artificiellement le besoin pour passer sous un seuil.
- ALLOTISSEMENT par principe (art. L2113-10 CCP) : découpe en lots de taille
  RAISONNABLE, pensés pour être atteignables par des PME, le cas échéant en GROUPEMENT
  (co-traitance). Objectif central : faire entrer les PME, éviter l'infructueux. Si tu
  proposes un LOT UNIQUE, tu DOIS le motiver au titre de l'art. L2113-11 (l'un des trois
  motifs limitatifs : coordination impossible ; restriction de concurrence ou exécution
  techniquement difficile/plus coûteuse ; risque d'infructuosité pour entités
  adjudicatrices) — renseigne alors `allotissement.motivation_lot_unique`.
- ENVIRONNEMENT (OBLIGATOIRE à compter du {DATE_OBLIG_ENV}, art. 35 loi n°2021-1104) :
  inclure SYSTÉMATIQUEMENT au moins UNE condition d'exécution environnementale liée à
  l'objet (art. L2112-2 / L2112-3) ET au moins UN critère d'attribution environnemental
  de pondération STRICTEMENT POSITIVE. Ajouter une clause sociale si pertinent.
- CCAG : choisis le CCAG adapté à l'objet (Travaux ; FCS ; PI ; TIC ; MOE ; MI). Dès
  qu'un CCAG est référencé, le CCAP doit récapituler les DÉROGATIONS en dernier article
  (art. R2112-3) — renseigne `ccap.derogations_ccag`.
- PIÈCES DU DCE : règlement de la consultation (RC), acte d'engagement (modèle ATTRI1),
  CCAP, CCTP, et pièces FINANCIÈRES COHÉRENTES avec le type de prix : DPGF si prix global
  et forfaitaire ; BPU + DQE si prix unitaires / à bons de commande.
- Tu produis un PROJET À FAIRE VALIDER, pas un acte juridique définitif. N'invente pas de
  référence normative précise dont tu n'es pas sûr ; utilise « [à compléter] » si une
  information manque.
- La PROCÉDURE (gré à gré / MAPA / formalisée) t'est IMPOSÉE en entrée : ne la recalcule
  pas, appuie ta rédaction dessus.

Tu réponds en JSON STRICT (français), sans aucun texte autour, selon EXACTEMENT ce schéma :
{{
  "objet": "intitulé clair et précis du marché",
  "synthese_besoin": "2 à 4 phrases reformulant le besoin et son contexte",
  "allotissement": {{
    "recommande": true|false,
    "principe": "rappel bref de l'obligation d'allotir et de la logique PME/groupement retenue",
    "motivation_lot_unique": "si recommande=false : motivation au titre de L2113-11, sinon \\"\\"",
    "lots": [
      {{"numero": <entier>, "intitule": "...", "description": "périmètre du lot",
        "atteignable_pme": "pourquoi ce lot est à portée d'une PME (ou d'un groupement)",
        "groupement_conseille": true|false}}
    ]
  }},
  "criteres": {{
    "liste": [
      {{"critere": "<nom du critère>", "ponderation": <entier>, "sous_criteres": ["...", "..."]}}
    ],
    "note": "rappel : somme des pondérations = 100 ; au moins un critère environnemental ; pas de critère excluant les PME"
  }}
}}

CONSIGNES : SOIS SYNTHÉTIQUE — allotissement raisonnable et pensé PME/groupement (sauf
impossibilité, alors lot unique MOTIVÉ) ; pondérations ENTIÈRES dont la SOMME vaut 100, avec au
moins un critère environnemental pondéré > 0. NE rédige NI le CCAP, NI les pièces, NI le CCTP
(rédigés séparément)."""


# ── Prompt ADMINISTRATIF (Haiku, rapide) : CCAP, RSE, pièces, conseils, garde-fous ──
_SYSTEM_ADMIN = f"""Tu es un acheteur public français. Tu rédiges les volets ADMINISTRATIFS d'un
projet de DCE de collectivité (le besoin et la procédure imposée te sont donnés). Règles :
- CCAG adapté à l'objet (Travaux ; FCS ; PI ; TIC ; MOE ; MI). Si un CCAG est référencé, le CCAP
  récapitule les DÉROGATIONS en dernier article (art. R2112-3).
- Pièces FINANCIÈRES cohérentes avec le type de prix : DPGF si prix global et forfaitaire ;
  BPU + DQE si prix unitaires / à bons de commande.
- ENVIRONNEMENT (obligatoire à compter du {DATE_OBLIG_ENV}, loi n°2021-1104) : au moins UNE
  condition d'exécution environnementale liée à l'objet (art. L2112-2). Clause sociale si pertinent.
- NEUTRALITÉ : jamais de préférence locale (illégale) ni de critère excluant les PME.
- Reste un PROJET à valider ; « [à compléter] » plutôt qu'inventer une référence incertaine.

Réponds en JSON STRICT (français), sans texte autour, selon EXACTEMENT ce schéma :
{{
  "ccap": {{
    "ccag_applicable": "CCAG Travaux | CCAG FCS | CCAG PI | CCAG TIC | CCAG MOE | CCAG MI",
    "type_prix": "prix global et forfaitaire | prix unitaires | mixte",
    "points_cles": ["durée / délais", "modalités de paiement (avances, acomptes)", "pénalités", "..."],
    "derogations_ccag": "article récapitulatif des dérogations au CCAG, ou \\"aucune dérogation\\" si aucune"
  }},
  "clauses_rse": {{
    "environnementales": ["condition d'exécution environnementale concrète, liée à l'objet", "..."],
    "sociales": ["clause d'insertion ou condition sociale si pertinent", "..."]
  }},
  "pieces_dce": ["Règlement de la consultation (RC)", "Acte d'engagement (ATTRI1)", "CCAP", "CCTP", "<pièce financière selon le type de prix>"],
  "pieces_candidature": ["DC1 (lettre de candidature)", "DC2 (déclaration du candidat) ou DUME", "..."],
  "conseils": ["conseil acheteur concret (anti-infructueux, sourcing, délai, etc.)", "..."],
  "garde_fous": ["rappel de neutralité / égalité de traitement / interdiction de préférence locale", "..."]
}}
Sois SYNTHÉTIQUE : 3 à 5 points clés, 3 à 4 conseils, 3 à 4 garde-fous."""

# ── Prompt CCTP (Haiku) : uniquement la prose technique, en parallèle ─────────
_SYSTEM_CCTP = """Tu es un rédacteur technique de marchés publics français. Tu rédiges UNIQUEMENT
le projet de CCTP (Cahier des Clauses Techniques Particulières) d'un marché de collectivité :
3 à 4 sections synthétiques mais concrètes (objet/consistance, spécifications techniques,
performances/qualité, et gestion environnementale du chantier/de la prestation). Chaque section
= 3 à 6 phrases. Intègre les exigences environnementales fournies. N'invente pas de norme précise
dont tu n'es pas sûr ; utilise « [à compléter] » au besoin.

Réponds en JSON STRICT (français), sans texte autour :
{"cctp_sections": [{"titre": "<titre de section>", "contenu": "<rédaction de la clause>"}]}"""


def _besoin_user(besoin: dict, objet: str, type_marche: str, proc: dict) -> str:
    """Message UTILISATEUR commun (besoin variable + procédure imposée)."""
    return f"""BESOIN :
- Objet : {objet}
- Type de marché : {type_marche}
- Montant estimé : {_eur(besoin.get('montant_estime')) if besoin.get('montant_estime') else '[à préciser]'} HT
- Durée / délai : {besoin.get('duree_mois') or '[à préciser]'} mois
- Lieu d'exécution : {(besoin.get('lieu') or '').strip() or '[à préciser]'} (dépt {besoin.get('dept') or '[?]'})
- Contraintes particulières : {(besoin.get('contraintes') or '').strip() or 'aucune précisée'}
- Exigences environnementales attendues : {(besoin.get('exigences_env') or '').strip() or 'à proposer selon l’objet (obligatoire)'}
- Exigences sociales attendues : {(besoin.get('exigences_sociales') or '').strip() or 'à proposer si pertinent'}
- Souhait d'allotissement : {besoin.get('allotissement') or 'auto (à toi de proposer)'}

PROCÉDURE IMPOSÉE (déterminée par les seuils, ne la recalcule pas) :
- {proc['type']} — {proc['justification']}"""


def _gen_core(user: str, tenant) -> dict:
    """Cœur juridique (Sonnet) : objet, synthèse, allotissement, critères. Re-pose le scope."""
    with tenant_scope(tenant):
        return complete_json(_SYSTEM_CORE, "Rédige le cœur du DCE pour :\n\n" + user,
                             max_tokens=3500, temperature=0.25)


def _gen_admin(user: str, tenant) -> dict:
    """Volets administratifs (Haiku, rapide) : CCAP, RSE, pièces, conseils, garde-fous."""
    with tenant_scope(tenant):
        raw = complete(_SYSTEM_ADMIN, "Rédige les volets administratifs pour :\n\n" + user,
                       max_tokens=2500, temperature=0.3, model=MODEL_FAST)
    return parse_json(raw)


def _gen_cctp(user: str, tenant) -> dict:
    """Appel CCTP (Haiku, prose rapide). Re-pose tenant_scope (thread du pool)."""
    with tenant_scope(tenant):
        raw = complete(_SYSTEM_CCTP, "Rédige le CCTP pour :\n\n" + user,
                       max_tokens=3000, temperature=0.3, model=MODEL_FAST)
    return parse_json(raw)


def generer_dce(besoin: dict, tenant=None) -> dict:
    """Génère un PROJET de DCE structuré à partir d'un besoin acheteur.

    3 appels LLM PARALLÈLES pour la latence : CŒUR juridique (Sonnet : allotissement +
    critères), ADMINISTRATIF (Haiku : CCAP/RSE/pièces/conseils) et CCTP (Haiku). Le cœur
    est FATAL en cas d'échec (503) ; admin et CCTP sont NON bloquants (dégradation gracieuse
    → avertissement). On ne fuite jamais la sortie brute du modèle au client.

    `tenant` : id de tenant LLM (re-posé dans chaque thread du pool)."""
    objet = (besoin.get("objet") or "").strip()
    if len(objet) < 8:
        raise ValueError("Objet du marché trop court pour générer un DCE fiable.")

    type_marche = (besoin.get("type_marche") or "services").strip().lower()
    proc = procedure_recommandee(besoin.get("montant_estime"), type_marche)
    user = _besoin_user(besoin, objet, type_marche, proc)

    # NB : on n'utilise PAS `with ... as ex` — son __exit__ ferait shutdown(wait=True) et
    # bloquerait jusqu'à la fin des appels Haiku (≤ LLM_TIMEOUT) même quand le cœur échoue
    # vite (disjoncteur ouvert). On gère l'arrêt nous-mêmes (wait=False) pour échouer vite.
    ex = ThreadPoolExecutor(max_workers=3)
    try:
        f_core = ex.submit(_gen_core, user, tenant)
        f_admin = ex.submit(_gen_admin, user, tenant)
        f_cctp = ex.submit(_gen_cctp, user, tenant)
        # Cœur = obligatoire. Toute panne (LLMUnavailable, JSON tronqué, erreur API brute du
        # fournisseur, contenu vide…) → 503 propre, jamais de 500 ni de fuite de sortie brute.
        try:
            data = f_core.result()
        except LLMUnavailable:
            f_admin.cancel(); f_cctp.cancel(); raise
        except ValueError as e:
            f_admin.cancel(); f_cctp.cancel()
            raise LLMUnavailable("Réponse IA incomplète. Veuillez réessayer.") from e
        except Exception as e:
            f_admin.cancel(); f_cctp.cancel()
            raise LLMUnavailable("Service IA momentanément indisponible. Réessayez.") from e
        if not isinstance(data, dict):
            f_admin.cancel(); f_cctp.cancel()
            raise LLMUnavailable("Réponse IA inexploitable. Veuillez réessayer.")
        # Administratif = best-effort : fusionné dans `data`.
        partiel_ko = False
        try:
            admin = f_admin.result()
            if isinstance(admin, dict):
                for k in ("ccap", "clauses_rse", "pieces_dce", "pieces_candidature", "conseils", "garde_fous"):
                    if k in admin:
                        data[k] = admin[k]
            else:
                partiel_ko = True
        except Exception:
            partiel_ko = True
        # CCTP = best-effort.
        cctp_sections = []
        try:
            cctp = f_cctp.result()
            if isinstance(cctp, dict):
                cctp_sections = [s for s in (cctp.get("cctp_sections") or []) if isinstance(s, dict)]
            else:
                partiel_ko = True
        except Exception:
            partiel_ko = True
    finally:
        ex.shutdown(wait=False)   # ne bloque jamais l'appelant
    data["cctp_sections"] = cctp_sections

    result = _assemble(data, objet, type_marche, proc, partiel_ko)
    # On conserve les champs de saisie (notamment le DÉPARTEMENT) dans le DCE : un DCE
    # rechargé garde son territoire → le sourcing/diffusion reste territorialisé même hors
    # du formulaire. (Le formulaire « Créer » est repeuplé depuis `_inputs` à l'ouverture.)
    result["_inputs"] = {
        "dept": (besoin.get("dept") or "").strip()[:3],
        "montant_estime": besoin.get("montant_estime"),
        "duree_mois": besoin.get("duree_mois"),
        "lieu": (besoin.get("lieu") or "").strip()[:120],
        "contraintes": (besoin.get("contraintes") or "").strip()[:2000],
        "exigences_env": (besoin.get("exigences_env") or "").strip()[:2000],
        "exigences_sociales": (besoin.get("exigences_sociales") or "").strip()[:2000],
        "allotissement": besoin.get("allotissement") or "auto",
    }
    return result


def _assemble(data: dict, objet: str, type_marche: str, proc: dict, partiel_ko: bool = False) -> dict:
    """Normalise la sortie LLM, ré-injecte la procédure déterministe, VÉRIFIE la
    cohérence métier (somme des pondérations, présence d'un critère environnemental)
    et ajoute les métadonnées (échéance RSE, disclaimer, note sourcing Pilier 2)."""
    crit = data.get("criteres") or {}
    liste = [c for c in (crit.get("liste") or []) if isinstance(c, dict)]
    allot = data.get("allotissement") or {}
    lots = [l for l in (allot.get("lots") or []) if isinstance(l, dict)]
    recommande = bool(allot.get("recommande", len(lots) > 1))

    # ── Vérifications déterministes (on ne fait pas une confiance aveugle au LLM) ──
    avertissements = []
    somme = sum(_pond(c.get("ponderation")) for c in liste)
    if liste and abs(somme - 100) > 1:
        avertissements.append(f"La somme des pondérations des critères vaut {somme} (et non 100) "
                              "— à corriger avant publication.")
    if liste and not _a_critere_env(liste):
        avertissements.append(f"Aucun critère d'attribution environnemental détecté : OBLIGATOIRE "
                              f"à compter du {DATE_OBLIG_ENV} (art. 35 loi Climat & Résilience). À ajouter.")
    rse = data.get("clauses_rse") or {}
    if not [e for e in (rse.get("environnementales") or []) if str(e).strip()]:
        avertissements.append(f"Aucune condition d'exécution environnementale : OBLIGATOIRE à compter "
                              f"du {DATE_OBLIG_ENV} (art. L2112-2 CCP). À ajouter.")
    if not recommande and not (allot.get("motivation_lot_unique") or "").strip():
        avertissements.append("Lot unique proposé sans motivation : le non-allotissement DOIT être "
                              "motivé (art. L2113-11 CCP) et tracé (R2113-2/R2113-3).")
    if partiel_ko:
        avertissements.append("Une partie du document (CCTP et/ou volets administratifs) n'a pas pu "
                              "être générée — relancez la génération pour l'obtenir.")

    return {
        "objet": (data.get("objet") or objet).strip(),
        "type_marche": type_marche,
        "synthese_besoin": (data.get("synthese_besoin") or "").strip(),
        # Procédure = la nôtre (déterministe), pas celle qu'aurait pu inventer le LLM.
        "procedure": proc,
        "allotissement": {
            "recommande": recommande,
            "principe": (allot.get("principe") or "").strip(),
            "motivation_lot_unique": (allot.get("motivation_lot_unique") or "").strip(),
            "lots": lots,
            "note_sourcing": "Lancez l'analyse de sourcing pour compter, par lot, les PME et "
                             "groupements réellement capables (et le risque d'infructuosité).",
        },
        "criteres": {"liste": liste, "note": (crit.get("note") or "").strip()},
        "cctp_sections": [s for s in (data.get("cctp_sections") or []) if isinstance(s, dict)],
        "ccap": data.get("ccap") or {},
        "clauses_rse": rse,
        "pieces_dce": [str(p) for p in (data.get("pieces_dce") or [])],
        "pieces_candidature": [str(p) for p in (data.get("pieces_candidature") or [])],
        "conseils": [str(c) for c in (data.get("conseils") or [])],
        "garde_fous": [str(g) for g in (data.get("garde_fous") or [])],
        "avertissements": avertissements,
        "echeance_rse": f"À compter du {DATE_OBLIG_ENV}, toute consultation doit comporter au moins "
                        "une condition d'exécution environnementale (art. L2112-2 CCP) ET au moins un "
                        "critère d'attribution environnemental (art. 35 loi n°2021-1104).",
        "disclaimer": "Projet généré par IA, à faire valider par votre service juridique / "
                      "un acheteur public avant publication. Ne constitue pas un conseil juridique.",
    }


def _pond(v) -> int:
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return 0


def _a_critere_env(liste) -> bool:
    """Au moins un critère dont le nom évoque l'environnement, avec pondération > 0."""
    for c in liste:
        nom = str(c.get("critere", "")).lower()
        if _pond(c.get("ponderation")) > 0 and any(m in nom for m in _ENV_MARKERS):
            return True
    return False
