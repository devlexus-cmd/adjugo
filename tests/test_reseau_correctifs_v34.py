"""
Réseau de partenaires (vague 3) — correctifs de la revue v34 (domaine A). Chaque test ÉCHOUE
sans la correction correspondante.

- identité : la publication passe par une VALIDATION Adjugo (usurpation d'une entreprise
  réelle, masquage contourné par un changement de SIRET, oracle « un seul profil par SIREN ») ;
- comptes non publiés : aucun compteur filtré, aucun repli SIRENE amputé des membres ;
- PUT /profil : listes bornées (dédoublonnage quadratique), année 1e400 → 422 ;
- RGPD : transfert de propriété puis effacement de l'ex-propriétaire ;
- repli SIRENE en parallèle avec budget global, recherche en erreur jamais mise en cache ;
- invitations simultanées, cron sans famine, index unique, borne de lecture signalée ;
- badge « marqué déposé » déclaratif et non fabricable seul ; critère zone sourcé ; département
  supposé signalé ; libellés honnêtes ; invitations reçues « qui peut accepter ».
Aucun appel réseau réel (registres simulés par la fixture `reg` du module des tests réseau).
"""
import json
import threading
import time
import uuid
from datetime import date, datetime, timedelta

import pytest

from tests.test_reseau_partenaires import (_admin_headers, _db, _org, _profile_row, _project, _publish,  # noqa: F401
                                           _siren, _validate, mails, reg)

# Le vrai repli SIRENE de « Qui me complète ? », capturé à l'import du module (avant que la
# fixture `reg` ne le remplace par un faux) : le test du délai par appel l'exerce directement.
from app.routers.reseau import _sirene_fallback as _VRAI_REPLI_SIRENE


@pytest.fixture(autouse=True)
def _retire_les_profils_publies():
    """La base de test est partagée : les profils publiés ici (nombreux, en électricité dans le
    29) ne doivent pas évincer ceux des autres modules (classements bornés, lot du cron)."""
    yield
    from app.models import PartnerProfile
    db = _db()
    try:
        db.query(PartnerProfile).filter(PartnerProfile.visible.is_(True)).update(
            {PartnerProfile.visible: False}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _demande(client, reg, org, metiers=("electricite",), deps=("29",)):
    """PUT + vérifier + demande de publication (sans validation Adjugo)."""
    reg.sirene.setdefault(org["siren"], {"nom": org["name"].upper(), "etat": "A"})
    assert client.put("/api/reseau/profil", headers=org["headers"],
                      json={"metiers": list(metiers), "departements": list(deps)}).status_code == 200
    assert client.post("/api/reseau/profil/verifier", headers=org["headers"]).status_code == 200
    r = client.post("/api/reseau/profil/publier", headers=org["headers"], json={"accepte": True})
    assert r.status_code == 200, r.text
    return r.json()


def _ids(client, org, metier="electricite"):
    v = client.get(f"/api/reseau/annuaire?metier={metier}&par_page=50", headers=org["headers"]).json()
    return {p["profile_id"] for p in v["profils"]}


# ── 1. Identité : validation Adjugo avant toute visibilité ───────────────────────────
def test_usurpation_publication_en_attente_puis_refus_avec_motif(client, reg):
    vraie = _siren()
    reg.sirene[vraie] = {"nom": "LE GALL ELECTRICITE", "etat": "A"}
    squat = _org(client, "Squatteur", siren=vraie)          # SIRET d'une AUTRE entreprise réelle
    v = _demande(client, reg, squat)
    assert v["visible"] is False and v["statut"] == "en_attente"
    assert v["statut_label"] == "En attente de validation par Adjugo"
    assert "pas que votre compte la représente" in v["validation"]["explication"]
    assert v["publication"]["peut_publier"] is False
    chef = _org(client, "Chef Honnête")
    _publish(client, reg, chef, metiers=("couverture",))
    assert v["profile_id"] not in _ids(client, chef)             # invisible tant que non validé
    assert client.get(f"/api/reseau/annuaire/{v['profile_id']}", headers=chef["headers"]).status_code == 404
    # L'administrateur Adjugo voit l'identité SIRENE, le nom et l'email du compte.
    q = client.get("/api/admin/reseau/validations", headers=_admin_headers(client))
    assert q.status_code == 200, q.text
    item = next(i for i in q.json()["en_attente"] if i["profile_id"] == v["profile_id"])
    assert item["siren"] == vraie and item["sirene"]["nom"] == "LE GALL ELECTRICITE"
    assert item["compte"]["email"] == squat["email"] and item["compte"]["nom"] == "Dirigeant"
    # Réservé à l'administrateur Adjugo (pas à l'administrateur d'une organisation).
    assert client.get("/api/admin/reseau/validations", headers=chef["headers"]).status_code == 403
    assert client.post(f"/api/admin/reseau/validations/{v['profile_id']}/valider",
                       headers=chef["headers"], json={}).status_code == 403
    r = client.post(f"/api/admin/reseau/validations/{v['profile_id']}/refuser", headers=_admin_headers(client),
                    json={"motif": "Le compte ne correspond pas à cette entreprise."})
    assert r.status_code == 200, r.text
    me = client.get("/api/reseau/profil", headers=squat["headers"]).json()
    assert me["statut"] == "refuse" and me["visible"] is False
    assert me["validation"]["motif"] == "Le compte ne correspond pas à cette entreprise."
    assert v["profile_id"] not in _ids(client, chef)


def test_admin_notifie_avec_plafond(client, reg, monkeypatch):
    import app.services.partner_network as pn
    monkeypatch.setattr(pn, "ADMIN_NOTIFY_DAY_CAP", 2)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "ADMIN_EMAILS", "equipe@adjugo-test.fr, autre@adjugo-test.fr")
    for i in range(3):
        _demande(client, reg, _org(client, f"Demandeur {i}"))
    assert len(reg.admin_mails) == 4                      # 2 demandes × 2 destinataires, puis plafond
    assert {m[0] for m in reg.admin_mails} == {"equipe@adjugo-test.fr", "autre@adjugo-test.fr"}
    assert all("Administration" in m[2] and "@" not in m[2] for m in reg.admin_mails)
    monkeypatch.setattr(get_settings(), "ADMIN_EMAILS", "")
    pn._ADMIN_NOTIFY.update({"day": "", "n": 0, "last": {}})
    reg.admin_mails.clear()
    _demande(client, reg, _org(client, "Demandeur repli"))
    assert [m[0] for m in reg.admin_mails] == ["contact@adjugo.pro"]


