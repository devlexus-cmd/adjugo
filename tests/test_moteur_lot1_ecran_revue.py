"""Revue de la partie écran du lot 1 « Dire juste » (docs/MOTEUR_LOT1.md, section « Écran », « Revue »). Chaque test
échoue sur ba07980 (la partie écran avant sa revue), sur le défaut qu'il couvre.

  R1. La bulle du crédit de « À venir » disait « Il faut une analyse disponible pour la lancer » : faux au paiement à
      l'usage, où le repli payant part sans analyse restante et est facturé hors forfait (quota.consume_analysis). Et
      rien ne disait, avant le clic, qu'il serait facturé.
  R2. La bulle d'en-tête de « À venir » ne parlait que de la DECP (date de notification, durée publiée) ; au repli, la
      fin part de la parution de l'avis d'attribution du BOAMP, avec une durée lue ou estimée.
  R3. « (durée estimée selon le type de contrat) » aussi sans type de contrat : la durée est alors 36 mois par défaut.
  R4. La bulle de « Date limite non précisée » affirmait que le rectificatif « porte sur sa date limite » ; le serveur
      le pose aussi, par prudence, sur des formes dont il ne sait pas s'ils en parlent.
  R5. Des codes CPV sans spécialité : « Dites d'abord votre métier », alors que le produit tient ce métier pour dit.
  R6. Le sous-titre de « Voir les marchés pour mon entreprise » promettait « le département de votre code postal » ; le
      bouton cherche dans les départements du champ de la recherche.
  R7. Le contrat et le bilan disaient encore « (estimée) », « rien de visible », une note d'adéquation que le client
      verrait bouger, et « trois chantiers ».

Sans réseau : IA et sources simulées, fonctions de app.js sous Node.
"""
import json
import pathlib
import re
from datetime import date, timedelta

from tests.test_moteur_lot1_ecran import (
    BULLE_A_VENIR, BULLE_CREDIT, BULLE_NON_LUE, CARTE, CREDIT, DUREE_PAR_DEFAUT, FACTURE_A, FACTURE_B, HTML, JS,
    MANQUE_METIER, MANQUE_METIER_CPV, RADAR, SOUS_TITRE, TROUVER, _compteurs, _dico, _fonction, _methode, _node,
    _plat, _sans_commentaires)

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ═══ R1. Le crédit au paiement à l'usage ═══════════════════════════════════════════════════════════════════════════

def _regler(uid, **cols):
    from app.models import User
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        u = db.get(User, uid)
        for k, v in cols.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def _lire(uid, *cols):
    from app.models import User
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        u = db.get(User, uid)
        return tuple(getattr(u, c) for c in cols)
    finally:
        db.close()


_SCRIPT_FORFAIT = r"""
const o = {
__METHODES__
};
const out = {};
const cas = JSON.parse(process.argv[1]);
for (const k in cas) { o.stats = cas[k]; out[k] = o.srcRenHorsForfait(); }
console.log(JSON.stringify(out));
"""


