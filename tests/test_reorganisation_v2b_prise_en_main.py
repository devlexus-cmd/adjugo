"""
Réorganisation de l'interface — vague 2b, chantier B1 « prise en main » (contrat : docs/REORGANISATION_V2B.md, B1 ;
étude « organisation du logiciel », § 7.1 à 7.4 et 7.7 ; décisions 12 (a), 13 (a) et 15 (a) retenues).

  1. « Vos premiers pas » sur l'accueil pendant 30 jours après la création du compte, état gardé SUR LE SERVEUR
     (migration c5priseenmain), repliable ; jamais pour la démonstration ;
  2. la liste d'activation : des tâches au verbe, trois statuts (Pas commencé · En cours · Terminé), chacune terminée
     selon une condition LUE dans les données (« Dire ce que vous faites et où » compte le montant porté seul OU « Je ne
     sais pas ») ; « Lancez votre première recherche » a disparu ; chaque tâche revient dans l'état vide de son écran ;
  3. les états vides du § 7.3 : l'état et un chemin direct ; « Voir un exemple » mène à /app/exemple, seulement quand
     cet écran est en ligne ; aucune promesse d'une fonction qui ne l'est pas ;
  4. la confirmation d'email vivante (décision 12 (a)) : revérification au retour sur l'onglet et à intervalle croissant
     tant qu'il est ouvert ; écran et courriel qui disent la suite ; la carte « Faites-vous trouver » gardée côté
     serveur ; le commentaire d'auth.py juste ; le serveur refuse toujours ce qu'il refusait ;
  5. au rechargement d'une adresse profonde, aucun écran avant qu'elle soit résolue.

Aucun réseau (courriels, IA, registres coupés) ; fonctions de app.js exécutées sous Node.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_reorganisation_v2a_entreprise import _methode
from tests.textes_visibles import mots_bannis, textes_html
from tests.zones import zone, zones

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
CONTRAT = (ROOT / "docs" / "REORGANISATION_V2B.md").read_text(encoding="utf-8")

_PP = JS[JS.index("// ══════════ Prise en main (réorganisation, vague 2b, B1"):
         JS.index("// Préparer › À plusieurs : les étapes 2 à 4 du groupement")]
_ADRESSES = JS[JS.index("// ══════════ Une adresse par écran (réorganisation, vague 2a, A1) ══════════"):
               JS.index("// ══════════ Réorganisation, vague 2a (chantier A3) ══════════")]
TACHES = ["dire", "suivre", "lire", "plusieurs", "dossiers"]
STATUTS = {"pas_commence", "en_cours", "termine"}
APRES = "Une fois confirmé, vous entrez votre SIRET et vous voyez les marchés de votre zone."


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _inscrire(client, verifie=True, nom="Couvreurs du Léon"):
    import uuid
    email = f"b1_{uuid.uuid4().hex[:10]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Anne Le Gall", "company_name": nom})
    assert r.status_code == 201, r.text
    if verifie:
        from app.models import User
        db = _db()
        try:
            db.query(User).filter(User.email == email).first().email_verified = True
            db.commit()
        finally:
            db.close()
    return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}, "email": email, "register": r.json()}


def _uid(email):
    from app.models import User
    db = _db()
    try:
        return db.query(User.id).filter(User.email == email).first()[0]
    finally:
        db.close()


def _taches(client, h):
    r = client.get("/api/prise-en-main", headers=h)
    assert r.status_code == 200, r.text
    pp = r.json()["premiers_pas"]
    return pp, {t["k"]: t for t in pp["taches"]}


# ═══ 1 et 2. « Vos premiers pas » : la liste d'activation, lue dans les données ═════════════════════════════════════

def test_compte_neuf_cinq_taches_au_verbe_pas_commencees(client):
    a = _inscrire(client)
    pp, t = _taches(client, a["headers"])
    assert pp["visible"] is True and pp["replie"] is False
    assert [x["k"] for x in pp["taches"]] == TACHES and pp["n_total"] == 5 and pp["n_terminees"] == 0
    assert all(x["statut"] == "pas_commence" for x in pp["taches"])
    assert t["dire"]["manque"] == ["metier", "zone", "montant"]
    assert t["suivre"] == {"k": "suivre", "statut": "pas_commence", "fait": 0, "sur": 3}
    assert t["plusieurs"]["profil"] == "aucun" and t["plusieurs"]["invitation"] is False
    # Jusqu'au : création du compte + 30 jours (le serveur le dit ; l'écran ne l'écrit jamais en dur).
    from app.models import User
    db = _db()
    try:
        cree = db.query(User).filter(User.email == a["email"]).first().created_at
    finally:
        db.close()
    assert pp["jusqu_au"] == (cree + timedelta(days=30)).date().isoformat()


def test_chaque_tache_terminee_selon_une_condition_lue_dans_les_donnees(client):
    from app.models import Document, KnowledgeDoc, Project
    a = _inscrire(client)
    h, uid = a["headers"], _uid(a["email"])
    crit = client.get("/api/criteria/", headers=h).json()
    # Dire ce que vous faites et où : métier, zone, puis le montant porté seul OU « Je ne sais pas ».
    client.put("/api/criteria/", headers=h, json=dict(crit, specialites="Couverture"))
    _, t = _taches(client, h)
    assert t["dire"]["statut"] == "en_cours" and t["dire"]["manque"] == ["zone", "montant"]
    client.put("/api/criteria/", headers=h, json=dict(crit, specialites="Couverture", departements="29"))
    _, t = _taches(client, h)
    assert t["dire"]["statut"] == "en_cours" and t["dire"]["manque"] == ["montant"]
    client.put("/api/criteria/", headers=h, json=dict(crit, specialites="Couverture", departements="29",
                                                      montant_porte_seul_inconnu=True))
    _, t = _taches(client, h)
    assert t["dire"]["statut"] == "termine" and t["dire"]["manque"] == []
    # Suivre 3 marchés : les marchés de Mes marchés (hors corbeille).
    pids = []
    for i in range(3):
        r = client.post("/api/projects/", headers=h, json={"name": f"Toiture de l'école {i}", "client": "Ville"})
        pids.append(r.json()["id"])
        _, t = _taches(client, h)
        assert t["suivre"]["fait"] == i + 1 and t["suivre"]["statut"] == ("termine" if i == 2 else "en_cours")
    # Lire le dossier d'un marché : importé (dossier rangé « DCE ») puis lu (analyse du dossier complet).
    _, t = _taches(client, h)
    assert t["lire"]["statut"] == "pas_commence" and t["lire"]["projet"] == pids[-1]       # le plus récent
    db = _db()
    try:
        db.add(Document(user_id=uid, name="RC.pdf", file_key="b1/rc.pdf", project_id=pids[0], folder="DCE"))
        db.commit()
    finally:
        db.close()
    _, t = _taches(client, h)
    assert t["lire"]["statut"] == "en_cours"
    db = _db()
    try:
        db.get(Project, pids[0]).ai_analysis = {"dce_available": True}
        db.commit()
    finally:
        db.close()
    _, t = _taches(client, h)
    assert t["lire"]["statut"] == "termine" and t["lire"]["projet"] is None
    # Inviter un partenaire, ou vous faire trouver : une invitation créée (ici un lien, sans courriel).
    r = client.post(f"/api/projects/{pids[0]}/invites", headers=h, json={"company_name": "Électricité Kerné"})
    assert r.status_code in (200, 201), r.text
    _, t = _taches(client, h)
    assert t["plusieurs"]["statut"] == "termine" and t["plusieurs"]["invitation"] is True
    # Ajouter vos 3 derniers dossiers de présentation (Mon savoir-faire) ; les autres documents ne comptent pas.
    db = _db()
    try:
        db.add(KnowledgeDoc(user_id=uid, name="Plaquette", kind="autre", text="x"))
        for i in range(2):
            db.add(KnowledgeDoc(user_id=uid, name=f"Dossier {i}", kind="memoire", text="x"))
        db.commit()
    finally:
        db.close()
    pp, t = _taches(client, h)
    assert t["dossiers"] == {"k": "dossiers", "statut": "en_cours", "fait": 2, "sur": 3}
    assert pp["visible"] is True and pp["n_terminees"] == 4
    db = _db()
    try:
        db.add(KnowledgeDoc(user_id=uid, name="Dossier 3", kind="memoire", text="x"))
        db.commit()
    finally:
        db.close()
    # Tout est fait : la liste quitte l'accueil (elle ne reste pas affichée pour rien).
    pp, t = _taches(client, h)
    assert all(x["statut"] == "termine" for x in pp["taches"]) and pp["visible"] is False


def test_le_profil_publie_ou_en_cours_compte_pour_vous_faire_trouver(client):
    from app.models import PartnerProfile
    a = _inscrire(client)
    uid = _uid(a["email"])
    db = _db()
    try:
        p = PartnerProfile(public_id="b1" + "0" * 30, user_id=uid, visible=False, validation_status="")
        db.add(p)
        db.commit()
    finally:
        db.close()
    _, t = _taches(client, a["headers"])
    assert t["plusieurs"]["statut"] == "en_cours" and t["plusieurs"]["profil"] == "brouillon"
    db = _db()
    try:
        db.query(PartnerProfile).filter(PartnerProfile.user_id == uid).first().visible = True
        db.commit()
    finally:
        db.close()
    r = client.get("/api/prise-en-main", headers=a["headers"]).json()
    t = {x["k"]: x for x in r["premiers_pas"]["taches"]}
    assert t["plusieurs"]["statut"] == "termine" and r["profil_reseau"] == "publie"


def test_trente_jours_apres_la_creation_du_compte_la_liste_quitte_l_accueil(client):
    from app.models import User
    from app.services import prise_en_main as pm
    a = _inscrire(client)
    db = _db()
    try:
        u = db.query(User).filter(User.email == a["email"]).first()
        u.created_at = datetime.now(timezone.utc) - timedelta(days=29, hours=23)
        db.commit()
        assert pm.premiers_pas(db, u)["visible"] is True
        u.created_at = datetime.now(timezone.utc) - timedelta(days=30, minutes=1)
        db.commit()
        hors = pm.premiers_pas(db, u)
        assert hors["visible"] is False and hors["taches"] == []          # rien n'est calculé hors de la période
        assert pm.PREMIERS_PAS_JOURS == 30
    finally:
        db.close()
    assert client.get("/api/prise-en-main", headers=a["headers"]).json()["premiers_pas"]["visible"] is False


def test_replie_garde_sur_le_serveur_pas_dans_le_navigateur(client):
    a = _inscrire(client)
    r = client.put("/api/prise-en-main", headers=a["headers"], json={"replie": True})
    assert r.status_code == 200 and r.json()["premiers_pas"]["replie"] is True
    # Une autre session (un autre appareil) retrouve l'état.
    tok = client.post("/api/auth/login", json={"email": a["email"], "password": "motdepasse123"}).json()["access_token"]
    autre = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/prise-en-main", headers=autre).json()["premiers_pas"]["replie"] is True
    assert client.put("/api/prise-en-main", headers=autre, json={"replie": False}).json()["premiers_pas"]["replie"] is False
    # Rien dans le navigateur : ni l'ancienne clé, ni une nouvelle.
    pp = "\n".join(_methode(n) for n in ("loadPriseEnMain", "ppReplier", "ppOuvrir", "ppVisible", "ppTaches", "ppRappel"))
    assert "localStorage" not in pp and "sessionStorage" not in pp and "adjugo_onboarding_done" not in JS


def test_ancienne_etape_lancez_votre_premiere_recherche_disparue():
    for src in (HTML, JS):
        assert "Lancez votre première recherche" not in src and "Premiers pas sur Adjugo" not in src
    assert "showOnboarding" not in HTML and "dismissOnboarding" not in JS and "    onboarding() {" not in JS


def test_demo_sans_premiers_pas_ni_carte_et_ecritures_refusees(client):
    tok = client.post("/api/auth/demo").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.get("/api/prise-en-main", headers=h).json()
    assert r["premiers_pas"]["visible"] is False and r["premiers_pas"]["taches"] == [] and r["suggestion_reseau"] is None
    assert client.put("/api/prise-en-main", headers=h, json={"replie": True}).status_code == 403
    assert client.post("/api/prise-en-main/suggestion-reseau/fermer", headers=h).status_code == 403


def test_cloisonnement_rien_du_chef_de_file_dans_les_premiers_pas_du_partenaire(client):
    """Un partenaire invité ne voit, dans ses premiers pas, que ses propres comptes : ni les marchés, ni les invitations,
    ni le dossier du chef de file. La réponse ne porte aucun nom ni aucun prix."""
    chef, part = _inscrire(client, nom="Chef de file SARL"), _inscrire(client, nom="Partenaire SAS")
    pid = client.post("/api/projects/", headers=chef["headers"], json={"name": "Groupe scolaire", "client": "Ville"}).json()["id"]
    inv = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"],
                      json={"recipient": part["email"], "company_name": "Partenaire SAS"}).json()
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=part["headers"]).status_code == 200
    r = client.get("/api/prise-en-main", headers=part["headers"]).json()
    t = {x["k"]: x for x in r["premiers_pas"]["taches"]}
    assert t["suivre"]["fait"] == 0 and t["lire"]["projet"] is None and t["plusieurs"]["invitation"] is False
    texte = json.dumps(r, ensure_ascii=False)
    assert "Groupe scolaire" not in texte and "Chef de file" not in texte
    assert [x.get("projet") for x in r["premiers_pas"]["taches"] if "projet" in x] == [None]   # aucun marché d'un autre
    _, tc = _taches(client, chef["headers"])
    assert tc["plusieurs"]["statut"] == "termine" and tc["lire"]["projet"] == pid


# ═══ La carte « Faites-vous trouver » gardée sur le serveur ═════════════════════════════════════════════════════════

def test_carte_faites_vous_trouver_gardee_sur_le_serveur(client):
    a = _inscrire(client, verifie=False)
    assert a["register"]["suggest_profile"]["code"] == "publier_profil_reseau"          # comme avant
    # L'onglet ouvert par le lien de confirmation (une autre session) la retrouve.
    tok = client.post("/api/auth/login", json={"email": a["email"], "password": "motdepasse123"}).json()["access_token"]
    autre = {"Authorization": f"Bearer {tok}"}
    s = client.get("/api/prise-en-main", headers=autre).json()["suggestion_reseau"]
    assert s and s["code"] == "publier_profil_reseau" and s["titre"] == "Faites-vous trouver pour des groupements"
    assert client.post("/api/prise-en-main/suggestion-reseau/fermer", headers=autre).json() == {"ok": True}
    assert client.get("/api/prise-en-main", headers=a["headers"]).json()["suggestion_reseau"] is None
    # Une nouvelle proposition (acceptation d'une invitation) la remontre, comme avant.
    chef = _inscrire(client, nom="Chef")
    pid = client.post("/api/projects/", headers=chef["headers"], json={"name": "Marché", "client": "Ville"}).json()["id"]
    inv = client.post(f"/api/projects/{pid}/invites", headers=chef["headers"], json={"company_name": "Couvreurs"}).json()
    from app.models import User
    db = _db()
    try:
        db.query(User).filter(User.email == a["email"]).first().email_verified = True
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/invite/{inv['token']}/claim", headers=a["headers"]).json()["suggest_profile"]
    assert client.get("/api/prise-en-main", headers=a["headers"]).json()["suggestion_reseau"]["code"] == "publier_profil_reseau"
    # Écran : fermer ou suivre la carte la ferme aussi sur le serveur.
    for m in ("rnSuggestClose", "rnSuggestGo"):
        assert "this._rnSuggestFermer();" in _methode(m)
    assert '"/api/prise-en-main/suggestion-reseau/fermer"' in _methode("_rnSuggestFermer")
    assert "this._rnSuggest(r.suggestion_reseau)" in _methode("loadPriseEnMain")


def test_carte_proposee_aussi_a_l_inscription_par_google():
    src = (ROOT / "app" / "routers" / "google_auth.py").read_text(encoding="utf-8")
    i = src.index("    if is_new:")
    assert "proposer_suggestion_reseau(db, user)" in src[i:i + 900]


# ═══ « Je ne sais pas » au montant porté seul ══════════════════════════════════════════════════════════════════════

def test_montant_porte_seul_je_ne_sais_pas(client):
    a = _inscrire(client)
    h = a["headers"]
    d = client.get("/api/criteria/", headers=h).json()
    assert d["montant_porte_seul"] is None and d["montant_porte_seul_inconnu"] is False       # jamais répondu
    r = client.put("/api/criteria/", headers=h, json=dict(d, montant_porte_seul_inconnu=True)).json()
    assert r["montant_porte_seul"] is None and r["montant_porte_seul_inconnu"] is True
    # Une page plus ancienne qui n'envoie aucun des deux garde la réponse.
    sans = {k: v for k, v in d.items() if not k.startswith("montant_porte_seul")}
    assert client.put("/api/criteria/", headers=h, json=sans).json()["montant_porte_seul_inconnu"] is True
    # Un montant donné retire « Je ne sais pas » (une seule réponse à la fois).
    r = client.put("/api/criteria/", headers=h, json=dict(d, montant_porte_seul=250000, montant_porte_seul_inconnu=True)).json()
    assert r["montant_porte_seul"] == 250000 and r["montant_porte_seul_inconnu"] is False
    r = client.put("/api/criteria/", headers=h, json=dict(d, montant_porte_seul=None, montant_porte_seul_inconnu=True)).json()
    assert r["montant_porte_seul"] is None and r["montant_porte_seul_inconnu"] is True
    # Mes données (RGPD) : la réponse est exportée avec les critères.
    assert client.get("/api/rgpd/export", headers=h).json()["criteres"]["montant_porte_seul_inconnu"] is True


def test_je_ne_sais_pas_n_entre_dans_aucun_calcul():
    """Comme le montant (vague 2a, A3) : seul app/routers/criteria_v2.py le nomme ; la liste d'activation lit seulement
    qu'une réponse a été donnée (ce_que_je_cherche_dit)."""
    lecteurs = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "app").rglob("*.py")
                      if "montant_porte_seul" in p.read_text(encoding="utf-8"))
    assert lecteurs == ["app/routers/criteria_v2.py"], lecteurs
    src = (ROOT / "app" / "services" / "prise_en_main.py").read_text(encoding="utf-8")
    assert "ce_que_je_cherche_dit(db, owner)" in src


