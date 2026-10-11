/*
 * Adjugo — chiffrement PAR MEMBRE du détail de chiffrage (co-traitance v2, doctrine de visibilité).
 *
 * Ce que ça protège : la DÉCOMPOSITION du prix d'un partenaire (coûts, marges, méthode).
 * Ce que ça ne protège PAS : le prix de vente du lot (prix_lot_ht), que le mandataire doit voir.
 *
 * Mécanique (WebCrypto natif, aucune bibliothèque) :
 *   code de récupération (24 caractères, affiché UNE fois)
 *     → PBKDF2-SHA256 (sel aléatoire 16 o, 600 000 itérations) → 512 bits
 *         → 256 bits = clé AES-256-GCM (importée NON exportable, mise en cache IndexedDB)
 *         → 256 bits → SHA-256 → empreinte de clé (16 hex) stockée dans l'enveloppe
 *   enveloppe envoyée au serveur : {ciphertext, iv, alg, kdf, kdf_salt, kdf_iter, key_fingerprint, updated_at}
 *
 * LIMITES HONNÊTES (à dire tel quel dans l'interface) :
 *   - ce n'est PAS du « zero-knowledge » : Adjugo sert ce script. Formulation retenue :
 *     « chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas » ;
 *   - code perdu = détail définitivement perdu (personne ne peut le récupérer) ;
 *   - autre navigateur / autre poste = ressaisir le code.
 */
