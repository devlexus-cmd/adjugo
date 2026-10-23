"""Non-régression — audit cyber oct. 2026, 2e lot, groupe « données ».

Rejoue les contournements trouvés après le 1er lot et vérifie qu'ils échouent désormais :
  • B1/B3 : l'effacement RGPD d'un membre réécrivait AuditLog.owner_id (haché) → fausse
            alerte de falsification sur la chaîne de l'entreprise ;
  • B2    : un ex-fondateur (propriété transférée puis retiré) effaçait le journal et les
            simulations de l'entreprise en supprimant son compte ;
  • transfert de propriété : simulations déplacées + /api/audit/integrity couvre les
            chaînes héritées (anciens propriétaires) ;
  • alerts piece.expiring chaîné sous le propriétaire du tenant (pas le membre créateur) ;
  • corbeille : les anciennes versions suivent le document (et reviennent avec lui) ;
  • démo : aucune invitation / aucun email même si le garde central est contourné ;
  • lien de confirmation à l'ancien format sur un compte déjà confirmé → 200 ;
  • plafond de 30 invitations par organisation et par 24 h.
"""
import io
import uuid
from datetime import date, timedelta

import pytest

PDF = b"%PDF-1.4\n% test donnees\n%%EOF"


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _tok(uid):
    from app.core.security import create_access_token
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        return create_access_token(data={"sub": str(uid), "tv": int(u.token_version or 0)})
    finally:
        db.close()


def _register(client, prefix="don"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123",
        "full_name": prefix, "company_name": prefix + " SARL"})
    assert r.status_code == 201, r.text
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        return u.id
    finally:
        db.close()


def _member(client, owner_id, prefix="sal"):
    from app.core.security import hash_password
    from app.models import User
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=_h(_tok(owner_id)), json={"email": email, "full_name": prefix})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        u.hashed_password = hash_password("motdepasse123")
        db.commit()
        return u.id
    finally:
        db.close()


def _delete(client, uid):
    return client.post("/api/rgpd/delete-account", headers=_h(_tok(uid)),
                       json={"password": "motdepasse123", "confirm": "SUPPRIMER"})


def _chain(uid):
    from app.services import audit
    db = _db()
    try:
        return audit.verify_chain(db, uid)
    finally:
        db.close()


def _count(model_attr, value, **extra):
    db = _db()
    try:
        q = db.query(model_attr.class_).filter(model_attr == value)
        for k, v in extra.items():
            q = q.filter(getattr(model_attr.class_, k) == v)
        return q.count()
    finally:
        db.close()


def _record(**kw):
    from app.services import audit
    db = _db()
    try:
        audit.record(db, **kw)
    finally:
        db.close()


# Clés étrangères appliquées comme en production : fixture « fk_on » de tests/conftest.py (SQLite : PRAGMA ;
# PostgreSQL : contraintes réelles des migrations ; sur les deux, une ligne orpheline vérifiée refusée).


def _founder_with_history(client, tag):
    """Fondateur F : 1 marché, 1 simulation enregistrée, journal chaîné ; transfert à R."""
    F = _register(client, f"fond{tag}")
    R = _member(client, F, f"rep{tag}")
    p = client.post("/api/projects/", headers=_h(_tok(F)), json={"name": "AO Ecole", "client": "Ville"}).json()
    r = client.post(f"/api/projects/{p['id']}/groupement/simulate", headers=_h(_tok(F)),
                    json={"members": [{"kind": "saisi", "name": "Z", "ca_n1": 500000, "effectif": 5}],
                          "save": True})
    assert r.status_code == 200, r.text
    for _ in range(3):
        _record(action="offer.frozen", owner_id=F, project_id=p["id"], actor="fondateur", actor_kind="owner")
    assert _chain(F)["intact"] is True
    r = client.post("/api/org/transfer-ownership", headers=_h(_tok(F)), json={"new_owner_id": R})
    assert r.status_code == 200, r.text
    return F, R, p["id"]


# ─── (3) Transfert : simulations suivies + intégrité des chaînes héritées ────────────────

def test_transfert_deplace_les_simulations_et_integrite_couvre_l_historique(client):
    from app.models import GroupementSimulation
    F, R, P = _founder_with_history(client, "t")
    db = _db()
    try:
        sims = db.query(GroupementSimulation).filter(GroupementSimulation.project_id == P).all()
        assert sims and {s.owner_id for s in sims} == {R}
    finally:
        db.close()
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is True and integ["owner_id"] == R
    owners = [c["owner_id"] for c in integ["chains"]]
    assert owners[0] == R and F in owners            # l'historique d'avant transfert est vérifié
    assert integ["entries"] >= 3 + 1


