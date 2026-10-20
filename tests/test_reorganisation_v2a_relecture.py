"""
Réorganisation de l'interface — vague 2a, relecture (contrat : docs/REORGANISATION_V2A.md, section « Relecture »).

Les dix remarques de la relecture de la vague 2a, chacune reproduite par un test qui échouait sur e66ed55 :
1. Précédent du navigateur avec une fenêtre ouverte : la fenêtre se ferme (et ne fait que se fermer), une confirmation
   n'agit jamais sur un autre écran que le sien (remarques 1 et 9).
2. Deux invitations acceptées sur le même marché : l'adresse, le rechargement, le retour arrière et ?shared= rouvrent
   chacun la sienne ; le jeton ne va jamais dans l'adresse (remarque 2).
3. Un geste (inviter, préparer, décider) ne fait jamais reculer un marché déposé, même depuis une liste ou une page
   plus ancienne ; « Marquer déposé » met à jour Mes marchés (remarque 3).
4. Bascule de la migration c4axeetapes : l'étendue réelle de la panne et la procédure sont écrites (remarque 4).
5. « Prêt à déposer » : un sous-traitant seul ou une convention restée en brouillon sans partenaire ne font pas un
   groupement (remarque 5).
6. Une pièce exigée par le dossier sans mot-clé connu est reconnue sous son nom (remarque 6).
7. Formulaires rangés par « Préparer mes documents » de la production : comptés pour une entreprise seule
   (remarque 7).
8. Atelier ouvert directement : « Retour au marché » puis « Retour » mènent à Mes marchés, sans boucle (remarque 8).
9. Carte « À venir » : la page ne parle ni d'« annonce seule » ni d'un dossier « indispensable » (remarque 10).

Aucun appel réseau : routes de l'API locale, fonctions de app.js exécutées sous Node, base SQLite des tests.
"""
import json
import pathlib
import re
from types import SimpleNamespace

from tests.test_reorganisation_v2a_adresses_etapes import _ADRESSES, _AXE, _HARNAIS, _NAV, _node, tranche
from tests.test_reorganisation_v2a_reunion import _methode
from tests.test_reseau_ecrans import _method
from tests.test_reseau_partenaires import _db, _org, _project, mails, reg  # noqa: F401
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CONTRAT = (ROOT / "docs" / "REORGANISATION_V2A.md").read_text(encoding="utf-8")

_CHAMPS = tranche(JS, "function champsValides(", "function champsValides(")


def _naviguer(scenario, methodes, depart="/app", etat=""):
    """Le navigateur simulé des tests de A1, dont précédent / suivant passent par le VRAI gestionnaire popstate
    (_surRetourNavigateur), avec les méthodes réelles `methodes` en plus de celles de la navigation."""
    extra = [n for n in dict.fromkeys(methodes) if n not in _NAV]
    obj = ("const o = {\n" + ",\n".join([_method(n).rstrip(",") for n in _NAV] + [_methode(n) for n in extra])
           + "\n};\n")
    harnais = _HARNAIS.replace(
        "o._ouvrirAdresse(etatDeAdresse(location.pathname), history.state && history.state.defil);",
        "o._surRetourNavigateur({ state: history.state });")
    assert harnais.count("_surRetourNavigateur") == 2
    doc = 'globalThis.document = { title: "", querySelector() { return { scrollTop: 40 }; } };'
    assert harnais.count(doc) == 1
    harnais = harnais.replace(doc, 'globalThis.document = { title: "", querySelector() { return { scrollTop: 40 }; }, '
                                   'getElementById() { return null; } };')
    script = (_ADRESSES + "\n" + _AXE + "\n" + _CHAMPS + "\n" + obj
              + harnais.replace("DEPART", json.dumps(depart)).replace("GARDE", "{}") + etat + scenario)
    return _node(script)


_FENETRES = """
Object.assign(o, { cdlg: null, rinv: null, modal: null, notifsOpen: false, atl: {}, pv: {}, pvAtl: { open: false },
  discover: { open: false }, fb: { open: false }, $refs: {}, reseau: { tab: "profil", fiche: null },
  pvAtlFermer() { this.pvAtl = { open: false }; } });
"""


# ═══ 1. Précédent du navigateur et fenêtres ouvertes (remarques 1 et 9) ═════════════════════════════════════════

