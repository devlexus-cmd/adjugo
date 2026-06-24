"""
Moteur de scoring DÉTERMINISTE, reproductible et explicable.
Chaque critère renvoie (points, max, statut, détail). Une donnée manquante a le
statut « inconnu » et rapporte 0 — jamais un bonus inventé. Le LLM ne produit
aucun score ici.

Barèmes documentés ci-dessous (modifiables sans toucher à la logique).
"""
import re
from typing import Optional

from app.sourcing.schemas import NormalizedTender, NormalizedCompany, Score, ScoreCriterion

# ── Barème AO (somme des max = 100) ──
TENDER_WEIGHTS = {
    "cpv": 25,        # adéquation métier (CPV/descripteur vs spécialités client)
    "zone": 20,       # zone géographique
    "montant": 15,    # budget dans la fourchette du client
    "deadline": 15,   # délai de réponse encore ouvert / suffisant
    "exclusion": 15,  # absence de mots-clés exclus
    "procedure": 10,  # type de marché / procédure acceptée
}
# ── Barème co-traitant (somme des max = 100) ──
# Fondé sur des signaux RÉELS et VÉRIFIABLES de l'API recherche-entreprises (SIRENE).
COMPANY_WEIGHTS = {
    "activite": 22,        # adéquation NAF / besoin du lot
    "etat": 18,            # entreprise active (non cessée/radiée) — éliminatoire
    "zone": 14,            # implantation vs lieu d'exécution
    "anciennete": 14,      # date_creation : stabilité (>3 ans)
    "capacite": 12,        # tranche d'effectif salarié
    "etablissements": 8,   # nombre d'établissements ouverts
    "categorie": 6,        # PME / ETI / GE
    "verif": 6,            # SIRET confirmé au registre
}


def _split(s) -> list:
    if not s:
        return []
    if isinstance(s, list):
        return [str(x).strip().lower() for x in s if str(x).strip()]
    return [p.strip().lower() for p in re.split(r"[,;]", str(s)) if p.strip()]


