"""
Réorganisation de l'interface — vague 1, chantier MENU ET ACCUEIL (contrat : docs/REORGANISATION_V1.md, § 1.3 à 1.8).

1.3 Le menu range des OBJETS (architecture C corrigée) : Accueil, Trouver des marchés, Mes marchés, Partenaires, Mes
    documents, Mon entreprise, et le groupe « Réglages » replié (état gardé) ; chaque ancienne vue est un onglet de sa
    rubrique, ouverte par go() sans changement ; la rubrique reste surlignée ; pastilles d'action seulement ; le
    radar des fins de contrat quitte le haut des résultats pour l'onglet « À venir » ; traductions (décision 16).
1.6 Accueil allégé : plus de ruban, de liens doublons ni de 4e raccourci ; « Préparer à plusieurs ».
1.7 Sous-titres de vue dans une bulle (i), sans promesse.
1.8 Transition : « Ce qui a changé », anciens noms en bulle.

Aucun appel réseau : lecture des fichiers statiques et exécution des fonctions sous Node.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_reseau_ecrans import _method
from tests.textes_visibles import textes_html, textes_js
from tests.zones import noms, zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")

# Fonctions pures du menu (en tête de app.js) : RUBRIQUES, rubriqueDe, ongletDe, ancienNom, noteReorgVisible.
_PUR = JS[JS.index("// ══════════ Menu par rubriques (réorganisation, vague 1, 1.3) ══════════"):
          JS.index("\n}\n", JS.index("function noteReorgVisible(")) + 3]
# Méthodes de l'application qui pilotent le menu, les onglets, l'en-tête et les pastilles.
_METHODES = ["rubrique", "_ongletPermis", "ongletsVisibles", "ongletActif", "ongletGo", "rubriqueGo", "enteteTitre",
             "enteteAideVue", "enteteAncien", "enteteAide", "partenaireActions", "mmActions", "ongletPastille",
             "rnRecuesCount", "adminEcranNom", "noteReorgVue", "_noteReorgSauver", "noteReorgMarquer", "noteReorgFermer"]


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _app(scenario):
    """Un objet qui porte les méthodes du menu, avec l'état utile ; go() et la mesure sont enregistrés."""
    i, j = JS.index("      titles: {"), JS.index("    };\n  },\n  computed: {")
    donnees = JS[i:j].strip().rstrip(",")
    return (_PUR + "\nconst o = {\n" + ",\n".join(_method(n).rstrip(",") for n in _METHODES) + "\n};\n"
            "Object.assign(o, {" + donnees + "});\n"
            "Object.assign(o, { view: 'dashboard', trouverOnglet: 'publies', features: { projets_a_venir: false },\n"
            # Un compte qui a connu l'ancienne organisation (créé avant REORG_V1_DEPUIS) : il voit la transition.
            "  user: { is_admin: false, email: 'a@b.fr', created_at: '2026-06-24T08:00:00' }, shared: [], expiring: [],\n"
            "  mobileNav: true, reorgEtat: {},\n"
            "  reseau: { recues: { list: [] } }, journal: [] });\n"
            "o.go = function (v) { this.view = v; this.journal.push('go:' + v); this.mobileNav = false; };\n"
            "o._ecranOuvert = function (v) { this.journal.push('mesure:' + v); };\n"
            "const store = {}; globalThis.localStorage = { setItem: (k, v) => { store[k] = v; }, getItem: (k) => store[k] };\n"
            + scenario)


# ═══ 1.3 Le menu : six rubriques, puis le groupe « Réglages » ═══════════════════════════════════════════════════

def _rubriques():
    return _node(_PUR + "\nconsole.log(JSON.stringify(RUBRIQUES));")


