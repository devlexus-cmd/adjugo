"""
Garde-fou de l'ESSAI GRATUIT (chantier E), et rien pour les forfaits payants.

 • 30 analyses sur TOUTE la durée de l'essai : un essai à cheval sur deux mois n'en donne plus 60 ;
 • questions-réponses : 15 par jour pendant l'essai (50 / 120 inchangés pour Pro / Business) ;
 • budget IA de l'essai mesuré appel par appel (coût réel au tarif public), rattaché au compte de
   facturation (propriétaire de l'organisation) : refus propre AVANT l'opération quand il est atteint,
   une opération lancée sous le budget qui le dépasse en cours de route va TOUJOURS au bout ;
 • forfaits payants : mêmes plafonds qu'avant, jamais bridés ; alerte interne (journal + route
   d'administration) sans blocage ;
 • aucun montant dans les réponses destinées au client.
Aucun appel réseau ni IA réel : le fournisseur IA est simulé.
"""
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException

from app.services import llm
from tests.test_redaction_socle0 import (FakeLLM, _Resp, _Usage, _db, _user_id, _company, _set_analysis,
                                         _atelier, _attendre_tache, _memoire_answer)
from tests.test_redaction_socle0 import _project as _projet_atelier
from tests.test_lecture_integrale import _gros_dossier, _petit_dossier, _answer, _project, _wait


# ── Outils ──────────────────────────────────────────────────────────────────────────────────

def _user(email):
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        db.expunge(u)
        return u
    finally:
        db.close()


def _set(email, **vals):
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        for k, v in vals.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def _cout_essai(uid, cout):
    """Coût IA déjà engagé pendant l'essai par ce compte (ligne usage_ia du mois)."""
    from app.models import UsageIA
    from app.services import budget_ia
    budget_ia.vider()
    db = _db()
    try:
        per = datetime.now(timezone.utc).strftime("%Y-%m")
        row = db.query(UsageIA).filter(UsageIA.compte == f"u{uid}", UsageIA.periode == per,
                                       UsageIA.essai.is_(True)).first()
        if row is None:
            row = UsageIA(compte=f"u{uid}", billing_user_id=uid, periode=per, essai=True, cout_eur=0.0,
                          appels=0, tokens_entree=0, tokens_sortie=0)
            db.add(row)
        row.cout_eur = float(cout)
        db.commit()
    finally:
        db.close()


def _cout_paye(uid, cout):
    from app.models import UsageIA
    db = _db()
    try:
        per = datetime.now(timezone.utc).strftime("%Y-%m")
        row = db.query(UsageIA).filter(UsageIA.compte == f"u{uid}", UsageIA.periode == per,
                                       UsageIA.essai.is_(False)).first()
        if row is None:
            db.add(UsageIA(compte=f"u{uid}", billing_user_id=uid, periode=per, essai=False, cout_eur=float(cout),
                           appels=1, tokens_entree=0, tokens_sortie=0))
        else:
            row.cout_eur = float(row.cout_eur or 0) + float(cout)
        db.commit()
    finally:
        db.close()


def _fake(monkeypatch, answer, usage=None):
    """Faux fournisseur ; `usage(kwargs)` → (tokens d'entrée, tokens de sortie) de chaque réponse."""
    class Fake(FakeLLM):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            text, stop = self._answer(kwargs)
            i, o = usage(kwargs) if usage else (100, 50)
            return _Resp(text, stop, usage=_Usage(i, o))
    fake = Fake(answer)
    monkeypatch.setattr(llm, "client", lambda: fake)
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    return fake


_MONTANT = re.compile(r"€|\$|\b(eur|euros?|co[uû]ts?|cout_\w*|\w*_eur|budget\w*|dollars?|usd)\b")


def _sans_montant(payload):
    """Aucun montant, aucune clé de coût ou de budget dans une réponse destinée au client."""
    txt = json.dumps(payload, ensure_ascii=False).lower()
    m = _MONTANT.search(txt)
    assert m is None, (m.group(0) if m else "", txt[:400])


