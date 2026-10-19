"""
Rédaction, vague 4 — documents privés déposés par le lien (décision 5 a) : contre-relecture de la reprise (contrat
docs/REDACTION_V4_GROUPEMENT.md § 21.15). Chaque test reproduit une remarque ; tous échouaient sur 31d384b.

 • une plaquette écrite en « nous / nos » n'est jamais prise pour un CV, même quand le nom de l'entreprise commence
   par un prénom (« Simon Frères », « Thomas Toiture ») ou qu'il est suivi de son métier (« Breizh Toit » /
   « Couvreur zingueur à Quimper depuis 1990 ») : déposée par le lien, et lue pour un compte (« Mon savoir-faire ») ;
   un vrai CV reste refusé ;
 • une écriture du partenaire dans ses brouillons (« J'écris moi-même », relire un fait, valider le texte du chef de
   file) prend le verrou de l'invitation d'abord : une réinitialisation de l'espace ou la suppression d'un document
   au même moment ne laisse ni le nom ni le passage du document, ni dans le nouvel espace, ni dans aucune table.

Les « courses » lancent l'autre requête dans un autre fil, au milieu de l'écriture, et l'attendent au plus
quelques secondes : sous SQLite (aucun verrou de ligne), elle passe tout de suite et l'écriture la voit en relisant
l'invitation et ses passages juste avant d'écrire ; sous Postgres, elle attend le verrou de l'invitation et passe
juste après l'écriture, qu'elle nettoie. Le même test vaut pour les deux bases. Aucun appel réseau : le client IA
est simulé.
"""
import json
import threading

from app.services import atelier_groupement as ag
from app.services import depot_lien as dl
from app.services import faits_sources as fs
from app.services import fiches_import as fi
from tests.test_redaction_socle0 import _db, fake_llm  # noqa: F401
from tests.test_redaction_v4_depot_lien import _deposer, _deposer_ok
from tests.test_redaction_v4_depot_lien_relecture import TEXTE_IA, _memoire, _partout, _secret
from tests.test_redaction_v4_groupement import P, _aide, _groupement, _part_a, _reponse_partenaire

ATTENTE = 2.0                   # secondes : l'autre requête passe (SQLite) ou attend le verrou (Postgres)


# ═══ 1. Une plaquette en « nous / nos » n'est pas un CV ════════════════════════════════════

SIMON = ("Simon Frères\n\nExpérience\nEntreprise familiale fondée en 1978, nous intervenons en charpente et ossature "
         "bois.\n\nCompétences\nCharpente traditionnelle, ossature bois, extensions, isolation par l'extérieur.\n\n"
         "Formations\nNotre équipe est qualifiée Qualibat RGE et formée au travail en hauteur.\n")
BREIZH = ("Breizh Toit\nCouvreur zingueur à Quimper depuis 1990\n\nExpérience\nNous avons réalisé plus de 300 chantiers "
          "pour des communes et des bailleurs du Finistère.\n\nCompétences\nCouverture ardoise et zinc, zinguerie, "
          "bardage, désamiantage sous-section 4.\n\nFormation\nNos compagnons sont formés chaque année au travail en "
          "hauteur et à l'amiante.\n")
# Un nom d'entreprise qui commence par un prénom courant, sans mot d'organisme connu : la voix de l'entreprise suffit.
TANGUY = ("Tanguy Kervella\n\nExpérience\nDepuis 1995, nous couvrons les écoles et les mairies du Finistère.\n\n"
          "Compétences\nArdoise, zinc, cuivre.\n\nFormation\nNos compagnons suivent chaque année une formation au "
          "travail en hauteur.\n")
PLAQUETTES = (("plaquette-simon.txt", SIMON), ("plaquette-breizh.txt", BREIZH), ("plaquette-tanguy.txt", TANGUY))
# De vrais CV, eux, restent des CV : un salarié présenté par son entreprise (« chez nous » une fois), un intitulé de
# fonction sous un prénom rare.
CV_SALARIE = ("Yann Tanguy\nConducteur de travaux\n\nExpérience\nChez nous depuis 2012 : 40 chantiers de couverture "
              "conduits.\n\nFormation\nBTS Bâtiment (2010)\n\nCompétences\nZinguerie, ardoise.\n")