def test_menu_six_rubriques_dans_l_ordre_puis_reglages():
    rub = _rubriques()
    assert [r["k"] for r in rub] == ["accueil", "trouver", "marches", "partenaires", "documents", "entreprise", "reglages"]
    menu = zone(HTML, "menu")
    reglages = zone(HTML, "menu-reglages")
    haut = menu[:menu.index(reglages)]
    entrees = re.findall(r'<a class="nav-item" :class="\{active:rubrique\(\)===\'(\w+)\'\}" @click="([^"]+)">'
                         r'<i data-lucide="([\w-]+)"></i>([^<]+)', haut)
    assert [(k, ic, lib) for k, _go, ic, lib in entrees] == [(r["k"], r["ic"], r["label"]) for r in rub[:6]]
    # Chaque entrée ouvre le premier onglet de sa rubrique.
    for (k, go, _ic, _lib), r in zip(entrees, rub[:6]):
        assert go in (f"go('{r['onglets'][0]['view']}')", f"rubriqueGo('{k}')"), go
    # Icônes de l'étude, § 8 : plus de layout-dashboard, target, square-kanban, briefcase ni « Plus ».
    for ancien in ("layout-dashboard", "target", "square-kanban", "briefcase", "navMore", ">Plus<", "Tableau de bord"):
        assert ancien not in menu, ancien
    assert "navMore" not in JS
    # « Réglages » : un vrai bouton de groupe, replié par défaut, état gardé d'une visite à l'autre.
    assert re.search(r'<button type="button" class="nav-item nav-groupe" :class="\{active:!navReglages && '
                     r'rubrique\(\)===\'reglages\'\}" :aria-expanded="navReglages\?\'true\':\'false\'" '
                     r'aria-controls="nav-reglages-liste" @click="toggleReglages\(\)"><i data-lucide="settings"></i>Réglages',
                     reglages)
    # v-show : la liste existe toujours (aria-controls la désigne), cachée quand le groupe est replié.
    liste = reglages[reglages.index('<div v-show="navReglages" id="nav-reglages-liste"'):]
    assert re.findall(r"go\('(\w+)'\)", liste) == ["team", "billing", "compte", "admin"]
    for lib in (">Collègues<", ">Abonnement<", ">Mon compte<", ">Administration<", "Mon avis", "theme-toggle"):
        assert lib in liste, lib
    assert '<a v-if="user.is_admin" class="nav-item" :class="{active:view===\'admin\'}" @click="go(\'admin\')">' in liste
    assert ('navReglages: (function(){ try { return localStorage.getItem("adjugo_nav_reglages") === "1"; } '
            'catch(e){ return false; } })(),') in JS
    assert 'localStorage.setItem("adjugo_nav_reglages", this.navReglages ? "1" : "0")' in _method("toggleReglages")
    # Les entrées de Réglages sont celles de la rubrique « reglages » (même ordre).
    assert [t["view"] for t in rub[6]["onglets"]] == ["team", "billing", "compte", "admin"] and rub[6]["groupe"]


def test_chaque_vue_a_sa_rubrique_et_s_atteint_en_deux_clics_au_plus():
    from app.services.mesure_usage import ECRANS
    rub = _rubriques()
    vues_app = set(re.findall(r"view===?'([a-z]+)'", HTML)) | set(re.findall(r'this\.view = "([a-z]+)"', JS))
    for v in vues_app - {"agent"}:
        assert any(v in r["vues"] for r in rub), f"vue {v} sans rubrique"
    menu = zone(HTML, "menu")
    reglages = zone(HTML, "menu-reglages")
    haut = menu[:menu.index(reglages)]
    un_clic = set(re.findall(r"go\('(\w+)'\)", haut)) | {r["onglets"][0]["view"] for r in rub
                                                          if f"rubriqueGo('{r['k']}')" in haut}
    deux_clics = {t["view"] for r in rub if not r.get("groupe") for t in r["onglets"]}
    deux_clics |= set(re.findall(r"go\('(\w+)'\)", reglages))          # ouvrir « Réglages », puis l'entrée
    sous = {t["sous"] for r in rub for t in r["onglets"] if t.get("sous")}
    # Vague 2a (A2) : « Où je suis partenaire » et « À plusieurs » sont des filtres de Mes marchés (2 clics : la rubrique,
    # puis le filtre) ; la mesure garde leurs anciens noms d'écran (shared, consortiums).
    filtres = {"shared", "consortiums"}
    assert '{ k: "partenaire", label: "Où je suis partenaire"' in JS and '{ k: "plusieurs", label: "À plusieurs"' in JS
    # Pages de détail (un marché, son atelier, un dossier partagé) : depuis la liste de leur rubrique.
    detail = {"aodetail", "atelier", "sharedao"}
    for e in ECRANS - detail:
        assert e in un_clic or e in deux_clics or e in sous or e in filtres, f"« {e} » à plus de 2 clics"
    assert sous == {"publies", "avenir", "alertes"}
    assert un_clic == {"dashboard", "sourcing", "pipeline", "cotraitants", "documents", "company"}


