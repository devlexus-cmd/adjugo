"""Correctif de production (revue approfondie des vagues 3+4, défauts présents dès la vague 2).

  • PDF de la convention : refusé à un non-signataire (sous-traitant) — il y lisait le prix de
    chaque lot et le total, alors que la vue JSON les lui masquait ;
  • vue membre : le total de l'offre n'est montré qu'aux membres signataires (jamais à un
    sous-traitant) ;
  • journal chaîné : une fourche HISTORIQUE (deux écritures simultanées, avant le verrou de
    chaîne) n'est plus un faux « altéré » ; une vraie altération reste détectée ;
  • garde des crons : un en-tête non ASCII donne 403, pas une erreur 500.
"""
import uuid

import pytest

from tests.test_convention_groupement import _gen, _groupement, _part, _valider   # noqa: F401


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda mails: sent.extend(mails))
    return sent


def _sous_traitant(client, h, pid):
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"company_name": "Échafaudages Sous-Traitant", "role": "sous_traitant"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_pdf_convention_refuse_au_non_signataire(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    st = _sous_traitant(client, h, pid)
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer"
    r = client.get(f"/api/invite/{st}/convention/pdf")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pas_signataire"
    assert b"40 000" not in r.content and b"100 000" not in r.content
    # Un membre signataire obtient bien le PDF.
    ok = client.get(f"/api/invite/{invs[0]['token']}/convention/pdf")
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("application/pdf")


def test_total_jamais_montre_au_sous_traitant(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    st = _sous_traitant(client, h, pid)
    c = _gen(client, h, pid).json()
    total = c["total_offre_ht"]
    v = client.get(f"/api/invite/{st}").json()
    assert (v.get("for_member") or {}).get("state", {}).get("total_offre_ht") is None
    m = client.get(f"/api/invite/{invs[0]['token']}").json()
    assert m["for_member"]["state"]["total_offre_ht"] == total


def test_fourche_historique_toleree_alteration_detectee(client):
    from app.core.database import SessionLocal
    from app.models import AuditLog
    from app.services import audit
    oid = 970000 + uuid.uuid4().int % 9000
    db = SessionLocal()
    try:
        for i in range(5):
            audit.record(db, action=f"e{i}", owner_id=oid, actor="x")
        rows = db.query(AuditLog).filter(AuditLog.owner_id == oid).order_by(AuditLog.id).all()
        # Fourche telle qu'en produisaient deux écritures simultanées : l'entrée 4 pointe vers la
        # 2 (et non la 3), avec une empreinte cohérente avec ce maillon.
        e4 = rows[3]
        e4.prev_hash = rows[1].entry_hash
        e4.entry_hash = audit._hash(e4.prev_hash, e4)
        rows[4].prev_hash = e4.entry_hash
        rows[4].entry_hash = audit._hash(rows[4].prev_hash, rows[4])
        db.commit()
        v = audit.verify_chain(db, oid)
        assert v["intact"] is True and v["forks"] == 1
        # Une vraie altération (contenu modifié) reste détectée.
        rows[2].detail = "falsifié"
        db.commit()
        v = audit.verify_chain(db, oid)
        assert v["intact"] is False and v["broken_at_id"] == rows[2].id
        rows[2].detail = ""
        db.commit()
        # Une entrée supprimée au milieu de la chaîne reste détectée.
        db.delete(rows[1])
        db.commit()
        v = audit.verify_chain(db, oid)
        assert v["intact"] is False
    finally:
        db.close()


def test_cron_en_tete_non_ascii_refuse_proprement(client, monkeypatch):
    import app.routers.admin as admin
    monkeypatch.setattr(admin.settings, "CRON_SECRET", "secret-cron-test")
    r = client.post("/api/admin/run-trash-purge", headers={"X-Cron-Secret": "sécret".encode("utf-8")})
    assert r.status_code == 403
    assert client.post("/api/admin/run-trash-purge", headers={"X-Cron-Secret": "faux"}).status_code == 403