def test_integrite_detecte_une_falsification_dans_une_chaine_heritee(client):
    from app.models import AuditLog
    F, R, P = _founder_with_history(client, "f")
    db = _db()
    try:
        e = db.query(AuditLog).filter(AuditLog.owner_id == F, AuditLog.action == "offer.frozen").first()
        e.detail = "falsifié"
        db.commit()
    finally:
        db.close()
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is False


# ─── (1) B1 : ex-fondateur resté membre → effacement sans casser la chaîne ──────────────

def test_b1_effacement_ex_fondateur_membre_ne_casse_pas_la_chaine(client, fk_on):
    from app.models import AuditLog, User
    F, R, P = _founder_with_history(client, "1")
    before = _count(AuditLog.owner_id, F)
    old_session = _tok(F)
    r = _delete(client, F)
    assert r.status_code == 200, r.text
    # Rien n'a été réécrit : la chaîne du nouveau propriétaire et l'historique restent intacts.
    assert _chain(R)["intact"] is True
    assert _chain(F)["intact"] is True and _count(AuditLog.owner_id, F) == before
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is True and F in [c["owner_id"] for c in integ["chains"]]
    # La personne est effacée : ligne anonymisée (plus aucune donnée personnelle).
    db = _db()
    try:
        u = db.get(User, F)
        assert u.email == f"deleted-{F}@invalid" and u.full_name == "" and u.is_active is False
        assert u.org_id is None
    finally:
        db.close()
    # Sessions coupées (token_version incrémenté).
    assert client.get("/api/auth/me", headers=_h(old_session)).status_code in (401, 403)


# ─── (2) B2 : ex-fondateur retiré puis effacé → journal et simulations de l'entreprise gardés

def test_b2_ex_fondateur_retire_n_efface_pas_le_journal_de_l_entreprise(client, fk_on):
    from app.models import AuditLog, GroupementSimulation, Project
    F, R, P = _founder_with_history(client, "2")
    assert client.delete(f"/api/org/members/{F}", headers=_h(_tok(R))).status_code == 200
    journal = _count(AuditLog.owner_id, F)
    sims = _count(GroupementSimulation.project_id, P)
    assert journal >= 3 and sims >= 1
    r = _delete(client, F)
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert db.get(Project, P).user_id == R
    finally:
        db.close()
    assert _count(AuditLog.owner_id, F) == journal          # 5 -> 0 avant le correctif
    assert _count(GroupementSimulation.project_id, P) == sims
    assert _count(AuditLog.project_id, P) >= 3
    integ = client.get("/api/audit/integrity", headers=_h(_tok(R))).json()
    assert integ["intact"] is True and F in [c["owner_id"] for c in integ["chains"]]


def test_b2_simulation_heritee_rattachee_au_proprietaire_du_marche(client, fk_on):
    """Donnée ancienne : simulation restée au nom de l'ex-fondateur (avant le correctif du
    transfert) → rattachée au propriétaire actuel, jamais effacée."""
    from app.models import GroupementSimulation
    F, R, P = _founder_with_history(client, "2b")
    db = _db()
    try:
        db.query(GroupementSimulation).filter(GroupementSimulation.project_id == P).update(
            {GroupementSimulation.owner_id: F})
        db.commit()
    finally:
        db.close()
    assert client.delete(f"/api/org/members/{F}", headers=_h(_tok(R))).status_code == 200
    assert _delete(client, F).status_code == 200
    db = _db()
    try:
        sims = db.query(GroupementSimulation).filter(GroupementSimulation.project_id == P).all()
        assert sims and {s.owner_id for s in sims} == {R}
    finally:
        db.close()


def test_effacement_solo_pur_supprime_toujours_la_ligne(client, fk_on):
    from app.models import AuditLog, User
    uid = _register(client, "solo")
    pid = client.post("/api/projects/", headers=_h(_tok(uid)), json={"name": "AO perso"}).json()["id"]
    _record(action="offer.frozen", owner_id=uid, project_id=pid, actor="x", actor_kind="owner")
    _record(action="team.role_changed", owner_id=uid, actor="x", actor_kind="owner")
    assert _delete(client, uid).status_code == 200
    db = _db()
    try:
        assert db.get(User, uid) is None
    finally:
        db.close()
    assert _count(AuditLog.owner_id, uid) == 0


# ─── B3 : membre dont le marché porte une entrée chaînée à son nom ──────────────────────