def test_r1_le_credit_dit_vrai_au_paiement_a_l_usage(client, auth, monkeypatch):
    """Sur ba07980 : « Il faut une analyse disponible pour la lancer. » Par la route : un forfait Pro, client Stripe
    connu, paiement à l'usage activé, 30 analyses sur 30 : le repli part, 200, « analyse » : « debitee », 31 utilisées,
    1 analyse hors forfait déclarée à Stripe ; vide, il est remboursé et la déclaration annulée ; paiement à l'usage
    coupé : refusé (402), rien de débité. L'écran le dit avant le clic, avec le prix du compteur."""
    from app.core import quota
    from app.services import billing_usage, decp, renewal
    from tests.test_redaction_socle0 import _user_id
    # La bulle : la règle réelle sans analyse restante ; la phrase fausse a disparu (néerlandais et espagnol compris).
    assert f'<span class="tip-b" role="tooltip">{BULLE_CREDIT}</span>' in RADAR
    visible = _plat(_sans_commentaires(HTML))
    assert "Il faut une analyse disponible pour la lancer" not in visible
    d = _dico()
    assert "betalen per gebruik" in d["nl"][BULLE_CREDIT] and "pago por uso" in d["es"][BULLE_CREDIT]
    # La ligne qui dit, avant le clic, que ce clic serait facturé : entre la ligne du crédit et les résultats.
    ligne = ('<p v-if="!estDemo() && srcRenHorsForfait()" id="avenir-facture" class="avenir-credit avenir-facture small" '
             'role="note"><i data-lucide="alert-circle" aria-hidden="true"></i><span><span>' + FACTURE_A + '</span> '
             '<span>{{ stats.usage.overage_price }} €</span> <span>' + FACTURE_B + '</span></span></p>')
    assert ligne in RADAR
    assert RADAR.index(CREDIT) < RADAR.index(ligne) < RADAR.index('v-for="r in src.renewals.list"')
    assert "avenir-credit avenir-facture" in RADAR.split("Chercher les fins de contrat</button>")[0]   # aria-describedby

    from app.core.quota import settings
    uid = _user_id(auth["email"])
    lim = int(settings.PLAN_LIMITS["pro"]["analyses"])
    declares, annules = [], []
    monkeypatch.setattr(billing_usage, "report_overage", lambda u, db=None: declares.append(u.id))
    monkeypatch.setattr(billing_usage, "cancel_overage", lambda u, db=None: annules.append(u.id))
    fin = {"idweb": "25-34232", "objet": "Voirie", "acheteur": "Ville", "lieu": "Voirie", "dept": "29",
           "date_attribution": "2025-01-30", "duree_mois": 36, "duree_estimee": True, "type_contrat": "",
           "fin_estimee": "2028-01-29", "renouvellement_estime": "2027-10-01", "score": 70, "url": "https://x.invalid"}
    repli = {"v": [fin]}
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"count": 0, "renewals": [], "errors": [],
                                                                      "source": "DECP"})
    monkeypatch.setattr(renewal, "detect_renewals", lambda *a, **k: {"count": len(repli["v"]),
                                                                    "renewals": list(repli["v"]), "errors": []})

    def regler(usage_active):
        _regler(uid, plan="pro", stripe_customer_id="cus_essai_local", overage_enabled=usage_active,
                analyses_used_this_month=lim, overage_count=0, analyses_period=quota._period())

    def demande():
        return client.post("/api/sourcing/renewals", headers=auth["headers"],
                           json={"query": "voirie", "departements": ["29"]})

    regler(True)
    # Ce que lit l'écran (GET /api/agent/stats, stats.usage) : la ligne s'affiche pour ce compte, avec le vrai prix.
    stats = client.get("/api/agent/stats", headers=auth["headers"]).json()
    u = stats["usage"]
    assert (u["plan"], u["analyses_limit"], u["analyses_remaining"], u["overage_enabled"]) == ("pro", lim, 0, True)
    assert u["overage_price"] == quota.OVERAGE_PRICE and "quota_scope" not in u
    script = _SCRIPT_FORFAIT.replace("__METHODES__", _methode("srcRenHorsForfait"))
    autres = {"reste": dict(u, analyses_remaining=3), "coupe": dict(u, overage_enabled=False),
              "essai": dict(u, plan="trial", quota_scope="essai"), "starter": dict(u, plan="starter"),
              "sans_compteur": None}
    vus = _node(script, json.dumps({"pro_a_zero": stats, **{k: ({"usage": v} if v else {}) for k, v in autres.items()}}))
    assert vus == {"pro_a_zero": True, "reste": False, "coupe": False, "essai": False, "starter": False,
                   "sans_compteur": False}

    # « Sans analyse restante, elle n'est lancée qu'avec le paiement à l'usage activé … facturée au tarif à l'usage »
    r = demande()
    assert r.status_code == 200, r.text
    assert r.json()["analyse"] == "debitee" and r.json()["source"] == "BOAMP"
    assert _lire(uid, "analyses_used_this_month", "overage_count") == (lim + 1, 1) and declares == [uid]
    # « … et remboursée dans les mêmes cas » : le repli ne trouve rien, l'analyse hors forfait est rendue et annulée.
    regler(True)
    repli["v"] = []
    r = demande()
    assert r.status_code == 200 and r.json()["analyse"] == "remboursee"
    assert _lire(uid, "analyses_used_this_month", "overage_count") == (lim, 0) and annules == [uid]
    # Toujours remboursée en outre-mer et en Corse, même au paiement à l'usage, même s'il trouve.
    regler(True)
    repli["v"] = [fin]
    r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie", "departements": ["974"]})
    assert r.status_code == 200 and r.json()["analyse"] == "remboursee"
    assert _lire(uid, "analyses_used_this_month", "overage_count") == (lim, 0)
    # Paiement à l'usage coupé : refusé avant tout appel, rien de débité.
    regler(False)
    r = demande()
    assert r.status_code == 402, r.text
    assert _lire(uid, "analyses_used_this_month", "overage_count") == (lim, 0)


