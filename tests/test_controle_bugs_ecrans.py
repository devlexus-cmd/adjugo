"""Contrôle des bugs d'octobre 2026, groupe « ecrans » (cloche et « À faire », compte à rebours de la part du
partenaire, page du marché, titre de l'onglet, barre basse sur téléphone) : chaque test dit ce que le logiciel DOIT
faire d'après ses contrats (docs/REORGANISATION_V2A.md § A1 et A1.3, docs/REORGANISATION_V2B.md § B3, décision 16 de
docs/REORGANISATION_V1.md § 0.5) et ses textes affichés ; tous échouaient sur cfe04e1, chacun sur son défaut.

19. « À faire » compte les dates limites sur le jour de l'appareil, jamais sur le jour UTC.
20. « Il vous reste N jours pour soumettre votre part » (aperçu du partenaire et écran du partenaire, invite.html) :
    des jours du calendrier de l'appareil.
21. La carte « Date limite » de l'en-tête du marché écrit la date JJ/MM/AAAA, comme le reste de l'application.
22. Le titre de l'onglet du navigateur suit la langue de l'écran.
23. Barre basse à 375 px : « Mes marchés » traduit tient en entier (néerlandais, espagnol), le français ne bouge pas.
24. Les lignes de « À faire » sont traduites en entier : titres et détails composés avec un nombre ou un nom.

Aucun réseau : fonctions et méthodes de app.js et invite.html exécutées sous Node ; un test ouvre en plus un vrai
Chromium (Playwright) quand il est installé, sans aucune requête.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_reorganisation_v2a_entreprise import _accolade_fermante, _methode
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
I18N = (STATIC / "i18n.js").read_text(encoding="utf-8")


def _node(script, *args, tz="Europe/Paris"):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    env = dict(os.environ, TZ=tz)
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _methode_si(nom):
    """La méthode si elle existe (une correction peut en ajouter une), sinon rien."""
    return _methode(nom) + ",\n" if re.search(r"\n    (async )?" + re.escape(nom) + r"\(", JS) else ""


# Une horloge fixée : `fixer(iso)` pose l'instant (UTC) ; le fuseau de l'appareil est celui de TZ.
_HORLOGE = r"""
const RealDate = Date;
function fixer(iso) {
  const f = new RealDate(iso).getTime();
  globalThis.Date = class extends RealDate { constructor(...x) { if (x.length) super(...x); else super(f); } static now() { return f; } };
}
"""


def _a_faire_src():
    i = JS.index("const A_FAIRE_JOURS = 7;")
    k = JS.index("function listeAFaire(", i)
    return JS[i:JS.index("\n}\n", k) + 3]


# ═══ 19. « À faire » : le jour de l'appareil ═══════════════════════════════════════════════════════════════════

def test_19_a_faire_compte_les_dates_limites_sur_le_jour_de_l_appareil_sous_node():
    # A1.3 : « une date limite de vos marchés dans les 7 jours (aujourd'hui, demain, dans N jours) » ; le jour de Paris
    # partout (V2A, dates de fin). Avant : le jour UTC (toISOString), la veille entre minuit et 2 h à Paris.
    script = _HORLOGE + _a_faire_src() + "\nconst o = {\n" + _methode("aFaire") + r"""
};
Object.assign(o, { shared: [], reseau: { recues: { list: [] } }, grpDash: null, expiring: [],
  projects: ["22", "23", "29", "30", "31"].map((j, i) => ({ id: i + 1, name: "M" + j, status: "suivi", deadline: "2026-10-" + j })) });
