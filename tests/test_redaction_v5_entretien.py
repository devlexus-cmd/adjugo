"""
Rédaction, vague 5 — D : l'entretien chantier, « Adjugo demande au lieu de deviner » (étude § 6.9).

Contrat : docs/REDACTION_V5.md (section D). Invariants vérifiés :
 • déclenchement SANS IA : la banque (≈ 40 questions BTP) se déclenche sur des mots du dossier de l'acheteur ;
   chaque question porte la phrase du dossier qui la motive, retrouvée mot pour mot ; une phrase niée ne déclenche
   rien ; 8 questions au plus ; classées par le poids (tel qu'écrit) du critère concerné ; l'environnement
   déclenche toujours une question ;
 • « Qui sera le chef de chantier ? » propose la liste « Équipe » de « Mes preuves » ; le nom ne part jamais en clair
   à l'IA (étiquette), le CV jamais ;
 • une question sautée laisse « [À compléter : … ] » dans la partie concernée (consigne de l'IA, et ajouté sans IA
   s'il manque) ; « sans objet » ne laisse rien ;
 • les réponses forment la fiche chantier : des faits [R#] « déclaré par vous » numérotés, remis à l'IA et reliés par
   le contrôle des faits de l'atelier ; retirés à l'export ;
 • groupement : une question qui relève du lot d'un partenaire lui est adressée ; il la lit et y répond dans SON
   espace (clé du lien, avertissement, identité) ; le chef de file lit sa réponse comme « déclaré par » ce
   partenaire, sans pouvoir la modifier ; l'IA du partenaire ne reçoit que SES réponses ; retrait : ses réponses
   effacées ;
 • option IA : questions supplémentaires gardées seulement si leur phrase est retrouvée mot pour mot (et sans nombre
   absent de la phrase) ; débit comme une refonte ; rien de retenu ou IA en panne : rien n'est décompté ;
   tenant_scope de l'organisation ;
 • démo : l'entretien de la vitrine se lit sans IA ; toute écriture est refusée ;
 • migration z1entretienchantier (SQLite : base neuve, retour arrière, remontée, rejeu).
Aucun appel réseau : le client IA est simulé.
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

from app.services import entretien_banque as eb
from app.services import entretien_chantier as ec
from app.services import llm
from tests.test_redaction_socle0 import _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _analysis, _zip

RC = ("REGLEMENT DE LA CONSULTATION\n"
      "Article 1 - Objet\nRéfection de la toiture du groupe scolaire Paul Bert.\n"
      "Article 5 - Visite\nLa visite du site est obligatoire avant la remise des offres.\n"
      "Article 7 - Critères de jugement des offres\n"
      "Méthodologie d'exécution : 30 %\n"
      "Organisation du chantier en site occupé : 20 %\n"
      "Moyens humains et encadrement : 10 %\n"
      "Démarche environnementale : 10 %\n"
      "Prix : 30 %\n"
      "Article 8 - Présentation des offres\nLe candidat remettra un mémoire technique.\n")
CCTP = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES\n"
        "Article 1 - Contraintes du site\n"
        "L'école reste en activité pendant toute la durée des travaux.\n"
        "Les livraisons sont interdites aux heures d'entrée et de sortie des élèves.\n"
        "Article 2 - Amiante\nLe repérage avant travaux n'a révélé aucune présence d'amiante.\n"
        "Article 3 - Couverture\nLa couverture existante en zinc est déposée par zones successives.\n"
        "Article 4 - Déchets\nLes déchets sont triés sur le chantier et évacués vers des filières agréées.\n"
        "Article 5 - Voirie\nLe stationnement des engins sur la voie publique fait l'objet d'un arrêté de circulation.\n")
CRITERES = [{"critere": "Méthodologie d'exécution", "ponderation": "30 %", "extrait": "Méthodologie d'exécution : 30 %"},
            {"critere": "Organisation du chantier en site occupé", "ponderation": "20 %",
             "extrait": "Organisation du chantier en site occupé : 20 %"},
            {"critere": "Moyens humains et encadrement", "ponderation": "10 %",
             "extrait": "Moyens humains et encadrement : 10 %"},
            {"critere": "Démarche environnementale", "ponderation": "10 %", "extrait": "Démarche environnementale : 10 %"},
            {"critere": "Prix", "ponderation": "30 %", "extrait": "Prix : 30 %"}]
SECRET_CHEF = "PORTAILNORDSECRET"


def _projet_chantier(client, h, rc=RC, cctp=CCTP, criteres=CRITERES, name="Toiture du groupe scolaire Paul Bert"):
    """Un marché avec un dossier de l'acheteur (règlement, CCTP) et la grille « Comment vous serez noté »."""
    from app.models import Project
    from app.services import grille_notation as gn
    from app.services.analysis import extract_dce_text
    from app.services.dossier import save_to_dossier
    r = client.post("/api/projects/", headers=h, json={"name": name, "client": "Ville de Quimperlé"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    content = _zip({"01_Reglement_de_la_consultation.txt": rc, "03_CCTP.txt": cctp})
    db = _db()
    try:
        p = db.get(Project, pid)
        text, pieces = extract_dce_text("DCE.zip", content, max_chars=120000, with_pieces=True)
        a = _analysis(text, pieces, impose=False)
        det = a["details"]
        det["criteres_attribution"] = criteres
        det["grille_notation"] = gn.build_grille(det, text, pieces=pieces)
        p.ai_analysis = a
        save_to_dossier(db, p.user_id, pid, "DCE", "DCE.zip", content, "application/zip")
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/atelier/{pid}", headers=h, json={"base": "auto"})
    assert r.status_code == 201, r.text
    return pid, r.json()


def _entretien(client, h, pid, preparer=True):
    if preparer:
        r = client.post(f"/api/atelier/{pid}/entretien", headers=h)
    else:
        r = client.get(f"/api/atelier/{pid}/entretien", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _q(st, code):
    return next(x for x in st["questions"] if x["code"] == code)


def _repondre(client, h, pid, q, **body):
    body.setdefault("statut", "repondue")
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _partie(st, mot):
    return next(s for s in st["sections"] if mot.lower() in (s.get("intitule") or "").lower())


def _attendre(client, h, pid, jid):
    r = None
    for _ in range(300):
        r = client.get(f"/api/atelier/{pid}/taches/{jid}", headers=h)
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("done", "error"):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"tâche {jid} jamais terminée : {r.json() if r is not None else None}")


def _rediger(client, h, pid, sid):
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    return _attendre(client, h, pid, r.json()["tache"]["id"])


def _effacer_entretien(pid):
    from app.models import EntretienQuestion
    db = _db()
    try:
        db.query(EntretienQuestion).filter(EntretienQuestion.project_id == pid).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _version_db(sid):
    from app.models import DossierSection, DossierSectionVersion
    db = _db()
    try:
        s = db.get(DossierSection, sid)
        v = db.get(DossierSectionVersion, s.current_version_id)
        return {"texte": v.texte, "faits": v.faits or []}
    finally:
        db.close()


# ═══ 1. Déclenchement sans IA, ordre, environnement ═════════════════════════════════════

def test_banque_environ_quarante_questions_btp_bien_formees():
    assert 36 <= len(eb.BANQUE) <= 48
    for q in eb.BANQUE:
        assert q["question"].endswith("?") and len(q["question"]) <= ec.QUESTION_MAX, q["code"]
        assert q["declencheurs"] and q["criteres"] and q["parties"] and q["a_completer"], q["code"]
        for x in q["declencheurs"]:
            re.compile(x)
        assert not re.search(r"[\U0001F300-\U0001FAFF]", q["question"] + q["theme"])      # zéro émoji
        assert "consortium" not in q["question"].lower() and "vérifié" not in q["question"].lower()
    familles = {q["famille"] for q in eb.BANQUE}
    assert eb.ENVIRONNEMENT in familles
    codes = {q["code"] for q in eb.BANQUE}
    # Les déclencheurs que l'étude nomme (§ 6.9).
    assert {"site_occupe", "erp", "ecole", "nuit", "amiante", "plomb", "voirie", "coactivite", "abf", "phasage",
            "dechets", "bruit", "chef_chantier"} <= codes


def test_declenchement_sans_ia_phrase_motivante_ordre_et_environnement(client, auth, fake_llm):
    fake = fake_llm(lambda kw: ("ne doit pas être appelé", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h)
    # Préparé avec le dossier de présentation, sans IA ni débit.
    e = _entretien(client, h, pid, preparer=False)
    assert e["prepare"] is True and fake.calls == [] and st["quota"]["analyse_debitee"] is False
    # Un dossier d'avant la vague 5 (aucune question enregistrée) : la PROPOSITION, rien d'enregistré ; puis préparer.
    _effacer_entretien(pid)
    prop = _entretien(client, h, pid, preparer=False)
    assert prop["prepare"] is False and prop["questions"] and all(x["id"] is None for x in prop["questions"])
    assert client.get(f"/api/atelier/{pid}", headers=h).json()["entretien"]["proposees"] == len(prop["questions"])
    e = _entretien(client, h, pid)
    assert e["prepare"] is True and fake.calls == [] and e["preparation"]["creees"] == len(prop["questions"])
    codes = [x["code"] for x in e["questions"]]
    assert 1 <= len(codes) <= ec.MAX_QUESTIONS
    # Une phrase niée ne déclenche rien (« aucune présence d'amiante »).
    assert "amiante" not in codes
    for code in ("site_occupe", "ecole", "acces_toiture", "chef_chantier", "dechets"):
        assert code in codes, (code, codes)
    # Chaque question porte la phrase du dossier qui la motive, telle qu'écrite dans le dossier.
    dce = re.sub(r"\s+", " ", RC + " " + CCTP)
    for x in e["questions"]:
        assert x["motif"] and x["motif"]["phrase"], x
        assert re.sub(r"\s+", " ", x["motif"]["phrase"]) in dce, x["motif"]
    assert "L'école reste en activité" in _q(e, "site_occupe")["motif"]["phrase"]
    assert _q(e, "site_occupe")["motif"]["piece"]
    # Classées par le poids du critère concerné (tel qu'écrit dans le règlement).
    poids = [float(re.sub(r"[^\d,]", "", (x["critere"] or {}).get("poids") or "0").replace(",", ".") or 0)
             for x in e["questions"]]
    assert poids == sorted(poids, reverse=True), poids
    assert e["questions"][0]["critere"]["critere"].startswith("Méthodologie")
    assert _q(e, "site_occupe")["critere"]["poids"] == "20 %"
    # L'environnement est représenté.
    assert any(eb.PAR_CODE[c]["famille"] == eb.ENVIRONNEMENT for c in codes)
    # La partie concernée suit le plan (grille).
    assert "encadrement" in _q(e, "chef_chantier")["partie"]["titre"].lower()
    assert "environnement" in _q(e, "dechets")["partie"]["titre"].lower()
    # Idempotent : préparer de nouveau ne change ni les numéros ni l'ordre.
    e2 = _entretien(client, h, pid)
    assert [(x["code"], x["numero"]) for x in e2["questions"]] == [(x["code"], x["numero"]) for x in e["questions"]]
    assert e2["preparation"] == {"creees": 0, "retirees": 0, "reproposees": 0}
    # L'en-tête de l'atelier compte les questions.
    at_st = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert at_st["entretien"]["prepare"] is True and at_st["entretien"]["a_repondre"] == len(codes)


def test_environnement_toujours_meme_sans_phrase_et_huit_au_plus(client, auth, fake_llm):
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    cctp = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES\n"
            "Le site reste occupé pendant les travaux. Une école jouxte le chantier et les élèves passent devant. "
            "Le bâtiment est un établissement recevant du public. Les travaux de nuit sont prévus pour la voirie. "
            "Le plomb des peintures est à traiter. La coactivité avec le lot électricité est forte. "
            "Le site est dans le périmètre des abords d'un monument historique. Un phasage en trois tranches de "
            "travaux est imposé. Les réseaux existants sont signalés. Les livraisons passent par la cour.\n")
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
          "Valeur technique : 60 %\nPrix : 40 %\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}]
    pid, _st = _projet_chantier(client, h, rc=rc, cctp=cctp, criteres=crit)
    e = _entretien(client, h, pid)
    codes = [x["code"] for x in e["questions"]]
    assert len(codes) == ec.MAX_QUESTIONS, codes
    env = [x for x in e["questions"] if eb.PAR_CODE[x["code"]]["famille"] == eb.ENVIRONNEMENT]
    assert len(env) == 1 and env[0]["code"] == "environnement"
    # Aucune phrase du dossier ne parle d'environnement : la question le dit, sans phrase inventée.
    assert env[0]["motif"] is None and env[0]["motif_message"] == ec.MSG_SANS_MOTIF
    # Un critère unique (« Valeur technique ») : toutes les questions s'y rattachent, avec son poids tel qu'écrit.
    assert {(x["critere"] or {}).get("poids") for x in e["questions"]} == {"60 %"}


# ═══ 2. La fiche chantier : réponses → faits sourcés ; question passée → « [À compléter] » ═══════════

def test_reponses_fiche_chantier_faits_sources_dans_l_atelier(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h)
    e = _entretien(client, h, pid)
    q = _q(e, "site_occupe")
    rep = (f"Accès du chantier par le {SECRET_CHEF}, séparé de l'entrée des élèves ; livraisons entre 9 h et 11 h 30, "
           "hors des entrées et des sorties.")
    e = _repondre(client, h, pid, q, reponse=rep, lock_version=q["lock_version"])
    q = _q(e, "site_occupe")
    assert q["statut"] == "repondue" and q["reponse"]["libelle"] == "déclaré par vous" and q["reponse"]["par"] == "vous"
    assert [x["ref"] for x in e["fiche"]] == [q["ref"]] and e["fiche"][0]["libelle"] == "déclaré par vous"
    # Verrou optimiste : une réponse fondée sur une version périmée est refusée.
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h,
                   json={"statut": "repondue", "reponse": "autre", "lock_version": 0})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "question_modifiee"
    ref = q["ref"]
    sec = _partie(st, "site occupé")
    texte = (f"Les livraisons ont lieu entre 9 h et 11 h 30 [{ref}].\n\n"
             f"Nous séparons l'accès du chantier de l'entrée des élèves [{ref}].")
    fake = fake_llm(lambda kw: (texte, "end_turn"))
    res = _rediger(client, h, pid, sec["id"])
    assert res["status"] == "done", res
    sent = fake.sent()
    # La réponse est un fait autorisé numéroté, « déclaré par vous », avec la question pour la placer.
    assert f"[{ref}] (déclaré par vous) Entretien chantier, réponse à « " in sent
    assert f"ENTRETIEN CHANTIER : les réponses [{ref}] concernent cette partie" in sent
    v = _version_db(sec["id"])
    reliees = [f for f in v["faits"] if f.get("statut") == "avec_source"]
    assert any((f.get("source") or {}).get("ref") == ref and f["source"]["type"] == "declare" for f in reliees), reliees
    assert not [f for f in v["faits"] if f.get("statut") == "a_relire" and "11 h 30" in f.get("fait", "")]
    # Les renvois [R#] ne partent jamais chez l'acheteur.
    from app.services.memoire_export import clean_markdown
    assert "[R" not in clean_markdown(v["texte"]) and "11 h 30" in clean_markdown(v["texte"])
    # Le compteur de l'en-tête de l'atelier.
    ent = client.get(f"/api/atelier/{pid}", headers=h).json()["entretien"]
    assert ent["repondues"] == 1 and ent["a_repondre"] == ent["total"] - 1


def test_question_passee_laisse_a_completer_dans_la_partie_concernee(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h)
    e = _entretien(client, h, pid)
    _repondre(client, h, pid, _q(e, "chef_chantier"), statut="sautee")
    e = _repondre(client, h, pid, _q(e, "dechets"), statut="sans_objet")
    assert _q(e, "chef_chantier")["statut_libelle"] == "Passée" and _q(e, "dechets")["statut"] == "sans_objet"
    assert _q(e, "chef_chantier")["a_completer"] == "[À compléter : chef de chantier]"
    sec = _partie(st, "encadrement")
    fake = fake_llm(lambda kw: ("Un encadrement de proximité suit le chantier au quotidien.", "end_turn"))
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    v = _version_db(sec["id"])
    # Jamais un texte de remplissage : le passage « [À compléter] » de la question passée, ajouté sans IA s'il manque.
    assert v["texte"].count("[À compléter : chef de chantier]") == 1, v["texte"]
    sent = fake.sent()
    assert "POINTS SANS RÉPONSE POUR CETTE PARTIE" in sent and "[À compléter : chef de chantier]" in sent
    # L'IA l'a écrit elle-même (autre libellé, même objet) : pas de doublon.
    sec_env = _partie(st, "environnement")
    fake = fake_llm(lambda kw: ("Les mesures du chantier sont décrites ici. [À compléter : mesures environnementales "
                                "propres au chantier]", "end_turn"))
    assert _rediger(client, h, pid, sec_env["id"])["status"] == "done"
    v = _version_db(sec_env["id"])
    assert v["texte"].count("[À compléter") == 1, v["texte"]
    # « Sans objet » ne laisse rien : pas de passage sur les déchets.
    assert "déchets" not in v["texte"].lower()
    # Le passage compte dans le blocage de l'export (rien ne part chez l'acheteur avec un trou).
    stt = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert any(r["code"] == "a_completer" for r in stt["blocage"]["raisons"])
    # Garde-fou sans IA, en direct.
    assert ec.garantir_manques("Texte.", ["[À compléter : chef de chantier]"]).endswith("[À compléter : chef de chantier]")
    assert ec.garantir_manques("Texte [À compléter : nom du chef de chantier].",
                               ["[À compléter : chef de chantier]"]).count("[À compléter") == 1
    assert ec.garantir_manques("", ["[À compléter : x]"]) == ""


def test_chef_de_chantier_liste_equipe_sans_nom_ni_cv_a_l_ia(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h)
    r = client.post("/api/preuves", headers=h, json={
        "nature": "salarie", "type_source": "declare",
        "valeur": {"nom": "Gwenola Kerhervé", "fonction": "Cheffe de chantier", "experience_annees": 14,
                   "diplomes": "BTS Bâtiment DIPLOMESECRET", "chantiers": "Toitures scolaires CHANTIERSECRET"}})
    assert r.status_code == 201, r.text
    pre = r.json()["id"]
    e = _entretien(client, h, pid)
    q = _q(e, "chef_chantier")
    assert q["type_reponse"] == "equipe" and q["aide"]
    assert any(p["preuve_id"] == pre and p["nom"] == "Gwenola Kerhervé" for p in e["equipe"])
    bad = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h,
                     json={"statut": "repondue", "preuve_id": 999999})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "personne_introuvable"
    e = _repondre(client, h, pid, q, preuve_id=pre)
    q = _q(e, "chef_chantier")
    assert q["reponse"]["personne"]["nom"] == "Gwenola Kerhervé"
    ref = q["ref"]
    sec = _partie(st, "encadrement")

    def ans(kw):
        flat = "\n".join(llm._flatten_content(m.get("content")) for m in kw.get("messages") or [])
        m = re.search(re.escape(f"[{ref}]") + r" \(déclaré par vous\) [^\n]*?: (\[[^\]]+\]), Cheffe de chantier", flat)
        lab = m.group(1) if m else "[?]"
        return f"Le chantier est conduit par {lab}, cheffe de chantier [{ref}].", "end_turn"
    fake = fake_llm(ans)
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    sent = fake.sent()
    # Jamais le nom en clair, jamais le CV à l'IA ; l'étiquette et le renvoi de la fiche, oui.
    for x in ("Gwenola", "Kerhervé", "DIPLOMESECRET", "CHANTIERSECRET"):
        assert x not in sent, x
    assert "(sa fiche : [F" in sent
    v = _version_db(sec["id"])
    assert "Gwenola Kerhervé" in v["texte"], v["texte"]           # le nom est remis en clair, sans IA
    assert any((f.get("source") or {}).get("ref") == ref for f in v["faits"] if f.get("statut") == "avec_source")
    # La fiche retirée de « Mes preuves » : la réponse ne sert plus (« [À compléter] »), l'écran le dit.
    assert client.post(f"/api/preuves/{pre}/retirer", headers=h, json={}).status_code == 200
    e = _entretien(client, h, pid, preparer=False)
    assert _q(e, "chef_chantier")["reponse"]["personne_retiree"] is True
    assert not [x for x in e["fiche"] if x["ref"] == ref]


