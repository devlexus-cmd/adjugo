"""
Réunion du 22/10 — REVUE de la réunion (85e5809). Document : docs/MISE_EN_LIGNE_22_10.md.

Chaque remarque de la revue a été reproduite sur le code réuni avant d'être corrigée ; chaque test ci-dessous échouait
sur 85e5809 (code, ou document qui disait autre chose que le code) :

  R1  décision 2 : la règle « rien vers une adresse non confirmée » ne couvrait que les alertes de marchés et les
      courriels vers des tiers ; « Demandez vos notes » et « pièces à renouveler » partaient encore. Eliot a pris
      l'option (b) le 22/10 : le test fixe désormais la règle unique (plus bas, « Décisions d'Eliot ») ;
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

DÉCISIONS D'ELIOT (22/10), appliquées sur 130fc9e ; chaque test échouait sur 130fc9e :

  D1  (b) le repli payant de « À venir » est remboursé en outre-mer et en Corse, seul ou avec d'autres départements,
      jusqu'à l'annonce du crédit à l'écran ; ailleurs, débité s'il trouve ; le journal dit la raison ;
  D2  (b) une seule règle pour les courriels planifiés vers le compte lui-même : rien vers une adresse non confirmée
      (alertes de marchés, « Demandez vos notes », « pièces à renouveler », veille amont), rien de marqué, envoi après
      la confirmation (tests R1) ;
  D3  (b) la bulle (i) de « Mes alertes » corrigée, traduite, et ce qu'elle dit vérifié dans le code.

RELECTURE des décisions (baf68de) : 7 remarques, dont deux en double ; le code des courriels ne change pas, chaque test
échouait sur baf68de (le document ou un commentaire disait autre chose que le code) :

  RD1 (remarques 1 et 6) le document de la décision 2 n'était plus vérifié par aucun test ;
  RD2 (remarques 2 et 5) le récapitulatif des attestations d'un marché créé par un collègue non confirmé n'attend pas
      la confirmation : il n'arrive qu'au palier suivant (exception dite, code inchangé, choix laissé à Eliot) ;
  RD3 (remarque 3) la veille amont rallumée ne reprend pas un projet lu avant la confirmation ;
  RD4 (remarque 4) un collègue invité est créé non confirmé, sans lien de confirmation (dit ; l'impact annoncé,
      rejeté : l'écran plein l'empêche de rien créer depuis l'application avant de confirmer) ;
  RD5 (remarque 7) docs/MOTEUR_LOT1.md disait que chaque test cité échouait sur 130fc9e.
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


# ═══ R1, puis décision 2 (b) du 22/10. Adresse non confirmée : aucun courriel planifié vers le compte ════════════════
# La revue (R1) avait fixé la règle telle qu'elle était sur 85e5809 et 130fc9e : l'alerte de marchés refusée, mais
# « Demandez vos notes » et « pièces à renouveler » envoyés à l'adresse non confirmée. Eliot a pris l'option (b) : ce
# test fixe la règle unique. Il échouait sur 130fc9e (« Demandez vos notes » et le récapitulatif partaient).

def _maj_user(uid, **cols):
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        for k, v in cols.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def _tournee(al):
    """La tournée planifiée du matin : alertes de marchés (avec « Demandez vos notes »), puis les pièces à renouveler."""
    res = al.run_tender_alerts(_db())
    al.run_document_expiry_alerts(_db())
    return res


def test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte(client, auth, monkeypatch):
    """Décision 2 (b) : dans une même tournée, une adresse non confirmée ne reçoit ni l'alerte de marchés, ni « Demandez
    vos notes », ni le récapitulatif « pièces à renouveler », avec la même fonction (_comptes_non_confirmes). Rien n'est
    marqué : la recherche n'est pas rejouée avec mark=True, aucun drapeau d'alerte n'est posé sur la pièce, aucun rappel
    n'est noté au carnet. Confirmée, la tournée suivante envoie les trois ; « Demandez vos notes » seulement dans ses
    14 jours (un marché perdu il y a 15 jours n'en reçoit pas)."""
    import app.services.alerts as al
    import app.services.email as em
    from app.models import Document, SavedSearch, User
    from app.services.carnet_notes import COURRIEL_FIN_JOURS
    assert COURRIEL_FIN_JOURS == 14
    envois, rejeux = [], []

    def _envoi(to, sujet, texte, *a, **k):
        envois.append((to, sujet, texte))
        return True
    monkeypatch.setattr(em, "send_email", _envoi)
    monkeypatch.setattr(al, "send_email", _envoi)
    h = _h(auth)
    recent, ancien = _marche(client, h), _marche(client, h, name="Couverture du gymnase")
    for pid, jours in ((recent, 3), (ancien, COURRIEL_FIN_JOURS + 1)):
        c = _get(pid)
        c["perdu_le"] = (datetime.utcnow() - timedelta(days=jours)).replace(microsecond=0).isoformat()
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

    def _rejeu(s, db, mark=True):
        if s.id != sid:
            return []
        rejeux.append(mark)
        return [marche]
    monkeypatch.setattr(al, "run_one_saved_search", _rejeu)
    # Les comptes des autres tests sont mis à l'écart comme le compte de démonstration : la tournée ne touche qu'à ce
    # compte (aucun drapeau d'envoi posé ailleurs).
    monkeypatch.setattr(al, "_demo_user_ids", lambda db: {u for (u,) in db.query(User.id).filter(User.id != uid).all()})

    def _drapeaux():
        db = _db()
        try:
            d = db.get(Document, doc_id)
            return (bool(d.alert_30_sent), bool(d.alert_7_sent), bool(d.alert_day_sent))
        finally:
            db.close()
    try:
        # 1) Adresse non confirmée : rien ne part, rien n'est marqué.
        assert uid in al._comptes_non_confirmes(_db())
        res = _tournee(al)
        assert [to for to, _s, _t in envois if to == auth["email"]] == []
        assert res["rappels_notes_envoyes"] == 0 and res["users_notified"] == 0
        assert rejeux == [False]                                   # recherche rejouée sans marquer « déjà vu »
        assert _drapeaux() == (False, False, False)                # pièce : aucun drapeau d'alerte
        assert "rappel_courriel" not in _get(recent) and "rappel_courriel" not in _get(ancien)
        # 2) Adresse confirmée : la tournée suivante envoie les trois courriels.
        _maj_user(uid, email_verified=True)
        envois.clear()
        res = _tournee(al)
    finally:
        _maj_user(uid, email_verified=True)
        db = _db()
        try:
            db.query(SavedSearch).filter(SavedSearch.id == sid).update({SavedSearch.active: False})
            db.get(Document, doc_id).deleted_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
    mes = [(sujet, texte) for to, sujet, texte in envois if to == auth["email"]]
    assert rejeux == [False, True]
    assert [x for x, _ in mes if "nouvel(s) appel(s) d'offres" in x] == ["Adjugo — 1 nouvel(s) appel(s) d'offres"]
    notes = [x for x, _ in mes if x.startswith("Adjugo — demandez vos notes")]
    assert res["rappels_notes_envoyes"] == 1 and notes == ["Adjugo — demandez vos notes : Toiture de l'école"]
    assert "rappel_courriel" in _get(recent) and "rappel_courriel" not in _get(ancien)   # 15 jours : plus de courriel
    assert [x for x, _ in mes if "pièce à renouveler" in x] == ["Adjugo — 1 pièce à renouveler"]
    assert _drapeaux() == (True, True, False)                      # palier « 7 jours » du jour de l'envoi


def test_r1_la_veille_amont_suit_la_meme_regle(client, auth, monkeypatch):
    """La veille amont (masquée, PROJETS_A_VENIR=0) est une autre tâche planifiée qui écrit au compte lui-même ;
    rallumée, elle suit la même règle : une adresse non confirmée n'est pas servie (aucun courriel, aucun projet
    enregistré pour elle), et l'est au premier passage après la confirmation. Sur 130fc9e, elle recevait le courriel."""
    import app.services.agents.amont as agents_amont
    import app.services.alerts as al
    import app.sourcing.sources.deliberations as deliberations
    from app.models import Signal, User
    monkeypatch.setenv("PROJETS_A_VENIR", "1")
    uid = _user_id(auth["email"])
    envois = []
    monkeypatch.setattr(al, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, sujet)) or True)
    monkeypatch.setattr(al, "_demo_user_ids", lambda db: {u for (u,) in db.query(User.id).filter(User.id != uid).all()})
    monkeypatch.setattr(deliberations.DeliberationSource, "fetch_recent", lambda self, *a, **k: [{"titre": "x"}])
    monkeypatch.setattr(agents_amont, "detect_from_deliberations", lambda *a, **k: [
        {"intitule": "Rénovation de la toiture de la mairie R1", "collectivite": "Ville de Brest", "source": "Brest"}])
    monkeypatch.setattr(agents_amont, "score_pertinence", lambda p, c, d=None: (80, "pertinent"))

    def _signaux():
        db = _db()
        try:
            return db.query(Signal).filter(Signal.user_id == uid).count()
        finally:
            db.close()
    _maj_user(uid, amont_alerts_enabled=True, email_verified=False)
    try:
        assert al.run_amont_alerts(_db()) == {"scanned": 0, "users_notified": 0, "new_signals": 0, "opted_in": 0}
        assert envois == [] and _signaux() == 0
        _maj_user(uid, email_verified=True)
        res = al.run_amont_alerts(_db())
    finally:
        _maj_user(uid, amont_alerts_enabled=False, email_verified=True)
    assert res["users_notified"] == 1 and _signaux() == 1
    assert envois == [(auth["email"], "Adjugo — 1 projet(s) détecté(s) en amont")]


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
  // Partie écran du lot 1 (point 11) : la fiche Identité n'a pas de spécialités, le pré-remplissage ne lit plus que son
  // code postal ; « Voirie » est tapé dans le champ des mots-clés de l'onglet (avant : une spécialité fictive de la fiche).
  Object.assign(o, { company: { postal_code: cp }, criteria: { departements: zone },
    src: { query: "Voirie", dept: "", prefilled: false, searched: false, renewals: { loading: false, done: false, list: [] } },
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


# ═══ Décisions d'Eliot (22/10) ══════════════════════════════════════════════════════════════════════════════════════
# Décision 2 : test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte et test_r1_la_veille_amont_suit_la_
# meme_regle (plus haut). Chaque test ci-dessous échouait sur 130fc9e.

# ─── Décision 1 (b) : le repli payant de « À venir » remboursé en outre-mer et en Corse ─────────────────────────────

def _compteurs(uid):
    from app.models import User
    db = _db()
    try:
        u = db.get(User, uid)
        return (u.trial_analyses_used or 0, u.analyses_used_this_month or 0)
    finally:
        db.close()


def test_d1_repli_a_venir_rembourse_en_outre_mer_et_en_corse(client, auth, monkeypatch, caplog):
    """La DECP ne donne rien, le repli (BOAMP + IA) trouve une fin de contrat. En outre-mer (« 974 », « 971 », « 988 »,
    « 97 ») et en Corse (« 2A, 2B », « 20 », un code postal corse), seul ou avec la métropole : l'analyse est remboursée,
    la fin de contrat est montrée, et le journal dit pourquoi. Ailleurs (métropole, toute la France) : débitée, comme
    avant. Sur 130fc9e, « 974 » et « 2A, 2B » étaient débités."""
    import logging
    from app.services import decp, renewal
    REMBOURSE_PAR_ZONE = "remboursée (outre-mer ou Corse, jusqu'à l'annonce du crédit à l'écran)"
    uid = _user_id(auth["email"])
    fin = {"idweb": "25-1", "objet": "Entretien de la voirie", "acheteur": "Ville", "lieu": "", "dept": "974",
           "date_attribution": "2023-01-10", "duree_mois": 36, "duree_estimee": True, "type_contrat": "",
           "fin_estimee": "2026-01-10", "renouvellement_estime": "2025-09-12", "score": 70, "url": "https://x.invalid"}
    demandes = []
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"count": 0, "renewals": [], "errors": []})

    def _repli(query, departements, criteria, domaines=None, lang_name=None):
        demandes.append(list(departements))
        return {"count": 1, "renewals": [dict(fin)], "errors": []}
    monkeypatch.setattr(renewal, "detect_renewals", _repli)
    cas = [(["974"], ["974"], False), (["971"], ["971"], False), (["988"], ["988"], False), (["97"], ["97"], False),
           (["2A", "2B"], ["2A", "2B"], False), (["20"], ["20"], False), (["20200"], ["20"], False),
           (["29", "974"], ["29", "974"], False), (["2B", "56"], ["2B", "56"], False),
           (["29"], ["29"], True), (["6"], ["06"], True), ([], [], True)]
    for champ, deps, debite in cas:
        _maj_user(uid, trial_analyses_used=0, analyses_used_this_month=0)
        caplog.clear()
        demandes.clear()
        with caplog.at_level(logging.INFO, logger="adjugo"):
            r = client.post("/api/sourcing/renewals", headers=_h(auth), json={"query": "voirie", "departements": champ})
        assert r.status_code == 200, (champ, r.text)
        assert [f["idweb"] for f in r.json()["renewals"]] == ["25-1"]          # la fin de contrat est montrée
        assert demandes == [deps], (champ, demandes)
        lignes = [x.getMessage() for x in caplog.records if "repli payant « À venir »" in x.getMessage()]
        assert len(lignes) == 1, (champ, lignes)
        if debite:
            assert _compteurs(uid) == (1, 1), champ
            assert "; analyse débitée ;" in lignes[0], (champ, lignes[0])
        else:
            assert _compteurs(uid) == (0, 0), champ
            assert f"; analyse {REMBOURSE_PAR_ZONE} ;" in lignes[0], (champ, lignes[0])
            assert "fins de contrat trouvées=1" in lignes[0]
    # Rien trouvé : remboursé partout ; en outre-mer et en Corse, le journal donne la même raison.
    monkeypatch.setattr(renewal, "detect_renewals", lambda *a, **k: {"count": 0, "renewals": [], "errors": []})
    for champ, raison in ((["974"], REMBOURSE_PAR_ZONE), (["29"], "remboursée")):
        _maj_user(uid, trial_analyses_used=0, analyses_used_this_month=0)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="adjugo"):
            r = client.post("/api/sourcing/renewals", headers=_h(auth), json={"query": "voirie", "departements": champ})
        assert r.status_code == 200 and _compteurs(uid) == (0, 0)
        lignes = [x.getMessage() for x in caplog.records if "repli payant « À venir »" in x.getMessage()]
        assert len(lignes) == 1 and f"; analyse {raison} ;" in lignes[0], lignes
    _maj_user(uid, trial_analyses_used=0, analyses_used_this_month=0)
    from app.routers.sourcing import REMBOURSE_PAR_ZONE as dans_le_code
    assert dans_le_code == REMBOURSE_PAR_ZONE