def test_changement_de_siret_depublie_et_exige_une_nouvelle_validation(client, reg):
    a = _org(client, "Discrète A")
    c = _org(client, "Concurrent C")
    a_pid = _publish(client, reg, a, hidden_from_sirens=[c["siren"]])
    c_pid = _publish(client, reg, c)
    assert a_pid not in _ids(client, c)
    autre = _siren()
    reg.sirene[autre] = {"nom": "AUTRE ENTREPRISE REELLE", "etat": "A"}
    r = client.put("/api/company/", headers=c["headers"], json={"name": "Concurrent C", "siret": autre + "00012"})
    assert r.status_code == 200, r.text
    row = _profile_row(c["id"])
    assert row.visible is False and row.validation_status == "" and row.siren == autre   # dépublié AU PUT
    obs = _org(client, "Observateur")
    _publish(client, reg, obs, metiers=("couverture",))
    assert c_pid not in _ids(client, obs)
    import app.routers.reseau as R
    R._VERIFY_LAST.clear()                   # délai entre deux vérifications (hors sujet ici)
    v = _demande(client, reg, c)
    assert v["statut"] == "en_attente" and v["visible"] is False      # plus de publication directe
    assert a_pid not in _ids(client, c)                               # masquage NON contourné


def test_plus_d_oracle_un_seul_profil_par_siren(client, reg):
    cible = _org(client, "Cible Publiée")
    _publish(client, reg, cible)
    curieux = _org(client, "Curieux", siren=cible["siren"])
    reg.sirene[cible["siren"]] = {"nom": "CIBLE PUBLIEE", "etat": "A"}
    client.put("/api/reseau/profil", headers=curieux["headers"], json={"metiers": ["peinture"], "departements": ["29"]})
    client.post("/api/reseau/profil/verifier", headers=curieux["headers"])
    v = client.get("/api/reseau/profil", headers=curieux["headers"]).json()
    assert "unique" not in {c["key"] for c in v["publication"]["conditions"]}
    r = client.post("/api/reseau/profil/publier", headers=curieux["headers"], json={"accepte": True})
    assert r.status_code == 200 and r.json()["statut"] == "en_attente"
    assert "siren_deja_publie" not in r.text and "déjà publié" not in r.text
    # L'administrateur voit le conflit et peut remplacer l'ancien profil.
    item = next(i for i in client.get("/api/admin/reseau/validations", headers=_admin_headers(client)).json()["en_attente"]
                if i["profile_id"] == r.json()["profile_id"])
    assert item["conflits"] and item["conflits"][0]["statut"] == "publie"
    assert item["conflits"][0]["compte_email"] == cible["email"]
    _validate(client, r.json()["profile_id"], remplacer=True)
    old = client.get("/api/reseau/profil", headers=cible["headers"]).json()
    assert old["visible"] is False and old["statut"] == "refuse" and "autre compte" in old["validation"]["motif"]


