"""Lot 2 « liens » : rejoue les contournements trouvés après le premier lot de correctifs.

- Faille 6 en profondeur : un lien d'avis douteux (javascript:, « /\\hôte », « //hôte »…)
  ne doit survivre NULLE PART (modèles normalisés, Project.source_url, ai_analysis.source),
  même quand l'objet AO est construit sans passer par une source (navigateur, test, futur code).
- Message 422 lisible (ni « Value error, » ni valeur saisie renvoyée).
- Paiement à l'usage : bouton réservé à un abonnement payant actif.
- DPA aligné sur la page sécurité ; cron de purge de la corbeille documenté ; pypdf récent.
"""
import json
import pathlib
import re
import shutil
import subprocess
import uuid

import pytest

from app.core.database import SessionLocal
from app.models import Project, User

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
XSS = "javascript:fetch('/x?k='+localStorage.getItem('adjugo_token'))"
BAD_LINKS = [XSS, "/\\evil.com", "//evil.com/avis", "  JavaScript:alert(1)",
             "data:text/html,<script>1</script>", "java\tscript:alert(1)", "vbscript:x"]
GOOD_LINKS = ["https://www.boamp.fr/avis/detail/26-1", "http://a.fr/x", "/static/demo/avis.html"]


def _register(client):
    email = f"lien_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Test User",
        "company_name": "Liens SARL"})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _tender(url, ref="X1"):
    return {"objet": "Travaux", "acheteur": "Ville",
            "provenance": {"source": "BOAMP", "source_url": url, "official_ref": ref},
            "also_seen_in": [{"source": "TED", "source_url": XSS, "official_ref": "t"}],
            "dce_url": XSS}


# ── (1) Modèles normalisés : lien douteux → vide, jamais d'erreur ────────────
@pytest.mark.parametrize("bad", BAD_LINKS + [None, 123])
def test_normalized_models_neutralize_bad_links_without_error(bad):
    from app.sourcing.schemas import NormalizedCompany, NormalizedTender, Provenance
    t = NormalizedTender(**{**_tender(bad), "dce_url": bad})   # construit HORS source
    assert t.provenance.source_url == ""
    assert t.also_seen_in[0].source_url == ""
    assert t.dce_url is None
    assert Provenance(source="SIRENE", source_url=bad).source_url == ""
    c = NormalizedCompany(nom="X", provenance={"source": "SIRENE", "source_url": bad})
    assert c.provenance.source_url == ""


@pytest.mark.parametrize("good", GOOD_LINKS)
def test_normalized_models_keep_legit_links(good):
    from app.sourcing.schemas import NormalizedTender
    t = NormalizedTender(objet="o", provenance={"source": "BOAMP", "source_url": good}, dce_url=good)
    assert t.provenance.source_url == good and t.dce_url == good


# ── (2) Routeur sourcing : une seule règle pour le lien stocké ───────────────
@pytest.mark.parametrize("bad", BAD_LINKS)
def test_router_safe_link_uses_single_rule(bad):
    from app.routers.sourcing import _safe_link, _safe_source
    assert _safe_link(bad) is None                      # « /\evil.com » passait avant
    legacy = {"source": "BOAMP", "source_url": bad, "official_ref": "r"}
    out = _safe_source(legacy)
    assert out["source_url"] == "" and out["official_ref"] == "r"
    assert legacy["source_url"] == bad                  # l'original n'est pas modifié
    for g in GOOD_LINKS:
        assert _safe_link(g) == g


def test_safe_source_tolerates_missing_or_odd_values():
    from app.routers.sourcing import _safe_source
    assert _safe_source(None) == {}
    assert _safe_source("x") == {}
    assert _safe_source({"source": "BOAMP"}) == {"source": "BOAMP"}


