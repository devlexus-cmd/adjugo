"""
Co-traitance v2 — corrections de la revue des vagues 3 et 4 (domaine B), parcours qui passent par
une invitation du RÉSEAU Adjugo (aperçu minimal tant que le partenaire n'a pas accepté).

Chaque test échoue sans la correction qu'il couvre :
- convention : une invitation réseau pas encore acceptée ne lit RIEN de la convention (ni le
  brouillon, qui cite l'acheteur et la composition du groupement, ni le PDF, ni l'accord) ;
  aucune route /api/invite/{token}/… ne renvoie l'acheteur ni le nom d'un autre membre.
"""
import json

import pytest

from tests.test_reseau_partenaires import _org, _profile_row, _project, _publish, reg  # noqa: F401  (fixture autouse)


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.services.email as E
    import app.routers.invites as I

    def _send(to, subject, text, html=None, **kw):
        sent.append((to, subject, text))
        return True
    monkeypatch.setattr(E, "send_email", _send)
    monkeypatch.setattr(I, "_send_mails_async", lambda m: sent.extend(m))
    return sent


def _put_part(client, token, **fields):
    v = client.get(f"/api/invite/{token}/contribution").json()["version"]
    r = client.put(f"/api/invite/{token}/contribution", json={"version": v, **fields})
    assert r.status_code == 200, r.text


def _set_company(org_id, **fields):
    from app.core.database import SessionLocal
    from app.models import Company
    db = SessionLocal()
    try:
        c = db.query(Company).filter(Company.user_id == org_id).first()
        for k, v in fields.items():
            setattr(c, k, v)
        db.commit()
    finally:
        db.close()


