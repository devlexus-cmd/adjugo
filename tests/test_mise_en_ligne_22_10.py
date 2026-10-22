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
              "la mise en ligne", "jusqu'à 25 marchés, dont 10 sont affichés"):
        assert x in r, x


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
    assert "Une entreprise déjà inscrite par cette fenêtre a « 97 » ou « 20 »" in _plat(DOC)


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
