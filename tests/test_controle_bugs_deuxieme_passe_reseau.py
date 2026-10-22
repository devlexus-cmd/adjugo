"""Contrôle des bugs d'octobre 2026, deuxième passe, invitations du réseau Adjugo (registre simulé, fixture `reg` de
tests/test_reseau_partenaires.py) : chaque test échouait sur f31ebef, chacun sur son défaut. Numéros du bilan
(docs/REORGANISATION_V2A.md, section R).

12. Tant qu'une invitation du réseau n'a pas de réponse (aperçu limité), ou après un refus, rien de son brouillon
    n'arrive chez le chef de file : ni capacités ni qualifications dans « Mes partenaires », ni notification de pièce
    déposée ou de capacités mises à jour. Une fois l'invitation acceptée, le comportement d'avant revient.
13. Seul le compte destinataire décline une invitation du réseau : un collègue de son organisation reçoit un refus en
    clair et l'invitation ne change pas, avant comme après l'acceptation.
"""
import uuid

from tests.test_reseau_partenaires import _org, _publish, reg  # noqa: F401
from tests.test_reseau_partenaires import _project as _projet_reseau


def _collegue(client, org):
    email = f"col_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=org["headers"], json={"email": email, "full_name": "Collègue"})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": r.json()["temp_password"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _invitation(client, reg, b, chef):  # noqa: F811
    a = _org(client, chef)
    _publish(client, reg, a, metiers=("couverture",))
    pid = _projet_reseau(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b["profile_id"], "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    return a, pid, r.json()


def _jeton(client, headers, chef):
    return next(x for x in client.get("/api/reseau/invitations", headers=headers).json()["invitations"]
                if x["mandataire"] == chef)


def _fuites(client, a, ct_id, pid):
    fiche = next(c for c in client.get("/api/cotraitants/", headers=a["headers"]).json() if c["id"] == ct_id)
    fuites = {k: fiche.get(k) for k in ("ca_n1", "effectif", "qualifications")
              if (k == "qualifications" and "Brouillon" in (fiche.get(k) or "")) or (k != "qualifications" and fiche.get(k))}
    notifs = [(n["action"], n["detail"]) for n in client.get("/api/notifications", headers=a["headers"]).json()
              if n["project_id"] == pid and n["action"] in ("guest.upload_piece", "guest.capacites_updated")]
    return fuites, notifs


def test_12_reseau_sans_reponse_brouillon_hors_de_mes_partenaires_et_des_notifications(client, reg):  # noqa: F811
    b = _org(client, "Partenaire Prudent")
    b["profile_id"] = _publish(client, reg, b)
    a, pid, inv = _invitation(client, reg, b, "Chef De File Curieux")
    ct_id = inv["annuaire"]["cotraitant_id"]
    token = _jeton(client, b["headers"], a["name"])["token"]
    assert client.get(f"/api/invite/{token}").json()["apercu_minimal"] is True
    v = client.get(f"/api/invite/{token}/contribution").json()["version"]
    r = client.put(f"/api/invite/{token}/contribution", json={
        "version": v, "capacites": {"ca_n1": 1234567, "effectif": 17}, "qualifications": ["Qualifelec E3 Brouillon"]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/invite/{token}/contribution/piece",
                    files={"file": ("Kbis_Partenaire_Prudent_confidentiel.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200, r.text
    assert _fuites(client, a, ct_id, pid) == ({}, [])
    # Acceptée depuis son compte : ses capacités déclarées rejoignent la fiche, ses notifications réapparaissent.
    assert client.post(f"/api/invite/{token}/claim", headers=b["headers"]).status_code == 200
    fuites, notifs = _fuites(client, a, ct_id, pid)
    assert fuites == {"ca_n1": 1234567.0, "effectif": 17, "qualifications": "Qualifelec E3 Brouillon"}, fuites
    assert ("guest.upload_piece", "Kbis_Partenaire_Prudent_confidentiel.pdf") in notifs, notifs


def test_12_reseau_decline_rien_du_brouillon_ne_reste_chez_le_chef_de_file(client, reg):  # noqa: F811
    b = _org(client, "Partenaire Qui Refuse")
    b["profile_id"] = _publish(client, reg, b)
    a, pid, inv = _invitation(client, reg, b, "Chef De File Refuse")
    ct_id = inv["annuaire"]["cotraitant_id"]
    token = _jeton(client, b["headers"], a["name"])["token"]
    v = client.get(f"/api/invite/{token}/contribution").json()["version"]
    assert client.put(f"/api/invite/{token}/contribution", json={
        "version": v, "capacites": {"ca_n1": 7654321, "effectif": 9},
        "qualifications": ["Qualibat Brouillon"]}).status_code == 200
    assert client.post(f"/api/invite/{token}/decline", headers=b["headers"]).status_code == 200
    assert _fuites(client, a, ct_id, pid) == ({}, [])


def test_13_un_collegue_ne_decline_pas_l_invitation_du_reseau(client, reg):  # noqa: F811
    b = _org(client, "Partenaire Avec Equipe")
    b["profile_id"] = _publish(client, reg, b)
    hc = _collegue(client, b)
    a, pid, inv = _invitation(client, reg, b, "Chef De File Equipe")
    inv_id = inv["invitation"]["id"]
    x = _jeton(client, hc, a["name"])
    assert x["peut_accepter"] is False and "décliner" in x["aide"], x
    r = client.post(f"/api/invite/{x['token']}/decline", headers=hc)
    assert r.status_code == 403, r.text
    assert "Seul le compte propriétaire de votre organisation" in r.text
    etat = lambda: next(i for i in client.get(f"/api/projects/{pid}/invites", headers=a["headers"]).json()  # noqa: E731
                        if i["id"] == inv_id)["state"]
    assert etat() != "declined"
    # Sans session, avec l'envoi de codes en service : l'adresse doit être prouvée par code, comme pour soumettre.
    import app.services.email as E
    from unittest import mock
    with mock.patch.object(E, "is_enabled", lambda: True):
        r = client.post(f"/api/invite/{x['token']}/decline")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified", r.text
    assert etat() != "declined"
    # Le compte destinataire, lui, décline.
    assert client.post(f"/api/invite/{x['token']}/decline", headers=b["headers"]).status_code == 200
    assert etat() == "declined"


def test_13_apres_l_acceptation_un_collegue_ne_decline_pas_non_plus(client, reg):  # noqa: F811
    b = _org(client, "Partenaire Accepte Equipe")
    b["profile_id"] = _publish(client, reg, b)
    hc = _collegue(client, b)
    a, pid, inv = _invitation(client, reg, b, "Chef De File Equipe Deux")
    inv_id = inv["invitation"]["id"]
    tok = _jeton(client, b["headers"], a["name"])["token"]
    assert client.post(f"/api/invite/{tok}/claim", headers=b["headers"]).status_code == 200
    x = _jeton(client, hc, a["name"])
    assert x["statut"] == "acceptee"
    r = client.post(f"/api/invite/{x['token']}/decline", headers=hc)
    assert r.status_code == 403, r.text
    me = next(i for i in client.get(f"/api/projects/{pid}/invites", headers=a["headers"]).json() if i["id"] == inv_id)
    assert me["state"] != "declined"
