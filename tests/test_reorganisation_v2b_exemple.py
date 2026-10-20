"""
Réorganisation de l'interface — vague 2b, chantier B2 « marché d'exemple » (contrat : docs/REORGANISATION_V2B.md, B2 ;
étude « organisation du logiciel », § 7.5, décision 13 a).

Une page À PART, à l'adresse /app/exemple, EN LECTURE SEULE : le parcours d'un marché à plusieurs jusqu'à « Seul 43 % ·
À plusieurs 100 % », puis l'écran du partenaire. ENTIÈREMENT FICTIF et dit comme tel (« Exemple · entreprises et client
fictifs » sur chaque bloc), noms repris de la démonstration. Données : un fichier statique versionné
(app/static/exemple-marche.json), servi tel quel au navigateur — ni base, ni IA, ni réseau. Il ne se mélange jamais aux
vraies données : aucune écriture, aucun appel à l'API, jamais dans Mes marchés, jamais par openAo.

1. L'adresse et l'écran : /app/exemple, la vue « exemple » (rubrique Accueil, sans entrée de menu), le fichier servi.
2. Les chiffres : ceux du calcul d'Adjugo appliqué aux données de l'exemple (score_groupement), et cohérents entre eux.
3. Fictif et dit comme tel : la mention sur chaque bloc, les seuls noms de la démo, aucun vrai organisme, aucun contact.
4. L'analyse réécrite : ni « No-Go », ni injonction, ni mot banni, ni « vérifié », ni émoji.
5. Lecture seule : aucun champ, aucun geste qui écrit, aucun appel à l'API (sous Node, avec les vraies méthodes), et
   rien ne change côté serveur (marchés, statistiques, quota, alertes, historique du réseau).
6. Entrée, mesure d'usage anonyme, traductions, téléphone.

Aucun appel réseau : fonctions de app.js exécutées sous Node, API locale, base SQLite des tests.
"""
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.textes_visibles import mots_bannis, textes_html
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
FICHIER = STATIC / "exemple-marche.json"
EX = json.loads(FICHIER.read_text(encoding="utf-8"))
MENTION = "Exemple · entreprises et client fictifs"
BLOCS = ["exemple-entete", "exemple-lire", "exemple-decider", "exemple-preparer", "exemple-deposer",
         "exemple-partenaire"]

_PUR = JS[JS.index("// ══════════ Marché d'exemple (réorganisation, vague 2b, chantier B2"):
          JS.index("// Traduction runtime de l'UI")]
_ADRESSES = JS[JS.index("// ══════════ Une adresse par écran (réorganisation, vague 2a, A1) ══════════"):
               JS.index("// ══════════ Réorganisation, vague 2a (chantier A3) ══════════")]
_RUBRIQUES = JS[JS.index("const RUBRIQUES = ["):JS.index("// ══════════ Mes marchés en liste filtrable")]


def _method(nom):
    """Le texte d'une méthode de l'application (async comprise), comme tests/test_reseau_ecrans._method."""
    m = (re.search(r"\n    (?:async )?" + re.escape(nom) + r"\(([\w, ]*)\) \{\n.*?\n    \},\n", JS, re.S)
         or re.search(r"\n    (?:async )?" + re.escape(nom) + r"\(([\w, ]*)\) \{ .*? \},\n", JS))
    assert m, f"méthode {nom} introuvable"
    return m.group(0).strip()


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _textes(x, chemin=""):
    """Toutes les chaînes du fichier (clés « _lisez_moi » comprises : rien n'y échappe), avec leur chemin."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _textes(v, chemin + "." + k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _textes(v, f"{chemin}[{i}]")
    elif isinstance(x, str):
        yield chemin, x


def _affiches():
    """Les chaînes que la page affiche (le bloc « calcul » et les notes « _lisez_moi » ne le sont pas)."""
    return [(c, t) for c, t in _textes({k: v for k, v in EX.items() if k != "calcul"}) if "_lisez_moi" not in c]


# ═══ 1. L'adresse, l'écran, le fichier ════════════════════════════════════════════════════════════════════════════

def test_l_exemple_a_son_adresse_et_sa_rubrique_sans_entree_de_menu():
    r = _node(_ADRESSES + "\n" + _RUBRIQUES + """
