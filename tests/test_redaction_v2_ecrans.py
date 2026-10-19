"""
Rédaction, vague 2 — les ÉCRANS de l'atelier du dossier de présentation (étude §6.4 G + A0).

Ce qui est vérifié, sans navigateur ni réseau (IA simulée) :
 • la page du marché porte une carte compacte « Dossier de présentation » (bulle « mémoire
   technique ») avec UN bouton qui ouvre l'atelier ; le menu n'est pas réorganisé ;
 • l'atelier : plan, texte, faits « à relire » (Corriger / Retirer / Je l'ai relu, jamais de
   correction par l'IA), extraits privés, historique et retour à une version, tâches de fond
   suivies toutes les 2 s et reprises, brouillon local, export Word / PDF avec la fenêtre de
   dérogation (avertissement d'irrégularité), mention « Préparé avec assistance IA » avant
   l'export ; sur téléphone : lire et valider seulement ;
 • « Mon savoir-faire » ne rédige plus : lien vers l'atelier du marché ;
 • zéro émoji, jamais « vérifié », aucun bouton sans type, bulles (i) bien formées ;
 • les fonctions pures de l'écran (rendu sûr du texte, surlignage des faits, « Retirer »,
   limites, nom du fichier) exécutées sous Node ; le gabarit compilé par le Vue du dépôt ;
 • le parcours de l'écran contre la vraie API : chaque champ lu par l'écran existe.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.test_redaction_socle0 import _company, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _ecrire, _etat, _projet, _redige
from tests.zones import zone, zones

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


HTML, JS, CSS = _read("app.html"), _read("app.js"), _read("styles.css")


def _between(s, start, end):
    i = s.index(start)
    return s[i:s.index(end, i)]


def _sans_commentaires_html(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _sans_commentaires_js(s):
    return re.sub(r"(^|\s)//[^\n]*", r"\1", s)


# Zones repérées par leur attribut data-test (tests/zones.py, docs/REORGANISATION_V1.md) : elles
# restent justes quand la page est réordonnée.
CARTE = zone(HTML, "marche-dossier-presentation")
ATELIER = zone(HTML, "vue-atelier")
FENETRES = "\n".join(zones(HTML, "fenetres-atelier"))
KB = zone(HTML, "vue-kb")
JS_PUR = _between(JS, "// ══════════ Atelier du dossier de présentation (rédaction, vague 2) — fonctions pures",
                  "const __adjApp = createApp({")
JS_METH = _between(JS, "    // ══════════ Atelier du dossier de présentation (rédaction, vague 2) ══════════",
                   "    saveBlob(blob, name) {")
CSS_ATL = CSS[CSS.index("/* ══════════ Atelier du dossier de présentation (rédaction, vague 2)"):]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆✅❌✔✖★☆]")


# ═══ 1. Gabarits : où l'atelier s'affiche, ce qu'il montre ═══════════════════════════════

def test_carte_du_marche_compacte_un_seul_bouton_et_menu_inchange():
    page = zone(HTML, "vue-aodetail")
    # La carte est sur la page du marché, juste avant les documents de réponse (étape « préparer »).
    assert page.index("Estimation du prix") < page.index("id=\"atl-card\"") < page.index("Mes documents de réponse")
    c = _sans_commentaires_html(CARTE)
    assert "Dossier de présentation" in c and "la partie technique de votre offre que demande le règlement de la consultation" in c and "mémoire" not in c   # vague 0
    assert len(re.findall(r"<button\b(?![^>]*class=\"tip)", c)) == 1 and "@click=\"atlOpen()\"" in c
    assert "Préparer le dossier de présentation" in c and "Ouvrir l'atelier" in c
    # Le menu n'est pas réorganisé : aucune entrée « atelier » dans la barre latérale.
    nav = zone(HTML, "menu")
    assert "atelier" not in nav and "go('atelier')" not in HTML
    for entree in ("go('dashboard')", "go('sourcing')", "go('pipeline')", "go('kb')", "go('documents')"):
        assert entree in nav


def test_atelier_plan_texte_faits_sources_et_actions():
    a = _sans_commentaires_html(ATELIER)
    for libelle in ("Retour au marché", "Plan", "Rédiger avec Adjugo", "Raccourcir", "J'écris moi-même",
                    "Valider", "Marquer relue", "À relire", "Corriger", "Retirer", "Je l'ai relu",
                    "Remettre à relire", "Extraits de vos documents", "Historique", "Revenir à cette version",
                    "Exporter en Word", "PDF", "Page de garde", "Sommaire", "Ce que demande l'acheteur",
                    "\"Rédiger les \" + atlAEcrire() + \" parties à écrire\"", "Rédiger la partie à écrire", "Reprendre", "Copier mon texte",
                    "Titre", "Liste", "Tableau", "Enregistrer", "Commencer avec ce plan", "Exporter malgré tout…"):
        assert libelle in a, libelle
    # Le message A0 exact, le poids tel qu'écrit, le découpage proposé dit comme tel.
    assert "Adjugo ne trouve pas d'où vient ce fait : relisez-le." in a
    assert "aucun poids écrit dans le règlement" in a and "sans poids écrit" in a
    assert "Découpage proposé par Adjugo : il n'est pas imposé par l'acheteur." in a
    assert "Le dossier de l'acheteur ne compte jamais comme source pour une phrase sur votre entreprise." in a
    # Compteur toujours « environ », comparé aux limites (vert / orange / rouge).
    assert "Environ {{ atlNum(atl.st.compteur.total.mots) }}" in a and "atlLimCls(l)" in a
    for niv in ("atl-lim-vert", "atl-lim-orange", "atl-lim-rouge"):
        assert "." + niv in CSS_ATL
    # Mention IA visible AVANT l'export (décision 9a) ; rappel du cadre imposé (décision 11).
    assert "atl.st.export.mention_ia" in a and "atl.st.export.message_ia" in a
    assert "atlAvert(atl.st, 'fichier_impose')" in a
    assert "atl.prop.proposition.avertissement_fichier" in a                # une phrase par cas, venue du serveur
    # Les parties d'un partenaire (vague 4) : jamais supposées modifiables, matière privée cachée.
    assert "atlSec().peut_ecrire" in a and "atlSec().prive_visible" in a
    assert "Les extraits et les faits à relire de cette partie restent chez son auteur." in a


def test_mobile_lire_et_valider_seulement():
    a = _sans_commentaires_html(ATELIER)
    # L'éditeur, la rédaction, Corriger / Retirer, le plan modifiable et l'export : jamais sur téléphone.
    assert "v-if=\"atl.mode==='modifier' && !atlMobile\"" in a
    assert "<template v-if=\"!atlMobile && atl.mode !== 'modifier'\">\n                      <button type=\"button\" class=\"btn sm primary\" @click=\"atlRediger(atlSec())\"" in a
    assert "<template v-if=\"!atlMobile\"><button type=\"button\" class=\"btn sm\" @click=\"atlFaitCorriger(f)\"" in a
    assert "<div v-if=\"!atlMobile\" class=\"row wrap atl-g6\">" in a          # export
    assert "Sur téléphone, vous pouvez lire et valider." in a
    # Valider et « Je l'ai relu » restent possibles partout.
    assert "@click=\"atlValider()\"" in a and "@click=\"atlFait(f, 'relu_par_vous')\"" in a
    assert "matchMedia(\"(max-width:640px)\")" in JS and "this.atlMobile = mq.matches" in JS
    for garde in ("atlEdit() {\n      const a = this.atl, s = this.atlSec(); if (!s || !s.peut_ecrire || this.atlMobile) return;",
                  "atlFaitCorriger(f) {\n      const a = this.atl; if (this.atlMobile) return;",
                  "atlFaitRetirer(f) {\n      const a = this.atl; if (this.atlMobile) return;"):
        assert garde in JS_METH, garde
    # Aucune barre de défilement horizontale : colonnes empilées, tableaux à largeur fixe.
    assert "@media (max-width:860px) {\n  .atl-grid { grid-template-columns:minmax(0,1fr); }" in CSS_ATL
    assert ".atl-table { width:100%; table-layout:fixed;" in CSS_ATL
    assert ".atl { position:relative; }" in CSS_ATL     # textes pour lecteurs d'écran contenus dans la zone qui défile


def test_fenetres_derogation_debit_version_et_plan():
    f = _sans_commentaires_html(FENETRES)
    assert "L'export est bloqué" in f and "Pourquoi exporter en l'état ?" in f
    assert "atl.derog.avert" in f and "atl-irreg" in f                 # « L'acheteur peut juger… » avant de confirmer
    assert "En quelques mots (obligatoire)" in f and "maxlength=\"300\"" in f
    assert "Corriger d'abord" in f and "Enregistrer et exporter" in f
    assert "Confirmer le débit" in f and "atlDebitOk()" in f
    assert "Reconstruire le plan" in f and "Reconstruire quand même" in f and "jamais supprimées" in f
    # Jamais de contournement silencieux : l'export bloqué ouvre la fenêtre, la dérogation passe par l'API.
    assert "d.code === \"export_bloque\") { this._atlDerogOpen(d, fmt); return; }" in JS_METH
    assert "this._atlUrl(\"/derogation\"), { raison: g.raison, texte: t, etat_hash: g.hash }" in JS_METH
    assert "etat_hash: st.blocage && st.blocage.etat_hash" in JS_METH


def test_savoir_faire_renvoie_a_l_atelier_du_marche():
    k = _sans_commentaires_html(KB)
    assert "Importer le dossier & rédiger" not in k and "kbMemoire" not in k and "kb.memoire" not in k
    assert "Ouvrir l'atelier" in k and "kbOuvrirAtelier(p)" in k and "Voir tous mes marchés" in k
    assert "la partie technique de votre offre que demande le règlement de la consultation" in k and "mémoire technique" not in k                          # vague 0
    assert "/api/knowledge/memoire-upload" not in JS and "kbMemoire" not in JS and "memoireLoading" not in JS
    assert "Votre savoir-faire" in k and "Répondre à un questionnaire" in k       # la bibliothèque reste


def test_regles_d_interface_zero_emoji_jamais_verifie_boutons_types_bulles():
    for nom, bloc in (("atelier", ATELIER), ("carte", CARTE), ("fenêtres", FENETRES), ("js", JS_METH),
                      ("pur", JS_PUR), ("css", CSS_ATL)):
        assert not EMOJI.search(bloc), nom
    # Côté script, seuls les textes montrés (chaînes entre guillemets) comptent.
    chaines = " ".join(re.findall(r'"((?:[^"\\\n]|\\.)*)"', _sans_commentaires_js(JS_METH + JS_PUR)))
    for nom, bloc in (("atelier", _sans_commentaires_html(ATELIER)), ("carte", _sans_commentaires_html(CARTE)),
                      ("fenêtres", _sans_commentaires_html(FENETRES)), ("js", chaines)):
        low = bloc.lower()
        assert "vérifié" not in low and "verifie" not in low, nom
        for jargon in ("consortium", "mandataire", "workflow", "prompt", "token"):
            assert jargon not in low, (nom, jargon)
    for bloc in (ATELIER, CARTE, FENETRES):
        s = _sans_commentaires_html(bloc)
        for m in re.finditer(r"<button\b(?:[^>\"]|\"[^\"]*\")*>", s):
            assert 'type="button"' in m.group(0), m.group(0)[:120]
        assert s.count('class="tip-b" role="tooltip"') == s.count("tip-b")
    # v-html seulement sur le rendu sûr de l'atelier (vague 4 : la part d'un partenaire dans « Qui écrit
    # quoi », par le même rendu, renvois montrés comme « source du partenaire »).
    vh = re.findall(r'v-html="([^"]+)"', ATELIER + FENETRES)
    assert sorted(set(vh)) == ["atlHtml(atlSec())", "atlPhrase(f)", "atlRepHtml(b.v)", "atlVueHtml()"]


def test_routes_branchees_suivi_des_taches_et_brouillon_local():
    for route in ("\"/api/atelier/\"", "\"/taches/\"", "\"/derogation\"", "\"/export\"", "\"/restaurer\"",
                  "\"/valider\"", "\"/relu\"", "\"/faits/\"", "\"/texte\"", "\"/raccourcir\"", "\"/rediger\"",
                  "\"/plan\"", "\"/options\"", "\"/remettre\"", "\"/sections\"", "\"/versions/\""):
        assert route in JS_METH, route
    assert "setInterval(() => this._atlPoll(), 2000)" in JS_METH                 # toutes les 2 s
    assert "_atlResume(d, pid)" in JS_METH and "rc.job_id && !this.atlJobs[rc.job_id]" in JS_METH   # reprise
    # Brouillon local, propre à l'utilisateur, au marché et à la partie.
    assert "\"adjugo_atl_\" + ((this.user && this.user.id) || 0) + \"_\" + this.atl.pid + \"_\" + sid" in JS_METH
    assert "base_version_id: a.edit.base" in JS_METH and "texte_modifie_entre_temps" in JS_METH
    assert "accepte_debit: true" in JS_METH and "debit_a_confirmer" in JS_METH
    # Le texte est envoyé tel quel par l'utilisateur : aucune réécriture par l'IA dans Corriger / Retirer.
    corr = _between(JS_METH, "atlFaitCorriger(f) {", "// ── Historique des versions ──")
    assert "this.api(" not in corr


# ═══ 2. Fonctions pures de l'écran, exécutées sous Node ══════════════════════════════════

def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    esc = _between(JS, "function _escHtml(s) {", "function _mdProtect(s)")
    out = subprocess.run([node, "-e", esc + "\n" + JS_PUR + "\n" + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_rendu_sur_du_texte_et_surlignage_des_faits_sous_node():
    md = ("## Organisation <script>alert(1)</script>\n"
          "Notre équipe de **12 compagnons** intervient [S1]. En 2012, rien.\n"
          "- Une nacelle de 18 m\n- Certifiés Qualibat 3191\n"
          "1. Phase un\n2. Phase deux\n\n"
          "| Phase | Durée |\n| --- | --- |\n| Travaux | [À compléter : durée] |\n"
          "<img src=x onerror=alert(1)> \"guillemets\"")
    faits = [{"id": "f1", "fait": "12 compagnons", "statut": "a_relire"},
             {"id": "f2", "fait": "12", "statut": "a_relire"},
             {"id": "f3", "fait": "Qualibat 3191", "statut": "relu_par_vous"},
             {"id": "f4\"><b", "fait": "nacelle", "statut": "a_relire"}]
    r = _node(f"const md = {json.dumps(md)}, faits = {json.dumps(faits)};\n"
              "console.log(JSON.stringify({h: atlMdToHtml(md, faits), p: atlPhraseHtml('Une nacelle <b>de</b> 18 m', 'nacelle'),"
              " vide: atlMdToHtml('', [])}));")
    h = r["h"]
    assert "<script" not in h and "<img" not in h and "onerror=alert(1)&gt;" in h and "&quot;guillemets&quot;" in h
    assert '<h5 class="atl-h">Organisation &lt;script&gt;' in h            # « ## » sous le titre de la partie
    # Gras traité d'abord : le fait reste surligné DANS le gras, sans astérisques ni balises croisées.
    assert '<strong><mark class="atl-fait" data-fait="f1">12 compagnons</mark></strong>' in h and "**" not in h
    assert "En 2012" in h and "20<mark" not in h                       # « 12 » ne marque pas « 2012 »
    assert "Qualibat 3191" in h and 'data-fait="f3"' not in h           # un fait relu n'est plus surligné
    assert 'data-fait="f4&quot;&gt;&lt;b"' in h                         # identifiant échappé
    assert '<sup class="atl-ref" data-ref="S1">S1</sup>' in h
    assert '<span class="atl-todo">[À compléter : durée]</span>' in h
    assert "<ul><li>" in h and "<ol><li>Phase un</li><li>Phase deux</li></ol>" in h
    assert '<table class="atl-table"><thead><tr><th scope="col">Phase</th>' in h and "---" not in h
    assert r["p"] == 'Une <mark class="atl-fait">nacelle</mark> &lt;b&gt;de&lt;/b&gt; 18 m' and r["vide"] == ""


def test_retirer_corriger_limites_mots_et_nom_du_fichier_sous_node():
    t = ("Notre équipe compte 12 compagnons. Le site est occupé.\n\n"
         "- Une nacelle de 18 m.\n- Un chef de chantier.\n\n"
         "| Phase | Durée |\n| --- | --- |\n| Travaux | 12 jours |\n\n"
         "Nos 12 camions roulent. Nous garantissons zéro accident.")
    r = _node(f"const t = {json.dumps(t)};\n"
              "console.log(JSON.stringify({"
              " a: atlRetirerPhrase(t, '12 compagnons', 'Notre équipe compte 12 compagnons.'),"
              " b: atlRetirerPhrase(t, 'nacelle', 'Une nacelle de 18 m.'),"
              " c: atlRetirerPhrase(t, '12 jours', 'Travaux ; 12 jours'),"
              " d: atlRetirerPhrase(t, 'zéro', 'Nous garantissons zéro accident.'),"
              " e: atlRetirerPhrase(t, 'ISO 9001', 'x'),"
              " f: atlRetirerPhrase('Une phrase seule avec 3 grues.\\n\\nSuite.', '3 grues', 'Une phrase seule avec 3 grues.'),"
              " pos: atlFaitPos(t, '12', 'Nos 12 camions roulent.'),"
              " lim: [atlLimNiveau({depassee: true}), atlLimNiveau({mesure: 7.5, valeur: 8}), atlLimNiveau({mesure: 3, valeur: 8}),"
              "       atlLimNiveau({mesure: null, valeur: 8}), atlLimNiveau(null)],"
              " mots: [atlMots('## Titre\\n- deux mots [S1]\\n| a | b |'), atlMots(\"l'équipe d'Adjugo\")],"
              " nom: [atlNomFichier(\"attachment; filename=\\\"Memoire justificatif.docx\\\"; filename*=UTF-8''M%C3%A9moire%20justificatif.docx\", 'x'),"
              "       atlNomFichier('attachment; filename=\"Dossier.pdf\"', 'x'), atlNomFichier('', 'Repli.docx')]}));")
    assert r["a"].startswith("Le site est occupé.\n\n- Une nacelle") and "12 compagnons" not in r["a"]
    assert "nacelle" not in r["b"] and "- Un chef de chantier." in r["b"] and "- \n" not in r["b"]
    assert "| Travaux | |" in r["c"] and "12 jours" not in r["c"] and "| Phase | Durée |" in r["c"]   # cellule vidée
    assert r["d"].endswith("Nos 12 camions roulent.") and "zéro" not in r["d"]
    assert r["e"] is None
    assert r["f"] == "Suite."
    assert t[r["pos"][0]:r["pos"][1]] == "12" and t[r["pos"][0] - 4:r["pos"][0]] == "Nos "   # la bonne phrase
    assert r["lim"] == ["rouge", "orange", "vert", "", ""]
    assert r["mots"] == [5, 2]
    assert r["nom"] == ["Mémoire justificatif.docx", "Dossier.pdf", "Repli.docx"]


def test_gabarit_compile_par_le_vue_du_depot():
    """Le gabarit complet (carte, atelier, fenêtres compris) se compile sans erreur ni avertissement."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    vue = sorted(p for p in os.listdir(os.path.join(STATIC, "vendor")) if p.startswith("vue-"))[-1]
    start = HTML.index('<div id="app">') + len('<div id="app">')
    end = HTML.index("<script", start)
    tpl = HTML[start:end]
    tpl = tpl[:tpl.rindex("</div>")]
    script = ("const fs = require('fs'), vm = require('vm');\n"
              f"const src = fs.readFileSync({json.dumps(os.path.join(STATIC, 'vendor', vue))}, 'utf8');\n"
              "const decode = (s) => String(s).replace(/&(#\\d+|#x[0-9a-f]+|amp|lt|gt|quot|apos|nbsp);/gi, (m, g) => {"
              " g = g.toLowerCase(); if (g[0] === '#') return String.fromCodePoint(g[1] === 'x' ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10));"
              " return ({amp: '&', lt: '<', gt: '>', quot: '\"', apos: \"'\", nbsp: '\\u00a0'})[g]; });\n"
              "const doc = { createElement() { const el = { _h: '' }; Object.defineProperty(el, 'innerHTML', { set(v) { el._h = v;"
              " const m = /^<div foo=\"([\\s\\S]*)\">$/.exec(v); el.children = m ? [{ getAttribute: () => decode(m[1]) }] : []; },"
              " get() { return el._h; } }); Object.defineProperty(el, 'textContent', { get() { return decode(el._h); } }); return el; } };\n"
              "const ctx = { console, window: {}, document: doc }; vm.createContext(ctx); vm.runInContext(src + ';this.Vue = Vue;', ctx);\n"
              f"const errors = []; ctx.Vue.compile({json.dumps(tpl)}, {{ onError: (e) => errors.push(String(e.message)),"
              " onWarn: (e) => errors.push('warn ' + String(e.message)) });\n"
              "console.log(JSON.stringify(errors));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


# ═══ 3. Le parcours de l'écran contre la vraie API (IA simulée) ═══════════════════════════

def test_parcours_de_l_ecran_contre_l_api(client, auth, fake_llm):  # noqa: F811
    """Chaque champ que l'écran lit existe, dans l'ordre où l'écran appelle l'API."""
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    # Carte, sans dossier : la proposition (rien n'est enregistré).
    d = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert d["dossier"] is None
    p = d["proposition"]
    for k in ("message", "sections", "fichier_impose", "message_fichier", "source", "limites", "criteres_hors_dossier"):
        assert k in p, k
    assert {"document", "chaque_question", "police", "non_controlees"} <= set(p["limites"])
    for s in p["sections"]:
        assert {"numero", "intitule", "parents", "critere", "poids", "limite"} <= set(s)
    assert client.get(f"/api/atelier/{pid}?base=libre", headers=h).json()["proposition"]["source"] == "libre"
    # « Commencer avec ce plan ».
    st = _creer(client, h, pid)
    for k in ("projet", "dossier", "sections", "sections_retirees", "compteur", "limites", "blocage", "quota",
              "export", "dossier_acheteur", "derogations_possibles"):
        assert k in st, k
    assert {"plan_source", "plan", "dernier_export"} <= set(st["dossier"])
    assert {"message", "criteres_hors_dossier", "limites"} <= set(st["dossier"]["plan"])
    assert {"mots", "caracteres", "pages"} <= set(st["compteur"]["total"]) and st["compteur"]["message"]
    assert {"bloque", "peut_exporter", "etat_hash", "raisons", "derogation", "avertissements"} <= set(st["blocage"])
    assert any(a["code"] == "fichier_impose" for a in st["blocage"]["avertissements"])
    assert {"ia_utilisee", "mention_ia", "message_ia", "nom_fichier_docx", "nom_fichier_pdf", "police", "options"} <= set(st["export"])
    assert {"message", "analyse_debitee"} <= set(st["quota"])
    assert {"pieces", "a_change", "message"} <= set(st["dossier_acheteur"])
    for pc in st["dossier_acheteur"]["pieces"]:
        assert {"nom", "libelle", "lu_en_entier"} <= set(pc)
    for lim in st["limites"]:
        assert {"portee", "section_id", "titre", "message", "phrase", "source", "depassee", "mesure", "valeur"} <= set(lim)
    sec = st["sections"][0]
    for k in ("id", "numero_affiche", "intitule", "titre", "parents", "question", "source_plan", "critere", "poids",
              "partie_de_critere", "statut", "statut_libelle", "intitule_modifiable", "peut_ecrire", "prive_visible",
              "redaction_en_cours", "validation", "version_courante", "nb_versions", "a_completer", "faits_a_relire",
              "compteur", "auteur"):
        assert k in sec, k
    assert st["export"]["ia_utilisee"] is False and st["export"]["mention_ia"] == ""
    # « Rédiger avec Adjugo » : tâche de fond, suivie par /taches.
    ans, _seen = _redige("Notre équipe de 12 compagnons intervient [S1]. Nous utilisons une nacelle de 18 m. "
                         "[À compléter : durée des travaux]")
    fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/rediger", headers=h, json={"accepte_debit": False})
    assert r.status_code == 202, r.text
    assert {"tache", "quota", "section_ids"} <= set(r.json()) and r.json()["section_ids"] == [sec["id"]]
    pendant = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sec["id"])
    if pendant["redaction_en_cours"]:                                       # reprise : job_id + action
        assert {"job_id", "action", "statut"} <= set(pendant["redaction_en_cours"])
    job = _attendre(client, h, pid, r.json()["tache"]["id"])
    assert job["status"] == "done" and {"sections", "echecs", "message"} <= set(job["result"])
    st = _etat(client, h, pid)
    s = next(x for x in st["sections"] if x["id"] == sec["id"])
    v = s["version_courante"]
    assert {"id", "numero", "origine_libelle", "cree_le", "texte", "sources", "faits", "coupe"} <= set(v)
    assert v["faits"] and all({"id", "fait", "type", "phrase", "message", "statut"} <= set(f) for f in v["faits"])
    assert st["export"]["ia_utilisee"] is True and st["export"]["mention_ia"] == "Préparé avec assistance IA"
    # « Je l'ai relu » sur un fait, puis « J'écris moi-même » (base_version_id), puis conflit.
    f0 = v["faits"][0]
    rf = client.post(f"/api/atelier/{pid}/sections/{s['id']}/faits/{f0['id']}", headers=h, json={"statut": "relu_par_vous"})
    assert rf.status_code == 200 and rf.json()["section"]["id"] == s["id"]
    s2 = _ecrire(client, h, pid, s, "Notre équipe intervient en site occupé. La durée est de 6 semaines.")
    assert s2["version_courante"]["numero"] == 2
    stale = client.put(f"/api/atelier/{pid}/sections/{s['id']}/texte", headers=h,
                       json={"texte": "Autre texte.", "base_version_id": v["id"]})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "texte_modifie_entre_temps"
    assert stale.json()["detail"]["message"]
    # Historique et retour à une version (base = version affichée).
    hist = client.get(f"/api/atelier/{pid}/sections/{s['id']}", headers=h).json()["versions"]
    assert [x["numero"] for x in hist] == [2, 1] and all("texte" not in x for x in hist)
    one = client.get(f"/api/atelier/{pid}/sections/{s['id']}/versions/{hist[1]['id']}", headers=h).json()
    assert "texte" in one and one["numero"] == 1
    rr = client.post(f"/api/atelier/{pid}/sections/{s['id']}/restaurer", headers=h,
                     json={"version_id": hist[1]["id"], "base_version_id": s2["version_courante"]["id"]})
    assert rr.status_code == 200 and rr.json()["version_courante"]["numero"] == 3
    # Valider la version affichée.
    rv = client.post(f"/api/atelier/{pid}/sections/{s['id']}/valider", headers=h,
                     json={"version_id": rr.json()["version_courante"]["id"]})
    assert rv.status_code == 200 and rv.json()["statut"] == "valide" and rv.json()["validation"]["le"]
    # Export : bloqué (parties vides, « À compléter ») → raisons et dérogations possibles, puis dérogation et fichier.
    st = _etat(client, h, pid)
    e = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "etat_hash": st["blocage"]["etat_hash"]})
    assert e.status_code == 409
    det = e.json()["detail"]
    assert det["code"] == "export_bloque" and det["raisons"] and det["derogations_possibles"] and det["etat_hash"]
    for rz in det["raisons"]:
        assert {"code", "message"} <= set(rz)
        for x in rz.get("sections") or []:
            assert {"section_id", "titre"} <= set(x)
    der = client.post(f"/api/atelier/{pid}/derogation", headers=h,
                      json={"raison": "completerai_dans_word", "texte": "Je complète dans Word.", "etat_hash": det["etat_hash"]})
    assert der.status_code == 200 and der.json()["blocage"]["peut_exporter"] is True
    assert {"raison_libelle", "texte", "le", "avertissement"} <= set(der.json()["derogation"])
    ok = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "etat_hash": det["etat_hash"]})
    assert ok.status_code == 200 and "filename*=UTF-8''" in ok.headers["content-disposition"]
    assert _etat(client, h, pid)["dossier"]["dernier_export"]["format"] == "docx"
    # Options de l'export (cases « Page de garde », « Sommaire »).
    o = client.put(f"/api/atelier/{pid}/options", headers=h, json={"sommaire": False})
    assert o.status_code == 200 and o.json()["options"] == {"page_garde": True, "sommaire": False}