# ═══ 3. Groupement : la question du lot d'un partenaire, posée dans SON espace ═══════════════════

def _avec_partenaires(client, h):
    from tests.test_convention_groupement import _invite, _put
    pid, st = _projet_chantier(client, h)
    a = _invite(client, h, pid, "Breizh Couverture")
    assert _put(client, a["token"], company_name="Breizh Couverture", lot="Couverture et zinguerie").status_code == 200
    b = _invite(client, h, pid, "Le Gall Électricité")
    assert _put(client, b["token"], company_name="Le Gall Électricité", lot="Électricité courants forts").status_code == 200
    r = client.post(f"/api/atelier/{pid}/repartition", headers=h, json={})
    assert r.status_code == 200, r.text
    return pid, st, a, b


def test_question_du_lot_d_un_partenaire_posee_dans_son_espace(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P, _audit
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, b = _avec_partenaires(client, h)
    e = _entretien(client, h, pid)
    q = _q(e, "acces_toiture")
    # Proposée sans IA d'après le lot (« Couverture et zinguerie » ↔ toiture), au seul partenaire qui correspond.
    assert q["adresse"]["type"] == "invitation" and q["adresse"]["invite_id"] == a["id"], q["adresse"]
    assert q["adresse"]["nom"] == "Breizh Couverture" and q["peut_repondre"] is False
    assert {m["nom"] for m in e["groupement"]["membres"]} >= {"Breizh Couverture", "Le Gall Électricité"}
    # Le chef de file ne répond pas à sa place.
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h,
                   json={"statut": "repondue", "reponse": "Par l'escalier intérieur."})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "question_d_un_partenaire"
    _repondre(client, h, pid, _q(e, "site_occupe"), reponse=f"Accès des compagnons par le {SECRET_CHEF}.")
    # Dans SON espace : la question, la phrase du dossier qui la motive, la partie concernée.
    pa = P(client, a["token"])
    ent = pa.get().json()["entretien"]
    assert [x["id"] for x in ent["questions"]] == [q["id"]] and ent["questions"][0]["motif"]["phrase"]
    assert ent["avertissement"] == ec.AVERTISSEMENT_REPONSE and ent["questions"][0]["partie"]
    assert SECRET_CHEF not in pa.get().text            # jamais une réponse du chef de file chez le partenaire
    pb = P(client, b["token"])
    assert pb.get().json()["entretien"]["questions"] == []
    corps = {"statut": "repondue", "reponse": "Échafaudage de pied côté cour et monte-matériaux.", "avertissement_lu": True}
    assert pb.put(f"/entretien/{q['id']}", corps).status_code == 404        # pas la sienne
    sans_cle = P(client, a["token"], ouvrir=False)
    r = sans_cle.put(f"/entretien/{q['id']}", corps)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    r = pa.put(f"/entretien/{q['id']}", dict(corps, avertissement_lu=False))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "avertissement_requis"
    r = pa.put(f"/entretien/{q['id']}", corps)
    assert r.status_code == 200, r.text
    assert r.json()["questions"][0]["reponse"]["texte"].startswith("Échafaudage de pied")
    assert ("entretien.reponse", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    jm = client.get(f"/api/invite/{a['token']}/journal").json()
    assert "Vous avez répondu à une question du chef de file sur le chantier" in json.dumps(jm, ensure_ascii=False)
    # Le chef de file lit la réponse comme un fait déclaré par ce partenaire, sans pouvoir la modifier.
    e = _entretien(client, h, pid, preparer=False)
    q = _q(e, "acces_toiture")
    assert q["reponse"]["par"] == "Breizh Couverture" and q["reponse"]["libelle"] == "déclaré par Breizh Couverture"
    assert any(x["ref"] == q["ref"] and x["libelle"] == "déclaré par Breizh Couverture" for x in e["fiche"])
    # L'IA du chef de file la reçoit « déclaré par votre partenaire » : elle n'appuie qu'une phrase qui le nomme.
    sec = _partie(st, "méthodologie")
    ref = q["ref"]
    fake = fake_llm(lambda kw: (f"Breizh Couverture accède à la toiture par un échafaudage de pied [{ref}].", "end_turn"))
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    assert f"[{ref}] (déclaré par votre partenaire) Breizh Couverture — entretien chantier" in fake.sent()
    v = _version_db(sec["id"])
    src = [f["source"] for f in v["faits"] if f.get("statut") == "avec_source" and (f.get("source") or {}).get("ref") == ref]
    assert src and src[0]["type"] == "partenaire" and src[0]["partenaire"] == "Breizh Couverture", v["faits"]
    # La reprendre : sa réponse sort de la fiche chantier (confirmation), et la question quitte son espace.
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h, json={"invite_id": None})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reponse_a_confirmer"
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h, json={"invite_id": None, "confirmer": True})
    assert r.status_code == 200, r.text
    q = _q(r.json(), "acces_toiture")
    assert q["statut"] == "a_repondre" and q["adresse"]["type"] == "organisation" and q["adresse"]["choix"] == "manuel"
    assert pa.get().json()["entretien"]["questions"] == []
    # La poser à l'autre partenaire ; un partenaire inconnu est refusé.
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h, json={"invite_id": 999999})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "partenaire_indisponible"
    assert client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h,
                      json={"invite_id": b["id"]}).status_code == 200
    assert [x["id"] for x in pb.get().json()["entretien"]["questions"]] == [q["id"]]
    assert pb.put(f"/entretien/{q['id']}", corps).status_code == 200
    # Préparer de nouveau ne reprend jamais un choix fait à la main.
    e = _entretien(client, h, pid)
    assert _q(e, "acces_toiture")["adresse"]["invite_id"] == b["id"]
    # Retrait de l'invitation : ses réponses sont effacées, ses questions reviennent au chef de file.
    assert client.delete(f"/api/projects/{pid}/invites/{b['id']}", headers=h).status_code == 200
    e = _entretien(client, h, pid, preparer=False)
    q = _q(e, "acces_toiture")
    assert q["adresse"]["type"] == "organisation" and q["statut"] == "a_repondre" and q["reponse"] is None
    from app.models import EntretienQuestion
    db = _db()
    try:
        assert db.query(EntretienQuestion).filter(EntretienQuestion.reponse_invite_id == b["id"]).count() == 0
    finally:
        db.close()


