"""
Classement des partenaires du RÉSEAU ADJUGO (co-traitance v2, innovation B) — service PUR,
déterministe, 0 LLM, 0 base, 0 réseau.

Règle produit (décision fondateur n° 2) : UN SEUL pourcentage est affiché à l'utilisateur,
le score de groupement (app.services.groupement_scoring, « seul 54 % → avec X 81 % »). Ce
module CLASSE et EXPLIQUE : il renvoie un RANG et des CRITÈRES (statut + phrase + source +
date), jamais un total ni un « % ». Le barème interne sert uniquement à ordonner :

    métier du lot 35 · zone d'intervention 25 · fiabilité vérifiée 15 ·
    expérience des marchés publics 15 · capacité et disponibilité 10

Confiance vérifiable (SIRENE, BODACC, DECP) — jamais de note, d'avis ni d'étoile. Le compteur de
groupements « marqués déposés » sur Adjugo est DÉCLARATIF (statut renseigné par le chef de file) :
badge de niveau « info », daté, jamais « vérifié ». Formulations honnêtes et datées :
  - « Aucun avis de procédure collective trouvé au JJ/MM (recherche BODACC) » (absence de
    résultat ≠ preuve d'absence) ; None = « non vérifié » ;
  - « Au moins N marchés publics publiés dans DECP » (DECP est partiel et en retard) ;
  - « Inscrite au registre RGE (ADEME) au JJ/MM — domaine à vérifier ».

Entrées : des dicts (cf. app.services.partner_network.profile_dict), une date `today` passée
par l'appelant (déterminisme : aucune lecture d'horloge ici). Tris explicites partout.
"""
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from app.services.groupement_scoring import _norm_dep

# Poids du classement (internes, jamais affichés comme note).
WEIGHTS = {"metier": 35, "zone": 25, "fiabilite": 15, "experience": 15, "capacite": 10}
CRITERIA_ORDER = ("metier", "zone", "fiabilite", "experience", "capacite")
CRITERIA_LABELS = {
    "metier": "Métier du lot",
    "zone": "Zone d'intervention",
    "fiabilite": "Fiabilité vérifiée (registres publics)",
    "experience": "Expérience des marchés publics",
    "capacite": "Capacité et disponibilité pour ce lot",
}
EXPLICATION_CLASSEMENT = (
    "Classement par métier du lot, zone d'intervention, fiabilité vérifiée dans les registres "
    "publics (SIRENE, BODACC), expérience des marchés publics (DECP, groupements marqués déposés sur Adjugo), puis "
    "capacité et disponibilité. Ce n'est pas une note : le seul pourcentage affiché reste le "
    "score de groupement, calculé quand vous simulez le groupement.")

ROLE_LABELS = {
    "cotraitant": "Partenaire du groupement (co-traitant)",
    "sous_traitant": "Sous-traitant",
    "mandataire": "Chef de file",
}
DISPO_LABELS = {
    "disponible": "Disponible pour de nouveaux marchés",
    "limitee": "Disponibilité limitée",
    "complet": "Plan de charge complet",
}
SIRENE_FRESH_DAYS = 90      # au-delà, la vérification SIRENE ne compte plus dans la fiabilité

_SOURCE_DECLARE = "déclaré par l'entreprise"
_SOURCE_SIRENE = "SIRENE (recherche-entreprises.api.gouv.fr)"
_SOURCE_BODACC = "BODACC (annonces commerciales officielles)"
_SOURCE_DECP = "DECP (données essentielles de la commande publique)"
_SOURCE_ADJUGO = "statut de dépôt renseigné par le chef de file sur Adjugo (déclaratif)"
_SOURCE_DCE = "dossier du marché (DCE)"
_SOURCE_RECHERCHE = "votre recherche"
_SOURCE_RGE = "registre RGE (ADEME), via SIRENE"
_SOURCE_QUALIOPI = "registre Qualiopi, via SIRENE"


# ── Utilitaires ──────────────────────────────────────────────────────────────────────

