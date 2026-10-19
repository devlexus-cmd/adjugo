/*
 * Rédaction, vague 5 (E2) — « Retrouver mes marchés publics » (DECP) et « mes qualifications RGE » (ADEME).
 * Étude « rédaction » § 6.7 ; contrat docs/REDACTION_V5.md, section E2.
 *
 * Un seul écran pour trois accès :
 *   • « Mes preuves » (app/static/app.html) : /api/preuves/publiques/… ; ce qui est coché devient une fiche ;
 *   • la part d'un partenaire par son compte (« Partagé avec moi ») : /api/invite/{jeton}/contribution/…, avec
 *     en plus SES preuves (« Reprendre depuis Mes preuves ») ;
 *   • la part d'un partenaire par le lien (app/static/invite.html) : les sources publiques lues avec le SIRET de
 *     sa part.
 *
 * Règles tenues ici (le serveur les impose aussi) :
 *   • rien n'est ajouté sans une case cochée ; une valeur inhabituelle est montrée telle quelle, avec son alerte,
 *     et n'est jamais cochée d'office ;
 *   • libellés justes : « marché attribué, source publique DECP » (l'attribution ne prouve ni l'exécution ni sa
 *     qualité), « source publique : liste RGE de l'ADEME », toujours datés ; jamais le mot interdit ;
 *   • une panne de la source est dite telle quelle (« ne répond pas »), jamais « aucun marché » ;
 *   • tout texte affiché passe par spEsc (échappé, jamais interprété comme du HTML).
 * Interface : français, zéro émoji, explications dans une bulle (i), compact, lisible à 375 px.
 */
