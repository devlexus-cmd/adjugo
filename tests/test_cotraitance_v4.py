"""
Co-traitance v2 — vague 4 « Preuves, dépôt, finitions » (partie serveur).

Invariants vérifiés :
- journal vérifiable PAR LE MEMBRE : sous-chaîne recalculée (empreinte + lien au maillon
  précédent), verdict intact → altéré détecté (entrée du membre modifiée ou supprimée ; autre
  entrée du tenant modifiée), date du dernier ancrage citée, exports JSON/PDF, vérification
  hors ligne (recalcul des maillons, comparaison de deux exports), routes « Partagé avec moi » ;
- doctrine : ni IP, ni email, ni empreinte brute, ni identifiant interne dans ce que reçoit
  le membre ; rien de nouveau ne fuite côté chef de file (detail_chiffre) ni au LLM ;
- SRI : empreintes à jour (sinon échec avec la commande de régénération), attributs integrity
  sur chaque <script src="/static/…">, filet de production, route publiée, CSP inchangée ;
- DPGF de lot : pièce « dpgf_lot » (CSV/PDF/tableurs), garde-fous CSV (formules, colonnes de
  coûts/marges), visible du chef de file, jamais des autres membres, part et convention intactes ;
- étape 5 : contrôles « prêt à déposer » fiables, « Marquer déposé » (409 puis confirmation,
  journal, idempotent, annulation), démo bloquée ;
- relances : une seule alerte d'attestations par palier et par date limite (plus de doublon
  quotidien), relance de part + attestations en UN email, récapitulatif unique au chef de file,
  plus aucune relance après dépôt ;
- tableau de bord : N marchés accessibles en groupement, groupements par étape, données du
  tenant seulement ;
- migration q1r2s3t4u5v6 : chiffrage_note vidée (texte recopié dans note_au_mandataire) mais
  CONSERVÉE en base (expand/contract : le code de production la mappe encore), acceptation durable
  des invitations réseau (SQLite : base neuve, base à la révision précédente avec données, rejeu).
"""
import io
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

import pytest

from tests.test_convention_groupement import (_db, _gen, _groupement, _invite, _part, _pdf_text,
                                              _project, _put, _register, _set_company, _submit,
                                              _valider)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


@pytest.fixture(autouse=True)
def _fresh_caches():
    from app.services import journal_membre as jm
    from app.services import audit_anchor
    jm.reset_caches()
    audit_anchor.reset_cache()
    yield
    jm.reset_caches()
    audit_anchor.reset_cache()


@pytest.fixture
def no_llm(monkeypatch):
    """Tout appel au LLM pendant le test échoue bruyamment."""
    import app.services.llm as llm

    def boom(*a, **k):
        raise AssertionError("appel LLM interdit dans la vague 4")
    monkeypatch.setattr(llm, "messages_create", boom)
    monkeypatch.setattr(llm, "client", boom)


def _upload(client, token, filename, data, **form):
    return client.post(f"/api/invite/{token}/contribution/piece",
                       files={"file": (filename, io.BytesIO(data), "application/octet-stream")}, data=form)


def _audit_rows(**flt):
    from app.models import AuditLog
    db = _db()
    try:
        q = db.query(AuditLog)
        for k, v in flt.items():
            q = q.filter(getattr(AuditLog, k) == v)
        return [(r.id, r.action, r.entry_hash, r.prev_hash, r.ip, r.actor) for r in q.order_by(AuditLog.id.asc()).all()]
    finally:
        db.close()


def _scenario(client, auth):
    """Marché + 2 partenaires (Alpha soumet, Beta invité) + lectures du chef de file."""
    h = auth["headers"]
    pid = _project(client, h)
    a = _invite(client, h, pid, "Alpha SARL", recipient="alpha@secret.fr")
    b = _invite(client, h, pid, "Beta SAS", recipient="beta@secret.fr")
    ta, tb = a["token"], b["token"]
    client.get(f"/api/invite/{ta}")                                   # guest.view_project
    client.get(f"/api/invite/{ta}")
    assert _put(client, ta, company_name="Alpha SARL", lot="Lot A", prix_lot_ht=10000).status_code == 200
    _submit(client, ta)
    up = _upload(client, ta, "extrait_kbis.pdf", PDF)
    assert up.status_code == 200, up.text
    client.get(f"/api/projects/{pid}/contributions", headers=h)       # owner.view_contribution
    assert client.get(f"/api/projects/{pid}/contribution-pieces/{up.json()['id']}", headers=h).status_code == 200
    return pid, a, b


# ═══ 1. Journal vérifiable par le membre ══════════════════════════════════════════════

