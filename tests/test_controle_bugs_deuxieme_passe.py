"""Contrôle des bugs d'octobre 2026, deuxième passe : chaque test dit ce que le logiciel DOIT faire d'après ses contrats
et ses textes affichés ; tous échouaient sur f31ebef, chacun sur son défaut. Les invitations du réseau Adjugo sont dans
tests/test_controle_bugs_deuxieme_passe_reseau.py (registre simulé). Le bilan : docs/REORGANISATION_V2A.md, section R.

Aucun réseau : routes appelées par le client de test, formulaires lus avec pypdf, méthodes de app.js et fonctions de
invite.html exécutées sous Node, gabarits de app.html rendus par le compilateur Vue du dépôt.
"""
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tests.test_convention_groupement import (_db, _gen, _groupement, _invite, _part, _pdf_text, _project,
                                              _set_company)
from tests.test_reorganisation_v2a_entreprise import _accolade_fermante, _methode
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
I18N = json.loads((STATIC / "i18n.js").read_text(encoding="utf-8").split("window.ADJUGO_I18N = ", 1)[1]
                  .rstrip().rstrip(";"))
VUE = sorted((STATIC / "vendor").glob("vue-*.prod.js"))[-1]


def _node(script, *args, tz="Europe/Paris"):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    env = dict(os.environ, TZ=tz)
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _methode_si(nom):
    """La méthode si elle existe (une correction peut en ajouter une), sinon rien."""
    return _methode(nom) + ",\n" if re.search(r"\n    (async )?" + re.escape(nom) + r"\(", JS) else ""


def _fonction_js(nom):
    m = re.search(r"\nfunction " + re.escape(nom) + r"\(", JS)
    assert m, nom
    return JS[m.start() + 1:_accolade_fermante(JS, JS.index("{", m.end()))]


# Un fragment de app.html rendu par le compilateur Vue du dépôt, avec les vraies méthodes de app.js : le texte lu.
_VUE_TEXTE = r"""
const fs = require("fs"), vm = require("vm");
const unesc = (x) => String(x).replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
const mkEl = () => ({ set innerHTML(v) { this._v = v; const m = /^<div foo="([\s\S]*)">/.exec(v);
  this.children = [{ getAttribute: () => unesc(m ? m[1] : "") }]; }, get textContent() { return unesc(this._v); } });
const ctx = { console, document: { createElement: mkEl } };
ctx.window = ctx; ctx.self = ctx; ctx.globalThis = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(VUE, "utf8"), ctx);
const text = (v) => v == null || typeof v === "boolean" ? "" : (typeof v === "string" || typeof v === "number") ? String(v)
  : Array.isArray(v) ? v.map(text).join("") : (typeof v.type === "symbol" && String(v.type).includes("v-cmt")) ? "" : text(v.children);
const render = ctx.Vue.compile(TPL);
const GLOBAUX = /^_|^(Object|Array|String|JSON|Math|Number|Date|encodeURIComponent|undefined|parseInt|isNaN)$/;
const res = CASES.map(st => {
  const o = Object.assign(FABRIQUE(), st);
  const proxy = new Proxy(o, {
    get: (t, key) => (key in t ? t[key] : (typeof key === "string" && /^[a-z]/i.test(key) ? () => "" : undefined)),
    has: (t, key) => (key in t) || (typeof key === "string" && !GLOBAUX.test(key)) });
  return text(render.call(proxy, proxy, [])).replace(/\s+/g, " ").trim();
});
console.log(JSON.stringify(res));
"""


def _rendre(tpl, methodes, cas, prelude="", tz="Europe/Paris"):
    script = (prelude + f"\nconst VUE = {json.dumps(str(VUE))};\nconst TPL = {json.dumps(tpl)};\n"
              f"const CASES = {json.dumps(cas)};\nconst FABRIQUE = () => ({{\n{methodes}\n}});\n" + _VUE_TEXTE)
    return _node(script, tz=tz)


def _textes_page(pdf: bytes, index: int):
    """[(x, y, texte)] de la page `index` (coordonnées absolues, depuis le bas)."""
    from pypdf import PdfReader
    out = []

    def v(t, cm, tm, fd, fs):
        if t.strip():
            out.append((tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5], t.strip()))
    PdfReader(io.BytesIO(pdf)).pages[index].extract_text(visitor_text=v)
    return out


@pytest.fixture
def groupes(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda mails: sent.extend(mails))
    return sent


def _lecture_seule(client, h, pid, name="Lecture Seule SARL"):
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": name, "can_contribute": False})
    assert r.status_code == 200, r.text
    return r.json()


# ═══ 1. « Total prévisionnel » : seul un prix manquant le masque ═══════════════════════════════════════════════

def test_01_total_previsionnel_affiche_sans_nom_d_entreprise_quand_aucun_prix_ne_manque(client, auth):
    h = auth["headers"]
    _set_company(auth["email"], name="")
    pid = _project(client, h, name="Gymnase")
    from app.models import Project
    db = _db()
    try:
        db.get(Project, pid).estimate = {"total_ht": 50000}
        db.commit()
    finally:
        db.close()
    # Aucun partenaire : pas de total (la convention en exige un).
    assert client.get(f"/api/projects/{pid}/consortium", headers=h).json()["offre"]["total_ht_estime"] is None
    i2 = _invite(client, h, pid, "Le Gall Électricité")
    _part(client, i2["token"], "Le Gall Électricité", "Lot 2", 20000)
    o = client.get(f"/api/projects/{pid}/consortium", headers=h).json()["offre"]
    assert (o["total_ht_estime"], o["lead_total_ht"], o["lead_source"]) == (70000.0, 50000.0, "estimation"), o
    conv = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert conv["total_estime_ht"] == 70000.0, conv
    assert any(m.startswith("Nom de votre entreprise") for m in conv["manques"]), conv["manques"]
    # Un prix manque : plus de total, nulle part.
    i3 = _invite(client, h, pid, "Morvan Plomberie")
    assert client.get(f"/api/projects/{pid}/consortium", headers=h).json()["offre"]["total_ht_estime"] is None
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["total_estime_ht"] is None
    assert i3["token"]


# ═══ 2. « Pièces à fournir » : un RIB dont le nom colle « rib » à un autre mot ════════════════════════════════

