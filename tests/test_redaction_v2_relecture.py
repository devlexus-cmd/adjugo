"""
Rédaction, vague 2 — relecture croisée de l'atelier (trois relecteurs : doctrine, français et écrans,
exactitude). Chaque test reproduit une remarque vérifiée, puis vérifie la correction :

 • A0 : une phrase sur l'entreprise ne passe plus pour une phrase sur le marché parce qu'elle
   commence par « Le marché », « Le site », « Commune de… » ; les nombres seuls d'un tableau, les
   noms propres en tête de phrase (et après « M. ») sont contrôlés ; « Raccourcir » ne blanchit
   plus un fait inventé réécrit (« quinze » → « 15 », « ISO 14001 » → « ISO14001 ») ; aucun plafond
   silencieux ;
 • vague 4 préparée : le brouillon d'un partenaire ne sort jamais (export, dossier commun,
   compteur, export RGPD) et la reconstruction du plan ne retire pas sa partie ;
 • le cadre imposé commande : une question retirée puis remise reprend sa place ;
 • quota 6a : le plafond ne se contourne plus (plan reconstruit, parties ajoutées), jamais deux
   analyses pour un dossier, pas de rédaction gratuite si la première tombe en panne ;
 • le plan dit vrai : critères à vérifier, dossier du marché absent, bases indisponibles, poids
   lu par vous, grille confirmée après coup (ajout, sans reconstruction) ;
 • textes : fichier imposé (une phrase par cas), pluriels, « Relue » / « Validée », plus
   d'« étape Préparer », raisons de dérogation selon ce qui bloque, « [À compléter] » surligné
   dans le PDF, « Mon savoir-faire » vide signalé.
Aucun appel réseau : le client IA est simulé.
"""
import io
import json
import threading
import zipfile

import pytest

from app.services import atelier as at
from app.services import atelier_plan as ap
from app.services import faits_a_relire as far
from app.services import grille_notation as gn
from app.services import llm
from tests.test_redaction_socle0 import _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import (SOURCES_ENT, _attendre, _creer, _ecrire, _etat, _get_project, _projet,
                                             _redige, _usage, _valider_tout, _zip, RC, CADRE)


def _faits(texte, section_entreprise=True, sources=SOURCES_ENT):
    return [(x["fait"], x["type"]) for x in far.a_relire(texte, sources, noms_entreprise=["Breizh Couverture"],
                                                          section_entreprise=section_entreprise)]


# ═══ A0 : qui parle de quoi ══════════════════════════════════════════════════════════════

@pytest.mark.parametrize("section_entreprise", [True, False])
def test_a0_references_et_phrases_qui_commencent_par_le_marche_ou_le_site_sont_controlees(section_entreprise):
    refs = ("- Commune de Quimperlé : réfection de 1 200 m² de toiture en 2021, 180 000 € HT.\n"
            "- Ville de Brest : couverture zinc du groupe scolaire Jean Moulin, 2022, 240 000 € HT.\n"
            "- Mairie de Lorient : zinguerie de la médiathèque, 2023.\n"
            "- Département du Finistère : couverture d'un collège, 2020.")
    got = _faits(refs, section_entreprise)
    for attendu in ("Commune de Quimperlé", "Ville de Brest", "Jean Moulin", "Mairie de Lorient", "Département du Finistère",
                    "1 200 m²", "180 000 €", "2021", "2023", "2020"):
        assert attendu in {f for f, _t in got}, attendu
    got = {f for f, _t in _faits("Le marché sera exécuté par 15 compagnons certifiés Qualibat 1312, avec 3 nacelles "
                                 "de 18 m et une intervention sous 2 heures. Le site sera sécurisé par 4 agents "
                                 "formés CACES R486.", section_entreprise)}
    assert {"15 compagnons", "Qualibat 1312", "3 nacelles", "2 heures", "4 agents", "CACES R486"} <= got


@pytest.mark.parametrize("phrase", [
    "Le CCTP prévoit une couverture en zinc de 450 m2.",
    "Le maître d'ouvrage impose la certification ISO 14001.",
    "Selon le règlement de la consultation, le délai d'exécution est de 12 mois.",
    "Le CCTP, dans son article 3.2 relatif à la couverture, prévoit une surface de 450 m2.",
])
def test_a0_ce_que_demande_une_piece_reste_une_phrase_sur_le_marche_meme_dans_une_partie_moyens(phrase):
    assert _faits(phrase, True) == [] and _faits(phrase, False) == []