def test_integrite_membre_intacte_puis_alteree_detectee(client, auth, mails, no_llm):
    from app.models import AuditLog
    from app.services import journal_membre as jm
    pid, a, b = _scenario(client, auth)
    ta = a["token"]
    r = client.get(f"/api/invite/{ta}/journal/integrity")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["verdict"] == "intact" and v["perimetre"] is None, v["message"]
    assert v["schema"] == "adjugo-journal-membre-v1"
    assert v["integrity_label"] == "Journal vérifiable : toute modification ou suppression d'entrée est détectable"
    ch = v["chaine"]
    assert len(ch) >= 6 and v["entrees"]["total"] == len(ch) and v["entrees"]["verifiees"] == len(ch)
    assert all(e["statut"] == "verifiee" for e in ch)
    assert [e["n"] for e in ch] == list(range(1, len(ch) + 1))
    assert v["empreinte"] == ch[-1]["maillon"]
    assert v["journal_complet_intact"] is True and "Journal intact" in v["message"]
    actions = [e["action"] for e in ch]
    assert "owner.view_contribution" in actions and "owner.download_piece" in actions
    assert "guest.submit_contribution" in actions and "invite.created" in actions

    # Doctrine : ni IP, ni email, ni empreinte brute, ni identifiant interne.
    raw = json.dumps(v, ensure_ascii=False)
    assert "@" not in raw and "secret.fr" not in raw
    rows = _audit_rows(project_id=pid)
    for (_id, _act, eh, ph, ip, actor) in rows:
        if eh:
            assert eh not in raw
        if ph:
            assert ph not in raw
        if ip:
            assert f'"{ip}"' not in raw
    assert not any(k in e for e in ch for k in ("ip", "id", "owner_id", "invite_id", "target_id", "entry_hash", "prev_hash"))
    # Beta ne reçoit pas les entrées propres d'Alpha (seulement les événements de groupement).
    vb = client.get(f"/api/invite/{b['token']}/journal/integrity").json()
    assert vb["verdict"] == "intact"
    assert not any(e["action"] in ("owner.view_contribution", "guest.submit_contribution",
                                   "owner.download_piece") for e in vb["chaine"])

    # Altération d'UNE entrée du membre (le détail d'une consultation est réécrit en base).
    target = next(rid for (rid, act, *_r) in _audit_rows(invite_id=a["id"]) if act == "guest.submit_contribution")
    db = _db()
    try:
        row = db.get(AuditLog, target)
        row.detail = "falsifié"
        db.commit()
    finally:
        db.close()
    jm.reset_caches()
    v2 = client.get(f"/api/invite/{ta}/journal/integrity").json()
    assert v2["verdict"] == "altere" and v2["perimetre"] == "vos_entrees"
    assert v2["entrees"]["alterees"] >= 1 and v2["premiere_alteration"]["label"] == "Vous avez soumis votre part"
    assert "modifiée" in v2["message"]
    assert any(e["statut"] == "alteree" for e in v2["chaine"])
    # L'entrée concernée de Beta n'est pas la sienne : son verdict tombe au niveau « journal ».
    vb2 = client.get(f"/api/invite/{b['token']}/journal/integrity").json()
    assert vb2["verdict"] == "altere" and vb2["perimetre"] == "journal"
    assert vb2["entrees"]["alterees"] == 0 and vb2["journal_complet_intact"] is False


def test_integrite_suppression_detectee_et_exports_compares(client, auth, mails, no_llm):
    from app.models import AuditLog
    from app.services import journal_membre as jm
    pid, a, b = _scenario(client, auth)
    ta = a["token"]
    old = client.get(f"/api/invite/{ta}/journal/export?format=json")
    assert old.status_code == 200 and old.headers["content-type"].startswith("application/json")
    assert "attachment" in old.headers["content-disposition"]
    old_doc = old.json()
    assert jm.verify_export(old_doc)["ok"] is True
    # L'export est journalisé (« Vous avez exporté votre journal ») et l'export suivant PROLONGE le précédent.
    labels = [e["label"] for e in client.get(f"/api/invite/{ta}/journal").json()["entries"]]
    assert "Vous avez exporté votre journal" in labels
    new_doc = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    assert jm.verify_export(new_doc)["ok"] is True and jm.prolonge(old_doc, new_doc) is True
    assert len(new_doc["entrees"]) == len(old_doc["entrees"]) + 1

    # Un export retouché à la main ne se vérifie plus hors ligne.
    forged = json.loads(json.dumps(new_doc))
    forged["entrees"][0]["action"] = "owner.autre"
    assert jm.verify_export(forged)["ok"] is False

    # Suppression d'une entrée du membre AU MILIEU de la chaîne (la 1re consultation).
    views = [rid for (rid, act, *_r) in _audit_rows(invite_id=a["id"]) if act == "guest.view_project"]
    db = _db()
    try:
        db.delete(db.get(AuditLog, views[0]))
        db.commit()
    finally:
        db.close()
    jm.reset_caches()
    v = client.get(f"/api/invite/{ta}/journal/integrity").json()
    assert v["verdict"] == "altere" and v["perimetre"] == "vos_entrees"
    after = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    assert jm.verify_export(after)["ok"] is True          # cohérent en soi…
    assert jm.prolonge(new_doc, after) is False           # …mais ne prolonge plus l'export conservé


