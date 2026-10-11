"""
Vocabulaire : « chef de file », jamais « mandataire », dans ce que voit l'utilisateur.

Règle produit : l'entreprise qui pilote le groupement s'appelle « chef de file » à l'écran, dans
les emails, les notifications, le journal du partenaire (écran, PDF) et les messages d'erreur.
Restent volontairement « mandataire » :
- le CORPS de la convention de groupement (texte scellé : ses empreintes ne doivent pas bouger,
  sinon chaque convention figée en production deviendrait « plus à jour ») ;
- les mentions juridiques secondaires, après la formule simple (« · Mandataire solidaire ») ;
- les formulaires officiels (DC1, DC2, ATTRI1) ;
- les identifiants : codes de rôle, clés JSON, valeurs en base, classes CSS, et la valeur `qui`
  du journal exporté (elle entre dans les maillons : seul son AFFICHAGE change).
"""
import json
import os
import re

import pytest

from tests.test_convention_groupement import _pdf_text
from tests.test_cotraitance_v4 import _scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOT = re.compile(r"mandataire", re.IGNORECASE)


def _static(name: str) -> str:
    with open(os.path.join(ROOT, "app", "static", name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


@pytest.fixture
def no_llm(monkeypatch):
    import app.services.llm as llm

    def boom(*a, **k):
        raise AssertionError("appel LLM interdit")
    monkeypatch.setattr(llm, "messages_create", boom)
    monkeypatch.setattr(llm, "client", boom)


@pytest.fixture(autouse=True)
def _fresh():
    from app.services import audit_anchor
    from app.services import journal_membre as jm
    jm.reset_caches()
    audit_anchor.reset_cache()
    yield
    jm.reset_caches()
    audit_anchor.reset_cache()


# ═══ 1. Texte scellé de la convention : empreintes figées ════════════════════════════════
# Valeurs relevées AVANT le passage à « chef de file » : render() n'a pas bougé d'un octet.

def _members(lead_name="Breizh Couverture", hors_ligne=False):
    m = [
        {"kind": "mandataire", "invite_id": None, "link_id": None, "company": lead_name,
         "siret": "12345678900011", "address": "1 rue du Port", "postal_code": "56100", "city": "Lorient",
         "representant_legal": "Eliot Viegas", "signataire_qualite": "Président", "role": "mandataire",
         "lot": "Lot 1", "prix_lot_ht": 60000.0},
        {"kind": "invite", "invite_id": 7, "link_id": None, "company": "Le Gall Électricité",
         "siret": "98765432100022", "address": "", "postal_code": "", "city": "Quimper",
         "representant_legal": "Jean Le Gall", "signataire_qualite": "Gérant", "role": "cotraitant",
         "lot": "Lot 2", "prix_lot_ht": 40000.5},
    ]
    if hors_ligne:
        m.append({"kind": "hors_ligne", "invite_id": None, "link_id": 3, "company": "Kerné *Bois*",
                  "siret": "", "address": "", "postal_code": "", "city": "",
                  "representant_legal": "", "signataire_qualite": "", "role": "cotraitant",
                  "lot": "", "prix_lot_ht": None})
    return m


_ALT = {"decision": "majorite", "delai_reponse_jours": 12, "defaillance": "reprise_par_les_autres",
        "sortie_preavis_jours": 0, "confidentialite_annees": 1, "pi": "copropriete",
        "penalites": "prorata", "assurances_travaux": False, "litiges": "mediation_puis_tribunal"}

EMPREINTES = [
    # (forme, mandataire_solidaire, brouillon, paramètres alternatifs, habilitation minimale,
    #  membre hors ligne, masque) → sha256(render)
    (("conjoint", True, False, False, False, False, "none"),
     "91c6ffe036009e056ab72aa1f0fe3dbcd02ba018a96faf201ae363f76a76d3e2"),
    (("conjoint", False, True, False, False, True, "member"),
     "102f07659a9f680d74b31e43b81b5ad81ef01bffed9f8670cb7a52bd4c9334b9"),
    (("solidaire", False, False, True, True, False, "none"),
     "0c557203cadb2cf538093552dfacbc2e62e9c0019975cc634c996063c5a9d69c"),
    (("solidaire", True, False, False, False, False, "all"),
     "95dfe20d4bb056cf3a584d8c04483616d29d732cd30606ce27f7d5a132da87ae"),
    (("", False, True, True, False, False, "none"),
     "78584fa2eb8c414317e9ba957742b251bd3cc0b8dd5da2eb2fe12d1a5d8667c3"),
]


@pytest.mark.parametrize("cas,attendu", EMPREINTES)
def test_texte_scelle_de_la_convention_inchange(cas, attendu):
    from app.services import groupement_convention as gc
    forme, ms, brouillon, alt, hab_min, hl, mask = cas
    defaults = {p["key"]: p["defaut"] for p in gc.PARAMS}
    hab = gc.default_habilitation()
    if hab_min:
        hab = {k: (k == "representer") for k in hab}
    mem = _members(hors_ligne=hl)
    ctx = {"version": 3, "marche": {"objet": "École Jules-Ferry", "acheteur": "Ville de Lorient",
                                    "reference": "AO-0042"},
           "forme": forme, "mandataire_solidaire": ms, "habilitation": hab,
           "params": ({**defaults, **_ALT} if alt else {**defaults, "assurances_travaux": True}),
           "members": mem, "total_ht": gc.total_of(mem), "brouillon": brouillon}
    assert gc.sha256(gc.render(ctx, mask=mask, viewer_invite_id=7)) == attendu


def test_texte_scelle_repli_du_nom_du_chef_de_file_inchange():
    """Le repli « Le mandataire » (nom d'entreprise absent) fait partie du texte scellé."""
    from app.services import groupement_convention as gc
    ctx = {"version": 1, "marche": {}, "forme": "conjoint", "mandataire_solidaire": False,
           "habilitation": gc.default_habilitation(), "params": {p["key"]: p["defaut"] for p in gc.PARAMS},
           "members": _members(lead_name=""), "total_ht": None}
    assert gc.sha256(gc.render(ctx)) == "64e68c0a8423477f462f9b6c5fd8178c8d9a9677fa7228202d61eb0ceb102f80"
    ctx["members"] = [m for m in ctx["members"] if m["role"] != "mandataire"]
    assert gc.sha256(gc.render(ctx)) == "3ce24a91f7f50eb4b891910d1763e0cfcc8fba33ae5dc72e8c373eb19ab951f0"


# ═══ 2. Libellés générés côté serveur ════════════════════════════════════════════════════

def test_libelles_du_journal_disent_chef_de_file():
    from app.services import journal_membre as jm
    for table in (jm.LABELS_ME, jm.LABELS_OWNER, jm.LABELS_PARTNER):
        for action, label in table.items():
            assert not MOT.search(label), (action, label)
    assert jm.LABELS_OWNER["offer.frozen"] == "Le chef de file a figé l'offre commune"
    assert jm._WHO["mandataire"] == "Chef de file"


def test_convention_libelles_hors_texte_scelle():
    from types import SimpleNamespace
    from app.services import groupement_convention as gc
    # Option « chef de file solidaire » : la formule simple d'abord, le terme officiel ensuite (b).
    opt = gc.MANDATAIRE_SOLIDAIRE
    assert not MOT.search(opt["phrase"]) and not MOT.search(opt["explication"])
    assert opt["terme"] == "Mandataire solidaire"
    assert all(not MOT.search(v) for v in gc.IDENTITY_LABELS.values())
    # « Accords enregistrés » (hors empreinte) : rôle affiché « chef de file ».
    conv = SimpleNamespace(content_hash="e" * 64, version=1, frozen_at=None)
    sig = SimpleNamespace(company_name="Breizh Couverture", invite_id=None, cotraitant_link_id=None,
                          status="pending", signataire_nom="", signataire_qualite="", identity_level="",
                          signed_at=None)
    md = gc.accords_md(conv, [sig])
    assert "- Breizh Couverture (chef de file) — accord en attente" in md
    assert not MOT.search(md)


def test_avertissement_mandataire_solidaire_formule_simple_d_abord():
    from types import SimpleNamespace
    from app.services import groupement_convention as gc
    project = SimpleNamespace(estimate={}, groupement_plan={}, id=1)
    conv = SimpleNamespace(params={}, habilitation={}, forme="conjoint", mandataire_solidaire=False)
    fi = {"forme_imposee": "conjoint",
          "extrait": "En cas de groupement conjoint, le mandataire sera solidaire de chacun des membres."}
    ctx = {"forme": "conjoint", "mandataire_solidaire": False, "members": []}
    w = [x for x in gc.warnings_for(conv, project, ctx, fi, []) if "solidaire" in x]
    assert w == ["La phrase citée du règlement parle d'un chef de file solidaire (« mandataire solidaire ») : "
                 "vérifiez s'il faut cocher l'option « Le chef de file répond aussi de la part de chaque "
                 "partenaire »."]


def test_journal_partenaire_ecran_json_pdf(client, auth, mails, no_llm):
    """Écran et PDF : « chef de file ». JSON : la valeur `qui` reste le code « mandataire » (elle
    entre dans les maillons) et l'export se vérifie toujours hors ligne."""
    from app.services import journal_membre as jm
    pid, a, b = _scenario(client, auth)
    ta = a["token"]
    entries = client.get(f"/api/invite/{ta}/journal").json()["entries"]
    owner = [e for e in entries if e["who"] == "mandataire"]
    assert owner and all(e["label"].startswith("Le chef de file ") for e in owner)
    assert not any(MOT.search(e["label"]) for e in entries)

    doc = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    assert jm.verify_export(doc)["ok"] is True
    assert any(e["qui"] == "mandataire" for e in doc["entrees"])
    assert not any(MOT.search(e["label"]) for e in doc["entrees"])

    pdf = client.get(f"/api/invite/{ta}/journal/export?format=pdf")
    assert pdf.status_code == 200
    flat = " ".join(_pdf_text(pdf.content).split())
    assert "Chef de file" in flat and "Le chef de file a consulté votre part" in flat
    assert not MOT.search(flat)


def test_compte_rendu_pdf_chef_de_file():
    from app.services.consortium_report import generate_consortium_report_pdf
    pdf = generate_consortium_report_pdf("AO", "Breizh Couverture", {"readiness": {}, "partners": [], "lots": []}, [])
    flat = " ".join(_pdf_text(pdf).split())
    assert "Chef de file : Breizh Couverture" in flat
    assert not MOT.search(flat) and "consortium" not in flat.lower()


# ═══ 3. Pages servies (partenaire et chef de file) ═══════════════════════════════════════

def test_pages_partenaire_sans_mandataire_visible():
    inv = _static("invite.html")
    for old in ("Soumettre au mandataire", "Message au mandataire", "visible par le mandataire",
                "Illisible par le mandataire", "Le mandataire est prévenu", "le mandataire sera prévenu",
                "· mandataire (chef de file)", "calculé par le mandataire", "soumise à ' + esc(d.mandataire || \"le mandataire\")"):
        assert old not in inv, old
    for new in ("Soumettre au chef de file", "Message au chef de file (optionnel)",
                'mandataire: "chef de file"', "Seul montant visible par le chef de file."):
        assert new in inv, new
    # Le libellé officiel reste après la formule simple ; la lecture de l'annexe scellée aussi.
    assert "· Mandataire solidaire" in inv and "mandataire \\(chef de file\\)" in inv

    crypto = _static("cotraitance-crypto.js")
    labels = crypto[crypto.index("LABELS"):]
    labels = labels[:labels.index("}")]
    assert not MOT.search(labels), labels

    app_html = _static("app.html")
    assert "'Le chef de file n\\'a pas encore calculé le score du groupement.'" in app_html
    assert "(e.who==='mandataire'?'Chef de file':'Partenaire')" in app_html
    assert "'Mandataire'" not in app_html and "'Le mandataire" not in app_html


def test_avertissement_solidaire_n_affirme_pas_ce_que_dit_la_citation():
    """L'avertissement se déclenche sur les seuls mots « mandataire » et « solidaire » : il doit
    rester neutre (« parle d'un »), même quand la phrase citée dit le contraire."""
    from types import SimpleNamespace
    from app.services import groupement_convention as gc
    project = SimpleNamespace(estimate={}, groupement_plan={}, id=1)
    ctx = {"forme": "conjoint", "mandataire_solidaire": False, "members": []}
    fi = {"extrait": "En cas de groupement conjoint, le mandataire ne sera pas solidaire des autres membres."}
    w = [x for x in gc.warnings_for(None, project, ctx, fi, []) if "solidaire" in x]
    assert len(w) == 1 and w[0].startswith("La phrase citée du règlement parle d'un chef de file solidaire")
    assert not re.search(r"\b(demande|impose|exige)\b", w[0]), w[0]


# ═══ 4. Emails sans nom d'entreprise du chef de file : « du / au chef de file » ═══════════

def test_emails_sans_nom_du_chef_de_file_bien_construits(client, auth, mails, monkeypatch):
    """Profil entreprise sans nom : le repli se construit avec « de » et « à » (« du chef de
    file », « au chef de file »), jamais « de le chef de file » ni « à le chef de file »."""
    import app.services.alerts as al
    import app.services.email as email_mod
    from tests.test_convention_groupement import _db, _set_company
    from tests.test_cotraitance_v4 import _alert_project
    _set_company(auth["email"], name="")
    sent = []
    monkeypatch.setattr(al, "send_email", lambda to, subj, body: sent.append((to, subj, body)) or True)
    monkeypatch.setattr(email_mod, "send_email", lambda to, subj, body, *a, **k: sent.append((to, subj, body)) or True)
    _p1, (relance,) = _alert_project(client, auth, days=3, n_partners=1, submit=False)
    _p2, (attest,) = _alert_project(client, auth, days=3, n_partners=1, submit=True)
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    by_to = {}
    for to, _subj, body in sent:
        by_to.setdefault(to, []).append(body)
    # Relance de part (attestations jointes) et alerte d'attestations seule.
    assert any("pour ajouter votre part au groupement du chef de file sur le marché" in b
               for b in by_to[relance["recipient"]]), by_to[relance["recipient"]]
    assert any("le groupement du chef de file a besoin de vos attestations à jour" in b
               for b in by_to[attest["recipient"]]), by_to[attest["recipient"]]
    # Accusé de réception au partenaire qui soumet sa part.
    assert any("a bien été transmise au chef de file." in b for b in by_to[attest["recipient"]])
    flat = " ".join(b for _to, _s, b in sent)
    assert "de le chef de file" not in flat and "à le chef de file" not in flat
    assert not MOT.search(flat)


def test_ancienne_convention_de_secours_sans_faute_d_accord():
    from app.services.agents.redaction import _groupement_convention
    md = _groupement_convention({}, [{"name": "Martin SAS", "role": "sous_traitant", "lot": "Lot 2"}],
                                {"intitule_marche": "École", "acheteur": "Ville"})
    assert "Est désigné chef de file (mandataire du groupement) : Entreprise à préciser." in md
    assert "Le chef de file représente l'ensemble des membres" in md
    assert "est désigné" not in md and "Il représente" not in md
    md2 = _groupement_convention({"name": "Breizh Couverture"}, [], {})
    assert "Est désigné chef de file (mandataire du groupement) : Breizh Couverture." in md2
