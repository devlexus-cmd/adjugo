"""Non-régression — audit cybersécurité oct. 2026, groupe « auth ».

Chaque test REJOUE l'exploit d'origine et vérifie qu'il échoue désormais :
  - faille 3  : le lien de confirmation d'email valait session complète (3 jours) ;
  - faille 17 : rejouer l'ancien lien après changement d'adresse « prouvait » la nouvelle ;
  - faille 15 : l'invitation d'équipe comparait l'email en tenant compte de la casse ;
  - faille 8  : un membre retiré relisait les résultats IA (jobs) de l'organisation.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import pytest

from app.core.database import SessionLocal
from app.core.security import create_access_token, decode_token
from app.models import User, Job


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _email(prefix="secu"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"


@pytest.fixture
def sent_links(monkeypatch):
    """Capture les liens de confirmation « envoyés » (aucun envoi réel)."""
    import app.routers.auth as A
    links = []

    def fake_send(to, subject, body, html=None, **kw):
        for line in body.splitlines():
            if "verify=" in line:
                links.append((to, parse_qs(urlparse(line.strip()).query)["verify"][0]))
        return True

    monkeypatch.setattr(A, "send_email", fake_send)
    return links


def _register(client, email=None, password="motdepasse123"):
    email = email or _email()
    r = client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": "Secu Test", "company_name": "Secu SARL"})
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def _set_verified(email):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        return u.id
    finally:
        db.close()


# ─── Faille 3 : le lien de confirmation n'est PAS une session ────────────────────────

def test_lien_de_verification_refuse_comme_session(client, sent_links):
    email, session = _register(client)
    assert sent_links, "le lien de confirmation doit être généré à l'inscription"
    to, verify_tok = sent_links[-1]
    assert to == email

    # EXPLOIT d'origine : utiliser le jeton du mail comme Bearer → accès complet au compte.
    for method, path in (("GET", "/api/auth/me"), ("GET", "/api/org/"), ("GET", "/api/knowledge/")):
        r = client.request(method, path, headers=_h(verify_tok))
        assert r.status_code == 401, f"{path} accepte le lien de confirmation comme session"
    r = client.put("/api/org/", json={"name": "Piratée"}, headers=_h(verify_tok))
    assert r.status_code == 401
    # Aucune fuite technique dans le message.
    assert "purpose" not in r.text and "tv" not in r.json().get("detail", "")

    # Durée du lien ramenée à 48 h (et plus 3 jours).
    p = decode_token(verify_tok)
    exp = datetime.fromtimestamp(p["exp"], tz=timezone.utc)
    assert exp - datetime.now(timezone.utc) <= timedelta(hours=48, minutes=1)

    # Usage légitime intact : le lien confirme toujours l'adresse, la session reste valide.
    r = client.post("/api/auth/verify-email", json={"token": verify_tok})
    assert r.status_code == 200, r.text
    me = client.get("/api/auth/me", headers=_h(session))
    assert me.status_code == 200 and me.json()["email_verified"] is True


def test_seuls_les_jetons_de_session_ouvrent_une_session(client):
    email, session = _register(client)
    uid = decode_token(session)["sub"]
    # Jeton à finalité, même forgé AVEC une version de session → refusé.
    forged = create_access_token({"sub": uid, "tv": 0, "purpose": "verify_email", "email": email})
    assert client.get("/api/auth/me", headers=_h(forged)).status_code == 401
    # State OAuth (porte `purpose`) → refusé.
    state = create_access_token({"purpose": "google_oauth", "nonce": "x", "sub": uid})
    assert client.get("/api/auth/me", headers=_h(state)).status_code == 401
    # Jeton sans version de session (aucun émetteur de session n'en produit) → refusé.
    bare = create_access_token({"sub": uid})
    assert client.get("/api/auth/me", headers=_h(bare)).status_code == 401
    # Un jeton à finalité ne passe pas non plus l'espace acheteur.
    ach = create_access_token({"sub": "1", "typ": "acheteur", "tv": 0, "purpose": "verify_email"})
    assert client.get("/api/acheteur/me", headers=_h(ach)).status_code == 401
    # La vraie session fonctionne.
    assert client.get("/api/auth/me", headers=_h(session)).status_code == 200


def test_emetteurs_de_session_toujours_acceptes(client):
    """Les parcours légitimes qui émettent une session restent fonctionnels."""
    email, tok = _register(client)
    # login
    r = client.post("/api/auth/login", json={"email": email.upper(), "password": "motdepasse123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_h(r.json()["access_token"])).status_code == 200
    # demo
    r = client.post("/api/auth/demo")
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_h(r.json()["access_token"])).status_code == 200
    # changement de mot de passe → jeton frais valide
    r = client.post("/api/auth/change-password", headers=_h(tok),
                    json={"current_password": "motdepasse123", "new_password": "nouveaumdp456"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_h(r.json()["access_token"])).status_code == 200


# ─── Faille 17 : ancien lien rejoué après changement d'adresse ───────────────────────

def test_ancien_lien_ne_prouve_pas_la_nouvelle_adresse(client, sent_links):
    email_a, session = _register(client)
    _, link_a = sent_links[-1]
    # 1. L'utilisateur confirme son adresse initiale.
    assert client.post("/api/auth/verify-email", json={"token": link_a}).status_code == 200

    # 2. Il la remplace par une adresse qu'il ne possède pas (mot de passe courant exigé).
    email_b = _email("autre")
    r = client.put("/api/auth/me", json={"email": email_b, "current_password": "motdepasse123"},
                   headers=_h(session))
    assert r.status_code == 200, r.text
    assert r.json()["email_verified"] is False
    _, link_b = sent_links[-1]

    # 3. EXPLOIT d'origine : rejouer le lien de l'ancienne adresse.
    r = client.post("/api/auth/verify-email", json={"token": link_a})
    assert r.status_code == 400
    assert "ancienne adresse" in r.json()["detail"]
    assert "nouveau lien" in r.json()["detail"]
    me = client.get("/api/auth/me", headers=_h(session)).json()
    assert me["email"] == email_b and me["email_verified"] is False

    # Le lien réellement envoyé à la nouvelle adresse fonctionne.
    assert client.post("/api/auth/verify-email", json={"token": link_b}).status_code == 200
    assert client.get("/api/auth/me", headers=_h(session)).json()["email_verified"] is True


def test_lien_sans_adresse_refuse(client):
    """Un lien à l'ancien format (sans adresse liée) ne peut plus rien prouver."""
    email, session = _register(client)
    uid = decode_token(session)["sub"]
    legacy = create_access_token({"sub": uid, "purpose": "verify_email"},
                                 expires_delta=timedelta(hours=1))
    r = client.post("/api/auth/verify-email", json={"token": legacy})
    assert r.status_code == 400
    assert "nouveau lien" in r.json()["detail"]
    assert client.get("/api/auth/me", headers=_h(session)).json()["email_verified"] is False


