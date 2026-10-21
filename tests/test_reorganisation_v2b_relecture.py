"""
Réorganisation de l'interface — vague 2b, RELECTURE. Contrat : docs/REORGANISATION_V2B.md, section S.

Chaque remarque de la relecture, reproduite sur le code réuni (bd61476), corrigée ici, avec le test qui échouait avant :

  S1  cloisonnement : le partenaire ne télécharge que le dossier de l'acheteur (dossier « DCE ») — jamais les formulaires
      officiels (l'acte d'engagement porte le prix de chaque membre), le dossier de présentation ni le tableau de prix
      que le chef de file range dans les autres dossiers du marché (défaut antérieur à la vague 2b) ;
  S2  le courriel d'invitation et le rappel disent ce que reçoit le chef de file (le tableau de prix déposé en fait
      partie) ; l'exemple aussi ;
  S3  la bulle de l'aperçu dit ce que lit un signataire de la convention ;
  S4  un lien en lecture seule : ni « Ma part », ni « Donner mon accord », ni pièces attendues, ni compte à rebours ;
  S5  aucune tâche planifiée n'écrit aux partenaires d'un chef de file dont l'adresse n'est pas confirmée ;
  S6  « Rien n'attend de réponse » seulement après avoir lu les pièces à renouveler et les invitations reçues ;
  S7  la tâche « dossiers » compte les dossiers du compte, comme Mon savoir-faire les liste ;
  S8  « Modifier ma zone » (À venir) mène au champ qui règle la zone de cette recherche ;
  S9  la tâche « Ajouter 3 marchés à Mes marchés » (plus « Suivre », geste absent) ;
  S10 les lignes d'état de « Vos premiers pas » se traduisent (chaque morceau est une clé) ;
  S11 la fenêtre du SIRET contrôle le montant porté seul et dit un refus du serveur ;
  S12 l'exemple ne conclut pas une conformité que ses chiffres n'établissent pas ;
  S13 l'aperçu ne montre ni compte à rebours après la part soumise, ni « quand le chef de file l'aura générée » après
      la convention ;
  S14 (test_reorganisation_v1_relecture.py) le contrôle « 1/1 » ignore les dates ;
  S15 (test_reorganisation_v2b_prise_en_main.py) aria-controls ne désigne jamais une liste absente.

Aucun appel réseau réel (registres simulés, emails coupés) ; les fonctions de app.js sous Node.
"""
import json
import pathlib
import re
import uuid
from datetime import date, timedelta

import pytest

from tests.test_reorganisation_v2b_espace_partenaire import (_apercu, _fonction, _inviter, _methode, _node,
                                                            _soumettre)
from tests.test_reseau_partenaires import _db, _org, _project, mails, reg  # noqa: F401 (fixtures)
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
APERCU = zone(HTML, "vue-apercu-partenaire")
EX = json.loads((STATIC / "exemple-marche.json").read_text(encoding="utf-8"))


def _dict():
    s = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)[1]
    return json.loads(s[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))


def _generer_convention(client, chef, pid, part_chef=120000):
    h = chef["headers"]
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                   json={"forme": "conjoint", "params": {"part_mandataire_ht": part_chef, "lot_mandataire": "Lot 1",
                                                         "mandataire_qualite": "Président"}})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/projects/{pid}/groupement/convention/generer", headers=h, json={})
    assert r.status_code == 200, r.text
    return r.json()


# ═══ S1. Le partenaire ne télécharge que le dossier de l'acheteur ═══════════════════════════════════════════════════