# ═══ R2. La bulle d'en-tête de « À venir » ═════════════════════════════════════════════════════════════════════════

def test_r2_la_bulle_d_a_venir_dit_les_deux_sources():
    """Sur ba07980 : « … la date de notification et la durée publiée » seulement. Vérifié dans le code : la DECP part de
    la date de notification et de la durée publiée ; le repli, de la parution de l'avis d'attribution du BOAMP, avec la
    durée que l'IA lit dans son intitulé, sinon une durée par défaut."""
    m = re.search(r'<b style="font-size:13\.5px">Contrats qui arrivent à échéance</b><button type="button" '
                  r'class="tip">.*?<span class="tip-b" role="tooltip">([^<]*)</span>', RADAR)
    assert m and m.group(1) == BULLE_A_VENIR
    assert ("À défaut, d'après les avis d'attribution du BOAMP : la date de publication de l'avis et une durée lue dans "
            "son intitulé, ou estimée.") in BULLE_A_VENIR
    src = (ROOT / "app" / "services" / "renewal.py").read_text(encoding="utf-8")
    for x in ('"date_attribution": (row.get("dateparution") or "")[:10]', 'duree = info.get("duree_mois")',
              "duree = _DEFAULT_DUREE.get(ctype, 36)", 'aw = _parse(r["date_attribution"])',
              "fin = aw + timedelta(days=int(duree * 30.4))"):
        assert x in src, x
    d = _dico()
    assert "BOAMP" in d["nl"][BULLE_A_VENIR] and "BOAMP" in d["es"][BULLE_A_VENIR]


# ═══ R3. La durée par défaut, sans type de contrat ═════════════════════════════════════════════════════════════════