def test_fenetre_siret_pose_la_question_du_montant_porte_seul():
    f = zone(HTML, "fenetre-siret")
    assert "Jusqu'à quel montant répondez-vous seul ?" in f and ">Je ne sais pas</label>" in f
    assert 'v-model.number="welcome.seul"' in f and 'v-model="welcome.seulInconnu"' in f and "facultatif" in f
    assert "Un seul champ suffit" not in f                     # il y a maintenant une question de plus (facultative)
    assert 'data-lucide="sparkles"' not in f                   # réservé aux actions de l'IA (§ 8, règle 5)
    w = _methode("welcomeStart")
    # Relecture de la vague 2b : welcomeStart contrôle le montant avant l'envoi (montantSeulValide, en tête du fichier).
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    r = _node(borne + "const o = {\n" + w + "\n};\n" + r"""
const res = {};
async function cas(seul, ns) {
  const envoye = [];
  Object.assign(o, { welcome: { siret: "12345678900012", busy: false, seul, seulInconnu: ns }, company: {}, criteria: { montant_porte_seul: null, montant_porte_seul_inconnu: false },
    src: { query: "", dept: "" }, notify() {}, go() {}, $nextTick() {}, srcSearch() {}, welcomeDone() {}, loadPriseEnMain() {},
    api: async (m, p, b) => { if (p.startsWith("/api/registre")) return { name: "Couvreurs", siret: "12345678900012", postal_code: "29200" };
                              if (p === "/api/criteria/") envoye.push(JSON.parse(JSON.stringify(b))); return {}; } });
  await o.welcomeStart();
  return envoye[0];
}
(async () => {
  res.montant = await cas(150000, false); res.ns = await cas("", true); res.rien = await cas("", false);
  console.log(JSON.stringify(res));
})();
""")
    assert r["montant"]["montant_porte_seul"] == 150000 and r["montant"]["montant_porte_seul_inconnu"] is False
    assert r["ns"]["montant_porte_seul"] is None and r["ns"]["montant_porte_seul_inconnu"] is True
    assert r["rien"]["montant_porte_seul"] is None and r["rien"]["montant_porte_seul_inconnu"] is False   # rien de déduit


