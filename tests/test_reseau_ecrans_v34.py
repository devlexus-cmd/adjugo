"""
Réseau de partenaires et dépôt — correctifs d'écran de la revue v34 (domaine A). Chaque test
ÉCHOUE sans la correction correspondante.

- profil sans rôle déclaré : la modale d'invitation ne bloque plus (liste vide = tous les rôles) ;
- « Chercher dans le registre SIRENE » depuis un marché : métier prérempli sans la vue Réseau ;
- tableau de bord : l'état vide « Aucun groupement » n'apparaît plus quand il y a des groupements
  déposés ou quand le serveur n'a pas répondu ; un marché en groupement n'est jamais « à repérer » ;
- un seul pourcentage : plus de « % réponse commune prête », de complétude en % ni de « prêt % » ;
- explications dans des bulles (i), pas en clair ;
- invitations reçues : seul le compte qui peut accepter voit « Accepter » / « Décliner » ;
- validation de l'identité : statut « en attente » expliqué, vue d'administration Valider / Refuser.
Aucun appel réseau : lecture des fichiers statiques et exécution locale sous Node.
"""
import re

from tests.test_reseau_ecrans import HTML, JS, PANEL, SECTION, _between, _method, _node


def _obj(*names, extra=""):
    return "const o = {\n" + "\n".join(_method(n) for n in names) + "\n};\n" + extra


_DOM = "globalThis.document = { activeElement: null, querySelector: () => null, body: { contains: () => false } };\n"


def test_invitation_profil_sans_role_declare_sous_node():
    script = _DOM + _obj("rnInviteOpen") + """
o.view = "reseau"; o.ao = { project: null }; o.$nextTick = () => {};
const res = {};
o.rnInviteOpen({ profile_id: "a".repeat(32), name: "X", roles_acceptes: [] });
res.vide = { noRole: o.rinv.noRole, roles: o.rinv.roles };
o.rnInviteOpen({ profile_id: "b".repeat(32), name: "Y", roles_acceptes: ["mandataire"] });
res.chef = { noRole: o.rinv.noRole };
o.rnInviteOpen({ profile_id: "c".repeat(32), name: "Z", roles_acceptes: ["sous_traitant"] });
res.st = { noRole: o.rinv.noRole, roles: o.rinv.roles };
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r["vide"] == {"noRole": False, "roles": ["cotraitant", "sous_traitant"]}
    assert r["chef"] == {"noRole": True}
    assert r["st"] == {"noRole": False, "roles": ["sous_traitant"]}


def test_chercher_dans_sirene_depuis_un_marche_sous_node():
    script = _obj("rnOptions", "rnDiscover") + """
o.reseau = { p: { d: null }, an: { f: { metier: "", departement: "" } } };
o.discover = {}; o.trades = [];
o.openDiscover = function () { this.discover.open = true; };
const res = {};
o.rnDiscover("electricite", "29", "Électricité");
res.libelle = { trade: o.discover.trade, dept: o.discover.dept };
o.discover = {}; o.trades = [{ key: "plomberie", label: "Plomberie" }];
o.rnDiscover("plomberie", "56");
res.trades = o.discover.trade;
o.discover = {}; o.trades = [];
o.rnDiscover("menuiserie", "35");
res.cle = o.discover.trade;
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r["libelle"] == {"trade": "Électricité", "dept": "29"}
    assert r["trades"] == "Plomberie" and r["cle"] == "menuiserie"
    assert 'rnDiscover(l.metier, l.departement, l.metier_label)' in PANEL


def test_tableau_de_bord_etat_vide_honnete_sous_node():
    script = _obj("grpDashHasAny", "grpDashItems", "grpDashState") + """
o.fmtDate = (d) => d; o.pl = (n, a, b) => (n > 1 ? b : a); o.consortiums = { consortiums: [] };
const res = {};
o.grpDash = { marches_accessibles_en_groupement: 0, groupements_en_cours: 0, deposes: 1, en_cours: [], accessibles: [] };
o.grpDashErr = ""; res.deposes = o.grpDashState();
o.grpDash = null; o.grpDashErr = "Erreur serveur"; res.erreur = o.grpDashState();
o.grpDash = null; o.grpDashErr = ""; res.chargement = o.grpDashState();
o.grpDash = { marches_accessibles_en_groupement: 0, groupements_en_cours: 0, deposes: 0, en_cours: [], accessibles: [] };
res.vide = o.grpDashState();
const ec = [1, 2, 3, 4, 5, 6].map(i => ({ project_id: i, name: "M" + i, etape: 2, label: "Partenaires invités" }));
o.grpDash = { marches_accessibles_en_groupement: 2, groupements_en_cours: 6, deposes: 0, en_cours: ec,
              accessibles: [{ project_id: 6, name: "M6" }, { project_id: 9, name: "M9" }] };
res.items = o.grpDashItems().map(x => [x.project_id, x.meta]);
res.liste = o.grpDashState();
console.log(JSON.stringify(res));
"""
    r = _node(script)
    assert r["deposes"] == "deposes" and r["erreur"] == "erreur" and r["chargement"] == "chargement"
    assert r["vide"] == "vide" and r["liste"] == "liste"
    ids = [i for i, _m in r["items"]]
    assert ids == [1, 2, 3, 4, 5, 9]                  # le 6e est en cours : jamais « Repérer le marché »
    dash = _between(HTML, "<!-- ESPACE RÉSEAU ADJUGO", "Calcul limité aux 100 marchés")
    assert "grpDashState()==='vide'" in dash and "grpDashState()==='erreur'" in dash
    assert "grpDashState()==='deposes'" in dash and "Données momentanément indisponibles." in dash
    assert re.search(r'<div v-else class="row wrap"[^>]*>\s*<i data-lucide="sparkles"', dash) is None
    assert "this.grpDash = null" not in JS


