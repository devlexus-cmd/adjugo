"""
Rédaction, vague 5 — chantier C2 complet (étude « rédaction » § 6.3) : « Comment vous serez noté » et ce
que le dossier DEMANDE. Contrat : docs/REDACTION_V5.md, section C2.

 1. sous-critères, pondérés ou non, TELS QU'ÉCRITS avec leur phrase, dans la grille et dans le plan de
    l'atelier (une partie par sous-critère, sous le titre de son critère) ;
 2. la liste des exigences (« le mémoire comprendra… », « le candidat devra… », « il est demandé… », les
    questions d'un cadre de réponse) repérée SANS IA, et les propositions de l'IA gardées seulement si leur
    phrase est retrouvée mot pour mot ; « 5 exigences traitées sur 6 » avec le nom de celle qui manque, par
    une règle EXPLICITE et testée ici, à la place de toute note de conformité ;
 3. l'environnement en information neutre ;
 4. l'avertissement R2142-21 (seul ET en groupement, plusieurs groupements) ;
 5. la phrase du règlement sur l'IA et le mode « sans IA » (aucun appel d'IA de rédaction, pour personne ;
    le contrôle des faits et la liste des exigences continuent) ;
 6. les questions à poser à l'acheteur, chacune avec sa phrase, et la date limite des questions ; Adjugo
    n'envoie rien ;
 7. la mesure de la décision 11 (dossiers qui imposent leur propre fichier de réponse).
Aucun appel réseau ; l'IA est simulée (et ses appels sont comptés : aucun ici n'en fait).
"""
import json
import re

import pytest

from app.services import atelier as at
from app.services import atelier_plan as ap
from app.services import grille_exigences as ge
from app.services import grille_notation as gn
from app.services import llm
from app.services.analysis import citation_guard
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _creer, _ecrire, _etat, _projet


def _g(text, criteres=None, **details):
    return gn.build_grille(dict(details, criteres_attribution=criteres or []), text)


def _crit(g, nom):
    return next(x for x in g["criteres"] if x["critere"] == nom)


def _toutes_les_phrases(g):
    """Chaque phrase affichée par la vague 5 (sous-critères, exigences, lieux, avertissements, questions)."""
    out = []
    for ln in g["criteres"]:
        out += [x["phrase"] for x in ln.get("sous_criteres") or []]
    out += [x["phrase"] for x in (g.get("exigences") or {}).get("liste") or []]
    out += [x["phrase"] for x in (g.get("environnement") or {}).get("lieux") or []]
    out += [x["phrase"] for x in (g.get("candidatures_multiples") or {}).get("messages") or []]
    out += [x["phrase"] for x in (g.get("ia") or {}).get("phrases") or []]
    for q in (g.get("questions_acheteur") or {}).get("liste") or []:
        out += [x["phrase"] for x in q["phrases"]]
    dl = (g.get("questions_acheteur") or {}).get("date_limite")
    if dl:
        out.append(dl["phrase"])
    return out


@pytest.fixture
def ia_comptee(monkeypatch):
    """Toute tentative d'appel à l'IA est comptée (aucune n'est permise dans ces parcours sans IA)."""
    appels = []

    def refus(*a, **k):
        appels.append(k.get("tache") or "?")
        raise AssertionError("appel à l'IA interdit ici")
    monkeypatch.setattr(llm, "messages_create", refus)
    return appels


# ═══ 1. Les sous-critères, tels qu'écrits ════════════════════════════════════════════════════════════

RC_SOUS = ("REGLEMENT DE LA CONSULTATION\n"
           "Article 8 - Critères de jugement des offres : Valeur technique 60 % appréciée au vu du mémoire technique ; "
           "Prix 40 %.\n"
           "Sous-critère 1 : méthodologie 30 points ; Sous-critère 2 : moyens humains et matériels 20 points ; "
           "Sous-critère 3 : démarche environnementale 10 points.\n"
           "Article 9 - Présentation des offres\n")
CRIT_SOUS = [{"critere": "Valeur technique", "ponderation": "60 %",
              "extrait": "Valeur technique 60 % appréciée au vu du mémoire technique"},
             {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix 40 %."}]


def test_sous_criteres_explicites_rattaches_a_leur_critere_par_leur_somme():
    """Écrits après « Prix 40 % » mais pesant 60 points au total : ils sont à la valeur technique (60 %)."""
    g = _g(RC_SOUS, CRIT_SOUS)
    vt, prix = _crit(g, "Valeur technique"), _crit(g, "Prix")
    assert [(x["critere"], x["poids"]) for x in vt["sous_criteres"]] == [
        ("méthodologie", "30 points"), ("moyens humains et matériels", "20 points"), ("démarche environnementale", "10 points")]
    assert prix.get("sous_criteres") == []
    assert all(x["statut"] == gn.RETROUVE and x["origine"] == "reperage" for x in vt["sous_criteres"])
    assert vt["controle_sous"]["statut"] == "ok"
    assert [x["id"] for x in vt["sous_criteres"]] == [vt["id"] + ".1", vt["id"] + ".2", vt["id"] + ".3"]
    for ph in _toutes_les_phrases(g):
        assert ph and citation_guard(RC_SOUS, ph, min_len=4), ph


def test_sous_criteres_numerotes_liste_annoncee_et_tableau():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères d'attribution\n"
          "2. Valeur technique : 60 points\n"
          "2.1 Organisation du chantier en site occupé : 25 points\n"
          "2.2 Moyens affectés : 20 points\n"
          "2.3 Gestion des déchets : 15 points\n"
          "3. Délai d'exécution : 10 points\n"
          "Le délai est apprécié selon les éléments suivants :\n"
          "- le planning détaillé\n"
          "- les mesures prises en cas d'intempéries\n"
          "Article 7 - Remise des offres\n")
    g = _g(rc, [{"critere": "Valeur technique", "ponderation": "60 points", "extrait": "2. Valeur technique : 60 points"},
                {"critere": "Délai d'exécution", "ponderation": "10 points", "extrait": "3. Délai d'exécution : 10 points"}])
    vt, delai = _crit(g, "Valeur technique"), _crit(g, "Délai d'exécution")
    assert [(x["critere"], x["poids"]) for x in vt["sous_criteres"]] == [
        ("Organisation du chantier en site occupé", "25 points"), ("Moyens affectés", "20 points"),
        ("Gestion des déchets", "15 points")]
    # Liste annoncée par « apprécié selon les éléments suivants : » : des sous-critères SANS poids, jamais un poids inventé.
    assert [(x["critere"], x["poids"]) for x in delai["sous_criteres"]] == [
        ("le planning détaillé", ""), ("les mesures prises en cas d'intempéries", "")]
    tab = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères de jugement des offres\n"
           "Critère | Pondération\nValeur technique | 60 %\nMéthodologie | 40 %\nMoyens humains | 20 %\nPrix | 40 %\n")
    g2 = _g(tab, [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique | 60 %"},
                  {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix | 40 %"}])
    # Lignes de tableau pondérées sans marque : retenues parce que leur somme fait le poids du critère.
    assert [(x["critere"], x["poids"]) for x in _crit(g2, "Valeur technique")["sous_criteres"]] == [
        ("Méthodologie", "40 %"), ("Moyens humains", "20 %")]


def test_sous_criteres_pas_de_faux_positif():
    """« sous-critères 1.1 à 1.5 » est un renvoi ; « le mémoire comprendra : - … » est une liste d'exigences ;
    des lignes pondérées dont la somme ne fait pas le poids du critère ne sont rien."""
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n"
          "1.1 Méthodologie : 25 %.\n1.2 Organisation : 15 %.\n2. Prix des prestations : 60 %.\n"
          "Les sous-critères 1.1 à 1.2 forment la valeur technique, appréciée au vu du mémoire technique.\n"
          "Le mémoire comprendra :\n- la méthodologie proposée ;\n- le planning.\n"
          "Article 8 - Remise des offres\n")
    g = _g(rc, [{"critere": "Méthodologie", "ponderation": "25 %", "extrait": "1.1 Méthodologie : 25 %."},
                {"critere": "Organisation", "ponderation": "15 %", "extrait": "1.2 Organisation : 15 %."},
                {"critere": "Prix des prestations", "ponderation": "60 %", "extrait": "2. Prix des prestations : 60 %."}])
    assert all(ln.get("sous_criteres") == [] for ln in g["criteres"]), [ln.get("sous_criteres") for ln in g["criteres"]]
    assert [x["texte"] for x in g["exigences"]["liste"]] == ["la méthodologie proposée", "le planning"]


def test_sous_criteres_proposes_par_l_ia_controles_contre_le_texte():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères de jugement des offres\n"
          "La valeur technique (60 %) est notée au regard de la méthodologie (35 %) et des moyens (25 %).\n"
          "Prix : 40 %\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %",
             "extrait": "La valeur technique (60 %) est notée au regard de la méthodologie (35 %) et des moyens (25 %).",
             "sous_criteres": [
                 {"critere": "Méthodologie", "ponderation": "35 %", "extrait": "au regard de la méthodologie (35 %)"},
                 {"critere": "Moyens", "ponderation": "30 %", "extrait": "et des moyens (25 %)"},       # poids faux
                 {"critere": "Sécurité", "ponderation": "10 %", "extrait": "et de la sécurité (10 %)"}]},   # inventé
            {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}]
    vt = _crit(_g(rc, crit), "Valeur technique")
    sc = {x["critere"]: x for x in vt["sous_criteres"]}
    assert "Sécurité" not in sc                                        # phrase introuvable : jamais affiché
    assert sc["Méthodologie"]["poids"] == "35 %" and sc["Méthodologie"]["statut"] == gn.RETROUVE
    assert sc["Moyens"]["poids"] == "" and sc["Moyens"]["statut"] == gn.A_VERIFIER   # 30 % n'est pas écrit
    assert "30 %" not in json.dumps(gn.public_grille(_g(rc, crit)), ensure_ascii=False)
    # Dans le plan : une partie par sous-critère retrouvé ; « poids à vérifier » n'y entre pas comme poids.
    plan = ap.build_plan({"details": {"grille_notation": _g(rc, crit)}})
    assert [(s["intitule"], s["question"].startswith("La valeur technique")) for s in plan["sections"]] == [
        ("Méthodologie", True), ("Moyens", True)]
    assert "30 %" not in json.dumps(plan, ensure_ascii=False)