def test_precedent_avec_une_fenetre_ouverte_ne_fait_que_la_fermer():
    r = _naviguer(_FENETRES + """
const res = {};
(async () => {
demarrer(); o.openAo(o.projects[1]); vider(); res.ouvert = etat();
// « Écarter ce marché ? » sur le marché 9, puis précédent : la fenêtre se ferme, l'écran reste le marché 9.
const reponse = o.demander({ title: "Écarter ce marché ?", ok: "Écarter" }); vider();
res.ouverte = !!o.cdlg;
history.back(); res.b1 = Object.assign(etat(), { cdlg: o.cdlg, projet: o.ao.project && o.ao.project.id });
res.reponse = await reponse;
// La fenêtre d'invitation, puis la fiche d'un partenaire, puis le tiroir : chacune se ferme, l'écran reste.
o.rinv = { projectId: 9 }; history.back(); res.b2 = Object.assign(etat(), { rinv: o.rinv });
o.reseau.fiche = { id: 4 }; o.drawer = { id: 9 }; history.back(); res.b3 = Object.assign(etat(), { fiche: o.reseau.fiche, tiroir: o.drawer });
// Plus de fenêtre : précédent change d'écran, comme avant.
history.back(); res.b4 = Object.assign(etat(), { projet: o.ao.project && o.ao.project.id });
// Suivant avec une fenêtre ouverte : elle se ferme et l'écran suit l'adresse.
o.rinv = { projectId: 7 }; history.forward(); res.f1 = Object.assign(etat(), { rinv: o.rinv, projet: o.ao.project && o.ao.project.id });
console.log(JSON.stringify(res));
})();
""", ["_surRetourNavigateur", "_fermerFenetres", "demander", "_cdlgOuvrir", "_cdlgFermer", "cdlgClose", "_cdlgEcran",
      "rinvClose", "rnCloseFiche"], depart="/app/marches/7")
    assert r["ouvert"]["urls"] == ["/app/marches/7", "/app/marches/9"] and r["ouverte"] is True
    # La confirmation est fermée (elle répond « Annuler »), le marché 9 reste à l'écran, son adresse aussi.
    assert r["b1"]["cdlg"] is None and r["reponse"] is None
    assert r["b1"]["view"] == "aodetail" and r["b1"]["projet"] == 9
    assert r["b1"]["urls"] == ["/app/marches/7", "/app/marches/9"] and r["b1"]["idx"] == 1 and r["b1"]["n"] == 1
    assert r["b2"]["rinv"] is None and r["b2"]["view"] == "aodetail" and r["b2"]["idx"] == 1
    assert r["b3"]["fiche"] is None and r["b3"]["tiroir"] is None and r["b3"]["idx"] == 1
    assert r["b4"]["view"] == "aodetail" and r["b4"]["projet"] == 7 and r["b4"]["idx"] == 0
    assert r["f1"]["rinv"] is None and r["f1"]["projet"] == 9 and r["f1"]["idx"] == 1


def test_une_confirmation_n_agit_que_sur_l_ecran_ou_elle_a_ete_ouverte():
    r = _naviguer(_FENETRES + """
const res = { runs: [] };
(async () => {
demarrer(); o.openAo(o.projects[1]); vider();
// Ouverte sur le marché 9 ; l'écran change sous elle (autre marché) : confirmer vaut « Annuler ».
o._convAsk({ title: "Écarter ce marché ?", ok: "Écarter", run: () => res.runs.push("ecarter") }); vider();
o.ao.project = o.projects[0];
await o.cdlgRun(); res.apres = { cdlg: o.cdlg, runs: res.runs.slice() };
const p = o.demander({ title: "Décliner l'invitation ?" }); o.sharedAo = { projectId: 5, token: "autre" }; o.cdlgAutre();
res.autre = await p;
// Sur le même écran, elle agit comme avant.
o.ao.project = o.projects[1];
o._convAsk({ title: "Écarter ce marché ?", ok: "Écarter", run: () => res.runs.push("ecarter-9") }); vider();
await o.cdlgRun(); res.memeEcran = res.runs.slice();
console.log(JSON.stringify(res));
})();
""", ["_surRetourNavigateur", "_fermerFenetres", "demander", "_convAsk", "_cdlgOuvrir", "_cdlgFermer", "cdlgClose",
      "cdlgRun", "cdlgAutre", "_cdlgEcran", "rinvClose", "rnCloseFiche"], depart="/app/marches/7")
    assert r["apres"] == {"cdlg": None, "runs": []}
    assert r["autre"] is None
    assert r["memeEcran"] == ["ecarter-9"]


