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


def test_dpgf_csv_volumineux_borne():
    """Le contrôle du CSV tourne en Python sous le GIL de l'unique process : au-delà de 4 Mo il
    est refusé d'emblée (tableur ou PDF) ; en dessous, même le pire fichier reste sous la seconde."""
    from fastapi import HTTPException
    from app.routers.invites import _DPGF_CSV_MAX_BYTES, _check_dpgf_csv
    gros = ("Désignation " * 20 + ";" + "b" * 2000 + "\n").encode() * (_DPGF_CSV_MAX_BYTES // 2000)
    assert len(gros) > _DPGF_CSV_MAX_BYTES
    t0 = time.perf_counter()
    with pytest.raises(HTTPException) as e:
        _check_dpgf_csv(gros)
    assert e.value.status_code == 422 and "4 Mo" in e.value.detail
    assert time.perf_counter() - t0 < 0.1
    pire = (("1 " * 30000) + "x;" + "\n").encode() * (_DPGF_CSV_MAX_BYTES // 60100)
    assert len(pire) <= _DPGF_CSV_MAX_BYTES
    t0 = time.perf_counter()
    try:
        _check_dpgf_csv(pire)
    except HTTPException:
        pass
    assert time.perf_counter() - t0 < 2.0


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


def test_dpgf_jointe_depuis_le_coffre_fort_controlee(client, auth, mails):
    """« Joindre depuis mon coffre-fort » une DPGF : mêmes contrôles qu'un dépôt direct (formule
    refusée, rien n'est copié dans le tenant du chef de file) ; une DPGF saine est jointe."""
    import uuid as _uuid
    from app.models import ContributionPiece, DocCategory, Document, User
    from app.services.storage import get_storage
    h = auth["headers"]
    pid = _project(client, h)
    email = f"part_{_uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Partenaire", "company_name": "Delta Peinture"})
    assert r.status_code == 201, r.text
    ph = {"Authorization": f"Bearer {r.json()['access_token']}"}
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    assert client.post(f"/api/invite/{t}/claim", headers=ph).status_code == 200
    db = _db()
    try:
        uid = db.query(User).filter(User.email == email).first().id
        ids = {}
        for nom, data in (("DPGF_lot2_piege.csv", b"Designation;Prix\nPose;=1+1\n"),
                          ("DPGF_lot2.csv", b"Designation;Prix HT\nPose;1 250,00\n")):
            key = f"{uid}/vault/{_uuid.uuid4().hex}.csv"
            get_storage().save(key, data, "text/csv")
            d = Document(user_id=uid, name=nom, category=DocCategory.autre, file_key=key, file_size=len(data),
                         mime_type="text/csv")
            db.add(d)
            db.commit()
            ids[nom] = d.id
    finally:
        db.close()

    def n_pieces():
        db = _db()
        try:
            return db.query(ContributionPiece).filter(ContributionPiece.project_id == pid).count()
        finally:
            db.close()
    r = client.post(f"/api/invite/{t}/contribution/piece/from-vault", headers=ph,
                    json={"document_id": ids["DPGF_lot2_piege.csv"]})
    assert r.status_code == 422 and "formule" in r.json()["detail"], r.text
    assert n_pieces() == 0
    r = client.post(f"/api/invite/{t}/contribution/piece/from-vault", headers=ph,
                    json={"document_id": ids["DPGF_lot2.csv"]})
    assert r.status_code == 200 and r.json()["piece_type"] == "dpgf_lot", r.text
    assert n_pieces() == 1


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


# ═══ Journal membre ═══════════════════════════════════════════════════════════════════

def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _invite_row(token):
    from app.models import ProjectInvite
    db = _db()
    try:
        i = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
        return i.id, i.owner_id, i.project_id
    finally:
        db.close()


def _integrity(client, token):
    from app.services import journal_membre as jm
    jm.reset_caches()
    r = client.get(f"/api/invite/{token}/journal/integrity")
    assert r.status_code == 200, r.text
    return r.json()


