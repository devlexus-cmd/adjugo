"""
Score de GROUPEMENT (co-traitance v2, innovation A) — service PUR, déterministe, 0 LLM.

Idée : « seul 54 % → avec Le Gall Électricité 81 % ». On construit une entreprise VIRTUELLE
(cumul des capacités des membres) et on lui RÉAPPLIQUE le même barème que pour une
entreprise seule (app.services.dce_scoring.score_dce : 30/20/15/15/10/10). Un seul barème,
un seul pourcentage, les mêmes seuils go/nogo que le verdict seul.

Invariants (ne jamais les casser) :
  - ANTI-HALLUCINATION : une capacité INCONNUE (CA non publié, effectif absent) vaut
    « inconnu », jamais un bonus ; un CA manquant compte 0 dans le cumul ET déclenche un
    avertissement explicite ; les exigences viennent des faits extraits du DCE (details),
    jamais devinées.
  - DÉTERMINISME : même entrée → même sortie (aucune date ailleurs que via score_dce pour le
    délai, tris explicites partout, aucun accès DB/réseau).
  - JAMAIS « go_groupement » sans partenaire réel (kind != 'lead') ni sans gain réel.
  - AVERTIR, PAS BLOQUER : un partenaire « déclaré par vous » peut faire basculer le verdict,
    mais l'avertissement le dit noir sur blanc.
  - LANGAGE SIMPLE : « groupement », « partenaire » — jamais « consortium ».

Aucun import de routeur, aucun modèle SQLAlchemy : les appelants passent des dicts
(company_dict / criteria_dict / annuaire Cotraitant / NormalizedCompany SIRENE / saisie).
"""
import re
import unicodedata

from app.services.dce_scoring import score_dce, _amount, _dept, _words, _GENERIC

# Critères du barème score_dce (miroir) + 2 exigences propres aux candidatures groupées
# (références et effectif ne sont pas notés par score_dce mais sont des manques réels).
GAP_KEYS = ("metier", "zone", "capacite", "qualifs", "references", "effectif")

_KINDS = ("lead", "attached", "annuaire", "reseau", "sirene", "saisi", "contribution")
_VERIFIED_SOURCES = ("rne", "sirene", "contribution")

# Qualifications vérifiables par un registre public consulté par Adjugo (API recherche-
# entreprises : est_rge / est_qualiopi). Tout le reste (Qualibat, OPQIBI, SS3/SS4, Qualifelec,
# certifications ISO…) n'est PAS vérifiable automatiquement → « à confirmer auprès du partenaire ».
_REGISTRY_VERIFIABLE = ("rge", "qualiopi")

_LABELS = {
    "metier": "Métier du marché non couvert par votre activité",
    "zone": "Lieu d'exécution hors de votre zone d'intervention",
    "capacite": "Chiffre d'affaires minimum exigé",
    "qualifs": "Qualification(s) exigée(s) non détenue(s)",
    "references": "Références de travaux similaires exigées",
    "effectif": "Effectif minimum exigé",
}
_A_CONFIRMER = " — à confirmer auprès du partenaire"
_NON_RENSEIGNE = "non renseigné"


# ── Petits utilitaires (robustes aux données sales) ───────────────────────────────────

