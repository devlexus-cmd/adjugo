"""
AVIS DE PUBLICITÉ (AAPC) + MÉTHODE DE NOTATION — assemblés DÉTERMINISTE depuis un DCE.

Pas de LLM : l'avis d'appel à la concurrence et la méthode de notation se déduisent des
champs structurés du DCE (objet, procédure, allotissement, critères, durée). Instantané,
robuste, et applicable à n'importe quel DCE déjà généré ou enregistré. Texte PROJET à
compléter (mentions « [à compléter] » pour les éléments propres à la collectivité).
"""


from app.services.format import format_eur


def _s(v):
    return str(v if v is not None else "").strip()


def _eur(v):
    return format_eur(v, " € HT", fallback="[montant à préciser]")


def _forme_prix(dce: dict) -> str:
    """Mention de la forme du prix + pièce financière cohérente (DPGF vs BPU/DQE)."""
    tp = _s((dce.get("ccap") or {}).get("type_prix"))
    if not tp:
        return ""
    low = tp.lower()
    if any(k in low for k in ("unitaire", "bordereau", "bons de commande", "bon de commande")):
        piece = " (bordereau des prix unitaires + DQE à joindre)"
    elif "forfait" in low or "global" in low:
        piece = " (décomposition du prix global et forfaitaire – DPGF – à joindre)"
    else:
        piece = ""
    return tp + piece


def build_avis(dce: dict) -> str:
    """Avis adapté au RÉGIME de passation : un gré à gré (dispense) ne fait pas l'objet d'un
    AAPC ; une procédure adaptée ou formalisée, oui (avec les mentions propres au formalisé)."""
    dce = dce or {}
    proc = dce.get("procedure") or {}
    if _s(proc.get("code")) == "mna":          # gré à gré / dispense → pas d'appel à la concurrence
        return _avis_gre_a_gre(dce, proc)
    return _avis_concurrence(dce, proc)


def _avis_gre_a_gre(dce: dict, proc: dict) -> str:
    """Pas d'AAPC pour un marché de gré à gré : note de bonnes pratiques à la place."""
    L = ["MARCHÉ SANS PUBLICITÉ NI MISE EN CONCURRENCE PRÉALABLES (GRÉ À GRÉ)", ""]
    L.append("Au vu du montant estimé, ce marché relève d'une dispense de procédure "
             "(art. R2122-8 CCP) : AUCUN avis d'appel à la concurrence n'est requis.")
    L.append("Objet : " + (_s(dce.get("objet")) or "[à préciser]") + ".")
    forme = _forme_prix(dce)
    if forme:
        L.append("Forme du prix : " + forme + ".")
    L.append("")
    L.append("Bonnes pratiques (bon emploi des deniers publics) :")
    L.append("• Consulter plusieurs fournisseurs (au moins 3 devis conseillés) et tracer le choix.")
    L.append("• Ne PAS scinder artificiellement le besoin pour rester sous le seuil — le seuil "
             "s'apprécie sur la valeur TOTALE estimée du besoin.")
    L.append("• Respecter l'égalité de traitement, prévenir les conflits d'intérêts et éviter "
             "de solliciter toujours les mêmes opérateurs (faire jouer la concurrence).")
    L.append("")
    L.append("— Note générée par Adjugo, à valider. Un gré à gré ne dispense pas du respect "
             "des principes de la commande publique.")
    return "\n".join(L)


