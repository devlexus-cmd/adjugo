"""
Réorganisation de l'interface — vague 2b, chantier B3 « espace partenaire ». Contrat : docs/REORGANISATION_V2B.md,
section B3 ; étude « organisation du logiciel », § 5.3 (côté partenaire), § 6 (« Avant d'inviter »), § 7.6, § 11
(décision 15 a).

  1. L'espace du partenaire se réduit à « Votre part dans [marché] », avec la même barre d'étapes que la page du marché
     du chef de file (Accepter · Ma part · Donner mon accord · Déposé par le chef de file), dans ses deux mises en œuvre :
     le dossier partagé de l'application (partenaire qui a un compte) et invite.html (partenaire sans compte). Plus de
     menu fermé à cadenas ni d'entrée « Projets à venir » : un seul encart « Créer mon compte », durée de l'essai lue
     dans la configuration. Toutes les fonctions du partenaire restent atteignables.
  2. « Voir ce que verra [partenaire] » sur la page du marché, avant et après l'invitation : son écran en lecture,
     construit UNIQUEMENT avec ce que le partenaire reçoit. Prouvé sur l'API : ce que reçoit l'aperçu est inclus, valeur
     pour valeur, dans ce que reçoit le partenaire, et rien d'autre (ni décomposition du prix du chef de file, ni matière
     d'un autre membre, ni donnée du partenaire que le chef de file ne voit pas déjà).

Aucun appel réseau réel (registres simulés, emails coupés) ; les fonctions pures sous Node.
"""
import json
import pathlib
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta

import pytest

from tests.test_reseau_partenaires import _db, _org, _project, _publish, mails, reg  # noqa: F401 (fixtures)
from tests.textes_visibles import chaines_js, mots_bannis, textes_html
from tests.zones import noms, zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
APERCU = zone(HTML, "vue-apercu-partenaire")
PARTAGE = zone(HTML, "vue-sharedao")


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _fonction(src, nom):
    """Le texte d'une fonction de premier niveau (app.js) ou du script d'invite.html, sans son indentation."""
    m = re.search(r"\n( *)function " + re.escape(nom) + r"\(", src)
    assert m, nom
    ind = m.group(1)
    i = m.start() + 1
    j = src.index("\n" + ind + "}\n", i)
    return "\n".join(ligne[len(ind):] if ligne.startswith(ind) else ligne for ligne in src[i:j + len(ind) + 2].split("\n"))


def _methode(nom):
    m = re.search(r"\n    (?:async )?" + re.escape(nom) + r"\([^)]*\) \{", JS)
    assert m, nom
    i = m.start() + 1
    j = re.search(r"\n    (?:async )?[A-Za-z_$][\w$]*\([^)]*\) \{|\n    // ", JS[i + 4:])
    return JS[i:i + 4 + j.start()].rstrip().rstrip(",") + ","


