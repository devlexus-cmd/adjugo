"""
Démo : le groupement du gymnase de Kerhel montré de bout en bout (app/services/demo_groupement.py).

Le marché vitrine du groupement s'arrêtait à « Réunir les parts » (convention « Pas encore préparée »,
forme « Non vérifié », « Avant de déposer : 1 contrôle sur 4 ») alors que la session démo ne peut rien
écrire. Le seed le remplit avec le code des routes, sans IA ni réseau. Vérifié ici par l'API, en session
démo (DEMO_PUBLIC=1 de la suite, puis lien privé) :
  - la forme du groupement est celle du règlement fictif, phrase citée et vérifiée par la garde des
    citations ; les exigences du marché (chiffre d'affaires, qualification SS3, cumul) sont citées ;
  - la convention est générée (offre figée, empreinte) et validée par le chef de file et le partenaire ;
  - DC1, DC2 et ATTRI1 sont remplis après elle ; « Avant de déposer » : 3 contrôles sur 4, l'attestation
    URSSAF du chef de file en alerte ; le marché n'est pas déposé ;
  - le partenaire voit la même chose par son lien (convention, total, accords, journal intact) ;
  - rien de la vitrine du groupement ne peut être défait par un visiteur ;
  - aucun appel à l'IA ; seed rejouable deux fois à l'identique, sans fichier nouveau, isolé dans sa
    transaction.
"""
import hashlib
import re

import pytest

from app.core.database import SessionLocal
from tests.test_demo_sans_cout import _cle_neuve, espions  # noqa: F401  (fixture)

URSSAF = "Votre Attest. sociale (URSSAF), dans Mes documents, expire avant la date limite"   # réunion 2a : le nom de l'écran


def _db():
    return SessionLocal()


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _remise_a_neuf():
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def _vitrine_remise_a_neuf(client):
    """Vitrine remise à neuf avant et après ce module, comme au démarrage du serveur."""
    _remise_a_neuf()
    yield
    _remise_a_neuf()


def _ctx() -> dict:
    """Identifiants du marché de Kerhel tels qu'en base (ils changent à chaque remise à neuf)."""
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        k = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        inv = db.query(ProjectInvite).filter(ProjectInvite.project_id == k.id).one()
        return {"uid": u.id, "pid": k.id, "token": inv.token}
    finally:
        db.close()


