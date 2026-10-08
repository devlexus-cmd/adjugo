"""
Adjugo — « Répondre à plusieurs ? » : orchestration (AVEC base) du score de groupement.

Le calcul PUR (cumul des capacités, score_dce réappliqué à l'entreprise virtuelle, manques,
alliance gloutonne) vit dans app/services/groupement_scoring.py (0 LLM, 0 DB). Ce module :

  • construit le POOL de partenaires d'un marché (rattachés → « Mes partenaires » → SIRENE,
    re-fetché côté serveur, borné à 3 appels, cache in-process 10 min — process unique) ;
  • applique le verdict de groupement sur un projet après analyse (auto_alliance sur les
    rattachés + annuaire, JAMAIS d'appel réseau sur le chemin d'analyse) : écrit
    project.groupement_score / groupement_plan, pose go_decision = 'go_groupement' si le
    service pur le conclut — match_score reste le score SEUL, jamais gonflé.

Invariants : jamais une capacité inventée (SIRENE : CA non publié = None, effectif du registre
uniquement) ; verdict fondé sur des capacités déclarées par le mandataire sur ses partenaires
⇒ avertissement PROÉMINENT en tête ; si le service pur est absent/en erreur → on ne change
rien (log + {}), l'app démarre et analyse quand même.
"""
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger("adjugo")

# Cache in-process des découvertes SIRENE par (métier, département) — process unique sans
# Redis, donc un dict module-level suffit et reste cohérent.
_SIRENE_CACHE: dict = {}
_SIRENE_TTL = 600   # 10 min

WARN_DECLARE = ("Verdict fondé sur des capacités que vous avez déclarées vous-même sur vos "
                "partenaires — à confirmer auprès d'eux")

VERDICT_LABELS = {
    "go": "Bon potentiel",
    "go_groupement": "Bon potentiel en groupement",
    "a_etudier": "À étudier",
    "no_go": "Peu adapté",
}


def verdict_label(decision: Optional[str]) -> str:
    return VERDICT_LABELS.get(decision or "", "—")


# ── Service pur (agent B1) : import PARESSEUX + tolérant ─────────────────────────────

def scoring_module():
    """Renvoie app.services.groupement_scoring, ou None s'il est absent / en erreur."""
    try:
        from app.services import groupement_scoring as gs
        return gs
    except Exception as e:   # module pas encore livré, erreur d'import…
        logger.warning("groupement_scoring indisponible : %s", e)
        return None


# ── Normalisation des membres ────────────────────────────────────────────────────────

def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.date().isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _qual_list(q) -> list:
    """Qualifications → liste de libellés (depuis une String « A, B », une liste de str ou de
    dicts {name, detail} comme sur le profil entreprise)."""
    if not q:
        return []
    if isinstance(q, str):
        import re
        return [s.strip() for s in re.split(r"[,;\n]", q) if s.strip()]
    out = []
    for x in q:
        if isinstance(x, dict):
            # name + detail : dce_scoring recoupe les DEUX (sinon le score « seul »
            # recalculé ici divergeait du match_score posé à l'analyse — 58 vs 80).
            n = ((x.get("name") or "") + " " + (x.get("detail") or "")).strip()
            if n:
                out.append(n)
        elif x:
            out.append(str(x).strip())
    return out


def lead_member(company_data: dict, criteria: dict) -> dict:
    """Le mandataire = profil entreprise (company_dict) + critères (spécialités/zone),
    kind 'lead', source 'profil'. Les clés du profil ne sont pas écrasées par celles des
    critères (criteria.qualifications est une String, company.qualifications une liste)."""
    company_data = company_data or {}
    criteria = criteria or {}
    from app.services.dce_scoring import _dept
    deps = criteria.get("departements") or []
    if isinstance(deps, str):
        import re
        deps = [d.strip() for d in re.split(r"[,;\s]+", deps) if d.strip()]
    m = dict(company_data)
    m.update({
        "kind": "lead", "id": None, "invite_id": None,
        "name": company_data.get("name") or "Votre entreprise",
        "siret": company_data.get("siret") or "",
        "ca_n1": company_data.get("ca_n1"),
        "effectif": company_data.get("effectif"),
        "qualifications": _qual_list(company_data.get("qualifications")),
        "specialites": criteria.get("specialites") or "",
        "departement": _dept(company_data.get("postal_code") or "") or "",
        "departements": [str(d) for d in deps],
        "postal_code": company_data.get("postal_code") or "",
        "references": company_data.get("references") if isinstance(company_data.get("references"), list) else [],
        "source": "profil", "as_of": None, "verified": False,
    })
    return m


