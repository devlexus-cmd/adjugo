"""
Rédaction, vague 4 — contre-relecture des corrections (cloisonnement et anti-invention). Chaque test reproduit une
remarque qui échouait avant la correction (sondes jouées sur 6a040d2).

Contrat : docs/REDACTION_V4_GROUPEMENT.md (§ 3.1, § 13, § 20). Aucun appel réseau : le client IA est simulé.
"""
import json

from app.services import atelier_assemblage as asm
from app.services import atelier_groupement as ag
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from tests.test_convention_groupement import _register
from tests.test_redaction_socle0 import _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _etat
from tests.test_redaction_v4_assemblage import (SOURCES_AVANT, _faux_harmoniseur, _groupement_trois_jonctions,
                                                _harmoniser, _texte)
from tests.test_redaction_v4_corrections import _code_en_attente, _set_inv
from tests.test_redaction_v4_groupement import (SECRET_BROUILLON, SECRET_DOC, SECRET_EXTRAIT, TEXTE_IA_A, P, PC,
                                                _aide, _audit, _ecrire, _envoyer, _groupement, _part_a,
                                                _reponse_partenaire, _section_par)


def _bloque_par_faits(client, h, pid, sid) -> bool:
    raisons = {r["code"]: r for r in _etat(client, h, pid)["blocage"]["raisons"]}
    return any(x["section_id"] == sid for x in (raisons.get("faits_a_relire") or {}).get("sections", []))


# ═══ Cloisonnement : rattacher un lien dont l'espace est ouvert ═══════════════════════

