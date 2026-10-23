"""
Réorganisation de l'interface — vagues 0 et 1, SOCLE (contrat : docs/REORGANISATION_V1.md).

1.0 Repères de test stables : chaque zone de app.html porte un attribut data-test unique (tests/zones.py) ;
    aucun test ne découpe plus app.html entre deux commentaires.
1.1 Mesure d'usage (décision 17) : un compteur par écran et par jour, sans donnée personnelle, lu par
    l'administrateur seulement ; la démonstration ne compte pas.
1.2 L'essai mène à l'inscription : /app?inscription ouvre « Créons votre compte ».
Vague 0 « dire juste » : bandeau cookies, libellés (Envoyé → Déposé), mots bannis des textes visibles
(application, vitrine, espace partenaire, courriels), traductions néerlandaises et espagnoles (décision 16).

Aucun appel réseau ; IA, emails et réseau coupés (conftest).
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import uuid
from datetime import date, timedelta

import pytest

from tests.zones import noms, sans_reperes, zone, zones

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"


def _lire(nom: str) -> str:
    return (STATIC / nom).read_text(encoding="utf-8")


HTML, JS = _lire("app.html"), _lire("app.js")


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _set(email, **vals):
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        for k, v in vals.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


# ═══ 1.0 Repères de test stables ════════════════════════════════════════════════════════════════

# Le contrat (docs/REORGANISATION_V1.md, § 1.0) : chaque nom, une seule fois, sauf les familles.
ZONES = {
    "cadre": ["auth", "menu", "menu-reglages", "entete", "contenu", "onglets-rubrique", "carte-essai",
              "carte-suggestion-reseau", "bandeau-cookies"],
    "accueil": ["vue-dashboard", "accueil-ce-qui-a-change", "accueil-premiers-pas", "accueil-reseau", "accueil-amont",
                "accueil-grille", "accueil-flux", "accueil-rail", "accueil-bilan", "accueil-carnet"],
    # Page du marché en 4 étapes (vague 1, 1.5) : la barre, une section par étape, le pied de page ; « Prêt à
    # déposer » a quitté la carte de la convention (convention-pret-a-deposer → marche-pret-a-deposer). Vague 2a (A2) :
    # plus de formulaire d'invitation dans la page (la fenêtre unique), la liste à cocher entre dans « Prêt à déposer »
    # (marche-avant-depot retiré), « Qui me complète ? » en trois réservoirs puis la recherche dans la zone.
    "marche": ["vue-aodetail", "marche-entete", "marche-resultat", "marche-carnet", "marche-etapes", "marche-lire",
               "marche-decider", "marche-preparer", "marche-deposer", "marche-pied", "marche-analyse",
               "marche-couverture", "marche-questions", "marche-grille", "marche-plusieurs", "plusieurs-manques",
               "plusieurs-simulation", "marche-qui-me-complete", "marche-convention", "marche-pret-a-deposer",
               "marche-prix", "marche-dossier-presentation", "marche-pieces", "pieces-documents-reponse",
               "pieces-a-fournir", "marche-client", "marche-partenaires", "marche-reseau", "marche-preparation",
               "marche-commande-groupement", "marche-inviter", "marche-invitations",
               "marche-contributions", "marche-suivi-groupement", "marche-coffre-croise", "marche-offre-commune",
               "marche-journal-acces", "marche-devis-suivi", "marche-dossier-fichiers", "marche-actions",
               "marche-taches-plusieurs", "marche-export", "complete-reseau", "complete-mes-partenaires",
               "complete-zone", "complete-recherche"],
    "trouver": ["vue-sourcing", "trouver-recherche", "trouver-radar", "trouver-alertes", "trouver-carte",
                "trouver-analyse"],
    "vues": ["vue-amont", "vue-kb", "kb-fiches-proposees", "vue-atelier", "atelier-page-preparation-case",
             "atelier-page-preparation", "atelier-entretien", "atelier-onglets", "atelier-repartition",
             "vue-pipeline", "vue-cotraitants", "vue-contacts", "vue-documents", "vue-invoices", "vue-company",
              # vue-tarifs : l'onglet « Tarifs » de Mon entreprise (vague 2a, A3 ; docs/REORGANISATION_V2A.md).
              "vue-preuves", "vue-criteria", "vue-tarifs", "vue-team", "vue-compte", "vue-billing", "billing-offres",
              "vue-admin", "admin-mesure",
              "vue-reseau", "reseau-onglets", "reseau-profil", "reseau-annuaire", "reseau-historique",
              "vue-sharedao-attente", "vue-sharedao",
              # Mes marchés en liste filtrable et Bilan en onglet (vague 2a, A2) : vue-shared, vue-consortiums et
              # reseau-recues y fondent.
              "mes-marches-filtres", "mes-marches-invitations", "mes-marches-liste", "mes-marches-plusieurs",
              "mes-marches-partenaire", "vue-bilan", "bilan-gagne-perdu", "bilan-carnet"],
    "partage": ["partage-entete", "partage-grille", "partage-pourquoi", "partage-convention", "partage-redaction",
                "partage-pieces", "partage-ma-part", "partage-tableau-prix", "partage-coffre-croise",
                "partage-journal"],
    "fenetres": ["tiroir-projet", "fenetre-siret", "fenetre-confirmation", "fenetre-fiche-partenaire",
                 "fenetre-invitation", "fenetre-formulaire", "fenetre-decouverte", "ecran-confirmation-email",
                 "fenetre-avis"],
    # Vague 2a, A1 (docs/REORGANISATION_V2A.md) : barre basse sur téléphone, cloche « À faire / Activité », bloc
    # « À faire » de l'accueil, décision de l'étape Décider, carte « À venir » créée depuis une fin de contrat.
    "vague2a_a1": ["menu-bas", "fenetre-notifications", "accueil-a-faire", "marche-decision",
                   "trouver-preparer-a-venir"],
    # Relecture de la vague 2a (docs/REORGANISATION_V2A.md, § L) : la page d'une carte « À venir » (marché pas encore
    # publié), à la place du bandeau « Le dossier complet du marché est indispensable ».
    "vague2a_relecture": ["marche-pas-publie"],
    # Vague 2b, B1 (docs/REORGANISATION_V2B.md) : l'attente d'une adresse au rechargement (aucun écran avant qu'elle
    # soit résolue), à côté de `contenu`.
    "vague2b_b1": ["ecran-attente"],
    # Vague 2b, B2 (docs/REORGANISATION_V2B.md, section B2) : le marché d'exemple, page à part en lecture seule
    # (/app/exemple) : l'en-tête, la barre d'ancres, les 4 étapes et l'écran du partenaire.
    "vague2b_exemple": ["vue-exemple", "exemple-entete", "exemple-etapes", "exemple-lire", "exemple-decider",
                        "exemple-preparer", "exemple-deposer", "exemple-partenaire"],
    # Vague 2b, chantier B3 (docs/REORGANISATION_V2B.md) : la barre de « Votre part » (dossier partagé), le lien « Voir ce
    # que verra votre partenaire » de l'en-tête du marché et l'écran de l'aperçu (son choix, l'écran du partenaire en
    # lecture, ce qui est attendu de lui, l'offre commune, un lien qui ne s'ouvre plus).
    "vague2b_b3": ["partage-barre", "marche-apercu", "vue-apercu-partenaire", "apercu-choix", "apercu-sans-acces",
                   "apercu-ecran", "apercu-attendu", "apercu-offre"],
}
FAMILLES = {"fenetres-atelier": 5, "fenetres-preuves": 2}     # même nom sur plusieurs fenêtres sœurs


def test_chaque_zone_du_contrat_est_reperee_une_seule_fois():
    poses = noms(HTML)
    attendus = [n for groupe in ZONES.values() for n in groupe]
    assert len(attendus) == len(set(attendus))
    for n in attendus:
        assert poses.count(n) == 1, f"{n} : {poses.count(n)} repère(s)"
    for n, k in FAMILLES.items():
        assert poses.count(n) == k, n
    # Rien d'autre que le contrat : un nouveau repère s'ajoute au contrat ET ici.
    assert set(poses) == set(attendus) | set(FAMILLES)
    for n in set(poses):
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", n), n


def test_chaque_zone_se_decoupe_et_reste_a_sa_place():
    # Une vue = sa section ; les cartes du marché vivent dans la page du marché, etc.
    for n in [x for x in noms(HTML) if x.startswith("vue-")]:
        assert zone(HTML, n).startswith(f'<section data-test="{n}"'), n
    page = zone(HTML, "vue-aodetail")
    for n in ZONES["marche"][1:]:
        assert zone(HTML, n) in page, n
    sharedao = zone(HTML, "vue-sharedao")
    for n in ZONES["partage"]:
        assert zone(HTML, n) in sharedao, n
    for n in ("trouver-recherche", "trouver-radar", "trouver-alertes", "trouver-carte", "trouver-analyse"):
        assert zone(HTML, n) in zone(HTML, "vue-sourcing"), n
    for n in ("reseau-onglets", "reseau-profil", "reseau-annuaire", "reseau-historique"):
        assert zone(HTML, n) in zone(HTML, "vue-reseau"), n
    for n in ("mes-marches-filtres", "mes-marches-invitations", "mes-marches-liste", "mes-marches-plusieurs",
              "mes-marches-partenaire"):
        assert zone(HTML, n) in zone(HTML, "vue-pipeline"), n
    for n in ("bilan-gagne-perdu", "bilan-carnet"):
        assert zone(HTML, n) in zone(HTML, "vue-bilan"), n
    for n in ("complete-reseau", "complete-mes-partenaires", "complete-zone", "complete-recherche"):
        assert zone(HTML, n) in zone(HTML, "marche-qui-me-complete"), n
    # Le menu est bien la barre latérale, le contenu contient toutes les vues.
    assert "go('dashboard')" in zone(HTML, "menu") and "<section" not in zone(HTML, "menu")
    assert zone(HTML, "menu-reglages") in zone(HTML, "menu")
    # Les onglets de rubrique (menu par rubriques, vague 1, 1.3) sont au-dessus des vues, hors de toute vue.
    assert zone(HTML, "onglets-rubrique") in contenu_avant_vues(HTML)
    contenu = zone(HTML, "contenu")
    assert all(zone(HTML, n) in contenu for n in noms(HTML) if n.startswith("vue-"))
    # Un repère ne change rien à ce qu'affiche la page : sans eux, le gabarit est celui d'avant.
    assert "data-test" not in sans_reperes(HTML)


def contenu_avant_vues(html):
    """Le début de la zone « contenu », avant la première vue."""
    c = zone(html, "contenu")
    return c[:c.index('<section data-test="vue-')]


def test_aucun_test_ne_decoupe_plus_app_html_entre_deux_commentaires():
    """La réorganisation déplace des blocs : un découpage entre deux commentaires (ou entre un commentaire et
    un libellé) de app.html casserait en silence. On passe par tests/zones.py."""
    motif = re.compile(r"""(?:_between\(\s*(?:HTML|html|app_html|app|SECTION|MODALS)\s*,|"""
                       r"""(?:HTML|html|app_html)\s*\.index\()\s*['"]<!--""")
    fautifs = []
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        for i, ligne in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if motif.search(ligne):
                fautifs.append(f"{p.name}:{i}")
    assert not fautifs, fautifs


def test_aide_zone_balises_imbriquees_et_commentaires():
    src = ('<div data-test="a"><div>1<!-- <div> --></div><section data-test="b"><div></div></section>'
           '</div><div data-test="c"></div><div data-test="c">x</div>')
    assert zone(src, "a").endswith("</section></div>") and zone(src, "b") == '<section data-test="b"><div></div></section>'
    assert len(zones(src, "c")) == 2
    with pytest.raises(AssertionError):
        zone(src, "c")
    with pytest.raises(AssertionError):
        zone(src, "absent")


# ═══ 1.1 Mesure d'usage (décision 17) ═══════════════════════════════════════════════════════════

def _releve(client, h, **q):
    r = client.get("/api/admin/mesures/ecrans", headers=h, params=q)
    assert r.status_code == 200, r.text
    return r.json()


def _n(rel, ecran):
    return next(x["ouvertures"] for x in rel["par_ecran"] if x["ecran"] == ecran)


def test_mesure_compte_une_ouverture_sans_donnee_personnelle(client, auth):
    from app.models import MesureEcran
    h = auth["headers"]
    _set(auth["email"], is_admin=True)
    avant = _n(_releve(client, h), "consortiums")
    for _ in range(3):
        r = client.post("/api/mesure/ecran", json={"ecran": "consortiums"}, headers=h)
        assert r.status_code == 204 and r.content == b""
    rel = _releve(client, h)
    assert _n(rel, "consortiums") == avant + 3
    # Une ligne par (jour, écran) ; rien d'autre n'est gardé.
    assert {c.name for c in MesureEcran.__table__.columns} == {"jour", "ecran", "ouvertures"}
    db = _db()
    try:
        lignes = db.query(MesureEcran).filter(MesureEcran.ecran == "consortiums").all()
        assert len({ln.jour for ln in lignes}) == len(lignes)
    finally:
        db.close()
    # Chaque écran de la liste figure au relevé, même jamais ouvert (0) : c'est souvent ce qu'on cherche.
    from app.services.mesure_usage import ECRANS
    assert {x["ecran"] for x in rel["par_ecran"]} == set(ECRANS)
    assert "personnelle" in rel["explication"] and rel["jusqu_au"] >= rel["depuis"]
    assert auth["email"] not in json.dumps(rel)


def test_mesure_ecran_inconnu_ignore_et_appel_anonyme_refuse(client, auth):
    from app.models import MesureEcran
    h = auth["headers"]
    for e in ("inconnu", "../admin", "dashboard;drop", "x" * 40):
        assert client.post("/api/mesure/ecran", json={"ecran": e}, headers=h).status_code == 204
    assert client.post("/api/mesure/ecran", json={"ecran": "x" * 41}, headers=h).status_code == 422
    assert client.post("/api/mesure/ecran", json={"ecran": "dashboard"}).status_code == 401
    db = _db()
    try:
        assert not db.query(MesureEcran).filter(~MesureEcran.ecran.in_(
            __import__("app.services.mesure_usage", fromlist=["ECRANS"]).ECRANS)).count()
    finally:
        db.close()


def test_mesure_la_demo_ne_compte_pas(client, auth):
    from app.services.mesure_usage import compter  # noqa: F401
    _set(auth["email"], is_admin=True)
    avant = _n(_releve(client, auth["headers"]), "billing")
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    demo = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.post("/api/mesure/ecran", json={"ecran": "billing"}, headers=demo).status_code == 204
    assert _n(_releve(client, auth["headers"]), "billing") == avant
    # La démo ne lit pas non plus le relevé (administrateur de la plateforme seulement).
    assert client.get("/api/admin/mesures/ecrans", headers=demo).status_code == 403


def test_releve_reserve_a_l_administrateur_et_borne(client, auth):
    h = auth["headers"]
    assert client.get("/api/admin/mesures/ecrans", headers=h).status_code == 403
    assert client.get("/api/admin/mesures/ecrans").status_code == 401
    _set(auth["email"], is_admin=True)
    assert client.get("/api/admin/mesures/ecrans", headers=h, params={"jours": 0}).status_code == 422
    assert client.get("/api/admin/mesures/ecrans", headers=h, params={"jours": 401}).status_code == 422
    rel = _releve(client, h, jours=7)
    assert (date.fromisoformat(rel["jusqu_au"]) - date.fromisoformat(rel["depuis"])).days == 6


def test_releve_lisible_dans_l_administration():
    """Lisible par l'administrateur sans outil : une carte de la vue Administration (réservée à is_admin)."""
    carte = zone(HTML, "admin-mesure")
    assert carte in zone(HTML, "vue-admin") and "admin.mesure.data.par_ecran" in carte and 'class="tip"' in carte
    assert '"/api/admin/mesures/ecrans?jours=30"' in JS and "this.adminMesureLoad();" in JS
    assert "user.is_admin" in zone(HTML, "menu") and "go('admin')" in zone(HTML, "menu")


def test_releve_par_jour_heure_de_paris():
    from app.models import MesureEcran
    from app.services import mesure_usage as mu
    db = _db()
    try:
        j = date(2001, 5, 3)
        db.query(MesureEcran).filter(MesureEcran.jour.in_([j, j - timedelta(days=1)])).delete(synchronize_session=False)
        db.commit()
        assert mu.compter(db, "reseau", jour=j) and mu.compter(db, "reseau", jour=j)
        assert mu.compter(db, "kb", jour=j - timedelta(days=1))
        assert not mu.compter(db, "inconnu", jour=j)
        rel = mu.releve(db, jours=2, fin=j)
        assert rel["jours"] == [{"jour": "2001-05-02", "ecrans": {"kb": 1}, "total": 1},
                                {"jour": "2001-05-03", "ecrans": {"reseau": 2}, "total": 2}]
        assert rel["total"] == 3 and rel["par_ecran"][0] == {"ecran": "reseau", "ouvertures": 2}
    finally:
        db.close()
    assert mu.PARIS.key == "Europe/Paris"


def test_chaque_vue_de_l_application_est_mesuree():
    from app.services.mesure_usage import ECRANS
    vues = set(re.findall(r"view===?'([a-z]+)'", HTML)) | set(re.findall(r'this\.view = "([a-z]+)"', JS))
    assert vues - {"agent", "veille"} <= ECRANS, sorted(vues - ECRANS)
    go = JS[JS.index("    go(v) {"):JS.index("    _ecranOuvert(v) {")]
    assert "this.view = v;\n      this._ecranOuvert(v);" in go
    # Les ouvertures hors de go() (un marché, un dossier partagé, l'atelier, les retours) comptent aussi.
    for site in ('this.view = "aodetail"; this._ecranOuvert("aodetail"); this.loadTrades();',
                 'this.view = "sharedao"; this._ecranOuvert("sharedao");',
                 'this.view = "atelier"; this._ecranOuvert("atelier");',
                 'this.view = this.ao.back || "pipeline"; this._ecranOuvert(this.view);',
                 'this.view = "aodetail"; this._ecranOuvert("aodetail"); this.atlCardLoad();'):
        assert site in JS, site
    mesure = JS[JS.index("    _ecranOuvert(v) {"):JS.index("    async loadAdmin() {")]
    # Interne, sans attente ni barre de progression ni message ; aucun outil tiers.
    assert '"/api/mesure/ecran"' in mesure and "this.api(" not in mesure and "notify" not in mesure
    assert ".catch(() => {})" in mesure and "await" not in mesure
    assert "http" not in mesure


def test_migration_mesure_ecrans_aller_retour_idempotente(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "mesure.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def tables():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            insp = sa.inspect(eng)
            t = set(insp.get_table_names())
            pk = insp.get_pk_constraint("mesure_ecrans")["constrained_columns"] if "mesure_ecrans" in t else []
            return t, pk
        finally:
            eng.dispose()

    run("upgrade", "head")
    t, pk = tables()
    assert "mesure_ecrans" in t and set(pk) == {"jour", "ecran"}
    run("downgrade", "a2carnetnotes")
    assert "mesure_ecrans" not in tables()[0] and "projects" in tables()[0]
    run("upgrade", "head")
    run("stamp", "a2carnetnotes")
    run("upgrade", "head")                                   # rejeu : idempotent
    assert "mesure_ecrans" in tables()[0]


# ═══ 1.2 L'essai mène à l'inscription ═══════════════════════════════════════════════════════════

def test_boutons_d_essai_vers_l_inscription():
    landing, invite = _lire("landing.html"), _lire("invite.html")
    essais = re.findall(r'<a [^>]*href="([^"]*)"[^>]*>Démarrer l’essai gratuit</a>', landing)
    assert len(essais) == 4 and set(essais) == {"/app?inscription"}
    assert landing.count('href="/app">Se connecter</a>') == 1           # « Se connecter » reste la connexion
    # Vague 2b (B3, décision 15 a) : le menu fermé à cadenas, le bouton de l'en-tête et la recherche de marchés de
    # l'espace partenaire ont laissé la place à UN SEUL encart « Créer mon compte », qui mène à l'inscription.
    assert invite.count('href="/app?inscription"') == 1
    assert '<a class="btn primary" href="/app?inscription" target="_blank" rel="noopener">${ico("user-plus", 15)}Créer mon compte</a>' in invite
    # Les liens « Me connecter » de l'espace partenaire restent des liens de connexion.
    assert invite.count('href="/app" target="_blank" rel="noopener"') == 2


def test_inscription_lue_par_l_application_sous_node():
    """inscriptionDemandee() (app.js), exécutée sous Node : le choix et l'adresse sans le paramètre ; puis le
    branchement dans mounted() : paramètre retiré tout de suite, formulaire choisi APRÈS la relecture de la session
    stockée (une session périmée est effacée, et l'on s'inscrit quand même — trouvé dans un vrai navigateur)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    i = JS.index("function inscriptionDemandee(loc) {")
    fn = JS[i:JS.index("\n}\n", i) + 3]
    script = fn + """
const cas = JSON.parse(process.argv[1]);
console.log(JSON.stringify(cas.map(u => { const x = new URL("https://adjugo.pro" + u);
  return inscriptionDemandee({ search: x.search, pathname: x.pathname, hash: x.hash }); })));
"""
    cas = ["/app?inscription", "/app?inscription&shared=abc#gcode=x", "/app?reset=r1&inscription", "/app", "/app?shared=a"]
    r = subprocess.run([node, "-e", script, json.dumps(cas)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [{"inscrire": True, "adresse": "/app"},
                                    {"inscrire": True, "adresse": "/app?shared=abc#gcode=x"},
                                    {"inscrire": True, "adresse": "/app?reset=r1"},
                                    {"inscrire": False, "adresse": None}, {"inscrire": False, "adresse": None}]
    a = JS.index("    const _ins = inscriptionDemandee(location);")
    b = JS.index("    if (_this_ins_) this.auth.mode = \"register\";".replace("_this_ins_", "_ins.inscrire && !this.token && !_rst"))
    c = JS.index("    else atlPurgeDrafts(false);")
    assert a < c < b, "le formulaire se choisit après la relecture de la session stockée"
    assert 'if (_ins.adresse !== null) { try { history.replaceState({}, "", _ins.adresse); } catch (e) {} }' in JS


# ═══ Vague 0 « dire juste » ═════════════════════════════════════════════════════════════════════

from tests.textes_visibles import messages_erreur, mots_bannis, textes_courriels, textes_html, textes_js  # noqa: E402

# Pages et scripts lus par un client (application, vitrine, espace partenaire, démonstration), et les pages de la face
# « collectivités » (acheteur*.html) depuis la réunion des chantiers de la vague 1 (contrat, § 4.3 : « SIRENE » y
# devient « registre Insee »).
FRONT_HTML = ("app.html", "invite.html", "landing.html", "demo.html", "demande-acces.html",
              "acheteur.html", "acheteur-landing.html")
FRONT_JS = ("app.js", "redaction-partenaire.js", "carnet-notes.js", "sources-publiques.js", "cotraitance-crypto.js")

# Exceptions assumées (texte exact → raison). Toute nouvelle exception se justifie ici ET au contrat.
EXCEPTIONS = {
    "Mémoire technique": "clé interne du dossier rangé (folderLabel l'affiche « Dossier de présentation »)",
    "DPGF du lot - prix de vente HT": "en-tête du fichier remis au chef de file puis à l'acheteur : son vocabulaire",
    "Indiquez le partenaire (cotraitant_id) ou le nom de l'entreprise (company).": "nom de champ de l'API",
    "Type de pièce inconnu (kbis, fiscale, sociale, assurance, rib, qualification, dpgf_lot, autre).": "clés de l'API",
    "Rôle invalide : cotraitant ou sous_traitant.": "valeurs de l'API",
    ".json, procédure dans docs/GO_LIVE.md).": "nom d'un fichier de procédure, courriel interne à l'administrateur",
}
# Fichiers hors règle : routeur archivé jamais monté (« Merged Brain », app/main.py).
PY_HORS = {"app/routers/cospace.py"}


def _fautes(items, nom):
    return [f"{nom}:{ln} {mots_bannis(t)} {t.strip()[:110]!r}" for ln, t in items
            if mots_bannis(t) and t.strip() not in EXCEPTIONS]


def test_aucun_mot_banni_dans_les_textes_visibles_du_front():
    fautes = []
    for f in FRONT_HTML:
        fautes += _fautes(textes_html(_lire(f)), f)
    for f in FRONT_JS:
        fautes += _fautes(textes_js(_lire(f)), f)
    assert not fautes, "\n".join(fautes)


def test_aucun_mot_banni_dans_les_courriels_ni_les_messages_d_erreur():
    fautes = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel in PY_HORS:
            continue
        src = p.read_text(encoding="utf-8")
        fautes += _fautes(textes_courriels(src), rel + " (courriel)")
        fautes += _fautes(messages_erreur(src), rel + " (message)")
    assert not fautes, "\n".join(fautes)


def test_les_courriels_cites_par_l_etude_disent_juste():
    inv = (ROOT / "app" / "routers" / "invites.py").read_text(encoding="utf-8")
    conv = (ROOT / "app" / "routers" / "convention.py").read_text(encoding="utf-8")
    al = (ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8")
    # Vague 2b (B4, docs/REORGANISATION_V2B.md) : le courriel d'invitation est composé par
    # app/services/email_invitation.py (HTML et texte) ; l'objet reste « Invitation à répondre ensemble à un marché — … ».
    from app.services.email_invitation import invitation
    assert invitation(chef="A", marche="Toiture", url="u")["objet"] == "Invitation à répondre ensemble à un marché — Toiture"
    assert "from app.services.email_invitation import invitation" in inv
    assert "Invitation à co-traiter" not in inv
    assert "Partenaires prêts : {done} sur {total}." in inv                     # « N sur M » (décision 8)
    for src in (inv, conv, al):
        assert "cockpit du groupement" not in src and "fiche du marché" not in src.lower()
    assert "disponible sur la page du marché, dans Adjugo" in conv


def test_le_serveur_dit_juste_dans_les_messages_montres(client, auth):
    """De bout en bout : un message d'erreur rendu à l'écran ne dit plus « co-traitant »."""
    r = client.delete("/api/cotraitants/999999", headers=auth["headers"])
    assert r.status_code == 404 and r.json()["detail"] == "Partenaire introuvable"


def test_bandeau_cookies_vers_la_page_de_confidentialite(client):
    b = zone(HTML, "bandeau-cookies")
    assert 'href="/confidentialite"' in b and 'rel="noopener"' in b and "/legal/" not in b
    r = client.get("/confidentialite")
    assert r.status_code == 200 and "onfidentialit" in r.text


def test_statut_envoye_s_affiche_depose_sans_toucher_a_la_cle():
    """Vague 0 : le libellé « Déposé ». Vague 2a (décision 7, docs/REORGANISATION_V2A.md, A1) : la clé « envoye » a
    migré vers « depose » ; le libellé vient de l'axe unique (AXE_ETAPES) ; un devis reste « Envoyé »."""
    i = JS.index("    statusLabel(s) {")
    status = JS[i:JS.index("\n", i)]
    assert "libelleStatut(s)" in status and "Envoyé" not in status
    assert '{ k: "depose", label: "Déposé" }' in JS and '"envoye"' not in JS[JS.index("const AXE_ETAPES"):JS.index("function libelleStatut(")]
    assert 'envoye: "Envoyé"' in JS                    # devis et factures : un devis s'envoie, il ne se dépose pas
    from app.models import InvoiceStatus, ProjectStatus
    assert ProjectStatus("envoye") is ProjectStatus.depose and "envoye" not in ProjectStatus.__members__
    assert InvoiceStatus("envoye").value == "envoye"                                    # devis : clé inchangée


def test_cartes_d_offre_et_vitrine_disent_juste():
    offres = zone(HTML, "billing-offres")
    assert "Formulaires officiels pré-remplis, à relire (DC1, DC2, DUME)" in offres
    for faux in ("CERFA", "rédaction IA sourcée", "partenaires vérifiés"):
        assert faux not in offres, faux
    landing = _lire("landing.html")
    assert "À plusieurs — votre différence" in landing and "Co-traitance" not in landing
    for faux in ("GO ou NO-GO", "co-traitant vérifié", "en un clic", "0 donnée jamais inventée", "(CERFA"):
        assert faux not in landing, faux


def test_espace_partenaire_dit_juste():
    inv = _lire("invite.html")
    assert "<title>Espace partenaire — Adjugo</title>" in inv
    # Vague 2b (B3, décision 15 a) : plus de menu (ni fermé à cadenas, ni « CRM ») ; l'espace se réduit à « Votre part
    # dans [marché] », vérifié en détail par test_reorganisation_v2b_espace_partenaire.py.
    assert 'class="nav-item"' not in inv and '<div class="nav-group">CRM</div>' not in inv
    assert '<b id="g-name">Partenaire</b><small id="g-role" style="display:block">Partenaire invité</small>' in inv
    assert '"Partenaire invité"' in inv and '"Invité · "' not in inv
    visibles = " ".join(t for _l, t in textes_html(inv))
    assert "Mon tableau de prix" in visibles and "Ma DPGF de lot" not in visibles and "DPGF" not in visibles.replace("DPGF du lot - prix de vente HT", "")
    # La durée de l'essai est celle du serveur (/api/public-config), jamais écrite dans la page.
    assert "Essai gratuit de ${esc(ESSAI_JOURS)} jours" in inv and "30 jours" not in inv and "compte gratuit" not in inv
    assert "Mon tableau de prix" in zone(HTML, "partage-tableau-prix")


def test_liste_des_pieces_sans_jargon_et_sans_doublon(client, auth):
    """« DPGF » ne s'affiche plus ; une pièce « DPGF » ou « Mémoire technique » lue dans le dossier du marché ne
    s'ajoute pas en double de « Tableau de prix » ou de « Dossier de présentation »."""
    from app.routers import checklist as ck
    noms_ = {p["id"]: p["name"] for p in ck.PIECES_STANDARD}
    assert noms_["dpgf"] == "Tableau de prix (bordereau ou décomposition des prix)"
    assert noms_["memoire_technique"] == "Dossier de présentation"
    for p in ck.PIECES_STANDARD:
        assert not mots_bannis(p["name"]) and not mots_bannis(p.get("help") or ""), p["id"]
    h = auth["headers"]
    r = client.post("/api/projects/", headers=h, json={"name": "Réfection de la toiture de la mairie"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    from app.models import Project
    db = _db()
    try:
        p = db.query(Project).filter(Project.id == pid).one()
        p.ai_analysis = {"details": {"pieces_requises": [{"nom": "DPGF"}, {"nom": "BPU"}, {"nom": "Mémoire technique"},
                                                         {"nom": "Planning de chantier détaillé"}]}}
        db.commit()
    finally:
        db.close()
    r = client.get(f"/api/checklist/{pid}", headers=h)
    assert r.status_code == 200, r.text
    corps = r.json()
    items = corps["checklist"]
    noms_vus = [i["name"] for i in items]
    assert "DPGF" not in noms_vus and "BPU" not in noms_vus and "Mémoire technique" not in noms_vus
    assert "Planning de chantier détaillé" in noms_vus
    assert all("alias" not in i for i in items)


def test_commentaire_de_l_inscription_a_jour():
    src = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    assert "n'empêche pas l'accès" not in src and "bannière « vérifiez votre adresse »" not in src
    assert "écran plein « Confirmez votre adresse email »" in src
    assert "Confirmez votre adresse email" in zone(HTML, "ecran-confirmation-email")


# Décision 16 : chaque libellé renommé (vague 0) et chaque libellé du menu ont leur néerlandais et leur espagnol.
RENOMMES = ["Déposé", "Pas encore déposé", "Supprimer ce marché", "Suivi du groupement", "Tableau de prix reçu",
            "Mon tableau de prix", "Préparer mon tableau de prix", "Marché lié (facultatif)", "Registre officiel",
            # « Entreprises du registre officiel » est devenu « Entreprises de la zone » (vague 2a, A2 : les réservoirs
            # de « Qui me complète ? », tests/test_reorganisation_v2a_marches_invitations.py).
            "Registre officiel des entreprises", "Chercher dans le registre officiel",
            "Chercher aussi dans le registre officiel", "Aucune activité récente de vos partenaires.",
            "Trouver des partenaires (avant la publication)", "Identité (pour vos formulaires officiels DC1, DC2)",
            "Formulaires officiels pré-remplis, à relire (DC1, DC2, DUME)", "Suivez vos marchés étape par étape",
            "Clients, partenaires, fournisseurs", "Trouvez des partenaires et faites-vous trouver",
            "Vos métiers, votre zone et vos montants : ce qu'Adjugo cherche pour vous"]


def _dico():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_traductions_des_libelles_renommes_et_du_menu():
    d = _dico()
    assert set(d) == {"nl", "es"} and set(d["nl"]) == set(d["es"])
    for k in RENOMMES:
        assert d["nl"].get(k) and d["es"].get(k), k
        assert k in HTML or k in JS, f"« {k} » n'est plus affiché : retirez-le de RENOMMES"
    # Chaque libellé du menu (texte d'une entrée) est traduit.
    menu = re.sub(r"<span[^>]*>.*?</span>", "", zone(HTML, "menu"), flags=re.S)
    # Menu par rubriques (vague 1, 1.3) : 6 rubriques, le titre du groupe « Réglages » et ses 5 entrées. Les onglets
    # de chaque rubrique (RUBRIQUES, app.js) sont vérifiés par tests/test_reorganisation_v1_menu.py.
    libelles = [x.strip() for x in re.findall(r'<(?:a|button) [^>]*class="nav-item[^"]*"[^>]*>(?:<i [^>]*></i>)?([^<{]+)', menu)]
    assert len(libelles) >= 12, libelles
    for k in libelles:
        k = k.replace("&amp;", "&")
        assert d["nl"].get(k) and d["es"].get(k), f"menu : « {k} » sans traduction (scripts/i18n_ajouter.py)"
    # Les libellés prévus par l'architecture C corrigée sont déjà traduits pour la suite de la vague 1.
    for k in ("Accueil", "Partenaires", "Réglages", "Réseau Adjugo", "Collègues", "Mon compte", "Où je suis partenaire",
              "Lire", "Décider", "Préparer", "Déposer", "Inviter un partenaire", "Qui me complète ?"):
        assert d["nl"].get(k) and d["es"].get(k), k
