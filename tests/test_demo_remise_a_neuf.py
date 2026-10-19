"""
Démo PARTAGÉE entre plusieurs présentations (13/10/2026) : la vitrine se retrouve toujours intacte.

1. Les écritures qui abîmaient la vitrine sont refusées à la session démo (« lecture guidée »), par le
   garde central ET dans la route : supprimer ou modifier un marché (seul le changement d'étape reste
   permis), supprimer ou renommer un document, modifier le profil entreprise ou les critères, modifier
   ou supprimer un partenaire, rattacher ou détacher un partenaire d'un marché.
2. Remise à neuf automatique (app/services/demo_remise.py) : à l'ouverture d'une session démo, si
   aucune session démo n'a fait de requête depuis DEMO_REMISE_A_NEUF_MIN minutes (30 par défaut), les
   deux démos sont recréées avant de délivrer la session. Jamais si une session est active ; une
   erreur du seed n'empêche jamais l'ouverture. Horloge simulée, aucune IA, aucun fichier nouveau.
"""
import time

import pytest

from app.core.database import SessionLocal
from tests.test_demo_sans_cout import _cle_neuve, espions  # noqa: F401  (fixture)

MIN = 60.0


def _db():
    return SessionLocal()


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


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


@pytest.fixture
def horloge(monkeypatch):
    """Horloge simulée du suivi d'activité. À la fin, le suivi repart de l'horloge réelle (sinon une
    trace « simulée » déclencherait une remise à neuf dans les tests suivants)."""
    from app.services import demo_remise
    t = {"now": 1000.0}
    monkeypatch.setattr(demo_remise, "_horloge", lambda: t["now"])
    monkeypatch.delenv("DEMO_REMISE_A_NEUF_MIN", raising=False)
    demo_remise._reinitialiser_pour_tests()
    demo_remise.noter_remise()                    # comme au démarrage du serveur : vitrine neuve
    yield t
    monkeypatch.undo()
    demo_remise._reinitialiser_pour_tests()
    demo_remise.noter_remise()


def _session(client, corps=None) -> dict:
    r = client.post("/api/auth/demo", json=corps)
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _projets(client, h) -> dict:
    return {p["name"]: p for p in client.get("/api/projects/", headers=h).json()}


def _kerhel(client, h) -> dict:
    return next(p for n, p in _projets(client, h).items() if "Kerhel" in n)


def _toiture(client, h) -> dict:
    return next(p for n, p in _projets(client, h).items() if n.startswith("Réfection toiture"))


def _abimer(client, h) -> None:
    """Ce qu'un visiteur laisse derrière lui avec les écritures qui restent ouvertes."""
    k = _kerhel(client, h)
    assert client.put(f"/api/projects/{k['id']}", headers=h, json={"status": "envoye"}).status_code == 200
    r = client.post("/api/projects/", headers=h, json={"name": "Marché ajouté pendant une présentation"})
    assert r.status_code == 201, r.text
    assert client.post("/api/contacts/", headers=h, json={"name": "Contact d'un visiteur"}).status_code == 201


def _est_abimee(client, h) -> bool:
    return "Marché ajouté pendant une présentation" in _projets(client, h)


def _vitrine_intacte(client, h) -> None:
    """La vitrine d'origine : 7 marchés (dont celui à plusieurs lots, rédaction vague 6), Kerhel « Validée par tous les
    membres », toiture intacte."""
    ps = _projets(client, h)
    assert len(ps) == 7 and "Marché ajouté pendant une présentation" not in ps
    k = _kerhel(client, h)
    assert k["status"] == "en_cours"
    cv = client.get(f"/api/projects/{k['id']}/groupement/convention", headers=h).json()
    assert cv["status_label"] == "Validée par tous les membres" and cv["n_accords"] == 2
    dp = client.get(f"/api/projects/{k['id']}/groupement/depot", headers=h).json()
    assert dp["depose"] is False and dp["pret"]["n_ok"] == 3
    t = _toiture(client, h)
    assert t["match_score"] == 87 and t["status"] == "en_cours"
    det = client.get(f"/api/projects/{t['id']}", headers=h).json()["ai_analysis"]["details"]
    assert [x["statut"] for x in det["grille_notation"]["criteres"]] == ["retrouve"] * 6
    assert len(client.get("/api/preuves", headers=h).json()["preuves"]) == 14
    assert client.get(f"/api/atelier/{t['id']}", headers=h).json()["dossier"]["plan_source"] == "grille"
    assert "Contact d'un visiteur" not in [c["name"] for c in client.get("/api/contacts/", headers=h).json()]


