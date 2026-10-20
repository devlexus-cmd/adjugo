"""
Réorganisation de l'interface — vague 2a, chantier A2 « Mes marchés et invitations ». Contrat :
docs/REORGANISATION_V2A.md, section A2 ; étude « organisation du logiciel », § 5.3, 8, 9 (vague 2a) et 11 (décisions 7, 8,
9, 10, 11, 18).

  1. Mes marchés en LISTE FILTRABLE (Tous · Je pilote · Où je suis partenaire · À plusieurs), groupée par statut : les vues
     « shared » et « consortiums » et l'onglet « Invitations reçues » du Réseau y fondent, SANS rien montrer de plus que
     ce que chaque vue montrait (mêmes réponses du serveur) ; « Devis et factures » et « Bilan » sont des onglets ;
  2. UNE SEULE fenêtre d'invitation, trois cas (réseau : Adjugo envoie, adresse masquée ; partenaire connu : Adjugo
     envoie à l'email donné ; registre : la PME copie le lien) ; UN SEUL composant « Qui me complète ? » (réseau Adjugo,
     mes partenaires, entreprises de la zone, chacun compté) ;
  3. UNE SEULE liste « Prêt à déposer », avec un calcul pour l'ENTREPRISE SEULE (prix, dossier, formulaires, pièces,
     attestations : jamais un faux manque de groupement) ; UN SEUL « Figer l'offre ».

Aucun appel réseau réel (registres simulés, repli SIRENE simulé, emails coupés) ; les fonctions pures sous Node.
"""
import io
import json
import pathlib
import re
import shutil
import subprocess
import uuid
from datetime import date, timedelta

import pytest

from tests.test_reseau_partenaires import _db, _org, _project, _publish, mails, reg  # noqa: F401 (fixtures)
from tests.textes_visibles import mots_bannis, textes_html
from tests.zones import noms, zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
CARNET = (STATIC / "carnet-notes.js").read_text(encoding="utf-8")
PAGE = zone(HTML, "vue-aodetail")
LISTE = zone(HTML, "vue-pipeline")
FENETRE = zone(HTML, "fenetre-invitation")
QMC = zone(HTML, "marche-qui-me-complete")
PRET = zone(HTML, "marche-pret-a-deposer")