def _rechain_from(db, chain, start):
    """Recalcule les maillons à partir de chain[start] (même version d'empreinte qu'avant)."""
    from app.services import audit
    for a in chain[start:]:
        a.prev_hash = chain[chain.index(a) - 1].entry_hash if chain.index(a) else ""
        a.entry_hash = audit._hash_v2(a.prev_hash, a)
    db.commit()


def test_journal_membre_fourche_historique_toleree_alteration_detectee(client, auth, mails):
    """Même tolérance que audit.verify_chain : une fourche ANCIENNE (deux écritures simultanées
    avant le verrou) n'est pas une altération ; une vraie modification ou suppression l'est."""
    from app.models import AuditLog
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    inv_id, owner, _ = _invite_row(t)
    db = _db()
    try:
        for i in range(4):
            audit.record(db, action="guest.view_project", owner_id=owner, project_id=pid, actor="Delta Peinture",
                         actor_kind="guest", target_type="project", target_id=pid, invite_id=inv_id, detail=f"vue {i}")
        chain = db.query(AuditLog).filter(AuditLog.owner_id == owner).order_by(AuditLog.id).all()
        c = chain[-1]
        # Fourche : B (avant-dernière) et C (dernière) ont lu le même maillon précédent A.
        c.prev_hash = chain[-3].entry_hash
        c.entry_hash = audit._hash_v2(c.prev_hash, c)
        db.commit()
        vc = audit.verify_chain(db, owner)
        assert vc["intact"] is True and vc["forks"] == 1
    finally:
        db.close()
    v = _integrity(client, t)
    assert v["verdict"] == "intact", v["message"]
    assert v["entrees"]["alterees"] == 0
    # Une vraie modification reste détectée.
    db = _db()
    try:
        b = db.get(AuditLog, chain[-2].id)
        b.detail = "falsifié"
        db.commit()
    finally:
        db.close()
    v = _integrity(client, t)
    assert v["verdict"] == "altere" and v["perimetre"] == "vos_entrees"
    db = _db()
    try:
        b = db.get(AuditLog, chain[-2].id)
        b.detail = "vue 2"
        db.commit()
        assert _integrity(client, t)["verdict"] == "intact"
        # Une suppression aussi (le maillon de B pointe vers A, qui n'existe plus nulle part).
        db.delete(db.get(AuditLog, chain[-3].id))
        db.commit()
    finally:
        db.close()
    v = _integrity(client, t)
    assert v["verdict"] == "altere" and v["perimetre"] == "vos_entrees"


def test_journal_membre_erreur_technique_jamais_alteree(client, auth, mails, monkeypatch):
    """Une panne pendant la vérification complète n'est JAMAIS présentée comme une modification :
    verdict « indisponible », rien en cache, export refusé (503) ; la vérification suivante, base
    rétablie, est normale."""
    import sqlalchemy as sa
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    assert client.get(f"/api/invite/{t}").status_code == 200
    real = audit.verify_chain

    def panne(*a, **k):
        raise sa.exc.OperationalError("SELECT 1", {}, Exception("base momentanément indisponible"))
    monkeypatch.setattr(audit, "verify_chain", panne)
    v = _integrity(client, t)
    assert v["verdict"] == "indisponible" and v["verdict"] != "altere", v
    assert v["journal_complet_intact"] is None and "réessayez" in v["message"]
    r = client.get(f"/api/invite/{t}/journal/export")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "verification_indisponible"
    monkeypatch.setattr(audit, "verify_chain", real)
    from app.services import journal_membre as jm
    r = client.get(f"/api/invite/{t}/journal/integrity")       # cache NON vidé : rien n'y était
    assert r.json()["verdict"] == "intact", r.json()
    exp = client.get(f"/api/invite/{t}/journal/export").json()
    assert exp["verdict"]["verdict"] == "intact" and jm.verify_export(exp)["ok"]


