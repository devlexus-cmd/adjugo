"""
Réorganisation de l'interface — vague 2a, chantier A1 « adresses et étapes » (contrat : docs/REORGANISATION_V2A.md, A1).

1. Une adresse par écran : routage par CHEMIN (/app/marches, /app/marches/12, /app/reglages/compte…), le serveur sert
   la même page (no-store) à chacune ; précédent / suivant du navigateur sur plusieurs niveaux ; lien, favori et
   rechargement rouvrent le bon écran ; ?shared=, ?verify=, ?reset=, ?inscription et #gcode= préservés ; les courriels
   au chef de file mènent à la page du marché.
2. Un seul axe d'étapes (décision 7) : À venir → Repéré → Décidé → En préparation → Déposé → Gagné / Perdu, plus
   Abandonné ; la clé « envoye » migre vers « depose » (données, code, statistiques) ; la barre de la page du marché
   affiche des statuts dérivés ; l'étape Décider décide ; une carte peut exister avant la publication (décision 11).
3. Barre basse sur téléphone (décision 18) ; la cloche fondue avec « À faire », la même liste que l'accueil.

Aucun appel réseau : routes de l'API locale, fonctions de app.js exécutées sous Node, base SQLite des tests.
"""
import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta

import pytest

from tests.test_reseau_ecrans import _method
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")


def tranche(src, debut, derniere):
    """De `debut` jusqu'à la fin de la fonction `derniere` (une ligne, ou jusqu'à son « } » de fin de bloc)."""
    i = src.index(debut)
    k = src.index(derniere, i)
    fin_ligne = src.index("\n", k)
    return src[i:fin_ligne + 1] if src[k:fin_ligne].rstrip().endswith("}") else src[i:src.index("\n}\n", k) + 3]


# Fonctions pures, en tête de app.js : les adresses, l'axe d'étapes, la barre, « À faire ».
_ADRESSES = tranche(JS, "// ══════════ Une adresse par écran (réorganisation, vague 2a, A1) ══════════", "function etatDeAdresse(")
_AXE = tranche(JS, "// ══════════ Un seul axe d'étapes (réorganisation, vague 2a, A1 ; décision 7)", "function statutEnPreparation(")
_BARRE = (tranche(JS, "const ETAPES_LIBELLES = {", "function etapeDuMarche(")
          + "\n" + tranche(JS, "const BARRE_ETATS = {", "function barreDuMarche("))
_A_FAIRE = tranche(JS, "const A_FAIRE_JOURS = 7;", "function listeAFaire(")
VUES_HTML = sorted(set(re.findall(r"view===?'([a-z]+)'", HTML)))


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ═══ 1. Une adresse par écran : le serveur ═════════════════════════════════════════════════════════════════════

ADRESSES_ECRANS = ["/app/marches", "/app/marches/12", "/app/marches/12/dossier-de-presentation",
                   "/app/marches/partenaire/34", "/app/trouver/a-venir", "/app/partenaires/reseau/invitations",
                   "/app/reglages/compte", "/app/entreprise/preuves", "/app/n-importe-quoi/2", "/app/"]


def test_chaque_adresse_sert_la_page_de_l_application_sans_cache(client):
    base = client.get("/app")
    assert base.status_code == 200 and base.headers["content-type"].startswith("text/html")
    for url in ADRESSES_ECRANS:
        r = client.get(url)
        assert r.status_code == 200, url
        assert r.text == base.text, url                                   # la même page, l'application lit le chemin
        assert r.headers["cache-control"] == "no-store, must-revalidate" and r.headers["pragma"] == "no-cache", url
        assert "frame-ancestors 'self'" in r.headers["content-security-policy"], url
    # Les liens déjà envoyés ne changent pas : /app et ses paramètres.
    for url in ("/app?verify=abc.def", "/app?reset=Zz9", "/app?shared=jeton", "/app?inscription", "/app?payment=success"):
        r = client.get(url)
        assert r.status_code == 200 and r.text == base.text, url
    # Rien d'autre n'est servi sous ce nom : /apps n'existe pas ; l'espace des collectivités garde sa page.
    assert client.get("/apps").status_code == 404
    assert "acheteur" in client.get("/acheteur/app").text.lower()


def test_le_serveur_ne_lit_jamais_le_chemin():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    i = src.index('@app.get("/app/{chemin:path}"')
    route = src[i:src.index("\n\n\n", i)]
    assert "def software_ecran(chemin: str):\n    return software()" in route      # aucune donnée, aucun accès
    assert 'p == "/app" or p.startswith("/app/")' in src                          # no-store sur toutes les adresses


# ═══ 1. Une adresse par écran : les chemins (fonctions pures, sous Node) ══════════════════════════════════════

def test_chaque_ecran_a_son_adresse_et_chaque_adresse_rouvre_son_ecran():
    r = _node(_ADRESSES + """
const vues = JSON.parse(process.argv[1]), out = {};
for (const v of vues) {
  const e = v === "aodetail" || v === "atelier" || v === "apercu" ? { view: v, projet: 12 } : v === "sharedao" ? { view: v, partage: 34 } : { view: v };
  const a = adresseDe(e), r = etatDeAdresse(a);
  out[v] = { a, retour: r && r.view, projet: r && (r.projet || r.partage) || null };
}
console.log(JSON.stringify(out));
""", json.dumps(VUES_HTML))
    # Réunion A1 × A2 : les vues « shared » et « consortiums » sont devenues des filtres de Mes marchés (leur adresse
    # est celle du filtre, test suivant) ; « bilan » est un onglet de Mes marchés.
    assert set(r) == set(VUES_HTML) and len(VUES_HTML) >= 21 and not {"shared", "consortiums"} & set(VUES_HTML)
    assert r["bilan"]["a"] == "/app/marches/bilan"
    for v, x in r.items():
        assert x["a"] and x["a"].startswith("/app") and x["retour"] == v, (v, x)
        assert re.fullmatch(r"/app(/[a-z0-9-]+)*", x["a"]), x["a"]                 # des mots, sans accent ni « # »
    assert r["dashboard"]["a"] == "/app" and r["pipeline"]["a"] == "/app/marches"
    assert r["aodetail"] == {"a": "/app/marches/12", "retour": "aodetail", "projet": 12}
    assert r["atelier"]["a"] == "/app/marches/12/dossier-de-presentation"
    assert r["sharedao"] == {"a": "/app/marches/partenaire/34", "retour": "sharedao", "projet": 34}
    # Vague 2b (B3) : « Voir ce que verra [partenaire] », un écran de la page du marché (docs/REORGANISATION_V2B.md).
    assert r["apercu"] == {"a": "/app/marches/12/apercu-partenaire", "retour": "apercu", "projet": 12}
    assert r["compte"]["a"] == "/app/reglages/compte" and r["admin"]["a"] == "/app/reglages/administration"
    assert len({x["a"] for x in r.values()}) == len(r)                               # une adresse par écran