def _sans_commentaires(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _fonction(nom):
    i = JS.index(f"function {nom}(")
    return JS[i:JS.index("\n}\n", i) + 3]


def _methode(nom):
    """Le texte d'une méthode de l'application (« nom(…) {» … jusqu'à la méthode suivante)."""
    m = re.search(r"\n    (?:async )?" + re.escape(nom) + r"\([^)]*\) \{", JS)
    assert m, nom
    i = m.start() + 1
    j = re.search(r"\n    (?:async )?[A-Za-z_$][\w$]*\([^)]*\) \{|\n    // ", JS[i + 4:])
    return JS[i:i + 4 + j.start()].rstrip().rstrip(",") + ","


def _obj(*noms_, extra=""):
    return "const o = {\n" + "\n".join(_methode(n) for n in noms_) + "\n};\n" + extra


# ═══ 1. Mes marchés : une liste filtrable ════════════════════════════════════════════════════════════════════════════

def test_mes_marches_une_liste_filtrable_et_les_anciennes_vues_fondues():
    poses = noms(HTML)
    for ancien in ("vue-shared", "vue-consortiums", "reseau-recues"):
        assert ancien not in poses, ancien
    for nouveau in ("mes-marches-filtres", "mes-marches-invitations", "mes-marches-liste", "mes-marches-plusieurs",
                    "mes-marches-partenaire", "vue-bilan", "bilan-gagne-perdu", "bilan-carnet"):
        assert nouveau in poses, nouveau
    # Les filtres d'abord, puis les invitations à traiter, puis la liste groupée par statut.
    pos = [LISTE.index(zone(HTML, n)) for n in ("mes-marches-filtres", "mes-marches-invitations", "mes-marches-liste")]
    assert pos == sorted(pos)
    filtres = zone(HTML, "mes-marches-filtres")
    assert 'v-for="f in mmFiltres()"' in filtres and '@click="mmFiltrer(f.k)"' in filtres and ":aria-pressed=" in filtres
    assert 'v-for="g in mmGroupes()"' in zone(HTML, "mes-marches-liste") and "statusLabel(g.k)" in LISTE
    # Plus d'onglet « Invitations reçues » dans le Réseau Adjugo (elles se traitent dans Mes marchés).
    assert "Invitations reçues" not in _sans_commentaires(zone(HTML, "vue-reseau"))
    # Mes marchés = Marchés · Devis et factures · Bilan.
    i = JS.index('  { k: "marches", label: "Mes marchés"')
    bloc = JS[i:JS.index("] },", i)]
    assert re.findall(r'label: "([^"]+)"', bloc) == ["Mes marchés", "Marchés", "Devis et factures", "Bilan"]
    assert 'pastille: "partenaire"' in bloc and '{ view: "bilan", label: "Bilan", ic: "chart-column"' in bloc


def test_liste_mes_marches_filtres_et_groupes_sous_node():
    script = _fonction("listeMesMarches") + _fonction("statutPartenaire") + _fonction("invitationsATraiter") + """
const MM_FILTRES = ["tous", "pilote", "partenaire", "plusieurs"];
const c = JSON.parse(process.argv[1]), out = {};
const court = gs => gs.map(g => [g.k, g.pilotes.map(p => p.id), g.partenaires.map(s => s.token)]);
for (const f of ["tous", "pilote", "partenaire", "plusieurs", "inconnu"]) out[f] = court(listeMesMarches(c.p, c.s, c.cs, f, c.ordre));
out.vide = listeMesMarches(null, null, null, "tous", c.ordre);
out.inv = invitationsATraiter(c.recues, c.s).map(i => i.token);
console.log(JSON.stringify(out));
"""
    cas = {
        "ordre": ["nouveau", "en_cours", "envoye", "gagne", "perdu", "abandonne"],
        "p": [{"id": 1, "status": "en_cours"}, {"id": 2, "status": "nouveau"}, {"id": 3, "status": "envoye"},
              {"id": 4}, {"id": 5, "status": "perdu"}],
        "s": [{"token": "a", "groupement": {"state": "invitation"}}, {"token": "b", "groupement": {"state": "depose"}},
              {"token": "c"}],
        "cs": [{"project_id": 1, "partners": 2}, {"project_id": 3, "partners": 1}, {"project_id": 5, "partners": 0}],
        "recues": [{"token": "a", "statut": "acceptee"}, {"token": "x", "statut": "a_repondre"},
                   {"token": "y", "statut": "acceptee"}, {"token": "z", "statut": "a_repondre", "_declined": True}],
    }
    r = _node(script, json.dumps(cas))
    # Tous : mes marchés et ceux où je suis partenaire, groupés par statut, dans l'ordre des statuts.
    assert r["tous"] == [["nouveau", [2, 4], []], ["en_cours", [1], ["a", "c"]], ["envoye", [3], ["b"]], ["perdu", [5], []]]
    assert r["pilote"] == [["nouveau", [2, 4], []], ["en_cours", [1], []], ["envoye", [3], []], ["perdu", [5], []]]
    assert r["partenaire"] == [["en_cours", [], ["a", "c"]], ["envoye", [], ["b"]]]
    # À plusieurs : mes marchés avec au moins un partenaire invité (pas le 5 : plus aucun), et où je suis partenaire.
    assert r["plusieurs"] == [["en_cours", [1], ["a", "c"]], ["envoye", [3], ["b"]]]
    assert r["inconnu"] == r["tous"] and r["vide"] == []
    # Invitations à traiter : à accepter, déclinées dans cette visite, acceptées seulement si absentes de la liste.
    assert r["inv"] == ["x", "y", "z"]


def test_les_anciennes_vues_menent_aux_filtres_et_restent_mesurees_sous_node():
    script = _obj("go", "_ecranOuvert", "mmFiltrer") + """
o.features = {}; o.fb = { open: false }; o.mesures = []; o.charges = [];
o._ecranOuvert = function (v) { this.mesures.push(v); };
for (const k of ["loadStats", "loadExpiring", "loadConsortiums", "loadNotifs", "loadGrpDash", "noteReorgMarquer", "loadShared",
                 "rnLoadRecues", "loadProjects", "loadContacts", "loadInvoices", "loadDocuments", "loadCotraitants", "loadTrades",
                 "loadAlerts", "loadCountries", "srcPrefillFromProfile", "loadAmont", "kbLoad", "pvLoad", "_pvSourcesCharger",
                 "loadOrg", "loadPlan", "loadAdmin", "rnGo"]) o[k] = function () { o.charges.push(k); };
o.$nextTick = () => {};
const MM_FILTRES = ["tous", "pilote", "partenaire", "plusieurs"];
const res = [];
o.view = "dashboard"; o.mmFiltre = "pilote";
o.go("shared"); res.push([o.view, o.mmFiltre, o.mesures.slice()]);
o.mesures = []; o.view = "dashboard"; o.go("consortiums"); res.push([o.view, o.mmFiltre, o.mesures.slice()]);
o.mesures = []; o.view = "dashboard"; o.go("pipeline"); res.push([o.view, o.mmFiltre, o.mesures.slice()]);
o.mesures = []; o.mmFiltrer("partenaire"); o.mmFiltrer("partenaire"); o.mmFiltrer("pilote"); o.mmFiltrer("nimporte");
res.push([o.mmFiltre, o.mesures.slice()]);
o.charges = []; o.go("pipeline"); res.push(o.charges.slice().sort());
o.charges = []; o.go("bilan"); res.push([o.view, o.charges.slice()]);
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r[0] == ["pipeline", "partenaire", ["pipeline", "shared"]]
    assert r[1] == ["pipeline", "plusieurs", ["pipeline", "consortiums"]]
    assert r[2] == ["pipeline", "tous", ["pipeline"]]                       # le menu remet la liste sur « Tous »
    assert r[3] == ["pilote", ["shared"]]                                   # un filtre inconnu ne change rien
    assert r[4] == ["loadConsortiums", "loadProjects", "loadShared", "rnLoadRecues"]
    assert r[5] == ["bilan", ["loadStats"]]
    # Les anciens écrans restent dans la mesure (comparer avant et après) ; « bilan » est une vue mesurée.
    from app.services.mesure_usage import ECRANS
    assert {"shared", "consortiums", "bilan"} <= ECRANS


# Ce que chaque ancienne vue lisait : la liste réunie n'en lit pas plus (aucune donnée nouvelle à l'écran).
CHAMPS_PARTAGE = {"token", "project", "mandataire", "role", "deadline", "groupement", "redaction", "contribution_status"}
CHAMPS_GROUPEMENT = {"submitted", "partners", "pieces", "deadline"}
CHAMPS_INVITATION = {"token", "project", "mandataire", "role", "lot_propose", "recue_le", "deadline", "_declined", "statut",
                     "statut_label", "peut_accepter", "aide"}


def test_la_liste_ne_lit_que_ce_que_lisaient_les_anciennes_vues():
    s = _sans_commentaires(LISTE)
    assert set(re.findall(r"\bs\.([a-z_]+)", s)) <= CHAMPS_PARTAGE, set(re.findall(r"\bs\.([a-z_]+)", s)) - CHAMPS_PARTAGE
    assert set(re.findall(r"\bcs\.([a-z_]+)", s)) <= CHAMPS_GROUPEMENT
    assert set(re.findall(r"\binv\.([a-z_]+)", s)) <= CHAMPS_INVITATION
    # Côté partenaire : des statuts, jamais un montant ni un score.
    part = zone(HTML, "mes-marches-partenaire")
    for interdit in ("eur(", "prix", "score", "%", "total"):
        assert interdit not in part, interdit
    # Le groupement de la carte « À plusieurs » : les compteurs de Mes groupements, rien d'autre.
    assert "parts reçues {{ cs.submitted }} sur {{ cs.partners }}" in zone(HTML, "mes-marches-plusieurs")


def test_le_partenaire_et_le_chef_de_file_ne_recoivent_rien_de_plus(client, reg, mails):
    """Cloisonnement : les réponses qui nourrissent la liste sont celles d'avant (mêmes champs), une autre entreprise
    n'y lit rien, et un partenaire n'atteint ni le dépôt, ni « Qui me complète ? », ni le groupement du chef de file."""
    chef, part = _org(client, "Breizh Couverture"), _org(client, "Le Gall Électricité")
    pid = _project(client, chef)
    inv = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                      json={"company_name": "Le Gall Électricité", "recipient": part["email"]}).json()
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=part["headers"]).status_code == 200
    partage = client.get("/api/shared", headers=part["headers"]).json()
    assert len(partage) == 1
    assert set(partage[0]) == {"token", "project_id", "project", "mandataire", "role", "can_contribute",
                               "contribution_status", "deadline", "groupement", "redaction"}, sorted(partage[0])
    assert set(partage[0]["groupement"] or {}) <= {"state", "label", "index", "etape", "etapes", "convention_status",
                                                   "a_valider"}
    grp = client.get("/api/consortiums", headers=chef["headers"]).json()
    assert set(grp) == {"consortiums", "active", "partners_total", "submitted_total"}
    assert set(grp["consortiums"][0]) == {"project_id", "project", "status", "deadline", "partners", "submitted",
                                          "pieces", "readiness_pct"}
    # Le partenaire : rien du chef de file en dehors de son dossier partagé.
    assert client.get("/api/consortiums", headers=part["headers"]).json()["consortiums"] == []
    assert all(p["id"] != pid for p in client.get("/api/projects/", headers=part["headers"]).json())
    for url in (f"/api/projects/{pid}/groupement/depot", f"/api/projects/{pid}/partner-matches",
                f"/api/projects/{pid}/invites", f"/api/projects/{pid}/consortium"):
        assert client.get(url, headers=part["headers"]).status_code == 404, url
    assert client.post(f"/api/projects/{pid}/groupement/deposer", headers=part["headers"], json={}).status_code == 404
    # Une troisième entreprise : rien de ce marché.
    tiers = _org(client, "Concurrent SARL")
    assert client.get("/api/shared", headers=tiers["headers"]).json() == []
    assert client.get(f"/api/projects/{pid}/groupement/depot", headers=tiers["headers"]).status_code == 404


# ═══ 2. Bilan, onglet de Mes marchés ══════════════════════════════════════════════════════════════════════════════════

def test_bilan_onglet_de_mes_marches_et_une_ligne_sur_l_accueil():
    bilan = zone(HTML, "bilan-gagne-perdu")
    assert bilan in zone(HTML, "vue-bilan") and bilan not in zone(HTML, "vue-dashboard")
    assert bilan.startswith('<div data-test="bilan-gagne-perdu" v-if="bilanVisible()"')
    # Décision 8 : « N sur M », jamais un taux.
    assert "{{ gagnesSur(stats.by_status && stats.by_status.gagne, stats.decided) }}" in bilan and not re.search(r"\}\}\s*%", bilan)
    assert '<carnet-notes data-test="bilan-carnet" mode="tableau"' in zone(HTML, "vue-bilan")
    # L'accueil : une ligne qui mène au bilan, et seulement les rappels « Demandez vos notes » du carnet.
    ligne = zone(HTML, "accueil-bilan")
    assert ligne.startswith('<div data-test="accueil-bilan" v-if="stats.decided"') and "go('bilan')" in ligne
    assert "Où vous gagnez" not in ligne and "seg-grid" not in ligne
    assert '<carnet-notes data-test="accueil-carnet" mode="rappels"' in zone(HTML, "vue-dashboard")
    assert 'o.mode === "rappels" ? renderRappels()' in CARNET and "function renderRappels()" in CARNET
    assert '"/tableau"' in CARNET and 'o.mode === "tableau" || o.mode === "rappels"' in CARNET


# ═══ 3. Une seule fenêtre d'invitation ════════════════════════════════════════════════════════════════════════════════

def test_une_seule_fenetre_d_invitation_trois_cas():
    assert "marche-inviter-formulaire" not in noms(HTML) and "aoCreateInvite" not in JS and "inviteForm" not in HTML + JS
    bouton = zone(HTML, "marche-inviter")
    assert '@click="aoInviter()"' in bouton and 'aria-haspopup="dialog"' in bouton and ">Inviter un partenaire</button>" in bouton
    assert "aoInviter() { if (this.ao.project) this.inviterOuvrir({ projectId: this.ao.project.id }); }," in JS
    f = _sans_commentaires(FENETRE)
    for cas in ("rinvChoisir('connu')", "rinvChoisir('reseau')", "rinvChoisir('sirene')"):
        assert cas in f, cas
    for libelle in ("Un partenaire que je connais", "Une entreprise du réseau Adjugo", "Une entreprise du registre officiel"):
        assert libelle in f, libelle
    # Le réseau : l'adresse du partenaire n'est jamais affichée (le serveur ne la renvoie pas) ; aucun « recipient ».
    assert "recipient" not in f and "vous verrez l'adresse du partenaire quand il aura accepté" in f
    # L'email n'existe que dans le cas « partenaire connu » : c'est celui que la PME donne elle-même.
    connu = f[f.index('<template v-if="rinv.kind===\'connu\'">'):]
    connu = connu[:connu.index("</template>")]
    assert 'v-model="rinv.email"' in connu and 'type="email"' in connu
    reste = f.replace(connu, "")
    assert "rinv.email" not in reste and 'type="email"' not in reste
    # Toutes les entrées d'invitation passent par la fenêtre (aucune autre création de lien dans la page).
    page = _sans_commentaires(PAGE)
    assert "/invites" not in page
    for appel in re.findall(r'@click="((?:aoGrpInvite|rnInviteOpen|inviterOuvrir|aoPmInviterConnu|aoInviter)\([^"]*\))"', page):
        assert appel.split("(")[0] in ("aoGrpInvite", "rnInviteOpen", "inviterOuvrir", "aoPmInviterConnu", "aoInviter"), appel
    envoi = _methode("rinvSend")
    for route in ('"/reseau/invitations"', '"/invites"', '"/reseau/invitations-sirene"'):
        assert route in envoi, route


def test_qui_invite_dans_quel_cas_sous_node():
    """aoGrpInvite et les cartes de « Qui me complète ? » ouvrent la fenêtre dans le bon cas ; rinvSend appelle la bonne
    route avec le bon corps (et rien d'autre)."""
    script = "globalThis.document = { activeElement: null, querySelector: () => null, body: { contains: () => false } };\n" \
        + _fonction("nomCle") + _obj("aoGrpInvite", "_ficheAnnuaire", "_grpProfileId", "rnInviteOpen", "inviterOuvrir",
                                     "_rinvBase", "_rinvFocusPremier", "_rinvMontrer", "rinvChoisir", "rinvSend", "aoPmInviterConnu",
                                     "rinvBouton", "rinvTitre") + """
o.$nextTick = () => {}; o.view = "aodetail"; o.ao = { project: { id: 7 }, grp: { sim: null, besoins: null }, pm: { d: null } };
o.cotraitants = [{ id: 11, name: "Le Gall Électricité", email: "contact@legall.fr", siret: "12345678900012" }];
o.grpPlan = () => ({ members: [{ name: "Le Gall Électricité", link_id: 33 }] });
o.simPartners = () => []; o.inviteUrl = (i) => "https://x" + i.path; o.notify = () => {}; o.copyInvite = () => {};
o._rnMarkInvited = () => {}; o.rinvClose = () => { o.rinv = null; };
for (const k of ["aoLoadInvites", "aoLoadCotraitants", "aoLoadConsortium", "aoGrpReloadState", "loadCotraitants", "loadConsortiums"]) o[k] = () => {};
o.appels = [];
o.api = async (m, u, b) => { o.appels.push([m, u, b]); return { path: "/invite/t", emailed: !!(b && b.recipient), invitation: { path: "/invite/s", company_name: "Bois SAS" } }; };
const res = {};
(async () => {
  o.aoGrpInvite({ kind: "reseau", profile_id: "p".repeat(32), name: "Réseau SA" }); res.reseau = [o.rinv.kind, o.rinv.profile_id.length];
  o.aoGrpInvite({ kind: "annuaire", id: 11, name: "le gall electricite" });
  res.annuaire = [o.rinv.kind, o.rinv.name, o.rinv.email, o.rinv.link_id, o.rinvBouton()];
  o.aoGrpInvite({ kind: "sirene", siret: "98765432100015", name: "Bois SAS" }); res.sirene = [o.rinv.kind, o.rinv.siret, o.rinvBouton()];
  o.aoGrpInvite({ kind: "saisi", name: "Inconnue SARL" }); res.saisi = [o.rinv.kind, o.rinv.name, o.rinv.email, o.rinvBouton()];
  o.inviterOuvrir({ projectId: 7 }); res.choix = [o.rinv.kind, o.rinvTitre()];
  o.rinvChoisir("sirene"); res.choixSirene = [o.rinv.kind, o.rinv.siretSaisi, o.rinv.depuisChoix];
  o.rinv.siret = "123"; await o.rinvSend(); res.siretCourt = [o.rinv.err, o.appels.length];
  o.inviterOuvrir({ projectId: 7 }); o.rinvChoisir("connu"); o.rinv.name = "Inconnue SARL"; o.rinv.email = "pas-un-email";
  await o.rinvSend(); res.emailFaux = [o.rinv.err, o.appels.length];
  o.rinv.email = "a@b.fr"; await o.rinvSend(); res.connu = o.appels.pop();
  o.aoGrpInvite({ kind: "annuaire", id: 11, name: "Le Gall Électricité" }); await o.rinvSend(); res.annuaireEnvoi = o.appels.pop();
  o.aoGrpInvite({ kind: "sirene", siret: "98765432100015", name: "Bois SAS" }); await o.rinvSend(); res.sireneEnvoi = o.appels.pop();
  o.rnInviteOpen({ profile_id: "q".repeat(32), name: "Réseau SA" }); await o.rinvSend(); res.reseauEnvoi = o.appels.pop();
  o.aoPmInviterConnu({ cotraitant_id: 11, name: "Le Gall Électricité", email: "contact@legall.fr" }); res.pm = [o.rinv.kind, o.rinv.email];
  console.log(JSON.stringify(res));
})();
"""
    r = _node(script)
    assert r["reseau"] == ["reseau", 32]
    assert r["annuaire"] == ["connu", "Le Gall Électricité", "contact@legall.fr", 33, "Envoyer l'invitation"]
    assert r["sirene"] == ["sirene", "98765432100015", "Créer le lien"]
    assert r["saisi"] == ["connu", "Inconnue SARL", "", "Créer le lien"]
    assert r["choix"] == ["choix", "Inviter un partenaire"]
    assert r["choixSirene"] == ["sirene", True, True]
    assert r["siretCourt"] == ["Un SIRET à 14 chiffres est requis.", 0]
    assert r["emailFaux"] == ["Cette adresse email n'est pas valide.", 0]
    assert r["connu"][:2] == ["POST", "/api/projects/7/invites"]
    assert r["connu"][2] == {"company_name": "Inconnue SARL", "recipient": "a@b.fr", "role": "cotraitant", "can_view_docs": True,
                             "can_contribute": True, "expires_days": 30}
    assert r["annuaireEnvoi"][2]["link_id"] == 33 and r["annuaireEnvoi"][2]["recipient"] == "contact@legall.fr"
    assert r["sireneEnvoi"][:2] == ["POST", "/api/projects/7/reseau/invitations-sirene"]
    assert r["sireneEnvoi"][2]["siret"] == "98765432100015" and "recipient" not in r["sireneEnvoi"][2]
    assert r["reseauEnvoi"][:2] == ["POST", "/api/projects/7/reseau/invitations"]
    assert set(r["reseauEnvoi"][2]) == {"profile_id", "role", "lot", "can_view_docs", "expires_days"}
    assert r["pm"] == ["connu", "contact@legall.fr"]


def test_invitation_d_un_partenaire_connu_par_email_et_par_lien(client, reg, mails):
    """Le cas « partenaire connu » de la fenêtre : la même route qu'avant (POST /invites). Avec un email, Adjugo
    l'envoie ; sans email, un lien à copier. Plafond quotidien et refus de la démo inchangés."""
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    r = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                    json={"company_name": "Le Gall Électricité", "recipient": "contact@legall.fr", "role": "cotraitant",
                          "can_view_docs": True, "can_contribute": True, "expires_days": 30})
    assert r.status_code == 200 and r.json()["emailed"] is True and r.json()["path"].startswith("/invite/")
    assert [m[0] for m in mails] == ["contact@legall.fr"]
    r = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                    json={"company_name": "Bois SAS", "recipient": "", "expires_days": 7})
    assert r.status_code == 200 and r.json()["emailed"] is False and len(mails) == 1