def test_parcours_plan_et_carte_du_savoir_faire(client, auth):
    h = auth["headers"]
    pid = _projet(client, h, with_dce=False, name="Entretien des espaces verts")
    st = _creer(client, h, pid)
    assert st["dossier"]["plan_source"] == "libre"
    # Ajouter, renommer, déplacer, retirer, remettre (plan simple) ; reconstruire avec confirmation.
    a = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Annexes"})
    assert a.status_code == 201 and a.json()["source_plan"] == "utilisateur"
    sid = a.json()["id"]
    assert client.patch(f"/api/atelier/{pid}/sections/{sid}", headers=h, json={"intitule": "Annexes techniques"}).status_code == 200
    assert client.patch(f"/api/atelier/{pid}/sections/{sid}", headers=h, json={"position": 0}).json()["ordre"] == 0
    assert client.delete(f"/api/atelier/{pid}/sections/{sid}", headers=h).json()["retiree"] is True
    st = _etat(client, h, pid)
    assert [x["id"] for x in st["sections_retirees"]] == [sid]
    assert {"id", "intitule", "nb_versions"} <= set(st["sections_retirees"][0])
    assert client.post(f"/api/atelier/{pid}/sections/{sid}/remettre", headers=h).json()["id"] == sid
    _ecrire(client, h, pid, st["sections"][0], "Un texte.")
    c = client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "libre", "remplacer": False})
    assert c.status_code == 409 and c.json()["detail"]["code"] == "plan_remplacement_a_confirmer"
    assert client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "libre", "remplacer": True}).status_code == 200
    # « Mon savoir-faire » : l'ancienne rédaction répond 410 et renvoie au marché.
    g = client.post("/api/knowledge/memoire-upload", headers=h)
    assert g.status_code == 410 and "marché" in json.dumps(g.json(), ensure_ascii=False)