def test_publication_exige_une_adresse_confirmee(client, reg):
    o = _org(client, "Adresse Non Confirmée", verified=False)
    reg.sirene[o["siren"]] = {"nom": "ADRESSE NON CONFIRMEE", "etat": "A"}
    client.put("/api/reseau/profil", headers=o["headers"], json={"metiers": ["peinture"], "departements": ["29"]})
    client.post("/api/reseau/profil/verifier", headers=o["headers"])
    r = client.post("/api/reseau/profil/publier", headers=o["headers"], json={"accepte": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_non_verifie"
    conds = {c["key"]: c["ok"] for c in client.get("/api/reseau/profil", headers=o["headers"]).json()["publication"]["conditions"]}
    assert conds["email"] is False


def test_index_unique_un_seul_profil_publie_par_siren(client, reg):
    from sqlalchemy.exc import IntegrityError
    from app.models import PartnerProfile
    a = _org(client, "Index A")
    _publish(client, reg, a)
    b = _org(client, "Index B", siren=a["siren"])
    client.put("/api/reseau/profil", headers=b["headers"], json={"metiers": ["peinture"], "departements": ["29"]})
    db = _db()
    try:
        p = db.query(PartnerProfile).filter(PartnerProfile.user_id == b["id"]).first()
        p.visible = True
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


# ── 2. Comptes non publiés : aucun oracle ────────────────────────────────────────────
def test_annuaire_non_publie_ne_depend_d_aucun_filtre(client, reg):
    cible = _org(client, "Kerbrat Menuiserie Oracle")
    _publish(client, reg, cible, metiers=("menuiserie",), deps=("56",))
    espion = _org(client, "Espion")
    demo = client.post("/api/auth/demo").json()["access_token"]
    for h in (espion["headers"], {"Authorization": f"Bearer {demo}"}):
        rs = [client.get(f"/api/reseau/annuaire?{qs}", headers=h).json() for qs in (
            "q=Kerbrat", "q=Inexistant", "q=Kerbrat&departement=56", "q=Kerbrat&departement=35",
            "metier=menuiserie", "metier=plomberie", "role=cotraitant", "cpv=45421000")]
        assert all(r["visible"] is False and r["total"] is None and r["profils"] == [] for r in rs)
        assert len({r["message"] for r in rs}) == 1          # même réponse quels que soient les filtres


def test_qui_me_complete_non_publie_repli_sirene_non_ampute(client, reg):
    membre = _org(client, "Elec Reseau Discret")
    _publish(client, reg, membre)
    curieux = _org(client, "Curieux Non Publié")
    pid = _project(client, curieux, allotissement="Lot 1 : Couverture ; Lot 2 : Électricité")
    reg.sirene_pool["electricite"] = [
        {"name": "ELEC RESEAU DISCRET", "siret": membre["siren"] + "00012", "city": "QUIMPER", "departement": "29",
         "as_of": date.today().isoformat()},
        {"name": "ELEC HORS RESEAU", "siret": "22222222200012", "city": "BREST", "departement": "29",
         "as_of": date.today().isoformat()}]
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=curieux["headers"]).json()
    lot = next(l for l in v["lots"] if l["metier"] == "electricite")
    assert {s["name"] for s in lot["sirene"]} == {"ELEC RESEAU DISCRET", "ELEC HORS RESEAU"}
    assert lot["n_correspondants"] is None and v["n_correspondants"] is None
    assert all(s["statut_reseau"] == "Trouvée dans le registre SIRENE — à inviter par lien" for s in lot["sirene"])
    assert "Hors réseau" not in json.dumps(v, ensure_ascii=False)


def test_publie_profil_qui_me_masque_jamais_dit_hors_reseau(client, reg):
    chef = _org(client, "Chef Masqué")
    _publish(client, reg, chef, metiers=("couverture",))
    masque = _org(client, "Masque Plomberie")
    _publish(client, reg, masque, metiers=("plomberie",), hidden_from_sirens=[chef["siren"]])
    pid = _project(client, chef, allotissement="Lot 1 : Couverture ; Lot 2 : Plomberie")
    reg.sirene_pool["plomberie"] = [{"name": "MASQUE PLOMBERIE", "siret": masque["siren"] + "00012", "city": "QUIMPER",
                                     "departement": "29", "as_of": date.today().isoformat()}]
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=chef["headers"]).json()
    lot = next(l for l in v["lots"] if l["metier"] == "plomberie")
    assert [s["statut_reseau"] for s in lot["sirene"]] == ["Trouvée dans le registre SIRENE — à inviter par lien"]