def test_le_gestionnaire_popstate_passe_par_la_fermeture_des_fenetres():
    mounted = JS[JS.index("  mounted() {\n    this.applyTheme();"):JS.index("  updated() {")]
    assert 'window.addEventListener("popstate", (ev) => this._surRetourNavigateur(ev));' in mounted
    f = _methode("_fermerFenetres")
    for fenetre in ("this.cdlg", "this.rinv", "this.reseau.fiche", "this.modal", "this.drawer", "this.notifsOpen",
                    "this.discover.open", "this.fb.open", "pv.passage", "this.pvAtl.open", "a.derog", "a.debit", "a.vue",
                    "a.lotsDlg", "a.plan"):
        assert fenetre in f, fenetre
    # Toujours un seul pushState (dans _adresseSynchro) : le retour qui ferme une fenêtre le réutilise.
    assert JS.count("history.pushState(") == 1 and "history.pushState(" in _methode("_adresseSynchro")
    # Chaque fenêtre de la page est dans la liste (une fenêtre ajoutée plus tard doit l'être aussi).
    for flag in re.findall(r'<div data-test="(?:fenetre|fenetres|tiroir)-[a-z-]+" v-if="([^"]+)"', HTML):
        if flag in ("token && showWelcome",):
            continue                              # l'écran d'accueil du SIRET : un premier pas, pas une fenêtre
        cle = flag.split("=")[0].strip()
        assert cle in f or cle.replace("atl.", "a.") in f, flag


# ═══ 2. Deux invitations sur le même marché (remarque 2) ════════════════════════════════════════════════════════

def test_l_adresse_d_un_dossier_partage_designe_une_invitation_sans_le_jeton():
    r = _node(_ADRESSES + """
const A = "jeton-cotraitant-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", B = "jeton-sous-traitant-BBBBBBBBBBBBBBBBBBBBBBBBBBBB";
const ca = clePartage(A), cb = clePartage(B);
const partages = [{ project_id: 8, token: B, role: "sous_traitant" }, { project_id: 8, token: A, role: "cotraitant" },
                  { project_id: 3, token: "x", role: "cotraitant" }];
console.log(JSON.stringify({ ca, cb, encore: clePartage(A), vide: clePartage(""),
  adr: adresseDe({ view: "sharedao", partage: 8, cle: ca }), sans: adresseDe({ view: "sharedao", partage: 8 }),
  douteuse: adresseDe({ view: "sharedao", partage: 8, cle: A }),
  retour: etatDeAdresse("/app/marches/partenaire/8/" + ca), ancien: etatDeAdresse("/app/marches/partenaire/8"),
  jeton: etatDeAdresse("/app/marches/partenaire/8/" + A),
  trouveA: trouverPartage(partages, 8, ca).role, trouveB: trouverPartage(partages, 8, cb).role,
  plusAncien: trouverPartage(partages, 8, "").role, inconnue: trouverPartage(partages, 8, "zzzzzzz"),
  autreMarche: trouverPartage(partages, 9, ca) }));
""")
    assert re.fullmatch(r"[0-9a-z]{7}", r["ca"]) and r["ca"] != r["cb"] and r["ca"] == r["encore"] and r["vide"] == ""
    assert r["adr"] == "/app/marches/partenaire/8/" + r["ca"] and r["sans"] == "/app/marches/partenaire/8"
    assert r["douteuse"] == "/app/marches/partenaire/8"                  # un jeton n'est jamais un repère
    assert "jeton" not in r["adr"] and r["ca"] not in "jeton-cotraitant-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    assert r["retour"] == {"view": "sharedao", "partage": 8, "cle": r["ca"]}
    assert r["ancien"] == {"view": "sharedao", "partage": 8}
    assert r["jeton"] == {"view": "dashboard", "inconnue": True}
    assert r["trouveA"] == "cotraitant" and r["trouveB"] == "sous_traitant"
    assert r["plusAncien"] == "cotraitant"                              # /api/shared : du plus récent au plus ancien
    assert r["inconnue"] is None and r["autreMarche"] is None


