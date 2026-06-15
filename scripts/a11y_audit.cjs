/**
 * Audit d'accessibilité (RGAA / WCAG 2.1 AA) automatisable en CI.
 *
 * Vérifie, sur la landing (/) et l'application (/app), les critères les plus
 * fréquemment violés : attribut lang, repère <main> unique, présence d'un <h1>,
 * nom accessible sur chaque champ et chaque bouton/lien, alt sur les images,
 * identifiants uniques. Sort en code non nul s'il trouve une violation → bloque la CI.
 *
 * Usage : BASE_URL=http://localhost:8000 node scripts/a11y_audit.cjs
 * Dépendances CI : npm i -D playwright && npx playwright install --with-deps chromium
 */
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL || "http://localhost:8000";
const PATHS = (process.env.A11Y_PATHS || "/,/app").split(",");

function audit() {
  const v = [];
  if (!document.documentElement.getAttribute("lang")) v.push("html sans attribut lang");
  const mains = document.querySelectorAll("main");
  if (mains.length !== 1) v.push(`<main> attendu=1, trouvé=${mains.length}`);
  if (!document.querySelector("h1")) v.push("aucun <h1>");
  document.querySelectorAll("input:not([type=hidden]),select,textarea").forEach((el, i) => {
    const name =
      el.getAttribute("aria-label") ||
      el.getAttribute("aria-labelledby") ||
      el.getAttribute("title") ||
      (el.id && document.querySelector(`label[for="${el.id}"]`)) ||
      el.closest("label") ||
      el.getAttribute("placeholder");
    if (!name) v.push(`champ sans nom accessible #${i} (${el.tagName} type=${el.getAttribute("type") || ""})`);
  });
  document.querySelectorAll("img").forEach((el, i) => {
    if (el.getAttribute("alt") === null && el.getAttribute("aria-hidden") !== "true" && el.getAttribute("role") !== "presentation")
      v.push(`<img> sans alt #${i} src=${(el.getAttribute("src") || "").slice(0, 40)}`);
  });
  document.querySelectorAll("button,a").forEach((el, i) => {
    const t = (el.textContent || "").trim() || el.getAttribute("aria-label") || el.getAttribute("title") || el.querySelector("img[alt]");
    if (!t) v.push(`${el.tagName} sans texte accessible #${i}`);
  });
  const ids = {};
  document.querySelectorAll("[id]").forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  Object.entries(ids).filter(([, n]) => n > 1).forEach(([k, n]) => v.push(`id dupliqué "${k}" (${n}×)`));
  return v;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newContext({ viewport: { width: 1280, height: 900 } }).then((c) => c.newPage());
  let total = 0;
  for (const path of PATHS) {
    await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000); // laisse Vue monter + _a11y() s'exécuter
    const v = await page.evaluate(audit);
    console.log(`\n=== ${path} : ${v.length} violation(s) ===`);
    v.forEach((x) => console.log("  ✗", x));
    if (!v.length) console.log("  ✓ aucune violation");
    total += v.length;
  }
  await browser.close();
  console.log(`\nTOTAL : ${total} violation(s)`);
  process.exit(total ? 1 : 0);
})().catch((e) => { console.error("FATAL", e); process.exit(2); });