def _scenario_brouillon_et_invitation_reseau(client, reg, mails):
    """Chef de file publié + un partenaire manuel (part soumise) + brouillon de convention, puis
    invitation RÉSEAU d'un second partenaire, pas encore acceptée. Renvoie (chef, partenaire, pid, token)."""
    part = _org(client, "Le Gall Électricité")
    part_pid = _publish(client, reg, part)
    chef = _org(client, "Breizh Couverture")
    _publish(client, reg, chef, metiers=("couverture",))
    _set_company(chef["id"], address="1 rue du Port", representant_legal="Eliot Viegas")
    pid = _project(client, chef)
    m = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                    json={"recipient": "morvan@plomberie-secrete.fr", "company_name": "Morvan Plomberie"}).json()
    _put_part(client, m["token"], company_name="Morvan Plomberie", lot="Lot 3 — Plomberie", prix_lot_ht=25000,
              representant_legal="Jean Morvan", signataire_qualite="Gérant", siret="11111111100011")
    assert client.post(f"/api/invite/{m['token']}/contribution/submit").status_code == 200
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=chef["headers"], json={
        "forme": "conjoint", "params": {"part_mandataire_ht": 60000, "lot_mandataire": "Lot 1 — Couverture"}})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=chef["headers"],
                    json={"profile_id": part_pid, "role": "cotraitant", "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    recues = client.get("/api/reseau/invitations", headers=part["headers"]).json()["invitations"]
    tok = next(x["token"] for x in recues if x["mandataire"] == chef["name"])
    return chef, part, pid, tok


SECRETS = ("Ville de Quimper", "Morvan Plomberie", "Jean Morvan", "11111111100011", "1 rue du Port")


def test_convention_refusee_tant_que_l_invitation_reseau_n_est_pas_acceptee(client, reg, mails):
    chef, part, pid, tok = _scenario_brouillon_et_invitation_reseau(client, reg, mails)
    assert client.get(f"/api/invite/{tok}").json()["apercu_minimal"] is True
    for path in ("/convention", "/convention/pdf"):
        r = client.get(f"/api/invite/{tok}{path}")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "apercu_minimal", (path, r.text)
        assert not any(s in r.text for s in SECRETS), path
    r = client.post(f"/api/invite/{tok}/convention/valider",
                    json={"content_hash": "x", "signataire_nom": "A", "signataire_qualite": "B", "accepte": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "apercu_minimal"
    # Aucune route de lecture du lien ne cite l'acheteur ni un autre membre.
    for path in ("", "/contribution", "/coffre-croise", "/journal", "/journal/integrity", "/convention"):
        r = client.get(f"/api/invite/{tok}{path}")
        hits = [s for s in SECRETS if s in r.text]
        assert not hits, (path, r.status_code, hits)
    # Après acceptation depuis le compte : la convention (brouillon) redevient lisible.
    assert client.post(f"/api/invite/{tok}/claim", headers=part["headers"]).status_code == 200
    r = client.get(f"/api/invite/{tok}/convention")
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert "Morvan Plomberie" in json.dumps(r.json(), ensure_ascii=False)


def test_page_partenaire_ne_charge_pas_la_convention_en_apercu_minimal():
    import os
    html = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "app", "static", "invite.html"), encoding="utf-8").read()
    i = html.index("Chargement de la convention")
    bloc = html[i - 700:i + 400]
    assert "if (!d.apercu_minimal)" in bloc and "loadConvention();" in bloc


def _export(client, tok):
    from app.services import journal_membre as jm
    jm.reset_caches()
    r = client.get(f"/api/invite/{tok}/journal/export")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert jm.verify_export(doc)["ok"]
    return doc


def test_journal_reseau_preuve_apres_acceptation_et_projection_durable(client, reg, mails):
    """Avant acceptation : ni vérification ni preuve (le journal ne montre que ses entrées et les
    événements du groupement s'y ajouteraient à l'acceptation). Après : la projection ne change
    plus, même quand le compte qui avait accepté est effacé (lien libéré) — l'export suivant
    PROLONGE toujours le précédent, aucune fausse alerte."""
    from app.services import journal_membre as jm
    chef, part, pid, tok = _scenario_brouillon_et_invitation_reseau(client, reg, mails)
    for path in ("/journal/integrity", "/journal/export"):
        r = client.get(f"/api/invite/{tok}{path}")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "apercu_minimal", (path, r.text)
    assert client.post(f"/api/invite/{tok}/claim", headers=part["headers"]).status_code == 200
    a = _export(client, tok)
    assert any(e["qui"] == "partenaire" for e in a["entrees"])      # événements du groupement
    r = client.post("/api/rgpd/delete-account", headers=part["headers"],
                    json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/invite/{tok}")
    assert g.status_code == 200 and g.json()["apercu_minimal"] is False
    b = _export(client, tok)
    assert jm.prolonge(a, b), "l'export après effacement doit prolonger le précédent"
    assert len(b["entrees"]) > len(a["entrees"])


def test_reseau_part_repassee_en_brouillon_reste_acceptee(client, reg, mails):
    """Part soumise (réponse à l'invitation) puis modifiée (repasse en brouillon) : l'invitation
    reste acceptée — pas de retour à l'aperçu minimal, l'export suivant prolonge le précédent."""
    from app.services import journal_membre as jm
    chef, part, pid, tok = _scenario_brouillon_et_invitation_reseau(client, reg, mails)
    _put_part(client, tok, company_name="Le Gall Électricité", lot="Lot 2 — Électricité", prix_lot_ht=40000)
    assert client.post(f"/api/invite/{tok}/contribution/submit").status_code == 200
    assert client.get(f"/api/invite/{tok}").json()["apercu_minimal"] is False
    a = _export(client, tok)
    _put_part(client, tok, prix_lot_ht=41000)                    # repasse en brouillon
    assert client.get(f"/api/invite/{tok}/contribution").json()["status"] == "draft"
    assert client.get(f"/api/invite/{tok}").json()["apercu_minimal"] is False
    b = _export(client, tok)
    assert jm.prolonge(a, b)


def _age_email(inv_id, minutes=16):
    from datetime import timedelta
    from app.core.database import SessionLocal
    from app.models import ProjectInvite
    db = SessionLocal()
    try:
        i = db.get(ProjectInvite, inv_id)
        i.emailed_at = i.emailed_at - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


def test_relance_reseau_refusee_apres_retrait_ou_masquage_et_plafonnee(client, reg, mails, monkeypatch):
    """La relance d'une invitation réseau refait les contrôles de l'envoi : profil toujours publié,
    paire non masquée (motif jamais dit au chef de file), et elle compte dans le plafond quotidien
    du profil. Plus d'email affirmant « votre profil est publié » à un profil retiré."""
    part = _org(client, "Le Gall Électricité")
    part_pid = _publish(client, reg, part)
    chef = _org(client, "Breizh Couverture")
    _publish(client, reg, chef, metiers=("couverture",))
    pid = _project(client, chef)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=chef["headers"],
                    json={"profile_id": part_pid, "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    iid = r.json()["invitation"]["id"]
    url = f"/api/projects/{pid}/invites/{iid}/resend"
    _age_email(iid)
    assert client.post(url, headers=chef["headers"]).json()["sent"] is True        # profil publié : OK
    # Retrait de la publication → plus de relance (et donc plus de « votre profil est publié »).
    assert client.delete("/api/reseau/profil/publier", headers=part["headers"]).status_code == 200
    _age_email(iid)
    n_mails = len(mails)
    r = client.post(url, headers=chef["headers"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "plus_sollicitable", r.text
    assert len(mails) == n_mails
    # Republication puis masquage du chef de file → refus, sans dire pourquoi.
    assert client.post("/api/reseau/profil/publier", headers=part["headers"], json={"accepte": True}).status_code == 200
    _age_email(iid)
    assert client.post(url, headers=chef["headers"]).status_code == 200
    assert client.put("/api/reseau/profil", headers=part["headers"],
                      json={"hidden_from_sirens": [chef["siren"]]}).status_code == 200
    _age_email(iid)
    r = client.post(url, headers=chef["headers"])
    assert r.status_code == 409 and "masqu" not in r.text
    # Démasqué : les relances comptent dans le plafond quotidien du profil (1 envoi + 2 relances).
    assert client.put("/api/reseau/profil", headers=part["headers"], json={"hidden_from_sirens": []}).status_code == 200
    import app.routers.reseau as R
    monkeypatch.setattr(R, "NETWORK_INVITES_PER_PROFILE_DAY", 3)
    _age_email(iid)
    assert client.post(url, headers=chef["headers"]).status_code == 429


def test_marquer_depose_recalcule_le_compteur_du_reseau(client, reg, mails):
    """Complément A14 : le badge « N groupements déposés via Adjugo » (COUNT réel) des profils du
    chef de file et du partenaire suit le marquage « déposé » et son annulation tout de suite,
    sans attendre le passage du cron."""
    part = _org(client, "Le Gall Électricité")
    part_pid = _publish(client, reg, part)
    chef = _org(client, "Breizh Couverture")
    _publish(client, reg, chef, metiers=("couverture",))
    pid = _project(client, chef)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=chef["headers"],
                    json={"profile_id": part_pid, "role": "cotraitant", "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    recues = client.get("/api/reseau/invitations", headers=part["headers"]).json()["invitations"]
    tok = next(x["token"] for x in recues if x["mandataire"] == chef["name"])
    assert client.post(f"/api/invite/{tok}/claim", headers=part["headers"]).status_code == 200
    _put_part(client, tok, company_name="Le Gall Électricité", lot="Lot 2 — Électricité", prix_lot_ht=40000)
    assert client.post(f"/api/invite/{tok}/contribution/submit").status_code == 200
    assert (_profile_row(part["id"]).groupements_deposes or 0) == 0
    assert (_profile_row(chef["id"]).groupements_deposes or 0) == 0
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=chef["headers"], json={"confirmer": True})
    assert r.status_code == 200 and r.json()["status"] == "envoye", r.text
    assert _profile_row(part["id"]).groupements_deposes == 1
    assert _profile_row(chef["id"]).groupements_deposes == 1
    assert _profile_row(part["id"]).last_groupement_at is not None
    r = client.delete(f"/api/projects/{pid}/groupement/deposer", headers=chef["headers"])
    assert r.status_code == 200 and r.json()["etait_depose"] is True
    assert _profile_row(part["id"]).groupements_deposes == 0
    assert _profile_row(chef["id"]).groupements_deposes == 0


def test_part_d_une_invitation_reseau_sans_reponse_invisible_du_chef_de_file(client, reg, mails):
    """Le brouillon saisi par un partenaire du réseau pendant l'aperçu minimal (contact, prix,
    note) n'est pas montré au chef de file — ni avant sa réponse, ni après un refus. Même seuil
    que l'adresse : accepté depuis le compte, adresse prouvée ou part soumise."""
    chef, part, pid, tok = _scenario_brouillon_et_invitation_reseau(client, reg, mails)
    h = chef["headers"]
    _put_part(client, tok, company_name="Le Gall Électricité", lot="Lot 2 — Électricité", prix_lot_ht=41234,
              note_au_mandataire="Note confidentielle Le Gall",
              contact={"nom": "Jean Prudent", "email": "jean.prudent@prudent-elec.fr", "telephone": "06 12 34 56 78"})
    secrets_part = ("jean.prudent@prudent-elec.fr", "06 12 34 56 78", "Jean Prudent", "41234", "41 234",
                    "Note confidentielle Le Gall")

    def owner_views():
        out = []
        for path in ("contributions", "consortium", "invites"):
            r = client.get(f"/api/projects/{pid}/{path}", headers=h)
            assert r.status_code == 200, (path, r.text)
            out.append((path, r.text))
        return out
    for path, text in owner_views():
        assert not [s for s in secrets_part if s in text], path
    # Aucune entrée « le mandataire a consulté votre part » pour une part qu'il n'a pas vue.
    assert not any(e["action"] == "owner.view_contribution"
                   for e in client.get(f"/api/invite/{tok}/journal").json()["entries"])
    # Refus : toujours rien.
    assert client.post(f"/api/invite/{tok}/decline", json={}).status_code == 200
    for path, text in owner_views():
        assert not [s for s in secrets_part if s in text], path


def test_part_d_une_invitation_reseau_acceptee_visible_du_chef_de_file(client, reg, mails):
    chef, part, pid, tok = _scenario_brouillon_et_invitation_reseau(client, reg, mails)
    _put_part(client, tok, company_name="Le Gall Électricité", lot="Lot 2 — Électricité", prix_lot_ht=41234,
              contact={"nom": "Jean Prudent", "email": "jean.prudent@prudent-elec.fr"})
    assert client.post(f"/api/invite/{tok}/claim", headers=part["headers"]).status_code == 200
    rows = client.get(f"/api/projects/{pid}/contributions", headers=chef["headers"]).json()
    mine = [c for c in rows if c["company_name"] == "Le Gall Électricité"]
    assert mine and mine[0]["contact"]["email"] == "jean.prudent@prudent-elec.fr" and mine[0]["prix_lot_ht"] == 41234