(function (root) {
  "use strict";

  // ── Fonctions pures (testées sous Node : tests/test_redaction_v5_e2.py) ──────────────────────────────

  function spEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function spJj(iso) {
    const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? m[3] + "/" + m[2] + "/" + m[1] : "";
  }

  // Montant à la française, tel que la source le donne (« 142 380,50 € », « 1 € »).
  function spEuros(x) {
    const n = Number(x);
    if (x === null || x === undefined || x === "" || !isFinite(n)) return String(x == null ? "" : x);
    const ent = Math.trunc(Math.abs(n)), dec = Math.round((Math.abs(n) - ent) * 100);
    const grp = String(ent).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return (n < 0 ? "-" : "") + grp + (dec ? "," + String(dec).padStart(2, "0") : "") + " €";
  }

  // La ligne d'un marché sous son objet : acheteur, date, montant d'attribution, rôle (rien de complété).
  function spMeta(m) {
    const a = (m && m.affiche) || {}, out = [];
    if (a.acheteur) out.push(a.acheteur);
    else if (a.acheteur_siret) out.push("acheteur : SIRET " + a.acheteur_siret + " (nom non retrouvé)");
    else out.push("acheteur non renseigné");
    if (a.date) out.push("notifié le " + (spJj(a.date) || a.date));
    if (a.montant !== null && a.montant !== undefined && a.montant !== "") out.push(spEuros(a.montant) + " HT");
    if (a.role_libelle) out.push(a.role_libelle);
    if (a.nature_marche && /accord/i.test(a.nature_marche)) out.push(a.nature_marche);
    return out.join(" · ");
  }

  function spMetaRge(q) {
    const a = (q && q.affiche) || {}, out = [];
    if (a.organisme) out.push(a.organisme);
    if (a.code) out.push("code " + a.code);
    if (a.date_debut && a.date_fin) out.push("du " + spJj(a.date_debut) + " au " + spJj(a.date_fin));
    else if (a.date_fin) out.push("jusqu'au " + spJj(a.date_fin));
    else if (a.date_debut) out.push("depuis le " + spJj(a.date_debut) + ", sans date de fin");
    return out.join(" · ");
  }

  // Les références saisies ligne à ligne, rattachées à leur version complète (acheteur, montant, provenance
  // « marché attribué, source publique DECP »…) quand l'intitulé n'a pas changé : enregistrer la part ne
  // perd jamais ce qui a été repris.
  function spFusionRefs(texte, riches) {
    const pool = (Array.isArray(riches) ? riches : []).filter(r => r && typeof r === "object" && r.intitule);
    const pris = new Set();
    return String(texte || "").split("\n").map(s => s.trim()).filter(Boolean).map(s => {
      const i = pool.findIndex((r, k) => !pris.has(k) && String(r.intitule).trim() === s);
      if (i >= 0) { pris.add(i); return Object.assign({}, pool[i]); }
      return { intitule: s };
    });
  }

  // « Dont 2 marchés attribués, source publique DECP (lus le 19/10/2026). »
  function spLibRefs(refs) {
    const d = (Array.isArray(refs) ? refs : []).filter(r => r && r.provenance === "decp");
    if (!d.length) return "";
    const dates = d.map(r => String(r.consulte_le || "")).filter(Boolean).sort();
    const der = dates.length ? spJj(dates[dates.length - 1]) : "";
    return "Dont " + d.length + (d.length > 1 ? " marchés attribués" : " marché attribué") + ", source publique DECP"
      + (der ? " (lu" + (d.length > 1 ? "s" : "") + " le " + der + ")" : "") + ".";
  }

  function spResume(r, mode) {
    const a = (r && r.ajoutees) || {}, nr = (a.references || []).length, nq = (a.qualifications || []).length;
    const c = r && Array.isArray(r.creees) ? r.creees : null;
    const parts = [];
    if (c) {
      if (c.length) parts.push(c.length + (c.length > 1 ? " fiches ajoutées" : " fiche ajoutée") + " à « Mes preuves »");
    } else {
      if (nr) parts.push(nr + (nr > 1 ? " références" : " référence"));
      if (nq) parts.push(nq + (nq > 1 ? " qualifications" : " qualification"));
      if (parts.length) { const n = nr + nq; parts.splice(0, parts.length, parts.join(" et ") + (n > 1 ? " ajoutées à votre part" : " ajoutée à votre part")); }
    }
    const deja = (r && r.deja) || 0;
    if (deja) parts.push(deja + (deja > 1 ? " étaient déjà " : " était déjà ") + (mode === "preuves" ? "dans vos preuves" : "dans votre part"));
    if (!parts.length) parts.push("Rien n'a été ajouté");
    return parts.join(" ; ") + ".";
  }

  const BULLE_DECP = "Adjugo lit les données essentielles de la commande publique (DECP, data.economie.gouv.fr) avec le SIRET de votre profil : les marchés où votre entreprise figure comme titulaire, seule ou en groupement. Un marché attribué ne prouve ni que les travaux ont été faits ni leur qualité : la fiche le dit (« marché attribué, source publique DECP »). Les valeurs sont montrées telles que la source les donne : rien n'est ajouté sans vous.";
  const BULLE_RGE = "Adjugo lit la liste publique des entreprises RGE de l'ADEME (data.ademe.fr) avec le SIRET de votre profil. Une qualification dont la date de fin est dépassée n'est pas proposée. Une qualification Qualibat hors RGE n'est dans aucune liste publique ouverte : ajoutez-la avec son certificat.";
  const BULLE_PART = "Ce que vous cochez s'ajoute aux références et aux qualifications de votre part, que lit le chef de file. Les marchés publics et les qualifications RGE sont lus avec le SIRET de votre part ; vos preuves restent dans votre compte, seule la ligne cochée part dans votre part.";
  const NOTE_ALERTE = "Une valeur inhabituelle est montrée telle quelle : cochez seulement si elle est juste.";
  const NOTE_QUALIBAT = "Une qualification Qualibat hors RGE n'est dans aucune liste publique ouverte : ajoutez-la avec son certificat.";

  const tip = (html, left) => html ? '<button type="button" class="tip' + (left ? " tip-l" : "") + '"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">' + html + "</span></button>" : "";
  const ico = (name, px) => '<i data-lucide="' + spEsc(name) + '" style="width:' + (px || 14) + "px;height:" + (px || 14) + 'px;flex:none"></i>';

  function errMessage(data, status) {
    const d = data && data.detail;
    if (d && typeof d === "object" && !Array.isArray(d) && d.message) return String(d.message);
    if (typeof d === "string") return d;
    if (status === 429) return "Trop de demandes rapprochées : réessayez dans quelques minutes.";
    return status >= 500 ? "Erreur du serveur : réessayez dans un instant." : "Action impossible pour le moment.";
  }

  /**
   * mount(el, opts) — opts :
   *   mode        "preuves" (« Mes preuves ») | "part" (part d'un partenaire)
   *   kinds       sections montrées : ["decp"], ["rge"], ["decp", "rge"]
   *   urls        { decp, rge, preuves (part par le compte), ecrire }
   *   headers     () => en-têtes d'authentification (compte : Bearer)
   *   avantEcrire async () => { ok, version } (part : enregistre d'abord la saisie en cours)
   *   apresEcrire (réponse) => void
   *   libelle     texte du bouton d'ouverture
   */
  function mount(el, opts) {
    const o = Object.assign({ mode: "preuves", kinds: ["decp"], urls: {}, headers: () => ({}) }, opts || {});
    const st = { open: false, loading: false, d: {}, sel: {}, busy: false, msg: "", err: "", destroyed: false };

    async function call(method, url, body) {
      const h = Object.assign({}, o.headers ? o.headers() : {});
      if (body !== undefined) h["Content-Type"] = "application/json";
      let r;
      try { r = await fetch(url, { method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined, cache: "no-store" }); }
      catch (e) { return { ok: false, status: 0, data: null, message: "Connexion impossible : vérifiez votre réseau, puis réessayez." }; }
      let data = null; try { data = await r.json(); } catch (e) {}
      return { ok: r.ok, status: r.status, data, message: r.ok ? "" : errMessage(data, r.status) };
    }

    const sections = () => {
      const s = [];
      if (o.urls.preuves) s.push("preuves");
      (o.kinds || []).forEach(k => { if (o.urls[k]) s.push(k); });
      return s;
    };

    async function load() {
      st.loading = true; st.err = ""; render();
      const res = await Promise.all(sections().map(k => call("GET", o.urls[k]).then(r => [k, r])));
      if (st.destroyed) return;
      const d = {};
      res.forEach(([k, r]) => { d[k] = r.ok ? r.data : { statut: "erreur", message: r.message }; });
      st.d = d; st.loading = false;
      // Seules SES preuves sont cochées d'office (il les a déjà acceptées) ; une ligne des sources publiques
      // se coche à la main (décision 7 b).
      const sel = {};
      ((d.preuves && d.preuves.preuves) || []).forEach(p => { if (!p.deja) sel["p:" + p.id] = true; });
      st.sel = sel;
      render();
    }

    const cochables = () => {
      const out = [];
      ((st.d.decp && st.d.decp.marches) || []).forEach(m => { if (!m.deja && !m.manque) out.push({ cle: m.cle, alerte: (m.alertes || []).length > 0 }); });
      ((st.d.rge && st.d.rge.qualifications) || []).forEach(q => { if (!q.deja && !q.manque) out.push({ cle: q.cle, alerte: (q.alertes || []).length > 0 }); });
      ((st.d.preuves && st.d.preuves.preuves) || []).forEach(p => { if (!p.deja) out.push({ cle: "p:" + p.id, alerte: false }); });
      return out;
    };
    const nbCoches = () => cochables().filter(x => st.sel[x.cle]).length;

    function itemDecp(m) {
      const off = m.deja || !!m.manque;
      let h = '<li class="sp-i' + (off ? " pv-off" : "") + '"><label class="sp-l"><input type="checkbox" data-cle="' + spEsc(m.cle) + '"' + (off ? " disabled" : "") + (st.sel[m.cle] ? " checked" : "") + ">";
      h += '<span class="pv-grow"><b class="sp-o">' + spEsc((m.affiche && m.affiche.objet) || (m.valeur && m.valeur.objet) || "") + "</b>";
      h += '<span class="muted small pv-block">' + spEsc(spMeta(m)) + "</span>";
      (m.alertes || []).forEach(a => { h += '<span class="pv-raison small pv-block">' + spEsc(a) + "</span>"; });
      if (m.manque) h += '<span class="pv-raison small pv-block">' + spEsc(m.manque) + "</span>";
      else if (m.deja) h += '<span class="muted small pv-block">' + spEsc(m.deja_message || "Déjà ajouté.") + "</span>";
      return h + "</span></label></li>";
    }

    function itemRge(q) {
      const off = q.deja || !!q.manque;
      const a = q.affiche || {};
      let h = '<li class="sp-i' + (off ? " pv-off" : "") + '"><label class="sp-l"><input type="checkbox" data-cle="' + spEsc(q.cle) + '"' + (off ? " disabled" : "") + (st.sel[q.cle] ? " checked" : "") + ">";
      h += '<span class="pv-grow"><b class="sp-o">' + spEsc(a.nom || (q.valeur && q.valeur.nom) || "") + "</b>";
      const meta = spMetaRge(q);
      if (meta) h += '<span class="muted small pv-block">' + spEsc(meta) + "</span>";
      if ((a.domaines || []).length) h += '<span class="muted small pv-block">Domaines : ' + spEsc(a.domaines.join(" ; ")) + "</span>";
      (q.alertes || []).forEach(x => { h += '<span class="pv-raison small pv-block">' + spEsc(x) + "</span>"; });
      if (q.deja) h += '<span class="muted small pv-block">' + spEsc(q.deja_message || "Déjà ajoutée.") + "</span>";
      return h + "</span></label></li>";
    }

    function itemPreuve(p) {
      const k = "p:" + p.id;
      let h = '<li class="sp-i' + (p.deja ? " pv-off" : "") + '"><label class="sp-l"><input type="checkbox" data-cle="' + spEsc(k) + '"' + (p.deja ? " disabled" : "") + (st.sel[k] ? " checked" : "") + ">";
      h += '<span class="pv-grow"><b class="sp-o">' + spEsc(p.titre || "") + "</b>";
      h += '<span class="muted small pv-block">' + spEsc(p.nature_libelle || "") + " · " + spEsc(p.source_libelle || "") + (p.date_fin_validite ? " · valable jusqu'au " + spEsc(spJj(p.date_fin_validite)) : "") + "</span>";
      if (p.deja) h += '<span class="muted small pv-block">' + spEsc(p.deja_message || "Déjà dans votre part.") + "</span>";
      return h + "</span></label></li>";
    }

    function etat(d, kind) {
      if (!d) return "";
      let h = "";
      if (d.exemple_fictif) {
        // Le bandeau de l'exemple fictif (démo) une seule fois par panneau.
        if (!st.fictifDit) h += '<div class="sp-fictif small">' + ico("flask-conical", 14) + "<span>" + spEsc(d.message || "") + "</span></div>";
        st.fictifDit = true;
      }
      else if (d.statut === "panne" || d.statut === "erreur") return '<div class="conv-err sp-mt" role="alert">' + ico("circle-alert", 15) + "<div>" + spEsc(d.message || "Source indisponible pour le moment.") + ' <button type="button" class="linkbtn" data-act="recharger">Réessayer</button></div></div>';
      else if (d.statut === "siret_manquant" || d.statut === "siren_invalide") {
        // Le même SIRET sert aux deux sources : le message une seule fois par panneau.
        if (st.siretDit) return "";
        st.siretDit = true;
        return '<div class="pv-info">' + ico("hash", 15) + '<span class="pv-grow">' + spEsc(d.message || "SIRET manquant.") + "</span></div>";
      }
      else if (d.ancien && d.message) h += '<div class="sp-ancien small">' + ico("clock", 14) + "<span>" + spEsc(d.message) + "</span></div>";
      return h;
    }

    function sectionDecp(d) {
      let h = '<div class="sp-sec"><div class="pv-sub">Marchés publics (DECP)</div>' + etat(d, "decp");
      if (!d || !["ok", "exemple"].includes(d.statut)) return h + "</div>";
      const ms = d.marches || [];
      if (!ms.length) h += '<p class="muted small pv-m0">Aucun marché trouvé dans DECP avec ce SIRET (lecture du ' + spEsc(spJj(d.consulte_le)) + ").</p>";
      else {
        if (ms.some(m => (m.alertes || []).length)) h += '<p class="muted small sp-p">' + spEsc(NOTE_ALERTE) + "</p>";
        h += '<ul class="sp-list">' + ms.map(itemDecp).join("") + "</ul>";
        if (d.tronque) h += '<p class="muted small sp-p">Adjugo montre les ' + spEsc(d.lus) + " lignes les plus récentes sur " + spEsc(d.total) + ".</p>";
      }
      h += '<p class="muted small sp-p">' + (d.exemple_fictif ? "Exemple fictif" : "Lu dans DECP le " + spEsc(spJj(d.consulte_le)))
        + (o.mode === "part" ? " · chaque référence ajoutée garde « marché attribué, source publique DECP »." : " · chaque fiche dira « marché attribué, source publique DECP ».") + "</p>";
      return h + "</div>";
    }

    function sectionRge(d) {
      let h = '<div class="sp-sec"><div class="pv-sub">Qualifications RGE (ADEME)</div>' + etat(d, "rge");
      if (!d || !["ok", "exemple"].includes(d.statut)) return h + "</div>";
      const qs = d.qualifications || [], ex = d.expirees || [];
      if (!qs.length && !ex.length) h += '<p class="muted small pv-m0">Aucune qualification trouvée dans la liste RGE avec ce SIRET (lecture du ' + spEsc(spJj(d.consulte_le)) + ").</p>";
      if (qs.length) h += '<ul class="sp-list">' + qs.map(itemRge).join("") + "</ul>";
      if (ex.length) {
        h += '<div class="sp-exp"><b class="small">Non proposées : date de fin dépassée</b><ul class="sp-exp-l">';
        ex.forEach(x => { h += '<li class="small"><span class="strong">' + spEsc(x.nom || "") + "</span><span class=\"pv-raison pv-block\">" + spEsc(x.message || "") + "</span></li>"; });
        h += "</ul></div>";
      }
      h += '<p class="muted small sp-p">' + (d.exemple_fictif ? "Exemple fictif" : "Lu dans la liste RGE de l'ADEME le " + spEsc(spJj(d.consulte_le))) + ". " + spEsc(NOTE_QUALIBAT) + "</p>";
      return h + "</div>";
    }

    function sectionPreuves(d) {
      let h = '<div class="sp-sec"><div class="pv-sub">Depuis Mes preuves</div>';
      if (!d || d.statut === "erreur") return h + '<p class="muted small pv-m0">' + spEsc((d && d.message) || "Vos preuves sont indisponibles pour le moment.") + "</p></div>";
      const ps = d.preuves || [];
      if (!ps.length) return h + '<p class="muted small pv-m0">Aucune référence ni qualification utilisable dans « Mes preuves » pour l\'instant.</p></div>';
      return h + '<ul class="sp-list">' + ps.map(itemPreuve).join("") + "</ul></div>";
    }

    function libelleAjout() {
      const n = nbCoches();
      if (o.mode === "preuves") return n ? "Ajouter à « Mes preuves » (" + n + ")" : "Ajouter à « Mes preuves »";
      return n ? "Ajouter à ma part (" + n + ")" : "Ajouter à ma part";
    }

    function render() {
      if (st.destroyed) return;
      const titre = o.libelle || (o.mode === "part" ? "Reprendre mes références et qualifications" : (o.kinds[0] === "rge" ? "Retrouver mes qualifications RGE" : "Retrouver mes marchés publics"));
      const bulle = o.mode === "part" ? BULLE_PART : (o.kinds[0] === "rge" ? BULLE_RGE : BULLE_DECP);
      if (!st.open) {
        el.innerHTML = '<div class="sp-lanceur">' + '<button type="button" class="btn sm" data-act="ouvrir">' + ico(o.kinds[0] === "rge" && o.mode !== "part" ? "badge-check" : "landmark", 14) + spEsc(titre) + "</button>" + tip(spEsc(bulle)) + (st.msg ? '<span class="small sp-ok" role="status">' + spEsc(st.msg) + "</span>" : "") + "</div>";
        icons(); return;
      }
      let h = '<section class="sp-panel" aria-label="' + spEsc(titre) + '"><div class="sp-head"><h3 class="pv-h3 pv-grow">' + spEsc(titre) + tip(spEsc(bulle)) + "</h3>"
        + '<button type="button" class="btn ghost sm" data-act="fermer" aria-label="Fermer">' + ico("x", 14) + "</button></div>";
      if (st.loading) h += '<div class="muted small" role="status"><span class="spin"></span> Lecture en cours…</div>';
      else {
        st.fictifDit = false; st.siretDit = false;
        sections().forEach(k => { h += k === "decp" ? sectionDecp(st.d.decp) : (k === "rge" ? sectionRge(st.d.rge) : sectionPreuves(st.d.preuves)); });
        if (st.err) h += '<div class="conv-err sp-mt" role="alert">' + ico("circle-alert", 15) + "<div>" + spEsc(st.err) + "</div></div>";
        if (st.msg) h += '<div class="small sp-ok sp-mt" role="status">' + spEsc(st.msg) + "</div>";
        const ch = cochables();
        if (ch.length) {
          h += '<div class="row wrap sp-acts"><button type="button" class="btn primary sm" data-act="ajouter"' + (st.busy || !nbCoches() ? " disabled" : "") + ">"
            + (st.busy ? '<span class="spin"></span>' : ico("plus", 14)) + '<span data-lib>' + spEsc(libelleAjout()) + "</span></button>";
          if (ch.some(x => !x.alerte && !String(x.cle).startsWith("p:"))) h += '<button type="button" class="btn ghost sm" data-act="cocher">Cocher les lignes sans alerte</button>';
          h += '<button type="button" class="btn ghost sm" data-act="fermer">Fermer</button></div>';
        } else h += '<div class="row wrap sp-acts"><button type="button" class="btn ghost sm" data-act="fermer">Fermer</button></div>';
      }
      h += "</section>";
      el.innerHTML = h;
      icons();
    }

    function icons() { try { root.lucide && root.lucide.createIcons({ root: el }); } catch (e) {} }

    async function ajouter() {
      if (st.busy) return;
      const cles = cochables().filter(x => st.sel[x.cle]).map(x => x.cle);
      if (!cles.length) return;
      st.busy = true; st.err = ""; st.msg = ""; render();
      try {
        let body;
        if (o.mode === "part") {
          const v = o.avantEcrire ? await o.avantEcrire() : { ok: true, version: null };
          if (!v || !v.ok) { st.err = (v && v.message) || "Enregistrez d'abord votre part, puis réessayez."; return; }
          body = { publiques: cles.filter(c => !c.startsWith("p:")), version: v.version };
          const ps = cles.filter(c => c.startsWith("p:")).map(c => Number(c.slice(2))).filter(n => n > 0);
          if (o.urls.preuves) body.preuves = ps;
        } else body = { cles };
        const r = await call("POST", o.urls.ecrire, body);
        if (!r.ok) { st.err = r.message; return; }
        const ign = (r.data && r.data.ignorees) || [];
        st.msg = spResume(r.data, o.mode) + (ign.length ? " " + ign.map(i => (i.texte ? i.texte + " : " : "") + i.message).join(" ") : "");
        try { o.apresEcrire && o.apresEcrire(r.data); } catch (e) {}
        st.sel = {};
        await load();
      } finally { st.busy = false; render(); }
    }

    function onClick(e) {
      const b = e.target.closest && e.target.closest("[data-act]");
      if (!b || !el.contains(b)) return;
      const act = b.dataset.act;
      if (act === "ouvrir") { st.open = true; st.msg = ""; load(); }
      else if (act === "fermer") { st.open = false; st.err = ""; render(); }
      else if (act === "recharger") load();
      else if (act === "cocher") { cochables().forEach(x => { if (!x.alerte && !String(x.cle).startsWith("p:")) st.sel[x.cle] = true; }); render(); }
      else if (act === "ajouter") ajouter();
    }
    function onChange(e) {
      const c = e.target;
      if (!c || c.type !== "checkbox" || !c.dataset.cle) return;
      st.sel[c.dataset.cle] = c.checked;
      const btn = el.querySelector('[data-act="ajouter"]');
      if (btn) { btn.disabled = st.busy || !nbCoches(); const lib = btn.querySelector("[data-lib]"); if (lib) lib.textContent = libelleAjout(); }
    }
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    render();
    return {
      destroy() { st.destroyed = true; el.removeEventListener("click", onClick); el.removeEventListener("change", onChange); el.innerHTML = ""; },
      ouvrir() { st.open = true; load(); },
    };
  }

  root.AdjugoSourcesPubliques = { mount, _pur: { spEsc, spJj, spEuros, spMeta, spMetaRge, spFusionRefs, spLibRefs, spResume } };
})(typeof window !== "undefined" ? window : globalThis);
