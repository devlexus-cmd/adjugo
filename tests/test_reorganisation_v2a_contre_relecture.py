"""
Réorganisation de l'interface — vague 2a, contre-relecture (contrat : docs/REORGANISATION_V2A.md, section M).

Les trois remarques de la contre-relecture, chacune reproduite par un test qui échouait sur 238f6e0 :
1. Une pièce exigée reconnue sous son nom (correction R6 de la relecture) : jamais par une pièce d'un autre numéro ou
   d'une autre lettre (« DC 4 » par DC1.pdf, « ATTRI2 » par ATTRI1.pdf, « Annexe 4 » par « Annexe 1 », « Annexe A »
   par « Annexe B »), jamais par un fichier du dossier de l'acheteur (dossier « DCE » : « CCAP signé » par CCAP.pdf) ;
   la carte « Pièces à fournir » et « Prêt à déposer » d'une entreprise seule le disent (remarques 1 et 3).
2. Précédent du navigateur avec une fenêtre ouverte (correction R1 de la relecture) : le menu du téléphone (barre
   basse, « Menu ») et les fenêtres hors de Vue (cotraitance-crypto.js : « Vérifiez votre identité », code de
   récupération ; redaction-partenaire.js : ses confirmations) se ferment aussi, l'écran reste ; un dossier partagé
   quitté pendant qu'une de ces fenêtres était ouverte ne reçoit jamais ce qui était destiné à un autre (remarque 2).

Aucun appel réseau : routes de l'API locale, fichiers de app/static exécutés sous Node, base SQLite des tests.
"""
import json
import pathlib
import re
from types import SimpleNamespace

from tests.test_reorganisation_v2a_adresses_etapes import _node
from tests.test_reorganisation_v2a_relecture import _FENETRES, _naviguer
from tests.test_reorganisation_v2a_reunion import _methode
from tests.test_reseau_partenaires import _db, _org, _project, mails, reg  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CRYPTO = STATIC / "cotraitance-crypto.js"
REDACTION = STATIC / "redaction-partenaire.js"
CONTRAT = (ROOT / "docs" / "REORGANISATION_V2A.md").read_text(encoding="utf-8")


# ═══ 1. Une pièce exigée reconnue sous son nom, jamais sous celui d'une autre (remarques 1 et 3) ════════════════

def _doc(nom, folder=None):
    return SimpleNamespace(id=hash(nom) % 10000, name=nom, category="autre", expiration_date=None, folder=folder)


AUTRE_PIECE = (
    ("DC 4", "DC1.pdf"), ("DC 4", "DC2.pdf"), ("ATTRI2", "ATTRI1.pdf"), ("Formulaire ATTRI 2", "ATTRI1.pdf"),
    ("Annexe 4", "Annexe 1.pdf"), ("Annexe 2 au CCAP", "Annexe 1 au CCAP.pdf"),
    ("Annexe 1 - Cadre de réponse technique", "Annexe 2 - Cadre de réponse technique"),
    ("Annexe 1", "Annexe 12.pdf"), ("Attestation de visite n° 2", "Attestation de visite n° 1"),
    ("Annexe A", "Annexe B.pdf"), ("Annexe A", "Annexe B à compléter.pdf"), ("Annexe A", "Annexe.pdf"),
    ("Lot A - Cadre de réponse", "Lot B - Cadre de réponse.pdf"), ("Partie B : moyens", "Partie C : moyens.pdf"),
    ("Annexe à la convention n° 3", "Annexe à la convention n° 2.pdf"),
)
MEME_PIECE = (
    ("DC 4", "DC4.pdf"), ("ATTRI2", "ATTRI 2.pdf"), ("Annexe 4", "Annexe 4.pdf"), ("Annexe 4", "annexe_4 signée.pdf"),
    ("Annexe 2 au CCAP", "Annexe 2 au CCAP.pdf"), ("Attestation de visite n° 2", "Attestation de visite n°2.pdf"),
    ("Annexe 1 - Cadre de réponse technique", "Annexe 1 - Cadre de réponse technique.docx"),
    ("Annexe A", "Annexe A.pdf"), ("Annexe A", "ANNEXE_A.pdf"), ("Annexe A", "Annexes A et B.pdf"),
    ("Lot B - Cadre de réponse", "Cadre de réponse lot B.pdf"), ("Pièce d'identité du gérant", "Pièce identité gérant.pdf"),
    ("Annexe à la convention n° 3", "Annexe à la convention n°3.pdf"),
)


