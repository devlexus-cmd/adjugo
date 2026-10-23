"""Contrôle des bugs d'octobre 2026, groupe « cotraitance » (répondre à plusieurs) : chaque test dit ce que le
logiciel DOIT faire d'après ses contrats (docs/COTRAITANCE_V2_VAGUE2_API.md, docs/COTRAITANCE_V2_ARCHITECTURE.md,
docs/REORGANISATION_V2B.md § S.4) et ses textes affichés ; tous échouaient sur cfe04e1, chacun sur son défaut.

1. Convention générée puis modifiée (retour en brouillon) : l'offre commune n'est plus figée (avant : l'ancien total
   restait montré au partenaire et au chef de file sous une convention en brouillon).
2. Retirer un sous-traitant ne rend pas la convention caduque (il n'en est pas membre).
3. Un lien en lecture seule (« peut contribuer » décoché) n'est pas membre du groupement : le créer ou le retirer ne
   rend pas la convention caduque ; il ne bloque ni la convention, ni « Prêt à déposer », ni l'étape « Toutes les parts
   reçues » ; le coffre-fort croisé, les manques et les comptes « X sur Y » ne le comptent pas.
4. Invitation du réseau sans réponse : la liste des invitations et « À plusieurs » ne disent rien de son brouillon.
5. « Renvoyer l'invitation » sur un lien expiré : refus lisible, aucun courriel (et le bouton n'est plus proposé).
6. Les courriels planifiés (rappel de part, attestations) ne partent pas vers un lien expiré.
7. « À deux, le total révèle la part de l'autre » : compté sur les membres du groupement, pas sur les liens.
8. « Figer l'offre » (route de la vague 1) : ni courriel ni total au sous-traitant, son prix hors du total.
9. Courriel d'invitation du réseau à un sous-traitant : « vous propose d'intervenir ».
10. « Total prévisionnel » du suivi du groupement = total de la convention (part du chef de file saisie dans
    « Convention et accords », sans le sous-traitant).
"""
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta

import pytest

from tests.test_convention_groupement import (_db, _gen, _groupement, _invite, _part, _project, _set_company,
                                              _valider)
from tests.test_reseau_partenaires import _org, _publish, reg  # noqa: F401  (fixture autouse du réseau simulé)
from tests.test_reseau_partenaires import _project as _projet_reseau

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "app", "static", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "static", "app.html"), encoding="utf-8").read()


@pytest.fixture
def groupes(monkeypatch):
    """Courriels de groupement (envoi hors requête) capturés de façon synchrone."""
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda mails: sent.extend(mails))
    return sent


@pytest.fixture
def courriels(monkeypatch):
    """Courriels envoyés un par un (send_email), capturés ; l'envoi « réussit »."""
    sent = []
    import app.services.alerts as A
    import app.services.email as E

    def _send(to, subject, text, html=None, **kw):
        sent.append((to, subject, text))
        return True
    monkeypatch.setattr(E, "send_email", _send)
    monkeypatch.setattr(A, "send_email", _send)
    return sent


def _set_invite(invite_id, **fields):
    from app.models import ProjectInvite
    db = _db()
    try:
        inv = db.get(ProjectInvite, invite_id)
        for k, v in fields.items():
            setattr(inv, k, v)
        db.commit()
    finally:
        db.close()


def _sous_traitant(client, h, pid, name="Échafaudages Sous-Traitant", recipient="", prix=None):
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"company_name": name, "role": "sous_traitant", "recipient": recipient})
    assert r.status_code == 200, r.text
    st = r.json()
    if prix is not None:
        _part(client, st["token"], name, "Échafaudage", prix)
    return st


def _lecture_seule(client, h, pid, name="Lecture Seule SARL", **extra):
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"company_name": name, "can_contribute": False, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _conv(client, h, pid):
    return client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()


