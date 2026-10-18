"""
Rédaction, vague 4 — corrections après les cinq relectures (cloisonnement, anti-invention, parcours et états,
coûts et RGPD, exactitude de l'interface). Chaque test reproduit un constat qui échouait avant la correction.

Contrat : docs/REDACTION_V4_GROUPEMENT.md (§ 3.1, § 13, § 19). Aucun appel réseau : le client IA est simulé.
"""
import json
import re
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import atelier_assemblage as asm
from app.services import atelier_groupement as ag
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from tests.test_convention_groupement import _gen, _put, _register, _submit
from tests.test_redaction_socle0 import _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _etat
from tests.test_redaction_v4_assemblage import (SOURCES_AVANT, _attendre_chef, _ecrire_chef, _faux_harmoniseur,
                                                _generee, _groupement_convention, _groupement_trois_jonctions,
                                                _harmoniser, _texte, _valider_chef, _valider_part, _valider_qfq,
                                                mails)  # noqa: F401
from tests.test_redaction_v4_groupement import (SECRET_BROUILLON, SECRET_DOC, SECRET_EXTRAIT, TEXTE_IA_A, P, PC,
                                                _aide, _attendre, _ecrire, _envoyer, _groupement, _part_a,
                                                _reponse_partenaire, _section_par, _vues_du_chef)

CV_BLOC = ("**Gwenaël Kerhervé**, encadrant technique amiante\n- Expérience : 15 ans\n- Diplômes : CAP DIPLOMESECRET83\n"
           "- Qualifications et habilitations : SS4 encadrement HABILSECRET29")


def _set_inv(iid, **champs):
    from app.models import ProjectInvite
    db = _db()
    try:
        inv = db.get(ProjectInvite, iid)
        for k, v in champs.items():
            setattr(inv, k, v)
        db.commit()
    finally:
        db.close()


def _code_en_attente(iid, code="123456"):
    import app.routers.invites as invites
    _set_inv(iid, otp_hash=invites._hash_otp(code), otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
             otp_attempts=0)


def _partenaire_par_compte(client, token, company="Breizh Désamiantage", cle=None, email=None):
    """Le partenaire rattache son lien à son compte. Quand l'espace du lien est ouvert (lien sans adresse), depuis le
    navigateur qui en a la clé (`cle` : les en-têtes de son espace)."""
    hp, ep = _register(client, company=company, email=email)
    r = client.post(f"/api/invite/{token}/claim", headers={**hp, **(cle or {})})
    assert r.status_code == 200, r.text
    return hp, ep


# ═══ Cloisonnement : l'espace privé du lien ══════════════════════════════════════════