# ═══ 4. Un seul « Qui me complète ? » ══════════════════════════════════════════════════════════════════════════════════

def test_un_seul_qui_me_complete_trois_reservoirs_comptes_puis_la_zone():
    q = _sans_commentaires(QMC)
    pos = [q.index(f'data-test="{n}"') for n in ("complete-reseau", "complete-mes-partenaires", "complete-zone",
                                                  "complete-recherche")]
    assert pos == sorted(pos), "Réseau Adjugo · Mes partenaires · Entreprises de la zone, puis la recherche"
    for n in ("complete-reseau", "complete-mes-partenaires", "complete-zone"):
        assert 'class="pm-n"' in zone(HTML, n), n                                  # chacun avec son compte
    assert "l.n_correspondants" in zone(HTML, "complete-reseau") and "l.n_mes_partenaires" in zone(HTML, "complete-mes-partenaires")
    recherche = zone(HTML, "complete-recherche")
    assert "aoSearchSt()" in recherche and "aoAttachSt(c)" in recherche and "Ajouter un sous-traitant (DC4)" in recherche
    assert "rnInviteOpen({ siret: c.siret, name: c.nom, city: c.ville })" in recherche
    # « Membres et sous-traitants » n'a plus sa propre recherche : elle mène à celle de « Qui me complète ? ».
    membres = zone(HTML, "marche-partenaires")
    assert "aoSearchSt" not in membres and "ao.st." not in membres and '@click="aoChercherEntreprise()"' in membres
    # Le composant est visible même sans analyse (la recherche dans la zone marche sans dossier), une seule fois.
    assert zone(HTML, "marche-qui-me-complete").startswith('<div data-test="marche-qui-me-complete" class="card rn-pm" ref="pmCard"')
    assert PAGE.count('ref="pmCard"') == 1 and "rnDiscover(" not in QMC
    assert "↗" not in QMC


