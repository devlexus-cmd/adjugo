"""
Router RÉDACTEUR DE DCE (côté ACHETEUR) — Pilier 1 du produit collectivités.

Produit SÉPARÉ du logiciel PME : sert la page autonome /acheteur et l'endpoint de
génération. Ne touche AUCUNE donnée d'un tenant PME (génération pure à partir du besoin
saisi) → cloisonnement et neutralité préservés (cf. réseau à deux faces).

Accès : protégeable par un CODE (env DCE_ACCESS_CODE). Si le code est défini, il est
exigé (en-tête X-Dce-Code de préférence, ou ?code= en repli) et comparé en temps
constant. En PRODUCTION, le code est OBLIGATOIRE (garde-fou fail-closed dans main.py).
Toujours rate-limité ; le tenant LLM est scopé PAR CLIENT (isolation coût + résilience).
"""
import logging
import os
import secrets

import json

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.ratelimit import limiter, real_client_ip
from app.core.http import content_disposition
from app.core.security import decode_token
from app.services.llm import LLMUnavailable
from app.services.agents.dce_redaction import generer_dce, procedure_recommandee
from app.services.agents.sourcing_acheteur import sourcer_lots
from app.services.dce_export import FORMATS

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/dce", tags=["Rédacteur de DCE (acheteur)"])


def _has_valid_acheteur_token(request: Request) -> bool:
    """Un acheteur CONNECTÉ (token JWT `typ=acheteur` valide) vaut accès — plus besoin du
    code. On vérifie signature + expiration + claim (pas de DB ici : la validation complète
    a lieu sur les endpoints /api/acheteur/*, celui-ci n'est qu'un portillon de confort)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    try:
        return decode_token(auth[7:].strip()).get("typ") == "acheteur"
    except Exception:
        return False


def _check_access(request: Request) -> None:
    """Si DCE_ACCESS_CODE est défini, exige le code (en-tête X-Dce-Code, ou ?code= en repli,
    comparé en TEMPS CONSTANT) OU un acheteur connecté. Sinon, ouvert (dev)."""
    code = os.getenv("DCE_ACCESS_CODE", "").strip()
    if not code:
        return
    provided = (request.headers.get("x-dce-code")
                or request.query_params.get("code") or "").strip()
    # Comparaison sur bytes : compare_digest sur des str non-ASCII lève TypeError.
    if provided and secrets.compare_digest(provided.encode("utf-8"), code.encode("utf-8")):
        return
    if _has_valid_acheteur_token(request):
        return
    raise HTTPException(401, "Accès restreint : connectez-vous à votre espace collectivité "
                             "ou utilisez le lien de démonstration avec son code.")


def _tenant(request: Request) -> str:
    """Tenant LLM scopé : par COMPTE acheteur si un token valide est présent (isolation
    coût/résilience par compte), sinon par IP. L'isolation 'voisin bruyant' de llm.py
    (disjoncteur + plafond PAR tenant) joue ainsi au bon grain."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            p = decode_token(auth[7:].strip())
            if p.get("typ") == "acheteur" and p.get("sub"):
                return f"dce:ach:{p.get('sub')}"
        except Exception:
            pass
    return f"dce:{real_client_ip(request)}"


class ProcedureIn(BaseModel):
    montant_estime: float | None = Field(default=None, ge=0)
    type_marche: str = "services"


class BesoinIn(BaseModel):
    objet: str = Field(min_length=1, max_length=4000)
    type_marche: str = Field(default="services", max_length=20)   # travaux | fournitures | services
    montant_estime: float | None = Field(default=None, ge=0)      # € HT
    duree_mois: int | None = Field(default=None, ge=0)
    lieu: str = Field(default="", max_length=4000)
    dept: str = Field(default="", max_length=3)
    contraintes: str = Field(default="", max_length=4000)
    exigences_env: str = Field(default="", max_length=4000)
    exigences_sociales: str = Field(default="", max_length=4000)
    allotissement: str = Field(default="auto", max_length=20)     # auto | oui | non


class EstimIn(BaseModel):
    objet: str = Field(default="", max_length=300)
    departement: str = Field(default="", max_length=3)


@router.post("/estimer-budget")
@limiter.limit("40/hour")
def estimer_budget_ep(request: Request, payload: EstimIn):
    """Fourchette de prix de référence à partir des marchés comparables (DECP). Déterministe."""
    _check_access(request)
    objet = (payload.objet or "").strip()
    if len(objet) < 3:
        raise HTTPException(422, "Décrivez l'objet du marché pour l'estimer.")
    from app.services.estimation_budget import estimer_budget
    return estimer_budget(objet, departement=payload.departement)