def test_a0_lieu_decrit_hors_des_parties_sur_l_entreprise_seulement():
    t = "Le site comprend 3 bâtiments."
    assert _faits(t, False) == []                                     # « Compréhension du besoin »
    assert _faits(t, True) == [("3 bâtiments", far.CHIFFRE)]          # partie Moyens : côté strict
    # Une description qui cite des moyens parle de l'entreprise, partout.
    assert ("15 compagnons", far.CHIFFRE) in _faits("Le projet comprend une équipe de 15 compagnons.", False)
    assert ("2 nacelles", far.CHIFFRE) in _faits("Le site comprend 2 nacelles.", False)


def test_a0_tableau_de_moyens_chaque_nombre_seul_est_controle_avec_le_libelle_de_sa_ligne():
    t = ("Nos moyens affectés au chantier :\n| Poste | Effectif |\n|---|---|\n"
         "| Compagnons couvreurs | 15 |\n| Chefs d'équipe | 3 |\n| Nacelles | 2 |")
    got = _faits(t)
    assert ("15", far.CHIFFRE) in got and ("3", far.CHIFFRE) in got and ("2", far.CHIFFRE) in got
    assert not any(f == "Compagnons" for f, _t in got)                # un libellé n'est pas un nom propre
    # Une source qui dit 15 compagnons : la ligne passe ; 15 nacelles ne prouve pas 15 compagnons.
    assert ("15", far.CHIFFRE) not in _faits(t, sources=["Effectif : 15 compagnons."])
    assert ("15", far.CHIFFRE) in _faits(t, sources=["Matériel : 15 nacelles."])


@pytest.mark.parametrize("phrase,nom", [
    ("Paul Durand, notre conducteur de travaux, pilotera le chantier.", "Paul Durand"),
    ("M. Paul Durand pilotera le chantier.", "Paul Durand"),
    ("Vinci Construction nous a confié la couverture du lycée.", "Vinci Construction"),
    ("Notre conducteur de travaux, Paul Durand, pilotera le chantier.", "Paul Durand"),
    ("Référence : Mairie de Lorient, couverture de la médiathèque.", "Mairie de Lorient"),
])
def test_a0_nom_propre_en_tete_de_phrase_ou_apres_un_titre(phrase, nom):
    assert (nom, far.NOM_PROPRE) in _faits(phrase)


def test_a0_mots_d_ouverture_et_titres_ne_coupent_pas_et_ne_sont_pas_des_noms():
    assert far.phrases("M. Durand et Mme Le Goff arrivent. Dr. Martin aussi.") == [
        ("M. Durand et Mme Le Goff arrivent.", False, False), ("Dr. Martin aussi.", False, False)]
    assert _faits("Nous intervenons en site occupé. Pour chaque zone, un balisage est posé.") == []


def test_a0_aucun_plafond_silencieux_le_reste_est_compte_et_bloque(monkeypatch):
    rows = "\n".join(f"| Mairie de Ville{i} | {2000 + i} | {100 + i} 000 € |" for i in range(25))
    texte = "| Client | Année | Montant |\n|---|---|---|\n" + rows
    tous = far.a_relire(texte, SOURCES_ENT, section_entreprise=True)
    assert len(tous) == 75                                               # 3 faits par ligne, 25 lignes
    assert {"Mairie de Ville24", "2024", "124 000 €"} <= {x["fait"] for x in tous}   # la ligne 25 est contrôlée
    monkeypatch.setattr(far, "MAX_FAITS", 10)
    faits = far.controle(texte, SOURCES_ENT, section_entreprise=True)
    assert len(faits) == 11 and faits[-1]["type"] == far.RESTE and faits[-1]["nombre"] == 65
    assert far.non_traites(faits) == 75
    relus = [dict(x, statut=far.RELU) if x["type"] != far.RESTE else x for x in faits]
    assert far.non_traites(relus) == 65                                  # le reste bloque toujours


# ═══ A0 : « Raccourcir » et les modifications de l'utilisateur ════════════════════════════

