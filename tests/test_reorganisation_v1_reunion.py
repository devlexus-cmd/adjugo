"""
Réorganisation de l'interface — vague 1, RÉUNION des chantiers « menu et accueil » (1.3, 1.6 à 1.8) et « page du
marché et recherche » (1.4, 1.5) (contrat : docs/REORGANISATION_V1.md, § 4).

Ce que la réunion a corrigé, trouvé en parcourant l'application réunie dans un vrai navigateur :
- l'accueil « À plusieurs » comptait encore les groupements sur les 5 étapes de juin (« Monter le groupement »,
  « Étape 5 sur 5 ») alors que la page du marché n'a plus que Lire · Décider · Préparer · Déposer : un seul découpage ;
- décision 8 hors de la page du marché : « Compatibilité N/100 », « 1/1 part reçue », « N/M » des gabarits, « 100/100 »
  de l'espace partenaire ;
- l'espace partenaire montrait l'ancien menu (Tableau de bord, Entreprise, Équipe…) ;
- « SIRENE » sur les pages collectivités ; l'en-tête du marché sur téléphone (titre écrasé par le choix de l'étape).

Aucun appel réseau : lecture des fichiers statiques, fonctions exécutées sous Node, démonstration locale.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.test_reorganisation_v1_menu import _rubriques
from tests.test_reseau_ecrans import _method
from tests.textes_visibles import mots_bannis, textes_html
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _obj(*noms):
    return "const o = {\n" + "\n".join(_method(n) for n in noms) + "\n};\n"


# ═══ Accueil « À plusieurs » : un seul découpage, celui de la page du marché ═════════════════════════════════

_ACCUEIL = _obj("grpDashEtape", "grpDashEtapes", "grpDashItems") + "o.fmtDate = d => d; o.pl = (n, a, b) => n > 1 ? b : a;\n"


def test_accueil_a_plusieurs_compte_sur_la_barre_du_marche():
    dash = zone(HTML, "accueil-reseau")
    assert '<li v-for="e in grpDashEtapes()"' in dash and "grpDash.par_etape" not in dash
    assert 'v-if="grpDashHasAny() && grpDashEtapes().length"' in dash
    # Le compteur « accessibles en groupement » seulement quand il y en a (étude, § 5.3) : jamais « 0 marchés ».
    assert '<div v-if="grpDash && grpDash.marches_accessibles_en_groupement" class="dh-count">' in dash
    items = _method("grpDashItems")
    for ancien in ("Monter le groupement", "Repérer le marché", "sur 5", "Avec partenaires", '"/" +', "Appel d'offres"):
        assert ancien not in dash and ancien not in items, ancien
    r = _node(_ACCUEIL + """
o.consortiums = { consortiums: [{ project_id: 7, partners: 2, submitted: 1 }] };
o.grpDash = { par_etape: [{ n: 1, count: 0 }, { n: 2, count: 1 }, { n: 3, count: 0 }, { n: 4, count: 2 }, { n: 5, count: 1 }],
  en_cours: [{ project_id: 7, name: "Gymnase", etape: 3, label: "Parts attendues", deadline: "2026-12-20" },
             { project_id: 8, name: "École", etape: 5, label: "Prêt" }],
  accessibles: [{ project_id: 9, name: "Voirie", groupement_score: 87 }, { project_id: 10, name: "Salle" }] };
