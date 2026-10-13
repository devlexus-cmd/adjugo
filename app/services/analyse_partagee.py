"""
Analyse PARTAGÉE d'un dossier de consultation : moins de coût d'IA, sans rien changer à la qualité.

Règle d'Eliot : « économiser le coût de l'IA sans JAMAIS baisser la performance ». Seules les
économies sans risque de qualité PAR CONSTRUCTION sont faites ici (docs/ANALYSE_PARTAGEE.md).

1. MESURE (toujours, même ANALYSE_PARTAGEE=0) : à chaque analyse d'un dossier (ou d'un avis), une ligne
   `analyse_empreintes` : l'organisation, l'empreinte NORMALISÉE du contenu (empreinte de chaque pièce,
   triées : jamais le contenu) et la clé exacte de l'extraction. Agrégats dans /metrics et sur
   GET /api/admin/analyse-partagee (administrateur de la plateforme) ; jamais montrés à un client.

2. EXTRACTION PARTAGÉE (ANALYSE_PARTAGEE=1, défaut) : l'analyse est faite en deux temps
   (app.services.analysis) — (a) l'extraction du dossier, qui ne reçoit AUCUNE donnée d'entreprise,
   puis (b) la partie propre à l'entreprise (score et verdict sans IA, puis un appel court qui reçoit
   l'extraction et le profil, jamais le dossier entier). L'extraction (a) est gardée dans
   `analyses_partagees` et resservie, sans nouvel appel, quand le MÊME dossier est analysé à nouveau,
   par la même organisation ou par une autre. La clé est l'empreinte de TOUT ce dont l'extraction dépend :
   la version et le texte des consignes, la route de l'IA (modèles, secours, réglages, fournisseurs
   disponibles), la version de la lecture intégrale et de la lecture des pièces, la langue, le mode de
   lecture, le budget de contexte, et le texte, le nom, le type et l'état de CHAQUE pièce, dans l'ordre.
   Même entrée exacte → même sortie : resservir l'extraction équivaut à la refaire. Un rectificatif
   (contenu différent), un autre modèle, d'autres consignes donnent une autre clé (invalidation
   automatique). « Ré-analyser » force une nouvelle extraction (qui remplace l'entrée).
   Une extraction n'est gardée que COMPLÈTE : réponse lisible, et, en lecture en deux temps, aucune
   partie en panne, illisible ou coupée (un incident passager n'est jamais resservi).

3. CONFIDENTIALITÉ : l'entrée partagée ne contient que la réponse de l'IA sur le dossier (document
   public de l'acheteur) et ce qui a été lu ; aucune colonne d'organisation. Rien dans l'API ni à
   l'écran ne dit qu'une extraction vient du partage (même réponse, mêmes champs, même déroulé : tâche
   de fond ou non selon le dossier seul, coût estimé de l'essai calculé comme pour une extraction
   neuve). Délai : la première fois qu'une organisation reçoit une extraction faite pour une AUTRE,
   la réponse attend la durée qu'avait prise l'extraction (progression rejouée), pour que la rapidité
   ne trahisse rien (ANALYSE_PARTAGEE_MASQUE=0 : réponse immédiate). Ses choix (critères confirmés,
   poids saisis, questions) restent dans son marché : ils ne sont jamais dans l'entrée partagée.

4. COÛT : le quota du client est débité comme d'habitude. L'extraction est comptée à la plateforme
   (budget_ia.mutualise), sauf l'extraction NEUVE déclenchée par un compte en essai gratuit, comptée à
   son essai comme aujourd'hui (sinon le garde-fou de l'essai ne verrait plus l'essentiel du coût) ;
   servie depuis le cache, elle ne coûte rien à personne. La partie propre à l'entreprise est comptée
   au client.

Données : l'entrée partagée n'est pas une donnée personnelle (document public de l'acheteur) ; elle
est effacée quand elle n'a plus servi depuis ANALYSE_PARTAGEE_JOURS jours (purge quotidienne). Les
lignes de mesure sont effacées avec le compte et au-delà d'ANALYSE_PARTAGEE_MESURE_JOURS jours. Le
texte intégral de chaque marché reste rangé avec le marché et supprimé avec lui (dce_texte).
"""
import contextlib
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("adjugo")

NATURE_DOSSIER = "dossier"
NATURE_AVIS = "avis"


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().lower()


def _env_float(name: str, default: float) -> float:
    try:
        v = float(str(os.getenv(name, "")).strip() or default)
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