def test_export_pdf_et_formats(client, auth, mails, no_llm):
    pid, a, b = _scenario(client, auth)
    r = client.get(f"/api/invite/{a['token']}/journal/export?format=pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert r.headers["content-type"].startswith("application/pdf")
    text = _pdf_text(r.content)
    assert "Journal du groupement" in text and "Alpha SARL" in text and "Intact" in text
    assert "@" not in text and "secret.fr" not in text
    assert client.get(f"/api/invite/{a['token']}/journal/export?format=xml").status_code == 422
    # Lien révoqué : plus rien.
    h = auth["headers"]
    assert client.delete(f"/api/projects/{pid}/invites/{b['id']}", headers=h).status_code == 200
    assert client.get(f"/api/invite/{b['token']}/journal/integrity").status_code == 404
    assert client.get(f"/api/invite/{b['token']}/journal/export").status_code == 404


def test_ancrage_cite_dans_le_verdict(client, auth, mails, monkeypatch):
    from app.services import audit_anchor
    pid, a, b = _scenario(client, auth)
    rows = _audit_rows(invite_id=a["id"])
    from app.models import AuditLog
    db = _db()
    try:
        last = db.query(AuditLog).filter(AuditLog.id == rows[2][0]).first()
        oid = last.owner_id
        n = db.query(AuditLog).filter(AuditLog.owner_id == oid, AuditLog.id <= last.id,
                                      AuditLog.entry_hash != "").count()
        head = {"owner_id": oid, "last_id": last.id, "last_hash": last.entry_hash, "entries": n,
                "status": "active", "since": "2026-10-07"}
    finally:
        db.close()
    fake = {"date": "2026-10-07", "tsa": {"ok": True}, "heads": [head], "_by_owner": {oid: head}}
    monkeypatch.setattr(audit_anchor, "latest_anchor", lambda: fake)
    v = client.get(f"/api/invite/{a['token']}/journal/integrity").json()
    assert v["verdict"] == "intact", v["message"]
    assert v["ancrage"]["date_label"] == "07/10/2026" and v["ancrage"]["horodate"] is True
    assert v["ancrage"]["entrees_couvertes"] >= 1
    assert "07/10/2026" in v["message"] and "horodatée" in v["message"]
    assert any(e["couverte_par_ancrage"] for e in v["chaine"]) and not v["chaine"][-1]["couverte_par_ancrage"]


def test_partage_avec_moi_journal_integrite_export(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    ph, pemail = _register(client, company="Gamma Menuiserie")
    inv = _invite(client, h, pid, "Gamma Menuiserie", recipient=pemail)
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=ph).status_code == 200
    client.get(f"/api/invite/{inv['token']}")
    r = client.get(f"/api/shared/{pid}/journal/integrity", headers=ph)
    assert r.status_code == 200 and r.json()["verdict"] == "intact"
    assert "invite.claimed" in [e["action"] for e in r.json()["chaine"]]
    j = client.get(f"/api/shared/{pid}/journal", headers=ph).json()
    assert j["entries"] and j["integrity_label"].startswith("Journal vérifiable")
    e = client.get(f"/api/shared/{pid}/journal/export?format=json", headers=ph)
    assert e.status_code == 200 and e.json()["membre"] == "Gamma Menuiserie"
    # Un autre compte, le chef de file lui-même, ou sans session : rien.
    oh, _ = _register(client, company="Intrus SARL")
    assert client.get(f"/api/shared/{pid}/journal/integrity", headers=oh).status_code == 404
    assert client.get(f"/api/shared/{pid}/journal/integrity", headers=h).status_code == 404
    assert client.get(f"/api/shared/{pid}/journal/integrity").status_code == 401


def test_cache_integrite_borne(client, auth, mails, monkeypatch):
    """Process unique : la vérification complète du tenant ne tourne qu'une fois par TTL."""
    from app.services import audit
    pid, a, b = _scenario(client, auth)
    calls = {"n": 0}
    real = audit.verify_chain

    def counting(db, owner_id, upto_id=None):
        calls["n"] += 1
        return real(db, owner_id, upto_id)
    monkeypatch.setattr(audit, "verify_chain", counting)
    for _ in range(4):
        assert client.get(f"/api/invite/{a['token']}/journal/integrity").status_code == 200
    client.get(f"/api/invite/{b['token']}/journal/integrity")
    assert calls["n"] == 1


# ═══ 2. SRI ═══════════════════════════════════════════════════════════════════════════

def test_sri_empreintes_a_jour():
    from app.core import sri
    rep = sri.stale_report()
    assert not rep["pages"] and rep["manifeste_a_jour"], (
        f"Empreintes SRI périmées ({', '.join(rep['pages']) or 'manifeste'}). Régénérez-les : {sri.REGEN_CMD}")
    m = sri.compute_manifest()["fichiers"]
    assert {"/static/app.js", "/static/cotraitance-crypto.js", "/static/i18n.js"} <= set(m)
    assert any(k.startswith("/static/vendor/") for k in m)
    for page in sri.PAGES:
        html = open(os.path.join(sri.STATIC_DIR, page), encoding="utf-8").read()
        tags = re.findall(r"<script\b[^>]*\bsrc=\"(/static/[^\"]+)\"[^>]*>", html)
        assert tags, page
        for src in tags:
            tag = re.search(r"<script\b[^>]*\bsrc=\"" + re.escape(src) + r"\"[^>]*>", html).group(0)
            assert f'integrity="{m[src]["integrity"]}"' in tag, f"{page} : {src} sans empreinte à jour ({sri.REGEN_CMD})"


def test_sri_pages_servies_route_publiee_et_csp(client):
    from app.core import sri
    m = sri.compute_manifest()["fichiers"]
    for url in ("/app", "/invite/abc", "/acheteur", "/acheteur/app"):
        r = client.get(url)
        assert r.status_code == 200, url
        for src, info in m.items():
            if f'src="{src}"' in r.text:
                assert f'integrity="{info["integrity"]}"' in r.text, (url, src)
        assert "'unsafe-inline'" in r.headers["content-security-policy"]   # CSP inchangée (scripts en ligne)
    pub = client.get("/api/securite/empreintes-scripts").json()
    assert pub["algorithme"] == "sha384" and pub["manifeste_publie_a_jour"] is True and pub["pages_a_jour"] is True
    assert pub["fichiers"]["/static/app.js"]["integrity"] == m["/static/app.js"]["integrity"]
    assert client.get("/static/sri-manifest.json").json()["fichiers"] == m
    import base64
    import hashlib
    data = open(os.path.join(sri.STATIC_DIR, "cotraitance-crypto.js"), "rb").read()
    assert m["/static/cotraitance-crypto.js"]["integrity"] == "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()


def test_sri_filet_de_production_et_regeneration(tmp_path, monkeypatch):
    from app.core import sri
    (tmp_path / "vendor").mkdir()
    (tmp_path / "a.js").write_text("console.log(1)")
    (tmp_path / "vendor" / "lib-1.0.js").write_text("var x=1")
    page = ('<html><script src="/static/vendor/lib-1.0.js"></script>'
            '<script src="/static/a.js" integrity="sha384-PERIME" defer></script>'
            '<script>inline()</script><script src="https://ailleurs.example/x.js"></script></html>')
    (tmp_path / "p.html").write_text(page)
    monkeypatch.setattr(sri, "STATIC_DIR", str(tmp_path))
    monkeypatch.setattr(sri, "MANIFEST_PATH", str(tmp_path / "sri-manifest.json"))
    monkeypatch.setattr(sri, "PAGES", ("p.html",))
    sri._CACHE.clear()
    m = sri.compute_manifest()["fichiers"]
    logged = []
    monkeypatch.setattr(sri.logger, "error", lambda msg, *a: logged.append(msg % a))
    html = sri.page_html("p.html")
    assert f'src="/static/a.js" integrity="{m["/static/a.js"]["integrity"]}" defer' in html
    assert f'integrity="{m["/static/vendor/lib-1.0.js"]["integrity"]}"' in html
    assert "PERIME" not in html and '<script src="https://ailleurs.example/x.js">' in html
    assert any("sri_update" in m and "p.html" in m for m in logged)
    assert sri.stale_report()["pages"] == ["p.html"]
    changed = sri.regenerate()
    assert "app/static/p.html" in changed and "app/static/sri-manifest.json" in changed
    assert sri.stale_report() == {"pages": [], "manifeste_a_jour": True}
    assert sri.regenerate() == []                                   # idempotent
    assert sri.apply_integrity(html, m) == html
    # Le fichier change → la page servie suit (cache invalidé par mtime/taille).
    (tmp_path / "a.js").write_text("console.log(2)  ")
    assert sri.compute_manifest()["fichiers"]["/static/a.js"]["integrity"] in sri.page_html("p.html")
    sri._CACHE.clear()


def test_sri_script_de_regeneration_check():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "scripts/sri_update.py", "--check"], cwd=root,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