# ── 1. Retour en brouillon : l'offre n'est plus figée ─────────────────────────────────
def test_convention_modifiee_apres_generation_defige_l_offre(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer" and c["total_offre_ht"] == 125000.5
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                   json={"params": {"part_mandataire_ht": 90000}, "confirmer_modification": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft" and r.json()["total_estime_ht"] == 155000.5
    # Le partenaire ne lit plus « Offre commune figée … 125 000,50 € HT ».
    st = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]["state"]
    assert st["offer_frozen"] is False and st["total_offre_ht"] is None and st["frozen_at"] is None
    # Page du marché du chef de file : ni « Offre commune figée », ni l'ancien total.
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["offre"]["frozen"] is False and ck["offre"]["total_ht"] is None
    assert ck["state"]["offer_frozen"] is False
    # Le défigement est tracé (journal du membre).
    j = client.get(f"/api/invite/{invs[0]['token']}/journal").json()["entries"]
    assert any(e["action"] == "offer.unfrozen" for e in j)
    # Un simple paramètre changé fait de même.
    pid2, invs2 = _groupement(client, auth, n=1)
    assert _gen(client, h, pid2).json()["status"] == "a_signer"
    r = client.put(f"/api/projects/{pid2}/groupement/convention", headers=h,
                   json={"params": {"pi": "copropriete"}, "confirmer_modification": True})
    assert r.status_code == 200 and r.json()["status"] == "draft", r.text
    assert client.get(f"/api/invite/{invs2[0]['token']}").json()["for_member"]["state"]["offer_frozen"] is False
    # Regénérée, la convention fige de nouveau l'offre, avec le nouveau total.
    c2 = _gen(client, h, pid).json()
    assert c2["status"] == "a_signer" and c2["total_offre_ht"] == 155000.5
    st = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]["state"]
    assert st["offer_frozen"] is True and st["total_offre_ht"] == 155000.5


# ── 2. Retirer un sous-traitant ───────────────────────────────────────────────────────
def test_retirer_un_sous_traitant_garde_la_convention_et_les_accords(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    st = _sous_traitant(client, h, pid, prix=7000)
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer" and c["total_offre_ht"] == 100000.0
    assert _valider(client, f"/api/invite/{invs[0]['token']}/convention/valider", c).status_code == 200
    assert client.delete(f"/api/projects/{pid}/invites/{st['id']}", headers=h).status_code == 200
    g = _conv(client, h, pid)
    assert g["status"] == "a_signer", g["status"]
    assert sorted(s["status"] for s in g["signatures"]) == ["pending", "signed"]
    fm = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]["state"]
    assert fm["offer_frozen"] is True and fm["total_offre_ht"] == 100000.0
    j = [e["action"] for e in client.get(f"/api/invite/{invs[0]['token']}/journal").json()["entries"]]
    assert "convention.perimee" not in j and "offer.unfrozen" not in j
    # Témoin : retirer un partenaire du groupement (signataire) la rend toujours caduque.
    assert client.delete(f"/api/projects/{pid}/invites/{invs[0]['id']}", headers=h).status_code == 200
    assert _conv(client, h, pid)["status"] == "perimee"


# ── 3. Lien en lecture seule : pas membre du groupement ─────────────────────────────────
def test_lien_en_lecture_seule_cree_ou_retire_apres_generation_ne_rend_rien_caduc(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    # Un lien en lecture seule décliné avant la génération…
    ro_decline = _lecture_seule(client, h, pid, name="Bureau d'Études Décliné")
    assert client.post(f"/api/invite/{ro_decline['token']}/decline").status_code == 200
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer"
    assert _valider(client, f"/api/invite/{invs[0]['token']}/convention/valider", c).status_code == 200
    # … un autre créé après la génération : ni manque, ni péremption, accords gardés.
    ro = _lecture_seule(client, h, pid, name="Expert Comptable SARL")
    assert client.get(f"/api/invite/{ro['token']}/contribution").status_code == 403   # il ne peut rien déposer
    g = _conv(client, h, pid)
    assert g["status"] == "a_signer" and not any("Expert Comptable" in m for m in g["manques"]), g["manques"]
    assert sorted(s["status"] for s in g["signatures"]) == ["pending", "signed"]
    fm = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]["state"]
    assert fm["offer_frozen"] is True and fm["total_offre_ht"] == 100000.0
    # Le retirer, ou retirer celui qui avait décliné, ne change rien non plus.
    assert client.delete(f"/api/projects/{pid}/invites/{ro['id']}", headers=h).status_code == 200
    assert client.delete(f"/api/projects/{pid}/invites/{ro_decline['id']}", headers=h).status_code == 200
    g = _conv(client, h, pid)
    assert g["status"] == "a_signer"
    assert sorted(s["status"] for s in g["signatures"]) == ["pending", "signed"]