def test_02_un_rib_au_nom_colle_reste_reconnu_les_faux_positifs_restent_ecartes():
    from app.routers.checklist import match_document
    from tests.test_controle_bugs_marche import _doc
    RIB, QUALIF = "Relevé d'identité bancaire (RIB)", "Certificat Qualibat / qualification"
    for nom in ("RIBBNP.pdf", "RIBdupont.pdf", "monrib.pdf", "ribcic.pdf", "SARLrib.pdf", "MonRIB.pdf",
                "RibEntreprise.pdf", "RIB_SARL.pdf"):
        for cat in ("autre", "administratif"):
            assert match_document(RIB, [_doc(nom, cat)])["found"] is True, (nom, cat)
    for nom in ("RGEpro.pdf", "rgequalibat.pdf"):
        assert match_document(QUALIF, [_doc(nom)])["found"] is True, nom
    for piece, nom in ((RIB, "Avis d'attribution 2025.pdf"), (RIB, "Contribution formation.pdf"),
                       (RIB, "ATTRIBUTION.pdf"), (RIB, "Distribution.pdf"), (QUALIF, "Cahier des charges.pdf"),
                       (QUALIF, "Décharge.pdf")):
        assert match_document(piece, [_doc(nom)])["found"] is False, (piece, nom)
    assert match_document("Avis d'attribution du lot précédent", [_doc("RIB.pdf")])["found"] is False


# ═══ 3. « Analyser ce marché » enregistre la date limite du marché ═══════════════════════════════════════════

def _analyser(client, monkeypatch, h, *, dl_iso=None, dl_fr=None, non_lue=False, ref="26-100001"):
    from app.sourcing.sources.boamp import BoampSource
    from app.services import analyse_partagee
    monkeypatch.setattr(BoampSource, "fetch_dce", lambda self, t: "")       # pas de réseau
    details = {"intitule_marche": "Couverture école"}
    if dl_fr:
        details["date_limite"] = dl_fr
    monkeypatch.setattr(analyse_partagee, "analyser_texte",
                        lambda *a, **k: {"summary": "Résumé", "details": dict(details), "score_breakdown": None})
    tender = {"objet": "Réfection couverture école", "acheteur": "Commune de Plomodiern", "departements": ["29"],
              "cpv": ["45261000"], "procedure": "MAPA", "date_limite": dl_iso, "date_limite_rectifiee_non_lue": non_lue,
              "provenance": {"source": "BOAMP", "source_url": "https://www.boamp.fr/avis/detail/" + ref,
                             "official_ref": ref}}
    r = client.post("/api/sourcing/analyze", headers=h, json={"tender": tender})
    assert r.status_code == 200, r.text
    return r.json()["project_id"]


def test_03_analyser_ce_marche_enregistre_la_date_limite_et_ce_qui_la_lit(client, auth, monkeypatch, groupes):
    h = auth["headers"]
    dl = date.today() + timedelta(days=2)
    pid = _analyser(client, monkeypatch, h, dl_iso=dl.isoformat(), dl_fr=dl.strftime("%d/%m/%Y") + " à 12h00")
    assert client.get(f"/api/projects/{pid}", headers=h).json()["deadline"] == dl.isoformat()
    # Courriel d'invitation : il nomme la date limite (REORGANISATION_V2B § B4).
    import app.services.email as E
    envoyes = []
    monkeypatch.setattr(E, "send_email", lambda to, subject, text, html=None, **kw: envoyes.append(text) or True)
    monkeypatch.setattr(E, "is_enabled", lambda: True)
    assert client.post(f"/api/projects/{pid}/invites", headers=h,
                       json={"recipient": f"p_{uuid.uuid4().hex[:6]}@test.fr", "company_name": "Partenaire SARL"}
                       ).status_code == 200
    lignes = [li.strip() for t in envoyes + [m[2] for m in groupes if len(m) > 2] for li in t.splitlines()
              if li.startswith("Date limite")]
    assert lignes and all(li == "Date limite : " + dl.strftime("%d/%m/%Y") for li in lignes), lignes
    # Rappel J-3 de la part : il part.
    import app.services.alerts as AL
    monkeypatch.setattr(AL, "send_email", lambda *a, **k: True, raising=False)
    db = _db()
    try:
        assert AL.run_cotraitance_reminders(db)["reminded"] >= 1
    finally:
        db.close()


def test_03_date_limite_lue_dans_l_analyse_a_defaut_de_l_avis_jamais_apres_un_rectificatif_non_lu(client, auth,
                                                                                                  monkeypatch):
    h = auth["headers"]
    pid = _analyser(client, monkeypatch, h, dl_fr="24/11/2026 à 12h00", ref="26-100002")
    assert client.get(f"/api/projects/{pid}", headers=h).json()["deadline"] == "2026-11-24"
    # Un rectificatif change la date limite sans qu'on ait pu la lire : aucune date (ni l'ancienne, ni une devinée).
    pid = _analyser(client, monkeypatch, h, dl_fr="24/11/2026 à 12h00", non_lue=True, ref="26-100003")
    assert client.get(f"/api/projects/{pid}", headers=h).json()["deadline"] is None


def test_03_import_du_dossier_pose_la_date_limite_sans_jamais_ecraser_une_date_deja_la(client, auth):
    from app.models import Project, User
    from app.routers.sourcing import _finish_analysis
    h = auth["headers"]
    sans = client.post("/api/projects/", headers=h, json={"name": "Marché importé", "client": "Ville"}).json()["id"]
    avec = _project(client, h, name="Marché daté", deadline_days=40)
    db = _db()
    try:
        user = db.query(User).filter(User.email == auth["email"]).first()
        for pid in (sans, avec):
            p = db.get(Project, pid)
            _finish_analysis(db, p, {"summary": "", "match_score": 50,
                                     "details": {"intitule_marche": p.name, "date_limite": "05/12/2026 à 16h00"}},
                             {}, {}, user)
    finally:
        db.close()
    assert client.get(f"/api/projects/{sans}", headers=h).json()["deadline"] == "2026-12-05"
    assert client.get(f"/api/projects/{avec}", headers=h).json()["deadline"] == (date.today()
                                                                                  + timedelta(days=40)).isoformat()


# ═══ 4. L'adresse lue au registre n'est écrite qu'une fois ════════════════════════════════════════════════════

def _registre_simule(monkeypatch, siege, etablissements=()):
    import httpx
    from app.services import registre
    rep = {"results": [{"siren": "912345678", "nom_complet": "COUVERTURE KERVELLA", "activite_principale": "43.91B",
                        "nature_juridique": "5499", "etat_administratif": "A", "categorie_entreprise": "PME",
                        "siege": dict(siege, siret="91234567800017", etat_administratif="A"),
                        "matching_etablissements": list(etablissements)}], "total_results": 1}
    monkeypatch.setattr(registre, "_client", lambda timeout=12: httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=rep)), timeout=timeout))
    return registre


