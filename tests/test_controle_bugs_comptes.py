"""Contrôle des bugs d'octobre 2026, groupe « comptes » (inscription, équipe, essai, abonnement) : chaque test dit
ce que le logiciel DOIT faire d'après ses contrats (app/core/quota.py, docs/ESSAI_GARDE_FOU.md, CGV 3.5, textes
affichés) ; tous échouaient sur cfe04e1, chacun sur son défaut.

1. Transfert de propriété : le compte de facturation est le propriétaire (quota._billing_user). Le forfait, le
   client Stripe, le paiement à l'usage, les compteurs du mois, l'essai et le relevé du coût de l'IA suivent le
   nouveau propriétaire ; avant, une organisation Pro redevenait « starter » et un essai terminé rouvrait l'IA.
2. La fenêtre de transfert dit « Vous deviendrez simple administrateur » : l'ancien propriétaire devient
   administrateur (avant : « membre », il ne pouvait plus inviter).
3. Un collègue invité est un nouveau compte : il a une date de fin d'essai (avant : aucune ; retiré de
   l'organisation, il avait 5 analyses par mois sans fin et l'IA jamais en pause).
4. « Passer au Pro » cliqué par un collègue administrateur abonne l'organisation (client Stripe et paiement du
   propriétaire) ; un simple membre ne peut pas engager l'organisation (403 lisible, affiché tel quel).
5. « Gérer mon abonnement » ouvre l'abonnement de l'organisation pour un administrateur (avant : « Pas d'abonnement
   actif », « Portail indisponible »).
6. Nom d'entreprise à l'inscription : fait d'espaces, il ne nomme pas l'organisation « » ; au-delà de 255
   caractères, 422 lisible au lieu d'un 500 sur PostgreSQL.
7. Nom d'un collègue invité nettoyé et borné comme à l'inscription (clean_full_name).
8. « Renvoyer l'email de vérification » ne dit « renvoyé » que si le courriel est parti ; un envoi manqué
   n'entame pas le plafond du jour.
"""
import json
import os
import re
import shutil
import subprocess
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "app", "static", "app.js"), encoding="utf-8").read()


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _register(client, tag="", company="Test SARL", verified=True):
    email = f"cbc_{tag}{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Jean Test", "company_name": company})
    assert r.status_code == 201, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    uid = client.get("/api/auth/me", headers=h).json()["id"]
    if verified:
        _set(uid, email_verified=True)
    return uid, h, email


def _token_of(uid):
    from app.core.security import create_access_token
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        return {"Authorization": "Bearer " + create_access_token({"sub": str(u.id), "tv": int(u.token_version or 0)})}
    finally:
        db.close()


def _set(uid, **kw):
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        for k, v in kw.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def _get(uid):
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        return {c: getattr(u, c) for c in ("plan", "stripe_customer_id", "trial_ends_at", "trial_analyses_used",
                                           "analyses_used_this_month", "analyses_period", "overage_enabled",
                                           "overage_count", "org_role", "org_id", "full_name")}
    finally:
        db.close()


def _plan(row):
    p = row["plan"]
    return getattr(p, "value", p)


def _invite(client, h, tag="", nom="Marie Collègue"):
    em = f"cbc_col_{tag}{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=h, json={"email": em, "full_name": nom})
    assert r.status_code == 201, r.text
    return r.json()["id"], em


def _stripe_off(monkeypatch):
    """/api/stripe/status sans réseau : Stripe « en panne », le forfait est lu en base."""
    import stripe
    monkeypatch.setattr(stripe.Subscription, "list",
                        lambda **kw: (_ for _ in ()).throw(stripe.error.StripeError("hors ligne")))


