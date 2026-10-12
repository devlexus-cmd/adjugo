"""
Fusion du routage par tâche (chantier R) et du garde-fou de l'essai gratuit (chantier E).

Le budget de l'essai compte EXACTEMENT le coût que calcule le cost_meter du routage : modèle
réellement appelé (Mistral Large 4, Claude Sonnet 5.5), point d'accès réellement utilisé (UE : +10 %),
cache (lecture ; écriture d'une heure de la rédaction), secours (une réponse coupée puis reprise par
l'autre fournisseur : les deux essais sont facturés, les deux sont comptés). Les estimations faites
avant une opération suivent la même route (modèle, secours, réflexion, durée du cache) et la même
table des prix (app/services/tarifs_ia.py).
Aucun appel réseau ni IA réel : fournisseurs simulés (ceux de tests/test_routage_ia.py).
"""
import types
from datetime import datetime, timezone

import pytest

from app.services import llm
from tests.test_redaction_socle0 import _db, _user_id
from tests.test_routage_ia import _propre, _anthropic, _mistral, _mistral_ok, _B, _U  # noqa: F401 — _propre : remise à zéro


def _cout_essai_enregistre(uid) -> float:
    from sqlalchemy import func
    from app.models import UsageIA
    from app.services import budget_ia
    assert budget_ia.vider() is not False
    db = _db()
    try:
        per = datetime.now(timezone.utc).strftime("%Y-%m")
        return float(db.query(func.coalesce(func.sum(UsageIA.cout_eur), 0.0)).filter(
            UsageIA.compte == f"u{uid}", UsageIA.periode == per, UsageIA.essai.is_(True)).scalar() or 0.0)
    finally:
        db.close()


def test_budget_de_l_essai_compte_le_cout_du_cost_meter_du_routage(client, auth, monkeypatch):
    from app.services import tarifs_ia
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "aucun")          # prix normal de Large 4
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    uid = _user_id(auth["email"])
    avant = _cout_essai_enregistre(uid)

    def mistral(url, payload):
        if len(m.calls) == 1:          # 1re analyse : réussie, 4 000 tokens relus dans le cache
            return _mistral_ok("{\"ok\": 1}", pt=10_000, ct=2_000, cached=4_000)
        return _mistral_ok("{\"tronq", finish="length", pt=20_000, ct=7_800)    # 2e : coupée → secours
    m = _mistral(monkeypatch, mistral)

    def anthropic(kw):
        if kw.get("max_tokens", 0) > 20_000:     # rédaction (réflexion adaptative) : cache d'une heure écrit
            return [_B("text", "Texte rédigé.")], "end_turn", _U(500, 4_000, cache_creation_input_tokens=100_000,
                                                                cache_read_input_tokens=0)
        return [_B("text", "{\"ok\": 2}")], "end_turn", _U(25_000, 3_000)
    fake = _anthropic(monkeypatch, anthropic)

    with llm.tenant_scope(uid), llm.cost_meter("fusion R+E", uid, log=False) as cm:
        r1 = llm.messages_create(tache="analyse", max_tokens=6000, temperature=0, system="s",
                                 messages=[{"role": "user", "content": "dossier"}])
        r2 = llm.messages_create(tache="analyse", max_tokens=6000, temperature=0, system="s",
                                 messages=[{"role": "user", "content": "dossier"}])
        llm.complete_ex("consigne", [llm.cached_text_block("dossier de l'acheteur " * 400),
                                     {"type": "text", "text": "partie 1"}], max_tokens=12_000, tache="redaction")
    assert r1.fournisseur == "mistral" and r1.zone == "ue"
    assert r2.fournisseur == "anthropic" and r2.bascule == "coupe"
    assert all(c["url"].startswith("https://api.eu.mistral.ai/") for c in m.calls) and len(fake.calls) == 2
    assert fake.calls[-1]["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    ue = 1.10
    attendu_usd = (
        (6_000 * 1.36 + 4_000 * 0.14 + 2_000 * 4.18) * ue           # Mistral UE, cache relu à 10 %
        + (20_000 * 1.36 + 7_800 * 4.18) * ue                        # Mistral coupée : facturée aussi
        + (25_000 * 2 + 3_000 * 10)                                  # secours Sonnet 5.5
        + (500 * 2 + 4_000 * 10 + 100_000 * 4.00)                    # rédaction : écriture d'une heure (2 × l'entrée)
    ) / 1e6
    s = cm.summary()
    assert s["appels"] == 4 and s["bascules_de_secours"] == 1 and s["reponses_coupees"] == 1
    assert s["tokens_cache_ecrits_1h"] == 100_000
    assert s["cout_estime_usd"] == pytest.approx(attendu_usd, abs=1e-5)
    assert s["cout_estime_eur"] == pytest.approx(attendu_usd * tarifs_ia.taux_usd_eur(), abs=1e-5)
    # Le budget de l'essai (relevé du compte facturé) a reçu le MÊME montant que le cost_meter.
    assert _cout_essai_enregistre(uid) - avant == pytest.approx(cm.cost_eur(), abs=1e-5)


def test_un_modele_renvoye_sans_tarif_est_compte_au_modele_de_la_route(monkeypatch):
    def create(**kw):
        return types.SimpleNamespace(content=[_B("text", "ok")], stop_reason="end_turn", stop_details=None,
                                     usage=_U(1_000_000, 0), model=modele_rendu["v"])
    modele_rendu = {"v": "nom-de-modele-imprevu"}
    monkeypatch.setattr(llm, "client", lambda: types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))
    with llm.cost_meter("a", log=False) as cm:
        llm.complete("s", "u", tache="questions")
    assert cm.cost_usd() == pytest.approx(2.0) and "claude-sonnet-5-5" in cm.summary()["par_modele"]
    modele_rendu["v"] = "claude-sonnet-4-6"                 # le fournisseur dit avoir servi un autre modèle
    with llm.cost_meter("b", log=False) as cm:
        llm.complete("s", "u", tache="questions")
    assert cm.cost_usd() == pytest.approx(3.0) and "claude-sonnet-4-6" in cm.summary()["par_modele"]


