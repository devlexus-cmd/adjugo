"""
Rédaction, vague 3 — chantier I « Partir de vos anciens dossiers » (étude § 6.6, doctrine § 7).

 • Adjugo lit un document de « Mon savoir-faire » une fois et PROPOSE des fiches (références,
   qualifications, matériel, chiffres clés), chacune avec le passage EXACT du document ;
 • une proposition dont le passage n'est pas retrouvé tel quel est écartée ; une fiche qui en dit
   plus que son passage (reformulation, année ou rôle déduits, montant TTC présenté HT, date de fin
   non écrite) est corrigée ou écartée, SANS IA ; un passage qui rapporte une exigence d'un acheteur
   n'appuie jamais une fiche ; aucune fiche « Équipe » proposée par l'IA ;
 • rien n'est accepté sans l'utilisateur : tout est « proposé », il coche (routes du socle) ;
 • noms des salariés (profil, fiches « Équipe », noms repérés dans le document) masqués avant
   l'IA ; un CV n'est jamais envoyé ; une pièce du dossier d'un acheteur n'est pas lue ;
 • coût : une lecture par document, seuls les paragraphes porteurs d'un fait partent à l'IA,
   gratuit jusqu'au plafond du mois, budget de l'essai vérifié AVANT, espace facturé, lecture
   rendue si l'IA tombe ;
 • isolation par organisation (404), démo en lecture seule, jamais le mot « vérifié ».
Aucun appel réseau : le fournisseur d'IA est simulé.
"""
import json
import re
import time
import uuid
from datetime import date, datetime, timezone

import pytest

from app.services import fiches_import as fi
from app.services import llm
from app.services import preuves as pv
from tests.test_redaction_socle0 import fake_llm  # noqa: F401

DOC = ("Mémoire technique — Breizh Couverture\n"
       "Quimper, le 12 mars 2021\n"
       "\n"
       "Nos références\n"
       "En 2019, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), réalisée "
       "seule par notre équipe sous la conduite de Yann Tanguy.\n"
       "En 2020, couverture en ardoise de la salle des fêtes de Plouguerneau pour la commune de Plouguerneau, en "
       "groupement conjoint (120 000 € TTC).\n"
       "\n"
       "Nos qualifications\n"
       "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345), valable jusqu'au 31/12/2027.\n"
       "\n"
       "Nos moyens matériels\n"
       "Nous disposons en propre de 2 nacelles articulées de 16 m.\n"
       "Le CCTP impose une nacelle de 20 m pour ce type d'ouvrage.\n"
       "\n"
       "Notre équipe\n"
       "M. Kerjean, conducteur de travaux, suit chaque chantier. Chef d'équipe : Anne Le Floch.\n"
       "\n"
       "Nous attachons une grande importance au dialogue avec chacun.\n"
       "\n"
       "CV de nos encadrants\n"
       "Yann Tanguy, né le 12/03/1980, marié, 2 enfants, permis B. Expériences professionnelles : couvreur depuis "
       "2002.\n")
P_REF1 = ("En 2019, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), réalisée "
          "seule par notre équipe sous la conduite de {label}.")
P_REF2 = ("En 2020, couverture en ardoise de la salle des fêtes de Plouguerneau pour la commune de Plouguerneau, en "
          "groupement conjoint (120 000 € TTC).")
P_QUAL = "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345), valable jusqu'au 31/12/2027."
P_MAT = "Nous disposons en propre de 2 nacelles articulées de 16 m."
P_CCTP = "Le CCTP impose une nacelle de 20 m pour ce type d'ouvrage."
TEAM = [{"nom": "Yann Tanguy", "fonction": "Chef de chantier"}]


# ── Outils ──────────────────────────────────────────────────────────────────────────────────

def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(client, prefix="fi", verifie=True):
    from app.models import User
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Dirigeant", "company_name": "Breizh Couverture"})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = verifie
        db.commit()
        uid = u.id
    finally:
        db.close()
    return email, _h(r.json()["access_token"]), uid


def _company(client, h, team=TEAM):
    r = client.put("/api/company/", headers=h, json={"name": "Breizh Couverture", "team": team})
    assert r.status_code == 200, r.text