def test_s1_un_sous_traitant_ne_recoit_jamais_le_prix_d_un_autre_membre(client, reg, mails):
    from app.models import Document
    from app.services.dossier import save_to_dossier
    chef = _org(client, "Chef Relecture Cloison")
    pid = _project(client, chef)
    a = _inviter(client, chef, pid, "Partenaire Prix Secret")
    st = _inviter(client, chef, pid, "Sous Traitant Curieux", role="sous_traitant")        # pièces téléchargeables
    _soumettre(client, a["token"], "Partenaire Prix Secret", 283456)
    _soumettre(client, st["token"], "Sous Traitant Curieux", 40000)
    _generer_convention(client, chef, pid)
    # La convention cache au sous-traitant l'annexe des prix (il n'est pas signataire).
    cv = client.get(f"/api/invite/{st['token']}/convention").json()
    assert cv.get("membres") in ([], None) and cv.get("total_offre_ht") is None
    # « Préparer mes documents » range les formulaires officiels dans le dossier « CERFA » du marché ; le chef de file y
    # range aussi son dossier de présentation ; le dossier de l'acheteur est dans « DCE ».
    r = client.post("/api/sourcing/documents", headers=chef["headers"], json={"project_id": pid})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        save_to_dossier(db, chef["id"], pid, "DCE", "RC.pdf", b"%PDF-1.4\n% Reglement de la consultation\n%%EOF")
        save_to_dossier(db, chef["id"], pid, "Mémoire technique", "Dossier de présentation.pdf",
                        b"%PDF-1.4\n% savoir-faire du chef de file\n%%EOF")
        hors_dce = [(d.id, d.name) for d in db.query(Document).filter(Document.project_id == pid,
                                                                       Document.folder != "DCE").all()]
        # La prémisse : l'acte d'engagement rangé par le chef de file porte le prix de vente du partenaire.
        import io
        from pypdf import PdfReader
        from app.services.storage import get_storage
        attri = db.query(Document).filter(Document.project_id == pid, Document.name == "ATTRI1.pdf").one()
        texte = " ".join(" ".join((pg.extract_text() or "") for pg in PdfReader(
            io.BytesIO(get_storage().load(attri.file_key))).pages).split())
        assert "283 456" in texte or "283456" in texte
        dce = [d.id for d in db.query(Document).filter(Document.project_id == pid, Document.folder == "DCE").all()]
    finally:
        db.close()
    assert any(n == "ATTRI1.pdf" for _i, n in hors_dce) and len(dce) == 1
    for jeton in (st["token"], a["token"]):
        vue = client.get(f"/api/invite/{jeton}").json()
        assert [(d["name"], d["folder"]) for d in vue["documents"]] == [("RC.pdf", "DCE")]
        for i, nom in hors_dce:                          # ni listé, ni téléchargeable (même en devinant le numéro)
            assert client.get(f"/api/invite/{jeton}/doc/{i}").status_code == 404, nom
        rr = client.get(f"/api/invite/{jeton}/doc/{dce[0]}")
        assert rr.status_code == 200 and b"Reglement de la consultation" in rr.content
        assert b"283" not in rr.content
    # L'aperçu du chef de file liste ce que le partenaire reçoit : le dossier de l'acheteur, rien d'autre.
    ap = _apercu(client, chef, pid, invite_id=st["id"])
    assert ap["vue"]["documents"] == [{"name": "RC.pdf", "folder": "DCE"}]
    assert _apercu(client, chef, pid, role="sous_traitant", nom="X")["vue"]["documents"] == [{"name": "RC.pdf",
                                                                                              "folder": "DCE"}]


def test_s1_les_libelles_disent_ce_qui_part():
    assert "<span>Dossier du marché téléchargeable</span>" in zone(HTML, "apercu-choix")
    assert "Pièces du marché téléchargeables" not in HTML
    f = zone(HTML, "fenetre-invitation")
    assert '<label for="rinv-docs">Autoriser le téléchargement du dossier du marché</label>' in f
    d = _dict()
    for k in ("Dossier du marché téléchargeable", "Autoriser le téléchargement du dossier du marché"):
        assert d["nl"].get(k) and d["es"].get(k), k
    src = (ROOT / "app" / "routers" / "invites.py").read_text(encoding="utf-8")
    assert 'DOSSIER_PARTAGE = "DCE"' in src
    for f in ("_documents_partages", "guest_download"):
        corps = src[src.index(f"def {f}("):]
        corps = corps[:corps.index("\n\n\n")]
        assert "Document.folder == DOSSIER_PARTAGE" in corps, f


# ═══ S2. Le courriel dit ce que reçoit le chef de file ═══════════════════════════════════════════════════════════════

