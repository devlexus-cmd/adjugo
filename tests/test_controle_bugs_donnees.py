"""Contrôle des bugs d'octobre 2026, groupe « données » (sauvegardes, inscription, tâches planifiées, fin des pièces) :
chaque test dit ce que le logiciel DOIT faire d'après ses contrats et ses textes ; tous échouaient sur cfe04e1 (et sur
a545256, avant cette correction), chacun sur son défaut, sur SQLite comme sur PostgreSQL.

1. (31) Restaurer une sauvegarde (docs/GO_LIVE.md, étape 4) dans une base au schéma de la production : sur PostgreSQL,
   refusée net (organizations.owner_id → users et users.org_id → organizations, liens en cycle), puis la première
   inscription refusée (compteurs de numéros restés à 1) ; sur les deux moteurs, un champ JSON vide revenait comme le
   texte « null ».
2. (32) Une sauvegarde est un instantané : un marché et sa pièce écrits pendant la lecture n'y laissent jamais la pièce
   sans son marché.
3. (33) Deux inscriptions de la même adresse au même instant : un compte créé, l'autre envoi refusé comme un doublon
   (400 « Cet email est déjà utilisé »), plus une erreur interne 500.
4. (35) Alerte d'attestations d'un partenaire : rien n'est noté « alerté » tant que le courriel n'est pas parti ; le
   passage suivant la renvoie, au partenaire et dans le récapitulatif du chef de file.
5. (37) « Pièces à fournir » et « Prêt à déposer » jugent une pièce expirée au jour de Paris, comme Mes documents.

Lancement : ADJUGO_TEST_DB=donnees.db TZ=UTC python -m pytest -q -p no:warnings tests/test_controle_bugs_donnees.py
"""
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, timezone

import pytest

from app.core.database import SessionLocal

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Stockage:
    """Stockage objet en mémoire (à la place de R2)."""

    def __init__(self):
        self.objets = {}

    def save(self, key, data, content_type=""):
        self.objets[key] = bytes(data)
        return key

    def load(self, key):
        return self.objets[key]

    def delete(self, key):
        self.objets.pop(key, None)

    def list_keys(self, prefix=""):
        return [k for k in self.objets if k.startswith(prefix)]


def _sauvegarde_en_memoire(monkeypatch):
    from app.core.config import get_settings
    from app.services import backup, storage
    st = _Stockage()
    monkeypatch.setattr(storage, "get_storage", lambda: st)
    monkeypatch.setattr(backup, "_backend_is_object", lambda: True)
    monkeypatch.setattr(get_settings(), "BACKUP_PUBLIC_KEY", "")
    return st


# ── 1. (31) Restaurer une sauvegarde dans une base au schéma de la production ─────────────────────────────────────