def score_tender(t: NormalizedTender, company: Optional[dict], criteria: Optional[dict]) -> Score:
    crit = criteria or {}
    comp = company or {}
    b = []

    # 1. Adéquation métier (CPV/descripteur ↔ spécialités/CPV client)
    cpv_targets = _split(crit.get("codes_cpv"))                    # codes numériques
    text_targets = _split(crit.get("specialites")) + _split(crit.get("qualifications"))
    targets = cpv_targets + text_targets
    text_blob = " ".join([t.objet or "", t.lieu or ""]).lower()
    blob_words = set(re.split(r"\W+", text_blob))
    if not targets:
        b.append(ScoreCriterion(key="cpv", label="Adéquation métier", points=0,
                                max_points=TENDER_WEIGHTS["cpv"], status="inconnu",
                                detail="Aucune spécialité/CPV défini dans vos critères"))
    else:
        hits = []
        # CPV : match par préfixe DÉLIMITÉ sur les codes CPV réels de l'avis (≥4 chiffres
        # communs), pas une sous-chaîne dans un blob (fini les faux positifs "4521").
        tender_cpv = [str(c).strip() for c in (t.cpv or []) if str(c).strip()]
        for ct in cpv_targets:
            digits = re.sub(r"\D", "", ct)
            if digits and any(tc.startswith(digits[:4]) or digits.startswith(tc[:4])
                              for tc in tender_cpv if re.sub(r"\D", "", tc)):
                hits.append(ct)
        # Spécialités/qualifs : match par MOT entier dans l'objet/lieu (pas sous-chaîne).
        for tt in text_targets:
            toks = [w for w in re.split(r"\W+", tt) if len(w) > 3]
            if toks and any(w in blob_words for w in toks):
                hits.append(tt)
        hits = list(dict.fromkeys(hits))
        pts = min(TENDER_WEIGHTS["cpv"], TENDER_WEIGHTS["cpv"] * len(hits) / 2) if hits else 0
        b.append(ScoreCriterion(key="cpv", label="Adéquation métier", points=round(pts),
                                max_points=TENDER_WEIGHTS["cpv"],
                                status="ok" if hits else "partiel",
                                detail=f"Correspondances : {', '.join(hits[:3]) or 'aucune'}"))
    # blob conservé pour les autres critères (mots-clés exclus)
    blob = (" ".join(t.cpv) + " " + text_blob).lower()

    # 2. Zone géographique
    zones = _split(crit.get("departements")) + [(comp.get("postal_code") or "")[:2]]
    zones = [z for z in zones if z]
    if not t.departements:
        b.append(ScoreCriterion(key="zone", label="Zone géographique", points=0,
                                max_points=TENDER_WEIGHTS["zone"], status="inconnu",
                                detail="Lieu d'exécution non précisé dans l'avis"))
    elif zones and any(d[:2] in zones for d in t.departements):
        b.append(ScoreCriterion(key="zone", label="Zone géographique",
                                points=TENDER_WEIGHTS["zone"], max_points=TENDER_WEIGHTS["zone"],
                                status="ok", detail=f"Département {', '.join(t.departements)} dans votre zone"))
    else:
        b.append(ScoreCriterion(key="zone", label="Zone géographique", points=0,
                                max_points=TENDER_WEIGHTS["zone"], status="partiel",
                                detail=f"Hors zone ({', '.join(t.departements)})"))

    # 3. Montant
    bmin, bmax = crit.get("budget_min"), crit.get("budget_max")
    if t.montant_estime is None:
        b.append(ScoreCriterion(key="montant", label="Budget", points=0,
                                max_points=TENDER_WEIGHTS["montant"], status="inconnu",
                                detail="Montant non publié dans l'avis"))
    elif (not bmin or t.montant_estime >= bmin) and (not bmax or t.montant_estime <= bmax):
        # Bornes OUVERTES (comme l'analyse) : un budget seulement MIN ne doit pas marquer
        # « hors fourchette » tout marché au-dessus du seuil (verdict opposé à l'analyse).
        b.append(ScoreCriterion(key="montant", label="Budget", points=TENDER_WEIGHTS["montant"],
                                max_points=TENDER_WEIGHTS["montant"], status="ok",
                                detail=f"{t.montant_estime:,.0f} € dans votre fourchette"))
    else:
        b.append(ScoreCriterion(key="montant", label="Budget", points=0,
                                max_points=TENDER_WEIGHTS["montant"], status="partiel",
                                detail=f"{t.montant_estime:,.0f} € hors fourchette"))

    # 4. Délai
    past = _is_past(t.date_limite)
    if t.date_limite is None:
        b.append(ScoreCriterion(key="deadline", label="Délai de réponse", points=0,
                                max_points=TENDER_WEIGHTS["deadline"], status="inconnu",
                                detail="Date limite non précisée"))
    elif past:
        b.append(ScoreCriterion(key="deadline", label="Délai de réponse", points=0,
                                max_points=TENDER_WEIGHTS["deadline"], status="partiel",
                                detail=f"Échéance dépassée ({t.date_limite})"))
    else:
        b.append(ScoreCriterion(key="deadline", label="Délai de réponse",
                                points=TENDER_WEIGHTS["deadline"], max_points=TENDER_WEIGHTS["deadline"],
                                status="ok", detail=f"Ouvert jusqu'au {t.date_limite}"))

    # 5. Mots-clés exclus
    excluded = _split(crit.get("excluded_keywords"))
    bad = [k for k in excluded if k and k in blob]
    b.append(ScoreCriterion(key="exclusion", label="Mots-clés exclus",
                            points=0 if bad else TENDER_WEIGHTS["exclusion"],
                            max_points=TENDER_WEIGHTS["exclusion"],
                            status="partiel" if bad else "ok",
                            detail=f"Exclu : {bad[0]}" if bad else "Aucun mot-clé exclu"))

    # 6. Procédure — une procédure RESTREINTE/négociée présélectionne les candidats :
    # une PME ne peut pas y répondre librement → score partiel, pas plein.
    pmax = TENDER_WEIGHTS["procedure"]
    proc_l = (t.procedure or "").lower()
    if not t.procedure:
        b.append(ScoreCriterion(key="procedure", label="Procédure", points=0,
                                max_points=pmax, status="inconnu", detail="Procédure non précisée"))
    elif any(k in proc_l for k in ("restreint", "négoci", "negoci", "dialogue", "concours")):
        b.append(ScoreCriterion(key="procedure", label="Procédure", points=round(pmax * 0.4),
                                max_points=pmax, status="partiel",
                                detail=f"{t.procedure} — accès restreint (présélection requise)"))
    else:
        b.append(ScoreCriterion(key="procedure", label="Procédure", points=pmax,
                                max_points=pmax, status="ok", detail=t.procedure))

    # Score rescalé sur les critères DISPONIBLES : une donnée absente (« inconnu », ex.
    # montant jamais publié par la source) ne pénalise plus mécaniquement le score —
    # elle est simplement exclue du dénominateur. « partiel » (donnée présente mais non
    # conforme) compte bien 0. Reste déterministe et explicable.
    achievable = sum(c.max_points for c in b if c.status != "inconnu")
    earned = sum(c.points for c in b)
    total = round(earned / achievable * 100) if achievable else 0
    # Adéquation évaluable UNIQUEMENT si l'utilisateur a renseigné de quoi juger le « fit » :
    # des spécialités/CPV/qualifications OU une zone cible. Sinon le score ne reflète que
    # la validité de l'avis (délai/procédure), pas l'adéquation au client → on le signale.
    fit_assessable = bool(targets) or bool(_split(crit.get("departements")))
    return Score(total=max(0, min(100, total)), breakdown=b, fit_assessable=fit_assessable)