LONG = ("Nous mobilisons quinze compagnons couvreurs sur le chantier. "
        + "Nous organisons le chantier par zones successives, avec un balisage quotidien et une information des usagers. " * 6
        + "Nous sommes certifiés ISO 14001.")
COURT = "Nous mobilisons 15 couvreurs. Nous organisons le chantier par zones. Nous sommes certifiés ISO14001."


def test_raccourcir_ne_blanchit_pas_les_faits_a_relire_reecrits(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    sid = _creer(client, h, pid)["sections"][2]["id"]

    def ans(kw):
        return (COURT if "Tu raccourcis" in llm._flatten_content(kw.get("system")) else LONG), "end_turn"
    fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={})
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert {f["fait"] for f in s["version_courante"]["faits"]} == {"quinze", "ISO 14001"}
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={"cible_mots": 30})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert s["version_courante"]["texte"] == COURT
    assert {(f["fait"], f["statut"]) for f in s["version_courante"]["faits"]} == {
        ("15 couvreurs", "a_relire"), ("ISO14001", "a_relire")}
    assert s["faits_a_relire"] == 2 and "faits_a_relire" in [x["code"] for x in _etat(client, h, pid)["blocage"]["raisons"]]


def test_relu_par_vous_suit_le_meme_fait_avec_la_meme_unite_jamais_une_autre():
    v1 = far.controle(LONG, SOURCES_ENT)
    relus = [dict(x, statut=far.RELU, relu_par=1) for x in v1]
    meme = far.controle("Nous mobilisons 15 compagnons. Nous sommes certifiés ISO 14001.", SOURCES_ENT,
                        declares=[LONG], anciens=relus, reprise="fait")
    assert {(f["fait"], f["statut"]) for f in meme} == {("15 compagnons", far.RELU), ("ISO 14001", far.RELU)}
    autre = far.controle(COURT, SOURCES_ENT, declares=[LONG], anciens=relus, reprise="fait")
    assert ("15 couvreurs", far.A_RELIRE) in {(f["fait"], f["statut"]) for f in autre}
    # L'utilisateur réécrit lui-même « quinze compagnons » en « 15 compagnons » : toujours à relire ;
    # « 12 mois » qu'il ajoute n'est pas « quinze » : c'est sa déclaration.
    user = "Nous mobilisons 15 compagnons. Le chantier dure 12 mois."
    faits = far.controle(user, SOURCES_ENT, declares=[user], anciens=v1, reprise="phrase")
    assert [(f["fait"], f["statut"]) for f in faits] == [("15 compagnons", far.A_RELIRE)]


def test_a0_de_bout_en_bout_le_marche_sera_execute_par_bloque_l_export(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sec = st["sections"][0]                                            # 1.1 Encadrement du chantier
    ans, _seen = _redige("Le marché sera exécuté par 15 compagnons certifiés Qualibat 1312. "
                         "Le site sera sécurisé par 4 agents formés CACES R486.")
    fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/rediger", headers=h, json={})
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sec["id"])
    assert {"15 compagnons", "Qualibat 1312", "4 agents", "CACES R486"} <= {f["fait"] for f in s["version_courante"]["faits"]}


# ═══ Vague 4 préparée : le brouillon d'un partenaire ne sort jamais ══════════════════════

def _partie_partenaire(pid, sid, texte="Brouillon privé du couvreur, non envoyé."):
    from app.models import DossierSection
    db = _db()
    try:
        s = db.get(DossierSection, sid)
        s.author_kind, s.author_invite_id = at.AUTEUR_INVITATION, 999
        db.commit()
        v = at.ajouter_version(db, s, texte=texte, origine="utilisateur", ia=False)
        db.commit()
        return v.id
    finally:
        db.close()


