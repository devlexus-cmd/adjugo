"""
Rédaction, vague 4 — le dossier de groupement cloisonné (étude § 6.8 B), SOCLE côté serveur.

Contrat : docs/REDACTION_V4_GROUPEMENT.md. Invariants vérifiés :
 • « Qui écrit quoi » : une ligne par partie, rédacteur pré-rempli SANS IA (lot ↔ critère), longueur
   conseillée, date limite interne, statut CALCULÉ (à rédiger, en cours, envoyée, à revalider, validée),
   « rédigé par le chef de file, à valider par X » ;
 • portée partenaire : un partenaire (lien + clé de son espace privé, ou compte rattaché) ne voit et n'écrit
   que SES parties et lit le dossier assemblé ; son brouillon, ses sources et ses extraits ne sont JAMAIS vus
   du chef de file (texte envoyé + compteurs de sources par type seulement), même s'il détient le lien ;
   aucune lecture croisée ;
 • tâches : celle d'un partenaire n'a aucun compte propriétaire ; 404 sur /api/jobs/{id} pour le chef de
   file ET pour un membre de son organisation ; lue seulement avec l'accès du partenaire ;
 • facturation : quota du chef de file, portée technique « inv:<id> », plafond par partie, message neutre
   (rien du forfait du chef de file), remboursement si l'IA tombe ; le chef de file ne lance jamais l'aide
   à la place du partenaire ;
 • empreintes : modification par le chef de file → « à revalider par » l'auteur (avant / après), validation
   ou rétablissement ; dossier assemblé validé puis modifié → « à revalider » ; journal chaîné ;
 • isolation entre deux groupements ; invitation retirée, déclinée ou expirée : accès coupé ;
 • RGPD : export (chef de file sans brouillon de partenaire ; partenaire avec ses brouillons),
   effacement du compte (chef de file, partenaire), retrait d'une invitation ;
 • export du chef de file bloqué par les « [À compléter] » et les faits à relire d'une part envoyée ;
 • migration x8y9redactionv4 (SQLite : base neuve, base à la révision précédente, rejeu, retour arrière).
Aucun appel réseau : le client IA est simulé.
"""
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone

from app.services import atelier_groupement as ag
from app.services import llm
from tests.test_convention_groupement import _invite, _put, _register
from tests.test_redaction_socle0 import _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _creer, _etat, _projet

SECRET_EXTRAIT = "SECRETEXTRAIT42"
SECRET_DOC = "Dossier-interne-partenaire-confidentiel"
SECRET_BROUILLON = "BROUILLONPRIVE77"
SECRET_CHEF = "CHEFSAVOIRFAIRE91"

LOT_A = "Désamiantage et gestion des déchets amiantés"
LOT_B = "Électricité courants forts"
TEXTE_IA_A = ("Nous mobilisons 4 bennes étanches pour les déchets amiantés [S1]. Notre équipe compte 9 salariés "
              "[P4]. Nous assurons 3 rotations de bennes par semaine. [À compléter : planning des rotations]")


# ── Le partenaire : par son lien (et la clé de son espace), ou par son compte ──────────

class P:
    """Le partenaire par son LIEN : la clé de son espace privé est jointe à chaque requête."""

    def __init__(self, client, token, ouvrir=True):
        self.c, self.token = client, token
        self.base = f"/api/invite/{token}/redaction"
        self.h = {}
        if ouvrir:
            r = client.post(f"{self.base}/espace", json={})
            assert r.status_code == 200, r.text
            self.h = {ag.ENTETE_CLE: r.json()["cle"]}

    def get(self, chemin=""):
        return self.c.get(self.base + chemin, headers=self.h)

    def put(self, chemin, body):
        return self.c.put(self.base + chemin, json=body, headers=self.h)

    def post(self, chemin, body=None):
        return self.c.post(self.base + chemin, json=body if body is not None else {}, headers=self.h)


class PC(P):
    """Le partenaire par le COMPTE Adjugo qui a rattaché son lien (aucune clé : le compte suffit)."""

    def __init__(self, client, project_id, headers):
        self.c, self.token = client, None
        self.base = f"/api/shared/{project_id}/redaction"
        self.h = dict(headers)


def _section_par(st_or_list, mot):
    items = st_or_list["sections"] if isinstance(st_or_list, dict) and "sections" in st_or_list else st_or_list
    return next(s for s in items if mot.lower() in (s.get("intitule") or s.get("titre") or "").lower())


def _groupement(client, auth, *, avec_b=True):
    """Chef de file (Breizh Couverture) + marché avec dossier de l'acheteur + atelier construit sur le cadre +
    partenaire A (lot désamiantage, sans adresse : aucun code à prouver) et partenaire B (électricité)."""
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    a = _invite(client, h, pid, "Breizh Désamiantage")
    r = _put(client, a["token"], company_name="Breizh Désamiantage", lot=LOT_A, qualifications=["Qualibat 1552"],
             references=[{"intitule": "Désamiantage du collège Brizeux", "client": "Département du Finistère",
                          "montant": 85000, "annee": 2024}], capacites={"ca_n1": 900000, "effectif": 9})
    assert r.status_code == 200, r.text
    b = None
    if avec_b:
        b = _invite(client, h, pid, "Le Gall Électricité")
        assert _put(client, b["token"], company_name="Le Gall Électricité", lot=LOT_B).status_code == 200
    r = client.post(f"/api/atelier/{pid}/repartition", headers=h, json={})
    assert r.status_code == 200, r.text
    return pid, st, a, b, r.json()


def _part_a(vue):
    return _section_par(vue, "environnement")


def _attendre(p, jid):
    r = None
    for _ in range(300):
        r = p.get(f"/taches/{jid}")
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("done", "error"):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"tâche {jid} jamais terminée : {r.json() if r is not None else None}")


def _aide(p, sid, **body):
    r = p.post(f"/sections/{sid}/aide", body)
    assert r.status_code == 202, r.text
    return _attendre(p, r.json()["tache"]["id"]), r.json()["tache"]["id"]


def _ecrire(p, sid, texte):
    cur = p.get(f"/sections/{sid}").json()
    bid = (cur.get("brouillon") or {}).get("id")
    r = p.put(f"/sections/{sid}/brouillon", {"texte": texte, "base_brouillon_id": bid})
    assert r.status_code == 200, r.text
    return r.json()


def _envoyer(p, sid):
    cur = p.get(f"/sections/{sid}").json()
    r = p.post(f"/sections/{sid}/envoyer", {"brouillon_id": cur["brouillon"]["id"], "avertissement_lu": True})
    assert r.status_code == 200, r.text
    return r.json()


