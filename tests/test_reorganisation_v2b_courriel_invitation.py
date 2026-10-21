"""
Réorganisation de l'interface — vague 2b, chantier B4 : le courriel d'invitation (contrat : docs/REORGANISATION_V2B.md,
§ B4 ; étude, § 6 « Le partenaire reçoit l'invitation », § 7.6 et § 7.7).

Les courriels d'invitation à un groupement — partenaire connu, membre du réseau Adjugo, leurs relances (renvoi par le
chef de file, rappel planifié à J-3 / J-1) — partent en HTML avec leur version texte. Ils nomment le chef de file, le
marché, la date limite, ce qui est attendu et ce que verra le partenaire (sa part, jamais le détail des prix des
autres), et mènent à « Votre part dans [marché] » par le lien de l'invitation, inchangé.

Aucun envoi réel : `send_email` est remplacé par un relevé (les courriels sont de toute façon coupés en test,
tests/conftest.py) ; registres simulés (tests/test_reseau_partenaires.py) ; aucune IA.
"""
import ast
import html as _html
import pathlib
import re
import uuid
from datetime import date, datetime, timedelta

import pytest

from tests.test_convention_groupement import _db, _invite, _project, _set_company
from tests.test_reseau_partenaires import _org, _publish, reg  # noqa: F401  (registres simulés, fixture autouse)
from tests.test_reseau_partenaires import _project as _projet_reseau
from tests.textes_visibles import _CLE, _docstrings, mots_bannis

ROOT = pathlib.Path(__file__).resolve().parent.parent
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")


@pytest.fixture
def courriels(monkeypatch):
    """Relevé des courriels : (destinataire, objet, texte, html). Rien ne part."""
    envoyes = []

    def _envoi(to, subject, text, html=None, **k):
        envoyes.append({"to": to, "objet": subject, "texte": text, "html": html})
        return True
    import app.services.alerts as al
    import app.services.email as em
    monkeypatch.setattr(em, "send_email", _envoi)
    monkeypatch.setattr(al, "send_email", _envoi)
    return envoyes


def _base() -> str:
    """Adresse des liens des courriels : APP_BASE_URL (comme en production), sinon celle de la requête."""
    from app.core.config import get_settings
    return (get_settings().APP_BASE_URL or "http://testserver").rstrip("/")


def _visible(h: str) -> str:
    """Texte lu dans le HTML d'un courriel (balises, styles et pré-en-tête compris : tout ce qu'un client affiche)."""
    return _html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style\b.*?</style>", " ", h, flags=re.S)))


def _urls(h: str) -> set:
    return set(re.findall(r"https?://[^\s\"'<>]+", _html.unescape(h)))


def _assert_courriel_propre(c: dict, url: str, interdits=(), saisies=()):
    """Les règles communes : HTML et texte, un seul lien (celui de l'invitation), aucune image ni pixel, aucune
    adresse email, aucun mot banni, aucun émoji, jamais « à le / de le chef de file ». `saisies` : données saisies
    par un client (nom d'un marché de test…), retirées avant la recherche des mots bannis (ce ne sont pas nos mots)."""
    t, h = c["texte"], c["html"]
    assert t and h and h.lstrip().startswith("<!DOCTYPE html>") and '<html lang="fr">' in h
    assert "\n" not in c["objet"] and "\r" not in c["objet"]
    assert "<img" not in h.lower() and "background-image" not in h.lower() and "url(" not in h.lower()
    assert _urls(h) == {url} and _urls(t) == {url}
    assert url in t and f'href="{_html.escape(url, quote=True)}"' in h
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t + _visible(h)), "aucune adresse email dans le courriel"
    for x in (c["objet"], t, _visible(h)):
        for d in saisies:
            x = x.replace(d, " ").replace(d[:50], " ")
        assert not mots_bannis(x), (mots_bannis(x), x[:200])
        assert not EMOJI.search(x)
        assert "à le chef" not in x and "de le chef" not in x and "vérifié" not in x.lower()
    for x in interdits:
        assert x not in t and x not in h and x not in c["objet"], x