@pytest.mark.parametrize("bad", [XSS, "/\\evil.com", "  JavaScript:alert(1)"])
def test_demo_analyze_never_stores_or_returns_bad_link(client, bad):
    """Rejeu cotraitance-6 [5] : compte démo, AO DEMO- avec un lien piégé."""
    d = client.post("/api/auth/demo")
    if d.status_code != 200:
        pytest.skip("compte démo indisponible dans cet environnement")
    h = {"Authorization": f"Bearer {d.json()['access_token']}"}
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": _tender(bad, "DEMO-01")})
    assert r.status_code == 200, r.text
    assert r.json()["source"]["source_url"] == ""
    pid = r.json()["project_id"]
    db = SessionLocal()
    try:
        p = db.get(Project, pid)
        assert p.source_url is None
        assert "javascript" not in json.dumps(p.ai_analysis or {}).lower()
        assert "evil.com" not in json.dumps(p.ai_analysis or {}).lower()
    finally:
        db.close()


def test_analyze_never_stores_or_returns_bad_link(client, monkeypatch):
    """Rejeu cotraitance-6 [6] : compte réel, IA simulée — l'analyse stockée et la réponse
    ne gardent pas le lien piégé (ni dans source_url, ni dans ai_analysis.source)."""
    import app.services.analysis as an
    from app.sourcing.sources.boamp import BoampSource
    monkeypatch.setattr(an, "analyze_dce_text",
                        lambda *a, **k: {"summary": "s", "details": {"intitule_marche": "T"},
                                         "match_score": 50})
    monkeypatch.setattr(BoampSource, "fetch_dce", lambda self, t: "")
    h = _register(client)
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": _tender("/\\evil.com")})
    assert r.status_code == 200, r.text
    assert r.json()["source"]["source_url"] == ""
    assert "evil.com" not in r.text and "javascript" not in r.text.lower()
    pid = r.json()["project_id"]
    db = SessionLocal()
    try:
        p = db.get(Project, pid)
        assert p.source_url is None
        assert (p.ai_analysis or {})["source"]["source_url"] == ""
    finally:
        db.close()
    o = client.get(f"/api/projects/{pid}", headers=h)
    assert o.status_code == 200
    assert "evil.com" not in o.text and "javascript:" not in o.text.lower()


def test_analyze_keeps_legit_link(client, monkeypatch):
    import app.services.analysis as an
    from app.sourcing.sources.boamp import BoampSource
    monkeypatch.setattr(an, "analyze_dce_text",
                        lambda *a, **k: {"summary": "s", "details": {}, "match_score": 50})
    monkeypatch.setattr(BoampSource, "fetch_dce", lambda self, t: "")
    h = _register(client)
    url = "https://www.boamp.fr/avis/detail/26-12345"
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": _tender(url)})
    assert r.status_code == 200, r.text
    assert r.json()["source"]["source_url"] == url
    db = SessionLocal()
    try:
        assert db.get(Project, r.json()["project_id"]).source_url == url
    finally:
        db.close()