def test_04_adresse_du_registre_sans_code_postal_ni_ville_en_double(client, auth, monkeypatch):
    registre = _registre_simule(monkeypatch, {"adresse": "3 RUE DU PORT 29200 BREST", "code_postal": "29200",
                                              "libelle_commune": "BREST"},
                                [{"siret": "91234567800025", "adresse": "12 ZA DE KERNEVEZ 29000 QUIMPER",
                                  "code_postal": "29000", "libelle_commune": "QUIMPER"}])
    r = client.get("/api/registre/company?q=91234567800017", headers=auth["headers"]).json()
    assert (r["address"], r["postal_code"], r["city"]) == ("3 RUE DU PORT", "29200", "BREST"), r
    from app.services.cerfa import generate_dc1
    from app.services.groupement_convention import _addr
    texte = " ".join(_pdf_text(generate_dc1({"name": r["name"], "siret": r["siret"], "address": r["address"],
                                             "postal_code": r["postal_code"], "city": r["city"]},
                                            {"name": "Marché test", "cotraitants": []})).split())
    assert "3 RUE DU PORT 29200 BREST" in texte and "29200 BREST 29200 BREST" not in texte
    assert _addr(r["address"], r["postal_code"], r["city"]) == "3 RUE DU PORT 29200 BREST"
    # Établissement du département (partenaires du registre) : même règle.
    x = registre.discover_cotraitants("couverture", "29")["results"][0]
    assert (x["address"], x["postal_code"], x["city"]) == ("12 ZA DE KERNEVEZ", "29000", "QUIMPER"), x


def test_04_adresse_du_registre_gardee_telle_quelle_si_elle_ne_finit_pas_par_le_code_postal_et_la_ville(monkeypatch):
    for adresse, cp, ville, attendu in (
            ("22-30 22 AVENUE DE WAGRAM 75008 PARIS", "75008", "PARIS", "22-30 22 AVENUE DE WAGRAM"),
            ("BP 12 LIEU-DIT KERHUEL 29120 PONT-L'ABBE CEDEX", "29120", "PONT-L'ABBE", "BP 12 LIEU-DIT KERHUEL"),
            ("ZONE DE KERDROAL", "29200", "BREST", "ZONE DE KERDROAL"),
            ("1 RUE DE PARIS 29000", "29000", "QUIMPER", "1 RUE DE PARIS"),
            ("29200 RUE DE BREST 56100 LORIENT", "56100", "LORIENT", "29200 RUE DE BREST")):
        registre = _registre_simule(monkeypatch, {"adresse": adresse, "code_postal": cp, "libelle_commune": ville})
        assert registre.lookup_company("91234567800017")["address"] == attendu, adresse


# ═══ 5. « Pourquoi vous dans ce groupement » (partenaire avec compte) : les seuils disent la donnée ═══════════

def test_05_seuils_du_partenaire_avec_compte_suivent_la_donnee_rendu_par_vue():
    bloc = zone(HTML, "partage-pourquoi")
    i = bloc.index('<div v-if="sfm().seuils"')
    tpl = bloc[i:bloc.index("</div>", bloc.index("qualifs_ok", i)) + len("</div>")]
    cas = [{"seuils": {"ca_cumule_ok": False, "qualifs_ok": False}}, {"seuils": {"ca_cumule_ok": True, "qualifs_ok": True}}]
    rendu = _rendre(tpl, "sfm() { return { seuils: this.seuils }; }", cas)
    assert rendu == ["Chiffre d'affaires cumulé à vérifier Qualifications exigées à vérifier",
                     "Chiffre d'affaires cumulé suffisant Qualifications exigées couvertes"], rendu
    for k in ("Chiffre d'affaires cumulé suffisant", "Chiffre d'affaires cumulé à vérifier",
              "Qualifications exigées couvertes", "Qualifications exigées à vérifier"):
        assert I18N["nl"].get(k) and I18N["es"].get(k), k
    # Les mêmes phrases que le lien du partenaire.
    assert '"Chiffre d\'affaires cumulé suffisant", "Chiffre d\'affaires cumulé à vérifier"' in INV


# ═══ 6. Lien du partenaire : « Ce que le groupement comble » ne parle pas de « votre » activité ═══════════════

def test_06_ce_que_le_groupement_comble_sans_phrase_ecrite_pour_le_chef_de_file(client):
    from app.models import Project, ProjectInvite
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        u = ensure_demo(db, force=True)
        p = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        inv = db.query(ProjectInvite).filter(ProjectInvite.project_id == p.id,
                                             ProjectInvite.company_name.like("Breizh D%")).first()
        token = inv.token
    finally:
        db.close()
    gaps = client.get(f"/api/invite/{token}").json()["for_member"]["gaps_combles"]
    assert gaps, gaps
    texte = " ".join(gaps).lower()
    assert "votre" not in texte and "auprès du partenaire" not in texte, gaps
    assert {"Métier du marché", "Lieu d'exécution", "Qualifications exigées"} <= set(gaps), gaps


# ═══ 7. Lien du partenaire : « Les membres du groupement » suit l'envoi de la part ═══════════════════════════

def test_07_le_bloc_des_membres_est_relu_quand_le_statut_de_la_part_change_sous_node():
    m = re.search(r"(let statutLu;[^\n]*\n\s*)?const setStatus = \(s\) => \{.*?\};\n", INV)
    assert m, "setStatus absent"
    fn = re.search(r"\n    async function rafraichirPourquoi\(", INV)
    raf = INV[fn.start():_accolade_fermante(INV, INV.index("{", fn.end()))] if fn else ""
    script = r"""
let appels = [], rendus = [];
const TOKEN = "jeton";
let POURQUOI = { innerHTML: "x" };
const BARRE = { partStatut: "" }; const renderBarre = () => {}; const icons = () => {}; const ico = () => "";
const status = { innerHTML: "", className: "", style: {} };
const fetch = async (url) => { appels.push(url); return { ok: true, json: async () => ({ for_member: { state: { n_submitted: 1 } } }) }; };
function renderForMember(el, fm, d) { rendus.push(fm.state.n_submitted); }
""" + raf + "\n" + m.group(0) + r"""
(async () => {
  setStatus("draft"); await new Promise(r => setTimeout(r, 10));
  const avant = appels.length;
  setStatus("submitted"); await new Promise(r => setTimeout(r, 10));
  setStatus("submitted"); await new Promise(r => setTimeout(r, 10));
  console.log(JSON.stringify({ avant, appels, rendus }));
})();
"""
    r = _node(script)
    assert r["avant"] == 0, r                      # le chargement de la part ne relit rien
    assert r["appels"] == ["/api/invite/jeton"] and r["rendus"] == [1], r


# ═══ 8. Barre du groupement : « Toutes les parts sont reçues » seulement avec des parts reçues ═══════════════

