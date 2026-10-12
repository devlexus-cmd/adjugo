"""
Rédaction, vague 3 — l'ENSEMBLE : I (anciens dossiers), E1 (« Mes preuves ») et A (chaque fait a sa
source) branchés sur le même socle, de bout en bout.

Le parcours d'une TPE (étude § 8, V3 : « une TPE qui part de ses anciens dossiers et obtient un mémoire
dont chaque fait sur l'entreprise est relié à sa source ») :

  1. elle importe un ancien mémoire dans « Mon savoir-faire » : Adjugo PROPOSE des fiches avec leur
     passage exact (I) ; elle en coche deux, en laisse une proposée ;
  2. dans « Mes preuves » (E1), elle reprend une personne et une référence de son profil, retire la
     référence, ajoute un matériel ;
  3. elle rédige une partie (A) : seules les preuves cochées ou saisies deviennent des faits [F#]
     numérotés ; la proposée n'y est pas ; un élément du profil repris n'est remis QUE par sa fiche
     (jamais par le profil quand la fiche est retirée) ; ni nom, ni CV, ni qualification de la
     personne ne part à l'IA ; le CV est inséré tel quel ;
  4. libellés de source : « trouvé dans vos documents » avec le lien vers le passage, « déclaré par
     vous » ; une preuve décochée rend le fait à relire et bloque l'export ;
  5. « Insérer une fiche » (E1) relie ses faits à la fiche ; « Raccourcir » refuse une partie qui
     contient un CV, avant tout appel et tout débit ;
  6. export Word : aucun renvoi [F#], [P#], [CV F#], aucun libellé interne.
Aucun appel réseau : le fournisseur d'IA est simulé. Aucune donnée réelle.
"""
import json
import re
import time
import uuid

from app.services import faits_sources as fs
from app.services import llm
from tests.test_redaction_socle0 import fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _docx_xml, _etat, _projet

DOC = ("Mémoire technique — Breizh Couverture\n"
       "Quimper, le 12 mars 2024\n"
       "\n"
       "Nos références\n"
       "En 2023, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), réalisée "
       "seule par notre équipe.\n"
       "\n"
       "Nos qualifications\n"
       "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345), valable jusqu'au 31/12/2030.\n"
       "\n"
       "Nos moyens matériels\n"
       "Nous disposons en propre de 2 nacelles articulées de 16 m.\n")
P_REF = ("En 2023, réfection de la toiture de l'école Jules Ferry pour la Mairie de Quimper (85 000 € HT), réalisée "
         "seule par notre équipe.")
P_QUAL = "Nous sommes qualifiés Qualibat 3194 (certificat n° 12345), valable jusqu'au 31/12/2030."
P_MAT = "Nous disposons en propre de 2 nacelles articulées de 16 m."

TEAM = [{"nom": "Maëlys Kerbrat", "fonction": "Conductrice de travaux", "qualifications": "CACES R486"}]
REFERENCES = [{"intitule": "Couverture de la salle des sports de Kerlouan", "client": "Commune de Kerlouan",
               "annee": 2022}]
QUALIFS = [{"name": "Qualibat 1311", "expiration": "2025-01-31"}]        # expirée : jamais remise


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _register(client):
    from app.models import User
    email = f"v3e_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Dirigeant", "company_name": "Breizh Couverture"})
    assert r.status_code == 201, r.text
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        uid = u.id
    finally:
        db.close()
    return email, {"Authorization": "Bearer " + r.json()["access_token"]}, uid


def _ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def _system(kw) -> str:
    return llm._flatten_content(kw.get("system"))


def _contenu(kw) -> str:
    return _system(kw) + "\n" + "\n".join(llm._flatten_content(m.get("content")) for m in kw.get("messages") or [])