def actif() -> bool:
    """Analyse en deux temps avec extraction partagée (défaut). ANALYSE_PARTAGEE=0 : analyse d'origine
    en un seul appel (la mesure des doublons continue)."""
    return _env("ANALYSE_PARTAGEE", "1") not in ("0", "false", "non", "no", "off")


def masque_actif() -> bool:
    return _env("ANALYSE_PARTAGEE_MASQUE", "1") not in ("0", "false", "non", "no", "off")


def masque_max_s() -> float:
    return _env_float("ANALYSE_PARTAGEE_MASQUE_MAX_S", 600.0)


def jours_cache() -> int:
    return int(_env_float("ANALYSE_PARTAGEE_JOURS", 120))


def jours_mesure() -> int:
    return int(_env_float("ANALYSE_PARTAGEE_MESURE_JOURS", 365))


def _maintenant():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Partage : qui analyse (jamais rangé dans l'entrée partagée) ─────────────────────────────────

def partage(owner_id, essai: bool = False, forcer: bool = False) -> dict:
    """Contexte d'une analyse : organisation (data_owner_id), compte en essai gratuit (l'extraction neuve
    est alors comptée à son essai), « Ré-analyser » (forcer : nouvelle extraction)."""
    return {"owner_id": int(owner_id) if owner_id is not None else None, "essai": bool(essai),
            "forcer": bool(forcer)}


def portee_extraction(p: dict):
    """Portée de coût de l'EXTRACTION : plateforme (mutualisée), sauf compte en essai."""
    from app.services import budget_ia
    if p and not p.get("essai"):
        return budget_ia.mutualise("extraction partagée d'un dossier")
    return contextlib.nullcontext()


# ── Empreintes ─────────────────────────────────────────────────────────────────────────────────

_ESPACES = re.compile(r"\s+")


def _norm_mesure(texte: str) -> str:
    """Forme normalisée pour la MESURE des doublons : Unicode NFKC, casse repliée, blancs réduits (une
    même pièce relue avec d'autres sauts de ligne compte pour la même)."""
    t = unicodedata.normalize("NFKC", texte or "").casefold()
    return _ESPACES.sub(" ", t).strip()


def _h(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", "surrogatepass"))
        h.update(b"\x1f")
    return h.hexdigest()


def empreinte_dossier(lecture: dict) -> str:
    """Empreinte du CONTENU d'un dossier (mesure) : empreinte normalisée de chaque pièce lue, triées
    (l'ordre et le nom des fichiers n'y entrent pas). Jamais le contenu."""
    pieces = sorted(_h(_norm_mesure(p.get("texte") or "")) for p in (lecture or {}).get("pieces") or []
                    if (p.get("texte") or "").strip())
    return _h("dossier", *pieces)


def empreinte_texte(texte: str) -> str:
    """Empreinte du contenu d'un avis (mesure)."""
    return _h("avis", _norm_mesure(texte))


def _route(tache: str) -> str:
    """Route EFFECTIVE de la tâche : modèles, secours, réglages et fournisseurs disponibles (un
    fournisseur activé ou retiré change le modèle qui répond, donc la clé)."""
    from app.services import llm
    r = llm.route(tache)
    cibles = [c for c in (r.primaire, r.secours) if c is not None]
    return "|".join([r.tache, r.origine] + [f"{c.fournisseur}:{c.modele}:{int(bool(llm._disponible(c.fournisseur)))}"
                                            for c in cibles]
                    + [",".join(sorted(r.secours_sur)), repr(r.anthropic), repr(r.mistral)])


def descripteur_modele(nature: str) -> str:
    from app.services import analysis as an
    taches = [an.ANALYSE_TACHE] + (["lecture_pieces"] if nature == NATURE_DOSSIER else [])
    return " ; ".join(_route(t) for t in taches)[:2000]


def version() -> str:
    from app.services import analysis as an
    from app.services import analyse_dossier as ad
    from app.services import dce_lecture as lec
    return f"c{an.VERSION_CONSIGNES}-l{lec.VERSION}-p{ad.VERSION_LECTURE}"


def _consignes(nature: str) -> str:
    from app.services import analysis as an
    from app.services import analyse_dossier as ad
    return _h(an.SYSTEM_EXTRACTION, an.ANALYSE_MAX_TOKENS,
              *((ad.PIECE_SYSTEM,) if nature == NATURE_DOSSIER else ()))


def cle_dossier(lecture: dict, lang_name, note: str, plan_info: dict) -> str:
    """Clé EXACTE de l'extraction d'un dossier lu en entier : tout ce dont elle dépend."""
    from app.services import analyse_dossier as ad
    h = hashlib.sha256()

    def up(*xs):
        for x in xs:
            h.update(str(x).encode("utf-8", "surrogatepass"))
            h.update(b"\x1f")

    up("cle-dossier", version(), _consignes(NATURE_DOSSIER), descripteur_modele(NATURE_DOSSIER),
       str(lang_name or "").strip().lower(), plan_info.get("mode"), plan_info.get("budget_caracteres"),
       ad.parametres_lecture(), note or "")
    for p in (lecture or {}).get("pieces") or []:
        up("piece", p.get("nom"), p.get("type"), p.get("libelle"), p.get("statut"), p.get("raison"),
           p.get("detail"), json.dumps(p.get("page_starts") or [], separators=(",", ":")),
           len(p.get("texte") or ""))
        h.update((p.get("texte") or "").encode("utf-8", "surrogatepass"))
        h.update(b"\x1e")
    return h.hexdigest()


def cle_texte(user_prompt: str) -> str:
    """Clé EXACTE de l'extraction d'un avis : le prompt envoyé à l'IA (sans aucune donnée d'entreprise),
    les consignes et la route."""
    return _h("cle-avis", version(), _consignes(NATURE_AVIS), descripteur_modele(NATURE_AVIS), user_prompt)


# ── Base : entrée partagée et lignes de mesure (sessions courtes, jamais bloquantes) ───────────

def _session():
    from app.core.database import SessionLocal
    return SessionLocal()


def lire(cle: str):
    """Entrée partagée de cette clé ({extraction, rapport, duree_s, cout_eur, mode}) ou None. Une
    erreur de lecture vaut « pas d'entrée » (l'analyse se fait alors comme d'habitude)."""
    if not cle:
        return None
    from app.models import AnalysePartagee
    db = _session()
    try:
        row = db.query(AnalysePartagee).filter(AnalysePartagee.cle == cle).first()
        if row is None or not isinstance(row.extraction, dict):
            return None
        out = {"extraction": json.loads(json.dumps(row.extraction)), "rapport": row.rapport,
               "duree_s": float(row.duree_s or 0.0), "cout_eur": float(row.cout_eur or 0.0), "mode": row.mode}
        row.utilise_le = _maintenant()
        db.commit()
        return out
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("analyse partagée : lecture impossible (%s) — extraction refaite", type(e).__name__)
        return None
    finally:
        db.close()


def ecrire(cle: str, nature: str, mode: str, extraction: dict, rapport=None, duree_s: float = 0.0,
           cout_eur: float = 0.0) -> bool:
    """Range (ou remplace) l'entrée partagée. Jamais bloquant : un échec laisse l'analyse intacte."""
    if not cle or not isinstance(extraction, dict):
        return False
    from sqlalchemy.exc import IntegrityError
    from app.models import AnalysePartagee
    vals = {"nature": nature, "mode": mode or "", "version": version(), "modele": descripteur_modele(nature)[:200],
            "extraction": extraction, "rapport": rapport, "duree_s": round(float(duree_s or 0.0), 3),
            "cout_eur": round(float(cout_eur or 0.0), 6), "utilise_le": _maintenant()}
    db = _session()
    try:
        for _essai in range(2):
            row = db.query(AnalysePartagee).filter(AnalysePartagee.cle == cle).first()
            try:
                if row is None:
                    db.add(AnalysePartagee(cle=cle, created_at=_maintenant(), **vals))
                else:
                    for k, v in vals.items():
                        setattr(row, k, v)
                db.commit()
                return True
            except IntegrityError:
                db.rollback()           # écrite au même instant par une autre analyse : on la remplace
        return False
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("analyse partagée : extraction non rangée (%s)", type(e).__name__)
        return False
    finally:
        db.close()


def deja_vue(owner_id, cle: str) -> bool:
    """Cette organisation a-t-elle déjà reçu une analyse de cette clé ?"""
    if owner_id is None or not cle:
        return False
    from app.models import AnalyseEmpreinte
    db = _session()
    try:
        return db.query(AnalyseEmpreinte.id).filter(AnalyseEmpreinte.owner_id == owner_id,
                                                    AnalyseEmpreinte.cle == cle).first() is not None
    except Exception:       # noqa: BLE001
        return False
    finally:
        db.close()


def noter(owner_id, nature: str, empreinte: str, cle: str, servi: bool, economie_eur: float = 0.0) -> None:
    """Ligne de mesure (jamais bloquant)."""
    if owner_id is None or not empreinte:
        return
    from app.models import AnalyseEmpreinte
    db = _session()
    try:
        db.add(AnalyseEmpreinte(owner_id=int(owner_id), nature=nature, empreinte=empreinte, cle=cle or None,
                                servi_du_cache=bool(servi), economie_eur=round(float(economie_eur or 0.0), 6),
                                created_at=_maintenant()))
        db.commit()
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("analyse partagée : mesure non rangée (%s)", type(e).__name__)
    finally:
        db.close()


# ── Délai : la rapidité d'une extraction resservie ne trahit rien ─────────────────────────────

def attendre(duree_s: float, progress=None, etapes=None) -> None:
    """Attend `duree_s` (bornée) en rejouant la progression (une étape par partie lue)."""
    d = max(0.0, min(float(duree_s or 0.0), masque_max_s()))
    etapes = list(etapes or [])
    if not etapes:
        if d:
            time.sleep(d)
        return
    pas = d / len(etapes)
    for i, nom in enumerate(etapes, 1):
        if pas:
            time.sleep(pas)
        if progress is not None:
            try:
                progress({"etape": "analyse", "parties_lues": i, "parties_total": len(etapes),
                          "piece_en_cours": str(nom or "")[:120]})
            except Exception:       # noqa: BLE001
                pass


# ── Orchestration commune (dossier lu en entier, avis) ─────────────────────────────────────────

def _complete(rapport) -> bool:
    """Lecture en deux temps sans incident passager (panne, réponse illisible ou coupée)."""
    if not isinstance(rapport, dict):
        return True
    return not (rapport.get("erreurs") or rapport.get("illisibles") or rapport.get("coupees"))


def executer(p: dict, nature: str, cle: str, empreinte: str, mode: str, analyser_fn, progress=None,
             etapes=None):
    """Analyse avec l'extraction partagée.
    analyser_fn(extraction_servie, on_extraction, mutualiser) → (analyse, rapport) : avec une extraction
    servie, ne fait que la partie propre à l'entreprise ; sinon fait l'extraction et appelle
    on_extraction(extraction, cout_eur, duree_s, rapport) dès qu'elle est prête (avant la partie propre
    à l'entreprise : une panne de celle-ci n'oblige pas à refaire l'extraction).
    p = partage(...) ou None (aucun partage ni mesure). Renvoie (analyse, rapport)."""
    owner = (p or {}).get("owner_id")
    partage_ok = p is not None and actif()
    servi = None
    if partage_ok and not p.get("forcer"):
        servi = lire(cle)
    if servi is not None:
        if masque_actif() and not deja_vue(owner, cle):
            attendre(servi.get("duree_s") or 0.0, progress=progress, etapes=etapes)
        analysis, rapport = analyser_fn(servi["extraction"], None, False, servi.get("rapport"))
        noter(owner, nature, empreinte, cle, True, servi.get("cout_eur") or 0.0)
        return analysis, rapport

    def on_extraction(extraction, cout_eur=0.0, duree_s=0.0, rapport=None):
        if partage_ok and isinstance(extraction, dict) and _complete(rapport):
            ecrire(cle, nature, mode, extraction, rapport=rapport, duree_s=duree_s, cout_eur=cout_eur)

    analysis, rapport = analyser_fn(None, on_extraction, bool(partage_ok and not p.get("essai")), None)
    if p is not None:
        noter(owner, nature, empreinte, cle, False, 0.0)
    return analysis, rapport


def analyser_texte(text: str, company=None, criteria=None, lang_name=None, p: dict = None, **kw) -> dict:
    """Analyse d'un avis (ou d'un dossier déjà extrait, route /analyze) avec l'extraction partagée."""
    from app.services import analysis as an
    if not text or len(text) < 50 or p is None:
        return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, **kw)
    user_prompt = an.build_user_prompt(text, None, None, lang_name, integral=bool(kw.get("integral")),
                                       note_lecture=kw.get("note_lecture") or "")
    cle = cle_texte(user_prompt)

    def fn(extraction, on_extraction, mutualiser, _rapport):
        if extraction is not None:
            return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, extraction=extraction, **kw), None
        cb = (lambda e, c, d: on_extraction(e, c, d, None)) if on_extraction is not None else None
        return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, on_extraction=cb,
                                   mutualiser=mutualiser, **kw), None

    analysis, _ = executer(p, NATURE_AVIS, cle, empreinte_texte(text), NATURE_AVIS, fn)
    return analysis