def test_lien_en_lecture_seule_aucune_tache_aucun_manque(client, auth, groupes, courriels):
    h = auth["headers"]
    pid, _ = _groupement(client, auth, n=0)
    ro = _lecture_seule(client, h, pid)
    p = _invite(client, h, pid, "Partenaire Actif SARL", recipient=f"{uuid.uuid4().hex[:6]}@partenaire.fr")
    _part(client, p["token"], "Partenaire Actif SARL", "Lot 2 — Électricité", 150000)
    # Courriel au chef de file : « Partenaires prêts : 1 sur 1. » (le lien en lecture seule n'a aucune part à donner).
    pret = [t for (to, s, t) in courriels if to == auth["email"] and "Partenaire Actif SARL a soumis sa part" in s]
    assert pret and "Partenaires prêts : 1 sur 1." in pret[-1], pret
    # Convention : rien ne manque, elle peut être générée.
    g = _conv(client, h, pid)
    assert g["peut_generer"] is True and g["manques"] == [], g["manques"]
    # Étape du groupement : toutes les parts reçues ; « parts reçues 1 sur 1 ».
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["state"] == "parts_completes" and st["n_members"] == 1 and st["n_submitted"] == 1
    assert "Lecture Seule SARL" not in json.dumps(st["members"])
    # « Prêt à déposer » : ni sa part, ni ses attestations.
    dep = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert not any("Lecture Seule" in m for m in dep["manques"] + dep["avertissements"]), dep["manques"]
    # Suivi du groupement (page du marché) : ni manque, ni ligne du coffre-fort croisé, « 1 sur 1 ».
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert not any("Lecture Seule" in m for m in ck["readiness"]["missing"]), ck["readiness"]["missing"]
    assert ck["readiness"]["invited"] == 1 and ck["readiness"]["submitted"] == 1
    assert [m["company"] for m in ck["coffre"]["members"]] == ["Partenaire Actif SARL"]
    assert [x["company"] for x in ck["partners"]] == ["Partenaire Actif SARL"]
    # Coffre-fort croisé vu par l'autre partenaire : aucune pièce réclamée au lien en lecture seule.
    cc = client.get(f"/api/invite/{p['token']}/coffre-croise").json()
    assert [m["company"] for m in cc["members"]] == ["Partenaire Actif SARL"]
    assert not any("Lecture Seule" in a for a in cc["alerts"])
    # « À plusieurs » (Mes marchés) : « parts reçues 1 sur 1 ».
    mine = next(x for x in client.get("/api/consortiums", headers=h).json()["consortiums"] if x["project_id"] == pid)
    assert mine["partners"] == 1 and mine["submitted"] == 1
    # La convention se génère, sans lui comme signataire.
    c = _gen(client, h, pid)
    assert c.status_code == 200, c.text
    assert [s["company"] for s in c.json()["signatures"]] == ["Breizh Couverture", "Partenaire Actif SARL"]
    assert _conv(client, h, pid)["status"] == "a_signer"