console.log(JSON.stringify({ a: adresseDe({ view: "exemple" }), e: etatDeAdresse("/app/exemple"),
  e2: etatDeAdresse("/app/exemple/"), x: etatDeAdresse("/app/exemple/12"),
  rub: RUBRIQUES.filter(r => r.vues.indexOf("exemple") >= 0).map(r => r.k),
  onglet: RUBRIQUES.some(r => r.onglets.some(t => t.view === "exemple")) }));
""")
    assert r["a"] == "/app/exemple" and r["e"] == {"view": "exemple"} and r["e2"] == {"view": "exemple"}
    assert r["x"] == {"view": "dashboard", "inconnue": True}                     # rien d'autre sous cette adresse
    assert r["rub"] == ["accueil"] and r["onglet"] is False                      # une page à part, pas un onglet
    assert "go('exemple')" not in zone(HTML, "menu") and "exemple" not in zone(HTML, "menu-bas")
    # L'en-tête dit le nom de la page (et non « Accueil ») ; la bulle de l'en-tête dit ce qu'elle est.
    assert 'exemple: "Marché d\'exemple"' in JS
    assert '(r.k === "accueil" && this.view === "dashboard")' in _method("enteteTitre")
    assert 'exemple: "Un marché inventé, en lecture seule :' in JS


def test_la_page_est_servie_a_son_adresse_et_le_fichier_tel_quel(client):
    base = client.get("/app")
    r = client.get("/app/exemple")
    assert r.status_code == 200 and r.text == base.text
    assert r.headers["cache-control"] == "no-store, must-revalidate"
    f = client.get("/static/exemple-marche.json")           # sans session : un fichier statique, sans donnée de compte
    assert f.status_code == 200 and f.headers["content-type"].startswith("application/json")
    assert f.content == FICHIER.read_bytes() and f.headers["cache-control"] == "no-store, must-revalidate"
    assert 'const EXEMPLE_FICHIER = "/static/exemple-marche.json";' in JS


def test_le_fichier_a_tout_ce_que_la_page_lit_sinon_la_page_le_dit():
    abime = [None, [], {}, dict(EX, decider=None), dict(EX, marche=dict(EX["marche"], nom="")),
             dict(EX, decider=dict(EX["decider"], seul="43")),
             dict(EX, deposer=dict(EX["deposer"], controles=[])),
             dict(EX, preparer=dict(EX["preparer"], repartition=[{"membre": "X"}])),
             dict(EX, ecran_partenaire=dict(EX["ecran_partenaire"], voit=None))]
    r = _node(_PUR + """
const ok = JSON.parse(process.argv[1]), abime = JSON.parse(process.argv[2]);
console.log(JSON.stringify({ ok: exempleValide(ok), abime: abime.map(exempleValide),
  eur: [eurExemple(280000), eurExemple(1250000), eurExemple("x")] }));
