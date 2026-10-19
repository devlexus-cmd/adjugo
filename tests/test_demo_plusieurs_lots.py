"""
Démo : plusieurs lots, un seul effort (rédaction, vague 6 — J ; app/services/demo_lots.py).

Un marché FICTIF réparti en trois lots (école maternelle Les Hirondelles, Ville de Trémorvan), auquel Bâtiment de
l'Ouest répond sur les lots 2 et 3. Vérifié par l'API, en session démo, sans IA ni réseau :
  - les lots sont repérés dans le règlement fictif (chacun avec sa phrase), la grille vaut pour chacun des lots
    (« Pour chacun des lots, … ») et le dit ;
  - une partie COMMUNE (gestion environnementale) et, pour chaque lot, ses parties propres ; le lot 2 est prêt à
    exporter, le lot 3 en préparation (une partie à écrire) ; aucun fait à relire dans les textes de la démo ;
  - un fichier par lot, nommé comme le règlement l'exige ; limites de pages contrôlées lot par lot ;
  - le visiteur ne change rien (lots, portée, export : refusés, sans coût) ;
  - seed rejouable à l'identique, sans fichier nouveau, isolé dans sa transaction.
"""
import pytest

from app.core.database import SessionLocal
from tests.test_demo_sans_cout import espions  # noqa: F401  (fixture)


def _db():
    return SessionLocal()


def _remise_a_neuf():
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def _vitrine_remise_a_neuf(client):
    _remise_a_neuf()
    yield
    _remise_a_neuf()


@pytest.fixture(scope="module")
def demo(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ps = client.get("/api/projects/", headers=h).json()
    p = next(x for x in ps if "Hirondelles" in x["name"])
    return {"h": h, "pid": p["id"]}


def test_le_marche_a_plusieurs_lots_de_la_vitrine(client, demo):
    from app.services import demo_lots as dl
    from app.services.analysis import citation_guard
    from app.services.dce_lecture import lire_dossier
    h, pid = demo["h"], demo["pid"]
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert st["lots"]["actif"] is True
    assert [(x["numero"], x["intitule"]) for x in st["lots"]["liste"]] == [
        ("2", "Couverture et zinguerie"), ("3", "Étanchéité des toitures-terrasses")]
    texte = "\n".join(p["texte"] for p in lire_dossier(dl.DCE_NOM, dl.dossier_zip(), mode="direct")["pieces"])
    for x in st["lots"]["liste"]:
        assert x["phrase"] and citation_guard(texte, x["phrase"], min_len=4)
        assert x["grille"]["mode"] == "commune" and x["grille"]["phrase"].startswith("Pour chacun des lots")
    assert [x["numero"] for x in st["lots"]["du_marche"]["lots"]] == ["1", "2", "3"]
    assert [(s["lot"], s["numero_affiche"], s["intitule"][:12]) for s in st["sections"]] == [
        ("2", "1.1", "Méthodologie"), ("2", "1.2", "Moyens humai"), ("3", "1.1", "Méthodologie"),
        ("3", "1.2", "Moyens humai"), ("", "1.3", "Gestion envi")]
    assert all(s["faits_a_relire"] == 0 and s["a_completer"] == 0 for s in st["sections"])
    l2, l3 = st["lots"]["liste"]
    assert l2["blocage"]["peut_exporter"] is True and not l2["blocage"]["raisons"]
    assert not [w for w in l2["blocage"]["avertissements"] if w["code"] == "non_valide"]       # « Prêt à exporter »
    assert [r["code"] for r in l3["blocage"]["raisons"]] == ["parties_vides"] and l3["blocage"]["peut_exporter"] is False
    for x in (l2, l3):
        assert x["export"]["nom_fichier_docx"] == f"Lot {x['numero']} - Mémoire technique - Bâtiment de l'Ouest.docx"
        assert x["export"]["nommage"]["selon_reglement"] is True and x["export"]["nommage"]["phrase"] == dl.REGLE_NOMMAGE
        lim = [y for y in x["limites"] if y["portee"] == "document"]
        assert [(y["type"], y["valeur"]) for y in lim] == [("pages", 6)] and not lim[0]["depassee"]
        assert lim[0]["phrase"] == dl.LIMITE
    # La partie commune : une seule partie, un seul texte, dans les deux dossiers.
    com = next(s for s in st["sections"] if s["commune"])
    assert com["id"] in l2["parties"] and com["id"] in l3["parties"] and com["statut"] == "valide"
    assert st["entretien"]["prepare"] is True
    # La carte du marché : un fichier par lot, l'état de chacun.
    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["ai_analysis"]["couverture"]["message"].startswith("Dossier lu en entier : 4 pièces")
    assert [x["statut"] for x in p["ai_analysis"]["details"]["grille_notation"]["criteres"]] == ["retrouve", "retrouve"]


def test_le_visiteur_ne_change_rien_et_rien_ne_coute(client, demo, espions):
    h, pid = demo["h"], demo["pid"]
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    sid = next(s for s in st["sections"] if s["commune"])["id"]
    for m, url, body in (("put", f"/api/atelier/{pid}/lots", {"lots": ["2"]}),
                         ("put", f"/api/atelier/{pid}/sections/{sid}/portee", {"commune": False}),
                         ("post", f"/api/atelier/{pid}/export", {"format": "docx", "lot": "2"}),
                         ("post", f"/api/atelier/{pid}/derogation", {"raison": "autre", "texte": "abc",
                                                                     "etat_hash": "x", "lot": "3"}),
                         ("post", f"/api/atelier/{pid}/sections/{sid}/rediger", {})):
        r = getattr(client, m)(url, headers=h, json=body)
        assert r.status_code == 403 and "lecture guidée" in str(r.json().get("detail")), (url, r.status_code, r.text)
    assert client.get(f"/api/atelier/{pid}/lots", headers=h).status_code == 200
    assert espions["ia"] == [] and espions["fichier"] == [] and espions["email"] == [] and espions["reseau"] == []
    assert client.get(f"/api/atelier/{pid}", headers=h).json()["sections"] == st["sections"]


def test_seed_rejouable_sans_fichier_nouveau_et_isole(client, monkeypatch):
    from app.models import DossierPresentation, Project
    from app.services import demo_lots as dl
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    from app.services.storage import get_storage
    from app.models import User
    avant = set(get_storage().list_keys("demo/"))
    _remise_a_neuf()
    assert set(get_storage().list_keys("demo/")) == avant           # clés liées au contenu : rien ne s'accumule
    assert dl.empreinte() == dl.empreinte()                          # octets stables

    def panne(*a, **k):
        raise RuntimeError("panne simulée")
    monkeypatch.setattr(dl, "dossier_zip", panne)
    db = _db()
    try:
        u = ensure_demo(db, force=True)
        projets = db.query(Project).filter(Project.user_id == u.id).all()
        assert len(projets) == 6 and not any("Hirondelles" in p.name for p in projets)
        toiture = next(p for p in projets if p.name.startswith("Réfection toiture"))
        assert db.query(DossierPresentation).filter(DossierPresentation.project_id == toiture.id).count() == 1
    finally:
        db.close()
    monkeypatch.undo()
    _remise_a_neuf()
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        assert any("Hirondelles" in p.name for p in db.query(Project).filter(Project.user_id == u.id).all())
    finally:
        db.close()
