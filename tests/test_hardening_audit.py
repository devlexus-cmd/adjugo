"""
Invariants des correctifs de durcissement (2e vague d'audit).

Couvre la logique DÉTERMINISTE ajoutée en remédiation :
  - Sourcing : rescale du score sur critères disponibles, match CPV délimité,
    procédure restreinte, has_more sur le brut.
  - Veille amont : ancrage anti-hallucination (_anchor), scoring de zone via dept.
  - Consortium : _parse_amount des formats compacts, classification des pièces.
  - Audit RGPD : chaîne de hash tamper-evidence.
Tests PURS (aucun LLM, aucune base).
"""
from app.sourcing.scoring import score_tender
from app.sourcing.schemas import NormalizedTender, Provenance
from app.services.agents.amont import _anchor, score_pertinence
from app.services.agents.redaction import _parse_amount
from app.routers.invites import _classify_partner_pieces


def _tender(**kw):
    base = dict(objet="Travaux de toiture", acheteur="Mairie", cpv=["45261000"],
                date_publication="2026-06-01", date_limite="2099-01-01", lieu="Quimper",
                departements=["29"], procedure="Procédure adaptée", nature="travaux",
                provenance=Provenance(source="BOAMP", source_url="x", official_ref="1"))
    base.update(kw)
    return NormalizedTender(**base)


# ── Sourcing : scoring ──────────────────────────────────────────────────────
def test_score_rescale_montant_inconnu_ne_plafonne_pas():
    """Une donnée absente (montant) est exclue du dénominateur : un AO qui matche tout
    le reste atteint 100, plus de plafond mécanique à 85."""
    crit = {"codes_cpv": ["45261"], "specialites": ["toiture"], "departements": ["29"],
            "budget_min": 0, "budget_max": 1_000_000}
    s = score_tender(_tender(montant_estime=None), {}, crit)
    assert s.total == 100
    assert any(c.key == "montant" and c.status == "inconnu" for c in s.breakdown)


def test_cpv_pas_de_faux_positif():
    """Un CPV non lié (médical 33600 vs toiture 45261) ne doit pas matcher."""
    crit = {"codes_cpv": ["33600"], "specialites": ["scanner"], "departements": ["75"]}
    cpv = [c for c in score_tender(_tender(), {}, crit).breakdown if c.key == "cpv"][0]
    assert cpv.points == 0


def test_cpv_match_prefixe_delimite():
    crit = {"codes_cpv": ["45261"], "departements": ["29"]}
    cpv = [c for c in score_tender(_tender(cpv=["45261000"]), {}, crit).breakdown if c.key == "cpv"][0]
    assert cpv.points > 0


def test_procedure_restreinte_partielle():
    crit = {"codes_cpv": ["45261"], "departements": ["29"]}
    proc = [c for c in score_tender(_tender(procedure="Procédure restreinte"), {}, crit).breakdown
            if c.key == "procedure"][0]
    assert proc.status == "partiel" and proc.points < proc.max_points


# ── Veille amont : ancrage anti-hallucination ───────────────────────────────
def test_anchor_efface_budget_invente_sur_titre():
    p = {"budget": 300000, "budget_texte": "300 000 €", "echeance_ao": "2026", "financement": "subvention"}
    out = _anchor(dict(p), "Réfection de la toiture de l'école", title_only=True)
    assert out["budget"] is None           # aucun chiffre dans la source
    assert out["echeance_ao"] == ""        # échéance devinée → effacée en mode titre
    assert out["financement"] == ""        # terme de financement absent de la source


def test_anchor_conserve_budget_reellement_present():
    out = _anchor({"budget": 50000, "budget_texte": "50 000€", "financement": "subvention", "echeance_ao": ""},
                  "Travaux voirie 50 000 € financés par subvention DETR", title_only=True)
    assert out["budget"] == 50000
    assert out["financement"] == "subvention"


def test_amont_zone_lit_dept():
    score, _ = score_pertinence({"intitule": "x", "dept": "29", "localisation": ""},
                                {"departements": ["29"], "specialites": ""})
    assert score >= 25   # le bonus zone (25) doit être inclus


# ── Consortium : montants compacts + classification pièces ──────────────────
def test_parse_amount_formats_compacts():
    assert _parse_amount("8 M€ HT") == 8_000_000
    assert _parse_amount("1,5 M€") == 1_500_000
    assert _parse_amount("300 000 €") == 300_000
    assert _parse_amount("300 k€") == 300_000
    assert _parse_amount("2,3 Md€") == 2_300_000_000
    assert _parse_amount("") == 0


def test_classification_pieces_pas_de_faux_positif():
    r = _classify_partner_pieces(["registre_de_securite.pdf"])
    assert "Kbis" not in r["have"]
    r2 = _classify_partner_pieces(["extrait_kbis_2026.pdf", "attestation_urssaf.pdf"])
    assert "Kbis" in r2["have"]


# ── Audit RGPD : chaîne de hash tamper-evidence ─────────────────────────────
def test_audit_hash_chain_detecte_falsification():
    from app.services.audit import _hash, _ts

    class Row:
        def __init__(self, i, det):
            self.id, self.created_at, self.owner_id, self.project_id = i, None, 1, 1
            self.actor = self.actor_kind = self.action = self.target_type = ""
            self.target_id, self.detail, self.ip = None, det, ""

    a = Row(1, "original")
    h = _hash("", a)
    a.detail = "falsifié"
    assert _hash("", a) != h        # toute modification casse le hash
    assert _ts(None) == ""