@pytest.fixture
def base_neuve(tmp_path):
    """Une base vide montée comme en production, sur le moteur de la suite : PostgreSQL, `alembic upgrade head` sur une
    base créée pour ce test (supprimée après) ; SQLite, ce que fait app/main.py (create_all puis colonnes ajoutées)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from app.core.database import Base, engine as moteur_app
    if moteur_app.dialect.name == "postgresql":
        from tests import _base_postgres as bp
        serveur = bp._ETAT["serveur"]
        nom = f"adjugo_restauration_{uuid.uuid4().hex[:8]}"
        adm = create_engine(serveur, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        with adm.connect() as c:
            c.execute(text(f'CREATE DATABASE "{nom}"'))
        url = bp._avec_base(serveur, nom)
        p = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RACINE,
                           env=dict(os.environ, DATABASE_URL=url), capture_output=True, text=True)
        assert p.returncode == 0, p.stderr[-3000:]
        moteur = create_engine(url, poolclass=NullPool, connect_args={"options": "-c timezone=UTC"})
        try:
            yield moteur
        finally:
            moteur.dispose()
            with adm.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
            adm.dispose()
    else:
        from app.core.dbsync import ensure_sqlite_columns, ensure_sqlite_statuts
        moteur = create_engine(f"sqlite:///{tmp_path}/restauration_test.db", poolclass=NullPool)
        Base.metadata.create_all(bind=moteur)
        ensure_sqlite_columns(moteur, Base)
        ensure_sqlite_statuts(moteur)
        try:
            yield moteur
        finally:
            moteur.dispose()


def test_d1_restauration_dans_une_base_neuve_puis_deja_remplie_puis_inscription(client, auth, monkeypatch, base_neuve):
    """Procédure docs/GO_LIVE.md, étape 4 (« Attendu : {'ok': True, …} »), sur le moteur de la production. Avant :
    PostgreSQL refusait la restauration (« organizations viole la clé étrangère fk_org_owner », puis, base déjà
    remplie, « users » à la purge) ; une fois ce point passé, la première inscription était refusée (« users_pkey,
    Key (id)=(1) already exists ») ; sur les deux moteurs, groupement_plan et ai_analysis vides revenaient comme le
    texte JSON « null » (« IS NULL » faux)."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from app.core.security import hash_password
    from app.models import Organization, Project, User
    from app.services import backup
    st = _sauvegarde_en_memoire(monkeypatch)
    r = client.post("/api/projects/", json={"name": "Marché à restaurer", "client": "Mairie"}, headers=auth["headers"])
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    db = SessionLocal()
    try:
        uid = db.query(User.id).filter(User.email == auth["email"]).scalar()
        org = db.query(Organization).filter(Organization.owner_id == uid).one()   # le lien en cycle existe
        oid = org.id
        assert db.execute(text("SELECT count(*) FROM projects WHERE id = :p AND ai_analysis IS NULL "
                               "AND groupement_plan IS NULL"), {"p": pid}).scalar() == 1
    finally:
        db.close()
    res = backup.run_backup(keep=14)
    assert res["ok"], res
    blob = st.objets[res["key"]]
    tables = json.loads(gzip.decompress(blob))["tables"]
    n_users, n_projets = len(tables["users"]), len(tables["projects"])
    plus_grand_compte = max(u["id"] for u in tables["users"])

    Session = sessionmaker(bind=base_neuve)
    for passage in (1, 2):                    # base vide, puis base déjà remplie par la première restauration
        db2 = Session()
        try:
            out = backup.restore_backup(blob, db2)
            assert out["ok"], out
            with base_neuve.connect() as c:
                assert c.execute(text("SELECT count(*) FROM users")).scalar() == n_users
                assert c.execute(text("SELECT count(*) FROM projects")).scalar() == n_projets
                assert c.execute(text("SELECT owner_id FROM organizations WHERE id = :o"), {"o": oid}).scalar() == uid
                assert c.execute(text("SELECT org_id FROM users WHERE id = :u"), {"u": uid}).scalar() == oid
                assert c.execute(text("SELECT count(*) FROM projects WHERE id = :p AND ai_analysis IS NULL "
                                      "AND groupement_plan IS NULL"), {"p": pid}).scalar() == 1, \
                    f"passage {passage} : un champ JSON vide doit rester vide"
            p = db2.get(Project, pid)
            assert p.name == "Marché à restaurer" and p.ai_analysis is None and p.groupement_plan is None
            # Une inscription après la restauration : un numéro libre, au-dessus des numéros restaurés.
            email = f"apres_restauration_{passage}_{uuid.uuid4().hex[:6]}@test.fr"
            db2.add(User(email=email, hashed_password=hash_password("motdepasse123"), full_name="Après",
                         is_active=True))
            db2.commit()
            assert db2.query(User).filter(User.email == email).one().id > plus_grand_compte
        finally:
            db2.close()


# ── 2. (32) La sauvegarde lit toutes les tables dans un seul instantané ───────────────────────────────────────────

