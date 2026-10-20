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

// Réorganisation, vague 1 (1.2) : l'adresse demande-t-elle l'inscription (/app?inscription) ? Rend le choix et
// l'adresse sans ce paramètre (null : rien à changer). Les autres paramètres (?shared=, ?verify=…) et le
// fragment (#gcode=…) restent tels quels.
function inscriptionDemandee(loc) {
  try {
    const q = new URLSearchParams(loc.search || "");
    if (!q.has("inscription")) return { inscrire: false, adresse: null };
    q.delete("inscription");
    const reste = q.toString();
    return { inscrire: true, adresse: (loc.pathname || "/app") + (reste ? "?" + reste : "") + (loc.hash || "") };
  } catch (e) { return { inscrire: false, adresse: null }; }
}

// ══════════ Menu par rubriques (réorganisation, vague 1, 1.3) ══════════
// Architecture C corrigée (étude « organisation du logiciel », § 5.3) : le menu range des OBJETS. Chaque ancienne
// vue est un onglet de sa rubrique, ouverte par go() sans changement ; la rubrique de l'écran ouvert reste surlignée.
// `vues` : toutes les vues de la rubrique (les pages de détail comprises, sans onglet). `sous` : onglet interne
// d'une vue (Trouver des marchés). `si` : fonction activée par le serveur, ou "admin". `pastille` : ce qui attend une
// action (jamais un total, jamais zéro). `ancien` / `avant` : l'ancien nom, dit en bulle pendant la transition (1.8).
// « Réglages » est un groupe du menu (replié, état gardé) : ses entrées ne sont pas des onglets.
const RUBRIQUES = [
  { k: "accueil", label: "Accueil", ic: "house", vues: ["dashboard"], onglets: [
    { view: "dashboard", label: "Accueil", ic: "house", ancien: "Tableau de bord" }] },
  { k: "trouver", label: "Trouver des marchés", ic: "search", vues: ["sourcing", "amont", "veille"], onglets: [
    { view: "sourcing", sous: "publies", label: "Publiés", ic: "search" },
    { view: "sourcing", sous: "avenir", label: "À venir", ic: "calendar-clock", ancien: "Radar des échéances" },
    { view: "sourcing", sous: "alertes", label: "Mes alertes", ic: "bell", ancien: "Alertes automatiques" },
    { view: "amont", label: "Projets à venir", ic: "calendar-clock", si: "projets_a_venir" }] },
  // Vague 2a (A2) : « Où je suis partenaire » et « À plusieurs » sont des FILTRES de la liste (plus des onglets) ; les
  // vues « shared » et « consortiums » n'existent plus que comme raccourcis de go() vers ces filtres.
  { k: "marches", label: "Mes marchés", ic: "folder-kanban",
    vues: ["pipeline", "shared", "consortiums", "invoices", "bilan", "aodetail", "atelier", "sharedao"], onglets: [
    { view: "pipeline", label: "Marchés", ic: "folder-kanban", pastille: "partenaire",
      avant: "« Où je suis partenaire » (anciennement « Partagé avec moi ») et « À plusieurs » (anciennement « Mes groupements ») sont des filtres de cette liste." },
    { view: "invoices", label: "Devis et factures", ic: "receipt", ancien: "Devis & factures" },
    { view: "bilan", label: "Bilan", ic: "chart-column", avant: "« Où vous gagnez / perdez » était sur l'accueil." }] },
  { k: "partenaires", label: "Partenaires", ic: "handshake", vues: ["cotraitants", "reseau", "contacts"], onglets: [
    { view: "cotraitants", label: "Mes partenaires", ic: "handshake" },
    { view: "reseau", label: "Réseau Adjugo", ic: "network", ancien: "Réseau" },
    { view: "contacts", label: "Contacts", ic: "contact-round" }] },
  { k: "documents", label: "Mes documents", ic: "folder-lock", vues: ["documents", "kb"], onglets: [
    { view: "documents", label: "Mes pièces", ic: "folder-lock", pastille: "pieces" },
    { view: "kb", label: "Mon savoir-faire", ic: "library" }] },
  // Vague 2a (A3) : Mon entreprise en 4 onglets, Identité · Ce que je cherche · Mes preuves · Tarifs (étude, § 5.3).
  { k: "entreprise", label: "Mon entreprise", ic: "building-2", vues: ["company", "criteria", "preuves", "tarifs"], onglets: [
    { view: "company", label: "Identité", ic: "building-2", ancien: "Profil de l'entreprise" },
    { view: "criteria", label: "Ce que je cherche", ic: "sliders-horizontal", ancien: "Mes critères" },
    { view: "preuves", label: "Mes preuves", ic: "award" },
    { view: "tarifs", label: "Tarifs", ic: "calculator", avant: "Vos tarifs étaient dans l'onglet « Identité »." }] },
  { k: "reglages", label: "Réglages", ic: "settings", groupe: true, vues: ["team", "billing", "compte", "admin"], onglets: [
    { view: "team", label: "Collègues", ic: "users-round", ancien: "Équipe" },
    { view: "billing", label: "Abonnement", ic: "credit-card" },
    { view: "compte", label: "Mon compte", ic: "circle-user", avant: "Votre mot de passe et vos données étaient dans « Équipe »." },
    { view: "admin", label: "Administration", ic: "shield", si: "admin" }] },
];
// ══════════ Mes marchés en liste filtrable (réorganisation, vague 2a, A2 ; contrat docs/REORGANISATION_V2A.md) ══════════
// Une seule liste réunit ce que montraient « Mes marchés », « Où je suis partenaire » et « À plusieurs » : mes marchés
// (/api/projects/), ceux d'autres entreprises où je suis partenaire (/api/shared) et mes groupements (/api/consortiums),
// TELS QUE le serveur les renvoie — rien de plus n'est demandé ni montré. Filtres : Tous, Je pilote, Où je suis
// partenaire, À plusieurs (mes marchés avec au moins un partenaire invité, et ceux où je suis partenaire). Groupés par
// statut, dans l'ordre `ordre` (statuses2). Un marché où je suis partenaire n'a pas de statut à lui : « Déposé » quand
// le chef de file l'a marqué déposé (étape du groupement que son espace lui montre), « En cours » sinon.
const MM_FILTRES = ["tous", "pilote", "partenaire", "plusieurs"];
// Nom d'entreprise comparable (sans accents, minuscules, espaces simples) : la règle du serveur (groupement_members.nom_cle).
function nomCle(s) { return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/\s+/).filter(Boolean).join(" "); }
function statutPartenaire(s) { return s && s.groupement && s.groupement.state === "depose" ? "depose" : "en_cours"; }
function listeMesMarches(projets, partages, groupements, filtre, ordre) {
  const f = MM_FILTRES.indexOf(filtre) >= 0 ? filtre : "tous";
  const plus = {};
  (groupements || []).forEach(c => { if (c && c.partners) plus[c.project_id] = true; });
  const statut = p => p.status || "nouveau";
  const pilotes = f === "partenaire" ? [] : (projets || []).filter(p => p && (f !== "plusieurs" || plus[p.id]));
  const partenaires = f === "pilote" ? [] : (partages || []).filter(Boolean);
  const cles = (ordre || []).slice();
  pilotes.map(statut).concat(partenaires.map(statutPartenaire)).forEach(k => { if (cles.indexOf(k) < 0) cles.push(k); });
  return cles.map(k => ({ k, pilotes: pilotes.filter(p => statut(p) === k), partenaires: partenaires.filter(x => statutPartenaire(x) === k) }))
    .filter(g => g.pilotes.length || g.partenaires.length);
}
// Invitations reçues par le réseau (anciennement l'onglet « Invitations reçues » du Réseau) montrées en tête de la liste :
// celles à accepter ou décliner, celles déclinées pendant cette visite, et une invitation acceptée seulement si son marché
// n'est pas déjà dans la liste (acceptée par un collègue : « Voir l'invitation »). Rien n'y disparaît par rapport à avant.
function invitationsATraiter(recues, partages) {
  const dans = new Set((partages || []).map(x => x && x.token).filter(Boolean));
  return (recues || []).filter(i => i && (i._declined || i.statut !== "acceptee" || !dans.has(i.token)));
}

// Nom affiché d'un dossier rangé (réorganisation, vague 1) : la clé stockée ne change pas (« CERFA », « DCE »,
// « Mémoire technique », app/services/dossier.py), seul le nom lu par le client.
const DOSSIERS_AFFICHES = { "CERFA": "Formulaires officiels", "DCE": "Dossier du marché",
                            "Mémoire technique": "Dossier de présentation" };
function nomDossier(f) { return DOSSIERS_AFFICHES[f] || (f || ""); }
// Rubrique d'une vue (null : vue inconnue).
function rubriqueDe(view) { return RUBRIQUES.find(r => r.vues.indexOf(view) >= 0) || null; }
// Onglet affiché pour (vue, onglet interne) : celui de la vue, et pour Trouver des marchés celui de l'onglet interne.
function ongletDe(view, sous) {
  const r = rubriqueDe(view); if (!r) return null;
  return r.onglets.find(t => t.view === view && (!t.sous || t.sous === sous)) || null;
}
// Phrase « ancien nom » d'un onglet (transition, 1.8) : "" s'il n'a pas changé de nom.
function ancienNom(t) {
  if (!t) return "";
  if (t.avant) return t.avant;
  return t.ancien ? "Anciennement « " + t.ancien + " »." : "";
}
// Note « Ce qui a changé » (1.8) : comptes créés avant la nouvelle organisation, hors démonstration, pas encore
// fermée, une semaine au plus après son premier affichage. `etat` : { vu: horodatage, ferme: bool } (localStorage).
const REORG_V1_DEPUIS = "2026-10-20";        // jour de mise en ligne du menu par rubriques
const REORG_V1_DUREE_MS = 7 * 24 * 3600 * 1000;
const DEMO_EMAIL_APP = "demo@adjugo.fr";     // = app/services/demo_seed.DEMO_EMAIL (vérifié par les tests)
// La transition (note et anciens noms en bulle) ne parle qu'à ceux qui ont connu l'ancienne organisation : un compte
// créé avant REORG_V1_DEPUIS, jamais la démonstration (un prospect n'a jamais vu ces noms) ni un compte neuf.
function transitionVisible(user) {
  if (!user || !user.created_at) return false;
  if (String(user.email || "").trim().toLowerCase() === DEMO_EMAIL_APP) return false;
  return String(user.created_at).slice(0, 10) < REORG_V1_DEPUIS;
}
function noteReorgVisible(user, etat, maintenant) {
  if (!transitionVisible(user)) return false;
  const e = etat || {};
  if (e.ferme) return false;
  return !e.vu || (maintenant - e.vu) < REORG_V1_DUREE_MS;
}

// ══════════ Une adresse par écran (réorganisation, vague 2a, A1) ══════════
// Chaque écran a son chemin sous /app ; le serveur sert la même page à chacun (app/main.py). Le bouton « précédent »
// du navigateur revient à l'écran d'avant, sur plusieurs niveaux ; un lien, un favori ou un rechargement rouvrent le
// bon écran. Routage par CHEMIN, jamais par « # » : le fragment porte le code de connexion Google (#gcode=…). Les
// paramètres des liens envoyés (?shared=, ?verify=, ?reset=, ?inscription) sont lus au démarrage, comme avant.
// `ADRESSES` : vue → chemin. Les pages de détail portent un identifiant : /app/marches/12 (le marché),
// /app/marches/12/dossier-de-presentation (l'atelier), /app/marches/partenaire/34 (un marché où vous êtes partenaire :
// l'identifiant du marché, jamais le jeton d'invitation). Contrat : docs/REORGANISATION_V2A.md, A1 et réunion.
// Réunion des chantiers A1 et A2 : « Où je suis partenaire » et « À plusieurs » sont des FILTRES de la liste de Mes
// marchés (plus des vues) ; chaque filtre garde son adresse (`ADRESSES_MES_MARCHES`), et l'ancienne adresse des
// invitations reçues du Réseau (/app/partenaires/reseau/invitations) mène au filtre où elles se traitent maintenant.
// Réunion avec A3 : Mon entreprise a 4 onglets (Identité · Ce que je cherche · Mes preuves · Tarifs), chacun son adresse.
const ADRESSES = {
  dashboard: "", sourcing: "trouver", amont: "trouver/projets-a-venir",
  pipeline: "marches", invoices: "marches/devis-et-factures", bilan: "marches/bilan",
  cotraitants: "partenaires", reseau: "partenaires/reseau", contacts: "partenaires/contacts",
  documents: "documents", kb: "documents/savoir-faire",
  company: "entreprise", criteria: "entreprise/ce-que-je-cherche", preuves: "entreprise/preuves", tarifs: "entreprise/tarifs",
  team: "reglages/collegues", billing: "reglages/abonnement", compte: "reglages/compte", admin: "reglages/administration",
};
const ADRESSES_TROUVER = { avenir: "a-venir", alertes: "alertes" };                 // onglets de Trouver des marchés
const ADRESSES_RESEAU = { annuaire: "annuaire", historique: "historique" };   // « profil » : la vue
const ADRESSES_MES_MARCHES = { pilote: "je-pilote", partenaire: "partenaire", plusieurs: "a-plusieurs" };   // « tous » : la vue
const ADRESSE_ATELIER = "dossier-de-presentation";
function _adrId(n) { const t = String(n == null ? "" : n); return /^[1-9][0-9]{0,11}$/.test(t) ? t : ""; }
// Relecture de la vague 2a : un même compte peut être partenaire deux fois du même marché (partenaire du groupement
// sur une partie, sous-traitant sur une autre). L'adresse d'un dossier partagé porte donc, après l'identifiant du
// marché, un REPÈRE de l'invitation : une empreinte courte de son jeton (7 caractères, FNV-1a 32 bits), dont on ne
// retrouve pas le jeton — le jeton, lui, ne va jamais dans l'adresse. /app/marches/partenaire/34/k3j9x2a.
function clePartage(jeton) {
  const t = String(jeton || ""); if (!t) return "";
  let h = 0x811c9dc5;
  for (let i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return ("000000" + h.toString(36)).slice(-7);
}
function _adrCle(c) { const t = String(c == null ? "" : c); return /^[0-9a-z]{7}$/.test(t) ? t : ""; }
// Le dossier partagé que désigne une adresse, dans `partages` (GET /api/shared, du plus récent au plus ancien) : celui
// du marché dont le repère est `cle` ; sans repère (adresse tapée, ou d'avant ce repère), le plus ancien de ce marché.
// null : aucun (invitation révoquée, déclinée, d'un autre compte).
function trouverPartage(partages, projet, cle) {
  const l = (partages || []).filter(x => x && x.project_id === projet);
  if (cle) return l.find(x => clePartage(x.token) === cle) || null;
  return l.length ? l[l.length - 1] : null;
}
// Chemin de l'écran décrit par `e` ({ view, sous, projet, partage, reseau, filtre }) ; null si l'écran n'a pas d'adresse (une
// page de détail sans son identifiant) : l'adresse ne change pas.
function adresseDe(e) {
  e = e || {};
  if (e.view === "aodetail") return _adrId(e.projet) ? "/app/marches/" + _adrId(e.projet) : null;
  if (e.view === "atelier") return _adrId(e.projet) ? "/app/marches/" + _adrId(e.projet) + "/" + ADRESSE_ATELIER : null;
  if (e.view === "sharedao") return _adrId(e.partage) ? "/app/marches/partenaire/" + _adrId(e.partage) + (_adrCle(e.cle) ? "/" + _adrCle(e.cle) : "") : null;
  if (!Object.prototype.hasOwnProperty.call(ADRESSES, e.view)) return null;
  let c = "/app" + (ADRESSES[e.view] ? "/" + ADRESSES[e.view] : "");
  if (e.view === "sourcing" && ADRESSES_TROUVER[e.sous]) c += "/" + ADRESSES_TROUVER[e.sous];
  if (e.view === "reseau" && ADRESSES_RESEAU[e.reseau]) c += "/" + ADRESSES_RESEAU[e.reseau];
  if (e.view === "pipeline" && ADRESSES_MES_MARCHES[e.filtre]) c += "/" + ADRESSES_MES_MARCHES[e.filtre];
  return c;
}
// L'écran que demande un chemin : null hors de /app ; { view: "dashboard", inconnue: true } pour un chemin inconnu.
function etatDeAdresse(chemin) {
  const p = String(chemin || "").split(/[?#]/)[0].replace(/\/+$/, "");
  if (p !== "/app" && p.indexOf("/app/") !== 0) return null;
  const r = p.slice(5).split("/").filter(Boolean).join("/");
  if (!r) return { view: "dashboard" };
  let m = /^marches\/([1-9][0-9]{0,11})$/.exec(r);
  if (m) return { view: "aodetail", projet: Number(m[1]) };
  m = /^marches\/([1-9][0-9]{0,11})\/dossier-de-presentation$/.exec(r);
  if (m) return { view: "atelier", projet: Number(m[1]) };
  m = /^marches\/partenaire\/([1-9][0-9]{0,11})(?:\/([0-9a-z]{7}))?$/.exec(r);
  if (m) return m[2] ? { view: "sharedao", partage: Number(m[1]), cle: m[2] } : { view: "sharedao", partage: Number(m[1]) };
  for (const v of Object.keys(ADRESSES)) if (ADRESSES[v] && ADRESSES[v] === r) return v === "sourcing" ? { view: v, sous: "publies" } : { view: v };
  for (const k of Object.keys(ADRESSES_TROUVER)) if (r === ADRESSES.sourcing + "/" + ADRESSES_TROUVER[k]) return { view: "sourcing", sous: k };
  for (const k of Object.keys(ADRESSES_RESEAU)) if (r === ADRESSES.reseau + "/" + ADRESSES_RESEAU[k]) return { view: "reseau", reseau: k };
  for (const k of Object.keys(ADRESSES_MES_MARCHES)) if (r === ADRESSES.pipeline + "/" + ADRESSES_MES_MARCHES[k]) return { view: "pipeline", filtre: k };
  if (r === ADRESSES.reseau + "/invitations") return { view: "pipeline", filtre: "partenaire" };   // invitations reçues (A2)
  return { view: "dashboard", inconnue: true };
}

// ══════════ Réorganisation, vague 2a (chantier A3) ══════════
// Fenêtre de confirmation de l'application (elle remplace les confirm() et prompt() du navigateur) : les champs
// sont-ils valables ? Un champ `requis` doit être rempli ; un champ `attendu` (« SUPPRIMER ») doit valoir ce mot, sans
// tenir compte de la casse ni des espaces autour ; un champ `motif` (expression régulière) doit le suivre quand il
// est rempli. Fonction pure, testée sous Node (tests/test_reorganisation_v2a_entreprise.py).
function champsValides(fields) {
  return (fields || []).every(f => {
    const v = String(f && f.value != null ? f.value : "").trim();
    if (f.attendu) return v.toUpperCase() === String(f.attendu).trim().toUpperCase();
    if (f.requis && !v) return false;
    if (f.motif && v && !new RegExp(f.motif).test(v)) return false;
    return true;
  });
}
// Mes documents : la catégorie d'une pièce (clé stockée → libellé lu ; app/models DocCategory), modifiable dans la
// liste. Une clé inconnue s'affiche « Autre ».
const CATEGORIES_DOC = [
  { k: "administratif", label: "Administratif" }, { k: "fiscal", label: "Fiscal et social" },
  { k: "assurances", label: "Assurances" }, { k: "qualifications", label: "Qualifications" }, { k: "autre", label: "Autre" }];
function categorieDoc(k) { const c = CATEGORIES_DOC.find(x => x.k === k); return c ? c.label : "Autre"; }
// « lot » devient « partie (lot n) » à l'écran (décision 10) : l'entreprise lit « partie », et retrouve le numéro du
// règlement entre parenthèses. `x` : un numéro (« 2 »), ou un libellé du serveur (« Lot 2 — Couverture », gardé tel
// quel dans les fichiers exportés et les données) ; `minuscule` : au milieu d'une phrase. Un texte libre (le
// périmètre saisi par un partenaire) reste tel quel. Même fonction dans redaction-partenaire.js et carnet-notes.js
// (chargés aussi par invite.html, sans app.js) : tests/test_reorganisation_v2a_entreprise.py vérifie que ce sont les mêmes.
function partieLot(x, intitule, minuscule) {
  if (typeof intitule === "boolean") { minuscule = intitule; intitule = ""; }
  const s = String(x == null ? "" : x).trim();
  const m = /^(?:lot\s*(?:n\s*[°o.]?\s*)?)?0*(\d{1,3})(?:\s*[—–:-]\s*(.*))?$/i.exec(s);
  if (!m || (!/^lot/i.test(s) && !/^\d+$/.test(s))) return s;
  const reste = String(intitule || m[2] || "").trim();
  return (minuscule ? "partie" : "Partie") + " (lot " + m[1] + ")" + (reste ? " — " + reste : "");
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

// ══════════ Un seul axe d'étapes (réorganisation, vague 2a, A1 ; décision 7) — fonctions pures ══════════
// Les étapes d'un marché, dans l'ordre, sous leur clé stockée (app.models.ProjectStatus) : À venir (une carte créée
// avant la publication, décision 11) → Repéré → Décidé → En préparation → Déposé → Gagné / Perdu, plus Abandonné.
// Le choix « Statut » de la page du marché, Mes marchés et l'entonnoir de l'accueil lisent cette seule liste. La clé
// « envoye » est devenue « depose » (migration c4axeetapes) ; un devis ou une facture, eux, restent « Envoyé ».
const AXE_ETAPES = [
  { k: "suivi", label: "À venir" }, { k: "nouveau", label: "Repéré" }, { k: "decide", label: "Décidé" },
  { k: "en_cours", label: "En préparation" }, { k: "depose", label: "Déposé" }, { k: "gagne", label: "Gagné" },
  { k: "perdu", label: "Perdu" }, { k: "abandonne", label: "Abandonné" },
];
function libelleStatut(s) { const x = AXE_ETAPES.find(e => e.k === s); return x ? x.label : (s || ""); }
// Ce que change une décision de l'étape Décider, jamais en arrière : « Préparer seul » et « Préparer à plusieurs »
// mènent à Décidé (un marché déjà décidé ou en préparation ne bouge pas ; un marché écarté est repris ; un marché
// « À venir » le reste jusqu'à sa publication, on peut déjà y inviter ses partenaires) ; « Écarter » mène à
// Abandonné ; « Remettre » ramène un marché écarté à Repéré. null : le statut ne change pas.
function statutApresDecision(statut, choix) {
  const s = statut || "nouveau";
  if (["depose", "gagne", "perdu"].indexOf(s) >= 0) return null;
  if (choix === "seul" || choix === "plusieurs") return ["nouveau", "abandonne"].indexOf(s) >= 0 ? "decide" : null;
  if (choix === "ecarter") return s === "abandonne" ? null : "abandonne";
  if (choix === "remettre") return s === "abandonne" ? "nouveau" : null;
  return null;
}
// Relecture de la vague 2a : les étapes d'où part chaque geste, celles où statutApresDecision et statutEnPreparation
// font avancer le marché. L'écran les envoie au serveur avec le changement (PUT /api/projects/{id}, `si_statut`) : le
// serveur ne change l'étape que si le marché y est encore. Une page ou une liste ouverte avant un « Marquer déposé »
// (le vôtre, celui d'un collègue) ne fait donc jamais reculer un marché ; le choix « Statut », lui, reste libre.
const DEPARTS_GESTE = {
  seul: ["nouveau", "abandonne"], plusieurs: ["nouveau", "abandonne"], remettre: ["abandonne"],
  ecarter: ["suivi", "nouveau", "decide", "en_cours"], preparer: ["nouveau", "decide"],
};
// Un geste de l'étape Préparer (estimer le prix, ouvrir le dossier de présentation, préparer les formulaires, inviter
// un partenaire) : un marché Repéré ou Décidé passe En préparation. null : il y est déjà, ou plus loin, ou il est
// « À venir » (pas encore publié : il le reste).
function statutEnPreparation(statut) { return ["nouveau", "decide"].indexOf(statut || "nouveau") >= 0 ? "en_cours" : null; }

// ══════════ Page du marché en 4 étapes (réorganisation, vague 1, 1.5 ; décision 6) — fonctions pures ══════════
// L'étape en cours de la barre Lire · Décider · Préparer · Déposer, déduite de ce que l'écran sait déjà : le statut
// du marché, le dossier du marché lu ou non, l'étape du groupement (1 à 5, dérivée côté serveur). Une indication,
// jamais un blocage : chaque étape s'ouvre à tout moment. Aucune étape surlignée pour un marché gagné, perdu ou
// abandonné (son bilan est en tête de page). Vague 2a (un seul axe) : un marché Décidé ou En préparation est à
// l'étape Préparer, dossier lu ou non (l'étape Lire dit alors « À faire »).
const ETAPES_LIBELLES = { lire: "Lire", decider: "Décider", preparer: "Préparer", deposer: "Déposer" };
function etapeDuMarche(statut, dossierLu, etapeGroupement) {
  const e = Number(etapeGroupement) || 1;
  if (statut === "gagne" || statut === "perdu" || statut === "abandonne") return "";
  if (statut === "depose" || e >= 5) return "deposer";
  if (statut === "decide" || statut === "en_cours" || e >= 2) return "preparer";
  return dossierLu ? "decider" : "lire";
}
// La barre affiche des statuts DÉRIVÉS (décision 7) : pour chacune des 4 étapes, « Terminé », « En cours » ou
// « À faire », lus dans le statut du marché, le dossier lu et l'étape du groupement ; rien n'est stocké. Lire est
// « Terminé » dès que le dossier du marché est lu ; une étape avant l'étape en cours est « Terminé » ; un marché
// déposé, gagné ou perdu a ses 4 étapes faites ; un marché écarté n'en a aucune en cours.
const BARRE_ETATS = { fait: "Terminé", en_cours: "En cours", a_faire: "À faire" };
function barreDuMarche(statut, dossierLu, etapeGroupement) {
  const ordre = ["lire", "decider", "preparer", "deposer"], cur = etapeDuMarche(statut, dossierLu, etapeGroupement);
  const fini = statut === "depose" || statut === "gagne" || statut === "perdu", ic = ordre.indexOf(cur);
  return ordre.map((k, i) => {
    let etat = "";
    if (fini) etat = "fait";
    else if (statut !== "abandonne") {
      if (k === "lire") etat = dossierLu ? "fait" : (cur === "lire" ? "en_cours" : "a_faire");
      else etat = i < ic ? "fait" : (i === ic ? "en_cours" : "a_faire");
    }
    return { k, label: ETAPES_LIBELLES[k], etat, statut: BARRE_ETATS[etat] || "", courante: k === cur };
  });
}

// ══════════ « À faire » (réorganisation, vague 2a, A1) — fonction pure ══════════
// Une seule liste de ce qui attend VOTRE action, lue par la cloche (onglet « À faire ») et par le bloc « À faire » de
// l'accueil (étude, § 5.3). Des faits que l'écran connaît déjà, rien d'autre : marchés où vous êtes partenaire (votre
// accord est demandé, une partie du dossier de présentation vous attend), invitations reçues par le réseau, dates
// limites de vos marchés dans les 7 jours, parts de partenaires encore attendues, pièces à renouveler. Jamais un total
// ni zéro : une liste vide n'affiche rien. Chaque ligne dit son action et l'écran qu'elle ouvre (`cible`).
// `d` : { shared, recues, projects, enCours, expiring } ; `aujourdhui` : « AAAA-MM-JJ ».
const A_FAIRE_JOURS = 7;
function listeAFaire(d, aujourdhui) {
  d = d || {};
  const out = [], jour = s => { const t = Date.parse(String(s || "").slice(0, 10) + "T00:00:00Z"); return isNaN(t) ? null : t; };
  const auj = jour(aujourdhui), dd = s => { const t = String(s || "").slice(0, 10).split("-"); return t.length === 3 ? t[2] + "/" + t[1] : ""; };
  (d.shared || []).forEach((s, i) => {
    const g = s.groupement || {}, r = s.redaction || {}, cible = { view: "sharedao", partage: s.project_id, jeton: s.token };
    const marche = s.project || "Marché";
    if (g.a_valider) out.push({ k: "accord-" + s.project_id + (i ? "-" + i : ""), ic: "signature", rang: 0, titre: "Votre accord est demandé",
      detail: marche + (s.mandataire ? " · chef de file : " + s.mandataire : ""), cta: "Lire et donner mon accord", cible });
    if (r.a_faire || r.a_revalider || r.a_valider || r.questions) out.push({ k: "redaction-" + s.project_id + (i ? "-" + i : ""), ic: "file-pen-line", rang: 1,
      titre: "Une partie du dossier de présentation vous attend", detail: marche, cta: "Ouvrir", cible });
  });
  (d.recues || []).filter(i => i && !i._declined && i.statut !== "acceptee").forEach(i => out.push({
    k: "invitation-" + i.token, ic: "inbox", rang: 2, titre: "Invitation à répondre ensemble",
    detail: (i.project || "Marché") + (i.mandataire ? " · chef de file : " + i.mandataire : ""), cta: "Voir l'invitation",
    cible: { view: "shared" } }));      // Mes marchés, filtre « Où je suis partenaire » (A2)
  (d.projects || []).forEach(p => {
    if (!p || p.deleted_at || ["suivi", "nouveau", "decide", "en_cours"].indexOf(p.status || "nouveau") < 0 || auj === null) return;
    const t = jour(p.deadline); if (t === null) return;
    const n = Math.round((t - auj) / 86400000); if (n < 0 || n > A_FAIRE_JOURS) return;
    out.push({ k: "date-" + p.id, ic: "clock", rang: 3, tri: n, cta: "Ouvrir", detail: p.name || "Marché",
      titre: n === 0 ? "Date limite aujourd'hui" : (n === 1 ? "Date limite demain" : "Date limite dans " + n + " jours"),
      cible: { view: "aodetail", projet: p.id } });
  });
  (d.enCours || []).forEach(g => {
    const n = Number(g && g.n_membres) || 0, ns = Number(g && g.n_parts) || 0;
    if (!n || ns >= n) return;
    out.push({ k: "parts-" + g.project_id, ic: "handshake", rang: 4, titre: "Parts reçues " + ns + " sur " + n,
      detail: g.name || "Marché", cta: "Ouvrir", cible: { view: "aodetail", projet: g.project_id } });
  });
  const ex = (d.expiring || []).filter(Boolean);
  if (ex.length) {
    const p0 = ex.slice().sort((a, b) => String(a.expiration_date).localeCompare(String(b.expiration_date)))[0];
    const passe = auj !== null && jour(p0.expiration_date) !== null && jour(p0.expiration_date) < auj;
    out.push({ k: "pieces", ic: "folder-lock", rang: 5, cta: "Voir", cible: { view: "documents" },
      titre: ex.length + " " + (ex.length > 1 ? "pièces à renouveler" : "pièce à renouveler"),
      detail: (p0.name || "Pièce") + (dd(p0.expiration_date) ? (passe ? " · expirée le " : " · expire le ") + dd(p0.expiration_date) : "") });
  }
  return out.sort((a, b) => a.rang - b.rang || (a.tri || 0) - (b.tri || 0));
}

// Préparer › À plusieurs : les étapes 2 à 4 du groupement deviennent des tâches. Des FAITS lus dans l'état dérivé
// du serveur (GET /groupement/state, jamais stocké) : partenaires invités, parts reçues avec leur prix, convention et
// accords, offre figée ; rien d'autre n'est calculé. La 5e étape (« Déposer ») est l'étape Déposer de la page. Vide
// tant que le groupement n'a pas commencé (étape 1 : « Repérer le marché »). Trois statuts seulement.
function tachesPlusieurs(st) {
  if (!st || (Number(st.etape) || 1) < 2) return [];
  const n = Number(st.n_members) || 0, ns = Number(st.n_submitted) || 0, np = Number(st.n_with_price) || 0;
  const cv = st.convention_status && st.convention_status !== "aucune" ? st.convention_status : "";
  const c = st.convention || {}, statut = { fait: "Terminé", en_cours: "En cours", a_faire: "Pas commencé" };
  const t = (key, label, etat, detail, voir) => ({ key, label, etat, statut: statut[etat], detail, voir });
  return [
    t("inviter", "Partenaires invités", n ? "fait" : "a_faire", n ? n + " " + (n > 1 ? "partenaires" : "partenaire") : "", "invitations"),
    t("parts", "Parts reçues", !n ? "a_faire" : (ns === n && np === n ? "fait" : (ns ? "en_cours" : "a_faire")), n ? ns + " sur " + n : "", "parts"),
    t("convention", "Convention et accords", cv === "signee" ? "fait" : (cv ? "en_cours" : "a_faire"),
      cv === "a_signer" && c.n_signataires ? "accords " + (Number(c.n_accords) || 0) + " sur " + c.n_signataires
        : ({ signee: "validée par tous", perimee: "à revalider", draft: "brouillon" })[cv] || "", "convention"),
    t("offre", "Offre commune", st.offer_frozen ? "fait" : "a_faire", st.offer_frozen ? "figée" : "", "convention"),
  ];
}

// État initial de « Partagé avec moi » (vue co-traitant avec compte) — plus de chiffrage_note : prix de vente du lot
// en clair + détail chiffré dans le navigateur (enveloppe), capacités déclarées, signataire, pièces typées.
function _sharedInit(token, mandataire, projectId, role) {
  return { token: token || "", cle: clePartage(token), projectId: projectId || null, project: null, mandataire: mandataire || "", role: role || "cotraitant", docs: [], status: "", version: 0, busy: false, msg: "", pieces: [], canContribute: true, loading: false, error: "",
           forMember: null, coffre: null, journal: null, journalLoaded: false, conv: _sconvInit(),
           // Vague 4 : vérification du journal par le membre (verdict du serveur, exports JSON / PDF).
           jv: { busy: false, v: null, err: "", live: "", exporting: "" },
           // detailDpgf : lignes de la DPGF rangées dans le même détail chiffré (AdjugoCrypto.packDetail) ;
           // cet écran ne les modifie pas mais les conserve à chaque enregistrement.
           envelope: null, detailClair: "", detailDpgf: null, detailLocked: false, cryptoCtx: null, pendingCode: null, detailLoaded: false,
           upl: { piece_type: "", expiration_date: "" }, vault: { open: false, loading: false, docs: [], needClaim: false, pendingDoc: null },
           // Vague 5 (E2) : les références telles qu'enregistrées (acheteur, montant, provenance « source publique DECP ») :
           // la zone « une par ligne » n'en montre que l'intitulé, l'enregistrement les garde.
           refsRiches: [],
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

// ══════════ « Mes preuves » (rédaction, vague 3, E1) — état et listes fermées ══════════
// Contrat : docs/REDACTION_V3_PREUVES.md. L'écran montre ce que dit le serveur (où le fait a été
// trouvé, validité, raison) : aucune note de confiance, jamais le mot interdit, aucune IA.
function _pvInit() {
  return { loaded: false, loading: false, error: "", list: [], tab: "reference", form: null, sel: {}, busy: "",
           passage: null, rep: { open: false, loading: false, d: null, sel: {}, err: "", busy: false } };
}
function _pvAtlInit() { return { open: false, loading: false, d: null, q: "", err: "", choix: null, busy: false, pos: null, sid: null }; }
function _pvJj(s) { const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + "/" + m[2] + "/" + m[1] : ""; }
const PV_NATURES = [
  { code: "reference", l: "Références", ic: "briefcase-business", ajout: "Ajouter une référence",
    tip: "Vos marchés réalisés ou attribués. Un marché repris des données publiques (DECP) est dit « marché attribué » : l'attribution ne prouve ni l'exécution ni sa qualité. Adjugo ne complète jamais une fiche : l'acheteur, l'année ou le montant viennent de vous, de vos documents ou de la source publique." },
  { code: "qualification", l: "Qualifications", ic: "scroll-text", ajout: "Ajouter une qualification",
    tip: "Certifications et qualifications professionnelles (Qualibat, RGE…), avec leur date de fin de validité : une fiche dont la date est dépassée n'est plus utilisée." },
  { code: "salarie", l: "Équipe", ic: "hard-hat", ajout: "Ajouter une personne",
    tip: "Un CV court par personne : fonction, expérience, diplômes, habilitations, chantiers. Ni photo, ni adresse, ni date de naissance. Le CV n'est jamais envoyé à l'IA : Adjugo l'insère tel quel dans votre dossier quand vous le choisissez." },
  { code: "materiel", l: "Matériel", ic: "truck", ajout: "Ajouter du matériel",
    tip: "Vos engins et équipements, en propre ou en location." },
  { code: "chiffre_cle", l: "Chiffres clés", ic: "hash", ajout: "Ajouter un chiffre clé",
    tip: "Effectif, chiffre d'affaires, ou une estimation (délai, effectif prévu, quantité). Une estimation peut ne valoir que pour un marché." },
];
// Champs de chaque nature (liste fermée du serveur, § 2 du contrat). n : longueur max ; t : num | area | select.
const PV_CHAMPS = {
  reference: [
    { k: "objet", l: "Objet du marché", req: true, n: 300, ph: "Réfection de la toiture de l'école", w: true },
    { k: "acheteur", l: "Acheteur", n: 200, ph: "Mairie de Quimper" },
    { k: "lieu", l: "Lieu", n: 120, ph: "Quimper" },
    { k: "annee", l: "Année", t: "num", min: 1900, max: 2100, ph: "2024" },
    { k: "montant_ht", l: "Montant HT (€)", t: "num", min: 0, ph: "85000" },
    { k: "role", l: "Rôle", t: "select", opts: [["", "Non précisé"], ["seul", "Seul"], ["groupement_conjoint", "En groupement conjoint"],
                                                  ["groupement_solidaire", "En groupement solidaire"], ["sous_traitant", "En sous-traitance"]] },
    { k: "description", l: "Description", t: "area", n: 1000, w: true, ph: "Ce qui a été fait, en quelques lignes" },
  ],
  qualification: [
    { k: "nom", l: "Qualification", req: true, n: 200, ph: "Qualibat 3194", w: true },
    { k: "organisme", l: "Délivrée par", n: 120, ph: "Qualibat" },
    { k: "numero", l: "Numéro", n: 60, ph: "12345" },
    { k: "detail", l: "Détail", n: 300, w: true, ph: "Couverture en ardoises" },
  ],
  salarie: [
    { k: "nom", l: "Nom", req: true, n: 120, ph: "Yann Tanguy" },
    { k: "fonction", l: "Fonction", req: true, n: 120, ph: "Conducteur de travaux" },
    { k: "experience_annees", l: "Années d'expérience", t: "num", min: 0, max: 70, ph: "15" },
    { k: "diplomes", l: "Diplômes", n: 300, ph: "BTS Bâtiment" },
    { k: "qualifications", l: "Qualifications et habilitations", n: 300, w: true, ph: "CACES R486, SST" },
    { k: "chantiers", l: "Chantiers", t: "area", n: 1000, w: true, ph: "12 réfections de toiture scolaire" },
  ],
  materiel: [
    { k: "designation", l: "Désignation", req: true, n: 200, ph: "Nacelle 18 m", w: true },
    { k: "quantite", l: "Quantité", t: "num", min: 1, ph: "2" },
    { k: "possession", l: "Possession", t: "select", opts: [["", "Non précisé"], ["propriete", "En propre"], ["location", "En location"]] },
    { k: "caracteristiques", l: "Caractéristiques", n: 300, w: true, ph: "Ciseaux, électrique" },
  ],
  chiffre_cle: [
    { k: "libelle", l: "Libellé", req: true, n: 120, ph: "Effectif", w: true },
    { k: "valeur", l: "Valeur", req: true, t: "num", ph: "14" },
    { k: "unite", l: "Unité", n: 40, ph: "personnes" },
    { k: "annee", l: "Année", t: "num", min: 1900, max: 2100, ph: "2025" },
  ],
};
const PV_SOURCES = [
  { code: "declare", l: "Déclaré par vous", natures: null },
  { code: "documents", l: "Dans vos documents", natures: null },
  { code: "public", l: "Source publique", natures: ["reference", "qualification"] },
  { code: "estimation", l: "Votre estimation", natures: ["chiffre_cle"] },
];
// Natures qui ont une fin de validité, et son libellé dans le formulaire.
const PV_VALIDITE = { qualification: "Valable jusqu'au", salarie: "Habilitations valables jusqu'au", materiel: "Valable jusqu'au" };
const PV_ALERTE_JOURS = 60;
// Texte d'une fiche à l'écran : titre et détails tels que saisis, sans rien compléter.
function pvNombre(x) { const n = Number(x); return (x === "" || x == null || !isFinite(n)) ? String(x == null ? "" : x) : n.toLocaleString("fr-FR"); }
function pvTitre(p) {
  const v = (p && p.valeur) || {};
  if (p.nature === "salarie") return [v.nom, v.fonction].filter(Boolean).join(", ");
  if (p.nature === "chiffre_cle") return (v.libelle || "") + " : " + pvNombre(v.valeur) + (v.unite ? " " + v.unite : "");
  return v.objet || v.nom || v.designation || "";
}
// Une référence tirée des DECP : un marché ATTRIBUÉ, jamais « réalisé » (l'attribution ne prouve ni l'exécution ni
// sa qualité) — mêmes mots que le texte du serveur (preuves.texte_de).
function pvAttribue(p) { return !!p && p.nature === "reference" && String(p.source_libelle || "").startsWith("marché attribué"); }
function pvDetail(p) {
  const v = (p && p.valeur) || {}, out = [];
  const role = pvAttribue(p)
    ? { seul: "attribué seul", groupement_conjoint: "attribué en groupement conjoint", groupement_solidaire: "attribué en groupement solidaire", sous_traitant: "en sous-traitance" }
    : { seul: "réalisé seul", groupement_conjoint: "en groupement conjoint", groupement_solidaire: "en groupement solidaire", sous_traitant: "en sous-traitance" };
  const a = (x) => { if (x != null && x !== "") out.push(String(x)); };
  if (p.nature === "reference") {
    a(v.acheteur); a(v.lieu); a(v.annee);
    if (v.montant_ht != null && v.montant_ht !== "") out.push(pvNombre(v.montant_ht) + " € HT");
    if (role[v.role]) out.push(role[v.role]);
  } else if (p.nature === "qualification") {
    a(v.organisme); if (v.numero) out.push("n° " + v.numero); a(v.detail);
  } else if (p.nature === "salarie") {
    if (v.experience_annees != null && v.experience_annees !== "") out.push(v.experience_annees + (Number(v.experience_annees) > 1 ? " ans" : " an") + " d'expérience");
    a(v.diplomes); a(v.qualifications);
  } else if (p.nature === "materiel") {
    if (v.quantite != null && v.quantite !== "") out.push("quantité : " + v.quantite);
    a(v.caracteristiques);
    if (v.possession) out.push(v.possession === "location" ? "en location" : "en propre");
  } else if (p.nature === "chiffre_cle") a(v.annee);
  return out.join(" · ");
}
function pvTexteLong(p) { const v = (p && p.valeur) || {}; return p.nature === "reference" ? (v.description || "") : (p.nature === "salarie" ? (v.chantiers || "") : ""); }
// Validité affichée, sobre : la date, et le nombre de jours restants seulement à l'approche.
function pvValidite(p) {
  if (!p || !p.date_fin_validite) return null;
  const d = _pvJj(p.date_fin_validite), j = p.jours_restants;
  if (p.expiree) return { t: "Fin de validité dépassée (" + d + ")" + (p.statut === "acceptee" ? " : Adjugo ne s'en sert plus" : ""), cls: "pv-ko" };
  if (j != null && j <= PV_ALERTE_JOURS) return { t: "Valable jusqu'au " + d + (j === 0 ? " (dernier jour)" : " (encore " + j + " jour" + (j > 1 ? "s" : "") + ")"), cls: "pv-warn" };
  return { t: "Valable jusqu'au " + d, cls: "" };
}
// Ligne de l'encadré « à mettre à jour » (minuscule initiale : elle suit le nom de la fiche).
function pvEcheance(p) {
  const d = _pvJj(p && p.date_fin_validite), j = p && p.jours_restants;
  if (!d) return "";
  if (p.expiree) return "fin de validité dépassée le " + d;
  return "valable jusqu'au " + d + (j === 0 ? " (dernier jour)" : (j != null ? " (encore " + j + " jour" + (j > 1 ? "s" : "") + ")" : ""));
}
function pvAlertes(list) {
  return (list || []).filter(p => p.statut === "acceptee" && p.date_fin_validite && (p.expiree || (p.jours_restants != null && p.jours_restants <= PV_ALERTE_JOURS)))
    .sort((a, b) => String(a.date_fin_validite).localeCompare(String(b.date_fin_validite)));
}
function pvSrcIcone(p) {
  const s = (p && p.source) || {};
  if (p.type_source === "documents") return s.lien_passage ? "text-quote" : "paperclip";
  return ({ public: "landmark", estimation: "calculator" })[p.type_source] || "pen-line";
}
// Corps envoyé au serveur : champs vides retirés, nombres lus à la française ; le serveur contrôle tout.
function pvCorps(f, avecValidite) {
  const valeur = {};
  (PV_CHAMPS[f.nature] || []).forEach(c => {
    const x = f.v[c.k];
    if (x === "" || x == null) return;
    if (c.t === "num") { const s = String(x).replace(/[\s  ]/g, "").replace(",", "."); const n = Number(s); valeur[c.k] = (s !== "" && isFinite(n)) ? n : String(x); }
    else { const s = String(x).trim(); if (s) valeur[c.k] = s; }
  });
  const body = { valeur, type_source: f.type_source, source: null, date_source: null };
  if (avecValidite) body.date_fin_validite = f.date_fin_validite || null;
  if (f.type_source === "documents") {
    const s = {};
    if (f.doc_id) { s.doc_id = Number(f.doc_id); s.passage = f.passage || ""; }
    if (f.document_id) s.document_id = Number(f.document_id);
    body.source = s; body.date_source = (f.doc_id && f.date_source) || null;
  } else if (f.type_source === "public") {
    body.source = { nom: f.pub.nom, url: f.pub.url, consulte_le: f.pub.consulte_le || null, identifiant: f.pub.identifiant };
  } else if (f.type_source === "estimation") {
    body.source = { project_id: f.est.project_id ? Number(f.est.project_id) : null, detail: f.est.detail };
  }
  return body;
}
// Fiche insérée dans le texte en cours de l'atelier (« J'écris moi-même ») : une ligne vide autour.
function pvInsererTexte(t, pos, bloc) {
  t = String(t || ""); const at = pos == null ? t.length : Math.max(0, Math.min(Number(pos) || 0, t.length));
  const avant = t.slice(0, at).replace(/\s+$/, ""), apres = t.slice(at).replace(/^\s+/, "");
  const ins = (avant ? "\n\n" : "") + bloc + (apres ? "\n\n" : "");
  return { texte: avant + ins + apres, pos: (avant + ins).length };
}
// Vague 5 (E2) : références d'une part, une par ligne, rattachées à leur version complète (sources-publiques.js).
function _spFusionRefs(texte, riches) {
  const SP = (typeof window !== "undefined") && window.AdjugoSourcesPubliques;
  if (SP && SP._pur && SP._pur.spFusionRefs) return SP._pur.spFusionRefs(texte, riches);
  return String(texte || "").split("\n").map(s => s.trim()).filter(Boolean).map(s => ({ intitule: s }));
}
function _spLibRefs(refs) {
  const SP = (typeof window !== "undefined") && window.AdjugoSourcesPubliques;
  return (SP && SP._pur && SP._pur.spLibRefs) ? SP._pur.spLibRefs(refs) : "";
}
// ══════════ fin « Mes preuves » — fonctions pures ══════════

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
// Promesse unique de GET /api/public-config (méthode loadFeatures).
let _publicConfigP = null;
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

// ══════════ Atelier du dossier de présentation (rédaction, vague 2) — fonctions pures ══════════
// Contrat : docs/REDACTION_V2_API.md. Le texte d'une partie est du Markdown simple (titres « ## »,
// listes « - » ou « 1. », tableaux « | »). Rendu SÛR : chaque morceau de texte est échappé ; seuls
// des éléments fixes sont produits (titres, listes, tableaux, gras, faits « à relire » surlignés,
// passages « [À compléter] », renvois [S1] vers les extraits privés de la partie). Jamais de lien,
// d'image ni d'attribut venu du texte.
function _atlInit() {
  return { pid: null, loading: false, error: "", st: null, prop: null, base: "auto", sel: null,
           mode: "lire", edit: { texte: "", base: null, dirty: false, sid: null }, draft: null, conflict: "",
           busy: "", hist: { open: false, loading: false, list: [], sid: null }, vue: null, derog: null, debit: null,
           plan: null, planOpen: false, add: "", ren: { on: false, v: "" }, factFocus: "", srcFocus: "", note: "",
           exportOpen: false, lastDerog: "", live: "", src: null, passage: null,
           onglet: "redaction", rep: _atlRepInit(), ent: _atlEntInit(), sansIaPropose: false, exOpen: false,
           // Vague 6 (H) : case « Joindre une page "Comment ce dossier a été préparé" », DÉCOCHÉE à chaque
           // ouverture de l'atelier (jamais enregistrée) ; `prep` : la page lue avant l'export (lecture seule) ;
           // `prep.lot` : dossier à plusieurs lots, le fichier dont on lit la page (un fichier par lot).
           prepJoindre: false, prep: { open: false, loading: false, d: null, err: "", lot: "", seq: 0 },
           // Plusieurs lots (rédaction, vague 6 — J) : lots cochés et lots indiqués (plan proposé), fenêtre « Changer les
           // lots », filtre du plan (« » toutes, « c » communes, sinon un numéro de lot), lot dont on lit le blocage.
           lotsChoix: [], lotsAjoutes: [], lotAjout: { numero: "", intitule: "" }, lotsDlg: null, lotFiltre: "",
           lotOuvert: "", addLot: "" };
}
// Entretien chantier (rédaction, vague 5 — D) : les questions lues (GET/POST …/entretien), la saisie de chaque
// réponse (par question), l'action en cours. `v` : clé de rendu des menus « Posée à » (remis à la valeur enregistrée).
function _atlEntInit() { return { open: false, loading: false, d: null, err: "", busy: "", edits: {}, v: 0, auto: false }; }
function _atlCardInit() { return { loading: false, loaded: false, d: null, error: "" }; }
// « Qui écrit quoi » (rédaction, vague 4, chef de file) : la répartition lue (GET …/repartition), la partie
// ouverte et son détail (texte envoyé, avant / après), la saisie du chef de file sur la part d'un partenaire,
// le résultat de « Demander les parts ». `v` : clé de rendu des menus (remis à la valeur enregistrée).
function _atlRepInit() {
  return { loading: false, d: null, err: "", busy: "", open: null, det: null, detLoading: false, edit: null,
           demande: null, v: 0 };
}
// Statut d'une partie dans « Qui écrit quoi » → pastille (mêmes couleurs que l'atelier).
function atlRepStatutCls(st) {
  return ({ a_rediger: "neutral", en_cours: "atl-st-brouillon", envoyee: "st-envoye", a_valider: "st-envoye",
            a_revalider: "a_etudier", validee: "go" })[st] || "neutral";
}
// Ce que le chef de file reçoit avec le texte envoyé : des COMPTEURS de sources par type, jamais les sources.
// « 5 faits avec une source : 3 déclarés, 2 trouvés dans ses documents · 1 fait à relire · 1 « [À compléter] » ».
const ATL_REP_TYPES = [["documents", "trouvé dans ses documents", "trouvés dans ses documents"],
  ["declare", "déclaré", "déclarés"], ["public", "de source publique", "de source publique"],
  ["estimation", "selon son estimation", "selon son estimation"],
  ["calcul", "calculé à partir de ses faits", "calculés à partir de ses faits"],
  ["acheteur", "tiré du dossier de l'acheteur", "tirés du dossier de l'acheteur"]];
function atlRepCompteurs(tc) {
  if (!tc) return "";
  const c = tc.compteurs && typeof tc.compteurs === "object" ? tc.compteurs : null, out = [];
  const pl = (n, un, des) => n + " " + (n > 1 ? des : un);
  if (c) {
    const n = Number(c.avec_source) || 0, par = c.par_type || {};
    const det = ATL_REP_TYPES.map(([k, un, des]) => [Number(par[k]) || 0, un, des]).filter(x => x[0] > 0)
      .map(([k, un, des]) => k + " " + (k > 1 ? des : un));
    out.push(n ? pl(n, "fait avec une source", "faits avec une source") + (det.length ? " : " + det.join(", ") : "")
               : "Aucun fait avec une source");
    if (Number(c.a_relire) > 0) out.push(pl(Number(c.a_relire), "fait à relire", "faits à relire"));
    if (Number(c.engagements) > 0) out.push(pl(Number(c.engagements), "engagement à confirmer", "engagements à confirmer"));
  } else if (Number(tc.faits_a_relire) > 0) {
    out.push(pl(Number(tc.faits_a_relire), "fait à relire", "faits à relire"));
  }
  if (Number(tc.a_completer) > 0) out.push(pl(Number(tc.a_completer), "passage « [À compléter] »", "passages « [À compléter] »"));
  return out.join(" · ");
}
// Le texte contient-il des renvois (F1, S2…) ? Ils désignent alors des sources du partenaire.
function atlRepARenvois(md) { return /\[\s*[FSPECGR]\s*\d{1,4}(?:\s*[,;]\s*[FSPECGR]?\s*\d{1,4})*\s*\]/.test(String(md || "")); }
// Partenaires qui recevront « Demander les parts » : une partie à rédiger, en cours ou à revalider.
function atlRepADemander(d) {
  const par = {};
  ((d && d.sections) || []).forEach(l => {
    const r = l.redacteur || {};
    if (r.type !== "partenaire" || !r.invite_id || ["envoyee", "validee"].indexOf(l.statut) >= 0) return;
    (par[r.invite_id] = par[r.invite_id] || { invite_id: r.invite_id, nom: r.nom, parties: 0 }).parties++;
  });
  return Object.keys(par).map(k => par[k]);
}
// Validation du dossier assemblé par chaque membre, en une phrase : « Dossier assemblé validé par X ; à
// revalider par Y ; à valider par vous, Z. »
function atlRepValidationsTexte(pret) {
  const ms = (pret && pret.membres) || [], par = { valide: [], a_revalider: [], a_faire: [] };
  ms.forEach(m => { (par[m.statut] || par.a_faire).push(m.membre === "chef_de_file" ? "vous" : m.nom); });
  const out = [];
  if (par.valide.length) out.push("validé par " + par.valide.join(", "));
  if (par.a_revalider.length) out.push("à revalider par " + par.a_revalider.join(", "));
  if (par.a_faire.length) out.push("à valider par " + par.a_faire.join(", "));
  return out.length ? "Dossier assemblé " + out.join(" ; ") + "." : "";
}
// « Qui fait quoi dans le groupement » (assemblage) : qui l'a validée, en une phrase : « Validée par vous, A ;
// à revalider par B ; à valider par C. » (validée quand chaque membre a validé son texte courant).
function atlRepQfqValidationsTexte(vals) {
  const par = { valide: [], a_revalider: [], a_faire: [] };
  (vals || []).forEach(m => { (par[m.statut] || par.a_faire).push(m.invite_id ? m.nom : "vous"); });
  const out = [];
  if (par.valide.length) out.push("validée par " + par.valide.join(", "));
  if (par.a_revalider.length) out.push("à revalider par " + par.a_revalider.join(", "));
  if (par.a_faire.length) out.push("à valider par " + par.a_faire.join(", "));
  if (!out.length) return "";
  const t = out.join(" ; ");
  return t.charAt(0).toUpperCase() + t.slice(1) + ".";
}
// Résultat de « Demander les parts », en phrases (aucune adresse n'est jamais montrée).
function atlRepDemandeTexte(r) {
  if (!r) return [];
  const noms = (xs) => (xs || []).map(x => x.nom).join(", "), out = [];
  const partis = (r.demandees || []).filter(x => x.email_parti), rates = (r.demandees || []).filter(x => !x.email_parti);
  if (partis.length) out.push("Demande envoyée à " + noms(partis) + ".");
  if (rates.length) out.push("L'email à " + noms(rates) + " n'est pas parti : réessayez dans quelques minutes.");
  const sa = r.sans_adresse || [];
  if (sa.length) out.push("Aucune adresse email sur le lien de " + noms(sa) + (sa.length > 1 ? " : transmettez-leur leur lien" : " : transmettez-lui son lien") + " vous-même, depuis la page du marché.");
  if ((r.deja_demandees || []).length) out.push("Déjà demandée il y a moins de 15 minutes à " + noms(r.deja_demandees) + ".");
  if ((r.plafond_atteint || []).length) out.push("Limite d'envois du jour atteinte : " + noms(r.plafond_atteint) + " recevra la demande si vous réessayez demain.");
  if (!out.length) out.push("Aucune partie à demander : chaque partenaire a envoyé ses parties.");
  return out;
}
// « Pièces du dossier de l'acheteur lues par Adjugo » : ce que la LECTURE a donné pour une pièce
// (lue en entier avec ses pages, lue en partie, non lue) ; la raison s'affiche à côté.
function atlLecturePiece(p) {
  p = p || {};
  const st = p.statut || (p.lu_en_entier === true ? "lu_en_entier" : (p.lu_en_entier === false ? "lu_en_partie" : ""));
  if (st === "lu_en_entier") return "lue en entier" + (p.pages ? " (" + p.pages + " page" + (p.pages > 1 ? "s" : "") + ")" : "");
  if (st === "non_lu") return "non lue";
  if (st === "lu_en_partie") return "lue en partie";
  return "";
}
// Ce qui manque à la lecture du dossier, à dire hors de la liste repliée : ancienne lecture (et
// comment obtenir la lecture intégrale), lecture en cours, ou pièces non lues ou lues en partie.
function atlManqueLecture(da) {
  if (!da || da.present === false) return "";
  if (da.message_lecture) return da.message_lecture;
  const c = da.couverture;
  return (c && c.message && !c.complet) ? c.message : "";
}
const ATL_FAIT_TYPES = { chiffre: "Chiffre", nombre_en_lettres: "Nombre en lettres", certification: "Certification",
  nom_propre: "Nom propre", materiel: "Matériel", engagement: "Engagement" };
const ATL_BASES = [
  { k: "auto", l: "Automatique", d: "Le cadre de réponse imposé s'il existe, sinon les critères retrouvés dans le règlement, sinon un plan simple." },
  { k: "cadre", l: "Le cadre de réponse de l'acheteur", d: "Ses numéros, ses intitulés et son ordre, tels quels.", non: "Aucun cadre de réponse découpé en questions dans le dossier." },
  { k: "grille", l: "Les critères du règlement", d: "Une partie par critère retenu dans « Comment vous serez noté », avec son poids.", non: "Aucun critère retenu dans « Comment vous serez noté »." },
  { k: "libre", l: "Un plan simple", d: "Proposé par Adjugo, sans IA, à adapter au marché." },
];
// Les bases de plan qui existent pour ce marché (le serveur dit lesquelles) : les autres restent
// visibles mais désactivées, avec leur raison.
function atlBasesDispo(bases) {
  const b = bases || {};
  return ATL_BASES.map(x => Object.assign({}, x, { off: (x.k === "cadre" || x.k === "grille") && b[x.k] === false }));
}
// Brouillons locaux de l'atelier (texte d'une partie, qui peut citer des salariés) : effacés à la
// déconnexion, à la suppression du compte, et ignorés puis effacés au-delà de 7 jours.
const ATL_DRAFT_TTL = 7 * 24 * 3600 * 1000;
function atlDraftPerime(d) { return !d || !d.at || !isFinite(Number(d.at)) || (Date.now() - Number(d.at)) > ATL_DRAFT_TTL; }
function atlPurgeDrafts(tous) {
  try {
    const ks = [];
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.indexOf("adjugo_atl_") === 0) ks.push(k); }
    ks.forEach(k => {
      let out = !!tous;
      if (!out) { try { out = atlDraftPerime(JSON.parse(localStorage.getItem(k) || "null")); } catch (e) { out = true; } }
      if (out) localStorage.removeItem(k);
    });
  } catch (e) { /* stockage interdit : rien à effacer */ }
}
// Session ouverte par le lien privé de démonstration (/demo#<clé>) : son jeton porte « dl »
// (empreinte de la clé). Session refusée → retour sur /demo, avec la raison (sessionPerdue).
// Détail exact renvoyé par le serveur quand la clé du lien a changé ou a été retirée
// (app/core/demo_guard.DEMO_LIEN_PERIME) ; tout autre refus = session simplement terminée.
const DEMO_LIEN_PERIME = "Ce lien de démonstration n'est plus valide.";
function jetonDemoLien(t) {
  try {
    let p = String(t || "").split(".")[1];
    if (!p) return false;
    p = p.replace(/-/g, "+").replace(/_/g, "/");
    while (p.length % 4) p += "=";
    const j = JSON.parse(atob(p));
    return !!(j && j.dl);
  } catch (e) { return false; }
}
function _atlReEsc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
function _atlKey(s) { return String(s || "").toLowerCase().replace(/\s+/g, " ").trim(); }
// Motif d'un fait : espaces souples (une espace insécable du texte vaut une espace), bornes de mot
// quand le fait commence ou finit par une lettre ou un chiffre (« 12 » ne marque pas « 2012 »).
function _atlFaitRe(f) {
  const s = String(f || "").trim(); if (!s) return "";
  const core = _atlReEsc(s).replace(/\s+/g, "\\s+");
  return (/^[A-Za-z0-9]/.test(s) ? "\\b" : "") + core + (/[A-Za-z0-9]$/.test(s) ? "\\b" : "");
}
// Un fait « à relire » est repéré UNE fois, dans SA phrase (atlFaitPos), puis entouré de marques
// privées (zone Unicode réservée) que le rendu transforme en <mark> : jamais toutes les occurrences
// de la même valeur (« 12 » dans « Le CCTP prévoit 12 mois » n'est pas un fait sur l'entreprise).
const _ATL_M0 = "\uE000", _ATL_M1 = "\uE001", _ATL_M2 = "\uE002";
function _atlSans(s) { return String(s).replace(/\uE000\d*\uE001?/g, "").replace(/[\uE000-\uE002]/g, ""); }
// Marques d'un morceau de ligne : [À compléter …], renvoi [S1], fait à relire repéré (groupes de `re`).
// `refs` : rendu des renvois (par défaut atlRefsHtml ; atlRefsPartHtml pour la part d'un partenaire).
function _atlMarks(s, re, ids, refs) {
  let out = "", last = 0, m;
  re.lastIndex = 0;
  while ((m = re.exec(s))) {
    if (!m[0]) { re.lastIndex++; continue; }
    out += _escHtml(_atlSans(s.slice(last, m.index)));
    if (m[1]) out += '<span class="atl-todo">' + _escHtml(_atlSans(m[1])) + "</span>";
    else if (m[2]) out += (refs || atlRefsHtml)(m[3]);
    else {
      const id = ids[Number(m[4])] || "";
      out += '<mark class="atl-fait"' + (id ? ' data-fait="' + _escHtml(id) + '"' : "") + ">" + _escHtml(_atlSans(m[5])) + "</mark>";
    }
    last = m.index + m[0].length;
  }
  return out + _escHtml(_atlSans(s.slice(last)));
}
// Renvois d'un bloc « F3, S2 » (le préfixe se reporte : « F3, 4 » = F3 et F4) → étiquettes sûres.
function atlRefs(inner) {
  const out = []; let pref = "";
  String(inner || "").replace(/([FSPECGR])?\s*(\d{1,4})/g, (m0, p, n) => { pref = p || pref; if (pref) out.push(pref + Number(n)); return m0; });
  return out;
}
function atlRefsHtml(inner) {
  return atlRefs(inner).map(r => '<sup class="atl-ref" data-ref="' + _escHtml(r) + '">' + _escHtml(r) + "</sup>").join("");
}
// Renvois d'une part ENVOYÉE par un partenaire (rédaction, vague 4) : ils désignent SES sources, qui restent
// chez lui. Montrés comme « source du partenaire », sans lien ni identifiant cliquable ; retirés à l'export.
function atlRefsPartHtml(inner) {
  return atlRefs(inner).map(r => '<sup class="atl-ref-p" title="Source du partenaire">' + _escHtml(r)
    + '<span class="sr-only"> : source du partenaire</span></sup>').join("");
}
// « Chaque fait a sa source » (vague 3) : libellé court d'une source, jamais « vérifié ».
const ATL_SRC_TYPES = { documents: "trouvé dans vos documents", justificatif: "justificatif déposé", declare: "déclaré par vous",
  public: "source publique", estimation: "votre estimation", partenaire: "déclaré par votre partenaire",
  acheteur: "dans le dossier de l'acheteur", calcul: "calculé à partir de vos faits", vous: "déclaré par vous" };
// Une source publique (DECP, liste RGE) est datée : « marché attribué, source publique DECP, consultée le 19/10/2026 ».
function atlSrcLib(src) {
  const lib = (src && (src.libelle || ATL_SRC_TYPES[src.type])) || "";
  const d = src && src.type === "public" ? _pvJj(src.date) : "";
  return lib && d ? lib + ", consultée le " + d : lib;
}
// Champs proposés pour déclarer un fait (les autres restent dans « Mes preuves »).
const ATL_DECL_CHAMPS = { reference: ["objet", "acheteur", "annee", "montant_ht"], qualification: ["nom", "organisme", "numero"],
  salarie: ["nom", "fonction"], materiel: ["designation", "quantite"], chiffre_cle: ["libelle", "valeur", "unite", "annee"] };
const ATL_DECL_LIB = { objet: "Objet", acheteur: "Acheteur", annee: "Année", montant_ht: "Montant HT (€)", nom: "Nom",
  organisme: "Organisme", numero: "Numéro", fonction: "Fonction", designation: "Désignation", quantite: "Quantité",
  libelle: "Libellé", valeur: "Valeur", unite: "Unité" };
const ATL_NATURES = { reference: "Référence", qualification: "Qualification", salarie: "Équipe", materiel: "Matériel", chiffre_cle: "Chiffre clé" };
// Une ligne : le gras (**…**) d'abord, puis les marques dans chaque morceau (jamais de balise croisée).
function _atlInline(raw, re, idx, refs) {
  const s = String(raw == null ? "" : raw), bold = /\*\*(.+?)\*\*/g;
  let out = "", last = 0, m;
  while ((m = bold.exec(s))) {
    out += _atlMarks(s.slice(last, m.index), re, idx, refs) + "<strong>" + _atlMarks(m[1], re, idx, refs) + "</strong>";
    last = m.index + m[0].length;
  }
  return out + _atlMarks(s.slice(last), re, idx, refs);
}
function _atlCells(line) { return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim()); }
const _atlHtmlCache = new Map();
// `opts.refsPartenaire` : le texte est la part d'un partenaire (ses renvois : « source du partenaire »).
function atlMdToHtml(md, faits, opts) {
  let src = _atlSans(String(md || ""));
  const part = !!(opts && opts.refsPartenaire), refs = part ? atlRefsPartHtml : atlRefsHtml;
  const list = (Array.isArray(faits) ? faits : []).filter(f => f && f.statut !== "relu_par_vous" && String(f.fait || "").trim());
  const ck = (part ? "p" : "o") + "\u0001" + src + "\u0000" + list.map(f => f.id + ":" + f.fait + ":" + (f.phrase || "")).join("|");
  if (_atlHtmlCache.has(ck)) return _atlHtmlCache.get(ck);
  // Chaque fait : SA position (la phrase où le serveur l'a relevé), sans chevauchement.
  const ids = [], spans = [];
  list.slice().sort((a, b) => String(b.fait).length - String(a.fait).length).forEach(f => {
    const p = atlFaitPos(src, f.fait, f.phrase); if (!p) return;
    if (spans.some(x => p[0] < x[1] && x[0] < p[1])) return;
    spans.push([p[0], p[1], ids.length]); ids.push(f.id);
  });
  spans.sort((a, b) => b[0] - a[0]).forEach(x => {
    src = src.slice(0, x[0]) + _ATL_M0 + x[2] + _ATL_M1 + src.slice(x[0], x[1]) + _ATL_M2 + src.slice(x[1]);
  });
  // « [À compléter …] » quelle que soit la casse (« [A COMPLETER …] », « [à Compléter …] ») comme le serveur
  // (far._TODO, re.IGNORECASE), sans rouvrir les renvois aux minuscules (« [f3] » n'est pas un renvoi).
  const re = new RegExp("(\\[\\s*[ÀàAa]\\s+[Cc][Oo][Mm][Pp][Ll][ÉéEe][Tt][Ee][Rr][^\\]]*\\])|(\\[\\s*([FSPECGR]\\s*\\d{1,4}(?:\\s*[,;]\\s*[FSPECGR]?\\s*\\d{1,4})*)\\s*\\])|\\uE000(\\d+)\\uE001([^\\uE002]*)\\uE002", "g");
  const inl = (t) => _atlInline(t, re, ids, refs);
  const out = [];
  let ul = null, ol = null, table = null, para = [];
  const flush = (keep) => {
    if (para.length && keep !== "p") { out.push("<p>" + para.map(inl).join("<br>") + "</p>"); para = []; }
    if (ul && keep !== "ul") { out.push("<ul>" + ul.map(x => "<li>" + inl(x) + "</li>").join("") + "</ul>"); ul = null; }
    if (ol && keep !== "ol") { out.push("<ol>" + ol.map(x => "<li>" + inl(x) + "</li>").join("") + "</ol>"); ol = null; }
    if (table && keep !== "table") {
      const head = table[0] || [], body = table.slice(1);
      out.push('<div class="atl-tw"><table class="atl-table"><thead><tr>' + head.map(c => '<th scope="col">' + inl(c) + "</th>").join("")
        + "</tr></thead><tbody>" + body.map(r => "<tr>" + r.map(c => "<td>" + inl(c) + "</td>").join("") + "</tr>").join("")
        + "</tbody></table></div>");
      table = null;
    }
  };
  src.replace(/\r\n?/g, "\n").split("\n").forEach(raw => {
    const t = raw.trim();
    if (!t) { flush(); return; }
    if (/^```/.test(t)) return;
    let m = t.match(/^(#{1,6})\s+(.+)$/);
    if (m) { flush(); const lv = Math.min(6, m[1].length + 3); out.push("<h" + lv + ' class="atl-h">' + inl(m[2]) + "</h" + lv + ">"); return; }
    m = t.match(/^[-*+•]\s+(.+)$/);
    if (m) { flush("ul"); (ul = ul || []).push(m[1]); return; }
    m = t.match(/^\d{1,2}[.)]\s+(.+)$/);
    if (m) { flush("ol"); (ol = ol || []).push(m[1]); return; }
    if (/^\|.*\|?$/.test(t) && t.indexOf("|", 1) > 0) {
      flush("table");
      if (!/^\|?[\s:|-]+\|?$/.test(t)) (table = table || []).push(_atlCells(t));
      return;
    }
    flush("p"); para.push(t);
  });
  flush();
  const html = out.join("");
  if (_atlHtmlCache.size > 40) _atlHtmlCache.clear();
  _atlHtmlCache.set(ck, html);
  return html;
}
// Phrase d'un fait, le fait surligné (première occurrence) : HTML sûr.
function atlPhraseHtml(phrase, fait) {
  const p = String(phrase || ""), f = String(fait || "").trim();
  const r = f ? _atlFaitRe(f) : "";
  const m = r ? new RegExp(r, "i").exec(p) : null;
  if (!m) return _escHtml(p);
  return _escHtml(p.slice(0, m.index)) + '<mark class="atl-fait">' + _escHtml(m[0]) + "</mark>" + _escHtml(p.slice(m.index + m[0].length));
}
// Limite comparée au texte : « rouge » dépassée, « orange » à moins de 10 %, « vert » sinon, "" sans mesure.
function atlLimNiveau(l) {
  if (!l) return "";
  if (l.depassee) return "rouge";
  const m = Number(l.mesure), v = Number(l.valeur);
  if (l.mesure == null || !isFinite(m) || !isFinite(v) || v <= 0) return "";
  return m / v >= 0.9 ? "orange" : "vert";
}
// Nombre de mots (approché, comme le serveur) d'un texte Markdown, sans renvois ni syntaxe.
function atlMots(md) {
  const t = String(md || "").replace(/\[\s*[FSPECGR]\s*\d{1,4}(?:\s*[,;]\s*[FSPECGR]?\s*\d{1,4})*\s*\]/g, " ").replace(/\[\s*CV\s+F\s*\d{1,4}\s*\]/gi, " ").replace(/^\s*(#{1,6}|[-*+•]|\d{1,2}[.)])\s+/gm, " ").replace(/[|*_`]/g, " ");
  const m = t.match(/[0-9A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:['’-][0-9A-Za-zÀ-ÖØ-öø-ÿŒœ]+)*/g);
  return m ? m.length : 0;
}
// « M. », « Mme. », « Dr. » ou une initiale ne finissent pas une phrase (comme côté serveur).
function _atlAbrev(t, i) { return /(?:^|[\s(«"'])(?:M|MM|Mme|Mmes|Mlle|Me|Dr|Pr|Mgr|[A-ZÀ-Ý])\.$/.test(t.slice(Math.max(0, i - 5), i + 1)); }
// Bornes de la phrase qui contient [a, b) dans le texte : jusqu'à la ponctuation forte, sans
// sortir de la ligne ; dans un tableau, la cellule.
function _atlSentence(t, a, b) {
  const ls = t.lastIndexOf("\n", a - 1) + 1;
  let le = t.indexOf("\n", b); if (le < 0) le = t.length;
  if (/^\s*\|/.test(t.slice(ls, le))) {
    const cs = t.lastIndexOf("|", a - 1) + 1, ce = t.indexOf("|", b);
    return [Math.max(ls, cs), ce < 0 || ce > le ? le : ce, true];
  }
  let s = ls, e = le;
  for (let i = a - 1; i >= ls; i--) { if (/[.!?;]/.test(t[i]) && /\s/.test(t[i + 1] || "") && !(t[i] === "." && _atlAbrev(t, i))) { s = i + 1; break; } }
  for (let i = b; i < le; i++) { if (/[.!?]/.test(t[i]) && (i + 1 === le || /\s/.test(t[i + 1])) && !(t[i] === "." && _atlAbrev(t, i))) { e = i + 1; break; } }
  while (s < e && /\s/.test(t[s])) s++;
  return [s, e, false];
}
// Ligne de tableau telle que le serveur la contrôle : ses cases jointes par « ; ».
function _atlRow(t, a) {
  const ls = t.lastIndexOf("\n", a - 1) + 1;
  let le = t.indexOf("\n", a); if (le < 0) le = t.length;
  return t.slice(ls, le).trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim()).filter(Boolean).join(" ; ");
}
// Position du fait dans le texte : l'occurrence dont la phrase (ou la ligne de tableau) est celle
// où le serveur l'a relevé ; à défaut, la première.
function atlFaitPos(texte, fait, phrase) {
  const t = String(texte || ""), r = _atlFaitRe(fait); if (!r) return null;
  const re = new RegExp(r, "gi"), hint = _atlKey(phrase).replace(/[*_`#|]/g, "").slice(0, 24);
  let best = null, m;
  while ((m = re.exec(t))) {
    const pos = [m.index, m.index + m[0].length];
    if (!best) best = pos;
    const sr = _atlSentence(t, pos[0], pos[1]);
    const where = sr[2] ? _atlRow(t, pos[0]) : t.slice(sr[0], sr[1]);
    if (hint && _atlKey(where.replace(/[*_`#|]/g, "")).indexOf(hint) >= 0) return pos;
  }
  return best;
}
// « Retirer » : le texte sans la phrase qui porte le fait (null si le fait n'est plus dans le texte).
// Une puce ou un paragraphe réduit à cette phrase disparaît ; une cellule de tableau est vidée.
function atlRetirerPhrase(texte, fait, phrase) {
  const t = String(texte || ""), pos = atlFaitPos(t, fait, phrase); if (!pos) return null;
  const [s, e, cell] = _atlSentence(t, pos[0], pos[1]);
  if (cell) return t.slice(0, s) + " " + t.slice(e);
  const ls = t.lastIndexOf("\n", s - 1) + 1;
  let le = t.indexOf("\n", e); if (le < 0) le = t.length;
  if (/^\s*(?:[-*+•]|\d{1,2}[.)]|#{1,6})?\s*$/.test(t.slice(ls, s)) && !t.slice(e, le).trim()) {
    return (t.slice(0, ls) + t.slice(le < t.length ? le + 1 : le)).replace(/\n{3,}/g, "\n\n").replace(/^\s*\n/, "");
  }
  const avant = t.slice(0, s).replace(/[ \t]+$/, ""), apres = t.slice(e).replace(/^[ \t]+/, "");
  const sep = avant && !/\n$/.test(avant) && apres && !/^\n/.test(apres) ? " " : "";
  return avant + sep + apres;
}
// Nom du fichier exporté (en-tête Content-Disposition : « filename* » UTF-8 d'abord).
function atlNomFichier(cd, repli) {
  const s = String(cd || "");
  let m = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(s);
  if (m) { try { return decodeURIComponent(m[1].trim()); } catch (e) { /* repli */ } }
  m = /filename\s*=\s*"?([^";]+)"?/i.exec(s);
  return (m && m[1].trim()) || repli || "document";
}

const __adjApp = createApp({
  data() {
    return {
      token: localStorage.getItem("adjugo_token") || "",
      theme: localStorage.getItem("adjugo_theme") || "system",
      mobileNav: false,
      user: {}, company: {}, criteria: {}, googleEnabled: false,
      idleLimitMs: 60 * 60 * 1000,   // déconnexion auto après 1 h SANS activité (sécurité appareil partagé/perdu)
      view: "dashboard", busy: false, toast: null, pending: 0, llmInfo: null,
      // Menu par rubriques (réorganisation, vague 1, 1.3) : groupe « Réglages » replié par défaut, état gardé ;
      // onglet interne de Trouver des marchés ; note « Ce qui a changé » (1.8), état gardé dans ce navigateur.
      navReglages: (function(){ try { return localStorage.getItem("adjugo_nav_reglages") === "1"; } catch(e){ return false; } })(),
      trouverOnglet: "publies",
      mmFiltre: "tous",        // Mes marchés (vague 2a, A2) : tous | pilote | partenaire | plusieurs
      reorgEtat: (function(){ try { return JSON.parse(localStorage.getItem("adjugo_reorg_v1") || "{}") || {}; } catch(e){ return {}; } })(),
      auth: { mode: "login", email: "", password: "", full_name: "", company_name: "", resetToken: "", sent: false },
      stats: {}, projects: [], cotraitants: [], contacts: [], invoices: [], documents: [], docQuery: "", docSort: "recent", expiring: [],
      categoriesDoc: CATEGORIES_DOC, docBusy: null,   // Mes documents : catégorie et date de fin modifiables (vague 2a, A3)
      notifs: [], notifsOpen: false, notifsOnglet: "a_faire", notifsSeen: (function(){ try { return localStorage.getItem("adjugo_notifs_seen") || ""; } catch(e){ return ""; } })(),
      consortiums: { consortiums: [], active: 0, partners_total: 0, submitted_total: 0 },
      grpDash: null,   // tableau de bord « Répondre à plusieurs » (vague 4) : GET /api/groupement/tableau-de-bord
      grpDashErr: "",  // échec du chargement : jamais l'état vide « Aucun groupement » à la place
      cdetail: {}, copen: {}, cexport: {}, cexportWarn: {}, cpreview: {}, cerror: {},
      shared: [],
      sharedAo: _sharedInit(),
      atl: _atlInit(),        // atelier du dossier de présentation (rédaction, vague 2)
      atlJobs: {},            // rédactions en cours (tâches de fond), suivies toutes les 2 s, toutes pages confondues
      atlEchecs: {},          // « marché:partie » → message d'échec de la dernière rédaction, gardé jusqu'à la prochaine action
      atlMobile: false,       // écran étroit : lire et valider seulement
      pieceTypes: [{ k: "kbis", l: "Kbis" }, { k: "fiscale", l: "Attestation fiscale" }, { k: "sociale", l: "Attestation sociale (URSSAF)" }, { k: "assurance", l: "Assurance" }, { k: "rib", l: "RIB" }, { k: "qualification", l: "Qualification" }, { k: "dpgf_lot", l: "Tableau de prix de votre partie (prix de vente)" }, { k: "autre", l: "Autre" }],
      veille: { q: "", loc: "", results: [], loading: false },
      drawer: null, modal: null, cdlg: null,   // cdlg : confirmation d'une action de la convention
      reseau: _reseauInit(),                  // vue « Réseau » (vague 3)
      rinv: null,                             // modale d'invitation en 1 clic (partenaire du réseau ou entreprise SIRENE)
      offre402: null, essaiAlerteOff: false,   // invitation à choisir un forfait (refus 402, limite d'usage de l'essai)
      reseauSuggest: null, reseauSuggestOff: false,   // suggestion « publiez votre profil » (après inscription / acceptation)
      welcome: { siret: "", busy: false, dismissed: false },   // activation par SIRET (1er lancement)
      ag: { query: "réhabilitation groupe scolaire", running: false, log: [], gonogo: null, coverage: null, lots: [], dossier: null },
      agState: {}, agStep: {},
      // Un seul axe d'étapes (vague 2a, décision 7) : AXE_ETAPES, en tête de ce fichier.
      statuses2: AXE_ETAPES.map(e => e.k),
      plan: { plan: "starter" }, org: { data: null, name: "", invite: { email: "", full_name: "" }, lastTemp: null },
      pwd: { current: "", next: "" },
      fb: { open: false, message: "", kind: "idee", busy: false },
      admin: { diag: null, backups: [], busy: false,
               // Profils du réseau à valider (identité) : liste, motif de refus et « remplacer » par demande.
               rv: { list: [], loaded: false, loading: false, error: "", busy: "", explication: "", motif: {}, remplacer: {}, refuser: {} },
               ia: { data: null, loading: false, error: "" },
               // Mesure d'usage (réorganisation, vague 1, 1.1) : ouvertures par écran, 30 derniers jours.
               mesure: { data: null, loading: false, error: "" } },
      cookiesOk: (function(){ try { return localStorage.getItem("adjugo_cookies_ok") === "1"; } catch(e){ return true; } })(),
      // « À vérifier vous-même » (vague 2a, A2) : ce qu'Adjugo ne peut pas vérifier. Les pièces manquantes et le dépôt
      // sont dans la liste « Prêt à déposer » elle-même (contrôles du serveur, « Marquer déposé »).
      predepot: [false, false],
      predepotSteps: [
        "Relisez chaque formulaire officiel. <b>Signez-le si le règlement l'exige</b> ; sinon, la signature vient à l'attribution.",
        "Vérifiez le <b>taux de TVA</b> et les montants de l'acte d'engagement (ATTRI1)."
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
      amont: { signals: [], uploading: false, scanning: false, regions: [], domaines: [], auto: false, autoPause: "", pasteOpen: false, pasteText: "", pasting: false },
      // Fonctions activées par le serveur (GET /api/public-config). « Projets à venir » : masqué tant
      // que PROJETS_A_VENIR=0 (refonte de l'étude veille, vague 1) — faux par défaut, même si l'appel échoue.
      features: { projets_a_venir: false },
      amontDomaines: ["bâtiment", "voirie / VRD", "réseaux", "énergie / rénovation énergétique", "espaces verts / aménagement", "numérique / télécom", "équipement", "études / maîtrise d'œuvre"],
      pv: _pvInit(), pvAtl: _pvAtlInit(),   // « Mes preuves » (rédaction, vague 3, E1)
      kb: { docs: [], totalChunks: 0, uploading: false, kind: "memoire", text: "", textName: "", busyText: false,
            searchQ: "", searchRes: null, searching: false, qText: "", qResults: null, qLoading: false,
            // Fiches proposées à partir d'un document (rédaction, vague 3, chantier I).
            fx: { open: null, data: null, busy: false, date: "", etat: {}, plafond: null, poll: 0, coche: null, contexte: {} } },
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
        query: "", dept: "", country: "FR", advOpen: false, type_marche: "", cpv: "", searching: false, tenders: [], errors: [], sources: [], nonConsultees: [], expanded: null,
        offset: 0, hasMore: false, loadingMore: false,
        analyzing: false, analysis: null, projectId: null, chosen: null, lectureMsg: "",
        alerts: [],
        renewals: { list: [], loading: false, done: false, prep: "" },
        searched: false, empty: null, prefilled: false,
        marketEst: null, marketEstBusy: false,
      },
      ao: { project: null, dossier: null, generating: false, uploading: false, back: "dashboard",
            cotraitants: [], st: { trade: "", dept: "", loading: false, results: [] },
            documents: [], checklist: null, buyer: null, buyerLoading: false, group: null,
            chkHelp: null, grp: _grpInit(), conv: _convInit(), pm: _pmInit(), depot: _depotInit(),
            qa: [], qaInput: "", qaLoading: false, grilleBusy: "", atl: _atlCardInit(), lectureMsg: "", lectureBusy: false, lecturePid: null,
            estimate: null, estimateOpen: false, estimateBusy: false, estimating: false, estimateDistance: 0, reviewNote: "",
            share: { busy: false, invites: [], auditOpen: false, audit: [], contributions: [], contribOpen: false, consortium: null, cockpitOpen: false, freezing: false } },
      // Nom de chaque vue (en-tête des vues hors onglets, relevé de la mesure). Réorganisation, vague 1 (1.3) : les noms
      // de l'architecture C corrigée ; une vue rangée en onglet affiche en tête le nom de sa rubrique (enteteTitre).
      titles: { preuves: "Mes preuves", atelier: "Dossier de présentation", kb: "Mon savoir-faire", amont: "Projets à venir", dashboard: "Accueil", sourcing: "Trouver des marchés", pipeline: "Mes marchés", veille: "Trouver des marchés", cotraitants: "Mes partenaires", contacts: "Contacts", documents: "Mes pièces", invoices: "Devis et factures", bilan: "Bilan", company: "Identité", criteria: "Ce que je cherche", tarifs: "Tarifs", team: "Collègues", billing: "Abonnement", compte: "Mon compte", aodetail: "Le marché", consortiums: "À plusieurs", shared: "Où je suis partenaire", sharedao: "Dossier partagé", admin: "Administration", reseau: "Réseau Adjugo" },
      // Ce que fait chaque vue, en une phrase, dans la bulle (i) de l'en-tête (1.7) : plus de sous-titre affiché, plus de
      // promesse (« Débloquez toute la puissance… »). Une vue sans phrase utile n'a pas de bulle. Clés : la vue, ou
      // l'onglet interne de Trouver des marchés (avenir, alertes).
      subtitles: { preuves: "Les faits de votre entreprise, chacun avec l'endroit où il a été trouvé", atelier: "Rédigez, relisez et validez chaque partie, puis exportez", kb: "Déposez vos documents : l'IA s'en sert pour rédiger vos dossiers de présentation et vos réponses", amont: "Détectez les projets des collectivités, des mois avant l'appel d'offres", sourcing: "Les marchés publiés sur les sources officielles : chaque résultat renvoie à son annonce.", avenir: "Contrats déjà attribués dont la fin estimée approche : un nouveau marché peut suivre.", alertes: "Recevez par email les nouveaux marchés d'une recherche enregistrée.", pipeline: "Suivez vos marchés étape par étape", cotraitants: "Vos partenaires pour répondre en groupement", contacts: "Clients, partenaires, fournisseurs", documents: "Vos pièces administratives centralisées", invoices: "Facturation liée à vos marchés", bilan: "Où vous gagnez et où vous perdez, d'après les marchés terminés, et ce que vos notes vous apprennent", company: "Informations utilisées dans vos candidatures", criteria: "Vos métiers, votre zone et vos montants : ce qu'Adjugo cherche pour vous", tarifs: "Vos prix de journée et vos frais de déplacement, pour estimer vos prix", team: "Invitez vos collègues à collaborer sur vos dossiers", compte: "Votre mot de passe, l'export de vos données et la suppression de votre compte", consortiums: "Vos groupements en cours et leur dossier commun", shared: "Les marchés où d'autres entreprises vous ont invité", sharedao: "Votre part dans le groupement", reseau: "Trouvez des partenaires et faites-vous trouver" },
    };
  },
  computed: {
    initials() { return (this.user.full_name || "U").split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase(); },
    filteredDocuments() {
      // Coffre-fort : recherche (nom/catégorie/dossier/marché lié) + tri. 100% côté client
      // (tous les documents sont déjà chargés), donc instantané et sans appel réseau.
      let list = (this.documents || []).slice();
      const q = (this.docQuery || "").trim().toLowerCase();
      if (q) list = list.filter(d => ((d.name || "") + " " + (d.folder || "") + " " + this.folderLabel(d.folder) + " " + categorieDoc(d.category) + " " + (d.project_name || "")).toLowerCase().includes(q));
      const by = {
        recent: (a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")),
        name: (a, b) => String(a.name || "").localeCompare(String(b.name || ""), "fr", { sensitivity: "base" }),
        category: (a, b) => categorieDoc(a.category).localeCompare(categorieDoc(b.category), "fr", { sensitivity: "base" }),
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
    quotaReached() { const u = this.stats.usage; return !!u && (u.analyses_remaining <= 0 || u.trial_usage === "atteint"); },
    // Carte « essai gratuit » en haut de l'écran : refus 402 (choisir un forfait), limite d'usage de
    // l'essai atteinte ou proche, dernières analyses de l'essai, essai terminé. Jamais de montant.
    essaiCarte() {
      if (this.view === "billing") return null;
      const info = "L'essai gratuit comprend 30 analyses sur toute sa durée (et non par mois) et jusqu'à 15 questions par jour sur vos dossiers. Une limite d'usage de l'IA protège le service pendant l'essai : une opération déjà lancée va toujours au bout. Avec un forfait Pro ou Business, cette limite ne s'applique pas.";
      const u = this.stats && this.stats.usage;
      // IA en pause : « essai » (essai terminé sans forfait) ou « forfait » (compte déjà passé par le
      // paiement, dont le forfait n'est plus actif) : à celui-là, on ne parle pas d'un essai.
      const pause = this.iaPause();
      const motif = (this.offre402 && this.offre402.code === "essai_termine" && this.offre402.motif) || pause;
      const infoFin = motif === "forfait"
        ? "Aucun forfait n'est actif sur votre compte. Les fonctions d'IA (analyses, questions sur vos dossiers, rédaction, chiffrage, veille) reprennent dès que vous choisissez un forfait Pro ou Business. Un traitement déjà lancé va toujours au bout."
        : "Votre essai gratuit de 30 jours est terminé. Les fonctions d'IA (analyses, questions sur vos dossiers, rédaction, chiffrage, veille) reprennent dès que vous choisissez un forfait Pro ou Business. Un traitement lancé pendant l'essai va toujours au bout.";
      if (this.offre402) return { titre: "Choisissez un forfait pour continuer", message: this.offre402.message, info: (pause || this.offre402.code === "essai_termine") ? infoFin : info, ferme: true };
      if (pause) return this.essaiAlerteOff ? null : { titre: pause === "forfait" ? "Aucun forfait actif" : "Votre essai gratuit est terminé", message: "Les fonctions d'IA sont en pause. Choisissez un forfait pour continuer : vos marchés, documents et dossiers restent accessibles.", info: infoFin, ferme: true };
      if (!u || u.quota_scope !== "essai") return null;
      if (u.trial_usage === "atteint") return { titre: "Votre essai a atteint sa limite d'usage", message: "Les fonctions d'IA sont en pause. Choisissez un forfait pour continuer : vos marchés, documents et dossiers restent accessibles.", info: info, ferme: false };
      if (this.essaiAlerteOff) return null;
      if (u.trial_usage === "proche") return { titre: "Votre essai approche de sa limite d'usage", message: "Pour continuer sans interruption, choisissez un forfait.", info: info, ferme: true };
      if (u.analyses_remaining > 0 && u.analyses_remaining <= 3) return { titre: "Plus que " + u.analyses_remaining + " analyse" + (u.analyses_remaining > 1 ? "s" : "") + " dans votre essai", message: "Votre essai gratuit comprend " + u.analyses_limit + " analyses au total. Choisissez un forfait pour continuer ensuite.", info: info, ferme: true };
      return null;
    },
    notifUnseen() { return this.notifs.filter(n => n.at && n.at > this.notifsSeen).length; },
    // Boucle gagné/perdu : synthèse en langage clair de ce que les marchés terminés apprennent.
    // Prudent : on ne conclut que sur des échantillons suffisants (jamais sur 1 marché).
    winInsights() {
      const s = this.stats && this.stats.segments; if (!s || (this.stats.decided || 0) < 3) return [];
      const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const out = [];
      const _bad = (k) => { const v = String(k || "").trim().toLowerCase(); return !v || v === "inconnu" || v === "non précisé" || v === "n/d"; };
      const best = (arr, min = 2) => (arr || []).filter(x => (x.total || 0) >= min && !_bad(x.key)).sort((a, b) => b.win_rate - a.win_rate)[0];
      // Décision 8 : « N gagnés sur M » (le taux ne sert qu'à choisir la leçon, jamais affiché).
      const sur = (x) => x.won + " " + (x.won > 1 ? "gagnés" : "gagné") + " sur " + x.total;
      const bz = best(s.by_zone);
      if (bz && bz.win_rate >= 50) out.push(`Vous gagnez surtout dans le <b>département ${esc(bz.key)}</b> (${sur(bz)}) — ciblez-y vos recherches.`);
      const bt = best(s.by_type);
      if (bt && bt.win_rate >= 50) out.push(`Vos meilleurs résultats : les marchés de <b>${esc(bt.key)}</b> (${sur(bt)}).`);
      const grp = (s.by_groupement || []).reduce((m, g) => { m[g.key] = g; return m; }, {});
      if (grp.Groupement && grp.Solo && (grp.Groupement.total || 0) >= 2 && (grp.Solo.total || 0) >= 2 && grp.Groupement.win_rate > grp.Solo.win_rate + 10) {
        out.push(`Vous gagnez plus <b>à plusieurs</b> (${sur(grp.Groupement)}) que seul (${sur(grp.Solo)}) — associez-vous plus souvent.`);
      }
      const bp = (s.by_partner || []).filter(p => (p.total || 0) >= 2).sort((a, b) => b.win_rate - a.win_rate)[0];
      if (bp && bp.win_rate >= 60) out.push(`Votre partenaire le plus gagnant : <b>${esc(bp.key)}</b> (${sur(bp)}).`);
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
        { k: "profil", done: profil, label: "Renseignez le nom et le SIRET de votre entreprise", view: "company", cta: "Compléter" },
        { k: "criteres", done: criteres, label: "Dites ce que vous cherchez : vos métiers ou votre zone", view: "criteria", cta: "Renseigner" },
        { k: "premier", done: premier, label: "Lancez votre première recherche de marchés", view: "sourcing", cta: "Rechercher" },
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
    // Une adresse par écran (vague 2a, A1) : le chemin de l'écran ouvert (null : pas d'adresse, rien ne change).
    adresseCourante() {
      return adresseDe({ view: this.view, sous: this.trouverOnglet, projet: this.ao.project && this.ao.project.id,
                         partage: this.sharedAo.projectId, cle: this.sharedAo.cle, reseau: this.reseau.tab, filtre: this.mmFiltre });
    },
  },
  watch: {
    // Chaque changement d'écran devient une entrée de l'historique du navigateur (précédent / suivant), sauf quand
    // l'écran suit déjà l'adresse (démarrage, retour arrière) : l'adresse est alors seulement corrigée.
    adresseCourante(adr) { this._adresseSynchro(adr); },
  },
  mounted() {
    this.applyTheme();
    // Atelier : sur un écran étroit (téléphone), on lit et on valide seulement.
    if (window.matchMedia) {
      const mq = window.matchMedia("(max-width:640px)"), upd = () => { this.atlMobile = mq.matches; };
      upd(); if (mq.addEventListener) mq.addEventListener("change", upd); else if (mq.addListener) mq.addListener(upd);
    }
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
    // Une adresse par écran (vague 2a, A1) : précédent / suivant du navigateur rouvrent l'écran de l'adresse ; une
    // fenêtre ouverte est fermée d'abord (relecture : _surRetourNavigateur).
    window.addEventListener("popstate", (ev) => this._surRetourNavigateur(ev));
    const _rst = new URLSearchParams(location.search).get("reset");
    // Cliquer le lien de réinitialisation est une action EXPLICITE : il prime sur une session
    // déjà ouverte. Sinon, un utilisateur connecté qui clique le lic reçu par email atterrissait
    // dans l'app sans jamais voir le formulaire « Nouveau mot de passe » (le clic semblait inerte).
    if (_rst) { this.auth.mode = "reset"; this.auth.resetToken = _rst; this.token = ""; }
    // Réorganisation, vague 1 (1.2) : /app?inscription (boutons d'essai de la vitrine et de l'espace partenaire)
    // ouvre « Créons votre compte ». Le paramètre est retiré tout de suite ; le formulaire est choisi plus bas,
    // une fois la session stockée relue (une session périmée est effacée : on s'inscrit alors aussi).
    const _ins = inscriptionDemandee(location);
    if (_ins.adresse !== null) { try { history.replaceState({}, "", _ins.adresse); } catch (e) {} }
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
    setInterval(() => { if (this.token && _idleStale()) { this.notify("Déconnecté par sécurité après une période d'inactivité.", "err"); this.sessionPerdue(); } }, 60000);
    // Session STOCKÉE (pas une connexion fraîche) trop ancienne → on l'efface, retour à l'écran de connexion
    // (session du lien privé de démonstration : retour sur /demo, qui invite à rouvrir le lien).
    if (this.token && !_freshLogin && _idleStale() && jetonDemoLien(this.token)) { this.sessionPerdue(); return; }
    if (this.token && !_freshLogin && _idleStale()) { localStorage.removeItem("adjugo_token"); this.token = ""; atlPurgeDrafts(true); }
    else atlPurgeDrafts(false);      // brouillons locaux de plus de 7 jours : effacés
    if (_ins.inscrire && !this.token && !_rst) this.auth.mode = "register";   // déjà connecté : rien ne change

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
        // Une fenêtre de confirmation sans champ est un « alertdialog » (fenetre-confirmation) : on ne l'écrase pas.
        document.querySelectorAll(".modal,.drawer").forEach((m) => { if (m.getAttribute("role") !== "alertdialog") m.setAttribute("role", "dialog"); m.setAttribute("aria-modal", "true"); });
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
    async api(method, path, body, isForm, extraHeaders) {
      this.pending++;   // → barre de progression globale (retour visuel sur TOUTE action réseau)
      try {
      const opt = { method, headers: Object.assign({}, extraHeaders || {}) };
      if (this.token) opt.headers["Authorization"] = "Bearer " + this.token;
      if (body && !isForm) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
      if (isForm) opt.body = body;
      const r = await fetch(path, opt);
      if (r.status === 401) { this.sessionPerdue(await r.json().then(j => j && j.detail, () => "")); throw new Error("Session expirée"); }
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
        if (r.status === 402) this.offre402 = { message: msg, code: (d && typeof d === "object" && !Array.isArray(d) && d.code) || "", motif: (d && typeof d === "object" && !Array.isArray(d) && d.motif) || "" };   // « Choisir un forfait » proposé en haut de l'écran
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
    googleLogin() {
      // L'écran demandé (lien vers un marché, favori…) est gardé le temps de l'aller-retour chez Google : le retour
      // arrive sur /app#gcode=… (vague 2a, A1). Seul un chemin de l'application est gardé (etatDeAdresse).
      try { const e = etatDeAdresse(location.pathname); if (e && !e.inconnue && e.view !== "dashboard") sessionStorage.setItem("adjugo_adresse", location.pathname); } catch (e) {}
      window.location.href = "/api/auth/google/login";
    },
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
    logout() { localStorage.removeItem("adjugo_token"); localStorage.removeItem("adjugo_active"); atlPurgeDrafts(true); window.location.href = "/"; },
    // Session refusée par le serveur (401), ou fermée après une heure sans activité : même nettoyage
    // que la déconnexion. Une session du lien privé de démonstration revient sur /demo avec la raison :
    // « perime » si le serveur dit que le lien a changé, sinon « terminee » (12 h écoulées, inactivité) :
    // /demo invite alors à rouvrir le lien reçu, au lieu de le dire « plus valide ».
    sessionPerdue(detail) {
      if (!jetonDemoLien(this.token)) { this.logout(); return; }
      try { sessionStorage.setItem("adjugo_demo_fin", detail === DEMO_LIEN_PERIME ? "perime" : "terminee"); } catch (e) {}
      localStorage.removeItem("adjugo_token"); localStorage.removeItem("adjugo_active"); atlPurgeDrafts(true); window.location.href = "/demo";
    },
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
      const v = await this.demander({ title: "Supprimer définitivement votre compte ?", danger: true, ok: "Supprimer définitivement",
        lines: ["Votre compte et toutes vos données sont effacés : marchés, documents, partenaires, devis et factures.",
                { t: "Cette suppression ne s'annule pas.", warn: true }],
        fields: [{ key: "pw", label: "Votre mot de passe", type: "password", autocomplete: "current-password", requis: true },
                 { key: "cf", label: "Tapez SUPPRIMER pour confirmer", attendu: "SUPPRIMER", autocomplete: "off", max: 20 }] });
      if (!v) return;
      const pw = v.pw;
      try {
        await this.api("POST", "/api/rgpd/delete-account", { password: pw, confirm: "SUPPRIMER" });
        localStorage.removeItem("adjugo_token"); atlPurgeDrafts(true); this.notify("Compte supprimé"); setTimeout(() => window.location.href = "/", 1200);
      } catch (e) { this.notify(e.message, "err"); }
    },
    acceptCookies() { try { localStorage.setItem("adjugo_cookies_ok", "1"); } catch (e) {} this.cookiesOk = true; },
    // Config publique, lue UNE fois (analytics + fonctions activées) ; partagée par loadAmont.
    loadFeatures() {
      if (!_publicConfigP) {
        _publicConfigP = this.api("GET", "/api/public-config").then(c => {
          this.features.projets_a_venir = !!(c && c.projets_a_venir);
          return c;
        }).catch(() => null);
      }
      return _publicConfigP;
    },
    async _loadAnalytics() {
      // Analytics produit cookieless (ex. Plausible), activé par variable d'env serveur.
      try {
        const cfg = await this.loadFeatures();
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
      // Une adresse par écran (vague 2a, A1) : l'écran que demande l'adresse (lien, favori, rechargement, ou
      // l'adresse gardée avant la connexion Google) ; un lien d'invitation « ouvert dans mon Adjugo » (?shared=…)
      // ouvre son dossier ; sinon l'accueil. Le jeton d'invitation ne reste jamais dans l'adresse.
      this.loadExpiring();      // « À faire » (cloche, accueil) : les pièces à renouveler, quel que soit l'écran
      let _demande = etatDeAdresse(this._adresseDemandee());
      try {
        const st = new URLSearchParams(location.search).get("shared");
        if (st) {
          history.replaceState(history.state, "", "/app");
          const it = this.shared.find(s => s.token === st);
          _demande = it ? { view: "sharedao", partage: it.project_id, cle: clePartage(it.token) } : { view: "pipeline", filtre: "partenaire" };
        }
      } catch (e) {}
      this._adresseActive = true;
      try { history.replaceState(Object.assign({}, history.state || {}, { adjugo: 1, n: (history.state && history.state.n) || 0 }), ""); } catch (e) {}
      this._ouvrirAdresse(_demande);
      try {   // posée par invite.html juste avant la redirection « Accepter depuis mon compte »
        const raw = sessionStorage.getItem("adjugo_suggest_profile");
        if (raw) { sessionStorage.removeItem("adjugo_suggest_profile"); this._rnSuggest(JSON.parse(raw)); }
      } catch (e) {}
      this.rnLoadRecues(true);   // pastille « Invitations reçues » du menu Réseau
    },

    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES en tête du fichier) ══════════
    // Rubrique de l'écran ouvert : toujours surlignée dans le menu, pages de détail comprises (le marché, l'atelier,
    // un dossier partagé sont dans « Mes marchés »).
    rubrique() { const r = rubriqueDe(this.view); return r ? r.k : ""; },
    _ongletPermis(t) { return !t.si || (t.si === "admin" ? !!(this.user && this.user.is_admin) : !!this.features[t.si]); },
    // Onglets de la rubrique, affichés seulement sur une vue qui est l'un d'eux (jamais sur une page de détail), et
    // seulement s'il y en a au moins deux. « Réglages » est un groupe du menu, sans onglets.
    ongletsVisibles() {
      const r = rubriqueDe(this.view); if (!r || r.groupe) return [];
      const tabs = r.onglets.filter(t => this._ongletPermis(t));
      return tabs.length > 1 && tabs.some(t => t.view === this.view) ? tabs : [];
    },
    ongletActif(t) { return this.view === t.view && (!t.sous || this.trouverOnglet === t.sous); },
    // Ouvre un onglet : la vue par go(), sans changement ; un onglet interne (Trouver des marchés) est compté à part
    // par la mesure d'usage (« avenir », « alertes »), la vue « sourcing » restant comptée à chaque ouverture.
    ongletGo(t) {
      if (!t) return;
      if (t.sous) {
        const deja = this.view === t.view;
        if (!deja) this.go(t.view);              // go() rouvre Trouver des marchés sur « Publiés »
        this.trouverOnglet = t.sous;
        if (t.sous !== "publies") this._ecranOuvert(t.sous);
        this.mobileNav = false;
        return;
      }
      this.go(t.view);
    },
    // Entrée du menu : le premier onglet de la rubrique.
    rubriqueGo(k) { const r = RUBRIQUES.find(x => x.k === k); if (r) this.ongletGo(r.onglets[0]); },
    // En-tête : le nom de la rubrique quand la vue en est un onglet (les onglets disent où l'on est dedans), sinon le
    // nom de la vue (Le marché, Collègues…). La bulle (i) dit ce que fait l'écran, puis son ancien nom (1.7, 1.8).
    enteteTitre() {
      const r = rubriqueDe(this.view);
      if (r && (r.k === "accueil" || this.ongletsVisibles().length)) return r.label;
      return this.titles[this.view] || "";
    },
    // Deux morceaux affichés séparément : chacun est une clé du dictionnaire de traduction (i18n.js).
    enteteAideVue() {
      const sous = this.view === "sourcing" && this.trouverOnglet !== "publies" ? this.trouverOnglet : "";
      return this.subtitles[sous || this.view] || "";
    },
    // L'ancien nom, seulement pour qui l'a connu (transitionVisible : ni la démonstration, ni un compte neuf).
    enteteAncien() { return transitionVisible(this.user) ? ancienNom(ongletDe(this.view, this.view === "sourcing" ? this.trouverOnglet : "")) : ""; },
    enteteAide() { return [this.enteteAideVue(), this.enteteAncien()].filter(Boolean).join(" "); },
    toggleReglages() {
      this.navReglages = !this.navReglages;
      try { localStorage.setItem("adjugo_nav_reglages", this.navReglages ? "1" : "0"); } catch (e) {}
    },
    // Pastilles : seulement ce qui attend une action de votre part, jamais un total ni zéro (étude, § 8, règle 8).
    // « Où je suis partenaire » : marchés d'autres entreprises où votre accord est demandé (convention) ou une partie
    // du dossier de présentation vous attend ; s'y ajoutent les invitations reçues par le réseau à traiter.
    partenaireActions() {
      return (this.shared || []).filter(s => (s.groupement && s.groupement.a_valider)
        || (s.redaction && (s.redaction.a_faire || s.redaction.a_revalider || s.redaction.a_valider || s.redaction.questions))).length;
    },
    mmActions() { return this.partenaireActions() + this.rnRecuesCount(); },
    // Barre basse (vague 2a, décision 18) : « Menu » est surligné quand il est ouvert, ou sur un écran qu'il range
    // (Mes documents, Mon entreprise, Réglages).
    menuBasMenu() { return this.mobileNav || ["documents", "entreprise", "reglages"].indexOf(this.rubrique()) >= 0; },
    // ── Mes marchés en liste filtrable (vague 2a, A2 ; listeMesMarches et invitationsATraiter en tête du fichier) ──
    // Les filtres ne comptent rien, sauf « Où je suis partenaire » : ce qui attend votre action (jamais un total).
    mmFiltres() {
      return [{ k: "tous", label: "Tous", ic: "list" }, { k: "pilote", label: "Je pilote", ic: "flag" },
              { k: "partenaire", label: "Où je suis partenaire", ic: "inbox", n: this.mmActions() },
              { k: "plusieurs", label: "À plusieurs", ic: "handshake" }];
    },
    // Changer de filtre : « Où je suis partenaire » et « À plusieurs » sont comptés comme leurs anciens écrans (mesure).
    mmFiltrer(k) {
      if (MM_FILTRES.indexOf(k) < 0 || this.mmFiltre === k) return;
      this.mmFiltre = k;
      if (k === "partenaire") { this._ecranOuvert("shared"); this.loadShared(); this.rnLoadRecues(true); }
      if (k === "plusieurs") { this._ecranOuvert("consortiums"); this.loadConsortiums(); }
    },
    mmGroupes() { return listeMesMarches(this.projects, this.shared, (this.consortiums || {}).consortiums, this.mmFiltre, this.statuses2); },
    mmPlusieurs(p) {
      const cs = ((this.consortiums || {}).consortiums || []).find(c => c && p && c.project_id === p.id);
      return cs && cs.partners ? cs : null;
    },
    mmInvitations() { return this.mmFiltre === "tous" || this.mmFiltre === "partenaire" ? invitationsATraiter(this.reseau.recues.list, this.shared) : []; },
    mmVide() { return !this.mmGroupes().length && !this.mmInvitations().length; },
    // Mes marchés › Bilan : « Où vous gagnez / perdez » s'il y a au moins un segment à montrer (comme sur l'accueil avant).
    bilanVisible() {
      const sg = this.stats && this.stats.segments;
      return !!(sg && ((sg.by_zone || []).length || (sg.loss_reasons || []).length || (sg.by_groupement || []).length));
    },
    ongletPastille(t) {
      if (t.pastille === "partenaire") return this.mmActions();
      if (t.pastille === "pieces") return (this.expiring || []).length;
      return 0;
    },
    // Note « Ce qui a changé » (1.8), sur l'accueil : une semaine au plus après son premier affichage, fermable.
    noteReorgVue() { return noteReorgVisible(this.user, this.reorgEtat, Date.now()); },
    _noteReorgSauver() { try { localStorage.setItem("adjugo_reorg_v1", JSON.stringify(this.reorgEtat)); } catch (e) {} },
    noteReorgMarquer() { if (this.noteReorgVue() && !this.reorgEtat.vu) { this.reorgEtat = { ...this.reorgEtat, vu: Date.now() }; this._noteReorgSauver(); } },
    noteReorgFermer() { this.reorgEtat = { ...this.reorgEtat, ferme: true }; this._noteReorgSauver(); },

    // ── Navigation + lazy loads ──
    go(v) {
      if (v === "amont" && !this.features.projets_a_venir) v = "dashboard";   // écran masqué (PROJETS_A_VENIR=0)
      // Mes marchés en liste filtrable (vague 2a, A2) : « Où je suis partenaire » et « À plusieurs » sont des filtres ;
      // les anciens appels (accueil, retour d'un dossier partagé…) y mènent. Entrer dans la liste par le menu la remet
      // sur « Tous » ; un retour depuis un marché garde le filtre (aoBack ne passe pas par go()).
      let filtre = "";
      if (v === "shared" || v === "consortiums") { filtre = v === "shared" ? "partenaire" : "plusieurs"; v = "pipeline"; }
      if (v === "pipeline") { if (filtre) this.mmFiltre = filtre; else if (this.view !== "pipeline") this.mmFiltre = "tous"; }
      if (v === "sourcing" && this.view !== "sourcing") this.trouverOnglet = "publies";   // s'ouvre sur « Publiés » (1.3)
      this.view = v;
      this._ecranOuvert(v);
      if (filtre) this._ecranOuvert(filtre === "partenaire" ? "shared" : "consortiums");   // mesure : l'ancien écran
      this.mobileNav = false;  // referme le menu mobile à la navigation
      this.notifsOpen = false; this.fb.open = false;  // referme les popups (notifications / retour d'avis) à la navigation
      if (v === "dashboard") { this.loadStats(); this.loadExpiring(); this.loadConsortiums(); this.loadNotifs(); this.loadGrpDash(); this.noteReorgMarquer(); }
      if (v === "pipeline") { this.loadProjects(); this.loadShared(); this.rnLoadRecues(true); this.loadConsortiums(); }   // la liste et ses pastilles à jour
      if (v === "bilan") this.loadStats();
      if (v === "contacts") this.loadContacts();
      if (v === "invoices") this.loadInvoices();
      if (v === "documents") this.loadDocuments();
      if (v === "cotraitants") { this.loadCotraitants(); this.loadTrades(); }
      if (v === "sourcing") { this.loadTrades(); this.loadAlerts(); this.loadCountries(); this.loadStats(); this.srcPrefillFromProfile(); }
      if (v === "amont") this.loadAmont();
      if (v === "kb") this.kbLoad();
      if (v === "preuves") { this.pvLoad(); this._pvSourcesCharger(); }
      if (v === "team") this.loadOrg();
      if (v === "billing") { this.loadPlan(); this.loadStats(); }
      if (v === "admin") this.loadAdmin();
      if (v === "reseau") this.rnGo(this.reseau.tab || "profil");
      this.$nextTick(() => { const w = document.querySelector(".work"); if (w) w.scrollTop = 0; });   // remonte en haut du contenu à chaque changement de vue
    },
    // ══════════ Une adresse par écran (réorganisation, vague 2a, A1 ; ADRESSES en tête du fichier) ══════════
    // Appelé par l'observateur d'`adresseCourante` : un nouvel écran ajoute une entrée à l'historique du navigateur
    // (la position de défilement de l'écran quitté y est gardée) ; quand l'écran suit déjà l'adresse (démarrage,
    // précédent / suivant), l'adresse est seulement corrigée (marché introuvable → Mes marchés, par exemple). Le titre
    // de l'onglet du navigateur suit l'écran. Rien avant la connexion : l'écran de connexion garde son adresse.
    // `garderDefil` : l'entrée quittée garde sa position de défilement (retour arrière qui ne fait que fermer une
    // fenêtre : l'écran affiché n'est pas celui de cette entrée). `_nIci` : la profondeur de l'entrée affichée.
    _adresseSynchro(adr, garderDefil) {
      if (!adr || !this.token || !this._adresseActive) return;
      try {
        const st = history.state || {}, titre = this.enteteTitre();
        document.title = (titre ? titre + " · " : "") + "Adjugo";
        this._nIci = st.n || 0;
        if (adr === location.pathname && !location.search) return;
        if (this._adresseSuit || adr === location.pathname) {
          history.replaceState(Object.assign({}, st, { adjugo: 1, n: st.n || 0 }), "", adr);
          return;
        }
        if (!garderDefil) {
          const w = document.querySelector(".work");
          history.replaceState(Object.assign({}, st, { adjugo: 1, n: st.n || 0, defil: w ? w.scrollTop : 0 }), "");
        }
        history.pushState({ adjugo: 1, n: (st.n || 0) + 1 }, "", adr);
        this._nIci = (st.n || 0) + 1;
      } catch (e) {}
    },
    // Précédent / suivant du navigateur (relecture de la vague 2a). Une fenêtre de l'application ouverte (confirmation,
    // invitation, fiche d'un partenaire, tiroir, cloche, fenêtres de l'atelier ou de Mes preuves) est toujours fermée
    // avant tout changement d'écran : une confirmation restée ouverte agissait sinon sur le marché de l'écran suivant.
    // Précédent avec une fenêtre ouverte ne fait QUE la fermer (le geste retour d'Android) : l'écran reste, son
    // adresse revient dans l'historique. Suivant : la fenêtre se ferme et l'écran suit l'adresse.
    _surRetourNavigateur(ev) {
      if (!this.token || !this._adresseActive) return;
      const n = ev && ev.state && typeof ev.state.n === "number" ? ev.state.n : null;
      const suivant = n !== null && typeof this._nIci === "number" && n > this._nIci;
      if (this._fermerFenetres(!suivant) && !suivant) {
        const ici = this.adresseCourante;
        if (ici && ici !== location.pathname) { this._adresseSynchro(ici, true); return; }
      }
      this._nIci = n || 0;
      this._ouvrirAdresse(etatDeAdresse(location.pathname), ev && ev.state && ev.state.defil);
    },
    // Ferme toute fenêtre de l'application ouverte ; vrai si l'une l'était. La confirmation répond « Annuler » (sa
    // promesse rend null). `rendreFocus` : l'écran reste, le focus revient où il était.
    _fermerFenetres(rendreFocus) {
      const a = this.atl || {}, pv = this.pv || {};
      const atelier = !!(a.derog || a.debit || a.vue || a.lotsDlg || a.plan);
      const ouverte = !!(this.cdlg || this.rinv || (this.reseau && this.reseau.fiche) || this.modal || this.drawer
        || this.notifsOpen || (this.discover && this.discover.open) || (this.fb && this.fb.open) || pv.passage
        || (this.pvAtl && this.pvAtl.open) || atelier);
      if (!ouverte) return false;
      if (this.cdlg) this.cdlgClose();
      if (this.rinv) this.rinvClose(!rendreFocus);
      if (this.reseau && this.reseau.fiche) this.rnCloseFiche(!rendreFocus);
      if (this.pvAtl && this.pvAtl.open) this.pvAtlFermer();
      if (pv.passage) pv.passage = null;
      if (atelier) { a.derog = null; a.debit = null; a.vue = null; a.lotsDlg = null; a.plan = null; }
      if (this.discover && this.discover.open) this.discover.open = false;
      if (this.fb && this.fb.open) this.fb.open = false;
      this.modal = null; this.drawer = null; this.notifsOpen = false;
      return true;
    },
    // L'écran suit l'adresse, sans nouvelle entrée d'historique. Le changement d'écran est observé à la fin du tour
    // en cours ; juste après, l'adresse est remise d'aplomb (chemin inconnu → /app, même quand l'écran n'a pas changé)
    // et le drapeau tombe.
    _sansHistorique(fn) {
      this._adresseSuit = true;
      try { fn(); } finally {
        this.$nextTick(() => { if (!this._adresseAttente) this._adresseSynchro(this.adresseCourante); this._adresseSuit = false; });
      }
    },
    // Chemin demandé au démarrage : celui de la barre d'adresse, ou celui gardé avant la connexion Google (le retour
    // de Google arrive sur /app). Lu une seule fois.
    _adresseDemandee() {
      let garde = "";
      try { garde = sessionStorage.getItem("adjugo_adresse") || ""; sessionStorage.removeItem("adjugo_adresse"); } catch (e) {}
      const ici = location.pathname;
      return (etatDeAdresse(ici) || {}).view === "dashboard" && etatDeAdresse(garde) ? garde : ici;
    },
    // Ouvre l'écran que décrit `e` (etatDeAdresse) sans ajouter d'entrée d'historique ; `defil` : la position de
    // défilement gardée dans l'entrée (retour arrière).
    _ouvrirAdresse(e, defil) {
      if (this.view === "atelier" && !(e && e.view === "atelier")) this._atlQuitter();
      this.drawer = null;
      this._sansHistorique(() => this._appliquerAdresse(e || { view: "dashboard" }));
      if (defil) this.$nextTick(() => setTimeout(() => { const w = document.querySelector(".work"); if (w) w.scrollTop = defil; }, 60));
    },
    _appliquerAdresse(e) {
      const v = e.view;
      if (v === "aodetail" || v === "atelier") {
        // Le marché revient à sa page (depuis l'atelier : sans tout recharger) ; un marché introuvable (supprimé, d'une
        // autre organisation) ouvre Mes marchés, avec un message.
        const ouvrir = (p) => {
          if (v === "aodetail" && this.view === "atelier" && this.ao.project && this.ao.project.id === p.id) {
            this.view = "aodetail"; this._ecranOuvert("aodetail"); this.atlCardLoad(); return;
          }
          if (!(this.ao.project && this.ao.project.id === p.id && (this.view === "aodetail" || this.view === "atelier"))) {
            this.openAo(p);
            this.ao.back = "pipeline";       // ouvert par son adresse : « Retour » mène à Mes marchés
          }
          if (v === "atelier") this.atlOpen();
        };
        const p = (this.projects || []).find(x => x.id === e.projet);
        if (p) { ouvrir(p); return; }
        // Pas dans la liste (créé dans un autre onglet, par exemple) : on le demande ; l'adresse ne bouge pas en attendant.
        this._adresseAttente = true;
        const voulue = adresseDe(e), encore = () => location.pathname === voulue;   // personne n'est allé ailleurs
        this.api("GET", "/api/projects/" + e.projet)
          .then(pp => { if (!(pp && pp.id)) throw new Error(); this._adresseAttente = false; if (encore()) this._sansHistorique(() => ouvrir(pp)); })
          .catch(() => { this._adresseAttente = false; if (!encore()) return; this.notify("Ce marché n'est plus accessible", "err"); this._sansHistorique(() => this.go("pipeline")); });
        return;
      }
      if (v === "sharedao") {
        const it = trouverPartage(this.shared, e.partage, e.cle);
        if (it) { if (!(this.view === "sharedao" && this.sharedAo.token === it.token)) this.openShared(it); return; }
        this.notify("Ce dossier n'est plus accessible", "err"); this.go("shared"); return;
      }
      if (v === "admin" && !(this.user && this.user.is_admin)) { this.go("dashboard"); return; }
      if (v === "reseau") this.reseau.tab = e.reseau || "profil";
      if (v === "sourcing") {
        if (this.view !== "sourcing") this.go("sourcing");
        const sous = e.sous || "publies";
        if (this.trouverOnglet !== sous) { this.trouverOnglet = sous; if (sous !== "publies") this._ecranOuvert(sous); }
        return;
      }
      if (v === "reseau" && this.view === "reseau") { this.rnGo(this.reseau.tab); return; }
      if (v === "pipeline") {
        // Mes marchés et son filtre (« Tous » sans filtre dans l'adresse) : la liste s'ouvre, puis le filtre se pose
        // comme un clic sur lui (chargements et mesure de l'ancien écran compris).
        if (this.view !== "pipeline") this.go("pipeline");
        this.mmFiltrer(e.filtre || "tous");
        return;
      }
      if (this.view !== v || v === "dashboard") this.go(v);
    },
    // « Retour » d'une page de détail : l'écran d'avant, comme le bouton du navigateur, quand on y est venu depuis
    // l'application (l'entrée d'historique le sait) ; sinon (lien ouvert directement), la liste, comme avant.
    _retourHistorique() {
      try { const st = history.state; if (this._adresseActive && st && st.adjugo && st.n > 0) { history.back(); return true; } } catch (e) {}
      return false;
    },
    partageRetour() { if (!this._retourHistorique()) this.go("shared"); },
    // Mesure d'usage (réorganisation, vague 1, 1.1 ; décision 17) : un événement par ouverture d'écran, vers le
    // compteur INTERNE d'Adjugo (jour, écran) — aucune donnée personnelle, aucun outil tiers, jamais montré aux
    // clients. Sans attente ni barre de progression ni message : une mesure perdue ne gêne jamais l'écran.
    _ecranOuvert(v) {
      if (!this.token || !v) return;
      try {
        fetch("/api/mesure/ecran", { method: "POST",
          headers: { "Authorization": "Bearer " + this.token, "Content-Type": "application/json" },
          body: JSON.stringify({ ecran: String(v) }) }).catch(() => {});
      } catch (e) {}
    },
    async loadAdmin() {
      this.adminRvLoad();
      this.adminIaLoad();
      this.adminMesureLoad();
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
    // Coût de l'IA (interne) : budget consommé par les essais, coût du mois des forfaits payants, alertes.
    async adminIaLoad() {
      const ia = this.admin.ia; if (ia.loading) return;
      ia.loading = true; ia.error = "";
      try { ia.data = await this.api("GET", "/api/admin/usage-ia"); }
      catch (e) { ia.error = (e && e.message) || "Relevé momentanément indisponible."; }
      finally { ia.loading = false; }
    },
    async adminMesureLoad() {
      const m = this.admin.mesure; if (m.loading) return;
      m.loading = true; m.error = "";
      try { m.data = await this.api("GET", "/api/admin/mesures/ecrans?jours=30"); }
      catch (e) { m.error = (e && e.message) || "Relevé momentanément indisponible."; }
      finally { m.loading = false; }
    },
    // Nom lisible d'un écran mesuré : « Rubrique › Onglet » (menu par rubriques, 1.3), sinon le titre de la vue, sinon
    // sa clé. « avenir » et « alertes » sont les onglets internes de Trouver des marchés.
    adminEcranNom(k) {
      const sous = (k === "avenir" || k === "alertes") ? k : "";
      const v = sous ? "sourcing" : k, r = rubriqueDe(v), t = ongletDe(v, sous);
      if (r && t && !r.groupe && r.k !== "accueil") return r.label + " › " + t.label;
      return this.titles[k] || (t && t.label) || k;
    },
    fmtEur(v) { const n = Number(v); return isFinite(n) ? n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €" : "—"; },
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
      if (!(await this.confirmer({ title: "Retirer " + (m.full_name || m.email) + " de vos collègues ?", ok: "Retirer", danger: true,
        lines: ["Ses dossiers (marchés, contacts…) sont réattribués au propriétaire de l'organisation.", "Son accès est coupé immédiatement."] }))) return;
      try { const r = await this.api("DELETE", "/api/org/members/" + m.id); this.loadOrg(); this.notify(m.full_name + " retiré" + (r && r.reassigned ? " — " + r.reassigned + " élément(s) réattribué(s)" : "")); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async orgSetRole(m, role) {
      try { await this.api("PUT", "/api/org/members/" + m.id + "/role", { role }); this.loadOrg(); this.notify((m.full_name || m.email) + " : " + this.roleLabelOrg(role)); }
      catch (e) { this.notify(e.message, "err"); this.loadOrg(); }
    },
    async orgTransfer(m) {
      if (!(await this.confirmer({ title: "Transférer la propriété de l'organisation ?", ok: "Transférer la propriété",
        lines: [(m.full_name || m.email) + " devient propriétaire de l'organisation.", { t: "Vous deviendrez simple administrateur.", warn: true }] }))) return;
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
      if (!(await this.confirmer({ title: "Créer la facture ?", ok: "Créer la facture",
        lines: ["Une facture est créée à partir du devis " + i.reference + "."] }))) return;
      try { const f = await this.api("POST", "/api/invoices/" + i.id + "/convert"); await this.loadInvoices(); this.notify("Facture " + (f && f.reference || "") + " créée"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async loadDocuments() { try { this.documents = await this.api("GET", "/api/documents/") || []; } catch (e) {} },
    async loadExpiring() { try { this.expiring = await this.api("GET", "/api/documents/expiring") || []; } catch (e) { this.expiring = []; } },
    async loadCompany() { try { const c = await this.api("GET", "/api/company/"); if (c && !c.detail) this.company = c; } catch (e) {} },
    async loadLlmInfo() { try { this.llmInfo = await this.api("GET", "/api/llm/info"); } catch (e) {} },
    async loadCriteria() { try { this.criteria = await this.api("GET", "/api/criteria/") || {}; } catch (e) {} },

    // ══════════ « Mes preuves » (rédaction, vague 3, E1) ══════════
    // Sous « Mon entreprise ». Contrat : docs/REDACTION_V3_PREUVES.md (routes /api/preuves) et
    // app/routers/preuves_ecrans.py (reprise de l'existant, insertion dans l'atelier). Aucune IA.
    pvNatures() { return PV_NATURES; },
    pvNature(code) { return PV_NATURES.find(n => n.code === code) || PV_NATURES[0]; },
    pvChamps(n) { return PV_CHAMPS[n] || []; },
    pvTypesSource(n) { return PV_SOURCES.filter(t => !t.natures || t.natures.includes(n)); },
    pvAvecValidite(n) { return !!PV_VALIDITE[n]; },
    pvLibValidite(n) { return PV_VALIDITE[n] || ""; },
    pvTitre, pvDetail, pvTexteLong, pvValidite, pvEcheance, pvSrcIcone, pvJj: _pvJj,
    pvAlertes() { return pvAlertes(this.pv.list); },
    pvOnglet(n) { this.pv.tab = n; if (this.pv.form && this.pv.form.nature !== n && !this.pv.form.id) this.pv.form = null; },
    async pvLoad() {
      const pv = this.pv; if (pv.loading) return;
      pv.loading = true; pv.error = "";
      try { const d = await this.api("GET", "/api/preuves"); pv.list = (d && d.preuves) || []; pv.loaded = true; }
      catch (e) { pv.error = e.message || "Liste momentanément indisponible."; }
      finally { pv.loading = false; }
      try { pv.rep.d = await this.api("GET", "/api/preuves/reprise"); } catch (e) { pv.rep.d = null; }
    },
    _pvSourcesCharger() {
      if (!this.kb.docs.length) this.kbLoad();
      if (!this.documents.length) this.loadDocuments();
      if (!this.projects.length) this.loadProjects();
    },
    pvListe(n) {
      const ordre = { proposee: 0, acceptee: 1, retiree: 2 };
      return this.pv.list.filter(p => p.nature === n).sort((a, b) => ((ordre[a.statut] || 0) - (ordre[b.statut] || 0)) || (a.numero - b.numero));
    },
    pvCompte(n) { return this.pv.list.filter(p => p.nature === n && p.statut !== "retiree").length; },
    pvProposees(n) { return this.pv.list.filter(p => p.nature === n && p.statut === "proposee"); },
    pvCoches(n) { return this.pvProposees(n).filter(p => this.pv.sel[p.id]); },
    pvRepriseNombre() { const d = this.pv.rep.d; return (d && d.a_reprendre) || 0; },
    pvUrlSure(u) { return /^https:\/\/[^\s"'<>]+$/.test(String(u || "")); },
    pvKbDocs() { return (this.kb.docs || []).filter(d => d && d.id); },
    // Vague 5 (E2) : une fiche tirée d'une source publique (DECP, liste RGE) garde les champs de la source tant
    // qu'elle garde cette source (le serveur le refuse aussi) ; « Déclaré par vous » les rend modifiables.
    pvVerrous() { const f = this.pv.form; return (f && f.type_source === "public" && Array.isArray(f.verrous)) ? f.verrous : []; },
    pvVerrou(k) { return this.pvVerrous().includes(k); },
    pvJustificatifs() { return (this.documents || []).filter(d => d && d.id); },
    // ── Ajouter / modifier une fiche ──
    pvNouveau(n) {
      this._pvSourcesCharger();
      const v = {}; this.pvChamps(n).forEach(c => { v[c.k] = ""; });
      this.pv.tab = n;
      this.pv.form = { id: null, nature: n, v, type_source: "declare", doc_id: "", passage: "", date_source: "", document_id: "",
                       pub: { nom: "", url: "", consulte_le: "", identifiant: "" }, est: { project_id: "", detail: "" },
                       date_fin_validite: "", version: null, err: "" };
      this.$nextTick(() => { const el = document.getElementById("pvf-" + this.pvChamps(n)[0].k); if (el) el.focus(); });
    },
    pvModifier(p) {
      this._pvSourcesCharger();
      const v = {}; this.pvChamps(p.nature).forEach(c => { const x = (p.valeur || {})[c.k]; v[c.k] = x == null ? "" : x; });
      const s = p.source || {}, doc = p.type_source === "documents";
      this.pv.form = { id: p.id, nature: p.nature, v, type_source: p.type_source, doc_id: (doc && s.doc_id) || "", passage: (doc && s.passage) || "",
                       date_source: (doc && s.doc_id && p.date_source) || "", document_id: (doc && s.document_id) || "",
                       pub: { nom: s.nom || "", url: s.url || "", consulte_le: s.consulte_le || "", identifiant: s.identifiant || "" },
                       est: { project_id: s.project_id || "", detail: s.detail || "" }, date_fin_validite: p.date_fin_validite || "",
                       version: p.version, err: "", verrous: p.type_source === "public" ? (p.champs_source_publique || []) : [] };
      this.$nextTick(() => { const el = document.getElementById("pvf-" + this.pvChamps(p.nature)[0].k); if (el) { el.focus(); el.scrollIntoView({ block: "center" }); } });
    },
    async pvEnregistrer() {
      const pv = this.pv, f = pv.form; if (!f || pv.busy) return;
      const manque = this.pvChamps(f.nature).filter(c => c.req && !String(f.v[c.k] == null ? "" : f.v[c.k]).trim()).map(c => c.l);
      if (manque.length) { f.err = "À remplir : " + manque.join(", ") + "."; return; }
      const body = pvCorps(f, this.pvAvecValidite(f.nature));
      pv.busy = "form"; f.err = "";
      try {
        if (f.id) { body.version = f.version; await this.api("PATCH", "/api/preuves/" + f.id, body); }
        else { body.nature = f.nature; await this.api("POST", "/api/preuves", body); }
        pv.form = null; this.notify(f.id ? "Fiche modifiée" : "Fiche ajoutée"); await this.pvLoad();
      } catch (e) {
        f.err = e.message || "Enregistrement impossible.";
        if (e.code === "modifiee_ailleurs") this.pvLoad();
      } finally { pv.busy = ""; }
    },
    // ── Cocher, retirer, supprimer ──
    async pvStatut(p, action) {
      if (this.pv.busy) return;
      this.pv.busy = "p" + p.id;
      try {
        await this.api("POST", "/api/preuves/" + p.id + "/" + action, { version: p.version }); delete this.pv.sel[p.id];
        this.notify(action === "accepter" ? "Fiche acceptée : Adjugo peut s'en servir" : "Fiche retirée : Adjugo ne s'en sert plus");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.pv.busy = ""; }
      await this.pvLoad();
    },
    async pvAccepterCoches(n) {
      const ps = this.pvCoches(n); if (!ps.length || this.pv.busy) return;
      this.pv.busy = "lot"; let ok = 0; const errs = [];
      for (const p of ps) {
        try { await this.api("POST", "/api/preuves/" + p.id + "/accepter", { version: p.version }); ok++; delete this.pv.sel[p.id]; }
        catch (e) { errs.push(pvTitre(p) + " : " + e.message); }
      }
      this.pv.busy = "";
      if (errs.length) this.notify(errs[0], "err"); else if (ok) this.notify(ok + (ok > 1 ? " fiches acceptées" : " fiche acceptée"));
      await this.pvLoad();
    },
    pvToutCocher(n) { const ps = this.pvProposees(n), tout = ps.every(p => this.pv.sel[p.id]); ps.forEach(p => { this.pv.sel[p.id] = !tout; }); },
    pvSupprimer(p) {
      this._convAsk({ title: "Supprimer cette fiche ?", ok: "Supprimer définitivement", run: () => this._pvSupprimer(p),
        lines: ["« " + pvTitre(p) + " » sera effacée de « Mes preuves »" + (p.nature === "salarie" ? ", CV compris" : "") + ". Les dossiers où vous l'avez déjà insérée ne changent pas.",
                "Pour qu'Adjugo ne s'en serve plus tout en la gardant, choisissez plutôt « Retirer »."] });
    },
    async _pvSupprimer(p) {
      try { await this.api("DELETE", "/api/preuves/" + p.id); if (this.pv.form && this.pv.form.id === p.id) this.pv.form = null; this.notify("Fiche supprimée"); }
      catch (e) { this.notify(e.message, "err"); }
      await this.pvLoad();
    },
    // ── Où le fait a été trouvé : le passage exact, ou le justificatif ──
    async pvPassage(p) {
      try { this.pv.passage = Object.assign({ titre: pvTitre(p) }, await this.api("GET", "/api/preuves/" + p.id + "/passage")); }
      catch (e) { this.notify(e.message, "err"); }
    },
    pvJustificatif(p) { const s = p.source || {}; if (s.document_id) this.downloadDoc({ id: s.document_id, name: s.document_nom || "justificatif" }); },
    // ── Reprendre ce qui existe déjà (profil, réseau, coffre-fort) : l'utilisateur coche ──
    async pvRepriseOuvrir() {
      const r = this.pv.rep; r.open = true; r.loading = true; r.err = "";
      try {
        r.d = await this.api("GET", "/api/preuves/reprise");
        const sel = {}; ((r.d && r.d.elements) || []).forEach(e => { if (!e.manque) sel[e.cle] = true; }); r.sel = sel;
      } catch (e) { r.err = e.message || "Reprise momentanément indisponible."; }
      finally { r.loading = false; }
    },
    pvRepriseGroupes() {
      const els = (this.pv.rep.d && this.pv.rep.d.elements) || [];
      return PV_NATURES.map(n => ({ code: n.code, l: n.l, els: els.filter(e => e.nature === n.code) })).filter(g => g.els.length);
    },
    pvRepriseCoches() { return ((this.pv.rep.d && this.pv.rep.d.elements) || []).filter(e => !e.manque && this.pv.rep.sel[e.cle]).length; },
    async pvReprendre() {
      const r = this.pv.rep; if (!r.d || r.busy) return;
      const cles = (r.d.elements || []).filter(e => !e.manque && r.sel[e.cle]).map(e => e.cle);
      if (!cles.length) return;
      r.busy = true; r.err = "";
      try {
        const x = await this.api("POST", "/api/preuves/reprise", { cles });
        const n = ((x && x.creees) || []).length;
        this.notify(n ? n + (n > 1 ? " fiches reprises" : " fiche reprise") + " dans « Mes preuves »" : "Rien de nouveau à reprendre");
        if (x && (x.ignorees || []).length) r.err = x.ignorees.map(i => i.texte + " : " + i.message).join(" ");
        else r.open = false;
      } catch (e) { r.err = e.message || "Reprise impossible."; }
      finally { r.busy = false; }
      await this.pvLoad();
    },
    // ── Dans l'atelier : insérer une fiche choisie, telle quelle, sans IA ──
    async pvAtlOuvrir() {
      const s = this.atlSec(); if (!s || !s.peut_ecrire || this.atlMobile || this.atl.busy) return;
      const ta = this.$refs.atlTa;
      this.pvAtl = Object.assign(_pvAtlInit(), { open: true, loading: true, sid: s.id,
                                                 pos: (this.atl.mode === "modifier" && ta) ? (ta.selectionEnd || 0) : null });
      try { this.pvAtl.d = await this.api("GET", this._atlUrl("/preuves")); }
      catch (e) { this.pvAtl.err = e.message || "Fiches momentanément indisponibles."; }
      finally { this.pvAtl.loading = false; }
    },
    pvAtlGroupes() {
      const d = this.pvAtl.d, q = _atlKey(this.pvAtl.q);
      const fs = ((d && d.fiches) || []).filter(f => !q || _atlKey(f.titre + " " + f.bloc).indexOf(q) >= 0);
      return PV_NATURES.map(n => ({ code: n.code, l: n.l, fiches: fs.filter(f => f.nature === n.code) })).filter(g => g.fiches.length);
    },
    // Aperçu du texte inséré : rendu sûr de l'atelier (tout est échappé ; seuls le gras et les listes passent).
    pvApercuHtml(f) { return atlMdToHtml((f && f.bloc) || "", []); },
    pvAtlFermer() { this.pvAtl = _pvAtlInit(); },
    pvAtlVersPreuves() { this.pvAtlFermer(); this.go("preuves"); },
    async pvAtlInserer() {
      const x = this.pvAtl, f = x.choix, a = this.atl, s = this.atlSec(); if (!f || !s || s.id !== x.sid || x.busy) return;
      if (a.mode === "modifier") {
        const r = pvInsererTexte(a.edit.texte, x.pos, f.bloc);
        a.edit.texte = r.texte; this.atlInput(); this.pvAtlFermer();
        this.$nextTick(() => { const ta = this.$refs.atlTa; if (ta) { ta.focus(); ta.setSelectionRange(r.pos, r.pos); } });
        this.notify("Fiche insérée : enregistrez le texte pour la garder");
        return;
      }
      const v = s.version_courante;
      this._atlEchecOublier(s.id);
      x.busy = true; x.err = "";
      try {
        const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/inserer-preuve"), { preuve_id: f.id, base_version_id: v ? v.id : null });
        this._atlPut(r); this.pvAtlFermer(); this.notify("Fiche insérée à la fin de la partie"); this.atlLoad(true);
      } catch (e) {
        x.err = e.message || "Insertion impossible.";
        if (e.code === "texte_modifie_entre_temps") this.atlLoad(true);
      } finally { x.busy = false; }
    },

    // ── Company / Criteria ──
    // Identité et Tarifs enregistrent la même fiche de l'entreprise (une seule route) : chaque onglet a son bouton.
    async saveCompany(onglet) {
      const tarifs = onglet === "tarifs";
      if (!(this.company.name || "").trim()) {
        this.notify(tarifs ? "Renseignez d'abord le nom de votre entreprise, dans l'onglet « Identité »" : "Indiquez le nom de votre entreprise (Dénomination)", "err"); return;
      }
      this.busy = true;
      try { await this.api("PUT", "/api/company/", this.company); this.notify(tarifs ? "Tarifs enregistrés" : "Profil enregistré"); }
      catch (e) { this.notify(e.message, "err"); } finally { this.busy = false; }
    },
    async saveCriteria() {
      const go = Number(this.criteria.go_threshold), ng = Number(this.criteria.nogo_threshold);
      if (go && ng && go <= ng) { this.notify("Le seuil « bon potentiel » doit être supérieur au seuil « peu adapté »", "err"); return; }
      const bmin = Number(this.criteria.budget_min), bmax = Number(this.criteria.budget_max);
      if (bmin && bmax && bmin > bmax) { this.notify("Le montant minimum doit être inférieur au montant maximum", "err"); return; }
      const seul = this.criteria.montant_porte_seul;
      if (seul !== "" && seul != null && !(Number(seul) >= 0)) { this.notify("Le montant que vous portez seul est un montant positif, en euros HT", "err"); return; }
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
    async gateCriteria() {
      // true = on continue ; false = on s'arrête (renvoyé vers « Ce que je cherche », ou fenêtre fermée : une analyse
      // coûte un crédit, elle ne part jamais sur un simple Échap).
      if (!this.criteriaEmpty()) return true;
      const r = await this.demander({ title: "Dire d'abord ce que vous cherchez ?", ok: "Renseigner ce que je cherche", autre: "Analyser quand même",
        lines: ["Vos spécialités et votre zone ne sont pas encore renseignées.", "Pour une analyse adaptée à votre entreprise, mieux vaut les indiquer d'abord, dans Mon entreprise, onglet « Ce que je cherche »."] });
      if (!r) return false;
      if (r.autre) return true;
      this.go("criteria"); return false;
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
      this.ao.cotraitants = []; this.ao.st.results = []; this.ao.st.trade = ""; this.ao.st.dept = "";
      this.view = "aodetail"; this._ecranOuvert("aodetail"); this.loadTrades(); this.ao.documents = []; this.ao.buyer = null; this.ao.buyerLoading = true; this.ao.checklist = null; this.ao.group = null;
      this.ao.qa = []; this.ao.qaInput = ""; this.ao.grilleBusy = ""; this.ao.atl = _atlCardInit(); this.ao.grp = _grpInit(); this.ao.conv = _convInit(); this.ao.pm = _pmInit(); this.ao.depot = _depotInit(); this.rinv = null;
      this.ao.estimate = null; this.ao.estimateOpen = false; this.ao.estimateDistance = 0;
      this.ao.share = { busy: false, invites: [], auditOpen: false, audit: [], contributions: [], contribOpen: false, consortium: null, cockpitOpen: false, freezing: false };
      this.$nextTick(() => { const w = document.querySelector(".work"); if (w) w.scrollTop = 0; });   // le marché s'ouvre en haut (depuis une recherche défilée, par exemple)
      try { this.ao.project = await this.api("GET", "/api/projects/" + p.id); } catch (e) {}
      this.loadPredepot(p.id);   // état du wizard pré-dépôt propre à cet AO
      this.aoLoadCotraitants(); this.aoLoadDocs(); this.aoLoadChecklist(); this.loadInvoices(); this.aoLoadEstimate(); this.aoLoadInvites(); this.aoLoadConsortium(); this.aoGrpLoad(); this.atlCardLoad();
      this.aoResumeLecture();   // gros dossier en cours de lecture (tâche de fond) : on reprend le suivi
      setTimeout(() => this.aoLoadBuyer(), 700);   // profil acheteur (BOAMP, lent) en différé, après le cœur de l'AO
    },
    loadPredepot(pid) {
      // Ancien format (4 cases, avant la vague 2a) : les 2 premières sont les mêmes points.
      try { const v = JSON.parse(localStorage.getItem("adjugo_predepot_" + pid) || "null"); this.predepot = Array.isArray(v) && (v.length === 2 || v.length === 4) ? v.slice(0, 2).map(Boolean) : [false, false]; }
      catch (e) { this.predepot = [false, false]; }
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
        this.ao.estimateOpen = true; this.aoAvancer();
        this.aoDepotLoadSoon();
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
        // Nom juste : c'est l'estimation d'Adjugo mise en forme, pas la pièce de prix exigée par l'acheteur.
        const a = document.createElement("a"); a.href = url; a.download = "Estimation-detaillee.pdf"; document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) { this.notify("Estimation détaillée momentanément indisponible.", "err"); }
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
      this.aoDepotLoadSoon();   // « Prêt à déposer » lit la même liste de pièces
    },
    async aoAsk() {
      const q = (this.ao.qaInput || "").trim();
      if (!q || this.ao.qaLoading) return;
      this.ao.qaLoading = true;
      this.ao.qa.push({ q, a: "__loading__", sources: [], msg: "" }); this.ao.qaInput = "";
      const entry = this.ao.qa[this.ao.qa.length - 1];
      try {
        const r = await this.api("POST", "/api/sourcing/ask", { project_id: this.ao.project.id, question: q });
        // Chaque source = une phrase du dossier retrouvée telle quelle, avec sa pièce et sa page.
        entry.sources = Array.isArray(r.sources) ? r.sources.filter(x => x && x.citation) : [];
        entry.msg = r.message || "";
        entry.a = r.answer || "—";
      } catch (e) { entry.a = "Erreur : " + e.message; }
      finally { this.ao.qaLoading = false; }
    },
    aoInvoices() { return (this.invoices || []).filter(i => i.project_id === (this.ao.project && this.ao.project.id)); },
    aoTimeline() {
      const p = this.ao.project || {}; const ev = [];
      if (p.created_at) ev.push({ icon: "plus", t: "Marché ajouté", d: this.fmtDate(p.created_at) });
      const a = p.ai_analysis;
      if (a) ev.push({ icon: "scan-search", t: a.dce_available ? "Dossier analysé (complet)" : "Annonce analysée", d: a.match_score != null ? "seul " + a.match_score + " %" : "" });   // décision 8 : le couple « Seul X % », jamais une note sur 100
      const e = this.ao.estimate;
      if (e && e.total_ht) ev.push({ icon: "calculator", t: "Estimation du prix", d: this.eur(e.total_ht) + " HT" });
      if (e && e.review && e.review.status === "valide") ev.push({ icon: "circle-check-big", t: "Estimation validée" + (e.review.by ? " · " + e.review.by : ""), d: "" });
      if (this.ao.cotraitants.length) ev.push({ icon: "handshake", t: this.ao.cotraitants.length + " membre(s) ou sous-traitant(s)", d: "" });
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
    // Réorganisation, vague 1 (réunion des chantiers, puis relecture) : un seul découpage, celui de la page du marché.
    // Chaque marché est placé sur la barre de SA page avec la même règle (etapeDuMarche : statut, dossier lu, étape du
    // groupement), lue dans la réponse du serveur (`barres`, et chaque marché listé). On ne montre que les étapes où se
    // trouve au moins un marché (jamais un zéro).
    grpDashEtape(x) { return ETAPES_LIBELLES[etapeDuMarche(x && x.statut, !!(x && x.dossier_lu), x && x.etape)] || ""; },
    grpDashEtapes() {
      const g = this.grpDash; if (!g || !Array.isArray(g.barres)) return [];
      const ordre = ["Lire", "Décider", "Préparer", "Déposer"], out = ordre.map(label => ({ label, count: 0 }));
      g.barres.forEach(b => { const i = ordre.indexOf(this.grpDashEtape(b)); if (i >= 0) out[i].count += 1; });
      return out.filter(e => e.count > 0);
    },
    grpDashItems() {
      const g = this.grpDash; if (!g) return [];
      const parts = {}; ((this.consortiums && this.consortiums.consortiums) || []).forEach(c => { parts[c.project_id] = c; });
      const lim = (d) => d ? "limite " + this.fmtDate(d) : "";
      const seen = new Set((g.en_cours || []).map(it => it.project_id)), out = [];   // TOUS les en cours, pas seulement les 5 listés
      (g.en_cours || []).slice(0, 5).forEach(it => {
        const cs = parts[it.project_id];
        // Décision 8 : « N sur M ». L'étape affichée est celle de la barre de la page du marché (grpDashEtape).
        const bits = [it.label, cs && cs.partners ? "parts reçues " + cs.submitted + " sur " + cs.partners : "", lim(it.deadline)].filter(Boolean);
        out.push({ project_id: it.project_id, name: it.name || "Marché", meta: bits.join(" · "), badge: this.grpDashEtape(it), pill: "neutral" });
      });
      (g.accessibles || []).filter(a => !seen.has(a.project_id)).slice(0, 3).forEach(a => {
        // « À décider », « À lire », « À préparer » : l'étape de la barre de sa page, dite en mots.
        const et = this.grpDashEtape(a);
        out.push({ project_id: a.project_id, name: a.name || "Marché", meta: [et ? "À " + et.toLowerCase() : "", lim(a.deadline)].filter(Boolean).join(" · "),
                   badge: a.groupement_score != null ? "À plusieurs " + a.groupement_score + " %" : "Bon potentiel en groupement", pill: "go_groupement" });
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
          // Téléchargé sans passer par la fiche du marché : les points à traiter (dossier de
          // présentation coupé ou non rédigé, pièces de partenaires manquantes…) restent affichés
          // sur la carte du groupement, et le plus grave est dit tout de suite — jamais tu.
          this.cexportWarn[pid] = (r.dossier.warnings || []).slice();
          this.notify(this.dossierToast(r.dossier, "Dossier commun exporté"), this.dossierWarnKind(r.dossier));
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
      this.sharedAo = _sharedInit(t, item.mandataire, item.project_id, item.role); this.sharedAo.loading = true;
      this.view = "sharedao"; this._ecranOuvert("sharedao");
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
        this.sharedAo.refsRiches = Array.isArray(c.references) ? c.references : [];
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
      if (!(await this.confirmer({ title: "Vous avez perdu votre code de récupération ?", ok: "Effacer l'ancien détail", danger: true,
        lines: [{ t: "L'ancien détail de votre chiffrage sera définitivement perdu : personne, ni Adjugo ni le chef de file, ne peut le récupérer.", warn: true },
                "Vous pourrez en saisir un nouveau."] }))) return;
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
               references: _spFusionRefs(k.refs, this.sharedAo.refsRiches),
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
    // Vague 5 (E2) : reprendre ses preuves et ses marchés publics dans sa part. La saisie en cours est d'abord
    // enregistrée (rien n'est perdu), puis le serveur ajoute ce qui a été coché à la version obtenue.
    async sharedAvantReprise() {
      const ok = await this._sharedPut();
      return ok ? { ok: true, version: this.sharedAo.version } : { ok: false, message: "Votre part n'a pas pu être enregistrée : rien n'a été ajouté." };
    },
    sharedApresReprise(d) {
      const c = d && d.contribution; if (!c) return;
      const k = this.sharedAo.contrib;
      k.quals = (c.qualifications || []).map(q => (q && typeof q === "object") ? (q.name || q.nom || "") : q).filter(Boolean).join(", ");
      k.refs = (c.references || []).map(r => (r && r.intitule) || "").filter(Boolean).join("\n");
      this.sharedAo.refsRiches = Array.isArray(c.references) ? c.references : [];
      this.sharedAo.version = c.version || 0; this.sharedAo.status = c.status;
    },
    sharedRefsNote() { return _spLibRefs(_spFusionRefs(this.sharedAo.contrib.refs, this.sharedAo.refsRiches)); },
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
      } else {
        const v = await this.demander({ title: "Vérifiez votre identité", ok: "Valider",
          lines: ["Saisissez le code à 6 chiffres envoyé à " + masked + " pour confirmer que c'est bien vous."],
          fields: [{ key: "code", label: "Code reçu par courriel", inputmode: "numeric", autocomplete: "one-time-code", placeholder: "123456", max: 6, requis: true, motif: "^\\d{6}$" }] });
        code = v && v.code;
      }
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
    // Rattacher un lien à son compte : la clé de l'espace privé de rédaction ouvert dans CE navigateur (page du lien)
    // prouve qu'on le détient (sinon 409 « espace_a_prouver »).
    _cleEspace(token) {
      try { const k = localStorage.getItem("adjugo_espace_" + token); return k ? { "X-Adjugo-Espace": k } : {}; } catch (e) { return {}; }
    },
    async sharedClaimThenVault() {
      const v = this.sharedAo.vault;
      try {
        const cr = await this.api("POST", "/api/invite/" + this.sharedAo.token + "/claim", null, false, this._cleEspace(this.sharedAo.token)); v.needClaim = false; this.loadShared();
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
      if (!(await this.confirmer({ title: "Décliner l'invitation ?", ok: "Décliner l'invitation", danger: true,
        lines: ["Vous sortez du groupement : votre part ne figurera pas dans la réponse commune.", "Ce lien ne sera plus utilisable."] }))) return;
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
    // Rédaction, vague 4 : ce qui attend le partenaire dans le dossier de présentation commun (statuts seulement).
    sharedRedLine(r) {
      if (!r) return "";
      if (r.a_revalider) return r.a_revalider > 1 ? r.a_revalider + " parties à revalider" : "Partie à revalider";
      if (r.a_faire) return r.a_faire > 1 ? r.a_faire + " parties à rédiger" : "Partie à rédiger";
      // Envoyée, pas encore validée : le chef de file attend sa validation.
      if (r.a_valider) return r.a_valider > 1 ? r.a_valider + " parties à valider" : "Partie à valider";
      // Entretien chantier (vague 5) : des questions du chef de file attendent sa réponse.
      return r.questions > 1 ? r.questions + " questions sur le chantier" : "Question sur le chantier";
    },
    openSharedKey(ev, s) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.openShared(s); } },
    // Les critères ne s'affichent QUE dans la carte « Comment vous serez noté » (phrase du
    // règlement, poids tel qu'écrit) : le serveur n'envoie plus la liste brute, aux poids non contrôlés.
    sharedGrille(a) { const g = a && a.grille_notation; return (g && Array.isArray(g.criteres)) ? g : null; },
    sharedFact(a) { const L = { acheteur: "Acheteur", allotissement: "Parties (lots)", lieu: "Lieu", type_marche: "Type", date_limite: "Date limite", duree: "Durée" }; return Object.entries(L).filter(([k]) => a && a[k] != null && a[k] !== "" && (!Array.isArray(a[k]) || a[k].length)).map(([k, lab]) => ({ k: lab, v: Array.isArray(a[k]) ? a[k].map(x => (x && typeof x === "object") ? (x.critere || x.nom || x.label || "") + (x.ponderation ? " — " + x.ponderation : "") : x).join(" · ") : a[k] })); },
    // ── Notifications (activité des partenaires) ──
    async loadNotifs() { try { this.notifs = await this.api("GET", "/api/notifications") || []; } catch (e) {} },
    // La cloche (vague 2a, A1) : deux onglets, « À faire » (ce qui attend votre action, la même liste que le bloc de
    // l'accueil) et « Activité » (ce que font vos partenaires). Elle s'ouvre sur « À faire » s'il y a quelque chose
    // à faire ; l'activité n'est marquée vue qu'une fois son onglet affiché.
    toggleNotifs() {
      this.notifsOpen = !this.notifsOpen;
      if (this.notifsOpen) {
        this.loadNotifs();
        this.notifsVoir(this.aFaire().length ? "a_faire" : "activite");
      }
    },
    notifsVoir(onglet) {
      this.notifsOnglet = onglet;
      if (onglet !== "activite") return;
      const newest = this.notifs.length ? this.notifs[0].at : new Date().toISOString();
      this.notifsSeen = newest || new Date().toISOString();
      try { localStorage.setItem("adjugo_notifs_seen", this.notifsSeen); } catch (e) {}
    },
    // « À faire » : une seule liste (listeAFaire, en tête du fichier), pour la cloche et l'accueil.
    aFaire() {
      return listeAFaire({ shared: this.shared, recues: this.reseau.recues.list, projects: this.projects,
                           enCours: (this.grpDash && this.grpDash.en_cours) || [], expiring: this.expiring },
                         new Date().toISOString().slice(0, 10));
    },
    aFaireOuvrir(t) {
      this.notifsOpen = false;
      const c = (t && t.cible) || {};
      if (c.view === "sharedao") { const it = (this.shared || []).find(x => c.jeton ? x.token === c.jeton : x.project_id === c.partage); if (it) this.openShared(it); else this.go("shared"); return; }
      if (c.view === "aodetail") { this.openProjectById(c.projet); return; }
      if (c.view) this.go(c.view);
    },
    openNotif(n) {
      this.notifsOpen = false;
      const p = this.projects.find(x => x.id === n.project_id);
      if (p) this.openProject(p); else this.notify("Ce marché n'est plus accessible", "err");
    },
    openProjectById(id) { const p = this.projects.find(x => x.id === id); if (p) this.openProject(p); else this.notify("Marché introuvable", "err"); },
    inviteUrl(inv) { return window.location.origin + (inv.path || ("/invite/" + inv.token)); },
    inviteState(inv) {
      if (inv.revoked) return { label: "Révoqué", cls: "neutral" };
      if (this.inviteDeclined(inv)) return { label: "A décliné", cls: "declined" };
      if (inv.expires_at && new Date(inv.expires_at) < new Date()) return { label: "Expiré", cls: "a_etudier" };
      return { label: "Actif", cls: "go" };
    },
    async aoRevokeInvite(inv) {
      if (!(await this.confirmer({ title: "Révoquer ce lien ?", ok: "Révoquer le lien", danger: true,
        lines: ["Le partenaire perd l'accès à ce marché immédiatement."] }))) return;
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
    inviteSourceLabel(inv) { return ({ reseau_adjugo: "Réseau Adjugo", sirene: "Registre officiel" })[inv && inv.source] || ""; },
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
        "guest.capacites_updated": "Capacités mises à jour par le partenaire",
        "guest.contribution_reprise": "Références ou qualifications ajoutées par le partenaire à sa part", "guest.otp_request": "Code de vérification demandé", "guest.otp_verified": "Adresse email vérifiée",
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
    // « Ajouter un sous-traitant (DC4) » : SEUL ajout direct possible. Un partenaire du groupement
    // s'invite (aoGrpInvite) et n'entre dans les formulaires qu'après avoir accepté.
    async aoAttachSt(c) {
      try {
        await this.api("POST", "/api/cotraitants/project/" + this.ao.project.id,
          { company: c, role: "sous_traitant" });
        await this.aoLoadCotraitants(); this.loadCotraitants();
        this.notify(c.nom + " déclaré comme sous-traitant (DC4)");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async aoOptimizeGroup() {
      if (!this.ao.group) this.ao.group = { loading: false, data: null };
      this.ao.group.loading = true;
      try {
        this.ao.group.data = await this.api("POST", "/api/sourcing/groupement", { project_id: this.ao.project.id });
        if (this.ao.group.data && !this.ao.group.data.n_lots) this.notify("Marché en une seule partie (lot unique) : pas de répartition. Invitez un partenaire avec « Inviter un partenaire », en haut de la page.");
        else if (this.ao.group.data) this.notify("Répartition proposée : " + this.ao.group.data.n_lots + " " + this.plFr(this.ao.group.data.n_lots, "partie analysée", "parties analysées"));
      }
      catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.group.loading = false; }
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
        if (sirene && !((this.ao.grp.besoins.candidats || {}).sirene || []).length) this.notify("Aucune entreprise du registre officiel trouvée pour ces manques", "err");
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
      return [{ key: "rattaches", label: "Déjà ajoutés à ce marché", list: c.rattaches || [] },
              { key: "annuaire", label: "Mes partenaires", list: c.annuaire || [] },
              { key: "reseau", label: "Réseau Adjugo", list: c.reseau || [] },
              { key: "sirene", label: "Registre officiel des entreprises", list: c.sirene || [] }];
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
    // « Inviter {nom} » (composition, simulation, membres, accords) : la fenêtre d'invitation unique, dans le bon cas.
    //   - membre du réseau Adjugo (profil connu) : Adjugo envoie, l'adresse reste masquée ;
    //   - entreprise du registre officiel (SIRET, hors de « Mes partenaires ») : un lien à copier ;
    //   - sinon, partenaire connu : l'email de votre fiche « Mes partenaires » s'il y en a une, sinon à saisir.
    // Un candidat déjà ajouté au marché (link_id, ou membre de même nom de la composition retenue) porte l'invitation.
    aoGrpInvite(m) {
      m = m || {};
      const pid = m.kind === "reseau" ? this._grpProfileId(m) : "";
      if (pid) { this.rnInviteOpen({ profile_id: pid, name: m.name }); return; }
      const n = nomCle(m.name), plan = this.grpPlan();
      const pm = (!m.link_id && n && plan) ? (plan.members || []).find(x => x && x.link_id && nomCle(x.name) === n) : null;
      const lid = m.link_id || (pm && pm.link_id) || null;
      const fiche = this._ficheAnnuaire(m);
      if (!fiche && m.kind === "sirene" && String(m.siret || "").replace(/\D/g, "").length === 14) {
        this.rnInviteOpen({ siret: m.siret, name: m.name, city: m.city || "" }); return;
      }
      this.inviterOuvrir({ kind: "connu", name: (fiche && fiche.name) || m.name || "", email: (fiche && fiche.email) || "",
                           cotraitantId: fiche ? fiche.id : "", link_id: lid });
    },
    // La fiche « Mes partenaires » d'une entreprise proposée : par identifiant, puis SIRET, puis nom.
    _ficheAnnuaire(m) {
      if (!m) return null;
      const list = this.cotraitants || [], s = String(m.siret || "").replace(/\D/g, ""), n = nomCle(m.name);
      return (m.kind === "attached" || m.kind === "annuaire") && m.id ? (list.find(c => c.id === m.id) || null)
        : (s && list.find(c => String(c.siret || "").replace(/\D/g, "") === s)) || (n && list.find(c => nomCle(c.name) === n)) || null;
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
      if (!(await this.confirmer({ title: "Annuler la composition retenue ?", ok: "Annuler la composition", annuler: "Garder la composition",
        lines: ["Vous revenez au verdict seul.", "Les entreprises déjà ajoutées au marché restent dans « Membres et sous-traitants »."] }))) return;
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
    openReseau(tab) {
      if (tab === "recues") { this.go("shared"); return; }   // vague 2a (A2) : Mes marchés, filtre « Où je suis partenaire »
      this.reseau.tab = tab || "profil"; this.go("reseau");
    },
    rnGo(tab) {
      if (tab === "recues") { this.go("shared"); return; }
      const r = this.reseau; r.tab = tab;
      if (tab === "profil" && !r.p.loaded) this.rnLoadProfil();
      if (tab === "annuaire") { if (!r.p.loaded) this.rnLoadProfil(true); if (!r.an.loaded) this.rnLoadAnnuaire(1); }
      if (tab === "historique") this.rnLoadHistorique();
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
    rnRoleLabel(r) { return ({ cotraitant: "Partenaire du groupement", sous_traitant: "Sous-traitant", mandataire: "Chef de file" })[r] || r; },
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
    essaiCarteClose() { if (this.offre402) this.offre402 = null; else this.essaiAlerteOff = true; },
    essaiCarteGo() { this.offre402 = null; this.go("billing"); },
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
      if (lot !== "" && lot != null && !(Number(lot) > 0)) { this._rnErr("Plus grosse partie acceptée : un montant HT positif.", "form"); return false; }
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
        const res = await this.api("POST", "/api/invite/" + encodeURIComponent(inv.token) + "/claim", null, false, this._cleEspace(inv.token));
        if (res && res.suggest_profile) this._rnSuggest(res.suggest_profile);
        inv.statut = "acceptee"; inv.statut_label = "Acceptée";
        r.live = "Invitation acceptée : le dossier est dans Mes marchés, filtre « Où je suis partenaire ».";
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
      pm.loading = true; pm.error = ""; pm.live = "Recherche des partenaires, partie par partie…";
      try {
        const d = await this.api("GET", "/api/projects/" + pid + "/partner-matches");
        if (!this.ao.project || this.ao.project.id !== pid) return;
        pm.d = d; pm.loaded = true; pm.live = this._pmSummary(d);
      } catch (e) { pm.error = (e && e.message) || "Recherche de partenaires momentanément indisponible."; pm.live = pm.error; }
      finally { pm.loading = false; }
    },
    _pmSummary(d) {
      const lots = (d && d.lots) || [];
      if (!lots.length) return "Aucune partie à compléter d'après le dossier.";
      const n = lots.reduce((s, l) => s + (l.reseau || []).length + (l.mes_partenaires || []).length + (l.sirene || []).length, 0);
      return lots.length + " " + this.plFr(lots.length, "partie à compléter", "parties à compléter") + " · " + n + " " + this.plFr(n, "entreprise proposée", "entreprises proposées") + ".";
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
          pm.live = partieLot(l.num) + " : " + n + " " + this.plFr(n, "entreprise proposée", "entreprises proposées") + ".";
        }
      } catch (e) { this.notify(e.message, "err"); }
      finally { pm.lotBusy = ""; }
    },
    // « Partie (lot n) » à l'écran (décision 10) : la fonction en tête de ce fichier, pour les gabarits.
    partieLot(x, intitule, minuscule) { return partieLot(x, intitule, minuscule); },
    pmLotTitle(l) { return l && l.num ? partieLot(l.num, l.label) : (l && l.label) || ""; },
    // Valeur proposée pour la « Part » d'un invité : une DONNÉE reprise dans la convention et les formulaires officiels
    // remis au client, qui gardent le mot du règlement (« Lot 2 — Électricité ») ; l'écran, lui, dit « partie ».
    pmLotPart(l) { return l && l.num ? "Lot " + l.num + " — " + l.label : (l && (l.metier_label || l.label)) || ""; },
    pmLotId(l) { return "pml-" + String((l && (l.num || l.metier)) || "x").replace(/[^A-Za-z0-9_-]/g, ""); },
    // « Simuler le groupement » depuis une carte : ajoute l'entreprise à la simulation de la carte
    // « Répondre à plusieurs ? » et lance le calcul (le SEUL pourcentage affiché).
    async aoPmSimulate(c) {
      const m = c.profile_id ? { kind: "reseau", profile_id: c.profile_id, name: c.name, city: c.city || "" }
        : c.cotraitant_id ? { kind: "annuaire", id: c.cotraitant_id, name: c.name, city: c.city || "" }
        : { kind: "sirene", siret: c.siret, name: c.name, city: c.city || "" };
      if (!this.isCandSelected(m)) {
        if (this.ao.grp.selected.length >= 4) { this.notify("4 partenaires au maximum par simulation : retirez-en un dans « Simuler avec ».", "err"); this.rnScrollTo("grpSim", true); return; }
        this.ao.grp.selected.push(m);
      }
      await this.aoGrpSimulate();
      this.rnScrollTo("grpSim", true);
    },

    // ── La fenêtre d'invitation unique (vague 3 ; réorganisation, vague 2a, A2) ──
    // Réseau : Adjugo envoie l'invitation, l'adresse du partenaire n'est JAMAIS affichée au chef de file.
    // Registre (hors réseau) : identité relue côté serveur, aucun email, un lien à transmettre.
    // Connu : Adjugo envoie l'invitation à l'email que VOUS donnez (votre fiche « Mes partenaires ») ; sans email, un lien.
    // Ouverte sans entreprise : « choix » (qui invitez-vous ?).
    _rinvBase(projectId, pickProject) {
      return { kind: "choix", card: null, name: "", profile_id: "", siret: "", siretSaisi: false, email: "", cotraitantId: "",
               link_id: null, depuisChoix: false, projectId, pickProject, roles: ["cotraitant", "sous_traitant"], role: "cotraitant",
               noRole: false, lot: "", can_view_docs: true, can_contribute: true, expires_days: 30,
               busy: false, err: "", errCode: "", errProfile: "", errStatus: 0, url: "", done: "" };
    },
    // Message d'erreur ou lien créé : en bas de la fenêtre, qui peut défiler ; on l'amène à l'écran.
    _rinvMontrer() {
      this.$nextTick(() => { const el = document.querySelector(".rinv-modal .modal-b .conv-err, .rinv-modal .modal-b .rn-done"); if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" }); });
    },
    _rinvFocusPremier() {
      this.$nextTick(() => { const el = document.querySelector(".rinv-modal .modal-b select, .rinv-modal .modal-b input, .rinv-modal .modal-b .rinv-c") || document.querySelector(".rinv-modal .x"); if (el && el.focus) el.focus(); });
    },
    rnInviteOpen(card, opts) {
      opts = opts || {}; if (!card) return;
      const kind = card.profile_id ? "reseau" : "sirene";
      const declared = Array.isArray(card.roles_acceptes) && card.roles_acceptes.length > 0;   // [] = tous les rôles (serveur)
      const ok = declared ? card.roles_acceptes.map(r => (r && r.value) || r).filter(r => r === "cotraitant" || r === "sous_traitant") : ["cotraitant", "sous_traitant"];
      const roles = kind === "sirene" || !declared ? ["cotraitant", "sous_traitant"] : ok;
      const inAo = this.view === "aodetail" && this.ao.project;
      this._rinvFocus = opts.focusBack || document.activeElement;
      this.rinv = Object.assign(this._rinvBase(opts.projectId || (inAo ? this.ao.project.id : ""), !opts.projectId && !inAo), {
        kind, card, name: card.name || "", profile_id: card.profile_id || "", siret: card.siret || "",
        roles, role: roles[0] || "cotraitant", noRole: kind === "reseau" && declared && !ok.length, lot: opts.lot || "",
      });
      this._rinvFocusPremier();
    },
    // Sans carte (bouton « Inviter un partenaire », « Inviter sur un marché » d'une fiche de Mes partenaires) : le cas
    // « choix » ou « connu », pré-rempli.
    inviterOuvrir(opts) {
      opts = opts || {};
      const inAo = this.view === "aodetail" && this.ao.project;
      this._rinvFocus = opts.focusBack || document.activeElement;
      const v = this._rinvBase(opts.projectId || (inAo ? this.ao.project.id : ""), !opts.projectId && !inAo);
      this.rinv = Object.assign(v, { kind: opts.kind === "connu" ? "connu" : "choix", name: opts.name || "", email: opts.email || "",
                                     cotraitantId: opts.cotraitantId || "", link_id: opts.link_id || null });
      this._rinvFocusPremier();
    },
    rinvChoisir(kind) {
      const v = this.rinv; if (!v) return;
      Object.assign(v, { kind, depuisChoix: kind !== "choix", siretSaisi: kind === "sirene", profile_id: "", siret: "", card: null,
                         roles: ["cotraitant", "sous_traitant"], role: "cotraitant", noRole: false, err: "", errCode: "", errProfile: "", errStatus: 0 });
      this._rinvFocusPremier();
    },
    rinvTitre() {
      const v = this.rinv; if (!v) return "";
      if (v.kind === "choix") return "Inviter un partenaire";
      if (v.name) return "Inviter " + v.name;
      return ({ reseau: "Inviter une entreprise du réseau Adjugo", sirene: "Inviter une entreprise du registre officiel" })[v.kind] || "Inviter un partenaire que je connais";
    },
    rinvBouton() {
      const v = this.rinv || {};
      if (v.kind === "reseau") return "Envoyer l'invitation";
      if (v.kind === "connu" && String(v.email || "").trim()) return "Envoyer l'invitation";
      return "Créer le lien";
    },
    rinvMesPartenaires() { return (this.cotraitants || []).filter(c => c && c.name).slice().sort((a, b) => String(a.name).localeCompare(String(b.name), "fr")); },
    rinvDepuisAnnuaire() {
      const v = this.rinv; if (!v) return;
      const c = (this.cotraitants || []).find(x => String(x.id) === String(v.cotraitantId));
      if (c) { v.name = c.name || ""; v.email = (c.email || "").trim(); }
    },
    // « Chercher dans Qui me complète ? » : la fenêtre se ferme, la page va au composant (et lance la recherche).
    rinvVersQuiMeComplete(zone) {
      this.rinvClose(true);
      if (this.view !== "aodetail") return;
      if (zone) { this.aoChercherEntreprise(); return; }
      this.rnScrollTo("pmCard");
      if (this.ao.project && this.ao.project.ai_analysis && !this.ao.pm.loaded) this.aoPmLoad();
    },
    // Registre indisponible : inviter la même entreprise par son nom, comme un partenaire connu (lien à copier).
    rinvSansRegistre() {
      const v = this.rinv; if (!v) return;
      Object.assign(v, { kind: "connu", siretSaisi: false, siret: "", err: "", errCode: "", errStatus: 0, depuisChoix: true });
      this._rinvFocusPremier();
    },
    rinvClose(sansFocus) {
      this.rinv = null;
      const el = this._rinvFocus; this._rinvFocus = null;
      if (!sansFocus && el && el.focus && document.body.contains(el)) this.$nextTick(() => el.focus());
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
        (l.mes_partenaires || []).forEach(c => { if (v.kind === "connu" && v.name && nomCle(c.name) === nomCle(v.name)) c.deja_invite = true; });
      });
    },
    async rinvSend() {
      const v = this.rinv; if (!v || v.busy || v.done || v.kind === "choix") return;
      const refus = (m) => { v.err = m; v.errCode = ""; this._rinvMontrer(); };
      if (!v.projectId) { refus("Choisissez le marché sur lequel inviter ce partenaire."); return; }
      if (v.noRole) return;
      if (v.kind === "connu" && !String(v.name || "").trim()) { refus("Indiquez le nom de l'entreprise à inviter."); return; }
      const email = String(v.email || "").trim();
      if (v.kind === "connu" && email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { refus("Cette adresse email n'est pas valide."); return; }
      if (v.kind === "sirene" && String(v.siret || "").replace(/\D/g, "").length !== 14) { refus("Un SIRET à 14 chiffres est requis."); return; }
      const pid = v.projectId, body = { role: v.role, lot: String(v.lot || "").trim().slice(0, 255), can_view_docs: !!v.can_view_docs, expires_days: 30 };
      v.busy = true; v.err = ""; v.errCode = ""; v.errProfile = ""; v.errStatus = 0;
      try {
        if (v.kind === "reseau") {
          const r = await this.api("POST", "/api/projects/" + pid + "/reseau/invitations", Object.assign({ profile_id: v.profile_id }, body));
          this._rnMarkInvited(v);
          this.notify((r && r.message) || "Invitation envoyée par Adjugo.");
          this.rinvClose();
        } else if (v.kind === "connu") {
          const inv = await this.api("POST", "/api/projects/" + pid + "/invites", Object.assign({
            company_name: String(v.name).trim().slice(0, 255), recipient: email, role: v.role, can_view_docs: !!v.can_view_docs,
            can_contribute: !!v.can_contribute, expires_days: Number(v.expires_days) || 0 }, v.link_id ? { link_id: v.link_id } : {}));
          v.url = (inv && inv.path) ? this.inviteUrl(inv) : ((inv && inv.url) || "");
          v.done = inv && inv.emailed ? "Invitation envoyée par Adjugo à " + email + ". Le lien reste ici, si l'email n'arrive pas."
            : (email ? "Lien créé. L'email n'a pas pu partir pour le moment : copiez le lien et envoyez-le."
                     : "Lien créé : copiez-le et envoyez-le à l'entreprise.");
          if (v.url) this.copyInvite(v.url, true);
          this._rinvMontrer();
        } else {
          const r = await this.api("POST", "/api/projects/" + pid + "/reseau/invitations-sirene", Object.assign({ siret: String(v.siret).replace(/\D/g, "") }, body));
          const inv = (r && r.invitation) || {};
          v.url = inv.path ? this.inviteUrl(inv) : ((r && r.url) || "");
          if (!v.name && inv.company_name) v.name = inv.company_name;
          v.done = (r && r.message) || "Lien créé : transmettez-le à l'entreprise.";
          this._rnMarkInvited(v);
          if (v.url) this.copyInvite(v.url, true);
          this._rinvMontrer();
        }
        if (this.view === "aodetail" && this.ao.project && this.ao.project.id === pid) { this.aoLoadInvites(); this.aoLoadCotraitants(); this.aoLoadConsortium(); this.aoGrpReloadState(); }
        this._marcheEnPreparation(pid);    // inviter est un geste de Préparer (vague 2a, décision 7)
        this.loadCotraitants(); this.loadConsortiums();
      } catch (e) {
        v.err = (e && e.message) || "Invitation impossible pour l'instant."; v.errCode = (e && e.code) || ""; v.errProfile = (e && e.profile_id) || ""; v.errStatus = (e && e.status) || 0;
        if (v.errCode === "deja_invite") this._rnMarkInvited(v);
        this._rinvMontrer();
      } finally { if (this.rinv === v) v.busy = false; }
    },
    // 409 « sur_le_reseau » : l'entreprise SIRENE est sur le réseau → on l'invite via sa fiche (Adjugo transmet).
    rinvViaReseau() {
      const v = this.rinv; if (!v || !v.errProfile) return;
      Object.assign(v, { kind: "reseau", profile_id: v.errProfile, siretSaisi: false, roles: ["cotraitant", "sous_traitant"], noRole: false, err: "", errCode: "", errProfile: "", errStatus: 0, url: "", done: "" });
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
    // Total prévisionnel de l'offre commune (avant qu'elle soit figée en générant la convention).
    freezeTotal() {
      const o = this.ao.share.consortium && this.ao.share.consortium.offre;
      return o && o.total_ht_estime != null ? o.total_ht_estime : null;
    },
    async aoUnfreezeOffer() {
      const cv = this.ao.conv.d, generated = !!(cv && (cv.status === "a_signer" || cv.status === "signee"));
      const lignes = ["Les partenaires ne verront plus le total tant qu'elle n'est pas figée de nouveau."];
      if (generated) lignes.push({ t: "La convention de groupement sera à revalider : les accords déjà enregistrés ne comptent plus et il faudra la régénérer.", warn: true });
      if (!(await this.confirmer({ title: "Défiger l'offre commune ?", ok: "Défiger l'offre", lines: lignes }))) return;
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
      lines.push(d.status === "perimee" ? { t: "Les accords donnés sur l'ancienne version ne comptent plus : chaque membre devra donner son accord sur la nouvelle." }
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
    // Vague 2a (A2) : « Prêt à déposer » pour TOUS les marchés. Le serveur choisit le calcul : à plusieurs (parts,
    // attestations des membres, convention, formulaires après elle) ou seul (prix, dossier de présentation, formulaires,
    // pièces, attestations) — jamais un faux manque de groupement.
    depotShown() { return !!(this.ao.project && this.ao.project.id); },
    depotPourGroupement() { const p = this.depotPret(); return !!(p && p.pour !== "seul"); },
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
    depotCount(p) { const n = Number(p && p.n_ok) || 0; return n + " " + (n > 1 ? "contrôles" : "contrôle") + " sur " + (Number(p && p.n_total) || 0); },
    _convPretGroup(m) { return /^part de/i.test(m) ? "parts_soumises" : /^formulaire/i.test(m) ? "cerfa_generes" : /^convention/i.test(m) ? "convention_signee" : "attestations_ok"; },
    convPretChecks() {
      const p = this.depotPret(); if (!p) return [];
      const ch = p.checks || {}, lib = p.libelles || {}, man = (p.manques || []).map(m => String(m || "")).filter(Boolean);
      const par = p.manques_par_controle && typeof p.manques_par_controle === "object" ? p.manques_par_controle : null;
      const sous = k => par ? (par[k] || []).map(m => String(m || "")).filter(Boolean) : man.filter(m => this._convPretGroup(m) === k);
      if (p.pour === "seul") {
        // Entreprise seule (vague 2a, A2) : l'action qui règle chaque contrôle, sur cette page.
        return [
          { key: "prix", label: "Votre prix estimé", cta: "Estimer mon prix", icon: "calculator", action: () => this.rnScrollTo("prixCard") },
          { key: "dossier", label: "Dossier de présentation prêt, sans passage à compléter", cta: "Ouvrir l'atelier", icon: "file-pen-line", action: () => this.atlOpen() },
          { key: "formulaires", label: "Formulaires officiels préparés", cta: "Préparer mes documents", icon: "stamp", action: () => this.aoGenerate() },
          { key: "pieces", label: "Pièces demandées réunies", cta: "Voir les pièces", icon: "list-checks", action: () => this.rnScrollTo("piecesCard") },
          { key: "attestations", label: "Vos attestations valides à la date limite", cta: "Mes pièces", icon: "folder-lock", action: () => this.go("documents") },
        ].filter(k => k.key in ch).map(k => Object.assign(k, { label: lib[k.key] || k.label, ok: !!ch[k.key], manques: sous(k.key) }));
      }
      const cv = this.ao.conv.d && this.ao.conv.d.status, generated = cv === "a_signer" || cv === "signee";
      const relance = this.aoPendingRelancables().length > 0;
      const conv = !cv || cv === "aucune" || cv === "draft"
        ? { cta: "Préparer la convention", icon: "scroll-text", action: () => this.aoConvScroll("convFoot") }
        : cv === "perimee" ? { cta: "Régénérer la convention", icon: "refresh-cw", action: () => this.aoConvAskRegenerate() }
        : { cta: "Voir les accords", icon: "users-round", action: () => this.aoConvScroll("convAccords") };
      return [
        { key: "parts_soumises", label: "Parts de tous les partenaires soumises, avec leur prix de vente", cta: relance ? "Relancer les partenaires" : "Voir les parts", icon: relance ? "send" : "users-round", action: () => relance ? this.aoRelanceRetardataires() : this.aoConvShowCoffre() },
        { key: "attestations_ok", label: "Attestations de tous les membres valides à la date limite", cta: "Voir les attestations", icon: "folder-lock", action: () => this.aoConvShowCoffre() },
        Object.assign({ key: "convention_signee", label: "Convention validée par tous les membres" }, conv),
        generated ? { key: "cerfa_generes", label: "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention", cta: "Préparer mes documents", icon: "file-text", action: () => this.aoConvPrepareDocs() }
                  : { key: "cerfa_generes", label: "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention", wait: "Après la convention" },
      ].filter(k => k.key in ch).map(k => Object.assign(k, { label: lib[k.key] || k.label, ok: !!ch[k.key], manques: sous(k.key) }));
    },
    convPretRest() {   // manques qui ne se rangent sous aucun contrôle encore à faire (jamais masqués)
      const p = this.depotPret(); if (!p) return [];
      const open = this.convPretChecks().filter(k => !k.ok).map(k => k.key);
      if (p.manques_par_controle && typeof p.manques_par_controle === "object") {
        const ranges = new Set(open.reduce((a, k) => a.concat(p.manques_par_controle[k] || []), []).map(String));
        return (p.manques || []).map(m => String(m || "")).filter(m => m && !ranges.has(m));
      }
      return (p.manques || []).map(m => String(m || "")).filter(m => m && !open.includes(this._convPretGroup(m)));
    },
    // « Marquer déposé » : avertir, pas bloquer. Dossier complet → confirmation simple ; sinon la
    // liste de ce qui manque et « Marquer déposé quand même » (le chef de file a pu déposer hors d'Adjugo).
    aoDepotAsk() {
      const p = this.depotPret() || {};
      if (p.pret) {
        this._convAsk({ title: "Marquer le dossier comme déposé ?", ok: "Marquer déposé", run: () => this.aoDepotMark(false),
          lines: this.depotPourGroupement()
            ? ["Le marché passe au statut « Déposé ».", "Chaque partenaire le verra dans son journal.",
               "Les relances automatiques s'arrêtent pour ce marché.", "En cas d'erreur, vous pourrez retirer ce marquage."]
            : ["Le marché passe au statut « Déposé ».", "En cas d'erreur, vous pourrez retirer ce marquage."] });
        return;
      }
      this._depotAskIncomplete(p.manques || [], (Number(p.n_total) || 4) - (Number(p.n_ok) || 0));
    },
    _depotAskIncomplete(manques, n) {
      const list = (manques || []).map(m => String(m || "")).filter(Boolean);
      const lines = [{ t: (n > 0 ? n + (n > 1 ? " contrôles avant dépôt ne sont pas réglés." : " contrôle avant dépôt n'est pas réglé.") : "Le dossier n'est pas complet.") + " Le marquer déposé quand même ? Vous avez peut-être déposé hors d'Adjugo.", warn: true }];
      list.slice(0, 5).forEach(m => lines.push({ t: m }));
      if (list.length > 5) lines.push({ t: "et " + (list.length - 5) + " autre" + (list.length - 5 > 1 ? "s" : "") });
      if (this.depotPourGroupement()) lines.push({ t: "Chaque partenaire verra le marquage dans son journal ; les relances automatiques s'arrêtent." });
      this._convAsk({ title: "Le dossier n'est pas complet", lines, ok: "Marquer déposé quand même", run: () => this.aoDepotMark(true) });
    },
    async aoDepotMark(confirmer) {
      const pid = this.ao.project && this.ao.project.id, dp = this.ao.depot; if (!pid || dp.busy) return;
      dp.busy = "deposer"; dp.err = "";
      try {
        const r = await this.api("POST", "/api/projects/" + pid + "/groupement/deposer", { confirmer: !!confirmer });
        this._listeSuitStatut(pid, r.status);    // Mes marchés suit (relecture de la vague 2a)
        if (!this.ao.project || this.ao.project.id !== pid) return;
        if (r.status) this.ao.project.status = r.status;
        if (r.state) this._convMergeState(r.state);
        dp.d = Object.assign({}, dp.d || {}, { depose: true, status: r.status || "depose" }, r.pret ? { pret: r.pret } : {});
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
        lines: this.depotPourGroupement()
          ? ["À faire seulement si le dossier n'a pas été déposé : le marché retrouve son statut d'avant.",
             "Le retrait est inscrit dans le journal de chaque partenaire."]
          : ["À faire seulement si le dossier n'a pas été déposé : le marché retrouve son statut d'avant."] });
    },
    async aoDepotUnmark() {
      const pid = this.ao.project && this.ao.project.id, dp = this.ao.depot; if (!pid || dp.busy) return;
      dp.busy = "annuler"; dp.err = "";
      try {
        const r = await this.api("DELETE", "/api/projects/" + pid + "/groupement/deposer");
        this._listeSuitStatut(pid, r.status);
        if (!this.ao.project || this.ao.project.id !== pid) return;
        if (r.status) this.ao.project.status = r.status;
        if (r.state) this.ao.grp.state = r.state;
        dp.d = Object.assign({}, dp.d || {}, { depose: false, status: r.status });
        dp.live = "Marquage « déposé » retiré."; this.notify(dp.live);
        dp.busy = ""; await this.aoDepotLoad();
      } catch (e) { dp.err = e.message || "Impossible de retirer le marquage pour le moment."; }
      finally { dp.busy = ""; }
    },
    // Fenêtre de confirmation de l'application (fenetre-confirmation) : dit ce que l'action fait AVANT de la faire.
    // Elle remplace les confirm() et prompt() du navigateur (vague 2a, A3). Dialogue modal nommé et décrit, focus
    // gardé dedans (Tab), Échap ferme, le focus revient où il était ; focus sur « Annuler », ou sur le premier champ.
    // cfg : title ; lines (texte, ou { t, warn }) ; ok, annuler (libellés) ; autre (un second choix) ; danger (action
    // destructrice) ; fields [{ key, label, value, type, requis, attendu, motif, max, inputmode, autocomplete,
    // placeholder, aide }] ; run (rappel, appelé avec les valeurs). `demander` rend une promesse : les valeurs (un
    // objet, vide sans champ) si l'on confirme, { autre: true } pour le second choix, null si l'on annule.
    _convAsk(cfg) { this._cdlgOuvrir(cfg || {}); },
    demander(cfg) { return new Promise(resolve => this._cdlgOuvrir(Object.assign({}, cfg || {}, { resolve }))); },
    async confirmer(cfg) { const r = await this.demander(cfg); return !!r && !r.autre; },
    _cdlgOuvrir(cfg) {
      const avant = this.cdlg;
      if (avant) { this.cdlg = null; if (avant.resolve) avant.resolve(null); }   // une seule fenêtre à la fois
      else this._cdlgFocus = document.activeElement;
      const lines = (cfg.lines || []).filter(Boolean).map(l => typeof l === "string" ? { t: l } : l);
      const fields = (cfg.fields || []).map(x => Object.assign({ value: "" }, x));
      this.cdlg = Object.assign({ ok: "Confirmer", annuler: "Annuler" }, cfg, { lines, fields, ecran: this._cdlgEcran() });
      this.$nextTick(() => {
        const champ = fields.length ? document.getElementById("cdlg-" + fields[0].key) : null;
        const b = champ || this.$refs.cdlgCancel; if (b && b.focus) b.focus();
      });
    },
    _cdlgFermer() {
      this.cdlg = null;
      const el = this._cdlgFocus; this._cdlgFocus = null;
      if (el && el.focus && document.body.contains(el)) this.$nextTick(() => el.focus());
    },
    cdlgClose() { const d = this.cdlg; this._cdlgFermer(); if (d && d.resolve) d.resolve(null); },
    // L'écran d'une confirmation (vue, marché ouvert, dossier partagé ouvert) : elle n'agit que sur l'écran où elle a
    // été ouverte. Si l'écran a changé sous elle, confirmer vaut « Annuler » (relecture de la vague 2a).
    _cdlgEcran() { return [this.view, (this.ao && this.ao.project && this.ao.project.id) || "", (this.sharedAo && this.sharedAo.token) || ""].join("|"); },
    cdlgValide() { return !!this.cdlg && champsValides(this.cdlg.fields); },
    async cdlgRun() {
      const d = this.cdlg; if (!d || !champsValides(d.fields)) return;
      if (d.ecran && d.ecran !== this._cdlgEcran()) { this.cdlgClose(); return; }
      const vals = {};    // un mot de passe est rendu tel quel (ses espaces comptent), le reste sans espaces autour
      (d.fields || []).forEach(x => { const s = String(x.value == null ? "" : x.value); vals[x.key] = x.type === "password" ? s : s.trim(); });
      this._cdlgFermer();
      if (d.resolve) d.resolve(vals);
      if (d.run) await d.run(vals);
    },
    cdlgAutre() { const d = this.cdlg; if (!d) return; if (d.ecran && d.ecran !== this._cdlgEcran()) { this.cdlgClose(); return; } this._cdlgFermer(); if (d.resolve) d.resolve({ autre: true }); },
    // Le focus reste dans la fenêtre : Tab sur le dernier élément revient au premier, Maj+Tab sur le premier au dernier.
    cdlgTab(e) {
      const box = this.$refs.cdlgBox; if (!box) return;
      const els = Array.from(box.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])"));
      if (!els.length) return;
      const first = els[0], last = els[els.length - 1], cur = document.activeElement;
      if (e.shiftKey && (cur === first || !box.contains(cur))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (cur === last || !box.contains(cur))) { e.preventDefault(); first.focus(); }
    },
    roleLabel(r) { return ({ mandataire: "Chef de file", cotraitant: "Partenaire", sous_traitant: "Sous-traitant" })[r] || r; },
    checklistLabel(s) { return ({ ok: "Disponible", manquant: "Manquant", expire: "Expiré", generable: "Généré auto", a_completer: "À terminer" })[s] || s; },
    // Dossiers du coffre : l'identifiant « Mémoire technique » reste en base, l'écran dit « Dossier de présentation ».
    // Nom affiché d'un dossier rangé : les clés de rangement (app/services/dossier.py, FOLDERS) ne changent pas
    // chez les clients, seul leur nom à l'écran (DOSSIERS_AFFICHES, en tête de ce fichier).
    folderLabel(f) { return nomDossier(f); },
    // Copie le texte affiché d'un bloc (ex. note d'information aux salariés).
    async copyRefText(ref, ok) {
      const el = this.$refs[ref]; const txt = el ? (el.innerText || "").trim() : "";
      if (!txt) return;
      try { await navigator.clipboard.writeText(txt); this.notify(ok || "Texte copié"); }
      catch (e) { this.notify("Copie impossible : sélectionnez le texte et copiez-le à la main", "err"); }
    },
    aoStAttached(c) { return this.ao.cotraitants.some(x => x.siret && x.siret === c.siret && x.role === "sous_traitant"); },
    async aoDetachSt(link_id) {
      try { await this.api("DELETE", "/api/cotraitants/project/" + this.ao.project.id + "/" + link_id); this.aoLoadCotraitants(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    aoBack() {
      if (this._retourHistorique()) return;           // vague 2a : l'écran d'avant, comme le bouton du navigateur
      this.view = this.ao.back || "pipeline"; this._ecranOuvert(this.view); this.loadProjects();
    },
    // ── Page du marché en 4 étapes (réorganisation, vague 1, 1.5) : la barre, les tâches à plusieurs, l'invitation ──
    aoEtape() { const st = this.ao.grp.state; return etapeDuMarche(this.ao.project && this.ao.project.status, this.aoDceAvailable(), st && st.etape); },
    aoTachesPlusieurs() { return tachesPlusieurs(this.ao.grp.state); },
    // La barre et ses statuts dérivés (vague 2a, décision 7) : Terminé · En cours · À faire, étape par étape.
    aoBarre() { const st = this.ao.grp.state; return barreDuMarche(this.ao.project && this.ao.project.status, this.aoDceAvailable(), st && st.etape); },
    aoBarreEtat(k) { return this.aoBarre().find(x => x.k === k) || {}; },
    // Étape Décider (vague 2a) : « Préparer seul », « Préparer à plusieurs » (puis « Inviter un partenaire »),
    // « Écarter » (avec confirmation, réversible : « Remettre ») ; le statut suit l'axe, jamais en arrière.
    aoDecisionVisible() { const s = this.ao.project && this.ao.project.status; return ["depose", "gagne", "perdu"].indexOf(s || "nouveau") < 0; },
    async aoDecider(choix) {
      const p = this.ao.project; if (!p) return;
      if (choix === "ecarter") {
        this._convAsk({ title: "Écarter ce marché ?", ok: "Écarter",
          lines: ["Il passe à l'étape « Abandonné » : plus de rappel de date limite ni de relance.",
                  "Vous pouvez le remettre à tout moment depuis cette page."],
          run: () => this._aoChangerStatut("abandonne", "Marché écarté", DEPARTS_GESTE.ecarter) });
        return;
      }
      const cible = statutApresDecision(p.status, choix);
      if (cible) await this._aoChangerStatut(cible, choix === "remettre" ? "Marché remis : Repéré" : "Statut : Décidé", DEPARTS_GESTE[choix]);
      if (choix === "plusieurs") this.aoInviter();
      else if (choix === "seul") this.rnScrollTo("etPreparer");
    },
    // `depuis` (relecture de la vague 2a) : les étapes d'où part le geste (DEPARTS_GESTE) ; le serveur ne change
    // l'étape que si le marché y est encore et renvoie l'étape réelle, que l'écran reprend (page et liste).
    async _aoChangerStatut(cible, message, depuis) {
      const p = this.ao.project; if (!p || !cible || p.status === cible) return;
      const avant = p.status, pid = p.id;
      p.status = cible;
      try {
        const r = await this.api("PUT", "/api/projects/" + pid, depuis ? { status: cible, si_statut: depuis } : { status: cible });
        const reel = (r && r.status) || cible;
        p.status = reel;
        const l = (this.projects || []).find(x => x.id === pid); if (l) l.status = reel;
        if (reel !== cible) { if (message) this.notify("Ce marché a changé d'étape entre-temps : il est à l'étape « " + libelleStatut(reel) + " ».", "err"); }
        else if (message) this.notify(message);
        this.loadStats(); this.ao.cnTick = (this.ao.cnTick || 0) + 1;
      } catch (e) { p.status = avant; this.notify(e.message, "err"); }
    },
    // Un geste de Préparer fait passer le marché « En préparation » (sans message : le statut change sous vos yeux).
    aoAvancer() { const p = this.ao.project, c = p && statutEnPreparation(p.status); if (c) this._aoChangerStatut(c, "", DEPARTS_GESTE.preparer); },
    // Réunion de la vague 2a : la fenêtre d'invitation unique (A2) sert aussi hors de la page du marché (« Inviter sur un
    // marché » de Mes partenaires) ; l'invitation y fait avancer le marché choisi comme sur sa page (A1). La liste peut
    // être plus ancienne que le marché (déposé depuis) : le serveur ne le fait avancer que s'il est encore Repéré ou
    // Décidé, et la liste reprend l'étape qu'il renvoie (relecture de la vague 2a).
    async _marcheEnPreparation(pid) {
      if (this.view === "aodetail" && this.ao.project && this.ao.project.id === pid) { this.aoAvancer(); return; }
      const p = (this.projects || []).find(x => x && x.id === pid), c = p && statutEnPreparation(p.status);
      if (!c) return;
      try {
        const r = await this.api("PUT", "/api/projects/" + p.id, { status: c, si_statut: DEPARTS_GESTE.preparer });
        p.status = (r && r.status) || c; this.loadStats();
      } catch (e) {}
    },
    aoTacheVoir(t) {
      if (t.voir === "parts") { this.aoConvShowCoffre(); return; }
      this.rnScrollTo(t.voir === "convention" && this.convVisible() ? "convCard" : "reseauCard");
    },
    // « Inviter un partenaire » (décision 0) : la fenêtre d'invitation unique (vague 2a, A2), ouverte sur « qui invitez-vous ? ».
    aoInviter() { if (this.ao.project) this.inviterOuvrir({ projectId: this.ao.project.id }); },
    // « Chercher une entreprise » (Membres et sous-traitants) : la recherche de « Qui me complète ? », dans la zone.
    aoChercherEntreprise() {
      if (!this.ao.st.dept) this.ao.st.dept = (this.aoDetails().lieu_execution || "").replace(/\D/g, "").slice(0, 2);
      this.rnScrollTo("pmZone");
      this.$nextTick(() => { const el = this.$refs.pmZoneMetier; const x = Array.isArray(el) ? el[0] : el; if (x && x.focus) x.focus({ preventScroll: true }); });
    },
    // « Chercher autrement » sur une partie : la recherche dans la zone, pré-remplie avec son métier et son département.
    aoPmZone(l) {
      if (l) { this.ao.st.trade = l.metier_label || l.label || this.ao.st.trade; if (l.departement) this.ao.st.dept = String(l.departement); }
      this.aoChercherEntreprise();
    },
    // Une entreprise de « Mes partenaires » proposée par « Qui me complète ? » : la fenêtre, cas « partenaire connu ».
    aoPmInviterConnu(m) {
      if (!m) return;
      this.inviterOuvrir({ kind: "connu", name: m.name || "", email: m.email || "", cotraitantId: m.cotraitant_id || "" });
    },
    // Déposer : « Prêt à déposer » porte déjà « Exporter le dossier complet » quand tout est prêt (pas de doublon).
    aoExportDansPret() { return this.depotShown() && !this.depotIsDeposed() && !!(this.depotPret() && this.depotPret().pret); },
    aoDetails() { return (this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.details) || {}; },
    aoSource() { return (this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.source) || null; },
    aoContact() { const c = this.aoDetails().contact; return (c && (c.nom || c.email)) ? c : null; },
    aoDceAvailable() { return !!(this.ao.project && this.ao.project.ai_analysis && this.ao.project.ai_analysis.dce_available); },
    // Une carte « À venir » (décision 11) : le marché n'est pas encore publié, il n'a ni annonce ni dossier. La page ne
    // parle donc ni d'« annonce seule » ni d'un dossier « indispensable » à télécharger (relecture de la vague 2a).
    aoPasPublie() { return !!(this.ao.project && this.ao.project.status === "suivi") && !this.aoDceAvailable(); },
    // « Comment vous serez noté » : la grille retrouvée dans le règlement (analyse ≥ vague 1 rédaction).
    aoGrille() { const g = this.aoDetails().grille_notation; return (g && Array.isArray(g.criteres)) ? g : null; },
    grilleResume(g) {
      if (!g) return "";
      const n = (g.criteres || []).filter(x => x.dans_le_plan).length, av = (g.compteurs && g.compteurs.a_verifier) || 0;
      const s = (g.ponderation || {}).statut;
      const base = n ? n + " critère" + (n > 1 ? "s" : "") : "aucun critère retenu";
      // Vague 5 : le nombre d'exigences repérées (hors celles retirées par l'utilisateur).
      const ex = ((g.exigences && g.exigences.compteurs) || {}).total || 0;
      return base + (s === "non_ponderes" ? (n === 1 ? " · sans poids" : " · non pondérés") : "") + (av ? " · " + av + " à vérifier" : "")
        + (ex ? " · " + ex + " exigence" + (ex > 1 ? "s" : "") : "");
    },
    async aoGrilleChoix(id, choix, poids) {
      const p = this.ao.project; if (!p || this.ao.grilleBusy) return;
      this.ao.grilleBusy = id;
      const avant = ((this.aoGrille() || {}).criteres || []).find(x => x.id === id) || {};
      try {
        const r = await this.api("POST", "/api/sourcing/grille/choix", { project_id: p.id, critere_id: id, choix, poids: poids || "" });
        const a = Object.assign({}, p.ai_analysis || {}); a.details = Object.assign({}, a.details || {}, { grille_notation: r.grille_notation });
        p.ai_analysis = a;
        // Une ligne déjà dans le plan (retrouvée sans poids) n'y est pas « ajoutée » : on dit ce qui a changé.
        const msgConfirme = !avant.dans_le_plan ? "Critère ajouté à votre plan" : (poids ? "Poids enregistré" : "Critère confirmé");
        this.notify(choix === "confirme" ? msgConfirme : choix === "ecarte" ? "Critère retiré de votre plan" : "Choix annulé");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grilleBusy = ""; }
    },
    // Rédaction, vague 5 (C2 complet) : exigences et questions de la grille, relecture du dossier — sans IA.
    _aoGrilleMaj(p, r) {
      if (!p || !r || !r.grille_notation) return;
      const a = Object.assign({}, p.ai_analysis || {}); a.details = Object.assign({}, a.details || {}, { grille_notation: r.grille_notation });
      p.ai_analysis = a;
    },
    async aoGrilleElement(type, id, choix) {
      const p = this.ao.project; if (!p || this.ao.grilleBusy) return;
      this.ao.grilleBusy = (type === "question" ? "q:" : "ex:") + id;
      try {
        const r = await this.api("POST", "/api/sourcing/grille/element", { project_id: p.id, type, element_id: id, choix });
        this._aoGrilleMaj(p, r);
        this.notify(type === "question" ? (choix === "ecarte" ? "Question retirée" : "Question remise dans la liste")
          : (choix === "ecarte" ? "Exigence retirée de la liste" : choix === "traitee" ? "Exigence dite traitée par vous" : "Exigence remise dans la liste"));
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grilleBusy = ""; }
    },
    async aoGrilleAjout(phrase, fini) {
      const p = this.ao.project; if (!p || this.ao.grilleBusy) return;
      this.ao.grilleBusy = "ajout";
      try {
        const r = await this.api("POST", "/api/sourcing/grille/exigence", { project_id: p.id, phrase });
        this._aoGrilleMaj(p, r); this.notify("Exigence ajoutée : sa phrase est bien dans le dossier");
        if (typeof fini === "function") fini(true);
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grilleBusy = ""; }
    },
    async aoGrilleRelire() {
      const p = this.ao.project; if (!p || this.ao.grilleBusy) return;
      this.ao.grilleBusy = "relire";
      try {
        const r = await this.api("POST", "/api/sourcing/grille/relire", { project_id: p.id });
        this._aoGrilleMaj(p, r); this.notify("Dossier relu sans IA : rien n'a été débité");
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.ao.grilleBusy = ""; }
    },
    // « Rédiger sans IA » depuis la carte : l'atelier s'ouvre sur le choix (il s'enregistre là, pour CE dossier).
    aoSansIa() { this.atlOpen(); this.atl.sansIaPropose = true; },
    // Détail du score : on affiche le VRAI score déterministe du DCE (score_breakdown,
    // 6 critères pondérés) ; repli sur le pré-score de l'avis (lead_score) si absent.
    aoBreakdown() {
      const a = this.ao.project && this.ao.project.ai_analysis;
      if (!a) return [];
      if (a.score_breakdown && a.score_breakdown.length) return a.score_breakdown;
      return (a.dce_available && a.lead_score && a.lead_score.breakdown) || [];
    },
    async aoStatus() {
      const pid = this.ao.project.id;
      try { const r = await this.api("PUT", "/api/projects/" + pid, { status: this.ao.project.status }); this._listeSuitStatut(pid, r && r.status); this.notify("Statut mis à jour"); this.loadStats(); this.ao.cnTick = (this.ao.cnTick || 0) + 1; }
      catch (e) { this.notify(e.message, "err"); }
    },
    // L'étape d'un marché change (marqué déposé, retrait, choix « Statut ») : sa carte de Mes marchés la reprend,
    // sans attendre de recharger la liste (relecture de la vague 2a).
    _listeSuitStatut(pid, statut) { const l = statut && (this.projects || []).find(x => x && x.id === pid); if (l) l.status = statut; },
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
    // Message après génération : le point le plus grave d'abord (BLOQUANT, puis dossier de
    // présentation), le succès seulement quand il n'y a rien à traiter. Jamais « archivé » quand
    // aucun dossier de présentation n'a été rangé.
    dossierWarnKind(d) { return ((d && d.warnings) || []).length ? "err" : "ok"; },
    dossierToast(d, okMsg) {
      const ws = (d && d.warnings) || [];
      if (!ws.length) return okMsg;
      const w = ws.find(x => x.startsWith("BLOQUANT")) || ws.find(x => x.startsWith("Dossier de présentation")) || ws[0];
      const n = ws.length - 1, x = n > 1 ? "s" : "";
      const plus = n ? " (et " + n + " autre" + x + " point" + x + ", détaillé" + x + " sur la page)" : "";
      return okMsg + ". À traiter avant le dépôt : " + w.replace(/^BLOQUANT — /, "") + plus;
    },
    async aoGenerate(opts) {
      const silent = opts && opts.silent;
      this.ao.generating = true; this.ao.dossier = null;
      try {
        const r = await this.api("POST", "/api/sourcing/documents", { project_id: this.ao.project.id, cotraitants: [] });
        this.ao.dossier = r.dossier; this.aoLoadDocs(); this.aoLoadChecklist(); this.aoAvancer();
        if (this.convVisible()) this.aoGrpReloadState();   // « Prêt à déposer » : formulaires préparés après la convention
        else this.aoDepotLoadSoon();                       // seul : formulaires préparés
        const range = r.dossier && r.dossier.memoire_fichiers && r.dossier.memoire_fichiers.length;
        if (!silent) this.notify(this.dossierToast(r.dossier, range ? "Documents préparés et rangés dans le dossier du marché" : "Documents préparés"), this.dossierWarnKind(r.dossier));
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
      await this.aoGenerate({ silent: true });
      const d = this.ao.dossier;
      if (d && d.zip_b64) { this.aoDownload(); this.notify(this.dossierToast(d, "Dossier commun assemblé et téléchargé"), this.dossierWarnKind(d)); }
    },
    // Lecture d'un dossier : liée au MARCHÉ suivi (ao.lecturePid). Ouvrir un autre marché pendant la
    // lecture n'y montre ni le voile ni les messages, et n'y bloque pas les boutons ; à la fin, seul
    // le marché lu est rechargé.
    aoBusy() { return !!(this.ao.uploading && this.ao.project && this.ao.lecturePid === this.ao.project.id); },
    aoLectureDebut(pid) { this.ao.uploading = true; this.ao.lecturePid = pid; this.ao.lectureMsg = ""; },
    aoLectureFin(pid) {
      if (this.ao.lecturePid === pid) { this.ao.uploading = false; this.ao.lectureMsg = ""; this.ao.lecturePid = null; }
      // L'atelier ouvert sur ce marché pendant la lecture relit « Pièces du dossier de l'acheteur lues
      // par Adjugo » (lecture terminée ou en échec) : plus de « pas encore terminée » resté affiché.
      if (this.view === "atelier" && this.atl.pid === pid) this.atlLoad(true);
    },
    aoLectureMsg(pid) { return m => { if (this.ao.lecturePid === pid) this.ao.lectureMsg = m; }; },
    async aoApresLecture(pid, toast) {
      if (!(this.ao.project && this.ao.project.id === pid)) { this.notify(toast); return; }
      this.ao.project = await this.api("GET", "/api/projects/" + pid);
      this.aoLoadDocs(); this.atlCardLoad();
      this.notify(toast === null ? this.couvertureToast(this.ao.project.ai_analysis) : toast);
    },
    async aoUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      if (!(await this.gateCriteria())) return;
      const pid = this.ao.project.id;
      this.aoLectureDebut(pid);
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", pid);
        const r = await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        if (r && r.en_cours) await this.waitLecture(pid, this.aoLectureMsg(pid));
        await this.aoApresLecture(pid, (this.ao.project && this.ao.project.id === pid) ? null : "Dossier du marché analysé");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.aoLectureFin(pid); }
    },
    async aoReanalyze() {
      if (!this.ao.project) return;
      const pid = this.ao.project.id;
      this.aoLectureDebut(pid);
      try {
        const fd = new FormData(); fd.append("project_id", pid);
        const r = await this.api("POST", "/api/sourcing/reanalyze", fd, true);
        if (r && r.en_cours) await this.waitLecture(pid, this.aoLectureMsg(pid));
        await this.aoApresLecture(pid, "Ré-analyse terminée");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.aoLectureFin(pid); }
    },
    // Lecture d'un gros dossier en tâche de fond : progression lue toutes les 3 s jusqu'à la fin.
    // Renvoie le résultat de l'analyse (même forme que la réponse d'import), ou lève l'erreur.
    async waitLecture(pid, onMsg) {
      for (let i = 0; i < 1000; i++) {
        let st = null;
        try { st = await this.api("GET", "/api/sourcing/lecture/" + pid); } catch (e) { st = null; }
        if (st && st.etat === "erreur") throw new Error(st.erreur || "La lecture du dossier a échoué.");
        if (st && st.etat === "termine") {
          if (st.job_id) { try { const j = await this.api("GET", "/api/jobs/" + st.job_id); if (j && j.result) return j.result; } catch (e) {} }
          return null;
        }
        if (st && onMsg) onMsg(this.lectureMsg(st.progression || {}));
        await new Promise(res => setTimeout(res, 3000));
      }
      throw new Error("La lecture du dossier prend plus de temps que prévu : revenez sur ce marché un peu plus tard.");
    },
    lectureMsg(p) {
      p = p || {};
      const n = (v, mot) => v + " " + mot + (v > 1 ? "s" : "");
      if (p.etape === "synthese") return "Analyse : rassemblement de ce qui a été lu dans chaque pièce…";
      if (p.etape === "analyse" && p.parties_total) return "Analyse : " + n(p.parties_lues || 0, "partie") + " lue" + ((p.parties_lues || 0) > 1 ? "s" : "") + " par l'IA sur " + p.parties_total + "…";
      if (p.etape === "analyse") return "Analyse du dossier lu en entier…";
      const lues = p.pieces_lues || 0;
      let m = "Lecture du dossier : " + n(lues, "pièce") + " lue" + (lues > 1 ? "s" : "");
      if (p.pieces_total) m += " sur " + p.pieces_total;
      if (p.pages_lues) m += ", " + n(p.pages_lues, "page");
      return m + "…";
    },
    async aoResumeLecture() {
      const p = this.ao.project; if (!p || this.ao.lecturePid === p.id) return;   // déjà suivie
      const st = p.workflow && p.workflow.lecture;
      if (!st || st.etat !== "en_cours") return;
      this.aoLectureDebut(p.id); this.ao.lectureBusy = true; this.ao.lectureMsg = "Lecture du dossier en cours…";
      try {
        await this.waitLecture(p.id, this.aoLectureMsg(p.id));
        if (this.ao.project && this.ao.project.id === p.id) {
          this.ao.project = await this.api("GET", "/api/projects/" + p.id);
          this.atlCardLoad();
          this.notify(this.couvertureToast(this.ao.project.ai_analysis));
        }
      } catch (e) { if (this.ao.project && this.ao.project.id === p.id) this.notify(e.message, "err"); }
      finally { this.ao.lectureBusy = false; this.aoLectureFin(p.id); }
    },
    // Couverture honnête de la lecture : « Dossier lu en entier : N pièces, P pages » ou les manques.
    couvertureToast(a) {
      const c = a && a.couverture;
      if (!c || !c.message) return "Dossier analysé";
      return c.complet ? "Dossier analysé. " + c.message : c.message;
    },
    aoCouverture() { const a = this.ao.project && this.ao.project.ai_analysis; return (a && a.couverture && a.couverture.message) ? a.couverture : null; },
    aoAncienneLecture() { const a = this.ao.project && this.ao.project.ai_analysis; return !!(a && a.dce_available && a.dce_excerpt && !a.lecture); },
    // Ce qui manque : pièces non lues ou lues en partie, ET parties que l'IA n'a pas pu exploiter
    // (lecture en deux temps), chacune avec sa raison.
    couvManques(c) { return c ? [].concat(c.non_lues || [], c.partielles || [], (c.analyse && c.analyse.manques) || []) : []; },
    // Avertissements joints par le serveur à un fichier (en-tête X-Adjugo-Avertissements) : par exemple
    // un partenaire absent des formulaires officiels faute d'accord. Aussi écrits dans le sommaire du ZIP.
    avertissementsFichier(r) {
      const v = r && r.headers && r.headers.get("X-Adjugo-Avertissements");
      if (!v) return "";
      try { return decodeURIComponent(v).split(" | ").filter(Boolean).join(" "); } catch (e) { return ""; }
    },
    async aoExport() {
      try {
        const r = await fetch("/api/export/" + this.ao.project.id, { method: "POST", headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Export impossible");
        this.saveBlob(await r.blob(), atlNomFichier(r.headers.get("content-disposition"), "Dossier_marche_" + this.ao.project.id + ".zip"));
        const av = this.avertissementsFichier(r); if (av) this.notify("Dossier téléchargé. À vérifier : " + av, "warn");
      } catch (e) { this.notify(e.message, "err"); }
    },
    async aoDelete() {
      const id = this.ao.project.id;
      try { await this.api("DELETE", "/api/projects/" + id); this.aoBack(); this.loadProjects(); this.notifyUndo("Marché mis à la corbeille", () => this.restoreProject(id)); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async restoreProject(id) {
      try { await this.api("POST", "/api/projects/" + id + "/restore"); this.loadProjects(); this.notify("Restauré"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async updateProjectStatus() {
      try { await this.api("PUT", "/api/projects/" + this.drawer.id, { status: this.drawer.status }); this.notify("Statut mis à jour"); this.loadProjects(); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async delProject(p) {
      const id = p.id;
      if (!(await this.confirmer({ title: "Supprimer ce marché ?", ok: "Mettre à la corbeille", danger: true,
        lines: ["Le marché et toutes ses données (analyse, partenaires, documents) partent à la corbeille.", "Vous pouvez le récupérer juste après, avec « Annuler »."] }))) return;
      try { await this.api("DELETE", "/api/projects/" + id); this.drawer = null; this.loadProjects(); this.notifyUndo("Marché mis à la corbeille", () => this.restoreProject(id)); }
      catch (e) { this.notify(e.message, "err"); }
    },
    async exportDossier(p) {
      this.notify("Génération du dossier…");
      try {
        const r = await fetch("/api/export/" + p.id, { method: "POST", headers: { Authorization: "Bearer " + this.token } });
        if (!r.ok) throw new Error("Export impossible");
        const blob = await r.blob(); this.saveBlob(blob, atlNomFichier(r.headers.get("content-disposition"), "Dossier_marche_" + p.id + ".zip"));
        const av = this.avertissementsFichier(r); this.notify(av ? "Dossier téléchargé. À vérifier : " + av : "Dossier téléchargé", av ? "warn" : "ok");
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
    async delCotraitant(c) {
      if (!(await this.confirmer({ title: "Retirer " + c.name + " de vos partenaires ?", ok: "Retirer", danger: true,
        lines: ["Elle est aussi retirée des marchés où vous l'avez ajoutée (« Membres et sous-traitants »).",
                { t: "Une convention de groupement qui la cite sera à revalider.", warn: true }] }))) return;
      try { await this.api("DELETE", "/api/cotraitants/" + c.id); this.loadCotraitants(); } catch (e) { this.notify(e.message, "err"); }
    },
    async delContact(c) {
      if (!(await this.confirmer({ title: "Supprimer le contact " + c.name + " ?", ok: "Supprimer", danger: true }))) return;
      try { await this.api("DELETE", "/api/contacts/" + c.id); this.loadContacts(); } catch (e) { this.notify(e.message, "err"); }
    },

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
      if (ok) { this.loadDocuments(); this.notify(ok === files.length ? ok + " document(s) ajouté(s)" : ok + " sur " + files.length + " ajouté(s)"); }
      else this.notify("Aucun document ajouté", "err");
    },
    async delDoc(d) { const id = d.id; try { await this.api("DELETE", "/api/documents/" + id); this.loadDocuments(); this.loadExpiring(); this.notifyUndo("Document mis à la corbeille", () => this.restoreDoc(id)); } catch (e) { this.notify(e.message, "err"); } },
    async renameDoc(d) {
      const v = await this.demander({ title: "Renommer le document", ok: "Renommer",
        fields: [{ key: "name", label: "Nom du document", value: d.name || "", requis: true, max: 500 }] });
      const name = ((v && v.name) || "").trim();
      if (!name || name === d.name) return;
      try { await this.api("PATCH", "/api/documents/" + d.id, { name }); this.loadDocuments(); this.notify("Renommé"); }
      catch (e) { this.notify(e.message, "err"); }
    },
    // Catégorie ou date de fin changée dans la liste : enregistrée tout de suite (PATCH), la ligne reprend ce que dit
    // le serveur (dont l'état « Expire dans 12 jours »), puis la pastille « pièces à renouveler » est relue. Refus
    // (démonstration, date illisible) : la liste est relue, l'ancienne valeur revient.
    async docModifier(d, patch) {
      if (!d || this.docBusy) return;
      this.docBusy = d.id;
      try {
        const r = await this.api("PATCH", "/api/documents/" + d.id, patch);
        const i = this.documents.findIndex(x => x.id === d.id);
        if (i >= 0 && r && r.id === d.id) this.documents.splice(i, 1, Object.assign({}, this.documents[i], r));
        this.notify("expiration_date" in patch ? (patch.expiration_date ? "Date de fin enregistrée" : "Date de fin retirée") : "Catégorie enregistrée");
        this.loadExpiring();
      } catch (e) { this.notify(e.message, "err"); await this.loadDocuments(); }
      finally { this.docBusy = null; }
    },
    async restoreDoc(id) { try { await this.api("POST", "/api/documents/" + id + "/restore"); this.loadDocuments(); this.loadExpiring(); this.notify("Restauré"); } catch (e) { this.notify(e.message, "err"); } },
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
      return ({ suivi: "var(--border-2)", nouveau: "var(--subtle)", decide: "var(--accent-weak)", en_cours: "var(--warning)",
                depose: "var(--accent)", gagne: "var(--success)", perdu: "var(--danger)", abandonne: "var(--border-2)" })[s] || "var(--subtle)";
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
    // Décision 8 : le seul pourcentage est le couple « Seul X % · À plusieurs Y % » (comme l'en-tête du marché), posé
    // après le dossier du marché (match_score n'existe qu'à partir d'un vrai dossier) ; avant, des mots.
    feedScoreTitle(p) {
      const bits = [];
      if (p.match_score != null) bits.push("Seul " + p.match_score + " %");
      if (p.groupement_score != null) bits.push("À plusieurs " + p.groupement_score + " %");
      return bits.length ? bits.join(" · ") : "Pas encore analysé";
    },
    // Le nombre de l'anneau (accueil) et de la carte (Mes marchés), dit avec son libellé : « Seul 87 % » ou
    // « À plusieurs 100 % » (décision 8 : le seul pourcentage est ce couple). "" tant que le marché n'est pas noté.
    scoreCourt(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null) return "À plusieurs " + p.groupement_score + " %";
      return p.match_score != null ? "Seul " + p.match_score + " %" : "";
    },
    // Bilan de l'accueil (décision 8) : « 2 gagnés sur 3 », jamais un taux en pourcentage.
    gagnesSur(won, total) { const w = Number(won) || 0, t = Number(total) || 0; return w + " " + (w > 1 ? "gagnés" : "gagné") + " sur " + t; },
    // Segment « Seul ou à plusieurs » : la clé de l'API (« Solo », « Groupement ») dite avec les mots du produit.
    segmentSeul(k) { return ({ Solo: "Seul", Groupement: "À plusieurs" })[k] || k; },
    feedRingStyle(p) {
      if (p.go_decision === "go_groupement" && p.groupement_score != null) {
        const deg = Math.max(0, Math.min(100, p.groupement_score)) * 3.6;
        return `background:conic-gradient(var(--accent) ${deg}deg, var(--hairline) ${deg}deg)`;
      }
      return this.ringStyle(p.match_score);
    },
    decLabel(d) { return ({ go: "Bon potentiel", go_groupement: "Bon potentiel en groupement", no_go: "Peu adapté", a_etudier: "À étudier" })[d] || "—"; },
    decColor(d) { return ({ go: "color:var(--go)", go_groupement: "color:var(--accent-text)", no_go: "color:var(--danger)", a_etudier: "color:var(--warning-text)" })[d] || "color:var(--muted)"; },
    // Kanban : la carte dit « À plusieurs 100 % » ou « Seul 87 % » (scoreCourt) ; le couple complet reste au survol.
    kanbanScoreTitle(p) { return (p.match_score == null && p.groupement_score == null) ? "" : this.feedScoreTitle(p); },
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
    statusLabel(s) { return libelleStatut(s); },            // un seul axe d'étapes (vague 2a, AXE_ETAPES)
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
      const out = {}; const labels = { intitule_marche: "Intitulé", acheteur: "Acheteur", budget_estime: "Budget", date_limite: "Date limite", delai_execution: "Délai", lieu_execution: "Lieu", allotissement: "Parties (lots)", penalites: "Pénalités", sous_traitance: "Sous-traitance", ca_minimum_requis: "CA minimum", visite_obligatoire: "Visite" };
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
      try { const r = await this.api("POST", "/api/saved-searches/" + a.id + "/run"); this.loadAlerts(); this.notify(r.new_matches + " " + (r.new_matches > 1 ? "nouveaux marchés trouvés" : "nouveau marché trouvé")); }
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
      if (!(await this.confirmer({ title: "Supprimer cette alerte ?", ok: "Supprimer l'alerte", danger: true,
        lines: ["Vous ne recevrez plus par courriel les nouveaux marchés de cette recherche."] }))) return;
      try { await this.api("DELETE", "/api/saved-searches/" + id); this.loadAlerts(); this.notify("Alerte supprimée"); }
      catch (e) { this.notify(e.message, "err"); }
    },

    // ── Sourcing IA (flux à la demande, sources officielles) ──
    srcDeps() { return this.src.dept.split(",").map(s => s.trim()).filter(Boolean); },
    srcCpv() { return (this.src.cpv || "").split(/[,\s]+/).map(s => s.trim()).filter(Boolean); },
    srcResetAdv() { this.src.type_marche = ""; this.src.cpv = ""; },
    async srcRenewals() {
      if (this.src.renewals.loading) return;   // Entrée maintenue dans les champs de l'onglet « À venir » : une seule recherche
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
    // Décision 11 (vague 2a) : « Préparer à plusieurs » sur une fin de contrat crée la carte du marché dans Mes
    // marchés, à l'étape « À venir » (avant sa publication), puis ouvre sa page sur « Inviter un partenaire ». Une carte
    // déjà créée pour ce contrat (même objet, même client, encore « À venir ») est rouverte, jamais recréée.
    async srcAVenirPreparer(r) {
      const R = this.src.renewals; if (!r || R.prep) return;
      const nom = String(r.objet || "").trim().slice(0, 500) || "Marché à venir", client = String(r.acheteur || "").trim().slice(0, 255);
      let p = (this.projects || []).find(x => x && !x.deleted_at && x.status === "suivi" && (x.name || "") === nom && (x.client || "") === client);
      R.prep = r.idweb || nom;
      try {
        if (!p) {
          p = await this.api("POST", "/api/projects/", { name: nom, client: client || null, source_url: r.url || null, status: "suivi" });
          await this.loadProjects();
          this.notify("Marché ajouté à Mes marchés, à l'étape « À venir »");
        }
        this.openAo(p);         // ao.share est posé tout de suite (avant le premier appel réseau)
        this.aoInviter();
      } catch (e) { this.notify(e.message, "err"); }
      finally { R.prep = ""; }
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
        this.src.chosen = null; this.src.projectId = null;
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
        } else { this.src.tenders = fresh; this.src.errors = r.errors || []; this.src.sources = r.sources_queried || []; this.src.nonConsultees = r.sources_non_consultees || []; }
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
    // Fonctions d'IA en pause (essai terminé sans forfait) : "essai" | "forfait" (compte déjà passé par
    // le paiement, dont le forfait n'est plus actif) | "". Repli sur l'état de l'essai si le serveur ne le dit pas.
    iaPause() {
      const u = this.stats && this.stats.usage; if (!u) return "";
      if ("ia_pause" in u) return u.ia_pause || "";
      return (u.trial_state === "expired" && u.plan === "starter") ? "essai" : "";
    },
    srcQuotaBlocked() { const u = this.stats.usage; return !!u && ((u.analyses_remaining <= 0 && !u.overage_enabled) || u.trial_usage === "atteint" || !!this.iaPause()); },
    srcQuotaLabel() {
      const u = this.stats.usage; if (!u || typeof u.analyses_remaining !== "number") return "";
      const pause = this.iaPause();
      if (pause === "forfait") return "Aucun forfait actif : choisissez un forfait pour lancer une analyse";
      if (pause) return "Essai gratuit terminé : choisissez un forfait pour lancer une analyse";
      if (u.quota_scope === "essai") {   // essai gratuit : compté sur toute sa durée, pas par mois
        if (u.trial_usage === "atteint") return "Limite d'usage de l'essai atteinte";
        if (u.analyses_remaining > 0) return u.analyses_remaining + " analyse" + (u.analyses_remaining > 1 ? "s" : "") + " restante" + (u.analyses_remaining > 1 ? "s" : "") + " sur " + u.analyses_limit + " (essai gratuit)";
        return "Les " + u.analyses_limit + " analyses de l'essai sont utilisées";
      }
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
      if (!(await this.gateCriteria())) return;
      this.src.analyzing = true; this.src.chosen = t; this.src.analysis = null; this.src.marketEst = null;
      try {
        const r = await this.api("POST", "/api/sourcing/analyze", { tender: t });
        this.src.analysis = r; this.src.projectId = r.project_id;
        this.loadProjects(); this.loadStats();
        this.rnScrollTo("srcAnalyse");   // l'analyse s'affiche sous les résultats : on y mène, « Ouvrir le marché » compris
        if (!r.dce_available) this.notify("Dossier complet non accessible — analyse fondée sur l'annonce publiée", "ok");
      } catch (e) {
        if ((e.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(e.message, "err");
      } finally { this.src.analyzing = false; }
    },
    async srcUploadDce(e) {
      const file = e.target.files[0]; if (!file) return;
      e.target.value = "";
      if (!(await this.gateCriteria())) return;
      if (!this.src.projectId) { this.notify("Analysez d'abord l'annonce", "err"); return; }
      this.src.analyzing = true;
      try {
        const fd = new FormData(); fd.append("file", file); fd.append("project_id", this.src.projectId);
        let r = await this.api("POST", "/api/sourcing/analyze-upload", fd, true);
        if (r && r.en_cours) r = await this.waitLecture(this.src.projectId, m => { this.src.lectureMsg = m; });
        if (r) this.src.analysis = r;
        this.loadProjects(); this.loadStats();
        this.notify(this.couvertureToast(r));
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota d'analyses atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.analyzing = false; this.src.lectureMsg = ""; }
    },
    async srcReanalyze() {
      if (!this.src.projectId) { this.notify("Importez d'abord le dossier du marché", "err"); return; }
      this.src.analyzing = true;
      try {
        const fd = new FormData(); fd.append("project_id", this.src.projectId);
        let r = await this.api("POST", "/api/sourcing/reanalyze", fd, true);
        if (r && r.en_cours) r = await this.waitLecture(this.src.projectId, m => { this.src.lectureMsg = m; });
        if (r) this.src.analysis = r;
        this.loadProjects();
        this.notify("Ré-analyse terminée");
      } catch (err) {
        if ((err.message || "").toLowerCase().includes("uota")) { this.notify("Quota atteint", "err"); this.go("billing"); }
        else this.notify(err.message, "err");
      } finally { this.src.analyzing = false; this.src.lectureMsg = ""; }
    },

    // ── Veille amont (signaux d'investissement) ──
    async loadAmont() {
      await this.loadFeatures();
      // Masqué jusqu'à la vague 1 de l'étude veille : rien n'est chargé ni affiché (données gardées).
      if (!this.features.projets_a_venir) { this.amont.signals = []; return; }
      try { this.amont.signals = await this.api("GET", "/api/amont/"); } catch (e) {}
      try {
        const a = await this.api("GET", "/api/amont/auto");
        this.amont.auto = a.enabled;
        // Activée mais en pause (essai terminé sans forfait) : la veille planifiée ne sert plus ce compte.
        this.amont.autoPause = a.en_pause ? (a.motif || "essai") : "";
      } catch (e) {}
    },
    amontPauseInfo() {
      return this.amont.autoPause === "forfait"
        ? "Aucun forfait n'est actif sur votre compte : la veille automatique reprend dès que vous choisissez un forfait."
        : "Votre essai gratuit est terminé : la veille automatique reprend dès que vous choisissez un forfait.";
    },
    async amontToggleAuto() {
      try {
        const r = await this.api("POST", "/api/amont/auto", { enabled: !this.amont.auto });
        this.amont.auto = r.enabled;
        this.amont.autoPause = "";   // accepté : activée hors pause, ou désactivée
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
      this.fxEtats();
    },

    // ── Fiches proposées à partir d'un document (rédaction, vague 3, chantier I) ──
    // Contrat : docs/REDACTION_V3_IMPORT.md. Adjugo lit le document une fois (tâche de fond) et
    // propose des fiches, chacune avec son passage exact ; l'utilisateur coche (routes du socle).
    async fxEtats() {
      try { const r = await this.api("GET", "/api/knowledge/fiches"); this.kb.fx.etat = r.documents || {}; this.kb.fx.plafond = r.plafond || null; }
      catch (e) {}
    },
    fxEtat(d) { return (this.kb.fx.etat || {})[String(d.id)] || null; },
    fxBouton(d) {
      const e = this.fxEtat(d); const st = e ? e.statut : "a_lire";
      if (st === "lu") return "Voir les fiches proposées";
      if (st === "en_cours") return "Lecture en cours";
      if (st === "cv" || st === "piece_acheteur" || st === "rien_a_lire") return "Pourquoi aucune fiche";
      return "Proposer des fiches";
    },
    fxResume(d) {
      const e = this.fxEtat(d);
      if (!e || e.statut !== "lu") return "";
      return e.a_cocher + " à cocher · " + e.cochees + " cochée(s)";
    },
    fxAujourdhui() {
      const n = new Date(); const p = x => String(x).padStart(2, "0");
      return n.getFullYear() + "-" + p(n.getMonth() + 1) + "-" + p(n.getDate());
    },
    fxDate(iso) {
      if (!iso) return "";
      const [y, m, j] = String(iso).slice(0, 10).split("-");
      return j + "/" + m + "/" + y;
    },
    fxStatut() {
      const x = this.kb.fx.data;
      if (!x) return "";
      return (x.lecture && x.lecture.statut) || x.document.statut;
    },
    fxTexte(f) { return String(f.texte || "").replace(/^[^:]{1,20} : /, ""); },
    fxEcarts() {
      const l = (this.kb.fx.data && this.kb.fx.data.lecture) || {};
      const n = l.ecartees || 0;
      if (!n) return "";
      const detail = (l.ecarts || []).map(e => e.libelle + " (" + e.nombre + ")").join(", ");
      return n + (n > 1 ? " propositions écartées" : " proposition écartée") + " par Adjugo, sans IA : " + detail + ".";
    },
    async fxOuvrir(d) {
      if (this.kb.fx.open === d.id) { this.kb.fx.open = null; this.kb.fx.data = null; this.kb.fx.poll++; return; }
      this.kb.fx.open = d.id; this.kb.fx.data = null; this.kb.fx.date = ""; this.kb.fx.contexte = {};
      await this.fxCharger(d.id);
      const doc = this.kb.fx.data && this.kb.fx.data.document;
      if (doc && doc.date_suggeree) this.kb.fx.date = doc.date_suggeree;
      this.fxSuivre(d.id);
    },
    async fxCharger(id) {
      try {
        const r = await this.api("GET", "/api/knowledge/" + id + "/fiches");
        if (this.kb.fx.open === id) { this.kb.fx.data = r; this.kb.fx.plafond = r.plafond || this.kb.fx.plafond; }
      } catch (e) { this.notify(e.message, "err"); }
    },
    async fxLancer(d) {
      if (this.kb.fx.busy) return;
      this.kb.fx.busy = true;
      try {
        const r = await this.api("POST", "/api/knowledge/" + d.id + "/fiches", { date_document: this.kb.fx.date || null });
        if (this.kb.fx.open === d.id) { this.kb.fx.data = r; this.kb.fx.plafond = r.plafond || this.kb.fx.plafond; }
        this.fxEtats();
        this.fxSuivre(d.id);
      } catch (e) { this.notify(e.message, "err"); }
      finally { this.kb.fx.busy = false; }
    },
    fxSuivre(id) {
      // Lecture en tâche de fond : l'écran se met à jour seul, sans bloquer la page.
      const tour = ++this.kb.fx.poll;
      const step = async (n) => {
        if (tour !== this.kb.fx.poll || this.kb.fx.open !== id) return;
        if (this.fxStatut() !== "en_cours") { if (n > 0) this.fxEtats(); return; }
        if (n > 240) return;
        await new Promise(r => setTimeout(r, 2500));
        if (tour !== this.kb.fx.poll || this.kb.fx.open !== id) return;
        await this.fxCharger(id);
        step(n + 1);
      };
      step(0);
    },
    async fxCocher(f, ev) {
      const on = !!ev.target.checked;
      this.kb.fx.coche = f.id;
      try {
        const r = await this.api("POST", "/api/preuves/" + f.id + (on ? "/accepter" : "/retirer"), { version: f.version });
        Object.assign(f, r);
        this.fxEtats();
      } catch (e) {
        ev.target.checked = !on;
        this.notify(e.message, "err");
        if (e.status === 409 && this.kb.fx.open) this.fxCharger(this.kb.fx.open);
      } finally { this.kb.fx.coche = null; }
    },
    async fxContexte(f) {
      if (this.kb.fx.contexte[f.id]) { const c = Object.assign({}, this.kb.fx.contexte); delete c[f.id]; this.kb.fx.contexte = c; return; }
      try {
        const p = await this.api("GET", "/api/preuves/" + f.id + "/passage");
        this.kb.fx.contexte = Object.assign({}, this.kb.fx.contexte, { [f.id]: p });
        // Le passage surligné est amené en vue dans sa boîte (sans faire défiler la page).
        this.$nextTick(() => {
          const box = document.querySelector('[data-fx-ctx="' + f.id + '"]');
          const m = box && box.querySelector("mark");
          if (box && m) box.scrollTop = Math.max(0, m.offsetTop - box.offsetTop - 24);
        });
      } catch (e) { this.notify(e.message, "err"); }
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
      if (!(await this.confirmer({ title: "Retirer ce document de votre savoir-faire ?", ok: "Retirer", danger: true,
        lines: ["Adjugo ne s'en sert plus pour rédiger. Les fiches de « Mes preuves » tirées de ce document n'auront plus de source."] }))) return;
      // kbLoad() rafraîchit aussi le compteur d'extraits indexés (sinon il restait périmé).
      try {
        const r = await this.api("DELETE", "/api/knowledge/" + d.id); await this.kbLoad();
        // « Mes preuves » : les fiches dont le passage venait de ce document n'ont plus de source.
        const n = (r && r.preuves_sans_source) || 0;
        if (n) this.notify(n + (n > 1 ? " fiches de « Mes preuves » n'ont plus de source : Adjugo ne s'en sert plus." : " fiche de « Mes preuves » n'a plus de source : Adjugo ne s'en sert plus."), "err");
      }
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
    async kbQuestionnaire() {
      const qs = (this.kb.qText || "").split("\n").map(s => s.trim()).filter(Boolean);
      if (!qs.length) { this.notify("Collez vos questions (une par ligne)", "err"); return; }
      if (!this.kb.docs.length) { this.notify("Ajoutez d'abord des documents à votre base", "err"); return; }
      this.kb.qLoading = true; this.kb.qResults = null;
      try {
        const job = await this.api("POST", "/api/knowledge/questionnaire", { questions: qs });
        const r = await this.pollJob(job.id); this.kb.qResults = r;
        const errs = r.errors || 0;
        let msg = r.covered + " sur " + (r.count - errs) + " réponse(s) proposée(s), à relire";
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
    // Après l'analyse : on ouvre le MARCHÉ (formulaires, dossier de présentation, pièces, groupement),
    // et non plus un dossier préparé ici avec des entreprises cochées sans leur accord (étude organisation,
    // décision 4). « Inviter » ouvre directement le formulaire d'invitation du marché.
    async srcOuvrirMarche(inviter) {
      const pid = this.src.projectId; if (!pid) return;
      await this.loadProjects();
      const p = this.projects.find(x => x.id === pid);
      if (!p) { this.notify("Marché introuvable", "err"); return; }
      this.openAo(p);   // ao.share est posé tout de suite (avant le premier appel réseau)
      if (inviter) this.aoInviter();   // le formulaire d'invitation, en tête de la page du marché
    },
    confClass(c) { return c >= 0.8 ? "go" : c >= 0.5 ? "a_etudier" : "neutral"; },
    critStatus(s) { return ({ ok: "go", partiel: "a_etudier", inconnu: "neutral" })[s] || "neutral"; },
    // ══════════ Atelier du dossier de présentation (rédaction, vague 2) ══════════
    // Contrat : docs/REDACTION_V2_API.md. Carte sur la page du marché (état + UN bouton) et vue
    // « atelier » : plan à gauche, texte au centre, extraits privés et faits « à relire » à droite.
    // Le dirigeant reste l'auteur : chaque enregistrement crée une version (rien n'est écrasé),
    // un brouillon local protège la saisie en cas de coupure, et l'IA ne corrige jamais un fait.
    _atlUrl(path) { return "/api/atelier/" + this.atl.pid + (path || ""); },
    async atlCardLoad() {
      const p = this.ao.project; if (!p) return;
      const c = this.ao.atl; c.loading = true; c.error = "";
      try {
        const d = await this.api("GET", "/api/atelier/" + p.id);
        if (this.ao.project && this.ao.project.id === p.id) { c.d = d; this._atlResume(d, p.id); }
      } catch (e) { c.error = e.message || "Dossier de présentation indisponible pour le moment."; }
      finally { c.loading = false; c.loaded = true; }
    },
    atlCompte(d) {
      const ss = (d && d.sections) || [], n = {};
      // Une part de partenaire ou une partie tirée du groupement compte selon son statut de groupement (le même
      // que sa pastille), jamais selon le statut brut de l'atelier.
      const grp = { validee: "valide", a_revalider: "a_revalider", envoyee: "a_valider", a_valider: "a_valider", en_cours: "brouillon", a_rediger: "a_ecrire" };
      ss.forEach(s => { const k = s.part ? (grp[s.part.statut] || s.statut) : s.statut; n[k] = (n[k] || 0) + 1; });
      return { total: ss.length, n, enCours: ss.filter(s => s.redaction_en_cours).length };
    },
    // « 2 validées sur 5 · 1 brouillon · 2 à écrire »
    atlCompteTexte(d) {
      const c = this.atlCompte(d); if (!c.total) return "Aucune partie dans le plan";
      const v = c.n.valide || 0;
      const parts = [v + " validée" + (v > 1 ? "s" : "") + " sur " + c.total];
      const lab = { a_revalider: ["à revalider", "à revalider"], a_valider: ["à valider", "à valider"], relu: ["relue", "relues"], brouillon: ["brouillon", "brouillons"], a_ecrire: ["à écrire", "à écrire"] };
      Object.keys(lab).forEach(k => { const x = c.n[k] || 0; if (x) parts.push(x + " " + lab[k][x > 1 ? 1 : 0]); });
      return parts.join(" · ");
    },
    atlLimCls(l) { const n = atlLimNiveau(l); return n ? "atl-lim-" + n : ""; },
    atlNum(n) { const x = Number(n); return isFinite(x) ? x.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) : ""; },
    atlWhen(s) {
      if (!s) return "";
      try {
        const d = new Date(_isoUtc(s)); if (isNaN(d.getTime())) return "";
        return d.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris", day: "2-digit", month: "2-digit", year: "numeric" })
          + " à " + d.toLocaleTimeString("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" });
      } catch (e) { return ""; }
    },
    atlStatutCls(st) { return ({ a_ecrire: "neutral", brouillon: "atl-st-brouillon", relu: "st-envoye", valide: "go", a_revalider: "a_etudier" })[st] || "neutral"; },
    // La partie d'un partenaire (vague 4) porte le statut du groupement (à rédiger, envoyée, à revalider…).
    atlPillCls(s) { return s && s.part ? atlRepStatutCls(s.part.statut) : this.atlStatutCls(s && s.statut); },
    atlPillLib(s) { return s && s.part ? s.part.statut_libelle : ((s && s.statut_libelle) || ""); },
    // Qui a écrit la version affichée : pour la part d'un partenaire, lui ou vous (jamais « par vous » à tort).
    atlOrigine(s) {
      const v = s && s.version_courante; if (!v) return "";
      // Partie tirée du groupement : écrite par Adjugo sans IA (personne ne l'« envoie »).
      if (s.genere || v.ecrit_par === "genere") return v.origine_libelle;
      if (s.prive_visible || !v.ecrit_par) return v.origine_libelle;
      return v.ecrit_par === "chef_de_file" ? "écrite par vous sur sa partie" : "envoyée par " + s.auteur.libelle;
    },
    atlPlanLabel(src) { return ({ cadre: "Cadre de l'acheteur", grille: "Critères du règlement", libre: "Plan simple" })[src] || ""; },
    atlLimTexte(x) { return _gnLim(x || {}); },
    atlLimCourt(l) { const m = String((l && l.message) || ""), p = (l && l.titre ? l.titre + " : " : ""); const r = p && m.indexOf(p) === 0 ? m.slice(p.length) : m; return r.charAt(0).toUpperCase() + r.slice(1); },
    atlPartLabel(s) { return (s.numero_affiche ? s.numero_affiche + " " : "") + s.intitule + ", " + s.statut_libelle + (s.faits_a_relire ? ", " + s.faits_a_relire + " fait" + (s.faits_a_relire > 1 ? "s" : "") + " à relire" : "") + (s.redaction_en_cours ? ", rédaction en cours" : ""); },
    atlMotsLib(n) { return Number(n) > 1 ? "mots" : "mot"; },
    atlPropLims(p) {   // limites repérées dans le règlement, montrées avec le plan proposé
      const l = (p && p.limites) || {}, out = [];
      // Plusieurs lots (vague 6) : la limite vaut pour le dossier de CHAQUE lot (celle propre à un lot est dite dans l'atelier).
      const plus = !!(p && p.lots && p.lots.actif);
      (l.document || []).forEach(x => out.push({ t: _gnLim(x) + (plus ? " pour le dossier de chaque partie du marché" : " pour tout le dossier"), phrase: x.phrase, source: x.source }));
      (l.chaque_question || []).forEach(x => out.push({ t: _gnLim(x) + " par question", phrase: x.phrase, source: x.source }));
      if (l.police && (l.police.police || l.police.taille)) out.push({ t: _gnLim(Object.assign({ type: "police" }, l.police)), phrase: l.police.phrase, source: l.police.source });
      return out;
    },
    atlNonControlees(lims) { return ((lims && lims.non_controlees) || []).map(x => _gnLim(x)).filter(Boolean); },
    atlSec() { const a = this.atl; return (a.st && a.st.sections.find(s => s.id === a.sel)) || null; },
    // Vague 6 (F) : « La dernière fois, l'acheteur a écrit : … » (carnet de notes d'un ancien marché, même famille de
    // critère, même acheteur d'abord) ; affiché seulement, jamais envoyé à l'IA.
    atlDerniereFois(s) { const st = this.atl.st; return (st && s && st.derniere_fois && st.derniere_fois[String(s.id)]) || null; },
    atlSecLims(s) { const st = this.atl.st; return (st && s) ? (st.limites || []).filter(l => l.portee === "section" && l.section_id === s.id) : []; },
    atlDocLims(st) { return ((st && st.limites) || []).filter(l => l.portee === "document"); },
    atlPieceLecture(p) { return atlLecturePiece(p); },
    atlCouvertureManque(st) { return atlManqueLecture(st && st.dossier_acheteur); },
    atlFaitsARelire(s) { const v = s && s.version_courante; return ((v && v.faits) || []).filter(f => f.statut !== "relu_par_vous" && f.type !== "reste"); },
    // Au-delà de ce que l'atelier détaille, les faits restants sont comptés (et bloquent l'export).
    atlFaitsReste(s) { const v = s && s.version_courante; return ((v && v.faits) || []).find(f => f.type === "reste" && f.statut !== "relu_par_vous") || null; },
    atlFaitsRelus(s) { const v = s && s.version_courante; return ((v && v.faits) || []).filter(f => f.statut === "relu_par_vous"); },
    atlFaitType(t) { return ATL_FAIT_TYPES[t] || "Fait"; },
    atlHtml(s) { const v = s && s.version_courante; return v ? atlMdToHtml(v.texte, v.faits, { refsPartenaire: !s.prive_visible }) : ""; },
    // La phrase telle qu'A0 la range garde l'espace laissée par un renvoi retiré (« salariés . ») : pas à l'écran.
    atlPhrase(f) { return atlPhraseHtml(String(f.phrase || "").replace(/\s+([.,])(?=\s|$)/g, "$1"), f.fait); },
    atlMotsEdit() { return atlMots(this.atl.edit.texte); },
    atlAEcrire() { const st = this.atl.st; return st ? st.sections.filter(s => s.statut === "a_ecrire" && s.peut_ecrire && !s.redaction_en_cours).length : 0; },
    atlEnCours() { const pid = this.atl.pid; return Object.values(this.atlJobs).filter(j => j.pid === pid); },
    atlAvert(st, code) { return ((st && st.blocage && st.blocage.avertissements) || []).find(x => x.code === code) || null; },
    atlBases(bases) { return atlBasesDispo(bases); },
    // Poids d'une partie et d'où il vient (comme dans « Comment vous serez noté »).
    atlPoidsTexte(s) {
      if (!s || !s.poids) return "";
      if (s.poids_source === "utilisateur") return "poids lu par vous : " + s.poids;
      if (s.poids_source === "reglement") return "poids écrit dans le règlement : " + s.poids;
      return "poids : " + s.poids;
    },
    // État de l'export en une pastille : jamais « Prêt » quand l'export ne passe que par une
    // dérogation, ni quand des parties restent à valider.
    atlEtatExport(d) {
      const b = d && d.blocage; if (!b) return { cls: "neutral", label: "" };
      if (!b.peut_exporter) return { cls: "neutral", label: "En préparation" };
      if (b.derogation) return { cls: "a_etudier", label: "Export avec dérogation" };
      const nv = (b.avertissements || []).find(x => x.code === "non_valide");
      if (nv) return { cls: "neutral", label: nv.nombre > 1 ? nv.nombre + " parties à valider" : "1 partie à valider" };
      return { cls: "go", label: "Prêt à exporter" };
    },
    atlEncoreOuvert(d) { const b = d && d.blocage; return b && b.derogation ? (b.raisons || []).map(r => r.message).join(" ") : ""; },
    // Une dérogation enregistrée pendant cette visite ne vaut plus : le dossier a changé depuis.
    atlDerogPerimee() { const st = this.atl.st, b = st && st.blocage; return !!(b && this.atl.lastDerog && b.bloque && !b.derogation && b.etat_hash !== this.atl.lastDerog); },

    // ── Ouvrir, recharger, choisir une partie ──
    atlOpen() {
      const p = this.ao.project; if (!p) return;
      if (this.atl.pid !== p.id) { this.atl = _atlInit(); this.atl.pid = p.id; }
      this.view = "atelier"; this._ecranOuvert("atelier"); this.aoAvancer();
      this.$nextTick(() => { const w = document.querySelector(".work"); if (w) w.scrollTop = 0; });
      this.atlLoad();
      if (this.atl.onglet === "repartition") this.atlRepLoad();      // « Qui écrit quoi » relu au retour
    },
    // Quitter l'atelier (bouton « Retour au marché », bouton précédent du navigateur, menu) : un texte non enregistré
    // est gardé sur cet appareil.
    _atlQuitter() {
      const a = this.atl;
      if (a.mode === "modifier" && a.edit && a.edit.dirty) { this._atlDraftSave(); this.notify("Votre texte non enregistré est gardé sur cet appareil : vous le retrouverez dans la partie."); }
    },
    atlBack() {
      this._atlQuitter();
      if (this._retourHistorique()) return;           // vague 2a : comme le bouton précédent du navigateur
      // Atelier ouvert directement (courriel « … a envoyé sa partie », favori) : la page du marché prend sa place dans
      // l'historique, sans nouvelle entrée ; son « Retour » mène alors à Mes marchés (relecture de la vague 2a : sinon
      // « Retour au marché » et « Retour » se renvoyaient l'un à l'autre sans fin).
      this._sansHistorique(() => { this.view = "aodetail"; this._ecranOuvert("aodetail"); });
      this.atlCardLoad();
      this.$nextTick(() => { const el = document.getElementById("atl-card"); if (el && el.scrollIntoView) el.scrollIntoView({ block: "center" }); });
    },
    async atlLoad(silent) {
      const a = this.atl, pid = a.pid; if (!pid) return;
      if (!silent) { a.loading = true; a.error = ""; }
      try {
        const qs = [];
        if (!a.st && a.base && a.base !== "auto") qs.push("base=" + encodeURIComponent(a.base));
        if (!a.st && (a.lotsChoix.length + a.lotsAjoutes.length) >= 2) {
          if (a.lotsChoix.length) qs.push("lots=" + encodeURIComponent(a.lotsChoix.join(",")));
          if (a.lotsAjoutes.length) qs.push("ajoutes=" + encodeURIComponent(JSON.stringify(a.lotsAjoutes)));
        }
        const q = qs.length ? "?" + qs.join("&") : "";
        const d = await this.api("GET", "/api/atelier/" + pid + q);
        if (this.atl.pid !== pid) return;
        if (d.dossier) { a.st = d; a.prop = null; } else { a.st = null; a.prop = d; }
        this._atlResume(d, pid);
        this._atlEntAuto();
        if (a.st) {
          const ids = a.st.sections.map(s => s.id);
          if (!ids.includes(a.sel)) this.atlSelect(ids[0] || null);
          else if (a.mode !== "modifier") this._atlDraftCheck();
          if (a.prep.open) this.atlPrepLoad();       // vague 6 (H) : la page lue suit le dossier
        }
      } catch (e) { if (silent) this.notify(e.message, "err"); else a.error = e.message || "Atelier indisponible pour le moment."; }
      finally { a.loading = false; }
    },
    // Reprise : une rédaction lancée avant (autre onglet, page rechargée) est suivie jusqu'au bout.
    _atlResume(d, pid) {
      ((d && d.sections) || []).forEach(s => {
        const rc = s.redaction_en_cours;
        if (rc && rc.job_id && !this.atlJobs[rc.job_id]) this._atlTrack({ id: rc.job_id, status: rc.statut, label: "" }, pid, [s.id], rc.action);
        else if (rc && rc.job_id) {
          const j = this.atlJobs[rc.job_id];          // une tâche pour plusieurs parties : toutes suivies
          if (j.pid === pid && !j.ids.includes(s.id)) j.ids.push(s.id);
        }
      });
    },
    atlSelect(sid) {
      const a = this.atl;
      if (a.mode === "modifier" && a.edit.sid === sid) { if (this.atlMobile) a.planOpen = false; return; }   // déjà en cours d'écriture
      if (a.mode === "modifier" && a.edit.dirty) { clearTimeout(this._atlDT); this._atlDraftSave(); this.notify("Votre texte non enregistré est gardé sur cet appareil."); }
      a.sel = sid; a.mode = "lire"; a.edit = { texte: "", base: null, dirty: false, sid: null };
      a.conflict = ""; a.factFocus = ""; a.srcFocus = ""; a.note = ""; a.ren = { on: false, v: "" }; a.src = null; a.passage = null;
      a.hist = { open: false, loading: false, list: [], sid: null };
      if (this.atlMobile) a.planOpen = false;
      this._atlDraftCheck();
    },
    atlGoSection(sid) {
      this.atlSelect(sid); if (this.atl.derog) this.atl.derog = null;
      this.$nextTick(() => { const el = document.getElementById("atl-centre"); if (el && el.scrollIntoView) el.scrollIntoView({ block: "start", behavior: "smooth" }); });
    },
    atlPreviewClick(ev) {
      const el = ev && ev.target && ev.target.closest ? ev.target.closest("[data-fait],[data-ref]") : null; if (!el) return;
      const f = el.getAttribute("data-fait"), r = el.getAttribute("data-ref");
      if (!f && r && r.charAt(0) !== "S") {
        const s = this.atlSec(), hit = this.atlFaitsSources(s).find(x => x.source && x.source.ref === r);
        if (!hit) return;
        this.atl.factFocus = hit.id;
        this.$nextTick(() => { const x = document.getElementById("atl-fs-" + hit.id); if (x) { const d = x.closest("details"); if (d) d.open = true; if (x.scrollIntoView) x.scrollIntoView({ block: "nearest", behavior: "smooth" }); x.focus(); } });
        return;
      }
      const id = f ? "atl-f-" + f : "atl-s-" + r;
      if (f) this.atl.factFocus = f; else this.atl.srcFocus = r;
      this.$nextTick(() => { const x = document.getElementById(id); if (x) { if (x.scrollIntoView) x.scrollIntoView({ block: "nearest", behavior: "smooth" }); x.focus(); } });
    },

    // ── Proposition (aucun dossier) et plan ──
    atlBase(b) { const a = this.atl; if (a.base === b.k || b.off) return; a.base = b.k; this.atlLoad(); },
    // « Comment vous serez noté » a changé depuis le plan : ajouter les critères confirmés et reprendre
    // les poids, sans rien retirer (aucune IA, aucun débit).
    async atlAppliquerGrille() {
      const a = this.atl; if (a.busy) return; a.busy = "grille";
      try {
        const d = await this.api("POST", this._atlUrl("/plan/grille"));
        a.st = d; const n = (d.application && d.application.ajoutees) || 0;
        this.notify(n ? (n > 1 ? n + " parties ajoutées au plan" : "1 partie ajoutée au plan") : "Poids mis à jour dans le plan");
        if (!a.st.sections.some(s => s.id === a.sel)) this.atlSelect((a.st.sections[0] || {}).id || null);
      } catch (e) { this.notify(e.message, "err"); this.atlLoad(true); }
      finally { a.busy = ""; }
    },
    // Aucun dossier du marché : l'import se fait sur la page du marché.
    atlImporterDce() {
      if (this.view === "atelier") this.atlBack();
      this.$nextTick(() => { const i = this.$refs.aoDce; if (i && i.click) i.click(); });
    },
    atlVersSavoirFaire() {
      const a = this.atl;
      if (a.mode === "modifier" && a.edit.dirty) { this._atlDraftSave(); this.notify("Votre texte non enregistré est gardé sur cet appareil : vous le retrouverez dans la partie."); }
      this.go("kb");
    },
    // « Ajouter une source » → « Mes preuves » (vague 3) : un texte en cours d'écriture est gardé sur l'appareil.
    atlVersPreuves() {
      const a = this.atl;
      if (a.mode === "modifier" && a.edit.dirty) { this._atlDraftSave(); this.notify("Votre texte non enregistré est gardé sur cet appareil : vous le retrouverez dans la partie."); }
      a.src = null;
      this.go("preuves");
    },
    async atlCreer() {
      const a = this.atl; if (a.busy) return; a.busy = "creer";
      try {
        const plus = (a.lotsChoix.length + a.lotsAjoutes.length) >= 2;
        const d = await this.api("POST", this._atlUrl(""), { base: a.base || "auto", sans_ia: !!a.sansIaPropose,
          lots: plus ? a.lotsChoix : [], lots_ajoutes: plus ? a.lotsAjoutes : [] });
        a.st = d; a.prop = null; this.atlSelect(((d.sections || [])[0] || {}).id || null);
        this.notify("Dossier de présentation créé : " + (d.sections || []).length + " parties" + (d.lots && d.lots.actif ? ", " + d.lots.liste.length + " parties du marché" : "") + (d.sans_ia && d.sans_ia.actif ? ", à rédiger sans IA" : ""));
      } catch (e) { if (e.code === "dossier_existe") this.atlLoad(); else this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    atlPlanOpen() { this.atl.plan = { base: "auto", busy: false, confirm: "" }; },
    async atlPlanOk(remplacer) {
      const a = this.atl, p = a.plan; if (!p || p.busy) return; p.busy = true;
      try {
        const d = await this.api("POST", this._atlUrl("/plan"), { base: p.base, remplacer: !!remplacer });
        a.st = d; a.plan = null; this.atlSelect(((d.sections || [])[0] || {}).id || null); this.notify("Plan reconstruit");
      } catch (e) { if (e.code === "plan_remplacement_a_confirmer") p.confirm = e.message; else this.notify(e.message, "err"); }
      finally { if (a.plan) a.plan.busy = false; }
    },
    async atlAjouter() {
      const a = this.atl, t = (a.add || "").trim(); if (a.busy) return;
      if (t.length < 2) { this.notify("Donnez un intitulé à cette partie.", "err"); return; }
      a.busy = "ajout";
      try { const r = await this.api("POST", this._atlUrl("/sections"), this.atlLots() ? { intitule: t, lot: a.addLot || "" } : { intitule: t }); a.add = ""; await this.atlLoad(true); this.atlSelect(r.id); this.notify("Partie ajoutée au plan"); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    atlRenOn() { const s = this.atlSec(); if (s) this.atl.ren = { on: true, v: s.intitule }; },
    async atlRenOk() {
      const a = this.atl, s = this.atlSec(), v = (a.ren.v || "").trim(); if (!s || a.busy) return;
      if (v === s.intitule) { a.ren = { on: false, v: "" }; return; }
      a.busy = "ren";
      try { await this.api("PATCH", this._atlUrl("/sections/" + s.id), { intitule: v }); a.ren = { on: false, v: "" }; await this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    async atlMove(s, dir) {
      const a = this.atl; if (!a.st || a.busy) return;
      const i = a.st.sections.findIndex(x => x.id === s.id), j = i + dir;
      if (i < 0 || j < 0 || j >= a.st.sections.length) return;
      a.busy = "move";
      try { await this.api("PATCH", this._atlUrl("/sections/" + s.id), { position: j }); await this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    // Confirmations de l'atelier : la fenêtre de l'application (comme « Marquer déposé »), jamais celle du navigateur.
    atlRetirerPartie(s) {
      const a = this.atl; if (!s || a.busy) return;
      this._convAsk({ title: "Retirer cette partie du plan ?", ok: "Retirer la partie", run: () => this._atlRetirer(s),
        lines: ["« " + s.titre + " » sort du plan. Ses versions restent gardées : vous pourrez la remettre."] });
    },
    async _atlRetirer(s) {
      const a = this.atl; if (!s || a.busy) return;
      this._atlEchecOublier(s.id);
      a.busy = "retirer";
      try { await this.api("DELETE", this._atlUrl("/sections/" + s.id)); this.notify("Partie retirée du plan"); await this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    async atlRemettre(r) {
      const a = this.atl; if (a.busy) return; a.busy = "remettre";
      try { const s = await this.api("POST", this._atlUrl("/sections/" + r.id + "/remettre")); await this.atlLoad(true); this.atlSelect(s.id); this.notify("Partie remise dans le plan"); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },

    // ── Brouillon local (coupure, onglet fermé) : jamais envoyé sans « Enregistrer » ──
    // Clé propre à l'utilisateur : un collègue sur le même poste ne retrouve pas le brouillon d'un autre.
    _atlDraftKey(sid) { return "adjugo_atl_" + ((this.user && this.user.id) || 0) + "_" + this.atl.pid + "_" + sid; },
    _atlDraftCheck() {
      const a = this.atl, s = this.atlSec(); a.draft = null; if (!s || !s.peut_ecrire) return;
      let d = null; try { d = JSON.parse(localStorage.getItem(this._atlDraftKey(s.id)) || "null"); } catch (e) { d = null; }
      if (!d || typeof d.t !== "string") return;
      if (atlDraftPerime(d)) { this._atlDraftClear(s.id); return; }        // plus de 7 jours : effacé
      const cur = (s.version_courante && s.version_courante.texte) || "";
      if (d.t.trim() === cur.trim()) { this._atlDraftClear(s.id); return; }
      a.draft = d;
    },
    _atlDraftSave() {
      const a = this.atl; if (!a.edit.sid) return;
      try { localStorage.setItem(this._atlDraftKey(a.edit.sid), JSON.stringify({ t: a.edit.texte, b: a.edit.base, at: Date.now() })); } catch (e) { /* stockage plein ou interdit : rien de plus */ }
    },
    _atlDraftClear(sid) { try { localStorage.removeItem(this._atlDraftKey(sid)); } catch (e) { /* rien */ } if (this.atl.sel === sid) this.atl.draft = null; },
    atlDraftWhen(d) { try { return d && d.at ? this.atlWhen(new Date(d.at).toISOString()) : ""; } catch (e) { return ""; } },
    atlDraftResume() {
      const a = this.atl, s = this.atlSec(), d = a.draft; if (!s || !d || this.atlMobile) return;
      const base = s.version_courante ? s.version_courante.id : null;
      a.mode = "modifier"; a.conflict = ""; a.edit = { texte: d.t, base, dirty: true, sid: s.id }; a.draft = null;
      a.note = d.b !== base ? "Ce brouillon partait d'une version plus ancienne : relisez-le avant d'enregistrer. La version actuelle restera dans l'historique." : "";
      this.$nextTick(() => { const ta = this.$refs.atlTa; if (ta) ta.focus(); });
    },
    atlDraftDrop() { const s = this.atlSec(); if (s) this._atlDraftClear(s.id); this.atl.draft = null; },

    // ── « J'écris moi-même » : éditeur simple (titres, listes, tableaux), enregistrement explicite ──
    atlEdit() {
      const a = this.atl, s = this.atlSec(); if (!s || !s.peut_ecrire || this.atlMobile) return;
      if (s.redaction_en_cours) { this.notify("Adjugo rédige cette partie : attendez la fin de la rédaction.", "err"); return; }
      this._atlEchecOublier(s.id);
      if (a.draft) { this.atlDraftResume(); return; }
      const v = s.version_courante;
      a.mode = "modifier"; a.conflict = ""; a.note = "";
      a.edit = { texte: (v && v.texte) || "", base: v ? v.id : null, dirty: false, sid: s.id };
      this.$nextTick(() => { const ta = this.$refs.atlTa; if (ta) ta.focus(); });
    },
    atlInput() { this.atl.edit.dirty = true; clearTimeout(this._atlDT); this._atlDT = setTimeout(() => this._atlDraftSave(), 500); },
    atlEditCancel() {
      const a = this.atl;
      if (!a.edit.dirty) { this._atlEditFermer(); return; }
      this._convAsk({ title: "Abandonner vos modifications ?", ok: "Abandonner les modifications", run: () => this._atlEditFermer(),
        lines: ["Les modifications non enregistrées de cette partie seront perdues, y compris la copie gardée sur cet appareil."] });
    },
    _atlEditFermer() {
      const a = this.atl;
      clearTimeout(this._atlDT);
      if (a.edit.sid) this._atlDraftClear(a.edit.sid);
      a.mode = "lire"; a.edit = { texte: "", base: null, dirty: false, sid: null }; a.conflict = ""; a.note = "";
    },
    atlTool(kind) {
      const ta = this.$refs.atlTa, a = this.atl; if (!ta) return;
      const t = a.edit.texte, s0 = ta.selectionStart || 0, s1 = ta.selectionEnd || 0;
      const ls = t.lastIndexOf("\n", s0 - 1) + 1;
      let pos;
      if (kind === "titre" || kind === "liste") {
        const pre = kind === "titre" ? "## " : "- ";
        let le = t.indexOf("\n", Math.max(s0, s1 > s0 && t[s1 - 1] === "\n" ? s1 - 1 : s1)); if (le < 0) le = t.length;
        const bloc = t.slice(ls, le).split("\n").map(l => pre + l.replace(/^\s*(#{1,6}\s+|[-*+•]\s+)/, "")).join("\n");
        a.edit.texte = t.slice(0, ls) + bloc + t.slice(le); pos = ls + bloc.length;
      } else {
        const ins = (s1 === 0 || t[s1 - 1] === "\n" ? "" : "\n") + "\n| Colonne 1 | Colonne 2 |\n| --- | --- |\n|  |  |\n";
        a.edit.texte = t.slice(0, s1) + ins + t.slice(s1); pos = s1 + ins.length;
      }
      this.atlInput();
      this.$nextTick(() => { ta.focus(); ta.setSelectionRange(pos, pos); });
    },
    async atlSave() {
      const a = this.atl, s = this.atlSec(); if (!s || a.busy || a.mode !== "modifier") return;
      if (a.edit.texte.length > 60000) { this.notify("Le texte dépasse 60 000 caractères : raccourcissez-le avant d'enregistrer.", "err"); return; }
      clearTimeout(this._atlDT); this._atlDraftSave();
      this._atlEchecOublier(s.id);
      a.busy = "save";
      try {
        const r = await this.api("PUT", this._atlUrl("/sections/" + s.id + "/texte"), { texte: a.edit.texte, base_version_id: a.edit.base });
        this._atlDraftClear(s.id); this._atlPut(r);
        a.mode = "lire"; a.edit = { texte: "", base: null, dirty: false, sid: null }; a.note = ""; a.conflict = "";
        this.notify(r.statut === "a_revalider" ? "Texte enregistré : cette partie est à revalider" : "Texte enregistré");
        this.atlLoad(true);
      } catch (e) {
        if (e.code === "texte_modifie_entre_temps") a.conflict = e.message;
        else this.notify(e.message, "err");
      } finally { a.busy = ""; }
    },
    // Conflit : le texte saisi reste gardé sur l'appareil ; on recharge la partie, puis « Reprendre ».
    async atlConflitRecharger() {
      const a = this.atl; this._atlDraftSave();
      a.mode = "lire"; a.edit = { texte: "", base: null, dirty: false, sid: null }; a.conflict = ""; a.note = "";
      await this.atlLoad(true); this._atlDraftCheck();
    },
    async atlCopier() {
      try { await navigator.clipboard.writeText(this.atl.edit.texte || ""); this.notify("Votre texte est copié"); }
      catch (e) { this.notify("Copie impossible : sélectionnez le texte et copiez-le à la main", "err"); }
    },
    _atlPut(r) {
      const st = this.atl.st; if (!st || !r || !r.id) return;
      const i = st.sections.findIndex(x => x.id === r.id);
      if (i >= 0) { if (!r.compteur) r.compteur = st.sections[i].compteur; st.sections.splice(i, 1, r); }
    },

    // ── Le moteur : rédiger, raccourcir (tâches de fond, suivies toutes les 2 s) ──
    // « Mon savoir-faire » vide, première rédaction (1 analyse) : on prévient avant de débiter.
    _atlLignesSavoirFaire() {
      const st = this.atl.st;
      if (!st || !st.savoir_faire || !st.savoir_faire.vide || (st.quota && st.quota.analyse_debitee)) return [];
      return [{ t: "« Mon savoir-faire » est vide : sans vos anciens dossiers ni vos fiches, Adjugo écrira surtout des « [À compléter] ».", warn: true },
              "La première rédaction compte pour 1 analyse de votre forfait."];
    },
    // Une seule fenêtre de confirmation, avec tout ce qu'il faut savoir avant de lancer (rien si rien à dire).
    _atlAvantLancer(title, ok, lines, go) {
      const all = (lines || []).concat(this._atlLignesSavoirFaire());
      if (!all.length) { go(); return; }
      this._convAsk({ title, ok, lines: all, run: go });
    },
    atlRediger(s) {
      const nouvelle = !!s.version_courante;
      this._atlAvantLancer(nouvelle ? "Rédiger une nouvelle version ?" : "Rédiger avec Adjugo ?",
        nouvelle ? "Rédiger une nouvelle version" : "Rédiger quand même",
        (nouvelle ? ["Adjugo va rédiger une nouvelle version de « " + s.titre + " ». Le texte actuel reste dans l'historique : vous pourrez y revenir."] : [])
          .concat(this._atlLignesEntretien()),
        () => this._atlLancer("/sections/" + s.id + "/rediger", { accepte_debit: false }, "rediger"));
    },
    atlRaccourcir(s) {
      this._atlAvantLancer("Raccourcir avec Adjugo ?", "Raccourcir quand même", [],
        () => this._atlLancer("/sections/" + s.id + "/raccourcir", { accepte_debit: false }, "raccourcir"));
    },
    atlRedigerTout() {
      const n = this.atlAEcrire(); if (!n) return;
      this._atlAvantLancer("Rédiger avec Adjugo ?", "Rédiger quand même", this._atlLignesEntretien(),
        () => this._atlLancer("/rediger", { accepte_debit: false }, "rediger"));
    },

    // ── Entretien chantier (rédaction, vague 5 — D : « Adjugo demande au lieu de deviner ») ──
    // Contrat : docs/REDACTION_V5.md (section D). Les questions viennent de la banque, sans IA ; chacune porte la phrase
    // du dossier qui la motive. Les réponses forment la fiche chantier (faits « déclaré par vous ») ; une question posée
    // à un partenaire se répond dans SON espace. Sur téléphone : répondre et passer restent possibles.
    atlEntCpt() { const st = this.atl.st; return (st && st.entretien) || {}; },
    atlEntTitre() {
      const e = this.atlEntCpt(), n = e.prepare ? (e.total || 0) : (e.proposees || 0);
      return n + " question" + (n > 1 ? "s" : "") + " sur ce chantier";
    },
    atlEntPill() {
      const e = this.atlEntCpt();
      if (!e.prepare) return { cls: "neutral", label: "À ouvrir" };
      if (e.a_repondre) return { cls: "a_etudier", label: e.a_repondre + " à répondre" };
      return { cls: "go", label: "Toutes traitées" };
    },
    atlEntSous() {
      const e = this.atlEntCpt(), out = [];
      if (e.repondues) out.push(e.repondues + (e.repondues > 1 ? " réponses" : " réponse"));
      if (e.passees) out.push(e.passees + (e.passees > 1 ? " passées" : " passée"));
      if (e.chez_partenaires) out.push(e.chez_partenaires + (e.chez_partenaires > 1 ? " posées à vos partenaires" : " posée à un partenaire"));
      return out.length ? out.join(" · ") + "." : "Répondez avant de rédiger : Adjugo s'appuiera sur vos réponses au lieu de deviner.";
    },
    atlEntStCls(q) { return ({ repondue: "go", sautee: "a_etudier", sans_objet: "neutral", a_repondre: "neutral" })[q.statut] || "neutral"; },
    _atlEntSet(d) {
      const ent = this.atl.ent, pid = this.atl.pid;
      ent.d = d; ent.err = "";
      (d.questions || []).forEach(q => {
        if (q.id && q.adresse.type !== "invitation" && !ent.edits[q.id]) ent.edits[q.id] = { texte: "", preuve_id: null, open: false };
      });
      if (this.atl.st && d.compteurs) this.atl.st.entretien = Object.assign({}, this.atl.st.entretien || {}, d.compteurs);
      const ec = d.ia && d.ia.en_cours;           // recherche avec l'IA lancée avant (page rechargée) : suivie jusqu'au bout
      if (ec && ec.job_id && !this.atlJobs[ec.job_id]) this._atlTrack({ id: ec.job_id, status: ec.statut }, pid, [], "entretien");
    },
    async atlEntLoad(preparer) {
      const ent = this.atl.ent, pid = this.atl.pid; if (!pid) return;
      ent.loading = true; ent.err = "";
      try {
        let d = await this.api("GET", this._atlUrl("/entretien"));
        if (preparer && !d.prepare) {
          // Dossier d'avant l'entretien : le préparer (sans IA, idempotent) ; la démo, en lecture, garde la proposition.
          try { d = await this.api("POST", this._atlUrl("/entretien")); }
          catch (e) { if (e.status !== 403) throw e; }
        }
        if (this.atl.pid !== pid) return;
        this._atlEntSet(d);
      } catch (e) { ent.err = e.message || "Les questions sont indisponibles pour le moment."; }
      finally { ent.loading = false; }
    },
    atlEntOuvrir() {
      const ent = this.atl.ent; ent.open = !ent.open;
      if (ent.open) this.atlEntLoad(true);
    },
    // Avant la rédaction des parties notées : à la première ouverture d'un atelier encore sans texte, les questions
    // sont dépliées d'elles-mêmes (une fois par visite ; les parties tirées du groupement ne comptent pas).
    _atlEntAuto() {
      const a = this.atl, st = a.st, ent = a.ent, e = (st && st.entretien) || {};
      if (!st || ent.auto) return;
      ent.auto = true;
      if ((e.prepare ? e.a_repondre : e.proposees) && st.sections.every(s => s.genere || !s.version_courante)) { ent.open = true; this.atlEntLoad(true); }
    },
    atlEntModifier(q) {
      const ent = this.atl.ent;
      ent.edits[q.id] = { texte: (q.reponse && q.reponse.texte) || "", preuve_id: (q.reponse && q.reponse.preuve_id) || null, open: true };
    },
    async atlEntRepondre(q, statut) {
      const ent = this.atl.ent; if (ent.busy) return;
      const ed = ent.edits[q.id] || {}, body = { statut, lock_version: q.lock_version };
      if (statut === "repondue") {
        body.reponse = String(ed.texte || "").trim();
        if (ed.preuve_id) body.preuve_id = ed.preuve_id;
        if (!body.reponse && !body.preuve_id) { this.notify("Écrivez votre réponse, ou passez la question.", "err"); return; }
      }
      ent.busy = "q" + q.id;
      try {
        const d = await this.api("PUT", this._atlUrl("/entretien/" + q.id), body);
        ent.edits[q.id] = { texte: "", preuve_id: null, open: false };
        this._atlEntSet(d);
        this.notify(statut === "repondue" ? "Réponse ajoutée à la fiche chantier"
          : statut === "sautee" ? "Question passée : la partie concernée gardera « [À compléter] »" : "Question sans objet sur ce chantier");
      } catch (e) {
        this.notify(e.message, "err");
        if (e.code === "question_modifiee" || e.code === "question_introuvable" || e.code === "question_d_un_partenaire") this.atlEntLoad(false);
      } finally { ent.busy = ""; }
    },
    async atlEntAdresser(q, val, confirmer) {
      const ent = this.atl.ent; if (ent.busy) return;
      const invite_id = val ? Number(val) : null;
      ent.busy = "ad" + q.id;
      try {
        const d = await this.api("PUT", this._atlUrl("/entretien/" + q.id + "/adresse"), { invite_id, confirmer: !!confirmer });
        this._atlEntSet(d);
        this.notify(invite_id ? "Question posée à votre partenaire : il la trouve dans son espace de rédaction" : "Question reprise pour votre entreprise");
      } catch (e) {
        ent.v++;                                    // le menu « Posée à » revient à la valeur enregistrée
        if (e.code === "reponse_a_confirmer") {
          this._convAsk({ title: "Poser la question à un autre ?", ok: "Confirmer", lines: [e.message], run: () => this.atlEntAdresser(q, val, true) });
        } else this.notify(e.message, "err");
      } finally { ent.busy = ""; }
    },
    atlEntIA() { this._atlLancer("/entretien/ia", { accepte_debit: false }, "entretien"); },
    // Avant de rédiger : les questions encore sans réponse et celles passées (dans la même fenêtre de confirmation).
    _atlLignesEntretien() {
      const e = this.atlEntCpt(), out = [];
      const n = e.prepare ? (e.a_repondre || 0) : (e.proposees || 0);
      if (n) out.push({ t: (n > 1 ? n + " questions sur ce chantier attendent" : "Une question sur ce chantier attend") + " une réponse : sans elle, Adjugo n'écrit rien à ce sujet et laisse « [À compléter] » si la partie en a besoin. Vous pouvez d'abord y répondre (« " + this.atlEntTitre() + " », en haut de l'atelier).", warn: true });
      if (e.passees) out.push(e.passees > 1 ? e.passees + " questions passées : leur partie gardera « [À compléter] »." : "Une question passée : sa partie gardera « [À compléter] ».");
      return out;
    },
    // Échec d'une rédaction : le message reste affiché DANS la partie jusqu'à la prochaine action sur elle.
    _atlEchecCle(pid, sid) { return pid + ":" + sid; },
    atlEchec(s) { return (s && this.atlEchecs[this._atlEchecCle(this.atl.pid, s.id)]) || ""; },
    _atlEchecNoter(pid, ids, msg) { (ids || []).forEach(id => { this.atlEchecs[this._atlEchecCle(pid, id)] = msg; }); },
    _atlEchecOublier(sid) { const k = this._atlEchecCle(this.atl.pid, sid); if (this.atlEchecs[k]) delete this.atlEchecs[k]; },
    async _atlLancer(path, body, action) {
      const a = this.atl, pid = a.pid; if (a.busy) return;
      a.busy = "lancer";
      try {
        const r = await this.api("POST", this._atlUrl(path), body);
        (r.section_ids || []).forEach(id => this._atlEchecOublier(id));
        if (a.st && r.quota) a.st.quota = r.quota;
        this._atlTrack(r.tache, pid, r.section_ids, action);
        (r.section_ids || []).forEach(id => { const x = a.st && a.st.sections.find(y => y.id === id); if (x) x.redaction_en_cours = { job_id: r.tache.id, action, statut: r.tache.status }; });
        const n = (r.section_ids || []).length;
        if (action === "entretien") { this.notify("Adjugo cherche d'autres questions sur ce chantier. Vous pouvez continuer ailleurs."); this.atlEntLoad(false); return; }
        this.notify(action === "harmoniser" ? "Adjugo relie les parts des membres. Vous pouvez continuer ailleurs."
          : action === "raccourcir" ? "Adjugo raccourcit la partie. Vous pouvez continuer ailleurs." : (n > 1 ? "Adjugo rédige " + n + " parties. Vous pouvez continuer ailleurs." : "Adjugo rédige la partie. Vous pouvez continuer ailleurs."));
      } catch (e) {
        if (e.code === "debit_a_confirmer") a.debit = { message: e.message, cout: (e.detail && e.detail.cout) || 1, path, body, action };
        else this.notify(e.message, "err");
      } finally { a.busy = ""; }
    },
    atlDebitOk() { const d = this.atl.debit; if (!d) return; this.atl.debit = null; this._atlLancer(d.path, Object.assign({}, d.body, { accepte_debit: true }), d.action); },
    _atlTrack(t, pid, ids, action) {
      if (!t || !t.id) return;
      this.atlJobs[t.id] = { id: t.id, pid, ids: ids || [], status: t.status || "pending", action: action || "rediger" };
      if (!this._atlTimer) this._atlTimer = setInterval(() => this._atlPoll(), 2000);
    },
    async _atlPoll() {
      const ids = Object.keys(this.atlJobs);
      if (!ids.length) { clearInterval(this._atlTimer); this._atlTimer = null; return; }
      if (this._atlPolling || !this.token) return;
      this._atlPolling = true;
      try {
        for (const id of ids) {
          const j = this.atlJobs[id]; if (!j) continue;
          let r;
          try { r = await this.api("GET", "/api/atelier/" + j.pid + "/taches/" + j.id); }
          catch (e) { if (e.status === 404) delete this.atlJobs[id]; continue; }
          j.status = r.status;
          if (r.status === "done" || r.status === "error") { delete this.atlJobs[id]; this._atlJobFini(j, r); }
        }
      } finally { this._atlPolling = false; }
    },
    _atlJobFini(j, r) {
      if (j.action === "entretien" || r.kind === "atelier_entretien") {
        // Entretien chantier (vague 5) : des questions de plus, chacune avec sa phrase du dossier ; rien de retenu ou
        // IA en panne : rien n'est décompté (le serveur le dit).
        const res = r.result || {}, ok = r.status !== "error";
        const msg = ok ? (res.message || "Recherche terminée.") : (r.error || "La recherche de questions n'a pas abouti. Rien n'a été décompté.");
        this.notify(msg, ok && Number(res.ajoutees) > 0 ? "ok" : "err");
        if (this.atl.pid === j.pid) { this.atl.live = msg; this.atlEntLoad(false); }
        if (this.view === "atelier" && this.atl.pid === j.pid) this.atlLoad(true);
        return;
      }
      if (j.action === "harmoniser" || r.kind === "atelier_harmoniser") {
        const res = r.result || {}, ok = r.status !== "error";
        const msg = ok ? (res.message || "Harmonisation terminée : relisez les parties touchées.")
          : (r.error || "L'harmonisation n'a pas abouti. Rien n'a été décompté.");
        this.notify(msg, ok && Number(res.ajoutees) > 0 ? "ok" : "err");
        if (this.atl.pid === j.pid) { this.atl.live = msg; if (this.atlRepVue()) this.atlRepLoad(); }
        if (this.view === "atelier" && this.atl.pid === j.pid) this.atlLoad(true);
        return;
      }
      const raccourcir = j.action === "raccourcir" || r.kind === "atelier_raccourcir";
      if (r.status === "error") {
        const msg = r.error || "La rédaction n'a pas abouti. Rien n'a été débité.";
        this.notify(msg, "err");
        this._atlEchecNoter(j.pid, j.ids, msg);
        if (this.atl.pid === j.pid) this.atl.live = msg;
      } else {
        const res = r.result || {}, ok = (res.sections || []).filter(x => x.ok).length;
        let msg = raccourcir ? "Partie raccourcie : relisez-la"
          : (ok > 1 ? ok + " parties rédigées : relisez-les" : "Partie rédigée : relisez-la");
        if (res.message) msg += ". " + res.message;
        this.notify(msg, res.echecs ? "err" : "ok");
        if (this.atl.pid === j.pid) this.atl.live = msg;
        const ko = (res.sections || []).filter(x => !x.ok).map(x => x.section_id);
        if (ko.length) this._atlEchecNoter(j.pid, ko, (raccourcir ? "Le raccourcissement" : "La rédaction")
          + " de cette partie n'a pas abouti (service d'IA indisponible) : rien n'a été débité pour elle, réessayez.");
      }
      if (this.view === "atelier" && this.atl.pid === j.pid) this.atlLoad(true);
      if (this.view === "aodetail" && this.ao.project && this.ao.project.id === j.pid) this.atlCardLoad();
    },

    // ── Relire, valider, traiter un fait « à relire » ──
    async atlRelu() {
      const a = this.atl, s = this.atlSec(), v = s && s.version_courante; if (!v || a.busy) return;
      this._atlEchecOublier(s.id);
      a.busy = "relu";
      try { const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/relu"), { version_id: v.id }); this._atlPut(r); this.notify("Partie marquée comme relue"); this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); if (e.code === "texte_modifie_entre_temps") this.atlLoad(true); }
      finally { a.busy = ""; }
    },
    atlValider() {
      const a = this.atl, s = this.atlSec(), v = s && s.version_courante; if (!v || a.busy) return;
      const open = [];
      if (s.faits_a_relire) open.push(s.faits_a_relire + " fait" + (s.faits_a_relire > 1 ? "s" : "") + " à relire");
      if (s.a_completer) open.push(s.a_completer + " passage" + (s.a_completer > 1 ? "s" : "") + " « À compléter »");
      if (!open.length) { this._atlValider(s, v); return; }
      this._convAsk({ title: "Valider cette partie ?", ok: "Valider quand même", run: () => this._atlValider(s, v),
        lines: ["Il reste " + open.join(" et ") + " dans cette partie.",
                { t: "L'export restera bloqué tant qu'ils ne sont pas traités.", warn: true }] });
    },
    async _atlValider(s, v) {
      const a = this.atl; if (!s || !v || a.busy) return;
      this._atlEchecOublier(s.id);
      a.busy = "valider";
      try { const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/valider"), { version_id: v.id }); this._atlPut(r); this.notify("Partie validée"); this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); if (e.code === "texte_modifie_entre_temps") this.atlLoad(true); }
      finally { a.busy = ""; }
    },
    async atlFait(f, statut) {
      const a = this.atl, s = this.atlSec(); if (!s || a.busy) return;
      this._atlEchecOublier(s.id);
      a.busy = "fait:" + f.id;
      try { const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/faits/" + encodeURIComponent(f.id)), { statut }); this._atlPut(r.section); this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    // ── « Chaque fait a sa source » (vague 3) : libellés seulement après la calibration ──
    atlLib() { const st = this.atl.st; return !!(st && st.sources_faits && st.sources_faits.libelles); },
    atlBulleSources() { const st = this.atl.st; return (st && st.sources_faits && st.sources_faits.bulle) || ""; },
    atlControle(s) { const v = s && s.version_courante; return (v && v.controle && v.controle.libelles && v.controle.total) ? v.controle : null; },
    atlFaitsSources(s) { const v = s && s.version_courante; return (v && v.faits_sources) || []; },
    atlEcartees() { const st = this.atl.st; return (st && st.sources_faits && st.sources_faits.preuves_ecartees) || []; },
    atlSrcLib(src) { return atlSrcLib(src); },
    atlNatureLib(n) { return ATL_NATURES[n] || n; },
    atlDeclChamps() { const x = this.atl.src; return (x && ATL_DECL_CHAMPS[x.nature]) || []; },
    atlDeclLib(k) { return ATL_DECL_LIB[k] || k; },
    // Relit les sources de la partie (une preuve ajoutée, retirée ou expirée) : sans IA, sans changer le texte.
    async atlRecontroler() {
      const a = this.atl, s = this.atlSec(); if (!s || a.busy) return;
      a.busy = "controle";
      try { const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/controle")); this._atlPut(r); this.notify("Sources relues"); this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    // « Ajouter une source » : relier une preuve qui contient ce fait, ou le déclarer (jamais l'IA, texte intact).
    async atlSourceOuvrir(f) {
      const a = this.atl, s = this.atlSec(); if (!s) return;
      if (a.src && a.src.fid === f.id) { a.src = null; return; }
      a.src = { fid: f.id, fait: f.fait, loading: true, d: null, nature: "", valeur: {}, err: "" };
      try {
        const d = await this.api("GET", this._atlUrl("/sections/" + s.id + "/faits/" + encodeURIComponent(f.id) + "/sources"));
        if (!a.src || a.src.fid !== f.id) return;
        const prop = d.proposition || {};
        a.src.d = d; a.src.nature = prop.nature || ""; a.src.valeur = Object.assign({}, prop.valeur || {});
      } catch (e) { if (a.src) a.src.err = e.message; }
      finally { if (a.src) a.src.loading = false; }
    },
    atlSourceNature(n) { const x = this.atl.src; if (!x) return; x.nature = n; const keep = {}; (ATL_DECL_CHAMPS[n] || []).forEach(k => { if (x.valeur[k] != null) keep[k] = x.valeur[k]; }); x.valeur = keep; },
    async _atlSourceEnvoyer(body) {
      const a = this.atl, s = this.atlSec(), x = a.src; if (!s || !x || a.busy) return;
      a.busy = "source"; x.err = "";
      try {
        const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/faits/" + encodeURIComponent(x.fid) + "/source"), body);
        this._atlPut(r.section); a.src = null; this.notify("Source ajoutée : le fait est relié à « Mes preuves »."); this.atlLoad(true);
      } catch (e) { x.err = e.message; }
      finally { a.busy = ""; }
    },
    atlSourceRelier(p) { return this._atlSourceEnvoyer({ preuve_id: p.id }); },
    atlSourceDeclarer() {
      const x = this.atl.src; if (!x) return;
      const v = {}; Object.keys(x.valeur || {}).forEach(k => { const val = x.valeur[k]; if (val !== "" && val != null) v[k] = val; });
      return this._atlSourceEnvoyer({ nature: x.nature, valeur: v });
    },
    // Le passage exact d'une preuve « trouvé dans vos documents » (lien vers le passage).
    async atlPassage(f) {
      const a = this.atl, src = f && f.source; if (!src) return;
      if (a.passage && a.passage.id === f.id) { a.passage = null; return; }
      if (!src.lien || src.lien.indexOf("/api/preuves/") !== 0) { a.passage = { id: f.id, d: { passage: src.extrait || "", avant: "", apres: "", doc_nom: src.doc_nom || "" } }; return; }
      a.passage = { id: f.id, d: null };
      try { const d = await this.api("GET", src.lien); if (a.passage && a.passage.id === f.id) a.passage.d = d; }
      catch (e) { a.passage = null; this.notify(e.message, "err"); }
    },
    // Corriger / Retirer : c'est VOUS qui modifiez le texte (jamais l'IA) ; rien ne part sans « Enregistrer ».
    atlFaitCorriger(f) {
      const a = this.atl; if (this.atlMobile) return;
      if (a.mode !== "modifier") this.atlEdit();
      this.$nextTick(() => {
        const ta = this.$refs.atlTa; if (!ta) return;
        const r = atlFaitPos(a.edit.texte, f.fait, f.phrase);
        if (!r) { a.note = "Ce fait n'est plus dans le texte modifié."; return; }
        ta.focus(); ta.setSelectionRange(r[0], r[1]);
        const lignes = a.edit.texte.slice(0, r[0]).split("\n").length;
        ta.scrollTop = Math.max(0, (lignes - 3) * 21);
        a.note = "Corrigez le fait sélectionné dans le texte, puis enregistrez.";
      });
    },
    atlFaitRetirer(f) {
      const a = this.atl; if (this.atlMobile) return;
      if (a.mode !== "modifier") this.atlEdit();
      this.$nextTick(() => {
        if (a.mode !== "modifier") return;
        const t2 = atlRetirerPhrase(a.edit.texte, f.fait, f.phrase);
        if (t2 == null) { a.note = "Adjugo ne retrouve plus cette phrase dans le texte : retirez-la à la main."; return; }
        a.edit.texte = t2; this.atlInput();
        a.note = "Phrase retirée du texte : enregistrez pour confirmer, ou annulez.";
      });
    },

    // ── Historique des versions ──
    async atlHist() {
      const a = this.atl, s = this.atlSec(); if (!s) return;
      if (a.hist.open && a.hist.sid === s.id) { a.hist.open = false; return; }
      a.hist = { open: true, loading: true, list: [], sid: s.id };
      try { const r = await this.api("GET", this._atlUrl("/sections/" + s.id)); if (a.hist.sid === s.id) a.hist.list = r.versions || []; }
      catch (e) { this.notify(e.message, "err"); a.hist.open = false; }
      finally { a.hist.loading = false; }
    },
    async atlVoir(v) {
      const s = this.atlSec(); if (!s) return;
      try { const r = await this.api("GET", this._atlUrl("/sections/" + s.id + "/versions/" + v.id)); this.atl.vue = { v: r, titre: s.titre, courante: !!(s.version_courante && s.version_courante.id === v.id) }; }
      catch (e) { this.notify(e.message, "err"); }
    },
    atlRestaurer(v) {
      const a = this.atl, s = this.atlSec(); if (!s || a.busy) return;
      if (a.mode === "modifier" && a.edit.dirty) { this.notify("Enregistrez ou annulez d'abord votre modification en cours.", "err"); return; }
      this._convAsk({ title: "Revenir à la version " + v.numero + " ?", ok: "Revenir à cette version", run: () => this._atlRestaurer(s, v),
        lines: ["Elle devient la version actuelle ; le texte actuel reste dans l'historique."] });
    },
    async _atlRestaurer(s, v) {
      const a = this.atl; if (!s || a.busy) return;
      this._atlEchecOublier(s.id);
      a.busy = "restaurer";
      try {
        const r = await this.api("POST", this._atlUrl("/sections/" + s.id + "/restaurer"), { version_id: v.id, base_version_id: s.version_courante ? s.version_courante.id : null });
        this._atlPut(r); a.vue = null; a.hist.open = false; a.mode = "lire";
        this.notify("Version " + v.numero + " remise"); this.atlLoad(true);
      } catch (e) { this.notify(e.message, "err"); if (e.code === "texte_modifie_entre_temps") this.atlLoad(true); }
      finally { a.busy = ""; }
    },
    atlVueHtml() { const x = this.atl.vue; return x ? atlMdToHtml(x.v.texte, []) : ""; },

    // ── Export (Word, PDF), blocage et dérogation inscrite au journal (décision 2b) ──
    // Rédaction, vague 5 : le mode « sans IA » de CE dossier (aucune IA de rédaction, pour personne).
    atlSansIa() { const st = this.atl.st; return !!(st && st.sans_ia && st.sans_ia.actif); },
    async atlSansIaChoisir(val, el) {
      // `el` : la case cochée (options de l'export). Refus (démo, réseau, 409) : elle revient à l'état enregistré
      // (Vue ne la repeint pas, la valeur liée n'ayant pas changé).
      const a = this.atl;
      const remettre = () => { if (el) el.checked = this.atlSansIa(); };
      if (!a.st || a.busy) { remettre(); return; }
      a.busy = "sansia";
      try {
        const r = await this.api("PUT", this._atlUrl("/options"), { sans_ia: !!val });
        a.st.export.options = r.options; if (r.sans_ia) a.st.sans_ia = r.sans_ia; a.sansIaPropose = false;
        this.notify(val ? "Ce dossier se rédige maintenant sans IA" : "L'aide de l'IA est de nouveau proposée pour ce dossier");
        this.atlLoad(true);
      } catch (e) { this.notify(e.message, "err"); remettre(); }
      finally { a.busy = ""; }
    },
    // « 11 exigences traitées sur 12 » : pastille, libellé, et les choix (dite traitée par vous, retirée).
    atlExCls(x) { return ({ traitee: "go", traitee_selon_vous: "neutral", a_traiter: "a_etudier", retiree: "neutral" })[x.statut] || "neutral"; },
    atlExLib(x) { return ({ traitee: "traitée", traitee_selon_vous: "traitée, selon vous", a_traiter: "à traiter", retiree: "retirée" })[x.statut] || ""; },
    async atlExChoix(x, choix) {
      const a = this.atl; if (!a.st || a.busy) return; a.busy = "ex:" + x.id;
      try {
        const r = await this.api("POST", "/api/sourcing/grille/element", { project_id: a.pid, type: "exigence", element_id: x.id, choix });
        this.notify(choix === "traitee" ? "Exigence dite traitée par vous" : choix === "ecarte" ? "Exigence retirée de la liste" : "Choix annulé");
        if (this.ao.project && this.ao.project.id === a.pid) this._aoGrilleMaj(this.ao.project, r);   // la carte du marché suit
        await this.atlLoad(true);
      } catch (e) { this.notify(e.message, "err"); }
      finally { a.busy = ""; }
    },
    async atlOption(k, val, el) {
      const a = this.atl; if (!a.st) return;
      try { const r = await this.api("PUT", this._atlUrl("/options"), { [k]: !!val }); a.st.export.options = r.options; this.atlLoad(true); }
      catch (e) { this.notify(e.message, "err"); if (el) el.checked = !!(a.st.export.options || {})[k]; this.atlLoad(true); }
    },
    // `l` (rédaction, vague 6) : le lot à exporter (un fichier par lot), avec SON état et SA dérogation.
    async atlExport(fmt, l) {
      const a = this.atl, st = a.st; if (!st || a.busy) return;
      if (a.mode === "modifier" && a.edit.dirty) { this.notify("Enregistrez d'abord votre texte : l'export reprend les textes enregistrés.", "err"); return; }
      const b = l ? l.blocage : st.blocage, ex = l ? l.export : st.export;
      a.busy = "export:" + (l ? l.numero + ":" : "") + fmt; this.pending++;
      try {
        // Vague 6 (H) : la case « Joindre une page "Comment ce dossier a été préparé" » vaut pour CET export
        // (chaque fichier de lot a sa propre page, avec ses parties).
        const corps = l ? { format: fmt, etat_hash: b && b.etat_hash, lot: l.numero, page_preparation: !!a.prepJoindre }
          : { format: fmt, etat_hash: st.blocage && st.blocage.etat_hash, page_preparation: !!a.prepJoindre };
        const r = await fetch(this._atlUrl("/export"), { method: "POST", headers: { Authorization: "Bearer " + this.token, "Content-Type": "application/json" },
          body: JSON.stringify(corps) });
        if (r.status === 401) { this.sessionPerdue(await r.json().then(j => j && j.detail, () => "")); return; }
        if (!r.ok) {
          const j = await r.json().catch(() => ({})), d = j && j.detail;
          const msg = (d && typeof d === "object" && d.message) || (typeof d === "string" && d) || (r.status === 429 ? TOO_MANY_MSG : "Export impossible pour le moment.");
          if (d && d.code === "export_bloque" && l) { this._atlDerogOpen(d, fmt, l.numero); return; }   // le lot exporté
          if (d && d.code === "export_bloque") { this._atlDerogOpen(d, fmt); return; }
          if (d && d.code === "etat_modifie") { await this.atlLoad(true); this.notify(msg, "err"); return; }
          throw new Error(msg);
        }
        const nom = atlNomFichier(r.headers.get("content-disposition"), fmt === "pdf" ? ex.nom_fichier_pdf : ex.nom_fichier_docx);
        this.saveBlob(await r.blob(), nom);
        this.notify((l ? "Fichier de la " + partieLot(l.numero, true) + " téléchargé" : "Fichier téléchargé") + " et rangé dans le dossier du marché : " + nom);
        this.atlLoad(true);
      } catch (e) { this.notify(e.message || "Export impossible pour le moment.", "err"); }
      finally { a.busy = ""; this.pending = Math.max(0, this.pending - 1); }
    },
    // Vague 6 (H) : la page « Comment ce dossier a été préparé », telle que l'export la joindrait (GET, sans IA).
    // Dossier à plusieurs lots (J) : la page du fichier d'UN lot (ses parties communes et les siennes).
    async atlPrepLoad() {
      const p = this.atl.prep; if (!this.atl.pid) return;
      const lots = this.atlLots() ? this.atlLotsListe() : [];
      if (lots.length && !lots.some(x => x.numero === p.lot)) p.lot = lots[0].numero;
      if (!lots.length) p.lot = "";
      // Deux lots choisis vite l'un après l'autre : seule la réponse du DERNIER choix est montrée (comme le carnet).
      const seq = (p.seq = (p.seq || 0) + 1), voulu = p.lot;
      p.loading = true; p.err = "";
      try {
        const d = await this.api("GET", this._atlUrl("/preparation" + (voulu ? "?lot=" + encodeURIComponent(voulu) : "")));
        if (seq === p.seq && p.lot === voulu) p.d = d;
      }
      catch (e) { if (seq === p.seq) p.err = e.message || "La page n'a pas pu être préparée pour le moment."; }
      finally { if (seq === p.seq) p.loading = false; }
    },
    atlPrepVoir() {
      const p = this.atl.prep; p.open = !p.open;
      if (p.open) this.atlPrepLoad();
    },
    atlPrepLot(numero) { const p = this.atl.prep; if (p.lot === numero) return; p.lot = numero; p.d = null; this.atlPrepLoad(); },
    // « Rédigée par X · aide de l'IA : oui · validée par X, le 19 octobre 2026 » (une ligne de la page, à l'écran).
    atlPrepLigne(l) {
      const min = s => String(s || "").charAt(0).toLowerCase() + String(s || "").slice(1);
      const auteur = /^Le groupement/.test(l.redigee_par || "") ? min(l.redigee_par) : (l.redigee_par || "");
      const ia = l.ia_libelle && l.ia_libelle !== "—" ? " · aide de l'IA : " + min(l.ia_libelle) : "";
      return "Rédigée par " + auteur + ia + " · " + (l.validee ? "validée " + min(l.validee_libelle) : "non validée");
    },
    _atlDerogOpen(d, fmt, lot) {
      const st = this.atl.st, raisons = (d && d.raisons) || [];
      const l = lot ? this.atlLotsListe().find(x => x.numero === lot) : null;
      this.atl.derog = { raisons, hash: (d && d.etat_hash) || (l ? l.blocage.etat_hash : (st && st.blocage.etat_hash)) || "",
        possibles: (d && d.derogations_possibles && d.derogations_possibles.length ? d.derogations_possibles : (l ? l.derogations_possibles : (st && st.derogations_possibles))) || [],
        fmt: fmt || "", raison: "", texte: "", err: "", busy: false, lot: lot || "", libelle: l ? l.libelle : "",
        avert: (raisons.find(x => x.avertissement) || {}).avertissement || "" };
    },
    atlDerogDepuisEtat() {
      const st = this.atl.st, b = st && st.blocage; if (!b || !b.bloque) return;
      this._atlDerogOpen({ raisons: b.raisons, etat_hash: b.etat_hash, derogations_possibles: st.derogations_possibles }, "");
    },
    async atlDerogOk() {
      const a = this.atl, g = a.derog; if (!g || g.busy) return;
      const t = (g.texte || "").trim();
      if (!g.raison) { g.err = "Choisissez une raison."; return; }
      if (t.length < 3 || t.length > 300) { g.err = "Expliquez en quelques mots (3 à 300 caractères)."; return; }
      g.busy = true; g.err = "";
      try {
        // Vague 6 : la dérogation du fichier d'UN lot porte son numéro.
        const r = g.lot ? await this.api("POST", this._atlUrl("/derogation"), { raison: g.raison, texte: t, etat_hash: g.hash, lot: g.lot })
          : await this.api("POST", this._atlUrl("/derogation"), { raison: g.raison, texte: t, etat_hash: g.hash });
        a.lastDerog = g.hash; if (a.st && r.blocage && !g.lot) a.st.blocage = r.blocage;
        const fmt = g.fmt, lot = g.lot; a.derog = null;
        this.notify("Dérogation inscrite au journal" + (lot ? " pour la " + partieLot(lot, true) : ""));
        if (fmt && lot) this.atlExportLot(this.atlLotsListe().find(x => x.numero === lot), fmt);
        else if (fmt) this.atlExport(fmt); else this.atlLoad(true);
      } catch (e) {
        if (e.code === "rien_a_deroger") { const fmt = g.fmt, lot = g.lot; a.derog = null; if (fmt && lot) this.atlExportLot(this.atlLotsListe().find(x => x.numero === lot), fmt); else if (fmt) this.atlExport(fmt); else this.atlLoad(true); return; }
        if (e.code === "etat_modifie") { a.derog = null; await this.atlLoad(true); this.notify(e.message, "err"); return; }
        g.err = e.message;
      } finally { if (a.derog) a.derog.busy = false; }
    },

    // ── Plusieurs lots, un seul effort (rédaction, vague 6 — J ; docs/REDACTION_V6.md) ──
    // Deux lots ou plus : des parties communes (une seule partie, un seul texte : modifiée, elle change dans le
    // fichier de chaque lot) et des parties propres à chaque lot ; un fichier par lot à l'export, avec ses limites,
    // son nom et sa dérogation. Tout est sans IA. Un dossier à un seul lot : rien ne change à l'écran.
    atlLots() { const st = this.atl.st; return !!(st && st.lots && st.lots.actif); },
    atlLotsListe() { const st = this.atl.st; return (st && st.lots && st.lots.liste) || []; },
    atlLotsMarche() { const a = this.atl; return (a.prop && a.prop.proposition && a.prop.proposition.lots_du_marche) || (a.st && a.st.lots && a.st.lots.du_marche) || null; },
    atlLotPlus() { const a = this.atl; return (a.lotsChoix.length + a.lotsAjoutes.length) >= 2; },
    atlLotCoche(n) { return this.atl.lotsChoix.includes(n); },
    atlLotBascule(n) {
      const a = this.atl; if (a.busy) return;
      a.lotsChoix = a.lotsChoix.includes(n) ? a.lotsChoix.filter(x => x !== n) : a.lotsChoix.concat([n]).sort((x, y) => Number(x) - Number(y));
      if (!a.st) this.atlLoad();
    },
    _atlLotAjoutValide(g, deja) {
      const n = String(g.numero || "").trim().replace(/^0+/, ""), t = String(g.intitule || "").trim();
      if (!/^\d{1,2}$/.test(n) || Number(n) < 1) return { err: "Le numéro d'une partie (lot) est un nombre de 1 à 99." };
      if (t.length < 2) return { err: "Donnez l'intitulé de la partie (lot " + n + "), tel qu'il est écrit dans le règlement." };
      if (deja.includes(n)) return { err: "La partie (lot " + n + ") est déjà dans la liste." };
      return { numero: n, intitule: t };
    },
    atlLotAjouter() {
      const a = this.atl, m = this.atlLotsMarche();
      const deja = ((m && m.lots) || []).map(x => x.numero).concat(a.lotsAjoutes.map(x => x.numero));
      const x = this._atlLotAjoutValide(a.lotAjout, deja);
      if (x.err) { this.notify(x.err, "err"); return; }
      a.lotsAjoutes = a.lotsAjoutes.concat([{ numero: x.numero, intitule: x.intitule }]);
      a.lotAjout = { numero: "", intitule: "" };
      if (!a.st) this.atlLoad();
    },
    atlLotRetirerAjout(n) { const a = this.atl; a.lotsAjoutes = a.lotsAjoutes.filter(x => x.numero !== n); if (!a.st) this.atlLoad(); },
    // Parties affichées dans le plan : toutes, les communes, ou celles du dossier d'un lot (communes comprises).
    atlSectionsVues() {
      const a = this.atl, ss = (a.st && a.st.sections) || [];
      if (!this.atlLots() || !a.lotFiltre) return ss;
      if (a.lotFiltre === "c") return ss.filter(s => s.commune);
      return ss.filter(s => s.commune || s.lot === a.lotFiltre);
    },
    // Numéro d'une partie dans le dossier du lot affiché (sinon celui de son lot).
    atlNumPart(s) {
      const a = this.atl;
      if (this.atlLots() && a.lotFiltre && a.lotFiltre !== "c") {
        const l = this.atlLotsListe().find(x => x.numero === a.lotFiltre);
        if (l && l.numeros && l.numeros[String(s.id)] !== undefined) return l.numeros[String(s.id)];
      }
      return s.numero_affiche;
    },
    atlLotTag(s) { return s.commune ? "Commune" : (s.lot ? partieLot(s.lot) : ""); },
    atlEtatLot(l) {
      const b = l && l.blocage; if (!b) return { cls: "neutral", label: "" };
      if (!b.peut_exporter) return { cls: "neutral", label: "Bloqué" };
      return this.atlEtatExport(l);
    },
    atlLotLims(l) { return ((l && l.limites) || []).filter(x => x.portee === "document"); },
    atlLotCompte(l) {
      const c = l && l.compteur && l.compteur.total; if (!c) return "";
      return "Environ " + this.atlNum(c.pages) + " page" + (c.pages > 1 ? "s" : "") + " · " + this.atlNum(c.mots) + " " + this.atlMotsLib(c.mots);
    },
    atlLotGrilleLignes(l) { return ((l && l.grille && l.grille.lignes) || []).filter(x => !x.prix); },
    atlExportLot(l, fmt) { if (l) this.atlExport(fmt, l); },
    atlDerogLot(l) {
      const b = l && l.blocage; if (!b || !b.bloque) return;
      this._atlDerogOpen({ raisons: b.raisons, etat_hash: b.etat_hash, derogations_possibles: l.derogations_possibles }, "", l.numero);
    },
    // Une partie commune devient propre à chaque lot, ou l'inverse (sans IA ; rien n'est supprimé).
    atlPortee(s, commune) {
      const a = this.atl; if (!s || a.busy) return;
      const lignes = commune
        ? ["« " + s.intitule + " » sera rédigée une fois et figurera telle quelle dans le fichier de chaque partie du marché. Elle garde ce texte ; la même partie des autres fichiers sort du plan (ses versions restent gardées)."]
        : ["« " + s.intitule + " » sera rédigée pour chaque partie du marché. Elle garde son texte pour la première ; une partie à écrire est ajoutée pour chacune des autres."];
      this._convAsk({ title: commune ? "Rendre cette partie commune à toutes vos parties du marché ?" : "Rédiger cette partie pour chaque partie du marché ?",
        ok: commune ? "Rendre commune" : "La rédiger pour chacune", lines: lignes, run: () => this._atlPortee(s, commune, false) });
    },
    async _atlPortee(s, commune, remplacer) {
      const a = this.atl; if (a.busy) return; a.busy = "portee";
      try {
        const d = await this.api("PUT", this._atlUrl("/sections/" + s.id + "/portee"), { commune, remplacer: !!remplacer });
        a.st = d; this.notify(commune ? "Partie commune à toutes vos parties du marché" : "Partie rédigée pour chaque partie du marché");
        if (!a.st.sections.some(x => x.id === a.sel)) this.atlSelect((a.st.sections[0] || {}).id || null);
      } catch (e) {
        if (e.code === "portee_a_confirmer") { a.busy = ""; this._convAsk({ title: "Retirer les textes des autres parties du marché ?", ok: "Confirmer", lines: [e.message], run: () => this._atlPortee(s, commune, true) }); return; }
        this.notify(e.message, "err");
      } finally { if (a.busy === "portee") a.busy = ""; }
    },
    // « Changer les lots » d'un dossier existant : le plan est reconstruit (les parties actuelles sont retirées,
    // jamais supprimées), avec la même confirmation que « Reconstruire le plan ».
    async atlLotsOuvrir() {
      const a = this.atl; if (a.busy) return;
      a.lotsDlg = { loading: true, d: null, choix: this.atlLotsListe().map(x => x.numero), ajoutes: [], ajout: { numero: "", intitule: "" }, err: "", busy: false, confirm: "" };
      try {
        const d = await this.api("GET", this._atlUrl("/lots"));
        if (!a.lotsDlg) return;
        a.lotsDlg.d = d.du_marche;
        const connus = ((d.du_marche && d.du_marche.lots) || []).map(x => x.numero);
        // Un lot indiqué par vous lors de la création reste dans la liste, comme lot ajouté.
        a.lotsDlg.ajoutes = this.atlLotsListe().filter(x => !connus.includes(x.numero)).map(x => ({ numero: x.numero, intitule: x.intitule }));
        a.lotsDlg.choix = a.lotsDlg.choix.filter(n => connus.includes(n));
      } catch (e) { if (a.lotsDlg) a.lotsDlg.err = e.message; }
      finally { if (a.lotsDlg) a.lotsDlg.loading = false; }
    },
    atlLotsDlgBascule(n) { const g = this.atl.lotsDlg; if (!g) return; g.choix = g.choix.includes(n) ? g.choix.filter(x => x !== n) : g.choix.concat([n]).sort((x, y) => Number(x) - Number(y)); g.confirm = ""; },
    atlLotsDlgAjouter() {
      const g = this.atl.lotsDlg; if (!g) return;
      const deja = (((g.d && g.d.lots) || []).map(x => x.numero)).concat(g.ajoutes.map(x => x.numero));
      const x = this._atlLotAjoutValide(g.ajout, deja);
      if (x.err) { g.err = x.err; return; }
      g.ajoutes = g.ajoutes.concat([x]); g.ajout = { numero: "", intitule: "" }; g.err = ""; g.confirm = "";
    },
    async atlLotsAppliquer(remplacer) {
      const a = this.atl, g = a.lotsDlg; if (!g || g.busy) return;
      g.busy = true; g.err = "";
      try {
        const d = await this.api("PUT", this._atlUrl("/lots"), { lots: g.choix, lots_ajoutes: g.ajoutes, remplacer: !!remplacer });
        a.st = d; a.lotsDlg = null; a.lotFiltre = "";
        this.atlSelect(((d.sections || [])[0] || {}).id || null);
        this.notify(d.lots && d.lots.actif ? "Plan reconstruit pour " + d.lots.liste.length + " parties du marché" : "Plan reconstruit : un seul dossier");
      } catch (e) {
        if (e.code === "plan_remplacement_a_confirmer") { g.confirm = e.message; return; }
        g.err = e.message;
      } finally { if (a.lotsDlg) a.lotsDlg.busy = false; }
    },

    // ── « Qui écrit quoi » (rédaction, vague 4, chef de file) ──
    // Contrat : docs/REDACTION_V4_GROUPEMENT.md § 4. Seulement pour un marché en groupement
    // (atl.st.groupement.onglet) : sans groupement, l'atelier ne change pas. Le chef de file répartit les
    // parties (pré-remplissage SANS IA d'après les lots), demande les parts (email, mêmes garde-fous que les
    // relances de la co-traitance), reçoit le texte envoyé et ses COMPTEURS de sources (jamais une source ni
    // un extrait), modifie une part (« à revalider par X », avant et après côte à côte) ou l'écrit à la place
    // d'un partenaire absent. Il ne lance JAMAIS l'aide de l'IA d'un partenaire : aucun bouton ici, et le
    // serveur refuse. Aucun temps réel : « Actualiser » relit la répartition.
    atlGrp() { const st = this.atl.st; return !!(st && st.groupement && st.groupement.onglet); },
    atlRepVue() { return this.atlGrp() && this.atl.onglet === "repartition"; },
    atlOnglet(o) {
      const a = this.atl;
      a.onglet = o === "repartition" ? "repartition" : "redaction";
      if (a.onglet === "repartition") this.atlRepLoad();
    },
    _atlRepUrl(p) { return this._atlUrl("/repartition" + (p || "")); },
    async atlRepLoad() {
      const a = this.atl, r = a.rep, pid = a.pid; if (!pid) return;
      r.loading = true; r.err = "";
      try {
        const d = await this.api("GET", this._atlRepUrl());
        if (this.atl.pid !== pid) return;
        r.d = d; r.v++;
        if (r.open && !d.sections.some(l => l.section_id === r.open)) { r.open = null; r.det = null; r.edit = null; }
      } catch (e) { r.err = e.message || "« Qui écrit quoi » est indisponible pour le moment."; }
      finally { r.loading = false; }
    },
    async atlRepPreparer() {
      const r = this.atl.rep; if (r.busy) return; r.busy = "preparer";
      try {
        r.d = await this.api("POST", this._atlRepUrl(), {}); r.v++;
        this.notify("Répartition préparée : vérifiez qui rédige chaque partie");
        this.atlLoad(true);
      } catch (e) { this.notify(e.message, "err"); }
      finally { r.busy = ""; }
    },
    atlRepLigne(sid) { const d = this.atl.rep.d; return (d && d.sections.find(l => l.section_id === sid)) || null; },
    // Les partenaires proposés dans « Rédigée par » : les co-traitants (un sous-traitant n'est pas membre du
    // groupement) ; ceux qui ne peuvent pas rédiger restent visibles, désactivés, avec leur raison.
    atlRepMembres() { const d = this.atl.rep.d; return ((d && d.membres) || []).filter(m => (m.role || "cotraitant") === "cotraitant"); },
    atlRepIndispo() { const d = this.atl.rep.d; return ((d && d.membres) || []).filter(m => !m.peut_rediger); },
    atlRepChoix(l) { const r = l && l.redacteur; return r && r.type === "partenaire" && r.invite_id ? "p:" + r.invite_id : "chef_de_file"; },
    // La raison de la proposition (sans IA), tant que le chef de file ne l'a pas changée.
    atlRepPropMsg(l) { return l && l.choix === "propose" && l.proposition ? (l.proposition.message || "") : ""; },
    // Libellé d'un partenaire dans « Rédigée par » : son nom et son lot (court) ; « indisponible » sinon.
    atlRepOption(m) {
      const lot = String(m.lot || ""), court = lot.length > 48 ? lot.slice(0, 47) + "…" : lot;
      return m.nom + (court ? " · " + court : "") + (m.peut_rediger ? "" : " (indisponible)");
    },
    atlRepStatutCls(st) { return atlRepStatutCls(st); },
    atlRepCompteurs(tc) { return atlRepCompteurs(tc); },
    atlRepEnvoyerA() { return atlRepADemander(this.atl.rep.d); },
    atlRepDemandeLignes() { return atlRepDemandeTexte(this.atl.rep.demande); },
    atlRepValidations() { const d = this.atl.rep.d; return atlRepValidationsTexte(d && d.dossier && d.dossier.pret); },
    atlRepRedacteur(l, val) {
      if (!l || val === this.atlRepChoix(l)) return;
      const body = val === "chef_de_file" ? { redacteur: "chef_de_file", invite_id: null }
        : { redacteur: "partenaire", invite_id: Number(String(val).slice(2)) };
      this._atlRepPut(l, body, false);
    },
    atlRepLongueur(l, val) {
      const t = String(val == null ? "" : val).trim(), n = t ? Math.round(Number(t)) : null;
      if (n !== null && (!isFinite(n) || n < 30 || n > 20000)) { this.atl.rep.v++; this.notify("Indiquez une longueur entre 30 et 20 000 mots.", "err"); return; }
      if (n === (l.longueur_mots || null)) return;
      this._atlRepPut(l, { longueur_mots: n }, false);
    },
    atlRepDate(l, val) {
      const d = String(val || "").slice(0, 10) || null;
      if (d === (l.date_limite || null)) return;
      this._atlRepPut(l, { date_limite: d }, false);
    },
    async _atlRepPut(l, body, confirmer) {
      const a = this.atl, r = a.rep; if (r.busy) { r.v++; return; }
      r.busy = "ligne:" + l.section_id;
      try {
        await this.api("PUT", this._atlRepUrl("/" + l.section_id), Object.assign({}, body, { lock_version: l.lock_version, confirmer: !!confirmer }));
        if (body.redacteur) this.notify(body.redacteur === "partenaire" ? "Partie confiée au partenaire" : "Partie reprise par vous");
        await this.atlRepLoad();
        if (r.open === l.section_id) this._atlRepDetail(l.section_id);
        if (body.redacteur) this.atlLoad(true);
      } catch (e) {
        r.v++;                                         // le menu revient à ce qui est enregistré
        if (e.code === "changement_a_confirmer") {
          this._convAsk({ title: "Confier cette partie à quelqu'un d'autre ?", ok: "Confier la partie", run: () => this._atlRepPut(l, body, true),
            lines: [e.message, "Le nouveau rédacteur repart d'une page vide : il ne voit pas le texte mis de côté."] });
        } else {
          this.notify(e.message, "err");
          if (e.code === "repartition_modifiee" || e.code === "partie_retiree") this.atlRepLoad();
        }
      } finally { r.busy = ""; }
    },
    // « Demander les parts » : un email par partenaire qui a une partie à rédiger, en cours ou à revalider.
    atlRepDemander() {
      const r = this.atl.rep, qui = this.atlRepEnvoyerA(); if (r.busy || !qui.length) return;
      this._convAsk({ title: "Demander les parts ?", ok: "Envoyer la demande", run: () => this._atlRepDemander(),
        lines: qui.map(x => x.nom + " : " + x.parties + " partie" + (x.parties > 1 ? "s" : "") + " à rédiger ou à revalider.")
          .concat(["Chacun reçoit par email la liste de ses parties, leur date limite interne et son lien."]) });
    },
    async _atlRepDemander() {
      const r = this.atl.rep; if (r.busy) return; r.busy = "demander"; r.demande = null;
      try { r.demande = await this.api("POST", this._atlRepUrl("/demander"), {}); await this.atlRepLoad(); }
      catch (e) { this.notify(e.message, "err"); }
      finally { r.busy = ""; }
    },
    // Réception : le texte envoyé (ou écrit par vous sur sa partie), l'avant et l'après d'une modification.
    atlRepOuvrir(l) {
      const r = this.atl.rep;
      if (r.open === l.section_id) {
        if (r.edit && r.edit.dirty) { this._convAsk({ title: "Abandonner votre texte ?", ok: "Abandonner", run: () => { r.edit = null; r.open = null; r.det = null; }, lines: ["Votre saisie sur cette partie n'est pas enregistrée."] }); return; }
        r.open = null; r.det = null; r.edit = null; return;
      }
      if (r.edit && r.edit.dirty) { this.notify("Enregistrez ou annulez d'abord votre texte en cours.", "err"); return; }
      r.open = l.section_id; r.det = null; r.edit = null;
      this._atlRepDetail(l.section_id);
    },
    async _atlRepDetail(sid) {
      const r = this.atl.rep; r.detLoading = true;
      try { const d = await this.api("GET", this._atlRepUrl("/" + sid)); if (r.open === sid) r.det = d; }
      catch (e) { this.notify(e.message, "err"); if (r.open === sid) r.open = null; }
      finally { r.detLoading = false; }
    },
    // Blocs de texte montrés : avant / après côte à côte quand vous avez modifié sa part, sinon le texte commun.
    atlRepBlocs() {
      const r = this.atl.rep, d = r.det; if (!d) return [];
      const nom = (d.redacteur && d.redacteur.nom) || "le partenaire", c = d.comparaison;
      if (c && c.avant && c.apres) return [{ k: "av", titre: "Avant : le texte envoyé par " + nom, v: c.avant }, { k: "ap", titre: "Après : votre modification", v: c.apres }];
      return d.texte_commun ? [{ k: "tc", titre: "", v: d.texte_commun }] : [];
    },
    atlRepHtml(v) { return v ? atlMdToHtml(v.texte, [], { refsPartenaire: true }) : ""; },
    atlRenvoisPart(s) { const v = s && s.version_courante; return !!(v && !s.prive_visible && atlRepARenvois(v.texte)); },
    atlRepRenvois() { return this.atlRepBlocs().some(b => atlRepARenvois(b.v && b.v.texte)); },
    atlRepMotsEdit() { const e = this.atl.rep.edit; return e ? atlMots(e.texte) : 0; },
    atlRepEcrire() {
      const r = this.atl.rep, d = r.det; if (!d || this.atlMobile) return;
      const tc = d.texte_commun;
      r.edit = { sid: d.section_id, texte: tc ? (tc.texte || "") : "", base: tc ? tc.version_id : null, dirty: false, conflict: "" };
      this.$nextTick(() => { const ta = this.$refs.atlRepTa; const el = Array.isArray(ta) ? ta[0] : ta; if (el && el.focus) el.focus(); });
    },
    atlRepAnnuler() {
      const r = this.atl.rep; if (!r.edit) return;
      if (!r.edit.dirty) { r.edit = null; return; }
      this._convAsk({ title: "Abandonner votre texte ?", ok: "Abandonner", run: () => { r.edit = null; }, lines: ["Votre saisie sur cette partie n'est pas enregistrée."] });
    },
    async atlRepEnregistrer() {
      const r = this.atl.rep, e = r.edit; if (!e || r.busy) return;
      if (!e.texte.trim()) { this.notify("Écrivez un texte.", "err"); return; }
      if (e.texte.length > 60000) { this.notify("Le texte dépasse 60 000 caractères : raccourcissez-le avant d'enregistrer.", "err"); return; }
      r.busy = "texte"; e.conflict = "";
      try {
        const d = await this.api("PUT", this._atlRepUrl("/" + e.sid + "/texte"), { texte: e.texte, base_version_id: e.base });
        if (r.open === e.sid) r.det = d;
        r.edit = null;
        this.notify(d.mention || "Texte enregistré : la partie est à valider par le partenaire");
        await this.atlRepLoad(); this.atlLoad(true);
      } catch (err) {
        if (err.code === "texte_modifie_entre_temps") { e.conflict = err.message; this._atlRepDetail(e.sid); }
        else this.notify(err.message, "err");
      } finally { r.busy = ""; }
    },
    async atlRepCopier() {
      const e = this.atl.rep.edit; if (!e) return;
      try { await navigator.clipboard.writeText(e.texte || ""); this.notify("Votre texte est copié"); }
      catch (x) { this.notify("Copie impossible : sélectionnez le texte et copiez-le à la main", "err"); }
    },
    // Repartir avec le texte actuel du partenaire (après un conflit) : votre saisie est remplacée.
    atlRepRepartir() {
      const r = this.atl.rep, d = r.det, e = r.edit; if (!d || !e) return;
      const tc = d.texte_commun;
      r.edit = { sid: d.section_id, texte: tc ? (tc.texte || "") : "", base: tc ? tc.version_id : null, dirty: false, conflict: "" };
    },
    // Passer d'un onglet à l'autre sur une partie précise.
    async atlRepVoir(sid) {
      this.atl.onglet = "repartition";
      await this.atlRepLoad();
      const x = this.atlRepLigne(sid); if (x && this.atl.rep.open !== sid) this.atlRepOuvrir(x);
      this.$nextTick(() => { const el = document.getElementById("atl-rep-" + sid); if (el && el.scrollIntoView) el.scrollIntoView({ block: "start", behavior: "smooth" }); });
    },
    atlRepVersAtelier(l) { this.atl.onglet = "redaction"; this.atlGoSection(l.section_id); },
    // « Prêt à déposer » (assemblage) : ce qui reste, qui a validé « Qui fait quoi », la validation du dossier
    // assemblé par le chef de file et « Harmoniser le ton » (des transitions entre les parts, rien d'autre).
    atlRepManques() { const d = this.atl.rep.d; return (d && d.dossier && d.dossier.pret && d.dossier.pret.manques) || []; },
    atlRepQfqTexte(l) { return l && l.genere === "grp_qfq" ? atlRepQfqValidationsTexte(l.validations) : ""; },
    // Une partie tirée du groupement attend-elle SA validation ? (« Qui fait quoi » : celle du chef de file, même si
    // un partenaire n'a pas encore validé.)
    atlRepAValider(l) {
      if (!l || l.statut === "validee") return false;
      if (l.genere !== "grp_qfq") return true;
      const moi = (l.validations || []).find(v => !v.invite_id); return !moi || moi.statut !== "valide";
    },
    // « Qui fait quoi » ouverte : les qualifications citées, avec leur mention (justifiée / déclarée) à l'écran.
    atlRepQuals() { const d = this.atl.rep.det; return d && d.genere === "grp_qfq" ? (d.membres || []).filter(m => (m.qualifications || []).length) : []; },
    atlRepMaValidation() {
      const d = this.atl.rep.d, ms = (d && d.dossier && d.dossier.pret && d.dossier.pret.membres) || [];
      const moi = ms.find(m => m.membre === "chef_de_file"); return moi ? moi.statut : "a_faire";
    },
    // Le chef de file valide le dossier assemblé une fois SES gestes faits (ses parties, « Organisation du
    // groupement », « Qui fait quoi ») : ce qui reste à faire par lui, partie par partie, d'après « Prêt à déposer ».
    atlRepChefPeutValider() { return !this.atlRepManques().some(m => m.section_id && (m.qui || []).indexOf("le chef de file") >= 0); },
    atlRepValiderDossier() {
      const r = this.atl.rep, d = r.d; if (r.busy || !d) return;
      this._convAsk({ title: "Valider le dossier assemblé ?", ok: "Valider le dossier",
        run: () => this._atlRepValiderDossier(d.dossier.empreinte),
        lines: ["Vous validez le dossier assemblé tel qu'il est aujourd'hui, toutes les parties comprises.",
                "Toute modification ensuite le fera repasser « à revalider » par chaque membre."] });
    },
    async _atlRepValiderDossier(empreinte) {
      const r = this.atl.rep; if (r.busy) return; r.busy = "dossier";
      try {
        await this.api("POST", this._atlRepUrl("/valider-dossier"), { empreinte: empreinte || null });
        this.notify("Dossier assemblé validé");
        await this.atlRepLoad();
      } catch (e) {
        const det = (e.detail && e.detail.sections) || [];
        this.notify(e.message + (det.length ? " " + det.map(x => "« " + x.titre + " »").join(", ") + "." : ""), "err");
        if (e.code === "dossier_modifie") this.atlRepLoad();
      } finally { r.busy = ""; }
    },
    atlRepHarm() { const d = this.atl.rep.d, h = d && d.harmoniser; return h && h.jonctions > 0 ? h : null; },
    atlRepHarmEnCours() { const pid = this.atl.pid; return Object.values(this.atlJobs || {}).some(j => j.pid === pid && j.action === "harmoniser"); },
    atlRepHarmoniser() {
      const h = this.atlRepHarm(); if (!h || this.atlRepHarmEnCours()) return;
      this._convAsk({ title: "Harmoniser le ton ?", ok: "Harmoniser",
        run: () => this._atlLancer("/repartition/harmoniser", { accepte_debit: false }, "harmoniser"),
        lines: [h.message, "Compte comme une nouvelle rédaction du dossier ; rien n'est décompté si aucune phrase n'est retenue."] });
    },
    atlRepEnvoyeeLe(l) { return l && l.envoyee_le ? this.atlWhen(l.envoyee_le) : ""; },
    // Ce qui se passe pour la partie d'un partenaire, en une phrase.
    atlRepEtat(l) {
      const nom = (l.redacteur && l.redacteur.nom) || "Le partenaire";
      if (l.statut === "a_rediger") return l.demandee_le ? "Demandée le " + this.atlWhen(l.demandee_le) + " : rien d'envoyé pour l'instant." : "Rien d'envoyé pour l'instant.";
      if (l.statut === "en_cours") return nom + " rédige sa partie : rien d'envoyé pour l'instant.";
      if (l.statut === "envoyee") return "Envoyée le " + this.atlRepEnvoyeeLe(l) + " : lisez-la ; " + nom + " doit encore la valider.";
      if (l.statut === "a_revalider") return l.mention ? "" : nom + " doit revalider sa partie.";
      if (l.statut === "validee") return l.mention ? "" : "Validée par " + nom + ".";
      return "";
    },

    // « Mon savoir-faire » : le dossier de présentation se prépare sur la page du marché.
    kbMarches() { return (this.projects || []).filter(p => !["perdu", "abandonne", "gagne"].includes(p.status)).slice(0, 3); },
    async kbOuvrirAtelier(p) { await this.openAo(p); this.atlOpen(); },
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
// « 20 pages au maximum », « 1 page au maximum par référence » : accord et partie visée.
const _GN_OBJET = { cv: "par CV", reference: "par référence", question: "pour une question", question_chaque: "par question",
  fiche: "par fiche", synthese: "pour la synthèse", lettre: "pour la lettre", annexe: "par annexe", selon_lot: "selon la partie du marché" };
function _gnLim(x) {
  if (x.type === "police") { const s = [x.police, x.taille != null ? x.taille : ""].filter(v => v !== "" && v != null).join(" "); return "Police : " + (s || x.texte || ""); }
  const un = Number(x.valeur) === 1;
  const u = ({ pages: un ? "page" : "pages", mots: un ? "mot" : "mots", caracteres: un ? "caractère" : "caractères", lignes: un ? "ligne" : "lignes" })[x.type] || x.type;
  const o = x.objet ? " " + (_GN_OBJET[x.objet] || "") : "";
  return ((x.valeur != null ? _gnNum(x.valeur) + " " + u : (x.texte || "")) + " au maximum" + o).trim();
}
// Rédaction, vague 4 : « Mes parties du dossier de présentation », vues par le COMPTE du partenaire (« Partagé
// avec moi ») — le même écran que par le lien (app/static/redaction-partenaire.js), monté une fois : Vue ne
// redessine jamais son contenu (gabarit statique).
__adjApp.component("redaction-partenaire", {
  props: { pid: { type: [Number, String], required: true }, token: { type: String, default: "" } },
  template: '<div class="rp-host"></div>',
  mounted() {
    const RP = window.AdjugoRedactionPartenaire;
    if (!RP) return;
    this._h = RP.mount(this.$el, { base: "/api/shared/" + encodeURIComponent(this.pid) + "/redaction", mode: "compte",
      headers: () => (this.token ? { Authorization: "Bearer " + this.token } : {}) });
  },
  unmounted() { if (this._h) this._h.destroy(); },
});
// Rédaction, vague 5 (E2) : « Retrouver mes marchés publics » et « mes qualifications RGE » (app/static/sources-publiques.js),
// dans « Mes preuves » (mode « preuves ») et dans la part d'un partenaire par son compte (mode « part »). Gabarit
// statique : Vue ne redessine jamais son contenu.
__adjApp.component("sources-publiques", {
  // La session est celle de l'application (this.$root) : elle n'est jamais passée dans le gabarit.
  props: { mode: { type: String, default: "preuves" }, kinds: { type: Array, default: () => ["decp"] },
           invite: { type: String, default: "" },
           avant: { type: Function, default: null }, apres: { type: Function, default: null } },
  template: '<div class="sp-host"></div>',
  mounted() {
    const SP = window.AdjugoSourcesPubliques;
    if (!SP) return;
    const enc = encodeURIComponent;
    const urls = this.mode === "part"
      ? { decp: "/api/invite/" + enc(this.invite) + "/contribution/publiques/marches", rge: "/api/invite/" + enc(this.invite) + "/contribution/publiques/rge",
          preuves: "/api/invite/" + enc(this.invite) + "/contribution/preuves", ecrire: "/api/invite/" + enc(this.invite) + "/contribution/reprendre-preuves" }
      : { decp: "/api/preuves/publiques/marches", rge: "/api/preuves/publiques/rge", ecrire: "/api/preuves/publiques" };
    const session = () => (this.$root && this.$root.token) || "";
    this._h = SP.mount(this.$el, { mode: this.mode, kinds: this.kinds, urls,
      headers: () => (session() ? { Authorization: "Bearer " + session() } : {}),
      avantEcrire: this.avant ? () => this.avant() : null, apresEcrire: (d) => { if (this.apres) this.apres(d); } });
  },
  unmounted() { if (this._h) this._h.destroy(); },
});
// Rédaction, vague 6 (F) : le carnet de notes (app/static/carnet-notes.js) — page du marché gagné ou perdu (mode
// « marche »), Mes marchés › Bilan (mode « tableau », « Où vous perdez des points ») et l'accueil (mode « rappels », les
// seuls « Demandez vos notes » ; réorganisation, vague 2a). Gabarit statique : Vue ne redessine
// jamais son contenu ; un autre marché remonte le composant (clé), un changement d'étape le relit.
__adjApp.component("carnet-notes", {
  props: { mode: { type: String, default: "marche" }, pid: { type: [Number, String], default: 0 },
           statut: { type: String, default: "" }, tick: { type: Number, default: 0 } },
  template: '<div class="cn-host"></div>',
  mounted() {
    const CN = window.AdjugoCarnetNotes;
    if (!CN) return;
    const session = () => (this.$root && this.$root.token) || "";
    this._h = CN.mount(this.$el, { mode: this.mode, pid: this.pid,
      headers: () => (session() ? { Authorization: "Bearer " + session() } : {}),
      onPartenaire: () => { const r = this.$root; if (r && r.openReseau) r.openReseau("annuaire"); },
      onOuvrir: (id) => { const r = this.$root; if (r && r.openProjectById) r.openProjectById(id); },
      onChange: () => { const r = this.$root; if (r && r.loadStats) r.loadStats(); } });
  },
  // `tick` : l'étape vient d'être enregistrée (PUT terminé) — le carnet se relit après le serveur, jamais avant.
  watch: { statut() { if (this._h) this._h.reload(); }, tick() { if (this._h) this._h.reload(); } },
  unmounted() { if (this._h) this._h.destroy(); },
});
__adjApp.component("grille-carte", {
  props: { g: { type: Object, default: null }, edit: { type: Boolean, default: false }, busy: { type: String, default: "" },
           // Vague 5 : écran étroit (le mode « sans IA » se choisit depuis un ordinateur, dans l'atelier) et dossier déjà
           // en mode « sans IA » (le bouton n'est plus proposé).
           mobile: { type: Boolean, default: false }, sansIa: { type: Boolean, default: false } },
  emits: ["choix", "element", "ajout", "relire", "sansia"],
  data() { return { poids: {}, ajout: "" }; },
  computed: {
    vm() {
      const g = this.g || {}, c = g.contraintes || {}, cad = c.cadre || {};
      const lignes = (g.criteres || []).map(x => {
        const ch = (x.choix_utilisateur && x.choix_utilisateur.choix) || (x.confirme ? "confirme" : x.ecarte ? "ecarte" : "");
        return { id: x.id || "", critere: x.critere || "", phrase: x.phrase || "", source: x.source || "", statut: x.statut,
          plan: !!x.dans_le_plan, choix: ch, poids: x.dans_le_plan ? (x.poids_retenu != null ? x.poids_retenu : (x.poids || "")) : "",
          poidsVous: x.poids_source === "utilisateur" || x.poids_saisi === true,
          // Vague 5 : sous-critères tels qu'écrits, et le contrôle de leur total (sans IA).
          sous: (x.sous_criteres || []).map(s => ({ critere: s.critere || "", poids: s.poids || "", phrase: s.phrase || "", statut: s.statut || "" })),
          ctlSous: x.controle_sous || {} };
      });
      const lim = (c.limites || []).filter(x => x && x.type);
      const vis = c.visite && (c.visite.phrase || c.visite.obligatoire) ? c.visite : null;
      // Vague 5 : ce que le dossier DEMANDE. Grille du chef de file : {liste, compteurs} ; vue des partenaires :
      // une liste. Une grille d'avant la vague 5 n'a pas ces rubriques (« Relire le dossier, sans IA »).
      const v2 = Object.prototype.hasOwnProperty.call(g, "exigences");
      const exRaw = Array.isArray(g.exigences) ? g.exigences : ((g.exigences && g.exigences.liste) || []);
      const exigences = exRaw.map(x => ({ id: x.id || "", texte: x.texte || "", phrase: x.phrase || "", intro: x.intro || "", source: x.source || "",
        origine: x.origine || "", retiree: x.retiree === true || ((x.choix_utilisateur || {}).choix === "ecarte") }));
      const cmRaw = Array.isArray(g.candidatures_multiples) ? g.candidatures_multiples : ((g.candidatures_multiples && g.candidatures_multiples.messages) || []);
      const qs = (g.questions_acheteur && typeof g.questions_acheteur === "object") ? g.questions_acheteur : null;
      const questions = ((qs && qs.liste) || []).map(q => ({ id: q.id || "", question: q.question || "", motif: q.motif || "", origine: q.origine || "",
        phrases: (q.phrases || []).filter(p => p && p.phrase), retiree: ((q.choix_utilisateur || {}).choix === "ecarte") }));
      const ia = (g.ia && g.ia.mentionne) ? g.ia : null;
      // Pastilles : les limites du mémoire, du cadre ou de l'offre (et la police) ; celles d'une
      // partie (un CV, une fiche référence, une question) restent dans « Voir les phrases ».
      return { lignes, pond: g.ponderation || {}, ordre: g.ordre || {}, total: g.controle_total || {},
        chips: lim.filter(x => !x.objet), partielles: lim.filter(x => x.objet).length,
        impose: !!c.fichier_impose, msgImpose: c.message_fichier || "",
        phraseOblig: (cad.obligatoire && cad.obligatoire.phrase) || c.phrase_obligation || "",
        cadreSource: (cad.obligatoire && cad.obligatoire.source) || cad.source || "",
        cadreFourni: cad.fourni != null ? !!cad.fourni : !!c.cadre_fourni,
        cadreMentionne: cad.mentionne != null ? !!cad.mentionne : !!c.cadre_mentionne,
        cadrePhrase: cad.phrase || "", limites: lim, visite: vis,
        lecture: (g.lecture && Array.isArray(g.lecture.pieces)) ? g.lecture : null,
        v2, exigences, env: (g.environnement && g.environnement.dans_la_note) ? g.environnement : null,
        cm: cmRaw.filter(x => x && x.message), ia, qs, questions };
    },
    alerteTotal() { const s = this.vm.total.statut; return s === "ecart" || s === "incomplet"; },
    piecesResume() {
      const ps = (this.vm.lecture && this.vm.lecture.pieces) || [];
      const manque = ps.filter(p => p.statut === "non_lu" || p.statut === "lu_en_partie" || p.ia || (!p.statut && p.lu_en_entier === false)).length;
      return manque ? ps.length + ", dont " + manque + " non lue" + (manque > 1 ? "s" : "") + " ou lue" + (manque > 1 ? "s" : "") + " en partie" : String(ps.length);
    },
    rienImpose() { const v = this.vm; return !v.impose && !v.cadreFourni && !v.cadreMentionne && !v.limites.length && !v.visite && !v.cm.length && !v.ia; },
    cadreManquant() { const v = this.vm; return v.impose && !v.cadreFourni; },
    exResume() {
      const ex = this.vm.exigences, n = ex.filter(x => !x.retiree).length, r = ex.length - n;
      if (!ex.length) return "";
      return n + " exigence" + (n > 1 ? "s" : "") + " repérée" + (n > 1 ? "s" : "") + (r ? " (" + r + " retirée" + (r > 1 ? "s" : "") + (this.edit ? " par vous" : " par le chef de file") + ")" : "") + ".";
    },
    qActives() { return this.vm.questions.filter(q => !q.retiree).length; },
  },
  methods: {
    lim(x) { return _gnLim(x); },
    send(l, choix) { this.$emit("choix", l.id, choix, choix === "confirme" ? String(this.poids[l.id] || "").trim() : ""); },
    // La phrase collée reste dans le champ tant que le serveur ne l'a pas retrouvée dans le dossier.
    ajouter() { const t = String(this.ajout || "").trim(); if (t.length < 12) return; this.$emit("ajout", t, ok => { if (ok) this.ajout = ""; }); },
    async copier(q) {
      const t = q.question + (q.phrases.length ? "\n\n" + q.phrases.map(p => "« " + p.phrase + " »").join("\n") : "");
      const r = this.$root;
      try { await navigator.clipboard.writeText(t); if (r && r.notify) r.notify("Question copiée : collez-la sur la plateforme de l'acheteur"); }
      catch (e) { if (r && r.notify) r.notify("Copie impossible : sélectionnez la question et copiez-la à la main", "err"); }
    },
  },
  template: '<div class="gn">'
    + '<ul v-if="vm.lignes.length" class="gn-list">'
    + '<li v-for="l in vm.lignes" :key="l.id||l.critere" class="gn-row" :class="{off:l.choix===\'ecarte\'}">'
    + '<span class="gn-crit">{{ l.critere }}</span>'
    + '<span v-if="l.poids" class="gn-poids num">{{ l.poids }}</span>'
    + '<span v-if="l.choix===\'ecarte\'" class="pill neutral gn-pill">retiré</span>'
    + '<span v-else-if="l.choix===\'confirme\' && l.statut===\'a_verifier\'" class="pill neutral gn-pill">{{ edit ? "confirmé par vous" : "confirmé par le chef de file" }}</span>'
    + '<span v-else-if="l.statut===\'a_verifier\'" class="pill a_etudier gn-pill">à vérifier dans le règlement</span>'
    + '<ul v-if="l.sous.length" class="gn-sous" :aria-label="\'Sous-critères de \' + l.critere"><li v-for="(s,i) in l.sous" :key="\'sc\'+i"><span class="gn-sous-n">{{ s.critere }}</span><span v-if="s.poids" class="gn-poids num">{{ s.poids }}</span><span v-else-if="s.statut===\'a_verifier\'" class="muted small">poids à vérifier</span></li></ul>'
    + '<span v-if="l.ctlSous.statut===\'ecart\' || l.ctlSous.statut===\'non_verifiable\'" class="muted small gn-sous-ctl">{{ l.ctlSous.message }}</span>'
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
    + '<div v-for="(s,i) in l.sous" :key="\'sp\'+i" class="gn-src-sous"><div class="small"><b>Sous-critère : {{ s.critere }}</b><span v-if="s.poids" class="muted"> · {{ s.poids }}</span></div><blockquote class="gn-q">{{ s.phrase }}</blockquote></div>'
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
    // Vague 5 : l'environnement, en information neutre.
    + '<template v-if="vm.env"><div class="gn-env small"><i data-lucide="leaf" aria-hidden="true"></i><span>{{ vm.env.message }}</span></div>'
    + '<details class="gn-det"><summary>Voir où il apparaît</summary><div v-for="(x,i) in vm.env.lieux" :key="\'en\'+i" class="gn-src"><div v-if="x.libelle" class="gn-src-t">{{ x.libelle }}<span v-if="x.poids" class="muted"> · {{ x.poids }}</span></div><blockquote class="gn-q">{{ x.phrase }}</blockquote></div></details></template>'
    + '<div class="gn-sub">Ce que le dossier impose'
    + '<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Repéré dans le texte, sans IA : un cadre de réponse fourni ou imposé, des limites de pages, de mots, de caractères ou de police, une visite obligatoire, l\'interdiction de répondre à la fois seul et en groupement, une phrase sur l\'intelligence artificielle. Chaque repérage garde sa phrase : relisez-la avant de rédiger. Un repérage peut en manquer : le règlement fait foi.</span></button></div>'
    + '<div v-if="vm.impose" class="warn-box"><i data-lucide="triangle-alert" style="width:15px;height:15px;flex:none;margin-top:1px"></i><span>{{ vm.msgImpose }}</span></div>'
    + '<p v-if="cadreManquant" class="small gn-note">{{ edit ? "Ce fichier ne figure pas dans les pièces importées : récupérez-le sur la plateforme de l\'acheteur." : "Ce fichier ne figure pas dans les pièces importées : le chef de file doit le récupérer sur la plateforme de l\'acheteur." }}</p>'
    + '<p v-else-if="!vm.impose && vm.cadreFourni" class="small gn-note">Un cadre de réponse est fourni avec le dossier.</p>'
    + '<p v-else-if="!vm.impose && vm.cadreMentionne" class="small gn-note">Le règlement parle d\'un cadre de réponse, mais il ne figure pas dans les fichiers lus.</p>'
    + '<div v-for="x in vm.cm" :key="\'cm\'+x.code" class="warn-box"><i data-lucide="triangle-alert" style="width:15px;height:15px;flex:none;margin-top:1px"></i><span>{{ x.message }}</span></div>'
    + '<div v-if="vm.ia" class="warn-box gn-ia"><i data-lucide="pen-off" style="width:15px;height:15px;flex:none;margin-top:1px"></i><span class="gn-ia-t">{{ vm.ia.message }}<template v-if="vm.ia.phrases && vm.ia.phrases.length"> <q class="gn-ia-q">{{ vm.ia.phrases[0].phrase }}</q></template></span>'
    + '<template v-if="edit"><span v-if="sansIa" class="small gn-ia-etat">Ce dossier se rédige sans IA.</span><span v-else-if="mobile" class="small muted gn-ia-etat">Rédiger sans IA se choisit depuis un ordinateur, dans l\'atelier.</span><button v-else type="button" class="btn sm" @click="$emit(\'sansia\')">Rédiger sans IA</button></template></div>'
    + '<ul v-if="vm.chips.length || vm.visite" class="gn-chips">'
    + '<li v-for="(x,i) in vm.chips" :key="\'l\'+i">{{ lim(x) }}</li>'
    + '<li v-if="vm.visite">Visite obligatoire</li></ul>'
    + '<p v-if="vm.partielles" class="muted small gn-note">{{ vm.partielles > 1 ? "D\'autres limites portent" : "Une autre limite porte" }} sur une partie du dossier (un CV, une question…) : voir les phrases.</p>'
    + '<p v-if="rienImpose" class="muted small gn-note">Ni cadre de réponse, ni limite de pages ou de police, ni visite obligatoire repérés dans le règlement.</p>'
    + '<details v-if="!rienImpose" class="gn-det"><summary>Voir les phrases</summary>'
    + '<div v-if="vm.phraseOblig || vm.cadrePhrase" class="gn-src"><div class="gn-src-t">Cadre de réponse</div><blockquote class="gn-q">{{ vm.phraseOblig || vm.cadrePhrase }}</blockquote><div v-if="vm.cadreSource" class="muted small">Trouvée dans : {{ vm.cadreSource }}</div></div>'
    + '<div v-for="(x,i) in vm.limites" :key="\'lp\'+i" class="gn-src"><div class="gn-src-t">{{ lim(x) }}</div><blockquote v-if="x.phrase" class="gn-q">{{ x.phrase }}</blockquote><div v-if="x.source" class="muted small">Trouvée dans : {{ x.source }}</div></div>'
    + '<div v-if="vm.visite" class="gn-src"><div class="gn-src-t">Visite obligatoire</div><blockquote class="gn-q">{{ vm.visite.phrase }}</blockquote><div v-if="vm.visite.source" class="muted small">Trouvée dans : {{ vm.visite.source }}</div></div>'
    + '<div v-for="x in vm.cm" :key="\'cmp\'+x.code" class="gn-src"><div class="gn-src-t">Répondre seul ou en groupement</div><blockquote class="gn-q">{{ x.phrase }}</blockquote></div>'
    + '<div v-for="(x,i) in (vm.ia ? vm.ia.phrases : [])" :key="\'iap\'+i" class="gn-src"><div class="gn-src-t">Intelligence artificielle</div><blockquote class="gn-q">{{ x.phrase }}</blockquote><div v-if="x.source" class="muted small">Trouvée dans : {{ x.source }}</div></div>'
    + '</details>'
    // Vague 5 : ce que le dossier DEMANDE (exigences repérées sans IA, phrase mot pour mot).
    + '<template v-if="vm.v2">'
    + '<div class="gn-sub">Ce que le dossier demande'
    + '<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Les phrases du règlement et du cadre de réponse qui demandent quelque chose au candidat (« le candidat présentera… », « le candidat devra… », « Décrivez… »), repérées sans IA. L\'IA de l\'analyse peut en proposer d\'autres : elles ne sont gardées que si leur phrase est retrouvée mot pour mot. Les pièces administratives, les prix et le dépôt n\'y sont pas. L\'atelier du dossier de présentation dit lesquelles sont traitées. Le règlement fait foi.</span></button></div>'
    + '<p class="small gn-note">{{ exResume || "Aucune exigence repérée dans le règlement ni dans le cadre de réponse." }}</p>'
    + '<details v-if="vm.exigences.length || edit" class="gn-det"><summary>{{ vm.exigences.length ? "Voir les exigences" : "Ajouter une exigence" }}</summary>'
    + '<div v-for="x in vm.exigences" :key="\'ex\'+x.id" class="gn-src" :class="{\'gn-off\': x.retiree}">'
    + '<div class="gn-src-t">« {{ x.texte }} »<span v-if="x.origine===\'ia\'" class="pill neutral gn-pill gn-ml">proposée par l\'IA, phrase retrouvée</span><span v-else-if="x.origine===\'utilisateur\'" class="pill neutral gn-pill gn-ml">ajoutée{{ edit ? " par vous" : "" }}</span><span v-if="x.retiree" class="pill neutral gn-pill gn-ml">retirée</span></div>'
    + '<div v-if="x.intro" class="muted small">{{ x.intro }}</div>'
    + '<blockquote class="gn-q">{{ x.phrase }}</blockquote>'
    + '<div v-if="x.source" class="muted small">Trouvée dans : {{ x.source }}</div>'
    + '<div v-if="edit" class="gn-act"><button type="button" class="btn ghost sm" :disabled="busy===\'ex:\'+x.id" @click="$emit(\'element\',\'exigence\',x.id,x.retiree?\'annule\':\'ecarte\')">{{ x.retiree ? "La remettre dans la liste" : "Retirer : ce n\'est pas une exigence" }}</button></div>'
    + '</div>'
    + '<div v-if="edit" class="gn-add"><label class="small muted" for="gn-ajout">Une exigence manque ? Collez sa phrase, telle qu\'elle est écrite dans le dossier.</label>'
    + '<div class="gn-add-r"><textarea id="gn-ajout" class="inp gn-add-t" v-model="ajout" rows="2" maxlength="600" placeholder="Ex. Le candidat précisera les mesures prises pour…"></textarea>'
    + '<button type="button" class="btn sm" :disabled="busy===\'ajout\' || String(ajout||\'\').trim().length < 12" @click="ajouter()"><i data-lucide="plus"></i>Ajouter</button></div></div>'
    + '</details>'
    // Vague 5 : questions à poser à l'acheteur (chef de file seulement : c'est lui qui les pose).
    + '<template v-if="edit && vm.qs">'
    + '<div class="gn-sub">Questions à poser à l\'acheteur'
    + '<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Repérées sans IA quand le dossier se contredit ou reste flou (pondération, sous-critères, limites, visite, cadre de réponse, date limite, intelligence artificielle). L\'IA de l\'analyse peut en proposer : elles ne sont gardées que si leur phrase est retrouvée mot pour mot. Adjugo n\'envoie rien : vous posez les questions vous-même sur la plateforme de l\'acheteur, avant la date limite des questions.</span></button></div>'
    + '<p v-if="vm.qs.date_limite && vm.qs.date_limite.message" class="small gn-note"><i data-lucide="clock" style="width:13px;height:13px;vertical-align:-2px"></i> {{ vm.qs.date_limite.message }}</p>'
    + '<template v-if="vm.questions.length">'
    + '<p class="small gn-note">{{ qActives ? (qActives + (qActives > 1 ? " questions à poser. " : " question à poser. ") + vm.qs.message) : "Toutes les questions sont retirées." }}</p>'
    + '<details class="gn-det"><summary>Voir les questions</summary>'
    + '<div v-for="q in vm.questions" :key="\'q\'+q.id" class="gn-src" :class="{\'gn-off\': q.retiree}">'
    + '<div class="gn-src-t">{{ q.question }}<span v-if="q.origine===\'ia\'" class="pill neutral gn-pill gn-ml">proposée par l\'IA</span><span v-if="q.retiree" class="pill neutral gn-pill gn-ml">retirée</span></div>'
    + '<div v-if="q.motif" class="muted small">{{ q.motif }}</div>'
    + '<blockquote v-for="(p,i) in q.phrases" :key="\'qp\'+i" class="gn-q">{{ p.phrase }}</blockquote>'
    + '<div class="gn-act"><button v-if="!q.retiree" type="button" class="btn sm" @click="copier(q)"><i data-lucide="copy"></i>Copier la question</button>'
    + '<button type="button" class="btn ghost sm" :disabled="busy===\'q:\'+q.id" @click="$emit(\'element\',\'question\',q.id,q.retiree?\'annule\':\'ecarte\')">{{ q.retiree ? "La remettre" : "Retirer" }}</button></div>'
    + '</div>'
    + '<div v-if="vm.qs.date_limite && vm.qs.date_limite.phrase" class="gn-src"><div class="gn-src-t">Date limite des questions</div><blockquote class="gn-q">{{ vm.qs.date_limite.phrase }}</blockquote></div>'
    + '</details></template>'
    + '<p v-else class="muted small gn-note">{{ vm.qs.message_vide }}</p>'
    + '</template>'
    + '</template>'
    + '<div v-else-if="edit" class="gn-relire small"><span style="flex:1;min-width:0">Cette analyse est antérieure aux sous-critères, à la liste des exigences et aux questions à poser à l\'acheteur.</span><button type="button" class="btn sm" :disabled="busy===\'relire\'" @click="$emit(\'relire\')"><span v-if="busy===\'relire\'" class="spin"></span><i v-else data-lucide="refresh-cw"></i>Relire le dossier, sans IA</button></div>'
    + '<details v-if="vm.lecture && vm.lecture.pieces.length" class="gn-det"><summary>Pièces lues ({{ piecesResume }})</summary>'
    + '<ul class="gn-pieces"><li v-for="(p,i) in vm.lecture.pieces" :key="\'pc\'+i" :class="{\'gn-nonlue\':p.statut===\'non_lu\'}"><span>{{ p.libelle }}</span><span v-if="p.nom" class="muted"> · {{ p.nom }}</span>'
    + '<template v-if="p.statut===\'non_lu\'"><span class="gn-manque"> · non lue</span><span v-if="p.raison" class="muted"> : {{ p.raison }}</span></template>'
    + '<template v-else-if="p.statut===\'lu_en_partie\' || (!p.statut && p.lu_en_entier===false)"><span class="gn-manque"> · lue en partie</span><span v-if="p.raison" class="muted"> : {{ p.raison }}</span></template>'
    + '<span v-else-if="(p.statut===\'lu_en_entier\' || p.lu_en_entier===true) && !p.ia" class="muted"> · lue en entier<template v-if="p.pages"> ({{ p.pages }} {{ p.pages > 1 ? "pages" : "page" }})</template></span>'
    + '<template v-if="p.ia"><span class="gn-manque"> · {{ p.ia }}</span></template></li></ul>'
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
    // Décision 9 : « vérifié » seulement pour une identité contrôlée dans un registre, datée (identité validée,
    // registre officiel). Un constat sur une autre source (BODACC, DECP) se dit « constaté à la source ».
    nv(b) {
      const n = b && b.niveau;
      if (n === "ok") return (b.key === "identite" || b.key === "sirene") ? "vérifié" : "constaté à la source";
      return ({ info: "information", alerte: "point d'attention" })[n] || "non vérifié";
    },
    jj: _rnJjmmaaaa,
  },
  template: '<ul v-if="badges && badges.length" class="rn-badges">'
    + '<li v-for="(b,i) in badges" :key="(b.key||\'b\')+i" class="rn-badge" :class="\'n-\'+(b.niveau||\'non_verifie\')">'
    + '<i :data-lucide="ic(b.niveau)" aria-hidden="true"></i><span class="rn-badge-l">{{ b.label }}<span class="sr-only"> ({{ nv(b) }})</span></span>'
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
    + '<div class="rn-sub">Vérifications dans les registres publics<button type="button" class="tip"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">Registre officiel : le répertoire des entreprises, tenu par l\'Insee. BODACC : le journal officiel où sont publiées les procédures collectives. DECP : les données publiques des marchés attribués. Chaque résultat est daté ; rien n\'est noté.</span></button></div>'
    + '<rn-badges :badges="c.badges"></rn-badges>'
    + '<template v-if="c.references && c.references.length"><div class="rn-sub">Références choisies par l\'entreprise</div>'
    + '<ul class="rn-refs"><li v-for="(r,i) in c.references" :key="\'rf\'+i">{{ r.intitule }}<span v-if="r.client" class="muted"> — {{ r.client }}</span><span v-if="r.annee" class="muted"> ({{ r.annee }})</span></li></ul></template>'
    + '<div v-if="c.declare_le" class="muted small rn-decl">Informations déclarées par l\'entreprise, mises à jour le {{ jj(c.declare_le) }}.</div>'
    + '</div>',
});

// window.__adjugo = instance racine montée (hook débogage/tests E2E ; mount() retourne le
// proxy en build prod comme dev — état client de l'utilisateur courant uniquement).
window.__adjugo = __adjApp.mount("#app");
