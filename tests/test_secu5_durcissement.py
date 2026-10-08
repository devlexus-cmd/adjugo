"""Audit cyber oct. 2026 — vague 3, lot « durcissement ».

1. Google OAuth : `state` lié au navigateur (cookie HttpOnly) + jeton de session hors URL
   (code d'échange à usage unique, 60 s, dans le fragment). Google est SIMULÉ : aucun appel réseau.
2. Masquage des jetons et des emails dans les journaux et dans les évènements Sentry.
3. Échappement des valeurs dynamiques dans les PDF reportlab (DUME, DPGF, compte-rendu…).
4. Coffre-fort : type MIME dérivé de l'extension, nosniff, téléchargement forcé.
"""
import hashlib
import io
import json
import logging
import sys
import types
import uuid
from datetime import date, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import pytest
from pypdf import PdfReader

from app.core.config import get_settings
from app.routers import google_auth as ga

HOSTILE = "A & B <Sàrl>"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Google OAuth
# ══════════════════════════════════════════════════════════════════════════════
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeGoogle:
    """Remplace le module `requests` de google_auth : Google n'est jamais appelé."""

    def __init__(self, email):
        self.email = email
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("post", url))
        return _FakeResp({"access_token": "ya29.jeton-google-factice"})

    def get(self, url, **kw):
        self.calls.append(("get", url))
        return _FakeResp({"email": self.email, "email_verified": True, "name": "Test Google"})


@pytest.fixture
def google(monkeypatch, client):
    s = get_settings()
    monkeypatch.setattr(s, "GOOGLE_CLIENT_ID", "client-id-de-test")
    monkeypatch.setattr(s, "GOOGLE_CLIENT_SECRET", "client-secret-de-test")
    fake = _FakeGoogle(f"g_{uuid.uuid4().hex[:8]}@exemple-test.fr")
    monkeypatch.setattr(ga, "requests", fake)
    client.cookies.clear()
    yield fake
    client.cookies.clear()


def _login(client):
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code in (302, 307), r.text
    loc = r.headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]
    raw = [h for h in r.headers.get_list("set-cookie") if h.startswith(ga.STATE_COOKIE + "=")]
    assert raw, "le cookie lié au navigateur doit être posé"
    jar = SimpleCookie()
    jar.load(raw[0])
    return state, jar[ga.STATE_COOKIE], loc


def _callback(client, state, nonce=None, **params):
    client.cookies.clear()
    headers = {"Cookie": f"{ga.STATE_COOKIE}={nonce}"} if nonce else {}
    q = {"code": "code-google-factice", "state": state}
    q.update(params)
    return client.get("/api/auth/google/callback", params=q, headers=headers, follow_redirects=False)


def _gerror(r) -> str:
    loc = r.headers["location"]
    assert "gcode" not in loc and "gtoken" not in loc
    return parse_qs(urlparse(loc).query).get("gerror", [""])[0]


def _cleared(r) -> bool:
    return any(h.startswith(ga.STATE_COOKIE + "=") and "max-age=0" in h.lower()
               for h in r.headers.get_list("set-cookie"))


def test_oauth_login_pose_un_cookie_lie_au_state(client, google):
    state, morsel, loc = _login(client)
    nonce = morsel.value
    assert morsel["httponly"] and morsel["secure"]
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == "/api/auth/google/callback"      # envoyé au seul retour Google
    assert morsel["max-age"] == str(ga.STATE_TTL_S) == "600"
    # Le state signé porte l'EMPREINTE du nonce, jamais le nonce lui-même.
    from app.core.security import decode_token
    st = decode_token(state)
    assert st["purpose"] == "google_oauth"
    assert st["nh"] == hashlib.sha256(nonce.encode()).hexdigest()
    assert nonce not in loc
    assert google.calls == []


def test_oauth_retour_sans_cookie_refuse(client, google):
    state, _morsel, _ = _login(client)
    r = _callback(client, state, nonce=None)
    assert r.status_code in (302, 307)
    assert "navigateur" in _gerror(r)
    assert google.calls == []           # Google n'est même pas contacté
    assert _cleared(r)


