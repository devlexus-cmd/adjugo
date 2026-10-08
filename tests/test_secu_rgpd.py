"""Non-régression — audit cyber oct. 2026, groupe « rgpd ».

Rejoue les exploits d'origine et vérifie qu'ils échouent désormais :
  • faille 5  : suppression de compte (FK appliquées comme sous Postgres, résidus, 500 bavard)
  • faille 12 : fichiers du stockage jamais purgés (compte + corbeille du coffre-fort)
  • faille 11 : paiement à l'usage activable sans abonnement → IA illimitée non facturable
  • faille 7  : compte démo public = vitrine en lecture guidée (emails, uploads, IA, compte)
  • Swagger /docs /redoc /openapi.json coupés en production
"""
import io
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event, insert, select, text

PDF = b"%PDF-1.4\n% fichier de test RGPD\n%%EOF"
_SKIP_FILL = {"users", "organizations", "acheteurs", "acheteur_dces", "processed_stripe_events"}


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(client, prefix="rgpd"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123",
        "full_name": "Test RGPD", "company_name": "RGPD SARL"})
    assert r.status_code == 201, r.text
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        return u.id, email, r.json()["access_token"]
    finally:
        db.close()


def _delete(client, tok):
    return client.post("/api/rgpd/delete-account", headers=_h(tok),
                       json={"password": "motdepasse123", "confirm": "SUPPRIMER"})


@pytest.fixture
def fk_on():
    """Applique les clés étrangères comme PostgreSQL en production (SQLite les ignore par
    défaut : c'est pourquoi la suite ne voyait pas l'effacement RGPD échouer)."""
    from app.core.database import engine

    def _on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    event.listen(engine, "connect", _on)
    engine.dispose()
    with engine.connect() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
    yield
    event.remove(engine, "connect", _on)
    engine.dispose()


# ─── Remplissage générique : une ligne dans CHAQUE table qui dépend d'un user/projet ───

def _dummy(col):
    from sqlalchemy import types as T
    t = col.type
    if isinstance(t, T.Enum):
        return list(t.enums)[0]
    if isinstance(t, T.Boolean):
        return False
    if isinstance(t, (T.Integer,)):
        return 1
    if isinstance(t, (T.Float, T.Numeric)):
        return 1.0
    if isinstance(t, T.DateTime):
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if isinstance(t, T.Date):
        return date.today()
    if isinstance(t, T.JSON):
        return {}
    if isinstance(t, T.LargeBinary):
        return b""
    n = getattr(t, "length", None) or 32
    return ("t" + uuid.uuid4().hex)[: max(1, min(n, 33))]


def _fill(table, refs):
    """INSERT minimal : FK → refs[table cible] ; colonnes obligatoires → valeurs factices."""
    vals = {}
    for col in table.columns:
        fks = list(col.foreign_keys)
        if fks:
            target = fks[0].column.table.name
            if target == table.name:
                vals[col.name] = None
                continue
            if target in refs:
                vals[col.name] = refs[target]
                continue
            if not col.nullable:
                return None
            vals[col.name] = None
            continue
        if col.primary_key:
            continue
        if not col.nullable and col.default is None and col.server_default is None:
            vals[col.name] = _dummy(col)
    from app.core.database import engine
    try:
        with engine.begin() as conn:
            res = conn.execute(insert(table).values(**vals))
            return res.inserted_primary_key[0]
    except Exception:
        return None   # ex. ligne unique déjà créée par l'inscription (companies, critères)


def _fill_everything(uid, pid):
    """Une ligne (au moins) dans chaque table rattachée à l'utilisateur ou à son projet —
    attrape aussi toute table AJOUTÉE plus tard et oubliée par l'effacement."""
    from app.core.database import Base
    refs = {"users": uid, "projects": pid}
    filled = []
    for table in Base.metadata.sorted_tables:
        if table.name in _SKIP_FILL or not table.foreign_keys or table.name == "projects":
            continue
        new_id = _fill(table, refs)
        if new_id is not None:
            refs.setdefault(table.name, new_id)
            filled.append(table.name)
    # Ancienne version d'un document (parent_id → version courante) : chaîne auto-référente.
    docs = Base.metadata.tables["documents"]
    if "documents" in refs:
        from app.core.database import engine
        with engine.begin() as conn:
            conn.execute(insert(docs).values(user_id=uid, project_id=pid, name="v1",
                                             file_key=f"{uid}/old_{uuid.uuid4().hex}.pdf",
                                             parent_id=refs["documents"]))
    return filled