def _fold(s) -> str:
    try:
        t = unicodedata.normalize("NFKD", str(s or ""))
        t = "".join(c for c in t if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", t.lower()).strip()
    except Exception:
        return str(s or "").lower().strip()


def as_date(v) -> Optional[date]:
    """date | datetime | 'AAAA-MM-JJ…' → date ; tout le reste → None (jamais d'exception)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def jjmm(v) -> str:
    """Date au format JJ/MM (formulations « au JJ/MM »), '' si inconnue."""
    d = as_date(v)
    return d.strftime("%d/%m") if d else ""


def jjmmaaaa(v) -> str:
    d = as_date(v)
    return d.strftime("%d/%m/%Y") if d else ""


def _iso(v) -> Optional[str]:
    d = as_date(v)
    return d.isoformat() if d else None


def trade_labels() -> dict:
    try:
        from app.sourcing.sources.sirene import TRADES
        return {t["key"]: t["label"] for t in TRADES}
    except Exception:
        return {}


def trade_label(key: str) -> str:
    return trade_labels().get(key or "", key or "")


def _money(v) -> str:
    try:
        return f"{float(v):,.0f} € HT".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def _deps(p: dict) -> list:
    out, seen = [], set()
    for d in (p.get("departements") or []):
        n = _norm_dep(d)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


# ── Formulations honnêtes des vérifications ───────────────────────────────────────────

def sirene_label(v: Optional[dict]) -> str:
    if not isinstance(v, dict) or not v.get("etat"):
        return "SIRENE : non vérifié"
    d = jjmm(v.get("checked_at"))
    if v.get("etat") == "actif":
        return f"Entreprise active (SIRENE au {d})" if d else "Entreprise active (SIRENE)"
    if v.get("etat") == "cesse":
        return f"Entreprise cessée selon SIRENE au {d}" if d else "Entreprise cessée selon SIRENE"
    return "SIRENE : non vérifié"


def bodacc_label(v: Optional[dict]) -> str:
    if not isinstance(v, dict) or v.get("found") is None:
        return "BODACC : non vérifié"
    d = jjmm(v.get("checked_at"))
    if v.get("found") is False:
        return (f"Aucun avis de procédure collective trouvé au {d} (recherche BODACC)" if d
                else "Aucun avis de procédure collective trouvé (recherche BODACC)")
    nature = (v.get("nature") or "procédure collective").strip()
    when = jjmmaaaa(v.get("date"))
    suffix = f" le {when}" if when else ""
    if v.get("ongoing"):
        return f"Procédure collective publiée au BODACC{suffix} : {nature}"
    return f"Procédure collective clôturée publiée au BODACC{suffix} : {nature}"


def decp_label(v: Optional[dict]) -> str:
    if not isinstance(v, dict) or v.get("count") is None:
        return "DECP : non vérifié"
    d = jjmm(v.get("checked_at"))
    n = int(v.get("count") or 0)
    au = f" (au {d})" if d else ""
    if n <= 0:
        return f"Aucun marché trouvé dans DECP au {d}" if d else "Aucun marché trouvé dans DECP"
    return f"Au moins {n} marché{'s' if n > 1 else ''} public{'s' if n > 1 else ''} publié{'s' if n > 1 else ''} dans DECP{au}"


def adjugo_label(n, when=None) -> str:
    """« N groupements marqués déposés sur Adjugo (déclaratif) » : c'est le chef de file qui
    marque le marché déposé ; Adjugo ne voit pas le dépôt sur la plateforme de l'acheteur."""
    n = int(n or 0)
    d = jjmm(when)
    au = f" au {d}" if d else ""
    return (f"{n} groupement{'s' if n > 1 else ''} marqué{'s' if n > 1 else ''} déposé{'s' if n > 1 else ''} "
            f"sur Adjugo (déclaratif){au}")


# ── Badges sourcés et datés ──────────────────────────────────────────────────────────

def badges(p: dict) -> list:
    """Badges de confiance VÉRIFIABLES uniquement, chacun avec sa source et sa date.
    niveau ∈ ok | info | alerte | non_verifie. Ordre fixe (déterminisme)."""
    out = []
    vs = p.get("verified_sirene") if isinstance(p.get("verified_sirene"), dict) else None
    vb = p.get("verified_bodacc") if isinstance(p.get("verified_bodacc"), dict) else None
    vd = p.get("verified_decp") if isinstance(p.get("verified_decp"), dict) else None

    etat = (vs or {}).get("etat")
    out.append({"key": "sirene", "label": sirene_label(vs), "source": _SOURCE_SIRENE,
                "date": _iso((vs or {}).get("checked_at")),
                "niveau": "ok" if etat == "actif" else ("alerte" if etat == "cesse" else "non_verifie")})
    if vs and vs.get("est_rge") is True:
        d = jjmm(vs.get("checked_at"))
        out.append({"key": "rge", "label": f"Inscrite au registre RGE (ADEME) au {d} — domaine à vérifier"
                    if d else "Inscrite au registre RGE (ADEME) — domaine à vérifier",
                    "source": _SOURCE_RGE, "date": _iso(vs.get("checked_at")), "niveau": "info"})
    if vs and vs.get("est_qualiopi") is True:
        d = jjmm(vs.get("checked_at"))
        out.append({"key": "qualiopi", "label": f"Certifiée Qualiopi (registre) au {d}" if d
                    else "Certifiée Qualiopi (registre)",
                    "source": _SOURCE_QUALIOPI, "date": _iso(vs.get("checked_at")), "niveau": "info"})

    found = (vb or {}).get("found")
    out.append({"key": "bodacc", "label": bodacc_label(vb), "source": _SOURCE_BODACC,
                "date": _iso((vb or {}).get("checked_at")),
                "niveau": ("non_verifie" if found is None else
                           "ok" if found is False else
                           "alerte" if (vb or {}).get("ongoing") else "info")})

    cnt = (vd or {}).get("count")
    out.append({"key": "decp", "label": decp_label(vd), "source": _SOURCE_DECP,
                "date": _iso((vd or {}).get("checked_at")),
                "niveau": "non_verifie" if cnt is None else ("ok" if int(cnt or 0) > 0 else "info")})

    n = int(p.get("groupements_deposes") or 0)
    if n > 0:
        when = p.get("groupements_checked_at")
        out.append({"key": "adjugo", "label": adjugo_label(n, when), "source": _SOURCE_ADJUGO,
                    "date": _iso(when), "niveau": "info"})
    return out


# ── Capacités (fiche de l'annuaire) : chacune avec sa date et sa source ───────────────

def capacites(p: dict) -> list:
    decl = _iso(p.get("declared_at"))
    labels = trade_labels()
    out = []
    metiers = [m for m in (p.get("metiers") or []) if m]
    if metiers:
        out.append({"key": "metiers", "label": "Métiers",
                    "valeur": ", ".join(labels.get(m, m) for m in metiers),
                    "source": _SOURCE_DECLARE, "date": decl})
    deps = _deps(p)
    if deps:
        out.append({"key": "zones", "label": "Zones d'intervention (départements)",
                    "valeur": ", ".join(deps), "source": _SOURCE_DECLARE, "date": decl})
    roles = [r for r in (p.get("roles_acceptes") or []) if r in ROLE_LABELS]
    if roles:
        out.append({"key": "roles", "label": "Rôles acceptés",
                    "valeur": ", ".join(ROLE_LABELS[r] for r in roles),
                    "source": _SOURCE_DECLARE, "date": decl})
    if p.get("lot_max_eur"):
        out.append({"key": "lot_max", "label": "Taille de lot maximale acceptée",
                    "valeur": _money(p.get("lot_max_eur")), "source": _SOURCE_DECLARE, "date": decl})
    dispo = p.get("disponibilite") or ""
    if dispo in DISPO_LABELS:
        val = DISPO_LABELS[dispo]
        if p.get("dispo_jusqua"):
            val += f" (jusqu'au {jjmmaaaa(p.get('dispo_jusqua'))})"
        out.append({"key": "disponibilite", "label": "Disponibilité", "valeur": val,
                    "source": _SOURCE_DECLARE, "date": decl})
    vs = p.get("verified_sirene") if isinstance(p.get("verified_sirene"), dict) else {}
    if vs.get("categorie"):
        out.append({"key": "categorie", "label": "Catégorie d'entreprise", "valeur": str(vs["categorie"]),
                    "source": _SOURCE_SIRENE, "date": _iso(vs.get("checked_at"))})
    if vs.get("est_rge") is True:
        out.append({"key": "rge", "label": "Registre RGE (ADEME)", "valeur": "inscrite — domaine à vérifier",
                    "source": _SOURCE_RGE, "date": _iso(vs.get("checked_at"))})
    if vs.get("est_qualiopi") is True:
        out.append({"key": "qualiopi", "label": "Qualiopi", "valeur": "certifiée (registre)",
                    "source": _SOURCE_QUALIOPI, "date": _iso(vs.get("checked_at"))})
    vd = p.get("verified_decp") if isinstance(p.get("verified_decp"), dict) else {}
    if vd.get("count") is None:
        val = "non vérifié"
    elif int(vd.get("count") or 0) > 0:
        val = f"au moins {int(vd['count'])}"
    else:
        val = "aucun trouvé"
    out.append({"key": "marches_publics", "label": "Marchés publics publiés (DECP)", "valeur": val,
                "source": _SOURCE_DECP, "date": _iso(vd.get("checked_at"))})
    n = int(p.get("groupements_deposes") or 0)
    if n > 0:
        out.append({"key": "groupements_adjugo", "label": "Groupements marqués déposés sur Adjugo (déclaratif)",
                    "valeur": str(n), "source": _SOURCE_ADJUGO, "date": _iso(p.get("groupements_checked_at"))})
    return out


def public_card(p: dict) -> dict:
    """Fiche PUBLIQUE = sous-ensemble STRICT. Jamais : email, téléphone, CA, effectif exact,
    documents, résultats, liste de masquage, compteur d'apparitions, identifiants internes.
    Les références n'apparaissent QUE si le partenaire en a choisi (sinon la clé est absente)."""
    labels = trade_labels()
    dispo = p.get("disponibilite") or ""
    siren = str(p.get("siren") or "")
    card = {
        "profile_id": p.get("public_id"),
        "name": p.get("name") or "",
        "siren": siren,
        "lien_annuaire": (f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}"
                          if re.fullmatch(r"\d{9}", siren) else None),
        "city": p.get("city") or "",
        "departement": p.get("departement") or "",
        "metiers": [{"key": m, "label": labels.get(m, m)} for m in (p.get("metiers") or []) if m],
        "departements": _deps(p),
        "roles_acceptes": [{"value": r, "label": ROLE_LABELS[r]} for r in (p.get("roles_acceptes") or [])
                           if r in ROLE_LABELS],
        "disponibilite": ({"value": dispo, "label": DISPO_LABELS[dispo], "jusqua": _iso(p.get("dispo_jusqua"))}
                          if dispo in DISPO_LABELS else None),
        "lot_max_eur": p.get("lot_max_eur"),
        "presentation": p.get("presentation") or "",
        "codes_cpv": [c for c in (p.get("codes_cpv") or []) if c],
        "declare_le": _iso(p.get("declared_at")),
        "badges": badges(p),
        "capacites": capacites(p),
    }
    refs = [r for r in (p.get("references_publiques") or []) if isinstance(r, dict) and r.get("intitule")]
    if refs:
        card["references"] = [{"intitule": r.get("intitule"), "client": r.get("client") or "",
                               "annee": r.get("annee"), "source": "choisie et rendue publique par l'entreprise"}
                              for r in refs]
    return card