def test_brouillon_d_un_partenaire_absent_de_l_export_du_dossier_commun_du_compteur_et_du_rgpd(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][1]["id"]
    vid = _partie_partenaire(pid, sid)
    for s in st["sections"]:
        if s["id"] != sid:
            s2 = _ecrire(client, h, pid, s, "Nous intervenons par zones.")
            client.post(f"/api/atelier/{pid}/sections/{s['id']}/valider", headers=h,
                        json={"version_id": s2["version_courante"]["id"]})
    st = _etat(client, h, pid)
    assert "Brouillon privé" not in json.dumps(st, ensure_ascii=False)
    part = next(x for x in st["sections"] if x["id"] == sid)
    assert part["compteur"]["mots"] == 0                              # rien du brouillon dans le compteur
    gate = st["blocage"]
    assert [r["code"] for r in gate["raisons"]] == ["attente_partenaire"]
    assert "en attente du partenaire" in gate["raisons"][0]["message"]
    assert [x["code"] for x in st["derogations_possibles"]] == ["partenaire_dans_word", "depot_en_l_etat", "autre"]
    db = _db()
    try:
        commun = at.dossier_commun(db, _get_project(pid), _user_id(auth["email"]))
    finally:
        db.close()
    assert "Brouillon privé" not in commun["markdown"] and commun["files"] == {}
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h,
                    json={"raison": "partenaire_dans_word", "texte": "Le couvreur envoie demain",
                          "etat_hash": gate["etat_hash"]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode("utf-8")
    assert "Brouillon privé du couvreur" not in xml
    r = client.get("/api/rgpd/export", headers=h)
    assert r.status_code == 200 and "Brouillon privé du couvreur" not in r.text
    # Le partenaire envoie (valide) sa partie, puis rédige un nouveau brouillon : seul l'envoyé sort.
    from app.models import DossierSection
    db = _db()
    try:
        s = db.get(DossierSection, sid)
        s.validated_version_id, s.validated_hash, s.statut = vid, "", at.VALIDE
        db.commit()
        at.ajouter_version(db, s, texte="Second brouillon privé, jamais envoyé.", origine="utilisateur", ia=False)
        db.commit()
    finally:
        db.close()
    st = _etat(client, h, pid)
    assert "attente_partenaire" not in [r["code"] for r in st["blocage"]["raisons"]]
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    xml = zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode("utf-8")
    assert "Brouillon privé du couvreur" in xml and "Second brouillon" not in xml
    assert "Second brouillon" not in client.get("/api/rgpd/export", headers=h).text


def test_reconstruire_le_plan_ne_retire_jamais_la_partie_d_un_partenaire(client, auth):
    h = auth["headers"]
    pid = _projet(client, h, impose=False)
    st = _creer(client, h, pid, base="libre")
    sid = st["sections"][3]["id"]
    _partie_partenaire(pid, sid)
    r = client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "libre", "remplacer": False})
    assert r.status_code == 200, r.text                             # le brouillon d'un autre ne demande rien
    st = r.json()
    assert sid in [s["id"] for s in st["sections"]] and st["sections"][-1]["id"] == sid
    assert len(st["sections"]) == 8


# ═══ Le cadre imposé commande : remettre une question la remet à sa place ═════════════════

def test_question_du_cadre_retiree_puis_remise_reprend_sa_place_dans_le_word(client, auth):
    import docx
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][1]["id"]                                     # 1.2 Équipe d'exécution
    assert client.delete(f"/api/atelier/{pid}/sections/{sid}", headers=h).status_code == 200
    assert client.post(f"/api/atelier/{pid}/sections/{sid}/remettre", headers=h).status_code == 200
    st = _etat(client, h, pid)
    assert [s["titre"] for s in st["sections"]] == ["1.1 Encadrement du chantier", "1.2 Équipe d'exécution",
                                                    "2. Méthodologie", "3. Démarche environnementale"]
    _valider_tout(client, h, pid, "Nous intervenons par zones.")
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    d = docx.Document(io.BytesIO(r.content))
    heads = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
    assert heads[heads.index("Sommaire") + 1:] == ["1. Moyens humains", "1.1 Encadrement du chantier",
                                                   "1.2 Équipe d'exécution", "2. Méthodologie",
                                                   "3. Démarche environnementale"]


# ═══ Quota 6a ═══════════════════════════════════════════════════════════════════════════

