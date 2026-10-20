"""Lien privé de démonstration (https://adjugo.pro/demo#<clé>, docs/DEMO_LIEN_PRIVE.md).

  • clé absente ou trop courte (DEMO_LIEN_CLE < 32 caractères) : lien fermé, 404 partout ;
  • mauvaise clé, clé dans l'adresse au lieu du corps : 404 (rien ne révèle le lien) ;
  • bonne clé : session démo entreprises ET session démo collectivités, garde-fous intacts ;
  • clé changée ou retirée : toutes les sessions ouvertes avec l'ancienne clé refusées (401) ;
  • DEMO_PUBLIC=1 inchangé ;
  • la clé n'apparaît dans aucun journal, aucune réponse, aucun évènement Sentry ;
  • page /demo : noindex, mention « fictives », clé lue dans le fragment puis effacée ;
  • aucun lien vers /demo et aucun bouton démo sur les pages publiques.

La clé est générée à chaque exécution (jamais écrite dans le dépôt).
"""
import base64
import json
import logging
import pathlib
import re
import secrets

import pytest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"
AUTH = "/api/auth/demo"
ACH = "/api/acheteur/demo"
VERIF = "/api/auth/demo/lien"


def _cle() -> str:
    # Même forme que la commande de la doc (openssl rand -base64 33 | tr '+/' '-_' | tr -d '=').
    return secrets.token_urlsafe(33)


def _claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def lien(monkeypatch):
    """Démo publique FERMÉE (comme en production) et lien privé ouvert avec une clé neuve."""
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    cle = _cle()
    monkeypatch.setenv("DEMO_LIEN_CLE", cle)
    return cle


def _ouvrir(client, cle):
    pme = client.post(AUTH, json={"cle": cle})
    ach = client.post(ACH, json={"cle": cle})
    assert pme.status_code == 200, pme.text
    assert ach.status_code == 200, ach.text
    return pme.json()["access_token"], ach.json()["access_token"]


# ── Lien fermé ────────────────────────────────────────────────────────────────────────
def test_cle_absente_lien_ferme(client, monkeypatch):
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    monkeypatch.delenv("DEMO_LIEN_CLE", raising=False)
    for route in (AUTH, ACH, VERIF):
        assert client.post(route).status_code == 404
        assert client.post(route, json={"cle": ""}).status_code == 404
        assert client.post(route, json={"cle": _cle()}).status_code == 404


def test_cle_trop_courte_ignoree(client, monkeypatch):
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    courte = _cle()[:31]
    monkeypatch.setenv("DEMO_LIEN_CLE", courte)
    for route in (AUTH, ACH, VERIF):
        r = client.post(route, json={"cle": courte})
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    # Espaces autour : la longueur utile reste < 32.
    monkeypatch.setenv("DEMO_LIEN_CLE", "  " + courte + "  ")
    assert client.post(AUTH, json={"cle": courte}).status_code == 404


def test_mauvaise_cle_404(client, lien):
    autres = ["", " ", lien[:-1], lien + "x", lien.swapcase(), _cle(), "é" * 40]
    for route in (AUTH, ACH, VERIF):
        assert client.post(route).status_code == 404
        for c in autres:
            r = client.post(route, json={"cle": c})
            # Même réponse qu'une route inexistante : rien ne révèle l'existence du lien.
            assert r.status_code == 404 and r.json() == {"detail": "Not Found"}, (route, c)


def test_cle_hors_du_corps_refusee(client, lien):
    """La clé n'est lue que dans le corps : ni l'adresse (journaux d'accès, Referer), ni un en-tête."""
    for route in (AUTH, ACH, VERIF):
        assert client.post(f"{route}?cle={lien}").status_code == 404
        assert client.post(route, headers={"X-Demo-Cle": lien}).status_code == 404


