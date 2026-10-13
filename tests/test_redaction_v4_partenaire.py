"""
Rédaction, vague 4 — CHANTIER DU PARTENAIRE : il rédige SES parties du dossier de présentation commun, chez
lui (étude « rédaction » § 6.8 B, parcours point 2 ; contrat docs/REDACTION_V4_GROUPEMENT.md § 15).

Invariants vérifiés (le socle est vérifié par tests/test_redaction_v4_groupement.py) :
 • un seul écran (app/static/redaction-partenaire.js) pour le lien d'invitation et pour « Partagé avec moi » :
   ce que l'acheteur note (critère, poids tel qu'écrit, phrase retrouvée), longueur conseillée, date limite ;
   « Rédiger avec Adjugo » ou « J'écris moi-même » ; l'avertissement avant l'envoi ; l'avant et l'après côte
   à côte ; le dossier assemblé en lecture ; le mode simple (le petit texte de la part) sans perte ;
 • chaque champ que l'écran lit existe, dans l'ordre où il appelle l'API (lien, puis compte) ;
 • brouillons précédents : relus et repris par leur SEUL auteur (404 pour tout autre, clé exigée par le lien) ;
 • aide de l'IA indisponible (essai du chef de file terminé, plafond atteint, IA en panne) : message neutre,
   rien du forfait du chef de file dans tout ce que lit l'écran, l'aide rendue si l'IA tombe ;
 • isolation : la partie, le brouillon et la tâche d'un autre membre n'existent pas (404) ; le chef de file
   reçoit le texte et des compteurs, jamais une source ni un extrait ;
 • démo : le lien partenaire de la démo n'écrit rien (refusé avant tout autre contrôle), le compte démo non
   plus, même sans le garde central ;
 • écran : zéro émoji, jamais « vérifié », « signer » ni « consortium », textes échappés, clé de l'espace en
   en-tête (jamais dans une adresse), script servi avec son empreinte (SRI) dans les deux pages ; fonctions
   pures exécutées sous Node.
Aucun appel réseau : le client IA est simulé.
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from app.services import atelier_groupement as ag
from tests.test_convention_groupement import _invite, _put, _register
from tests.test_redaction_socle0 import _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _creer, _projet
from tests.test_redaction_v4_groupement import (LOT_A, P, PC, SECRET_BROUILLON, SECRET_DOC, SECRET_EXTRAIT, TEXTE_IA_A,
                                                _aide, _ecrire, _envoyer, _groupement, _part_a, _reponse_partenaire,
                                                _vues_du_chef)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")
FORFAIT = ("essai", "forfait", "quota", "abonn", "analyses_", "trial", "plan_", "402")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


JS = _read("redaction-partenaire.js")


# ═══ 1. Le parcours de l'écran contre la vraie API (par le lien) ══════════════════════

def test_parcours_de_l_ecran_par_le_lien(client, auth, fake_llm):
    """Chaque champ que l'écran lit existe, dans l'ordre où l'écran appelle l'API."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"longueur_mots": 120, "date_limite": "2030-11-02"})
    # Le petit texte de la part (mode simple) : écrit AVANT, gardé tel quel.
    assert _put(client, a["token"], memoire_paragraph="Spécialiste du désamiantage en site occupé.").status_code == 200
    base = f"/api/invite/{a['token']}/redaction"
    # 1. Première lecture, sans clé : ce qui est commun seulement ; l'espace n'est pas encore ouvert.
    v = client.get(base).json()
    assert v["espace"]["cle_valide"] is False and v["espace"]["ouvert"] is False and v["espace"]["entete"] == "X-Adjugo-Espace"
    assert v["mode"] == "lien" and v["message_mode"] == ag.MSG_MODE_LIEN and v["peut_ecrire"] is True
    assert v["avertissement_envoi"] == "Ce texte sera lu par le chef de file et par les autres membres du groupement."
    assert v["membre"] == {"nom": "Breizh Désamiantage", "lot": LOT_A}
    assert v["identite"] == {"a_prouver": False, "message": ""}
    assert v["mode_simple"]["petit_texte"] == "Spécialiste du désamiantage en site occupé."
    assert v["dossier"]["pret"]["message"].startswith("Sections validées 0 sur")
    p = v["parties"][0]
    for k in ("section_id", "titre", "intitule", "statut", "statut_libelle", "mention", "longueur_mots", "date_limite",
              "limite", "note", "brouillon", "texte_commun", "comparaison", "validation", "aide"):
        assert k in p, k
    assert p["longueur_mots"] == 120 and p["date_limite"] == "2030-11-02" and p["statut"] == "a_rediger"
    assert p["brouillon"] is None and p["aide"] == {"utilisees": 0, "plafond": 3, "restantes": 3, "en_cours": None}
    assert set(p["note"]) >= {"critere", "poids", "poids_source", "poids_libelle", "phrase", "question", "grille"}
    # 2. « Ouvrir mon espace » : la clé, rendue une fois, part ensuite en en-tête.
    r = client.post(base + "/espace", json={})
    assert r.status_code == 200 and r.json()["entete"] == "X-Adjugo-Espace"
    H = {"X-Adjugo-Espace": r.json()["cle"]}
    assert client.get(base, headers=H).json()["espace"]["cle_valide"] is True
    # 3. « Rédiger avec Adjugo » : tâche de fond de SA portée, suivie par l'écran, rien de texte dedans.
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    r = client.post(base + f"/sections/{sid}/aide", json={"action": "rediger"}, headers=H)
    assert r.status_code == 202 and r.json()["tache"]["id"]
    jid = r.json()["tache"]["id"]
    j = None
    for _ in range(300):
        j = client.get(base + f"/taches/{jid}", headers=H).json()
        if j["status"] in ("done", "error"):
            break
    assert j["status"] == "done" and j["result"]["sections"][0]["ok"] is True and "texte" not in json.dumps(j["result"])
    p = client.get(base, headers=H).json()["parties"][0]
    b1 = p["brouillon"]
    for k in ("id", "numero", "origine", "origine_libelle", "ia", "empreinte", "base_version_id", "a_completer",
              "faits_a_relire", "faits", "controle", "compteurs", "sources", "sources_depuis_le_compte", "texte"):
        assert k in b1, k
    assert b1["origine"] == "ia" and b1["a_completer"] == 1 and b1["faits_a_relire"] >= 1
    assert p["statut"] == "en_cours" and p["aide"]["restantes"] == 2
    # 4. Un fait relu par lui (« Je l'ai relu »).
    f = next(x for x in b1["faits"] if x["statut"] == "a_relire" and x["type"] != "reste")
    r = client.post(base + f"/sections/{sid}/faits/{f['id']}", json={"statut": "relu_par_vous"}, headers=H)
    assert r.status_code == 200 and r.json()["fait"]["statut"] == "relu_par_vous"
    # 5. « J'écris moi-même » : il complète, l'écran enregistre (verrou sur le brouillon courant).
    texte = b1["texte"].replace("[À compléter : planning des rotations]", "Le planning des rotations est joint.")
    r = client.put(base + f"/sections/{sid}/brouillon", json={"texte": texte, "base_brouillon_id": b1["id"]}, headers=H)
    assert r.status_code == 200 and r.json()["brouillon"]["a_completer"] == 0
    b2 = r.json()["brouillon"]
    r = client.put(base + f"/sections/{sid}/brouillon", json={"texte": "autre", "base_brouillon_id": b1["id"]}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "brouillon_modifie"
    # 6. « Vos brouillons précédents » : la liste (sans textes), puis un brouillon repris avec son texte.
    d = client.get(base + f"/sections/{sid}", headers=H).json()
    assert [x["numero"] for x in d["brouillons"]] == [2, 1] and all("texte" not in x for x in d["brouillons"])
    r = client.get(base + f"/sections/{sid}/brouillons/{b1['id']}", headers=H)
    assert r.status_code == 200 and r.json()["texte"] == b1["texte"]
    # 7. Envoyer : l'avertissement est exigé, puis le texte devient commun.
    r = client.post(base + f"/sections/{sid}/envoyer", json={"brouillon_id": b2["id"]}, headers=H)
    assert r.status_code == 422 and r.json()["detail"]["message"] == v["avertissement_envoi"]
    r = client.post(base + f"/sections/{sid}/envoyer", json={"brouillon_id": b2["id"], "avertissement_lu": True},
                    headers=H)
    assert r.status_code == 200
    p = r.json()
    assert p["statut"] == "envoyee" and p["texte_commun"]["ecrit_par"] == "partenaire" and p["texte_commun"]["cree_le"]
    assert p["brouillon"]["empreinte"] == p["texte_commun"]["empreinte"]          # rien de nouveau à envoyer
    # Ce que le chef de file reçoit : le texte et des compteurs par type, rien d'autre.
    ligne = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert "Le planning des rotations est joint." in ligne["texte_commun"]["texte"]
    assert set(ligne["texte_commun"]["compteurs"]) == {"par_type", "avec_source", "a_relire", "engagements"}
    assert "sources" not in ligne["texte_commun"] and "brouillon" not in ligne
    # 8. Le chef de file modifie : l'avant et l'après, puis « Valider la modification ».
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": texte.replace("4 bennes", "5 bennes"), "base_version_id": p["texte_commun"]["version_id"]})
    assert r.status_code == 200
    p = client.get(base + f"/sections/{sid}", headers=H).json()
    assert p["statut"] == "a_revalider" and p["texte_commun"]["ecrit_par"] == "chef_de_file"
    assert "4 bennes" in p["comparaison"]["avant"]["texte"] and "5 bennes" in p["comparaison"]["apres"]["texte"]
    assert p["mention"] == "Modifié par le chef de file, à revalider par Breizh Désamiantage"
    r = client.post(base + f"/sections/{sid}/valider", json={"version_id": p["texte_commun"]["version_id"]}, headers=H)
    assert r.status_code == 200 and r.json()["statut"] == "validee" and r.json()["validation"]["le"]
    # 9. Le dossier assemblé, en lecture, puis sa validation sur l'empreinte lue.
    dos = client.get(base + "/dossier", headers=H).json()
    assert dos["message"] == ag.MSG_LECTURE and dos["empreinte"]
    moi = next(x for x in dos["parties"] if x["section_id"] == sid)
    assert moi["redacteur"]["vous"] is True and moi["ecrit_par"] == "chef_de_file" and "5 bennes" in moi["texte"]
    assert all({"titre", "statut", "statut_libelle", "redacteur", "texte"} <= set(x) for x in dos["parties"])
    v = client.get(base, headers=H).json()
    assert v["dossier"]["peut_valider"] is True and v["dossier"]["ma_validation"] is None
    r = client.post(base + "/dossier/valider", json={"empreinte": dos["empreinte"]}, headers=H)
    assert r.status_code == 200 and r.json()["validation"]["statut"] == "valide"
    assert client.get(base, headers=H).json()["dossier"]["ma_validation"]["statut_libelle"] == "Validé"
    # 10. Portabilité (clé exigée, en en-tête).
    assert client.get(base + "/export").status_code == 403
    r = client.get(base + "/export", headers=H)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    # Le mode simple n'a rien perdu : le petit texte est toujours celui de la part, lu par le chef de file.
    assert client.get(f"/api/invite/{a['token']}/contribution").json()["memoire_paragraph"] == \
        "Spécialiste du désamiantage en site occupé."
    contribs = client.get(f"/api/projects/{pid}/contributions", headers=h).json()
    assert contribs[0]["memoire_paragraph"] == "Spécialiste du désamiantage en site occupé."
    assert client.get(base, headers=H).json()["mode_simple"]["petit_texte"] == "Spécialiste du désamiantage en site occupé."


# ═══ 2. Ce que l'acheteur note ═══════════════════════════════════════════════════════

def test_ce_que_l_acheteur_note_critere_poids_et_phrase_retrouvee(client, auth):
    """Plan tiré de la grille : le critère, le poids tel qu'écrit, d'où il vient et la phrase retrouvée dans
    le règlement. Plan tiré du cadre : la question du cadre, et les critères techniques de la grille (le prix,
    jugé sur le bordereau, n'en fait pas partie)."""
    h = auth["headers"]
    _company(client, h)
    # Plan sur la grille : chaque partie porte son critère.
    pid = _projet(client, h, name="Marché grille")
    _creer(client, h, pid, base="grille")
    a = _invite(client, h, pid, "Breizh Désamiantage")
    _put(client, a["token"], company_name="Breizh Désamiantage", lot=LOT_A)
    assert client.post(f"/api/atelier/{pid}/repartition", headers=h, json={}).status_code == 200
    vue = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    s = vue["sections"][0]
    assert s["critere"] == "Valeur technique"
    r = client.put(f"/api/atelier/{pid}/repartition/{s['section_id']}", headers=h,
                   json={"redacteur": "partenaire", "invite_id": a["id"], "confirmer": True})
    assert r.status_code == 200, r.text
    n = P(client, a["token"], ouvrir=False).get().json()["parties"][0]["note"]
    assert n["critere"] == "Valeur technique" and n["poids"] == "60 %" and n["poids_source"] == "reglement"
    assert n["poids_libelle"] == "écrit dans le règlement"
    assert n["phrase"] == "Valeur technique : 60 %" and n["grille"] == []
    # Plan sur le cadre de réponse : la question du cadre, et les critères techniques de la grille.
    pid2, st, a2, b2, vue2 = _groupement(client, auth, avec_b=False)
    n2 = P(client, a2["token"], ouvrir=False).get().json()["parties"][0]["note"]
    assert n2["critere"] == "" and "gestion des déchets" in n2["question"]
    assert [g["critere"] for g in n2["grille"]] == ["Valeur technique"]
    assert n2["grille"][0]["poids"] == "60 %" and n2["grille"][0]["phrase"] == "Valeur technique : 60 %"
    assert "Prix" not in json.dumps(n2["grille"], ensure_ascii=False)


# ═══ 3. « Partagé avec moi » : le même écran, par le compte ═════════════════════════

def test_partage_avec_moi_resume_et_ecran_par_le_compte(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    hp, ep = _register(client, company="Breizh Désamiantage")
    r = client.post("/api/knowledge/text", headers=hp, json={
        "name": SECRET_DOC, "kind": "memoire",
        "text": f"Gestion des déchets du chantier : 4 bennes étanches pour les déchets amiantés {SECRET_EXTRAIT}."})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invite/{a['token']}/claim", headers=hp).status_code == 200
    # La liste : statuts seulement (jamais un texte).
    item = next(x for x in client.get("/api/shared", headers=hp).json() if x["project_id"] == pid)
    assert item["redaction"] == {"parties": 1, "a_faire": 1, "a_revalider": 0}
    # L'écran par le compte : aucune clé, sa matière privée lisible, ses preuves et son savoir-faire.
    pc = PC(client, pid, hp)
    v = pc.get().json()
    assert v["mode"] == "compte" and v["espace"]["cle_valide"] is True and v["message_mode"] == ag.MSG_MODE_COMPTE
    assert v["identite"]["a_prouver"] is False
    fake = fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    job, jid = _aide(pc, sid)
    assert job["status"] == "done" and SECRET_EXTRAIT in fake.sent()
    b1 = pc.get(f"/sections/{sid}").json()["brouillon"]
    assert any(SECRET_EXTRAIT in (s.get("extrait") or "") for s in b1["sources"])
    _ecrire(pc, sid, "Nous trions les déchets amiantés.")
    r = pc.get(f"/sections/{sid}/brouillons/{b1['id']}")
    assert r.status_code == 200 and r.json()["texte"] == b1["texte"] and r.json()["sources"]
    # Par le lien (même invitation, avec la clé) : les sources écrites depuis le compte restent au compte.
    pl = P(client, a["token"])
    rl = pl.get(f"/sections/{sid}/brouillons/{b1['id']}").json()
    assert rl["sources"] == [] and rl["sources_depuis_le_compte"] is True
    _envoyer(pc, sid)
    item = next(x for x in client.get("/api/shared", headers=hp).json() if x["project_id"] == pid)
    assert item["redaction"] == {"parties": 1, "a_faire": 0, "a_revalider": 0}
    tout = _vues_du_chef(client, h, pid, sid, token=a["token"])
    assert "Nous trions les déchets amiantés." in tout and SECRET_EXTRAIT not in tout and SECRET_DOC not in tout
    # Le chef de file modifie : la pastille de la liste le dit.
    cur = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()["texte_commun"]["version_id"]
    client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
               json={"texte": "Nous trions et évacuons les déchets amiantés.", "base_version_id": cur})
    item = next(x for x in client.get("/api/shared", headers=hp).json() if x["project_id"] == pid)
    assert item["redaction"] == {"parties": 1, "a_faire": 0, "a_revalider": 1}
    # Un sous-traitant, ou un dossier pas encore préparé : rien (l'écran reste vide).
    h2, e2 = _register(client, company="Chef sans dossier")
    _company(client, h2)
    pid2 = _projet(client, h2, name="Sans dossier")
    a2 = _invite(client, h2, pid2, "Breizh Désamiantage")
    assert client.post(f"/api/invite/{a2['token']}/claim", headers=hp).status_code == 200
    item2 = next(x for x in client.get("/api/shared", headers=hp).json() if x["project_id"] == pid2)
    assert item2["redaction"] is None
    assert client.get(f"/api/shared/{pid2}/redaction", headers=hp).status_code == 404


# ═══ 4. Brouillons précédents : seulement leur auteur ═══════════════════════════════

def test_brouillons_precedents_relus_seulement_par_leur_auteur(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    b1 = _ecrire(pa, sid, f"Premier brouillon {SECRET_BROUILLON}.")["brouillon"]
    _ecrire(pa, sid, "Second brouillon.")
    assert pa.get(f"/sections/{sid}/brouillons/{b1['id']}").json()["texte"] == f"Premier brouillon {SECRET_BROUILLON}."
    # Le lien sans la clé (le chef de file qui l'a transmis) : rien.
    sans = P(client, a["token"], ouvrir=False)
    r = sans.get(f"/sections/{sid}/brouillons/{b1['id']}")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    # Un autre membre : la partie n'existe pas pour lui ; un identifiant inventé non plus.
    pb = P(client, b["token"])
    assert pb.get(f"/sections/{sid}/brouillons/{b1['id']}").status_code == 404
    assert pa.get(f"/sections/{sid}/brouillons/999999").status_code == 404
    # Le chef de file, par ses routes : jamais un brouillon de partenaire.
    assert SECRET_BROUILLON not in _vues_du_chef(client, h, pid, sid, token=a["token"])
    assert client.get(f"/api/atelier/{pid}/sections/{sid}/brouillons/{b1['id']}", headers=h).status_code in (404, 405)


# ═══ 5. Aide de l'IA indisponible : message neutre, rien du forfait du chef de file ══

def test_aide_indisponible_neutre_dans_tout_l_ecran_et_aide_rendue_si_l_ia_tombe(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])

    def boom(kw):
        raise RuntimeError("fournisseur indisponible")
    # IA en panne : la tâche échoue avec un message lisible, l'aide est rendue, rien n'est débité.
    fake_llm(boom)
    job, _ = _aide(pa, sid)
    assert job["status"] == "error" and job["error"] == ag.MSG_IA_PANNE
    p = pa.get(f"/sections/{sid}").json()
    assert p["aide"]["restantes"] == ag.plafond_partie() and p["brouillon"] is None
    # Essai du chef de file terminé : message neutre ; l'écran ne lit rien de son forfait.
    from app.models import User
    db = _db()
    try:
        db.query(User).filter(User.email == auth["email"]).first().trial_ends_at = \
            datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    r = pa.post(f"/sections/{sid}/aide", {"action": "rediger"})
    assert r.status_code == 409 and r.json()["detail"] == {"code": "aide_indisponible", "message": ag.MSG_AIDE_INDISPONIBLE}
    for lu in (pa.get().text, pa.get(f"/sections/{sid}").text, pa.get("/dossier").text):
        low = lu.lower()
        for mot in FORFAIT:
            assert mot not in low, mot
    # Il écrit toujours lui-même, et envoie.
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    assert _envoyer(pa, sid)["statut"] == "envoyee"
    assert client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()["statut"] == "envoyee"


# ═══ 6. Isolation : la partie, le brouillon et la tâche d'un autre membre n'existent pas ═

def test_isolation_entre_membres_et_404_sur_les_taches(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pa, pb = P(client, a["token"]), P(client, b["token"])
    job, jid = _aide(pa, sid)
    assert job["status"] == "done"
    bid = pa.get(f"/sections/{sid}").json()["brouillon"]["id"]
    assert pb.get(f"/sections/{sid}").status_code == 404
    assert pb.get(f"/taches/{jid}").status_code == 404
    assert pb.get(f"/sections/{sid}/brouillons/{bid}").status_code == 404
    for m, chemin, body in (("put", f"/sections/{sid}/brouillon", {"texte": "x", "base_brouillon_id": None}),
                            ("post", f"/sections/{sid}/aide", {}),
                            ("post", f"/sections/{sid}/envoyer", {"brouillon_id": bid, "avertissement_lu": True})):
        assert getattr(pb, m)(chemin, body).status_code == 404, chemin
    assert client.get(f"/api/jobs/{jid}", headers=h).status_code == 404
    # Le dossier assemblé de B : la partie de A n'y a pas de texte tant qu'elle n'est pas envoyée.
    d = pb.get("/dossier").json()
    assert next(x for x in d["parties"] if x["section_id"] == sid)["texte"] is None
    assert "4 bennes" not in pb.get("/dossier").text


# ═══ 7. Démonstration : rien n'est écrit, ni par le lien de la démo ni par le compte démo ═

def test_demo_lien_partenaire_et_compte_demo_refuses_dans_la_route(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = SessionLocal()
    try:
        ensure_demo(db)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        lorient = next(p for p in db.query(Project).filter(Project.user_id == u.id) if "Kerhel" in p.name)
        token = db.query(ProjectInvite).filter(ProjectInvite.project_id == lorient.id).first().token
        pid = lorient.id
    finally:
        db.close()
    base = f"/api/invite/{token}/redaction"
    for m, chemin, body in (("post", "/espace", {}), ("put", "/sections/1/brouillon", {"texte": "x"}),
                            ("post", "/sections/1/aide", {"action": "rediger"}),
                            ("post", "/sections/1/envoyer", {"brouillon_id": 1, "avertissement_lu": True}),
                            ("post", "/sections/1/valider", {"version_id": 1}),
                            ("post", "/sections/1/retablir", {"base_version_id": 1}),
                            ("post", "/sections/1/faits/x", {"statut": "relu_par_vous"}),
                            ("post", "/dossier/valider", {})):
        r = getattr(client, m)(base + chemin, json=body)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "demo", (chemin, r.text)
        assert "lecture guidée" in r.json()["detail"]["message"]
    assert client.get(base).status_code == 404                    # lecture : pas de dossier commun, rien de cassé
    # Le compte démo, même si le garde central était contourné.
    import app.core.demo_guard as g
    monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)
    tok = client.post("/api/auth/demo").json()["access_token"]
    hd = {"Authorization": f"Bearer {tok}"}
    for m, chemin, body in ((client.post, f"/api/shared/{pid}/redaction/sections/1/aide", {}),
                            (client.post, f"/api/shared/{pid}/redaction/sections/1/envoyer", {"brouillon_id": 1}),
                            (client.put, f"/api/shared/{pid}/redaction/sections/1/brouillon", {"texte": "x"}),
                            (client.post, f"/api/atelier/{pid}/repartition", {}),
                            (client.put, f"/api/atelier/{pid}/repartition/1", {"longueur_mots": 100}),
                            (client.put, f"/api/atelier/{pid}/repartition/1/texte", {"texte": "x"}),
                            (client.post, f"/api/atelier/{pid}/repartition/valider-dossier", {})):
        r = m(chemin, json=body, headers=hd)
        assert r.status_code == 403 and "lecture guidée" in json.dumps(r.json(), ensure_ascii=False), (chemin, r.text)


# ═══ 8. L'écran lui-même ═════════════════════════════════════════════════════════════

def _chaines_js(src):
    """Les textes montrés : chaînes entre guillemets, hors commentaires et hors codes (« identity_unverified »)."""
    sans = re.sub(r"(?m)^\s*//.*$", "", re.sub(r"/\*[\s\S]*?\*/", "", src))
    return " ".join(c for c in re.findall(r'"((?:[^"\\\n]|\\.)*)"', sans) if not re.fullmatch(r"[a-z_\-/]*", c))


def test_ecran_regles_d_interface_et_branchements():
    inv, app_html, app_js = _read("invite.html"), _read("app.html"), _read("app.js")
    # Un seul écran, servi avec son empreinte dans les deux pages, monté par le lien et par le compte.
    m = json.loads(_read("sri-manifest.json"))["fichiers"]["/static/redaction-partenaire.js"]
    for page in (inv, app_html):
        assert f'<script src="/static/redaction-partenaire.js" integrity="{m["integrity"]}"' in page
    assert 'base: "/api/invite/" + encodeURIComponent(TOKEN) + "/redaction", mode: "lien"' in inv
    assert 'cleStockage: "adjugo_espace_" + TOKEN' in inv and "verifyIdentity(el, op)" in inv
    assert '__adjApp.component("redaction-partenaire"' in app_js and 'mode: "compte"' in app_js
    assert '"/api/shared/" + encodeURIComponent(this.pid) + "/redaction"' in app_js
    assert '<redaction-partenaire v-if="sharedAo.projectId"' in app_html and "sharedRedLine(s.redaction)" in app_html
    # Routes branchées (toutes relatives à la base de l'accès).
    for route in ('"/espace"', '"/dossier"', '"/dossier/valider"', '"/export"', '"/taches/"', '"/aide"', '"/envoyer"',
                  '"/valider"', '"/retablir"', '"/brouillon"', '"/faits/"', '"/brouillons/"', '"/otp/request"'):
        assert route in JS, route
    # La clé de l'espace part en en-tête, jamais dans une adresse.
    assert 'const ENTETE = "X-Adjugo-Espace"' in JS and "h[ENTETE] = k" in JS
    assert "?cle" not in JS and "cle=" not in JS and "encodeURIComponent(k" not in JS
    # Avertissement avant l'envoi, exigé par l'API ; c'est le partenaire qui lance l'aide.
    assert "avertissement_lu: true" in JS and "Ce texte sera lu par le chef de file et par les autres membres du groupement." in JS
    assert '"Rédiger avec Adjugo"' in JS and "J'écris moi-même" in JS
    assert "Valider la modification" in JS and "Rétablir ma version" in JS
    # Suivi de SA tâche toutes les 2 s (aucun temps réel), reprise au rechargement.
    assert "}, 2000);" in JS and "p.aide && p.aide.en_cours" in JS
    assert "WebSocket" not in JS and "EventSource" not in JS
    # Textes affichés échappés : aucun texte de l'API n'entre dans le HTML sans rpEsc / rpTexte / rpPhrase.
    assert "insertAdjacentHTML" not in JS and "outerHTML" not in JS
    # Règles d'interface : zéro émoji, jamais « vérifié », « signer », « consortium », ni jargon.
    chaines = _chaines_js(JS)
    assert not EMOJI.search(JS)
    low = chaines.lower()
    for mot in ("vérifié", "verifie", "signer", "signature", "consortium", "mandataire", "prompt", "token", "workflow"):
        assert mot not in low, mot
    # Bulles (i) : boutons typés, une bulle par explication.
    assert JS.count('class="tip-b" role="tooltip"') == 1 and '<button type="button" class="tip' in JS
    for b in re.findall(r"<button\b[^>]*>", JS):
        assert 'type="button"' in b, b
    css = _read("styles.css")
    assert ".rp-card" in css and "@media (max-width:640px)" in css[css.index(".rp-card"):]


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    prog = "const window = {};\n" + JS + "\nconst R = window.AdjugoRedactionPartenaire._pur;\n" + script
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_fonctions_pures_de_l_ecran_sous_node():
    md = ("## Gestion <script>alert(1)</script>\n"
          "Nous mobilisons **4 bennes** étanches [S1]. <img src=x onerror=alert(1)> \"guillemets\"\n"
          "- Tri sur place [F2, F3]\n- Bordereaux [À compléter : délai]\n\n"
          "| Phase | Durée |\n| --- | --- |\n| Tri | 3 jours |\n")
    r = _node(f"const md = {json.dumps(md)};\n"
              "console.log(JSON.stringify({"
              " t: R.rpTexte(md, 'source du partenaire'),"
              " p: R.rpPhrase('Une nacelle <b>de</b> 18 m', 'Nacelle'), p0: R.rpPhrase('rien <i>', 'absent'),"
              " mots: [R.rpMots('## Titre\\n- deux mots [S1]\\n| a | b |'), R.rpMots(\"l'équipe d'Adjugo\")],"
              " todo: R.rpACompleter('[À compléter : x] et [a COMPLETER y] et [F2]'),"
              " lim: [R.rpLim({type: 'pages', valeur: 20}), R.rpLim({type: 'pages', valeur: 1, objet: 'reference'}),"
              "       R.rpLim({type: 'police', police: 'Arial', taille: 11})],"
              " cpt: R.rpCompteurs({par_type: {documents: 2, declare: 1, public: 0, acheteur: 1}}),"
              " d: R.rpDiff('Nous avons 4 bennes <b>.', 'Nous avons 5 bennes <b>.'),"
              " dl: R.rpDiff('a', ''), jour: R.rpJour('2026-11-02')}));")
    t = r["t"]
    assert "<script" not in t and "<img" not in t and "&lt;img src=x onerror=alert(1)&gt;" in t
    assert "&quot;guillemets&quot;" in t
    assert '<div class="rp-h">Gestion &lt;script&gt;alert(1)&lt;/script&gt;</div>' in t
    assert "<strong>4 bennes</strong>" in t
    assert '<span class="rp-ref" title="source du partenaire">S1</span>' in t
    assert '<span class="rp-ref" title="source du partenaire">F2,F3</span>' in t
    assert '<span class="rp-todo">[À compléter : délai]</span>' in t and "<ul><li>Tri sur place" in t
    assert '<table class="rp-table"><tbody><tr><td>Phase</td><td>Durée</td></tr><tr><td>Tri</td><td>3 jours</td></tr>' in t
    assert "---" not in t
    assert r["p"] == 'Une <mark class="rp-mark">nacelle</mark> &lt;b&gt;de&lt;/b&gt; 18 m' and r["p0"] == "rien &lt;i&gt;"
    assert r["mots"] == [5, 2] and r["todo"] == 2
    assert r["lim"] == ["20 pages au maximum", "1 page au maximum par référence", "Police : Arial 11"]
    assert r["cpt"] == ["2 trouvés dans vos documents", "1 déclarés par vous", "1 dans le dossier de l'acheteur"]
    d = r["d"]
    assert d["ok"] is True and '<mark class="rp-del">4</mark>' in d["avant"] and '<mark class="rp-ins">5</mark>' in d["apres"]
    assert "&lt;b&gt;" in d["avant"] and "<b>" not in d["avant"]
    assert r["dl"] == {"avant": "a", "apres": "", "ok": False}
    assert "novembre 2026" in r["jour"]