def _webhook(client, monkeypatch, event: dict):
    import stripe
    from app.routers import stripe_pay
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda payload, sig, secret: event)
    monkeypatch.setattr(stripe_pay.settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_local")
    r = client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 200, r.text


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _methode(nom):
    from tests.test_reorganisation_v2b_espace_partenaire import _methode as m
    return m(nom)


# ── 1. Le transfert de propriété emporte la facturation (le compte de facturation change) ──

def test_1_transfert_emporte_le_forfait_paye(client, monkeypatch):
    """Propriétaire Pro (client Stripe, paiement à l'usage activé, 7 analyses ce mois, 2 hors forfait) : après le
    transfert, l'organisation est toujours Pro pour tous ses membres, portée par le nouveau propriétaire ; la
    résiliation reçue ensuite de Stripe rétrograde bien l'organisation."""
    from app.core.quota import _period, usage
    from app.models import Job, PlanType, User
    from app.services.billing_usage import UNITE_KIND
    owner, h, _ = _register(client, "t1")
    _set(owner, plan=PlanType.pro, stripe_customer_id="cus_cbc_t1", overage_enabled=True, overage_count=2,
         analyses_used_this_month=7, analyses_period=_period())
    mid, _ = _invite(client, h, "t1")
    db = _db()
    try:   # une unité de dépassement envoyée ce mois (annulable si l'analyse est remboursée)
        db.add(Job(user_id=owner, kind=UNITE_KIND, status="envoyee", label="adjugo-ovr-test-cbc"))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/org/transfer-ownership", headers=h, json={"new_owner_id": mid})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        u = usage(db.get(User, mid), db)
        assert u["plan"] == "pro" and u["analyses_limit"] == 30 and u["analyses_used"] == 7, u
        assert u["overage_enabled"] is True and u["overage_count"] == 2, u
        assert usage(db.get(User, owner), db)["plan"] == "pro"          # l'ancien propriétaire aussi
        assert [j.user_id for j in db.query(Job).filter(Job.label == "adjugo-ovr-test-cbc")] == [mid]
    finally:
        db.close()
    _stripe_off(monkeypatch)
    for who in (mid, owner):
        s = client.get("/api/stripe/status", headers=_token_of(who)).json()
        assert s["plan"] == "pro" and s["analyses_limit"] == 30, s
    new, old = _get(mid), _get(owner)
    assert new["stripe_customer_id"] == "cus_cbc_t1"
    assert old["stripe_customer_id"] is None and _plan(old) == "starter"
    assert old["overage_enabled"] is False and old["overage_count"] == 0 and old["analyses_used_this_month"] == 0
    _webhook(client, monkeypatch, {"id": f"evt_cbc_{uuid.uuid4().hex[:8]}", "type": "customer.subscription.deleted",
                                   "data": {"object": {"customer": "cus_cbc_t1"}}})
    db = _db()
    try:
        assert usage(db.get(User, mid), db)["plan"] == "starter"
    finally:
        db.close()


def test_1_transfert_ne_remet_pas_un_essai_a_neuf(client):
    """Essai terminé : transférer la propriété à un collègue invité ne rouvre pas les fonctions d'IA."""
    from datetime import datetime, timedelta, timezone
    from app.core.quota import pause_ia, usage
    from app.models import User
    owner, h, _ = _register(client, "t1b")
    mid, _ = _invite(client, h, "t1b")
    _set(owner, trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1), trial_analyses_used=12)
    db = _db()
    try:
        assert pause_ia(db.get(User, mid), db) == "essai"
    finally:
        db.close()
    assert client.post("/api/org/transfer-ownership", headers=h, json={"new_owner_id": mid}).status_code == 200
    db = _db()
    try:
        m = db.get(User, mid)
        assert pause_ia(m, db) == "essai", usage(m, db)
        assert usage(m, db)["trial_state"] == "expired"
        assert int(m.trial_analyses_used or 0) == 12
        # L'ancien propriétaire garde sa propre date de fin d'essai : s'il quitte un jour l'organisation, il n'est
        # pas un compte sans fin d'essai.
        assert pause_ia(db.get(User, owner), db) == "essai"
    finally:
        db.close()


def test_1_transfert_emporte_le_releve_du_cout_de_l_ia(client):
    """Essai en cours : la limite d'usage de l'IA (coût déjà engagé) suit le nouveau compte de facturation, y compris
    quand le nouveau propriétaire avait déjà une ligne pour la même période (fusionnée, pas en double)."""
    from app.models import UsageIA, User
    from app.services import budget_ia
    owner, h, _ = _register(client, "t1c")
    mid, _ = _invite(client, h, "t1c")
    budget = budget_ia.budget_essai_eur()
    assert budget > 0
    oid = _get(owner)["org_id"]
    db = _db()
    try:
        db.add(UsageIA(compte=f"u{owner}", billing_user_id=owner, org_id=oid, periode=budget_ia._periode(),
                       essai=True, cout_eur=0.8 * budget, appels=3))
        db.add(UsageIA(compte=f"u{mid}", billing_user_id=mid, org_id=oid, periode=budget_ia._periode(),
                       essai=True, cout_eur=0.1 * budget, appels=1))
        db.commit()
        assert budget_ia.etat_essai(db, db.get(User, owner)) == "proche"
    finally:
        db.close()
    assert client.post("/api/org/transfer-ownership", headers=h, json={"new_owner_id": mid}).status_code == 200
    db = _db()
    try:
        m = db.get(User, mid)
        assert abs(budget_ia.cout_essai_eur(db, m) - 0.9 * budget) < 1e-6
        assert budget_ia.etat_essai(db, m) == "proche"
        rows = db.query(UsageIA).filter(UsageIA.compte == f"u{mid}").all()
        assert len(rows) == 1 and rows[0].appels == 4 and rows[0].billing_user_id == mid
        assert db.query(UsageIA).filter(UsageIA.compte == f"u{owner}").count() == 0
    finally:
        db.close()