def test_onglets_internes_chemins_inconnus_et_identifiants():
    r = _node(_ADRESSES + """
const cas = JSON.parse(process.argv[1]);
console.log(JSON.stringify({
  adresses: [adresseDe({ view: "sourcing", sous: "avenir" }), adresseDe({ view: "sourcing", sous: "alertes" }),
             adresseDe({ view: "sourcing", sous: "publies" }), adresseDe({ view: "reseau", reseau: "historique" }),
             adresseDe({ view: "reseau", reseau: "profil" }), adresseDe({ view: "reseau", reseau: "annuaire" }),
             adresseDe({ view: "aodetail" }), adresseDe({ view: "aodetail", projet: "12abc" }), adresseDe({ view: "inconnue" }),
             adresseDe({ view: "sharedao", partage: "jeton-secret" })],
  filtres: ["tous", "pilote", "partenaire", "plusieurs", "inconnu"].map(f => adresseDe({ view: "pipeline", filtre: f })),
  etatsFiltres: ["/app/marches", "/app/marches/je-pilote", "/app/marches/partenaire", "/app/marches/a-plusieurs"].map(c => etatDeAdresse(c)),
  etats: cas.map(c => etatDeAdresse(c)),
}));
""", json.dumps(["/app/trouver/a-venir", "/app/trouver/alertes", "/app/partenaires/reseau/invitations",
                 "/app/marches/12?x=1#gcode=abc", "/app/marches/12/", "/app/marches/0", "/app/marches/-3",
                 "/app/marches/1234567890123", "/app/marches/abc", "/app/xyz", "/", "/apps", "/invite/abc",
                 "https://ailleurs.example/app/marches/1", "/app/marches/partenaire/jeton"]))
    assert r["adresses"] == ["/app/trouver/a-venir", "/app/trouver/alertes", "/app/trouver",
                             "/app/partenaires/reseau/historique", "/app/partenaires/reseau",
                             "/app/partenaires/reseau/annuaire", None, None, None, None]
    # Réunion A1 × A2 : chaque filtre de Mes marchés a son adresse (« Tous » : la liste) et la rouvre.
    assert r["filtres"] == ["/app/marches", "/app/marches/je-pilote", "/app/marches/partenaire", "/app/marches/a-plusieurs",
                            "/app/marches"]
    assert r["etatsFiltres"] == [{"view": "pipeline"}, {"view": "pipeline", "filtre": "pilote"},
                                 {"view": "pipeline", "filtre": "partenaire"}, {"view": "pipeline", "filtre": "plusieurs"}]
    e = r["etats"]
    assert e[0] == {"view": "sourcing", "sous": "avenir"} and e[1] == {"view": "sourcing", "sous": "alertes"}
    # L'ancienne adresse des invitations reçues du Réseau mène là où elles se traitent : Mes marchés, « Où je suis partenaire ».
    assert e[2] == {"view": "pipeline", "filtre": "partenaire"}
    assert e[3] == {"view": "aodetail", "projet": 12} and e[4] == {"view": "aodetail", "projet": 12}
    for x in e[5:10]:
        assert x == {"view": "dashboard", "inconnue": True}                        # jamais un identifiant douteux
    assert e[10] is None and e[11] is None and e[12] is None and e[13] is None     # hors de l'application
    assert e[14] == {"view": "dashboard", "inconnue": True}                        # un jeton n'est jamais une adresse


# ═══ 1. Retour arrière sur plusieurs niveaux, liens profonds (méthodes réelles, navigateur simulé) ═════════════

_NAV = ["_adresseSynchro", "_sansHistorique", "_adresseDemandee", "_ouvrirAdresse", "_appliquerAdresse",
        "_retourHistorique", "partageRetour", "aoBack", "adresseCourante"]
_HARNAIS = """
const _calc = o.adresseCourante; delete o.adresseCourante;       // une propriété calculée, comme dans Vue
Object.defineProperty(o, "adresseCourante", { get() { return _calc.call(this); } });
const entrees = [{ url: DEPART, state: null }]; let idx = 0, pops = 0;
const ses = Object.assign({}, GARDE);
globalThis.sessionStorage = { getItem: k => ses[k] || null, setItem: (k, v) => { ses[k] = v; }, removeItem: k => { delete ses[k]; } };
globalThis.location = { get pathname() { return entrees[idx].url.split(/[?#]/)[0]; },
  get search() { const u = entrees[idx].url.split("#")[0], i = u.indexOf("?"); return i < 0 ? "" : u.slice(i); } };
globalThis.history = { get state() { return entrees[idx].state; },
  pushState(st, t, url) { entrees.splice(idx + 1); entrees.push({ url, state: st }); idx++; },
  replaceState(st, t, url) { entrees[idx] = { url: url === undefined ? entrees[idx].url : url, state: st }; },
  back() { if (idx > 0) { idx--; pops++; o._ouvrirAdresse(etatDeAdresse(location.pathname), history.state && history.state.defil); vider(); } },
  forward() { if (idx < entrees.length - 1) { idx++; pops++; o._ouvrirAdresse(etatDeAdresse(location.pathname), history.state && history.state.defil); vider(); } } };
globalThis.document = { title: "", querySelector() { return { scrollTop: 40 }; } };
globalThis.setTimeout = () => 0;
const ticks = [];
o.$nextTick = cb => { ticks.push(cb); };
let derniere = null;
function vider() {        // comme Vue : l'observateur d'adresseCourante, puis les rappels de $nextTick
  for (let k = 0; k < 5; k++) { const a = o.adresseCourante; if (a !== derniere) { derniere = a; o._adresseSynchro(a); }
    const t = ticks.splice(0); t.forEach(f => f()); if (!ticks.length) break; }
}
Object.assign(o, { token: "t", user: { is_admin: false }, view: "dashboard", trouverOnglet: "publies", projects: [{ id: 7, name: "Sept" }, { id: 9, name: "Neuf" }],
  shared: [{ project_id: 5, token: "jeton-5" }], ao: { project: null, back: "" }, sharedAo: { projectId: null }, reseau: { tab: "profil" },
  journal: [], drawer: null, mmFiltre: "tous",
  enteteTitre() { return this.view; }, notify(m) { this.journal.push("message:" + m); },
  go(v) { if (v === "admin" && !this.user.is_admin) v = "dashboard";
    let f = ""; if (v === "shared" || v === "consortiums") { f = v === "shared" ? "partenaire" : "plusieurs"; v = "pipeline"; }   // comme go() (A2)
    if (v === "pipeline") { if (f) this.mmFiltre = f; else if (this.view !== "pipeline") this.mmFiltre = "tous"; }
    this.view = v; if (v === "sourcing") this.trouverOnglet = "publies"; this.journal.push("go:" + v); },
  mmFiltrer(k) { if (this.mmFiltre !== k) { this.mmFiltre = k; this.journal.push("filtre:" + k); } },
  openAo(p) { this.ao.back = this.view; this.ao.project = p; this.view = "aodetail"; this.journal.push("ao:" + p.id); },
  atlOpen() { this.view = "atelier"; this.journal.push("atelier"); }, atlCardLoad() {}, _atlQuitter() { this.journal.push("quitte-atelier"); },
  openShared(it) { this.sharedAo = { projectId: it.project_id }; this.view = "sharedao"; this.journal.push("partage:" + it.project_id); },
  rnGo(t) { this.reseau.tab = t; }, _ecranOuvert() {}, loadProjects() {},
  api() { return Promise.reject(new Error("404")); } });
function demarrer() {     // comme boot()
  derniere = o.adresseCourante;
  o._adresseActive = true;
  history.replaceState(Object.assign({}, history.state || {}, { adjugo: 1, n: (history.state && history.state.n) || 0 }), "");
  o._ouvrirAdresse(etatDeAdresse(o._adresseDemandee())); vider();
}
const urls = () => entrees.map(e => e.url), etat = () => ({ urls: urls(), idx, view: o.view, n: history.state && history.state.n });
"""


