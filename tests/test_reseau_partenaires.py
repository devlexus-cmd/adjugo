"""
Co-traitance v2 — vague 3 : « Vrai réseau de partenaires Adjugo » (innovation B).

Invariants vérifiés :
- classement DÉTERMINISTE (35/25/15/15/10) : un rang et des critères sourcés, jamais un « % » ;
- formulations honnêtes et datées (BODACC « aucun avis trouvé au JJ/MM », DECP « au moins N »,
  None = « non vérifié ») ; une erreur réseau ne remplace jamais une vérification réussie ;
- opt-in : visible = false par défaut ; publication = admin + SIRET 14 chiffres + vérification
  SIRENE active de moins de 30 jours ; un seul profil publié par SIREN ;
- réciprocité (« Publiez votre profil pour voir les N partenaires correspondants ») ;
- hidden_from_sirens dans les deux sens ; compteur d'apparitions ANONYME ;
- mise en relation en 1 clic : email rempli côté serveur, MASQUÉ au chef de file tant que le
  partenaire n'a pas répondu, lien jamais remis au chef de file, 409 si déjà invité ;
- invitation SIRENE hors réseau (lien à transmettre) ; pool « reseau » du score de groupement ;
- historique = COUNT réels dans les deux sens ; cron qui ne dépublie JAMAIS sur erreur ;
- RGPD (export, effacement + recipient effacé, transfert d'organisation) ; démo bloquée ;
  isolation entre entreprises ; aucun profil is_demo exposé ; migration SQLite.
Aucun appel réseau réel : SIRENE / BODACC / DECP / registre sont SIMULÉS.
"""
import json
import os
import random
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

import pytest


# ── Faux registres (aucun appel réseau réel) ─────────────────────────────────────────
class FakeRegistry:
    def __init__(self):
        self.sirene = {}     # siren → {nom, etat 'A'|'C', cp, ville, rge}
        self.bodacc = {}     # siren → enregistrement BODACC (absent = aucun avis)
        self.decp = {}       # siren → nombre de lignes
        self.fail = set()    # {"sirene", "bodacc", "decp"} → panne simulée
        self.calls = []

    def __call__(self, url, params, timeout=5.0):
        if "recherche-entreprises" in url:
            kind = "sirene"
        elif "bodacc" in url:
            kind = "bodacc"
        elif "economie.gouv" in url:
            kind = "decp"
        else:
            raise AssertionError(f"appel réseau inattendu : {url}")
        self.calls.append(kind)
        if kind in self.fail:
            raise RuntimeError("panne simulée")
        if kind == "sirene":
            siren = str(params.get("q"))
            e = self.sirene.get(siren)
            if not e:
                return {"results": []}
            return {"results": [{
                "siren": siren, "nom_complet": e["nom"], "etat_administratif": e.get("etat", "A"),
                "siege": {"siret": siren + "00012", "code_postal": e.get("cp", "29000"),
                          "libelle_commune": e.get("ville", "QUIMPER"), "etat_administratif": "A"},
                "date_creation": "2010-01-01", "categorie_entreprise": "PME", "nature_juridique": "5710",
                "complements": {"est_rge": e.get("rge", False), "est_qualiopi": False},
                "activite_principale": "43.21A"}]}
        siren = re.search(r"\d{9}", params.get("where", "")).group(0)
        if kind == "bodacc":
            rec = self.bodacc.get(siren)
            return {"results": [rec] if rec else []}
        n = self.decp.get(siren, 0)
        return {"results": [{"objet": f"Marché n°{i}", "datenotification": f"2025-0{(i % 9) + 1}-01",
                             "acheteur_id": "21290232900016"} for i in range(n)]}


@pytest.fixture(autouse=True)
def reg(monkeypatch):
    """Registres simulés + caches/plafonds en mémoire remis à zéro + repli SIRENE simulé."""
    import app.routers.reseau as R
    import app.services.partner_network as pn
    import app.services.registre as registre
    fake = FakeRegistry()
    monkeypatch.setattr(pn, "_http_get", fake)
    monkeypatch.setattr(registre, "lookup_company", lambda q, timeout=12: None)
    fake.fallback_calls = []

    def _fallback(trade, dept, warnings):
        fake.fallback_calls.append((trade, dept))
        return list(fake.sirene_pool.get(trade, []))
    fake.sirene_pool = {}
    monkeypatch.setattr(R, "_sirene_fallback", _fallback)
    for d in (pn._APPEAR_SEEN, pn._QUOTA, R._VERIFY_LAST, R._LOOKUP_CACHE):
        d.clear()
    return fake


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.services.email as E

    def _send(to, subject, text, html=None, **kw):
        sent.append((to, subject, text))
        return True
    monkeypatch.setattr(E, "send_email", _send)
    return sent


# ── Helpers ──────────────────────────────────────────────────────────────────
def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _siren():
    return str(random.randint(100_000_000, 999_999_999))


def _org(client, name, *, cp="29000", city="Quimper", siren=None, verified=True, extra=None):
    """Organisation (compte propriétaire) avec un profil entreprise et un SIRET."""
    email = f"o_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Dirigeant", "company_name": name})
    assert r.status_code == 201, r.text
    siren = siren or _siren()
    from app.models import Company, User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = verified
        c = db.query(Company).filter(Company.user_id == u.id).first()
        c.siret, c.postal_code, c.city = siren + "00012", cp, city
        for k, v in (extra or {}).items():
            setattr(c, k, v)
        db.commit()
        uid = u.id
    finally:
        db.close()
    return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}, "email": email,
            "id": uid, "siren": siren, "name": name, "register": r.json()}


def _publish(client, reg, org, metiers=("electricite",), deps=("29",), roles=("cotraitant", "sous_traitant"),
             **put):
    reg.sirene[org["siren"]] = {"nom": org["name"].upper(), "etat": "A"}
    body = {"metiers": list(metiers), "departements": list(deps), "roles_acceptes": list(roles),
            "disponibilite": "disponible", "lot_max_eur": 250000, "presentation": "Électricité générale."}
    body.update(put)
    r = client.put("/api/reseau/profil", headers=org["headers"], json=body)
    assert r.status_code == 200, r.text
    r = client.post("/api/reseau/profil/verifier", headers=org["headers"])
    assert r.status_code == 200, r.text
    r = client.post("/api/reseau/profil/publier", headers=org["headers"], json={"accepte": True})
    assert r.status_code == 200, r.text
    assert r.json()["visible"] is True
    return r.json()["profile_id"]