# ═══ 3. DPGF de lot ═══════════════════════════════════════════════════════════════════

CSV_OK = ("Désignation;Unité;Quantité;Prix unitaire HT;Montant HT\n"
          "Tableau électrique;u;2;1 250,00;2 500,00\n"
          "Remise commerciale;forfait;1;-150,00;-150,00\n").encode("utf-8")


def test_dpgf_lot_deposee_visible_du_chef_de_file_seulement(client, auth, mails, no_llm):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    ta, tb = invs[0]["token"], invs[1]["token"]
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer"
    r = _upload(client, ta, "dpgf.csv", CSV_OK, piece_type="dpgf_lot", expiration_date="2030-01-01")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["piece_type"] == "dpgf_lot" and p["expiration_date"] is None
    # Part toujours soumise, convention intacte (le prix de vente du lot n'a pas changé).
    assert client.get(f"/api/invite/{ta}/contribution").json()["status"] == "submitted"
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["status"] == "a_signer"
    me = client.get(f"/api/invite/{ta}/contribution").json()
    assert me["has_dpgf_lot"] is True
    # Chef de file : la pièce, le drapeau, le téléchargement (audité → journal du membre).
    own = client.get(f"/api/projects/{pid}/contributions", headers=h).json()
    mine = next(x for x in own if x["company_name"] == "Le Gall Électricité")
    assert any(x["piece_type"] == "dpgf_lot" for x in mine["pieces"]) and mine["has_dpgf_lot"] is True
    assert all("detail_chiffre" not in x for x in own) and "ciphertext" not in json.dumps(own)
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert next(x for x in ck["partners"] if x["company"] == "Le Gall Électricité")["has_dpgf_lot"] is True
    dl = client.get(f"/api/projects/{pid}/contribution-pieces/{p['id']}", headers=h)
    assert dl.status_code == 200 and dl.content == CSV_OK
    assert "attachment" in dl.headers["content-disposition"]
    labels = [e["label"] for e in client.get(f"/api/invite/{ta}/journal").json()["entries"]]
    assert any(l.startswith("Le chef de file a téléchargé votre pièce « dpgf.csv »") for l in labels)
    # Autre membre : ni la pièce, ni son nom, ni une case « DPGF » dans le coffre croisé.
    assert client.get(f"/api/invite/{tb}/contribution/piece/{p['id']}").status_code == 404
    cc = client.get(f"/api/invite/{tb}/coffre-croise").json()
    assert "dpgf.csv" not in json.dumps(cc, ensure_ascii=False) and "dpgf_lot" not in json.dumps(cc)
    # Retirer la DPGF ne repasse pas la part en brouillon.
    assert client.delete(f"/api/invite/{ta}/contribution/piece/{p['id']}").status_code == 200
    assert client.get(f"/api/invite/{ta}/contribution").json()["status"] == "submitted"
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["status"] == "a_signer"


def test_dpgf_lot_gardes_fous(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    bad_cols = "Désignation;Quantité;Coût unitaire;Marge;Prix unitaire HT\nPeinture;10;8;20 %;12\n".encode()
    r = _upload(client, t, "dpgf.csv", bad_cols, piece_type="dpgf_lot")
    assert r.status_code == 422 and "prix de vente" in r.json()["detail"]
    formula = "Désignation;Montant\nPeinture;=SOMME(B1:B9)\n".encode()
    assert _upload(client, t, "dpgf.csv", formula, piece_type="dpgf_lot").status_code == 422
    assert _upload(client, t, "dpgf.csv", "Désignation;Montant\nX;-SOMME(A1)\n".encode(),
                   piece_type="dpgf_lot").status_code == 422
    assert _upload(client, t, "dpgf.csv", "Désignation;Montant\nX;12\n".encode("utf-16"),
                   piece_type="dpgf_lot").status_code == 422
    r = _upload(client, t, "dpgf.docx", b"PK\x03\x04", piece_type="dpgf_lot")
    assert r.status_code == 422 and "CSV" in r.json()["detail"]
    # Hors DPGF, le CSV reste refusé (liste blanche générale inchangée).
    assert _upload(client, t, "notes.csv", CSV_OK).status_code == 400
    # Reconnue par le nom (et pas prise pour un RIB : « distRIBution »).
    r = _upload(client, t, "DPGF_distribution.csv", CSV_OK)
    assert r.status_code == 200 and r.json()["piece_type"] == "dpgf_lot"
    r = _upload(client, t, "DPGF_lot_peinture.pdf", PDF)
    assert r.status_code == 200 and r.json()["piece_type"] == "dpgf_lot"
    chk = client.get(f"/api/invite/{t}/contribution").json()["pieces_checklist"]
    assert "RIB" not in chk["have"]
    # Une image ne devient pas une DPGF.
    img = _upload(client, t, "photo.png", b"\x89PNG\r\n\x1a\n")
    assert img.status_code == 200
    r = client.patch(f"/api/invite/{t}/contribution/piece/{img.json()['id']}", json={"piece_type": "dpgf_lot"})
    assert r.status_code == 422
    # Type inconnu : message à jour.
    r = _upload(client, t, "x.pdf", PDF, piece_type="devis")
    assert r.status_code == 422 and "dpgf_lot" in r.json()["detail"]


# ═══ 4. Étape 5 : prêt à déposer, marquer déposé ══════════════════════════════════════

def _ready_project(client, auth, mails, far_days=200):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture", siret="12345678900011", address="1 rue du Port",
                 postal_code="56100", city="Lorient", representant_legal="Eliot Viegas")
    pid = _project(client, h)
    inv = _invite(client, h, pid, "Le Gall Électricité", recipient="legall@partenaire.fr")
    t = inv["token"]
    exp = (date.today() + timedelta(days=far_days)).isoformat()
    for fname, ptype in (("kbis.pdf", "kbis"), ("fiscale.pdf", "fiscale"), ("urssaf.pdf", "sociale"),
                         ("assurance.pdf", "assurance"), ("rib.pdf", "rib")):
        r = _upload(client, t, fname, PDF, piece_type=ptype, expiration_date=exp)
        assert r.status_code == 200, r.text
    _part(client, t, "Le Gall Électricité", "Lot 2 — Électricité", 40000)
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
               json={"forme": "solidaire", "params": {"part_mandataire_ht": 60000, "lot_mandataire": "Lot 1"}})
    return pid, inv


