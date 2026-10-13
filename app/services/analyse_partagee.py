"""
Analyse PARTAGÉE d'un dossier de consultation : moins de coût d'IA, sans rien changer à la qualité.

Règle d'Eliot : « économiser le coût de l'IA sans JAMAIS baisser la performance ». Seules les
économies sans risque de qualité PAR CONSTRUCTION sont faites ici (docs/ANALYSE_PARTAGEE.md).

1. MESURE (toujours, même ANALYSE_PARTAGEE=0) : à chaque analyse d'un dossier (ou d'un avis), une ligne
   `analyse_empreintes` : l'organisation, l'empreinte NORMALISÉE du contenu (empreinte de chaque pièce,
   triées : jamais le contenu) et la clé exacte de l'extraction. Agrégats dans /metrics et sur
   GET /api/admin/analyse-partagee (administrateur de la plateforme) ; jamais montrés à un client.

2. ANALYSE EN DEUX TEMPS (ANALYSE_PARTAGEE=1, défaut ; app.services.analysis) : (a) l'EXTRACTION du
   dossier, qui ne reçoit AUCUNE donnée d'entreprise, puis (b) la partie propre à l'entreprise (score
   et verdict sans IA, puis un appel court qui reçoit l'extraction et le profil, jamais le dossier
   entier). L'extraction (a) est gardée dans `analyses_partagees` et resservie, sans nouvel appel, quand
   le MÊME dossier est analysé à nouveau, par la même organisation ou par une autre. La clé est
   l'empreinte de TOUT ce dont l'extraction dépend : la version et le texte des consignes, la route de
   l'IA (modèles, secours, réglages, fournisseurs disponibles), la version de la lecture intégrale et de
   la lecture des pièces, la langue, le mode de lecture, le budget de contexte et les réglages de la
   lecture en deux temps, le texte assemblé du dossier, et le nom, le type, l'état et le texte de CHAQUE
   pièce. Même entrée exacte → même extraction : la resservir équivaut à la refaire. Un rectificatif
   (contenu différent), un autre modèle, d'autres consignes donnent une autre clé (invalidation
   automatique). « Ré-analyser » force une nouvelle extraction (qui remplace l'entrée).
   Une extraction n'est gardée que COMPLÈTE et faite par le modèle prévu : réponse lisible, aucune
   bascule de secours pendant l'extraction (hors fournisseur non configuré, déjà dans la clé), et, en
   lecture en deux temps, aucune partie en panne, illisible ou coupée (un incident passager n'est jamais
   resservi).

3. CONFIDENTIALITÉ : l'entrée partagée ne contient que la réponse de l'IA sur le dossier (document
   public de l'acheteur) et ce qui a été lu ; aucune colonne d'organisation. Rien dans l'API ni à
   l'écran ne dit qu'une extraction vient du partage (même réponse, mêmes champs, même déroulé : tâche
   de fond ou non selon le dossier seul, coût estimé de l'essai calculé comme pour une extraction
   neuve, compteurs de la lecture recalculés pour CE marché). Délai : la première fois qu'une
   organisation reçoit une extraction faite pour une AUTRE, la réponse attend la durée qu'avait prise
   l'extraction (progression rejouée), pour que la rapidité ne trahisse rien ; ensuite (même
   organisation), réponse immédiate. ANALYSE_PARTAGEE_MASQUE=0 : réponse toujours immédiate. Ses choix
   (critères confirmés, poids saisis, questions) restent dans son marché : ils ne sont jamais dans
   l'entrée partagée.

4. COÛT : le quota du client est débité comme d'habitude. L'extraction est comptée à la plateforme
   (budget_ia.mutualise), sauf l'extraction NEUVE déclenchée par un compte en essai gratuit, comptée à
   son essai comme aujourd'hui (sinon le garde-fou de l'essai ne verrait plus l'essentiel du coût) ;
   servie depuis le partage, elle ne coûte rien à personne. La partie propre à l'entreprise est comptée
   au client (et à son essai).

Données : l'entrée partagée n'est pas une donnée personnelle d'un client (document public de
l'acheteur) ; elle est effacée quand elle n'a plus servi depuis ANALYSE_PARTAGEE_JOURS jours (purge
quotidienne). Les lignes de mesure sont effacées avec le compte et au-delà
d'ANALYSE_PARTAGEE_MESURE_JOURS jours. Le texte intégral de chaque marché reste rangé avec le marché et
supprimé avec lui (dce_texte).
"""
import contextlib
import contextvars
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