def test_ia_du_partenaire_recoit_ses_seules_reponses_et_ses_manques(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P, _aide
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, b = _avec_partenaires(client, h)
    met = _partie(st, "méthodologie")["id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{met}", headers=h, json={"redacteur": "partenaire",
                                                                            "invite_id": a["id"]})
    assert r.status_code == 200, r.text
    e = _entretien(client, h, pid)
    # La partie concernée lui est confiée : les questions de cette partie lui sont proposées.
    mien = [x for x in e["questions"] if x["adresse"]["invite_id"] == a["id"]]
    assert {x["code"] for x in mien} >= {"acces_toiture", "visite"}, [(x["code"], x["adresse"]) for x in e["questions"]]
    _repondre(client, h, pid, _q(e, "site_occupe"), reponse=f"Accès des compagnons par le {SECRET_CHEF}.")
    pa = P(client, a["token"])
    qt = _q(e, "acces_toiture")
    assert pa.put(f"/entretien/{qt['id']}", {"statut": "repondue", "reponse": "Échafaudage de pied côté cour.",
                                            "avertissement_lu": True}).status_code == 200
    assert pa.put(f"/entretien/{_q(e, 'visite')['id']}", {"statut": "sautee"}).status_code == 200
    fake = fake_llm(lambda kw: ("Nous montons par un échafaudage de pied côté cour [%s]." % qt["ref"], "end_turn"))
    res, _jid = _aide(pa, met)
    assert res["status"] == "done", res
    sent = fake.sent()
    assert f"[{qt['ref']}] (déclaré par vous) Entretien chantier, réponse à « " in sent
    assert SECRET_CHEF not in sent                       # jamais la matière du chef de file
    assert "[À compléter : constats de la visite du site]" in sent
    b_ = pa.get(f"/sections/{met}").json()["brouillon"]
    assert "[À compléter : constats de la visite du site]" in b_["texte"]
    # Le chef de file ne voit jamais le brouillon : seulement ce que le partenaire envoie.
    assert "Échafaudage de pied côté cour [" not in client.get(f"/api/atelier/{pid}/repartition/{met}", headers=h).text


def test_reponse_du_partenaire_espace_reinitialise_ou_lien_retire_entre_temps(client, auth, fake_llm, monkeypatch):
    """Comme ses autres écritures (dépôt par le lien), la réponse prend d'abord le verrou de l'invitation et relit la
    clé juste avant d'écrire : un espace réinitialisé entre-temps (autre appareil) ne reçoit rien (409), un lien
    retiré entre-temps non plus (404)."""
    from app.models import EntretienQuestion, ProjectInvite
    from app.services import atelier_groupement as ag
    from tests.test_redaction_v4_groupement import P
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, b = _avec_partenaires(client, h)
    q = _q(_entretien(client, h, pid), "acces_toiture")
    assert q["adresse"]["invite_id"] == a["id"]
    pa = P(client, a["token"])
    corps = {"statut": "repondue", "reponse": "Échafaudage de pied côté cour.", "avertissement_lu": True}
    vrai = ag._exiger_identite
    fait = {}

    def pendant(geste):
        def identite(acces):
            if not fait:
                db = _db()
                try:
                    fait["r"] = geste(db)
                finally:
                    db.close()
            return vrai(acces)
        return identite

    def lue():
        db = _db()
        try:
            r = db.get(EntretienQuestion, q["id"])
            return r.statut, r.reponse, r.reponse_invite_id
        finally:
            db.close()

    monkeypatch.setattr(ag, "_exiger_identite", pendant(
        lambda db: ag.ouvrir_espace(db, db.get(ProjectInvite, a["id"]), reinitialiser=True)["cle"]))
    r = pa.put(f"/entretien/{q['id']}", corps)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "espace_reinitialise", r.text
    assert r.json()["detail"]["message"] == ag.MSG_ECRITURE_ESPACE_REINITIALISE
    assert lue() == ("a_repondre", None, None)
    # Avec la nouvelle clé, la réponse passe.
    monkeypatch.setattr(ag, "_exiger_identite", vrai)
    pa.h = {ag.ENTETE_CLE: fait["r"]}
    assert pa.put(f"/entretien/{q['id']}", corps).status_code == 200
    assert lue()[0] == "repondue"
    # Lien retiré pendant la réponse : rien n'est écrit en son nom (le retrait passe avant).
    fait.clear()
    pb = P(client, b["token"])
    assert client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h,
                      json={"invite_id": b["id"], "confirmer": True}).status_code == 200

    def retirer(db):
        inv = db.get(ProjectInvite, b["id"])
        inv.revoked = True                   # comme la route du retrait : l'accès coupé, puis ce qui suit
        db.commit()
        ag.retirer_invitation(db, inv, "retiré du groupement")
        return True
    monkeypatch.setattr(ag, "_exiger_identite", pendant(retirer))
    r = pb.put(f"/entretien/{q['id']}", corps)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "question_introuvable", r.text
    assert lue() == ("a_repondre", None, None)