def test_lien_rattache_a_un_compte_aucun_espace_par_le_lien(client, auth, fake_llm):
    """Le partenaire travaille par son compte (« Partagé avec moi ») : le chef de file, qui détient le lien,
    n'ouvre pas d'espace par ce lien et ne lit ni le brouillon de l'IA, ni ses brouillons, ni ses extraits."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    hp, _ep = _partenaire_par_compte(client, a["token"])
    r = client.post("/api/knowledge/text", headers=hp, json={
        "name": SECRET_DOC, "kind": "memoire",
        "text": f"Démarche environnementale : tri des déchets amiantés dans 4 bennes étanches {SECRET_EXTRAIT}."})
    assert r.status_code == 200, r.text
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pc = PC(client, pid, hp)
    assert _aide(pc, sid)[0]["status"] == "done"
    _ecrire(pc, sid, f"Brouillon privé {SECRET_BROUILLON}, jamais envoyé.")
    # Le chef de file tente d'ouvrir l'espace par le lien : refusé, rien n'est effacé.
    r = client.post(f"/api/invite/{a['token']}/redaction/espace", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "espace_par_le_compte", r.text
    r = client.post(f"/api/invite/{a['token']}/redaction/espace", json={"reinitialiser": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "espace_par_le_compte"
    assert len(pc.get(f"/sections/{sid}").json()["brouillons"]) == 2
    v = client.get(f"/api/invite/{a['token']}/redaction").json()
    assert v["espace"]["par_le_compte"] is True and v["espace"]["cle_valide"] is False
    tout = _vues_du_chef(client, h, pid, sid, token=a["token"])
    for secret in (SECRET_BROUILLON, SECRET_EXTRAIT, SECRET_DOC, "4 bennes étanches pour les déchets"):
        assert secret not in tout, secret


def test_cle_prise_avant_le_rattachement_ne_vaut_plus(client, auth, fake_llm):
    """Le chef de file ouvre l'espace du lien AVANT le partenaire ; le partenaire rattache ensuite le lien à son
    compte et y travaille : la clé du chef de file ne lit plus rien et n'agit plus."""
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    # Lien qui vise l'adresse du partenaire : son compte (adresse prouvée) le rattache sans la clé de l'espace.
    ep = f"desamiantage_{a['id']}@partenaire.fr"
    _set_inv(a["id"], recipient=ep)
    chef = P(client, a["token"])                       # première ouverture, par le chef de file
    hp, _ep = _partenaire_par_compte(client, a["token"], email=ep)
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pc = PC(client, pid, hp)
    assert _aide(pc, sid)[0]["status"] == "done"
    bid = pc.get(f"/sections/{sid}").json()["brouillon"]["id"]
    v = chef.get().json()
    assert v["espace"]["cle_valide"] is False and v["parties"][0]["brouillon"] is None
    assert chef.get(f"/sections/{sid}").json()["brouillons"] == []
    assert chef.get(f"/sections/{sid}/brouillons/{bid}").status_code == 403
    assert chef.get("/export").status_code == 403
    r = chef.post(f"/sections/{sid}/aide", {"action": "rediger"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    r = chef.put(f"/sections/{sid}/brouillon", {"texte": "x", "base_brouillon_id": bid})
    assert r.status_code == 403
    assert "4 bennes étanches" not in json.dumps(chef.get().json())


def test_lien_a_adresse_premiere_ouverture_exige_le_code(client, auth, fake_llm, monkeypatch):
    """Un lien qui vise une adresse : même la PREMIÈRE ouverture de l'espace exige le code envoyé à cette adresse.
    Le chef de file qui détient le lien n'ouvre rien, ne lance pas l'aide de l'IA, n'envoie ni ne valide."""
    import app.routers.invites as invites
    monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    _set_inv(a["id"], recipient="desamiantage@partenaire.fr", verified_at=datetime.now(timezone.utc))
    base = f"/api/invite/{a['token']}/redaction"
    r = client.post(base + "/espace", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "code_requis", r.text
    assert r.json()["detail"]["code_possible"] is True
    v = client.get(base).json()["espace"]
    assert v["ouvert"] is False and v["code_possible"] is True and v["cle_valide"] is False
    _code_en_attente(a["id"])
    assert client.post(base + "/espace", json={"code": "000000"}).json()["detail"]["code"] == "code_incorrect"
    r = client.post(base + "/espace", json={"code": "123456"})
    assert r.status_code == 200 and r.json()["cle"], r.text
    pa = P(client, a["token"], ouvrir=False)
    pa.h = {ag.ENTETE_CLE: r.json()["cle"]}
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    # Celui qui réinitialise (le chef de file, avec le lien) : l'adresse est à prouver de nouveau, et l'aide de
    # l'IA, l'envoi et la validation sont refusés en son nom.
    r = client.post(base + "/espace", json={"reinitialiser": True})
    assert r.status_code == 200
    chef = P(client, a["token"], ouvrir=False)
    chef.h = {ag.ENTETE_CLE: r.json()["cle"]}
    fake = fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    r = chef.post(f"/sections/{sid}/aide", {"action": "rediger"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified", r.text
    assert fake.calls == []
    b0 = _ecrire(chef, sid, "Texte écrit par celui qui a réinitialisé.")
    r = chef.post(f"/sections/{sid}/envoyer", {"brouillon_id": b0["brouillon"]["id"], "avertissement_lu": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified"
    from tests.test_redaction_v4_groupement import _audit
    actions = [x[0] for x in _audit(project_id=pid, invite_id=a["id"])]
    assert "redaction.espace_ouvert" in actions and "redaction.espace_reinitialise" in actions
    assert "redaction.part_envoyee" not in actions


# ═══ Cloisonnement : aucun CV ni nom de salarié envoyé à l'IA ════════════════════════

def test_raccourcir_par_le_lien_refuse_un_cv(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    long = " ".join(["Nous trions les déchets amiantés sur place et les évacuons en filière agréée."] * 12)
    _ecrire(pa, sid, CV_BLOC + "\n\n" + long)
    fake = fake_llm(_reponse_partenaire("Texte raccourci.")[0])
    r = pa.post(f"/sections/{sid}/aide", {"action": "raccourcir", "cible_mots": 40})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cv_dans_la_partie", r.text
    assert fake.calls == []
    assert pa.get().json()["parties"][0]["aide"]["utilisees"] == 0


def test_harmoniser_ne_transmet_jamais_le_cv_ni_les_salaries_d_un_partenaire(client, auth, fake_llm):
    """« Harmoniser le ton » : le CV écrit au début de la part envoyée d'un partenaire ne part pas à l'IA (le CV
    est repéré sur le texte tel qu'écrit, pas sur l'extrait aplati) ; les noms de l'équipe d'un partenaire qui a
    un compte sont masqués même si sa part de co-traitance n'est pas soumise."""
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    # B a un compte, une équipe dans son profil, et sa part de co-traitance n'est PAS soumise. Il rattache son lien
    # depuis le navigateur où il rédigeait (la clé de son espace).
    hp, ep = _partenaire_par_compte(client, b["token"], company="Le Gall Électricité", cle=pb.h)
    r = client.put("/api/company/", headers=hp, json={"name": "Le Gall Électricité", "team": [
        {"nom": "Gwendal Kerbrat", "fonction": "Chef d'équipe", "qualifications": "B2V", "references": ""}]})
    assert r.status_code == 200, r.text
    pcb = PC(client, pid, hp)
    _ecrire(pcb, s["1.2"], "Gwendal Kerbrat pilote nos électriciens, qui interviennent en binôme sur chaque zone.")
    _envoyer(pcb, s["1.2"])
    _ecrire(pa, s["3"], CV_BLOC + "\n\nNous trions les déchets amiantés sur place, avec 9 salariés formés.")
    _envoyer(pa, s["3"])
    fake = fake_llm(_faux_harmoniseur(["Cette partie présente ensuite l'équipe d'exécution.",
                                       "La méthodologie suit.", "Le groupement décrit enfin sa démarche."]))
    job, _jid = _harmoniser(client, h, pid)
    assert job["status"] == "done", job
    envoye = fake.sent()
    for secret in ("DIPLOMESECRET83", "HABILSECRET29", "Kerhervé", "Gwenaël", "Kerbrat", "Gwendal"):
        assert secret not in envoye, secret


# ═══ Anti-invention : contrôle des faits (A) et transitions ══════════════════════════

PIEGES_TRANSITIONS = [
    ("Le groupement intervient en 48h sur cette partie.", "chiffre"),
    ("Cette partie couvre 1200m² de toiture.", "chiffre"),
    ("Cette partie traite 30t de déchets.", "chiffre"),
    ("Le chantier se situe à 15km du dépôt du groupement.", "chiffre"),
    ("Cette partie porte sur 250ml de gouttières.", "chiffre"),
    ("Le groupement prévoit 3j de préparation pour cette partie.", "chiffre"),
    ("Le groupement cumule neuf ans d'expérience sur ce type de chantier.", "nombre_en_lettres"),
    ("Le groupement est le 1er désamianteur du département.", "chiffre"),
    ("Le groupement est le premier désamianteur du département.", "nombre_en_lettres"),
    ("Cette partie marque la 3e intervention du groupement pour l'acheteur.", "chiffre"),
    ("La totalité des déchets de cette partie est recyclée.", "quantite"),
    ("Cette partie mobilise un aspirateur à filtre absolu.", "materiel"),
    ("Le groupement démolit les cloisons avec un robot de démolition.", "materiel"),
    ("Cette partie commence dès la rentrée.", "date"),
    ("Cette partie sera livrée l'an prochain.", "date"),
    ("Les travaux de cette partie ont lieu la nuit.", "date"),
    ("Le groupement garantit l'absence de réserve à la réception de cette partie.", "engagement"),
    ("Cette partie bénéficie d'une garantie décennale.", "engagement"),
    ("Le groupement intervient en moins d'une heure sur cette partie.", "engagement"),
    ("Les déchets de cette partie sont évacués le jour même.", "date"),
]


def test_transitions_refusent_les_faits_colles_ordinaux_periodes_et_engagements():
    for phrase, genre in PIEGES_TRANSITIONS:
        r = asm.controle_transition(phrase, SOURCES_AVANT)
        assert r["ok"] is False, phrase
        assert genre in {f["type"] for f in r["faits"]}, (phrase, r["faits"])
    # Ce qui est déjà dans le dossier passe toujours (un fait repris n'est pas un fait ajouté).
    for bonne in ("Le groupement s'appuie sur 9 salariés formés pour cette partie.",
                  "Cette partie présente ensuite la démarche environnementale du groupement.",
                  "Enfin, la dernière partie décrit la démarche environnementale."):
        assert asm.controle_transition(bonne, SOURCES_AVANT)["ok"] is True, bonne


def test_controle_a_repere_les_nombres_colles_les_ordinaux_et_neuf():
    """Le repérage des faits (contrôle A), seul garde-fou de la part rédigée par l'IA d'un partenaire : un nombre
    collé à son unité, un ordinal et « neuf » devant un nom compté sont des faits à relire, comme avec un espace."""
    fiches = fs.fiches_contexte("Entreprise : Breizh Désamiantage.", "", "", [])
    for phrase, fait in (("Nous avons désamianté 1200m² de toiture.", "1200m²"),
                         ("Nous avons désamianté 1200 m² de toiture.", "1200 m²"),
                         ("Nous traitons 30t de déchets par an.", "30t"),
                         ("Notre dépôt est à 15km du chantier.", "15km"),
                         ("Nous intervenons sous 48h.", "48h"),
                         ("Notre équipe cumule neuf ans d'expérience.", "neuf"),
                         ("Nous sommes le 1er désamianteur du Finistère.", "1er"),
                         ("C'est notre 3e chantier pour cet acheteur.", "3e")):
        faits = fs.controler(phrase, fiches, mode="ia", noms_entreprise=["Breizh Désamiantage"],
                             section_entreprise=True)
        relus = [x["fait"] for x in faits if x.get("statut") == far.A_RELIRE]
        assert any(fait.lower() in x.lower() for x in relus), (phrase, faits)
    # « neuf » adjectif n'est pas un nombre ; un code (R486, A320) non plus.
    for phrase in ("Le bâtiment neuf de la commune.", "Une nacelle CACES R486."):
        faits = far._facts_in(phrase)
        assert not [f for f in faits if f[1] in (far.CHIFFRE, far.EN_LETTRES)], (phrase, faits)
    # Une source qui écrit le nombre collé appuie le même fait écrit avec un espace, et l'inverse.
    src = far.Sources(["Nous avons désamianté 1200m² de toiture."])
    k = next(f for f in far._facts_in("Toiture de 1200 m² désamiantée.") if f[1] == far.CHIFFRE)
    assert src.has(k[1], k[2])


def test_harmoniser_de_bout_en_bout_refuse_48h_1200m2_et_1er(client, auth, fake_llm):
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    fake_llm(_faux_harmoniseur(["Le groupement intervient en 48h sur cette partie.",
                                "Cette partie couvre 1200m² de toiture.",
                                "Le groupement est le 1er désamianteur du département."]))
    job, _ = _harmoniser(client, h, pid)
    assert job["status"] == "done", job
    assert job["result"]["ajoutees"] == 0 and job["result"]["refusees"] == 3, job["result"]
    assert "1200m²" not in _section_par(_etat(client, h, pid), "méthodologie")["version_courante"]["texte"]


def test_partir_du_texte_du_chef_garde_ses_faits_a_relire(client, auth):
    """« Partir du texte du chef de file » : les faits que le chef de file a ajoutés restent à relire chez le
    partenaire ; ils ne deviennent pas « déclarés par vous » sans qu'il les ait relus."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    cur = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()["texte_commun"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h, json={
        "texte": cur["texte"] + "\n\nNous mobilisons 4 nacelles articulées et 2 camions-grues.",
        "base_version_id": cur["version_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["texte_commun"]["faits_a_relire"] == 2
    # Comme l'écran : le texte commun chargé dans l'éditeur, une virgule changée, enregistré, envoyé.
    p = pa.get(f"/sections/{sid}").json()
    t = p["texte_commun"]["texte"].replace("Nous mobilisons 4", "Nous mobilisons, 4")
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": t, "base_brouillon_id": p["brouillon"]["id"],
                                              "base_version_id": p["texte_commun"]["version_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["brouillon"]["faits_a_relire"] == 2
    _envoyer(pa, sid)
    ligne = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert ligne["texte_commun"]["faits_a_relire"] == 2 and ligne["texte_commun"]["compteurs"]["a_relire"] == 2


def test_revalider_apres_harmonisation_garde_les_declarations_du_partenaire(client, auth, fake_llm):
    """Le partenaire revalide sa partie après une transition sans fait : ses propres déclarations (« déclaré par
    vous ») ne repassent pas « à relire »."""
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    _ecrire(pb, s["1.2"], "Nos 6 électriciens interviennent en binôme avec 2 nacelles.")
    _envoyer(pb, s["1.2"])
    _valider_part(pb, s["1.2"])
    assert _texte(client, h, pid, s["1.2"])["texte_commun"]["faits_a_relire"] == 0
    fake_llm(_faux_harmoniseur(["Cette partie présente ensuite l'équipe d'exécution.", None, None]))
    job, _ = _harmoniser(client, h, pid)
    assert job["status"] == "done" and job["result"]["ajoutees"] == 1, job
    assert _texte(client, h, pid, s["1.2"])["texte_commun"]["faits_a_relire"] == 0
    _valider_part(pb, s["1.2"])
    t = _texte(client, h, pid, s["1.2"])
    assert t["statut"] == "validee" and t["texte_commun"]["faits_a_relire"] == 0, t["texte_commun"]


# ═══ Parcours et états ═══════════════════════════════════════════════════════════════

def test_co_traitant_sans_partie_peut_valider_le_dossier(client, auth, mails):
    pid, a, b, vue, conv = _groupement_convention(client, auth, avec_b=True)
    pb = P(client, b["token"])
    v = pb.get().json()
    assert v["parties"] == []
    assert _valider_qfq(pb).status_code == 200
    v = pb.get().json()
    assert v["dossier"]["peut_valider"] is True, v["dossier"]
    r = pb.post("/dossier/valider", {"empreinte": v["dossier"]["empreinte"]})
    assert r.status_code == 200, r.text


def test_envoyer_refuse_quand_le_chef_a_modifie_entre_temps(client, auth):
    """Le partenaire a ouvert son écran sur son texte envoyé ; le chef de file modifie la partie ; le partenaire
    enregistre puis envoie depuis son écran : refusé (« modifié entre-temps »), rien n'est remplacé en silence."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    vu = pa.get(f"/sections/{sid}").json()                     # l'écran du partenaire
    v1 = vu["texte_commun"]["version_id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h, json={
        "texte": "Nous trions les déchets amiantés sur place. MODIF_CHEF.", "base_version_id": v1})
    assert r.status_code == 200
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": "Nous trions et évacuons les déchets amiantés.",
                                              "base_brouillon_id": vu["brouillon"]["id"], "base_version_id": v1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "texte_modifie_entre_temps", r.text
    # Un brouillon écrit avant la modification du chef de file ne l'écrase pas non plus.
    r = pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": vu["brouillon"]["id"], "avertissement_lu": True,
                                             "base_version_id": v1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "texte_modifie_entre_temps"
    # Après avoir vu l'avant et l'après, il peut écrire sa version et l'envoyer.
    v2 = pa.get(f"/sections/{sid}").json()["texte_commun"]["version_id"]
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": "Nous trions et évacuons les déchets amiantés.",
                                              "base_brouillon_id": vu["brouillon"]["id"], "base_version_id": v2})
    assert r.status_code == 200, r.text
    r = pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": r.json()["brouillon"]["id"], "avertissement_lu": True,
                                             "base_version_id": v2})
    assert r.status_code == 200, r.text
    ligne = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert ligne["statut"] == "envoyee"


def test_envoyer_pendant_la_reprise_par_le_chef_ne_touche_pas_sa_partie(client, auth, monkeypatch):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    br = _ecrire(pa, sid, "TEXTE_DU_PARTENAIRE : tri des déchets amiantés.")["brouillon"]
    orig = ag._verrouiller_rep
    fait = []

    def course(db, rep):
        if not fait:
            fait.append(1)
            r = client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h,
                           json={"redacteur": "chef_de_file", "confirmer": True})
            assert r.status_code == 200, r.text
        return orig(db, rep)
    monkeypatch.setattr(ag, "_verrouiller_rep", course)
    r = pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": br["id"], "avertissement_lu": True})
    assert r.status_code == 404, r.text
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)
    assert s["auteur"]["type"] == "organisation" and s["version_courante"] is None


def test_organisation_a_revalider_tant_que_la_nouvelle_convention_attend_des_accords(client, auth, mails):
    h = auth["headers"]
    pid, a, b, vue, conv = _groupement_convention(client, auth)
    orga = _generee(_etat(client, h, pid), "grp_orga")
    assert _valider_chef(client, h, pid, orga["id"]).status_code == 200
    assert client.get(f"/api/atelier/{pid}/repartition/{orga['id']}", headers=h).json()["statut"] == "validee"
    # A change son prix : la convention est périmée ; il resoumet, le chef de file régénère (accords en attente).
    assert _put(client, a["token"], prix_lot_ht=41000.0).status_code == 200
    _submit(client, a["token"])
    assert _gen(client, h, pid).status_code == 200
    d = client.get(f"/api/atelier/{pid}/repartition/{orga['id']}", headers=h).json()
    assert d["statut"] == "a_revalider", d["statut"]
    pret = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()["dossier"]["pret"]
    assert any(m["section_id"] == orga["id"] for m in pret["manques"])


def test_partie_envoyee_comptee_a_valider_dans_partage_avec_moi(client, auth):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    hp, _ep = _partenaire_par_compte(client, a["token"])
    pc = PC(client, pid, hp)
    _ecrire(pc, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pc, sid)
    item = next(x for x in client.get("/api/shared", headers=hp).json() if x.get("project_id") == pid)
    assert item["redaction"]["a_valider"] == 1, item["redaction"]


def test_partie_confiee_a_un_autre_partenaire_demande_relance_et_aides_remises_a_zero(client, auth, fake_llm,
                                                                                       monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth)
    _set_inv(a["id"], recipient="a@partenaire.fr")
    _set_inv(b["id"], recipient="b@partenaire.fr")
    sid = _part_a(vue)["section_id"]
    lim = date.today() + timedelta(days=2)
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"date_limite": lim.isoformat()})
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()["demandees"]
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pa = P(client, a["token"])
    for _ in range(ag.plafond_partie()):
        assert _aide(pa, sid)[0]["status"] == "done"
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h,
                   json={"redacteur": "partenaire", "invite_id": b["id"], "confirmer": True})
    assert r.status_code == 200, r.text
    assert r.json()["demandee_le"] is None
    r = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={})
    assert [x["nom"] for x in r.json()["demandees"]] == ["Le Gall Électricité"], r.json()
    assert any(to == "b@partenaire.fr" for to, _s, _t in sent)
    pb = P(client, b["token"])
    aide = pb.get().json()["parties"][0]["aide"]
    assert aide["utilisees"] == 0 and aide["restantes"] == ag.plafond_partie()


