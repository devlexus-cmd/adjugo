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

// État initial de « Partagé avec moi » (vue co-traitant avec compte) — plus de chiffrage_note : prix de vente du lot
// en clair + détail chiffré dans le navigateur (enveloppe), capacités déclarées, signataire, pièces typées.
function _sharedInit(token, mandataire, projectId) {
  return { token: token || "", projectId: projectId || null, project: null, mandataire: mandataire || "", docs: [], status: "", version: 0, busy: false, msg: "", pieces: [], canContribute: true, loading: false, error: "",
           forMember: null, coffre: null, journal: null, journalLoaded: false, conv: _sconvInit(),
           // Vague 4 : vérification du journal par le membre (verdict du serveur, exports JSON / PDF).
           jv: { busy: false, v: null, err: "", live: "", exporting: "" },
           // detailDpgf : lignes de la DPGF rangées dans le même détail chiffré (AdjugoCrypto.packDetail) ;
           // cet écran ne les modifie pas mais les conserve à chaque enregistrement.
           envelope: null, detailClair: "", detailDpgf: null, detailLocked: false, cryptoCtx: null, pendingCode: null, detailLoaded: false,
           upl: { piece_type: "", expiration_date: "" }, vault: { open: false, loading: false, docs: [], needClaim: false, pendingDoc: null },
           contrib: { company_name: "", lot: "", siret: "", forme_juridique: "", address: "", postal_code: "", city: "", quals: "", refs: "", memoire_paragraph: "",
                      prix_lot_ht: "", representant_legal: "", signataire_qualite: "", ca_n1: "", effectif: "", contact: { nom: "", email: "", telephone: "" } } };
}

// État initial de la carte « Répondre à plusieurs ? » (co-traitance v2) — réinitialisé à chaque ouverture de marché.
function _grpInit() {
  return { loading: false, error: "", state: null, besoins: null, selected: [],
           saisi: { name: "", siret: "", ca_n1: null, effectif: null, qualifications: "" }, saisiOpen: false,
           sim: null, simulating: false, retaining: false,
           history: [], historyOpen: false, historyLoading: false, historyLoaded: false, sireneLoading: false };
}

// ── « Monter le groupement » (co-traitance v2, vague 2) ──────────────────────────────
// État de la carte côté chef de file — réinitialisé à chaque ouverture de marché.
function _convInit() {
  return { loading: false, loaded: false, error: "", d: null, f: null, busy: "", live: "", err: "", errCode: "", missing: [],
           errAt: "top", staleReason: "", editOpen: false, textOpen: false, rulesOpen: false, accord: { nom: "", qualite: "", accepte: false, hash: "" } };
}
// Étape 5 « Prêt à déposer » (vague 4) : contrôles GET /groupement/depot, « Marquer déposé ».
function _depotInit() { return { d: null, loading: false, again: false, loaded: false, busy: "", err: "", live: "", pid: null }; }
// Convention vue par un partenaire qui a un compte (« Partagé avec moi », après rattachement du lien).
function _sconvInit() {
  return { loading: false, d: null, error: "", busy: false, live: "", err: "", textOpen: false,
           accord: { nom: "", qualite: "", accepte: false, hash: "" } };
}

// ── Réseau de partenaires (co-traitance v2, vague 3) — contrat : docs/COTRAITANCE_V2_VAGUE3_API.md ──
// État de la vue « Réseau » (Mon profil partenaire · Annuaire · Mon historique · Invitations reçues).
function _reseauInit() {
  return {
    tab: "profil",
    p: { loading: false, loaded: false, error: "", d: null, f: null, busy: "", live: "", err: "", errCode: "", errAt: "", missing: [], consent: false, verifMsgs: [] },
    an: { loading: false, loaded: false, error: "", d: null, page: 1, live: "", f: { metier: "", departement: "", role: "", q: "" } },
    hist: { loading: false, loaded: false, error: "", d: null },
    recues: { loading: false, loaded: false, list: [], busy: "", live: "" },
    fiche: null,
  };
}
// Panneau « Partenaires pour ce marché » (bouton « Qui me complète ? ») — réinitialisé à chaque ouverture de marché.
function _pmInit() { return { loading: false, loaded: false, error: "", d: null, lotBusy: "", live: "" }; }

