"""Demande d'accès (remplace la démo publique) + fermeture de la démo sans mot de passe.

  • /demande-acces sert la page ; la demande part à contact@adjugo.pro avec « Répondre à »
    = l'adresse du demandeur, et AUCUN email n'est envoyé à l'adresse saisie ;
  • robots (champ piège), champs invalides, injection d'en-tête dans l'objet, échec d'envoi ;
  • démo fermée par défaut : connexion démo 404, sessions démo déjà ouvertes refusées ;
  • plus aucun lien « démo » sur les pages publiques.
"""
import pathlib

import pytest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"

BON = {"prenom": "Camille", "nom": "Martin", "email": "Camille@Exemple.fr",
       "organisation": "Martin Couverture", "telephone": "06 12 34 56 78",
       "profil": "entreprise", "message": "Couvreur dans le Finistère.\nMarchés de toitures."}


@pytest.fixture
def mails(monkeypatch):
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email",
                        lambda to, subj, text, html=None, reply_to=None: sent.append(
                            {"to": to, "subj": subj, "text": text, "reply_to": reply_to}) or True)
    return sent


def test_page_servie(client):
    r = client.get("/demande-acces")
    assert r.status_code == 200
    assert 'id="f"' in r.text and "Réserver ma démonstration" in r.text


def test_demande_part_a_contact_avec_repondre_a(client, mails):
    r = client.post("/api/contact/demande-acces", json=BON)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(mails) == 1
    m = mails[0]
    assert m["to"] == "contact@adjugo.pro"
    assert m["reply_to"] == "camille@exemple.fr"
    assert "Martin Couverture" in m["subj"] and "Entreprise" in m["subj"]
    assert "06 12 34 56 78" in m["text"] and "Marchés de toitures." in m["text"]
    # Jamais d'email vers l'adresse saisie (le formulaire anonyme n'est pas un canal d'envoi).
    assert not [x for x in mails if x["to"] == "camille@exemple.fr"]


def test_adresse_de_contact_configurable(client, mails, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "ventes@adjugo.pro")
    assert client.post("/api/contact/demande-acces", json=BON).status_code == 200
    assert mails[0]["to"] == "ventes@adjugo.pro"


def test_robot_ignore(client, mails):
    r = client.post("/api/contact/demande-acces", json={**BON, "site_web": "http://spam.example"})
    assert r.status_code == 200 and mails == []


@pytest.mark.parametrize("champ,valeur", [
    ("email", "pas-une-adresse"), ("prenom", "   "), ("organisation", ""),
    ("telephone", "appelez-moi"), ("profil", "pirate"), ("message", "x" * 2001)])
def test_champs_invalides(client, mails, champ, valeur):
    r = client.post("/api/contact/demande-acces", json={**BON, champ: valeur})
    assert r.status_code == 422 and mails == []


def test_pas_d_injection_dans_l_objet(client, mails):
    r = client.post("/api/contact/demande-acces",
                    json={**BON, "organisation": "Société X\r\nBcc: victime@exemple.fr"})
    assert r.status_code == 200
    assert "\n" not in mails[0]["subj"] and "\r" not in mails[0]["subj"]


def test_echec_d_envoi_signale(client, monkeypatch):
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda *a, **k: False)
    r = client.post("/api/contact/demande-acces", json=BON)
    assert r.status_code == 503 and "contact@adjugo.pro" in r.json()["detail"]


def test_lien_de_rendez_vous_https_uniquement(client, monkeypatch):
    monkeypatch.delenv("BOOKING_URL", raising=False)
    assert client.get("/api/contact/config").json()["booking_url"] == \
        "https://cal.com/eliot-viegas-adjugo/reservez-ma-demo-adjugo"
    monkeypatch.setenv("BOOKING_URL", "off")
    assert client.get("/api/contact/config").json()["booking_url"] is None
    monkeypatch.setenv("BOOKING_URL", "https://cal.example/adjugo")
    assert client.get("/api/contact/config").json()["booking_url"] == "https://cal.example/adjugo"
    for bad in ("http://cal.example/x", "javascript:alert(1)"):
        monkeypatch.setenv("BOOKING_URL", bad)
        assert client.get("/api/contact/config").json()["booking_url"] is None


# ── Démo publique fermée ──────────────────────────────────────────────────────────────
def test_demo_fermee_par_defaut(client, monkeypatch):
    # Sessions ouvertes pendant que la démo était encore publique…
    pme = client.post("/api/auth/demo")
    ach = client.post("/api/acheteur/demo")
    assert pme.status_code == 200 and ach.status_code == 200
    h_pme = {"Authorization": f"Bearer {pme.json()['access_token']}"}
    h_ach = {"Authorization": f"Bearer {ach.json()['access_token']}"}
    # … puis fermeture (comportement par défaut en production : variable absente).
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    assert client.post("/api/auth/demo").status_code == 404
    assert client.post("/api/acheteur/demo").status_code == 404
    assert client.get("/api/auth/me", headers=h_pme).status_code == 401
    assert client.get("/api/acheteur/me", headers=h_ach).status_code == 401


def test_demo_reactivable(client, monkeypatch):
    monkeypatch.setenv("DEMO_PUBLIC", "1")
    assert client.post("/api/auth/demo").status_code == 200


def test_plus_aucun_lien_demo_sur_les_pages_publiques():
    for name in ("landing.html", "acheteur-landing.html", "app.html", "app.js", "acheteur.html"):
        s = (STATIC / name).read_text(encoding="utf-8")
        assert "demo=1" not in s and "/api/auth/demo" not in s and "/api/acheteur/demo" not in s, name
    landing = (STATIC / "landing.html").read_text(encoding="utf-8")
    assert landing.count('href="/demande-acces"') >= 3