def test_pret_a_deposer_controles_fiables(client, auth, mails):
    h = auth["headers"]
    pid, inv = _ready_project(client, auth, mails, far_days=10)   # URSSAF… expire AVANT la date limite (J+30)
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()
    p = d["pret"]
    assert d["depose"] is False and p["pret"] is False and p["n_total"] == 4
    assert p["checks"] == {"parts_soumises": True, "attestations_ok": False,
                           "convention_signee": False, "cerfa_generes": False}
    assert any("expire avant la date limite" in m for m in p["manques"])
    assert any(m.startswith("Convention de groupement à générer") for m in p["manques"])
    assert set(p["libelles"]) == set(p["checks"])
    # Un sous-traitant en retard : avertissement, pas un manque.
    st = client.post(f"/api/projects/{pid}/invites", headers=h,
                     json={"company_name": "Sous-Traitant SARL", "role": "sous_traitant"})
    assert st.status_code == 200, st.text
    p = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert p["checks"]["parts_soumises"] is True
    assert any("Sous-Traitant SARL" in a and "sous-traitant" in a for a in p["avertissements"])
    # Un co-traitant qui n'a pas soumis sa part : manque.
    _invite(client, h, pid, "Retard Plomberie")
    p = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert p["checks"]["parts_soumises"] is False
    assert "Part de Retard Plomberie pas encore soumise" in p["manques"]
    assert "detail_chiffre" not in json.dumps(p) and "ciphertext" not in json.dumps(p)
    # Date limite inconnue : avertissement explicite.
    from app.models import Project
    db = _db()
    try:
        db.get(Project, pid).deadline = None
        db.commit()
    finally:
        db.close()
    p = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert any("Date limite du marché inconnue" in a for a in p["avertissements"])


def test_marquer_depose_confirmation_journal_idempotent_annulation(client, auth, mails):
    h = auth["headers"]
    pid, inv = _ready_project(client, auth, mails)
    t = inv["token"]
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={})
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["code"] == "pas_pret" and det["manques"] and "Confirmez" in det["message"]
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "envoye" and body["complet"] is False and body["state"]["state"] == "depose"
    assert client.get(f"/api/projects/{pid}", headers=h).json()["status"] == "envoye"
    labels = [e["label"] for e in client.get(f"/api/invite/{t}/journal").json()["entries"]]
    assert "Le chef de file a marqué le dossier comme déposé" in labels
    rows = _audit_rows(project_id=pid, action="groupement.depose")
    assert len(rows) == 1 and rows[0][2]                                   # chaîné
    # Idempotent : aucune seconde trace.
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={})
    assert r.status_code == 200 and r.json()["deja_depose"] is True
    assert len(_audit_rows(project_id=pid, action="groupement.depose")) == 1
    # Côté partenaire : étape « Déposé ».
    assert client.get(f"/api/invite/{t}").json()["for_member"]["state"]["state"] == "depose"
    # Annulation (erreur de clic) : retour au statut d'avant le marquage, tracé.
    r = client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h)
    assert r.status_code == 200 and r.json()["etait_depose"] is True and r.json()["status"] == "nouveau"   # statut d'avant le marquage
    labels = [e["label"] for e in client.get(f"/api/invite/{t}/journal").json()["entries"]]
    assert "Le chef de file a annulé le marquage « déposé »" in labels
    assert client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h).json()["etait_depose"] is False
    # Intégrité du journal du membre après ces écritures.
    assert client.get(f"/api/invite/{t}/journal/integrity").json()["verdict"] == "intact"
    # Autre entreprise : rien.
    oh, _ = _register(client, company="Concurrent SARL")
    assert client.post(f"/api/projects/{pid}/groupement/deposer", headers=oh, json={"confirmer": True}).status_code == 404
    assert client.get(f"/api/projects/{pid}/groupement/depot", headers=oh).status_code == 404


def test_marquer_depose_dossier_complet_sans_confirmation(client, auth, mails):
    h = auth["headers"]
    pid, inv = _ready_project(client, auth, mails)
    c = _gen(client, h, pid).json()
    assert _valider(client, f"/api/invite/{inv['token']}/convention/valider", c).status_code == 200
    assert _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h,
                    nom="Eliot Viegas").status_code == 200
    for dt in ("dc1", "dc2", "attri1"):
        assert client.post(f"/api/cerfa/{pid}/{dt}", headers=h).status_code == 200
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["pret"] is True and d["n_ok"] == 4 and d["manques"] == []
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["state"] == "pret_a_deposer" and st["label"] == "Prêt à déposer" and st["pret"]["pret"] is True
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h)
    assert r.status_code == 200 and r.json()["complet"] is True
    rows = _audit_rows(project_id=pid, action="groupement.depose")
    from app.models import AuditLog
    db = _db()
    try:
        assert db.get(AuditLog, rows[0][0]).detail == "dossier complet"
    finally:
        db.close()


