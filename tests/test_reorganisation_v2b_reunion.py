"""
Réorganisation de l'interface — vague 2b, réunion des chantiers B1, B2, B3 et B4 (contrat : docs/REORGANISATION_V2B.md,
§ R).

Ce que la réunion ajoute ou vérifie entre les chantiers, et que les tests de chaque chantier ne voyaient pas :
1. Marché d'exemple (B2) × espace du partenaire (B3) : l'écran du partenaire de l'exemple a la barre de « Votre part
   dans [marché] », calculée par la même fonction (barrePartenaire) à partir de l'état que l'exemple décrit déjà.
2. Adresses (vague 2a) × exemple (B2) × aperçu (B3) × attente au rechargement (B1) : chaque écran a son adresse, le
   précédent et le suivant les reprennent, un rechargement les rouvre sans attente du serveur ni écran intermédiaire.
3. Premiers pas (B1) × aperçu (B3) × courriel (B4) : regarder ce que verra un partenaire n'est pas une invitation (la
   tâche « Seul ou à plusieurs » ne bouge pas) ; l'invitation envoyée la termine ; le courriel nomme le chef de file
   et le marché que montrent l'aperçu et l'écran du partenaire, sous le même titre « Votre part dans « … » ».
4. Prise en main (B1) × exemple (B2) : les entrées « Voir un exemple » mènent toutes à /app/exemple.
5. Une seule tête Alembic, écrans de la mesure, traductions, contrat.

Aucun appel réseau : fonctions de app.js exécutées sous Node, API locale et base SQLite des tests, courriels relevés.
"""
import json
import pathlib
import re
import uuid

