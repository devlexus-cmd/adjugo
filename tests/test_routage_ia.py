"""
Chantier R — routage de l'IA par tâche, secours croisé, surveillance, diagnostic.

Aucun appel réseau ni IA réel : le client Anthropic est remplacé par un faux (ou par le VRAI SDK 0.34
branché sur un transport httpx simulé, pour prouver ce qu'il envoie et ce qu'il lit), et l'API Mistral
par un faux httpx.post / httpx.get.
"""
import ast
import datetime as dt
import json
import logging
import pathlib
import types

import httpx
import pytest

from app.services import llm
from app.services import llm_qualite as qualite

CLE_MISTRAL = "Zq9Kx7Lm2Pw4Rt8Vb6Nc3Hy5Jd1"
CLE_ANTHROPIC = "sk-ant-Qw3Er5Ty7Ui9Op2As4Df6"


@pytest.fixture(autouse=True)
def _propre(monkeypatch):
    for v in ("LLM_PROVIDER", "LLM_ROUTAGE", "LLM_SECOURS", "MISTRAL_POINT_ACCES", "MISTRAL_BASE_URL",
              "MISTRAL_SOLDE_JUSQU_AU", "ANALYSE_MODELE_PIECES", "LLM_MODELE_SONNET", "LLM_MODELE_MISTRAL"):
        monkeypatch.delenv(v, raising=False)
    for t in llm.TACHES:
        for suf in ("", "_SECOURS", "_EFFORT", "_REFLEXION", "_CACHE", "_RESERVE", "_RAISONNEMENT"):
            monkeypatch.delenv(f"LLM_TACHE_{t.upper()}{suf}", raising=False)
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY_ADJUGO", "")
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(llm.settings, "LLM_ROUTAGE", "nouveau")
    monkeypatch.setattr(llm.settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", False)
    monkeypatch.setattr(llm.settings, "MISTRAL_ACTIF", False)

    def reset():
        llm._CB.update(fails=0, open_until=0.0)
        llm._CB_MISTRAL.update(fails=0, open_until=0.0)
        llm._TENANT_CB.clear()
        llm._reinitialiser_point_acces()
        qualite.reinitialiser()
    reset()
    yield
    reset()


# ── Faux fournisseurs ───────────────────────────────────────────────────────────

class _B:
    def __init__(self, type_, text=None, **kw):
        self.type = type_
        self.text = text
        for k, v in kw.items():
            setattr(self, k, v)


class _U:
    def __init__(self, i=100, o=50, **kw):
        self.input_tokens, self.output_tokens = i, o
        for k, v in kw.items():
            setattr(self, k, v)


class FakeAnthropic:
    """Remplace llm.client() : `repondre(kwargs)` → (blocs, motif d'arrêt[, usage]) ou lève."""

    def __init__(self, repondre=None):
        self.calls = []
        self.repondre = repondre or (lambda kw: ([_B("text", "ok")], "end_turn"))
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        out = self.repondre(kw)
        blocs, stop = out[0], out[1]
        usage = out[2] if len(out) > 2 else _U()
        return types.SimpleNamespace(content=blocs, stop_reason=stop, usage=usage, stop_details=None)


class _HR:
    def __init__(self, status=200, data=None, text=""):
        self.status_code = status
        self._data = data or {}
        self.text = text or json.dumps(self._data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", "https://x"),
                                        response=httpx.Response(self.status_code))


def _mistral_ok(text="{\"ok\": true}", finish="stop", pt=1000, ct=500, cached=0):
    return _HR(200, {"choices": [{"message": {"content": text}, "finish_reason": finish}],
                     "usage": {"prompt_tokens": pt, "completion_tokens": ct,
                               "prompt_tokens_details": {"cached_tokens": cached}}})


class FakeMistral:
    def __init__(self, repondre=None):
        self.calls = []
        self.repondre = repondre or (lambda url, payload: _mistral_ok())

    def __call__(self, url, json=None, headers=None, timeout=None, **kw):
        self.calls.append({"url": url, "payload": json, "headers": headers})
        out = self.repondre(url, json)
        if isinstance(out, Exception):
            raise out
        return out


def _anthropic(monkeypatch, repondre=None):
    fake = FakeAnthropic(repondre)
    monkeypatch.setattr(llm, "client", lambda: fake)
    return fake


def _mistral(monkeypatch, repondre=None, cle=CLE_MISTRAL, modeles=("mistral-large-4",), actif=True):
    """Mistral simulé. actif : clé + MISTRAL_ACTIF + désinscription de l'entraînement (les trois sont
    nécessaires pour que Mistral reçoive quoi que ce soit) ; actif=False : la clé seule."""
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY_ADJUGO", cle)
    monkeypatch.setattr(llm.settings, "MISTRAL_ACTIF", bool(actif))
    monkeypatch.setattr(llm.settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", bool(actif))
    fake = FakeMistral(repondre)
    monkeypatch.setattr(llm.httpx, "post", fake)
    vus = {"n": 0}

    def get(url, headers=None, timeout=None, **kw):
        vus["n"] += 1
        return _HR(200, {"object": "list", "data": [{"id": m, "aliases": []} for m in modeles]})
    monkeypatch.setattr(llm.httpx, "get", get)
    fake.verifications = vus
    return fake


# ── 1. Routage par tâche ────────────────────────────────────────────────────────

def test_table_de_routage_decisions_du_fondateur():
    lecture = ("analyse", "lecture_pieces", "exigences", "veille", "deliberation", "renouvellements")
    for t in lecture:
        r = llm.route(t)
        assert (r.primaire.fournisseur, r.primaire.modele) == ("mistral", "mistral-large-4"), t
        assert (r.secours.fournisseur, r.secours.modele) == ("anthropic", "claude-sonnet-5-5"), t
        assert {"absent", "panne", "modele"} <= r.secours_sur, t
    assert "coupe" in llm.route("analyse").secours_sur          # analyse coupée → Sonnet 5.5
    for t in set(llm.TACHES) - set(lecture):
        r = llm.route(t)
        assert (r.primaire.fournisseur, r.primaire.modele) == ("anthropic", "claude-sonnet-5-5"), t
        assert (r.secours.fournisseur, r.secours.modele) == ("mistral", "mistral-large-4"), t
        assert "panne" in r.secours_sur and "coupe" not in r.secours_sur, t
    # Jamais l'alias -latest (mistral-large-latest = Large 3).
    assert all("latest" not in llm.route(t).primaire.modele for t in llm.TACHES)
    # Réglages : questions rapides et fidèles, rédaction en qualité avec un cache d'une heure.
    q, red = llm.route("questions").anthropic, llm.route("redaction").anthropic
    assert (q.reflexion, q.effort) == ("between_tools", "medium")
    assert (red.reflexion, red.effort, red.cache_ttl) == ("adaptive", "high", "1h")


def test_surcharge_par_variables_d_environnement(monkeypatch):
    monkeypatch.setenv("LLM_TACHE_QUESTIONS", "anthropic:claude-opus-5-5")
    monkeypatch.setenv("LLM_TACHE_QUESTIONS_EFFORT", "low")
    monkeypatch.setenv("LLM_TACHE_ANALYSE_SECOURS", "aucun")
    monkeypatch.setenv("LLM_TACHE_REDACTION_CACHE", "5m")
    assert llm.route("questions").primaire.modele == "claude-opus-5-5"
    assert llm.route("questions").anthropic.effort == "low"
    assert llm.route("analyse").secours is None
    assert llm.route("redaction").anthropic.cache_ttl == "5m"
    monkeypatch.setenv("LLM_SECOURS", "0")
    assert all(llm.route(t).secours is None for t in llm.TACHES)


def _appels_ia(tree):
    noms = {"messages_create", "complete", "complete_ex", "complete_json"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nom = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if nom in noms:
                yield node


def test_tous_les_appels_ia_de_l_application_nomment_leur_tache():
    """Recensement : chaque appel IA du code (hors llm.py) passe `tache=` d'une tâche connue."""
    racine = pathlib.Path(__file__).resolve().parent.parent / "app"
    vus = []
    for p in racine.rglob("*.py"):
        if p.name in ("llm.py", "llm_qualite.py"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        consts = {n.targets[0].id: n.value.value for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                  and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
        for call in _appels_ia(tree):
            kw = {k.arg: k.value for k in call.keywords}
            assert "tache" in kw, f"{p.relative_to(racine)}:{call.lineno} : appel IA sans tâche"
            v = kw["tache"]
            nom = v.value if isinstance(v, ast.Constant) else consts.get(getattr(v, "id", ""), None)
            if nom is None and isinstance(v, ast.Attribute):
                nom = {"ANALYSE_TACHE": "analyse"}.get(v.attr)
            assert nom in llm.TACHES, f"{p.relative_to(racine)}:{call.lineno} : tâche inconnue {nom!r}"
            vus.append(nom)
    # Tous les usages recensés (comparatif § 2.1 + lecture en deux temps, atelier, questions) sont là.
    assert set(vus) == set(llm.TACHES)


# ── 2. Sonnet 5.5 : jamais de temperature, réflexion/effort, blocs lus par type ─────────────────

def test_sonnet_55_sans_temperature_et_reglages_par_tache(monkeypatch):
    fake = _anthropic(monkeypatch)
    llm.complete_ex("consigne", "question", max_tokens=1000, temperature=0.3, tache="questions")
    kw = fake.calls[-1]
    assert kw["model"] == "claude-sonnet-5-5"
    assert not ({"temperature", "top_p", "top_k"} & set(kw))
    assert kw["extra_body"] == {"thinking": {"type": "between_tools"}, "output_config": {"effort": "medium"}}
    assert kw["max_tokens"] == 1300                            # découpage +30 %, pas de réflexion préalable
    llm.complete_ex("consigne", [llm.cached_text_block("dossier commun " * 50), {"type": "text", "text": "partie"}],
                    max_tokens=1000, temperature=0.3, tache="redaction")
    kw = fake.calls[-1]
    assert "temperature" not in kw and "thinking" not in kw["extra_body"]        # adaptatif = défaut du modèle
    assert kw["extra_body"]["output_config"] == {"effort": "high"}
    assert kw["max_tokens"] == 1300 + 8000                      # place pour la réflexion (comptée dedans)
    assert kw["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_vrai_sdk_034_envoie_extra_body_et_ignore_les_blocs_de_reflexion(monkeypatch):
    """Le SDK épinglé (0.34) : extra_body transmis tel quel, durée du cache conservée, aucun
    paramètre d'échantillonnage, blocs « thinking » / « redacted_thinking » lus sans erreur et écartés."""
    from anthropic import Anthropic
    vu = {}
    corps = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
             "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                         {"type": "redacted_thinking", "data": "zzz"},
                         {"type": "text", "text": "Réponse "}, {"type": "text", "text": "finale."}],
             "stop_reason": "end_turn", "stop_sequence": None,
             "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 3000,
                       "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 3000}}}

    def handler(request):
        vu["corps"] = json.loads(request.content)
        vu["entetes"] = dict(request.headers)
        return httpx.Response(200, json=corps)
    c = Anthropic(api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    monkeypatch.setattr(llm, "client", lambda: c)
    with llm.cost_meter("test", 1, log=False) as m:
        texte, stop = llm.complete_ex("consigne", [llm.cached_text_block("x" * 3000), {"type": "text", "text": "q"}],
                                      max_tokens=100, temperature=0.3, tache="redaction")
    assert texte == "Réponse finale." and stop == "end_turn"
    b = vu["corps"]
    assert b["model"] == "claude-sonnet-5-5" and "temperature" not in b and "top_p" not in b
    assert b["output_config"] == {"effort": "high"} and "thinking" not in b
    assert b["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert not any(k.startswith("anthropic-beta") for k in vu["entetes"])      # aucun en-tête bêta requis
    s = m.summary()
    assert s["tokens_cache_ecrits"] == 3000 and s["tokens_cache_ecrits_1h"] == 3000
    # 10 × 2 $ + 5 × 10 $ + 3 000 × 4 $ (écriture d'une heure) par million.
    assert s["cout_estime_usd"] == pytest.approx((10 * 2 + 5 * 10 + 3000 * 4) / 1e6)


def test_blocs_de_reflexion_ignores_avec_un_faux_client(monkeypatch):
    _anthropic(monkeypatch, lambda kw: ([_B("thinking", None, thinking="je réfléchis"), _B("text", "{\"a\": 1}")],
                                        "end_turn"))
    assert llm.complete_json("s", "u", tache="chiffrage") == {"a": 1}


def test_effort_xhigh_jamais_avec_between_tools(monkeypatch):
    fake = _anthropic(monkeypatch)
    monkeypatch.setenv("LLM_TACHE_QUESTIONS_EFFORT", "xhigh")
    llm.complete("s", "u", tache="questions")
    assert "thinking" not in fake.calls[-1]["extra_body"]       # between_tools refusé à xhigh → adaptatif
    assert fake.calls[-1]["extra_body"]["output_config"] == {"effort": "xhigh"}


# ── 3. Ancien routage : une variable, réglages d'origine ──────────────────────────────────────────

def test_bascule_de_retour_vers_l_ancien_routage(monkeypatch):
    monkeypatch.setenv("LLM_ROUTAGE", "ancien")
    _mistral(monkeypatch)                                       # même avec une clé Mistral : jamais utilisée
    fake = _anthropic(monkeypatch)
    assert llm.route("questions").primaire == llm.Cible("anthropic", "claude-haiku-4-5")
    assert llm.route("analyse").primaire == llm.Cible("anthropic", "claude-sonnet-4-6")
    assert llm.route("lecture_pieces").primaire.modele == "claude-haiku-4-5"
    assert llm.route("acheteur_annexes").primaire.modele == "claude-haiku-4-5"
    assert all(llm.route(t).secours is None for t in llm.TACHES)
    llm.complete_ex("s", [llm.cached_text_block("d" * 100), {"type": "text", "text": "p"}], max_tokens=900,
                    temperature=0.3, tache="redaction")
    kw = fake.calls[-1]
    assert kw["model"] == "claude-sonnet-4-6" and kw["temperature"] == 0.3 and kw["max_tokens"] == 900
    assert "extra_body" not in kw and kw["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert llm.httpx.post.calls == []
    assert any("LLM_ROUTAGE=ancien" in m for m in llm.diagnostic(verifier=False)["messages"])


# ── 4. Aucune bascule silencieuse quand une clé Mistral apparaît ──────────────────────────────────

def test_aucune_bascule_silencieuse_avec_une_cle_mistral(monkeypatch):
    for nom in ("MISTRAL_API_KEY", "MISTRAL_API_KEY_ADJUGO"):
        monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY_ADJUGO", "")
        monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY", "")
        monkeypatch.setattr(llm.settings, nom, CLE_MISTRAL)
        monkeypatch.setattr(llm.settings, "MISTRAL_ACTIF", True)
        monkeypatch.setattr(llm.settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", True)
        post = FakeMistral()
        monkeypatch.setattr(llm.httpx, "post", post)
        monkeypatch.setattr(llm.httpx, "get", lambda *a, **k: _HR(200, {"data": [{"id": "mistral-large-4"}]}))
        fake = _anthropic(monkeypatch)
        for t in ("questions", "redaction", "raccourcir", "questionnaire", "chiffrage", "acheteur_dce"):
            llm.complete("s", "u", tache=t)
        llm.messages_create(model=llm.MODEL, max_tokens=5, messages=[])     # appel direct : son modèle
        assert post.calls == [] and len(fake.calls) == 7
        assert llm._cle_mistral()[1] == nom
        assert llm.active_provider()["provider"] == "mixte"                 # dit, jamais silencieux
        assert llm.diagnostic(verifier=False)["fournisseurs"]["mistral"]["variable"] == nom


def test_cle_adjugo_prioritaire_sur_le_nom_historique(monkeypatch):
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY", "Hk4Bv8Wq2Zx6")
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY_ADJUGO", "Pm7Lr3Ts9Ny5")
    assert llm._cle_mistral() == ("Pm7Lr3Ts9Ny5", "MISTRAL_API_KEY_ADJUGO")
    d = llm.diagnostic(verifier=False)
    assert any("MISTRAL_API_KEY est aussi renseignée" in m for m in d["messages"])
    assert "Pm7Lr3Ts9Ny5" not in json.dumps(d) and "Hk4Bv8Wq2Zx6" not in json.dumps(d)


def test_llm_provider_force_un_seul_fournisseur_et_le_dit(monkeypatch):
    _mistral(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert all(llm.route(t).primaire.fournisseur == "anthropic" and llm.route(t).secours is None
               for t in llm.TACHES)
    d = llm.diagnostic(verifier=False)
    assert d["forcage_llm_provider"] == "anthropic"
    assert any("toutes les tâches partent chez anthropic" in m for m in d["messages"])
    assert any("LLM_PROVIDER=anthropic" in x for x in llm.resume_routage())
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    assert all(llm.route(t).primaire == llm.Cible("mistral", "mistral-large-4") for t in llm.TACHES)
    monkeypatch.setattr(llm.settings, "MISTRAL_API_KEY_ADJUGO", "")      # forcé sans clé : jamais de panne
    assert all(llm.route(t).primaire.fournisseur == "anthropic" for t in llm.TACHES)


# ── 5. Mistral Large 4 : appel HTTP, JSON, point d'accès, coupure ─────────────────────────────────

def test_appel_mistral_json_point_d_acces_ue_et_tenant(monkeypatch):
    m = _mistral(monkeypatch, lambda url, p: _mistral_ok("{\"faits\": []}", pt=1200, ct=300, cached=200))
    fake = _anthropic(monkeypatch)
    with llm.tenant_scope("espace-1"), llm.cost_meter("lecture", "espace-1", log=False) as cm:
        resp = llm.messages_create(tache="lecture_pieces", max_tokens=8000, temperature=0,
                                   system=[llm.cached_text_block("consigne")],
                                   messages=[{"role": "user", "content": [{"type": "text", "text": "pièce"}]}])
    assert resp.content[0].text == "{\"faits\": []}" and resp.fournisseur == "mistral" and resp.bascule is None
    c = m.calls[-1]
    assert c["url"] == "https://api.eu.mistral.ai/v1/chat/completions"     # modèle servi sur l'UE (models.list)
    assert c["payload"]["model"] == "mistral-large-4"
    assert c["payload"]["response_format"] == {"type": "json_object"}
    assert c["payload"]["temperature"] == 0 and c["payload"]["max_tokens"] == 10400
    assert c["payload"]["messages"][0] == {"role": "system", "content": "consigne"}   # cache_control aplati
    assert c["headers"]["Authorization"] == f"Bearer {CLE_MISTRAL}" and fake.calls == []
    assert llm.tenant_usage("espace-1") >= 1500
    s = cm.summary()
    assert s["tokens_entree"] == 1000 and s["tokens_cache_lus"] == 200 and "mistral-large-4@ue" in s["par_modele"]
    assert m.verifications["n"] == 1


def test_point_d_acces_auto_mondial_si_large4_absent_de_l_ue(monkeypatch):
    m = _mistral(monkeypatch, modeles=("mistral-large-2512", "mistral-small-2603"))
    _anthropic(monkeypatch)
    llm.complete("s", "u", tache="analyse")
    assert m.calls[-1]["url"] == "https://api.mistral.ai/v1/chat/completions"
    pa = llm.point_acces_mistral()
    assert pa["zone"] == "mondial" and pa["verifie"] is True
    assert llm.diagnostic(verifier=False)["fournisseurs"]["mistral"]["large4_sur_ue"] is False


def test_point_d_acces_force_par_variable(monkeypatch):
    m = _mistral(monkeypatch, modeles=())
    monkeypatch.setenv("MISTRAL_POINT_ACCES", "ue")
    llm.complete("s", "u", tache="veille")
    assert m.calls[-1]["url"].startswith("https://api.eu.mistral.ai/") and m.verifications["n"] == 0
    monkeypatch.setenv("MISTRAL_POINT_ACCES", "mondial")
    llm.complete("s", "u", tache="veille")
    assert m.calls[-1]["url"].startswith("https://api.mistral.ai/")


def test_blocs_de_raisonnement_mistral_ignores(monkeypatch):
    _mistral(monkeypatch, lambda url, p: _HR(200, {
        "choices": [{"message": {"content": [{"type": "thinking", "thinking": [{"type": "text", "text": "hmm"}]},
                                             {"type": "text", "text": "{\"projets\": []}"}]},
                     "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5}}))
    assert llm.complete_json("s", "u", tache="veille") == {"projets": []}


# ── 6. Secours dans les deux sens ───────────────────────────────────────────────────────────────

def test_secours_analyse_vers_sonnet_si_mistral_absent(monkeypatch):
    fake = _anthropic(monkeypatch, lambda kw: ([_B("text", "{\"x\": 1}")], "end_turn"))
    resp = llm.messages_create(tache="analyse", max_tokens=6000, temperature=0, system="s",
                               messages=[{"role": "user", "content": "dossier"}])
    assert resp.fournisseur == "anthropic" and resp.bascule == "absent"
    assert fake.calls[-1]["model"] == "claude-sonnet-5-5" and "temperature" not in fake.calls[-1]
    assert fake.calls[-1]["extra_body"]["thinking"] == {"type": "between_tools"}
    b = qualite.instantane()["bascules"]
    assert b == [{"tache": "analyse", "de": "mistral", "vers": "anthropic", "motif": "absent", "nombre": 1}]


@pytest.mark.parametrize("panne,motif", [
    (lambda url, p: httpx.ConnectError("injoignable"), "panne"),
    (lambda url, p: _HR(503, {"message": "surcharge"}), "panne"),
    (lambda url, p: _HR(404, {"message": "Invalid model: mistral-large-4", "type": "invalid_model"}), "modele"),
    (lambda url, p: _mistral_ok("{\"tronque\": ", finish="length"), "coupe"),
    (lambda url, p: _mistral_ok("ceci n'est pas du JSON"), "json"),
])
def test_secours_analyse_vers_sonnet_si_mistral_defaille(monkeypatch, caplog, panne, motif):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    _mistral(monkeypatch, panne)
    fake = _anthropic(monkeypatch, lambda kw: ([_B("text", "{\"ok\": 1}")], "end_turn"))
    caplog.set_level(logging.INFO, logger="adjugo")
    with llm.cost_meter("analyse", 7, log=False) as cm:
        resp = llm.messages_create(tache="analyse", max_tokens=6000, temperature=0, system="s",
                                   messages=[{"role": "user", "content": "dossier"}])
    assert resp.fournisseur == "anthropic" and resp.bascule == motif and resp.content[0].text == "{\"ok\": 1}"
    if motif == "coupe":
        assert fake.calls[-1]["max_tokens"] == 7800 * 2          # le secours a deux fois plus de place
    assert cm.summary()["bascules_de_secours"] == 1
    assert any("Bascule de secours IA" in r.getMessage() and f"motif : {motif}" in r.getMessage()
               for r in caplog.records)
    lignes = {(x["fournisseur"], x["tache"]): x for x in qualite.instantane()["par_fournisseur_et_tache"]}
    assert lignes[("mistral", "analyse")]["bascules_vers_le_secours"] == 1
    if motif == "modele":                                       # UE sans le modèle → mondial ensuite
        assert llm.point_acces_mistral()["zone"] == "mondial"


def test_secours_questions_et_redaction_vers_mistral_si_anthropic_en_panne(monkeypatch):
    from app.services.pii import Pseudonymizer
    m = _mistral(monkeypatch, lambda url, p: _mistral_ok("Texte de [Chef de chantier 1]."))

    def panne(kw):
        raise RuntimeError("Anthropic en panne")
    _anthropic(monkeypatch, panne)
    pz = Pseudonymizer([{"nom": "Yann Tanguy", "fonction": "Chef de chantier"}])
    with llm.pii_scope(pz):
        texte, stop = llm.complete_ex("Rédige.", "Yann Tanguy dirige le chantier.", max_tokens=1000,
                                      temperature=0.3, tache="redaction")
    assert texte == "Texte de Yann Tanguy." and stop == "end_turn"          # remis en clair, sans IA
    envoye = json.dumps(m.calls[-1]["payload"], ensure_ascii=False)
    assert "Yann" not in envoye and "Tanguy" not in envoye                  # garde-fou inchangé au secours
    assert m.calls[-1]["payload"]["model"] == "mistral-large-4"
    assert "response_format" not in m.calls[-1]["payload"]                    # rédaction : texte libre
    resp = llm.messages_create(tache="questions", max_tokens=1200, temperature=0, system="s",
                               messages=[{"role": "user", "content": "q"}])
    assert resp.fournisseur == "mistral" and resp.bascule == "panne"


def test_sans_cle_mistral_la_panne_anthropic_remonte_telle_quelle(monkeypatch):
    def panne(kw):
        raise RuntimeError("fournisseur en panne")
    _anthropic(monkeypatch, panne)
    with pytest.raises(RuntimeError):
        llm.complete("s", "u", tache="questions")
    assert qualite.instantane()["bascules"] == []                            # aucune bascule fictive


def test_refus_du_modele_secours_ou_erreur_propre(monkeypatch):
    _anthropic(monkeypatch, lambda kw: ([], "refusal"))
    with pytest.raises(llm.LLMRefus):
        llm.complete("s", "u", tache="questions")
    assert issubclass(llm.LLMRefus, llm.LLMUnavailable)                      # remboursé par les appelants
    _mistral(monkeypatch, lambda url, p: _mistral_ok("{\"trouve\": true}"))
    resp = llm.messages_create(tache="questions", max_tokens=100, system="s", messages=[{"role": "user", "content": "q"}])
    assert resp.fournisseur == "mistral" and resp.bascule == "refus"
    lignes = {(x["fournisseur"], x["tache"]): x for x in qualite.instantane()["par_fournisseur_et_tache"]}
    assert lignes[("anthropic", "questions")]["refus"] == 2


def test_coupure_des_deux_cotes_rendue_a_l_appelant(monkeypatch):
    """Analyse coupée chez Mistral ET au secours : la réponse coupée est rendue (stop_reason
    « max_tokens ») ; l'appelant la traite comme avant (AnalyseCoupee → remboursement)."""
    from app.services import analysis as an
    _mistral(monkeypatch, lambda url, p: _mistral_ok("{\"summary\": \"coup", finish="length"))
    _anthropic(monkeypatch, lambda kw: ([_B("text", "{\"summary\": \"cou")], "max_tokens"))
    with pytest.raises(an.AnalyseCoupee):
        an.analyze_dce_text("Règlement de la consultation : travaux de voirie. " * 5)
    lignes = {(x["fournisseur"], x["tache"]): x for x in qualite.instantane()["par_fournisseur_et_tache"]}
    assert lignes[("mistral", "analyse")]["coupees"] == 1 and lignes[("anthropic", "analyse")]["coupees"] == 1


def test_json_invalide_partout_rend_la_reponse_et_compte(monkeypatch):
    _mistral(monkeypatch, lambda url, p: _mistral_ok("pas du json"))
    _anthropic(monkeypatch, lambda kw: ([_B("text", "toujours pas")], "end_turn"))
    with pytest.raises(ValueError):
        llm.complete_json("s", "u", tache="renouvellements")
    lignes = {(x["fournisseur"], x["tache"]): x for x in qualite.instantane()["par_fournisseur_et_tache"]}
    assert lignes[("mistral", "renouvellements")]["json_invalides"] == 1
    assert lignes[("anthropic", "renouvellements")]["json_invalides"] == 1


def test_disjoncteurs_separes_par_fournisseur(monkeypatch):
    monkeypatch.setattr(llm, "_CB_THRESHOLD", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    _mistral(monkeypatch, lambda url, p: _HR(500, {}))
    fake = _anthropic(monkeypatch, lambda kw: ([_B("text", "{}")], "end_turn"))
    for _ in range(3):
        llm.complete("s", "u", tache="veille")
    assert llm._CB_MISTRAL["open_until"] > 0 and llm._CB["open_until"] == 0.0
    n = len(llm.httpx.post.calls)
    llm.complete("s", "u", tache="veille")                 # disjoncteur Mistral ouvert : secours direct
    assert len(llm.httpx.post.calls) == n and len(fake.calls) == 4


# ── 7. Coût : vrais prix, cache, découpage ──────────────────────────────────────────────────────

def test_prix_mistral_solde_normal_et_surcout_ue(monkeypatch):
    assert llm.prix_mistral("mistral-large-4", dt.date(2026, 10, 12)) == (0.68, 2.09, 0.07)
    assert llm.prix_mistral("mistral-large-4", dt.date(2026, 11, 1)) == (1.36, 4.18, 0.14)
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "aucun")
    assert llm.cout_usd("mistral-large-4", 1_000_000, 0) == pytest.approx(1.36)
    assert llm.cout_usd("mistral-large-4", 1_000_000, 0, zone="ue") == pytest.approx(1.496)
    monkeypatch.setenv("MISTRAL_PRIX_LARGE4", "2|5|0.2")
    assert llm.cout_usd("mistral-large-4", 0, 1_000_000) == pytest.approx(5.0)
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "2999-12-31")
    assert llm.cout_usd("mistral-large-4", 1_000_000, 1_000_000, 1_000_000) == pytest.approx(0.68 + 2.09 + 0.07)


def test_prix_sonnet_55_et_cache_d_une_heure():
    # Entrée 2 $, sortie 10 $, cache relu 0,10 $ (5 % de l'entrée), écrit 2,50 $ (5 min) ou 4 $ (1 h).
    assert llm.cout_usd("claude-sonnet-5-5", 1000, 500, 10_000, 20_000, 20_000) == pytest.approx(
        (1000 * 2 + 500 * 10 + 10_000 * 0.10 + 20_000 * 4) / 1e6)
    assert llm.cout_usd("claude-sonnet-5-5", 0, 0, 0, 1_000_000, 0) == pytest.approx(2.5)
    assert llm.cout_usd("modele-inconnu", 1, 1) is None
    # Découpage +30 % appliqué aux estimations faites à partir de caractères.
    assert llm.tokens_estimes(33_000, "claude-sonnet-5-5") == 13_000
    assert llm.tokens_estimes(33_000, "claude-sonnet-4-6") == 10_000
    assert llm.estimer_cout("claude-sonnet-5-5", 33_000, 1000) == pytest.approx((13_000 * 2 + 1300 * 10) / 1e6)


def test_cost_meter_melange_mistral_ue_et_sonnet(monkeypatch):
    monkeypatch.setenv("MISTRAL_SOLDE_JUSQU_AU", "aucun")
    _mistral(monkeypatch, lambda url, p: _mistral_ok("{}", pt=1000, ct=1000))
    _anthropic(monkeypatch, lambda kw: ([_B("text", "t")], "end_turn",
                                        _U(100, 200, cache_read_input_tokens=10_000, cache_creation_input_tokens=0)))
    with llm.cost_meter("mix", 3, log=False) as cm:
        llm.complete("s", "u", tache="analyse")
        llm.complete("s", "u", tache="redaction")
    s = cm.summary()
    attendu = (1000 * 1.36 + 1000 * 4.18) * 1.10 / 1e6 + (100 * 2 + 200 * 10 + 10_000 * 0.10) / 1e6
    assert s["cout_estime_usd"] == pytest.approx(attendu, abs=1e-5)
    assert s["fournisseur"] == "anthropic+mistral"


# ── 8. Diagnostic d'administration : jamais de clé ──────────────────────────────────────────────

def test_diagnostic_sans_fuite_de_cle(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    _mistral(monkeypatch)
    d = llm.diagnostic(verifier=True)
    brut = json.dumps(d, ensure_ascii=False)
    for cle in (CLE_MISTRAL, CLE_ANTHROPIC):
        for i in range(0, len(cle) - 6):
            assert cle[i:i + 7] not in brut
    mi = d["fournisseurs"]["mistral"]
    assert mi["configure"] is True and mi["variable"] == "MISTRAL_API_KEY_ADJUGO"
    assert mi["large4_sur_ue"] is True and mi["point_acces"]["zone"] == "ue"
    assert d["fournisseurs"]["anthropic"]["variable"] == "ANTHROPIC_API_KEY"
    t = {x["tache"]: x for x in d["taches"]}
    assert t["analyse"]["fournisseur"] == "mistral" and t["analyse"]["part_maintenant_chez"]["fournisseur"] == "mistral"
    assert t["questions"]["modele"] == "claude-sonnet-5-5"
    assert mi["actif"] is True and mi["etat"] == "actif"
    assert not any("PAS activé" in m or "désinscription de l'entraînement n'est pas confirmée" in m
                   for m in d["messages"])


def test_diagnostic_sans_cle_mistral_dit_ou_part_l_analyse(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    d = llm.diagnostic(verifier=True)
    t = {x["tache"]: x for x in d["taches"]}
    assert t["analyse"]["part_maintenant_chez"] == {"fournisseur": "anthropic", "modele": "claude-sonnet-5-5"}
    assert d["fournisseurs"]["mistral"]["configure"] is False


def test_routes_d_administration_ia(client, auth, monkeypatch):
    from tests.test_reseau_partenaires import _admin_headers
    assert client.get("/api/admin/ia/diagnostic", headers=auth["headers"]).status_code == 403
    assert client.get("/api/admin/ia/qualite", headers=auth["headers"]).status_code == 403
    _mistral(monkeypatch)
    h = _admin_headers(client)
    r = client.get("/api/admin/ia/diagnostic", headers=h)
    assert r.status_code == 200 and CLE_MISTRAL not in r.text
    assert r.json()["fournisseurs"]["mistral"]["variable"] == "MISTRAL_API_KEY_ADJUGO"
    q = client.get("/api/admin/ia/qualite", headers=h)
    assert q.status_code == 200 and "par_fournisseur_et_tache" in q.json()


def test_diagnostic_sans_verification_ne_touche_pas_au_reseau(monkeypatch):
    _mistral(monkeypatch)

    def interdit(*a, **k):
        raise AssertionError("appel réseau interdit")
    monkeypatch.setattr(llm.httpx, "get", interdit)
    d = llm.diagnostic(verifier=False)
    assert d["fournisseurs"]["mistral"]["point_acces"]["verifie"] is False
    assert d["fournisseurs"]["mistral"]["large4_sur_ue"] is None


def test_route_publique_llm_info_sans_detail_ni_souverainete(client, monkeypatch):
    j = client.get("/api/llm/info").json()
    assert j["provider"] == "anthropic" and j["sovereign"] is False and j["fournisseurs"] == ["anthropic"]
    _mistral(monkeypatch)
    j = client.get("/api/llm/info").json()
    assert j["provider"] == "mixte" and set(j["fournisseurs"]) == {"anthropic", "mistral"} and j["sovereign"] is False


def test_fournisseur_absent_compte_mais_ne_declenche_pas_d_alerte(monkeypatch, caplog):
    monkeypatch.setenv("LLM_ALERTE_MIN_APPELS", "3")
    _anthropic(monkeypatch, lambda kw: ([_B("text", "{}")], "end_turn"))
    caplog.set_level(logging.INFO, logger="adjugo")
    for _ in range(6):
        llm.complete_json("s", "u", tache="analyse")          # pas de clé Mistral : Sonnet 5.5 à chaque fois
    assert qualite.instantane()["bascules"][0]["nombre"] == 6
    assert not [r for r in caplog.records if "Alerte qualité IA" in r.getMessage()]
    assert len([r for r in caplog.records if "Bascule de secours IA" in r.getMessage()]) == 1   # 1 fois / heure


# ── 9. Surveillance : /metrics, seuils journalisés sans bloquer ─────────────────────────────────

def test_metrics_et_seuils_d_alerte(monkeypatch, caplog):
    from app.core import metrics
    monkeypatch.setenv("LLM_ALERTE_MIN_APPELS", "5")
    _anthropic(monkeypatch, lambda kw: ([_B("text", "pas du json")], "end_turn"))
    caplog.set_level(logging.WARNING, logger="adjugo")
    for _ in range(6):
        with pytest.raises(ValueError):
            llm.complete_json("s", "u", tache="chiffrage")      # jamais bloqué par l'alerte
    alertes = [r.getMessage() for r in caplog.records if "Alerte qualité IA" in r.getMessage()]
    assert len(alertes) == 1 and "réponses JSON invalides" in alertes[0] and "chiffrage" in alertes[0]
    qualite.marquer_dernier("mistral", "lecture_pieces")
    qualite.noter_citations(8, 2)
    qualite.noter_question(False, "anthropic", "questions")
    out = metrics.render()
    assert 'adjugo_llm_json_invalides_total{fournisseur="anthropic",tache="chiffrage"} 6' in out
    assert 'adjugo_llm_citations_total{fournisseur="mistral",tache="lecture_pieces",verdict="rejetee"} 2' in out
    assert 'adjugo_llm_abstentions_total{fournisseur="anthropic",tache="questions"} 1' in out
    assert 'adjugo_llm_fournisseur_circuit_open{fournisseur="mistral"} 0' in out
    assert "adjugo_llm_tache_duree_seconds_bucket" in out


def test_citations_et_abstentions_attribuees_au_fournisseur_qui_a_repondu(monkeypatch):
    from app.services import analysis as an
    texte = ("Règlement de la consultation. Le chiffre d'affaires minimum exigé est de 300 000 euros HT. "
             "Les candidats fournissent trois références de moins de cinq ans. ") * 3
    reponse = json.dumps({"summary": "s", "details": {"exigences_sources": {
        "ca_minimum_requis": "Le chiffre d'affaires minimum exigé est de 300 000 euros HT.",
        "references_requises": "Dix références de moins de deux ans sont exigées pour tous."}}})
    _mistral(monkeypatch, lambda url, p: _mistral_ok(reponse))
    an.analyze_dce_text(texte)
    lignes = {(x["fournisseur"], x["tache"]): x for x in qualite.instantane()["par_fournisseur_et_tache"]}
    assert lignes[("mistral", "analyse")]["citations_acceptees"] == 1
    assert lignes[("mistral", "analyse")]["citations_rejetees"] == 1


# ── 10. Pages juridiques : texte injecté exact ──────────────────────────────────────────────────

def test_pages_juridiques_sans_mistral_inchangees(client):
    html = client.get("/confidentialite").text
    assert "Anthropic, PBC" in html and "Mistral" not in html


def test_pages_juridiques_avec_mistral_ue(client, monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)    # chacun relais de l'autre
    _mistral(monkeypatch)
    html = client.get("/confidentialite").text
    assert "Anthropic, PBC et Mistral AI" in html and "api.eu.mistral.ai" in html
    assert "Union européenne et de l&#x27;AELE" in html
    # Sous-traitants de Mistral AI : aucun nom (liste non vérifiée), renvoi vers la liste qu'il publie.
    assert ("Mistral AI s&#x27;appuie sur ses propres sous-traitants techniques, dont la liste à jour est publiée "
            "sur son centre de confiance") in html and "trust.mistral.ai/subprocessors" in html
    assert "droit américain" not in html and "désactivée par l&#x27;Éditeur sur son compte" in html
    assert "non encore confirmée" not in html
    assert "France — api.mistral.ai" not in html and "{{AI_" not in html
    # Transferts (§ 7) : UE ET AELE, rôles et relais tirés du routage effectif.
    assert "calcul dans l&#x27;Union européenne et l&#x27;AELE" in html
    assert ("Anthropic (États-Unis ; calcul possiblement dans d&#x27;autres pays) pour les questions "
            "sur les dossiers et la rédaction, et en relais pour la lecture et l&#x27;analyse des dossiers") in html
    assert ("le fournisseur d&#x27;IA Mistral AI et ses propres sous-traitants techniques pour la lecture et "
            "l&#x27;analyse des dossiers, et en relais pour les questions sur les dossiers et la rédaction") in html
    dpa = client.get("/dpa").text
    assert ("Anthropic : États-Unis pour le stockage, calcul possiblement hors des États-Unis (CCT) ; "
            "Mistral AI : Union européenne et AELE pour le calcul") in dpa
    # Désinscription non confirmée : Mistral coupé, les pages reviennent à Anthropic seul (jamais une
    # page qui dirait « jamais utilisés pour entraîner » alors que Mistral reçoit des contenus).
    monkeypatch.setattr(llm.settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", False)
    for page in ("/confidentialite", "/dpa"):
        assert "Mistral" not in client.get(page).text


def test_pages_juridiques_avec_mistral_mondial(client, monkeypatch):
    _mistral(monkeypatch, modeles=("mistral-large-2512",))
    html = client.get("/confidentialite").text
    assert "sans engagement de lieu de calcul" in html and "possiblement hors de l&#x27;Union européenne" in html
    assert "api.eu.mistral.ai" not in html


# ── 11. Relecture du 12/10/2026 ─────────────────────────────────────────────────────────────────

def test_cle_mistral_seule_n_envoie_rien_chez_mistral(client, monkeypatch):
    """Clé déjà dans Railway, MISTRAL_ACTIF non posé : rien ne part chez Mistral, la lecture des dossiers
    part chez Claude Sonnet 5.5, et les pages juridiques ne parlent que d'Anthropic (aucun nouveau
    sous-traitant sans préavis, aucune page qui se contredit)."""
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    m = _mistral(monkeypatch, actif=False)
    fake = _anthropic(monkeypatch, lambda kw: ([_B("text", "{\"x\": 1}")], "end_turn"))
    resp = llm.messages_create(tache="analyse", max_tokens=6000, system="s",
                               messages=[{"role": "user", "content": "dossier"}])
    assert resp.fournisseur == "anthropic" and resp.bascule == "absent" and m.calls == []
    assert fake.calls[-1]["model"] == "claude-sonnet-5-5"
    assert llm.etat_mistral() == "inactif" and llm.active_provider()["provider"] == "anthropic"
    for page in ("/confidentialite", "/dpa"):
        html = client.get(page).text
        assert "Mistral" not in html and "Anthropic, PBC" in html and "{{AI_" not in html
    d = llm.diagnostic(verifier=True)
    mi = d["fournisseurs"]["mistral"]
    assert mi["configure"] is True and mi["actif"] is False and mi["etat"] == "inactif"
    assert mi["large4_sur_ue"] is True          # la clé suffit pour vérifier le point d'accès UE avant d'activer
    assert any("PAS activé" in x and "MISTRAL_ACTIF=1" in x for x in d["messages"])
    t = {x["tache"]: x for x in d["taches"]}
    assert t["analyse"]["part_maintenant_chez"] == {"fournisseur": "anthropic", "modele": "claude-sonnet-5-5"}
    assert any("Mistral non utilisé (MISTRAL_ACTIF non posé)" in x for x in llm.resume_routage())
    assert any("mistral:mistral-large-4 (non utilisable : part chez anthropic:claude-sonnet-5-5) ← analyse" in x
               for x in llm.resume_routage())
    # MISTRAL_ACTIF posé, désinscription non confirmée : toujours rien chez Mistral, et le diagnostic le dit.
    monkeypatch.setattr(llm.settings, "MISTRAL_ACTIF", True)
    llm.messages_create(tache="analyse", max_tokens=100, system="s", messages=[{"role": "user", "content": "d"}])
    assert m.calls == [] and llm.etat_mistral() == "entrainement"
    assert any(x.startswith("IA — ATTENTION : Mistral non utilisé") for x in llm.resume_routage())
    assert any("désinscription de l'entraînement n'est pas confirmée" in x
               for x in llm.diagnostic(verifier=False)["messages"])
    # Les trois réunis : Mistral lit le dossier.
    monkeypatch.setattr(llm.settings, "MISTRAL_ENTRAINEMENT_DESACTIVE", True)
    r = llm.messages_create(tache="analyse", max_tokens=100, system="s", messages=[{"role": "user", "content": "d"}])
    assert r.fournisseur == "mistral" and len(m.calls) == 1 and llm.etat_mistral() == "actif"


def test_refus_du_secours_claude_l_emporte_sur_mistral_absent(monkeypatch):
    """Tâche de lecture, Mistral non utilisable, Claude (secours) refuse : LLMRefus et son message, pas
    « Service IA non configuré » (essai sans appel)."""
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    _anthropic(monkeypatch, lambda kw: ([], "refusal"))
    with pytest.raises(llm.LLMRefus) as e:
        llm.messages_create(tache="analyse", max_tokens=100, system="s", messages=[{"role": "user", "content": "d"}])
    assert str(e.value) == llm._MSG_REFUS
    # Disjoncteur de Mistral ouvert (clé et activation présentes) : même règle.
    _mistral(monkeypatch)
    llm._CB_MISTRAL.update(fails=5, open_until=llm.time.monotonic() + 600)
    with pytest.raises(llm.LLMRefus) as e:
        llm.messages_create(tache="veille", max_tokens=100, system="s", messages=[{"role": "user", "content": "d"}])
    assert str(e.value) == llm._MSG_REFUS
    # Une tâche Claude qui refuse sans secours possible : inchangé.
    llm._CB_MISTRAL.update(fails=0, open_until=0.0)
    monkeypatch.setattr(llm.settings, "MISTRAL_ACTIF", False)
    with pytest.raises(llm.LLMRefus):
        llm.complete("s", "u", tache="questions")


def test_llm_provider_mistral_sans_mistral_utilisable_dit_claude(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    for actif in (None, False):                      # aucune clé, puis clé sans activation
        if actif is False:
            _mistral(monkeypatch, actif=False)
        assert all(llm.route(t).primaire.fournisseur == "anthropic" for t in llm.TACHES)
        lignes = llm.resume_routage()
        assert not any("TOUTES les tâches partent chez mistral" in x for x in lignes)
        assert any("LLM_PROVIDER=mistral demandé, mais Mistral n'est pas utilisable" in x
                   and "partent chez Claude (Anthropic)" in x for x in lignes)
        msgs = llm.diagnostic(verifier=False)["messages"]
        assert not any("toutes les tâches partent chez mistral" in x for x in msgs)
        assert any("partent chez Claude (Anthropic)" in x for x in msgs)
    _mistral(monkeypatch)                             # utilisable : le forçage s'applique et le dit
    assert all(llm.route(t).primaire.fournisseur == "mistral" for t in llm.TACHES)
    assert any("LLM_PROVIDER=mistral : toutes les tâches partent chez mistral" in x for x in llm.resume_routage())


def test_ancien_routage_ignore_les_variables_par_tache(monkeypatch):
    monkeypatch.setenv("LLM_ROUTAGE", "ancien")
    _mistral(monkeypatch)
    monkeypatch.setenv("LLM_TACHE_QUESTIONS", "mistral:mistral-large-4")
    monkeypatch.setenv("LLM_TACHE_ANALYSE_SECOURS", "mistral:mistral-large-4")
    monkeypatch.setenv("LLM_TACHE_REDACTION_EFFORT", "max")
    assert llm.route("questions").primaire == llm.Cible("anthropic", "claude-haiku-4-5")
    assert llm.route("analyse").primaire == llm.Cible("anthropic", "claude-sonnet-4-6")
    assert all(llm.route(t).secours is None for t in llm.TACHES)
    assert llm.route("redaction").anthropic.effort == ""
    d = llm.diagnostic(verifier=False)
    assert d["secours"]["actifs"] is False
    ignorees = [x for x in d["messages"] if x.startswith("Variables ignorées par l'ancien routage")]
    assert ignorees and "LLM_TACHE_QUESTIONS" in ignorees[0] and "mistral-large-4" not in ignorees[0]
    assert any("variables ignorées par l'ancien routage" in x for x in llm.resume_routage())
    # Routage par tâche : les mêmes variables s'appliquent.
    monkeypatch.setenv("LLM_ROUTAGE", "nouveau")
    assert llm.route("questions").primaire == llm.Cible("mistral", "mistral-large-4")


def test_pages_juridiques_anthropic_seul_lieu_de_calcul_exact(client):
    """Anthropic par défaut (inference_geo « global ») : stockage aux États-Unis, calcul possiblement
    ailleurs (documentation Anthropic sur la résidence des données, relue le 12/10/2026)."""
    html = client.get("/confidentialite").text
    assert "pour le stockage (API standard api.anthropic.com) ; calcul possiblement hors des États-Unis" in html
    assert "(Anthropic, États-Unis ; calcul possiblement dans d&#x27;autres pays) pour l&#x27;analyse" in html
    dpa = client.get("/dpa").text
    assert "États-Unis pour le stockage, calcul possiblement hors des États-Unis (CCT)" in dpa