def test_08_barre_du_groupement_sans_aucune_part_recue_rendu_par_vue():
    tpl = zone(HTML, "marche-commande-groupement")
    meth = ",\n".join(_methode(n) for n in ("aoPendingInvites", "aoPendingRelancables", "inviteRelancable",
                                             "inviteDeclined")) + ",\n" + _methode_si("aoPartsRecues")
    inv = {"id": 1, "revoked": False, "can_contribute": True, "recipient": "", "source": "manuel"}
    cas = [{"ao": {"generating": False, "share": {"invites": [dict(inv, state="declined", declined_at="2026-10-22T10:00:00")]}}},
           {"ao": {"generating": False, "share": {"invites": [dict(inv, revoked=True)]}}},
           {"ao": {"generating": False, "share": {"invites": [dict(inv, can_contribute=False)]}}},
           {"ao": {"generating": False, "share": {"invites": [dict(inv, contribution_status="submitted")]}}},
           {"ao": {"generating": False, "share": {"invites": [dict(inv)]}}}]
    r = _rendre(tpl, meth, cas)
    for t in r[:3]:
        assert "Toutes les parts sont reçues" not in t and t.startswith("Aucune part reçue : invitez un partenaire"), r
    assert r[3].startswith("Toutes les parts sont reçues"), r            # démo de Kerhel : 1 sur 1, inchangé
    assert r[4].startswith("1 partenaire(s) en attente de leur part"), r
    assert I18N["nl"].get("Aucune part reçue : invitez un partenaire") and I18N["es"].get(
        "Aucune part reçue : invitez un partenaire")


# ═══ 9. Suivi des invitations et simulations : l'heure locale de l'événement ═════════════════════════════════

def test_09_heures_du_suivi_des_invitations_et_des_simulations_a_l_heure_locale_rendu_par_vue():
    meth = ",\n".join(_methode(n) for n in ("auditWhen", "auditAt"))
    prelude = _fonction_js("_isoUtc")
    inv = {"id": 1, "company_name": "Élec Le Goff", "view_count": 4, "last_viewed_at": "2026-10-22T21:57:38.622569",
           "recipient": "p@exemple.fr", "emailed_at": "2026-10-22T21:54:36.280573", "revoked": False}
    tpl = zone(HTML, "marche-invitations")
    r = _rendre(tpl, meth + ",\ninviteIsNetwork(i) { return !!i.reseau; }",
                [{"ao": {"share": {"invites": [inv]}}}, {"ao": {"share": {"invites": [dict(inv, reseau=True)]}}}],
                prelude=prelude)
    assert "4 consultation(s) · dernière 22 oct., 23:57" in r[0] and "Email envoyé 22 oct., 23:54" in r[0], r
    assert "Envoyée par Adjugo 22 oct., 23:54" in r[1], r
    i = HTML.index('<div v-for="h in ao.grp.history"')
    tpl = HTML[i:HTML.index("</div>", HTML.index("h.retained", i)) + len("</div>")]
    r = _rendre(tpl, meth + ",\ndecLabel() { return ''; }",
                [{"ao": {"grp": {"history": [{"id": 1, "created_at": "2026-01-15T10:00:00.123456", "members": []}]}}}],
                prelude=prelude)
    assert r[0].startswith("15 janv., 11:00"), r
    assert "auditWhen(" not in HTML


# ═══ 10. « À venir » : une source qui ne répond pas est dite, jamais « aucune échéance » ═════════════════════

def test_10_a_venir_sources_injoignables_le_serveur_rend_les_deux_erreurs(client, auth, monkeypatch):
    from app.services import decp, renewal

    def _coupe(*a, **k):
        raise ConnectionError("réseau sortant coupé")
    monkeypatch.setattr(decp, "_fetch", _coupe)
    monkeypatch.setattr(renewal, "_fetch_attributions", _coupe)
    r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie", "departements": ["29"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 0 and d["analyse"] == "remboursee", d
    assert any(e.startswith("DECP indisponible") for e in d["errors"]), d
    assert any(e.startswith("BOAMP indisponible") for e in d["errors"]), d


def test_10_a_venir_sources_injoignables_l_ecran_le_dit_sous_node_et_rendu_par_vue():
    script = "const o = {\n" + _methode("srcRenewals") + ",\n" + _methode_si("srcRenErreurs") + r"""
  notify(m, k) { this.notes.push([m, k]); }, loadStats() {}, srcDeps() { return ["29"]; },
  async api() { return { count: 0, renewals: [], errors: ["DECP indisponible : x", "BOAMP indisponible : y"], source: "BOAMP", analyse: "remboursee" }; },
};
Object.assign(o, { notes: [], src: { query: "voirie", renewals: { list: [], loading: false, done: false, source: "", analyse: "" } } });
o.srcRenewals().then(() => console.log(JSON.stringify({ notes: o.notes, errors: o.src.renewals.errors })));
"""
    r = _node(script)
    assert r["errors"] == ["DECP indisponible : x", "BOAMP indisponible : y"], r
    assert r["notes"] and "Aucune échéance proche" not in r["notes"][0][0], r
    tpl = zone(HTML, "trouver-radar")
    meth = _methode_si("srcRenErreurs") + "estDemo() { return true; }, srcRenHorsForfait() { return false; }"
    base = {"trouverOnglet": "avenir", "src": {"query": "", "dept": "", "renewals": {"list": [], "loading": False, "done": True, "source": "BOAMP",
                                                          "analyse": "remboursee", "errors": []}}}
    cas = [base, json.loads(json.dumps(base))]
    cas[1]["src"]["renewals"]["errors"] = ["DECP indisponible : HTTPSConnectionPool(host=x)", "BOAMP indisponible : y"]
    r = _rendre(tpl, meth, cas)
    assert "Aucune échéance proche sur ce périmètre." in r[0], r
    assert "Aucune échéance proche" not in r[1] and "HTTPSConnectionPool" not in r[1], r
    assert ("Les données publiées des marchés attribués n'ont pas répondu." in r[1]
            and "Les avis d'attribution du BOAMP n'ont pas répondu." in r[1]), r
    for k in ("Les données publiées des marchés attribués n'ont pas répondu.",
              "Les avis d'attribution du BOAMP n'ont pas répondu.", "Une source n'a pas répondu.",
              "Aucune fin de contrat trouvée, mais une source n'a pas répondu : réessayez plus tard."):
        assert I18N["nl"].get(k) and I18N["es"].get(k), k


# ═══ 11. Un lien en lecture seule ne reçoit le total de l'offre commune nulle part ═══════════════════════════

def _sans_total(client, token):
    fm = client.get(f"/api/invite/{token}").json()["for_member"]["state"]
    j = client.get(f"/api/invite/{token}/journal").json()["entries"]
    integ = client.get(f"/api/invite/{token}/journal/integrity").json()
    exp = client.get(f"/api/invite/{token}/journal/export?format=json")
    assert exp.status_code == 200, exp.text
    vus = [e["detail"] for e in j if e["action"] == "offer.frozen"]
    assert vus, j
    chaine = json.dumps(integ.get("chaine") or integ, ensure_ascii=False)
    return fm["total_offre_ht"], vus, ("100 000" in chaine or "100000" in chaine), "100 000" in exp.text