def member_from_cotraitant(ct, kind: str = "annuaire", invite_id: Optional[int] = None) -> dict:
    """Partenaire de l'annuaire « Mes partenaires » → membre normalisé (capacités étiquetées
    par ct.capacites_source / capacites_updated_at)."""
    src = getattr(ct, "capacites_source", None) or "declare"
    refs = getattr(ct, "references", None)
    return {
        "kind": kind, "id": ct.id, "invite_id": invite_id,
        "name": ct.name or "Partenaire", "siret": ct.siret or "",
        "ca_n1": ct.ca_n1 if ct.ca_n1 else None,
        "effectif": ct.effectif if ct.effectif else None,
        "qualifications": _qual_list(ct.qualifications),
        "specialites": ct.specialites or "", "codes_cpv": getattr(ct, "codes_cpv", "") or "",
        "departement": ct.departement or "", "postal_code": ct.postal_code or "",
        "city": ct.city or "",
        "references": refs if isinstance(refs, list) else [],
        "source": src, "as_of": _iso(getattr(ct, "capacites_updated_at", None)),
        "verified": src in ("rne", "sirene"),
    }


def member_from_sirene(fiche: dict, siret: str = "") -> dict:
    """Fiche registre.lookup_company → membre 'sirene'. SEULES les données du registre sont
    gardées : CA = None (« CA non publié — à demander »), effectif = tranche INSEE, aucune
    qualification inventée."""
    fiche = fiche or {}
    return {
        "kind": "sirene", "id": None, "invite_id": None,
        "name": fiche.get("name") or fiche.get("nom") or "Entreprise",
        "siret": fiche.get("siret") or siret or "", "siren": fiche.get("siren") or "",
        "ca_n1": None,
        "effectif": fiche.get("effectif") or None,
        "qualifications": [],
        "specialites": fiche.get("specialite") or fiche.get("naf_label") or "",
        "code_ape": fiche.get("code_ape") or "",
        "departement": fiche.get("departement") or "", "postal_code": fiche.get("postal_code") or "",
        "city": fiche.get("city") or "",
        "references": [],
        "source": "sirene", "as_of": _today(), "verified": True,
    }


def member_from_profile(p) -> dict:
    """Profil PUBLIÉ du réseau Adjugo (vague 3) → membre 'reseau' du score de groupement.
    Uniquement ce que la fiche publique expose : JAMAIS de CA ni d'effectif exact (inconnus →
    « CA non publié — à demander »), qualifications = registres (RGE / Qualiopi via SIRENE),
    références = celles que le partenaire a rendues publiques. Source 'reseau' = déclaré par
    l'entreprise elle-même sur son profil (étiquette datée)."""
    vs = p.verified_sirene if isinstance(getattr(p, "verified_sirene", None), dict) else {}
    quals = []
    if vs.get("est_rge") is True:
        quals.append("RGE (registre ADEME)")
    if vs.get("est_qualiopi") is True:
        quals.append("Qualiopi (registre)")
    try:
        from app.services.partner_matching import trade_labels
        labels = trade_labels()
    except Exception:
        labels = {}
    refs = [{"name": r.get("intitule"), "client": r.get("client") or "", "year": r.get("annee")}
            for r in (p.references_publiques or []) if isinstance(r, dict) and r.get("intitule")]
    return {
        "kind": "reseau", "id": None, "invite_id": None, "profile_id": p.public_id,
        "name": p.name or "Partenaire", "siret": p.siret or "", "siren": p.siren or "",
        "ca_n1": None, "effectif": None,
        "qualifications": quals,
        "specialites": ", ".join(labels.get(m, m) for m in (p.metiers or [])),
        "code_ape": str(vs.get("naf") or "").replace(".", ""),
        "departement": p.departement or "", "departements": list(p.departements or []),
        "postal_code": p.postal_code or "", "city": p.city or "",
        "references": refs,
        "source": "reseau", "as_of": _iso(getattr(p, "declared_at", None)), "verified": False,
    }