# ── 2. « Vous deviendrez simple administrateur » (fenêtre de transfert) doit être vrai ──

def test_2_l_ancien_proprietaire_devient_administrateur(client):
    assert "Vous deviendrez simple administrateur." in JS
    owner, h, _ = _register(client, "t2")
    mid, _ = _invite(client, h, "t2")
    r = client.post("/api/org/transfer-ownership", headers=h, json={"new_owner_id": mid})
    assert r.status_code == 200, r.text
    h2 = {"Authorization": "Bearer " + r.json()["access_token"]}
    o = client.get("/api/org/", headers=h2).json()
    assert o["my_role"] == "admin" and o["is_owner"] is False and o["can_invite"] is True, o
    me = [m for m in o["members"] if m["is_me"]][0]
    assert me["role"] == "admin" and me["is_owner"] is False
    # Le propriétaire reste seul à retirer, changer les rôles et transférer.
    assert client.delete(f"/api/org/members/{mid}", headers=h2).status_code == 403
    assert client.put(f"/api/org/members/{mid}/role", headers=h2, json={"role": "membre"}).status_code == 403
    assert client.post("/api/org/transfer-ownership", headers=h2, json={"new_owner_id": owner}).status_code == 403


# ── 3. Tout nouveau compte a une date de fin d'essai, collègue invité compris ──

def test_3_un_collegue_invite_a_une_date_de_fin_d_essai(client):
    from datetime import datetime, timedelta, timezone
    from app.core.quota import TRIAL_DAYS, _as_utc, usage
    from app.models import User
    owner, h, _ = _register(client, "t3")
    mid, _ = _invite(client, h, "t3")
    row = _get(mid)
    assert row["trial_ends_at"] is not None, row
    restant = _as_utc(row["trial_ends_at"]) - datetime.now(timezone.utc)
    assert timedelta(days=TRIAL_DAYS - 1, hours=23) < restant <= timedelta(days=TRIAL_DAYS)
    db = _db()
    try:   # membre : le forfait et l'essai du propriétaire, comme avant
        assert usage(db.get(User, mid), db)["trial_ends_at"] == usage(db.get(User, owner), db)["trial_ends_at"]
    finally:
        db.close()
    assert client.delete(f"/api/org/members/{mid}", headers=h).status_code == 200
    db = _db()
    try:
        u = usage(db.get(User, mid), db)
        assert u["trial_state"] == "active" and u["quota_scope"] == "essai", u
        assert u["analyses_limit"] == 30 and 0 < u["trial_days_left"] <= TRIAL_DAYS
    finally:
        db.close()


# ── 4. Le paiement est rattaché au compte de facturation (propriétaire), pas au collègue qui clique ──

def test_4_le_paiement_d_un_collegue_administrateur_abonne_l_organisation(client, monkeypatch):
    import stripe
    from app.core.quota import usage
    from app.models import User
    owner, h, _ = _register(client, "t4")
    mid, _ = _invite(client, h, "t4")
    assert client.put(f"/api/org/members/{mid}/role", headers=h, json={"role": "admin"}).status_code == 200
    vu = {}

    class _Client:
        id = "cus_cbc_t4"

    class _Session:
        url, id = "https://checkout.test/x", "cs_test_cbc"

    monkeypatch.setattr(stripe.Customer, "create", lambda **kw: vu.update(client=kw) or _Client())
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: vu.update(session=kw) or _Session())
    r = client.post("/api/stripe/create-checkout?plan=pro", headers=_token_of(mid))
    assert r.status_code == 200, r.text
    assert vu["client"]["metadata"]["user_id"] == str(owner), vu["client"]
    assert vu["session"]["customer"] == "cus_cbc_t4" and vu["session"]["metadata"]["user_id"] == str(owner)
    assert _get(owner)["stripe_customer_id"] == "cus_cbc_t4" and _get(mid)["stripe_customer_id"] is None
    _webhook(client, monkeypatch, {"id": f"evt_cbc_{uuid.uuid4().hex[:8]}", "type": "checkout.session.completed",
                                   "data": {"object": {"metadata": vu["session"]["metadata"],
                                                       "customer": "cus_cbc_t4"}}})
    db = _db()
    try:
        assert usage(db.get(User, mid), db)["plan"] == "pro"
        assert usage(db.get(User, owner), db)["plan"] == "pro"
    finally:
        db.close()