def test_journal_liste_erreur_technique_ni_alteree_ni_mise_en_cache(client, auth, mails, monkeypatch):
    """GET …/journal : une panne pendant la vérification complète donne « chained » inconnu
    (None), jamais False, et rien n'est gardé en cache (la requête suivante est normale)."""
    import sqlalchemy as sa
    import app.routers.invites as I
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    I._CHAIN_CACHE.clear()
    real = audit.verify_chain

    def panne(*a, **k):
        raise sa.exc.OperationalError("SELECT 1", {}, Exception("base momentanément indisponible"))
    monkeypatch.setattr(audit, "verify_chain", panne)
    r = client.get(f"/api/invite/{t}/journal")
    assert r.status_code == 200 and r.json()["chained"] is None, r.json()
    monkeypatch.setattr(audit, "verify_chain", real)
    assert client.get(f"/api/invite/{t}/journal").json()["chained"] is True


def test_journal_membre_rattachement_scelle_pour_les_nouvelles_entrees(client, auth, mails):
    """Version 2 de l'empreinte : l'invitation concernée (invite_id) est scellée. Réattribuer une
    entrée à un autre membre est détecté ; une entrée ancienne (v1) le dit (rattachement non
    scellé) et les limites l'expliquent."""
    from app.models import AuditLog
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    ta = _invite(client, h, pid, "Alpha Électricité")["token"]
    tb = _invite(client, h, pid, "Beta Plomberie")["token"]
    a_id, owner, _ = _invite_row(ta)
    b_id, _, _ = _invite_row(tb)
    assert client.get(f"/api/invite/{ta}").status_code == 200
    assert client.get(f"/api/invite/{tb}").status_code == 200
    va = _integrity(client, ta)
    assert va["verdict"] == "intact"
    assert all(e["rattachement_scelle"] for e in va["chaine"] if e["statut"] == "verifiee")
    assert va["entrees"]["rattachement_non_scelle"] == 0
    assert not any("pas scellé" in lim for lim in va["limites"])
    db = _db()
    try:
        e = db.query(AuditLog).filter(AuditLog.invite_id == a_id, AuditLog.action == "guest.view_project").first()
        e.invite_id = b_id                 # « Beta a consulté le dossier » à la place d'Alpha
        db.commit()
        eid = e.id
    finally:
        db.close()
    vb = _integrity(client, tb)
    assert vb["verdict"] == "altere" and vb["perimetre"] == "vos_entrees", vb["message"]
    va = _integrity(client, ta)
    assert va["verdict"] == "altere"       # la chaîne du chef de file est cassée elle aussi
    # Entrée ANCIENNE (empreinte v1) : la vérification passe, mais elle dit que le rattachement
    # n'est pas scellé — promesse exacte.
    db = _db()
    try:
        e = db.get(AuditLog, eid)
        e.invite_id = a_id
        chain = db.query(AuditLog).filter(AuditLog.owner_id == owner).order_by(AuditLog.id).all()
        i = [x.id for x in chain].index(eid)
        e.entry_hash = audit._hash(e.prev_hash, e)          # empreinte v1, comme avant la vague 4
        db.commit()
        _rechain_from(db, chain, i + 1)
        assert audit.verify_chain(db, owner)["intact"] is True
    finally:
        db.close()
    va = _integrity(client, ta)
    assert va["verdict"] == "intact"
    old = [x for x in va["chaine"] if x["action"] == "guest.view_project"]
    assert old and old[0]["rattachement_scelle"] is False
    assert va["entrees"]["rattachement_non_scelle"] == 1
    assert any("rattachement à votre journal n'est pas scellé" in lim for lim in va["limites"])
    exp = client.get(f"/api/invite/{ta}/journal/export").json()
    assert any(x["rattachement_scelle"] is False for x in exp["entrees"])
    assert any("pas scellé" in lim for lim in exp["limites"])