""", json.dumps(EX), json.dumps(abime))
    assert r["ok"] is True and r["abime"] == [False] * len(abime)
    sep = lambda s: re.sub(r"\s", " ", s)    # noqa: E731 — espace fine insécable du français
    assert [sep(x) for x in r["eur"]] == ["280 000 € HT", "1 250 000 € HT", ""]
    m = _method("exempleCharger")
    assert "exempleValide(d)" in m and "L'exemple n'a pas pu être chargé" in m      # jamais un exemple à moitié
    assert "exempleCharger(true)" in zone(HTML, "vue-exemple")                        # « Réessayer »


# ═══ 2. Les chiffres : ceux du calcul d'Adjugo, cohérents entre eux ═══════════════════════════════════════════════

def _calcul():
    from app.services.groupement_scoring import score_groupement
    from app.services.groupement_verdict import lead_member
    c = EX["calcul"]
    marche = {k: v for k, v in c["marche"].items() if k != "jours_pour_repondre"}
    marche["date_limite"] = (dt.date.today() + dt.timedelta(days=c["marche"]["jours_pour_repondre"])).strftime("%d/%m/%Y")
    lead = lead_member(c["entreprise"], c["criteres"])
    return score_groupement(marche, c["entreprise"], c["criteres"], [lead, dict(c["partenaire"])])


def test_seul_43_a_plusieurs_100_sont_ceux_du_calcul_d_adjugo():
    r, d = _calcul(), EX["decider"]
    assert (d["seul"], d["a_plusieurs"]) == (43, 100) == (r["score_seul"], r["score_groupement"])
    assert (d["seul_decision"], d["a_plusieurs_decision"]) == (r["decision_seul"], r["decision"]) == ("a_etudier", "go_groupement")
    calc = {c["key"]: c for c in r["breakdown"]}
    assert [c["key"] for c in d["criteres"]] == [c["key"] for c in r["breakdown"]]
    for c in d["criteres"]:
        k = calc[c["key"]]
        assert (c["label"], c["seul"], c["a_plusieurs"], c["max"], c["apporte_par"]) == (
            k["label"], k["points_seul"], k["points_groupement"], k["max_points"], k["apporte_par"]), c["key"]
    assert sum(c["seul"] for c in d["criteres"]) == 43 and sum(c["a_plusieurs"] for c in d["criteres"]) == 100
    # Les manques montrés sont ceux du calcul seul, tous comblés à plusieurs, par le partenaire de l'exemple.
    assert {g["key"] for g in d["manques"]} == {g["key"] for g in r["gaps_combles"]} and r["gaps"] == []
    assert all(g["apporte_par"] == [EX["partenaire"]["nom"]] for g in r["gaps_combles"])
    assert r["cumul"]["ca_n1"] == 3350000 and r["cumul"]["cumul_admis"] is True
    assert "1 250 000 € + 2 100 000 € = 3 350 000 €" in d["cumul"] and "3 000 000 €" in d["cumul"]
    # L'avertissement que le calcul porte (capacités déclarées, à confirmer) est dit à l'écran.
    assert any("déclarées par vous (Breizh Désamiantage)" in w for w in r["warnings"])
    assert "déclarées par Bâtiment de l'Ouest" in d["avertissement"] and "à confirmer" in d["avertissement"]
    # Les phrases citées sont celles du règlement de l'exemple, mot pour mot.
    phrases = {x["phrase"] for x in EX["lire"]["exigences"]}
    assert all(g["phrase"] in phrases for g in d["manques"] if g["phrase"])
    from app.services import demo_groupement as dg
    assert {dg.EXIGENCE_CA, dg.EXIGENCE_QUALIFICATIONS, dg.EXIGENCE_CAPACITES} == phrases


def test_les_montants_les_parts_et_les_controles_sont_coherents():
    pr, ep, dp = EX["preparer"], EX["ecran_partenaire"], EX["deposer"]
    assert sum(m["prix_ht"] for m in pr["repartition"]) == pr["total_ht"] == ep["total_ht"] == 1250000
    part = next(m for m in pr["repartition"] if m["membre"] == EX["partenaire"]["nom"])
    assert part["prix_ht"] == ep["prix_ht"] and ep["chef_de_file"] == EX["entreprise"]["nom"]
    assert EX["marche"]["montant"] == "1 250 000 € HT" and len(EX["marche"]["parties"]) == 3
    assert (pr["parts_recues"], pr["parts_attendues"], pr["accords"], pr["membres"]) == (1, 1, 2, len(pr["repartition"]))
    assert ep["a_plusieurs"] == EX["decider"]["a_plusieurs"] == EX["decider"]["complete"]["a_plusieurs"]
    assert ep["apporte"] == EX["decider"]["complete"]["apporte"]
    # « Avant de déposer » : un contrôle manquant, nommé ; les autres faits, sans phrase de manque.
    assert [c["ok"] for c in dp["controles"]] == [True, False, True, True]
    assert all(bool(c["manque"]) is (not c["ok"]) for c in dp["controles"])
    tpl = zone(HTML, "exemple-deposer")
    assert "{{ exOk(ex.deposer.controles) }} contrôles sur {{ ex.deposer.controles.length }}" in tpl
    # Décision 8 : le seul pourcentage est le couple seul / à plusieurs, après le dossier ; ailleurs « N sur M ».
    dec = zone(HTML, "exemple-decider")
    assert "Seul {{ ex.decider.seul }} % · À plusieurs {{ ex.decider.a_plusieurs }} %" in dec
    assert "%" not in zone(HTML, "exemple-lire").replace("{{ c.poids }}", "")
    assert "Parts reçues {{ ex.preparer.parts_recues }} sur {{ ex.preparer.parts_attendues }}" in zone(HTML, "exemple-preparer")


# ═══ 3. Entièrement fictif, et dit comme tel ══════════════════════════════════════════════════════════════════════

def test_chaque_bloc_porte_la_mention_fictif():
    page = zone(HTML, "vue-exemple")
    charge = page[page.index("<template v-for=\"ex in (exemple.d ? [exemple.d] : [])\""):]
    for b in BLOCS:
        assert MENTION in zone(HTML, b), b
        assert zone(HTML, b) in charge, b
    # Chaque carte de l'exemple chargé porte la mention (une par carte, aucune carte sans elle).
    cartes = re.findall(r'<div(?: data-test="[a-z-]+")? class="card\b', charge)
    assert cartes and charge.count(MENTION) == len(cartes) == len(BLOCS)
    assert 'aria-label="Marché d\'exemple"' in page


def test_seulement_les_noms_fictifs_de_la_demo_jamais_un_vrai_organisme_ni_un_contact():
    demo = (ROOT / "app" / "services" / "demo_seed.py").read_text(encoding="utf-8")
    noms = {EX["entreprise"]["nom"], EX["partenaire"]["nom"], EX["marche"]["client"],
            EX["ecran_partenaire"]["chef_de_file"], EX["decider"]["complete"]["nom"]}
    noms |= {m["membre"] for m in EX["preparer"]["repartition"]}
    noms |= {n for c in EX["decider"]["criteres"] for n in c["apporte_par"]}
    assert noms == {"Bâtiment de l'Ouest", "Breizh Désamiantage", "Kerhel Agglomération"}
    for n in noms:
        assert f'"{n}"' in demo, n                                              # déjà dans la démo de pitch
    assert EX["marche"]["nom"] in demo and EX["marche"]["objet"] in demo
    tout = json.dumps(EX, ensure_ascii=False)
    from tests.test_demo_sans_cout import _COURRIEL, _REELS, _TEL
    for reel in _REELS:
        assert reel not in tout, reel
    assert not _COURRIEL.search(tout) and not _TEL.search(tout)
    assert not re.search(r"\d{9,}", tout)                                         # ni SIREN ni SIRET
    assert not re.search(r"https?://|www\.", tout)
    # Aucune personne : ni les représentants ni les contacts (fictifs) de la démo.
    for personne in re.findall(r'(?:representant_legal|"nom")\s*[=:]\s*"([^"]+)"', demo):
        prenom_nom = personne.split(",")[0].strip()
        if " " in prenom_nom:
            assert prenom_nom not in tout, prenom_nom
    for personne in ("Soizic Morvan", "Gwénaël Le Bihan", "Sabine Vidal", "Hervé Quéméner", "Loïc Le Berre"):
        assert personne not in tout, personne
    # La démo de pitch n'est pas lue par l'exemple (et ne le lit pas).
    assert "exemple-marche" not in demo


# ═══ 4. L'analyse réécrite : ni « No-Go », ni injonction ══════════════════════════════════════════════════════════

_INJONCTIONS = re.compile(r"\b(il faut|vous devez|devez|doit répondre|foncez|n'hésitez|bonne stratégie|à ne pas manquer|"
                          r"impérati\w*|vivement|recommand\w*|uniquement en groupement|hors d'atteinte|à écarter)\b|!", re.I)


def test_analyse_sans_no_go_sans_injonction_sans_mot_banni():
    fautes = []
    for chemin, t in _textes(EX):
        if mots_bannis(t):
            fautes.append((chemin, mots_bannis(t), t))
    assert not fautes, fautes
    for chemin, t in _affiches():
        assert not _INJONCTIONS.search(t), (chemin, t)
        assert "vérifi" not in t.lower(), (chemin, t)                             # décision 9 : rien n'est « vérifié »
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t), chemin
        assert "co-trait" not in t.lower() and "consortium" not in t.lower() and "mandataire" not in t.lower()
    # Le parcours dit ce que fait Adjugo et laisse la décision à l'entreprise.
    assert "c'est l'entreprise qui décide" in EX["decider"]["decision"]
    # Le gabarit de la page, lui aussi (la garde des mots bannis du socle le lit déjà avec tout app.html).
    for _ln, t in textes_html(zone(HTML, "vue-exemple")):
        assert not mots_bannis(t), t
        assert "!" not in t and "vérifi" not in t.lower(), t


# ═══ 5. Lecture seule : aucun champ, aucun geste qui écrit, aucun appel à l'API ═══════════════════════════════════

def test_la_page_n_a_aucun_champ_ni_aucun_geste_qui_ecrit():
    page = zone(HTML, "vue-exemple")
    for interdit in ("v-model", "<input", "<select", "<textarea", "<form", "v-html", "contenteditable", "draggable"):
        assert interdit not in page, interdit
    gestes = set(re.findall(r'@click(?:\.prevent)?="([^"]+)"', page))
    assert gestes == {"exempleRetour()", "exempleCharger(true)", "rubriqueGo('trouver')", "rnScrollTo('exLire')",
                      "rnScrollTo('exDecider')", "rnScrollTo('exPreparer')", "rnScrollTo('exDeposer')",
                      "rnScrollTo('exPartenaire')"}, gestes
    assert not re.search(r'@(?!click)[a-z]', page)                               # ni @change, ni @submit, ni @input
    # Les méthodes de la page : un fichier statique, jamais l'API ni la page d'un marché.
    for nom in ("exempleCharger", "exempleRetour", "exEur", "exOk"):
        m = _method(nom)
        for x in ("this.api(", "openAo", "this.projects", "/api/", "localStorage", "sessionStorage"):
            assert x not in m, (nom, x)
    assert "fetch(EXEMPLE_FICHIER, { cache: \"no-store\" })" in _method("exempleCharger")
    go = _method("go")
    assert 'if (v === "exemple") this.exempleCharger();' in go


def test_ouvrir_l_exemple_ne_charge_que_le_fichier_sous_node():
    """go("exemple") avec les vraies méthodes : un seul fichier lu, aucune autre lecture, rien dans Mes marchés."""
    go, charger = _method("go").rstrip(","), _method("exempleCharger").rstrip(",")
    appels = sorted(set(re.findall(r"this\.(load\w+|rnGo|kbLoad|pvLoad|_pvSourcesCharger|srcPrefillFromProfile|"
                                   r"noteReorgMarquer|rnLoadRecues|mmFiltrer)\(", go)))
    stubs = ",\n".join(f"  {n}() {{ journal.push('{n}'); }}" for n in appels)
    r = _node(_PUR + """
