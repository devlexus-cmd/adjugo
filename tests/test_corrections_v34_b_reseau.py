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

from tests.test_reseau_partenaires import _org, _project, _publish, reg  # noqa: F401  (fixture autouse)


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