# ═══ 1. 30 analyses sur toute la durée de l'essai (et non 30 par mois civil) ════════════════════

def test_essai_a_cheval_sur_deux_mois_30_analyses_au_total(client, auth, monkeypatch):
    from app.core import quota
    from app.models import User
    mois = {"v": "2026-10"}
    monkeypatch.setattr(quota, "_period", lambda: mois["v"])
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert quota.essai_actif(u) and quota._limit(u) == 30
        for _ in range(18):                              # fin octobre : 18 analyses
            quota.consume_analysis(u, db)
        mois["v"] = "2026-11"                            # l'essai continue en novembre
        db.refresh(u)
        assert quota.usage(u, db)["analyses_used"] == 18          # pas remis à zéro
        assert quota.usage(u, db)["analyses_remaining"] == 12
        for _ in range(12):
            quota.consume_analysis(u, db)
        with pytest.raises(HTTPException) as e:          # 31e : refusée (avant : 30 de plus en novembre)
            quota.consume_analysis(u, db)
        assert e.value.status_code == 402 and "essai" in e.value.detail and "30 sur 30" in e.value.detail
        db.refresh(u)
        assert u.trial_analyses_used == 30 and u.analyses_used_this_month == 12
        # Une analyse remboursée (l'IA est tombée) est rendue à l'essai, même après le changement de mois.
        quota.refund_analysis(u, db)
        db.refresh(u)
        assert u.trial_analyses_used == 29 and quota.usage(u, db)["analyses_remaining"] == 1
        quota.consume_analysis(u, db)
    finally:
        db.close()


def test_compteur_d_essai_reglable_et_affiche_sur_30(client, auth, monkeypatch):
    from app.core import quota
    h = auth["headers"]
    st = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert st["quota_scope"] == "essai" and st["analyses_limit"] == 30 and st["analyses_remaining"] == 30
    assert st["trial_questions_per_day"] == 15 and st["trial_usage"] == "ok"
    _sans_montant(st)
    monkeypatch.setattr(quota.settings, "TRIAL_ANALYSES", 12)
    st = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert st["analyses_limit"] == 12
    assert client.get("/api/stripe/status", headers=h).json()["analyses_limit"] == 12


# ═══ 2. Questions : 15 par jour pendant l'essai ══════════════════════════════════════════════════

def test_questions_15_par_jour_pendant_l_essai(client, auth, monkeypatch):
    from app.core import quota
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        assert quota.questions_limit(u, db) == 15
        for _ in range(15):
            quota.reserve_question(u, db)
        with pytest.raises(HTTPException) as e:
            quota.reserve_question(u, db)
        assert e.value.status_code == 429 and "15 par organisation et par jour" in e.value.detail
        monkeypatch.setattr(quota.settings, "TRIAL_QUESTIONS_PAR_JOUR", 20)   # réglable
        assert quota.questions_limit(u, db) == 20
        monkeypatch.setattr(quota.settings, "QUESTIONS_PAR_JOUR", 4)          # borne globale : la plus basse
        assert quota.questions_limit(u, db) == 4
    finally:
        db.close()


# ═══ 3. Budget atteint : refus propre AVANT l'opération ═══════════════════════════════════════════

