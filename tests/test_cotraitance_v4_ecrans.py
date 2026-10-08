"""
Co-traitance v2 — vague 4, écrans « Preuves, dépôt, finitions ».

Invariants vérifiés (ce que les écrans exigent du serveur, et les écrans eux-mêmes) :
- « Ma DPGF de lot » : les lignes de la DPGF sont rangées dans le DÉTAIL CHIFFRÉ du partenaire
  (route « détail seul ») ; l'enregistrer ne repasse pas une part soumise en brouillon, ne défige
  pas l'offre et ne rend pas la convention caduque ; verrou optimiste ; enveloppe validée ;
  lien révoqué / lecture seule refusés ; démo bloquée ; le chef de file ne reçoit jamais
  l'enveloppe ;
- le fichier produit par le navigateur (AdjugoCrypto.dpgf.csv) est accepté tel quel comme pièce
  « dpgf_lot » (UTF-8, « ; », sans formule, sans colonne de coût ni de marge) ;
- exports du journal : nom de fichier lisible (accents translittérés) ;
- écrans : routes de la vague 4 branchées (vérification, exports, dépôt, tableau de bord), plus
  aucun pourcentage « prêt » affiché pour le dépôt, plus de « preuve opposable » ni de
  « journal infalsifiable », aucun émoji.
"""
import io
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.test_convention_groupement import _gen, _groupement, _invite, _project, _put, _submit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")

ENV = {"ciphertext": "QUJDRA==", "iv": "AAAAAAAAAAAAAAAA", "alg": "A256GCM", "kdf": "PBKDF2-SHA256",
       "kdf_salt": "c2FsdHNhbHRzYWx0c2FsdA==", "kdf_iter": 600000, "key_fingerprint": "0123456789abcdef",
       "updated_at": "2026-10-08T10:00:00Z"}

# Fichier produit par le générateur du navigateur (AdjugoCrypto.dpgf.csv, cotraitance-crypto.js)
# pour les lignes de _DPGF_OPTS : désignation commençant par « - » ou « = », point-virgule et
# guillemets dans une cellule, mot « marges » dans une LIGNE (autorisé), moins-value négative.
CSV_NAVIGATEUR = (
    "﻿DPGF du lot - prix de vente HT\r\n"
    "Entreprise;Le Gall Électricité\r\n"
    "Lot;Lot 2 — Électricité\r\n"
    "N°;Désignation;Unité;Quantité;Prix unitaire HT (€);Montant HT (€)\r\n"
    "1;Dépose de l'existant;m²;120;12,50;1500,00\r\n"
    "2;\"SOMME(A1) Fourniture; pose \"\"câbles\"\"\";ml;300,333;4,10;1231,37\r\n"
    "3;Reprise des marges de voirie;u;1;1999,99;1999,99\r\n"
    "4;Moins-value (remise);ft;1;-150,00;-150,00\r\n"
    ";Total HT;;;;4581,36\r\n")
_DPGF_OPTS = {"entreprise": "Le Gall Électricité", "lot": "Lot 2 — Électricité", "lignes": [
    {"designation": "- Dépose de l'existant", "unite": "m²", "quantite": 120, "pu": 12.5},
    {"designation": "=SOMME(A1) Fourniture; pose \"câbles\"", "unite": "ml", "quantite": 300.333, "pu": 4.1},
    {"designation": "Reprise des marges de voirie", "unite": "u", "quantite": 1, "pu": 1999.99},
    {"designation": "Moins-value (remise)", "unite": "ft", "quantite": 1, "pu": -150}]}


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def _detail(client, token, env, version=None):
    if version is None:
        version = client.get(f"/api/invite/{token}/contribution").json()["version"]
    return client.put(f"/api/invite/{token}/contribution/detail", json={"detail_chiffre": env, "version": version})


# ═══ 1. Détail chiffré seul (lignes de la DPGF) ═══════════════════════════════════════