def _inclus(a, b, chemin="vue"):
    """Chaque clé de `a` est dans `b` avec la même valeur (récursif) : l'aperçu ne reçoit rien que le partenaire ne
    reçoive pas."""
    if isinstance(a, dict):
        assert isinstance(b, dict), (chemin, b)
        for k, v in a.items():
            assert k in b, f"{chemin}.{k} : absent de ce que reçoit le partenaire"
            _inclus(v, b[k], f"{chemin}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), (chemin, a, b)
        for i, (x, y) in enumerate(zip(a, b)):
            _inclus(x, y, f"{chemin}[{i}]")
    else:
        assert a == b, (chemin, a, b)


def _apercu(client, org, pid, **q):
    r = client.get(f"/api/projects/{pid}/apercu-partenaire", headers=org["headers"], params=q)
    assert r.status_code == 200, r.text
    return r.json()


def _inviter(client, chef, pid, nom, **extra):
    body = {"company_name": nom, "recipient": "", "role": "cotraitant", "can_view_docs": True, "can_contribute": True}
    body.update(extra)
    r = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _soumettre(client, token, nom, prix):
    r = client.put(f"/api/invite/{token}/contribution", json={
        "company_name": nom, "lot": "Électricité (lot 2)", "prix_lot_ht": prix, "siret": "12345678900012",
        "capacites": {"ca_n1": 1850000, "effectif": 14}, "memoire_paragraph": "Notre savoir-faire en électricité.",
        "version": 0})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/invite/{token}/contribution/submit")
    assert r.status_code == 200, r.text


def _ajouter_piece_et_chiffrage(pid, uid):
    """Une pièce du marché (vue par le partenaire si le partage est ouvert) et le chiffrage DÉTAILLÉ du chef de file
    (jamais montré au partenaire)."""
    from app.models import Document, Project
    db = _db()
    try:
        db.add(Document(user_id=uid, project_id=pid, name="RC.pdf", folder="DCE", file_key="x/rc.pdf", file_size=1200))
        p = db.get(Project, pid)
        p.estimate = {"total_ht": 123456, "lignes": [{"designation": "Main-d'œuvre secrète du chef", "montant": 99999}]}
        db.commit()
    finally:
        db.close()


# Clés que la vue du partenaire peut porter mais que l'aperçu ne reprend jamais (son adresse, son jeton, sa part, ses
# capacités, la composition du groupement), et clés du chef de file qui ne vont jamais au partenaire.
CLES_INTERDITES = ("token", "recipient", "prix_lot_ht", "detail_chiffre", "capacites", "my_capacites", "members", "my_apport",
                   "score_groupement", "gaps_combles", "seuils", "estimate", "lignes", "lead_total_ht", "parts",
                   "ai_summary", "match_score", "n_members", "n_submitted", "steps", "etapes", "convention", "id", "size")
VALEURS_INTERDITES = ("Main-d'œuvre secrète du chef", "99999", "123456", "1850000", "Notre savoir-faire")


def _rien_d_interdit(apercu, *en_plus):
    def cles(x, chemin=""):
        if isinstance(x, dict):
            for k, v in x.items():
                # « convention » et « id » n'existent que dans `etat` (le statut de la convention, que le chef de file
                # voit) et `invite_id` (sa propre invitation) : ailleurs, jamais.
                if not (chemin == "etat" and k == "convention"):
                    assert k not in CLES_INTERDITES, f"{chemin}.{k}"
                cles(v, k if not chemin else chemin + "." + k)
        elif isinstance(x, list):
            for y in x:
                cles(y, chemin)
    cles(apercu)
    texte = json.dumps(apercu, ensure_ascii=False)
    for mot in VALEURS_INTERDITES + en_plus:
        assert mot not in texte, mot


# ═══ 1. « Voir ce que verra [partenaire] » : rien de plus que ce que reçoit le partenaire ══════════════════════════════

def test_apercu_d_une_invitation_inclus_dans_ce_que_recoit_le_partenaire(client, reg, mails):
    chef, part = _org(client, "Breizh Couverture"), _org(client, "Le Gall Électricité")
    pid = _project(client, chef)
    _ajouter_piece_et_chiffrage(pid, chef["id"])
    inv = _inviter(client, chef, pid, "Le Gall Électricité")
    tok = inv["token"]
    ap = _apercu(client, chef, pid, invite_id=inv["id"])
    assert ap["acces"] is True and ap["pour"] == "invitation" and ap["invite_id"] == inv["id"]
    vue = client.get(f"/api/invite/{tok}").json()
    _inclus(ap["vue"], vue)
    assert ap["vue"]["project"]["name"] == "Rénovation de l'école Jules-Ferry" and ap["vue"]["mandataire"] == "Breizh Couverture"
    assert ap["vue"]["project"]["deadline"] and ap["vue"]["documents"] == [{"name": "RC.pdf", "folder": "DCE"}]
    assert ap["pieces_attendues"] == client.get(f"/api/invite/{tok}/coffre-croise").json()["expected"]
    assert ap["etat"] == {"part": None, "convention": None, "signature": None}
    _rien_d_interdit(ap)
    # La part du partenaire : le chef de file en voit l'état (« soumise »), jamais son contenu dans l'aperçu.
    _soumettre(client, tok, "Le Gall Électricité", 280000)
    ap = _apercu(client, chef, pid, invite_id=inv["id"])
    _inclus(ap["vue"], client.get(f"/api/invite/{tok}").json())
    assert ap["etat"]["part"] == client.get(f"/api/invite/{tok}/contribution").json()["status"] == "submitted"
    _rien_d_interdit(ap, "280000", "12345678900012")
    # Lecture seule : l'aperçu ne compte pas une consultation du partenaire et n'écrit rien au journal.
    from app.models import AuditLog, ProjectInvite
    db = _db()
    try:
        vues = db.get(ProjectInvite, inv["id"]).view_count
        n = db.query(AuditLog).filter(AuditLog.project_id == pid).count()
    finally:
        db.close()
    _apercu(client, chef, pid, invite_id=inv["id"])
    _apercu(client, chef, pid)
    db = _db()
    try:
        assert db.get(ProjectInvite, inv["id"]).view_count == vues
        assert db.query(AuditLog).filter(AuditLog.project_id == pid).count() == n
        assert db.query(ProjectInvite).filter(ProjectInvite.project_id == pid).count() == 1   # rien de créé
    finally:
        db.close()


def test_apercu_avant_l_invitation_est_ce_que_recevra_le_partenaire(client, reg, mails):
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    _ajouter_piece_et_chiffrage(pid, chef["id"])
    for role, docs in (("cotraitant", True), ("sous_traitant", False)):
        ap = _apercu(client, chef, pid, role=role, can_view_docs=str(docs).lower(), can_contribute="true",
                     nom="Menuiserie Kerdual")
        assert ap["acces"] is True and ap["pour"] == "nouveau" and ap["invite_id"] is None
        assert ap["vue"]["invited"] == {"company": "Menuiserie Kerdual", "role": role}
        # Une invitation neuve n'a ni part ni accord, et ne voit aucun total (inviter défige l'offre).
        assert ap["etat"] == {"part": None, "convention": None, "signature": None} and "for_member" not in ap["vue"]
        _rien_d_interdit(ap)
        inv = _inviter(client, chef, pid, "Menuiserie Kerdual", role=role, can_view_docs=docs)
        vue = client.get(f"/api/invite/{inv['token']}").json()
        _inclus(ap["vue"], vue)
        assert ap["pieces_attendues"] == client.get(f"/api/invite/{inv['token']}/coffre-croise").json()["expected"]
        assert client.delete(f"/api/projects/{pid}/invites/{inv['id']}", headers=chef["headers"]).status_code == 200


def test_apercu_d_une_invitation_du_reseau_ni_adresse_ni_brouillon(client, reg, mails):
    b = _org(client, "Partenaire Réseau Discret")
    b_pid = _publish(client, reg, b)
    a = _org(client, "Chef de File Réseau B3")
    _publish(client, reg, a, metiers=("couverture",))
    pid = _project(client, a)
    # Avant l'invitation : l'aperçu limité, comme le partenaire le verra (ni acheteur, ni lien de l'avis, ni pièces).
    avant = _apercu(client, a, pid, reseau="true", role="cotraitant", nom="Partenaire Réseau Discret")
    assert avant["vue"]["apercu_minimal"] is True and avant["vue"]["project"]["client"] is None
    assert avant["vue"]["documents"] == [] and avant["pieces_attendues"] is None
    assert "acheteur" not in avant["vue"]["project"]["analysis"]
    r = client.post(f"/api/projects/{pid}/reseau/invitations", headers=a["headers"],
                    json={"profile_id": b_pid, "lot": "Lot 2 — Électricité"})
    assert r.status_code == 200, r.text
    inv_id = r.json()["invitation"]["id"]
    recues = client.get("/api/reseau/invitations", headers=b["headers"]).json()["invitations"]
    tok = next(x["token"] for x in recues if x["mandataire"] == a["name"])
    # Le nom de l'entreprise : celui que le chef de file a sous les yeux dans la fenêtre (ici saisi), le serveur
    # inscrivant ensuite celui du profil du réseau ; tout le reste est ce que le partenaire reçoit.
    sans_nom = json.loads(json.dumps(avant["vue"]))
    sans_nom["invited"].pop("company")
    _inclus(sans_nom, client.get(f"/api/invite/{tok}").json())
    # Le partenaire saisit un brouillon pendant l'aperçu limité : le chef de file ne le voit pas, l'aperçu non plus.
    r = client.put(f"/api/invite/{tok}/contribution", json={"company_name": "Nom saisi en brouillon", "prix_lot_ht": 77777,
                                                           "version": 0})
    assert r.status_code == 200, r.text
    ap = _apercu(client, a, pid, invite_id=inv_id)
    vue = client.get(f"/api/invite/{tok}").json()
    _inclus(ap["vue"], vue)
    assert ap["vue"]["apercu_minimal"] is True and ap["etat"]["part"] is None and ap["pieces_attendues"] is None
    _rien_d_interdit(ap, b["email"], "77777", "Nom saisi en brouillon")
    assert vue["invited"]["recipient"] == b["email"]          # le partenaire voit son adresse ; l'aperçu, jamais
    # Acceptée depuis son compte : l'aperçu suit (dossier complet), toujours inclus dans sa vue.
    assert client.post(f"/api/invite/{tok}/claim", headers=b["headers"]).status_code == 200
    ap = _apercu(client, a, pid, invite_id=inv_id)
    _inclus(ap["vue"], client.get(f"/api/invite/{tok}").json())
    assert ap["vue"]["apercu_minimal"] is False and ap["vue"]["project"]["client"] == "Ville de Quimper"
    _rien_d_interdit(ap, b["email"])


def test_total_de_l_offre_commune_seulement_quand_le_partenaire_le_voit(client, reg, mails):
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    p1 = _inviter(client, chef, pid, "Le Gall Électricité")
    st = _inviter(client, chef, pid, "Peinture Sous-Traitée", role="sous_traitant")
    _soumettre(client, p1["token"], "Le Gall Électricité", 280000)
    _soumettre(client, st["token"], "Peinture Sous-Traitée", 40000)
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=chef["headers"], json={"lead_total_ht": 120000})
    assert r.status_code == 200, r.text
    for inv, voit in ((p1, True), (st, False)):
        ap = _apercu(client, chef, pid, invite_id=inv["id"])
        vue = client.get(f"/api/invite/{inv['token']}").json()
        _inclus(ap["vue"], vue)
        total = ap["vue"]["for_member"]["state"]["total_offre_ht"]
        assert (total is not None) is voit and total == vue["for_member"]["state"]["total_offre_ht"]
        # Ni la part du chef de file, ni celle des autres membres : seulement le total, quand le partenaire le voit.
        _rien_d_interdit(ap, "120000")
    # Pas encore invité : une invitation neuve défige l'offre, il n'y verra donc aucun total.
    assert "for_member" not in _apercu(client, chef, pid)["vue"]


