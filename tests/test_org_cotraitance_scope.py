"""
Portée ORGANISATION de la co-traitance (invites / consortium).

Régression : un coéquipier voyait l'AO d'un collègue dans la liste « Mes marchés »
(portée org) mais recevait un 404 / une liste vide sur les invitations, le consortium
et les contributions (portée personnelle `owner_id == current_user.id`). On prouve ici
que toute la co-traitance d'un AO est visible par TOUS les membres de l'organisation,
tout en restant cloisonnée vis-à-vis d'une autre organisation.
"""
import uuid


def _register(client):
    email = f"team_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123",
        "full_name": "Owner", "company_name": "Mandataire SARL"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def _invite_teammate(client, owner_headers):
    """Le propriétaire ajoute un coéquipier à SON organisation, puis ce dernier se connecte."""
    email = f"mate_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=owner_headers,
                    json={"email": email, "full_name": "Coéquipier"})
    assert r.status_code == 201, r.text
    temp = r.json()["temp_password"]
    lr = client.post("/api/auth/login", json={"email": email, "password": temp})
    assert lr.status_code == 200, lr.text
    return {"Authorization": f"Bearer {lr.json()['access_token']}"}


def test_teammate_sees_colleague_cotraitance(client):
    owner, _ = _register(client)

    # Le propriétaire crée un AO et y attache une invitation co-traitant.
    pr = client.post("/api/projects/", headers=owner, json={"name": "AO Groupement", "budget": 50000})
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]

    ir = client.post(f"/api/projects/{pid}/invites", headers=owner,
                     json={"recipient": "partenaire@ext.fr", "company_name": "Partenaire SARL"})
    assert ir.status_code == 200, ir.text

    # Un coéquipier de la MÊME organisation rejoint l'équipe.
    mate = _invite_teammate(client, owner)

    # Il voit l'AO (déjà le cas avant) ET désormais ses invitations / consortium / contributions.
    assert client.get(f"/api/projects/{pid}", headers=mate).status_code == 200
    inv_list = client.get(f"/api/projects/{pid}/invites", headers=mate)
    assert inv_list.status_code == 200, inv_list.text
    assert len(inv_list.json()) == 1, "le coéquipier doit voir l'invitation créée par le collègue"
    assert inv_list.json()[0]["company_name"] == "Partenaire SARL"

    cockpit = client.get(f"/api/projects/{pid}/consortium", headers=mate)
    assert cockpit.status_code == 200, cockpit.text
    assert len(cockpit.json()["partners"]) == 1

    contribs = client.get(f"/api/projects/{pid}/contributions", headers=mate)
    assert contribs.status_code == 200, contribs.text

    # Tableau de bord des consortiums (agrégat org) : le coéquipier voit l'AO du collègue.
    cons = client.get("/api/consortiums", headers=mate)
    assert cons.status_code == 200, cons.text
    assert cons.json()["active"] >= 1
    assert any(c["project_id"] == pid for c in cons.json()["consortiums"])

    # Le coéquipier peut révoquer l'invitation (action d'écriture, périmètre org).
    inv_id = inv_list.json()[0]["id"]
    rev = client.delete(f"/api/projects/{pid}/invites/{inv_id}", headers=mate)
    assert rev.status_code == 200, rev.text


def test_other_org_stays_isolated(client):
    owner, _ = _register(client)
    pr = client.post("/api/projects/", headers=owner, json={"name": "AO Privé", "budget": 10000})
    pid = pr.json()["id"]
    client.post(f"/api/projects/{pid}/invites", headers=owner,
                json={"recipient": "p@ext.fr", "company_name": "P SARL"})

    # Un utilisateur d'une AUTRE organisation ne voit rien de cet AO : cloisonnement intact.
    outsider, _ = _register(client)
    assert client.get(f"/api/projects/{pid}", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/invites", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/consortium", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/contributions", headers=outsider).status_code == 404

    # Son tableau de bord consortiums est vide (il ne capte pas l'AO du voisin).
    cons = client.get("/api/consortiums", headers=outsider)
    assert cons.status_code == 200
    assert all(c["project_id"] != pid for c in cons.json()["consortiums"])
