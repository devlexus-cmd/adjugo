"""
PREUVE EMPIRIQUE du scoring Go/No-Go déterministe (cœur du pitch Adjugo).

Le pitch promet un score « déterministe, reproductible, explicable, sans hallucination ».
Ces tests transforment cette promesse en invariants VÉRIFIÉS à chaque CI :

  1. Reproductibilité   — même entrée → score strictement identique (100 exécutions).
  2. Explicabilité      — la somme du barème détaillé == le score (chaque point tracé).
  3. Bornage            — score ∈ [0, 100] sur des entrées variées.
  4. Anti-hallucination — une donnée MANQUANTE ne fait JAMAIS monter le score.
  5. Monotonicité       — une meilleure adéquation ne fait jamais baisser le score.
  6. Seuils Go/No-Go    — frontières go / a_etudier / no_go correctes.
  7. Ancres « golden »  — deux DCE réalistes → scores exacts connus (garde anti-régression).

Tests PURS : aucun LLM, aucune base — le module score_dce est par construction
indépendant de l'IA (l'IA extrait les faits, le barème calcule le score).
"""
from app.services.dce_scoring import score_dce

# Date limite toujours lointaine → délai stable dans le temps (test non daté).
FUTURE = "31/12/2099"
PAST = "01/01/2020"

# DCE parfaitement adéquat pour l'entreprise → doit scorer 100 / go.
FULL_MATCH = dict(
    details=dict(
        intitule_marche="Réfection de toiture et étanchéité d'un groupe scolaire",
        type_marche="travaux",
        lieu_execution="Quimper (29)",
        budget_estime="480 000 EUR HT",
        ca_minimum_requis="200 000 EUR",
        qualifications_requises=["Qualibat 3212"],
        criteres_attribution=[{"critere": "valeur technique"}, {"critere": "prix"}],
        date_limite=FUTURE,
    ),
    company=dict(name="Toitures de l'Ouest", ca_n1=600000, postal_code="29000",
                 qualifications=[{"name": "Qualibat 3212", "detail": "étanchéité"}]),
    criteria=dict(specialites="toiture, étanchéité", departements=["29"],
                  budget_min=50000, budget_max=1000000, go_threshold=60),
)

# DCE inadéquat (autre métier, hors zone, budget hors fourchette, CA inatteignable,
# qualif non couverte, échéance dépassée) → doit scorer bas / no_go.
NO_MATCH = dict(
    details=dict(
        intitule_marche="Prestation d'infogérance informatique",
        type_marche="services",
        lieu_execution="Lille (59)",
        budget_estime="5 000 EUR",
        ca_minimum_requis="5 000 000 EUR",
        qualifications_requises=["Certification 27001"],
        date_limite=PAST,
    ),
    company=dict(name="Toitures de l'Ouest", ca_n1=100000, postal_code="29000",
                 qualifications=[{"name": "Qualibat"}]),
    criteria=dict(specialites="toiture, étanchéité", departements=["29"],
                  budget_min=50000, budget_max=1000000, go_threshold=60),
)


# ── 1. Reproductibilité ───────────────────────────────────────────────────────
def test_reproductible_100_executions():
    ref = score_dce(**FULL_MATCH)
    for _ in range(100):
        r = score_dce(**FULL_MATCH)
        assert r["score"] == ref["score"]
        assert r["go_decision"] == ref["go_decision"]
        assert [c["points"] for c in r["breakdown"]] == [c["points"] for c in ref["breakdown"]]


# ── 2. Explicabilité : la somme du barème == le score ─────────────────────────
def test_breakdown_somme_egale_score():
    for case in (FULL_MATCH, NO_MATCH):
        r = score_dce(**case)
        assert r["score"] == sum(c["points"] for c in r["breakdown"])
        # chaque critère est complet et lisible (défendable devant un acheteur)
        for c in r["breakdown"]:
            assert set(c) >= {"key", "label", "points", "max_points", "status", "detail"}
            assert 0 <= c["points"] <= c["max_points"]
            assert c["detail"]
    # les 6 critères du barème sont toujours présents
    keys = {c["key"] for c in score_dce(**FULL_MATCH)["breakdown"]}
    assert keys == {"metier", "zone", "budget", "capacite", "qualifs", "delai"}


# ── 3. Bornage [0, 100] ───────────────────────────────────────────────────────
def test_score_borne_0_100():
    for case in (FULL_MATCH, NO_MATCH, dict(details={}, company={}, criteria={})):
        r = score_dce(**case)
        assert 0 <= r["score"] <= 100


# ── 4. Anti-hallucination : une donnée MANQUANTE n'est jamais un bonus ─────────
def test_donnee_manquante_ne_monte_jamais_le_score():
    full = score_dce(**FULL_MATCH)["score"]
    # On retire, un par un, des faits favorables : le score ne doit pas augmenter.
    import copy
    for path in (("details", "budget_estime"),
                 ("company", "ca_n1"),
                 ("details", "lieu_execution"),
                 ("details", "date_limite")):
        c = copy.deepcopy(FULL_MATCH)
        c[path[0]].pop(path[1], None)
        degraded = score_dce(**c)["score"]
        assert degraded <= full, f"Retirer {path} a AUGMENTÉ le score ({degraded} > {full})"


def test_profil_vide_est_prudent_pas_genereux():
    """Sans profil entreprise, le métier est 'inconnu' à score partiel (18/30), jamais 30."""
    r = score_dce(details=FULL_MATCH["details"], company={}, criteria={})
    metier = next(c for c in r["breakdown"] if c["key"] == "metier")
    assert metier["status"] == "inconnu"
    assert metier["points"] < metier["max_points"]


# ── 5. Monotonicité : meilleure adéquation ⇒ score ≥ ──────────────────────────
def test_monotonicite_metier():
    import copy
    bon = score_dce(**FULL_MATCH)["score"]
    c = copy.deepcopy(FULL_MATCH)
    c["criteria"]["specialites"] = "plomberie, chauffage"   # ne recoupe plus le marché
    moins_bon = score_dce(**c)["score"]
    assert moins_bon <= bon


# ── 6. Seuils Go / À étudier / No-Go ──────────────────────────────────────────
def test_seuils_go_nogo():
    assert score_dce(**FULL_MATCH)["go_decision"] == "go"
    assert score_dce(**NO_MATCH)["go_decision"] == "no_go"
    # Un cas intermédiaire bascule en 'a_etudier' :
    # métier partiel (8) + hors zone (5) + budget inconnu (9) + capacité ok (15)
    # + qualif non couverte (3) + délai ok (10) = 50 ∈ [38, 60[.
    import copy
    c = copy.deepcopy(FULL_MATCH)
    c["details"].pop("budget_estime", None)                 # budget inconnu
    c["details"]["lieu_execution"] = "Lille (59)"           # hors zone
    c["company"]["qualifications"] = []                     # plus de qualif couvrante
    c["criteria"]["specialites"] = "plomberie"              # métier non recoupé
    r = score_dce(**c)
    assert r["score"] == 50
    assert r["go_decision"] == "a_etudier"


# ── 7. Ancres golden (anti-régression sur le barème) ──────────────────────────
def test_golden_full_match_vaut_100():
    assert score_dce(**FULL_MATCH)["score"] == 100


def test_golden_no_match_vaut_25():
    # 8 (métier) + 5 (zone) + 6 (budget) + 2 (capacité) + 3 (qualifs) + 1 (délai)
    assert score_dce(**NO_MATCH)["score"] == 25
