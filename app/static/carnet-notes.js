/*
 * Rédaction, vague 6 (F) — le carnet de notes : « Demandez vos notes », la saisie des notes reçues et
 * « Où vous perdez des points ». Étude « rédaction » § 6.11 ; contrat docs/REDACTION_V6.md, section F.
 *
 * Deux écrans, montés par app/static/app.js (composant <carnet-notes>) :
 *   • mode « marche » (page du marché gagné ou perdu) : le courrier pré-rempli (copier, ou ouvrir dans sa
 *     messagerie : Adjugo n'envoie jamais rien), « J'ai envoyé ma demande », le rappel des 2 jours, le formulaire
 *     tiré de « Comment vous serez noté » (critères et sous-critères), la lecture du courrier collé sans IA ou avec
 *     l'IA en option, les notes validées, le constat et, pour un marché gagné, « Ajouter ce dossier à mon
 *     savoir-faire » ;
 *   • mode « tableau » (Mes marchés › Bilan) : « Où vous perdez des points » et les rappels « Demandez vos notes » ;
 *   • mode « rappels » (accueil, réorganisation vague 2a) : les seuls rappels « Demandez vos notes » (des actions), rien
 *     quand il n'y en a pas.
 *
 * Règles tenues ici (le serveur les impose aussi) :
 *   • une valeur lue dans le courrier (sans IA ou avec l'IA) n'est qu'une PROPOSITION : elle montre la ligne du
 *     courrier où elle est écrite et rien n'est enregistré avant « Valider les notes » ;
 *   • aucune moyenne avant 3 marchés ; les familles proposées par Adjugo se confirment en validant ;
 *   • tout texte affiché passe par cnEsc (échappé, jamais interprété comme du HTML).
 * Interface : français, zéro émoji, explications dans une bulle (i), compact, lisible à 375 px.
 */