# ── 3. PUT /profil : bornes et année ─────────────────────────────────────────────────
def test_put_profil_listes_bornees_avant_traitement(client, reg):
    o = _org(client, "Bornes")
    h = o["headers"]
    assert client.put("/api/reseau/profil", headers=h, json={"metiers": ["peinture"]}).status_code == 200
    t0 = time.monotonic()
    r = client.put("/api/reseau/profil", headers=h, json={"hidden_from_sirens": ["123456789"] * 50_000})
    assert r.status_code == 422 and "300 éléments au plus" in r.json()["detail"]
    assert time.monotonic() - t0 < 5
    many = [str(100_000_000 + i) for i in range(150)]
    r = client.put("/api/reseau/profil", headers=h, json={"hidden_from_sirens": many})
    assert r.status_code == 422 and "Au plus 100" in r.json()["detail"]
    r = client.put("/api/reseau/profil", headers=h, json={"hidden_from_sirens": ["123456789"] * 200})
    assert r.status_code == 200 and r.json()["hidden_from_sirens"] == ["123456789"]
    r = client.put("/api/reseau/profil", headers=h, json={"departements": ["29"] * 121})
    assert r.status_code == 422


def test_annee_de_reference_hors_limites_422(client, reg):
    o = _org(client, "Année Infinie")
    h = {**o["headers"], "Content-Type": "application/json"}
    for raw in ('{"references_publiques": [{"intitule": "École", "annee": 1e400}]}',
                '{"references_publiques": [{"intitule": "École", "annee": Infinity}]}'):
        r = client.put("/api/reseau/profil", headers=h, content=raw)
        assert r.status_code == 422, (raw, r.status_code, r.text)