def test_second_compte_ne_rattache_pas_un_lien_dont_l_espace_est_ouvert(client, auth, fake_llm):
    """Le partenaire travaille par le LIEN (sans adresse). Le chef de file, qui détient le lien, ouvre un second
    compte (autre entreprise) et rattache le lien : refusé tant qu'il ne détient pas la clé de l'espace. Il ne lit
    rien, et le vrai partenaire garde son espace. Le partenaire, lui, rattache le lien depuis son navigateur."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _ecrire(pa, sid, f"Brouillon privé {SECRET_BROUILLON}, jamais envoyé.")
    for verifie in (False, True):
        hx, _ex = _register(client, company="Compte fantôme", verified=verifie)
        r = client.post(f"/api/invite/{a['token']}/claim", headers=hx)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "espace_a_prouver", r.text
        assert "navigateur où vous rédigez" in r.json()["detail"]["message"]
        # Une clé fausse ne vaut rien non plus.
        r = client.post(f"/api/invite/{a['token']}/claim", headers={**hx, ag.ENTETE_CLE: "pas-la-bonne-cle"})
        assert r.status_code == 409
        px = PC(client, pid, hx)
        for chemin in ("", f"/sections/{sid}", "/export"):
            rr = px.get(chemin)
            assert rr.status_code == 404 and SECRET_BROUILLON not in rr.text, (chemin, rr.status_code)
        assert client.get("/api/shared", headers=hx).json() == []
    # Le vrai partenaire garde son espace : il lit, écrit, réinitialiserait s'il le voulait.
    v = pa.get().json()
    assert v["espace"]["cle_valide"] is True and not v["espace"].get("par_le_compte")
    assert SECRET_BROUILLON in json.dumps(pa.get(f"/sections/{sid}").json())
    _ecrire(pa, sid, f"Je continue {SECRET_BROUILLON}.")
    # Le partenaire rattache son lien depuis le navigateur où il rédige : ses brouillons suivent son compte.
    hp, _ep = _register(client, company="Breizh Désamiantage")
    r = client.post(f"/api/invite/{a['token']}/claim", headers={**hp, **pa.h})
    assert r.status_code == 200, r.text
    assert SECRET_BROUILLON in json.dumps(PC(client, pid, hp).get(f"/sections/{sid}").json())
    journal = _audit(project_id=pid, invite_id=a["id"], action="invite.claimed")
    assert len(journal) == 1 and "clé présentée" in journal[0][3]
    # Le chef de file ne lit toujours rien de ses brouillons.
    for url in (f"/api/atelier/{pid}/repartition/{sid}", f"/api/atelier/{pid}/sections/{sid}"):
        assert SECRET_BROUILLON not in client.get(url, headers=h).text


def test_rattacher_un_lien_dont_l_espace_n_est_pas_ouvert_reste_libre(client, auth):
    """Sans espace ouvert (rien n'a été écrit par le lien), le rattachement ne change pas : le compte suffit."""
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    hp, _ep = _register(client, company="Breizh Désamiantage")
    r = client.post(f"/api/invite/{a['token']}/claim", headers=hp)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/shared/{pid}/redaction", headers=hp).status_code == 200


def test_ecrans_rattachent_le_lien_avec_la_cle_de_l_espace():
    """Les deux pages qui rattachent un lien (page du lien, application) joignent la clé de l'espace gardée par le
    navigateur ; la page du lien met l'explication dans le bandeau, pas sur le bouton."""
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / "app" / "static"
    inv = (base / "invite.html").read_text(encoding="utf-8")
    app = (base / "app.js").read_text(encoding="utf-8")
    assert inv.count("headers: claimHeaders(") == 2 and '"adjugo_espace_" + TOKEN' in inv
    assert 'e.detail.code === "espace_a_prouver"' in inv
    assert app.count("/claim\", null, false, this._cleEspace(") == 2 and '"adjugo_espace_" + token' in app


# ═══ Cloisonnement : relire un fait du texte commun exige l'identité ═════════════════

def test_apres_reinitialisation_le_chef_ne_releve_pas_les_faits_du_texte_commun(client, auth, monkeypatch, fake_llm):
    """Lien qui vise une adresse : le partenaire (adresse prouvée par code) envoie sa partie avec des faits à relire.
    Le chef de file, qui détient le lien, réinitialise l'espace, recopie le texte commun dans un brouillon et tente
    de marquer chaque fait « relu » : refusé (identité), les faits restent à relire et l'export reste bloqué. Le
    partenaire, adresse prouvée, relit ensuite un fait : c'est inscrit au journal chaîné."""
    import app.routers.invites as invites
    monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    _set_inv(a["id"], recipient="desamiantage@partenaire.fr")
    base = f"/api/invite/{a['token']}/redaction"
    _code_en_attente(a["id"])
    r = client.post(base + "/espace", json={"code": "123456"})
    assert r.status_code == 200, r.text
    pa = P(client, a["token"], ouvrir=False)
    pa.h = {ag.ENTETE_CLE: r.json()["cle"]}
    fake_llm(_reponse_partenaire("Nous assurons 3 rotations de bennes par semaine et 2 contrôles "
                                 "d'empoussièrement par jour.")[0])
    assert _aide(pa, sid)[0]["status"] == "done"
    cur = pa.get(f"/sections/{sid}").json()
    r = pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": cur["brouillon"]["id"], "avertissement_lu": True})
    assert r.status_code == 200, r.text
    avant = _texte(client, h, pid, sid)["texte_commun"]["faits_a_relire"]
    assert avant > 0 and _bloque_par_faits(client, h, pid, sid)
    commun = client.get(f"/api/atelier/{pid}/sections/{sid}", headers=h).json()["version_courante"]["texte"]
    # Le chef de file, avec le lien seulement :
    r = client.post(base + "/espace", json={"reinitialiser": True})
    assert r.status_code == 200, r.text
    chef = P(client, a["token"], ouvrir=False)
    chef.h = {ag.ENTETE_CLE: r.json()["cle"]}
    r = chef.put(f"/sections/{sid}/brouillon", {"texte": commun, "base_brouillon_id": None})
    assert r.status_code == 200, r.text
    a_relire = [f for f in r.json()["brouillon"]["faits"] if f.get("statut") == far.A_RELIRE]
    assert a_relire
    for f in a_relire:
        rr = chef.post(f"/sections/{sid}/faits/{f['id']}", {"statut": far.RELU})
        assert rr.status_code == 403 and rr.json()["detail"]["code"] == "identity_unverified", rr.text
    assert _texte(client, h, pid, sid)["texte_commun"]["faits_a_relire"] == avant
    assert _bloque_par_faits(client, h, pid, sid)
    assert "redaction.fait_relu" not in [x[0] for x in _audit(project_id=pid, invite_id=a["id"])]
    # Le partenaire rouvre son espace avec le code reçu (adresse prouvée) et relit un fait : il vaut pour le texte
    # commun, et c'est au journal chaîné (attribué au partenaire, par le lien).
    _code_en_attente(a["id"])
    r = client.post(base + "/espace", json={"code": "123456"})
    assert r.status_code == 200, r.text
    pa.h = {ag.ENTETE_CLE: r.json()["cle"]}
    rr = pa.post(f"/sections/{sid}/faits/{a_relire[0]['id']}", {"statut": far.RELU})
    assert rr.status_code == 200, rr.text
    assert _texte(client, h, pid, sid)["texte_commun"]["faits_a_relire"] == avant - 1
    j = [x for x in _audit(project_id=pid, invite_id=a["id"]) if x[0] == "redaction.fait_relu"]
    assert len(j) == 1 and j[0][2] == "guest" and j[0][4]
    # Un fait d'un brouillon qui n'est PAS le texte commun reste une affaire privée : aucune identité, aucun journal.
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": commun + " Nous ajoutons 4 bennes étanches.",
                                               "base_brouillon_id": pa.get(f"/sections/{sid}").json()["brouillon"]["id"]})
    assert r.status_code == 200, r.text
    prive = next(f for f in r.json()["brouillon"]["faits"] if f.get("statut") == far.A_RELIRE)
    assert pa.post(f"/sections/{sid}/faits/{prive['id']}", {"statut": far.RELU}).status_code == 200
    assert len([x for x in _audit(project_id=pid, invite_id=a["id"]) if x[0] == "redaction.fait_relu"]) == 1