# ── Mesure (administration, /metrics) ─────────────────────────────────────────────────────────

def mesure(db) -> dict:
    """Doublons entre organisations et économies (agrégats internes, aucune organisation nommée)."""
    from sqlalchemy import func
    from app.models import AnalyseEmpreinte, AnalysePartagee
    par_nature = {}
    for nature in (NATURE_DOSSIER, NATURE_AVIS):
        base = db.query(AnalyseEmpreinte).filter(AnalyseEmpreinte.nature == nature)
        imports = base.count()
        # (empreinte, nombre d'organisations distinctes, nombre d'analyses)
        rows = (db.query(AnalyseEmpreinte.empreinte, func.count(func.distinct(AnalyseEmpreinte.owner_id)),
                         func.count(AnalyseEmpreinte.id))
                .filter(AnalyseEmpreinte.nature == nature).group_by(AnalyseEmpreinte.empreinte).all())
        distincts = len(rows)
        inter = sum(max(0, int(orgs) - 1) for _e, orgs, _n in rows)
        meme = sum(max(0, int(n) - int(orgs)) for _e, orgs, n in rows)
        multi = sum(1 for _e, orgs, _n in rows if int(orgs) > 1)
        cles = (db.query(AnalyseEmpreinte.cle, func.count(func.distinct(AnalyseEmpreinte.owner_id)))
                .filter(AnalyseEmpreinte.nature == nature, AnalyseEmpreinte.cle.isnot(None))
                .group_by(AnalyseEmpreinte.cle).all())
        inter_cle = sum(max(0, int(orgs) - 1) for _c, orgs in cles)
        servies = base.filter(AnalyseEmpreinte.servi_du_cache.is_(True)).count()
        eco = float(db.query(func.coalesce(func.sum(AnalyseEmpreinte.economie_eur), 0.0))
                    .filter(AnalyseEmpreinte.nature == nature).scalar() or 0.0)
        par_nature[nature] = {
            "analyses": imports, "contenus_distincts": distincts,
            "contenus_vus_par_plusieurs_organisations": multi,
            "doublons_entre_organisations": inter, "doublons_meme_organisation": meme,
            "taux_doublons_entre_organisations": round(inter / imports, 4) if imports else 0.0,
            "doublons_entre_organisations_cle_exacte": inter_cle,
            "servies_depuis_le_partage": servies,
            "taux_servies": round(servies / imports, 4) if imports else 0.0,
            "economie_eur": round(eco, 4),
        }
    entrees = db.query(func.count(AnalysePartagee.id)).scalar() or 0
    return {"actif": actif(), "masque_du_delai": masque_actif(), "version": version(),
            "entrees_partagees": int(entrees), "par_nature": par_nature,
            "explication": ("Interne, jamais montré à un client. « doublons entre organisations » : analyses d'un "
                            "contenu déjà analysé par une AUTRE organisation (borne haute des extractions que le "
                            "partage peut éviter) ; « clé exacte » : la même chose, à l'identique de ce que l'IA "
                            "reçoit (ce que le partage peut réellement resservir) ; « économie » : coût des "
                            "extractions resservies, au tarif public du modèle.")}