CV_FONCTION = "Gwenhaël KERJEAN\nCheffe de chantier\n\nExpérience\nConduite de chantiers.\n\nFormation\nBTS\n"


class _Doc:
    def __init__(self, i, nom, texte):
        self.id, self.name, self.text, self.char_count = i, nom, texte, len(texte)


def test_plaquette_en_nous_deposee_par_le_lien_n_est_pas_un_cv(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    for nom, texte in PLAQUETTES:
        r = _deposer(pa, nom, texte)
        assert r.status_code == 201, (nom, r.text)
        assert r.json()["depose"]["passages_cv_retires"] is False, nom
    for nom, texte in (("presentation-yann.txt", CV_SALARIE), ("presentation-kerjean.txt", CV_FONCTION)):
        r = _deposer(pa, nom, texte)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "document_cv", (nom, r.text)


def test_plaquette_en_nous_du_savoir_faire_d_un_compte_reste_lue():
    """« Mon savoir-faire » d'un compte : une plaquette n'est pas marquée « cv » (elle serait écartée en entier de
    l'aide de l'IA et montrée comme un CV dans « Partir de vos anciens dossiers »)."""
    for i, (nom, texte) in enumerate(PLAQUETTES, start=880001):
        assert fi.statut_document(_Doc(i, "plaquette.pdf", texte)) is None, nom
        assert not fi.lignes_privees(texte)["cv"], nom
    for i, texte in enumerate((CV_SALARIE, CV_FONCTION), start=880101):
        assert fi.statut_document(_Doc(i, "presentation.pdf", texte)) == fi.DOC_CV
    # Un nom d'entreprise (« Frères », « Fils », « Atelier », un métier) n'est pas un nom de personne à masquer.
    assert fi.noms_probables("Simon Frères, Tanguy Fils et Thomas Toiture interviennent.", etendu=True) == []
    # Un intitulé de fonction n'a ni lieu, ni durée, ni chiffre.
    assert fi._intitule_de_fonction("Cheffe de chantier désamiantage")
    assert not fi._intitule_de_fonction("Couvreur zingueur à Quimper depuis 1990")


# ═══ 2. Courses : réinitialisation ou suppression pendant une écriture du partenaire ═════════════════

def _pendant(action):
    """Lance `action` dans un autre fil (une autre requête au même moment) et l'attend au plus ATTENTE secondes.
    Rend (fil, résultat) : le fil est à attendre après l'écriture."""
    out = {}

    def run():
        try:
            out["r"] = action()
        except Exception as e:      # noqa: BLE001 — relu par le test
            out["e"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(ATTENTE)
    return t, out


def _fin(t, out):
    t.join(60)
    assert not t.is_alive(), "l'autre requête n'a jamais fini"
    assert "e" not in out, repr(out.get("e"))
    return out["r"]


def _reinitialiser(invite_id):
    """Celui qui détient le lien (le chef de file, par exemple) réinitialise l'espace : la nouvelle clé."""
    from app.models import ProjectInvite
    db = _db()
    try:
        return ag.ouvrir_espace(db, db.get(ProjectInvite, invite_id), reinitialiser=True)["cle"]
    finally:
        db.close()


def _supprimer(invite_id, cle, doc_id):
    """Le partenaire supprime un document (depuis un autre onglet)."""
    from app.models import Project, ProjectInvite
    db = _db()
    try:
        inv = db.get(ProjectInvite, invite_id)
        acc = ag.acces_partenaire(db, inv, db.get(Project, inv.project_id), mode="lien", cle=cle)
        return dl.supprimer(db, acc, doc_id)
    finally:
        db.close()


def _au_controle(monkeypatch, mode, action):
    """Pendant le contrôle des faits (`mode` : « utilisateur » pour « J'écris moi-même », « ia » pour valider le texte
    du chef de file), une seule fois : `action` lancée dans un autre fil."""
    vrai = fs.controler
    lance = {}

    def controler(*args, **kw):
        if kw.get("mode") == mode and lance.get("pret") and "fil" not in lance:
            lance["fil"] = _pendant(action)
        return vrai(*args, **kw)
    monkeypatch.setattr(fs, "controler", controler)
    return lance


def _avec_document(client, auth, fake_llm, monkeypatch, texte_ia=TEXTE_IA):
    """Un partenaire par le lien, un document déposé, un brouillon de l'aide de l'IA qui le cite."""
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    secret = _secret()
    nom = f"Memoire-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    did = _deposer_ok(pa, nom, _memoire(secret))["depose"]["id"]
    fake_llm(_reponse_partenaire(texte_ia)[0])
    assert _aide(pa, sid)[0]["status"] == "done"
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert nom in json.dumps(br, ensure_ascii=False)          # contrôle : le brouillon cite le document
    return pid, sid, a, pa, did, secret, nom, br


def _rien_pour_la_nouvelle_cle(client, a, sid, cle, nom, secret):
    hc = {ag.ENTETE_CLE: cle}
    for chemin in (f"/sections/{sid}", "", "/export", "/documents"):
        r = client.get(f"/api/invite/{a['token']}/redaction{chemin}", headers=hc)
        assert r.status_code == 200, (chemin, r.text)
        assert nom not in r.text and secret not in r.text, chemin
    assert _partout(secret) == []


def test_reinitialisation_pendant_l_enregistrement(client, auth, fake_llm, monkeypatch):
    pid, sid, a, pa, did, secret, nom, br = _avec_document(client, auth, fake_llm, monkeypatch)
    lance = _au_controle(monkeypatch, "utilisateur", lambda: _reinitialiser(a["id"]))
    lance["pret"] = True
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": br["texte"] + " Le tri est fait sur place.",
                                              "base_brouillon_id": br["id"], "base_version_id": None})
    cle = _fin(*lance["fil"])
    # SQLite : l'enregistrement voit la réinitialisation (409, rien d'écrit) ; Postgres : la réinitialisation attend la
    # fin de l'enregistrement, puis efface ce qu'il a rangé.
    assert r.status_code in (200, 409), r.text
    if r.status_code == 409:
        assert r.json()["detail"]["code"] == "espace_reinitialise"
        assert r.json()["detail"]["message"] == ag.MSG_ECRITURE_ESPACE_REINITIALISE
    _rien_pour_la_nouvelle_cle(client, a, sid, cle, nom, secret)
    assert client.get(f"/api/invite/{a['token']}/redaction/sections/{sid}",
                      headers={ag.ENTETE_CLE: cle}).json()["brouillon"] is None
    # L'ancienne clé n'ouvre plus rien.
    assert pa.get(f"/sections/{sid}").json().get("brouillon") is None


