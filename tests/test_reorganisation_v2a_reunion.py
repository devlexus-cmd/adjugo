"""
Réorganisation de l'interface — vague 2a, réunion des chantiers A1, A2 et A3 (contrat : docs/REORGANISATION_V2A.md,
section « Réunion »).

Ce que la réunion ajoute ou corrige entre les chantiers, et que les tests de chaque chantier ne voyaient pas :
1. Axe d'étapes (A1) × liste de Mes marchés (A2) : un marché où je suis partenaire, déposé, prend la clé « depose » ;
   la liste se groupe dans l'ordre de l'axe (« À venir » en tête).
2. Adresses (A1) × filtres de Mes marchés (A2) : chaque filtre a son adresse, le précédent du navigateur les reprend,
   l'ancienne adresse des invitations reçues et ?shared= sans dossier mènent au filtre « Où je suis partenaire ».
3. Gestes de Préparer (A1) × fenêtre d'invitation unique (A2) : inviter fait passer le marché « En préparation »,
   sur sa page comme depuis Mes partenaires ; jamais un marché « À venir » ni un marché déjà plus loin.
4. Adresses (A1) × Mon entreprise en 4 onglets (A3) : Ce que je cherche et Tarifs ont leur adresse.
5. « partie (lot n) » (A3) × liste de Mes marchés (A2) : les libellés de parties venus des données passent par
   partieLot à l'écran ; le message « Prêt à déposer » nomme l'écran « Mes documents ».
6. Une seule tête Alembic : b3mesureecrans → c4axeetapes → c4montantseul.

Aucun appel réseau : fonctions de app.js exécutées sous Node, base SQLite des tests.
"""
import json
import pathlib
import re

from tests.test_reorganisation_v2a_adresses_etapes import _ADRESSES, _AXE, _naviguer, _node, tranche
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _methode(nom):
    m = re.search(r"\n    (?:async )?" + re.escape(nom) + r"\([^)]*\) \{", JS)
    assert m, nom
    i = m.start() + 1
    j = re.search(r"\n    (?:async )?[A-Za-z_$][\w$]*\([^)]*\) \{|\n    // ", JS[i + 4:])
    return JS[i:i + 4 + j.start()].rstrip().rstrip(",")


# ═══ 1. Axe d'étapes × liste de Mes marchés ═══════════════════════════════════════════════════════════════════

def test_un_marche_ou_je_suis_partenaire_depose_prend_la_cle_de_l_axe():
    assert '"envoye"' not in tranche(JS, "const MM_FILTRES = [", "function listeMesMarches(")
    r = _node(tranche(JS, "const MM_FILTRES = [", "function listeMesMarches(") + _AXE + """
const ordre = AXE_ETAPES.map(e => e.k);
const g = listeMesMarches([{ id: 1, status: "suivi" }, { id: 2, status: "depose" }, { id: 3 }],
  [{ token: "a", groupement: { state: "depose" } }, { token: "b", groupement: { state: "convention" } }], [], "tous", ordre);
console.log(JSON.stringify(g.map(x => [x.k, x.pilotes.map(p => p.id), x.partenaires.map(s => s.token)])));
""")
    # « À venir » en tête (décision 11), puis l'ordre de l'axe ; le partenaire déposé rejoint « Déposé ».
    assert r == [["suivi", [1], []], ["nouveau", [3], []], ["en_cours", [], ["b"]], ["depose", [2], ["a"]]]


# ═══ 2. Adresses × filtres de Mes marchés ═════════════════════════════════════════════════════════════════════