def score_company(c: NormalizedCompany, need_trade_label: str = "",
                  tender_departements: Optional[list] = None,
                  lot_montant: Optional[float] = None) -> Score:
    out = []
    need = (need_trade_label or "").lower()
    W = COMPANY_WEIGHTS

    # 1. Adéquation métier (NAF) — 22
    label = (c.naf_label or "").lower()
    if not c.naf:
        out.append(_crit("activite", "Adéquation métier", 0, W["activite"], "inconnu",
                         "Code NAF non disponible"))
    elif need and (need in label or label in need or _share_words(need, label)):
        out.append(_crit("activite", "Adéquation métier", W["activite"], W["activite"], "ok",
                         f"NAF {c.naf} — {c.naf_label}"))
    elif need:
        out.append(_crit("activite", "Adéquation métier", round(W["activite"] * 0.4), W["activite"],
                         "partiel", f"NAF {c.naf} — à confirmer pour « {need_trade_label} »"))
    else:
        out.append(_crit("activite", "Adéquation métier", round(W["activite"] * 0.6), W["activite"],
                         "partiel", f"NAF {c.naf} — {c.naf_label}"))

    # 2. État actif — 18 (signal éliminatoire : société cessée ou radiée)
    if c.etat_administratif is None:
        out.append(_crit("etat", "Entreprise active", 0, W["etat"], "inconnu",
                         "État administratif non disponible"))
    elif c.etat_administratif == "A" and not c.date_fermeture:
        out.append(_crit("etat", "Entreprise active", W["etat"], W["etat"], "ok",
                         "Active au registre SIRENE"))
    else:
        out.append(_crit("etat", "Entreprise active", 0, W["etat"], "partiel",
                         "Cessée / radiée" + (f" le {c.date_fermeture}" if c.date_fermeture else "")))

    # 3. Zone géographique — 14 (vs lieu d'exécution du marché)
    deps = [d[:2] for d in (tender_departements or [])]
    if not c.departement:
        out.append(_crit("zone", "Zone géographique", 0, W["zone"], "inconnu",
                         "Adresse non disponible"))
    elif deps and c.departement in deps:
        out.append(_crit("zone", "Zone géographique", W["zone"], W["zone"], "ok",
                         f"Implantée dans le {c.departement}"))
    elif deps:
        out.append(_crit("zone", "Zone géographique", round(W["zone"] * 0.5), W["zone"], "partiel",
                         f"Département {c.departement} (hors lieu d'exécution)"))
    else:
        out.append(_crit("zone", "Zone géographique", round(W["zone"] * 0.5), W["zone"], "partiel",
                         f"Département {c.departement} — lieu du marché non précisé"))

    # 4. Ancienneté — 14 (date_creation : stabilité)
    age = _age_years(c.date_creation)
    if age is None:
        out.append(_crit("anciennete", "Ancienneté", 0, W["anciennete"], "inconnu",
                         "Date de création non disponible"))
    elif age >= 3:
        out.append(_crit("anciennete", "Ancienneté", W["anciennete"], W["anciennete"], "ok",
                         f"{age} ans d'existence"))
    elif age >= 1:
        out.append(_crit("anciennete", "Ancienneté", round(W["anciennete"] * 0.5), W["anciennete"],
                         "partiel", f"{age} an(s) — jeune entreprise"))
    else:
        out.append(_crit("anciennete", "Ancienneté", 0, W["anciennete"], "partiel",
                         "Moins d'un an d'existence"))

    # 5. Capacité (tranche d'effectif salarié) — 12
    if c.effectif is None:
        out.append(_crit("capacite", "Capacité (effectif)", 0, W["capacite"], "inconnu",
                         "Tranche d'effectif non publiée"))
    elif c.effectif >= 5:
        out.append(_crit("capacite", "Capacité (effectif)", W["capacite"], W["capacite"], "ok",
                         f"~{c.effectif} salariés"))
    else:
        out.append(_crit("capacite", "Capacité (effectif)", round(W["capacite"] * 0.5), W["capacite"],
                         "partiel", f"~{c.effectif} salarié(s) — petite structure"))

    # 6. Présence opérationnelle (établissements ouverts) — 8
    nb = c.nb_etablissements_ouverts
    if nb is None:
        out.append(_crit("etablissements", "Établissements ouverts", 0, W["etablissements"],
                         "inconnu", "Nombre non disponible"))
    elif nb >= 1:
        out.append(_crit("etablissements", "Établissements ouverts", W["etablissements"],
                         W["etablissements"], "ok", f"{nb} établissement(s) ouvert(s)"))
    else:
        out.append(_crit("etablissements", "Établissements ouverts", 0, W["etablissements"],
                         "partiel", "Active mais aucun établissement ouvert"))

    # 7. Catégorie de taille — 6 (PME / ETI / GE)
    cat = (c.categorie or "").upper()
    if not cat:
        out.append(_crit("categorie", "Catégorie de taille", 0, W["categorie"], "inconnu",
                         "Catégorie non renseignée"))
    elif cat in ("ETI", "GE"):
        out.append(_crit("categorie", "Catégorie de taille", W["categorie"], W["categorie"], "ok",
                         cat))
    else:
        out.append(_crit("categorie", "Catégorie de taille", round(W["categorie"] * 0.66),
                         W["categorie"], "partiel", cat))

    # 8. SIRET vérifié — 6 (confirmé au registre officiel)
    out.append(_crit("verif", "SIRET vérifié", W["verif"] if c.siret_verified else 0, W["verif"],
                     "ok" if c.siret_verified else "inconnu",
                     c.siret or "SIRET non confirmé"))

    total = round(sum(x.points for x in out))

    # ── Red-flags & badges (uniquement sur des données vérifiables) ──
    flags = list(c.red_flags or [])
    if c.procedure_collective:
        flags.append(f"Procédure collective : {c.procedure_collective}")
        total = min(total, 20)            # plafond : risque de défaillance majeur (BODACC)
    if c.nb_etablissements_ouverts == 0 and c.etat_administratif == "A":
        flags.append("Active mais aucun établissement ouvert")
    if c.resultat_net is not None and c.resultat_net < 0:
        flags.append("Dernier résultat net négatif")
    flags = list(dict.fromkeys(flags))     # dédoublonnage en gardant l'ordre
    c.red_flags = flags

    badges = []
    if c.est_rge:
        badges.append("RGE")
    if c.est_qualiopi:
        badges.append("Qualiopi")

    note_parts = []
    if badges:
        note_parts.append("Certifié " + ", ".join(badges))
    if flags:
        note_parts.append("⚠ " + " ; ".join(flags))
    note = ". ".join(note_parts)

    return Score(total=max(0, min(100, total)), breakdown=out, note=note)