# ── Purge et effacement ────────────────────────────────────────────────────────────────────────

def purger(db) -> dict:
    """Entrées partagées inutilisées depuis ANALYSE_PARTAGEE_JOURS jours, lignes de mesure de plus
    d'ANALYSE_PARTAGEE_MESURE_JOURS jours. Jamais bloquant pour la purge qui l'appelle."""
    from app.models import AnalyseEmpreinte, AnalysePartagee
    try:
        c1 = _maintenant() - timedelta(days=max(1, jours_cache()))
        c2 = _maintenant() - timedelta(days=max(1, jours_mesure()))
        n1 = db.query(AnalysePartagee).filter(AnalysePartagee.utilise_le < c1).delete(synchronize_session=False)
        n2 = db.query(AnalyseEmpreinte).filter(AnalyseEmpreinte.created_at < c2).delete(synchronize_session=False)
        db.commit()
        return {"analyses_partagees_purgees": int(n1 or 0), "mesures_purgees": int(n2 or 0)}
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("purge de l'analyse partagée en échec : %s", type(e).__name__)
        return {"analyses_partagees_purgees": 0, "mesures_purgees": 0, "erreur_analyse_partagee": True}


def effacer_organisation(db, owner_id: int) -> None:
    """Effacement du compte (RGPD) : ses lignes de mesure. Les entrées partagées n'appartiennent à
    personne (aucune colonne d'organisation) : rien à effacer."""
    from app.models import AnalyseEmpreinte
    db.query(AnalyseEmpreinte).filter(AnalyseEmpreinte.owner_id == owner_id).delete(synchronize_session=False)