_NON = ("0", "false", "non", "no", "off")


def actif() -> bool:
    """Analyse en deux temps avec extraction partagée (défaut). ANALYSE_PARTAGEE=0 : analyse d'origine
    en un seul appel (la mesure des doublons continue)."""
    return _env("ANALYSE_PARTAGEE", "1") not in _NON


def masque_actif() -> bool:
    return _env("ANALYSE_PARTAGEE_MASQUE", "1") not in _NON


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


def partage_de(user, db, forcer: bool = False) -> dict:
    """partage(...) d'un utilisateur : son organisation et l'état d'essai de son compte de facturation."""
    from app.core.org import data_owner_id
    from app.core.quota import _billing_user
    from app.services.budget_ia import essai_actif
    try:
        essai = essai_actif(_billing_user(user, db))
    except Exception:       # noqa: BLE001 — prudent : compté à l'essai s'il y en a un
        essai = True
    return partage(data_owner_id(user, db), essai=essai, forcer=forcer)


def portee_extraction(p: dict):
    """Portée de coût de l'EXTRACTION : plateforme (mutualisée), sauf compte en essai."""
    from app.services import budget_ia
    if p and not p.get("essai"):
        return budget_ia.mutualise("extraction partagée d'un dossier")
    return contextlib.nullcontext()


# ── Aléas pendant l'extraction (bascule de secours) : l'extraction n'est alors pas gardée ──────

_ALEAS = contextvars.ContextVar("adjugo_analyse_partagee_aleas", default=None)


def noter_reponse(resp) -> None:
    """Appelée après chaque réponse de l'IA pendant une analyse (analysis._appel_analyse,
    analyse_dossier._appel). Une bascule de secours autre que « fournisseur non configuré » (déjà dans
    la clé) veut dire qu'un autre modèle que celui de la clé a répondu : l'extraction n'est pas gardée."""
    lst = _ALEAS.get()
    if lst is None:
        return
    motif = getattr(resp, "bascule", None)
    if motif and motif != "absent":
        lst.append(str(motif))


@contextlib.contextmanager
def _collecter_aleas():
    lst = []
    tok = _ALEAS.set(lst)       # les fils (map_in_context) copient le contexte : même liste
    try:
        yield lst
    finally:
        _ALEAS.reset(tok)


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
    return "|".join([str(r.tache), str(r.origine)]
                    + [f"{c.fournisseur}:{c.modele}:{int(bool(llm._disponible(c.fournisseur)))}" for c in cibles]
                    + [",".join(sorted(r.secours_sur or ())), repr(r.anthropic), repr(r.mistral),
                       llm.routage_mode(), llm.forcage() or "-"])


def descripteur_modele(nature: str) -> str:
    from app.services import analysis as an
    taches = [an.ANALYSE_TACHE] + (["lecture_pieces"] if nature == NATURE_DOSSIER else [])
    return " ; ".join(_route(t) for t in taches)


def version() -> str:
    from app.services import analysis as an
    from app.services import analyse_dossier as ad
    from app.services import dce_lecture as lec
    return f"c{an.VERSION_CONSIGNES}-l{lec.VERSION}-p{ad.VERSION_LECTURE}"


def _consignes(nature: str) -> str:
    from app.services import analysis as an
    from app.services import analyse_dossier as ad
    return _h(an.SYSTEM_EXTRACTION, an.ANALYSE_MAX_TOKENS, an.ANALYSE_MODEL,
              *((ad.PIECE_SYSTEM, ad.PIECES_MAX_TOKENS) if nature == NATURE_DOSSIER else ()))