def test_plafond_de_sortie_estime_egal_au_plafond_envoye(monkeypatch):
    m = _mistral(monkeypatch)
    fake = _anthropic(monkeypatch)
    for tache in ("analyse", "redaction", "questions", "chiffrage"):
        r = llm.route(tache)
        llm.complete("s", "u", max_tokens=6000, tache=tache)
        envoye = (m.calls[-1]["payload"]["max_tokens"] if r.primaire.fournisseur == "mistral"
                  else fake.calls[-1]["max_tokens"])
        assert llm.plafond_sortie(r.primaire, r, 6000) == envoye, tache
    assert llm.plafond_sortie(llm.route("redaction").primaire, llm.route("redaction"), 6000) == 6000 * 13 // 10 + 8000
    assert llm.plafond_sortie(llm.route("analyse").primaire, llm.route("analyse"), 6000) == 7800


def test_estimations_de_l_essai_suivent_la_route(monkeypatch):
    from app.services import budget_ia, tarifs_ia
    from app.services.atelier import DOSSIER_COMMUN_MAX
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "aucun")
    _anthropic(monkeypatch)
    est = lambda modele, chars, sortie, **kw: tarifs_ia.estimer_eur(modele, chars, sortie, sortie_envoyee=True, **kw)  # noqa: E731

    # Sans clé Mistral : l'analyse part chez son secours, Sonnet 5.5 (le plus cher des deux est compté).
    sonnet = est("claude-sonnet-5-5", 110_000, 7_800)
    large4_ue = est("mistral-large-4", 110_000, 7_800, zone="ue")
    assert large4_ue < sonnet
    assert budget_ia.estimer("analyse") == pytest.approx(sonnet, abs=1e-6)

    # Mistral configuré, sans secours : Large 4 au point d'accès UE (+10 %).
    _mistral(monkeypatch)
    monkeypatch.setenv("LLM_TACHE_ANALYSE_SECOURS", "aucun")
    assert budget_ia.estimer("analyse") == pytest.approx(large4_ue, abs=1e-6)
    monkeypatch.setenv("MISTRAL_POINT_ACCES", "mondial")
    assert budget_ia.estimer("analyse") == pytest.approx(est("mistral-large-4", 110_000, 7_800), abs=1e-6)
    monkeypatch.delenv("MISTRAL_POINT_ACCES")
    monkeypatch.delenv("LLM_TACHE_ANALYSE_SECOURS")

    # Rédaction : Sonnet 5.5, réflexion adaptative (réserve de 8 000 tokens), cache écrit pour une heure ;
    # son secours Large 4 est moins cher.
    monkeypatch.setenv("LLM_TACHE_REDACTION_SECOURS", "aucun")
    premier = est("claude-sonnet-5-5", 40_000, 4_000 * 13 // 10 + 8_000,
                  caracteres_cache_ecrits=DOSSIER_COMMUN_MAX, ttl="1h")
    suivant = est("claude-sonnet-5-5", 40_000, 4_000 * 13 // 10 + 8_000, caracteres_cache_lus=DOSSIER_COMMUN_MAX)
    assert budget_ia.estimer_atelier(1) == pytest.approx(premier, abs=1e-6)
    assert budget_ia.estimer_atelier(3) == pytest.approx(premier + 2 * suivant, abs=1e-5)
    assert premier > est("claude-sonnet-5-5", 40_000, 13_200, caracteres_cache_ecrits=DOSSIER_COMMUN_MAX)

    # Retour arrière (LLM_ROUTAGE=ancien) : Sonnet 4.6, sans secours, plafond d'origine.
    monkeypatch.setenv("LLM_ROUTAGE", "ancien")
    assert budget_ia.estimer("analyse") == pytest.approx(est("claude-sonnet-4-6", 110_000, 6_000), abs=1e-6)
    # Tout forcé chez Anthropic : Sonnet 5.5 seul.
    monkeypatch.delenv("LLM_ROUTAGE")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert budget_ia.estimer("analyse") == pytest.approx(sonnet, abs=1e-6)


def test_estimation_d_un_gros_dossier_en_deux_temps_suit_la_route(monkeypatch):
    from app.services import budget_ia
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "aucun")
    _anthropic(monkeypatch)
    lecture = {"pieces": [{"nom": f"p{i}.pdf"} for i in range(10)]}
    plan = {"caracteres": 2_000_000, "budget_caracteres": 390_000}
    sans_mistral = budget_ia.estimer_import(lecture, plan)          # tout chez le secours Sonnet 5.5
    _mistral(monkeypatch)
    monkeypatch.setenv("LLM_TACHE_LECTURE_PIECES_SECOURS", "aucun")
    monkeypatch.setenv("LLM_TACHE_ANALYSE_SECOURS", "aucun")
    avec_mistral = budget_ia.estimer_import(lecture, plan)          # Large 4 au point d'accès UE
    assert 0 < avec_mistral < sans_mistral
    assert budget_ia.estimer_import(lecture, {"caracteres": 50_000, "budget_caracteres": 390_000}) < avec_mistral