def test_total_masque_au_cotraitant_ajoute_apres_la_generation(client, auth, mails):
    """Un co-traitant invité APRÈS la génération n'est pas signataire : le détail « total … € HT »
    de l'offre figée ne lui est montré ni dans le journal, ni dans sa vérification, ni dans ses
    exports (règle de la vague 2). Un signataire le voit toujours."""
    from tests.test_convention_groupement import _gen, _groupement, _pdf_text
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    c = _gen(client, h, pid).json()
    assert c["total_offre_ht"]
    late = _invite(client, h, pid, "Arrivé Tard SARL")["token"]
    from app.services import journal_membre as jm
    jm.reset_caches()
    blobs = [client.get(f"/api/invite/{late}/journal").json(),
             client.get(f"/api/invite/{late}/journal/integrity").json(),
             client.get(f"/api/invite/{late}/journal/export").json()]
    labels = [e["label"] for e in blobs[0]["entries"]]
    assert "Le chef de file a figé l'offre commune" in labels
    for b in blobs:
        raw = json.dumps(b, ensure_ascii=False)
        assert "€ HT" not in raw and "100 000" not in raw, raw[:400]
    assert "€ HT" not in _pdf_text(client.get(f"/api/invite/{late}/journal/export?format=pdf").content)
    co = client.get(f"/api/invite/{invs[0]['token']}/journal").json()
    assert any(e["action"] == "offer.frozen" and "€ HT" in e["detail"] for e in co["entries"])


def test_total_montre_au_membre_invite_avant_le_figeage_meme_sans_rattachement_ancien(client, auth, mails):
    """Précision du masquage : l'arrivée du membre est datée par l'entrée « invitation créée »
    (cible = son invitation), pas par sa première entrée rattachée — un membre invité AVANT le
    figeage, dont l'entrée d'invitation est ancienne (sans invite_id), voit bien le total."""
    from app.models import AuditLog
    from app.services import audit
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Le Gall Électricité")["token"]
    inv_id, owner, _ = _invite_row(t)
    db = _db()
    try:
        audit.record(db, action="offer.frozen", owner_id=owner, project_id=pid, actor="user:0", actor_kind="owner",
                     target_type="project", target_id=pid, detail="total 100 000 € HT (convention v1)")
        e = db.query(AuditLog).filter(AuditLog.action == "invite.created", AuditLog.target_id == inv_id).first()
        e.invite_id = None                     # entrée d'avant la colonne invite_id
        db.commit()
    finally:
        db.close()
    assert client.get(f"/api/invite/{t}").status_code == 200      # 1re entrée rattachée : après le figeage
    entries = client.get(f"/api/invite/{t}/journal").json()["entries"]
    frozen = [e for e in entries if e["action"] == "offer.frozen"]
    assert frozen and "100 000 € HT" in frozen[0]["detail"], frozen


# ═══ Dépôt (étape 5) ══════════════════════════════════════════════════════════════════

def test_pret_a_deposer_controle_aussi_les_attestations_du_chef_de_file(client, auth, mails):
    """Le chef de file est membre du groupement : une attestation EXPIRÉE de son coffre-fort est un
    manque (plus de « prêt à déposer » à tort) ; une attestation absente de son coffre-fort est
    seulement signalée (il peut la gérer hors d'Adjugo)."""
    from datetime import date, timedelta
    from app.models import DocCategory, Document, User
    from tests.test_convention_groupement import _groupement
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)

    def pret():
        r = client.get(f"/api/projects/{pid}/groupement/depot", headers=h)
        assert r.status_code == 200, r.text
        return r.json()["pret"]
    p = pret()
    assert any("Vos propres attestations ne sont pas toutes dans votre coffre-fort" in a for a in p["avertissements"])
    assert not any("coffre-fort" in m for m in p["manques"])
    db = _db()
    try:
        uid = db.query(User).filter(User.email == auth["email"]).first().id
        db.add(Document(user_id=uid, name="attestation_urssaf_vigilance.pdf", category=DocCategory.fiscal,
                        file_key="x/urssaf.pdf", file_size=10, mime_type="application/pdf",
                        expiration_date=date.today() - timedelta(days=20)))
        db.commit()
    finally:
        db.close()
    p = pret()
    assert p["checks"]["attestations_ok"] is False and p["pret"] is False
    assert any("(coffre-fort) a expiré" in m for m in p["manques"]), p["manques"]
    # Une attestation à jour (valide après la date limite) remplace l'ancienne.
    db = _db()
    try:
        db.add(Document(user_id=uid, name="attestation_urssaf_2026.pdf", category=DocCategory.fiscal,
                        file_key="x/urssaf2.pdf", file_size=10, mime_type="application/pdf",
                        expiration_date=date.today() + timedelta(days=200)))
        db.commit()
    finally:
        db.close()
    assert not any("coffre-fort" in m for m in pret()["manques"])