def test_update_me_email_normalise_et_valide(client):
    email, session = _register(client)
    r = client.put("/api/auth/me", json={"email": "pas-une-adresse", "current_password": "motdepasse123"},
                   headers=_h(session))
    assert r.status_code == 400 and "invalide" in r.json()["detail"].lower()
    autre, _ = _register(client)
    r = client.put("/api/auth/me", json={"email": autre.upper(), "current_password": "motdepasse123"},
                   headers=_h(session))
    assert r.status_code == 400  # doublon insensible à la casse
    nouv = _email("Mixte").replace("mixte", "MiXte")
    r = client.put("/api/auth/me", json={"email": nouv, "current_password": "motdepasse123"},
                   headers=_h(session))
    assert r.status_code == 200 and r.json()["email"] == nouv.lower()


def test_changement_email_exige_le_mot_de_passe(client):
    """EXPLOIT : une session volée (token seul, sans mot de passe) détournait l'adresse, puis
    prenait le compte DÉFINITIVEMENT via « mot de passe oublié ». Le changement d'adresse exige
    désormais le mot de passe courant — un token volé ne suffit plus."""
    email, session = _register(client)
    cible = _email("pirate")
    # Sans mot de passe → refusé.
    assert client.put("/api/auth/me", json={"email": cible}, headers=_h(session)).status_code == 403
    # Mauvais mot de passe → refusé.
    r = client.put("/api/auth/me", json={"email": cible, "current_password": "faux"}, headers=_h(session))
    assert r.status_code == 403
    # L'adresse n'a pas bougé.
    assert client.get("/api/auth/me", headers=_h(session)).json()["email"] == email
    # Avec le bon mot de passe → accepté (parcours légitime préservé).
    r = client.put("/api/auth/me", json={"email": cible, "current_password": "motdepasse123"},
                   headers=_h(session))
    assert r.status_code == 200 and r.json()["email"] == cible.lower()