def test_plafond_des_refontes_ne_se_contourne_pas_en_reconstruisant_ou_en_ajoutant(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_REGEN_GRATUITES", "2")
    h = auth["headers"]
    pid = _projet(client, h, impose=False)
    _creer(client, h, pid, base="libre")
    fake_llm(lambda kw: ("Notre méthodologie en site occupé.", "end_turn"))
    u0 = _usage(auth["email"])
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 202 and _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    assert _usage(auth["email"]) == u0 + 1 and r.json()["quota"]["premieres_incluses"] == 7
    r = client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "libre", "remplacer": True})
    assert r.status_code == 200
    # 7 parties neuves après la reconstruction : ce sont des refontes (2 gratuites, 5 à confirmer).
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "debit_a_confirmer" and r.json()["detail"]["cout"] == 5
    assert "Il reste 2 refontes gratuites" in r.json()["detail"]["message"]
    assert _usage(auth["email"]) == u0 + 1
    # Une partie de plus dans le plan (8 parties) : sa première rédaction est comprise.
    s1 = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Annexe"}).json()
    r = client.post(f"/api/atelier/{pid}/sections/{s1['id']}/rediger", headers=h, json={})
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    assert r.json()["quota"]["regenerations_utilisees"] == 0 and r.json()["quota"]["premieres_incluses"] == 8
    # Ajouter, rédiger, retirer, recommencer : chaque nouvelle partie de remplacement est une refonte.
    for k, (titre, attendu) in enumerate((("Annexe bis", 1), ("Annexe ter", 2))):
        client.delete(f"/api/atelier/{pid}/sections/{s1['id']}", headers=h)
        s1 = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": titre}).json()
        r = client.post(f"/api/atelier/{pid}/sections/{s1['id']}/rediger", headers=h, json={})
        assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
        assert r.json()["quota"]["regenerations_utilisees"] == attendu
    client.delete(f"/api/atelier/{pid}/sections/{s1['id']}", headers=h)
    s1 = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Annexe quater"}).json()
    r = client.post(f"/api/atelier/{pid}/sections/{s1['id']}/rediger", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "debit_a_confirmer"
    assert "Les 2 refontes gratuites de ce dossier sont utilisées" in r.json()["detail"]["message"]
    assert _usage(auth["email"]) == u0 + 1


def test_deux_redactions_simultanees_sur_un_dossier_neuf_une_seule_analyse(client, auth, monkeypatch):
    import app.services.jobs as jobs
    from app.core.org import data_owner_id, member_ids
    from app.models import DossierSection, Project, User
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    s1, s2 = st["sections"][0]["id"], st["sections"][1]["id"]
    monkeypatch.setattr(jobs, "run_in_thread", lambda *a, **k: None)   # on ne regarde que le débit
    uid = _user_id(auth["email"])
    u0 = _usage(auth["email"])

    def charger():
        db = _db()
        u = db.get(User, uid)
        return db, u, db.get(Project, pid), at.get_dossier(db, pid, data_owner_id(u, db)), member_ids(u, db)
    A, B = charger(), charger()                  # les deux requêtes ont lu le dossier avant tout débit
    try:
        (db, u, p, d, mids) = A
        at.lancer(db, u, p, d, [db.get(DossierSection, s1)], at.JOB_REDIGER, at.Lecteur.organisation(d.owner_id, u), mids)
        (db, u, p, d, mids) = B
        with pytest.raises(at.AtelierError) as e:
            at.lancer(db, u, p, d, [db.get(DossierSection, s2)], at.JOB_REDIGER,
                      at.Lecteur.organisation(d.owner_id, u), mids)
        assert e.value.code == "premiere_redaction_en_cours"
        assert db.get(DossierSection, s2).job_id is None                 # la partie est libérée
    finally:
        A[0].close()
        B[0].close()
    assert _usage(auth["email"]) == u0 + 1


def test_pendant_la_premiere_redaction_aucune_autre_puis_panne_tout_est_rendu(client, auth, fake_llm):
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    s1, s2 = st["sections"][0], st["sections"][1]
    gate = threading.Event()

    def ans(kw):
        if "PARTIE À RÉDIGER : " + s1["intitule"] in llm._flatten_content(kw["messages"][0]["content"]):
            gate.wait(10)
            raise RuntimeError("panne")
        return "Texte rédigé pour la partie.", "end_turn"
    fake_llm(ans)
    u0 = _usage(auth["email"])
    ra = client.post(f"/api/atelier/{pid}/sections/{s1['id']}/rediger", headers=h, json={})
    assert ra.status_code == 202
    rb = client.post(f"/api/atelier/{pid}/sections/{s2['id']}/rediger", headers=h, json={})
    assert rb.status_code == 409 and rb.json()["detail"]["code"] == "premiere_redaction_en_cours"
    assert "attendez" in rb.json()["detail"]["message"]
    gate.set()
    assert _attendre(client, h, pid, ra.json()["tache"]["id"])["status"] == "error"
    assert _usage(auth["email"]) == u0 and _etat(client, h, pid)["quota"]["analyse_debitee"] is False
    rb = client.post(f"/api/atelier/{pid}/sections/{s2['id']}/rediger", headers=h, json={})
    assert rb.status_code == 202 and _attendre(client, h, pid, rb.json()["tache"]["id"])["status"] == "done"
    assert _usage(auth["email"]) == u0 + 1 and _etat(client, h, pid)["quota"]["analyse_debitee"] is True


def test_l_analyse_n_est_pas_rendue_si_l_ia_a_deja_servi_au_dossier(client, auth):
    from app.models import DossierPresentation, DossierSection, Job
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    s1, s2 = st["sections"][0]["id"], st["sections"][1]["id"]
    uid = _user_id(auth["email"])
    db = _db()
    try:
        from app.core.quota import consume_analysis
        from app.models import User
        consume_analysis(db.get(User, uid), db)
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).first()
        d.analyse_debitee = True
        ja = Job(user_id=uid, kind=at.JOB_REDIGER, status="error", label="x",
                 result={"_debit": {"analyse": True, "sections": {str(s1): "incluse"}, "dossier_id": d.id}})
        jb = Job(user_id=uid, kind=at.JOB_REDIGER, status="done", label="y", result={})
        db.add_all([ja, jb])
        db.flush()
        d.job_analyse_id = ja.id
        at.ajouter_version(db, db.get(DossierSection, s2), texte="Texte de l'IA.", origine=at.IA, ia=True, job_id=jb.id)
        db.commit()
        u1 = _usage(auth["email"])
        at.rembourser(db, db.get(Job, ja.id))
        assert _usage(auth["email"]) == u1                               # l'IA a servi : l'analyse reste due
        assert db.query(DossierPresentation).get(d.id).analyse_debitee is True
        assert db.get(Job, ja.id).result["_debit"]["analyse_conservee"] is True
    finally:
        db.close()