def test_d1_le_document_dit_la_decision():
    d1 = _section("1. **Repli payant de l'onglet « À venir »", "2. **Adresses non confirmées")
    for x in ("**Décidé le 22/10 : (b)**", "remboursé en outre-mer et en Corse", "seul ou avec d'autres départements",
              "débité s'il trouve, remboursé sinon", REMBOURSE_PAR_ZONE_DOC,
              "test_d1_repli_a_venir_rembourse_en_outre_mer_et_en_corse"):
        assert x in d1, x
    s1 = _section("### Trouver des marchés › À venir (fins de contrat)", "### Trouver des marchés › Mes alertes")
    assert "L'analyse est alors **débitée**" not in s1
    assert "l'analyse est **remboursée**, même s'il trouve" in s1
    nc = _section("### Ce qui ne change pas", "## 2. Les défauts de production corrigés")
    assert "peut désormais trouver, donc débiter, en Corse et en outre-mer" not in nc


REMBOURSE_PAR_ZONE_DOC = "« analyse remboursée (outre-mer ou Corse, jusqu'à l'annonce du crédit à l'écran) »"


# ─── Décision 3 (b) : la bulle (i) de « Mes alertes », corrigée et traduite ─────────────────────────────────────────

BULLE = ("Recevez par email les nouveaux marchés de cette recherche, 10 au plus par alerte, les autres comptés. "
         "Chaque envoi lit un nombre limité d'avis par source (au BOAMP, les 25 derniers publiés) : une recherche très "
         "large peut en avoir d'autres, à voir dans Adjugo. La recherche de l'onglet « Publiés » est enregistrée telle "
         "quelle.")