def test_qui_me_complete_propose_mon_annuaire_et_jamais_celui_d_un_autre(client, reg, mails):
    chef, autre = _org(client, "Breizh Couverture"), _org(client, "Concurrent SARL")
    for org, nom, email in ((chef, "Le Gall Électricité", "contact@legall.fr"), (autre, "Kerjean Électricité", "k@kerjean.fr")):
        r = client.post("/api/cotraitants/", headers=org["headers"],
                        json={"name": nom, "specialites": "Électricité générale", "email": email, "city": "Quimper",
                              "departement": "29", "siret": "4" * 9 + "00012" if org is autre else "5" * 9 + "00012"})
        assert r.status_code == 200, r.text
    pid = _project(client, chef, allotissement="Lot 1 : Couverture ; Lot 2 : Électricité")
    d = client.get(f"/api/projects/{pid}/partner-matches", headers=chef["headers"]).json()
    lot = next(l for l in d["lots"] if l["num"] == "2")
    assert d["reseau_visible"] is False                                 # compte non publié : rien du réseau…
    assert lot["n_mes_partenaires"] == 1 and [m["name"] for m in lot["mes_partenaires"]] == ["Le Gall Électricité"]
    m = lot["mes_partenaires"][0]
    assert m["email"] == "contact@legall.fr" and m["deja_invite"] is False   # …mais son propre annuaire
    assert set(m) == {"cotraitant_id", "name", "siret", "siren", "city", "departement", "specialites", "email", "reseau",
                      "deja_invite"}
    assert "Kerjean" not in json.dumps(d)
    # Invité : « Déjà invité » ; l'autre entreprise ne voit jamais l'annuaire du chef de file.
    client.post(f"/api/projects/{pid}/invites", headers=chef["headers"], json={"company_name": "Le Gall Électricité"})
    d = client.get(f"/api/projects/{pid}/partner-matches", headers=chef["headers"]).json()
    assert next(l for l in d["lots"] if l["num"] == "2")["mes_partenaires"][0]["deja_invite"] is True
    assert client.get(f"/api/projects/{pid}/partner-matches", headers=autre["headers"]).status_code == 404
    pid2 = _project(client, autre, allotissement="Lot 1 : Couverture ; Lot 2 : Électricité")
    d2 = client.get(f"/api/projects/{pid2}/partner-matches", headers=autre["headers"]).json()
    assert "Le Gall" not in json.dumps(d2) and "legall" not in json.dumps(d2)