def test_ce_que_je_cherche_a_sa_case_je_ne_sais_pas():
    v = zone(HTML, "vue-criteria")
    assert ':disabled="!!criteria.montant_porte_seul_inconnu"' in v and ">Je ne sais pas</label>" in v
    assert '@change="critSeulInconnu($event.target.checked)"' in v
    assert "cochez « Je ne sais pas »" in v and "Laissez vide si vous ne savez pas" not in v
    r = _node("const o = {\n" + _methode("critSeulInconnu") + """
};
o.criteria = { montant_porte_seul: 90000, montant_porte_seul_inconnu: false };
o.critSeulInconnu(true); const a = JSON.parse(JSON.stringify(o.criteria));
o.critSeulInconnu(false); console.log(JSON.stringify({ a, b: o.criteria }));""")
    assert r["a"] == {"montant_porte_seul": None, "montant_porte_seul_inconnu": True}
    assert r["b"] == {"montant_porte_seul": None, "montant_porte_seul_inconnu": False}


# ═══ L'écran : la liste, ses statuts, ses rappels (sous Node) ═══════════════════════════════════════════════════════

SERVEUR = {"visible": True, "replie": False, "jusqu_au": "2026-11-19", "n_terminees": 1, "n_total": 5, "taches": [
    {"k": "dire", "statut": "en_cours", "fait": 2, "sur": 3, "manque": ["montant"]},
    {"k": "suivre", "statut": "en_cours", "fait": 1, "sur": 3},
    {"k": "lire", "statut": "pas_commence", "projet": 12},
    {"k": "plusieurs", "statut": "pas_commence", "invitation": False, "profil": "aucun"},
    {"k": "dossiers", "statut": "termine", "fait": 3, "sur": 3},
    {"k": "inconnue", "statut": "termine"}]}