# ── helpers ──
def _crit(key: str, label: str, points: float, max_points: float,
          status: str, detail: str = "") -> ScoreCriterion:
    return ScoreCriterion(key=key, label=label, points=points,
                          max_points=max_points, status=status, detail=detail)


def _age_years(date_str: Optional[str]) -> Optional[int]:
    """Ancienneté en années pleines depuis date_creation (ISO). None si absente/illisible."""
    if not date_str:
        return None
    from datetime import datetime, date
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return max(0, years)


def _share_words(a: str, b: str) -> bool:
    wa = {w for w in re.split(r"\W+", a) if len(w) > 3}
    wb = {w for w in re.split(r"\W+", b) if len(w) > 3}
    return bool(wa & wb)


def _is_past(date_str: Optional[str]) -> bool:
    if not date_str:
        return False
    from datetime import datetime, date
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date() < date.today()
    except (ValueError, TypeError):
        return False


# ================================================================
# COMPLEMENTARITY GRAPH — score de SYNERGIE d'un co-traitant
# Mesure ce que le candidat APPORTE au groupement (vs l'entreprise pilote
# et le marché), pas seulement sa fiabilité intrinsèque.
#   Complémentarité métier 40 · Ancrage territorial 35 · Fiabilité & certifs 25
# ================================================================
def _wset(s: str) -> set:
    import re as _re
    return {w for w in _re.split(r"\W+", str(s).lower()) if len(w) > 3}