def test_budget_atteint_refus_avant_toute_operation(client, auth, monkeypatch):
    from app.models import Job
    fake = _fake(monkeypatch, _answer)
    h = auth["headers"]
    uid = _user_id(auth["email"])
    pid = _project(client, h, "Marché budget atteint")
    _cout_essai(uid, 14.99)                              # 15 € de budget : plus rien ne passe
    avant = _user(auth["email"])

    # Import et analyse du dossier : refusé avant la lecture par l'IA, rien n'est débité.
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", _petit_dossier(), "application/zip")})
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["code"] == "essai_limite_usage" and "limite d'usage" in d["message"] and "forfait" in d["message"]
    _sans_montant(r.json())
    apres = _user(auth["email"])
    assert apres.trial_analyses_used == avant.trial_analyses_used
    assert (apres.analyses_used_this_month or 0) == (avant.analyses_used_this_month or 0)

    # Analyse d'un avis : même refus, avant la récupération du dossier et avant l'IA.
    tender = {"objet": "Test", "provenance": {"source": "BOAMP", "source_url": "https://www.boamp.fr/x",
                                              "official_ref": "x"}}
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": tender})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"

    # Question sur un dossier : refusée avant d'être comptée (aucune réservation laissée).
    _set_analysis(pid, {"summary": "s", "details": {"intitule_marche": "Marché budget atteint"},
                        "dce_excerpt": "Date limite le 3 mars."})
    db = _db()
    try:
        n0 = db.query(Job).filter(Job.user_id == uid, Job.kind == "question_dossier").count()
    finally:
        db.close()
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"
    db = _db()
    try:
        assert db.query(Job).filter(Job.user_id == uid, Job.kind == "question_dossier").count() == n0
    finally:
        db.close()

    # Chiffrage (hors quota) : refusé aussi.
    _set_analysis(pid, {"summary": "s", "details": {"intitule_marche": "Marché budget atteint"}})
    r = client.post(f"/api/chiffrage/{pid}/estimate", headers=h, json={"distance_km": 10})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"
    assert fake.calls == []                              # aucun appel à l'IA

    # L'écran : état « atteint » sans montant ; le compteur dit pourquoi.
    st = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert st["trial_usage"] == "atteint"
    _sans_montant(st)
    _sans_montant(client.get("/api/stripe/status", headers=h).json())


def test_operation_trop_lourde_pour_ce_qui_reste_les_questions_restent_possibles(client, auth, monkeypatch):
    _fake(monkeypatch, lambda kw: ("Le 3 mars.", "end_turn"))
    h = auth["headers"]
    uid = _user_id(auth["email"])
    pid = _project(client, h, "Marché presque au bout")
    _set_analysis(pid, {"summary": "s", "details": {"intitule_marche": "Marché presque au bout"},
                        "dce_excerpt": "REGLEMENT. Date limite le 3 mars."})
    _cout_essai(uid, 14.85)          # reste ≈ 0,15 € : plus de place pour une analyse, assez pour une question
    tender = {"objet": "Test", "provenance": {"source": "BOAMP", "source_url": "https://www.boamp.fr/x",
                                              "official_ref": "x"}}
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": tender})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"
    assert "dépasserait la limite d'usage" in r.json()["detail"]["message"]
    _sans_montant(r.json())
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Date limite ?"})
    assert r.status_code == 200, r.text
    st = client.get("/api/agent/stats", headers=h).json()["usage"]
    assert st["trial_usage"] == "proche"
    _sans_montant(st)