def test_une_piece_n_est_jamais_reconnue_par_une_autre_d_un_autre_numero_ou_d_une_autre_lettre():
    from app.routers.checklist import match_document
    faux = [(p, n) for p, n in AUTRE_PIECE if match_document(p, [_doc(n)])["found"]]
    assert not faux, faux
    manques = [(p, n) for p, n in MEME_PIECE if not match_document(p, [_doc(n)])["found"]]
    assert not manques, manques


def test_un_fichier_du_dossier_de_l_acheteur_ne_vaut_jamais_une_piece_par_ses_mots():
    from app.routers.checklist import match_document
    # Le dossier « DCE » range le dossier de l'acheteur, importé par l'entreprise : jamais une de ses pièces.
    for piece, nom in (("CCAP signé", "CCAP.pdf"), ("Cahier des clauses techniques particulières (CCTP) signé",
                                                    "Cahier des clauses techniques particulières (CCTP).pdf"),
                       ("Attestation de visite obligatoire", "Attestation de visite obligatoire.pdf")):
        assert match_document(piece, [_doc(nom, folder="DCE")])["found"] is False, (piece, nom)
        # Le même nom déposé par l'entreprise dans Mes documents ou dans un autre dossier du marché : reconnu.
        assert match_document(piece, [_doc(nom)])["found"] is True, (piece, nom)
        assert match_document(piece, [_doc(nom, folder="Pièces administratives")])["found"] is True, (piece, nom)


def _poser_pieces(pid, pieces):
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        a = dict(p.ai_analysis)
        a["details"] = dict(a["details"], pieces_requises=pieces)
        p.ai_analysis = a
        db.commit()
    finally:
        db.close()


def _deposer(client, h, nom, pid=None):
    data = {"name": nom, "category": "autre"}
    if pid:
        data["project_id"] = str(pid)
    r = client.post("/api/documents/", headers=h, files={"file": (nom + ".pdf", b"%PDF-1.4 x", "application/pdf")},
                    data=data)
    assert r.status_code == 201, r.text


PIECES = ["ATTRI2", "Annexe 4", "Annexe 1 - Cadre de réponse technique", "Attestation de visite n° 2", "CCAP signé"]