def test_apercu_reserve_au_chef_de_file_et_lien_qui_ne_s_ouvre_plus(client, reg, mails):
    chef, part, tiers = _org(client, "Breizh Couverture"), _org(client, "Le Gall Électricité"), _org(client, "Concurrent SARL")
    pid, autre = _project(client, chef), _project(client, chef)
    inv = _inviter(client, chef, pid, "Le Gall Électricité")
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=part["headers"]).status_code == 200
    for org in (part, tiers):
        for q in ({"invite_id": inv["id"]}, {}):
            assert client.get(f"/api/projects/{pid}/apercu-partenaire", headers=org["headers"], params=q).status_code == 404
    assert client.get(f"/api/projects/{pid}/apercu-partenaire", params={}).status_code == 401
    # Une invitation d'un autre marché ne se lit pas par celui-ci.
    assert client.get(f"/api/projects/{autre}/apercu-partenaire", headers=chef["headers"],
                      params={"invite_id": inv["id"]}).status_code == 404
    # Révoquée : le partenaire ne voit plus rien, l'aperçu le dit et ne montre rien.
    assert client.delete(f"/api/projects/{pid}/invites/{inv['id']}", headers=chef["headers"]).status_code == 200
    assert client.get(f"/api/invite/{inv['token']}").status_code == 404
    ap = _apercu(client, chef, pid, invite_id=inv["id"])
    assert ap == {"acces": False, "raison": "revoquee", "invite_id": inv["id"], "pour": "invitation",
                  "company": "Le Gall Électricité", "role": "cotraitant"}
    inv2 = _inviter(client, chef, pid, "Le Gall Électricité")
    assert client.post(f"/api/invite/{inv2['token']}/decline").status_code == 200
    assert _apercu(client, chef, pid, invite_id=inv2["id"])["raison"] == "declinee"


