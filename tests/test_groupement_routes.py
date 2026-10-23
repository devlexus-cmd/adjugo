"""
« Répondre à plusieurs ? » — routes du score de groupement (co-traitance v2, vague 1).

Invariants prouvés ici :
  • besoins : « ce que le marché exige et que vous n'avez pas » (capacite, qualifs) → qui l'a
    dans « Mes partenaires », avec apports, score_avec et preuve datée ;
  • simulate : seul < groupement, verdict 'go_groupement', simulation enregistrée, et les
    capacités envoyées par le client pour un partenaire de l'annuaire sont IGNORÉES ;
  • anti-hallucination : un membre 'sirene' est RE-FETCHÉ par SIRET (le CA/qualifs du body
    sont ignorés, CA inconnu = avertissement, stocké None) ;
  • retenir : go_decision 'go_groupement', match_score INCHANGÉ (= score seul), partenaire
    rattaché (source 'simulation'), état dérivé 'composition' ;
  • DELETE /plan : retour au verdict seul, partenaire conservé (avertir, pas bloquer) ;
  • isolation : un autre compte reçoit 404 sur toutes les routes ;
  • accroche /analyze-upload (LLM simulé) : pose go_groupement et laisse match_score seul.
Le calcul vient du service pur app/services/groupement_scoring.py (déterministe, 0 LLM).
"""
import json
import uuid

DETAILS = {
    "intitule_marche": "Rénovation thermique et étanchéité d'un groupe scolaire",
    "type_marche": "Travaux", "lieu_execution": "Quimper (29)",
    "budget_estime": "400 000 EUR HT", "ca_minimum_requis": "300 000 EUR",
    "qualifications_requises": ["Qualibat 1512"], "date_limite": "31/12/2099",
    "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"},
                             {"critere": "Prix", "ponderation": "40%"}],
    "allotissement": "Lot unique",
}
# Mandataire : CA 100 k€ (< 300 k€ exigés), aucune qualification, zone 44 (chantier en 29).
COMPANY = {"name": "Toitures Test", "ca_n1": 100000, "postal_code": "44000", "qualifications": []}
CRITERIA = {"specialites": "toiture, étanchéité", "departements": "44", "budget_min": 50000,
            "budget_max": 1000000, "go_threshold": 75, "nogo_threshold": 40}
PARTNER = {"name": "Le Gall Étanchéité", "siret": "73282932000074", "ca_n1": 400000, "effectif": 12,
           "qualifications": "Qualibat 1512", "specialites": "étanchéité, toiture",
           "departement": "29", "city": "Quimper"}


def _register(client):
    email = f"grp_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Autre", "company_name": "Autre SARL"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_project(client, h):
    """Projet DÉJÀ analysé (score seul déterministe via score_dce, posé en base)."""
    assert client.put("/api/company/", headers=h, json=COMPANY).status_code == 200
    assert client.put("/api/criteria/", headers=h, json=CRITERIA).status_code == 200
    pr = client.post("/api/projects/", headers=h, json={"name": "AO Quimper", "budget": 400000})
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]
    from app.core.database import SessionLocal
    from app.models import Project
    from app.services.dce_scoring import score_dce
    det = score_dce(DETAILS, COMPANY, CRITERIA)
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == pid).first()
        p.ai_analysis = {"details": DETAILS, "match_score": det["score"], "go_decision": det["go_decision"],
                         "score_breakdown": det["breakdown"], "dce_available": True,
                         "groupement": {"recommande": True, "raisons": ["CA minimum exigé supérieur au vôtre"]}}
        p.match_score = det["score"]
        p.go_decision = det["go_decision"]
        db.commit()
    finally:
        db.close()
    return pid, det["score"], det["go_decision"]


