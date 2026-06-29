"""
SOURCING ACHETEUR (côté COLLECTIVITÉ) — Pilier 2.

Pour chaque LOT d'un marché, ce moteur :
  1. TROUVE les PME potentiellement intéressées/capables (réutilise le moteur de sourcing
     d'Adjugo : `CompanySearchService.discover()` → SIRENE + enrichissement BODACC santé +
     DECP marchés gagnés + scoring déterministe `score_company`),
  2. MESURE des signaux (vivier, capacité prouvée, densité locale, santé, groupement),
  3. CALCULE un INDICE D'INFRUCTUOSITÉ déterministe (`infructuosite_scoring`),
  4. propose des GROUPEMENTS quand le vivier solo est mince (graphe de synergie
     `synergy_score` = ADN co-traitance),
  5. génère des CONSEILS actionnables (1 appel LLM, ancré sur les chiffres mesurés).

NEUTRALITÉ / LÉGALITÉ : l'outil aide à SOURCER et à bien allotir ; il ne désigne jamais un
attributaire et ne « pousse » aucune entreprise précise (cf. délit de favoritisme,
art. 432-14 CP). Les PME affichées sont des candidats POTENTIELS publics (open data), à
titre d'information de marché (sourcing R2111-1). Aucune donnée d'un tenant PME Adjugo n'est
utilisée (cloisonnement de la plateforme à deux faces).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.sourcing.sources.sirene import SireneSource
from app.sourcing.sources.bodacc import BodaccSource
from app.sourcing.search import CompanySearchService
from app.sourcing.groupement import infer_trade
from app.sourcing.scoring import synergy_score
from app.services.infructuosite_scoring import score_infructuosite, agreger
from app.services.llm import complete_json, tenant_scope

logger = logging.getLogger("adjugo")

# Une PME est « capable » au-dessus de ce score d'adéquation déterministe (score_company).
SEUIL_CAPABLE = int(os.getenv("DCE_SOURCING_SEUIL", "50"))
# Synergie minimale pour considérer une PME comme partenaire de groupement viable.
SEUIL_SYNERGIE = int(os.getenv("DCE_SYNERGIE_SEUIL", "45"))


def _service() -> CompanySearchService:
    """Même construction que le sourcing PME (SIRENE + red-flags BODACC)."""
    return CompanySearchService([SireneSource()], red_flag_source=BodaccSource())


def _dep2(departement: str) -> str:
    return (str(departement or "").strip()[:2])


_STOP = {"et", "de", "des", "du", "la", "le", "les", "pour", "aux", "avec", "sur"}


def _mots_cles(intitule: str) -> str:
    """Repli quand le métier n'est pas reconnu : 1 à 2 mots significatifs du libellé
    (la recherche SIRENE par phrase entière ne ramène rien)."""
    import re
    mots = [w for w in re.split(r"[^\wÀ-ÿ]+", str(intitule or "").lower())
            if len(w) > 3 and w not in _STOP]
    return " ".join(mots[:2]) if mots else (intitule or "").strip()[:40]


def _serialize(c, cpv_fam: str = "") -> dict:
    """Fiche PME publique, factuelle (provenance open data), pour l'affichage acheteur.

    MINIMISATION RGPD (art. 5.1.c + art. 14) — l'acheteur est un responsable de traitement
    TIERS : on n'expose que les données strictement utiles à l'appréciation de l'offre
    économique. On N'INCLUT VOLONTAIREMENT PAS `c.dirigeant` (donnée nominative non
    nécessaire au sourcing) ni `c.raw`. Ne pas ré-ajouter le dirigeant ici sans revoir la
    politique de confidentialité (/confidentialite) et l'information des personnes."""
    ei = bool(getattr(c, "est_personne_physique", False))
    # Capacité prouvée QUALIFIÉE : « dans le domaine » (famille CPV gagnée) et « récente »
    # (≤ 4 ans), au lieu d'un décompte brut tous marchés confondus (badge plus honnête).
    win_domains = [str(w) for w in (getattr(c, "win_domains", []) or [])]
    capacite_domaine = bool(cpv_fam) and cpv_fam in win_domains
    lw = str(getattr(c, "last_win_date", "") or "")[:4]
    import datetime as _dt
    capacite_recente = lw.isdigit() and int(lw) >= _dt.date.today().year - 4
    return {
        # EI = personne physique : le nom EST une donnée nominative → masqué (minimisation
        # RGPD). L'acheteur peut lever l'identité lui-même via le SIREN au registre public.
        "nom": ("Entreprise individuelle (nom masqué)" if ei else c.nom),
        "personne_physique": ei,
        "siren": c.siren,
        "ville": c.ville,
        "departement": c.departement,
        "naf_label": c.naf_label,
        "categorie": c.categorie,
        "effectif": c.effectif,
        "score": (c.score.total if c.score else None),
        "capacite_prouvee": bool(getattr(c, "past_wins", 0)),
        "past_wins": int(getattr(c, "past_wins", 0) or 0),
        "last_win_date": getattr(c, "last_win_date", None),
        "capacite_domaine": capacite_domaine,
        "capacite_recente": capacite_recente,
        "win_domains": win_domains,
        "est_rge": c.est_rge,
        "procedure_collective": c.procedure_collective,
        "red_flags": list(c.red_flags or []),
        "source_url": (c.provenance.source_url if c.provenance else None),
    }