def test_detail_seul_ne_touche_ni_la_part_ni_la_convention(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    ta = invs[0]["token"]
    conv = _gen(client, h, pid).json()
    assert conv["status"] == "a_signer"
    before = client.get(f"/api/invite/{ta}/contribution").json()
    assert before["status"] == "submitted"
    labels_avant = [e["label"] for e in client.get(f"/api/invite/{ta}/journal").json()["entries"]]

    r = _detail(client, ta, ENV, before["version"])
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["status"] == "submitted" and after["version"] == before["version"] + 1
    assert after["detail_chiffre"]["ciphertext"] == ENV["ciphertext"]
    assert after["prix_lot_ht"] == before["prix_lot_ht"]
    # Convention toujours à valider, offre toujours figée, aucune trace « caduque » / « défigée ».
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["status"] == "a_signer"
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["state"] == "convention_a_signer"
    labels = [e["label"] for e in client.get(f"/api/invite/{ta}/journal").json()["entries"]]
    assert labels == labels_avant
    # Le chef de file ne reçoit jamais l'enveloppe.
    own = client.get(f"/api/projects/{pid}/contributions", headers=h).json()
    assert "ciphertext" not in json.dumps(own) and all("detail_chiffre" not in x for x in own)
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert "ciphertext" not in json.dumps(ck)

    # Verrou optimiste, version exigée, enveloppe stricte, champ exigé.
    assert _detail(client, ta, ENV, before["version"]).status_code == 409
    assert client.put(f"/api/invite/{ta}/contribution/detail", json={"detail_chiffre": ENV}).status_code == 428
    bad = dict(ENV, alg="none")
    assert _detail(client, ta, bad).status_code == 422
    assert _detail(client, ta, dict(ENV, extra="x")).status_code == 422
    v = client.get(f"/api/invite/{ta}/contribution").json()["version"]
    assert client.put(f"/api/invite/{ta}/contribution/detail", json={"version": v}).status_code == 422
    # Effacer (null) : la part reste soumise.
    r = _detail(client, ta, None)
    assert r.status_code == 200 and r.json()["detail_chiffre"] is None and r.json()["status"] == "submitted"
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["status"] == "a_signer"


def test_detail_seul_lien_revoque_lecture_seule_et_demo(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    ro = client.post(f"/api/projects/{pid}/invites", headers=h,
                     json={"company_name": "Lecture Seule SARL", "can_contribute": False}).json()
    assert _detail(client, ro["token"], ENV, 0).status_code == 403
    inv = _invite(client, h, pid, "Retirée SAS")
    assert client.delete(f"/api/projects/{pid}/invites/{inv['id']}", headers=h).status_code == 200
    assert _detail(client, inv["token"], ENV, 0).status_code in (404, 410)
    assert client.put("/api/invite/jeton-inconnu/contribution/detail",
                      json={"detail_chiffre": ENV, "version": 0}).status_code == 404
    from app.core.demo_guard import blocked_action
    assert blocked_action("PUT", "/api/invite/abc/contribution/detail")


# ═══ 2. Le fichier produit par le navigateur est accepté tel quel ═════════════════════

def test_csv_du_navigateur_accepte_comme_dpgf(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Le Gall Électricité")["token"]
    assert _put(client, t, company_name="Le Gall Électricité", lot="Lot 2 — Électricité",
                prix_lot_ht=4581.36).status_code == 200
    _submit(client, t)
    data = CSV_NAVIGATEUR.encode("utf-8")
    r = client.post(f"/api/invite/{t}/contribution/piece",
                    files={"file": ("DPGF_Lot_2_Electricite.csv", io.BytesIO(data), "text/csv")},
                    data={"piece_type": "dpgf_lot"})
    assert r.status_code == 200, r.text
    assert r.json()["piece_type"] == "dpgf_lot"
    c = client.get(f"/api/invite/{t}/contribution").json()
    assert c["status"] == "submitted" and c["has_dpgf_lot"] is True
    # Aucune colonne de coût, de marge ni de coefficient dans les en-têtes produits.
    head = CSV_NAVIGATEUR.split("\r\n")[:4]
    assert not any(re.search(r"marge|co[uû]t|d[ée]bours|coefficient|prix d'achat", l, re.I) for l in head)


def test_generateur_navigateur_identique_au_fichier_de_reference():
    """Le générateur réel (cotraitance-crypto.js) produit exactement CSV_NAVIGATEUR."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    script = ("global.window = {}; require(process.argv[1]); const D = window.AdjugoCrypto.dpgf;"
              "const o = JSON.parse(process.argv[2]);"
              "process.stdout.write(JSON.stringify({csv: D.csv(o), name: D.fileName(o), total: D.total(o.lignes),"
              " head: D.headerProblem({entreprise: 'Coûts Maîtrisés SARL'}), ok: D.headerProblem(o)}));")
    out = subprocess.run([node, "-e", script, os.path.join(STATIC, "cotraitance-crypto.js"), json.dumps(_DPGF_OPTS)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res["csv"] == CSV_NAVIGATEUR
    assert res["name"] == "DPGF_Lot_2_Electricite.csv" and res["total"] == 4581.36
    assert "Coûts" in res["head"] and res["ok"] == ""


def test_detail_v2_texte_et_lignes_dans_la_meme_enveloppe():
    """packDetail / unpackDetail : l'ancien détail (texte brut) se relit tel quel."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    script = ("global.window = {}; require(process.argv[1]); const C = window.AdjugoCrypto;"
              "const p = C.packDetail('marge 12 %', {lignes: [{designation: 'Pose', unite: 'u', quantite: '2', pu: '1 250,50'}]});"
              "process.stdout.write(JSON.stringify({p, u: C.unpackDetail(p), old: C.unpackDetail('texte libre'),"
              " vide: C.packDetail('', {lignes: []}), seul: C.packDetail('texte', null)}));")
    out = subprocess.run([node, "-e", script, os.path.join(STATIC, "cotraitance-crypto.js")],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res["u"]["texte"] == "marge 12 %"
    assert res["u"]["dpgf"]["lignes"] == [{"designation": "Pose", "unite": "u", "quantite": 2, "pu": 1250.5}]
    assert res["old"] == {"texte": "texte libre", "dpgf": None}
    assert res["vide"] == "" and res["seul"] == "texte"


# ═══ 3. Exports du journal : nom de fichier lisible ═══════════════════════════════════

def test_export_journal_nom_de_fichier_translittere(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h, name="Réhabilitation de l'école Jules-Ferry")
    t = _invite(client, h, pid, "Le Gall Électricité")["token"]
    r = client.get(f"/api/invite/{t}/journal/export?format=json")
    assert r.status_code == 200
    assert 'filename="Journal_Rehabilitation de l_ecole Jules-Ferry.json"' in r.headers["content-disposition"]


# ═══ 4. Écrans ═════════════════════════════════════════════════════════════════════════

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def test_ecrans_vague4_branches_et_regles_d_interface():
    inv, js, html, css = _read("invite.html"), _read("app.js"), _read("app.html"), _read("styles.css")
    # Partenaire (lien magique) : vérification, exports, DPGF produite dans le navigateur.
    for needle in ("Vérifier mon journal", "/journal/integrity", "/journal/export?format=",
                   "Ma DPGF de lot", 'url + "/detail"', '"dpgf_lot"', "packDetail", "unpackDetail"):
        assert needle in inv, needle
    # « Partagé avec moi », chef de file, tableau de bord.
    for needle in ("/api/shared/", "/integrity", "/groupement/depot", "/groupement/deposer",
                   "/api/groupement/tableau-de-bord", "packDetail", '"groupement.depose"'):
        assert needle in js, needle
    assert "Vérifier mon journal" in html and "Marquer déposé" in html and "dash-steps" in html
    # Un seul pourcentage dans le produit : plus de « prêt à XX % » pour le dépôt.
    assert "convPret().pct" not in html and "depotPret().pct" not in html
    # On ne survend pas la preuve.
    for f in (inv, js, html):
        assert "preuve opposable" not in f and "infalsifiable" not in f
    # Zéro émoji.
    for name, f in (("invite.html", inv), ("app.js", js), ("cotraitance-crypto.js", _read("cotraitance-crypto.js"))):
        assert not _EMOJI.search(f), name
    # Styles partagés du verdict présents.
    assert ".jv-acts" in css and ".dash-steps" in css
