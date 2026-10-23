"""
Garde ANTI-HALLUCINATION des citations du DCE (co-traitance v2).

L'IA « recopie » des phrases du DCE (CA exigé, forme de groupement imposée…). Une phrase
reformulée ou inventée serait affichée comme une citation → mensonge au client. Règle :
un extrait n'est conservé QUE s'il est une sous-chaîne du texte INTÉGRAL du DCE (après
normalisation tolérante), sinon '' (jamais affiché).

Tests PURS (aucun réseau) : le client LLM est remplacé par un faux qui renvoie un JSON
contenant un extrait RÉEL et un extrait FABRIQUÉ.
"""
import json
from unittest.mock import patch

from app.services.analysis import (
    _RISK_TERMS, _detect_groupement, analyze_dce_text, citation_guard, select_dce_content,
)

DCE = (
    "REGLEMENT DE LA CONSULTATION\n"
    "Objet : réfection de la toiture du groupe scolaire Jules Ferry, Quimper (29).\n"
    "Article 4 — Capacités. Le candidat devra justifier d’un chiffre d’affaires\n"
    "   minimum de 300 000 € HT sur les trois derniers exercices.\n"
    "En cas de groupement, les capacités des membres sont appréciées de manière cumulée.\n"
    "Le groupement sera obligatoirement solidaire après attribution du marché.\n"
    "Date limite de remise des offres : 31/12/2099 à 12h00.\n"
)


# ── citation_guard : tolérances ───────────────────────────────────────────────────────
def test_accents_casse_espaces_toleres():
    ex = "CHIFFRE D'AFFAIRES   minimum de 300 000 € HT"   # casse ≠, apostrophe droite, espaces multiples
    assert citation_guard(DCE, ex) == ex
    assert citation_guard(DCE, "chiffre d’affaires minimum de 300 000 € HT") != ""
    assert citation_guard(DCE, "justifier d'un chiffre d'affaires\nminimum") != ""
    assert citation_guard(DCE, "  le groupement sera obligatoirement solidaire  ") == "le groupement sera obligatoirement solidaire"
    # Accents retirés des DEUX côtés : « reglement » retrouve « REGLEMENT », « réfection » retrouve « réfection ».
    assert citation_guard(DCE, "refection de la toiture du groupe scolaire") != ""


def test_extrait_absent_reformule_ou_trop_court_vide():
    assert citation_guard(DCE, "Le candidat doit avoir un CA de 300 000 euros") == ""   # reformulé
    assert citation_guard(DCE, "effectif minimum de 10 salariés") == ""                  # inventé
    assert citation_guard(DCE, "300 000 €") == ""                                        # trop court (< 12)
    assert citation_guard(DCE, "300 000 €", min_len=5) == "300 000 €"                   # seuil ajustable
    assert citation_guard(DCE, "") == "" and citation_guard(DCE, None) == ""
    assert citation_guard("", "chiffre d'affaires minimum") == ""
    assert citation_guard(None, None) == ""
    assert citation_guard(DCE, 12345) == ""                                              # type sale, pas d'exception


def test_guillemets_retires_et_longueur_bornee():
    assert citation_guard(DCE, "« chiffre d’affaires minimum de 300 000 € HT »") == "chiffre d’affaires minimum de 300 000 € HT"
    assert citation_guard(DCE, '"chiffre d’affaires minimum de 300 000 € HT"') == "chiffre d’affaires minimum de 300 000 € HT"
    assert citation_guard(DCE, "“chiffre d’affaires minimum de 300 000 € HT”") == "chiffre d’affaires minimum de 300 000 € HT"
    long_text = "a" * 1000
    assert len(citation_guard(long_text, long_text)) <= 400


def test_risk_terms_groupement_entrent_dans_la_fenetre():
    for t in ("groupement conjoint", "solidaire", "mandataire", "cotraitant", "co-traitance",
              "références", "references", "effectif", "chiffre d'affaires", "capacité"):
        assert _RISK_TERMS.search(t), t
    # select_dce_content : une clause de groupement page 180 est bien repêchée.
    head = "Objet du marché. " * 600                      # > 9 000 caractères de tête
    filler = "Lorem ipsum dolor sit amet. " * 1200
    clause = "Chaque membre du groupement doit satisfaire individuellement au niveau minimal de CA."
    text = head + filler + clause + filler
    assert len(text) > 30000
    assert clause in select_dce_content(text)


# ── analyze_dce_text : extrait fabriqué vidé, extrait réel conservé ───────────────────
class _FakeUsage:
    input_tokens = 10
    output_tokens = 20


def _fake_llm(payload: dict):
    class _Resp:
        usage = _FakeUsage()
        content = [type("B", (), {"text": json.dumps(payload, ensure_ascii=False)})()]

    return type("C", (), {"messages": type("M", (), {"create": staticmethod(lambda **kw: _Resp())})})