def test_d3_la_bulle_de_mes_alertes_dit_ce_que_fait_le_courriel():
    m = re.search(r'<b style="font-size:13\.5px">Mes alertes</b><button type="button" class="tip">.*?'
                  r'<span class="tip-b" role="tooltip">([^<]*)</span>', HTML)
    assert m and m.group(1) == BULLE, m and m.group(1)          # un seul nœud de texte : translateDOM le traduit entier
    assert "seuil de compatibilité" not in m.group(1)
    tete, corps = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)
    d = json.loads(corps[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for lg, mots in (("nl", ("maximaal 10 per melding", "de overige geteld", "BOAMP de 25 laatst gepubliceerde")),
                     ("es", ("10 como máximo por alerta", "las demás contabilizadas", "BOAMP, los 25 últimos"))):
        assert all(x in d[lg][BULLE] for x in mots), (lg, d[lg][BULLE])
        assert "drempel" not in d[lg][BULLE] and "umbral" not in d[lg][BULLE]
    d3 = _section("3. **La bulle (i) de « Mes alertes »**", "4. **Mesure du rappel avant le lot.**")
    assert "**Décidé le 22/10 : (b)**" in d3 and _plat(BULLE) in d3
    assert "« les autres comptés » n'est vrai que pour les avis que l'envoi lit" in d3
    alertes = _section("### Trouver des marchés › Mes alertes", "### Mes marchés et la page d'un marché")
    assert "C'est faux depuis ce lot" not in alertes and "dit encore « au-dessus de votre seuil" not in alertes


def test_d3_ce_que_dit_la_bulle_est_vrai(client, auth, monkeypatch):
    """« 10 au plus par alerte, les autres comptés » : 13 nouveaux marchés dans une alerte, 10 dans le courriel et la
    ligne « … et 3 autres marchés ». « un nombre limité d'avis par source (au BOAMP, les 25 derniers publiés) » : la
    tournée demande 25 avis à chaque source, et le BOAMP les trie du plus récent au plus ancien."""
    import app.services.alerts as al
    import app.services.email as em
    from app.models import SavedSearch, User
    from app.sourcing import http as sourcing_http
    from app.sourcing import search
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource
    assert al._MARCHES_PAR_ALERTE == 10
    uid = _user_id(auth["email"])
    db = _db()
    try:
        s = SavedSearch(user_id=uid, name="Voirie D3", query="voirie", active=True, frequency="quotidienne")
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()
    envois = []
    monkeypatch.setattr(em, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, sujet, texte)) or True)
    monkeypatch.setattr(al, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, sujet, texte)) or True)
    monkeypatch.setattr(al, "_demo_user_ids", lambda db: {u for (u,) in db.query(User.id).filter(User.id != uid).all()})
    marches = [{"objet": f"Voirie D3 n° {i}", "acheteur": "Ville", "score": 50, "date_limite": None, "lieu": "",
                "source": "BOAMP", "url": f"https://exemple.invalid/{i}", "ref": f"26-{i}"} for i in range(13)]
    monkeypatch.setattr(al, "run_one_saved_search", lambda s, db, mark=True: marches if s.id == sid else [])
    try:
        al.run_tender_alerts(_db())
    finally:
        db = _db()
        try:
            db.query(SavedSearch).filter(SavedSearch.id == sid).update({SavedSearch.active: False})
            db.commit()
        finally:
            db.close()
    mes = [(sujet, texte) for to, sujet, texte in envois if to == auth["email"]]
    assert len(mes) == 1 and mes[0][0] == "Adjugo — 13 nouvel(s) appel(s) d'offres"
    texte = mes[0][1]
    assert "● Voirie D3 (13 nouveau(x)) :" in texte
    assert sum(1 for i in range(13) if f"Voirie D3 n° {i} —" in texte) == 10
    assert "… et 3 autres marchés : relancez cette recherche dans Adjugo pour les voir tous." in texte
    # 25 avis demandés à chaque source par la tournée ; le BOAMP, les 25 derniers publiés.
    monkeypatch.undo()
    vus = []
    monkeypatch.setattr(search.TenderSearchService, "search", lambda self, crit, company=None, gonogo=None: (
        vus.append(crit.limit), {"tenders": [], "errors": []})[1])
    db = _db()
    try:
        al.run_one_saved_search(SavedSearch(user_id=uid, name="x", query="voirie", departements=["29"]), db, mark=False)
    finally:
        db.close()
    assert vus == [25]
    demandes = []

    class _Rep:
        def json(self):
            return {"results": []}

    def _get(url, params=None, **k):
        demandes.append(dict(params or {}))
        return _Rep()
    monkeypatch.setattr(sourcing_http, "get_with_retry", _get)
    BoampSource().search(TenderCriteria(query="voirie", departements=["29"], limit=25))
    assert demandes and demandes[0]["limit"] == 25 and demandes[0]["order_by"] == "-dateparution"


