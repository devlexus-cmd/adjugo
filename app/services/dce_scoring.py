"""
Scoring Go/No-Go DÉTERMINISTE d'un DCE.

L'IA EXTRAIT les faits du DCE (budget, lieu, CA exigé, qualifications, délai…) ; ce
module CALCULE le score à partir d'un barème ouvert et reproductible — pas l'IA. Deux
analyses du même DCE donnent donc le MÊME score (contrairement à un score sorti du LLM).
Chaque point est rattaché à un critère lisible → défendable devant un acheteur public.

Barème (somme = 100) :
  Adéquation métier 30 · Zone 20 · Budget 15 · Capacité financière (CA) 15 ·
  Qualifications exigées 10 · Délai de réponse 10
Donnée manquante = score partiel prudent, jamais un bonus inventé (anti-hallucination).
"""
import re
from datetime import date, datetime


def _amount(s):
    """Extrait le plus grand montant d'un texte (« 150 000 EUR HT » → 150000)."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s)
    # Forme ABRÉGÉE avec devise (« 2 M€ », « 1,5 M EUR HT », « 800 k€ ») : sans ça « 1,5 M€ »
    # était lu « 15 » → marché faussement « hors fourchette ». On EXIGE le symbole monétaire
    # après le multiplicateur pour ne JAMAIS confondre avec « 500 m² » ou « 5 mois ».
    mm = re.search(r"(\d+(?:[.,]\d+)?)\s*(milliards?|millions?|md|m|k)\s*(?:€|eur)", t, re.I)
    if mm:
        val = float(mm.group(1).replace(",", "."))
        suf = mm.group(2).lower()
        if suf in ("md", "milliard", "milliards"):
            mult = 1_000_000_000
        elif suf in ("m", "million", "millions"):
            mult = 1_000_000
        else:
            mult = 1_000
        return int(val * mult)
    best = None
    for n in re.findall(r"\d[\d  .]*\d|\d", str(s)):
        v = n.replace(" ", "").replace(" ", "").replace(".", "")
        try:
            iv = int(v)
            best = iv if best is None else max(best, iv)
        except ValueError:
            pass
    return best


def _dept(s):
    """Département depuis « Quimper (29) », « Ajaccio (2A) » ou un code postal. DOM-TOM (97x/98x)
    sur 3 chiffres (Guadeloupe 971 ≠ Réunion 974) ; Corse (CP 20xxx) mappée 2A (20000-20199,
    Corse-du-Sud) / 2B (20200-20999, Haute-Corse) — sinon toute la Corse passait « hors zone »."""
    t = str(s or "")
    m = re.search(r"\((\d{2,3}|2[ABab])\)", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(\d{5})\b", t)
    if m:
        cp = m.group(1)
        if cp[:2] == "20":
            return "2A" if cp < "20200" else "2B"
        return cp[:3] if cp[:2] in ("97", "98") else cp[:2]
    return ""


def _days_until(s):
    """Nombre de jours jusqu'à une date « 15/06/2026 » (None si non parsable)."""
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", str(s or ""))
    if not m:
        return None
    try:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return (d - date.today()).days
    except ValueError:
        return None


# Vocabulaire GÉNÉRIQUE de la commande publique : présent dans presque tous les DCE ET
# profils → un recoupement sur ces seuls mots ne prouve AUCUNE adéquation métier réelle.
_GENERIC = {
    "marche", "marche", "public", "publics", "publique", "travaux", "service", "services",
    "prestation", "prestations", "fourniture", "fournitures", "technique", "techniques",
    "prix", "offre", "offres", "candidat", "entreprise", "societe", "projet", "lot", "lots",
    "realisation", "mise", "oeuvre", "place", "ensemble", "divers", "general", "generale",
    "qualite", "delai", "delais", "client", "maitre", "ouvrage", "consultation",
}


def _words(s):
    return {w for w in re.split(r"\W+", str(s).lower()) if len(w) > 3}


def _crit(key, label, points, maxp, status, detail):
    return {"key": key, "label": label, "points": round(points), "max_points": maxp,
            "status": status, "detail": detail}