def test_relance_des_parties_sans_doublon_avec_la_co_traitance(client, auth, monkeypatch):
    """Une même tournée de relances n'envoie qu'UN email au partenaire (les parties sont ajoutées au rappel de
    sa part) ; « Demander les parts » compte comme la relance du palier en cours."""
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    import app.services.alerts as alerts
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _set_inv(a["id"], recipient="desamiantage@partenaire.fr")
    from app.models import Project
    db = _db()
    try:
        db.get(Project, pid).deadline = datetime.now(timezone.utc) + timedelta(days=1)
        db.commit()
    finally:
        db.close()
    sid = _part_a(vue)["section_id"]
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"date_limite": date.today().isoformat()})
    db = _db()
    try:
        res = alerts.run_cotraitance_reminders(db)
    finally:
        db.close()
    vers_a = [(s, t) for to, s, t in sent if to == "desamiantage@partenaire.fr"]
    assert len(vers_a) == 1, [s for s, _t in vers_a]
    assert "Démarche environnementale" in vers_a[0][1] and res["parts_fusionnees"] >= 1
    # Rejouer : rien de plus.
    db = _db()
    try:
        alerts.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert len([1 for to, _s, _t in sent if to == "desamiantage@partenaire.fr"]) == 1


def test_relance_des_parties_pas_juste_apres_la_demande(client, auth, monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _set_inv(a["id"], recipient="desamiantage@partenaire.fr")
    sid = _part_a(vue)["section_id"]
    lim = date.today() + timedelta(days=2)
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"date_limite": lim.isoformat()})
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).status_code == 200
    vers_a = lambda: [s for to, s, _t in sent if to == "desamiantage@partenaire.fr"]  # noqa: E731
    assert len(vers_a()) == 1
    db = _db()
    try:
        ag.relancer_parts(db, date.today())          # la demande vaut la relance de J-2 : rien de plus
        assert len(vers_a()) == 1
        ag.relancer_parts(db, lim)                   # le jour J : la relance part
    finally:
        db.close()
    assert len(vers_a()) == 2 and "Rappel" in vers_a()[1]