def _set_status(pid, value):
    from app.models import Project, ProjectStatus
    db = _db()
    try:
        db.get(Project, pid).status = ProjectStatus(value)
        db.commit()
    finally:
        db.close()


def _n_depose(pid):
    from app.models import AuditLog
    db = _db()
    try:
        return db.query(AuditLog).filter(AuditLog.project_id == pid, AuditLog.action == "groupement.depose").count()
    finally:
        db.close()


def test_marquer_depose_double_clic_une_seule_entree(client, auth, mails):
    """Deux « Marquer déposé » simultanés : un seul passe (transition atomique), une seule entrée
    « déposé » dans le journal de tous les membres ; idem pour l'annulation."""
    import threading
    h = auth["headers"]
    doubles = 0
    for _k in range(4):
        pid = _project(client, h)
        _invite(client, h, pid, "Le Gall Électricité")
        barrier, codes = threading.Barrier(2), []

        def click(method):
            barrier.wait()
            r = client.request(method, f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True})
            codes.append(r.status_code)
        ts = [threading.Thread(target=click, args=("POST",)) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert codes == [200, 200]
        doubles += int(_n_depose(pid) > 1)
    assert doubles == 0


def _depose_entry(pid, statut_precedent):
    """Marquage « déposé » ANCIEN (avant la règle qui refuse un marché abandonné) : statut envoyé
    + entrée de journal portant le statut d'avant."""
    from app.models import Project, ProjectStatus
    from app.services import audit
    db = _db()
    try:
        p = db.get(Project, pid)
        p.status = ProjectStatus.depose
        db.commit()
        audit.record(db, action="groupement.depose", owner_id=p.user_id, project_id=pid, actor="user:0",
                     actor_kind="owner", target_type="project", target_id=pid,
                     meta={"statut_precedent": statut_precedent}, detail="dossier complet")
    finally:
        db.close()


def test_marche_abandonne_refuse_et_annulation_restaure_le_statut_precedent(client, auth, mails):
    """« Marquer déposé » est refusé sur un marché abandonné (409, statut et journal inchangés) ;
    l'annulation d'un marquage restaure EXACTEMENT le statut d'avant (« nouveau », « en cours »,
    et « abandonné » pour un marquage antérieur à la règle) — jamais « en cours » par défaut."""
    h = auth["headers"]
    pid = _project(client, h)
    _invite(client, h, pid, "Le Gall Électricité")
    _set_status(pid, "abandonne")
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "marche_abandonne", r.text
    assert "rouvrez-le" in r.json()["detail"]["message"]
    assert _n_depose(pid) == 0
    assert client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["status"] == "abandonne"
    for avant in ("nouveau", "en_cours"):
        _set_status(pid, avant)
        r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True})
        assert r.status_code == 200 and r.json()["status"] == "depose", r.text
        r = client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h)
        assert r.status_code == 200 and r.json()["etait_depose"] is True and r.json()["status"] == avant, r.json()
    # Marquage ancien d'un marché abandonné : l'annulation le rend « abandonné » (relances coupées).
    _depose_entry(pid, "abandonne")
    r = client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "abandonne", r.json()
    # Une seconde annulation ne fait rien (et n'écrit rien).
    from app.models import AuditLog
    db = _db()
    try:
        n_annul = db.query(AuditLog).filter(AuditLog.project_id == pid,
                                            AuditLog.action == "groupement.depot_annule").count()
    finally:
        db.close()
    r = client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h)
    assert r.json()["etait_depose"] is False and r.json()["status"] == "abandonne"
    db = _db()
    try:
        assert db.query(AuditLog).filter(AuditLog.project_id == pid,
                                         AuditLog.action == "groupement.depot_annule").count() == n_annul
    finally:
        db.close()