def test_apercu_de_la_demonstration(client):
    """La vitrine (lien privé) : l'aperçu du partenaire de Kerhel s'ouvre, en lecture, inclus dans sa vue."""
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        kerhel = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        inv = db.query(ProjectInvite).filter(ProjectInvite.project_id == kerhel.id).first()
        pid, iid, tok = kerhel.id, inv.id, inv.token
    finally:
        db.close()
    r = client.post("/api/auth/demo", json=None)
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    ap = client.get(f"/api/projects/{pid}/apercu-partenaire", headers=h, params={"invite_id": iid})
    assert ap.status_code == 200, ap.text
    ap = ap.json()
    assert ap["acces"] is True and ap["vue"]["mandataire"]
    _inclus(ap["vue"], client.get(f"/api/invite/{tok}").json())
    assert client.get(f"/api/projects/{pid}/apercu-partenaire", headers=h).status_code == 200


# ═══ 2. L'écran de l'aperçu : il ne lit que ce que l'API lui donne ═══════════════════════════════════════════════════

def test_l_ecran_de_l_apercu_ne_lit_que_la_reponse_de_l_aperçu():
    gabarit = re.sub(r"<!--.*?-->", "", APERCU, flags=re.S)
    # Les expressions du gabarit (liaisons, conditions, interpolations) : ce que l'écran lit.
    expr = " ".join(re.findall(r"\{\{(.*?)\}\}", gabarit, flags=re.S)
                    + re.findall(r'\s(?:v-[\w-]+|:[\w-]+|@[\w.-]+)="([^"]*)"', gabarit))
    # Jamais les données de la page du marché du chef de file (son prix, son chiffrage, ses partenaires…).
    for interdit in ("ao.", "estimate", "consortium", "contribution", "sharedAo", "prix_lot", "cdetail", "grp.", "conv.d"):
        assert interdit not in expr, interdit
    lus = set(re.findall(r"\bv\.([a-z_]+(?:\.[a-z_]+)*)", expr))
    assert lus <= {"mandataire", "project.name", "project.client", "project.deadline", "project.analysis",
                   "project.analysis.date_limite", "project.source_url", "apercu_minimal", "apercu_message",
                   "invited.role", "can_contribute", "documents", "documents.length", "for_member.warning_two_members"}, lus
    for m in ("apercuBarre", "apercuTotal", "apercuPieces"):
        corps = _methode(m)
        assert "this.ao" not in corps and "this.apercu.d" in corps, m
    # La seule route lue : celle de l'aperçu (et la liste des invitations du marché, pour le choix « Aperçu pour »).
    assert '"/apercu-partenaire?"' in _methode("apercuCharger") and '"/invites"' in _methode("_apercuInvitations")
    assert "/api/invite/" not in APERCU + _methode("apercuCharger") + _methode("apercuOuvrir")