def test_atelier_refuse_avant_de_lancer_quand_le_budget_est_atteint(client, auth, monkeypatch):
    from app.models import Job
    fake = _fake(monkeypatch, _memoire_answer("Texte de la partie."))
    h = auth["headers"]
    _company(client, h, team=[])
    pid = _projet_atelier(client, h, "Marché atelier essai")
    _set_analysis(pid, {"details": {"intitule_marche": "Marché atelier essai"}})
    st = _atelier(client, h, pid)
    uid = _user_id(auth["email"])
    _cout_essai(uid, 14.9)
    db = _db()
    try:
        n0 = db.query(Job).filter(Job.user_id == uid).count()
    finally:
        db.close()
    r = client.post(f"/api/atelier/{pid}/sections/{st['sections'][0]['id']}/rediger", headers=h, json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"
    _sans_montant(r.json())
    db = _db()
    try:
        assert db.query(Job).filter(Job.user_id == uid).count() == n0      # aucune tâche créée
    finally:
        db.close()
    assert fake.calls == [] and (_user(auth["email"]).trial_analyses_used or 0) == 0
    # Sous le budget, la même rédaction part (le garde-fou ne bride pas l'essai avant la limite).
    _cout_essai(uid, 1.0)
    r = client.post(f"/api/atelier/{pid}/sections/{st['sections'][0]['id']}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    assert _attendre_tache(client, h, pid, r.json()["tache"]["id"])["status"] == "done"


# ═══ 4. Lancée sous le budget, l'opération va au bout même si elle le dépasse ═══════════════════

def test_operation_lancee_sous_le_budget_va_au_bout(client, auth, monkeypatch):
    from app.services import analysis as an, budget_ia
    from app.core import quota
    monkeypatch.setattr(an, "ocr_available", lambda: False)
    monkeypatch.setattr(quota.settings, "TRIAL_AI_BUDGET_EUR", 2.0)
    # Chaque appel coûte cher (500 000 tokens d'entrée) : le dossier lu en deux temps dépasse 2 €.
    fake = _fake(monkeypatch, _answer, usage=lambda kw: (500_000, 2000))
    h = auth["headers"]
    uid = _user_id(auth["email"])
    pid = _project(client, h, "Gros dossier sous le budget")
    z, codes, _total, _p = _gros_dossier()
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", z, "application/zip")})
    assert r.status_code == 202, r.text                 # admise : estimation sous le budget
    st = _wait(client, h, pid)
    assert st["etat"] == "termine", st                  # jamais un dossier à moitié lu
    sent = fake.sent()
    for code in codes:
        assert f"FIN-PIECE-{code}" in sent, code
    synth = [k for k in fake.calls if "Tu lis UNE pièce" not in llm._flatten_content(k.get("system"))]
    assert len(synth) == 1 and len(fake.calls) >= 5
    assert budget_ia.vider()
    db = _db()
    try:
        from app.models import User
        u = db.get(User, uid)
        assert budget_ia.cout_essai_eur(db, u) > 2.0    # le budget est dépassé… par l'opération finie
    finally:
        db.close()
    # La suivante est refusée avant de commencer, proprement.
    r = client.post("/api/sourcing/ask", headers=h, json={"project_id": pid, "question": "Compacteur ?"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage"
    _sans_montant(client.get("/api/agent/stats", headers=h).json()["usage"])


# ═══ 5. Mesure : coût réel par appel, rattaché au compte de facturation ═════════════════════════

def test_cout_mesure_par_appel_et_rattache_au_proprietaire_de_l_organisation(client, auth, monkeypatch):
    from app.core.security import hash_password
    from app.models import User, UsageIA
    from app.services import budget_ia
    _fake(monkeypatch, lambda kw: ("ok", "end_turn"), usage=lambda kw: (1_000_000, 100_000))
    owner = _user(auth["email"])
    db = _db()
    try:
        m = User(email=f"membre_{owner.id}@test.fr", hashed_password=hash_password("motdepasse123"),
                 full_name="Membre", org_id=owner.org_id, email_verified=True)
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    with llm.tenant_scope(mid):                          # appel fait par un MEMBRE de l'organisation
        llm.messages_create(model="claude-sonnet-4-6", max_tokens=5, messages=[])
    with llm.tenant_scope(owner.id), budget_ia.mutualise("veille amont planifiée"):
        llm.messages_create(model="claude-sonnet-4-6", max_tokens=5, messages=[])   # mutualisé
    with llm.tenant_scope("dce:ach:7"):
        llm.messages_create(model="claude-sonnet-4-6", max_tokens=5, messages=[])
    with llm.tenant_scope("dce:203.0.113.9"):
        llm.messages_create(model="claude-sonnet-4-6", max_tokens=5, messages=[])
    assert budget_ia.vider()
    db = _db()
    try:
        per = datetime.now(timezone.utc).strftime("%Y-%m")
        row = db.query(UsageIA).filter(UsageIA.compte == f"u{owner.id}", UsageIA.periode == per).one()
        # Sonnet 4.6 : 1 M × 3 $ + 0,1 M × 15 $ = 4,5 $ × 0,85 = 3,825 € — porté par le propriétaire, essai.
        assert row.essai is True and row.billing_user_id == owner.id and row.appels == 1
        assert row.cout_eur == pytest.approx(3.825, rel=1e-6)
        comptes = {r.compte for r in db.query(UsageIA).filter(UsageIA.periode == per).all()}
        assert {"plateforme", "acheteur:7", "acheteur:anonyme"} <= comptes
        assert not any("203.0.113.9" in c for c in comptes)            # jamais d'adresse IP en base
        u = db.get(User, owner.id)
        assert budget_ia.cout_essai_eur(db, u) == pytest.approx(3.825, rel=1e-6)
    finally:
        db.close()


def test_tarifs_des_modeles_retenus():
    from app.services import tarifs_ia as t
    k = t.taux_usd_eur()
    # Sonnet 5.5 : 2 $ / 10 $, cache lu 0,10 $, cache écrit 2,50 $.
    assert t.cout_eur("claude-sonnet-5-5", 1_000_000, 100_000, 1_000_000, 1_000_000) == pytest.approx(
        (2 + 1 + 0.10 + 2.50) * k, rel=1e-6)
    # Haiku 5.5 : prix de la requête longue au-delà de 100 000 tokens d'entrée (cache compris).
    assert t.cout_eur("claude-haiku-5-5", 50_000, 0) == pytest.approx(0.005 * k, rel=1e-6)
    assert t.cout_eur("claude-haiku-5-5", 60_000, 0, cache_lus=60_000) == pytest.approx(
        (0.06 * 0.50 + 0.06 * 0.05) * k, rel=1e-6)
    # Mistral Large 4 (identifiant exact), publié en euros ; l'alias « latest » au prix le plus haut.
    assert t.cout_eur("mistral-large-4", 1_000_000, 1_000_000) == pytest.approx(1.156 + 3.553, rel=1e-6)
    assert t.cout_eur("mistral-large-latest", 1_000_000, 0) == pytest.approx(1.156, rel=1e-6)
    # Modèle inconnu : compté au prix du plus cher (jamais sous-estimé).
    assert t.cout_eur("modele-inconnu-x", 1_000_000, 0) == pytest.approx(4.0 * k, rel=1e-6)


def test_point_d_acces_europeen_de_mistral_majore_de_10_pour_cent(monkeypatch):
    from app.services import tarifs_ia as t
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "MISTRAL_BASE_URL", "https://api.eu.mistral.ai/v1")
    assert t.cout_eur("mistral-large-4", 1_000_000, 0) == pytest.approx(1.156 * 1.1, rel=1e-6)


# ═══ 6. Forfaits payants : inchangés (non-régression), alerte interne sans blocage ══════════════

def test_forfaits_payants_memes_plafonds_qu_avant_et_jamais_bridés(client, auth, monkeypatch):
    from app.core import quota
    from app.models import User, PlanType
    from app.services import budget_ia
    uid = _user_id(auth["email"])
    for plan, analyses, questions in ((PlanType.pro, 30, 50), (PlanType.business, 100, 120)):
        _set(auth["email"], plan=plan, analyses_used_this_month=0, analyses_period=quota._period())
        db = _db()
        try:
            u = db.query(User).filter(User.email == auth["email"]).first()
            assert not quota.essai_actif(u)                       # l'essai n'existe plus pour un payant
            assert quota._limit(u) == analyses and quota.questions_limit(u, db) == questions
            _cout_paye(uid, 10_000.0)                             # coût IA énorme : aucun effet
            budget_ia.verifier(u, db, "analyse", 9_999.0)          # jamais de refus
            quota.consume_analysis(u, db)
            quota.reserve_question(u, db)
            us = quota.usage(u, db)
            assert us["analyses_limit"] == analyses and us["analyses_used"] == 1
            assert "trial_usage" not in us and "quota_scope" not in us
            # Au plafond du forfait : le comportement d'avant (402 « Quota d'analyses IA atteint … ce mois »).
            u.analyses_used_this_month = analyses
            db.commit()
            with pytest.raises(HTTPException) as e:
                quota.consume_analysis(u, db)
            assert e.value.status_code == 402 and "ce mois" in e.value.detail
        finally:
            db.close()
    # Compte historique (sans essai) : 5 analyses par mois, 15 questions, inchangé.
    _set(auth["email"], plan=PlanType.starter, trial_ends_at=None)
    u = _user(auth["email"])
    db = _db()
    try:
        assert quota._limit(u) == 5 and quota.questions_limit(u, db) == 15 and not quota.essai_actif(u)
    finally:
        db.close()


def test_alerte_interne_pour_un_forfait_payant_sans_blocage(client, auth, monkeypatch, caplog):
    from app.core import quota
    from app.models import User, PlanType, UsageIA
    from app.services import budget_ia
    _set(auth["email"], plan=PlanType.pro, analyses_used_this_month=0, analyses_period=quota._period())
    uid = _user_id(auth["email"])
    caplog.set_level(logging.WARNING, logger="adjugo")
    # Pro à 129,99 € : seuil d'alerte = 50 % → 65,00 €. Un mois à 70 € de coût réel.
    assert budget_ia.seuil_alerte_eur(_user(auth["email"])) == pytest.approx(65.0, abs=0.01)
    budget_ia.enregistrer_appel(uid, "claude-sonnet-4-6", 40.0, 1000, 100)
    assert budget_ia.vider()
    budget_ia.enregistrer_appel(uid, "claude-sonnet-4-6", 30.0, 1000, 100)
    assert budget_ia.vider()
    db = _db()
    try:
        row = db.query(UsageIA).filter(UsageIA.compte == f"u{uid}", UsageIA.essai.is_(False)).one()
        assert row.cout_eur == pytest.approx(70.0) and row.alerte_le is not None
        u = db.query(User).filter(User.email == auth["email"]).first()
        quota.consume_analysis(u, db)                            # aucun blocage
        quota.reserve_question(u, db)
    finally:
        db.close()
    alertes = [r for r in caplog.records if "ALERTE coût IA" in r.getMessage()]
    assert len(alertes) == 1 and f"u{uid}" in alertes[0].getMessage()
    budget_ia.enregistrer_appel(uid, "claude-sonnet-4-6", 5.0, 10, 10)        # une seule alerte par mois
    assert budget_ia.vider()
    assert len([r for r in caplog.records if "ALERTE coût IA" in r.getMessage()]) == 1

    # Route d'administration : visible au seul administrateur de la plateforme.
    h = auth["headers"]
    assert client.get("/api/admin/usage-ia", headers=h).status_code == 403
    _set(auth["email"], is_admin=True)
    d = client.get("/api/admin/usage-ia", headers=h).json()
    p = next(x for x in d["forfaits_payants"] if x["compte"] == f"u{uid}")
    assert p["au_dela_du_seuil"] is True and p["alerte_le"] and p["cout_ia_mois_eur"] == pytest.approx(75.0)
    assert p["seuil_alerte_eur"] == pytest.approx(65.0, abs=0.01)
    assert client.get("/api/admin/usage-ia?periode=xx", headers=h).status_code == 422
    _set(auth["email"], is_admin=False)


def test_administration_voit_le_budget_consomme_par_chaque_essai(client, auth):
    from app.services import budget_ia
    uid = _user_id(auth["email"])
    _cout_essai(uid, 12.5)
    _set(auth["email"], trial_analyses_used=7)
    # Le client, lui, ne voit qu'un état : jamais le montant.
    st = client.get("/api/agent/stats", headers=auth["headers"]).json()["usage"]
    assert st["trial_usage"] == "proche" and st["analyses_used"] == 7
    _sans_montant(st)
    _set(auth["email"], is_admin=True)
    try:
        d = client.get("/api/admin/usage-ia", headers=auth["headers"]).json()
        e = next(x for x in d["essais"] if x["compte"] == f"u{uid}")
        assert e["cout_ia_eur"] == pytest.approx(12.5) and e["budget_eur"] == budget_ia.budget_essai_eur()
        assert e["analyses_utilisees"] == 7 and e["analyses_comprises"] == 30 and e["etat"] == "proche"
    finally:
        _set(auth["email"], is_admin=False)


# ═══ 7. Écrans : compteur sur 30, carte sobre, invitation aux forfaits, sans montant ═════════════

def test_ecrans_compteur_d_essai_et_invitation_aux_forfaits():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "app", "static", "app.js"), encoding="utf-8").read()
    html = open(os.path.join(root, "app", "static", "app.html"), encoding="utf-8").read()
    assert '" (essai gratuit)"' in js and 'u.quota_scope === "essai"' in js
    assert "Votre essai a atteint sa limite d'usage" in js and "Votre essai approche de sa limite d'usage" in js
    assert "if (r.status === 402) this.offre402" in js and 'this.go("billing")' in js
    assert "30 analyses IA pendant l'essai" in html and "30 analyses IA / mois</li><li>Aucune carte" not in html
    i = html.index('v-if="essaiCarte"')
    carte = html[i:html.index("</div>\n\n", i)]
    assert 'class="tip"' in carte and "Voir les forfaits" in carte          # bulle (i), forfaits proposés
    for m in ("€", "budget", "coût"):
        assert m not in carte
    # Le texte de la carte (côté script) ne contient aucun montant.
    j = js.index("essaiCarte() {")
    bloc = js[j:js.index("\n    },", j)]
    assert "€" not in bloc and "budget" not in bloc.lower()


# ═══ 8. Migration (SQLite : à neuf, sur une base « production » existante, retour arrière) ═════

def test_migration_essai_a_neuf_existante_et_retour_arriere(tmp_path):
    import sqlalchemy as sa
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "essai.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=root, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    run("upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    insp = sa.inspect(eng)
    assert "usage_ia" in insp.get_table_names()
    assert "trial_analyses_used" in {c["name"] for c in insp.get_columns("users")}
    # Base « production » d'avant : ni table ni colonne, un compte en essai qui a déjà 7 analyses ce mois.
    with eng.begin() as cn:
        cn.execute(sa.text("DROP TABLE usage_ia"))
        cn.execute(sa.text("ALTER TABLE users DROP COLUMN trial_analyses_used"))
        cn.execute(sa.text("INSERT INTO users (email, hashed_password, full_name, analyses_used_this_month, "
                           "trial_ends_at) VALUES ('e@t.fr', 'x', 'E', 7, :f)"),
                   {"f": datetime.now(timezone.utc) + timedelta(days=10)})
        cn.execute(sa.text("INSERT INTO users (email, hashed_password, full_name, analyses_used_this_month) "
                           "VALUES ('h@t.fr', 'x', 'H', 3)"))
    eng.dispose()
    run("stamp", "t4u5redactionv2b")
    run("upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    with eng.connect() as cn:
        rows = dict(cn.execute(sa.text("SELECT email, trial_analyses_used FROM users")).fetchall())
    assert rows["e@t.fr"] == 7                           # rien n'est offert en plus à l'essai en cours
    assert rows["h@t.fr"] in (None, 0)
    assert "usage_ia" in sa.inspect(eng).get_table_names()
    uq = {tuple(u["column_names"]) for u in sa.inspect(eng).get_unique_constraints("usage_ia")}
    assert ("compte", "periode", "essai") in uq
    eng.dispose()
    run("upgrade", "head")                               # rejouée : aucun effet, aucune erreur
    run("downgrade", "t4u5redactionv2b")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    insp = sa.inspect(eng)
    assert "usage_ia" not in insp.get_table_names()
    assert "trial_analyses_used" not in {c["name"] for c in insp.get_columns("users")}
    eng.dispose()
    run("upgrade", "head")
