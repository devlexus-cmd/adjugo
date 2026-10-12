"""
Rédaction, vague 3 — SOCLE « Mes preuves » (étude § 6.5 A, § 6.6 I, § 6.7 E1, § 7 doctrine).

 • modèle : nature, valeur structurée (liste fermée de champs, CV minimal), source TYPÉE (dans vos
   documents | déclaré par vous | source publique | votre estimation), lien vers la source, date de
   validité, propriétaire (organisation ; membre du groupement prévu, jamais exposé), statut ;
 • « trouvé dans vos documents » : passage EXACT retrouvé dans le document, et qui couvre la fiche
   (chaque chiffre, nom, année…) ; sinon refus. Jamais le mot « vérifié » ;
 • numéros STABLES (« F3 ») jamais réutilisés, même après suppression ;
 • faits_autorises() : acceptés, de l'organisation, valables, source encore présente ;
 • API isolée par organisation (404 pour un autre compte), démo en lecture seule ;
 • RGPD : export, effacement avec le compte, transfert de propriété ; noms des fiches « Équipe »
   masqués avant l'IA, CV jamais dans le texte remis à l'IA ;
 • migration (SQLite : à neuf, création par la révision, rejeu, retour arrière).
Aucun appel réseau, aucune IA.
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta

import pytest

from app.services import preuves as pv

PASSAGE_DOC = ("Références récentes\n"
               "En 2024, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), "
               "réalisée seule par notre équipe de 6 couvreurs.\n"
               "Yann Tanguy, conducteur de travaux, 15 ans d'expérience, encadre nos chantiers.\n"
               "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345).\n")
PASSAGE_REF = ("En 2024, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), "
               "réalisée seule")
REF_VAL = {"objet": "Réfection de la toiture de l'école Jules Ferry", "acheteur": "Mairie de Quimper",
           "annee": 2024, "montant_ht": 85000, "role": "seul"}


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(client, prefix="pv"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Dirigeant", "company_name": "Breizh Couverture"})
    assert r.status_code == 201, r.text
    return email, _h(r.json()["access_token"])


def _uid(email):
    from app.models import User
    db = _db()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


def _kb(client, h, text=PASSAGE_DOC, name="Mémoire 2024"):
    r = client.post("/api/knowledge/text", headers=h, json={"name": name, "text": text, "kind": "memoire"})
    assert r.status_code == 200, r.text
    return r.json()["doc"]["id"]


def _creer(client, h, **body):
    body.setdefault("type_source", "declare")
    return client.post("/api/preuves", headers=h, json=body)


def _ok(r, code=201):
    assert r.status_code == code, r.text
    return r.json()


def _code(r, status):
    assert r.status_code == status, r.text
    return r.json()["detail"]["code"]


# ═══ 1. Créer, lire, lister ═════════════════════════════════════════════════════════════════

def test_creer_une_reference_declaree_et_la_lister(client, auth):
    h = auth["headers"]
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL))
    assert p["ref"] == f"F{p['numero']}" and p["nature_libelle"] == "Référence"
    assert p["type_source"] == "declare" and p["source_libelle"] == "déclaré par vous"
    assert p["statut"] == "acceptee" and p["utilisable"] is True and p["raison"] is None
    assert p["texte"] == ("Référence : Réfection de la toiture de l'école Jules Ferry ; acheteur : Mairie de "
                          "Quimper ; année 2024 ; montant 85 000 € HT ; réalisé seul")
    assert "proprietaire" not in json.dumps(p) and "invite" not in json.dumps(p)      # vague 4 : jamais exposé
    r = client.get("/api/preuves", headers=h)
    data = _ok(r, 200)
    assert [x["id"] for x in data["preuves"]] == [p["id"]]
    assert data["compteurs"]["reference"] == {"proposee": 0, "acceptee": 1, "retiree": 0}
    assert {n["code"] for n in data["natures"]} == set(pv.NATURES)
    ts = {t["code"]: t for t in data["types_source"]}
    assert ts["public"]["natures"] == ["reference", "qualification"] and ts["estimation"]["natures"] == ["chiffre_cle"]
    assert _ok(client.get(f"/api/preuves/{p['id']}", headers=h), 200)["id"] == p["id"]
    assert _ok(client.get("/api/preuves?nature=salarie", headers=h), 200)["preuves"] == []
    assert _code(client.get("/api/preuves?nature=inconnue", headers=h), 422) == "nature_invalide"


def test_les_cinq_natures_et_leurs_champs(client, auth):
    h = auth["headers"]
    _ok(_creer(client, h, nature="qualification", valeur={"nom": "Qualibat 3194", "organisme": "Qualibat",
                                                          "numero": "12345"},
               date_fin_validite=(pv.aujourd_hui() + timedelta(days=300)).isoformat()))
    s = _ok(_creer(client, h, nature="salarie", valeur={"nom": "Yann Tanguy", "fonction": "Conducteur de travaux",
                                                        "experience_annees": 15, "diplomes": "BTS Bâtiment"}))
    assert s["nature_libelle"] == "Équipe"
    m = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Nacelle articulée 16 m", "quantite": 2,
                                                         "possession": "propriete"}))
    assert m["texte"] == "Matériel : Nacelle articulée 16 m ; quantité : 2 ; en propre"
    c = _ok(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Effectif", "valeur": "12", "unite": "salariés",
                                                            "annee": 2025}))
    assert c["valeur"]["valeur"] == 12 and c["texte"] == "Chiffre clé : Effectif : 12 salariés (2025)"
    c2 = _ok(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Chiffre d'affaires", "valeur": 1250000.5,
                                                             "unite": "€"}))
    assert "1 250 000,5 €" in c2["texte"]


@pytest.mark.parametrize("valeur,code", [
    ({"objet": "x", "inconnu": 1}, "champ_inconnu"),
    ({"acheteur": "Mairie"}, "champ_requis"),
    ({"objet": "x", "annee": 1800}, "champ_invalide"),
    ({"objet": "x", "annee": "deux mille"}, "champ_invalide"),
    ({"objet": "x", "montant_ht": True}, "champ_invalide"),
    ({"objet": "x", "role": "chef"}, "champ_invalide"),
    ("pas un objet", None),
])
def test_valeur_refusee_si_hors_de_la_liste_fermee(client, auth, valeur, code):
    r = _creer(client, auth["headers"], nature="reference", valeur=valeur)
    if code is None:
        assert r.status_code == 422
    else:
        assert _code(r, 422) == code


@pytest.mark.parametrize("champ", ["photo", "adresse", "date_naissance", "telephone", "email"])
def test_cv_minimal_sans_photo_ni_adresse_ni_date_de_naissance(client, auth, champ):
    r = _creer(client, auth["headers"], nature="salarie",
               valeur={"nom": "Yann Tanguy", "fonction": "Couvreur", champ: "x"})
    assert _code(r, 422) == "champ_interdit"
    assert r.json()["detail"]["message"] == "Le CV ne contient ni photo, ni adresse, ni date de naissance."


def test_nature_et_statut_et_source_inconnus(client, auth):
    h = auth["headers"]
    assert _code(_creer(client, h, nature="avis_client", valeur={"x": 1}), 422) == "nature_invalide"
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, statut="retiree"), 422) == "statut_invalide"
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="ia"), 422) == \
        "type_source_invalide"
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="acheteur"), 422) == \
        "type_source_invalide"                                         # le dossier de l'acheteur n'est jamais une source


# ═══ 2. « Trouvé dans vos documents » : le passage exact, qui couvre la fiche ═══════════════════

def test_passage_retrouve_tel_quel_et_lien_vers_le_passage(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                   source={"doc_id": doc_id, "passage": "« " + PASSAGE_REF.upper() + " »"}))
    assert p["source_libelle"] == "trouvé dans vos documents"
    src = p["source"]
    assert src["doc_id"] == doc_id and src["doc_nom"] == "Mémoire 2024"
    assert src["lien_passage"] == f"/api/preuves/{p['id']}/passage" and src["chunk_id"]
    assert src["passage"] == PASSAGE_REF                   # tel qu'il est écrit dans le document
    ps = _ok(client.get(src["lien_passage"], headers=h), 200)
    assert ps["passage"] == PASSAGE_REF and ps["debut"] == PASSAGE_DOC.index("En 2024")
    assert ps["avant"] == "Références récentes\n" and ps["apres"].startswith(" par notre équipe de 6 couvreurs.")


def test_passage_introuvable_refuse(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    r = _creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
               source={"doc_id": doc_id, "passage": "En 2024, réfection complète de la toiture de la mairie"})
    assert _code(r, 422) == "passage_introuvable"
    assert "déclaré par vous" in r.json()["detail"]["message"]
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                        source={"doc_id": doc_id, "passage": "En 2024"}), 422) == "passage_introuvable"   # trop court
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents", source={}), 422) == \
        "source_requise"
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                        source={"doc_id": doc_id, "passage": "x" * 1300}), 422) == "passage_trop_long"


@pytest.mark.parametrize("modif,attendu", [
    ({"acheteur": "Mairie de Brest"}, "Mairie de Brest"),
    ({"annee": 2023}, "2023"),
    ({"montant_ht": 120000}, "120 000"),
    ({"objet": "Réfection de la toiture de l'école Jules Ferry et du gymnase Jean Moulin"}, "Jean Moulin"),
    ({"lieu": "Concarneau"}, "Concarneau"),
    ({"description": "Chantier certifié ISO 14001"}, "ISO 14001"),
])
def test_un_element_de_la_fiche_absent_du_passage_est_refuse(client, auth, modif, attendu):
    """Le libellé « trouvé dans vos documents » n'est donné que si la fiche ne dit RIEN de plus
    que le passage : un chiffre, une année, un nom changés ou ajoutés sont refusés."""
    h = auth["headers"]
    doc_id = _kb(client, h)
    r = _creer(client, h, nature="reference", valeur=dict(REF_VAL, **modif), type_source="documents",
               source={"doc_id": doc_id, "passage": PASSAGE_REF})
    assert _code(r, 422) == "valeur_hors_passage"
    assert attendu in r.json()["detail"]["elements"]


def test_document_d_un_autre_compte_refuse(client, auth):
    _e2, h2 = _register(client)
    doc_autre = _kb(client, h2)
    r = _creer(client, auth["headers"], nature="reference", valeur=REF_VAL, type_source="documents",
               source={"doc_id": doc_autre, "passage": PASSAGE_REF})
    assert _code(r, 422) == "document_introuvable"


def test_document_retire_la_preuve_perd_sa_source(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                   source={"doc_id": doc_id, "passage": PASSAGE_REF}))
    owner = _uid(auth["email"])
    db = _db()
    try:
        assert [f["id"] for f in pv.faits_autorises(db, owner)] == [p["id"]]
    finally:
        db.close()
    r = client.delete(f"/api/knowledge/{doc_id}", headers=h)
    assert r.status_code == 200 and r.json()["preuves_sans_source"] == 1
    q = _ok(client.get(f"/api/preuves/{p['id']}", headers=h), 200)
    assert q["utilisable"] is False and q["raison"] == "source_introuvable"
    assert "Mon savoir-faire" in q["raison_message"]
    db = _db()
    try:
        assert pv.faits_autorises(db, owner) == []
        assert [(x["id"], x["raison"]) for x in pv.faits_ecartes(db, owner)] == [(p["id"], "source_introuvable")]
    finally:
        db.close()
    assert _code(client.get(f"/api/preuves/{p['id']}/passage", headers=h), 404) == "source_introuvable"
    _ok(client.post(f"/api/preuves/{p['id']}/retirer", headers=h), 200)
    assert _code(client.post(f"/api/preuves/{p['id']}/accepter", headers=h), 409) == "source_introuvable"
    # Elle redevient utilisable en la déclarant soi-même.
    q = _ok(client.patch(f"/api/preuves/{p['id']}", headers=h, json={"type_source": "declare"}), 200)
    assert q["source_libelle"] == "déclaré par vous" and q["source"] == {}
    q = _ok(client.post(f"/api/preuves/{p['id']}/accepter", headers=h), 200)
    assert q["utilisable"] is True


def _justificatif(email, name="Certificat Qualibat.pdf"):
    from app.models import Document
    db = _db()
    try:
        d = Document(user_id=_uid(email), name=name, file_key=f"x/{uuid.uuid4().hex}.pdf", file_size=10)
        db.add(d)
        db.commit()
        return d.id
    finally:
        db.close()


def test_justificatif_depose(client, auth):
    h = auth["headers"]
    jid = _justificatif(auth["email"])
    p = _ok(_creer(client, h, nature="qualification", valeur={"nom": "Qualibat 3194"}, type_source="documents",
                   source={"document_id": jid}))
    assert p["source_libelle"] == "justificatif déposé"
    assert p["source"]["lien_justificatif"] == f"/api/documents/{jid}/download"
    assert p["source"]["document_nom"] == "Certificat Qualibat.pdf" and p["utilisable"]
    assert client.delete(f"/api/documents/{jid}", headers=h).status_code == 204      # corbeille
    q = _ok(client.get(f"/api/preuves/{p['id']}", headers=h), 200)
    assert q["utilisable"] is False and q["raison"] == "justificatif_introuvable"
    _e2, h2 = _register(client)
    assert _code(_creer(client, h2, nature="qualification", valeur={"nom": "Qualibat 3194"},
                        type_source="documents", source={"document_id": jid}), 422) == "justificatif_introuvable"


def test_document_d_origine_de_plus_de_trois_ans_a_reconfirmer(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    vieux = (pv.aujourd_hui() - timedelta(days=4 * 365)).isoformat()
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                   source={"doc_id": doc_id, "passage": PASSAGE_REF}, date_source=vieux))
    assert p["a_reconfirmer"] is True and p["date_source"] == vieux
    p2 = _ok(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Couvreurs", "valeur": 6},
                    type_source="documents", source={"doc_id": doc_id, "passage": "notre équipe de 6 couvreurs"},
                    date_source=(pv.aujourd_hui() - timedelta(days=200)).isoformat()))
    assert p2["a_reconfirmer"] is False
    futur = (pv.aujourd_hui() + timedelta(days=30)).isoformat()
    assert _code(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Couvreurs", "valeur": 6},
                        type_source="documents", source={"doc_id": doc_id, "passage": "notre équipe de 6 couvreurs"},
                        date_source=futur), 422) == "champ_invalide"


# ═══ 3. Sources publiques et estimations ════════════════════════════════════════════════════

def test_source_publique_datee(client, auth):
    h = auth["headers"]
    jour = (pv.aujourd_hui() - timedelta(days=2)).isoformat()
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="public",
                   source={"nom": "DECP", "url": "https://data.economie.gouv.fr/explore/dataset/decp",
                           "consulte_le": jour, "identifiant": "21290232900015_2024_0012"}))
    assert p["source_libelle"] == "marché attribué, source publique DECP"
    assert p["source"] == {"nom": "DECP", "url": "https://data.economie.gouv.fr/explore/dataset/decp",
                           "consulte_le": jour, "identifiant": "21290232900015_2024_0012"}
    assert p["date_source"] == jour and p["a_reconfirmer"] is False
    q = _ok(_creer(client, h, nature="qualification", valeur={"nom": "RGE Qualibat"}, type_source="public",
                   source={"nom": "Liste RGE", "url": "https://france-renov.gouv.fr/annuaire-rge", "consulte_le": jour}))
    assert q["source_libelle"] == "source publique : Liste RGE"
    base = {"nom": "DECP", "url": "https://data.gouv.fr/x", "consulte_le": jour}
    for src, code in [(dict(base, url="http://data.gouv.fr/x"), "url_invalide"),
                      (dict(base, url="javascript:alert(1)"), "url_invalide"),
                      ({k: v for k, v in base.items() if k != "nom"}, "source_requise"),
                      ({k: v for k, v in base.items() if k != "consulte_le"}, "date_requise"),
                      (dict(base, consulte_le=(pv.aujourd_hui() + timedelta(days=10)).isoformat()), "champ_invalide")]:
        assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="public", source=src),
                     422) == code
    for nature, valeur in (("salarie", {"nom": "Yann Tanguy", "fonction": "Couvreur"}),
                           ("materiel", {"designation": "Nacelle"})):
        assert _code(_creer(client, h, nature=nature, valeur=valeur, type_source="public", source=base), 422) == \
            "source_non_permise"


def test_estimation_rattachee_a_un_marche(client, auth):
    h = auth["headers"]
    pid = _ok(client.post("/api/projects/", headers=h, json={"name": "Toiture école", "client": "Commune"}))["id"]
    p = _ok(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Délai d'exécution", "valeur": 6,
                                                            "unite": "semaines"},
                   type_source="estimation", source={"project_id": pid, "detail": "chiffrage du marché"}))
    assert p["source_libelle"] == "votre estimation" and p["source"]["project_id"] == pid
    g = _ok(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "Compagnons prévus", "valeur": 4},
                   type_source="estimation"))
    assert _code(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="estimation"), 422) == \
        "source_non_permise"
    _e2, h2 = _register(client)
    pid2 = _ok(client.post("/api/projects/", headers=h2, json={"name": "Autre", "client": "Commune"}))["id"]
    assert _code(_creer(client, h, nature="chiffre_cle", valeur={"libelle": "x", "valeur": 1},
                        type_source="estimation", source={"project_id": pid2}), 422) == "marche_introuvable"
    owner = _uid(auth["email"])
    db = _db()
    try:
        assert {f["id"] for f in pv.faits_autorises(db, owner)} == {g["id"]}              # hors de son marché
        assert {f["id"] for f in pv.faits_autorises(db, owner, project_id=pid)} == {g["id"], p["id"]}
        f = next(x for x in pv.faits_autorises(db, owner, project_id=pid) if x["id"] == p["id"])
        assert f["appuie"] == "estimations"
    finally:
        db.close()


# ═══ 4. Statuts, versions, suppression, numéros stables ═════════════════════════════════════

def test_proposee_puis_acceptee_puis_retiree(client, auth):
    h = auth["headers"]
    owner = _uid(auth["email"])
    doc_id = _kb(client, h)
    db = _db()
    try:
        p, cree = pv.proposer(db, owner, nature="reference", valeur=REF_VAL, type_source="documents",
                              source={"doc_id": doc_id, "passage": PASSAGE_REF})
        assert cree and p.statut == "proposee" and p.origine == "import_document"
        again, cree2 = pv.proposer(db, owner, nature="reference", valeur=dict(REF_VAL, objet=REF_VAL["objet"].upper()),
                                   type_source="documents", source={"doc_id": doc_id, "passage": PASSAGE_REF})
        assert not cree2 and again.id == p.id                                   # pas deux fois la même fiche
        with pytest.raises(pv.PreuveError) as e:                                # sans passage retrouvé : rejetée
            pv.proposer(db, owner, nature="reference", valeur=dict(REF_VAL, annee=2021), type_source="documents",
                        source={"doc_id": doc_id, "passage": PASSAGE_REF})
        assert e.value.code == "valeur_hors_passage"
        db.rollback()
        assert pv.faits_autorises(db, owner) == []
        pid = p.id
    finally:
        db.close()
    q = _ok(client.get(f"/api/preuves/{pid}", headers=h), 200)
    assert q["utilisable"] is False and q["raison"] == "proposee" and q["statut_libelle"] == "Proposée"
    q = _ok(client.post(f"/api/preuves/{pid}/accepter", headers=h), 200)
    assert q["statut"] == "acceptee" and q["utilisable"] and q["accepte_le"]
    db = _db()
    try:
        assert [f["id"] for f in pv.faits_autorises(db, owner)] == [pid]
    finally:
        db.close()
    q = _ok(client.post(f"/api/preuves/{pid}/retirer", headers=h), 200)
    assert q["statut"] == "retiree" and q["raison"] == "retiree"
    db = _db()
    try:
        assert pv.faits_autorises(db, owner) == [] and pv.faits_ecartes(db, owner) == []
    finally:
        db.close()
    assert _ok(client.get("/api/preuves?statut=retiree", headers=h), 200)["preuves"][0]["id"] == pid


def test_verrou_de_version_et_modification_partielle(client, auth):
    h = auth["headers"]
    fin = (pv.aujourd_hui() + timedelta(days=100)).isoformat()
    p = _ok(_creer(client, h, nature="qualification", valeur={"nom": "Qualibat 3194"}, date_fin_validite=fin))
    q = _ok(client.patch(f"/api/preuves/{p['id']}", headers=h,
                         json={"valeur": {"nom": "Qualibat 3194", "numero": "12345"}, "version": p["version"]}), 200)
    assert q["version"] == p["version"] + 1 and q["date_fin_validite"] == fin and q["valeur"]["numero"] == "12345"
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={"valeur": {"nom": "Autre"}, "version": p["version"]})
    assert _code(r, 409) == "modifiee_ailleurs" and r.json()["detail"]["version"] == q["version"]
    q = _ok(client.patch(f"/api/preuves/{p['id']}", headers=h, json={"date_fin_validite": None}), 200)
    assert q["date_fin_validite"] is None and q["valeur"]["numero"] == "12345"
    assert _code(client.patch(f"/api/preuves/{p['id']}", headers=h, json={"valeur": None}), 422) == "valeur_invalide"
    assert _code(client.post(f"/api/preuves/{p['id']}/retirer", headers=h, json={"version": 0}), 409) == \
        "modifiee_ailleurs"


def test_modifier_une_preuve_documentee_recontrole_le_passage(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                   source={"doc_id": doc_id, "passage": PASSAGE_REF}))
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={"valeur": dict(REF_VAL, montant_ht=95000)})
    assert _code(r, 422) == "valeur_hors_passage"
    q = _ok(client.get(f"/api/preuves/{p['id']}", headers=h), 200)
    assert q["valeur"]["montant_ht"] == 85000 and q["version"] == p["version"]          # rien n'a changé
    q = _ok(client.patch(f"/api/preuves/{p['id']}", headers=h, json={"valeur": {k: v for k, v in REF_VAL.items()
                                                                               if k != "montant_ht"}}), 200)
    assert q["source_libelle"] == "trouvé dans vos documents" and "montant_ht" not in q["valeur"]


def test_numeros_stables_jamais_reutilises_et_contenu_efface(client, auth):
    h = auth["headers"]
    a = _ok(_creer(client, h, nature="salarie", valeur={"nom": "Hélène Le Gall", "fonction": "Couvreuse",
                                                        "chantiers": "Lycée de Brest"}))
    b = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Échafaudage"}))
    assert b["numero"] == a["numero"] + 1
    assert client.delete(f"/api/preuves/{b['id']}", headers=h).status_code == 204
    assert client.get(f"/api/preuves/{b['id']}", headers=h).status_code == 404
    assert client.delete(f"/api/preuves/{a['id']}", headers=h).status_code == 204
    c = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Nacelle"}))
    assert c["numero"] == b["numero"] + 1 and c["ref"] == f"F{b['numero'] + 1}"           # F2 n'est jamais repris
    from app.models import Preuve
    db = _db()
    try:
        row = db.get(Preuve, a["id"])
        assert row.statut == "supprimee" and row.valeur is None and row.source is None and row.empreinte == ""
        assert pv.personnes(db, [_uid(auth["email"])]) == []                            # le nom est parti
    finally:
        db.close()
    assert [x["id"] for x in _ok(client.get("/api/preuves", headers=h), 200)["preuves"]] == [c["id"]]


def test_limite_du_nombre_de_preuves(client, auth, monkeypatch):
    monkeypatch.setattr(pv, "MAX_PREUVES", 1)
    h = auth["headers"]
    _ok(_creer(client, h, nature="materiel", valeur={"designation": "Nacelle"}))
    assert _code(_creer(client, h, nature="materiel", valeur={"designation": "Grue"}), 409) == "trop_de_preuves"


# ═══ 5. Isolation : une organisation ne voit jamais les preuves d'une autre ═══════════════════

def test_un_autre_compte_recoit_404_partout(client, auth):
    h = auth["headers"]
    doc_id = _kb(client, h)
    p = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                   source={"doc_id": doc_id, "passage": PASSAGE_REF}))
    _e2, h2 = _register(client)
    for method, url, body in [("get", f"/api/preuves/{p['id']}", None),
                              ("get", f"/api/preuves/{p['id']}/passage", None),
                              ("patch", f"/api/preuves/{p['id']}", {"valeur": {"objet": "x"}}),
                              ("post", f"/api/preuves/{p['id']}/accepter", None),
                              ("post", f"/api/preuves/{p['id']}/retirer", None),
                              ("delete", f"/api/preuves/{p['id']}", None)]:
        r = getattr(client, method)(url, headers=h2, **({"json": body} if body is not None else {}))
        assert r.status_code == 404 and r.json()["detail"]["code"] == "preuve_introuvable", (method, url, r.text)
    assert _ok(client.get("/api/preuves", headers=h2), 200)["preuves"] == []
    assert _ok(client.get(f"/api/preuves/{p['id']}", headers=h), 200)["valeur"] == REF_VAL     # rien n'a bougé
    assert client.get("/api/preuves", headers={}).status_code == 401


def test_les_membres_de_l_organisation_partagent_les_preuves(client, auth):
    from app.models import PlanType, User
    h = auth["headers"]
    db = _db()
    try:
        db.query(User).filter(User.email == auth["email"]).first().plan = PlanType.pro
        db.commit()
    finally:
        db.close()
    r = client.post("/api/org/invite", headers=h, json={"email": f"membre_{uuid.uuid4().hex[:6]}@test.fr"})
    assert r.status_code == 201, r.text
    login = client.post("/api/auth/login", json={"email": r.json()["email"], "password": r.json()["temp_password"]})
    assert login.status_code == 200, login.text
    hm = _h(login.json()["access_token"])
    p = _ok(_creer(client, hm, nature="materiel", valeur={"designation": "Nacelle"}))
    from app.models import Preuve
    db = _db()
    try:
        assert db.get(Preuve, p["id"]).owner_id == _uid(auth["email"])        # portée par l'organisation
    finally:
        db.close()
    assert [x["id"] for x in _ok(client.get("/api/preuves", headers=h), 200)["preuves"]] == [p["id"]]
    # Le passage d'un document déposé par un collègue appuie une preuve de l'organisation.
    doc_id = _kb(client, hm)
    _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
               source={"doc_id": doc_id, "passage": PASSAGE_REF}))


def _preuve_d_invitation(owner, invite_id=7):
    """Vague 4 (prévue) : une preuve DÉTENUE par un membre du groupement, dans le tenant du chef de file."""
    from app.models import Preuve
    db = _db()
    try:
        p = Preuve(owner_id=owner, proprietaire_kind="invitation", proprietaire_invite_id=invite_id, numero=1,
                   nature="salarie", valeur={"nom": "Gwenaël Kerjean", "fonction": "Charpentier"},
                   type_source="declare", source={}, statut="acceptee")
        db.add(p)
        db.commit()
        return p.id
    finally:
        db.close()


def test_preuve_d_un_membre_du_groupement_jamais_lue_par_le_chef_de_file(client, auth):
    h = auth["headers"]
    owner = _uid(auth["email"])
    mien = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Nacelle"}))
    pid = _preuve_d_invitation(owner)
    assert mien["numero"] == 1                                     # numérotation propre à chaque détenteur
    assert client.get(f"/api/preuves/{pid}", headers=h).status_code == 404
    assert [x["id"] for x in _ok(client.get("/api/preuves", headers=h), 200)["preuves"]] == [mien["id"]]
    assert _ok(client.get("/api/preuves", headers=h), 200)["compteurs"]["salarie"]["acceptee"] == 0
    db = _db()
    try:
        assert [f["id"] for f in pv.faits_autorises(db, owner)] == [mien["id"]]
        assert pv.exporter(db, owner)[0]["ref"] == "F1" and len(pv.exporter(db, owner)) == 1
        # … mais son nom est masqué avant l'IA comme les autres (on ne prend aucun risque).
        assert {"nom": "Gwenaël Kerjean", "fonction": "Charpentier"} in pv.personnes(db, [owner])
    finally:
        db.close()
    n = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Grue"}))
    assert n["numero"] == 2


# ═══ 6. Ce que reçoit la rédaction (A) ══════════════════════════════════════════════════════

def test_faits_autorises_contrat_pour_la_redaction(client, auth):
    h = auth["headers"]
    owner = _uid(auth["email"])
    doc_id = _kb(client, h)
    ref = _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
                     source={"doc_id": doc_id, "passage": PASSAGE_REF}))
    sal = _ok(_creer(client, h, nature="salarie", valeur={"nom": "Yann Tanguy", "fonction": "Conducteur de travaux",
                                                          "experience_annees": 15, "diplomes": "BTS Bâtiment",
                                                          "chantiers": "Collège de Lorient"}))
    exp = _ok(_creer(client, h, nature="qualification", valeur={"nom": "Qualibat 1312"},
                     date_fin_validite=(pv.aujourd_hui() - timedelta(days=10)).isoformat()))
    val = _ok(_creer(client, h, nature="qualification", valeur={"nom": "Qualibat 3194"},
                     date_fin_validite=(pv.aujourd_hui() + timedelta(days=10)).isoformat()))
    assert _ok(client.get(f"/api/preuves/{exp['id']}", headers=h), 200)["expiree"] is True
    assert _ok(client.get(f"/api/preuves/{val['id']}", headers=h), 200)["jours_restants"] == 10
    db = _db()
    try:
        faits = pv.faits_autorises(db, owner)
        assert [f["ref"] for f in faits] == [ref["ref"], sal["ref"], val["ref"]]          # ordre des numéros
        f = faits[0]
        assert set(f) == {"ref", "id", "numero", "nature", "nature_libelle", "type_source", "source_libelle",
                          "appuie", "texte", "texte_ia", "valeur", "source", "date_source", "a_reconfirmer",
                          "date_fin_validite", "proprietaire"}
        assert f["appuie"] == "entreprise" and f["source_libelle"] == "trouvé dans vos documents"
        assert f["proprietaire"] == {"kind": "organisation", "invite_id": None}
        s = faits[1]
        assert s["appuie"] == "entreprise_declaration" and "Yann Tanguy" in s["texte"] and "15 ans" in s["texte"]
        for interdit in ("Yann", "Tanguy", "15", "BTS", "Collège"):                   # ni nom ni CV vers l'IA
            assert interdit not in s["texte_ia"], s["texte_ia"]
        assert s["texte_ia"] == "Équipe : une personne de l'équipe, Conducteur de travaux"
        from app.services.pii import from_team, team_of_users
        pz = from_team(team_of_users(db, [owner]))
        assert pv.texte_pour_ia(s, pz) == "Équipe : [Conducteur de travaux 1], Conducteur de travaux"
        assert [f["ref"] for f in pv.faits_autorises(db, owner, natures=["qualification"])] == [val["ref"]]
        assert [(x["ref"], x["raison"]) for x in pv.faits_ecartes(db, owner)] == [(exp["ref"], "expiree")]
        # Plus tard (jour donné) : la qualification valable expire à son tour.
        assert [f["ref"] for f in pv.faits_autorises(db, owner, jour=pv.aujourd_hui() + timedelta(days=11))] == \
            [ref["ref"], sal["ref"]]
    finally:
        db.close()


def test_noms_des_fiches_equipe_masques_avant_l_ia(client, auth):
    """Doctrine § 7, règle 9 : un nom saisi seulement dans « Mes preuves » ne part pas à l'IA."""
    h = auth["headers"]
    _ok(_creer(client, h, nature="salarie", valeur={"nom": "Maëlys Kerbrat", "fonction": "Cheffe de chantier"},
               statut="proposee"))
    owner = _uid(auth["email"])
    db = _db()
    try:
        from app.services.pii import from_team, team_of_users
        pz = from_team(team_of_users(db, [owner]))
        masque = pz.mask("Mme Kerbrat encadrera le chantier ; Maëlys Kerbrat a 12 ans de métier.")
        assert "Kerbrat" not in masque and "Maëlys" not in masque
        assert pz.unmask(masque) == "Mme Kerbrat encadrera le chantier ; Maëlys Kerbrat a 12 ans de métier."
    finally:
        db.close()