# ── 4. RGPD : transfert de propriété puis effacement de l'ex-propriétaire ────────────
def test_transfert_readresse_les_invitations_et_effacement_les_nettoie(client, reg, mails):
    from app.core.security import create_access_token
    from app.models import ProjectInvite, User
    b = _org(client, "Partenaire Repris")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef Transfert")
    _publish(client, reg, a, metiers=("couverture",))
    pid1, pid2 = _project(client, a), _project(client, a)
    inv1 = client.post(f"/api/projects/{pid1}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid}).json()
    inv2 = client.post(f"/api/projects/{pid2}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid}).json()
    tok1 = next(i["token"] for i in client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"]
                if i["project"] and i["token"])
    # L'ancien propriétaire accepte une des deux invitations AVANT le transfert.
    db = _db()
    try:
        tokens = {db.get(ProjectInvite, inv1["invitation"]["id"]).token: inv1["invitation"]["id"],
                  db.get(ProjectInvite, inv2["invitation"]["id"]).token: inv2["invitation"]["id"]}
    finally:
        db.close()
    first_tok = next(iter(tokens))
    assert client.post(f"/api/invite/{first_tok}/claim", headers=b["headers"]).status_code == 200
    other_id = [i for t, i in tokens.items() if t != first_tok][0]
    other_tok = [t for t in tokens if t != first_tok][0]
    em = f"rep_{uuid.uuid4().hex[:8]}@test.fr"
    assert client.post("/api/org/invite", headers=b["headers"], json={"email": em, "full_name": "Repreneuse"}).status_code == 201
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        m.email_verified = True
        db.commit()
        mid = m.id
        mh = {"Authorization": "Bearer " + create_access_token(data={"sub": str(m.id), "tv": int(m.token_version or 0)})}
    finally:
        db.close()
    assert client.post("/api/org/transfer-ownership", headers=b["headers"], json={"new_owner_id": mid}).status_code == 200
    db = _db()
    try:
        assert db.get(ProjectInvite, other_id).recipient == em          # réadressée au nouveau propriétaire
        b_tv = int(db.get(User, b["id"]).token_version or 0)
    finally:
        db.close()
    assert client.post(f"/api/invite/{other_tok}/claim", headers=mh).status_code == 200
    bh = {"Authorization": "Bearer " + create_access_token(data={"sub": str(b["id"]), "tv": b_tv})}
    r = client.post("/api/rgpd/delete-account", headers=bh, json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        left = db.query(ProjectInvite).filter(ProjectInvite.recipient == b["email"]).count()
        left += db.query(ProjectInvite).filter(ProjectInvite.verified_email == b["email"]).count()
        assert left == 0
    finally:
        db.close()
    assert tok1


# ── 5. Repli SIRENE borné ────────────────────────────────────────────────────────────
def test_repli_sirene_lots_en_parallele_et_budget_global(client, reg, monkeypatch):
    import app.routers.reseau as R
    calls = []

    def slow(trade, dept, warnings):
        calls.append(time.monotonic())
        time.sleep(0.4)
        return []
    monkeypatch.setattr(R, "_sirene_fallback", slow)
    a = _org(client, "Chef Pressé")
    pid = _project(client, a)
    t0 = time.monotonic()
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).json()
    assert len(calls) == 3 and time.monotonic() - t0 < 1.0          # en série : 1,2 s
    assert max(calls) - min(calls) < 0.3
    monkeypatch.setattr(R, "SIRENE_BUDGET_S", 0.2)

    def stuck(trade, dept, warnings):
        time.sleep(1.5)
        return []
    monkeypatch.setattr(R, "_sirene_fallback", stuck)
    t0 = time.monotonic()
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).json()
    assert time.monotonic() - t0 < 1.0
    slow_lots = [l for l in v["lots"] if (l.get("sirene_message") or "").startswith("Le registre SIRENE est lent")]
    assert len(slow_lots) == 3


def test_repli_sirene_delai_court_par_appel(monkeypatch):
    """Revue v34 (A26) : sur « Qui me complète ? », chaque appel HTTP du repli (SIRENE, puis
    BODACC qui écarte les procédures collectives) a un délai de 5 s au plus. Avant : 12 s et
    8 s, et un fil détaché après le budget global restait occupé jusqu'à 20 s par lot."""
    import httpx
    from app.services import groupement_verdict as gv
    delais = []

    class _Rep:
        status_code = 200

        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._d

    class _Client:
        def __init__(self, *a, timeout=None, **kw):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, **kw):
            kind = "bodacc" if "bodacc" in url else "sirene"
            delais.append((kind, self.timeout))
            if kind == "bodacc":
                return _Rep({"results": []})
            return _Rep({"results": [{"siren": "123456782", "nom_complet": "ETANCHEITE DE MAYOTTE",
                                      "nature_juridique": "5710", "activite_principale": "43.99A",
                                      "siege": {"siret": "12345678200011", "code_postal": "97600",
                                                "libelle_commune": "MAMOUDZOU", "etat_administratif": "A"}}]})
    monkeypatch.setattr(httpx, "Client", _Client)
    gv._SIRENE_CACHE.pop(("etancheite", "976"), None)
    try:
        found = _VRAI_REPLI_SIRENE("etancheite", "976", [])
    finally:
        gv._SIRENE_CACHE.pop(("etancheite", "976"), None)
    assert [m["name"] for m in found] == ["ETANCHEITE DE MAYOTTE"]
    assert {k for k, _t in delais} == {"sirene", "bodacc"}, delais
    assert all(t is not None and float(t) <= 5 for _k, t in delais), delais


def test_recherche_sirene_en_erreur_jamais_mise_en_cache(monkeypatch):
    from app.services import groupement_verdict as gv
    import app.routers.sourcing as S
    n = {"calls": 0}

    class _Err:
        message = "SIRENE indisponible"

    class _Svc:
        def discover(self, **kw):
            n["calls"] += 1
            return {"companies": [], "errors": [_Err()]}
    monkeypatch.setattr(S, "_company_service", lambda: _Svc())
    gv._SIRENE_CACHE.pop(("etancheite", "98"), None)
    w1, w2 = [], []
    gv._discover_sirene("etancheite", "98", w1)
    gv._discover_sirene("etancheite", "98", w2)
    assert n["calls"] == 2 and w1 and w2


