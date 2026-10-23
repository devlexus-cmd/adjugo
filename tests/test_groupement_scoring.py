"""
Score de GROUPEMENT (co-traitance v2, innovation A) — invariants VÉRIFIÉS à chaque CI.

Le pitch : « seul 74 % → avec Étanchéité Le Gall 94 % », par RÉAPPLICATION du barème
déterministe score_dce à une entreprise virtuelle (cumul des membres). Ces tests verrouillent :

  a. Idempotence        — 50 exécutions → sortie strictement identique.
  b. CA inconnu          — compte 0 dans le cumul + avertissement explicite (jamais un bonus).
  c. « chaque membre »   — la clause du DCE annule le cumul (CA/effectif = lead seul) + warning.
  d. Jamais go_groupement sans partenaire réel (ni sans gain).
  e. Seul déjà 'go'      — decision 'go' (le groupement n'a pas à être proposé).
  f. Cas canon           — seul 74 (a_etudier) → avec partenaire 94 (go_groupement), apporte_par,
                           gaps_combles, warning « déclaré par vous ».
  g. auto_alliance       — choisit qui comble le plus, borné max_partners, stable à l'ordre du pool.
  h. gaps_for            — 'a_verifier' sur CA non renseigné, extrait recopié, suffixe Qualibat.

Tests PURS : aucun LLM, aucune base, aucun réseau. Date limite lointaine (délai stable).
"""
import copy
import json

from app.services.dce_scoring import score_dce
from app.services.groupement_scoring import (
    GAP_KEYS, auto_alliance, cumulate, gaps_for, member_capacities, score_groupement,
)

FUTURE = "31/12/2099"

# Marché : toiture/étanchéité à Quimper, CA mini 300 k€, Qualibat 3212 exigée, 2 lots.
DETAILS = dict(
    intitule_marche="Réfection de toiture et étanchéité d'un groupe scolaire",
    type_marche="travaux",
    lieu_execution="Quimper (29)",
    ca_minimum_requis="CA minimum de 300 000 EUR HT",
    qualifications_requises=["Qualibat 3212"],
    criteres_attribution=[{"critere": "valeur technique"}, {"critere": "prix"}],
    date_limite=FUTURE,
    allotissement="Lot 1 : Couverture, Lot 2 : Étanchéité",
    capacites_groupement="Non specifie dans le DCE",
    exigences_sources={
        "ca_minimum_requis": "chiffre d'affaires minimum de 300 000 EUR HT",
        "qualifications_requises": "Qualibat 3212 exigée",
        "references_requises": "", "effectif_minimum_requis": "", "capacites_groupement": "",
    },
)
# Lead : métier ok, zone ok, CA insuffisant (180 k€ < 300 k€), qualification exigée manquante.
LEAD = dict(name="Toitures de l'Ouest", ca_n1=180000, postal_code="29000",
            qualifications=[{"name": "Certificat couvreur zingueur", "detail": "couverture"}])
CRITERIA = dict(specialites="toiture, couverture", departements=["29"], go_threshold=80)
# Partenaire déclaré par l'utilisateur : apporte CA + Qualibat 3212.
PARTNER = dict(kind="annuaire", id=7, name="Étanchéité Le Gall", ca_n1=250000,
               qualifications="Qualibat 3212, RGE", specialites="étanchéité",
               departement="29", source="declare")


def _run(members, details=None, lead=None, criteria=None):
    return score_groupement(details or DETAILS, lead or LEAD, criteria or CRITERIA, members)


# ── a. Idempotence ────────────────────────────────────────────────────────────────────
def test_idempotence_50_executions():
    ref = json.dumps(_run([PARTNER]), sort_keys=True, ensure_ascii=False)
    for _ in range(50):
        assert json.dumps(_run([PARTNER]), sort_keys=True, ensure_ascii=False) == ref
    # Et l'entrée n'est pas mutée (service pur).
    d, l, c, p = copy.deepcopy(DETAILS), copy.deepcopy(LEAD), copy.deepcopy(CRITERIA), copy.deepcopy(PARTNER)
    score_groupement(d, l, c, [p])
    assert (d, l, c, p) == (DETAILS, LEAD, CRITERIA, PARTNER)


def test_score_seul_est_exactement_score_dce():
    r = _run([PARTNER])
    det = score_dce(DETAILS, LEAD, CRITERIA)
    assert r["score_seul"] == det["score"]
    assert r["thresholds"] == {"go": det["threshold"], "nogo": det["nogo_threshold"]}
    assert [c["points_seul"] for c in r["breakdown"]] == [c["points"] for c in det["breakdown"]]
    assert [c["key"] for c in r["breakdown"]] == ["metier", "zone", "budget", "capacite", "qualifs", "delai"]