# ═══ Le plan dit vrai ═══════════════════════════════════════════════════════════════════

def _grille_en_attente():
    g = {"criteres": [
        {"id": "c1", "critere": "Valeur technique", "statut": "retrouve", "poids": "60 %", "phrase": "Valeur technique : 60 %"},
        {"id": "c2", "critere": "Délais d'exécution", "statut": "a_verifier", "poids": "", "phrase": "Délais d'exécution"},
        {"id": "c3", "critere": "Environnement", "statut": "a_verifier", "poids": "", "phrase": "Environnement"},
        {"id": "c4", "critere": "Prix", "statut": "retrouve", "poids": "40 %", "phrase": "Prix : 40 %"}],
        "contraintes": {}}
    return gn.refresh(g)


def test_plan_ne_dit_jamais_un_seul_critere_quand_d_autres_sont_a_verifier():
    p = ap.build_plan({"details": {"grille_notation": _grille_en_attente()}}, "", "auto")
    assert p["source"] == ap.GRILLE and len(p["sections"]) == 7
    assert "ne donne qu'un critère" not in p["message"]
    assert "2 critères restent à vérifier dans « Comment vous serez noté » : confirmez-les pour qu'ils entrent dans le plan." in p["message"]
    assert p["criteres_en_attente"] == 2
    seul = gn.refresh({"criteres": [_grille_en_attente()["criteres"][0]], "contraintes": {}})
    assert "ne donne qu'un critère" in ap.build_plan({"details": {"grille_notation": seul}}, "", "auto")["message"]


