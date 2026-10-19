"""
Rédaction, vague 4 — chantier CHEF DE FILE : « Qui écrit quoi » dans l'atelier (étude § 6.8 B, parcours 1 et 3).

Contrat : docs/REDACTION_V4_GROUPEMENT.md § 4 et § 15. Ce qui est vérifié, sans navigateur ni réseau (IA simulée) :
 • l'onglet « Qui écrit quoi » n'existe QUE pour un marché en groupement : un marché seul garde exactement
   l'atelier d'aujourd'hui (aucun onglet, aucune répartition, aucune écriture) ;
 • la répartition pré-remplie SANS IA (lot ↔ critère), son critère et son poids, la longueur conseillée et la
   date limite interne, telles que l'écran les lit ;
 • « Demander les parts » : mêmes garde-fous d'envoi que les relances de la co-traitance (adresse du chef de
   file confirmée, démo refusée, anti-rafale de 15 min, même plafond quotidien que les invitations, un email
   PARTI seulement) ; la relance planifiée ;
 • la réception : le texte envoyé et les COMPTEURS de sources par type (« 5 faits avec une source : 3
   déclarés, 2 trouvés dans ses documents »), jamais une source ni un extrait ; renvois « source du partenaire » ;
 • modifier une part envoyée → « à revalider par X », avant et après ; partenaire absent → « rédigé par le
   chef de file, à valider par X » ;
 • le chef de file ne lance JAMAIS l'aide de l'IA d'un partenaire (aucun bouton, et le serveur refuse) ;
 • la démo : toute écriture refusée dans la route (chef de file, lien partenaire de la vitrine) ;
 • l'écran : zéro émoji, jamais « vérifié », bulles (i), boutons typés, 375 px, rendu sûr ; fonctions pures
   exécutées sous Node.
"""
import json
import re
from datetime import date, timedelta

import pytest

from app.services import atelier_groupement as ag
from tests.test_convention_groupement import _invite, _register
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _creer, _etat, _projet
from tests.test_redaction_v2_ecrans import (CSS, EMOJI, HTML, JS, _between, _node, _sans_commentaires_html,
                                           _sans_commentaires_js)
from tests.zones import sans_reperes, zone
from tests.test_redaction_v4_groupement import (LOT_A, SECRET_DOC, SECRET_EXTRAIT, TEXTE_IA_A, P, PC, _aide, _audit,
                                                _ecrire, _envoyer, _groupement, _part_a, _reponse_partenaire,
                                                _section_par, _vues_du_chef)

# Zones repérées par leur attribut data-test (tests/zones.py, docs/REORGANISATION_V1.md).
ATELIER = zone(HTML, "vue-atelier")
REP = zone(HTML, "atelier-onglets") + "\n" + zone(HTML, "atelier-repartition")
JS_REP = _between(JS, "    // ── « Qui écrit quoi » (rédaction, vague 4, chef de file) ──",
                  "    // « Mon savoir-faire » : le dossier de présentation se prépare sur la page du marché.")
CSS_REP = CSS[CSS.index("/* ── « Qui écrit quoi » (rédaction, vague 4, chef de file) ──"):
              CSS.index("/* ── Fiches proposées à partir d'un document")]


def _ligne(client, h, pid, mot):
    return _section_par(client.get(f"/api/atelier/{pid}/repartition", headers=h).json(), mot)


def _email_a(invite_id, adresse):
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, invite_id).recipient = adresse
        db.commit()
    finally:
        db.close()


# ═══ 1. Un marché SANS groupement : l'atelier reste exactement celui d'aujourd'hui ═══════════

def test_marche_seul_atelier_inchange(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _creer(client, h, pid)
    st = _etat(client, h, pid)
    assert st["groupement"] == {"onglet": False, "actif": False, "membres": 0}
    assert all(s["peut_ecrire"] and s["prive_visible"] and "part" not in s for s in st["sections"])
    r = client.post(f"/api/atelier/{pid}/repartition", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pas_de_groupement"
    assert client.get(f"/api/atelier/{pid}/repartition", headers=h).json()["actif"] is False
    # Un sous-traitant n'est pas membre du groupement : pas d'onglet non plus.
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Peinture Sous-traitante",
                                                                     "role": "sous_traitant"})
    assert r.status_code == 200, r.text
    assert _etat(client, h, pid)["groupement"]["onglet"] is False
    assert client.post(f"/api/atelier/{pid}/repartition", headers=h, json={}).status_code == 409
    from app.models import DossierRepartition
    db = _db()
    try:
        assert db.query(DossierRepartition).filter(DossierRepartition.project_id == pid).count() == 0
    finally:
        db.close()
    # Rien d'autre ne change à l'atelier : mêmes clés qu'avant la vague 4 (plus l'indicateur).
    assert set(st) >= {"dossier", "sections", "blocage", "export", "quota", "compteur", "limites"}