# ── 6. Concurrence, cron, borne de lecture ───────────────────────────────────────────
def test_deux_invitations_simultanees_une_seule_creee(client, reg, mails, monkeypatch):
    import app.services.partner_network as pn
    from app.models import ProjectInvite
    real = pn.network_recipient

    def slow_recipient(db, p):
        time.sleep(0.3)        # élargit la fenêtre entre « déjà invité ? » et la création
        return real(db, p)
    monkeypatch.setattr(pn, "network_recipient", slow_recipient)
    chef = _org(client, "Chef Double Clic")
    _publish(client, reg, chef, metiers=("couverture",))
    part = _org(client, "Partenaire Double Clic")
    prof = _publish(client, reg, part)
    pid = _project(client, chef)
    bar, codes = threading.Barrier(2), []

    def click():
        bar.wait()
        codes.append(client.post(f"/api/projects/{pid}/reseau/invitations", headers=chef["headers"],
                                 json={"profile_id": prof}).status_code)
    ts = [threading.Thread(target=click) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    db = _db()
    try:
        n = db.query(ProjectInvite).filter(ProjectInvite.project_id == pid, ProjectInvite.revoked.is_(False)).count()
    finally:
        db.close()
    assert sorted(codes) == [200, 409] and n == 1


def test_cron_tourne_sur_la_derniere_tentative(client, reg, monkeypatch):
    import app.services.partner_network as pn
    from app.models import PartnerProfile
    monkeypatch.setattr(pn, "CRON_BATCH", 2)
    orgs = [_org(client, f"Cron {i}") for i in range(3)]
    for o in orgs:
        _publish(client, reg, o)
    ids = [_profile_row(o["id"]).id for o in orgs]
    db = _db()
    try:
        for p in db.query(PartnerProfile).filter(PartnerProfile.visible.is_(True), ~PartnerProfile.id.in_(ids)).all():
            p.last_check_at = datetime.utcnow() + timedelta(days=1)       # hors du lot de ce test
        db.commit()
    finally:
        db.close()
    reg.fail.add("sirene")                                     # SIRENE ne répond jamais « ok »
    seen = []
    real = pn.run_checks

    def spy(siren, now=None):
        seen.append(siren)
        return real(siren, now)
    monkeypatch.setattr(pn, "run_checks", spy)
    db = _db()
    try:
        pn.run_partner_network(db, limit=2)
        pn.run_partner_network(db, limit=2)
    finally:
        db.close()
    assert {o["siren"] for o in orgs} <= set(seen)             # le 3e profil a eu son tour
    assert all(_profile_row(o["id"]).last_check_at for o in orgs)


def test_borne_de_lecture_signalee(client, reg, monkeypatch):
    import app.services.partner_network as pn
    monkeypatch.setattr(pn, "MAX_VISIBLE_SCAN", 1)
    me = _org(client, "Chercheur Borne")
    _publish(client, reg, me, metiers=("couverture",))
    for i in range(2):
        _publish(client, reg, _org(client, f"Borne {i}"), metiers=("etancheite",))
    v = client.get("/api/reseau/annuaire?metier=etancheite", headers=me["headers"]).json()
    assert v.get("avertissement") == pn.TRONQUE_MSG


def test_annuaire_filtre_departement_en_base_avant_la_borne(client, reg, monkeypatch):
    """Revue v34 (A13) : le filtre département s'applique en base AVANT la borne de lecture,
    comme le métier. Sinon, au-delà de la borne, un profil récent du département cherché
    disparaissait de l'annuaire (les plus anciens remplissaient la lecture)."""
    import app.services.partner_network as pn
    me = _org(client, "Chercheur Département")
    _publish(client, reg, me, metiers=("couverture",))
    for i in range(2):
        _publish(client, reg, _org(client, f"Étanchéité Ancienne {i}"), metiers=("etancheite",), deps=("56",))
    cible = _publish(client, reg, _org(client, "Mayotte Étanchéité", cp="97600", city="Mamoudzou"),
                     metiers=("etancheite",), deps=("976",))
    monkeypatch.setattr(pn, "MAX_VISIBLE_SCAN", 2)
    v = client.get("/api/reseau/annuaire?departement=976&par_page=50", headers=me["headers"]).json()
    assert [p["profile_id"] for p in v["profils"]] == [cible], v
    assert v["total"] == 1 and "avertissement" not in v
    v = client.get("/api/reseau/annuaire?metier=etancheite&departement=976", headers=me["headers"]).json()
    assert [p["profile_id"] for p in v["profils"]] == [cible], v
    # Le siège compte aussi (même règle que le filtre exact de l'annuaire) : zones 29, siège à 976.
    siege = _publish(client, reg, _org(client, "Siège Mayotte", cp="97600", city="Mamoudzou"),
                     metiers=("etancheite",), deps=("29",))
    v = client.get("/api/reseau/annuaire?departement=976&par_page=50", headers=me["headers"]).json()
    assert {p["profile_id"] for p in v["profils"]} == {cible, siege}, v


# ── 7. Badge déclaratif, critères sourcés, département supposé ────────────────────────
def test_groupement_avec_soi_meme_non_compte(client, reg, mails):
    """Revue v34 (contre/c4) : une entreprise s'invite par lien, remplit la part elle-même et
    marque le marché déposé ; ce « groupement » avec soi-même ne fabrique plus le badge."""
    from tests.test_convention_groupement import _put, _submit
    import app.services.partner_network as pn
    a = _org(client, "Auto Groupement")
    _publish(client, reg, a)
    for i in range(2):
        pid = _project(client, a)
        inv = client.post(f"/api/projects/{pid}/invites", headers=a["headers"],
                          json={"company_name": "Société imaginaire"}).json()
        assert _put(client, inv["token"], company_name="Société imaginaire", lot="Lot 2",
                    prix_lot_ht=1).status_code == 200
        _submit(client, inv["token"])
        r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=a["headers"], json={"confirmer": True})
        assert r.status_code == 200, r.text
    h = client.get("/api/reseau/historique", headers=a["headers"]).json()      # recalcule le compteur
    assert h["groupements_deposes"] == 0, h
    db = _db()
    try:
        n, _d = pn.count_groupements(db, pn.org_member_ids(db, a["id"]), _profile_row(a["id"]).id, a["siren"])
    finally:
        db.close()
    assert n == 0
    # Un vrai partenaire (autre organisation, lien réclamé) compte, lui.
    b = _org(client, "Vrai Partenaire")
    pid = _project(client, a)
    inv = client.post(f"/api/projects/{pid}/invites", headers=a["headers"],
                      json={"company_name": "Vrai Partenaire", "recipient": b["email"]}).json()
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=b["headers"]).status_code == 200
    assert _put(client, inv["token"], b["headers"], company_name="Vrai Partenaire", lot="Lot 3",
                prix_lot_ht=1, siret=b["siren"] + "00012").status_code == 200
    _submit(client, inv["token"])
    assert client.post(f"/api/projects/{pid}/groupement/deposer", headers=a["headers"],
                       json={"confirmer": True}).status_code == 200
    h = client.get("/api/reseau/historique", headers=a["headers"]).json()
    assert h["groupements_deposes"] == 1, h