def test_la_carte_et_pret_a_deposer_ne_cochent_pas_une_piece_par_une_autre(client):
    """Le cas des deux remarques, par l'API : une entreprise seule passe par « Préparer mes documents » (qui range
    ATTRI1.pdf dans le dossier du marché), dépose « Annexe 1 », « Annexe 2 - … », « … n° 1 », et a importé le CCAP de
    l'acheteur. Aucune des cinq pièces n'est cochée ; chacune l'est quand la bonne pièce arrive."""
    chef = _org(client, "Contre Pièces SARL", extra={"representant_legal": "Jean Test"})
    h = chef["headers"]
    pid = _project(client, chef)
    _poser_pieces(pid, PIECES)
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    for nom in ("Annexe 1", "Annexe 2 - Cadre de réponse technique", "Attestation de visite n° 1"):
        _deposer(client, h, nom, pid)
    from app.models import DocCategory, Document, Project
    db = _db()
    try:
        p = db.get(Project, pid)
        assert db.query(Document).filter(Document.project_id == pid, Document.folder == "CERFA",
                                         Document.name == "ATTRI1.pdf").count() == 1
        db.add(Document(user_id=p.user_id, project_id=pid, folder="DCE", category=DocCategory.autre, name="CCAP.pdf",
                        file_key="x/CCAP.pdf"))
        db.commit()
    finally:
        db.close()

    def lire():
        carte = {i["name"]: (i["status"], i.get("document_name"))
                 for i in client.get(f"/api/checklist/{pid}", headers=h).json()["checklist"]}
        pret = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
        return carte, pret

    carte, pret = lire()
    assert {p: carte[p] for p in PIECES} == {p: ("manquant", None) for p in PIECES}
    manques = pret["manques_par_controle"]["pieces"]
    for p in PIECES:
        assert f"{p} : à ajouter dans Mes documents" in manques, (p, manques)
    assert pret["checks"]["pieces"] is False
    # Les bonnes pièces arrivent : chacune est cochée par la sienne, et seulement elle.
    for nom in ("ATTRI2", "Annexe 4", "Annexe 1 - Cadre de réponse technique", "Attestation de visite n° 2",
                "CCAP signé"):
        _deposer(client, h, nom, pid)
    carte, pret = lire()
    assert {p: carte[p] for p in PIECES} == {p: ("ok", p) for p in PIECES}
    assert not [m for m in pret["manques_par_controle"]["pieces"] if any(p in m for p in PIECES)]


def test_le_contrat_ne_promet_plus_ce_que_le_code_ne_tient_pas():
    # L.6 disait « Jamais sur un seul mot commun » sans les chiffres d'un seul caractère : la section M le corrige.
    m = CONTRAT[CONTRAT.index("## M. Contre-relecture de la vague 2a"):]
    assert "« DC 4 »" in m and "DC1.pdf" in m and "« DCE »" in m and "mobileNav" in m and "fermerFenetres" in m


# ═══ 2. Précédent du navigateur : menu du téléphone et fenêtres hors de Vue (remarque 2) ═══════════════════════

_HORS_VUE = """
const horsVue = { ouvertes: 0, fermees: 0 };
const moduleFenetres = { fenetresOuvertes() { return horsVue.ouvertes; },
  fermerFenetres() { const n = horsVue.ouvertes; horsVue.ouvertes = 0; horsVue.fermees += n; return n > 0; } };
globalThis.window = { AdjugoCrypto: moduleFenetres, AdjugoRedactionPartenaire: moduleFenetres };
Object.assign(o, { mobileNav: false });
"""


def test_precedent_avec_le_menu_du_telephone_ouvert_ne_fait_que_le_fermer():
    r = _naviguer(_FENETRES + _HORS_VUE + """
const res = {};
demarrer(); o.go("pipeline"); vider(); o.openAo(o.projects[0]); vider(); o.go("pipeline"); vider();
o.openAo(o.projects[1]); vider(); res.ouvert = etat();
// Mes marchés, puis « Menu » de la barre basse, puis précédent : le menu se ferme, l'écran reste.
history.back(); vider(); res.liste = etat();
o.mobileNav = true; history.back(); res.b1 = Object.assign(etat(), { menu: o.mobileNav, projet: o.ao.project && o.ao.project.id });
// Plus rien d'ouvert : précédent change d'écran, comme avant.
history.back(); res.b2 = Object.assign(etat(), { projet: o.ao.project && o.ao.project.id });
// Une fenêtre hors de Vue (code de vérification, confirmation de la rédaction) : précédent la ferme, l'écran reste.
horsVue.ouvertes = 2; history.back(); res.b3 = Object.assign(etat(), { horsVue: Object.assign({}, horsVue) });
// Suivant avec une fenêtre hors de Vue ouverte : elle se ferme et l'écran suit l'adresse.
history.back(); res.b4 = etat();
horsVue.ouvertes = 1; history.forward(); res.f1 = Object.assign(etat(), { horsVue: Object.assign({}, horsVue) });
console.log(JSON.stringify(res));
""", ["_surRetourNavigateur", "_fermerFenetres", "rinvClose", "rnCloseFiche"], depart="/app/marches")
    assert r["ouvert"]["urls"] == ["/app/marches", "/app/marches/7", "/app/marches", "/app/marches/9"]
    assert r["liste"]["view"] == "pipeline" and r["liste"]["idx"] == 2
    assert r["b1"]["menu"] is False and r["b1"]["view"] == "pipeline" and r["b1"]["idx"] == 2
    assert r["b2"]["view"] == "aodetail" and r["b2"]["projet"] == 7 and r["b2"]["idx"] == 1
    assert r["b3"]["horsVue"] == {"ouvertes": 0, "fermees": 2} and r["b3"]["view"] == "aodetail" and r["b3"]["idx"] == 1
    assert r["b4"]["view"] == "pipeline" and r["b4"]["idx"] == 0
    assert r["f1"]["horsVue"] == {"ouvertes": 0, "fermees": 3} and r["f1"]["view"] == "aodetail" and r["f1"]["idx"] == 1