def sourcer_lot(lot: dict, departement: str = "", cpv: str = "") -> dict:
    """Source un lot : vivier de PME capables + signaux + indice d'infructuosité + groupement.
    N'appelle PAS le LLM (uniquement les sources open data) — sûr à paralléliser.
    `cpv` (optionnel) qualifie la capacité prouvée par famille CPV (2 chiffres)."""
    cpv_fam = (cpv or "").strip()[:2]
    numero = lot.get("numero") if isinstance(lot, dict) else None
    intitule = (lot.get("intitule") if isinstance(lot, dict) else str(lot)) or ""
    intitule = intitule.strip()
    lot_montant = None
    if isinstance(lot, dict):
        try:
            v = lot.get("montant", lot.get("montant_estime"))
            lot_montant = float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            lot_montant = None
    dep = _dep2(departement)
    deps = [dep] if dep else None
    # Recherche PAR MÉTIER (NAF), pas par le libellé complet du lot : passer l'intitulé
    # entier en `query` ramène ~0 résultat (il matche des noms d'entreprise). On déduit le
    # métier (infer_trade → filtre NAF), avec repli sur un mot-clé court si non reconnu.
    trade = infer_trade(intitule)
    metier_reconnu = trade is not None   # sinon repli mots-clés (sans filtre NAF) → vivier à vérifier
    activity = trade or _mots_cles(intitule)

    errors = []
    try:
        res = _service().discover(activity=activity, departement=dep, query="",
                                  limit=12, tender_departements=deps, need_label=intitule,
                                  lot_montant=lot_montant)
        companies = res.get("companies") or []
        errors = [f"{e.source}: {e.message}" for e in (res.get("errors") or [])]
    except Exception as e:
        logger.info("sourcing lot « %s » indisponible : %s", intitule, e)
        companies = []
        errors = [f"Sourcing indisponible : {str(e)[:160]}"]

    capables = [c for c in companies if (c.score.total if c.score else 0) >= SEUIL_CAPABLE]
    nb_capables = len(capables)
    nb_cap_prouvee = sum(1 for c in capables if int(getattr(c, "past_wins", 0) or 0) > 0)
    nb_local = sum(1 for c in capables if dep and c.departement == dep)
    nb_sain = sum(1 for c in capables if not c.procedure_collective)

    # Groupement : utile quand le vivier solo est mince. Graphe de synergie (ADN co-traitance).
    groupement = []
    nb_groupement = 0
    if 2 <= nb_capables <= 6:   # vivier mince à moyen → on explore les groupements possibles
        base = capables[0]
        base_dict = {"code_ape": base.naf, "postal_code": base.code_postal, "qualifications": []}
        for c in capables[1:6]:
            try:
                syn = synergy_score(c, base_dict, tender_departements=deps, need_label=intitule)
            except Exception:
                continue
            if syn.get("total", 0) >= SEUIL_SYNERGIE:
                nb_groupement += 1
                groupement.append({"nom": c.nom, "ville": c.ville,
                                   "synergie": syn.get("total"), "headline": syn.get("headline")})
        if nb_groupement:
            # NEUTRALITÉ : on ne DÉSIGNE personne comme mandataire/chef de file (risque de
            # favoritisme, art. 432-14 CP). On montre une COMBINAISON possible, simple point de
            # départ d'un groupement — l'acheteur reste seul juge, l'égalité de traitement prime.
            groupement.insert(0, {"nom": base.nom, "ville": base.ville,
                                  "synergie": None, "headline": "Point de départ possible d'un groupement"})

    signals = {"nb_capables": nb_capables, "nb_capacite_prouvee": nb_cap_prouvee,
               "nb_local": nb_local, "nb_sain": nb_sain, "nb_groupement": nb_groupement}
    indice = score_infructuosite(intitule, signals)

    # NEUTRALITÉ (art. 432-14 CP) : vivier en ordre ALPHABÉTIQUE, pas par score décroissant —
    # on évite un classement de facto des candidats potentiels.
    vivier = sorted(capables[:8], key=lambda c: (c.nom or "").lower())
    return {
        "numero": numero, "intitule": intitule, "metier": activity,
        "metier_reconnu": metier_reconnu,
        "indice": indice,
        "vivier": [_serialize(c, cpv_fam) for c in vivier],
        "groupement": groupement,
        "errors": errors,
    }