def test_les_entrees_vers_l_apercu_avant_et_apres_l_invitation():
    entete = zone(HTML, "marche-entete")
    lien = zone(HTML, "marche-apercu")
    assert lien in entete and '@click="apercuDepuisMarche()"' in lien and "Voir ce que verra votre partenaire" in lien
    assert '@click="apercuInvitation(inv)"' in zone(HTML, "marche-invitations")
    f = zone(HTML, "fenetre-invitation")
    assert f.count('@click="rinvApercu()"') == 2                      # avant l'envoi, et sur l'invitation créée
    assert "<span>Voir ce que verra</span>" in f and "<span>Voir ce que voit</span>" in f
    for z in ("apercu-choix", "apercu-sans-acces", "apercu-ecran", "apercu-attendu", "apercu-offre"):
        assert zone(HTML, z) in APERCU, z
    assert APERCU.startswith('<section data-test="vue-apercu-partenaire" class="pa-vue" v-if="view===\'apercu\'"')
    assert '@click="apercuRetour()"' in APERCU and "Retour au marché" in APERCU
    assert '@click="apercuReprendre()"' in APERCU and "Revenir à l'invitation" in APERCU


def test_la_fenetre_d_invitation_passe_ses_choix_a_l_apercu_sous_node():
    script = "\n".join([
        "const _adrId = (n) => { const t = String(n == null ? '' : n); return /^[1-9][0-9]{0,11}$/.test(t) ? t : ''; };",
        _fonction(JS, "_apercuInit"),
        "const o = {", _methode("rinvApercu"), _methode("apercuOuvrir"), "};",
        """
const res = [];
o.view = "aodetail"; o._ecranOuvert = () => {}; o.apercuCharger = () => {}; o._apercuInvitations = () => {};
o.rinvClose = () => { o.rinv = null; };
o.rinv = { kind: "reseau", projectId: 7, name: "Le Gall", role: "sous_traitant", can_view_docs: false, can_contribute: false,
           done: "", inviteId: null, busy: true, err: "x" };
o.rinvApercu(); res.push({ view: o.view, a: Object.assign({}, o.apercu, { depuis: !!o.apercu.depuis }), fenetre: o.rinv });
o.rinv = { kind: "connu", projectId: 7, name: "Kerdual", role: "cotraitant", can_view_docs: true, can_contribute: false,
           done: "Lien créé", inviteId: 56 };
o.rinvApercu(); res.push({ a: Object.assign({}, o.apercu, { depuis: !!o.apercu.depuis }) });
console.log(JSON.stringify(res));
"""])
    r = _node(script)
    a = r[0]["a"]
    assert r[0]["view"] == "apercu" and r[0]["fenetre"] is None
    assert (a["projectId"], a["inviteId"], a["nom"], a["role"], a["reseau"], a["can_view_docs"], a["can_contribute"]) == \
        (7, None, "Le Gall", "sous_traitant", True, False, True)      # le réseau : la part est toujours demandée
    assert a["depuis"] is True
    b = r[1]["a"]
    assert (b["projectId"], b["inviteId"], b["depuis"]) == (7, 56, False)


def test_adresse_de_l_apercu_et_retour_au_marche_sous_node():
    i = JS.index("const ADRESSES = {")
    pur = JS[i:JS.index("// ══════════ Réorganisation, vague 2a (chantier A3)", i)]
    r = _node(pur + """
console.log(JSON.stringify({
  a: [adresseDe({ view: "apercu", projet: 12 }), adresseDe({ view: "apercu", projet: 12, invitation: 56 }),
      adresseDe({ view: "apercu" }), adresseDe({ view: "apercu", projet: 12, invitation: "jeton" })],
  e: ["/app/marches/12/apercu-partenaire", "/app/marches/12/apercu-partenaire/56", "/app/marches/12/apercu-partenaire/0",
      "/app/marches/12/apercu-partenaire/abc"].map(etatDeAdresse),
}));
""")
    assert r["a"] == ["/app/marches/12/apercu-partenaire", "/app/marches/12/apercu-partenaire/56", None,
                      "/app/marches/12/apercu-partenaire"]
    assert r["e"][0] == {"view": "apercu", "projet": 12} and r["e"][1] == {"view": "apercu", "projet": 12, "invitation": 56}
    assert r["e"][2]["inconnue"] and r["e"][3]["inconnue"]
    # De l'aperçu, la page du marché revient telle qu'on l'avait laissée (sans tout recharger).
    assert 'if (v === "aodetail" && this.view === "apercu" && this.ao.project && this.ao.project.id === p.id) {' in JS
    assert "this.apercuOuvrir({ projectId: e.projet, inviteId: e.invitation || null });" in _methode("_appliquerAdresse")
    assert "this._ouvrirAdresse({ view: \"aodetail\", projet: this.apercu.projectId });" in _methode("apercuRetour")
    # Le choix « Aperçu pour » ne crée pas d'entrée d'historique (c'est le même écran).
    assert "this._sansHistorique(() => { a.inviteId = id; });" in _methode("apercuChoisir")
    from app.services.mesure_usage import ECRANS
    assert "apercu" in ECRANS and "apercu" in next(x for x in re.findall(r'vues: \[([^\]]+)\]', JS) if '"sharedao"' in x)