def test_sous_criteres_a_nombres_sans_unite_seulement_si_leur_somme_fait_le_critere():
    """« Méthodologie (20) ; moyens humains et matériels (15) ; démarche environnementale (10) » sous une
    valeur technique à 45 % : des poids tels qu'écrits (« 20 »), parce que leur somme fait 45."""
    rc = ("REGLEMENT DE LA CONSULTATION\n5. Critères d'attribution des offres\nCritère\nPondération\nSous-critères\n"
          "Valeur technique\n45 %\nMéthodologie (20) ; moyens humains et matériels (15) ; démarche environnementale (10)\n"
          "Prix des prestations\n55 %\n")

    def crit(p3):
        return [{"critere": "Valeur technique", "ponderation": "45 %", "extrait": "Valeur technique\n45 %",
                 "sous_criteres": [{"critere": "Méthodologie", "ponderation": "20", "extrait": "Méthodologie (20)"},
                                   {"critere": "Moyens humains et matériels", "ponderation": "15",
                                    "extrait": "moyens humains et matériels (15)"},
                                   {"critere": "Démarche environnementale", "ponderation": p3,
                                    "extrait": "démarche environnementale (10)"}]},
                {"critere": "Prix des prestations", "ponderation": "55 %", "extrait": "Prix des prestations\n55 %"}]
    vt = _crit(_g(rc, crit("10")), "Valeur technique")
    assert [(x["critere"], x["poids"], x["statut"]) for x in vt["sous_criteres"]] == [
        ("Méthodologie", "20", gn.RETROUVE), ("Moyens humains et matériels", "15", gn.RETROUVE),
        ("Démarche environnementale", "10", gn.RETROUVE)]
    assert vt["controle_sous"]["statut"] == "ok"
    # Un poids annoncé qui n'est pas celui écrit : la somme ne tombe plus juste, aucun nombre nu n'est retenu.
    vt2 = _crit(_g(rc, crit("12")), "Valeur technique")
    assert all(x["poids"] == "" and x["statut"] == gn.A_VERIFIER for x in vt2["sous_criteres"])


def test_controle_des_sous_criteres_et_vue_des_partenaires():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères de jugement des offres\n"
          "Valeur technique : 60 points\nSous-critère 1 : méthodologie 30 points ;\nSous-critère 2 : moyens 20 points.\n"
          "Prix : 40 points\n")
    g = _g(rc, [{"critere": "Valeur technique", "ponderation": "60 points", "extrait": "Valeur technique : 60 points"},
                {"critere": "Prix", "ponderation": "40 points", "extrait": "Prix : 40 points"}])
    cs = _crit(g, "Valeur technique")["controle_sous"]
    assert cs["statut"] == "ecart" and "50 points" in cs["message"] and "60 points" in cs["message"]
    q = [x for x in g["questions_acheteur"]["liste"] if x["code"] == "total_sous"]
    assert q and "font 50 points au total" in q[0]["question"] and q[0]["phrases"]
    pub = gn.public_grille(g)
    vt = next(x for x in pub["criteres"] if x["critere"] == "Valeur technique")
    assert [x["critere"] for x in vt["sous_criteres"]] == ["méthodologie", "moyens"]
    assert vt["controle_sous"]["statut"] == "ecart"
    assert "questions_acheteur" not in pub                             # le chef de file pose les questions


# ═══ 1 bis. Le plan de l'atelier suit les sous-critères ══════════════════════════════════════════════

def _plan_grille(lignes):
    return ap.build_plan({"details": {"grille_notation": {"criteres": lignes,
                                                           "contraintes": {"fichier_impose": False, "limites": []}}}})


def _ln(i, nom, poids, subs=()):
    return {"id": f"c{i}", "critere": nom, "dans_le_plan": True, "poids_retenu": poids, "phrase": nom,
            "statut": gn.RETROUVE,
            "sous_criteres": [{"id": f"c{i}.{k}", "critere": n, "poids": p, "phrase": f"{n} : {p}",
                               "statut": gn.RETROUVE} for k, (n, p) in enumerate(subs, 1)]}