def cle_dossier(lecture: dict, texte: str, note: str, lang_name, plan_info: dict) -> str:
    """Clé EXACTE de l'extraction d'un dossier lu en entier : tout ce dont elle dépend (voir l'en-tête)."""
    from app.services import analyse_dossier as ad
    h = hashlib.sha256()

    def up(*xs):
        for x in xs:
            h.update(str(x).encode("utf-8", "surrogatepass"))
            h.update(b"\x1f")

    up("cle-dossier", version(), _consignes(NATURE_DOSSIER), descripteur_modele(NATURE_DOSSIER),
       str(lang_name or "").strip().lower(), (plan_info or {}).get("mode"),
       (plan_info or {}).get("budget_caracteres"), ad.parametres_lecture(), note or "",
       hashlib.sha256((texte or "").encode("utf-8", "surrogatepass")).hexdigest())
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
        out = {"extraction": json.loads(json.dumps(row.extraction)),
               "rapport": json.loads(json.dumps(row.rapport)) if row.rapport is not None else None,
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
    vals = {"nature": nature, "mode": mode or "", "version": version()[:40],
            "modele": descripteur_modele(nature)[:200],
            "extraction": json.loads(json.dumps(extraction)),
            "rapport": json.loads(json.dumps(rapport)) if rapport is not None else None,
            "duree_s": round(float(duree_s or 0.0), 3), "cout_eur": round(float(cout_eur or 0.0), 6),
            "utilise_le": _maintenant()}
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


def noter(p, nature: str, empreinte: str, cle, servi: bool, economie_eur: float = 0.0) -> None:
    """Ligne de mesure après une analyse réussie (jamais bloquant)."""
    owner_id = (p or {}).get("owner_id")
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
    """Attend `duree_s` (bornée) en rejouant la progression (une étape par appel de lecture)."""
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


class Rangement:
    """Extraction NEUVE d'une analyse : portée de coût de l'extraction (plateforme, ou essai du compte ;
    sans partage : le client) et rangement de l'extraction dans le partage dès qu'elle est prête —
    seulement si elle est complète et faite par le modèle prévu (aucune bascule de secours)."""

    def __init__(self, p, nature: str, cle: str, mode: str, aleas: list, cm, t0: float):
        self.p, self.nature, self.cle, self.mode = p, nature, cle, mode
        self.aleas, self.cm, self.t0 = aleas, cm, t0
        self.rangee = False

    def portee(self):
        return portee_extraction(self.p) if self.p is not None else contextlib.nullcontext()

    def apres(self, rapport=None):
        """Rappel `apres_extraction` d'analysis.analyze_dce_text (appelé avant la partie propre à
        l'entreprise : le coût et la durée relevés à cet instant sont ceux de l'extraction seule)."""
        def ranger(extraction, *_ignores):
            if self.p is None or not isinstance(extraction, dict):
                return
            if self.aleas:
                logger.info("analyse partagée : extraction non gardée (bascule de secours : %s)",
                            ", ".join(sorted(set(self.aleas))))
                return
            if not _complete(rapport):
                return
            self.rangee = ecrire(self.cle, self.nature, self.mode, extraction, rapport=rapport,
                                 duree_s=time.monotonic() - self.t0, cout_eur=self.cm.cost_eur())
        return ranger


def executer(p, nature: str, cle: str, mode: str, analyser_fn, progress=None, etapes=None, ajuster=None,
             lecture_permise: bool = True):
    """Analyse avec l'extraction partagée. analyser_fn(extraction, rapport, rangement) → (analyse, rapport) :
    - extraction resservie (dict) : ne fait que la partie propre à l'entreprise (rangement None) ;
    - sinon (extraction None) : fait l'extraction dans `rangement.portee()` et passe `rangement.apres(rapport)`
      à analyze_dce_text (apres_extraction).
    p = partage(...) ou None (aucun partage : extraction faite et comptée au client, rien de gardé).
    ajuster(rapport) : rapport resservi recalculé pour CE marché. Renvoie (analyse, rapport, servie,
    coût de l'extraction resservie). Propage une panne de l'IA."""
    from app.services import llm
    partage_ok = p is not None and actif() and bool(cle)
    if partage_ok and lecture_permise and not p.get("forcer"):
        servi = lire(cle)
        if servi is not None:
            rapport = servi.get("rapport")
            if ajuster is not None and isinstance(rapport, dict):
                rapport = ajuster(rapport)
            if masque_actif() and not deja_vue(p.get("owner_id"), cle):
                attendre(servi.get("duree_s") or 0.0, progress=progress, etapes=etapes)
            analysis, rapport = analyser_fn(servi["extraction"], rapport, None)
            return analysis, rapport, True, float(servi.get("cout_eur") or 0.0)
    with _collecter_aleas() as aleas, \
            llm.cost_meter("extraction du dossier", llm._CURRENT_TENANT.get(), log=False) as cm:
        rg = Rangement(p if partage_ok else None, nature, cle, mode, aleas, cm, time.monotonic())
        analysis, rapport = analyser_fn(None, None, rg)
    return analysis, rapport, False, 0.0


def analyser_texte(text: str, company=None, criteria=None, lang_name=None, p: dict = None,
                   annonce_seule: bool = False) -> dict:
    """Analyse d'un avis (ou d'un dossier récupéré auprès de la source, route /analyze) avec
    l'extraction partagée et la mesure. Même résultat qu'analysis.analyze_dce_text."""
    from app.services import analysis as an
    if p is None or not text or len(text) < 50:
        return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, annonce_seule=annonce_seule)
    cle = cle_texte(an.build_extraction_prompt(text, lang_name)) if actif() else ""

    def fn(extraction, _rapport, rg):
        if extraction is not None:
            return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, annonce_seule=annonce_seule,
                                       extraction=extraction), None
        return an.analyze_dce_text(text, company, criteria, lang_name=lang_name, annonce_seule=annonce_seule,
                                   portee_extraction=rg.portee(), apres_extraction=rg.apres()), None

    analysis, _r, servie, cout = executer(p, NATURE_AVIS, cle, NATURE_AVIS, fn)
    noter(p, NATURE_AVIS, empreinte_texte(text), cle or None, servie, cout)
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