def test_r3_duree_par_defaut_sans_type_de_contrat(monkeypatch):
    """Le vrai repli (renewal.detect_renewals, avis simulés, IA simulée) : l'IA ne rend rien, toutes les durées sont
    estimées sans type, 36 mois ; l'IA rend un type, la durée de ce type (48 mois pour un accord-cadre, 30 pour un
    marché). Sur ba07980, l'écran disait « (durée estimée selon le type de contrat) » dans tous ces cas."""
    from app.services import renewal
    aw = (date.today() - timedelta(days=800)).isoformat()
    avis = [{"idweb": f"24-{i}", "objet": o, "acheteur": "Ville", "dept": "29", "lieu": "", "date_attribution": aw,
             "url": f"https://www.boamp.fr/avis/detail/24-{i}"}
            for i, o in enumerate(("Entretien de voirie", "Accord-cadre de travaux de voirie", "Marché de voirie"))]
    monkeypatch.setattr(renewal, "_fetch_attributions", lambda *a, **k: [dict(x) for x in avis])

    def panne(*a, **k):
        raise RuntimeError("IA indisponible")
    monkeypatch.setattr(renewal, "complete_json", panne)
    sans_ia = renewal.detect_renewals("voirie", ["29"], {})["renewals"]
    assert len(sans_ia) == 3 and all(f["duree_estimee"] and f["type_contrat"] == "" and f["duree_mois"] == 36
                                     for f in sans_ia)
    monkeypatch.setattr(renewal, "complete_json", lambda *a, **k: {"avis": [
        {"index": 0, "garder": True, "duree_mois": None, "type": None},
        {"index": 1, "garder": True, "duree_mois": None, "type": "accord-cadre"},
        {"index": 2, "garder": True, "duree_mois": None, "type": "marché"}]})
    par_ref = {f["idweb"]: f for f in renewal.detect_renewals("voirie", ["29"], {})["renewals"]}
    assert [(par_ref[k]["type_contrat"], par_ref[k]["duree_mois"]) for k in ("24-0", "24-1", "24-2")] == [
        ("", 36), ("accord-cadre", 48), ("marché", 30)]
    script = (_fonction("dureeFinDeContrat") + "\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(r => "
              "dureeFinDeContrat(r, 'BOAMP'))));")
    assert _node(script, json.dumps(sans_ia)) == [DUREE_PAR_DEFAUT] * 3
    assert _node(script, json.dumps([par_ref[k] for k in ("24-0", "24-1", "24-2")])) == [
        DUREE_PAR_DEFAUT, "(durée estimée selon le type de contrat)", "(durée estimée selon le type de contrat)"]
    d = _dico()
    assert d["nl"][DUREE_PAR_DEFAUT] and d["es"][DUREE_PAR_DEFAUT]


# ═══ R4. La bulle de « Date limite non précisée » ══════════════════════════════════════════════════════════════════

def test_r4_la_bulle_non_precisee_reste_vraie_quand_le_serveur_est_prudent():
    """Le vrai code (boamp.lire_rectificatif, BoampSource._appliquer) sur deux formes jamais observées : un rectificatif
    sans bloc `infosRectif`, un autre délai que la réception des offres. Le serveur ne sait pas s'ils parlent de la date
    limite : par prudence, « non précisée ». Sur ba07980, la bulle affirmait « porte sur sa date limite »."""
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.sources.boamp import BoampSource, lire_rectificatif
    cas = [{"idweb": "26-1", "nature": "RECTIFICATIF", "dateparution": "2026-10-10",
            "donnees": json.dumps({"FNSimple": {"autre": "x"}})},
           {"idweb": "26-2", "nature": "RECTIFICATIF", "dateparution": "2026-10-10",
            "donnees": json.dumps({"MAPA": {"infosRectif": {"rubDelais": "DateLimiteQuestions",
                                                            "auLieuDeDate": "2026-10-20", "lireDate": "2026-10-25"}}})}]
    cartes = []
    for r in cas:
        assert lire_rectificatif(r)["concerne"] is True and lire_rectificatif(r)["date"] is None
        t = NormalizedTender(objet="Travaux", acheteur="Ville", date_limite="2026-11-05", departements=["29"],
                             provenance=Provenance(source="BOAMP", source_url="https://www.boamp.fr/avis/detail/26-0",
                                                   official_ref="26-0"))
        BoampSource()._appliquer(t, [r])
        assert t.date_limite is None and t.date_limite_rectifiee_non_lue is True
        cartes.append(t.model_dump(exclude={"raw"}))
    script = _fonction("rectifDeCarte") + "\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(rectifDeCarte)));"
    assert [x["etat"] for x in _node(script, json.dumps(cartes))] == ["non_lue", "non_lue"]
    # La bulle ne dit que ce qui est vrai dans tous les cas : il « peut changer » sa date limite.
    assert BULLE_NON_LUE in CARTE and "porte sur sa date limite" not in _plat(_sans_commentaires(HTML))
    assert BULLE_NON_LUE.startswith("Un rectificatif de cet avis peut changer sa date limite")


