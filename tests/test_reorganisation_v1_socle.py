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
    "cadre": ["auth", "menu", "entete", "contenu", "carte-essai", "carte-suggestion-reseau", "bandeau-cookies"],
    "accueil": ["vue-dashboard", "accueil-premiers-pas", "accueil-ruban", "accueil-reseau", "accueil-amont",
                "accueil-grille", "accueil-flux", "accueil-rail", "accueil-bilan", "accueil-carnet"],
    "marche": ["vue-aodetail", "marche-entete", "marche-resultat", "marche-carnet", "marche-analyse",
               "marche-couverture", "marche-questions", "marche-grille", "marche-plusieurs", "plusieurs-manques",
               "plusieurs-simulation", "marche-qui-me-complete", "marche-convention", "convention-pret-a-deposer",
               "marche-prix", "marche-dossier-presentation", "marche-pieces", "pieces-documents-reponse",
               "pieces-a-fournir", "marche-client", "marche-partenaires", "marche-reseau", "marche-preparation",
               "marche-commande-groupement", "marche-inviter", "marche-inviter-formulaire", "marche-invitations",
               "marche-contributions", "marche-suivi-groupement", "marche-coffre-croise", "marche-offre-commune",
               "marche-journal-acces", "marche-devis-suivi", "marche-dossier-fichiers", "marche-actions"],
    "trouver": ["vue-sourcing", "trouver-recherche", "trouver-radar", "trouver-alertes", "trouver-carte",
                "trouver-analyse"],
    "vues": ["vue-amont", "vue-kb", "kb-fiches-proposees", "vue-atelier", "atelier-page-preparation-case",
             "atelier-page-preparation", "atelier-entretien", "atelier-onglets", "atelier-repartition",
             "vue-pipeline", "vue-cotraitants", "vue-contacts", "vue-documents", "vue-invoices", "vue-company",
             "vue-preuves", "vue-criteria", "vue-team", "vue-billing", "billing-offres", "vue-admin",
             "vue-consortiums", "vue-reseau", "reseau-onglets", "reseau-profil", "reseau-annuaire",
             "reseau-historique", "reseau-recues", "vue-shared", "vue-sharedao-attente", "vue-sharedao"],
    "partage": ["partage-entete", "partage-grille", "partage-pourquoi", "partage-convention", "partage-redaction",
                "partage-pieces", "partage-ma-part", "partage-tableau-prix", "partage-coffre-croise",
                "partage-journal"],
    "fenetres": ["tiroir-projet", "fenetre-siret", "fenetre-confirmation", "fenetre-fiche-partenaire",
                 "fenetre-invitation", "fenetre-formulaire", "fenetre-decouverte"],
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
    for n in ZONES["marche"][1:] + ["plusieurs-manques", "plusieurs-simulation", "convention-pret-a-deposer"]:
        assert zone(HTML, n) in page, n
    sharedao = zone(HTML, "vue-sharedao")
    for n in ZONES["partage"]:
        assert zone(HTML, n) in sharedao, n
    for n in ("trouver-recherche", "trouver-radar", "trouver-alertes", "trouver-carte", "trouver-analyse"):
        assert zone(HTML, n) in zone(HTML, "vue-sourcing"), n
    for n in ("reseau-onglets", "reseau-profil", "reseau-annuaire", "reseau-historique", "reseau-recues"):
        assert zone(HTML, n) in zone(HTML, "vue-reseau"), n
    # Le menu est bien la barre latérale, le contenu contient toutes les vues.
    assert "go('dashboard')" in zone(HTML, "menu") and "<section" not in zone(HTML, "menu")
    contenu = zone(HTML, "contenu")
    assert all(zone(HTML, n) in contenu for n in noms(HTML) if n.startswith("vue-"))
    # Un repère ne change rien à ce qu'affiche la page : sans eux, le gabarit est celui d'avant.
    assert "data-test" not in sans_reperes(HTML)


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
    assert "keepalive: true" in mesure and ".catch(() => {})" in mesure
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
    assert '<a class="btn primary" href="/app?inscription" target="_blank" rel="noopener"><i data-lucide="sparkles"></i>Créer mon compte' in invite
    assert 'href="/app?inscription" target="_blank" rel="noopener" style="margin-top:16px"' in invite
    assert '<a href="/app?inscription" target="_blank" rel="noopener"><b>Commencez votre essai gratuit de 30 jours</b>' in invite
    # Les liens « Me connecter » de l'espace partenaire restent des liens de connexion.
    assert invite.count('href="/app" target="_blank" rel="noopener"') == 2


def test_inscription_lue_par_l_application_sous_node():
    """Le bloc de app.js qui lit ?inscription, exécuté sous Node : non connecté → « Créons votre compte » ;
    connecté ou lien de réinitialisation → rien ne change ; le paramètre est retiré, les autres restent."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    i = JS.index("    try {\n      const _q = new URLSearchParams(location.search);")
    bloc = JS[i:JS.index("    } catch (e) {}\n", i) + len("    } catch (e) {}\n")]
    script = """
const cas = JSON.parse(process.argv[1]); const out = [];
for (const c of cas) {
  const u = new URL("https://adjugo.pro" + c.url); let remplace = null;
  const location = { search: u.search, pathname: u.pathname, hash: u.hash };
  const history = { replaceState: (a, b, x) => { remplace = x; } };
  const ctx = { token: c.token, auth: { mode: "login" } }; const _rst = c.rst || null;
  (function () { BLOC }).call(ctx);
  out.push([ctx.auth.mode, remplace]);
}
console.log(JSON.stringify(out));
""".replace("BLOC", bloc)
    cas = [{"url": "/app?inscription", "token": ""},
           {"url": "/app?inscription", "token": "jeton"},
           {"url": "/app?inscription&shared=abc#gcode=x", "token": ""},
           {"url": "/app?inscription&reset=r1", "token": "", "rst": "r1"},
           {"url": "/app", "token": ""}]
    r = subprocess.run([node, "-e", script, json.dumps(cas)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [["register", "/app"], ["login", "/app"],
                                    ["register", "/app?shared=abc#gcode=x"], ["login", "/app?reset=r1"],
                                    ["login", None]]