# ═══ 4. Option IA : des questions de plus, chacune motivée par une phrase retrouvée ═══════════════

SYNDIC = ("Les travaux sur le pignon nord exigent l'accord préalable du syndic de la copropriété voisine, sous "
          "un préavis de 15 jours.")


def _ans_ia(items, tenants=None):
    def ans(kw):
        if "Tu prépares l'entretien chantier" in llm._flatten_content(kw.get("system")):
            if tenants is not None:
                tenants.append(llm._CURRENT_TENANT.get())
            return json.dumps({"questions": items}, ensure_ascii=False), "end_turn"
        return "x", "end_turn"
    return ans


def _lancer_ia(client, h, pid):
    r = client.post(f"/api/atelier/{pid}/entretien/ia", headers=h, json={})
    assert r.status_code == 202, r.text
    return _attendre(client, h, pid, r.json()["tache"]["id"])


def test_option_ia_questions_gardees_seulement_si_phrase_mot_pour_mot(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h, cctp=CCTP + "Article 6 - Mitoyenneté\n" + SYNDIC + "\n")
    e = _entretien(client, h, pid)
    n0 = len(e["questions"])
    assert e["ia"]["restantes"] == ec.MAX_IA and e["ia"]["bulle"]
    items = [{"question": "Comment obtenez-vous l'accord du syndic voisin pour le pignon nord ?", "phrase": SYNDIC,
              "theme": "accord du syndic voisin"},
             {"question": "Comment limitez-vous la poussière ?", "phrase": "Le chantier doit limiter la poussière au maximum.",
              "theme": "poussière"},
             {"question": "Prévenez-vous le syndic 30 jours avant ?", "phrase": SYNDIC, "theme": "préavis"},
             {"question": "Comment organisez-vous les livraisons ?", "phrase": "Les livraisons sont interdites aux heures "
              "d'entrée et de sortie des élèves.", "theme": "livraisons"}]
    tenants = []
    fake_llm(_ans_ia(items, tenants))
    res = _lancer_ia(client, h, pid)
    assert res["status"] == "done", res
    # Gardée : sa phrase est dans le dossier ; écartées : phrase absente, nombre absent de la phrase, phrase déjà montrée.
    assert res["result"]["ajoutees"] == 1 and res["result"]["refusees"] == 3, res["result"]
    assert "_debit" not in res["result"]
    owner = _user_id(auth["email"])
    assert tenants == [owner]                            # espace facturé de l'organisation
    e = _entretien(client, h, pid, preparer=False)
    ia = [x for x in e["questions"] if x["origine"] == "ia"]
    assert len(e["questions"]) == n0 + 1 and len(ia) == 1
    assert ia[0]["motif"]["phrase"] == SYNDIC and ia[0]["origine_libelle"] == ec.LIB_ORIGINE["ia"]
    assert ia[0]["numero"] == max(x["numero"] for x in e["questions"])
    # Compte sur le plafond de l'atelier : la 1re action de l'IA du dossier = 1 analyse (une refonte comprise).
    q1 = client.get(f"/api/atelier/{pid}", headers=h).json()["quota"]
    assert q1["analyse_debitee"] is True and q1["regenerations_utilisees"] == 1
    # Préparer de nouveau garde la question de l'IA.
    assert [x for x in _entretien(client, h, pid)["questions"] if x["origine"] == "ia"]
    # Rien de retenu : rien n'est décompté.
    fake_llm(_ans_ia([items[1]]))
    res = _lancer_ia(client, h, pid)
    assert res["status"] == "done" and res["result"]["ajoutees"] == 0 and "rien n'a été décompté" in res["result"]["message"]
    q2 = client.get(f"/api/atelier/{pid}", headers=h).json()["quota"]
    assert q2["regenerations_utilisees"] == q1["regenerations_utilisees"]