const journal = [], lus = [];
const DATA = JSON.parse(process.argv[1]);
globalThis.document = { querySelector() { return null; } };
globalThis.fetch = async (url, opt) => { lus.push(url); return { ok: true, json: async () => DATA }; };
const o = {
""" + go + ",\n" + charger + ",\n" + stubs + """,
  features: {}, view: "dashboard", mmFiltre: "tous", trouverOnglet: "publies", mobileNav: true, notifsOpen: true,
  fb: { open: true }, reseau: { tab: "profil" }, projects: [{ id: 7 }], exemple: { d: null, err: "", chargement: false },
  _ecranOuvert(v) { journal.push("mesure:" + v); }, $nextTick(f) {}, openAo() { journal.push("openAo"); },
  api() { journal.push("api"); return Promise.reject(new Error("aucun appel")); },
};
o.go("exemple");
setImmediate(() => setImmediate(() => console.log(JSON.stringify({ journal, lus, view: o.view, projets: o.projects,
  charge: !!(o.exemple.d && o.exemple.d.marche), err: o.exemple.err, menu: o.mobileNav }))));
""", json.dumps(EX))
    assert r["view"] == "exemple" and r["charge"] is True and r["err"] == ""
    assert r["lus"] == ["/static/exemple-marche.json"]                            # le fichier statique, rien d'autre
    assert r["journal"] == ["mesure:exemple"]                                      # aucun chargement de l'API, ni openAo
    assert r["projets"] == [{"id": 7}] and r["menu"] is False                     # Mes marchés intact ; menu refermé


def _etat(client, h):
    """Ce que le serveur rend d'un compte : marchés, statistiques, quota, alertes, groupements, réseau, notifications."""
    out = {}
    for url in ("/api/projects/", "/api/agent/stats", "/api/auth/me", "/api/stripe/status", "/api/notifications",
                "/api/groupement/tableau-de-bord", "/api/consortiums", "/api/shared", "/api/documents/expiring",
                "/api/reseau/historique", "/api/saved-searches/"):
        r = client.get(url, headers=h)
        # L'heure du calcul (« calcule_le » du tableau de bord) change d'une seconde à l'autre : seule elle est neutralisée.
        out[url] = (r.status_code, re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", "<heure>", r.text))
    return out


def test_ouvrir_l_exemple_ne_change_rien_cote_serveur_et_la_mesure_reste_anonyme(client, auth):
    from app.core.database import SessionLocal
    from app.models import MesureEcran
    from app.services.mesure_usage import ECRANS, aujourd_hui
    assert "exemple" in ECRANS
    h = auth["headers"]
    avant = _etat(client, h)
    db = SessionLocal()
    try:
        n0 = sum(m.ouvertures for m in db.query(MesureEcran).filter(MesureEcran.ecran == "exemple").all())
    finally:
        db.close()
    # Ce que fait le navigateur : la page, le fichier, l'ouverture comptée (go → _ecranOuvert).
    assert client.get("/app/exemple", headers=h).status_code == 200
    assert client.get("/static/exemple-marche.json").status_code == 200
    assert client.post("/api/mesure/ecran", headers=h, json={"ecran": "exemple"}).status_code == 204
    assert _etat(client, h) == avant
    db = SessionLocal()
    try:
        lignes = db.query(MesureEcran).filter(MesureEcran.ecran == "exemple").all()
        assert sum(m.ouvertures for m in lignes) == n0 + 1 and {m.jour for m in lignes} >= {aujourd_hui()}
        assert {c.name for c in MesureEcran.__table__.columns} == {"jour", "ecran", "ouvertures"}   # ni compte ni organisation
    finally:
        db.close()


# ═══ 6. Entrée, traductions, téléphone ════════════════════════════════════════════════════════════════════════════

def test_une_entree_dans_repondre_a_plusieurs_par_l_adresse():
    carte = zone(HTML, "marche-plusieurs")
    assert '<a href="/app/exemple"' in carte and "@click.prevent=\"go('exemple')\"" in carte
    assert "Le parcours en entier sur un marché fictif :" in carte


LIBELLES = ["Marché d'exemple", MENTION, "Chargement de l'exemple…", "Réessayer", "Parties",
            "L'exemple n'a pas pu être chargé. Réessayez dans un instant.",
            "· l'entreprise qui répond", "· son partenaire",
            "Lecture seule : rien de cet exemple n'est enregistré dans votre compte.", "Étapes de l'exemple",
            "Aller à l'écran du partenaire", "Analyse du dossier du marché", "Ce que dit le règlement",
            "Comment l'offre sera notée", "Points, seul puis à plusieurs", "Exigé :", "Inviter et réunir les parts",
            "Répartition", "Membre", "Part", "Prix de vente HT", "Total de l'offre commune", "Ce que chacun voit",
            "L'écran du partenaire", "Chef de file :", "Pourquoi vous dans ce groupement", "Vous apportez :",
            "Votre prix", "Le détail de vos postes, vous seul le voyez.", "Il voit", "Il ne voit pas",
            "Le parcours en entier sur un marché fictif :", "voir un exemple"]


def test_traductions_des_libelles_de_l_exemple():
    r = subprocess.run([shutil.which("node") or "node", "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    page = zone(HTML, "vue-exemple") + zone(HTML, "marche-plusieurs") + JS
    for k in LIBELLES:
        assert k in page, k                                                       # le libellé est bien affiché
        assert d["nl"].get(k) and d["es"].get(k), k
    assert d["nl"][MENTION] != d["nl"]["Marché d'exemple"]


def test_lisible_a_375_px_et_accessible():
    page = zone(HTML, "vue-exemple")
    # Les classes de la page du marché (barre, colonnes seul / à plusieurs, manques, tableau) ; une colonne sur téléphone.
    for c in ('class="mk-etapes"', 'class="sg-cols"', 'class="gap"', 'class="cv-table cv-rep"', 'class="ex-acteurs"',
              'class="ex-voit"'):
        assert c in page, c
    m = CSS[CSS.index("/* Marché d'exemple (réorganisation, vague 2b, chantier B2)"):]
    assert "@media (max-width:640px)" in m and ".ex .ex-acteurs, .ex .ex-voit { grid-template-columns:minmax(0,1fr); }" in m
    assert "@media (max-width:720px){ .sg-cols { grid-template-columns:1fr; } }" in CSS
    # Titres reliés, ancres et statuts lus par un lecteur d'écran, bulles (i) avec leur libellé.
    for b in ("lire", "decider", "preparer", "deposer"):
        assert f'aria-labelledby="ex-{b}-h"' in zone(HTML, "exemple-" + b) and f'id="ex-{b}-h"' in zone(HTML, "exemple-" + b)
    assert 'aria-label="Étapes de l\'exemple"' in zone(HTML, "exemple-etapes")
    assert '<span class="sr-only"> : {{ c.ok ? \'fait\' : \'à faire\' }}</span>' in zone(HTML, "exemple-deposer")
    assert page.count('class="tip"') == page.count('<span class="sr-only">En savoir plus</span>') == 2
    assert '<th scope="col">Membre</th>' in page and '<th scope="row">{{ m.membre }}</th>' in page


def test_contrat_de_la_vague_2b_section_b2():
    doc = (ROOT / "docs" / "REORGANISATION_V2B.md").read_text(encoding="utf-8")
    b2 = doc[doc.index("## B2. Le marché d'exemple"):]
    for x in ("/app/exemple", "app/static/exemple-marche.json", MENTION, "Seul 43 % · À plusieurs 100 %",
              "score_groupement", "Bâtiment de l'Ouest", "Breizh Désamiantage", "Kerhel Agglomération",
              "Aucune migration", "demo_seed.py", "tests/test_reorganisation_v2b_exemple.py"):
        assert x in b2, x
    for n in ["vue-exemple"] + BLOCS + ["exemple-etapes"]:
        assert f"`{n}`" in b2, n