def test_d2_sauvegarde_instantanee_jamais_une_piece_sans_son_marche(client, auth, monkeypatch):
    """Une autre connexion enregistre un marché et sa pièce au moment où la sauvegarde va lire la table des pièces
    (la table des marchés est déjà lue). Avant : la pièce était dans la sauvegarde, pas son marché (PostgreSQL refuse
    ensuite toute la restauration : clé étrangère fk_documents_project_id). Attendu : aucune pièce sans son marché ;
    sur PostgreSQL l'écriture passe et la sauvegarde ne la voit pas ; sur SQLite elle attend la fin de la lecture."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    import app.core.database as base_mod
    from app.models import Document, Project, User
    from app.services import backup
    st = _sauvegarde_en_memoire(monkeypatch)
    r = client.post("/api/projects/", json={"name": "Marché d'avant", "client": "Mairie"}, headers=auth["headers"])
    assert r.status_code in (200, 201), r.text
    pid_avant = r.json()["id"]
    db = SessionLocal()
    try:
        uid = db.query(User.id).filter(User.email == auth["email"]).scalar()
    finally:
        db.close()
    sqlite = base_mod.engine.dialect.name == "sqlite"
    ecrivain = create_engine(base_mod.engine.url, poolclass=NullPool,
                             connect_args={"timeout": 1, "check_same_thread": False} if sqlite
                             else {"options": "-c timezone=UTC"})
    etat = {"fait": False}

    def _ecrire_pendant():
        s = sessionmaker(bind=ecrivain)()
        try:
            p = Project(user_id=uid, name="Marché écrit pendant", client="Mairie")
            s.add(p)
            s.flush()
            s.add(Document(user_id=uid, project_id=p.id, name="Pièce écrite pendant", file_key=f"{uid}/pendant.pdf",
                           file_size=1, mime_type="application/pdf"))
            s.commit()
            etat["ecrit"] = True
        except Exception as e:       # noqa: BLE001 — SQLite : la base est tenue par la lecture de la sauvegarde
            s.rollback()
            etat["ecrit"], etat["erreur"] = False, type(e).__name__
        finally:
            s.close()

    def _avant_lecture(conn, cursor, statement, params, context, executemany):
        if not etat["fait"] and statement.lstrip().upper().startswith("SELECT") \
                and re.search(r"\bFROM\s+\"?documents\"?(\s|$)", statement):
            etat["fait"] = True
            _ecrire_pendant()

    event.listen(base_mod.engine, "before_cursor_execute", _avant_lecture)
    try:
        res = backup.run_backup(keep=14)
    finally:
        event.remove(base_mod.engine, "before_cursor_execute", _avant_lecture)
        ecrivain.dispose()
    assert res["ok"], res
    assert etat["fait"], "la sauvegarde n'a pas lu la table des pièces"
    tables = json.loads(gzip.decompress(st.objets[res["key"]]))["tables"]
    marches = {p["id"] for p in tables["projects"]}
    assert pid_avant in marches
    orphelines = [d["name"] for d in tables["documents"] if d.get("project_id") and d["project_id"] not in marches]
    assert orphelines == [], f"pièces sans leur marché dans la sauvegarde : {orphelines} ({etat})"
    if not sqlite:
        assert etat.get("ecrit") is True, etat      # PostgreSQL : l'application continue d'écrire pendant la sauvegarde


# ── 3. (33) Deux inscriptions de la même adresse au même instant ──────────────────────────────────────────────────

def test_d3_deux_inscriptions_simultanees_un_compte_et_un_refus_lisible(client, monkeypatch):
    """Deux appuis sur Entrée dans le formulaire « Créer le compte » (ou deux onglets) : les deux envois passent la
    vérification du doublon avant que l'un n'enregistre (le calcul du mot de passe laisse le temps ; ici, les deux
    attendent l'un l'autre à ce calcul, pour que le test ne dépende pas de la vitesse de la machine). Avant : 201 et
    500 « Internal Server Error » (contrainte d'unicité de l'adresse), l'écran disait « Erreur serveur » alors que le
    compte venait d'être créé. Attendu : 201 et 400 « Cet email est déjà utilisé », un seul compte."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import User
    from app.routers import auth as auth_mod
    vrai_hash = auth_mod.hash_password
    rendez_vous = threading.Barrier(2, timeout=20)

    def _hash_apres_les_deux_verifications(mdp):
        rendez_vous.wait()
        return vrai_hash(mdp)

    monkeypatch.setattr(auth_mod, "hash_password", _hash_apres_les_deux_verifications)
    brut = TestClient(app, raise_server_exceptions=False)     # la vraie réponse HTTP (500 au lieu d'une exception)
    email = f"double_{uuid.uuid4().hex[:8]}@test.fr"
    depart, reponses = threading.Barrier(2, timeout=20), []

    def _inscrire():
        depart.wait()
        r = brut.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                  "full_name": "Double Envoi", "company_name": "Double SARL"})
        try:
            detail = r.json().get("detail", "")
        except ValueError:
            detail = r.text[:80]
        reponses.append((r.status_code, detail))

    fils = [threading.Thread(target=_inscrire) for _ in range(2)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(60)
    assert sorted(c for c, _ in reponses) == [201, 400], reponses
    assert [d for c, d in reponses if c == 400] == ["Cet email est déjà utilisé"], reponses
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == email).count() == 1
    finally:
        db.close()