def test_plan_une_partie_par_sous_critere_sous_le_titre_du_critere():
    plan = _plan_grille([_ln(1, "Valeur technique", "60 %", [("Méthodologie", "30 %"), ("Moyens", "20 %"),
                                                             ("Environnement", "10 %")]),
                         _ln(2, "Délai d'exécution", "10 %"), _ln(3, "Prix", "30 %")])
    assert plan["source"] == ap.GRILLE and plan["message"] == ap.MSG_GRILLE_SOUS
    assert [(s["numero"], s["intitule"]) for s in plan["sections"]] == [
        ("1.1", "Méthodologie"), ("1.2", "Moyens"), ("1.3", "Environnement"), ("2", "Délai d'exécution")]
    s1 = plan["sections"][0]
    assert s1["parents"] == [{"numero": "1", "intitule": "Valeur technique"}]
    assert (s1["critere"], s1["critere_id"], s1["poids"], s1["partie_de_critere"]) == ("Valeur technique", "c1", "60 %", False)
    assert s1["question"] == "Méthodologie : 30 %"                     # la phrase du sous-critère
    # Un seul critère technique, découpé par le règlement lui-même : ses sous-critères, pas un plan d'Adjugo.
    p1 = _plan_grille([_ln(1, "Valeur technique", "60 %", [("Méthodologie", "30 %"), ("Moyens", "30 %")]),
                       _ln(2, "Prix", "40 %")])
    assert [s["intitule"] for s in p1["sections"]] == ["Méthodologie", "Moyens"]
    assert not any(s["partie_de_critere"] for s in p1["sections"]) and "sous-critères" in p1["message"]
    # Un seul sous-critère : pas de découpage.
    p2 = _plan_grille([_ln(1, "Valeur technique", "60 %", [("Méthodologie", "30 %")]), _ln(2, "Délai", "10 %")])
    assert [s["intitule"] for s in p2["sections"]] == ["Valeur technique", "Délai"]


def _rc_sous_criteres():
    return ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
            "1. Valeur technique : 60 %\n1.1 Méthodologie d'intervention : 40 %\n1.2 Moyens affectés au chantier : 20 %\n"
            "2. Prix : 40 %\nArticle 8 - Présentation\nLe candidat devra présenter les mesures de sécurité du chantier.\n")