def test_clef_d_un_autre_type_refusee(client, lien):
    for route in (AUTH, ACH, VERIF):
        assert client.post(route, json={"cle": ["x"]}).status_code in (404, 422)
        assert client.post(route, json={"cle": "x" * 300}).status_code in (404, 422)


# ── Bonne clé ─────────────────────────────────────────────────────────────────────────
def test_bonne_cle_verification(client, lien):
    r = client.post(VERIF, json={"cle": lien})
    assert r.status_code == 200 and r.json() == {"ok": True}
    # Espaces autour de la clé (copier-coller) : tolérés.
    assert client.post(VERIF, json={"cle": f"  {lien}\n"}).status_code == 200


def test_bonne_cle_session_entreprises(client, lien):
    pme, _ = _ouvrir(client, lien)
    me = client.get("/api/auth/me", headers=_h(pme))
    assert me.status_code == 200 and me.json()["email"] == "demo@adjugo.fr"
    c = _claims(pme)
    assert re.fullmatch(r"[0-9a-f]{16}", c["dl"]), c
    assert lien not in json.dumps(c)


def test_bonne_cle_session_collectivites(client, lien):
    _, ach = _ouvrir(client, lien)
    me = client.get("/api/acheteur/me", headers=_h(ach))
    assert me.status_code == 200 and me.json()["demo"] is True
    c = _claims(ach)
    assert c["typ"] == "acheteur" and re.fullmatch(r"[0-9a-f]{16}", c["dl"])
    assert lien not in json.dumps(c)
    # Le cloisonnement des deux espaces tient toujours.
    pme, _ = _ouvrir(client, lien)
    assert client.get("/api/acheteur/me", headers=_h(pme)).status_code == 401
    assert client.get("/api/auth/me", headers=_h(ach)).status_code == 401


def test_garde_fous_de_la_demo_intacts(client, lien):
    pme, ach = _ouvrir(client, lien)
    # Middleware « lecture guidée » : emails, IA payante, compte.
    r = client.post("/api/org/invite", headers=_h(pme), json={"email": "x@exemple.fr"})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    assert client.post("/api/sourcing/ask", headers=_h(pme), json={"question": "?"}).status_code == 403
    assert client.post("/api/rgpd/delete-account", headers=_h(pme), json={}).status_code == 403
    # Défense en profondeur : consume_analysis refuse tout appel IA du compte démo.
    from app.core.database import SessionLocal
    from app.core.quota import consume_analysis
    from app.models import User
    from fastapi import HTTPException
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "demo@adjugo.fr").first()
        with pytest.raises(HTTPException) as e:
            consume_analysis(u, db)
        assert e.value.status_code == 403
    finally:
        db.close()
    # Espace collectivités : le compte de démonstration reste en lecture seule.
    r = client.post("/api/acheteur/dce", headers=_h(ach), json={"objet": "Test", "payload": {"objet": "Test"}})
    assert r.status_code == 403


# ── Révocation ────────────────────────────────────────────────────────────────────────
def test_cle_changee_coupe_les_sessions(client, lien, monkeypatch):
    pme, ach = _ouvrir(client, lien)
    nouvelle = _cle()
    monkeypatch.setenv("DEMO_LIEN_CLE", nouvelle)
    r = client.get("/api/auth/me", headers=_h(pme))
    assert r.status_code == 401 and r.json()["detail"] == "Ce lien de démonstration n'est plus valide."
    r = client.get("/api/acheteur/me", headers=_h(ach))
    assert r.status_code == 401 and r.json()["detail"] == "Ce lien de démonstration n'est plus valide."
    # Le middleware ne laisse rien passer non plus (401, ni 403 ni 200).
    assert client.post("/api/org/invite", headers=_h(pme), json={"email": "x@exemple.fr"}).status_code == 401
    # L'ancienne clé n'ouvre plus rien ; la nouvelle, si.
    for route in (AUTH, ACH, VERIF):
        assert client.post(route, json={"cle": lien}).status_code == 404
    pme2, ach2 = _ouvrir(client, nouvelle)
    assert client.get("/api/auth/me", headers=_h(pme2)).status_code == 200
    assert client.get("/api/acheteur/me", headers=_h(ach2)).status_code == 200