def test_une_entreprise_du_reseau_n_est_pas_repetee_dans_mes_partenaires(client, reg, mails):
    """Une entreprise du réseau montrée pour la partie n'est pas repétée dans « Mes partenaires » : on l'invite par le
    réseau, son adresse reste masquée."""
    # Un métier qu'aucun autre test ne publie (le réseau de la suite est partagé) : seul ce profil y répond.
    nom = "Imprimerie Kerne " + uuid.uuid4().hex[:6]
    chef, imp = _org(client, "Breizh Couverture"), _org(client, nom)
    _publish(client, reg, chef, metiers=("couverture",))
    _publish(client, reg, imp, metiers=("imprimerie",))
    r = client.post("/api/cotraitants/", headers=chef["headers"],
                    json={"name": nom, "specialites": "Imprimerie", "siret": imp["siren"] + "00012", "email": "k@kerne.fr"})
    assert r.status_code == 200, r.text
    pid = _project(client, chef, allotissement="Lot 1 : Couverture ; Lot 2 : Imprimerie")
    d = client.get(f"/api/projects/{pid}/partner-matches", headers=chef["headers"]).json()
    lot = next(l for l in d["lots"] if l["num"] == "2")
    assert [c["name"].lower() for c in lot["reseau"]] == [nom.lower()]
    assert lot["mes_partenaires"] == [] and lot["n_mes_partenaires"] == 0
    assert imp["email"] not in json.dumps(d) and "k@kerne.fr" not in json.dumps(d)