def test_les_pastilles_ne_comptent_que_ce_qui_attend_une_action():
    menu = zone(HTML, "menu")
    pastilles = re.findall(r'<span v-if="([^"]+)" class="badge"', menu)
    assert pastilles == ["mmActions()", "expiring.length"]
    assert menu.count('class="badge"') == 2                       # toutes conditionnelles : jamais un zéro
    for total in ("projects.length", "cotraitants.length", "contacts.length", "shared.length", "kb.docs.length",
                  "consortiums.active", "amont.signals.length"):
        assert total not in menu, total
    onglets = zone(HTML, "onglets-rubrique")
    assert '<span v-if="ongletPastille(t)" class="rn-count">' in onglets
    r = _node(_app("""
o.shared = [
  { groupement: { a_valider: true }, redaction: null },                       // accord demandé
  { groupement: { a_valider: false }, redaction: { a_faire: 1 } },            // une partie à rédiger
  { groupement: null, redaction: { a_faire: 0, a_revalider: 0, a_valider: 0, questions: 0 } },   // rien à faire
  { groupement: { a_valider: false }, redaction: null } ];
o.reseau.recues.list = [{ statut: "en_attente" }, { statut: "acceptee" }, { statut: "en_attente", _declined: true }];
o.expiring = [1, 2];
const r = RUBRIQUES;
console.log(JSON.stringify({ mm: o.mmActions(), part: o.partenaireActions(),
  tab: o.ongletPastille(r[2].onglets[0]), pieces: o.ongletPastille(r[4].onglets[0]),
  autre: o.ongletPastille(r[2].onglets[1]) }));
"""))
    assert r == {"mm": 3, "part": 2, "tab": 3, "pieces": 2, "autre": 0}


# ═══ 1.3 Les onglets de rubrique ════════════════════════════════════════════════════════════════════════════

def test_un_seul_composant_d_onglets_au_dessus_des_vues():
    o = zone(HTML, "onglets-rubrique")
    c = zone(HTML, "contenu")
    assert c.index(o) < c.index('<section data-test="vue-')
    assert 'v-for="t in ongletsVisibles()"' in o and '@click="ongletGo(t)"' in o and ":aria-current=\"ongletActif(t)?'page':null\"" in o
    assert 'type="button" class="rn-tab"' in o and "{{ t.label }}" in o
    # Les anciennes barres d'onglets propres à une vue ont disparu (Mon entreprise).
    assert "pv-onglets" not in HTML and "pv-onglets" not in CSS


