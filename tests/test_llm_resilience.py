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