def test_ecran_relire_un_fait_passe_par_la_verification_d_identite():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "redaction-partenaire.js").read_text(
        encoding="utf-8")
    assert 'avecIdentite(() => call("POST", "/sections/" + sid + "/faits/"' in js


# ═══ Cloisonnement : export RGPD d'un membre retiré ═════════════════════════════════

def test_export_rgpd_du_membre_retire_sans_les_extraits_de_son_ancienne_organisation(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    ho, eo = _register(client, company="Breizh Désamiantage")
    client.get("/api/org/", headers=ho)
    r = client.post("/api/knowledge/text", headers=ho, json={
        "name": SECRET_DOC, "kind": "memoire",
        "text": f"Démarche environnementale : tri des déchets amiantés dans 4 bennes étanches {SECRET_EXTRAIT}."})
    assert r.status_code == 200, r.text
    hm, em = _register(client, company="Breizh Désamiantage")
    from app.models import User
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        m.org_id = db.query(User).filter(User.email == eo).first().org_id
        m.org_role = "membre"
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/invite/{a['token']}/claim", headers=hm).status_code == 200
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pc = PC(client, pid, hm)
    assert _aide(pc, sid)[0]["status"] == "done"
    # Témoin : membre de l'organisation, son export RGPD rend bien ses sources (portabilité).
    assert SECRET_EXTRAIT in client.get("/api/rgpd/export", headers=hm).text
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        m.org_id, m.org_role = None, None                                          # retiré de l'organisation
        db.commit()
    finally:
        db.close()
    rgpd = client.get("/api/rgpd/export", headers=hm)
    assert rgpd.status_code == 200
    assert SECRET_EXTRAIT not in rgpd.text and SECRET_DOC not in rgpd.text
    # Ses brouillons restent dans son export (seule la matière de son ancienne organisation en sort).
    parts = rgpd.json()["parts_redigees_pour_des_groupements"]
    assert len(parts) == 1 and parts[0]["brouillons"] and parts[0]["brouillons"][0]["texte"]


# ═══ Anti-invention : unités courtes et ordinaux (contrôle A) ═══════════════════════

def test_unites_courtes_et_ordinaux_ne_s_appuient_que_sur_le_meme_fait():
    """« 3e », « 30t », « 48h » : une clé à eux, jamais un mot quelconque qui commence par la même lettre près du
    même nombre ; ni un mot d'une autre phrase ou d'une autre source."""
    sources = ["Nous posons 30 tuiles par heure sur la toiture.", "La commune compte 48 habitants par hectare.",
               "Nous intervenons avec 3 équipes."]
    for phrase in ("Cette partie traite 30t de déchets.", "Le groupement intervient en 48h sur cette partie.",
                   "Cette partie présente la 3e intervention du groupement pour l'acheteur."):
        r = asm.controle_transition(phrase, sources)
        assert r["ok"] is False and r["faits"], (phrase, r)
    # Même nombre, unité dans une AUTRE phrase de la même source : pas le même fait.
    assert asm.controle_transition("Cette partie traite 30t de déchets.",
                                   ["Nous posons 30 tuiles. Nos tonnes de déchets sont triées."])["ok"] is False
    # Le même fait, écrit autrement, reste appuyé.
    src = far.Sources(["Nous traitons 30 tonnes de déchets.", "Nous intervenons sous 48 heures.",
                       "C'est notre troisième chantier pour cet acheteur.", "Nous sommes le premier désamianteur.",
                       "Notre équipe cumule 15 années d'expérience.", "Notre dépôt est à 15km.", "Pendant 12 mois."])
    for phrase in ("Nous traitons 30t de déchets.", "Nous traitons 30 t de déchets.", "Nous intervenons en 48h.",
                   "C'est notre 3e chantier.", "Nous sommes le 1er désamianteur.", "Nous avons 15 ans d'expérience.",
                   "Notre dépôt est à 15 km.", "Pendant 12 mois de travaux."):
        faits = [f for f in far._facts_in(phrase) if f[1] in (far.CHIFFRE, far.EN_LETTRES)]
        assert faits and all(src.has(k, key) for _f, k, key in faits), (phrase, faits)
    for phrase in ("Nous intervenons en 3 jours.", "Nous avons 12 moines.", "C'est notre 30e chantier."):
        faits = [f for f in far._facts_in(phrase) if f[1] in (far.CHIFFRE, far.EN_LETTRES)]
        assert faits and not all(src.has(k, key) for _f, k, key in faits), (phrase, faits)
    # Un cardinal n'appuie pas un ordinal (« 3 électriciens » ≠ « 3e chantier »), ni l'inverse.
    assert not far.Sources(["Nos 3 électriciens."]).has(far.CHIFFRE, (3.0, far.ORDINAL))
    assert not far.Sources(["Notre 3e chantier."]).has(far.CHIFFRE, (3.0, "elect"))
    assert far._unit_key("t") == far._unit_key("tonnes") == "tonne" and far._unit_key("e") == far.ORDINAL


def test_raccourci_ne_presente_pas_un_ordinal_de_l_ia_comme_declare_par_vous():
    """Mode « raccourci » (texte d'avant le contrôle A) : un « 3e » écrit par l'IA n'est pas « repris du texte de
    départ » parce que ce texte contient « 3 électriciens »."""
    fiches = fs.fiches_contexte("Entreprise : Breizh Désamiantage.", "", "", [])
    base = "Nos 3 électriciens interviennent en binôme sur chaque zone."
    faits = fs.controler("C'est notre 3e chantier de ce type.", fiches, mode="raccourci", base_texte=base,
                         section_entreprise=True, noms_entreprise=["Breizh Désamiantage"])
    f = next(x for x in faits if x["fait"] == "3e")
    assert f["statut"] == far.A_RELIRE, f
    # Le même ordinal dans le texte de départ : repris de ce texte.
    faits = fs.controler("C'est notre 3e chantier de ce type.", fiches, mode="raccourci",
                         base_texte="C'est notre troisième chantier de ce type, en site occupé.",
                         section_entreprise=True, noms_entreprise=["Breizh Désamiantage"])
    assert next(x for x in faits if x["fait"] == "3e")["statut"] != far.A_RELIRE


# ═══ Anti-invention : transitions (superlatifs, périodes, organisation) ═════════════

PIEGES_CONTRE_RELECTURE = [
    ("Le groupement est le seul désamianteur du département.", far.EN_LETTRES),
    ("Le groupement est l'unique entreprise à proposer cette méthode.", far.EN_LETTRES),
    ("Le groupement est le meilleur spécialiste de ce type de chantier.", far.EN_LETTRES),
    ("Le groupement est la référence du désamiantage dans le département.", far.EN_LETTRES),
    ("Le groupement retient la méthode la plus sûre pour cette partie.", far.EN_LETTRES),
    ("Cette partie se déroule pendant les vacances scolaires.", "date"),
    ("Cette partie sera livrée avant l'été.", "date"),
    ("Cette partie se déroule pendant la période estivale.", "date"),
    ("Le groupement intervient dès la signature du marché.", "date"),
    ("Le groupement réalise cette partie sans aucune sous-traitance.", "quantite"),
    ("Le groupement trie toujours ses déchets sur place.", "quantite"),
    ("Le groupement intervient en horaires décalés sur cette partie.", fs.ENGAGEMENT),
    ("Le groupement reste en astreinte pendant cette partie.", fs.ENGAGEMENT),
    ("Le groupement respecte les délais de cette partie.", fs.ENGAGEMENT),
]

BONNES_TRANSITIONS = [
    "Dans un second temps, cette partie décrit la méthodologie du groupement.",
    "En premier lieu, le groupement présente son organisation.",
    "Cette partie présente ensuite le premier volet de la méthodologie.",
    "Dans un premier temps, la première partie présente l'organisation du chantier.",
    "Cette partie présente ensuite la démarche environnementale du groupement.",
    "Après l'organisation du chantier, cette partie décrit la gestion des déchets.",
    "Le groupement s'appuie sur 9 salariés formés pour cette partie.",
    "Breizh Désamiantage décrit ensuite le tri des déchets.",
    "S'agissant de l'environnement, la suite précise la méthode retenue.",
    "Enfin, la dernière partie décrit la démarche environnementale.",
    "Cette partie a été rédigée par Breizh Désamiantage et décrit le tri des déchets.",
]


def test_transitions_refusent_superlatifs_periodes_et_organisation_du_travail():
    for phrase, genre in PIEGES_CONTRE_RELECTURE:
        r = asm.controle_transition(phrase, SOURCES_AVANT)
        assert r["ok"] is False, phrase
        assert genre in {f["type"] for f in r["faits"]}, (phrase, r["faits"])
    # Un rang reste un fait, même à côté d'une locution qui ne classe rien.
    for phrase in ("Le groupement est le premier désamianteur du département.",
                   "Dans un premier temps, le groupement, premier désamianteur du département, présente son "
                   "organisation."):
        assert asm.controle_transition(phrase, SOURCES_AVANT)["ok"] is False, phrase
    # … et ce qui est dans le dossier passe (un fait repris n'est pas un fait ajouté).
    assert asm.controle_transition("Le groupement est le seul désamianteur de l'opération.",
                                   SOURCES_AVANT + ["Nous sommes le seul désamianteur de l'opération."])["ok"] is True


def test_bonnes_transitions_passent_connecteurs_compris():
    """Les locutions qui ne classent rien (« dans un second temps », « en premier lieu », « le premier volet »)
    ne sont pas des rangs : l'IA n'est pas payée pour des phrases jetées."""
    for bonne in BONNES_TRANSITIONS:
        r = asm.controle_transition(bonne, SOURCES_AVANT)
        assert r["ok"] is True, (bonne, r)


def test_harmoniser_de_bout_en_bout_refuse_3e_seul_et_vacances(client, auth, fake_llm):
    """De bout en bout : B a envoyé « Nos 3 électriciens… » ; « la 3e intervention », « le seul désamianteur » et
    « les vacances scolaires » sont refusées, aucune partie ne les reçoit ; une bonne transition passe."""
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    _ecrire(pb, s["1.2"], "Nos 3 électriciens interviennent en binôme sur chaque zone.")
    _envoyer(pb, s["1.2"])
    fake_llm(_faux_harmoniseur(["Cette partie présente la 3e intervention du groupement pour l'acheteur.",
                                "Le groupement est le seul désamianteur du département.",
                                "Cette partie se déroule pendant les vacances scolaires."]))
    job, _ = _harmoniser(client, h, pid)
    assert job["status"] == "done", job
    assert job["result"]["ajoutees"] == 0 and job["result"]["refusees"] == 3, job["result"]
    st = _etat(client, h, pid)
    tout = json.dumps([_section_par(st, m)["version_courante"]["texte"]
                       for m in ("équipe d'exécution", "méthodologie", "environnement")], ensure_ascii=False)
    for piege in ("3e intervention", "seul désamianteur", "vacances"):
        assert piege not in tout, piege
    fake_llm(_faux_harmoniseur(["Dans un second temps, cette partie décrit l'équipe d'exécution.", "", ""]))
    job, _ = _harmoniser(client, h, pid)
    assert job["status"] == "done" and job["result"]["ajoutees"] == 1, job["result"]