def test_taches_au_verbe_trois_statuts_et_leurs_chemins_sous_node():
    r = _node(_PP + """
const pp = JSON.parse(process.argv[1]);
console.log(JSON.stringify({ avec: tachesPremiersPas(pp, 2), sans: tachesPremiersPas(pp, 0),
  rappel: { dire: rappelPremiersPas(pp, "dire"), dossiers: rappelPremiersPas(pp, "dossiers"),
            cache: rappelPremiersPas(Object.assign({}, pp, { visible: false }), "dire") },
  statuts: PP_STATUTS }));
""", json.dumps(SERVEUR))
    t = {x["k"]: x for x in r["avec"]}
    assert list(t) == TACHES                                                   # la clé inconnue n'est pas affichée
    assert r["statuts"] == {"pas_commence": "Pas commencé", "en_cours": "En cours", "termine": "Terminé"}
    # Relecture de la vague 2b : « Suivre 3 marchés » nommait un geste absent ; « Ajouter 3 marchés à Mes marchés ».
    verbes = ("Dire", "Ajouter", "Lire", "Inviter", "Ajouter")
    assert [x["titre"].split()[0] for x in r["avec"]] == list(verbes)          # chaque tâche commence par un verbe
    assert t["dire"]["detail"] == "Reste à dire : le montant que vous portez seul (ou « Je ne sais pas »)."
    assert t["suivre"]["detail"] == "1 sur 3 dans Mes marchés." and t["suivre"]["libelle"] == "En cours"
    assert t["lire"]["actions"][0]["cible"] == {"view": "aodetail", "projet": 12}
    assert t["dossiers"]["actions"] == [] and t["dossiers"]["pill"] == "go"   # terminée : plus d'action
    # « Inviter un partenaire » seulement s'il y a un marché sur lequel inviter ; « Publier mon profil » sinon.
    assert [a["label"] for a in t["plusieurs"]["actions"]] == ["Inviter un partenaire", "Publier mon profil"]
    assert [a["label"] for a in {x["k"]: x for x in r["sans"]}["plusieurs"]["actions"]] == ["Publier mon profil"]
    assert r["rappel"]["dire"]["titre"] == "Dire ce que vous faites et où"
    assert r["rappel"]["dossiers"] is None and r["rappel"]["cache"] is None


def test_bloc_de_l_accueil_repliable_et_accessible():
    b = zone(HTML, "accueil-premiers-pas")
    assert b.startswith('<section data-test="accueil-premiers-pas" v-if="ppVisible()"')
    assert ">Vos premiers pas</b>" in b and 'aria-labelledby="pp-t"' in b
    # Relecture de la vague 2b : replié, la liste quitte la page (v-if) ; aria-controls ne la désigne alors plus (une
    # référence ARIA vers un élément absent est cassée).
    assert (':aria-expanded="pp.d.replie ? \'false\' : \'true\'" :aria-controls="pp.d.replie ? null : \'pp-liste\'"'
            in b) and ' aria-controls="pp-liste"' not in b
    assert "{{ pp.d.replie ? 'Déplier' : 'Replier' }}" in b and '@click="ppReplier(!pp.d.replie)"' in b
    # « N sur M » (décision 8), jamais un % ; relecture de la vague 2b : chaque morceau dans son élément, « sur » est
    # une clé du dictionnaire (traduit en néerlandais et en espagnol).
    assert "<span>{{ pp.d.n_terminees }}</span> <span>sur</span> <span>{{ pp.d.n_total }}</span>" in b
    assert "%" not in re.sub(r"<!--.*?-->", "", b, flags=re.S)
    assert "fmtDate(pp.d.jusqu_au)" in b and "30 jours" not in re.sub(r"<!--.*?-->", "", b, flags=re.S)
    assert '@click="ppOuvrir(a)"' in b and "{{ t.libelle }}" in b
    assert '"/api/prise-en-main", { replie: !!replie }' in _methode("ppReplier")
    # Lu au démarrage, en revenant à l'accueil, après « Ce que je cherche » et la fenêtre du SIRET.
    boot = _methode("boot")
    # Relecture de la vague 2b : les pièces à renouveler et les invitations reçues sont lues dans le même allSettled.
    assert "this.loadPriseEnMain(), this.loadExpiring(), this.rnLoadRecues(true)]" in boot
    assert "this.loadPriseEnMain(); }" in _methode("go") and "this.loadPriseEnMain();" in _methode("saveCriteria")
    assert "this.loadPriseEnMain();" in _methode("welcomeStart")


def test_ppouvrir_mene_a_l_ecran_de_chaque_tache_sous_node():
    r = _node("const o = {\n" + _methode("ppOuvrir") + """
};
const j = [];
Object.assign(o, { rubriqueGo: k => j.push("rubrique:" + k), openProjectById: id => j.push("marche:" + id),
  inviterOuvrir: () => j.push("inviter"), openReseau: t => j.push("reseau:" + t), go: v => j.push("go:" + v) });
[{ view: "criteria" }, { rubrique: "trouver" }, { view: "aodetail", projet: 12 }, { inviter: true }, { reseau: "profil" },
 { view: "kb" }].forEach(c => o.ppOuvrir({ cible: c }));
console.log(JSON.stringify(j));""")
    assert r == ["go:criteria", "rubrique:trouver", "marche:12", "inviter", "reseau:profil", "go:kb"]


# ═══ 3. Les états vides du § 7.3 ═══════════════════════════════════════════════════════════════════════════════════

def _rappel(src, k):
    return f"<p v-if=\"ppRappel('{k}')\" class=\"pp-rappel small" in src