# ═══ 1. Partenaire connu : l'invitation, de bout en bout ═════════════════════════════════════════════════════════

def test_invitation_d_un_partenaire_connu_en_html_et_en_texte(client, auth, courriels):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    nom = f"Réfection de la toiture du groupe scolaire Jean-Jaurès {uuid.uuid4().hex[:4]}"
    pid = _project(client, h, name=nom, deadline_days=20)
    inv = _invite(client, h, pid, "Breizh Désamiantage", recipient="contact@desamiantage.example")
    assert inv["emailed"] is True
    (c,) = [x for x in courriels if x["to"] == "contact@desamiantage.example"]
    url = _base() + "/invite/" + inv["token"]
    echeance = (date.today() + timedelta(days=20)).strftime("%d/%m/%Y")
    # L'objet d'avant (vague 1) : sans « co-traitant ».
    assert c["objet"] == f"Invitation à répondre ensemble à un marché — {nom[:60]}"
    t, v = c["texte"], _visible(c["html"])
    for x in (t, v):
        assert "Breizh Couverture vous invite à rejoindre son groupement pour répondre ensemble au marché" in x
        assert nom in x and echeance in x and "Breizh Désamiantage" in x            # chef, marché, date, invitée
        assert "Partenaire du groupement" in x
        assert "Ce qui est attendu de vous" in x and "Renseigner votre part" in x and "La soumettre à Breizh Couverture" in x
        assert "Ce que vous verrez" in x and "Jamais le détail des prix des autres entreprises." in x
        # Relecture de la vague 2b : le tableau de prix déposé part au chef de file (ses prix de vente, ligne par ligne) ;
        # seul le chiffrage détaillé (coûts, marges, méthode) reste chez le partenaire. Avant : « pas son détail », faux.
        assert ("Votre chiffrage détaillé (coûts, marges, méthode) reste chez vous : Breizh Couverture reçoit le prix "
                "de vente de votre partie et, si vous le déposez, votre tableau de prix de vente.") in x
        assert "pas son détail" not in x
        assert f"Votre part dans « {nom} »" in x
        assert "déclinez l'invitation" in x
    assert "Ouvrir votre part" in c["html"]
    # Ni l'acheteur (ce que voit le partenaire, il le lit dans sa part), ni l'adresse du chef de file.
    _assert_courriel_propre(c, url, interdits=("Ville de Lorient", auth["email"], "contact@desamiantage.example"))
    # Le lien du courriel ouvre toujours l'espace du partenaire (les liens déjà envoyés aussi : même chemin).
    assert client.get("/invite/" + inv["token"]).status_code == 200
    assert client.get("/api/invite/" + inv["token"]).json()["project"]["name"] == nom


def test_echappement_de_toute_donnee_saisie(client, auth, courriels):
    h = auth["headers"]
    _set_company(auth["email"], name='Toit <img src=x onerror="alert(1)"> & Fils')
    nom = 'Marché <script>alert("x")</script> & co\r\nBcc: victime@tiers.example'
    pid = _project(client, h, name=nom)
    inv = _invite(client, h, pid, "<b>Entreprise</b> invitée", recipient="p@partenaire.example")
    (c,) = [x for x in courriels if x["to"] == "p@partenaire.example"]
    hh = c["html"]
    assert "<script" not in hh and "<img" not in hh and "<b>Entreprise" not in hh and 'onerror="' not in hh
    assert "&lt;script&gt;" in hh and "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in hh and "&amp; Fils" in hh
    assert "&lt;b&gt;Entreprise&lt;/b&gt; invitée" in hh
    # Aucun retour à la ligne dans l'objet (pas d'en-tête glissé), ni dans le texte d'un nom saisi.
    assert "\r" not in c["objet"] and "\n" not in c["objet"] and "Bcc:" in c["objet"]
    assert "co Bcc: victime" in c["texte"] and "\r" not in c["texte"]
    assert _base() + "/invite/" + inv["token"] in c["texte"]