def _member_from_normalized_company(c) -> dict:
    """NormalizedCompany (découverte SIRENE) → membre 'sirene'. RGE n'est ajouté que si le
    registre (ADEME via recherche-entreprises) le dit explicitement."""
    quals = ["RGE (registre ADEME)"] if getattr(c, "est_rge", None) else []
    return {
        "kind": "sirene", "id": None, "invite_id": None,
        "name": c.nom, "siret": c.siret or "", "siren": c.siren or "",
        "ca_n1": None,                      # jamais le CA RNE ici : « CA non publié — à demander »
        "effectif": c.effectif or None,
        "qualifications": quals,
        "specialites": c.naf_label or "", "code_ape": c.naf or "",
        "departement": c.departement or "", "postal_code": c.code_postal or "",
        "city": c.ville or "",
        "references": [],
        "source": "sirene", "as_of": _today(), "verified": True,
    }


def proof_label(member: dict) -> str:
    """Étiquette de provenance datée, lisible par tous (zéro jargon)."""
    src = (member or {}).get("source") or "declare"
    as_of = (member or {}).get("as_of")
    d = ""
    if as_of:
        try:
            dt = date.fromisoformat(str(as_of)[:10])
            d = f" le {dt.strftime('%d/%m')}"
        except ValueError:
            d = ""
    if src in ("rne", "sirene"):
        return f"vérifié SIRENE{d}"
    if src == "contribution":
        return f"déclaré par le partenaire{d}"
    if src == "reseau":
        return f"déclaré par l'entreprise sur son profil Adjugo{d}"
    if src == "profil":
        return "votre profil"
    return f"déclaré par vous{d}"


def ca_label(member: dict) -> Optional[str]:
    """« CA non publié — à demander » quand le CA du partenaire est inconnu."""
    ca = (member or {}).get("ca_n1")
    if ca in (None, 0, 0.0, ""):
        return "CA non publié — à demander"
    return None


# ── Pool de partenaires ──────────────────────────────────────────────────────────────

def _execution_dept(details: dict, criteria: dict, company_data: dict) -> str:
    from app.services.dce_scoring import _dept
    d = _dept((details or {}).get("lieu_execution") or "")
    if d:
        return d
    deps = (criteria or {}).get("departements") or ""
    if isinstance(deps, list):
        return str(deps[0])[:3] if deps else ""
    first = str(deps).split(",")[0].strip()
    if first:
        return first[:3]
    return _dept((company_data or {}).get("postal_code") or "")


def _discover_sirene(trade: str, dept: str, warnings: list) -> list:
    """Découverte SIRENE pour UN métier/département, cachée 10 min. Jamais d'exception."""
    key = (trade, dept)
    hit = _SIRENE_CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < _SIRENE_TTL:
        return list(hit[1])
    try:
        from app.routers.sourcing import _company_service
        from app.sourcing.sources.sirene import TRADES
        label = next((t["label"] for t in TRADES if t["key"] == trade), trade)
        # limit 4 + PAS d'enrichissement DECP (1 requête HTTP par entreprise) : sur
        # l'unique worker, 3 métiers × (SIRENE + 6 BODACC + 6 DECP) bloquaient ~100 s.
        # BODACC est conservé (filtre « procédure collective » juste en dessous).
        res = _company_service().discover(activity=trade, departement=dept,
                                          tender_departements=[dept] if dept else [],
                                          need_label=label, limit=4, enrich_decp=False)
        out = []
        for c in res.get("companies") or []:
            if getattr(c, "procedure_collective", None):
                continue   # procédure collective publiée → exclu du pool
            if getattr(c, "est_personne_physique", False):
                continue   # entrepreneur individuel : nom = personne physique (RGPD)
            out.append(_member_from_normalized_company(c))
        for e in res.get("errors") or []:
            msg = getattr(e, "message", None) or str(e)
            warnings.append(f"Recherche SIRENE ({label}) partielle : {msg[:120]}")
        _SIRENE_CACHE[key] = (now, out)
        return list(out)
    except Exception as e:
        logger.warning("découverte SIRENE %s/%s en échec : %s", trade, dept, e)
        warnings.append(f"Recherche SIRENE indisponible pour « {trade} » — réessayez plus tard.")
        return []


