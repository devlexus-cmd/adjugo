"""
Rédaction, vague 1 — cohérence d'ensemble après la fusion du socle 0 (chantier S) et de la
grille « Comment vous serez noté » (chantier C).

 • la carte de la grille ne réintroduit aucune promesse retirée par le socle 0 (« Aucune
   invention », « sourcé », « Rien n'est deviné », « vérifié ») et parle de « dossier de
   présentation » ;
 • une seule façon d'afficher les critères : la carte de la grille. La liste brute proposée
   par l'IA, aux poids jamais contrôlés, ne sort plus vers les partenaires ;
 • les deux moteurs de rédaction ne reçoivent que des poids écrits dans le règlement :
   le dossier de présentation (moteur A) prend le plan de la grille, ses noms de salariés
   masqués ; le moteur du savoir-faire (moteur B) passe les critères de l'IA par la grille.
Aucun appel réseau : le client IA est simulé.
"""
import json
import os
import re

from app.services import grille_notation as gn
from app.services import llm
from tests.test_redaction_socle0 import NOMS, TEAM, _company, _db, _memoire_answer, _user_id, fake_llm  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
      "Valeur technique : 60 %\nPrix : 40 %\nLe mémoire technique ne devra pas excéder 8 pages.\n")
# Proposition de l'IA : deux critères bien recopiés, un troisième au poids inventé (absent du texte).
PROPOSES = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"},
            {"critere": "Délai d'intervention", "ponderation": "25 %", "extrait": "Délai d'intervention : 25 %"}]


def _static(name):
    with open(os.path.join(ROOT, "app", "static", name), encoding="utf-8") as f:
        return f.read()


def _between(s, a, b):
    i = s.index(a)
    return s[i:s.index(b, i)]


def _tips(html):
    return " ".join(re.findall(r'<span class="tip-b" role="tooltip">(.*?)</span>', html, flags=re.S))


PROMESSES = ("Aucune invention", "Rien n'est deviné", "sourcé", "vérifié", "garanti", "100 %", "sans erreur")


# ── La carte « Comment vous serez noté » ne promet rien ─────────────────────────────

def test_carte_de_la_grille_sans_promesse_et_bon_vocabulaire():
    html, js, inv = _static("app.html"), _static("app.js"), _static("invite.html")
    chef = _between(html, "<!-- Comment vous serez noté — la grille", "<!-- Répondre à plusieurs ?")
    part = _between(html, "<!-- Comment vous serez noté : la même grille", "<!-- Pourquoi vous dans ce groupement")
    comp = _between(js, '__adjApp.component("grille-carte"', "// ── Réseau de partenaires (vague 3)")
    page = _between(inv, "function renderGrille", "function renderMonAO")
    for zone in (chef, part, comp, page):
        for mot in PROMESSES:
            assert mot not in zone, f"« {mot} » réintroduit dans la carte de la grille"
    # Les bulles disent ce qui est contrôlé, et que le règlement fait foi.
    for zone in (_tips(chef), _tips(part), page):
        assert "écrit tel quel dans cette phrase" in zone and "le règlement fait foi" in zone.lower()
    assert "dossier de présentation (le « mémoire technique »)" in _tips(chef)
    assert "Un repérage peut en manquer" in comp and "Un repérage peut en manquer" in page


# ── Une seule façon d'afficher les critères : la carte ────────────────────────────────

def test_les_criteres_ne_sortent_que_par_la_grille():
    from app.routers.invites import _safe_analysis
    details = {"intitule_marche": "Couverture", "acheteur": "Commune",
               "criteres_attribution": [{"critere": "Prix", "ponderation": "70 %"}]}
    out = _safe_analysis({"details": details})
    assert "criteres_attribution" not in out and "grille_notation" not in out      # analyse ancienne
    out = _safe_analysis({"details": dict(details, grille_notation=gn.build_grille({"criteres_attribution": PROPOSES}, RC))})
    assert "criteres_attribution" not in out and [c["critere"] for c in out["grille_notation"]["criteres"]] == \
        ["Valeur technique", "Prix", "Délai d'intervention"]
    assert "70 %" not in json.dumps(out, ensure_ascii=False)
    # Côté écran : plus aucune ligne « Critères » brute, chez le chef de file comme chez le partenaire.
    js, inv = _static("app.js"), _static("invite.html")
    assert "criteres_attribution" not in js and "criteres_attribution" not in inv
    rows = _between(js, "detailRows(d) {", "clausesRisque(d)")
    assert "criter" not in rows