def test_b3_effacement_membre_garde_la_chaine_de_l_entreprise(client, fk_on):
    from app.models import AuditLog
    O = _register(client, "patron3")
    Mm = _member(client, O, "sal3")
    pm = client.post("/api/projects/", headers=_h(_tok(Mm)), json={"name": "AO M", "client": "X"}).json()["id"]
    _record(action="invite.created", owner_id=O, project_id=pm, actor="x")
    _record(action="piece.expiring", owner_id=Mm, project_id=pm, actor="system")
    _record(action="invite.resent", owner_id=O, project_id=pm, actor="x")
    assert _chain(O)["intact"] is True
    assert _delete(client, Mm).status_code == 200
    assert _chain(O)["intact"] is True                      # broken_at_id avant le correctif
    assert _count(AuditLog.owner_id, Mm) == 1
    integ = client.get("/api/audit/integrity", headers=_h(_tok(O))).json()
    assert integ["intact"] is True and Mm in [c["owner_id"] for c in integ["chains"]]


# ─── (4) alerts : piece.expiring sous le propriétaire du tenant ─────────────────────────

def test_piece_expiring_chaine_sous_le_proprietaire_du_tenant(client, monkeypatch):
    from app.models import AuditLog, Project, ProjectInvite
    import app.routers.invites as inv_mod
    import app.services.alerts as al
    O = _register(client, "patron4")
    Mm = _member(client, O, "sal4")
    pid = client.post("/api/projects/", headers=_h(_tok(Mm)), json={"name": "AO alerte"}).json()["id"]
    db = _db()
    try:
        p = db.get(Project, pid)
        p.deadline = date.today() + timedelta(days=3)
        inv = ProjectInvite(project_id=pid, owner_id=O, token=uuid.uuid4().hex,
                            recipient="partenaire@test.fr", company_name="Partenaire")
        db.add(inv)
        db.commit()
        inv_id = inv.id
    finally:
        db.close()
    monkeypatch.setattr(inv_mod, "coffre_croise", lambda *a, **k: {
        "members": [{"invite_id": inv_id, "company": "Partenaire",
                     "pieces": {"kbis": {"status": "manquant"}}}]})
    monkeypatch.setattr(al, "send_email", lambda *a, **k: True)
    db = _db()
    try:
        assert al._run_piece_expiry_alerts(db, date.today()) >= 1
        e = db.query(AuditLog).filter(AuditLog.invite_id == inv_id,
                                      AuditLog.action == "piece.expiring").first()
        assert e is not None and e.owner_id == O            # était project.user_id (= membre)
    finally:
        db.close()
    assert _chain(O)["intact"] is True


# ─── (5) Corbeille : anciennes versions incluses ────────────────────────────────────────

def test_corbeille_propage_aux_anciennes_versions(client, auth):
    from app.models import Document
    h = auth["headers"]
    up = client.post("/api/documents/", headers=h,
                     files={"file": ("kbis.pdf", io.BytesIO(PDF), "application/pdf")},
                     data={"name": "Kbis", "category": "administratif"})
    assert up.status_code == 201, up.text
    v1 = up.json()["id"]
    v2 = client.put(f"/api/documents/{v1}/replace", headers=h,
                    files={"file": ("kbis2.pdf", io.BytesIO(PDF), "application/pdf")}).json()["id"]
    v3 = client.put(f"/api/documents/{v2}/replace", headers=h,
                    files={"file": ("kbis3.pdf", io.BytesIO(PDF), "application/pdf")}).json()["id"]
    assert client.delete(f"/api/documents/{v3}", headers=h).status_code == 204
    db = _db()
    try:
        assert all(db.get(Document, i).deleted_at is not None for i in (v1, v2, v3))
    finally:
        db.close()
    assert client.post(f"/api/documents/{v3}/restore", headers=h).status_code == 200
    db = _db()
    try:
        assert all(db.get(Document, i).deleted_at is None for i in (v1, v2, v3))
    finally:
        db.close()


# ─── (6) Démo : jamais d'email, même si le garde central est contourné ──────────────────

@pytest.fixture
def demo(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


@pytest.fixture
def mails(monkeypatch):
    sent = []

    def fake(to, *a, **k):
        sent.append(to)
        return True
    import app.services.email as em
    monkeypatch.setattr(em, "send_email", fake)
    monkeypatch.setattr(em, "is_enabled", lambda: True)
    return sent


@pytest.fixture
def guard_off(monkeypatch):
    """Simule un trou dans le garde central (ex. en-tête Host forgé)."""
    import app.core.demo_guard as g
    monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)


def _demo_403(r, what="inviter un"):
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d.startswith("La démo est en lecture guidée : commencez votre essai gratuit de 30 jours pour ") and what in d, d