def test_sans_nom_d_entreprise_ni_date_limite_rien_n_est_invente():
    from app.services.email_invitation import invitation
    c = invitation(chef="", marche="Toiture", url="https://adjugo.pro/invite/t", date_limite=None)
    t = c["texte"]
    assert t.startswith("Bonjour,\n\nUne entreprise vous invite à rejoindre son groupement")
    assert "Chef de file :" not in t and "Date limite : pas encore indiquée sur ce marché" in t
    # Relecture de la vague 2b : « le prix de vente de votre partie et, si vous le déposez, votre tableau de prix ».
    assert "La soumettre au chef de file" in t and "le chef de file reçoit le prix de vente de votre partie" in t
    _assert_courriel_propre(c, "https://adjugo.pro/invite/t")


def test_ce_qui_est_attendu_suit_le_role_et_les_droits_du_lien():
    from app.services.email_invitation import invitation
    u = "https://adjugo.pro/invite/t"
    st = invitation(chef="A SARL", marche="M", url=u, role="sous_traitant", partie="Lot 3 — Plomberie")
    assert "A SARL vous invite à intervenir comme sous-traitant sur le marché « M »." in st["texte"]
    assert "Votre rôle : Sous-traitant" in st["texte"] and "Partie proposée : Lot 3 — Plomberie" in st["texte"]
    assert "Comme sous-traitant, vous ne signez pas la convention de groupement." in st["texte"]
    lecture = invitation(chef="A SARL", marche="M", url=u, peut_contribuer=False, voit_pieces=False)
    assert "Ce lien est en lecture seule : aucune part à renseigner." in lecture["texte"]
    assert "Renseigner votre part" not in lecture["texte"] and "Votre part dans" not in lecture["texte"]
    assert "Le résumé du marché." in lecture["texte"] and "pièces" not in lecture["texte"]
    assert "Ouvrir le dossier partagé" in lecture["html"]
    sans_pieces = invitation(chef="A SARL", marche="M", url=u, voit_pieces=False)
    assert "Le résumé du marché et votre part." in sans_pieces["texte"]
    avec = invitation(chef="A SARL", marche="M", url=u, expire_le=datetime(2026, 11, 20, 9, 0))
    assert "Ce lien est réservé à votre entreprise et valable jusqu'au 20/11/2026." in avec["texte"]
    for c in (st, lecture, sans_pieces, avec):
        _assert_courriel_propre(c, u)


def test_la_version_texte_dit_ce_que_dit_le_html():
    """Mêmes faits dans les deux versions : chaque ligne du texte (hors lien) se lit dans le HTML."""
    from app.services.email_invitation import invitation, rappel_part
    u = "https://adjugo.pro/invite/t"
    cas = [invitation(chef="A SARL", marche="M & N", url=u, date_limite=date(2026, 11, 6), entreprise="B"),
           invitation(chef="A SARL", marche="M", url=u, reseau=True, partie="Lot 2", relance=True),
           invitation(chef="", marche="M", url=u, peut_contribuer=False),
           rappel_part(chef="A SARL", marche="M", url=u, date_limite=date(2026, 11, 6), jours_restants=3,
                       attestations=["Kbis à fournir"], parties=["« Démarche » (date limite interne : 01/11/2026)"])]
    for c in cas:
        v = " ".join(_visible(c["html"]).split())
        for ligne in c["texte"].split("\n"):
            ligne = ligne.strip().lstrip("- ").rstrip(" :")
            if not ligne or ligne == u or ligne.startswith("— Adjugo"):
                continue
            if ":" in ligne and not ligne.startswith(("Ce ", "Votre part", "Vos ", "Il ", "Le ")):
                lib, _, val = ligne.partition(" : ")      # « Libellé : valeur » : libellé et valeur, l'un sous l'autre
                assert lib in v and val in v, ligne
            else:
                assert ligne in v, ligne