def _residues(uid, pid):
    """(table, colonne) qui référencent encore l'utilisateur ou son projet."""
    from app.core.database import Base, engine
    out = []
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                for fk in col.foreign_keys:
                    tgt = fk.column.table.name
                    val = uid if tgt == "users" else pid if tgt == "projects" else None
                    if val is None:
                        continue
                    n = conn.execute(select(text("count(*)")).select_from(table)
                                     .where(col == val)).scalar()
                    if n:
                        out.append(f"{table.name}.{col.name}={n}")
    return out


# ─── Faille 5 : effacement RGPD sous clés étrangères appliquées ──────────────────────────

def test_fk_on_rend_bien_l_ancien_ordre_detectable(client, fk_on):
    """Témoin : avec les FK appliquées, supprimer un user qui a un job échoue — le test
    ci-dessous détecterait donc tout oubli dans l'ordre d'effacement."""
    from app.core.database import SessionLocal
    from app.models import Job, User
    uid, _, _ = _register(client)
    db = SessionLocal()
    try:
        db.add(Job(user_id=uid, kind="memoire", status="done", label="x"))
        db.commit()
        db.query(User).filter(User.id == uid).update({User.org_id: None})
        with pytest.raises(Exception):
            db.query(User).filter(User.id == uid).delete()
            db.flush()
        db.rollback()
    finally:
        db.close()


def test_suppression_compte_solo_complete_sous_fk(client, fk_on):
    from app.core.database import SessionLocal
    from app.models import ProjectInvite, User, Feedback, Job
    from app.services.storage import get_storage

    uid, email, tok = _register(client)
    # Un autre mandataire B dont l'invitation a été RÉCLAMÉE par A.
    bid, _, btok = _register(client, "mandataire")
    bp = client.post("/api/projects/", headers=_h(btok), json={"name": "Marché de B"}).json()["id"]

    pid = client.post("/api/projects/", headers=_h(tok), json={"name": "Mon marché"}).json()["id"]
    # Vrais fichiers dans le stockage : un document actif + un à la corbeille.
    up1 = client.post("/api/documents/", headers=_h(tok),
                      files={"file": ("kbis.pdf", io.BytesIO(PDF), "application/pdf")},
                      data={"name": "Kbis", "category": "administratif"})
    up2 = client.post("/api/documents/", headers=_h(tok),
                      files={"file": ("urssaf.pdf", io.BytesIO(PDF), "application/pdf")},
                      data={"name": "Urssaf", "category": "administratif"})
    assert up1.status_code == 201 and up2.status_code == 201, (up1.text, up2.text)
    assert client.delete(f"/api/documents/{up2.json()['id']}", headers=_h(tok)).status_code in (200, 204)
    keys = [up1.json()["file_key"], up2.json()["file_key"]]
    st = get_storage()
    assert all(st.load(k) == PDF for k in keys)

    filled = _fill_everything(uid, pid)
    # Les tables oubliées par l'ancien effacement sont bien peuplées.
    for t in ("jobs", "feedback", "groupement_simulations", "project_cotraitants", "co_members",
              "co_spaces", "cotraitants", "matching_criteria_ext"):
        assert t in filled or t in ("matching_criteria_ext",), (t, filled)
    db = SessionLocal()
    try:
        inv_b = ProjectInvite(project_id=bp, owner_id=bid, token=uuid.uuid4().hex,
                              accepted_by_user_id=uid)
        db.add(inv_b)
        db.commit()
        inv_b_id = inv_b.id
    finally:
        db.close()

    r = _delete(client, tok)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    assert _residues(uid, pid) == []
    db = SessionLocal()
    try:
        assert db.get(User, uid) is None
        assert db.query(Feedback).filter(Feedback.email == email).count() == 0
        assert db.query(Job).filter(Job.user_id == uid).count() == 0
        # L'invitation de B survit, libérée (plus de 409 pour le prochain partenaire).
        inv = db.get(ProjectInvite, inv_b_id)
        assert inv is not None and inv.accepted_by_user_id is None
        assert db.get(User, bid) is not None
    finally:
        db.close()
    # Faille 12 : les fichiers (actif ET corbeille) ont quitté le stockage.
    for k in keys:
        with pytest.raises(Exception):
            st.load(k)
    # La session du compte supprimé ne vaut plus rien.
    assert client.get("/api/auth/me", headers=_h(tok)).status_code == 401