# ═══ Coûts et RGPD ═══════════════════════════════════════════════════════════════════

def test_membre_retire_ne_lit_plus_les_extraits_de_son_ancienne_organisation(client, auth, fake_llm):
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
    assert SECRET_EXTRAIT in json.dumps(pc.get(f"/sections/{sid}").json())       # témoin : membre de l'organisation
    db = _db()
    try:
        m = db.query(User).filter(User.email == em).first()
        m.org_id, m.org_role = None, None                                          # retiré de l'organisation
        db.commit()
    finally:
        db.close()
    raw = json.dumps(pc.get(f"/sections/{sid}").json()) + json.dumps(pc.get().json()) + pc.get("/export").text
    assert SECRET_EXTRAIT not in raw and SECRET_DOC not in raw


def test_harmonisation_parties_changees_tache_lisible_et_rien_decompte(client, auth, fake_llm, monkeypatch):
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    import app.services.jobs as jobs
    orig = jobs.run_in_thread

    def apres_changement(jid, fn, **kw):
        _ecrire(pb, s["1.2"], "Nos électriciens interviennent en binôme, zone par zone.")
        _envoyer(pb, s["1.2"])
        _ecrire_chef(client, h, pid, s["2"], "Nous intervenons par zones, en site occupé, avec un planning.",
                     valider=True)
        _ecrire(pa, s["3"], "Nous trions les déchets amiantés sur place.")
        _envoyer(pa, s["3"])
        return orig(jid, fn, **kw)
    monkeypatch.setattr(jobs, "run_in_thread", apres_changement)
    fake_llm(_faux_harmoniseur(["Une.", "Deux.", "Trois."]))
    r = client.post(f"/api/atelier/{pid}/repartition/harmoniser", headers=h, json={})
    assert r.status_code == 202, r.text
    job = _attendre_chef(client, h, pid, r.json()["tache"]["id"])
    assert job["status"] == "done" and "rien n'est décompté" in job["result"]["message"], job
    assert _etat(client, h, pid)["quota"]["regenerations_utilisees"] == 0