def _kb(client, h, text=DOC, name="Mémoire 2021.pdf"):
    r = client.post("/api/knowledge/text", headers=h, json={"name": name, "text": text, "kind": "memoire"})
    assert r.status_code == 200, r.text
    return r.json()["doc"]["id"]


def _attendre(client, h, doc_id):
    r = None
    for _ in range(300):
        r = client.get(f"/api/knowledge/{doc_id}/fiches", headers=h)
        assert r.status_code == 200, r.text
        lec = r.json().get("lecture") or {}
        if lec.get("statut") in ("lu", "echec"):
            return r.json()
        time.sleep(0.03)
    raise AssertionError(f"lecture jamais terminée : {r.json() if r is not None else None}")


def _contenu(kw) -> str:
    return "\n".join(llm._flatten_content(m.get("content")) for m in kw.get("messages") or [])


def _reponse_type(kw):
    """Le faux lecteur : il répond À PARTIR du texte reçu (donc masqué), comme le ferait l'IA."""
    recu = _contenu(kw)
    m = re.search(r"sous la conduite de (\[[^\]]+\])", recu)
    label = m.group(1) if m else "?"
    fiches = [
        # 1. juste : passage recopié (avec l'étiquette du chef de chantier), champs du passage
        {"nature": "reference", "champs": {"objet": "Réfection de la toiture de l'école Jules Ferry",
                                           "acheteur": "Mairie de Quimper", "annee": 2019, "montant_ht": 85000,
                                           "role": "seul"},
         "passage": P_REF1.format(label=label)},
        # 2. montant TTC présenté comme HT : le montant est retiré, le rôle écrit est gardé
        {"nature": "reference", "champs": {"objet": "Couverture en ardoise de la salle des fêtes de Plouguerneau",
                                           "acheteur": "commune de Plouguerneau", "annee": 2020,
                                           "montant_ht": 120000, "role": "groupement_conjoint"},
         "passage": P_REF2},
        # 3. qualification, date de fin écrite dans le passage
        {"nature": "qualification", "champs": {"nom": "Qualibat 3194", "numero": "12345"},
         "date_fin_validite": "2027-12-31", "passage": P_QUAL},
        # 4. matériel en propre
        {"nature": "materiel", "champs": {"designation": "nacelles articulées de 16 m", "quantite": 2,
                                          "possession": "propriete"}, "passage": P_MAT},
        # 5. exigence de l'acheteur recopiée dans le mémoire : jamais une preuve de l'entreprise
        {"nature": "materiel", "champs": {"designation": "nacelle de 20 m"}, "passage": P_CCTP},
        # 6. passage inventé : introuvable dans le document
        {"nature": "reference", "champs": {"objet": "Rénovation du gymnase de Brest", "acheteur": "Ville de Brest",
                                           "annee": 2022},
         "passage": "En 2022, rénovation du gymnase de Brest pour la Ville de Brest (300 000 € HT)."},
        # 7. une personne : jamais proposée par l'IA
        {"nature": "salarie", "champs": {"nom": label, "fonction": "Chef de chantier"},
         "passage": P_REF1.format(label=label)},
        # 8. reformulation de l'objet (« rénovation » au lieu de « réfection ») : écartée
        {"nature": "reference", "champs": {"objet": "Rénovation de la toiture de l'école Jules Ferry"},
         "passage": P_REF1.format(label=label)},
    ]
    return json.dumps({"fiches": fiches}, ensure_ascii=False), "end_turn"


def _lancer(client, h, doc_id, **body):
    return client.post(f"/api/knowledge/{doc_id}/fiches", headers=h, json=body)


# ═══ 1. Proposer, contrôler sans IA, cocher ═════════════════════════════════════════════════