def test_11_lien_lecture_seule_sans_total_journal_verification_et_export(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    ro = _lecture_seule(client, h, pid, name="Expert Comptable SARL")      # créé AVANT la génération
    c = _gen(client, h, pid).json()
    assert c["status"] == "a_signer" and c["total_offre_ht"] == 100000.0
    total, vus, integ, export = _sans_total(client, ro["token"])
    assert total is None and not any("100" in (d or "") for d in vus) and not integ and not export, (vus, integ, export)
    # Le membre qui apporte une part garde ce qu'il voit.
    total, vus, integ, export = _sans_total(client, invs[0]["token"])
    assert total == 100000.0 and any("100 000" in (d or "") for d in vus) and export


def test_11_lien_lecture_seule_sans_total_avec_l_ancienne_route_figer(client, auth, groupes):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid = _project(client, h)
    p1 = _invite(client, h, pid, "Le Gall Électricité", recipient=f"p1_{uuid.uuid4().hex[:6]}@partenaire.fr")
    _part(client, p1["token"], "Le Gall Électricité", "Lot 2 — Électricité", 40000)
    ro = _lecture_seule(client, h, pid, name="Lecture Seule Avant Figer")
    assert client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 60000}).status_code == 200
    total, vus, integ, export = _sans_total(client, ro["token"])
    assert total is None and not any("100" in (d or "") for d in vus) and not integ and not export, (total, vus)
    assert client.get(f"/api/invite/{p1['token']}").json()["for_member"]["state"]["total_offre_ht"] == 100000.0


# ═══ 14. Coffre-fort croisé : refusé à un lien en lecture seule ══════════════════════════════════════════════

