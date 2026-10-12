"""
Essai gratuit TERMINÉ sans formule payante (décision du fondateur du 12/10/2026, option a).

 • toutes les fonctions d'IA sont en pause : analyse d'un avis, import et ré-analyse d'un dossier,
   questions sur un dossier, atelier (rédiger, raccourcir), questionnaire, chiffrage, veille manuelle
   (texte collé, fichier importé, recherche des délibérations), renouvellements par l'IA, veille
   automatique ;
 • chaque refus (402, code « essai_termine ») tombe AVANT tout appel à l'IA et tout débit, avec un
   message clair et sobre qui invite à choisir un forfait (aucun montant) ;
 • un traitement commencé avant la fin de l'essai va au bout ;
 • essai en cours, comptes historiques sans essai, compte de démonstration, forfaits payants :
   inchangés ;
 • CGV (article 3.5) et page Sécurité : texte retenu, pages servies synchronisées avec leur source.
Aucun appel réseau ni IA réel : le fournisseur IA est simulé.
"""
import importlib.util
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from tests.test_essai_garde_fou import _cout_essai, _fake, _sans_montant, _set, _user
from tests.test_lecture_integrale import _answer, _gros_dossier, _petit_dossier, _project, _wait
from tests.test_redaction_socle0 import (_atelier, _attendre_tache, _company, _db, _memoire_answer,
                                         _set_analysis, _user_id)
from tests.test_redaction_socle0 import _project as _projet_atelier

ROOT = pathlib.Path(__file__).resolve().parent.parent

TENDER = {"objet": "Réfection de toiture", "provenance": {"source": "BOAMP", "source_url": "https://www.boamp.fr/x",
                                                          "official_ref": "x"}}
ANALYSE = {"summary": "s", "details": {"intitule_marche": "Marché test"},
           "dce_excerpt": "REGLEMENT. Date limite le 3 mars."}


# ── Outils ──────────────────────────────────────────────────────────────────────────────────

def _hier():
    return datetime.now(timezone.utc) - timedelta(days=1)


def _expirer(email):
    _set(email, trial_ends_at=_hier())


def _termine(r):
    """Refus « essai terminé » : 402, code dédié, message sobre qui invite à choisir un forfait."""
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["code"] == "essai_termine", d
    assert "essai gratuit est terminé" in d["message"] and "forfait" in d["message"], d
    assert "restent accessibles" in d["message"]
    _sans_montant(r.json())
    return d


def _inscrire(client):
    email = f"fin_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Test Fin", "company_name": "Fin SARL"})
    assert r.status_code == 201, r.text
    _set(email, email_verified=True)
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _compte(model, uid):
    db = _db()
    try:
        return db.query(model).filter(model.user_id == uid).count()
    finally:
        db.close()


# ═══ 1. Essai terminé : chaque fonction d'IA refusée avant tout appel et tout débit ═════════════