def test_demo_invitations_refusees_en_profondeur(client, demo, mails, guard_off):
    pid = client.get("/api/projects/", headers=demo).json()[0]["id"]
    _demo_403(client.post(f"/api/projects/{pid}/invites", headers=demo,
                          json={"recipient": "victime@tiers.example", "company_name": "Votre banque"}))
    _demo_403(client.post(f"/api/projects/{pid}/invites/1/resend", headers=demo))
    _demo_403(client.post("/api/org/invite", headers=demo, json={"email": "victime@tiers.example"}))
    assert mails == []


def _demo_invite_token():
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        p = db.query(Project).filter(Project.user_id == u.id).first()
        inv = ProjectInvite(project_id=p.id, owner_id=u.id, token=uuid.uuid4().hex,
                            recipient="victime@tiers.example", company_name="Vitrine")
        db.add(inv)
        db.commit()
        return inv.token
    finally:
        db.close()


def test_demo_liens_invites_n_envoient_aucun_email(client, demo, mails):
    tok = _demo_invite_token()
    assert client.get(f"/api/invite/{tok}").status_code == 200          # vitrine consultable
    st = client.get(f"/api/invite/{tok}/otp/status").json()
    assert st["required"] is False
    r = client.post(f"/api/invite/{tok}/otp/request")
    assert r.status_code == 200 and r.json()["sent"] is False
    r = client.post(f"/api/invite/{tok}/contribution/submit")
    assert r.status_code == 200, r.text
    r = client.post(f"/api/invite/{tok}/contribution/piece",
                    files={"file": ("kbis.pdf", io.BytesIO(PDF), "application/pdf")})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    r = client.post(f"/api/invite/{tok}/decline")
    assert r.status_code == 403
    assert mails == []


def test_lien_invite_normal_garde_l_otp(client, auth, mails):
    """Non-régression : hors démo, la vérification par code reste exigée et envoyée."""
    pid = client.post("/api/projects/", headers=auth["headers"], json={"name": "AO otp"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/invites", headers=auth["headers"],
                    json={"recipient": "partenaire@test.fr", "company_name": "P"})
    assert r.status_code == 200, r.text
    tok = r.json()["path"].rstrip("/").split("/")[-1]
    assert client.get(f"/api/invite/{tok}/otp/status").json()["required"] is True
    assert client.post(f"/api/invite/{tok}/otp/request").json()["sent"] is True
    assert "partenaire@test.fr" in mails


def test_demo_mot_de_passe_oublie_n_envoie_rien(client, demo, mails):
    from app.models import User
    from app.services.demo_seed import DEMO_EMAIL
    r = client.post("/api/auth/forgot-password", json={"email": DEMO_EMAIL})
    other = client.post("/api/auth/forgot-password", json={"email": "inconnu@nulle-part.fr"})
    assert r.status_code == 200 and r.json() == other.json()       # aucune information révélée
    assert mails == []
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        assert not u.reset_token_hash
    finally:
        db.close()


# ─── (7) Lien de confirmation à l'ancien format ─────────────────────────────────────────

def test_lien_ancien_format_sur_compte_deja_confirme(client):
    from app.core.security import create_access_token
    from app.models import User
    uid = _register(client, "verif")
    old = create_access_token(data={"sub": str(uid), "purpose": "verify_email"},
                              expires_delta=timedelta(hours=1))
    r = client.post("/api/auth/verify-email", json={"token": old})
    assert r.status_code == 200 and r.json()["message"] == "Votre adresse est déjà confirmée."
    db = _db()
    try:
        db.get(User, uid).email_verified = False
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/verify-email", json={"token": old}).status_code == 400


# ─── (8) Plafond anti-spam des invitations ──────────────────────────────────────────────

def test_plafond_30_invitations_par_jour(client):
    O = _register(client, "spam")
    Mm = _member(client, O, "spam_sal")
    pid = client.post("/api/projects/", headers=_h(_tok(O)), json={"name": "AO spam"}).json()["id"]
    for i in range(30):
        who = O if i % 2 else Mm               # le plafond vaut pour toute l'organisation
        r = client.post(f"/api/projects/{pid}/invites", headers=_h(_tok(who)),
                        json={"recipient": f"p{i}@test.fr", "company_name": f"P{i}"})
        assert r.status_code == 200, (i, r.text)
    r = client.post(f"/api/projects/{pid}/invites", headers=_h(_tok(O)),
                    json={"recipient": "p31@test.fr", "company_name": "P31"})
    assert r.status_code == 429 and "30 invitations par jour" in r.json()["detail"]
