"""Contrôle des bugs d'octobre 2026, groupe « marché » (page du marché, pièces à fournir, « Avant de déposer »,
formulaires officiels, export du dossier, devis et factures) : chaque test dit ce que le logiciel DOIT faire d'après
ses contrats et ses textes affichés ; tous échouaient sur cfe04e1, chacun sur son défaut.

1. Devis et factures : un devis qu'un collègue rattache à un marché se lit sur la page de ce marché et dans Mes
   marchés › Devis et factures pour toute l'organisation (avant : « Aucun devis ni facture lié »), et la numérotation
   suit l'entreprise (avant : deux collègues obtenaient chacun « DEV-2026-001 ») ; retiré de l'équipe, le collègue
   laisse ses devis à l'entreprise.
2. Export du dossier (ZIP) : deux pièces de même nom gardent deux entrées distinctes (avant : deux entrées du même
   chemin, l'une écrase l'autre à l'extraction).
3. Un intitulé de marché avec « / » (« Travaux de voirie 2026/2027 ») donne des noms de fichiers, jamais des chemins,
   dans le ZIP, son sommaire et le nom du formulaire téléchargé.
4. « Pièces à fournir » et « Avant de déposer » (entreprise seule) : une attestation URSSAF rangée dans « Fiscal et
   social » ne vaut pas l'attestation fiscale, un « Avis d'attribution » ne vaut pas le RIB (« rib » lu dans
   « attribution »), un « Cahier des charges » ne vaut pas une qualification (« rge » lu dans « charges »).
5. « Préparer mes documents » lancé par deux collègues : un seul jeu de formulaires dans le dossier du marché et dans
   le ZIP (avant : un DC1.pdf, un DC2.pdf… par collègue).
6. Modifier un devis (PUT /api/invoices/{id}) : mêmes refus qu'à la création pour une ligne négative, un statut
   inconnu refusé lisiblement (avant : total négatif enregistré, ou réponse 500).
"""
import io
import uuid
import zipfile
from datetime import date, timedelta
from types import SimpleNamespace

from tests.test_redaction_socle0 import ANALYSIS, _company, _set_analysis
from tests.test_reseau_partenaires import _db, _org, _project, mails, reg  # noqa: F401 (fixtures)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
ANNEE = date.today().year


def _collegue(client, chef):
    """Un collègue de la même organisation, invité depuis Réglages › Collègues, adresse confirmée."""
    email = f"cbm_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=chef["headers"], json={"email": email, "full_name": "Collègue"})
    assert r.status_code == 201, r.text
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        uid = u.id
    finally:
        db.close()
    r2 = client.post("/api/auth/login", json={"email": email, "password": r.json()["temp_password"]})
    assert r2.status_code == 200, r2.text
    return {"headers": {"Authorization": f"Bearer {r2.json()['access_token']}"}, "email": email, "id": uid}


def _devis(client, h, pid, qty=1):
    r = client.post("/api/invoices/", headers=h, json={
        "type": "devis", "client_name": "Ville de Quimper", "tva_rate": 0, "project_id": pid,
        "items": [{"description": "Étude", "qty": qty, "unit_price": 1000}]})
    assert r.status_code == 201, r.text
    return r.json()


def _piece(client, h, nom, categorie):
    data = {"name": nom, "category": categorie, "expiration_date": (date.today() + timedelta(days=200)).isoformat()}
    r = client.post("/api/documents/", headers=h, files={"file": ("f.pdf", io.BytesIO(PDF), "application/pdf")},
                    data=data)
    assert r.status_code == 201, r.text
    return r.json()


def _ref(prefixe, n):
    return f"{prefixe}-{ANNEE}-{n:03d}"


# ── 1. Devis et factures : le périmètre est l'organisation, le numéro suit l'entreprise ─────────────────────