# ═══ 4. Relecture croisée de la vague 2 (écrans) ═════════════════════════════════════════

def test_seule_l_occurrence_du_fait_dans_sa_phrase_est_surlignee_sous_node():
    md = ("Nous disposons de 12 salariés. Le CCTP prévoit 12 mois de travaux.\n\n"
          "| Poste | Effectif |\n| --- | --- |\n| Chefs d'équipe | 12 |\n| Compagnons couvreurs | 15 |")
    faits = [{"id": "f1", "fait": "12", "phrase": "Nous disposons de 12 salariés.", "statut": "a_relire"},
             {"id": "f2", "fait": "15", "phrase": "Compagnons couvreurs ; 15", "statut": "a_relire"},
             {"id": "f3", "fait": "12", "phrase": "Chefs d'équipe ; 12", "statut": "a_relire"}]
    r = _node(f"const md = {json.dumps(md)}, faits = {json.dumps(faits)};\n"
              "console.log(JSON.stringify({h: atlMdToHtml(md, faits),"
              " p: atlFaitPos(md, '15', 'Compagnons couvreurs ; 15'), q: atlFaitPos(md, '12', 'Chefs d\\'équipe ; 12'),"
              " m: atlFaitPos('M. Paul Durand pilotera. Paul Durand signe.', 'Paul Durand', 'M. Paul Durand pilotera.')}));")
    h = r["h"]
    assert h.count('<mark class="atl-fait"') == 3
    assert 'de <mark class="atl-fait" data-fait="f1">12</mark> salariés' in h
    assert "prévoit 12 mois" in h                                   # la phrase du CCTP n'est pas surlignée
    assert '<td><mark class="atl-fait" data-fait="f3">12</mark></td>' in h
    assert '<td><mark class="atl-fait" data-fait="f2">15</mark></td>' in h
    assert "" not in h and "" not in h and "" not in h
    assert md[r["p"][0]:r["p"][1]] == "15" and md[r["q"][0]:r["q"][1]] == "12"
    assert "Chefs d'équipe" in md[md.rfind("\n", 0, r["q"][0]):r["q"][0]]         # la bonne ligne du tableau
    assert r["m"] == [3, 14]                                          # « M. » ne coupe pas la phrase


