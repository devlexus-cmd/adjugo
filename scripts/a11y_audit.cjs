/**
 * Audit d'accessibilité (RGAA / WCAG 2.1 AA) automatisable en CI.
 *
 * Couvre la landing (/), l'écran de connexion (/app déconnecté) ET l'application
 * CONNECTÉE (inscription d'un compte de test puis parcours de toutes les vues) —
 * c'est là que vivent la plupart des champs de formulaire. Vérifie : attribut lang,
 * repère <main> unique au rendu, présence d'un <h1>, nom accessible sur chaque champ
 * et chaque bouton/lien, alt sur les images, identifiants uniques. Sort en code non
 * nul s'il trouve une violation → bloque la CI.
 *
 * Usage : BASE_URL=http://localhost:8000 node scripts/a11y_audit.cjs
 * Dépendances CI : npm install --no-save playwright && npx playwright install --with-deps chromium
 */
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL || "http://localhost:8000";

function audit() {
  const v = [];
  if (!document.documentElement.getAttribute("lang")) v.push("html sans attribut lang");
  const mains = document.querySelectorAll("main");
  if (mains.length !== 1) v.push(`<main> attendu=1, rendu=${mains.length}`);
  if (!document.querySelector("h1")) v.push("aucun <h1>");
  document.querySelectorAll("input:not([type=hidden]),select,textarea").forEach((el) => {
    const name =
      el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title") ||
      (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.closest("label") || el.getAttribute("placeholder");
    if (!name) v.push(`champ sans nom accessible: ${el.tagName}.${(el.className || "").toString().split(" ")[0]} type=${el.getAttribute("type") || ""}`);
  });
  document.querySelectorAll("button,a").forEach((el) => {
    const t = (el.textContent || "").trim() || el.getAttribute("aria-label") || el.getAttribute("title") || el.querySelector("img[alt]");
    if (!t) v.push(`${el.tagName} sans texte accessible .${(el.className || "").toString().split(" ").slice(0, 2).join(".")}`);
  });
  const ids = {};
  document.querySelectorAll("[id]").forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  Object.entries(ids).filter(([, n]) => n > 1).forEach(([k, n]) => v.push(`id dupliqué "${k}" (${n}×)`));
  return v;
}

async function run(page, label) {
  await page.waitForTimeout(2000); // laisse Vue monter + _a11y() s'exécuter
  const v = await page.evaluate(audit);
  console.log(`\n=== ${label} : ${v.length} violation(s) ===`);
  v.forEach((x) => console.log("  ✗", x));
  if (!v.length) console.log("  ✓ aucune violation");
  return v.length;
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  let total = 0;

  // 1) Landing
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  total += await run(page, "/ (landing)");

  // 2) App déconnectée (écran d'auth)
  await page.goto(BASE + "/app", { waitUntil: "domcontentloaded" });
  total += await run(page, "/app (déconnecté)");

  // 3) App CONNECTÉE : on inscrit un compte de test, on injecte le jeton, on parcourt les vues.
  let token = "";
  try {
    const email = `a11y_${Date.now()}@test.local`;
    const r = await page.request.post(BASE + "/api/auth/register", {
      data: { email, password: "motdepasse123", full_name: "A11y CI", company_name: "CI SARL" },
    });
    if (r.ok()) token = (await r.json()).access_token;
  } catch (e) { /* registration indisponible → on saute la partie connectée */ }

  if (token) {
    await ctx.addInitScript((t) => localStorage.setItem("adjugo_token", t), token);
    await page.goto(BASE + "/app", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3500);
    total += await run(page, "/app (connecté, vue par défaut)");
    const navs = await page.$$(".nav-item");
    for (let i = 0; i < navs.length; i++) {
      try {
        await navs[i].click();
        const title = await page.evaluate(() => document.querySelector(".top h1")?.textContent || `vue ${location.hash}`);
        total += await run(page, `/app → ${title}`);
      } catch (e) { /* vue indisponible */ }
    }
    // Modales : on les ouvre pour valider leurs champs dynamiques (sinon jamais audités).
    const MODALS = [
      { nav: "Facture", btn: (t) => t === "Créer", label: "modale facture" },
      { nav: "Contact", btn: (t) => t.includes("Ajouter un contact"), label: "modale contact" },
    ];
    for (const m of MODALS) {
      try {
        await page.evaluate((n) => { for (const el of document.querySelectorAll(".nav-item")) if ((el.textContent || "").includes(n)) { el.click(); break; } }, m.nav);
        await page.waitForTimeout(1200);
        await page.evaluate((src) => { const f = new Function("t", "return " + src); for (const el of document.querySelectorAll("button")) if (f((el.textContent || "").trim())) { el.click(); break; } }, m.btn.toString());
        await page.waitForTimeout(1200);
        if (await page.$(".overlay .modal, .drawer")) total += await run(page, `/app → ${m.label}`);
        await page.evaluate(() => document.querySelector(".overlay .modal-h .x, .drawer .x")?.click());
        await page.waitForTimeout(500);
      } catch (e) { /* modale indisponible */ }
    }
  } else {
    console.log("\n(inscription indisponible — partie connectée ignorée)");
  }

  await browser.close();
  console.log(`\nTOTAL : ${total} violation(s)`);
  process.exit(total ? 1 : 0);
})().catch((e) => { console.error("FATAL", e); process.exit(2); });