def test_fiches_proposees_avec_leur_passage_exact_et_rien_d_accepte_sans_l_utilisateur(client, fake_llm):
    fake = fake_llm(_reponse_type)
    email, h, uid = _register(client)
    _company(client, h)
    doc_id = _kb(client, h)
    r = _lancer(client, h, doc_id, date_document="2021-03-12")
    assert r.status_code == 202, r.text
    assert r.json()["lecture"]["statut"] == "en_cours"
    etat = _attendre(client, h, doc_id)
    lec = etat["lecture"]
    assert lec["statut"] == "lu" and lec["proposees"] == 4 and lec["date_document"] == "2021-03-12"
    ecarts = {e["code"]: e["nombre"] for e in lec["ecarts"]}
    assert ecarts == {"exigence_acheteur": 1, "passage_introuvable": 1, "equipe": 1, "valeur_hors_passage": 1}
    assert lec["ecartees"] == 4
    fiches = etat["fiches"]
    assert len(fiches) == 4 and {f["statut"] for f in fiches} == {"proposee"}
    assert all(f["source_libelle"] == "trouvé dans vos documents" and f["type_source"] == "documents"
               and f["origine"] == "import_document" and not f["utilisable"] for f in fiches)
    par = {(f["nature"], (f["valeur"].get("objet") or f["valeur"].get("nom") or f["valeur"].get("designation"))): f
           for f in fiches}
    ref1 = par[("reference", "Réfection de la toiture de l'école Jules Ferry")]
    # Le passage enregistré est celui du DOCUMENT (nom remis en clair, sans IA).
    assert ref1["source"]["passage"] == P_REF1.format(label="Yann Tanguy")
    assert ref1["source"]["passage"] in DOC and ref1["source"]["doc_id"] == doc_id
    assert ref1["valeur"] == {"objet": "Réfection de la toiture de l'école Jules Ferry",
                              "acheteur": "Mairie de Quimper", "annee": 2019, "montant_ht": 85000, "role": "seul"}
    assert ref1["date_source"] == "2021-03-12" and ref1["a_reconfirmer"] is True        # plus de 3 ans
    ref2 = par[("reference", "Couverture en ardoise de la salle des fêtes de Plouguerneau")]
    assert "montant_ht" not in ref2["valeur"] and ref2["valeur"]["role"] == "groupement_conjoint"
    qual = par[("qualification", "Qualibat 3194")]
    assert qual["date_fin_validite"] == "2027-12-31" and qual["valeur"]["numero"] == "12345"
    mat = par[("materiel", "nacelles articulées de 16 m")]
    assert mat["valeur"] == {"designation": "nacelles articulées de 16 m", "quantite": 2, "possession": "propriete"}
    # Rien n'est accepté sans l'utilisateur.
    db = _db()
    try:
        assert pv.faits_autorises(db, uid) == []
    finally:
        db.close()
    # Il coche une fiche (route du socle) : elle devient une preuve « trouvé dans vos documents ».
    r = client.post(f"/api/preuves/{ref1['id']}/accepter", headers=h, json={"version": ref1["version"]})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        faits = pv.faits_autorises(db, uid)
        assert [f["id"] for f in faits] == [ref1["id"]]
        assert faits[0]["source_libelle"] == "trouvé dans vos documents" and faits[0]["appuie"] == "entreprise"
    finally:
        db.close()
    # … et la décoche : Adjugo ne s'en sert plus.
    v = r.json()["version"]
    assert client.post(f"/api/preuves/{ref1['id']}/retirer", headers=h, json={"version": v}).status_code == 200
    etat = client.get(f"/api/knowledge/{doc_id}/fiches", headers=h).json()
    assert {f["id"]: f["statut"] for f in etat["fiches"]}[ref1["id"]] == "retiree"
    # Résumé de la liste « Mon savoir-faire ».
    resume = client.get("/api/knowledge/fiches", headers=h).json()
    assert resume["documents"][str(doc_id)] == {"statut": "lu", "a_cocher": 3, "cochees": 0}
    assert resume["plafond"]["utilises"] == 1
    assert len(fake.calls) == 1


def test_le_passage_tolere_casse_accents_espaces_et_le_lien_vers_le_passage(client, fake_llm):
    def ans(kw):
        passage = "nous disposons en propre de 2 nacelles   articulees de 16 m."       # casse, accents, espaces
        return json.dumps({"fiches": [{"nature": "materiel", "champs": {"designation": "nacelles articulées",
                                                                        "quantite": 2}, "passage": passage}]}), \
            "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    (f,) = etat["fiches"]
    assert f["source"]["passage"] == P_MAT                       # tel qu'il est écrit dans le document
    p = client.get(f["source"]["lien_passage"], headers=h).json()
    assert p["passage"] == P_MAT and "Nos moyens matériels" in p["avant"] and p["doc_id"] == doc_id
    assert f["date_source"] is None and f["a_reconfirmer"] is False