def test_demo_garde_routes_de_depot():
    from app.core.demo_guard import blocked_action
    assert blocked_action("POST", "/api/projects/12/groupement/deposer")
    assert blocked_action("DELETE", "/api/projects/12/groupement/deposer")
    assert blocked_action("GET", "/api/projects/12/groupement/depot") is None


# ═══ 5. Relances sans doublon ═════════════════════════════════════════════════════════

def _alert_project(client, auth, days, n_partners=1, submit=False):
    h = auth["headers"]
    pid = _project(client, h, name=f"AO relances {uuid.uuid4().hex[:6]}", deadline_days=days)
    invs = []
    for i in range(n_partners):
        inv = _invite(client, h, pid, f"Partenaire {i} SARL", recipient=f"p{i}_{uuid.uuid4().hex[:5]}@partenaire.fr")
        if submit:
            assert _put(client, inv["token"], lot=f"Lot {i}", prix_lot_ht=1000).status_code == 200
            _submit(client, inv["token"])
        invs.append(inv)
    return pid, invs


def test_alertes_attestations_une_seule_par_palier(client, auth, mails, monkeypatch):
    """Le cron tourne CHAQUE JOUR : avant la vague 4, l'alerte repartait chaque jour du palier.
    On rejoue les jours J-6 → J-2 en simulant l'horloge (date du cron ET date des entrées)."""
    import app.models as models
    import app.services.alerts as al
    sent = []
    monkeypatch.setattr(al, "send_email", lambda to, subj, body: sent.append((to, subj, body)) or True)
    pid, invs = _alert_project(client, auth, days=6, n_partners=2, submit=True)
    rcpts = {i["recipient"] for i in invs}
    pname = client.get(f"/api/projects/{pid}", headers=auth["headers"]).json()["name"]
    today = date.today()

    real_utcnow = models.utcnow

    def run_on(offset):
        day = today + timedelta(days=offset)
        monkeypatch.setattr(models, "utcnow", lambda: datetime.combine(day, datetime.now().time()))
        db = _db()
        try:
            al._run_piece_expiry_alerts(db, day)
        finally:
            db.close()
            monkeypatch.setattr(models, "utcnow", real_utcnow)

    def member_mails():
        return [s for s in sent if s[0] in rcpts]

    def owner_mails():
        return [s for s in sent if pname[:50] in s[1] and "attestation(s) à surveiller" in s[1]]

    run_on(0)                                                   # J-6 → palier J-7
    assert len(member_mails()) == 2 and len(owner_mails()) == 1          # UN récapitulatif
    assert "Partenaire 0 SARL" in owner_mails()[0][2] and "Partenaire 1 SARL" in owner_mails()[0][2]
    assert "Kbis à fournir" in member_mails()[0][2]
    for offset in (0, 1, 2):                                    # même palier : rien de plus
        run_on(offset)
    assert len(member_mails()) == 2 and len(owner_mails()) == 1
    run_on(3)                                                   # J-3 : une nouvelle alerte chacun
    assert len(member_mails()) == 4 and len(owner_mails()) == 2
    for offset in (4, 5):                                       # J-2, J-1 : rien de plus
        run_on(offset)
    assert len(member_mails()) == 4 and len(owner_mails()) == 2
    from app.models import AuditLog
    db = _db()
    try:
        details = [r.detail for r in db.query(AuditLog).filter(
            AuditLog.project_id == pid, AuditLog.action == "piece.expiring").all()]
    finally:
        db.close()
    assert len(details) == 4 and all(d.startswith(("J-7 (date limite", "J-3 (date limite")) for d in details)
    labels = [e["label"] for e in client.get(f"/api/invite/{invs[0]['token']}/journal").json()["entries"]]
    assert labels.count("Adjugo vous a alerté : une attestation manque ou expire") == 2
    assert client.get(f"/api/invite/{invs[0]['token']}/journal/integrity").json()["verdict"] == "intact"


def test_relance_part_et_attestations_en_un_seul_email(client, auth, mails, monkeypatch):
    import app.services.alerts as al
    sent = []
    monkeypatch.setattr(al, "send_email", lambda to, subj, body: sent.append((to, subj, body)) or True)
    pid, invs = _alert_project(client, auth, days=3, n_partners=1, submit=False)
    to = invs[0]["recipient"]
    db = _db()
    try:
        res = al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert res["pieces_merged"] >= 1
    to_member = [s for s in sent if s[0] == to]
    assert len(to_member) == 1, [s[1] for s in to_member]
    assert to_member[0][1].startswith("Rappel") and "attestations sont aussi à mettre à jour" in to_member[0][2]
    assert "Kbis à fournir" in to_member[0][2]
    # Re-lancé le même jour : rien de plus pour ce partenaire.
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert len([s for s in sent if s[0] == to]) == 1


def test_plus_de_relance_apres_depot(client, auth, mails, monkeypatch):
    import app.services.alerts as al
    sent = []
    monkeypatch.setattr(al, "send_email", lambda to, subj, body: sent.append((to, subj, body)) or True)
    h = auth["headers"]
    pid, invs = _alert_project(client, auth, days=2, n_partners=1, submit=False)
    assert client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True}).status_code == 200
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert not [s for s in sent if s[0] == invs[0]["recipient"]]


# ═══ 6. Tableau de bord ═══════════════════════════════════════════════════════════════