def test_s2_le_courriel_et_le_rappel_disent_que_le_tableau_de_prix_part_au_chef_de_file(client, reg, mails):
    from app.services.email_invitation import invitation, rappel_part
    phrase = ("Votre chiffrage détaillé (coûts, marges, méthode) reste chez vous : Chef Sonde DPGF reçoit le prix de "
              "vente de votre partie et, si vous le déposez, votre tableau de prix de vente.")
    for c in (invitation(chef="Chef Sonde DPGF", marche="M", url="http://x/invite/t"),
              invitation(chef="Chef Sonde DPGF", marche="M", url="http://x/invite/t", relance=True),
              rappel_part(chef="Chef Sonde DPGF", marche="M", url="http://x/invite/t", date_limite=date.today(),
                          jours_restants=2)):
        assert phrase in c["texte"] and "pas son détail" not in c["texte"] + c["html"]
        assert "tableau de prix de vente" in c["html"]
    # Ce que dit la phrase : le tableau de prix déposé par le partenaire, le chef de file le télécharge.
    chef = _org(client, "Chef Sonde DPGF")
    pid = _project(client, chef)
    a = _inviter(client, chef, pid, "Partenaire DPGF")
    _soumettre(client, a["token"], "Partenaire DPGF", 280000)
    contenu = "Poste;Quantité;Prix unitaire HT;Total HT\nDépose amiante;120 m2;145,50;17460\n".encode("utf-8")
    r = client.post(f"/api/invite/{a['token']}/contribution/piece", data={"piece_type": "dpgf_lot"},
                    files={"file": ("tableau-de-prix.csv", contenu, "text/csv")})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/projects/{pid}/contribution-pieces/{r.json()['id']}", headers=chef["headers"])
    assert r.status_code == 200 and b"145,50" in r.content
    # L'exemple dit la même chose.
    c0 = EX["preparer"]["cloisonnement"][0]
    assert "jamais le détail de ses postes" not in c0 and "tableau de prix de vente" in c0
    assert "jamais le détail de ses coûts ni de ses marges" in c0
    # Et l'écran du partenaire de l'exemple, sous « Votre prix » : le chiffrage détaillé, pas « le détail de vos postes ».
    ecran = zone(HTML, "exemple-partenaire")
    assert "Le détail de votre chiffrage (coûts, marges, méthode), vous seul le voyez." in ecran
    assert "Le détail de vos postes, vous seul le voyez." not in HTML


# ═══ S3. La bulle de l'aperçu dit ce que lit un signataire ══════════════════════════════════════════════════════════

def test_s3_la_bulle_de_l_apercu_dit_ce_que_lit_un_signataire(client, reg, mails):
    tip = APERCU[APERCU.index('<span class="tip-b" role="tooltip">'):]
    tip = tip[:tip.index("</span>")]
    assert "ni la part des autres partenaires" not in tip
    assert ("Une fois la convention générée, chaque membre qui la signe y lit la partie et le prix de vente de chacun, "
            "et le total.") in tip
    d = _dict()
    k = tip[len('<span class="tip-b" role="tooltip">'):]
    assert d["nl"].get(k) and d["es"].get(k)
    # Ce que la bulle annonce, sur l'API : chaque signataire lit la partie et le prix de chacun ; un sous-traitant, rien.
    chef = _org(client, "Chef Bulle Apercu")
    pid = _project(client, chef)
    a = _inviter(client, chef, pid, "Partenaire A Bulle")
    b = _inviter(client, chef, pid, "Partenaire B Bulle")
    st = _inviter(client, chef, pid, "Sous-traitant Bulle", role="sous_traitant")
    _soumettre(client, a["token"], "Partenaire A Bulle", 280000)
    _soumettre(client, b["token"], "Partenaire B Bulle", 91234)
    _soumettre(client, st["token"], "Sous-traitant Bulle", 15000)
    _generer_convention(client, chef, pid)
    for jeton in (a["token"], b["token"]):
        vue = client.get(f"/api/invite/{jeton}/convention").json()
        prix = {m["company"]: m["prix_lot_ht"] for m in vue["membres"]}
        assert prix == {"Chef Bulle Apercu": 120000.0, "Partenaire A Bulle": 280000.0, "Partenaire B Bulle": 91234.0}
        assert all(m.get("lot") for m in vue["membres"])
    assert client.get(f"/api/invite/{st['token']}/convention").json().get("membres") in ([], None)


# ═══ S4. Un lien en lecture seule : aucune tâche qu'il ne peut pas faire ════════════════════════════════════════════