# ═══ 2. Noms masqués, CV jamais envoyé, paragraphes sans fait jamais envoyés ══════════════════

def test_noms_masques_cv_jamais_envoye_et_paragraphes_sans_fait_non_envoyes(client, fake_llm):
    seen = []

    def ans(kw):
        seen.append(llm._CURRENT_TENANT.get())
        return _reponse_type(kw)
    fake = fake_llm(ans)
    _e, h, uid = _register(client)
    _company(client, h)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    _attendre(client, h, doc_id)
    envoye = fake.sent()
    for nom in ("Tanguy", "Yann", "Kerjean", "Le Floch", "Floch"):
        assert nom not in envoye, nom
    for cv in ("né le", "12/03/1980", "marié", "permis B", "Expériences professionnelles", "CV de nos encadrants"):
        assert cv not in envoye, cv
    assert "Nous attachons une grande importance au dialogue" not in envoye      # aucun fait : pas envoyé
    assert "Qualibat 3194" in envoye and "Mairie de Quimper" in envoye
    assert seen == [uid]                                                          # espace facturé posé


def test_fiche_equipe_saisie_masquee_avant_la_lecture(client, fake_llm):
    fake = fake_llm(lambda kw: ('{"fiches": []}', "end_turn"))
    _e, h, _uid = _register(client)
    r = client.post("/api/preuves", headers=h, json={"nature": "salarie", "valeur": {"nom": "Gwenaël Morvan",
                                                                                     "fonction": "Couvreur"}})
    assert r.status_code == 201, r.text
    doc_id = _kb(client, h, text="Nos références\nEn 2023, Gwenaël Morvan a dirigé la réfection de la mairie de "
                                 "Brest (45 000 € HT).\n")
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert etat["lecture"]["statut"] == "lu" and etat["lecture"]["proposees"] == 0
    assert "Morvan" not in fake.sent() and "Gwenaël" not in fake.sent()


def test_un_cv_n_est_jamais_lu(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    for name, text in (("CV_Yann_Tanguy.pdf", "Yann Tanguy\nCouvreur depuis 2002, Qualibat 3194, 2 nacelles.\n"),
                       ("Document.pdf", "Curriculum vitae\nYann Tanguy\nNé le 12/03/1980\nCouvreur depuis 2002.\n"
                                        "Expériences professionnelles : Qualibat 3194.")):
        doc_id = _kb(client, h, text=text, name=name)
        r = _lancer(client, h, doc_id)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "document_cv", r.text
        assert "jamais" in r.json()["detail"]["message"]
        etat = client.get(f"/api/knowledge/{doc_id}/fiches", headers=h).json()
        assert etat["document"]["statut"] == "cv" and etat["lecture"] is None
        assert client.get("/api/knowledge/fiches", headers=h).json()["documents"][str(doc_id)]["statut"] == "cv"
    assert fake.calls == []


def test_une_piece_du_dossier_d_un_acheteur_n_est_pas_lue(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    cctp = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES\nArticle 1 - Objet\nLe titulaire devra disposer d'une "
            "nacelle de 20 m et de la qualification Qualibat 3194.\n")
    doc_id = _kb(client, h, text=cctp, name="Document 2.pdf")
    r = _lancer(client, h, doc_id)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "document_piece_acheteur", r.text
    # Un ancien mémoire qui répond au CCTP, lui, est lu.
    memo = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES — notre réponse\nNous disposons en propre de 2 nacelles "
            "articulées de 16 m.\n")
    doc2 = _kb(client, h, text=memo, name="Document 3.pdf")
    assert _lancer(client, h, doc2).status_code == 202
    _attendre(client, h, doc2)
    assert len(fake.calls) == 1


def test_document_sans_aucun_fait_rien_a_lire_sans_appel(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h, text="Nous attachons une grande importance au dialogue et à la bonne humeur sur nos "
                                 "lieux de travail, toujours.\n")
    r = _lancer(client, h, doc_id)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "document_rien_a_lire"
    assert fake.calls == []


# ═══ 3. Coût : une lecture par document, plafond du mois, essai, panne ═══════════════════════

