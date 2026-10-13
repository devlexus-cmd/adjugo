"""
Rédaction, vague 3 — corrections de la revue (contre-revue sceptique, octobre 2026).

 • CV et noms des salariés jamais à l'IA (décision 8, doctrine § 7 règle 9), sur TOUS les chemins :
     - « Partir de vos anciens dossiers » : un tableau « Moyens humains », une liste « Encadrement : X et
       Y », un CV en annexe dont les rubriques sont séparées par des lignes vides ;
     - la rédaction de l'atelier : un document de « Mon savoir-faire » qui ressemble à un CV, un passage
       de CV d'un ancien mémoire, un nom masqué à la lecture d'un ancien dossier puis resté dans la fiche
       acceptée ;
     - « Raccourcir » : un CV inséré dont la fiche a été supprimée depuis ;
 • « Mes preuves » ne fait jamais taire le profil par une proposition écartée ;
 • l'estimation du budget de l'essai couvre le pire de la lecture d'un document ;
 • l'outil de mesure des fausses alertes montre aussi les libellés positifs, et ne range jamais les
   mémoires de calibration dans le dépôt.
Aucun appel réseau : le fournisseur d'IA est simulé. Aucune donnée réelle.
"""
import json
import os
import re

import pytest

from app.services import fiches_import as fi
from tests.test_redaction_socle0 import fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _etat, _projet
from tests.test_redaction_v3_ensemble import _attendre_lecture, _contenu, _ok, _register, _system, _version

REDACTION = "dossier de présentation (le « mémoire technique »)"


def _kb(client, h, text, name="Mémoire 2023.pdf", kind="memoire"):
    return _ok(client.post("/api/knowledge/text", headers=h, json={"name": name, "text": text, "kind": kind}))["doc"]["id"]


def _rediger(client, h, pid, sid):
    r = _ok(client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={}), 202)
    assert _attendre(client, h, pid, r["tache"]["id"])["status"] == "done"


# ═══ 1. « Partir de vos anciens dossiers » : tableaux et listes de noms, CV en annexe ═══════════

DOC_RH = ("Mémoire technique — Breizh Couverture\n\n"
          "Moyens humains\n"
          "| Nom | Fonction | Expérience |\n|---|---|---|\n"
          "| Jean-Yves Le Goff | Chef de chantier | 15 ans |\n"
          "| Anne Le Floch | Couvreuse | 8 ans |\n\n"
          "Encadrement : Gwenaël Kerhervé et Soizic Le Bris.\n\n"
          "Notre effectif compte 12 salariés.\n\n"
          "Moyens matériels\n"
          "Nous disposons de 2 nacelles articulées.\n")

DOC_ANNEXE = ("Mémoire technique 2023\n\n"
              "Nos références\n"
              "En 2022, réfection de la toiture du lycée de Brest pour la Région Bretagne (85 000 € HT).\n"
              "En 2021, couverture en ardoise de la salle des fêtes de Plouguerneau pour la commune (60 000 € HT).\n"
              "En 2020, zinguerie de la médiathèque de Landerneau pour la ville de Landerneau (45 000 € HT).\n\n"
              "Notre méthodologie\n"
              "Chaque chantier commence par une visite du site, un relevé des existants et un plan de prévention. "
              "Nous protégeons les abords, nous trions les déchets sur place et nous nettoyons le site chaque soir. "
              "La réception se prépare avec le maître d'œuvre une semaine avant la fin des travaux.\n\n"
              "Annexe 3 : CV du conducteur de travaux\n\n"
              "Yann Tanguy\n\n"
              "Né le 3 mai 1985 à Brest, marié\n\n"
              "Expériences professionnelles\n"
              "Conducteur de travaux chez Breizh Couverture depuis 2012, 40 chantiers de couverture.\n\n"
              "Formations : BTS Bâtiment 2005\n\n"
              "Annexe 4 : Attestations\n"
              "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345).\n")


def test_noms_dans_un_tableau_ou_une_liste_reperes_sans_ia():
    assert fi.noms_probables("| Jean-Yves Le Goff | Chef de chantier | 15 ans |") == ["Jean-Yves Le Goff"]
    assert fi.noms_probables("Encadrement : Jean-Yves Le Goff et Anne Le Floch.") == ["Jean-Yves Le Goff",
                                                                                      "Anne Le Floch"]
    assert fi.noms_probables("Encadrement : Gwenaël Kerhervé, Soizic Le Bris et Loïc Guéguen.") == [
        "Gwenaël Kerhervé", "Soizic Le Bris", "Loïc Guéguen"]
    assert fi.noms_probables("Jean-Yves Le Goff, 15 ans d'expérience en couverture.") == ["Jean-Yves Le Goff"]
    # Pas un nom : un organisme, un matériel.
    assert fi.noms_probables("| Mairie de Quimper | 2024 |\n| Nacelle articulée | 2 |\nAcheteur : Mairie de Brest.") == []