def _naviguer(scenario, depart="/app", garde=None):
    obj = "const o = {\n" + ",\n".join(_method(n).rstrip(",") for n in _NAV) + "\n};\n"
    script = (_ADRESSES + "\n" + obj + _HARNAIS.replace("DEPART", json.dumps(depart)).replace("GARDE", json.dumps(garde or {}))
              + scenario)
    return _node(script)


def test_retour_arriere_sur_plusieurs_niveaux_et_lien_profond():
    r = _naviguer("""
const res = {};
demarrer(); res.depart = etat();
o.go("pipeline"); vider(); o.openAo(o.projects[1]); vider(); o.atlOpen(); vider(); res.avant = etat();
history.back(); res.b1 = etat(); history.back(); res.b2 = etat(); history.back(); res.b3 = etat();
history.forward(); res.f1 = etat(); res.journal = o.journal.slice(-6);
o.openAo(o.projects[1]); vider(); res.ouvert = etat(); o.aoBack(); res.retour = etat();
console.log(JSON.stringify(res));
""", depart="/app/marches/7")
    # Lien profond : le marché s'ouvre, l'adresse reste, aucune entrée ajoutée.
    assert r["depart"] == {"urls": ["/app/marches/7"], "idx": 0, "view": "aodetail", "n": 0}
    assert r["avant"]["urls"] == ["/app/marches/7", "/app/marches", "/app/marches/9", "/app/marches/9/dossier-de-presentation"]
    assert r["avant"]["n"] == 3
    # Précédent, trois fois : l'atelier, puis la liste, puis le premier marché ; aucune entrée ajoutée en revenant.
    assert r["b1"] == {"urls": r["avant"]["urls"], "idx": 2, "view": "aodetail", "n": 2}
    assert r["b2"]["view"] == "pipeline" and r["b2"]["idx"] == 1
    assert r["b3"]["view"] == "aodetail" and r["b3"]["idx"] == 0
    assert r["f1"]["view"] == "pipeline" and r["f1"]["urls"] == r["avant"]["urls"]   # suivant
    assert "quitte-atelier" in r["journal"]                                         # brouillon de l'atelier gardé
    # « Retour » de la page du marché = le bouton précédent quand on vient d'un écran de l'application.
    assert r["ouvert"]["urls"][-1] == "/app/marches/9" and r["retour"]["view"] == "pipeline"
    assert r["retour"]["urls"] == r["ouvert"]["urls"]


def test_adresse_inconnue_marche_introuvable_onglets_et_partenaire():
    r = _naviguer("""
const res = {};
demarrer(); res.inconnue = etat();
o.go("sourcing"); o.trouverOnglet = "avenir"; vider(); res.avenir = etat();       // un clic : une seule entrée
o.trouverOnglet = "alertes"; vider(); res.alertes = etat();
o.openShared(o.shared[0]); vider(); res.partage = etat(); o.partageRetour(); res.partageRetour = etat();
o.go("admin"); vider(); res.admin = etat();
console.log(JSON.stringify(res));
""", depart="/app/n-importe-quoi")
    assert r["inconnue"] == {"urls": ["/app"], "idx": 0, "view": "dashboard", "n": 0}     # adresse remise d'aplomb
    assert r["avenir"]["urls"] == ["/app", "/app/trouver/a-venir"]
    assert r["alertes"]["urls"] == ["/app", "/app/trouver/a-venir", "/app/trouver/alertes"]
    assert r["partage"]["urls"][-1] == "/app/marches/partenaire/5"                  # l'identifiant, jamais le jeton
    assert all("jeton" not in u for u in r["partage"]["urls"])
    assert r["partageRetour"]["view"] == "sourcing" and r["partageRetour"]["idx"] == 2
    assert r["admin"]["view"] == "dashboard"                                        # réservé à l'administrateur


def test_marche_introuvable_et_adresse_gardee_avant_la_connexion_google():
    r = _naviguer("""
demarrer();
setImmediate(() => { vider(); console.log(JSON.stringify(Object.assign(etat(), { journal: o.journal }))); });
""", depart="/app/marches/99")
    assert r["view"] == "pipeline" and r["urls"] == ["/app/marches"] and r["idx"] == 0   # remplacée, pas empilée
    assert "message:Ce marché n'est plus accessible" in r["journal"]
    # Retour de Google sur /app : l'adresse demandée avant de partir est rouverte ; une adresse étrangère, jamais.
    g = _naviguer("demarrer(); console.log(JSON.stringify(etat()));", depart="/app", garde={"adjugo_adresse": "/app/marches/7"})
    assert g["view"] == "aodetail" and g["urls"] == ["/app/marches/7"]
    for mauvaise in ("https://ailleurs.example/app/marches/7", "//ailleurs.example", "/invite/abc"):
        x = _naviguer("demarrer(); console.log(JSON.stringify(etat()));", depart="/app", garde={"adjugo_adresse": mauvaise})
        assert x["view"] == "dashboard" and x["urls"] == ["/app"], mauvaise