# ═══ 3. « Votre part dans [marché] » : la même barre, dans les deux mises en œuvre ══════════════════════════════════

def test_la_barre_du_partenaire_est_la_meme_fonction_dans_les_deux_espaces():
    assert _fonction(JS, "barrePartenaire") == _fonction(INV, "barrePartenaire")
    assert "class=\"mk-etapes pa-barre\"" in zone(HTML, "partage-barre") and "mk-etapes pa-barre pa-n" in INV
    assert zone(HTML, "partage-barre") in PARTAGE
    # Le stepper des 5 étapes du groupement a quitté les deux espaces.
    for ancien in ("gstep", "renderEtapes", "cv-steps", "grpSteps"):
        assert ancien not in PARTAGE and ancien not in INV, ancien
    # Même apparence que la barre du chef de file ; 3 colonnes quand il y a 3 étapes.
    assert ".pa-barre.pa-n3 { grid-template-columns:repeat(3, minmax(0,1fr)); }" in CSS


def test_la_barre_du_partenaire_sous_node():
    r = _node(_fonction(JS, "barrePartenaire") + """
const cas = {
  arrivee: {},
  minimal: { apercuMinimal: true },
  brouillon: { partStatut: "draft" },
  soumise: { partStatut: "submitted" },
  a_valider: { partStatut: "submitted", conventionStatut: "a_signer", signature: "pending" },
  valide: { partStatut: "submitted", conventionStatut: "a_signer", signature: "signed" },
  perimee: { partStatut: "submitted", conventionStatut: "perimee", signature: "perimee" },
  depose: { groupement: "depose" },
  sous_traitant: { role: "sous_traitant", partStatut: "submitted" },
  lecture: { part: false },
};
const out = {};
for (const k of Object.keys(cas)) out[k] = barrePartenaire(cas[k]).map(s => [s.k, s.statut, s.courante]);
console.log(JSON.stringify(out));
""")
    L = ["accepter", "part", "accord", "depose"]
    assert [x[0] for x in r["arrivee"]] == L
    assert r["arrivee"] == [["accepter", "Terminé", False], ["part", "En cours", True], ["accord", "À faire", False],
                            ["depose", "À faire", False]]
    assert r["minimal"][0] == ["accepter", "En cours", True] and r["minimal"][1][1] == "À faire"
    assert r["brouillon"] == r["arrivee"]
    assert r["soumise"][1] == ["part", "Terminé", False] and r["soumise"][2] == ["accord", "En cours", True]
    assert r["a_valider"] == r["soumise"]
    assert r["valide"][2] == ["accord", "Terminé", False] and r["valide"][3] == ["depose", "En cours", True]
    assert r["perimee"][2] == ["accord", "En cours", True]                 # à revalider
    assert all(s[1] == "Terminé" and not s[2] for s in r["depose"])
    assert [x[0] for x in r["sous_traitant"]] == ["accepter", "part", "depose"] and r["sous_traitant"][2][2] is True
    # Relecture de la vague 2b : un lien en lecture seule ne dépose rien et ne signe jamais la convention (il ne peut
    # pas soumettre de part, sans laquelle la convention ne se génère pas) — ni « Ma part » ni « Donner mon accord ».
    assert [x[0] for x in r["lecture"]] == ["accepter", "depose"]