def _dep_of_postal(cp) -> str:
    cp = str(cp or "").strip()
    return cp[:2] if len(cp) >= 2 and cp[:2].isdigit() else ""


def synergy_score(candidate, lead: dict = None, tender_departements=None, need_label: str = "") -> dict:
    """Score de synergie 0-100 du candidat vs l'entreprise pilote + le marché."""
    lead = lead or {}
    deps = [str(d)[:2] for d in (tender_departements or []) if d]
    bd = []

    # 1) Complémentarité métier (40) — couvre un besoin que le pilote n'assure pas
    cand = _wset((candidate.naf_label or "") + " " + (need_label or ""))
    needw = _wset(need_label)
    lead_words = _wset(" ".join(str(q.get("name", q) if isinstance(q, dict) else q)
                                for q in (lead.get("qualifications") or [])) + " " + str(lead.get("code_ape", "")))
    redundant = bool(cand & lead_words)
    if needw and (cand & needw):
        comp = 33 if redundant else 40
        dcomp = (f"Couvre le besoin « {need_label} »"
                 + (" (proche de votre activité)" if redundant else " que vous n'assurez pas — complémentaire"))
    elif needw:
        comp, dcomp = 20, "Métier à confirmer vs le besoin recherché"
    else:
        comp, dcomp = 26, "Métier potentiellement complémentaire"
    bd.append({"key": "complementarite", "label": "Complémentarité métier", "points": comp, "max": 40, "detail": dcomp})

    # 2) Ancrage territorial (35) — implantation locale = bonus RSE/carbone du dossier
    lead_dep = _dep_of_postal(lead.get("postal_code"))
    if deps and candidate.departement in deps:
        terr = 35
        d = "Implanté sur le lieu d'exécution"
        if lead_dep and lead_dep not in deps:
            d += " — apporte l'ancrage local que vous n'avez pas (RSE/carbone)"
    elif not deps:
        terr, d = 18, "Lieu d'exécution non précisé"
    else:
        terr, d = 9, f"Hors lieu d'exécution (dépt {candidate.departement or 'n/d'})"
    bd.append({"key": "territoire", "label": "Ancrage territorial", "points": terr, "max": 35, "detail": d})

    # 3) Fiabilité & qualifications (25) — réutilise la fiabilité + certifs
    rel = round((candidate.score.total if candidate.score else 50) / 100 * 18)
    certs, cl = 0, []
    if candidate.est_rge:
        certs += 4; cl.append("RGE")
    if candidate.est_qualiopi:
        certs += 3; cl.append("Qualiopi")
    fiab = min(25, rel + certs)
    bd.append({"key": "fiabilite", "label": "Fiabilité & qualifications", "points": fiab, "max": 25,
               "detail": f"Fiabilité {candidate.score.total if candidate.score else '—'}/100"
                         + (" · " + ", ".join(cl) if cl else "")})

    # 4) Expérience marchés publics (bonus, DECP) — « a déjà gagné des marchés publics »
    wins = int(getattr(candidate, "past_wins", 0) or 0)
    if wins >= 1:
        exp = min(10, 3 + wins)
        dexp = f"A déjà remporté {wins} marché(s) public(s) (source DECP)"
        if getattr(candidate, "last_win_date", None):
            dexp += f", dernier le {candidate.last_win_date}"
        bd.append({"key": "experience", "label": "Expérience marchés publics", "points": exp, "max": 10, "detail": dexp})
    else:
        exp = 0

    total = min(100, comp + terr + fiab + exp)
    headline = "Forte synergie" if total >= 70 else ("Synergie correcte" if total >= 45 else "Synergie faible")
    note = ("Inclut l'historique réel de marchés publics gagnés (DECP)." if wins
            else "Aucun marché public gagné trouvé en source DECP pour ce SIRET.")
    return {"total": total, "headline": headline, "breakdown": bd, "note": note}
