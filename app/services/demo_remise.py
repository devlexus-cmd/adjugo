"""
Remise à neuf AUTOMATIQUE de la vitrine de démonstration entre deux présentations.

Le compte démo est PARTAGÉ : ce qu'un visiteur y laisse (marché ajouté depuis la recherche, étape
déplacée, contact, devis…) restait jusqu'au prochain redémarrage du serveur, donc pour les visiteurs
suivants. Plusieurs entreprises présentent Adjugo sur la même démo, parfois l'une après l'autre dans
la journée : chaque nouvelle présentation doit repartir d'une vitrine propre.

Règle : quand une session démo S'OUVRE (POST /api/auth/demo ou /api/acheteur/demo, par le lien
privé ou DEMO_PUBLIC=1), si AUCUNE requête d'une session démo n'a eu lieu depuis
DEMO_REMISE_A_NEUF_MIN minutes (30 par défaut ; 0 = jamais), les deux démos (entreprises et
collectivités) sont rejouées — le seed du démarrage, force=True — AVANT de délivrer la session.
Jamais pendant qu'une autre session démo est active (activité récente). Une erreur du seed ne
bloque jamais l'ouverture : elle est journalisée et la session s'ouvre sur la vitrine existante.

Activité : toute requête authentifiée d'une session démo (PME ou collectivités) et toute requête
sur un lien partenaire de la démo, notées en mémoire (le serveur tourne en un seul process : voir
les invariants d'architecture). Les seeds sont idempotents, sans IA ni réseau, et ne rangent aucun
fichier nouveau (clés de stockage liées au contenu).
"""
import logging
import os
import threading
import time

logger = logging.getLogger("adjugo")

DELAI_DEFAUT_MIN = 30.0

_LOCK = threading.RLock()     # réentrant : jamais d'interblocage si le seed note une activité
# Horloge monotone (insensible aux changements d'heure du système). « remise » = dernier seed complet
# (démarrage du serveur compris) : la vitrine est neuve à ce moment-là, comme après une activité.
_ETAT = {"activite": None, "remise": None}


def _horloge() -> float:
    return time.monotonic()


def delai_secondes() -> float:
    """Délai d'inactivité avant remise à neuf (DEMO_REMISE_A_NEUF_MIN, en minutes). Valeur absente ou
    illisible : 30 min. 0 ou négatif : jamais de remise à neuf automatique."""
    v = (os.getenv("DEMO_REMISE_A_NEUF_MIN") or "").strip().replace(",", ".")
    try:
        minutes = float(v) if v else DELAI_DEFAUT_MIN
    except ValueError:
        minutes = DELAI_DEFAUT_MIN
    return minutes * 60.0


def noter_activite() -> None:
    """Une requête d'une session démo vient d'avoir lieu. Ne lève jamais."""
    try:
        with _LOCK:
            _ETAT["activite"] = _horloge()
    except Exception:       # noqa: BLE001 — le suivi ne doit jamais faire échouer une requête
        pass


def noter_remise() -> None:
    """La vitrine vient d'être recréée (démarrage du serveur, remise à neuf)."""
    with _LOCK:
        _ETAT["remise"] = _horloge()


def _derniere_trace():
    traces = [t for t in (_ETAT["activite"], _ETAT["remise"]) if t is not None]
    return max(traces) if traces else None


def a_remettre_a_neuf() -> bool:
    """Vrai si aucune session démo n'a fait de requête (et aucune remise à neuf n'a eu lieu) depuis le
    délai : la vitrine peut être recréée sans gêner personne."""
    delai = delai_secondes()
    if delai <= 0:
        return False
    with _LOCK:
        derniere = _derniere_trace()
    return derniere is None or (_horloge() - derniere) >= delai


def _rejouer(db) -> dict:
    """Les deux seeds (entreprises, collectivités), chacun isolé : l'échec de l'un n'empêche pas
    l'autre. Renvoie {"entreprises": bool, "collectivites": bool, "duree_s": float}."""
    t0 = time.perf_counter()
    ok = {"entreprises": False, "collectivites": False}
    try:
        from app.services.demo_seed import ensure_demo
        ensure_demo(db, force=True)
        ok["entreprises"] = True
    except Exception as e:      # noqa: BLE001 — jamais bloquant pour l'ouverture de la session
        logger.warning("remise à neuf de la démo (entreprises) en échec : %s", type(e).__name__)
        try:
            db.rollback()
        except Exception:       # noqa: BLE001
            pass
    try:
        from app.services.acheteur_demo_seed import ensure_demo_acheteur
        ensure_demo_acheteur(db, force=True)
        ok["collectivites"] = True
    except Exception as e:      # noqa: BLE001
        logger.warning("remise à neuf de la démo (collectivités) en échec : %s", type(e).__name__)
        try:
            db.rollback()
        except Exception:       # noqa: BLE001
            pass
    ok["duree_s"] = round(time.perf_counter() - t0, 2)
    return ok


def remettre_a_neuf_si_inactive(db) -> dict:
    """Appelé à l'OUVERTURE d'une session démo, avant de la délivrer. Rejoue les seeds si la démo est
    inactive depuis le délai ; sinon ne fait rien. Ne lève jamais. Renvoie {"remise": bool, …}."""
    try:
        with _LOCK:
            delai = delai_secondes()
            derniere = _derniere_trace()
            if delai <= 0 or (derniere is not None and (_horloge() - derniere) < delai):
                _ETAT["activite"] = _horloge()          # l'ouverture compte comme une activité
                return {"remise": False}
            # Sous le verrou : deux ouvertures simultanées ne rejouent pas le seed deux fois.
            res = _rejouer(db)
            _ETAT["remise"] = _ETAT["activite"] = _horloge()
        logger.info("Démo remise à neuf avant une nouvelle présentation (inactive depuis %s min) : "
                    "entreprises %s, collectivités %s, %.2f s.", round(delai / 60),
                    "ok" if res["entreprises"] else "en échec",
                    "ok" if res["collectivites"] else "en échec", res["duree_s"])
        return {"remise": True, **res}
    except Exception as e:      # noqa: BLE001 — l'ouverture de la session passe toujours
        logger.warning("remise à neuf de la démo impossible : %s", type(e).__name__)
        try:
            db.rollback()
        except Exception:       # noqa: BLE001
            pass
        return {"remise": False}


def _reinitialiser_pour_tests() -> None:
    with _LOCK:
        _ETAT["activite"] = None
        _ETAT["remise"] = None