# ═══ Relecture des décisions d'Eliot (baf68de) ══════════════════════════════════════════════════════════════════════
# 7 remarques, dont deux en double (RD1 = remarques 1 et 6, RD2 = remarques 2 et 5). Chaque test ci-dessous échouait
# sur baf68de, par le document ou par un commentaire qui disait autre chose que le code ; le code des courriels ne
# change pas (les comportements fixés ici étaient déjà ceux de baf68de).

def _commentaire_auth():
    src = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    i = src.index("    # Email de confirmation. Choix du 24/06, gardé")
    return re.sub(r"\s*\n\s*#\s*", " ", src[i:src.index("    _send_verification(user)", i)])


def _docstring_non_confirmes():
    import app.services.alerts as al
    return _plat(al._comptes_non_confirmes.__doc__ or "")


D2_DEBUT, D2_FIN = "2. **Adresses non confirmées", "3. **La bulle (i)"
S1_DEBUT, S1_FIN = "### Inscription et confirmation de l'adresse", "### Fenêtre du SIRET et « Ce que je cherche »"


# ─── RD1 (remarques 1 et 6) : le document dit la décision 2 ─────────────────────────────────────────────────────────

def test_d2_le_document_dit_la_decision():
    """Les vérifications du document qu'avait l'ancien test R1 (130fc9e), parties avec lui, rétablies sur la décision
    prise : sans elles, la décision 2 réécrite en « (a), garder tel quel » laissait la suite verte (reproduit sur une
    copie de baf68de)."""
    d2 = _section(D2_DEBUT, D2_FIN)
    assert "règle du reste de l'application" not in d2
    assert "**Décidé le 22/10 : (b)**" in d2 and "**Décidé le 22/10 : (a)**" not in d2
    for x in ("`_comptes_non_confirmes`", "ni « Demandez vos notes » (`carnet_notes.envoyer_rappels`)",
              "ni récapitulatif « pièces à renouveler » (`run_document_expiry_alerts`)",
              "ni alerte de marchés (`run_tender_alerts`", "ni veille amont (`run_amont_alerts`)",
              "seulement dans ses 14 jours, `COURRIEL_FIN_JOURS`",
              "test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte",
              "test_r1_la_veille_amont_suit_la_meme_regle", "test_d2_le_document_dit_la_decision"):
        assert x in d2, x
    # Plus d'affirmation sans exception (RD2, RD3) : les deux exceptions sont dites.
    assert "tout part au premier passage après la confirmation" not in d2
    assert "Deux exceptions" in d2
    s1 = _section(S1_DEBUT, S1_FIN)
    for x in ("**Tant que l'adresse n'est pas confirmée, Adjugo ne lui envoie aucun courriel planifié**",
              "ni alerte de marchés, ni « Demandez vos notes », ni récapitulatif « pièces à renouveler »",
              "dans les 14 jours qui suivent le passage du marché à « Perdu »"):
        assert x in s1, x
    assert "ne reçoit plus d'alerte de marchés" in _plat(DOC)
    # La section 5 ne dit plus « aucun test retiré sans remplaçant » sans le manque, et nomme le test qui le comble.
    dec = _section("### Décisions d'Eliot (22/10/2026)", "### Relecture des décisions d'Eliot (22/10/2026)")
    assert "Aucun test n'est affaibli ni retiré sans remplaçant." not in dec
    assert "les vérifications du document sur la décision 2 étaient parties avec l'ancien test R1" in dec