def test_le_dossier_partage_se_reduit_a_votre_part_et_garde_ses_fonctions():
    entete = zone(HTML, "partage-entete")
    assert '<h2 class="pa-titre"><span>Votre part dans</span> « {{ sharedAo.project.name }} »</h2>' in entete
    assert "<span>Chef de file :</span> <b>{{ sharedAo.mandataire }}</b>" in entete and "Partagé par" not in entete
    barre = zone(HTML, "partage-barre")
    assert 'v-for="s in sharedBarre()"' in barre and '@click="sharedBarreAller(s.k)"' in barre
    assert 'type="button"' in barre and ":aria-current=\"s.courante?'step':null\"" in barre and 'aria-label="Étapes de votre part"' in barre
    corps = _methode("sharedBarre")
    for lu in ("s.role", "s.canContribute", "s.status", "cv.status", "ms.status", "this.sfmState().state"):
        assert lu in corps, lu
    # Les ancres mènent aux blocs : l'en-tête, ma part, la convention.
    assert 'ref="sharedEntete"' in entete and 'ref="sharedPart"' in zone(HTML, "partage-ma-part")
    assert 'ref="sharedConv"' in zone(HTML, "partage-convention")
    # Toutes les fonctions du partenaire restent : part, prix, pièces, coffre-fort, tableau de prix, rédaction,
    # convention et accord, journal vérifiable, déclin.
    for z in ("partage-grille", "partage-pourquoi", "partage-convention", "partage-redaction", "partage-pieces",
              "partage-ma-part", "partage-tableau-prix", "partage-coffre-croise", "partage-journal"):
        assert zone(HTML, z) in PARTAGE, z
    for appel in ("sharedSave()", "sharedSubmit()", "sharedUnlock()", "sharedLostCode()", "sharedConvValider()",
                  "sharedJournalVerify()", "sharedDecline()", "sharedVaultOpen()", "sharedDpgfOpen()", "sharedUpload"):
        assert appel in PARTAGE, appel
    assert "<sources-publiques" in PARTAGE and "<redaction-partenaire" in PARTAGE


def test_l_espace_sans_compte_se_reduit_a_sa_part_avec_un_seul_encart():
    # Un seul écran : ni menu (ni à cadenas, ni « Projets à venir »), ni recherche de marchés, ni bouton d'en-tête.
    assert '<aside class="side">' not in INV and 'class="nav-item"' not in INV
    for parti in ("renderBlocked", "renderSourcing", "nav-amont", "/search", "est réservé aux membres", "data-view"):
        assert parti not in INV, parti
    assert 'Votre part dans « ${esc(p.name || "Marché")} »' in INV and '<h1 class="pa-titre">' in INV
    assert "BARRE.el = $(`<nav class=\"mk-etapes pa-barre\" aria-label=\"Étapes de votre part\"></nav>`);" in INV
    # La barre suit la part et la convention.
    assert "BARRE.partStatut = s || \"\"; renderBarre();" in INV and "renderBarre();     // « Donner mon accord »" in INV
    # Même ordre que le dossier partagé de l'application : en-tête et faits, barre, grille, « Pourquoi vous » (sa carte).
    mon = _fonction(INV, "renderMonAO")
    assert (mon.index("if (dl.children.length) head.appendChild(dl);") < mon.index("root.appendChild(head);")
            < mon.index("root.appendChild(BARRE.el)") < mon.index("renderGrille(grille)")
            < mon.index("renderForMember(pq, d.for_member, d)") < mon.index("const cvCard"))
    assert "renderForMember(head" not in INV and ".g-pourquoi > .g-sec:first-child" in INV
    app = PARTAGE
    assert app.index('data-test="partage-barre"') < app.index('data-test="partage-grille"') < app.index('data-test="partage-pourquoi"')
    # Un seul encart « Créer mon compte », au texte juste ; la durée de l'essai vient du serveur.
    compte = _fonction(INV, "renderCompte")
    assert INV.count('href="/app?inscription"') == 1 and 'href="/app?inscription"' in compte
    assert compte.count("Créer mon compte") == 2                     # le titre de l'encart et son bouton
    assert "Votre part à ce marché ne demande pas de compte." in compte
    assert "Essai gratuit de ${esc(ESSAI_JOURS)} jours, sans carte bancaire." in compte
    assert "if (!DATA || DATA.apercu_minimal || MY_TOKEN) return;" in compte
    assert "30 jours" not in INV and "essai_jours" in INV and "c.essai_jours" in INV
    assert "renderCompte();     // après la part et le journal" in INV


def test_la_duree_de_l_essai_est_celle_du_serveur(client):
    from app.core.quota import TRIAL_DAYS
    assert client.get("/api/public-config").json()["essai_jours"] == TRIAL_DAYS


def test_l_espace_sans_compte_garde_toutes_les_fonctions_du_partenaire():
    for present in (
        "renderContribution(d)", "Prix de vente de votre partie (€ HT)", "/contribution/piece", "Ajouter une pièce",
        "window.AdjugoRedactionPartenaire.mount(rpHost", "verifyIdentity(", "CR.encrypt(", "Déverrouiller avec mon code",
        "J'ai perdu mon code", "loadConvention()", "cvAccordBox(d, flash)", "Vérifier mon journal", "renderDpgf(dpApi)",
        "Décliner l'invitation", "/claim", "Accepter depuis mon compte", "Ouvrir dans mon Adjugo", "reloadCoffre()",
        "Soumettre au chef de file", "Enregistrer le brouillon", "SPX.mount(spHost",
    ):
        assert present in INV, present
    # Entretien et dépôt de documents par lien : dans l'écran de rédaction du partenaire, monté tel quel.
    rp = (STATIC / "redaction-partenaire.js").read_text(encoding="utf-8")
    assert "entretien" in rp.lower() and "/documents" in rp