def test_oauth_retour_avec_un_autre_cookie_refuse(client, google):
    state_a, _cookie_a, _ = _login(client)
    _state_b, cookie_b, _ = _login(client)
    # Scénario d'attaque : le state de l'attaquant (A) rejoué dans le navigateur de la
    # victime, qui détient un autre cookie (B).
    r = _callback(client, state_a, nonce=cookie_b.value)
    assert "navigateur" in _gerror(r)
    r = _callback(client, state_a, nonce="valeur-forgee")
    assert "navigateur" in _gerror(r)
    assert google.calls == []


def test_oauth_state_non_signe_ou_detourne_refuse(client, google):
    """Protection existante conservée : state signé, à finalité google_oauth, 10 min."""
    _state, morsel, _ = _login(client)
    from app.core.security import create_access_token
    session_like = create_access_token({"sub": "1", "tv": 0})
    for bad in ("n-importe-quoi", session_like):
        r = _callback(client, bad, nonce=morsel.value)
        assert "invalide ou expirée" in _gerror(r)
    expired = create_access_token({"purpose": "google_oauth",
                                   "nh": hashlib.sha256(morsel.value.encode()).hexdigest()},
                                  expires_delta=timedelta(seconds=-5))
    assert "invalide ou expirée" in _gerror(_callback(client, expired, nonce=morsel.value))
    assert google.calls == []


def test_oauth_erreur_google_message_fixe(client, google):
    state, morsel, _ = _login(client)
    r = _callback(client, state, nonce=morsel.value, code="", error="<b>Appelez le 0899</b>")
    msg = _gerror(r)
    assert msg == "Connexion Google interrompue. Réessayez." and "0899" not in r.headers["location"]


def test_oauth_flux_complet_code_unique_jamais_de_jeton_dans_l_url(client, google):
    state, morsel, _ = _login(client)
    r = _callback(client, state, nonce=morsel.value)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    u = urlparse(loc)
    assert u.path == "/app" and u.query == ""                  # rien dans la query string
    assert u.fragment.startswith("gcode=")
    assert "gtoken" not in loc and "eyJ" not in loc            # aucun JWT dans l'URL
    assert _cleared(r)                                          # cookie effacé au retour
    assert [c[0] for c in google.calls] == ["post", "get"]
    code = parse_qs(u.fragment)["gcode"][0]

    ex = client.post("/api/auth/google/exchange", json={"code": code})
    assert ex.status_code == 200, ex.text
    assert ex.headers.get("cache-control") == "no-store"
    tok = ex.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["email"] == google.email

    # Usage unique : le même code ne resert jamais.
    again = client.post("/api/auth/google/exchange", json={"code": code})
    assert again.status_code == 400 and "invalide ou expiré" in again.json()["detail"]


def test_oauth_code_d_echange_expire_apres_60_s(client, google, monkeypatch):
    state, morsel, _ = _login(client)
    code = parse_qs(urlparse(_callback(client, state, nonce=morsel.value).headers["location"]).fragment)["gcode"][0]
    real = ga._now
    monkeypatch.setattr(ga, "_now", lambda: real() + ga.EXCHANGE_TTL_S + 1)
    r = client.post("/api/auth/google/exchange", json={"code": code})
    assert r.status_code == 400


def test_oauth_code_refuse_si_sessions_revoquees_entre_temps(client, google):
    state, morsel, _ = _login(client)
    code = parse_qs(urlparse(_callback(client, state, nonce=morsel.value).headers["location"]).fragment)["gcode"][0]
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == google.email).first()
        u.token_version = int(u.token_version or 0) + 1      # ex. mot de passe changé
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/google/exchange", json={"code": code}).status_code == 400
    assert client.post("/api/auth/google/exchange", json={"code": "inconnu"}).status_code == 400


def test_oauth_front_lit_le_fragment_et_echange_par_post():
    import pathlib
    js = pathlib.Path("app/static/app.js").read_text(encoding="utf-8")
    assert "gtoken" not in js
    assert "location.hash" in js and "/api/auth/google/exchange" in js
    src = pathlib.Path("app/routers/google_auth.py").read_text(encoding="utf-8")
    assert "?gtoken=" not in src