def _reseau_pool(db, project, network_ctx: dict, trades: list, dept: str, per_trade: int = 5) -> list:
    """Pool 'reseau' (vague 3) : profils PUBLIÉS visibles par le chercheur (réciprocité,
    masquage dans les deux sens, jamais démo) dont le métier correspond, dans l'ORDRE du
    classement déterministe partner_matching (B classe, A calcule le seul pourcentage).
    Base seulement : aucun appel réseau."""
    if not network_ctx or not network_ctx.get("published") or not trades:
        return []
    from datetime import date as _date
    from app.services import partner_matching as pm
    from app.services import partner_network as pn
    profiles = pn.visible_profiles(db, network_ctx)
    by_pid = {p.public_id: p for p in profiles}
    dicts = [pn.profile_dict(p) for p in profiles]
    out, seen = [], set()
    today = _date.today()
    for trade in trades:
        for r in pm.rank({"metier": trade, "departement": dept, "role": "cotraitant"}, dicts, today, limit=per_trade):
            if r["profile_id"] in seen:
                continue
            seen.add(r["profile_id"])
            m = member_from_profile(by_pid[r["profile_id"]])
            m["trade"] = trade
            m["rang"] = r["rang"]
            m["_db_id"] = by_pid[r["profile_id"]].id    # interne (compteur anonyme), jamais sérialisé
            out.append(m)
    return out