def test_tableau_de_bord_groupements(client, auth, mails):
    from app.models import Project
    h = auth["headers"]
    p_acc = _project(client, h, name="Marché accessible en groupement")
    p_inv = _project(client, h, name="Marché avec partenaires")
    p_dep = _project(client, h, name="Marché déposé")
    p_old = _project(client, h, name="Marché échu", deadline_days=-3)
    db = _db()
    try:
        for pid in (p_acc, p_old):
            pr = db.get(Project, pid)
            pr.go_decision, pr.groupement_score, pr.match_score = "go_groupement", 81, 54
        db.commit()
    finally:
        db.close()
    _invite(client, h, p_inv, "Alpha SARL")
    i = _invite(client, h, p_dep, "Beta SAS")
    assert client.post(f"/api/projects/{p_dep}/groupement/deposer", headers=h, json={"confirmer": True}).status_code == 200
    # Autre entreprise : ses marchés n'apparaissent jamais.
    oh, _ = _register(client, company="Autre SARL")
    other = _project(client, oh, name="Marché d'une autre entreprise")
    _invite(client, oh, other, "Gamma")
    r = client.get("/api/groupement/tableau-de-bord", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["marches_accessibles_en_groupement"] == 1
    assert [x["name"] for x in d["accessibles"]] == ["Marché accessible en groupement"]
    assert d["accessibles"][0]["groupement_score"] == 81 and "match_score" not in json.dumps(d)
    assert d["groupements_en_cours"] == 1 and d["en_cours"][0]["name"] == "Marché avec partenaires"
    assert d["en_cours"][0]["etape"] == 2 and d["en_cours"][0]["n_membres"] == 1
    assert d["deposes"] == 1
    assert [e["count"] for e in d["par_etape"]] == [1, 1, 0, 0, 0]
    raw = json.dumps(d, ensure_ascii=False)
    assert "Autre SARL" not in raw and "autre entreprise" not in raw
    assert "Alpha SARL" not in raw and "Beta SAS" not in raw and "prix" not in raw
    assert client.get("/api/groupement/tableau-de-bord", headers=oh).json()["groupements_en_cours"] == 1
    assert client.get("/api/groupement/tableau-de-bord").status_code == 401


# ═══ 7. Doctrine : rien de nouveau ne fuite ═══════════════════════════════════════════

def test_doctrine_vague4_rien_ne_fuite(client, auth, mails, no_llm):
    from tests.test_cotraitance_v2_doctrine import _envelope
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    ta, tb = invs[0]["token"], invs[1]["token"]
    assert _put(client, ta, detail_chiffre=_envelope()).status_code == 200
    _submit(client, ta)
    _upload(client, ta, "dpgf.csv", CSV_OK, piece_type="dpgf_lot")
    blobs = {
        "integrite_b": client.get(f"/api/invite/{tb}/journal/integrity").json(),
        "export_b": client.get(f"/api/invite/{tb}/journal/export").json(),
        "depot": client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json(),
        "tableau": client.get("/api/groupement/tableau-de-bord", headers=h).json(),
        "empreintes": client.get("/api/securite/empreintes-scripts").json(),
        "contribs_owner": client.get(f"/api/projects/{pid}/contributions", headers=h).json(),
    }
    for name, b in blobs.items():
        raw = json.dumps(b, ensure_ascii=False)
        assert "ciphertext" not in raw and "kdf_salt" not in raw, name
        assert "@" not in raw or name == "contribs_owner", name
    # Beta ne voit jamais le prix d'Alpha ni le nom de sa DPGF.
    raw_b = json.dumps(blobs["integrite_b"], ensure_ascii=False) + json.dumps(blobs["export_b"], ensure_ascii=False)
    assert "40000" not in raw_b and "40 000" not in raw_b and "dpgf.csv" not in raw_b
    # Le chef de file voit la DPGF (prix de vente), jamais l'enveloppe du détail chiffré.
    assert all("detail_chiffre" not in x for x in blobs["contribs_owner"])
    assert any(x.get("has_detail_chiffre") for x in blobs["contribs_owner"])
    # Aucun appel au LLM dans tout ce parcours (fixture no_llm).


# ═══ 8. Migration q1r2s3t4u5v6 (SQLite) ═══════════════════════════════════════════════

def test_migration_chiffrage_note_videe_sans_suppression_sqlite(tmp_path):
    """Expand/contract : la colonne est vidée (texte recopié, aucune perte) mais PAS supprimée —
    l'ancien code (production) la mappe encore et doit continuer de lire et d'écrire les parts
    pendant le déploiement et après un retour arrière. La suppression viendra plus tard."""
    import sqlalchemy as sa
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    alembic = [sys.executable, "-m", "alembic"]

    def make(name):
        dbfile = tmp_path / name
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

        def run(*args):
            r = subprocess.run(alembic + list(args), cwd=root, env=env, capture_output=True, text=True, timeout=300)
            assert r.returncode == 0, r.stdout + r.stderr
        return sa.create_engine(f"sqlite:///{dbfile}"), run

    def cols(eng, table="project_contributions"):
        return {c["name"] for c in sa.inspect(eng).get_columns(table)}

    def version(eng):
        with eng.connect() as cn:
            return cn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()

    # (a) Base NEUVE : toute la chaîne passe ; la colonne n'a jamais existé (le modèle ne la mappe plus).
    eng, run = make("neuve.db")
    run("upgrade", "head")
    assert "chiffrage_note" not in cols(eng) and {"prix_lot_ht", "note_au_mandataire"} <= cols(eng)
    assert "network_accepted_at" in cols(eng, "project_invites")
    assert version(eng) == head
    eng.dispose()

    # (b) Base « production » à la révision précédente, colonne présente + données.
    eng, run = make("prod.db")
    run("upgrade", "p0q1r2s3t4u5")
    with eng.begin() as cn:
        cn.execute(sa.text("ALTER TABLE project_contributions ADD COLUMN chiffrage_note TEXT"))
        if "network_accepted_at" in cols(eng, "project_invites"):      # créée par une synchro générique
            cn.execute(sa.text("ALTER TABLE project_invites DROP COLUMN network_accepted_at"))
        ins = sa.text("INSERT INTO project_contributions (invite_id, project_id, owner_id, company_name, status, "
                      "version, prix_lot_ht, chiffrage_note, note_au_mandataire) VALUES "
                      "(:i, 1, 1, :c, :s, 2, :p, :n, :m)")
        cn.execute(ins, {"i": 101, "c": "Alpha", "s": "submitted", "p": 40000.0, "n": "SECRET marge 18 %", "m": "Merci"})
        cn.execute(ins, {"i": 102, "c": "Beta", "s": "submitted", "p": None, "n": "", "m": "Note de Beta"})
        cn.execute(ins, {"i": 103, "c": "Gamma", "s": "draft", "p": 12.5, "n": None, "m": ""})
        inv = sa.text("INSERT INTO project_invites (id, token, project_id, owner_id, source, accepted_by_user_id, "
                      "revoked) VALUES (:i, :t, 1, 1, :s, :a, 0)")
        cn.execute(inv, {"i": 101, "t": "t101", "s": "reseau_adjugo", "a": None})     # part soumise
        cn.execute(inv, {"i": 103, "t": "t103", "s": "reseau_adjugo", "a": None})     # rien : en attente
        cn.execute(inv, {"i": 104, "t": "t104", "s": "reseau_adjugo", "a": 1})        # acceptée (compte)
        cn.execute(inv, {"i": 105, "t": "t105", "s": "manuel", "a": 1})               # pas du réseau
    assert "chiffrage_note" in cols(eng) and "network_accepted_at" not in cols(eng, "project_invites")
    run("upgrade", "head")
    assert version(eng) == head
    assert "chiffrage_note" in cols(eng), "la colonne doit rester en base (expand/contract)"
    with eng.connect() as cn:
        rows = {r[0]: tuple(r[1:]) for r in cn.execute(sa.text(
            "SELECT invite_id, note_au_mandataire, prix_lot_ht, version, status, chiffrage_note "
            "FROM project_contributions"))}
        acc = {r[0]: r[1] for r in cn.execute(sa.text("SELECT id, network_accepted_at FROM project_invites"))}
    assert rows[101] == ("(ancienne approche prix) SECRET marge 18 %\n\nMerci", 40000.0, 2, "submitted", "")
    assert rows[102][0] == "Note de Beta" and rows[103][:2] == ("", 12.5)
    assert acc[101] and acc[104] and acc[103] is None and acc[105] is None
    # L'ancien code (son modèle mappe chiffrage_note) lit et écrit toujours les parts.
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO project_contributions (invite_id, project_id, owner_id, version, "
                           "chiffrage_note) VALUES (201, 1, 1, 0, '')"))
        assert cn.execute(sa.text("SELECT COUNT(chiffrage_note) FROM project_contributions")).scalar() == 3
    # Le nouveau code (colonne non mappée) écrit sans elle.
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO project_contributions (invite_id, project_id, owner_id, version) "
                           "VALUES (202, 1, 1, 0)"))
    with pytest.raises(sa.exc.IntegrityError):         # unicité invite_id intacte
        with eng.begin() as cn:
            cn.execute(sa.text("INSERT INTO project_contributions (invite_id, project_id, owner_id, version) "
                               "VALUES (101, 1, 1, 0)"))

    # (c) Rejeu : aucune erreur, rien ne change (le texte n'est pas recopié deux fois).
    run("stamp", "p0q1r2s3t4u5")
    run("upgrade", "head")
    assert "chiffrage_note" in cols(eng) and version(eng) == head
    with eng.connect() as cn:
        assert cn.execute(sa.text("SELECT COUNT(*) FROM project_contributions")).scalar() == 5
        assert cn.execute(sa.text("SELECT note_au_mandataire FROM project_contributions WHERE invite_id = 101")
                          ).scalar() == "(ancienne approche prix) SECRET marge 18 %\n\nMerci"
    # Retour arrière : downgrade ne casse rien (la colonne est toujours là pour l'ancien code).
    run("downgrade", "p0q1r2s3t4u5")
    assert "chiffrage_note" in cols(eng)
    eng.dispose()