def test_annulations_simultanees_une_seule_entree(client, auth, mails):
    """Deux « Retirer le marquage » simultanés : une seule annulation au journal."""
    import threading
    from app.models import AuditLog
    h = auth["headers"]
    pid = _project(client, h)
    _invite(client, h, pid, "Le Gall Électricité")
    for _k in range(3):
        assert client.post(f"/api/projects/{pid}/groupement/deposer", headers=h,
                           json={"confirmer": True}).json()["status"] == "depose"
        barrier, codes = threading.Barrier(2), []

        def click():
            barrier.wait()
            codes.append(client.delete(f"/api/projects/{pid}/groupement/deposer", headers=h).status_code)
        ts = [threading.Thread(target=click) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert codes == [200, 200]
    db = _db()
    try:
        assert db.query(AuditLog).filter(AuditLog.project_id == pid,
                                         AuditLog.action == "groupement.depot_annule").count() == 3
    finally:
        db.close()


# ═══ SRI ══════════════════════════════════════════════════════════════════════════════

def test_sri_integrity_place_avant_src_reste_dans_la_balise():
    """Ancien attribut integrity placé AVANT src : la nouvelle empreinte restait hors de la
    balise (dans le contenu du script) et la protection disparaissait sans bruit."""
    from app.core.sri import apply_integrity
    files = {"/static/app.js": {"integrity": "sha384-NOUVELLE"}}
    for tag in ('<script integrity="sha384-ancienne" src="/static/app.js" defer></script>',
                "<script INTEGRITY='sha384-ancienne' defer src='/static/app.js'></script>",
                '<script src="/static/app.js" integrity="sha384-ancienne" defer></script>'):
        out = apply_integrity(tag, files)
        head, _, rest = out.partition(">")
        assert 'integrity="sha384-NOUVELLE"' in head and "ancienne" not in out, out
        assert rest == "</script>", out
        assert apply_integrity(out, files) == out          # stable : plus rien à corriger


def test_sri_promesse_exacte_sur_les_fichiers_du_serveur():
    """Le filet de production sert un script modifié sur le serveur avec SA propre empreinte : la
    documentation ne promet plus un refus dans ce cas, et dit comment le voir."""
    from app.core import sri
    doc = " ".join(sri.__doc__.split())
    assert "fichier altéré sur le stockage" not in doc
    assert "PAS une protection contre une modification des fichiers sur le serveur" in doc
    contrat = open(os.path.join(os.path.dirname(STATIC), "..", "docs", "COTRAITANCE_V2_VAGUE4_API.md"),
                   encoding="utf-8").read()
    contrat = " ".join(contrat.split())
    assert "Ce que la SRI protège, dit exactement" in contrat and "manifeste_publie_a_jour" in contrat


def test_dpgf_explications_dans_des_bulles():
    """Règle d'interface : les phrases d'explication de la carte « Ma DPGF de lot » sont dans la
    bulle (i) du titre, pas affichées en clair ; la pastille « DPGF du lot reçue » du chef de file
    a sa bulle (le détail des prix de vente, ligne par ligne)."""
    inv = open(os.path.join(STATIC, "invite.html"), encoding="utf-8").read()
    i = inv.index('id="dp-title"')
    titre = inv[i:inv.index("\n", i)]
    assert "<b>Partagé avec le chef de file, au dépôt :</b>" in titre and "<b>Jamais partagé :</b>" in titre
    assert inv.count("Jamais partagé :") == 1 and "dp-share" not in inv
    app = open(os.path.join(STATIC, "app.html"), encoding="utf-8").read()
    from tests.zones import zone
    suivi = zone(app, "marche-suivi-groupement")     # vague 0 : « DPGF du lot reçue » → « Tableau de prix reçu »
    i = suivi.index('v-if="p.has_dpgf_lot"')
    assert "Tableau de prix reçu" in suivi[i:i + 600] and "DPGF" not in suivi[i:i + 600]
    assert 'class="tip"' in suivi[i:i + 700] and "ligne par ligne" in suivi[i:i + 700]