def test_onglets_titre_et_bulle_de_l_en_tete_sous_node():
    r = _node(_app("""
const res = {};
const lib = () => o.ongletsVisibles().map(t => t.label);
for (const v of ["dashboard", "pipeline", "bilan", "aodetail", "atelier", "sharedao", "reseau", "kb", "company",
                 "preuves", "team", "compte", "billing"]) {
  o.view = v; res[v] = { rub: o.rubrique(), onglets: lib(), titre: o.enteteTitre(), aide: o.enteteAide() };
}
o.view = "sourcing"; o.trouverOnglet = "publies"; res.publies = { onglets: lib(), titre: o.enteteTitre(), aide: o.enteteAide() };
o.features.projets_a_venir = true; res.avecProjets = lib(); o.features.projets_a_venir = false;
o.trouverOnglet = "avenir"; res.avenir = { aide: o.enteteAide(), vue: o.enteteAideVue(), ancien: o.enteteAncien(),
  actif: o.ongletsVisibles().filter(t => o.ongletActif(t)).map(t => t.label) };
o.user.is_admin = true; o.view = "admin"; res.admin = { rub: o.rubrique(), titre: o.enteteTitre(), onglets: lib() };
res.permis = [o._ongletPermis({ si: "admin" }), o._ongletPermis({ si: "projets_a_venir" }), o._ongletPermis({})];
console.log(JSON.stringify(res));
"""))
    assert r["dashboard"] == {"rub": "accueil", "onglets": [], "titre": "Accueil", "aide": "Anciennement « Tableau de bord »."}
    # Vague 2a (A2) : « Où je suis partenaire » et « À plusieurs » sont des filtres de la liste ; le Bilan, un onglet.
    assert r["pipeline"]["onglets"] == ["Marchés", "Devis et factures", "Bilan"]
    assert r["pipeline"]["titre"] == "Mes marchés" and r["pipeline"]["aide"].startswith("Suivez vos marchés étape par étape ")
    assert r["pipeline"]["aide"].endswith("sont des filtres de cette liste.") and "« Partagé avec moi »" in r["pipeline"]["aide"]
    assert r["bilan"]["titre"] == "Mes marchés" and r["bilan"]["aide"].endswith("« Où vous gagnez / perdez » était sur l'accueil.")
    # Pages de détail : rubrique surlignée (Mes marchés), aucun onglet, leur propre titre.
    for v, titre in (("aodetail", "Le marché"), ("atelier", "Dossier de présentation"), ("sharedao", "Dossier partagé")):
        assert r[v]["rub"] == "marches" and r[v]["onglets"] == [] and r[v]["titre"] == titre, v
    assert r["aodetail"]["aide"] == ""                                   # plus de « Dossier complet de l'appel d'offres »
    assert r["reseau"]["onglets"] == ["Mes partenaires", "Réseau Adjugo", "Contacts"] and r["reseau"]["titre"] == "Partenaires"
    assert r["reseau"]["aide"] == "Trouvez des partenaires et faites-vous trouver Anciennement « Réseau »."
    assert r["kb"]["onglets"] == ["Mes pièces", "Mon savoir-faire"] and r["kb"]["titre"] == "Mes documents"
    # Vague 2a (A3) : Mon entreprise en 4 onglets.
    assert r["company"]["onglets"] == ["Identité", "Ce que je cherche", "Mes preuves", "Tarifs"] and r["preuves"]["titre"] == "Mon entreprise"
    # Réglages : pas d'onglets, le nom de l'écran ; Mon compte dit où étaient ses cartes.
    assert r["team"] == {"rub": "reglages", "onglets": [], "titre": "Collègues",
                         "aide": "Invitez vos collègues à collaborer sur vos dossiers Anciennement « Équipe »."}
    assert r["compte"]["titre"] == "Mon compte" and r["compte"]["aide"].endswith("étaient dans « Équipe ».")
    assert r["billing"]["aide"] == ""                                    # plus de « Débloquez toute la puissance »
    assert r["publies"] == {"onglets": ["Publiés", "À venir", "Mes alertes"], "titre": "Trouver des marchés",
                            "aide": "Les marchés publiés sur les sources officielles : chaque résultat renvoie à son annonce."}
    assert r["avecProjets"] == ["Publiés", "À venir", "Mes alertes", "Projets à venir"]
    assert r["avenir"]["ancien"] == "Anciennement « Radar des échéances »." and r["avenir"]["actif"] == ["À venir"]
    assert r["avenir"]["vue"].startswith("Contrats déjà attribués")
    assert r["admin"] == {"rub": "reglages", "titre": "Administration", "onglets": []}
    assert r["permis"] == [True, False, True]


def test_ongletgo_ouvre_par_go_et_compte_les_onglets_de_trouver_des_marches():
    r = _node(_app("""
const T = RUBRIQUES[1].onglets, res = {};
o.view = "dashboard"; o.ongletGo(T[1]);
res.depuisAccueil = { view: o.view, onglet: o.trouverOnglet, journal: o.journal.slice(), menu: o.mobileNav };
o.journal = []; o.mobileNav = true; o.ongletGo(T[2]);
res.alertes = { onglet: o.trouverOnglet, journal: o.journal.slice(), menu: o.mobileNav };
o.journal = []; o.ongletGo(T[0]); res.publies = { onglet: o.trouverOnglet, journal: o.journal.slice() };
o.journal = []; o.trouverOnglet = "avenir"; o.view = "pipeline"; o.rubriqueGo("trouver");
res.menu = { view: o.view, onglet: o.trouverOnglet, journal: o.journal.slice() };
o.journal = []; o.ongletGo(RUBRIQUES[2].onglets[2]); res.bilan = { view: o.view, journal: o.journal.slice() };
res.noms = ["avenir", "alertes", "kb", "dashboard", "team", "aodetail", "compte"].map(k => o.adminEcranNom(k));
console.log(JSON.stringify(res));
"""))
    assert r["depuisAccueil"] == {"view": "sourcing", "onglet": "avenir", "journal": ["go:sourcing", "mesure:avenir"],
                                  "menu": False}
    assert r["alertes"] == {"onglet": "alertes", "journal": ["mesure:alertes"], "menu": False}   # déjà sur la vue
    assert r["publies"] == {"onglet": "publies", "journal": []}
    assert r["menu"] == {"view": "sourcing", "onglet": "publies", "journal": ["go:sourcing"]}
    assert r["bilan"] == {"view": "bilan", "journal": ["go:bilan"]}                             # go() sans changement
    assert r["noms"] == ["Trouver des marchés › À venir", "Trouver des marchés › Mes alertes",
                         "Mes documents › Mon savoir-faire", "Accueil", "Collègues", "Le marché", "Mon compte"]