# ── 1. Écritures qui abîmaient la vitrine : refusées ─────────────────────────────────────────────

def _ids(client, h) -> dict:
    from app.models import Document, User
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.services.demo_seed import DEMO_EMAIL
    k, t = _kerhel(client, h), _toiture(client, h)
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        breizh = db.query(Cotraitant).filter(Cotraitant.user_id == u.id, Cotraitant.name == "Breizh Désamiantage").one()
        lien = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == k["id"]).one()
        doc = db.query(Document).filter(Document.user_id == u.id, Document.name.like("Extrait Kbis%")).one()
        return {"kerhel": k["id"], "toiture": t["id"], "breizh": breizh.id, "lien": lien.id, "doc": doc.id}
    finally:
        db.close()


def _ecritures(i: dict) -> list:
    return [
        ("DELETE", f"/api/projects/{i['toiture']}", None),
        ("PUT", f"/api/projects/{i['kerhel']}", {"name": "Nom changé par un visiteur"}),
        ("PUT", f"/api/projects/{i['kerhel']}", {"client": "Autre acheteur"}),
        ("PUT", f"/api/projects/{i['kerhel']}", {"status": "en_cours", "budget": 1.0}),
        ("PUT", f"/api/projects/{i['toiture']}", {"tva_rate": 20}),
        ("PUT", f"/api/projects/{i['toiture']}", {"outcome_reason": "Prix", "awarded_amount": 1.0}),
        ("PATCH", f"/api/documents/{i['doc']}", {"name": "Renommé par un visiteur"}),
        ("DELETE", f"/api/documents/{i['doc']}", None),
        ("POST", "/api/company/", {"name": "Pirate SARL"}),
        ("PUT", "/api/company/", {"name": "Pirate SARL"}),
        ("PUT", "/api/criteria/", {"specialites": "informatique"}),
        ("PUT", f"/api/cotraitants/{i['breizh']}", {"name": "Partenaire renommé"}),
        ("DELETE", f"/api/cotraitants/{i['breizh']}", None),
        ("POST", f"/api/cotraitants/project/{i['kerhel']}", {"cotraitant_id": i["breizh"], "role": "sous_traitant"}),
        ("DELETE", f"/api/cotraitants/project/{i['kerhel']}/{i['lien']}", None),
    ]


def _photo(client, h) -> dict:
    return {"projets": sorted((p["name"], p["client"], p["status"], p.get("budget"), p.get("tva_rate"))
                              for p in _projets(client, h).values()),
            "company": client.get("/api/company/", headers=h).json()["name"],
            "criteres": client.get("/api/criteria/", headers=h).json(),
            "documents": sorted(d["name"] for d in client.get("/api/documents/", headers=h).json()),
            "partenaires": sorted((c["name"], c["ca_n1"]) for c in client.get("/api/cotraitants/", headers=h).json())}


@pytest.mark.parametrize("garde", [True, False], ids=["avec le garde central", "sans le garde (défense en profondeur)"])
def test_ecritures_qui_abiment_la_vitrine_refusees(client, monkeypatch, garde):
    if not garde:
        import app.core.demo_guard as g
        monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)
    h = _session(client)
    i = _ids(client, h)
    avant = _photo(client, h)
    for methode, url, corps in _ecritures(i):
        r = client.request(methode, url, headers=h, json=corps)
        assert r.status_code == 403, (methode, url, r.status_code, r.text)
        assert r.json()["detail"].startswith("La démo est en lecture guidée"), (methode, url, r.text)
    assert _photo(client, h) == avant
    k = client.get(f"/api/projects/{i['kerhel']}/groupement/convention", headers=h).json()
    assert k["status"] == "signee"                                  # le groupement de la vitrine est intact