def test_etats_vides_de_l_etude_et_rappel_de_chaque_tache():
    dash, mm = zone(HTML, "vue-dashboard"), zone(HTML, "vue-pipeline")
    # Accueil › À faire ; Accueil › À plusieurs.
    assert "Rien n'attend de réponse de votre part." in zone(HTML, "accueil-a-faire")
    reseau = zone(HTML, "accueil-reseau")
    assert "Aucun groupement en cours. Pour répondre avec une autre entreprise, ouvrez un marché et invitez-la." in reseau
    assert _rappel(reseau, "plusieurs")
    # Trouver › Publiés (premier lancement) et zéro résultat (la carte d'élargissement, inchangée) ; À venir.
    src = zone(HTML, "vue-sourcing")
    assert _rappel(src, "suivre") and "Élargissez votre recherche en un clic" in src
    radar = zone(HTML, "trouver-radar")
    assert "Contrats de votre zone qui arrivent à échéance." in radar and "Modifier ma zone" in radar
    # Mes marchés ; Où je suis partenaire.
    assert "Les marchés que vous suivez ou analysez arrivent ici." in mm and _rappel(mm, "suivre")
    assert "Publier mon profil sur le réseau" in mm and 'v-if="ppProfilAPublier()"' in mm and _rappel(mm, "plusieurs")
    # Partenaires › Réseau Adjugo, profil non publié.
    an = zone(HTML, "reseau-annuaire")
    assert "L'annuaire s'ouvre quand votre profil est publié : c'est la règle pour tous." in an
    assert "Compléter mon profil" in an and _rappel(an, "plusieurs")
    # Mes documents › Mes pièces (vague 2a) ; Mon savoir-faire, avec son bouton « Importer ».
    assert "Ajoutez vos attestations avec leur date de fin" in zone(HTML, "vue-documents")
    kb = zone(HTML, "vue-kb")
    assert "Vos anciens dossiers servent de source au dossier de présentation." in kb and _rappel(kb, "dossiers")
    assert '@click="$refs.kbUpl.click()" :disabled="kb.uploading"><i data-lucide="upload"></i>Importer</button>' in kb
    # Ce que je cherche ; la page du marché, étape Lire.
    assert _rappel(zone(HTML, "vue-criteria"), "dire") and _rappel(zone(HTML, "marche-analyse"), "lire")
    assert "Premiers pas" not in dash.replace("Vos premiers pas", "")


def test_aucune_promesse_d_une_fonction_qui_n_est_pas_en_ligne():
    for src in (HTML, JS):
        assert "projets votés en conseil" not in src.lower()            # Veille V1 : pas en ligne
    # « Voir un exemple » : seulement quand le marché d'exemple (/app/exemple) est en ligne, et il y mène.
    boutons = re.findall(r"<button[^>]*>(?:(?!</button>).)*Voir un exemple</button>", HTML, re.S)
    assert len(boutons) == 3
    pp = zone(HTML, "accueil-premiers-pas")
    garde = pp[pp.index('<div v-if="exempleEnLigne()" class="pp-exemple">'):]
    garde = garde[:garde.index("</div>")]
    assert "Entreprises et client fictifs" in garde
    for b in boutons:
        assert "@click=\"go('exemple')\"" in b, b
        assert 'v-if="exempleEnLigne()"' in b or b in garde, b              # le bouton, ou le bloc qui le porte


def test_exemple_en_ligne_seulement_quand_l_adresse_ouvre_l_ecran_sous_node():
    # Réunion de la vague 2b (docs/REORGANISATION_V2B.md, § R) : le chantier B2 a mis en ligne /app/exemple, donc
    # « Voir un exemple » s'affiche ; sans l'adresse de l'exemple (un écran absent), il ne s'afficherait pas.
    m = _methode("exempleEnLigne")
    r = _node(_ADRESSES + "\nconst o = {\n" + m + """
};
const en_ligne = o.exempleEnLigne(), adr = adresseDe({ view: "exemple" });
delete ADRESSES.exemple;                   // sans l'écran du marché d'exemple
console.log(JSON.stringify({ en_ligne, adr, sans: o.exempleEnLigne() }));""")
    assert r == {"en_ligne": True, "adr": "/app/exemple", "sans": False}


# ═══ 4. La confirmation d'email vivante (décision 12 (a)) ══════════════════════════════════════════════════════════

def test_ecran_de_confirmation_dit_la_suite_et_se_reverifie():
    e = zone(HTML, "ecran-confirmation-email")
    assert APRES in e and '<p v-if="!(company && company.siret)" class="small conf-suite">' in e
    assert "cette page s'ouvre d'elle-même" in e and 'role="status"' in e
    assert '@click="confirmationVerifier(true)"' in e and "Renvoyer l'email de vérification" in e
    # La réponse des deux boutons s'affiche DANS l'écran : le message habituel (z-index 200) passe sous lui (300).
    assert '<p v-if="confirmation.message" class="small conf-msg" role="status" aria-live="polite">' in e
    assert '@click="confirmationRenvoyer()"' in e and "resendVerification" not in e
    assert re.search(r"\.toast \{[^}]*z-index:200;", CSS) and "z-index:300" in e
    assert 'role="dialog" aria-modal="true" aria-labelledby="conf-t"' in e
    from app.routers.auth import APRES_CONFIRMATION
    assert APRES_CONFIRMATION == APRES                                          # la même phrase, écran et courriel
    assert '"user.email_verified"(v) { if (v === false && this.token) this.confirmationSuivre(); else this.confirmationArreter(); }' in JS


def test_revérification_sans_marteler_le_serveur_sous_node():
    r = _node(_PP + "\nconsole.log(JSON.stringify([0, 119999, 120000, 899999, 900000, 3600000].map(delaiReverification)));")
    assert r == [5000, 5000, 15000, 15000, 60000, 60000]


def test_revérification_au_retour_sur_l_onglet_et_seulement_visible_sous_node():
    noms = ("confirmationSuivre", "confirmationArreter", "_confPlanifier", "confirmationVerifier")
    r = _node(_PP + "\nconst o = {\n" + ",\n".join(_methode(n) for n in noms) + "\n};\n" + r"""
const ev = {}, minuteries = [], appels = [], j = [];
let vis = "visible", verifie = false, maintenant = 1000000;
Date.now = () => maintenant;
global.document = { get visibilityState() { return vis; }, addEventListener: (k, f) => { ev["doc:" + k] = f; }, removeEventListener: k => { delete ev["doc:" + k]; } };
global.window = { addEventListener: (k, f) => { ev["win:" + k] = f; }, removeEventListener: k => { delete ev["win:" + k]; } };
global.setTimeout = (f, ms) => { minuteries.push({ f, ms, vive: true }); return minuteries.length; };
global.clearTimeout = id => { if (minuteries[id - 1]) minuteries[id - 1].vive = false; };
global.fetch = async (url, opt) => { appels.push([url, opt.cache]); return { status: 200, ok: true, json: async () => ({ id: 1, email_verified: verifie }) }; };
Object.assign(o, { token: "t", user: { id: 1, email_verified: false }, confirmation: { enCours: false, depuis: 0, vu: 0 },
  notify: m => j.push(m), loadPriseEnMain: () => j.push("pp"), sessionPerdue: () => j.push("perdue") });
const vivantes = () => minuteries.filter(m => m.vive);
(async () => {
  o.confirmationSuivre();
  const premier = vivantes().map(m => m.ms);
  // Onglet caché : plus aucune minuterie ; on y revient : une vérification tout de suite.
  vis = "hidden"; ev["doc:visibilitychange"]();
  const cache = vivantes().length;
  vis = "visible"; maintenant += 5000; ev["doc:visibilitychange"](); await new Promise(r => setImmediate(r));
  const apresRetour = appels.length;
  ev["win:focus"](); await new Promise(r => setImmediate(r));          // focus juste après : pas un second appel
  const apresFocus = appels.length;
  // Le lien a été cliqué ailleurs : la vérification suivante ouvre l'écran.
  verifie = true; maintenant += 5000; const m = vivantes().pop(); m.vive = false; await m.f(); await new Promise(r => setImmediate(r));
  console.log(JSON.stringify({ premier, cache, apresRetour, apresFocus, user: o.user, j, cacheOpt: appels[0][1] }));
})();
""")
    assert r["premier"] == [5000] and r["cache"] == 0
    assert r["apresRetour"] == 1 and r["apresFocus"] == 1 and r["cacheOpt"] == "no-store"
    assert r["user"]["email_verified"] is True and r["j"] == ["Adresse email confirmée", "pp"]