def test_document_supprime_pendant_l_enregistrement(client, auth, fake_llm, monkeypatch):
    pid, sid, a, pa, did, secret, nom, br = _avec_document(client, auth, fake_llm, monkeypatch)
    cle = pa.h[ag.ENTETE_CLE]
    lance = _au_controle(monkeypatch, "utilisateur", lambda: _supprimer(a["id"], cle, did))
    lance["pret"] = True
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": br["texte"] + " Le tri est fait sur place.",
                                              "base_brouillon_id": br["id"], "base_version_id": None})
    assert r.status_code == 200, r.text
    assert _fin(*lance["fil"]) == 1
    nouveau = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert nouveau["id"] != br["id"] and "Le tri est fait sur place." in nouveau["texte"]
    assert nom not in json.dumps(nouveau, ensure_ascii=False) and secret not in json.dumps(nouveau, ensure_ascii=False)
    assert _partout(secret) == []


def test_reinitialisation_pendant_la_validation_du_texte_du_chef(client, auth, fake_llm, monkeypatch):
    """Le chef de file a écrit la partie ; le partenaire la valide (ses faits contrôlés sur ses documents) pendant que
    qui détient le lien réinitialise l'espace : le brouillon « Texte du chef de file accepté par vous » ne garde, pour
    le nouvel espace, ni le nom ni le passage du document."""
    pid, sid, a, pa, did, secret, nom, br = _avec_document(client, auth, fake_llm, monkeypatch)
    h = auth["headers"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Nous trions les déchets amiantés dans 6 big-bags étanches, évacués vers une "
                                  "installation de stockage agréée.", "base_version_id": None})
    assert r.status_code == 200, r.text
    v = pa.get(f"/sections/{sid}").json()["texte_commun"]["version_id"]
    lance = _au_controle(monkeypatch, "ia", lambda: _reinitialiser(a["id"]))
    lance["pret"] = True
    r = pa.post(f"/sections/{sid}/valider", {"version_id": v})
    cle = _fin(*lance["fil"])
    assert r.status_code in (200, 409), r.text
    if r.status_code == 409:
        assert r.json()["detail"]["code"] == "espace_reinitialise"
    _rien_pour_la_nouvelle_cle(client, a, sid, cle, nom, secret)