def test_mesure_des_nouveaux_ecrans():
    from app.services.mesure_usage import ECRANS
    assert {"compte", "avenir", "alertes"} <= ECRANS
    go = JS[JS.index("    go(v) {"):JS.index("    _ecranOuvert(v) {")]
    assert 'if (v === "pipeline") { this.loadProjects(); this.loadShared(); this.rnLoadRecues(true); this.loadConsortiums(); }' in go
    # Trouver des marchés s'ouvre sur « Publiés » ; un onglet choisi l'est après go().
    assert 'if (v === "sourcing" && this.view !== "sourcing") this.trouverOnglet = "publies";' in go
    og = _method("ongletGo")
    assert og.index("if (!deja) this.go(t.view);") < og.index("this.trouverOnglet = t.sous;")
    i = JS.index("    async srcRenewals() {")
    assert "if (this.src.renewals.loading) return;" in JS[i:JS.index("\n    },\n", i)]
    assert "this.noteReorgMarquer();" in go


# ═══ 1.3 Trouver des marchés : Publiés · À venir · Mes alertes ═══════════════════════════════════════════════

def test_le_radar_quitte_le_haut_des_resultats_pour_l_onglet_a_venir():
    vue = zone(HTML, "vue-sourcing")
    radar, alertes = zone(HTML, "trouver-radar"), zone(HTML, "trouver-alertes")
    assert radar.startswith('<div data-test="trouver-radar" v-if="trouverOnglet===\'avenir\'"')
    assert alertes.startswith('<div data-test="trouver-alertes" v-if="trouverOnglet===\'alertes\'"')
    publies = vue[vue.index('<template v-if="trouverOnglet===\'publies\'">'):]
    for n in ("trouver-recherche", "trouver-carte", "trouver-analyse"):
        assert zone(HTML, n) in publies, n
    assert radar not in publies and alertes not in publies
    # Le radar a ses propres champs (plus de « mots-clés ci-dessus »), son nom de l'étude, aucune note sur 100.
    assert "Contrats qui arrivent à échéance" in radar and 'data-lucide="calendar-clock"' in radar
    assert 'v-model="src.query"' in radar and 'v-model="src.dept"' in radar and "Chercher les fins de contrat" in radar
    for faux in ("ci-dessus", "pertinence", "/100", "↗", "Radar des échéances", "timer-reset"):
        assert faux not in radar, faux
    assert "Mes alertes" in alertes and "Alertes automatiques" not in alertes and "ci-dessus" not in alertes
    assert "srcSaveAlert()" in alertes and "srcDeps()" in alertes        # la recherche enregistrée est dite
    assert 'trouverOnglet: "publies",' in JS


# ═══ 1.6 Accueil allégé ════════════════════════════════════════════════════════════════════════════════════

def test_accueil_allege():
    dash = re.sub(r"<!--.*?-->", "", zone(HTML, "vue-dashboard"), flags=re.S)
    assert "accueil-ruban" not in noms(HTML)
    for parti in ("dash-ribbon", "Taux de réussite", "act-hero", "act-links", "Monter un groupement", "Vos appels d'offres"):
        assert parti not in dash, parti
    plusieurs = zone(HTML, "accueil-reseau")
    assert '<button class="btn primary dh-act" @click="go(\'consortiums\')"><i data-lucide="handshake"></i>Préparer à plusieurs</button>' in plusieurs
    assert ">À plusieurs<" in plusieurs and "user-plus" not in plusieurs and "users-round" not in plusieurs
    assert "Mes groupements" not in plusieurs
    assert "<h3>Vos marchés</h3>" in zone(HTML, "accueil-flux")
    # Vague 2a (A1) : les pièces à renouveler sont dans le bloc « À faire » (accueil-a-faire), plus dans le rail.
    assert zone(HTML, "accueil-rail").startswith('<div data-test="accueil-rail" v-if="dashTotal()"')
    assert "pièces à renouveler" not in zone(HTML, "accueil-rail")
    assert ".dash-grid.solo { grid-template-columns:minmax(0,1fr); }" in CSS
    # Vague 2a (A2) : « À plusieurs » est un filtre de Mes marchés ; go('consortiums') y mène (plus de vue à part).
    assert 'if (v === "shared" || v === "consortiums") { filtre = v === "shared" ? "partenaire" : "plusieurs"; v = "pipeline"; }' in JS
    assert "Monter un groupement" not in HTML and "Nouveau groupement" not in HTML


# ═══ 1.7 Sous-titres en bulle ══════════════════════════════════════════════════════════════════════════════