const lignes = iso => { fixer(iso); return o.aFaire().map(t => [t.detail, t.titre]); };
console.log(JSON.stringify({ nuit: lignes(process.argv[1]), midi: lignes(process.argv[2]) }));
"""
    # Paris : le 23/10 à 0 h 30, puis à midi. La date limite du 22 est passée, celle du 23 tombe le jour même.
    attendu = [["M23", "Date limite aujourd'hui"], ["M29", "Date limite dans 6 jours"], ["M30", "Date limite dans 7 jours"]]
    r = _node(script, "2026-10-22T22:30:00Z", "2026-10-23T10:00:00Z")
    assert r["nuit"] == attendu
    assert r["midi"] == attendu
    # Martinique (UTC-4) : le 22/10 à 21 h, le jour même de M22 ; M30 est à 8 jours.
    r = _node(script, "2026-10-23T01:00:00Z", "2026-10-22T16:00:00Z", tz="America/Martinique")
    attendu = [["M22", "Date limite aujourd'hui"], ["M23", "Date limite demain"], ["M29", "Date limite dans 7 jours"]]
    assert r["nuit"] == attendu and r["midi"] == attendu
    assert "toISOString" not in _methode("aFaire")


# ═══ 20. Le compte à rebours de la part : des jours du calendrier de l'appareil ══════════════════════════════

def test_20_compte_a_rebours_de_l_apercu_du_partenaire_sous_node():
    # B3 : l'aperçu reprend le compte à rebours de l'écran du partenaire. Avant : des tranches de 24 h depuis minuit
    # UTC (« Dernier jour » le lendemain de la date limite à 0 h 30 à Paris, « Date limite dépassée » le jour même à
    # 21 h aux Antilles).
    script = _HORLOGE + "const o = {\n" + _methode("paJours") + ",\n" + _methode("paDelai") + r"""
};
const a = (iso, dl) => { fixer(iso); return [o.paJours(dl), o.paDelai(dl)]; };
const c = JSON.parse(process.argv[1]);
console.log(JSON.stringify(c.map(x => a(x[0], x[1])).concat([[o.paJours(null), o.paJours(""), o.paJours("pas une date"), o.paDelai(null)]])));
"""
    paris = _node(script, json.dumps([["2026-10-22T22:30:00Z", "2026-10-22"], ["2026-10-22T22:30:00Z", "2026-10-23"],
                                      ["2026-10-22T22:30:00Z", "2026-10-24"], ["2026-10-23T10:00:00Z", "2026-10-23"],
                                      ["2026-10-23T10:00:00Z", "2026-11-23"]]))
    assert paris == [[-1, "Date limite dépassée : contactez le chef de file."],
                     [0, "Dernier jour : soumettez votre part aujourd'hui."],
                     [1, "Il vous reste 1 jour pour soumettre votre part au chef de file."],
                     [0, "Dernier jour : soumettez votre part aujourd'hui."],
                     [31, "Il vous reste 31 jours pour soumettre votre part au chef de file."],   # passage à l'heure d'hiver
                     [None, None, None, ""]]
    gp = _node(script, json.dumps([["2026-10-23T01:00:00Z", "2026-10-22"], ["2026-10-23T01:00:00Z", "2026-10-23"]]),
               tz="America/Guadeloupe")
    assert gp[:2] == [[0, "Dernier jour : soumettez votre part aujourd'hui."],
                      [1, "Il vous reste 1 jour pour soumettre votre part au chef de file."]]


def _fonction_inv(nom):
    m = re.search(r"\n\s*function " + re.escape(nom) + r"\(", INV)
    assert m, f"invite.html : fonction {nom} absente"
    return INV[m.start():_accolade_fermante(INV, INV.index("{", m.end()))]


def test_20_compte_a_rebours_de_l_ecran_du_partenaire_sous_node():
    # L'écran du partenaire (invite.html, « Votre part ») et son aperçu disent le même nombre de jours.
    assert "Math.ceil((new Date(p.deadline) - new Date()) / 86400000)" not in INV
    assert "const dLeft = joursAvantDateLimite(p.deadline);" in INV and "if (dLeft !== null) {" in INV
    script = _HORLOGE + _fonction_inv("joursAvantDateLimite") + r"""
const a = (iso, dl) => { fixer(iso); return joursAvantDateLimite(dl); };
console.log(JSON.stringify([a("2026-10-22T22:30:00Z", "2026-10-22"), a("2026-10-22T22:30:00Z", "2026-10-23"),
  a("2026-10-23T10:00:00Z", "2026-10-23"), a("2026-10-23T10:00:00Z", "2026-11-23"),
  joursAvantDateLimite(null), joursAvantDateLimite(""), joursAvantDateLimite("pas une date")]));