def test_deux_invitations_sur_le_meme_marche_chacune_rouvre_la_sienne(client):
    chef, part = _org(client, "Breizh Couverture"), _org(client, "Le Gall Électricité")
    pid = _project(client, chef)
    toks = []
    for role in ("cotraitant", "sous_traitant"):
        inv = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                          json={"company_name": "Le Gall Électricité", "recipient": part["email"], "role": role}).json()
        assert client.post(f"/api/invite/{inv['token']}/claim", headers=part["headers"]).status_code == 200
        toks.append(inv["token"])
    partages = client.get("/api/shared", headers=part["headers"]).json()
    assert [(s["project_id"], s["role"]) for s in partages] == [(pid, "sous_traitant"), (pid, "cotraitant")]
    # Le navigateur, avec les vraies réponses : ?shared=<jeton du partenaire du groupement> au démarrage, puis
    # l'autre dossier, puis précédent ; le rechargement de chaque adresse.
    etat = ("\nconst PARTAGES = " + json.dumps(partages) + ", JETONS = " + json.dumps(toks) + ";\n"
            + "o.shared = PARTAGES; o.openShared = function (it) { this.sharedAo = { projectId: it.project_id, "
              "token: it.token, cle: clePartage(it.token) }; this.view = 'sharedao'; this.journal.push('partage:' + it.role); };\n")
    r = _naviguer(f"""
const res = {{}};
demarrer();
const it = o.shared.find(s => s.token === JETONS[0]);       // comme boot() avec ?shared=
o._ouvrirAdresse({{ view: "sharedao", partage: it.project_id, cle: clePartage(it.token) }}); vider(); res.lien = etat();
o.openShared(o.shared[0]); vider(); res.autre = etat();
history.back(); res.retour = Object.assign(etat(), {{ role: o.sharedAo && o.shared.find(s => s.token === o.sharedAo.token).role }});
res.journal = o.journal.filter(x => x.startsWith("partage:"));
console.log(JSON.stringify(res));
""", ["_surRetourNavigateur", "_fermerFenetres", "rinvClose", "rnCloseFiche"], depart="/app", etat=_FENETRES + etat)
    cle_co = r["lien"]["urls"][-1].rsplit("/", 1)[1]
    assert r["lien"]["urls"][-1].startswith(f"/app/marches/partenaire/{pid}/") and r["lien"]["view"] == "sharedao"
    assert r["autre"]["urls"][-1].startswith(f"/app/marches/partenaire/{pid}/") and r["autre"]["urls"][-1].rsplit("/", 1)[1] != cle_co
    assert r["retour"]["role"] == "cotraitant" and r["retour"]["idx"] == r["autre"]["idx"] - 1
    assert r["journal"] == ["partage:cotraitant", "partage:sous_traitant", "partage:cotraitant"]
    for t in toks:
        assert all(t not in u for u in r["autre"]["urls"])                # jamais le jeton dans l'adresse
    # Rechargement : chaque adresse rouvre son dossier.
    for i, attendu in ((0, "cotraitant"), (1, "sous_traitant")):
        x = _naviguer("demarrer(); console.log(JSON.stringify({ role: o.shared.find(s => s.token === o.sharedAo.token).role, u: etat().urls }));",
                      ["_surRetourNavigateur", "_fermerFenetres", "rinvClose", "rnCloseFiche"],
                      depart="/app/marches/partenaire/%d/%s" % (pid, _node(_ADRESSES + f"console.log(JSON.stringify(clePartage({json.dumps(toks[i])})));")),
                      etat=_FENETRES + etat)
        assert x["role"] == attendu, (i, x)
    # Le démarrage : ?shared= ouvre l'invitation de CE jeton ; « À faire » garde le jeton (en mémoire) pour la sienne.
    boot = JS[JS.index("    async boot() {"):JS.index("    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES")]
    assert '_demande = it ? { view: "sharedao", partage: it.project_id, cle: clePartage(it.token) }' in boot
    assert 'cible = { view: "sharedao", partage: s.project_id, jeton: s.token }' in JS
    assert "c.jeton ? x.token === c.jeton : x.project_id === c.partage" in _methode("aFaireOuvrir")
    assert "partage: this.sharedAo.projectId, cle: this.sharedAo.cle" in JS[JS.index("    adresseCourante() {"):JS.index("  watch: {")]
    # Le cloisonnement ne bouge pas : /api/shared garde exactement ses champs (aucun identifiant ajouté).
    assert set(partages[0]) == {"token", "project_id", "project", "mandataire", "role", "can_contribute",
                                "contribution_status", "deadline", "groupement", "redaction"}


# ═══ 3. Un geste ne fait jamais reculer un marché (remarque 3) ═════════════════════════════════════════════════

def test_un_geste_ne_fait_jamais_reculer_un_marche_depose(client):
    chef = _org(client, "Breizh Couverture")
    h = chef["headers"]
    pid = _project(client, chef)
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={"confirmer": True})
    assert r.status_code == 200 and r.json()["status"] == "depose"
    # Une liste périmée (« Repéré ») invite un partenaire, puis fait le geste « En préparation » : rien ne recule.
    r = client.put(f"/api/projects/{pid}", headers=h, json={"status": "en_cours", "si_statut": ["nouveau", "decide"]})
    assert r.status_code == 200 and r.json()["status"] == "depose"
    for choix, cible, depuis in (("seul", "decide", ["nouveau", "abandonne"]), ("ecarter", "abandonne", ["suivi", "nouveau", "decide", "en_cours"])):
        r = client.put(f"/api/projects/{pid}", headers=h, json={"status": cible, "si_statut": depuis})
        assert r.status_code == 200 and r.json()["status"] == "depose", choix
    assert client.get(f"/api/projects/{pid}", headers=h).json()["status"] == "depose"
    from app.models import AuditLog
    db = _db()
    try:
        assert not db.query(AuditLog).filter(AuditLog.project_id == pid, AuditLog.action == "groupement.depot_annule").count()
    finally:
        db.close()
    # Depuis l'étape attendue, le geste fait avancer ; le choix « Statut » (sans si_statut) reste libre.
    p2 = _project(client, chef)
    r = client.put(f"/api/projects/{p2}", headers=h, json={"status": "en_cours", "si_statut": ["nouveau", "decide"]})
    assert r.json()["status"] == "en_cours"
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "en_cours"}).json()["status"] == "en_cours"
    # Une étape inconnue est refusée lisiblement ; « envoye » est lue comme « depose ».
    assert client.put(f"/api/projects/{p2}", headers=h, json={"status": "decide", "si_statut": ["bidule"]}).status_code == 422
    assert client.put(f"/api/projects/{p2}", headers=h, json={"status": "decide", "si_statut": [None]}).status_code == 422
    r = client.put(f"/api/projects/{p2}", headers=h, json={"status": "gagne", "si_statut": ["envoye"]})
    assert r.status_code == 200 and r.json()["status"] == "en_cours"