def score_dce(details: dict, company: dict = None, criteria: dict = None) -> dict:
    """Renvoie {score, go_decision, breakdown[]} de façon déterministe."""
    details = details or {}
    company = company or {}
    criteria = criteria or {}
    bd = []

    # Vocabulaire du marché (pour l'adéquation métier)
    quals_req = details.get("qualifications_requises") or []
    crit_att = details.get("criteres_attribution") or []
    hay = " ".join(str(x) for x in [
        details.get("intitule_marche", ""), details.get("type_marche", ""),
        " ".join(map(str, quals_req)),
        " ".join(c.get("critere", "") if isinstance(c, dict) else str(c) for c in crit_att),
    ]).lower()
    hay_w = _words(hay)

    # Vocabulaire de l'entreprise
    specs = [s.strip().lower() for s in re.split(r"[,;]", str(criteria.get("specialites", ""))) if s.strip()]
    quals_ent = company.get("qualifications") or []
    ent_qual_w = _words(" ".join((q.get("name", "") + " " + q.get("detail", "")) if isinstance(q, dict) else str(q)
                                 for q in quals_ent))
    ent_w = set().union(*[_words(s) for s in specs]) if specs else set()
    ent_w |= ent_qual_w | _words(company.get("name", ""))

    # 1) Adéquation métier (30) — recoupement sur des mots SIGNIFIANTS (hors vocabulaire
    # générique « travaux/technique/prix… » qui matche tout et donnait de faux « ok »).
    meaningful = (hay_w - _GENERIC) & (ent_w - _GENERIC)
    if not ent_w:
        bd.append(_crit("metier", "Adéquation métier", 18, 30, "inconnu",
                        "Profil entreprise incomplet (renseignez vos spécialités/qualifications)"))
    elif meaningful:
        bd.append(_crit("metier", "Adéquation métier", 30, 30, "ok",
                        "Le marché recoupe votre activité (" + ", ".join(sorted(meaningful)[:3]) + ")"))
    else:
        bd.append(_crit("metier", "Adéquation métier", 8, 30, "partiel",
                        "Recoupement faible avec votre activité — à vérifier"))

    # 2) Zone géographique (20)
    def _dep(x):                       # normalise un dépt saisi (métropole 2, DOM-TOM 3, Corse 2A/2B/20)
        x = str(x).strip().upper()
        if x[:2] in ("2A", "2B"):
            return x[:2]
        if x[:2] == "20":              # saisie numérique Corse, ambiguë (2A ou 2B)
            return "20"
        return x[:3] if x[:2] in ("97", "98") else x[:2]

    def _in_zone(ld, deps):            # lieu dans la zone ? tolérant Corse/DOM-TOM
        ld = str(ld).strip().upper()
        for d in deps:
            d = str(d).strip().upper()
            if ld == d:
                return True
            # Corse : « 20 » (ambigu) tolère 2A/2B et inversement ; mais 2A ≠ 2B.
            if ld in ("20", "2A", "2B") and d in ("20", "2A", "2B") and "20" in (ld, d):
                return True
            # DOM-TOM : un dépt saisi sur 2 chiffres (97/98) couvre tout son préfixe.
            if d in ("97", "98") and ld[:2] == d:
                return True
        return False
    raw = criteria.get("departements") or []
    deps = [_dep(d) for d in raw if str(d).strip()] if isinstance(raw, list) else [_dep(d) for d in re.split(r"[,;\s]+", str(raw)) if d.strip()]
    explicit = bool(deps)              # l'utilisateur a-t-il VRAIMENT défini une zone ?
    if not deps and company.get("postal_code"):
        deps = [_dep(company["postal_code"])]
    ld = _dept(details.get("lieu_execution", ""))
    if not deps:
        bd.append(_crit("zone", "Zone géographique", 12, 20, "inconnu", "Zone d'intervention non renseignée"))
    elif ld and _in_zone(ld, deps):
        bd.append(_crit("zone", "Zone géographique", 20, 20, "ok", f"Lieu d'exécution dans votre zone ({ld})"))
    elif ld and explicit:
        bd.append(_crit("zone", "Zone géographique", 5, 20, "partiel", f"Hors zone d'intervention (dépt {ld})"))
    elif ld:
        # zone déduite du SEUL code postal (jamais définie) → on ne pénalise pas « hors zone »
        bd.append(_crit("zone", "Zone géographique", 12, 20, "inconnu", "Zone d'intervention non renseignée — précisez vos départements"))
    else:
        bd.append(_crit("zone", "Zone géographique", 11, 20, "inconnu", "Lieu d'exécution non précisé"))

    # 3) Budget (15)
    b = _amount(details.get("budget_estime"))
    bmin, bmax = _amount(criteria.get("budget_min")), _amount(criteria.get("budget_max"))
    if b is None:
        bd.append(_crit("budget", "Budget", 9, 15, "inconnu", "Montant non publié"))
    elif (not bmin or b >= bmin) and (not bmax or b <= bmax):
        bd.append(_crit("budget", "Budget", 15, 15, "ok", "Dans votre fourchette de marchés"))
    else:
        bd.append(_crit("budget", "Budget", 6, 15, "partiel", "Hors de votre fourchette habituelle"))

    # 4) Capacité financière — CA minimum exigé vs votre CA (15)
    ca_req = _amount(details.get("ca_minimum_requis"))
    ca_ent = _amount(company.get("ca_n1"))
    if not ca_req:
        bd.append(_crit("capacite", "Capacité financière", 12, 15, "ok", "Pas de CA minimum exigé / non précisé"))
    elif ca_ent and ca_ent >= ca_req:
        bd.append(_crit("capacite", "Capacité financière", 15, 15, "ok",
                        f"CA exigé {ca_req:,}€ ≤ votre CA".replace(",", " ")))
    elif ca_ent:
        bd.append(_crit("capacite", "Capacité financière", 2, 15, "partiel",
                        f"CA exigé {ca_req:,}€ > votre CA — risque d'inéligibilité".replace(",", " ")))
    else:
        bd.append(_crit("capacite", "Capacité financière", 6, 15, "inconnu",
                        f"CA exigé {ca_req:,}€ — renseignez votre CA pour vérifier".replace(",", " ")))

    # 5) Qualifications exigées (10)
    if not quals_req:
        bd.append(_crit("qualifs", "Qualifications exigées", 8, 10, "ok", "Aucune qualification spécifique exigée"))
    else:
        req_w = _words(" ".join(map(str, quals_req)))
        if req_w & ent_qual_w:
            bd.append(_crit("qualifs", "Qualifications exigées", 10, 10, "ok", "Vos qualifications recoupent les exigences"))
        else:
            bd.append(_crit("qualifs", "Qualifications exigées", 3, 10, "partiel",
                            "Qualifications exigées non couvertes par votre profil — à vérifier"))

    # 6) Délai de réponse (10)
    days = _days_until(details.get("date_limite"))
    if days is None:
        bd.append(_crit("delai", "Délai de réponse", 6, 10, "inconnu", "Date limite non précisée"))
    elif days >= 10:
        bd.append(_crit("delai", "Délai de réponse", 10, 10, "ok", f"{days} jours pour répondre"))
    elif days >= 3:
        bd.append(_crit("delai", "Délai de réponse", 5, 10, "partiel", f"Délai court ({days} jours)"))
    else:
        bd.append(_crit("delai", "Délai de réponse", 1, 10, "partiel",
                        "Échéance dépassée ou imminente" if days < 0 else f"Très peu de temps ({days} j)"))

    total = max(0, min(100, sum(c["points"] for c in bd)))
    try:
        threshold = int(criteria.get("go_threshold") or 65)   # défaut aligné sur le routeur (65) → plus de
    except (ValueError, TypeError):                            # contradiction verdict/détail dans la bande 60-64
        threshold = 65
    try:
        nogo = int(criteria.get("nogo_threshold") or 40)
    except (ValueError, TypeError):
        nogo = 40
    if nogo >= threshold:                       # nogo doit rester strictement sous le seuil « go »
        nogo = max(0, threshold - 1)
    # Garde-fou « extraction vide » : si l'IA n'a RIEN extrait d'exploitable (fichier qui n'est pas
    # un vrai DCE, scan illisible…), on PLAFONNE le score dans la bande « à étudier » — jamais
    # « go / Bon potentiel » sur du vide. Le plafond porte sur le SCORE → le routeur, qui recalcule
    # le verdict à partir du score, le respecte aussi (sinon il écrasait ce garde-fou).
    extracted = any([
        details.get("intitule_marche"), details.get("type_marche"),
        details.get("lieu_execution"), details.get("budget_estime"),
        details.get("ca_minimum_requis"), details.get("date_limite"),
        quals_req, crit_att,
    ])
    if not extracted:
        total = min(total, 50)
    # Bande à DEUX SEUILS, identique au routeur (go_threshold / nogo_threshold) : le verdict
    # affiché (pastille) ne contredit plus le détail du score (avant, score_dce et le routeur
    # utilisaient deux formules différentes → « À étudier » posé sur un détail qui valait rejet).
    if total >= threshold:
        go = "go"
    elif total >= nogo:
        go = "a_etudier"
    else:
        go = "no_go"
    return {"score": total, "go_decision": go, "breakdown": bd, "threshold": threshold,
            "nogo_threshold": nogo, "extracted": bool(extracted)}