def test_s4_un_lien_en_lecture_seule_n_a_ni_part_ni_accord_ni_pieces_attendues(client, reg, mails):
    chef = _org(client, "Chef Lecture Seule")
    pid = _project(client, chef)
    ro = _inviter(client, chef, pid, "Lecture Seule RO", can_contribute=False)
    ap = _apercu(client, chef, pid, invite_id=ro["id"])
    assert ap["vue"]["can_contribute"] is False and ap["pieces_attendues"] is None
    assert _apercu(client, chef, pid, can_contribute="false", nom="X")["pieces_attendues"] is None
    assert _apercu(client, chef, pid, nom="X")["pieces_attendues"]                 # une part : ses pièces, toujours
    # Il ne peut ni déposer ni soumettre : c'est pourquoi l'écran ne lui demande ni part ni accord.
    assert client.put(f"/api/invite/{ro['token']}/contribution", json={"company_name": "x", "version": 0}).status_code == 403
    for src in (JS, INV):
        r = _node(_fonction(src, "barrePartenaire") + """
console.log(JSON.stringify([barrePartenaire({ part: false }).map(s => s.k),
                            barrePartenaire({ part: false, role: "sous_traitant" }).map(s => s.k)]));""")
        assert r == [["accepter", "depose"], ["accepter", "depose"]]
    # L'aperçu : « Votre accord » seulement s'il a l'étape ; une ligne qui dit la lecture seule ; pas de compte à rebours.
    att = zone(HTML, "apercu-attendu")
    assert "<li v-if=\"apercuEtape('accord')\">" in att and "Ce lien est en lecture seule : aucune part à renseigner ni convention à valider." in att
    assert 'v-if="apercuDelaiVisible(v)"' in APERCU and 'v-if="paJours(v.project.deadline) !== null"' not in APERCU
    assert "if (p.deadline && d.can_contribute) {" in INV              # son écran : pas de compte à rebours non plus
    d = _dict()
    for k in ("Ce lien est en lecture seule : aucune part à renseigner ni convention à valider.",
              "Votre accord sur la convention de groupement."):
        assert d["nl"].get(k) and d["es"].get(k), k


# ═══ S5. Rien n'est écrit aux partenaires d'un chef de file sans adresse confirmée ═══════════════════════════════════

def _compte(client, verifie):
    from app.core.database import SessionLocal
    from app.models import User
    email = f"rl_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                               "full_name": "Dirigeant Test", "company_name": "Test SARL"})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == email).first().email_verified = verifie
        db.commit()
    finally:
        db.close()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.mark.parametrize("verifie", [False, True])
def test_s5_le_rappel_planifie_ne_part_que_d_un_compte_confirme(client, monkeypatch, verifie):
    import app.services.alerts as alerts
    from app.core.database import SessionLocal
    h = _compte(client, verifie)
    r = client.post("/api/projects/", headers=h, json={"name": "Marché relecture", "client": "Ville X",
                                                      "deadline": (date.today() + timedelta(days=2)).isoformat()})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    cible = f"cible_{uuid.uuid4().hex[:6]}@exemple.org"
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Cible SARL", "recipient": cible})
    assert r.status_code == 200 and r.json()["emailed"] is False              # le lien, pas de courriel (inchangé)
    envoyes = []
    monkeypatch.setattr(alerts, "send_email",
                        lambda to, subj, text, html=None, **k: envoyes.append((to, subj, text, html)) or True)
    db = SessionLocal()
    try:
        alerts.run_cotraitance_reminders(db)
    finally:
        db.close()
    au_tiers = [x for x in envoyes if x[0] == cible]
    if verifie:   # le témoin : un compte confirmé, le rappel part, avec le lien et les attestations à fournir (un seul)
        assert len(au_tiers) == 1 and au_tiers[0][1].startswith("Rappel") and "/invite/" in au_tiers[0][2]
        assert "Vos attestations sont aussi à mettre à jour" in au_tiers[0][2]
    else:         # jamais le lien, ni rien d'autre, vers un tiers depuis un compte non confirmé
        assert au_tiers == []