def test_badge_marque_depose_declaratif_niveau_info_date():
    from app.services import partner_matching as pm
    b = pm.badges({"groupements_deposes": 3, "groupements_checked_at": "2026-10-08T10:00:00"})
    bd = next(x for x in b if x["key"] == "adjugo")
    assert bd["label"] == "3 groupements marqués déposés sur Adjugo (déclaratif) au 08/10"
    assert bd["niveau"] == "info" and bd["date"] == "2026-10-08" and "déclaratif" in bd["source"]


def _prof(**kw):
    d = {"public_id": "a" * 32, "name": "X", "metiers": ["electricite"], "departements": [],
         "roles_acceptes": ["cotraitant"], "declared_at": "2026-10-01T10:00:00", "postal_code": "29000",
         "departement": "29", "verified_sirene": {"etat": "actif", "checked_at": "2026-10-05T09:00:00",
                                                  "code_postal": "75001"}}
    d.update(kw)
    return d


def test_critere_zone_dit_d_ou_vient_la_donnee():
    from app.services import partner_matching as pm
    today = date(2026, 10, 8)
    _t, crits = pm.score_lot({"metier": "electricite", "departement": "29"}, _prof(), today)
    z = next(c for c in crits if c["key"] == "zone")
    assert z["detail"] == "Adresse dans le 29 (code postal déclaré)" and z["source"] == "déclaré par l'entreprise"
    _t, crits = pm.score_lot({"metier": "electricite", "departement": "75"}, _prof(), today)
    z = next(c for c in crits if c["key"] == "zone")
    assert z["detail"] == "Siège dans le 75 (siège SIRENE)" and z["source"].startswith("SIRENE")
    _t, crits = pm.score_lot({"metier": "electricite", "departement": "", "contexte": "annuaire"}, _prof(), today)
    z = next(c for c in crits if c["key"] == "zone")
    assert z["detail"] == "Aucun département choisi dans votre recherche" and z["source"] == "votre recherche"