def test_le_demarrage_lit_l_adresse_et_preserve_les_liens_envoyes():
    boot = JS[JS.index("    async boot() {"):JS.index("    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES")]
    assert "this._ouvrirAdresse(_demande);" in boot and 'this.go("dashboard");' not in boot
    assert boot.index("this._adresseActive = true;") < boot.index("this._ouvrirAdresse(_demande);")
    # ?shared=<jeton> (lien d'invitation « ouvert dans mon Adjugo ») ouvre le dossier, et le jeton quitte l'adresse.
    assert 'const st = new URLSearchParams(location.search).get("shared");' in boot
    assert 'history.replaceState(history.state, "", "/app");' in boot
    # Relecture de la vague 2a : l'adresse porte aussi le repère de CETTE invitation (deux invitations acceptées sur le
    # même marché : ?shared= ouvre celle du jeton ; tests/test_reorganisation_v2a_relecture.py).
    assert ('_demande = it ? { view: "sharedao", partage: it.project_id, cle: clePartage(it.token) } : '
            '{ view: "pipeline", filtre: "partenaire" };') in boot
    # ?verify=, ?reset=, #gcode=, ?gerror= et ?inscription sont lus au montage, avant le démarrage, comme avant.
    mounted = JS[JS.index("  mounted() {\n    this.applyTheme();"):JS.index("  updated() {")]
    for m in ('get("reset")', 'get("verify")', 'get("gcode")', 'get("gerror")', "inscriptionDemandee(location)"):
        assert m in mounted, m
    assert mounted.index('window.addEventListener("popstate"') < mounted.index('get("reset")')
    # Routage par chemin : aucun « # » (le fragment porte #gcode=) ; pushState seulement dans _adresseSynchro.
    assert JS.count("history.pushState(") == 1 and "history.pushState(" in _method("_adresseSynchro")
    assert "location.hash =" not in JS and "hashchange" not in JS
    # Connexion Google : l'adresse demandée est gardée le temps de l'aller-retour (onglet du navigateur seulement).
    g = JS[JS.index("    googleLogin() {"):JS.index("    async resendVerification() {")]
    assert 'sessionStorage.setItem("adjugo_adresse", location.pathname)' in g and "etatDeAdresse(location.pathname)" in g
    # L'observateur : une seule source, l'adresse de l'écran ouvert.
    assert "adresseCourante(adr) { this._adresseSynchro(adr); }," in JS


# ═══ 1. Courriels : la page du marché, les anciens liens inchangés ═════════════════════════════════════════════

def _fstrings(rel):
    arbre = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{" + ast.unparse(v.value) + "}"
                               for v in n.values))
    return out


def test_courriels_au_chef_de_file_menent_a_la_page_du_marche():
    attendus = {"app/routers/invites.py": "{base}/app/marches/{inv.project_id}",
                "app/routers/convention.py": "{base}/app/marches/{project.id}",
                "app/services/atelier_groupement.py": "{base}/app/marches/{acces.project.id}/dossier-de-presentation",
                "app/services/carnet_notes.py": "{base}/app/marches/{p.id}"}
    for rel, lien in attendus.items():
        assert any(lien in f for f in _fstrings(rel)), rel
    # Les liens qui ouvrent un écran précis ne changent pas : confirmation, mot de passe, invitation, Google.
    assert any("{base}/app?verify={token}" in f for f in _fstrings("app/routers/auth.py"))
    assert any("{base}/app?reset={raw}" in f for f in _fstrings("app/routers/auth.py"))
    assert any("{base}/invite/{inv.token}" in f for f in _fstrings("app/routers/convention.py"))
    assert '_front("/app#gcode=" + _issue_exchange_code(user))' in (ROOT / "app/routers/google_auth.py").read_text(encoding="utf-8")


# ═══ 2. Un seul axe d'étapes : le modèle, la clé migrée ═══════════════════════════════════════════════════════

AXE = ["suivi", "nouveau", "decide", "en_cours", "depose", "gagne", "perdu", "abandonne"]
LIBELLES = ["À venir", "Repéré", "Décidé", "En préparation", "Déposé", "Gagné", "Perdu", "Abandonné"]


def test_un_seul_axe_le_meme_au_serveur_et_a_l_ecran():
    from app.models import (AXE_ETAPES, STATUTS_CLOS, STATUTS_DEPOSES, STATUTS_LIBELLES, InvoiceStatus,
                            ProjectStatus, statut_normalise)
    assert list(AXE_ETAPES) == AXE and [STATUTS_LIBELLES[k] for k in AXE] == LIBELLES
    assert STATUTS_DEPOSES == ("depose", "gagne", "perdu") and STATUTS_CLOS == ("depose", "gagne", "perdu", "abandonne")
    assert ProjectStatus("envoye") is ProjectStatus.depose and "envoye" not in ProjectStatus.__members__
    assert [statut_normalise(x) for x in ("envoye", "depose", ProjectStatus.suivi, " decide ", "", None, "bidule")] == \
        ["depose", "depose", "suivi", "decide", None, None, None]
    assert InvoiceStatus.envoye.value == "envoye"                                   # un devis s'envoie
    r = _node(_AXE + "\nconsole.log(JSON.stringify(AXE_ETAPES));")
    assert [x["k"] for x in r] == AXE and [x["label"] for x in r] == LIBELLES
    # Le choix « Statut », Mes marchés et l'entonnoir de l'accueil lisent cette seule liste.
    assert "statuses2: AXE_ETAPES.map(e => e.k)," in JS and "statuses: [" not in JS
    assert "statusLabel(s) { return libelleStatut(s); }" in JS
    entete = zone(HTML, "marche-entete")
    assert '<option v-for="s in statuses2" :key="s" :value="s">{{ statusLabel(s) }}</option>' in entete
    assert '<option v-for="s in statuses2" :key="s" :value="s">{{ statusLabel(s) }}</option>' in zone(HTML, "tiroir-projet")