def test_reponses_de_l_ecran_de_confirmation_dans_l_ecran_sous_node():
    noms = ("confirmationRenvoyer", "confirmationVerifier", "_confPlanifier")
    r = _node(_PP + "\nconst o = {\n" + ",\n".join(_methode(n) for n in noms) + "\n};\n" + r"""
const j = [], appels = [];
let reponse = { message: "Email de confirmation renvoyé." }, refus = null;
global.document = { visibilityState: "visible" };
global.setTimeout = () => 1; global.clearTimeout = () => {};
global.fetch = async () => ({ status: 200, ok: true, json: async () => ({ id: 1, email_verified: false }) });
Object.assign(o, { token: "t", user: { id: 1, email_verified: false }, confirmation: { enCours: false, depuis: 0, vu: 0, message: "" },
  notify: m => j.push(m), loadPriseEnMain() {}, sessionPerdue() {},
  api: async (m, p) => { appels.push(m + " " + p); if (refus) throw new Error(refus); return reponse; } });
(async () => {
  await o.confirmationVerifier(true);
  const clic = o.confirmation.message;
  await o.confirmationRenvoyer();
  const renvoi = o.confirmation.message;
  refus = "Plusieurs emails de confirmation sont déjà partis."; await o.confirmationRenvoyer();
  console.log(JSON.stringify({ clic, renvoi, refus: o.confirmation.message, j, appels }));
})();
""")
    assert r["clic"] == "Pas encore confirmée : cliquez sur le lien du courriel, puis revenez ici."
    assert r["renvoi"] == "Email de confirmation renvoyé." and r["refus"].startswith("Plusieurs emails")
    assert r["j"] == [] and r["appels"] == ["POST /api/auth/resend-verification"] * 2     # aucun message sous l'écran


def test_courriel_de_confirmation_dit_la_suite_seulement_quand_elle_est_vraie(client, monkeypatch):
    import app.routers.auth as A
    envoyes = []
    monkeypatch.setattr(A, "send_email", lambda to, subject, text, html=None, **kw: envoyes.append((to, text, html)) or True)
    a = _inscrire(client, verifie=False)
    to, texte, html = envoyes[-1]
    assert to == a["email"] and APRES in texte and APRES in html and "/app?verify=" in texte
    # L'entreprise a déjà son SIRET (adresse changée, collègue) : pas de « vous entrez votre SIRET ».
    from app.models import Company
    db = _db()
    try:
        db.query(Company).filter(Company.user_id == _uid(a["email"])).first().siret = "12345678900012"
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/resend-verification", headers=a["headers"]).status_code == 200
    _, texte, html = envoyes[-1]
    assert APRES not in texte and APRES not in html and "Confirmez votre adresse email" in texte


def test_le_serveur_refuse_toujours_ce_qu_il_refusait_sans_adresse_confirmee(client, monkeypatch):
    import app.services.email as E
    envoyes = []
    monkeypatch.setattr(E, "send_email", lambda to, subject, text, html=None, **kw: envoyes.append(to) or True)
    from app.services.demo_search import search_results
    a = _inscrire(client, verifie=False)
    h = a["headers"]
    avis = search_results()[0].model_dump(exclude={"raw"})
    avis["provenance"]["official_ref"] = "26-654321"                             # un vrai marché, pas la démo
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": avis})
    assert r.status_code == 403 and "Confirmez votre adresse email" in r.text   # aucune analyse
    pid = client.post("/api/projects/", headers=h, json={"name": "Marché", "client": "Ville"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"recipient": "x@test.fr", "company_name": "X"})
    assert r.status_code == 200 and r.json()["emailed"] is False and "x@test.fr" not in envoyes   # le lien, pas de courriel
    assert client.get("/api/prise-en-main", headers=h).status_code == 200      # l'écran peut toujours lire son état


def test_commentaire_d_auth_py_decrit_le_blocage_tel_qu_il_est():
    src = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    i = src.index("    # Email de confirmation. Choix du 24/06, gardé")
    c = src[i:src.index("    _send_verification(user)", i)]
    c = re.sub(r"\s*\n\s*#\s*", " ", c)                                       # le commentaire, en une seule ligne
    for mot in ("décision 12 (a)", "ecran-confirmation-email", "revérifie seul", "consume_analysis", "email_non_confirme",
                "membre du réseau", "publication du profil", "convention", "lien nominatif",
                "aucun courriel au nom d'Adjugo", "Ne vérifient PAS", "exiger_ia"):
        assert mot in c, mot
    # Chaque refus dit dans le commentaire existe dans le code ; exiger_ia, lui, ne lit pas l'adresse (dit tel quel).
    q = (ROOT / "app/core/quota.py").read_text(encoding="utf-8")
    assert 'if not getattr(user, "email_verified", True):' in q[q.index("def consume_analysis"):]
    assert "email_verified" not in q[q.index("def exiger_ia"):q.index("def trial_analyses_limit")]
    for f in ("atelier.py", "atelier_groupement.py", "entretien.py"):
        assert '"email_non_confirme"' in (ROOT / "app/routers" / f).read_text(encoding="utf-8"), f
    assert "adresse_a_confirmer" in (ROOT / "app/services/fiches_import.py").read_text(encoding="utf-8")
    inv = (ROOT / "app/routers/invites.py").read_text(encoding="utf-8")
    assert "pour accepter ce partage nominatif" in inv and 'getattr(current_user, "email_verified", False)' in inv
    res = (ROOT / "app/routers/reseau.py").read_text(encoding="utf-8")
    assert '"email_non_verifie"' in res and "inviter un partenaire du réseau" in res
    conv = (ROOT / "app/routers/convention.py").read_text(encoding="utf-8")
    assert '"enregistrer votre accord."' in conv and '"email_non_verifie"' in conv
    assert 'raise RuntimeError("expéditeur non confirmé")' in (ROOT / "app/routers/org.py").read_text(encoding="utf-8")


def test_bandeau_des_cookies_ne_passe_plus_sur_la_fenetre_du_siret():
    b = zone(HTML, "bandeau-cookies")
    assert 'v-if="!cookiesOk && !mobileNav && !(token && showWelcome)"' in b


# ═══ 5. Rechargement d'une adresse profonde : aucun écran avant qu'elle soit résolue ═══════════════════════════════