# ─── RD2 (remarques 2 et 5) : le récapitulatif des attestations d'un marché de collègue ─────────────────────────────

def test_d2_le_recapitulatif_des_attestations_d_un_marche_de_collegue_attend_le_palier_suivant(client, auth, monkeypatch):
    """Propriétaire du compte confirmé, marché créé par un collègue (membre de l'équipe) qui a changé d'adresse : au
    palier J-7, le partenaire est prévenu et son alerte est notée (`piece.expiring`), rien au collègue. Le collègue
    confirme : le même palier ne lui envoie rien ; le palier J-3 lui envoie le récapitulatif. Témoin : propriétaire
    non confirmé, rien n'est noté ni envoyé ; confirmé, le partenaire et le récapitulatif partent dans le même palier.
    Comportement de la vague 2b, inchangé ; baf68de affirmait « ils partent au premier passage après la confirmation »
    sans cette exception (auth.py, docstring, document)."""
    import uuid
    import app.routers.invites as inv_router
    import app.services.alerts as al
    from app.models import AuditLog, User
    from tests.test_convention_groupement import _invite, _project
    envois = []
    monkeypatch.setattr(al, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, sujet)) or True)
    monkeypatch.setattr(inv_router, "_send_mails_async", lambda m: None)
    proprio = _user_id(auth["email"])
    r = client.post("/api/org/invite", headers=_h(auth), json={"email": f"collegue_{uuid.uuid4().hex[:8]}@test.fr",
                                                                "full_name": "Collègue RD2"})
    assert r.status_code == 201, r.text
    collegue, c_email, mdp = r.json()["id"], r.json()["email"], r.json()["temp_password"]
    _maj_user(collegue, email_verified=True)
    r = client.post("/api/auth/login", json={"email": c_email, "password": mdp})
    assert r.status_code == 200, r.text
    hc = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # La tournée ne touche qu'à ces deux comptes (les autres sont écartés comme le compte de démonstration).
    monkeypatch.setattr(al, "_demo_user_ids",
                        lambda db: {u for (u,) in db.query(User.id).filter(User.id.notin_([proprio, collegue])).all()})
    p_proprio = f"p_{uuid.uuid4().hex[:8]}@partenaire.fr"
    p_collegue = f"p_{uuid.uuid4().hex[:8]}@partenaire.fr"
    RECAP = "1 partenaire : attestation(s) à surveiller"

    def tournee(jour):
        envois.clear()
        db = _db()
        try:
            al._run_piece_expiry_alerts(db, jour)
        finally:
            db.close()
        return [(to, sujet) for to, sujet in envois if to in (auth["email"], c_email, p_proprio, p_collegue)]

    def notes(pid):
        db = _db()
        try:
            return db.query(AuditLog).filter(AuditLog.project_id == pid, AuditLog.action == "piece.expiring").count()
        finally:
            db.close()
    aujourd_hui = date.today()
    try:
        # Témoin : le marché du propriétaire, propriétaire non confirmé. Rien n'est noté : tout part après.
        pid_p = _project(client, _h(auth), name=f"AO RD2 propriétaire {uuid.uuid4().hex[:5]}", deadline_days=6)
        _invite(client, _h(auth), pid_p, "Partenaire du propriétaire SARL", recipient=p_proprio)
        _maj_user(proprio, email_verified=False)
        assert tournee(aujourd_hui) == [] and notes(pid_p) == 0
        _maj_user(proprio, email_verified=True)
        vus = tournee(aujourd_hui)
        assert [to for to, _s in vus if to == p_proprio] == [p_proprio]
        recap = [s for to, s in vus if to == auth["email"]]
        assert len(recap) == 1 and recap[0].startswith(RECAP), vus
        # L'exception : le marché du collègue, collègue non confirmé (changement d'adresse), propriétaire confirmé.
        pid_c = _project(client, hc, name=f"AO RD2 collègue {uuid.uuid4().hex[:5]}", deadline_days=6)
        _invite(client, hc, pid_c, "Partenaire du collègue SARL", recipient=p_collegue)
        _maj_user(collegue, email_verified=False)
        vus = tournee(aujourd_hui)                                          # palier J-7
        assert [to for to, _s in vus] == [p_collegue] and notes(pid_c) == 1  # le partenaire, noté ; rien au collègue
        _maj_user(collegue, email_verified=True)
        assert tournee(aujourd_hui) == []                                   # confirmé, même palier : rien
        vus = tournee(aujourd_hui + timedelta(days=3))                      # palier J-3
        recap = [s for to, s in vus if to == c_email]
        assert len(recap) == 1 and recap[0].startswith(RECAP), vus
    finally:
        _maj_user(proprio, email_verified=True)
        _maj_user(collegue, email_verified=True)
    # Les trois textes disent l'exception (et plus « ils partent » sans elle).
    c = _commentaire_auth()
    assert "ils partent au premier passage après la confirmation" in c        # (test_s5 de la vague 2b)
    for x in ("sauf deux exceptions", "le récapitulatif des attestations d'un marché créé par un collègue non confirmé",
              "le collègue confirmé n'a que le récapitulatif du palier suivant"):
        assert x in c, x
    doc = _docstring_non_confirmes()
    for x in ("sauf deux exceptions", "le récapitulatif des attestations d'un marché créé par un collègue non confirmé",
              "n'a que le récapitulatif du palier suivant (J-3), aucun si c'était déjà J-3",
              "Propriétaire non confirmé : rien n'est noté, tout part après"):
        assert x in doc, x
    d2 = _section(D2_DEBUT, D2_FIN)
    for x in ("**le récapitulatif des attestations des partenaires d'un marché créé par un collègue**",
              "son alerte est notée pour tout le palier, J-7 ou J-3 (`_piece_alerts_due`)",
              "seulement celui du palier suivant (J-3)", "au palier J-3, il n'en reçoit aucun",
              "Quand c'est le propriétaire du compte qui n'est pas confirmé, rien n'est noté",
              "test_d2_le_recapitulatif_des_attestations_d_un_marche_de_collegue_attend_le_palier_suivant"):
        assert x in d2, x
    assert "n'arrive qu'au palier suivant (section 3, décision 2)" in _section(S1_DEBUT, S1_FIN)
    plus_tard = _section("### Plus tard (rien ne bloque la mise en ligne)", "## 4. Procédure")
    assert "**Récapitulatif des attestations d'un marché créé par un collègue non confirmé**" in plus_tard