def test_4_un_simple_membre_ne_peut_pas_engager_l_organisation(client, monkeypatch):
    """Même règle que le paiement à l'usage : propriétaire ou administrateur ; aucune écriture Stripe sinon."""
    import stripe
    owner, h, _ = _register(client, "t4b")
    mid, _ = _invite(client, h, "t4b")
    ecrit = []

    def _refus(**kw):
        ecrit.append(kw)
        raise stripe.error.StripeError("aucune écriture Stripe attendue")

    monkeypatch.setattr(stripe.Customer, "create", _refus)
    monkeypatch.setattr(stripe.checkout.Session, "create", _refus)
    r = client.post("/api/stripe/create-checkout?plan=pro", headers=_token_of(mid))
    assert r.status_code == 403, r.text
    assert "propriétaire ou un administrateur" in r.json()["detail"]
    assert ecrit == [] and _get(owner)["stripe_customer_id"] is None


def test_4_5_l_ecran_affiche_le_refus_du_serveur():
    """Refus 403 du paiement ou du portail : l'écran affiche le message du serveur (qui peut le faire), pas
    « Paiement indisponible (config Stripe) » ni « Portail indisponible »."""
    noms = ("checkout", "portal")
    r = _node("const o = {\n" + "\n".join(_methode(n) for n in noms) + "\n};\n" + r"""
const vus = [];
Object.assign(o, { notify: (m, t) => vus.push([m, t || ""]),
  api: async () => { const e = new Error("Seul le propriétaire ou un administrateur de l'organisation peut le faire."); e.status = 403; throw e; } });
(async () => {
  await o.checkout("pro"); await o.portal();
  o.api = async () => { const e = new Error("Pas d'abonnement actif"); e.status = 400; throw e; };
  await o.checkout("pro"); await o.portal();
  console.log(JSON.stringify(vus));
})();
""")
    refus = "Seul le propriétaire ou un administrateur de l'organisation peut le faire."
    assert r[0] == [refus, "err"] and r[1] == [refus, "err"], r
    assert r[2][0].startswith("Paiement indisponible") and r[3][0] == "Portail indisponible", r


# ── 5. « Gérer mon abonnement » pour un administrateur d'une organisation Pro ──

def test_5_portail_pour_un_administrateur_d_une_organisation_pro(client, monkeypatch):
    import stripe
    from app.models import PlanType
    owner, h, _ = _register(client, "t5")
    _set(owner, plan=PlanType.pro, stripe_customer_id="cus_cbc_t5")
    mid, _ = _invite(client, h, "t5")
    assert client.put(f"/api/org/members/{mid}/role", headers=h, json={"role": "admin"}).status_code == 200
    _stripe_off(monkeypatch)
    assert client.get("/api/stripe/status", headers=_token_of(mid)).json()["plan"] == "pro"
    vu = {}

    class _Portail:
        url = "https://portal.test/x"

    monkeypatch.setattr(stripe.billing_portal.Session, "create", lambda **kw: vu.update(kw) or _Portail())
    r = client.post("/api/stripe/portal", headers=_token_of(mid))
    assert r.status_code == 200, r.text
    assert vu["customer"] == "cus_cbc_t5" and r.json()["portal_url"] == "https://portal.test/x"
    # Un simple membre : refus clair, aucune écriture Stripe.
    assert client.put(f"/api/org/members/{mid}/role", headers=h, json={"role": "membre"}).status_code == 200
    vu.clear()
    r = client.post("/api/stripe/portal", headers=_token_of(mid))
    assert r.status_code == 403 and vu == {}, r.text
    # Le propriétaire, lui, ouvre toujours son portail.
    assert client.post("/api/stripe/portal", headers=h).status_code == 200 and vu["customer"] == "cus_cbc_t5"


# ── 6. Nom d'entreprise à l'inscription : nettoyé, borné ──

def test_6_nom_d_entreprise_fait_d_espaces(client):
    uid, h, _ = _register(client, "t6", company="   ")
    o = client.get("/api/org/", headers=h).json()
    assert o["name"] == "Équipe Jean Test", o
    from app.models import Company
    db = _db()
    try:
        assert db.query(Company).filter(Company.user_id == uid).count() == 0    # pas de fiche nommée « »
    finally:
        db.close()
    uid, h, _ = _register(client, "t6b", company="  Menuiserie Le Gall  ")
    assert client.get("/api/org/", headers=h).json()["name"] == "Menuiserie Le Gall"


