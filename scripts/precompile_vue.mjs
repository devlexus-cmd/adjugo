/**
 * Précompilation des gabarits Vue → render functions (app/static/app.render.js).
 *
 * POURQUOI : en production, Vue est chargé en build RUNTIME-ONLY (vendor/vue.runtime-*.prod.js),
 * sans compilateur de gabarits. La compilation à l'exécution (build complet) exige
 * `script-src 'unsafe-eval'` dans la CSP (elle utilise `new Function`). En précompilant ici,
 * au build (comme scripts/sri_update.py), on retire DÉFINITIVEMENT `unsafe-eval` sans rien
 * changer au rendu : `@vue/compiler-dom` produit EXACTEMENT les mêmes render functions que le
 * compilateur embarqué dans le build complet (même version, mêmes options). La perf s'améliore
 * (plus de compilation dans le navigateur au démarrage).
 *
 * Ce qui est précompilé :
 *   - le gabarit in-DOM de la racine (innerHTML de #app dans app.html), sous la clé "__root__" ;
 *   - les 7 gabarits `template:` des composants enregistrés dans app.js (clé = la chaîne exacte).
 * La racine reçoit son render directement (1 ligne dans app.js) ; les composants passent par
 * `Vue.registerRuntimeCompiler` (app/static/vue-precompiled.js), qui renvoie le render précompilé
 * au lieu de compiler.
 *
 * Reproductibilité : `npm install --no-save @vue/compiler-dom@3.5.38 jsdom` puis
 *   node scripts/precompile_vue.mjs
 * La version de @vue/compiler-dom DOIT correspondre au build Vue vendorisé (3.5.38).
 *
 * jsdom sert à normaliser le gabarit in-DOM comme le ferait un navigateur (insertion de
 * <tbody>, décodage d'entités, minuscules d'attributs) : c'est exactement ce que lit le
 * compilateur à l'exécution sur `container.innerHTML`.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { compile } from "@vue/compiler-dom";
import vuePkg from "@vue/compiler-dom/package.json" with { type: "json" };

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(HERE, "..", "app", "static");
const APP_HTML = path.join(STATIC, "app.html");
const APP_JS = path.join(STATIC, "app.js");
// Sortie : app/static/app.render.js par défaut ; surchargeable (ADJUGO_RENDER_OUT ou 1er argument)
// pour que le test de non-régression régénère dans un fichier temporaire et compare.
const OUT = process.env.ADJUGO_RENDER_OUT || process.argv[2] || path.join(STATIC, "app.render.js");

const VENDOR_VERSION = "3.5.38";
if (vuePkg.version !== VENDOR_VERSION) {
  console.error(`@vue/compiler-dom ${vuePkg.version} ≠ build vendorisé ${VENDOR_VERSION} : installez la bonne version.`);
  process.exit(1);
}

// ── 1) Gabarit racine : innerHTML de #app, normalisé par le parseur HTML (jsdom) ──
const html = fs.readFileSync(APP_HTML, "utf8");
const rootTpl = new JSDOM(html).window.document.getElementById("app").innerHTML;

// ── 2) Gabarits des composants : on exécute app.js avec un faux Vue qui capture les `template:` ──
const captured = {};            // nom → définition du composant
const appStub = {
  config: {},
  component(name, def) { captured[name] = def; return appStub; },
  directive() { return appStub; },
  use() { return appStub; },
  mixin() { return appStub; },
  provide() { return appStub; },
  mount() { return {}; },
  unmount() { },
};
const VueStub = {
  createApp() { return appStub; },
  markRaw: (x) => x,
  version: VENDOR_VERSION,
};
// Globals minimaux pour que le chargement d'app.js (définitions + createApp + .component + .mount)
// n'échoue pas. Aucune méthode de composant n'est appelée (pas de rendu, pas de réseau).
const store = {};
const noopEl = { style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  setAttribute() {}, appendChild() {}, addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  querySelectorAll: () => [], focus() {} };
const win = {
  Vue: VueStub,
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
  navigator: { language: "fr", userAgent: "node", clipboard: {} },
  location: { href: "http://localhost/app", search: "", pathname: "/app", hash: "", origin: "http://localhost", replace() {} },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
  addEventListener() {}, removeEventListener() {}, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, fetch: () => Promise.reject(new Error("no fetch au build")),
  document: {
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
    getElementById: () => null, createElement: () => ({ ...noopEl }), documentElement: { ...noopEl, lang: "" },
    body: { ...noopEl }, head: { ...noopEl }, title: "", cookie: "", visibilityState: "visible",
  },
  console,
};
win.window = win;
win.self = win;
win.globalThis = win;

const src = fs.readFileSync(APP_JS, "utf8");
// Exécution d'app.js dans un contexte avec nos globals (les `const` top-level restent locaux à la fonction).
const names = Object.keys(win);
try {
  // Sloppy mode (pas de "use strict") : app.js est servi comme script classique.
  // eslint-disable-next-line no-new-func
  const run = new Function(...names, src);
  run(...names.map((n) => win[n]));
} catch (e) {
  console.error("Échec d'exécution d'app.js pour récolter les gabarits :", e && e.stack || e);
  process.exit(1);
}

const compNames = Object.keys(captured);
// Clé = la CHAÎNE EXACTE du gabarit : c'est ainsi que Vue appelle le compilateur à l'exécution
// (registerRuntimeCompiler reçoit le `template` de chaque composant). La racine garde "__root__"
// (son render est injecté directement dans app.js, pas via le compilateur).
const templates = { __root__: rootTpl };
for (const name of compNames) {
  const def = captured[name];
  if (def && typeof def.template === "string") templates[def.template] = def.template;
}
// Un composant est couvert si son gabarit (chaîne) est dans `templates`, ou s'il a déjà un render.
const missing = compNames.filter((n) => {
  const def = captured[n];
  if (!def) return true;
  if (typeof def.template === "string") return !(def.template in templates);
  return !def.render;
});
console.log(`Composants récoltés : ${compNames.length} (${compNames.join(", ")})`);

// ── 3) Compilation (mêmes options que compileToFunction du build complet : { hoistStatic: true }) ──
function compileOne(tpl) {
  const { code } = compile(tpl, { hoistStatic: true });
  return code;
}

// ── 4) Émission : script CLASSIQUE (sloppy mode obligatoire : les render functions utilisent `with`) ──
let out = "";
out += "/* Généré par scripts/precompile_vue.mjs — NE PAS ÉDITER.\n";
out += `   Render functions précompilées (Vue ${VENDOR_VERSION}) : retire 'unsafe-eval' de la CSP.\n`;
out += "   Régénérer après toute modification du gabarit de app.html ou des template: de app.js. */\n";
out += "window.__ADJ_R = window.__ADJ_R || {};\n";
for (const [key, tpl] of Object.entries(templates)) {
  const code = compileOne(tpl);
  out += `window.__ADJ_R[${JSON.stringify(key)}] = (function(){ var Vue = window.Vue;\n${code}\n})();\n`;
}
out += "(function(){ for (var k in window.__ADJ_R) { if (window.__ADJ_R[k]) window.__ADJ_R[k]._rc = true; } })();\n";

fs.writeFileSync(OUT, out, "utf8");
console.log(`Écrit : ${path.relative(path.resolve(HERE, ".."), OUT)} (${templates.__root__ ? "racine + " : ""}${compNames.length} composants, ${out.length} octets)`);
if (missing.length) { console.error("ATTENTION : composants sans gabarit ni render :", missing); process.exit(1); }