def test_aucun_ecran_avant_que_l_adresse_soit_resolue():
    assert '      view: "", ecranPret: false,' in JS                               # aucun écran au départ
    assert '<div data-test="contenu" v-show="ecranPret" class="content">' in HTML
    att = zone(HTML, "ecran-attente")
    assert att.startswith('<div data-test="ecran-attente" v-if="token && !ecranPret"') and 'role="status"' in att
    boot = _methode("boot")
    assert "Promise.allSettled([" in boot                                       # un échec n'empêche pas d'ouvrir
    assert boot.index("this._ouvrirAdresse(_demande);") < boot.index("if (!this._adresseAttente) this.ecranPret = true;")
    assert "catch (e) { this.ecranPret = true; return; }" in boot
    assert "|| !this.ecranPret) return false;" in JS[JS.index("    showWelcome() {"):JS.index("    showWelcome() {") + 400]
    # Avant le montage de Vue, le gabarit brut (tous les écrans, avec leurs {{ … }}) n'est pas peint : la feuille de
    # style, chargée dans <head>, le cache jusqu'à ce que Vue pose `data-v-app` sur #app (il le pose au montage).
    assert "#app:not([data-v-app]) { display:none; }" in CSS
    assert HTML.index('<link rel="stylesheet" href="/static/styles.css">') < HTML.index("</head>") < HTML.index('<div id="app">')
    vue = sorted(p.name for p in (STATIC / "vendor").glob("vue-*.js"))[-1]
    assert 'r.setAttribute("data-v-app","")' in (STATIC / "vendor" / vue).read_text(encoding="utf-8")
    # Seule la page de l'application a un #app (les autres pages qui lisent styles.css n'en ont pas).
    for page in STATIC.glob("*.html"):
        if page.name != "app.html":
            assert 'id="app"' not in page.read_text(encoding="utf-8"), page.name


def test_marche_demande_a_l_api_l_ecran_s_ouvre_a_la_reponse_sous_node():
    m = _methode("_appliquerAdresse")
    r = _node(_ADRESSES + "\nconst o = {\n" + m + r"""
};
const j = [];
let reponse = null;
global.location = { pathname: "/app/marches/12" };
Object.assign(o, { view: "", ao: { project: null }, projects: [], ecranPret: false, _adresseAttente: false,
  _sansHistorique(f) { f(); }, openAo(p) { j.push("ouvre:" + p.id); this.view = "aodetail"; this.ao.project = p; },
  atlOpen() {}, notify(t) { j.push(t); }, go(v) { j.push("go:" + v); this.view = v; },
  api: () => reponse });
(async () => {
  reponse = Promise.resolve({ id: 12, name: "Marché" });
  o._appliquerAdresse({ view: "aodetail", projet: 12 });
  const pendant = { pret: o.ecranPret, attente: o._adresseAttente };
  await new Promise(r => setImmediate(r));
  const ok = { pret: o.ecranPret, view: o.view };
  o.ecranPret = false; reponse = Promise.reject(new Error("404"));
  o._appliquerAdresse({ view: "aodetail", projet: 12 });
  await new Promise(r => setImmediate(r));
  console.log(JSON.stringify({ pendant, ok, refus: { pret: o.ecranPret, view: o.view }, j }));
})();
""")
    assert r["pendant"] == {"pret": False, "attente": True}                     # rien d'affiché pendant l'appel
    assert r["ok"] == {"pret": True, "view": "aodetail"}
    assert r["refus"] == {"pret": True, "view": "pipeline"} and "Ce marché n'est plus accessible" in r["j"]


# ═══ § 7.4 L'aide en bulles ════════════════════════════════════════════════════════════════════════════════════════

def _bulles(src):
    return re.findall(r'<span class="tip-b" role="tooltip">(.*?)</span></button>', src, re.S)


def test_les_deux_bulles_qui_manquaient_sans_action_dedans():
    lire = zone(HTML, "marche-analyse")
    assert '<span class="sr-only">Où récupérer le dossier du marché</span>' in lire
    assert "<b>Où récupérer le dossier du marché</b> : sur la plateforme où le client l'a publié" in lire
    # Le lien de l'avis est à côté de la bulle, jamais dedans (aucune action dans une bulle).
    assert "Ouvrir l'avis du marché</a>" in lire and ':href="safeUrl(aoSource().source_url)"' in lire
    plus = zone(HTML, "marche-plusieurs")
    assert '<span class="sr-only">Comment Adjugo dit seul ou à plusieurs</span>' in plus
    b = plus[plus.index("Comment Adjugo dit seul ou à plusieurs</span>"):]
    b = b[:b.index("</span></button>")]
    for critere in ("métier", "zone", "montant", "capacité financière", "qualifications", "délai de réponse"):
        assert critere in b, critere
    assert "Une capacité inconnue ne compte jamais en plus." in b
    for z in ("accueil-premiers-pas", "marche-analyse", "marche-plusieurs", "fenetre-siret"):
        for t in _bulles(zone(HTML, z)):
            assert "<a " not in t and "@click" not in t and "<button" not in t, (z, t[:80])


def test_une_seule_bulle_d_explication_par_carte_nouvelle():
    pp = zone(HTML, "accueil-premiers-pas")
    assert pp.count('class="tip"') == 1
    entete = pp[:pp.index("</div>")]
    assert entete.count('class="tip"') == 1                                      # à côté du titre


# ═══ Textes, mots, traductions, 375 px ═════════════════════════════════════════════════════════════════════════════

NOUVEAUX = [
    "Vos premiers pas", "Vos premiers pas :", "Replier", "Déplier", "Dire ce que vous faites et où", "Ajouter 3 marchés à Mes marchés",
    "Lire le dossier d'un marché", "Inviter un partenaire, ou vous faire trouver",
    "Ajouter vos 3 derniers dossiers de présentation", "Pas commencé", "En cours", "Terminé",
    "Métier, zone et montant porté seul : c'est dit.", "Un dossier complet lu.", "Dossier importé, pas encore lu en entier.",
    "Importez le dossier complet d'un marché, à l'étape Lire de sa page.", "Partenaire invité sur un marché.",
    "Profil publié sur le réseau Adjugo.", "Profil en attente de validation par Adjugo.",
    "Profil partenaire enregistré, pas encore publié.",
    "Invitez une entreprise sur un marché, ou publiez votre profil partenaire.", "Ouvrir le marché", "Publier mon profil",
    "Voir ma demande de publication", "Importer", "Voir un exemple", "Entreprises et client fictifs",
    "Rien n'attend de réponse de votre part.",
    "Aucun groupement en cours. Pour répondre avec une autre entreprise, ouvrez un marché et invitez-la.",
    "L'annuaire s'ouvre quand votre profil est publié : c'est la règle pour tous.", "Compléter mon profil",
    "Les marchés que vous suivez ou analysez arrivent ici.", "Publier mon profil sur le réseau",
    "Contrats de votre zone qui arrivent à échéance.", "Modifier ma zone",
    "Vos anciens dossiers servent de source au dossier de présentation.", "Où récupérer le dossier du marché",
    "Ouvrir l'avis du marché", "Comment Adjugo dit seul ou à plusieurs", "Je ne sais pas",
    "Jusqu'à quel montant répondez-vous seul ?", "Montant en € HT", APRES,
    "Dès que vous cliquez sur le lien, ici ou sur votre téléphone, cette page s'ouvre d'elle-même.",
    "J'ai cliqué sur le lien", "Chargement de l'écran", "Adresse email confirmée", "Email de confirmation renvoyé.",
    "Pas encore confirmée : cliquez sur le lien du courriel, puis revenez ici.",
]