"""
    assert _node(script) == [-1, 0, 0, 31, None, None, None]
    assert _node(script.replace('"2026-10-22T22:30:00Z", "2026-10-22"', '"2026-10-23T01:00:00Z", "2026-10-22"'),
                 tz="America/Guadeloupe")[0] == 0


# ═══ 21. La date limite de l'en-tête du marché : JJ/MM/AAAA ══════════════════════════════════════════════════

def test_21_date_limite_de_l_en_tete_du_marche_au_format_de_l_application():
    entete = zone(HTML, "marche-entete")
    kpi = re.search(r'<span>Date limite</span>.*?<div class="v"[^>]*>\{\{ (.*?) \}\}</div>', entete, re.S)
    assert kpi, "la carte « Date limite » de l'en-tête du marché"
    script = "const o = {\n" + _methode("fmtDate") + r"""
};
const out = [];
for (const c of JSON.parse(process.argv[1])) {
  const aoDetails = () => c.details, ao = { project: c.project }, fmtDate = s => o.fmtDate(s);
  out.push(eval(process.argv[2]));
}
console.log(JSON.stringify(out));
"""
    r = _node(script, json.dumps([
        {"details": {}, "project": {"deadline": "2026-10-24"}},                        # sans analyse : la date de l'API
        {"details": {"date_limite": "24/10/2026 à 12 h"}, "project": {"deadline": "2026-10-24"}},   # l'analyse d'abord
        {"details": {}, "project": {"deadline": None}},
    ]), kpi.group(1))
    assert r == ["24/10/2026", "24/10/2026 à 12 h", "non précisée"]
    # Le reste de l'application l'écrit ainsi : Mes marchés, l'aperçu du partenaire.
    assert "fmtDate(cs.deadline)" in zone(HTML, "vue-pipeline") and "fmtDate(v.project.deadline)" in HTML


# ═══ 22. Le titre de l'onglet suit la langue de l'écran ═══════════════════════════════════════════════════════

_TITRE = r"""
globalThis.window = {}; """ + "\n" + I18N + r"""
globalThis.document = { title: "", querySelector() { return null; }, documentElement: { setAttribute() {} } };
let entree = { url: "/app", state: { adjugo: 1, n: 0 } }, pousses = 0;
globalThis.location = { get pathname() { return entree.url; }, search: "" };
globalThis.history = { get state() { return entree.state; },
  replaceState(st, t, url) { entree = { url: url === undefined ? entree.url : url, state: st }; },
  pushState(st, t, url) { pousses++; entree = { url, state: st }; } };
const titres = { dashboard: "Accueil", pipeline: "Mes marchés", essai: "Titre sans traduction" };
Object.assign(o, { token: "t", _adresseActive: true, view: "dashboard", lang: "fr", adresseCourante: "/app",
                   renderI18n() {}, enteteTitre() { return titres[this.view]; } });