def test_14_coffre_croise_refuse_au_lien_lecture_seule(client, auth, groupes):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    fin = (date.today() + timedelta(days=12)).isoformat()
    r = client.post(f"/api/invite/{invs[0]['token']}/contribution/piece",
                    data={"piece_type": "sociale", "expiration_date": fin},
                    files={"file": ("URSSAF_LeGall.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200, r.text
    ro = _lecture_seule(client, h, pid, name="Bureau Lecture Seule")
    r = client.get(f"/api/invite/{ro['token']}/coffre-croise")
    assert r.status_code == 403, r.text
    assert "lecture seule" in r.json()["detail"], r.json()
    assert "Le Gall" not in r.text
    # Le membre garde la grille.
    r = client.get(f"/api/invite/{invs[0]['token']}/coffre-croise")
    assert r.status_code == 200 and any(m.get("company") == "Le Gall Électricité" for m in r.json()["members"])


# ═══ 15. ATTRI1 : la partie de l'acheteur reste vide ═════════════════════════════════════════════════════════

_FICHE = {"name": "Test SARL", "siret": "12345678900011", "address": "1 rue de Brest", "postal_code": "29000",
          "city": "Quimper", "representant_legal": "Jean Test", "forme_juridique": "SARL",
          "email": "contact@test.fr", "phone": "0298000000"}


def test_15_acte_d_engagement_ne_remplit_pas_la_ligne_de_l_acheteur():
    from app.services.cerfa import generate_attri1
    for p in ({"name": "École", "client": "Mairie de Brest"},
              {"name": "École", "client": "Mairie de Brest", "groupement": {"forme": "conjoint"},
               "cotraitants": [{"name": "Le Gall", "siret": "98765432100011", "role": "cotraitant"}]}):
        pdf = generate_attri1(dict(_FICHE), p)
        page6 = " ".join(t for _x, _y, t in _textes_page(pdf, 5))
        assert "Quimper" not in page6 and not re.search(r"\d{2}/\d{2}/\d{4}", page6), page6
    # Le lieu et la date du candidat restent en C1 (page 4).
    page4 = " ".join(t for _x, _y, t in _textes_page(generate_attri1(dict(_FICHE), {"name": "École"}), 3))
    assert re.search(r"Quimper, le \d{2}/\d{2}/\d{4}", page4), page4


# ═══ 16. DC4 : lieu et date sur les lignes du sous-traitant et du titulaire ══════════════════════════════════

def test_16_dc4_lieu_et_date_sur_leurs_lignes_jamais_dans_la_zone_de_l_acheteur():
    from app.services.cerfa import generate_dc4
    p = {"name": "École", "client": "Mairie de Brest",
         "cotraitants": [{"name": "Echafaudages Kerne", "siret": "98765432100011", "role": "sous_traitant",
                          "city": "Brest", "address": "2 rue Kerne", "postal_code": "29200"}]}
    ajoutes = [(x, y, t) for x, y, t in _textes_page(generate_dc4(dict(_FICHE), p), 7)
               if "Quimper" in t or "Brest" in t or re.search(r"\d{2}/\d{2}/\d{4}", t)]
    assert ajoutes, ajoutes
    assert all(440 < y < 480 for _x, y, _t in ajoutes), ajoutes            # lignes « A …, le … » (y = 459,6)
    sous = " ".join(t for x, _y, t in ajoutes if x < 300)
    titulaire = " ".join(t for x, _y, t in ajoutes if x >= 300)
    assert "Brest" in sous and "Quimper" not in sous and re.search(r"\d{2}/\d{2}/\d{4}", sous), ajoutes
    assert "Quimper" in titulaire and re.search(r"\d{2}/\d{2}/\d{4}", titulaire), ajoutes
    # Sous-traitant sans ville : sa colonne reste à remplir, jamais la ville du titulaire.
    p["cotraitants"][0]["city"] = ""
    sous = [t for x, y, t in _textes_page(generate_dc4(dict(_FICHE), p), 7) if x < 300 and 440 < y < 480]
    assert not any("Quimper" in t for t in sous), sous


# ═══ 17. Documents générés : le jour de Paris ════════════════════════════════════════════════════════════════

def test_17_documents_generes_dates_du_jour_de_paris(client, auth, monkeypatch, groupes):
    import app.services.pieces_fin as pf
    monkeypatch.setattr(pf, "jour_paris", lambda: date(2031, 1, 15))     # jour de Paris (le jour UTC est autre)
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    _set_company(auth["email"], city="Quimper")
    from app.models import Project
    db = _db()
    try:
        db.get(Project, pid).estimate = {"lignes": [{"tache": "Pose", "phase": "Travaux", "jours": 2, "tarif": 450,
                                                     "montant": 900}], "total_ht": 900}
        db.commit()
    finally:
        db.close()
    for t in ("honneur", "dume", "attri1"):
        r = client.post(f"/api/cerfa/{pid}/{t}", headers=h)
        assert r.status_code == 200, (t, r.text)
        dates = set(re.findall(r"\d{2}/\d{2}/\d{4}", _pdf_text(r.content)))
        assert "15/01/2031" in dates, (t, dates)
    from app.services.cerfa import generate_dc4
    dc4 = " ".join(t for _x, _y, t in _textes_page(generate_dc4(dict(_FICHE), {"name": "École", "cotraitants": [
        {"name": "Kerne", "role": "sous_traitant", "city": "Brest"}]}), 7))
    assert "15/01/2031" in dc4, dc4
    r = client.get(f"/api/chiffrage/{pid}/dpgf", headers=h)
    assert r.status_code == 200 and "Établi le 15/01/2031" in _pdf_text(r.content)
    _gen(client, h, pid)
    r = client.get(f"/api/projects/{pid}/consortium/report", headers=h)
    assert r.status_code == 200 and "édité le 15/01/2031" in _pdf_text(r.content)
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    sommaire = z.read("00_SOMMAIRE.txt").decode("utf-8")
    assert "Date : 15/01/2031" in sommaire and "Genere par adjugo. le 15/01/2031" in sommaire, sommaire
    assert any(n.endswith("_2031-01-15.pdf") for n in z.namelist()), z.namelist()
    assert "2031-01-15" in r.headers.get("content-disposition", ""), r.headers


def test_17_compte_rendu_offre_figee_le_jour_de_paris(client, auth, groupes):
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    _gen(client, h, pid)
    from app.models import Project
    from sqlalchemy.orm.attributes import flag_modified
    db = _db()
    try:
        p = db.get(Project, pid)
        plan = dict(p.groupement_plan or {})
        plan["offre"] = dict(plan.get("offre") or {}, frozen_at="2026-10-22T22:30:00")     # 23/10 à 0 h 30 à Paris
        p.groupement_plan = plan
        flag_modified(p, "groupement_plan")
        db.commit()
    finally:
        db.close()
    from app.services.groupement_convention import get_convention
    db = _db()
    try:
        conv = get_convention(db, pid)
        conv.frozen_at = datetime(2026, 10, 22, 22, 30)
        db.commit()
    finally:
        db.close()
    texte = _pdf_text(client.get(f"/api/projects/{pid}/consortium/report", headers=h).content)
    assert "Offre commune figée le 23/10" in texte, re.findall(r"Offre commune fig[^\n]*", texte)


# ═══ 18. Courriel « Mes alertes » : la date limite au format de l'écran ══════════════════════════════════════

def test_18_courriel_des_alertes_date_limite_jj_mm_aaaa_et_acheteur_non_precise(client, auth, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import SavedSearch, User
    from app.services import alerts
    from app.sourcing import http as shttp
    from app.sourcing.sources import ted
    import app.routers.sourcing as rs
    fut = date.today() + timedelta(days=30)
    avis = [{"publication-number": "123456-2026", "notice-title": {"fra": "Travaux de voirie TED"},
             "place-of-performance": ["FRA"], "buyer-name": {"fra": ["Ville de Brest"]},
             "deadline-receipt-tender-date-lot": [fut.isoformat() + "+02:00"]},
            {"publication-number": "123457-2026", "notice-title": {"fra": "Travaux de voirie sans acheteur"},
             "place-of-performance": ["FRA"], "deadline-receipt-tender-date-lot": [fut.isoformat() + "+01:00"]}]

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"notices": avis}
    monkeypatch.setattr(shttp, "post_with_retry", lambda url, json=None, **k: _R())
    monkeypatch.setattr(rs, "_tender_sources", lambda countries=None: [ted.TedSource()])
    db = SessionLocal()
    u = db.query(User).filter(User.email == auth["email"]).first()
    s = SavedSearch(user_id=u.id, name="Voirie", query="voirie", countries=["FR"], frequency="quotidienne", active=True)
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    reel = alerts.run_one_saved_search
    monkeypatch.setattr(alerts, "run_one_saved_search", lambda s, db, mark=True: reel(s, db, mark) if s.id == sid else [])
    envoyes = []
    monkeypatch.setattr(alerts, "send_email", lambda to, sujet, texte, *a, **k: envoyes.append((to, sujet, texte)) or True)
    db = SessionLocal()
    try:
        alerts.run_tender_alerts(db)
    finally:       # l'alerte ne reste pas active pour les passages des autres tests de la session
        db.query(SavedSearch).filter(SavedSearch.id == sid).delete()
        db.commit()
        db.close()
    texte = next(e[2] for e in envoyes if e[0] == auth["email"])
    jour = fut.strftime("%d/%m/%Y")
    assert f"Travaux de voirie TED — Ville de Brest — clôture {jour}" in texte, texte
    assert f"Travaux de voirie sans acheteur — acheteur non précisé — clôture {jour}" in texte, texte
    assert "+02:00" not in texte and "n/d" not in texte and fut.isoformat() not in texte


# ═══ 19. Rappel de la part le jour de la date limite ══════════════════════════════════════════════════════════

def test_19_rappel_le_jour_de_la_date_limite_dit_le_dernier_jour(client, auth, monkeypatch):
    from tests.test_cotraitance_v4 import _alert_project
    import app.services.alerts as al
    import app.services.email as em
    envoyes = []

    def _envoi(to, subject, text, html=None, **k):
        envoyes.append({"to": to, "objet": subject, "texte": text})
        return True
    monkeypatch.setattr(em, "send_email", _envoi)
    monkeypatch.setattr(al, "send_email", _envoi)
    _set_company(auth["email"], name="Breizh Couverture")
    pid, (inv,) = _alert_project(client, auth, days=0, n_partners=1, submit=False)
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    mien = [x for x in envoyes if x["to"] == inv["recipient"] and x["objet"].startswith("Rappel")]
    assert mien, envoyes
    jour = date.today().strftime("%d/%m/%Y")
    assert mien[0]["objet"].startswith("Rappel — dernier jour pour votre part ("), mien[0]["objet"]
    assert "C'est le dernier jour pour ajouter votre part au groupement de Breizh Couverture" in mien[0]["texte"]
    assert f"(date limite : aujourd'hui, {jour})." in mien[0]["texte"], mien[0]["texte"]
    assert "il vous reste 1 jour" not in (mien[0]["objet"] + mien[0]["texte"]).lower()
    from app.services.email_invitation import rappel_part
    un = rappel_part(chef="Breizh Couverture", marche="École", url="", date_limite=date(2026, 10, 24), jours_restants=1)
    assert un["objet"] == "Rappel — il vous reste 1 jour pour votre part (École)", un["objet"]
    assert "Il vous reste 1 jour pour ajouter votre part" in un["texte"]


# ═══ 20. Journal d'accès : une phrase pour chaque action, Adjugo nommé, jamais « user:N » ════════════════════

_SANS_MARCHE = re.compile(r"^(network\.(profile_[a-z_]+|annuaire_query)|team\.[a-z_]+)$")


def _actions_du_code():
    """Les clés d'action du journal écrites dans app/ (familles du journal d'un marché)."""
    import ast
    cle = re.compile(r"^(atelier|carnet|entretien|grille|network|redaction|guest|owner|invite|offer|piece|groupement"
                     r"|convention|team)\.[a-z_]+$")
    out = {}
    for p in (ROOT / "app").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and cle.match(n.value):
                out.setdefault(n.value, set()).add(str(p.relative_to(ROOT)))
    return out


def test_20_chaque_action_du_journal_d_un_marche_a_sa_phrase():
    i = JS.index("    auditLabel(a) {")
    table = JS[i:JS.index("\n    },", i)]
    connues = set(re.findall(r'"([a-z_]+\.[a-z_]+)":', table))
    actions = {a for a in _actions_du_code() if a.rsplit(".", 1)[1] not in ("html", "js", "css", "pdf")}
    sans = sorted(a for a in actions if a not in connues and not _SANS_MARCHE.match(a))
    assert not sans, sans
    # Les actions laissées de côté ne s'écrivent jamais avec un marché (audit.record sans project_id).
    import ast
    for p in (ROOT / "app").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and any(kw.arg == "action" for kw in n.keywords):
                v = next(kw.value for kw in n.keywords if kw.arg == "action")
                if isinstance(v, ast.Constant) and isinstance(v.value, str) and _SANS_MARCHE.match(v.value):
                    assert not any(kw.arg == "project_id" for kw in n.keywords), (p, v.value)
    # Repli : une phrase, jamais la clé technique.
    script = "const o = {\n" + _methode("auditLabel") + "\n};\nconsole.log(JSON.stringify([o.auditLabel({action: 'x.inconnue'}), o.auditLabel({action: 'atelier.sans_ia'})]));"
    r = _node(script)
    assert r[0] == "Action enregistrée" and "." not in r[1], r


def test_20_journal_d_acces_auteur_lisible_et_pastille_adjugo(client, auth, monkeypatch):
    from tests.test_cotraitance_v4 import _alert_project
    import app.services.alerts as al
    import app.services.email as em
    monkeypatch.setattr(em, "send_email", lambda *a, **k: True)
    monkeypatch.setattr(al, "send_email", lambda *a, **k: True)
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid, (_inv,) = _alert_project(client, auth, days=5, n_partners=1, submit=True)
    db = _db()
    try:
        al.run_cotraitance_reminders(db)
    finally:
        db.close()
    assert client.post(f"/api/atelier/{pid}", headers=h, json={"base": "libre", "sans_ia": True}).status_code == 201
    rows = client.get(f"/api/projects/{pid}/audit", headers=h).json()
    sys_ = [x for x in rows if x["action"] == "piece.expiring"]
    moi = [x for x in rows if x["action"] in ("atelier.sans_ia", "invite.created")]
    assert sys_ and sys_[0]["actor_kind"] == "system" and sys_[0]["actor_label"] == "Adjugo", sys_
    assert moi and all(x["actor"].startswith("user:") or "@" in x["actor"] for x in moi), moi
    assert all(not str(x["actor_label"]).startswith("user:") for x in rows), [x["actor_label"] for x in rows]
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        nom = (u.full_name or "").strip() or u.email
    finally:
        db.close()
    assert all(x["actor_label"] == nom for x in moi), (nom, moi)
    # La ligne du journal : pastille « Adjugo » pour Adjugo, « Vous » pour l'entreprise, « Invité » pour un partenaire.
    bloc = zone(HTML, "marche-journal-acces")
    i = bloc.index('<div v-for="a in ao.share.audit"')
    tpl = bloc[i:bloc.index("</div>", i) + len("</div>")]
    cas = [{"ao": {"share": {"audit": [dict(x, at="2026-10-22T08:00:00")]}}}
           for x in (sys_[0], moi[0], {"id": 9, "action": "guest.view_project", "actor_kind": "guest",
                                       "actor": "Le Gall", "actor_label": "Le Gall", "detail": ""})]
    r = _rendre(tpl, ",\n".join(_methode(n) for n in ("auditLabel", "auditWhen", "auditAt")), cas,
                prelude=_fonction_js("_isoUtc"))
    assert re.search(r"10:00\s*Adjugo\s*Alerte", r[0]) and r[0].endswith("Adjugo"), r
    assert re.search(r"10:00\s*Vous\s*Réglage", r[1]) and r[1].endswith(nom) and "user:" not in r[1], r
    assert re.search(r"10:00\s*Invité\s*Consultation du dossier", r[2]), r


# ═══ 21. Convention : « 1 jour », pas « 1 jours » (nouveau modèle de texte) ══════════════════════════════════

def test_21_convention_accorde_jour_au_singulier_dans_le_modele_3_seulement(client, auth, groupes):
    from app.services import groupement_convention as gc
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                   json={"params": {"delai_reponse_jours": 1, "sortie_preavis_jours": 1, "confidentialite_annees": 1}})
    assert r.status_code == 200, r.text
    apercu = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["apercu_md"]
    c = _gen(client, h, pid).json()
    for texte in (apercu, c["content_md"]):
        assert "délai de 1 jours" not in texte and "de 1 jours :" not in texte and "1 jours avant" not in texte
        assert "dans un délai de 1 jour ; le silence" in texte and "de 1 jour :" in texte, texte
        assert "au moins 1 jour avant la date limite" in texte and "1 an après" in texte
    from app.models import GroupementConvention, Project
    db = _db()
    try:
        conv = db.query(GroupementConvention).filter(GroupementConvention.project_id == pid).one()
        project = db.get(Project, pid)
        assert conv.params["modele_texte"] == gc.MODELE_TEXTE == 3 and not gc.is_stale(db, project, conv)
        ctx = gc.build_context(db, project, conv, gc._company_for(db, project), version=conv.version)["ctx"]
        ctx["modele"] = 2              # une convention figée avec le modèle 2 garde son texte (et son empreinte)
        ancien = gc.render(ctx)
        assert "délai de 1 jours ;" in ancien and "au moins 1 jours avant" in ancien
        ctx["modele"] = 3
        ctx["params"] = dict(ctx["params"], delai_reponse_jours=2, sortie_preavis_jours=2)
        assert "délai de 2 jours ;" in gc.render(ctx) and "au moins 2 jours avant" in gc.render(ctx)
    finally:
        db.close()


# ═══ 22. Compte-rendu interne : le total au centime, comme la convention ════════════════════════════════════

def test_22_compte_rendu_total_de_l_offre_commune_au_centime(client, auth, groupes):
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=2)                       # 60 000 + 40 000 + 25 000,50
    assert _gen(client, h, pid).status_code == 200
    conv = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert "Total de l'offre commune : 125 000,50 € HT" in conv["content_md"]
    texte = _pdf_text(client.get(f"/api/projects/{pid}/consortium/report", headers=h).content)
    assert re.search(r"Offre commune figée le \d{2}/\d{2} : total 125 000,50 € HT", texte), \
        re.findall(r"Offre commune fig[^\n]*", texte)


# ═══ 23. Export ZIP : un sous-traitant n'est pas un partenaire du groupement ════════════════════════════════

def test_23_sommaire_du_zip_range_le_sous_traitant_a_part(client, auth):
    h = auth["headers"]
    client.put("/api/company/", headers=h, json=dict(_FICHE))
    pid = _project(client, h, name="Marché zip", deadline_days=20)
    r = client.post(f"/api/cotraitants/project/{pid}", headers=h,
                    json={"company": {"name": "Echafaudages Kerne", "siret": "98765432100011", "city": "Brest"},
                          "role": "sous_traitant", "lot": "Échafaudage"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text
    sommaire = zipfile.ZipFile(io.BytesIO(r.content)).read("00_SOMMAIRE.txt").decode("utf-8")
    assert "PARTENAIRES DU GROUPEMENT" not in sommaire, sommaire
    assert "SOUS-TRAITANTS DÉCLARÉS (DC4) (1)" in sommaire and "1. Echafaudages Kerne - SIRET: 98765432100011" in sommaire


def test_23_sommaire_du_zip_groupement_membres_et_sous_traitants(client, auth, groupes):
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    assert client.post(f"/api/cotraitants/project/{pid}", headers=h,
                       json={"company": {"name": "Echafaudages Kerne", "siret": "98765432100011"},
                             "role": "sous_traitant"}).status_code == 200
    _gen(client, h, pid)
    sommaire = zipfile.ZipFile(io.BytesIO(client.post(f"/api/export/{pid}", headers=h).content)).read(
        "00_SOMMAIRE.txt").decode("utf-8")
    membres = sommaire.split("PARTENAIRES DU GROUPEMENT", 1)[1].split("SOUS-TRAITANTS", 1)[0]
    assert "Le Gall Électricité" in membres and "Kerne" not in membres, sommaire
    assert "Echafaudages Kerne" in sommaire.split("SOUS-TRAITANTS DÉCLARÉS (DC4)", 1)[1], sommaire


# ═══ 24. Invitation du réseau à un sous-traitant : l'objet dit la même chose que le corps ═══════════════════

def test_24_objet_de_l_invitation_du_reseau_a_un_sous_traitant():
    from app.services.email_invitation import invitation
    kw = dict(chef="Breizh Couverture", marche="Réfection toiture école", url="https://adjugo.pro/invite/x")
    st = invitation(role="sous_traitant", reseau=True, **kw)
    assert st["objet"] == "Une entreprise vous propose d'intervenir comme sous-traitant — Réfection toiture école"
    assert invitation(role="sous_traitant", reseau=True, relance=True, **kw)["objet"] == (
        "Rappel : une entreprise vous propose d'intervenir comme sous-traitant — Réfection toiture école")
    assert invitation(role="cotraitant", reseau=True, **kw)["objet"] == (
        "Une entreprise vous propose un groupement — Réfection toiture école")
    assert invitation(role="sous_traitant", **kw)["objet"] == (
        "Invitation à répondre ensemble à un marché — Réfection toiture école")


# ═══ 25. Un sous-traitant décline : ni courriel ni écran ne parlent de « rejoindre le groupement » ══════════

def test_25_courriel_au_chef_de_file_quand_un_sous_traitant_decline(client, auth, groupes):
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid = _project(client, h, name="Marché déclin", deadline_days=20)
    texte = {}
    for role, nom in (("sous_traitant", "Echafaudages Kerne"), ("cotraitant", "Le Gall Électricité")):
        r = client.post(f"/api/projects/{pid}/invites", headers=h,
                        json={"recipient": f"{role}@kerne.example", "company_name": nom, "role": role})
        assert r.status_code == 200 and r.json()["role"] == role
        groupes.clear()
        assert client.post(f"/api/invite/{r.json()['token']}/decline").status_code == 200
        texte[role] = " ".join(m[2] for m in groupes)
    assert ("Echafaudages Kerne a décliné votre invitation à intervenir comme sous-traitant sur le marché "
            "« Marché déclin »." in texte["sous_traitant"]), texte
    assert "groupement" not in texte["sous_traitant"], texte
    assert ("Le Gall Électricité a décliné l'invitation à rejoindre le groupement sur le marché « Marché déclin »."
            in texte["cotraitant"]), texte


def test_25_fenetre_de_declin_selon_le_role_sous_node():
    fn = re.search(r"\n    function texteDeclin\(", INV)
    assert fn, "texteDeclin absent"
    src = INV[fn.start():_accolade_fermante(INV, INV.index("{", fn.end()))]
    r = _node(src + "\nconsole.log(JSON.stringify([texteDeclin({ invited: { role: 'sous_traitant' } }), "
                    "texteDeclin({ invited: { role: 'cotraitant' } })]));")
    assert "groupement" not in r[0] and "sous-traitant" in r[0], r
    assert r[1].startswith("Vous ne ferez plus partie de ce groupement"), r
    assert 'bodyHtml: texteDeclin(d)' in INV
    # Les mêmes fenêtres dans l'application (« Partagé avec moi », invitations reçues du réseau).
    script = "const o = {\n" + _methode("sharedDecline") + ",\n" + _methode("rnDecline") + r"""
};
const vus = [];
Object.assign(o, { confirmer: async (x) => { vus.push(x.lines[0]); return false; }, _convAsk: (x) => vus.push(x.lines[0]) });
(async () => {
  for (const role of ["sous_traitant", "cotraitant"]) {
    o.sharedAo = { role, token: "t" }; await o.sharedDecline(); o.rnDecline({ role, mandataire: "Breizh", token: "t" });
  }
  console.log(JSON.stringify(vus));
})();
"""
    r = _node(script)
    assert all("groupement" not in t and "sous-traitant" in t for t in r[:2]), r
    assert all("groupement" in t for t in r[2:]), r


# ═══ 26. Invitation d'un collègue par un compte sans nom ═════════════════════════════════════════════════════

def test_26_invitation_d_un_collegue_par_un_inviteur_sans_nom(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import User
    import app.services.email as em
    envoyes = []
    monkeypatch.setattr(em, "send_email", lambda to, s, t, *a, **k: envoyes.append((to, s, t)) or True)
    email = f"sansnom_{uuid.uuid4().hex[:6]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123", "full_name": "",
                                                "company_name": "Kerne Bâtiment"})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == email).first().email_verified = True
        db.commit()
    finally:
        db.close()
    r = client.post("/api/org/invite", headers={"Authorization": "Bearer " + r.json()["access_token"]},
                    json={"email": f"col_{uuid.uuid4().hex[:5]}@test.fr", "full_name": "Anne"})
    assert r.status_code == 201 and r.json()["emailed"] is True, r.text
    texte = next(t for _to, s, t in envoyes if s.startswith("Invitation à rejoindre"))
    assert texte.startswith("Bonjour,\n\nUn collègue vous invite à rejoindre l'espace « Kerne Bâtiment » sur Adjugo."), texte


# ═══ 27. Abonnement : « 1 j restant » le dernier jour de l'essai ═══════════════════════════════════════════════

def test_27_dernier_jour_de_l_essai_au_singulier_rendu_par_vue():
    i = HTML.index('<span v-if="plan.trial_state===\'active\'" class="pill go">')
    tpl = HTML[i:HTML.index("</span>", i) + len("</span>")]
    r = _rendre(tpl, "", [{"plan": {"trial_state": "active", "trial_days_left": n}} for n in (1, 2, 30)])
    assert r == ["Essai gratuit · 1 j restant", "Essai gratuit · 2 j restants", "Essai gratuit · 30 j restants"], r
