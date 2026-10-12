"""
Rédaction, vague 1 — cohérence d'ensemble après la fusion du socle 0 (chantier S) et de la
grille « Comment vous serez noté » (chantier C).

 • la carte de la grille ne réintroduit aucune promesse retirée par le socle 0 (« Aucune
   invention », « sourcé », « Rien n'est deviné », « vérifié ») et parle de « dossier de
   présentation » ;
 • une seule façon d'afficher les critères : la carte de la grille. La liste brute proposée
   par l'IA, aux poids jamais contrôlés, ne sort plus vers les partenaires ;
 • l'atelier (vague 2) ne reçoit que des poids écrits dans le règlement : son plan suit la
   grille contrôlée, les noms des salariés sont masqués ; le moteur du savoir-faire (fusion de
   groupement archivée) passe toujours les critères de l'IA par la grille.
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


# ── L'atelier (vague 2) : le plan suit la grille, l'IA ne reçoit que des poids écrits ──────
# Le moteur A (dossier complet en un appel) est retiré ; le moteur du savoir-faire est devenu le
# moteur de l'atelier, partie par partie. Ce qui était vérifié ici l'est désormais sur l'atelier.

def _atelier_redige(client, h, pid):
    import time
    st = client.post(f"/api/atelier/{pid}", headers=h, json={}).json()
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    for _ in range(200):
        j = client.get(f"/api/atelier/{pid}/taches/{r.json()['tache']['id']}", headers=h).json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    return st


def test_dossier_de_presentation_plan_de_la_grille_et_noms_masques(client, auth, fake_llm):  # noqa: F811
    from tests.test_redaction_socle0 import _project, _set_analysis
    h = auth["headers"]
    _company(client, h)
    g = gn.build_grille({"criteres_attribution": PROPOSES}, RC)
    assert next(x for x in g["criteres"] if x["critere"].startswith("Délai"))["statut"] == gn.A_VERIFIER
    pid = _project(client, h, "Couverture")
    _set_analysis(pid, {"details": {"intitule_marche": "Couverture", "grille_notation": g,
                                    "criteres_attribution": PROPOSES}})
    fake = fake_llm(_memoire_answer("[Chef de chantier 1] encadre le chantier."))
    st = _atelier_redige(client, h, pid)
    # Un seul critère technique retrouvé (le prix est jugé sur le bordereau) : découpage proposé,
    # chaque partie porte le critère et son poids TEL QU'ÉCRIT.
    assert st["dossier"]["plan_source"] == "grille"
    assert {(s["critere"], s["poids"]) for s in st["sections"]} == {("Valeur technique", "60 %")}
    sent = fake.sent()
    assert "CRITÈRE DE L'ACHETEUR : Valeur technique (poids écrit dans le règlement : 60 %)" in sent
    assert "Délai d'intervention" not in sent and "25 %" not in sent      # ligne à vérifier : hors du plan
    for nom in NOMS:
        assert nom not in sent, f"« {nom} » est parti à l'IA"
    texts = [s["version_courante"]["texte"] for s in client.get(f"/api/atelier/{pid}", headers=h).json()["sections"]]
    assert all("Yann Tanguy encadre le chantier." == t for t in texts)


def test_analyse_ancienne_sans_grille_aucun_poids_non_controle_a_l_ia(client, auth, fake_llm):  # noqa: F811
    from tests.test_redaction_socle0 import _project, _set_analysis
    h = auth["headers"]
    pid = _project(client, h, "Couverture ancienne")
    _set_analysis(pid, {"details": {"intitule_marche": "Couverture", "criteres_attribution": PROPOSES}})
    fake = fake_llm(_memoire_answer("Texte."))
    st = _atelier_redige(client, h, pid)
    assert st["dossier"]["plan_source"] == "libre" and all(s["poids"] == "" for s in st["sections"])
    sent = fake.sent()
    assert "60 %" not in sent and "25 %" not in sent and "Délai d'intervention" not in sent
    assert "CRITÈRE DE L'ACHETEUR" not in sent


def test_moteur_savoir_faire_poids_controles_par_la_grille():
    """Le plan de l'atelier ne vient jamais de l'IA : il est calculé sur la grille contrôlée."""
    from app.services import atelier_plan as ap
    g = gn.build_grille({"criteres_attribution": PROPOSES}, RC)
    plan = ap.build_plan({"details": {"grille_notation": g}})
    joined = json.dumps(plan, ensure_ascii=False)
    assert "25 %" not in joined and "?)" not in joined
    assert plan["criteres_hors_dossier"] == [{"critere": "Prix", "poids": "40 %", "raison": ap.MSG_PRIX}]


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
