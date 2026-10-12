"""
Adjugo — surveillance de la qualité de l'IA en production, par fournisseur et par tâche.

Compte, pour chaque couple (fournisseur, tâche) :
  • les appels (réussis, en erreur, refusés) et leurs délais ;
  • les réponses JSON invalides et les réponses coupées (plafond de sortie) ;
  • les citations vérifiées par citation_guard (acceptées / rejetées) ;
  • les abstentions « pas trouvé dans le dossier » (questions) ;
  • les bascules de secours (de quel fournisseur vers lequel, et pourquoi).

Tout est en mémoire du process (process unique, cf. invariants d'architecture), exposé dans /metrics
(format Prometheus) et dans la route d'administration GET /api/admin/ia/qualite. Des SEUILS d'alerte
sont évalués sur une fenêtre glissante des derniers appels : un dépassement est JOURNALISÉ (une fois
par période), jamais bloquant. Aucune donnée client ici : des compteurs et des noms de tâches.

Attribution d'une citation ou d'une abstention : au DERNIER appel IA du contexte courant (contextvar
posée par app.services.llm.messages_create), c'est-à-dire au fournisseur qui a réellement produit
le texte vérifié — secours compris.
"""
import collections
import contextvars
import logging
import os
import threading
import time

logger = logging.getLogger("adjugo")

_LOCK = threading.Lock()


def _env_float(name: str, default: float) -> float:
    try:
        v = float(str(os.getenv(name, "")).strip() or default)
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


# Seuils d'alerte (part des appels de la fenêtre glissante) — réglables, jamais bloquants.
def seuils() -> dict:
    return {
        "fenetre": _env_int("LLM_ALERTE_FENETRE", 50),              # derniers appels regardés
        "min_appels": _env_int("LLM_ALERTE_MIN_APPELS", 10),        # pas d'alerte avant
        "erreurs": _env_float("LLM_ALERTE_ERREURS", 0.10),
        "json_invalides": _env_float("LLM_ALERTE_JSON", 0.05),
        "coupees": _env_float("LLM_ALERTE_COUPEES", 0.05),
        "refus": _env_float("LLM_ALERTE_REFUS", 0.02),
        "bascules": _env_float("LLM_ALERTE_BASCULES", 0.10),
        "citations_rejetees": _env_float("LLM_ALERTE_CITATIONS_REJETEES", 0.25),
        "abstentions": _env_float("LLM_ALERTE_ABSTENTIONS", 0.50),
        "delai_p95_s": _env_float("LLM_ALERTE_DELAI_P95_S", 120.0),
        "repetition_s": _env_float("LLM_ALERTE_REPETITION_S", 1800.0),   # une même alerte au plus 1 fois / 30 min
    }


LIBELLES_SEUILS = {
    "erreurs": "appels en erreur",
    "json_invalides": "réponses JSON invalides",
    "coupees": "réponses coupées",
    "refus": "refus du modèle",
    "bascules": "bascules vers le secours",
    "citations_rejetees": "citations rejetées par la vérification",
    "abstentions": "réponses « pas trouvé dans le dossier »",
    "delai_p95_s": "délai au 95e centile (secondes)",
}

_DUREE_BUCKETS = [1, 2, 5, 10, 30, 60, 120, 300]

# (fournisseur, tache) -> compteurs cumulés
_STATS: dict = {}
# (fournisseur, tache) -> derniers appels {ok, erreur, refus, json, coupee, bascule, duree}
_FEN: dict = {}
# (fournisseur, tache) -> dernières vérifications de citations [(acceptées, rejetées)] et abstentions
_FEN_CIT: dict = {}
_FEN_ABS: dict = {}
# Bascules : compteur (tache, de, vers, motif) et dernières bascules (sans contenu)
_BASCULES: dict = {}
_DERNIERES_BASCULES = collections.deque(maxlen=50)
# Dernière alerte journalisée par (clé, mesure) → horodatage (anti-répétition)
_ALERTES_VUES: dict = {}
_ABSENT_VU: dict = {}
_DERNIERES_ALERTES = collections.deque(maxlen=50)

# Dernier appel IA du contexte courant : (fournisseur, tache) — pour attribuer citations/abstentions.
_DERNIER = contextvars.ContextVar("adjugo_llm_dernier_appel", default=None)


def _vide() -> dict:
    return {"appels": 0, "reussis": 0, "erreurs": 0, "refus": 0, "json_invalides": 0, "coupees": 0,
            "bascules_depuis": 0, "citations_acceptees": 0, "citations_rejetees": 0, "abstentions": 0,
            "questions": 0, "duree_somme": 0.0, "duree_max": 0.0,
            "duree_buckets": {b: 0 for b in _DUREE_BUCKETS}, "modeles": {}}