def test_chaque_filtre_de_mes_marches_a_son_adresse_et_le_precedent_les_reprend():
    r = _naviguer("""
const res = {};
demarrer(); res.lien = Object.assign(etat(), { filtre: o.mmFiltre });
o.mmFiltrer("partenaire"); vider(); res.partenaire = Object.assign(etat(), { filtre: o.mmFiltre });
o.mmFiltrer("pilote"); vider(); res.pilote = Object.assign(etat(), { filtre: o.mmFiltre });
o.openAo(o.projects[0]); vider(); res.marche = etat();
history.back(); res.b1 = Object.assign(etat(), { filtre: o.mmFiltre });
history.back(); res.b2 = Object.assign(etat(), { filtre: o.mmFiltre });
history.back(); res.b3 = Object.assign(etat(), { filtre: o.mmFiltre });
o.go("dashboard"); vider(); o.go("shared"); vider(); res.ancienne = Object.assign(etat(), { filtre: o.mmFiltre });
console.log(JSON.stringify(res));
""", depart="/app/marches/a-plusieurs")
    # Lien profond sur un filtre : la liste s'ouvre filtrée, l'adresse reste, aucune entrée ajoutée.
    assert r["lien"] == {"urls": ["/app/marches/a-plusieurs"], "idx": 0, "view": "pipeline", "n": 0, "filtre": "plusieurs"}
    assert r["partenaire"]["urls"][-1] == "/app/marches/partenaire" and r["partenaire"]["n"] == 1
    assert r["pilote"]["urls"][-1] == "/app/marches/je-pilote"
    assert r["marche"]["urls"][-1] == "/app/marches/7"
    # Précédent : le marché, puis chaque filtre dans l'ordre inverse.
    assert (r["b1"]["view"], r["b1"]["filtre"]) == ("pipeline", "pilote")
    assert (r["b2"]["view"], r["b2"]["filtre"]) == ("pipeline", "partenaire")
    assert (r["b3"]["view"], r["b3"]["filtre"]) == ("pipeline", "plusieurs") and r["b3"]["idx"] == 0
    # go("shared") (anciens appels, retour d'un dossier partagé) : le filtre, à son adresse.
    assert r["ancienne"]["urls"][-1] == "/app/marches/partenaire" and r["ancienne"]["filtre"] == "partenaire"


def test_anciennes_adresses_et_liens_vers_le_filtre_ou_je_suis_partenaire():
    r = _node(_ADRESSES + """
console.log(JSON.stringify([etatDeAdresse("/app/partenaires/reseau/invitations"), etatDeAdresse("/app/marches/bilan"),
  etatDeAdresse("/app/entreprise/ce-que-je-cherche"), etatDeAdresse("/app/entreprise/tarifs"),
  adresseDe({ view: "reseau", reseau: "recues" }), adresseDe({ view: "shared" }), adresseDe({ view: "consortiums" })]));
""")
    assert r[0] == {"view": "pipeline", "filtre": "partenaire"}                 # l'onglet du Réseau d'avant (A1)
    assert r[1] == {"view": "bilan"}
    assert r[2] == {"view": "criteria"} and r[3] == {"view": "tarifs"}         # Mon entreprise en 4 onglets (A3)
    assert r[4] == "/app/partenaires/reseau"                                   # plus d'onglet « Invitations reçues »
    assert r[5] is None and r[6] is None                                       # des filtres, plus des vues
    # Démarrage : ?shared=<jeton> sans dossier trouvé ouvre le filtre (le jeton quitte l'adresse, A1).
    boot = JS[JS.index("    async boot() {"):JS.index("    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES")]
    assert '{ view: "pipeline", filtre: "partenaire" }' in boot
    # « À faire » : une invitation reçue s'ouvre là où elle se traite.
    assert 'cible: { view: "shared" }' in JS and 'cible: { view: "reseau", reseau: "recues" }' not in JS
    assert "openReseau(c.reseau)" not in _methode("aFaireOuvrir")


def test_l_adresse_suit_le_filtre_et_l_ouvre():
    assert "filtre: this.mmFiltre" in JS[JS.index("    adresseCourante() {"):JS.index("  watch: {")]
    a = _methode("_appliquerAdresse")
    assert 'if (v === "pipeline") {' in a and 'this.mmFiltrer(e.filtre || "tous");' in a


# ═══ 3. Gestes de Préparer × fenêtre d'invitation unique ══════════════════════════════════════════════════════