def test_sous_titres_dans_la_bulle_de_l_en_tete():
    e = zone(HTML, "entete")
    assert 'class="sub"' not in e and "subtitles[view]" not in e and "titles[view]" not in e
    assert "<h1>{{ enteteTitre() }}</h1>" in e
    assert ('<button v-if="enteteAide()" type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">'
            'En savoir plus</span><span class="tip-b" role="tooltip">') in e
    chaines = " ".join(t for _l, t in textes_js(JS))
    for promesse in ("Débloquez toute la puissance", "Vue d'ensemble de votre activité", "Dossier complet de l'appel d'offres",
                     "vous validez chaque étape"):
        assert promesse not in chaines, promesse
    # Sur téléphone, la bulle de l'en-tête s'ouvre sous la barre (sa position fixe y serait piégée par le flou).
    assert ".top .tip .tip-b, .top .tip.tip-l .tip-b { position:absolute; top:calc(100% + 6px);" in CSS


# ═══ 1.8 Transition ════════════════════════════════════════════════════════════════════════════════════════

def _depuis() -> str:
    """Le jour de mise en ligne lu dans app.js (Eliot le règle au jour réel : le test suit, il ne fige rien)."""
    m = re.search(r'const REORG_V1_DEPUIS = "(\d{4}-\d{2}-\d{2})";', JS)
    assert m, "REORG_V1_DEPUIS introuvable dans app.js"
    return m.group(1)


def test_note_ce_qui_a_change_regles_sous_node():
    r = _node(_PUR + """
const J = 24 * 3600 * 1000, jour = REORG_V1_DEPUIS, now = Date.parse(jour + "T10:00:00Z") + J;
const veille = new Date(Date.parse(jour + "T12:00:00Z") - J).toISOString().slice(0, 10);
const avant = { email: "a@b.fr", created_at: veille + "T08:00:00" };
console.log(JSON.stringify([
  noteReorgVisible(avant, {}, now),
  noteReorgVisible(avant, { vu: now - 6 * J }, now),
  noteReorgVisible(avant, { vu: now - 8 * J }, now),
  noteReorgVisible(avant, { vu: now, ferme: true }, now),
  noteReorgVisible({ email: "x@y.fr", created_at: jour + "T09:00:00" }, {}, now),
  noteReorgVisible({ email: "Demo@Adjugo.fr", created_at: "2026-01-01T00:00:00" }, {}, now),
  noteReorgVisible({}, {}, now), noteReorgVisible(null, null, now)]));
""")
    assert r == [True, True, False, False, False, False, False, False]
    assert _depuis() >= "2026-10-20"                         # jamais avant la vague 1 (la note ne viserait personne)
    from app.services.demo_seed import DEMO_EMAIL
    assert f'const DEMO_EMAIL_APP = "{DEMO_EMAIL}";' in JS                   # la démo (pitch) ne la voit jamais


def test_note_ce_qui_a_change_sur_l_accueil():
    note = zone(HTML, "accueil-ce-qui-a-change")
    dash = zone(HTML, "vue-dashboard")
    assert dash.index(note) < dash.index('data-test="accueil-premiers-pas"')
    assert 'v-if="noteReorgVue()"' in note and '@click="noteReorgFermer()"' in note and 'aria-label="Fermer"' in note
    assert "<details" in note and "Ce qui a changé" in note
    for ancien in ("Tableau de bord", "Partagé avec moi", "Mes groupements", "Radar des échéances", "« Plus »", "« Équipe »"):
        assert ancien in note, ancien
    r = _node(_app("""
o.user = { email: "a@b.fr", created_at: "2026-06-24T08:00:00" };
const res = { avant: o.noteReorgVue() };
o.noteReorgMarquer(); const vu = o.reorgEtat.vu; o.noteReorgMarquer();
res.vu = typeof vu === "number" && o.reorgEtat.vu === vu;
o.noteReorgFermer(); res.ferme = o.noteReorgVue(); res.garde = JSON.parse(store["adjugo_reorg_v1"]);
console.log(JSON.stringify({ avant: res.avant, vu: res.vu, ferme: res.ferme, garde: res.garde.ferme === true && res.garde.vu === vu }));
"""))
    assert r == {"avant": True, "vu": True, "ferme": False, "garde": True}