def test_le_geste_de_la_demonstration_reste_permis(client):
    """La vitrine partagée : seul le changement d'étape est permis ; le geste (étape + étapes de départ) l'est aussi,
    et, parti d'une autre étape, il ne change rien."""
    from tests.test_demo_sans_cout import _contexte, _sessions
    pme, _ach = _sessions(client)
    ctx = _contexte()
    avant = client.get(f"/api/projects/{ctx['lorient']}", headers=pme).json()["status"]
    r = client.put(f"/api/projects/{ctx['lorient']}", headers=pme,
                   json={"status": "decide", "si_statut": [s for s in ("suivi", "abandonne") if s != avant]})
    assert r.status_code == 200 and r.json()["status"] == avant


def test_l_ecran_envoie_l_etape_de_depart_et_reprend_l_etape_reelle():
    m = _methode("_marcheEnPreparation")
    r = _node(_AXE + """
const o = {
""" + m + """,
  view: "cotraitants", ao: { project: null }, appels: [], stats: 0,
  projects: [{ id: 8, status: "nouveau" }, { id: 9, status: "decide" }],
  async api(m, p, b) { this.appels.push([m, p, b]); return { status: p.endsWith("/8") ? "depose" : "en_cours" }; },
  loadStats() { this.stats++; }, aoAvancer() { this.appels.push(["page"]); },
};
(async () => {
  await o._marcheEnPreparation(8); await o._marcheEnPreparation(9);
  const coh = {};
  for (const s of AXE_ETAPES.map(e => e.k)) for (const c of ["seul", "plusieurs", "ecarter", "remettre"])
    coh[s + "/" + c] = (statutApresDecision(s, c) !== null) === (DEPARTS_GESTE[c].indexOf(s) >= 0);
  for (const s of AXE_ETAPES.map(e => e.k)) coh[s + "/preparer"] = (statutEnPreparation(s) !== null) === (DEPARTS_GESTE.preparer.indexOf(s) >= 0);
  console.log(JSON.stringify({ appels: o.appels, statuts: o.projects.map(p => p.status), coh }));
})();
""")
    # La liste disait « Repéré », le serveur dit « Déposé » : la liste reprend « Déposé », jamais « En préparation ».
    assert r["appels"][0] == ["PUT", "/api/projects/8", {"status": "en_cours", "si_statut": ["nouveau", "decide"]}]
    assert r["statuts"] == ["depose", "en_cours"]
    # Les étapes de départ envoyées sont exactement celles où le geste fait avancer le marché.
    assert all(r["coh"].values()), [k for k, v in r["coh"].items() if not v]
    # La page du marché : la décision et le geste de Préparer envoient leurs étapes de départ.
    assert 'this._aoChangerStatut(c, "", DEPARTS_GESTE.preparer)' in _methode("aoAvancer")
    assert "DEPARTS_GESTE[choix]" in _methode("aoDecider") and "DEPARTS_GESTE.ecarter" in _methode("aoDecider")
    ch = _methode("_aoChangerStatut")
    assert "depuis ? { status: cible, si_statut: depuis } : { status: cible }" in ch
    assert "const l = (this.projects || []).find(x => x.id === pid); if (l) l.status = reel;" in ch