_CONSEILS_SYSTEM = """Tu es un acheteur public senior français. À partir de SIGNAUX MESURÉS
(ne rien inventer, ne cite que les chiffres fournis), tu donnes des CONSEILS concrets et
chiffrés pour RÉDUIRE le risque d'infructuosité d'un marché, dans le respect du droit
(égalité de traitement, AUCUNE préférence locale, pas de favoritisme). Leviers possibles :
ajuster l'allotissement, encourager les groupements (co-traitance), assouplir un critère ou
une exigence de capacité disproportionnée, allonger le délai de remise, faire un sourcing
préalable (R2111-1), élargir/adapter la publicité. Sois actionnable et bref.

Réponds en JSON STRICT : {"conseils": ["conseil 1", "conseil 2", ...]} (3 à 6 conseils)."""


def _generer_conseils(lots_out: list, glob: dict, tenant) -> list:
    """1 appel LLM (tenant-scopé) → conseils ancrés sur les signaux. Non bloquant."""
    compact = [{
        "lot": l["intitule"], "risque": l["indice"]["risque"], "niveau": l["indice"]["niveau"],
        "signaux": l["indice"]["signaux"],
        "groupement_possible": bool(l.get("groupement")),
    } for l in lots_out]
    user = ("Risque global d'infructuosité : "
            f"{glob.get('risque')}% ({glob.get('niveau')}). Détail par lot :\n"
            f"{compact}\n\nDonne 3 à 6 conseils concrets et chiffrés pour réduire ce risque.")
    try:
        with tenant_scope(tenant):
            data = complete_json(_CONSEILS_SYSTEM, user, max_tokens=900, temperature=0.3)
        return [str(c) for c in (data.get("conseils") or []) if str(c).strip()][:6]
    except Exception as e:   # best-effort : les conseils ne doivent jamais casser le sourcing
        logger.info("conseils sourcing non générés : %s", e)
        return []


def sourcer_lots(lots: list, departement: str = "", tenant=None, cpv: str = "") -> dict:
    """Source TOUS les lots (en parallèle), agrège le risque global et génère les conseils.
    `cpv` (optionnel) : la capacité prouvée DECP est alors qualifiée « dans le domaine »
    (famille CPV à 2 chiffres) plutôt que « tous marchés confondus »."""
    lots = [l for l in (lots or []) if isinstance(l, dict) and (l.get("intitule") or "").strip()][:12]
    if not lots:
        return {"lots": [], "global": {"risque": 0, "niveau": "faible", "pire_lot": None},
                "conseils": [], "disclaimer": _DISCLAIMER}

    out = [None] * len(lots)
    with ThreadPoolExecutor(max_workers=min(4, len(lots))) as ex:
        futs = {ex.submit(sourcer_lot, lot, departement, cpv): i for i, lot in enumerate(lots)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                out[i] = fut.result()
            except Exception as e:
                logger.info("lot %s en échec : %s", i, e)
                out[i] = {"numero": lots[i].get("numero"),
                          "intitule": (lots[i].get("intitule") or "").strip(), "metier": "",
                          "indice": score_infructuosite(lots[i].get("intitule", ""), {}),
                          "vivier": [], "groupement": [], "errors": [str(e)[:160]]}
    lots_out = [o for o in out if o]
    glob = agreger([o["indice"] for o in lots_out])
    conseils = _generer_conseils(lots_out, glob, tenant)
    return {"lots": lots_out, "global": glob, "conseils": conseils, "disclaimer": _DISCLAIMER}


_DISCLAIMER = ("PME identifiées via les données publiques (SIRENE, DECP, BODACC) à titre "
               "d'information de marché (sourcing). L'outil n'attribue rien et ne recommande "
               "aucune entreprise nominativement — l'égalité de traitement reste votre responsabilité.")