# ── Classement pour UN lot ───────────────────────────────────────────────────────────

def _cpv_match(lot_cpv: list, p_cpv: list) -> str:
    """Premier code du profil qui partage la même famille (3 premiers chiffres) qu'un code du
    marché, sinon ''."""
    fams = {re.sub(r"\D", "", str(c))[:3] for c in (lot_cpv or []) if len(re.sub(r"\D", "", str(c))) >= 3}
    for c in sorted(str(x) for x in (p_cpv or [])):
        digits = re.sub(r"\D", "", c)
        if len(digits) >= 3 and digits[:3] in fams:
            return c
    return ""


def score_lot(lot: dict, p: dict, today: date) -> tuple:
    """(total interne, critères affichables) pour un profil sur un lot. Le total NE SORT PAS
    de ce module (il ordonne seulement). Critère = {key, label, statut, detail, source, date}."""
    lot = lot or {}
    decl = p.get("declared_at")
    decl_txt = f"déclaré par l'entreprise le {jjmm(decl)}" if jjmm(decl) else "déclaré par l'entreprise"
    crits, total = [], 0

    def add(key, pts, statut, detail, source, when):
        nonlocal total
        total += max(0, min(int(pts), WEIGHTS[key]))
        crits.append({"key": key, "label": CRITERIA_LABELS[key], "statut": statut, "detail": detail,
                      "source": source, "date": _iso(when)})

    # 1) Métier (35)
    metier = lot.get("metier") or ""
    metiers = set(p.get("metiers") or [])
    cpv = _cpv_match(lot.get("cpv") or [], p.get("codes_cpv") or [])
    if metier and metier in metiers:
        add("metier", 35, "ok", f"Métier « {trade_label(metier)} » {decl_txt}", _SOURCE_DECLARE, decl)
    elif cpv:
        cible = "de votre recherche" if (lot.get("contexte") or "") == "annuaire" else "du marché"
        add("metier", 20, "partiel", f"Code CPV {cpv} proche {cible}, {decl_txt}", _SOURCE_DECLARE, decl)
    else:
        lab = trade_label(metier) if metier else "du lot"
        add("metier", 0, "non", f"Métier « {lab} » non déclaré par l'entreprise", _SOURCE_DECLARE, decl)

    # 2) Zone (25). Chaque phrase dit d'où vient la donnée : zones déclarées, siège SIRENE
    # (code postal du siège lu dans le registre) ou code postal déclaré (profil entreprise).
    dep = _norm_dep(lot.get("departement") or "")
    zones = _deps(p)
    vs = p.get("verified_sirene") if isinstance(p.get("verified_sirene"), dict) else {}
    siege_sirene = _norm_dep(vs.get("code_postal") or "")
    adresse_declaree = _norm_dep(p.get("postal_code") or p.get("departement") or "")
    note = (" — département supposé (le vôtre) : le dossier n'indique pas le lieu d'exécution"
            if dep and lot.get("departement_suppose") else "")
    if not dep:
        if (lot.get("contexte") or "") == "annuaire":
            add("zone", 10, "partiel", "Aucun département choisi dans votre recherche", _SOURCE_RECHERCHE, None)
        else:
            add("zone", 10, "partiel", "Lieu d'exécution non précisé dans le dossier du marché", _SOURCE_DCE, None)
    elif dep in zones:
        add("zone", 25, "ok", f"Intervient dans le {dep} ({decl_txt}){note}", _SOURCE_DECLARE, decl)
    elif siege_sirene and siege_sirene == dep:
        add("zone", 25, "ok", f"Siège dans le {dep} (siège SIRENE){note}", _SOURCE_SIRENE, vs.get("checked_at"))
    elif adresse_declaree and adresse_declaree == dep:
        add("zone", 25, "ok", f"Adresse dans le {dep} (code postal déclaré){note}", _SOURCE_DECLARE, decl)
    else:
        add("zone", 0, "non", f"N'indique pas intervenir dans le {dep}{note}", _SOURCE_DECLARE, decl)

    # 3) Fiabilité vérifiée (15) : SIRENE actif récent 8 + aucun avis BODACC trouvé 7.
    pts, parts, alerte = 0, [], False
    sir_date = as_date(vs.get("checked_at"))
    if vs.get("etat") == "actif" and sir_date and (today - sir_date).days <= SIRENE_FRESH_DAYS:
        pts += 8
        parts.append(sirene_label(vs))
    else:
        parts.append(sirene_label(vs) if vs.get("etat") else "SIRENE : non vérifié récemment")
        if vs.get("etat") == "cesse":
            alerte = True
    vb = p.get("verified_bodacc") if isinstance(p.get("verified_bodacc"), dict) else {}
    if vb.get("found") is False:
        pts += 7
    elif vb.get("found") is True and vb.get("ongoing"):
        alerte = True
    parts.append(bodacc_label(vb or None))
    statut = "alerte" if alerte else ("ok" if pts >= 15 else ("partiel" if pts > 0 else "non"))
    dates = [d for d in (as_date(vs.get("checked_at")), as_date(vb.get("checked_at"))) if d]
    add("fiabilite", pts, statut, " · ".join(parts), f"{_SOURCE_SIRENE} ; {_SOURCE_BODACC}",
        min(dates) if dates else None)

    # 4) Expérience des marchés publics (15) : DECP (au moins N) + dépôts réels Adjugo.
    vd = p.get("verified_decp") if isinstance(p.get("verified_decp"), dict) else {}
    cnt = vd.get("count")
    pts, parts = 0, [decp_label(vd or None)]
    if cnt is not None:
        n = int(cnt or 0)
        pts += 12 if n >= 5 else (8 if n >= 1 else 0)
    ng = int(p.get("groupements_deposes") or 0)
    if ng > 0:
        pts += 3
        parts.append(adjugo_label(ng, p.get("groupements_checked_at")))
    statut = "ok" if pts >= 12 else ("partiel" if pts > 0 else "non")
    add("experience", pts, statut, " · ".join(parts), f"{_SOURCE_DECP} ; {_SOURCE_ADJUGO}", vd.get("checked_at"))

    # 5) Capacité et disponibilité (10) : rôle accepté 4 + disponibilité 3 + taille de lot 3.
    pts, parts = 0, []
    role = lot.get("role") or "cotraitant"
    roles = [r for r in (p.get("roles_acceptes") or []) if r in ROLE_LABELS]
    if not roles or role in roles:
        pts += 4 if roles else 2
        parts.append(f"Accepte le rôle « {ROLE_LABELS.get(role, role)} »" if roles
                     else "Rôles acceptés non précisés")
    else:
        parts.append(f"N'accepte pas le rôle « {ROLE_LABELS.get(role, role)} »")
    dispo = p.get("disponibilite") or ""
    jusqua = as_date(p.get("dispo_jusqua"))
    if jusqua and jusqua < today:
        parts.append("Disponibilité à mettre à jour (date dépassée)")
        pts += 1
    elif dispo == "disponible":
        pts += 3
        parts.append(DISPO_LABELS[dispo])
    elif dispo == "limitee":
        pts += 1
        parts.append(DISPO_LABELS[dispo])
    elif dispo == "complet":
        parts.append(DISPO_LABELS[dispo])
    else:
        parts.append("Disponibilité non précisée")
    lot_max = p.get("lot_max_eur")
    montant = lot.get("montant")
    if lot_max and montant:
        if float(lot_max) >= float(montant):
            pts += 3
            parts.append(f"Lots jusqu'à {_money(lot_max)}")
        else:
            parts.append(f"Lot plus gros que sa taille maximale déclarée ({_money(lot_max)})")
    elif lot_max:
        pts += 1
        parts.append(f"Lots jusqu'à {_money(lot_max)} (montant du lot non connu)")
    else:
        parts.append("Taille de lot maximale non précisée")
    statut = "ok" if pts >= 8 else ("partiel" if pts > 0 else "non")
    add("capacite", pts, statut, " · ".join(parts), _SOURCE_DECLARE, decl)

    order = {k: i for i, k in enumerate(CRITERIA_ORDER)}
    crits.sort(key=lambda c: order[c["key"]])
    return total, crits


