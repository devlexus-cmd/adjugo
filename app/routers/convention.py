"""
« Monter le groupement » — convention de groupement et accords des membres (co-traitance v2,
vague 2). Contrat d'API complet : docs/COTRAITANCE_V2_VAGUE2_API.md.

Côté MANDATAIRE (compte, périmètre organisation via _owned_project) :
  GET  /api/projects/{id}/groupement/convention                 assistant + état + texte
  PUT  /api/projects/{id}/groupement/convention                 enregistrer le brouillon
  POST /api/projects/{id}/groupement/convention/relire-dce      relire le dossier du marché
  POST /api/projects/{id}/groupement/convention/generer         figer l'offre + générer
  POST /api/projects/{id}/groupement/convention/valider         accord du mandataire
  POST /api/projects/{id}/groupement/convention/hors-ligne/{link_id}  accord recueilli hors ligne
  GET  /api/projects/{id}/groupement/convention/pdf             PDF (brouillon ou texte figé)

Côté PARTENAIRE (lien magique, portée = invite.project_id ; compte facultatif après claim) :
  GET  /api/invite/{token}/convention                           sa vue (prix des autres masqués en brouillon)
  GET  /api/invite/{token}/convention/pdf                       PDF du texte figé
  POST /api/invite/{token}/convention/valider                   son accord (gate d'identité existant)

0 LLM. Aucune route n'envoie la convention à l'IA. Avertir, pas bloquer (sauf données
indispensables au texte : forme, parts soumises, prix). Toutes les écritures sont bloquées
pour le compte démo (app/core/demo_guard.py) et pour les liens de la démo.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.http import content_disposition
from app.core.org import member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import (GroupementConvention, Project, ProjectContribution,
                        ProjectInvite, User, utcnow)
from app.services import audit
from app.services import groupement_convention as gc
from app.services.groupement_members import groupement_state

logger = logging.getLogger("adjugo")
_settings = get_settings()

owner_router = APIRouter(prefix="/api/projects/{project_id}/groupement/convention",
                         tags=["Monter le groupement"])
guest_router = APIRouter(prefix="/api/invite/{token}/convention", tags=["Monter le groupement"])


# ── Helpers ──────────────────────────────────────────────────────────────────────────

def _inv():
    from app.routers import invites
    return invites


def _project(project_id: int, user: User, db: Session) -> Project:
    return _inv()._owned_project(project_id, user, db)


def _options(project) -> dict:
    return {
        "formes": [{"value": k, **v} for k, v in gc.FORMES.items()],
        "mandataire_solidaire": {**gc.MANDATAIRE_SOLIDAIRE, "disponible_si": "conjoint"},
        "habilitation": [{k: h[k] for k in ("key", "libelle", "terme", "defaut", "obligatoire")}
                         for h in gc.HABILITATION],
        "params": [{**p, "defaut": (gc.is_travaux(project) if p["key"] == "assurances_travaux" else p["defaut"])}
                   for p in gc.PARAMS],
        "mandataire": [
            {"key": "part_mandataire_ht", "type": "montant", "libelle": "Votre part : prix de vente HT de ce que vous réalisez"},
            {"key": "lot_mandataire", "type": "texte", "libelle": "Votre part : lot ou prestations que vous réalisez"},
            {"key": "mandataire_qualite", "type": "texte", "libelle": "Qualité du signataire (ex. gérant, président)"},
        ],
    }


def _forme_label(forme: str) -> Optional[dict]:
    f = gc.FORMES.get(forme or "")
    return {"value": forme, **f} if f else None


def _fi_payload(conv, project, db, owner_ids) -> dict:
    """Bloc « ce que le règlement impose » : stocké sur la convention s'il a été relu, sinon
    calculé depuis l'analyse (citation vérifiée à l'analyse contre le texte intégral)."""
    if conv is not None and conv.forme_imposee and (conv.params or {}).get("_forme_relue_le"):
        code = conv.forme_imposee
        fi = {"forme_imposee": code, "extrait": conv.forme_imposee_extrait or "",
              "clauses": list((conv.params or {}).get("_clauses") or ([conv.forme_imposee_extrait] if conv.forme_imposee_extrait else [])),
              "libelle": (conv.params or {}).get("_forme_libelle") or gc.FORME_IMPOSEE_LABELS.get(code, ""),
              "source": "dossier_relu", "relu_le": (conv.params or {}).get("_forme_relue_le")}
    else:
        fi = gc.forme_imposee(project)
        fi["relu_le"] = None
    fi["dossier_disponible"] = gc.has_dce_document(db, project, owner_ids)
    return fi


def _fi_public(fi: dict) -> dict:
    return {"code": fi.get("forme_imposee"), "libelle": fi.get("libelle"), "extrait": fi.get("extrait") or "",
            "clauses": fi.get("clauses") or [], "source": fi.get("source"), "relu_le": fi.get("relu_le"),
            "dossier_disponible": bool(fi.get("dossier_disponible"))}


def _public_params(params: dict) -> dict:
    return {k: v for k, v in params.items() if not str(k).startswith("_")
            and k not in ("membres_hors_ligne", "masquer_repartition")}


def _members_public(members: list, show_prices: bool, viewer_invite_id=None) -> list:
    out = []
    for m in members:
        row = {"membre": {"mandataire": "mandataire", "invite": "partenaire", "hors_ligne": "hors_ligne"}[m["kind"]],
               "company": m.get("company"), "role": m.get("role"), "lot": m.get("lot") or ""}
        if show_prices or (viewer_invite_id is not None and m.get("invite_id") == viewer_invite_id):
            row["prix_lot_ht"] = m.get("prix_lot_ht")
        out.append(row)
    return out


def _owner_payload(db: Session, project: Project, conv, user: User) -> dict:
    owner_ids = member_ids(user, db)
    company = gc._company_for(db, project)
    status = conv.status if conv is not None else "aucune"
    params = gc.merged_params(conv, project)
    fi = _fi_payload(conv, project, db, owner_ids)
    built = gc.build_context(db, project, conv, company,
                             version=(conv.version if conv is not None and status in gc.ACTIVE else None),
                             brouillon=status not in gc.ACTIVE)
    ctx = built["ctx"]
    manques = list(built["manques"])
    if not (conv is not None and conv.forme in gc.FORMES):
        manques.insert(0, "Forme du groupement à choisir : chacun responsable de sa part (conjoint) "
                          "ou tous responsables de tout (solidaire)")
    sigs = gc.signatures_of(db, conv) if conv is not None else []
    out = {
        "project_id": project.id,
        "status": status, "status_label": gc.STATUS_LABELS.get(status, status),
        "version": (conv.version or 0) if conv is not None else 0,
        "avertissement": gc.AVERTISSEMENT, "nature_accord": gc.NATURE_ACCORD,
        "forme": (conv.forme if conv is not None else "") or "",
        "forme_label": _forme_label(conv.forme if conv is not None else ""),
        "mandataire_solidaire": bool(conv.mandataire_solidaire) if conv is not None else False,
        "forme_imposee": _fi_public(fi),
        "habilitation": gc.merged_habilitation(conv),
        "params": _public_params(params),
        "membres_hors_ligne": params.get("membres_hors_ligne") or [],
        "candidats_hors_ligne": [{k: o[k] for k in ("link_id", "company", "siret", "lot", "representant_legal")}
                                 for o in gc.offline_candidates(db, project)],
        "options": _options(project),
        "membres": _members_public(ctx["members"], show_prices=True),
        # total FIGÉ (révélé aux membres) seulement une fois la convention générée ; en brouillon,
        # total_estime_ht = somme des prix connus (vue mandataire uniquement), None si incomplet.
        "total_offre_ht": conv.total_offre_ht if status in gc.ACTIVE else None,
        "total_estime_ht": ctx.get("total_ht") if status not in gc.ACTIVE else conv.total_offre_ht,
        "manques": manques,
        "peut_generer": not manques,
        "avertissements": gc.warnings_for(conv, project, ctx, fi, built["sous_traitants"], db=db),
        "content_hash": conv.content_hash if conv is not None and status in gc.ACTIVE + ("perimee",) else None,
        "frozen_at": conv.frozen_at.isoformat() if conv is not None and conv.frozen_at else None,
        "signatures": [gc.serialize_signature(s, for_owner=True) for s in sigs],
        "n_signataires": len(sigs) if status in gc.ACTIVE else 0,
        "n_accords": sum(1 for s in sigs if s.status in ("signed", "hors_ligne")) if status in gc.ACTIVE else 0,
        "state": groupement_state(project, db),
    }
    if status in gc.ACTIVE or status == "perimee":
        out["content_md"] = conv.content_md
        out["apercu_md"] = None
    else:
        out["content_md"] = None
        out["masquer_repartition"] = bool(params.get("masquer_repartition"))
        out["apercu_md"] = gc.render(ctx, mask="all" if params.get("masquer_repartition") else "none")
    mine = next((s for s in sigs if gc.member_kind(s) == "mandataire"), None)
    out["ma_signature"] = {
        "status": mine.status if mine else None,
        "peut_valider": bool(mine and status == "a_signer" and mine.status == "pending"),
        "signataire_nom": (mine.signataire_nom if mine else "") or ((company.representant_legal if company else "") or ""),
        "signataire_qualite": (mine.signataire_qualite if mine else "") or params.get("mandataire_qualite") or "",
        "email_verifie": bool(getattr(user, "email_verified", False)),
    }
    return out


def _get_or_create_draft(db: Session, project: Project, user: User) -> GroupementConvention:
    conv = gc.get_convention(db, project.id)
    if conv is None:
        fi = gc.forme_imposee(project)
        conv = GroupementConvention(
            project_id=project.id, owner_id=_inv().tenant_owner_id(project, db),
            forme=(fi["forme_imposee"] if fi["forme_imposee"] in gc.FORMES else ""),
            mandataire_solidaire=False, forme_imposee=fi["forme_imposee"],
            forme_imposee_extrait=fi.get("extrait") or "",
            habilitation=gc.default_habilitation(), params={}, status="draft", version=0)
        db.add(conv)
        try:
            db.commit()
        except Exception:
            # project_id UNIQUE : création concurrente (deux onglets) → on relit l'autre.
            db.rollback()
            conv = gc.get_convention(db, project.id)
            if conv is None:
                raise
        db.refresh(conv)
    return conv


def _remettre_en_brouillon(db: Session, project: Project, conv, reason: str, user: User, request: Request):
    """Modifier une convention générée = nouveau brouillon : les accords donnés sur l'ancien
    texte deviennent caducs (tracé)."""
    if conv.status in gc.ACTIVE:
        gc.perimer(db, project, reason, actor=f"user:{user.id}", actor_kind="owner",
                   ip=audit.client_ip(request))
        db.refresh(conv)
    if conv.status == "perimee":
        conv.status = "draft"


# ── Assistant (mandataire) ───────────────────────────────────────────────────────────

@owner_router.get("")
@limiter.limit("240/hour")
def get_convention(request: Request, project_id: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    conv = gc.get_convention(db, project.id)
    gc.refresh(db, project, conv)
    return _owner_payload(db, project, conv, current_user)


class HorsLigneEntry(BaseModel):
    link_id: int
    prix_lot_ht: Optional[float] = None
    lot: Optional[str] = None
    representant_legal: Optional[str] = None
    signataire_qualite: Optional[str] = None


class BrouillonIn(BaseModel):
    forme: Optional[str] = None                     # '' | conjoint | solidaire
    mandataire_solidaire: Optional[bool] = None
    habilitation: Optional[dict] = None
    params: Optional[dict] = None
    membres_hors_ligne: Optional[list[HorsLigneEntry]] = None
    masquer_repartition: Optional[bool] = None
    confirmer_modification: bool = False            # requis si la convention est déjà générée


@owner_router.put("")
@limiter.limit("120/hour")
def save_draft(request: Request, project_id: int, data: BrouillonIn,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Enregistre les choix du brouillon. Sur une convention déjà générée, exige
    confirmer_modification=true : le texte change, les accords déjà enregistrés tombent."""
    project = _project(project_id, current_user, db)
    conv = _get_or_create_draft(db, project, current_user)
    gc.refresh(db, project, conv)
    fields = data.model_fields_set - {"confirmer_modification"}
    if conv.status in gc.ACTIVE and fields:
        if fields == {"masquer_repartition"}:
            raise HTTPException(422, "« Masquer la répartition » n'existe qu'en brouillon : une fois générée, "
                                     "la convention montre la même répartition à tous les membres.")
        if not data.confirmer_modification:
            raise HTTPException(409, {"code": "convention_generee",
                                      "message": "La convention est déjà générée. La modifier annule les accords "
                                                 "déjà enregistrés et demande une nouvelle génération : confirmez."})

    try:
        hab = gc.validate_habilitation(data.habilitation) if data.habilitation is not None else None
        prm = gc.validate_params(data.params) if data.params is not None else None
    except gc.ParamError as e:
        raise HTTPException(422, str(e))
    if data.forme is not None and data.forme not in ("", "conjoint", "solidaire"):
        raise HTTPException(422, "Forme inconnue : « conjoint » (chacun responsable de sa part) ou "
                                 "« solidaire » (tous responsables de tout).")

    hl = None
    if data.membres_hors_ligne is not None:
        cands = {o["link_id"] for o in gc.offline_candidates(db, project)}
        seen, hl = set(), []
        for e in data.membres_hors_ligne:
            if e.link_id not in cands:
                raise HTTPException(404, "Partenaire hors ligne introuvable : il doit être rattaché à ce marché "
                                         "sans invitation (et ne pas être sous-traitant).")
            if e.link_id in seen:
                raise HTTPException(422, "Ce partenaire hors ligne est déjà dans la liste.")
            seen.add(e.link_id)
            if e.prix_lot_ht is not None and (e.prix_lot_ht != e.prix_lot_ht or e.prix_lot_ht < 0 or e.prix_lot_ht > 1e10):
                raise HTTPException(422, "Le prix du lot doit être compris entre 0 et 10 milliards d'euros HT.")
            hl.append({"link_id": e.link_id,
                       "prix_lot_ht": round(float(e.prix_lot_ht), 2) if e.prix_lot_ht is not None else None,
                       "lot": gc._clean(e.lot, 255) if e.lot is not None else "",
                       "representant_legal": gc._clean(e.representant_legal, 255) if e.representant_legal else "",
                       "signataire_qualite": gc._clean(e.signataire_qualite, 120) if e.signataire_qualite else ""})

    if fields:
        _remettre_en_brouillon(db, project, conv, "convention modifiée par le mandataire", current_user, request)
    if data.forme is not None:
        conv.forme = data.forme
        if data.forme != "conjoint":
            conv.mandataire_solidaire = False
    if data.mandataire_solidaire is not None:
        conv.mandataire_solidaire = bool(data.mandataire_solidaire) and (conv.forme == "conjoint")
    if hab is not None:
        merged = gc.merged_habilitation(conv)
        merged.update(hab)
        conv.habilitation = merged
    params = dict(conv.params or {})
    if prm is not None:
        params.update(prm)
    if hl is not None:
        params["membres_hors_ligne"] = hl
    if data.masquer_repartition is not None:
        params["masquer_repartition"] = bool(data.masquer_repartition)
    conv.params = params                       # NOUVEAU dict (colonne JSON)
    if conv.status != "draft" and fields:
        conv.status = "draft"
    db.commit()
    db.refresh(conv)
    return _owner_payload(db, project, conv, current_user)