def test_section_moyens_humains_jamais_envoyee_avec_ses_noms():
    t, _n = fi.texte_sans_lignes_privees(DOC_RH)
    for interdit in ("Jean-Yves Le Goff", "Anne Le Floch", "Gwenaël", "Soizic", "15 ans", "8 ans"):
        assert interdit not in t, interdit
    assert "Notre effectif compte 12 salariés." in t and "2 nacelles articulées" in t


def test_cv_en_annexe_rubriques_separees_par_des_lignes_vides():
    t, n = fi.texte_sans_lignes_privees(DOC_ANNEXE)
    for interdit in ("Yann Tanguy", "3 mai 1985", "marié", "BTS Bâtiment", "Expériences professionnelles",
                     "CV du conducteur"):
        assert interdit not in t, interdit
    assert n > 0 and "Qualibat 3194" in t and "lycée de Brest" in t
    # Sans titre « CV » : la date de naissance suffit, avec le nom au-dessus et les rubriques en dessous.
    t2, _n = fi.texte_sans_lignes_privees(DOC_ANNEXE.replace("Annexe 3 : CV du conducteur de travaux\n\n", ""))
    for interdit in ("Yann Tanguy", "3 mai 1985", "BTS Bâtiment"):
        assert interdit not in t2, interdit


def test_lecture_d_un_ancien_dossier_aucun_nom_ni_cv_envoye(client, fake_llm):
    recus = []

    def ans(kw):
        recus.append(_contenu(kw))
        return json.dumps({"fiches": []}), "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture"}))
    for texte in (DOC_RH, DOC_ANNEXE):
        doc_id = _kb(client, h, texte, name=f"Mémoire {len(recus)}.pdf")
        _ok(client.post(f"/api/knowledge/{doc_id}/fiches", headers=h, json={}), 202)
        assert _attendre_lecture(client, h, doc_id)["lecture"]["statut"] == "lu"
    envoye = "\n".join(recus)
    for interdit in ("Jean-Yves Le Goff", "Anne Le Floch", "Gwenaël Kerhervé", "Soizic Le Bris", "Yann Tanguy",
                     "3 mai 1985", "BTS Bâtiment", "15 ans", "8 ans"):
        assert interdit not in envoye, interdit
    assert "2 nacelles articulées" in envoye and "Qualibat 3194" in envoye


# ═══ 2. La rédaction de l'atelier : CV de « Mon savoir-faire », noms des fiches et des extraits ══

CV_DOC = ("Curriculum vitae\n\nAnne Le Floch\nNée le 3 mai 1985, mariée, 2 enfants\n12 rue des Lilas, 29000 Quimper\n\n"
          "Expériences professionnelles : conductrice de travaux couverture zinguerie depuis 2012, encadrement du "
          "chantier, encadrement des compagnons sur le chantier, sécurité du chantier.\n\n"
          "Formations : BTS Bâtiment. Loisirs : voile.")


def test_un_cv_de_mon_savoir_faire_ne_part_jamais_a_la_redaction(client, fake_llm):
    envoyes = []

    def ans(kw):
        if REDACTION in _system(kw):
            envoyes.append(_contenu(kw))
        return "Notre équipe [À compléter : moyens humains].", "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture"}))
    doc_id = _kb(client, h, CV_DOC, name="Anne.pdf", kind="autre")
    assert _ok(client.get(f"/api/knowledge/{doc_id}/fiches", headers=h))["document"]["statut"] == "cv"
    # Un ancien mémoire avec un CV en annexe : l'extrait du CV ne part pas, le reste oui.
    _kb(client, h, DOC_ANNEXE.replace("conducteur de travaux", "encadrement du chantier"))
    pid = _projet(client, h)
    sid = _creer(client, h, pid)["sections"][0]["id"]
    _rediger(client, h, pid, sid)
    assert envoyes
    e = "\n".join(envoyes)
    for interdit in ("3 mai 1985", "rue des Lilas", "Anne Le Floch", "Anne.pdf", "Yann Tanguy", "BTS Bâtiment"):
        assert interdit not in e, interdit


def test_rag_pour_l_ia_ecarte_les_cv_la_recherche_de_l_utilisateur_les_montre(client):
    from app.services import rag
    from tests.test_redaction_v3_ensemble import _db
    _e, h, uid = _register(client)
    _kb(client, h, CV_DOC, name="Anne.pdf", kind="autre")
    db = _db()
    try:
        assert rag.retrieve_multi(db, [uid], "encadrement chantier compagnons", k=6) == []
        assert rag.retrieve(db, uid, "encadrement chantier compagnons", k=6) == []
        assert rag.retrieve(db, uid, "encadrement chantier compagnons", k=6, pour_ia=False)
    finally:
        db.close()
    r = _ok(client.post("/api/knowledge/search", headers=h, json={"query": "encadrement chantier", "k": 5}))
    assert r                                         # sa propre recherche montre tout