def test_suppression_compte_membre_sous_fk(client, fk_on):
    """Membre d'une organisation : registres d'entreprise réassignés, perso effacé, et la
    transaction passe malgré les FK (jobs, feedback, journal…)."""
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models import User, Project, Job, Feedback, AuditLog

    oid, _, otok = _register(client, "owner")
    member_email = f"membre_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=_h(otok), json={"email": member_email})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        m = db.query(User).filter(User.email == member_email).first()
        m.hashed_password = hash_password("motdepasse123")
        m.email_verified = True
        db.commit()
        mid = m.id
    finally:
        db.close()
    mtok = client.post("/api/auth/login", json={"email": member_email,
                                                "password": "motdepasse123"}).json()["access_token"]
    pid = client.post("/api/projects/", headers=_h(mtok), json={"name": "AO du membre"}).json()["id"]
    assert client.post("/api/feedback", headers=_h(mtok),
                       json={"message": "retour perso du membre", "kind": "idee"}).status_code in (200, 201)
    db = SessionLocal()
    try:
        db.add(Job(user_id=mid, kind="memoire", status="done", label="Mémoire"))
        db.add(AuditLog(owner_id=mid, project_id=pid, action="test.member"))
        db.commit()
    finally:
        db.close()

    r = _delete(client, mtok)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.get(User, mid) is None
        assert db.get(Project, pid).user_id == oid               # le dossier reste à l'entreprise
        assert db.query(Job).filter(Job.user_id == oid, Job.label == "Mémoire").count() >= 1
        assert db.query(Feedback).filter(Feedback.user_id == mid).count() == 0
        assert db.query(AuditLog).filter(AuditLog.owner_id == mid).count() == 0
    finally:
        db.close()
    assert _residues(mid, -1) == []


def test_erreur_de_suppression_generique_sans_sql(client, monkeypatch):
    """Rejoue la fuite : l'échec renvoyait « (sqlite3.IntegrityError) … [SQL: DELETE …] »."""
    from app.routers import rgpd
    from app.core.database import SessionLocal
    from app.models import User
    uid, _, tok = _register(client)

    def boom(*a, **k):
        raise RuntimeError("(sqlite3.IntegrityError) FOREIGN KEY constraint failed "
                           "[SQL: DELETE FROM users WHERE users.id = ?] [parameters: (2,)]")

    monkeypatch.setattr(rgpd, "_erase_solo", boom)
    r = _delete(client, tok)
    assert r.status_code == 500
    body = r.text
    assert "SQL" not in body and "sqlite" not in body.lower() and "users" not in body
    assert r.json()["detail"] == rgpd._DELETE_FAILED
    db = SessionLocal()
    try:
        assert db.get(User, uid) is not None                    # rollback : rien d'effacé
    finally:
        db.close()


# ─── Faille 12 : purge de la corbeille du coffre-fort ────────────────────────────────────

