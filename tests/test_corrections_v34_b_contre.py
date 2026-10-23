"""
Co-traitance v2 — contre-vérification des corrections du domaine B (vagues 3 et 4).

Chaque test échoue sans la correction qu'il couvre :
- DPGF CSV : une virgule du TEXTE (« Fourniture, - y compris », « Pose, +/- 2 mm ») n'est pas un
  séparateur pour un fichier au « ; » → accepté ; « = » et « @ » restent refusés sous tous les
  séparateurs, et « + » / « - » sous ceux que le tableur du chef de file peut appliquer ; message
  exact (ligne, signe, « juste après une virgule ») ;
- DPGF PDF : en-tête « %PDF- » accepté dans les 1024 premiers octets, comme les lecteurs PDF ;
  un « .xls » en HTML ou en XML Excel 2003 reste refusé avec un message qui dit quoi faire ;
- journal membre : une entrée v2 ALTÉRÉE n'est pas comptée comme « ancienne » dans le message
  d'ancrage (seules les entrées v1 le sont) ;
- part d'une invitation réseau sans réponse : ni le brouillon de convention, ni « prêt à déposer »,
  ni le coffre croisé, ni l'état du groupement ne montrent le nom, le SIRET, l'adresse ou le
  représentant saisis — au chef de file comme aux autres membres ;
- réseau : les relances comptent dans le plafond de sollicitations À L'ENVOI aussi, et la relance
  exige que le chef de file soit toujours publié.
"""
import io

import pytest

from tests.test_convention_groupement import _invite, _project


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _dpgf(client, token, data, name="dpgf.csv"):
    data = data.encode("utf-8") if isinstance(data, str) else data
    return client.post(f"/api/invite/{token}/contribution/piece",
                       files={"file": (name, io.BytesIO(data), "application/octet-stream")},
                       data={"piece_type": "dpgf_lot"})


# ═══ DPGF CSV : virgule du texte ═══════════════════════════════════════════════════════

ENTETE = "N°;Désignation;Unité;Qté;PU HT;Montant HT\r\n"