# ─── RD3 (remarque 3) : la veille amont rallumée ne reprend pas un projet lu avant la confirmation ─────────────────

def test_d2_la_veille_amont_ne_reprend_pas_un_projet_lu_avant_la_confirmation(client, auth, monkeypatch):
    """Deux abonnés à la veille amont rallumée : un compte confirmé, et ce compte, non confirmé. Passage 1 : le projet A
    est lu, enregistré et envoyé pour l'autre abonné, rien pour ce compte. Il confirme. Passage 2 : seul le projet B est
    encore dans les délibérations lues. Ce compte n'a que B ; A n'est jamais enregistré ni envoyé pour lui. baf68de
    disait seulement « elle suit la même règle » (document) et « ils partent au premier passage » (auth.py)."""
    import uuid
    import app.services.agents.amont as agents_amont
    import app.services.alerts as al
    import app.sourcing.sources.deliberations as deliberations
    from app.models import Signal, User
    monkeypatch.setenv("PROJETS_A_VENIR", "1")
    uid = _user_id(auth["email"])
    autre_email = f"autre_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": autre_email, "password": "motdepasse123",
                                                "full_name": "Autre abonné", "company_name": "Autre SARL"})
    assert r.status_code == 201, r.text
    autre = _user_id(autre_email)
    envois = []
    monkeypatch.setattr(al, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, texte)) or True)
    monkeypatch.setattr(al, "_demo_user_ids",
                        lambda db: {u for (u,) in db.query(User.id).filter(User.id.notin_([uid, autre])).all()})
    monkeypatch.setattr(deliberations.DeliberationSource, "fetch_recent", lambda self, *a, **k: [{"titre": "x"}])
    lus = [[{"intitule": "Projet A RD3, lu avant la confirmation", "collectivite": "Ville A", "source": "A"}],
           [{"intitule": "Projet B RD3, lu après la confirmation", "collectivite": "Ville B", "source": "B"}]]
    monkeypatch.setattr(agents_amont, "detect_from_deliberations", lambda *a, **k: lus.pop(0))
    monkeypatch.setattr(agents_amont, "score_pertinence", lambda p, c, d=None: (80, "pertinent"))

    def signaux(u):
        db = _db()
        try:
            return sorted(s.intitule for s in db.query(Signal).filter(Signal.user_id == u).all())
        finally:
            db.close()
    _maj_user(uid, amont_alerts_enabled=True, email_verified=False)
    _maj_user(autre, amont_alerts_enabled=True, email_verified=True)
    try:
        r1 = al.run_amont_alerts(_db())
        assert r1["users_notified"] == 1 and signaux(uid) == []
        assert signaux(autre) == ["Projet A RD3, lu avant la confirmation"]
        assert [to for to, _t in envois] == [autre_email]
        _maj_user(uid, email_verified=True)
        envois.clear()
        al.run_amont_alerts(_db())
    finally:
        _maj_user(uid, amont_alerts_enabled=False, email_verified=True)
        _maj_user(autre, amont_alerts_enabled=False)
    assert signaux(uid) == ["Projet B RD3, lu après la confirmation"]          # A n'est jamais repris pour ce compte
    mes = [t for to, t in envois if to == auth["email"]]
    assert len(mes) == 1 and "Projet B RD3" in mes[0] and "Projet A RD3" not in mes[0]
    # Les textes le disent.
    c = _commentaire_auth()
    assert ("la veille amont, qui n'enregistre aucun projet pour une adresse non confirmée et ne reprend ensuite que "
            "ceux des délibérations qu'elle lit alors") in c
    assert ("un projet lu entre-temps et sorti des délibérations récentes n'est jamais ajouté"
            in _docstring_non_confirmes())
    src = _plat((ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8").replace("#", ""))
    assert "Un projet lu entre-temps (pour les autres abonnés) et sorti des délibérations récentes n'est donc jamais" in src
    d2 = _section(D2_DEBUT, D2_FIN)
    for x in ("**la veille amont, si elle est rallumée**", "elle n'enregistre pas non plus les projets de « Projets à venir »",
              "un projet lu entre-temps et sorti des délibérations récentes n'est jamais ajouté pour ce compte, ni envoyé",
              "À trancher au rallumage", "test_d2_la_veille_amont_ne_reprend_pas_un_projet_lu_avant_la_confirmation"):
        assert x in d2, x
    plus_tard = _section("### Plus tard (rien ne bloque la mise en ligne)", "## 4. Procédure")
    assert "**Veille amont, au moment de la rallumer**" in plus_tard
    moteur = _plat((ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8"))
    assert ("la veille amont, rallumée, n'enregistre aucun projet pour une adresse non confirmée et ne reprend ensuite "
            "que ceux des délibérations qu'elle lit alors") in moteur


# ─── RD4 (remarque 4) : un collègue invité est créé non confirmé, sans lien de confirmation ─────────────────────────

def test_d2_un_collegue_invite_est_cree_non_confirme_sans_lien_de_confirmation(client, auth, monkeypatch):
    """POST /api/org/invite crée le collègue non confirmé (il entre dans _comptes_non_confirmes) ; seul le courriel
    d'invitation part, avec le mot de passe provisoire et sans lien ; la connexion n'en envoie pas non plus ;
    « Renvoyer l'email de vérification » l'envoie. L'écran plein « Confirmez votre adresse email » vaut pour tout
    compte non confirmé, collègue compris. Le document (baf68de) ne citait que le changement d'adresse."""
    import uuid
    import app.routers.auth as auth_router
    import app.services.alerts as al
    import app.services.email as em
    liens, envois = [], []
    monkeypatch.setattr(auth_router, "_send_verification", lambda u: liens.append(u.email))
    monkeypatch.setattr(em, "send_email", lambda to, sujet, texte, *a, **k: envois.append((to, sujet, texte)) or True)
    email = f"collegue_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/org/invite", headers=_h(auth), json={"email": email, "full_name": "Collègue RD4"})
    assert r.status_code == 201, r.text
    cid, mdp = r.json()["id"], r.json()["temp_password"]
    try:
        assert cid in al._comptes_non_confirmes(_db())
        assert [to for to, _s, _t in envois] == [email]                     # un seul courriel : l'invitation
        sujet, texte = envois[0][1], envois[0][2]
        assert sujet.startswith("Invitation à rejoindre") and "Mot de passe provisoire" in texte
        assert "verify" not in texte and liens == []                       # aucun lien de confirmation
        r = client.post("/api/auth/login", json={"email": email, "password": mdp})
        assert r.status_code == 200, r.text
        hc = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert liens == []                                                 # ni à la connexion
        assert client.get("/api/auth/me", headers=hc).json()["email_verified"] is False
        assert client.post("/api/auth/resend-verification", headers=hc).status_code == 200
        assert liens == [email]                                            # « Renvoyer » : le lien part
    finally:
        _maj_user(cid, email_verified=True)
    # L'écran plein bloque tout compte non confirmé, sans condition de rôle, et dit qu'un lien a été envoyé.
    assert ('data-test="ecran-confirmation-email" v-if="token && user && user.id && user.email_verified===false"'
            in HTML)
    assert "Un lien de confirmation vous a été envoyé par email" in HTML
    assert "Renvoyer l'email de vérification</button>" in HTML
    s1 = _section(S1_DEBUT, S1_FIN)
    for x in ("**un collègue invité depuis Réglages › Collègues**", "aucun lien de confirmation ne lui est envoyé, ni à "
              "l'invitation", "ni à la connexion", "« Renvoyer l'email de vérification »",
              "**un compte qui change d'adresse**", "C'est le seul cas où la décision retire des courriels à un client",
              "ne peut rien créer depuis l'application avant d'avoir confirmé (ni alerte, ni marché, ni pièce)",
              "« Un lien de confirmation vous a été envoyé par email », ce qui est faux pour lui"):
        assert x in s1, x
    d2 = _section(D2_DEBUT, D2_FIN)
    for x in ("un collègue invité depuis Réglages › Collègues sont aussi non confirmés",
              "Le collègue invité ne reçoit aucun lien de confirmation, ni à l'invitation ni à la connexion",
              "C'est le seul compte à qui la décision retire des courriels",
              "test_d2_un_collegue_invite_est_cree_non_confirme_sans_lien_de_confirmation"):
        assert x in d2, x
    plus_tard = _section("### Plus tard (rien ne bloque la mise en ligne)", "## 4. Procédure")
    assert "**Collègue invité : aucun lien de confirmation** (production, inchangé)" in plus_tard
    c = _commentaire_auth()
    assert ("Un collègue invité (org.invite_member) est créé non confirmé et ne reçoit aucun lien de confirmation, ni à "
            "l'invitation ni à la connexion") in c


# ─── RD5 (remarque 7) : le contrat du moteur dit quel test D3 passait déjà ──────────────────────────────────────────

def test_d3_le_contrat_du_moteur_dit_quel_test_passait_deja():
    """Reproduit sur une extraction de 130fc9e avec les tests de baf68de : test_d3_la_bulle_… échoue,
    test_d3_ce_que_dit_la_bulle_est_vrai passe (il fixe ce que la bulle affirme). MOTEUR_LOT1.md disait « Chaque test
    cité échouait sur 130fc9e »."""
    m = _plat((ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8"))
    a = m.index("## Décisions d'Eliot (22/10/2026)")
    dec = m[a:]
    assert "Chaque test cité échouait sur `130fc9e`" not in dec
    assert ("`test_d3_ce_que_dit_la_bulle_est_vrai` passait déjà sur `130fc9e` : il fixe ce que la bulle affirme"
            in dec)
    assert "Les autres tests cités échouaient sur `130fc9e`" in dec
    # Le bilan disait déjà juste (« passait déjà »).
    assert "`test_d3_ce_que_dit_la_bulle_est_vrai` (passait déjà : il fixe ce que la bulle affirme)" in _plat(DOC)