def test_jamais_le_mot_verifie(client, auth):
    """Doctrine § 7, règle 3 : Adjugo dit où il a trouvé le fait, jamais qu'il est « vérifié »."""
    import ast
    import inspect
    textes = [pv.LIB_TROUVE, pv.LIB_JUSTIFICATIF, pv.LIB_DECLARE, pv.LIB_PUBLIC, pv.LIB_DECP, pv.LIB_ESTIMATION,
              pv.MSG_CV, *pv.RAISONS.values(), *pv.TYPE_SOURCE_LIBELLES.values(), *pv.NATURE_LIBELLES.values(),
              *pv.STATUT_LIBELLES.values()]
    # Toutes les chaînes du module et du router (messages d'erreur compris), hors documentation.
    messages = []
    import app.routers.preuves as rp
    for mod in (pv, rp):
        arbre = ast.parse(inspect.getsource(mod))
        docs = {id(n.body[0].value) for n in ast.walk(arbre)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        messages += [n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
    assert any("passage n'a pas été retrouvé" in m for m in messages)
    h = auth["headers"]
    data = _ok(client.get("/api/preuves", headers=h), 200)
    for t in textes + messages + [json.dumps(data, ensure_ascii=False)]:
        assert "vérifi" not in t.lower() and "verifie" not in t.lower() and "certifié par adjugo" not in t.lower(), t


# ═══ 7. Démo en lecture seule ════════════════════════════════════════════════════════════════

def test_la_demo_ne_peut_rien_ecrire(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    hd = _h(r.json()["access_token"])
    assert client.get("/api/preuves", headers=hd).status_code == 200
    r = _creer(client, hd, nature="materiel", valeur={"designation": "Nacelle"})
    assert r.status_code == 403 and r.json()["detail"] == ("La démo est en lecture guidée : créez votre compte "
                                                           "gratuit pour renseigner vos preuves.")
    for method, url in [("patch", "/api/preuves/1"), ("delete", "/api/preuves/1"), ("post", "/api/preuves/1/accepter"),
                        ("post", "/api/preuves/1/retirer")]:
        r = getattr(client, method)(url, headers=hd, **({"json": {}} if method != "delete" else {}))
        assert r.status_code == 403, (method, url, r.text)


# ═══ 8. RGPD : export, effacement, transfert de propriété ═══════════════════════════════════

def test_export_rgpd_contient_les_preuves_et_les_cv(client, auth):
    h = auth["headers"]
    _ok(_creer(client, h, nature="salarie", valeur={"nom": "Yann Tanguy", "fonction": "Couvreur",
                                                    "diplomes": "CAP Couvreur"}))
    b = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Grue"}))
    assert client.delete(f"/api/preuves/{b['id']}", headers=h).status_code == 204
    data = client.get("/api/rgpd/export", headers=h).json()
    assert len(data["mes_preuves"]) == 1
    e = data["mes_preuves"][0]
    assert e["valeur"] == {"nom": "Yann Tanguy", "fonction": "Couvreur", "diplomes": "CAP Couvreur"}
    assert e["source_libelle"] == "déclaré par vous" and e["statut"] == "acceptee" and e["ref"].startswith("F")


def test_effacement_du_compte_efface_toutes_les_preuves(client):
    from app.models import Preuve
    email, h = _register(client)
    owner = _uid(email)
    doc_id = _kb(client, h)
    _ok(_creer(client, h, nature="reference", valeur=REF_VAL, type_source="documents",
               source={"doc_id": doc_id, "passage": PASSAGE_REF}))
    s = _ok(_creer(client, h, nature="salarie", valeur={"nom": "Yann Tanguy", "fonction": "Couvreur"}))
    assert client.delete(f"/api/preuves/{s['id']}", headers=h).status_code == 204          # ligne réservée
    _preuve_d_invitation(owner)
    r = client.post("/api/rgpd/delete-account", headers=h, json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert db.query(Preuve).filter(Preuve.owner_id == owner).count() == 0
    finally:
        db.close()


def test_transfert_de_propriete_les_preuves_suivent(client):
    from app.models import PlanType, Preuve, User
    email, h = _register(client)
    db = _db()
    try:
        db.query(User).filter(User.email == email).first().plan = PlanType.pro
        db.commit()
    finally:
        db.close()
    a = _ok(_creer(client, h, nature="materiel", valeur={"designation": "Nacelle"}))
    b = _ok(_creer(client, h, nature="salarie", valeur={"nom": "Yann Tanguy", "fonction": "Couvreur"}))
    r = client.post("/api/org/invite", headers=h, json={"email": f"repreneur_{uuid.uuid4().hex[:6]}@test.fr"})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    r = client.post("/api/org/transfer-ownership", headers=h, json={"new_owner_id": new_id})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert {p.owner_id for p in db.query(Preuve).filter(Preuve.id.in_([a["id"], b["id"]]))} == {new_id}
        assert [f["ref"] for f in pv.faits_autorises(db, new_id)] == [a["ref"], b["ref"]]   # mêmes renvois
        assert pv.faits_autorises(db, _uid(email)) == []
    finally:
        db.close()
    h_ancien = _h(r.json()["access_token"])                       # l'ancien propriétaire, devenu membre
    assert [x["id"] for x in _ok(client.get("/api/preuves", headers=h_ancien), 200)["preuves"]] == [a["id"], b["id"]]
    c = _ok(_creer(client, h_ancien, nature="materiel", valeur={"designation": "Grue"}))
    assert c["numero"] == b["numero"] + 1


def test_transferer_ne_heurte_jamais_un_numero(client):
    from app.models import Preuve
    e1, h1 = _register(client)
    e2, h2 = _register(client)
    old, new = _uid(e1), _uid(e2)
    for d in ("Nacelle", "Grue", "Benne"):
        _ok(_creer(client, h1, nature="materiel", valeur={"designation": d}))
    for d in ("Pelle", "Camion"):
        _ok(_creer(client, h2, nature="materiel", valeur={"designation": d}))          # numéros 1 et 2 : heurts
    db = _db()
    try:
        assert pv.transferer(db, old, new) == 3
        db.commit()
        rows = db.query(Preuve).filter(Preuve.owner_id == new).order_by(Preuve.numero).all()
        assert [(r.numero, r.valeur["designation"]) for r in rows] == [
            (1, "Nacelle"), (2, "Grue"), (3, "Benne"), (4, "Pelle"), (5, "Camion")]
        assert pv.transferer(db, new, new) == 0 and pv.transferer(db, None, new) == 0
    finally:
        db.close()


def test_effacement_d_un_membre_ses_preuves_restent_a_l_organisation(client):
    from app.models import PlanType, Preuve, User
    email, h = _register(client)
    owner = _uid(email)
    db = _db()
    try:
        db.query(User).filter(User.email == email).first().plan = PlanType.pro
        db.commit()
    finally:
        db.close()
    r = client.post("/api/org/invite", headers=h, json={"email": f"membre_{uuid.uuid4().hex[:6]}@test.fr"})
    mid, mmail, mpwd = r.json()["id"], r.json()["email"], r.json()["temp_password"]
    hm = _h(client.post("/api/auth/login", json={"email": mmail, "password": mpwd}).json()["access_token"])
    p = _ok(_creer(client, hm, nature="materiel", valeur={"designation": "Nacelle"}))
    # Cas ancien (avant la portée par l'organisation) : une ligne portée par le membre lui-même.
    db = _db()
    try:
        db.add(Preuve(owner_id=mid, numero=1, nature="materiel", valeur={"designation": "Grue"}, statut="acceptee"))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/rgpd/delete-account", headers=hm, json={"password": mpwd, "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert db.query(Preuve).filter(Preuve.owner_id == mid).count() == 0
        rows = db.query(Preuve).filter(Preuve.owner_id == owner).order_by(Preuve.numero).all()
        assert [(x.numero, x.valeur["designation"]) for x in rows] == [(1, "Nacelle"), (2, "Grue")]
        assert rows[0].id == p["id"]
    finally:
        db.close()


# ═══ 9. Migration (SQLite : à neuf, création par la révision, rejeu, retour arrière) ══════════

def test_migration_preuves_a_neuf_creation_rejeu_et_retour_arriere(tmp_path):
    import sqlalchemy as sa
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "preuves.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=root, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def schema(eng):
        insp = sa.inspect(eng)
        cols = {c["name"]: (str(c["type"]), c["nullable"], str(c.get("default"))) for c in insp.get_columns("preuves")}
        idx = {i["name"]: tuple(i["column_names"]) for i in insp.get_indexes("preuves")}
        uq = {tuple(u["column_names"]) for u in insp.get_unique_constraints("preuves")}
        fks = {(tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys("preuves")}
        return cols, idx, uq, fks

    run("upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    neuf = schema(eng)                                 # table créée depuis les modèles (révision ancienne)
    assert ("owner_id", "proprietaire_invite_id", "numero") in neuf[2]
    assert {"ix_preuves_owner_id", "ix_preuves_source_doc_id", "ix_preuves_empreinte"} <= set(neuf[1])
    assert ((("owner_id",), "users")) in neuf[3]
    # Base « production » d'avant : pas de table ; la révision la crée elle-même.
    with eng.begin() as cn:
        cn.execute(sa.text("DROP TABLE preuves"))
        cn.execute(sa.text("INSERT INTO users (email, hashed_password, full_name) VALUES ('p@t.fr', 'x', 'P')"))
    eng.dispose()
    run("stamp", "u5v6essaigardefou")
    run("upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    assert schema(eng) == neuf                         # même schéma, colonne par colonne, index par index
    with eng.begin() as cn:
        uid = cn.execute(sa.text("SELECT id FROM users WHERE email = 'p@t.fr'")).scalar()
        cn.execute(sa.text("INSERT INTO preuves (owner_id, numero, nature) VALUES (:u, 1, 'materiel')"), {"u": uid})
        row = cn.execute(sa.text("SELECT proprietaire_kind, proprietaire_invite_id, type_source, statut, origine, "
                                 "empreinte, version FROM preuves")).one()
        assert tuple(row) == ("organisation", 0, "declare", "proposee", "saisie", "", 0)
        with pytest.raises(Exception):
            cn.execute(sa.text("INSERT INTO preuves (owner_id, numero, nature) VALUES (:u, 1, 'materiel')"),
                       {"u": uid})
    eng.dispose()
    run("stamp", "u5v6essaigardefou")
    run("upgrade", "head")                             # rejouée : aucune erreur, données gardées
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    with eng.connect() as cn:
        assert cn.execute(sa.text("SELECT count(*) FROM preuves")).scalar() == 1
    eng.dispose()
    run("downgrade", "u5v6essaigardefou")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    assert "preuves" not in sa.inspect(eng).get_table_names()
    eng.dispose()
    run("upgrade", "head")