def _stats(cle) -> dict:
    s = _STATS.get(cle)
    if s is None:
        s = _STATS[cle] = _vide()
    return s


def _fen(store: dict, cle):
    d = store.get(cle)
    taille = seuils()["fenetre"]
    if d is None or d.maxlen != taille:
        d = store[cle] = collections.deque(d or (), maxlen=taille)
    return d


def marquer_dernier(fournisseur: str, tache: str) -> None:
    """Posée par messages_create après chaque réponse : le texte vérifié ensuite vient de là."""
    _DERNIER.set((fournisseur or "?", tache or "sans_tache"))


def dernier():
    return _DERNIER.get()


def noter_appel(fournisseur: str, tache: str, modele: str, duree: float, resultat: str = "ok",
                coupee: bool = False, json_invalide: bool = False) -> None:
    """resultat : « ok » | « erreur » | « refus »."""
    cle = (fournisseur or "?", tache or "sans_tache")
    duree = max(0.0, float(duree or 0.0))
    with _LOCK:
        s = _stats(cle)
        s["appels"] += 1
        if resultat == "ok":
            s["reussis"] += 1
        elif resultat == "refus":
            s["refus"] += 1
        else:
            s["erreurs"] += 1
        if coupee:
            s["coupees"] += 1
        if json_invalide:
            s["json_invalides"] += 1
        s["modeles"][modele or "?"] = s["modeles"].get(modele or "?", 0) + 1
        s["duree_somme"] += duree
        s["duree_max"] = max(s["duree_max"], duree)
        for b in _DUREE_BUCKETS:
            if duree <= b:
                s["duree_buckets"][b] += 1
        _fen(_FEN, cle).append({"ok": resultat == "ok", "erreur": resultat == "erreur",
                                "refus": resultat == "refus", "json": bool(json_invalide),
                                "coupee": bool(coupee), "bascule": False, "duree": duree})
    _verifier_seuils(cle)


def noter_bascule(tache: str, de: str, vers: str, motif: str, detail: str = "", modele_de: str = "",
                  modele_vers: str = "") -> None:
    """Une bascule de secours : journalisée (avertissement, sauf « absent » : information) et comptée."""
    tache = tache or "sans_tache"
    with _LOCK:
        k = (tache, de or "?", vers or "?", motif or "?")
        _BASCULES[k] = _BASCULES.get(k, 0) + 1
        _DERNIERES_BASCULES.append({"quand": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "tache": tache, "de": de, "vers": vers, "motif": motif,
                                    "modele_de": modele_de, "modele_vers": modele_vers,
                                    "detail": (detail or "")[:200]})
        cle = (de or "?", tache)
        _stats(cle)["bascules_depuis"] += 1
        fen = _fen(_FEN, cle)
        if fen and motif != "absent":
            fen[-1]["bascule"] = True
        elif motif == "absent":
            # Fournisseur absent : pas d'appel tenté, la bascule compte quand même dans la fenêtre.
            fen.append({"ok": False, "erreur": False, "refus": False, "json": False, "coupee": False,
                        "bascule": True, "duree": 0.0, "absent": True})
    msg = ("Bascule de secours IA — tâche « %s » : %s (%s) → %s (%s), motif : %s%s"
           % (tache, de, modele_de or "?", vers, modele_vers or "?", motif, (" — " + detail[:160]) if detail else ""))
    if motif == "absent":
        # Fournisseur non configuré : la même bascule à chaque appel → journalisée une fois par heure.
        now = time.monotonic()
        with _LOCK:
            vu = _ABSENT_VU.get((tache, de))
            if vu is None or now - vu >= 3600:
                _ABSENT_VU[(tache, de)] = now
            else:
                msg = ""
        if msg:
            logger.info(msg + " (comptée à chaque appel, journalisée une fois par heure)")
    else:
        logger.warning(msg)
    _verifier_seuils((de or "?", tache))


def noter_citations(acceptees: int, rejetees: int, fournisseur: str = None, tache: str = None) -> None:
    """Citations d'une réponse vérifiées contre le dossier (citation_guard) : attribuées au dernier
    appel IA du contexte si fournisseur/tâche ne sont pas donnés."""
    acceptees, rejetees = max(0, int(acceptees or 0)), max(0, int(rejetees or 0))
    if not (acceptees or rejetees):
        return
    if fournisseur is None or tache is None:
        d = _DERNIER.get()
        if d is None:
            return          # aucun appel IA dans ce contexte : rien à attribuer
        fournisseur = fournisseur or d[0]
        tache = tache or d[1]
    cle = (fournisseur, tache)
    with _LOCK:
        s = _stats(cle)
        s["citations_acceptees"] += acceptees
        s["citations_rejetees"] += rejetees
        _fen(_FEN_CIT, cle).append((acceptees, rejetees))
    _verifier_seuils(cle)