def test_update_me_ignore_les_parametres_d_url(client):
    """L'adresse ne doit JAMAIS transiter par la query string (logs d'accès, historique,
    en-tête Referer) : passée en paramètre d'URL, elle n'a AUCUN effet (le corps JSON fait foi)."""
    email, session = _register(client)
    r = client.put("/api/auth/me", params={"email": _email("url"), "current_password": "motdepasse123"},
                   json={}, headers=_h(session))
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_h(session)).json()["email"] == email


# ─── Faille 15 : invitation d'équipe insensible à la casse ───────────────────────────

def test_invitation_insensible_a_la_casse(client):
    target, _ = _register(client)          # compte existant « target@… » (minuscules)
    owner, owner_tok = _register(client)

    # EXPLOIT d'origine : inviter la même adresse en MAJUSCULES créait un 2e compte.
    r = client.post("/api/org/invite", headers=_h(owner_tok),
                    json={"email": target.upper(), "full_name": "Doublon"})
    assert r.status_code == 400, r.text
    db = SessionLocal()
    try:
        from sqlalchemy import func
        assert db.query(User).filter(func.lower(User.email) == target.lower()).count() == 1
    finally:
        db.close()

    # Une nouvelle adresse en casse mixte est stockée normalisée → connexion prévisible.
    mixed = f"Nouveau.Membre_{uuid.uuid4().hex[:6]}@Exemple.FR"
    r = client.post("/api/org/invite", headers=_h(owner_tok), json={"email": mixed})
    assert r.status_code == 201, r.text
    assert r.json()["email"] == mixed.lower()
    tmp = r.json()["temp_password"]
    assert client.post("/api/auth/login", json={"email": mixed, "password": tmp}).status_code == 200
    # Ré-inviter la même personne (autre casse) → « déjà dans l'organisation ».
    r = client.post("/api/org/invite", headers=_h(owner_tok), json={"email": mixed.upper()})
    assert r.status_code == 400 and "déjà" in r.json()["detail"]


# ─── Faille 8 : un ex-membre ne relit plus les résultats IA de l'organisation ─────────

def _wait_job(client, jid, headers):
    r = None
    for _ in range(60):
        r = client.get(f"/api/jobs/{jid}", headers=headers)
        if r.status_code != 200 or r.json()["status"] in ("done", "error"):
            return r
        time.sleep(0.1)
    return r