def test_marquer_depose_met_a_jour_mes_marches():
    r = _node(_AXE + """
const o = {
""" + _methode("aoDepotMark") + ",\n" + _methode("aoDepotUnmark") + ",\n" + _methode("_listeSuitStatut") + """,
  ao: { project: { id: 8, status: "nouveau" }, depot: { busy: "", d: {} }, grp: {} }, projects: [{ id: 8, status: "nouveau" }, { id: 3, status: "nouveau" }],
  $nextTick() {}, $refs: {}, notify() {}, _convMergeState() {}, async aoDepotLoad() {},
  async api(m) { return m === "POST" ? { status: "depose" } : { status: "decide" }; },
};
(async () => {
  await o.aoDepotMark(true); const a = o.projects.map(p => p.status);
  await o.aoDepotUnmark(); const b = o.projects.map(p => p.status);
  console.log(JSON.stringify({ a, b }));
})();
""")
    assert r == {"a": ["depose", "nouveau"], "b": ["decide", "nouveau"]}


# ═══ 4. Bascule de la migration (remarque 4) ═══════════════════════════════════════════════════════════════════

def test_la_bascule_de_la_migration_dit_l_etendue_reelle_de_la_panne():
    src = (ROOT / "alembic" / "versions" / "c4axeetapes_axe_etapes.py").read_text(encoding="utf-8")
    doc = src[:src.index('"""', 3)]
    assert "la nouvelle instance prend le relais aussitôt" not in doc and "quelques secondes" not in doc
    for fait in ("TOUTES ses listes", "/api/shared", "l'historique du réseau", "contrôle de santé",
                 "`alembic downgrade b3mesureecrans`", "heure creuse"):
        assert fait in doc, fait
    r8 = CONTRAT[CONTRAT.index("### R.8 Pour Eliot"):]
    r8 = r8[:r8.index("\n## ") if "\n## " in r8 else len(r8)]
    assert "sinon l'ancien code ne lit plus les marchés déposés" not in r8
    for fait in ("toutes ses listes", "/api/shared", "heure creuse", "alembic downgrade b3mesureecrans"):
        assert fait in r8, fait
    a16 = CONTRAT[CONTRAT.index("### A1.6 Migration"):CONTRAT.index("### A1.7")]
    assert "la nouvelle prend le relais aussitôt" not in a16


# ═══ 5. « Prêt à déposer » : sous-traitant seul, convention restée en brouillon (remarque 5) ═══════════════════

def test_a_un_groupement_seulement_avec_un_membre():
    from app.services.groupement_members import a_un_groupement
    st, co = SimpleNamespace(role="sous_traitant"), SimpleNamespace(role="cotraitant")
    brouillon = SimpleNamespace(status="draft", params={"forme": "conjoint"})
    hors_ligne = SimpleNamespace(status="draft", params={"membres_hors_ligne": [{"link_id": 3}]})
    assert a_un_groupement([], None) is False and a_un_groupement([st], None) is False
    assert a_un_groupement([st], brouillon) is False and a_un_groupement([], brouillon) is False
    assert a_un_groupement([co], None) is True and a_un_groupement([st, co], None) is True
    assert a_un_groupement([], hors_ligne) is True
    for s in ("a_signer", "signee", "perimee"):
        assert a_un_groupement([], SimpleNamespace(status=s, params=None)) is True, s


def test_pret_a_deposer_d_une_entreprise_avec_un_seul_sous_traitant(client):
    chef = _org(client, "Chef Avec ST SARL", extra={"representant_legal": "Jean Test"})
    h = chef["headers"]
    pid = _project(client, chef)
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Sous Traitant Y", "role": "sous_traitant"})
    assert r.status_code == 200
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["pour"] == "seul" and "convention" not in " ".join(d["manques"]).lower()
    assert not any("après la convention" in m for m in d["manques"])
    assert any("Sous Traitant Y" in a and "DC4" in a for a in d["avertissements"]), d["avertissements"]
    # La liste des pièces dit la même chose : ni pouvoir du chef de file, ni convention ; le DC4 à prévoir.
    ck = client.get(f"/api/checklist/{pid}", headers=h).json()
    ids = {i["id"]: i for i in ck["checklist"]}
    assert ck["context"]["groupement"] is False and "convention_groupement" not in ids
    assert ids["pouvoir"]["required"] is False and ids["dc4"]["required"] is True
    r = client.post(f"/api/projects/{pid}/groupement/deposer", headers=h, json={})
    assert r.status_code == 409 and not any("onvention" in m for m in r.json()["detail"]["manques"])


def test_pret_a_deposer_apres_le_declin_du_seul_partenaire(client):
    chef = _org(client, "Chef Decline SARL")
    h = chef["headers"]
    pid = _project(client, chef)
    inv = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Partenaire Z"}).json()
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"forme": "conjoint"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]["pour"] == "groupement"
    assert client.post(f"/api/invite/{inv['token']}/decline", json={"motif": "pas dispo"}).status_code == 200
    assert client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()["state"] == "seul"
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["pour"] == "seul" and list(d["checks"])[0] == "prix"
    assert not any("onvention" in m for m in d["manques"])
    ck = client.get(f"/api/checklist/{pid}", headers=h).json()
    assert "convention_groupement" not in {i["id"] for i in ck["checklist"]}