def noter_question(trouve, fournisseur: str = None, tache: str = None) -> None:
    """Une question posée sur le dossier : trouve=False compte une abstention « pas dans le dossier »."""
    if fournisseur is None or tache is None:
        d = _DERNIER.get()
        if d is None:
            return
        fournisseur = fournisseur or d[0]
        tache = tache or d[1]
    cle = (fournisseur, tache)
    abst = trouve is False
    with _LOCK:
        s = _stats(cle)
        s["questions"] += 1
        if abst:
            s["abstentions"] += 1
        _fen(_FEN_ABS, cle).append(1 if abst else 0)
    _verifier_seuils(cle)


def _p95(durees: list) -> float:
    if not durees:
        return 0.0
    d = sorted(durees)
    return d[min(len(d) - 1, int(round(0.95 * (len(d) - 1))))]


def _taux_fenetre(cle) -> dict:
    """Taux sur la fenêtre glissante (à appeler sous _LOCK)."""
    fen = list(_FEN.get(cle) or ())
    n = len(fen)
    reels = [x for x in fen if not x.get("absent")]
    nr = len(reels) or 1
    out = {"appels": n}
    if n:
        out["erreurs"] = sum(1 for x in reels if x["erreur"]) / nr
        out["json_invalides"] = sum(1 for x in reels if x["json"]) / nr
        out["coupees"] = sum(1 for x in reels if x["coupee"]) / nr
        out["refus"] = sum(1 for x in reels if x["refus"]) / nr
        out["bascules"] = sum(1 for x in fen if x["bascule"]) / n
        out["delai_p95_s"] = _p95([x["duree"] for x in reels])
    cit = list(_FEN_CIT.get(cle) or ())
    acc, rej = sum(a for a, _ in cit), sum(r for _, r in cit)
    out["citations"] = acc + rej
    if acc + rej:
        out["citations_rejetees"] = rej / (acc + rej)
    ab = list(_FEN_ABS.get(cle) or ())
    out["questions"] = len(ab)
    if ab:
        out["abstentions"] = sum(ab) / len(ab)
    return out


def _verifier_seuils(cle) -> None:
    """Journalise (sans bloquer) chaque seuil dépassé sur la fenêtre glissante, une fois par période."""
    try:
        sl = seuils()
        now = time.monotonic()
        a_journaliser = []
        with _LOCK:
            t = _taux_fenetre(cle)
            for mesure, seuil in sl.items():
                if mesure in ("fenetre", "min_appels", "repetition_s") or mesure not in t:
                    continue
                base = t["citations"] if mesure == "citations_rejetees" else (
                    t["questions"] if mesure == "abstentions" else t["appels"])
                if base < sl["min_appels"]:
                    continue
                valeur = t[mesure]
                if valeur <= seuil:
                    continue
                k = (cle, mesure)
                if now - _ALERTES_VUES.get(k, -1e18) < sl["repetition_s"]:
                    continue
                _ALERTES_VUES[k] = now
                alerte = {"quand": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "fournisseur": cle[0],
                          "tache": cle[1], "mesure": mesure, "libelle": LIBELLES_SEUILS.get(mesure, mesure),
                          "valeur": round(valeur, 3), "seuil": seuil, "sur": base}
                _DERNIERES_ALERTES.append(alerte)
                a_journaliser.append(alerte)
        for a in a_journaliser:
            if a["mesure"] == "delai_p95_s":
                txt = f"{a['valeur']:.0f} s (seuil {a['seuil']:.0f} s)"
            else:
                txt = f"{a['valeur'] * 100:.0f} % (seuil {a['seuil'] * 100:.0f} %)"
            logger.warning("Alerte qualité IA — %s, tâche « %s » : %s à %s sur les %d derniers.",
                           a["fournisseur"], a["tache"], a["libelle"], txt, a["sur"])
    except Exception:       # la surveillance ne casse jamais un appel
        pass