@router.post("/preview-procedure")
@limiter.limit("60/hour")
def preview_procedure(request: Request, payload: ProcedureIn):
    """Procédure recommandée (déterministe, sans IA) — retour instantané dans le
    formulaire dès que l'acheteur saisit montant + type."""
    _check_access(request)
    return procedure_recommandee(payload.montant_estime, payload.type_marche)


class ExportIn(BaseModel):
    dce: dict
    format: str = Field(default="docx", max_length=8)   # docx | pdf | zip


@router.post("/export")
@limiter.limit("60/hour")
def export(request: Request, payload: ExportIn):
    """Exporte un DCE déjà généré en Word (.docx), PDF, ou ZIP des pièces (RC/CCAP/CCTP).
    Ne rappelle pas le LLM : rendu pur du contenu fourni."""
    _check_access(request)
    fmt = (payload.format or "docx").strip().lower()
    if fmt not in FORMATS:
        raise HTTPException(422, "Format non supporté (docx, pdf, zip).")
    dce = payload.dce or {}
    if not isinstance(dce, dict) or not (dce.get("objet") or "").strip():
        raise HTTPException(422, "DCE manquant ou invalide.")
    if len(json.dumps(dce, ensure_ascii=False)) > 300000:
        raise HTTPException(413, "DCE trop volumineux.")
    fn, media = FORMATS[fmt]
    try:
        content, filename = fn(dce)
    except Exception:
        logger.exception("Échec export DCE (%s)", fmt)
        raise HTTPException(500, "Échec de l'export. Réessayez.")
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": content_disposition(filename)})


@router.post("/avis")
@limiter.limit("60/hour")
def avis(request: Request, payload: ExportIn):
    """Avis de publicité (AAPC) + méthode de notation, assemblés depuis le DCE (déterministe)."""
    _check_access(request)
    dce = payload.dce or {}
    if not isinstance(dce, dict) or not (dce.get("objet") or "").strip():
        raise HTTPException(422, "DCE manquant ou invalide.")
    if len(json.dumps(dce, ensure_ascii=False)) > 300000:
        raise HTTPException(413, "DCE trop volumineux.")
    from app.services.dce_avis import build_avis, build_methode_notation
    return {"avis": build_avis(dce), "methode": build_methode_notation(dce)}


class LotIn(BaseModel):
    numero: int | None = Field(default=None, ge=0)
    intitule: str = Field(min_length=1, max_length=200)


class SourcingIn(BaseModel):
    lots: list[LotIn]
    departement: str = ""


@router.post("/sourcing")
@limiter.limit("20/hour")
def sourcing(request: Request, payload: SourcingIn):
    """Pour chaque lot : vivier de PME capables (open data), indice d'infructuosité,
    groupements possibles et conseils. Ne touche aucune donnée de tenant PME."""
    _check_access(request)
    lots = [l.model_dump() for l in payload.lots if (l.intitule or "").strip()][:12]
    if not lots:
        raise HTTPException(422, "Aucun lot à analyser.")
    dep = (payload.departement or "").strip()[:3]
    try:
        return sourcer_lots(lots, departement=dep, tenant=_tenant(request))
    except Exception:
        logger.exception("Échec sourcing acheteur")
        raise HTTPException(500, "Échec de l'analyse de sourcing. Réessayez.")


@router.post("/generate")
@limiter.limit("15/hour")
def generate(request: Request, besoin: BesoinIn):
    """Génère un PROJET de DCE structuré à partir du besoin saisi par l'acheteur."""
    _check_access(request)
    data = besoin.model_dump()
    if len((data.get("objet") or "").strip()) < 8:
        raise HTTPException(422, "Décrivez l'objet du marché (au moins quelques mots).")
    for k in ("objet", "lieu", "contraintes", "exigences_env", "exigences_sociales"):
        if isinstance(data.get(k), str) and len(data[k]) > 4000:
            data[k] = data[k][:4000]
    try:
        # La génération splitte en threads qui RE-POSENT tenant_scope → on passe le tenant.
        return generer_dce(data, tenant=_tenant(request))
    except LLMUnavailable:
        raise HTTPException(503, "Service IA momentanément indisponible. Réessayez dans un instant.",
                            headers={"Retry-After": "30"})
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        logger.exception("Échec génération DCE")
        raise HTTPException(500, "Échec de la génération. Réessayez.")
