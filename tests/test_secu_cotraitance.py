"""Non-régression sécurité — co-traitance (audit cyber oct. 2026, failles 6, 9 et 10).

Chaque test rejoue l'exploit d'origine et vérifie qu'il échoue désormais :
  6  — lien « Avis d'origine » en javascript: (XSS dans l'espace cloisonné du partenaire)
  9  — le partenaire voyait/téléchargeait les versions remplacées des pièces
  10 — « offre figée / défigée » chaînée sous le membre créateur au lieu de l'entreprise
"""
import pathlib
import uuid

import pytest

from app.core.database import SessionLocal
from app.models import AuditLog, Document, Project, User

JS_PAYLOAD = "javascript:fetch('/x?k='+localStorage.getItem('adjugo_token'))"
STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"


def _register(client, company="Org SARL"):
    email = f"cot_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Test User",
        "company_name": company})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        uid = u.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, uid


def _invite(client, headers, pid, **extra):
    body = {"recipient": "partenaire", "company_name": "Partenaire SAS"}
    body.update(extra)
    r = client.post(f"/api/projects/{pid}/invites", json=body, headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j["path"].rsplit("/", 1)[-1]


# ── Faille 6 : XSS via source_url ────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    JS_PAYLOAD, "JavaScript:alert(1)", "  javascript:alert(1)", "data:text/html,<script>1</script>",
    "vbscript:msgbox(1)", "//evil.example/avis", "java\tscript:alert(1)", "https://x.fr/\nabc",
])
def test_create_project_rejects_dangerous_source_url(client, bad):
    h, _ = _register(client)
    r = client.post("/api/projects/", json={"name": "AO", "source_url": bad}, headers=h)
    assert r.status_code == 422, r.text
    # Message en français, sans jargon technique.
    assert "http" in r.text and "invalide" in r.text


def test_update_project_rejects_dangerous_source_url(client):
    h, _ = _register(client)
    pid = client.post("/api/projects/", json={"name": "AO"}, headers=h).json()["id"]
    r = client.put(f"/api/projects/{pid}", json={"source_url": JS_PAYLOAD}, headers=h)
    assert r.status_code == 422, r.text
    db = SessionLocal()
    try:
        assert db.query(Project).get(pid).source_url is None
    finally:
        db.close()