const out = { etapes: o.grpDashEtapes(), items: o.grpDashItems().map(x => [x.meta, x.badge]) };
o.grpDash = { par_etape: [{ n: 1, count: 2 }, { n: 5, count: 0 }] }; out.decider = o.grpDashEtapes();
o.grpDash = { par_etape: [{ n: 1, count: 0 }] }; out.vide = o.grpDashEtapes();
console.log(JSON.stringify(out));
""")
    assert r["etapes"] == [{"label": "Préparer", "count": 3}, {"label": "Déposer", "count": 1}]   # jamais un zéro
    assert r["items"] == [["Parts attendues · parts reçues 1 sur 2 · limite 2026-12-20", "Préparer"], ["Prêt", "Déposer"],
                          ["À décider", "À plusieurs 87 %"], ["À décider", "Bon potentiel en groupement"]]
    assert r["decider"] == [{"label": "Décider", "count": 2}] and r["vide"] == []
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in CSS[CSS.index(".dash-steps {"):][:200]


def test_accueil_a_plusieurs_sur_la_demonstration(client, vitrine):
    """Ce que voit la démo (pitch) : Kerhel, groupement validé, compté dans « Déposer », ses parts « 1 sur 1 »."""
    dash = client.get("/api/groupement/tableau-de-bord", headers=vitrine)
    cons = client.get("/api/consortiums", headers=vitrine)
    assert dash.status_code == 200 and cons.status_code == 200
    r = _node(_ACCUEIL + """
o.grpDash = JSON.parse(process.argv[1]); o.consortiums = JSON.parse(process.argv[2]);
console.log(JSON.stringify({ etapes: o.grpDashEtapes(), items: o.grpDashItems().map(x => [x.name, x.meta, x.badge]) }));
""", json.dumps(dash.json()), json.dumps(cons.json()))
    assert r["etapes"] == [{"label": "Déposer", "count": 1}]
    kerhel = [it for it in r["items"] if "Kerhel" in it[0]]
    assert len(kerhel) == 1 and "parts reçues 1 sur 1" in kerhel[0][1] and kerhel[0][2] == "Déposer"
    for _nom, meta, badge in r["items"]:
        assert not re.search(r"\d+\s*/\s*\d+ part", meta), meta                       # « N sur M » (décision 8)
        assert badge in ("Décider", "Préparer", "Déposer") or "%" in badge or badge == "Bon potentiel en groupement"


@pytest.fixture(scope="module")
def vitrine(client):
    """La démonstration remise à neuf (comme au démarrage du serveur), avant et après ce module."""
    from app.core.database import SessionLocal
    from app.services.demo_seed import ensure_demo

    def neuf():
        db = SessionLocal()
        try:
            ensure_demo(db, force=True)
        finally:
            db.close()
    neuf()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    yield {"Authorization": "Bearer " + r.json()["access_token"]}
    neuf()


# ═══ Décision 8 hors de la page du marché ════════════════════════════════════════════════════════════════════

def test_bulles_de_l_accueil_et_de_mes_marches_seul_et_a_plusieurs():
    r = _node(_obj("feedScoreTitle", "kanbanScoreTitle") + """
const cas = [{ match_score: 72 }, { match_score: 43, groupement_score: 100, go_decision: "go_groupement" }, {},
             { groupement_score: 80 }];