# ── (3) Message 422 lisible côté navigateur ──────────────────────────────────
def _js_method(name):
    """Extrait une méthode de l'objet Vue (app.js) pour l'exécuter seule sous Node."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    m = (re.search(r"\n    " + name + r"\((\w*)\) \{\n(.*?)\n    \},\n", js, re.S)
         or re.search(r"\n    " + name + r"\((\w*)\) \{ (.*?) \},\n", js))
    assert m, f"méthode {name} introuvable"
    return f"function {name}({m.group(1)}) {{\n{m.group(2)}\n}}"


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_422_message_has_no_jargon_nor_echoed_input(client):
    h = _register(client)
    r = client.post("/api/projects/", json={"name": "AO", "source_url": XSS}, headers=h)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list)
    extra = [{"type": "missing", "loc": ["body", "name"], "msg": "Field required", "input": {}},
             {"type": "string_too_short", "loc": ["body", "password"], "msg": "String should have at least 8 characters", "input": "abc"},
             {"type": "value_error", "loc": ["body", "email"], "msg": "value is not a valid email address: x", "input": "secret@"},
             {"type": "int_parsing", "loc": ["query", "zzz"], "msg": "Input should be a valid integer", "input": "secret-zzz"},
             {"type": "value_error", "loc": ["body", "siret"], "msg": "Value error, Le SIRET doit comporter exactement 14 chiffres.", "input": "12"}]
    fn = _js_method("validationMsg")
    res = _node(fn + "\nconsole.log(JSON.stringify(" + json.dumps([detail[0]] + extra) + ".map(validationMsg)));")
    first, missing, short, email, num, siret = res
    assert first.startswith("Adresse de l'avis invalide")
    for msg in res:
        assert "Value error" not in msg and "value_error" not in msg
        assert "javascript" not in msg.lower() and "secret" not in msg   # jamais la valeur saisie
        assert not re.search(r"\b(Field|Input|String|should)\b", msg)    # pas d'anglais pydantic
    assert missing == "Nom : information obligatoire."
    assert short == "Mot de passe : trop court."
    assert email == "Adresse e-mail invalide."
    assert "zzz" not in num and "nombre invalide" in num
    assert siret == "Le SIRET doit comporter exactement 14 chiffres."


def test_api_uses_clean_validation_message():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    api = js[js.index("async api(method"):js.index("validationMsg(f) {")]
    assert "this.validationMsg(d[0])" in api
    assert "f.input" not in api.replace("JAMAIS f.input", "")
    assert '"Champ « " + field' not in js


# ── (4) Paiement à l'usage : réservé à un abonnement payant actif ────────────
def test_overage_button_only_for_paid_plan():
    html = (STATIC / "app.html").read_text(encoding="utf-8")
    i = html.index("Paiement à l'usage</b>")
    block = html[i:i + 2000]
    assert 'v-if="overageAvailable() || (stats.usage&&stats.usage.overage_enabled)"' in block
    assert "Disponible avec un abonnement Pro ou Business" in block
    fn = _js_method("overageAvailable")
    cases = [{"usage": {"plan": p}} for p in ("starter", "pro", "business", "")] + [{}, {"usage": None}]
    script = (fn.replace("function overageAvailable()", "function overageAvailable(stats)")
                .replace("this.stats", "stats")
              + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(overageAvailable)));")
    assert _node(script) == [False, True, True, False, False, False]


def test_overage_server_still_refuses_unpaid(client):
    h = _register(client)
    r = client.post("/api/stripe/overage?enabled=true", headers=h)
    assert r.status_code in (400, 402, 403), r.text


# ── (5) DPA aligné sur la page sécurité ──────────────────────────────────────
def test_dpa_wording_matches_security_page(client):
    s = client.get("/securite")
    assert s.status_code == 200
    sec = s.text
    dpa = client.get("/dpa")
    assert dpa.status_code == 200
    t = dpa.text
    phrase = "stockées chiffrées au repos chez notre hébergeur européen"
    assert phrase in t and phrase in sec
    assert "sauvegardes quotidiennes chiffrées, stockées en Union européenne" not in t
    assert "ne sont pas utilisés pour entraîner un modèle" in t
    assert "encadrée par les conditions applicables à l'API" in t
    assert "{{AI_" not in t


# ── (6) Cron de purge de la corbeille documenté ──────────────────────────────
def test_go_live_documents_trash_purge_cron():
    doc = (ROOT / "docs" / "GO_LIVE.md").read_text(encoding="utf-8")
    assert "POST /api/admin/run-trash-purge" in doc
    i = doc.index("run-trash-purge")
    assert "X-Cron-Secret" in doc[i - 1500:i + 1500]
    assert "quotidien" in doc[i - 200:i]


# ── (7) pypdf récent (plafonds de décompression) aligné sur le venv ──────────
def test_pypdf_pinned_to_tested_version_with_limits():
    import pypdf
    from pypdf import filters
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    m = re.search(r"^pypdf==([\d.]+)", req, re.M)
    assert m and m.group(1) == pypdf.__version__
    assert int(m.group(1).split(".")[0]) >= 6
    assert hasattr(filters, "ZLIB_MAX_OUTPUT_LENGTH") and hasattr(filters, "LimitReachedError")
    from pypdf import PageObject, PdfReader, PdfWriter   # API utilisée par le code
    assert all(hasattr(PageObject, a) for a in ("merge_page", "extract_text", "mediabox"))
    assert hasattr(PdfWriter, "add_page") and hasattr(PdfReader, "pages")