def test_pret_a_deposer_d_un_groupement_inchange_avec_un_partenaire(client):
    chef = _org(client, "Chef Groupement SARL")
    h = chef["headers"]
    pid = _project(client, chef)
    client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Sous Traitant", "role": "sous_traitant"})
    client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Partenaire", "role": "cotraitant"})
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["pour"] == "groupement" and list(d["checks"]) == ["parts_soumises", "attestations_ok", "convention_signee",
                                                               "cerfa_generes"]
    assert client.get(f"/api/checklist/{pid}", headers=h).json()["context"]["groupement"] is True


# ═══ 6. Une pièce exigée reconnue sous son nom (remarque 6) ════════════════════════════════════════════════════

def _doc(nom, cat="autre"):
    return SimpleNamespace(id=hash(nom) % 10000, name=nom, category=cat, expiration_date=None)


def test_une_piece_sans_mot_cle_est_reconnue_sous_son_nom():
    from app.routers.checklist import match_document
    for piece, docs in (("Attestation de visite obligatoire", ["Attestation de visite obligatoire", "Visite obligatoire.pdf",
                                                               "attestation visite", "ATTESTATION_DE_VISITE.pdf"]),
                        ("Certificat ISO 27001", ["Certificat ISO 27001", "ISO 27001.pdf", "iso27001", "Certificats ISO-27001"]),
                        ("ISO 27001", ["ISO 27001", "iso27001.pdf"])):
        for nom in docs:
            assert match_document(piece, [_doc(nom)])["found"] is True, (piece, nom)
    # Jamais sur un seul mot commun : tous les mots significatifs de la pièce.
    for piece, nom in (("Certificat ISO 27001", "Certificat ISO 9001"), ("Attestation de régularité fiscale",
                                                                          "Attestation de régularité sociale"),
                       ("Attestation de visite obligatoire", "Attestation d'assurance"), ("ISO 27001", "Kbis")):
        assert match_document(piece, [_doc(nom)])["found"] is False, (piece, nom)
    # Les pièces standard gardent leurs mots-clés.
    assert match_document("Attestation de régularité sociale (URSSAF)", [_doc("urssaf 2026.pdf")])["found"] is True
    assert match_document("Extrait Kbis ou équivalent", [_doc("Kbis.pdf")])["found"] is True


def test_pret_a_deposer_reconnait_la_piece_deposee_sous_son_nom(client):
    chef = _org(client, "Seule Pièces SARL")
    h = chef["headers"]
    pid = _project(client, chef)
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        a = dict(p.ai_analysis)
        a["details"] = dict(a["details"], pieces_requises=["Attestation de visite obligatoire", "Certificat ISO 27001"])
        p.ai_analysis = a
        db.commit()
    finally:
        db.close()
    avant = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]["manques_par_controle"]["pieces"]
    assert "Attestation de visite obligatoire : à ajouter dans Mes documents" in avant
    for nom in ("Attestation de visite obligatoire", "iso27001"):
        r = client.post("/api/documents/", headers=h, files={"file": (nom + ".pdf", b"%PDF-1.4 x", "application/pdf")},
                        data={"name": nom, "category": "qualifications"})
        assert r.status_code == 201, r.text
    apres = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]["manques_par_controle"]["pieces"]
    assert not any("visite" in m.lower() or "27001" in m for m in apres), apres
    carte = {i["name"]: i["status"] for i in client.get(f"/api/checklist/{pid}", headers=h).json()["checklist"]}
    assert carte["Attestation de visite obligatoire"] == "ok" and carte["Certificat ISO 27001"] == "ok"


# ═══ 7. Formulaires rangés par la production (remarque 7) ══════════════════════════════════════════════════════

def test_formulaires_ranges_par_la_production_comptent_pour_une_entreprise_seule(client):
    """La production (fab9d9a) rangeait DC1, DC2 et ATTRI1 dans « Formulaires officiels » sans les horodater pour une
    entreprise seule : le marché ne doit pas afficher « Formulaire … à préparer » le jour de la mise en ligne."""
    chef = _org(client, "Seule Prod SARL", extra={"representant_legal": "Jean Test"})
    h = chef["headers"]
    pid = _project(client, chef)
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    from app.models import Document, GeneratedDoc
    db = _db()
    try:
        assert {d.name for d in db.query(Document).filter(Document.project_id == pid, Document.folder == "CERFA")} >= {
            "DC1.pdf", "DC2.pdf", "ATTRI1.pdf"}
        db.query(GeneratedDoc).filter(GeneratedDoc.project_id == pid).delete()     # l'état laissé par la production
        db.commit()
    finally:
        db.close()
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["checks"]["formulaires"] is True and d["manques_par_controle"]["formulaires"] == []
    # Un formulaire retiré du dossier manque de nouveau (corbeille comprise) ; un autre marché n'en prête aucun.
    db = _db()
    try:
        from app.models import utcnow
        doc = db.query(Document).filter(Document.project_id == pid, Document.folder == "CERFA", Document.name == "DC2.pdf").first()
        doc.deleted_at = utcnow()
        db.commit()
    finally:
        db.close()
    d = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    assert d["manques_par_controle"]["formulaires"] == ["Formulaire DC2 à préparer : « Préparer mes documents »"]
    p2 = _project(client, chef)
    assert client.get(f"/api/projects/{p2}/groupement/depot", headers=h).json()["pret"]["checks"]["formulaires"] is False