def pool_for_project(db, project, owner_ids: list, include_sirene: bool = False,
                     max_sirene_calls: int = 3, gaps: Optional[list] = None,
                     lead: Optional[dict] = None, criteria: Optional[dict] = None,
                     company_data: Optional[dict] = None, network_ctx: Optional[dict] = None) -> dict:
    """Pool de partenaires d'un marché, en membres normalisés :
      rattaches = ProjectCotraitant du projet → Cotraitant (kind 'attached')
      annuaire  = Cotraitant de l'organisation NON rattachés (kind 'annuaire')
      sirene    = (si include_sirene) découverte SIRENE pour les métiers des manques
                  (≤ max_sirene_calls appels, cache 10 min, erreurs → liste vide + warning)
      reseau    = (si network_ctx d'un chercheur au profil PUBLIÉ) profils du réseau Adjugo
                  pour les métiers des manques, dans l'ordre du classement partner_matching
    `gaps` : manques déjà calculés (sinon calculés ici via gaps_for si lead/criteria fournis)."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.models import ProjectInvite
    warnings: list = []
    owner_ids = list(owner_ids or [])

    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id).all()
    link_by_ct = {lk.cotraitant_id: lk for lk in links}
    cts = db.query(Cotraitant).filter(Cotraitant.user_id.in_(owner_ids or [0])).all()
    # Invitations ACTIVES (membres) : un rattachement avec invite_id pointe vers elles ;
    # on signale l'invite_id sur le membre pour que le plan/la convention le retrouvent.
    rattaches, annuaire = [], []
    for ct in sorted(cts, key=lambda c: (c.name or "").lower()):
        lk = link_by_ct.get(ct.id)
        if lk:
            inv_id = getattr(lk, "invite_id", None)
            if inv_id:
                inv = db.query(ProjectInvite).filter(ProjectInvite.id == inv_id).first()
                if inv and (inv.revoked or getattr(inv, "declined_at", None) is not None):
                    inv_id = None   # a décliné / révoqué → redevient simple candidat
            m = member_from_cotraitant(ct, "attached", invite_id=inv_id)
            m["link_id"] = lk.id
            m["role"] = lk.role or "cotraitant"
            m["lot"] = lk.lot or ""
            rattaches.append(m)
        else:
            annuaire.append(member_from_cotraitant(ct, "annuaire"))

    sirene: list = []
    reseau: list = []
    with_network = bool(network_ctx and network_ctx.get("published"))
    if include_sirene or with_network:
        details = (project.ai_analysis or {}).get("details") or {} if isinstance(project.ai_analysis, dict) else {}
        if gaps is None and lead is not None:
            gs = scoring_module()
            if gs is not None:
                try:
                    gaps = gs.gaps_for(details, lead, criteria or {})
                except Exception as e:
                    logger.warning("gaps_for en échec : %s", e)
                    gaps = []
        trades: list = []
        for g in gaps or []:
            for t in (g.get("trades") or []) if isinstance(g, dict) else []:
                if t and t not in trades:
                    trades.append(t)
        if not trades:
            # Aucun métier déduit des manques → on cherche au moins les métiers des lots
            # non couverts par le mandataire (déterministe, sans LLM).
            try:
                from app.sourcing.groupement import parse_lots, infer_trade, own_trades
                mine = own_trades({**(company_data or {}), "specialites": (criteria or {}).get("specialites", "")})
                for lot in parse_lots(details.get("allotissement", "")):
                    k = infer_trade(lot["label"])
                    if k and k not in mine and k not in trades:
                        trades.append(k)
            except Exception:
                pass
        dept = _execution_dept(details, criteria or {}, company_data or lead or {})
        known = {m["siret"] for m in rattaches + annuaire if m.get("siret")}
        if with_network:
            try:
                reseau = _reseau_pool(db, project, network_ctx, trades, dept)
            except Exception as e:
                logger.warning("pool réseau indisponible (projet %s) : %s", getattr(project, "id", "?"), e)
                reseau = []
            for m in reseau:
                m["deja_partenaire"] = bool(m.get("siret") and m["siret"] in known)
        seen = set()
        for trade in (trades[:max(0, int(max_sirene_calls))] if include_sirene else []):
            for m in _discover_sirene(trade, dept, warnings):
                s = m.get("siret") or m.get("name")
                if s in seen:
                    continue
                seen.add(s)
                m["deja_partenaire"] = bool(m.get("siret") and m["siret"] in known)
                m["trade"] = trade
                sirene.append(m)
        if include_sirene and len(trades) > max_sirene_calls:
            warnings.append(f"Recherche SIRENE limitée à {max_sirene_calls} métiers par requête "
                            f"({len(trades) - max_sirene_calls} non cherché(s)).")

    return {"rattaches": rattaches, "annuaire": annuaire, "sirene": sirene, "reseau": reseau, "warnings": warnings}


# ── Verdict de groupement après analyse ──────────────────────────────────────────────

def _matches(member: dict, ref) -> bool:
    """`apporte_par` d'un critère peut citer un nom, un id, un siret ou un dict membre."""
    if isinstance(ref, dict):
        return any(_matches(member, v) for v in (ref.get("id"), ref.get("name"), ref.get("siret")) if v not in (None, ""))
    if ref in (None, ""):
        return False
    return ref in (member.get("id"), member.get("name"), member.get("siret"))


def apports_for(member: dict, breakdown: list) -> list:
    """Clés des critères que CE membre apporte (d'après breakdown[].apporte_par)."""
    out = []
    for bd in breakdown or []:
        if not isinstance(bd, dict):
            continue
        refs = bd.get("apporte_par") or []
        if not isinstance(refs, (list, tuple)):
            refs = [refs]
        if any(_matches(member, r) for r in refs) and bd.get("key") not in out:
            out.append(bd.get("key"))
    return out


def plan_member(member: dict, breakdown: list) -> dict:
    return {
        "kind": member.get("kind"), "id": member.get("id"), "invite_id": member.get("invite_id"),
        "name": member.get("name"), "siret": member.get("siret") or "",
        "apporte": apports_for(member, breakdown),
        "source": member.get("source"), "as_of": member.get("as_of"),
    }


def _gap_keys(gaps) -> list:
    out = []
    for g in gaps or []:
        k = g.get("key") if isinstance(g, dict) else g
        if k and k not in out:
            out.append(k)
    return out


def plan_members(partners: list, breakdown: list, gaps_combles=None) -> list:
    """Membres du plan (hors lead) avec leurs apports. Avec UN seul partenaire, ses apports
    sont exactement les manques comblés (repli si `apporte_par` ne le cite pas)."""
    out = [plan_member(m, breakdown) for m in partners if isinstance(m, dict) and m.get("kind") != "lead"]
    if len(out) == 1 and not out[0]["apporte"]:
        out[0]["apporte"] = _gap_keys(gaps_combles)
    return out