def test_brouillons_locaux_effaces_a_la_deconnexion_et_apres_sept_jours_sous_node():
    r = _node("const store = {}; global.localStorage = { get length() { return Object.keys(store).length; },"
              " key(i) { return Object.keys(store)[i]; }, getItem(k) { return k in store ? store[k] : null; },"
              " setItem(k, v) { store[k] = String(v); }, removeItem(k) { delete store[k]; } };\n"
              "const now = Date.now();\n"
              "localStorage.setItem('adjugo_atl_1_2_3', JSON.stringify({t: 'récent', at: now}));\n"
              "localStorage.setItem('adjugo_atl_1_2_4', JSON.stringify({t: 'ancien', at: now - 8 * 24 * 3600 * 1000}));\n"
              "localStorage.setItem('adjugo_atl_1_2_5', 'pas du JSON');\n"
              "localStorage.setItem('adjugo_theme', 'dark');\n"
              "atlPurgeDrafts(false); const apres7j = Object.keys(store).sort();\n"
              "atlPurgeDrafts(true); const apresDeco = Object.keys(store).sort();\n"
              "console.log(JSON.stringify({apres7j, apresDeco, b: atlBasesDispo({cadre: false, grille: true}).map(x => [x.k, x.off])}));")
    assert r["apres7j"] == ["adjugo_atl_1_2_3", "adjugo_theme"]
    assert r["apresDeco"] == ["adjugo_theme"]
    assert r["b"] == [["auto", False], ["cadre", True], ["grille", False], ["libre", False]]
    # Déconnexion (y compris par inactivité) et suppression du compte effacent les brouillons.
    assert 'logout() { localStorage.removeItem("adjugo_token"); localStorage.removeItem("adjugo_active"); atlPurgeDrafts(true);' in JS
    assert 'localStorage.removeItem("adjugo_token"); atlPurgeDrafts(true); this.notify("Compte supprimé")' in JS
    assert "if (atlDraftPerime(d)) { this._atlDraftClear(s.id); return; }" in JS_METH


