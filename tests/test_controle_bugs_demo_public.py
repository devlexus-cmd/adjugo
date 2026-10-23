"""Contrôle des bugs d'octobre 2026, groupe « demo-public » (page publique /acheteur et espace collectivités
/acheteur/app) : chaque test dit ce que le logiciel DOIT faire d'après ses contrats et ses textes affichés ; tous
échouaient sur cfe04e1, chacun sur son défaut.

25. La page /acheteur se déclare à l'adresse officielle du site (https://adjugo.pro, app/core/config.py et
    docs/legal/mentions-legales.md) : adresse canonique, og:url et og:image, jamais l'adresse technique de
    l'hébergeur (avant : https://adjugo-api-production.up.railway.app/…).
26. Aucun lien de la page publique /acheteur ne mène à une page fermée en production (avant : « API · /docs » et
    « OpenAPI », 404 en production, docs/AUDIT_CYBER_2026-10.md).
27. L'estimation du budget refusée à un visiteur non connecté dit « Connectez-vous pour utiliser cette fonction. »
    (avant : « Connectez-vous (ou lancez la démo) … », alors que la page n'a aucun moyen de lancer la démo : démo
    publique fermée le 08/10/2026, docs/DEMO_LIEN_PRIVE.md).
28. À 1 280, 1 366 et 1 440 px, le premier écran de /acheteur garde le rapport de sa grille (1.08fr / .92fr) : le
    titre tient dans sa colonne, les trois chiffres de la carte d'exemple tiennent sur une ligne, la carte « Pièces
    générées » reste dans l'écran (avant : colonne du titre à 840 px, carte à 301 px). Téléphone et tablette
    inchangés.
29. « Mes DCE » : la date de diffusion au réseau s'écrit JJ/MM/AAAA, comme « modifié le » (avant : « signalé au
    réseau le 2026-10-22 »).

Aucun réseau : la page /acheteur et ses fichiers sont servis depuis le dépôt, le code de acheteur.html est exécuté
sous Node ; un test ouvre en plus un vrai Chromium (Playwright) quand il est installé, toute requête vers
l'extérieur coupée, la police du titre lue dans app/static/fonts.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import uuid

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
LANDING = (STATIC / "acheteur-landing.html").read_text(encoding="utf-8")
ACH = (STATIC / "acheteur.html").read_text(encoding="utf-8")


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _fonction(src, debut):
    """Le texte de `debut` jusqu'à l'accolade qui ferme la première accolade ouverte après lui (chaînes sautées)."""
    i = src.index(debut)
    j, prof, chaine = src.index("{", i), 0, None
    while True:
        c = src[j]
        if chaine:
            if c == "\\":
                j += 1
            elif c == chaine:
                chaine = None
        elif c in "\"'":
            chaine = c
        elif c == "{":
            prof += 1
        elif c == "}":
            prof -= 1
            if not prof:
                return src[i:j + 1]
        j += 1


# ═══ 25. Adresse officielle de la page /acheteur ═══════════════════════════════════════════════════════════

def _meta(html, motif):
    m = re.search(motif, html)
    assert m, motif
    return m.group(1)


def test_25_la_page_acheteur_se_dit_a_son_adresse_officielle(client):
    from app.core.config import Settings
    officiel = Settings.model_fields["APP_BASE_URL"].default          # « Domaine officiel adjugo.pro »
    assert officiel == "https://adjugo.pro"
    r = client.get("/acheteur")
    assert r.status_code == 200
    html = r.text
    assert _meta(html, r'<link rel="canonical" href="([^"]+)">') == officiel + "/acheteur"
    assert _meta(html, r'<meta property="og:url" content="([^"]+)">') == officiel + "/acheteur"
    assert _meta(html, r'<meta property="og:image" content="([^"]+)">') == officiel + "/static/favicon.svg"
    assert client.get("/static/favicon.svg").status_code == 200      # l'image annoncée existe
    assert "railway.app" not in html


# ═══ 26. Aucun lien de /acheteur vers une page fermée en production ═════════════════════════════════════════

def test_26_la_page_acheteur_ne_mene_a_aucune_page_fermee_en_production(tmp_path):
    env = dict(os.environ)
    env.update({
        "ENVIRONMENT": "production", "DEMO_MODE": "false",
        "SECRET_KEY": uuid.uuid4().hex + uuid.uuid4().hex,
        "CRON_SECRET": uuid.uuid4().hex, "DCE_ACCESS_CODE": uuid.uuid4().hex,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'prod.db'}",
        "SENTRY_DSN": "", "ANTHROPIC_API_KEY": "", "MISTRAL_API_KEY": "", "BREVO_API_KEY": "",
    })
    code = (
        "import json, re\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app)\n"
        "out = {'docs': {p: c.get(p).status_code for p in ('/docs', '/openapi.json', '/redoc')}}\n"
        "r = c.get('/acheteur')\n"
        "out['page'] = r.status_code\n"
        "liens = sorted(set(re.findall(r'href=\"(/[^\"/#][^\"#]*)', r.text)))\n"
        "out['liens'] = {l: c.get(l).status_code for l in liens}\n"
        "print(json.dumps(out))\n"
    )
    p = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    # La fermeture des pages techniques en production reste (décision de sécurité, test_docs_coupees_en_production).
    assert out["docs"] == {"/docs": 404, "/openapi.json": 404, "/redoc": 404}
    assert out["page"] == 200
    assert "/acheteur/app?login=1" in out["liens"] and "/mentions-legales" in out["liens"], out["liens"]
    morts = {l: s for l, s in out["liens"].items() if s >= 400}
    assert not morts, morts


# ═══ 27. Estimation du budget refusée : pas de démo promise ════════════════════════════════════════════════

def test_27_l_estimation_refusee_ne_propose_pas_une_demo_que_le_visiteur_ne_peut_pas_lancer():
    # Le gestionnaire de la réponse de /api/dce/estimer-budget, exécuté tel quel avec une réponse 401.
    estim = _fonction(ACH, '$("#estimBtn").onclick=function(e)')
    traite = _fonction(estim, ".then(function(res){")[len(".then("):]
    r = _node("var note = {textContent: '', innerHTML: ''}; var esc = String;\n"
              "(" + traite + ")({status: 401, d: {detail: 'Accès restreint.'}});\n"
              "console.log(JSON.stringify(note.textContent));")
    assert r == "Connectez-vous pour utiliser cette fonction."
    # Rien sur la page ne lance la démo pour un visiteur (démo publique fermée, docs/DEMO_LIEN_PRIVE.md) : la page ne
    # doit donc pas la proposer.
    assert "/api/acheteur/demo" not in ACH
    assert "lancez la démo" not in ACH


# ═══ 28. Premier écran de /acheteur sur ordinateur ═════════════════════════════════════════════════════════

def _hors_blocs_at(css):
    """La feuille sans ses blocs « @… { … } » (@media, @keyframes) : les règles qui valent à toutes les largeurs."""
    out, i = [], 0
    while True:
        j = css.find("@", i)
        if j < 0:
            return "".join(out) + css[i:]
        out.append(css[i:j])
        k, prof = css.index("{", j), 0
        while True:
            prof += {"{": 1, "}": -1}.get(css[k], 0)
            if not prof:
                break
            k += 1
        i = k + 1


def test_28_les_cellules_de_la_grille_du_haut_peuvent_retrecir_et_le_titre_y_tient():
    css = LANDING[LANDING.index("<style>") + 7:LANDING.index("</style>")]
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    hors = _hors_blocs_at(css)
    # Une cellule de grille garde sinon la largeur de son contenu : le titre sur une ligne (white-space:nowrap)
    # imposait 840 px à la première colonne.
    assert re.search(r"\.hero-grid > \* \{\s*min-width:0;?\s*\}", hors), "cellules de .hero-grid rétrécissables"
    # Sur deux colonnes (au-delà de 940 px), « Trouvez qui peut y répondre. » tient sur une ligne dans sa colonne,
    # 587 px au plus : mesuré dans Chromium avec la police de Google Fonts, la ligne fait 12,1 (à 68 px) à 12,8 (à
    # 32 px) fois la taille de la police, point compris en plus ; 600 px à 48 px, 564 px à 44 px.
    m = re.search(r"@media \(min-width:941px\) \{[^@]*?h1\.hero-title \{ font-size:clamp\((\d+)px,([\d.]+)vw,(\d+)px\); \}", css)
    assert m, "taille du titre sur deux colonnes"
    assert int(m.group(3)) <= 44 and int(m.group(1)) >= 32
    assert 941 * float(m.group(2)) / 100 * 12.81 + 10 <= (941 - 112) * 1.08 / 2     # colonne la plus étroite
    # Téléphone et tablette : la règle d'avant reste.
    assert "h1.hero-title { font-size:clamp(40px,5.4vw,68px);" in css
    assert re.search(r"@media \(max-width:560px\) \{[^@]*h1\.hero-title \{ font-size:34px; \}", css)


_MESURE = r"""
let pw; try { pw = require("playwright"); } catch (e) { console.log(JSON.stringify({ absent: true })); process.exit(0); }
const fs = require("fs"), path = require("path");
const [html, statique] = JSON.parse(process.argv[1]);
const POLICE = "@font-face{font-family:'Bricolage Grotesque';src:url(https://fonts.gstatic.com/bricolage.woff2) format('woff2');font-weight:200 800}";
(async () => {
  const b = await pw.chromium.launch();
  const out = {};
  for (const [w, h] of [[1280, 900], [1366, 900], [1440, 900], [1024, 768], [768, 1024], [375, 812]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
    await ctx.route("**/*", r => {
      const u = r.request().url();
      if (u === "http://adjugo.test/acheteur") return r.fulfill({ contentType: "text/html", body: html });
      if (u.startsWith("http://adjugo.test/static/")) {
        const f = path.join(statique, decodeURIComponent(new URL(u).pathname.slice(8)));
        return fs.existsSync(f) ? r.fulfill({ path: f }) : r.abort();
      }
      if (u.startsWith("https://fonts.googleapis.com/")) return r.fulfill({ contentType: "text/css", body: POLICE });
      if (u === "https://fonts.gstatic.com/bricolage.woff2") return r.fulfill({ path: path.join(statique, "fonts", "bricolage-grotesque.woff2") });
      return r.abort();
    });
    const p = await ctx.newPage();
    await p.goto("http://adjugo.test/acheteur");
    await p.evaluate(() => document.fonts.ready);
    out[w] = await p.evaluate(() => {
      const q = s => document.querySelector(s), R = e => e.getBoundingClientRect();
      const wrap = q(".hero-grid"), cs = getComputedStyle(wrap), titre = q("h1.hero-title");
      const col = wrap.children[0];
      return {
        police: [...document.fonts].some(f => f.family.includes("Bricolage") && f.status === "loaded"),
        colonnes: cs.gridTemplateColumns.split(" ").map(parseFloat),
        taille: parseFloat(getComputedStyle(titre).fontSize),
        titreDroite: (() => { const g = document.createRange(); g.selectNodeContents(titre);
                              return Math.max(...[...g.getClientRects()].map(x => x.right)); })(),   // point compris
        colDroite: R(col).right,
        contenuDroite: R(wrap).right - parseFloat(cs.paddingRight),
        visuelDroite: R(q(".visual")).right,
        valeurs: [...document.querySelectorAll(".pv-kpi .v")].map(e => Math.round(R(e).height)),
        pv2Droite: getComputedStyle(q(".pv-2")).display === "none" ? null : R(q(".pv-2")).right,
        ecran: innerWidth,
      };
    });
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(String(e)); process.exit(1); });
"""


def test_28_premier_ecran_de_la_page_acheteur_mesure_dans_un_navigateur():
    """Chromium réel (Playwright, s'il est installé), aucune requête vers l'extérieur, police du titre servie depuis
    app/static/fonts : sur deux colonnes, la grille garde son rapport, le titre tient dans sa colonne, les chiffres de
    la carte d'exemple tiennent sur une ligne et la carte « Pièces générées » reste dans l'écran."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    env = dict(os.environ)
    env["NODE_PATH"] = os.pathsep.join(x for x in (env.get("NODE_PATH", ""), str(ROOT / "node_modules")) if x)
    r = subprocess.run([node, "-e", _MESURE, json.dumps([LANDING, str(STATIC)])], capture_output=True, text=True,
                       timeout=180, env=env, cwd=str(ROOT))
    if r.returncode and "Executable doesn't exist" in r.stderr:
        pytest.skip("navigateur de Playwright non installé")
    assert r.returncode == 0, r.stderr
    m = json.loads(r.stdout.strip().splitlines()[-1])
    if m.get("absent"):
        pytest.skip("Playwright non installé")
    for w in ("1280", "1366", "1440", "1024"):
        x = m[w]
        assert x["police"], (w, x)
        a, b = x["colonnes"]
        assert abs(a / b - 1.08 / .92) < 0.01, (w, x)                  # 587 / 500 px à 1 280 px, plus 840 / 301
        assert x["titreDroite"] <= x["colDroite"] + 0.5, (w, x)          # le titre ne déborde pas sur la carte
        assert x["visuelDroite"] <= x["contenuDroite"] + 0.5, (w, x)     # la carte reste dans le contenu de la page
        assert len(set(x["valeurs"])) == 1 and len(x["valeurs"]) == 3, (w, x)   # trois chiffres, chacun sur une ligne
        assert x["pv2Droite"] is not None and x["pv2Droite"] <= x["ecran"], (w, x)
    # Une colonne : tablette et téléphone gardent leur taille de titre (5,4 % de la largeur, au moins 40 px ; 34 px).
    assert abs(m["768"]["taille"] - max(40, 768 * 0.054)) < 0.1, m["768"]
    assert m["375"]["taille"] == 34, m["375"]


# ═══ 29. « Mes DCE » : date de diffusion au réseau en JJ/MM/AAAA ═══════════════════════════════════════════

def test_29_la_date_de_diffusion_au_reseau_s_ecrit_comme_les_autres_dates():
    # La ligne de « Mes DCE » (loadMesDce), exécutée telle quelle avec un DCE comme le renvoie GET /api/acheteur/dce
    # (_out : date_diffusion = date ISO sur 10 caractères), celui de la démo diffusé au réseau.
    debut = ACH.index("h+='<tr data-id=\"'+d.id+'\"><td>")
    fin = ACH.index("</td></tr>';", debut) + len("</td></tr>';")
    ligne = ACH[debut:fin]
    fonctions = "\n".join(re.search(r"  (function " + nom + r"\(.*)", ACH).group(1) for nom in ("esc", "jourFr"))
    d = {"id": 7, "objet": "Rénovation énergétique de l'école primaire des Tilleuls", "statut": "preparation",
         "updated_at": "2026-10-22T17:07:45.926419", "diffuse": True, "date_diffusion": "2026-10-22", "date_limite": None}
    texte = _node(fonctions + "\nvar STATUTS = [['preparation', 'En préparation', 'neutral']];\n"
                  "var d = JSON.parse(process.argv[1]), h = '', dl = d.date_limite || '', late = false;\n"
                  + ligne + "\nconsole.log(JSON.stringify(h.replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ')));",
                  json.dumps(d))
    assert "modifié le 22/10/2026" in texte, texte
    assert "signalé au réseau le 22/10/2026" in texte, texte
    assert "2026-10-22" not in texte, texte