def test_d3_bis_deux_appuis_sur_entree_une_seule_inscription_envoyee():
    """L'écran « Créer le compte » : le bouton est désactivé pendant l'envoi (:disabled="busy"), mais Entrée dans les
    champs Email et Mot de passe appelle submitAuth directement (@keyup.enter). Avant : deux appuis rapides envoyaient
    deux inscriptions (la seconde finissait en « Erreur serveur », puis, serveur corrigé, en « Cet email est déjà
    utilisé » sous un compte créé). Attendu : un seul envoi tant que le premier n'a pas répondu, comme le bouton."""
    import shutil
    from tests.test_reorganisation_v2b_espace_partenaire import _methode
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    html = open("app/static/app.html", encoding="utf-8").read()
    assert html.count('@keyup.enter="submitAuth"') >= 2          # le chemin par Entrée existe toujours
    script = (
        "globalThis.localStorage = { setItem() {} };\n"
        "const app = ({\n" + _methode("submitAuth") + "\n});\n"
        "let envois = 0;\n"
        "Object.assign(app, { busy: false, token: '',\n"
        "  auth: { mode: 'register', email: 'a@b.fr', password: 'motdepasse123', full_name: 'A', company_name: 'B' },\n"
        "  async api(m, p, b) { envois += 1; await new Promise(r => setTimeout(r, 20)); return { access_token: 't' }; },\n"
        "  notify() {}, async boot() {}, _rnSuggest() {} });\n"
        "(async () => { const a = app.submitAuth(); const b = app.submitAuth(); await Promise.all([a, b]);\n"
        "  const apres = envois; await app.submitAuth();\n"
        "  console.log(JSON.stringify({ deux_appuis: apres, puis: envois, busy: app.busy })); })();\n")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    vu = json.loads(r.stdout.strip().splitlines()[-1])
    assert vu == {"deux_appuis": 1, "puis": 2, "busy": False}, vu   # un envoi, puis un nouvel essai possible


# ── 4. (35) Alerte d'attestations : notée seulement une fois partie ──────────────────────────────────────────────

def _alertes_notees(pid):
    from app.models import AuditLog
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.project_id == pid, AuditLog.action == "piece.expiring").count()
    finally:
        db.close()