def _avis_concurrence(dce: dict, proc: dict) -> str:
    """Texte d'avis d'appel à la concurrence (AAPC) adapté à MAPA ou formalisé."""
    allot = dce.get("allotissement") or {}
    lots = [l for l in (allot.get("lots") or []) if isinstance(l, dict)]
    crit = [c for c in ((dce.get("criteres") or {}).get("liste") or []) if isinstance(c, dict)]
    formalise = (_s(proc.get("code")) == "formalise")
    delai = proc.get("delai_min_jours")

    L = []
    L.append("AVIS D'APPEL À LA CONCURRENCE")
    L.append("")
    L.append("1. Identité du pouvoir adjudicateur : [Nom de la collectivité], [adresse], "
             "[code postal et ville]. Profil acheteur : [URL du profil acheteur].")
    L.append("2. Objet du marché : " + (_s(dce.get("objet")) or "[objet à préciser]") + ".")
    if _s(dce.get("type_marche")):
        L.append("3. Type de marché : " + _s(dce.get("type_marche")) + ".")
    L.append("4. Procédure de passation : " + (_s(proc.get("type")) or "[à préciser]") + ".")
    if _s(proc.get("publicite")):
        L.append("   Modalités de publicité : " + _s(proc.get("publicite")) + ".")
    if formalise:
        L.append("   Publication au BOAMP ET au JOUE (formulaire eForms standard) ; le présent "
                 "avis tient lieu d'avis de marché.")

    if lots:
        L.append("5. Allotissement : marché alloti en " + str(len(lots)) + " lots :")
        for l in lots:
            L.append("   - Lot " + _s(l.get("numero")) + " : " + _s(l.get("intitule")) +
                     ((" — " + _s(l.get("description"))) if _s(l.get("description")) else ""))
        L.append("   Les candidats peuvent présenter une offre pour un, plusieurs ou la totalité "
                 "des lots [préciser un éventuel nombre maximal de lots attribuables à un même candidat].")
    else:
        L.append("5. Allotissement : lot unique." +
                 (("  Motivation : " + _s(allot.get("motivation_lot_unique")))
                  if _s(allot.get("motivation_lot_unique")) else ""))

    if crit:
        L.append("6. Critères d'attribution (offre économiquement la plus avantageuse) :")
        for c in crit:
            try:
                p = int(float(c.get("ponderation") or 0))
            except (TypeError, ValueError):
                p = 0
            L.append("   - " + _s(c.get("critere")) + " : " + str(p) + " %")

    L.append("6 bis. Conditions de participation : capacités professionnelles, techniques et "
             "financières exigées — [à compléter] ; le candidat ne doit pas être dans un cas "
             "d'interdiction de soumissionner (art. L2141-1 et s. CCP).")
    L.append("6 ter. Critères de sélection des candidatures : [à compléter].")
    forme = _forme_prix(dce)
    if forme:
        L.append("6 quater. Forme du prix : " + forme + ".")
    L.append("7. Durée du marché / délai d'exécution : [à compléter]. Variantes : [autorisées / "
             "non autorisées — à préciser].")
    if formalise:
        delai_txt = (f"{delai or 35} jours minimum à compter de l'envoi du présent avis "
                     "(procédure formalisée, art. R2161-2 et s. ; réductions possibles : 30 j si "
                     "remise électronique des offres, 15 j avec avis de préinformation ou urgence)")
    elif delai:
        delai_txt = f"délai indicatif d'environ {delai} jours"
    else:
        delai_txt = ("délai raisonnable et proportionné — la DAJ recommande ≈ 22 jours en MAPA "
                     "publié ; un délai trop court pénalise les PME")
    L.append("8. Date limite de réception des offres : [JJ/MM/AAAA à HH:MM] "
             "(" + delai_txt + ").")
    L.append("   Délai de validité des offres : [à compléter, ex. 120 jours].")
    L.append("9. Modalités essentielles de remise des offres : dossier de consultation et "
             "dépôt des plis par voie ÉLECTRONIQUE sur le profil acheteur ; les candidats "
             "peuvent présenter une offre en groupement (co-traitance).")
    L.append("10. Renseignements complémentaires : [service / contact — à compléter].")
    L.append("11. Procédures de recours : Tribunal administratif compétent — [nom / adresse à "
             "compléter]. Référé précontractuel possible AVANT la signature (art. L551-1 du code "
             "de justice administrative), référé contractuel APRÈS la signature (art. L551-13).")
    if formalise:
        L.append("    Un délai de suspension (standstill) d'au moins 11 jours (16 jours si "
                 "notification non électronique) est respecté entre l'information des candidats "
                 "évincés et la signature du marché.")
    averts = [a for a in (dce.get("avertissements") or []) if _s(a)]
    if averts:
        L.append("")
        L.append("⚠️ Points à corriger AVANT publication (contrôles automatiques du projet) :")
        for a in averts:
            L.append("   - " + _s(a))
    L.append("")
    L.append("Date d'envoi du présent avis à la publication : [à compléter].")
    L.append("")
    L.append("— Projet d'avis généré par Adjugo, à valider et compléter avant publication.")
    return "\n".join(L)


def build_methode_notation(dce: dict) -> str:
    """Méthode de notation des offres (complément du règlement de la consultation)."""
    crit = [c for c in ((dce.get("criteres") or {}).get("liste") or []) if isinstance(c, dict)]
    L = []
    L.append("MÉTHODE DE NOTATION DES OFFRES")
    L.append("")
    if len(crit) == 1:
        L.append("Le marché est attribué à l'offre économiquement la plus avantageuse, appréciée "
                 "au regard du SEUL critère ci-dessous.")
    else:
        L.append("Le marché est attribué à l'offre économiquement la plus avantageuse, appréciée "
                 "selon les critères pondérés ci-dessous. La note globale d'une offre est la somme "
                 "des notes pondérées de chaque critère (sur 100 points).")
    L.append("")
    has_prix = has_sub = False
    for c in crit:
        try:
            p = int(float(c.get("ponderation") or 0))
        except (TypeError, ValueError):
            p = 0
        nom = _s(c.get("critere"))
        low = nom.lower()
        L.append("• " + nom + " (" + str(p) + " points) :")
        if any(m in low for m in ("prix", "coût", "cout", "tarif", "économ", "econom", "financ")):
            has_prix = True
            L.append("   Note = (offre la moins-disante / offre considérée) × " + str(p) +
                     " points. L'offre la moins chère obtient la note maximale ; les offres "
                     "anormalement basses font l'objet d'une demande de justification écrite "
                     "avant tout rejet (art. R2152-1 à R2152-3 CCP).")
        else:
            L.append("   Note attribuée selon un barème détaillé dans le règlement de la "
                     "consultation (sous-critères, échelle de 0 à " + str(p) + " points).")
        sub = [s for s in (c.get("sous_criteres") or []) if _s(s)]
        if sub:
            has_sub = True
            L.append("   Sous-critères : " + " ; ".join(_s(s) for s in sub) + ".")
    if not crit:
        L.append("• [Critères et pondérations à définir.]")
    L.append("")
    if has_sub:
        L.append("Les sous-critères susceptibles d'exercer une influence sur le classement des "
                 "offres sont portés à la connaissance des candidats (information préalable, avec "
                 "leur pondération ou hiérarchisation).")
    if not has_prix:
        L.append("Rappel : le critère prix doit être noté par une formule proportionnelle "
                 "(offre la moins-disante / offre × points).")
    L.append("En cas d'égalité, [préciser la règle de départage].")
    L.append("")
    L.append("— Projet de méthode de notation généré par Adjugo, à valider.")
    return "\n".join(L)