# ══════════════════════════════════════════════════════════════════════════════
# 2. Masquage dans les journaux et dans Sentry
# ══════════════════════════════════════════════════════════════════════════════
from app.core.redact import RedactingFilter, install_log_redaction, mask_text  # noqa: E402

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLWZhY3RpY2U"


@pytest.mark.parametrize("raw, expected", [
    ("GET /invite/AbC123_secret-tok", "GET /invite/***"),
    ("path=/api/invite/AbC123_secret/contribution/piece", "path=/api/invite/***/contribution/piece"),
    ("https://x.fr/app?verify=abc.def&lang=fr", "https://x.fr/app?verify=***&lang=fr"),
    ("/app?reset=Zz9_-q", "/app?reset=***"),
    ("cb?code=4/0Abc&state=xyz", "cb?code=***&state=***"),
    ("token=abcdef123", "token=***"),
    ("Authorization: Bearer " + _JWT, "Authorization: Bearer ***"),
    ("jeton " + _JWT + " fin", "jeton *** fin"),
    ("email envoyé destinataire=jean.dupont@exemple.fr sujet=Bonjour",
     "email envoyé destinataire=j***@exemple.fr sujet=Bonjour"),
    ("email=jean.dupont%40exemple.fr", "email=j***%40exemple.fr"),
    ("q=Jean%20jean.d@exemple.fr", "q=J***@exemple.fr"),
    ("<marie@x.fr>, paul.n@y.org.", "<m***@x.fr>, p***@y.org."),
    ("postal_code=29000 status=404 code_ape=4321A", "postal_code=29000 status=404 code_ape=4321A"),
])
def test_masquage_texte(raw, expected):
    assert mask_text(raw) == expected
    assert mask_text(expected) == expected            # idempotent


def _record(msg, *args, exc_info=None):
    return logging.LogRecord("adjugo", logging.INFO, __file__, 1, msg, args, exc_info)


def test_filtre_journaux_couvre_les_arguments():
    rec = _record("email envoyé destinataire=%s sujet=%s via=%s", "marie.curie@labo.fr", "Invitation", "brevo")
    assert RedactingFilter().filter(rec) is True
    assert rec.getMessage() == "email envoyé destinataire=m***@labo.fr sujet=Invitation via=brevo"
    assert not rec.args
    # Message sans donnée sensible : gabarit et arguments intacts (regroupement Sentry préservé).
    rec2 = _record("request method=%s status=%s", "GET", 200)
    RedactingFilter().filter(rec2)
    assert rec2.msg == "request method=%s status=%s" and rec2.args == ("GET", 200)


def test_filtre_journaux_masque_la_trace_d_exception():
    try:
        raise ValueError("échec d'envoi à paul@exemple.fr pour /invite/TOKEN_SECRET_42")
    except ValueError:
        rec = _record("échec", exc_info=sys.exc_info())
    RedactingFilter().filter(rec)
    out = logging.Formatter("%(message)s").format(rec)
    assert "paul@" not in out and "TOKEN_SECRET_42" not in out
    assert "p***@exemple.fr" in out and "/invite/***" in out


def test_filtre_pose_au_demarrage_et_journal_des_requetes_masque(client):
    # setup_logging() (app.main) a posé le filtre sur le handler racine.
    root = logging.getLogger()
    assert any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters)
    # Le journal des requêtes (app.core.observability.request_logger) ne laisse plus passer
    # le jeton d'invitation présent dans le chemin.
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    lg = logging.getLogger("adjugo")
    lg.addHandler(h)
    install_log_redaction(("adjugo",))
    old = lg.level
    lg.setLevel(logging.INFO)
    try:
        client.get("/api/invite/JETON_TRES_SECRET_123/journal")
    finally:
        lg.removeHandler(h)
        lg.setLevel(old)
    out = buf.getvalue()
    assert "/api/invite/***/journal" in out and "JETON_TRES_SECRET_123" not in out