_DOM = """
const enfants = [];
function el(tag) {
  const e = { tag, style: {}, dataset: {}, children: [], className: "", textContent: "", innerHTML: "", value: "",
    appendChild(c) { this.children.push(c); return c; }, remove() { const i = enfants.indexOf(this); if (i >= 0) enfants.splice(i, 1); },
    addEventListener() {}, focus() {}, querySelector() { return null; } };
  return e;
}
globalThis.window = globalThis;
globalThis.document = { createElement: el, createTextNode: t => ({ t }), body: { appendChild(c) { enfants.push(c); } },
  getElementById: () => null, activeElement: null };
globalThis.setTimeout = () => 0;
"""


def test_les_fenetres_de_cotraitance_crypto_se_ferment_comme_annuler():
    r = _node(_DOM + "require(" + json.dumps(str(CRYPTO)) + """);
const C = window.AdjugoCrypto;
(async () => {
  const code = C.askRecoveryCode(), otp = C.modal({ title: "Vérifiez votre identité", withInput: true }), note = C.showRecoveryCode("ABCD");
  const avant = { ouvertes: C.fenetresOuvertes(), dom: enfants.length };
  const ferme = C.fermerFenetres();
  const rep = [await code, await otp, await note];
  console.log(JSON.stringify({ avant, ferme, rep, apres: C.fenetresOuvertes(), dom: enfants.length, encore: C.fermerFenetres() }));
})();
""")
    assert r["avant"] == {"ouvertes": 3, "dom": 3} and r["ferme"] is True
    assert r["rep"] == [None, None, None]                     # « Annuler » : aucun code, aucune vérification
    assert r["apres"] == 0 and r["dom"] == 0 and r["encore"] is False


def test_les_confirmations_de_la_redaction_se_ferment_comme_annuler():
    r = _node(_DOM + REDACTION.read_text(encoding="utf-8") + """
const R = window.AdjugoRedactionPartenaire;
(async () => {
  const p = R._modal({ title: "Envoyer votre partie au groupement ?", confirmLabel: "J'ai lu, envoyer" });
  const avant = { ouvertes: R.fenetresOuvertes(), dom: enfants.length };
  const ferme = R.fermerFenetres();
  console.log(JSON.stringify({ avant, ferme, rep: await p, apres: R.fenetresOuvertes(), dom: enfants.length }));
})();
""")
    assert r == {"avant": {"ouvertes": 1, "dom": 1}, "ferme": True, "rep": None, "apres": 0, "dom": 0}