LLM_JSON = {
    "match_score": 70, "go_decision": "go", "summary": "ok",
    "details": {
        "intitule_marche": "Réfection de la toiture du groupe scolaire Jules Ferry",
        "type_marche": "Travaux", "lieu_execution": "Quimper (29)", "date_limite": "31/12/2099",
        "ca_minimum_requis": "300 000 € HT sur les trois derniers exercices",
        "qualifications_requises": [],
        "capacites_groupement": "cumul admis",
        "forme_groupement": {"imposee": "SOLIDAIRE", "extrait": "Le groupement doit être solidaire (phrase inventée)"},
        "exigences_sources": {
            "ca_minimum_requis": "« chiffre d’affaires minimum de 300 000 € HT sur les trois derniers exercices »",
            "capacites_groupement": "Les capacités des membres sont appréciées cumulativement",   # reformulé
            "references_requises": ["pas une chaîne"],
        },
    },
}


def _analyze(payload):
    from app.services import llm
    llm._CB["fails"] = 0
    llm._CB["open_until"] = 0.0
    with patch.object(llm, "_use_mistral", lambda: False), \
         patch.object(llm, "client", lambda: _fake_llm(payload)):
        return analyze_dce_text(DCE, {"name": "Toitures de l'Ouest", "ca_n1": 180000},
                                {"specialites": "toiture"}, lang_name="français")


def test_analyze_vide_extrait_fabrique_et_conserve_extrait_reel():
    r = _analyze(LLM_JSON)
    d = r["details"]
    src = d["exigences_sources"]
    assert set(src) == {"ca_minimum_requis", "qualifications_requises", "references_requises",
                        "effectif_minimum_requis", "capacites_groupement"}
    assert all(isinstance(v, str) for v in src.values())
    # Réel (guillemets retirés, apostrophe typographique tolérée) → conservé tel quel.
    assert src["ca_minimum_requis"] == "chiffre d’affaires minimum de 300 000 € HT sur les trois derniers exercices"
    # Reformulé / type sale / absent → vidé, jamais affiché.
    assert src["capacites_groupement"] == ""
    assert src["references_requises"] == "" and src["qualifications_requises"] == "" and src["effectif_minimum_requis"] == ""
    assert d["exigences_verifiees"] == {"ca_minimum_requis": True, "qualifications_requises": False,
                                        "references_requises": False, "effectif_minimum_requis": False,
                                        "capacites_groupement": False, "forme_groupement": False}
    # Le score reste celui du barème déterministe (le LLM disait 70 / go).
    assert r["score_deterministe"] is True and r["match_score"] != 70 or r["go_decision"] in ("go", "a_etudier", "no_go")


def test_analyze_forme_groupement_normalisee_et_defauts():
    d = _analyze(LLM_JSON)["details"]
    assert d["forme_groupement"] == {"imposee": "solidaire", "extrait": ""}   # casse normalisée, extrait inventé vidé
    assert d["references_requises"] == "Non specifie dans le DCE"
    assert d["effectif_minimum_requis"] == "Non specifie dans le DCE"
    assert d["capacites_groupement"] == "cumul admis"
    # Valeur hors énumération / forme chaîne / absente → non_specifie.
    p = json.loads(json.dumps(LLM_JSON))
    p["details"]["forme_groupement"] = "mixte"
    assert _analyze(p)["details"]["forme_groupement"] == {"imposee": "non_specifie", "extrait": ""}
    p["details"].pop("forme_groupement")
    p["details"].pop("exigences_sources")
    p["details"].pop("capacites_groupement")
    d2 = _analyze(p)["details"]
    assert d2["forme_groupement"] == {"imposee": "non_specifie", "extrait": ""}
    assert d2["capacites_groupement"] == "Non specifie dans le DCE"
    assert set(d2["exigences_sources"].values()) == {""}
    # Extrait RÉEL de forme imposée → conservé.
    p["details"]["forme_groupement"] = {"imposee": "solidaire",
                                        "extrait": "le groupement sera obligatoirement solidaire après attribution"}
    d3 = _analyze(p)["details"]
    assert d3["forme_groupement"]["extrait"] == "le groupement sera obligatoirement solidaire après attribution"
    assert d3["exigences_verifiees"]["forme_groupement"] is True


def test_detect_groupement_transmet_les_exigences():
    d = _analyze(LLM_JSON)
    g = d["groupement"]
    assert set(g) >= {"recommande", "raisons", "exigences"}
    ex = g["exigences"]
    assert set(ex) == {"ca_minimum_requis", "qualifications_requises", "references_requises",
                       "effectif_minimum_requis", "capacites_groupement", "forme_groupement"}
    assert ex["forme_groupement"] == {"imposee": "solidaire", "extrait": ""}
    assert ex["capacites_groupement"] == "cumul admis"
    assert ex["ca_minimum_requis"] == "300 000 € HT sur les trois derniers exercices"
    # Comportement historique conservé (CA exigé > CA entreprise → raison).
    assert g["recommande"] is True and any("CA minimum" in r for r in g["raisons"])
    # Appel direct avec des details minimaux : toujours les 6 clés, valeurs par défaut sûres.
    g2 = _detect_groupement({}, {})
    assert g2["exigences"]["forme_groupement"] == {"imposee": "non_specifie", "extrait": ""}
    assert g2["exigences"]["qualifications_requises"] == []