class _IA:
    """Le faux fournisseur : il lit les anciens dossiers (I) et rédige la partie (A), à partir de ce
    qu'il REÇOIT (renvois du bloc des faits, comme le ferait l'IA). Il garde chaque appel."""

    def __init__(self):
        self.lecture, self.redaction, self.raccourcir = [], [], []
        self.refs = {}

    def __call__(self, kw):
        sysp = _system(kw)
        if "Tu raccourcis" in sysp:
            self.raccourcir.append(kw)
            return "Texte raccourci.", "end_turn"
        if "dossier de présentation (le « mémoire technique »)" in sysp:
            self.redaction.append(kw)
            recu = _contenu(kw)
            m = re.search(r"\[(P\d+)\] \(déclaré par vous\) Effectif : 12", recu)
            p_eff = m.group(1) if m else "P99"
            r = self.refs
            texte = (f"Nous avons réalisé en 2023 la réfection de la toiture de l'école Jules Ferry pour la Mairie "
                     f"de Quimper, pour 85 000 € HT [{r['ref']}]. Nous sommes qualifiés Qualibat 3194 [{r['qual']}]. "
                     f"Notre équipe compte 12 salariés [{p_eff}].\n\n[CV {r['sal']}]\n")
            return texte, "end_turn"
        self.lecture.append(kw)
        return json.dumps({"fiches": [
            {"nature": "reference", "champs": {"objet": "Réfection de la toiture de l'école Jules Ferry",
                                               "acheteur": "Mairie de Quimper", "annee": 2023, "montant_ht": 85000,
                                               "role": "seul"}, "passage": P_REF},
            {"nature": "qualification", "champs": {"nom": "Qualibat 3194", "numero": "12345"},
             "date_fin_validite": "2030-12-31", "passage": P_QUAL},
            {"nature": "materiel", "champs": {"designation": "nacelles articulées de 16 m", "quantite": 2,
                                              "possession": "propriete"}, "passage": P_MAT},
        ]}, ensure_ascii=False), "end_turn"


def _attendre_lecture(client, h, doc_id):
    r = None
    for _ in range(300):
        r = client.get(f"/api/knowledge/{doc_id}/fiches", headers=h)
        assert r.status_code == 200, r.text
        if (r.json().get("lecture") or {}).get("statut") in ("lu", "echec"):
            return r.json()
        time.sleep(0.03)
    raise AssertionError(f"lecture jamais terminée : {r.json() if r is not None else None}")


def _version(client, h, pid, sid):
    return next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)["version_courante"]