def test_cle_retiree_coupe_les_sessions(client, lien, monkeypatch):
    pme, ach = _ouvrir(client, lien)
    monkeypatch.delenv("DEMO_LIEN_CLE")
    assert client.get("/api/auth/me", headers=_h(pme)).status_code == 401
    assert client.get("/api/acheteur/me", headers=_h(ach)).status_code == 401
    # Clé raccourcie sous le minimum : même effet (lien fermé).
    monkeypatch.setenv("DEMO_LIEN_CLE", lien[:31])
    assert client.get("/api/auth/me", headers=_h(pme)).status_code == 401


def test_session_du_lien_coupee_meme_si_la_demo_publique_est_rouverte(client, lien, monkeypatch):
    pme, ach = _ouvrir(client, lien)
    monkeypatch.setenv("DEMO_PUBLIC", "1")
    monkeypatch.setenv("DEMO_LIEN_CLE", _cle())
    assert client.get("/api/auth/me", headers=_h(pme)).status_code == 401
    assert client.get("/api/acheteur/me", headers=_h(ach)).status_code == 401


def test_empreinte_forgee_refusee(client, lien):
    """Une revendication « dl » qui n'est pas l'empreinte de la clé actuelle ne vaut rien."""
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.models import User
    pme, _ = _ouvrir(client, lien)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "demo@adjugo.fr").first()
        faux = create_access_token(data={"sub": str(u.id), "tv": int(u.token_version or 0), "dl": "0" * 16})
    finally:
        db.close()
    assert client.get("/api/auth/me", headers=_h(faux)).status_code == 401
    assert client.get("/api/auth/me", headers=_h(pme)).status_code == 200


def test_portillon_dce_respecte_la_revocation(client, lien, monkeypatch):
    """/api/dce/* : une session collectivités du lien vaut accès tant que la clé n'a pas changé."""
    monkeypatch.setenv("DCE_ACCESS_CODE", secrets.token_hex(8))
    _, ach = _ouvrir(client, lien)
    corps = {"montant_estime": 30000, "type_marche": "services"}
    assert client.post("/api/dce/preview-procedure", headers=_h(ach), json=corps).status_code == 200
    monkeypatch.setenv("DEMO_LIEN_CLE", _cle())
    assert client.post("/api/dce/preview-procedure", headers=_h(ach), json=corps).status_code == 401


# ── Démo publique : comportement inchangé ─────────────────────────────────────────────
def test_demo_publique_inchangee(client, monkeypatch):
    monkeypatch.setenv("DEMO_PUBLIC", "1")
    monkeypatch.delenv("DEMO_LIEN_CLE", raising=False)
    pme = client.post(AUTH)
    ach = client.post(ACH)
    assert pme.status_code == 200 and ach.status_code == 200
    tp, ta = pme.json()["access_token"], ach.json()["access_token"]
    assert "dl" not in _claims(tp) and "dl" not in _claims(ta)
    # Une clé posée ensuite (ou changée) ne touche pas les sessions de la démo publique.
    monkeypatch.setenv("DEMO_LIEN_CLE", _cle())
    assert client.get("/api/auth/me", headers=_h(tp)).status_code == 200
    assert client.get("/api/acheteur/me", headers=_h(ta)).status_code == 200
    # Une mauvaise clé avec la démo publique ouverte : session publique (comme sans clé).
    r = client.post(AUTH, json={"cle": "pas-la-bonne"})
    assert r.status_code == 200 and "dl" not in _claims(r.json()["access_token"])
    # La vérification du lien, elle, ne dépend que de la clé.
    assert client.post(VERIF, json={"cle": "pas-la-bonne"}).status_code == 404
    # Fermeture de la démo publique : ses sessions sont refusées, comme avant.
    monkeypatch.delenv("DEMO_PUBLIC")
    assert client.get("/api/auth/me", headers=_h(tp)).status_code == 401
    assert client.get("/api/acheteur/me", headers=_h(ta)).status_code == 401


