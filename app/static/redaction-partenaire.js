/*
 * Rédaction, vague 4 — l'écran du PARTENAIRE : il rédige SES parties du dossier de présentation commun,
 * chez lui (étude « rédaction » § 6.8 B, parcours point 2 ; contrat docs/REDACTION_V4_GROUPEMENT.md § 5).
 *
 * Un seul écran pour les deux accès :
 *   • le lien de son invitation (app/static/invite.html) : /api/invite/{token}/redaction…, avec la clé de
 *     son espace privé gardée dans CE navigateur et envoyée dans l'en-tête X-Adjugo-Espace (jamais dans une
 *     adresse) ;
 *   • son compte Adjugo (« Partagé avec moi », app/static/app.html) : /api/shared/{projet}/redaction…
 *     (le compte suffit, aucune clé).
 *
 * Règles tenues ici (le serveur les impose aussi) :
 *   • tout texte affiché passe par rpEsc / rpTexte (échappé, jamais interprété comme du HTML) ; les renvois
 *     [F3], [S2]… sont montrés comme « votre source », « source du partenaire » ou « source du chef de
 *     file », sans lien ;
 *   • c'est LUI qui lance l'aide de l'IA (« Rédiger avec Adjugo ») ; un refus est affiché tel que le serveur
 *     l'écrit (message neutre : rien du forfait du chef de file) et « J'écris moi-même » reste toujours
 *     possible ;
 *   • avant l'envoi, il lit « Ce texte sera lu par le chef de file et par les autres membres du
 *     groupement. » ; ses sources, ses extraits et ses brouillons restent privés ;
 *   • aucun temps réel : on relit l'écran après chaque action ; seule SA tâche de rédaction est suivie
 *     (toutes les 2 secondes, comme l'atelier).
 * Interface : français, zéro émoji, explications dans une bulle (i), compact, lisible à 375 px.
 */
