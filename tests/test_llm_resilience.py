"""
Robustesse de la couche IA : disjoncteur (circuit breaker) + plafond de tokens.

Ces garde-fous évitent qu'une API IA en panne ne bloque tous les workers de jobs
(martèlement) et qu'un emballement de coût ne passe inaperçu. Tests sans réseau :
on remplace le client Anthropic par un faux.
"""
import time
import pytest

from app.services import llm


class _FakeUsage:
    input_tokens = 10
    output_tokens = 20


class _FakeResp:
    usage = _FakeUsage()
    content = [type("B", (), {"text": "ok"})()]


def _reset():
    llm._CB["fails"] = 0
    llm._CB["open_until"] = 0.0
    llm.TOKENS.update(input=0, output=0, calls=0)
    llm._TENANT_TOKENS.clear()
    llm._TENANT_CB.clear()
    llm._LAT["counts"] = {b: 0 for b in llm._LAT_BUCKETS}
    llm._LAT["sum"] = 0.0
    llm._LAT["count"] = 0


def test_disjoncteur_souvre_apres_n_echecs(monkeypatch):
    _reset()
    monkeypatch.setattr(llm, "_CB_THRESHOLD", 3)
    monkeypatch.setattr(llm, "_CB_COOLDOWN", 60)

    class _Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("API down")

    monkeypatch.setattr(llm, "client", lambda: _Boom)

    # Les 3 premiers échecs propagent l'erreur d'origine et incrémentent le compteur.
    for _ in range(3):
        with pytest.raises(RuntimeError):
            llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    # Circuit désormais OUVERT → échec RAPIDE (LLMUnavailable), sans rappeler l'API.
    with pytest.raises(llm.LLMUnavailable):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    _reset()


def test_succes_referme_le_circuit(monkeypatch):
    _reset()
    llm._CB["fails"] = 2  # quelques échecs récents
    monkeypatch.setattr(llm, "client", lambda: type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _FakeResp())})
    }))
    resp = llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    assert resp is not None
    assert llm._CB["fails"] == 0           # compteur remis à zéro
    assert llm.TOKENS["calls"] == 1         # usage bien suivi
    assert llm.TOKENS["input"] == 10 and llm.TOKENS["output"] == 20
    _reset()


def test_plafond_tokens_bloque(monkeypatch):
    _reset()
    monkeypatch.setattr(llm, "_TOKEN_HARD_CAP", 100)
    llm.TOKENS["input"] = 80
    llm.TOKENS["output"] = 30   # 110 ≥ 100
    monkeypatch.setattr(llm, "client", lambda: type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _FakeResp())})
    }))
    with pytest.raises(llm.LLMUnavailable):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    _reset()


def _fake_client():
    return type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _FakeResp())})
    })


def test_tokens_attribues_par_tenant(monkeypatch):
    _reset()
    monkeypatch.setattr(llm, "client", _fake_client)
    with llm.tenant_scope("tenantA"):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    with llm.tenant_scope("tenantB"):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    assert llm.tenant_usage("tenantA") == 60   # 2 appels × 30 tokens
    assert llm.tenant_usage("tenantB") == 30   # isolé
    _reset()


def test_plafond_par_tenant_isole_le_voisin_bruyant(monkeypatch):
    """Un tenant qui sature SON plafond ne bloque PAS les autres (anti voisin bruyant)."""
    _reset()
    monkeypatch.setattr(llm, "_TOKEN_CAP_PER_TENANT", 50)
    monkeypatch.setattr(llm, "client", _fake_client)
    # tenantA consomme jusqu'au plafond (30, puis 60 ≥ 50).
    with llm.tenant_scope("A"):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)   # 30
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)   # 60 ≥ 50
        with pytest.raises(llm.LLMUnavailable):
            llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    # tenantB n'est PAS affecté.
    with llm.tenant_scope("B"):
        resp = llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
        assert resp is not None
    _reset()


def test_disjoncteur_par_tenant_isole_le_voisin(monkeypatch):
    """Un tenant dont les appels échouent ouvre SON circuit ; un autre tenant reste OK."""
    _reset()
    monkeypatch.setattr(llm, "_TCB_THRESHOLD", 2)

    class _Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("entrée pathologique")

    # tenantA échoue 2 fois → son circuit s'ouvre.
    monkeypatch.setattr(llm, "client", lambda: _Boom)
    with llm.tenant_scope("A"):
        for _ in range(2):
            with pytest.raises(RuntimeError):
                llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
        # 3e appel de A : échec RAPIDE (circuit tenant ouvert), sans toucher l'API.
        with pytest.raises(llm.LLMUnavailable):
            llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)

    # tenantB, lui, fonctionne normalement (API « réparée » pour cet exemple).
    monkeypatch.setattr(llm, "client", _fake_client)
    with llm.tenant_scope("B"):
        resp = llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
        assert resp is not None
    assert llm._TENANT_CB["A"]["open_until"] > 0    # circuit de A ouvert
    _reset()


def test_concurrence_compteurs_coherents(monkeypatch):
    """Sous 16 threads en parallèle (8 tenants × 2), les compteurs verrouillés restent
    EXACTS — pas de perte d'incrément (atomicité du disjoncteur/usage/latence)."""
    import concurrent.futures as cf
    _reset()
    monkeypatch.setattr(llm, "client", _fake_client)
    N_TENANTS, PER = 8, 20

    def hammer(tid):
        with llm.tenant_scope(f"t{tid}"):
            for _ in range(PER):
                llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)

    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(hammer, list(range(N_TENANTS)) * 2))   # chaque tenant martelé par 2 threads

    expected_calls = N_TENANTS * 2 * PER
    assert llm.TOKENS["calls"] == expected_calls                     # aucun appel perdu
    assert llm.latency_snapshot()["count"] == expected_calls         # latence cohérente
    for tid in range(N_TENANTS):
        assert llm.tenant_usage(f"t{tid}") == 2 * PER * 30           # 2 threads × 20 × 30 tokens
    _reset()


def test_circuit_ouvert_echoue_vite_sans_appeler_api(monkeypatch):
    _reset()
    llm._CB["open_until"] = time.monotonic() + 60   # circuit ouvert
    called = {"n": 0}

    class _Spy:
        class messages:
            @staticmethod
            def create(**kw):
                called["n"] += 1
                return _FakeResp()

    monkeypatch.setattr(llm, "client", lambda: _Spy)
    with pytest.raises(llm.LLMUnavailable):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
    assert called["n"] == 0   # l'API n'a PAS été appelée
    _reset()