def prometheus_lignes(fmt) -> list:
    """Lignes /metrics (agrégats seulement)."""
    db = _session()
    try:
        m = mesure(db)
    finally:
        db.close()
    out = ["# HELP adjugo_analyse_partagee_analyses Analyses mesurées (une par import), par nature.",
           "# TYPE adjugo_analyse_partagee_analyses gauge"]
    for nature, v in m["par_nature"].items():
        out.append(fmt("adjugo_analyse_partagee_analyses", v["analyses"], {"nature": nature}))
    out += ["# HELP adjugo_analyse_partagee_contenus_distincts Contenus distincts analysés, par nature.",
            "# TYPE adjugo_analyse_partagee_contenus_distincts gauge"]
    for nature, v in m["par_nature"].items():
        out.append(fmt("adjugo_analyse_partagee_contenus_distincts", v["contenus_distincts"], {"nature": nature}))
    out += ["# HELP adjugo_analyse_partagee_doublons_entre_organisations Analyses d'un contenu déjà analysé par "
            "une autre organisation (empreinte normalisée ; « exacte » : clé exacte de l'extraction).",
            "# TYPE adjugo_analyse_partagee_doublons_entre_organisations gauge"]
    for nature, v in m["par_nature"].items():
        out.append(fmt("adjugo_analyse_partagee_doublons_entre_organisations", v["doublons_entre_organisations"],
                       {"nature": nature, "mesure": "contenu"}))
        out.append(fmt("adjugo_analyse_partagee_doublons_entre_organisations",
                       v["doublons_entre_organisations_cle_exacte"], {"nature": nature, "mesure": "exacte"}))
    out += ["# HELP adjugo_analyse_partagee_servies Extractions resservies depuis le partage, par nature.",
            "# TYPE adjugo_analyse_partagee_servies gauge"]
    for nature, v in m["par_nature"].items():
        out.append(fmt("adjugo_analyse_partagee_servies", v["servies_depuis_le_partage"], {"nature": nature}))
    out += ["# HELP adjugo_analyse_partagee_economie_eur Coût d'IA des extractions resservies (tarif public).",
            "# TYPE adjugo_analyse_partagee_economie_eur gauge"]
    for nature, v in m["par_nature"].items():
        out.append(fmt("adjugo_analyse_partagee_economie_eur", v["economie_eur"], {"nature": nature}))
    out += ["# HELP adjugo_analyse_partagee_entrees Extractions gardées dans le partage.",
            "# TYPE adjugo_analyse_partagee_entrees gauge",
            fmt("adjugo_analyse_partagee_entrees", m["entrees_partagees"])]
    return out


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