def test_chiffrage_note_plus_lue_ni_ecrite_nulle_part():
    """La colonne supprimée n'apparaît plus dans le code applicatif, sauf en commentaire ou
    docstring (historique)."""
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    hits = []
    for f in root.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "chiffrage_note":
                hits.append(f"{f.name}:{node.lineno} attribut")
            elif isinstance(node, ast.Name) and node.id == "chiffrage_note":
                hits.append(f"{f.name}:{node.lineno} nom")
            elif isinstance(node, ast.keyword) and node.arg == "chiffrage_note":
                hits.append(f"{f.name}:{node.lineno} argument")
            elif isinstance(node, ast.Constant) and node.value == "chiffrage_note":
                hits.append(f"{f.name}:{node.lineno} clé")
    assert not hits, hits
    from app.models import ProjectContribution
    assert "chiffrage_note" not in ProjectContribution.__table__.columns


def test_sous_traitant_ne_voit_pas_le_total_dans_le_journal(client, auth, mails):
    """Règle de la vague 2 (un non-signataire ne reçoit jamais le total), appliquée aussi au
    détail « total … € HT » de l'entrée « offre figée » du journal, de son intégrité et de ses exports."""
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    st = client.post(f"/api/projects/{pid}/invites", headers=h,
                     json={"company_name": "Échafaudages Sous-Traitant", "role": "sous_traitant"}).json()
    c = _gen(client, h, pid).json()
    total = c["total_offre_ht"]
    assert total
    blobs = [client.get(f"/api/invite/{st['token']}/journal").json(),
             client.get(f"/api/invite/{st['token']}/journal/integrity").json(),
             client.get(f"/api/invite/{st['token']}/journal/export").json()]
    for b in blobs:
        raw = json.dumps(b, ensure_ascii=False)
        assert "€ HT" not in raw and "100 000" not in raw and "100000" not in raw, raw[:400]
    assert "Le chef de file a figé l'offre commune" in [e["label"] for e in blobs[0]["entries"]]
    pdf = _pdf_text(client.get(f"/api/invite/{st['token']}/journal/export?format=pdf").content)
    assert "€ HT" not in pdf
    # Un co-traitant signataire voit le total (doctrine inchangée).
    co = client.get(f"/api/invite/{invs[0]['token']}/journal").json()
    assert any(e["action"] == "offer.frozen" and "€ HT" in e["detail"] for e in co["entries"])
