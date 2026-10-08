"""
Co-traitance v2 — corrections de la revue des vagues 3 et 4 (domaine B : convention, journal
membre, dépôt, DPGF, migration, SRI, invitations, page partenaire).

Chaque test échoue sans la correction qu'il couvre :
- DPGF CSV : plus de retour arrière quadratique (une cellule géante ne gèle plus le process),
  formules contrôlées sous chaque séparateur plausible (« ; », « , », tabulation, « sep= »),
  en-têtes de coûts / marges reconnus quel que soit le nombre de lignes de titre ou l'écriture
  (« Marge_HT », « cout_unitaire »), texte renommé en .xls refusé, et tout CSV produit par le
  navigateur (AdjugoCrypto.dpgf.csv) toujours accepté.
"""
import io
import json
import os
import random
import shutil
import subprocess
import time

import pytest

from tests.test_convention_groupement import _invite, _project

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


def _upload(client, token, filename, data, **form):
    return client.post(f"/api/invite/{token}/contribution/piece",
                       files={"file": (filename, io.BytesIO(data), "application/octet-stream")}, data=form)


def _dpgf(client, token, text, name="dpgf.csv"):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return _upload(client, token, name, data, piece_type="dpgf_lot")


# ═══ DPGF CSV ═════════════════════════════════════════════════════════════════════════

def test_dpgf_cellule_geante_traitee_en_temps_lineaire():
    """Une cellule de 20 000 espaces prenait ~5 s (retour arrière quadratique, GIL bloqué) ;
    100 000 espaces, plusieurs minutes. Désormais : quelques millisecondes, dans les deux chemins
    (cellule « -… » contrôlée comme formule, et ligne d'en-tête)."""
    from fastapi import HTTPException
    from app.routers.invites import _check_dpgf_csv
    for n in (20000, 100000):
        cases = [("Designation;Prix\nA;-1" + " " * n + "x\n", 422),
                 ("1" + " " * n + "x\nLigne;u;1;10;10\n", 200)]
        for text, expected in cases:
            t0 = time.perf_counter()
            try:
                _check_dpgf_csv(text.encode())
                got = 200
            except HTTPException as e:
                got = e.status_code
            assert got == expected
            assert time.perf_counter() - t0 < 0.3, f"{n} espaces : {time.perf_counter() - t0:.2f} s"