# ═══ 5. Une seule liste « Prêt à déposer », un calcul pour l'entreprise seule ═════════════════════════════════════════

GROUPEMENT = ("Part de", "partenaire", "Partenaire", "membre", "Convention", "convention", "groupement")


def _depot(client, h, pid):
    r = client.get(f"/api/projects/{pid}/groupement/depot", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["pret"]


def _set(pid, **fields):
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        for k, v in fields.items():
            setattr(p, k, v)
        db.commit()
    finally:
        db.close()


def test_pret_a_deposer_d_une_entreprise_seule_sans_faux_manque_de_groupement(client, reg, mails):
    from app.models import Company, Document, User
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    p = _depot(client, chef["headers"], pid)
    assert p["pour"] == "seul" and list(p["checks"]) == ["prix", "dossier", "formulaires", "pieces", "attestations"]
    assert p["n_total"] == 5 and p["pret"] is False and set(p["manques_par_controle"]) == set(p["checks"])
    assert not [m for m in p["manques"] if any(w in m for w in GROUPEMENT)], p["manques"]
    assert p["libelles"]["prix"] == "Votre prix estimé" and "%" not in json.dumps(p["libelles"])
    assert p["manques_par_controle"]["formulaires"] == ["Formulaire DC1 à préparer : « Préparer mes documents »",
                                                        "Formulaire DC2 à préparer : « Préparer mes documents »",
                                                        "Formulaire ATTRI1 à préparer : « Préparer mes documents »"]
    assert "Extrait Kbis ou équivalent : à ajouter dans Mes documents" in p["manques_par_controle"]["pieces"]
    # Le prix estimé, puis les formulaires officiels préparés : leurs contrôles passent.
    _set(pid, estimate={"total_ht": 48000.0, "lignes": []})
    db = _db()
    try:
        u = db.query(User).filter(User.id == chef["id"]).first()
        c = db.query(Company).filter(Company.user_id == u.id).first()
        c.name, c.representant_legal, c.address = "Breizh Couverture", "Eliot Viegas", "1 rue du Port"
        db.commit()
    finally:
        db.close()
    for dt in ("dc1", "dc2", "attri1"):
        assert client.post(f"/api/cerfa/{pid}/{dt}", headers=chef["headers"]).status_code == 200, dt
    p = _depot(client, chef["headers"], pid)
    assert p["checks"]["prix"] is True and p["checks"]["formulaires"] is True and p["n_ok"] >= 2
    # Une attestation qui expire AVANT la date limite : un manque de « Vos attestations », jamais d'un membre.
    db = _db()
    try:
        db.add(Document(user_id=chef["id"], name="attestation_urssaf.pdf", file_key="x/urssaf.pdf",
                        expiration_date=date.today() + timedelta(days=5)))
        db.commit()
    finally:
        db.close()
    p = _depot(client, chef["headers"], pid)
    assert p["checks"]["attestations"] is False
    assert [m for m in p["manques_par_controle"]["attestations"] if "expire avant la date limite" in m]
    # « Marquer déposé » : avertir, pas bloquer — 409 avec la liste de l'entreprise seule, puis quand même.
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=chef["headers"], json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pas_pret"
    assert not [m for m in r.json()["detail"]["manques"] if any(w in m for w in GROUPEMENT)]
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=chef["headers"], json={"confirmer": True})
    assert r.status_code == 200 and r.json()["status"] == "envoye"
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=chef["headers"]).json()
    assert d["depose"] is True and d["pret"]["pour"] == "seul"


def test_pret_a_deposer_le_dossier_de_presentation_seulement_s_il_est_demande():
    from app.services import groupement_members as gm
    assert [k for k, _l in gm.DEPOT_CHECKS_SEUL] == ["prix", "dossier", "formulaires", "pieces", "attestations"]
    assert gm.FORMULAIRES_FR == ("dc1", "dc2", "attri1") and gm.FORMULAIRES_HORS_FR == ("dume",)
    src = (ROOT / "app/services/groupement_members.py").read_text(encoding="utf-8")
    assert 'cles = [k for k, _label in DEPOT_CHECKS_SEUL if k != "dossier" or controle_dossier]' in src


def test_pret_a_deposer_d_un_groupement_inchange(client, reg, mails):
    chef = _org(client, "Breizh Couverture")
    pid = _project(client, chef)
    client.post(f"/api/projects/{pid}/invites", headers=chef["headers"], json={"company_name": "Le Gall Électricité"})
    p = _depot(client, chef["headers"], pid)
    from app.services.groupement_members import DEPOT_CHECKS
    assert p["pour"] == "groupement" and list(p["checks"]) == [k for k, _l in DEPOT_CHECKS] and p["n_total"] == 4
    assert set(p["manques_par_controle"]) == set(p["checks"])
    ranges = [m for ms in p["manques_par_controle"].values() for m in ms]
    assert sorted(ranges) == sorted(p["manques"]), "chaque manque sous un seul contrôle"
    assert "Part de Le Gall Électricité pas encore soumise" in p["manques_par_controle"]["parts_soumises"]


def test_le_dossier_prepare_horodate_les_formulaires_aussi_pour_une_entreprise_seule(client, auth):
    from tests.test_redaction_socle0 import ANALYSIS, _company, _project as _projet, _set_analysis
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _set_analysis(pid, ANALYSIS)
    assert _depot(client, h, pid)["checks"]["formulaires"] is False
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    p = _depot(client, h, pid)
    assert p["pour"] == "seul" and p["checks"]["formulaires"] is True, p["manques_par_controle"]