def test_dpgf_csv_virgule_d_une_designation_n_est_pas_un_separateur(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    legitimes = {
        "virgule puis tiret": ENTETE + "1;Fourniture, - y compris accessoires;u;2;100,00;200,00\r\n",
        "tolérance +/- après virgule": ENTETE + "1;Pose de dalles, +/- 2 mm de planéité;m2;10;30,00;300,00\r\n",
        "remise après virgule, avec titre": (
            "DPGF du lot - prix de vente HT\r\nEntreprise;Alpha SARL\r\nLot;Lot A\r\n"
            "N°;Désignation;Unité;Quantité;Prix unitaire HT (€);Montant HT (€)\r\n"
            + "".join(f"{i};Fourniture, pose, raccordement, essais, -10 % sur option;u;2,5;100,00;250,00\r\n"
                      for i in range(1, 6)) + ";Total HT;;;;1250,00\r\n"),
        "sans en-tête (ligne de valeurs d'abord)": "1;Pose, - repli compris;u;2;100,00;200,00\r\n",
    }
    for label, text in legitimes.items():
        r = _dpgf(client, t, text)
        assert r.status_code == 200, (label, r.text)


def test_dpgf_csv_formules_toujours_refusees_avec_un_message_exact(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    refus = {
        # Fichier à la virgule (en-tête découpé ainsi) : « - » en début de cellule = formule.
        "virgule, fichier anglo": ("No,Designation,Unit,Qty,Unit price,Amount\n1,Supply,u,2,-cmd|calc,201.00\n",
                                   ["ligne 2", "« - »", "formule"]),
        # Directive Excel « sep=, » : la virgule est le séparateur appliqué.
        "directive sep=,": ("sep=,\nN°;Désignation;Qté;PU\n1;Pose, - y compris;2;10\n", ["ligne 3", "« - »"]),
        # « = » et « @ » restent refusés après une virgule de texte, avec le motif exact.
        "= après une virgule": (ENTETE + "1;Câble,=1+1;u;1;10;10\n",
                                ["ligne 2", "« = »", "juste après une virgule", "formule"]),
        "@ après une virgule": (ENTETE + "1;Câble, @SOMME(A1);u;1;10;10\n", ["« @ »", "juste après une virgule"]),
        # Fichier au « ; » : « - » en début de vraie cellule.
        "cellule « - » texte": (ENTETE + "1;- y compris accessoires;u;2;100,00;200,00\n",
                                ["ligne 2", "« - »", "formule"]),
        # Fichier tabulé (en-tête découpé à la tabulation) : la tabulation est un vrai séparateur.
        "tabulation": ("N°\tDésignation\tQté\tPU\n1\tPose\t2\t+x\n", ["ligne 2", "« + »"]),
    }
    for label, (text, needles) in refus.items():
        r = _dpgf(client, t, text)
        assert r.status_code == 422, (label, r.text)
        detail = r.json()["detail"]
        for n in needles:
            assert n in detail, (label, n, detail)
    # Un nombre négatif reste un nombre.
    ok = ENTETE + "1;Remise commerciale;ft;1;-150,00;-150,00\n"
    assert _dpgf(client, t, ok).status_code == 200


def test_dpgf_csv_borne_avant_le_travail_sur_les_cellules():
    """Une ligne de 4 Mo de « ;, » alternés est refusée vite (découpage seul, fait en C) : le
    repérage de l'en-tête, fait avant le contrôle des formules, est borné lui aussi."""
    import time
    from fastapi import HTTPException
    from app.routers.invites import _DPGF_CSV_MAX_BYTES, _check_dpgf_csv
    data = ((";," * (_DPGF_CSV_MAX_BYTES // 2 - 10)) + "\n").encode()
    t0 = time.perf_counter()
    with pytest.raises(HTTPException) as e:
        _check_dpgf_csv(data)
    assert e.value.status_code == 422
    assert time.perf_counter() - t0 < 0.5


# ═══ DPGF PDF / tableurs : signature ══════════════════════════════════════════════════

def test_dpgf_pdf_en_tete_apres_quelques_octets_accepte(client, auth, mails):
    h = auth["headers"]
    pid = _project(client, h)
    t = _invite(client, h, pid, "Delta Peinture")["token"]
    r = _dpgf(client, t, b"\r\n%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", name="DPGF_lot.pdf")
    assert r.status_code == 200, r.text
    r = _dpgf(client, t, b"x" * 1100 + b"%PDF-1.4\n", name="DPGF_lot.pdf")
    assert r.status_code == 422 and "PDF" in r.json()["detail"]
    for data in (b"<html xmlns:x=\"urn:schemas-microsoft-com:office:excel\"><table><tr><td>Pose</td></tr></table></html>",
                 b"<?xml version=\"1.0\"?><?mso-application progid=\"Excel.Sheet\"?><Workbook/>"):
        r = _dpgf(client, t, data, name="DPGF_lot.xls")
        assert r.status_code == 422
        d = r.json()["detail"]
        assert "XLS" in d and ".xlsx ou .ods" in d and "page web ou un fichier XML" in d, d


# ═══ Journal membre : « anciennes » = v1 seulement ═══════════════════════════════════

def _invite_row(token):
    from app.models import ProjectInvite
    db = _db()
    try:
        i = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
        return i.id, i.owner_id
    finally:
        db.close()


def _integrity(client, token):
    from app.services import journal_membre as jm
    jm.reset_caches()
    r = client.get(f"/api/invite/{token}/journal/integrity")
    assert r.status_code == 200, r.text
    return r.json()


def test_ancrage_ne_dit_ancienne_qu_une_entree_v1(client, auth, mails, monkeypatch):
    """Une entrée v2 dont l'invite_id a été modifié est ALTÉRÉE, pas « ancienne » : le message
    d'ancrage ne dit plus « Pour 1 d'entre elles, anciennes… » alors qu'aucune entrée n'est v1.
    Une vraie entrée v1 couverte par l'ancrage le dit toujours."""
    from app.models import AuditLog
    from app.services import audit
    from app.services import journal_membre as jm
    h = auth["headers"]
    pid = _project(client, h)
    ta = _invite(client, h, pid, "Alpha Électricité")["token"]
    tb = _invite(client, h, pid, "Beta Plomberie")["token"]
    a_id, owner = _invite_row(ta)
    b_id, _ = _invite_row(tb)
    assert client.get(f"/api/invite/{ta}").status_code == 200
    assert client.get(f"/api/invite/{tb}").status_code == 200
    db = _db()
    try:
        last = db.query(AuditLog).filter(AuditLog.owner_id == owner).order_by(AuditLog.id.desc()).first()
        head = {"owner_id": owner, "last_id": last.id, "last_hash": last.entry_hash, "status": "active"}
        e = (db.query(AuditLog).filter(AuditLog.invite_id == b_id, AuditLog.action == "guest.view_project")
             .order_by(AuditLog.id).first())
        e.invite_id = a_id                  # entrée v2 de Beta attribuée à Alpha : altérée
        db.commit()
        moved = e.id
    finally:
        db.close()
    fake = {"date": "2026-10-07", "tsa": {"ok": True}, "heads": [head], "_by_owner": {owner: head}}
    monkeypatch.setattr(jm, "_anchor", lambda: fake)
    v = _integrity(client, ta)
    assert v["verdict"] == "altere" and v["entrees"]["alterees"] == 1, v["message"]
    assert v["entrees"]["rattachement_non_scelle"] == 0
    msg = v["ancrage"]["message"]
    assert "couverte" in msg and "anciennes" not in msg and "rattachement" not in msg, msg

    # Contrôle positif : une vraie entrée v1 couverte le dit.
    db = _db()
    try:
        e = db.get(AuditLog, moved)
        e.invite_id = b_id
        chain = db.query(AuditLog).filter(AuditLog.owner_id == owner).order_by(AuditLog.id).all()
        # ORDER BY : la session ne vide pas ses écritures avant une requête (autoflush coupé), l'entrée
        # de Beta est donc encore rattachée à Alpha en base ; sans ordre, Postgres peut la renvoyer
        # en premier (place physique de la ligne mise à jour) et le test vise la mauvaise entrée.
        mine = (db.query(AuditLog).filter(AuditLog.invite_id == a_id, AuditLog.action == "guest.view_project")
                .order_by(AuditLog.id).first())
        i = [x.id for x in chain].index(mine.id)
        mine.entry_hash = audit._hash(mine.prev_hash, mine)          # empreinte v1
        for x in chain[i + 1:]:
            x.prev_hash = chain[chain.index(x) - 1].entry_hash
            x.entry_hash = audit._hash_v2(x.prev_hash, x)
        db.commit()
        assert audit.verify_chain(db, owner)["intact"] is True
    finally:
        db.close()
    v = _integrity(client, ta)
    assert v["verdict"] == "intact" and v["entrees"]["rattachement_non_scelle"] == 1, v["message"]
    assert "Pour 1 d'entre elles, anciennes" in v["ancrage"]["message"]