def _fold(s) -> str:
    """minuscules sans accents, espaces normalisés (comparaisons de texte libre)."""
    try:
        t = unicodedata.normalize("NFKD", str(s or ""))
        t = "".join(c for c in t if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", t.lower()).strip()
    except Exception:
        return ""


def _is_unspecified(v) -> bool:
    """« Non specifie dans le DCE », vide, None… ⇒ ni critère ni manque (anti-hallucination)."""
    if v is None or isinstance(v, (bool, dict)):
        return True
    if isinstance(v, (list, tuple)):
        return not any(not _is_unspecified(x) for x in v)
    t = _fold(v)
    if not t or t in ("none", "null", "n/a", "na", "-", "aucun", "aucune", "non"):
        return True
    return bool(re.search(r"non\s+(specifie|precise|indique|renseigne|mentionne|communique)|"
                          r"pas\s+(specifie|precise|indique|mentionne)|non\s+requis|sans\s+objet", t))


def _as_list(v) -> list:
    """str « a, b ; c » / list / None → liste de str non vides (ordre conservé, dédoublonnée)."""
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        items = []
        for x in v:
            if isinstance(x, dict):
                name = str(x.get("name") or x.get("nom") or x.get("label") or "").strip()
                detail = str(x.get("detail") or x.get("description") or "").strip()
                s = (name + (" " + detail if detail else "")).strip()
            else:
                s = str(x or "").strip()
            if s:
                items.append(s)
    else:
        items = [s.strip() for s in re.split(r"[,;\n|]", str(v)) if s.strip()]
    out, seen = [], set()
    for s in items:
        k = _fold(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _norm_dep(x) -> str:
    """Code département normalisé (métropole 2, DOM-TOM 3, Corse 2A/2B/20) — miroir de score_dce."""
    x = str(x or "").strip().upper()
    if not x:
        return ""
    if re.fullmatch(r"\d{5}", x):              # code postal
        return _dept(x)
    if x[:2] in ("2A", "2B"):
        return x[:2]
    if x[:2] == "20":
        return "20"
    if x[:2] in ("97", "98"):
        return x[:3]
    m = re.fullmatch(r"(\d{2,3})", x)
    return m.group(1)[:2] if m else _dept(x)


def _in_zone(ld, deps) -> bool:
    """Lieu d'exécution dans la zone ? Tolérance Corse/DOM-TOM identique à score_dce."""
    ld = str(ld or "").strip().upper()
    if not ld:
        return False
    for d in deps:
        d = str(d).strip().upper()
        if ld == d:
            return True
        if ld in ("20", "2A", "2B") and d in ("20", "2A", "2B") and "20" in (ld, d):
            return True
        if d in ("97", "98") and ld[:2] == d:
            return True
    return False


def _money(v) -> str:
    try:
        return f"{int(round(float(v))):,} €".replace(",", " ")
    except (TypeError, ValueError):
        return _NON_RENSEIGNE


def _first_int(s, patterns=()) -> "int | None":
    """Premier entier d'un texte (« 3 références sur 5 ans » → 3 ; « 10 salariés » → 10)."""
    t = _fold(s)
    if not t:
        return None
    for p in patterns:
        m = re.search(r"(\d+)\s*" + p, t)
        if m:
            return int(m.group(1))
    m = re.search(r"\b(\d+)\b", t)
    return int(m.group(1)) if m else None


def _deps_of_criteria(criteria: dict) -> list:
    raw = (criteria or {}).get("departements") or []
    if isinstance(raw, (list, tuple, set)):
        items = [str(d) for d in raw if str(d).strip()]
    else:
        items = [d for d in re.split(r"[,;\s]+", str(raw)) if d.strip()]
    out, seen = [], set()
    for d in items:
        n = _norm_dep(d)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _market_words(details: dict) -> set:
    """Mots SIGNIFIANTS du marché — même recette que score_dce (adéquation métier)."""
    quals_req = details.get("qualifications_requises") or []
    crit_att = details.get("criteres_attribution") or []
    try:
        hay = " ".join(str(x) for x in [
            details.get("intitule_marche", ""), details.get("type_marche", ""),
            " ".join(map(str, quals_req)) if isinstance(quals_req, (list, tuple)) else str(quals_req),
            " ".join(c.get("critere", "") if isinstance(c, dict) else str(c) for c in crit_att)
            if isinstance(crit_att, (list, tuple)) else str(crit_att),
        ]).lower()
    except Exception:
        hay = ""
    return _words(hay) - _GENERIC


def _required_qual_words(details: dict) -> set:
    quals_req = details.get("qualifications_requises") or []
    try:
        if isinstance(quals_req, (list, tuple)):
            return _words(" ".join(map(str, quals_req)))
        return _words(str(quals_req))
    except Exception:
        return set()


def _member_words(m: dict) -> set:
    """Vocabulaire d'un membre : spécialités + qualifications + nom (comme score_dce)."""
    w = set()
    for s in _as_list(m.get("specialites")):
        w |= _words(s)
    w |= _words(" ".join(m.get("qualifications") or []))
    w |= _words(m.get("name") or "")
    return w - _GENERIC


# ── 1) Normalisation d'un membre ──────────────────────────────────────────────────────

def member_capacities(member: dict) -> dict:
    """Normalise un membre venu de n'importe quelle source en
    {kind, id, invite_id, name, siret, ca_n1: float|None, effectif: int|None,
     qualifications: list[str], specialites: str, departements: list[str], references: list[dict],
     source: str, as_of: str, verified: bool}.
    kind ∈ {'lead','attached','annuaire','reseau','sirene','saisi','contribution'}.
    Accepte : Company/Cotraitant dict (ca_n1, effectif, qualifications str OU list[str|dict],
    specialites, departement/postal_code), NormalizedCompany SIRENE (effectif, naf_label, specialite,
    departement, siret, pas de CA → ca_n1=None), saisie manuelle. CA absent/0 → None (jamais 0
    silencieux) ; 'verified' = source in ('rne','sirene','contribution'). Idempotent, ne lève jamais."""
    m = member if isinstance(member, dict) else {}

    kind = str(m.get("kind") or "").strip().lower()
    source = str(m.get("source") or m.get("capacites_source") or "").strip().lower()
    if kind not in _KINDS:
        if source in ("sirene", "rne"):
            kind = "sirene"
        elif source == "contribution":
            kind = "contribution"
        elif source == "reseau":
            kind = "reseau"
        else:
            kind = "saisi"
    if not source:
        source = {"lead": "profil", "sirene": "sirene", "contribution": "contribution",
                  "reseau": "reseau"}.get(kind, "declare")

    name = str(m.get("name") or m.get("nom") or m.get("company_name") or m.get("company")
               or "Partenaire").strip() or "Partenaire"

    # CA : ca_n1 (Company/Cotraitant), ca (SIRENE/RNE), chiffre_affaires (saisie) — texte accepté.
    ca = None
    for k in ("ca_n1", "ca", "chiffre_affaires"):
        if k in m and m.get(k) not in (None, "", 0, 0.0, "0"):
            try:
                v = _amount(m.get(k))
                if v and float(v) > 0:
                    ca = float(v)
                    break
            except Exception:
                continue

    effectif = None
    for k in ("effectif", "effectif_salarie", "headcount"):
        v = m.get(k)
        if v in (None, "", 0, "0"):
            continue
        try:
            iv = int(float(str(v).replace(" ", "")))
            if iv > 0:
                effectif = iv
                break
        except (TypeError, ValueError):
            n = _first_int(v)
            if n and n > 0:
                effectif = n
                break

    quals = _as_list(m.get("qualifications"))
    for flag, label in (("est_rge", "RGE"), ("est_qualiopi", "Qualiopi")):
        if m.get(flag) is True and not any(_fold(label) in _fold(q) for q in quals):
            quals.append(label)

    spec_raw = m.get("specialites")
    if spec_raw in (None, "", [], ()):
        spec_raw = m.get("specialite") or m.get("naf_label") or m.get("activite") or ""
    specialites = ", ".join(_as_list(spec_raw))

    deps = []
    for k in ("departements", "departement"):
        deps += _as_list(m.get(k))
    for k in ("postal_code", "code_postal"):
        v = m.get(k)
        if v:
            deps.append(str(v))
    departements, seen = [], set()
    for d in deps:
        n = _norm_dep(d)
        if n and n not in seen:
            seen.add(n)
            departements.append(n)

    refs_raw = m.get("references")
    references = []
    if isinstance(refs_raw, (list, tuple)):
        for r in refs_raw:
            if isinstance(r, dict):
                references.append(dict(r))
            elif r not in (None, ""):
                references.append({"name": str(r)})
    elif isinstance(refs_raw, str) and refs_raw.strip():
        references = [{"name": s} for s in _as_list(refs_raw)]

    as_of = m.get("as_of") or m.get("capacites_updated_at") or m.get("freshness_date") or ""
    as_of = str(as_of) if as_of else ""

    rid = m.get("id")
    inv = m.get("invite_id")
    return {
        "kind": kind,
        "id": rid if isinstance(rid, (int, str)) else None,
        "invite_id": inv if isinstance(inv, (int, str)) else None,
        "name": name,
        "siret": str(m.get("siret") or "").replace(" ", "").replace(".", "") or "",
        "ca_n1": ca,
        "effectif": effectif,
        "qualifications": quals,
        "specialites": specialites,
        "departements": departements,
        "references": references,
        "source": source,
        "as_of": as_of,
        "verified": source in _VERIFIED_SOURCES,
    }


# ── 2) Entreprise virtuelle (cumul) ───────────────────────────────────────────────────

_NO_CUMUL = re.compile(r"chaque membre|individuellement|chacun des membres")


def cumulate(members: list, capacites_groupement: str = "") -> dict:
    """Entreprise VIRTUELLE : ca_n1 = somme des CA connus (ca_unknown_members = noms sans CA),
    effectif = somme, qualifications = union, specialites = concat ', ', departements = union,
    references = concat, name = 'Groupement (A + B + C)'.
    RÈGLE : si capacites_groupement contient « chaque membre » / « individuellement » /
    « chacun des membres » → cumul_admis=False : ca_n1 et effectif = ceux du lead seul,
    warning explicite. Renvoie {..., cumul_admis, ca_unknown_members, members, warnings}."""
    norm = [member_capacities(m) for m in (members or []) if isinstance(m, dict)]
    lead = next((m for m in norm if m["kind"] == "lead"), norm[0] if norm else None)
    cumul_admis = not bool(_NO_CUMUL.search(_fold(capacites_groupement)))
    warnings = []

    known = [m for m in norm if m["ca_n1"] is not None]
    unknown = [m["name"] for m in norm if m["ca_n1"] is None]
    if cumul_admis:
        ca = float(sum(m["ca_n1"] for m in known)) if known else None
        effs = [m["effectif"] for m in norm if m["effectif"] is not None]
        eff = int(sum(effs)) if effs else None
    else:
        ca = lead["ca_n1"] if lead else None
        eff = lead["effectif"] if lead else None
        warnings.append("Le règlement exige que chaque membre satisfasse seul : le cumul ne s'applique pas")

    quals, seen = [], set()
    for m in norm:
        for q in m["qualifications"]:
            k = _fold(q)
            if k and k not in seen:
                seen.add(k)
                quals.append(q)
    specs, seen = [], set()
    for m in norm:
        for s in _as_list(m["specialites"]):
            k = _fold(s)
            if k and k not in seen:
                seen.add(k)
                specs.append(s)
    deps, seen = [], set()
    for m in norm:
        for d in m["departements"]:
            if d not in seen:
                seen.add(d)
                deps.append(d)
    refs = []
    for m in norm:
        refs.extend(m["references"])

    names = [m["name"] for m in norm]
    return {
        "name": "Groupement (" + " + ".join(names) + ")" if names else "Groupement",
        "ca_n1": ca,
        "effectif": eff,
        "qualifications": quals,
        "specialites": ", ".join(specs),
        "departements": deps,
        "references": refs,
        "postal_code": None,
        "cumul_admis": cumul_admis,
        "ca_unknown_members": unknown,
        "members": norm,
        "warnings": warnings,
    }


# ── 3) Manques : ce que le marché exige et que l'entreprise n'a pas ───────────────────

def _lots_trades_uncovered(details: dict, company: dict, criteria: dict) -> list:
    """Métiers (clés TRADES) des lots du marché non couverts par l'entreprise."""
    try:
        from app.sourcing.groupement import infer_trade, own_trades, parse_lots
    except Exception:
        return []
    try:
        own = own_trades({
            "specialites": (criteria or {}).get("specialites") or company.get("specialites") or "",
            "qualifications": " ".join(_as_list(company.get("qualifications"))),
            "code_ape": company.get("code_ape") or "",
            "naf_label": company.get("naf_label") or "",
            "name": company.get("name") or "",
        })
        lots = parse_lots(str(details.get("allotissement") or ""))
        labels = [l.get("label", "") for l in lots] or [str(details.get("intitule_marche") or "")]
        trades = []
        for lab in labels:
            t = infer_trade(lab)
            if t and t not in own and t not in trades:
                trades.append(t)
        return sorted(trades)
    except Exception:
        return []


def _qual_trades(details: dict) -> list:
    try:
        from app.sourcing.groupement import infer_trade
    except Exception:
        return []
    out = []
    for q in _as_list(details.get("qualifications_requises")):
        t = infer_trade(q)
        if t and t not in out:
            out.append(t)
    return sorted(out)


def gaps_for(details: dict, lead_company: dict, criteria: dict) -> list:
    """Ce que le marché EXIGE et que l'entreprise SEULE n'a pas. Déterministe, à partir de
    score_dce(details, lead, criteria) + exigences de groupement (références, effectif).
    Chaque gap : {key ∈ GAP_KEYS, label (langage simple), required, have, extrait
    (details.exigences_sources.<clé> ou ''), severity 'bloquant'|'important'|'a_verifier',
    trades (métiers inférés des lots non couverts)}.
    Statut 'inconnu' côté entreprise → 'a_verifier' avec have='non renseigné' (jamais
    'bloquant' sur du vide). 'Non specifie dans le DCE' ⇒ ni critère ni manque."""
    details = details if isinstance(details, dict) else {}
    company = lead_company if isinstance(lead_company, dict) else {}
    criteria = criteria if isinstance(criteria, dict) else {}
    src = details.get("exigences_sources") if isinstance(details.get("exigences_sources"), dict) else {}

    def _extrait(k):
        v = src.get(k)
        return str(v).strip() if isinstance(v, str) else ""

    gaps = []
    try:
        det = score_dce(details, company, criteria)
    except Exception:
        det = {"breakdown": []}
    bd = {c.get("key"): c for c in det.get("breakdown", []) if isinstance(c, dict)}

    # Métier (30) — à partir du statut du barème ; 'inconnu' = profil vide → à vérifier.
    # Un DCE sans objet ni lots n'EXIGE rien de connu → pas de manque (anti-hallucination).
    c = bd.get("metier")
    market_known = bool(_market_words(details)) or not _is_unspecified(details.get("allotissement"))
    if c and market_known and c.get("status") != "ok":
        lots = str(details.get("allotissement") or "").strip()
        req = str(details.get("intitule_marche") or "").strip()
        if lots and not _is_unspecified(lots):
            req = (req + " — " if req else "") + lots
        specs = ", ".join(_as_list(criteria.get("specialites") or company.get("specialites")))
        gaps.append({
            "key": "metier", "label": _LABELS["metier"],
            "required": req[:200] or "métier du marché",
            "have": specs or _NON_RENSEIGNE,
            "extrait": "",
            "severity": "a_verifier" if (c.get("status") == "inconnu" or not specs) else "important",
            "trades": _lots_trades_uncovered(details, company, criteria),
        })

    # Zone (20) — seulement si le DCE PRÉCISE un lieu (sinon rien n'est exigé)
    c = bd.get("zone")
    ld = _dept(details.get("lieu_execution", ""))
    if c and ld and c.get("status") != "ok":
        deps = _deps_of_criteria(criteria)
        gaps.append({
            "key": "zone", "label": _LABELS["zone"],
            "required": f"département {ld} ({str(details.get('lieu_execution') or '').strip()[:80]})",
            "have": ", ".join(deps) if deps else _NON_RENSEIGNE,
            "extrait": "",
            "severity": "important" if (deps and c.get("status") == "partiel") else "a_verifier",
            "trades": [],
        })

    # Capacité financière (15) — CA minimum exigé
    c = bd.get("capacite")
    ca_req = _amount(details.get("ca_minimum_requis")) if not _is_unspecified(details.get("ca_minimum_requis")) else None
    if c and ca_req and c.get("status") != "ok":
        ca_ent = _amount(company.get("ca_n1"))
        unknown = not ca_ent
        gaps.append({
            "key": "capacite", "label": _LABELS["capacite"],
            "required": _money(ca_req),
            "have": _NON_RENSEIGNE if unknown else _money(ca_ent),
            "extrait": _extrait("ca_minimum_requis"),
            "severity": "a_verifier" if unknown else "bloquant",
            "trades": [],
        })

    # Qualifications exigées (10)
    c = bd.get("qualifs")
    quals_req = _as_list(details.get("qualifications_requises"))
    if c and quals_req and not _is_unspecified(quals_req) and c.get("status") != "ok":
        own = _as_list(company.get("qualifications"))
        label = _LABELS["qualifs"]
        if any(not any(v in _fold(q) for v in _REGISTRY_VERIFIABLE) for q in quals_req):
            label += _A_CONFIRMER
        gaps.append({
            "key": "qualifs", "label": label,
            "required": ", ".join(quals_req)[:200],
            "have": ", ".join(own)[:200] if own else _NON_RENSEIGNE,
            "extrait": _extrait("qualifications_requises"),
            "severity": "important" if own else "a_verifier",
            "trades": _qual_trades(details),
        })

    # Références exigées (hors barème, mais un manque réel en candidature)
    refs_req = details.get("references_requises")
    if not _is_unspecified(refs_req):
        n_req = _first_int(refs_req, (r"r[ée]f", r"chantier", r"op[ée]ration", r"march", r"r[ée]alisation", r"projet"))
        refs = company.get("references")
        n_have = len(refs) if isinstance(refs, (list, tuple)) else (len(_as_list(refs)) if refs else 0)
        if n_have == 0:
            sev, have = "a_verifier", _NON_RENSEIGNE
        elif n_req is None:
            sev, have = "a_verifier", f"{n_have} référence(s) renseignée(s) — exigence à comparer"
        elif n_have < n_req:
            sev, have = "important", f"{n_have} référence(s) renseignée(s)"
        else:
            sev = None
        if sev:
            gaps.append({
                "key": "references", "label": _LABELS["references"],
                "required": str(refs_req).strip()[:200],
                "have": have,
                "extrait": _extrait("references_requises"),
                "severity": sev,
                "trades": [],
            })

    # Effectif minimum exigé (hors barème)
    eff_req_txt = details.get("effectif_minimum_requis")
    if not _is_unspecified(eff_req_txt):
        n_req = _first_int(eff_req_txt, (r"salari", r"personne", r"etp", r"agent", r"ouvrier", r"compagnon"))
        try:
            eff = int(float(company.get("effectif") or 0))
        except (TypeError, ValueError):
            eff = 0
        if eff <= 0:
            sev, have = "a_verifier", _NON_RENSEIGNE
        elif n_req is None:
            sev, have = "a_verifier", f"{eff} salarié(s) — exigence à comparer"
        elif eff < n_req:
            sev, have = "important", f"{eff} salarié(s)"
        else:
            sev = None
        if sev:
            gaps.append({
                "key": "effectif", "label": _LABELS["effectif"],
                "required": str(eff_req_txt).strip()[:200],
                "have": have,
                "extrait": _extrait("effectif_minimum_requis"),
                "severity": sev,
                "trades": [],
            })

    order = {k: i for i, k in enumerate(GAP_KEYS)}
    gaps.sort(key=lambda g: order.get(g["key"], 99))
    return gaps


# ── 4) Score de groupement ────────────────────────────────────────────────────────────

def _thresholds(det: dict) -> dict:
    return {"go": int(det.get("threshold") or 65), "nogo": int(det.get("nogo_threshold") or 40)}


def _build_lead(lead_company: dict, criteria: dict, given: dict = None) -> dict:
    """Le mandataire normalisé : profil (company_dict) + critères (spécialités, départements),
    complété par les champs non vides d'un membre 'lead' éventuellement fourni par l'appelant."""
    base = dict(lead_company or {})
    base["kind"] = "lead"
    base.setdefault("source", "profil")
    if criteria.get("specialites") and not base.get("specialites"):
        base["specialites"] = criteria.get("specialites")
    if criteria.get("departements"):
        base["departements"] = criteria.get("departements")
    if given:
        for k, v in given.items():
            if k in ("kind",):
                continue
            if v not in (None, "", [], {}, 0) and base.get(k) in (None, "", [], {}, 0):
                base[k] = v
    return member_capacities(base)


def _apporte_par(key: str, details: dict, partners: list, cumul_admis: bool) -> list:
    """Membres (non lead) dont la capacité fait passer le critère `key`."""
    ld = _dept(details.get("lieu_execution", ""))
    out = []
    for p in partners:
        ok = False
        if key == "capacite":
            ok = cumul_admis and p["ca_n1"] is not None
        elif key == "qualifs":
            ok = bool(_required_qual_words(details) & _words(" ".join(p["qualifications"])))
        elif key == "metier":
            ok = bool(_market_words(details) & _member_words(p))
        elif key == "zone":
            ok = bool(ld) and _in_zone(ld, p["departements"])
        elif key == "references":
            ok = bool(p["references"])
        elif key == "effectif":
            ok = cumul_admis and p["effectif"] is not None
        if ok:
            out.append(p["name"])
    return out


def score_groupement(details: dict, lead_company: dict, criteria: dict, members: list) -> dict:
    """Score de l'entreprise virtuelle = score_dce RÉAPPLIQUÉ au cumul (company=cumul,
    criteria=critères du lead avec specialites et departements enrichis des membres).
    Renvoie {score_seul, score_groupement, decision, breakdown[6], cumul, gaps (restants APRÈS
    groupement), gaps_combles (avec apporte_par), warnings, members (normalisés), thresholds}.
    decision : 'go' si seul est déjà go ; 'go_groupement' ssi score_groupement ≥ seuil go ET ≥ 1
    membre réel (kind != 'lead') ET score_groupement > score_seul ; 'a_etudier' si ≥ seuil nogo ;
    sinon 'no_go'. JAMAIS go_groupement sans partenaire."""
    details = details if isinstance(details, dict) else {}
    lead_company = lead_company if isinstance(lead_company, dict) else {}
    criteria = criteria if isinstance(criteria, dict) else {}
    members = [m for m in (members or []) if isinstance(m, dict)]

    # 1) Score SEUL — exactement score_dce (même barème, mêmes seuils).
    seul = score_dce(details, lead_company, criteria)
    score_seul = int(seul["score"])
    thresholds = _thresholds(seul)

    # 2) Membres normalisés : le lead vient du profil ; les partenaires de l'appelant.
    given_lead = next((m for m in members if str(m.get("kind") or "").lower() == "lead"), None)
    lead = _build_lead(lead_company, criteria, given_lead)
    partners = [member_capacities(m) for m in members if str(m.get("kind") or "").lower() != "lead"]
    all_members = [lead] + partners

    # 3) Cumul (règle « chaque membre doit satisfaire seul » lue dans le DCE).
    cap_g = "" if _is_unspecified(details.get("capacites_groupement")) else str(details.get("capacites_groupement") or "")
    cumul = cumulate(all_members, cap_g)
    cumul_admis = cumul["cumul_admis"]

    # 4) Entreprise virtuelle + critères enrichis.
    company_v = dict(lead_company)
    company_v.update({
        # Mots des noms de TOUS les membres (comme score_dce lit le nom du candidat) — sans le
        # mot « Groupement », qui recouperait faussement un « groupement de commandes ».
        "name": " ".join(m["name"] for m in all_members),
        "ca_n1": cumul["ca_n1"],
        "effectif": cumul["effectif"],
        "qualifications": list(cumul["qualifications"]),
        "references": list(cumul["references"]),
    })
    criteria_v = dict(criteria)
    specs = _as_list(criteria.get("specialites"))
    for p in partners:
        for s in _as_list(p["specialites"]):
            if _fold(s) not in {_fold(x) for x in specs}:
                specs.append(s)
    criteria_v["specialites"] = ", ".join(specs)
    lead_deps = _deps_of_criteria(criteria)
    partner_deps = []
    for p in partners:
        for d in p["departements"]:
            if d not in lead_deps and d not in partner_deps:
                partner_deps.append(d)
    ld = _dept(details.get("lieu_execution", ""))
    # Zone : on n'« explicite » la zone du groupement que si elle n'était pas déjà définie
    # ET qu'un partenaire couvre vraiment le lieu — sinon un lead sans zone (statut 'inconnu',
    # non pénalisé) passerait « hors zone » par le seul fait d'ajouter un partenaire.
    if partner_deps and (lead_deps or (ld and _in_zone(ld, partner_deps))):
        criteria_v["departements"] = lead_deps + partner_deps

    grp = score_dce(details, company_v, criteria_v)
    score_grp = int(grp["score"])

    # 5) Détail critère par critère, seul | en groupement, avec « apporté par ».
    bd_seul = {c["key"]: c for c in seul["breakdown"]}
    bd_grp = {c["key"]: c for c in grp["breakdown"]}
    breakdown = []
    for key in ("metier", "zone", "budget", "capacite", "qualifs", "delai"):
        a, b = bd_seul.get(key, {}), bd_grp.get(key, {})
        improved = int(b.get("points", 0)) > int(a.get("points", 0))
        breakdown.append({
            "key": key, "label": a.get("label") or b.get("label") or key,
            "points_seul": int(a.get("points", 0)), "points_groupement": int(b.get("points", 0)),
            "max_points": int(a.get("max_points") or b.get("max_points") or 0),
            "status_seul": a.get("status", "inconnu"), "status_groupement": b.get("status", "inconnu"),
            "detail": b.get("detail", ""),
            "apporte_par": _apporte_par(key, details, partners, cumul_admis) if improved else [],
        })

    # 6) Manques : avant / après groupement.
    gaps_seul = gaps_for(details, lead_company, criteria)
    gaps_grp = gaps_for(details, company_v, criteria_v)
    remaining = {g["key"] for g in gaps_grp}
    gaps_combles = []
    for g in gaps_seul:
        if g["key"] not in remaining:
            gc = dict(g)
            gc["apporte_par"] = _apporte_par(g["key"], details, partners, cumul_admis)
            gaps_combles.append(gc)

    # 7) Décision.
    has_partner = bool(partners)
    decision_seul = seul["go_decision"]
    if decision_seul == "go":
        decision = "go"
    elif has_partner and score_grp >= thresholds["go"] and score_grp > score_seul:
        decision = "go_groupement"
    elif score_grp >= thresholds["nogo"]:
        decision = "a_etudier"
    else:
        decision = "no_go"

    # 8) Avertissements obligatoires (avertir, pas bloquer).
    warnings = []
    for p in partners:
        if p["ca_n1"] is None:
            warnings.append(f"Le CA de {p['name']} n'est pas connu : il compte pour 0 dans le cumul — à demander")
    if has_partner and lead["ca_n1"] is None:
        warnings.append("Votre CA n'est pas renseigné : il compte pour 0 dans le cumul — complétez votre profil")
    if decision != decision_seul and decision in ("go_groupement", "a_etudier"):
        contributors = []
        for c in breakdown:
            contributors += c["apporte_par"]
        for p in partners:
            if not p["verified"] and p["name"] in contributors and p["name"] not in [
                    w.split("(")[-1].rstrip(")") for w in warnings]:
                if p["source"] in ("declare", "saisi", "profil", "manuel", ""):
                    warnings.append(f"Verdict fondé sur des capacités déclarées par vous ({p['name']}) — à confirmer auprès du partenaire")
                else:
                    warnings.append(f"Verdict fondé sur des capacités déclarées par {p['name']} (source : {p['source']}, non vérifiée) — à confirmer auprès du partenaire")
    warnings += [w for w in cumul.get("warnings", []) if w not in warnings]

    return {
        "score_seul": score_seul,
        "score_groupement": score_grp,
        "decision": decision,
        "decision_seul": decision_seul,
        "breakdown": breakdown,
        "cumul": {k: v for k, v in cumul.items() if k not in ("members", "warnings")},
        "gaps": gaps_grp,
        "gaps_combles": gaps_combles,
        "warnings": warnings,
        "members": all_members,
        "thresholds": thresholds,
    }


# ── 5) Alliance automatique (glouton déterministe) ────────────────────────────────────

def _pool_key(m: dict):
    return (_fold(m.get("name")), str(m.get("id") if m.get("id") is not None else ""), m.get("siret") or "")


def _identity(m: dict):
    return (m.get("kind"), str(m.get("id") if m.get("id") is not None else ""), m.get("siret") or "", _fold(m.get("name")))


def auto_alliance(details: dict, lead_company: dict, criteria: dict, pool: list, max_partners: int = 3) -> dict:
    """Glouton déterministe : part du lead seul ; à chaque tour ajoute le candidat du pool (trié
    par nom/id pour la stabilité) qui maximise score_groupement (tie-break : comble le plus de
    gaps, puis vérifié avant déclaré, puis nom) ; s'arrête quand plus de gain (score ou nombre
    de manques) ou max_partners atteint. Renvoie score_groupement(...) du meilleur ensemble +
    'chosen': [membres], 'considered': len(pool). Pool vide → résultat 'seul' avec gaps."""
    try:
        max_partners = max(0, int(max_partners))
    except (TypeError, ValueError):
        max_partners = 3
    candidates, seen = [], set()
    for m in (pool or []):
        if not isinstance(m, dict):
            continue
        n = member_capacities(m)
        if n["kind"] == "lead":
            continue
        ident = _identity(n)
        if ident in seen:
            continue
        seen.add(ident)
        candidates.append(n)
    candidates.sort(key=_pool_key)

    chosen = []
    current = score_groupement(details, lead_company, criteria, chosen)

    def _gain(r):
        return (int(r["score_groupement"]), -len(r["gaps"]))

    while len(chosen) < max_partners:
        best, best_res, best_key = None, None, None
        for cand in candidates:
            if any(_identity(cand) == _identity(c) for c in chosen):
                continue
            r = score_groupement(details, lead_company, criteria, chosen + [cand])
            key = (int(r["score_groupement"]), -len(r["gaps"]), 1 if cand["verified"] else 0)
            if best_key is None or key > best_key:          # égalité ⇒ le premier par nom gagne
                best, best_res, best_key = cand, r, key
        if best is None or _gain(best_res) <= _gain(current):
            break
        chosen.append(best)
        current = best_res

    result = dict(current)
    result["chosen"] = list(chosen)
    result["considered"] = len(candidates)
    return result