def test_6_nom_d_entreprise_trop_long_refuse_lisiblement(client):
    """Au-delà de 255 caractères (largeur des colonnes), PostgreSQL refusait l'inscription (500) : 422 lisible."""
    email = f"cbc_t6l{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Jean Test", "company_name": "Menuiserie " + "x" * 300})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][-1] == "company_name"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Jean Test", "company_name": "  " + "y" * 255 + "  "})
    assert r.status_code == 201, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/org/", headers=h).json()["name"] == "y" * 255


# ── 7. Nom d'un collègue invité : mêmes règles qu'à l'inscription ──

def test_7_nom_du_collegue_invite_nettoye_et_borne(client):
    from app.models import User
    owner, h, _ = _register(client, "t7")
    em = f"cbc_col_t7{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=h, json={"email": em, "full_name": "Ma\x00rie Du\tpont " + "x" * 300})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        nom = db.query(User).filter(User.email == em).first().full_name
    finally:
        db.close()
    assert nom.startswith("Marie Dupont x") and len(nom) == 120, (nom[:20], len(nom))
    assert r.json()["full_name"] == nom
    # Organisation Business (assez de places) : fait d'espaces seulement, le nom est la partie avant « @ ».
    from app.models import PlanType
    _set(owner, plan=PlanType.business)
    em2 = f"cbc_col_t7b{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=h, json={"email": em2, "full_name": "   "})
    assert r.status_code == 201, r.text
    assert r.json()["full_name"] == em2.split("@")[0]


# ── 8. « Renvoyer l'email de vérification » dit vrai ──

def test_8_renvoi_de_l_email_dit_vrai_quand_il_ne_part_pas(client, monkeypatch):
    import app.routers.auth as auth_mod
    uid, h, _ = _register(client, "t8", verified=False)       # courriel coupé en test : rien n'est parti
    monkeypatch.setattr(auth_mod, "send_email", lambda *a, **k: False)
    for _ in range(auth_mod.VERIFY_MAILS_PER_DAY):
        r = client.post("/api/auth/resend-verification", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False and "renvoy" not in r.json()["message"].lower(), r.json()
        assert r.json()["message"] == auth_mod.MSG_VERIF_NON_PARTIE
    envois = []
    monkeypatch.setattr(auth_mod, "send_email", lambda to, *a, **k: envois.append(to) or True)
    for _ in range(auth_mod.VERIFY_MAILS_PER_DAY):       # les envois manqués (inscription comprise) n'ont rien consommé
        r = client.post("/api/auth/resend-verification", headers=h)
        assert r.status_code == 200 and r.json() == {"ok": True, "message": "Email de confirmation renvoyé."}, r.text
    assert len(envois) == auth_mod.VERIFY_MAILS_PER_DAY
    assert client.post("/api/auth/resend-verification", headers=h).status_code == 429   # atteint par de vrais envois
    # Affiché dans l'écran plein comme « Email de confirmation renvoyé. » : traduit comme lui (décision 16).
    i18n = open(os.path.join(ROOT, "app", "static", "i18n.js"), encoding="utf-8").read()
    d = json.loads(i18n.split("\n", 1)[1][len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for langue in ("nl", "es"):
        assert d[langue].get(auth_mod.MSG_VERIF_NON_PARTIE) and d[langue].get("Email de confirmation renvoyé."), langue


def test_8_l_ecran_montre_l_envoi_manque_comme_un_echec():
    """Bouton « Renvoyer l'email de confirmation » des écrans de signature : la réponse « n'a pas pu partir »
    s'affiche en message d'erreur, « renvoyé » en message normal."""
    r = _node("const o = {\n" + _methode("resendVerification") + "\n};\n" + r"""
const vus = [];
let reponse = { ok: false, message: "L'email de confirmation n'a pas pu partir pour l'instant." };
Object.assign(o, { notify: (m, t) => vus.push([m, t || ""]), api: async () => reponse });
(async () => {
  await o.resendVerification();
  reponse = { ok: true, message: "Email de confirmation renvoyé." }; await o.resendVerification();
  console.log(JSON.stringify(vus));
})();
""")
    assert r == [["L'email de confirmation n'a pas pu partir pour l'instant.", "err"],
                 ["Email de confirmation renvoyé.", ""]], r