# ═══ R5 et R6. « Voir les marchés pour mon entreprise » ════════════════════════════════════════════════════════════

_SCRIPT_MINE = r"""
global.document = { getElementById() { return { focus() {} }; } };
const journal = [];
const o = {
__METHODES__
};
async function cas(c) {
  journal.length = 0;
  Object.assign(o, { company: c.company, criteria: JSON.parse(JSON.stringify(c.criteria)),
    src: { query: "", dept: c.dept || "", prefilled: !!c.prefilled, searched: false, manqueMetier: false, cpvSeuls: false },
    $refs: { srcDireMetier: { focus() {} } }, $nextTick(f) { f(); }, notify() {}, go() {},
    srcSearch() { journal.push("search:" + o.src.query + "|" + o.src.dept); },
    api: async (m, p) => { journal.push(m + " " + p); if (c.serveur === "panne") throw new Error("x"); return c.serveur; } });
  await o.srcSearchMine();
  return { journal: journal.slice(), manque: o.src.manqueMetier, cpv: o.src.cpvSeuls };
}
(async () => {
  const out = {};
  const cass = JSON.parse(process.argv[1]);
  for (const k in cass) out[k] = await cas(cass[k]);
  console.log(JSON.stringify(out));
})();
"""


def _mine(cas):
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    script = borne + _SCRIPT_MINE.replace("__METHODES__", "\n".join(_methode(m) for m in (
        "srcPrefillFromProfile", "srcMetier", "srcSearchMine")))
    return _node(script, json.dumps(cas))