def test_parcours_complet_anciens_dossiers_mes_preuves_redaction_libelles_export(client, fake_llm, monkeypatch):
    monkeypatch.delenv("ATELIER_LIBELLES_SOURCES", raising=False)
    ia = _IA()
    fake = fake_llm(ia)
    email, h, uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture", "city": "Quimper", "effectif": 12,
                                                     "team": TEAM, "references": REFERENCES,
                                                     "qualifications": QUALIFS}))

    # ── 1. I : un ancien mémoire, des fiches PROPOSÉES avec leur passage, l'utilisateur coche ──
    doc_id = _ok(client.post("/api/knowledge/text", headers=h,
                             json={"name": "Mémoire 2024.pdf", "text": DOC, "kind": "memoire"}))["doc"]["id"]
    _ok(client.post(f"/api/knowledge/{doc_id}/fiches", headers=h, json={"date_document": "2024-03-12"}), 202)
    etat = _attendre_lecture(client, h, doc_id)
    assert etat["lecture"]["statut"] == "lu" and etat["lecture"]["proposees"] == 3, etat["lecture"]
    par = {f["nature"]: f for f in etat["fiches"]}
    assert {f["statut"] for f in etat["fiches"]} == {"proposee"} and not any(f["utilisable"] for f in etat["fiches"])
    ref, qual, mat = par["reference"], par["qualification"], par["materiel"]
    for p in (ref, qual):
        _ok(client.post(f"/api/preuves/{p['id']}/accepter", headers=h, json={"version": p["version"]}))
    # Une seule lecture : la redemander ne rappelle pas l'IA.
    _ok(client.post(f"/api/knowledge/{doc_id}/fiches", headers=h, json={}))
    assert len(ia.lecture) == 1

    # ── 2. E1 : reprise du profil (une personne, une référence), une référence retirée, un ajout ──
    rep = _ok(client.get("/api/preuves/reprise", headers=h))
    elems = {(e["nature"], e["valeur"].get("nom") or e["valeur"].get("objet") or e["valeur"].get("libelle")): e
             for e in rep["elements"]}
    cles = [elems[("salarie", "Maëlys Kerbrat")]["cle"],
            elems[("reference", "Couverture de la salle des sports de Kerlouan")]["cle"]]
    creees = {p["nature"]: p for p in _ok(client.post("/api/preuves/reprise", headers=h, json={"cles": cles}))["creees"]}
    sal, kerlouan = creees["salarie"], creees["reference"]
    assert sal["source_libelle"] == "déclaré par vous" and sal["valeur"]["qualifications"] == "CACES R486"
    _ok(client.post(f"/api/preuves/{kerlouan['id']}/retirer", headers=h, json={"version": kerlouan["version"]}))
    camion = _ok(client.post("/api/preuves", headers=h, json={
        "nature": "materiel", "valeur": {"designation": "Camion grue", "quantite": 1}, "type_source": "declare"}), 201)
    liste = _ok(client.get("/api/preuves", headers=h))
    statuts = {p["ref"]: (p["statut"], p["utilisable"]) for p in liste["preuves"]}
    assert statuts[ref["ref"]] == ("acceptee", True) and statuts[qual["ref"]] == ("acceptee", True)
    assert statuts[mat["ref"]] == ("proposee", False) and statuts[kerlouan["ref"]] == ("retiree", False)
    assert statuts[sal["ref"]] == ("acceptee", True) and statuts[camion["ref"]] == ("acceptee", True)

    # ── 3. A : la partie est rédigée avec les faits NUMÉROTÉS ──
    ia.refs = {"ref": ref["ref"], "qual": qual["ref"], "sal": sal["ref"]}
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    r = _ok(client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={}), 202)
    assert _attendre(client, h, pid, r["tache"]["id"])["status"] == "done"
    assert len(ia.redaction) == 1
    envoye = _contenu(ia.redaction[0])
    # Les preuves cochées (I) et saisies ou reprises (E1) sont des faits [F#] typés…
    assert f"[{ref['ref']}] (trouvé dans vos documents) Référence : Réfection de la toiture de l'école Jules Ferry" in envoye
    assert f"[{qual['ref']}] (trouvé dans vos documents) Qualification : Qualibat 3194" in envoye
    assert f"[{camion['ref']}] (déclaré par vous) Matériel : Camion grue" in envoye
    assert re.search(re.escape(f"[{sal['ref']}] (déclaré par vous) Équipe : [Conductrice de travaux") + r" \d+\]", envoye)
    assert f"[CV {sal['ref']}]" in envoye
    # … la fiche seulement PROPOSÉE et la fiche RETIRÉE n'y sont pas ;
    assert f"[{mat['ref']}] (" not in envoye and f"[{kerlouan['ref']}] (" not in envoye
    # … le profil ne redit pas ce que « Mes preuves » gouverne : ni la référence retirée, ni la
    # personne reprise (ni son nom, ni sa qualification), ni la qualification expirée ; l'effectif
    # (non repris) reste remis depuis le profil.
    for interdit in ("Kerlouan", "Maëlys", "Kerbrat", "CACES", "R486", "1311"):
        assert interdit not in envoye, interdit
    assert re.search(r"\[P\d+\] \(déclaré par vous\) Effectif : 12", envoye)

    v = _version(client, h, pid, sid)
    texte = v["texte"]
    # Le CV est inséré tel quel, sans IA, dans le format de « Mes preuves ».
    assert f"**Maëlys Kerbrat**, conductrice de travaux [{sal['ref']}]" in texte
    assert f"- Qualifications et habilitations : CACES R486 [{sal['ref']}]" in texte
    # Libellés éteints par défaut (calibration à faire) : seul l'affichage d'A0, et rien n'est à relire.
    assert v["controle"] == {"libelles": False} and "faits_sources" not in v
    assert v["faits"] == [], v["faits"]

    # ── 4. Libellés de source (après la calibration) ──
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    v = _version(client, h, pid, sid)
    srcs = {f["fait"]: f["source"] for f in v["faits_sources"]}
    assert srcs["Jules Ferry"]["ref"] == ref["ref"] and srcs["Jules Ferry"]["libelle"] == "trouvé dans vos documents"
    assert srcs["Jules Ferry"]["lien"] == f"/api/preuves/{ref['id']}/passage"
    assert srcs["Qualibat 3194"]["ref"] == qual["ref"] and srcs["Qualibat 3194"]["libelle"] == "trouvé dans vos documents"
    assert srcs["12 salariés"]["libelle"] == "déclaré par vous" and srcs["12 salariés"]["ref"].startswith("P")
    assert srcs["CACES R486"]["ref"] == sal["ref"] and srcs["CACES R486"]["libelle"] == "déclaré par vous"
    c = v["controle"]
    assert c["libelles"] is True and c["sans_source"] == 0 and c["avec_source"] == c["total"] > 4
    assert c["message"] == f"Faits avec une source : {c['total']} sur {c['total']}"
    passage = _ok(client.get(srcs["Jules Ferry"]["lien"], headers=h))
    assert passage["passage"] == P_REF and passage["doc_id"] == doc_id
    assert not any("vérifi" in json.dumps(x, ensure_ascii=False).lower() for x in v["faits_sources"])

    # Une preuve décochée : le fait redevient à relire dès la lecture, et bloque l'export.
    p = _ok(client.get(f"/api/preuves/{ref['id']}", headers=h))
    _ok(client.post(f"/api/preuves/{ref['id']}/retirer", headers=h, json={"version": p["version"]}))
    v = _version(client, h, pid, sid)
    perdus = [f for f in v["faits"] if f["fait"] == "Jules Ferry"]
    assert perdus and perdus[0]["statut"] == "a_relire" and perdus[0]["detail"] == fs.DET_SOURCE_PERDUE
    bl = _etat(client, h, pid)["blocage"]
    assert bl["bloque"] and "faits_a_relire" in [x["code"] for x in bl["raisons"]]
    p = _ok(client.get(f"/api/preuves/{ref['id']}", headers=h))
    _ok(client.post(f"/api/preuves/{ref['id']}/accepter", headers=h, json={"version": p["version"]}))
    assert _version(client, h, pid, sid)["faits"] == []

    # ── 5. « Raccourcir » : la partie contient un CV → refusé avant tout appel et tout débit ──
    from app.models import User
    db = _db()
    try:
        avant = db.get(User, uid).analyses_used_this_month or 0
    finally:
        db.close()
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cv_dans_la_partie", r.text
    assert "Maëlys Kerbrat" in r.json()["detail"]["message"] and not ia.raccourcir
    db = _db()
    try:
        assert (db.get(User, uid).analyses_used_this_month or 0) == avant
    finally:
        db.close()

    # « Insérer une fiche » (E1) : telle quelle, sans IA ; ses faits sont reliés à la fiche (A).
    appels = len(fake.calls)
    v = _version(client, h, pid, sid)
    sec = _ok(client.post(f"/api/atelier/{pid}/sections/{sid}/inserer-preuve", headers=h,
                          json={"preuve_id": camion["id"], "base_version_id": v["id"]}))
    assert len(fake.calls) == appels
    v = _version(client, h, pid, sid)
    assert v["origine"] == "utilisateur" and v["texte"].rstrip().endswith("**Camion grue**\n- Quantité : 1")
    assert f"[{camion['ref']}]" not in v["texte"].split("[CV")[0][-200:] and "déclaré par vous" not in v["texte"]
    srcs = {f["fait"]: f["source"] for f in v["faits_sources"]}
    camion_src = [s for f, s in srcs.items() if "camion" in f.lower()]
    assert camion_src and all(s["ref"] == camion["ref"] for s in camion_src), srcs
    assert srcs["Jules Ferry"]["ref"] == ref["ref"]                       # les sources de l'IA restent
    assert v["faits"] == [] and sec

    # ── 6. Export Word : aucun renvoi, aucun libellé interne ──
    st = _etat(client, h, pid)
    bl = st["blocage"]
    assert [x["code"] for x in bl["raisons"]] == ["parties_vides"], bl
    _ok(client.post(f"/api/atelier/{pid}/derogation", headers=h,
                    json={"raison": "redigerai_dans_word", "texte": "Les autres parties dans Word",
                          "etat_hash": bl["etat_hash"]}))
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 200, r.text
    xml = _docx_xml(r.content)
    assert "Jules Ferry" in xml and "Qualibat 3194" in xml and "Maëlys Kerbrat" in xml and "CACES R486" in xml
    assert "Camion grue" in xml
    assert not re.search(r"\[\s*(?:CV\s+)?[FSPECG]\s*\d", xml), re.findall(r".{30}\[\s*(?:CV\s+)?[FSPECG]\s*\d.{10}", xml)
    for interne in ("trouvé dans vos documents", "déclaré par vous", "à relire", "vérifié"):
        assert interne not in xml, interne