def test_essai_termine_chaque_fonction_d_ia_refusee_avant_tout_appel_et_tout_debit(client, auth, monkeypatch):
    import app.routers.amont as amont_router
    import app.services.decp as decp
    from app.models import Document, Job
    fake = _fake(monkeypatch, _memoire_answer("Texte de la partie."))
    h = auth["headers"]
    uid = _user_id(auth["email"])
    # Préparé pendant l'essai : un marché analysé, un dossier de présentation, une base de savoir-faire.
    _company(client, h, team=[])
    pid = _projet_atelier(client, h, "Marché après l'essai")
    _set_analysis(pid, ANALYSE)
    st = _atelier(client, h, pid)
    sid = st["sections"][0]["id"]
    r = client.post("/api/knowledge/text", headers=h, json={
        "name": "Références", "text": "Nous réalisons des toitures en ardoise et en zinc depuis vingt ans en Bretagne."})
    assert r.status_code == 200, r.text

    _expirer(auth["email"])
    avant = _user(auth["email"])
    jobs0, docs0 = _compte(Job, uid), _compte(Document, uid)
    recherches = []

    class _Deliberations:
        def fetch_recent(self, *a, **k):
            recherches.append(1)
            return [{"titre": "Délibération"}]

    monkeypatch.setattr(amont_router, "DeliberationSource", _Deliberations)
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"renewals": []})

    # Analyses : avis, import d'un dossier (refusé avant la lecture et le rangement du fichier), ré-analyse.
    _termine(client.post("/api/sourcing/analyze", headers=h, json={"tender": TENDER}))
    _termine(client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                         files={"file": ("DCE.zip", _petit_dossier(), "application/zip")}))
    _termine(client.post("/api/sourcing/reanalyze", headers=h, data={"project_id": str(pid)}))
    # Questions sur le dossier (aucune réservation laissée), renouvellements par l'IA, chiffrage.
    _termine(client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"}))
    _termine(client.post("/api/sourcing/renewals", headers=h, json={"query": "toiture"}))
    _termine(client.post(f"/api/chiffrage/{pid}/estimate", headers=h, json={"distance_km": 10}))
    # Questionnaire.
    _termine(client.post("/api/knowledge/questionnaire", headers=h, json={"questions": ["Vos références ?"]}))
    # Atelier : écrire soi-même reste possible ; rédiger (une partie, toutes) et raccourcir : refusés.
    texte = " ".join(["Nous intervenons avec une équipe dédiée et un encadrement présent sur le chantier."] * 8)
    r = client.put(f"/api/atelier/{pid}/sections/{sid}/texte", headers=h, json={"texte": texte})
    assert r.status_code == 200, r.text
    _termine(client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={"accepte_debit": True}))
    _termine(client.post(f"/api/atelier/{pid}/rediger", headers=h, json={"accepte_debit": True}))
    _termine(client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={}))
    # Veille manuelle : texte collé, fichier importé, recherche des délibérations (refusée avant de chercher).
    _termine(client.post("/api/amont/analyze-text", headers=h, json={
        "text": "Délibération du conseil municipal : rénovation de l'école élémentaire prévue en 2027."}))
    _termine(client.post("/api/amont/analyze-upload", headers=h,
                         files={"file": ("deliberation.txt", b"Deliberation du conseil municipal", "text/plain")}))
    _termine(client.post("/api/amont/scan", headers=h, json={}))
    assert recherches == []
    # Veille automatique : ne s'active plus (la désactiver reste possible).
    _termine(client.post("/api/amont/auto", headers=h, json={"enabled": True}))
    assert client.post("/api/amont/auto", headers=h, json={"enabled": False}).status_code == 200

    # Aucun appel à l'IA, aucun débit, aucune tâche, aucun fichier rangé.
    assert fake.calls == []
    apres = _user(auth["email"])
    assert (apres.trial_analyses_used or 0) == (avant.trial_analyses_used or 0)
    assert (apres.analyses_used_this_month or 0) == (avant.analyses_used_this_month or 0)
    assert (apres.overage_count or 0) == (avant.overage_count or 0)
    assert not apres.amont_alerts_enabled
    assert _compte(Job, uid) == jobs0
    assert _compte(Document, uid) == docs0

    # Ce qui ne fait pas appel à l'IA reste accessible : marchés, atelier, renouvellements par les
    # données publiques des marchés (sans IA).
    assert client.get("/api/projects/", headers=h).status_code == 200
    assert client.get(f"/api/atelier/{pid}", headers=h).status_code == 200
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"renewals": [{"objet": "Toiture"}]})
    r = client.post("/api/sourcing/renewals", headers=h, json={"query": "toiture"})
    assert r.status_code == 200 and r.json()["renewals"], r.text
    assert fake.calls == []

    # L'écran : essai terminé, plus aucune analyse, jamais de montant.
    us = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert us["trial_state"] == "expired" and us["plan"] == "starter" and us["analyses_remaining"] == 0
    _sans_montant(us)