def test_r5_des_codes_cpv_sans_specialite_l_ecran_dit_ce_qui_manque(client, auth):
    """Le produit tient le métier pour dit avec des codes CPV seuls (premiers pas : criteria_v2.ce_que_je_cherche_dit) ;
    ce bouton ne cherche qu'avec des mots (le BOAMP ne lit pas les codes CPV). Sur ba07980 : « Dites d'abord votre
    métier », comme s'il n'avait rien dit."""
    from app.routers.criteria_v2 import ce_que_je_cherche_dit
    from tests.test_redaction_socle0 import _db, _user_id
    r = client.put("/api/criteria/", headers=auth["headers"], json={"specialites": "", "codes_cpv": "45233140"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert ce_que_je_cherche_dit(db, _user_id(auth["email"]))["metier"] is True
    finally:
        db.close()
    boamp = (ROOT / "app" / "sourcing" / "sources" / "boamp.py").read_text(encoding="utf-8")
    assert 'supported_filters = {"query", "departements"}' in boamp and 'or ["travaux"]' in boamp
    cp = {"postal_code": "29200"}
    vus = _mine({
        "cpv_a_l_ecran": {"company": cp, "criteria": {"specialites": "", "codes_cpv": "45233140"}, "serveur": {}},
        "cpv_enregistres": {"company": cp, "criteria": {}, "serveur": {"specialites": " ", "codes_cpv": "45233140"}},
        "rien": {"company": cp, "criteria": {"specialites": "", "codes_cpv": ""}, "serveur": {}},
        "rien_serveur_en_panne": {"company": cp, "criteria": {}, "serveur": "panne"},
        "metier_et_cpv": {"company": cp, "criteria": {"specialites": "Voirie", "codes_cpv": "45233140"}},
    })
    assert vus["cpv_a_l_ecran"] == {"journal": ["GET /api/criteria/"], "manque": True, "cpv": True}
    assert vus["cpv_enregistres"] == {"journal": ["GET /api/criteria/"], "manque": True, "cpv": True}
    assert vus["rien"]["cpv"] is False and vus["rien"]["manque"] is True
    assert vus["rien_serveur_en_panne"]["cpv"] is False and vus["rien_serveur_en_panne"]["manque"] is True
    assert vus["metier_et_cpv"] == {"journal": ["search:Voirie|29"], "manque": False, "cpv": False}
    assert f'<span v-if="src.cpvSeuls">{MANQUE_METIER_CPV}</span>' in TROUVER
    assert f'<span v-else>{MANQUE_METIER}</span>' in TROUVER
    d = _dico()
    assert "CPV" in d["nl"][MANQUE_METIER_CPV] and "CPV" in d["es"][MANQUE_METIER_CPV]


def test_r6_le_sous_titre_dit_les_departements_de_la_recherche():
    """Le bouton cherche dans les départements du champ de la recherche (pré-rempli une fois par le code postal) : vidé,
    toute la France ; « 56 » tapé, le 56. Sur ba07980, le sous-titre promettait « le département de votre code postal »."""
    cp = {"postal_code": "29200"}
    vus = _mine({
        "pre_rempli": {"company": cp, "criteria": {"specialites": "Voirie"}},
        "vide": {"company": cp, "criteria": {"specialites": "Voirie"}, "prefilled": True, "dept": ""},
        "autre": {"company": cp, "criteria": {"specialites": "Voirie"}, "prefilled": True, "dept": "56"},
    })
    assert [vus[k]["journal"] for k in ("pre_rempli", "vide", "autre")] == [
        ["search:Voirie|29"], ["search:Voirie|"], ["search:Voirie|56"]]
    assert f'<div class="muted small" style="margin-top:6px">{SOUS_TITRE}</div>' in TROUVER
    assert "le département de votre code postal" not in HTML
    # « ci-dessus » : la recherche (et son champ « Départements ») précède l'état vide qui porte ce sous-titre.
    assert TROUVER.index('data-test="trouver-recherche"') < TROUVER.index(SOUS_TITRE)
    assert 'v-model="src.dept" placeholder="Départements (29, 56…)"' in TROUVER


# ═══ R7. Le contrat et le bilan ═══════════════════════════════════════════════════════════════════════════════════

def test_r7_contrat_et_bilan_disent_l_ecran_d_apres_la_revue():
    contrat = _plat((ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8"))
    bilan = _plat((ROOT / "docs" / "MISE_EN_LIGNE_22_10.md").read_text(encoding="utf-8"))
    # Phrases dépassées par l'écran ou fausses dans le code.
    for x in ("une analyse disponible est exigée avant, même là", "la carte affiche « (estimée) » au lieu de « (réelle) »",
              "13. Chaque repli payant est noté dans le journal : rien de visible.",
              "Point 12 ter : « (estimée) » au lieu de « (réelle) » dans ces cas.",
              "7. Plus de faux « métier correspondant » sur une carte BOAMP : sa note d'adéquation peut baisser. Une"):
        assert x not in contrat, x
    for x in ("qu'il faut une analyse disponible. C'est la règle du code",
              "un compte sans analyse disponible reçoit le même refus. Ce que",
              "est affichée « (estimée) », et non plus « (réelle) »",
              "sans donnée personnelle. Rien n'est visible à l'écran.",
              "L'ordre et la note d'adéquation d'une carte Mégalis peuvent donc bouger un peu.",
              "La note d'adéquation de certaines cartes BOAMP baisse.",
              "Trois chantiers, finis et vérifiés chacun de son côté, sont réunis"):
        assert x not in bilan, x
    # Ce que dit l'écran d'après la revue, et sa preuve.
    ecran = contrat[contrat.index("## Écran"):]
    for x in ("tests/test_moteur_lot1_ecran_revue.py", "paiement à l'usage", DUREE_PAR_DEFAUT, "peut changer sa date limite",
              "les départements de la recherche ci-dessus", "Vos codes CPV seuls ne suffisent pas à ce bouton"):
        assert x in ecran, x
    for x in ("tests/test_moteur_lot1_ecran_revue.py", "paiement à l'usage", DUREE_PAR_DEFAUT,
              "puis la partie écran du lot 1"):
        assert x in bilan, x