def test_critere_confirme_apres_coup_s_ajoute_au_plan_avec_son_poids_lu_par_vous(client, auth):
    from app.models import Project
    h = auth["headers"]
    r = client.post("/api/projects/", headers=h, json={"name": "Toiture", "client": "Ville de Lorient"})
    pid = r.json()["id"]
    db = _db()
    try:
        p = db.get(Project, pid)
        p.ai_analysis = {"summary": "x", "dce_available": True, "dce_excerpt": RC,
                         "details": {"grille_notation": _grille_en_attente()}}
        db.commit()
    finally:
        db.close()
    st = _creer(client, h, pid)
    assert st["dossier"]["plan_source"] == "grille" and st["grille"] is None
    assert st["dossier"]["plan"]["message_en_attente"].startswith("2 critères restent")
    # L'utilisateur confirme « Délais d'exécution » avec le poids qu'il a lu (40 %).
    r = client.post("/api/sourcing/grille/choix", headers=h,
                    json={"project_id": pid, "critere_id": "c2", "choix": "confirme", "poids": "40 %"})
    assert r.status_code == 200, r.text
    st = _etat(client, h, pid)
    assert [x["critere"] for x in st["grille"]["nouveaux"]] == ["Délais d'exécution"]
    assert "depuis la création du plan" in st["grille"]["message"] and st["grille"]["peut_appliquer"] is True
    n0 = len(st["sections"])
    r = client.post(f"/api/atelier/{pid}/plan/grille", headers=h)
    assert r.status_code == 200, r.text
    st = r.json()
    assert len(st["sections"]) == n0 + 1 and st["grille"] is None and st["application"]["ajoutees"] == 1
    s = st["sections"][-1]
    assert s["intitule"] == "Délais d'exécution" and s["poids"] == "40 %" and s["poids_source"] == "utilisateur"
    assert st["sections"][0]["poids_source"] == "reglement"
    assert client.post(f"/api/atelier/{pid}/plan/grille", headers=h).status_code == 409   # rien de plus
    # L'IA reçoit la provenance du poids.
    from app.services.agents import memoire as moteur
    assert "poids lu dans le règlement par l'entreprise : 40 %" in moteur._consigne_partie(
        {"titre": "Délais", "critere": "Délais d'exécution", "poids": "40 %", "poids_source": "utilisateur"})


def test_sans_dossier_du_marche_le_plan_le_dit_et_l_atelier_aussi(client, auth):
    h = auth["headers"]
    pid = _projet(client, h, with_dce=False)
    prop = client.get(f"/api/atelier/{pid}", headers=h).json()["proposition"]
    assert prop["dossier_present"] is False and prop["message"] == ap.MSG_SANS_DOSSIER
    assert "Aucun critère n'a été retrouvé dans le règlement" not in prop["message"]
    st = _creer(client, h, pid)
    assert st["dossier_acheteur"]["present"] is False and st["dossier_acheteur"]["source"] == "aucun"
    assert st["dossier_acheteur"]["message_absent"].startswith("Aucun dossier du marché importé")


def test_bases_indisponibles_et_plan_simple_choisi(client, auth):
    h = auth["headers"]
    pid = _projet(client, h)
    prop = client.get(f"/api/atelier/{pid}", headers=h).json()["proposition"]
    assert prop["bases"] == {"auto": True, "cadre": True, "grille": True, "libre": True}
    prop = client.get(f"/api/atelier/{pid}?base=libre", headers=h).json()["proposition"]
    assert prop["message"] == ap.MSG_LIBRE_CHOISI
    # Grille retrouvée mais aucun cadre de réponse : « cadre » est indisponible, et le dire.
    an = {"details": {"grille_notation": gn.refresh({"criteres": _grille_en_attente()["criteres"][:1] + [
        dict(_grille_en_attente()["criteres"][0], id="c9", critere="Qualité")], "contraintes": {}})}}
    p = ap.build_plan(an, "", "cadre")
    assert p["bases"]["cadre"] is False and p["message"].startswith(ap.MSG_PAS_DE_CADRE)


def test_dossier_du_marche_reimporte_le_signal_reste_apres_une_redaction(client, auth, fake_llm):
    from app.models import Project
    from app.services.dossier import save_to_dossier
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    db = _db()
    try:
        p = db.get(Project, pid)
        save_to_dossier(db, p.user_id, pid, "DCE", "DCE_v2.zip",
                        _zip({"01_Reglement_de_la_consultation.txt": RC, "02_Cadre_de_reponse_technique.txt":
                              CADRE + "4. Planning\nDécrivez le planning.\n"}), "application/zip")
        db.commit()
    finally:
        db.close()
    assert _etat(client, h, pid)["dossier_acheteur"]["a_change"] is True
    ans, _seen = _redige("Notre méthodologie.")
    fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/sections/{st['sections'][0]['id']}/rediger", headers=h, json={})
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    assert _etat(client, h, pid)["dossier_acheteur"]["a_change"] is True     # le plan suit toujours l'ancien
    r = client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "auto", "remplacer": True})
    assert r.json()["dossier_acheteur"]["a_change"] is False and len(r.json()["sections"]) == 5