def test_onglet_du_groupement_dans_l_etat_de_l_atelier(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _creer(client, h, pid)
    a = _invite(client, h, pid, "Breizh Désamiantage")
    st = _etat(client, h, pid)
    assert st["groupement"] == {"onglet": True, "actif": False, "membres": 1}       # à préparer
    assert client.post(f"/api/atelier/{pid}/repartition", headers=h, json={}).status_code == 200
    assert _etat(client, h, pid)["groupement"]["actif"] is True
    # Le partenaire retiré : l'onglet reste (le chef de file y reprend ses parties).
    assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=h).status_code == 200
    g = _etat(client, h, pid)["groupement"]
    assert g["onglet"] is True and g["membres"] == 0


# ═══ 2. Répartition pré-remplie sans IA, telle que l'écran la lit ════════════════════════════

def test_repartition_preremplie_sans_ia_champs_lus_par_l_ecran(client, auth, fake_llm):
    fake = fake_llm(lambda kw: (_ for _ in ()).throw(AssertionError("aucune IA pour répartir")))
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    assert fake.calls == []
    # Les 4 parties du cadre, et les deux parties tirées du groupement (assemblage) : personne ne les rédige.
    cadre = [l for l in vue["sections"] if not l.get("genere")]
    gen = [l for l in vue["sections"] if l.get("genere")]
    assert vue["actif"] is True and len(cadre) == 4
    assert [(l["genere"], l["choix"], l["redacteur"]["type"]) for l in gen] == [
        ("grp_orga", "genere", "groupement"), ("grp_qfq", "genere", "groupement")]
    assert all(l["message"] and l["longueur_mots"] is None and l["proposition"] is None for l in gen)
    assert {m["nom"]: (m["role"], m["peut_rediger"], m["raison"]) for m in vue["membres"]} == {
        "Breizh Désamiantage": ("cotraitant", True, ""), "Le Gall Électricité": ("cotraitant", True, "")}
    for l in cadre:
        # Chaque champ lu par l'écran existe.
        for k in ("section_id", "numero_affiche", "intitule", "critere", "poids", "poids_source", "redacteur",
                  "proposition", "choix", "longueur_mots", "date_limite", "demandee_le", "statut",
                  "statut_libelle", "mention", "envoyee_le", "texte_commun", "lock_version"):
            assert k in l, k
        assert set(l["redacteur"]) == {"type", "invite_id", "nom"} and l["proposition"]["message"]
        assert l["choix"] == "propose" and l["statut"] == "a_rediger"
    env = _part_a(vue)
    assert env["redacteur"] == {"type": "partenaire", "invite_id": a["id"], "nom": "Breizh Désamiantage"}
    assert "lot de Breizh Désamiantage" in env["proposition"]["message"]
    for k in ("message", "membres", "sections_validees", "sections_total"):
        assert k in vue["dossier"]["pret"]
    assert vue["dossier"]["pret"]["message"] == "Sections validées 0 sur 6"
    # Choisir le rédacteur, la longueur et la date (verrou optimiste comme l'écran l'envoie).
    met = _section_par(vue, "méthodologie")
    url = f"/api/atelier/{pid}/repartition/{met['section_id']}"
    lim = (date.today() + timedelta(days=6)).isoformat()
    r = client.put(url, headers=h, json={"redacteur": "partenaire", "invite_id": b["id"], "lock_version":
                                         met["lock_version"], "confirmer": False})
    assert r.status_code == 200, r.text
    r2 = client.put(url, headers=h, json={"longueur_mots": 350, "lock_version": met["lock_version"]})
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "repartition_modifiee"      # menu périmé
    r2 = client.put(url, headers=h, json={"longueur_mots": 350, "lock_version": r.json()["lock_version"]})
    assert r2.status_code == 200 and r2.json()["longueur_mots"] == 350
    r3 = client.put(url, headers=h, json={"date_limite": lim, "lock_version": r2.json()["lock_version"]})
    assert r3.status_code == 200 and r3.json()["date_limite"] == lim and r3.json()["choix"] == "manuel"
    assert client.put(url, headers=h, json={"date_limite": None}).json()["date_limite"] is None
    # Le partenaire indisponible : une phrase lisible (« … : son lien a expiré. »).
    from app.models import ProjectInvite
    from app.models import utcnow
    db = _db()
    try:
        db.get(ProjectInvite, b["id"]).expires_at = utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    enc = _section_par(vue, "encadrement")
    r = client.put(f"/api/atelier/{pid}/repartition/{enc['section_id']}", headers=h,
                   json={"redacteur": "partenaire", "invite_id": b["id"]})
    assert r.status_code == 409
    assert r.json()["detail"]["message"] == "Ce partenaire ne peut pas rédiger : son lien a expiré."
    m = {x["invite_id"]: x for x in client.get(f"/api/atelier/{pid}/repartition", headers=h).json()["membres"]}
    assert m[b["id"]]["peut_rediger"] is False and m[b["id"]]["raison"] == "son lien a expiré"
    # L'atelier montre la partie d'un partenaire avec le statut du groupement (jamais « Brouillon » à tort).
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == env["section_id"])
    assert s["peut_ecrire"] is False and s["part"] == {"statut": "a_rediger", "statut_libelle": "À rédiger",
                                                       "mention": ""}