def test_purge_corbeille_30_jours(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import Document
    from app.routers import admin
    from app.services.storage import get_storage
    _, _, tok = _register(client)

    def up(name):
        r = client.post("/api/documents/", headers=_h(tok),
                        files={"file": (f"{name}.pdf", io.BytesIO(PDF), "application/pdf")},
                        data={"name": name, "category": "administratif"})
        assert r.status_code == 201, r.text
        return r.json()

    old, recent, kept = up("ancien"), up("recent"), up("actif")
    # « ancien » a une version précédente (remplacement) → elle part avec lui.
    rep = client.put(f"/api/documents/{old['id']}/replace", headers=_h(tok),
                     files={"file": ("ancien_v2.pdf", io.BytesIO(PDF), "application/pdf")})
    assert rep.status_code == 200, rep.text
    cur_id = rep.json()["id"]
    db = SessionLocal()
    try:
        cur = db.get(Document, cur_id)
        version_keys = [old["file_key"], cur.file_key]
    finally:
        db.close()
    for d in (cur_id, recent["id"]):
        assert client.delete(f"/api/documents/{d}", headers=_h(tok)).status_code in (200, 204)
    db = SessionLocal()
    try:
        db.get(Document, cur_id).deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        db.commit()
    finally:
        db.close()

    # Route cron : secret obligatoire (comme les autres tâches admin).
    monkeypatch.setattr(admin.settings, "CRON_SECRET", "secret-cron-test")
    assert client.post("/api/admin/run-trash-purge").status_code == 403
    assert client.post("/api/admin/run-trash-purge",
                       headers={"X-Cron-Secret": "mauvais"}).status_code == 403
    r = client.post("/api/admin/run-trash-purge", headers={"X-Cron-Secret": "secret-cron-test"})
    assert r.status_code == 200, r.text
    assert r.json()["purged_documents"] >= 2

    st = get_storage()
    db = SessionLocal()
    try:
        assert db.get(Document, cur_id) is None and db.get(Document, old["id"]) is None
        assert db.get(Document, recent["id"]) is not None          # < 30 j : restaurable
        assert db.get(Document, kept["id"]) is not None
    finally:
        db.close()
    for k in version_keys:
        with pytest.raises(Exception):
            st.load(k)
    assert st.load(recent["file_key"]) == PDF and st.load(kept["file_key"]) == PDF


# ─── Faille 11 : paiement à l'usage sans abonnement ─────────────────────────────────────

def _set_user(uid, **vals):
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        for k, v in vals.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def test_overage_refuse_sans_abonnement(client):
    uid, _, tok = _register(client)
    r = client.post("/api/stripe/overage", params={"enabled": "true"}, headers=_h(tok))
    assert r.status_code == 402, r.text
    assert "abonnement" in r.json()["detail"]
    # Désactiver reste toujours possible.
    assert client.post("/api/stripe/overage", params={"enabled": "false"},
                       headers=_h(tok)).status_code == 200


def test_consume_analysis_ignore_un_overage_non_facturable(client):
    """Rejoue p2_overage : flag forcé en base, quota épuisé, sans client Stripe → 402."""
    from app.core.database import SessionLocal
    from app.core.quota import consume_analysis, _limit, _period
    from app.models import User
    uid, _, _ = _register(client)
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        lim = _limit(u)
        u.overage_enabled = True
        u.analyses_period = _period()
        u.analyses_used_this_month = lim
        db.commit()
        with pytest.raises(HTTPException) as e:
            consume_analysis(u, db)
        assert e.value.status_code == 402
        db.refresh(u)
        assert (u.overage_count or 0) == 0 and u.analyses_used_this_month == lim
    finally:
        db.close()


def test_overage_abonne_paye_inchange(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.core.quota import consume_analysis, _limit, _period
    from app.models import User, PlanType
    import app.services.billing_usage as bu
    monkeypatch.setattr(bu, "report_overage", lambda *a, **k: False)
    uid, _, tok = _register(client)
    _set_user(uid, plan=PlanType.pro, stripe_customer_id="cus_test_rgpd")
    r = client.post("/api/stripe/overage", params={"enabled": "true"}, headers=_h(tok))
    assert r.status_code == 200 and r.json()["overage_enabled"] is True
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        u.analyses_period = _period()
        u.analyses_used_this_month = _limit(u)
        db.commit()
        consume_analysis(u, db)                                # hors quota mais facturable
        db.refresh(u)
        assert u.overage_count == 1
    finally:
        db.close()


# ─── Faille 7 : compte démo = vitrine en lecture guidée ─────────────────────────────────

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
    import app.services.alerts as al
    monkeypatch.setattr(al, "send_email", fake)
    return sent


def _demo_msg(r):
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d.startswith("La démo est en lecture guidée : créez votre compte gratuit pour "), d
    return d


def test_parcours_demo_vitrine_reste_fonctionnel(client, demo):
    assert client.get("/api/auth/me", headers=demo).status_code == 200
    projs = client.get("/api/projects/", headers=demo)
    assert projs.status_code == 200 and projs.json()
    assert client.get("/api/stripe/status", headers=demo).status_code == 200
    # Simulation de groupement sur un marché démo analysé, avec un partenaire de l'annuaire.
    cts = client.get("/api/cotraitants/", headers=demo).json()
    assert cts
    ok = False
    for p in projs.json():
        r = client.post(f"/api/projects/{p['id']}/groupement/simulate", headers=demo,
                        json={"members": [{"kind": "annuaire", "id": cts[0]["id"]}], "save": False})
        if r.status_code == 200:
            ok = True
            break
    assert ok, "la simulation de groupement doit rester ouverte à la démo"
    # Recherche démo (canned) toujours servie.
    assert client.post("/api/sourcing/search", headers=demo, json={"query": "toiture"}).status_code == 200


def test_demo_ne_peut_plus_envoyer_d_email(client, demo, mails):
    pid = client.get("/api/projects/", headers=demo).json()[0]["id"]
    # Exploit d'origine : invitation vers une adresse tierce depuis le compte démo.
    r = client.post(f"/api/projects/{pid}/invites", headers=demo,
                    json={"recipient": "victime@tiers.example", "company_name": "Votre banque"})
    assert "partenaire" in _demo_msg(r)
    _demo_msg(client.post(f"/api/projects/{pid}/invites/1/resend", headers=demo))
    _demo_msg(client.post("/api/org/invite", headers=demo, json={"email": "victime@tiers.example"}))
    _demo_msg(client.put("/api/auth/me", params={"email": "victime@tiers.example"}, headers=demo))
    _demo_msg(client.post(f"/api/projects/{pid}/offre/figer", headers=demo))
    assert mails == []


def test_demo_ne_peut_plus_televerser(client, demo):
    r = client.post("/api/documents/", headers=demo,
                    files={"file": ("kbis.pdf", io.BytesIO(PDF), "application/pdf")},
                    data={"name": "Kbis", "category": "administratif"})
    _demo_msg(r)
    _demo_msg(client.post("/api/knowledge/upload", headers=demo,
                          files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")}))


def test_demo_ne_peut_plus_lancer_d_ia_payante(client, demo):
    pid = client.get("/api/projects/", headers=demo).json()[0]["id"]
    _demo_msg(client.post("/api/sourcing/ask", headers=demo, json={"project_id": pid, "question": "?"}))
    _demo_msg(client.post(f"/api/chiffrage/{pid}/estimate", headers=demo, json={}))
    _demo_msg(client.post("/api/knowledge/memoire", headers=demo, json={"text": "x"}))
    _demo_msg(client.post("/api/sourcing/documents", headers=demo, json={"project_id": pid}))
    # Défense en profondeur : même sans le middleware, consume_analysis refuse la démo.
    from app.core.database import SessionLocal
    from app.core.quota import consume_analysis
    from app.models import User
    from app.services.demo_seed import DEMO_EMAIL
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        with pytest.raises(HTTPException) as e:
            consume_analysis(u, db)
        assert e.value.status_code == 403 and "lecture guidée" in e.value.detail
    finally:
        db.close()


def test_demo_ne_peut_plus_gerer_compte_abonnement_equipe(client, demo):
    _demo_msg(client.post("/api/rgpd/delete-account", headers=demo,
                          json={"password": "x", "confirm": "SUPPRIMER"}))
    _demo_msg(client.post("/api/stripe/overage", params={"enabled": "true"}, headers=demo))
    _demo_msg(client.post("/api/stripe/create-checkout", params={"plan": "pro"}, headers=demo))
    _demo_msg(client.put("/api/org/", headers=demo, json={"name": "Pirate"}))
    _demo_msg(client.post("/api/org/transfer-ownership", headers=demo, json={"member_id": 1}))
    assert client.get("/api/auth/me", headers=demo).status_code == 200


def test_garde_demo_sans_effet_sur_un_vrai_compte(client):
    _, _, tok = _register(client)
    r = client.post("/api/documents/", headers=_h(tok),
                    files={"file": ("kbis.pdf", io.BytesIO(PDF), "application/pdf")},
                    data={"name": "Kbis", "category": "administratif"})
    assert r.status_code == 201, r.text
    # Jeton invalide sur une route gardée : la route répond elle-même (401), pas le garde.
    assert client.post("/api/documents/", headers=_h("pas-un-jeton"),
                       files={"file": ("k.pdf", io.BytesIO(PDF), "application/pdf")}).status_code == 401


def test_cron_n_ecrit_pas_au_compte_demo(client, demo, mails):
    """Relances/digests planifiés : rien ne part pour le compte démo."""
    from app.core.database import SessionLocal
    from app.models import Document, User
    from app.services.alerts import run_document_expiry_alerts, _demo_user_ids
    from app.services.demo_seed import DEMO_EMAIL
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        assert u.id in _demo_user_ids(db)
        db.add(Document(user_id=u.id, name="Attestation démo", file_key="demo/none.pdf",
                        expiration_date=date.today()))
        db.commit()
        run_document_expiry_alerts(db)
    finally:
        db.close()
    assert DEMO_EMAIL not in mails


# ─── Swagger coupé en production ─────────────────────────────────────────────────────────

def test_docs_coupees_en_production(tmp_path):
    env = dict(os.environ)
    env.update({
        "ENVIRONMENT": "production", "DEMO_MODE": "false",
        "SECRET_KEY": uuid.uuid4().hex + uuid.uuid4().hex,
        "CRON_SECRET": uuid.uuid4().hex, "DCE_ACCESS_CODE": uuid.uuid4().hex,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'prod.db'}",
        "SENTRY_DSN": "", "ANTHROPIC_API_KEY": "", "MISTRAL_API_KEY": "", "BREVO_API_KEY": "",
    })
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None\n"
        "c = TestClient(app)\n"
        "for p in ('/docs', '/redoc', '/openapi.json'):\n"
        "    assert c.get(p).status_code == 404, p\n"
        "csp = c.get('/api/health').headers['content-security-policy']\n"
        "assert 'cdn.jsdelivr.net' not in csp and 'tiangolo' not in csp, csp\n"
        "print('OK')\n"
    )
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and "OK" in p.stdout, p.stderr[-2000:]


def test_docs_toujours_disponibles_hors_production(client):
    assert client.get("/openapi.json").status_code == 200