def test_changement_d_etape_toujours_permis(client):
    """Le tableau des marchés reste interactif : la démo déplace un marché d'étape (et le remet)."""
    h = _session(client)
    t = _toiture(client, h)
    r = client.put(f"/api/projects/{t['id']}", headers=h, json={"status": "envoye"})
    assert r.status_code == 200 and r.json()["status"] == "envoye"
    r = client.put(f"/api/projects/{t['id']}", headers=h, json={"status": "en_cours"})
    assert r.status_code == 200 and r.json()["status"] == "en_cours"


def test_un_vrai_compte_garde_toutes_ses_ecritures(client, auth):
    """Les refus ne visent que la démo."""
    h = auth["headers"]
    p = client.post("/api/projects/", headers=h, json={"name": "Marché réel", "client": "Ville"}).json()
    r = client.put(f"/api/projects/{p['id']}", headers=h, json={"name": "Marché renommé", "budget": 10.0})
    assert r.status_code == 200 and r.json()["name"] == "Marché renommé"
    assert client.put("/api/company/", headers=h, json={"name": "Ma SARL"}).status_code == 200
    assert client.put("/api/criteria/", headers=h, json={"specialites": "toiture"}).status_code == 200
    ct = client.post("/api/cotraitants/", headers=h, json={"name": "Partenaire"}).json()
    assert client.put(f"/api/cotraitants/{ct['id']}", headers=h, json={"name": "Partenaire 2"}).status_code == 200
    lien = client.post(f"/api/cotraitants/project/{p['id']}", headers=h, json={"cotraitant_id": ct["id"]}).json()
    assert client.delete(f"/api/cotraitants/project/{p['id']}/{lien['link_id']}", headers=h).status_code == 200
    assert client.delete(f"/api/cotraitants/{ct['id']}", headers=h).status_code == 200
    assert client.delete(f"/api/projects/{p['id']}", headers=h).status_code == 204


# ── 2. Remise à neuf automatique entre deux présentations ───────────────────────────────────────

def test_remise_a_neuf_apres_inactivite(client, horloge, espions):  # noqa: F811
    """Une présentation laisse la vitrine abîmée ; 31 minutes sans aucune session démo ; la suivante
    retrouve la vitrine d'origine (ouverte par le lien privé, comme en production). Sans IA, sans
    email, sans réseau, sans fichier nouveau."""
    h = _session(client)
    _abimer(client, h)
    assert _est_abimee(client, h)
    horloge["now"] += 31 * MIN
    espions["fichier"].clear()
    t0 = time.perf_counter()
    h2 = _session(client)
    duree = time.perf_counter() - t0
    _vitrine_intacte(client, h2)
    _vitrine_intacte(client, h)                   # la session précédente voit la même vitrine propre
    assert espions["ia"] == [] and espions["email"] == [] and espions["reseau"] == []
    assert espions["fichier"] == []               # seed idempotent : aucun fichier nouveau
    print(f"\nremise à neuf + ouverture de la session : {duree:.2f} s")


def test_remise_a_neuf_par_le_lien_prive(client, horloge, monkeypatch):
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    cle = _cle_neuve()
    monkeypatch.setenv("DEMO_LIEN_CLE", cle)
    h = _session(client, {"cle": cle})
    _abimer(client, h)
    horloge["now"] += 30 * MIN
    h2 = _session(client, {"cle": cle})
    _vitrine_intacte(client, h2)


def test_pas_de_remise_a_neuf_pendant_qu_une_session_est_active(client, horloge):
    """Une présentation en cours (requêtes de sa session, ou de son lien partenaire) n'est jamais
    remise à neuf sous ses pieds, même si une autre session s'ouvre."""
    h = _session(client)
    _abimer(client, h)
    horloge["now"] += 20 * MIN
    assert client.get("/api/projects/", headers=h).status_code == 200      # la présentation continue
    horloge["now"] += 20 * MIN                                              # 40 min depuis le démarrage
    _session(client)
    assert _est_abimee(client, h)
    # Le lien partenaire de la vitrine, montré pendant la présentation, compte aussi.
    from app.models import ProjectInvite
    db = _db()
    try:
        tok = db.query(ProjectInvite).filter(ProjectInvite.project_id == _kerhel(client, h)["id"]).one().token
    finally:
        db.close()
    horloge["now"] += 25 * MIN
    assert client.get(f"/api/invite/{tok}").status_code == 200
    horloge["now"] += 25 * MIN
    _session(client)
    assert _est_abimee(client, h)
    # Une seule session qui s'ouvre après 30 minutes sans rien : remise à neuf.
    horloge["now"] += 31 * MIN
    _session(client)
    assert not _est_abimee(client, h)