def test_option_ia_en_panne_rien_n_est_decompte(client, auth, fake_llm, monkeypatch):
    h = auth["headers"]
    _company(client, h)
    pid, st = _projet_chantier(client, h)
    _entretien(client, h, pid)

    def panne(kw):
        raise llm.LLMUnavailable("panne simulée")
    fake_llm(panne)
    res = _lancer_ia(client, h, pid)
    assert res["status"] == "error" and res["error"] == ec.MSG_IA_PANNE
    q = client.get(f"/api/atelier/{pid}", headers=h).json()["quota"]
    assert q["analyse_debitee"] is False and q["regenerations_utilisees"] == 0
    assert not [x for x in _entretien(client, h, pid, preparer=False)["questions"] if x["origine"] == "ia"]


# ═══ 5. Isolation, RGPD, démo, migration ══════════════════════════════════════════════════

def test_isolation_entre_comptes_et_rgpd(client, auth, fake_llm):
    from tests.test_convention_groupement import _register
    from tests.test_redaction_v4_groupement import P
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, b = _avec_partenaires(client, h)
    e = _entretien(client, h, pid)
    _repondre(client, h, pid, _q(e, "site_occupe"), reponse=f"Accès par le {SECRET_CHEF}.")
    qt = _q(e, "acces_toiture")
    pa = P(client, a["token"])
    assert pa.put(f"/entretien/{qt['id']}", {"statut": "repondue", "reponse": "Échafaudage de pied.",
                                            "avertissement_lu": True}).status_code == 200
    h2, _e2 = _register(client, company="Autre entreprise")
    for m, url, body in (("get", f"/api/atelier/{pid}/entretien", None), ("post", f"/api/atelier/{pid}/entretien", None),
                         ("put", f"/api/atelier/{pid}/entretien/{qt['id']}", {"statut": "sautee"}),
                         ("put", f"/api/atelier/{pid}/entretien/{qt['id']}/adresse", {"invite_id": None}),
                         ("post", f"/api/atelier/{pid}/entretien/ia", {})):
        r = getattr(client, m)(url, headers=h2, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (url, r.status_code, r.text)
    # Export RGPD du chef de file : l'entretien de ses dossiers.
    ex = client.get("/api/rgpd/export", headers=h).json()
    txt = json.dumps(ex["entretiens_chantier"], ensure_ascii=False)
    assert SECRET_CHEF in txt and "Échafaudage de pied." in txt
    # Portabilité du partenaire : SES réponses, jamais celles du chef de file.
    exp = pa.get("/export").json()
    assert "Échafaudage de pied." in json.dumps(exp["reponses_entretien_chantier"], ensure_ascii=False)
    assert SECRET_CHEF not in json.dumps(exp, ensure_ascii=False)


def test_demo_entretien_de_la_vitrine_sans_ia_et_en_lecture(client, monkeypatch):
    from app.models import DossierPresentation, EntretienQuestion, Project, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        toiture = next(p for p in db.query(Project).filter(Project.user_id == u.id) if p.name.startswith("Réfection toiture"))
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == toiture.id).one()
        assert db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == d.id).count() >= 4
        pid = toiture.id
    finally:
        db.close()
    appels = []
    monkeypatch.setattr(llm, "messages_create", lambda *a, **k: appels.append(1) or (_ for _ in ()).throw(
        llm.LLMUnavailable("IA coupée")))
    tok = client.post("/api/auth/demo").json()["access_token"]
    hd = {"Authorization": f"Bearer {tok}"}
    e = _entretien(client, hd, pid, preparer=False)
    assert e["prepare"] is True and 4 <= len(e["questions"]) <= ec.MAX_QUESTIONS
    rep = [x for x in e["questions"] if x["statut"] == "repondue"]
    assert len(rep) >= 3 and e["fiche"] and all(f["libelle"] == "déclaré par vous" for f in e["fiche"])
    assert any(x["reponse"]["personne"] for x in rep)                     # le chef de chantier, de « Mes preuves »
    assert any(x["statut"] == "sautee" for x in e["questions"])          # le « [À compléter] » qu'elle laissera
    from app.services import demo_redaction as dr
    dossier_txt = re.sub(r"\s+", " ", " ".join(" ".join(p[2]) for p in dr.PIECES))
    for x in e["questions"]:
        if x["motif"]:
            assert re.sub(r"\s+", " ", x["motif"]["phrase"]) in dossier_txt, x["motif"]
    assert client.get(f"/api/atelier/{pid}", headers=hd).json()["entretien"]["repondues"] >= 3
    q = e["questions"][0]
    for m, url, body in (("post", f"/api/atelier/{pid}/entretien", None),
                         ("put", f"/api/atelier/{pid}/entretien/{q['id']}", {"statut": "sautee"}),
                         ("put", f"/api/atelier/{pid}/entretien/{q['id']}/adresse", {"invite_id": None}),
                         ("post", f"/api/atelier/{pid}/entretien/ia", {})):
        r = getattr(client, m)(url, headers=hd, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and "lecture guidée" in r.text, (url, r.status_code, r.text)
    assert appels == []


def test_migration_entretien_sqlite_neuve_retour_arriere_rejeu(tmp_path):
    import sqlalchemy as sa
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "v5d.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=root, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def schema():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            insp = sa.inspect(eng)
            return ({c["name"]: (str(c["type"]), c["nullable"], str(c.get("default")))
                     for c in insp.get_columns("entretien_questions")},
                    {i["name"]: (tuple(i["column_names"]), bool(i.get("unique")))
                     for i in insp.get_indexes("entretien_questions")},
                    sorted(tuple(u["column_names"]) for u in insp.get_unique_constraints("entretien_questions")))
        finally:
            eng.dispose()

    run("upgrade", "head")
    neuf = schema()
    assert {"numero", "code", "motif", "adresse_invite_id", "reponse_invite_id", "statut"} <= set(neuf[0])
    assert ("dossier_id", "numero") in neuf[2] and ("dossier_id", "code") in neuf[2]
    run("downgrade", "y9z0depotlien")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    try:
        assert "entretien_questions" not in sa.inspect(eng).get_table_names()
        assert "dossier_repartitions" in sa.inspect(eng).get_table_names()       # la vague 4 n'est pas touchée
        assert "depots_lien_documents" in sa.inspect(eng).get_table_names()      # ni le dépôt par le lien
    finally:
        eng.dispose()
    run("upgrade", "head")
    assert schema() == neuf
    run("stamp", "y9z0depotlien")
    run("upgrade", "head")                               # rejeu : idempotent
    assert schema() == neuf


# ═══ 6. Écrans : chef de file (atelier) et partenaire (son espace) ════════════════════════════════

_STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static")


def _lire(nom):
    with open(os.path.join(_STATIC, nom), encoding="utf-8") as f:
        return f.read()


def _bloc_entretien(html):
    from tests.zones import zone
    return zone(html, "atelier-entretien")


def test_ecran_du_chef_de_file_regles_d_interface_et_branchements():
    from tests.test_redaction_v4_partenaire import EMOJI
    html, js = _lire("app.html"), _lire("app.js")
    bloc = _bloc_entretien(html)
    # Branché sur les routes de l'entretien ; la recherche avec l'IA passe par le moteur commun de l'atelier (débit
    # confirmé dans la fenêtre de l'atelier, tâche suivie toutes les 2 s).
    for x in ('this._atlUrl("/entretien")', '"/entretien/" + q.id', '"/adresse"', '"/entretien/ia"',
              'r.kind === "atelier_entretien"', "_atlLignesEntretien()"):
        assert x in js, x
    assert "atlEntRepondre(q, 'repondue')" in bloc and "atlEntRepondre(q, 'sautee')" in bloc
    assert "atlEntRepondre(q, 'sans_objet')" in bloc and "atlEntAdresser(q, $event.target.value)" in bloc
    # La phrase du dossier, la partie concernée, la liste « Équipe » ; jamais une commande d'IA sur téléphone.
    assert "q.motif.phrase" in bloc and "Partie concernée" in bloc and "atl.ent.d.equipe" in bloc
    # (ni dans un dossier « sans IA », vague 5 C2 : intégration des chantiers.)
    assert ('<template v-if="!atlMobile && atl.ent.d.prepare && !atlSansIa() && atl.ent.d.ia.permise !== false">'
            in bloc)
    # Textes de l'API rendus par interpolation (échappés), jamais en v-html.
    assert "v-html" not in bloc
    # Règles d'interface : boutons typés, bulles (i), zéro émoji, aucun mot interdit.
    for b in re.findall(r"<button\b[^>]*>", bloc):
        assert 'type="button"' in b, b
    assert bloc.count('class="tip-b" role="tooltip"') >= 3
    assert not EMOJI.search(bloc)
    low = re.sub(r"<[^>]+>", " ", bloc).lower()
    for mot in ("vérifié", "signer", "consortium", "mandataire", "prompt", "workflow"):
        assert mot not in low, mot
    for sel in re.findall(r"<select\b[^>]*>", bloc):
        i = re.search(r':id="([^"]+)"', sel).group(1)
        assert f':for="{i}"' in bloc, sel                 # chaque menu a son libellé
    css = _lire("styles.css")
    assert ".atl-ent" in css and "@media (max-width:640px)" in css[css.index(".atl-ent {"):]


def test_gabarit_de_l_application_precompile_a_jour():
    """Les render functions PRÉCOMPILÉES (app/static/app.render.js) sont à jour vis-à-vis des
    gabarits (le bloc #app de app.html + les `template:` des composants de app.js), à l'image du
    SRI. Garde contre un gabarit modifié sans régénération (scripts/precompile_vue.mjs) — qui, en
    build Vue runtime-only, casserait l'écran concerné. La régénération échoue si un gabarit ne
    compile pas (ce test couvre donc aussi « le gabarit compile sans erreur »). Skippé si la chaîne
    de build dev (node + @vue/compiler-dom@3.5.38 + jsdom) est absente, comme l'ancien test l'était
    sans node."""
    import shutil, tempfile
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dep = subprocess.run([node, "-e", "require.resolve('@vue/compiler-dom');require.resolve('jsdom')"],
                         cwd=root, capture_output=True)
    if dep.returncode != 0:
        pytest.skip("@vue/compiler-dom@3.5.38 / jsdom absents "
                    "(npm install --no-save @vue/compiler-dom@3.5.38 jsdom)")
    committed = os.path.join(_STATIC, "app.render.js")
    assert os.path.exists(committed), "app.render.js manquant : lancez  node scripts/precompile_vue.mjs"
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "app.render.js")
        r = subprocess.run([node, os.path.join(root, "scripts", "precompile_vue.mjs")],
                           cwd=root, capture_output=True, text=True, timeout=180,
                           env={**os.environ, "ADJUGO_RENDER_OUT": out})
        assert r.returncode == 0, r.stderr[-2000:]
        with open(out, encoding="utf-8") as f:
            regen = f.read()
    with open(committed, encoding="utf-8") as f:
        current = f.read()
    assert regen == current, ("app.render.js périmé : lancez  node scripts/precompile_vue.mjs  "
                              "(un gabarit a été modifié sans régénérer les render functions).")