# ═══ 2. Membre du réseau Adjugo : adresse jamais révélée, aperçu avant acceptation ════════════════════════════════

def test_invitation_d_un_membre_du_reseau(client, reg, courriels):  # noqa: F811
    b = _org(client, "Partenaire Masqué")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef De File Réseau")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _projet_reseau(client, a)
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b_pid, "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    (c,) = [x for x in courriels if x["to"] == b["email"]]
    # Le jeton n'est jamais remis au chef de file : on le relit dans la base pour le lien attendu.
    from app.models import ProjectInvite
    db = _db()
    try:
        token = db.get(ProjectInvite, r.json()["invitation"]["id"]).token
    finally:
        db.close()
    url = _base() + "/invite/" + token
    assert c["objet"] == "Une entreprise vous propose un groupement — Rénovation de l'école Jules-Ferry"
    t, v = c["texte"], _visible(c["html"])
    for x in (t, v):
        assert "Chef De File Réseau a trouvé votre profil sur le réseau Adjugo et vous propose de rejoindre son groupement" in x
        assert "Rénovation de l'école Jules-Ferry" in x and "Lot 2 — Électricité" in x
        assert (date.today() + timedelta(days=30)).strftime("%d/%m/%Y") in x
        assert "Accepter ou décliner l'invitation" in x and "Avant votre réponse : un aperçu du marché." in x
        assert "Jamais le détail des prix des autres entreprises." in x
        assert "Votre adresse n'est pas communiquée au chef de file tant que vous n'avez pas accepté." in x
        assert "retirer cette publication" in x and "Partenaires › Réseau Adjugo › Mon profil partenaire" in x
        assert "Votre part dans « Rénovation de l'école Jules-Ferry »" in x
    # Aucune adresse (ni celle du membre, ni celle du chef de file) ; ni l'acheteur, que l'aperçu cache aussi.
    _assert_courriel_propre(c, url, interdits=(b["email"], a["email"], "Ville de Quimper"))
    # Côté chef de file : toujours ni adresse ni lien.
    assert b["email"] not in r.text and token not in r.text
    # Renvoi (« Relancer ») : même lien, dit comme un rappel, adresse toujours absente de la réponse.
    db = _db()
    try:
        db.get(ProjectInvite, r.json()["invitation"]["id"]).emailed_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    rr = client.post(f"/api/projects/{pid}/invites/{r.json()['invitation']['id']}/resend", headers=a["headers"])
    assert rr.status_code == 200 and rr.json()["sent"] is True and b["email"] not in rr.text
    c2 = [x for x in courriels if x["to"] == b["email"]][-1]
    assert c2["objet"] == "Rappel : une entreprise vous propose un groupement — Rénovation de l'école Jules-Ferry"
    assert "Chef De File Réseau, qui a trouvé votre profil sur le réseau Adjugo, vous renvoie sa proposition" in c2["texte"]
    _assert_courriel_propre(c2, url, interdits=(b["email"], a["email"]))


# ═══ 3. Relances : le renvoi du chef de file et le rappel planifié ═══════════════════════════════════════════════

def test_renvoi_d_une_invitation_meme_lien_et_anti_spam_inchange(client, auth, courriels):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid = _project(client, h, name="Marché relancé")
    inv = _invite(client, h, pid, "Alpha SARL", recipient="alpha@partenaire.example")
    url = _base() + "/invite/" + inv["token"]
    n = len(courriels)
    # Moins de 15 minutes après l'envoi : refusé, rien ne part (anti-spam d'avant).
    r = client.post(f"/api/projects/{pid}/invites/{inv['id']}/resend", headers=h)
    assert r.status_code == 429 and len(courriels) == n
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, inv["id"]).emailed_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/invites/{inv['id']}/resend", headers=h)
    assert r.status_code == 200 and r.json()["sent"] is True
    c = courriels[-1]
    assert c["to"] == "alpha@partenaire.example"
    assert c["objet"] == "Rappel : invitation à répondre ensemble à un marché — Marché relancé"
    assert "Breizh Couverture vous renvoie son invitation à rejoindre son groupement" in c["texte"]
    _assert_courriel_propre(c, url, interdits=(auth["email"],))      # le même lien : le jeton ne change pas
    assert client.get(f"/api/projects/{pid}/invites", headers=h).json()[0]["token"] == inv["token"]