def rank(lot: dict, profiles: list, today: date, limit: int = 5) -> list:
    """Classe les profils pour UN lot. Seuls les profils dont le métier (ou, à défaut, une
    famille CPV) correspond sont retenus. Renvoie [{profile_id, rang, criteres, badges}] —
    aucun total, aucun pourcentage. Ordre : total interne décroissant, puis nom, puis id
    (stable et déterministe)."""
    scored = []
    for p in profiles or []:
        if not isinstance(p, dict) or not p.get("public_id"):
            continue
        total, crits = score_lot(lot, p, today)
        if crits and crits[0]["statut"] == "non":     # métier non couvert : pas un candidat
            continue
        scored.append((total, _fold(p.get("name")), str(p.get("public_id")), p, crits))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    out = []
    for i, (_t, _n, _pid, p, crits) in enumerate(scored[:max(0, int(limit))], start=1):
        out.append({"profile_id": p.get("public_id"), "rang": i, "criteres": crits})
    return out


def count_matches(lot: dict, profiles: list, today: date) -> int:
    """Nombre de profils correspondant au lot (même règle que rank, sans limite)."""
    n = 0
    for p in profiles or []:
        if not isinstance(p, dict) or not p.get("public_id"):
            continue
        _t, crits = score_lot(lot, p, today)
        if crits and crits[0]["statut"] != "non":
            n += 1
    return n