def test_connexion_par_mot_de_passe_du_compte_demo_toujours_refusee(client, lien):
    """Le compte démo a un mot de passe connu (seed) : il n'ouvre pas une session acceptée."""
    from app.services.demo_seed import DEMO_PASSWORD
    r = client.post("/api/auth/login", json={"email": "demo@adjugo.fr", "password": DEMO_PASSWORD})
    if r.status_code == 200:
        assert client.get("/api/auth/me", headers=_h(r.json()["access_token"])).status_code == 401


# ── La clé ne fuit nulle part ─────────────────────────────────────────────────────────
def test_la_cle_n_apparait_dans_aucun_journal(client, lien, caplog):
    caplog.set_level(logging.DEBUG)
    reponses = [client.post(VERIF, json={"cle": lien}), client.post(AUTH, json={"cle": lien}),
                client.post(ACH, json={"cle": lien}), client.post(AUTH, json={"cle": lien + "x"}),
                client.get("/demo")]
    pme = reponses[1].json()["access_token"]
    reponses.append(client.post("/api/org/invite", headers=_h(pme), json={"email": "x@exemple.fr"}))
    assert caplog.records, "aucun journal capturé : le test ne prouverait rien"
    assert lien not in caplog.text
    for rec in caplog.records:
        assert lien not in rec.getMessage()
    for r in reponses:
        assert lien not in r.text


def test_journaux_et_sentry_masquent_la_cle_meme_recopiee(lien):
    from app.core.observability import sentry_before_send
    from app.core.redact import RedactingFilter, mask_text
    assert lien not in mask_text(f"corps reçu : {{'cle': '{lien}'}}")
    rec = logging.LogRecord("adjugo", logging.WARNING, __file__, 1, "clé %s", (lien,), None)
    RedactingFilter().filter(rec)
    assert lien not in rec.getMessage()
    ev = {"request": {"url": "https://adjugo.pro/api/auth/demo", "method": "POST",
                      "data": {"cle": lien}, "headers": {"Content-Type": "application/json"}},
          "message": f"échec {lien}", "extra": {"corps": {"cle": lien}},
          "breadcrumbs": {"values": [{"message": lien}]}}
    out = sentry_before_send(ev)
    assert out is not None and lien not in json.dumps(out, ensure_ascii=False)
    assert "data" not in out["request"]       # le corps des requêtes ne part jamais chez Sentry


def test_sentry_ne_recoit_jamais_le_corps():
    import inspect
    from app.core import observability
    src = inspect.getsource(observability.init_sentry)
    assert 'max_request_body_size="never"' in src and "send_default_pii=False" in src


# ── Limite de débit ───────────────────────────────────────────────────────────────────
def test_limite_de_debit(client, lien):
    from app.core.ratelimit import limiter
    limiter.enabled = True
    try:
        codes = [client.post(VERIF, json={"cle": "mauvaise"}).status_code for _ in range(62)]
        assert 429 in codes, codes
        codes = [client.post(AUTH, json={"cle": "mauvaise"}).status_code for _ in range(32)]
        assert 429 in codes, codes
        codes = [client.post(ACH, json={"cle": "mauvaise"}).status_code for _ in range(32)]
        assert 429 in codes, codes
    finally:
        limiter.enabled = False
        try:
            limiter.reset()
        except Exception:
            pass