def test_lien_en_lecture_seule_seul_n_en_fait_pas_un_groupement(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    _lecture_seule(client, h, pid)
    dep = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert dep["pour"] == "seul", dep
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["n_members"] == 0 and st["state"] not in ("invitation", "parts_completes")


def test_lien_en_lecture_seule_ne_prend_pas_le_partenaire_hors_ligne(client, auth, groupes):
    """Un partenaire rattaché au marché (candidat hors ligne) à qui l'on envoie un lien en lecture seule reste un
    candidat hors ligne : avant, l'invitation le « portait », et, le lien ne comptant plus, il disparaissait de la
    convention sans un mot."""
    h = auth["headers"]
    pid, _ = _groupement(client, auth, n=1)
    from app.models import User
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    db = _db()
    try:
        owner = db.query(User).filter(User.email == auth["email"]).first()
        ct = Cotraitant(user_id=owner.id, name="Kerjean Menuiserie", siret="55566677700088",
                        representant_legal="Anne Kerjean", city="Brest")
        db.add(ct)
        db.flush()
        lk = ProjectCotraitant(project_id=pid, cotraitant_id=ct.id, role="cotraitant", lot="Lot 5 — Menuiserie",
                               source="reseau")
        db.add(lk)
        db.commit()
        link_id = lk.id
    finally:
        db.close()
    _lecture_seule(client, h, pid, name="Kerjean Menuiserie", link_id=link_id)
    g = _conv(client, h, pid)
    assert any(o["link_id"] == link_id for o in g["candidats_hors_ligne"]), g["candidats_hors_ligne"]
    assert any("Kerjean Menuiserie" in w and "ni invité ni ajouté hors ligne" in w for w in g["avertissements"])


# ── 4. Invitation du réseau sans réponse ─────────────────────────────────────────────
def test_invitation_reseau_sans_reponse_brouillon_invisible_du_chef_de_file(client, reg, courriels):  # noqa: F811
    b = _org(client, "Partenaire Silencieux")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef De File Réseau")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _projet_reseau(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b_pid, "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    inv_id = r.json()["invitation"]["id"]
    recues = client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"]
    token = next(x["token"] for x in recues if x["mandataire"] == a["name"])
    assert client.get(f"/api/invite/{token}").json()["apercu_minimal"] is True
    v = client.get(f"/api/invite/{token}/contribution").json()["version"]
    r = client.put(f"/api/invite/{token}/contribution", json={
        "version": v, "lot": "Lot 2 — Électricité", "prix_lot_ht": 41234, "memoire_paragraph": "Notre méthode.",
        "references": [{"titre": "École de Brest", "client": "Ville de Brest", "annee": 2024}]})
    assert r.status_code == 200, r.text
    lst = client.get(f"/api/projects/{pid}/invites", headers=a["headers"]).json()
    me = next(x for x in lst if x["id"] == inv_id)
    assert me["recipient_masque"] is True
    # « vu » (il a ouvert l'aperçu) n'est pas un champ du brouillon ; « brouillon » et « prix renseigné » en sont.
    assert me["state"] == "viewed" and me["contribution_status"] is None and me["has_price"] is False, me
    mine = next(x for x in client.get("/api/consortiums", headers=a["headers"]).json()["consortiums"]
                if x["project_id"] == pid)
    assert mine["readiness_pct"] == 0 and mine["pieces"] == 0, mine
    # Refusée ensuite : toujours rien de son brouillon.
    assert client.post(f"/api/invite/{token}/decline").status_code == 200
    me = next(x for x in client.get(f"/api/projects/{pid}/invites", headers=a["headers"]).json() if x["id"] == inv_id)
    assert me["state"] == "declined" and me["contribution_status"] is None and me["has_price"] is False


# ── 5. Renvoyer une invitation dont le lien a expiré ───────────────────────────────────
def test_renvoyer_un_lien_expire_est_refuse_sans_courriel(client, auth, courriels):
    h = auth["headers"]
    pid = _project(client, h, name="Marché relancé")
    adr = f"alpha_{uuid.uuid4().hex[:6]}@partenaire.example"
    inv = _invite(client, h, pid, "Alpha SARL", recipient=adr)
    _set_invite(inv["id"], expires_at=datetime.utcnow() - timedelta(days=1),
                emailed_at=datetime.utcnow() - timedelta(hours=1))
    assert client.get(f"/api/invite/{inv['token']}").status_code == 410
    avant = len([m for m in courriels if m[0] == adr])
    r = client.post(f"/api/projects/{pid}/invites/{inv['id']}/resend", headers=h)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Ce lien a expiré — créez une nouvelle invitation."
    assert len([m for m in courriels if m[0] == adr]) == avant


def test_ecran_ne_propose_pas_de_relancer_un_lien_expire():
    """inviteRelancable (bouton « Renvoyer l'invitation par email », « Relancer les partenaires ») exécuté sous Node."""
    if not shutil.which("node"):
        pytest.skip("node absent")
    m = re.search(r"^    inviteRelancable\(inv\) \{(.*)\},$", JS, re.M)
    assert m, "inviteRelancable introuvable (une ligne)"
    corps = m.group(1)
    hier = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    demain = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
    prog = ("const o = { inviteRelancable(inv) {" + corps + "} };\n"
            f"console.log(JSON.stringify([o.inviteRelancable({{recipient: 'a@b.fr', expires_at: {json.dumps(hier)}}}),"
            f" o.inviteRelancable({{recipient: 'a@b.fr', expires_at: {json.dumps(demain)}}}),"
            " o.inviteRelancable({recipient: 'a@b.fr', expires_at: null}),"
            f" o.inviteRelancable({{source: 'reseau_adjugo', expires_at: {json.dumps(hier)}}})]));")
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [False, True, True, False]


# ── 6. Courriels planifiés vers un lien expiré ──────────────────────────────────────
def test_aucun_courriel_planifie_vers_un_lien_expire(client, auth, courriels):
    from app.services import alerts
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    # Part pas encore soumise, marché à J+2 : rappel de part.
    pid = _project(client, h, name="Toiture de la mairie", deadline_days=2)
    exp = f"exp_{uuid.uuid4().hex[:6]}@partenaire.fr"
    ok = f"ok_{uuid.uuid4().hex[:6]}@partenaire.fr"
    i_exp = _invite(client, h, pid, "Expiré SARL", recipient=exp)
    i_ok = _invite(client, h, pid, "Valide SARL", recipient=ok)
    _set_invite(i_exp["id"], expires_at=datetime.utcnow() - timedelta(days=1))
    # Part soumise, marché à J+5 : alerte « Attestations à mettre à jour » (aucune pièce déposée).
    pid2 = _project(client, h, name="Préau de l'école", deadline_days=5)
    exp2 = f"exp2_{uuid.uuid4().hex[:6]}@partenaire.fr"
    ok2 = f"ok2_{uuid.uuid4().hex[:6]}@partenaire.fr"
    j_exp = _invite(client, h, pid2, "Expiré Deux SARL", recipient=exp2)
    j_ok = _invite(client, h, pid2, "Valide Deux SARL", recipient=ok2)
    _part(client, j_exp["token"], "Expiré Deux SARL", "Lot 2", 1000)
    _part(client, j_ok["token"], "Valide Deux SARL", "Lot 3", 1000)
    _set_invite(j_exp["id"], expires_at=datetime.utcnow() - timedelta(days=1))
    assert client.get(f"/api/invite/{i_exp['token']}").status_code == 410
    n0 = len(courriels)                         # les invitations elles-mêmes sont parties : on lit la suite
    db = _db()
    try:
        alerts.run_cotraitance_reminders(db)
    finally:
        db.close()
    apres = courriels[n0:]
    pour = lambda adr: [s for (to, s, _t) in apres if to == adr]  # noqa: E731
    assert pour(ok) and "il vous reste 2 jours" in pour(ok)[0]              # témoin : un lien valide est relancé
    assert any("Attestations à mettre à jour" in s for s in pour(ok2))       # témoin
    assert pour(exp) == [] and pour(exp2) == [], (pour(exp), pour(exp2))
    # Le récapitulatif du chef de file ne dit pas « prévenus » d'un partenaire qui ne l'a pas été.
    recap = [t for (to, s, t) in apres if to == auth["email"] and "Préau de l'école" in s]
    assert recap and all("Expiré Deux SARL" not in t for t in recap), recap


# ── 7. « À deux, le total révèle la part de l'autre » ───────────────────────────────
def test_avertissement_a_deux_membres_compte_les_membres_pas_les_liens(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    _sous_traitant(client, h, pid, prix=7000)
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer" and c["total_offre_ht"] == 100000.0
    fm = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]
    cv = client.get(f"/api/invite/{invs[0]['token']}/convention").json()
    assert cv["warning_two_members"] is True
    assert fm["state"]["offer_frozen"] is True and fm["warning_two_members"] is True
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["offre"]["warning_two_members"] is True
    # Témoin : à trois membres, pas d'avertissement.
    pid3, invs3 = _groupement(client, auth, n=2)
    _sous_traitant(client, h, pid3)
    assert _gen(client, h, pid3).json()["status"] == "a_signer"
    assert client.get(f"/api/invite/{invs3[0]['token']}").json()["for_member"]["warning_two_members"] is False


# ── 8. « Figer l'offre » (vague 1) ───────────────────────────────────────────────────
def test_figer_l_offre_ni_courriel_ni_prix_du_sous_traitant(client, auth, groupes):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid = _project(client, h)
    p1 = _invite(client, h, pid, "Le Gall Électricité", recipient=f"p1_{uuid.uuid4().hex[:6]}@partenaire.fr")
    _part(client, p1["token"], "Le Gall Électricité", "Lot 2 — Électricité", 40000)
    st_adr = f"st_{uuid.uuid4().hex[:6]}@partenaire.fr"
    _sous_traitant(client, h, pid, recipient=st_adr, prix=7000)
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 60000})
    assert r.status_code == 200, r.text
    assert r.json()["total_ht"] == 100000.0                     # 40 000 + 60 000 : le sous-traitant n'y est pas
    dest = [m[0] for m in groupes if "L'offre commune est figée" in m[1]]
    assert dest == [p1["recipient"]], dest
    assert all("107" not in m[2] for m in groupes)
    fm = client.get(f"/api/invite/{p1['token']}").json()["for_member"]["state"]
    assert fm["total_offre_ht"] == 100000.0
    # Un lien en lecture seule ajouté ensuite (l'offre est défigée, comme pour toute invitation créée) : il ne
    # bloque pas un nouveau « figer » et ne reçoit pas le total.
    groupes.clear()
    ro_adr = f"ro_{uuid.uuid4().hex[:6]}@partenaire.fr"
    _lecture_seule(client, h, pid, recipient=ro_adr)
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 60000})
    assert r.status_code == 200, r.text
    dest = [m[0] for m in groupes if "L'offre commune est figée" in m[1]]
    assert dest == [p1["recipient"]], dest