def test_estimation_de_l_harmonisation_tiree_de_ses_plafonds(client, auth, fake_llm, monkeypatch):
    from app.services import budget_ia
    assert budget_ia.estimer("harmoniser") >= budget_ia.estimer_appel("raccourcir", asm.JONCTIONS_MAX * 2 * asm.EXTRAIT,
                                                                      4000)
    vus = []
    orig = budget_ia.verifier
    monkeypatch.setattr(budget_ia, "verifier", lambda user, db, op, est: vus.append(est) or orig(user, db, op, est))
    h = auth["headers"]
    pid, a, b, pa, pb, s = _groupement_trois_jonctions(client, auth)
    fake_llm(_faux_harmoniseur(["Cette partie présente ensuite l'équipe d'exécution.", None, None]))
    _harmoniser(client, h, pid)
    assert vus and vus[-1] == budget_ia.estimer("harmoniser")


# ═══ Exactitude de l'interface ═══════════════════════════════════════════════════════

def test_atelier_partie_tiree_du_groupement_porte_son_statut_et_la_validation_du_chef(client, auth, mails):
    h = auth["headers"]
    pid, a, b, vue, conv = _groupement_convention(client, auth)
    qfq = _generee(_etat(client, h, pid), "grp_qfq")
    assert qfq["part"]["statut"] == "a_valider" and qfq["part"]["statut_libelle"] == "À valider"
    assert qfq["part"]["a_valider_par_vous"] is True
    assert _valider_chef(client, h, pid, qfq["id"]).status_code == 200
    qfq = _generee(_etat(client, h, pid), "grp_qfq")
    assert qfq["part"]["statut"] == "a_valider" and qfq["part"]["a_valider_par_vous"] is False
    assert qfq["part"]["mention"] == "Validée par vous ; à valider par Breizh Désamiantage"
    orga = _generee(_etat(client, h, pid), "grp_orga")
    assert orga["part"]["statut"] == "a_valider" and orga["part"]["a_valider_par_vous"] is True


