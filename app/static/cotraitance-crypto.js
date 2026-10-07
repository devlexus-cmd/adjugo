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
    lock: "Chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas. Ni le mandataire, ni Adjugo, ni l'IA ne peuvent le lire.",
    lost: "Si vous perdez votre code de récupération, ce détail est définitivement perdu : nous ne pouvons pas le récupérer.",
    other_device: "Sur un autre ordinateur ou navigateur, vous devrez ressaisir votre code de récupération.",
    not_zero_knowledge: "Le prix de vente de votre lot reste lisible par le mandataire : c'est voulu, il en a besoin pour consolider l'offre.",
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
        .then(() => { b.textContent = "Copié ✓"; }).catch(() => { b.textContent = "Copie impossible — sélectionnez le code"; }); };
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

  window.AdjugoCrypto = {
    ALG, KDF, ITER, LABELS,
    generateRecoveryCode, normalizeCode, derive, newSalt, encrypt, decrypt,
    ensureKey, keyFromCode, resetKey, showRecoveryCode, askRecoveryCode, modal,
    _setStore: (s) => { _store = s; },   // tests
  };
})();