def test_une_seule_liste_pret_a_deposer_dans_deposer():
    assert "marche-avant-depot" not in noms(HTML)
    assert PRET in zone(HTML, "marche-deposer") and PRET.startswith('<section data-test="marche-pret-a-deposer" class="conv-pret"')
    assert "depotShown() && " not in PRET                                       # pour tous, seul ou à plusieurs
    assert "depotShown() { return !!(this.ao.project && this.ao.project.id); }," in JS
    # Ce que vous vérifiez vous-même entre dans la même liste (gardé sur cet appareil).
    assert 'v-for="(st,i) in predepotSteps"' in PRET and "predepotDone }} sur {{ predepotSteps.length }}" in PRET
    assert "À vérifier vous-même" in PRET and "Marquer déposé" in PRET and "Avant de déposer sur la plateforme du client" not in HTML
    # Une seule ligne « Exporter le dossier complet » visible à la fois.
    assert 'v-if="!aoExportDansPret()"' in zone(HTML, "marche-export")


def test_les_controles_et_leur_action_sous_node():
    script = _obj("convPretChecks", "convPretRest", "depotPret", "convPret", "depotPourGroupement", "_convPretGroup") + """
o.ao = { depot: { d: null }, grp: { state: null }, conv: { d: null }, share: {} };
o.aoPendingRelancables = () => [];
const seul = { pour: "seul", checks: { prix: false, formulaires: true, pieces: false, attestations: true },
  libelles: { prix: "Votre prix estimé", formulaires: "Formulaires officiels préparés", pieces: "Pièces demandées réunies", attestations: "Vos attestations valides à la date limite" },
  manques: ["Prix à estimer", "Kbis : à ajouter", "Autre chose"], manques_par_controle: { prix: ["Prix à estimer"], pieces: ["Kbis : à ajouter"], formulaires: [], attestations: [] } };
const res = {};
o.ao.depot.d = { pret: seul };
res.seul = o.convPretChecks().map(k => [k.key, k.ok, k.cta, k.manques]); res.seulReste = o.convPretRest(); res.seulG = o.depotPourGroupement();
o.ao.depot.d = { pret: { pour: "groupement", checks: { parts_soumises: false, attestations_ok: true, convention_signee: false, cerfa_generes: false },
  libelles: {}, manques: ["Part de X pas encore soumise", "Convention à faire valider par tous les membres"],
  manques_par_controle: { parts_soumises: ["Part de X pas encore soumise"], attestations_ok: [], convention_signee: ["Convention à faire valider par tous les membres"], cerfa_generes: [] } } };
res.grp = o.convPretChecks().map(k => [k.key, k.ok, k.manques.length]); res.grpG = o.depotPourGroupement();
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r["seul"] == [["prix", False, "Estimer mon prix", ["Prix à estimer"]], ["formulaires", True, "Préparer mes documents", []],
                         ["pieces", False, "Voir les pièces", ["Kbis : à ajouter"]], ["attestations", True, "Mes pièces", []]]
    assert r["seulReste"] == ["Autre chose"] and r["seulG"] is False
    assert r["grp"] == [["parts_soumises", False, 1], ["attestations_ok", True, 0], ["convention_signee", False, 1],
                        ["cerfa_generes", False, 0]] and r["grpG"] is True


def test_la_liste_a_cocher_garde_les_deux_premieres_cases_de_l_ancien_format_sous_node():
    script = _obj("loadPredepot") + """
const store = { "adjugo_predepot_1": JSON.stringify([true, false, true, true]), "adjugo_predepot_2": JSON.stringify([false, true]),
                "adjugo_predepot_3": "pas du json", "adjugo_predepot_4": JSON.stringify([true]) };
globalThis.localStorage = { getItem: k => (k in store ? store[k] : null) };
const res = [];
for (const pid of [1, 2, 3, 4, 5]) { o.loadPredepot(pid); res.push(o.predepot); }
console.log(JSON.stringify(res));
"""
    assert _node(script) == [[True, False], [False, True], [False, False], [False, False], [False, False]]


# ═══ 6. Un seul « Figer l'offre » ══════════════════════════════════════════════════════════════════════════════════════

def test_un_seul_figer_l_offre():
    page = _sans_commentaires(PAGE)
    boutons = re.findall(r"<button\b[^>]*>(?:(?!</button>).)*Figer l'offre(?:(?!</button>).)*</button>", page, re.S)
    assert len(boutons) == 1 and "aoConvAskGenerate()" in boutons[0], boutons
    assert boutons[0] in zone(HTML, "marche-convention")
    offre = zone(HTML, "marche-offre-commune")
    assert "aoFreezeOffer" not in offre and "ao.share.leadTotal" not in offre and "aoConvScroll('convFoot')" in offre
    for absent in ("aoFreezeOffer", "canFreeze", "freezeMissing", "leadTotal"):
        assert absent not in JS + HTML, absent
    assert "Défiger" in offre                                                     # défiger reste possible


# ═══ 7. Textes : les invitations reçues se traitent dans Mes marchés ═══════════════════════════════════════════════════

def test_les_textes_disent_ou_se_traitent_les_invitations():
    reseau = (ROOT / "app/routers/reseau.py").read_text(encoding="utf-8")
    assert "Réseau \"\n                    \"Adjugo › Invitations reçues" not in reseau and "Invitations reçues). L'email" not in reseau
    assert "(Mes marchés, filtre \"\n                    \"« Où je suis partenaire »)" in reseau
    from app.services import atelier_groupement as ag
    assert "dans Mes marchés, filtre « Où je suis partenaire »" in ag.MSG_ESPACE_COMPTE
    invite = (STATIC / "invite.html").read_text(encoding="utf-8")
    assert "Invitations reçues" not in invite and "filtre « Où je suis partenaire »" in invite
    rp = (STATIC / "redaction-partenaire.js").read_text(encoding="utf-8")
    assert "onglet « Où je suis partenaire »" not in rp and rp.count("filtre « Où je suis partenaire »") == 3
    assert "onglet « Où je suis partenaire »" not in HTML + JS
    assert 'r.live = "Invitation acceptée : le dossier est dans Mes marchés, filtre « Où je suis partenaire ».";' in JS


def test_aucun_mot_banni_ni_emoji_dans_les_nouveaux_ecrans():
    for nom in ("vue-pipeline", "vue-bilan", "fenetre-invitation", "marche-qui-me-complete", "marche-pret-a-deposer",
                "marche-offre-commune"):
        textes = [t for _l, t in textes_html(zone(HTML, nom))]
        assert not [t for t in textes if mots_bannis(t)], nom
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", zone(HTML, nom)), nom
    # Boutons : un type déclaré ; bulles (i) au composant existant.
    for nom in ("vue-pipeline", "fenetre-invitation", "marche-qui-me-complete", "marche-pret-a-deposer"):
        z = _sans_commentaires(zone(HTML, nom))
        for m in re.finditer(r"<button\b[^>]*>", z):
            assert 'type="button"' in m.group(0) or ' class="btn primary" @click="rubriqueGo' in m.group(0), m.group(0)[:120]
        assert z.count('class="tip-b" role="tooltip"') == z.count("tip-b"), nom


def test_375_px_les_filtres_et_les_cartes_tiennent():
    assert "@media (max-width:560px) { .mm-filtres { grid-template-columns:repeat(2, minmax(0,1fr)); } }" in CSS
    assert "@media (max-width:560px) { .mm-cartes { grid-template-columns:minmax(0,1fr); } }" in CSS
    assert ".mm-cartes { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));" in CSS
    assert ".kanban" not in CSS and ".shared-recues" not in CSS


# ═══ 8. La démonstration (lien privé, pitchs) ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def vitrine(client):
    from app.core.database import SessionLocal
    from app.services.demo_seed import ensure_demo

    def neuf():
        db = SessionLocal()
        try:
            ensure_demo(db, force=True)
        finally:
            db.close()
    neuf()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    yield {"Authorization": "Bearer " + r.json()["access_token"]}
    neuf()


def test_la_demo_mes_marches_et_pret_a_deposer(client, vitrine):
    projets = client.get("/api/projects/", headers=vitrine).json()
    partages = client.get("/api/shared", headers=vitrine).json()
    grp = client.get("/api/consortiums", headers=vitrine).json()["consortiums"]
    script = _fonction("listeMesMarches") + _fonction("statutPartenaire") + """