@owner_router.post("/relire-dce")
@limiter.limit("10/hour")
def relire_dce(request: Request, project_id: int, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Relit le dossier du marché archivé (texte intégral, extraction bornée, 0 LLM) : la
    citation de l'analyse y est re-vérifiée ; à défaut, les phrases qui parlent de la forme du
    groupement sont proposées « à lire », sans interprétation."""
    project = _project(project_id, current_user, db)
    owner_ids = member_ids(current_user, db)
    text = gc.dce_text(db, project, owner_ids)
    if not text:
        raise HTTPException(404, "Aucun dossier du marché lisible n'est archivé pour ce marché : importez-le "
                                 "depuis la fiche du marché.")
    fi = gc.forme_imposee(project, text_integral=text)
    conv = _get_or_create_draft(db, project, current_user)
    conv.forme_imposee = fi["forme_imposee"]
    conv.forme_imposee_extrait = fi.get("extrait") or ""
    params = dict(conv.params or {})
    params["_forme_relue_le"] = utcnow().isoformat()
    params["_clauses"] = fi.get("clauses") or []
    params["_forme_libelle"] = fi.get("libelle") or ""
    conv.params = params
    db.commit()
    fi["relu_le"] = params["_forme_relue_le"]
    fi["dossier_disponible"] = True
    return {"forme_imposee": _fi_public(fi)}


class GenererIn(BaseModel):
    regenerer: bool = False


# Plafonds des emails « convention à valider » (process unique : en mémoire suffit, comme
# l'anti-rafale des notifications de groupement). Une régénération en boucle ne doit pas
# transformer Adjugo en canal de spam vers les partenaires déjà invités.
CONV_MAILS_PER_INVITE_PER_DAY = 3
CONV_MAILS_PER_ORG_PER_DAY = 60
_CONV_MAILS: dict = {}
_CONV_MAILS_LOCK = __import__("threading").Lock()


def _conv_mail_allowed(owner_id: int, invite_id: int) -> bool:
    import time
    now = time.time()
    with _CONV_MAILS_LOCK:
        if len(_CONV_MAILS) > 20000:             # borne mémoire
            _CONV_MAILS.clear()
        keys = (("inv", invite_id), ("org", owner_id))
        logs = {k: [t for t in _CONV_MAILS.get(k, []) if now - t < 86400] for k in keys}
        if len(logs[keys[0]]) >= CONV_MAILS_PER_INVITE_PER_DAY or len(logs[keys[1]]) >= CONV_MAILS_PER_ORG_PER_DAY:
            _CONV_MAILS.update(logs)
            return False
        for k in keys:
            logs[k].append(now)
        _CONV_MAILS.update(logs)
        return True


def _mail_a_valider(db: Session, project: Project, conv, user: User, request: Request) -> int:
    """« Convention à valider » à chaque partenaire invité (best-effort, hors requête).
    Jamais depuis la démo ; seulement si l'expéditeur a confirmé son adresse ; anti-rafale
    par invitation (plafond existant des notifications de groupement, 30 min) + plafonds
    quotidiens par partenaire et par organisation."""
    inv_mod = _inv()
    from app.services.demo_search import is_demo
    if is_demo(user) or not getattr(user, "email_verified", False):
        return 0
    base = (_settings.APP_BASE_URL or str(request.base_url)).rstrip("/")
    company = gc._company_for(db, project)
    chef = (company.name if company and company.name else "le chef de file")
    mails = []
    for s in gc.signatures_of(db, conv):
        if not s.invite_id:
            continue
        inv = db.query(ProjectInvite).filter(ProjectInvite.id == s.invite_id).first()
        if not inv or not inv_mod._is_email(inv.recipient) or inv_mod._invite_is_demo(inv, db):
            continue
        if not inv_mod._notify_allowed(("convention_a_valider", inv.id)):
            continue
        if not _conv_mail_allowed(conv.owner_id, inv.id):
            continue
        mails.append((inv.recipient, f"Convention de groupement à valider — {project.name[:60]}",
                      f"Bonjour,\n\n{chef} a généré la convention de groupement pour le marché « {project.name} » "
                      f"(version {conv.version}). Relisez-la et donnez votre accord depuis votre espace :\n"
                      f"{base}/invite/{inv.token}\n\n"
                      f"L'annexe de répartition indique la part et le prix de vente de chaque membre, ainsi que "
                      f"le total de l'offre commune.\n\n{gc.NATURE_ACCORD}\n\n{gc.AVERTISSEMENT}\n\n— Adjugo"))
    inv_mod._send_mails_async(mails)
    return len(mails)


@owner_router.post("/generer")
@limiter.limit("20/hour")
def generer(request: Request, project_id: int, data: GenererIn = None,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fige l'offre commune ET génère la convention (modèle déterministe, 0 LLM) : texte figé,
    empreinte unique, total révélé aux membres, un accord attendu par membre."""
    data = data or GenererIn()
    project = _project(project_id, current_user, db)
    conv = gc.get_convention(db, project.id)
    if conv is None or conv.forme not in gc.FORMES:
        raise HTTPException(422, {"message": "Choisissez d'abord la forme du groupement.",
                                  "missing": ["Forme du groupement : chacun responsable de sa part (conjoint) "
                                              "ou tous responsables de tout (solidaire)"]})
    gc.refresh(db, project, conv)
    if conv.status in gc.ACTIVE and not data.regenerer:
        raise HTTPException(409, {"code": "deja_generee",
                                  "message": f"La convention est déjà générée (version {conv.version}). La "
                                             "régénérer annule les accords déjà enregistrés : confirmez."})
    company = gc._company_for(db, project)
    built = gc.build_context(db, project, conv, company)
    if built["manques"]:
        raise HTTPException(422, {"message": "Impossible de générer la convention : il manque des éléments.",
                                  "missing": built["manques"]})
    ctx = built["ctx"]
    ctx["brouillon"] = False
    content = gc.render(ctx)
    h = gc.sha256(content)
    members = ctx["members"]
    total = ctx["total_ht"]
    frozen = utcnow()

    if conv.status in gc.ACTIVE:                      # régénération confirmée : tracé
        gc.perimer(db, project, "convention régénérée par le mandataire",
                   actor=f"user:{current_user.id}", actor_kind="owner", ip=audit.client_ip(request))
        db.refresh(conv)
    conv.content_md = content
    conv.content_hash = h
    conv.total_offre_ht = total
    conv.version = ctx["version"]
    conv.frozen_at = frozen
    conv.status = "a_signer"
    # Ce que le règlement impose, tel qu'affiché au moment de la génération (trace).
    fi = _fi_payload(conv, project, db, member_ids(current_user, db))
    conv.forme_imposee = fi.get("forme_imposee") or "non_verifie"
    conv.forme_imposee_extrait = fi.get("extrait") or ""
    params = dict(conv.params or {})
    # Valeurs EFFECTIVES figées avec le texte (un défaut dérivé — estimation, « travaux » —
    # ne doit pas faire dériver la convention générée).
    effective = gc.merged_params(conv, project)
    for k in gc.PARAM_KEYS + ["part_mandataire_ht", "lot_mandataire", "mandataire_qualite"]:
        params[k] = effective.get(k)
    params["masquer_repartition"] = False             # n'existe qu'en brouillon
    conv.params = params
    lead = next((m for m in members if m["kind"] == "mandataire"), {})
    plan = dict(project.groupement_plan) if isinstance(project.groupement_plan, dict) else {}
    plan["offre"] = {"total_ht": total, "frozen_at": frozen.isoformat(),
                     "parts": gc.snapshot_parts(members), "lead_total_ht": lead.get("prix_lot_ht"),
                     "convention_id": conv.id, "convention_version": conv.version}
    project.groupement_plan = plan                    # NOUVEAU dict : SQLAlchemy détecte le changement
    gc.sync_signatures(db, conv, members)
    db.commit()
    db.refresh(conv)

    owner = _inv().tenant_owner_id(project, db)
    ip = audit.client_ip(request)
    audit.record(db, action="offer.frozen", owner_id=owner, project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner", target_type="project",
                 target_id=project.id, detail=f"total {gc.eur(total)} HT (convention v{conv.version})"[:255], ip=ip)
    audit.record(db, action="convention.generated", owner_id=owner, project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner", target_type="convention",
                 target_id=conv.id, detail=f"version {conv.version} — empreinte {h[:12]}", ip=ip)
    sent = 0
    try:
        sent = _mail_a_valider(db, project, conv, current_user, request)
    except Exception as e:
        logger.warning("emails « convention à valider » non envoyés : %s", e)
    out = _owner_payload(db, project, conv, current_user)
    out["emails_envoyes"] = sent
    return out


class ValiderIn(BaseModel):
    content_hash: str = Field("", max_length=64)
    signataire_nom: str = Field("", max_length=255)
    signataire_qualite: str = Field("", max_length=120)
    accepte: bool = False


def _check_valider_body(data: ValiderIn, conv) -> None:
    if not data.accepte:
        raise HTTPException(422, "Cochez « J'ai lu la convention et je donne mon accord ».")
    if not gc._clean(data.signataire_nom):
        raise HTTPException(422, "Indiquez le nom de la personne qui donne l'accord.")
    if (data.content_hash or "") != (conv.content_hash or ""):
        raise HTTPException(409, {"code": "texte_modifie",
                                  "message": "La convention a changé depuis votre lecture : relisez la nouvelle "
                                             "version avant de donner votre accord."})


def _status_conflict(conv) -> HTTPException:
    if conv is None or conv.status == "draft":
        return HTTPException(409, {"code": "pas_generee", "message": "La convention n'est pas encore générée."})
    if conv.status == "perimee":
        return HTTPException(409, {"code": "perimee",
                                   "message": "La convention n'est plus à jour (une part, un prix ou la composition "
                                              "a changé) : le chef de file doit la régénérer."})
    return HTTPException(409, {"code": "statut", "message": "Accord impossible dans l'état actuel de la convention."})


def _after_agreement(db: Session, project: Project, conv, by_owner: bool) -> None:
    """Tous d'accord → 'signee' (+ email au mandataire, si l'accord vient d'un partenaire)."""
    sigs = gc.signatures_of(db, conv)
    if conv.status == "a_signer" and gc.all_agreed(sigs):
        conv.status = "signee"
        db.commit()
        if not by_owner:
            try:
                inv_mod = _inv()
                to = inv_mod._mandataire_email(conv.owner_id, db)
                if to and inv_mod._notify_allowed(("convention_validee", conv.id, conv.version)):
                    base = (_settings.APP_BASE_URL or "").rstrip("/")
                    inv_mod._send_mails_async([(
                        to, f"Convention validée par tous les membres — {project.name[:60]}",
                        f"Bonjour,\n\nTous les membres du groupement ont donné leur accord sur la convention "
                        f"(version {conv.version}) du marché « {project.name} ».\n\nLe PDF, avec la liste des "
                        f"accords enregistrés, est disponible dans la fiche du marché :\n{base}/app\n\n"
                        f"{gc.AVERTISSEMENT}\n\n— Adjugo")])
            except Exception:
                pass


@owner_router.post("/valider")
@limiter.limit("30/hour")
def valider_mandataire(request: Request, project_id: int, data: ValiderIn,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Accord du mandataire, depuis son compte (adresse email confirmée exigée)."""
    project = _project(project_id, current_user, db)
    conv = gc.get_convention(db, project.id)
    gc.refresh(db, project, conv)
    if conv is None or conv.status not in gc.ACTIVE:
        raise _status_conflict(conv)
    mine = next((s for s in gc.signatures_of(db, conv) if gc.member_kind(s) == "mandataire"), None)
    if mine is None:
        raise HTTPException(409, {"code": "statut", "message": "Régénérez la convention."})
    if mine.status == "signed":
        return _owner_payload(db, project, conv, current_user)         # idempotent
    if not getattr(current_user, "email_verified", False):
        raise HTTPException(403, {"code": "email_non_verifie",
                                  "message": "Confirmez d'abord votre adresse email (lien reçu par mail) pour "
                                             "enregistrer votre accord."})
    _check_valider_body(data, conv)
    mine.status = "signed"
    mine.signed_at = utcnow()
    mine.user_id = current_user.id
    mine.identity_level = "compte_verifie"
    mine.verified_email = (current_user.email or "")[:255]
    mine.signataire_nom = gc._clean(data.signataire_nom, 255)
    mine.signataire_qualite = gc._clean(data.signataire_qualite, 120)
    mine.content_hash = conv.content_hash
    mine.ip = audit.client_ip(request)
    db.commit()
    audit.record(db, action="convention.signed", owner_id=_inv().tenant_owner_id(project, db),
                 project_id=project.id, actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="convention", target_id=conv.id,
                 detail=f"version {conv.version} — empreinte {conv.content_hash[:12]}", ip=audit.client_ip(request))
    _after_agreement(db, project, conv, by_owner=True)
    db.refresh(conv)
    return _owner_payload(db, project, conv, current_user)


class HorsLigneIn(BaseModel):
    accord_recueilli: bool = True
    signataire_nom: str = Field("", max_length=255)
    signataire_qualite: str = Field("", max_length=120)


@owner_router.post("/hors-ligne/{link_id}")
@limiter.limit("60/hour")
def accord_hors_ligne(request: Request, project_id: int, link_id: int, data: HorsLigneIn,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le mandataire coche l'accord d'un membre rattaché SANS invitation (recueilli hors
    Adjugo, sur papier par exemple). Statut 'hors_ligne', imprimé tel quel dans le PDF."""
    project = _project(project_id, current_user, db)
    conv = gc.get_convention(db, project.id)
    gc.refresh(db, project, conv)
    if conv is None or conv.status not in gc.ACTIVE:
        raise _status_conflict(conv)
    sig = next((s for s in gc.signatures_of(db, conv) if s.cotraitant_link_id == link_id), None)
    if sig is None:
        raise HTTPException(404, "Ce partenaire hors ligne ne figure pas dans la convention.")
    owner = _inv().tenant_owner_id(project, db)
    if data.accord_recueilli:
        if sig.status != "hors_ligne":
            sig.status = "hors_ligne"
            sig.signed_at = utcnow()
            sig.user_id = current_user.id
            sig.identity_level = ""
            sig.verified_email = ""
            sig.content_hash = conv.content_hash
            sig.ip = audit.client_ip(request)
            if gc._clean(data.signataire_nom):
                sig.signataire_nom = gc._clean(data.signataire_nom, 255)
            if gc._clean(data.signataire_qualite):
                sig.signataire_qualite = gc._clean(data.signataire_qualite, 120)
            db.commit()
            audit.record(db, action="convention.hors_ligne", owner_id=owner, project_id=project.id,
                         actor=f"user:{current_user.id}", actor_kind="owner", target_type="convention",
                         target_id=conv.id, detail=(sig.company_name or "")[:255], ip=audit.client_ip(request))
            _after_agreement(db, project, conv, by_owner=True)
    elif sig.status == "hors_ligne":
        sig.status = "pending"
        sig.signed_at = None
        sig.user_id = None
        if conv.status == "signee":
            conv.status = "a_signer"
        db.commit()
        audit.record(db, action="convention.hors_ligne_retire", owner_id=owner, project_id=project.id,
                     actor=f"user:{current_user.id}", actor_kind="owner", target_type="convention",
                     target_id=conv.id, detail=(sig.company_name or "")[:255], ip=audit.client_ip(request))
    db.refresh(conv)
    return _owner_payload(db, project, conv, current_user)


def _pdf_response(pdf: bytes, project: Project, version) -> Response:
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9._ -]", "_", (project.name or "marche"))[:40].strip() or "marche"
    name = f"Convention_groupement_{safe}_v{version}.pdf" if version else f"Convention_groupement_{safe}_brouillon.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(name)})


@owner_router.get("/pdf")
@limiter.limit("60/hour")
def pdf_mandataire(request: Request, project_id: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    conv = gc.get_convention(db, project.id)
    gc.refresh(db, project, conv)
    if conv is not None and conv.status in gc.ACTIVE + ("perimee",) and conv.content_md:
        return _pdf_response(gc.convention_pdf(conv, gc.signatures_of(db, conv)), project, conv.version)
    params = gc.merged_params(conv, project)
    built = gc.build_context(db, project, conv, gc._company_for(db, project), brouillon=True)
    md = gc.render(built["ctx"], mask="all" if params.get("masquer_repartition") else "none")
    return _pdf_response(gc.pdf_bytes(md, "Convention de groupement (brouillon)"), project, None)


# ── Vue PARTENAIRE (lien magique ; compte facultatif après claim) ─────────────────────

def _optional_user(request: Request, db: Session) -> Optional[User]:
    """Compte Adjugo du partenaire si un Bearer valide accompagne la requête (« Partagé avec
    moi »), sinon None. Jamais d'erreur : un jeton absent/invalide = invité sans compte."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return get_current_user(token=auth[7:].strip(), db=db)
    except HTTPException:
        return None
    except Exception:
        return None


def _guest_ctx(token: str, db: Session):
    inv_mod = _inv()
    inv = inv_mod._valid_invite(token, db)          # révoqué → 404 ; décliné / expiré → 410
    project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(404, "Projet introuvable ou retiré")
    if inv_mod._network_pending(inv, db):
        # Invitation du RÉSEAU pas encore acceptée (aperçu minimal) : ni acheteur, ni composition du
        # groupement. Le brouillon de la convention cite les deux (membres, « Acheteur : … ») → rien
        # de la convention, pas même son état, sur les trois routes (lecture, PDF, accord).
        raise HTTPException(403, {"code": "apercu_minimal",
                                  "message": "Acceptez d'abord l'invitation depuis votre compte Adjugo pour voir "
                                             "la convention de groupement."})
    conv = gc.get_convention(db, project.id)
    gc.refresh(db, project, conv)
    return inv, project, conv


def _identity_level(inv, user: Optional[User]) -> tuple:
    if user is not None and inv.accepted_by_user_id == user.id and getattr(user, "email_verified", False):
        return "compte_verifie", (user.email or "")
    if inv.verified_at and inv.verified_email:
        return "email_verifie", inv.verified_email
    return "lien_seul", ""


def _guest_payload(db: Session, inv, project: Project, conv, user: Optional[User]) -> dict:
    status = conv.status if conv is not None else "aucune"
    base = {"status": status, "status_label": gc.STATUS_LABELS.get(status, status),
            "avertissement": gc.AVERTISSEMENT, "nature_accord": gc.NATURE_ACCORD}
    if conv is None:
        base["message"] = "Le chef de file n'a pas encore préparé la convention de groupement."
        return base
    sigs = gc.signatures_of(db, conv)
    mine = next((s for s in sigs if s.invite_id == inv.id), None)
    hab = gc.merged_habilitation(conv)
    params = gc.merged_params(conv, project)
    base.update({
        "version": conv.version or 0,
        "forme": conv.forme or "", "forme_label": _forme_label(conv.forme),
        "mandataire_solidaire": bool(conv.mandataire_solidaire),
        "habilitation": [{"key": h["key"], "libelle": h["libelle"], "terme": h["terme"]}
                         for h in gc.HABILITATION if hab.get(h["key"])],
        "params": [{"key": p["key"], "libelle": p["libelle"], "valeur": params.get(p["key"]),
                    "valeur_libelle": _param_value_label(p, params.get(p["key"]))}
                   for p in gc.PARAMS],
    })
    generated = status in gc.ACTIVE or status == "perimee"
    full = generated and mine is not None
    if generated and mine is None:
        # Non signataire (sous-traitant, ou lien ajouté après la génération) : il n'est pas partie à
        # la convention → ni texte, ni annexe des prix, ni total.
        base.update({"content_md": None, "content_hash": None, "total_offre_ht": None,
                      "membres": [], "apercu_md": None})
    elif full:
        # Texte figé : identique pour tous (annexe de répartition incluse, un seul hash).
        # Convention caduque : l'ancienne annexe reste dans le texte ; on ne renvoie JAMAIS les prix
        # courants (ils peuvent avoir changé depuis : c'est justement la cause de la péremption).
        parts = ((project.groupement_plan or {}).get("offre") or {}).get("parts") or [] \
            if isinstance(project.groupement_plan, dict) and status in gc.ACTIVE else []
        base.update({
            "content_md": conv.content_md, "content_hash": conv.content_hash,
            "total_offre_ht": conv.total_offre_ht,
            "frozen_at": conv.frozen_at.isoformat() if conv.frozen_at else None,
            "membres": _members_public([dict(p, kind=p.get("kind") or "invite") for p in parts
                                        if isinstance(p, dict)], show_prices=True),
            "signatures": [gc.serialize_signature(s, for_owner=False) for s in sigs],
            "n_signataires": len(sigs),
            "n_accords": sum(1 for s in sigs if s.status in ("signed", "hors_ligne")),
            "warning_two_members": len(sigs) == 2,
        })
    else:
        # Brouillon (ou caduque sans avoir été signataire) : JAMAIS le prix des autres ni le total.
        built = gc.build_context(db, project, conv, gc._company_for(db, project), brouillon=True)
        base.update({
            "content_md": None, "content_hash": None, "total_offre_ht": None,
            "membres": _members_public(built["ctx"]["members"], show_prices=False, viewer_invite_id=inv.id),
            "apercu_md": gc.render(built["ctx"], mask="member", viewer_invite_id=inv.id),
        })
    level, _ = _identity_level(inv, user)
    inv_mod = _inv()
    binding = inv_mod._binding_required(inv)
    claimed_other = bool(inv.accepted_by_user_id) and (user is None or user.id != inv.accepted_by_user_id)
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    base["ma_signature"] = {
        "status": mine.status if mine else None,
        "signataire": mine is not None,
        "peut_valider": bool(mine and status == "a_signer" and mine.status == "pending"),
        "identite_prevue": level, "identite_libelle": gc.IDENTITY_LABELS.get(level, ""),
        "verification_requise": bool(binding and not inv.verified_at and level != "compte_verifie"),
        "compte_requis": claimed_other,
        "signataire_nom": (mine.signataire_nom if mine and mine.signataire_nom else (c.representant_legal if c else "")) or "",
        "signataire_qualite": (mine.signataire_qualite if mine and mine.signataire_qualite else (c.signataire_qualite if c else "")) or "",
        "signed_at": mine.signed_at.isoformat() if mine and mine.signed_at else None,
    }
    if status == "a_signer" and mine is None:
        base["message"] = ("Vous n'êtes pas signataire de cette convention (sous-traitant, ou ajouté après sa "
                           "génération).")
    return base


def _param_value_label(spec: dict, value) -> str:
    if spec["type"] == "choix":
        return next((c["libelle"] for c in spec["choix"] if c["value"] == value), "")
    if spec["type"] == "oui_non":
        return "Oui" if value else "Non"
    if spec["type"] == "entier":
        return f"{value} {spec.get('unite', '')}".strip()
    return str(value or "")


@guest_router.get("")
@limiter.limit("120/minute")
def guest_convention(token: str, request: Request, db: Session = Depends(get_db)):
    inv, project, conv = _guest_ctx(token, db)
    return _guest_payload(db, inv, project, conv, _optional_user(request, db))


@guest_router.get("/pdf")
@limiter.limit("30/minute")
def guest_convention_pdf(token: str, request: Request, db: Session = Depends(get_db)):
    inv, project, conv = _guest_ctx(token, db)
    sigs = gc.signatures_of(db, conv) if conv is not None else []
    mine = next((s for s in sigs if s.invite_id == inv.id), None)
    if conv is None or not conv.content_md or not (conv.status in gc.ACTIVE or (conv.status == "perimee" and mine)):
        raise HTTPException(409, {"code": "pas_generee",
                                  "message": "Le PDF de la convention est disponible une fois la convention générée."})
    if mine is None:
        # Non signataire (sous-traitant, lien ajouté après la génération) : ni texte, ni annexe des
        # prix, ni total — même règle que la vue JSON (_guest_payload).
        raise HTTPException(403, {"code": "pas_signataire",
                                  "message": "Vous n'êtes pas signataire de cette convention : elle ne vous est pas "
                                             "communiquée."})
    audit.record(db, action="guest.download_convention", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_inv()._guest_actor(inv), actor_kind="guest", target_type="convention",
                 target_id=conv.id, invite_id=inv.id, detail=f"version {conv.version}",
                 ip=audit.client_ip(request))
    return _pdf_response(gc.convention_pdf(conv, sigs), project, conv.version)


@guest_router.post("/valider")
@limiter.limit("20/hour")
def guest_valider(token: str, data: ValiderIn, request: Request, db: Session = Depends(get_db)):
    """Accord du partenaire depuis SON espace. Gate d'identité INCHANGÉ (_binding_required +
    OTP, comme la soumission de la part) ; un compte ayant réclamé le lien (adresse vérifiée)
    vaut preuve d'identité. Le niveau réellement prouvé est stocké et imprimé dans le PDF."""
    inv_mod = _inv()
    inv, project, conv = _guest_ctx(token, db)
    inv_mod._refuse_if_demo_invite(inv, db)
    if conv is None or conv.status not in gc.ACTIVE:
        raise _status_conflict(conv)
    mine = next((s for s in gc.signatures_of(db, conv) if s.invite_id == inv.id), None)
    if mine is None:
        raise HTTPException(403, {"code": "pas_signataire",
                                  "message": "Vous n'êtes pas signataire de cette convention."})
    user = _optional_user(request, db)
    if mine.status == "signed":
        return _guest_payload(db, inv, project, conv, user)           # idempotent
    if inv.accepted_by_user_id and (user is None or user.id != inv.accepted_by_user_id):
        raise HTTPException(403, {"code": "compte_requis",
                                  "message": "Ce dossier est rattaché à un compte Adjugo : connectez-vous avec ce "
                                             "compte pour valider la convention."})
    level, email = _identity_level(inv, user)
    if inv_mod._binding_required(inv) and not inv.verified_at and level != "compte_verifie":
        raise HTTPException(403, {"code": "identity_unverified",
                                  "message": "Vérifiez votre adresse email avant de valider la convention."})
    _check_valider_body(data, conv)
    mine.status = "signed"
    mine.signed_at = utcnow()
    mine.user_id = user.id if level == "compte_verifie" else None
    mine.identity_level = level
    mine.verified_email = (email or "")[:255]
    mine.signataire_nom = gc._clean(data.signataire_nom, 255)
    mine.signataire_qualite = gc._clean(data.signataire_qualite, 120)
    mine.content_hash = conv.content_hash
    mine.ip = audit.client_ip(request)
    db.commit()
    audit.record(db, action="convention.signed", owner_id=inv_mod.tenant_owner_id(project, db),
                 project_id=project.id, actor=inv_mod._guest_actor(inv), actor_kind="guest",
                 target_type="convention", target_id=conv.id, invite_id=inv.id,
                 detail=(mine.company_name or inv.company_name or "")[:255], ip=audit.client_ip(request))
    _after_agreement(db, project, conv, by_owner=False)
    db.refresh(conv)
    return _guest_payload(db, inv, project, conv, user)