# ── b. CA inconnu compte 0 + warning ──────────────────────────────────────────────────
def test_ca_inconnu_compte_zero_et_avertit():
    sans_ca = dict(PARTNER, name="Sans CA", ca_n1=None)
    r = _run([sans_ca])
    assert r["cumul"]["ca_n1"] == 180000.0                 # = CA du lead seul, pas un bonus
    assert r["cumul"]["ca_unknown_members"] == ["Sans CA"]
    cap = next(c for c in r["breakdown"] if c["key"] == "capacite")
    assert cap["points_groupement"] == cap["points_seul"]   # le critère n'a PAS bougé
    assert any("Sans CA" in w and "n'est pas connu" in w and "0 dans le cumul" in w for w in r["warnings"])
    # Un CA à 0 (valeur par défaut du modèle) est traité comme INCONNU, jamais comme 0 €.
    assert member_capacities(dict(PARTNER, ca_n1=0))["ca_n1"] is None
    # Aucun CA connu du tout → None (statut 'inconnu'), pas 0.
    assert cumulate([dict(kind="lead", name="A"), dict(name="B")])["ca_n1"] is None


# ── c. « chaque membre » annule le cumul ──────────────────────────────────────────────
def test_chaque_membre_annule_le_cumul():
    for clause in ("Chaque membre du groupement doit satisfaire individuellement au niveau minimal de CA",
                   "Les capacités sont appréciées pour chacun des membres",
                   "Le niveau minimal est exigé INDIVIDUELLEMENT de chaque cotraitant"):
        d = dict(DETAILS, capacites_groupement=clause)
        r = _run([PARTNER], details=d)
        assert r["cumul"]["cumul_admis"] is False
        assert r["cumul"]["ca_n1"] == 180000.0                # lead seul
        cap = next(c for c in r["breakdown"] if c["key"] == "capacite")
        assert cap["points_groupement"] == cap["points_seul"]
        assert "chaque membre satisfasse seul" in " ".join(r["warnings"])
        assert r["decision"] != "go_groupement" or r["score_groupement"] > r["score_seul"]
    # Cumul admis explicitement → s'additionne.
    r = _run([PARTNER], details=dict(DETAILS, capacites_groupement="cumul admis"))
    assert r["cumul"]["cumul_admis"] is True and r["cumul"]["ca_n1"] == 430000.0


# ── d. Jamais go_groupement sans partenaire ───────────────────────────────────────────
def test_jamais_go_groupement_sans_partenaire():
    for members in ([], [dict(kind="lead", name="Toitures de l'Ouest")], None):
        r = _run(members)
        assert r["decision"] != "go_groupement"
        assert r["score_groupement"] == r["score_seul"]     # seul = seul
        assert [m["kind"] for m in r["members"]] == ["lead"]
    # Un partenaire qui n'apporte RIEN (score inchangé) → pas de go_groupement non plus.
    inutile = dict(kind="annuaire", id=9, name="Peinture Durand", specialites="peinture", departement="75")
    r = _run([inutile])
    assert r["score_groupement"] == r["score_seul"]
    assert r["decision"] != "go_groupement"


# ── e. Seul déjà 'go' → decision 'go' ─────────────────────────────────────────────────
def test_seul_deja_go_reste_go():
    lead_ok = dict(LEAD, ca_n1=600000, qualifications=[{"name": "Qualibat 3212"}])
    r = _run([PARTNER], lead=lead_ok)
    assert r["decision_seul"] == "go"
    assert r["decision"] == "go"
    assert r["score_groupement"] >= r["score_seul"]          # calculé quand même
    assert r["gaps"] == []