def test_quotas_et_anti_spam_d_invitation_inchanges():
    from app.routers import invites, reseau
    assert invites.DAILY_INVITE_CAP == 30 and invites.RESEND_MIN_INTERVAL == timedelta(minutes=15)
    assert invites.NOTIFY_MIN_INTERVAL_S == 30 * 60 and reseau.NETWORK_INVITES_PER_PROFILE_DAY == 10
    src = (ROOT / "app" / "routers" / "invites.py").read_text(encoding="utf-8")
    i = src.index('@router.post("/api/projects/{project_id}/invites/{invite_id}/resend")')
    assert src[i:i + 200].count('@limiter.limit("20/hour")') == 1
    corps = src[i:src.index("\n@router", i + 10)]
    for garde in ("_refuse_demo_sender(current_user)", "_require_verified_sender(current_user)",
                  "_check_network_resend(inv, current_user, db)", "_check_daily_invite_cap(current_user, db)",
                  "RESEND_MIN_INTERVAL"):
        assert garde in corps, garde
    # L'envoi reste réservé à un expéditeur à l'adresse confirmée (anti-spam par comptes jetables).
    assert 'if getattr(current_user, "email_verified", False) else False)' in src


def test_rappel_planifie_en_html_mene_a_la_part(client, auth, courriels):
    from tests.test_cotraitance_v4 import _alert_project
    import app.services.alerts as al
    _set_company(auth["email"], name="Breizh <Couverture>")
    pid, (inv,) = _alert_project(client, auth, days=3, n_partners=1, submit=False)
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    (c,) = [x for x in courriels if x["to"] == inv["recipient"] and x["objet"].startswith("Rappel —")]
    url = _base() + "/invite/" + inv["token"]
    assert c["objet"].startswith("Rappel — il vous reste 3 jours pour votre part (AO relances ")
    t, v = c["texte"], _visible(c["html"])
    echeance = (date.today() + timedelta(days=3)).strftime("%d/%m/%Y")
    for x in (t, v):
        assert "Il vous reste 3 jours pour ajouter votre part au groupement de Breizh <Couverture> sur le marché" in x
        assert f"(date limite : {echeance})" in x and "Votre part dans « AO relances " in x
        assert "Complétez votre part et soumettez-la à Breizh <Couverture>." in x
        assert "jamais le détail des prix des autres entreprises" in x       # ce qu'il voit, ici aussi
        assert "Kbis à fournir" in x                                       # attestations jointes (un seul courriel)
    assert "Breizh &lt;Couverture&gt;" in c["html"] and "Breizh <Couverture>" not in c["html"]
    assert "via votre lien Adjugo" not in t                               # avant : un lien cité, jamais donné
    nom = client.get(f"/api/projects/{pid}", headers=auth["headers"]).json()["name"]
    _assert_courriel_propre(c, url, interdits=(auth["email"],), saisies=(nom,))


# ═══ 4. Jamais d'envoi depuis la démonstration ═══════════════════════════════════════════════════════════════════

