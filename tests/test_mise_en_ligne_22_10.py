"""
Réunion du 22/10 — REVUE de la réunion (85e5809). Document : docs/MISE_EN_LIGNE_22_10.md.

Chaque remarque de la revue a été reproduite sur le code réuni avant d'être corrigée ; chaque test ci-dessous échouait
sur 85e5809 (code, ou document qui disait autre chose que le code) :

  R1  décision 2 : la règle « rien vers une adresse non confirmée » ne couvre aujourd'hui que les alertes de marchés et
      les courriels vers des tiers ; « Demandez vos notes » et « pièces à renouveler » partent encore (fixé ici) ;
  R2  mise en ligne : par `railway up` depuis le bon dossier, jamais par un push vers GitHub ;
  R3  retour arrière : l'ancien code renvoie une fois TOUS les marchés revus par la nouvelle version qui passent son
      seuil, même ceux envoyés avant la mise en ligne (mécanisme de la mémoire des alertes, fixé ici) ;
  R4  retour arrière : `alembic stamp` (sans coupure ni perte) ; le downgrade réel coupe le service, c'est annoncé ;
  R5  `alembic current` dans la nouvelle image : « c4montantseul » sans « (head) » ;
  R6  démo de pitch : 184 + 2 + 4 = 190 réponses ;
  R7  fenêtre du SIRET, « Voir les marchés pour mon entreprise », « Chercher » des partenaires : le département du code
      postal suit la règle du serveur (outre-mer sur 3 chiffres ; Corse « 2A, 2B » pour la zone) ;
  R8  « Offre commune figée le … » : le jour local sur tous les écrans, comme la page du partenaire sans compte.

La migration (R3, R4, R5) est aussi rejouée sur PostgreSQL 16.2 depuis l'état exact de la production (section 5 du
document). Aucun appel réseau réel (courriels coupés) ; les fonctions de app.js et d'invite.html sous Node.

CONTRE-RELECTURE de la revue (002e2bb) : 2 remarques, reproduites, corrigées dans le document (le code ne change pas) ;
les tests CR1 et CR2 échouaient sur 002e2bb (le document disait autre chose que le code) :

  CR1 décision 1, « Qui est concerné » : le champ « Départements » de « À venir » (et de Publiés) est pré-rempli depuis
      le code postal de Mon entreprise pour TOUTE entreprise, déjà inscrite ou non ; la zone enregistrée dans Ce que
      je cherche n'y entre pas (onglet et route) ;
  CR2 retour arrière, étape 4 : l'ancien code ne plafonne pas le renvoi à 25 marchés par alerte (25 par source qui
      suit la limite, plus Mégalis, qui ne la suit pas ; la liste réunie n'est jamais coupée) — rejoué sur le code de
      production extrait par `git archive`.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta

import pytest

from tests.test_redaction_v6_carnet import _db, _get, _h, _marche, _set, _user_id
from tests.test_reorganisation_v2b_espace_partenaire import _fonction, _methode

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
INVITE = (STATIC / "invite.html").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "MISE_EN_LIGNE_22_10.md").read_text(encoding="utf-8")


def _plat(s: str) -> str:
    """Le texte sans ses retours à la ligne ni son retrait (un paragraphe Markdown est coupé à 120 colonnes)."""
    return " ".join(s.split())


def _section(debut: str, fin: str) -> str:
    assert DOC.count(debut) == 1, debut
    a = DOC.index(debut)
    return _plat(DOC[a:DOC.index(fin, a + len(debut))])


def _node_tz(script, tz="Europe/Paris", *args):
    """Node avec un fuseau donné (la suite tourne en TZ=UTC : l'heure locale de Paris doit être demandée)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, TZ=tz))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ═══ R1. Adresse non confirmée : ce qui part, ce qui ne part pas ═══════════════════════════════════════════════════

def test_r1_adresse_non_confirmee_ce_qui_part_et_ce_qui_ne_part_pas(client, auth, monkeypatch):
    """La règle telle qu'elle est (décision 2) : dans une même tournée planifiée, l'alerte de marchés n'est pas envoyée
    à une adresse non confirmée, mais « Demandez vos notes » l'est ; le récapitulatif « pièces à renouveler » aussi.
    Si la décision 2 (b) est prise, ce test change avec elle. Le document ne dit plus que c'est « la règle du reste de
    l'application »."""
    import app.services.alerts as al
    import app.services.email as em
    from app.models import Document, SavedSearch, User
    envois = []

    def _envoi(to, sujet, texte, *a, **k):
        envois.append((to, sujet, texte))
        return True
    monkeypatch.setattr(em, "send_email", _envoi)
    monkeypatch.setattr(al, "send_email", _envoi)
    h = _h(auth)
    pid = _marche(client, h)
    c = _get(pid)
    c["perdu_le"] = (datetime.utcnow() - timedelta(days=3)).replace(microsecond=0).isoformat()
    _set(pid, carnet_notes=c)
    uid = _user_id(auth["email"])
    db = _db()
    try:
        s = SavedSearch(user_id=uid, name="Toitures R1", query="toiture", active=True, frequency="quotidienne")
        doc = Document(user_id=uid, name="Attestation URSSAF R1", file_key="r1/urssaf.pdf",
                       expiration_date=date.today() + timedelta(days=5))
        db.add_all([s, doc])
        db.get(User, uid).email_verified = False
        db.commit()
        sid, doc_id = s.id, doc.id
    finally:
        db.close()
    marche = {"objet": "Réfection de toiture R1", "acheteur": "Ville", "score": 50, "date_limite": None, "lieu": "",
              "source": "BOAMP", "url": "https://exemple.invalid/avis", "ref": "26-1"}
    monkeypatch.setattr(al, "run_one_saved_search", lambda s, db, mark=True: [marche] if s.id == sid else [])
    # Les comptes des autres tests sont mis à l'écart comme le compte de démonstration : la tournée ne touche qu'à ce
    # compte (aucun drapeau d'envoi posé ailleurs).
    monkeypatch.setattr(al, "_demo_user_ids", lambda db: {u for (u,) in db.query(User.id).filter(User.id != uid).all()})
    try:
        res = al.run_tender_alerts(_db())
        al.run_document_expiry_alerts(_db())
    finally:
        db = _db()
        try:
            db.get(User, uid).email_verified = True
            db.query(SavedSearch).filter(SavedSearch.id == sid).update({SavedSearch.active: False})
            db.get(Document, doc_id).deleted_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
    mes = [(sujet, texte) for to, sujet, texte in envois if to == auth["email"]]
    assert not any("nouvel(s) appel(s) d'offres" in sujet for sujet, _ in mes)        # alerte de marchés : refusée
    assert res["rappels_notes_envoyes"] >= 1
    assert any(sujet.startswith("Adjugo — demandez vos notes") for sujet, _ in mes)  # même tournée : envoyé
    assert any("parce que vous avez des alertes actives" in texte for _, texte in mes)
    assert any("pièce à renouveler" in sujet for sujet, _ in mes)                     # récapitulatif : envoyé
    # Le document dit cette règle telle qu'elle est, et la laisse à Eliot.
    d2 = _section("2. **Adresses non confirmées", "3. **La bulle (i)")
    assert "règle du reste de l'application" not in d2           # (la revue, section 5, cite l'ancienne phrase)
    for x in ("Demandez vos notes", "pièces à renouveler", "_comptes_non_confirmes", "**(a)**", "**(b)**", "**(c)**",
              "test_r1_adresse_non_confirmee_ce_qui_part_et_ce_qui_ne_part_pas"):
        assert x in d2, x
    assert "ne reçoit plus d'alerte de marchés" in _plat(DOC)


# ═══ R2. Mettre en ligne : `railway up`, jamais un push ═══════════════════════════════════════════════════════════

def test_r2_la_mise_en_ligne_dit_la_vraie_procedure():
    m = _section("### Mettre en ligne", "### Revenir en arrière")
    assert "puis poussez" not in m and "Railway construit l'image ;" not in m
    for x in ("git merge --ff-only", "Ne poussez pas pour mettre en ligne", "railway up",
              "cd /Users/eliot/Downloads/adjugo-backend && npx -y @railway/cli@latest up -c -s adjugo-api",
              "git worktree add", "-e production -s adjugo-api", "`git status` vide", "projet parasite",
              "github.com/devlexus-cmd/adjugo", "287 commits"):
        assert x in m, x


# ═══ R3. Retour arrière : ce que l'ancien code renvoie ═════════════════════════════════════════════════════════════

def _avis(ref):
    from app.sourcing.schemas import NormalizedTender, Provenance
    return NormalizedTender(objet=f"Couverture {ref}", acheteur="Ville de Quimper", date_limite="2026-12-15",
                            provenance=Provenance(source="BOAMP", official_ref=ref,
                                                  source_url="https://www.boamp.fr/avis/detail/" + ref))


def test_r3_l_ancien_code_renvoie_tous_les_marches_revus_meme_envoyes_avant():
    """La mémoire que la production a écrite (références nues) : 26-1 et 26-2 envoyés AVANT la mise en ligne, 26-3 vu
    sous son seuil, 26-0 vu puis plus rendu par la recherche. La nouvelle version revoit 26-1 à 26-5 : elle réécrit
    l'entrée de chaque marché revu sous la forme nouvelle (« BOAMP|26-1 + 26-1 »). Après un retour arrière, la
    production teste `ref in set(last_seen_refs)` (0afc1ed, run_one_saved_search) : elle ne reconnaît plus aucun
    marché revu, même envoyé avant la mise en ligne, et le renvoie s'il passe son seuil ; 26-0, resté nu, reste
    reconnu. La nouvelle version, remise, ne renvoie rien."""
    from app.services.alerts import _jetons, _memoriser, _refs_du_marche
    memoire_prod = ["26-0", "26-1", "26-2", "26-3"]
    vus = []
    for ref in ("26-1", "26-2", "26-3", "26-4", "26-5"):
        nouvelles, anciennes = _refs_du_marche(_avis(ref))
        vus.append((nouvelles, set(nouvelles) | set(anciennes)))
    memoire = _memoriser(memoire_prod, vus)
    assert memoire[0] == "26-0" and "BOAMP|26-1 + 26-1" in memoire and "BOAMP|26-4" in memoire
    vus_par_la_production = set(memoire)                         # lecture de 0afc1ed : la référence nue, telle quelle
    renvoyes = [r for r in ("26-1", "26-2", "26-3", "26-4", "26-5") if r not in vus_par_la_production]
    assert renvoyes == ["26-1", "26-2", "26-3", "26-4", "26-5"]          # 26-1 et 26-2 compris (envoyés avant)
    assert "26-0" in vus_par_la_production                               # pas revu : reconnu
    connus = {j for e in memoire for j in _jetons(e)}
    assert all(set(c) & connus for _n, c in vus)                         # la nouvelle version remise : rien
    r = _section("### Revenir en arrière", "## 5. Les vérifications faites")
    assert "les marchés déjà envoyés depuis la mise en ligne" not in r
    for x in ("une fois tous les marchés que la nouvelle version a revus et qui passent son seuil, même ceux envoyés "
              "avant la mise en ligne", "3 marchés ont été renvoyés à l'alerte du chef de file, dont 2 envoyés avant "
              "la mise en ligne", "Le courriel en affiche 10 par alerte"):
        assert x in r, x
    # Le plafond de 25 par alerte n'existe pas (contre-relecture, CR2 : test_cr2_…, rejoué sur le code de production).
    assert "jusqu'à 25 marchés, dont 10 sont affichés" not in r


# ═══ R4 et R5. Retour arrière : `stamp` sans coupure ; ce qu'affiche `alembic current` ════════════════════════════

def test_r4_le_retour_arriere_recommande_est_sans_coupure_et_le_downgrade_l_annonce():
    r = _section("### Revenir en arrière", "## 5. Les vérifications faites")
    assert r.index("**`alembic stamp c4montantseul`**") < r.index("**`alembic downgrade c4montantseul`**")
    for x in ("ni coupure ni perte", "Les trois colonnes restent", "La nouvelle image continue de servir normalement",
              "rejoue `c5priseenmain` sans effet", "**Ce choix coupe le service**", "« erreur 500 »",
              "toute connexion, à toute inscription et à toute page d'un utilisateur connecté",
              "`/api/health` reste à 200", "Ne relancez jamais l'ancienne image avant l'étape 1"):
        assert x in r, x
    # La migration permet le `stamp` : rejouée sur une base qui a déjà les colonnes, elle ne fait rien.
    src = (ROOT / "alembic" / "versions" / "c5priseenmain_prise_en_main.py").read_text(encoding="utf-8")
    assert "if nom in _colonnes(bind, table):\n            continue" in src


def test_r5_alembic_current_dans_la_nouvelle_image_n_a_pas_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    sd = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert sd.get_heads() == ["c5priseenmain"]       # « (head) » ne suit c4montantseul que dans l'ancienne image
    r = _section("### Revenir en arrière", "## 5. Les vérifications faites")
    assert "vérifiez `alembic current` : `c4montantseul (head)`" not in r
    assert ("il affiche `c4montantseul`, **sans « (head) »**, car la tête de la nouvelle image est `c5priseenmain`. "
            "L'ancienne image, une fois relancée, affichera `c4montantseul (head)`") in r


# ═══ R6. Démo de pitch : le compte des réponses ════════════════════════════════════════════════════════════════════

def test_r6_le_compte_des_reponses_de_la_demo_tombe_juste():
    d = _plat(DOC)
    m = re.search(r"Sur \*\*(\d+) réponses, (\d+) sont identiques\*\*, (\d+) ne diffèrent que par l'ordre .*?, et les "
                  r"(\d+) autres ont seulement des champs ajoutés", d)
    assert m, "phrase du compte des réponses"
    total, identiques, ordre, ajouts = map(int, m.groups())
    assert (total, identiques, ordre, ajouts) == (190, 184, 2, 4) and identiques + ordre + ajouts == total


# ═══ R7. Le département d'un code postal, comme le serveur ═════════════════════════════════════════════════════════

CODES_POSTAUX = ["29200", "06000", "97400", "97110", "97300", "97600", "98800", "20000", "20200", "75001"]


def test_r7_le_departement_du_code_postal_suit_la_regle_du_serveur_sous_node():
    from app.services.decp import code_departement
    from app.sourcing.scoring import _dep_du_code_postal
    pur = _fonction(JS, "depDuCodePostal") + "\n" + _fonction(JS, "zoneDuCodePostal")
    r = _node_tz(pur + "\nconst cps = JSON.parse(process.argv[1]);\nconsole.log(JSON.stringify(cps.map(c => "
                 "[depDuCodePostal(c), zoneDuCodePostal(c)])));", "UTC", json.dumps(CODES_POSTAUX))
    for cp, (dep, zone_) in zip(CODES_POSTAUX, r):
        assert dep == _dep_du_code_postal(cp) == code_departement(cp), cp       # une seule règle, celle du serveur
        assert zone_ == ("2A, 2B" if cp.startswith("20") else dep), cp
    assert dict(zip(CODES_POSTAUX, r))["97400"] == ["974", "974"]


def test_r7_fenetre_du_siret_profil_et_partenaires_prennent_le_bon_departement_sous_node():
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    script = borne + "const o = {\n" + "\n".join(_methode(m) for m in (
        "welcomeStart", "srcPrefillFromProfile", "openDiscover")) + "\n};\n" + r"""
global.document = { getElementById() { return { focus() {} }; } };
async function cas(cp) {
  const j = { put: [] };
  Object.assign(o, { welcome: { siret: "12345678900012", busy: false, seul: "", seulInconnu: false }, company: {},
    criteria: { departements: "", specialites: "" }, src: { query: "", dept: "", prefilled: false, searched: false },
    discover: { open: false, results: [], dept: "" },
    notify() {}, go() {}, $nextTick() {}, srcSearch() {}, welcomeDone() {}, loadPriseEnMain() {}, loadTrades() {},
    api: async (m, p, b) => {
      if (p.startsWith("/api/registre")) return { name: "Couvreurs", siret: "12345678900012", postal_code: cp, specialite: "Couverture" };
      if (p === "/api/criteria/") j.put.push(JSON.parse(JSON.stringify(b)));
      return {};
    } });
  await o.welcomeStart();
  const fenetre = { criteres: j.put[0].departements, recherche: o.src.dept };
  o.src = { query: "", dept: "", prefilled: false, searched: false }; o.company = { postal_code: cp };
  o.srcPrefillFromProfile();
  o.openDiscover();
  return { fenetre, profil: o.src.dept, partenaires: o.discover.dept };
}
(async () => {
  const out = {};
  for (const cp of JSON.parse(process.argv[1])) out[cp] = await cas(cp);
  console.log(JSON.stringify(out));
})();
"""
    r = _node_tz(script, "UTC", json.dumps(["29200", "97400", "97110", "98800", "20000"]))
    assert r["29200"] == {"fenetre": {"criteres": "29", "recherche": "29"}, "profil": "29", "partenaires": "29"}
    assert r["97400"] == {"fenetre": {"criteres": "974", "recherche": "974"}, "profil": "974", "partenaires": "974"}
    assert r["97110"]["fenetre"] == {"criteres": "971", "recherche": "971"} and r["98800"]["profil"] == "988"
    # Corse : toute la Corse pour la zone et la recherche ; « 20 » pour les partenaires (le registre, comme avant).
    assert r["20000"] == {"fenetre": {"criteres": "2A, 2B", "recherche": "2A, 2B"}, "profil": "2A, 2B",
                          "partenaires": "20"}


def test_r7_ce_que_le_serveur_fait_de_ces_zones():
    """« 974 » (et non « 97 ») : un avis de la Guadeloupe est hors zone pour une entreprise de La Réunion ; « 2A, 2B »
    (et non « 20 ») : le BOAMP est interrogé sous « 20A » et « 20B », la DECP sous « 2A » et « 2B »."""
    from app.services.renewal import _departements_voulus
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.scoring import score_tender
    from app.sourcing.sources.boamp import formes_boamp
    t = NormalizedTender(objet="Voirie", acheteur="Ville de Pointe-à-Pitre", departements=["971"],
                         provenance=Provenance(source="BOAMP", official_ref="26-1", source_url="https://www.boamp.fr/x"))
    zone_de = lambda deps: next(c for c in score_tender(t, {"postal_code": "97400"}, {"departements": deps}).breakdown
                                if c.key == "zone").status
    assert zone_de("97") == "ok" and zone_de("974") != "ok"                   # avant / après la revue
    assert [f for d in "2A, 2B".split(",") for f in formes_boamp(d.strip())] == ["2A", "20A", "2B", "20B"]
    assert formes_boamp("20") == ["20"]                                       # « 20 » : aucun avis au BOAMP
    assert _departements_voulus("2A, 2B") == ["2A", "2B"]
    assert "La zone tirée du code postal suit la règle du serveur" in _plat(DOC)
    # Une entreprise déjà inscrite garde « 97 » ou « 20 » dans Ce que je cherche (rien n'est réécrit), mais pas dans le
    # champ de Trouver (contre-relecture, CR1 : test_cr1_…).
    assert "Une entreprise déjà inscrite par la fenêtre du SIRET y a « 97 » ou « 20 »" in _plat(DOC)


# ═══ R8. « Offre commune figée le … » : le même jour sur tous les écrans ═══════════════════════════════════════════

def test_r8_l_offre_figee_porte_le_jour_local_comme_la_page_du_partenaire_sous_node():
    # Toutes les dates d'une offre ou d'une convention figée dans app.html, et le formateur de chacune.
    vus = re.findall(r"\{\{\s*(\w+)\(([^{}]*?frozen_at)\)\s*\}\}", HTML)
    formateurs = sorted({f for f, _ in vus})
    assert len(vus) >= 5, vus
    invite = "\n".join(re.search(r"^ *(const " + n + r" = .*;)$", INVITE, re.M).group(1) for n in ("apiDate", "fmtShort"))
    script = (_fonction(JS, "_isoUtc") + "\n" + invite + "\nconst o = {\n"
              + "\n".join(_methode(m) for m in formateurs) + "\n};\n" + r"""
const out = {};
for (const s of JSON.parse(process.argv[1])) {
  out[s] = { invite: fmtShort(s) };
  for (const f of JSON.parse(process.argv[2])) out[s][f] = o[f](s);
}
console.log(JSON.stringify(out));
""")
    instants = ["2026-10-21T23:41:46.949140+00:00", "2026-10-21T23:41:46.949140", "2026-10-21T22:30:00",
                "2026-10-21T10:00:00+00:00", "2026-03-28T23:30:00"]
    r = _node_tz(script, "Europe/Paris", json.dumps(instants), json.dumps(formateurs))
    for s, v in r.items():
        for f in formateurs:
            assert v[f][:10] == v["invite"], (s, f, v)            # le même jour que la page du partenaire sans compte
    assert {x for f, x in vus if f == "convJour"} == {"ao.share.consortium.offre.frozen_at", "sfmState().frozen_at",
                                                      "apercuTotal().frozen_at"} and "fmtDate" not in formateurs
    assert r["2026-10-21T23:41:46.949140+00:00"]["convJour"] == "22/10/2026"   # 01:41 à Paris (avant : 21/10/2026)
    assert r["2026-10-21T10:00:00+00:00"]["convJour"] == "21/10/2026"
    assert "« Offre commune figée le … »** donne le même jour partout" in _plat(DOC)


# ═══ Contre-relecture de la revue (002e2bb) ════════════════════════════════════════════════════════════════════════

# ─── CR1. « À venir » part du code postal, pour toute entreprise ──────────────────────────────────────────────────

def test_cr1_a_venir_part_du_code_postal_pour_toute_entreprise_sous_node():
    """Une entreprise DÉJÀ inscrite, zone enregistrée « 97 » ou « 20 » dans Ce que je cherche (rien n'est réécrit),
    code postal 97400 ou 20000 : à l'ouverture de Trouver, le champ « Départements » est pré-rempli depuis le code
    postal (srcPrefillFromProfile), et « À venir » n'envoie que lui (srcRenewals → srcDeps). Sur 85e5809 : ["97"] et
    ["20"] ; depuis la revue (002e2bb) : ["974"] et ["2A", "2B"], quelle que soit la zone enregistrée. Le document
    disait le contraire (« elle garde l'ancien comportement … tant qu'elle ne corrige pas sa zone »)."""
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    script = borne + "const o = {\n" + "\n".join(_methode(m) for m in (
        "srcPrefillFromProfile", "srcDeps", "srcRenewals")) + "\n};\n" + r"""
async function cas(cp, zone) {
  const envois = [];
  Object.assign(o, { company: { postal_code: cp, specialites: "Voirie" }, criteria: { departements: zone },
    src: { query: "", dept: "", prefilled: false, searched: false, renewals: { loading: false, done: false, list: [] } },
    notify() {}, go() {},
    api: async (m, p, b) => { envois.push([m, p, JSON.parse(JSON.stringify(b || {}))]); return { renewals: [], count: 0 }; } });
  o.srcPrefillFromProfile();           // go("sourcing") : ouverture de Trouver
  await o.srcRenewals();               // onglet « À venir »
  return { champ: o.src.dept, envois, zone: o.criteria.departements };
}
(async () => {
  const out = {};
  for (const [cp, zone] of JSON.parse(process.argv[1])) out[cp + "|" + zone] = await cas(cp, zone);
  console.log(JSON.stringify(out));
})();
"""
    cas = [["97400", "97"], ["97400", "974"], ["97400", ""], ["20000", "20"], ["20000", "2A, 2B"], ["29200", "974"]]
    r = _node_tz(script, "UTC", json.dumps(cas))
    attendu = {"97400": ["974"], "20000": ["2A", "2B"], "29200": ["29"]}
    for cp, zone in cas:
        v = r[cp + "|" + zone]
        assert v["envois"] == [["POST", "/api/sourcing/renewals", {"query": "Voirie", "departements": attendu[cp]}]], (cp, zone, v)
        assert v["zone"] == zone                                    # Ce que je cherche : jamais réécrit
    assert r["97400|97"]["champ"] == "974" and r["20000|20"]["champ"] == "2A, 2B"
    # Le pré-remplissage a lieu à chaque ouverture de Trouver, pour tout compte ; Publiés envoie le même champ.
    assert re.search(r'if \(v === "sourcing"\) \{[^\n}]*this\.srcPrefillFromProfile\(\);', JS)
    assert re.search(r'"/api/sourcing/search",\s*\{ query: this\.src\.query, departements: this\.srcDeps\(\)', JS)
    assert JS.count("this.src.dept = ") == 3                   # fenêtre du SIRET, pré-remplissage, « Élargir »
    # Le document le dit (décision 1 et section 1), sans plus promettre l'ancien comportement aux comptes existants.
    d1 = _section("1. **Repli payant de l'onglet « À venir »", "2. **Adresses non confirmées")
    for x in ("toute entreprise dont le code postal (Mon entreprise) est en outre-mer ou en Corse, inscrite avant ou "
              "après cette mise en ligne", "`srcPrefillFromProfile`", "et non depuis Ce que je cherche",
              "toute entreprise qui saisit ces codes dans le champ", "elle passe sous cette règle dès la mise en ligne",
              "test_cr1_a_venir_part_du_code_postal_pour_toute_entreprise_sous_node",
              "test_cr1_la_route_a_venir_ne_lit_que_le_champ_de_l_onglet"):
        assert x in d1, x
    assert "tant qu'elle ne corrige pas sa zone" not in d1 and "garde l'ancien comportement" not in d1
    s1 = _section("## 1. Ce qui change pour les clients", "## 2. Les défauts de production corrigés")
    assert "Une entreprise déjà inscrite garde la zone enregistrée : rien n'est réécrit" not in s1
    for x in ("**Le champ « Départements » de Trouver des marchés suit la même règle pour toutes les entreprises, "
              "inscrites avant ou après la mise en ligne**", "Seule la zone déjà enregistrée dans Ce que je cherche "
              "n'est pas réécrite", "L'onglet n'envoie que son champ « Départements »"):
        assert x in s1, x


def test_cr1_la_route_a_venir_ne_lit_que_le_champ_de_l_onglet(client, auth, monkeypatch):
    """Côté serveur : POST /api/sourcing/renewals choisit ses départements dans la requête (le champ de l'onglet), pour
    la DECP comme pour le repli payant ; la zone enregistrée (« 97 ») ne sert qu'à la note des fins de contrat."""
    from app.services import decp, renewal
    h = _h(auth)
    assert client.put("/api/company/", headers=h, json={"name": "Voirie CR1", "postal_code": "97400"}).status_code == 200
    assert client.put("/api/criteria/", headers=h, json={"departements": "97"}).status_code == 200
    vus = []

    def _decp(query, departements, criteria, domaines=None):
        vus.append(("DECP", list(departements), (criteria or {}).get("departements")))
        return {"count": 0, "renewals": [], "errors": []}

    def _repli(query, departements, criteria, domaines=None, lang_name=None):
        vus.append(("repli", list(departements), (criteria or {}).get("departements")))
        return {"count": 0, "renewals": [], "errors": []}       # rien trouvé : analyse remboursée

    monkeypatch.setattr(decp, "detect_renewals_decp", _decp)
    monkeypatch.setattr(renewal, "detect_renewals", _repli)
    for champ, deps in ((["974"], ["974"]), (["2A", "2B"], ["2A", "2B"]), (["97"], ["97"]), ([], [])):
        vus.clear()
        r = client.post("/api/sourcing/renewals", headers=h, json={"query": "voirie", "departements": champ})
        assert r.status_code == 200, r.text
        assert vus == [("DECP", deps, "97"), ("repli", deps, "97")], (champ, vus)


# ─── CR2. Retour arrière : l'ancien code ne plafonne pas le renvoi à 25 ──────────────────────────────────────────

_ALERTE_DE_PRODUCTION = r'''
import json, sys, types
sys.path.insert(0, sys.argv[1])
import app.services.alerts as al
import app.services.profile as pr
import app.routers.sourcing as rs
import app.sourcing.sources.atexo as atexo
from app.sourcing.schemas import NormalizedTender, Provenance

def avis(src, i):
    t = NormalizedTender(objet=f"Voirie {src} {i}", acheteur=f"Acheteur {src} {i}", date_limite="2099-12-15",
                         departements=["29"], provenance=Provenance(source=src, official_ref=f"{src}-{i}",
                                                                    source_url=f"https://exemple.invalid/{src}/{i}"))
    t.dedup_key = f"{src}|{i}"
    return t

class SuitLaLimite:       # BOAMP et TED de 0afc1ed : min(criteria.limit, 50) lignes demandées
    def __init__(self, name): self.name = name
    def search(self, c): return [avis(self.name, i) for i in range(min(c.limit, 50))]

atexo._cached_fetch = lambda url, name, base: [avis("MEGALIS", i) for i in range(30)]   # 3 pages lues, sans réseau
atexo._refusee = lambda name: False
rs._tender_sources = lambda countries: [SuitLaLimite("BOAMP"), atexo.MEGALIS, SuitLaLimite("TED")]
pr.criteria_dict = lambda uid, db: {"go_threshold": 0}
pr.company_dict = lambda c: {}

class Q:
    def filter(self, *a): return self
    def first(self): return None

s = types.SimpleNamespace(user_id=1, query="voirie", cpv=[], departements=["29"], countries=[], montant_min=None,
                          montant_max=None, type_marche="", last_seen_refs=["BOAMP|BOAMP-0 + BOAMP-0"], min_score=None,
                          last_run=None)
fresh = al.run_one_saved_search(s, types.SimpleNamespace(query=lambda *a: Q()), mark=False)
print(json.dumps({"total": len(fresh), "par_source": {k: sum(1 for f in fresh if f["source"] == k)
                                                      for k in ("BOAMP", "MEGALIS", "TED")}}))
'''


def test_cr2_l_ancien_code_ne_plafonne_pas_le_renvoi_a_25_par_alerte(tmp_path):
    """Rejoué sur le code de PRODUCTION (0afc1ed, extrait par `git archive`) : run_one_saved_search passe limit=25 à
    chaque source ; BOAMP et TED en demandent 25, Mégalis (alerte bretonne) ne lit pas la limite, et
    TenderSearchService.search ne coupe jamais la liste réunie. Avec 25 + 30 + 25 avis encore inconnus de la mémoire
    (celle de la nouvelle version : « BOAMP|BOAMP-0 + BOAMP-0 » n'est pas reconnue, R3), l'alerte en renvoie 80. Le
    courriel en affiche 10 par alerte, avec leur nombre, et son objet donne le total. Le document disait « jusqu'à 25
    marchés »."""
    import io
    import sys
    import tarfile
    git = shutil.which("git")
    if not git or subprocess.run([git, "-C", str(ROOT), "cat-file", "-e", "0afc1ed^{commit}"],
                                 capture_output=True).returncode:
        pytest.skip("code de production (0afc1ed) absent de ce dépôt")
    arch = subprocess.run([git, "-C", str(ROOT), "archive", "--format=tar", "0afc1ed", "app"], capture_output=True,
                          check=True).stdout
    code = tmp_path / "code_0afc1ed"
    with tarfile.open(fileobj=io.BytesIO(arch)) as t:
        t.extractall(code, filter="data")
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp_path / 'prod.db'}", SMTP_HOST="", SMTP_USER="",
               BREVO_API_KEY="", ANTHROPIC_API_KEY="", MISTRAL_API_KEY="", MISTRAL_API_KEY_ADJUGO="", TZ="UTC")
    r = subprocess.run([sys.executable, "-I", "-c", _ALERTE_DE_PRODUCTION, str(code)], capture_output=True, text=True,
                       timeout=120, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-2000:]
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res == {"total": 80, "par_source": {"BOAMP": 25, "MEGALIS": 30, "TED": 25}}
    prod = lambda chemin: (code / chemin).read_text(encoding="utf-8")
    assert "limit=25," in prod("app/services/alerts.py")
    assert '"limit": min(criteria.limit, 50)' in prod("app/sourcing/sources/boamp.py")
    assert "lim = min(criteria.limit, 50)" in prod("app/sourcing/sources/ted.py")
    assert "for t in tenders[:10]:" in prod("app/services/alerts.py")                     # 10 affichés par alerte
    assert 'f"\\n● {name} ({len(tenders)} nouveau(x)) :"' in prod("app/services/alerts.py")   # avec leur nombre
    assert "{sum(len(t) for _, t in blocks)} nouvel(s) appel(s) d'offres" in prod("app/services/alerts.py")
    r4 = _section("### Revenir en arrière", "## 5. Les vérifications faites")
    assert "jusqu'à 25 marchés" not in r4
    for x in ("Ce renvoi n'est pas plafonné à 25 marchés par alerte", "25 avis à chaque source qui suit cette limite "
              "(BOAMP et TED, soit 50 au plus)", "tous ceux de Mégalis, qui ne la suit pas",
              "il ne coupe jamais la liste réunie", "Le courriel en affiche 10 par alerte, avec leur nombre, et son "
              "objet donne le total"):
        assert x in r4, x