def test_le_gestionnaire_ferme_aussi_le_menu_et_les_fenetres_hors_de_vue():
    f = _methode("_fermerFenetres")
    assert "this.mobileNav" in f
    for module in ("AdjugoCrypto", "AdjugoRedactionPartenaire"):
        assert module in f, module
    # Chaque fichier servi qui ajoute une fenêtre à la page (hors de Vue) sait la fermer, et la page les ferme toutes.
    for src in sorted(STATIC.glob("*.js")):
        code = src.read_text(encoding="utf-8")
        if re.search(r"document\.body\.appendChild\((?!a\))", code) and src.name != "app.js":
            assert "fermerFenetres" in code and "fenetresOuvertes" in code, src.name
            nom = re.search(r"(?:root|window)\.(Adjugo\w+) = ", code).group(1)
            assert nom in f, (src.name, nom)
    # Le menu du téléphone : sa toile de fond est une fenêtre comme les autres.
    assert '<div v-if="mobileNav" class="nav-backdrop"' in HTML


# ═══ 2 bis. Un dossier partagé quitté sous une fenêtre ouverte ne reçoit rien d'un autre (remarque 2) ═══════════

_PARTAGE = ["_rawCtx", "_sharedApplyPlain", "_sharedEncrypt", "_sharedBody", "_sharedPut", "sharedSave",
            "sharedEnsureVerified", "sharedSubmit", "sharedUnlock", "sharedLostCode"]


def _partage(scenario):
    obj = "const o = {\n" + ",\n".join(_methode(n) for n in _PARTAGE) + "\n};\n"
    return _node("""
const appels = []; let ouverte = null;
const fenetre = () => new Promise(r => { ouverte = r; });
globalThis.window = globalThis;
globalThis.Vue = { markRaw: x => x };
globalThis.AdjugoCrypto = {
  modal: fenetre, showRecoveryCode: fenetre, askRecoveryCode: fenetre,
  ensureKey: async (scope, env) => (appels.push("ensureKey:" + scope), env ? { ctx: { k: scope } } : { isNew: true, code: "CODE-" + scope, ctx: { k: scope } }),
  keyFromCode: async (scope) => (appels.push("keyFromCode:" + scope), { k: scope }),
  resetKey: async (scope) => (appels.push("resetKey:" + scope), { code: "NOUVEAU-" + scope, ctx: { k: scope } }),
  encrypt: async (ctx) => ({ ciphertext: "c", cle: ctx.k }), decrypt: async () => "détail déchiffré",
  packDetail: t => t, unpackDetail: p => ({ texte: p, dpgf: null }) };
globalThis.fetch = async (url, opts) => { appels.push((opts && opts.method || "GET") + " " + url + " " + ((opts && opts.body) || ""));
  return { ok: true, status: 200, json: async () => ({ version: 2, status: "draft" }) }; };
const dossier = (t, autres) => Object.assign({ token: t, contrib: { company_name: "Société " + t, lot: "", quals: "", refs: "", contact: {} },
  refsRiches: [], version: 1, envelope: null, detailLocked: false, detailClair: "détail de " + t, detailDpgf: null,
  cryptoCtx: null, pendingCode: null, busy: false }, autres || {});
""" + obj + """
Object.assign(o, { notify(m) { appels.push("message:" + m); }, loadShared() {}, sharedConvLoad() {}, sharedReload() {},
  validationMsg() { return ""; }, confirmer: async () => true,
  api: async (m, url) => { appels.push(m + " " + url); if (url.endsWith("/otp/status")) return { required: true, pending: true, email_masked: "c***@x.fr" }; return { status: "submitted" }; } });
globalThis._spFusionRefs = () => [];             // fonction de app.js hors du sujet (références de la part)
const attendre = async () => { for (let i = 0; i < 20 && !ouverte; i++) await new Promise(r => setImmediate(r));
  const r = ouverte; ouverte = null; if (!r) throw new Error("aucune fenêtre ouverte"); return r; };
const versB = () => appels.filter(a => a.indexOf("/B/") >= 0 || a.indexOf(":B") >= 0);
""" + scenario)