@pytest.fixture(scope="module")
def demo(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    return {"h": _h(r.json()["access_token"]), "ctx": _ctx()}


def _texte_du_dossier() -> str:
    from app.services import demo_groupement as dg
    from app.services.dce_lecture import lire_dossier
    return "\n".join(p["texte"] for p in lire_dossier(dg.DCE_NOM, dg.dossier_zip(), mode="direct")["pieces"])


# ── Écrans (réutilisés avec une session ouverte par le lien privé) ────────────────────────────────

def ecran_forme_du_groupement_citee(client, d):
    """« Ce que le règlement impose » : la forme lue dans le règlement, avec SA phrase, vérifiée."""
    from app.services import demo_groupement as dg
    from app.services import groupement_convention as gc
    from app.services.analysis import citation_guard
    pid = d["ctx"]["pid"]
    cv = client.get(f"/api/projects/{pid}/groupement/convention", headers=d["h"]).json()
    fi = cv["forme_imposee"]
    assert fi["code"] == "libre" and fi["source"] == "analyse" and fi["dossier_disponible"] is True
    assert fi["libelle"] == gc.FORME_IMPOSEE_LABELS["libre"] and "Non vérifié" not in fi["libelle"]
    assert fi["extrait"] == dg.EXIGENCE_FORME and fi["clauses"] == [dg.EXIGENCE_FORME]
    assert citation_guard(_texte_du_dossier(), fi["extrait"]) == dg.EXIGENCE_FORME
    det = client.get(f"/api/projects/{pid}", headers=d["h"]).json()["ai_analysis"]["details"]
    assert det["exigences_verifiees"]["forme_groupement"] is True
    # La forme choisie suit le règlement : conjoint, chef de file solidaire comme la phrase le demande.
    assert cv["forme"] == "conjoint" and cv["mandataire_solidaire"] is True
    assert not [w for w in cv["avertissements"] if "solidaire" in w or "ne correspond pas" in w]
    assert cv["habilitation"] == gc.default_habilitation()


def ecran_exigences_citees(client, d):
    """Chiffre d'affaires, qualification SS3, cumul des capacités : écrits dans le règlement, cités ;
    visite obligatoire lue dans le dossier ; « Dossier lu en entier »."""
    from app.services import demo_groupement as dg
    from app.services.analysis import citation_guard
    pid = d["ctx"]["pid"]
    p = client.get(f"/api/projects/{pid}", headers=d["h"]).json()
    a, det = p["ai_analysis"], p["ai_analysis"]["details"]
    assert a["couverture"]["message"].startswith("Dossier lu en entier : 4 pièces")
    for cle, phrase in (("ca_minimum_requis", dg.EXIGENCE_CA), ("qualifications_requises", dg.EXIGENCE_QUALIFICATIONS),
                        ("capacites_groupement", dg.EXIGENCE_CAPACITES)):
        assert det["exigences_verifiees"][cle] is True, cle
        assert det["exigences_sources"][cle] == phrase, cle
    texte = _texte_du_dossier()
    for phrase in (dg.EXIGENCE_CA, dg.JUSTIFICATION_CA, dg.EXIGENCE_QUALIFICATIONS, dg.EXIGENCE_CAPACITES,
                   dg.EXIGENCE_FORME, dg.EXIGENCE_VISITE):
        assert citation_guard(texte, phrase), phrase
    # Ce que la fiche affiche correspond à ce que le règlement écrit.
    assert "3 000 000" in det["ca_minimum_requis"] and "3 000 000" in dg.EXIGENCE_CA
    assert all(q.lower() in dg.EXIGENCE_QUALIFICATIONS.lower() for q in det["qualifications_requises"])
    assert det["visite_obligatoire"].startswith("Obligatoire — 05/12/2026") and "5 décembre 2026" in dg.EXIGENCE_VISITE
    g = det["grille_notation"]
    assert [x["statut"] for x in g["criteres"]] == ["retrouve", "retrouve"]
    assert g["controle_total"]["statut"] == "ok" and g["contraintes"]["visite"]["obligatoire"] is True
    # Même barème qu'avant : seul 43, « Bon potentiel en groupement » avec Breizh Désamiantage.
    assert p["match_score"] == 43 and p["go_decision"] == "go_groupement" and p["groupement_score"] > 43
    # « Répondre à plusieurs ? » : la phrase du dossier sous ce qui manque.
    b = client.get(f"/api/projects/{pid}/groupement/besoins", headers=d["h"]).json()
    gaps = {x["key"]: x for x in b["gaps"]}
    assert gaps["capacite"]["severity"] == "bloquant" and gaps["capacite"]["extrait"] == dg.EXIGENCE_CA
    assert gaps["qualifs"]["extrait"] == dg.EXIGENCE_QUALIFICATIONS


def ecran_convention_generee_et_validee(client, d):
    """Convention générée (offre figée, empreinte unique) et validée par les deux membres."""
    from app.services import demo_groupement as dg
    pid = d["ctx"]["pid"]
    cv = client.get(f"/api/projects/{pid}/groupement/convention", headers=d["h"]).json()
    assert cv["status"] == "signee" and cv["status_label"] == "Validée par tous les membres"
    assert cv["version"] == 1 and cv["manques"] == []
    assert cv["content_hash"] == hashlib.sha256(cv["content_md"].encode("utf-8")).hexdigest()
    assert cv["frozen_at"] and cv["total_offre_ht"] == 1250000.0
    parts = {m["company"]: (m["membre"], m["lot"], m["prix_lot_ht"]) for m in cv["membres"]}
    assert parts == {"Bâtiment de l'Ouest": ("mandataire", dg.LOT_CHEF_DE_FILE, 970000.0),
                     "Breizh Désamiantage": ("partenaire", "Lot 1 — Désamiantage et retrait d'amiante (SS3)", 280000.0)}
    assert cv["params"]["part_mandataire_ht"] == 970000.0 and cv["params"]["lot_mandataire"] == dg.LOT_CHEF_DE_FILE
    assert cv["n_signataires"] == cv["n_accords"] == 2
    sigs = {s["company"]: s for s in cv["signatures"]}
    chef, part = sigs["Bâtiment de l'Ouest"], sigs["Breizh Désamiantage"]
    assert chef["status"] == part["status"] == "signed"
    assert chef["status_label"] == part["status_label"] == "Accord enregistré"
    assert (chef["membre"], chef["signataire_nom"], chef["signataire_qualite"]) == \
        ("mandataire", "Gwénaël Le Bihan", "Gérant")
    assert (part["membre"], part["signataire_nom"], part["signataire_qualite"]) == \
        ("partenaire", "Soizic Morvan", "Présidente")
    # Niveau d'identité réellement prouvé : aucun code de vérification n'est simulé pour le partenaire.
    assert chef["identity_level"] == "compte_verifie" and part["identity_level"] == "lien_seul"
    assert cv["ma_signature"]["status"] == "signed" and cv["ma_signature"]["peut_valider"] is False
    # Texte figé : les deux parts, le total, la forme, le chef de file solidaire.
    texte = cv["content_md"]
    assert "Total de l'offre commune : 1 250 000 € HT" in texte
    assert "970 000 € HT" in texte and "280 000 € HT" in texte
    assert "Le groupement est **conjoint**" in texte and "Le mandataire est **solidaire**" in texte
    # Relire la convention ne la rend pas caduque (le texte figé correspond aux faits).
    cv2 = client.get(f"/api/projects/{pid}/groupement/convention", headers=d["h"]).json()
    assert cv2["status"] == "signee" and cv2["content_hash"] == cv["content_hash"]
    pdf = client.get(f"/api/projects/{pid}/groupement/convention/pdf", headers=d["h"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Étapes : « Monter le groupement » fait, « Déposer » en cours (pas marqué déposé).
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=d["h"]).json()
    assert st["state"] == "pret_a_deposer" and st["label"] == "Convention validée — derniers contrôles avant dépôt"
    assert [(e["label"], e["status"]) for e in st["etapes"]] == [
        ("Repérer le marché", "fait"), ("Trouver les partenaires", "fait"), ("Réunir les parts", "fait"),
        ("Monter le groupement", "fait"), ("Déposer", "en_cours")]
    assert st["offer_frozen"] is True and st["total_offre_ht"] == 1250000.0
    assert st["convention"]["toutes_validees"] is True


def ecran_formulaires_et_avant_de_deposer(client, d):
    """DC1, DC2, ATTRI1 remplis après la convention ; « Avant de déposer » : 3 contrôles sur 4, l'URSSAF
    du chef de file expire avant la date limite (alerte gardée) ; marché non déposé."""
    pid = d["ctx"]["pid"]
    cerfa = {x["id"]: x["status"] for x in client.get(f"/api/cerfa/{pid}/status", headers=d["h"]).json()}
    assert cerfa["dc1"] == cerfa["dc2"] == cerfa["attri1"] == "pret"
    assert cerfa["dc4"] == "vide"                        # Breizh Désamiantage est co-traitant, pas sous-traitant
    dp = client.get(f"/api/projects/{pid}/groupement/depot", headers=d["h"]).json()
    assert dp["depose"] is False and dp["status"] != "depose"
    pret = dp["pret"]
    assert (pret["n_ok"], pret["n_total"], pret["pret"]) == (3, 4, False)
    assert pret["checks"] == {"parts_soumises": True, "attestations_ok": False, "convention_signee": True,
                              "cerfa_generes": True}
    assert pret["manques"] == [URSSAF] and pret["avertissements"] == []


def ecran_vue_du_partenaire(client, d):
    """Breizh Désamiantage, par son lien : même convention, même total, mêmes accords, journal intact."""
    pid, tok = d["ctx"]["pid"], d["ctx"]["token"]
    cv = client.get(f"/api/projects/{pid}/groupement/convention", headers=d["h"]).json()
    g = client.get(f"/api/invite/{tok}").json()
    st = g["for_member"]["state"]
    assert st["state"] == "pret_a_deposer" and st["total_offre_ht"] == 1250000.0
    assert st["convention"]["status"] == "signee" and st["convention"]["n_accords"] == 2
    assert [x["name"] for x in g["documents"]] == ["DCE — Réhabilitation énergétique du gymnase municipal.zip"]
    gc_ = client.get(f"/api/invite/{tok}/convention").json()
    assert gc_["status_label"] == "Validée par tous les membres"
    assert gc_["content_hash"] == cv["content_hash"] and gc_["content_md"] == cv["content_md"]
    assert gc_["total_offre_ht"] == cv["total_offre_ht"]
    assert gc_["membres"] == cv["membres"]
    assert [(s["company"], s["status"]) for s in gc_["signatures"]] == \
        [(s["company"], s["status"]) for s in cv["signatures"]]
    assert gc_["ma_signature"]["status"] == "signed" and gc_["ma_signature"]["peut_valider"] is False
    pdf = client.get(f"/api/invite/{tok}/convention/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    cc = client.get(f"/api/invite/{tok}/coffre-croise").json()
    assert [m["complete"] for m in cc["members"]] == [True]
    # Son journal raconte le groupement dans l'ordre, et la chaîne est intacte.
    j = client.get(f"/api/invite/{tok}/journal").json()
    assert j["chained"] is True
    seed = ("invite.created", "guest.submit_contribution", "offer.frozen", "convention.generated", "convention.signed")
    recit = [e["label"] for e in reversed(j["entries"]) if e["action"] in seed]   # hors consultations du test
    assert recit == ["Le chef de file vous a invité", "Vous avez soumis votre part",
                     "Le chef de file a figé l'offre commune",
                     "Le chef de file a généré la convention de groupement",
                     "Le chef de file a validé la convention (accord enregistré)",
                     "Vous avez validé la convention (accord enregistré)"]
    fige = next(e for e in j["entries"] if e["action"] == "offer.frozen")
    assert fige["detail"] == "total 1 250 000 € HT (convention v1)"
    vi = client.get(f"/api/invite/{tok}/journal/integrity").json()
    assert vi["verdict"] == "intact" and vi["entrees"]["alterees"] == 0
    assert client.get("/api/audit/integrity", headers=d["h"]).json()["intact"] is True


ECRANS = (ecran_forme_du_groupement_citee, ecran_exigences_citees, ecran_convention_generee_et_validee,
          ecran_formulaires_et_avant_de_deposer, ecran_vue_du_partenaire)


# ── Tests ─────────────────────────────────────────────────────────────────────────────────────────

def test_forme_du_groupement_verifiee_par_une_phrase_du_dossier(client, demo):
    ecran_forme_du_groupement_citee(client, demo)


def test_exigences_du_marche_citees_par_son_dossier(client, demo):
    ecran_exigences_citees(client, demo)


def test_convention_generee_et_validee_par_les_deux_membres(client, demo):
    ecran_convention_generee_et_validee(client, demo)


def test_formulaires_generes_apres_la_convention_et_avant_de_deposer(client, demo):
    from app.models import GeneratedDoc, GroupementConvention
    ecran_formulaires_et_avant_de_deposer(client, demo)
    db = _db()
    try:
        pid = demo["ctx"]["pid"]
        conv = db.query(GroupementConvention).filter(GroupementConvention.project_id == pid).one()
        for t in ("dc1", "dc2", "attri1"):
            g = db.query(GeneratedDoc).filter(GeneratedDoc.project_id == pid, GeneratedDoc.doc_type == t).one()
            assert g.updated_at >= conv.frozen_at, t
            assert (g.filled_data or {}).get("convention_version") == 1, t
    finally:
        db.close()


def test_vue_du_partenaire_coherente(client, demo):
    ecran_vue_du_partenaire(client, demo)


def test_le_visiteur_ne_peut_pas_defaire_le_groupement(client, demo):
    """Vitrine partagée : aucune action d'un visiteur ne rend la convention caduque pour les suivants."""
    pid, tok, h = demo["ctx"]["pid"], demo["ctx"]["token"], demo["h"]
    avant = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    for methode, url, corps in (
            ("PUT", f"/api/projects/{pid}/groupement/convention", {"forme": "solidaire", "confirmer_modification": True}),
            ("POST", f"/api/projects/{pid}/groupement/convention/generer", {"regenerer": True}),
            ("POST", f"/api/projects/{pid}/groupement/retenir", {"simulation_id": 1}),
            ("DELETE", f"/api/projects/{pid}/groupement/plan", None),
            ("DELETE", f"/api/projects/{pid}/offre/figer", None),
            ("POST", f"/api/projects/{pid}/groupement/deposer", {})):
        r = client.request(methode, url, headers=h, json=corps)
        assert r.status_code == 403 and "lecture guidée" in r.json()["detail"], (methode, url, r.text)
    r = client.put(f"/api/invite/{tok}/contribution", json={"prix_lot_ht": 1.0, "version": 1})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    r = client.post(f"/api/invite/{tok}/convention/valider",
                    json={"content_hash": avant["content_hash"], "signataire_nom": "x", "accepte": True})
    assert r.status_code == 403
    apres = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert apres["status"] == "signee" and apres["content_hash"] == avant["content_hash"]
    assert client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]["n_ok"] == 3


def test_textes_du_groupement_fictifs_et_sans_jargon(client, demo):
    """Dossier fictif (bandeau sur chaque pièce, acheteur jamais nommé, aucun téléphone) ; à l'écran,
    « groupement / partenaire / chef de file / valider » : ni « consortium », ni « signer », ni émoji."""
    from app.services import demo_groupement as dg
    from app.services import groupement_convention as gc
    from app.services.demo_redaction import BANDEAU
    from app.services.dce_lecture import lire_dossier
    lec = lire_dossier(dg.DCE_NOM, dg.dossier_zip(), mode="direct")
    assert len(lec["pieces"]) == 4 and all(p["statut"] == "lu_en_entier" for p in lec["pieces"])
    assert all(BANDEAU[:40] in re.sub(r"\s+", " ", p["texte"]) for p in lec["pieces"])
    assert dg.dossier_zip() == dg.dossier_zip()          # octets stables (clé de stockage)
    pieces = "\n".join(t for _n, titre, paras in dg.PIECES for t in [titre] + paras)
    for nom in ("Kerhel", "Agglomération", "Ville de", "Mairie", "Métropole", "Lorient"):
        assert nom not in pieces, nom
    assert not re.search(r"(?<!\d)0[1-9](?:[ .]?\d{2}){4}(?!\d)", pieces)
    ecran = [pieces, dg.LOT_CHEF_DE_FILE, " ".join(dg.ACCORD_CHEF_DE_FILE)]
    pid = demo["ctx"]["pid"]
    cv = client.get(f"/api/projects/{pid}/groupement/convention", headers=demo["h"]).json()
    ecran += [cv["status_label"], cv["forme_imposee"]["libelle"]] + cv["avertissements"] + \
             [s["status_label"] for s in cv["signatures"]] + [s["identity_label"] for s in cv["signatures"]]
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=demo["h"]).json()
    ecran += [st["label"]] + [e["label"] for e in st["etapes"]]
    dp = client.get(f"/api/projects/{pid}/groupement/depot", headers=demo["h"]).json()["pret"]
    ecran += list(dp["libelles"].values()) + dp["manques"]
    tout = "\n".join(ecran)
    for mot in ("consortium", "signer", "signature", "signé"):
        assert mot not in tout.lower(), mot
    assert "signer" not in pieces.lower() and "consortium" not in pieces.lower()
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", tout)
    assert gc.STATUS_LABELS["signee"] == "Validée par tous les membres"


def test_aucun_appel_ia_et_seed_rejoue_deux_fois_identique(client, demo, espions):  # noqa: F811
    """Le seed (et l'affichage du groupement) n'appellent jamais l'IA ; rejoué deux fois, il redonne
    la même vitrine (au numéro du marché près), sans doublon ni fichier nouveau dans le stockage."""
    from app.models import (AuditLog, Document, GeneratedDoc, GroupementConvention, GroupementSignature,
                            Project, User)
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo

    def photo(db):
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        k = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        pids = [p.id for p in db.query(Project).filter(Project.user_id == u.id).all()]
        convs = db.query(GroupementConvention).filter(GroupementConvention.project_id.in_(pids)).all()
        assert len(convs) == 1
        c = convs[0]
        ref = f"AO-{k.id:04d}"
        return {
            "convention": (c.status, c.version, c.forme, c.mandataire_solidaire, c.forme_imposee,
                           c.forme_imposee_extrait, c.total_offre_ht, c.content_md.replace(ref, "AO-n")),
            "accords": sorted((s.company_name, s.status, s.identity_level, s.signataire_nom, s.signataire_qualite)
                              for s in db.query(GroupementSignature).filter(
                                  GroupementSignature.project_id.in_(pids)).all()),
            "formulaires": sorted((g.doc_type, g.status) for g in
                                  db.query(GeneratedDoc).filter(GeneratedDoc.project_id == k.id).all()),
            "documents": sorted((d.name, d.file_key) for d in
                                db.query(Document).filter(Document.user_id == u.id).all()),
            "dossier": (k.dce_file_key, k.match_score, k.go_decision, k.groupement_score),
            "journal": [(a.action, a.actor_kind) for a in db.query(AuditLog).filter(
                AuditLog.project_id == k.id).order_by(AuditLog.id).all()],
            "offre": {x: (k.groupement_plan or {}).get("offre", {}).get(x) for x in ("total_ht", "lead_total_ht")},
        }

    db = _db()
    try:
        ensure_demo(db, force=True)
        avant = photo(db)
        espions["fichier"].clear()
        for _ in range(2):
            ensure_demo(db, force=True)
            assert photo(db) == avant
    finally:
        db.close()
    assert avant["convention"][:3] == ("signee", 1, "conjoint")
    assert avant["formulaires"] == [("attri1", "pret"), ("dc1", "pret"), ("dc2", "pret"), ("honneur", "pret")]
    assert avant["journal"] == [("invite.created", "owner"), ("guest.submit_contribution", "guest"),
                                ("offer.frozen", "owner"), ("convention.generated", "owner"),
                                ("convention.signed", "owner"), ("convention.signed", "guest")]
    assert avant["offre"] == {"total_ht": 1250000.0, "lead_total_ht": 970000.0}
    assert espions["fichier"] == []        # clés liées au contenu : rien de neuf à ranger au redémarrage
    # Les écrans du groupement, relus sans IA.
    d = {"h": demo["h"], "ctx": _ctx()}
    for ecran in ECRANS:
        ecran(client, d)
    assert espions["ia"] == [] and espions["email"] == [] and espions["reseau"] == []


def test_seed_du_groupement_isole_dans_sa_transaction(client, demo, monkeypatch):
    """Un échec du groupement laisse le reste de la vitrine intact : l'étape « convention » qui échoue
    ne laisse ni convention, ni accord, ni formulaire, ni dossier à moitié faits ; l'étape « dossier »
    qui échoue laisse l'analyse d'origine. Tout revient au redémarrage suivant."""
    from app.models import Document, GroupementConvention, Preuve, Project
    from app.routers import cerfa
    from app.services import demo_groupement as dg
    from app.services.demo_seed import ensure_demo

    def panne(*a, **k):
        raise RuntimeError("panne simulée")

    def kerhel(db, u):
        return next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)

    # 1) La convention échoue au dernier moment (formulaires) : rien de l'étape ne reste.
    monkeypatch.setattr(cerfa, "produire_formulaire", panne)
    db = _db()
    try:
        u = ensure_demo(db, force=True)
        k = kerhel(db, u)
        assert db.query(GroupementConvention).filter(GroupementConvention.project_id == k.id).count() == 0
        assert db.query(Document).filter(Document.project_id == k.id, Document.folder == "DCE").count() == 0
        assert k.status.value == "nouveau" and "offre" not in (k.groupement_plan or {})
        assert (k.ai_analysis or {})["details"]["forme_groupement"]["extrait"] == dg.EXIGENCE_FORME
        assert k.go_decision == "go_groupement"
        assert db.query(Preuve).filter(Preuve.owner_id == u.id).count() == 14     # rédaction intacte
    finally:
        db.close()
    monkeypatch.undo()
    pid = _ctx()["pid"]
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=demo["h"]).json()
    assert st["state"] == "parts_completes"

    # 2) Le dossier ne se lit pas : analyse d'origine, pas de convention, verdict de groupement intact.
    monkeypatch.setattr(dg, "dossier_zip", panne)
    db = _db()
    try:
        u = ensure_demo(db, force=True)
        k = kerhel(db, u)
        assert "forme_groupement" not in (k.ai_analysis or {}).get("details", {})
        assert not k.dce_file_key and k.go_decision == "go_groupement" and k.match_score == 43
        assert db.query(GroupementConvention).filter(GroupementConvention.project_id == k.id).count() == 0
        assert db.query(Preuve).filter(Preuve.owner_id == u.id).count() == 14
    finally:
        db.close()
    monkeypatch.undo()

    _remise_a_neuf()                       # et tout revient au redémarrage suivant
    d = {"h": demo["h"], "ctx": _ctx()}
    ecran_convention_generee_et_validee(client, d)
    ecran_formulaires_et_avant_de_deposer(client, d)


def test_lien_prive_le_groupement_de_bout_en_bout(client, monkeypatch, espions):  # noqa: F811
    """Comme en production depuis le 13/10/2026 : démo publique fermée, session ouverte par le lien privé.
    Le pitcheur montre le même parcours, sans aucun appel à l'IA."""
    _remise_a_neuf()
    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    cle = _cle_neuve()
    monkeypatch.setenv("DEMO_LIEN_CLE", cle)
    assert client.post("/api/auth/demo").status_code == 404
    r = client.post("/api/auth/demo", json={"cle": cle})
    assert r.status_code == 200, r.text
    d = {"h": _h(r.json()["access_token"]), "ctx": _ctx()}
    for ecran in ECRANS:
        ecran(client, d)
    assert espions["ia"] == [] and espions["email"] == [] and espions["fichier"] == []