def test_une_seule_lecture_par_document_resultats_gardes(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    _attendre(client, h, doc_id)
    r = _lancer(client, h, doc_id)
    assert r.status_code == 200 and r.json()["lecture"]["statut"] == "lu" and len(r.json()["fiches"]) == 4
    assert len(fake.calls) == 1
    assert client.get("/api/knowledge/fiches", headers=h).json()["plafond"]["utilises"] == 1


def test_plafond_du_mois_reglable(client, fake_llm, monkeypatch):
    fake_llm(lambda kw: ('{"fiches": []}', "end_turn"))
    monkeypatch.setenv("FICHES_DOCUMENTS_PAR_MOIS", "1")
    _e, h, _uid = _register(client)
    a, b = _kb(client, h), _kb(client, h, name="Plaquette.pdf")
    assert _lancer(client, h, a).status_code == 202
    _attendre(client, h, a)
    r = _lancer(client, h, b)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "plafond_atteint", r.text
    assert "1er du mois" in r.json()["detail"]["message"]
    monkeypatch.setenv("FICHES_DOCUMENTS_PAR_MOIS", "0")
    r = _lancer(client, h, b)
    assert r.status_code == 429 and "pause" in r.json()["detail"]["message"]


def test_budget_de_l_essai_verifie_avant_toute_lecture(client, fake_llm):
    from tests.test_essai_garde_fou import _cout_essai
    fake = fake_llm(_reponse_type)
    email, h, uid = _register(client)
    doc_id = _kb(client, h)
    _cout_essai(uid, 15.0)                                        # budget de l'essai épuisé
    r = _lancer(client, h, doc_id)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_limite_usage", r.text
    assert fake.calls == []
    assert client.get("/api/knowledge/fiches", headers=h).json()["plafond"]["utilises"] == 0
    # L'estimation compte chaque partie du document, au plus (prudente).
    from app.services import budget_ia
    assert budget_ia.estimer("fiches", n=3) > budget_ia.estimer("fiches", n=1) > 0
    # Juste sous le budget, une lecture de 1 partie passe.
    _cout_essai(uid, 15.0 - 2 * budget_ia.estimer("fiches", n=1))
    assert _lancer(client, h, doc_id).status_code == 202
    _attendre(client, h, doc_id)


def test_essai_termine_aucune_lecture(client, fake_llm):
    from app.models import User
    fake = fake_llm(_reponse_type)
    email, h, uid = _register(client)
    doc_id = _kb(client, h)
    db = _db()
    try:
        u = db.get(User, uid)
        u.trial_ends_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
    finally:
        db.close()
    r = _lancer(client, h, doc_id)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "essai_termine", r.text
    assert fake.calls == []


def test_ia_en_panne_rien_propose_lecture_rendue_et_relancable(client, fake_llm):
    from app.models import User
    etat_ia = {"panne": True}

    def ans(kw):
        if etat_ia["panne"]:
            raise RuntimeError("fournisseur en panne")
        return _reponse_type(kw)
    fake_llm(ans)
    email, h, uid = _register(client)
    doc_id = _kb(client, h)
    db = _db()
    try:
        avant = db.get(User, uid).analyses_used_this_month or 0
    finally:
        db.close()
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert etat["lecture"]["statut"] == "echec" and "pas comptée" in etat["lecture"]["message"]
    assert etat["fiches"] == []
    assert client.get("/api/knowledge/fiches", headers=h).json()["plafond"]["utilises"] == 0      # rendue
    db = _db()
    try:
        assert (db.get(User, uid).analyses_used_this_month or 0) == avant       # aucune analyse débitée ni rendue
    finally:
        db.close()
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    etat_ia["panne"] = False
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert etat["lecture"]["statut"] == "lu" and len(etat["fiches"]) == 4


def test_reponse_illisible_echec_sans_rien_proposer(client, fake_llm):
    fake_llm(lambda kw: ("Voici les fiches : aucune idée", "end_turn"))
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert etat["lecture"]["statut"] == "echec" and etat["fiches"] == []


def test_reponse_coupee_la_partie_est_relue_en_deux(client, fake_llm, monkeypatch):
    monkeypatch.setattr(fi, "SEGMENT_MIN_COUPE", 50)
    appels = []

    def ans(kw):
        appels.append(_contenu(kw))
        if len(appels) == 1:
            return '{"fiches": [{"nature": "materiel", "champs": {"designation": "na', "max_tokens"
        return '{"fiches": []}', "end_turn"
    fake_llm(ans)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert etat["lecture"]["statut"] == "lu"
    assert len(appels) == 3 and len(appels[1]) < len(appels[0]) and len(appels[2]) < len(appels[0])


def test_redemarrage_lecture_interrompue_rendue_sans_toucher_aux_analyses(client):
    from app.main import _recover_orphan_jobs
    from app.models import Job, User
    _e, h, uid = _register(client)
    doc_id = _kb(client, h)
    db = _db()
    try:
        j = Job(user_id=uid, kind=fi.JOB_KIND, status="running", label="x", result={"doc_id": doc_id})
        db.add(j)
        u = db.get(User, uid)
        u.analyses_used_this_month, u.trial_analyses_used = 3, 3
        u.analyses_period = datetime.now(timezone.utc).strftime("%Y-%m")
        db.commit()
        jid = j.id
    finally:
        db.close()
    _recover_orphan_jobs()
    db = _db()
    try:
        assert db.get(Job, jid).status == "error"
        u = db.get(User, uid)
        assert u.analyses_used_this_month == 3 and u.trial_analyses_used == 3    # rien de rendu à tort
    finally:
        db.close()
    assert client.get("/api/knowledge/fiches", headers=h).json()["plafond"]["utilises"] == 0
    assert client.get(f"/api/knowledge/{doc_id}/fiches", headers=h).json()["lecture"]["statut"] == "echec"


# ═══ 4. Isolation, démo, adresse non confirmée ══════════════════════════════════════════════

def test_isolation_entre_organisations(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, ha, uid_a = _register(client)
    _e, hb, uid_b = _register(client)
    doc_id = _kb(client, ha)
    assert _lancer(client, hb, doc_id).status_code == 404
    assert client.get(f"/api/knowledge/{doc_id}/fiches", headers=hb).status_code == 404
    assert str(doc_id) not in client.get("/api/knowledge/fiches", headers=hb).json()["documents"]
    assert fake.calls == []
    assert _lancer(client, ha, doc_id).status_code == 202
    etat = _attendre(client, ha, doc_id)
    fid = etat["fiches"][0]["id"]
    assert client.get(f"/api/preuves/{fid}", headers=hb).status_code == 404
    assert client.post(f"/api/preuves/{fid}/accepter", headers=hb, json={}).status_code == 404
    assert client.get("/api/preuves", headers=hb).json()["preuves"] == []
    db = _db()
    try:
        assert pv.faits_autorises(db, uid_b) == []
    finally:
        db.close()


def test_la_demo_ne_lance_aucune_lecture(client, fake_llm):
    fake = fake_llm(_reponse_type)
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    hd = _h(r.json()["access_token"])
    r = client.post("/api/knowledge/1/fiches", headers=hd, json={})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    assert client.get("/api/knowledge/fiches", headers=hd).status_code == 200
    assert fake.calls == []


def test_adresse_non_confirmee(client, fake_llm):
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client, verifie=False)
    doc_id = _kb(client, h)
    r = _lancer(client, h, doc_id)
    assert r.status_code == 403 and "Confirmez votre adresse" in r.json()["detail"]
    assert fake.calls == []


def test_date_du_document_suggeree_et_controlee(client, fake_llm):
    fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    etat = client.get(f"/api/knowledge/{doc_id}/fiches", headers=h).json()
    assert etat["document"]["date_suggeree"] == "2021-03-12" and etat["document"]["statut"] == "a_lire"
    r = _lancer(client, h, doc_id, date_document="2999-01-01")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "date_invalide"
    r = _lancer(client, h, doc_id, date_document="pas une date")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "date_invalide"


# ═══ 5. Le contrôle des propositions, sans IA (unitaire) ══════════════════════════════════════

def test_controler_une_fiche_ne_dit_jamais_plus_que_son_passage():
    t = fi._Texte(DOC)
    # Année déduite (non écrite) : retirée ; le reste est gardé.
    val, ext, _fin, motif = fi.controler("reference", {"objet": "Réfection de la toiture de l'école Jules Ferry",
                                                       "annee": 2018}, P_REF1.format(label="Yann Tanguy"), t)
    assert motif is None and val == {"objet": "Réfection de la toiture de l'école Jules Ferry"}
    # Rôle non écrit : retiré.
    val, _e, _f, motif = fi.controler("reference", {"objet": "Réfection de la toiture de l'école Jules Ferry",
                                                    "role": "groupement_solidaire"},
                                      P_REF1.format(label="Yann Tanguy"), t)
    assert motif is None and "role" not in val
    # Date de fin non écrite : jamais gardée.
    _v, _e, fin, motif = fi.controler("qualification", {"nom": "Qualibat 3194"}, P_QUAL, t, "2030-01-01")
    assert motif is None and fin is None
    _v, _e, fin, _m = fi.controler("qualification", {"nom": "Qualibat 3194"}, P_QUAL, t, "2027-12-31")
    assert fin == date(2027, 12, 31)
    # Possession non écrite : retirée ; champ inconnu ou interdit : ignoré.
    val, _e, _f, motif = fi.controler("materiel", {"designation": "nacelles articulées", "possession": "location",
                                                   "photo": "x.jpg", "prix": 3},
                                      P_MAT, t)
    assert motif is None and val == {"designation": "nacelles articulées"}
    # Un nom propre absent du passage dans un champ obligatoire : écartée.
    assert fi.controler("qualification", {"nom": "Qualibat 1311"}, P_QUAL, t)[3] == "valeur_hors_passage"
    # Un passage trop court pour être un passage : introuvable.
    assert fi.controler("materiel", {"designation": "nacelle"}, "nacelles", t)[3] == "passage_introuvable"
    assert fi.controler("inconnue", {}, P_MAT, t)[3] == "incomplete"
    # Chiffre clé : « Effectif » admis pour « 12 salariés » ; jamais rangé sous une autre catégorie.
    t2 = fi._Texte("Plaquette 2024\nBreizh Couverture compte 12 salariés et a réalisé 85 chantiers en 2023.\n")
    p2 = "Breizh Couverture compte 12 salariés et a réalisé 85 chantiers en 2023."
    val, _e, _f, motif = fi.controler("chiffre_cle", {"libelle": "Effectif", "valeur": 12, "unite": "salariés"}, p2, t2)
    assert motif is None and val == {"libelle": "Effectif", "valeur": 12, "unite": "salariés"}
    assert fi.controler("chiffre_cle", {"libelle": "Chiffre d'affaires", "valeur": 85}, p2, t2)[3] == \
        "valeur_hors_passage"
    assert fi.controler("chiffre_cle", {"libelle": "Effectif", "valeur": 15}, p2, t2)[3] == "valeur_hors_passage"


def test_un_nombre_de_la_fiche_figure_dans_son_role_jamais_dans_un_autre():
    """Revue de la vague 3 : une dimension (« de 16 m »), un numéro (« n° 12345 ») ou un nombre qui compte
    autre chose (« 300 m2 ») ne deviennent jamais une quantité, un montant HT ou un effectif."""
    def _c(nature, champs, passage):
        return fi.controler(nature, champs, passage, fi._Texte(passage))
    p = "Nous disposons en propre de 2 nacelles articulées de 16 m."
    val, *_ = _c("materiel", {"designation": "nacelles articulées", "quantite": 16, "possession": "propriete"}, p)
    assert "quantite" not in val                                       # 16 m est une dimension
    val, *_ = _c("materiel", {"designation": "nacelles articulées", "quantite": 2}, p)
    assert val["quantite"] == 2
    assert _c("materiel", {"designation": "Nacelle articulée", "quantite": 2},
              "| Nacelle articulée | 2 | propriété |")[0]["quantite"] == 2
    assert _c("materiel", {"designation": "nacelles", "quantite": 2}, "Nous avons deux nacelles.")[0]["quantite"] == 2
    p = "Notre équipe de 6 couvreurs a posé 300 m2 de zinc en 2023."
    assert _c("chiffre_cle", {"libelle": "Effectif", "valeur": 300}, p)[3] == "valeur_hors_passage"
    assert _c("chiffre_cle", {"libelle": "Effectif", "valeur": 6}, p)[3] == "valeur_hors_passage"
    assert _c("chiffre_cle", {"libelle": "Couvreurs", "valeur": 6}, p)[0] == {"libelle": "Couvreurs", "valeur": 6}
    assert _c("chiffre_cle", {"libelle": "Surface de l'atelier", "valeur": 300, "unite": "m2"},
              "Notre atelier de 300 m2 est à Quimper.")[3] is None
    assert _c("chiffre_cle", {"libelle": "Effectif", "valeur": 12}, "Effectif : 12")[3] is None
    p = ("En 2024, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), "
         "certificat n° 12345.")
    val, *_ = _c("reference", {"objet": "Réfection de la toiture de l'école Jules Ferry", "montant_ht": 12345}, p)
    assert "montant_ht" not in val                                     # un numéro n'est pas un montant
    val, *_ = _c("reference", {"objet": "Réfection de la toiture de l'école Jules Ferry", "montant_ht": 85000,
                               "annee": 2024}, p)
    assert val["montant_ht"] == 85000 and val["annee"] == 2024
    val, *_ = _c("reference", {"objet": "Réfection de la toiture de l'école Jules Ferry", "annee": 12345}, p)
    assert "annee" not in val
    assert _c("reference", {"objet": "Réfection de la toiture du gymnase", "montant_ht": 1200000},
              "Réfection de la toiture du gymnase pour 1,2 million d'euros HT.")[0]["montant_ht"] == 1200000
    # La même règle pour une fiche saisie avec un passage de vos documents (socle).
    assert pv.elements_hors_passage("materiel", {"designation": "nacelles articulées", "quantite": 16},
                                    "Nous disposons en propre de 2 nacelles articulées de 16 m.") == ["16"]


def test_noms_probables_reperes_sans_ia():
    noms = fi.noms_probables("M. Kerjean dirige. Conducteur de travaux : Anne Le Floch. Paul Durand, chef de "
                             "chantier, 15 ans. La Mairie de Quimper, responsable du suivi. M. le Maire. Travaux "
                             "réalisés sous la conduite de Loïc Guéguen.")
    assert noms == ["Kerjean", "Paul Durand", "Anne Le Floch", "Loïc Guéguen"]


def test_nom_hors_profil_masque_quand_meme(client, fake_llm):
    """Sans équipe dans le profil, le nom écrit « sous la conduite de Yann Tanguy » ne part pas."""
    fake = fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    assert _lancer(client, h, doc_id).status_code == 202
    etat = _attendre(client, h, doc_id)
    assert "Tanguy" not in fake.sent() and etat["lecture"]["proposees"] == 4
    ref = [f for f in etat["fiches"] if f["valeur"].get("acheteur") == "Mairie de Quimper"][0]
    assert ref["source"]["passage"].endswith("sous la conduite de Yann Tanguy.")


def test_jamais_le_mot_verifie_dans_le_chantier_i(client, fake_llm):
    import ast
    import inspect
    import app.routers.fiches_import as rf
    messages = []
    for mod in (fi, rf):
        arbre = ast.parse(inspect.getsource(mod))
        docs = {id(n.body[0].value) for n in ast.walk(arbre)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        messages += [n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
    fake_llm(_reponse_type)
    _e, h, _uid = _register(client)
    doc_id = _kb(client, h)
    _lancer(client, h, doc_id)
    etat = _attendre(client, h, doc_id)
    for t in messages + [json.dumps(etat, ensure_ascii=False)]:
        assert "vérifi" not in t.lower() and "verifie" not in t.lower(), t[:200]


def test_ecran_mon_savoir_faire():
    """L'écran : le bouton, la liste des propositions avec leur passage, cocher / décocher, bulles (i),
    aucun émoji, jamais « vérifié »."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "app", "static", "app.html"), encoding="utf-8").read()
    js = open(os.path.join(root, "app", "static", "app.js"), encoding="utf-8").read()
    assert "Proposer des fiches à partir de ce document" in html
    from tests.zones import zone
    bloc = zone(html, "kb-fiches-proposees")
    assert 'class="tip' in bloc and 'type="checkbox"' in bloc
    assert "f.source.passage" in bloc and "f.source_libelle" in bloc                    # libellé du serveur
    assert "vérifi" not in bloc.lower()
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", bloc)
    for appel in ("/fiches", "/accepter", "/retirer"):
        assert appel in js