# ── Page /demo ────────────────────────────────────────────────────────────────────────
def test_page_demo(client):
    r = client.get("/demo")
    assert r.status_code == 200
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert "no-store" in r.headers.get("cache-control", "")
    s = r.text
    assert '<meta name="robots" content="noindex, nofollow">' in s
    assert '<meta name="referrer" content="no-referrer">' in s
    assert "Démonstration : entreprise et données fictives" in s
    assert "Espace entreprises" in s and "Espace collectivités" in s
    assert "Ce lien de démonstration n'est plus valide." in s and 'href="/demande-acces"' in s
    # Clé lue dans le fragment, effacée de la barre d'adresse, envoyée dans le corps d'un POST.
    assert "location.hash" in s and "history.replaceState" in s
    assert 'JSON.stringify({ cle: cle })' in s and 'method: "POST"' in s
    for route in (AUTH, ACH, VERIF):
        assert f'"{route}"' in s
    # Aucun script ni style tiers, aucun émoji.
    assert not re.search(r"<script[^>]+src=", s)
    assert "https://" not in s
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", s)


def test_aucun_lien_vers_demo_ni_bouton_demo_sur_le_site():
    # Attribut href (pas « location.href = "/demo" », le renvoi d'une session du lien refusée).
    lien_demo = re.compile(r"""(?<![.\w])href\s*=\s*["'](?:https?://[^"'/]*)?/demo(?:[#?/"'])""", re.I)
    for f in sorted(STATIC.rglob("*.html")):
        if f.name == "demo.html":
            continue
        s = f.read_text(encoding="utf-8")
        assert not lien_demo.search(s), f
    for name in ("landing.html", "acheteur-landing.html", "app.html", "acheteur.html", "demande-acces.html"):
        s = (STATIC / name).read_text(encoding="utf-8")
        assert "Voir la démo" not in s and "Découvrir avec la démo" not in s, name
        assert "/api/auth/demo" not in s and "/api/acheteur/demo" not in s, name
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "/api/auth/demo" not in js and "demo=1" not in js


def test_retour_sur_demo_quand_la_session_du_lien_est_refusee():
    """Session du lien refusée (401) : le logiciel et l'espace collectivités renvoient sur /demo."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function jetonDemoLien(" in js and "sessionPerdue()" in js
    assert 'atlPurgeDrafts(true); window.location.href = "/demo";' in js
    ach = (STATIC / "acheteur.html").read_text(encoding="utf-8")
    assert "function demoLien(" in ach and 'location.href="/demo"' in ach


def test_doc_du_lien_prive():
    doc = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "DEMO_LIEN_PRIVE.md").read_text(encoding="utf-8")
    assert "openssl rand -base64 33 | tr '+/' '-_' | tr -d '='" in doc
    assert "DEMO_LIEN_CLE" in doc and "https://adjugo.pro/demo#" in doc
    assert "consortium" not in doc.lower()


# ── Fin de session : « terminée » (rouvrir le lien) ou « plus valide » (clé changée) ───────────────
PERIME = "Ce lien de démonstration n'est plus valide."


def _node(script: str, *args) -> dict:
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    out = subprocess.run([node, "-e", script, *args], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_session_du_lien_expiree_ne_se_dit_pas_perimee(client, lien):
    """Contrat sur lequel s'appuient le logiciel et l'espace collectivités : une session du lien arrivée
    au bout de ses 12 heures (clé inchangée) est refusée SANS le détail « plus valide », réservé à une
    clé changée ou retirée."""
    from datetime import timedelta
    from app.core.security import create_access_token
    pme, ach = _ouvrir(client, lien)
    assert client.post(VERIF, json={"cle": lien}).status_code == 200          # le lien vaut toujours
    for tok, url in ((pme, "/api/auth/me"), (ach, "/api/acheteur/me")):
        c = {k: v for k, v in _claims(tok).items() if k != "exp"}
        assert c.get("dl")
        expire = create_access_token(c, expires_delta=timedelta(seconds=-5))
        r = client.get(url, headers=_h(expire))
        assert r.status_code == 401 and r.json()["detail"] != PERIME, (url, r.json())


_DEMO_JS = """
const [hash, fin] = JSON.parse(process.argv[1]);
const els = {}, store = {}, appels = [];
function el(id) {
  return els[id] || (els[id] = {id, hidden: false, focused: false, textContent: "", disabled: false,
    focus() { this.focused = true; }, addEventListener() {}, querySelector() { return null; },
    setAttribute() {}, getAttribute() { return null; }, replaceWith() {}});
}
global.document = {getElementById: el, querySelectorAll: () => [], addEventListener() {}, createElement: () => el("x")};
global.window = {addEventListener() {}};
global.sessionStorage = {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; }};
global.localStorage = {setItem() {}};
if (fin) store.adjugo_demo_fin = fin;
global.location = {hash, pathname: "/demo", assign() {}};
global.history = {state: null, replaceState(st) { this.state = st; }};
global.fetch = (url, opt) => { appels.push([url, JSON.parse(opt.body).cle]); return new Promise(() => {}); };
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const visibles = ["verif", "choix", "incomplet", "invalide", "terminee", "erreur"].filter(k => !el(k).hidden);
process.stdout.write(JSON.stringify({visibles, appels, fin: store.adjugo_demo_fin || null,
  focus: visibles.filter(k => el(k).focused)}));