(function (root) {
  "use strict";

  // ── Fonctions pures (testées sous Node : tests/test_redaction_v6_carnet.py) ─────────────────────────

  function cnEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // « 32,5 » → 32.5 ; vide → null ; illisible → NaN.
  function cnNombre(s) {
    if (s === null || s === undefined) return null;
    const t = String(s).replace(/[\s  ]/g, "");
    if (!t) return null;
    return /^\d{1,5}(?:[.,]\d{1,3})?$/.test(t) ? Number(t.replace(",", ".")) : NaN;
  }

  function cnPct(note, max) {
    const n = cnNombre(note), m = cnNombre(max);
    if (n === null || m === null || isNaN(n) || isNaN(m) || m <= 0) return null;
    return Math.round(100 * n / m);
  }

  // Lien « Ouvrir dans ma messagerie » : le courrier part de la messagerie de l'utilisateur, jamais d'Adjugo.
  function cnMailto(dest, objet, corps) {
    const d = /^[^@\s<>"']+@[^@\s<>"']+\.[A-Za-z]{2,24}$/.test(String(dest || "")) ? encodeURIComponent(dest) : "";
    return "mailto:" + d + "?subject=" + encodeURIComponent(String(objet || "")) + "&body=" + encodeURIComponent(String(corps || ""));
  }

  // Les propositions lues dans le courrier, posées sur les lignes du formulaire : seuls les champs proposés
  // changent, chacun avec sa ligne du courrier ; la ligne est marquée « à valider ».
  function cnFusion(lignes, props) {
    const p = props || {};
    return (lignes || []).map(l => {
      const x = p[l.cle];
      if (!x) return Object.assign({}, l);
      const out = Object.assign({}, l, { proposee: true, origine: x.origine || "courrier" });
      if (x.note) { out.note = x.note; out.extrait_note = x.extrait_note || ""; if (x.note_max) out.note_max = x.note_max; }
      if (x.note_gagnant) { out.note_gagnant = x.note_gagnant; out.extrait_gagnant = x.extrait_gagnant || ""; if (!out.note_max && x.note_gagnant_max) out.note_max = x.note_gagnant_max; }
      if (x.commentaire) { out.commentaire = x.commentaire; out.commentaire_du_courrier = true; }
      return out;
    });
  }

  // Le corps de PUT …/notes : ce que l'utilisateur valide, ligne par ligne (`lot` : le lot d'un critère ajouté,
  // marché à plusieurs lots ; le serveur garde le lot de chaque critère connu).
  function cnPayload(lignes) {
    return (lignes || []).map(l => ({
      cle: l.cle || "", critere: String(l.critere || "").trim(), parent: l.parent || "", poids: l.poids || "",
      note: String(l.note || "").trim() || null, note_max: String(l.note_max || "").trim() || null,
      note_gagnant: String(l.note_gagnant || "").trim() || null, commentaire: String(l.commentaire || "").trim(),
      famille: l.famille || "", origine: l.origine || "saisie", extrait_note: l.extrait_note || "",
      extrait_gagnant: l.extrait_gagnant || "", commentaire_du_courrier: !!l.commentaire_du_courrier,
      lot: String(l.lot || ""),
    }));
  }

  // Plusieurs lots (vague 6, J) : le titre à poser AVANT chaque ligne (« Lot 2 — Couverture » quand le lot change,
  // « Critères ajoutés » avant le premier critère ajouté), "" sinon. Un marché à un seul lot : aucun titre.
  function cnTetes(lignes, avecAjoutees) {
    let prec = null, ajout = false;
    return (lignes || []).map(l => {
      if (avecAjoutees && l.ajoutee) {
        if (ajout) return "";
        ajout = true;
        return (lignes || []).some(x => x.lot && !x.ajoutee) ? "Critères ajoutés" : "";
      }
      const lot = l.lot || "";
      if (!lot || lot === prec) { prec = lot; return ""; }
      prec = lot;
      return String(l.lot_libelle || ("Lot " + lot));
    });
  }

  // Contrôle avant l'envoi (le serveur refait le même) : un message, ou "".
  function cnControle(lignes, lots) {
    for (const l of lignes || []) {
      const n = cnNombre(l.note), m = cnNombre(l.note_max), g = cnNombre(l.note_gagnant);
      const nom = "« " + String(l.critere || "ce critère").slice(0, 60) + " »";
      if ([n, m, g].some(v => v !== null && isNaN(v))) return nom + " : une note n'est pas un nombre (exemple : 12,5).";
      if ((n !== null || g !== null) && !m) return nom + " : indiquez la note maximale.";
      if (n !== null && m && n > m) return nom + " : la note dépasse la note maximale.";
      if (g !== null && m && g > m) return nom + " : la note de l'offre retenue dépasse la note maximale.";
      if (!String(l.critere || "").trim() && (n !== null || g !== null || String(l.commentaire || "").trim())) return "Chaque ligne nomme son critère.";
      if (lots && lots.length && l.ajoutee && !l.lot && (n !== null || g !== null || String(l.commentaire || "").trim())) return nom + " : choisissez le lot de ce critère.";
    }
    return "";
  }

  // L'en-tête d'une ligne du formulaire : le champ « Critère » d'un critère ajouté, SINON le nom du critère (et son
  // poids) ; puis, sur un marché à plusieurs lots, le choix du lot d'un critère ajouté. Un marché simple : rien de plus.
  function cnLigneTete(l, k, lots) {
    let h = "";
    if (l.ajoutee && !l.cle_fixe) h += '<div class="field cn-field"><label for="' + k + 'c">Critère</label><input id="' + k + 'c" data-f="critere" value="' + cnEsc(l.critere) + '" maxlength="200"></div>';
    else h += '<div class="cn-l-h"><span class="cn-l-c">' + cnEsc(l.critere) + (l.poids ? ' <span class="muted">· ' + cnEsc(l.poids) + "</span>" : "") + "</span>" + (l.proposee ? '<span class="pill a_etudier cn-pill">à valider</span>' : "") + "</div>";
    // Plusieurs lots : un critère ajouté dit son lot (l'acheteur note chaque lot à part).
    if (l.ajoutee && (lots || []).length) h += '<div class="field cn-field"><label for="' + k + 'l">Lot</label><select id="' + k + 'l" data-f="lot"><option value="">Choisissez le lot</option>' + lots.map(x => '<option value="' + cnEsc(x.numero) + '"' + (x.numero === l.lot ? " selected" : "") + ">" + cnEsc(x.libelle) + "</option>").join("") + "</select></div>";
    return h;
  }

  // ── Petits gabarits ─────────────────────────────────────────────────────────────────────────────

  const tip = (txt, left) => txt ? '<button type="button" class="tip' + (left ? " tip-l" : "") + '"><i data-lucide="info"></i><span class="sr-only">En savoir plus</span><span class="tip-b" role="tooltip">' + cnEsc(txt) + "</span></button>" : "";
  const ico = (name, px) => '<i data-lucide="' + cnEsc(name) + '" style="width:' + (px || 14) + "px;height:" + (px || 14) + 'px;flex:none"></i>';
  const btn = (act, label, cls, extra) => '<button type="button" class="btn sm' + (cls ? " " + cls : "") + '" data-act="' + act + '"' + (extra || "") + ">" + label + "</button>";
  const barre = (p) => '<span class="cn-bar" aria-hidden="true"><span style="width:' + Math.max(0, Math.min(100, Number(p) || 0)) + '%"></span></span>';

  function errMessage(data, status) {
    const d = data && data.detail;
    if (d && typeof d === "object" && !Array.isArray(d) && d.message) return String(d.message);
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) return "Saisie invalide.";
    if (status === 429) return "Trop de demandes rapprochées : réessayez dans quelques minutes.";
    return status >= 500 ? "Erreur du serveur : réessayez dans un instant." : "Action impossible pour le moment.";
  }

  // ── Montage ─────────────────────────────────────────────────────────────────────────────────────

  /**
   * mount(el, opts) — opts :
   *   mode          "marche" | "tableau" | "rappels"
   *   pid           identifiant du marché (mode « marche »)
   *   headers       () => en-têtes d'authentification
   *   onPartenaire  () => ouvre le réseau de partenaires (« Chercher un partenaire qui couvre ce manque »)
   *   onOuvrir(pid) ouvre un marché (rappels du tableau de bord)
   *   onChange()    après une écriture
   */
  function mount(el, opts) {
    const o = Object.assign({ mode: "marche", headers: () => ({}) }, opts || {});
    const st = { d: null, err: "", busy: "", form: null, courrier: "", lecture: null, demande: false, lettre: null,
      proc: null, msg: null, destroyed: false };

    async function call(method, path, body) {
      const h = Object.assign({}, o.headers ? o.headers() : {});
      if (body !== undefined) h["Content-Type"] = "application/json";
      let r;
      try { r = await fetch("/api/carnet" + path, { method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined, cache: "no-store" }); }
      catch (e) { return { ok: false, status: 0, data: null, message: "Connexion impossible : vérifiez votre réseau, puis réessayez." }; }
      let data = null; try { data = await r.json(); } catch (e) {}
      return { ok: r.ok, status: r.status, data, message: r.ok ? "" : errMessage(data, r.status) };
    }
    const dire = (txt, err) => { st.msg = txt ? { txt, err: !!err } : null; };
    const changed = () => { try { o.onChange && o.onChange(); } catch (e) {} };

    async function load() {
      const seq = (st.seq = (st.seq || 0) + 1);     // deux relectures croisées : seule la dernière compte
      const r = await call("GET", o.mode === "tableau" || o.mode === "rappels" ? "/tableau" : "/" + encodeURIComponent(o.pid));
      if (st.destroyed || seq !== st.seq) return;
      if (!r.ok) { st.d = null; st.err = r.status === 404 ? "" : r.message; render(); return; }
      st.d = r.data; st.err = "";
      render();
    }

    // ── Rendu ────────────────────────────────────────────────────────────────────────────────────
    function render() {
      if (st.destroyed) return;
      const ouverts = new Set(Array.from(el.querySelectorAll("details[open]")).map(x => x.dataset.k || ""));
      el.innerHTML = o.mode === "tableau" ? renderTableau() : o.mode === "rappels" ? renderRappels() : renderMarche();
      el.querySelectorAll("details[data-k]").forEach(x => { if (ouverts.has(x.dataset.k)) x.open = true; });
      try { root.lucide && root.lucide.createIcons({ root: el }); } catch (e) {}
    }

    function msgHtml() {
      const m = st.msg;
      if (!m) return '<div class="sr-only" aria-live="polite" data-live></div>';
      return (m.err ? '<div class="conv-err cn-mt8" role="alert">' + ico("circle-alert", 15) + "<div>" + cnEsc(m.txt) + "</div></div>"
        : '<div class="cn-ok small cn-mt8" role="status">' + ico("check", 14) + "<span>" + cnEsc(m.txt) + "</span></div>");
    }

    function rappelHtml(r) {
      return '<button type="button" class="alert-callout is-link cn-mt8" data-act="ouvrir" data-pid="' + Number(r.project_id) + '">' + ico("bell", 16)
        + '<div><b>Demandez vos notes : ' + cnEsc(r.nom) + "</b>" + '<div class="small">Perdu le ' + cnEsc(r.perdu_le_jj) + ". " + cnEsc(r.message) + "</div></div></button>";
    }

    // Accueil : les rappels seuls (« Demandez vos notes »), sans carte quand il n'y en a pas.
    function renderRappels() {
      const d = st.d;
      if (!d || !(d.rappels || []).length) return "";
      return '<div class="cn-rappels">' + d.rappels.map(rappelHtml).join("") + "</div>";
    }

    function renderTableau() {
      const d = st.d;
      if (!d || (!(d.familles || []).length && !(d.rappels || []).length)) return "";
      let h = '<div class="card pad cn-tab"><div class="cn-head"><h3 class="cn-title">Où vous perdez des points</h3>' + tip(d.bulle) + "</div>";
      if (d.marches) h += '<div class="muted small cn-sub">' + d.marches + (d.marches > 1 ? " marchés notés" : " marché noté") + "</div>";
      (d.rappels || []).forEach(r => { h += rappelHtml(r); });
      if (d.constat) {
        h += '<div class="cn-constat small cn-mt8">' + ico("search", 14) + '<span style="flex:1;min-width:0">' + cnEsc(d.constat.message) + "</span>"
          + (d.constat.partenaire && o.onPartenaire ? '<button type="button" class="linkbtn small" data-act="partenaire">Chercher un partenaire qui couvre ce manque</button>' + tip("Ouvre le réseau de partenaires d'Adjugo. C'est un constat sur vos marchés, pas une recommandation.", true) : "") + "</div>";
      }
      if ((d.familles || []).length) {
        h += '<ul class="cn-fams">';
        d.familles.forEach(f => {
          h += '<li class="cn-fam"><div class="cn-fam-h"><span class="cn-fam-l">' + cnEsc(f.libelle) + "</span>"
            + (f.moyenne !== null && f.moyenne !== undefined ? barre(f.moyenne) + '<span class="num cn-fam-v">' + Number(f.moyenne) + " %</span>" : '<span class="muted small cn-fam-v">' + Number(f.marches) + (f.marches > 1 ? " marchés" : " marché") + "</span>") + "</div>"
            + '<div class="muted small">' + cnEsc(f.message) + (f.moyenne_gagnant !== null && f.moyenne_gagnant !== undefined ? " · offre retenue : " + Number(f.moyenne_gagnant) + " % en moyenne" : "") + "</div>";
          if ((f.valeurs || []).length) h += '<div class="muted small">' + f.valeurs.map(v => cnEsc(v.nom) + " : " + Number(v.pct) + " %").join(" · ") + "</div>";
          h += "</li>";
        });
        h += "</ul>";
      }
      return h + msgHtml() + "</div>";
    }

    function renderMarche() {
      const d = st.d;
      if (st.err) return '<div class="conv-err cn-mt8" role="alert">' + ico("circle-alert", 15) + "<div>" + cnEsc(st.err) + ' <button type="button" class="linkbtn" data-act="recharger">Réessayer</button></div></div>';
      if (!d || !d.ouvert) return "";
      const id = "cn-t-" + Number(d.projet.id);
      let h = '<section class="cn-card" aria-labelledby="' + id + '"><div class="cn-head"><h3 class="cn-title" id="' + id + '">Vos notes sur ce marché</h3>' + tip(d.bulle) + "</div>";
      if (d.statut === "perdu") h += renderDemande(d);
      h += st.form ? renderForm(d) : renderNotes(d);
      if (d.statut === "gagne" && d.savoir_faire) h += renderSavoirFaire(d.savoir_faire);
      return h + msgHtml() + "</section>";
    }

    function renderDemande(d) {
      const dm = d.demande || {};
      let h = '<div class="cn-bloc">';
      if (dm.rappel && dm.rappel.du) {
        h += '<div class="cn-rappel" role="status">' + ico("bell", 15) + '<span style="flex:1;min-width:0">' + cnEsc(dm.rappel.message) + "</span>" + '<button type="button" class="linkbtn small" data-act="masquer">Ne plus me le rappeler</button></div>';
      }
      if (dm.envoyee_le) {
        h += '<div class="small">' + ico("send", 13) + " Demande envoyée le " + cnEsc(dm.envoyee_le_jj) + ' (par vous, depuis votre messagerie). <button type="button" class="linkbtn small" data-act="demande-annuler">Annuler</button></div>';
      }
      h += '<div class="cn-row">' + btn("demande-ouvrir", ico("mail", 14) + (st.demande ? "Fermer le courrier" : "Demandez vos notes"), dm.envoyee_le || d.notes ? "" : "primary", ' aria-expanded="' + (st.demande ? "true" : "false") + '"')
        + tip("Adjugo prépare le courrier qui demande à l'acheteur les motifs du rejet et vos notes, critère par critère, avec l'article du code de la commande publique qui correspond à la procédure. C'est vous qui l'envoyez : Adjugo n'envoie rien.") + "</div>";
      if (st.demande) h += renderLettre(d);
      return h + "</div>";
    }

    function renderLettre(d) {
      const dm = d.demande || {}, pr = dm.procedure || {}, l = st.lettre;
      const code = st.proc !== null ? st.proc : (pr.code || "");
      let h = '<div class="cn-lettre-box">';
      h += '<div class="field cn-field"><label for="cn-proc-' + Number(d.projet.id) + '">Procédure du marché</label><select id="cn-proc-' + Number(d.projet.id) + '" data-in="proc">'
        + (dm.procedures || []).map(p => '<option value="' + cnEsc(p.code) + '"' + (p.code === code ? " selected" : "") + ">" + cnEsc(p.libelle) + (p.article ? " — article " + cnEsc(p.article) : "") + "</option>").join("") + "</select></div>";
      if (pr.phrase && code === pr.code) h += '<blockquote class="gn-q">' + cnEsc(pr.phrase) + "</blockquote>";
      if (pr.message && code === pr.code) h += '<div class="muted small">' + cnEsc(pr.message) + "</div>";
      if (!l) return h + '<div class="muted small cn-mt8">' + (st.busy === "lettre" ? "Préparation du courrier…" : "") + "</div></div>";
      h += '<div class="cn-delai small cn-mt8">' + ico("clock", 14) + "<span>" + cnEsc(l.message_delai) + "</span></div>";
      if (l.phrase_subsequent) h += '<blockquote class="gn-q">' + cnEsc(l.phrase_subsequent) + "</blockquote>";
      if (l.message_notes) h += '<div class="muted small cn-mt4">' + cnEsc(l.message_notes) + "</div>";
      if (l.message_lots) h += '<div class="muted small cn-mt4">' + cnEsc(l.message_lots) + "</div>";
      h += '<div class="field cn-field cn-mt8"><label for="cn-obj-' + Number(d.projet.id) + '">Objet</label><input id="cn-obj-' + Number(d.projet.id) + '" data-in="objet" value="' + cnEsc(l.objet) + '"></div>';
      h += '<div class="field cn-field"><label for="cn-corps-' + Number(d.projet.id) + '">Courrier (modifiable avant de l\'envoyer)</label><textarea id="cn-corps-' + Number(d.projet.id) + '" data-in="corps" rows="12" class="cn-ta">' + cnEsc(l.corps) + "</textarea></div>";
      h += '<div class="cn-row">' + btn("copier", ico("copy", 14) + "Copier le courrier")
        + '<a class="btn sm" data-lien="mailto" href="' + cnEsc(cnMailto(l.destinataire, l.objet, l.corps)) + '">' + ico("external-link", 14) + "Ouvrir dans ma messagerie</a>"
        + (dm.envoyee_le ? "" : btn("demande-envoyee", ico("check", 14) + "J'ai envoyé ma demande")) + "</div>";
      h += '<div class="muted small cn-mt4">' + cnEsc(l.destinataire ? "Destinataire : " + l.destinataire + ". " : "") + cnEsc(l.destinataire_message) + " " + cnEsc(l.message_envoi) + "</div>";
      return h + "</div>";
    }

    function renderNotes(d) {
      const n = d.notes;
      let h = '<div class="cn-bloc">';
      if (!n) {
        h += '<div class="cn-row">' + btn("saisir", ico("clipboard-list", 14) + "Saisir les notes reçues", d.statut === "gagne" ? "" : "")
          + tip("Quand l'acheteur vous répond, saisissez vos notes critère par critère, ou collez son courrier : Adjugo propose ce qu'il y lit, vous validez.") + "</div>";
        return h + "</div>";
      }
      h += '<ul class="cn-lignes">';
      const tetes = cnTetes(n.lignes, false);
      n.lignes.forEach((x, i) => {
        if (tetes[i]) h += '<li class="cn-lot-h">' + cnEsc(tetes[i]) + "</li>";
        h += '<li class="cn-ligne' + (x.parent ? " cn-sous" : "") + '"><div class="cn-l-h"><span class="cn-l-c">' + cnEsc(x.critere) + (x.poids ? ' <span class="muted">· ' + cnEsc(x.poids) + "</span>" : "") + "</span>"
          + (x.note ? '<span class="num cn-l-n">' + cnEsc(x.note) + " / " + cnEsc(x.note_max) + "</span>" + barre(x.pct) + '<span class="num muted cn-l-p">' + Number(x.pct) + " %</span>" : "")
          + '<span class="pill neutral cn-pill">' + cnEsc(x.famille_libelle) + "</span></div>";
        if (x.note_gagnant) h += '<div class="muted small">Offre retenue : ' + cnEsc(x.note_gagnant) + " / " + cnEsc(x.note_max) + (x.pct_gagnant !== null ? " (" + Number(x.pct_gagnant) + " %)" : "") + "</div>";
        if (x.commentaire) h += '<blockquote class="gn-q">' + cnEsc(x.commentaire) + "</blockquote>";
        const meta = [x.origine_libelle];
        if (x.auteur && x.auteur.type === "invitation") meta.push("partie rédigée par " + (x.auteur.nom || "un partenaire"));
        h += '<div class="muted small">' + cnEsc(meta.join(" · ")) + "</div></li>";
      });
      h += "</ul>";
      if (n.total) h += '<div class="small cn-mt4">Note d\'ensemble : <b class="num">' + cnEsc(n.total.note) + " / " + cnEsc(n.total.note_max) + "</b> (" + Number(n.total.pct) + " %)</div>";
      (n.totaux || []).forEach(t => {
        h += '<div class="small cn-mt4">Note d\'ensemble, ' + cnEsc(String(t.lot_libelle || "").charAt(0).toLowerCase() + String(t.lot_libelle || "").slice(1)) + ' : <b class="num">' + cnEsc(t.note) + " / " + cnEsc(t.note_max) + "</b> (" + Number(t.pct) + " %)</div>";
      });
      (n.messages_total || []).forEach(m => { h += '<div class="muted small cn-mt4">' + cnEsc(m) + "</div>"; });
      if (n.constat) {
        h += '<div class="cn-constat small cn-mt8">' + ico("search", 14) + '<span style="flex:1;min-width:0">' + cnEsc(n.constat.message) + "</span>"
          + (n.constat.partenaire && o.onPartenaire ? '<button type="button" class="linkbtn small" data-act="partenaire">Chercher un partenaire qui couvre ce manque</button>' + tip("Ouvre le réseau de partenaires d'Adjugo. C'est un constat sur ce marché, pas une recommandation.", true) : "") + "</div>";
      }
      h += '<div class="cn-row cn-mt8"><span class="muted small" style="flex:1;min-width:0">Validées par vous le ' + cnEsc(n.valide_le_jj) + ".</span>" + btn("saisir", ico("pen-line", 14) + "Modifier les notes") + "</div>";
      return h + "</div>";
    }

    function renderForm(d) {
      const f = st.form, pid = Number(d.projet.id);
      let h = '<div class="cn-bloc cn-form">';
      h += '<details class="gn-det" data-k="courrier"' + (st.courrier ? " open" : "") + '><summary>Coller le courrier de l\'acheteur</summary>'
        + '<div class="field cn-field cn-mt4"><label for="cn-cour-' + pid + '">Courrier reçu (texte)</label><textarea id="cn-cour-' + pid + '" data-in="courrier" rows="6" class="cn-ta" placeholder="Collez ici le texte du courrier qui donne vos notes.">' + cnEsc(st.courrier) + "</textarea></div>"
        + '<div class="cn-row">' + btn("lire", (st.busy === "lire" ? '<span class="spin"></span>' : ico("scan-text", 14)) + "Lire le courrier", "", st.busy ? " disabled" : "") + tip(d.bulle_lecture)
        + btn("lire-ia", (st.busy === "lire-ia" ? '<span class="spin"></span>' : ico("sparkles", 14)) + "Lire avec l'IA", "", st.busy ? " disabled" : "") + tip((d.ia || {}).bulle, true) + "</div>";
      if (st.lecture) h += '<div class="small cn-mt4" role="status">' + cnEsc(st.lecture) + "</div>";
      h += "</details>";
      h += '<div class="muted small cn-mt8">' + cnEsc((d.criteres || {}).message) + "</div>";
      h += '<ul class="cn-lignes">';
      const lots = d.lots || [], tetes = cnTetes(f, true);
      f.forEach((l, i) => {
        const k = "cn-" + pid + "-" + i;
        if (tetes[i]) h += '<li class="cn-lot-h">' + cnEsc(tetes[i]) + "</li>";
        h += '<li class="cn-ligne cn-edit' + (l.parent ? " cn-sous" : "") + (l.proposee ? " cn-prop" : "") + '" data-i="' + i + '">';
        h += cnLigneTete(l, k, lots);
        if (l.auteur && l.auteur.type === "invitation") h += '<div class="muted small">Partie rédigée par ' + cnEsc(l.auteur.nom || "un partenaire") + "</div>";
        h += '<div class="cn-grid">'
          + '<div class="field cn-field"><label for="' + k + 'n">Votre note</label><input id="' + k + 'n" data-f="note" inputmode="decimal" value="' + cnEsc(l.note) + '"></div>'
          + '<div class="field cn-field"><label for="' + k + 'm">Sur</label><input id="' + k + 'm" data-f="note_max" inputmode="decimal" value="' + cnEsc(l.note_max) + '"></div>'
          + '<div class="field cn-field"><label for="' + k + 'g">Offre retenue <span class="hint">(si donnée)</span></label><input id="' + k + 'g" data-f="note_gagnant" inputmode="decimal" value="' + cnEsc(l.note_gagnant) + '"></div>'
          + '<div class="field cn-field"><label for="' + k + 'f">Famille' + (l.famille === l.famille_proposee ? ' <span class="hint">(proposée)</span>' : "") + '</label><select id="' + k + 'f" data-f="famille">' + (d.familles || []).map(x => '<option value="' + cnEsc(x.code) + '"' + (x.code === l.famille ? " selected" : "") + ">" + cnEsc(x.libelle) + "</option>").join("") + "</select></div></div>";
        if (l.extrait_note) h += '<div class="muted small cn-ex">Lu dans le courrier : « ' + cnEsc(l.extrait_note) + " »</div>";
        if (l.extrait_gagnant && l.extrait_gagnant !== l.extrait_note) h += '<div class="muted small cn-ex">Offre retenue lue dans : « ' + cnEsc(l.extrait_gagnant) + " »</div>";
        h += '<div class="field cn-field"><label for="' + k + 't">Commentaire de l\'acheteur' + (l.commentaire_du_courrier ? ' <span class="hint">(lu dans le courrier)</span>' : "") + '</label><textarea id="' + k + 't" data-f="commentaire" rows="2" class="cn-ta" maxlength="1500">' + cnEsc(l.commentaire) + "</textarea></div>";
        if (l.ajoutee && !l.cle_fixe) h += '<button type="button" class="linkbtn small" data-act="retirer-ligne" data-i="' + i + '">Retirer cette ligne</button>';
        h += "</li>";
      });
      h += "</ul>";
      h += '<div class="cn-row"><button type="button" class="linkbtn small" data-act="ajouter-ligne">Ajouter un critère</button></div>';
      h += '<div class="cn-row cn-mt8">' + btn("valider", (st.busy === "valider" ? '<span class="spin"></span>' : ico("check", 14)) + "Valider les notes", "primary", st.busy ? " disabled" : "") + btn("annuler", "Annuler")
        + tip("Valider enregistre les notes telles qu'elles sont à l'écran, et la famille de chaque critère. Une valeur lue dans le courrier n'est gardée comme « lue dans le courrier » que si la ligne citée y est encore.", true) + "</div>";
      return h + "</div>";
    }

    function renderSavoirFaire(s) {
      let h = '<div class="cn-bloc">';
      if (s.deja) h += '<div class="small">' + ico("library", 14) + " Ajouté à « Mon savoir-faire » le " + cnEsc(s.deja.le_jj) + " : " + cnEsc(s.deja.nom) + ".</div>";
      else if (s.parties) h += '<div class="cn-row">' + btn("savoir-faire", (st.busy === "sf" ? '<span class="spin"></span>' : ico("library", 14)) + "Ajouter ce dossier à mon savoir-faire", "", st.busy ? " disabled" : "") + tip(s.bulle) + "</div>";
      else if (s.message) h += '<div class="muted small">' + cnEsc(s.message) + "</div>";
      return h + "</div>";
    }

    // ── Actions ──────────────────────────────────────────────────────────────────────────────────
    function lireForm() {
      if (!st.form) return;
      el.querySelectorAll("li.cn-edit[data-i]").forEach(li => {
        const l = st.form[Number(li.dataset.i)];
        if (!l) return;
        li.querySelectorAll("[data-f]").forEach(inp => { l[inp.dataset.f] = inp.value; });
      });
      const c = el.querySelector('[data-in="courrier"]');
      if (c) st.courrier = c.value;
    }

    async function lettre() {
      st.busy = "lettre"; render();
      const proc = st.proc !== null ? st.proc : "";
      const q = st.proc !== null ? "?procedure=" + encodeURIComponent(proc === "" ? "inconnue" : proc) : "";
      const r = await call("GET", "/" + encodeURIComponent(o.pid) + "/courrier" + q);
      st.busy = "";
      if (r.ok) st.lettre = r.data; else dire(r.message, true);
      render();
    }

    async function copier() {
      const t = el.querySelector('[data-in="corps"]'), ob = el.querySelector('[data-in="objet"]');
      const texte = (ob ? "Objet : " + ob.value + "\n\n" : "") + (t ? t.value : "");
      try { await navigator.clipboard.writeText(texte); dire("Courrier copié : collez-le dans votre messagerie ou sur la plateforme de l'acheteur."); }
      catch (e) { if (t) { t.focus(); t.select(); } dire("Sélectionnez le texte du courrier, puis copiez-le (Ctrl+C ou Cmd+C).", true); }
      render();
    }

    async function ecrire(method, path, body, ok) {
      st.busy = path; render();
      const r = await call(method, "/" + encodeURIComponent(o.pid) + path, body);
      st.busy = "";
      if (r.ok) { if (r.data && r.data.projet) st.d = r.data; dire(ok); changed(); }
      else dire(r.message, true);
      render();
      return r.ok;
    }

    async function act(a, b) {
      if (st.busy && !["annuler"].includes(a)) return;
      if (a === "recharger") { st.err = ""; load(); return; }
      if (a === "ouvrir") { if (o.onOuvrir) o.onOuvrir(Number(b.dataset.pid)); return; }
      if (a === "partenaire") { if (o.onPartenaire) o.onPartenaire(); return; }
      if (a === "demande-ouvrir") { st.demande = !st.demande; dire(""); if (st.demande && !st.lettre) { lettre(); return; } render(); return; }
      if (a === "copier") { copier(); return; }
      if (a === "demande-envoyee") { await ecrire("POST", "/demande", { envoyee: true }, "Demande notée : le rappel s'arrête. Adjugo n'a rien envoyé."); return; }
      if (a === "demande-annuler") { await ecrire("POST", "/demande", { envoyee: false }, "Demande retirée."); return; }
      if (a === "masquer") { await ecrire("POST", "/rappel/masquer", undefined, "Rappel retiré pour ce marché."); return; }
      if (a === "saisir") { st.form = ((st.d.criteres || {}).lignes || []).map(l => Object.assign({}, l)); st.lecture = null; dire(""); render(); return; }
      if (a === "annuler") { st.form = null; st.lecture = null; dire(""); render(); return; }
      if (a === "ajouter-ligne") {
        lireForm();
        const n = st.form.filter(l => /^u\d+$/.test(l.cle || "")).reduce((m, l) => Math.max(m, Number(l.cle.slice(1)) || 0), 0) + 1;
        st.form.push({ cle: "u" + n, critere: "", parent: "", poids: "", niveau: 1, famille: "autre", famille_proposee: "autre", note: "", note_max: "", note_gagnant: "", commentaire: "", origine: "saisie", ajoutee: true });
        render();
        const inp = el.querySelector('li.cn-edit[data-i="' + (st.form.length - 1) + '"] [data-f="critere"]'); if (inp) inp.focus();
        return;
      }
      if (a === "retirer-ligne") { lireForm(); st.form.splice(Number(b.dataset.i), 1); render(); return; }
      if (a === "lire" || a === "lire-ia") {
        lireForm();
        if (String(st.courrier || "").trim().length < 40) { st.lecture = "Collez d'abord le courrier de l'acheteur (au moins quelques lignes)."; render(); return; }
        st.busy = a; st.lecture = a === "lire-ia" ? "L'IA lit le courrier…" : null; render();
        const r = await call("POST", "/" + encodeURIComponent(o.pid) + (a === "lire" ? "/lire" : "/lire-ia"), { courrier: st.courrier });
        st.busy = "";
        if (r.ok) { st.form = cnFusion(st.form, r.data.propositions); st.lecture = r.data.message; }
        else st.lecture = r.message;
        render();
        return;
      }
      if (a === "valider") {
        lireForm();
        const err = cnControle(st.form, st.d.lots);
        if (err) { dire(err, true); render(); return; }
        const body = { lignes: cnPayload(st.form), rev: st.d.rev };
        if (String(st.courrier || "").trim().length >= 40) body.courrier = st.courrier;
        const ok = await ecrire("PUT", "/notes", body, "Notes validées. Elles comptent dans « Où vous perdez des points ».");
        if (ok) { st.form = null; st.lecture = null; render(); }
        return;
      }
      if (a === "savoir-faire") {
        st.busy = "sf"; render();
        const r = await call("POST", "/" + encodeURIComponent(o.pid) + "/savoir-faire");
        st.busy = "";
        if (r.ok) { dire(r.data.message); changed(); await load(); }
        else { dire(r.message, true); render(); }
      }
    }

    const onClick = (e) => {
      const b = e.target.closest && e.target.closest("[data-act]");
      if (!b || !el.contains(b) || b.disabled) return;
      e.preventDefault();
      act(b.dataset.act, b);
    };
    const onChange = (e) => {
      const t = e.target;
      if (t && t.matches && t.matches('[data-in="proc"]')) { st.proc = t.value; st.lettre = null; lettre(); }
    };
    const onInput = (e) => {
      const t = e.target;
      if (!t || !t.matches) return;
      if (t.matches('[data-in="corps"], [data-in="objet"]')) {
        const a = el.querySelector('[data-lien="mailto"]'), c = el.querySelector('[data-in="corps"]'), ob = el.querySelector('[data-in="objet"]');
        if (a && st.lettre) a.setAttribute("href", cnMailto(st.lettre.destinataire, ob ? ob.value : st.lettre.objet, c ? c.value : st.lettre.corps));
      }
    };
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    el.addEventListener("input", onInput);
    load();

    return {
      reload: load,
      destroy() {
        st.destroyed = true;
        el.removeEventListener("click", onClick);
        el.removeEventListener("change", onChange);
        el.removeEventListener("input", onInput);
        el.innerHTML = "";
      },
    };
  }

  // Les notes communes du marché dans l'espace d'un partenaire du groupement (app/static/redaction-partenaire.js) :
  // toutes les lignes, ses parties signalées. Lecture seule ; `c` vient de vue_partenaire().carnet.
  function cnPartenaireHtml(c) {
    if (!c || !(c.lignes || []).length) return "";
    let h = '<div class="cn-part"><div class="rp-lbl">Les notes du marché' + tip(c.message) + "</div>";
    if ((c.vos_parties || []).length) h += '<div class="small">Vos parties : ' + c.vos_parties.map(x => cnEsc(x.critere) + (x.lot_libelle ? " (" + cnEsc(String(x.lot_libelle).charAt(0).toLowerCase() + String(x.lot_libelle).slice(1)) + ")" : "") + (x.note ? " " + cnEsc(x.note) + " / " + cnEsc(x.note_max) + " (" + Number(x.pct) + " %)" : "")).join(" · ") + "</div>";
    h += '<details class="gn-det"><summary>Voir toutes les notes</summary><ul class="cn-lignes">';
    const tetes = cnTetes(c.lignes, false);
    c.lignes.forEach((x, i) => {
      if (tetes[i]) h += '<li class="cn-lot-h">' + cnEsc(tetes[i]) + "</li>";
      h += '<li class="cn-ligne' + (x.parent ? " cn-sous" : "") + (x.vous ? " cn-vous" : "") + '"><div class="cn-l-h"><span class="cn-l-c">' + cnEsc(x.critere) + "</span>"
        + (x.note ? '<span class="num cn-l-n">' + cnEsc(x.note) + " / " + cnEsc(x.note_max) + "</span>" + barre(x.pct) + '<span class="num muted cn-l-p">' + Number(x.pct) + " %</span>" : "")
        + (x.vous ? '<span class="pill go cn-pill">votre partie</span>' : "") + "</div>";
      if (x.note_gagnant) h += '<div class="muted small">Offre retenue : ' + cnEsc(x.note_gagnant) + " / " + cnEsc(x.note_max) + "</div>";
      if (x.commentaire) h += '<blockquote class="gn-q">' + cnEsc(x.commentaire) + "</blockquote>";
      h += "</li>";
    });
    h += "</ul></details>";
    if (c.total) h += '<div class="small cn-mt4">Note d\'ensemble du groupement : <b class="num">' + cnEsc(c.total.note) + " / " + cnEsc(c.total.note_max) + "</b> (" + Number(c.total.pct) + " %)</div>";
    (c.totaux || []).forEach(t => {
      h += '<div class="small cn-mt4">Note d\'ensemble du groupement, ' + cnEsc(String(t.lot_libelle || "").charAt(0).toLowerCase() + String(t.lot_libelle || "").slice(1)) + ' : <b class="num">' + cnEsc(t.note) + " / " + cnEsc(t.note_max) + "</b> (" + Number(t.pct) + " %)</div>";
    });
    return h + "</div>";
  }

  root.AdjugoCarnetNotes = { mount, partenaireHtml: cnPartenaireHtml,
    _pur: { cnEsc, cnNombre, cnPct, cnMailto, cnFusion, cnPayload, cnControle, cnPartenaireHtml, cnTetes, cnLigneTete } };
})(typeof window !== "undefined" ? window : this);