(function () {
  "use strict";
  const ALG = "A256GCM", KDF = "PBKDF2-SHA256", ITER = 600000;
  const ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789";   // base32 Crockford sans I/L/O/U/0/1 (lisible)
  const subtle = (typeof crypto !== "undefined" && crypto.subtle) ? crypto.subtle : null;

  const LABELS = {
    lock: "Chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas. Ni le chef de file, ni Adjugo, ni l'IA ne peuvent le lire.",
    lost: "Si vous perdez votre code de récupération, ce détail est définitivement perdu : nous ne pouvons pas le récupérer.",
    other_device: "Sur un autre ordinateur ou navigateur, vous devrez ressaisir votre code de récupération.",
    not_zero_knowledge: "Seul montant visible par le chef de file.",
    // Version courte, visible sous le champ (le texte complet lock + lost va dans l'icône d'aide du libellé).
    lock_short: "Illisible par le chef de file, Adjugo et l'IA. Code perdu = détail perdu.",
  };

  // ── encodage ──
  const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const hex = (buf) => Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  const utf8 = (s) => new TextEncoder().encode(s);
  const unutf8 = (b) => new TextDecoder().decode(b);

  function generateRecoveryCode() {
    const bytes = new Uint8Array(24);
    crypto.getRandomValues(bytes);
    let s = "";
    for (let i = 0; i < 24; i++) s += ALPHABET[bytes[i] % ALPHABET.length];
    return s.match(/.{1,4}/g).join("-");          // XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
  }
  const normalizeCode = (code) => String(code || "").toUpperCase().replace(/[^A-Z2-9]/g, "")
    .replace(/O/g, "0").replace(/[IL]/g, "1");   // tolère les confusions de lecture

  async function derive(code, saltB64, iter) {
    if (!subtle) throw new Error("WebCrypto indisponible dans ce navigateur");
    const base = await subtle.importKey("raw", utf8(normalizeCode(code)), "PBKDF2", false, ["deriveBits"]);
    const bits = await subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: unb64(saltB64), iterations: iter || ITER }, base, 512);
    const keyBytes = bits.slice(0, 32), fpBytes = bits.slice(32, 64);
    const key = await subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
    const fingerprint = hex(await subtle.digest("SHA-256", fpBytes)).slice(0, 16);
    return { key, fingerprint, salt: saltB64, iter: iter || ITER };
  }

  function newSalt() { const s = new Uint8Array(16); crypto.getRandomValues(s); return b64(s); }

  async function encrypt(ctx, plaintext) {
    const iv = new Uint8Array(12); crypto.getRandomValues(iv);
    const ct = await subtle.encrypt({ name: "AES-GCM", iv }, ctx.key, utf8(String(plaintext || "")));
    return { ciphertext: b64(ct), iv: b64(iv), alg: ALG, kdf: KDF, kdf_salt: ctx.salt, kdf_iter: ctx.iter,
             key_fingerprint: ctx.fingerprint, updated_at: new Date().toISOString() };
  }

  async function decrypt(ctx, env) {
    if (!env || !env.ciphertext) return "";
    if (env.key_fingerprint && ctx.fingerprint && env.key_fingerprint !== ctx.fingerprint) {
      const e = new Error("Ce n'est pas la bonne clé pour ce détail (code de récupération différent)."); e.code = "wrong_key"; throw e;
    }
    const pt = await subtle.decrypt({ name: "AES-GCM", iv: unb64(env.iv) }, ctx.key, unb64(env.ciphertext));
    return unutf8(pt);
  }

  // ── cache local de la clé (IndexedDB : une CryptoKey non exportable se clone, jamais ses octets) ──
  const DB = "adjugo-cotraitance", STORE = "keys";
  let _store = null;   // remplaçable (tests)
  function idb() {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === "undefined") return reject(new Error("IndexedDB indisponible"));
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE);
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  async function storeGet(scope) {
    if (_store) return _store.get(scope);
    try { const db = await idb(); return await new Promise((res, rej) => { const t = db.transaction(STORE, "readonly").objectStore(STORE).get(scope); t.onsuccess = () => res(t.result || null); t.onerror = () => rej(t.error); }); }
    catch (e) { return null; }
  }
  async function storePut(scope, value) {
    if (_store) return _store.put(scope, value);
    try { const db = await idb(); await new Promise((res, rej) => { const t = db.transaction(STORE, "readwrite").objectStore(STORE).put(value, scope); t.onsuccess = () => res(); t.onerror = () => rej(t.error); }); } catch (e) {}
  }
  async function storeDel(scope) {
    if (_store) return _store.del(scope);
    try { const db = await idb(); await new Promise((res, rej) => { const t = db.transaction(STORE, "readwrite").objectStore(STORE).delete(scope); t.onsuccess = () => res(); t.onerror = () => rej(t.error); }); } catch (e) {}
  }

  /**
   * Résout la clé pour un espace (scope = jeton d'invitation).
   * - clé en cache et compatible avec l'enveloppe existante → {ctx}
   * - enveloppe existante mais pas de clé (autre poste) → {needCode:true, salt, iter, fingerprint}
   * - rien → nouvelle clé : {ctx, isNew:true, code}  (AFFICHER le code une fois, puis l'oublier)
   */
  async function ensureKey(scope, envelope) {
    const cached = await storeGet(scope);
    if (cached && cached.key) {
      if (!envelope || !envelope.key_fingerprint || envelope.key_fingerprint === cached.fingerprint) return { ctx: cached };
    }
    if (envelope && envelope.ciphertext) {
      return { needCode: true, salt: envelope.kdf_salt, iter: envelope.kdf_iter || ITER, fingerprint: envelope.key_fingerprint || "" };
    }
    const code = generateRecoveryCode();
    const ctx = await derive(code, newSalt(), ITER);
    await storePut(scope, ctx);
    return { ctx, isNew: true, code };
  }

  /** Autre poste : reconstruit la clé depuis le code, vérifie l'empreinte, met en cache. */
  async function keyFromCode(scope, code, envelope) {
    const ctx = await derive(code, envelope.kdf_salt, envelope.kdf_iter || ITER);
    if (envelope.key_fingerprint && envelope.key_fingerprint !== ctx.fingerprint) {
      const e = new Error("Code de récupération incorrect."); e.code = "wrong_code"; throw e;
    }
    await storePut(scope, ctx);
    return ctx;
  }

  /** Repartir de zéro (code perdu) : nouvelle clé, l'ancien détail devient illisible. */
  async function resetKey(scope) {
    await storeDel(scope);
    const code = generateRecoveryCode();
    const ctx = await derive(code, newSalt(), ITER);
    await storePut(scope, ctx);
    return { ctx, code };
  }

  // ── Modales minimales (DOM pur, couleurs Adjugo) — partagées par invite.html et app.js ──
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function modal({ title, bodyHtml, confirmLabel, cancelLabel, withInput, placeholder, requireCheck }) {
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.style.cssText = "position:fixed;inset:0;background:rgba(12,21,38,.58);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px";
      const box = document.createElement("div");
      box.style.cssText = "background:var(--card,#fff);color:var(--text,#0c1526);border-radius:14px;max-width:460px;width:100%;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.3);font-family:inherit";
      box.innerHTML = `<div style="font-size:16px;font-weight:800;margin-bottom:8px">${esc(title)}</div><div style="font-size:13px;line-height:1.55;color:var(--text-2,#4b5563)">${bodyHtml || ""}</div>`;
      let input = null, check = null;
      if (withInput) {
        input = document.createElement("input"); input.className = "inp";
        input.style.cssText = "width:100%;margin-top:12px;font-size:15px;letter-spacing:1.5px;text-transform:uppercase;font-family:ui-monospace,Menlo,monospace";
        input.placeholder = placeholder || "XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"; input.autocomplete = "off"; input.spellcheck = false;
        box.appendChild(input);
      }
      if (requireCheck) {
        const lab = document.createElement("label"); lab.style.cssText = "display:flex;gap:8px;align-items:flex-start;margin-top:12px;font-size:13px;cursor:pointer";
        check = document.createElement("input"); check.type = "checkbox";
        lab.appendChild(check); lab.appendChild(document.createTextNode(requireCheck)); box.appendChild(lab);
      }
      const err = document.createElement("div"); err.style.cssText = "margin-top:8px;min-height:16px;font-size:12.5px;color:#b42318"; box.appendChild(err);
      const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:16px";
      const cancel = document.createElement("button"); cancel.className = "btn"; cancel.textContent = cancelLabel || "Annuler";
      const ok = document.createElement("button"); ok.className = "btn primary"; ok.textContent = confirmLabel || "Continuer";
      bar.appendChild(cancel); bar.appendChild(ok); box.appendChild(bar); ov.appendChild(box); document.body.appendChild(ov);
      const close = (v) => { ov.remove(); resolve(v); };
      cancel.onclick = () => close(null);
      ok.onclick = () => {
        if (check && !check.checked) { err.textContent = "Cochez la case pour confirmer que vous avez noté le code."; return; }
        close(withInput ? { value: (input.value || "").trim() } : true);
      };
      if (input) { input.addEventListener("keydown", (e) => { if (e.key === "Enter") ok.click(); }); setTimeout(() => input.focus(), 40); }
    });
  }

  /** Affiche le code UNE fois ; résout true quand l'utilisateur confirme l'avoir noté. */
  async function showRecoveryCode(code) {
    // Copie dans le presse-papier UNIQUEMENT sur demande explicite (un secret ne doit pas
    // atterrir dans le presse-papier à l'insu de l'utilisateur).
    setTimeout(() => {
      const b = document.getElementById("adj-copy-code");
      if (b) b.onclick = () => { Promise.resolve(navigator.clipboard && navigator.clipboard.writeText(code))
        .then(() => { b.textContent = "Copié"; }).catch(() => { b.textContent = "Copie impossible — sélectionnez le code"; }); };
    }, 60);
    return modal({
      title: "Votre code de récupération",
      bodyHtml: `<p style="margin:0 0 10px">Le détail de votre chiffrage est <b>chiffré dans votre navigateur</b> avec une clé dérivée de ce code. Adjugo ne le stocke pas.</p>
        <div style="font-family:ui-monospace,Menlo,monospace;font-size:17px;letter-spacing:1.5px;padding:12px;border:1.5px dashed var(--accent,#1b4fff);border-radius:10px;text-align:center;background:var(--accent-weak,#eef2ff);user-select:all">${esc(code)}</div>
        <div style="text-align:center;margin-top:8px"><button type="button" id="adj-copy-code" class="btn sm">Copier le code</button></div>
        <p style="margin:10px 0 0;font-size:12.5px">${esc(LABELS.lost)}<br>${esc(LABELS.other_device)}</p>`,
      confirmLabel: "J'ai noté mon code", cancelLabel: "Plus tard",
      requireCheck: "Je l'ai noté dans un endroit sûr (gestionnaire de mots de passe, carnet…).",
    });
  }

  /** Demande le code (autre poste). Résout la chaîne saisie ou null. */
  async function askRecoveryCode(extraHtml) {
    const r = await modal({
      title: "Saisissez votre code de récupération",
      bodyHtml: `<p style="margin:0">Ce détail a été chiffré sur un autre navigateur. Saisissez le code de récupération affiché à ce moment-là.</p>${extraHtml || ""}`,
      withInput: true, confirmLabel: "Déverrouiller", cancelLabel: "Annuler",
    });
    return r && r.value ? r.value : null;
  }

  // ── Contenu du détail chiffré (vague 4) : texte libre + lignes de la DPGF du lot ──
  // Historique : le texte clair chiffré EST le détail (texte libre). Dès que le partenaire saisit
  // les lignes de sa DPGF, le texte clair devient un petit document JSON marqué, chiffré de la
  // même façon (une seule enveloppe, un seul code). Un ancien détail (texte brut) se relit tel quel.
  const DETAIL_TAG = "adjugo-detail-v2";
  const MAX_LIGNES = 300;
  const clip = (v, n) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, n);
  const numOrNull = (v) => (typeof v === "number" && isFinite(v)) ? v : parseNum(v);
  function cleanLine(l) {
    const o = (l && typeof l === "object") ? l : {};
    return { designation: clip(o.designation, 300), unite: clip(o.unite, 20), quantite: numOrNull(o.quantite), pu: numOrNull(o.pu) };
  }
  function packDetail(texte, dpgf) {
    const t = String(texte == null ? "" : texte);
    const lignes = (dpgf && Array.isArray(dpgf.lignes)) ? dpgf.lignes.slice(0, MAX_LIGNES).map(cleanLine) : [];
    if (!lignes.length) return t;
    return JSON.stringify({ format: DETAIL_TAG, texte: t, dpgf: { lignes, maj: (dpgf && dpgf.maj) || new Date().toISOString() } });
  }
  function unpackDetail(plain) {
    const s = String(plain == null ? "" : plain);
    if (s.charAt(0) === "{" && s.indexOf(DETAIL_TAG) > 0) {
      try {
        const o = JSON.parse(s);
        if (o && o.format === DETAIL_TAG) {
          const d = o.dpgf && Array.isArray(o.dpgf.lignes) ? { lignes: o.dpgf.lignes.slice(0, MAX_LIGNES).map(cleanLine), maj: String(o.dpgf.maj || "") } : null;
          return { texte: String(o.texte == null ? "" : o.texte), dpgf: (d && d.lignes.length) ? d : null };
        }
      } catch (e) {}
    }
    return { texte: s, dpgf: null };
  }

  // ── DPGF du lot : fonctions pures (le navigateur produit le fichier, le serveur ne voit que lui) ──
  // Niveau PRIX DE VENTE uniquement : désignation, unité, quantité, prix unitaire HT, montant HT.
  // Aucune colonne de coût, de marge ni de coefficient (le serveur refuse ces en-têtes).
  function parseNum(v) {
    if (v == null) return null;
    let s = String(v).trim().replace(/[\s  ]/g, "").replace(/€$/, "");
    if (!s) return null;
    if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");   // « 1.250,50 » ou « 1250,5 »
    if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
    const n = Number(s);
    return isFinite(n) ? n : null;
  }
  const round2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;
  function montant(l) {
    const q = numOrNull(l && l.quantite), pu = numOrNull(l && l.pu);
    return (q == null || pu == null) ? null : round2(q * pu);
  }
  function total(lignes) {
    let t = 0;
    (lignes || []).forEach((l) => { const m = montant(l); if (m != null) t += m; });
    return round2(t);
  }
  // Nombre pour le fichier : virgule décimale, sans séparateur de milliers (lisible par un tableur).
  function csvNum(n, dec) {
    if (n == null || !isFinite(n)) return "";
    let s = dec == null ? String(Math.round(Number(n) * 1000) / 1000) : Number(n).toFixed(dec);
    return s.replace(".", ",");
  }
  // Aucune cellule ne commence par = + - @ (formule à l'ouverture dans un tableur), QUEL QUE SOIT le
  // séparateur qu'appliquera le tableur : le serveur découpe chaque ligne avec « ; », « , » et la
  // tabulation. D'où : le début du texte, et ce qui suit chaque virgule (espaces et guillemets compris).
  // Caractères de contrôle et sauts de ligne Unicode → espace (le serveur les traite comme des blancs).
  const OPS = /[=+\-@]/g;
  const csvText = (v) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f\u0085\u2028\u2029]+/g, " ")
    .replace(/,[\s\u0085"=+\-@]+/g, (m) => m.replace(OPS, ""))
    .replace(/^[\s\u0085=+\-@]+/, "").trim();
  const csvCell = (v) => { const s = String(v == null ? "" : v); return /[;"\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  // Mots refusés par le serveur dans les lignes d'en-tête d'une DPGF : MÊME liste et MÊME
  // normalisation (invites._DPGF_FORBIDDEN / _dpgf_norm) : sans accents, minuscules, tout ce qui
  // n'est ni lettre ni chiffre devient une espace (« Marge_HT », « coût-unitaire » sont reconnus).
  // Un coût ou une marge ne doit jamais partir par erreur vers le chef de file.
  const FORBIDDEN = /(^| )(marges?|couts?|debourses?|prix d achat|prix achat|pu achat|prix de revient|frais generaux|coefficients?|coef|taux de marque)( |$)/;
  const normWords = (s) => String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  // Libellé lisible du mot reconnu (le motif travaille sans accents).
  const WORD_LABEL = { cout: "coût", couts: "coûts", debourse: "déboursé", debourses: "déboursés",
    "prix d achat": "prix d'achat", "frais generaux": "frais généraux" };
  function forbiddenWord(s) { const m = FORBIDDEN.exec(normWords(s)); return m ? (WORD_LABEL[m[2]] || m[2]) : ""; }
  function lineErrors(lignes) {
    const out = [];
    (lignes || []).forEach((l, i) => {
      const n = i + 1;
      if (!csvText(l.designation)) out.push("Ligne " + n + " : désignation manquante.");
      if (numOrNull(l.quantite) == null || numOrNull(l.quantite) < 0) out.push("Ligne " + n + " : quantité manquante ou invalide.");
      if (numOrNull(l.pu) == null) out.push("Ligne " + n + " : prix unitaire manquant ou invalide.");
    });
    return out;
  }
  /** Lignes du fichier (tableau de tableaux), exactement ce qui sera partagé. */
  function dpgfRows(opts) {
    const o = opts || {}, lignes = (o.lignes || []).map(cleanLine);
    const rows = [["DPGF du lot - prix de vente HT"]];
    if (csvText(o.entreprise)) rows.push(["Entreprise", csvText(o.entreprise)]);
    if (csvText(o.lot)) rows.push(["Lot", csvText(o.lot)]);
    rows.push(["N°", "Désignation", "Unité", "Quantité", "Prix unitaire HT (€)", "Montant HT (€)"]);
    lignes.forEach((l, i) => rows.push([String(i + 1), csvText(l.designation), csvText(l.unite), csvNum(l.quantite), csvNum(l.pu, 2), csvNum(montant(l), 2)]));
    rows.push(["", "Total HT", "", "", "", csvNum(total(lignes), 2)]);
    return rows;
  }
  /** En-têtes refusés (mot de coût ou de marge dans le nom d'entreprise ou du lot) : message, sinon "". */
  function headerProblem(opts) {
    const o = opts || {};
    for (const [lab, v] of [["Le nom de l'entreprise", o.entreprise], ["Le nom du lot", o.lot]]) {
      const w = forbiddenWord(csvText(v));
      if (w) return lab + " (« " + csvText(v).slice(0, 80) + " ») contient le mot « " + w + " » : une DPGF de lot ne doit faire apparaître ni coût ni marge, ce mot est donc refusé en en-tête. Modifiez ce nom dans votre part.";
    }
    return "";
  }
  /** Fichier CSV UTF-8 (BOM), séparateur « ; », montants « 1250,00 », sans formule. */
  function dpgfCsv(opts) { return "﻿" + dpgfRows(opts).map((r) => r.map(csvCell).join(";")).join("\r\n") + "\r\n"; }
  function dpgfFileName(opts) {
    const o = opts || {};
    const base = String(csvText(o.lot) || csvText(o.entreprise) || "lot").normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50) || "lot";
    return "DPGF_" + base + ".csv";
  }

  window.AdjugoCrypto = {
    ALG, KDF, ITER, LABELS,
    generateRecoveryCode, normalizeCode, derive, newSalt, encrypt, decrypt,
    ensureKey, keyFromCode, resetKey, showRecoveryCode, askRecoveryCode, modal,
    packDetail, unpackDetail,
    dpgf: { MAX_LIGNES, parseNum, montant, total, lineErrors, rows: dpgfRows, csv: dpgfCsv, fileName: dpgfFileName, headerProblem, forbiddenWord },
    _setStore: (s) => { _store = s; },   // tests
  };
})();