"""


def _page_demo(tmp_path, hash_: str, fin):
    page = (STATIC / "demo.html").read_text(encoding="utf-8")
    script = re.search(r"<script>\n(.*?)\n</script>", page, re.S).group(1)
    f = tmp_path / "demo_page.js"
    f.write_text(script, encoding="utf-8")
    return _node(_DEMO_JS, json.dumps([hash_, fin]), str(f))


def test_page_demo_session_terminee_ou_lien_perime(tmp_path):
    """/demo sans clé : « terminée » (rouvrir le lien) quand le logiciel y renvoie une session du lien
    simplement terminée ; « plus valide » quand la clé a été changée (« perime ») ; sinon « lien
    incomplet » (clé manquante après le #). Avec une clé : nouvelle visite, la marque est effacée."""
    r = _page_demo(tmp_path, "", "terminee")
    assert r["visibles"] == ["terminee"] and r["focus"] == ["terminee"] and r["appels"] == []
    assert r["fin"] == "terminee"                       # rechargement : même message
    r = _page_demo(tmp_path, "", "perime")
    assert r["visibles"] == ["invalide"] and r["appels"] == []
    for fin in (None, "autre"):
        r = _page_demo(tmp_path, "", fin)
        assert r["visibles"] == ["incomplet"] and r["focus"] == ["incomplet"] and r["appels"] == [], fin
    cle = "k" * 44
    r = _page_demo(tmp_path, "#" + cle, "terminee")
    assert r["visibles"] == ["verif"] and r["appels"] == [[VERIF, cle]] and r["fin"] is None
    page = (STATIC / "demo.html").read_text(encoding="utf-8")
    carte = re.search(r'<section id="terminee".*?</section>', page, re.S).group(0)
    assert "Votre session de démonstration est terminée." in carte and "Rouvrez le lien" in carte
    assert 'class="tip"' in carte and "/demande-acces" not in carte
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", carte)
    # Commentaire juste : la clé quitte la barre d'adresse, pas l'historique du navigateur.
    assert "reste en revanche dans l'HISTORIQUE du navigateur" in page


def _methode(js: str, nom: str) -> str:
    m = re.search(r"\n    " + nom + r"\((\w*)\) \{\n(.*?)\n    \},\n", js, re.S)
    assert m, nom
    return f"function {nom}({m.group(1)}) {{\n{m.group(2)}\n}}"


def test_logiciel_transmet_la_raison_du_refus_a_la_page_demo():
    """sessionPerdue(detail) : « perime » seulement sur le détail exact du serveur, sinon « terminee » ;
    une session ordinaire garde la déconnexion habituelle. Chaque 401 transmet le détail reçu."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    const = re.search(r'\nconst DEMO_LIEN_PERIME = "[^"]+";', js).group(0)
    jeton = re.search(r"\nfunction jetonDemoLien\(t\) \{\n.*?\n\}\n", js, re.S).group(0)
    script = const + jeton + _methode(js, "sessionPerdue") + """
const store = {}, res = [];
global.sessionStorage = {setItem: (k, v) => { store[k] = v; }};
global.localStorage = {removeItem() {}};
global.window = {location: {href: "/app"}};
function atlPurgeDrafts() {}
const b64 = o => Buffer.from(JSON.stringify(o)).toString("base64url");
const lien = "e." + b64({sub: "1", dl: "abc"}) + ".s", ordinaire = "e." + b64({sub: "1"}) + ".s";
for (const [token, detail] of [[lien, DEMO_LIEN_PERIME], [lien, "Token invalide ou expire"], [lien, undefined],
                               [ordinaire, DEMO_LIEN_PERIME]]) {
  delete store.adjugo_demo_fin; window.location.href = "/app"; let sortie = false;
  sessionPerdue.call({token, logout() { sortie = true; }}, detail);
  res.push([store.adjugo_demo_fin || null, window.location.href, sortie]);
}
process.stdout.write(JSON.stringify(res));
"""
    assert _node(script) == [["perime", "/demo", False], ["terminee", "/demo", False],
                             ["terminee", "/demo", False], [None, "/app", True]]
    assert const == '\nconst DEMO_LIEN_PERIME = "' + PERIME + '";'
    # api(), export, et la revérification de la confirmation d'email (vague 2b, B1 : confirmationVerifier, qui appelle
    # /api/auth/me sans la barre de progression) : chaque 401 transmet le détail reçu.
    assert js.count("this.sessionPerdue(await r.json().then(j => j && j.detail") == 3
    # Inactivité d'une heure : une session du lien revient aussi sur /demo (« terminée »).
    assert "this.sessionPerdue(); } }, 60000);" in js
    assert "_idleStale() && jetonDemoLien(this.token)) { this.sessionPerdue(); return; }" in js


def test_espace_collectivites_transmet_la_raison_du_refus():
    ach = (STATIC / "acheteur.html").read_text(encoding="utf-8")
    fin = re.search(r"\n  (function demoFin\(detail\)\{.*?)\n", ach).group(1)
    script = fin + """
const store = {};
global.sessionStorage = {setItem: (k, v) => { store[k] = v; }};
const res = [];
for (const d of [process.argv[1], "Session expirée, reconnectez-vous", "Token invalide ou expire", undefined]) {
  demoFin(d); res.push(store.adjugo_demo_fin);
}
process.stdout.write(JSON.stringify(res));
"""
    assert _node(script, PERIME) == ["perime", "terminee", "terminee", "terminee"]
    assert 'if(demoLien(ATOKEN)){demoFin(detail);setToken("");location.href="/demo";return;}' in ach
    assert "return detail401(r).then(function(d){sessionLost(d);" in ach
    assert ach.count("detail401(r).then(function(d){sessionLost(d);") == 2    # aFetch et ouverture


def test_guide_historique_mon_avis_et_donnees_fictives():
    doc = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "DEMO_LIEN_PRIVE.md").read_text(encoding="utf-8")
    # La clé reste dans l'historique : appareils personnels, sinon navigation privée, sinon changer la clé.
    assert "historique du navigateur" in doc and "fenêtre de navigation privée" in doc
    assert "changez la clé (étape 4)" in doc
    # « Mon avis » : seul message envoyé, au fondateur, signé demo@adjugo.fr.
    assert "« Mon avis »" in doc and "signé\n  demo@adjugo.fr" in doc
    assert "Aucun appel d'IA, aucun email, aucun fichier" not in doc
    # Session terminée ≠ lien plus valide.
    assert "Votre session de\ndémonstration est terminée" in doc
    # Données fictives : plus de « à remplacer », aucune collectivité réelle citée.
    assert "À remplacer" not in doc
    for nom in ("Bordeaux", "Lorient", "Toulouse", "Nice"):
        assert nom not in doc, nom
