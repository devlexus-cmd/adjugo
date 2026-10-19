"""
Rédaction, vague 5 — contre-relecture (C2 complet, D, E2 et leurs jointures). Chaque test reproduit une remarque
de la relecture et échouait sur la tête d'intégration (0277857). Contrat : docs/REDACTION_V5.md.

Aucun appel réseau (sources publiques simulées, transport HTTP coupé) ; l'IA est simulée.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from types import SimpleNamespace as NS

import pytest

from app.services import atelier as at
from app.services import dce_pieces as dp
from app.services import entretien_chantier as ec
from app.services import grille_exigences as ge
from app.services import grille_notation as gn
from app.services import llm
from app.services import sources_publiques as sp
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v5_e2 import ACH1, ACH2, SIRET, _org, _par_id, sources  # noqa: F401
from tests.test_redaction_v5_entretien import (_avec_partenaires, _entretien, _lancer_ia, _projet_chantier, _q,
                                               _rediger, _repondre, _version_db)

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static")


def _lire(nom):
    with open(os.path.join(STATIC, nom), encoding="utf-8") as f:
        return f.read()


def _rc(*lignes):
    return dp.header("01_Reglement_de_la_consultation.txt") + "\n" + "\n".join(lignes) + "\n"


def _crit(*xs):
    return [{"critere": c, "ponderation": w, "extrait": e} for c, w, e in xs]


# ═══ 1. Entretien : le thème d'une question de l'IA n'est jamais un fait « déclaré par vous » ════════

PHRASE_ZONES = "La couverture existante en zinc est déposée par zones successives."


def test_theme_ecrit_par_l_ia_jamais_dans_le_fait_declare_par_vous(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid, _st = _projet_chantier(client, h)
    _entretien(client, h, pid)
    items = [{"question": "Comment organisez-vous la dépose de la couverture par zones ?", "phrase": PHRASE_ZONES,
              "theme": "dépose avec 3 nacelles de 18 m"}]

    def ans(kw):
        if "Tu prépares l'entretien chantier" in llm._flatten_content(kw.get("system")):
            return json.dumps({"questions": items}, ensure_ascii=False), "end_turn"
        return "x", "end_turn"
    fake_llm(ans)
    assert _lancer_ia(client, h, pid)["result"]["ajoutees"] == 1
    e = _entretien(client, h, pid, preparer=False)
    qi = next(x for x in e["questions"] if x["origine"] == "ia")
    # Thème refusé (nombres absents de la phrase) : les mots de la question, sans sa tournure interrogative.
    assert qi["theme"] == "dépose de la couverture par zones" and "3" not in qi["a_completer"]
    _repondre(client, h, pid, qi, reponse="Par zones de 50 m², bâchées chaque soir.", lock_version=qi["lock_version"])
    sid, ref = qi["partie"]["section_id"], qi["ref"]
    fake_llm(lambda kw: (f"La dépose se fait par zones de 50 m² avec 3 nacelles de 18 m [{ref}].", "end_turn"))
    assert _rediger(client, h, pid, sid)["status"] == "done"
    faits = {f["fait"]: f for f in _version_db(sid)["faits"]}
    assert faits["50 m²"]["statut"] == "avec_source" and faits["50 m²"]["source"]["ref"] == ref
    for inv in ("3 nacelles", "18"):                         # écrits par l'IA : jamais « déclaré par vous »
        assert faits[inv]["statut"] == "a_relire" and not faits[inv].get("source"), faits[inv]


def test_theme_de_l_ia_hors_de_la_fiche_meme_accepte():
    """Même un thème accepté (sans nombre) n'entre pas dans le texte que le contrôle des faits rapproche ; le thème
    fixe de la banque, lui, y reste."""
    r = NS(theme="accès des engins de levage", question="Quel accès prévoyez-vous ?", reponse="Par la cour.",
           reponse_preuve_id=None, numero=4, origine=ec.IA)
    f = ec._fiche(r, {}, None)
    assert "engins" not in f.texte and f.texte.endswith(": Par la cour.")
    r.origine = ec.BANQUE
    assert "accès des engins de levage" in ec._fiche(r, {}, None).texte


# ═══ 2. Date limite des questions : un délai avant la date de REMISE n'est pas la date des questions ═

@pytest.mark.parametrize("phrase,attendue", [
    ("Les candidats peuvent poser leurs questions au plus tard 6 jours avant la date limite de remise des offres, "
     "fixée au 15/12/2026.", "09/12/2026"),
    ("Les questions des candidats doivent parvenir au plus tard 10 jours avant la date limite de réception des "
     "offres du 15 décembre 2026.", "05/12/2026"),
])
def test_date_limite_des_questions_delai_avant_la_remise(phrase, attendue):
    g = gn.build_grille({"criteres_attribution": _crit(("Valeur technique", "60 %", "1. Valeur technique : 60 %"),
                                                       ("Prix", "40 %", "2. Prix : 40 %"))},
                        _rc("REGLEMENT DE LA CONSULTATION", "Article 7 - Critères de jugement des offres",
                            "1. Valeur technique : 60 %", "2. Prix : 40 %", "Article 9 - Questions", phrase))
    dl = g["questions_acheteur"]["date_limite"]
    assert dl["date"] is None                                  # la date écrite est celle de la remise
    assert dl["message"].startswith(f"Date limite pour poser vos questions : le {attendue}, calculée par Adjugo")
    assert "15/12/2026" in dl["message"] and "écrite dans le règlement" not in dl["message"]
    # Une date écrite pour les questions, elle, reste « écrite dans le règlement ».
    g2 = gn.build_grille({"criteres_attribution": []}, _rc(
        "REGLEMENT DE LA CONSULTATION", "Article 9 - Questions",
        "Les questions sont posées au plus tard le 05/12/2026, soit 10 jours avant la date limite de remise des offres."))
    assert g2["questions_acheteur"]["date_limite"]["date"] == "2026-12-05"


# ═══ 3. Exigences proposées par l'IA : les mêmes exclusions que le repérage ═══════════════════════════

def test_exigences_proposees_par_l_ia_passent_les_memes_exclusions_que_le_reperage():
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 7 - Critères de jugement des offres", "1. Valeur technique : 60 %",
             "2. Prix : 40 %", "Article 8 - Contenu du mémoire technique",
             "Le candidat n'est pas tenu de présenter un planning détaillé des travaux.",
             "Le candidat peut présenter un reportage photographique de ses chantiers récents.",
             "Le candidat présentera, à titre facultatif, ses certificats de formation.",
             "Le candidat présentera la méthodologie de dépose de la couverture.",
             "Le candidat décrira les engins qu'il pourra mobiliser sur le chantier.",
             "Article 9 - Conditions de participation",
             "Le candidat devra présenter la liste de ses moyens financiers.")
    base = {"criteres_attribution": _crit(("Valeur technique", "60 %", "1. Valeur technique : 60 %"),
                                          ("Prix", "40 %", "2. Prix : 40 %"))}
    ia = dict(base, exigences_memoire=[
        "Le candidat n'est pas tenu de présenter un planning détaillé des travaux.",
        "présenter un planning détaillé des travaux",
        "Le candidat peut présenter un reportage photographique de ses chantiers récents.",
        "Le candidat présentera, à titre facultatif, ses certificats de formation.",
        "Le candidat devra présenter la liste de ses moyens financiers.",
        "Le candidat décrira les engins qu'il pourra mobiliser sur le chantier."])
    g = gn.build_grille(ia, rc)
    textes = [x["texte"] for x in g["exigences"]["liste"]]
    assert textes == ["la méthodologie de dépose de la couverture", "les engins qu'il pourra mobiliser sur le chantier"]
    t = ge.traitement(g, [{"id": 1, "titre": "1", "texte": "Nous présentons la méthodologie de dépose de la couverture "
                                                            "par zones et les engins mobilisés."}])
    assert [x["statut"] for x in t["liste"]] == [ge.TRAITEE, ge.TRAITEE] and not t["message_manque"]
    assert "planning" not in json.dumps(t, ensure_ascii=False)


def test_exigence_de_l_ia_du_cctp_qui_parle_de_l_offre_reste_gardee():
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 1 - Objet", "Réfection de la toiture.")
    cctp = (dp.header("03_CCTP.txt") + "\nCAHIER DES CLAUSES TECHNIQUES PARTICULIERES\nArticle 6 - Propreté\n"
            "La réduction des trajets des véhicules est à exposer dans l'offre.\nArticle 7 - Essais\n"
            "L'entreprise devra fournir les procès-verbaux d'essais en fin de chantier.\n")
    g = gn.build_grille({"criteres_attribution": [], "exigences_memoire": [
        "La réduction des trajets des véhicules est à exposer dans l'offre.",
        "L'entreprise devra fournir les procès-verbaux d'essais en fin de chantier."]}, rc + cctp)
    assert [x["origine"] for x in g["exigences"]["liste"]] == ["ia"]
    assert "trajets" in g["exigences"]["liste"][0]["texte"]


# ═══ 4. Questions à l'acheteur proposées par l'IA : les nombres comparés un à un ════════════════════

def test_question_de_l_ia_avec_un_nombre_absent_de_sa_phrase_est_ecartee():
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 7 - Critères de jugement des offres", "1. Valeur technique : 60 %",
             "2. Prix : 40 %", "Article 8 - Contenu du mémoire technique",
             "Le mémoire technique comportera au maximum 10 pages.",
             "Les candidats présenteront un planning détaillé de 12 semaines.")
    det = {"criteres_attribution": _crit(("Valeur technique", "60 %", "1. Valeur technique : 60 %"),
                                         ("Prix", "40 %", "2. Prix : 40 %")),
           "questions_acheteur": [
               {"question": "Le mémoire est-il limité à 1 page par sous-critère ?",
                "extraits": ["Le mémoire technique comportera au maximum 10 pages."]},
               {"question": "Le planning doit-il tenir en 2 semaines ?",
                "extraits": ["Les candidats présenteront un planning détaillé de 12 semaines."]},
               {"question": "Les 10 pages comprennent-elles les annexes ?",
                "extraits": ["Le mémoire technique comportera au maximum 10 pages."]}]}
    qs = [q["question"] for q in gn.build_grille(det, rc)["questions_acheteur"]["liste"] if q["origine"] == "ia"]
    assert qs == ["Les 10 pages comprennent-elles les annexes ?"]


# ═══ 5. « Traitée » : « chantier » n'est pas un mot principal d'une exigence ═══════════════════════

def test_traitee_le_mot_chantier_ne_suffit_pas():
    g = {"exigences": {"liste": [{"id": "e1", "texte": "la gestion des déchets du chantier",
                                  "phrase": "la gestion des déchets du chantier", "origine": "reperage"}]}}
    assert "chant" not in ge.cles("la gestion des déchets du chantier")
    t = ge.traitement(g, [{"id": 1, "titre": "Organisation",
                           "texte": "Notre conducteur de travaux assure la gestion du chantier au quotidien."}])
    assert t["liste"][0]["statut"] == ge.A_TRAITER
    assert "Il manque : « la gestion des déchets du chantier »" in t["message_manque"]
    t2 = ge.traitement(g, [{"id": 1, "titre": "Env", "texte": "Les déchets sont triés ; leur gestion est suivie."}])
    assert t2["liste"][0]["statut"] == ge.TRAITEE


# ═══ 6. Sous-critères non pondérés en liste « ; ; . » : tous repérés ════════════════════════════════

@pytest.mark.parametrize("puces", [
    ["méthodologie d'exécution en site occupé", "moyens humains et encadrement", "démarche environnementale"],
    ["méthodologie d'exécution en site occupé", "moyens humains et encadrement", "planning d'exécution",
     "démarche environnementale"],
])
def test_sous_criteres_non_ponderes_en_liste_a_point_virgule(puces):
    from app.services import atelier_plan as ap
    lignes = ["- " + p + (" ;" if i < len(puces) - 1 else ".") for i, p in enumerate(puces)]
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 7 - Critères de jugement des offres",
             "1. Valeur technique : 60 %, appréciée selon les sous-critères suivants :", *lignes,
             "2. Délai d'exécution : 10 %", "3. Prix : 30 %")
    det = {"criteres_attribution": _crit(
        ("Valeur technique", "60 %", "1. Valeur technique : 60 %, appréciée selon les sous-critères suivants :"),
        ("Délai d'exécution", "10 %", "2. Délai d'exécution : 10 %"), ("Prix", "30 %", "3. Prix : 30 %"))}
    g = gn.build_grille(det, rc)
    vt = next(c for c in g["criteres"] if c["critere"] == "Valeur technique")
    assert [s["critere"] for s in vt["sous_criteres"]] == puces
    assert g["environnement"]["dans_la_note"] is True
    plan = ap.build_plan({"details": {"grille_notation": g}}, "", base="grille")
    assert [s["numero"] for s in plan["sections"]] == [f"1.{i}" for i in range(1, len(puces) + 1)] + ["2"]


# ═══ 7. « Raccourcir » garde les « [À compléter] » (chef de file et partenaire) ═══════════════════════

def test_raccourcir_garde_le_a_completer_d_une_question_passee(client, auth, fake_llm):
    from tests.test_redaction_v5_entretien import _attendre
    h = auth["headers"]
    pid, _st = _projet_chantier(client, h)
    qc = _q(_entretien(client, h, pid), "chef_chantier")
    _repondre(client, h, pid, qc, statut="sautee")
    sid = qc["partie"]["section_id"]
    fake_llm(lambda kw: (" ".join(["Un encadrement de proximité suit le chantier au quotidien."] * 8), "end_turn"))
    assert _rediger(client, h, pid, sid)["status"] == "done"
    assert "[À compléter : chef de chantier]" in _version_db(sid)["texte"]
    fake_llm(lambda kw: ("Un encadrement de proximité suit le chantier au quotidien.", "end_turn"))
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={"cible_mots": 30})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    texte = _version_db(sid)["texte"]
    assert texte.startswith("Un encadrement de proximité suit le chantier au quotidien.")
    assert "[À compléter : chef de chantier]" in texte
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert "a_completer" in [x["code"] for x in st["blocage"]["raisons"]]


def test_raccourcir_chez_le_partenaire_garde_ses_a_completer(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P, _aide, _ecrire, _groupement, _part_a
    _pid, _st, a, _b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, " ".join(["Nous trions les déchets amiantés sur place avec soin."] * 12)
            + "\n\n[À compléter : filière d'élimination des déchets amiantés]")
    fake_llm(lambda kw: ("Nous trions les déchets amiantés sur place.", "end_turn"))
    job, _ = _aide(pa, sid, action="raccourcir", cible_mots=30)
    assert job["status"] == "done", job
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["texte"].startswith("Nous trions les déchets amiantés sur place.")
    assert "[À compléter : filière d'élimination des déchets amiantés]" in br["texte"]


def test_garder_trous_ne_double_pas_un_trou_reformule():
    base = "Texte.\n\n[À compléter : chef de chantier]\n[À compléter : planning des phases]"
    assert ec.garder_trous("Court. [À compléter : nom du chef de chantier]", base).count("[À compléter") == 2
    assert ec.garder_trous("Court.", "Sans trou.") == "Court."


# ═══ 8. Sous-critères numérotés « 1.1 / 1.2 » : jamais déplacés vers un autre critère ═══════════════

def test_sous_criteres_numerotes_restent_a_leur_critere_meme_si_leur_somme_tombe_sur_un_autre():
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 7 - Critères de jugement des offres",
             "1. Valeur technique : 60 points", "1.1 Méthodologie d'exécution : 25 points",
             "1.2 Moyens humains et encadrement : 15 points", "2. Prix : 40 points")
    det = {"criteres_attribution": _crit(("Valeur technique", "60 points", "1. Valeur technique : 60 points"),
                                         ("Prix", "40 points", "2. Prix : 40 points"))}
    g = gn.build_grille(det, rc)
    vt = next(c for c in g["criteres"] if c["critere"] == "Valeur technique")
    prix = next(c for c in g["criteres"] if c["critere"] == "Prix")
    assert [s["critere"] for s in vt["sous_criteres"]] == ["Méthodologie d'exécution", "Moyens humains et encadrement"]
    assert not prix.get("sous_criteres")
    assert vt["controle_sous"]["statut"] == "ecart"
    assert "total_sous" in [q["code"] for q in g["questions_acheteur"]["liste"]]


def test_sous_criteres_d_un_autre_critere_restent_rattaches_par_leur_somme():
    """Le cas que la règle « somme = poids d'un autre critère » sert toujours : sous-critères écrits APRÈS la ligne
    des critères, sans numéro de critère."""
    rc = _rc("REGLEMENT DE LA CONSULTATION", "Article 8 - Critères de jugement des offres : Valeur technique 60 % "
             "appréciée au vu du mémoire technique ; Prix 40 %.",
             "Sous-critère 1 : méthodologie 30 points ; Sous-critère 2 : moyens humains et matériels 20 points ; "
             "Sous-critère 3 : démarche environnementale 10 points.")
    det = {"criteres_attribution": _crit(("Valeur technique", "60 %", "Valeur technique 60 %"), ("Prix", "40 %", "Prix 40 %"))}
    vt = next(c for c in gn.build_grille(det, rc)["criteres"] if c["critere"] == "Valeur technique")
    assert len(vt["sous_criteres"]) == 3


# ═══ 9. Une phrase qui PERMET l'IA n'est jamais lue comme une interdiction ═════════════════════════

def test_mention_ia_permise_jamais_interdite():
    def m(ph):
        return ge.mention_ia(gn._pieces(_rc("REGLEMENT DE LA CONSULTATION", "Article 8 - Mémoire", ph)))
    r1 = m("L'usage d'un outil d'intelligence artificielle pour la rédaction du mémoire n'est pas interdit ; le "
           "candidat le signale dans son offre.")
    assert r1["nature"] == "declarer" and "signale" in r1["phrases"][0]["phrase"]
    r2 = m("Le recours à l'intelligence artificielle pour rédiger le mémoire technique est autorisé, sans restriction.")
    assert r2["nature"] == "permis" and r2["message"] == ge.MSG_IA_PERMIS and "écarte" not in r2["message"]
    assert m("Le mémoire technique est rédigé sans recours à un système d'intelligence artificielle.")["nature"] == "interdit"
    assert m("Le mémoire technique ne peut être rédigé par un outil d'intelligence artificielle.")["nature"] == "interdit"
    # « est autorisé » ne fait pas taire une interdiction écrite dans la même phrase.
    assert m("L'intelligence artificielle est autorisée pour la mise en page, mais le mémoire ne doit pas être "
             "rédigé par un outil d'IA.")["nature"] == "interdit"
    # Aucune question « l'IA est-elle admise ? » quand le règlement l'admet.
    det = {"criteres_attribution": []}
    g = gn.build_grille(det, _rc("REGLEMENT DE LA CONSULTATION", "Article 8 - Mémoire", "Le recours à l'intelligence "
                                 "artificielle pour rédiger le mémoire technique est autorisé, sans restriction."))
    assert "ia" not in [q["code"] for q in g["questions_acheteur"]["liste"]]


# ═══ 10. Entretien : un sous-critère sans poids écrit se classe sur le poids écrit de son critère ════

def test_questions_d_un_sous_critere_sans_poids_classees_sur_le_poids_ecrit_de_leur_critere():
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
          "1. Valeur technique : 60 %, appréciée selon les sous-critères suivants :\n"
          "- méthodologie d'exécution en site occupé ;\n- moyens humains et encadrement ;\n- démarche environnementale.\n"
          "2. Délai d'exécution : 10 %\n3. Prix : 30 %\n")
    cctp = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES\nArticle 1 - Contraintes du site\n"
            "L'école reste en activité pendant toute la durée des travaux.\n"
            "Article 2 - Délai\nLe délai d'exécution est de 4 mois, travaux réalisés pendant les vacances scolaires.\n"
            "Article 4 - Déchets\nLes déchets sont triés sur le chantier et évacués vers des filières agréées.\n")
    texte = dp.header("01_Reglement_de_la_consultation.txt") + "\n" + rc + "\n" + dp.header("03_CCTP.txt") + "\n" + cctp
    det = {"criteres_attribution": _crit(
        ("Valeur technique", "60 %", "1. Valeur technique : 60 %, appréciée selon les sous-critères suivants :"),
        ("Délai d'exécution", "10 %", "2. Délai d'exécution : 10 %"), ("Prix", "30 %", "3. Prix : 30 %"))}
    g = gn.build_grille(det, texte)
    lg = ec.lignes_grille(NS(ai_analysis={"details": {"grille_notation": g}}))
    sous = [x for x in lg if x["sous"]]
    assert sous and all(x["poids"] == "" and x["_w"] == 60.0 and x["parent_poids"] == "60 %" for x in sous)
    pieces = sorted(({"type": p["type"], "libelle": p["libelle"], "nom": p.get("nom") or "", "texte": p["texte"]}
                     for p in dp.typed_pieces(texte)), key=lambda p: ec._ORDRE.get(p["type"], 4))
    sel = ec.selection(ec.candidates(pieces, lg), lg)
    poids = [(c["q"]["code"], c["ligne"]["parent"] if c["ligne"].get("sous") else c["ligne"]["critere"]) for c in sel]
    criteres = [c for _code, c in poids]
    k = criteres.count("Valeur technique")
    # Toutes les questions du critère de 60 % d'abord (le site occupé en tête), puis celles du délai (10 %).
    assert k >= 3 and criteres[:k] == ["Valeur technique"] * k and set(criteres[k:]) == {"Délai d'exécution"}, poids
    assert poids[0][0] == "site_occupe"
    out = ec._critere_out(next(c["ligne"] for c in sel if c["q"]["code"] == "site_occupe"))
    assert out["sous"] and out["poids"] == "" and out["parent"] == "Valeur technique" and out["parent_poids"] == "60 %"


# ═══ 11. Réponse d'un partenaire effacée : oubliée des faits du chef de file ═══════════════════════

SECRET_PART = "ECHAFAUDAGEPIEDCOURNORD"


def _reponse_du_partenaire_redigee(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, b = _avec_partenaires(client, h)
    q = _q(_entretien(client, h, pid), "acces_toiture")
    pa = P(client, a["token"])
    r = pa.put(f"/entretien/{q['id']}", {"statut": "repondue", "avertissement_lu": True,
                                         "reponse": f"Accès par {SECRET_PART} et monte-matériaux de 12 mètres."})
    assert r.status_code == 200, r.text
    from tests.test_redaction_v5_entretien import _partie
    sec = _partie(st, "méthodologie")
    fake_llm(lambda kw: (f"Breizh Couverture accède à la toiture par un monte-matériaux de 12 mètres [{q['ref']}].",
                         "end_turn"))
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    f = next(x for x in _version_db(sec["id"])["faits"] if x["fait"] == "12 mètres")
    assert f["statut"] == "avec_source" and SECRET_PART in f["source"]["extrait"]
    return h, pid, sec, q, a, pa


def _toutes_les_versions(sid):
    from app.models import DossierSectionVersion
    db = _db()
    try:
        return json.dumps([[v.faits, v.sources] for v in db.query(DossierSectionVersion).filter(
            DossierSectionVersion.section_id == sid).all()], ensure_ascii=False)
    finally:
        db.close()


def test_retrait_du_partenaire_ses_reponses_sortent_des_faits_du_chef(client, auth, fake_llm, monkeypatch):
    h, pid, sec, q, a, _pa = _reponse_du_partenaire_redigee(client, auth, fake_llm)
    assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=h).status_code == 200
    assert SECRET_PART not in _toutes_les_versions(sec["id"])
    f = next(x for x in _version_db(sec["id"])["faits"] if x["fait"] == "12 mètres")
    assert f["statut"] == "a_relire" and not f.get("source")
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert "faits_a_relire" in [x["code"] for x in st["blocage"]["raisons"]]
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    assert SECRET_PART not in client.get(f"/api/atelier/{pid}/sections/{sec['id']}", headers=h).text


def test_question_reprise_ou_reponse_retiree_par_le_partenaire_faits_a_relire(client, auth, fake_llm):
    h, pid, sec, q, a, pa = _reponse_du_partenaire_redigee(client, auth, fake_llm)
    # Le partenaire retire sa réponse : les faits qui la citaient redeviennent « à relire ».
    cur = next(x for x in pa.get().json()["entretien"]["questions"] if x["id"] == q["id"])
    r = pa.put(f"/entretien/{q['id']}", {"statut": "a_repondre", "lock_version": cur["lock_version"]})
    assert r.status_code == 200, r.text
    assert SECRET_PART not in _toutes_les_versions(sec["id"])


def test_question_reprise_par_le_chef_avec_confirmation_faits_a_relire(client, auth, fake_llm):
    h, pid, sec, q, a, _pa = _reponse_du_partenaire_redigee(client, auth, fake_llm)
    url = f"/api/atelier/{pid}/entretien/{q['id']}/adresse"
    assert client.put(url, headers=h, json={"invite_id": None}).status_code == 409
    assert client.put(url, headers=h, json={"invite_id": None, "confirmer": True}).status_code == 200
    assert SECRET_PART not in _toutes_les_versions(sec["id"])
    f = next(x for x in _version_db(sec["id"])["faits"] if x["fait"] == "12 mètres")
    assert f["statut"] == "a_relire"


# ═══ 12. Invitation coupée sans « Retirer » (corbeille) : rien n'est montré, la purge efface ═════════

def test_invitation_coupee_par_la_corbeille_reponse_cachee_puis_effacee(client, auth, fake_llm):
    from app.models import EntretienQuestion, ProjectInvite
    from app.services import atelier_groupement as ag
    from tests.test_redaction_v4_groupement import P
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, _st, a, _b = _avec_partenaires(client, h)
    q = _q(_entretien(client, h, pid), "acces_toiture")
    pa = P(client, a["token"])
    assert pa.put(f"/entretien/{q['id']}", {"statut": "repondue", "avertissement_lu": True,
                                            "reponse": f"Accès par {SECRET_PART}."}).status_code == 200
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code == 204
    assert client.post(f"/api/projects/{pid}/restore", headers=h).status_code == 200
    # Avant la purge : ni dans la fiche chantier, ni sur la carte, ni dans l'export RGPD ; le refus dit pourquoi.
    e = client.get(f"/api/atelier/{pid}/entretien", headers=h).json()
    assert e["fiche"] == [] and SECRET_PART not in json.dumps(e, ensure_ascii=False)
    qq = _q(e, "acces_toiture")
    assert qq["adresse"]["active"] is False and qq["reponse"] is None
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h, json={"statut": "sautee"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "question_partenaire_sans_acces"
    assert "ne peut plus y répondre" in r.json()["detail"]["message"]
    assert SECRET_PART not in client.get("/api/rgpd/export", headers=h).text
    # La purge quotidienne efface sa réponse et rend la question au chef de file, comme le retrait.
    db = _db()
    try:
        assert db.get(ProjectInvite, a["id"]).revoked is True
        out = ag.purger(db)
        assert out["questions_entretien_reprises"] >= 1
        row = db.get(EntretienQuestion, q["id"])
        assert row.statut == ec.A_REPONDRE and row.reponse is None and row.adresse_kind == ec.ORG
    finally:
        db.close()
    assert _repondre(client, h, pid, _q(_entretien(client, h, pid, preparer=False), "acces_toiture"),
                     statut="sautee")


# ═══ 13. DECP : les accords-cadres réels (champ `techniques`) ══════════════════════════════════════

def test_accord_cadre_au_format_reel_de_decp(client, sources):
    assert "techniques" in sp.SELECT_DECP.split(",")
    base = {"nature": "Marché", "titulaire_id_1": SIRET, "titulaire_id_2": "CDL", "titulaire_id_3": "CDL",
            "typegroupementoperateurs": "Pas de groupement", "acheteur_id": ACH1}
    sources.decp = [
        # Ligne réelle 2026S08012 (lue le 19/10/2026), titulaire remplacé par l'entreprise fictive du test.
        dict(base, id="2026S08012", objet="Entretien des couvertures des bâtiments communaux", montant=200000.0,
             datenotification="2026-03-02", techniques="Accord-cadre", idaccordcadre="CDL"),
        dict(base, id="2026252606", objet="Maintenance des toitures terrasses", montant=510000.0,
             datenotification="2026-02-01", techniques="Accord-cadre, Accord-cadre", idaccordcadre="2026252606"),
        dict(base, id="2025COM57", objet="Marché subséquent : toiture de la salle", montant=55500.0,
             datenotification="2025-05-01", techniques="Accord-cadre", idaccordcadre="2020-COM-121"),
    ]
    r = sp.marches(SIRET)
    ac, ac2, sub = (_par_id(r["marches"], i) for i in ("2026S08012", "2026252606", "2025COM57"))
    for m in (ac, ac2):
        assert "montant_ht" not in m["valeur"] and m["releve"]["montant_ht"] is None     # vide, et verrouillé
        assert any(a.startswith("Accord-cadre") and "n'est pas repris" in a for a in m["alertes"]), m["alertes"]
    assert ac["affiche"]["montant"] == 200000.0
    assert sub["valeur"]["montant_ht"] == 55500 and not sub["alertes"]
    # Ajoutée à « Mes preuves », la fiche n'a pas de montant ; un montant écrit à la main serait dit « de DECP » :
    # refusé tant qu'elle garde la source (« Déclaré par vous » le permet).
    h, _uid = _org(client)
    d = client.get("/api/preuves/publiques/marches", headers=h).json()
    p = client.post("/api/preuves/publiques", headers=h,
                    json={"cles": [_par_id(d["marches"], "2026S08012")["cle"]]}).json()
    fiche = p["creees"][0]
    assert "montant_ht" not in fiche["valeur"] and "montant_ht" in fiche["champs_source_publique"]
    assert "montant d'attribution" not in fiche["texte"]
    src = fiche["source"]
    pub = {"nom": src["nom"], "url": src["url"], "consulte_le": src["consulte_le"], "identifiant": src["identifiant"]}
    r = client.patch(f"/api/preuves/{fiche['id']}", headers=h, json={
        "valeur": dict(fiche["valeur"], montant_ht=200000), "type_source": "public", "source": pub,
        "version": fiche["version"]})
    assert r.status_code == 422 and r.json()["detail"]["champs"] == ["montant_ht"], r.text
    r = client.patch(f"/api/preuves/{fiche['id']}", headers=h, json={
        "valeur": dict(fiche["valeur"], montant_ht=48000), "type_source": "declare", "version": fiche["version"]})
    assert r.status_code == 200 and r.json()["source_libelle"] == "déclaré par vous"
    # Dans la démo, l'exemple fictif suit le format réel.
    demo = sp.exemple_fictif_marches()["marches"]
    fic = _par_id(demo, "FICTIF-2023-077")
    assert any(a.startswith("Accord-cadre") for a in fic["alertes"]) and "montant_ht" not in fic["valeur"]


# ═══ 14. Deux marchés DECP distincts au même objet : deux références ═══════════════════════════════

def _deux_marches_meme_objet(sources):
    base = {"nature": "Marché", "titulaire_id_2": "CDL", "titulaire_id_3": "CDL",
            "typegroupementoperateurs": "Pas de groupement", "titulaire_id_1": SIRET}
    sources.decp = [
        dict(base, id="2026-A", objet="Rénovation du terrain de football en gazon synthétique", montant=409368.41,
             datenotification="2026-06-04", acheteur_id=ACH1),
        dict(base, id="2023-B", objet="Rénovation du terrain de football en gazon synthétique", montant=470888.7,
             datenotification="2023-10-31", acheteur_id=ACH2),
    ]


def test_meme_objet_autre_marche_dans_mes_preuves(client, sources):
    _deux_marches_meme_objet(sources)
    h, _uid = _org(client)
    d = client.get("/api/preuves/publiques/marches", headers=h).json()
    a = _par_id(d["marches"], "2026-A")
    assert client.post("/api/preuves/publiques", headers=h, json={"cles": [a["cle"]]}).json()["deja"] == 0
    d2 = client.get("/api/preuves/publiques/marches", headers=h).json()
    assert _par_id(d2["marches"], "2026-A")["deja"] is True
    b2 = _par_id(d2["marches"], "2023-B")
    assert b2["deja"] is False
    r2 = client.post("/api/preuves/publiques", headers=h, json={"cles": [b2["cle"]]}).json()
    assert len(r2["creees"]) == 1 and r2["deja"] == 0
    # Une fiche SAISIE au même intitulé, elle, fait encore dire « déjà dans vos preuves ».
    h2, _uid2 = _org(client)
    assert client.post("/api/preuves", headers=h2, json={
        "nature": "reference", "valeur": {"objet": "Rénovation du terrain de football en gazon synthétique"},
        "type_source": "declare"}).status_code in (200, 201)
    d3 = client.get("/api/preuves/publiques/marches", headers=h2).json()
    assert all(m["deja"] for m in d3["marches"])


def test_meme_objet_dans_la_part_deux_references(client, auth, sources):
    from tests.test_convention_groupement import _put
    from tests.test_redaction_v5_e2 import _groupement_simple, _version
    _deux_marches_meme_objet(sources)
    _h, _pid, token = _groupement_simple(client, auth)
    assert _put(client, token, company_name="Couverture Kerbrat (test)", siret=SIRET).status_code == 200
    dm = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    r = client.post(f"/api/invite/{token}/contribution/reprendre",
                    json={"publiques": [m["cle"] for m in dm["marches"]], "version": _version(client, token)}).json()
    assert len(r["ajoutees"]["references"]) == 2 and r["deja"] == 0
    dm2 = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    assert all(m["deja"] for m in dm2["marches"])


# ═══ 15. Liste RGE au format réel : les domaines d'une qualification regroupés ══════════════════════

def test_rge_au_format_reel_un_domaine_par_ligne_regroupe(sources):
    q = {"siret": SIRET, "nom_certificat": "QUALIBAT-RGE", "organisme": "qualibat", "meta_domaine": "Travaux "
         "d'efficacité énergétique", "lien_date_debut": "2022-10-20", "lien_date_fin": "2030-11-10"}
    sources.rge = [  # lecture réelle de data.ademe.fr (19/10/2026), SIRET remplacé par celui du test
        dict(q, code_qualification="2111D111", nom_qualification="Maçonnerie et ouvrage en béton armé (2111D111)",
             domaine="Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds"),
        dict(q, code_qualification="2111D112", nom_qualification="Maçonnerie et ouvrage en béton armé (2111D112)",
             domaine="Isolation des murs par l'extérieur"),
        dict(q, code_qualification="2111D115", nom_qualification="Maçonnerie et ouvrage en béton armé (2111D115)",
             domaine="Isolation des planchers bas"),
        dict(q, code_qualification="4131D111", nom_qualification="Plaques de plâtre (4131D111)",
             domaine="Isolation des planchers bas", lien_date_debut="2023-10-16", lien_date_fin="2031-11-10"),
    ]
    r = sp.qualifications_rge(SIRET)
    assert [(x["valeur"]["nom"], x["valeur"]["numero"], len(x["affiche"]["domaines"])) for x in r["qualifications"]] == [
        ("QUALIBAT-RGE : Maçonnerie et ouvrage en béton armé", "2111", 3), ("QUALIBAT-RGE : Plaques de plâtre", "4131", 1)]
    assert "D111" not in json.dumps([x["valeur"] for x in r["qualifications"]])


# ═══ 16. Noms des acheteurs : un exécuteur borné, aucune lecture perdue ni relancée ═══════════════════

def test_noms_des_acheteurs_budget_borne_sans_lectures_perdues(monkeypatch):
    sp.vider_cache()
    appels, en_meme_temps, pic = [], [0], [0]
    verrou = threading.Lock()

    def lent(siren):
        with verrou:
            appels.append(siren)
            en_meme_temps[0] += 1
            pic[0] = max(pic[0], en_meme_temps[0])
        time.sleep(0.15)
        with verrou:
            en_meme_temps[0] -= 1
        return f"Commune {siren}"
    monkeypatch.setattr(sp, "_nom_sirene", lent)
    monkeypatch.setattr(sp, "NOMS_BUDGET_S", 0.2)
    sirets = [f"{200000000 + i}00011" for i in range(12)]
    t0 = time.monotonic()
    premier = sp.noms_acheteurs(sirets)
    assert time.monotonic() - t0 < 1.0 and len(premier) < 12
    time.sleep(0.5)                               # les lectures commencées finissent… et rangent leur nom
    lus = len(appels)
    assert lus < 12                               # celles qui n'avaient pas commencé ont été annulées
    assert pic[0] <= 4                            # 4 lectures au plus en même temps, pour tout le process
    deuxieme = sp.noms_acheteurs(sirets)
    time.sleep(0.6)
    assert len(set(appels)) == len(appels)        # jamais deux lectures du même acheteur
    assert all(premier[s] == deuxieme[s] for s in premier)
    assert len(deuxieme) > len(premier)
    sp.vider_cache()


# ═══ 17. Ajout dans la part : aucun appel à l'annuaire pendant que la part est verrouillée ════════════

def test_ajout_dans_la_part_sans_appel_reseau_sous_le_verrou(client, auth, sources, monkeypatch):
    from app.services import preuves_publiques as ppub
    from tests.test_convention_groupement import _put
    from tests.test_redaction_v5_e2 import _groupement_simple, _version
    _h, _pid, token = _groupement_simple(client, auth)
    assert _put(client, token, company_name="Couverture Kerbrat (test)", siret=SIRET).status_code == 200
    dm = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    m1 = _par_id(dm["marches"], "M-2024-01")
    sp.vider_cache()                                # redémarrage : la route préchauffe avant de verrouiller
    monkeypatch.setattr(sp, "NOMS_MAX", 1)          # le préchauffage ne résout qu'un acheteur sur deux
    sous_verrou = []
    vrai = ppub.reprendre_dans_part

    def espion(*a, **k):
        n = len(sources.calls)
        out = vrai(*a, **k)
        sous_verrou.extend(sources.calls[n:])
        return out
    monkeypatch.setattr(ppub, "reprendre_dans_part", espion)
    r = client.post(f"/api/invite/{token}/contribution/reprendre",
                    json={"publiques": [m1["cle"]], "version": _version(client, token)})
    assert r.status_code == 200, r.text
    assert sous_verrou == []
    assert r.json()["ajoutees"]["references"][0]["client"] == "COMMUNE DE KERBRAT (FICTIVE)"   # nom lu au préchauffage


# ═══ 18. Une source tombe pendant un ajout : la ligne cochée n'est jamais perdue en silence ══════════

def test_panne_partielle_a_l_ajout_la_ligne_cochee_est_dite(client, auth, sources):
    from tests.test_convention_groupement import _put
    from tests.test_redaction_v5_e2 import _groupement_simple, _version
    _h, _pid, token = _groupement_simple(client, auth)
    assert _put(client, token, company_name="Couverture Kerbrat (test)", siret=SIRET).status_code == 200
    dm = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    dr = client.get(f"/api/invite/{token}/contribution/publiques/rge").json()
    m1 = _par_id(dm["marches"], "M-2024-01")
    q = next(x for x in dr["qualifications"] if x["valeur"]["numero"] == "5112")
    sp.vider_cache()
    sources.fail.add("decp")
    r = client.post(f"/api/invite/{token}/contribution/reprendre",
                    json={"publiques": [m1["cle"], q["cle"]], "version": _version(client, token)})
    d = r.json()
    assert r.status_code == 200 and d["ajoutees"]["qualifications"] and not d["ajoutees"]["references"]
    assert [x["message"] for x in d["ignorees"]] == [sp.MSG_PANNE["decp"]] and d["pannes"] == [sp.MSG_PANNE["decp"]]
    # Mes preuves : idem, la ligne est dite.
    h2, _uid = _org(client)
    sources.fail = set()
    sp.vider_cache()
    d2 = client.get("/api/preuves/publiques/marches", headers=h2).json()
    dq = client.get("/api/preuves/publiques/rge", headers=h2).json()
    sp.vider_cache()
    sources.fail.add("decp")
    r2 = client.post("/api/preuves/publiques", headers=h2, json={"cles": [_par_id(d2["marches"], "M-2024-01")["cle"],
                                                                          dq["qualifications"][0]["cle"]]}).json()
    assert len(r2["creees"]) == 1 and [x["message"] for x in r2["ignorees"]] == [sp.MSG_PANNE["decp"]]
    js = _lire("sources-publiques.js")
    assert "r.data.pannes" in js and "errPanne" in js


# ═══ 19. La provenance « source publique DECP » n'est jamais prise du navigateur ═════════════════════

def test_provenance_decp_jamais_prise_du_navigateur(client, auth, sources):
    from tests.test_convention_groupement import _invite, _project, _put
    from tests.test_redaction_v5_e2 import _version
    h = auth["headers"]
    pid = _project(client, h, name=f"Toiture {uuid.uuid4().hex[:4]}")
    token = _invite(client, h, pid, "Partenaire (test)")["token"]
    fausse = {"intitule": "Couverture du stade (jamais attribuée)", "client": "Ville imaginaire", "montant": 9999999,
              "annee": 2025, "role": "seul", "provenance": "decp", "consulte_le": "2026-10-19",
              "identifiant": "marché INVENTE, acheteur 00000000000000"}
    assert _put(client, token, company_name="Partenaire (test)", siret=SIRET, references=[fausse]).status_code == 200
    c = client.get(f"/api/invite/{token}/contribution").json()
    ref = c["references"][0]
    assert ref["intitule"] == fausse["intitule"] and not ({"provenance", "consulte_le", "identifiant"} & set(ref))
    db = _db()
    try:
        out, _uids = at._apports_partenaires(db, pid)
    finally:
        db.close()
    assert "marché attribué" not in json.dumps(out, ensure_ascii=False)
    # Une référence reprise de DECP par « Reprendre », renvoyée telle quelle par l'écran, garde sa provenance ;
    # modifiée, elle devient une simple saisie.
    dm = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    m1 = _par_id(dm["marches"], "M-2024-01")
    c2 = client.post(f"/api/invite/{token}/contribution/reprendre",
                     json={"publiques": [m1["cle"]], "version": _version(client, token)}).json()["contribution"]
    decp = next(x for x in c2["references"] if x.get("provenance") == "decp")
    assert _put(client, token, references=c2["references"]).status_code == 200
    c3 = client.get(f"/api/invite/{token}/contribution").json()
    assert decp in c3["references"]
    modifiee = dict(decp, montant=1)
    assert _put(client, token, references=[modifiee]).status_code == 200
    ref4 = client.get(f"/api/invite/{token}/contribution").json()["references"][0]
    assert ref4["montant"] == 1 and "provenance" not in ref4


# ═══ 20. L'écran dit que les données publiques couvrent surtout les marchés depuis 2024 ═══════════════

def test_ecran_dit_la_couverture_des_donnees_publiques():
    js = _lire("sources-publiques.js")
    phrase = ("Les données publiques lues couvrent surtout les marchés notifiés depuis 2024 : un marché plus ancien "
              "peut manquer, ajoutez-le vous-même.")
    assert phrase in js and "NOTE_COUVERTURE" in js.split("const BULLE_DECP")[1].split(";")[0]
    assert "spEsc(NOTE_COUVERTURE)" in js


# ═══ 21. « Mes preuves » : une référence de DECP est « attribuée », jamais « réalisée » ═══════════════

def test_mes_preuves_reference_de_decp_dite_attribuee_sous_node():
    from tests.test_redaction_v3_mes_preuves_ecrans import _node
    r = _node("""
      const p = { nature: "reference", type_source: "public", source_libelle: "marché attribué, source publique DECP",
                  valeur: { acheteur: "COMMUNE DE KERBRAT (FICTIVE)", annee: 2024, montant_ht: 85000, role: "seul" } };
      const s = Object.assign({}, p, { valeur: Object.assign({}, p.valeur, { role: "groupement_solidaire" }) });
      const d = { nature: "reference", type_source: "declare", source_libelle: "déclaré par vous", valeur: { role: "seul" } };
      console.log(JSON.stringify([pvDetail(p), pvDetail(s), pvDetail(d)]));""")
    r = [re.sub(r"[\u202f\u00a0]", " ", x) for x in r]
    assert r[0] == "COMMUNE DE KERBRAT (FICTIVE) · 2024 · 85 000 € HT · attribué seul"
    assert r[1].endswith("attribué en groupement solidaire") and r[2] == "réalisé seul"
    js = _lire("app.js")
    assert '{ k: "role", l: "Rôle", t: "select"' in js and "Vos marchés réalisés ou attribués" in js
    assert "Les marchés que vous avez réalisés" not in js


# ═══ 22. « Rédiger sans IA » sur la carte du marché : jamais un bouton sans effet ═══════════════════

def test_carte_comment_vous_serez_note_bouton_sans_ia_selon_l_ecran_et_le_mode():
    js, html = _lire("app.js"), _lire("app.html")
    comp = js.split('__adjApp.component("grille-carte", {')[1].split("__adjApp.component(")[0]
    assert "mobile: { type: Boolean" in comp and "sansIa: { type: Boolean" in comp
    assert '<span v-if="sansIa"' in comp and "Ce dossier se rédige sans IA." in comp
    assert 'v-else-if="mobile"' in comp and "se choisit depuis un ordinateur, dans l\\'atelier" in comp
    assert ':mobile="atlMobile"' in html and ':sans-ia="!!(ao.atl.d && ao.atl.d.sans_ia && ao.atl.d.sans_ia.actif)"' in html


# ═══ 23. Les cases des options de l'export reviennent à l'état enregistré après un refus ═════════════

def test_cases_des_options_remises_a_l_etat_enregistre_apres_un_refus():
    js, html = _lire("app.js"), _lire("app.html")
    meth = js.split("async atlSansIaChoisir(val, el) {")[1].split("\n    },")[0]
    assert "el.checked = this.atlSansIa()" in meth and "remettre();" in meth.split("catch (e)")[1]
    assert "atlSansIaChoisir($event.target.checked, $event.target)" in html
    assert "atlOption('page_garde', $event.target.checked, $event.target)" in html
    assert "el.checked = !!(a.st.export.options || {})[k]" in js.split("async atlOption(k, val, el) {")[1].split("\n    },")[0]


# ═══ 24. Déplacer une partie : les sous-critères d'un critère restent ensemble, un seul numéro ════════

def _atelier_sous_criteres(client, h):
    from app.models import Project
    from tests.test_redaction_v2_atelier import _creer, _projet
    pid = _projet(client, h)
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
          "1. Valeur technique : 60 %\n1.1 Méthodologie d'intervention : 30 %\n1.2 Moyens affectés au chantier : 20 %\n"
          "1.3 Démarche environnementale : 10 %\n2. Prix : 40 %\n")
    db = _db()
    try:
        p = db.get(Project, pid)
        det = {"intitule_marche": "Toiture", "criteres_attribution": _crit(
            ("Valeur technique", "60 %", "1. Valeur technique : 60 %"), ("Prix", "40 %", "2. Prix : 40 %"))}
        det["grille_notation"] = gn.build_grille(det, rc)
        p.ai_analysis = {"summary": "x", "dce_available": True, "details": det}
        db.commit()
    finally:
        db.close()
    st = _creer(client, h, pid, base="grille")
    assert [s["numero_affiche"] for s in st["sections"]] == ["1.1", "1.2", "1.3"]
    return pid, st


def _ordre(client, h, pid):
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    return [(s["numero_affiche"], s["intitule"]) for s in st["sections"]], st


def test_deplacer_une_partie_garde_les_sous_criteres_ensemble(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid, st = _atelier_sous_criteres(client, h)
    s1, s2, s3 = st["sections"]
    libre = client.post(f"/api/atelier/{pid}/sections", headers=h,
                        json={"intitule": "Partie ajoutée", "apres_section_id": s1["id"]}).json()
    # Ajoutée « après 1.1 » : elle passe le groupe, jamais au milieu.
    o, _ = _ordre(client, h, pid)
    assert o == [("1.1", "Méthodologie d'intervention"), ("1.2", "Moyens affectés au chantier"),
                 ("1.3", "Démarche environnementale"), ("2", "Partie ajoutée")]
    # « Monter » la partie libre : elle passe le groupe entier.
    assert client.patch(f"/api/atelier/{pid}/sections/{libre['id']}", headers=h, json={"position": 2}).status_code == 200
    o, _ = _ordre(client, h, pid)
    assert o[0] == ("1", "Partie ajoutée") and [n for n, _t in o[1:]] == ["2.1", "2.2", "2.3"]
    # « Descendre » : elle repasse le groupe entier.
    assert client.patch(f"/api/atelier/{pid}/sections/{libre['id']}", headers=h, json={"position": 1}).status_code == 200
    o, st2 = _ordre(client, h, pid)
    assert [n for n, _t in o] == ["1.1", "1.2", "1.3", "2"]
    # Entre eux, les sous-critères changent d'ordre librement ; sortir du groupe est refusé et dit.
    assert client.patch(f"/api/atelier/{pid}/sections/{s2['id']}", headers=h, json={"position": 0}).status_code == 200
    r = client.patch(f"/api/atelier/{pid}/sections/{s3['id']}", headers=h, json={"position": 3})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "groupe_sous_criteres"
    assert "Valeur technique" in r.json()["detail"]["message"]
    o, st3 = _ordre(client, h, pid)
    assert [t for _n, t in o] == ["Moyens affectés au chantier", "Méthodologie d'intervention",
                                  "Démarche environnementale", "Partie ajoutée"]
    # Retirée puis remise : la partie d'un sous-critère revient dans son groupe, pas en fin de plan.
    assert client.delete(f"/api/atelier/{pid}/sections/{s1['id']}", headers=h).status_code == 200
    assert client.post(f"/api/atelier/{pid}/sections/{s1['id']}/remettre", headers=h).status_code == 200
    o, st4 = _ordre(client, h, pid)
    assert [n for n, _t in o] == ["1.1", "1.2", "1.3", "2"] and o[-1][1] == "Partie ajoutée"
    parents = [s["parents"] for s in st4["sections"][:3]]
    assert parents == [[{"numero": "1", "intitule": "Valeur technique"}]] * 3


def test_rangs_d_un_ordre_ancien_interrompu_un_seul_numero_par_critere():
    def s(i, cid=None):
        return NS(id=i, source_plan="grille" if cid else "utilisateur", critere_id=cid or "",
                  parents=[{"intitule": "Valeur technique"}] if cid else [], numero="")
    d = NS(plan_source="grille")
    secs = [s(1, "c1"), s(2), s(3, "c1"), s(4, "c1")]
    rangs = at._rangs(d, secs)
    assert rangs == {1: "1.1", 2: "2", 3: "1.2", 4: "1.3"}
    assert {at.parents_affiches(d, x, rangs[x.id])[0]["numero"] for x in (secs[0], secs[2], secs[3])} == {"1"}


# ═══ 25. Entretien : la phrase qui motive une question n'est pas prise dans un article de candidature ═

def test_phrase_du_dossier_jamais_tiree_des_conditions_de_participation():
    q = {"code": "periodes", "declencheurs": [r"vacances scolaires"]}
    rc = ("REGLEMENT DE LA CONSULTATION\n## Article 2 — Conditions de participation\n"
          "Ce niveau, supérieur au double du montant estimé, est justifié par les conditions d'exécution : travaux en "
          "site occupé, concentrés sur les vacances scolaires.\n## Article 3 — Délai d'exécution\n"
          "Les travaux en toiture au droit des salles de classe sont réalisés pendant les vacances scolaires.\n")
    x = ec._trouver(q, [{"type": dp.REGLEMENT, "libelle": "Règlement de la consultation", "texte": rc}])
    assert x["phrase"].startswith("Les travaux en toiture au droit des salles de classe")
    # Seule phrase du dossier : elle sert, faute de mieux.
    seule = rc.split("## Article 3")[0]
    assert ec._trouver(q, [{"type": dp.REGLEMENT, "libelle": "RC", "texte": seule}])["phrase"].startswith("Ce niveau")


def test_demo_la_question_des_periodes_motivee_par_l_article_du_delai(client, monkeypatch):
    from app.models import Project, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        pid = next(p for p in db.query(Project).filter(Project.user_id == u.id)
                   if p.name.startswith("Réfection toiture")).id
    finally:
        db.close()
    monkeypatch.setattr(llm, "messages_create", lambda *a, **k: (_ for _ in ()).throw(AssertionError("IA")))
    tok = client.post("/api/auth/demo").json()["access_token"]
    e = _entretien(client, {"Authorization": f"Bearer {tok}"}, pid, preparer=False)
    per = _q(e, "periodes")
    assert per["motif"]["phrase"].startswith("Les travaux en toiture au droit des salles de classe")
    assert all("supérieur au double du montant" not in (x["motif"] or {}).get("phrase", "") for x in e["questions"])


# ═══ 26. 375 px : l'en-tête de l'estimation du prix passe à la ligne ═══════════════════════════════

def test_en_tete_de_l_estimation_passe_a_la_ligne_sur_telephone():
    html, css = _lire("app.html"), _lire("styles.css")
    assert '<div class="ch ch-wrap"><i data-lucide="calculator"></i><h3>Estimation du prix</h3>' in html
    assert re.search(r"\.card \.ch\.ch-wrap \{[^}]*flex-wrap:wrap", css)