def test_changer_le_redacteur_d_une_partie_ecrite_demande_confirmation(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    url = f"/api/atelier/{pid}/repartition/{sid}"
    r = client.put(url, headers=h, json={"redacteur": "chef_de_file", "invite_id": None})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "changement_a_confirmer"
    assert "reste dans l'historique" in r.json()["detail"]["message"]
    r = client.put(url, headers=h, json={"redacteur": "chef_de_file", "invite_id": None, "confirmer": True})
    assert r.status_code == 200 and r.json()["redacteur"]["type"] == "chef_de_file"
    assert r.json()["statut"] == "a_rediger" and r.json()["texte_commun"] is None
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert s["peut_ecrire"] is True and s["version_courante"] is None and "part" not in s


# ═══ 3. « Demander les parts » et relance ═══════════════════════════════════════════════════

def test_demander_les_parts_memes_garde_fous_que_les_relances(client, auth, monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth)
    _email_a(a["id"], "desamiantage@partenaire.fr")                    # B : aucune adresse sur son lien
    sid = _part_a(vue)["section_id"]
    lim = date.today() + timedelta(days=9)
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"date_limite": lim.isoformat()})
    met = _section_par(vue, "méthodologie")
    client.put(f"/api/atelier/{pid}/repartition/{met['section_id']}", headers=h,
               json={"redacteur": "partenaire", "invite_id": b["id"]})
    from app.routers import invites
    db = _db()
    try:
        from app.models import User
        u = db.query(User).filter(User.email == auth["email"]).first()
        avant = invites._daily_invite_count(u, db)
    finally:
        db.close()
    r = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["nom"], x["parties"], x["email_parti"]) for x in d["demandees"]] == [("Breizh Désamiantage", 1, True)]
    assert [x["nom"] for x in d["sans_adresse"]] == ["Le Gall Électricité"] and d["plafond_atteint"] == []
    assert len(sent) == 1 and sent[0][0] == "desamiantage@partenaire.fr"
    texte = sent[0][2]
    assert "« Démarche environnementale »" in texte and lim.strftime("%d/%m/%Y") in texte and a["token"] in texte
    assert "restent privés" in texte and "@" not in texte.replace("desamiantage@partenaire.fr", "")
    l = _ligne(client, h, pid, "environnement")
    assert l["demandee_le"] is not None
    # Même canal que les relances : chaque demande partie compte dans le plafond quotidien des invitations.
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert invites._daily_invite_count(u, db) == avant + 1
    finally:
        db.close()
    assert ("redaction.parts_demandees", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    # Anti-rafale : 15 minutes par partenaire.
    d = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()
    assert [x["nom"] for x in d["deja_demandees"]] == ["Breizh Désamiantage"] and len(sent) == 1
    # Plafond quotidien atteint : rien ne part, le partenaire est dit (jamais son adresse).
    db = _db()
    try:
        from app.models import DossierRepartition
        db.query(DossierRepartition).filter(DossierRepartition.section_id == sid).one().demandee_le = None
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(invites, "DAILY_INVITE_CAP", avant + 1)
    d = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()
    assert [x["nom"] for x in d["plafond_atteint"]] == ["Breizh Désamiantage"] and len(sent) == 1
    assert "desamiantage" not in json.dumps(d)


def test_demander_les_parts_envoi_rate_retentable_et_refus(client, auth, monkeypatch):
    h = auth["headers"]
    from app.services import email as _email
    essais = []
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: essais.append(to) and False)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _email_a(a["id"], "desamiantage@partenaire.fr")
    d = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()
    assert d["demandees"][0]["email_parti"] is False and len(essais) == 1
    assert _ligne(client, h, pid, "environnement")["demandee_le"] is None        # un envoi raté ne compte pas
    assert "redaction.parts_demandees" not in [x[0] for x in _audit(project_id=pid)]
    d = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()
    assert d["deja_demandees"] == [] and len(essais) == 2                         # retenté aussitôt
    # Adresse du chef de file non confirmée : refusé (comme le renvoi d'une invitation).
    from app.models import User
    db = _db()
    try:
        db.query(User).filter(User.email == auth["email"]).first().email_verified = False
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).status_code == 403
    assert len(essais) == 2


def test_relance_a_la_date_limite_et_texte_a_valider(client, auth, monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _email_a(a["id"], "desamiantage@partenaire.fr")
    sid = _part_a(vue)["section_id"]
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h,
               json={"date_limite": (date.today() + timedelta(days=1)).isoformat()})
    db = _db()
    try:
        assert ag.relancer_parts(db, date.today())["parts_relancees"] == 1                 # J-2
        assert ag.relancer_parts(db, date.today())["parts_relancees"] == 0                 # jamais deux fois
    finally:
        db.close()
    assert len(sent) == 1 and sent[0][1].startswith("Rappel")
    # Partenaire absent : le chef de file écrit sa partie ; la demande dit « à relire et valider ».
    client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
               json={"texte": "Le désamiantage suit la réglementation.", "base_version_id": None})
    r = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={})
    assert r.status_code == 200 and r.json()["demandees"][0]["email_parti"] is True
    assert "texte du chef de file, à relire et valider" in sent[-1][2]