def test_ecran_du_partenaire_questions_posees_dans_son_espace_sous_node():
    from tests.test_redaction_v4_corrections import _rendu, _vue_partenaire
    vue = _vue_partenaire([])
    q1 = {"id": 11, "numero": 3, "theme": "accès à la toiture",
          "question": "Comment accéderez-vous à la toiture <script>alert(1)</script> ?", "type_reponse": "texte",
          "motif": {"phrase": "La toiture couvre 1 850 m² <b>.", "piece": "Clauses techniques (CCTP)"},
          "motif_message": "", "partie": {"section_id": 5, "titre": "Méthodologie"}, "statut": "a_repondre",
          "statut_libelle": "À répondre", "reponse": None, "a_completer": "[À compléter : accès à la toiture]",
          "lock_version": 0}
    q2 = dict(q1, id=12, numero=4, question="Avez-vous visité le site ?", statut="sautee", statut_libelle="Passée",
              a_completer="[À compléter : constats de la visite du site]", motif=None,
              motif_message=ec.MSG_SANS_MOTIF)
    q3 = dict(q1, id=13, numero=5, question="Où partent vos déchets ?", statut="repondue", statut_libelle="Répondue",
              reponse={"texte": "Plateforme de tri <i>locale</i>.", "le": "2026-10-18T10:00:00"})
    vue["entretien"] = {"questions": [q1, q2, q3], "total": 3, "a_repondre": 1, "message": ec.MSG_PARTENAIRE,
                        "avertissement": ec.AVERTISSEMENT_REPONSE, "statuts": ec.STATUTS}
    h = _rendu(vue)["html"]
    assert "3 questions du chef de file sur ce chantier" in h and "1 à faire" in h
    # Tout est échappé ; la phrase du dossier et la partie concernée sont montrées.
    assert "<script" not in h and "&lt;script&gt;alert(1)&lt;/script&gt;" in h and "<b>" not in h and "<i>locale" not in h
    assert "La toiture couvre 1 850 m² &lt;b&gt;." in h and "Partie concernée : Méthodologie" in h
    assert ec.MSG_SANS_MOTIF.replace("'", "&#39;") in h
    # À répondre : envoyer, passer, sans objet ; passée : ce qu'elle laissera ; répondue : sa réponse, modifiable.
    for act in ('data-act="ent-envoyer" data-qid="11"', 'data-act="ent-passer" data-qid="11"',
                'data-act="ent-sans-objet" data-qid="11"', 'data-act="ent-modifier" data-qid="12"',
                'data-act="ent-modifier" data-qid="13"'):
        assert act in h, act
    assert "[À compléter : constats de la visite du site]" in h and "Plateforme de tri &lt;i&gt;locale&lt;/i&gt;." in h
    # Sans question posée : aucun bloc.
    vue["entretien"] = {"questions": [], "total": 0, "a_repondre": 0, "message": "", "avertissement": "", "statuts": {}}
    assert "questions du chef de file" not in _rendu(vue)["html"]
    # Règles : la réponse part avec l'avertissement lu ; aucun mot interdit dans l'écran.
    js = _lire("redaction-partenaire.js")
    assert '"/entretien/" + qid' in js and "body.avertissement_lu = true" in js
    assert "Pour répondre au chef de file" in js