def test_poids_saisi_par_le_chef_de_file_dit_comme_tel_au_partenaire():
    g = gn.build_grille({"criteres_attribution": PROPOSES}, RC)
    d = next(x for x in g["criteres"] if x["critere"].startswith("Délai"))
    pub = gn.public_grille(gn.apply_choice(g, d["id"], "confirme", poids="20 %", when="2026-10-12T10:00:00"))
    row = next(x for x in pub["criteres"] if x["critere"].startswith("Délai"))
    assert row["poids"] == "20 %" and row["poids_saisi"] is True
    assert [x["poids_saisi"] for x in pub["criteres"] if x is not row] == [False, False]
    assert "(lu par le chef de file)" in _static("invite.html") and "x.poids_saisi === true" in _static("app.js")


# ── Moteur A : le dossier de présentation ne reçoit que le plan de la grille ──────────

def test_dossier_de_presentation_plan_de_la_grille_et_noms_masques(fake_llm):  # noqa: F811
    from app.services.agents import redaction as red
    g = gn.build_grille({"criteres_attribution": PROPOSES}, RC)
    assert next(x for x in g["criteres"] if x["critere"].startswith("Délai"))["statut"] == gn.A_VERIFIER
    fake = fake_llm(_memoire_answer("# Mémoire\n\n## Moyens humains\n[Chef de chantier 1] encadre le chantier."))
    out = red.build_dossier({"details": {"intitule_marche": "Couverture", "grille_notation": g,
                                         "criteres_attribution": PROPOSES}},
                            {"name": "Breizh Couverture", "team": TEAM}, [])
    sent = fake.sent()
    assert "Valeur technique (60 %) ; Prix (40 %)" in sent
    assert "Délai d'intervention" not in sent and "25 %" not in sent      # ligne à vérifier : hors du plan
    for nom in NOMS:
        assert nom not in sent, f"« {nom} » est parti à l'IA"
    assert "Yann Tanguy encadre le chantier." in out["memoire_markdown"]


def test_analyse_ancienne_sans_grille_aucun_poids_non_controle_a_l_ia(fake_llm):  # noqa: F811
    from app.services.agents import redaction as red
    fake = fake_llm(_memoire_answer("# Mémoire\n\nTexte."))
    red.build_dossier({"details": {"intitule_marche": "Couverture", "criteres_attribution": PROPOSES}},
                      {"name": "Solo SARL"}, [])
    sent = fake.sent()
    assert "Valeur technique; Prix; Délai d'intervention (poids non contrôlés" in sent
    assert "60 %" not in sent and "25 %" not in sent


# ── Moteur B : les critères de l'IA passent par la grille avant le plan et les sections ─

def test_moteur_savoir_faire_poids_controles_par_la_grille(client, auth, fake_llm):  # noqa: F811
    h = auth["headers"]
    _company(client, h)
    extraits = [{"intitule": c["critere"], "ponderation": c["ponderation"], "extrait": c["extrait"]} for c in PROPOSES]

    def answer(kw):
        system = llm._flatten_content(kw.get("system"))
        if "analyste de la commande publique" in system:
            return json.dumps({"objet": "Toiture", "criteres_attribution": extraits, "exigences": []}), "end_turn"
        if "SOMMAIRE" in system:
            return json.dumps({"sections": [{"titre": "Méthodologie", "objectif": "x", "requete": "méthodologie"}]}), "end_turn"
        if "contrôleur qualité" in system:
            return "{}", "end_turn"
        return "Notre méthodologie.", "end_turn"
    fake = fake_llm(answer)
    from app.services.agents.memoire import generate_memoire
    db = _db()
    try:
        out = generate_memoire(db, _user_id(auth["email"]), RC * 3)
    finally:
        db.close()
    plan_et_sections = "\n".join(
        llm._flatten_content(m.get("content")) for k in fake.calls
        if "analyste de la commande publique" not in llm._flatten_content(k.get("system"))
        for m in k.get("messages") or [])
    assert "Valeur technique (60 %)" in plan_et_sections and "Prix (40 %)" in plan_et_sections
    assert "25 %" not in plan_et_sections and "Délai d'intervention" not in plan_et_sections
    assert "?)" not in plan_et_sections
    assert out["criteres_attribution"] == [{"intitule": "Valeur technique", "ponderation": "60 %"},
                                           {"intitule": "Prix", "ponderation": "40 %"}]


def test_moteur_savoir_faire_sans_poids_ecrit_aucune_priorite_supposee():
    from app.services.agents.memoire import _criteres_controles, _grille_consigne
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères d'attribution\n"
          "Les offres seront jugées sur la valeur technique et sur le prix.\n")
    crit = _criteres_controles({"criteres_attribution": [{"intitule": "Valeur technique", "ponderation": ""},
                                                         {"intitule": "Prix", "ponderation": ""}]}, rc)
    assert [c["ponderation"] for c in crit] == ["", ""]
    txt = _grille_consigne(crit)
    assert "ne suppose aucune pondération ni aucun ordre" in txt and "?" not in txt
    assert "plus pondérés" not in txt
    assert _grille_consigne([]) == "" and _criteres_controles({}, "") == []