def with_declare_warning(members: list, warnings: list) -> list:
    """Avertissement PROÉMINENT (en tête) si un membre retenu repose sur des capacités
    déclarées par le mandataire lui-même ('declare') ou saisies à la volée ('saisi')."""
    warnings = [w for w in (warnings or []) if w != WARN_DECLARE]
    if any((m.get("source") in ("declare", "saisi")) for m in members if m.get("kind") != "lead"):
        warnings.insert(0, WARN_DECLARE)
    return warnings


def apply_groupement_verdict(db, project, analysis: dict, company_data: dict, gonogo: dict,
                             owner_ids: list) -> dict:
    """Après une analyse (DCE réel) : manques, alliance automatique sur rattachés + annuaire
    (jamais SIRENE ici), écriture de groupement_score / groupement_plan / go_decision.
    Renvoie analysis['groupement'] enrichi, ou {} si le service pur est indisponible."""
    gs = scoring_module()
    if gs is None:
        return {}
    try:
        from sqlalchemy.orm.attributes import flag_modified
        details = (analysis or {}).get("details") or {}
        criteria = gonogo or {}
        lead = lead_member(company_data, criteria)
        gaps = gs.gaps_for(details, lead, criteria) or []
        score_seul = project.match_score if project.match_score is not None else (analysis or {}).get("match_score")
        verdict_seul = (analysis or {}).get("go_decision") or project.go_decision

        result, chosen = None, []
        if verdict_seul != "go":
            pool = pool_for_project(db, project, owner_ids)
            candidates = pool["rattaches"] + pool["annuaire"]
            if candidates:
                result = gs.auto_alliance(details, lead, criteria, candidates, max_partners=3) or {}
                chosen = [m for m in (result.get("chosen") or []) if isinstance(m, dict) and m.get("kind") != "lead"]

        breakdown = (result or {}).get("breakdown") or []
        warnings = list((result or {}).get("warnings") or [])
        warnings = with_declare_warning(chosen, warnings)
        score_grp = (result or {}).get("score_groupement") if chosen else None
        decision = (result or {}).get("decision") if chosen else None
        gaps_after = (result or {}).get("gaps") if result else gaps
        gaps_combles = (result or {}).get("gaps_combles") or [] if chosen else []

        plan = {
            "members": plan_members(chosen, breakdown, gaps_combles),
            "breakdown": breakdown, "gaps": gaps_after if chosen else gaps,
            "gaps_combles": gaps_combles, "warnings": warnings,
            "auto": True, "computed_at": datetime.now(timezone.utc).isoformat(),
            "score_seul": score_seul, "score_groupement": score_grp,
        }
        # Une offre déjà figée (vague D) survit à la ré-analyse : la perdre ici l'aurait
        # effacée pour les membres sans aucune entrée « offer.unfrozen » au journal.
        _old = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
        if _old.get("offre"):
            plan["offre"] = _old["offre"]
        project.groupement_score = int(score_grp) if score_grp is not None else None
        project.groupement_plan = plan
        if decision == "go_groupement":
            project.go_decision = "go_groupement"   # match_score INCHANGÉ (= seul)

        grp = dict((analysis or {}).get("groupement") or {})
        grp.update({
            "score_seul": score_seul, "score_groupement": score_grp,
            "decision": decision or verdict_seul, "gaps": plan["gaps"], "gaps_combles": gaps_combles,
            "members": plan["members"], "warnings": warnings,
            "recommande": bool(grp.get("recommande")) or decision == "go_groupement" or bool(gaps),
            "label": verdict_label(decision or verdict_seul),
        })
        if analysis is not None:
            analysis["groupement"] = grp
            # JSON mutable : forcer l'UPDATE (la mutation en place n'est pas détectée).
            project.ai_analysis = dict(analysis)
            flag_modified(project, "ai_analysis")
        return grp
    except Exception as e:
        logger.warning("verdict de groupement non appliqué (projet %s) : %s", getattr(project, "id", "?"), e)
        return {}