# ── 9. Courriel d'invitation du réseau à un sous-traitant ──────────────────────────────
def test_invitation_reseau_sous_traitant_elision():
    from app.services.email_invitation import invitation
    for chef in ("Breizh Couverture", ""):
        c = invitation(chef=chef, marche="École", url="https://exemple.test/invite/x", role="sous_traitant",
                       reseau=True)
        assert "de intervenir" not in c["texte"] and "de intervenir" not in c["html"]
        assert "vous propose d'intervenir comme sous-traitant sur le marché « École »." in c["texte"]
    # Le partenaire du groupement garde « vous propose de rejoindre ».
    c = invitation(chef="Breizh Couverture", marche="École", url="https://exemple.test/invite/x", reseau=True)
    assert "vous propose de rejoindre son groupement" in c["texte"]


# ── 10. « Total prévisionnel » = total de la convention ───────────────────────────────
def test_total_previsionnel_du_suivi_egal_au_total_de_la_convention(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)                 # part du chef de file : 60 000 (Convention et accords)
    _sous_traitant(client, h, pid, prix=7000)
    g = _conv(client, h, pid)
    assert g["total_estime_ht"] == 100000.0
    o = client.get(f"/api/projects/{pid}/consortium", headers=h).json()["offre"]
    assert o["frozen"] is False
    assert o["total_ht_estime"] == g["total_estime_ht"] == 100000.0, o
    assert o["lead_total_ht"] == 60000.0 and o["lead_source"] == "convention", o
    # Sans part saisie dans la convention, la part vient de l'estimation de prix (et le dit).
    from app.models import Project
    pid2 = _project(client, h, name="Gymnase")
    db = _db()
    try:
        p = db.get(Project, pid2)
        p.estimate = {"total_ht": 50000}
        db.commit()
    finally:
        db.close()
    i2 = _invite(client, h, pid2, "Le Gall Électricité")
    _part(client, i2["token"], "Le Gall Électricité", "Lot 2", 20000)
    o2 = client.get(f"/api/projects/{pid2}/consortium", headers=h).json()["offre"]
    assert o2["total_ht_estime"] == 70000.0 and o2["lead_total_ht"] == 50000.0 and o2["lead_source"] == "estimation"
    # L'écran dit d'où vient la part du chef de file.
    assert "indiquée dans « Convention et accords »" in HTML
    assert re.search(r"lead_source\s*===\s*'convention'", HTML)