def test_essai_termine_refus_au_niveau_du_compte_de_facturation(client, auth):
    """Le propriétaire de l'organisation porte le forfait : ses membres sont en pause avec lui, et
    reprennent dès qu'il choisit un forfait. Les fonctions d'entrée refusent avant tout débit."""
    from app.core import quota
    from app.core.security import hash_password
    from app.models import PlanType, User
    from app.services import budget_ia
    owner = _user(auth["email"])
    db = _db()
    try:
        m = User(email=f"membre_fin_{owner.id}@test.fr", hashed_password=hash_password("motdepasse123"),
                 full_name="Membre", org_id=owner.org_id, email_verified=True)
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    _expirer(auth["email"])
    db = _db()
    try:
        membre = db.get(User, mid)
        assert quota.essai_termine(quota._billing_user(membre, db))
        for appel in (lambda: quota.exiger_ia(membre, db), lambda: quota.consume_analysis(membre, db),
                      lambda: quota.reserve_question(membre, db),
                      lambda: budget_ia.verifier(membre, db, "chiffrage")):
            with pytest.raises(HTTPException) as e:
                appel()
            assert e.value.status_code == 402 and e.value.detail["code"] == "essai_termine"
        o = db.get(User, owner.id)
        assert (o.analyses_used_this_month or 0) == 0 and (o.trial_analyses_used or 0) == 0
    finally:
        db.close()
    # Le propriétaire choisit un forfait : tout repart, pour lui comme pour ses membres.
    _set(auth["email"], plan=PlanType.pro, analyses_used_this_month=0, analyses_period=quota._period())
    db = _db()
    try:
        membre = db.get(User, mid)
        quota.exiger_ia(membre, db)
        budget_ia.verifier(membre, db, "chiffrage")
        quota.consume_analysis(membre, db)
        quota.reserve_question(membre, db)
    finally:
        db.close()


# ═══ 2. Un traitement commencé pendant l'essai va au bout ═══════════════════════════════════════