APP = None


def _read(nom):
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / nom).read_text(encoding="utf-8")


def test_partage_avec_moi_avertit_avant_de_soumettre_la_part():
    html = _read("app.html")
    i = html.index('@click="sharedSubmit()"')
    zone = html[i:i + 1500]
    assert "repris dans la partie « Qui fait quoi dans le groupement » du dossier de présentation" in zone
    assert "sous_traitant" in zone


def test_atelier_origine_d_une_partie_tiree_du_groupement():
    js = _read("app.js")
    m = re.search(r"atlOrigine\(s\) \{(.*?)\n    \},", js, re.S)
    assert m and "s.genere" in m.group(1) and "origine_libelle" in m.group(1)
    html = _read("app.html")
    assert "Écrite par Adjugo sans IA : aucune source ni extrait." in html
    # L'en-tête « 1 validée sur 6 · 2 à valider · 3 à écrire » compte chaque partie de groupement selon sa pastille.
    m = re.search(r"atlCompte\(d\) \{(.*?)\n    \},", js, re.S)
    assert m and "s.part ? (grp[s.part.statut]" in m.group(1) and 'envoyee: "a_valider"' in m.group(1)
    assert 'a_valider: ["à valider", "à valider"]' in js
    # Le bouton « Valider » d'une partie tirée du groupement suit ce qu'elle attend du chef de file.
    assert "atlSec().part ? atlSec().part.a_valider_par_vous" in html