def test_ex_membre_ne_lit_plus_les_jobs(client, monkeypatch):
    import app.routers.knowledge as K

    def fake_answer_questions(db, user_id, questions, kb_user_ids=None):
        return {"answers": [{"question": q, "answer": "SAVOIR-FAIRE-ORG-A"} for q in questions]}
    monkeypatch.setattr(K, "answer_questions", fake_answer_questions)

    owner_email, owner_tok = _register(client)
    _set_verified(owner_email)
    db = SessionLocal()
    try:   # offre Pro : l'équipe de 3 dépasse la limite Starter (2 membres)
        from app.models import PlanType
        from app.models import KnowledgeDoc, KnowledgeChunk
        o = db.query(User).filter(User.email == owner_email).first()
        o.plan = PlanType.pro
        # Savoir-faire COMMUN de l'org (déposé par le propriétaire).
        d = KnowledgeDoc(user_id=o.id, name="methodo.pdf", kind="methodologie",
                         text="x" * 200, char_count=200, n_chunks=1)
        db.add(d)
        db.flush()
        db.add(KnowledgeChunk(doc_id=d.id, user_id=o.id, ordinal=0,
                              text="Procédé secret de l'entreprise A", doc_name="methodo.pdf"))
        db.commit()
    finally:
        db.close()
    # Membre actuel A2 (celui qui partira) et membre actuel A3 (qui reste).
    r = client.post("/api/org/invite", headers=_h(owner_tok), json={"email": _email("a2")})
    assert r.status_code == 201, r.text
    a2_id, a2_email, a2_pwd = r.json()["id"], r.json()["email"], r.json()["temp_password"]
    _set_verified(a2_email)
    a2 = _h(client.post("/api/auth/login", json={"email": a2_email, "password": a2_pwd}).json()["access_token"])
    r = client.post("/api/org/invite", headers=_h(owner_tok), json={"email": _email("a3")})
    assert r.status_code == 201, r.text
    a3_email, a3_pwd = r.json()["email"], r.json()["temp_password"]
    a3 = _h(client.post("/api/auth/login", json={"email": a3_email, "password": a3_pwd}).json()["access_token"])
    stranger_email, stranger_tok = _register(client)

    # A2 lance une génération (parcours réel, seul le LLM est simulé).
    r = client.post("/api/knowledge/questionnaire", headers=a2,
                    json={"questions": ["Votre méthodologie ?"]})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    r = _wait_job(client, jid, a2)
    assert r.status_code == 200 and r.json()["status"] == "done", r.text

    # Membres ACTUELS de l'org : propriétaire et collègue voient le résultat de l'équipe.
    assert client.get(f"/api/jobs/{jid}", headers=_h(owner_tok)).status_code == 200
    assert client.get(f"/api/jobs/{jid}", headers=a3).status_code == 200
    # Une autre organisation : rien.
    assert client.get(f"/api/jobs/{jid}", headers=_h(stranger_tok)).status_code == 404

    # Le propriétaire retire A2.
    r = client.delete(f"/api/org/members/{a2_id}", headers=_h(owner_tok))
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        owner_id = db.query(User).filter(User.email == owner_email).first().id
        assert db.get(Job, jid).user_id == owner_id, "le job doit rester à l'organisation"
    finally:
        db.close()

    # EXPLOIT d'origine : A2 se reconnecte (compte intact) et relit le job.
    a2n = _h(client.post("/api/auth/login", json={"email": a2_email, "password": a2_pwd}).json()["access_token"])
    r = client.get(f"/api/jobs/{jid}", headers=a2n)
    assert r.status_code == 404
    assert "SAVOIR-FAIRE-ORG-A" not in r.text
    assert "Job" not in r.json()["detail"]   # message sans jargon

    # Défense en profondeur : même un job resté au nom de l'ex-membre (données d'avant le
    # correctif) n'est plus lisible par lui… mais reste lisible par l'org s'il est réassigné.
    db = SessionLocal()
    try:
        legacy = Job(user_id=owner_id, kind="memoire", status="done", label="ancien",
                     result={"secret": "SAVOIR-FAIRE-ORG-A"})
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
    finally:
        db.close()
    assert client.get(f"/api/jobs/{legacy_id}", headers=a2n).status_code == 404
    assert client.get(f"/api/jobs/{legacy_id}", headers=a3).status_code == 200
    # Le propriétaire et le collègue restant voient toujours le résultat de l'équipe.
    assert client.get(f"/api/jobs/{jid}", headers=_h(owner_tok)).status_code == 200
    assert client.get(f"/api/jobs/{jid}", headers=a3).status_code == 200