def test_vocabulaire_et_textes_justes():
    # « partenaire », jamais « co-traitant » ni « consortium » ; aucun mot banni ; zéro émoji ; « vérifié » absent.
    textes = [t for _l, t in textes_html(INV)]
    textes += [t for _l, t in textes_html(APERCU)] + [t for _l, t in textes_html(zone(HTML, "partage-entete"))]
    textes += [t for _l, t in textes_html(zone(HTML, "partage-barre"))] + [t for _l, t in textes_html(zone(HTML, "marche-apercu"))]
    for nom in ("barrePartenaire", "renderBarre", "renderCompte"):
        textes += [t for _l, t in chaines_js(_fonction(INV, nom))]
    for m in ("apercuRaison", "paDelai", "apercuCharger"):
        textes += [t for _l, t in chaines_js(_methode(m))]
    fautes = [t for t in textes if mots_bannis(t)]
    assert not fautes, fautes
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    assert not [t for t in textes if emoji.search(t)]
    neufs = APERCU + _fonction(INV, "renderCompte") + _fonction(INV, "barrePartenaire")
    assert "vérifié" not in neufs and "Vérifié" not in neufs
    # Une bulle (i) explique l'aperçu ; l'aperçu promet ce que le serveur tient (aucune fonction absente).
    # Relecture de la vague 2b : « ni la part des autres partenaires » était faux (une fois la convention générée, chaque
    # signataire y lit la partie et le prix de vente de chacun) ; la bulle dit ce qui est vrai.
    assert APERCU.count('class="tip"') == 1 and "Jamais le détail de votre chiffrage, ni les pièces des autres partenaires." in APERCU
    assert "ni la part des autres partenaires" not in APERCU


def test_traductions_des_libelles_de_l_espace_partenaire():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    for fr in ("Votre part", "Votre part dans", "Chef de file :", "Ce que verra votre partenaire", "Accepter", "Ma part",
               "Donner mon accord", "Déposé par le chef de file", "Voir ce que verra votre partenaire", "Retour au marché",
               "Revenir à l'invitation", "Aperçu pour", "Un partenaire pas encore invité", "Ce qui est attendu de vous",
               "Son écran, en lecture", "Le marché d'une autre entreprise, où vous apportez votre part",
               "Son écran tel qu'il le verra, en lecture : rien de plus que ce qu'Adjugo lui montre"):
        assert d["nl"].get(fr) and d["es"].get(fr), fr


def test_a_375_px_et_accessibilite_de_base():
    # Barre : la règle du téléphone de .mk-etapes s'applique (colonne : numéro, mot, statut) ; libellés coupés au besoin.
    i = CSS.index("@media (max-width:520px) {\n  .mk-etapes")
    assert ".mk-et { flex-direction:column;" in CSS[i:i + 300]
    assert ".pa-barre .mk-et > span:nth-child(2) { text-align:center; overflow-wrap:anywhere; }" in CSS
    assert ".pa-titre {" in CSS and "overflow-wrap:anywhere" in CSS[CSS.index(".pa-titre {"):CSS.index(".pa-titre {") + 200]
    assert "@media (max-width:640px){ .g-main { padding:14px 16px 48px; }" in INV       # 16 px de marge sur téléphone
    # L'aperçu : une région nommée, un choix étiqueté, une barre en liste (lecture seule, pas de faux boutons).
    assert 'role="region" aria-label="Écran du partenaire, en lecture"' in APERCU
    assert '<label for="ap-pour">Aperçu pour</label>' in APERCU and 'id="ap-pour"' in APERCU
    assert '<ol class="mk-etapes pa-barre"' in APERCU and "<button" not in APERCU[APERCU.index('<ol class="mk-etapes pa-barre"'):APERCU.index("</ol>")]
    assert 'aria-label="Étapes de sa part"' in APERCU
    # Les deux écrans contiennent leurs éléments positionnés (textes pour lecteur d'écran de la barre) : rien n'allonge
    # la page entière sous la zone qui défile (vérifié dans un navigateur réel, docs/REORGANISATION_V2B.md, B3).
    assert PARTAGE.startswith('<section data-test="vue-sharedao" class="pa-vue"') and ".pa-vue { position:relative; }" in CSS
    # Les libellés du partenaire, plus longs : chaque étape en colonne, à toutes les largeurs.
    assert ".pa-barre .mk-et { position:relative; flex-direction:column;" in CSS


def test_les_reperes_du_chantier():
    poses = noms(HTML)
    for n in ("partage-barre", "marche-apercu", "vue-apercu-partenaire", "apercu-choix", "apercu-sans-acces",
              "apercu-ecran", "apercu-attendu", "apercu-offre"):
        assert poses.count(n) == 1, n