def test_un_cv_insere_par_l_ia_ou_par_une_fiche_bloque_raccourcir_meme_sans_experience(client, fake_llm):
    """Un seul format de CV : celui que l'IA fait insérer (« [CV F2] ») et celui de « Insérer une fiche »
    ont les mêmes lignes, et le garde-fou de « Raccourcir » les reconnaît tous les deux — même pour une
    fiche « Équipe » qui n'a que des qualifications."""
    from app.services import preuves as pv
    from app.services import preuves_atelier as pa
    val = pv.valider_valeur("salarie", {"nom": "Gwendal Le Bihan", "fonction": "Chef d'équipe",
                                        "qualifications": "Habilitation électrique B1V"})
    f = fs.Fiche("F7", fs.T_DECLARE, fs.LIB_DECLARE, pv.texte_de("salarie", val), nature="salarie", valeur=val)
    par_ia = fs.inserer_cv("Encadrement :\n\n[CV F7]\n", [f])
    par_fiche = pa.bloc(pv.SALARIE, val)
    for ligne in pa.lignes_cv(val):
        assert ligne in par_ia and ligne in par_fiche
    # Contre l'API : la fiche « Équipe » enregistrée, le CV inséré par l'IA → « Raccourcir » refusé.
    ia = []

    def ans(kw):
        if "Tu raccourcis" in _system(kw):
            ia.append(kw)
            return "court", "end_turn"
        m = re.search(r"\[(F\d+)\] \(déclaré par vous\) Équipe", _contenu(kw))
        return ("Notre chef d'équipe encadre le chantier au quotidien et suit chaque étape avec les compagnons, "
                "la sécurité et la propreté du site.\n\n[CV " + (m.group(1) if m else "F0") + "]\n"), "end_turn"
    fake_llm(ans)
    email, h, uid = _register(client)
    _ok(client.put("/api/company/", headers=h, json={"name": "Breizh Couverture"}))
    _ok(client.post("/api/preuves", headers=h, json={"nature": "salarie", "valeur": val, "type_source": "declare"}), 201)
    pid = _projet(client, h)
    sid = _creer(client, h, pid)["sections"][0]["id"]
    r = _ok(client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={}), 202)
    assert _attendre(client, h, pid, r["tache"]["id"])["status"] == "done"
    assert "Habilitation électrique B1V" in _version(client, h, pid, sid)["texte"]
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/raccourcir", headers=h, json={"cible_mots": 30})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cv_dans_la_partie", r.text
    assert not ia