def _project(client, org, allotissement="Lot 1 : Couverture ; Lot 2 : Électricité ; Lot 3 : Plomberie ; "
                                       "Lot 4 : Peinture ; Lot 5 : Menuiserie"):
    r = client.post("/api/projects/", headers=org["headers"], json={
        "name": "Rénovation de l'école Jules-Ferry", "client": "Ville de Quimper", "budget": 300000,
        "deadline": (date.today() + timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        p.ai_analysis = {"details": {"intitule_marche": "Rénovation de l'école Jules-Ferry",
                                     "acheteur": "Ville de Quimper", "allotissement": allotissement,
                                     "lieu_execution": "Quimper (29)"}}
        db.commit()
    finally:
        db.close()
    return pid


def _profile_row(org_id):
    from app.models import PartnerProfile
    db = _db()
    try:
        return db.query(PartnerProfile).filter(PartnerProfile.user_id == org_id).first()
    finally:
        db.close()


# ── 1. Service PUR : classement déterministe, jamais de % ────────────────────────────
def _p(pid, name, metiers=("electricite",), deps=("29",), **kw):
    d = {"public_id": pid, "name": name, "siren": "123456789", "metiers": list(metiers), "departements": list(deps),
         "roles_acceptes": ["cotraitant"], "disponibilite": "disponible", "lot_max_eur": 100000,
         "declared_at": "2026-10-01T10:00:00", "groupements_deposes": 0,
         "verified_sirene": {"etat": "actif", "checked_at": "2026-10-05T09:00:00"},
         "verified_bodacc": {"found": False, "checked_at": "2026-10-05T09:00:00"},
         "verified_decp": {"count": 3, "checked_at": "2026-10-05T09:00:00"}}
    d.update(kw)
    return d


def test_matching_deterministe_rang_et_criteres_sans_pourcentage():
    from app.services import partner_matching as pm
    today = date(2026, 10, 8)
    lot = {"metier": "electricite", "departement": "29", "montant": None, "role": "cotraitant"}
    profiles = [
        _p("a" * 32, "Zeta Élec", deps=("56",)),                                  # hors zone
        _p("b" * 32, "Alpha Élec"),
        _p("c" * 32, "Beta Élec", verified_decp={"count": 12, "checked_at": "2026-10-05"}),
        _p("d" * 32, "Plombier", metiers=("plomberie",)),                         # métier absent
        _p("e" * 32, "Gamma Élec", verified_bodacc={"found": None}),              # BODACC non vérifié
    ]
    first = pm.rank(lot, profiles, today)
    for _ in range(5):
        shuffled = profiles[:]
        random.shuffle(shuffled)
        assert pm.rank(lot, shuffled, today) == first          # même entrée → même sortie
    assert [r["profile_id"] for r in first] == ["c" * 32, "b" * 32, "e" * 32, "a" * 32]
    assert [r["rang"] for r in first] == [1, 2, 3, 4]
    assert pm.count_matches(lot, profiles, today) == 4
    blob = json.dumps(first, ensure_ascii=False)
    assert "%" not in blob
    for r in first:
        assert set(r) == {"profile_id", "rang", "criteres"}    # ni total, ni score, ni pourcentage
        assert [c["key"] for c in r["criteres"]] == ["metier", "zone", "fiabilite", "experience", "capacite"]
        for c in r["criteres"]:
            assert set(c) == {"key", "label", "statut", "detail", "source", "date"}
            assert c["source"]
    # Égalité parfaite → départage par nom (stable).
    twins = [_p("f" * 32, "Bravo"), _p("0" * 32, "Alpha")]
    assert [r["profile_id"] for r in pm.rank(lot, twins, today)] == ["0" * 32, "f" * 32]


def test_formulations_honnetes_et_datees():
    from app.services import partner_matching as pm
    assert pm.bodacc_label({"found": False, "checked_at": "2026-10-08T10:00:00"}) == \
        "Aucun avis de procédure collective trouvé au 08/10 (recherche BODACC)"
    assert pm.bodacc_label({"found": None}) == "BODACC : non vérifié"
    assert pm.bodacc_label(None) == "BODACC : non vérifié"
    assert pm.bodacc_label({"found": True, "ongoing": True, "nature": "Redressement judiciaire",
                            "date": "2025-03-12", "checked_at": "2026-10-08"}).startswith(
        "Procédure collective publiée au BODACC le 12/03/2025")
    assert pm.decp_label({"count": 3, "checked_at": "2026-10-08"}) == \
        "Au moins 3 marchés publics publiés dans DECP (au 08/10)"
    assert pm.decp_label({"count": 0, "checked_at": "2026-10-08"}) == "Aucun marché trouvé dans DECP au 08/10"
    assert pm.decp_label({"count": None}) == "DECP : non vérifié"
    assert pm.sirene_label({"etat": "actif", "checked_at": "2026-10-08"}) == "Entreprise active (SIRENE au 08/10)"
    assert pm.sirene_label(None) == "SIRENE : non vérifié"
    b = pm.badges(_p("a" * 32, "X", verified_sirene={"etat": "actif", "est_rge": True, "checked_at": "2026-10-08"}))
    rge = next(x for x in b if x["key"] == "rge")
    assert rge["label"] == "Inscrite au registre RGE (ADEME) au 08/10 — domaine à vérifier"
    assert all(x["source"] for x in b)
    joined = json.dumps(b, ensure_ascii=False).lower()
    for mot in ("étoile", "avis client", "note", "/5"):
        assert mot not in joined


def test_fiche_publique_sous_ensemble_strict():
    from app.services import partner_matching as pm
    p = _p("a" * 32, "X", references_publiques=[])
    p.update({"email": "secret@x.fr", "phone": "0600000000", "ca_n1": 999999, "effectif": 42,
              "hidden_from_sirens": ["111111111"], "appearances_count": 7})
    card = pm.public_card(p)
    assert "references" not in card                     # non choisies → non affichées
    s = json.dumps(card, ensure_ascii=False)
    for secret in ("secret@x.fr", "0600000000", "999999", "111111111", "appearances", "hidden", "ca_n1", "effectif"):
        assert secret not in s
    caps = {c["key"]: c for c in card["capacites"]}
    assert caps["metiers"]["source"] == "déclaré par l'entreprise" and caps["metiers"]["date"] == "2026-10-01"
    assert caps["marches_publics"]["valeur"] == "au moins 3" and caps["marches_publics"]["date"] == "2026-10-05"
    p["references_publiques"] = [{"intitule": "Groupe scolaire", "client": "Ville de Brest", "annee": 2025}]
    card = pm.public_card(p)
    assert card["references"][0]["intitule"] == "Groupe scolaire"


# ── 2. Profil : pré-remplissage, opt-in, validation ──────────────────────────────────
def test_profil_prerempli_opt_in_et_validation(client, reg, monkeypatch):
    org = _org(client, "Le Gall Électricité", extra={"phone": "0298000000"})
    import app.services.registre as registre
    calls = []

    def _lookup(q, timeout=12):
        calls.append((q, timeout))
        return {"name": "LE GALL ELECTRICITE", "postal_code": "29000", "city": "QUIMPER",
                "specialite": "électricité", "naf_label": "Électricité"}
    monkeypatch.setattr(registre, "lookup_company", _lookup)
    r = client.get("/api/reseau/profil", headers=org["headers"])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["exists"] is False and v["visible"] is False
    assert v["identite"]["siret"] == org["siren"] + "00012"
    assert "electricite" in v["declare"]["metiers"]                 # nom « … Électricité » → métier
    assert v["declare"]["departements"] == ["29"]
    assert calls and calls[0][1] <= 5                               # délai court (process unique)
    assert "registre SIRENE" in v["prefill_sources"]
    assert v["suggestion"]["code"] == "publier_profil_reseau"
    # Création : opt-in, jamais publié par défaut.
    r = client.put("/api/reseau/profil", headers=org["headers"], json={"presentation": "Électricité générale."})
    assert r.status_code == 200, r.text
    assert r.json()["exists"] is True and r.json()["visible"] is False and r.json()["statut"] == "brouillon"
    row = _profile_row(org["id"])
    assert row.visible is False and row.is_demo is False and re.fullmatch(r"[0-9a-f]{32}", row.public_id)
    for body, frag in (({"metiers": ["astronaute"]}, "Métier inconnu"),
                       ({"presentation": "x" * 301}, "300 caractères"),
                       ({"departements": ["Bretagne"]}, "Département invalide"),
                       ({"roles_acceptes": ["patron"]}, "Rôle inconnu"),
                       ({"hidden_from_sirens": ["12"]}, "SIREN invalide"),
                       ({"codes_cpv": ["4531"]}, "8 chiffres"),
                       ({"references_publiques": [{"client": "X"}]}, "intitulé")):
        r = client.put("/api/reseau/profil", headers=org["headers"], json=body)
        assert r.status_code == 422 and frag in r.text, (body, r.text)


def test_verification_formulations_et_erreur_reseau(client, reg):
    org = _org(client, "Morvan Plomberie")
    client.put("/api/reseau/profil", headers=org["headers"], json={"metiers": ["plomberie"], "departements": ["29"]})
    # 1re vérification en panne totale : « non vérifié », rien d'inventé.
    reg.fail = {"sirene", "bodacc", "decp"}
    r = client.post("/api/reseau/profil/verifier", headers=org["headers"])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["verifications"]["sirene"]["label"] == "SIRENE : non vérifié"
    assert v["verifications"]["bodacc"]["label"] == "BODACC : non vérifié"
    assert v["verifications"]["decp"]["label"] == "DECP : non vérifié"
    assert v["verification"]["sirene"]["statut"] == "erreur"
    assert v["publication"]["peut_publier"] is False
    # Vérification réussie : formulations datées.
    reg.fail = set()
    reg.sirene[org["siren"]] = {"nom": "MORVAN PLOMBERIE", "etat": "A", "rge": True}
    reg.decp[org["siren"]] = 4
    import app.routers.reseau as R
    R._VERIFY_LAST.clear()
    v = client.post("/api/reseau/profil/verifier", headers=org["headers"]).json()
    d = datetime.utcnow().strftime("%d/%m")
    assert v["verifications"]["sirene"]["label"] == f"Entreprise active (SIRENE au {d})"
    assert v["verifications"]["bodacc"]["label"] == f"Aucun avis de procédure collective trouvé au {d} (recherche BODACC)"
    assert v["verifications"]["decp"]["label"] == f"Au moins 4 marchés publics publiés dans DECP (au {d})"
    assert v["identite"]["name"] == "MORVAN PLOMBERIE" and v["identite"]["nom_officiel"] is True
    assert any(b["key"] == "rge" for b in v["badges"])
    # Une panne ultérieure ne remplace JAMAIS la vérification réussie (sa date est conservée).
    before = _profile_row(org["id"]).verified_bodacc
    R._VERIFY_LAST.clear()
    reg.fail = {"bodacc", "decp"}
    v = client.post("/api/reseau/profil/verifier", headers=org["headers"]).json()
    assert _profile_row(org["id"]).verified_bodacc == before
    assert "conservée" in v["verification"]["bodacc"]["message"]
    # Cooldown : pas plus d'une vérification toutes les 10 min.
    assert client.post("/api/reseau/profil/verifier", headers=org["headers"]).status_code == 429


def test_publication_conditions(client, reg):
    org = _org(client, "Kerjean Menuiserie")
    h = org["headers"]
    assert client.post("/api/reseau/profil/publier", headers=h, json={"accepte": True}).status_code == 404
    client.put("/api/reseau/profil", headers=h, json={"metiers": ["menuiserie"], "departements": ["29"]})
    r = client.post("/api/reseau/profil/publier", headers=h, json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "consentement_requis"
    r = client.post("/api/reseau/profil/publier", headers=h, json={"accepte": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "verification_requise"
    reg.sirene[org["siren"]] = {"nom": "KERJEAN MENUISERIE", "etat": "A"}
    assert client.post("/api/reseau/profil/verifier", headers=h).status_code == 200
    # Vérification de plus de 30 jours → refus.
    from app.models import PartnerProfile
    db = _db()
    try:
        p = db.query(PartnerProfile).filter(PartnerProfile.user_id == org["id"]).first()
        p.verified_at = datetime.utcnow() - timedelta(days=31)
        db.commit()
    finally:
        db.close()
    r = client.post("/api/reseau/profil/publier", headers=h, json={"accepte": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "verification_requise"
    db = _db()
    try:
        p = db.query(PartnerProfile).filter(PartnerProfile.user_id == org["id"]).first()
        p.verified_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
    # Un membre (non admin) ne publie pas.
    from app.core.security import create_access_token
    from app.models import User
    em = f"m_{uuid.uuid4().hex[:8]}@test.fr"
    assert client.post("/api/org/invite", headers=h, json={"email": em, "full_name": "Salarié"}).status_code == 201
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        mh = {"Authorization": "Bearer " + create_access_token(data={"sub": str(m.id), "tv": int(m.token_version or 0)})}
    finally:
        db.close()
    r = client.post("/api/reseau/profil/publier", headers=mh, json={"accepte": True})
    assert r.status_code == 403 and "administrateur" in r.text
    assert client.put("/api/reseau/profil", headers=mh, json={"presentation": "x"}).status_code == 403
    assert client.get("/api/reseau/profil", headers=mh).status_code == 200       # lecture : tous les membres
    # Succès.
    r = client.post("/api/reseau/profil/publier", headers=h, json={"accepte": True})
    assert r.status_code == 200 and r.json()["visible"] is True and r.json()["statut"] == "publie"
    # Même SIREN sur une autre organisation : un seul profil publié par entreprise.
    twin = _org(client, "Kerjean bis", siren=org["siren"])
    client.put("/api/reseau/profil", headers=twin["headers"], json={"metiers": ["menuiserie"], "departements": ["29"]})
    assert client.post("/api/reseau/profil/verifier", headers=twin["headers"]).status_code == 200
    r = client.post("/api/reseau/profil/publier", headers=twin["headers"], json={"accepte": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "siren_deja_publie"
    # Entreprise cessée → publication impossible.
    ce = _org(client, "Ancienne SARL")
    client.put("/api/reseau/profil", headers=ce["headers"], json={"metiers": ["peinture"], "departements": ["29"]})
    reg.sirene[ce["siren"]] = {"nom": "ANCIENNE SARL", "etat": "C"}
    client.post("/api/reseau/profil/verifier", headers=ce["headers"])
    r = client.post("/api/reseau/profil/publier", headers=ce["headers"], json={"accepte": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "entreprise_inactive"
    # Retrait de la publication.
    r = client.delete("/api/reseau/profil/publier", headers=h)
    assert r.status_code == 200 and r.json()["visible"] is False and r.json()["statut"] == "retire"


# ── 3. Réciprocité, masquage dans les deux sens, compteur anonyme ─────────────────────
def test_reciprocite_annuaire_et_fiche(client, reg):
    b = _org(client, "Réseau Élec B")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chercheur A")
    r = client.get("/api/reseau/annuaire?metier=electricite&departement=29", headers=a["headers"])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["visible"] is False and v["profils"] == [] and v["total"] >= 1
    assert re.fullmatch(r"Publiez votre profil pour voir (le partenaire correspondant|les \d+ partenaires correspondants)\.",
                        v["message"]), v["message"]
    r = client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "profil_non_publie"
    assert _profile_row(b["id"]).appearances_count == 0              # le teaser ne compte pas
    _publish(client, reg, a, metiers=("couverture",))
    v = client.get("/api/reseau/annuaire?metier=electricite&departement=29", headers=a["headers"]).json()
    assert v["visible"] is True
    mine = [p for p in v["profils"] if p["profile_id"] == b_pid]
    assert mine and mine[0]["rang"] >= 1 and mine[0]["criteres"]
    fiche = client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"])
    assert fiche.status_code == 200, fiche.text
    assert fiche.json()["name"] == b["name"].upper()
    assert set(fiche.json()["historique_avec_vous"]) == {"invitations_actives", "parts_soumises",
                                                          "marches_deposes", "gagnes", "perdus"}
    # Son propre profil n'apparaît jamais dans l'annuaire.
    v = client.get("/api/reseau/annuaire?metier=couverture", headers=a["headers"]).json()
    assert all(p["name"] != a["name"].upper() for p in v["profils"])


def test_hidden_from_sirens_dans_les_deux_sens(client, reg):
    a = _org(client, "Concurrent A")
    b = _org(client, "Discret B")
    c = _org(client, "Tiers C")
    a_pid = _publish(client, reg, a)
    b_pid = _publish(client, reg, b, hidden_from_sirens=[a["siren"] + "00012"])   # SIRET accepté → SIREN
    c_pid = _publish(client, reg, c)
    assert _profile_row(b["id"]).hidden_from_sirens == [a["siren"]]

    def ids(org):
        v = client.get("/api/reseau/annuaire?metier=electricite&par_page=50", headers=org["headers"]).json()
        return {p["profile_id"] for p in v["profils"]}
    assert b_pid not in ids(a) and c_pid in ids(a)          # B me masque : je ne le vois pas
    assert a_pid not in ids(b) and c_pid in ids(b)          # …et B ne me voit pas non plus
    assert client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"]).status_code == 404
    assert client.get(f"/api/reseau/annuaire/{a_pid}", headers=b["headers"]).status_code == 404
    pid = _project(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid})
    assert r.status_code == 404
    m = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).json()
    assert b_pid not in json.dumps(m)


def test_compteur_d_apparitions_anonyme(client, reg):
    from app.models import AuditLog
    b = _org(client, "Cherchée B")
    b_pid = _publish(client, reg, b, metiers=("etancheite",), deps=("22",))
    a = _org(client, "Chercheur Un")
    c = _org(client, "Chercheur Deux")
    _publish(client, reg, a, metiers=("couverture",))
    _publish(client, reg, c, metiers=("couverture",))
    for _ in range(3):        # le même chercheur ne compte qu'une fois par mois
        assert client.get("/api/reseau/annuaire?metier=etancheite", headers=a["headers"]).status_code == 200
    assert _profile_row(b["id"]).appearances_count == 1
    client.get("/api/reseau/annuaire?metier=etancheite", headers=c["headers"])
    row = _profile_row(b["id"])
    assert row.appearances_count == 2 and row.appearances_period == datetime.utcnow().strftime("%Y-%m")
    v = client.get("/api/reseau/profil", headers=b["headers"]).json()
    assert v["apparitions_ce_mois"] == 2
    s = json.dumps(v, ensure_ascii=False)
    for who in (a, c):        # un profil ne sait JAMAIS qui l'a cherché
        assert who["siren"] not in s and who["name"].upper() not in s and who["name"] not in s
    db = _db()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action.like("network.%query")).all()
        assert rows and all(r.owner_id != b["id"] for r in rows)
        assert {r.owner_id for r in rows if r.action == "network.annuaire_query"} >= {a["id"], c["id"]}
    finally:
        db.close()


# ── 4. « Qui me complète ? » lot par lot ─────────────────────────────────────────────
def test_partner_matches_par_lot_sans_second_pourcentage(client, reg):
    b = _org(client, "Le Gall Électricité Réseau")
    reg.decp[b["siren"]] = 12          # au moins 12 marchés DECP → classé premier sur son lot
    b_pid = _publish(client, reg, b, metiers=("electricite",), deps=("29",))
    a = _org(client, "Breizh Couverture")
    pid = _project(client, a)
    reg.sirene_pool["plomberie"] = [{"name": "PLOMBERIE DU FINISTERE", "siret": "55544433300011",
                                     "city": "BREST", "departement": "29", "specialites": "Plomberie / CVC",
                                     "qualifications": ["RGE (registre ADEME)"], "as_of": date.today().isoformat()}]
    # Non publié : seulement un compteur et le repli SIRENE.
    r = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["reseau_visible"] is False and v["n_correspondants"] >= 1
    assert v["message"].startswith("Publiez votre profil pour voir")
    lots = {l["num"]: l for l in v["lots"]}
    assert set(lots) == {"2", "3", "4", "5"}                         # lot 1 (couverture) couvert
    assert [l["num"] for l in v["lots_couverts"]] == ["1"]
    assert all(l["reseau"] == [] for l in v["lots"])
    assert len(reg.fallback_calls) == 3                              # ≤ 3 lots SIRENE par appel
    assert "sirene_message" in lots["5"] and lots["5"]["sirene_cherche"] is False
    assert lots["3"]["sirene"][0]["statut_reseau"] == "Hors réseau Adjugo — à inviter par lien"
    assert _profile_row(b["id"]).appearances_count == 0
    # Publié : profils classés par lot.
    _publish(client, reg, a, metiers=("couverture",))
    reg.fallback_calls.clear()
    v = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).json()
    lot2 = next(l for l in v["lots"] if l["num"] == "2")
    top = lot2["reseau"][0]
    assert top["profile_id"] == b_pid and top["rang"] == 1
    assert top["simulation"] == {"kind": "reseau", "profile_id": b_pid}
    assert top["deja_invite"] is False
    assert {c["key"] for c in top["criteres"]} == {"metier", "zone", "fiabilite", "experience", "capacite"}
    # UN seul pourcentage affiché : jamais de « % », de score ni de total dans cette réponse.
    blob = json.dumps(v, ensure_ascii=False)
    assert "%" not in blob
    for k in ('"score"', '"total"', '"pourcentage"', '"score_avec"', '"points"'):
        assert k not in blob
    # Un lot seul → recherche SIRENE pour ce lot.
    reg.fallback_calls.clear()
    v = client.get(f"/api/projects/{pid}/partner-matches?lot=5", headers=a["headers"]).json()
    assert [l["num"] for l in v["lots"]] == ["5"] and reg.fallback_calls == [("menuiserie", "29")]
    assert client.get(f"/api/projects/{pid}/partner-matches?lot=1", headers=a["headers"]).status_code == 404


def test_simulation_avec_un_profil_du_reseau(client, reg):
    b = _org(client, "Élec Simulée")
    b_pid = _publish(client, reg, b, metiers=("electricite",))
    a = _org(client, "Couvreur Simulateur")
    pid = _project(client, a)
    body = {"members": [{"kind": "reseau", "profile_id": b_pid, "ca_n1": 9_000_000, "effectif": 300}], "save": True}
    r = client.post(f"/api/projects/{pid}/groupement/simulate", headers=a["headers"], json=body)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "profil_non_publie"
    _publish(client, reg, a, metiers=("couverture",))
    # Pool « reseau » du panneau « Ce que le marché exige → Trouver qui l'a ».
    r = client.get(f"/api/projects/{pid}/groupement/besoins", headers=a["headers"])
    assert r.status_code == 200, r.text
    net = r.json()["candidats"]["reseau"]
    cand = next(c for c in net if c.get("profile_id") == b_pid)
    assert cand["kind"] == "reseau" and cand["capacites_source"] == "reseau" and cand["rang"] >= 1
    assert cand["proof_label"].startswith("déclaré par l'entreprise sur son profil Adjugo")
    assert cand["capacites"]["ca_n1"] is None and "_db_id" not in cand
    assert _profile_row(b["id"]).appearances_count >= 1
    r = client.post(f"/api/projects/{pid}/groupement/simulate", headers=a["headers"], json=body)
    assert r.status_code == 200, r.text
    m = next(x for x in r.json()["members"] if x["kind"] == "reseau")
    assert m["profile_id"] == b_pid and m["ca_n1"] is None and m["effectif"] is None   # le body est IGNORÉ
    assert m["source"] == "reseau"
    assert any("non affiché sur le réseau" in w for w in r.json()["warnings"])
    sim_id = r.json()["simulation_id"]
    r = client.post(f"/api/projects/{pid}/groupement/retenir", headers=a["headers"], json={"simulation_id": sim_id})
    assert r.status_code == 200, r.text
    from app.routers.cotraitants import Cotraitant
    db = _db()
    try:
        ct = db.query(Cotraitant).filter(Cotraitant.user_id == a["id"], Cotraitant.siret == b["siren"] + "00012").first()
        assert ct is not None and ct.capacites_source == "reseau" and not ct.email and not ct.phone
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/groupement/simulate", headers=a["headers"],
                    json={"members": [{"kind": "reseau", "profile_id": "0" * 32}]})
    assert r.status_code == 404


# ── 5. Mise en relation en 1 clic : email masqué ─────────────────────────────────────
def test_invitation_reseau_email_masque_jusqu_a_la_reponse(client, reg, mails):
    b = _org(client, "Partenaire Masqué")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef de File Réseau")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b_pid, "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["emailed"] is True
    inv = out["invitation"]
    assert inv["source"] == "reseau_adjugo" and inv["recipient"] == "" and inv["recipient_masque"] is True
    assert inv["token"] is None and inv["path"] is None and "url" not in inv
    assert b["email"] not in json.dumps(out)
    # Email envoyé PAR ADJUGO au compte du profil.
    assert mails and mails[-1][0] == b["email"] and "Lot 2 — Électricité" in mails[-1][2]
    assert "retirer cette publication" in mails[-1][2]
    # Côté chef de file : liste, journal, cockpit — jamais l'adresse.
    for path in (f"/api/projects/{pid}/invites", f"/api/projects/{pid}/audit", f"/api/projects/{pid}/consortium",
                 "/api/notifications"):
        rr = client.get(path, headers=a["headers"])
        assert rr.status_code == 200, (path, rr.text)
        assert b["email"] not in rr.text, path
        assert b["email"].split("@")[0] not in rr.text, path
    # Rattachement à l'annuaire, sans email.
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    db = _db()
    try:
        lk = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == pid).first()
        assert lk.source == "reseau_adjugo" and lk.invite_id == inv["id"] and lk.lot == "Lot 2 — Électricité"
        ct = db.get(Cotraitant, lk.cotraitant_id)
        assert ct.capacites_source == "reseau" and not ct.email
    finally:
        db.close()
    # 409 si une invitation active existe déjà.
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "deja_invite"
    # Relance : même texte réseau, adresse toujours absente de la réponse.
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, inv["id"]).emailed_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/invites/{inv['id']}/resend", headers=a["headers"])
    assert r.status_code == 200 and r.json()["sent"] is True and b["email"] not in r.text
    assert mails[-1][0] == b["email"] and "retirer cette publication" in mails[-1][2]
    # Le partenaire la retrouve dans son espace (même sans email) et l'accepte depuis son compte.
    recues = client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"]
    mine = [x for x in recues if x["project"] == "Rénovation de l'école Jules-Ferry" and x["mandataire"] == a["name"]]
    assert mine and mine[0]["statut"] == "a_repondre" and mine[0]["lot_propose"] == "Lot 2 — Électricité"
    token = mine[0]["token"]
    g = client.get(f"/api/invite/{token}").json()               # aperçu minimal avant acceptation
    assert g["apercu_minimal"] is True and g["project"]["client"] is None and g["documents"] == []
    assert "acheteur" not in g["project"]["analysis"] and g["project"]["analysis"]["objet"]
    assert g["for_member"] is None and g["project"]["source_url"] is None
    assert client.get(f"/api/invite/{token}/coffre-croise").status_code == 403
    j = client.get(f"/api/invite/{token}/journal").json()["entries"]
    assert all(e["who"] in ("vous", "mandataire") for e in j)
    r = client.post(f"/api/invite/{token}/claim", headers=b["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["suggest_profile"] is None                   # B a déjà publié
    g = client.get(f"/api/invite/{token}").json()
    assert g["apercu_minimal"] is False and g["project"]["client"] == "Ville de Quimper"
    assert g["for_member"] is not None
    assert client.get(f"/api/invite/{token}/coffre-croise").status_code == 200
    lst = client.get(f"/api/projects/{pid}/invites", headers=a["headers"]).json()
    me = next(x for x in lst if x["id"] == inv["id"])
    assert me["recipient"] == b["email"] and me["recipient_masque"] is False and me["token"] is None


def test_invitation_reseau_regles_anti_spam(client, reg, mails):
    b = _org(client, "Partenaire Sollicité")
    b_pid = _publish(client, reg, b, roles=("sous_traitant",))
    a = _org(client, "Chef Non Publié")
    pid = _project(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "profil_non_publie"
    _publish(client, reg, a, metiers=("couverture",))
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid})
    assert r.status_code == 422 and "n'accepte pas le rôle" in r.text
    # Expéditeur non confirmé → 403 (le lien ne peut pas être remis au chef de file).
    u = _org(client, "Chef Non Confirmé", verified=False)
    pid2 = _project(client, u)
    r = client.post(f"/api/projects/{pid2}/reseau/invitations", headers=u["headers"],
                    json={"profile_id": b_pid, "role": "sous_traitant"})
    assert r.status_code == 403 and "Confirmez" in r.text
    assert mails == []
    # Plafond quotidien par organisation (règle existante, partagée).
    import app.routers.invites as I
    old = I.DAILY_INVITE_CAP
    I.DAILY_INVITE_CAP = 0
    try:
        r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                        json={"profile_id": b_pid, "role": "sous_traitant"})
        assert r.status_code == 429
    finally:
        I.DAILY_INVITE_CAP = old
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b_pid, "role": "sous_traitant"})
    assert r.status_code == 200, r.text


def test_invitation_sirene_hors_reseau(client, reg, mails):
    a = _org(client, "Chef Lien SIRENE")
    pid = _project(client, a)
    siren = _siren()
    reg.sirene[siren] = {"nom": "PEINTURES DE L'ODET", "etat": "A", "cp": "29000", "ville": "QUIMPER"}
    r = client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"],
                    json={"siret": siren + "00012", "lot": "Lot 4 — Peinture"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["emailed"] is False and mails == []
    assert v["invitation"]["source"] == "sirene" and v["invitation"]["recipient"] == ""
    assert v["invitation"]["company_name"] == "PEINTURES DE L'ODET"
    assert v["url"].endswith(v["invitation"]["path"]) and v["invitation"]["token"]
    r = client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"],
                    json={"siret": siren + "00012"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "deja_invite"
    ce = _siren()
    reg.sirene[ce] = {"nom": "FERMEE SARL", "etat": "C"}
    r = client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"], json={"siret": ce + "00012"})
    assert r.status_code == 422 and "pas active" in r.text
    reg.fail = {"sirene"}
    r = client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"], json={"siret": _siren() + "00012"})
    assert r.status_code == 503
    reg.fail = set()
    assert client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"],
                       json={"siret": "123"}).status_code == 422
    # Entreprise PUBLIÉE sur le réseau (et visible) → passer par le réseau (adresse masquée).
    b = _org(client, "Sur Le Réseau")
    b_pid = _publish(client, reg, b)
    _publish(client, reg, a, metiers=("couverture",))
    r = client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=a["headers"],
                    json={"siret": b["siren"] + "00012"})
    assert r.status_code == 409 and r.json()["detail"] == {
        "code": "sur_le_reseau", "profile_id": b_pid,
        "message": "Cette entreprise est sur le réseau Adjugo : invitez-la depuis sa fiche (Adjugo lui transmet l'invitation)."}


def test_creation_d_invitation_manuelle_inchangee(client, auth, reg):
    pid = client.post("/api/projects/", headers=auth["headers"], json={"name": "AO manuel", "client": "X"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/invites", headers=auth["headers"],
                    json={"recipient": "contact@partenaire.fr", "company_name": "Partenaire Manuel"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["token"] and v["path"] == f"/invite/{v['token']}" and v["url"].endswith(v["path"])
    assert v["recipient"] == "contact@partenaire.fr" and v["recipient_masque"] is False and v["source"] == "manuel"
    assert client.get(f"/api/invite/{v['token']}").json()["apercu_minimal"] is False


# ── 6. Historique réel (COUNT, dans les deux sens) ───────────────────────────────────
def test_historique_comptes_reels_dans_les_deux_sens(client, reg, mails):
    b = _org(client, "Membre Historique")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef Historique")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"], json={"profile_id": b_pid})
    assert r.status_code == 200, r.text
    token = client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"][0]["token"]
    v = client.get(f"/api/invite/{token}/contribution").json()["version"]
    assert client.put(f"/api/invite/{token}/contribution", json={"version": v, "lot": "Lot 2", "prix_lot_ht": 40000}).status_code == 200
    assert client.post(f"/api/invite/{token}/contribution/submit").status_code == 200
    assert client.put(f"/api/projects/{pid}", headers=a["headers"], json={"status": "envoye"}).status_code == 200
    ha = client.get("/api/reseau/historique", headers=a["headers"]).json()
    assert ha["comme_chef_de_file"] == {"invitations_actives": 1, "parts_recues": 1, "marches_deposes": 1,
                                        "gagnes": 0, "perdus": 0}
    assert ha["groupements_deposes"] == 1
    hb = client.get("/api/reseau/historique", headers=b["headers"]).json()
    assert hb["comme_partenaire"] == {"invitations_actives": 1, "parts_soumises": 1, "marches_deposes": 1,
                                      "gagnes": 0, "perdus": 0}
    assert hb["groupements_deposes"] == 1 and _profile_row(b["id"]).groupements_deposes == 1
    avec = client.get(f"/api/reseau/historique?profile_id={b_pid}", headers=a["headers"]).json()["avec"]
    assert avec["marches_deposes"] == 1 and avec["parts_soumises"] == 1
    # Badge « groupement déposé via Adjugo » (dépôt réel) sur la fiche de B.
    fiche = client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"]).json()
    assert any(x["key"] == "adjugo" and x["label"] == "1 groupement déposé via Adjugo" for x in fiche["badges"])
    # COUNT seulement : aucun nom de marché, aucune adresse.
    for h in (ha, hb, avec):
        s = json.dumps(h, ensure_ascii=False)
        assert "Jules-Ferry" not in s and "@" not in s
    assert client.put(f"/api/projects/{pid}", headers=a["headers"], json={"status": "gagne"}).status_code == 200
    assert client.get("/api/reseau/historique", headers=a["headers"]).json()["comme_chef_de_file"]["gagnes"] == 1


# ── 7. Cron : ne dépublie JAMAIS sur erreur ──────────────────────────────────────────
def test_cron_borne_et_jamais_de_depublication_sur_erreur(client, reg, monkeypatch):
    import app.routers.admin as admin
    from app.models import PartnerProfile
    monkeypatch.setattr(admin.settings, "CRON_SECRET", "secret-reseau")
    assert client.post("/api/admin/run-partner-network").status_code == 403
    b = _org(client, "Profil Ancien")
    _publish(client, reg, b)
    db = _db()
    try:
        p = db.query(PartnerProfile).filter(PartnerProfile.user_id == b["id"]).first()
        p.verified_at = datetime(2000, 1, 1)       # le plus anciennement vérifié → traité en premier
        db.commit()
    finally:
        db.close()
    before = _profile_row(b["id"]).verified_sirene
    hdr = {"X-Cron-Secret": "secret-reseau"}
    reg.fail = {"sirene", "bodacc", "decp"}                      # panne réseau totale
    r = client.post("/api/admin/run-partner-network", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["unpublished"] == 0 and r.json()["checked"] <= 25
    row = _profile_row(b["id"])
    assert row.visible is True and row.verified_sirene == before
    reg.fail = set()
    del reg.sirene[b["siren"]]                                   # SIREN introuvable ≠ cessé
    client.post("/api/admin/run-partner-network", headers=hdr)
    assert _profile_row(b["id"]).visible is True
    reg.bodacc[b["siren"]] = {"jugement": {"famille": "Jugement d'ouverture", "nature": "Liquidation judiciaire",
                                           "date": "2026-09-01"}, "dateparution": "2026-09-05"}
    reg.sirene[b["siren"]] = {"nom": b["name"].upper(), "etat": "A"}
    client.post("/api/admin/run-partner-network", headers=hdr)
    row = _profile_row(b["id"])
    assert row.visible is True and row.verified_bodacc["found"] is True    # avertir, pas dépublier
    db = _db()
    try:
        p = db.query(PartnerProfile).filter(PartnerProfile.user_id == b["id"]).first()
        p.verified_at = datetime(2000, 1, 1)
        db.commit()
    finally:
        db.close()
    reg.sirene[b["siren"]] = {"nom": b["name"].upper(), "etat": "C"}     # réponse POSITIVE « cessé »
    r = client.post("/api/admin/run-partner-network", headers=hdr).json()
    assert r["unpublished"] >= 1
    assert _profile_row(b["id"]).visible is False
    v = client.get("/api/reseau/profil", headers=b["headers"]).json()
    assert v["statut"] == "retire" and "cessé" in v["statut_label"]


# ── 8. RGPD : export, effacement, transfert ──────────────────────────────────────────
def test_rgpd_export_effacement_et_recipient_efface(client, reg, mails):
    from app.models import ProjectInvite
    b = _org(client, "Partenaire Effacé")
    b_pid = _publish(client, reg, b, hidden_from_sirens=["111222333"])
    a = _org(client, "Chef RGPD")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    inv_id = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                         json={"profile_id": b_pid}).json()["invitation"]["id"]
    exp = client.get("/api/rgpd/export", headers=b["headers"])
    assert exp.status_code == 200
    prof = json.loads(exp.content)["profil_partenaire_reseau"]
    assert prof["public_id"] == b_pid and prof["hidden_from_sirens"] == ["111222333"]
    db = _db()
    try:
        assert db.get(ProjectInvite, inv_id).recipient == b["email"]
    finally:
        db.close()
    r = client.post("/api/rgpd/delete-account", headers=b["headers"],
                    json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    assert _profile_row(b["id"]) is None
    db = _db()
    try:
        inv = db.get(ProjectInvite, inv_id)
        assert inv.recipient == "" and inv.verified_email == "" and inv.partner_profile_id is None
    finally:
        db.close()
    assert client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"]).status_code == 404
    # Effacement du seul profil (sans supprimer le compte).
    c = _org(client, "Profil Seul Effacé")
    _publish(client, reg, c)
    assert client.delete("/api/reseau/profil", headers=c["headers"]).status_code == 200
    assert _profile_row(c["id"]) is None


def test_transfert_d_organisation_le_profil_suit(client, reg):
    from app.core.security import create_access_token
    from app.models import User
    a = _org(client, "Org Transférée")
    a_pid = _publish(client, reg, a)
    em = f"r_{uuid.uuid4().hex[:8]}@test.fr"
    assert client.post("/api/org/invite", headers=a["headers"], json={"email": em, "full_name": "Repreneur"}).status_code == 201
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        mid = m.id
    finally:
        db.close()
    r = client.post("/api/org/transfer-ownership", headers=a["headers"], json={"new_owner_id": mid})
    assert r.status_code == 200, r.text
    assert _profile_row(a["id"]) is None and _profile_row(mid).public_id == a_pid
    db = _db()
    try:
        m = db.get(User, mid)
        mh = {"Authorization": "Bearer " + create_access_token(data={"sub": str(m.id), "tv": int(m.token_version or 0)})}
    finally:
        db.close()
    v = client.get("/api/reseau/profil", headers=mh).json()
    assert v["profile_id"] == a_pid and v["visible"] is True and v["peut_modifier"] is True


# ── 9. Démo bloquée, aucun profil démo exposé, isolation ─────────────────────────────
def test_demo_bloquee_sur_le_reseau(client, reg):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    dh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.get("/api/projects/", headers=dh).json()[0]["id"]
    for method, path, body in (("PUT", "/api/reseau/profil", {"presentation": "x"}),
                               ("DELETE", "/api/reseau/profil", None),
                               ("POST", "/api/reseau/profil/verifier", None),
                               ("POST", "/api/reseau/profil/publier", {"accepte": True}),
                               ("DELETE", "/api/reseau/profil/publier", None),
                               ("POST", f"/api/projects/{pid}/reseau/invitations", {"profile_id": "a" * 32}),
                               ("POST", f"/api/projects/{pid}/reseau/invitations-sirene", {"siret": "12345678900011"})):
        r = client.request(method, path, headers=dh, json=body)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["detail"].startswith("La démo est en lecture guidée"), r.text
    v = client.get("/api/reseau/annuaire?metier=electricite", headers=dh).json()
    assert v["visible"] is False and v["profils"] == []
    assert client.get("/api/reseau/profil", headers=dh).json()["suggestion"] is None
    from app.core.demo_guard import blocked_action
    for m, p in (("PUT", "/api/reseau/profil"), ("POST", "/api/reseau/profil/publier"),
                 ("POST", "/api/projects/7/reseau/invitations"), ("POST", "/api/projects/7/reseau/invitations-sirene")):
        assert blocked_action(m, p)


def test_aucun_profil_demo_expose(client, reg):
    from app.models import PartnerProfile, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    a = _org(client, "Chercheur Anti-Démo")
    _publish(client, reg, a, metiers=("couverture",))
    db = _db()
    try:
        assert db.query(PartnerProfile).filter(PartnerProfile.is_demo.is_(True)).count() == 0   # aucun créé
        demo = ensure_demo(db)
        fake = PartnerProfile(public_id=uuid.uuid4().hex, user_id=_org(client, "Fictive SARL")["id"], visible=True,
                              is_demo=True, name="FICTIVE DEMO", siren=_siren(), metiers=["etancheite"],
                              departements=["29"], verified_sirene={"etat": "actif", "checked_at": datetime.utcnow().isoformat()},
                              verified_at=datetime.utcnow())
        db.add(fake)
        if not db.query(PartnerProfile).filter(PartnerProfile.user_id == demo.id).first():
            db.add(PartnerProfile(public_id=uuid.uuid4().hex, user_id=demo.id, visible=True, is_demo=False,
                                  name="COMPTE DEMO", siren=_siren(), metiers=["etancheite"], departements=["29"]))
        db.commit()
        fake_pid = fake.public_id
    finally:
        db.close()
    v = client.get("/api/reseau/annuaire?metier=etancheite&par_page=50", headers=a["headers"]).json()
    names = {p["name"] for p in v["profils"]}
    assert "FICTIVE DEMO" not in names and "COMPTE DEMO" not in names
    assert client.get(f"/api/reseau/annuaire/{fake_pid}", headers=a["headers"]).status_code == 404
    pid = _project(client, a, allotissement="Lot 1 : Couverture ; Lot 2 : Étanchéité")
    m = client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).text
    assert "FICTIVE DEMO" not in m and "COMPTE DEMO" not in m
    # Le cron ignore aussi les profils démo.
    db = _db()
    try:
        db.query(PartnerProfile).filter(PartnerProfile.name.in_(["FICTIVE DEMO", "COMPTE DEMO"])).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_isolation_entre_entreprises(client, reg, mails):
    b = _org(client, "Isolée B", extra={"phone": "0298765432", "email": "compta@isolee-b.fr",
                                         "ca_n1": 1234567, "effectif": 37})
    b_pid = _publish(client, reg, b)
    a = _org(client, "Isolée A")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    c = _org(client, "Curieuse C")
    assert client.get(f"/api/projects/{pid}/partner-matches", headers=c["headers"]).status_code == 404
    assert client.post(f"/api/projects/{pid}/reseau/invitations", headers=c["headers"],
                       json={"profile_id": b_pid}).status_code == 404
    assert client.post(f"/api/projects/{pid}/reseau/invitations-sirene", headers=c["headers"],
                       json={"siret": b["siren"] + "00012"}).status_code == 404
    # Fiche et annuaire : jamais email, téléphone, CA, effectif exact.
    for txt in (client.get(f"/api/reseau/annuaire/{b_pid}", headers=a["headers"]).text,
                client.get("/api/reseau/annuaire?metier=electricite&par_page=50", headers=a["headers"]).text,
                client.get(f"/api/projects/{pid}/partner-matches", headers=a["headers"]).text):
        for secret in ("0298765432", "compta@isolee-b.fr", "1234567", b["email"], '"effectif"', '"ca_n1"'):
            assert secret not in txt, secret
    # Le profil d'une autre entreprise n'est ni lisible ni modifiable par une autre org.
    v = client.get("/api/reseau/profil", headers=a["headers"]).json()
    assert v["profile_id"] != b_pid
    client.put("/api/reseau/profil", headers=a["headers"], json={"presentation": "Couvreur."})
    assert _profile_row(b["id"]).presentation == "Électricité générale."


# ── 10. Boucle de croissance : suggestion d'interface, jamais d'email ────────────────
def test_suggest_profile_apres_inscription_et_claim(client, reg, mails):
    org = _org(client, "Nouvelle Inscrite")
    assert org["register"]["suggest_profile"]["code"] == "publier_profil_reseau"
    a = _org(client, "Chef Suggestion")
    pid = _project(client, a)
    inv = client.post(f"/api/projects/{pid}/invites", headers=a["headers"],
                      json={"recipient": org["email"], "company_name": "Nouvelle Inscrite"}).json()
    n_before = len(mails)
    r = client.post(f"/api/invite/{inv['token']}/claim", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["suggest_profile"]["code"] == "publier_profil_reseau"
    assert len(mails) == n_before                         # aucune sollicitation par email
    # Login : réponse inchangée (pas de champ ajouté).
    r = client.post("/api/auth/login", json={"email": org["email"], "password": "motdepasse123"})
    assert r.status_code == 200 and set(r.json()) == {"access_token", "token_type"}


# ── 11. Migration p0q1r2s3t4u5 (SQLite) ──────────────────────────────────────────────
def test_migration_partner_profiles_a_neuf_precedente_et_rejouee(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "mig_v3.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    alembic = [sys.executable, "-m", "alembic"]

    def run(*args):
        r = subprocess.run(alembic + list(args), cwd=root, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        return r

    import sqlalchemy as sa
    expected = {"public_id", "user_id", "visible", "name", "siren", "siret", "postal_code", "city", "departement",
                "metiers", "codes_cpv", "departements", "roles_acceptes", "disponibilite", "dispo_jusqua",
                "lot_max_eur", "presentation", "references_publiques", "declared_at", "hidden_from_sirens",
                "verified_sirene", "verified_bodacc", "verified_decp", "verified_at", "groupements_deposes",
                "last_groupement_at", "appearances_count", "appearances_period", "published_at", "is_demo",
                "created_at", "updated_at"}

    def check(eng):
        insp = sa.inspect(eng)
        assert "partner_profiles" in insp.get_table_names()
        assert expected <= {c["name"] for c in insp.get_columns("partner_profiles")}
        uq = {tuple(u["column_names"]) for u in insp.get_unique_constraints("partner_profiles")}
        uq |= {tuple(i["column_names"]) for i in insp.get_indexes("partner_profiles") if i.get("unique")}
        assert ("user_id",) in uq and ("public_id",) in uq
        assert "ix_partner_profiles_siren" in {i["name"] for i in insp.get_indexes("partner_profiles")}
        assert {"source", "partner_profile_id"} <= {c["name"] for c in insp.get_columns("project_invites")}
        with eng.connect() as cn:
            assert cn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "p0q1r2s3t4u5"
            assert cn.execute(sa.text("SELECT COUNT(*) FROM partner_profiles")).scalar() == 0   # aucun profil créé

    run("upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    check(eng)
    # Cas production : base à la révision précédente, SANS la table → créée par la révision.
    with eng.begin() as cn:
        cn.execute(sa.text("DROP TABLE partner_profiles"))
    run("stamp", "o9p0q1r2s3t4")
    run("upgrade", "head")
    check(eng)
    # Opt-in par défaut côté base : une ligne insérée sans « visible » n'est pas publiée.
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO partner_profiles (public_id, user_id) VALUES ('x', 999999)"))
        assert cn.execute(sa.text("SELECT visible, is_demo FROM partner_profiles WHERE public_id='x'")).one() == (0, 0)
        cn.execute(sa.text("DELETE FROM partner_profiles"))
    # Rejouée : aucun effet, aucune erreur.
    run("stamp", "o9p0q1r2s3t4")
    run("upgrade", "head")
    check(eng)
    eng.dispose()
