"""
AVIS DE PUBLICITÉ (AAPC) + MÉTHODE DE NOTATION — assemblés DÉTERMINISTE depuis un DCE.

Pas de LLM : l'avis d'appel à la concurrence et la méthode de notation se déduisent des
champs structurés du DCE (objet, procédure, allotissement, critères, durée). Instantané,
robuste, et applicable à n'importe quel DCE déjà généré ou enregistré. Texte PROJET à
compléter (mentions « [à compléter] » pour les éléments propres à la collectivité).
"""


def _s(v):
    return str(v if v is not None else "").strip()


def _eur(v):
    try:
        return f"{int(round(float(v))):,}".replace(",", " ") + " € HT"
    except (ValueError, TypeError):
        return "[montant à préciser]"


def build_avis(dce: dict) -> str:
    """Texte d'avis d'appel à la concurrence (AAPC), prêt à adapter puis publier."""
    dce = dce or {}
    proc = dce.get("procedure") or {}
    allot = dce.get("allotissement") or {}
    lots = [l for l in (allot.get("lots") or []) if isinstance(l, dict)]
    crit = [c for c in ((dce.get("criteres") or {}).get("liste") or []) if isinstance(c, dict)]
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

    if lots:
        L.append("5. Allotissement : marché alloti en " + str(len(lots)) + " lots :")
        for l in lots:
            L.append("   - Lot " + _s(l.get("numero")) + " : " + _s(l.get("intitule")) +
                     ((" — " + _s(l.get("description"))) if _s(l.get("description")) else ""))
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

    L.append("7. Durée du marché / délai d'exécution : [à compléter].")
    delai_txt = (f"délai indicatif d'environ {delai} jours" if delai
                 else "délai raisonnable et proportionné à la complexité")
    L.append("8. Date limite de réception des offres : [JJ/MM/AAAA à HH:MM] "
             "(" + delai_txt + " à compter de l'envoi du présent avis).")
    L.append("9. Modalités essentielles de remise des offres : dossier de consultation et "
             "dépôt des plis par voie ÉLECTRONIQUE sur le profil acheteur ; les candidats "
             "peuvent présenter une offre en groupement (co-traitance).")
    L.append("10. Renseignements complémentaires : [service / contact — à compléter].")
    L.append("11. Instance chargée des procédures de recours : Tribunal administratif "
             "compétent — [à compléter].")
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
    L.append("Le marché est attribué à l'offre économiquement la plus avantageuse, appréciée "
             "selon les critères pondérés ci-dessous. La note globale d'une offre est la somme "
             "des notes pondérées de chaque critère (sur 100 points).")
    L.append("")
    has_prix = False
    for c in crit:
        try:
            p = int(float(c.get("ponderation") or 0))
        except (TypeError, ValueError):
            p = 0
        nom = _s(c.get("critere"))
        low = nom.lower()
        L.append("• " + nom + " (" + str(p) + " points) :")
        if "prix" in low or "coût" in low or "cout" in low:
            has_prix = True
            L.append("   Note = (offre la moins-disante / offre considérée) × " + str(p) +
                     " points. L'offre la moins chère obtient la note maximale ; les offres "
                     "anormalement basses font l'objet d'une demande de justification (art. R2152-3 CCP).")
        else:
            L.append("   Note attribuée selon un barème détaillé dans le règlement de la "
                     "consultation (sous-critères, échelle de 0 à " + str(p) + " points).")
        sub = [s for s in (c.get("sous_criteres") or []) if _s(s)]
        if sub:
            L.append("   Sous-critères : " + " ; ".join(_s(s) for s in sub) + ".")
    if not crit:
        L.append("• [Critères et pondérations à définir.]")
    L.append("")
    if not has_prix:
        L.append("Rappel : le critère prix doit être noté par une formule proportionnelle "
                 "(offre la moins-disante / offre × points).")
    L.append("En cas d'égalité, [préciser la règle de départage].")
    L.append("")
    L.append("— Projet de méthode de notation généré par Adjugo, à valider.")
    return "\n".join(L)