def test_etat_d_export_honnete_bases_poids_grille_et_dossier_absent_dans_les_gabarits():
    c = _sans_commentaires_html(CARTE)
    a = _sans_commentaires_html(ATELIER)
    f = _sans_commentaires_html(FENETRES)
    # Jamais « Prêt à exporter » quand l'export ne passe que par une dérogation ou que des parties restent à valider.
    assert ":class=\"atlEtatExport(ao.atl.d).cls\"" in c and "{{ atlEtatExport(ao.atl.d).label }}" in c
    assert "'Prêt à exporter'" not in c and "Encore ouvert, exporté avec votre dérogation" in c
    for lib in ('"Export avec dérogation"', '" parties à valider"', '"Prêt à exporter"'):
        assert lib in JS_METH, lib
    # Bases disponibles seulement (les autres désactivées, avec leur raison), dans la proposition et la fenêtre.
    assert "atlBases(atl.prop.proposition.bases)" in a and ":disabled=\"atl.loading || b.off\"" in a
    assert "atlBases(atl.st && atl.st.dossier.plan.bases)" in f and ":disabled=\"b.off\"" in f
    # Poids lu par vous ≠ poids écrit dans le règlement.
    assert "atlPoidsTexte(atlSec())" in a and "(lu par vous)" in a and '"poids lu par vous : "' in JS_METH
    # « Comment vous serez noté » a changé : ajouter au plan, sans reconstruire.
    assert "atl.st.grille.message" in a and "Mettre le plan à jour" in a and "\"/plan/grille\"" in JS_METH
    # Dossier du marché absent : dit, avec le chemin vers l'import ; la bulle « Rédiger » suit.
    assert "atl.st.dossier_acheteur.message_absent" in a and "atlImporterDce()" in a and "atlImporterDce()" in c
    assert "Aucun dossier du marché importé : Adjugo rédige sans le règlement ni le cadre de réponse." in a
    # « Mon savoir-faire » vide : signalé, et confirmé avant la première analyse (fenêtre de l'application).
    assert "atl.st.savoir_faire.message" in a and "this._atlLignesSavoirFaire()" in JS_METH
    assert "_atlAvantLancer(title, ok, lines, go)" in JS_METH
    # Le reste des faits (au-delà de ce qui est détaillé) est compté.
    assert "atlFaitsReste(atlSec())" in a
