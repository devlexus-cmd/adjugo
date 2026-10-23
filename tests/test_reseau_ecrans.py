"""
Co-traitance v2 — vague 3 : écrans du réseau de partenaires (garde-fous du front).

Vérifie, dans app.html / app.js / invite.html :
- la vue « Réseau » (Mon profil partenaire · Annuaire · Mon historique ; les invitations reçues sont dans Mes
  marchés depuis la vague 2a), le panneau « Qui me complète ? » et les modales existent ;
- aucun v-html / innerHTML sur ces écrans (noms, présentations, références = texte de tiers) ;
- aucun pourcentage, note ou étoile dans ces écrans (le seul % reste le score de groupement) ;
- zéro émoji, zéro jargon (« consortium », « pitch », « matching », « réciprocité ») ;
- la modale d'invitation n'affiche jamais d'adresse ; pas de « Copier le lien » pour une
  invitation du réseau ; relance possible (Adjugo renvoie l'invitation) ;
- l'aperçu minimal d'invite.html propose « Accepter depuis mon compte » ;
- la mise à jour du profil est PARTIELLE (seuls les champs modifiés partent au serveur) ;
- syntaxe JS valide (node --check) quand node est disponible.
Aucun appel réseau : lecture des fichiers statiques et exécution locale sous Node.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.zones import zone

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
INVITE = (STATIC / "invite.html").read_text(encoding="utf-8")


def _between(s, start, end):
    i = s.index(start)
    return s[i:s.index(end, i)]


def _no_html_comments(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _no_js_comments(s):
    return re.sub(r"(^|\s)//[^\n]*", r"\1", s)


# Zones repérées par leur attribut data-test (tests/zones.py, docs/REORGANISATION_V1.md) : elles
# restent justes quand la page est réordonnée ou qu'un libellé change.
SECTION = zone(HTML, "vue-reseau")
PANEL = zone(HTML, "marche-qui-me-complete")
MODALS = zone(HTML, "fenetre-fiche-partenaire") + "\n" + zone(HTML, "fenetre-invitation")
SUGGEST = zone(HTML, "carte-suggestion-reseau")
JS_METHODS = _between(JS, "// ══════════ Réseau de partenaires (co-traitance v2, vague 3) ══════════", "// ── Coffre-fort croisé")
JS_COMPONENTS = _between(JS, "// ── Réseau de partenaires (vague 3) : petits composants", "// window.__adjugo")
SCREENS = {k: _no_html_comments(v) for k, v in
           {"section": SECTION, "panneau": PANEL, "modales": MODALS, "suggestion": SUGGEST}.items()}
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆✅❌✔✖★☆]")


def test_vue_reseau_et_navigation():
    # Menu par rubriques (réorganisation, vague 1, 1.3) : « Réseau Adjugo » est un onglet de la rubrique Partenaires
    # (RUBRIQUES, app.js), ouvert par go('reseau') ; ses onglets internes restent jusqu'à la vague 2a.
    assert '{ view: "reseau", label: "Réseau Adjugo", ic: "network", ancien: "Réseau" }' in JS and "openReseau(" in HTML
    for libelle in ("Mon profil partenaire", "Annuaire", "Mon historique"):
        assert libelle in SECTION, libelle
    # Réorganisation, vague 2a (A2) : les invitations reçues se traitent dans Mes marchés (en tête de la liste).
    assert "Invitations reçues" not in _no_html_comments(SECTION)
    assert "Invitations à traiter" in zone(HTML, "mes-marches-invitations")
    # Réorganisation, vague 1 (1.5) : la carte s'appelle « Qui me complète ? » ; son bouton cherche.
    assert '<h3 id="pm-h">Qui me complète ?</h3>' in PANEL and "Chercher des partenaires" in PANEL
    assert "Partenaires pour ce marché" not in PANEL
    assert "Présentation en une phrase" in SECTION
    assert 'reseau: "Réseau Adjugo"' in JS


@pytest.mark.parametrize("name", list(SCREENS))
def test_aucun_html_brut_ni_pourcentage_ni_jargon(name):
    s = SCREENS[name]
    assert "v-html" not in s and "innerHTML" not in s
    assert "%" not in s, "un seul pourcentage dans l'app : le score de groupement (simulation)"
    low = s.lower()
    for mot in ("consortium", "pitch", "matching", "réciprocité", "étoile", "/5"):
        assert mot not in low, mot
    assert not EMOJI.search(s)
    # Vrais boutons : chaque <button> déclare son type ; les bulles (i) gardent le composant existant.
    for m in re.finditer(r"<button\b[^>]*>", s):
        assert 'type="button"' in m.group(0) or 'type="submit"' in m.group(0), m.group(0)[:120]
    assert s.count('class="tip-b" role="tooltip"') == s.count("tip-b")


def test_js_reseau_sans_html_brut_ni_pourcentage():
    for blk in (_no_js_comments(JS_METHODS), _no_js_comments(JS_COMPONENTS)):
        assert "innerHTML" not in blk and "v-html" not in blk
        assert "%" not in blk
        assert not EMOJI.search(blk)
    # Les composants n'affichent que ce que l'API renvoie : libellé, source, date — aucun calcul.
    assert "rn-badges" in JS_COMPONENTS and "rn-criteres" in JS_COMPONENTS and "rn-fiche" in JS_COMPONENTS
    assert "annuaire-entreprises\\.data\\.gouv\\.fr" in JS_COMPONENTS   # lien externe strictement contrôlé


def test_invitation_reseau_adresse_jamais_affichee():
    rinv = zone(HTML, "fenetre-invitation")
    assert "recipient" not in rinv
    # Réorganisation, vague 2a (A2) : la fenêtre unique a aussi le cas « partenaire connu », dont l'email est celui que
    # la PME saisit elle-même ; ce champ n'existe que dans ce cas, jamais pour une entreprise du réseau.
    connu = rinv[rinv.index('<template v-if="rinv.kind===\'connu\'">'):]
    connu = connu[:connu.index("</template>")]
    sans_connu = rinv.replace(connu, "")
    assert 'v-model="rinv.email"' in connu and "rinv.email" not in sans_connu and 'type="email"' not in sans_connu
    assert "vous verrez l'adresse du partenaire quand il aura accepté" in MODALS
    assert "deja_invite" in MODALS and "sur_le_reseau" in MODALS
    # Liste des invitations du marché : pas de lien à copier pour une invitation réseau, adresse masquée.
    assert '<button v-if="!inviteIsNetwork(inv)" class="btn icon sm ghost" @click="copyInvite(inviteUrl(inv))"' in HTML
    assert "Adresse visible quand le partenaire aura accepté" in HTML
    assert 'inviteRelancable(inv)' in HTML
    assert "inv.source === \"reseau_adjugo\"" in JS


def test_statut_a_decline_partout():
    assert "inviteDeclinedFor(c.name)" in PANEL                      # cartes réseau et SIRENE
    assert "inviteDeclinedFor(m.name)" in HTML                       # composition retenue
    assert "inviteDeclinedFor(c.name)" in zone(HTML, "plusieurs-manques")   # candidats (« Qui l'a ? »)
    assert "Vous avez décliné" in zone(HTML, "mes-marches-invitations")   # invitations reçues (Mes marchés, vague 2a)


def test_simulation_reseau_envoie_seulement_l_identifiant():
    assert 'if (m.kind === "reseau") return { kind: "reseau", profile_id: m.profile_id };' in JS
    assert '{ key: "reseau", label: "Réseau Adjugo", list: c.reseau || [] }' in JS


def test_apercu_minimal_et_suggestion_invite_html():
    assert "d.apercu_minimal" in INVITE and "Accepter depuis mon compte" in INVITE
    assert "tip(esc(d.apercu_message" in INVITE                     # message serveur échappé, en bulle (i)
    keep = _between(INVITE, "function keepSuggestion(res)", "// « Accepter depuis mon compte »")
    assert 'JSON.stringify({ code: s.code, titre: String(s.titre || ""), message: String(s.message || "") })' in keep
    assert 'sessionStorage.getItem("adjugo_suggest_profile")' in JS
    assert "_rnSuggest(res.suggest_profile)" in JS and "_rnSuggest(cr.suggest_profile)" in JS


# ── Exécution sous Node : mise à jour PARTIELLE du profil ────────────────────────────
def _method(name):
    m = (re.search(r"\n    " + re.escape(name) + r"\(([\w, ]*)\) \{\n.*?\n    \},\n", JS, re.S)
         or re.search(r"\n    " + re.escape(name) + r"\(([\w, ]*)\) \{ .*? \},\n", JS))
    assert m, f"méthode {name} introuvable"
    return m.group(0).strip()


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_profil_mise_a_jour_partielle_sous_node():
    names = ["rnOptions", "_rnSplit", "_rnRefKey", "_rnRefClean", "_rnForm", "rnRefOptions", "_rnAll", "_rnBody"]
    obj = "const o = {\n" + "\n".join(_method(n) for n in names) + "\n};\n"
    d = {"exists": True, "hidden_from_sirens": [], "options": {"presentation_max": 300, "references_max": 5},
         "declare": {"metiers": ["electricite", "plomberie"], "departements": ["29", "56"], "roles_acceptes": ["cotraitant"],
                     "disponibilite": "disponible", "dispo_jusqua": None, "lot_max_eur": 250000.0, "codes_cpv": [],
                     "presentation": "Électricité.", "references_publiques": [{"intitule": "École", "client": "Brest", "annee": 2025}]},
         "references_disponibles": [{"intitule": "École", "client": "Brest", "annee": 2025}, {"intitule": "Mairie", "client": "", "annee": None}]}
    script = obj + "const d = " + json.dumps(d) + ";\n" + """