def test_d4_alerte_d_attestations_non_partie_pas_notee_et_renvoyee(client, auth, monkeypatch):
    """Marché à J-3 (dernier palier), un partenaire invité avec une adresse, sa part envoyée (pas de rappel de part :
    l'alerte d'attestations part seule), aucune attestation. Le fournisseur d'email est en panne (send_email rend
    faux). Avant : l'alerte était notée (« piece.expiring », qui vaut « déjà alerté pour tout le palier »), le journal
    du partenaire disait « Adjugo vous a alerté », et le passage suivant, fournisseur revenu, n'envoyait plus rien, ni
    au partenaire ni au chef de file. Attendu : rien de noté, puis l'alerte part au passage suivant et n'est notée
    qu'une fois (docs/COTRAITANCE_V2_VAGUE4_API.md, section 6 ; même règle que les pièces à renouveler)."""
    from tests.test_convention_groupement import _invite, _project, _put, _submit
    import app.services.alerts as al
    h = auth["headers"]
    nom = f"Marché attestations {uuid.uuid4().hex[:6]}"
    pid = _project(client, h, name=nom, deadline_days=3)
    adresse = f"p_{uuid.uuid4().hex[:6]}@partenaire.fr"
    inv = _invite(client, h, pid, "Partenaire Attestations SARL", recipient=adresse)
    assert _put(client, inv["token"], lot="Lot 1", prix_lot_ht=1000).status_code == 200
    _submit(client, inv["token"])
    envois, fournisseur = [], {"ok": False}

    def _envoi(to, sujet, texte, *a, **k):
        envois.append((to, sujet, fournisseur["ok"]))
        return fournisseur["ok"]

    monkeypatch.setattr(al, "send_email", _envoi)

    def _journal():
        r = client.get(f"/api/invite/{inv['token']}/journal")
        assert r.status_code == 200, r.text
        return [e.get("label", "") for e in r.json()["entries"]]

    db = SessionLocal()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert any(to == adresse for to, _, _ in envois), "l'alerte au partenaire n'a pas été tentée"
    assert _alertes_notees(pid) == 0, "le courriel n'est pas parti : l'alerte ne doit pas être notée"
    assert not any("vous a alerté" in lab for lab in _journal())
    assert not any(nom[:50] in s and "à surveiller" in s for _, s, _ in envois), \
        "le récapitulatif ne dit pas « prévenus » des partenaires qui n'ont rien reçu"

    fournisseur["ok"] = True                          # même jour, fournisseur revenu
    envois.clear()
    db = SessionLocal()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert [s for to, s, _ in envois if to == adresse], "le partenaire n'est jamais prévenu pour ce palier"
    assert [s for to, s, _ in envois if to == auth["email"] and "à surveiller" in s and nom[:50] in s], \
        "le chef de file ne reçoit jamais son récapitulatif"
    assert _alertes_notees(pid) == 1
    assert any("vous a alerté" in lab for lab in _journal())

    envois.clear()                                    # une seule alerte par palier
    db = SessionLocal()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert not [s for to, s, _ in envois if to == adresse]
    assert _alertes_notees(pid) == 1


# ── 5. (37) Une pièce expirée l'est au jour de Paris, sur tous les écrans ─────────────────────────────────────────