def test_un_nom_masque_a_la_lecture_reste_masque_a_la_redaction(client, fake_llm):
    passage = ("En 2022, réfection de la toiture du lycée de Brest pour la Région Bretagne, sous la conduite de "
               "Yann Tanguy, conducteur de travaux.")
    lecture, redaction = [], []

    def ans(kw):
        recu = _contenu(kw)
        if REDACTION in _system(kw):
            redaction.append(recu)
            return "Nous avons réalisé la toiture du lycée de Brest.", "end_turn"
        lecture.append(recu)
        m = re.search(r"En 2022, réfection de la toiture du lycée de Brest pour la Région Bretagne, sous la "
                      r"conduite de [^\n]+?\.", recu)
        p = m.group(0) if m else passage
        return json.dumps({"fiches": [{"nature": "reference", "champs": {
            "objet": "Réfection de la toiture du lycée de Brest", "acheteur": "Région Bretagne", "annee": 2022,
            "description": p}, "passage": p}]}, ensure_ascii=False), "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture"}))
    doc_id = _kb(client, h, "Mémoire technique\n\nNos références\n" + passage + "\n")
    _ok(client.post(f"/api/knowledge/{doc_id}/fiches", headers=h, json={}), 202)
    f = _attendre_lecture(client, h, doc_id)["fiches"][0]
    assert "Yann Tanguy" in f["valeur"]["description"]           # la fiche garde le texte du document
    _ok(client.post(f"/api/preuves/{f['id']}/accepter", headers=h, json={"version": f["version"]}))
    pid = _projet(client, h)
    sid = _creer(client, h, pid)["sections"][0]["id"]
    _rediger(client, h, pid, sid)
    assert lecture and redaction
    assert not any("Yann Tanguy" in x or "Tanguy" in x for x in lecture + redaction)
    assert any("lycée de Brest" in x for x in redaction)        # la fiche part, son nom masqué


# ═══ 3. « Raccourcir » : un CV inséré dont la fiche a été supprimée depuis ═══════════════════════

def test_un_cv_insere_puis_fiche_supprimee_n_est_jamais_raccourci(client, fake_llm):
    envoyes = []

    def ans(kw):
        if "Tu raccourcis" in _system(kw):
            envoyes.append(_contenu(kw))
            return "Texte court.", "end_turn"
        return "Texte.", "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture"}))
    sal = _ok(client.post("/api/preuves", headers=h, json={
        "nature": "salarie", "valeur": {"nom": "Yann Tanguy", "fonction": "Conducteur de travaux",
                                        "experience_annees": 15, "diplomes": "BTS Bâtiment 2009"},
        "type_source": "declare"}), 201)
    pid = _projet(client, h)
    sid = _creer(client, h, pid)["sections"][0]["id"]
    sec = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    base = (sec.get("version_courante") or {}).get("id")
    texte = " ".join(["Notre équipe encadre chaque chantier avec rigueur et attention."] * 10)
    _ok(client.put(f"/api/atelier/{pid}/sections/{sid}/texte", headers=h, json={"texte": texte, "base_version_id": base}))
    v = _version(client, h, pid, sid)
    _ok(client.post(f"/api/atelier/{pid}/sections/{sid}/inserer-preuve", headers=h,
                    json={"preuve_id": sal["id"], "base_version_id": v["id"]}))
    for _ in range(2):          # avant, puis après la suppression de la fiche (le salarié est parti)
        r = client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={"cible_mots": 40})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "cv_dans_la_partie", r.text
        assert client.delete(f"/api/preuves/{sal['id']}", headers=h).status_code in (204, 404)
    assert envoyes == []


def test_forme_d_un_cv_reconnue_sans_sa_fiche():
    from app.services import preuves_atelier as pa
    b = pa.bloc("salarie", {"nom": "Yann Tanguy", "fonction": "Conducteur de travaux", "experience_annees": 15,
                            "diplomes": "BTS"})
    assert pa._cv_par_forme("Intro.\n\n" + b) == ["Yann Tanguy"]
    assert pa._cv_par_forme("**Maëlys Kerbrat**, conductrice de travaux [F2]\n- Expérience : 17 ans [F2]") == [
        "Maëlys Kerbrat"]
    assert pa._cv_par_forme("Nos références :\n- Acheteur : Mairie de Quimper\n- Année : 2024") == []
    assert pa._cv_par_forme("Notre entreprise a une expérience de 15 ans.") == []