# ═══ 8. Atelier ouvert directement : « Retour au marché » puis « Retour » (remarque 8) ═════════════════════════

def test_atelier_ouvert_directement_retour_au_marche_puis_retour_sans_boucle():
    r = _naviguer(_FENETRES + """
o.atlCardLoad = () => {}; o._atlQuitter = () => o.journal.push("quitte-atelier");
const res = {};
demarrer(); res.depart = etat();
o.atlBack(); vider(); res.marche = etat();
o.aoBack(); vider(); res.liste = etat();
history.back(); res.precedent = etat();
console.log(JSON.stringify(res));
""", ["_surRetourNavigateur", "_fermerFenetres", "rinvClose", "rnCloseFiche", "atlBack", "aoBack"],
        depart="/app/marches/7/dossier-de-presentation")
    assert r["depart"] == {"urls": ["/app/marches/7/dossier-de-presentation"], "idx": 0, "view": "atelier", "n": 0}
    # La page du marché prend la place de l'atelier (aucune entrée ajoutée) ; son « Retour » mène à Mes marchés.
    assert r["marche"] == {"urls": ["/app/marches/7"], "idx": 0, "view": "aodetail", "n": 0}
    assert r["liste"]["view"] == "pipeline" and r["liste"]["urls"] == ["/app/marches/7", "/app/marches"]
    assert r["precedent"]["view"] == "aodetail" and r["precedent"]["idx"] == 0


# ═══ 9. Carte « À venir » : la page d'un marché pas encore publié (remarque 10) ════════════════════════════════

def test_la_page_d_une_carte_a_venir_ne_parle_ni_d_annonce_ni_de_dossier_indispensable():
    analyse = zone(HTML, "marche-analyse")
    pas = zone(HTML, "marche-pas-publie")
    assert pas in analyse and pas.startswith('<div data-test="marche-pas-publie" v-if="aoPasPublie()"')
    assert "Marché pas encore publié" in pas and "Vous pouvez déjà inviter vos partenaires." in pas
    assert "indispensable" not in pas and "Annonce seule" not in pas
    # Le bandeau « indispensable » et « Aucune analyse encore » ne sont plus pour une carte « À venir ».
    sinon = analyse.index('v-else-if="!aoDceAvailable()"')
    assert analyse.index(pas) < sinon < analyse.index("Le dossier complet du marché est indispensable")
    assert '<p class="muted small" v-else-if="!aoPasPublie()">Aucune analyse encore.' in analyse
    assert "(aoPasPublie()?'Pas encore publié':'Annonce seule')" in analyse
    r = _node("const o = {\n" + _methode("aoDceAvailable") + ",\n" + _methode("aoPasPublie") + """,
  ao: { project: null } };
const out = [];
for (const [st, dce] of [["suivi", false], ["suivi", true], ["nouveau", false], ["en_cours", false]]) {
  o.ao.project = { status: st, ai_analysis: { dce_available: dce } }; out.push(o.aoPasPublie());
}
o.ao.project = null; out.push(o.aoPasPublie());
console.log(JSON.stringify(out));
""")
    assert r == [True, False, False, False, False]


def test_les_textes_ajoutes_sont_traduits_sans_mot_banni():
    from tests.textes_visibles import mots_bannis, textes_html
    d = json.loads((STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)[1][len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for fr in ("Pas encore publié", "Marché pas encore publié",
               "Le dossier sera à importer à sa publication. Vous pouvez déjà inviter vos partenaires."):
        assert d["nl"].get(fr) and d["es"].get(fr), fr
    assert "Aanbesteding" in d["nl"]["Marché pas encore publié"] and "Licitación" in d["es"]["Marché pas encore publié"]
    textes = [t for _ligne, t in textes_html(zone(HTML, "marche-pas-publie"))]
    assert "Marché pas encore publié" in " ".join(textes)
    assert not [t for t in textes if mots_bannis(t)], [t for t in textes if mots_bannis(t)]
