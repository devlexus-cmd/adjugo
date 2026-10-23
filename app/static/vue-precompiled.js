/* Gabarits Vue précompilés (scripts/precompile_vue.mjs) — co-traitance v2 / durcissement CSP.
 *
 * En build RUNTIME-ONLY, Vue n'embarque pas de compilateur de gabarits (c'est lui qui imposait
 * `script-src 'unsafe-eval'` via `new Function`). On remplace ici le compilateur par une simple
 * table de render functions précompilées AU BUILD, à la version EXACTE de Vue (même sortie que
 * le compilateur embarqué) : aucune compilation dans le navigateur, aucun 'eval', rendu inchangé.
 *
 * - La racine reçoit son render directement (app.js : render = window.__ADJ_R["__root__"]).
 * - Les composants (template:) passent par registerRuntimeCompiler : Vue appelle cette fonction
 *   avec la chaîne du gabarit, on renvoie le render précompilé (clé = la chaîne exacte).
 * registerRuntimeCompiler installe aussi le `withProxy` des render runtime-compilés (_rc) — nos
 * renders portent _rc=true (posé dans app.render.js), donc comportement identique au build complet.
 *
 * À charger APRÈS vue.runtime-*.prod.js et app.render.js, AVANT app.js.
 */
(function () {
  "use strict";
  if (!window.Vue || typeof window.Vue.registerRuntimeCompiler !== "function") {
    try { console.error("[Adjugo] Vue runtime introuvable : vue-precompiled.js doit suivre le build Vue."); } catch (e) {}
    return;
  }
  var R = window.__ADJ_R || {};
  window.Vue.registerRuntimeCompiler(function (template) {
    var r = R[template];
    if (!r && typeof template === "string") r = R[template.trim()];
    if (!r) {
      try { console.error("[Adjugo] gabarit non précompilé (relancez scripts/precompile_vue.mjs) :",
                          String(template || "").slice(0, 120)); } catch (e) {}
    }
    return r;
  });
})();