def _figer_l_horloge(monkeypatch, instant_utc):
    """Une seule horloge pour tous les modules : le jour de Paris par la vraie fonction (zoneinfo), et le jour du
    serveur (date.today(), en UTC comme la production) de ce même instant."""
    from app.routers import checklist, invites
    from app.services import pieces_fin

    class _Instant(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant_utc.astimezone(tz) if tz is not None else instant_utc.replace(tzinfo=None)

    class _JourServeur(date):
        @classmethod
        def today(cls):
            return instant_utc.date()

    monkeypatch.setattr(pieces_fin, "datetime", _Instant)
    # Le jour du serveur de ces deux modules (avant la correction, leur « aujourd'hui ») ; raising=False : la
    # correction retire `date` de checklist, qui n'en a plus besoin.
    monkeypatch.setattr(checklist, "date", _JourServeur, raising=False)
    monkeypatch.setattr(invites, "date", _JourServeur, raising=False)


@pytest.mark.parametrize("heure_utc", [12, 23])
def test_d5_piece_expiree_au_jour_de_paris_sur_tous_les_ecrans(client, auth, monkeypatch, heure_utc):
    """Une attestation URSSAF dont la date de fin est le 22/10/2026. À 23 h UTC le 22/10, il est 1 h du matin le 23/10
    à Paris : Mes documents dit « Expirée le 22/10/2026 ». Avant : « Pièces à fournir » la comptait valable (status
    ok, expired faux) et « Prêt à déposer » ne la rangeait pas dans les manques (jour du serveur, UTC). Attendu : la
    même réponse partout (docs/REORGANISATION_V2A.md A3.3, « Un seul calcul de la fin », « Jour de Paris partout »).
    À midi UTC, les écrans s'accordent déjà : elle expire aujourd'hui, valable partout."""
    from app.models import DocCategory, Document, User
    _figer_l_horloge(monkeypatch, datetime(2026, 10, 22, heure_utc, 0, tzinfo=timezone.utc))
    db = SessionLocal()
    try:
        uid = db.query(User.id).filter(User.email == auth["email"]).scalar()
        db.add(Document(user_id=uid, name="Attestation URSSAF vigilance", category=DocCategory.fiscal,
                        file_key=f"{uid}/urssaf_paris.pdf", file_size=1, mime_type="application/pdf",
                        expiration_date=date(2026, 10, 22)))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/projects/", json={"name": "Marché jour de Paris", "client": "Mairie"},
                    headers=auth["headers"])
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.get("/api/documents/", headers=auth["headers"])
    assert r.status_code == 200, r.text
    fin = next(d for d in r.json() if d["name"].startswith("Attestation URSSAF vigilance"))["fin"]
    expiree = heure_utc == 23
    assert fin["code"] == ("expiree" if expiree else "bientot"), fin

    # « Pièces à fournir »
    r = client.get(f"/api/checklist/{pid}", headers=auth["headers"])
    assert r.status_code == 200, r.text
    ligne = next(i for i in r.json()["checklist"] if i["id"] == "attestation_sociale")
    assert ligne["expired"] is expiree, ligne
    assert (ligne["status"] == "ok") is (not expiree), ligne

    # « Prêt à déposer » : la même pièce, dans « Pièces » (liste des pièces) et dans « Vos attestations »
    # (attestations du chef de file, même calcul que le coffre-fort croisé des partenaires).
    r = client.get(f"/api/projects/{pid}/groupement/depot", headers=auth["headers"])
    assert r.status_code == 200, r.text
    manques = (r.json().get("pret") or {}).get("manques_par_controle") or {}
    texte_pieces = " ".join(manques.get("pieces") or [])
    texte_attestations = " ".join(manques.get("attestations") or [])
    assert ("expirée" in texte_pieces) is expiree, manques
    assert ("a expiré" in texte_attestations) is expiree, manques


def test_d5_bis_statut_d_une_piece_de_partenaire_au_jour_de_paris(monkeypatch):
    """Le statut d'une attestation du coffre-fort croisé (pièces des partenaires et du chef de file : invites.
    _piece_status) suit le même jour de Paris : à 23 h UTC le 22/10, une pièce finissant le 22/10 « a expiré »."""
    from types import SimpleNamespace
    from app.routers.invites import _piece_status
    _figer_l_horloge(monkeypatch, datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc))
    assert _piece_status(SimpleNamespace(expiration_date=date(2026, 10, 22)), None) == "expire"
    assert _piece_status(SimpleNamespace(expiration_date=date(2026, 10, 23)), None) == "valide_jusquau"
    _figer_l_horloge(monkeypatch, datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc))
    assert _piece_status(SimpleNamespace(expiration_date=date(2026, 10, 22)), None) == "valide_jusquau"