def _constantes(rel):
    return [n.value for n in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_la_cle_envoye_n_existe_plus_pour_un_marche():
    # Serveur : la chaîne « envoye » n'est plus qu'au modèle (lecture d'une ancienne clé) ; les devis gardent la leur
    # par l'énumération InvoiceStatus (jamais une chaîne).
    fautes = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel == "app/models/__init__.py":
            continue
        if "envoye" in _constantes(rel):
            fautes.append(rel)
    assert not fautes, fautes
    modele = _constantes("app/models/__init__.py")
    assert modele.count("envoye") == 2                                               # _missing_ et InvoiceStatus
    # Écran : plus de statut « envoye » (devis et factures mis à part : invStatusLabel ; « st-envoye » reste un style).
    sans_devis = JS.replace('envoye: "Envoyé"', "")
    assert not re.search(r"""["']envoye["']|\benvoye:""", sans_devis)
    assert not re.search(r"""['"]envoye['"]""", HTML)
    assert ".pill.st-envoye,.pill.st-depose {" in CSS and ".pill.st-suivi {" in CSS and ".pill.st-decide {" in CSS


def test_api_statut_valide_ancienne_cle_et_carte_avant_publication(client, auth):
    h = auth["headers"]
    p = client.post("/api/projects/", json={"name": "Réfection de voirie (A1)"}, headers=h).json()
    assert p["status"] == "nouveau"                                                 # Repéré par défaut
    # Décision 11 : une carte avant la publication, à l'étape « À venir ».
    s = client.post("/api/projects/", json={"name": "Groupe scolaire (fin de contrat)", "status": "suivi"}, headers=h).json()
    assert s["status"] == "suivi"
    for v in ("decide", "en_cours", "depose", "gagne", "abandonne", "nouveau"):
        r = client.put(f"/api/projects/{p['id']}", json={"status": v}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == v, (v, r.text)
    # Une page ouverte avant la mise en ligne envoie l'ancienne clé : elle est comprise.
    r = client.put(f"/api/projects/{p['id']}", json={"status": "envoye"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "depose"
    # Une valeur hors de l'axe est refusée proprement (422, message lisible), jamais un 500.
    for v in ("bidule", "Déposé", "ENVOYE"):
        r = client.put(f"/api/projects/{p['id']}", json={"status": v}, headers=h)
        assert r.status_code == 422, (v, r.status_code)
        assert "Statut inconnu" in r.text
    assert client.post("/api/projects/", json={"name": "x", "status": "publie"}, headers=h).status_code == 422
    # « status: null » ne vide jamais l'étape.
    assert client.put(f"/api/projects/{p['id']}", json={"status": None}, headers=h).json()["status"] == "depose"
    # Filtre de la liste : l'ancienne clé est lue, une clé inconnue ne trouve rien (sans erreur).
    ids = [x["id"] for x in client.get("/api/projects/?status=envoye", headers=h).json()]
    assert p["id"] in ids and all(x["status"] == "depose" for x in client.get("/api/projects/?status=depose", headers=h).json())
    assert client.get("/api/projects/?status=bidule", headers=h).json() == []
    assert [x["id"] for x in client.get("/api/projects/?status=suivi", headers=h).json()] == [s["id"]]


def test_statistiques_dans_l_ordre_de_l_axe_et_taux_sur_les_deposes(client, auth):
    h = auth["headers"]
    for nom, st in (("Perdu 1", "perdu"), ("Déposé 1", "depose"), ("Gagné 1", "gagne"), ("Repéré 1", None),
                    ("À venir 1", "suivi"), ("Décidé 1", "decide")):
        p = client.post("/api/projects/", json={"name": nom}, headers=h).json()
        if st:
            client.put(f"/api/projects/{p['id']}", json={"status": st}, headers=h)
    s = client.get("/api/agent/stats", headers=h).json()
    ordre = list(s["by_status"])
    assert ordre == [k for k in AXE if k in ordre] and set(ordre) == {"suivi", "nouveau", "decide", "depose", "gagne", "perdu"}
    assert s["win_rate"] == 33 and s["decided"] == 2                                # 1 gagné sur 3 déposés ou clos


def test_marquer_depose_et_annuler_suivent_la_nouvelle_cle():
    src = (ROOT / "app/routers/groupement.py").read_text(encoding="utf-8")
    assert "{Project.status: ProjectStatus.depose}" in src and '"status": "depose"' in src
    assert 'if status_v != "depose":' in src and "Project.status == ProjectStatus.depose" in src
    from app.services.alerts import _CLOSED
    from app.services.groupement_members import CLOSED_STATUSES
    from app.services.partner_network import _DEPOSE_STATUSES, _status_values
    assert CLOSED_STATUSES == _DEPOSE_STATUSES == ("depose", "gagne", "perdu") and "abandonne" in _CLOSED
    assert [s.value for s in _status_values()] == ["depose", "gagne", "perdu"]


# ═══ 2. La migration : SQLite (aller, retour, rejeu) ; Postgres : docs/REORGANISATION_V2A.md, A1 ══════════════

def test_migration_axe_etapes_aller_retour_idempotente(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "axe.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    env.pop("ADJUGO_TEST_DB", None)

    def alembic(*a):
        r = subprocess.run([sys.executable, "-m", "alembic", *a], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        return r

    alembic("upgrade", "b3mesureecrans")
    e = sa.create_engine(f"sqlite:///{dbfile}")
    with e.begin() as c:
        c.execute(sa.text("INSERT INTO users (id, email, hashed_password, full_name, is_active) "
                          "VALUES (1, 'a@b.fr', 'x', 'A', 1)"))
        for i, st in enumerate(("nouveau", "en_cours", "envoye", "gagne", "perdu", "abandonne", "envoye"), start=1):
            c.execute(sa.text("INSERT INTO projects (id, user_id, name, status) VALUES (:i, 1, :n, :s)"),
                      {"i": i, "n": f"M{i}", "s": st})
        c.execute(sa.text("INSERT INTO invoices (id, user_id, reference, type, status, client_name, items, subtotal_ht, "
                          "tva_rate, tva_amount, total_ttc) VALUES (1, 1, 'D-1', 'devis', 'envoye', 'C', '[]', 0, 0, 0, 0)"))

    def statuts():
        with e.connect() as c:
            return ([r[0] for r in c.execute(sa.text("SELECT status FROM projects ORDER BY id"))],
                    c.execute(sa.text("SELECT status FROM invoices")).scalar())

    alembic("upgrade", "head")
    assert statuts() == (["nouveau", "en_cours", "depose", "gagne", "perdu", "abandonne", "depose"], "envoye")
    alembic("upgrade", "head")                                                      # rejeu : rien ne bouge
    alembic("stamp", "b3mesureecrans")
    alembic("upgrade", "head")
    assert statuts()[0] == ["nouveau", "en_cours", "depose", "gagne", "perdu", "abandonne", "depose"]
    with e.begin() as c:                                                            # les nouvelles étapes
        c.execute(sa.text("UPDATE projects SET status='suivi' WHERE id=1"))
        c.execute(sa.text("UPDATE projects SET status='decide' WHERE id=6"))
    alembic("downgrade", "b3mesureecrans")
    assert statuts() == (["nouveau", "en_cours", "envoye", "gagne", "perdu", "en_cours", "envoye"], "envoye")
    alembic("upgrade", "head")
    assert statuts()[0] == ["nouveau", "en_cours", "depose", "gagne", "perdu", "en_cours", "depose"]


def test_base_sqlite_deja_creee_normalisee_au_demarrage(tmp_path):
    import sqlalchemy as sa
    from app.core.dbsync import ensure_sqlite_statuts
    e = sa.create_engine(f"sqlite:///{tmp_path / 'dev.db'}")
    with e.begin() as c:
        c.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY, status VARCHAR(9))"))
        c.execute(sa.text("INSERT INTO projects (id, status) VALUES (1, 'envoye'), (2, 'nouveau')"))
    ensure_sqlite_statuts(e)
    ensure_sqlite_statuts(e)
    with e.connect() as c:
        assert [r[0] for r in c.execute(sa.text("SELECT status FROM projects ORDER BY id"))] == ["depose", "nouveau"]
    assert "ensure_sqlite_statuts(engine)" in (ROOT / "app/main.py").read_text(encoding="utf-8")


# ═══ 2. La barre affiche des statuts dérivés ; l'étape Décider ════════════════════════════════════════════════

def test_barre_du_marche_statuts_derives_sous_node():
    r = _node(_BARRE + """
const cas = JSON.parse(process.argv[1]);
console.log(JSON.stringify(cas.map(c => barreDuMarche(c[0], c[1], c[2]).map(x => [x.k, x.statut, x.courante]))));
""", json.dumps([["nouveau", False, 1], ["nouveau", True, 1], ["decide", False, 1], ["en_cours", True, 3],
                 ["en_cours", True, 5], ["depose", True, 5], ["gagne", False, 1], ["abandonne", True, 1],
                 ["suivi", False, 1]]))
    T, E, A = "Terminé", "En cours", "À faire"
    assert r[0] == [["lire", E, True], ["decider", A, False], ["preparer", A, False], ["deposer", A, False]]
    assert r[1] == [["lire", T, False], ["decider", E, True], ["preparer", A, False], ["deposer", A, False]]
    assert r[2] == [["lire", A, False], ["decider", T, False], ["preparer", E, True], ["deposer", A, False]]
    assert r[3] == [["lire", T, False], ["decider", T, False], ["preparer", E, True], ["deposer", A, False]]
    assert r[4] == [["lire", T, False], ["decider", T, False], ["preparer", T, False], ["deposer", E, True]]
    assert r[5] == [["lire", T, False], ["decider", T, False], ["preparer", T, False], ["deposer", T, True]]
    assert r[6] == [["lire", T, False], ["decider", T, False], ["preparer", T, False], ["deposer", T, False]]
    assert r[7] == [["lire", "", False], ["decider", "", False], ["preparer", "", False], ["deposer", "", False]]
    assert r[8][0] == ["lire", E, True]                                             # À venir : on lit ce qu'on sait
    barre = zone(HTML, "marche-etapes")
    for k in ("lire", "decider", "preparer", "deposer"):
        assert f"aoBarreEtat('{k}').statut" in barre and f":class=\"['mk-'+(aoBarreEtat('{k}').etat||'aucun')" in barre
    assert barre.count('<span class="sr-only"> : </span>') == 4                       # lu par un lecteur d'écran
    assert ".mk-et .mk-st {" in CSS and ".mk-et.mk-fait .mk-n {" in CSS


def test_decider_seul_a_plusieurs_ecarter_et_gestes_de_preparer():
    r = _node(_AXE + """
const st = ["suivi", "nouveau", "decide", "en_cours", "depose", "gagne", "perdu", "abandonne"], ch = ["seul", "plusieurs", "ecarter", "remettre"];
console.log(JSON.stringify({ d: st.map(s => ch.map(c => statutApresDecision(s, c))), p: st.map(statutEnPreparation),
                             l: st.map(libelleStatut).concat([libelleStatut("bidule")]) }));
""")
    # Un marché « À venir » le reste jusqu'à sa publication (on y invite déjà ses partenaires) ; on peut l'écarter.
    assert r["d"] == [[None, None, "abandonne", None], ["decide", "decide", "abandonne", None],
                      [None, None, "abandonne", None], [None, None, "abandonne", None], [None] * 4, [None] * 4, [None] * 4,
                      ["decide", "decide", None, "nouveau"]]
    assert r["p"] == [None, "en_cours", "en_cours", None, None, None, None, None]   # « À venir » ne bouge pas
    assert r["l"] == LIBELLES + ["bidule"]
    d = zone(HTML, "marche-decision")
    assert d in zone(HTML, "marche-decider") and zone(HTML, "marche-decider").index(d) < zone(HTML, "marche-decider").index(
        'class="card pad muted small mk-vide"')
    assert 'v-if="aoDecisionVisible()"' in d
    for clic, ic, mot in (("seul", "user", "Préparer seul"), ("plusieurs", "handshake", "Préparer à plusieurs"),
                          ("ecarter", "archive", "Écarter"), ("remettre", "archive-restore", "Remettre")):
        assert f"""@click="aoDecider('{clic}')"><i data-lucide="{ic}"></i>{mot}</button>""" in d
    # Relecture de la vague 2a : _aoChangerStatut reçoit aussi les étapes de départ du geste (`depuis`).
    dec = JS[JS.index("    async aoDecider(choix) {"):JS.index("    async _aoChangerStatut(cible, message, depuis) {")]
    assert "this._convAsk({" in dec and 'run: () => this._aoChangerStatut("abandonne"' in dec   # confirmé avant
    assert "this.aoInviter();" in dec and 'this.rnScrollTo("etPreparer");' in dec
    # Les gestes de Préparer : estimer, préparer les formulaires, inviter, ouvrir l'atelier.
    for debut, fin in (("    async aoEstimate() {", "    async aoSaveEstimate() {"), ("    async aoGenerate(opts) {", "    _downloadB64("),
                       ("    atlOpen() {", "    _atlQuitter() {")):
        assert "this.aoAvancer();" in JS[JS.index(debut):JS.index(fin)], debut
    # Réunion A1 × A2 : inviter passe par la fenêtre unique (rinvSend), sur la page du marché comme ailleurs.
    envoi = JS[JS.index("    async rinvSend() {"):JS.index("    rinvViaReseau() {")]
    assert "this._marcheEnPreparation(pid);" in envoi and envoi.index("this._marcheEnPreparation(pid);") < envoi.index("} catch (e) {")
    m = JS[JS.index("    async _marcheEnPreparation(pid) {"):JS.index("    aoTacheVoir(t) {")]
    assert "this.aoAvancer();" in m and "statutEnPreparation(p.status)" in m


def test_mes_marches_un_groupe_par_etape_et_a_venir():
    # Réunion A1 × A2 : Mes marchés est la liste filtrable de A2, groupée par étape dans l'ordre de l'axe ; un groupe
    # n'existe que s'il a des marchés (« À venir » et « Abandonné » n'apparaissent que s'il y en a, comme les colonnes).
    assert 'v-for="g in mmGroupes()"' in zone(HTML, "vue-pipeline") and "kanbanColonnes" not in JS + HTML
    assert ("listeMesMarches(this.projects, this.shared, (this.consortiums || {}).consortiums, this.mmFiltre, this.statuses2)"
            in _method("mmGroupes"))
    g = _node(tranche(JS, "const MM_FILTRES = [", "function listeMesMarches(") + _AXE + """
const ordre = AXE_ETAPES.map(e => e.k);
console.log(JSON.stringify(listeMesMarches([{ id: 1, status: "en_cours" }, { id: 2, status: "suivi" }, { id: 3, status: "decide" }],
  [{ token: "a", groupement: { state: "depose" } }], [], "tous", ordre).map(x => [x.k, x.pilotes.map(p => p.id), x.partenaires.length])));
""")
    assert g == [["suivi", [2], 0], ["decide", [3], 0], ["en_cours", [1], 0], ["depose", [], 1]]
    radar = zone(HTML, "trouver-radar")
    b = zone(HTML, "trouver-preparer-a-venir")
    assert b in radar and '@click="srcAVenirPreparer(r)"' in b and "Préparer à plusieurs" in b
    f = JS[JS.index("    async srcAVenirPreparer(r) {"):JS.index("    async srcSearch(arg) {")]
    assert 'status: "suivi"' in f and 'x.status === "suivi"' in f and "this.aoInviter();" in f


# ═══ 3. Barre basse sur téléphone ; la cloche et « À faire » ═════════════════════════════════════════════════

def test_barre_basse_de_cinq_sur_telephone():
    b = zone(HTML, "menu-bas")
    assert b.startswith('<nav data-test="menu-bas" class="barre-basse" aria-label="Menu principal">')
    entrees = re.findall(r'<button type="button" class="bb-i"[^>]*@click="([^"]+)"><i data-lucide="([\w-]+)"></i><span>([^<]+)</span>', b)
    assert entrees == [("go('dashboard')", "house", "Accueil"), ("rubriqueGo('trouver')", "search", "Trouver"),
                       ("go('pipeline')", "folder-kanban", "Mes marchés"), ("go('cotraitants')", "handshake", "Partenaires"),
                       ("mobileNav=!mobileNav", "menu", "Menu")]
    assert b.count(":aria-current=") == 4 and ":aria-expanded=\"mobileNav?'true':'false'\"" in b
    # Pastilles : ce qui attend une action, jamais un total ni zéro (les mêmes que le menu).
    assert re.findall(r'<span v-if="([^"]+)" class="bb-badge">', b) == ["mmActions()", "expiring.length"]
    assert b not in zone(HTML, "menu") and b not in zone(HTML, "contenu")
    i = CSS.index(".barre-basse { display:none; }")
    bloc = CSS[i:CSS.index("\n}\n", i)]
    assert "@media (max-width:860px) {" in bloc and "grid-template-columns:repeat(5, minmax(0,1fr))" in bloc
    for regle in (".top .menu-btn { display:none; }", "env(safe-area-inset-bottom, 0px)",
                  ".content { padding-bottom:calc(84px", ".app ~ .toast { bottom:calc(74px",
                  ".bandeau-cookies.avec-menu { bottom:calc(72px", "min-height:52px"):
        assert regle in bloc, regle


def test_la_cloche_a_faire_et_activite():
    entete = zone(HTML, "entete")
    f = zone(HTML, "fenetre-notifications")
    assert f in entete and 'role="dialog" aria-label="À faire et activité"' in f
    assert re.findall(r'role="tab"[^>]*>\s*<span>([^<]+)</span>', f) == ["À faire", "Activité"]
    # Vague 2b (B1, étude § 7.3) : la phrase de l'état vide est celle de l'étude, la même que sur l'accueil.
    assert "Rien n'attend de réponse de votre part." in f and "Aucune activité récente de vos partenaires." in f
    assert '@click="aFaireOuvrir(t)"' in f and 'v-for="n in notifs"' in f
    # La pastille de la cloche ne compte que ce qui est à faire ; l'activité nouvelle n'est qu'un point, sans nombre.
    assert "notifUnseen>99" not in entete and '<span v-if="aFaire().length" class="notif-pastille"' in entete
    assert '<span v-if="notifUnseen>0" class="notif-point" aria-hidden="true"></span>' in f
    t = JS[JS.index("    toggleNotifs() {"):JS.index("    aFaire() {")]
    assert 'this.notifsVoir(this.aFaire().length ? "a_faire" : "activite");' in t
    assert t.index('if (onglet !== "activite") return;') < t.index('localStorage.setItem("adjugo_notifs_seen"')
    assert ".notif-zone { position:static; }" in CSS                                 # 375 px : sous la barre du haut


def test_l_accueil_lit_la_meme_liste_a_faire():
    a = zone(HTML, "accueil-a-faire")
    dash = zone(HTML, "vue-dashboard")
    assert a in dash and dash.index(zone(HTML, "accueil-premiers-pas")) < dash.index(a) < dash.index(zone(HTML, "accueil-reseau"))
    # Vague 2b (B1, étude § 7.3) : jamais « 0 » ; quand rien n'attend, le bloc le dit en une phrase.
    assert a.startswith('<div data-test="accueil-a-faire" class="card pad dash-block"')
    assert '<p v-if="!aFaire().length" class="muted small afaire-vide">Rien n\'attend de réponse de votre part.</p>' in a
    assert 'v-for="t in aFaire().slice(0, 6)"' in a and '@click="aFaireOuvrir(t)"' in a
    m = _method("aFaire")
    assert "listeAFaire({ shared: this.shared, recues: this.reseau.recues.list, projects: this.projects," in m
    boot = JS[JS.index("    async boot() {"):JS.index("    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES")]
    assert "this.loadExpiring();" in boot                                            # sur tous les écrans


def test_liste_a_faire_sous_node():
    auj = "2026-10-20"
    d = {
        "shared": [{"project_id": 5, "project": "Salle de sports", "mandataire": "BTP Ouest",
                    "groupement": {"a_valider": True}, "redaction": {"a_faire": 1}},
                   {"project_id": 6, "project": "Voirie", "groupement": {"a_valider": False}, "redaction": None}],
        "recues": [{"token": "t1", "project": "Gymnase", "mandataire": "Kerhel SA", "statut": "envoyee"},
                   {"token": "t2", "project": "École", "statut": "acceptee"}, {"token": "t3", "_declined": True}],
        "projects": [{"id": 1, "name": "Toiture", "status": "en_cours", "deadline": "2026-10-25"},
                     {"id": 2, "name": "Lointain", "status": "nouveau", "deadline": "2026-11-30"},
                     {"id": 3, "name": "Déposé", "status": "depose", "deadline": "2026-10-21"},
                     {"id": 4, "name": "Passé", "status": "en_cours", "deadline": "2026-10-19"},
                     {"id": 8, "name": "Aujourd'hui", "status": "decide", "deadline": "2026-10-20"},
                     {"id": 9, "name": "Demain", "status": "nouveau", "deadline": "2026-10-21"}],
        "enCours": [{"project_id": 1, "name": "Toiture", "n_membres": 3, "n_parts": 1},
                    {"project_id": 7, "name": "Complet", "n_membres": 2, "n_parts": 2}],
        "expiring": [{"name": "Kbis", "expiration_date": "2026-10-30"}, {"name": "URSSAF", "expiration_date": "2026-10-18"}],
    }
    r = _node(_A_FAIRE + """
const a = JSON.parse(process.argv[1]);
console.log(JSON.stringify({ l: listeAFaire(a.d, a.auj).map(t => [t.k, t.titre, t.detail, t.cta, t.cible]), vide: listeAFaire({}, a.auj) }));
""", json.dumps({"d": d, "auj": auj}))
    assert r["vide"] == []
    assert [x[0] for x in r["l"]] == ["accord-5", "redaction-5", "invitation-t1", "date-8", "date-9", "date-1",
                                      "parts-1", "pieces"]
    l = {x[0]: x[1:] for x in r["l"]}
    assert l["accord-5"] == ["Votre accord est demandé", "Salle de sports · chef de file : BTP Ouest",
                             "Lire et donner mon accord", {"view": "sharedao", "partage": 5}]
    assert l["invitation-t1"][3] == {"view": "shared"}             # Mes marchés, filtre « Où je suis partenaire » (A2)
    assert [l["date-8"][0], l["date-9"][0], l["date-1"][0]] == ["Date limite aujourd'hui", "Date limite demain",
                                                                "Date limite dans 5 jours"]
    assert l["parts-1"][:2] == ["Parts reçues 1 sur 3", "Toiture"]                  # « N sur M » (décision 8)
    assert l["pieces"][:2] == ["2 pièces à renouveler", "URSSAF · expirée le 18/10"]


def test_tableau_de_bord_compte_les_parts_recues_sans_rien_exposer_de_plus():
    src = (ROOT / "app/routers/groupement.py").read_text(encoding="utf-8")
    i = src.index('        en_cours.append({"project_id": p.id, "name": p.name,')
    item = src[i:src.index("})", i)]
    assert '"n_parts": st.get("n_submitted") or 0,' in item
    # Rien d'un partenaire : ni nom, ni prix, ni montant ; seulement un compte, déjà affiché sur la page du marché.
    assert "prix" not in item and "company" not in item and "montant" not in item
    # « À faire » ne lit que des statuts déjà envoyés à l'écran (aucune nouvelle route, aucune nouvelle donnée).
    f = tranche(JS, "const A_FAIRE_JOURS = 7;", "function listeAFaire(")
    assert "api(" not in f and "fetch(" not in f


# ═══ Traductions (décision 16), mesure, démonstration ════════════════════════════════════════════════════════

NOUVEAUX = ["Repéré", "Décidé", "En préparation", "À faire", "Activité", "Rien n'attend votre action pour l'instant.",
            "Votre accord est demandé", "Une partie du dossier de présentation vous attend",
            "Invitation à répondre ensemble", "Date limite aujourd'hui", "Date limite demain", "Lire et donner mon accord",
            "Ouvrir", "Voir l'invitation", "Remettre", "Marché écarté", "Écarter ce marché ?", "Trouver", "Menu principal",
            "Marché ajouté à Mes marchés, à l'étape « À venir »", "Statut : Décidé", "À venir", "Déposé", "Abandonné"]


def test_traductions_des_nouveaux_libelles():
    from tests.test_reorganisation_v1_socle import _dico
    d = _dico()
    for k in NOUVEAUX:
        assert d["nl"].get(k) and d["es"].get(k), k
    assert d["nl"]["En préparation"] == "In voorbereiding" and d["es"]["Repéré"] == "Detectado"


def test_chaque_icone_nouvelle_existe_dans_lucide():
    """Règle 1 des icônes (§ 8 de l'étude) : chaque nom d'icône posé par ce chantier existe dans Lucide 1.20.0."""
    lucide = (STATIC / "vendor" / "lucide-1.20.0.min.js").read_text(encoding="utf-8")
    zones_a1 = "".join(zone(HTML, n) for n in ("menu-bas", "fenetre-notifications", "accueil-a-faire", "marche-decision",
                                               "trouver-preparer-a-venir"))
    noms = set(re.findall(r'data-lucide="([a-z0-9-]+)"', zones_a1)) | set(re.findall(r'ic: "([a-z0-9-]+)"', _A_FAIRE))
    assert noms >= {"house", "search", "folder-kanban", "handshake", "menu", "bell", "user", "archive", "archive-restore",
                    "signature", "file-pen-line", "inbox", "clock", "folder-lock"}
    for n in noms:
        pascal = "".join(x.capitalize() for x in n.split("-"))
        assert re.search(r"\b" + pascal + r"\b", lucide), n


def test_aucun_ecran_nouveau_donc_mesure_inchangee():
    from app.services.mesure_usage import ECRANS
    assert set(VUES_HTML) <= ECRANS                                                 # chaque écran mesuré, comme avant
    assert "_ecranOuvert" not in _method("_adresseSynchro")                          # une adresse ne compte pas deux fois


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


def test_la_demo_sur_l_axe_et_ses_adresses(client, vitrine):
    projets = client.get("/api/projects/", headers=vitrine).json()
    assert projets and all(p["status"] in AXE for p in projets)
    stats = client.get("/api/agent/stats", headers=vitrine).json()
    assert list(stats["by_status"]) == [k for k in AXE if k in stats["by_status"]]
    # Chaque marché de la démo a son adresse, et la page la sert.
    for p in projets:
        assert client.get(f"/app/marches/{p['id']}").status_code == 200
    kerhel = next(p for p in projets if "Gymnase de Kerhel" in p["name"])
    fiche = client.get(f"/api/projects/{kerhel['id']}", headers=vitrine).json()
    st = client.get(f"/api/projects/{kerhel['id']}/groupement/state", headers=vitrine).json()
    r = _node(_BARRE + "\nconsole.log(JSON.stringify(barreDuMarche(process.argv[1], process.argv[2] === '1', Number(process.argv[3])).map(x => x.statut)));",
              fiche["status"], "1" if (fiche.get("ai_analysis") or {}).get("dce_available") else "0", str(st.get("etape") or 1))
    assert r == ["Terminé", "Terminé", "Terminé", "En cours"]                        # convention validée : Déposer
    # Le tableau de bord des groupements compte les parts (« À faire »), sans nom ni prix.
    g = client.get("/api/groupement/tableau-de-bord", headers=vitrine).json()
    for it in g["en_cours"]:
        assert set(it) >= {"n_parts", "n_membres"} and "prix" not in json.dumps(it)
    # La démo peut décider (changer l'étape reste permis à la vitrine) ; remise à neuf par la fixture.
    toiture = next(p for p in projets if "Réfection toiture" in p["name"])
    r = client.put(f"/api/projects/{toiture['id']}", json={"status": "decide"}, headers=vitrine)
    assert r.status_code == 200 and r.json()["status"] == "decide"