o.reseau = { p: { d, f: null } };
const res = {};
o.reseau.p.f = o._rnForm(d); res.inchange = o._rnBody();
o.reseau.p.f.metiers = ["plomberie", "electricite"]; res.ordre = o._rnBody();
o.reseau.p.f.presentation = "Électricité générale. "; res.pres = o._rnBody();
o.reseau.p.f = o._rnForm(d); o.reseau.p.f.refs.push(o.rnRefOptions()[1]._k); res.refs = o._rnBody();
o.reseau.p.f = o._rnForm(d); o.reseau.p.f.lot_max_eur = ""; o.reseau.p.f.hidden = "732829320 ; 443061841"; res.vide = o._rnBody();
o.reseau.p.d = Object.assign({}, d, { exists: false }); o.reseau.p.f = o._rnForm(d); res.creation = Object.keys(o._rnBody()).sort();
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r["inchange"] == {}
    assert r["ordre"] == {}                                   # même ensemble de métiers : rien à envoyer
    assert r["pres"] == {"presentation": "Électricité générale."}
    assert r["refs"] == {"references_publiques": [{"intitule": "École", "client": "Brest", "annee": 2025},
                                                  {"intitule": "Mairie", "client": "", "annee": None}]}
    assert r["vide"] == {"lot_max_eur": None, "hidden_from_sirens": ["732829320", "443061841"]}
    assert r["creation"] == sorted(["metiers", "departements", "roles_acceptes", "disponibilite", "dispo_jusqua",
                                    "lot_max_eur", "codes_cpv", "presentation", "references_publiques", "hidden_from_sirens"])


