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
    """Département depuis « Quimper (29) » ou un code postal."""
    t = str(s or "")
    m = re.search(r"\((\d{2,3})\)", t) or re.search(r"\b(\d{2})\d{3}\b", t)
    return m.group(1) if m else ""


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
    deps = criteria.get("departements") or []
    deps = [str(d)[:2] for d in deps] if isinstance(deps, list) else [d.strip()[:2] for d in re.split(r"[,;\s]+", str(deps)) if d.strip()]
    if not deps and company.get("postal_code"):
        deps = [str(company["postal_code"])[:2]]
    ld = _dept(details.get("lieu_execution", ""))
    if not deps:
        bd.append(_crit("zone", "Zone géographique", 12, 20, "inconnu", "Zone d'intervention non renseignée"))
    elif ld and ld in deps:
        bd.append(_crit("zone", "Zone géographique", 20, 20, "ok", f"Lieu d'exécution dans votre zone ({ld})"))
    elif ld:
        bd.append(_crit("zone", "Zone géographique", 5, 20, "partiel", f"Hors zone d'intervention (dépt {ld})"))
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
        threshold = int(criteria.get("go_threshold") or 60)
    except (ValueError, TypeError):
        threshold = 60
    if total >= threshold:
        go = "go"
    elif total >= max(35, threshold - 22):
        go = "a_etudier"
    else:
        go = "no_go"
    return {"score": total, "go_decision": go, "breakdown": bd, "threshold": threshold}