const MM_FILTRES = ["tous", "pilote", "partenaire", "plusieurs"];
const c = JSON.parse(process.argv[1]), ordre = ["nouveau", "en_cours", "envoye", "gagne", "perdu", "abandonne"], out = {};
for (const f of MM_FILTRES) out[f] = listeMesMarches(c.p, c.s, c.cs, f, ordre).map(g => [g.k, g.pilotes.map(p => p.name)]);
console.log(JSON.stringify(out));
"""
    r = _node(script, json.dumps({"p": projets, "s": partages, "cs": grp}))
    noms_tous = [n for g in r["tous"] for n in g[1]]
    assert sorted(noms_tous) == sorted(p["name"] for p in projets)
    plus = [n for g in r["plusieurs"] for n in g[1]]
    assert any("Gymnase de Kerhel" in n for n in plus) and not any("Réfection toiture — Groupe scolaire" in n for n in plus)
    assert r["partenaire"] == []
    # « Prêt à déposer » : la toiture (seule) a son propre calcul, sans manque de groupement ; Kerhel reste à 4 contrôles.
    toit = next(p for p in projets if "Réfection toiture — Groupe scolaire Jean Moulin" in p["name"])
    p = _depot(client, vitrine, toit["id"])
    assert p["pour"] == "seul" and not [m for m in p["manques"] if any(w in m for w in GROUPEMENT)], p["manques"]
    kerhel = next(x for x in projets if "Gymnase de Kerhel" in x["name"])
    k = _depot(client, vitrine, kerhel["id"])
    assert k["pour"] == "groupement" and (k["n_ok"], k["n_total"]) == (3, 4)


# ═══ 9. Décision 16 : les nouveaux libellés ont leur néerlandais et leur espagnol ══════════════════════════════════════

NOUVEAUX = ["Tous", "Je pilote", "Bilan", "Voir le bilan", "Invitations à traiter", "Compte-rendu", "Masquer le compte-rendu",
            "Partenaires et pièces", "Part soumise", "Part en brouillon", "Part à compléter",
            "Aucun marché où vous êtes partenaire", "Aucun marché à plusieurs pour l'instant", "Voir tous mes marchés",
            "Aucun marché terminé pour l'instant", "Un partenaire que je connais", "Une entreprise du réseau Adjugo",
            "Une entreprise du registre officiel", "Dans Mes partenaires", "Une autre entreprise", "Entreprise",
            "Email du contact (facultatif)", "SIRET de l'entreprise", "Durée du lien", "Inviter une autre sorte d'entreprise",
            "Inviter sans passer par le registre", "Envoyer l'invitation", "Créer le lien", "Copier le lien",
            "Entreprises de la zone", "Chercher une entreprise de la zone", "Chercher pour cette partie", "Chercher autrement",
            "Votre prix estimé", "Dossier de présentation prêt, sans passage à compléter", "Formulaires officiels préparés",
            "Pièces demandées réunies", "Vos attestations valides à la date limite", "Ouvrir l'atelier", "Voir les pièces",
            "À vérifier vous-même", "Marquer déposé", "Avant de déposer", "Préparer mes documents", "Estimer mon prix",
            "Aller à « Convention et accords »", "Chercher dans « Qui me complète ? »", "Ouvrir l'annuaire du réseau",
            "Inviter par lien"]


def test_traductions_des_libelles_de_mes_marches_et_des_invitations():
    from tests.test_reorganisation_v1_socle import _dico
    d = _dico()
    serveur = (ROOT / "app/services/groupement_members.py").read_text(encoding="utf-8")
    for k in NOUVEAUX:
        assert d["nl"].get(k) and d["es"].get(k), f"« {k} » sans traduction (scripts/i18n_ajouter.py)"
        assert k in HTML or k in JS or k in serveur, f"« {k} » n'est plus affiché : retirez-le de NOUVEAUX"