def test_annuaire_sans_departement_ne_parle_pas_d_un_marche(client, reg):
    me = _org(client, "Chercheur Sans Département")
    _publish(client, reg, me, metiers=("couverture",))
    _publish(client, reg, _org(client, "Électricien Annuaire"), metiers=("electricite",))
    v = client.get("/api/reseau/annuaire?metier=electricite", headers=me["headers"]).json()
    zones = [c for p in v["profils"] for c in p["criteres"] if c["key"] == "zone"]
    assert zones and all("dossier du marché" not in c["detail"] for c in zones)


def test_departement_suppose_signale(client, reg):
    a = _org(client, "Chef Sans Lieu", cp="29000")
    pid = _project(client, a)
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        det = dict(p.ai_analysis["details"])
        det.pop("lieu_execution", None)
        p.ai_analysis = {"details": det}
        db.commit()
    finally:
        db.close()
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).json()
    assert any("département retenu" in w and "29" in w for w in v["warnings"])
    assert all(l["departement_source"] == "suppose" for l in v["lots"])


def test_libelle_apparitions_compte_des_entreprises(client, reg):
    b = _org(client, "Apparue")
    _publish(client, reg, b, metiers=("etancheite",))
    v = client.get("/api/reseau/profil", headers=b["headers"]).json()
    assert v["apparitions_label"].startswith("Votre profil est apparu dans les recherches de 0 entreprise ")


def test_invitations_recues_seul_le_proprietaire_peut_accepter(client, reg, mails):
    from app.core.security import create_access_token
    from app.models import User
    b = _org(client, "Partenaire Équipe")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef Équipe")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    assert client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                       json={"profile_id": b_pid}).status_code == 200
    em = f"adm_{uuid.uuid4().hex[:8]}@test.fr"
    assert client.post("/api/org/invite", headers=b["headers"], json={"email": em, "full_name": "Adjointe"}).status_code == 201
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        mh = {"Authorization": "Bearer " + create_access_token(data={"sub": str(m.id), "tv": int(m.token_version or 0)})}
    finally:
        db.close()
    mine = client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"]
    other = client.get("/api/reseau/invitations", headers=mh).json()["invitations"]
    assert mine and mine[0]["peut_accepter"] is True and mine[0]["aide"] is None
    assert other and other[0]["peut_accepter"] is False and "propriétaire" in other[0]["aide"]
    assert b["email"] not in json.dumps(other)


def test_notification_admin_objet_sur_une_ligne(client, reg):
    """Un saut de ligne dans le nom de l'entreprise ne doit jamais casser l'objet de l'email
    envoyé à l'équipe Adjugo (l'envoi SMTP échouait, la demande restait sans notification)."""
    o = _org(client, "Ligne\r\nCc: x@y.fr")
    _demande(client, reg, o)
    assert reg.admin_mails
    for _to, subj, text in reg.admin_mails:
        assert "\n" not in subj and "\r" not in subj
        assert "ligne cc: x@y.fr" in subj.lower()


def test_badge_identite_validee_par_adjugo_date_et_retire_au_changement_de_siret(client, reg):
    """« Trouvez des partenaires vérifiés » : la fiche dit QUI a vérifié l'identité et QUAND
    (décision de l'administrateur Adjugo), jamais supposé ; un SIRET modifié le retire."""
    me = _org(client, "Lecteur Badge")
    _publish(client, reg, me, metiers=("couverture",))
    b = _org(client, "Badge Identité")
    b_pid = _publish(client, reg, b, metiers=("menuiserie",))
    fiche = client.get(f"/api/reseau/annuaire/{b_pid}", headers=me["headers"]).json()
    iv = next(x for x in fiche["badges"] if x["key"] == "identite")
    assert iv["niveau"] == "ok" and iv["date"] == date.today().isoformat()
    assert iv["label"] == f"Identité de l'entreprise validée par Adjugo le {date.today().strftime('%d/%m/%Y')}"
    assert "Adjugo" in iv["source"]
    # Après un changement de SIRET : validation retirée, plus de badge (aperçu du propriétaire).
    autre = _siren()
    reg.sirene[autre] = {"nom": "AUTRE", "etat": "A"}
    assert client.put("/api/company/", headers=b["headers"],
                      json={"name": "Badge Identité", "siret": autre + "00012"}).status_code == 200
    v = client.get("/api/reseau/profil", headers=b["headers"]).json()
    assert v["validation"]["identite_validee"] is False
    assert all(x["key"] != "identite" for x in v["badges"])