# ── L'écran du partenaire, rendu sous Node (faux DOM minimal) ─────────────────────────

def _rendu(vue, extra=""):
    """Monte l'écran du partenaire sur une vue de l'API (fausse) et rend le HTML produit ; `icones` : les
    options passées à lucide.createIcons."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    js = _read("redaction-partenaire.js")
    prog = r"""
const icones = [];
const el = { innerHTML: "", _h: [], querySelectorAll: () => [], querySelector: () => null, contains: () => false,
             addEventListener: () => {}, removeEventListener: () => {} };
globalThis.document = { activeElement: null, body: { appendChild() {} }, createElement: () => ({ style: {} }) };
globalThis.localStorage = { getItem: () => "cle", setItem() {} };
globalThis.sessionStorage = { getItem: () => null, setItem() {} };
globalThis.setInterval = () => 1; globalThis.clearInterval = () => {};
const VUE = __VUE__;
globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => VUE });
const window = { lucide: { createIcons: (o) => icones.push(o === undefined ? null : Object.keys(o)) } };
""".replace("__VUE__", json.dumps(vue)) + js + r"""
const h = window.AdjugoRedactionPartenaire.mount(el, { base: "/x", mode: "compte" });
setTimeout(() => { """ + extra + r""" console.log(JSON.stringify({ html: el.innerHTML, icones })); }, 50);
"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _vue_partenaire(parties, peut_valider=False, qfq=None):
    return {"marche": {"id": 1, "nom": "M"}, "mode": "compte",
            "espace": {"cle_valide": True, "ouvert": True, "code_possible": False, "message": ""},
            "message_mode": "", "avertissement_envoi": "Ce texte sera lu…", "peut_ecrire": True,
            "membre": {"nom": "Breizh Désamiantage", "lot": "x"}, "identite": {"a_prouver": False, "message": ""},
            "mode_simple": {"petit_texte": "", "message": ""}, "parties": parties, "statuts": {}, "origines": {},
            "qui_fait_quoi": qfq,
            "dossier": {"empreinte": "e", "ma_validation": None, "peut_valider": peut_valider,
                        "pret": {"sections_total": 1, "message": "Sections validées 0 sur 1"}}}