const out = {};
o.lang = "nl"; o._adresseSynchro("/app"); out.accueilNl = document.title;
o.view = "pipeline"; o.adresseCourante = "/app/marches"; o._adresseSynchro("/app/marches"); out.marchesNl = document.title;
o.view = "essai"; o._adresseSynchro("/app/marches"); out.sansTraduction = document.title;
o.view = "dashboard"; o.adresseCourante = "/app"; o.lang = "es"; o._adresseSynchro("/app"); out.accueilEs = document.title;
o.lang = "fr"; o._adresseSynchro("/app"); out.accueilFr = document.title;
// La langue arrive après l'écran (fiche de l'entreprise lue ou enregistrée) : le titre suit, sans entrée d'historique.
const avant = pousses; o.applyLang("nl"); out.apresLangue = document.title; out.pousses = pousses - avant; out.url = entree.url;
// Écran de connexion : rien n'est touché.
o.token = ""; document.title = "Connexion"; o.applyLang("es"); out.connexion = document.title;
console.log(JSON.stringify(out));
"""


def test_22_titre_de_l_onglet_dans_la_langue_de_l_ecran_sous_node():
    script = "const o = {\n" + _methode_si("_titreOnglet") + _methode("_adresseSynchro") + ",\n" + _methode("applyLang") + "\n};\n" + _TITRE
    r = _node(script)
    assert r["accueilNl"] == "Start · Adjugo" and r["marchesNl"] == "Mijn aanbestedingen · Adjugo"
    assert r["accueilEs"] == "Inicio · Adjugo" and r["accueilFr"] == "Accueil · Adjugo"
    assert r["sansTraduction"] == "Titre sans traduction · Adjugo"        # un libellé sans traduction reste en français
    assert r["apresLangue"] == "Start · Adjugo" and r["pousses"] == 0 and r["url"] == "/app"
    assert r["connexion"] == "Connexion"


# ═══ 23. Barre basse à 375 px : le libellé traduit tient en entier ═══════════════════════════════════════════

def _regle_barre():
    i = CSS.index(".barre-basse { display:none; }")
    bloc = CSS[i:CSS.index("\n}\n", i)]
    return re.search(r"\n  \.barre-basse \{[^}]*\}", bloc).group(0)


def test_23_les_colonnes_de_la_barre_basse_s_elargissent_a_leur_libelle():
    # A1.3 : « 375 px : les 5 mots tiennent ». Une colonne ne descend jamais sous la largeur de son libellé : les
    # colonnes restent égales tant que chaque libellé y tient (le français à 375 px), sinon la colonne du libellé long
    # prend ce qu'il lui faut et les autres se partagent le reste. Avant : 5 colonnes égales, quoi qu'il arrive, et
    # « Mijn aanbestedingen » (107 px pour 73) coupé en « Mijn aanbes… ».
    regle = _regle_barre()
    assert "grid-template-columns:repeat(5, minmax(min-content,1fr))" in regle, regle
    assert "minmax(0,1fr)" not in regle
    # Les libellés traduits existent (décision 16) : c'est bien eux que la barre affiche en néerlandais et en espagnol.
    d = json.loads(I18N.split("window.ADJUGO_I18N = ", 1)[1].rstrip().rstrip(";"))
    assert d["nl"]["Mes marchés"] == "Mijn aanbestedingen" and d["es"]["Mes marchés"] == "Mis licitaciones"


_MESURE = r"""
let pw; try { pw = require("playwright"); } catch (e) { console.log(JSON.stringify({ absent: true })); process.exit(0); }
const page_ = JSON.parse(process.argv[1]);
(async () => {
  const b = await pw.chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 375, height: 812 } });
  await ctx.route("**/*", r => r.abort());
  const out = {};
  for (const [lang, html] of Object.entries(page_)) {
    const p = await ctx.newPage(); await p.setContent(html);
    out[lang] = await p.evaluate(() => ({
      page: document.documentElement.scrollWidth,
      boutons: [...document.querySelectorAll(".bb-i")].map(x => { const s = x.querySelector("span"); return {
        mot: s.textContent, coupe: s.scrollWidth > s.clientWidth, large: Math.round(x.getBoundingClientRect().width * 10) / 10 }; }) }));
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(String(e)); process.exit(1); });
"""


def test_23_barre_basse_mesuree_dans_un_navigateur_a_375_px():
    """Chromium réel (Playwright, s'il est installé : NODE_PATH ou node_modules du dépôt), polices du système, aucune
    requête : les 5 libellés tiennent dans les trois langues, la page ne défile pas de côté, et en français les
    colonnes restent égales (rien ne bouge)."""
    d = json.loads(I18N.split("window.ADJUGO_I18N = ", 1)[1].rstrip().rstrip(";"))
    barre = re.sub(r'<span v-if="[^"]*" class="bb-badge">.*?</span></span>', "", zone(HTML, "menu-bas"))
    pages = {}
    for lang in ("fr", "nl", "es"):
        b = barre if lang == "fr" else re.sub(r"<span>([^<]+)</span>", lambda m: "<span>" + d[lang].get(m.group(1), m.group(1)) + "</span>", barre)
        pages[lang] = ('<!doctype html><html lang="' + lang + '"><meta charset="utf-8"><style>' + CSS + "</style><body>"
                       '<div class="app">' + b + "</div></body></html>")
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    env = dict(os.environ)
    env["NODE_PATH"] = os.pathsep.join(x for x in (env.get("NODE_PATH", ""), str(ROOT / "node_modules")) if x)
    r = subprocess.run([node, "-e", _MESURE, json.dumps(pages)], capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT))
    if r.returncode and "Executable doesn't exist" in r.stderr:
        pytest.skip("navigateur de Playwright non installé")
    assert r.returncode == 0, r.stderr
    m = json.loads(r.stdout.strip().splitlines()[-1])
    if m.get("absent"):
        pytest.skip("Playwright non installé")
    for lang in ("fr", "nl", "es"):
        assert m[lang]["page"] <= 375, (lang, m[lang])
        assert [x["coupe"] for x in m[lang]["boutons"]] == [False] * 5, (lang, m[lang]["boutons"])
    assert [x["mot"] for x in m["nl"]["boutons"]][2] == "Mijn aanbestedingen"
    assert [x["mot"] for x in m["es"]["boutons"]][2] == "Mis licitaciones"
    larges = [x["large"] for x in m["fr"]["boutons"]]
    assert max(larges) - min(larges) < 0.5, larges                       # français : 5 colonnes égales, comme avant


# ═══ 24. « À faire » traduit en entier ══════════════════════════════════════════════════════════════════════

_DONNEES_A_FAIRE = {
    "shared": [{"project_id": 5, "project": "Toiture", "mandataire": "Breizh", "groupement": {"a_valider": True}}],
    "recues": [{"token": "t1", "project": "Gymnase", "mandataire": "Kerhel", "statut": "envoyee"}],
    "projects": [{"id": 1, "name": "École", "status": "nouveau", "deadline": "2026-10-22"},
                 {"id": 2, "name": "Mairie", "status": "en_cours", "deadline": "2026-10-24"}],
    "enCours": [{"project_id": 2, "name": "Mairie", "n_membres": 1, "n_parts": 0}],
    "expiring": [{"name": "URSSAF", "expiration_date": "2026-10-18"}, {"name": "Kbis", "expiration_date": "2026-11-10"}],
}


def _a_faire_traduit(donnees):
    # La règle de translateDOM (app.js) : un nœud texte est traduit s'il est, espaces autour retirés, une clé du
    # dictionnaire. Chaque morceau est son propre nœud (gabarits de la cloche et de l'accueil).
    return _node("globalThis.window = {};\n" + I18N + "\n" + _a_faire_src() + r"""
const tr = (lang, s) => { const dict = window.ADJUGO_I18N[lang], k = s.trim(), t = dict && dict[k]; return t && t !== k ? s.replace(k, () => t) : s; };
const l = listeAFaire(JSON.parse(process.argv[1]), "2026-10-22"), out = {};
for (const lang of ["fr", "nl", "es"])
  out[lang] = l.map(t => [(t.morceauxTitre || [t.titre]).map(m => tr(lang, m)).join(""),
                          (t.morceauxDetail || [t.detail]).map(m => tr(lang, m)).join(""), tr(lang, t.cta)]);
out.joint = l.every(t => (t.morceauxTitre || []).join("") === t.titre && (t.morceauxDetail || []).join("") === t.detail);
console.log(JSON.stringify(out));
""", json.dumps(donnees))


def test_24_lignes_a_faire_entierement_traduites_sous_node():
    r = _a_faire_traduit(_DONNEES_A_FAIRE)
    assert r["fr"] == [["Votre accord est demandé", "Toiture · chef de file : Breizh", "Lire et donner mon accord"],
                       ["Invitation à répondre ensemble", "Gymnase · chef de file : Kerhel", "Voir l'invitation"],
                       ["Date limite aujourd'hui", "École", "Ouvrir"],
                       ["Date limite dans 2 jours", "Mairie", "Ouvrir"],
                       ["Parts reçues 0 sur 1", "Mairie", "Ouvrir"],
                       ["2 pièces à renouveler", "URSSAF · expirée le 18/10", "Voir"]]
    assert r["nl"] == [["Uw akkoord wordt gevraagd", "Toiture · penvoerder: Breizh", "Lezen en mijn akkoord geven"],
                       ["Uitnodiging om samen in te schrijven", "Gymnase · penvoerder: Kerhel", "Uitnodiging bekijken"],
                       ["Uiterste datum vandaag", "École", "Openen"],
                       ["Uiterste datum over 2 dagen", "Mairie", "Openen"],
                       ["Ontvangen delen 0 van 1", "Mairie", "Openen"],
                       ["2 te vernieuwen documenten", "URSSAF · verlopen op 18/10", "Bekijken"]]
    assert r["es"] == [["Se solicita su acuerdo", "Toiture · mandatario: Breizh", "Leer y dar mi acuerdo"],
                       ["Invitación a responder en agrupación", "Gymnase · mandatario: Kerhel", "Ver la invitación"],
                       ["Fecha límite hoy", "École", "Abrir"],
                       ["Fecha límite dentro de 2 días", "Mairie", "Abrir"],
                       ["Partes recibidas 0 de 1", "Mairie", "Abrir"],
                       ["2 documentos a renovar", "URSSAF · caducado el 18/10", "Ver"]]
    assert r["joint"]                                     # le titre et le détail en français restent ceux d'avant
    # Une seule pièce, pas encore expirée.
    une = _a_faire_traduit({"expiring": [{"name": "Kbis", "expiration_date": "2026-11-10"}]})
    assert une["fr"] == [["1 pièce à renouveler", "Kbis · expire le 10/11", "Voir"]]
    assert une["nl"] == [["1 te vernieuwen document", "Kbis · verloopt op 10/11", "Bekijken"]]
    assert une["es"] == [["1 documento a renovar", "Kbis · caduca el 10/11", "Ver"]]


def test_24_la_cloche_et_l_accueil_affichent_chaque_morceau_dans_son_noeud():
    for nom, pre in (("fenetre-notifications", "nf"), ("accueil-a-faire", "af")):
        z = zone(HTML, nom)
        assert "{{ t.titre }}" not in z and "{{ t.detail }}" not in z, nom
        assert ('<b class="small"><span v-for="(m,mi) in t.morceauxTitre" :key="\'' + pre + 't\'+t.k+mi">{{ m }}</span></b>') in z, nom
        assert ('<span class="muted small"><span v-for="(m,mi) in t.morceauxDetail" :key="\'' + pre + 'd\'+t.k+mi">{{ m }}</span></span>') in z, nom
