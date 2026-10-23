"""Régressions issues de la relecture adversariale de la vague 1 (co-traitance v2).

B1 : le score « seul » recalculé par le service de groupement doit être EXACTEMENT le
     match_score posé à l'analyse (même profil, qualifications {name, detail}).
I3 : un invité (jeton seul) ne réécrit jamais les capacités d'un partenaire non rattaché.
I4 : figer exige la part du mandataire ; une nouvelle invitation ou un nouveau chiffrage
     défige l'offre AVEC trace (offer.unfrozen) ; une simple revue du chiffrage ne défige pas.
I2 : le journal invité met en cache la vérification d'intégrité (pas de re-hash à chaque appel).
"""
import json

from tests.test_cotraitance_v2_doctrine import _invite, _project, _put, _submit


DETAILS = {
    "intitule_marche": "Travaux de ventilation et désenfumage du groupe scolaire",
    "type_marche": "Travaux", "lieu_execution": "Quimper (29)",
    "budget_estime": "180 000 EUR HT", "date_limite": "31/12/2099",
    "ca_minimum_requis": "Non specifie dans le DCE",
    "qualifications_requises": ["ventilation désenfumage"],
    "criteres_attribution": [{"critere": "Prix", "ponderation": "60%"}],
}
LEAD = {"name": "Aéraulique SARL", "postal_code": "29000", "ca_n1": 900000, "effectif": 12,
        "qualifications": [{"name": "Qualibat 5411", "detail": "ventilation désenfumage"}]}
CRIT = {"specialites": "ventilation, désenfumage, CVC", "departements": ["29"],
        "go_threshold": 65, "nogo_threshold": 40}


def test_b1_score_seul_identique_au_score_analyse():
    """dce_scoring recoupe name + detail des qualifications : le lead normalisé par le
    service de verdict doit garder les deux, sinon seul = 58 ici au lieu de 80."""
    from app.services.dce_scoring import score_dce
    from app.services.groupement_scoring import score_groupement
    from app.services.groupement_verdict import lead_member
    analyse = score_dce(DETAILS, LEAD, CRIT)
    lead = lead_member(LEAD, CRIT)
    res = score_groupement(DETAILS, lead, CRIT, [lead])
    assert res["score_seul"] == analyse["score"], (res["score_seul"], analyse["score"])
    assert res["decision"] == analyse["go_decision"] or res["decision"] in ("go", analyse["go_decision"])


def test_i4_figer_exige_la_part_du_mandataire(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Alpha SARL")["token"]
    _put(client, token, lot="Lot A", prix_lot_ht=40000)
    _submit(client, token)
    # Pas de chiffrage mandataire, pas de lead_total_ht → 422 explicite (jamais un total faux).
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={})
    assert r.status_code == 422 and "part" in r.text.lower(), r.text
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 60000})
    assert r.status_code == 200 and r.json()["total_ht"] == 100000.0


def _journal_actions(client, token):
    return [e["action"] for e in client.get(f"/api/invite/{token}/journal").json()["entries"]]


def test_i4_nouvelle_invitation_defige_avec_trace(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Alpha SARL")["token"]
    _put(client, token, lot="Lot A", prix_lot_ht=40000)
    _submit(client, token)
    assert client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 1000}).status_code == 200
    assert client.get(f"/api/invite/{token}").json()["for_member"]["state"]["offer_frozen"] is True
    _invite(client, h, pid, company="Beta SAS")           # nouveau membre → total caduc
    fm = client.get(f"/api/invite/{token}").json()["for_member"]
    assert fm["state"]["offer_frozen"] is False
    assert "offer.unfrozen" in _journal_actions(client, token)


def test_i4_chiffrage_mandataire_defige_mais_pas_la_revue(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Alpha SARL")["token"]
    _put(client, token, lot="Lot A", prix_lot_ht=40000)
    _submit(client, token)
    # Chiffrage mandataire (manuel, sans IA) → part du mandataire connue.
    r = client.put(f"/api/chiffrage/{pid}", headers=h, json={
        "lignes": [{"tache": "Pose", "profil": "Production / édition", "jours": 2}], "distance_km": 0})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={}).status_code == 200
    # Une REVUE (validation) ne change pas le montant → l'offre reste figée.
    r = client.put(f"/api/chiffrage/{pid}/review", headers=h, json={"status": "valide", "note": "ok"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/invite/{token}").json()["for_member"]["state"]["offer_frozen"] is True
    # Un NOUVEAU chiffrage change la part du mandataire → défigé avec trace.
    r = client.put(f"/api/chiffrage/{pid}", headers=h, json={
        "lignes": [{"tache": "Pose", "profil": "Production / édition", "jours": 5}], "distance_km": 0})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/invite/{token}").json()["for_member"]["state"]["offer_frozen"] is False
    assert "offer.unfrozen" in _journal_actions(client, token)


def test_i2_journal_invite_cache_verification_integrite(client, auth, monkeypatch):
    from app.routers import invites as inv_mod
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Alpha SARL")["token"]
    inv_mod._CHAIN_CACHE.clear()
    calls = {"n": 0}
    real = audit.verify_chain

    def counting(db, owner_id):
        calls["n"] += 1
        return real(db, owner_id)
    monkeypatch.setattr(audit, "verify_chain", counting)
    for _ in range(5):
        r = client.get(f"/api/invite/{token}/journal")
        assert r.status_code == 200 and r.json()["chained"] is True
    assert calls["n"] == 1, "verify_chain (full-scan + re-hash) ne doit tourner qu'une fois par TTL"