def test_un_seul_pourcentage_plus_de_preparation_en_pourcent():
    for motif in ("readiness.pct", "readiness_pct", "p.completeness", "réponse commune prête", "readinessColor"):
        assert motif not in HTML, motif
    assert "readinessColor" not in JS
    cockpit = _between(HTML, "<!-- Cockpit : état de préparation", "aoToggleCockpit()")
    assert "readiness.submitted }}/{{ ao.share.consortium.readiness.invited" in cockpit and "%" not in cockpit


def _in_tip(html, phrase):
    """Chaque occurrence de `phrase` est à l'intérieur d'une bulle (i) (span.tip-b non refermé)."""
    found = False
    for m in re.finditer(re.escape(phrase), html):
        found = True
        before = html[:m.start()]
        i = before.rfind('<span class="tip-b" role="tooltip">')
        if i < 0 or "</span>" in before[i:]:
            return False
    return found


def test_explications_dans_des_bulles():
    assert "Cliquez sur « Qui me complète ? »" not in HTML
    assert _in_tip(HTML, "Renseignez ce que vous proposez, vérifiez votre entreprise, puis")
    assert _in_tip(HTML, "Votre historique se remplit quand vous invitez des partenaires")


def test_invitations_recues_reservees_a_qui_peut_accepter():
    recues = _between(SECTION, "<!-- ── Invitations reçues par le réseau", "</template>\n        </section>")
    assert "inv.statut!=='acceptee' && inv.peut_accepter!==false\" type=\"button\" class=\"btn sm primary\" @click=\"rnAccept(inv)\"" in recues
    assert "inv.peut_accepter!==false\" type=\"button\" class=\"btn sm ghost\" @click=\"rnDecline(inv)\"" in recues
    assert "{{ inv.aide }}" in recues
    accept = _between(JS, "    async rnAccept(inv) {", "    async rnOpenRecue(inv)")
    assert "inv.peut_accepter === false" in accept


def test_profil_en_attente_de_validation_explique_sous_node():
    prof = _between(SECTION, "<!-- ── Mon profil partenaire ── -->", "<!-- ── Annuaire ── -->")
    assert "En attente de validation par Adjugo" in prof
    assert _in_tip(prof, "{{ d.validation.explication }}")
    assert "rnCancelDemande()" in prof and "rnPubLabel(d)" in prof
    assert "{{ d.validation.motif }}" in prof
    assert "Vu par {{ d.apparitions_ce_mois }}" in prof          # entreprises distinctes, pas des recherches
    script = _obj("rnStatutPill", "rnPubLabel") + """
console.log(JSON.stringify({ att: o.rnStatutPill("en_attente"), ref: o.rnStatutPill("refuse"),
  dem: o.rnPubLabel({ validation: { identite_validee: false } }), rep: o.rnPubLabel({ validation: { identite_validee: true } }) }));
"""
    r = _node(script)
    assert r == {"att": "a_etudier", "ref": "no_go", "dem": "Demander la publication", "rep": "Publier mon profil"}


def test_administration_valider_ou_refuser_sous_node():
    adm = _between(HTML, "<section v-if=\"view==='admin'\">", "<!-- Mes groupements — hub central")
    for s in ("Profils du réseau à valider", "adminRvValider(it)", "adminRvRefuser(it)", "{{ it.compte.email }}",
              "{{ it.sirene.nom || 'nom non trouvé' }}", "Motif du refus", "admin.rv.remplacer[it.profile_id]"):
        assert s in adm, s
    assert "v-html" not in adm and "innerHTML" not in adm
    assert '"/api/admin/reseau/validations"' in JS and "/valider\"" in JS and "/refuser\"" in JS
    script = _obj("adminRvLink") + """
console.log(JSON.stringify([
  o.adminRvLink({ sirene: { lien_annuaire: "https://annuaire-entreprises.data.gouv.fr/entreprise/552100554" } }),
  o.adminRvLink({ sirene: { lien_annuaire: "javascript:alert(1)" } }),
  o.adminRvLink({ sirene: { lien_annuaire: "https://annuaire-entreprises.data.gouv.fr/entreprise/552100554/x" } }) ]));
"""
    r = _node(script)
    assert r == ["https://annuaire-entreprises.data.gouv.fr/entreprise/552100554", "", ""]