@pytest.mark.parametrize("good", [
    "https://www.boamp.fr/avis/detail/26-12345", "http://marches.example.fr/a?b=1",
    "/static/demo/avis-boamp.html",
])
def test_legit_source_urls_still_accepted(client, good):
    h, _ = _register(client)
    r = client.post("/api/projects/", json={"name": "AO", "source_url": good}, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    tok = _invite(client, h, pid)
    assert client.get(f"/api/invite/{tok}").json()["project"]["source_url"] == good


def test_guest_view_sanitizes_legacy_javascript_source_url(client):
    """Une valeur ancienne déjà en base (écrite avant la validation, ou par un autre chemin
    comme /api/sourcing/analyze) ne doit JAMAIS ressortir telle quelle au partenaire."""
    h, _ = _register(client)
    pid = client.post("/api/projects/", json={"name": "AO"}, headers=h).json()["id"]
    db = SessionLocal()
    try:
        db.query(Project).get(pid).source_url = JS_PAYLOAD   # contourne la validation
        db.commit()
    finally:
        db.close()
    tok = _invite(client, h, pid)
    r = client.get(f"/api/invite/{tok}")
    assert r.status_code == 200, r.text
    assert r.json()["project"]["source_url"] is None
    assert "javascript" not in r.text.lower()


def test_sourcing_sources_neutralize_non_web_links():
    """Garde centrale : toute source d'AO (BOAMP, TED, futures…) voit ses liens filtrés."""
    from app.sourcing.base import TenderCriteria, TenderSource
    from app.sourcing.schemas import NormalizedTender, Provenance

    class Evil(TenderSource):
        name = "EVIL"

        def search(self, criteria):
            return [NormalizedTender(
                objet="AO", dce_url="javascript:alert(1)",
                provenance=Provenance(source="EVIL", source_url=JS_PAYLOAD),
                also_seen_in=[Provenance(source="X", source_url="data:text/html,x"),
                              Provenance(source="Y", source_url="https://ok.fr/a")])]

    t = Evil().search(TenderCriteria())[0]
    assert t.provenance.source_url == ""
    assert t.dce_url is None
    assert [p.source_url for p in t.also_seen_in] == ["", "https://ok.fr/a"]


def test_front_links_go_through_safe_url_guard():
    """Côté navigateur : aucun lien construit depuis une donnée ne contourne safeUrl."""
    inv = (STATIC / "invite.html").read_text(encoding="utf-8")
    assert "const safeUrl" in inv
    assert 'href="${esc(p.source_url)}"' not in inv
    assert "href=\"${esc(t.url || t.provenance.source_url)}\"" not in inv
    # Vague 2b (B3) : la recherche de marchés (3e lien construit depuis une donnée) a quitté l'espace partenaire ; le
    # lien de l'avis d'origine passe toujours par le garde, et tout autre lien est un chemin interne fixe.
    assert inv.count("safeUrl(") >= 2 and 'href="${esc(safeUrl(p.source_url))}"' in inv
    import re
    for m in re.finditer(r'href="\$\{([^}]+)\}', inv):
        assert m.group(1).startswith("esc(safeUrl(") or m.group(1) == "pieceUrl", m.group(1)
    html = (STATIC / "app.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "safeUrl(u)" in js
    import re
    for m in re.finditer(r':href="([^"]+)"', html):
        expr = m.group(1).strip()
        # Autorisé : passé par safeUrl, préfixe fixe (chemin interne / mailto:), ou helper interne.
        assert (expr.startswith("safeUrl(") or expr.startswith("'/") or expr.startswith("'mailto:")
                or expr.startswith("companyWeb(")), f"lien non protégé : {expr}"


def test_safe_url_js_semantics_match_server():
    """Le garde JS (invite.html / app.js) et le garde serveur ont la même règle."""
    from app.schemas import safe_link_url
    for u in ["https://a.fr", "http://a.fr/x", "/static/x.html"]:
        assert safe_link_url(u) == u
    for u in [JS_PAYLOAD, "//a.fr", "/\\a.fr", "data:x", "mailto:a@b.fr", "https://", "ftp://a.fr", ""]:
        assert safe_link_url(u) is None


# ── Faille 9 : versions remplacées visibles par le partenaire ────────────────
def _project_doc(client, h, pid, content: bytes, name="cctp.pdf"):
    r = client.post("/api/documents/", files={"file": (name, content, "application/pdf")},
                    data={"name": name, "category": "autre"}, headers=h)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    db = SessionLocal()
    try:
        # Rangée dans le dossier de l'acheteur (« DCE »), comme l'import du dossier du marché : relecture de la vague
        # 2b, le partenaire ne voit plus que ce dossier (une pièce du marché hors dossier ne lui est jamais partagée).
        d = db.query(Document).get(did)
        d.project_id, d.folder = pid, "DCE"
        db.commit()
    finally:
        db.close()
    return did


def test_guest_cannot_see_or_download_replaced_versions(client):
    h, _ = _register(client)
    pid = client.post("/api/projects/", json={"name": "AO pièces"}, headers=h).json()["id"]
    old_id = _project_doc(client, h, pid, b"%PDF-1.4\n% CCTP v1 - PRIX ERRONE 120000 EUR\n%%EOF")
    r = client.put(f"/api/documents/{old_id}/replace",
                   files={"file": ("cctp.pdf", b"%PDF-1.4\n% CCTP v2 corrige\n%%EOF", "application/pdf")},
                   headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        old = db.query(Document).get(old_id)
        assert old.parent_id, "la pièce remplacée doit être archivée (parent_id)"
        new_id = old.parent_id
    finally:
        db.close()
    tok = _invite(client, h, pid)

    ids = [d["id"] for d in client.get(f"/api/invite/{tok}").json()["documents"]]
    assert ids == [new_id], ids                                     # plus l'ancienne
    assert client.get(f"/api/invite/{tok}/doc/{old_id}").status_code == 404
    assert client.get(f"/api/invite/{tok}/doc/{new_id}").status_code in (200, 307)

    # Dossier de l'AO côté mandataire : plus de doublon homonyme périmé.
    d = client.get(f"/api/projects/{pid}/documents", headers=h).json()
    listed = [doc["id"] for f in d["folders"] for doc in f["documents"]]
    assert listed == [new_id] and d["total"] == 1

    # Aggravation d'origine : la version courante mise à la corbeille → l'ancienne
    # orpheline ne redevient PAS téléchargeable par le partenaire.
    assert client.delete(f"/api/documents/{new_id}", headers=h).status_code == 204
    assert client.get(f"/api/invite/{tok}/doc/{old_id}").status_code == 404
    assert client.get(f"/api/invite/{tok}").json()["documents"] == []


# ── Faille 10 : « offre figée » chaînée sous le tenant ──────────────────────
def _join_org(owner_uid, member_uid):
    db = SessionLocal()
    try:
        owner = db.query(User).get(owner_uid)
        m = db.query(User).get(member_uid)
        m.org_id = owner.org_id
        m.org_role = "membre"
        db.commit()
    finally:
        db.close()


def test_offer_freeze_audit_is_chained_under_tenant_owner(client):
    h1, a1 = _register(client, "Org A")
    h2, a2 = _register(client, "Perso A2")
    client.get("/api/org/", headers=h1)            # garantit l'org de A1
    _join_org(a1, a2)
    # A2 (membre) crée l'AO → Project.user_id = A2
    pid = client.post("/api/projects/", json={"name": "Marché A"}, headers=h2).json()["id"]
    tok = _invite(client, h2, pid)
    v = client.get(f"/api/invite/{tok}/contribution").json()["version"]
    r = client.put(f"/api/invite/{tok}/contribution",
                   json={"version": v, "prix_lot_ht": 1000, "company_name": "Partenaire SAS"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invite/{tok}/contribution/submit").status_code == 200
    # A1 fige / défige / refige ; un changement de part défige aussi (chemin invité).
    assert client.post(f"/api/projects/{pid}/offre/figer", json={"lead_total_ht": 5000}, headers=h1).status_code == 200
    assert client.delete(f"/api/projects/{pid}/offre/figer", headers=h1).status_code == 200
    assert client.post(f"/api/projects/{pid}/offre/figer", json={"lead_total_ht": 5000}, headers=h2).status_code == 200

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.project_id == pid,
                                         AuditLog.action.in_(["offer.frozen", "offer.unfrozen"])).all()
        assert len(rows) == 3
        assert {r.owner_id for r in rows} == {a1}, [(r.action, r.owner_id) for r in rows]
        # Toute la traçabilité du dossier est sous UN seul propriétaire (le tenant).
        owners = {r.owner_id for r in db.query(AuditLog).filter(AuditLog.project_id == pid).all()}
        assert owners == {a1}, owners
    finally:
        db.close()

    integ = client.get("/api/audit/integrity", headers=h1).json()
    assert integ["intact"] is True and integ["owner_id"] == a1

    # L'ex-membre efface ses propres entrées (chemin RGPD « propriétaire solo » :
    # DELETE AuditLog WHERE owner_id = A2) → la trace « offre figée » de l'entreprise reste.
    db = SessionLocal()
    try:
        db.query(AuditLog).filter(AuditLog.owner_id == a2).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    actions = [e["action"] for e in client.get(f"/api/projects/{pid}/audit", headers=h1).json()]
    assert actions.count("offer.frozen") == 2 and actions.count("offer.unfrozen") == 1
    journal = [e["action"] for e in client.get(f"/api/invite/{tok}/journal").json()["entries"]]
    assert "offer.frozen" in journal


def test_tenant_owner_id_falls_back_to_creator(client):
    from app.routers.invites import tenant_owner_id
    _, uid = _register(client)
    db = SessionLocal()
    try:
        u = db.query(User).get(uid)
        u.org_id = None
        db.commit()
        p = Project(user_id=uid, name="AO solo")
        db.add(p); db.commit()
        assert tenant_owner_id(p, db) == uid
    finally:
        db.close()