def instantane() -> dict:
    """État lisible pour la route d'administration (aucune donnée client)."""
    with _LOCK:
        lignes = []
        for (f, t), s in sorted(_STATS.items()):
            reels = s["appels"] or 0
            fen = _taux_fenetre((f, t))

            def pct(x, n):
                return round(100.0 * x / n, 1) if n else None
            cit = s["citations_acceptees"] + s["citations_rejetees"]
            lignes.append({
                "fournisseur": f, "tache": t, "modeles": dict(s["modeles"]),
                "appels": reels, "reussis": s["reussis"], "erreurs": s["erreurs"], "refus": s["refus"],
                "json_invalides": s["json_invalides"], "coupees": s["coupees"],
                "bascules_vers_le_secours": s["bascules_depuis"],
                "citations_acceptees": s["citations_acceptees"], "citations_rejetees": s["citations_rejetees"],
                "questions": s["questions"], "abstentions": s["abstentions"],
                "pourcentages": {"erreurs": pct(s["erreurs"], reels), "json_invalides": pct(s["json_invalides"], reels),
                                 "coupees": pct(s["coupees"], reels), "refus": pct(s["refus"], reels),
                                 "citations_rejetees": pct(s["citations_rejetees"], cit),
                                 "abstentions": pct(s["abstentions"], s["questions"])},
                "delai_moyen_s": round(s["duree_somme"] / reels, 2) if reels else None,
                "delai_max_s": round(s["duree_max"], 2),
                "fenetre_glissante": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fen.items()},
            })
        bascules = [{"tache": t, "de": de, "vers": vers, "motif": m, "nombre": n}
                    for (t, de, vers, m), n in sorted(_BASCULES.items())]
        return {"par_fournisseur_et_tache": lignes, "bascules": bascules,
                "dernieres_bascules": list(_DERNIERES_BASCULES)[-20:],
                "dernieres_alertes": list(_DERNIERES_ALERTES)[-20:],
                "seuils": seuils(),
                "note": ("Compteurs depuis le dernier démarrage du serveur. Les alertes sont journalisées, "
                         "jamais bloquantes.")}


def derniere_bascule() -> dict:
    with _LOCK:
        return dict(_DERNIERES_BASCULES[-1]) if _DERNIERES_BASCULES else {}


def prometheus_lignes(fmt) -> list:
    """Lignes Prometheus (fmt = app.core.metrics._fmt)."""
    out = []
    with _LOCK:
        items = sorted(_STATS.items())
        out += ["# HELP adjugo_llm_tache_appels_total Appels IA par fournisseur, tâche et résultat.",
                "# TYPE adjugo_llm_tache_appels_total counter"]
        for (f, t), s in items:
            for res, k in (("ok", "reussis"), ("erreur", "erreurs"), ("refus", "refus")):
                out.append(fmt("adjugo_llm_tache_appels_total", s[k], {"fournisseur": f, "tache": t, "resultat": res}))
        for nom, k, aide in (("adjugo_llm_json_invalides_total", "json_invalides", "Réponses JSON invalides."),
                             ("adjugo_llm_coupees_total", "coupees", "Réponses coupées (plafond de sortie)."),
                             ("adjugo_llm_abstentions_total", "abstentions", "Questions : pas trouvé dans le dossier."),
                             ("adjugo_llm_questions_total", "questions", "Questions posées sur le dossier.")):
            out += [f"# HELP {nom} {aide}", f"# TYPE {nom} counter"]
            for (f, t), s in items:
                out.append(fmt(nom, s[k], {"fournisseur": f, "tache": t}))
        out += ["# HELP adjugo_llm_citations_total Citations vérifiées contre le dossier (citation_guard).",
                "# TYPE adjugo_llm_citations_total counter"]
        for (f, t), s in items:
            out.append(fmt("adjugo_llm_citations_total", s["citations_acceptees"],
                           {"fournisseur": f, "tache": t, "verdict": "acceptee"}))
            out.append(fmt("adjugo_llm_citations_total", s["citations_rejetees"],
                           {"fournisseur": f, "tache": t, "verdict": "rejetee"}))
        out += ["# HELP adjugo_llm_tache_duree_seconds Durée des appels IA par fournisseur et tâche.",
                "# TYPE adjugo_llm_tache_duree_seconds histogram"]
        for (f, t), s in items:
            lab = {"fournisseur": f, "tache": t}
            for b in _DUREE_BUCKETS:
                out.append(fmt("adjugo_llm_tache_duree_seconds_bucket", s["duree_buckets"][b], dict(lab, le=str(b))))
            out.append(fmt("adjugo_llm_tache_duree_seconds_bucket", s["appels"], dict(lab, le="+Inf")))
            out.append(fmt("adjugo_llm_tache_duree_seconds_sum", round(s["duree_somme"], 3), lab))
            out.append(fmt("adjugo_llm_tache_duree_seconds_count", s["appels"], lab))
        out += ["# HELP adjugo_llm_bascules_total Bascules de secours entre fournisseurs.",
                "# TYPE adjugo_llm_bascules_total counter"]
        for (t, de, vers, m), n in sorted(_BASCULES.items()):
            out.append(fmt("adjugo_llm_bascules_total", n, {"tache": t, "de": de, "vers": vers, "motif": m}))
    return out


def reinitialiser() -> None:
    """Remise à zéro (tests)."""
    with _LOCK:
        _STATS.clear()
        _FEN.clear()
        _FEN_CIT.clear()
        _FEN_ABS.clear()
        _BASCULES.clear()
        _DERNIERES_BASCULES.clear()
        _ALERTES_VUES.clear()
        _ABSENT_VU.clear()
        _DERNIERES_ALERTES.clear()