console.log(JSON.stringify(cas.map(p => [o.feedScoreTitle(p), o.kanbanScoreTitle(p)])));
""")
    assert r == [["Seul 72 %", "Seul 72 %"], ["Seul 43 % · À plusieurs 100 %", "Seul 43 % · À plusieurs 100 %"],
                 ["Pas encore analysé", ""], ["À plusieurs 80 %", "À plusieurs 80 %"]]
    tiroir = zone(HTML, "tiroir-projet")
    assert "{{ kanbanScoreTitle(drawer) }}" in tiroir and "/100" not in tiroir and "Compatibilité" not in tiroir


def test_n_sur_m_dans_l_application_et_l_espace_partenaire():
    assert not re.search(r"\}\}\s*/\s*\{\{", HTML), "« N sur M », jamais « N/M »"
    assert 'ok + " sur " + files.length + " ajouté(s)"' in JS and 'r.covered + " sur " + (r.count - errs)' in JS
    assert "{{ cs.submitted }} sur {{ cs.partners }}" in zone(HTML, "vue-consortiums")
    # Espace partenaire (lien) et dossier partagé (compte) : le score du groupement se dit « à plusieurs », en %.
    assert "/100" not in INV and not re.search(r"\$\{esc\(n\w\)\}/\$\{esc\(n\w\)\}", INV)
    assert "parts reçues ${esc(nS)} sur ${esc(nM)}" in INV and "${esc(nA)} sur ${esc(nS)}</span>" in INV
    assert ' %</span></div><div class="sg-lab">à plusieurs</div>' in INV
    assert '<div class="sg-lab">à plusieurs</div>' in zone(HTML, "partage-pourquoi")
    assert "score du groupement</div>" not in INV and "score du groupement</div>" not in HTML


# ═══ L'espace partenaire montre le menu de l'application réorganisée ═════════════════════════════════════════

def test_menu_verrouille_de_l_espace_partenaire_est_celui_de_l_application():
    rub = _rubriques()
    side = INV[INV.index('<aside class="side">'):INV.index("</aside>")]
    items = re.findall(r'<a class="nav-item" data-view="(\w+)"([^>]*)><i data-lucide="([\w-]+)"></i>([^<]+)</a>', side)
    menu = [(v, ic, lib) for v, _a, ic, lib in items if v not in ("monao", "amont")]
    assert menu[:6] == [(r["onglets"][0]["view"], r["ic"], r["label"]) for r in rub[:6]]
    assert menu[6:] == [("team", "users-round", "Collègues"), ("billing", "credit-card", "Abonnement")]
    assert '<div class="nav-group">Réglages</div>' in side
    permis = {v for v, attrs, _ic, _l in items if 'data-allowed="1"' in attrs}
    assert permis == {"monao", "sourcing", "amont"}
    for ancien in ("Tableau de bord", "Pilotage", "Gestion", "Configuration", ">Entreprise<", ">Équipe<",
                   "Devis &amp; factures", "layout-dashboard", "square-kanban", "briefcase", "brain-circuit"):
        assert ancien not in side, ancien
    # « Mon appel d'offres » devient « Le marché » (comme l'en-tête de la page du marché dans l'application).
    assert "Mon appel d'offres" not in INV and 'monao: ["Le marché",' in INV and 'nav("monao", "Le marché")' in INV
    assert "Trouvez des marchés publics" in INV and "pipeline, coffre-fort" not in INV


# ═══ Pages collectivités, en-tête du marché sur téléphone, derniers libellés ═════════════════════════════════

def test_pages_collectivites_sans_mot_banni():
    for f in ("acheteur.html", "acheteur-landing.html"):
        src = (STATIC / f).read_text(encoding="utf-8")
        fautes = [t.strip()[:80] for _l, t in textes_html(src) if mots_bannis(t)]
        assert not fautes, (f, fautes)
        assert "SIRENE" not in src
    land = (STATIC / "acheteur-landing.html").read_text(encoding="utf-8")
    assert "</i>Registre Insee</span>" in land and 'rel="noopener">Annuaire des entreprises</a>' in land


def test_en_tete_du_marche_sur_telephone():
    assert '<div class="row mk-entete" style="align-items:flex-start;gap:14px">' in zone(HTML, "marche-entete")
    i = CSS.index("@media (max-width:520px) {", CSS.index(".mk-etapes {"))
    bloc = CSS[i:CSS.index("\n}\n", i)]
    assert ".mk-entete { flex-wrap:wrap; row-gap:12px; }" in bloc
    assert ".mk-entete > .field { flex:1 1 100%; min-width:0 !important; }" in bloc


def test_derniers_libelles_sans_ancien_nom():
    assert "<i data-lucide=\"receipt\"></i><h3>Devis et factures liés</h3>" in zone(HTML, "marche-devis-suivi")
    for ancien in ("Appel d'offres introuvable", "Cet appel d'offres n'est plus accessible",
                   "Appel d'offres mis à la corbeille", "recherche d'appel d'offres"):
        assert ancien not in JS, ancien
    assert '"Marché introuvable"' in JS and '"Marché mis à la corbeille"' in JS


def test_traductions_des_libelles_de_la_reunion():
    tete, corps = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)
    d = json.loads(corps[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for lib in ("À décider", "Vos marchés à plusieurs, par étape", "Marché", "Devis et factures liés", "à plusieurs",
                "Lancez votre première recherche de marchés", "Décider", "Préparer", "Déposer"):
        assert d["nl"].get(lib) and d["es"].get(lib), lib