def test_dpgf_formule_controlee_sous_chaque_separateur(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    pieges = [
        "sep=,\nDésignation;Unité;Qté;PU\nPose;u;1;b,=1+1\n",                       # directive Excel
        "Désignation,Unité,Quantité,Prix,Montant,Note,A,B,C\nCâble,u,1,2;=1+1,3\n",  # « ; » caché
        "A;B;C;D;E;F;G;H;C\nCâble;x,=1+1;3\n",                                     # « , » caché
        "A;B\nx\t@SOMME(A1);2\n",                                                   # tabulation
        "A;B\nx;y,\"\"=HYPERLINK(1)\"\n",                                           # guillemet après virgule
    ]
    for text in pieges:
        r = _dpgf(client, t, text)
        assert r.status_code == 422 and "formule" in r.json()["detail"], (text, r.text)
    # Valeurs négatives, milliers, exposant : des nombres, pas des formules.
    ok = ("N°;Désignation;Unité;Quantité;PU HT;Montant HT\n1;Remise;u;1;-1.250,50;-1.250,50\n"
          "2;Très grand;u;1;1e+21;1e+21\n3;Pose;u;2;1 250,00 €;2 500,00 €\n")
    assert _dpgf(client, t, ok).status_code == 200


def test_dpgf_entetes_de_couts_reconnus(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    refus = {
        "5 lignes de titre": ("DPGF - Lot 2 Électricité;;;;;\nMarché : rénovation de l'école;;;;;\n;;;;;\n"
                              "Entreprise : Le Gall;;;;;\n;;;;;\nN°;Désignation;Unité;Qté;PU HT;Marge\n"
                              "1;Pose tableau;u;1;1 250,00;12 %\n"),
        "nombre dans l'en-tête": "N°;Désignation;Qté;PU 2026;Marge 2026\n1;Câble;2;10;3\n",
        "Marge_HT": "N°;Désignation;Qté;PU;Marge_HT\n1;Câble;2;10;3\n",
        "cout_unitaire": "N°;Désignation;Qté;cout_unitaire;PU\n1;Câble;2;10;3\n",
        "PRIX D'ACHAT": "N°;Désignation;Qté;PRIX D'ACHAT;PU\n1;Câble;2;10;3\n",
    }
    for label, text in refus.items():
        r = _dpgf(client, t, text)
        assert r.status_code == 422 and "prix de vente" in r.json()["detail"], (label, r.text)
    # Un mot de la liste DANS une désignation (ligne de valeurs) n'est pas une colonne : accepté.
    ligne = "N°;Désignation;Qté;PU;Montant\n1;Reprise des marges et du coût de voirie;2;10;20\n"
    assert _dpgf(client, t, ligne).status_code == 200


def test_dpgf_texte_renomme_en_tableur_refuse(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    r = _dpgf(client, t, "Désignation;Marge\nPose;=1+1\n", name="dpgf_lot2.xls")
    assert r.status_code == 422 and "XLS" in r.json()["detail"]
    r = _dpgf(client, t, "Désignation;Marge\nPose;=1+1\n", name="dpgf_lot2.xlsx")
    assert r.status_code == 422
    assert _dpgf(client, t, PDF, name="DPGF_lot.pdf").status_code == 200
    assert _dpgf(client, t, b"PK\x03\x04" + b"\x00" * 30, name="DPGF_lot.xlsx").status_code == 200
    # Changer le type d'une pièce en DPGF applique les mêmes contrôles.
    up = _upload(client, t, "tableau.xlsx", b"Designation;Prix\nX;=1+1\n")
    assert up.status_code == 200, up.text
    r = client.patch(f"/api/invite/{t}/contribution/piece/{up.json()['id']}", json={"piece_type": "dpgf_lot"})
    assert r.status_code == 422


def _node_csvs(batch):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    script = ("global.window = {}; require(process.argv[1]); const D = window.AdjugoCrypto.dpgf;"
              "const opts = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              "process.stdout.write(JSON.stringify(opts.map(o => ({csv: D.csv(o), hp: D.headerProblem(o)}))));")
    out = subprocess.run([node, "-e", script, os.path.join(STATIC, "cotraitance-crypto.js")],
                         input=json.dumps(batch), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_dpgf_produite_par_le_navigateur_toujours_acceptee():
    """Le fichier du générateur (cotraitance-crypto.js) passe TOUJOURS le contrôle du serveur :
    cas de la revue (désignations à virgules, « , +10 ml de réserve ») et échantillon aléatoire
    (virgules, guillemets, signes, caractères de contrôle, mots de coût dans les lignes)."""
    from fastapi import HTTPException
    from app.routers.invites import _check_dpgf_csv
    revue = {"entreprise": "Le Gall Électricité", "lot": "Lot 2", "lignes": [
        {"designation": "Fourniture, pose, raccordement, réglage, essais, mise en service, nettoyage, repli, "
                        "+10 ml de réserve", "unite": "ml", "quantite": 2.5, "pu": 100},
        {"designation": "Câble, \"=HYPERLINK(1)\", -3 m, @lot", "unite": "u", "quantite": 1, "pu": -150}]}
    rnd = random.Random(20261008)
    alphabet = list("abc ,;\"'=+-@ \t\r\n\u2028\u00a0\u0085\x0b\x1c—éàç0123456789") + [
        "coût", "marge", "sep=,", ", -", ",\"=", "1,5", "-3", ",+", ", @"]

    def txt(k):
        return "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, k)))
    batch = [revue] + [{"entreprise": txt(12), "lot": txt(12), "lignes": [
        {"designation": txt(60) or "x", "unite": txt(5), "quantite": rnd.choice([0, 1, 2.5, 300.333, 1e23]),
         "pu": rnd.choice([12.5, -150, 0, 1999.99, -1e22, -0.001])} for _ in range(rnd.randint(1, 5))]}
        for _ in range(600)]
    res = _node_csvs(batch)
    assert res[0]["hp"] == ""
    checked = 0
    for o, r in zip(batch, res):
        if r["hp"]:
            continue                       # le navigateur refuse lui-même ce nom d'entreprise ou de lot
        try:
            _check_dpgf_csv(r["csv"].encode("utf-8"))
        except HTTPException as e:
            raise AssertionError(f"CSV du navigateur refusé : {e.detail} — {r['csv'][:300]!r}")
        checked += 1
    assert checked > 150