def test_atelier_parties_des_sous_criteres_numeros_titres_et_export(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    rc = _rc_sous_criteres()
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        det = {"intitule_marche": "Toiture", "criteres_attribution": [
            {"critere": "Valeur technique", "ponderation": "60 %", "extrait": "1. Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "2. Prix : 40 %"}]}
        det["grille_notation"] = gn.build_grille(det, rc)
        p.ai_analysis = {"summary": "x", "dce_available": True, "details": det}
        db.commit()
    finally:
        db.close()
    st = _creer(client, h, pid, base="grille")
    secs = st["sections"]
    assert [(s["numero_affiche"], s["intitule"]) for s in secs] == [("1.1", "Méthodologie d'intervention"),
                                                                    ("1.2", "Moyens affectés au chantier")]
    assert secs[0]["parents"] == [{"numero": "1", "intitule": "Valeur technique"}]
    assert secs[0]["sous_critere"] == {"critere": "Méthodologie d'intervention", "poids": "40 %",
                                       "phrase": "1.1 Méthodologie d'intervention : 40 %"}
    assert secs[0]["critere"] == "Valeur technique" and secs[0]["poids"] == "60 %"
    # Le fichier Word : le titre du critère au-dessus de ses sous-critères, une seule fois.
    db = _db()
    try:
        d = at.get_dossier(db, pid, _owner(db, pid))
        sections = at.sections_actives(db, d)
        ctx = at.contexte_rendu(db, db.get(Project, pid), d, sections, {})
    finally:
        db.close()
    from app.services import atelier_export as ax
    rendu = ax.plan_rendu(ctx["sections"])
    assert [(k, n, t if k == "titre" else t["intitule"]) for k, n, t in rendu] == [
        ("titre", 1, "1. Valeur technique"), ("section", 2, "Méthodologie d'intervention"),
        ("section", 2, "Moyens affectés au chantier")]


def _owner(db, pid):
    from app.models import Project
    return db.get(Project, pid).user_id


def test_consigne_de_l_ia_dit_le_sous_critere_jamais_un_decoupage_d_adjugo():
    from app.services.agents import memoire as moteur
    c = moteur._consigne_partie({"titre": "Méthodologie", "critere": "Valeur technique", "poids": "60 %",
                                 "poids_source": "reglement", "partie_de_critere": False, "source_plan": "grille",
                                 "question": "1.1 Méthodologie : 40 %",
                                 "sous_critere": {"critere": "Méthodologie", "poids": "40 %", "phrase": "1.1 Méthodologie : 40 %"}})
    assert "SOUS-CRITÈRE DE L'ACHETEUR : Méthodologie (poids écrit dans le règlement : 40 %)" in c
    assert "découpage proposé par Adjugo" not in c
    c2 = moteur._consigne_partie({"titre": "Valeur technique", "critere": "Valeur technique", "poids": "60 %",
                                  "poids_source": "reglement", "source_plan": "cadre", "question": "Q",
                                  "sous_criteres": [{"critere": "Méthodologie", "poids": "40 %"},
                                                    {"critere": "Moyens", "poids": ""}]})
    assert "SOUS-CRITÈRES NOTÉS : Méthodologie (40 %) ; Moyens (aucun poids écrit)" in c2


# ═══ 2. Les exigences, repérées sans IA, et la règle « traitée » ═════════════════════════════════════

RC_EX = ("REGLEMENT DE LA CONSULTATION\n"
         "Article 2 - Conditions de participation\n"
         "Le candidat justifie d'une qualification Qualibat 3212.\n"
         "Article 5 - Contenu de l'offre\n"
         "Le mémoire technique comprendra :\n"
         "- la méthodologie d'intervention proposée ;\n"
         "- les moyens humains et matériels affectés au chantier ;\n"
         "- un planning prévisionnel détaillé.\n"
         "Le candidat devra présenter les mesures prises pour limiter les nuisances sonores à proximité de l'école.\n"
         "Il est demandé au candidat de préciser son organisation pour la gestion des déchets.\n"
         "Une attention particulière sera portée à la propreté des abords.\n"
         "Le mémoire comportera au maximum 10 pages.\n"
         "Le candidat devra fournir un extrait Kbis et les attestations d'assurance.\n"
         "Le candidat retenu devra fournir les attestations sociales.\n"
         "Le candidat peut joindre une plaquette de présentation.\n"
         "Le candidat n'est pas tenu de présenter des références.\n"
         "Le candidat devra obligatoirement utiliser le cadre de réponse joint.\n"
         "Le titulaire devra évacuer les déchets chaque soir.\n")
CADRE_EX = ("CADRE DE REPONSE TECHNIQUE\n1. Encadrement\nPrésentez l'encadrement du chantier (2 pages maximum).\n"
            "2. Sécurité\nDécrivez les protections collectives mises en place.\n")


def _texte_dossier():
    return "=== 01 RC.pdf ===\n" + RC_EX + "\n=== 02 Cadre de reponse technique.docx ===\n" + CADRE_EX


def test_exigences_reperees_avec_leur_phrase_et_rien_d_autre():
    t = _texte_dossier()
    g = _g(t)
    ex = g["exigences"]["liste"]
    assert [x["texte"] for x in ex] == [
        "la méthodologie d'intervention proposée", "les moyens humains et matériels affectés au chantier",
        "un planning prévisionnel détaillé",
        "les mesures prises pour limiter les nuisances sonores à proximité de l'école",
        "préciser son organisation pour la gestion des déchets",
        "la propreté des abords",
        "l'encadrement du chantier (2 pages maximum)", "les protections collectives mises en place"]
    assert all(x["origine"] == ge.REPERAGE for x in ex)
    assert ex[0]["intro"] == "Le mémoire technique comprendra :"
    assert ex[-1]["source"].startswith("Cadre de réponse")
    for x in ex:
        assert citation_guard(t, x["phrase"], min_len=4), x["phrase"]
    tout = json.dumps(ex, ensure_ascii=False)
    for absent in ("Qualibat", "Kbis", "attestations", "plaquette", "références", "10 pages.", "cadre de réponse joint",
                   "chaque soir"):
        assert absent not in tout, absent
    assert g["exigences"]["compteurs"]["total"] == 8


def test_questions_du_cadre_numerotees_ou_en_liste():
    t = ("=== Cadre de reponse technique.docx ===\nCADRE DE REPONSE TECHNIQUE\n"
         "2.1 Décrivez votre méthode de pose des membranes.\n- Précisez les contrôles d'étanchéité réalisés.\n"
         "Question 3 : Indiquez les délais de livraison des matériaux.\n"
         "Le candidat retrouvera ci-dessous les informations utiles. Décrire ne suffit pas toujours.\n")
    ex = [x["texte"] for x in _g(t)["exigences"]["liste"]]
    assert ex == ["votre méthode de pose des membranes", "les contrôles d'étanchéité réalisés",
                  "les délais de livraison des matériaux"], ex
    # « Chaque candidat présente une offre conforme » ne demande rien de précis au mémoire.
    assert _g("REGLEMENT DE LA CONSULTATION\nChaque candidat présente une offre conforme au cahier des charges.\n"
              )["exigences"]["liste"] == []


def test_exigences_proposees_par_l_ia_seulement_si_leur_phrase_est_retrouvee():
    t = _texte_dossier() + "\nLa réduction des trajets des véhicules est à exposer dans l'offre.\n"
    g = _g(t, exigences_memoire=[
        "La réduction des trajets des véhicules est à exposer dans l'offre.",            # hors des motifs : l'IA l'a vue
        "Le candidat garantira un taux de valorisation des déchets de 95 %.",          # inventée : rejetée
        "Le candidat devra fournir un extrait Kbis et les attestations d'assurance.",  # administratif : écartée
        {"extrait": "Il est demandé au candidat de préciser son organisation pour la gestion des déchets."}])  # déjà là
    ex = g["exigences"]["liste"]
    ia = [x for x in ex if x["origine"] == ge.IA]
    assert [x["phrase"] for x in ia] == ["La réduction des trajets des véhicules est à exposer dans l'offre."]
    assert ia[0]["texte"] == "La réduction des trajets des véhicules est à exposer dans l'offre"   # tiré de la phrase
    assert "95 %" not in json.dumps(g, ensure_ascii=False)
    assert sum(1 for x in ex if "gestion des déchets" in x["phrase"]) == 1           # jamais en double


def test_regle_traitee_explicite():
    """La règle : mots principaux de l'exigence (hors mots vides et mots de toute exigence) ; tous s'il y en a
    un ou deux, sinon la moitié et au moins deux ; les « [À compléter] » ne comptent pas ; la partie qui en
    reprend le plus l'emporte."""
    assert ge.cles("un planning prévisionnel détaillé") == ["plann", "previ"]
    assert ge.cles("le candidat devra présenter son mémoire technique") == []
    assert [ge.requis(k) for k in range(0, 7)] == [0, 1, 2, 2, 2, 3, 3]
    g = {"exigences": {"liste": [
        {"id": "e1", "texte": "un planning prévisionnel détaillé", "phrase": "p1"},
        {"id": "e2", "texte": "la gestion des déchets de chantier", "phrase": "p2"},
        {"id": "e3", "texte": "les mesures de réduction des nuisances sonores", "phrase": "p3"},
        {"id": "e4", "texte": "les références similaires", "phrase": "p4", "choix_utilisateur": {"choix": "traitee"}},
        {"id": "e5", "texte": "une plaquette commerciale", "phrase": "p5", "choix_utilisateur": {"choix": "ecarte"}}]}}
    parties = [{"id": 1, "titre": "1. Planning", "texte": "Le planning est joint. [À compléter : planning prévisionnel]"},
               {"id": 2, "titre": "2. Environnement", "texte": "Les déchets du chantier sont triés et la gestion suit le "
                                                             "plan. Les nuisances sont limitées."},
               {"id": 3, "titre": "3. Bruit", "texte": "Mesures contre les nuisances sonores : réduction des horaires."}]
    t = ge.traitement(g, parties)
    st = {x["id"]: x for x in t["liste"]}
    assert st["e1"]["statut"] == ge.A_TRAITER                          # « prévisionnel » n'est que dans un trou
    assert st["e2"]["statut"] == ge.TRAITEE and st["e2"]["partie"]["section_id"] == 2
    assert st["e3"]["statut"] == ge.TRAITEE and st["e3"]["partie"]["section_id"] == 3     # la meilleure partie
    assert st["e4"]["statut"] == ge.TRAITEE_SELON_VOUS
    assert st["e5"]["statut"] == ge.RETIREE
    assert (t["traitees"], t["total"]) == (3, 4)
    assert t["message"] == "3 exigences traitées sur 4"
    assert t["message_manque"] == "Il manque : « un planning prévisionnel détaillé »."
    assert "vérifi" not in json.dumps(t, ensure_ascii=False).lower()
    tout = ge.traitement(g, parties + [{"id": 4, "titre": "4", "texte": "Planning prévisionnel par phase."}])
    assert tout["message"] == "Les 4 exigences repérées sont traitées dans le dossier" and tout["message_manque"] == ""
    assert ge.message_traitement(1, 6) == "1 exigence traitée sur 6"


def test_choix_ajout_et_reprise_des_exigences():
    t = _texte_dossier()
    g = _g(t)
    g2 = ge.appliquer_choix(g, "exigence", "e6", "ecarte", when="2026-10-19")
    assert g2["exigences"]["compteurs"]["total"] == 7 and g2["exigences"]["compteurs"]["retirees"] == 1
    assert g["exigences"]["compteurs"]["total"] == 8                  # nouvelle grille : l'ancienne est intacte
    with pytest.raises(ValueError, match="ne retrouve pas"):
        ge.ajouter_exigence(g2, t, "Le candidat présentera une phrase qui n'est nulle part.")
    g3 = ge.ajouter_exigence(g2, t, "Le titulaire devra évacuer les déchets chaque soir.")
    u = g3["exigences"]["liste"][-1]
    assert (u["id"], u["origine"]) == ("u1", ge.UTILISATEUR) and citation_guard(t, u["phrase"])
    with pytest.raises(ValueError, match="déjà dans la liste"):
        ge.ajouter_exigence(g3, t, "Le titulaire devra évacuer les déchets chaque soir.")
    # Ré-analyse ou relecture : les choix et l'exigence ajoutée restent (sa phrase est toujours là).
    fresh = gn.relire(g3, {}, t)
    assert next(x for x in fresh["exigences"]["liste"] if x["id"] == "e6").get("choix_utilisateur", {}).get("choix") == "ecarte"
    assert any(x["origine"] == ge.UTILISATEUR for x in fresh["exigences"]["liste"])
    # Ré-analyse sans le texte du nouveau dossier : l'exigence ajoutée ne revient pas (sa phrase n'est plus
    # retrouvable), les choix sur les autres restent.
    fresh0 = gn.carry_over(g3, _g(t))
    assert not any(x["origine"] == ge.UTILISATEUR for x in fresh0["exigences"]["liste"])
    assert next(x for x in fresh0["exigences"]["liste"] if x["id"] == "e6")["choix_utilisateur"]["choix"] == "ecarte"
    # Phrase disparue du nouveau dossier : l'exigence ajoutée ne revient pas.
    fresh2 = gn.relire(g3, {}, t.replace("Le titulaire devra évacuer les déchets chaque soir.", ""))
    assert not any(x["origine"] == ge.UTILISATEUR for x in fresh2["exigences"]["liste"])


# ═══ 3, 4, 5. Environnement, candidatures multiples, intelligence artificielle ═════════════════════

def test_environnement_dans_la_note_seulement_s_il_compte():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères de jugement des offres\n"
          "Valeur technique : 50 %\nPerformance environnementale : 10 %\nPrix : 40 %\n")
    g = _g(rc, [{"critere": "Valeur technique", "ponderation": "50 %", "extrait": "Valeur technique : 50 %"},
                {"critere": "Performance environnementale", "ponderation": "10 %",
                 "extrait": "Performance environnementale : 10 %"},
                {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}])
    env = g["environnement"]
    assert env["dans_la_note"] is True and env["message"] == ge.MSG_ENV
    assert env["lieux"][0] == {"type": "critere", "libelle": "Performance environnementale", "poids": "10 %",
                               "phrase": "Performance environnementale : 10 %", "source": "Règlement de la consultation"}
    # Une clause d'exécution sur les déchets n'est pas « dans la note ».
    rc2 = ("REGLEMENT DE LA CONSULTATION\nArticle 6 - Critères de jugement des offres\nValeur technique : 60 %\n"
           "Prix : 40 %\nArticle 7 - Exécution\nLe titulaire trie les déchets du chantier.\n")
    g2 = _g(rc2, [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
                  {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}])
    assert g2["environnement"]["dans_la_note"] is False and g2["environnement"]["message"] == ""


@pytest.mark.parametrize("phrase,cle", [
    ("Les candidats ne peuvent pas présenter plusieurs offres en agissant à la fois en qualité de candidats "
     "individuels et de membres d'un ou plusieurs groupements.", "seul_et_groupement"),
    ("Il est interdit aux candidats de présenter plusieurs offres en agissant en qualité de membres de plusieurs "
     "groupements.", "plusieurs_groupements"),
    ("Un même opérateur économique ne peut pas être mandataire de plus d'un groupement pour un même marché.",
     "mandataire_unique"),
])
def test_candidatures_multiples_interdites_avec_la_phrase(phrase, cle):
    g = _g("REGLEMENT DE LA CONSULTATION\nArticle 3 - Groupements\n" + phrase + "\n")
    cm = g["candidatures_multiples"]
    assert cm[cle]["phrase"] == phrase
    assert [x["code"] for x in cm["messages"]] == [cle]
    assert "mandataire" not in cm["messages"][0]["message"].lower()      # le vocabulaire de l'écran : chef de file


def test_candidatures_multiples_permises_jamais_lues_comme_interdites():
    g = _g("REGLEMENT DE LA CONSULTATION\nL'acheteur n'interdit pas aux candidats de présenter plusieurs offres en "
           "agissant à la fois en qualité de candidats individuels et de membres d'un groupement.\n")
    assert g["candidatures_multiples"]["messages"] == []


@pytest.mark.parametrize("phrase,nature,message", [
    ("Le mémoire technique est rédigé sans recours à un système d'intelligence artificielle.", "interdit",
     ge.MSG_IA_INTERDIT),
    ("Le candidat indique s'il a utilisé un outil d'intelligence artificielle pour rédiger son offre.", "declarer",
     ge.MSG_IA_DECLARER),
    ("L'usage de l'intelligence artificielle dans la rédaction de l'offre fera l'objet d'un échange avec l'acheteur.",
     "mention", ge.MSG_IA_MENTION),
])
def test_mention_de_l_ia_phrase_et_nature(phrase, nature, message):
    g = _g("REGLEMENT DE LA CONSULTATION\nArticle 9 - Offre\n" + phrase + "\n")
    ia = g["ia"]
    assert ia["mentionne"] is True and ia["nature"] == nature and ia["message"] == message
    assert ia["phrases"][0]["phrase"] == phrase and ia["propose_sans_ia"] is True
    pub = gn.public_grille(g)["ia"]
    assert pub["message"] == ge.MSG_IA_PARTENAIRE and pub["phrases"] == [{"phrase": phrase}]
    if nature == "mention":                                           # aucune règle claire : une question proposée
        assert [q["code"] for q in g["questions_acheteur"]["liste"]] == ["ia"]
    assert not _g("REGLEMENT DE LA CONSULTATION\nArticle 9 - Offre\nLe mémoire décrit la méthode.\n")["ia"]["mentionne"]
    # Un marché qui ACHÈTE de l'intelligence artificielle ne parle pas de la rédaction de l'offre.
    assert not _g("REGLEMENT DE LA CONSULTATION\nArticle 1 - Objet\nLe marché porte sur un outil d'intelligence "
                  "artificielle pour l'accueil téléphonique.\n")["ia"]["mentionne"]


# ═══ 6. Questions à poser à l'acheteur ══════════════════════════════════════════════════════════════

def test_question_quand_les_poids_ne_font_pas_le_total_et_jamais_si_adjugo_a_pu_manquer_un_critere():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\nValeur technique : 60 %\n"
          "Prix : 30 %\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "30 %", "extrait": "Prix : 30 %"}]
    q = _g(rc, crit)["questions_acheteur"]
    assert [x["code"] for x in q["liste"]] == ["total_poids"]
    assert q["liste"][0]["question"] == ("Les poids des critères indiqués dans le règlement font 90 % au total, et non "
                                         "100 %. Pouvez-vous confirmer la pondération des critères ?")
    assert {p["phrase"] for p in q["liste"][0]["phrases"]} == {"Valeur technique : 60 %", "Prix : 30 %"}
    assert q["message"].startswith("Adjugo n'envoie rien")
    # Un troisième poids écrit dans la zone des critères que l'IA n'a pas proposé : pas de question à l'acheteur.
    rc2 = rc + "Délai : 10 %\n"
    assert [x["code"] for x in _g(rc2, crit)["questions_acheteur"]["liste"]] == []


def test_questions_cadre_absent_limites_visite_dates():
    rc = ("REGLEMENT DE LA CONSULTATION\n"
          "Le candidat devra impérativement compléter le cadre de réponse technique joint au dossier.\n"
          "Le mémoire ne devra pas excéder 10 pages.\nLe mémoire technique fera 15 pages maximum.\n"
          "La visite des lieux est obligatoire.\nLa visite du site est facultative.\n"
          "La date limite de remise des offres est fixée au 12/06/2026 à 12h00.\n"
          "Les offres devront être remises au plus tard le 15 juin 2026.\n")
    codes = [x["code"] for x in _g(rc)["questions_acheteur"]["liste"]]
    assert codes == ["cadre_absent", "limites", "visite", "date_remise"]
    q = {x["code"]: x for x in _g(rc)["questions_acheteur"]["liste"]}
    assert "10 pages et 15 pages" in q["limites"]["question"]
    assert "le 12/06/2026 et le 15/06/2026" in q["date_remise"]["question"]
    for x in q.values():
        assert x["phrases"] and all(citation_guard(rc, p["phrase"], min_len=4) for p in x["phrases"])
    # Un règlement modificatif reporte souvent la date : deux dates ne sont alors pas une contradiction.
    t = "=== RC modificatif n°1.pdf ===\n" + rc
    assert "date_remise" not in [x["code"] for x in _g(t)["questions_acheteur"]["liste"]]


def test_dates_de_remise_un_report_ou_une_date_de_candidature_ne_sont_pas_une_contradiction():
    rc = ("REGLEMENT DE LA CONSULTATION\nLa date limite de réception des candidatures est fixée au 02/06/2026.\n"
          "La date limite de remise des offres est fixée au 12/06/2026 à 12h00.\n")
    assert [d.isoformat() for d, _p, _s in ge.dates_remise(gn._pieces(rc))] == ["2026-06-12"]
    rc2 = ("REGLEMENT DE LA CONSULTATION\nLa date limite de remise des offres est fixée au 12/06/2026.\n"
           "La date limite de remise des offres, initialement fixée au 12/06/2026, est reportée au 19/06/2026.\n")
    assert "date_remise" not in [x["code"] for x in _g(rc2)["questions_acheteur"]["liste"]]


def test_date_limite_des_questions_ecrite_ou_calculee_et_dite_comme_telle():
    q = _g("REGLEMENT DE LA CONSULTATION\nLes questions sont posées sur la plateforme au plus tard le 05/06/2026 à "
           "12h00.\n")["questions_acheteur"]
    assert q["date_limite"]["date"] == "2026-06-05" and "écrite dans le règlement" in q["date_limite"]["message"]
    q2 = _g("REGLEMENT DE LA CONSULTATION\nLes demandes de renseignements doivent être adressées au plus tard 6 jours "
            "avant la date limite de remise des offres.\nLa date limite de remise des offres est fixée au 20/06/2026.\n"
            )["questions_acheteur"]
    dl = q2["date_limite"]
    assert dl["jours_avant"] == 6 and dl["date"] is None and dl["date_calculee"] == "2026-06-14"
    assert "calculée par Adjugo" in dl["message"] and "vérifiez-la" in dl["message"]
    q3 = _g("REGLEMENT DE LA CONSULTATION\nLes questions doivent être posées au plus tard 6 jours francs avant la date "
            "limite de remise des offres.\nLa date limite de remise des offres est fixée au 20/06/2026.\n")["questions_acheteur"]
    assert q3["date_limite"]["date_calculee"] is None                  # jours francs : aucun calcul
    # « Les réponses seront envoyées… » n'est pas la date limite des questions.
    q4 = _g("REGLEMENT DE LA CONSULTATION\nLes réponses aux questions seront envoyées au plus tard 6 jours avant la "
            "date limite.\n")["questions_acheteur"]
    assert q4["date_limite"] is None


def test_questions_proposees_par_l_ia_controlees():
    rc = ("REGLEMENT DE LA CONSULTATION\nLe délai d'exécution est de 5 mois.\n"
          "Le planning prévoit une durée de 6 mois.\n")
    g = _g(rc, questions_acheteur=[
        {"question": "Le délai d'exécution est-il de 5 mois ou de 6 mois ?",
         "extraits": ["Le délai d'exécution est de 5 mois.", "Le planning prévoit une durée de 6 mois."]},
        {"question": "Le délai est-il de 7 mois ?", "extraits": ["Le délai d'exécution est de 5 mois."]},   # 7 inventé
        {"question": "Quel est le budget ?", "extraits": ["Le budget est de 2 millions."]},               # phrase absente
        {"question": "Pas une question", "extraits": ["Le délai d'exécution est de 5 mois."]}])
    qs = g["questions_acheteur"]["liste"]
    assert [x["question"] for x in qs] == ["Le délai d'exécution est-il de 5 mois ou de 6 mois ?"]
    assert qs[0]["origine"] == ge.IA and len(qs[0]["phrases"]) == 2
    g2 = ge.appliquer_choix(g, "question", "q1", "ecarte")
    assert g2["questions_acheteur"]["liste"][0]["choix_utilisateur"]["choix"] == "ecarte"


# ═══ L'analyse : l'IA propose dans le MÊME appel, rien de plus n'est envoyé ═════════════════════════

def test_consigne_d_analyse_demande_les_propositions_avec_leur_phrase():
    from app.services import analysis as an
    for consigne in (an.SYSTEM_PROMPT, an.SYSTEM_EXTRACTION):
        assert '"sous_criteres"' in consigne and '"exigences_memoire"' in consigne and '"questions_acheteur"' in consigne
        assert "recopie LITTERALEMENT (300 caracteres maximum)" in consigne
    assert an.VERSION_CONSIGNES == "2"
    assert {"exigences_memoire", "questions_acheteur"} <= set(an._HORS_FAITS)   # jamais renvoyées à la partie entreprise
    p = an.build_entreprise_prompt({"summary": "s", "details": {"intitule_marche": "x", "exigences_memoire": ["EXIGENCE"],
                                                                "questions_acheteur": [{"question": "QUESTION ?"}]}})
    assert "EXIGENCE" not in p and "QUESTION ?" not in p


# ═══ Routes : choix, ajout, relecture — sans IA, dans l'organisation seulement ═══════════════════════

def _projet_v1(client, h):
    """Un marché analysé AVANT la vague 5 : grille sans sous-critères ni exigences (version 1)."""
    pid = _projet(client, h)
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        a = dict(p.ai_analysis)
        det = dict(a["details"])
        g = dict(det["grille_notation"])
        for k in ("exigences", "environnement", "candidatures_multiples", "ia", "questions_acheteur"):
            g.pop(k, None)
        g["version"] = 1
        det["grille_notation"] = g
        a["details"] = det
        p.ai_analysis = a
        db.commit()
    finally:
        db.close()
    return pid


def test_relire_un_marche_d_avant_sans_ia_et_garder_les_choix(client, auth, ia_comptee):
    h = auth["headers"]
    pid = _projet_v1(client, h)
    g0 = client.get(f"/api/projects/{pid}", headers=h).json()["ai_analysis"]["details"]["grille_notation"]
    assert "exigences" not in g0
    assert "exigences" not in gn.public_grille(g0)                     # les partenaires ne lisent pas « aucune »
    r = client.post("/api/sourcing/grille/choix", headers=h, json={"project_id": pid, "critere_id": "c2", "choix": "ecarte"})
    assert r.status_code == 200, r.text
    r = client.post("/api/sourcing/grille/relire", headers=h, json={"project_id": pid})
    assert r.status_code == 200, r.text
    g = r.json()["grille_notation"]
    assert g["version"] == gn.VERSION and g["relue_le"]
    assert [x["texte"] for x in g["exigences"]["liste"]] == [
        "l'encadrement du chantier (2 pages maximum)", "les compagnons affectés au chantier",
        "la méthodologie d'intervention en site occupé", "la gestion des déchets du chantier"]
    assert next(x for x in g["criteres"] if x["id"] == "c2")["choix_utilisateur"]["choix"] == "ecarte"
    assert ia_comptee == []
    # Enregistré sur le marché.
    g2 = client.get(f"/api/projects/{pid}", headers=h).json()["ai_analysis"]["details"]["grille_notation"]
    assert g2["exigences"]["compteurs"]["total"] == 4


def test_routes_element_et_exigence(client, auth, ia_comptee):
    h = auth["headers"]
    pid = _projet(client, h)
    r = client.post("/api/sourcing/grille/element", headers=h,
                    json={"project_id": pid, "type": "exigence", "element_id": "e1", "choix": "ecarte"})
    assert r.status_code == 200, r.text
    assert r.json()["grille_notation"]["exigences"]["compteurs"]["retirees"] == 1
    r = client.post("/api/sourcing/grille/element", headers=h,
                    json={"project_id": pid, "type": "exigence", "element_id": "e99", "choix": "ecarte"})
    assert r.status_code == 422 and "n'existe plus" in r.json()["detail"]
    r = client.post("/api/sourcing/grille/element", headers=h,
                    json={"project_id": pid, "type": "question", "element_id": "q1", "choix": "traitee"})
    assert r.status_code == 422                                        # une question n'est jamais « traitée »
    r = client.post("/api/sourcing/grille/exigence", headers=h,
                    json={"project_id": pid, "phrase": "Les entreprises devront être certifiées ISO 14001."})
    assert r.status_code == 200, r.text
    assert r.json()["grille_notation"]["exigences"]["liste"][-1]["origine"] == ge.UTILISATEUR
    r = client.post("/api/sourcing/grille/exigence", headers=h,
                    json={"project_id": pid, "phrase": "Le candidat proposera une visite virtuelle du chantier."})
    assert r.status_code == 422 and "ne retrouve pas" in r.json()["detail"]
    assert ia_comptee == []


def test_routes_de_la_grille_dans_l_organisation_seulement(client, auth):
    h = auth["headers"]
    pid = _projet(client, h)
    from tests.test_convention_groupement import _register
    autre, _email = _register(client)
    for chemin, corps in (("/api/sourcing/grille/element", {"type": "exigence", "element_id": "e1", "choix": "ecarte"}),
                          ("/api/sourcing/grille/exigence", {"phrase": "Les entreprises devront être certifiées ISO 14001."}),
                          ("/api/sourcing/grille/relire", {})):
        r = client.post(chemin, headers=autre, json=dict(corps, project_id=pid))
        assert r.status_code == 404, (chemin, r.status_code, r.text)


def test_routes_de_la_grille_refusees_a_la_demo(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    pid = next(p["id"] for p in client.get("/api/projects/", headers=h).json() if p["name"].startswith("Réfection toiture"))
    for chemin, corps in (("/api/sourcing/grille/element", {"type": "exigence", "element_id": "e1", "choix": "ecarte"}),
                          ("/api/sourcing/grille/exigence", {"phrase": "Le mémoire technique indique si le candidat a eu recours"}),
                          ("/api/sourcing/grille/relire", {})):
        r = client.post(chemin, headers=h, json=dict(corps, project_id=pid))
        assert r.status_code == 403 and r.json()["detail"].startswith("La démo est en lecture guidée"), (chemin, r.text)
    r = client.put(f"/api/atelier/{pid}/options", headers=h, json={"sans_ia": True})
    assert r.status_code == 403


# ═══ L'atelier : « n exigences traitées sur m », sans IA ═══════════════════════════════════════════

def test_atelier_exigences_traitees_avec_le_nom_de_celle_qui_manque(client, auth, ia_comptee):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    ex = st["exigences"]
    assert ex["disponible"] is True and (ex["traitees"], ex["total"]) == (0, 4)
    assert ex["message"] == "0 exigence traitée sur 4" and ex["message_manque"] == "Il en manque 4 : voir la liste."
    assert ex["regle"] == ge.REGLE_TRAITEE
    secs = {s["intitule"]: s for s in st["sections"]}
    _ecrire(client, h, pid, secs["Encadrement du chantier"], "L'encadrement du chantier est assuré par un conducteur.")
    _ecrire(client, h, pid, secs["Méthodologie"], "Notre méthodologie d'intervention en site occupé suit les horaires.")
    _ecrire(client, h, pid, secs["Démarche environnementale"], "La gestion des déchets du chantier : tri sur place.")
    ex = _etat(client, h, pid)["exigences"]
    assert ex["message"] == "3 exigences traitées sur 4"
    assert ex["message_manque"] == "Il manque : « les compagnons affectés au chantier »."
    traitee = next(x for x in ex["liste"] if x["texte"].startswith("la gestion des déchets"))
    assert traitee["statut"] == ge.TRAITEE and traitee["partie"]["titre"] == "3. Démarche environnementale"
    # « Je la traite déjà » : traitée selon vous (dit comme tel), le compte suit.
    manque = next(x for x in ex["liste"] if x["statut"] == ge.A_TRAITER)
    r = client.post("/api/sourcing/grille/element", headers=h,
                    json={"project_id": pid, "type": "exigence", "element_id": manque["id"], "choix": "traitee"})
    assert r.status_code == 200, r.text
    ex = _etat(client, h, pid)["exigences"]
    assert ex["message"] == "Les 4 exigences repérées sont traitées dans le dossier"
    assert next(x for x in ex["liste"] if x["id"] == manque["id"])["statut"] == ge.TRAITEE_SELON_VOUS
    # Jamais une note de conformité, jamais « vérifié ».
    blob = json.dumps(_etat(client, h, pid), ensure_ascii=False).lower()
    assert "conformit" not in blob and "vérifié" not in blob
    assert ia_comptee == []


def test_atelier_grille_d_avant_la_vague_5_le_dit(client, auth):
    h = auth["headers"]
    pid = _projet_v1(client, h)
    st = _creer(client, h, pid)
    assert st["exigences"]["disponible"] is False and st["exigences"]["message_ancien"] == at.MSG_EXIGENCES_ANCIENNES


# ═══ Le mode « sans IA » ═══════════════════════════════════════════════════════════════════════════

def test_mode_sans_ia_aucun_appel_d_ia_de_redaction_et_le_controle_continue(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    fake = fake_llm(lambda kw: ("Texte de l'IA.", "end_turn"))
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    assert st["sans_ia"]["actif"] is False
    r = client.put(f"/api/atelier/{pid}/options", headers=h, json={"sans_ia": True})
    assert r.status_code == 200, r.text
    assert r.json()["options"] == {"page_garde": True, "sommaire": True}          # contrat de la vague 2 inchangé
    assert r.json()["sans_ia"]["actif"] is True and r.json()["sans_ia"]["message"] == at.MSG_SANS_IA_ACTIF
    sec = st["sections"][0]
    for chemin in (f"/sections/{sec['id']}/rediger", "/rediger"):
        r = client.post(f"/api/atelier/{pid}{chemin}", headers=h, json={})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "mode_sans_ia", (chemin, r.text)
    out = _ecrire(client, h, pid, sec, "Nous sommes certifiés ISO 9001 et comptons 37 compagnons.")
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/raccourcir", headers=h, json={"cible_mots": 30})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mode_sans_ia"
    # Le contrôle des faits continue, sans IA : chaque fait du texte est relevé (ici vos déclarations).
    from app.models import DossierSectionVersion
    from app.services import faits_sources as fs
    db = _db()
    try:
        v = db.get(DossierSectionVersion, out["version_courante"]["id"])
        faits = list(v.faits or [])
    finally:
        db.close()
    assert len(faits) >= 2, faits                                       # ISO 9001, 37 compagnons
    assert all((f.get("source") or {}).get("type") == fs.T_VOUS for f in faits), faits      # « déclaré par vous »
    assert _etat(client, h, pid)["exigences"]["disponible"] is True
    assert fake.calls == []
    # Le choix tient (les options d'export ne l'effacent pas) et s'inscrit au journal.
    assert client.put(f"/api/atelier/{pid}/options", headers=h, json={"page_garde": False}).status_code == 200
    assert _etat(client, h, pid)["sans_ia"]["actif"] is True
    from app.models import AuditLog
    db = _db()
    try:
        acts = [a.detail for a in db.query(AuditLog).filter(AuditLog.project_id == pid,
                                                            AuditLog.action == "atelier.sans_ia").all()]
    finally:
        db.close()
    assert acts == ["mode sans IA activé"]
    # Revenir à l'aide de l'IA : de nouveau permis.
    assert client.put(f"/api/atelier/{pid}/options", headers=h, json={"sans_ia": False}).json()["sans_ia"]["actif"] is False


def test_mode_sans_ia_des_la_creation_et_phrase_du_reglement(client, auth):
    h = auth["headers"]
    pid = _projet(client, h)
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        a = dict(p.ai_analysis)
        det = dict(a["details"])
        texte = ("REGLEMENT DE LA CONSULTATION\nArticle 9 - Offre\nLe mémoire technique est rédigé sans recours à un "
                 "système d'intelligence artificielle.\n")
        det["grille_notation"] = gn.build_grille({}, texte)
        a["details"] = det
        p.ai_analysis = a
        db.commit()
    finally:
        db.close()
    prop = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert prop["dossier"] is None and prop["sans_ia"]["reglement"]["nature"] == "interdit"
    assert prop["sans_ia"]["reglement"]["phrases"][0]["phrase"].startswith("Le mémoire technique est rédigé sans recours")
    r = client.post(f"/api/atelier/{pid}", headers=h, json={"base": "auto", "sans_ia": True})
    assert r.status_code == 201, r.text
    assert r.json()["sans_ia"]["actif"] is True


def test_mode_sans_ia_vaut_pour_les_partenaires_et_l_harmonisation(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P, _groupement, _part_a
    fake = fake_llm(lambda kw: ("Texte.", "end_turn"))
    h = auth["headers"]
    pid, _st, a, _b, rep = _groupement(client, auth)
    assert client.put(f"/api/atelier/{pid}/options", headers=h, json={"sans_ia": True}).status_code == 200
    pa = P(client, a["token"])
    vue = pa.get().json()
    assert vue["sans_ia"] == {"actif": True, "message": at.MSG_SANS_IA_PARTENAIRE}
    sid = _part_a(vue["parties"])["section_id"]
    r = pa.post(f"/sections/{sid}/aide", {"action": "rediger"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mode_sans_ia", r.text
    r = client.post(f"/api/atelier/{pid}/repartition/harmoniser", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mode_sans_ia", r.text
    assert client.get(f"/api/atelier/{pid}/repartition", headers=h).json()["harmoniser"]["jonctions"] == 0
    assert fake.calls == []
    # Le partenaire lit les exigences du dossier d'après les textes COMMUNS seulement.
    assert vue["exigences"]["disponible"] is True and vue["exigences"]["total"] == 4
    assert all("source" not in x and "choix" not in x for x in vue["exigences"]["liste"])


# ═══ La démo : les nouveautés, sans IA ni réseau ══════════════════════════════════════════════════

def test_demo_exigences_traitees_ia_r2142_et_question(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    pid = next(p["id"] for p in client.get("/api/projects/", headers=h).json() if p["name"].startswith("Réfection toiture"))
    g = client.get(f"/api/projects/{pid}", headers=h).json()["ai_analysis"]["details"]["grille_notation"]
    assert g["version"] == gn.VERSION
    assert g["exigences"]["compteurs"]["total"] == 7
    assert g["environnement"]["dans_la_note"] is True
    assert [x["code"] for x in g["candidatures_multiples"]["messages"]] == ["seul_et_groupement"]
    assert g["ia"]["nature"] == "declarer"
    q = g["questions_acheteur"]
    assert q["date_limite"]["date"] == "2026-12-18" and len(q["liste"]) == 1 and q["liste"][0]["origine"] == ge.IA
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    ex = st["exigences"]
    assert ex["message"] == "5 exigences traitées sur 7"
    assert ex["message_manque"] == ("Il manque : « si le candidat a eu recours à un outil d'intelligence artificielle "
                                    "pour le rédiger », « un planning par phase, calé sur les vacances scolaires ».")
    assert st["sans_ia"]["actif"] is False and st["sans_ia"]["reglement"]["mentionne"] is True


# ═══ 7. Décision 11 : la mesure (agrégat, aucun contenu) ═══════════════════════════════════════════

def test_mesure_decision_11_agregat_sans_contenu_et_hors_demo(client, auth):
    from app.services.demo_seed import DEMO_EMAIL
    from app.models import Project, User
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if u is not None:
            assert db.query(Project).filter(Project.user_id == u.id, Project.dce_importe_le.isnot(None)).count() == 0
        m = at.mesure_fichier_impose(db)
    finally:
        db.close()
    assert set(m) == {"dossiers_importes", "fichier_impose", "part", "seuil_decision", "atteint", "message"}
    assert m["seuil_decision"] == 0.2
    assert isinstance(m["dossiers_importes"], int) and isinstance(m["fichier_impose"], int)
    r = client.get("/api/admin/mesures/redaction", headers=auth["headers"])
    assert r.status_code == 403                                       # administrateur de la plateforme seulement


# ═══ Écrans : français, zéro émoji, jamais « vérifié » ════════════════════════════════════════════

def test_textes_des_ecrans_et_des_messages():
    import pathlib
    static = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"
    js = (static / "app.js").read_text(encoding="utf-8")
    deb = js.index('__adjApp.component("grille-carte"')
    carte = js[deb:js.index("// ── Réseau de partenaires", deb)]
    html = (static / "app.html").read_text(encoding="utf-8")
    msgs = " ".join(v for k, v in vars(ge).items() if k.startswith("MSG_") and isinstance(v, str))
    msgs += " " + ge.REGLE_TRAITEE + " " + at.MSG_SANS_IA_ACTIF + " " + at.MSG_SANS_IA_REFUS + " " + at.MSG_SANS_IA_PARTENAIRE
    for t in (carte, msgs):
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t)
        assert "vérifié" not in t.lower() and "consortium" not in t.lower() and "signer" not in t.lower()
    assert "Ce que le dossier demande" in carte and "Questions à poser à l\\'acheteur" in carte
    assert "Adjugo n'envoie rien" in msgs
    assert "Rédiger ce dossier sans IA" in html and "atlSansIaChoisir(true)" in html
    assert 'v-if="!atlSansIa()"' in html                               # aucun bouton d'IA dans un dossier « sans IA »
