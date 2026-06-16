const { createApp } = Vue;

// Rendu des icônes Lucide SANS remplacer les éléments (sinon conflit avec le
// virtual DOM de Vue → "parent.insertBefore" null). On injecte le SVG en
// innerHTML du <i data-lucide>, que Vue continue de gérer.
function _pascal(name) {
  return name.split("-").map(s => s.charAt(0).toUpperCase() + s.slice(1)).join("");
}
function _iconSvg(node) {
  const children = Array.isArray(node) ? node : [];
  const inner = children.map(c => {
    const tag = c[0], attrs = c[1] || {};
    const a = Object.keys(attrs).map(k => `${k}="${attrs[k]}"`).join(" ");
    return `<${tag} ${a}></${tag}>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="lucide">${inner}</svg>`;
}
function paintIcons(root) {
  const L = window.lucide;
  if (!L) return;
  (root || document).querySelectorAll("[data-lucide]").forEach(el => {
    const name = el.getAttribute("data-lucide");
    if (!name || el._iconName === name) return;       // déjà peint
    const pascal = _pascal(name);
    const node = L[pascal] || (L.icons && L.icons[pascal]);
    if (!node) return;                                 // nom inconnu → on laisse vide
    el.innerHTML = _iconSvg(node);
    el._iconName = name;
  });
}

// Traduction runtime de l'UI : remplace les libellés FR statiques par leur
// traduction (dictionnaire window.ADJUGO_I18N) selon la langue du pays choisi.
// Idempotent : un texte déjà traduit ne correspond plus à une clé FR.
function translateDOM(lang) {
  const dict = lang && window.ADJUGO_I18N && window.ADJUGO_I18N[lang];
  if (!dict) return;  // français ou langue inconnue → aucune traduction
  const root = document.body;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentNode;
      if (!p || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      const t = p.nodeName;
      if (t === "SCRIPT" || t === "STYLE" || t === "TEXTAREA") return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n);
  nodes.forEach(node => {
    const raw = node.nodeValue, key = raw.trim();
    const tr = dict[key];
    if (tr && tr !== key) node.nodeValue = raw.replace(key, () => tr);
  });
  root.querySelectorAll("[placeholder],[title],[aria-label]").forEach(el => {
    ["placeholder", "title", "aria-label"].forEach(attr => {
      const v = el.getAttribute(attr);
      const tr = v && dict[v.trim()];
      if (tr) el.setAttribute(attr, tr);
    });
  });
}

const __adjApp = createApp({
  data() {
    return {
      token: localStorage.getItem("adjugo_token") || "",
      theme: localStorage.getItem("adjugo_theme") || "system",
      mobileNav: false,
      user: {}, company: {}, criteria: {},
      view: "dashboard", busy: false, toast: null, pending: 0, llmInfo: null,
      auth: { mode: "login", email: "", password: "", full_name: "", company_name: "" },
      stats: {}, projects: [], cotraitants: [], contacts: [], invoices: [], documents: [], expiring: [],
      veille: { q: "", loc: "", results: [], loading: false },
      drawer: null, modal: null,
      ag: { query: "réhabilitation groupe scolaire", running: false, log: [], gonogo: null, coverage: null, lots: [], dossier: null },
      agState: {}, agStep: {},
      agentDefs: [
        { id: "sourceur", ic: "radar", name: "Agent Sourceur", role: "Veille BOAMP · scoring critères · Go/No-Go" },
        { id: "groupement", ic: "handshake", name: "Agent Stratège", role: "Lots non couverts · matching co-traitants" },
        { id: "redacteur", ic: "file-text", name: "Agent Rédacteur", role: "Mémoire technique · CERFA · dossier ZIP" },
      ],
      statuses: ["nouveau", "en_cours", "envoye", "gagne", "perdu"],
      statuses2: ["nouveau", "en_cours", "envoye", "gagne", "perdu", "abandonne"],
      plan: { plan: "starter" }, org: { data: null, name: "", invite: { email: "", full_name: "" }, lastTemp: null },
      discover: { open: false, trade: "", dept: "", q: "", results: [], loading: false, total: 0 }, trades: [],
      countries2: [], adaptedCountries: [], orgCountry: "FR", lang: "fr",
      amont: { signals: [], uploading: false, scanning: false, regions: [], domaines: [], auto: false },
      amontDomaines: ["bâtiment", "voirie / VRD", "réseaux", "énergie / rénovation énergétique", "espaces verts / aménagement", "numérique / télécom", "équipement", "études / maîtrise d'œuvre"],
      kb: { docs: [], totalChunks: 0, uploading: false, kind: "memoire", text: "", textName: "", busyText: false,
            searchQ: "", searchRes: null, qText: "", qResults: null, qLoading: false,
            memoire: null, memoireLoading: false },
      cospace: { spaces: [], current: null, newName: "", newMarche: "", inviteEmail: "", inviteRole: "cotraitant",
                 lastToken: "", joinToken: "", dceText: "", memoire: null, generating: false,
                 warroomDce: "", warroomLoading: false },
      amontRegions: [
        { code: "IDF", nom: "Île-de-France", deps: ["75", "77", "78", "91", "92", "93", "94", "95"] },
        { code: "ARA", nom: "Auvergne-Rhône-Alpes", deps: ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"] },
        { code: "NAQ", nom: "Nouvelle-Aquitaine", deps: ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"] },
        { code: "OCC", nom: "Occitanie", deps: ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"] },
        { code: "HDF", nom: "Hauts-de-France", deps: ["02", "59", "60", "62", "80"] },
        { code: "GES", nom: "Grand Est", deps: ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"] },
        { code: "PAC", nom: "Provence-Alpes-Côte d'Azur", deps: ["04", "05", "06", "13", "83", "84"] },
        { code: "PDL", nom: "Pays de la Loire", deps: ["44", "49", "53", "72", "85"] },
        { code: "NOR", nom: "Normandie", deps: ["14", "27", "50", "61", "76"] },
        { code: "BRE", nom: "Bretagne", deps: ["22", "29", "35", "56"] },
        { code: "BFC", nom: "Bourgogne-Franche-Comté", deps: ["21", "25", "39", "58", "70", "71", "89", "90"] },
        { code: "CVL", nom: "Centre-Val de Loire", deps: ["18", "28", "36", "37", "41", "45"] },
        { code: "COR", nom: "Corse", deps: ["2A", "2B"] },
        { code: "DROM", nom: "Outre-mer", deps: ["971", "972", "973", "974", "976"] },
      ],
      src: {
        query: "", dept: "", country: "FR", advOpen: false, type_marche: "", cpv: "", searching: false, tenders: [], errors: [], sources: [], expanded: null,
        analyzing: false, analysis: null, projectId: null, chosen: null,
        ct: { trade: "", dept: "", searching: false, companies: [], selected: [], errors: [] },
        generating: false, dossier: null, alerts: [],
        renewals: { list: [], loading: false, done: false },
      },
      ao: { project: null, dossier: null, generating: false, uploading: false, back: "dashboard",
            cotraitants: [], stOpen: false, st: { trade: "", dept: "", role: "sous_traitant", loading: false, results: [] },
            documents: [], checklist: null, buyer: null, buyerLoading: false, group: null,
            qa: [], qaInput: "", qaLoading: false,
            estimate: null, estimateOpen: false, estimateBusy: false, estimating: false, estimateDistance: 0, reviewNote: "",
            share: { open: false, busy: false, invites: [], lastUrl: "", auditOpen: false, audit: [], contributions: [], contribOpen: false, form: { recipient: "", company_name: "", role: "cotraitant", can_view_docs: true, can_contribute: true, expires_days: 30 } } },
      titles: { kb: "Base de connaissances — savoir-faire & mémoires IA", amont: "Veille amont — signaux d'investissement", dashboard: "Tableau de bord", sourcing: "Sourcing IA — appels d'offres", agent: "Agent IA — Pipeline multi-agents", pipeline: "Pipeline des appels d'offres", veille: "Veille des marchés publics", cotraitants: "Réseau de co-traitants", contacts: "Contacts CRM", documents: "Coffre-fort documentaire", invoices: "Devis & Factures", company: "Profil entreprise", criteria: "Critères Go/No-Go", team: "Équipe", billing: "Abonnement", aodetail: "Appel d'offres" },
      subtitles: { kb: "Déposez vos documents → l'IA rédige des mémoires et réponses 100% sourcés", amont: "Détectez les projets des collectivités, des mois avant l'appel d'offres", dashboard: "Vue d'ensemble de votre activité", sourcing: "Sources officielles, traçables — vous validez chaque étape", agent: "3 agents IA orchestrés de la veille au dossier complet", pipeline: "Suivez vos AO étape par étape", veille: "Appels d'offres réels en direct du BOAMP", cotraitants: "Vos partenaires pour répondre en groupement", contacts: "Maîtres d'ouvrage, partenaires, fournisseurs", documents: "Vos pièces administratives centralisées", invoices: "Facturation liée à vos marchés", company: "Informations utilisées dans vos candidatures", criteria: "Pilotez les décisions automatiques de l'agent", team: "Invitez vos collègues à collaborer sur vos dossiers", billing: "Débloquez toute la puissance d'Adjugo", aodetail: "Dossier complet de l'appel d'offres" },
    };
  },
  computed: {
    initials() { return (this.user.full_name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase(); },
    quotaReached() { const u = this.stats.usage; return !!u && u.analyses_remaining <= 0; },
  },
  mounted() {
    this.applyTheme();
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (this.theme === "system") this.applyTheme(); });
    }
    this.renderIcons();
    // Accessibilité clavier (RGAA) : Échap ferme la modale ouverte ; Entrée/Espace
    // active l'élément de navigation focalisé (les nav-item ne sont pas des <button>).
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { const x = document.querySelector(".overlay .modal-h .x, .drawer .x"); if (x) x.click(); }
      const a = document.activeElement;
      if ((e.key === "Enter" || e.key === " ") && a && a.classList && a.classList.contains("nav-item")) { e.preventDefault(); a.click(); }
    });
    this.$nextTick(() => this._a11y());
    if (!this.token && new URLSearchParams(location.search).get("demo") === "1") { this.demoLogin(); return; }
    if (this.token) this.boot();
  },
  updated() { this.renderIcons(); this.renderI18n(); this._a11y(); },
  methods: {
    // Accessibilité : associe chaque label à son champ, rend les modales/nav sémantiques.
    _a11y() {
      try {
        const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
        const FALLBACK = { email: "E-mail", password: "Mot de passe", search: "Recherche",
          tel: "Téléphone", number: "Valeur", date: "Date", file: "Importer un fichier" };
        // Nom accessible sur TOUTE commande de formulaire (pas seulement celles en .field) :
        // label associé > label du .field parent > placeholder > repli par type.
        document.querySelectorAll("input:not([type=hidden]), select, textarea").forEach((el) => {
          if (el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.closest("label")) return;
          let name = "";
          if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) name = l.textContent; }
          if (!name) { const f = el.closest(".field"); if (f) { const l = f.querySelector("label"); if (l) name = l.textContent; } }
          if (!name) name = el.getAttribute("placeholder") || "";
          if (!name) name = FALLBACK[el.getAttribute("type")] || (el.tagName === "SELECT" ? "Sélection" : "Champ");
          el.setAttribute("aria-label", clean(name));
        });
        document.querySelectorAll(".modal,.drawer").forEach((m) => { m.setAttribute("role", "dialog"); m.setAttribute("aria-modal", "true"); });
        document.querySelectorAll(".nav-item").forEach((n) => { if (!n.getAttribute("tabindex")) { n.setAttribute("tabindex", "0"); n.setAttribute("role", "button"); } });
        // Boutons/liens à ICÔNE SEULE (pas de texte) : leur donner un nom accessible.
        const ICON = { x: "Fermer", "trash-2": "Supprimer", trash: "Supprimer", plus: "Ajouter",
          search: "Rechercher", download: "Télécharger", package: "Exporter", edit: "Modifier",
          "pencil": "Modifier", check: "Valider", "external-link": "Ouvrir le lien", copy: "Copier",
          "more-horizontal": "Plus d'options", "chevron-down": "Dérouler", filter: "Filtrer" };
        document.querySelectorAll("button, a").forEach((el) => {
          if (clean(el.textContent) || el.getAttribute("aria-label") || el.getAttribute("title")) return;
          let label = el.classList.contains("x") ? "Fermer" : "";
          if (!label) { const ic = el.querySelector("[data-lucide]"); if (ic) { const k = ic.getAttribute("data-lucide"); label = ICON[k] || k.replace(/-/g, " "); } }
          if (label) el.setAttribute("aria-label", label);
        });
      } catch (e) { console.warn("a11y enhancement skipped:", e); }
    },
    renderI18n() { if (this.lang && this.lang !== "fr") this.$nextTick(() => translateDOM(this.lang)); },
    applyLang(code) { this.lang = code || "fr"; document.documentElement.setAttribute("lang", this.lang); this.renderI18n(); },
    // ── Thème + icônes ──
    setTheme(t) { this.theme = t; localStorage.setItem("adjugo_theme", t); this.applyTheme(); },
    applyTheme() {
      const dark = this.theme === "dark" || (this.theme === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    },
    renderIcons() { this.$nextTick(() => paintIcons()); },

    // ── API helper ──
    async api(method, path, body, isForm) {
      this.pending++;   // → barre de progression globale (retour visuel sur TOUTE action réseau)
      try {
      const opt = { method, headers: {} };
      if (this.token) opt.headers["Authorization"] = "Bearer " + this.token;
      if (body && !isForm) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
      if (isForm) opt.body = body;
      const r = await fetch(path, opt);
      if (r.status === 401) { this.logout(); throw new Error("Session expirée"); }
      const txt = await r.text();
      const data = txt ? JSON.parse(txt) : null;
      if (!r.ok) throw new Error((data && data.detail) ? JSON.stringify(data.detail) : "Erreur " + r.status);
      return data;
      } finally { this.pending = Math.max(0, this.pending - 1); }
    },
    notify(msg, kind = "ok") { if (this._toastT) clearTimeout(this._toastT); this.toast = { msg, kind }; this._toastT = setTimeout(() => this.toast = null, 2600); },
    notifyUndo(msg, undoFn) { if (this._toastT) clearTimeout(this._toastT); this.toast = { msg, kind: "ok", undo: undoFn }; this._toastT = setTimeout(() => this.toast = null, 7000); },
    doUndo() { const t = this.toast; this.toast = null; if (t && t.undo) t.undo(); },

    // ── Auth ──
    async submitAuth() {
      this.busy = true;
      try {
        const path = this.auth.mode === "login" ? "/api/auth/login" : "/api/auth/register";
        const body = this.auth.mode === "login"
          ? { email: this.auth.email, password: this.auth.password }
          : { email: this.auth.email, password: this.auth.password, full_name: this.auth.full_name, company_name: this.auth.company_name };
        const res = await this.api("POST", path, body);
        this.token = res.access_token; localStorage.setItem("adjugo_token", this.token);
        await this.boot();
      } catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async demoLogin() {
      this.busy = true;
      try {
        const res = await this.api("POST", "/api/auth/demo");
        this.token = res.access_token; localStorage.setItem("adjugo_token", this.token);
        history.replaceState({}, "", "/app");   // retire ?demo=1 de l'URL
        await this.boot();
      } catch (e) { this.notify("Démo momentanément indisponible.", "err"); } finally { this.busy = false; }
    },
    logout() { localStorage.removeItem("adjugo_token"); window.location.href = "/"; },

    async boot() {
      try { this.user = await this.api("GET", "/api/auth/me"); } catch (e) { return; }
      await Promise.all([this.loadCompany(), this.loadCriteria(), this.loadProjects(), this.loadCotraitants(), this.loadStats(), this.loadOrg(), this.loadAdaptedCountries(), this.loadAmont(), this.loadLlmInfo()]);
      // Adaptation au pays de l'organisation : scope AO + devise + LANGUE par défaut
      if (this.org.data && this.org.data.country) { this.src.country = this.org.data.country; this.orgCountry = this.org.data.country; this.applyLang(this.org.data.lang); }
      this.go("dashboard");
    },

    // ── Navigation + lazy loads ──
    go(v) {
      this.view = v;
      this.mobileNav = false;  // referme le menu mobile à la navigation
      if (v === "dashboard") { this.loadStats(); this.loadExpiring(); }
      if (v === "pipeline") this.loadProjects();
      if (v === "contacts") this.loadContacts();
      if (v === "invoices") this.loadInvoices();
      if (v === "documents") this.loadDocuments();
      if (v === "cotraitants") { this.loadCotraitants(); this.loadTrades(); this.coLoad(); }
      if (v === "agent") this.loadStats();
      if (v === "sourcing") { this.loadTrades(); this.loadAlerts(); this.loadCountries(); }
      if (v === "amont") this.loadAmont();
      if (v === "kb") this.kbLoad();
      if (v === "team") this.loadOrg();
      if (v === "billing") { this.loadPlan(); this.loadStats(); }
    },

    // ── Registre entreprises (données réelles) ──
    async loadTrades() { if (this.trades.length) return; try { this.trades = await this.api("GET", "/api/registre/trades"); } catch (e) {} },
    async lookupCompany() {
      const q = (this.company.siret || this.company.name || "").trim();
      if (!q) { this.notify("Saisis un SIRET ou un nom", "err"); return; }
      this.busy = true;
      try {
        const r = await this.api("GET", "/api/registre/company?q=" + encodeURIComponent(q));
        ["name", "siret", "code_ape", "forme_juridique", "address", "postal_code", "city", "effectif", "tva_intracom"].forEach(k => { if (r[k]) this.company[k] = r[k]; });
        if (r.dirigeant && !this.company.representant_legal) this.company.representant_legal = r.dirigeant;
        if (r.source === "VIES") {
          if (r.vat_valid && r.name) this.notify("TVA UE validée (VIES) — profil pré-rempli");
          else if (r.vat_valid) this.notify("TVA UE validée — nom non communiqué par ce pays, complétez le profil");
          else this.notify("Numéro de TVA non valide auprès de VIES", "err");
        } else {
          this.notify("Profil pré-rempli depuis le registre");
        }
      } catch (e) { this.notify("Entreprise introuvable", "err"); } finally { this.busy = false; }
    },
    openDiscover() { this.discover.open = true; this.discover.results = []; this.loadTrades(); if (!this.discover.dept) this.discover.dept = (this.company.postal_code || "").slice(0, 2); },
    async runDiscover() {
      this.discover.loading = true; this.discover.results = [];
      try {
        const qs = "?activity=" + encodeURIComponent(this.discover.trade) + "&departement=" + encodeURIComponent(this.discover.dept) + (this.discover.q ? "&query=" + encodeURIComponent(this.discover.q) : "");
        const r = await this.api("GET", "/api/registre/discover" + qs);
        this.discover.results = r.results || []; this.discover.total = r.total || 0;
        if (!this.discover.results.length) this.notify("Aucune entreprise trouvée", "err");
      } catch (e) { this.notify(e.message, "err"); } finally { this.discover.loading = false; }
    },
    async importCotraitant(e) {
      const t = this.trades.find(t => t.key === this.discover.trade || (t.label || "").toLowerCase() === (this.discover.trade || "").toLowerCase());
      const tradeLabel = t ? t.label : (this.discover.trade || "");
      try {
        await this.api("POST", "/api/registre/import", { ...e, specialites: tradeLabel });
        e._added = true; this.loadCotraitants(); this.notify(e.name + " ajouté au réseau");
      } catch (err) { this.notify(err.message.includes("409") ? "Déjà dans le réseau" : err.message, "err"); }
    },

    // ── Abonnement / MRR ──
    async loadPlan() { try { this.plan = await this.api("GET", "/api/stripe/status"); } catch (e) { this.plan = { plan: this.user.plan || "starter" }; } },
    roleLabelOrg(r) { return ({ admin: "Administrateur", membre: "Membre" })[r] || r; },
    async loadOrg() {
      try { this.org.data = await this.api("GET", "/api/org/"); this.org.name = this.org.data.name; this.orgCountry = this.org.data.country; }
      catch (e) { this.org.data = null; }
    },
    async loadAdaptedCountries() { if (this.adaptedCountries.length) return; try { this.adaptedCountries = await this.api("GET", "/api/org/countries"); } catch (e) {} },
    async setOrgCountry() {
      try {
        await this.api("PUT", "/api/org/", { country: this.orgCountry });
        await this.loadOrg();
        this.src.country = this.orgCountry;
        if (this.org.data) this.applyLang(this.org.data.lang);
        const n = (this.adaptedCountries.find(c => c.code === this.orgCountry) || {}).nom || this.orgCountry;
        this.notify("Adjugo adapté pour : " + n);
      } catch (e) { this.notify(e.message, "err"); if (this.org.data) this.orgCountry = this.org.data.country; }
    },
    async orgRename() {
      try { await this.api("PUT", "/api/org/", { name: this.org.name }); this.loadOrg(); this.notify("Organisation renommée"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async orgInvite() {
      const i = this.org.invite;
      if (!i.email) { this.notify("Email requis", "err"); return; }
      try {
        const r = await this.api("POST", "/api/org/invite", { email: i.email, full_name: i.full_name });
        this.org.lastTemp = r; this.org.invite = { email: "", full_name: "" };
        this.loadOrg(); this.notify("Membre invité");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async orgRemove(m) {
      try { await this.api("DELETE", "/api/org/members/" + m.id); this.loadOrg(); this.notify(m.full_name + " retiré"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async toggleOverage() {
      const on = !(this.stats.usage && this.stats.usage.overage_enabled);
      try { await this.api("POST", "/api/stripe/overage?enabled=" + on); await this.loadStats(); this.notify(on ? "Paiement à l'usage activé" : "Paiement à l'usage désactivé"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async checkout(planKey) {
      try {
        const r = await this.api("POST", "/api/stripe/create-checkout?plan=" + planKey);
        if (r && r.checkout_url) window.location.href = r.checkout_url;
      } catch (e) { this.notify("Paiement indisponible (config Stripe) : " + e.message, "err"); }
    },
    async portal() {
      try { const r = await this.api("POST", "/api/stripe/portal"); if (r.portal_url) window.location.href = r.portal_url; }
      catch (e) { this.notify("Portail indisponible", "err"); }
    },

    async loadStats() { try { this.stats = await this.api("GET", "/api/agent/stats"); } catch (e) {} },
    async loadProjects() { try { this.projects = await this.api("GET", "/api/projects/") || []; } catch (e) {} },
    async loadCotraitants() { try { this.cotraitants = await this.api("GET", "/api/cotraitants/") || []; } catch (e) {} },
    async loadContacts() { try { this.contacts = await this.api("GET", "/api/contacts/") || []; } catch (e) {} },
    async loadInvoices() { try { this.invoices = await this.api("GET", "/api/invoices/") || []; } catch (e) {} },
    async loadDocuments() { try { this.documents = await this.api("GET", "/api/documents/") || []; } catch (e) {} },
    async loadExpiring() { try { this.expiring = await this.api("GET", "/api/documents/expiring") || []; } catch (e) { this.expiring = []; } },
    async loadCompany() { try { const c = await this.api("GET", "/api/company/"); if (c && !c.detail) this.company = c; } catch (e) {} },
    async loadLlmInfo() { try { this.llmInfo = await this.api("GET", "/api/llm/info"); } catch (e) {} },
    async loadCriteria() { try { this.criteria = await this.api("GET", "/api/criteria/") || {}; } catch (e) {} },

    // ── Company / Criteria ──
    async saveCompany() {
      this.busy = true;
      try { await this.api("PUT", "/api/company/", this.company); this.notify("Profil enregistré"); }
      catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async saveCriteria() {
      this.busy = true;
      try { await this.api("PUT", "/api/criteria/", this.criteria); this.notify("Critères enregistrés"); }
      catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },

    // ── Projects (kanban + page détaillée AO) ──
    byStatus(s) { return this.projects.filter(p => (p.status || "nouveau") === s); },
    openProject(p) { this.openAo(p); },
    async openAo(p) {
      this.ao.back = this.view; this.ao.dossier = null; this.ao.project = p;
      this.ao.cotraitants = []; this.ao.stOpen = false; this.ao.st.results = [];
      this.view = "aodetail"; this.loadTrades(); this.ao.documents = []; this.ao.buyer = null; this.ao.group = null;
      this.ao.qa = []; this.ao.qaInput = "";
      this.ao.estimate = null; this.ao.estimateOpen = false; this.ao.estimateDistance = 0;
      this.ao.share = { open: false, busy: false, invites: [], lastUrl: "", auditOpen: false, audit: [], contributions: [], contribOpen: false, form: { recipient: "", company_name: "", role: "cotraitant", can_view_docs: true, can_contribute: true, expires_days: 30 } };
      try { this.ao.project = await this.api("GET", "/api/projects/" + p.id); } catch (e) {}
      this.aoLoadCotraitants(); this.aoLoadDocs(); this.aoLoadChecklist(); this.loadInvoices(); this.aoLoadEstimate(); this.aoLoadInvites();
      setTimeout(() => this.aoLoadBuyer(), 700);   // profil acheteur (BOAMP, lent) en différé, après le cœur de l'AO
    },
    async aoLoadEstimate() {
      try { const e = await this.api("GET", "/api/chiffrage/" + this.ao.project.id); this.ao.estimate = (e && e.lignes) ? e : null; } catch (e) {}
    },
    async aoEstimate() {
      this.ao.estimateBusy = true; this.ao.estimating = true;
      try {
        this.ao.estimate = await this.api("POST", "/api/chiffrage/" + this.ao.project.id + "/estimate", { distance_km: Number(this.ao.estimateDistance) || 0 });
        this.ao.estimateOpen = true;
      } catch (e) { this.notify(e.message, "err"); } finally { this.ao.estimateBusy = false; this.ao.estimating = false; }
    },
    async aoSaveEstimate() {
      this.ao.estimateBusy = true;
      try {
        this.ao.estimate = await this.api("PUT", "/api/chiffrage/" + this.ao.project.id,
          { lignes: this.ao.estimate.lignes, distance_km: Number(this.ao.estimateDistance) || 0 });
        this.notify("Chiffrage recalculé");
      } catch (e) { this.notify(e.message, "err"); } finally { this.ao.estimateBusy = false; }
    },
    estRateLabels() { return (this.company && this.company.day_rates && this.company.day_rates.length ? this.company.day_rates : [{label:'Étude / conception'},{label:'Production / édition'},{label:'Encadrement / direction'},{label:'Exécution / terrain'}]).map(r => r.label); },
    async aoReview(status) {
      this.ao.estimateBusy = true;
      try {
        this.ao.estimate = await this.api("PUT", "/api/chiffrage/" + this.ao.project.id + "/review", { status, note: this.ao.reviewNote || "" });
        this.ao.reviewNote = "";
        this.notify(status === "valide" ? "Chiffrage validé" : "Révision demandée");
      } catch (e) { this.notify(e.message, "err"); } finally { this.ao.estimateBusy = false; }
    },
    reviewLabel(s) { return { valide: "Validé", revision: "Révision demandée", a_valider: "À valider" }[s] || "Brouillon"; },
    reviewPill(s) { return { valide: "go", revision: "a_etudier", a_valider: "neutral" }[s] || "neutral"; },
    async aoDownloadDpgf() {
      try {
        const r = await fetch("/api/chiffrage/" + this.ao.project.id + "/dpgf", { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("indispo");
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = "DPGF.pdf"; document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) { this.notify("Export DPGF momentanément indisponible.", "err"); }
    },
    async aoLoadBuyer() {
      const name = this.ao.project && this.ao.project.client;
      if (!name) return;
      this.ao.buyerLoading = true;
      try { this.ao.buyer = await this.api("GET", "/api/sourcing/buyer-profile?acheteur=" + encodeURIComponent(name)); }
      catch (e) { this.ao.buyer = null; }
      finally { this.ao.buyerLoading = false; }
    },
    async aoLoadChecklist() {
      try { this.ao.checklist = await this.api("GET", "/api/checklist/" + this.ao.project.id); } catch (e) { this.ao.checklist = null; }
    },
    async aoAsk() {
      const q = (this.ao.qaInput || "").trim();
      if (!q || this.ao.qaLoading) return;
      this.ao.qaLoading = true;
      const entry = { q, a: "__loading__" };
      this.ao.qa.push(entry); this.ao.qaInput = "";
      try {
        const r = await this.api("POST", "/api/sourcing/ask", { project_id: this.ao.project.id, question: q });
        entry.a = r.answer || "—";
      } catch (e) { entry.a = "Erreur : " + e.message; }
      finally { this.ao.qaLoading = false; }
    },
    aoInvoices() { return (this.invoices || []).filter(i => i.project_id === (this.ao.project && this.ao.project.id)); },
    aoTimeline() {
      const p = this.ao.project || {}; const ev = [];
      if (p.created_at) ev.push({ icon: "plus", t: "Appel d'offres créé", d: p.created_at.slice(0, 10) });
      const a = p.ai_analysis;
      if (a) ev.push({ icon: "scan-search", t: a.dce_available ? "DCE analysé (complet)" : "Avis analysé", d: a.match_score != null ? "score " + a.match_score + "/100" : "" });
      const e = this.ao.estimate;
      if (e && e.total_ht) ev.push({ icon: "calculator", t: "Chiffrage estimé", d: this.eur(e.total_ht) + " HT" });
      if (e && e.review && e.review.status === "valide") ev.push({ icon: "circle-check-big", t: "Chiffrage validé" + (e.review.by ? " · " + e.review.by : ""), d: "" });
      if (this.ao.cotraitants.length) ev.push({ icon: "handshake", t: this.ao.cotraitants.length + " co-traitant(s) rattaché(s)", d: "" });
      if (this.ao.dossier) ev.push({ icon: "package", t: "Dossier généré (CERFA + mémoire)", d: "" });
      const nd = (this.ao.documents || []).reduce((s, g) => s + ((g && g.documents || []).length), 0);
      if (nd) ev.push({ icon: "folder", t: nd + " pièce(s) au coffre-fort", d: "" });
      const dl = this.aoDetails().date_limite;
      if (dl) ev.push({ icon: "calendar-clock", t: "Échéance de remise", d: dl });
      return ev;
    },
    async aoLoadCotraitants() {
      try { this.ao.cotraitants = await this.api("GET", "/api/cotraitants/project/" + this.ao.project.id) || []; } catch (e) {}
    },

    // ── Partage co-traitant (lien bridé) + journal d'accès RGPD ──
    async aoLoadInvites() {
      try { this.ao.share.invites = await this.api("GET", "/api/projects/" + this.ao.project.id + "/invites") || []; } catch (e) {}
    },
    inviteUrl(inv) { return window.location.origin + (inv.path || ("/invite/" + inv.token)); },
    inviteState(inv) {
      if (inv.revoked) return { label: "Révoqué", cls: "neutral" };
      if (inv.expires_at && new Date(inv.expires_at) < new Date()) return { label: "Expiré", cls: "a_etudier" };
      return { label: "Actif", cls: "go" };
    },
    async aoCreateInvite() {
      const f = this.ao.share.form;
      this.ao.share.busy = true;
      try {
        const inv = await this.api("POST", "/api/projects/" + this.ao.project.id + "/invites", f);
        this.ao.share.lastUrl = this.inviteUrl(inv);
        this.ao.share.form = { recipient: "", company_name: "", role: "cotraitant", can_view_docs: true, can_contribute: true, expires_days: 30 };
        await this.aoLoadInvites();
        this.copyInvite(this.ao.share.lastUrl, true);
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.share.busy = false; }
    },
    async aoRevokeInvite(inv) {
      if (!confirm("Révoquer ce lien ? Le co-traitant perdra l'accès immédiatement.")) return;
      try { await this.api("DELETE", "/api/projects/" + this.ao.project.id + "/invites/" + inv.id); this.notify("Lien révoqué"); this.aoLoadInvites(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    copyInvite(url, silent) {
      try { navigator.clipboard.writeText(url); if (!silent) this.notify("Lien copié"); else this.notify("Lien généré et copié dans le presse-papier"); }
      catch (e) { if (!silent) this.notify("Copie impossible — sélectionnez le lien manuellement", "err"); }
    },
    async aoToggleAudit() {
      this.ao.share.auditOpen = !this.ao.share.auditOpen;
      if (this.ao.share.auditOpen && !this.ao.share.audit.length) {
        try { this.ao.share.audit = await this.api("GET", "/api/projects/" + this.ao.project.id + "/audit") || []; } catch (e) {}
      }
    },
    async aoLoadContributions() {
      try { this.ao.share.contributions = await this.api("GET", "/api/projects/" + this.ao.project.id + "/contributions") || []; } catch (e) {}
    },
    async aoToggleContrib() {
      this.ao.share.contribOpen = !this.ao.share.contribOpen;
      if (this.ao.share.contribOpen) await this.aoLoadContributions();
    },
    contribCount() { return (this.ao.share.invites || []).filter(i => i.contribution_status === "submitted").length; },
    auditLabel(a) {
      const m = { "invite.created": "Lien créé", "invite.revoked": "Lien révoqué", "guest.view_project": "Consultation du dossier", "guest.download_doc": "Téléchargement de pièce" };
      return m[a.action] || a.action;
    },
    auditWhen(s) { if (!s) return ""; try { return new Date(s).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (e) { return s; } },
    async aoLoadDocs() {
      try { const r = await this.api("GET", "/api/projects/" + this.ao.project.id + "/documents"); this.ao.documents = r.folders || []; } catch (e) {}
    },
    async aoSearchSt() {
      this.ao.st.loading = true; this.ao.st.results = [];
      if (!this.ao.st.dept) this.ao.st.dept = (this.aoDetails().lieu_execution || "").replace(/\D/g, "").slice(0, 2);
      try {
        const r = await this.api("POST", "/api/sourcing/cotraitants",
          { project_id: this.ao.project.id, activity: this.ao.st.trade, departement: this.ao.st.dept });
        this.ao.st.results = r.companies || [];
        if (!this.ao.st.results.length) this.notify("Aucune entreprise trouvée", "err");
      } catch (e) { this.notify(e.message, "err"); } finally { this.ao.st.loading = false; }
    },
    async aoAttachSt(c, role) {
      try {
        await this.api("POST", "/api/cotraitants/project/" + this.ao.project.id,
          { company: c, role: role || this.ao.st.role || "sous_traitant" });
        await this.aoLoadCotraitants(); this.loadCotraitants();
        this.notify(c.nom + " rattaché");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async aoOptimizeGroup() {
      if (!this.ao.group) this.ao.group = { loading: false, data: null };
      this.ao.group.loading = true;
      try {
        this.ao.group.data = await this.api("POST", "/api/sourcing/groupement", { project_id: this.ao.project.id });
        if (this.ao.group.data && !this.ao.group.data.n_lots) this.notify("Marché en lot unique : pas de décomposition possible. Utilisez « Ajouter » pour un co-traitant.");
        else if (this.ao.group.data) this.notify("Groupement optimisé : " + this.ao.group.data.n_lots + " lot(s) analysé(s)");
      }
      catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.group.loading = false; }
    },
    async aoAttachFromGroup(l) {
      if (!l.candidate) return;
      try {
        await this.api("POST", "/api/cotraitants/project/" + this.ao.project.id,
          { company: l.candidate, role: l.role || "cotraitant", lot: "Lot " + l.num });
        await this.aoLoadCotraitants(); this.loadCotraitants();
        this.notify(l.candidate.nom + " rattaché (Lot " + l.num + ")");
      } catch (e) { this.notify(e.message, "err"); }
    },
    roleLabel(r) { return ({ mandataire: "Mandataire", cotraitant: "Co-traitant", sous_traitant: "Sous-traitant" })[r] || r; },
    checklistLabel(s) { return ({ ok: "Disponible", manquant: "Manquant", expire: "Expiré", generable: "Généré auto" })[s] || s; },
    aoStAttached(c) { return this.ao.cotraitants.some(x => x.siret && x.siret === c.siret); },
    async aoDetachSt(link_id) {
      try { await this.api("DELETE", "/api/cotraitants/project/" + this.ao.project.id + "/" + link_id); this.aoLoadCotraitants(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    aoBack() { this.view = this.ao.back || "pipeline"; this.loadProjects(); },
    aoDetails() { return (this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.details) || {}; },
    aoSource() { return (this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.source) || null; },
    aoContact() { const c = this.aoDetails().contact; return (c && (c.nom || c.email)) ? c : null; },
    aoDceAvailable() { return !!(this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.dce_available); },
    aoBreakdown() { const a = this.ao.project && this.ao.project.ai_analysis; return (a && a.dce_available && a.lead_score && a.lead_score.breakdown) || []; },
    async aoStatus() {
      try { await this.api("PUT", "/api/projects/" + this.ao.project.id, { status: this.ao.project.status }); this.notify("Étape mise à jour"); this.loadStats(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    outcomeReasons(status) {
      return status === "gagne"
        ? ["Prix compétitif", "Valeur technique / mémoire", "Références & expérience", "Délai proposé", "Critère RSE / insertion", "Co-traitance / groupement", "Relation acheteur"]
        : ["Prix trop élevé", "Mémoire technique insuffisant", "Références insuffisantes", "Délai non tenable", "Critère RSE non couvert", "Dossier incomplet / hors délai", "Capacité / effectif insuffisant"];
    },
    async aoSaveOutcome() {
      const p = this.ao.project;
      try {
        await this.api("PUT", "/api/projects/" + p.id, {
          outcome_reason: p.outcome_reason || null, outcome_rank: p.outcome_rank || null,
          awarded_amount: p.awarded_amount || null, competitor_winner: p.competitor_winner || null,
        });
        this.notify("Bilan enregistré"); this.loadStats();
      } catch (e) { this.notify(e.message, "err"); }
    },
    async aoGenerate() {
      this.ao.generating = true; this.ao.dossier = null;
      try {
        const r = await this.api("POST", "/api/sourcing/documents", { project_id: this.ao.project.id, cotraitants: [] });
        this.ao.dossier = r.dossier; this.aoLoadDocs();
        this.notify("Documents générés et archivés dans le dossier");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.ao.generating = false; }
    },
    aoDownload() {
      const d = this.ao.dossier; if (!d || !d.zip_b64) return;
      const bin = atob(d.zip_b64), arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      this.saveBlob(new Blob([arr], { type: "application/zip" }), d.zip_name || "dossier.zip");
    },
    async aoUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = ""; this.ao.uploading = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", this.ao.project.id);
        await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        this.ao.project = await this.api("GET", "/api/projects/" + this.ao.project.id);
        this.aoLoadDocs();
        this.notify("DCE analysé — analyse complète ✓");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.ao.uploading = false; }
    },
    async aoExport() {
      try {
        const r = await fetch("/api/export/" + this.ao.project.id, { method: "POST", headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Export impossible");
        this.saveBlob(await r.blob(), "Dossier_AO_" + this.ao.project.id + ".zip");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async aoDelete() {
      const id = this.ao.project.id;
      try { await this.api("DELETE", "/api/projects/" + id); this.aoBack(); this.loadProjects(); this.notifyUndo("Appel d'offres mis à la corbeille", () => this.restoreProject(id)); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async restoreProject(id) {
      try { await this.api("POST", "/api/projects/" + id + "/restore"); this.loadProjects(); this.notify("Restauré"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async updateProjectStatus() {
      try { await this.api("PUT", "/api/projects/" + this.drawer.id, { status: this.drawer.status }); this.notify("Étape mise à jour"); this.loadProjects(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async delProject(p) {
      const id = p.id;
      try { await this.api("DELETE", "/api/projects/" + id); this.drawer = null; this.loadProjects(); this.notifyUndo("Appel d'offres mis à la corbeille", () => this.restoreProject(id)); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async exportDossier(p) {
      this.notify("Génération du dossier…");
      try {
        const r = await fetch("/api/export/" + p.id, { method: "POST", headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Export impossible");
        const blob = await r.blob(); this.saveBlob(blob, "Dossier_AO_" + p.id + ".zip"); this.notify("Dossier téléchargé");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async suggestForProject(p) {
      this.notify("Analyse de co-traitance…");
      try {
        const s = await this.api("POST", "/api/cotraitants/suggest", { project_id: p.id, demo: true });
        this.drawer.suggestion = s; this.notify("Suggestion prête");
      } catch (e) { this.notify(e.message, "err"); }
    },

    // ── Modals (cotraitant / contact / invoice) ──
    openCotraitant(c) { this.modal = { type: "cotraitant", title: c ? "Modifier le co-traitant" : "Nouveau co-traitant", d: c ? { ...c } : { name: "", ca_n1: 0, ca_n2: 0, effectif: 0 } }; },
    openContact(c) { this.modal = { type: "contact", title: c ? "Modifier le contact" : "Nouveau contact", d: c ? { ...c } : { name: "", contact_type: "" } }; },
    openInvoice() { this.modal = { type: "invoice", wide: true, title: "Nouveau document", d: { type: "devis", client_name: "", client_address: "", tva_rate: 20, items: [{ description: "", qty: 1, unit_price: 0 }] } }; },
    async saveModal() {
      this.busy = true;
      try {
        const d = this.modal.d;
        if (this.modal.type === "cotraitant") {
          if (d.id) await this.api("PUT", "/api/cotraitants/" + d.id, d); else await this.api("POST", "/api/cotraitants/", d);
          this.loadCotraitants();
        } else if (this.modal.type === "contact") {
          if (d.id) await this.api("PUT", "/api/contacts/" + d.id, d); else await this.api("POST", "/api/contacts/", d);
          this.loadContacts();
        } else if (this.modal.type === "invoice") {
          await this.api("POST", "/api/invoices/", d); this.loadInvoices();
        }
        this.modal = null; this.notify("Enregistré");
      } catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async delCotraitant(c) { if (!confirm("Supprimer " + c.name + " ?")) return; try { await this.api("DELETE", "/api/cotraitants/" + c.id); this.loadCotraitants(); } catch (e) { this.notify(e.message, "err"); } },
    async delContact(c) { if (!confirm("Supprimer " + c.name + " ?")) return; try { await this.api("DELETE", "/api/contacts/" + c.id); this.loadContacts(); } catch (e) { this.notify(e.message, "err"); } },

    // ── Documents ──
    async uploadDoc(e) {
      const file = e.target.files[0]; if (!file) return;
      const fd = new FormData(); fd.append("file", file); fd.append("name", file.name); fd.append("category", "autre");
      try { await this.api("POST", "/api/documents/", fd, true); this.loadDocuments(); this.notify("Document ajouté"); }
      catch (err) { this.notify(err.message, "err"); }
      e.target.value = "";
    },
    async delDoc(d) { const id = d.id; try { await this.api("DELETE", "/api/documents/" + id); this.loadDocuments(); this.notifyUndo("Document mis à la corbeille", () => this.restoreDoc(id)); } catch (e) { this.notify(e.message, "err"); } },
    async restoreDoc(id) { try { await this.api("POST", "/api/documents/" + id + "/restore"); this.loadDocuments(); this.notify("Restauré"); } catch (e) { this.notify(e.message, "err"); } },
    async downloadDoc(d) {
      try {
        const r = await fetch("/api/documents/" + d.id + "/download", { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Téléchargement impossible");
        this.saveBlob(await r.blob(), d.name || "document");
      } catch (e) { this.notify(e.message, "err"); }
    },

    // ── Veille ──
    async searchVeille() {
      this.veille.loading = true; this.veille.results = [];
      try {
        const qs = "?q=" + encodeURIComponent(this.veille.q) + (this.veille.loc ? "&location=" + encodeURIComponent(this.veille.loc) : "");
        const r = await this.api("GET", "/api/veille/search" + qs);
        this.veille.results = (r && r.results) ? r.results : (Array.isArray(r) ? r : []);
        if (!this.veille.results.length) this.notify("Aucun résultat BOAMP", "err");
      } catch (e) { this.notify(e.message, "err"); } finally { this.veille.loading = false; }
    },

    // ── Agent IA (SSE) ──
    async runAgent() {
      this.ag.running = true; this.ag.log = []; this.ag.gonogo = null; this.ag.coverage = null; this.ag.lots = []; this.ag.dossier = null;
      this.agState = {}; this.agStep = {};
      try {
        const res = await fetch("/api/pipeline/run", {
          method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + this.token },
          body: JSON.stringify({ query: this.ag.query }),
        });
        if (res.status === 402) {
          const d = await res.json().catch(() => ({}));
          this.notify(d.detail || "Quota d'analyses atteint", "err");
          this.ag.running = false; this.loadStats(); this.go("billing"); return;
        }
        if (!res.ok) throw new Error("Erreur " + res.status);
        const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
        while (true) {
          const { value, done } = await reader.read(); if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
            const ln = chunk.split("\n").find(l => l.startsWith("data:"));
            if (ln) { try { this.handleAg(JSON.parse(ln.slice(5).trim())); } catch (e) {} }
          }
        }
      } catch (e) { this.notify(e.message, "err"); } finally { this.ag.running = false; this.loadProjects(); this.loadStats(); }
    },
    handleAg(ev) {
      const { agent, event, data } = ev;
      if (data && data.label) this.ag.log.push({ a: agent, m: data.label });
      if (["agent_start", "step", "error"].includes(event)) { this.agState[agent] = "En cours"; this.agStep[agent] = data.label || ""; }
      if (event === "agent_done") { this.agState[agent] = "Terminé"; this.agStep[agent] = data.label || ""; }
      if (agent === "sourceur" && event === "agent_done") this.ag.gonogo = { decision: data.decision, score: data.score, summary: data.summary };
      if (agent === "groupement" && event === "agent_done") {
        this.ag.lots = data.lots || [];
        const g = data.groupement || {};
        this.ag.coverage = { label: data.label, members: g.membres || [] };
      }
      if (event === "pipeline_complete" && data.dossier) { this.ag.dossier = data.dossier; }
    },
    dlAgentZip() {
      const d = this.ag.dossier; if (!d || !d.zip_b64) return;
      const bin = atob(d.zip_b64); const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      this.saveBlob(new Blob([arr], { type: "application/zip" }), d.zip_name || "dossier.zip");
    },
    agStyle(id) { const s = this.agState[id]; if (s === "Terminé") return "border-color:var(--go)"; if (s === "En cours") return "border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)"; return ""; },
    agPillClass(id) { const s = this.agState[id]; if (s === "Terminé") return "go"; if (s === "En cours") return "a_etudier"; return "st-nouveau"; },

    // ── Dashboard « briefing » ──
    ringStyle(score) {
      if (score == null) return "background:conic-gradient(var(--border-2) 0deg, var(--hairline) 0deg)";
      const deg = Math.max(0, Math.min(100, score)) * 3.6;
      const col = score >= 70 ? "var(--success)" : score >= 45 ? "var(--accent)" : "var(--warning)";
      return `background:conic-gradient(${col} ${deg}deg, var(--hairline) ${deg}deg)`;
    },
    dashTotal() { return Object.values((this.stats && this.stats.by_status) || {}).reduce((a, b) => a + b, 0); },
    dashPct(n) { const t = this.dashTotal(); return t ? Math.max(3, Math.round(n / t * 100)) : 0; },
    dashColor(s) {
      return ({ nouveau: "var(--subtle)", en_cours: "var(--warning)", envoye: "var(--accent)",
                gagne: "var(--success)", perdu: "var(--danger)", abandonne: "var(--border-2)" })[s] || "var(--subtle)";
    },

    // ── Helpers d'affichage ──
    decLabel(d) { return ({ go: "GO", no_go: "NO-GO", a_etudier: "À ÉTUDIER" })[d] || "—"; },
    decColor(d) { return ({ go: "color:var(--go)", no_go: "color:var(--nogo)", a_etudier: "color:var(--warn)" })[d] || "color:var(--muted)"; },
    statusLabel(s) { return ({ nouveau: "Nouveau", en_cours: "En cours", envoye: "Envoyé", gagne: "Gagné", perdu: "Perdu", abandonne: "Abandonné" })[s] || s; },
    covLabel(c) { return ({ entreprise: "Entreprise seule", cotraitant: "Co-traitance", non_couvert: "Non couvert" })[c] || c; },
    covClass(c) { return ({ entreprise: "go", cotraitant: "st-nouveau", non_couvert: "no_go" })[c] || "st-nouveau"; },
    eur(v) {
      v = Number(v) || 0;
      const cur = (this.org.data && this.org.data.devise) || "EUR";
      try { return new Intl.NumberFormat("fr-FR", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(v); }
      catch (e) { return v.toLocaleString("fr-FR") + " €"; }
    },
    kb(b) { return Math.round((Number(b) || 0) / 1024) + " Ko"; },
    avg(...a) { const n = a.map(Number).filter(x => x > 0); return n.length ? n.reduce((s, x) => s + x, 0) / n.length : 0; },
    detailRows(d) {
      const out = {}; const labels = { intitule_marche: "Intitulé", acheteur: "Acheteur", budget_estime: "Budget", date_limite: "Date limite", delai_execution: "Délai", lieu_execution: "Lieu", allotissement: "Allotissement", penalites: "Pénalités", sous_traitance: "Sous-traitance", ca_minimum_requis: "CA minimum", visite_obligatoire: "Visite" };
      for (const k in labels) { if (d[k] && typeof d[k] !== "object") out[labels[k]] = String(d[k]).slice(0, 120); }
      return out;
    },
    clausesRisque(d) { return Array.isArray(d && d.clauses_risque) ? d.clauses_risque : []; },
    niveauPill(n) { return ({ eleve: "no_go", "élevé": "no_go", "élevée": "no_go", moyen: "a_etudier", moyenne: "a_etudier", faible: "go" })[String(n || "").toLowerCase()] || "neutral"; },
    niveauLabel(n) { return ({ eleve: "Élevé", "élevé": "Élevé", moyen: "Moyen", faible: "Faible" })[String(n || "").toLowerCase()] || (n || "—"); },
    async loadCountries() { if (this.countries2.length) return; try { this.countries2 = await this.api("GET", "/api/sourcing/countries"); } catch (e) {} },
    countryName(code) { const c = this.countries2.find(x => x.code === code); return c ? c.nom : code; },
    // ── Veille / alertes AO sauvegardées ──
    async loadAlerts() { try { this.src.alerts = await this.api("GET", "/api/saved-searches/"); } catch (e) {} },
    async srcSaveAlert() {
      const deps = this.srcDeps();
      const countries = this.src.country ? [this.src.country] : [];
      const zone = this.src.country ? this.countryName(this.src.country) : "UE";
      const name = (this.src.query || "Veille") + " · " + zone + (deps.length ? " (" + deps.join("/") + ")" : "");
      try {
        await this.api("POST", "/api/saved-searches/", { name, query: this.src.query, departements: deps, countries, frequency: "quotidienne", active: true });
        this.loadAlerts(); this.notify("Alerte créée — vous serez notifié par email");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async srcRunAlert(a) {
      this.notify("Test de l'alerte…");
      try { const r = await this.api("POST", "/api/saved-searches/" + a.id + "/run"); this.loadAlerts(); this.notify(r.new_matches + " nouvel(s) AO trouvé(s)"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async srcToggleAlert(a) {
      try { await this.api("PUT", "/api/saved-searches/" + a.id, { name: a.name, query: a.query, departements: a.departements, frequency: a.frequency, active: !a.active }); this.loadAlerts(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async srcDelAlert(a) {
      const id = a.id;
      try { await this.api("DELETE", "/api/saved-searches/" + id); this.loadAlerts(); this.notify("Alerte supprimée"); }
      catch (e) { this.notify(e.message, "err"); }
    },

    // ── Sourcing IA (flux à la demande, sources officielles) ──
    srcDeps() { return this.src.dept.split(",").map(s => s.trim()).filter(Boolean); },
    srcCpv() { return (this.src.cpv || "").split(/[,\s]+/).map(s => s.trim()).filter(Boolean); },
    srcResetAdv() { this.src.type_marche = ""; this.src.cpv = ""; },
    async srcRenewals() {
      this.src.renewals.loading = true; this.src.renewals.done = false;
      try {
        const r = await this.api("POST", "/api/sourcing/renewals", { query: this.src.query || "travaux", departements: this.srcDeps() });
        this.src.renewals.list = r.renewals || []; this.src.renewals.done = true;
        this.notify(r.count ? (r.count + " marché(s) en fin de contrat détecté(s)") : "Aucune échéance proche sur ce périmètre", r.count ? "ok" : "err");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.renewals.loading = false; }
    },
    async srcSearch() {
      this.src.searching = true; this.src.tenders = []; this.src.errors = []; this.src.analysis = null;
      try {
        const r = await this.api("POST", "/api/sourcing/search",
          { query: this.src.query, departements: this.srcDeps(), countries: this.src.country ? [this.src.country] : [],
            type_marche: this.src.type_marche, cpv: this.srcCpv(), limit: 15 });
        this.src.tenders = r.tenders || []; this.src.errors = r.errors || []; this.src.sources = r.sources_queried || [];
        if (!this.src.tenders.length) this.notify("Aucun appel d'offres trouvé pour ces critères", "err");
      } catch (e) { this.notify(e.message, "err"); } finally { this.src.searching = false; }
    },
    async srcAnalyze(t) {
      this.src.analyzing = true; this.src.chosen = t; this.src.analysis = null;
      this.src.ct.companies = []; this.src.ct.selected = []; this.src.dossier = null;
      try {
        const r = await this.api("POST", "/api/sourcing/analyze", { tender: t });
        this.src.analysis = r; this.src.projectId = r.project_id;
        this.loadProjects(); this.loadStats();
        if (!r.dce_available) this.notify("DCE complet non accessible — analyse fondée sur l'avis publié", "ok");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.src.analyzing = false; }
    },
    async srcUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      if (!this.src.projectId) { this.notify("Analysez d'abord l'avis", "err"); return; }
      this.src.analyzing = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", this.src.projectId);
        const r = await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        this.src.analysis = r; this.loadProjects(); this.loadStats();
        this.notify("DCE analysé — analyse complète ✓");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.analyzing = false; }
    },

    // ── Veille amont (signaux d'investissement) ──
    async loadAmont() {
      try { this.amont.signals = await this.api("GET", "/api/amont/"); } catch (e) {}
      try { this.amont.auto = (await this.api("GET", "/api/amont/auto")).enabled; } catch (e) {}
    },
    async amontToggleAuto() {
      try {
        const r = await this.api("POST", "/api/amont/auto", { enabled: !this.amont.auto });
        this.amont.auto = r.enabled;
        this.notify(r.enabled ? "Veille automatique activée — alertes par email" : "Veille automatique désactivée");
      } catch (e) { this.notify(e.message, "err"); }
    },
    amontToggleRegion(code) {
      const i = this.amont.regions.indexOf(code);
      if (i >= 0) this.amont.regions.splice(i, 1); else this.amont.regions.push(code);
    },
    amontToggleDomaine(d) {
      const i = this.amont.domaines.indexOf(d);
      if (i >= 0) this.amont.domaines.splice(i, 1); else this.amont.domaines.push(d);
    },
    amontDeps() {
      const sel = this.amont.regions;
      if (!sel.length) return [];
      return this.amontRegions.filter(r => sel.includes(r.code)).flatMap(r => r.deps);
    },
    async amontScan() {
      this.amont.scanning = true;
      try {
        const r = await this.api("POST", "/api/amont/scan", { departements: this.amontDeps(), domaines: this.amont.domaines });
        await this.loadAmont();
        if (r.count) this.notify(r.count + " projet(s) détecté(s) sur " + r.scanned + " délibérations");
        else this.notify(r.scanned ? "Aucun nouveau projet (sur " + r.scanned + " délibérations)" : "Sources momentanément indisponibles", r.scanned ? "ok" : "err");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.amont.scanning = false; }
    },
    amontLabel(p) { return ({ pertinent: "Pertinent", a_etudier: "À étudier", faible: "Peu pertinent" })[p] || p; },
    async amontUpload(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      this.amont.uploading = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("domaines", this.amont.domaines.join(","));
        const r = await this.api("POST", "/api/amont/analyze-upload", fd, true);
        await this.loadAmont();
        this.notify(r.count ? (r.count + " projet(s) détecté(s)") : "Aucun projet d'investissement détecté");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.amont.uploading = false; }
    },
    async amontDelete(s) {
      try { await this.api("DELETE", "/api/amont/" + s.id); this.amont.signals = this.amont.signals.filter(x => x.id !== s.id); }
      catch (e) { this.notify(e.message, "err"); }
    },

    // ── Base de connaissances (RAG) ──
    async kbLoad() {
      try { const r = await this.api("GET", "/api/knowledge/"); this.kb.docs = r.docs || []; this.kb.totalChunks = r.total_chunks || 0; }
      catch (e) {}
    },
    kbKindLabel(k) { return ({ memoire: "Mémoire technique", rse: "RSE", methodologie: "Méthodologie", certification: "Certification", reference: "Référence", autre: "Autre" })[k] || k; },
    async kbUpload(e) {
      const files = Array.from(e.target.files || []); if (!files.length) return;
      e.target.value = ""; this.kb.uploading = true;
      let ok = 0;
      try {
        for (const file of files) {
          const fd = new FormData(); fd.append("file", file); fd.append("kind", this.kb.kind);
          try { await this.api("POST", "/api/knowledge/upload", fd, true); ok++; }
          catch (err) { this.notify(file.name + " : " + err.message, "err"); }
        }
        await this.kbLoad();
        if (ok) this.notify(ok + " document(s) ajouté(s) à la base");
      } finally { this.kb.uploading = false; }
    },
    async kbAddText() {
      if ((this.kb.text || "").trim().length < 40) { this.notify("Texte trop court", "err"); return; }
      this.kb.busyText = true;
      try {
        await this.api("POST", "/api/knowledge/text", { name: this.kb.textName || "Texte collé", text: this.kb.text, kind: this.kb.kind });
        this.kb.text = ""; this.kb.textName = ""; await this.kbLoad(); this.notify("Ajouté à la base");
      } catch (e) { this.notify(e.message, "err"); } finally { this.kb.busyText = false; }
    },
    async kbDelete(d) {
      try { await this.api("DELETE", "/api/knowledge/" + d.id); this.kb.docs = this.kb.docs.filter(x => x.id !== d.id); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async kbSearch() {
      if (!(this.kb.searchQ || "").trim()) return;
      try { this.kb.searchRes = await this.api("POST", "/api/knowledge/search", { query: this.kb.searchQ, k: 6 }); }
      catch (e) { this.notify(e.message, "err"); }
    },
    // Attend la fin d'un job asynchrone (génération longue) en interrogeant /api/jobs/{id}
    async pollJob(jobId) {
      for (let i = 0; i < 160; i++) {
        const j = await this.api("GET", "/api/jobs/" + jobId);
        if (j.status === "done") return j.result;
        if (j.status === "error") throw new Error(j.error || "Échec de la génération");
        await new Promise(r => setTimeout(r, 3000));
      }
      throw new Error("Délai dépassé — réessayez");
    },
    async kbMemoire(e) {
      const file = e.target.files[0]; if (!file) return; e.target.value = "";
      if (!this.kb.docs.length) { this.notify("Ajoutez d'abord des documents à votre base", "err"); return; }
      this.kb.memoireLoading = true; this.kb.memoire = null;
      try {
        const fd = new FormData(); fd.append("file", file);
        const job = await this.api("POST", "/api/knowledge/memoire-upload", fd, true);
        this.kb.memoire = await this.pollJob(job.id);
        this.notify("Mémoire généré (" + (this.kb.memoire.n_sections || 0) + " sections)");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.kb.memoireLoading = false; }
    },
    async kbQuestionnaire() {
      const qs = (this.kb.qText || "").split("\n").map(s => s.trim()).filter(Boolean);
      if (!qs.length) { this.notify("Collez vos questions (une par ligne)", "err"); return; }
      this.kb.qLoading = true; this.kb.qResults = null;
      try {
        const job = await this.api("POST", "/api/knowledge/questionnaire", { questions: qs });
        this.kb.qResults = await this.pollJob(job.id);
        this.notify(this.kb.qResults.covered + "/" + this.kb.qResults.count + " réponses trouvées dans votre base");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.kb.qLoading = false; }
    },

    // ── Espace co-traitance (Merged Brain) ──
    async coLoad() {
      try { const r = await this.api("GET", "/api/cospace/"); this.cospace.spaces = r.spaces || []; if (this.cospace.current) { const c = this.cospace.spaces.find(s => s.id === this.cospace.current.id); if (c) this.cospace.current = c; } }
      catch (e) {}
    },
    async coCreate() {
      if (!(this.cospace.newName || "").trim()) { this.notify("Nom de l'espace requis", "err"); return; }
      try {
        const r = await this.api("POST", "/api/cospace/", { name: this.cospace.newName, marche: this.cospace.newMarche });
        this.cospace.newName = ""; this.cospace.newMarche = ""; await this.coLoad(); this.coOpen(r.space); this.notify("Espace créé");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async coOpen(s) {
      try { const r = await this.api("GET", "/api/cospace/" + s.id); this.cospace.current = r.space; this.cospace.memoire = null; this.cospace.lastToken = ""; }
      catch (e) { this.notify(e.message, "err"); }
    },
    async coInvite() {
      if (!this.cospace.current) return;
      if (!(this.cospace.inviteEmail || "").includes("@")) { this.notify("Email invalide", "err"); return; }
      try {
        const r = await this.api("POST", "/api/cospace/" + this.cospace.current.id + "/invite", { email: this.cospace.inviteEmail, role: this.cospace.inviteRole });
        this.cospace.lastToken = r.join_token; this.cospace.inviteEmail = ""; await this.coOpen(this.cospace.current);
        this.notify("Invitation créée — partagez le code");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async coJoin() {
      if (!(this.cospace.joinToken || "").trim()) { this.notify("Collez le code d'invitation", "err"); return; }
      try {
        const r = await this.api("POST", "/api/cospace/join", { token: this.cospace.joinToken.trim() });
        this.cospace.joinToken = ""; await this.coLoad(); if (r.space) this.coOpen(r.space); this.notify("Vous avez rejoint l'espace");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async coDelete(s) {
      try { await this.api("DELETE", "/api/cospace/" + s.id); if (this.cospace.current && this.cospace.current.id === s.id) this.cospace.current = null; await this.coLoad(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    coIsOwner(s) { return s && s.owner_id === this.user.id; },
    async coWarroom() {
      if (!this.cospace.current) return;
      if ((this.cospace.warroomDce || "").trim().length < 60) { this.notify("Collez le DCE (min. 60 caractères)", "err"); return; }
      this.cospace.warroomLoading = true;
      try {
        const job = await this.api("POST", "/api/cospace/" + this.cospace.current.id + "/warroom", { dce_text: this.cospace.warroomDce });
        const r = await this.pollJob(job.id);
        this.cospace.current.warroom = r; this.notify("Pré-répartition générée (" + (r.lots ? r.lots.length : 0) + " lots)");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.cospace.warroomLoading = false; }
    },
    eurMaybe(n) { return (n || n === 0) ? this.eur(n) : "montant estimé n/d"; },
    companyWeb(c) { return "https://www.google.com/search?q=" + encodeURIComponent((c.nom || c.name || "") + " " + (c.ville || c.city || "") + " site officiel contact"); },
    async coMerge() {
      if (!this.cospace.current) return;
      if ((this.cospace.dceText || "").trim().length < 60) { this.notify("Collez le DCE (RC/CCTP) — min. 60 caractères", "err"); return; }
      this.cospace.generating = true; this.cospace.memoire = null;
      try {
        const job = await this.api("POST", "/api/cospace/" + this.cospace.current.id + "/memoire", { dce_text: this.cospace.dceText });
        this.cospace.memoire = await this.pollJob(job.id);
        this.notify("Mémoire fusionné généré (" + (this.cospace.memoire.n_sections || 0) + " sections)");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.cospace.generating = false; }
    },
    async srcCotraitants() {
      this.src.ct.searching = true; this.src.ct.companies = []; this.src.ct.errors = [];
      if (!this.src.ct.dept) this.src.ct.dept = (this.srcDeps()[0] || (this.company.postal_code || "").slice(0, 2));
      try {
        const r = await this.api("POST", "/api/sourcing/cotraitants",
          { project_id: this.src.projectId, activity: this.src.ct.trade, departement: this.src.ct.dept });
        this.src.ct.companies = r.companies || []; this.src.ct.errors = r.errors || [];
        if (!this.src.ct.companies.length) this.notify("Aucune entreprise trouvée", "err");
      } catch (e) { this.notify(e.message, "err"); } finally { this.src.ct.searching = false; }
    },
    srcToggle(c) {
      const i = this.src.ct.selected.findIndex(x => x.siret === c.siret);
      if (i >= 0) this.src.ct.selected.splice(i, 1); else this.src.ct.selected.push(c);
    },
    srcIsSelected(c) { return this.src.ct.selected.some(x => x.siret === c.siret); },
    async srcGenerate() {
      this.src.generating = true; this.src.dossier = null;
      try {
        const r = await this.api("POST", "/api/sourcing/documents",
          { project_id: this.src.projectId, cotraitants: this.src.ct.selected });
        this.src.dossier = r.dossier;
        this.notify(`Dossier généré (${r.cotraitants_verifies} co-traitant(s) SIRET vérifié)`);
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.src.generating = false; }
    },
    srcDownload() {
      const d = this.src.dossier; if (!d || !d.zip_b64) return;
      const bin = atob(d.zip_b64), arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      this.saveBlob(new Blob([arr], { type: "application/zip" }), d.zip_name || "dossier.zip");
    },
    confClass(c) { return c >= 0.8 ? "go" : c >= 0.5 ? "a_etudier" : "neutral"; },
    critStatus(s) { return ({ ok: "go", partiel: "a_etudier", inconnu: "neutral" })[s] || "neutral"; },
    saveBlob(blob, name) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); },
  },
});

// Filet de sécurité : une erreur de rendu dans UNE carte ne doit JAMAIS blanchir toute
// l'app (page blanche). On l'intercepte → Vue conserve le dernier rendu valide au lieu de
// tout démonter, on journalise le détail (diagnostic) et on affiche le message à l'écran.
__adjApp.config.errorHandler = function (err, vm, info) {
  var msg = (err && err.message) ? err.message : String(err);
  try { console.error("[Adjugo] erreur de rendu (" + info + ") :", err); } catch (e) {}
  // Si l'app s'est vidée (Vue démonte la racine sur erreur de rendu), on remplace la page
  // blanche par un message LISIBLE + le détail technique + un bouton recharger. Plus jamais
  // d'écran blanc muet ; et l'erreur exacte est visible (diagnostic).
  try {
    setTimeout(function () {
      var app = document.querySelector("#app");
      if (!app || app.innerHTML.replace(/\s/g, "").length > 60) return;       // app intacte → rien à faire
      if (document.getElementById("adj-crash")) return;
      var safe = String(msg).replace(/[<>&]/g, "").slice(0, 200);
      var d = document.createElement("div");
      d.id = "adj-crash";
      d.style.cssText = "max-width:560px;margin:64px auto;padding:26px;font-family:system-ui,-apple-system,sans-serif;text-align:center;color:#16181d";
      d.innerHTML = '<div style="font-size:36px">⚠️</div>'
        + '<h2 style="margin:10px 0 4px;font-size:19px">Un élément n’a pas pu s’afficher</h2>'
        + '<p style="color:#6b7280;font-size:14px;margin:6px 0 4px">L’application reste intacte — rechargez la page.</p>'
        + '<p style="font-size:12px;color:#9aa0ab;margin:10px 0">Détail : <code style="background:#f1f3f5;padding:2px 6px;border-radius:5px;color:#444">' + safe + '</code></p>'
        + '<button onclick="location.reload()" style="margin-top:14px;padding:10px 20px;border:0;border-radius:9px;background:#3b5bdb;color:#fff;font-weight:600;font-size:14px;cursor:pointer">Recharger</button>';
      document.body.appendChild(d);
    }, 60);
  } catch (e) {}
};

// window.__adjugo = instance racine montée (hook débogage/tests E2E ; mount() retourne le
// proxy en build prod comme dev — état client de l'utilisateur courant uniquement).
window.__adjugo = __adjApp.mount("#app");
