"""
Non-régression de l'audit SOURCING IA (02/07/2026). Tests PURS (aucun réseau) qui
verrouillent les invariants corrigés :

  P0  panne LLM réelle → analyze_dce_text PROPAGE (jamais de faux NO-GO facturé)
  P1  filtre CPV de l'estimation (chaîne "45211000" ≠ itérée caractère par caractère)
  P1  réponse Mistral tronquée ("length") normalisée en "max_tokens"
  P2  durée aberrante DECP/renewal → pas d'OverflowError (row ignoré)
  P2  verdict : nogo_threshold ≥ go_threshold n'efface pas la bande « à étudier »
  P2  département injecté (guillemet ODSQL) écarté par TenderCriteria
"""
from unittest.mock import patch
import pytest


def test_p0_panne_llm_propage_pas_de_faux_nogo():
    from app.services import llm
    from app.services.analysis import analyze_dce_text

    class _Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("panne fournisseur simulée (avant seuil disjoncteur)")

    with patch.object(llm, "_use_mistral", lambda: False), \
         patch.object(llm, "client", lambda: _Boom()):
        # Texte > 50 caractères pour dépasser le garde-fou « contenu insuffisant ».
        dce = "Objet du marché : rénovation de la toiture du groupe scolaire, lot unique."
        with pytest.raises(Exception):   # doit PROPAGER, pas retourner un no_go score 0
            analyze_dce_text(dce, {"name": "X"}, {}, lang_name="français")


def test_p1_cpv_chaine_non_iteree_caractere():
    # cpv="45211000" doit produire UN filtre "4521", pas "4","5","2","1","1".
    from app.services import decp
    captured = {}

    class _Resp:
        def json(self): return {"results": []}

    def _fake_get(url, params=None, **kw):
        captured["where"] = (params or {}).get("where", "")
        return _Resp()

    with patch.object(decp, "get_with_retry", _fake_get):
        decp._fetch("travaux", ["29"], cpv="45211000", per=10)
    where = captured.get("where", "")
    assert 'codecpv like "4521"' in where
    assert 'codecpv like "4"' not in where   # plus d'itération caractère par caractère


def test_p1_mistral_troncature_normalisee():
    from app.services import llm
    payload = {"choices": [{"message": {"content": "coupé"}, "finish_reason": "length"}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 2}}

    class _R:
        def raise_for_status(self): pass
        def json(self): return payload

    with patch.object(llm.httpx, "post", lambda *a, **k: _R()):
        resp = llm._mistral_create(model="x", messages=[{"role": "user", "content": "hi"}])
    assert resp.stop_reason == "max_tokens"   # "length" (Mistral) → "max_tokens" (contrat Anthropic)


def test_p2_duree_aberrante_pas_doverflow():
    from datetime import date, timedelta
    from app.services import decp
    today = date.today()
    notif = (today - timedelta(days=400)).isoformat()
    rows = [
        {"objet": "marché sain", "acheteur_id": "1", "datenotification": notif,
         "dureemois": 12, "lieuexecution_code": "29"},
        {"objet": "durée absurde", "acheteur_id": "2", "datenotification": notif,
         "dureemois": 999_999_999, "lieuexecution_code": "29"},
    ]
    with patch.object(decp, "_fetch", return_value=rows):
        out = decp.detect_renewals_decp("travaux", ["29"], {})   # ne doit pas lever d'OverflowError
    assert isinstance(out, dict) and "renewals" in out


def test_p2_verdict_bande_a_etudier_preservee():
    from app.routers.sourcing import _verdict
    # Profil incohérent : nogo (80) >= go (75). La bande « à étudier » doit survivre.
    gonogo = {"go_threshold": 75, "nogo_threshold": 80}
    assert _verdict(90, gonogo) == "go"
    assert _verdict(74, gonogo) == "a_etudier"   # avant : tombait à tort en "no_go"
    assert _verdict(50, gonogo) == "no_go"


def test_p2_departement_injecte_ecarte():
    from app.sourcing.base import TenderCriteria
    c = TenderCriteria(departements=['29" OR objet like "x', "29", "2A", "abc", "971"])
    assert c.departements == ["29", "2A", "971"]   # l'entrée d'injection est supprimée