def _reponse_partenaire(texte):
    """Faux fournisseur IA : rend `texte` ; note chaque appel et sa portée de facturation."""
    vus = []

    def ans(kw):
        vus.append(llm._CURRENT_TENANT.get())
        return texte, "end_turn"
    return ans, vus


def _audit(**flt):
    from app.models import AuditLog
    db = _db()
    try:
        q = db.query(AuditLog)
        for k, v in flt.items():
            q = q.filter(getattr(AuditLog, k) == v)
        return [(r.action, r.invite_id, r.actor_kind, r.detail, r.entry_hash) for r in q.order_by(AuditLog.id).all()]
    finally:
        db.close()


def _brouillons_de(invite_id):
    from app.models import DossierPartBrouillon
    db = _db()
    try:
        return db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == invite_id).count()
    finally:
        db.close()


def _vues_du_chef(client, h, pid, sid, token=None):
    """Tout ce que le chef de file peut lire du dossier (JSON concaténé), y compris — s'il détient le lien
    du partenaire — ce que ce lien rend SANS la clé de l'espace privé."""
    out = [client.get(f"/api/atelier/{pid}", headers=h).text,
           client.get(f"/api/atelier/{pid}/repartition", headers=h).text,
           client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).text,
           client.get(f"/api/atelier/{pid}/sections/{sid}", headers=h).text,
           client.get(f"/api/projects/{pid}/audit", headers=h).text,
           client.get("/api/rgpd/export", headers=h).text]
    st = client.get(f"/api/atelier/{pid}/sections/{sid}", headers=h).json()
    for v in st.get("versions") or []:
        out.append(client.get(f"/api/atelier/{pid}/sections/{sid}/versions/{v['id']}", headers=h).text)
    cv = (st.get("version_courante") or {}).get("id")
    if cv:
        out.append(client.get(f"/api/atelier/{pid}/sections/{sid}/versions/{cv}", headers=h).text)
    if token:
        base = f"/api/invite/{token}/redaction"
        for chemin in ("", "/dossier", f"/sections/{sid}", "/export"):
            out.append(client.get(base + chemin).text)
    return "\n".join(out)


# ═══ 1. « Qui écrit quoi » : pré-remplissage sans IA ═════════════════════════════════

def test_preremplissage_sans_ia_lot_et_critere(client, auth, fake_llm):
    fake = fake_llm(lambda kw: (_ for _ in ()).throw(AssertionError("aucune IA pour répartir")))
    pid, st, a, b, vue = _groupement(client, auth)
    assert vue["actif"] is True and fake.calls == []
    env = _section_par(vue, "environnement")
    assert env["redacteur"]["type"] == "partenaire" and env["redacteur"]["invite_id"] == a["id"]
    assert env["redacteur"]["nom"] == "Breizh Désamiantage"
    assert "lot de Breizh Désamiantage" in env["proposition"]["message"] and "déchets" in env["proposition"]["message"]
    for mot in ("encadrement", "équipe", "méthodologie"):
        s = _section_par(vue, mot)
        assert s["redacteur"]["type"] == "chef_de_file" and "aucun lot" in s["proposition"]["message"]
    assert env["statut"] == "a_rediger" and env["statut_libelle"] == "À rédiger"
    # La partie suit le rédacteur : l'atelier du chef de file la montre comme celle d'un partenaire.
    st = _etat(client, auth["headers"], pid)
    s = next(x for x in st["sections"] if x["id"] == env["section_id"])
    assert s["auteur"]["type"] == "invitation" and s["auteur"]["libelle"] == "Breizh Désamiantage"
    assert s["peut_ecrire"] is False
    assert {m["nom"]: m["peut_rediger"] for m in vue["membres"]} == {"Breizh Désamiantage": True,
                                                                     "Le Gall Électricité": True}
    # Rejouer la préparation ne change rien (idempotent) ; journal.
    r = client.post(f"/api/atelier/{pid}/repartition", headers=auth["headers"], json={})
    assert r.json()["preparation"]["crees"] == 0
    actions = [x[0] for x in _audit(project_id=pid)]
    assert "redaction.repartition" in actions and "redaction.partie_confiee" in actions