# ── f. Cas canon : seul 74 → avec partenaire 94 ──────────────────────────────────────
def test_cas_canon_seul_vers_groupement():
    r = _run([PARTNER])
    # Seul : 30 métier + 20 zone + 9 budget (non publié) + 2 CA insuffisant + 3 qualif + 10 délai = 74
    assert r["score_seul"] == 74 and r["decision_seul"] == "a_etudier"
    # Groupement : CA 430 k€ ≥ 300 k€ (15) + Qualibat 3212 apportée (10) = 94 ≥ seuil 80
    assert r["score_groupement"] == 94
    assert r["decision"] == "go_groupement"
    bd = {c["key"]: c for c in r["breakdown"]}
    assert bd["capacite"]["apporte_par"] == ["Étanchéité Le Gall"]
    assert bd["qualifs"]["apporte_par"] == ["Étanchéité Le Gall"]
    assert bd["metier"]["apporte_par"] == []                 # déjà ok seul : personne ne « fait passer »
    assert {g["key"] for g in r["gaps_combles"]} == {"capacite", "qualifs"}
    assert all(g["apporte_par"] == ["Étanchéité Le Gall"] for g in r["gaps_combles"])
    assert r["gaps"] == []
    assert r["cumul"]["name"] == "Groupement (Toitures de l'Ouest + Étanchéité Le Gall)"
    # Verdict fondé sur des capacités DÉCLARÉES par l'utilisateur → avertir, pas bloquer.
    assert any("déclarées par vous (Étanchéité Le Gall)" in w for w in r["warnings"])
    # Partenaire VÉRIFIÉ (contribution) → pas cet avertissement.
    r2 = _run([dict(PARTNER, source="contribution")])
    assert r2["decision"] == "go_groupement"
    assert not any("déclarées par vous" in w for w in r2["warnings"])
    # Langage : jamais « consortium » dans ce qui est montré au client.
    assert "consortium" not in json.dumps(r, ensure_ascii=False).lower()


# ── g. auto_alliance ──────────────────────────────────────────────────────────────────
POOL = [
    dict(kind="annuaire", id=1, name="CA seulement", ca_n1=200000, departement="29"),
    dict(PARTNER, id=2),                                          # CA + Qualibat 3212 → comble 2 gaps
    dict(kind="annuaire", id=3, name="Rien", specialites="peinture", departement="75"),
]


def test_auto_alliance_choisit_qui_comble_le_plus():
    a = auto_alliance(DETAILS, LEAD, CRITERIA, POOL)
    assert [c["name"] for c in a["chosen"]] == ["Étanchéité Le Gall"]
    assert a["score_groupement"] == 94 and a["decision"] == "go_groupement"
    assert a["considered"] == 3
    assert "chosen" in a and "gaps" in a and "breakdown" in a


def test_auto_alliance_stable_a_l_ordre_du_pool_et_bornee():
    ref = auto_alliance(DETAILS, LEAD, CRITERIA, POOL)
    rev = auto_alliance(DETAILS, LEAD, CRITERIA, list(reversed(POOL)))
    assert [c["name"] for c in rev["chosen"]] == [c["name"] for c in ref["chosen"]]
    assert rev["score_groupement"] == ref["score_groupement"]
    # Borné : max_partners=1 → au plus un partenaire ; 0 → aucun.
    assert len(auto_alliance(DETAILS, LEAD, CRITERIA, POOL, max_partners=1)["chosen"]) <= 1
    assert auto_alliance(DETAILS, LEAD, CRITERIA, POOL, max_partners=0)["chosen"] == []
    # S'arrête quand plus de gain : « Rien » n'est jamais ajouté.
    assert "Rien" not in [c["name"] for c in ref["chosen"]]


def test_auto_alliance_pool_vide_renvoie_seul_avec_gaps():
    a = auto_alliance(DETAILS, LEAD, CRITERIA, [])
    assert a["chosen"] == [] and a["considered"] == 0
    assert a["score_groupement"] == a["score_seul"] == 74
    assert a["decision"] == "a_etudier"
    assert {g["key"] for g in a["gaps"]} == {"capacite", "qualifs"}


# ── h. gaps_for ───────────────────────────────────────────────────────────────────────
def test_gaps_for_ca_non_renseigne_a_verifier_et_extrait_recopie():
    gaps = gaps_for(DETAILS, dict(LEAD, ca_n1=None), CRITERIA)
    cap = next(g for g in gaps if g["key"] == "capacite")
    assert cap["severity"] == "a_verifier"                    # jamais bloquant sur du vide
    assert cap["have"] == "non renseigné"
    assert cap["required"] == "300 000 €"
    assert cap["extrait"] == DETAILS["exigences_sources"]["ca_minimum_requis"]
    # CA renseigné mais insuffisant → bloquant, avec le CA de l'entreprise.
    cap2 = next(g for g in gaps_for(DETAILS, LEAD, CRITERIA) if g["key"] == "capacite")
    assert cap2["severity"] == "bloquant" and cap2["have"] == "180 000 €"
    for g in gaps:
        assert g["key"] in GAP_KEYS
        assert set(g) >= {"key", "label", "required", "have", "extrait", "severity", "trades"}