def test_inviter_fait_passer_en_preparation_sur_la_page_et_ailleurs():
    m = JS[JS.index("    async _marcheEnPreparation(pid) {"):JS.index("    aoTacheVoir(t) {")]
    r = _node(tranche(JS, "function statutApresDecision(", "function statutEnPreparation(") + """
const o = {
""" + m.rstrip().rstrip(",") + """,
  view: "cotraitants", ao: { project: null }, appels: [], stats: 0,
  projects: [{ id: 1, status: "nouveau" }, { id: 2, status: "decide" }, { id: 3, status: "suivi" }, { id: 4, status: "depose" }],
  async api(m, p, b) { this.appels.push([m, p, b && b.status]); return {}; },
  loadStats() { this.stats++; }, aoAvancer() { this.appels.push(["page"]); },
};
(async () => {
  for (const id of [1, 2, 3, 4, 99]) await o._marcheEnPreparation(id);
  o.view = "aodetail"; o.ao.project = { id: 3 }; await o._marcheEnPreparation(3);
  console.log(JSON.stringify({ appels: o.appels, statuts: o.projects.map(p => p.status), stats: o.stats }));
})();
""")
    # Depuis Mes partenaires : Repéré et Décidé passent « En préparation » ; « À venir » et « Déposé » ne bougent pas.
    assert r["appels"][:2] == [["PUT", "/api/projects/1", "en_cours"], ["PUT", "/api/projects/2", "en_cours"]]
    assert r["statuts"] == ["en_cours", "en_cours", "suivi", "depose"] and r["stats"] == 2
    # Sur la page du marché : le geste de la page (aoAvancer, qui garde la même règle).
    assert r["appels"][2:] == [["page"]]


# ═══ 5. « partie (lot n) » × liste de Mes marchés ; « Mes documents » dans « Prêt à déposer » ═══════════════

def test_les_libelles_de_parties_venus_des_donnees_passent_par_partie_lot():
    brut = re.findall(r"\{\{ [a-z]+\.lot(?:_libelle|_propose)? \}\}", HTML)
    assert not brut, brut
    cr = zone(HTML, "mes-marches-liste")
    assert "{{ partieLot(l.lot) }}" in cr and "Parties couvertes" in cr and "Lots couverts" not in cr
    assert "{{ partieLot(inv.lot_propose) }}" in zone(HTML, "mes-marches-invitations")
    r = _node(JS[JS.index("function partieLot("):JS.index("\n}\n", JS.index("function partieLot(")) + 3] + """
console.log(JSON.stringify([partieLot("Lot 1 — Désamiantage et retrait d'amiante (SS3)"), partieLot("Démolition"),
  partieLot("Lots 2 et 3 — Isolation")]));
""")
    assert r == ["Partie (lot 1) — Désamiantage et retrait d'amiante (SS3)", "Démolition", "Lots 2 et 3 — Isolation"]


def test_pret_a_deposer_nomme_l_ecran_mes_documents():
    src = (ROOT / "app/services/groupement_members.py").read_text(encoding="utf-8")
    assert "(coffre-fort)" not in src and src.count(", dans Mes documents, ") == 2


# ═══ 6. Une seule tête Alembic ══════════════════════════════════════════════════════════════════════════════════

def test_une_seule_tete_alembic_dans_l_ordre_des_chantiers():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    sd = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert sd.get_heads() == ["c4montantseul"]
    assert sd.get_revision("c4montantseul").down_revision == "c4axeetapes"
    assert sd.get_revision("c4axeetapes").down_revision == "b3mesureecrans"


def test_mesure_d_usage_compte_les_vues_nouvelles_des_chantiers():
    from app.services.mesure_usage import ECRANS
    assert {"bilan", "tarifs", "shared", "consortiums"} <= set(ECRANS)


def test_traductions_completes_apres_la_reunion():
    s = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)[1]
    d = json.loads(s[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    assert set(d["nl"]) == set(d["es"]) and len(d["nl"]) >= 632
    for cle in ("Je pilote", "Ce que je cherche", "Tarifs", "À faire", "Préparer à plusieurs", "Parties couvertes"):
        assert cle in d["nl"] and cle in d["es"], cle