# ═══ Textes ═════════════════════════════════════════════════════════════════════════════

def test_fichier_impose_une_seule_phrase_par_cas():
    assert ap.avertissement_fichier(True, ap.GRILLE) == (
        "Ce marché impose son propre fichier de réponse : recopiez votre texte dans le fichier de l'acheteur, "
        "ne déposez pas le fichier Word d'Adjugo seul.")
    for src in (ap.CADRE, ap.GRILLE, ap.LIBRE):
        m = ap.avertissement_fichier(True, src)
        assert m.count("recopi") == 1 and "recopiez-y" not in m and "vous devrez" not in m
    assert ap.avertissement_fichier(False, ap.CADRE) == ""


def test_echecs_au_pluriel_libelles_au_feminin_et_plus_d_etape_preparer(client, auth, fake_llm):
    h = auth["headers"]
    pid = _projet(client, h)
    _creer(client, h, pid)

    def ans(kw):
        user = llm._flatten_content(kw["messages"][0]["content"])
        if "PARTIE À RÉDIGER : Méthodologie" in user or "PARTIE À RÉDIGER : Démarche environnementale" in user:
            raise RuntimeError("panne")
        return "Texte de la partie.", "end_turn"
    fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    job = _attendre(client, h, pid, r.json()["tache"]["id"])
    assert job["result"]["message"] == ("2 parties n'ont pas pu être rédigées (service d'IA indisponible) : rien n'a "
                                        "été débité pour elles, réessayez.")
    assert at.STATUTS[at.RELU] == "Relue" and at.STATUTS[at.VALIDE] == "Validée"
    db = _db()
    try:
        commun = at.dossier_commun(db, _get_project(_projet(client, h)), _user_id(auth["email"]))
    finally:
        db.close()
    assert "« Préparer »" not in " ".join(commun["warnings"]) and "carte « Dossier de présentation »" in commun["warnings"][0]
    r = client.post("/api/knowledge/memoire", headers=h)
    assert r.status_code == 410 and "Préparer" not in r.text


def test_limite_depassee_raisons_de_derogation_propres_a_la_limite(client, auth):
    h = auth["headers"]
    pid = _projet(client, h)
    _creer(client, h, pid)
    long = "\n\n".join(["Nous organisons le chantier par zones successives, avec un balisage quotidien "
                        "et une information des usagers du groupe scolaire."] * 60)
    st = _valider_tout(client, h, pid, long)
    assert [x["code"] for x in st["derogations_possibles"]] == ["reduirai_dans_word", "depot_en_l_etat", "autre"]
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h,
                    json={"raison": "completerai_dans_word", "texte": "x y z", "etat_hash": st["blocage"]["etat_hash"]})
    assert r.status_code == 422


def test_pdf_exporte_avec_derogation_surligne_les_passages_a_completer(client, auth):
    from pypdf import PdfReader
    h = auth["headers"]
    pid = _projet(client, h)
    _creer(client, h, pid)
    st = _valider_tout(client, h, pid, "Nous intervenons. [À compléter : planning détaillé]")
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h,
                    json={"raison": "completerai_dans_word", "texte": "Planning lundi", "etat_hash": st["blocage"]["etat_hash"]})
    assert r.status_code == 200
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "pdf"})
    assert r.status_code == 200
    flux = b"".join(p.get_contents().get_data() for p in PdfReader(io.BytesIO(r.content)).pages
                    if p.get_contents() is not None)
    assert b"1 .945098 .658824 rg" in flux                              # fond #FFF1A8 du surlignage


def test_mon_savoir_faire_vide_est_signale(client, auth):
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    assert st["savoir_faire"]["vide"] is True and "« Mon savoir-faire »" in st["savoir_faire"]["message"]