def _sentry_event():
    return {
        "message": "email envoyé destinataire=jean.dupont@exemple.fr",
        "logentry": {"message": "destinataire=%s", "params": ["jean.dupont@exemple.fr"]},
        "request": {
            "url": "https://adjugo.example/api/invite/JETON_SECRET_777/contribution",
            "query_string": "verify=" + _JWT + "&lang=fr",
            "method": "GET",
            "headers": {"Authorization": "Bearer " + _JWT, "Cookie": "s=1",
                        "User-Agent": "Mozilla/5.0", "X-Cron-Secret": "cron"},
            "cookies": {"s": "1"},
            "data": {"email": "jean.dupont@exemple.fr", "password": "motdepasse"},
        },
        "user": {"id": 42, "email": "jean.dupont@exemple.fr", "ip_address": "203.0.113.9"},
        "exception": {"values": [{"type": "ValueError",
                                  "value": "lien /invite/JETON_SECRET_777 pour jean.dupont@exemple.fr",
                                  "stacktrace": {"frames": [{"function": "f",
                                                             "vars": {"token": "JETON_SECRET_777",
                                                                      "dest": "jean.dupont@exemple.fr"}}]}}]},
        "breadcrumbs": {"values": [{"category": "httplib",
                                    "data": {"url": "https://adjugo.example/app?reset=RESET_TOK"}},
                                   {"category": "log", "message": "GET /invite/JETON_SECRET_777"}]},
        "extra": {"destinataire": "jean.dupont@exemple.fr", "gcode": "CODE_UNIQUE"},
    }


def test_sentry_before_send_masque_et_retire_les_secrets():
    from app.core.observability import sentry_before_send
    out = sentry_before_send(_sentry_event(), {})
    dump = json.dumps(out, ensure_ascii=False)
    for secret in ("jean.dupont@", "JETON_SECRET_777", "eyJ", "RESET_TOK", "CODE_UNIQUE",
                   "motdepasse", "203.0.113.9", "cron"):
        assert secret not in dump, secret
    req = out["request"]
    assert "cookies" not in req and "data" not in req
    assert set(req["headers"]) == {"User-Agent"}
    assert req["url"] == "https://adjugo.example/api/invite/***/contribution"
    assert req["query_string"] == "verify=***&lang=fr"
    assert out["user"] == {"id": 42}
    assert "j***@exemple.fr" in out["message"]                 # domaine conservé (diagnostic)
    assert out["exception"]["values"][0]["value"] == "lien /invite/*** pour j***@exemple.fr"


def test_sentry_before_send_abandonne_plutot_que_d_envoyer_en_clair():
    from app.core.observability import sentry_before_send

    class Piege(dict):
        def get(self, *a, **k):
            raise RuntimeError("structure inattendue")

    assert sentry_before_send(Piege(message="jean@exemple.fr"), {}) is None
    assert sentry_before_send("pas un évènement", {}) is None


def test_sentry_before_breadcrumb_masque():
    from app.core.observability import sentry_before_breadcrumb
    crumb = {"category": "log", "message": "email envoyé destinataire=ana@exemple.fr",
             "data": {"url": "https://x/api/invite/TOKX/claim?token=abc"}}
    out = sentry_before_breadcrumb(crumb, {})
    assert out["message"] == "email envoyé destinataire=a***@exemple.fr"
    assert out["data"]["url"] == "https://x/api/invite/***/claim?token=***"