def test_gaps_for_qualibat_a_confirmer_aupres_du_partenaire():
    q = next(g for g in gaps_for(DETAILS, LEAD, CRITERIA) if g["key"] == "qualifs")
    assert q["label"].endswith("à confirmer auprès du partenaire")
    assert q["severity"] == "important" and q["required"] == "Qualibat 3212"
    assert q["extrait"] == "Qualibat 3212 exigée"
    # Profil sans aucune qualification → 'a_verifier', have = non renseigné.
    q2 = next(g for g in gaps_for(DETAILS, dict(LEAD, qualifications=[]), CRITERIA) if g["key"] == "qualifs")
    assert q2["severity"] == "a_verifier" and q2["have"] == "non renseigné"
    # RGE (vérifiable au registre) seule → pas de suffixe.
    d = dict(DETAILS, qualifications_requises=["RGE"])
    q3 = next(g for g in gaps_for(d, LEAD, CRITERIA) if g["key"] == "qualifs")
    assert "à confirmer" not in q3["label"]


def test_gaps_for_non_specifie_ni_critere_ni_manque():
    d = dict(DETAILS, ca_minimum_requis="Non specifie dans le DCE", qualifications_requises=[],
             references_requises="Non specifie dans le DCE", effectif_minimum_requis="Non specifie dans le DCE")
    assert gaps_for(d, LEAD, CRITERIA) == []
    # Références / effectif exigés et non renseignés côté entreprise → à vérifier, jamais bloquant.
    d2 = dict(DETAILS, references_requises="3 références de travaux similaires sur 5 ans",
              effectif_minimum_requis="10 salariés")
    keys = {g["key"]: g for g in gaps_for(d2, LEAD, CRITERIA)}
    assert keys["references"]["severity"] == "a_verifier" and keys["references"]["have"] == "non renseigné"
    assert keys["effectif"]["severity"] == "a_verifier"
    # Renseignés mais insuffisants → important ; suffisants → plus de manque.
    lead2 = dict(LEAD, effectif=4, references=[{"name": "Toiture école"}])
    keys2 = {g["key"]: g for g in gaps_for(d2, lead2, CRITERIA)}
    assert keys2["references"]["severity"] == "important" and keys2["effectif"]["severity"] == "important"
    lead3 = dict(LEAD, effectif=12, references=[{"name": "A"}, {"name": "B"}, {"name": "C"}])
    assert not {"references", "effectif"} & {g["key"] for g in gaps_for(d2, lead3, CRITERIA)}
    # Métiers des lots non couverts, inférés via app.sourcing.groupement.
    d3 = dict(DETAILS, allotissement="Lot 1 : Couverture, Lot 2 : Électricité courant fort")
    m = next((g for g in gaps_for(d3, LEAD, dict(CRITERIA, specialites="peinture")) if g["key"] == "metier"), None)
    assert m is not None and "electricite" in m["trades"]


# ── Robustesse : données sales, formes multiples ──────────────────────────────────────
def test_member_capacities_formes_multiples_et_idempotent():
    sirene = member_capacities({"nom": "SIRENE SAS", "siret": "123 456 789 00012", "naf_label": "Travaux d'étanchéité",
                                "departement": "29", "effectif": 8, "est_rge": True, "source": "sirene",
                                "freshness_date": "2026-09-01"})
    assert sirene["kind"] == "sirene" and sirene["verified"] is True
    assert sirene["ca_n1"] is None and sirene["effectif"] == 8 and sirene["siret"] == "12345678900012"
    assert sirene["qualifications"] == ["RGE"] and sirene["departements"] == ["29"]
    assert member_capacities(sirene) == sirene                 # idempotent
    saisi = member_capacities({"name": "Saisi", "ca_n1": "1,5 M€", "qualifications": [{"name": "Qualibat 1312", "detail": "Gros œuvre"}, None, "RGE"],
                               "departement": "29, 56", "effectif": "12 salariés"})
    assert saisi["kind"] == "saisi" and saisi["verified"] is False
    assert saisi["ca_n1"] == 1500000.0 and saisi["effectif"] == 12
    assert saisi["qualifications"] == ["Qualibat 1312 Gros œuvre", "RGE"] and saisi["departements"] == ["29", "56"]
    assert member_capacities({"postal_code": "20100"})["departements"] == ["2A"]
    assert member_capacities(None)["name"] == "Partenaire"


def test_robustesse_donnees_sales_jamais_d_exception():
    r = score_groupement(None, None, None, [{"kind": "x", "ca_n1": "n/a", "qualifications": None, "departement": 29},
                                            "pas un dict", {"name": None}])
    assert r["decision"] in ("go", "go_groupement", "a_etudier", "no_go")
    assert 0 <= r["score_groupement"] <= 100 and 0 <= r["score_seul"] <= 100
    assert gaps_for(None, None, None) == []
    assert auto_alliance({}, {}, {}, [None, "x", {}], max_partners="3")["chosen"] == []
    assert cumulate([], "chaque membre")["cumul_admis"] is False