def test_ouverture_cote_collectivites_remet_aussi_a_neuf(client, horloge):
    """L'espace collectivités s'ouvre aussi par /demo : la même remise à neuf recrée les deux démos
    (DCE d'exemple recréés, dates de pilotage à jour)."""
    from app.models import Acheteur, AcheteurDce
    from app.services.acheteur_demo_seed import DEMO_EMAIL as ACH
    h = _session(client)
    _abimer(client, h)
    r = client.post("/api/acheteur/demo")
    assert r.status_code == 200
    db = _db()
    try:   # une dérive des DCE d'exemple (le compte est en lecture seule : simulée en base)
        a_id = db.query(Acheteur).filter(Acheteur.email == ACH).one().id
        d = db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a_id).order_by(AcheteurDce.id).first()
        d.statut, d.nb_pme_diffusion = "infructueux", 999
        db.commit()
    finally:
        db.close()
    horloge["now"] += 31 * MIN
    r = client.post("/api/acheteur/demo")
    assert r.status_code == 200
    ha = _h(r.json()["access_token"])
    assert len(client.get("/api/acheteur/dce", headers=ha).json()) == 2
    db = _db()
    try:
        apres = db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a_id).all()
        assert len(apres) == 2
        assert not [x for x in apres if x.nb_pme_diffusion == 999]
    finally:
        db.close()
    _vitrine_intacte(client, h)                   # la démo entreprises aussi


def test_delai_reglable(client, horloge, monkeypatch):
    """DEMO_REMISE_A_NEUF_MIN règle le délai ; 0 désactive la remise à neuf automatique."""
    monkeypatch.setenv("DEMO_REMISE_A_NEUF_MIN", "5")
    h = _session(client)
    _abimer(client, h)
    horloge["now"] += 4 * MIN
    _session(client)
    assert _est_abimee(client, h)
    horloge["now"] += 6 * MIN
    _session(client)
    assert not _est_abimee(client, h)
    monkeypatch.setenv("DEMO_REMISE_A_NEUF_MIN", "0")
    _abimer(client, h)
    horloge["now"] += 600 * MIN
    _session(client)
    assert _est_abimee(client, h)
    _remise_a_neuf()


def test_erreur_du_seed_sans_effet_sur_l_ouverture(client, horloge, monkeypatch):
    """Le seed qui échoue pendant la remise à neuf est journalisé ; la session s'ouvre quand même, sur
    la vitrine existante (entreprises et collectivités)."""
    from app.services import acheteur_demo_seed, demo_seed
    orig, orig_ach = demo_seed.ensure_demo, acheteur_demo_seed.ensure_demo_acheteur

    def en_panne(db, force=False):
        if force:
            raise RuntimeError("panne simulée du seed")
        return orig(db, force=force)

    def en_panne_ach(db, force=False):
        if force:
            raise RuntimeError("panne simulée du seed")
        return orig_ach(db, force=force)
    monkeypatch.setattr(demo_seed, "ensure_demo", en_panne)
    monkeypatch.setattr(acheteur_demo_seed, "ensure_demo_acheteur", en_panne_ach)
    h = _session(client)
    _abimer(client, h)
    horloge["now"] += 31 * MIN
    h2 = _session(client)
    assert client.get("/api/auth/me", headers=h2).json()["email"] == "demo@adjugo.fr"
    assert _est_abimee(client, h2)                # la remise à neuf n'a pas eu lieu, la session est là
    horloge["now"] += 31 * MIN
    r = client.post("/api/acheteur/demo")
    assert r.status_code == 200
    assert client.get("/api/acheteur/me", headers=_h(r.json()["access_token"])).json()["demo"] is True
    monkeypatch.undo()
    _remise_a_neuf()