def test_anciens_noms_en_bulle_seulement_pour_qui_les_a_connus_sous_node():
    """Ni la démonstration (un prospect n'a jamais vu ces noms), ni un compte créé à partir de la mise en ligne : la
    bulle de l'en-tête ne dit plus l'ancien nom ; sur l'Accueil, elle n'a alors plus rien à dire et disparaît."""
    r = _node(_app("""
const J = 24 * 3600 * 1000, jour = REORG_V1_DEPUIS;
const veille = new Date(Date.parse(jour + "T12:00:00Z") - J).toISOString().slice(0, 10);
const res = {};
const comptes = { ancien: { email: "a@b.fr", created_at: veille + "T08:00:00" },
                  neuf: { email: "n@b.fr", created_at: jour + "T08:00:00" },
                  demo: { email: DEMO_EMAIL_APP, created_at: "2026-01-01T00:00:00" }, vide: {} };
for (const [k, u] of Object.entries(comptes)) {
  o.user = u; res[k] = {};
  for (const v of ["dashboard", "pipeline", "bilan", "reseau", "team", "compte", "company"]) {
    o.view = v; res[k][v] = { ancien: o.enteteAncien(), aide: o.enteteAide() };
  }
  res[k].transition = transitionVisible(u);
}
console.log(JSON.stringify(res));
"""))
    assert r["ancien"]["transition"] is True
    assert r["ancien"]["dashboard"]["aide"] == "Anciennement « Tableau de bord »."
    assert r["ancien"]["pipeline"]["ancien"].startswith("« Où je suis partenaire » (anciennement « Partagé avec moi »)")
    assert r["ancien"]["compte"]["ancien"].endswith("étaient dans « Équipe ».")
    for k in ("neuf", "demo", "vide"):
        assert r[k]["transition"] is False, k
        for v, x in r[k].items():
            if v == "transition":
                continue
            assert x["ancien"] == "" and "Anciennement" not in x["aide"] and "« Équipe »" not in x["aide"], (k, v, x)
        assert r[k]["dashboard"]["aide"] == "", k            # plus de bulle (i) vide à côté de « Accueil »
        assert r[k]["pipeline"]["aide"] and r[k]["team"]["aide"], k   # la phrase de l'écran reste
    from app.services.demo_seed import DEMO_EMAIL
    assert f'const DEMO_EMAIL_APP = "{DEMO_EMAIL}";' in JS
    assert "if (!transitionVisible(user)) return false;" in JS          # la note suit la même règle


def test_les_anciens_noms_ne_restent_que_dans_la_note_et_les_bulles():
    anciens = ("Tableau de bord", "Partagé avec moi", "Mes groupements", "Radar des échéances", "Alertes automatiques",
               "Monter un groupement", "Nouveau groupement", "Profil de l'entreprise")
    note = zone(HTML, "accueil-ce-qui-a-change")
    debut = HTML.index(note)
    l0, l1 = HTML.count("\n", 0, debut) + 1, HTML.count("\n", 0, debut + len(note)) + 1
    fautes = [(ln, t.strip()) for ln, t in textes_html(HTML) if any(a in t for a in anciens) and not l0 <= ln <= l1]
    assert not fautes, fautes
    i, j = JS.index("const RUBRIQUES = ["), JS.index("\n];\n", JS.index("const RUBRIQUES = ["))
    hors = [(ln, t) for ln, t in textes_js(JS) if any(a in t for a in anciens)
            and not (JS.count("\n", 0, i) < ln <= JS.count("\n", 0, j) + 1)]
    assert not hors, hors
    for f in ("redaction-partenaire.js",):
        src = (STATIC / f).read_text(encoding="utf-8")
        assert not [t for _l, t in textes_js(src) if "Partagé avec moi" in t], f
        assert "Mes marchés, filtre « Où je suis partenaire »" in src           # vague 2a (A2) : un filtre de la liste
    assert "Invitation acceptée : le dossier est dans Mes marchés, filtre « Où je suis partenaire »." in JS


# ═══ Les vues rangées ══════════════════════════════════════════════════════════════════════════════════════

def test_mon_compte_rassemble_mot_de_passe_et_donnees():
    compte, equipe = zone(HTML, "vue-compte"), zone(HTML, "vue-team")
    for s in ("Mon mot de passe", "changePassword()", "Mes données (RGPD)", "rgpdExport()", "rgpdDelete()"):
        assert s in compte and s not in equipe, s
    assert "Inviter un collègue" in equipe
    assert 'compte: "Mon compte"' in JS
    org = (ROOT / "app" / "routers" / "org.py").read_text(encoding="utf-8")
    assert "changez votre mot de passe (menu Réglages, puis Mon compte)." in org