def test_s5_le_commentaire_d_auth_py_reste_vrai():
    src = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    i = src.index("    # Email de confirmation. Choix du 24/06, gardé")
    c = re.sub(r"\s*\n\s*#\s*", " ", src[i:src.index("    _send_verification(user)", i)])
    assert "ni le rappel planifié de la part ni l'alerte d'attestations à ses partenaires" in c
    a = (ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8")
    assert a.count("_comptes_non_confirmes(db)") == 2


# ═══ S6. « Rien n'attend de réponse » seulement une fois tout lu ════════════════════════════════════════════════════

def test_s6_l_ecran_s_ouvre_apres_avoir_lu_les_pieces_et_les_invitations_sous_node():
    boot = _methode("boot")
    script = "const o = {\n" + boot + "\n" + _methode("loadExpiring") + "\n" + _methode("rnLoadRecues") + "\n};\n" + r"""
global.localStorage = { setItem() {}, getItem() { return null; } };
global.sessionStorage = { getItem() { return null; }, removeItem() {} };
global.history = { state: null, replaceState() {} };
global.location = { search: "" };
global.etatDeAdresse = () => ({ view: "dashboard" });
global.clePartage = t => t;
const lus = { expiring: false, recues: false };
const tard = (v, k) => new Promise(res => setTimeout(() => { if (k) lus[k] = true; res(v); }, 30));
Object.assign(o, {
  token: "t", expiring: [], expiringLu: false, shared: [], org: {}, reseau: { recues: { loading: false, loaded: false, list: [] } },
  api: (m, p) => p === "/api/auth/me" ? Promise.resolve({ id: 1 })
    : p === "/api/documents/expiring" ? tard([{ name: "URSSAF", expiration_date: "2026-11-01" }], "expiring")
    : p === "/api/reseau/invitations" ? tard({ invitations: [] }, "recues") : Promise.resolve({}),
  notify() {}, applyLang() {}, _adresseDemandee() { return "/app"; }, _rnSuggest() {},
  _ouvrirAdresse() { this.aOuvert = Object.assign({}, lus); }, _adresseAttente: false,
});
for (const k of ["loadCompany", "loadCriteria", "loadProjects", "loadCotraitants", "loadStats", "loadOrg",
                 "loadAdaptedCountries", "loadAmont", "loadNotifs", "loadConsortiums", "loadShared", "loadGrpDash",
                 "loadPriseEnMain"]) o[k] = () => Promise.resolve();
let pret = null;
Object.defineProperty(o, "ecranPret", { set(v) { if (v && !pret) pret = Object.assign({}, lus); }, get() { return !!pret; } });
o.boot().then(() => setTimeout(() => console.log(JSON.stringify({ pret, ouvert: o.aOuvert, lu: o.expiringLu,
  recues: o.reseau.recues.loaded })), 60));
"""
    r = _node(script)
    # L'écran (l'accueil et son « À faire ») ne s'ouvre qu'une fois lues les deux listes qu'il affiche.
    assert r["ouvert"] == {"expiring": True, "recues": True} and r["pret"] == {"expiring": True, "recues": True}
    assert r["lu"] is True and r["recues"] is True


def test_s6_la_phrase_vide_attend_la_lecture_sous_node():
    for z in ("accueil-a-faire", "fenetre-notifications"):
        assert "!aFaire().length && aFaireLu()" in zone(HTML, z), z
    r = _node("const o = {\n" + _methode("aFaireLu") + "\n" + _methode("loadExpiring") + r"""
};
(async () => {
  const res = [];
  Object.assign(o, { expiring: [], expiringLu: false, reseau: { recues: { loaded: false } } });
  res.push(o.aFaireLu());
  o.api = async () => { throw new Error("réseau"); }; await o.loadExpiring(); o.reseau.recues.loaded = true;
  res.push(o.aFaireLu());                                     // la liste des pièces n'a pas pu être lue : pas de phrase
  o.api = async () => []; await o.loadExpiring();
  res.push(o.aFaireLu());
  console.log(JSON.stringify(res));
})();
""")
    assert r == [False, False, True]


# ═══ S7. La tâche « dossiers » compte ceux du compte, comme Mon savoir-faire ════════════════════════════════════════

def test_s7_un_collegue_ne_lit_pas_trois_sur_trois_devant_un_ecran_vide(client):
    owner = _compte(client, True)
    email = f"rlm_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=owner, json={"email": email, "full_name": "Collègue"})
    assert r.status_code == 201, r.text
    lr = client.post("/api/auth/login", json={"email": email, "password": r.json()["temp_password"]})
    m = {"Authorization": "Bearer " + lr.json()["access_token"]}
    texte = "Mémoire technique : méthodologie de chantier, moyens humains, références de travaux de couverture. " * 3
    for i in range(3):
        assert client.post("/api/knowledge/text", headers=owner,
                           json={"name": f"Dossier {i}", "text": texte, "kind": "memoire"}).status_code == 200

    def tache(h):
        pp = client.get("/api/prise-en-main", headers=h).json()["premiers_pas"]
        return next(t for t in pp["taches"] if t["k"] == "dossiers")
    assert client.get("/api/knowledge/", headers=m).json()["total_docs"] == 0
    assert tache(m) == {"k": "dossiers", "statut": "pas_commence", "fait": 0, "sur": 3}
    assert client.get("/api/knowledge/", headers=owner).json()["total_docs"] == 3
    assert tache(owner) == {"k": "dossiers", "statut": "termine", "fait": 3, "sur": 3}


# ═══ S8. « Modifier ma zone » mène au champ qui règle la zone de la recherche ════════════════════════════════════════

def test_s8_modifier_ma_zone_met_le_focus_sur_les_departements_de_l_onglet_sous_node():
    radar = zone(HTML, "trouver-radar")
    assert '<button type="button" class="linkbtn small" @click="srcRenZone()">Modifier ma zone</button>' in radar
    assert "go('criteria')" not in radar
    assert '<input ref="srcRenDep" class="inp" v-model="src.dept"' in radar
    # La recherche des fins de contrat n'envoie que ce champ (jamais la zone de « Ce que je cherche »).
    assert "departements: this.srcDeps()" in _methode("srcRenewals") and "this.src.dept" in _methode("srcDeps")
    r = _node("const o = {\n" + _methode("srcRenZone") + r"""
};
const j = [];
o.$refs = { srcRenDep: { focus() { j.push("focus"); }, select() { j.push("select"); } } };
o.srcRenZone(); o.$refs = {}; o.srcRenZone();
console.log(JSON.stringify(j));
""")
    assert r == ["focus", "select"]


# ═══ S9. La tâche nomme un geste qui existe ═════════════════════════════════════════════════════════════════════════

def test_s9_la_tache_des_marches_nomme_un_geste_en_ligne():
    i = JS.index("const PP_TACHES = {")
    taches = JS[i:JS.index("};", i)]
    assert 'titre: "Ajouter 3 marchés à Mes marchés"' in taches and '"Suivre 3 marchés"' not in taches
    # Aucune commande « Suivre » dans l'application : une carte de recherche propose « Analyser ce marché ».
    assert not re.search(r">\s*Suivre\b", HTML) and "Analyser ce marché" in zone(HTML, "vue-sourcing")
    d = _dict()
    assert d["nl"].get("Ajouter 3 marchés à Mes marchés") and d["es"].get("Ajouter 3 marchés à Mes marchés")


# ═══ S10. Les lignes d'état de « Vos premiers pas » se traduisent ═══════════════════════════════════════════════════

def test_s10_chaque_morceau_des_lignes_d_etat_est_une_cle_sous_node():
    i = JS.index("const PP_STATUTS")
    pur = JS[i:JS.index("// Confirmation d'email vivante", i)]
    combis = [[], ["metier"], ["zone"], ["montant"], ["metier", "zone"], ["metier", "montant"], ["zone", "montant"],
              ["metier", "zone", "montant"]]
    taches = [{"k": "dire", "statut": "en_cours" if 0 < 3 - len(m) < 3 else ("termine" if not m else "pas_commence"),
               "fait": 3 - len(m), "sur": 3, "manque": m} for m in combis]
    taches += [{"k": k, "statut": ("termine" if n == 3 else "en_cours" if n else "pas_commence"), "fait": n, "sur": 3}
               for k in ("suivre", "dossiers") for n in range(4)]
    r = _node(pur + "\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(t => tachePremiersPas(t, 1))))",
              json.dumps(taches))
    d = _dict()
    assert len(r) == 16
    for t in r:
        assert "".join(t["morceaux"]) == t["detail"] and t["detail"]
        for m in t["morceaux"]:
            k = m.strip()
            if re.fullmatch(r"[\d.,]+", k):
                continue                                 # un nombre ou une ponctuation reste tel quel
            assert d["nl"].get(k) and d["es"].get(k), (t["k"], k)
    # Le gabarit rend chaque morceau dans son élément (accueil, rappel de « Ce que je cherche »), et le compte du bloc.
    pp = zone(HTML, "accueil-premiers-pas")
    assert 'v-for="(m,mi) in t.morceaux"' in pp and "{{ t.detail }}" not in pp
    assert "<span>{{ pp.d.n_terminees }}</span> <span>sur</span> <span>{{ pp.d.n_total }}</span>" in pp
    assert "v-for=\"(m,mi) in ppRappel('dire').morceaux\"" in zone(HTML, "vue-criteria")
    assert d["nl"]["sur"] == "van" and d["es"]["sur"] == "de"


# ═══ S11. La fenêtre du SIRET contrôle le montant et dit un refus ═══════════════════════════════════════════════════

def test_s11_la_borne_du_montant_est_celle_du_serveur():
    from app.routers.criteria_v2 import MONTANT_SEUL_MAX
    assert f"const MONTANT_SEUL_MAX = {MONTANT_SEUL_MAX};" in JS
    assert f'type="number" min="0" max="{MONTANT_SEUL_MAX}" step="1000" v-model.number="welcome.seul"' in zone(HTML, "fenetre-siret")
    d = _dict()
    m = re.search(r'const MSG_MONTANT_SEUL = "([^"]+)";', JS).group(1)
    assert d["nl"].get(m) and d["es"].get(m)


def test_s11_un_montant_trop_grand_ne_fait_plus_perdre_le_metier_et_la_zone_sous_node():
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    r = _node(borne + "const o = {\n" + _methode("welcomeStart") + "\n};\n" + r"""
global.document = { getElementById() { return { focus() {} }; } };
async function cas(seul, refus) {
  const j = { put: [], notes: [], fermee: false };
  Object.assign(o, { welcome: { siret: "12345678900012", busy: false, seul, seulInconnu: false }, company: {},
    criteria: { montant_porte_seul: null, montant_porte_seul_inconnu: false }, src: { query: "", dept: "" },
    notify(t, k) { j.notes.push([t, k || "ok"]); }, go() {}, $nextTick() {}, srcSearch() {},
    welcomeDone() { j.fermee = true; }, loadPriseEnMain() {},
    api: async (m, p, b) => {
      if (p.startsWith("/api/registre")) return { name: "Couvreurs", siret: "12345678900012", postal_code: "29200", specialite: "Couverture" };
      if (p === "/api/criteria/") { j.put.push(JSON.parse(JSON.stringify(b))); if (refus) throw new Error(refus); }
      return {};
    } });
  await o.welcomeStart();
  return j;
}
(async () => {
  console.log(JSON.stringify({ grand: await cas(20000000000), negatif: await cas(-5), ok: await cas(150000),
                               refus: await cas(150000, "Refus du serveur") }));
})();
""")
    for k in ("grand", "negatif"):           # la fenêtre reste ouverte, rien n'est envoyé, le message le dit
        assert r[k]["put"] == [] and r[k]["fermee"] is False
        assert r[k]["notes"] == [["Le montant que vous portez seul est un montant positif, en euros HT, jusqu'à 10 milliards.", "err"]]
    assert r["ok"]["put"][0]["montant_porte_seul"] == 150000 and r["ok"]["put"][0]["specialites"] == "Couverture"
    assert r["ok"]["notes"] == [["Profil créé depuis votre SIRET", "ok"]] and r["ok"]["fermee"] is True
    # Un refus du serveur n'est plus avalé : l'écran dit ce qui n'a pas été enregistré.
    assert r["refus"]["notes"][-1][1] == "err" and "n'ont pas été enregistrés : Refus du serveur" in r["refus"]["notes"][-1][0]


# ═══ S12. L'exemple ne conclut pas une conformité qu'il n'établit pas ═══════════════════════════════════════════════

def test_s12_le_chiffre_d_affaires_de_l_exemple_dit_ce_qu_il_sait():
    dec = EX["decider"]
    cumul = dec["cumul"]
    assert "1 250 000 € + 2 100 000 € = 3 350 000 €" in cumul and "au dernier exercice" in cumul
    assert "au-dessus" not in cumul and "reste à confirmer" in cumul and "moyenne sur trois exercices" in cumul
    ca = next(g for g in dec["manques"] if g["key"] == "capacite")
    assert "en moyenne sur 3 ans" in ca["exige"] and ca["a"] == "1 250 000 € au dernier exercice"
    # La présentation du partenaire cite ses deux qualifications, celles du calcul et de la démonstration.
    pres = EX["partenaire"]["presentation"]
    assert "Qualification désamiantage SS3" in pres and "certification amiante sous-section 3" in pres
    assert [q.lower() for q in EX["calcul"]["partenaire"]["qualifications"]] == [
        "qualification désamiantage ss3", "certification amiante sous-section 3"]
    assert dec["seul"] == 43 and dec["a_plusieurs"] == 100           # les pourcentages ne changent pas


# ═══ S13. L'aperçu suit l'état réel de sa part et de la convention ══════════════════════════════════════════════════

_APERCU_METHODES = ("apercuBarre", "apercuEtape", "apercuConventionGeneree", "apercuDelaiVisible", "paJours")


def _apercu_sous_node(ap):
    script = (_fonction(JS, "barrePartenaire") + "\nconst o = {\n" + "\n".join(_methode(m) for m in _APERCU_METHODES)
              + "\n};\n" + r"""
o.apercu = { d: JSON.parse(process.argv[1]) };
const v = o.apercu.d.vue;
console.log(JSON.stringify({ delai: o.apercuDelaiVisible(v), generee: o.apercuConventionGeneree(),
                             part: o.apercuEtape("part"), accord: o.apercuEtape("accord") }));
""")
    return _node(script, json.dumps(ap))


def test_s13_part_soumise_et_convention_validee_sous_node(client, reg, mails):
    chef = _org(client, "Chef Apercu Etat")
    pid = _project(client, chef)
    a = _inviter(client, chef, pid, "Partenaire Apercu Etat")
    avant = _apercu_sous_node(_apercu(client, chef, pid, invite_id=a["id"]))
    assert avant["delai"] is True and avant["generee"] is False
    assert avant["part"]["statut"] == "En cours" and avant["accord"]["statut"] == "À faire"
    _soumettre(client, a["token"], "Partenaire Apercu Etat", 280000)
    soumise = _apercu_sous_node(_apercu(client, chef, pid, invite_id=a["id"]))
    assert soumise["delai"] is False                         # comme son écran : plus de « pour soumettre votre part »
    assert soumise["part"] == dict(soumise["part"], statut="Terminé", pill="go")
    _generer_convention(client, chef, pid)
    generee = _apercu_sous_node(_apercu(client, chef, pid, invite_id=a["id"]))
    assert generee["generee"] is True and generee["accord"]["statut"] == "En cours"
    # Le gabarit : le texte « quand le chef de file l'aura générée » seulement avant la génération ; chaque tâche porte
    # le statut de son étape.
    att = zone(HTML, "apercu-attendu")
    assert ('<span v-if="apercuConventionGeneree()">Votre accord sur la convention de groupement.</span><span v-else>Votre '
            "accord sur la convention de groupement, quand le chef de file l'aura générée.</span>") in att
    assert att.count('class="pill pa-att-st"') == 2
    for m in ("apercuConventionGeneree", "apercuDelaiVisible"):
        corps = _methode(m)
        assert "this.ao" not in corps and "this.apercu.d" in corps, m
    assert "this.apercuBarre()" in _methode("apercuEtape")


def test_s13_la_demonstration_de_kerhel_sous_node(client):
    """La vitrine : l'aperçu de Breizh Désamiantage (part soumise, convention validée) ne dit ni « Il vous reste … pour
    soumettre votre part » ni « quand le chef de file l'aura générée »."""
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        kerhel = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        pid, iid = kerhel.id, db.query(ProjectInvite).filter(ProjectInvite.project_id == kerhel.id).first().id
    finally:
        db.close()
    h = {"Authorization": "Bearer " + client.post("/api/auth/demo", json=None).json()["access_token"]}
    ap = client.get(f"/api/projects/{pid}/apercu-partenaire", headers=h, params={"invite_id": iid}).json()
    assert ap["etat"]["part"] == "submitted" and ap["etat"]["convention"] in ("signee", "a_signer")
    r = _apercu_sous_node(ap)
    assert r["delai"] is False and r["generee"] is True
    assert r["part"]["statut"] == "Terminé" and r["accord"]["statut"] == "Terminé"
    # Les pièces partagées de Kerhel : le dossier de l'acheteur, comme avant (S1 n'enlève rien à la démonstration).
    assert [d["folder"] for d in ap["vue"]["documents"]] == ["DCE"]


# ═══ Le contrat ══════════════════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_section_s_de_la_relecture():
    doc = (ROOT / "docs" / "REORGANISATION_V2B.md").read_text(encoding="utf-8")
    s = doc[doc.index("## S. Relecture"):]
    for n in range(1, 16):
        assert f"### S.{n} " in s or f"| S{n} " in s, n
    assert "test_reorganisation_v2b_relecture.py" in s
    # B3.10 ne dit plus que le compte à rebours reste après la part soumise ; B4.2 dit la phrase nouvelle.
    b3 = doc[doc.index("### B3.10"):doc.index("## B4.")]
    assert "reste affiché une fois la part soumise" not in b3
    b4 = doc[doc.index("### B4.2"):doc.index("### B4.3")]
    assert "pas son détail" not in b4 and "tableau de prix" in b4