def test_lecture_commencee_pendant_l_essai_va_au_bout(client, auth, monkeypatch):
    from app.services import analysis as an
    monkeypatch.setattr(an, "ocr_available", lambda: False)
    email = auth["email"]
    fin = {"v": False}

    def ans(kw):
        if not fin["v"]:
            fin["v"] = True
            _expirer(email)              # l'essai se termine pendant la lecture du dossier
        return _answer(kw)

    fake = _fake(monkeypatch, ans)
    h = auth["headers"]
    pid = _project(client, h, "Gros dossier en fin d'essai")
    z, codes, _total, _p = _gros_dossier()
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", z, "application/zip")})
    assert r.status_code == 202, r.text
    st = _wait(client, h, pid)
    assert fin["v"] and st["etat"] == "termine", st      # jamais un dossier à moitié lu
    sent = fake.sent()
    for code in codes:
        assert f"FIN-PIECE-{code}" in sent, code
    assert _user(email).trial_analyses_used == 1          # une analyse débitée, au lancement
    # L'opération suivante est refusée avant tout appel.
    n = len(fake.calls)
    _termine(client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Compacteur ?"}))
    assert len(fake.calls) == n


def test_redaction_commencee_pendant_l_essai_va_au_bout(client, auth, monkeypatch):
    email = auth["email"]
    fin = {"v": False}
    base = _memoire_answer("Texte de la partie.")

    def ans(kw):
        if not fin["v"]:
            fin["v"] = True
            _expirer(email)              # l'essai se termine pendant la rédaction
        return base(kw)

    fake = _fake(monkeypatch, ans)
    h = auth["headers"]
    _company(client, h, team=[])
    pid = _projet_atelier(client, h, "Rédaction en fin d'essai")
    _set_analysis(pid, {"details": {"intitule_marche": "Rédaction en fin d'essai"}})
    st = _atelier(client, h, pid)
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    j = _attendre_tache(client, h, pid, r.json()["tache"]["id"])
    assert fin["v"] and j["status"] == "done", j
    redigees = r.json()["section_ids"]
    assert len(redigees) >= 1 and len(fake.calls) >= len(redigees)
    n = len(fake.calls)
    _termine(client.post(f"/api/atelier/{pid}/sections/{st['sections'][0]['id']}/rediger", headers=h,
                         json={"accepte_debit": True}))
    assert len(fake.calls) == n


# ═══ 3. Non-régression : essai en cours, forfaits payants, comptes historiques, démonstration ═══

def test_essai_en_cours_inchange(client, auth):
    from app.core import quota
    from app.models import User
    from app.services import budget_ia
    uid = _user_id(auth["email"])
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert quota.essai_actif(u) and not quota.essai_termine(u)
        quota.exiger_ia(u, db)
        budget_ia.verifier(u, db, "analyse")
        assert quota._limit(u) == 30 and quota.questions_limit(u, db) == 15
        quota.consume_analysis(u, db)
        quota.reserve_question(u, db)
        us = quota.usage(u, db)
        assert us["quota_scope"] == "essai" and us["analyses_limit"] == 30 and us["analyses_remaining"] == 29
        assert us["trial_questions_per_day"] == 15 and us["trial_state"] == "active"
    finally:
        db.close()
    # Le budget de l'essai garde son propre refus (« limite d'usage »), distinct de la fin d'essai.
    _cout_essai(uid, 14.99)
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        with pytest.raises(HTTPException) as e:
            budget_ia.verifier(u, db, "analyse")
        assert e.value.status_code == 402 and e.value.detail["code"] == "essai_limite_usage"
    finally:
        db.close()


@pytest.mark.parametrize("plan,analyses,questions", [("pro", 30, 50), ("business", 100, 120)])
def test_forfait_payant_apres_un_essai_termine_inchange(client, auth, monkeypatch, plan, analyses, questions):
    from app.core import quota
    from app.models import PlanType, User
    from app.services import budget_ia
    _fake(monkeypatch, lambda kw: ("Le 3 mars.", "end_turn"))
    _set(auth["email"], plan=PlanType(plan), trial_ends_at=_hier(), analyses_used_this_month=0,
         analyses_period=quota._period())
    h = auth["headers"]
    pid = _project(client, h, f"Marché {plan}")
    _set_analysis(pid, ANALYSE)
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"})
    assert r.status_code == 200, r.text
    assert client.post("/api/amont/auto", headers=h, json={"enabled": True}).json()["enabled"] is True
    assert client.post("/api/amont/auto", headers=h, json={"enabled": False}).status_code == 200
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert not quota.essai_termine(u) and not quota.essai_actif(u)
        quota.exiger_ia(u, db)
        budget_ia.verifier(u, db, "analyse", 9_999.0)
        assert quota._limit(u) == analyses and quota.questions_limit(u, db) == questions
        quota.consume_analysis(u, db)
        us = quota.usage(u, db)
        assert us["analyses_limit"] == analyses and us["analyses_used"] == 1 and us["trial_state"] is None
        assert "quota_scope" not in us
        # Au plafond du forfait : le refus d'avant (« Quota d'analyses IA atteint … ce mois »).
        u.analyses_used_this_month = analyses
        db.commit()
        with pytest.raises(HTTPException) as e:
            quota.consume_analysis(u, db)
        assert e.value.status_code == 402 and "ce mois" in e.value.detail
    finally:
        db.close()


def test_compte_historique_sans_essai_inchange(client, auth, monkeypatch):
    from app.core import quota
    from app.models import PlanType, User
    from app.services import budget_ia
    _fake(monkeypatch, lambda kw: ("Le 3 mars.", "end_turn"))
    _set(auth["email"], plan=PlanType.starter, trial_ends_at=None, analyses_used_this_month=0,
         analyses_period=quota._period())
    h = auth["headers"]
    pid = _project(client, h, "Marché historique")
    _set_analysis(pid, ANALYSE)
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert quota._trial_state(u) == "none" and not quota.essai_termine(u)
        quota.exiger_ia(u, db)
        budget_ia.verifier(u, db, "chiffrage")
        assert quota._limit(u) == 5 and quota.questions_limit(u, db) == 15
        quota.consume_analysis(u, db)
        assert quota.usage(u, db)["analyses_remaining"] == 4
    finally:
        db.close()


def test_compte_de_demonstration_inchange(client):
    """La démo garde son refus « lecture guidée » (403), même avec une date de fin d'essai passée."""
    from app.core import quota
    from app.models import User
    from app.services.demo_seed import DEMO_EMAIL
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    hd = {"Authorization": f"Bearer {r.json()['access_token']}"}
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        ancienne = u.trial_ends_at
        u.trial_ends_at = _hier()
        db.commit()
        try:
            quota.exiger_ia(u, db)                              # sans effet : la démo a son propre refus
            with pytest.raises(HTTPException) as e:
                quota.consume_analysis(u, db)
            assert e.value.status_code == 403 and "La démo est en lecture guidée" in e.value.detail
            pid = client.get("/api/projects/", headers=hd).json()[0]["id"]
            r = client.post("/api/sourcing/ask", headers=hd, json={"project_id": pid, "question": "Date ?"})
            assert r.status_code == 403 and r.json()["detail"].startswith("La démo est en lecture guidée")
            r = client.post("/api/sourcing/analyze", headers=hd, json={"tender": TENDER})
            assert r.status_code == 403 and "La démo est en lecture guidée" in r.json()["detail"]
        finally:
            u = db.query(User).filter(User.email == DEMO_EMAIL).first()
            u.trial_ends_at = ancienne
            db.commit()
    finally:
        db.close()


# ═══ 4. Veille automatique : un essai terminé n'est plus servi ═════════════════════════════════

def test_veille_automatique_ne_sert_plus_un_essai_termine(client, auth, monkeypatch):
    import app.services.agents.amont as agents_amont
    import app.services.profile as profile
    import app.sourcing.sources.deliberations as deliberations
    from app.services import alerts
    actif_email, _h = _inscrire(client)
    _set(auth["email"], amont_alerts_enabled=True)
    _set(actif_email, amont_alerts_enabled=True)
    _expirer(auth["email"])
    servis = []
    monkeypatch.setattr(profile, "criteria_dict", lambda uid, db: (servis.append(uid), {})[1])
    monkeypatch.setattr(deliberations.DeliberationSource, "fetch_recent", lambda self, *a, **k: [{"titre": "x"}])
    monkeypatch.setattr(agents_amont, "detect_from_deliberations", lambda *a, **k: [])
    db = _db()
    try:
        alerts.run_amont_alerts(db)
    finally:
        db.close()
        _set(auth["email"], amont_alerts_enabled=False)
        _set(actif_email, amont_alerts_enabled=False)
    assert _user_id(actif_email) in servis                  # essai en cours : servi comme avant
    assert _user_id(auth["email"]) not in servis            # essai terminé sans forfait : plus servi


# ═══ 5. Écran : carte sobre « essai terminé » (bulle (i), forfaits proposés, aucun montant) ════

def _bloc_js(js, debut):
    j = js.index(debut)
    return js[j:js.index("\n    },", j)]


def test_ecran_carte_essai_termine_sans_montant():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    bloc = _bloc_js(js, "essaiCarte() {")
    assert "Votre essai gratuit est terminé" in bloc and "this.iaPause()" in bloc
    assert 'this.offre402.code === "essai_termine"' in bloc
    assert "€" not in bloc and "budget" not in bloc.lower()
    pause = _bloc_js(js, "iaPause() {")
    assert '"ia_pause" in u' in pause and 'u.trial_state === "expired"' in pause
    assert 'code: (d && typeof d === "object" && !Array.isArray(d) && d.code) || ""' in js
    assert 'motif: (d && typeof d === "object" && !Array.isArray(d) && d.motif) || ""' in js
    assert "Essai gratuit terminé : choisissez un forfait pour lancer une analyse" in js


# ═══ 6. Pages juridiques : CGV 3.5, page Sécurité, pages servies synchronisées ══════════════════

def _build_legal():
    spec = importlib.util.spec_from_file_location("build_legal_test", ROOT / "scripts" / "build_legal.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pages_juridiques_servies_synchronisees_avec_leur_source():
    b = _build_legal()
    for src, dst, title in b.PAGES:
        md = (ROOT / "docs" / "legal" / src).read_text(encoding="utf-8")
        attendu = b.TEMPLATE.replace("{title}", title).replace("{content}", b.md_to_html(md))
        servi = (ROOT / "app" / "static" / "legal" / dst).read_text(encoding="utf-8")
        assert servi == attendu, f"{dst} n'est pas à jour : lancer python scripts/build_legal.py"


def test_cgv_article_3_5_essai_gratuit(client):
    md = (ROOT / "docs" / "legal" / "cgv.md").read_text(encoding="utf-8")
    art = md[md.index("### 3.5. Essai gratuit"):md.index("## 4. Paiement")]
    for t in ("dans les limites suivantes, valables pour **toute la durée de l'essai**",
              "**trente (30) analyses d'appel d'offres au total** (et non par mois)",
              "**quinze (15) questions par jour** posées sur les dossiers",
              "une **limite d'usage** des fonctions d'intelligence artificielle destinée à protéger le Service",
              "un traitement déjà commencé (lecture et analyse d'un dossier, rédaction) est toujours mené à son terme",
              "Ces limites ne s'appliquent pas aux formules payantes",
              "À la fin de l'essai, les **fonctions d'intelligence artificielle** du Service **ne sont plus "
              "accessibles sans formule payante**"):
        assert t in art, t
    assert "30 analyses d'appel d'offres par mois" not in art
    assert "€" not in art and "budget" not in art.lower()         # le budget de l'essai n'est jamais cité
    # Le reste de l'article ne change pas.
    assert "L'essai est limité à **un (1) par Client**" in art and "usage abusif" in art
    assert "l'accès aux analyses est **suspendu**" in art
    html = client.get("/cgv").text
    for t in ("<strong>quinze (15) questions par jour</strong>", "au total</strong> (et non par mois)",
              "<strong>ne sont plus accessibles sans formule payante</strong>"):
        assert t in html, t
    assert "analyses d&#x27;appel d&#x27;offres par mois</strong>)" not in html


def test_page_securite_puce_strict_necessaire(client):
    html = client.get("/securite").text
    puce = ("<li><strong>Strict nécessaire</strong> : on transmet à l'IA le dossier du marché que vous analysez "
            "(lu en entier, pour ne rien manquer) et, pour la rédaction, les extraits utiles de vos documents. "
            "Jamais l'ensemble de votre espace. Les noms de vos salariés sont remplacés par des étiquettes "
            "avant tout envoi.</li>")
    assert puce in html
    assert "on ne transmet au modèle que les extraits utiles" not in html
    # Les autres engagements ne bougent pas (les corrections liées à Mistral attendent son activation).
    assert "jamais utilisés pour entraîner un modèle d'IA" in html
    assert "encadrée par ses conditions applicables à l'API" in html
    assert "<strong>Transferts encadrés</strong>" in html


# ═══ 7. Inscription par Google : un essai de 30 jours, qui se termine comme les autres ══════════

@pytest.fixture
def google_essai(monkeypatch, client):
    """Google SIMULÉ (aucun appel réseau), comme dans test_secu5_durcissement."""
    from app.core.config import get_settings
    from app.routers import google_auth as ga
    from tests.test_secu5_durcissement import _FakeGoogle
    s = get_settings()
    monkeypatch.setattr(s, "GOOGLE_CLIENT_ID", "client-id-de-test")
    monkeypatch.setattr(s, "GOOGLE_CLIENT_SECRET", "client-secret-de-test")
    fake = _FakeGoogle(f"g_essai_{uuid.uuid4().hex[:8]}@exemple-test.fr")
    monkeypatch.setattr(ga, "requests", fake)
    client.cookies.clear()
    yield fake
    client.cookies.clear()


def _connexion_google(client):
    from urllib.parse import parse_qs, urlparse
    from tests.test_secu5_durcissement import _callback, _login
    state, morsel, _ = _login(client)
    r = _callback(client, state, nonce=morsel.value)
    assert r.status_code in (302, 307), r.text
    code = parse_qs(urlparse(r.headers["location"]).fragment)["gcode"][0]
    ex = client.post("/api/auth/google/exchange", json={"code": code})
    assert ex.status_code == 200, ex.text
    return {"Authorization": f"Bearer {ex.json()['access_token']}"}


def test_compte_cree_par_google_a_un_essai_de_30_jours_qui_se_termine(client, google_essai):
    from app.core import quota
    h = _connexion_google(client)
    u = _user(google_essai.email)
    fin = quota._as_utc(u.trial_ends_at)
    assert fin is not None, "un compte créé par Google doit avoir une date de fin d'essai"
    restant = fin - datetime.now(timezone.utc)
    assert timedelta(days=29, hours=23) < restant <= timedelta(days=30)
    assert quota._trial_state(u) == "active" and quota.essai_actif(u)
    us = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert us["quota_scope"] == "essai" and us["analyses_limit"] == 30 and us["ia_pause"] is None
    # Fin de l'essai : même refus qu'un compte inscrit par mot de passe, avant tout appel et tout débit.
    _set(google_essai.email, email_verified=True)
    _expirer(google_essai.email)
    _termine(client.post("/api/sourcing/analyze", headers=h, json={"tender": TENDER}))
    us = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert us["ia_pause"] == "essai" and us["analyses_remaining"] == 0
    assert (_user(google_essai.email).trial_analyses_used or 0) == 0


def test_compte_deja_en_base_connecte_par_google_inchange(client, google_essai, monkeypatch):
    """Un compte historique (sans essai) qui se connecte par Google n'en reçoit pas un : rien n'est
    modifié pour les comptes déjà en base."""
    from app.core import quota
    from app.models import PlanType
    email, _h = _inscrire(client)
    _set(email, trial_ends_at=None, plan=PlanType.starter)
    google_essai.email = email
    h = _connexion_google(client)
    u = _user(email)
    assert u.trial_ends_at is None and quota._trial_state(u) == "none" and not quota.essai_termine(u)
    _fake(monkeypatch, lambda kw: ("Le 3 mars.", "end_turn"))
    pid = _project(client, h, "Marché historique Google")
    _set_analysis(pid, ANALYSE)
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"})
    assert r.status_code == 200, r.text


# ═══ 8. Compte déjà passé par le paiement : même pause, sans parler d'un essai ═════════════════

def test_ancien_abonne_sans_forfait_actif_message_sans_essai(client, auth, monkeypatch):
    """Abonnement résilié ou paiement en échec : le webhook Stripe remet le forfait à « starter ».
    Même pause que la fin de l'essai (décision du 12/10/2026), mais le message ne parle pas d'essai."""
    import stripe
    from types import SimpleNamespace
    from app.core import quota
    from app.models import PlanType, User
    monkeypatch.setattr(stripe.Subscription, "list", lambda *a, **k: SimpleNamespace(data=[]))
    h = auth["headers"]
    _set(auth["email"], plan=PlanType.starter, trial_ends_at=_hier(), stripe_customer_id="cus_test_ancien")
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": TENDER})
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["code"] == "essai_termine" and d["motif"] == "forfait", d
    assert d["message"].startswith("Aucun forfait n'est actif sur votre compte")
    assert "essai" not in d["message"].lower() and "restent accessibles" in d["message"]
    _sans_montant(r.json())
    us = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert us["ia_pause"] == "forfait"
    st = client.get("/api/stripe/status", headers=h).json()
    assert st["ia_pause"] == "forfait"
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        with pytest.raises(HTTPException) as e:
            quota.consume_analysis(u, db)
        assert e.value.detail["motif"] == "forfait" and "essai" not in e.value.detail["message"].lower()
    finally:
        db.close()
    # Il reprend un forfait : tout repart, comme avant.
    _set(auth["email"], plan=PlanType.pro, analyses_used_this_month=0, analyses_period=quota._period())
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        quota.exiger_ia(u, db)
        assert quota.usage(u, db)["ia_pause"] is None
    finally:
        db.close()


def test_essai_termine_sans_paiement_motif_essai(client, auth):
    h = auth["headers"]
    _expirer(auth["email"])
    d = _termine(client.post("/api/sourcing/analyze", headers=h, json={"tender": TENDER}))
    assert d["motif"] == "essai"
    assert client.get("/api/agent/stats", headers=h).json()["usage"]["ia_pause"] == "essai"
    assert client.get("/api/stripe/status", headers=h).json()["ia_pause"] == "essai"


def test_ecran_aucun_forfait_actif_sans_parler_d_essai():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "app.html").read_text(encoding="utf-8")
    bloc = _bloc_js(js, "essaiCarte() {")
    assert '"Aucun forfait actif"' in bloc and "Aucun forfait n'est actif sur votre compte." in bloc
    assert "Aucun forfait actif : choisissez un forfait pour lancer une analyse" in js
    assert "plan.ia_pause==='forfait' ? 'Aucun forfait actif' : 'Essai terminé — abonnez-vous'" in html


# ═══ 9. Veille automatique activée pendant l'essai : « En pause » à l'écran, pas « Active » ═══

def test_veille_automatique_en_pause_a_l_ecran(client, auth):
    from app.models import PlanType
    h = auth["headers"]
    _set(auth["email"], amont_alerts_enabled=True)
    try:
        a = client.get("/api/amont/auto", headers=h).json()
        assert a == {"enabled": True, "en_pause": False, "motif": None}       # essai en cours : servie
        _expirer(auth["email"])
        a = client.get("/api/amont/auto", headers=h).json()
        assert a == {"enabled": True, "en_pause": True, "motif": "essai"}     # choix gardé, en pause
        assert _user(auth["email"]).amont_alerts_enabled is True
        _set(auth["email"], stripe_customer_id="cus_test_veille")
        assert client.get("/api/amont/auto", headers=h).json()["motif"] == "forfait"
        # Un forfait est choisi : la veille reprend seule, sans rien réactiver.
        _set(auth["email"], plan=PlanType.pro)
        assert client.get("/api/amont/auto", headers=h).json() == {"enabled": True, "en_pause": False,
                                                                   "motif": None}
        # Compte historique sans essai : jamais en pause.
        _set(auth["email"], plan=PlanType.starter, trial_ends_at=None)
        assert client.get("/api/amont/auto", headers=h).json()["en_pause"] is False
    finally:
        _set(auth["email"], amont_alerts_enabled=False)


def test_ecran_veille_automatique_en_pause():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "app.html").read_text(encoding="utf-8")
    assert '<template v-if="amont.auto && amont.autoPause"><span class="pill neutral" style="font-size:10px">En pause</span>' in html
    assert '<span class="tip-b" role="tooltip">{{ amontPauseInfo() }}</span>' in html
    assert '<span v-else-if="amont.auto" class="pill go" style="font-size:10px">Active</span>' in html
    load = _bloc_js(js, "async loadAmont() {")
    assert 'this.amont.autoPause = a.en_pause ? (a.motif || "essai") : "";' in load
    info = _bloc_js(js, "amontPauseInfo() {")
    assert "Votre essai gratuit est terminé : la veille automatique reprend dès que vous choisissez un forfait." in info
    assert "€" not in info