def _partie(statut, ecrit_par="partenaire", libelle="À revalider"):
    tc = {"version_id": 9, "numero": 2, "ecrit_par": ecrit_par, "empreinte": "e2", "cree_le": "2026-10-18T10:00:00",
          "a_completer": 0, "texte": "Nous trions."}
    return {"section_id": 5, "titre": "3 Démarche environnementale", "intitule": "Démarche environnementale",
            "statut": statut, "statut_libelle": libelle, "mention": "", "note": {}, "limite": [],
            "brouillon": {"id": 3, "numero": 2, "origine": "utilisateur", "empreinte": "e2", "base_version_id": 9,
                          "faits": [], "texte": "Nous trions.", "controle": {}, "compteurs": {}},
            "texte_commun": tc, "comparaison": None, "validation": {"version_id": 7, "le": "2026-10-17T10:00:00"},
            "aide": {"utilisees": 0, "plafond": 3, "restantes": 3, "en_cours": None}}


def test_ecran_valider_une_nouvelle_version_ecrite_par_le_partenaire():
    r = _rendu(_vue_partenaire([_partie("a_revalider")]), extra="")
    assert 'data-act="valider"' in r["html"] and "Valider cette nouvelle version" in r["html"]


def test_ecran_partie_envoyee_comptee_a_faire_et_dossier_sans_partie():
    r = _rendu(_vue_partenaire([_partie("envoyee", libelle="Envoyée")]))
    assert "1 à faire" in r["html"] and "À jour" not in r["html"]
    q = {"section_id": 2, "intitule": "Qui fait quoi dans le groupement", "texte_commun": {"version_id": 1},
         "ma_validation": {"statut": "a_faire"}, "membres": []}
    r = _rendu(_vue_partenaire([], qfq=q))
    assert "Validez d'abord « Qui fait quoi dans le groupement », puis lisez le dossier assemblé." in r["html"]
    assert "chacune de vos parties" not in r["html"]


def test_ecran_icones_seulement_dans_l_ecran_du_partenaire():
    r = _rendu(_vue_partenaire([_partie("envoyee", libelle="Envoyée")]))
    assert r["icones"] and all(o is not None and "root" in o for o in r["icones"]), r["icones"]
    js = _read("redaction-partenaire.js")
    assert "createIcons()" not in js


def test_ecran_compteurs_au_singulier():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    prog = ("const window = {};\n" + _read("redaction-partenaire.js")
            + "\nconsole.log(JSON.stringify(window.AdjugoRedactionPartenaire._pur.rpCompteurs("
              "{par_type: {documents: 1, declare: 1, estimation: 1, public: 2}})));")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["1 trouvé dans vos documents", "1 déclaré par vous", "2 de source publique",
                                      "1 tiré de votre estimation"]