def test_un_dossier_partage_quitte_sous_la_fenetre_du_code_ne_recoit_pas_la_part_d_un_autre():
    r = _partage("""
(async () => {
  const res = {};
  for (const reponse of [true, null]) {          // l'utilisateur confirme dans la fenêtre restée ouverte, ou elle se ferme
    appels.length = 0;
    o.sharedAo = dossier("A");
    const p = o.sharedSave(); const fermer = await attendre();
    o.sharedAo = dossier("B");                   // suivant du navigateur : un autre dossier partagé à l'écran
    fermer(reponse); await p;
    res[String(reponse)] = { versB: versB(), b: { pendingCode: o.sharedAo.pendingCode, cryptoCtx: o.sharedAo.cryptoCtx } };
  }
  console.log(JSON.stringify(res));
})();
""")
    for reponse in ("true", "null"):
        assert r[reponse]["versB"] == [], (reponse, r[reponse])
        assert r[reponse]["b"] == {"pendingCode": None, "cryptoCtx": None}, reponse


def test_la_verification_et_la_soumission_ne_partent_jamais_vers_un_autre_dossier():
    r = _partage("""
// Une fenêtre qui s'ouvre encore pour un autre dossier (le code de A montré pour B) ne serait jamais fermée : le
// résultat partiel est alors écrit à la sortie, et le test échoue sur l'étape en cause.
const etapes = {}; let fini = false;
process.on("exit", () => { if (!fini) console.log(JSON.stringify(Object.assign({ incomplet: true }, etapes))); });
(async () => {
  appels.length = 0;
  o.sharedAo = dossier("A", { cryptoCtx: { k: "A" }, detailClair: "" });
  const p = o.sharedSubmit(); const fermer = await attendre();     // « Vérifiez votre identité » ouverte
  o.sharedAo = dossier("B");
  fermer({ value: "123456" }); await p;
  const soumission = etapes.soumission = { appels: appels.slice(), versB: versB() };
  // Déverrouiller le détail : le code saisi pour A n'est jamais appliqué ni rangé pour B.
  appels.length = 0;
  o.sharedAo = dossier("A", { envelope: { ciphertext: "x", kdf_salt: "s" } });
  const q = o.sharedUnlock(); const fermer2 = await attendre();
  o.sharedAo = dossier("B", { detailClair: "détail de B" });
  fermer2("CODE-A"); await q;
  const deverrou = etapes.deverrou = { versB: versB(), b: o.sharedAo.detailClair, ctx: o.sharedAo.cryptoCtx };
  // « Code perdu » : le nouveau code de A ne devient jamais celui de B, rien n'est envoyé pour B.
  appels.length = 0;
  o.sharedAo = dossier("A", { envelope: { ciphertext: "x" } });
  const s = o.sharedLostCode(); const fermer3 = await attendre();
  o.sharedAo = dossier("B");
  fermer3(null); etapes.perdu = { versB: versB() }; await s;
  const perdu = { versB: versB(), b: { pendingCode: o.sharedAo.pendingCode, cryptoCtx: o.sharedAo.cryptoCtx } };
  // Sur le même écran, tout se passe comme avant.
  appels.length = 0;
  o.sharedAo = dossier("A", { cryptoCtx: { k: "A" }, detailClair: "" });
  const t = o.sharedSubmit(); const fermer4 = await attendre(); fermer4({ value: "123456" }); await t;
  fini = true; console.log(JSON.stringify({ soumission, deverrou, perdu, meme: appels.slice() }));
})();
""")
    assert not r.get("incomplet"), r
    assert r["soumission"]["versB"] == [], r["soumission"]
    assert not [a for a in r["soumission"]["appels"] if "/otp/verify" in a or "/contribution/submit" in a], r["soumission"]
    assert r["deverrou"] == {"versB": [], "b": "détail de B", "ctx": None}
    assert r["perdu"] == {"versB": [], "b": {"pendingCode": None, "cryptoCtx": None}}
    assert any(a.startswith("POST /api/invite/A/otp/verify") for a in r["meme"]), r["meme"]
    assert any(a.startswith("POST /api/invite/A/contribution/submit") for a in r["meme"]), r["meme"]