def test_devis_d_un_collegue_vu_par_l_organisation_et_numerote_sans_doublon(client, reg, mails):
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    col = _collegue(client, chef)
    d1 = _devis(client, col["headers"], pid)
    assert d1["reference"] == _ref("DEV", 1)
    # Le propriétaire le voit : page du marché (« Devis et factures liés », filtrée sur le marché) et Mes marchés ›
    # Devis et factures lisent la même liste.
    vus = client.get("/api/invoices/", headers=chef["headers"]).json()
    assert [(i["reference"], i["project_id"]) for i in vus] == [(_ref("DEV", 1), pid)]
    # Son propre devis prend le numéro suivant de l'ENTREPRISE, jamais un second « DEV-…-001 ».
    d2 = _devis(client, chef["headers"], pid)
    assert d2["reference"] == _ref("DEV", 2)
    refs = sorted(i["reference"] for i in client.get("/api/invoices/", headers=col["headers"]).json())
    assert refs == [_ref("DEV", 1), _ref("DEV", 2)]
    # « Facturer » le devis d'un collègue : la facture suit la même numérotation d'entreprise.
    r = client.post(f"/api/invoices/{d1['id']}/convert", headers=chef["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["reference"] == _ref("FAC", 1) and r.json()["project_id"] == pid
    r = client.post(f"/api/invoices/{d2['id']}/convert", headers=col["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["reference"] == _ref("FAC", 2)
    assert client.put(f"/api/invoices/{d1['id']}", headers=chef["headers"], json={"notes": "vu"}).status_code == 200
    # Retiré de l'équipe, le collègue laisse ses devis et factures à l'entreprise (réassignés au propriétaire,
    # sans heurter l'unicité des numéros) ; lui ne les voit plus.
    r = client.delete(f"/api/org/members/{col['id']}", headers=chef["headers"])
    assert r.status_code == 200, r.text
    refs = sorted(i["reference"] for i in client.get("/api/invoices/", headers=chef["headers"]).json())
    assert refs == [_ref("DEV", 1), _ref("DEV", 2), _ref("FAC", 1), _ref("FAC", 2)], refs
    # Une autre organisation ne voit rien et ne peut rien modifier ; elle a sa propre numérotation.
    autre = _org(client, "Autre Entreprise")
    assert client.get("/api/invoices/", headers=autre["headers"]).json() == []
    assert client.put(f"/api/invoices/{d1['id']}", headers=autre["headers"], json={"notes": "x"}).status_code == 404
    assert client.post(f"/api/invoices/{d1['id']}/convert", headers=autre["headers"]).status_code == 404
    assert _devis(client, autre["headers"], None)["reference"] == _ref("DEV", 1)


# ── 2. Deux pièces de même nom dans Mes documents : deux entrées distinctes du ZIP ────────────────────────

def test_export_zip_deux_pieces_de_meme_nom(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h, json={"name": "Toiture école", "client": "Ville"}).json()["id"]
    _set_analysis(pid, ANALYSIS)
    a = _piece(client, h, "Attestation URSSAF.pdf", "fiscal")
    b = _piece(client, h, "Attestation URSSAF.pdf", "fiscal")
    c = _piece(client, h, "attestation urssaf.pdf", "fiscal")       # même nom à la casse près : même fichier extrait
    assert len({a["id"], b["id"], c["id"]}) == 3
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text[:300]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    noms = z.namelist()
    assert len({n.lower() for n in noms}) == len(noms), noms
    fiscal = sorted(n for n in noms if n.startswith("02_Documents/Fiscal/"))
    assert len(fiscal) == 3, fiscal
    assert "02_Documents/Fiscal/Attestation_URSSAF.pdf" in fiscal
    assert "02_Documents/Fiscal/Attestation_URSSAF_2.pdf" in fiscal
    assert all(z.read(n) == PDF for n in fiscal)


# ── 3. Un intitulé de marché avec « / » : des noms de fichiers, jamais des chemins ────────────────────────

def test_export_zip_et_formulaire_avec_une_barre_oblique_dans_l_intitule(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h,
                      json={"name": "Travaux de voirie 2026/2027", "client": "Ville"}).json()["id"]
    _set_analysis(pid, ANALYSIS)
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text[:300]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    formulaires = [n for n in z.namelist() if n.startswith("01_Formulaires_officiels/")]
    assert formulaires and all(n.count("/") == 1 for n in formulaires), formulaires
    assert ("01_Formulaires_officiels/DC1_Travaux_de_voirie_2026_2027_" + date.today().isoformat() + ".pdf"
            in formulaires), formulaires
    cd = r.headers["content-disposition"]
    assert "/" not in cd.split("filename*=UTF-8''", 1)[1] and "2026_2027" in cd, cd
    sommaire = z.read("00_SOMMAIRE.txt").decode()
    assert "Projet : Travaux de voirie 2026/2027" in sommaire                   # l'intitulé, lui, reste tel quel
    lignes = [l for l in sommaire.splitlines() if l.startswith("  - DC1_")]
    assert lignes == ["  - DC1_Travaux_de_voirie_2026_2027_" + date.today().isoformat() + ".pdf"], lignes
    r = client.post(f"/api/cerfa/{pid}/dc1", headers=h)
    assert r.status_code == 200, r.text[:300]
    cd = r.headers["content-disposition"]
    assert "/" not in cd.split("filename*=UTF-8''", 1)[1] and "%2F" not in cd, cd


def test_content_disposition_sans_separateur_de_chemin():
    from app.core.http import content_disposition
    cd = content_disposition("DC1_Voirie 2026/2027 — école.pdf")
    utf8 = cd.split("filename*=UTF-8''", 1)[1]
    assert "%2F" not in utf8 and "/" not in utf8 and "%5C" not in utf8, cd
    assert utf8 == "DC1_Voirie%202026_2027%20%E2%80%94%20%C3%A9cole.pdf", utf8     # accents et tiret gardés
    assert 'filename="DC1_Voirie 2026_2027  ecole.pdf"' in cd, cd                     # repli ASCII inchangé


# ── 4. « Pièces à fournir » : ni une catégorie partagée, ni un bout de mot ne reconnaissent une pièce ────────

def _doc(nom, categorie="autre"):
    return SimpleNamespace(id=abs(hash(nom)) % 10000, name=nom, category=categorie, expiration_date=None, folder=None)


def test_l_attestation_urssaf_ne_vaut_pas_l_attestation_fiscale_meme_dans_la_categorie_fiscal_et_social():
    from app.routers.checklist import match_document
    FISCALE, SOCIALE = "Attestation de régularité fiscale", "Attestation de régularité sociale (URSSAF)"
    for nom in ("Attestation de vigilance URSSAF.pdf", "Attestation de vigilance.pdf", "Cotisations 2026.pdf"):
        assert match_document(FISCALE, [_doc(nom, "fiscal")])["found"] is False, nom
    assert match_document(SOCIALE, [_doc("Attestation de vigilance URSSAF.pdf", "fiscal")])["found"] is True
    # L'attestation fiscale reste reconnue par son nom ou, à défaut d'indice, par la catégorie : la règle des
    # attestations du chef de file (invites.vault_doc_type).
    for nom in ("Attestation de régularité fiscale.pdf", "DGFiP 2026.pdf", "attestation 2026.pdf"):
        assert match_document(FISCALE, [_doc(nom, "fiscal")])["found"] is True, nom
    assert match_document(SOCIALE, [_doc("attestation 2026.pdf", "fiscal")])["found"] is False


def test_un_mot_cle_court_n_est_jamais_reconnu_dans_un_autre_mot():
    from app.routers.checklist import match_document
    RIB, QUALIF = "Relevé d'identité bancaire (RIB)", "Certificat Qualibat / qualification"
    for piece, nom in ((RIB, "Avis d'attribution 2025.pdf"), (RIB, "Contribution formation.pdf"),
                       (RIB, "ATTRIBUTION.pdf"), (QUALIF, "Cahier des charges.pdf"), (QUALIF, "Décharge.pdf")):
        assert match_document(piece, [_doc(nom)])["found"] is False, (piece, nom)
    # Une pièce demandée par le dossier dont le nom porte un de ces bouts de mot n'appelle pas la famille du RIB.
    assert match_document("Avis d'attribution du lot précédent", [_doc("RIB.pdf")])["found"] is False
    for piece, nom in ((RIB, "RIB.pdf"), (RIB, "RIB_2026.pdf"), (RIB, "rib-banque.pdf"), (RIB, "Mon RIB.pdf"),
                       (RIB, "MonRIB.pdf"), (RIB, "RibEntreprise.pdf"), (RIB, "RIB2026.pdf"),
                       (QUALIF, "Attestation RGE.pdf"), (QUALIF, "qualif-rge 2026.pdf"), (QUALIF, "Qualibat 3212.pdf"),
                       ("Extrait Kbis ou équivalent", "ExtraitKbis.pdf"), ("DC1 - Lettre de candidature", "DC1.pdf")):
        assert match_document(piece, [_doc(nom)])["found"] is True, (piece, nom)


def test_la_carte_des_pieces_et_avant_de_deposer_disent_l_attestation_fiscale_et_le_rib_manquants(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h, json={"name": "Travaux de voirie", "client": "Ville"}).json()["id"]
    _set_analysis(pid, ANALYSIS)
    _piece(client, h, "Attestation de vigilance URSSAF.pdf", "fiscal")
    _piece(client, h, "Avis d'attribution 2025.pdf", "administratif")
    carte = {i["id"]: i for i in client.get(f"/api/checklist/{pid}", headers=h).json()["checklist"]}
    assert carte["attestation_sociale"]["status"] == "ok"
    assert carte["attestation_fiscale"]["status"] == "manquant", carte["attestation_fiscale"]
    assert carte["rib"]["status"] == "manquant", carte["rib"]
    pret = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert pret["pour"] == "seul" and pret["checks"]["pieces"] is False
    manques = pret["manques_par_controle"]["pieces"]
    assert "Attestation de régularité fiscale : à ajouter dans Mes documents" in manques, manques
    assert "Relevé d'identité bancaire (RIB) : à ajouter dans Mes documents" in manques, manques
    # Rangée sous son nom, l'attestation fiscale est reconnue et quitte les manques.
    _piece(client, h, "Attestation de régularité fiscale.pdf", "fiscal")
    carte = {i["id"]: i for i in client.get(f"/api/checklist/{pid}", headers=h).json()["checklist"]}
    assert carte["attestation_fiscale"]["status"] == "ok"
    assert carte["attestation_fiscale"]["document_name"] == "Attestation de régularité fiscale.pdf"
    manques = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]["manques_par_controle"]["pieces"]
    assert not any("fiscale" in m for m in manques), manques


# ── 5. « Préparer mes documents » par deux collègues : un seul jeu de formulaires ───────────────────────────

def test_preparer_mes_documents_par_deux_collegues_ne_double_pas_les_formulaires(client, reg, mails):
    chef = _org(client, "Breizh Couverture", extra={"representant_legal": "Eliot Viegas", "address": "1 rue du Port"})
    pid = _project(client, chef)
    _set_analysis(pid, ANALYSIS)
    col = _collegue(client, chef)
    for qui in (chef, col, chef):
        r = client.post("/api/sourcing/documents", headers=qui["headers"], json={"project_id": pid, "cotraitants": []})
        assert r.status_code == 200, r.text[:300]
    for qui in (chef, col):
        docs = client.get(f"/api/projects/{pid}/documents", headers=qui["headers"]).json()
        cerfa = next(f for f in docs["folders"] if f["folder"] == "CERFA")
        noms = [d["name"] for d in cerfa["documents"]]
        assert noms and len(noms) == len(set(noms)), noms
        assert {"DC1.pdf", "DC2.pdf", "ATTRI1.pdf"} <= set(noms), noms
    # Le jeu gardé est le dernier : celui que le propriétaire vient de ranger.
    from app.models import Document
    db = _db()
    try:
        auteurs = {d.user_id for d in db.query(Document).filter(Document.project_id == pid,
                                                                  Document.folder == "CERFA").all()}
    finally:
        db.close()
    assert auteurs == {chef["id"]}, auteurs
    # Le ZIP exporté ne porte qu'un exemplaire de chaque formulaire rangé.
    r = client.post(f"/api/export/{pid}", headers=col["headers"])
    assert r.status_code == 200, r.text[:300]
    entrees = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(entrees) == len(set(entrees)), entrees
    assert sum(1 for n in entrees if n.endswith("/DC1.pdf")) == 1, entrees
    # Une autre organisation qui range ses formulaires sur SON marché ne touche jamais à ceux-ci.
    autre = _org(client, "Autre Entreprise", extra={"representant_legal": "A", "address": "2 rue"})
    pid2 = _project(client, autre)
    _set_analysis(pid2, ANALYSIS)
    assert client.post("/api/sourcing/documents", headers=autre["headers"],
                       json={"project_id": pid2, "cotraitants": []}).status_code == 200
    docs = client.get(f"/api/projects/{pid}/documents", headers=chef["headers"]).json()
    assert "DC1.pdf" in [d["name"] for f in docs["folders"] if f["folder"] == "CERFA" for d in f["documents"]]


# ── 6. Modifier un devis : mêmes refus qu'à la création, jamais un 500 ─────────────────────────────────────

def test_modifier_un_devis_refuse_une_ligne_negative_et_un_statut_inconnu(client, auth):
    h = auth["headers"]
    d = _devis(client, h, None)
    r = client.put(f"/api/invoices/{d['id']}", headers=h,
                   json={"items": [{"description": "a", "qty": -3, "unit_price": 10}]})
    assert r.status_code == 422, r.text
    assert "Quantité et prix unitaire doivent être positifs" in r.text
    r = client.put(f"/api/invoices/{d['id']}", headers=h, json={"status": "foo"})
    assert r.status_code == 422, r.text
    assert "Statut inconnu" in r.text
    for vide in ({"status": None}, {"items": None}, {"tva_rate": None}):
        r = client.put(f"/api/invoices/{d['id']}", headers=h, json=vide)
        assert r.status_code == 422, (vide, r.status_code, r.text[:200])
    liste = client.get("/api/invoices/", headers=h)
    assert liste.status_code == 200 and liste.json()[0]["total_ttc"] == 1000.0     # rien n'a été enregistré
    r = client.put(f"/api/invoices/{d['id']}", headers=h,
                   json={"status": "accepte", "items": [{"description": "a", "qty": 2, "unit_price": 10}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepte" and r.json()["total_ttc"] == 20.0
    assert client.get("/api/invoices/", headers=h).json()[0]["total_ttc"] == 20.0