# ═══ 4. Réception : texte envoyé et compteurs, jamais une source ni un extrait ═══════════════

def test_reception_texte_envoye_et_compteurs_sans_extraits(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    hp, _ep = _register(client, company="Breizh Désamiantage")
    r = client.post("/api/knowledge/text", headers=hp, json={
        "name": SECRET_DOC, "kind": "memoire",
        "text": (f"Gestion des déchets du chantier : tri sélectif des déchets amiantés dans 4 bennes étanches, "
                 f"bordereaux de suivi {SECRET_EXTRAIT}. Démarche environnementale et gestion des déchets.")})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invite/{a['token']}/claim", headers=hp).status_code == 200
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pc = PC(client, pid, hp)
    sid = _part_a(vue)["section_id"]
    job, _jid = _aide(pc, sid)
    assert job["status"] == "done", job
    br = pc.get(f"/sections/{sid}").json()["brouillon"]
    assert pc.post(f"/sections/{sid}/envoyer", {"brouillon_id": br["id"], "avertissement_lu": True}).status_code == 200
    # Ce que lit l'écran du chef de file : la ligne, le détail, l'atelier.
    l = _ligne(client, h, pid, "environnement")
    assert l["statut"] == "envoyee" and l["envoyee_le"] and l["mention"] == ""
    tc = l["texte_commun"]
    assert "texte" not in tc and tc["ecrit_par"] == "partenaire" and tc["a_completer"] == 1
    c = tc["compteurs"]
    assert set(c) == {"par_type", "avec_source", "a_relire", "engagements"} and c["avec_source"] >= 2
    det = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert det["texte_commun"]["texte"].startswith("Nous mobilisons 4 bennes") and det["comparaison"] == {
        "avant": None, "apres": det["texte_commun"]}
    tout = _vues_du_chef(client, h, pid, sid, token=a["token"])
    assert "Nous mobilisons 4 bennes étanches" in tout
    for secret in (SECRET_EXTRAIT, SECRET_DOC):
        assert secret not in tout, secret
    assert not re.search(r'"sources":\s*\[\s*\{', tout) and not re.search(r'"extrait":', tout)
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert s["prive_visible"] is False and "sources" not in s["version_courante"] and "faits" not in s["version_courante"]
    assert s["version_courante"]["compteurs"] == c and s["part"]["statut"] == "envoyee"
    # La phrase de l'écran, calculée sur la vraie réponse de l'API (sous Node).
    phrase = _node(f"console.log(JSON.stringify(atlRepCompteurs({json.dumps(tc)})));")
    assert phrase.startswith(f"{c['avec_source']} faits avec une source : ")
    assert "trouvé" in phrase and "déclaré" in phrase and "1 passage « [À compléter] »" in phrase


# ═══ 5. Modifier une part : « à revalider par X » ; partenaire absent ════════════════════════

def test_modifier_une_part_envoyee_a_revalider_avant_apres(client, auth, monkeypatch):
    h = auth["headers"]
    mails = []
    from app.routers import invites
    monkeypatch.setattr(invites, "_send_mails_async", lambda ms: mails.extend(ms))
    monkeypatch.setattr(invites, "_notify_allowed", lambda key: True)
    pid, st, a, b, vue = _groupement(client, auth)
    _email_a(a["id"], "desamiantage@partenaire.fr")
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place [S1].")
    _envoyer(pa, sid)
    det = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    v1 = det["texte_commun"]["version_id"]
    # Ce que fait l'écran : PUT …/texte avec la version lue.
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Nous trions et évacuons les déchets amiantés sur place [S1].", "base_version_id": v1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["statut"] == "a_revalider" and d["statut_libelle"] == "À revalider"
    assert d["mention"] == "Modifié par le chef de file, à revalider par Breizh Désamiantage"
    assert d["comparaison"]["avant"]["version_id"] == v1 and "évacuons" in d["comparaison"]["apres"]["texte"]
    assert d["texte_commun"]["ecrit_par"] == "chef_de_file" and d["texte_commun"]["compteurs"] is None
    assert "évacuons" not in d["comparaison"]["avant"]["texte"]                     # l'avant est conservé
    assert any(m[0] == "desamiantage@partenaire.fr" and "modifié votre partie" in m[2] for m in mails)
    assert ("redaction.part_modifiee", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    # Un texte saisi sur une version périmée n'écrase rien.
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h, json={"texte": "x", "base_version_id": v1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "texte_modifie_entre_temps"
    # L'atelier et le partenaire voient la même chose ; l'écriture ordinaire reste refusée au chef de file.
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert s["part"]["mention"] == d["mention"] and s["version_courante"]["ecrit_par"] == "chef_de_file"
    assert client.put(f"/api/atelier/{pid}/sections/{sid}/texte", headers=h,
                      json={"texte": "y", "base_version_id": s["version_courante"]["id"]}).status_code == 403
    p = pa.get(f"/sections/{sid}").json()
    assert p["statut"] == "a_revalider" and p["comparaison"]["avant"]["version_id"] == v1
    v2 = p["texte_commun"]["version_id"]
    assert pa.post(f"/sections/{sid}/valider", {"version_id": v2}).status_code == 200
    l = _ligne(client, h, pid, "environnement")
    assert l["statut"] == "validee" and l["mention"] == "Modifié par le chef de file, validé par Breizh Désamiantage"


def test_partenaire_absent_le_chef_de_file_redige_sa_part(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    det = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert det["texte_commun"] is None and det["comparaison"] is None                # « Rédiger à sa place »
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Le désamiantage suit la réglementation en vigueur.", "base_version_id": None})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mention"] == "Rédigé par le chef de file, à valider par Breizh Désamiantage"
    assert d["comparaison"] == {"avant": None, "apres": d["texte_commun"]}
    assert ("redaction.part_redigee_par_chef", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    pa = P(client, a["token"])
    p = pa.get(f"/sections/{sid}").json()
    assert p["statut"] == "a_revalider" and p["mention"] == d["mention"]
    assert pa.post(f"/sections/{sid}/valider", {"version_id": p["texte_commun"]["version_id"]}).status_code == 200
    assert _ligne(client, h, pid, "environnement")["mention"] == ("Rédigé par le chef de file, validé par "
                                                                  "Breizh Désamiantage")


# ═══ 6. Le chef de file ne lance jamais l'aide de l'IA d'un partenaire ═══════════════════════

def test_le_chef_de_file_ne_lance_pas_l_ia_a_la_place_du_partenaire(client, auth, fake_llm):
    fake = fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    for chemin, corps in ((f"/api/atelier/{pid}/sections/{sid}/rediger", {}),
                          (f"/api/atelier/{pid}/sections/{sid}/raccourcir", {}),
                          (f"/api/atelier/{pid}/rediger", {"section_ids": [sid]})):
        r = client.post(chemin, headers=h, json=corps)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "partie_d_un_partenaire", chemin
    # Par « Partagé avec moi » : le chef de file n'est pas le partenaire (404) ; par le lien sans la clé de
    # l'espace privé du partenaire : refusé.
    assert client.post(f"/api/shared/{pid}/redaction/sections/{sid}/aide", headers=h, json={}).status_code == 404
    r = client.post(f"/api/invite/{a['token']}/redaction/sections/{sid}/aide", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    assert fake.calls == []
    from app.models import Job
    db = _db()
    try:
        assert db.query(Job).filter(Job.portee == "partenaire", Job.invite_id == a["id"]).count() == 0
    finally:
        db.close()
    # « Rédiger tout » de l'atelier ne compte que les parties du chef de file.
    st2 = _etat(client, h, pid)
    assert all(s["peut_ecrire"] for s in st2["sections"] if s["statut"] == "a_ecrire" and s["id"] != sid)
    assert next(s for s in st2["sections"] if s["id"] == sid)["peut_ecrire"] is False


# ═══ 7. Démo : refus dans la route (chef de file, lien partenaire de la vitrine) ═════════════

def test_demo_ecritures_du_dossier_de_groupement_refusees_dans_la_route(client, monkeypatch):
    import app.core.demo_guard as g
    monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)          # garde central contourné
    from app.models import DossierPresentation, DossierSection, Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        toiture = next(p for p in db.query(Project).filter(Project.user_id == u.id) if p.name.startswith("Réfection"))
        kerhel = next(p for p in db.query(Project).filter(Project.user_id == u.id) if "Kerhel" in p.name)
        # Le refus vient AVANT toute lecture du dossier : une partie de la vitrine si elle existe, sinon un numéro.
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == toiture.id).first()
        s0 = db.query(DossierSection).filter(DossierSection.dossier_id == d.id).first() if d else None
        sid = s0.id if s0 else 1
        token = db.query(ProjectInvite).filter(ProjectInvite.project_id == kerhel.id).first().token
    finally:
        db.close()
    r = client.post("/api/auth/demo", json=None)
    hd = {"Authorization": f"Bearer {r.json()['access_token']}"}
    from app.services import email as _email
    emails = []
    monkeypatch.setattr(_email, "send_email", lambda to, *a, **k: emails.append(to) or True)
    for m, chemin, corps in (("POST", f"/api/atelier/{toiture.id}/repartition", {}),
                             ("PUT", f"/api/atelier/{toiture.id}/repartition/{sid}", {"longueur_mots": 300}),
                             ("PUT", f"/api/atelier/{toiture.id}/repartition/{sid}/texte",
                              {"texte": "x", "base_version_id": None}),
                             ("POST", f"/api/atelier/{kerhel.id}/repartition/demander", {}),
                             ("POST", f"/api/atelier/{toiture.id}/repartition/valider-dossier", {})):
        r = client.request(m, chemin, headers=hd, json=corps)
        assert r.status_code == 403 and "lecture guidée" in str(r.json()["detail"]), (chemin, r.text)
    base = f"/api/invite/{token}/redaction"
    for m, chemin, corps in (("POST", "/espace", {}), ("PUT", f"/sections/{sid}/brouillon", {"texte": "x"}),
                             ("POST", f"/sections/{sid}/faits/f1", {"statut": "relu_par_vous"}),
                             ("POST", f"/sections/{sid}/aide", {}),
                             ("POST", f"/sections/{sid}/envoyer", {"brouillon_id": 1, "avertissement_lu": True}),
                             ("POST", f"/sections/{sid}/valider", {"version_id": 1}),
                             ("POST", f"/sections/{sid}/retablir", {"base_version_id": 1}),
                             ("POST", "/dossier/valider", {})):
        r = client.request(m, base + chemin, json=corps)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "demo", (chemin, r.text)
    assert client.get(base).status_code == 404                                 # lecture : aucun dossier commun
    assert emails == []


# ═══ 8. L'écran « Qui écrit quoi » ═══════════════════════════════════════════════════════════

def test_ecran_onglet_seulement_en_groupement_et_menu_inchange():
    a = sans_reperes(_sans_commentaires_html(ATELIER))
    assert '<nav v-if="atlGrp()" class="rn-tabs atl-onglets" aria-label="Vues de l\'atelier">' in a
    assert '<div v-if="atlRepVue()" class="atl-rep">' in a and '<div v-show="!atlRepVue()" class="atl-grid">' in a
    assert "atlGrp() { const st = this.atl.st; return !!(st && st.groupement && st.groupement.onglet); }" in JS_REP
    assert 'onglet: "redaction", rep: _atlRepInit()' in JS
    # Le menu n'est pas réorganisé : rien de neuf dans la barre latérale.
    nav = zone(HTML, "menu")
    assert "repartition" not in nav and "Qui écrit quoi" not in nav


def test_ecran_repartir_relancer_recevoir_modifier():
    r = _sans_commentaires_html(REP)
    for libelle in ("Qui écrit quoi", "Préparer la répartition", "Rédigée par", "Vous (chef de file)",
                    "Mots conseillés", "Date limite interne", "Demander les parts", "Actualiser", "Lire le texte",
                    "Rédiger à sa place", "Modifier ce texte", "Rédiger sa partie", "Enregistrer", "Annuler",
                    "Copier mon texte", "Repartir du texte actuel", "aucun poids écrit dans le règlement",
                    "Aucune IA à cette étape : rien n'est débité.", "« à revalider par {{ l.redacteur.nom }} »",
                    "« Rédigé par le chef de file, à valider par {{ l.redacteur.nom }} »",
                    "disparaissent à l'export"):
        assert libelle in r, libelle
    assert "atlRepCompteurs(l.texte_commun)" in r and "atlPoidsTexte(l)" in r and "atlRepPropMsg(l)" in r
    # Aucune IA pour la part d'un partenaire : ni bouton, ni route d'aide, ni rédaction depuis cet écran.
    for interdit in ("Rédiger avec Adjugo", "sparkles", "atlRediger", "atlRaccourcir", "/aide", "Raccourcir"):
        assert interdit not in r, interdit
        assert interdit not in JS_REP, interdit
    # Jamais une source ni un extrait : l'écran ne lit ni « sources », ni « extrait », ni « faits » d'une part.
    for champ in (".sources", ".extrait", ".faits", "doc_name"):
        assert champ not in r and champ not in JS_REP, champ
    # Les routes du contrat, le verrou optimiste, la confirmation avant de confier une partie écrite.
    for route in ('"/repartition"', '"/demander"', '"/texte"'):
        assert route in JS_REP, route
    assert "lock_version: l.lock_version, confirmer: !!confirmer" in JS_REP
    assert 'e.code === "changement_a_confirmer"' in JS_REP and "base_version_id: e.base" in JS_REP
    # Sur téléphone : lire et répartir ; modifier un texte depuis un ordinateur.
    assert "atl.rep.edit.sid===l.section_id && !atlMobile" in r and "Sur téléphone, vous pouvez lire et répartir" in r
    assert "atlRepEcrire() {\n      const r = this.atl.rep, d = r.det; if (!d || this.atlMobile) return;" in JS_REP


def test_ecran_pret_a_deposer_parties_du_groupement_et_harmoniser():
    """Assemblage dans « Qui écrit quoi » : ce qui reste avant de déposer (jamais ce qui manque au chef de file
    comme entreprise), « Valider le dossier assemblé », les parties tirées du groupement en lecture (validées dans
    l'onglet « Rédaction »), la note interne au chef de file seul, « Harmoniser le ton » proposé seulement quand
    des parts de membres différents se suivent."""
    r = _sans_commentaires_html(REP)
    for libelle in ("Prêt à déposer", "Ce qui reste avant de déposer", "Valider le dossier assemblé",
                    "Écrite par Adjugo, sans IA", "La valider dans l'onglet « Rédaction »", "Lire cette partie",
                    "Note interne, pour vous seul", "Harmoniser le ton", "elles ne partent pas chez l'acheteur"):
        assert libelle in r, libelle
    assert '<template v-if="l.genere">' in r and "atlRepManques()" in r and "atlRepHarm() && !atlMobile" in r
    assert 'v-if="atlRepAValider(l)"' in r and ':disabled="!!atl.rep.busy || !atlRepChefPeutValider()"' in r
    # Une partie tirée du groupement n'a ni « Rédigée par », ni longueur, ni date : personne ne la rédige.
    gen = r[r.index('<template v-if="l.genere">'):r.index("<template v-else>", r.index('<template v-if="l.genere">'))]
    assert "Rédigée par" not in gen and "atlRepRedacteur" not in gen and "<textarea" not in gen
    for route in ('"/valider-dossier"', '"/repartition/harmoniser"'):
        assert route in JS_REP, route
    assert 'action === "harmoniser"' in JS and 'r.kind === "atelier_harmoniser"' in JS
    out = _node("console.log(JSON.stringify({q: atlRepQfqValidationsTexte(["
                " {membre: 'chef_de_file', invite_id: null, nom: 'Chef', statut: 'valide'},"
                " {membre: 'partenaire', invite_id: 4, nom: 'A', statut: 'a_revalider'},"
                " {membre: 'partenaire', invite_id: 5, nom: 'B', statut: 'a_faire'}]),"
                " v: atlRepQfqValidationsTexte([]), st: atlRepStatutCls('a_valider')}));")
    assert out == {"q": "Validée par vous ; à revalider par A ; à valider par B.", "v": "", "st": "st-envoye"}


def test_vue_du_chef_harmoniser_propose_seulement_entre_membres_differents(client, auth, fake_llm):
    fake = fake_llm(lambda kw: (_ for _ in ()).throw(AssertionError("aucune IA pour lire la répartition")))
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    assert vue["harmoniser"]["jonctions"] == 0 and vue["harmoniser"]["message"]
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    for s in _etat(client, h, pid)["sections"]:
        if s["auteur"]["type"] == "organisation":
            r = client.put(f"/api/atelier/{pid}/sections/{s['id']}/texte", headers=h,
                           json={"texte": f"Notre réponse pour {s['intitule']}.", "base_version_id": None})
            assert r.status_code == 200, r.text
    v = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    assert v["harmoniser"]["jonctions"] >= 1 and fake.calls == []
    # La partie « Qui fait quoi », ouverte par le chef de file : son texte, ce que chacun apporte, la note interne.
    q = next(l for l in v["sections"] if l.get("genere") == "grp_qfq")
    d = client.get(f"/api/atelier/{pid}/repartition/{q['section_id']}", headers=h).json()
    assert d["texte_commun"]["texte"] and d["note_interne"]["lignes"] and d["validations"]
    assert all({"nom", "lot", "qualifications"} <= set(m) for m in d["membres"])


def test_ecran_regles_d_interface():
    r = _sans_commentaires_html(REP)
    chaines = " ".join(re.findall(r'"((?:[^"\\\n]|\\.)*)"', _sans_commentaires_js(JS_REP)))
    for nom, bloc in (("écran", r), ("script", chaines), ("css", CSS_REP)):
        assert not EMOJI.search(bloc), nom
        low = bloc.lower()
        for mot in ("vérifié", "verifie", "consortium", "mandataire", "signer", "signé", "workflow", "prompt",
                    "token"):
            assert mot not in low, (nom, mot)
    for m in re.finditer(r"<button\b(?:[^>\"]|\"[^\"]*\")*>", r):
        assert 'type="button"' in m.group(0), m.group(0)[:120]
    assert r.count('class="tip-b" role="tooltip"') == r.count("tip-b") >= 4          # bulles (i)
    assert set(re.findall(r'v-html="([^"]+)"', REP)) == {"atlRepHtml(b.v)"}         # rendu sûr seulement
    assert "atlRepHtml(v) { return v ? atlMdToHtml(v.texte, [], { refsPartenaire: true }) : \"\"; }" in JS_REP
    # 375 px : champs empilés, avant / après l'un sous l'autre, aucune barre horizontale.
    assert ".atl-rep-champs { display:grid;" in CSS_REP and "minmax(0," in CSS_REP
    assert "@media (max-width:860px) {\n  .atl-rep-cmp.deux { grid-template-columns:minmax(0,1fr); }" in CSS_REP
    assert "@media (max-width:640px) {\n  .atl-rep-head, .atl-rep-l { padding:12px; }" in CSS_REP
    assert ".rn-tabs.atl-onglets { grid-template-columns:repeat(2, minmax(0,1fr)); }" in CSS_REP
    assert ".atl-rep-l { padding:16px;" in CSS_REP and ".atl-rep-head { padding:16px; }" in CSS_REP


def test_fonctions_pures_de_l_ecran_sous_node():
    out = _node(
        "const c = {par_type: {documents: 2, declare: 3, public: 0, estimation: 0, calcul: 0, acheteur: 0},"
        " avec_source: 5, a_relire: 1, engagements: 0};\n"
        "console.log(JSON.stringify({"
        " a: atlRepCompteurs({compteurs: c, a_completer: 0, faits_a_relire: 1}),"
        " b: atlRepCompteurs({compteurs: {par_type: {declare: 1}, avec_source: 1, a_relire: 0, engagements: 2}, a_completer: 2}),"
        " c: atlRepCompteurs({compteurs: null, faits_a_relire: 3, a_completer: 1}),"
        " d: atlRepCompteurs({compteurs: {par_type: {}, avec_source: 0, a_relire: 0, engagements: 0}, a_completer: 0}),"
        " e: atlRepCompteurs(null),"
        " st: ['a_rediger', 'en_cours', 'envoyee', 'a_revalider', 'validee', 'x'].map(atlRepStatutCls),"
        " dem: atlRepADemander({sections: ["
        "   {redacteur: {type: 'partenaire', invite_id: 7, nom: 'A'}, statut: 'a_rediger'},"
        "   {redacteur: {type: 'partenaire', invite_id: 7, nom: 'A'}, statut: 'a_revalider'},"
        "   {redacteur: {type: 'partenaire', invite_id: 8, nom: 'B'}, statut: 'envoyee'},"
        "   {redacteur: {type: 'chef_de_file', invite_id: null, nom: 'Chef de file'}, statut: 'a_rediger'}]}),"
        " txt: atlRepDemandeTexte({demandees: [{nom: 'A', email_parti: true}, {nom: 'C', email_parti: false}],"
        "   sans_adresse: [{nom: 'B'}, {nom: 'D'}], deja_demandees: [{nom: 'E'}], plafond_atteint: [{nom: 'F'}]}),"
        " vide: atlRepDemandeTexte({demandees: [], sans_adresse: [], deja_demandees: [], plafond_atteint: []}),"
        " val: atlRepValidationsTexte({membres: [{membre: 'chef_de_file', nom: 'Chef de file', statut: 'valide'},"
        "   {membre: 'partenaire', nom: 'A', statut: 'a_revalider'}, {membre: 'partenaire', nom: 'B', statut: 'a_faire'}]}),"
        " renv: [atlRepARenvois('Texte [F3, S2].'), atlRepARenvois('Sans renvoi [À compléter : x].')],"
        " part: atlMdToHtml('Nos 4 bennes [S1] <b>x</b>.', [], {refsPartenaire: true}),"
        " moi: atlMdToHtml('Nos 4 bennes [S1].', [])}));")
    assert out["a"] == "5 faits avec une source : 2 trouvés dans ses documents, 3 déclarés · 1 fait à relire"
    assert out["b"] == ("1 fait avec une source : 1 déclaré · 2 engagements à confirmer · "
                        "2 passages « [À compléter] »")
    assert out["c"] == "3 faits à relire · 1 passage « [À compléter] »"
    assert out["d"] == "Aucun fait avec une source" and out["e"] == ""
    assert out["st"] == ["neutral", "atl-st-brouillon", "st-envoye", "a_etudier", "go", "neutral"]
    assert out["dem"] == [{"invite_id": 7, "nom": "A", "parties": 2}]
    assert out["txt"] == ["Demande envoyée à A.", "L'email à C n'est pas parti : réessayez dans quelques minutes.",
                          "Aucune adresse email sur le lien de B, D : transmettez-leur leur lien vous-même, depuis "
                          "la page du marché.", "Déjà demandée il y a moins de 15 minutes à E.",
                          "Limite d'envois du jour atteinte : F recevra la demande si vous réessayez demain."]
    assert out["vide"] == ["Aucune partie à demander : chaque partenaire a envoyé ses parties."]
    assert out["val"] == "Dossier assemblé validé par vous ; à revalider par A ; à valider par B."
    assert out["renv"] == [True, False]
    # Renvoi d'une part de partenaire : « source du partenaire », sans lien ni identifiant cliquable.
    assert ('<sup class="atl-ref-p" title="Source du partenaire">S1<span class="sr-only"> : source du '
            'partenaire</span></sup>') in out["part"]
    assert "data-ref" not in out["part"] and "&lt;b&gt;x&lt;/b&gt;" in out["part"] and "<b>" not in out["part"]
    assert '<sup class="atl-ref" data-ref="S1">S1</sup>' in out["moi"]           # l'atelier du chef : inchangé


@pytest.mark.parametrize("motif", ["atlPillCls(s)", "atlPillLib(s)", "atlPillCls(atlSec())", "atlOrigine(atlSec())",
                                   "atlRepVoir(atlSec().id)", "Rédigée par {{ s.auteur.libelle }}",
                                   "atlRenvoisPart(atlSec())"])
def test_atelier_montre_la_part_d_un_partenaire_avec_son_statut(motif):
    a = _sans_commentaires_html(ATELIER)
    assert motif in a, motif
    # Le texte d'une part de partenaire, dans l'atelier aussi, montre ses renvois comme « source du partenaire ».
    assert "atlHtml(s) { const v = s && s.version_courante; return v ? atlMdToHtml(v.texte, v.faits, " \
           "{ refsPartenaire: !s.prive_visible }) : \"\"; }" in JS