// Rendu SÛR du texte de la convention (Markdown simple renvoyé par l'API : # titres, - listes,
// **gras**, *italique*). JAMAIS de v-html brut : on échappe TOUT le HTML d'abord, puis on
// applique ce rendu minimal sur le texte échappé. Les valeurs saisies arrivent échappées par le
// serveur (« \* », « \_ », « \# »…) : elles restent du texte littéral. Aucun lien, aucune image,
// aucun attribut venu du texte. L'annexe « - **Membre** — rôle — part : … — prix de vente : … »
// devient un tableau de répartition (même texte, même ordre).
const _MD_PH = { "\\": "", "*": "", "_": "", "`": "", "#": "", "[": "", "]": "" };
const _MD_PH_BACK = {};
Object.keys(_MD_PH).forEach(k => { _MD_PH_BACK[_MD_PH[k]] = k; });
function _escHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function _mdProtect(s) {   // échappements Markdown → marqueurs internes (jamais interprétés)
  return String(s == null ? "" : s).replace(/[-]/g, "").replace(/\\([\\*_`#\[\]])/g, (m, c) => _MD_PH[c]);
}
function _mdInline(prot) {
  let s = _escHtml(prot);
  s = s.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+?)\*/g, "<em>$1</em>");
  return s.replace(/[-]/g, c => _MD_PH_BACK[c]);
}
function _mdCells(line) { return line.replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim()); }
const _convMdCache = new Map();
function convMdToHtml(md) {
  const src = String(md || "");
  if (_convMdCache.has(src)) return _convMdCache.get(src);
  const out = [];
  let list = null, rows = null, table = null, annex = false;
  const flush = (keep) => {
    if (list && keep !== "list") { out.push("<ul>" + list.map(li => "<li>" + li + "</li>").join("") + "</ul>"); list = null; }
    if (rows && keep !== "rows") {
      out.push('<div class="cv-tw"><table class="cv-table cv-rep"><thead><tr><th scope="col">Membre</th><th scope="col">Rôle</th><th scope="col">Part</th><th scope="col">Prix de vente</th></tr></thead><tbody>'
        + rows.map(r => "<tr>" + r.map((c, i) => i === 0 ? '<th scope="row">' + _mdInline(c) + "</th>" : "<td>" + _mdInline(c) + "</td>").join("") + "</tr>").join("")
        + "</tbody></table></div>");
      rows = null;
    }
    if (table && keep !== "table") {
      const head = table[0] || [], body = table.slice(1);
      out.push('<div class="cv-tw"><table class="cv-table"><thead><tr>' + head.map(c => '<th scope="col">' + _mdInline(c) + "</th>").join("")
        + "</tr></thead><tbody>" + body.map(r => "<tr>" + r.map(c => "<td>" + _mdInline(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>");
      table = null;
    }
  };
  src.replace(/\r\n?/g, "\n").split("\n").forEach(raw => {
    const t = _mdProtect(raw).trim();
    if (!t) { flush(); return; }
    let m = t.match(/^(#{1,3})\s+(.+)$/);
    if (m) {
      flush(); const tag = "h" + (m[1].length + 3);
      annex = /^annexe\b/i.test(m[2]);
      out.push("<" + tag + ' class="cv-h">' + _mdInline(m[2]) + "</" + tag + ">");
      return;
    }
    m = t.match(/^[-*]\s+(.+)$/);
    if (m) {
      const a = annex && m[1].match(/^\*\*(.+?)\*\* — (.+?) — part : (.*) — prix de vente : (.*)$/);
      if (a) { flush("rows"); (rows = rows || []).push([a[1], a[2], a[3], a[4]]); }
      else { flush("list"); (list = list || []).push(_mdInline(m[1])); }
      return;
    }
    if (/^\|.*\|$/.test(t)) {
      flush("table");
      if (!/^\|[\s:|-]+\|$/.test(t)) (table = table || []).push(_mdCells(t));
      return;
    }
    flush(); out.push("<p>" + _mdInline(t) + "</p>");
  });
  flush();
  const html = out.join("");
  if (_convMdCache.size > 8) _convMdCache.clear();
  _convMdCache.set(src, html);
  return html;
}
// Les dates du serveur sont en UTC sans fuseau (« 2026-10-08T01:30:10 ») : on l'indique
// explicitement, sinon le navigateur les lirait comme une heure locale.
// Trop de demandes (limite de fréquence côté serveur, réponse 429 sans message en français).
const TOO_MANY_MSG = "Trop de demandes en peu de temps : réessayez dans quelques minutes.";
// Journal vérifiable par chaque membre (co-traitance v2, vague 4) : libellé exact et limites de
// repli (les limites renvoyées par la vérification les remplacent). On ne survend pas la preuve.
const JOURNAL_LABEL = "Journal vérifiable : toute modification ou suppression d'entrée est détectable";
const JOURNAL_LIMITES = [
  "La vérification entrée par entrée est faite par Adjugo ; vous pouvez la compléter hors ligne en comparant deux exports successifs de votre journal.",
  "Les entrées écrites depuis la dernière empreinte quotidienne (moins de 24 h) ne sont couvertes que par l'export que vous avez conservé.",
  "Le journal ne montre jamais l'adresse IP ni l'email des autres membres : leurs entrées sont engagées par un sceau, pas révélées.",
];
function _isoUtc(s) {
  s = String(s || "");
  return (/T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s)) ? s + "Z" : s;
}

const __adjApp = createApp({
  data() {
    return {
      token: localStorage.getItem("adjugo_token") || "",
      theme: localStorage.getItem("adjugo_theme") || "system",
      mobileNav: false,
      user: {}, company: {}, criteria: {}, googleEnabled: false,
      idleLimitMs: 60 * 60 * 1000,   // déconnexion auto après 1 h SANS activité (sécurité appareil partagé/perdu)
      view: "dashboard", navMore: false, busy: false, toast: null, pending: 0, llmInfo: null,
      auth: { mode: "login", email: "", password: "", full_name: "", company_name: "", resetToken: "", sent: false },
      stats: {}, projects: [], cotraitants: [], contacts: [], invoices: [], documents: [], docQuery: "", docSort: "recent", expiring: [],
      notifs: [], notifsOpen: false, notifsSeen: (function(){ try { return localStorage.getItem("adjugo_notifs_seen") || ""; } catch(e){ return ""; } })(),
      consortiums: { consortiums: [], active: 0, partners_total: 0, submitted_total: 0 },
      grpDash: null,   // tableau de bord « Répondre à plusieurs » (vague 4) : GET /api/groupement/tableau-de-bord
      grpDashErr: "",  // échec du chargement : jamais l'état vide « Aucun groupement » à la place
      cdetail: {}, copen: {}, cexport: {}, cpreview: {}, cerror: {},
      shared: [],
      sharedAo: _sharedInit(),
      pieceTypes: [{ k: "kbis", l: "Kbis" }, { k: "fiscale", l: "Attestation fiscale" }, { k: "sociale", l: "Attestation sociale (URSSAF)" }, { k: "assurance", l: "Assurance" }, { k: "rib", l: "RIB" }, { k: "qualification", l: "Qualification" }, { k: "dpgf_lot", l: "DPGF du lot (prix de vente)" }, { k: "autre", l: "Autre" }],
      veille: { q: "", loc: "", results: [], loading: false },
      drawer: null, modal: null, cdlg: null,   // cdlg : confirmation d'une action de la convention
      reseau: _reseauInit(),                  // vue « Réseau » (vague 3)
      rinv: null,                             // modale d'invitation en 1 clic (partenaire du réseau ou entreprise SIRENE)
      reseauSuggest: null, reseauSuggestOff: false,   // suggestion « publiez votre profil » (après inscription / acceptation)
      welcome: { siret: "", busy: false, dismissed: false },   // activation par SIRET (1er lancement)
      ag: { query: "réhabilitation groupe scolaire", running: false, log: [], gonogo: null, coverage: null, lots: [], dossier: null },
      agState: {}, agStep: {},
      agentDefs: [
        { id: "sourceur", ic: "radar", name: "Agent Sourceur", role: "Recherche BOAMP · score selon vos critères · recommandation" },
        { id: "groupement", ic: "handshake", name: "Agent Stratège", role: "Parties non couvertes · partenaires complémentaires" },
        { id: "redacteur", ic: "file-text", name: "Agent Rédacteur", role: "Dossier de présentation · formulaires officiels · dossier ZIP" },
      ],
      statuses: ["nouveau", "en_cours", "envoye", "gagne", "perdu"],
      statuses2: ["nouveau", "en_cours", "envoye", "gagne", "perdu", "abandonne"],
      plan: { plan: "starter" }, org: { data: null, name: "", invite: { email: "", full_name: "" }, lastTemp: null },
      pwd: { current: "", next: "" },
      fb: { open: false, message: "", kind: "idee", busy: false },
      admin: { diag: null, backups: [], busy: false,
               // Profils du réseau à valider (identité) : liste, motif de refus et « remplacer » par demande.
               rv: { list: [], loaded: false, loading: false, error: "", busy: "", explication: "", motif: {}, remplacer: {}, refuser: {} } },
      cookiesOk: (function(){ try { return localStorage.getItem("adjugo_cookies_ok") === "1"; } catch(e){ return true; } })(),
      predepot: [false, false, false, false],
      predepotSteps: [
        "Relisez chaque formulaire officiel et <b>signez</b> (acte d'engagement + déclaration sur l'honneur).",
        "Vérifiez le <b>taux de TVA</b> et les montants du formulaire ATTRI1.",
        "Ajoutez les pièces <b>« manquantes »</b> de la liste (attestations fiscale/sociale, assurances…).",
        "Déposez avant la <b>date limite</b> sur le profil de votre client (Chorus Pro, PLACE, plateforme du marché)."
      ],
      discover: { open: false, trade: "", dept: "", q: "", results: [], loading: false, total: 0 }, trades: [], uploading: false,
      cpvList: [
        {code:"45000000",label:"Travaux de construction"},{code:"45100000",label:"Préparation de chantier"},
        {code:"45110000",label:"Démolition / terrassement"},{code:"45200000",label:"Bâtiment / génie civil"},
        {code:"45210000",label:"Construction de bâtiments"},{code:"45233000",label:"Voirie / routes"},
        {code:"45260000",label:"Couverture / charpente"},{code:"45262500",label:"Maçonnerie"},
        {code:"45300000",label:"Installations du bâtiment"},{code:"45310000",label:"Installation électrique"},
        {code:"45320000",label:"Isolation"},{code:"45330000",label:"Plomberie"},
        {code:"45331000",label:"Chauffage / ventilation / climatisation"},{code:"45400000",label:"Parachèvement de bâtiment"},
        {code:"45410000",label:"Plâtrerie"},{code:"45420000",label:"Menuiserie"},
        {code:"45430000",label:"Revêtements sols et murs"},{code:"45440000",label:"Peinture et vitrerie"},
        {code:"45450000",label:"Autres travaux de finition"},{code:"45500000",label:"Location de matériel de chantier"},
        {code:"50000000",label:"Réparation et entretien"},{code:"71000000",label:"Architecture, ingénierie, études"},
        {code:"71200000",label:"Services d'architecture"},{code:"71300000",label:"Services d'ingénierie"},
        {code:"71400000",label:"Urbanisme / paysage"},{code:"72000000",label:"Services informatiques"},
        {code:"72200000",label:"Développement de logiciels"},{code:"72400000",label:"Services internet"},
        {code:"48000000",label:"Logiciels et systèmes"},{code:"79000000",label:"Services aux entreprises"},
        {code:"79400000",label:"Conseil en gestion"},{code:"79800000",label:"Impression et services connexes"},
        {code:"79341000",label:"Publicité"},{code:"79952000",label:"Organisation d'événements"},
        {code:"80000000",label:"Enseignement et formation"},{code:"85000000",label:"Santé et action sociale"},
        {code:"90000000",label:"Environnement / déchets / assainissement"},{code:"90900000",label:"Nettoyage / hygiène"},
        {code:"77000000",label:"Agriculture / sylviculture / horticulture"},{code:"77300000",label:"Espaces verts (création/entretien)"},
        {code:"55000000",label:"Hôtellerie et restauration"},{code:"55500000",label:"Cantine et traiteur"},
        {code:"60000000",label:"Transport"},{code:"92000000",label:"Culture, loisirs, sport"},
        {code:"92500000",label:"Bibliothèques, archives, musées"},{code:"30000000",label:"Matériel informatique et de bureau"},
        {code:"32000000",label:"Communication / audiovisuel"},{code:"39000000",label:"Mobilier et équipements"},
        {code:"33000000",label:"Équipements médicaux"},{code:"34000000",label:"Véhicules / transport"},
        {code:"22000000",label:"Imprimés et papeterie"},{code:"09000000",label:"Énergie / carburants"},
        {code:"15000000",label:"Produits alimentaires"},
      ],
      countries2: [], adaptedCountries: [], orgCountry: "FR", lang: "fr",
      amont: { signals: [], uploading: false, scanning: false, regions: [], domaines: [], auto: false, pasteOpen: false, pasteText: "", pasting: false },
      amontDomaines: ["bâtiment", "voirie / VRD", "réseaux", "énergie / rénovation énergétique", "espaces verts / aménagement", "numérique / télécom", "équipement", "études / maîtrise d'œuvre"],
      kb: { docs: [], totalChunks: 0, uploading: false, kind: "memoire", text: "", textName: "", busyText: false,
            searchQ: "", searchRes: null, searching: false, qText: "", qResults: null, qLoading: false,
            memoire: null, memoireLoading: false },
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
        offset: 0, hasMore: false, loadingMore: false,
        analyzing: false, analysis: null, projectId: null, chosen: null,
        ct: { trade: "", dept: "", searching: false, companies: [], selected: [], errors: [] },
        generating: false, dossier: null, alerts: [],
        renewals: { list: [], loading: false, done: false },
        searched: false, empty: null, prefilled: false,
        marketEst: null, marketEstBusy: false,
      },
      ao: { project: null, dossier: null, generating: false, uploading: false, back: "dashboard",
            cotraitants: [], stOpen: false, st: { trade: "", dept: "", role: "sous_traitant", loading: false, results: [] },
            documents: [], checklist: null, buyer: null, buyerLoading: false, group: null,
            chkHelp: null, grp: _grpInit(), conv: _convInit(), pm: _pmInit(), depot: _depotInit(),
            qa: [], qaInput: "", qaLoading: false, grilleBusy: "",
            estimate: null, estimateOpen: false, estimateBusy: false, estimating: false, estimateDistance: 0, reviewNote: "",
            share: { open: false, busy: false, invites: [], lastUrl: "", auditOpen: false, audit: [], contributions: [], contribOpen: false, consortium: null, cockpitOpen: false, leadTotal: null, freezing: false, form: { recipient: "", company_name: "", role: "cotraitant", can_view_docs: true, can_contribute: true, expires_days: 30 } } },
      titles: { kb: "Mon savoir-faire", amont: "Projets à venir", dashboard: "Tableau de bord", sourcing: "Trouver des marchés", agent: "Agent IA", pipeline: "Mes marchés", veille: "Trouver des marchés", cotraitants: "Mes partenaires", contacts: "Contacts", documents: "Mes documents", invoices: "Devis & factures", company: "Mon entreprise", criteria: "Mes critères", team: "Équipe", billing: "Abonnement", aodetail: "Le marché", consortiums: "Mes groupements", shared: "Partagé avec moi", sharedao: "Dossier partagé", admin: "Administration", reseau: "Réseau de partenaires" },
      subtitles: { kb: "Déposez vos documents : l'IA s'en sert pour rédiger vos dossiers de présentation et vos réponses", amont: "Détectez les projets des collectivités, des mois avant l'appel d'offres", dashboard: "Vue d'ensemble de votre activité", sourcing: "Sources officielles, traçables — vous validez chaque étape", agent: "3 agents IA orchestrés de la veille au dossier complet", pipeline: "Suivez vos AO étape par étape", veille: "Appels d'offres réels en direct du BOAMP", cotraitants: "Vos partenaires pour répondre en groupement", contacts: "Maîtres d'ouvrage, partenaires, fournisseurs", documents: "Vos pièces administratives centralisées", invoices: "Facturation liée à vos marchés", company: "Informations utilisées dans vos candidatures", criteria: "Pilotez les décisions automatiques de l'agent", team: "Invitez vos collègues à collaborer sur vos dossiers", billing: "Débloquez toute la puissance d'Adjugo", aodetail: "Dossier complet de l'appel d'offres", consortiums: "Vos groupements en cours et leur dossier commun", shared: "Les marchés où d'autres entreprises vous ont invité", sharedao: "Votre part dans le groupement", reseau: "Trouvez des partenaires vérifiés et faites-vous trouver" },
    };
  },
  computed: {
    initials() { return (this.user.full_name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase(); },
    filteredDocuments() {
      // Coffre-fort : recherche (nom/catégorie/dossier/marché lié) + tri. 100% côté client
      // (tous les documents sont déjà chargés), donc instantané et sans appel réseau.
      let list = (this.documents || []).slice();
      const q = (this.docQuery || "").trim().toLowerCase();
      if (q) list = list.filter(d => ((d.name || "") + " " + (d.folder || "") + " " + this.folderLabel(d.folder) + " " + (d.category || "") + " " + (d.project_name || "")).toLowerCase().includes(q));
      const by = {
        recent: (a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")),
        name: (a, b) => String(a.name || "").localeCompare(String(b.name || ""), "fr", { sensitivity: "base" }),
        category: (a, b) => String(a.folder || a.category || "").localeCompare(String(b.folder || b.category || ""), "fr", { sensitivity: "base" }),
        size: (a, b) => (Number(b.file_size) || 0) - (Number(a.file_size) || 0),
        expiry: (a, b) => {            // la plus proche d'abord ; les pièces sans date d'expiration en dernier
          if (!a.expiration_date && !b.expiration_date) return 0;
          if (!a.expiration_date) return 1;
          if (!b.expiration_date) return -1;
          return String(a.expiration_date).localeCompare(String(b.expiration_date));
        },
      }[this.docSort];
      if (by) list.sort(by);
      return list;
    },
    quotaReached() { const u = this.stats.usage; return !!u && u.analyses_remaining <= 0; },
    notifUnseen() { return this.notifs.filter(n => n.at && n.at > this.notifsSeen).length; },
    // Boucle gagné/perdu : synthèse en langage clair de ce que les marchés terminés apprennent.
    // Prudent : on ne conclut que sur des échantillons suffisants (jamais sur 1 marché).
    winInsights() {
      const s = this.stats && this.stats.segments; if (!s || (this.stats.decided || 0) < 3) return [];
      const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const out = [];
      const _bad = (k) => { const v = String(k || "").trim().toLowerCase(); return !v || v === "inconnu" || v === "non précisé" || v === "n/d"; };
      const best = (arr, min = 2) => (arr || []).filter(x => (x.total || 0) >= min && !_bad(x.key)).sort((a, b) => b.win_rate - a.win_rate)[0];
      const bz = best(s.by_zone);
      if (bz && bz.win_rate >= 50) out.push(`Vous gagnez surtout dans le <b>département ${esc(bz.key)}</b> (${bz.win_rate}% de réussite) — ciblez-y vos recherches.`);
      const bt = best(s.by_type);
      if (bt && bt.win_rate >= 50) out.push(`Vos meilleurs résultats : les marchés de <b>${esc(bt.key)}</b> (${bt.win_rate}%).`);
      const grp = (s.by_groupement || []).reduce((m, g) => { m[g.key] = g; return m; }, {});
      if (grp.Groupement && grp.Solo && (grp.Groupement.total || 0) >= 2 && (grp.Solo.total || 0) >= 2 && grp.Groupement.win_rate > grp.Solo.win_rate + 10) {
        out.push(`Vous gagnez plus <b>en groupement</b> (${grp.Groupement.win_rate}%) qu'en solo (${grp.Solo.win_rate}%) — associez-vous plus souvent.`);
      }
      const bp = (s.by_partner || []).filter(p => (p.total || 0) >= 2).sort((a, b) => b.win_rate - a.win_rate)[0];
      if (bp && bp.win_rate >= 60) out.push(`Votre partenaire le plus gagnant : <b>${esc(bp.key)}</b> (${bp.win_rate}% sur ${bp.total} marchés).`);
      const lr = (s.loss_reasons || [])[0];
      if (lr && lr.count >= 2) out.push(`Vous perdez surtout pour : <b>${esc(lr.reason)}</b> (${lr.count} fois) — un levier à travailler.`);
      return out.slice(0, 4);
    },
    // Veille amont mise en avant (dashboard) : les 3 projets les plus pertinents/mûrs.
    topAmont() {
      return [...(this.amont.signals || [])]
        .sort((a, b) => (b.pertinence_score || 0) - (a.pertinence_score || 0) || (b.maturite || 0) - (a.maturite || 0))
        .slice(0, 3);
    },
    predepotDone() { return (this.predepot || []).filter(Boolean).length; },
    onboarding() {
      // Premiers pas : 3 jalons d'activation, dérivés des données réelles du compte.
      const c = this.company || {}, cr = this.criteria || {};
      const profil = !!(c.name && c.siret);
      const criteres = !!((cr.specialites && String(cr.specialites).trim()) || (cr.departements && String(cr.departements).trim()));
      const premier = (this.projects || []).length > 0;
      const steps = [
        { k: "profil", done: profil, label: "Complétez votre profil entreprise", view: "company", cta: "Compléter" },
        { k: "criteres", done: criteres, label: "Définissez vos critères", view: "criteria", cta: "Définir" },
        { k: "premier", done: premier, label: "Lancez votre première recherche d'appel d'offres", view: "sourcing", cta: "Rechercher" },
      ];
      return { steps, done: steps.filter(s => s.done).length, total: steps.length };
    },
    showOnboarding() {
      try { if (localStorage.getItem("adjugo_onboarding_done") === "1") return false; } catch (e) {}
      return this.onboarding.done < this.onboarding.total;
    },
    // Activation par SIRET : écran d'accueil au 1er lancement tant que le profil n'a pas de SIRET.
    showWelcome() {
      if (!this.token || this.welcome.dismissed) return false;
      try { if (localStorage.getItem("adjugo_welcome_done") === "1") return false; } catch (e) {}
      return !!(this.user && this.user.id) && !(this.company && this.company.siret);
    },
  },
  mounted() {
    this.applyTheme();
    // Bulles d'information (i) : au toucher on donne le focus (iOS ne le fait pas pour un
    // bouton), Échap referme, et la bulle est recadrée pour ne jamais sortir de l'écran
    // (à droite comme en bas : elle s'ouvre alors au-dessus de l'icône).
    (function () {
      const fit = (t) => {
        const b = t && t.querySelector(".tip-b"); if (!b) return;
        b.style.translate = ""; b.style.top = ""; b.style.bottom = "";
        if (window.matchMedia && window.matchMedia("(max-width:640px)").matches) return;   // feuille fixe en bas
        let r = b.getBoundingClientRect();
        const vw = document.documentElement.clientWidth, vh = window.innerHeight;
        let dx = 0; if (r.right > vw - 8) dx = vw - 8 - r.right; if (r.left + dx < 8) dx = 8 - r.left;
        if (dx) b.style.translate = Math.round(dx) + "px 0";
        if (r.bottom > vh - 8) { b.style.top = "auto"; b.style.bottom = "calc(100% + 8px)"; }
      };
      const tipOf = (e) => (e.target && e.target.closest) ? e.target.closest(".tip") : null;
      ["mouseover", "focusin"].forEach(ev => document.addEventListener(ev, e => { const t = tipOf(e); if (t) fit(t); }));
      document.addEventListener("click", e => { const t = tipOf(e); if (t) { e.preventDefault(); t.focus(); fit(t); } });
      document.addEventListener("keydown", e => { const a = document.activeElement; if (e.key === "Escape" && a && a.classList && a.classList.contains("tip")) a.blur(); });
    })();
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (this.theme === "system") this.applyTheme(); });
    }
    this.renderIcons();
    // Accessibilité clavier (RGAA) : Échap ferme la modale ouverte ; Entrée/Espace
    // active l'élément de navigation focalisé (les nav-item ne sont pas des <button>).
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { const x = document.querySelector(".overlay .modal-h .x, .drawer .x"); if (x) x.click(); this.fb.open = false; this.notifsOpen = false; }
      const a = document.activeElement;
      if ((e.key === "Enter" || e.key === " ") && a && a.classList && a.classList.contains("nav-item") && !document.querySelector(".overlay, .drawer, .modal-back")) { e.preventDefault(); a.click(); }
    });
    this.$nextTick(() => this._a11y());
    const _rst = new URLSearchParams(location.search).get("reset");
    // Cliquer le lien de réinitialisation est une action EXPLICITE : il prime sur une session
    // déjà ouverte. Sinon, un utilisateur connecté qui clique le lic reçu par email atterrissait
    // dans l'app sans jamais voir le formulaire « Nouveau mot de passe » (le clic semblait inerte).
    if (_rst) { this.auth.mode = "reset"; this.auth.resetToken = _rst; this.token = ""; }
    // Confirmation d'email : le lien reçu par mail ouvre /app?verify=… → on confirme et on retire le param.
    const _vrf = new URLSearchParams(location.search).get("verify");
    if (_vrf) {
      history.replaceState({}, "", this.token ? "/app" : "/");
      this.api("POST", "/api/auth/verify-email", { token: _vrf })
        .then(r => { this.notify(r.message || "Adresse confirmée"); if (this.token) this.api("GET", "/api/auth/me").then(u => this.user = u).catch(() => {}); })
        .catch(e => this.notify(e.message || "Lien de vérification invalide ou expiré", "err"));
    }
    // Connexion Google : retour de l'OAuth → un code à usage unique (60 s) arrive dans le FRAGMENT
    // (#gcode=…, jamais envoyé au serveur ni dans le Referer) et s'échange contre le jeton par POST
    // plus bas : le jeton de session ne passe jamais dans une URL. Erreur : ?gerror=.
    const _gc = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("gcode");
    const _ge = new URLSearchParams(location.search).get("gerror");
    let _freshLogin = false;
    if (_gc) { history.replaceState({}, "", "/app"); this.token = ""; _freshLogin = true; }
    else if (_ge) { history.replaceState({}, "", "/"); this.$nextTick(() => this.notify(_ge, "err")); }

    // ── Verrou de session par INACTIVITÉ ──
    // Chaque interaction rafraîchit l'horodatage d'activité. Au retour (nouvelle fenêtre, longtemps
    // après…), si la dernière activité dépasse idleLimitMs → PAS de reconnexion auto : on repasse par
    // l'écran de connexion. Un appareil laissé ouvert ne donne plus accès au compte des heures plus tard.
    const _touch = () => { if (this.token) { try { localStorage.setItem("adjugo_active", String(Date.now())); } catch (e) {} } };
    ["click", "keydown", "touchstart"].forEach(ev => window.addEventListener(ev, _touch, { passive: true }));
    const _idleStale = () => { const l = parseInt(localStorage.getItem("adjugo_active") || "0", 10); return !!(l && (Date.now() - l) > this.idleLimitMs); };
    setInterval(() => { if (this.token && _idleStale()) { this.notify("Déconnecté par sécurité après une période d'inactivité.", "err"); this.logout(); } }, 60000);
    // Session STOCKÉE (pas une connexion fraîche) trop ancienne → on l'efface, retour à l'écran de connexion.
    if (this.token && !_freshLogin && _idleStale()) { localStorage.removeItem("adjugo_token"); this.token = ""; }

    const _oauthCfg = () => this.api("GET", "/api/auth/oauth-config").then(c => this.googleEnabled = !!(c && c.google)).catch(() => {});
    if (!this.token && !_gc) _oauthCfg();
    this._loadAnalytics();
    if (_gc) {
      this.api("POST", "/api/auth/google/exchange", { code: _gc }).then(
        r => { this.token = r.access_token; localStorage.setItem("adjugo_token", this.token); this.boot(); },
        e => { this.notify(e.message || "Connexion Google expirée, réessayez.", "err"); _oauthCfg(); });
    } else if (this.token) this.boot();
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
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = null; }   // réponse non-JSON (ex. 500 « Internal Server Error »)
      if (!r.ok) {
        const d = data && data.detail;
        let msg;
        if (Array.isArray(d) && d.length) {
          // Erreur de validation Pydantic (422) : on extrait un message lisible au lieu
          // d'afficher le JSON brut [{"type":"missing","loc":[...]}] à l'utilisateur.
          // On n'affiche JAMAIS f.input (la valeur saisie renvoyée par le serveur).
          msg = this.validationMsg(d[0]);
        } else if (typeof d === "string") { msg = d; }
        else if (d && d.message) { msg = d.message; }
        else if (r.status === 429) { msg = TOO_MANY_MSG; }   // limite de fréquence (réponse sans « detail »)
        else { msg = r.status >= 500 ? "Erreur serveur, réessayez dans un instant." : "Erreur " + r.status; }
        // Statut et code métier conservés (ex. 409 « deja_generee », 403 « email_non_verifie ») :
        // certains écrans enchaînent une confirmation au lieu d'afficher seulement le message.
        const err = new Error(msg);
        err.status = r.status;
        if (d && typeof d === "object" && !Array.isArray(d)) {
          err.code = d.code || ""; if (Array.isArray(d.missing)) err.missing = d.missing; err.detail = d;
          if (typeof d.profile_id === "string" && /^[0-9a-f]{32}$/.test(d.profile_id)) err.profile_id = d.profile_id;
        }
        throw err;
      }
      return data;
      } finally { this.pending = Math.max(0, this.pending - 1); }
    },
    // Message lisible pour une erreur de validation : nos propres messages (déjà en français)
    // sont repris sans le préfixe technique « Value error, » ; les autres cas reçoivent une
    // phrase simple en français, avec le nom du champ seulement s'il est parlant.
    validationMsg(f) {
      f = f || {};
      const labels = { email: "Adresse e-mail", password: "Mot de passe", full_name: "Nom",
        name: "Nom", company_name: "Entreprise", source_url: "Adresse de l'avis", siret: "SIRET",
        client: "Client", phone: "Téléphone", deadline: "Date limite" };
      const field = Array.isArray(f.loc) ? f.loc[f.loc.length - 1] : "";
      const label = labels[field] || "";
      const type = String(f.type || "");
      const raw = String(f.msg || "").replace(/^(value error|assertion failed)\s*,\s*/i, "").trim();
      if (field === "email" || /email address/i.test(raw)) return "Adresse e-mail invalide.";
      if (type === "value_error" && raw) return raw;
      let txt;
      if (type === "missing") txt = "information obligatoire";
      else if (/too_short/.test(type)) txt = "trop court";
      else if (/too_long/.test(type)) txt = "trop long";
      else if (/int|float|decimal|number|greater|less/.test(type)) txt = "nombre invalide";
      else if (/date|time/.test(type)) txt = "date invalide";
      else txt = "valeur invalide";
      return label ? label + " : " + txt + "." : "Une information saisie est invalide (" + txt + ").";
    },
    notify(msg, kind = "ok") { if (this._toastT) clearTimeout(this._toastT); this.toast = { msg, kind }; this._toastT = setTimeout(() => this.toast = null, Math.min(9000, Math.max(2600, String(msg || "").length * 45))); },
    notifyUndo(msg, undoFn) { if (this._toastT) clearTimeout(this._toastT); this.toast = { msg, kind: "ok", undo: undoFn }; this._toastT = setTimeout(() => this.toast = null, 7000); },
    doUndo() { const t = this.toast; this.toast = null; if (t && t.undo) t.undo(); },

    // ── Auth ──
    async submitAuth() {
      if (this.auth.mode === "register" && (this.auth.password || "").length < 8) {
        this.notify("Le mot de passe doit faire au moins 8 caractères", "err"); return;
      }
      this.busy = true;
      try {
        const path = this.auth.mode === "login" ? "/api/auth/login" : "/api/auth/register";
        const body = this.auth.mode === "login"
          ? { email: this.auth.email, password: this.auth.password }
          : { email: this.auth.email, password: this.auth.password, full_name: this.auth.full_name, company_name: this.auth.company_name };
        const res = await this.api("POST", path, body);
        this.token = res.access_token; localStorage.setItem("adjugo_token", this.token);
        if (res && res.suggest_profile) this._rnSuggest(res.suggest_profile);
        await this.boot();
      } catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async forgotPassword() {
      if (!this.auth.email) { this.notify("Entrez votre email", "err"); return; }
      this.busy = true;
      try {
        const r = await this.api("POST", "/api/auth/forgot-password", { email: this.auth.email });
        this.auth.sent = true; this.notify(r.message || "Email envoyé si le compte existe");
      } catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    googleLogin() { window.location.href = "/api/auth/google/login"; },
    async resendVerification() {
      try { const r = await this.api("POST", "/api/auth/resend-verification"); this.notify(r.message || "Email de confirmation renvoyé"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async resetPassword() {
      if ((this.auth.password || "").length < 8) { this.notify("Mot de passe : 8 caractères minimum", "err"); return; }
      this.busy = true;
      try {
        const res = await this.api("POST", "/api/auth/reset-password", { token: this.auth.resetToken, new_password: this.auth.password });
        this.token = res.access_token; localStorage.setItem("adjugo_token", this.token);
        history.replaceState({}, "", "/app");
        this.notify("Mot de passe réinitialisé"); await this.boot();
      } catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    logout() { localStorage.removeItem("adjugo_token"); localStorage.removeItem("adjugo_active"); window.location.href = "/"; },
    dismissOnboarding() { try { localStorage.setItem("adjugo_onboarding_done", "1"); } catch (e) {} this.$forceUpdate(); },
    // ── Feedback in-app ──
    openFeedback() { this.fb.open = true; this.fb.message = ""; this.fb.kind = "idee"; },
    async sendFeedback() {
      if ((this.fb.message || "").trim().length < 2) { this.notify("Écrivez votre message", "err"); return; }
      this.fb.busy = true;
      try {
        const r = await this.api("POST", "/api/feedback", { message: this.fb.message, kind: this.fb.kind, page: this.view });
        this.fb.open = false; this.notify(r.message || "Merci pour votre retour !");
      } catch (e) { this.notify(e.message, "err"); } finally { this.fb.busy = false; }
    },
    // ── RGPD : export + suppression ──
    async rgpdExport() {
      try {
        const r = await fetch("/api/rgpd/export", { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Export indisponible");
        this.saveBlob(await r.blob(), "mes_donnees_adjugo.json"); this.notify("Export téléchargé");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async rgpdDelete() {
      const pw = window.prompt("Suppression DÉFINITIVE de votre compte et de toutes vos données.\nEntrez votre mot de passe pour confirmer :");
      if (!pw) return;
      const cf = window.prompt("Tapez SUPPRIMER en majuscules pour confirmer définitivement :");
      if ((cf || "").trim().toUpperCase() !== "SUPPRIMER") { this.notify("Suppression annulée", "err"); return; }
      try {
        await this.api("POST", "/api/rgpd/delete-account", { password: pw, confirm: "SUPPRIMER" });
        localStorage.removeItem("adjugo_token"); this.notify("Compte supprimé"); setTimeout(() => window.location.href = "/", 1200);
      } catch (e) { this.notify(e.message, "err"); }
    },
    acceptCookies() { try { localStorage.setItem("adjugo_cookies_ok", "1"); } catch (e) {} this.cookiesOk = true; },
    async _loadAnalytics() {
      // Analytics produit cookieless (ex. Plausible), activé par variable d'env serveur.
      try {
        const cfg = await this.api("GET", "/api/public-config");
        if (cfg && cfg.analytics_src && !document.getElementById("adj-analytics")) {
          const s = document.createElement("script");
          s.id = "adj-analytics"; s.defer = true; s.src = cfg.analytics_src;
          if (cfg.analytics_domain) s.setAttribute("data-domain", cfg.analytics_domain);
          document.head.appendChild(s);
        }
      } catch (e) {}
    },

    async boot() {
      try { localStorage.setItem("adjugo_active", String(Date.now())); } catch (e) {}   // toute connexion réussie = activité (réarme le verrou d'inactivité)
      try { this.user = await this.api("GET", "/api/auth/me"); } catch (e) { return; }
      await Promise.all([this.loadCompany(), this.loadCriteria(), this.loadProjects(), this.loadCotraitants(), this.loadStats(), this.loadOrg(), this.loadAdaptedCountries(), this.loadAmont(), this.loadNotifs(), this.loadConsortiums(), this.loadShared(), this.loadGrpDash()]);
      // Adaptation au pays de l'organisation : scope AO + devise + LANGUE par défaut
      if (this.org.data && this.org.data.country) { this.src.country = this.org.data.country; this.orgCountry = this.org.data.country; this.applyLang(this.org.data.lang); }
      this.go("dashboard");
      try {   // posée par invite.html juste avant la redirection « Accepter depuis mon compte »
        const raw = sessionStorage.getItem("adjugo_suggest_profile");
        if (raw) { sessionStorage.removeItem("adjugo_suggest_profile"); this._rnSuggest(JSON.parse(raw)); }
      } catch (e) {}
      this.rnLoadRecues(true);   // pastille « Invitations reçues » du menu Réseau
      // Arrivée depuis un lien d'invitation « ouvert dans mon Adjugo » → ouvre le dossier partagé
      try {
        const st = new URLSearchParams(location.search).get("shared");
        if (st) { history.replaceState({}, "", "/app"); const it = this.shared.find(s => s.token === st); if (it) this.openShared(it); else this.go("shared"); }
      } catch (e) {}
    },

    // ── Navigation + lazy loads ──
    go(v) {
      this.view = v;
      this.mobileNav = false;  // referme le menu mobile à la navigation
      this.notifsOpen = false; this.fb.open = false;  // referme les popups (notifications / retour d'avis) à la navigation
      if (v === "dashboard") { this.loadStats(); this.loadExpiring(); this.loadConsortiums(); this.loadNotifs(); this.loadGrpDash(); }
      if (v === "consortiums") this.loadConsortiums();
      if (v === "pipeline") this.loadProjects();
      if (v === "contacts") this.loadContacts();
      if (v === "invoices") this.loadInvoices();
      if (v === "documents") this.loadDocuments();
      if (v === "cotraitants") { this.loadCotraitants(); this.loadTrades(); }
      if (v === "agent") this.loadStats();
      if (v === "sourcing") { this.loadTrades(); this.loadAlerts(); this.loadCountries(); this.loadStats(); this.srcPrefillFromProfile(); }
      if (v === "amont") this.loadAmont();
      if (v === "kb") this.kbLoad();
      if (v === "team") this.loadOrg();
      if (v === "billing") { this.loadPlan(); this.loadStats(); }
      if (v === "admin") this.loadAdmin();
      if (v === "reseau") { this.rnGo(this.reseau.tab || "profil"); this.rnLoadRecues(true); }
      this.$nextTick(() => { const w = document.querySelector(".work"); if (w) w.scrollTop = 0; });   // remonte en haut du contenu à chaque changement de vue
    },
    async loadAdmin() {
      this.adminRvLoad();
      try { this.admin.diag = await this.api("GET", "/api/admin/storage-diag"); } catch (e) { this.admin.diag = null; }
      try { this.admin.backups = (await this.api("GET", "/api/admin/backups")).backups || []; } catch (e) { this.admin.backups = []; }
    },
    // Réseau : demandes de publication à valider (identité de l'entreprise). Le serveur fournit
    // l'identité SIRENE, le nom et l'email du compte, et les conflits de SIREN ; rien n'est déduit ici.
    async adminRvLoad() {
      const rv = this.admin.rv; if (rv.loading) return;
      rv.loading = true; rv.error = "";
      try {
        const d = await this.api("GET", "/api/admin/reseau/validations");
        rv.list = (d && d.en_attente) || []; rv.explication = (d && d.explication) || ""; rv.loaded = true;
      } catch (e) { rv.error = (e && e.message) || "Liste momentanément indisponible."; }
      finally { rv.loading = false; }
    },
    adminRvPublished(it) { return ((it && it.conflits) || []).filter(c => c.statut === "publie"); },
    // Lien vers l'annuaire officiel des entreprises : seulement l'adresse attendue (SIREN à 9 chiffres).
    adminRvLink(it) { const u = String((it && it.sirene && it.sirene.lien_annuaire) || ""); return /^https:\/\/annuaire-entreprises\.data\.gouv\.fr\/entreprise\/\d{9}$/.test(u) ? u : ""; },
    async adminRvValider(it) {
      const rv = this.admin.rv; if (!it || rv.busy) return;
      if (this.adminRvPublished(it).length && !rv.remplacer[it.profile_id]) {
        this.notify("Un autre profil est publié pour ce SIREN : cochez « Retirer l'autre fiche » ou refusez la demande.", "err"); return;
      }
      rv.busy = it.profile_id;
      try {
        const r = await this.api("POST", "/api/admin/reseau/validations/" + encodeURIComponent(it.profile_id) + "/valider", { remplacer: !!rv.remplacer[it.profile_id] });
        this.notify((r && r.message) || "Profil validé.");
        rv.list = rv.list.filter(x => x.profile_id !== it.profile_id);
      } catch (e) { this.notify(e.message, "err"); if (e && e.code === "deja_traitee") rv.list = rv.list.filter(x => x.profile_id !== it.profile_id); }
      finally { rv.busy = ""; }
    },
    async adminRvRefuser(it) {
      const rv = this.admin.rv; if (!it || rv.busy) return;
      const motif = String(rv.motif[it.profile_id] || "").trim();
      if (motif.length < 5) { this.notify("Indiquez le motif du refus : il sera affiché à l'entreprise.", "err"); return; }
      rv.busy = it.profile_id;
      try {
        const r = await this.api("POST", "/api/admin/reseau/validations/" + encodeURIComponent(it.profile_id) + "/refuser", { motif });
        this.notify((r && r.message) || "Demande refusée.");
        rv.list = rv.list.filter(x => x.profile_id !== it.profile_id);
      } catch (e) { this.notify(e.message, "err"); if (e && e.code === "deja_traitee") rv.list = rv.list.filter(x => x.profile_id !== it.profile_id); }
      finally { rv.busy = ""; }
    },
    async adminRunBackup() {
      this.admin.busy = true;
      try {
        const r = await this.api("POST", "/api/admin/run-backup");
        if (r && r.ok) this.notify("Sauvegarde effectuée (" + (r.rows || 0) + " lignes)"); else this.notify("Sauvegarde : " + ((r && r.error) || "ignorée"), "err");
        await this.loadAdmin();
      } catch (e) { this.notify(e.message, "err"); } finally { this.admin.busy = false; }
    },

    // ── Registre entreprises (données réelles) ──
    async loadTrades() { if (this.trades.length) return; try { this.trades = await this.api("GET", "/api/registre/trades"); } catch (e) {} },
    async lookupCompany() {
      const q = (this.company.siret || this.company.name || "").trim();
      if (!q) { this.notify("Saisis un SIRET ou un nom", "err"); return; }
      this.busy = true;
      try {
        const r = await this.api("GET", "/api/registre/company?q=" + encodeURIComponent(q));
        // On COMPLÈTE les champs vides sans ÉCRASER ce que l'utilisateur a déjà saisi (ex.
        // effectif précis remplacé par une tranche SIRENE, adresse de correspondance perdue).
        ["name", "siret", "code_ape", "forme_juridique", "address", "postal_code", "city", "effectif", "tva_intracom"].forEach(k => { if (r[k] && !this.company[k]) this.company[k] = r[k]; });
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
    // ── Activation par SIRET : un champ → profil rempli + critères pré-réglés + marchés ──
    welcomeDone() { this.welcome.dismissed = true; try { localStorage.setItem("adjugo_welcome_done", "1"); } catch (e) {} },
    welcomeSkip() { this.welcomeDone(); },
    async welcomeStart() {
      const q = (this.welcome.siret || "").trim();
      if (!q) { this.notify("Saisissez votre SIRET (14 chiffres)", "err"); return; }
      this.welcome.busy = true;
      try {
        const r = await this.api("GET", "/api/registre/company?q=" + encodeURIComponent(q));
        if (!r || (!r.name && !r.siret)) { this.notify("Entreprise introuvable — vérifiez le SIRET", "err"); return; }
        // 1) Profil entreprise (on n'écrase pas une saisie existante).
        ["name", "siret", "code_ape", "forme_juridique", "address", "postal_code", "city", "effectif", "tva_intracom"].forEach(k => { if (r[k] && !this.company[k]) this.company[k] = r[k]; });
        if (r.dirigeant && !this.company.representant_legal) this.company.representant_legal = r.dirigeant;
        await this.api("PUT", "/api/company/", this.company);
        // 2) Critères pré-réglés : spécialité (dérivée du NAF) + département (du code postal).
        const spec = r.specialite || r.naf_label || "";
        const dep = (r.postal_code || this.company.postal_code || "").slice(0, 2);
        if (spec && !((this.criteria.specialites || "").trim())) this.criteria.specialites = spec;
        if (dep && !((this.criteria.departements || "").trim())) this.criteria.departements = dep;
        try { await this.api("PUT", "/api/criteria/", this.criteria); } catch (e) {}
        // 3) Pré-remplir et lancer la 1re recherche pertinente.
        if (spec && !this.src.query) this.src.query = spec.split(/[ ,;]/)[0];
        if (dep && !this.src.dept) this.src.dept = dep;
        this.welcomeDone();
        this.notify("Profil créé depuis votre SIRET");
        this.go("sourcing");
        this.$nextTick(() => this.srcSearch());
      } catch (e) { this.notify("Entreprise introuvable — vérifiez le SIRET", "err"); }
      finally { this.welcome.busy = false; }
    },
    openDiscover() { this.discover.open = true; this.discover.results = []; this.loadTrades(); if (!this.discover.dept) this.discover.dept = (this.company.postal_code || "").slice(0, 2); },
    amontFindPartners(s) {
      // Pré-AO : constituer le groupement DÈS le signal amont, AVANT la publication de l'AO.
      const trade = (s && s.metiers && s.metiers.length) ? s.metiers[0] : ((s && s.domaine) || "");
      const m = String((s && s.localisation) || "").match(/\b(\d{2})\d{0,3}\b/);
      this.openDiscover();
      this.discover.trade = trade;
      if (m) this.discover.dept = m[1];
    },
    async runDiscover() {
      this.discover.loading = true; this.discover.results = []; this.discover.total = 0;   // sinon l'ancien compteur « N trouvées » survit à une recherche en échec
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
      if (!confirm("Retirer " + (m.full_name || m.email) + " de l'équipe ?\nSes dossiers (AO, contacts…) seront réattribués au propriétaire et son accès coupé immédiatement.")) return;
      try { const r = await this.api("DELETE", "/api/org/members/" + m.id); this.loadOrg(); this.notify(m.full_name + " retiré" + (r && r.reassigned ? " — " + r.reassigned + " élément(s) réattribué(s)" : "")); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async orgSetRole(m, role) {
      try { await this.api("PUT", "/api/org/members/" + m.id + "/role", { role }); this.loadOrg(); this.notify((m.full_name || m.email) + " : " + this.roleLabelOrg(role)); }
      catch (e) { this.notify(e.message, "err"); this.loadOrg(); }
    },
    async orgTransfer(m) {
      if (!confirm("Transférer la PROPRIÉTÉ de l'organisation à " + (m.full_name || m.email) + " ?\nVous deviendrez simple administrateur.")) return;
      try {
        const r = await this.api("POST", "/api/org/transfer-ownership", { new_owner_id: m.id });
        // L'API renvoie un jeton frais (nos sessions ont été révoquées) : on l'adopte AVANT
        // tout autre appel, sinon loadOrg() partait avec l'ancien jeton → 401 → logout brutal.
        if (r && r.access_token) { this.token = r.access_token; localStorage.setItem("adjugo_token", r.access_token); }
        this.loadOrg(); this.notify("Propriété transférée à " + (m.full_name || m.email));
      } catch (e) { this.notify(e.message, "err"); }
    },
    async changePassword() {
      if (!this.pwd.current || !this.pwd.next) { this.notify("Renseignez les deux champs", "err"); return; }
      if ((this.pwd.next || "").length < 8) { this.notify("Le nouveau mot de passe doit faire au moins 8 caractères", "err"); return; }
      try {
        const r = await this.api("POST", "/api/auth/change-password", { current_password: this.pwd.current, new_password: this.pwd.next });
        if (r && r.access_token) { this.token = r.access_token; localStorage.setItem("adjugo_token", r.access_token); }
        this.pwd = { current: "", next: "" }; this.notify("Mot de passe changé");
      } catch (e) { this.notify(e.message, "err"); }
    },
    // Paiement à l'usage : réservé à un abonnement payant actif (le serveur le revérifie).
    overageAvailable() { const u = this.stats && this.stats.usage; return !!u && (u.plan === "pro" || u.plan === "business"); },
    async toggleOverage() {
      const on = !(this.stats.usage && this.stats.usage.overage_enabled);
      if (on && !this.overageAvailable()) { this.notify("Disponible avec un abonnement Pro ou Business", "err"); return; }
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
    async convertInvoice(i) {
      if (!confirm("Créer une facture à partir du devis " + i.reference + " ?")) return;
      try { const f = await this.api("POST", "/api/invoices/" + i.id + "/convert"); await this.loadInvoices(); this.notify("Facture " + (f && f.reference || "") + " créée"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async loadDocuments() { try { this.documents = await this.api("GET", "/api/documents/") || []; } catch (e) {} },
    async loadExpiring() { try { this.expiring = await this.api("GET", "/api/documents/expiring") || []; } catch (e) { this.expiring = []; } },
    async loadCompany() { try { const c = await this.api("GET", "/api/company/"); if (c && !c.detail) this.company = c; } catch (e) {} },
    async loadLlmInfo() { try { this.llmInfo = await this.api("GET", "/api/llm/info"); } catch (e) {} },
    async loadCriteria() { try { this.criteria = await this.api("GET", "/api/criteria/") || {}; } catch (e) {} },

    // ── Company / Criteria ──
    async saveCompany() {
      if (!(this.company.name || "").trim()) { this.notify("Indiquez le nom de votre entreprise (Dénomination)", "err"); return; }
      this.busy = true;
      try { await this.api("PUT", "/api/company/", this.company); this.notify("Profil enregistré"); }
      catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async saveCriteria() {
      const go = Number(this.criteria.go_threshold), ng = Number(this.criteria.nogo_threshold);
      if (go && ng && go <= ng) { this.notify("Le seuil « bon potentiel » doit être supérieur au seuil « peu adapté »", "err"); return; }
      const bmin = Number(this.criteria.budget_min), bmax = Number(this.criteria.budget_max);
      if (bmin && bmax && bmin > bmax) { this.notify("Le budget minimum doit être inférieur au budget maximum", "err"); return; }
      this.busy = true;
      // Un champ numérique vidé arrive en "" → on l'envoie en null (le backend garde le défaut au lieu de refuser).
      const payload = {};
      for (const [k, v] of Object.entries(this.criteria || {})) payload[k] = (v === "" || (typeof v === "number" && Number.isNaN(v))) ? null : v;
      try { await this.api("PUT", "/api/criteria/", payload); this.notify("Critères enregistrés"); }
      catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    // ── Garde-fou critères + résolution des libellés CPV ──
    criteriaEmpty() {
      const cr = this.criteria || {};
      const has = k => cr[k] && String(cr[k]).trim();
      return !(has('specialites') || has('codes_cpv') || has('qualifications') || has('departements'));
    },
    gateCriteria() {
      // true = on continue ; false = on a renvoyé l'utilisateur vers ses critères.
      if (!this.criteriaEmpty()) return true;
      const ok = confirm("Vous n'avez pas encore renseigné vos critères (vos spécialités, votre zone géographique…).\n\nPour une analyse vraiment adaptée à votre entreprise, mieux vaut les définir d'abord.\n\nAller à « Mes critères » maintenant ?");
      if (ok) { this.go('criteria'); return false; }
      return true;
    },
    cpvLabels(str) {
      const codes = (str || "").split(/[ ,;]+/).map(s => s.trim().replace(/\D/g, "")).filter(Boolean);
      return codes.map(code => {
        if (code.length < 8) return code + " — (tapez les 8 chiffres)";
        let hit = (this.cpvList || []).find(c => c.code === code);
        if (!hit) hit = (this.cpvList || []).find(c => code.slice(0, 2) === c.code.slice(0, 2));
        return hit ? code + " — " + hit.label : code + " — (libellé inconnu)";
      });
    },

    // ── Projects (kanban + page détaillée AO) ──
    byStatus(s) { return this.projects.filter(p => (p.status || "nouveau") === s); },
    openProject(p) { this.openAo(p); },
    async openAo(p) {
      this.ao.back = this.view; this.ao.dossier = null; this.ao.project = p;
      this.ao.cotraitants = []; this.ao.stOpen = false; this.ao.st.results = [];
      this.view = "aodetail"; this.loadTrades(); this.ao.documents = []; this.ao.buyer = null; this.ao.buyerLoading = true; this.ao.checklist = null; this.ao.group = null;
      this.ao.qa = []; this.ao.qaInput = ""; this.ao.grilleBusy = ""; this.ao.grp = _grpInit(); this.ao.conv = _convInit(); this.ao.pm = _pmInit(); this.ao.depot = _depotInit(); this.rinv = null;
      this.ao.estimate = null; this.ao.estimateOpen = false; this.ao.estimateDistance = 0;
      this.ao.share = { open: false, busy: false, invites: [], lastUrl: "", auditOpen: false, audit: [], contributions: [], contribOpen: false, consortium: null, cockpitOpen: false, leadTotal: null, freezing: false, form: { recipient: "", company_name: "", role: "cotraitant", can_view_docs: true, can_contribute: true, expires_days: 30 } };
      try { this.ao.project = await this.api("GET", "/api/projects/" + p.id); } catch (e) {}
      this.loadPredepot(p.id);   // état du wizard pré-dépôt propre à cet AO
      this.aoLoadCotraitants(); this.aoLoadDocs(); this.aoLoadChecklist(); this.loadInvoices(); this.aoLoadEstimate(); this.aoLoadInvites(); this.aoLoadConsortium(); this.aoGrpLoad();
      setTimeout(() => this.aoLoadBuyer(), 700);   // profil acheteur (BOAMP, lent) en différé, après le cœur de l'AO
    },
    loadPredepot(pid) {
      try { const v = JSON.parse(localStorage.getItem("adjugo_predepot_" + pid) || "null"); this.predepot = Array.isArray(v) && v.length === 4 ? v : [false, false, false, false]; }
      catch (e) { this.predepot = [false, false, false, false]; }
    },
    savePredepot() {
      try { if (this.ao.project) localStorage.setItem("adjugo_predepot_" + this.ao.project.id, JSON.stringify(this.predepot)); } catch (e) {}
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
        this.notify("Estimation recalculée");
      } catch (e) { this.notify(e.message, "err"); } finally { this.ao.estimateBusy = false; }
    },
    estRateLabels() { return (this.company && this.company.day_rates && this.company.day_rates.length ? this.company.day_rates : [{label:'Étude / conception'},{label:'Production / édition'},{label:'Encadrement / direction'},{label:'Exécution / terrain'}]).map(r => r.label); },
    async aoReview(status) {
      this.ao.estimateBusy = true;
      try {
        this.ao.estimate = await this.api("PUT", "/api/chiffrage/" + this.ao.project.id + "/review", { status, note: this.ao.reviewNote || "" });
        this.ao.reviewNote = "";
        this.notify(status === "valide" ? "Estimation validée" : "Révision demandée");
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
      if (p.created_at) ev.push({ icon: "plus", t: "Marché ajouté", d: this.fmtDate(p.created_at) });
      const a = p.ai_analysis;
      if (a) ev.push({ icon: "scan-search", t: a.dce_available ? "Dossier analysé (complet)" : "Annonce analysée", d: a.match_score != null ? "compatibilité " + a.match_score + "/100" : "" });
      const e = this.ao.estimate;
      if (e && e.total_ht) ev.push({ icon: "calculator", t: "Estimation du prix", d: this.eur(e.total_ht) + " HT" });
      if (e && e.review && e.review.status === "valide") ev.push({ icon: "circle-check-big", t: "Estimation validée" + (e.review.by ? " · " + e.review.by : ""), d: "" });
      if (this.ao.cotraitants.length) ev.push({ icon: "handshake", t: this.ao.cotraitants.length + " partenaire(s) rattaché(s)", d: "" });
      if (this.ao.dossier) ev.push({ icon: "package", t: "Documents préparés (formulaires + présentation)", d: "" });
      const nd = (this.ao.documents || []).reduce((s, g) => s + ((g && g.documents || []).length), 0);
      if (nd) ev.push({ icon: "folder", t: nd + " pièce(s) dans mes documents", d: "" });
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
    async aoLoadConsortium() {
      try { this.ao.share.consortium = await this.api("GET", "/api/projects/" + this.ao.project.id + "/consortium"); } catch (e) { this.ao.share.consortium = null; }
    },
    async aoToggleCockpit() {
      this.ao.share.cockpitOpen = !this.ao.share.cockpitOpen;
      if (this.ao.share.cockpitOpen) await this.aoLoadConsortium();
    },

    async loadConsortiums() { try { this.consortiums = await this.api("GET", "/api/consortiums") || this.consortiums; } catch (e) {} },
    // ── Tableau de bord « Répondre à plusieurs » (vague 4) ──
    // Données réelles de l'organisation (serveur) : marchés accessibles en groupement, groupements
    // en cours par étape 1→5, déposés. Aucun montant ; un seul pourcentage : le score de groupement.
    async loadGrpDash() {
      try { this.grpDash = await this.api("GET", "/api/groupement/tableau-de-bord"); this.grpDashErr = ""; }
      catch (e) { this.grpDashErr = (e && e.message) || "erreur"; }   // on garde les dernières données reçues
    },
    // État de la carte : chargement, erreur, rien du tout, seulement des groupements déposés, ou une liste.
    grpDashState() {
      const g = this.grpDash;
      if (!g) return this.grpDashErr ? "erreur" : "chargement";
      if (this.grpDashItems().length) return "liste";
      if (g.deposes) return "deposes";
      if (!g.marches_accessibles_en_groupement && !g.groupements_en_cours) return "vide";
      return "rien_a_lister";
    },
    grpDashHasAny() { const g = this.grpDash; return !!(g && (g.marches_accessibles_en_groupement || g.groupements_en_cours || g.deposes)); },
    grpDashItems() {
      const g = this.grpDash; if (!g) return [];
      const parts = {}; ((this.consortiums && this.consortiums.consortiums) || []).forEach(c => { parts[c.project_id] = c; });
      const lim = (d) => d ? "limite " + this.fmtDate(d) : "";
      const seen = new Set((g.en_cours || []).map(it => it.project_id)), out = [];   // TOUS les en cours, pas seulement les 5 listés
      (g.en_cours || []).slice(0, 5).forEach(it => {
        const cs = parts[it.project_id];
        const bits = [it.label, cs && cs.partners ? cs.submitted + "/" + cs.partners + " " + this.pl(cs.partners, "part reçue", "parts reçues") : "", lim(it.deadline)].filter(Boolean);
        out.push({ project_id: it.project_id, name: it.name || "Appel d'offres", meta: bits.join(" · "), badge: "Étape " + it.etape + " sur 5", pill: "neutral" });
      });
      (g.accessibles || []).filter(a => !seen.has(a.project_id)).slice(0, 3).forEach(a => {
        out.push({ project_id: a.project_id, name: a.name || "Appel d'offres", meta: ["Repérer le marché", lim(a.deadline)].filter(Boolean).join(" · "),
                   badge: a.groupement_score != null ? "Avec partenaires : " + a.groupement_score + " %" : "Bon potentiel en groupement", pill: "go_groupement" });
      });
      return out;
    },

    // ── Espace « Mes consortiums » (hub central) ──
    async toggleConsortium(pid) {
      this.copen[pid] = !this.copen[pid];
      if (this.copen[pid] && !this.cdetail[pid]) {
        this.cerror[pid] = "";
        try { this.cdetail[pid] = await this.api("GET", "/api/projects/" + pid + "/consortium"); }
        catch (e) { this.cerror[pid] = e.message || "Échec du chargement du compte-rendu"; }   // sinon spinner infini
      }
    },
    async retryConsortium(pid) {
      this.cerror[pid] = ""; this.cdetail[pid] = null;
      try { this.cdetail[pid] = await this.api("GET", "/api/projects/" + pid + "/consortium"); }
      catch (e) { this.cerror[pid] = e.message || "Échec du chargement du compte-rendu"; }
    },
    async exportConsortium(pid) {
      this.cexport[pid] = true;
      this.notify("Assemblage du dossier commun (présentation fusionnée + pièces des partenaires)…");
      try {
        const r = await this.api("POST", "/api/sourcing/documents", { project_id: pid, cotraitants: [] });
        if (r.dossier && r.dossier.zip_b64) {
          this._downloadB64(r.dossier.zip_b64, r.dossier.zip_name);
          // Téléchargé sans passer par la fiche du marché : le point bloquant (dossier de présentation
          // coupé ou non rédigé, passages à compléter) est dit tout de suite, jamais tu.
          const ws = r.dossier.warnings || [];
          const w = ws.find(x => x.startsWith("BLOQUANT")) || ws.find(x => x.startsWith("Dossier de présentation"));
          if (w) this.notify("Dossier commun exporté. À traiter avant le dépôt : " + w.replace(/^BLOQUANT — /, ""), "err");
          else this.notify("Dossier commun exporté");
        }
        else this.notify("Rien à exporter pour ce groupement", "err");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.cexport[pid] = false; }
    },
    async dossierPreview(pid) {
      if (this.cpreview[pid]) { this.cpreview[pid] = null; return; }   // re-clic = replier
      try { this.cpreview[pid] = await this.api("GET", "/api/projects/" + pid + "/dossier-preview"); } catch (e) { this.notify("Aperçu indisponible", "err"); }
    },
    async consortiumReportPdf(pid) {
      try {
        const r = await fetch("/api/projects/" + pid + "/consortium/report", { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("indispo");
        this.saveBlob(await r.blob(), "Compte-rendu_interne_groupement.pdf");
        this.notify("Compte-rendu interne téléchargé (document du chef de file, pas pour l'acheteur)");
      } catch (e) { this.notify("Compte-rendu indisponible", "err"); }
    },

    // ── Partagé avec moi (compte-à-compte) : je contribue à un AO d'un autre mandataire ──
    async loadShared() { try { this.shared = await this.api("GET", "/api/shared") || []; } catch (e) { this.shared = []; } },
    async openShared(item) {
      const t = item.token;
      this.sharedAo = _sharedInit(t, item.mandataire, item.project_id); this.sharedAo.loading = true;
      this.view = "sharedao";
      try {
        const v = await this.api("GET", "/api/invite/" + t);
        this.sharedAo.project = v.project; this.sharedAo.mandataire = v.mandataire; this.sharedAo.docs = v.documents || []; this.sharedAo.canContribute = v.can_contribute;
        this.sharedAo.forMember = v.for_member || null;   // « Pourquoi vous » : % commun, mon apport, seuils — jamais le score seul du mandataire
        if (v.can_contribute) await this.sharedReload(t);
        this.sharedLoadCoffre(); this.sharedConvLoad();
      } catch (e) { this.sharedAo.error = "Ce dossier n'est plus accessible (lien expiré, décliné ou révoqué)."; this.notify("Ce dossier n'est plus accessible", "err"); }
      finally { this.sharedAo.loading = false; }
    },
    sfm() { return this.sharedAo.forMember || {}; },
    sfmState() { return (this.sharedAo.forMember && this.sharedAo.forMember.state) || {}; },
    memberStatusLabel(s) { return ({ submitted: "part soumise", draft: "brouillon", invited: "invité" })[s] || s || ""; },
    cryptoLabels() { return (window.AdjugoCrypto && window.AdjugoCrypto.LABELS) || {}; },
    async sharedReload(t) {
      try {
        const c = await this.api("GET", "/api/invite/" + (t || this.sharedAo.token) + "/contribution");
        this.sharedAo.status = c.status; this.sharedAo.pieces = c.pieces || []; this.sharedAo.version = c.version || 0;
        this.sharedAo.envelope = (c.detail_chiffre && c.detail_chiffre.ciphertext) ? c.detail_chiffre : null;
        const k = this.sharedAo.contrib;
        if (!k.company_name && !k.lot) {   // pré-remplir au 1er chargement, sans écraser une saisie
          k.company_name = c.company_name || this.company.name || ""; k.lot = c.lot || "";
          // Identité juridique (pour les CERFA DC1/DC2 du groupement) — pré-remplie depuis MA fiche entreprise.
          k.siret = c.siret || this.company.siret || ""; k.forme_juridique = c.forme_juridique || this.company.forme_juridique || "";
          k.address = c.address || this.company.address || ""; k.postal_code = c.postal_code || this.company.postal_code || ""; k.city = c.city || this.company.city || "";
          k.quals = (c.qualifications || []).join(", "); k.refs = (c.references || []).map(r => r.intitule || "").filter(Boolean).join("\n");
          k.memoire_paragraph = c.memoire_paragraph || "";
          k.prix_lot_ht = c.prix_lot_ht != null ? c.prix_lot_ht : "";
          k.representant_legal = c.representant_legal || this.company.representant_legal || ""; k.signataire_qualite = c.signataire_qualite || "";
          const cap = c.capacites || {};
          k.ca_n1 = cap.ca_n1 != null ? cap.ca_n1 : (this.company.ca_n1 || ""); k.effectif = cap.effectif != null ? cap.effectif : (this.company.effectif || "");
          const ct = c.contact || {}; k.contact = { nom: ct.nom || this.user.full_name || "", email: ct.email || this.user.email || "", telephone: ct.telephone || "" };
        }
        if (!this.sharedAo.detailLoaded) { this.sharedAo.detailLoaded = true; await this.sharedDetailLoad(); }
      } catch (e) {}
    },
    // ── Détail du chiffrage : chiffré PAR MEMBRE dans le navigateur (window.AdjugoCrypto, scope = jeton d'invitation) ──
    _rawCtx(ctx) { return (ctx && window.Vue && Vue.markRaw) ? Vue.markRaw(ctx) : ctx; },
    async sharedDetailLoad() {   // au chargement : clé connue → texte déchiffré ; enveloppe sans clé → zone verrouillée
      const C = window.AdjugoCrypto, env = this.sharedAo.envelope;
      if (!env) { this.sharedAo.detailLocked = false; return; }
      if (!C) { this.sharedAo.detailLocked = true; return; }
      try {
        const r = await C.ensureKey(this.sharedAo.token, env);
        if (r.ctx) { this._sharedApplyPlain(await C.decrypt(r.ctx, env)); this.sharedAo.cryptoCtx = this._rawCtx(r.ctx); this.sharedAo.detailLocked = false; }
        else this.sharedAo.detailLocked = true;
      } catch (e) { this.sharedAo.detailLocked = true; }
    },
    async sharedUnlock() {
      const C = window.AdjugoCrypto, env = this.sharedAo.envelope; if (!C || !env) return;
      const code = await C.askRecoveryCode(); if (!code) return;
      try {
        const ctx = await C.keyFromCode(this.sharedAo.token, code, env);
        this._sharedApplyPlain(await C.decrypt(ctx, env)); this.sharedAo.cryptoCtx = this._rawCtx(ctx); this.sharedAo.detailLocked = false;
        this.notify("Détail déverrouillé");
      } catch (e) { this.notify((e && e.code === "wrong_code") ? "Code incorrect" : ((e && e.message) || "Code incorrect"), "err"); }
    },
    async sharedLostCode() {
      const C = window.AdjugoCrypto; if (!C) return;
      if (!confirm("Vous avez perdu votre code de récupération ?\n\nL'ancien détail de votre chiffrage sera définitivement perdu : personne (ni Adjugo, ni le chef de file) ne peut le récupérer. Vous pourrez en saisir un nouveau.")) return;
      try {
        const rr = await C.resetKey(this.sharedAo.token);
        this.sharedAo.envelope = null; this.sharedAo.detailClair = ""; this.sharedAo.detailDpgf = null; this.sharedAo.detailLocked = false;
        const ok = await C.showRecoveryCode(rr.code);
        if (ok) { this.sharedAo.cryptoCtx = this._rawCtx(rr.ctx); this.sharedAo.pendingCode = null; } else { this.sharedAo.pendingCode = { code: rr.code, ctx: this._rawCtx(rr.ctx) }; }
        await this._sharedPut();   // efface l'ancien détail (désormais illisible) côté serveur
        this.notify("Ancien détail effacé — vous pouvez en saisir un nouveau");
      } catch (e) { this.notify((e && e.message) || "Réinitialisation impossible", "err"); }
    },
    // Texte clair déchiffré → texte libre (zone de saisie) + lignes de DPGF (conservées telles quelles).
    _sharedApplyPlain(plain) {
      const C = window.AdjugoCrypto;
      const u = (C && C.unpackDetail) ? C.unpackDetail(plain) : { texte: String(plain || ""), dpgf: null };
      this.sharedAo.detailClair = u.texte; this.sharedAo.detailDpgf = u.dpgf ? Vue.markRaw(u.dpgf) : null;
    },
    // Chiffre le texte ; null = ne pas envoyer (code non noté, détail verrouillé, navigateur sans WebCrypto…).
    async _sharedEncrypt(txt) {
      const C = window.AdjugoCrypto; if (!C) { this.notify("Chiffrement indisponible dans ce navigateur — détail non enregistré", "err"); return null; }
      let ctx = this.sharedAo.cryptoCtx;
      if (!ctx) {
        let code = null;
        if (this.sharedAo.pendingCode) { code = this.sharedAo.pendingCode.code; ctx = this.sharedAo.pendingCode.ctx; }
        else {
          const r = await C.ensureKey(this.sharedAo.token, this.sharedAo.envelope);
          if (r.needCode) { this.notify("Déverrouillez d'abord votre détail avec votre code", "err"); return null; }
          if (r.isNew) { code = r.code; ctx = r.ctx; }
          else if (!this.sharedAo.envelope) { const rr = await C.resetKey(this.sharedAo.token); code = rr.code; ctx = rr.ctx; }   // clé en cache mais rien de chiffré encore : on montre un code
          else ctx = r.ctx;
        }
        if (code) {
          const ok = await C.showRecoveryCode(code);
          if (!ok) { this.sharedAo.pendingCode = { code, ctx: this._rawCtx(ctx) }; this.notify("Détail non enregistré : notez d'abord votre code", "err"); return null; }
          this.sharedAo.pendingCode = null;
        }
        this.sharedAo.cryptoCtx = this._rawCtx(ctx);
      }
      try { return await C.encrypt(ctx, txt); } catch (e) { this.notify("Chiffrement impossible — détail non enregistré", "err"); return null; }
    },
    async _sharedBody() {
      const k = this.sharedAo.contrib;
      const num = (v) => (v === "" || v == null || Number.isNaN(Number(v))) ? null : Number(v);
      const body = { company_name: k.company_name, lot: k.lot,
               siret: k.siret, forme_juridique: k.forme_juridique, address: k.address, postal_code: k.postal_code, city: k.city,
               qualifications: (k.quals || "").split(",").map(s => s.trim()).filter(Boolean),
               references: (k.refs || "").split("\n").map(s => s.trim()).filter(Boolean).map(s => ({ intitule: s })),
               memoire_paragraph: k.memoire_paragraph, contact: k.contact,
               prix_lot_ht: num(k.prix_lot_ht), representant_legal: k.representant_legal || "", signataire_qualite: k.signataire_qualite || "",
               capacites: { ca_n1: num(k.ca_n1), effectif: num(k.effectif) == null ? null : Math.round(num(k.effectif)) },
               version: this.sharedAo.version };
      // Détail du chiffrage : verrouillé → on n'y touche pas (champ absent) ; vide → effacé ; sinon chiffré dans le navigateur.
      const txt = (this.sharedAo.detailClair || "").trim();
      if (!this.sharedAo.detailLocked) {
        // Les lignes de la DPGF (produites depuis la page partenaire) restent dans la même enveloppe.
        const C = window.AdjugoCrypto;
        const plain = (C && C.packDetail) ? C.packDetail(txt, this.sharedAo.detailDpgf) : txt;
        if (!String(plain).trim()) body.detail_chiffre = null;
        else { const env = await this._sharedEncrypt(plain); if (env) body.detail_chiffre = env; }
      }
      return body;
    },
    async _sharedPut() {   // PUT avec gestion du verrou optimiste (409)
      const body = await this._sharedBody();
      const r = await fetch("/api/invite/" + this.sharedAo.token + "/contribution", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (r.ok) { const c = await r.json(); this.sharedAo.version = c.version || 0; this.sharedAo.status = c.status; this.sharedAo.envelope = (c.detail_chiffre && c.detail_chiffre.ciphertext) ? c.detail_chiffre : null; return true; }
      if (r.status === 409) { this.notify("Modifié ailleurs entre-temps — rechargement de la dernière version", "err"); await this.sharedReload(); return false; }
      const e = await r.json().catch(() => ({})); const d = e && e.detail;
      this.notify((typeof d === "string" ? d : ((d && d.message) || (Array.isArray(d) && d[0] && this.validationMsg(d[0])))) || "Erreur d'enregistrement", "err"); return false;
    },
    async sharedSave() { this.sharedAo.busy = true; try { if (await this._sharedPut()) this.notify("Brouillon enregistré"); } finally { this.sharedAo.busy = false; } },
    // Binding d'identité OTP côté « Partagé avec moi » : si le lien l'exige (email
    // configuré), on vérifie l'adresse avant de soumettre — sinon le 403 bloquait sans
    // recours (aucun moyen de saisir le code).
    async sharedEnsureVerified() {
      const t = this.sharedAo.token;
      const st = await this.api("GET", "/api/invite/" + t + "/otp/status").catch(() => null);
      if (!st || !st.required || st.verified) return true;
      let masked = (st && st.email_masked) || "votre adresse";
      // On réutilise un code déjà valide (st.pending) au lieu d'en redemander un (la limite
      // 6/h serait épuisée par des clics répétés sur « Soumettre » → partenaire bloqué).
      if (!st.pending) {
        this.notify("Envoi d'un code de vérification…");
        const rq = await this.api("POST", "/api/invite/" + t + "/otp/request").catch(() => null);
        if (!rq || !rq.sent) { this.notify("Trop d'envois récents — patientez quelques minutes puis ressaisissez le dernier code reçu", "err"); return false; }
        masked = rq.email_masked || masked;
      }
      const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      let code = null;
      if (window.AdjugoCrypto && window.AdjugoCrypto.modal) {
        const r = await window.AdjugoCrypto.modal({ title: "Vérifiez votre identité", bodyHtml: "<p style='margin:0'>Saisissez le code à 6 chiffres envoyé à <b>" + esc(masked) + "</b> pour confirmer que c'est bien vous.</p>", withInput: true, placeholder: "123456", confirmLabel: "Valider", cancelLabel: "Annuler" });
        code = r && r.value;
      } else code = window.prompt("Saisissez le code à 6 chiffres envoyé à " + masked + " pour valider votre identité :");
      if (!code) { this.notify("Vérification annulée — brouillon conservé", "err"); return false; }
      try { await this.api("POST", "/api/invite/" + t + "/otp/verify", { code: String(code).trim() }); return true; }
      catch (e) { this.notify(e.message || "Code incorrect", "err"); return false; }
    },
    async sharedSubmit() {
      this.sharedAo.busy = true;
      try {
        if (!(await this._sharedPut())) return;
        if (!(await this.sharedEnsureVerified())) return;
        const c = await this.api("POST", "/api/invite/" + this.sharedAo.token + "/contribution/submit");
        this.sharedAo.status = c.status; this.notify("Contribution soumise au chef de file"); this.loadShared(); this.sharedConvLoad();
      } catch (e) { this.notify(e.message, "err"); } finally { this.sharedAo.busy = false; }
    },
    async sharedUpload(ev) {
      const f = ev.target.files[0]; if (!f) return;
      ev.target.value = "";
      this.sharedAo.busy = true;
      const fd = new FormData(); fd.append("file", f);
      if (this.sharedAo.upl.piece_type) fd.append("piece_type", this.sharedAo.upl.piece_type);
      if (this.sharedAo.upl.expiration_date) fd.append("expiration_date", this.sharedAo.upl.expiration_date);
      try {
        const r = await fetch("/api/invite/" + this.sharedAo.token + "/contribution/piece", { method: "POST", body: fd });
        if (!r.ok) { const e = await r.json().catch(() => ({})); this.notify((typeof e.detail === "string" && e.detail) || "Échec de l'envoi", "err"); }
        else { this.notify("Pièce ajoutée"); this.sharedAo.upl = { piece_type: "", expiration_date: "" }; this.sharedReload(); this.sharedLoadCoffre(); }
      } catch (e) { this.notify("Échec de l'envoi", "err"); } finally { this.sharedAo.busy = false; }
    },
    async sharedPatchPiece(pc, patch) {   // type / date d'expiration d'une de MES pièces (coffre croisé)
      try {
        const r = await fetch("/api/invite/" + this.sharedAo.token + "/contribution/piece/" + pc.id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error((typeof e.detail === "string" && e.detail) || "Modification impossible"); }
        Object.assign(pc, await r.json()); this.notify("Pièce mise à jour"); this.sharedLoadCoffre();
      } catch (e) { this.notify(e.message, "err"); }
    },
    async sharedRemovePiece(id) {
      try { await fetch("/api/invite/" + this.sharedAo.token + "/contribution/piece/" + id, { method: "DELETE" }); this.sharedReload(); this.sharedLoadCoffre(); }
      catch (e) { this.notify("Échec de la suppression de la pièce", "err"); }
    },
    // « Joindre depuis mon coffre-fort » : mes documents (compte) → copie jointe à ma part. Exige que le lien soit réclamé par mon compte (403 sinon).
    async sharedVaultOpen() {
      const v = this.sharedAo.vault; v.open = true; v.loading = true; v.needClaim = false;
      try { v.docs = (await this.api("GET", "/api/documents/") || []).filter(d => d && d.id); }
      catch (e) { v.docs = []; this.notify(e.message, "err"); }
      finally { v.loading = false; }
    },
    async sharedFromVault(d) {
      const v = this.sharedAo.vault; this.sharedAo.busy = true;
      try {
        const r = await fetch("/api/invite/" + this.sharedAo.token + "/contribution/piece/from-vault", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + this.token }, body: JSON.stringify({ document_id: d.id }) });
        if (r.status === 403) { v.needClaim = true; v.pendingDoc = d; return; }
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error((typeof e.detail === "string" && e.detail) || "Pièce non jointe"); }
        this.notify((d.name || "Pièce") + " jointe à votre part"); this.sharedReload(); this.sharedLoadCoffre();
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.sharedAo.busy = false; }
    },
    async sharedClaimThenVault() {
      const v = this.sharedAo.vault;
      try {
        const cr = await this.api("POST", "/api/invite/" + this.sharedAo.token + "/claim"); v.needClaim = false; this.loadShared();
        if (cr && cr.suggest_profile) this._rnSuggest(cr.suggest_profile);
        if (v.pendingDoc) { const d = v.pendingDoc; v.pendingDoc = null; await this.sharedFromVault(d); }
      } catch (e) { this.notify(e.message, "err"); }
    },
    async sharedLoadCoffre() {   // grille membre : statut des pièces de chacun, détail de MA ligne seulement
      try { this.sharedAo.coffre = await this.api("GET", "/api/invite/" + this.sharedAo.token + "/coffre-croise"); } catch (e) { this.sharedAo.coffre = null; }
    },
    async sharedJournalToggle(ev) {
      if (!(ev && ev.target && ev.target.open) || this.sharedAo.journalLoaded) return;
      await this.sharedJournalLoad();
    },
    async sharedJournalLoad() {
      const t = this.sharedAo.token; if (!t) return;
      try {
        const j = await this.api("GET", "/api/invite/" + t + "/journal");
        if (this.sharedAo.token === t) { this.sharedAo.journal = j; this.sharedAo.journalLoaded = true; }
      } catch (e) { this.notify("Journal indisponible", "err"); }
    },
    // ── Journal vérifiable par le membre (vague 4) : /api/shared/{project_id}/journal/… ──
    // Le verdict, la date de l'empreinte quotidienne et l'empreinte viennent du serveur ; rien
    // n'est recalculé ici. Repli sur les routes du lien si le marché n'est pas connu.
    _sharedJournalBase() {
      const a = this.sharedAo;
      return a.projectId ? "/api/shared/" + encodeURIComponent(a.projectId) + "/journal" : "/api/invite/" + encodeURIComponent(a.token) + "/journal";
    },
    async sharedJournalVerify() {
      const a = this.sharedAo, t = a.token, jv = a.jv; if (jv.busy) return;
      jv.busy = true; jv.err = ""; jv.live = "Vérification de votre journal…";
      try {
        const v = await this.api("GET", this._sharedJournalBase() + "/integrity");
        if (this.sharedAo.token !== t) return;
        jv.v = v; jv.live = (v.verdict_label || "") + " : " + (v.message || "");
      } catch (e) { jv.err = e.message || "Vérification impossible pour le moment."; jv.live = ""; }
      finally { jv.busy = false; }
    },
    async sharedJournalExport(fmt) {
      const a = this.sharedAo, jv = a.jv; if (jv.exporting) return;
      jv.exporting = fmt; jv.err = "";
      try {
        const r = await fetch(this._sharedJournalBase() + "/export?format=" + fmt, { headers: this.token ? { Authorization: "Bearer " + this.token } : {} });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error((typeof e.detail === "string" && e.detail) || (r.status === 429 ? TOO_MANY_MSG : "Téléchargement impossible pour le moment.")); }
        const cd = r.headers.get("content-disposition") || "", m = /filename="?([^";]+)"?/i.exec(cd);
        this.saveBlob(await r.blob(), (m && m[1]) || ("Journal." + fmt));
        jv.live = fmt === "json" ? "Preuve téléchargée : gardez ce fichier, le prochain export doit reprendre toutes ses lignes à l'identique." : "Journal téléchargé (PDF).";
        this.notify(fmt === "json" ? "Preuve du journal téléchargée" : "Journal téléchargé");
        a.journalLoaded = false; await this.sharedJournalLoad();   // « Vous avez exporté votre journal »
      } catch (e) { jv.err = e.message || "Téléchargement impossible."; }
      finally { jv.exporting = ""; }
    },
    jvPill(v) { return ({ intact: "go", altere: "no_go" })[v && v.verdict] || "neutral"; },
    jvIcon(v) { return ({ intact: "shield-check", altere: "shield-alert" })[v && v.verdict] || "shield"; },
    jvAncrage(v) {
      const an = v && v.ancrage;
      if (an && an.date) return an.horodate ? "Dernier horodatage : " + (an.date_label || an.date) + ", empreinte quotidienne du journal horodatée par une autorité indépendante."
                                            : "Dernière empreinte quotidienne du journal : " + (an.date_label || an.date) + " (sans horodatage externe).";
      return "Pas encore d'empreinte quotidienne horodatée : vos entrées sont couvertes par cette vérification et par les preuves que vous téléchargez.";
    },
    jvAncrageExtra(v) { const an = v && v.ancrage; return (an && an.message && an.entrees_couvertes && String(v.message || "").indexOf(an.message) < 0) ? an.message : ""; },
    jvHex(h) { return String(h || "").slice(0, 24).replace(/(.{4})/g, "$1 ").trim(); },
    jvWhen(s) { return this.convWhen(s); },
    async jvCopy(v) {
      try { await navigator.clipboard.writeText(v.empreinte); this.notify("Empreinte copiée"); } catch (e) { this.notify("Copie impossible : sélectionnez l'empreinte dans la preuve (JSON)", "err"); }
    },
    jvLabel() { return JOURNAL_LABEL; },
    jvLimites() { const v = this.sharedAo.jv.v; return (v && Array.isArray(v.limites) && v.limites.length) ? v.limites : JOURNAL_LIMITES; },
    // Lignes de DPGF conservées dans le détail chiffré (produites depuis la page partenaire).
    sharedDpgfPieces() { return (this.sharedAo.pieces || []).filter(p => p.piece_type === "dpgf_lot"); },
    sharedDpgfOpen() { window.open("/invite/" + encodeURIComponent(this.sharedAo.token) + "#dpgf", "_blank", "noopener"); },
    // Après un accord : l'étape du groupement (stepper) vient de /api/shared, rechargé ici — rouvrir
    // le dossier ajouterait une « consultation » au journal. Le journal est relu s'il est ouvert.
    async _sharedAfterAccord(t) {
      await this.loadShared();
      if (this.sharedAo.token !== t) return;
      const it = (this.shared || []).find(x => x && x.token === t), g = it && it.groupement, fm = this.sharedAo.forMember;
      if (g && fm) {
        const up = {}; ["state", "label", "index", "etape", "etapes"].forEach(k => { if (g[k] !== undefined) up[k] = g[k]; });
        fm.state = Object.assign({}, fm.state || {}, up);
      }
      this.sharedAo.journalLoaded = false;
      let el = this.$refs.sharedJournal; if (Array.isArray(el)) el = el[0];
      if (el && el.open) await this.sharedJournalLoad();
    },
    async sharedDecline() {
      if (!confirm("Décliner l'invitation ?\n\nVous sortez du groupement : votre part ne figurera pas dans la réponse commune et ce lien ne sera plus utilisable.")) return;
      try {
        const r = await fetch("/api/invite/" + this.sharedAo.token + "/decline", { method: "POST" });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error((typeof e.detail === "string" && e.detail) || "Impossible de décliner"); }
        this.go("shared"); this.loadShared(); this.notify("Invitation déclinée");
      } catch (e) { this.notify(e.message, "err"); }
    },
    // ── Convention de groupement vue par le partenaire (« Partagé avec moi ») ──
    // Mêmes routes que l'espace par lien (/api/invite/{token}/convention) : api() ajoute le
    // jeton du compte, donc l'accord est enregistré « depuis son compte Adjugo ».
    async sharedConvLoad() {
      const t = this.sharedAo.token; if (!t) return;
      const c = this.sharedAo.conv; c.loading = true; c.error = "";
      try {
        const d = await this.api("GET", "/api/invite/" + t + "/convention");
        if (this.sharedAo.token === t) this._sconvApply(d);
      } catch (e) { if (this.sharedAo.token === t) this.sharedAo.conv.error = e.message || "Convention momentanément indisponible."; }
      finally { c.loading = false; }
    },
    _sconvApply(d) {
      const c = this.sharedAo.conv; c.d = d;
      const ms = (d && d.ma_signature) || {};
      if (!c.accord.nom) c.accord.nom = ms.signataire_nom || "";
      if (!c.accord.qualite) c.accord.qualite = ms.signataire_qualite || "";
      if (c.accord.hash !== ((d && d.content_hash) || "")) { c.accord.accepte = false; c.accord.hash = (d && d.content_hash) || ""; }
    },
    sconvGenerated() { const s = this.sharedAo.conv.d && this.sharedAo.conv.d.status; return s === "a_signer" || s === "signee"; },
    async sharedConvValider(retried) {
      const t = this.sharedAo.token, c = this.sharedAo.conv, d = c.d; if (!d || (c.busy && !retried)) return;
      const ms = d.ma_signature || {};
      if (!c.accord.accepte) { c.err = "Cochez « J'ai lu la convention et je donne mon accord »."; return; }
      if (!(c.accord.nom || "").trim()) { c.err = "Indiquez le nom de la personne qui donne l'accord."; return; }
      c.busy = true; c.err = "";
      try {
        if (ms.verification_requise && !retried && !(await this.sharedEnsureVerified())) return;
        const r = await this.api("POST", "/api/invite/" + t + "/convention/valider",
          { content_hash: d.content_hash, signataire_nom: c.accord.nom.trim(), signataire_qualite: (c.accord.qualite || "").trim(), accepte: true });
        if (this.sharedAo.token !== t) return;
        this._sconvApply(r); c.live = "Votre accord est enregistré."; this.notify("Accord enregistré"); this._sharedAfterAccord(t);
      } catch (e) {
        if (e.code === "identity_unverified" && !retried) {
          if (await this.sharedEnsureVerified()) { await this.sharedConvValider(true); return; }
        }
        if (["texte_modifie", "perimee", "pas_generee"].includes(e.code)) await this.sharedConvLoad();
        c.err = e.message || "Accord impossible pour l'instant.";
      } finally { c.busy = false; }
    },
    async sharedConvPdf() {
      try { await this._pdfFetch("/api/invite/" + this.sharedAo.token + "/convention/pdf", "Convention_groupement.pdf"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    sharedGrpLine(s) {
      const g = s && s.groupement; if (!g || !g.etape) return "";
      const all = g.etapes || [], e = all.find(x => x.n === g.etape);
      return "Étape " + g.etape + (all.length ? " sur " + all.length : "") + (e ? " · " + e.label : "");
    },
    openSharedKey(ev, s) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.openShared(s); } },
    // Avec la grille « Comment vous serez noté », les critères s'affichent dans sa carte (phrase
    // du règlement, poids tel qu'écrit) : plus de ligne « Critères » brute, aux poids non contrôlés.
    sharedGrille(a) { const g = a && a.grille_notation; return (g && Array.isArray(g.criteres)) ? g : null; },
    sharedFact(a) { const L = { acheteur: "Acheteur", allotissement: "Allotissement", lieu: "Lieu", type_marche: "Type", date_limite: "Date limite", criteres_attribution: "Critères", duree: "Durée" }; if (this.sharedGrille(a)) delete L.criteres_attribution; return Object.entries(L).filter(([k]) => a && a[k] != null && a[k] !== "" && (!Array.isArray(a[k]) || a[k].length)).map(([k, lab]) => ({ k: lab, v: Array.isArray(a[k]) ? a[k].map(x => (x && typeof x === "object") ? (x.critere || x.nom || x.label || "") + (x.ponderation ? " — " + x.ponderation : "") : x).join(" · ") : a[k] })); },
    // ── Notifications (activité des partenaires) ──
    async loadNotifs() { try { this.notifs = await this.api("GET", "/api/notifications") || []; } catch (e) {} },
    toggleNotifs() {
      this.notifsOpen = !this.notifsOpen;
      if (this.notifsOpen) {
        this.loadNotifs();
        const newest = this.notifs.length ? this.notifs[0].at : new Date().toISOString();
        this.notifsSeen = newest || new Date().toISOString();
        try { localStorage.setItem("adjugo_notifs_seen", this.notifsSeen); } catch (e) {}
      }
    },
    openNotif(n) {
      this.notifsOpen = false;
      const p = this.projects.find(x => x.id === n.project_id);
      if (p) this.openProject(p); else this.notify("Cet appel d'offres n'est plus accessible", "err");
    },
    openProjectById(id) { const p = this.projects.find(x => x.id === id); if (p) this.openProject(p); else this.notify("Appel d'offres introuvable", "err"); },
    inviteUrl(inv) { return window.location.origin + (inv.path || ("/invite/" + inv.token)); },
    inviteState(inv) {
      if (inv.revoked) return { label: "Révoqué", cls: "neutral" };
      if (this.inviteDeclined(inv)) return { label: "A décliné", cls: "declined" };
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
      if (!confirm("Révoquer ce lien ? Le partenaire perdra l'accès immédiatement.")) return;
      try { await this.api("DELETE", "/api/projects/" + this.ao.project.id + "/invites/" + inv.id); this.notify("Lien révoqué"); this.aoLoadInvites(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async aoResendInvite(inv) {
      // Renvoie le mail sur le MÊME lien (sans changer le token) : relance un partenaire
      // silencieux ou rattrape un mail en spam, sans casser l'URL déjà partagée.
      if (inv._resending) return;   // garde anti double-clic (évite l'invitation en double)
      inv._resending = true;
      try {
        const r = await this.api("POST", "/api/projects/" + this.ao.project.id + "/invites/" + inv.id + "/resend");
        this.notify(r && r.sent ? (this.inviteIsNetwork(inv) ? "Invitation renvoyée par Adjugo" : "Invitation renvoyée par email")
          : (this.inviteIsNetwork(inv) ? "Envoi impossible pour le moment : le partenaire retrouve l'invitation dans son espace Adjugo" : "Envoi impossible — copiez le lien et transmettez-le"), r && r.sent ? "ok" : "err");
        this.aoLoadInvites();
      } catch (e) { this.notify(e.message, "err"); }
      finally { inv._resending = false; }
    },
    copyInvite(url, silent) {
      // writeText renvoie une Promise : on gère succès ET échec (le try/catch ne capte pas
      // un rejet asynchrone) → l'utilisateur a toujours un retour fiable.
      Promise.resolve(navigator.clipboard && navigator.clipboard.writeText(url))
        .then(() => this.notify(silent ? "Lien généré et copié dans le presse-papier" : "Lien copié"))
        .catch(() => this.notify("Copie impossible — sélectionnez le lien manuellement", "err"));
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
    // Cockpit — partenaires EN ATTENTE (invités, non révoqués, part non soumise) et relançables (email).
    aoPendingInvites() {
      return (this.ao.share.invites || []).filter(i => !i.revoked && !this.inviteDeclined(i) && i.can_contribute && i.contribution_status !== "submitted");
    },
    aoPendingRelancables() {
      return this.aoPendingInvites().filter(i => this.inviteRelancable(i));
    },
    // Relançable par email : adresse saisie, ou invitation du réseau Adjugo (adresse masquée au chef
    // de file mais connue d'Adjugo, qui renvoie le même texte réseau). Jamais une invitation SIRENE.
    inviteRelancable(inv) { return !!inv && (inv.source === "reseau_adjugo" || (inv.recipient || "").includes("@")); },
    inviteIsNetwork(inv) { return !!inv && inv.source === "reseau_adjugo"; },
    inviteSourceLabel(inv) { return ({ reseau_adjugo: "Réseau Adjugo", sirene: "Registre SIRENE" })[inv && inv.source] || ""; },
    async aoRelanceRetardataires() {
      if (this.ao.share._relancing) return;   // garde anti double-clic (évite les relances en double)
      const list = this.aoPendingRelancables();
      if (!list.length) { this.notify("Aucun partenaire relançable par email (copiez le lien à la place)", "err"); return; }
      this.ao.share._relancing = true;
      let sent = 0;
      for (const inv of list) {
        try {
          const r = await this.api("POST", "/api/projects/" + this.ao.project.id + "/invites/" + inv.id + "/resend");
          if (r && r.sent) sent++;
        } catch (e) {}
      }
      await this.aoLoadInvites();
      this.notify(sent ? sent + " partenaire(s) relancé(s) par email" : "Envoi impossible — copiez les liens et transmettez-les", sent ? "ok" : "err");
      this.ao.share._relancing = false;
    },
    auditLabel(a) {
      const m = {
        "invite.created": "Lien créé", "invite.revoked": "Lien révoqué", "invite.resent": "Invitation renvoyée", "invite.declined": "Le partenaire a décliné l'invitation", "invite.claimed": "Lien rattaché à un compte Adjugo",
        "guest.view_project": "Consultation du dossier", "guest.download_doc": "Téléchargement de pièce", "guest.submit_contribution": "Part soumise", "guest.upload_piece": "Pièce déposée par le partenaire",
        "guest.capacites_updated": "Capacités mises à jour par le partenaire", "guest.otp_request": "Code de vérification demandé", "guest.otp_verified": "Adresse email vérifiée",
        "owner.view_contribution": "Vous avez consulté la part de ce partenaire", "owner.download_piece": "Vous avez téléchargé une pièce du partenaire", "owner.view_piece": "Vous avez consulté une pièce du partenaire",
        "offer.frozen": "Offre commune figée", "offer.unfrozen": "Offre commune défigée", "piece.expiring": "Alerte : une attestation manque ou expire",
        "groupement.besoins": "Lecture de ce que le marché exige", "groupement.simulate": "Score en groupement calculé", "groupement.retenue": "Composition du groupement retenue", "groupement.plan_retire": "Composition du groupement annulée",
        "convention.generated": "Convention de groupement générée", "convention.signed": "Accord enregistré sur la convention",
        "convention.perimee": "Convention plus à jour (à régénérer)", "convention.hors_ligne": "Accord hors ligne enregistré",
        "convention.hors_ligne_retire": "Accord hors ligne retiré", "guest.download_convention": "Convention téléchargée par le partenaire",
        // Vague 4 : dépôt, journal vérifiable, pièces
        "groupement.depose": "Dossier marqué déposé", "groupement.depot_annule": "Marquage « déposé » retiré",
        "guest.export_journal": "Le partenaire a exporté son journal", "guest.update_piece": "Pièce mise à jour par le partenaire (type ou date de validité)",
        "grille.choix": "Critère de notation confirmé ou retiré",
      };
      return m[a.action] || a.action;
    },
    auditWhen(s) { if (!s) return ""; try { return new Date(s).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (e) { return s; } },
    // Horodatage du journal (audit_logs.created_at) : UTC « naïf » côté serveur → lu comme UTC,
    // affiché à l'heure locale (sinon décalé d'une ou deux heures par rapport à « Vérifié le … »).
    auditAt(s) { return s ? this.auditWhen(_isoUtc(s)) : ""; },
    verifWhen(c) { const s = (c && (c.freshness_date || (c.provenance && c.provenance.fetched_at))) || ""; if (!s) return ""; try { return new Date(s).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }); } catch (e) { return String(s).slice(0, 10); } },
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
        if (this.ao.group.data && !this.ao.group.data.n_lots) this.notify("Marché en lot unique : pas de répartition possible. Utilisez « Ajouter » pour un partenaire.");
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
    // ── « Répondre à plusieurs ? » (co-traitance v2) : score de groupement, manques, candidats, simulation ──
    // Règle : aucun chiffre n'est calculé ici ; tout vient de l'API (state / besoins / simulate).
    async aoGrpLoad() {
      const pid = this.ao.project && this.ao.project.id; if (!pid) return;
      this.ao.grp.loading = true; this.ao.grp.error = "";
      const [st, bs] = await Promise.all([
        this.api("GET", "/api/projects/" + pid + "/groupement/state").catch(e => ({ _err: e })),
        this.api("GET", "/api/projects/" + pid + "/groupement/besoins").catch(e => ({ _err: e })),
      ]);
      if (!this.ao.project || this.ao.project.id !== pid) return;   // l'utilisateur a changé de marché entre-temps
      if (st && !st._err) this.ao.grp.state = st;
      if (bs && !bs._err) this.ao.grp.besoins = bs;
      const err = (st && st._err) || (bs && bs._err);
      if (err) this.ao.grp.error = err.message || "Le calcul de groupement est momentanément indisponible.";
      this.ao.grp.loading = false;
      if (this.convVisible()) this.aoConvLoad();
      this.aoDepotLoadSoon();
    },
    async aoGrpLoadBesoins(sirene) {
      const pid = this.ao.project && this.ao.project.id; if (!pid) return;
      if (sirene) this.ao.grp.sireneLoading = true;
      try {
        this.ao.grp.besoins = await this.api("GET", "/api/projects/" + pid + "/groupement/besoins" + (sirene ? "?sirene=1" : ""));
        if (sirene && !((this.ao.grp.besoins.candidats || {}).sirene || []).length) this.notify("Aucune entreprise SIRENE trouvée pour ces manques", "err");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grp.sireneLoading = false; }
    },
    async aoGrpReloadState() {
      const pid = this.ao.project && this.ao.project.id; if (!pid) return;
      try { this.ao.grp.state = await this.api("GET", "/api/projects/" + pid + "/groupement/state"); } catch (e) {}
      if (this.convVisible() && !this.ao.conv.loaded) this.aoConvLoad(true);
      this.aoDepotLoadSoon();
    },
    // Stepper du groupement : les 5 étapes du parcours (state.etapes, dérivées côté serveur) ;
    // repli sur les 8 états de la vague 1 si l'API ne les renvoie pas. Plus de marque « bientôt ».
    grpSteps(state) {
      if (!state) return [];
      if (Array.isArray(state.etapes) && state.etapes.length)
        return state.etapes.map(e => ({ key: e.key, n: e.n, label: e.label, done: e.status === "fait", cur: e.status === "en_cours" }));
      const idx = typeof state.index === "number" ? state.index : -1;
      return (state.steps || []).map((s, i) => ({ key: s.key, n: i + 1, label: s.label, done: i < idx, cur: i === idx }));
    },
    grpEtapeNow(state) {
      const all = this.grpSteps(state), cur = all.find(s => s.cur); if (!cur) return "";
      const sub = state && state.label && state.label !== cur.label ? " — " + state.label : "";
      return "Étape " + cur.n + " sur " + all.length + " : " + cur.label + sub;
    },
    grpPlan() { const st = this.ao.grp.state; const p = st && st.plan; return (p && typeof p === "object" && (p.members || []).length) ? p : null; },
    grpBreakdown() {
      const sim = this.ao.grp.sim, plan = this.grpPlan();
      const src = (sim && sim.breakdown) || (plan && plan.breakdown);
      if (Array.isArray(src) && src.length) return src;
      // Rien de simulé : les critères du score SEUL (détail du dossier), colonne groupement vide.
      return (this.aoBreakdown() || []).map(c => ({ key: c.key, label: c.label, points_seul: c.points, points_groupement: null, max_points: c.max_points, apporte_par: [] }));
    },
    grpScore() {
      const sim = this.ao.grp.sim; if (sim && sim.score_groupement != null) return sim.score_groupement;
      const p = this.ao.project; return (p && p.groupement_score != null) ? p.groupement_score : null;
    },
    grpDecision() {
      const sim = this.ao.grp.sim; if (sim && sim.decision) return sim.decision;
      const st = this.ao.grp.state; if (st && st.decision) return st.decision;
      return this.ao.project && this.ao.project.go_decision;
    },
    grpWarnings() {
      const out = [], push = (w) => { if (w && !out.includes(w)) out.push(w); };
      ((this.ao.grp.besoins && this.ao.grp.besoins.warnings) || []).forEach(push);
      const sim = this.ao.grp.sim, plan = this.grpPlan(), st = this.ao.grp.state;
      ((sim && sim.warnings) || (plan && plan.warnings) || (st && st.warnings) || []).forEach(push);
      return out;
    },
    aoGrpRaisons() { const g = this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.groupement; return (g && g.recommande && Array.isArray(g.raisons)) ? g.raisons : []; },
    gapLabel(k) {
      const gaps = (this.ao.grp.besoins && this.ao.grp.besoins.gaps) || [];
      const g = gaps.find(x => x.key === k); if (g && g.label) return g.label;
      const b = this.grpBreakdown().find(x => x.key === k); if (b && b.label) return b.label;
      return ({ metier: "Métier", zone: "Zone", capacite: "Capacité financière", qualifs: "Qualifications", references: "Références", effectif: "Effectif" })[k] || k;
    },
    gapSevLabel(s) { return ({ bloquant: "Bloquant", important: "Important", a_verifier: "À vérifier" })[s] || s || ""; },
    gapSevClass(s) { return ({ bloquant: "no_go", important: "a_etudier", a_verifier: "neutral" })[s] || "neutral"; },
    candGroups() {
      const c = (this.ao.grp.besoins && this.ao.grp.besoins.candidats) || {};
      // « reseau » (vague 3) : profils publiés du réseau Adjugo, dans l'ORDRE du classement serveur
      // (un rang, jamais une note) ; le seul pourcentage reste score_avec (score de groupement).
      return [{ key: "rattaches", label: "Déjà rattachés à ce marché", list: c.rattaches || [] },
              { key: "annuaire", label: "Mes partenaires", list: c.annuaire || [] },
              { key: "reseau", label: "Réseau Adjugo", list: c.reseau || [] },
              { key: "sirene", label: "Entreprises SIRENE", list: c.sirene || [] }];
    },
    candTotal() { return this.candGroups().reduce((n, g) => n + g.list.length, 0); },
    candId(c) { return (c.kind || "?") + ":" + ((c.kind === "reseau" && c.profile_id) || c.id || c.siret || (c.name || "").toLowerCase()); },
    isCandSelected(c) { const id = this.candId(c); return this.ao.grp.selected.some(m => this.candId(m) === id); },
    toggleCand(c) {
      const id = this.candId(c), i = this.ao.grp.selected.findIndex(m => this.candId(m) === id);
      if (i >= 0) { this.ao.grp.selected.splice(i, 1); return; }
      if (this.ao.grp.selected.length >= 4) { this.notify("4 partenaires au maximum par simulation", "err"); return; }
      this.ao.grp.selected.push(c);
    },
    aoGrpAddSaisi() {
      const s = this.ao.grp.saisi; const name = (s.name || "").trim();
      if (!name) { this.notify("Le nom de l'entreprise est obligatoire", "err"); return; }
      const quals = (s.qualifications || "").split(",").map(x => x.trim()).filter(Boolean);
      this.toggleCand({ kind: "saisi", name, siret: (s.siret || "").replace(/\D/g, ""), ca_n1: s.ca_n1 || null, effectif: s.effectif || null, qualifications: quals, city: "" });
      this.ao.grp.saisi = { name: "", siret: "", ca_n1: null, effectif: null, qualifications: "" }; this.ao.grp.saisiOpen = false;
    },
    _grpMemberBody(m) {
      if (m.kind === "attached" || m.kind === "annuaire") return { kind: m.kind, id: m.id };
      if (m.kind === "sirene") return { kind: "sirene", siret: m.siret, name: m.name };
      // Réseau : le serveur relit le profil publié (capacités du navigateur ignorées).
      if (m.kind === "reseau") return { kind: "reseau", profile_id: m.profile_id };
      return { kind: "saisi", name: m.name, siret: m.siret || "", ca_n1: m.ca_n1 || null, effectif: m.effectif || null, qualifications: m.qualifications || [] };
    },
    async aoGrpSimulate() {
      const pid = this.ao.project.id, members = this.ao.grp.selected.map(m => this._grpMemberBody(m));
      if (!members.length) { this.notify("Cochez au moins un partenaire", "err"); return; }
      this.ao.grp.simulating = true;
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/simulate", { members, save: true });
        r.retained = false; this.ao.grp.sim = r;
        if (r.state && this.ao.grp.state) Object.assign(this.ao.grp.state, r.state);
        this.ao.grp.historyLoaded = false;
        this.notify("Seul " + r.score_seul + " % → en groupement " + r.score_groupement + " %");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grp.simulating = false; }
    },
    simPartners(sim) { return ((sim && sim.members) || []).filter(m => m && m.kind !== "lead"); },
    async aoGrpRetenir() {
      const sim = this.ao.grp.sim; if (!sim || !sim.simulation_id) return;
      this.ao.grp.retaining = true;
      try {
        const r = await this.api("POST", "/api/projects/" + this.ao.project.id + "/groupement/retenir", { simulation_id: sim.simulation_id });
        sim.retained = true;
        this.notify("Composition retenue" + (r && r.decision_label ? " — " + r.decision_label : ""));
        await this.aoGrpReloadState();
        try { this.ao.project = await this.api("GET", "/api/projects/" + this.ao.project.id); } catch (e) {}
        this.aoLoadCotraitants(); this.loadProjects(); this.ao.grp.historyLoaded = false;
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grp.retaining = false; }
    },
    inviteDeclined(inv) { return !!(inv && (inv.state === "declined" || inv.declined_at)); },
    grpAlreadyInvited(m) {
      const n = ((m && m.name) || "").trim().toLowerCase(); if (!n) return false;
      return (this.ao.share.invites || []).some(i => !i.revoked && !this.inviteDeclined(i) && (i.company_name || "").trim().toLowerCase() === n);
    },
    // Dernière invitation DÉCLINÉE pour ce nom d'entreprise, s'il n'en a pas d'active depuis (même
    // rapprochement par nom que grpAlreadyInvited) → pastille « A décliné » là où il est proposé.
    inviteDeclinedFor(name) {
      const n = String(name || "").trim().toLowerCase(); if (!n) return null;
      const same = (this.ao.share.invites || []).filter(i => (i.company_name || "").trim().toLowerCase() === n);
      if (same.some(i => !i.revoked && !this.inviteDeclined(i))) return null;
      const dec = same.filter(i => this.inviteDeclined(i)).sort((a, b) => String(b.declined_at || "").localeCompare(String(a.declined_at || "")));
      return dec[0] || null;
    },
    declinedLabel(inv) { const d = inv && this.ddmm(inv.declined_at); return "A décliné" + (d ? " le " + d : ""); },
    // « Inviter {nom} » : pré-remplit le formulaire d'invitation existant et y amène l'utilisateur.
    aoGrpInvite(m) {
      // Partenaire du réseau Adjugo : invitation en 1 clic (Adjugo l'envoie, l'adresse reste masquée)
      // au lieu du formulaire manuel, qui demanderait une adresse que le chef de file n'a pas.
      const pid = m && m.kind === "reseau" ? this._grpProfileId(m) : "";
      if (pid) { this.rnInviteOpen({ profile_id: pid, name: m.name }); return; }
      this.ao.share.form.company_name = (m && m.name) || ""; this.ao.share.open = true;
      this.$nextTick(() => { const el = this.$refs.reseauCard; if (el && el.scrollIntoView) el.scrollIntoView({ block: "start" }); });
    },
    // Identifiant de profil d'un membre « reseau » de la composition retenue (le plan ne le garde pas) :
    // retrouvé dans la simulation, les candidats ou le panneau « Partenaires pour ce marché » (SIRET, sinon nom).
    _grpProfileId(m) {
      if (!m) return "";
      if (m.profile_id) return m.profile_id;
      const n = String(m.name || "").trim().toLowerCase(), s = m.siret || "";
      const pool = this.simPartners(this.ao.grp.sim).concat(((this.ao.grp.besoins || {}).candidats || {}).reseau || [],
        ((this.ao.pm.d && this.ao.pm.d.lots) || []).reduce((a, l) => a.concat(l.reseau || []), []));
      const same = x => (s && (x.siret === s || (x.siren && s.slice(0, 9) === x.siren))) || (n && String(x.name || "").trim().toLowerCase() === n);
      const hit = pool.find(x => x && x.profile_id && same(x));
      return (hit && hit.profile_id) || "";
    },
    async aoGrpHistoryToggle(ev) {
      const open = !!(ev && ev.target && ev.target.open); this.ao.grp.historyOpen = open;
      if (!open || this.ao.grp.historyLoaded) return;
      this.ao.grp.historyLoading = true;
      try { this.ao.grp.history = await this.api("GET", "/api/projects/" + this.ao.project.id + "/groupement/simulations") || []; this.ao.grp.historyLoaded = true; }
      catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grp.historyLoading = false; }
    },
    grpCanCancel() { const st = this.ao.grp.state, p = this.grpPlan(); return !!(st && typeof st.index === "number" && st.index >= 2 && p && !p.auto); },
    async aoGrpCancelPlan() {
      if (!confirm("Annuler la composition retenue ?\nVous revenez au verdict seul. Les partenaires déjà rattachés au marché restent en place.")) return;
      try {
        const r = await this.api("DELETE", "/api/projects/" + this.ao.project.id + "/groupement/plan");
        this.ao.grp.sim = null; if (r && r.state) this.ao.grp.state = r.state;
        try { this.ao.project = await this.api("GET", "/api/projects/" + this.ao.project.id); } catch (e) {}
        this.loadProjects(); this.ao.grp.historyLoaded = false;
        this.notify("Composition annulée — verdict seul restauré");
      } catch (e) { this.notify(e.message, "err"); }
    },
    // ══════════ Réseau de partenaires (co-traitance v2, vague 3) ══════════
    // Contrat : docs/COTRAITANCE_V2_VAGUE3_API.md. Règles tenues ici :
    //  - un seul pourcentage à l'écran : le score de groupement (/groupement/simulate). Le réseau
    //    renvoie un RANG et des CRITÈRES (statut + phrase + source + date) : rien n'est calculé ici ;
    //  - badges et capacités affichés tels quels (libellé, source, date) — jamais de note ni d'étoile ;
    //  - l'adresse d'un partenaire du réseau n'est jamais affichée (le serveur la masque) ;
    //  - tout texte saisi par une entreprise est rendu en {{ }} (jamais v-html / innerHTML).
    openReseau(tab) { this.reseau.tab = tab || "profil"; this.go("reseau"); },
    rnGo(tab) {
      const r = this.reseau; r.tab = tab;
      if (tab === "profil" && !r.p.loaded) this.rnLoadProfil();
      if (tab === "annuaire") { if (!r.p.loaded) this.rnLoadProfil(true); if (!r.an.loaded) this.rnLoadAnnuaire(1); }
      if (tab === "historique") this.rnLoadHistorique();
      if (tab === "recues") this.rnLoadRecues();
    },
    rnOptions() {
      const d = this.reseau.p.d, o = (d && d.options) || {};
      return { metiers: o.metiers || [], roles: o.roles || [], disponibilites: o.disponibilites || [], presentation_max: o.presentation_max || 300, references_max: o.references_max || 5 };
    },
    plFr(n, one, many) { return Math.abs(Number(n) || 0) < 2 ? one : many; },
    rnStatutPill(s) { return ({ publie: "go", brouillon: "neutral", retire: "a_etudier", aucun: "neutral", en_attente: "a_etudier", refuse: "no_go" })[s] || "neutral"; },
    rnPending() { const d = this.reseau.p.d; return !!(d && d.statut === "en_attente"); },
    // Libellé des raccourcis « Publier mon profil » (annuaire, marché) : une demande en cours se consulte.
    rnPubCta() { return this.rnPending() ? "Voir ma demande de publication" : "Publier mon profil"; },
    // Bouton de publication du profil : demande de validation à Adjugo, sauf identité déjà validée.
    rnPubLabel(d) { return d && d.validation && d.validation.identite_validee ? "Publier mon profil" : "Demander la publication"; },
    rnRoleLabel(r) { return ({ cotraitant: "Partenaire du groupement (co-traitant)", sous_traitant: "Sous-traitant", mandataire: "Chef de file" })[r] || r; },
    rnMetiers(c) { return ((c && c.metiers) || []).map(m => (m && m.label) || m).filter(Boolean).join(", "); },
    rnLieu(c) { return c ? [c.city, c.departement ? "(" + c.departement + ")" : ""].filter(Boolean).join(" ") : ""; },
    // Icône d'une vérification (SIRENE / BODACC / DECP) : vérifié, à regarder, ou « non vérifié ».
    rnVerif(v, k) {
      v = v || {};
      if (k === "sirene") return v.etat === "actif" ? { ic: "check", cls: "ok" } : v.etat === "cesse" ? { ic: "circle-x", cls: "alerte" } : { ic: "circle-dashed", cls: "nv" };
      if (k === "bodacc") return v.found === false ? { ic: "check", cls: "ok" } : v.found === true ? { ic: "triangle-alert", cls: "alerte" } : { ic: "circle-dashed", cls: "nv" };
      return v.count > 0 ? { ic: "check", cls: "ok" } : v.count === 0 ? { ic: "minus", cls: "info" } : { ic: "circle-dashed", cls: "nv" };
    },
    _rnSay(msg) { this.reseau.p.live = msg; this.notify(msg); },
    _rnErr(msg, at, code, missing) { const p = this.reseau.p; p.err = msg; p.errAt = at || "form"; p.errCode = code || ""; p.missing = missing || []; this.notify(msg, "err"); },
    _rnFail(e, at) { this._rnErr((e && e.message) || "Action impossible pour l'instant.", at, (e && e.code) || "", (e && e.missing) || []); },
    _rnErrClear() { const p = this.reseau.p; p.err = ""; p.errCode = ""; p.errAt = ""; p.missing = []; },
    rnErrAt(z) { const p = this.reseau.p; return !!p.err && p.errAt === z; },
    _rnSuggest(s) {
      if (!s || typeof s !== "object" || s.code !== "publier_profil_reseau" || this.reseauSuggestOff) return;
      this.reseauSuggest = { titre: String(s.titre || "Faites-vous trouver pour des groupements"), message: String(s.message || "") };
    },
    rnSuggestClose() { this.reseauSuggest = null; this.reseauSuggestOff = true; },
    rnSuggestGo() { this.reseauSuggest = null; this.reseauSuggestOff = true; this.openReseau("profil"); },

    // ── Mon profil partenaire ──
    rnLoadProfil(quiet) {   // renvoie la requête en cours si elle existe déjà (pas de double appel)
      const p = this.reseau.p;
      if (p.loading && this._rnProfilP) return this._rnProfilP;
      p.loading = true; p.error = "";
      this._rnProfilP = (async () => {
        try { this._rnApply(await this.api("GET", "/api/reseau/profil")); }
        catch (e) { p.error = (e && e.message) || "Profil partenaire momentanément indisponible."; if (!quiet) this.notify(p.error, "err"); }
        finally { p.loading = false; }
      })();
      return this._rnProfilP;
    },
    _rnApply(d, keepForm) {
      const p = this.reseau.p; if (!d || typeof d !== "object") return;
      p.d = d; p.loaded = true;
      if (!keepForm || !p.f) p.f = this._rnForm(d);
      if (!d.suggestion) this.reseauSuggest = null;   // profil déjà publié (ou démo) : plus de suggestion
    },
    _rnSplit(s) { return String(s || "").split(/[,;\s]+/).map(x => x.trim()).filter(Boolean); },
    _rnRefKey(r) { return [(r && r.intitule) || "", (r && r.client) || "", (r && r.annee != null && r.annee !== "") ? String(r.annee) : ""].join("|"); },
    _rnRefClean(r) { return { intitule: r.intitule, client: r.client || "", annee: (r.annee != null && r.annee !== "") ? r.annee : null }; },
    _rnForm(d) {
      const dc = (d && d.declare) || {};
      return {
        metiers: (dc.metiers || []).slice(), departements: (dc.departements || []).join(", "),
        roles_acceptes: (dc.roles_acceptes || []).slice(), disponibilite: dc.disponibilite || "",
        dispo_jusqua: dc.dispo_jusqua || "", lot_max_eur: dc.lot_max_eur != null ? dc.lot_max_eur : "",
        codes_cpv: (dc.codes_cpv || []).join(", "), presentation: dc.presentation || "",
        refs: (dc.references_publiques || []).map(r => this._rnRefKey(r)),
        hidden: ((d && d.hidden_from_sirens) || []).join(", "),
      };
    },
    // Références proposables : celles du profil entreprise, puis celles déjà rendues publiques qui n'y
    // figurent plus (pour pouvoir les décocher). Chacune garde une clé stable (intitulé|client|année).
    rnRefOptions() {
      const d = this.reseau.p.d; if (!d) return [];
      const out = [], seen = new Set();
      (d.references_disponibles || []).concat((d.declare && d.declare.references_publiques) || []).forEach(r => {
        if (!r || !r.intitule) return; const k = this._rnRefKey(r); if (seen.has(k)) return; seen.add(k); out.push(Object.assign({ _k: k }, r));
      });
      return out;
    },
    rnRefDisabled(r) { const f = this.reseau.p.f; return !!f && !f.refs.includes(r._k) && f.refs.length >= this.rnOptions().references_max; },
    _rnAll() {
      const f = this.reseau.p.f;
      const lot = (f.lot_max_eur === "" || f.lot_max_eur == null) ? null : Number(f.lot_max_eur);
      return {
        metiers: f.metiers.slice(), departements: this._rnSplit(f.departements), roles_acceptes: f.roles_acceptes.slice(),
        disponibilite: f.disponibilite || "", dispo_jusqua: f.disponibilite ? (f.dispo_jusqua || null) : null, lot_max_eur: lot,
        codes_cpv: this._rnSplit(f.codes_cpv), presentation: String(f.presentation || "").trim(),
        references_publiques: this.rnRefOptions().filter(r => f.refs.includes(r._k)).map(r => this._rnRefClean(r)),
        hidden_from_sirens: this._rnSplit(f.hidden),
      };
    },
    // Mise à jour PARTIELLE : seulement les champs modifiés (tout, au premier enregistrement).
    _rnBody() {
      const d = this.reseau.p.d || {}, dc = d.declare || {}, all = this._rnAll();
      if (!d.exists) return all;
      const before = {
        metiers: dc.metiers || [], departements: dc.departements || [], roles_acceptes: dc.roles_acceptes || [],
        disponibilite: dc.disponibilite || "", dispo_jusqua: dc.disponibilite ? (dc.dispo_jusqua || null) : null,
        lot_max_eur: dc.lot_max_eur != null ? Number(dc.lot_max_eur) : null, codes_cpv: dc.codes_cpv || [],
        presentation: dc.presentation || "", references_publiques: (dc.references_publiques || []).map(r => this._rnRefClean(r)),
        hidden_from_sirens: d.hidden_from_sirens || [],
      };
      const unordered = { metiers: 1, roles_acceptes: 1, codes_cpv: 1, hidden_from_sirens: 1 };
      const norm = (k, v) => (unordered[k] && Array.isArray(v)) ? v.slice().sort() : v;
      const out = {};
      Object.keys(all).forEach(k => { if (JSON.stringify(norm(k, all[k])) !== JSON.stringify(norm(k, before[k]))) out[k] = all[k]; });
      return out;
    },
    rnDirty() { const p = this.reseau.p; return !!(p.d && p.f && p.d.exists && Object.keys(this._rnBody()).length); },
    async rnSave(silentOk) {
      const p = this.reseau.p; if (!p.f || !p.d || p.busy) return false;
      const lot = p.f.lot_max_eur;
      if (lot !== "" && lot != null && !(Number(lot) > 0)) { this._rnErr("Taille de lot maximale invalide (montant HT positif).", "form"); return false; }
      if (String(p.f.presentation || "").trim().length > this.rnOptions().presentation_max) { this._rnErr("Présentation en une phrase : " + this.rnOptions().presentation_max + " caractères au plus.", "form"); return false; }
      const created = !p.d.exists, body = this._rnBody();
      if (!created && !Object.keys(body).length) { if (!silentOk) this._rnSay("Aucune modification à enregistrer."); return true; }
      p.busy = "save"; this._rnErrClear();
      try {
        const d = await this.api("PUT", "/api/reseau/profil", body);
        this._rnApply(d);
        this._rnSay(d.message || (created ? "Profil enregistré, non publié. Vérifiez votre entreprise, puis publiez-le." : "Profil enregistré."));
        this.reseau.an.loaded = false;
        return true;
      } catch (e) { this._rnFail(e, "form"); return false; }
      finally { p.busy = ""; }
    },
    async rnVerify() {
      const p = this.reseau.p; if (!p.d || p.busy) return;
      p.busy = "verif"; this._rnErrClear(); p.verifMsgs = [];
      try {
        const d = await this.api("POST", "/api/reseau/profil/verifier");
        this._rnApply(d, true);
        const v = d.verification || {}, msgs = [];
        if (d.message) msgs.push(d.message);
        ["sirene", "bodacc", "decp"].forEach(k => { const x = v[k]; if (x && x.message && !msgs.includes(x.message)) msgs.push(x.message); });
        p.verifMsgs = msgs;
        this._rnSay(msgs.length ? "Vérification terminée : un point est à regarder." : "Vérification terminée.");
      } catch (e) { this._rnFail(e, "verif"); }
      finally { p.busy = ""; }
    },
    async rnPublish() {
      const p = this.reseau.p; if (!p.d || p.busy) return;
      if (!p.consent) { this._rnErr("Cochez « J'accepte que la fiche ci-dessus soit visible des entreprises qui ont publié la leur » pour publier.", "pub", "consentement_requis"); return; }
      if (this.rnDirty() && !(await this.rnSave(true))) return;   // la fiche publiée = celle de l'aperçu, modifications comprises
      p.busy = "pub"; this._rnErrClear();
      try {
        const d = await this.api("POST", "/api/reseau/profil/publier", { accepte: true });
        this._rnApply(d, true); p.consent = false; this.reseauSuggest = null;
        this.reseau.an.loaded = false;
        this._rnSay(d.message || (d.visible ? "Profil publié dans le réseau Adjugo." : "Demande envoyée à Adjugo."));
      } catch (e) { this._rnFail(e, "pub"); }
      finally { p.busy = ""; }
    },
    rnUnpublish() {
      this._convAsk({ title: "Retirer la publication ?", ok: "Retirer la publication",
        lines: ["Votre fiche n'apparaîtra plus dans le réseau Adjugo.", "Les invitations déjà en cours restent valables.", "Vous pourrez la publier de nouveau à tout moment."],
        run: async () => {
          const p = this.reseau.p; if (p.busy) return;
          p.busy = "pub"; this._rnErrClear();
          try { const d = await this.api("DELETE", "/api/reseau/profil/publier"); this._rnApply(d, true); this.reseau.an.loaded = false; this._rnSay(d.message || "Publication retirée."); }
          catch (e) { this._rnFail(e, "pub"); }
          finally { p.busy = ""; }
        } });
    },
    rnCancelDemande() {
      this._convAsk({ title: "Annuler la demande de publication ?", ok: "Annuler la demande",
        lines: ["Adjugo ne vérifiera pas votre entreprise pour l'instant.", "Votre profil reste enregistré, non publié.", "Vous pourrez renvoyer la demande à tout moment."],
        run: async () => {
          const p = this.reseau.p; if (p.busy) return;
          p.busy = "pub"; this._rnErrClear();
          try { const d = await this.api("DELETE", "/api/reseau/profil/publier"); this._rnApply(d, true); this._rnSay(d.message || "Demande de publication annulée."); }
          catch (e) { this._rnFail(e, "pub"); }
          finally { p.busy = ""; }
        } });
    },
    rnDelete() {
      this._convAsk({ title: "Effacer votre profil partenaire ?", ok: "Effacer mon profil",
        lines: ["Il disparaît du réseau Adjugo.", "Votre adresse est retirée des invitations reçues par le réseau.", { t: "Cette action ne s'annule pas : il faudra recréer le profil.", warn: true }],
        run: async () => {
          const p = this.reseau.p; if (p.busy) return;
          p.busy = "del"; this._rnErrClear();
          try {
            const r = await this.api("DELETE", "/api/reseau/profil");
            p.loaded = false; p.consent = false; p.verifMsgs = [];
            this.reseau.an = _reseauInit().an; this.reseau.hist.loaded = false;
            this._rnSay((r && r.message) || "Profil partenaire effacé.");
            p.busy = ""; await this.rnLoadProfil(true);
          } catch (e) { this._rnFail(e, "pub"); }
          finally { p.busy = ""; }
        } });
    },
    // Défilement de la seule zone de contenu (.work) : scrollIntoView faisait aussi défiler la page
    // entière quand la cible était en bas (barre latérale décalée). L'en-tête collant est compté.
    rnScrollTo(ref, nearest) {
      this.$nextTick(() => {
        let el = this.$refs[ref]; if (Array.isArray(el)) el = el[0];
        const w = document.querySelector(".work"); if (!el || !w) return;
        const top = w.querySelector(".top"), head = top ? top.getBoundingClientRect().height : 0;
        const wr = w.getBoundingClientRect(), r = el.getBoundingClientRect();
        let delta = r.top - wr.top - head - 16;
        if (nearest) {
          if (r.top >= wr.top + head && r.bottom <= wr.bottom) delta = 0;
          else if (r.bottom > wr.bottom && r.height < wr.height - head) delta = r.bottom - wr.bottom + 16;
        }
        if (delta) w.scrollTo({ top: Math.max(0, w.scrollTop + delta), behavior: "smooth" });
        if (el.focus && el.getAttribute("tabindex") != null) el.focus({ preventScroll: true });
      });
    },
    // Raccourci « Publier mon profil » depuis l'annuaire ou un marché : onglet profil, bloc Publication.
    async rnGoPublish() { this.openReseau("profil"); if (!this.reseau.p.loaded) await this.rnLoadProfil(true); this.rnScrollTo("rnPub"); },

    // ── Annuaire ──
    async rnLoadAnnuaire(page) {
      const a = this.reseau.an; if (a.loading) return;
      const f = a.f, qs = new URLSearchParams();
      if (f.metier) qs.set("metier", f.metier);
      if (String(f.departement || "").trim()) qs.set("departement", String(f.departement).trim());
      if (f.role) qs.set("role", f.role);
      if (String(f.q || "").trim()) qs.set("q", String(f.q).trim());
      qs.set("page", String(page || 1)); qs.set("par_page", "20");
      a.loading = true; a.error = "";
      try {
        const d = await this.api("GET", "/api/reseau/annuaire?" + qs.toString());
        a.d = d; a.loaded = true; a.page = (d && d.page) || page || 1;
        a.live = !d.visible ? (d.message || "") : (d.total ? d.total + " " + this.plFr(d.total, "partenaire trouvé", "partenaires trouvés") + "." : "Aucun partenaire du réseau Adjugo ne correspond encore à cette recherche.");
      } catch (e) { a.error = (e && e.message) || "Annuaire momentanément indisponible."; a.live = a.error; }
      finally { a.loading = false; }
    },
    rnPages() { const d = this.reseau.an.d; return d && d.visible ? Math.max(1, Math.ceil((d.total || 0) / (d.par_page || 20))) : 1; },
    rnClassed() { const d = this.reseau.an.d; return !!(d && (d.profils || []).some(c => c.rang != null)); },
    // États vides : on renvoie vers la recherche SIRENE existante (« Découvrir ») et « Mes partenaires ».
    rnDiscover(metierKey, dept, label) {
      const key = metierKey || this.reseau.an.f.metier;
      // Les options du réseau ne sont chargées qu'avec la vue Réseau : repli sur le libellé du lot,
      // puis sur la liste des métiers du registre (chargée par openDiscover), puis sur la clé.
      const m = this.rnOptions().metiers.find(x => x.key === key) || (this.trades || []).find(t => t.key === key);
      this.openDiscover();
      const lab = label || (m && m.label) || key || "";
      if (lab) this.discover.trade = lab;
      const dd = String(dept || this.reseau.an.f.departement || "").trim();
      if (dd) this.discover.dept = dd;
    },

    // ── Fiche d'un partenaire (modale) ──
    async rnOpenFiche(profileId, ctx) {
      if (!profileId) return;
      this._rnFicheFocus = document.activeElement;
      this.reseau.fiche = { id: profileId, loading: true, d: null, error: "", errCode: "", ctx: ctx || null };
      this.$nextTick(() => { const x = this.$refs.rnFicheX; if (x && x.focus) x.focus(); });
      try {
        const d = await this.api("GET", "/api/reseau/annuaire/" + encodeURIComponent(profileId));
        if (this.reseau.fiche && this.reseau.fiche.id === profileId) this.reseau.fiche.d = d;
      } catch (e) {
        if (this.reseau.fiche && this.reseau.fiche.id === profileId) { this.reseau.fiche.error = (e && e.message) || "Fiche indisponible."; this.reseau.fiche.errCode = (e && e.code) || ""; }
      } finally { if (this.reseau.fiche && this.reseau.fiche.id === profileId) this.reseau.fiche.loading = false; }
    },
    rnCloseFiche(keepFocus) {
      this.reseau.fiche = null;
      const el = this._rnFicheFocus; this._rnFicheFocus = null;
      if (!keepFocus && el && el.focus && document.body.contains(el)) this.$nextTick(() => el.focus());
    },
    rnInviteFromFiche() {
      const fi = this.reseau.fiche; if (!fi || !fi.d) return;
      const card = fi.d, ctx = fi.ctx || {};
      const back = this._rnFicheFocus; this.rnCloseFiche(true);
      this.rnInviteOpen(card, { lot: ctx.lot || "", projectId: ctx.projectId || null, focusBack: back });
    },
    rnHistAvec(h) {
      h = h || {};
      return [{ l: "Invitations en cours", v: h.invitations_actives }, { l: "Parts envoyées", v: h.parts_soumises },
              { l: "Marchés déposés ensemble", v: h.marches_deposes }, { l: "Gagnés", v: h.gagnes }, { l: "Perdus", v: h.perdus }].map(x => ({ l: x.l, v: Number(x.v) || 0 }));
    },

    // ── Mon historique ──
    async rnLoadHistorique() {
      const h = this.reseau.hist; if (h.loading) return;
      h.loading = true; h.error = "";
      try { h.d = await this.api("GET", "/api/reseau/historique"); h.loaded = true; }
      catch (e) { h.error = (e && e.message) || "Historique momentanément indisponible."; }
      finally { h.loading = false; }
    },
    rnHistRows(side) {
      const d = this.reseau.hist.d || {}, x = (side === "chef" ? d.comme_chef_de_file : d.comme_partenaire) || {};
      const rows = side === "chef"
        ? [["invitations_actives", "Invitations en cours"], ["parts_recues", "Parts reçues des partenaires"], ["marches_deposes", "Marchés déposés"], ["gagnes", "Gagnés"], ["perdus", "Perdus"]]
        : [["invitations_actives", "Invitations en cours"], ["parts_soumises", "Parts envoyées au chef de file"], ["marches_deposes", "Marchés déposés"], ["gagnes", "Gagnés"], ["perdus", "Perdus"]];
      return rows.map(r => ({ k: r[0], l: r[1], v: Number(x[r[0]]) || 0 }));
    },
    rnHistEmpty() { return !["chef", "partenaire"].some(s => this.rnHistRows(s).some(r => r.v > 0)); },

    // ── Invitations reçues par le réseau (côté partenaire) ──
    async rnLoadRecues(quiet) {
      const r = this.reseau.recues; if (r.loading || !this.token) return;
      r.loading = true;
      try {
        const d = await this.api("GET", "/api/reseau/invitations");
        const declined = (r.list || []).filter(i => i._declined);   // « Vous avez décliné » reste visible jusqu'au départ de la vue
        r.list = ((d && d.invitations) || []).concat(declined.filter(x => !((d && d.invitations) || []).some(i => i.token === x.token)));
        r.loaded = true;
      } catch (e) { if (!quiet) this.notify(e.message, "err"); }
      finally { r.loading = false; }
    },
    rnRecuesCount() { return (this.reseau.recues.list || []).filter(i => !i._declined && i.statut !== "acceptee").length; },
    async rnAccept(inv) {
      const r = this.reseau.recues; if (r.busy || (inv && inv.peut_accepter === false)) return;
      r.busy = inv.token;
      try {
        const res = await this.api("POST", "/api/invite/" + encodeURIComponent(inv.token) + "/claim");
        if (res && res.suggest_profile) this._rnSuggest(res.suggest_profile);
        inv.statut = "acceptee"; inv.statut_label = "Acceptée";
        r.live = "Invitation acceptée : le dossier est dans « Partagé avec moi ».";
        this.notify(r.live);
        await this.loadShared();
        const it = (this.shared || []).find(s => s.token === inv.token);
        if (it) this.openShared(it);
      } catch (e) { r.live = e.message; this.notify(e.message, "err"); }
      finally { r.busy = ""; }
    },
    async rnOpenRecue(inv) {
      let it = (this.shared || []).find(s => s.token === inv.token);
      if (!it) { await this.loadShared(); it = (this.shared || []).find(s => s.token === inv.token); }
      if (it) this.openShared(it); else this.notify("Ce dossier n'est plus accessible", "err");
    },
    rnDecline(inv) {
      this._convAsk({ title: "Décliner l'invitation ?", ok: "Décliner l'invitation",
        lines: ["Vous ne ferez pas partie de ce groupement : " + (inv.mandataire || "le chef de file") + " sera prévenu.", "Votre adresse ne lui est pas communiquée.", "Ce lien ne fonctionnera plus ensuite."],
        run: async () => {
          const r = this.reseau.recues; if (r.busy) return;
          r.busy = inv.token;
          try {
            await this.api("POST", "/api/invite/" + encodeURIComponent(inv.token) + "/decline");
            inv._declined = true; r.live = "Invitation déclinée."; this.notify(r.live);
          } catch (e) { r.live = e.message; this.notify(e.message, "err"); }
          finally { r.busy = ""; }
        } });
    },

    // ── « Qui me complète ? » : partenaires lot par lot sur un marché ──
    async aoPmLoad() {
      const pid = this.ao.project && this.ao.project.id, pm = this.ao.pm; if (!pid || pm.loading) return;
      pm.loading = true; pm.error = ""; pm.live = "Recherche des partenaires, lot par lot…";
      try {
        const d = await this.api("GET", "/api/projects/" + pid + "/partner-matches");
        if (!this.ao.project || this.ao.project.id !== pid) return;
        pm.d = d; pm.loaded = true; pm.live = this._pmSummary(d);
      } catch (e) { pm.error = (e && e.message) || "Recherche de partenaires momentanément indisponible."; pm.live = pm.error; }
      finally { pm.loading = false; }
    },
    _pmSummary(d) {
      const lots = (d && d.lots) || [];
      if (!lots.length) return "Aucun lot à compléter d'après le dossier.";
      const n = lots.reduce((s, l) => s + (l.reseau || []).length + (l.sirene || []).length, 0);
      return lots.length + " " + this.plFr(lots.length, "lot à compléter", "lots à compléter") + " · " + n + " " + this.plFr(n, "entreprise proposée", "entreprises proposées") + ".";
    },
    async aoPmLot(l) {
      const pid = this.ao.project && this.ao.project.id, pm = this.ao.pm; if (!pid || pm.lotBusy || !l || !l.num) return;
      pm.lotBusy = String(l.num);
      try {
        const d = await this.api("GET", "/api/projects/" + pid + "/partner-matches?lot=" + encodeURIComponent(l.num));
        const nl = ((d && d.lots) || [])[0];
        if (nl && pm.d) {
          const i = pm.d.lots.findIndex(x => String(x.num) === String(l.num));
          if (i >= 0) pm.d.lots.splice(i, 1, nl);
          ((d && d.warnings) || []).forEach(w => { if (!(pm.d.warnings || []).includes(w)) (pm.d.warnings = pm.d.warnings || []).push(w); });
          const n = (nl.reseau || []).length + (nl.sirene || []).length;
          pm.live = "Lot " + l.num + " : " + n + " " + this.plFr(n, "entreprise proposée", "entreprises proposées") + ".";
        }
      } catch (e) { this.notify(e.message, "err"); }
      finally { pm.lotBusy = ""; }
    },
    pmLotTitle(l) { return l && l.num ? "Lot " + l.num + " — " + l.label : (l && l.label) || ""; },
    pmLotPart(l) { return l && l.num ? "Lot " + l.num + " — " + l.label : (l && (l.metier_label || l.label)) || ""; },
    pmLotId(l) { return "pml-" + String((l && (l.num || l.metier)) || "x").replace(/[^A-Za-z0-9_-]/g, ""); },
    // « Simuler le groupement » depuis une carte : ajoute l'entreprise à la simulation de la carte
    // « Répondre à plusieurs ? » et lance le calcul (le SEUL pourcentage affiché).
    async aoPmSimulate(c) {
      const m = c.profile_id ? { kind: "reseau", profile_id: c.profile_id, name: c.name, city: c.city || "" }
                             : { kind: "sirene", siret: c.siret, name: c.name, city: c.city || "" };
      if (!this.isCandSelected(m)) {
        if (this.ao.grp.selected.length >= 4) { this.notify("4 partenaires au maximum par simulation : retirez-en un dans « Simuler avec ».", "err"); this.rnScrollTo("grpSim", true); return; }
        this.ao.grp.selected.push(m);
      }
      await this.aoGrpSimulate();
      this.rnScrollTo("grpSim", true);
    },

    // ── Modale d'invitation en 1 clic (vague 3) ──
    // Réseau : Adjugo envoie l'invitation, l'adresse du partenaire n'est JAMAIS affichée au chef de file.
    // SIRENE (hors réseau) : identité relue côté serveur, aucun email, un lien à transmettre.
    rnInviteOpen(card, opts) {
      opts = opts || {}; if (!card) return;
      const kind = card.profile_id ? "reseau" : "sirene";
      const declared = Array.isArray(card.roles_acceptes) && card.roles_acceptes.length > 0;   // [] = tous les rôles (serveur)
      const ok = declared ? card.roles_acceptes.map(r => (r && r.value) || r).filter(r => r === "cotraitant" || r === "sous_traitant") : ["cotraitant", "sous_traitant"];
      const roles = kind === "sirene" || !declared ? ["cotraitant", "sous_traitant"] : ok;
      const inAo = this.view === "aodetail" && this.ao.project;
      this._rinvFocus = opts.focusBack || document.activeElement;
      this.rinv = {
        kind, card, name: card.name || "", profile_id: card.profile_id || "", siret: card.siret || "",
        projectId: opts.projectId || (inAo ? this.ao.project.id : ""), pickProject: !opts.projectId && !inAo,
        roles, role: roles[0] || "cotraitant", noRole: kind === "reseau" && declared && !ok.length,
        lot: opts.lot || "", can_view_docs: true, busy: false, err: "", errCode: "", errProfile: "", url: "", done: "",
      };
      this.$nextTick(() => { const el = document.querySelector(".rinv-modal .modal-b select, .rinv-modal .modal-b input") || document.querySelector(".rinv-modal .x"); if (el && el.focus) el.focus(); });
    },
    rinvClose() {
      this.rinv = null;
      const el = this._rinvFocus; this._rinvFocus = null;
      if (el && el.focus && document.body.contains(el)) this.$nextTick(() => el.focus());
    },
    rinvProjects() { return (this.projects || []).filter(p => p && !p.deleted_at && p.status !== "abandonne"); },
    // « Déjà invité » : la carte d'origine et, sur la fiche du marché, toutes les cartes de la même entreprise.
    _rnMarkInvited(v) {
      if (!v) return;
      if (v.card && typeof v.card === "object") v.card.deja_invite = true;
      const d = this.ao.pm && this.ao.pm.d; if (!d || this.view !== "aodetail" || !this.ao.project || this.ao.project.id !== v.projectId) return;
      (d.lots || []).forEach(l => {
        (l.reseau || []).forEach(c => { if (v.profile_id && c.profile_id === v.profile_id) c.deja_invite = true; });
        (l.sirene || []).forEach(c => { if (v.siret && c.siret === v.siret) c.deja_invite = true; });
      });
    },
    async rinvSend() {
      const v = this.rinv; if (!v || v.busy || v.done) return;
      if (!v.projectId) { v.err = "Choisissez le marché sur lequel inviter ce partenaire."; v.errCode = ""; return; }
      if (v.noRole) return;
      const pid = v.projectId, body = { role: v.role, lot: String(v.lot || "").trim().slice(0, 255), can_view_docs: !!v.can_view_docs, expires_days: 30 };
      v.busy = true; v.err = ""; v.errCode = ""; v.errProfile = "";
      try {
        if (v.kind === "reseau") {
          const r = await this.api("POST", "/api/projects/" + pid + "/reseau/invitations", Object.assign({ profile_id: v.profile_id }, body));
          this._rnMarkInvited(v);
          this.notify((r && r.message) || "Invitation envoyée par Adjugo.");
          this.rinvClose();
        } else {
          const r = await this.api("POST", "/api/projects/" + pid + "/reseau/invitations-sirene", Object.assign({ siret: v.siret }, body));
          const inv = (r && r.invitation) || {};
          v.url = inv.path ? this.inviteUrl(inv) : ((r && r.url) || "");
          v.done = (r && r.message) || "Lien créé : transmettez-le à l'entreprise.";
          this._rnMarkInvited(v);
          if (v.url) this.copyInvite(v.url, true);
        }
        if (this.view === "aodetail" && this.ao.project && this.ao.project.id === pid) { this.aoLoadInvites(); this.aoLoadCotraitants(); this.aoLoadConsortium(); }
        this.loadCotraitants();
      } catch (e) {
        v.err = (e && e.message) || "Invitation impossible pour l'instant."; v.errCode = (e && e.code) || ""; v.errProfile = (e && e.profile_id) || "";
        if (v.errCode === "deja_invite") this._rnMarkInvited(v);
      } finally { if (this.rinv === v) v.busy = false; }
    },
    // 409 « sur_le_reseau » : l'entreprise SIRENE est sur le réseau → on l'invite via sa fiche (Adjugo transmet).
    rinvViaReseau() {
      const v = this.rinv; if (!v || !v.errProfile) return;
      Object.assign(v, { kind: "reseau", profile_id: v.errProfile, roles: ["cotraitant", "sous_traitant"], noRole: false, err: "", errCode: "", errProfile: "", url: "", done: "" });
    },
    rinvShowInvites() { this.rinvClose(); if (this.view === "aodetail") this.rnScrollTo("reseauCard"); },
    // ── Coffre-fort croisé (statuts) + offre commune (mandataire) ──
    ddmm(s) { const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + "/" + m[2] : ""; },
    cxPiece(m, k) { return (m && m.pieces && m.pieces[k]) || { status: "manquant" }; },
    cxLabel(p) {
      const d = p.expiration_date ? this.fmtDate(p.expiration_date) : "";
      return ({ present: "présente", valide_jusquau: "valide → " + d, expire_avant_limite: "expire le " + d, expire: "expirée" + (d ? " le " + d : ""), manquant: "à fournir" })[p.status] || p.status;
    },
    // Sous le tableau (partenaire) : seulement ce qu'il ne montre pas — les attestations expirées
    // ou qui expirent avant la date limite — et une ligne de synthèse pour les pièces à fournir.
    cxExpirations(g) { return ((g && g.alert_items) || []).filter(a => a && a.kind !== "a_fournir").map(a => a.text); },
    cxResume(g) { return (g && g.a_fournir && g.a_fournir.resume) || ""; },
    cxTitle(m, k) {
      const p = this.cxPiece(m, k);
      return (p.name ? p.name + " — " : "") + (({ present: "Pièce fournie (sans date d'expiration)", valide_jusquau: "Valide au-delà de la date limite", expire_avant_limite: "Expire AVANT la date limite : à renouveler", expire: "Expirée : à renouveler", manquant: "Pièce non fournie" })[p.status] || "");
    },
    async aoDownloadPiece(p) {
      if (!p || !p.piece_id) return;
      try {
        const r = await fetch("/api/projects/" + this.ao.project.id + "/contribution-pieces/" + p.piece_id, { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Téléchargement impossible");
        this.saveBlob(await r.blob(), p.name || "piece");
      } catch (e) { this.notify(e.message, "err"); }
    },
    freezeTotal() {
      const o = this.ao.share.consortium && this.ao.share.consortium.offre; if (!o || o.total_ht_estime == null) return null;
      const lead = (o.lead_total_ht == null && Number(this.ao.share.leadTotal) > 0) ? Number(this.ao.share.leadTotal) : 0;
      return o.total_ht_estime + lead;
    },
    canFreeze() { const o = this.ao.share.consortium && this.ao.share.consortium.offre; return !!(o && !o.frozen && o.total_ht_estime != null); },
    freezeMissing() {
      const cs = this.ao.share.consortium || {}; const miss = (cs.readiness && cs.readiness.missing) || [];
      if (!(cs.readiness && cs.readiness.invited)) return ["Invitez au moins un partenaire et attendez sa part"];
      return miss.length ? miss : ["Aucune part soumise avec un prix de lot pour l'instant"];
    },
    async aoFreezeOffer() {
      // Vague 2 : « Figer l'offre » = « Figer l'offre et générer la convention » (même geste,
      // même confirmation). L'ancienne route ne sert plus que de repli si la convention n'a pas pu se charger.
      if (this.convVisible() && this.ao.conv.d) { await this.aoConvAskGenerate(true); return; }
      const cs = this.ao.share.consortium, o = cs && cs.offre; if (!o || !this.canFreeze()) return;
      const lead = (o.lead_total_ht == null && Number(this.ao.share.leadTotal) > 0) ? Number(this.ao.share.leadTotal) : null;
      let msg = "Figer l'offre commune ?\n\nTotal prévisionnel : " + this.eur(this.freezeTotal()) + " HT"
        + (lead != null ? " (dont votre part " + this.eur(lead) + " HT)" : (o.lead_total_ht == null ? " — sans votre part (aucune estimation enregistrée)" : ""))
        + ".\nChaque partenaire verra ce total.";
      if (o.warning_two_members) msg += "\n\nÀ deux, le total révèle mécaniquement la part de l'autre.";
      if (!confirm(msg)) return;
      this.ao.share.freezing = true;
      try {
        const r = await this.api("POST", "/api/projects/" + this.ao.project.id + "/offre/figer", lead != null ? { lead_total_ht: lead } : {});
        this.notify("Offre commune figée — total " + this.eur(r.total_ht) + " HT");
        await this.aoLoadConsortium();
      } catch (e) {
        // 409 « convention_generee » : l'offre est déjà figée par la convention → on y renvoie.
        if (e.status === 409 && (e.code === "convention_generee" || e.code === "convention_a_generer")) { this.notify(e.message, "err"); await this.aoConvLoad(true); this.aoConvScroll("convCard"); }
        else this.notify(e.message, "err");
      }
      finally { this.ao.share.freezing = false; }
    },
    async aoUnfreezeOffer() {
      const cv = this.ao.conv.d, generated = !!(cv && (cv.status === "a_signer" || cv.status === "signee"));
      const msg = "Défiger l'offre commune ? Les partenaires ne verront plus le total tant qu'elle n'est pas refigée."
        + (generated ? "\n\nLa convention de groupement deviendra caduque : les accords déjà enregistrés tombent et il faudra la régénérer." : "");
      if (!confirm(msg)) return;
      this.ao.share.freezing = true;
      try { await this.api("DELETE", "/api/projects/" + this.ao.project.id + "/offre/figer"); this.notify("Offre commune défigée"); await this.aoLoadConsortium(); if (this.convVisible()) await this.aoConvLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.share.freezing = false; }
    },
    // ── « Monter le groupement » (vague 2) : assistant, génération (= figer l'offre), accords ──
    // Règle : aucun chiffre ni statut n'est calculé ici ; tout vient de l'API (contrat :
    // docs/COTRAITANCE_V2_VAGUE2_API.md). Le texte de la convention passe par convHtml() (échappé).
    convVisible() {
      const st = this.ao.grp.state, d = this.ao.conv.d;
      return !!((st && ((Number(st.etape) || 1) >= 2 || st.convention)) || (d && d.status && d.status !== "aucune"));
    },
    convHtml(md) { return convMdToHtml(md); },
    convGenerated() { const s = this.ao.conv.d && this.ao.conv.d.status; return s === "a_signer" || s === "signee" || s === "perimee"; },
    convStatusPill(s) { return ({ a_signer: "a_etudier", signee: "go", perimee: "no_go" })[s] || "neutral"; },
    convSigPill(s) { return ({ signed: "go", hors_ligne: "go", pending: "a_etudier", perimee: "no_go" })[s] || "neutral"; },
    convMemberLabel(m) { return ({ mandataire: "Chef de file", partenaire: "Partenaire", hors_ligne: "Partenaire · accord hors ligne" })[m] || ""; },
    convHash(d) { return String((d && d.content_hash) || "").slice(0, 12); },
    convTotal(d) { if (!d) return null; return this.convGenerated() ? d.total_offre_ht : d.total_estime_ht; },
    convMySig() { const d = this.ao.conv.d; return ((d && d.signatures) || []).find(s => s.membre === "mandataire") || null; },
    convOtherClauses(fi) { return ((fi && fi.clauses) || []).filter(x => x && x !== fi.extrait); },
    convPret() { const st = this.ao.grp.state; return (st && st.pret) || null; },
    eur2(v) {   // montants de la convention : au centime près (comme le texte et le PDF), jamais arrondis
      if (v == null || v === "") return "—";
      const n = Number(v); if (!isFinite(n)) return "—";
      try { return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 }).format(n); }
      catch (e) { return n.toLocaleString("fr-FR") + " €"; }
    },
    convWhen(s) {
      if (!s) return "";
      try {
        const d = new Date(_isoUtc(s)); if (isNaN(d.getTime())) return String(s);
        return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }) + " à " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
      } catch (e) { return String(s); }
    },
    _convMergeState(st) {   // le stepper et « Prêt à déposer » suivent la convention sans recharger la fiche
      if (!st || typeof st !== "object") return;
      if (this.ao.grp.state) Object.assign(this.ao.grp.state, st); else this.ao.grp.state = st;
      this.aoDepotLoadSoon();
    },
    _convForm(d) {
      const hl = {};
      (d.candidats_hors_ligne || []).forEach(c => {
        const cur = (d.membres_hors_ligne || []).find(x => x.link_id === c.link_id);
        hl[c.link_id] = { on: !!cur, prix_lot_ht: cur && cur.prix_lot_ht != null ? cur.prix_lot_ht : "",
                          lot: (cur && cur.lot) || c.lot || "", representant_legal: (cur && cur.representant_legal) || c.representant_legal || "",
                          signataire_qualite: (cur && cur.signataire_qualite) || "" };
      });
      return { forme: d.forme || "", mandataire_solidaire: !!d.mandataire_solidaire, habilitation: Object.assign({}, d.habilitation || {}),
               params: Object.assign({}, d.params || {}), hl, masquer_repartition: !!d.masquer_repartition };
    },
    _convApply(d, keepForm) {
      const c = this.ao.conv, keep = !!(keepForm && c.f && this.convDirty());
      c.d = d;
      if (!keep) c.f = this._convForm(d);
      else { const fresh = this._convForm(d); Object.keys(fresh.hl).forEach(k => { if (!c.f.hl[k]) c.f.hl[k] = fresh.hl[k]; }); }
      c.loaded = true; c.error = "";
      const ms = (d && d.ma_signature) || {};
      if (!c.accord.nom) c.accord.nom = ms.signataire_nom || "";
      if (!c.accord.qualite) c.accord.qualite = ms.signataire_qualite || "";
      if (c.accord.hash !== ((d && d.content_hash) || "")) { c.accord.accepte = false; c.accord.hash = (d && d.content_hash) || ""; }
      if (d && d.state) this._convMergeState(d.state);
      if (d && d.status === "perimee") this._convLoadStaleReason(); else c.staleReason = "";
    },
    // Convention caduque : la cause n'est pas dans la réponse de la convention, mais le serveur
    // la journalise (« convention.perimee »). Ce détail est une note interne : on le traduit en
    // phrase simple (_convStaleCause) ; cause inconnue → le bandeau garde sa phrase générique.
    async _convLoadStaleReason() {
      const pid = this.ao.project && this.ao.project.id; if (!pid) return;
      try {
        const rows = await this.api("GET", "/api/projects/" + pid + "/audit?limit=100") || [];
        if (this.ao.project && this.ao.project.id === pid && this.ao.conv.d && this.ao.conv.d.status === "perimee")
          this.ao.conv.staleReason = this._convStaleCause(rows);
      } catch (e) { /* cause indisponible : le bandeau reste générique */ }
    },
    _convStaleCause(rows) {
      const list = Array.isArray(rows) ? rows : [];
      const i = list.findIndex(x => x && x.action === "convention.perimee"); if (i < 0) return "";
      const det = String(list[i].detail || "").trim().replace(/\s+/g, " "), low = det.toLowerCase();
      const cap = t => t.charAt(0).toUpperCase() + t.slice(1);
      const fixed = {
        "défigée par le chef de file": "L'offre commune a été défigée.",
        "chiffrage du chef de file modifié": "Votre chiffrage (votre part de l'offre) a été modifié.",
        // Anciennes entrées du journal (avant le passage à « chef de file ») : même message.
        "défigée par le mandataire": "L'offre commune a été défigée.",
        "chiffrage du mandataire modifié": "Votre chiffrage (votre part de l'offre) a été modifié.",
        "composition du groupement modifiée": "La composition du groupement a changé.",
        "plan de groupement retiré": "Le plan de groupement a été retiré.",
        "partenaire hors ligne retiré du marché": "Un partenaire hors ligne a été retiré du marché.",
        "les parts, les prix ou la composition ont changé depuis la génération": "Une part, un prix ou la composition a changé depuis sa génération.",
      };
      if (fixed[low]) return fixed[low];
      let m = det.match(/^part de (.+) modifiée$/i);
      if (m) {
        // Un refus d'invitation passe par le même chemin : il est journalisé juste après
        // (« invite.declined », détail = l'entreprise), dans la même minute.
        const who = m[1], t0 = Date.parse(_isoUtc(list[i].at));
        const declined = list.slice(0, i).some(x => x && x.action === "invite.declined"
          && String(x.detail || "").replace(/\s+/g, " ").trim() === who && Math.abs(Date.parse(_isoUtc(x.at)) - t0) < 60000);
        return cap(who) + (declined ? " a décliné l'invitation." : " a modifié sa part.");
      }
      m = det.match(/^nouveau partenaire invité \((.+)\)$/i);
      if (m) return m[1] === "sans nom" ? "Un nouveau partenaire a été invité." : cap(m[1]) + " a été invité dans le groupement.";
      m = det.match(/^(.+) retiré$/i);
      if (m) return cap(m[1]) + " a été retiré du groupement.";
      return "";
    },
    _convSay(msg) { this.ao.conv.live = msg; this.notify(msg); },
    // Les messages d'erreur s'affichent À CÔTÉ du bouton qui les a provoqués (zone) : « top » (haut de
    // la carte), « fi » (règlement), « foot » (pied de l'assistant), « accords » (suivi), « accord » (mon accord).
    _convErrZone() { return (this.convGenerated() && !this.ao.conv.editOpen) ? "top" : "foot"; },
    _convFail(e, at) { const c = this.ao.conv; c.err = (e && e.message) || "Action impossible pour l'instant."; c.errCode = (e && e.code) || ""; c.missing = (e && Array.isArray(e.missing)) ? e.missing : []; c.errAt = at || this._convErrZone(); },
    _convErr(msg, at) { const c = this.ao.conv; c.err = msg; c.errCode = ""; c.missing = []; c.errAt = at || this._convErrZone(); },
    // peut_generer = false : le message s'affiche là où la liste des manques est visible (pied de
    // l'assistant en brouillon ; haut de la carte, au-dessus du bandeau « plus à jour », sinon) et on y va.
    _convCantGenerate(scroll) {
      const c = this.ao.conv, d = c.d || {}, gen = this.convGenerated();
      this._convErr((gen ? "Impossible de régénérer la convention" : "Impossible de générer la convention")
        + " : complétez d'abord les éléments listés ci-dessous.", gen ? "top" : "foot");
      // Convention générée et encore à jour : aucune autre liste en haut de la carte → elle va dans le message.
      if (gen && d.status !== "perimee") c.missing = (d.manques || []).map(m => String(m || "")).filter(Boolean);
      if (gen) this.aoConvScroll("convCard"); else if (scroll) this.aoConvScroll("convFoot");
    },
    convErrAt(z) { return !!this.ao.conv.err && (this.ao.conv.errAt || "top") === z; },
    convErrClear() { const c = this.ao.conv; c.err = ""; c.errCode = ""; c.missing = []; },
    async aoConvLoad(quiet) {
      const pid = this.ao.project && this.ao.project.id; if (!pid) return;
      const c = this.ao.conv; if (c.loading) return;
      c.loading = true; if (!quiet) c.error = "";
      try {
        const d = await this.api("GET", "/api/projects/" + pid + "/groupement/convention");
        if (this.ao.project && this.ao.project.id === pid) this._convApply(d, true);
      } catch (e) { if (this.ao.project && this.ao.project.id === pid) this.ao.conv.error = e.message || "La convention est momentanément indisponible."; }
      finally { c.loading = false; }
    },
    _convNorm(v) { return (v === "" || v === undefined) ? null : v; },
    // Mise à jour PARTIELLE (contrat 3.2) : seuls les champs modifiés partent au serveur.
    convDiff() {
      const c = this.ao.conv, d = c.d, f = c.f, body = {}; if (!d || !f) return body;
      const same = (a, b) => JSON.stringify(this._convNorm(a)) === JSON.stringify(this._convNorm(b));
      if ((f.forme || "") !== (d.forme || "")) body.forme = f.forme || "";
      if (f.forme === "conjoint" && (body.forme !== undefined || !!f.mandataire_solidaire !== !!d.mandataire_solidaire)) body.mandataire_solidaire = !!f.mandataire_solidaire;
      const hab = {};
      Object.keys(f.habilitation || {}).forEach(k => { if (k !== "representer" && !!f.habilitation[k] !== !!(d.habilitation || {})[k]) hab[k] = !!f.habilitation[k]; });
      if (Object.keys(hab).length) body.habilitation = hab;
      const prm = {};
      Object.keys(f.params || {}).forEach(k => { if (!same(f.params[k], (d.params || {})[k])) prm[k] = this._convNorm(f.params[k]); });
      if (Object.keys(prm).length) body.params = prm;
      const pick = e => ({ link_id: Number(e.link_id), prix_lot_ht: this._convNorm(e.prix_lot_ht), lot: e.lot || "", representant_legal: e.representant_legal || "", signataire_qualite: e.signataire_qualite || "" });
      const hl = Object.keys(f.hl || {}).filter(id => f.hl[id].on).map(id => pick(Object.assign({ link_id: id }, f.hl[id])));
      const cur = (d.membres_hors_ligne || []).map(pick);
      const byId = a => a.slice().sort((x, y) => x.link_id - y.link_id);
      if (JSON.stringify(byId(hl)) !== JSON.stringify(byId(cur))) body.membres_hors_ligne = hl;
      if ((d.status === "draft" || d.status === "aucune") && !!f.masquer_repartition !== !!d.masquer_repartition) body.masquer_repartition = !!f.masquer_repartition;
      return body;
    },
    convDirty() { return Object.keys(this.convDiff()).length > 0; },
    convIsDefault(p) { const f = this.ao.conv.f; return !!f && JSON.stringify(this._convNorm(f.params[p.key])) === JSON.stringify(this._convNorm(p.defaut)); },
    convPickForme(v) { const f = this.ao.conv.f; if (!f) return; f.forme = v; if (v !== "conjoint") f.mandataire_solidaire = false; },
    async aoConvSave(extra) {
      const c = this.ao.conv, pid = this.ao.project && this.ao.project.id; if (!pid || !c.d || c.busy) return false;
      const body = Object.assign(this.convDiff(), extra || {});
      if (!Object.keys(body).some(k => k !== "confirmer_modification")) { this._convSay("Rien à enregistrer : aucun choix n'a changé."); return true; }
      c.busy = "save"; c.err = ""; c.errCode = ""; c.missing = [];
      try {
        const d = await this.api("PUT", "/api/projects/" + pid + "/groupement/convention", body);
        if (!this.ao.project || this.ao.project.id !== pid) return false;
        this._convApply(d);
        this._convSay(body.confirmer_modification ? "Convention repassée en brouillon : générez-la à nouveau quand vos choix sont faits." : "Brouillon enregistré.");
        return true;
      } catch (e) {
        if (e.status === 409 && e.code === "convention_generee") {
          this._convAsk({ title: "Modifier la convention ?", ok: "Modifier quand même",
            lines: [{ t: "Modifier la convention annule les accords déjà enregistrés.", warn: true },
                    { t: "Elle repasse en brouillon : il faudra la générer à nouveau, et chaque membre devra redonner son accord." }],
            run: () => this.aoConvSave({ confirmer_modification: true }) });
        } else this._convFail(e);
        return false;
      } finally { c.busy = ""; }
    },
    async aoConvToggleMasquer(ev) {   // option du brouillon seulement : enregistrée tout de suite (aperçu et PDF)
      const f = this.ao.conv.f; if (!f) return;
      f.masquer_repartition = !!(ev && ev.target && ev.target.checked);
      await this.aoConvSave();
    },
    async aoConvRelire() {
      const c = this.ao.conv, pid = this.ao.project && this.ao.project.id; if (!pid || c.busy) return;
      c.busy = "relire"; c.err = "";
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/convention/relire-dce");
        if (!this.ao.project || this.ao.project.id !== pid) return;
        if (c.d && r && r.forme_imposee) c.d.forme_imposee = r.forme_imposee;
        this._convSay("Dossier du marché relu.");
        c.busy = ""; await this.aoConvLoad(true);   // avertissements à jour (le formulaire en cours est conservé)
      } catch (e) { this._convFail(e, "fi"); }
      finally { c.busy = ""; }
    },
    // fromCockpit : l'action vient du cockpit (autre carte) → on amène l'utilisateur à la convention.
    async aoConvAskGenerate(fromCockpit) {
      const c = this.ao.conv; if (!c.d || c.busy) return;
      if (this.convDirty() && !(await this.aoConvSave())) return;
      const d = this.ao.conv.d;
      // Déjà générée ou plus à jour : c'est une régénération (même route, sa propre confirmation).
      if (this.convGenerated()) { this.aoConvAskRegenerate(null, fromCockpit); return; }
      if (!d.peut_generer) { this._convCantGenerate(fromCockpit); return; }
      if (fromCockpit) this.aoConvScroll("convCard");
      const total = d.total_estime_ht, two = (d.membres || []).length === 2;
      const lines = [
        { t: total != null ? "Le total de l'offre commune (" + this.eur2(total) + " HT) sera figé et révélé à tous les partenaires."
                           : "Le total de l'offre commune sera figé et révélé à tous les partenaires." },
        { t: "L'annexe de répartition (la part et le prix de vente de chaque membre) sera visible par tous les membres du groupement." },
      ];
      if (two) lines.push({ t: "À 2 membres, le total révèle à chacun la part de l'autre.", warn: true });
      lines.push({ t: "Chaque partenaire invité recevra la convention à valider dans son espace." },
                 { t: "Si une part, un prix ou la composition change ensuite, la convention ne sera plus à jour et devra être régénérée." },
                 { t: d.avertissement, warn: true });
      this._convAsk({ title: "Figer l'offre et générer la convention ?", lines, ok: "Figer l'offre et générer", run: () => this.aoConvGenerate(false) });
    },
    aoConvAskRegenerate(apiMsg, fromCockpit) {
      const d = this.ao.conv.d; if (!d) return;
      if (!d.peut_generer) { this._convCantGenerate(fromCockpit); return; }   // sinon le serveur refuserait (422)
      if (fromCockpit) this.aoConvScroll("convCard");
      const lines = [];
      if (apiMsg) lines.push({ t: apiMsg });
      lines.push({ t: "Une nouvelle version est créée, avec une nouvelle empreinte." });
      lines.push(d.status === "perimee" ? { t: "Les accords donnés sur l'ancienne version sont caducs : chaque membre devra donner son accord sur la nouvelle." }
                                        : { t: "Les accords déjà enregistrés sont annulés : chaque membre devra redonner son accord.", warn: true });
      lines.push({ t: "Le total de l'offre est recalculé, figé et révélé à tous les partenaires, avec l'annexe de répartition." });
      if ((d.membres || []).length === 2) lines.push({ t: "À 2 membres, le total révèle à chacun la part de l'autre.", warn: true });
      lines.push({ t: d.avertissement, warn: true });
      this._convAsk({ title: "Régénérer la convention ?", lines, ok: "Régénérer la convention", run: () => this.aoConvGenerate(true) });
    },
    async aoConvGenerate(regen) {
      const c = this.ao.conv, pid = this.ao.project && this.ao.project.id; if (!pid || c.busy) return;
      c.busy = "generer"; c.err = ""; c.errCode = ""; c.missing = [];
      try {
        const d = await this.api("POST", "/api/projects/" + pid + "/groupement/convention/generer", { regenerer: !!regen });
        if (!this.ao.project || this.ao.project.id !== pid) return;
        this._convApply(d); c.textOpen = false; c.editOpen = false;
        const n = Number(d.emails_envoyes) || 0;
        this._convSay("Convention générée (version " + d.version + ")" + (n ? " — " + (n > 1 ? n + " partenaires prévenus" : "1 partenaire prévenu") + " par email." : "."));
        this.aoLoadConsortium(); this.aoLoadInvites();
      } catch (e) {
        if (e.status === 409 && e.code === "deja_generee") this.aoConvAskRegenerate(e.message);
        else { const z = this._convErrZone(); this._convFail(e, z); if (z === "top") this.aoConvScroll("convCard"); }
      } finally { c.busy = ""; }
    },
    async aoConvValider() {
      const c = this.ao.conv, d = c.d, pid = this.ao.project && this.ao.project.id; if (!pid || !d || c.busy) return;
      if (!c.accord.accepte) { this._convErr("Cochez « J'ai lu la convention et je donne mon accord ».", "accord"); return; }
      if (!(c.accord.nom || "").trim()) { this._convErr("Indiquez le nom de la personne qui donne l'accord.", "accord"); return; }
      c.busy = "valider"; c.err = ""; c.errCode = ""; c.missing = [];
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/convention/valider",
          { content_hash: d.content_hash, signataire_nom: c.accord.nom.trim(), signataire_qualite: (c.accord.qualite || "").trim(), accepte: true });
        if (!this.ao.project || this.ao.project.id !== pid) return;
        this._convApply(r, true); this._convSay("Votre accord est enregistré.");
      } catch (e) {
        this._convFail(e, "accord");
        if (["texte_modifie", "perimee", "pas_generee", "statut"].includes(e.code)) { c.busy = ""; await this.aoConvLoad(true); }
      } finally { c.busy = ""; }
    },
    aoConvAskHorsLigne(s, on) {
      const d = this.ao.conv.d; if (!d || !s || s.link_id == null) return;
      if (!on) {
        this._convAsk({ title: "Retirer l'accord hors ligne ?", ok: "Retirer l'accord",
          lines: [{ t: "L'accord de " + s.company + " repasse « En attente »." }], run: () => this.aoConvHorsLigne(s.link_id, false, {}) });
        return;
      }
      const prev = (d.membres_hors_ligne || []).find(x => x.link_id === s.link_id) || (d.candidats_hors_ligne || []).find(x => x.link_id === s.link_id) || {};
      this._convAsk({ title: "Enregistrer l'accord hors ligne ?", ok: "Enregistrer l'accord",
        lines: [{ t: "Vous déclarez avoir recueilli l'accord de " + s.company + " sur la version " + d.version + " de la convention, en dehors d'Adjugo (sur papier, par exemple)." },
                { t: "Le PDF indiquera que cet accord a été recueilli hors ligne et déclaré par vous, chef de file." }],
        fields: [{ key: "nom", label: "Nom de la personne qui a donné l'accord", value: prev.representant_legal || "", max: 255 },
                 { key: "qualite", label: "Qualité (gérant, président…)", value: prev.signataire_qualite || "", max: 120 }],
        run: (v) => this.aoConvHorsLigne(s.link_id, true, v) });
    },
    async aoConvHorsLigne(linkId, on, v) {
      const c = this.ao.conv, pid = this.ao.project && this.ao.project.id; if (!pid || c.busy) return;
      c.busy = "horsligne"; c.err = ""; c.errCode = ""; c.missing = [];
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/convention/hors-ligne/" + linkId,
          { accord_recueilli: !!on, signataire_nom: (v && v.nom) || "", signataire_qualite: (v && v.qualite) || "" });
        if (!this.ao.project || this.ao.project.id !== pid) return;
        this._convApply(r, true); this._convSay(on ? "Accord hors ligne enregistré." : "Accord hors ligne retiré.");
      } catch (e) {
        this._convFail(e, "accords");
        if (e.status === 409) { c.busy = ""; await this.aoConvLoad(true); }
      } finally { c.busy = ""; }
    },
    async _pdfFetch(url, fallbackName) {
      const r = await fetch(url, { headers: this.token ? { Authorization: "Bearer " + this.token } : {} });
      if (!r.ok) {
        let m = r.status === 429 ? TOO_MANY_MSG : "Téléchargement impossible pour l'instant.";
        try { const j = await r.json(), dd = j && j.detail; m = (typeof dd === "string" ? dd : (dd && dd.message)) || m; } catch (e) {}
        throw new Error(m);
      }
      const cd = r.headers.get("Content-Disposition") || "";
      let name = fallbackName;
      const m1 = cd.match(/filename\*=UTF-8''([^;]+)/i), m2 = cd.match(/filename="?([^";]+)"?/i);
      try { if (m1) name = decodeURIComponent(m1[1]); else if (m2) name = m2[1]; } catch (e) {}
      this.saveBlob(await r.blob(), name);
    },
    async aoConvPdf() {
      const c = this.ao.conv, pid = this.ao.project && this.ao.project.id; if (!pid || c.busy) return;
      c.busy = "pdf";
      try { await this._pdfFetch("/api/projects/" + pid + "/groupement/convention/pdf", "Convention_groupement.pdf"); }
      catch (e) { this.notify(e.message, "err"); }
      finally { c.busy = ""; }
    },
    aoConvScroll(ref) {
      this.$nextTick(() => {
        let el = this.$refs[ref];
        if (Array.isArray(el)) el = el[0];   // ref posé dans un v-for (carte de la convention) → tableau
        if (!el) return;
        if (el.scrollIntoView) el.scrollIntoView({ block: "start", behavior: "smooth" });
        if (el.focus) el.focus({ preventScroll: true });
      });
    },
    aoConvShowCoffre() {
      this.ao.share.cockpitOpen = true; this.aoLoadConsortium();
      this.$nextTick(() => { const el = this.$refs.reseauCard; if (el && el.scrollIntoView) el.scrollIntoView({ block: "start", behavior: "smooth" }); });
    },
    async aoConvPrepareDocs() { await this.aoGenerate(); await this.aoGrpReloadState(); },
    // ── Étape 5 « Prêt à déposer » (vague 4, contrat docs/COTRAITANCE_V2_VAGUE4_API.md §5) ──
    // Les 4 contrôles viennent de GET /groupement/depot, calculables à tout moment ; affichés
    // « 3 contrôles sur 4 » (un seul pourcentage dans le produit : le score de groupement).
    // Chaque manque (texte tel quel de l'API) est rangé sous son contrôle, avec l'action qui le règle.
    depotShown() {
      const st = this.ao.grp.state; if (!st || !this.convVisible()) return false;
      const cv = this.ao.conv.d && this.ao.conv.d.status;
      // Dès qu'un partenaire est invité (état « invitation » et au-delà) ou qu'une convention existe.
      return (Number(st.index) || 0) >= 3 || (Number(st.etape) || 1) >= 3 || (!!cv && cv !== "aucune") || st.state === "depose" || !!(this.ao.depot.d && this.ao.depot.d.depose);
    },
    aoDepotLoadSoon() {
      clearTimeout(this._depotT);
      this._depotT = setTimeout(() => { if (this.depotShown()) this.aoDepotLoad(); }, 200);
    },
    async aoDepotLoad() {
      const pid = this.ao.project && this.ao.project.id, dp = this.ao.depot; if (!pid) return;
      if (dp.loading) { dp.again = true; return; }   // un état plus récent arrive : relire après la lecture en cours
      dp.loading = true;
      try {
        const d = await this.api("GET", "/api/projects/" + pid + "/groupement/depot");
        if (this.ao.project && this.ao.project.id === pid) { dp.d = d; dp.pid = pid; dp.loaded = true; dp.err = ""; }
      } catch (e) { if (this.ao.project && this.ao.project.id === pid) dp.err = e.message || "Les contrôles avant dépôt sont momentanément indisponibles."; }
      finally { dp.loading = false; if (dp.again && this.ao.depot === dp) { dp.again = false; this.aoDepotLoad(); } }
    },
    depotPret() { const d = this.ao.depot.d; return (d && d.pret) || this.convPret() || null; },
    depotIsDeposed() { const d = this.ao.depot.d; return !!(d && d.depose) || !!(this.ao.grp.state && this.ao.grp.state.state === "depose"); },
    depotStatus() { const d = this.ao.depot.d; return (d && d.status) || (this.ao.project && this.ao.project.status) || ""; },
    depotCount(p) { const n = Number(p && p.n_ok) || 0; return n + " " + (n > 1 ? "contrôles" : "contrôle") + " sur " + (Number(p && p.n_total) || 4); },
    _convPretGroup(m) { return /^part de/i.test(m) ? "parts_soumises" : /^formulaire/i.test(m) ? "cerfa_generes" : /^convention/i.test(m) ? "convention_signee" : "attestations_ok"; },
    convPretChecks() {
      const p = this.depotPret(); if (!p) return [];
      const ch = p.checks || {}, lib = p.libelles || {}, man = (p.manques || []).map(m => String(m || "")).filter(Boolean);
      const cv = this.ao.conv.d && this.ao.conv.d.status, generated = cv === "a_signer" || cv === "signee";
      const relance = this.aoPendingRelancables().length > 0;
      const conv = !cv || cv === "aucune" || cv === "draft"
        ? { cta: "Préparer la convention", icon: "file-signature", action: () => this.aoConvScroll("convFoot") }
        : cv === "perimee" ? { cta: "Régénérer la convention", icon: "refresh-cw", action: () => this.aoConvAskRegenerate() }
        : { cta: "Voir les accords", icon: "users-round", action: () => this.aoConvScroll("convAccords") };
      return [
        { key: "parts_soumises", label: "Parts de tous les partenaires soumises, avec leur prix de vente", cta: relance ? "Relancer les partenaires" : "Voir les parts", icon: relance ? "send" : "users-round", action: () => relance ? this.aoRelanceRetardataires() : this.aoConvShowCoffre() },
        { key: "attestations_ok", label: "Attestations de tous les membres valides à la date limite", cta: "Voir les attestations", icon: "folder-lock", action: () => this.aoConvShowCoffre() },
        Object.assign({ key: "convention_signee", label: "Convention validée par tous les membres" }, conv),
        generated ? { key: "cerfa_generes", label: "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention", cta: "Préparer mes documents", icon: "file-text", action: () => this.aoConvPrepareDocs() }
                  : { key: "cerfa_generes", label: "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention", wait: "Après la convention" },
      ].filter(k => k.key in ch).map(k => Object.assign(k, { label: lib[k.key] || k.label, ok: !!ch[k.key], manques: man.filter(m => this._convPretGroup(m) === k.key) }));
    },
    convPretRest() {   // manques qui ne se rangent sous aucun contrôle encore à faire (jamais masqués)
      const p = this.depotPret(); if (!p) return [];
      const open = this.convPretChecks().filter(k => !k.ok).map(k => k.key);
      return (p.manques || []).map(m => String(m || "")).filter(m => m && !open.includes(this._convPretGroup(m)));
    },
    // « Marquer déposé » : avertir, pas bloquer. Dossier complet → confirmation simple ; sinon la
    // liste de ce qui manque et « Marquer déposé quand même » (le chef de file a pu déposer hors d'Adjugo).
    aoDepotAsk() {
      const p = this.depotPret() || {};
      if (p.pret) {
        this._convAsk({ title: "Marquer le dossier comme déposé ?", ok: "Marquer déposé", run: () => this.aoDepotMark(false),
          lines: ["Le marché passe à l'étape « Déposé ».", "Chaque partenaire le verra dans son journal.",
                  "Les relances automatiques s'arrêtent pour ce marché.", "En cas d'erreur, vous pourrez retirer ce marquage."] });
        return;
      }
      this._depotAskIncomplete(p.manques || [], (Number(p.n_total) || 4) - (Number(p.n_ok) || 0));
    },
    _depotAskIncomplete(manques, n) {
      const list = (manques || []).map(m => String(m || "")).filter(Boolean);
      const lines = [{ t: (n > 0 ? n + (n > 1 ? " contrôles avant dépôt ne sont pas réglés." : " contrôle avant dépôt n'est pas réglé.") : "Le dossier n'est pas complet.") + " Le marquer déposé quand même ? Vous avez peut-être déposé hors d'Adjugo.", warn: true }];
      list.slice(0, 5).forEach(m => lines.push({ t: m }));
      if (list.length > 5) lines.push({ t: "et " + (list.length - 5) + " autre" + (list.length - 5 > 1 ? "s" : "") });
      lines.push({ t: "Chaque partenaire verra le marquage dans son journal ; les relances automatiques s'arrêtent." });
      this._convAsk({ title: "Le dossier n'est pas complet", lines, ok: "Marquer déposé quand même", run: () => this.aoDepotMark(true) });
    },
    async aoDepotMark(confirmer) {
      const pid = this.ao.project && this.ao.project.id, dp = this.ao.depot; if (!pid || dp.busy) return;
      dp.busy = "deposer"; dp.err = "";
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/deposer", { confirmer: !!confirmer });
        if (!this.ao.project || this.ao.project.id !== pid) return;
        if (r.status) this.ao.project.status = r.status;
        if (r.state) this._convMergeState(r.state);
        dp.d = Object.assign({}, dp.d || {}, { depose: true, status: r.status || "envoye" }, r.pret ? { pret: r.pret } : {});
        dp.live = r.deja_depose ? "Le dossier était déjà marqué déposé." : "Dossier marqué déposé.";
        this.notify(dp.live);
        this.$nextTick(() => { let el = this.$refs.depotCard; if (Array.isArray(el)) el = el[0]; if (el && el.focus) el.focus({ preventScroll: true }); });
      } catch (e) {
        if (e.status === 409 && e.code === "pas_pret") { dp.busy = ""; await this.aoDepotLoad(); const d = e.detail || {}; this._depotAskIncomplete(d.manques || [], 0); return; }
        dp.err = e.message || "Marquage impossible pour le moment.";
      } finally { dp.busy = ""; }
    },
    aoDepotAskCancel() {
      this._convAsk({ title: "Retirer le marquage « déposé » ?", ok: "Retirer le marquage", run: () => this.aoDepotUnmark(),
        lines: ["À faire seulement si le dossier n'a pas été déposé : le marché retrouve son statut d'avant.",
                "Le retrait est inscrit dans le journal de chaque partenaire."] });
    },
    async aoDepotUnmark() {
      const pid = this.ao.project && this.ao.project.id, dp = this.ao.depot; if (!pid || dp.busy) return;
      dp.busy = "annuler"; dp.err = "";
      try {
        const r = await this.api("DELETE", "/api/projects/" + pid + "/groupement/deposer");
        if (!this.ao.project || this.ao.project.id !== pid) return;
        if (r.status) this.ao.project.status = r.status;
        if (r.state) this.ao.grp.state = r.state;
        dp.d = Object.assign({}, dp.d || {}, { depose: false, status: r.status });
        dp.live = "Marquage « déposé » retiré."; this.notify(dp.live);
        dp.busy = ""; await this.aoDepotLoad();
      } catch (e) { dp.err = e.message || "Impossible de retirer le marquage pour le moment."; }
      finally { dp.busy = ""; }
    },
    // Boîte de confirmation : dit ce que l'action fait AVANT de la faire (focus sur « Annuler », Échap ferme).
    _convAsk(cfg) {
      this._cdlgFocus = document.activeElement;
      const lines = (cfg.lines || []).filter(Boolean).map(l => typeof l === "string" ? { t: l } : l);
      this.cdlg = Object.assign({ ok: "Confirmer", fields: [] }, cfg, { lines, fields: (cfg.fields || []).map(x => Object.assign({}, x)) });
      this.$nextTick(() => { const b = this.$refs.cdlgCancel; if (b && b.focus) b.focus(); });
    },
    cdlgClose() {
      this.cdlg = null;
      const el = this._cdlgFocus; this._cdlgFocus = null;
      if (el && el.focus && document.body.contains(el)) this.$nextTick(() => el.focus());
    },
    async cdlgRun() {
      const d = this.cdlg; if (!d) return;
      const vals = {}; (d.fields || []).forEach(x => { vals[x.key] = String(x.value || "").trim(); });
      const run = d.run; this.cdlgClose();
      if (run) await run(vals);
    },
    roleLabel(r) { return ({ mandataire: "Chef de file", cotraitant: "Partenaire", sous_traitant: "Sous-traitant" })[r] || r; },
    checklistLabel(s) { return ({ ok: "Disponible", manquant: "Manquant", expire: "Expiré", generable: "Généré auto", a_completer: "À terminer" })[s] || s; },
    // Dossiers du coffre : l'identifiant « Mémoire technique » reste en base, l'écran dit « Dossier de présentation ».
    folderLabel(f) { return f === "Mémoire technique" ? "Dossier de présentation" : (f || ""); },
    // Copie le texte affiché d'un bloc (ex. note d'information aux salariés).
    async copyRefText(ref, ok) {
      const el = this.$refs[ref]; const txt = el ? (el.innerText || "").trim() : "";
      if (!txt) return;
      try { await navigator.clipboard.writeText(txt); this.notify(ok || "Texte copié"); }
      catch (e) { this.notify("Copie impossible : sélectionnez le texte et copiez-le à la main", "err"); }
    },
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
    // « Comment vous serez noté » : la grille retrouvée dans le règlement (analyse ≥ vague 1 rédaction).
    aoGrille() { const g = this.aoDetails().grille_notation; return (g && Array.isArray(g.criteres)) ? g : null; },
    grilleResume(g) {
      if (!g) return "";
      const n = (g.criteres || []).filter(x => x.dans_le_plan).length, av = (g.compteurs && g.compteurs.a_verifier) || 0;
      const s = (g.ponderation || {}).statut;
      const base = n ? n + " critère" + (n > 1 ? "s" : "") : "aucun critère retenu";
      return base + (s === "non_ponderes" ? " · non pondérés" : "") + (av ? " · " + av + " à vérifier" : "");
    },
    async aoGrilleChoix(id, choix, poids) {
      const p = this.ao.project; if (!p || this.ao.grilleBusy) return;
      this.ao.grilleBusy = id;
      try {
        const r = await this.api("POST", "/api/sourcing/grille/choix", { project_id: p.id, critere_id: id, choix, poids: poids || "" });
        const a = Object.assign({}, p.ai_analysis || {}); a.details = Object.assign({}, a.details || {}, { grille_notation: r.grille_notation });
        p.ai_analysis = a;
        this.notify(choix === "confirme" ? "Critère ajouté à votre plan" : choix === "ecarte" ? "Critère retiré de votre plan" : "Choix annulé");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grilleBusy = ""; }
    },
    // Détail du score : on affiche le VRAI score déterministe du DCE (score_breakdown,
    // 6 critères pondérés) ; repli sur le pré-score de l'avis (lead_score) si absent.
    aoBreakdown() {
      const a = this.ao.project && this.ao.project.ai_analysis;
      if (!a) return [];
      if (a.score_breakdown && a.score_breakdown.length) return a.score_breakdown;
      return (a.dce_available && a.lead_score && a.lead_score.breakdown) || [];
    },
    async aoStatus() {
      try { await this.api("PUT", "/api/projects/" + this.ao.project.id, { status: this.ao.project.status }); this.notify("Étape mise à jour"); this.loadStats(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    outcomeReasons(status) {
      return status === "gagne"
        ? ["Prix compétitif", "Valeur technique / présentation", "Références & expérience", "Délai proposé", "Critère RSE / insertion", "Groupement / partenaires", "Relation client"]
        : ["Prix trop élevé", "Dossier de présentation insuffisant", "Références insuffisantes", "Délai non tenable", "Critère RSE non couvert", "Dossier incomplet / hors délai", "Capacité / effectif insuffisant"];
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
        if (this.convVisible()) this.aoGrpReloadState();   // « Prêt à déposer » : formulaires préparés après la convention
        this.notify("Documents générés et archivés dans le dossier");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.ao.generating = false; }
    },
    _downloadB64(b64, name) {
      const bin = atob(b64), arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      this.saveBlob(new Blob([arr], { type: "application/zip" }), name || "dossier.zip");
    },
    aoDownload() { const d = this.ao.dossier; if (d && d.zip_b64) this._downloadB64(d.zip_b64, d.zip_name); },
    // Taux de TVA de l'acte d'engagement (0 % par défaut — art. 293 B CGI).
    async setTva(v) {
      const rate = parseFloat(v) || 0;
      if (!this.ao.project) return;
      this.ao.project.tva_rate = rate;
      try {
        await this.api("PUT", "/api/projects/" + this.ao.project.id, { tva_rate: rate });
        this.notify("TVA réglée à " + (rate ? String(rate).replace('.', ',') + " %" : "0 % (franchise)") + " — régénérez le dossier pour l'appliquer");
      } catch (e) { this.notify(e.message, "err"); }
    },
    // Cockpit : assemble la réponse commune PUIS télécharge directement (sinon on ne
    // « trouve pas le doc » : il était généré mais le bouton de téléchargement était ailleurs).
    async aoAssemble() {
      await this.aoGenerate();
      if (this.ao.dossier && this.ao.dossier.zip_b64) { this.aoDownload(); this.notify("Dossier commun assemblé et téléchargé"); }
    },
    async aoUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      if (!this.gateCriteria()) return;
      this.ao.uploading = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", this.ao.project.id);
        await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        this.ao.project = await this.api("GET", "/api/projects/" + this.ao.project.id);
        this.aoLoadDocs();
        this.notify("Dossier analysé — analyse complète");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.ao.uploading = false; }
    },
    async aoReanalyze() {
      if (!this.ao.project) return;
      this.ao.uploading = true;
      try {
        const fd = new FormData(); fd.append("project_id", this.ao.project.id);
        await this.api("POST", "/api/sourcing/reanalyze", fd, true);
        this.ao.project = await this.api("GET", "/api/projects/" + this.ao.project.id);
        this.aoLoadDocs();
        this.notify("Ré-analyse terminée");
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
      if (!confirm("Supprimer ce marché et toutes ses données (analyse, partenaires, documents) ?\nIl part à la corbeille — récupérable.")) return;
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
    // ── Modals (cotraitant / contact / invoice) ──
    openCotraitant(c) { this.modal = { type: "cotraitant", title: c ? "Modifier le partenaire" : "Nouveau partenaire", d: c ? { ...c } : { name: "", ca_n1: 0, ca_n2: 0, effectif: 0 } }; },
    openContact(c) { this.modal = { type: "contact", title: c ? "Modifier le contact" : "Nouveau contact", d: c ? { ...c } : { name: "", contact_type: "" } }; },
    openInvoice(projectId = null) { this.modal = { type: "invoice", wide: true, title: "Nouveau document", d: { type: "devis", client_name: "", client_address: "", tva_rate: 0, project_id: (typeof projectId === "number" ? projectId : null), items: [{ description: "", qty: 1, unit_price: 0 }] } }; },
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
      const files = Array.from(e.target.files || []); if (!files.length) return;
      e.target.value = "";
      this.uploading = true;
      let ok = 0;
      try {
        for (const file of files) {
          const fd = new FormData(); fd.append("file", file); fd.append("name", file.name); fd.append("category", "autre");
          try { await this.api("POST", "/api/documents/", fd, true); ok++; }
          catch (err) { this.notify(file.name + " : " + err.message, "err"); }
        }
      } finally { this.uploading = false; }
      if (ok) { this.loadDocuments(); this.notify(ok === files.length ? ok + " document(s) ajouté(s)" : ok + "/" + files.length + " ajouté(s)"); }
      else this.notify("Aucun document ajouté", "err");
    },
    async delDoc(d) { const id = d.id; try { await this.api("DELETE", "/api/documents/" + id); this.loadDocuments(); this.notifyUndo("Document mis à la corbeille", () => this.restoreDoc(id)); } catch (e) { this.notify(e.message, "err"); } },
    async renameDoc(d) {
      const name = (prompt("Nouveau nom du document :", d.name || "") || "").trim();
      if (!name || name === d.name) return;
      try { await this.api("PATCH", "/api/documents/" + d.id, { name }); this.loadDocuments(); this.notify("Renommé"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async restoreDoc(id) { try { await this.api("POST", "/api/documents/" + id + "/restore"); this.loadDocuments(); this.notify("Restauré"); } catch (e) { this.notify(e.message, "err"); } },
    async downloadDoc(d) {
      try {
        const r = await fetch("/api/documents/" + d.id + "/download", { headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Téléchargement impossible");
        this.saveBlob(await r.blob(), d.name || "document");
      } catch (e) { this.notify(e.message, "err"); }
    },

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
    // Pluriel lisible (« 1 partenaire », « 3 partenaires ») au lieu de « partenaire(s) ».
    pl(n, one, many) { return Number(n) === 1 ? one : many; },
    // « 6 % », « 280 000 € » : espace fine insécable entre le nombre et l'unité (jamais « % » seul en début de ligne).
    nbspUnits(t) { return String(t == null ? "" : t).replace(/(\d)\s+(?=%|€)/g, "$1\u202F"); },
    // Libellé COURT du verdict pour les listes compactes (fil du tableau de bord).
    decShort(d) { return ({ go: "Bon potentiel", go_groupement: "En groupement", no_go: "Peu adapté", a_etudier: "À étudier" })[d] || "—"; },
    // Fil du tableau de bord : un marché « bon potentiel en groupement » affiche le score DU GROUPEMENT
    // (même règle que la vue Mes marchés) ; le score seul reste lisible au survol.
    feedScore(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null) return p.groupement_score;
      return p.match_score != null ? p.match_score : "—";
    },
    feedScoreTitle(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null)
        return "Seul : " + (p.match_score != null ? p.match_score : "—") + "/100 · En groupement : " + p.groupement_score + "/100";
      return p.match_score != null ? "Compatibilité " + p.match_score + "/100" : "Pas encore analysé";
    },
    feedRingStyle(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null) {
        const deg = Math.max(0, Math.min(100, p.groupement_score)) * 3.6;
        return `background:conic-gradient(var(--accent) ${deg}deg, var(--hairline) ${deg}deg)`;
      }
      return this.ringStyle(p.match_score);
    },
    decLabel(d) { return ({ go: "Bon potentiel", go_groupement: "Bon potentiel en groupement", no_go: "Peu adapté", a_etudier: "À étudier" })[d] || "—"; },
    decColor(d) { return ({ go: "color:var(--go)", go_groupement: "color:var(--accent-text)", no_go: "color:var(--danger)", a_etudier: "color:var(--warn)" })[d] || "color:var(--muted)"; },
    // Kanban : un marché « bon potentiel en groupement » affiche son score de groupement (le score seul reste au survol).
    kanbanScore(p) { if (p.go_decision === "go_groupement" && p.groupement_score != null) return p.groupement_score; return p.match_score != null ? p.match_score : ""; },
    kanbanScoreTitle(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null) return "Seul : " + (p.match_score != null ? p.match_score + "/100" : "—") + " · En groupement : " + p.groupement_score + "/100";
      return p.match_score != null ? "Compatibilité " + p.match_score + "/100" : "";
    },
    // Verdict SEUL d'un marché « bon potentiel en groupement » : celui que l'API a calculé (simulation)
    // sinon, à défaut, les seuils du profil (mêmes défauts que le serveur : 65 / 40). Jamais un chiffre inventé.
    aoSeulDecision() {
      const p = this.ao.project || {}; const d = p.go_decision;
      if (d !== "go_groupement") return d;
      const sim = this.ao.grp && this.ao.grp.sim; if (sim && sim.decision_seul) return sim.decision_seul;
      if (p.match_score == null) return null;
      const go = Number(this.criteria.go_threshold) || 65, ng = Math.min(Number(this.criteria.nogo_threshold) || 40, go - 1);
      return p.match_score >= go ? "go" : (p.match_score < ng ? "no_go" : "a_etudier");
    },
    statusLabel(s) { return ({ nouveau: "Nouveau", en_cours: "En cours", envoye: "Envoyé", gagne: "Gagné", perdu: "Perdu", abandonne: "Abandonné" })[s] || s; },
    covLabel(c) { return ({ entreprise: "Entreprise seule", cotraitant: "Avec un partenaire", non_couvert: "Non couvert" })[c] || c; },
    covClass(c) { return ({ entreprise: "go", cotraitant: "st-nouveau", non_couvert: "no_go" })[c] || "st-nouveau"; },
    eurExact(v) {
      // Montants de FACTURATION : 2 décimales (le centime calculé doit être lisible).
      v = Number(v) || 0;
      const cur = (this.org.data && this.org.data.devise) || "EUR";
      try { return new Intl.NumberFormat("fr-FR", { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v); }
      catch (e) { return v.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €"; }
    },
    invStatusLabel(s) { return ({ brouillon: "Brouillon", envoye: "Envoyé", accepte: "Accepté", en_attente: "En attente", paye: "Payé", en_retard: "En retard" })[s] || s; },
    // Date FR (JJ/MM/AAAA). Ne reformate QUE les dates ISO strictes → laisse intacts les
    // estimés libres (« S2 2026 », « 2026 »…) au lieu de les transformer en fausse date.
    fmtDate(s) { if (!s) return "—"; const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + "/" + m[2] + "/" + m[1] : String(s); },
    scoreStatusLabel(s) { return ({ ok: "Conforme", partiel: "Partiel", inconnu: "Inconnu" })[s] || s; },
    eur(v) {
      v = Number(v) || 0;
      const cur = (this.org.data && this.org.data.devise) || "EUR";
      try { return new Intl.NumberFormat("fr-FR", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(v); }
      catch (e) { return v.toLocaleString("fr-FR") + " €"; }
    },
    koSize(b) { const k = (Number(b) || 0) / 1024; return k >= 1024 ? (k / 1024).toFixed(1) + " Mo" : Math.round(k) + " Ko"; },   // bascule en Mo au-delà de ~1 Mo (sinon « 18432 Ko » illisible). Attention : ne PAS nommer kb() : collision avec la donnée `kb`
    avg(...a) { const n = a.map(Number).filter(x => x > 0); return n.length ? n.reduce((s, x) => s + x, 0) / n.length : 0; },
    detailRows(d) {
      const out = {}; const labels = { intitule_marche: "Intitulé", acheteur: "Acheteur", budget_estime: "Budget", date_limite: "Date limite", delai_execution: "Délai", lieu_execution: "Lieu", allotissement: "Allotissement", penalites: "Pénalités", sous_traitance: "Sous-traitance", ca_minimum_requis: "CA minimum", visite_obligatoire: "Visite" };
      for (const k in labels) { if (d[k] && typeof d[k] !== "object") out[labels[k]] = String(d[k]).slice(0, 120); }
      return out;
    },
    clausesRisque(d) { return Array.isArray(d && d.clauses_risque) ? d.clauses_risque : []; },
    niveauPill(n) { return ({ eleve: "no_go", "élevé": "no_go", "élevée": "no_go", moyen: "a_etudier", moyenne: "a_etudier", faible: "go" })[String(n || "").toLowerCase()] || "neutral"; },
    niveauLabel(n) { return ({ eleve: "Élevé", "élevé": "Élevé", "élevée": "Élevé", elevee: "Élevé", moyen: "Moyen", moyenne: "Moyen", faible: "Faible" })[String(n || "").toLowerCase()] || (n || "—"); },   // formes féminines alignées sur niveauPill (sinon « moyenne »/« élevée » brut)
    async loadCountries() { if (this.countries2.length) return; try { this.countries2 = await this.api("GET", "/api/sourcing/countries"); } catch (e) {} },
    countryName(code) { const c = this.countries2.find(x => x.code === code); return c ? c.nom : code; },
    // ── Veille / alertes AO sauvegardées ──
    async loadAlerts() { try { this.src.alerts = await this.api("GET", "/api/saved-searches/"); } catch (e) {} },
    async srcSaveAlert() {
      if (this.src._savingAlert) return;   // garde anti double-clic (évite l'alerte en double)
      this.src._savingAlert = true;
      const deps = this.srcDeps();
      const countries = this.src.country ? [this.src.country] : [];
      const cpv = (this.src.cpv || "").split(/[ ,;]+/).map(s => s.trim()).filter(Boolean);
      const zone = this.src.country ? this.countryName(this.src.country) : "UE";
      const name = (this.src.query || "Veille") + " · " + zone + (deps.length ? " (" + deps.join("/") + ")" : "");
      try {
        // On replique fidèlement la recherche : query + CPV + type de marché + zone.
        await this.api("POST", "/api/saved-searches/", { name, query: this.src.query, cpv, type_marche: this.src.type_marche || "", departements: deps, countries, frequency: "quotidienne", active: true });
        this.loadAlerts(); this.notify("Alerte créée — vous serez notifié par email");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.src._savingAlert = false; }
    },
    async srcRunAlert(a) {
      this.notify("Test de l'alerte…");
      try { const r = await this.api("POST", "/api/saved-searches/" + a.id + "/run"); this.loadAlerts(); this.notify(r.new_matches + " nouvel(s) AO trouvé(s)"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async srcToggleAlert(a) {
      // On renvoie l'alerte COMPLÈTE (…a) : le PUT backend réécrit tous les champs avec
      // leur défaut s'ils sont absents → un payload partiel effaçait silencieusement CPV,
      // type de marché, pays, montants et seuil de compatibilité à chaque pause/activation.
      try { await this.api("PUT", "/api/saved-searches/" + a.id, { ...a, active: !a.active }); this.loadAlerts(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async srcDelAlert(a) {
      const id = a.id;
      if (!confirm("Supprimer cette alerte ? Vous ne recevrez plus les nouveaux marchés correspondants par email.")) return;
      try { await this.api("DELETE", "/api/saved-searches/" + id); this.loadAlerts(); this.notify("Alerte supprimée"); }
      catch (e) { this.notify(e.message, "err"); }
    },

    // ── Sourcing IA (flux à la demande, sources officielles) ──
    srcDeps() { return this.src.dept.split(",").map(s => s.trim()).filter(Boolean); },
    srcCpv() { return (this.src.cpv || "").split(/[,\s]+/).map(s => s.trim()).filter(Boolean); },
    srcResetAdv() { this.src.type_marche = ""; this.src.cpv = ""; },
    async srcRenewals() {
      this.src.renewals.loading = true; this.src.renewals.done = false;
      this.src.renewals.list = [];   // vide le scan précédent (sinon résultats périmés affichés)
      try {
        const r = await this.api("POST", "/api/sourcing/renewals", { query: this.src.query || "travaux", departements: this.srcDeps() });
        this.src.renewals.list = r.renewals || []; this.src.renewals.done = true;
        this.notify(r.count ? (r.count + " marché(s) en fin de contrat détecté(s)") : "Aucune échéance proche sur ce périmètre", r.count ? "ok" : "err");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.renewals.loading = false; }
    },
    async srcSearch(arg) {
      // Garde de réentrance : Entrée maintenue / double-clic ne lancent pas des requêtes
      // concurrentes qui se piétinent.
      if (this.src.searching || this.src.loadingMore) return;
      // arg === true vient UNIQUEMENT du bouton « Charger plus » (srcLoadMore). Un clic /
      // une touche Entrée passe l'évènement DOM en argument : avant, il était pris pour un
      // « append » → toute recherche après la 1re s'empilait avec un mauvais offset (d'où
      // « une seule recherche, il faut rafraîchir »). On ne s'y trompe plus.
      const sig = JSON.stringify([(this.src.query || "").trim().toLowerCase(), this.srcDeps(),
        this.src.country || "", this.src.type_marche || "", this.srcCpv()]);
      // Mêmes critères que la dernière recherche → on enchaîne la page suivante et on
      // n'affiche QUE ce qu'on n'a pas déjà vu (rappuyer = « montre-m'en d'autres »).
      // Critères modifiés → nouvelle recherche (remise à zéro).
      const append = (arg === true) || (sig === this.src.lastSig && this.src.tenders.length > 0);
      if (append) { this.src.loadingMore = true; }
      else {
        this.src.searching = true; this.src.tenders = []; this.src.errors = []; this.src.analysis = null;
        this.src.offset = 0; this.src.hasMore = false; this.src.lastSig = sig;
        this.src.empty = null; this.src.marketEst = null;
        // Purge l'état d'analyse périmé de la recherche précédente (sinon un panneau
        // « Analyser » / partenaires restait latent sur les nouveaux résultats).
        this.src.chosen = null; this.src.projectId = null; this.src.dossier = null;
      }
      const PAGE = 15;
      try {
        const r = await this.api("POST", "/api/sourcing/search",
          { query: this.src.query, departements: this.srcDeps(), countries: this.src.country ? [this.src.country] : [],
            type_marche: this.src.type_marche, cpv: this.srcCpv(), limit: PAGE, offset: append ? this.src.offset : 0 });
        const fresh = r.tenders || [];
        // Clé de dédup ROBUSTE : official_ref peut être vide (avis TED sans réf claire) →
        // on combine source + réf + objet, sinon plusieurs avis « sans réf » s'écrasaient
        // (pagination qui semblait bloquée / résultats perdus en silence).
        const tkey = t => ((t.provenance && t.provenance.source) || "") + "|" + ((t.provenance && t.provenance.official_ref) || "") + "|" + ((t.objet || "").slice(0, 60));
        let appendedNothing = false;
        if (append) {
          const seen = new Set(this.src.tenders.map(tkey));
          const added = fresh.filter(t => !seen.has(tkey(t)));
          this.src.tenders = this.src.tenders.concat(added);
          this.src.errors = r.errors || [];
          if (added.length) this.notify(added.length + " nouveau" + (added.length > 1 ? "x" : "") + " marché" + (added.length > 1 ? "s" : ""), "ok");
          else { this.notify("Tous les marchés correspondant à ces critères sont déjà affichés", "ok"); appendedNothing = true; }
        } else { this.src.tenders = fresh; this.src.errors = r.errors || []; this.src.sources = r.sources_queried || []; }
        this.src.offset = (append ? this.src.offset : 0) + PAGE;
        // Une page entièrement dupliquée = on est au bout côté affichage → on masque « charger plus »
        // (le serveur ignore ce qui est déjà à l'écran et pouvait renvoyer has_more à tort).
        this.src.hasMore = appendedNothing ? false : !!r.has_more;
        if (!append) this.src.searched = true;
        if (!append && !this.src.tenders.length) {
          // 0 résultat → carte ACTIONNABLE (élargir en un clic) plutôt qu'un simple toast.
          this.src.empty = {
            closed: (r.closed_filtered || 0) + (r.amount_filtered || 0),
            hasDept: !!this.srcDeps().length,
            hasAdv: !!(this.src.type_marche || this.srcCpv().length),
            multiWord: (this.src.query || "").trim().split(/\s+/).filter(Boolean).length > 1,
          };
        }
      } catch (e) { this.notify(e.message, "err"); } finally { this.src.searching = false; this.src.loadingMore = false; }
    },
    srcLoadMore() { return this.srcSearch(true); },
    // ── #3 Pré-remplissage de la 1re recherche depuis le profil (fin de la page blanche) ──
    srcPrefillFromProfile() {
      if (this.src.prefilled || this.src.searched) return;
      const c = this.company || {};
      const spec = (c.specialites || "").split(/[,;]/).map(s => s.trim()).filter(Boolean)[0];
      if (spec && !this.src.query) this.src.query = spec;
      const dep = (c.postal_code || "").slice(0, 2);
      if (dep && !this.src.dept) this.src.dept = dep;
      this.src.prefilled = true;
    },
    srcSearchMine() {   // « Voir les marchés pour mon entreprise »
      this.srcPrefillFromProfile();
      if (!(this.src.query || "").trim() && !this.src.dept) { this.go("company"); this.notify("Complétez vos spécialités et votre zone", "err"); return; }
      this.srcSearch();
    },
    // ── #2 Élargir la recherche en un clic ──
    srcWiden(kind) {
      if (kind === "dept") this.src.dept = "";
      else if (kind === "adv") { this.src.type_marche = ""; this.src.cpv = ""; }
      else if (kind === "query") this.src.query = (this.src.query || "").trim().split(/\s+/)[0] || "";
      this.srcSearch();
    },
    // ── #10 Quota visible avant l'analyse : compteur + garde ──
    srcQuotaBlocked() { const u = this.stats.usage; return !!u && u.analyses_remaining <= 0 && !u.overage_enabled; },
    srcQuotaLabel() {
      const u = this.stats.usage; if (!u || typeof u.analyses_remaining !== "number") return "";
      if (u.analyses_remaining > 0) return u.analyses_remaining + " analyse" + (u.analyses_remaining > 1 ? "s" : "") + " restante" + (u.analyses_remaining > 1 ? "s" : "") + " ce mois";
      if (u.overage_enabled) return "Quota atteint — analyses au tarif à l'usage";
      return "Quota d'analyses atteint ce mois";
    },
    // ── #5 Repère de prix marché (DECP) quand l'annonce n'a pas de budget ──
    srcHasBudget(details) {
      const b = details && (details.budget_estime || details.budget);
      return !!(b && String(b).trim() && !/non|inconnu|à compléter|a completer|\bn\/?a\b/i.test(String(b)));
    },
    async srcMarketEstimate() {
      const a = this.src.analysis; if (!a) return;
      const d = a.details || {};
      const objet = d.intitule_marche || (this.src.chosen && this.src.chosen.objet) || this.src.query || "";
      const dep = (this.srcDeps()[0] || (this.src.chosen && (this.src.chosen.departements || [])[0]) || "");
      this.src.marketEstBusy = true;
      try {
        this.src.marketEst = await this.api("POST", "/api/sourcing/market-estimate",
          { objet: objet, departement: dep, cpv: this.srcCpv()[0] || "" });
      } catch (e) { this.src.marketEst = { ok: false }; this.notify(e.message, "err"); }
      finally { this.src.marketEstBusy = false; }
    },
    async srcAnalyze(t) {
      if (!this.gateCriteria()) return;
      this.src.analyzing = true; this.src.chosen = t; this.src.analysis = null; this.src.marketEst = null;
      this.src.ct.companies = []; this.src.ct.selected = []; this.src.dossier = null;
      try {
        const r = await this.api("POST", "/api/sourcing/analyze", { tender: t });
        this.src.analysis = r; this.src.projectId = r.project_id;
        this.loadProjects(); this.loadStats();
        if (!r.dce_available) this.notify("Dossier complet non accessible — analyse fondée sur l'annonce publiée", "ok");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.src.analyzing = false; }
    },
    async srcUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      if (!this.gateCriteria()) return;
      if (!this.src.projectId) { this.notify("Analysez d'abord l'annonce", "err"); return; }
      this.src.analyzing = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", this.src.projectId);
        const r = await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        this.src.analysis = r; this.loadProjects(); this.loadStats();
        this.notify("Dossier analysé — analyse complète");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.analyzing = false; }
    },
    async srcReanalyze() {
      if (!this.src.projectId) { this.notify("Importez d'abord le dossier du marché", "err"); return; }
      this.src.analyzing = true;
      try {
        const fd = new FormData(); fd.append("project_id", this.src.projectId);
        const r = await this.api("POST", "/api/sourcing/reanalyze", fd, true);
        this.src.analysis = r; this.loadProjects();
        this.notify("Ré-analyse terminée");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
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
    contactTypeLabel(t) { return ({ maitre_ouvrage: "Client (acheteur)", sous_traitant: "Sous-traitant", partenaire: "Partenaire", fournisseur: "Fournisseur" })[t] || t || "—"; },
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
    async amontAnalyzeText() {
      if (this.amont.pasteText.trim().length < 60) { this.notify("Texte trop court (60 caractères min.)", "err"); return; }
      this.amont.pasting = true;
      try {
        const r = await this.api("POST", "/api/amont/analyze-text", { text: this.amont.pasteText, domaines: this.amont.domaines, source: "Texte collé" });
        await this.loadAmont();
        this.amont.pasteText = ""; this.amont.pasteOpen = false;
        this.notify(r.count ? (r.count + " projet(s) détecté(s)") : "Aucun projet d'investissement détecté");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.amont.pasting = false; }
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
    kbKindLabel(k) { return ({ memoire: "Dossier de présentation", rse: "RSE", methodologie: "Méthodologie", certification: "Certification", reference: "Référence", autre: "Autre" })[k] || k; },
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
      if (!confirm("Retirer ce document de votre savoir-faire ?")) return;
      // kbLoad() rafraîchit aussi le compteur d'extraits indexés (sinon il restait périmé).
      try { await this.api("DELETE", "/api/knowledge/" + d.id); await this.kbLoad(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async kbSearch() {
      if (!(this.kb.searchQ || "").trim() || this.kb.searching) return;
      this.kb.searching = true;
      try { this.kb.searchRes = await this.api("POST", "/api/knowledge/search", { query: this.kb.searchQ, k: 6 }); }
      catch (e) { this.notify(e.message, "err"); } finally { this.kb.searching = false; }
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
        const nc = this.kb.memoire.n_coupees || 0;
        this.notify("Dossier de présentation rédigé (" + (this.kb.memoire.n_sections || 0) + " sections), à relire"
          + (nc ? " · " + nc + " section(s) coupée(s) à terminer" : ""), nc ? "err" : "ok");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.kb.memoireLoading = false; }
    },
    async kbQuestionnaire() {
      const qs = (this.kb.qText || "").split("\n").map(s => s.trim()).filter(Boolean);
      if (!qs.length) { this.notify("Collez vos questions (une par ligne)", "err"); return; }
      if (!this.kb.docs.length) { this.notify("Ajoutez d'abord des documents à votre base", "err"); return; }
      this.kb.qLoading = true; this.kb.qResults = null;
      try {
        const job = await this.api("POST", "/api/knowledge/questionnaire", { questions: qs });
        const r = await this.pollJob(job.id); this.kb.qResults = r;
        const errs = r.errors || 0;
        let msg = r.covered + "/" + (r.count - errs) + " réponse(s) proposée(s), à relire";
        if (errs) msg += " · " + errs + " non générée(s), réessayez";
        this.notify(msg);
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.kb.qLoading = false; }
    },

    eurMaybe(n) { return (n || n === 0) ? this.eur(n) : "montant estimé n/d"; },
    companyWeb(c) { return "https://www.google.com/search?q=" + encodeURIComponent((c.nom || c.name || "") + " " + (c.ville || c.city || "") + " site officiel contact"); },
    // Garde de schéma pour TOUT :href construit depuis une donnée (avis, fiches, délibérations…) :
    // Vue n'assainit pas les URL « javascript: ». Seules une adresse web absolue (http/https) ou
    // un chemin interne (/…) passent ; sinon lien neutre « # ».
    safeUrl(u) {
      const s = String(u == null ? "" : u).trim();
      return (s && !/[\u0000-\u001f\u007f]/.test(s) && /^(https?:\/\/[^\s\/]|\/(?![\/\\]))/i.test(s)) ? s : "#";
    },
    async srcCotraitants() {
      if (!this.src.projectId) { this.notify("Analysez d'abord un marché (Étape 2) avant de chercher des partenaires", "err"); return; }
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
        this.notify(`Documents préparés (${r.cotraitants_verifies} partenaire(s) SIRET vérifié)`);
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
    saveBlob(blob, name) {
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      // Sans révocation, chaque téléchargement gardait le fichier entier en mémoire.
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    },
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
      d.innerHTML = '<div style="color:#b45309;line-height:0"><svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg></div>'
        + '<h2 style="margin:10px 0 4px;font-size:19px">Un élément n’a pas pu s’afficher</h2>'
        + '<p style="color:#6b7280;font-size:14px;margin:6px 0 4px">L’application reste intacte — rechargez la page.</p>'
        + '<p style="font-size:12px;color:#9aa0ab;margin:10px 0">Détail : <code style="background:#f1f3f5;padding:2px 6px;border-radius:5px;color:#444">' + safe + '</code></p>'
        + '<button onclick="location.reload()" style="margin-top:14px;padding:10px 20px;border:0;border-radius:9px;background:#3b5bdb;color:#fff;font-weight:600;font-size:14px;cursor:pointer">Recharger</button>';
      document.body.appendChild(d);
    }, 60);
  } catch (e) {}
};

// « Comment vous serez noté » (rédaction, vague 1) : la grille de l'acheteur, retrouvée dans le
// texte du règlement. Accepte la grille complète (chef de file, edit=true) ou la vue publique des
// partenaires (edit=false, lecture seule). N'affiche QUE ce que le serveur a retrouvé : critère,
// poids tel qu'écrit, phrase source. Texte toujours rendu en {{ }} (jamais v-html).
function _gnNum(v) { const n = Number(v); return isFinite(n) ? n.toLocaleString("fr-FR") : String(v || ""); }
__adjApp.component("grille-carte", {
  props: { g: { type: Object, default: null }, edit: { type: Boolean, default: false }, busy: { type: String, default: "" } },
  emits: ["choix"],
  data() { return { poids: {} }; },
  computed: {
    vm() {
      const g = this.g || {}, c = g.contraintes || {}, cad = c.cadre || {};
      const lignes = (g.criteres || []).map(x => {
        const ch = (x.choix_utilisateur && x.choix_utilisateur.choix) || (x.confirme ? "confirme" : x.ecarte ? "ecarte" : "");
        return { id: x.id || "", critere: x.critere || "", phrase: x.phrase || "", source: x.source || "", statut: x.statut,
          plan: !!x.dans_le_plan, choix: ch, poids: x.dans_le_plan ? (x.poids_retenu != null ? x.poids_retenu : (x.poids || "")) : "",
          poidsVous: x.poids_source === "utilisateur" };
      });
      const lim = (c.limites || []).filter(x => x && x.type);
      const vis = c.visite && (c.visite.phrase || c.visite.obligatoire) ? c.visite : null;
      return { lignes, pond: g.ponderation || {}, ordre: g.ordre || {}, total: g.controle_total || {},
        impose: !!c.fichier_impose, msgImpose: c.message_fichier || "",
        phraseOblig: (cad.obligatoire && cad.obligatoire.phrase) || c.phrase_obligation || "",
        cadreSource: (cad.obligatoire && cad.obligatoire.source) || cad.source || "",
        cadreFourni: cad.fourni != null ? !!cad.fourni : !!c.cadre_fourni,
        cadreMentionne: cad.mentionne != null ? !!cad.mentionne : !!c.cadre_mentionne,
        cadrePhrase: cad.phrase || "", limites: lim, visite: vis,
        lecture: (g.lecture && Array.isArray(g.lecture.pieces)) ? g.lecture : null };
    },
    alerteTotal() { const s = this.vm.total.statut; return s === "ecart" || s === "incomplet"; },
    rienImpose() { const v = this.vm; return !v.impose && !v.cadreFourni && !v.cadreMentionne && !v.limites.length && !v.visite; },
  },
  methods: {
    lim(x) {
      if (x.type === "police") { const s = [x.police, x.taille != null ? x.taille : ""].filter(v => v !== "" && v != null).join(" "); return "Police : " + (s || x.texte || ""); }
      const u = ({ pages: "pages", mots: "mots", caracteres: "caractères", lignes: "lignes" })[x.type] || x.type;
      return (x.valeur != null ? _gnNum(x.valeur) + " " + u : (x.texte || "")) + " au maximum";
    },
    send(l, choix) { this.$emit("choix", l.id, choix, choix === "confirme" ? String(this.poids[l.id] || "").trim() : ""); },
  },
  template: '<div class="gn">'
    + '<ul v-if="vm.lignes.length" class="gn-list">'
    + '<li v-for="l in vm.lignes" :key="l.id||l.critere" class="gn-row" :class="{off:l.choix===\'ecarte\'}">'
    + '<span class="gn-crit">{{ l.critere }}</span>'
    + '<span v-if="l.poids" class="gn-poids num">{{ l.poids }}</span>'
    + '<span v-if="l.choix===\'ecarte\'" class="pill neutral gn-pill">retiré</span>'
    + '<span v-else-if="l.choix===\'confirme\' && l.statut===\'a_verifier\'" class="pill neutral gn-pill">{{ edit ? "confirmé par vous" : "confirmé par le chef de file" }}</span>'
    + '<span v-else-if="l.statut===\'a_verifier\'" class="pill a_etudier gn-pill">à vérifier dans le règlement</span>'
    + '</li></ul>'
    + '<p v-if="vm.pond.message" class="muted small gn-note">{{ vm.pond.message }}</p>'
    + '<div v-if="alerteTotal" class="warn-box"><i data-lucide="triangle-alert" style="width:15px;height:15px;flex:none;margin-top:1px"></i><span>{{ vm.total.message }}</span></div>'
    + '<p v-else-if="vm.total.message" class="muted small gn-note">{{ vm.total.message }}</p>'
    + '<p v-if="vm.lecture && vm.lecture.pieces.length && !vm.lecture.reglement" class="muted small gn-note">Adjugo n\'a pas reconnu de règlement de la consultation parmi les pièces lues : comparez avec le règlement.</p>'
    + '<details v-if="vm.lignes.length" class="gn-det"><summary>Voir les phrases du règlement</summary>'
    + '<div v-for="l in vm.lignes" :key="\'p\'+(l.id||l.critere)" class="gn-src">'
    + '<div class="gn-src-t">{{ l.critere }}<span v-if="l.poids" class="muted"> · {{ l.poids }}<template v-if="l.poidsVous"> (lu par {{ edit ? "vous" : "le chef de file" }})</template></span></div>'
    + '<blockquote v-if="l.phrase" class="gn-q">{{ l.phrase }}</blockquote>'
    + '<div v-else class="muted small">Phrase non retrouvée dans le dossier importé.</div>'
    + '<div v-if="l.source" class="muted small">Trouvée dans : {{ l.source }}</div>'
    + '<div v-if="edit" class="gn-act">'
    + '<template v-if="!l.choix && (l.statut===\'a_verifier\' || (!l.poids && vm.pond.statut!==\'non_ponderes\'))">'
    + '<input class="inp gn-inp" v-model="poids[l.id]" maxlength="40" placeholder="Poids lu, ex. 60 %" :aria-label="\'Poids lu dans le règlement pour \' + l.critere">'
    + '<button type="button" class="btn sm" :disabled="busy===l.id" @click="send(l,\'confirme\')"><i data-lucide="check"></i>Je l\'ai lu dans le règlement</button>'
    + '<button type="button" class="btn ghost sm" :disabled="busy===l.id" @click="send(l,\'ecarte\')">Retirer</button>'
    + '</template>'
    + '<button v-else-if="l.choix" type="button" class="btn ghost sm" :disabled="busy===l.id" @click="send(l,\'annule\')">Annuler mon choix</button>'
    + '<button v-else type="button" class="btn ghost sm" :disabled="busy===l.id" @click="send(l,\'ecarte\')">Retirer de mon plan</button>'
    + '</div></div>'
    + '<div v-if="vm.ordre.phrase" class="gn-src"><div class="gn-src-t">Ordre des critères</div><blockquote class="gn-q">{{ vm.ordre.phrase }}</blockquote></div>'
    + '</details>'
    + '<div class="gn-sub">Ce que le dossier impose'
    + '<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Repéré dans le texte, sans IA : un cadre de réponse fourni ou imposé, des limites de pages, de mots, de caractères ou de police, une visite obligatoire. Chaque repérage garde sa phrase : relisez-la avant de rédiger. Un repérage peut en manquer : le règlement fait foi.</span></button></div>'
    + '<div v-if="vm.impose" class="warn-box"><i data-lucide="triangle-alert" style="width:15px;height:15px;flex:none;margin-top:1px"></i><span>{{ vm.msgImpose }}</span></div>'
    + '<p v-else-if="vm.cadreFourni" class="small gn-note">Un cadre de réponse est fourni avec le dossier.</p>'
    + '<p v-else-if="vm.cadreMentionne" class="small gn-note">Le règlement parle d\'un cadre de réponse, mais il ne figure pas dans les fichiers lus.</p>'
    + '<ul v-if="vm.limites.length || vm.visite" class="gn-chips">'
    + '<li v-for="(x,i) in vm.limites" :key="\'l\'+i">{{ lim(x) }}</li>'
    + '<li v-if="vm.visite">Visite obligatoire</li></ul>'
    + '<p v-if="rienImpose" class="muted small gn-note">Ni cadre de réponse, ni limite de pages ou de police, ni visite obligatoire repérés dans le règlement.</p>'
    + '<details v-if="!rienImpose" class="gn-det"><summary>Voir les phrases</summary>'
    + '<div v-if="vm.phraseOblig || vm.cadrePhrase" class="gn-src"><div class="gn-src-t">Cadre de réponse</div><blockquote class="gn-q">{{ vm.phraseOblig || vm.cadrePhrase }}</blockquote><div v-if="vm.cadreSource" class="muted small">Trouvée dans : {{ vm.cadreSource }}</div></div>'
    + '<div v-for="(x,i) in vm.limites" :key="\'lp\'+i" class="gn-src"><div class="gn-src-t">{{ lim(x) }}</div><blockquote v-if="x.phrase" class="gn-q">{{ x.phrase }}</blockquote><div v-if="x.source" class="muted small">Trouvée dans : {{ x.source }}</div></div>'
    + '<div v-if="vm.visite" class="gn-src"><div class="gn-src-t">Visite obligatoire</div><blockquote class="gn-q">{{ vm.visite.phrase }}</blockquote><div v-if="vm.visite.source" class="muted small">Trouvée dans : {{ vm.visite.source }}</div></div>'
    + '</details>'
    + '<details v-if="vm.lecture && vm.lecture.pieces.length" class="gn-det"><summary>Pièces lues ({{ vm.lecture.pieces.length }})</summary>'
    + '<ul class="gn-pieces"><li v-for="(p,i) in vm.lecture.pieces" :key="\'pc\'+i"><span>{{ p.libelle }}</span><span v-if="p.nom" class="muted"> · {{ p.nom }}</span>'
    + '<span v-if="p.lu_en_entier===true" class="muted"> · lue en entier</span><span v-else-if="p.lu_en_entier===false" class="muted"> · lue en partie</span></li></ul>'
    + '</details>'
    + '</div>',
});

// ── Réseau de partenaires (vague 3) : petits composants d'affichage, SANS état propre ──
// Ils ne font qu'afficher ce que l'API renvoie (libellé, source, date) : aucune note, aucun calcul,
// aucun « % ». Texte toujours rendu en {{ }} (jamais v-html). Les icônes sont peintes par le
// hook `updated` de la racine (les props ne changent que quand la racine se re-rend).
function _rnJjmmaaaa(s) { const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + "/" + m[2] + "/" + m[1] : ""; }
const _RN_TIP = '<button type="button" class="tip tip-l"><i data-lucide="info"></i><span class="sr-only">Source et date</span><span class="tip-b" role="tooltip">';
// Badges de confiance vérifiables (SIRENE, RGE, Qualiopi, BODACC, DECP, dépôts Adjugo).
__adjApp.component("rn-badges", {
  props: { badges: { type: Array, default: () => [] } },
  methods: {
    ic(n) { return ({ ok: "badge-check", info: "circle-dot", alerte: "triangle-alert" })[n] || "circle-dashed"; },
    nv(n) { return ({ ok: "vérifié", info: "information", alerte: "point d'attention" })[n] || "non vérifié"; },
    jj: _rnJjmmaaaa,
  },
  template: '<ul v-if="badges && badges.length" class="rn-badges">'
    + '<li v-for="(b,i) in badges" :key="(b.key||\'b\')+i" class="rn-badge" :class="\'n-\'+(b.niveau||\'non_verifie\')">'
    + '<i :data-lucide="ic(b.niveau)" aria-hidden="true"></i><span class="rn-badge-l">{{ b.label }}<span class="sr-only"> ({{ nv(b.niveau) }})</span></span>'
    + _RN_TIP + 'Source : {{ b.source || "non précisée" }}<template v-if="b.date"><br>Date : {{ jj(b.date) }}</template></span></button>'
    + '</li></ul>',
});
// Critères du classement (statut + phrase + source + date), toujours dans l'ordre renvoyé.
__adjApp.component("rn-criteres", {
  props: { criteres: { type: Array, default: () => [] } },
  methods: {
    ic(s) { return ({ ok: "check", partiel: "minus", non: "x", alerte: "triangle-alert" })[s] || "minus"; },
    st(s) { return ({ ok: "oui", partiel: "en partie", non: "non", alerte: "point d'attention" })[s] || ""; },
    jj: _rnJjmmaaaa,
  },
  template: '<ul class="rn-crits">'
    + '<li v-for="c in criteres" :key="c.key" class="rn-crit" :class="\'s-\'+c.statut">'
    + '<i :data-lucide="ic(c.statut)" aria-hidden="true"></i>'
    + '<span class="rn-crit-t"><b>{{ c.label }}</b><span class="sr-only"> : {{ st(c.statut) }}.</span> <span class="rn-crit-d">{{ c.detail }}</span></span>'
    + '<button v-if="c.source || c.date" type="button" class="tip tip-l"><i data-lucide="info"></i><span class="sr-only">Source et date</span><span class="tip-b" role="tooltip">Source : {{ c.source || "non précisée" }}<template v-if="c.date"><br>Date : {{ jj(c.date) }}</template></span></button>'
    + '</li></ul>',
});
// Fiche PUBLIQUE d'un partenaire (annuaire, aperçu de « Mon profil », fiche ouverte) : sous-ensemble
// strict renvoyé par le serveur — jamais d'email, de téléphone, de CA ni de documents.
__adjApp.component("rn-fiche", {
  props: { c: { type: Object, required: true } },
  computed: {
    lien() { const u = String((this.c && this.c.lien_annuaire) || ""); return /^https:\/\/annuaire-entreprises\.data\.gouv\.fr\/entreprise\/\d{9}$/.test(u) ? u : ""; },
    lieu() { const c = this.c || {}; return [c.city, c.departement ? "(" + c.departement + ")" : ""].filter(Boolean).join(" "); },
  },
  methods: { jj: _rnJjmmaaaa },
  template: '<div class="rn-fiche">'
    + '<div class="rn-fiche-h"><div class="rn-fiche-id"><b class="rn-name">{{ c.name }}</b>'
    + '<span v-if="c.siren" class="muted small nw">SIREN {{ c.siren }}'
    + '<button type="button" class="tip tip-l"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">SIREN : le numéro à 9 chiffres qui identifie l\'entreprise dans le registre officiel des entreprises.</span></button></span></div>'
    + '<div v-if="lieu" class="muted small">{{ lieu }}</div>'
    + '<a v-if="lien" :href="lien" target="_blank" rel="noopener noreferrer" class="rn-link small"><i data-lucide="external-link"></i>Vérifier sur l\'annuaire des entreprises</a></div>'
    + '<p v-if="c.presentation" class="rn-pres">{{ c.presentation }}</p>'
    + '<div class="rn-sub">Capacités<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Chaque ligne indique sa source : déclarée par l\'entreprise, ou relevée dans un registre public, avec sa date.</span></button></div>'
    + '<ul v-if="c.capacites && c.capacites.length" class="rn-caps"><li v-for="x in c.capacites" :key="x.key" class="rn-cap">'
    + '<span class="rn-cap-l">{{ x.label }}</span><span class="rn-cap-v">{{ x.valeur }}</span>'
    + '<span class="rn-cap-s">{{ x.source }}<template v-if="x.date"> · {{ jj(x.date) }}</template></span></li></ul>'
    + '<p v-else class="muted small">Aucune capacité déclarée pour l\'instant.</p>'
    + '<div class="rn-sub">Vérifications dans les registres publics<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">SIRENE : le répertoire officiel des entreprises. BODACC : le journal officiel où sont publiées les procédures collectives. DECP : les données publiques des marchés attribués. Chaque résultat est daté ; rien n\'est noté.</span></button></div>'
    + '<rn-badges :badges="c.badges"></rn-badges>'
    + '<template v-if="c.references && c.references.length"><div class="rn-sub">Références choisies par l\'entreprise</div>'
    + '<ul class="rn-refs"><li v-for="(r,i) in c.references" :key="\'rf\'+i">{{ r.intitule }}<span v-if="r.client" class="muted"> — {{ r.client }}</span><span v-if="r.annee" class="muted"> ({{ r.annee }})</span></li></ul></template>'
    + '<div v-if="c.declare_le" class="muted small rn-decl">Informations déclarées par l\'entreprise, mises à jour le {{ jj(c.declare_le) }}.</div>'
    + '</div>',
});

// window.__adjugo = instance racine montée (hook débogage/tests E2E ; mount() retourne le
// proxy en build prod comme dev — état client de l'utilisateur courant uniquement).
window.__adjugo = __adjApp.mount("#app");