def test_document_supprime_pendant_la_validation_du_texte_du_chef(client, auth, fake_llm, monkeypatch):
    pid, sid, a, pa, did, secret, nom, br = _avec_document(client, auth, fake_llm, monkeypatch)
    h = auth["headers"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Nous trions les déchets amiantés dans 6 big-bags étanches, évacués vers une "
                                  "installation de stockage agréée.", "base_version_id": None})
    assert r.status_code == 200, r.text
    v = pa.get(f"/sections/{sid}").json()["texte_commun"]["version_id"]
    cle = pa.h[ag.ENTETE_CLE]
    lance = _au_controle(monkeypatch, "ia", lambda: _supprimer(a["id"], cle, did))
    lance["pret"] = True
    r = pa.post(f"/sections/{sid}/valider", {"version_id": v})
    assert r.status_code == 200, r.text
    assert _fin(*lance["fil"]) == 1
    p = pa.get(f"/sections/{sid}").json()
    assert p["statut"] == "validee" and p["brouillon"]["origine"] == "acceptee"
    assert nom not in json.dumps(p, ensure_ascii=False) and secret not in json.dumps(p, ensure_ascii=False)
    assert _partout(secret) == []


def test_document_supprime_pendant_la_relecture_d_un_fait(client, auth, fake_llm, monkeypatch):
    """« Relu par vous » sur un fait de son brouillon pendant la suppression d'un document qu'il cite : la relecture
    ne remet pas dans le brouillon la source effacée (nom du document, passage)."""
    texte = TEXTE_IA + " Nous mobilisons 3 opérateurs certifiés sur le chantier."
    pid, sid, a, pa, did, secret, nom, br = _avec_document(client, auth, fake_llm, monkeypatch, texte_ia=texte)
    fait = next(x for x in br["faits"] if "3 opérateurs" in (x.get("phrase") or x.get("fait") or ""))
    assert any(nom == (x.get("source") or {}).get("doc_nom") for x in br.get("faits_sources") or [])
    cle = pa.h[ag.ENTETE_CLE]
    vrai = ag._commune
    lance = {}

    def commune(db, section):
        if lance.get("pret") and "fil" not in lance:
            lance["fil"] = _pendant(lambda: _supprimer(a["id"], cle, did))
        return vrai(db, section)
    monkeypatch.setattr(ag, "_commune", commune)
    lance["pret"] = True
    r = pa.post(f"/sections/{sid}/faits/{fait['id']}", {"statut": "relu_par_vous"})
    assert "fil" in lance
    assert r.status_code == 200, r.text
    assert _fin(*lance["fil"]) == 1
    p = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert nom not in json.dumps(p, ensure_ascii=False) and secret not in json.dumps(p, ensure_ascii=False)
    assert _partout(secret) == []