def test_repartir_redacteur_longueur_date_et_garde_fous(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    met = _section_par(vue, "méthodologie")
    url = f"/api/atelier/{pid}/repartition/{met['section_id']}"
    r = client.put(url, headers=h, json={"redacteur": "partenaire", "invite_id": b["id"], "longueur_mots": 400,
                                         "date_limite": (date.today() + timedelta(days=5)).isoformat()})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["redacteur"]["invite_id"] == b["id"] and d["longueur_mots"] == 400 and d["choix"] == "manuel"
    assert d["date_limite"] == (date.today() + timedelta(days=5)).isoformat()
    assert client.put(url, headers=h, json={"longueur_mots": 5}).json()["detail"]["code"] == "longueur_invalide"
    assert client.put(url, headers=h, json={"redacteur": "partenaire", "invite_id": 999999}).status_code == 404
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Sous-traitant Peinture",
                                                                     "role": "sous_traitant"})
    st_inv = r.json()
    r = client.put(url, headers=h, json={"redacteur": "partenaire", "invite_id": st_inv["id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "partenaire_indisponible"
    # Un sous-traitant n'a pas d'accès au dossier commun (même réponse qu'un dossier inexistant).
    assert client.get(f"/api/invite/{st_inv['token']}/redaction").status_code == 404
    # La partie du chef de file qui a déjà du texte ne change de mains que sur confirmation.
    enc = _section_par(vue, "encadrement")
    assert client.put(f"/api/atelier/{pid}/sections/{enc['section_id']}/texte", headers=h,
                      json={"texte": f"Brouillon du chef {SECRET_CHEF}.", "base_version_id": None}).status_code == 200
    url2 = f"/api/atelier/{pid}/repartition/{enc['section_id']}"
    r = client.put(url2, headers=h, json={"redacteur": "partenaire", "invite_id": a["id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "changement_a_confirmer"
    r = client.put(url2, headers=h, json={"redacteur": "partenaire", "invite_id": a["id"], "confirmer": True})
    assert r.status_code == 200, r.text
    # Le brouillon privé du chef de file n'arrive jamais chez le partenaire.
    pa = P(client, a["token"])
    raw = pa.get().text + pa.get("/dossier").text
    assert SECRET_CHEF not in raw
    p = _section_par(pa.get().json()["parties"], "encadrement")
    assert p["texte_commun"] is None and p["brouillon"] is None and p["statut"] == "a_rediger"


# ═══ 2. Portée partenaire : SES parties, le dossier assemblé en lecture ═════════════

def test_partenaire_ne_voit_et_n_ecrit_que_ses_parties(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa, pb = P(client, a["token"]), P(client, b["token"])
    va = pa.get().json()
    assert [p["intitule"] for p in va["parties"]] == ["Démarche environnementale"]
    p = va["parties"][0]
    assert p["question"] and p["aide"]["plafond"] == ag.plafond_partie() and p["brouillon"] is None
    assert va["avertissement_envoi"] == ag.AVERTISSEMENT_ENVOI and va["espace"]["cle_valide"] is True
    enc = _section_par(vue, "encadrement")
    assert pa.get(f"/sections/{enc['section_id']}").status_code == 404
    assert pa.put(f"/sections/{enc['section_id']}/brouillon", {"texte": "x", "base_brouillon_id": None}).status_code == 404
    assert pb.get().json()["parties"] == []
    assert pb.put(f"/sections/{p['section_id']}/brouillon", {"texte": "intrus", "base_brouillon_id": None}).status_code == 404
    # Le dossier assemblé se lit en entier (décision 3a), sans aucun brouillon.
    _ecrire(pa, p["section_id"], f"Notre tri des déchets {SECRET_BROUILLON}.")
    d = pb.get("/dossier")
    assert d.status_code == 200 and SECRET_BROUILLON not in d.text
    parties = d.json()["parties"]
    assert len(parties) == 4 and d.json()["message"] == ag.MSG_LECTURE
    env = _section_par(parties, "environnement")
    assert env["texte"] is None and env["statut"] == "en_cours" and env["redacteur"]["nom"] == "Breizh Désamiantage"
    assert _section_par(client.get(f"/api/atelier/{pid}/repartition", headers=h).json(),
                        "environnement")["statut"] == "en_cours"
    assert SECRET_BROUILLON not in _vues_du_chef(client, h, pid, p["section_id"], token=a["token"])
    # Envoi : il faut avoir lu l'avertissement.
    cur = pa.get(f"/sections/{p['section_id']}").json()
    r = pa.post(f"/sections/{p['section_id']}/envoyer", {"brouillon_id": cur["brouillon"]["id"]})
    assert r.status_code == 422 and r.json()["detail"]["message"] == ag.AVERTISSEMENT_ENVOI
    _envoyer(pa, p["section_id"])
    env = _section_par(pb.get("/dossier").json()["parties"], "environnement")
    assert SECRET_BROUILLON in env["texte"] and env["statut"] == "envoyee"


def test_le_lien_seul_ne_lit_jamais_la_matiere_privee(client, auth, fake_llm, monkeypatch):
    """Le chef de file a transmis le lien (invitation manuelle) : avec le lien SEUL, il ne lit ni brouillon,
    ni source, ni tâche, et n'agit pas à la place du partenaire. Réinitialiser l'espace efface les brouillons
    non envoyés (personne ne les lit) ; le code reçu par email rouvre l'espace en les gardant."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _ecrire(pa, sid, f"Brouillon privé {SECRET_BROUILLON}.")
    job, jid = _aide(pa, sid)
    assert job["status"] == "done"
    chef = P(client, a["token"], ouvrir=False)                 # le lien, sans la clé
    v = chef.get().json()
    assert v["espace"] == {"cle_valide": False, "ouvert": True, "entete": ag.ENTETE_CLE, "code_possible": False,
                           "message": ag.MSG_CLE_REQUISE}
    assert v["parties"][0]["brouillon"] is None and v["parties"][0]["aide"]["en_cours"] is None
    assert chef.get(f"/sections/{sid}").json()["brouillons"] == []
    tout = _vues_du_chef(client, h, pid, sid, token=a["token"])
    assert SECRET_BROUILLON not in tout and "4 bennes" not in tout
    for m, chemin, body in (("put", f"/sections/{sid}/brouillon", {"texte": "x", "base_brouillon_id": None}),
                            ("post", f"/sections/{sid}/aide", {}), ("post", f"/sections/{sid}/envoyer",
                                                                     {"brouillon_id": 1, "avertissement_lu": True}),
                            ("post", f"/sections/{sid}/valider", {"version_id": 1}),
                            ("post", f"/sections/{sid}/faits/x", {"statut": "relu_par_vous"}),
                            ("post", "/dossier/valider", {})):
        r = getattr(chef, m)(chemin, body)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise", chemin
    assert chef.get(f"/taches/{jid}").status_code == 403 and chef.get("/export").status_code == 403
    # Une clé inventée ne vaut rien ; l'espace déjà ouvert ne se rouvre pas sans code ni réinitialisation.
    chef.h = {ag.ENTETE_CLE: "cle-inventee"}
    assert chef.get().json()["espace"]["cle_valide"] is False
    r = chef.post("/espace")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "espace_deja_ouvert"
    # Réinitialiser : les brouillons non envoyés sont EFFACÉS, l'ancienne clé ne vaut plus, journal du membre.
    n0 = _brouillons_de(a["id"])
    assert n0 == 2
    r = chef.post("/espace", {"reinitialiser": True})
    assert r.status_code == 200 and r.json()["brouillons_effaces"] == 2
    chef.h = {ag.ENTETE_CLE: r.json()["cle"]}
    assert chef.get().json()["parties"][0]["brouillon"] is None and _brouillons_de(a["id"]) == 0
    assert pa.get().json()["espace"]["cle_valide"] is False
    j = client.get(f"/api/invite/{a['token']}/journal").json()
    assert any(e["action"] == "redaction.espace_reinitialise" for e in j["entries"])
    # Le partenaire rouvre son espace avec le code reçu à son adresse : les brouillons sont gardés.
    _ecrire(chef, sid, "Brouillon écrit après la réinitialisation.")
    import app.routers.invites as invites
    from app.models import ProjectInvite
    monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
    db = _db()
    try:
        inv = db.get(ProjectInvite, a["id"])
        inv.otp_hash = invites._hash_otp("123456")
        inv.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        inv.otp_attempts = 0
        db.commit()
    finally:
        db.close()
    assert pa.post("/espace", {"code": "000000"}).json()["detail"]["code"] == "code_incorrect"
    r = pa.post("/espace", {"code": "123456"})
    assert r.status_code == 200 and r.json()["brouillons_effaces"] == 0
    pa.h = {ag.ENTETE_CLE: r.json()["cle"]}
    assert pa.get().json()["parties"][0]["brouillon"]["texte"] == "Brouillon écrit après la réinitialisation."
    assert chef.get().json()["espace"]["cle_valide"] is False


def test_envoyer_et_valider_exigent_l_identite_prouvee(client, auth, monkeypatch):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _ecrire(pa, sid, "Nous trions les déchets amiantés.")
    import app.routers.invites as invites
    monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
    cur = pa.get(f"/sections/{sid}").json()
    r = pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": cur["brouillon"]["id"], "avertissement_lu": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified"
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).verified_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    assert pa.post(f"/sections/{sid}/envoyer", {"brouillon_id": cur["brouillon"]["id"],
                                                 "avertissement_lu": True}).status_code == 200


def test_texte_envoye_compteurs_jamais_sources_ni_extraits(client, auth, fake_llm):
    """Partenaire AVEC compte : son savoir-faire et son profil servent à SA partie ; le chef de file reçoit
    le texte envoyé et les compteurs de sources par type — jamais une source, un extrait ni un nom de
    document."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    hp, ep = _register(client, company="Breizh Désamiantage")
    r = client.post("/api/knowledge/text", headers=hp, json={
        "name": SECRET_DOC, "kind": "memoire",
        "text": (f"Gestion des déchets du chantier : tri sélectif des déchets amiantés dans 4 bennes étanches, "
                 f"bordereaux de suivi {SECRET_EXTRAIT}. Démarche environnementale et gestion des déchets du "
                 f"chantier.")})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invite/{a['token']}/claim", headers=hp).status_code == 200
    ans, vus = _reponse_partenaire(TEXTE_IA_A)
    fake = fake_llm(ans)
    pc = PC(client, pid, hp)
    sid = _part_a(vue)["section_id"]
    job, jid = _aide(pc, sid, action="rediger")
    assert job["status"] == "done", job
    assert "_debit" not in json.dumps(job) and "texte" not in json.dumps(job["result"])
    br = pc.get(f"/sections/{sid}").json()["brouillon"]
    assert br["origine"] == "ia" and any(SECRET_EXTRAIT in (s.get("extrait") or "") for s in br["sources"])
    assert SECRET_EXTRAIT in fake.sent() and vus and all(v == f"inv:{a['id']}" for v in vus)
    assert pc.get().json()["message_mode"] == ag.MSG_MODE_COMPTE
    # Par le lien (même invitation), sans la clé : rien ; avec la clé, les sources écrites depuis le compte
    # restent réservées au compte.
    pl = P(client, a["token"])
    brl = pl.get(f"/sections/{sid}").json()["brouillon"]
    assert brl["sources"] == [] and brl["sources_depuis_le_compte"] is True
    r = pc.post(f"/sections/{sid}/envoyer", {"brouillon_id": br["id"], "avertissement_lu": True})
    assert r.status_code == 200, r.text
    tout = _vues_du_chef(client, h, pid, sid, token=a["token"])
    assert "Nous mobilisons 4 bennes étanches" in tout               # le texte envoyé : oui
    for secret in (SECRET_EXTRAIT, SECRET_DOC):                       # les sources : jamais
        assert secret not in tout, secret
    ligne = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    c = ligne["texte_commun"]["compteurs"]
    assert set(c) == {"par_type", "avec_source", "a_relire", "engagements"}
    assert c["par_type"]["documents"] >= 1 and c["par_type"]["declare"] >= 1 and c["a_relire"] >= 1
    assert ligne["statut"] == "envoyee" and ligne["texte_commun"]["a_completer"] == 1
    from app.models import DossierSectionVersion
    db = _db()
    try:
        v = db.query(DossierSectionVersion).filter(DossierSectionVersion.section_id == sid,
                                                   DossierSectionVersion.partage.is_(True)).one()
        assert v.sources == [] and all("source" not in f for f in (v.faits or []))
        assert v.ecrit_par == "partenaire" and v.author_invite_id == a["id"]
    finally:
        db.close()
    d = P(client, b["token"]).get("/dossier").text
    assert "Nous mobilisons 4 bennes étanches" in d and SECRET_EXTRAIT not in d and SECRET_DOC not in d


def test_ia_du_partenaire_n_utilise_que_ses_faits(client, auth, fake_llm):
    """Sans compte : sa part déclarée (« déclaré par vous ») et le dossier de l'acheteur ; jamais le profil,
    l'équipe, le savoir-faire du chef de file ni la part d'un autre membre ; noms masqués."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    assert client.post("/api/knowledge/text", headers=h, json={
        "name": "Mémoire du chef", "kind": "memoire",
        "text": f"Gestion des déchets du chantier par le chef de file {SECRET_CHEF}."}).status_code == 200
    ans, vus = _reponse_partenaire("Nous trions les déchets amiantés [P3].")
    fake = fake_llm(ans)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    assert _aide(pa, sid)[0]["status"] == "done"
    sent = fake.sent()
    assert "Qualibat 1552" in sent and "Désamiantage du collège Brizeux" in sent
    assert "CETTE PARTIE EST RÉDIGÉE PAR Breizh Désamiantage" in sent
    assert "REGLEMENT DE LA CONSULTATION" in sent
    for interdit in (SECRET_CHEF, "Yann", "Tanguy", "Le Gall", LOT_B, "Breizh Couverture"):
        assert interdit not in sent, interdit
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["sources"] == [] and br["origine"] == "ia"
    assert pa.get().json()["message_mode"] == ag.MSG_MODE_LIEN


# ═══ 3. Tâches d'un partenaire : propriétaire distinct, 404 pour tout autre ════════

def test_tache_partenaire_404_pour_le_chef_et_son_organisation(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    job, jid = _aide(pa, sid)
    assert job["status"] == "done"
    from app.models import Job, User
    db = _db()
    try:
        j = db.get(Job, jid)
        assert j.user_id is None and j.portee == "partenaire" and j.invite_id == a["id"]
        org_id = db.query(User).filter(User.email == auth["email"]).first().org_id
    finally:
        db.close()
    hc, ec = _register(client, company="Collègue")
    db = _db()
    try:
        db.query(User).filter(User.email == ec).first().org_id = org_id
        db.commit()
    finally:
        db.close()
    for hh in (h, hc):
        r = client.get(f"/api/jobs/{jid}", headers=hh)
        assert r.status_code == 404, r.text                                       # test de non-régression
        assert client.get(f"/api/atelier/{pid}/taches/{jid}", headers=hh).status_code == 404
    assert P(client, b["token"]).get(f"/taches/{jid}").status_code == 404        # un autre membre
    assert pa.get(f"/taches/{jid}").status_code == 200                           # lui seul
    # Un compte de l'organisation du chef de file n'est jamais « le partenaire ».
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).accepted_by_user_id = _user_id(ec)
        db.commit()
    finally:
        db.close()
    assert client.get(f"/api/shared/{pid}/redaction", headers=hc).status_code == 404
    assert client.get(f"/api/shared/{pid}/redaction/taches/{jid}", headers=hc).status_code == 404
    # Le chef de file ne lance jamais l'aide de l'IA sur la partie du partenaire.
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "partie_d_un_partenaire"
    assert client.post(f"/api/atelier/{pid}/rediger", headers=h, json={"section_ids": [sid]}).status_code == 403


# ═══ 4. Facturation : quota du chef de file, plafond, message neutre, remboursement ══

def _trial(email):
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        return int(u.trial_analyses_used or 0), int(u.analyses_used_this_month or 0)
    finally:
        db.close()


def _dossier_db(pid):
    from app.models import DossierPresentation
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).first()
        return {"analyse_debitee": bool(d.analyse_debitee), "premieres": int(d.premieres_incluses or 0),
                "regen": int(d.regenerations or 0)}
    finally:
        db.close()


def test_facturation_quota_du_chef_portee_propre_plafond_et_panne(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]

    def boom(kw):
        raise RuntimeError("fournisseur indisponible")
    fake_llm(boom)
    t0 = _trial(auth["email"])
    job, _ = _aide(pa, sid)
    assert job["status"] == "error" and job["error"] == ag.MSG_IA_PANNE
    assert _trial(auth["email"]) == t0 and _dossier_db(pid)["analyse_debitee"] is False
    p = pa.get(f"/sections/{sid}").json()
    assert p["aide"]["utilisees"] == 0 and p["brouillon"] is None
    # Réussite : l'analyse du dossier est débitée au CHEF DE FILE (une fois), la partie y est comprise.
    ans, vus = _reponse_partenaire(TEXTE_IA_A)
    fake_llm(ans)
    assert _aide(pa, sid)[0]["status"] == "done"
    t1 = _trial(auth["email"])
    assert t1[0] == t0[0] + 1 and _dossier_db(pid) == {"analyse_debitee": True, "premieres": 1, "regen": 0}
    assert vus == [f"inv:{a['id']}"]
    from app.services import budget_ia
    db = _db()
    try:
        c = budget_ia._compte(db, f"inv:{a['id']}")
        assert c["compte"] == f"u{_user_id(auth['email'])}" and c["billing_user_id"] == _user_id(auth["email"])
    finally:
        db.close()
    # Refaire : gratuit (refonte du dossier), puis plafond PAR PARTIE.
    for _ in range(ag.plafond_partie() - 1):
        assert _aide(pa, sid)[0]["status"] == "done"
    assert _trial(auth["email"]) == t1 and _dossier_db(pid)["regen"] == ag.plafond_partie() - 1
    r = pa.post(f"/sections/{sid}/aide", {})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "plafond_partie"


def test_raccourcir_et_reprise_au_redemarrage(client, auth, fake_llm):
    """« Raccourcir » chez le partenaire (aucun fait ajouté) ; une tâche de partenaire interrompue par un
    redémarrage est close, son débit rendu au chef de file et son aide rendue au partenaire."""
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    long_ = " ".join(["Nous trions les déchets amiantés sur place avec soin."] * 12)
    _ecrire(pa, sid, long_)
    fake_llm(lambda kw: ("Nous trions les déchets amiantés sur place.", "end_turn"))
    job, _ = _aide(pa, sid, action="raccourcir", cible_mots=30)
    assert job["status"] == "done", job
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["origine"] == "raccourci" and br["texte"] == "Nous trions les déchets amiantés sur place."
    # Reprise au démarrage : la tâche « en cours » (thread mort) est close et tout est rendu.
    from app.models import DossierRepartition, Job
    db = _db()
    try:
        d0 = _dossier_db(pid)
        j = Job(user_id=None, portee="partenaire", invite_id=a["id"], kind=ag.JOB_REDIGER, status="running",
                label="test", result={"_debit": {"analyse": False, "sections": {str(sid): "gratuite"},
                                                 "payeur_id": _user_id(auth["email"]), "dossier_id": None,
                                                 "rendu": False}})
        db.add(j)
        db.flush()
        from app.models import DossierPresentation
        dossier = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).first()
        j.result = dict(j.result, _debit=dict(j.result["_debit"], dossier_id=dossier.id))
        dossier.regenerations = int(dossier.regenerations or 0) + 1
        rep = db.query(DossierRepartition).filter(DossierRepartition.section_id == sid).first()
        rep.job_id, rep.aides_ia = j.id, int(rep.aides_ia or 0) + 1
        jid, aides = j.id, rep.aides_ia
        db.commit()
    finally:
        db.close()
    from app.main import _recover_orphan_jobs
    _recover_orphan_jobs()
    db = _db()
    try:
        assert db.get(Job, jid).status == "error"
        rep = db.query(DossierRepartition).filter(DossierRepartition.section_id == sid).first()
        assert rep.job_id is None and rep.aides_ia == aides - 1
    finally:
        db.close()
    assert _dossier_db(pid)["regen"] == d0["regen"]


def test_message_neutre_quand_l_essai_du_chef_est_termine(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth)
    fake = fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    from app.models import Job, User
    db = _db()
    try:
        db.query(User).filter(User.email == auth["email"]).first().trial_ends_at = \
            datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    r = pa.post(f"/sections/{sid}/aide", {})
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "aide_indisponible" and d["message"] == ag.MSG_AIDE_INDISPONIBLE
    for mot in ("essai", "forfait", "quota", "analyse", "abonn", "pro", "business", "402"):
        assert mot not in json.dumps(d, ensure_ascii=False).lower(), mot
    assert fake.calls == []
    p = pa.get(f"/sections/{sid}").json()
    assert p["aide"]["utilisees"] == 0 and p["aide"]["en_cours"] is None
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")       # il écrit toujours lui-même
    _envoyer(pa, sid)
    db = _db()
    try:
        assert db.query(Job).filter(Job.invite_id == a["id"]).count() == 0
    finally:
        db.close()


# ═══ 5. Modification par le chef de file, revalidation, rétablissement ══════════════

def test_chef_modifie_a_revalider_avant_apres_puis_retablir_et_valider(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    v1 = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()["texte_commun"]["version_id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Nous trions les déchets amiantés sur place avec 12 compagnons.",
                         "base_version_id": v1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["statut"] == "a_revalider"
    assert d["mention"] == "Modifié par le chef de file, à revalider par Breizh Désamiantage"
    assert d["comparaison"]["avant"]["version_id"] == v1 and "12 compagnons" in d["comparaison"]["apres"]["texte"]
    assert d["texte_commun"]["faits_a_relire"] >= 1                         # « 12 compagnons » : à relire
    v2 = d["texte_commun"]["version_id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h, json={"texte": "x", "base_version_id": v1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "texte_modifie_entre_temps"
    p = pa.get(f"/sections/{sid}").json()
    assert p["statut"] == "a_revalider" and p["comparaison"]["avant"]["version_id"] == v1
    r = pa.post(f"/sections/{sid}/retablir", {"base_version_id": v2})
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "envoyee" and "12 compagnons" not in r.json()["texte_commun"]["texte"]
    v3 = r.json()["texte_commun"]["version_id"]
    r = pa.post(f"/sections/{sid}/valider", {"version_id": v3})
    assert r.status_code == 200 and r.json()["statut"] == "validee"
    assert r.json()["validation"]["empreinte"] == r.json()["texte_commun"]["empreinte"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Nous trions et évacuons les déchets amiantés.", "base_version_id": v3})
    assert r.json()["statut"] == "a_revalider"
    v4 = r.json()["texte_commun"]["version_id"]
    r = pa.post(f"/sections/{sid}/valider", {"version_id": v4})
    assert r.status_code == 200 and r.json()["statut"] == "validee"
    assert r.json()["mention"] == "Modifié par le chef de file, validé par Breizh Désamiantage"
    assert r.json()["brouillon"]["origine"] == "acceptee"
    actions = [x[0] for x in _audit(project_id=pid, invite_id=a["id"])]
    for act in ("redaction.part_envoyee", "redaction.part_modifiee", "redaction.part_retablie",
                "redaction.part_validee"):
        assert act in actions, act
    j = client.get(f"/api/invite/{a['token']}/journal").json()
    assert any(e["action"] == "redaction.part_modifiee" and e["who"] == "mandataire" for e in j["entries"])


def test_partenaire_absent_redige_par_le_chef_a_valider_par_x(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Le désamiantage suit la réglementation en vigueur.", "base_version_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["mention"] == "Rédigé par le chef de file, à valider par Breizh Désamiantage"
    assert r.json()["statut"] == "a_revalider"
    assert ("redaction.part_redigee_par_chef", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    r = client.put(f"/api/atelier/{pid}/sections/{sid}/texte", headers=h, json={"texte": "x", "base_version_id": None})
    assert r.status_code == 403                    # jamais par l'écriture ordinaire de l'atelier
    pa = P(client, a["token"])
    p = pa.get(f"/sections/{sid}").json()
    assert p["comparaison"]["avant"] is None and p["texte_commun"]["ecrit_par"] == "chef_de_file"
    r = pa.post(f"/sections/{sid}/retablir", {"base_version_id": p["texte_commun"]["version_id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "rien_a_retablir"


# ═══ 6. Dossier assemblé : empreinte, validation des membres, péremption ═══════════

def test_validation_du_dossier_assemble_puis_a_revalider(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés sur place.")
    _envoyer(pa, sid)
    r = pa.post("/dossier/valider", {})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "parties_a_valider"
    cur = pa.get(f"/sections/{sid}").json()["texte_commun"]["version_id"]
    assert pa.post(f"/sections/{sid}/valider", {"version_id": cur}).status_code == 200
    emp = pa.get("/dossier").json()["empreinte"]
    r = pa.post("/dossier/valider", {"empreinte": "0" * 64})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "dossier_modifie"
    r = pa.post("/dossier/valider", {"empreinte": emp})
    assert r.status_code == 200 and r.json()["validation"]["statut"] == "valide"
    for s in _etat(client, h, pid)["sections"]:
        if s["auteur"]["type"] != "organisation":
            continue
        s2 = client.put(f"/api/atelier/{pid}/sections/{s['id']}/texte", headers=h,
                        json={"texte": f"Texte du chef pour {s['intitule']}.", "base_version_id": None}).json()
        assert client.post(f"/api/atelier/{pid}/sections/{s['id']}/valider", headers=h,
                           json={"version_id": s2["version_courante"]["id"]}).status_code == 200
    # Les parties validées du chef de file entrent dans le dossier assemblé : sa validation est à refaire.
    assert pa.get().json()["dossier"]["ma_validation"]["statut"] == "a_revalider"
    assert "redaction.dossier_a_revalider" in [x[0] for x in _audit(project_id=pid)]
    vue = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    r = client.post(f"/api/atelier/{pid}/repartition/valider-dossier", headers=h,
                    json={"empreinte": vue["dossier"]["empreinte"]})
    assert r.status_code == 200, r.text
    emp2 = pa.get("/dossier").json()["empreinte"]
    assert pa.post("/dossier/valider", {"empreinte": emp2}).status_code == 200
    pret = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()["dossier"]["pret"]
    assert pret["message"] == "Sections validées 4 sur 4" and pret["complet"] is True
    # Toute modification ensuite : « à revalider » pour TOUS les membres (même mécanisme que la convention).
    cur = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()["texte_commun"]["version_id"]
    client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
               json={"texte": "Nous trions les déchets amiantés.", "base_version_id": cur})
    vue = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    assert {m["statut"] for m in vue["dossier"]["pret"]["membres"]} == {"a_revalider"}
    assert vue["dossier"]["pret"]["complet"] is False
    assert vue["dossier"]["pret"]["message"] == "Sections validées 3 sur 4"
    assert all(x[4] for x in _audit(project_id=pid) if x[0].startswith("redaction."))     # journal chaîné
    j = client.get(f"/api/invite/{a['token']}/journal").json()
    assert any(e["action"] == "redaction.dossier_a_revalider" for e in j["entries"])


# ═══ 7. Isolation entre deux groupements ══════════════════════════════════════════

def test_isolation_entre_deux_groupements(client, auth, fake_llm):
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    pid1, st1, a1, b1, vue1 = _groupement(client, auth, avec_b=False)
    h2, e2 = _register(client, company="Autre Chef SARL")
    pid2, st2, a2, b2, vue2 = _groupement(client, {"headers": h2, "email": e2}, avec_b=False)
    s1, s2 = _part_a(vue1)["section_id"], _part_a(vue2)["section_id"]
    p1, p2 = P(client, a1["token"]), P(client, a2["token"])
    _ecrire(p2, s2, f"Texte privé du groupement 2 {SECRET_BROUILLON}.")
    _, j2 = _aide(p2, s2)
    assert p1.get(f"/sections/{s2}").status_code == 404
    assert p1.put(f"/sections/{s2}/brouillon", {"texte": "x", "base_brouillon_id": None}).status_code == 404
    assert p1.get(f"/taches/{j2}").status_code == 404
    assert SECRET_BROUILLON not in p1.get("/dossier").text
    # La clé d'un espace ne vaut que pour SON lien.
    croise = P(client, a1["token"], ouvrir=False)
    croise.h = dict(p2.h)
    assert croise.get().json()["espace"]["cle_valide"] is False
    for url in (f"/api/atelier/{pid2}/repartition", f"/api/atelier/{pid2}/repartition/{s2}"):
        assert client.get(url, headers=auth["headers"]).status_code == 404
    assert client.put(f"/api/atelier/{pid2}/repartition/{s2}/texte", headers=auth["headers"],
                      json={"texte": "x"}).status_code == 404
    assert client.get(f"/api/jobs/{j2}", headers=h2).status_code == 404
    hp, _ = _register(client, company="Partenaire Compte")
    assert client.post(f"/api/invite/{a1['token']}/claim", headers=hp).status_code == 200
    assert client.get(f"/api/shared/{pid1}/redaction", headers=hp).status_code == 200
    assert client.get(f"/api/shared/{pid2}/redaction", headers=hp).status_code == 404
    assert client.get(f"/api/shared/{pid1}/redaction/taches/{j2}", headers=hp).status_code == 404


# ═══ 8. Invitation retirée, déclinée ou expirée : accès coupé ══════════════════════

def test_invitation_retiree_coupe_l_acces_et_efface_les_brouillons(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Nous trions les déchets amiantés.")
    _envoyer(pa, sid)
    _ecrire(pa, sid, f"Deuxième brouillon {SECRET_BROUILLON}.")
    assert _brouillons_de(a["id"]) == 2
    assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=h).status_code == 200
    for m, chemin, body in (("get", "", None), ("get", "/dossier", None), ("get", f"/sections/{sid}", None),
                            ("put", f"/sections/{sid}/brouillon", {"texte": "x", "base_brouillon_id": None}),
                            ("post", f"/sections/{sid}/aide", {}), ("post", "/espace", {"reinitialiser": True})):
        r = getattr(pa, m)(chemin, body) if body is not None else getattr(pa, m)(chemin)
        assert r.status_code == 404, (chemin, r.status_code)
    assert _brouillons_de(a["id"]) == 0
    d = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert d["redacteur"]["type"] == "chef_de_file" and d["statut"] == "a_rediger" and d["texte_commun"] is None
    sec = client.get(f"/api/atelier/{pid}/sections/{sid}", headers=h).json()
    assert sec["peut_ecrire"] is True and sec["version_courante"] is None and len(sec["versions"]) == 1
    assert ("redaction.parts_reprises", a["id"]) in [(x[0], x[1]) for x in _audit(project_id=pid)]
    # Déclin : même effet.
    pb = P(client, b["token"])
    met = _section_par(vue, "méthodologie")["section_id"]
    client.put(f"/api/atelier/{pid}/repartition/{met}", headers=h, json={"redacteur": "partenaire",
                                                                          "invite_id": b["id"]})
    _ecrire(pb, met, "Méthode de l'électricien.")
    assert client.post(f"/api/invite/{b['token']}/decline").status_code == 200
    assert pb.get().status_code == 410 and _brouillons_de(b["id"]) == 0


def test_invitation_expiree_ou_reseau_non_acceptee(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa = P(client, a["token"])
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.get(ProjectInvite, b["id"]).source = "reseau_adjugo"
        db.commit()
    finally:
        db.close()
    assert pa.get().status_code == 410
    r = client.get(f"/api/invite/{b['token']}/redaction")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "apercu_minimal"
    vue = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    m = {x["invite_id"]: x for x in vue["membres"]}
    assert m[a["id"]]["peut_rediger"] is False and "expiré" in m[a["id"]]["raison"]
    assert m[b["id"]]["peut_rediger"] is False and "accepté" in m[b["id"]]["raison"]
    met = _section_par(vue, "méthodologie")["section_id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{met}", headers=h, json={"redacteur": "partenaire",
                                                                              "invite_id": b["id"]})
    assert r.status_code == 409


# ═══ 9. Export du chef de file : les points ouverts d'une part envoyée bloquent ═══

def test_export_bloque_par_la_part_envoyee_du_partenaire(client, auth, fake_llm):
    """Un fait sans source (rédigé avec l'IA) et un « [À compléter] » de la part ENVOYÉE bloquent l'export du
    chef de file (décision 2b, étendue aux parts des partenaires), sans qu'il voie la moindre source."""
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    gate = _etat(client, h, pid)["blocage"]
    assert any(r["code"] == "attente_partenaire" for r in gate["raisons"])
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    assert _aide(pa, sid)[0]["status"] == "done"
    _envoyer(pa, sid)
    gate = _etat(client, h, pid)["blocage"]
    codes = {r["code"]: r for r in gate["raisons"]}
    assert "attente_partenaire" not in codes
    assert any(x["section_id"] == sid for x in codes["a_completer"]["sections"])
    assert any(x["section_id"] == sid for x in codes["faits_a_relire"]["sections"])
    assert any(x["section_id"] == sid for x in next(a_ for a_ in gate["avertissements"]
                                                     if a_["code"] == "non_valide")["sections"])
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "export_bloque"
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h,
                    json={"raison": "depot_en_l_etat", "texte": "Le partenaire complétera dans Word.",
                          "etat_hash": gate["etat_hash"]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "etat_hash": gate["etat_hash"]})
    assert r.status_code == 200


# ═══ 10. RGPD : export, effacement des comptes ═════════════════════════════════════

def test_rgpd_export_et_effacement_des_comptes(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    hp, ep = _register(client, company="Breizh Désamiantage")
    assert client.post(f"/api/invite/{a['token']}/claim", headers=hp).status_code == 200
    pc = PC(client, pid, hp)
    sid = _part_a(vue)["section_id"]
    _ecrire(pc, sid, f"Brouillon du compte {SECRET_BROUILLON}.")
    _envoyer(pc, sid)
    exp_p = client.get("/api/rgpd/export", headers=hp).json()
    parts = exp_p["parts_redigees_pour_des_groupements"]
    assert parts and SECRET_BROUILLON in json.dumps(parts, ensure_ascii=False) and parts[0]["textes_envoyes"]
    exp_c = client.get("/api/rgpd/export", headers=h).json()
    assert exp_c["dossiers_de_groupement"] and exp_c["dossiers_de_groupement"][0]["repartition"]
    assert SECRET_BROUILLON not in json.dumps(exp_c["dossiers_de_groupement"], ensure_ascii=False)
    pa = P(client, a["token"])
    r = pa.get("/export")
    assert r.status_code == 200 and SECRET_BROUILLON in r.text
    # Effacement du compte du PARTENAIRE : ses brouillons partent, le texte envoyé reste au groupement.
    r = client.post("/api/rgpd/delete-account", headers=hp, json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    assert _brouillons_de(a["id"]) == 0
    d = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert d["statut"] == "envoyee"
    assert SECRET_BROUILLON in client.get(f"/api/atelier/{pid}/sections/{sid}/versions/"
                                          f"{d['texte_commun']['version_id']}", headers=h).text
    # Effacement du compte du CHEF DE FILE : tout le dossier de groupement part avec lui.
    fake_llm(_reponse_partenaire(TEXTE_IA_A)[0])
    _, jid = _aide(pa, sid)
    r = client.post("/api/rgpd/delete-account", headers=h, json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    from app.models import DossierPartBrouillon, DossierRepartition, DossierValidation, Job
    db = _db()
    try:
        assert db.query(DossierRepartition).filter(DossierRepartition.project_id == pid).count() == 0
        assert db.query(DossierPartBrouillon).filter(DossierPartBrouillon.project_id == pid).count() == 0
        assert db.query(DossierValidation).filter(DossierValidation.project_id == pid).count() == 0
        assert db.get(Job, jid) is None
    finally:
        db.close()


def test_purge_brouillons_d_une_invitation_expiree(client, auth):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    sid = _part_a(vue)["section_id"]
    _ecrire(pa, sid, "Brouillon.")
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=ag.PURGE_JOURS + 1)
        db.commit()
        assert ag.purger(db)["brouillons_partenaires_effaces"] >= 1
    finally:
        db.close()
    assert _brouillons_de(a["id"]) == 0


# ═══ 11. Demander les parts, relances, démonstration ═══════════════════════════════

def test_demander_les_parts_et_relance_a_la_date_limite(client, auth, monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).recipient = "desamiantage@partenaire.fr"
        db.commit()
    finally:
        db.close()
    sid = _part_a(vue)["section_id"]
    lim = date.today() + timedelta(days=2)
    client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h, json={"date_limite": lim.isoformat()})
    r = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={})
    assert r.status_code == 200, r.text
    assert r.json()["demandees"][0]["parties"] == 1 and len(sent) == 1
    assert "Démarche environnementale" in sent[0][2] and a["token"] in sent[0][2]
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).json()["deja_demandees"]
    assert len(sent) == 1
    db = _db()
    try:
        assert ag.relancer_parts(db, date.today())["parts_relancees"] == 1
        assert ag.relancer_parts(db, date.today())["parts_relancees"] == 0
    finally:
        db.close()
    assert len(sent) == 2 and "Rappel" in sent[1][1]


def test_demo_bloque_les_ecritures_du_dossier_de_groupement():
    from app.core.demo_guard import blocked_action
    for m, path in (("POST", "/api/atelier/3/repartition"), ("PUT", "/api/atelier/3/repartition/4"),
                    ("PUT", "/api/atelier/3/repartition/4/texte"), ("POST", "/api/atelier/3/repartition/demander"),
                    ("POST", "/api/atelier/3/repartition/valider-dossier"),
                    ("POST", "/api/shared/3/redaction/sections/4/aide"),
                    ("POST", "/api/shared/3/redaction/sections/4/envoyer")):
        assert blocked_action(m, path), path
    assert blocked_action("GET", "/api/atelier/3/repartition") is None


# ═══ 12. Migration x8y9redactionv4 (SQLite) ═══════════════════════════════════════

def test_migration_v4_sqlite_neuve_precedente_rejeu_retour_arriere(tmp_path):
    import sqlalchemy as sa
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "v4.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    tables = ("dossier_repartitions", "dossier_parts_brouillons", "dossier_validations")

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=root, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def schema():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            insp = sa.inspect(eng)
            out = {}
            for t in tables + ("jobs", "dossier_section_versions", "project_invites"):
                out[t] = ({c["name"]: (str(c["type"]), c["nullable"], str(c.get("default"))) for c in insp.get_columns(t)},
                          {i["name"]: (tuple(i["column_names"]), bool(i.get("unique"))) for i in insp.get_indexes(t)})
            return out
        finally:
            eng.dispose()

    run("upgrade", "head")
    neuf = schema()
    assert neuf["jobs"][0]["user_id"][1] is True and {"portee", "invite_id"} <= set(neuf["jobs"][0])
    assert {"partage", "ecrit_par", "compteurs"} <= set(neuf["dossier_section_versions"][0])
    assert "espace_hash" in neuf["project_invites"][0]
    assert neuf["dossier_repartitions"][1]["ix_dossier_repartitions_section_id"] == (("section_id",), True)
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO jobs (user_id, kind, status, portee) VALUES "
                           "(NULL, 'partenaire_rediger', 'done', 'partenaire')"))
    eng.dispose()
    run("downgrade", "w7x8analysepartagee")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    try:
        insp = sa.inspect(eng)
        assert not set(tables) & set(insp.get_table_names())
        jc = {c["name"]: c for c in insp.get_columns("jobs")}
        assert "portee" not in jc and "invite_id" not in jc and jc["user_id"]["nullable"] is False
        assert "partage" not in {c["name"] for c in insp.get_columns("dossier_section_versions")}
        assert "espace_hash" not in {c["name"] for c in insp.get_columns("project_invites")}
        with eng.connect() as cn:
            assert cn.execute(sa.text("SELECT count(*) FROM jobs WHERE user_id IS NULL")).scalar() == 0
    finally:
        eng.dispose()
    run("upgrade", "head")
    assert schema() == neuf
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO dossier_validations (dossier_id, project_id, owner_id, membre_cle) "
                           "VALUES (1, 1, 1, 'chef_de_file')"))
    eng.dispose()
    run("stamp", "w7x8analysepartagee")
    run("upgrade", "head")
    assert schema() == neuf
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    try:
        with eng.connect() as cn:
            row = cn.execute(sa.text("SELECT membre, statut, empreinte FROM dossier_validations")).one()
            assert tuple(row) == ("chef_de_file", "valide", "")
    finally:
        eng.dispose()