def test_init_sentry_branche_les_crochets_et_coupe_les_donnees_personnelles(monkeypatch):
    from app.core import observability as obs
    captured = {}
    sdk = types.ModuleType("sentry_sdk")
    sdk.init = lambda **kw: captured.update(kw)
    integ = types.ModuleType("sentry_sdk.integrations")
    fa = types.ModuleType("sentry_sdk.integrations.fastapi")
    st = types.ModuleType("sentry_sdk.integrations.starlette")
    fa.FastApiIntegration = lambda: "fastapi"
    st.StarletteIntegration = lambda: "starlette"
    for name, mod in (("sentry_sdk", sdk), ("sentry_sdk.integrations", integ),
                      ("sentry_sdk.integrations.fastapi", fa),
                      ("sentry_sdk.integrations.starlette", st)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(obs.settings, "SENTRY_DSN", "https://cle@o0.ingest.invalid/1")
    assert obs.init_sentry() is True
    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["before_send"] is obs.sentry_before_send
    assert captured["before_send_transaction"] is obs.sentry_before_send
    assert captured["before_breadcrumb"] is obs.sentry_before_breadcrumb


def test_sentry_reel_evenement_masque_de_bout_en_bout():
    """Avec le vrai SDK (installé en prod) et un transport local : rien ne sort du process."""
    sentry_sdk = pytest.importorskip("sentry_sdk")
    from sentry_sdk.transport import Transport
    from app.core.observability import sentry_before_breadcrumb, sentry_before_send
    envelopes = []

    class _Local(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    sentry_sdk.init(dsn="https://cle@o0.ingest.invalid/1", transport=_Local,
                    default_integrations=False, auto_enabling_integrations=False,
                    send_default_pii=False, include_local_variables=False,
                    before_send=sentry_before_send, before_breadcrumb=sentry_before_breadcrumb)
    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.add_breadcrumb(category="log", message="GET /api/invite/TOKZ_998/journal",
                                 data={"url": "https://x.fr/app?verify=" + _JWT})
            scope.set_extra("destinataire", "lea.martin@exemple.fr")
            try:
                raise ValueError("envoi impossible à lea.martin@exemple.fr (/invite/TOKZ_998)")
            except ValueError:
                sentry_sdk.capture_exception()
        sentry_sdk.flush()
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)
    events = [e.get_event() for e in envelopes if e.get_event()]
    assert events, "un évènement devait être produit"
    dump = json.dumps(events, ensure_ascii=False, default=str)
    assert "lea.martin@" not in dump and "TOKZ_998" not in dump and "eyJ" not in dump
    assert "l***@exemple.fr" in dump


def test_politique_de_confidentialite_ligne_sentry_inchangee_et_tenue():
    """La ligne Sentry (§6) redevient exacte grâce au masquage : on ne la modifie pas, mais
    elle doit rester alignée entre la source Markdown et la page servie."""
    import pathlib
    ligne = "journaux techniques, identifiants techniques, adresse IP"
    assert ligne in pathlib.Path("app/static/legal/confidentialite.html").read_text(encoding="utf-8")
    assert ligne in pathlib.Path("docs/legal/politique-confidentialite.md").read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 3. PDF reportlab : valeurs dynamiques échappées
# ══════════════════════════════════════════════════════════════════════════════
def _pdf_text(pdf: bytes) -> str:
    assert pdf[:4] == b"%PDF"
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _no_links(pdf: bytes) -> bool:
    return all(not p.get("/Annots") for p in PdfReader(io.BytesIO(pdf)).pages)


_COMPANY = {"name": HOSTILE, "siret": "1 & 2", "city": "<Brest>", "representant_legal": "M. <Le Gall>",
            "address": "1 rue <A>", "postal_code": "29000", "email": "a&b@exemple.fr",
            "qualifications": [{"name": HOSTILE, "detail": "<i>Qualibat", "expiration": "2027"}],
            "references": [{"name": "R&D <b", "client": "<Mairie>", "value": 1000, "year": 2024}]}
_PROJECT = {"name": HOSTILE, "client": "Ville de <X> & Co", "reference": "R&D"}


def test_pdf_dume_nom_hostile_valide_et_lisible():
    from app.services.cerfa import generate_dume
    pdf = generate_dume(_COMPANY, _PROJECT)
    txt = _pdf_text(pdf)
    assert HOSTILE in txt and "Ville de <X> & Co" in txt and "R&D <b" in txt


def test_pdf_dume_pas_d_injection_de_lien():
    from app.services.cerfa import generate_dume
    c = dict(_COMPANY, name='X <a href="https://piege.example">payez ici</a>')
    pdf = generate_dume(c, _PROJECT)
    assert _no_links(pdf)
    assert '<a href="https://piege.example">' in _pdf_text(pdf)


def test_pdf_autres_generateurs_nom_hostile():
    from app.services.cerfa import _fallback, generate_attestation_honneur, generate_national_form
    from app.services.consortium_report import generate_consortium_report_pdf
    from app.services.dpgf import generate_dpgf_pdf
    pdfs = [
        _fallback(HOSTILE, _COMPANY, _PROJECT),
        generate_attestation_honneur(_COMPANY, _PROJECT),
        generate_national_form(_COMPANY, _PROJECT, {"form_name": HOSTILE, "sections": [
            {"title": "<S>", "fields": [{"label": "Nom & raison", "source": "company.name"}]}]}),
        generate_dpgf_pdf({"lignes": [{"tache": HOSTILE, "phase": "<p>", "jours": 2, "tarif": 500,
                                       "montant": 1000}], "total_ht": 1000,
                           "rates_used": [{"label": HOSTILE, "rate": 500}]}, HOSTILE, HOSTILE),
        generate_consortium_report_pdf(HOSTILE, HOSTILE,
                                       {"readiness": {"pct": 60, "submitted": 1, "invited": 2, "lots": 1,
                                                      "missing": ["Kbis de " + HOSTILE]},
                                        "partners": [{"company": HOSTILE, "status": "submitted",
                                                      "lot": "<b>lot</b>"}],
                                        "lots": [{"lot": HOSTILE, "partners": [HOSTILE]}]},
                                       [{"company_name": HOSTILE, "status": "submitted", "lot": "A&B",
                                         "memoire_paragraph": HOSTILE}]),
    ]
    for pdf in pdfs:
        assert HOSTILE in _pdf_text(pdf)


def test_pdf_compte_rendu_balisage_voulu_rendu():
    """Le gras et les sauts de ligne voulus ne s'affichent plus en toutes lettres."""
    from app.services.consortium_report import generate_consortium_report_pdf
    txt = _pdf_text(generate_consortium_report_pdf(
        "Marché X", "M", {"readiness": {"pct": 90, "submitted": 2, "invited": 2, "lots": 1}}, []))
    assert "<b>" not in txt and "<br/>" not in txt and "<font" not in txt
    assert "90%" in txt and "2/2 partenaire(s) ont contribué" in txt


def test_pdf_dume_via_l_api(client, auth):
    h = auth["headers"]
    r = client.put("/api/company/", headers=h, json={"name": HOSTILE, "city": "Quimper & <Brest>"})
    assert r.status_code == 200, r.text
    pid = client.post("/api/projects/", headers=h, json={"name": "Voirie <lot 1> & réseaux"}).json()["id"]
    r = client.post(f"/api/cerfa/{pid}/dume", headers=h)
    assert r.status_code == 200, r.text
    txt = _pdf_text(r.content)
    assert HOSTILE in txt and "Voirie <lot 1> & réseaux" in txt


# ══════════════════════════════════════════════════════════════════════════════
# 4. Coffre-fort : type MIME dérivé de l'extension
# ══════════════════════════════════════════════════════════════════════════════
from app.core.mime import download_name, mime_for, storage_content_type  # noqa: E402

PDF = b"%PDF-1.4\n<html><script>alert(document.domain)</script></html>"


def test_table_mime_fixe():
    assert mime_for("x.pdf") == mime_for("X.PDF") == "application/pdf"
    assert mime_for("a.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert mime_for("a.png") == "image/png" and mime_for("a.jpg") == mime_for("a.jpeg") == "image/jpeg"
    for dangerous in ("a.html", "a.htm", "a.svg", "a.xhtml", "a.js", "a", "a.pdf.html"):
        assert mime_for(dangerous) == "application/octet-stream", dangerous
    assert download_name("facture.html", "u/abc.pdf") == "facture.html.pdf"
    assert download_name("Kbis", "u/abc.pdf") == "Kbis.pdf"
    assert download_name("Kbis.PDF", "u/abc.pdf") == "Kbis.PDF"


def _upload(client, h, filename, declared, data=PDF):
    r = client.post("/api/documents/", headers=h, files={"file": (filename, io.BytesIO(data), declared)},
                    data={"category": "autre"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_coffre_pdf_declare_html_servi_en_pdf(client, auth):
    h = auth["headers"]
    doc_id = _upload(client, h, "x.pdf", "text/html")
    listed = {d["id"]: d for d in client.get("/api/documents/", headers=h).json()}
    assert listed[doc_id]["mime_type"] == "application/pdf"
    r = client.get(f"/api/documents/{doc_id}/download", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment")


def test_coffre_remplacement_et_texte_jamais_inline(client, auth):
    h = auth["headers"]
    doc_id = _upload(client, h, "notes.txt", "text/html", data=b"<script>alert(1)</script>")
    r = client.get(f"/api/documents/{doc_id}/download", headers=h)
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"
    r = client.put(f"/api/documents/{doc_id}/replace", headers=h,
                   files={"file": ("v2.pdf", io.BytesIO(PDF), "image/svg+xml")})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    r = client.get(f"/api/documents/{new_id}/download", headers=h)
    assert r.headers["content-type"] == "application/pdf"


def test_coffre_ancienne_ligne_au_type_client_reste_neutralisee(client, auth):
    """Lignes créées avant le correctif : le type stocké (annoncé par le client) est ignoré."""
    from app.core.database import SessionLocal
    from app.models import Document, User
    from app.services.storage import get_storage
    key_html = f"legacy/{uuid.uuid4().hex}.html"           # ex. DCE importé « page.html »
    get_storage().save(key_html, b"<script>alert(1)</script>", "text/html")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        d = Document(user_id=u.id, name="page.html", category="autre", file_key=key_html,
                     file_size=25, mime_type="text/html")
        db.add(d)
        db.commit()
        doc_id = d.id
    finally:
        db.close()
    r = client.get(f"/api/documents/{doc_id}/download", headers=auth["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_piece_de_co_traitance_type_derive(client, auth):
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={
        "name": "AO pièces", "deadline": (date.today() + timedelta(days=20)).isoformat()}).json()["id"]
    inv = client.post(f"/api/projects/{pid}/invites", headers=h,
                      json={"recipient": "", "company_name": "Partenaire"})
    assert inv.status_code == 200, inv.text
    token = inv.json()["token"]
    up = client.post(f"/api/invite/{token}/contribution/piece",
                     files={"file": ("kbis.pdf", io.BytesIO(PDF), "text/html")})
    assert up.status_code == 200, up.text
    piece_id = up.json()["id"]
    for url, kw in ((f"/api/invite/{token}/contribution/piece/{piece_id}", {}),
                    (f"/api/projects/{pid}/contribution-pieces/{piece_id}", {"headers": h})):
        r = client.get(url, **kw)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-disposition"].startswith("attachment")


class _FakeS3:
    def __init__(self):
        self.put = []
        self.signed = []

    def put_object(self, **kw):
        self.put.append(kw)

    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        self.signed.append(Params)
        return "https://stockage.invalid/objet"


def _s3():
    from app.services.storage import S3Storage
    st = S3Storage.__new__(S3Storage)          # sans boto3 ni réseau
    st.s3, st.bucket = _FakeS3(), "seau-test"
    return st


def test_s3_content_type_pose_a_l_envoi_est_derive():
    st = _s3()
    st.save("u/a.pdf", b"x", "text/html")
    st.save("u/b.html", b"x", "text/html")
    st.save("u/c.svg", b"x", "image/svg+xml")
    st.save("backups/adjugo-1.json.gz", b"x", "application/gzip")     # fichier serveur conservé
    assert [p["ContentType"] for p in st.s3.put] == [
        "application/pdf", "application/octet-stream", "application/octet-stream", "application/gzip"]


def test_s3_url_signee_impose_type_et_telechargement():
    st = _s3()
    st.url("u/a.pdf", filename="Kbis.pdf")
    st.url("u/b.docx", filename="Mémoire — v2.docx")
    st.url("u/c.html", filename="page.html")
    pdf, docx, html = st.s3.signed
    assert pdf["ResponseContentType"] == "application/pdf" and "ResponseContentDisposition" not in pdf
    assert docx["ResponseContentType"].endswith("wordprocessingml.document")
    assert docx["ResponseContentDisposition"].startswith("attachment")
    assert html["ResponseContentType"] == "application/octet-stream"
    assert html["ResponseContentDisposition"].startswith("attachment")
    assert storage_content_type("u/x.pdf", "text/html") == "application/pdf"