from tests.test_convention_groupement import _invite, _project, _set_company
from tests.test_reorganisation_v2a_adresses_etapes import _naviguer, _node
from tests.test_reorganisation_v2b_courriel_invitation import courriels  # noqa: F401  (relevé des courriels)
from tests.test_reorganisation_v2b_courriel_invitation import _base, _visible
from tests.test_reorganisation_v2b_espace_partenaire import _fonction
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
EX = json.loads((STATIC / "exemple-marche.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "REORGANISATION_V2B.md").read_text(encoding="utf-8")


def _espaces(t):
    """Les espaces insécables du fichier de l'exemple (autour des guillemets) lus comme des espaces."""
    return t.replace("\u00a0", " ").replace("\u202f", " ")


def _methode(nom):
    m = re.search(r"\n    (?:async )?" + re.escape(nom) + r"\(([\w, ]*)\) \{ .*? \},\n", JS)
    assert m, nom
    return m.group(0).strip()


# ═══ 1. L'écran du partenaire de l'exemple a la barre de son espace réel ══════════════════════════════════════════

def test_l_ecran_du_partenaire_de_l_exemple_a_la_barre_de_votre_part():
    r = _node(_fonction(JS, "barrePartenaire") + "\n" + _fonction(JS, "barreExemple") + """
const ex = JSON.parse(process.argv[1]);
const vue = barreExemple(ex).map(s => [s.k, s.label, s.statut, s.courante]);
// Les mêmes règles que l'espace réel : un accord qui manque laisse « Donner mon accord » en cours.
const sansAccord = barreExemple(Object.assign({}, ex, { preparer: Object.assign({}, ex.preparer, { accords: 1 }) }))
  .map(s => [s.k, s.statut]);
console.log(JSON.stringify({ vue, sansAccord, vide: barreExemple(null).map(s => s.statut) }));
""", json.dumps(EX))
    # L'état que l'exemple décrit : part reçue (1 sur 1), accords des membres 2 sur 2, dépôt pas encore fait (« Avant
    # de déposer » : 3 contrôles sur 4) : le partenaire attend le dépôt du chef de file.
    pr = EX["preparer"]
    assert (pr["parts_recues"], pr["parts_attendues"], pr["accords"], pr["membres"]) == (1, 1, 2, 2)
    assert [c["ok"] for c in EX["deposer"]["controles"]].count(False) == 1
    assert r["vue"] == [["accepter", "Accepter", "Terminé", False], ["part", "Ma part", "Terminé", False],
                        ["accord", "Donner mon accord", "Terminé", False],
                        ["depose", "Déposé par le chef de file", "En cours", True]]
    assert r["sansAccord"] == [["accepter", "Terminé"], ["part", "Terminé"], ["accord", "En cours"], ["depose", "À faire"]]
    # Sans état (jamais affiché : la page exige un fichier complet, exempleValide), aucune part ni aucun accord comptés.
    assert r["vide"] == ["Terminé", "En cours", "À faire", "À faire"]
    # La page : la même liste en lecture que l'aperçu de B3 (aucun bouton), dans le bloc du partenaire, sous son titre
    # « Votre part dans « … » » ; la méthode ne lit que l'exemple.
    bloc = zone(HTML, "exemple-partenaire")
    ol = bloc[bloc.index('<ol class="mk-etapes pa-barre ex-barre"'):bloc.index("</ol>")]
    assert ":class=\"'pa-n'+exBarre(ex).length\" aria-label=\"Étapes de sa part\"" in ol
    assert '<li v-for="s in exBarre(ex)"' in ol and "<button" not in ol and "@click" not in ol
    assert bloc.index("ex.ecran_partenaire.titre") < bloc.index("exBarre(ex)") < bloc.index("Pourquoi vous dans ce groupement")
    assert _espaces(EX["ecran_partenaire"]["titre"]) == f"Votre part dans « {EX['marche']['nom']} »"
    m = _methode("exBarre")
    assert m == "exBarre(d) { return barreExemple(d); },"
    for x in ("this.api(", "fetch(", "openAo", "localStorage"):
        assert x not in _fonction(JS, "barreExemple") and x not in m
    assert ".ex .ex-ecran .ex-barre { margin:12px 0 4px; }" in CSS


# ═══ 2. Adresses : exemple, marché, aperçu ; précédent, suivant, rechargement ════════════════════════════════════

_APERCU = """
Object.assign(o, { apercu: { projectId: null, inviteId: null },
  apercuOuvrir(a) { this.apercu = { projectId: a.projectId, inviteId: a.inviteId || null }; this.view = "apercu";
    this.journal.push("apercu:" + a.projectId + "/" + (a.inviteId || "")); },
  apercuCharger() { this.journal.push("apercu-charge"); } });
"""


def test_exemple_marche_et_apercu_chacun_son_adresse_et_le_precedent_les_reprend():
    r = _naviguer(_APERCU + """
const res = {};
demarrer(); res.depart = etat(); res.attente = !!o._adresseAttente;
o.openAo(o.projects[0]); vider(); res.marche = etat();
o.apercuOuvrir({ projectId: 7, inviteId: 3 }); vider(); res.apercu = etat();
history.back(); res.b1 = etat(); history.back(); res.b2 = etat();
history.forward(); history.forward(); res.f2 = etat();
console.log(JSON.stringify(Object.assign(res, { journal: o.journal })));
""", depart="/app/exemple")
    assert r["depart"] == {"urls": ["/app/exemple"], "idx": 0, "view": "exemple", "n": 0} and r["attente"] is False
    assert r["marche"]["urls"] == ["/app/exemple", "/app/marches/7"]
    assert r["apercu"]["urls"] == ["/app/exemple", "/app/marches/7", "/app/marches/7/apercu-partenaire/3"]
    assert r["b1"]["view"] == "aodetail" and r["b1"]["idx"] == 1                     # l'aperçu → le marché
    assert r["b2"]["view"] == "exemple" and r["b2"]["idx"] == 0                      # le marché → l'exemple
    assert r["f2"]["view"] == "apercu" and r["f2"]["idx"] == 2 and r["f2"]["urls"] == r["apercu"]["urls"]
    assert "go:exemple" in r["journal"] and "apercu:7/3" in r["journal"]


def test_rechargement_de_l_exemple_et_de_l_apercu_sans_attente_ni_ecran_intermediaire():
    for depart, vue in (("/app/exemple", "exemple"), ("/app/marches/7/apercu-partenaire", "apercu"),
                        ("/app/marches/7/apercu-partenaire/3", "apercu")):
        r = _naviguer(_APERCU + """
demarrer();
console.log(JSON.stringify(Object.assign(etat(), { attente: !!o._adresseAttente, journal: o.journal, apercu: o.apercu })));
""", depart=depart)
        assert r["view"] == vue and r["urls"] == [depart] and r["attente"] is False, depart
        # Un seul écran ouvert : jamais l'accueil d'abord (B1, ecranPret posé dès que boot() a ouvert l'adresse).
        assert "go:dashboard" not in r["journal"], depart
    boot = JS[JS.index("    async boot() {"):JS.index("    // ══════════ Menu par rubriques (réorganisation, vague 1, 1.3 ; RUBRIQUES")]
    assert "this._ouvrirAdresse(_demande);\n" in boot and "if (!this._adresseAttente) this.ecranPret = true;" in boot


# ═══ 3. Premiers pas × aperçu × courriel ═════════════════════════════════════════════════════════════════════════

def _tache(client, h, k):
    pp = client.get("/api/prise-en-main", headers=h).json()["premiers_pas"]
    return next(t for t in pp["taches"] if t["k"] == k)


def test_apercu_n_est_pas_une_invitation_puis_le_courriel_dit_ce_que_montrent_les_ecrans(client, auth, courriels):  # noqa: F811
    h = auth["headers"]
    _set_company(auth["email"], name="Couverture Réunion")
    nom = f"Réfection de la toiture de la salle des fêtes {uuid.uuid4().hex[:4]}"
    pid = _project(client, h, name=nom, deadline_days=20)
    assert _tache(client, h, "plusieurs")["statut"] == "pas_commence"
    # Regarder ce que verra un partenaire pas encore invité (B3) : rien n'est créé, la tâche (B1) ne bouge pas.
    a = client.get(f"/api/projects/{pid}/apercu-partenaire?role=cotraitant&nom=Charpente%20R%C3%A9union", headers=h)
    assert a.status_code == 200, a.text
    assert client.get(f"/api/projects/{pid}/invites", headers=h).json() == []
    assert _tache(client, h, "plusieurs")["statut"] == "pas_commence"
    assert not courriels
    # L'invitation envoyée (B4) termine la tâche (B1).
    inv = _invite(client, h, pid, "Charpente Réunion", recipient="contact@charpente-reunion.example")
    assert inv["emailed"] is True and _tache(client, h, "plusieurs")["statut"] == "termine"
    (c,) = [x for x in courriels if x["to"] == "contact@charpente-reunion.example"]
    # Le courriel, l'aperçu de cette invitation et l'écran du partenaire disent le même chef de file, le même marché,
    # sous le même titre ; le lien du courriel ouvre cet écran.
    ap = client.get(f"/api/projects/{pid}/apercu-partenaire?invite_id={inv['id']}", headers=h).json()
    vue = client.get("/api/invite/" + inv["token"]).json()
    assert ap["vue"]["mandataire"] == vue["mandataire"] == "Couverture Réunion"
    assert ap["vue"]["project"]["name"] == vue["project"]["name"] == nom
    titre = f"Votre part dans « {nom} »"
    for x in (c["texte"], _visible(c["html"])):
        assert "Couverture Réunion" in x and nom in x and titre in x
    assert _base() + "/invite/" + inv["token"] in c["texte"]
    assert client.get("/invite/" + inv["token"]).status_code == 200
    # Le même titre sur les trois écrans du partenaire : invite.html, l'application (vue « sharedao ») et l'exemple.
    assert "Votre part dans « ${esc(p.name || \"Marché\")} »" in INV
    assert '<h2 class="pa-titre"><span>Votre part dans</span> « {{ sharedAo.project.name }} »</h2>' in zone(HTML, "partage-entete")
    assert _espaces(EX["ecran_partenaire"]["titre"]).startswith("Votre part dans « ")


# ═══ 4. « Voir un exemple » : toutes les entrées mènent à /app/exemple ═════════════════════════════════════════════

def test_toutes_les_entrees_voir_un_exemple_menent_a_l_exemple():
    boutons = re.findall(r'<button v-if="exempleEnLigne\(\)"[^>]*@click="([^"]+)"', HTML)
    boutons += re.findall(r'<div v-if="exempleEnLigne\(\)" class="pp-exemple"><button[^>]*@click="([^"]+)"', HTML)
    assert len(boutons) == 3 and set(boutons) == {"go('exemple')"}                   # premiers pas, états vides (B1)
    liens = re.findall(r'<a href="/app/exemple"[^>]*@click\.prevent="([^"]+)"', HTML)
    assert liens == ["go('exemple')"]                                               # « Répondre à plusieurs ? » (B2)
    r = _node(JS[JS.index("// ══════════ Une adresse par écran (réorganisation, vague 2a, A1) ══════════"):
                 JS.index("// ══════════ Réorganisation, vague 2a (chantier A3) ══════════")] + """
console.log(JSON.stringify({ e: etatDeAdresse("/app/exemple"), a: adresseDe({ view: "exemple" }) }));""")
    assert r == {"e": {"view": "exemple"}, "a": "/app/exemple"}
    assert "exempleEnLigne() { const e = etatDeAdresse(\"/app/exemple\"); return !!(e && e.view === \"exemple\"); }," in JS


# ═══ 5. Tête Alembic, écrans mesurés, traductions, contrat ═══════════════════════════════════════════════════════

def test_une_seule_tete_alembic_c5priseenmain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    sd = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert sd.get_heads() == ["c5priseenmain"]
    assert sd.get_revision("c5priseenmain").down_revision == "c4montantseul"        # seule migration de la vague (B1)


def test_ecrans_des_chantiers_mesures_et_nommes():
    from app.services.mesure_usage import ECRANS
    assert {"exemple", "apercu"} <= ECRANS
    t = JS[JS.index("      titles: {"):JS.index("      subtitles: {")]
    s = JS[JS.index("      subtitles: {"):JS.index("      // Marché d'exemple (vague 2b, B2) : le contenu du fichier statique")]
    assert 'sharedao: "Votre part"' in t and 'apercu: "Ce que verra votre partenaire"' in t
    assert 'exemple: "Marché d\'exemple"' in t
    assert 'sharedao: "Le marché d\'une autre entreprise, où vous apportez votre part"' in s
    assert 'apercu: "Son écran tel qu\'il le verra' in s and 'exemple: "Un marché inventé, en lecture seule' in s
    assert 'exemple: { d: null, err: "", chargement: false },' in JS                  # l'état de l'exemple (B2) gardé


def test_traductions_completes_apres_la_reunion():
    tete, corps = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)
    d = json.loads(corps[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    assert set(d["nl"]) == set(d["es"]) and len(d["nl"]) >= 774
    # Clé ajoutée par deux chantiers (B2 et B3) : une seule traduction, celle du reste du dictionnaire (« mandatario »).
    assert d["es"]["Chef de file :"] == "Mandatario:" and d["nl"]["Chef de file :"] == "Penvoerder:"
    for k in ("Étapes de sa part", "Accepter", "Ma part", "Donner mon accord", "Déposé par le chef de file",
              "Terminé", "En cours", "À faire"):
        assert k in d["nl"] and k in d["es"], k                                       # la barre de l'exemple


def test_contrat_de_la_vague_2b_reuni():
    for s in ("## B1. Prise en main", "## B2. Le marché d'exemple", "## B3. L'espace du partenaire",
              "## B4. Le courriel d'invitation", "## R. Réunion des chantiers"):
        assert DOC.count(s) == 1, s
    assert DOC.index("## B1.") < DOC.index("## B2.") < DOC.index("## B3.") < DOC.index("## B4.") < DOC.index("## R.")
    assert DOC.count("Contrat de la vague 2b.") == 1 and "Convention commune aux chantiers" in DOC
    r = DOC[DOC.index("## R. Réunion des chantiers"):]
    for x in ("barreExemple", "test_reorganisation_v2b_reunion.py", "c5priseenmain", "Mandatario:", "Postgres",
              "Navigateur réel"):
        assert x in r, x