def test_pluriel_francais_et_a_decline_sous_node():
    obj = "const o = {\n" + "\n".join(_method(n) for n in ["plFr", "ddmm", "inviteDeclined", "inviteDeclinedFor", "declinedLabel"]) + "\n};\n"
    script = obj + """
o.ao = { share: { invites: [
  { company_name: "LE GALL ELECTRICITE", revoked: false, declined_at: "2026-10-08T10:00:00", state: "declined" },
  { company_name: "Atelier Kerné", revoked: false, declined_at: "2026-10-01T10:00:00", state: "declined" },
  { company_name: "atelier kerné", revoked: false, declined_at: null, state: "sent" } ] } };
console.log(JSON.stringify({
  p0: o.plFr(0, "recherche", "recherches"), p1: o.plFr(1, "recherche", "recherches"), p2: o.plFr(2, "recherche", "recherches"),
  dec: o.declinedLabel(o.inviteDeclinedFor(" le gall electricite ")),
  reinvite: o.inviteDeclinedFor("Atelier Kerné"), inconnu: o.inviteDeclinedFor("Autre") }));
"""
    r = _node(script)
    assert (r["p0"], r["p1"], r["p2"]) == ("recherche", "recherche", "recherches")
    assert r["dec"] == "A décliné le 08/10"
    assert r["reinvite"] is None and r["inconnu"] is None       # invitée de nouveau → plus « a décliné »


def test_syntaxe_js_node_check(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    out = subprocess.run([node, "--check", str(STATIC / "app.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    for i, block in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", INVITE, re.S)):
        f = tmp_path / f"invite_{i}.js"
        f.write_text(block, encoding="utf-8")
        out = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