def test_ou_je_suis_partenaire_toujours_present_et_invitations_du_reseau():
    # Vague 2a (A2) : « Où je suis partenaire » est un filtre de Mes marchés, toujours proposé (mmFiltres ne dépend pas des
    # données) ; les invitations reçues par le réseau se traitent en tête de la liste (plus dans le Réseau Adjugo).
    filtres = _method("mmFiltres")
    assert '{ k: "partenaire", label: "Où je suis partenaire", ic: "inbox", n: this.mmActions() }' in filtres and " if " not in filtres
    assert "rnAccept(inv)" in zone(HTML, "mes-marches-invitations") and "Dossiers partagés avec vous" not in HTML
    assert 'if (tab === "recues") { this.go("shared"); return; }' in JS
    for z in ("vue-sharedao", "vue-sharedao-attente"):
        assert '<i data-lucide="arrow-left"></i>Où je suis partenaire</button>' in zone(HTML, z)
    assert "v-if=\"shared.length\" class=\"nav-item\"" not in HTML        # plus d'entrée qui apparaît et disparaît


def test_icones_de_l_etude_et_existence_dans_lucide():
    rub = _rubriques()
    icones = {r["ic"] for r in rub} | {t["ic"] for r in rub for t in r["onglets"]}
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    script = ("const fs = require('fs'), vm = require('vm'); const ctx = { window: {}, self: {}, console };"
              "ctx.globalThis = ctx; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(STATIC / 'vendor' / 'lucide-1.20.0.min.js'))}, 'utf8'), ctx);"
              "const L = ctx.lucide || ctx.window.lucide; const p = n => n.split('-').map(s => s[0].toUpperCase() + s.slice(1)).join('');"
              f"console.log(JSON.stringify({json.dumps(sorted(icones))}.filter(n => !(L[p(n)] || (L.icons && L.icons[p(n)])))));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []
    assert [r["ic"] for r in rub] == ["house", "search", "folder-kanban", "handshake", "folder-lock", "building-2", "settings"]
    # users-round : seulement Collègues dans le menu ; user-plus réservé à « Inviter un partenaire ».
    menu = zone(HTML, "menu")
    assert menu.count('data-lucide="users-round"') == 1 and "user-plus" not in menu
    assert 'data-lucide="users-round"' not in zone(HTML, "vue-dashboard")


def test_375_px_onglets_sur_deux_colonnes_et_reseau_subordonne():
    assert ".rub-onglets.rub-n2, .rub-onglets.rub-n4 { grid-template-columns:repeat(2, minmax(0,1fr)); }" in CSS
    assert "section.rn > .rn-tabs .rn-tab { min-height:32px;" in CSS
    assert not re.search(r"(?<![-\w])width:\s*\d{3,}px", CSS[CSS.index("/* ══════════ Menu par rubriques"):
                                                             CSS.index("/* ══════════ Bulle d'information")])


# ═══ Décision 16 : traductions ═════════════════════════════════════════════════════════════════════════════

def test_traductions_du_menu_des_onglets_des_bulles_et_de_la_note():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    rub = _node(_PUR + "\nconsole.log(JSON.stringify({ r: RUBRIQUES, a: RUBRIQUES.flatMap(x => x.onglets).map(ancienNom).filter(Boolean) }));")
    cles = {x["label"] for x in rub["r"]} | {t["label"] for x in rub["r"] for t in x["onglets"]} | set(rub["a"])
    sous = re.search(r"      subtitles: \{(.*?)\},\n", JS, re.S).group(1)
    cles |= set(re.findall(r'\w+: "([^"]+)"', sous))
    note = zone(HTML, "accueil-ce-qui-a-change")
    cles |= {re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<li>(.*?)</li>", note)}
    cles |= {"Ce qui a changé", "Où retrouver vos écrans", "Préparer à plusieurs", "Vos marchés", "Vos marchés à plusieurs",
             "Contrats qui arrivent à échéance", "Chercher les fins de contrat", "Les marchés où vous êtes partenaire",
             "Voir les invitations", "Voir mes marchés à plusieurs"}
    manque = sorted(k for k in cles if not (d["nl"].get(k) and d["es"].get(k)))
    assert not manque, f"sans traduction (scripts/i18n_ajouter.py) : {manque}"
    # Deux onglets voisins ne se traduisent jamais pareil (Mes documents › Mes pièces).
    assert d["es"]["Mes pièces"] != d["es"]["Mes documents"] and d["nl"]["Mes pièces"] != d["nl"]["Mes documents"]