def test_traductions_des_libelles_nouveaux():
    s = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)[1]
    d = json.loads(s[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for lib in NOUVEAUX:
        assert d["nl"].get(lib) and d["es"].get(lib), lib
        assert lib in HTML or lib in JS, lib
    # Règle de la vague 1 : un seul mot pour « marché » et pour « à plusieurs ».
    t = "Ajouter 3 marchés à Mes marchés"                   # relecture de la vague 2b (était « Suivre 3 marchés »)
    assert "aanbesteding" in d["nl"][t] and "licitaciones" in d["es"][t]
    assert "samen" in d["nl"]["Comment Adjugo dit seul ou à plusieurs"]
    assert "agrupación" in d["es"]["Comment Adjugo dit seul ou à plusieurs"]


def test_aucun_mot_banni_aucun_emoji_et_verifie_seulement_pour_le_registre():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅]")
    zones_b1 = "".join(zone(HTML, n) for n in ("accueil-premiers-pas", "accueil-a-faire", "accueil-reseau",
                                               "vue-pipeline", "trouver-radar", "reseau-annuaire", "vue-kb",
                                               "vue-criteria", "fenetre-siret", "ecran-confirmation-email",
                                               "ecran-attente", "marche-analyse", "marche-plusieurs"))
    for _, t in textes_html(zones_b1):
        assert not mots_bannis(t), (t, mots_bannis(t))
        assert not emoji.search(t), t
    for lib in NOUVEAUX + [_PP]:
        assert not emoji.search(lib)
    for _, t in textes_html(zones_b1):
        assert not re.search(r"\bvérifi[ée]e?s?\b", t, re.I) or "registre" in t, t
    src = (ROOT / "app" / "services" / "prise_en_main.py").read_text(encoding="utf-8")
    assert "co-traitant" not in src.lower() and "consortium" not in src.lower()


def test_375_px_la_liste_passe_a_la_ligne_sans_defiler_de_cote():
    i = CSS.index("/* ══════════ Prise en main (réorganisation, vague 2b, B1")
    bloc = CSS[i:]
    m = bloc[bloc.index("@media (max-width:640px) {"):]
    m = m[:m.index("\n}") + 2]
    for regle in (".pp-l { flex-wrap:wrap; }", ".pp-tx { flex:1 1 calc(100% - 26px); }", ".pp-l .pp-st { margin-left:26px; }",
                  ".pp-a { flex-basis:100%; margin-left:26px; }"):
        assert regle in m, regle
    assert not re.search(r"(?<![-\w])(min-)?width:\s*\d{3,}px", bloc)            # aucune largeur fixe de 100 px et plus
    assert ".siret-seul-l .inp { flex:1 1 160px; min-width:0; }" in bloc


def test_icones_nouvelles_existent_dans_lucide_et_suivent_les_regles():
    lucide = (STATIC / "vendor" / "lucide-1.20.0.min.js").read_text(encoding="utf-8")
    noms = set(re.findall(r'ic: "([a-z0-9-]+)"', _PP))
    noms |= set(re.findall(r'data-lucide="([a-z0-9-]+)"', zone(HTML, "accueil-premiers-pas") + zone(HTML, "fenetre-siret")
                           + zone(HTML, "ecran-confirmation-email")))
    assert {"sliders-horizontal", "folder-kanban", "folder-open", "handshake", "library", "user-plus", "id-card",
            "book-open", "rocket", "mail", "refresh-cw", "building-2"} <= noms
    for n in noms:
        assert re.search(r"\b" + "".join(x.capitalize() for x in n.split("-")) + r"\b", lucide), n
    # Règle 5 : sparkles réservé aux actions de l'IA ; « Inviter un partenaire » seul porte user-plus.
    assert "sparkles" not in noms
    assert 'label: "Inviter un partenaire", ic: "user-plus"' in _PP


# ═══ Migration c5priseenmain (SQLite ; Postgres : script de la session, docs/REORGANISATION_V2B.md) ════════════════

def test_migration_prise_en_main_aller_retour_idempotente(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "pem.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def cols(table):
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            return {c["name"]: c for c in sa.inspect(eng).get_columns(table)}
        finally:
            eng.dispose()

    def sql(q):
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            with eng.begin() as c:
                res = c.execute(sa.text(q))
                return res.fetchall() if res.returns_rows else None
        finally:
            eng.dispose()

    # L'état de la production : la tête c4montantseul, sans les colonnes (sur une base neuve, la réconciliation
    # b7d9e1f3a2c4 les pose déjà à partir du modèle actuel ; le retour arrière les retire).
    run("upgrade", "head")
    run("downgrade", "c4montantseul")
    assert "premiers_pas_replie" not in cols("users") and "montant_porte_seul_inconnu" not in cols("matching_criteria_ext")
    # Une ligne écrite par le code d'avant (sans les colonnes) : elle prend les valeurs par défaut, rien d'inventé.
    sql("INSERT INTO users (email, hashed_password, full_name) VALUES ('avant@test.fr', 'x', 'Avant')")
    sql("INSERT INTO matching_criteria_ext (user_id) VALUES ((SELECT id FROM users WHERE email='avant@test.fr'))")
    run("upgrade", "head")
    u, m = cols("users"), cols("matching_criteria_ext")
    assert {"premiers_pas_replie", "suggestion_reseau"} <= set(u) and "montant_porte_seul_inconnu" in m
    # Mêmes définitions que la réconciliation d'une base neuve : NULL permis, la valeur par défaut posée par la base.
    assert u["premiers_pas_replie"]["default"] == "false" and u["suggestion_reseau"]["default"] == "''"
    assert m["montant_porte_seul_inconnu"]["default"] == "false"
    assert sql("SELECT premiers_pas_replie, suggestion_reseau FROM users WHERE email='avant@test.fr'") == [(0, "")]
    assert sql("SELECT montant_porte_seul, montant_porte_seul_inconnu FROM matching_criteria_ext") == [(None, 0)]
    run("downgrade", "c4montantseul")
    assert "premiers_pas_replie" not in cols("users") and "suggestion_reseau" not in cols("users")
    assert "montant_porte_seul_inconnu" not in cols("matching_criteria_ext") and "montant_porte_seul" in cols("matching_criteria_ext")
    assert sql("SELECT email FROM users") == [("avant@test.fr",)]                 # rien d'autre ne bouge
    run("upgrade", "head")
    run("stamp", "c4montantseul")
    run("upgrade", "head")                                                       # rejeu forcé : sans effet


def test_une_seule_tete_c5priseenmain_apres_c4montantseul():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    sd = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert sd.get_heads() == ["c5priseenmain"]
    assert sd.get_revision("c5priseenmain").down_revision == "c4montantseul"


def test_contrat_b1_ecrit():
    i = CONTRAT.index("## B1.")
    b1 = CONTRAT[i:]
    for mot in ("c5priseenmain", "/api/prise-en-main", "Pas commencé", "En cours", "Terminé", "Je ne sais pas",
                "/app/exemple", "ecranPret", "décision 12", "Faites-vous trouver", "Lancez votre première recherche"):
        assert mot in b1, mot