(function (root) {
  "use strict";

  // ── Fonctions pures (testées sous Node : tests/test_redaction_v4_partenaire.py) ─────────────────────

  function rpEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Nombre de mots (approché, comme le serveur et l'atelier) d'un texte, sans renvois ni syntaxe.
  function rpMots(md) {
    const t = String(md || "").replace(/\[\s*[FSPECG]\s*\d{1,4}(?:\s*[,;]\s*[FSPECG]?\s*\d{1,4})*\s*\]/g, " ")
      .replace(/\[\s*CV\s+F\s*\d{1,4}\s*\]/gi, " ").replace(/^\s*(#{1,6}|[-*+•]|\d{1,2}[.)])\s+/gm, " ").replace(/[|*_`]/g, " ");
    const m = t.match(/[0-9A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:['’-][0-9A-Za-zÀ-ÖØ-öø-ÿŒœ]+)*/g);
    return m ? m.length : 0;
  }

  const RE_TODO = /\[\s*[ÀàAa]\s+[Cc][Oo][Mm][Pp][Ll][ÉéEe][Tt][Ee][Rr][^\]]*\]/g;
  const RE_REF = /\[\s*([FSPECG]\s*\d{1,4}(?:\s*[,;]\s*[FSPECG]?\s*\d{1,4})*)\s*\]/g;

  // Nombre de « [À compléter …] » d'un texte (même repérage que le serveur, quelle que soit la casse).
  function rpACompleter(t) { return (String(t || "").match(RE_TODO) || []).length; }

  // Rendu SÛR d'un texte (Markdown simple) : tout est échappé d'abord ; puis gras, « [À compléter] »,
  // renvois (libellé `refLib` en infobulle, sans lien), titres, listes, tableaux et paragraphes.
  function rpTexte(md, refLib) {
    const inl = (t) => {
      let h = rpEsc(t);
      h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      h = h.replace(RE_TODO, m => '<span class="rp-todo">' + m + "</span>");
      h = h.replace(RE_REF, (m, g) => '<span class="rp-ref" title="' + rpEsc(refLib || "source") + '">' + g.replace(/\s+/g, "") + "</span>");
      return h;
    };
    const lines = String(md || "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let para = [], li = [], rows = [];
    const flush = () => {
      if (para.length) { out.push("<p>" + para.join("<br>") + "</p>"); para = []; }
      if (li.length) { out.push("<ul>" + li.map(x => "<li>" + x + "</li>").join("") + "</ul>"); li = []; }
      if (rows.length) {
        out.push('<table class="rp-table"><tbody>' + rows.map(r => "<tr>" + r.map(c => "<td>" + inl(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
        rows = [];
      }
    };
    for (const raw of lines) {
      const ln = raw.replace(/\s+$/, "");
      let m;
      if (!ln.trim()) { flush(); continue; }
      if (/^\s*\|/.test(ln)) {
        if (para.length || li.length) { const keep = rows; rows = []; flush(); rows = keep; }
        if (/^\s*\|?\s*:?-{3,}/.test(ln)) continue;                       // ligne de séparation
        rows.push(ln.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim()));
        continue;
      }
      if (rows.length) flush();
      if ((m = /^\s*#{1,6}\s+(.*)$/.exec(ln))) { flush(); out.push('<div class="rp-h">' + inl(m[1]) + "</div>"); continue; }
      if ((m = /^\s*[-*•]\s+(.*)$/.exec(ln))) { if (para.length) { const keep = li; li = []; flush(); li = keep; } li.push(inl(m[1])); continue; }
      if (li.length) flush();
      para.push(inl(ln));
    }
    flush();
    return out.join("");
  }

  // La phrase d'un fait à relire, le fait surligné (première occurrence, sans tenir compte de la casse).
  function rpPhrase(phrase, fait) {
    const p = String(phrase || ""), f = String(fait || "").trim();
    const i = f ? p.toLowerCase().indexOf(f.toLowerCase()) : -1;
    if (i < 0) return rpEsc(p);
    return rpEsc(p.slice(0, i)) + '<mark class="rp-mark">' + rpEsc(p.slice(i, i + f.length)) + "</mark>" + rpEsc(p.slice(i + f.length));
  }

  // L'avant et l'après d'une modification, mot à mot (plus longue sous-suite commune, sans IA) : ce qui a
  // été retiré est surligné dans l'avant, ce qui a été ajouté dans l'après. Textes échappés, espaces gardés.
  // Trop long pour être comparé à la volée : les deux textes, sans surlignage (ok = false).
  function rpDiff(a, b) {
    const ta = String(a || "").match(/\s+|[^\s]+/g) || [], tb = String(b || "").match(/\s+|[^\s]+/g) || [];
    const n = ta.length, m = tb.length;
    if (!n || !m || n * m > 4000000) return { avant: rpEsc(a), apres: rpEsc(b), ok: false };
    const L = new Array(n + 1);
    for (let i = 0; i <= n; i++) L[i] = new Uint16Array(m + 1);
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = ta[i] === tb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const vide = (arr, cls) => {
      if (!arr.length) return "";
      const t = arr.join(""); arr.length = 0;
      return /^\s*$/.test(t) ? rpEsc(t) : '<mark class="' + cls + '">' + rpEsc(t) + "</mark>";
    };
    let i = 0, j = 0, ha = "", hb = "";
    const da = [], db = [];
    while (i < n && j < m) {
      if (ta[i] === tb[j]) { ha += vide(da, "rp-del") + rpEsc(ta[i]); hb += vide(db, "rp-ins") + rpEsc(tb[j]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) da.push(ta[i++]);
      else db.push(tb[j++]);
    }
    while (i < n) da.push(ta[i++]);
    while (j < m) db.push(tb[j++]);
    return { avant: ha + vide(da, "rp-del"), apres: hb + vide(db, "rp-ins"), ok: true };
  }

  // « 20 pages au maximum », « 1 page au maximum par référence » (comme « Comment vous serez noté »).
  const LIM_OBJET = { cv: "par CV", reference: "par référence", question: "pour une question", question_chaque: "par question",
    fiche: "par fiche", synthese: "pour la synthèse", lettre: "pour la lettre", annexe: "par annexe" };
  function rpLim(x) {
    if (!x) return "";
    if (x.type === "police") { const s = [x.police, x.taille != null ? x.taille : ""].filter(v => v !== "" && v != null).join(" "); return "Police : " + (s || x.texte || ""); }
    const un = Number(x.valeur) === 1;
    const u = ({ pages: un ? "page" : "pages", mots: un ? "mot" : "mots", caracteres: un ? "caractère" : "caractères", lignes: un ? "ligne" : "lignes" })[x.type] || x.type || "";
    const o = x.objet ? " " + (LIM_OBJET[x.objet] || "") : "";
    return ((x.valeur != null ? Number(x.valeur).toLocaleString("fr-FR") + " " + u : (x.texte || "")) + " au maximum" + o).trim();
  }

  // Ce que le chef de file reçoit avec le texte : des compteurs PAR TYPE de source (jamais les sources).
  const TYPES_LIB = { documents: "trouvés dans vos documents", declare: "déclarés par vous", public: "de source publique",
    estimation: "tirés de votre estimation", calcul: "calculés à partir de vos faits", acheteur: "dans le dossier de l'acheteur" };
  function rpCompteurs(c) {
    const p = (c && c.par_type) || {};
    return Object.keys(TYPES_LIB).filter(k => Number(p[k]) > 0).map(k => Number(p[k]) + " " + TYPES_LIB[k]);
  }

  // Date « AAAA-MM-JJ » ou horodatage de l'API (UTC « naïf ») → « 2 novembre 2026 ».
  function rpJour(s) {
    if (!s) return "";
    const d = /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(s + "T12:00:00") : new Date(/T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s + "Z" : s);
    if (isNaN(d.getTime())) return String(s);
    try { return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }); } catch (e) { return String(s); }
  }

  const FAIT_TYPES = { chiffre: "Chiffre", nombre_en_lettres: "Nombre en lettres", certification: "Certification",
    nom_propre: "Nom propre", materiel: "Matériel", engagement: "Engagement" };
  const PILL = { a_rediger: "neutral", en_cours: "a_etudier", envoyee: "st-envoye", a_revalider: "a_etudier", validee: "go" };

  // ── Petits gabarits ─────────────────────────────────────────────────────────────────────────────

  // Bulle (i) : `html` est DÉJÀ échappé. left : la bulle s'ouvre vers la gauche.
  const tip = (html, left) => html ? '<button type="button" class="tip' + (left ? " tip-l" : "") + '"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">' + html + "</span></button>" : "";
  const ico = (name, px) => '<i data-lucide="' + rpEsc(name) + '" style="width:' + (px || 14) + "px;height:" + (px || 14) + 'px;flex:none"></i>';
  const btn = (act, label, cls, extra) => '<button type="button" class="btn sm' + (cls ? " " + cls : "") + '" data-act="' + act + '"' + (extra || "") + ">" + label + "</button>";

  const BULLE_CARTE = "Le chef de file vous a confié ces parties du dossier de présentation commun (le mémoire technique du groupement). Vous les rédigez ici, chez vous : vos brouillons, vos sources et vos extraits restent privés. Le chef de file et les autres membres lisent le texte que vous envoyez.";
  const BULLE_NOTE = "Le critère et son poids sont repris du règlement de la consultation, avec la phrase où Adjugo les a trouvés. Un poids n'est affiché que s'il est écrit tel quel, ou s'il a été lu par le chef de file (c'est alors indiqué). Le règlement fait foi.";
  const BULLE_FAITS = "Adjugo signale les chiffres, certifications, noms et matériels qu'il ne retrouve pas dans ce que vous avez déclaré (et, avec un compte Adjugo, dans vos preuves, votre profil et votre savoir-faire), et les engagements à confirmer. Le dossier de l'acheteur ne compte jamais comme source pour une phrase sur votre entreprise. Il ne juge pas les phrases générales : relisez-les.";
  const BULLE_ENVOI = "Le chef de file reçoit le texte envoyé, le nombre de faits encore à relire et des compteurs de sources par type. Jamais vos sources, vos extraits ni vos brouillons.";
  const BULLE_VALIDER = "Valider dit que ce texte est votre version définitive. S'il change ensuite, par vous ou par le chef de file, la partie repasse « à revalider ».";
  const BULLE_DOSSIER = "Le dossier assemblé réunit, dans l'ordre du cadre de l'acheteur, le texte envoyé par chaque membre et le texte validé du chef de file. Il est en lecture seule. Le valider dit que vous l'avez lu : toute modification ensuite le fait repasser « à revalider ».";
  const BULLE_ESPACE = "Vos brouillons, vos sources et l'aide d'Adjugo restent dans un espace privé, lié à ce navigateur : même la personne qui vous a transmis ce lien ne peut pas les lire. Avec un compte Adjugo, rien à ouvrir : retrouvez ce dossier dans « Partagé avec moi ».";
  const BULLE_EXTRAITS = "Les passages de vos documents qu'Adjugo a cités en rédigeant (S1, S2…). Ils restent privés : ni le chef de file ni l'acheteur ne les voient, et les renvois sont retirés à l'export. Un extrait cité ne prouve pas que la phrase est exacte.";

  function errMessage(data, status) {
    const d = data && data.detail;
    if (d && typeof d === "object" && !Array.isArray(d) && d.message) return String(d.message);
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) return "Saisie invalide.";
    if (status === 429) return "Trop de demandes rapprochées : réessayez dans quelques minutes.";
    return status >= 500 ? "Erreur du serveur : réessayez dans un instant." : "Action impossible pour le moment.";
  }

  // ── Fenêtre de confirmation (aux couleurs d'Adjugo, sans dialogue système) ─────────────────────────

  function modal(o) {
    return new Promise(resolve => {
      const ov = document.createElement("div");
      ov.className = "rp-ov";
      const uid = "rpm" + Math.random().toString(36).slice(2, 9);
      ov.innerHTML = '<div class="rp-modal" role="dialog" aria-modal="true" aria-labelledby="' + uid + '"><div class="rp-modal-t" id="' + uid + '">' + rpEsc(o.title || "") + '</div><div class="rp-modal-b small">' + (o.bodyHtml || "") + "</div>"
        + (o.withInput ? '<label class="small rp-modal-l" for="' + uid + 'i">' + rpEsc(o.inputLabel || "") + '</label><input id="' + uid + 'i" class="inp rp-code" inputmode="numeric" autocomplete="one-time-code" maxlength="6">' : "")
        + '<div class="small rp-modal-n" role="status">' + (o.noteHtml || "") + '</div><div class="rp-modal-a"><button type="button" class="btn sm" data-r="0">' + rpEsc(o.cancelLabel || "Annuler") + '</button><button type="button" class="btn sm ' + (o.danger ? "danger" : "primary") + '" data-r="1">' + rpEsc(o.confirmLabel || "Confirmer") + "</button></div></div>";
      document.body.appendChild(ov);
      const input = ov.querySelector("input");
      const prev = document.activeElement;
      const close = (v) => { ov.remove(); try { if (prev && prev.focus) prev.focus({ preventScroll: true }); } catch (e) {} resolve(v); };
      ov.addEventListener("click", e => {
        const b = e.target.closest && e.target.closest("[data-r]");
        if (e.target === ov) close(null);
        else if (b) close(b.dataset.r === "1" ? (input ? { value: (input.value || "").trim() } : true) : null);
      });
      ov.addEventListener("keydown", e => { if (e.key === "Escape") { e.preventDefault(); close(null); } if (e.key === "Enter" && input && e.target === input) close({ value: (input.value || "").trim() }); });
      setTimeout(() => (input || ov.querySelector(o.focusCancel ? '[data-r="0"]' : '[data-r="1"]')).focus(), 30);
      try { root.lucide && root.lucide.createIcons(); } catch (e) {}
    });
  }

  // ── Montage ─────────────────────────────────────────────────────────────────────────────────────

  /**
   * mount(el, opts) — opts :
   *   base        "/api/invite/<token>/redaction" ou "/api/shared/<projet>/redaction"
   *   mode        "lien" | "compte"
   *   headers     () => en-têtes d'authentification (compte : Bearer)
   *   cleStockage nom de la clé du navigateur où garder la clé de l'espace (lien)
   *   invite      "/api/invite/<token>" (lien : demande d'un code par email)
   *   verifyIdentity(msgEl, {purpose}) → Promise<bool> (lien : code reçu par email)
   *   onChange()  appelé après une action (ex. relire « Mon journal »)
   *   onEtat(vue) appelé à chaque lecture (ex. pastille de la liste)
   */
  function mount(el, opts) {
    const o = Object.assign({ mode: "lien", headers: () => ({}) }, opts || {});
    const st = { vue: null, open: null, edits: {}, moi: {}, msgs: {}, busy: "", jobs: {}, timer: null, dossier: null,
      dossierOpen: false, msgDossier: null, hist: {}, err: "", gone: false, destroyed: false };
    const ENTETE = "X-Adjugo-Espace";
    const KEY_ED = "rp_ed_" + (o.cleStockage || o.base);

    const cle = () => { if (o.mode !== "lien" || !o.cleStockage) return ""; try { return localStorage.getItem(o.cleStockage) || ""; } catch (e) { return ""; } };
    const garderCle = (k) => { try { localStorage.setItem(o.cleStockage, k); } catch (e) {} };
    const brouillonsLocaux = () => { try { return JSON.parse(sessionStorage.getItem(KEY_ED) || "{}") || {}; } catch (e) { return {}; } };
    const garderLocaux = () => { try { sessionStorage.setItem(KEY_ED, JSON.stringify(st.edits)); } catch (e) {} };
    st.edits = brouillonsLocaux();

    async function call(method, path, body, raw) {
      const h = Object.assign({}, o.headers ? o.headers() : {});
      const k = cle(); if (k) h[ENTETE] = k;
      if (body !== undefined) h["Content-Type"] = "application/json";
      let r;
      try { r = await fetch(o.base + path, { method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined, cache: "no-store" }); }
      catch (e) { return { ok: false, status: 0, data: null, code: "", message: "Connexion impossible : vérifiez votre réseau, puis réessayez." }; }
      if (raw) return { ok: r.ok, status: r.status, res: r };
      let data = null; try { data = await r.json(); } catch (e) {}
      const d = data && data.detail;
      return { ok: r.ok, status: r.status, data, code: (d && typeof d === "object" && d.code) || "", message: r.ok ? "" : errMessage(data, r.status) };
    }

    const partie = (sid) => ((st.vue && st.vue.parties) || []).find(p => p.section_id === sid) || null;
    const say = (sid, txt, err) => { st.msgs[sid] = txt ? { txt, err: !!err } : null; };
    const changed = () => { try { o.onChange && o.onChange(); } catch (e) {} };

    async function load() {
      const r = await call("GET", "");
      if (st.destroyed) return;
      if (!r.ok) {
        // Pas de dossier commun (pas encore préparé, sous-traitant), aperçu limité, lien coupé : rien à montrer.
        st.vue = null; st.gone = [403, 404, 410].includes(r.status) && r.code !== "cle_espace_requise";
        st.err = st.gone ? "" : r.message;
        render();
        return;
      }
      st.vue = r.data; st.gone = false; st.err = "";
      (st.vue.parties || []).forEach(p => {
        const ec = p.aide && p.aide.en_cours;
        if (ec && ec.job_id) st.jobs[p.section_id] = ec.job_id;
        // Un texte local plus ancien que le brouillon enregistré est oublié (le brouillon a changé ailleurs).
        const loc = st.edits[p.section_id];
        if (loc && p.brouillon && loc.base !== p.brouillon.id) { delete st.edits[p.section_id]; }
        if (loc && p.brouillon && loc.texte === p.brouillon.texte) delete st.edits[p.section_id];
      });
      garderLocaux();
      if (st.open == null) {
        const next = (st.vue.parties || []).find(p => ["a_rediger", "en_cours", "a_revalider"].includes(p.statut));
        st.open = next ? next.section_id : null;
      }
      try { o.onEtat && o.onEtat(st.vue); } catch (e) {}
      render();
      poll();
    }

    function poll() {
      if (st.timer || !Object.keys(st.jobs).length) return;
      st.timer = setInterval(async () => {
        const ids = Object.keys(st.jobs);
        if (!ids.length || st.destroyed) { clearInterval(st.timer); st.timer = null; return; }
        let fini = false;
        for (const sid of ids) {
          const r = await call("GET", "/taches/" + encodeURIComponent(st.jobs[sid]));
          if (!r.ok) { delete st.jobs[sid]; fini = true; continue; }
          const j = r.data || {};
          if (j.status === "done" || j.status === "error") {
            delete st.jobs[sid]; fini = true;
            const res = (j.result && j.result.sections && j.result.sections[0]) || null;
            if (j.status === "error") say(Number(sid), j.error || "La rédaction n'a pas abouti : réessayez dans quelques minutes, ou écrivez votre partie vous-même.", true);
            else if (res && res.ok) { delete st.edits[sid]; say(Number(sid), "Texte rédigé : relisez-le, complétez les « [À compléter] », puis envoyez-le."); }
            else say(Number(sid), (j.result && j.result.message) || "Le texte n'a pas été gardé.", true);
          }
        }
        if (fini) { garderLocaux(); await load(); changed(); }
      }, 2000);
    }

    // ── Rendu ────────────────────────────────────────────────────────────────────────────────────
    function render() {
      if (st.destroyed) return;
      const v = st.vue;
      if (!v) {
        el.innerHTML = st.err ? '<section class="card pad rp-card"><div class="conv-err" role="alert">' + ico("circle-alert", 15) + "<div>" + rpEsc(st.err) + ' <button type="button" class="linkbtn" data-act="recharger">Réessayer</button></div></div></section>' : "";
        icons(); return;
      }
      const parts = v.parties || [];
      const cleOk = !!(v.espace && v.espace.cle_valide);
      const ecrire = !!v.peut_ecrire && cleOk;
      const aFaire = parts.filter(p => ["a_rediger", "en_cours", "a_revalider"].includes(p.statut)).length;
      const pret = (v.dossier && v.dossier.pret) || null;
      let h = '<section class="card pad rp-card" aria-labelledby="rp-titre">';
      h += '<div class="rp-head"><div class="rp-head-t"><h2 class="rp-title" id="rp-titre">Mes parties du dossier de présentation</h2>' + tip(rpEsc(BULLE_CARTE)) + "</div>"
        + (aFaire ? '<span class="pill a_etudier rp-pill">' + aFaire + " à faire</span>" : (parts.length ? '<span class="pill go rp-pill">À jour</span>' : "")) + "</div>";
      h += '<div class="muted small rp-sub">' + (parts.length ? parts.length + (parts.length > 1 ? " parties confiées" : " partie confiée") + (v.membre && v.membre.nom ? " à " + rpEsc(v.membre.nom) : "") : "Aucune partie ne vous est confiée pour le moment.")
        + (pret && pret.sections_total ? " · " + rpEsc(pret.message) : "") + "</div>";
      if (o.mode === "lien" && !cleOk) h += renderEspace(v);
      else if (!v.peut_ecrire) h += '<div class="rp-info small">' + ico("lock", 14) + "<span>La co-construction n'est pas ouverte sur ce lien : vous lisez vos parties sans pouvoir les modifier.</span></div>";
      if (parts.length) {
        h += '<ul class="rp-parts">';
        parts.forEach(p => { h += renderPartie(v, p, ecrire); });
        h += "</ul>";
      }
      h += renderDossier(v, ecrire);
      const simple = v.mode_simple && v.mode_simple.petit_texte;
      if (simple) {
        h += '<details class="gn-det rp-simple"><summary>Mode simple : votre paragraphe</summary><p class="muted small rp-p">' + rpEsc(v.mode_simple.message) + '</p><div class="rp-txt rp-txt-s">' + rpTexte(simple, "votre source") + "</div></details>";
      }
      if (cleOk) h += '<div class="rp-export"><button type="button" class="linkbtn small" data-act="export">Télécharger mes textes</button>' + tip("Vos brouillons et les textes que vous avez envoyés, dans un fichier (droit à la portabilité).", true) + "</div>";
      h += '<div class="sr-only" aria-live="polite" data-live></div></section>';
      // L'écran est redessiné après chaque action : les volets ouverts et le focus (clavier, lecteur d'écran)
      // sont gardés.
      const ouverts = new Set(Array.from(el.querySelectorAll("details[open]")).map(cleVolet));
      const garde = focusGarde();
      el.innerHTML = h;
      el.querySelectorAll("details").forEach(d => { if (ouverts.has(cleVolet(d))) d.open = true; });
      focusRendu(garde);
      icons();
    }

    function cleVolet(d) {
      const li = d.closest(".rp-part"), s = d.querySelector("summary");
      return (li ? li.dataset.sid || "" : "") + "|" + (s ? s.textContent.replace(/\(\d+\)/g, "").trim() : "");
    }

    function focusGarde() {
      const a = document.activeElement;
      if (!a || !el.contains(a) || !a.dataset) return null;
      return { act: a.dataset.act || "", sid: a.dataset.sid || "", fid: a.dataset.fid || "", ta: a.matches && a.matches("textarea.rp-ta"),
        s: a.selectionStart, e: a.selectionEnd };
    }

    function focusRendu(g) {
      if (!g) return;
      const q = (v) => (window.CSS && CSS.escape) ? CSS.escape(v) : String(v).replace(/["\\]/g, "");
      let n = null;
      if (g.ta && g.sid) n = el.querySelector('textarea.rp-ta[data-sid="' + q(g.sid) + '"]');
      else if (g.act) n = el.querySelector('[data-act="' + q(g.act) + '"]' + (g.sid ? '[data-sid="' + q(g.sid) + '"]' : "") + (g.fid ? '[data-fid="' + q(g.fid) + '"]' : ""));
      if (!n && g.sid) n = el.querySelector('[data-act="ouvrir"][data-sid="' + q(g.sid) + '"]');
      if (!n) return;
      try { n.focus({ preventScroll: true }); if (g.ta && typeof g.s === "number") n.setSelectionRange(g.s, g.e); } catch (e) {}
    }

    function icons() { try { root.lucide && root.lucide.createIcons(); } catch (e) {} }

    function renderEspace(v) {
      const e = v.espace || {};
      let h = '<div class="rp-esp"><div class="rp-esp-t">' + ico("key-round", 15) + "<b>Votre espace privé de rédaction</b>" + tip(rpEsc(BULLE_ESPACE)) + "</div>";
      if (!e.ouvert) {
        h += '<p class="small rp-p">Ouvrez-le sur cet appareil pour rédiger vos parties.</p><div class="rp-acts">' + btn("espace-ouvrir", ico("lock-open", 14) + "Ouvrir mon espace", "primary") + "</div>";
      } else {
        h += '<p class="small rp-p">Votre espace est déjà ouvert sur un autre appareil ou un autre navigateur.'
          + (e.code_possible ? " Recevez un code par email pour l'ouvrir ici : vos brouillons sont gardés." : " Vous pouvez le réinitialiser ici : vos brouillons non envoyés seront effacés, vos textes envoyés restent.") + "</p><div class=\"rp-acts\">"
          + (e.code_possible ? btn("espace-code", ico("mail", 14) + "Recevoir un code", "primary") : "")
          + btn("espace-reinit", "Réinitialiser mon espace", e.code_possible ? "ghost" : "") + "</div>";
      }
      return h + "</div>";
    }

    function renderNote(p) {
      const n = p.note || {};
      let h = '<div class="rp-note"><div class="rp-lbl">Ce que l\'acheteur note' + tip(rpEsc(BULLE_NOTE)) + "</div>";
      if (n.critere) h += '<div class="rp-crit"><span class="rp-crit-n">' + rpEsc(n.critere) + "</span>" + (n.poids ? '<span class="gn-poids num">' + rpEsc(n.poids) + "</span>" : "")
        + (n.poids && n.poids_libelle ? '<span class="muted small">' + rpEsc(n.poids_libelle) + "</span>" : "") + "</div>";
      if (n.phrase) h += '<blockquote class="gn-q">' + rpEsc(n.phrase) + "</blockquote>";
      if (n.question) h += '<div class="small rp-q"><span class="muted">Question du cadre de réponse :</span> ' + rpEsc(n.question) + "</div>";
      const g = !n.critere ? (n.grille || []) : [];
      if (g.length) {
        h += '<div class="small muted rp-q">Le mémoire technique est jugé sur ' + (g.length > 1 ? "ces critères" : "ce critère") + " du règlement :</div>"
          + '<ul class="gn-list">' + g.map(x => '<li class="gn-row"><span class="gn-crit">' + rpEsc(x.critere) + "</span>" + (x.poids ? '<span class="gn-poids num">' + rpEsc(x.poids) + "</span>" : "")
          + (x.poids && x.poids_libelle ? '<span class="muted small">' + rpEsc(x.poids_libelle) + "</span>" : "") + "</li>").join("") + "</ul>";
        const ph = g.filter(x => x.phrase);
        if (ph.length) h += '<details class="gn-det"><summary>Voir les phrases du règlement</summary>' + ph.map(x => '<div class="gn-src"><div class="gn-src-t">' + rpEsc(x.critere) + '</div><blockquote class="gn-q">' + rpEsc(x.phrase) + "</blockquote></div>").join("") + "</details>";
      }
      if (!n.critere && !n.phrase && !n.question && !g.length) h += '<div class="muted small">Le dossier de l\'acheteur ne rattache aucun critère à cette partie.</div>';
      const lim = (p.limite || []).filter(x => x && x.type);
      if (lim.length) h += '<ul class="gn-chips">' + lim.map(x => "<li>" + rpEsc(rpLim(x)) + "</li>").join("") + "</ul>";
      return h + "</div>";
    }

    function renderPartie(v, p, ecrire) {
      const sid = p.section_id, open = st.open === sid;
      const meta = [p.longueur_mots ? "environ " + Number(p.longueur_mots).toLocaleString("fr-FR") + " mots" : "", p.date_limite ? "avant le " + rpJour(p.date_limite) : ""].filter(Boolean).join(" · ");
      let h = '<li class="rp-part' + (open ? " open" : "") + '" data-sid="' + sid + '">';
      h += '<button type="button" class="rp-ph" data-act="ouvrir" data-sid="' + sid + '" aria-expanded="' + (open ? "true" : "false") + '"><span class="rp-chev">' + ico("chevron-right", 15) + '</span><span class="rp-pt"><span class="rp-pn">' + rpEsc(p.titre || p.intitule) + "</span>"
        + (meta ? '<span class="rp-pm muted small">' + rpEsc(meta) + "</span>" : "") + '</span><span class="pill ' + (PILL[p.statut] || "neutral") + ' rp-pill">' + rpEsc(p.statut_libelle) + "</span></button>";
      if (!open) return h + "</li>";
      h += '<div class="rp-pb">';
      if (p.mention) h += '<div class="muted small rp-mention">' + rpEsc(p.mention) + "</div>";
      h += renderNote(p);
      const cur = p.texte_commun, cmp = p.comparaison;
      const job = st.jobs[sid];
      const parChef = p.statut === "a_revalider" && cur && cur.ecrit_par === "chef_de_file";
      if (parChef) h += renderComparaison(p, cmp, ecrire);
      else h += renderCommun(v, p, ecrire);
      if (job) h += '<div class="rp-job" role="status"><span class="spin"></span><span>Adjugo rédige votre partie (une à deux minutes). Vous pouvez quitter cette page : le texte vous attendra.</span></div>';
      else if (ecrire && editeurVisible(p)) h += renderEditeur(v, p);
      else if (ecrire) h += '<div class="rp-acts rp-mt">' + btn("moi", ico("pencil", 14) + (parChef ? "Écrire une autre version" : "Modifier mon texte"), "", ' data-sid="' + sid + '"') + "</div>";
      else if (p.brouillon && p.brouillon.texte) h += '<div class="rp-ed"><div class="rp-lbl">Votre brouillon</div><div class="rp-txt">' + rpTexte(p.brouillon.texte, "votre source") + "</div></div>";
      const m = st.msgs[sid];
      if (m) h += m.err ? '<div class="conv-err rp-msg" role="alert">' + ico("circle-alert", 15) + "<div>" + rpEsc(m.txt) + "</div></div>" : '<div class="rp-ok-msg small" role="status">' + ico("check", 14) + "<span>" + rpEsc(m.txt) + "</span></div>";
      return h + "</div></li>";
    }

    function renderComparaison(p, cmp, ecrire) {
      const av = cmp && cmp.avant, ap = (cmp && cmp.apres) || p.texte_commun;
      let h = '<div class="rp-cmp-box"><div class="rp-lbl">' + (av ? "Le chef de file a modifié votre partie" : "Le chef de file a rédigé cette partie à votre place")
        + tip(av ? "Votre version et celle du chef de file, côte à côte. Validez la modification si elle vous convient, ou rétablissez votre version : elle redevient le texte commun." : "Le chef de file a écrit cette partie en votre absence. Validez son texte s'il vous convient, ou écrivez votre version ci-dessous et envoyez-la.") + "</div>";
      if (av) {
        const d = rpDiff(av.texte, ap && ap.texte);
        h += '<div class="rp-cmp"><div class="rp-cmp-c"><div class="rp-cmp-h">Votre version</div><div class="rp-txt rp-diff">' + d.avant + '</div></div><div class="rp-cmp-c"><div class="rp-cmp-h">Version du chef de file</div><div class="rp-txt rp-diff">' + d.apres + "</div></div></div>";
        if (d.ok) h += '<div class="muted small rp-p"><mark class="rp-del">Surligné ainsi</mark> : retiré par le chef de file. <mark class="rp-ins">Surligné ainsi</mark> : ajouté par lui.</div>';
      } else h += '<div class="rp-txt rp-txt-b">' + rpTexte(ap && ap.texte, "source du chef de file") + "</div>";
      if (ecrire) h += '<div class="rp-acts">' + btn("valider", ico("check", 14) + (av ? "Valider la modification" : "Valider ce texte"), "primary", ' data-sid="' + p.section_id + '"') + (av ? btn("retablir", ico("undo-2", 14) + "Rétablir ma version", "", ' data-sid="' + p.section_id + '"') : "") + "</div>";
      return h + "</div>";
    }

    function texteEdite(p) {
      const loc = st.edits[p.section_id];
      if (loc && typeof loc.texte === "string") return loc.texte;
      return (p.brouillon && p.brouillon.texte) || "";
    }

    // Saisie pas encore enregistrée (gardée dans l'onglet, jamais envoyée sans « Enregistrer » ou « Envoyer »).
    function modifie(p) {
      const loc = st.edits[p.section_id], b = p.brouillon;
      return !!loc && (!b || loc.texte !== b.texte);
    }

    // Un brouillon écrit APRÈS le texte commun courant, et différent de lui : une nouvelle version à envoyer.
    function enAttente(p) {
      const b = p.brouillon, cur = p.texte_commun;
      return !!(b && cur && b.base_version_id === cur.version_id && b.empreinte !== cur.empreinte);
    }

    // L'éditeur est ouvert tant que rien n'est envoyé ; ensuite, sur demande (« Modifier mon texte ») ou
    // quand une nouvelle version attend d'être envoyée.
    function editeurVisible(p) {
      return !p.texte_commun || !!st.moi[p.section_id] || modifie(p) || enAttente(p);
    }

    function renderEditeur(v, p) {
      const sid = p.section_id, b = p.brouillon, cur = p.texte_commun, aide = p.aide || {};
      const loc = st.edits[sid];
      const reste = Number(aide.restantes || 0);
      const bulleAide = rpEsc(v.message_mode || "") + " Adjugo n'invente aucun fait : ce qu'il ne trouve pas devient « [À compléter] »." + (aide.plafond ? " Aide d'Adjugo pour cette partie : " + reste + " sur " + aide.plafond + " restante" + (reste > 1 ? "s" : "") + "." : "");
      const plafond = !reste && aide.plafond ? '<div class="muted small rp-p">L\'aide d\'Adjugo a déjà servi ' + aide.plafond + " fois pour cette partie : écrivez la suite vous-même, votre texte sera contrôlé de la même façon.</div>" : "";
      if (!b && !loc && !st.moi[sid]) {
        let h = '<div class="rp-choix"><div class="rp-lbl">Rédiger cette partie' + tip(bulleAide) + '</div><div class="rp-acts">'
          + btn("aide", ico("sparkles", 14) + "Rédiger avec Adjugo", "primary", ' data-sid="' + sid + '"' + (reste ? "" : " disabled")) + btn("moi", ico("pencil", 14) + "J'écris moi-même", "", ' data-sid="' + sid + '"') + "</div>" + plafond;
        if (v.mode_simple && v.mode_simple.petit_texte) h += '<button type="button" class="linkbtn small rp-p" data-act="simple" data-sid="' + sid + '">Partir de mon paragraphe</button>';
        return h + "</div>";
      }
      const t = texteEdite(p), mots = rpMots(t), todo = rpACompleter(t);
      const cible = Number(p.longueur_mots || 0);
      const dirty = modifie(p);
      const aEnvoyer = dirty || (b && (!cur || b.empreinte !== cur.empreinte));
      let h = '<div class="rp-ed"><div class="rp-ed-h"><span class="rp-lbl">Votre texte' + tip(bulleAide) + "</span>"
        + (b ? '<span class="muted small">' + rpEsc(b.origine_libelle || "") + (dirty ? " · modifié, pas encore enregistré" : "") + "</span>" : (dirty ? '<span class="muted small">pas encore enregistré</span>' : "")) + "</div>";
      h += '<textarea class="inp rp-ta" rows="10" data-sid="' + sid + '" aria-label="Texte de la partie">' + rpEsc(t) + "</textarea>";
      h += '<div class="rp-ed-m small muted"><span data-mots="' + sid + '">' + mots.toLocaleString("fr-FR") + " mot" + (mots > 1 ? "s" : "") + (cible ? " sur environ " + cible.toLocaleString("fr-FR") + " conseillés" : "") + "</span>"
        + '<span data-todo="' + sid + '"' + (todo ? "" : " hidden") + ">" + (todo ? todo + " « [À compléter] » à remplir" : "") + "</span></div>";
      h += '<div class="rp-acts">' + btn("enregistrer", "Enregistrer", "", ' data-sid="' + sid + '"')
        + (reste ? btn("aide", ico("sparkles", 14) + (b && b.ia ? "Refaire avec Adjugo" : "Rédiger avec Adjugo"), "ghost", ' data-sid="' + sid + '"') : "")
        + (b && reste && cible && rpMots(b.texte) > cible ? btn("raccourcir", "Raccourcir avec Adjugo", "ghost", ' data-sid="' + sid + '"') : "")
        + btn("envoyer", ico("send", 14) + (cur ? "Envoyer cette version" : "Envoyer au groupement"), "primary", ' data-sid="' + sid + '"' + (aEnvoyer && t.trim() ? "" : " disabled")) + "</div>" + plafond;
      const liens = [];
      if (!t.trim() && v.mode_simple && v.mode_simple.petit_texte) liens.push('<button type="button" class="linkbtn small" data-act="simple" data-sid="' + sid + '">Partir de mon paragraphe</button>');
      if (cur && cur.ecrit_par === "chef_de_file" && (cur.texte || "") !== t) liens.push('<button type="button" class="linkbtn small" data-act="partir-commun" data-sid="' + sid + '">Partir du texte du chef de file</button>');
      if (b && Number(b.numero || 0) > 1) liens.push('<button type="button" class="linkbtn small" data-act="historique" data-sid="' + sid + '" aria-expanded="' + (st.hist[sid] ? "true" : "false") + '">Vos brouillons précédents</button>');
      if (liens.length) h += '<div class="rp-liens">' + liens.join("") + "</div>";
      if (st.hist[sid]) h += renderHistorique(sid, b);
      if (b) h += renderFaits(b, sid) + renderExtraits(b);
      return h + "</div>";
    }

    function renderHistorique(sid, b) {
      const list = (st.hist[sid] || []).filter(x => !b || x.id !== b.id);
      if (!list.length) return '<div class="muted small rp-p">Aucun brouillon précédent.</div>';
      return '<ul class="rp-fl rp-hist">' + list.map(x => '<li class="rp-relu small"><span>Brouillon ' + rpEsc(x.numero) + " · " + rpEsc(x.origine_libelle || "") + (x.cree_le ? " · " + rpEsc(rpJour(x.cree_le)) : "") + "</span>"
        + btn("reprendre", "Reprendre ce texte", "ghost", ' data-sid="' + sid + '" data-bid="' + rpEsc(x.id) + '"') + "</li>").join("") + "</ul>";
    }

    function renderFaits(b, sid) {
      const faits = (b.faits || []).filter(f => f && f.type !== "reste");
      const aRelire = faits.filter(f => f.statut !== "relu_par_vous"), relus = faits.filter(f => f.statut === "relu_par_vous");
      const reste = (b.faits || []).find(f => f && f.type === "reste" && f.statut !== "relu_par_vous");
      let h = '<div class="rp-faits">';
      const c = b.controle || {};
      if (c.libelles && c.message) h += '<div class="rp-lbl">' + rpEsc(c.message) + "</div>";
      h += '<div class="rp-lbl">À relire' + (aRelire.length ? ' <span class="rp-badge">' + aRelire.length + "</span>" : "") + tip(rpEsc(BULLE_FAITS)) + "</div>";
      if (!aRelire.length && !reste) h += '<div class="muted small">' + (b.origine === "utilisateur" ? "Texte écrit par vous : vos chiffres et vos noms sont vos déclarations. Adjugo signale les faits ajoutés par l'IA." : "Aucun fait signalé dans ce texte. Relisez tout de même les phrases générales.") + "</div>";
      if (aRelire.length) {
        h += '<ul class="rp-fl">';
        aRelire.forEach(f => {
          h += '<li class="rp-fait"><div class="rp-fk">' + rpEsc(FAIT_TYPES[f.type] || "Fait") + '</div><div class="small">' + rpPhrase(f.phrase || f.fait, f.fait) + "</div>"
            + '<div class="muted small">' + rpEsc(f.message || "Adjugo ne trouve pas d'où vient ce fait : relisez-le.") + "</div>"
            + '<div class="rp-acts">' + btn("relu", f.type === "engagement" ? "Je confirme cet engagement" : "Je l'ai relu", "ghost", ' data-sid="' + sid + '" data-fid="' + rpEsc(f.id) + '"') + "</div></li>";
        });
        h += "</ul>";
      }
      if (reste) h += '<div class="muted small">' + rpEsc(reste.message || "") + "</div>";
      if (relus.length) h += '<details class="gn-det"><summary>Relus par vous (' + relus.length + ")</summary>" + relus.map(f => '<div class="rp-relu small"><span>' + rpEsc(f.fait) + "</span>" + btn("a-relire", "Remettre à relire", "ghost", ' data-sid="' + sid + '" data-fid="' + rpEsc(f.id) + '"') + "</div>").join("") + "</details>";
      const fsrc = b.faits_sources || [];
      if (c.libelles && fsrc.length) {
        h += '<details class="gn-det"><summary>Faits avec une source (' + fsrc.length + ")</summary><ul class=\"rp-fl\">" + fsrc.map(f => '<li class="small"><b>' + rpEsc(f.fait) + "</b>"
          + (f.source && f.source.ref ? ' <span class="rp-ref">' + rpEsc(f.source.ref) + "</span>" : "") + ' <span class="muted">· ' + rpEsc((f.source && f.source.libelle) || "") + (f.source && f.source.doc_nom ? " · " + rpEsc(f.source.doc_nom) : "") + "</span></li>").join("") + "</ul></details>";
      }
      return h + "</div>";
    }

    function renderExtraits(b) {
      const src = b.sources || [];
      if (b.sources_depuis_le_compte) return '<div class="muted small rp-p">Les extraits cités depuis votre compte Adjugo ne s\'affichent que dans votre compte (« Partagé avec moi »).</div>';
      if (!src.length) return "";
      return '<details class="gn-det"><summary>Vos extraits cités, privés (' + src.length + ")</summary>" + tip(rpEsc(BULLE_EXTRAITS)) + '<ul class="rp-fl">' + src.map(x => '<li class="small"><span class="rp-ref">' + rpEsc(x.ref) + "</span> <b>" + rpEsc(x.doc_name || "") + '</b><div class="muted">« ' + rpEsc(x.extrait || "") + " »</div></li>").join("") + "</ul></details>";
    }

    function renderCommun(v, p, ecrire) {
      const cur = p.texte_commun;
      if (!cur) return "";
      const sid = p.section_id;
      let h = '<div class="rp-env">';
      if (p.statut === "validee") h += '<div class="rp-env-t">' + ico("circle-check", 15) + "<b>Validée</b>" + (p.validation && p.validation.le ? '<span class="muted small">le ' + rpEsc(rpJour(p.validation.le)) + "</span>" : "") + "</div>";
      else if (p.statut === "envoyee") {
        h += '<div class="rp-env-t">' + ico("send", 15) + "<b>Envoyée</b>" + (cur.cree_le ? '<span class="muted small">le ' + rpEsc(rpJour(cur.cree_le)) + "</span>" : "") + tip(rpEsc(BULLE_VALIDER)) + "</div>";
        if (ecrire) h += '<div class="rp-acts">' + btn("valider", ico("check", 14) + "Valider ma partie", "primary", ' data-sid="' + sid + '"') + "</div>";
      }
      if (!(p.statut === "a_revalider" && cur.ecrit_par === "chef_de_file"))      // sinon : déjà côte à côte plus haut
        h += '<details class="gn-det"><summary>' + (p.statut === "validee" ? "Voir le texte validé" : (cur.ecrit_par === "chef_de_file" ? "Voir le texte commun actuel" : "Voir le texte envoyé")) + '</summary><div class="rp-txt rp-txt-b">' + rpTexte(cur.texte, cur.ecrit_par === "chef_de_file" ? "source du chef de file" : "votre source") + "</div></details>";
      return h + "</div>";
    }

    function renderDossier(v, ecrire) {
      const d = v.dossier || {}, ma = d.ma_validation, pret = d.pret || {};
      const lu = !!(st.dossier && st.dossier.empreinte === d.empreinte);
      let h = '<div class="rp-dos"><div class="rp-lbl">Le dossier assemblé' + tip(rpEsc(BULLE_DOSSIER)) + "</div>";
      h += '<div class="small muted">' + (pret.sections_total ? rpEsc(pret.message) + " · " : "") + "Votre validation : " + rpEsc(ma ? ma.statut_libelle : "à faire") + "</div>";
      h += '<div class="rp-acts">' + btn("lire-dossier", ico("book-open", 14) + (st.dossierOpen ? "Fermer le dossier assemblé" : "Lire le dossier assemblé"), "", ' aria-expanded="' + (st.dossierOpen ? "true" : "false") + '"');
      if (ecrire && !(ma && ma.statut === "valide")) h += btn("valider-dossier", ico("check", 14) + "Valider le dossier assemblé", lu && d.peut_valider ? "primary" : "", lu && d.peut_valider ? "" : " disabled");
      h += "</div>";
      if (ecrire && !(ma && ma.statut === "valide")) {
        if (!d.peut_valider) h += '<div class="muted small rp-p">Validez d\'abord chacune de vos parties, puis lisez le dossier assemblé.</div>';
        else if (!lu) h += '<div class="muted small rp-p">Lisez le dossier assemblé avant de le valider.</div>';
      }
      const m = st.msgDossier;
      if (m) h += m.err ? '<div class="conv-err rp-msg" role="alert">' + ico("circle-alert", 15) + "<div>" + rpEsc(m.txt) + "</div></div>" : '<div class="rp-ok-msg small" role="status">' + ico("check", 14) + "<span>" + rpEsc(m.txt) + "</span></div>";
      if (st.dossierOpen && st.dossier) h += renderAssemble(st.dossier);
      return h + "</div>";
    }

    function renderAssemble(a) {
      let h = '<div class="rp-assemble" tabindex="0" role="document" aria-label="Dossier assemblé"><p class="muted small rp-p">' + rpEsc(a.message || "") + "</p>";
      (a.parties || []).forEach(p => {
        const r = p.redacteur || {};
        const lib = r.vous ? "votre source" : r.type === "partenaire" ? "source du partenaire" : "source du chef de file";
        h += '<article class="rp-dp"><div class="rp-dp-h"><b>' + rpEsc(p.titre || p.intitule) + '</b><span class="pill ' + (PILL[p.statut] || "neutral") + ' rp-pill">' + rpEsc(p.statut_libelle) + "</span></div>"
          + '<div class="muted small">Rédigée par ' + rpEsc(r.vous ? "vous" : (r.nom || "")) + (p.ecrit_par === "chef_de_file" && r.type === "partenaire" ? ", modifiée par le chef de file" : "") + "</div>"
          + (p.texte ? '<div class="rp-txt">' + rpTexte(p.texte, lib) + "</div>" : '<div class="muted small rp-p">Pas encore de texte commun pour cette partie.</div>') + "</article>";
      });
      return h + "</div>";
    }

    // ── Actions ──────────────────────────────────────────────────────────────────────────────────
    function live(t) { const x = el.querySelector("[data-live]"); if (x) x.textContent = t || ""; }

    async function identite(r, purpose) {
      if (r.code !== "identity_unverified") return false;
      if (o.mode !== "lien" || !o.verifyIdentity) return false;
      const holder = document.createElement("span");
      const ok = await o.verifyIdentity(holder, { purpose, cancelMsg: "Vérification annulée : rien n'a été envoyé." });
      if (!ok && holder.textContent) r.message = holder.textContent;
      return ok;
    }

    async function avecIdentite(fn, sid, purpose) {
      let r = await fn();
      if (!r.ok && r.code === "identity_unverified" && await identite(r, purpose)) r = await fn();
      return r;
    }

    async function enregistrer(sid, silencieux) {
      const p = partie(sid); if (!p) return null;
      const texte = texteEdite(p);
      const r = await call("PUT", "/sections/" + sid + "/brouillon", { texte, base_brouillon_id: p.brouillon ? p.brouillon.id : null });
      if (!r.ok) { say(sid, r.code === "brouillon_modifie" ? r.message + " Votre saisie est gardée sur cet écran." : r.message, true); return null; }
      delete st.edits[sid]; delete st.hist[sid]; garderLocaux();
      if (!silencieux) say(sid, "Enregistré. Les faits de votre texte ont été relus sans IA.");
      return r.data;
    }

    async function act(a, b) {
      const sid = b.dataset.sid ? Number(b.dataset.sid) : st.open;
      if (a === "ouvrir") { st.open = st.open === sid ? null : sid; render(); return; }
      if (a === "recharger") { await load(); return; }
      if (a === "moi") { st.moi[sid] = true; render(); focusTa(sid); return; }
      if (a === "partir-commun") {
        const p = partie(sid), cur = p && p.texte_commun;
        if (!cur) return;
        st.edits[sid] = { texte: cur.texte || "", base: p.brouillon ? p.brouillon.id : null }; st.moi[sid] = true; garderLocaux();
        render(); focusTa(sid); return;
      }
      if (a === "historique") {
        if (st.hist[sid]) { delete st.hist[sid]; render(); return; }
        const r = await call("GET", "/sections/" + sid);
        if (!r.ok) { say(sid, r.message, true); render(); return; }
        st.hist[sid] = (r.data && r.data.brouillons) || []; render(); return;
      }
      if (a === "reprendre") {
        const r = await call("GET", "/sections/" + sid + "/brouillons/" + encodeURIComponent(b.dataset.bid || ""));
        if (!r.ok || !r.data) { say(sid, r.message, true); render(); return; }
        const p = partie(sid);
        st.edits[sid] = { texte: r.data.texte || "", base: p && p.brouillon ? p.brouillon.id : null }; st.moi[sid] = true;
        delete st.hist[sid]; garderLocaux();
        say(sid, "Texte repris dans l'éditeur : enregistrez-le pour qu'il redevienne votre brouillon.");
        render(); focusTa(sid); return;
      }
      if (a === "simple") { const p = partie(sid); st.edits[sid] = { texte: (st.vue.mode_simple && st.vue.mode_simple.petit_texte) || "", base: p && p.brouillon ? p.brouillon.id : null }; st.moi[sid] = true; garderLocaux(); render(); focusTa(sid); return; }
      if (a === "lire-dossier") {
        if (st.dossierOpen) { st.dossierOpen = false; render(); return; }
        const r = await call("GET", "/dossier");
        if (!r.ok) { st.msgDossier = { txt: r.message, err: true }; render(); return; }
        st.msgDossier = null;
        st.dossier = r.data; st.dossierOpen = true; render(); return;
      }
      if (a === "export") { await exporter(); return; }
      if (a === "espace-ouvrir") { await espace({}); return; }
      if (a === "espace-code") { await espaceCode(); return; }
      if (a === "espace-reinit") {
        const ok = await modal({ title: "Réinitialiser votre espace privé ?", danger: true, confirmLabel: "Réinitialiser", focusCancel: true,
          bodyHtml: "Vos brouillons non envoyés seront <b>effacés</b>. Les textes que vous avez envoyés restent. Si votre invitation vise une adresse email, un code vous sera demandé avant d'envoyer ou de valider." });
        if (ok) await espace({ reinitialiser: true });
        return;
      }
      if (st.busy) return;
      st.busy = a; b.disabled = true;
      try {
        if (a === "enregistrer") { if (await enregistrer(sid)) { await load(); changed(); } else render(); }
        else if (a === "aide" || a === "raccourcir") {
          const p = partie(sid);
          const dirty = p && modifie(p);
          if (dirty || (a === "aide" && p && p.brouillon)) {
            const ok = await modal({ title: a === "aide" ? "Rédiger un nouveau texte ?" : "Raccourcir votre texte ?", confirmLabel: a === "aide" ? "Rédiger avec Adjugo" : "Raccourcir",
              bodyHtml: (a === "aide" ? "Adjugo rédige un nouveau texte pour cette partie. " : "") + (dirty ? "Votre saisie pas encore enregistrée est enregistrée d'abord. " : "")
                + "Votre texte actuel reste dans « Vos brouillons précédents » : vous pourrez le reprendre." });
            if (!ok) return;
            if (dirty && !(await enregistrer(sid, true))) { render(); return; }
          }
          const r = await call("POST", "/sections/" + sid + "/aide", { action: a === "aide" ? "rediger" : "raccourcir" });
          if (r.ok && r.data && r.data.tache) { st.jobs[sid] = r.data.tache.id; say(sid, ""); live("Adjugo rédige votre partie."); await load(); }
          else { say(sid, r.message, true); render(); }
        }
        else if (a === "envoyer") await envoyer(sid);
        else if (a === "valider") {
          const p = partie(sid); const cur = p && p.texte_commun;
          const r = await avecIdentite(() => call("POST", "/sections/" + sid + "/valider", { version_id: cur ? cur.version_id : 0 }), sid, "Pour valider votre partie");
          say(sid, r.ok ? "Partie validée." : r.message, !r.ok);
          await load(); if (r.ok) changed();
        }
        else if (a === "retablir") {
          const p = partie(sid); const cur = p && p.texte_commun;
          const ok = await modal({ title: "Rétablir votre version ?", confirmLabel: "Rétablir ma version", bodyHtml: "Votre texte d'avant redevient le texte commun de la partie. La version du chef de file reste dans l'historique." });
          if (!ok) return;
          const r = await avecIdentite(() => call("POST", "/sections/" + sid + "/retablir", { base_version_id: cur ? cur.version_id : 0 }), sid, "Pour rétablir votre version");
          say(sid, r.ok ? "Votre version est de nouveau le texte commun. Validez-la quand elle est définitive." : r.message, !r.ok);
          await load(); if (r.ok) changed();
        }
        else if (a === "relu" || a === "a-relire") {
          const r = await call("POST", "/sections/" + sid + "/faits/" + encodeURIComponent(b.dataset.fid || ""), { statut: a === "relu" ? "relu_par_vous" : "a_relire" });
          if (!r.ok) say(sid, r.message, true);
          await load();
        }
        else if (a === "valider-dossier") {
          const r = await avecIdentite(() => call("POST", "/dossier/valider", { empreinte: st.dossier ? st.dossier.empreinte : null }), null, "Pour valider le dossier assemblé");
          if (!r.ok) { if (r.code === "dossier_modifie") { st.dossier = null; st.dossierOpen = false; } st.msgDossier = { txt: r.message, err: true }; }
          else { st.msgDossier = { txt: "Dossier assemblé validé. S'il change, il repassera « à revalider »." }; live("Dossier assemblé validé."); }
          await load(); if (r.ok) changed();
        }
      } finally { st.busy = ""; if (b.isConnected) b.disabled = false; }
    }

    function focusTa(sid) { const t = el.querySelector('textarea[data-sid="' + sid + '"]'); if (t) { t.focus(); } }

    async function envoyer(sid) {
      let p = partie(sid); if (!p) return;
      const dirty = st.edits[sid] && (!p.brouillon || st.edits[sid].texte !== p.brouillon.texte);
      const t = texteEdite(p), todo = rpACompleter(t);
      const c = (p.brouillon && p.brouillon.controle) || {};
      const cpt = c.libelles && p.brouillon ? rpCompteurs(p.brouillon.compteurs) : [];
      const aRelire = p.brouillon ? (p.brouillon.faits_a_relire || 0) : 0;
      let body = "<b>" + rpEsc(st.vue.avertissement_envoi || "Ce texte sera lu par le chef de file et par les autres membres du groupement.") + "</b><br><br>" + rpEsc(BULLE_ENVOI);
      if (cpt.length) body += "<br>Compteurs transmis : " + rpEsc(cpt.join(", ")) + ".";
      if (todo || aRelire) body += '<br><br><span class="rp-warn">' + rpEsc([todo ? todo + " « [À compléter] » à remplir" : "", aRelire ? aRelire + " fait" + (aRelire > 1 ? "s" : "") + " encore à relire" : ""].filter(Boolean).join(" et ")) + " : le dossier commun ne pourra pas être déposé tant qu'ils restent.</span>";
      if (st.vue.identite && st.vue.identite.a_prouver) body += "<br><br>" + rpEsc(st.vue.identite.message);
      const ok = await modal({ title: "Envoyer votre partie au groupement ?", bodyHtml: body, confirmLabel: "J'ai lu, envoyer", cancelLabel: "Revenir", focusCancel: true });
      if (!ok) return;
      if (dirty) { if (!(await enregistrer(sid, true))) { render(); return; } await load(); p = partie(sid); }
      if (!p || !p.brouillon) return;
      const bid = p.brouillon.id;
      const r = await avecIdentite(() => call("POST", "/sections/" + sid + "/envoyer", { brouillon_id: bid, avertissement_lu: true }), sid, "Pour envoyer votre partie");
      if (r.ok) { delete st.moi[sid]; delete st.hist[sid]; }
      say(sid, r.ok ? "Partie envoyée : le chef de file et les autres membres peuvent la lire. Validez-la quand elle est définitive." : r.message, !r.ok);
      await load(); if (r.ok) changed();
    }

    async function espace(body) {
      const r = await call("POST", "/espace", body);
      if (r.ok && r.data && r.data.cle) {
        garderCle(r.data.cle);
        if (r.data.brouillons_effaces) live(r.data.brouillons_effaces + " brouillon(s) effacé(s).");
        await load(); changed(); return true;
      }
      if (r.code === "espace_deja_ouvert") { await load(); return false; }
      st.err = r.message; st.vue = null; render();
      return false;
    }

    async function espaceCode() {
      const rq = await fetch(o.invite + "/otp/request", { method: "POST" }).then(x => x.ok ? x.json() : null).catch(() => null);
      if (!rq || (!rq.sent && !rq.already)) { await modal({ title: "Code indisponible", bodyHtml: rpEsc((rq && rq.reason) || "Envoi impossible pour le moment : réessayez dans quelques minutes."), confirmLabel: "Fermer" }); return; }
      let note = "";
      while (true) {
        const res = await modal({ title: "Ouvrir votre espace ici", withInput: true, inputLabel: "Code reçu par email", noteHtml: note, confirmLabel: "Ouvrir",
          bodyHtml: "Saisissez le code à 6 chiffres envoyé à <b>" + rpEsc(rq.email_masked || "votre adresse") + "</b>. Vos brouillons sont gardés." });
        if (!res) return;
        if (!res.value) { note = "Saisissez le code reçu par email."; continue; }
        const r = await call("POST", "/espace", { code: res.value });
        if (r.ok && r.data && r.data.cle) { garderCle(r.data.cle); await load(); changed(); return; }
        if (r.code === "code_incorrect") { note = rpEsc(r.message); continue; }
        await modal({ title: "Ouverture impossible", bodyHtml: rpEsc(r.message), confirmLabel: "Fermer" });
        return;
      }
    }

    async function exporter() {
      const r = await call("GET", "/export", undefined, true);
      if (!r.ok) return;
      try {
        const blob = await r.res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "ma_partie_adjugo.json";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      } catch (e) {}
    }

    // ── Écoute (délégation : l'écran est redessiné après chaque action) ──────────────────────────────
    const onClick = (e) => {
      const b = e.target.closest && e.target.closest("[data-act]");
      if (!b || !el.contains(b) || b.disabled) return;
      e.preventDefault();
      act(b.dataset.act, b);
    };
    const onInput = (e) => {
      const t = e.target;
      if (!t || !t.matches || !t.matches("textarea.rp-ta")) return;
      const sid = Number(t.dataset.sid), p = partie(sid);
      st.edits[sid] = { texte: t.value, base: p && p.brouillon ? p.brouillon.id : null };
      garderLocaux();
      const mots = rpMots(t.value), todo = rpACompleter(t.value), cible = Number((p && p.longueur_mots) || 0);
      const m = el.querySelector('[data-mots="' + sid + '"]');
      if (m) m.textContent = mots.toLocaleString("fr-FR") + " mot" + (mots > 1 ? "s" : "") + (cible ? " sur environ " + cible.toLocaleString("fr-FR") + " conseillés" : "");
      const td = el.querySelector('[data-todo="' + sid + '"]');
      if (td) { td.hidden = !todo; td.textContent = todo ? todo + " « [À compléter] » à remplir" : ""; }
      const env = el.querySelector('[data-act="envoyer"][data-sid="' + sid + '"]');
      if (env) env.disabled = !t.value.trim();
    };
    el.addEventListener("click", onClick);
    el.addEventListener("input", onInput);
    load();

    return {
      reload: load,
      destroy() {
        st.destroyed = true;
        if (st.timer) clearInterval(st.timer);
        el.removeEventListener("click", onClick);
        el.removeEventListener("input", onInput);
        el.innerHTML = "";
      },
    };
  }

  root.AdjugoRedactionPartenaire = { mount, _pur: { rpEsc, rpMots, rpTexte, rpPhrase, rpLim, rpCompteurs, rpJour, rpACompleter, rpDiff } };
})(typeof window !== "undefined" ? window : this);