def _add_partner(client, h, **over):
    body = dict(PARTNER); body.update(over)
    r = client.post("/api/cotraitants/", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _url(pid, tail):
    return f"/api/projects/{pid}/groupement/{tail}"


# ── 1) Besoins : manques + qui les comble ─────────────────────────────────────────────

def test_besoins_liste_les_manques_et_qui_les_comble(client, auth):
    h = auth["headers"]
    pid, seul, dec = _seed_project(client, h)
    assert dec == "a_etudier", "le mandataire seul ne doit pas être 'go' (CA + qualif manquants)"
    ct = _add_partner(client, h)
    # Annuaire : capacités saisies par l'utilisateur → étiquetées 'declare', datées.
    assert ct["capacites_source"] == "declare" and ct["capacites_updated_at"]

    r = client.get(_url(pid, "besoins"), headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["score_seul"] == seul and j["decision"] == "a_etudier"
    keys = {g["key"] for g in j["gaps"]}
    assert {"capacite", "qualifs"} <= keys, keys
    assert j["exigences"]["ca_minimum_requis"] == "300 000 EUR"
    assert j["exigences"]["qualifications_requises"] == ["Qualibat 1512"]

    annuaire = j["candidats"]["annuaire"]
    assert len(annuaire) == 1 and annuaire[0]["id"] == ct["id"]
    c = annuaire[0]
    assert {"capacite", "qualifs"} <= set(c["apporte"]), c
    assert c["score_avec"] is not None and c["score_avec"] > seul
    assert c["proof_label"].startswith("déclaré par vous")
    assert c["capacites"]["ca_n1"] == 400000 and "Qualibat 1512" in c["capacites"]["qualifications"]
    assert c["verified"] is False and c["ca_label"] is None
    assert j["candidats"]["rattaches"] == []
    assert j["candidats"]["sirene"] == []          # aucun appel réseau sans sirene=1
    assert j["state"]["state"] in ("seul", "potentiel")


# ── 2) Simulation avec un partenaire de l'annuaire ───────────────────────────────────

def test_simulate_annuaire_go_groupement(client, auth):
    h = auth["headers"]
    pid, seul, _ = _seed_project(client, h)
    ct = _add_partner(client, h)
    r = client.post(_url(pid, "simulate"), headers=h,
                    json={"members": [{"kind": "annuaire", "id": ct["id"], "ca_n1": 99000000}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["score_seul"] == seul
    assert j["score_groupement"] > seul
    assert j["decision"] == "go_groupement"
    assert j["simulation_id"]
    # Les capacités du body sont IGNORÉES : lues en base (CA 400 k€, source 'declare').
    partner = [m for m in j["members"] if m["kind"] != "lead"][0]
    assert partner["ca_n1"] == 400000 and partner["source"] == "declare"
    # Avertissement PROÉMINENT (en tête) : verdict fondé sur vos propres déclarations.
    # En tête, une seule phrase sur les capacités déclarées (celle qui nomme le partenaire), jamais deux.
    assert "capacités déclarées par vous" in j["warnings"][0] and "à confirmer" in j["warnings"][0]
    assert sum("déclarées" in w for w in j["warnings"]) == 1
    hist = client.get(_url(pid, "simulations"), headers=h).json()
    assert len(hist) == 1 and hist[0]["id"] == j["simulation_id"] and hist[0]["retained"] is False
    assert hist[0]["members"] == [{"name": PARTNER["name"], "kind": "annuaire"}]

    # Garde-fous d'entrée
    assert client.post(_url(pid, "simulate"), headers=h, json={"members": []}).status_code == 422
    too_many = [{"kind": "annuaire", "id": ct["id"]}] * 5
    assert client.post(_url(pid, "simulate"), headers=h, json={"members": too_many}).status_code == 422
    assert client.post(_url(pid, "simulate"), headers=h,
                       json={"members": [{"kind": "annuaire", "id": 999999}]}).status_code == 404


# ── 3) Membre SIRENE : re-fetch serveur, capacités client ignorées ───────────────────

def test_simulate_sirene_refetch_ignore_le_client(client, auth, monkeypatch):
    h = auth["headers"]
    pid, seul, _ = _seed_project(client, h)
    siret = "73282932000074"
    calls = []

    def fake_lookup(q):
        calls.append(q)
        if q != siret:
            return None
        return {"name": "Étanchéité du Registre", "siren": siret[:9], "siret": siret, "code_ape": "4399A",
                "naf_label": "Autres travaux spécialisés", "specialite": "étanchéité",
                "forme_juridique": "SAS", "address": "", "postal_code": "29000", "city": "Quimper",
                "departement": "29", "effectif": 10, "etat": "actif"}   # AUCUN CA publié

    monkeypatch.setattr("app.services.registre.lookup_company", fake_lookup)
    r = client.post(_url(pid, "simulate"), headers=h, json={"members": [
        {"kind": "sirene", "siret": siret, "ca_n1": 5000000, "qualifications": ["Qualibat 1512"]}]})
    assert r.status_code == 200, r.text
    assert calls == [siret], "le serveur doit RE-FETCHER la fiche par SIRET"
    j = r.json()
    partner = [m for m in j["members"] if m["kind"] == "sirene"][0]
    assert partner["ca_n1"] is None, "le CA inventé par le client doit être ignoré"
    assert partner["qualifications"] == [], "aucune qualification inventée"
    assert partner["source"] == "sirene" and partner["effectif"] == 10
    assert any("CA" in w and "non connu" in w for w in j["warnings"]), j["warnings"]

    from app.core.database import SessionLocal
    from app.models import GroupementSimulation
    db = SessionLocal()
    try:
        sim = db.query(GroupementSimulation).filter(GroupementSimulation.id == j["simulation_id"]).first()
        stored = [m for m in sim.members if m["kind"] == "sirene"][0]
        assert stored["ca_n1"] is None and "Qualibat" not in json.dumps(stored)
    finally:
        db.close()

    # SIRET invalide → 422 ; introuvable dans le registre → 404.
    assert client.post(_url(pid, "simulate"), headers=h,
                       json={"members": [{"kind": "sirene", "siret": "123"}]}).status_code == 422
    assert client.post(_url(pid, "simulate"), headers=h,
                       json={"members": [{"kind": "sirene", "siret": "11111111111111"}]}).status_code == 404


# ── 4) Retenir : verdict groupement, score seul inchangé, partenaire rattaché ─────────

def test_retenir_pose_go_groupement_et_rattache(client, auth):
    h = auth["headers"]
    pid, seul, _ = _seed_project(client, h)
    ct = _add_partner(client, h)
    sim = client.post(_url(pid, "simulate"), headers=h,
                      json={"members": [{"kind": "annuaire", "id": ct["id"]}]}).json()
    assert client.post(_url(pid, "retenir"), headers=h, json={"simulation_id": 999999}).status_code == 404

    r = client.post(_url(pid, "retenir"), headers=h, json={"simulation_id": sim["simulation_id"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] and j["decision"] == "go_groupement"
    assert j["state"]["state"] == "composition"
    assert j["plan"]["auto"] is False and j["plan"]["simulation_id"] == sim["simulation_id"]
    assert j["plan"]["members"][0]["id"] == ct["id"]
    assert {"capacite", "qualifs"} <= set(j["plan"]["members"][0]["apporte"]), j["plan"]["members"]
    assert j["plan"]["score_seul"] == seul and j["plan"]["score_groupement"] == sim["score_groupement"]

    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["go_decision"] == "go_groupement"
    assert p["match_score"] == seul, "match_score reste le score SEUL (jamais gonflé)"

    links = client.get(f"/api/cotraitants/project/{pid}", headers=h).json()
    assert len(links) == 1 and links[0]["id"] == ct["id"]
    assert links[0]["source"] == "simulation" and links[0]["role"] == "cotraitant"
    assert links[0]["capacites_source"] == "declare" and links[0]["ca_n1"] == 400000

    st = client.get(_url(pid, "state"), headers=h).json()
    assert st["state"] == "composition" and st["decision"] == "go_groupement"
    assert st["score_seul"] == seul and st["score_groupement"] == sim["score_groupement"]
    hist = client.get(_url(pid, "simulations"), headers=h).json()
    assert hist[0]["retained"] is True

    # Retenir à nouveau : pas de doublon de liaison.
    assert client.post(_url(pid, "retenir"), headers=h, json={"simulation_id": sim["simulation_id"]}).status_code == 200
    assert len(client.get(f"/api/cotraitants/project/{pid}", headers=h).json()) == 1


# ── 5) Retirer le plan : verdict seul restauré, partenaire conservé ──────────────────

def test_delete_plan_restaure_le_verdict_seul(client, auth):
    h = auth["headers"]
    pid, seul, dec = _seed_project(client, h)
    ct = _add_partner(client, h)
    sim = client.post(_url(pid, "simulate"), headers=h,
                      json={"members": [{"kind": "annuaire", "id": ct["id"]}]}).json()
    client.post(_url(pid, "retenir"), headers=h, json={"simulation_id": sim["simulation_id"]})

    r = client.delete(_url(pid, "plan"), headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["decision"] == dec == "a_etudier"
    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["go_decision"] == "a_etudier" and p["match_score"] == seul
    st = client.get(_url(pid, "state"), headers=h).json()
    assert st["plan"] is None and st["score_groupement"] is None and st["state"] == "seul"
    # Avertir, pas bloquer : le partenaire rattaché reste en place.
    assert len(client.get(f"/api/cotraitants/project/{pid}", headers=h).json()) == 1
    assert client.get(_url(pid, "simulations"), headers=h).json()[0]["retained"] is False


# ── 6) Isolation : un autre compte reçoit 404 partout ────────────────────────────────

def test_isolation_autre_compte_404(client, auth):
    h = auth["headers"]
    pid, _, _ = _seed_project(client, h)
    ct = _add_partner(client, h)
    sim = client.post(_url(pid, "simulate"), headers=h,
                      json={"members": [{"kind": "annuaire", "id": ct["id"]}]}).json()
    o = _register(client)
    assert client.get(_url(pid, "besoins"), headers=o).status_code == 404
    assert client.get(_url(pid, "state"), headers=o).status_code == 404
    assert client.get(_url(pid, "simulations"), headers=o).status_code == 404
    assert client.post(_url(pid, "simulate"), headers=o,
                       json={"members": [{"kind": "annuaire", "id": ct["id"]}]}).status_code == 404
    assert client.post(_url(pid, "retenir"), headers=o,
                       json={"simulation_id": sim["simulation_id"]}).status_code == 404
    assert client.delete(_url(pid, "plan"), headers=o).status_code == 404
    # Et rien n'a bougé côté propriétaire.
    assert client.get(_url(pid, "state"), headers=h).json()["decision"] == "a_etudier"


# ── 7) Accroche /analyze-upload (LLM simulé) ─────────────────────────────────────────

def test_analyze_upload_pose_go_groupement_et_garde_le_score_seul(client, auth, monkeypatch):
    h = auth["headers"]
    pid, seul, _ = _seed_project(client, h)
    ct = _add_partner(client, h)

    from app.services import llm
    llm._CB["fails"] = 0; llm._CB["open_until"] = 0.0
    llm._TENANT_CB.clear()
    payload = json.dumps({"match_score": 50, "go_decision": "a_etudier",
                          "summary": "Analyse simulée.", "details": DETAILS})

    class _Resp:
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 20})()
        content = [type("B", (), {"text": payload})()]

    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    monkeypatch.setattr(llm, "client", lambda: type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _Resp())})}))

    dce = ("Règlement de la consultation — rénovation thermique et étanchéité du groupe scolaire. "
           "Chiffre d'affaires minimum 300 000 EUR. Qualification Qualibat 1512 exigée. " * 4).encode("utf-8")
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("dce.txt", dce, "text/plain")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["score"] == seul, "score = SEUL (déterministe, jamais gonflé)"
    assert j["decision"] == "go_groupement"
    assert j["groupement"]["decision"] == "go_groupement"
    assert j["groupement"]["score_groupement"] > seul
    assert j["groupement_score"] == j["groupement"]["score_groupement"]
    assert [m["name"] for m in j["groupement"]["members"]] == [PARTNER["name"]]
    assert j["groupement"]["members"][0]["id"] == ct["id"]
    w0 = j["groupement"]["warnings"]
    assert "capacités déclarées par vous" in w0[0] and sum("déclarées" in w for w in w0) == 1

    p = client.get(f"/api/projects/{pid}", headers=h).json()
    assert p["match_score"] == seul and p["go_decision"] == "go_groupement"
    assert p["ai_analysis"]["groupement"]["decision"] == "go_groupement"
    st = client.get(_url(pid, "state"), headers=h).json()
    assert st["plan"]["auto"] is True and st["score_groupement"] == j["groupement_score"]
    assert st["state"] == "potentiel"   # plan AUTO (calculé à l'analyse) = potentiel ; « composition » = retenue par le mandataire

    llm._CB["fails"] = 0; llm._CB["open_until"] = 0.0


# ── 8) Export RGPD : les simulations sont portables ──────────────────────────────────

def test_export_rgpd_inclut_les_simulations(client, auth):
    h = auth["headers"]
    pid, _, _ = _seed_project(client, h)
    ct = _add_partner(client, h)
    sim = client.post(_url(pid, "simulate"), headers=h,
                      json={"members": [{"kind": "annuaire", "id": ct["id"]}]}).json()
    r = client.get("/api/rgpd/export", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()["simulations_groupement"]
    assert any(s["id"] == sim["simulation_id"] and s["project_id"] == pid for s in rows)