def test_jamais_d_envoi_depuis_la_demo(client, courriels):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    demo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    projets = client.get("/api/projects/", headers=demo).json()
    pid = projets[0]["id"]
    assert client.post(f"/api/projects/{pid}/invites", headers=demo,
                       json={"recipient": "victime@tiers.example", "company_name": "X"}).status_code == 403
    assert client.post(f"/api/projects/{pid}/reseau/invitations", headers=demo,
                       json={"profile_id": "0" * 32}).status_code == 403
    invs = client.get(f"/api/projects/{pid}/invites", headers=demo).json()
    if invs:
        assert client.post(f"/api/projects/{pid}/invites/{invs[0]['id']}/resend", headers=demo).status_code == 403
    # Le rappel planifié non plus : le marché de la démo qui a une invitation avec une adresse, à J-2.
    from app.models import Project, ProjectInvite, User
    from app.services.alerts import run_cotraitance_reminders
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        cible = db.query(ProjectInvite).filter(ProjectInvite.owner_id == u.id,
                                               ProjectInvite.recipient.like("%@%")).first()
        assert cible is not None
        p = db.get(Project, cible.project_id)
        avant, stage, adresse = p.deadline, cible.reminder_stage, cible.recipient
        p.deadline = date.today() + timedelta(days=2)
        db.commit()
        try:
            run_cotraitance_reminders(db)
        finally:
            p, cible = db.get(Project, p.id), db.get(ProjectInvite, cible.id)
            p.deadline, cible.reminder_stage = avant, stage
            db.commit()
    finally:
        db.close()
    assert not [x for x in courriels if x["to"] in ("victime@tiers.example", adresse)]


# ═══ 5. Textes : mots du glossaire, nom d'écran d'aujourd'hui ═════════════════════════════════════════════════════

def test_aucun_mot_banni_dans_le_module_des_courriels_d_invitation():
    """Le garde-fou du socle lit les fonctions qui appellent send_email ; les phrases vivent maintenant ici."""
    src = (ROOT / "app" / "services" / "email_invitation.py").read_text(encoding="utf-8")
    arbre = ast.parse(src)
    exclus = _docstrings(arbre)
    textes = [n.value for n in ast.walk(arbre) if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and id(n) not in exclus]
    textes += ["".join(v.value for v in n.values if isinstance(v, ast.Constant)) for n in ast.walk(arbre)
               if isinstance(n, ast.JoinedStr)]
    fautes = [t for t in textes if not _CLE.fullmatch(t) and mots_bannis(re.sub(r'style="[^"]*"', "", t))]
    assert not fautes, fautes
    assert not EMOJI.search(src)


def test_les_courriels_au_partenaire_disent_votre_part_plus_votre_espace():
    """§ 7.7 : les courriels qui citaient l'ancien « espace » du partenaire disent « votre part dans ce marché »."""
    inv = (ROOT / "app" / "routers" / "invites.py").read_text(encoding="utf-8")
    conv = (ROOT / "app" / "routers" / "convention.py").read_text(encoding="utf-8")
    al = (ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8")
    for src in (inv, conv, al):
        assert "votre espace" not in src and "espace dédié" not in src
    assert "Relisez-la et donnez votre accord depuis votre part dans ce marché :" in conv
    assert 'f"Votre part dans ce marché : {base}/invite/{inv.token}' in inv            # offre commune figée
    assert '"depuis votre part dans ce marché :' in al                                 # attestations à jour
    # « Retrouvez le détail » promettait un détail que le partenaire ne voit pas (le total seulement).
    assert "Retrouvez le détail" not in inv


def test_l_ancien_pied_des_courriels_existants_ne_change_pas():
    from app.services.email_templates import _PIED, reset_password_html, verify_email_html
    for h in (verify_email_html("https://adjugo.pro/app?verify=x", "Jean"), reset_password_html("https://x", "")):
        assert "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email." in h
    assert "ignorez simplement cet email" in _PIED
    from app.services.email_invitation import invitation
    h = invitation(chef="A SARL", marche="M", url="https://adjugo.pro/invite/t")["html"]
    assert "ignorez simplement cet email" not in h
    assert "Vous recevez ce message parce que A SARL a indiqué votre adresse pour vous inviter sur Adjugo." in _visible(h)
