"""Zone « recherche » (Trouver des marchés, À venir, Mes alertes, Ce que je cherche) : reproductions des écarts
relevés sur cfe04e1. Chaque test ÉCHOUE sur cfe04e1 et décrit le comportement attendu ; aucun réseau.

Lancement : ADJUGO_TEST_DB=p1.db TZ=UTC python -m pytest -q -p no:warnings tests/test_p1_recherche_bugs.py
"""
import json
from datetime import datetime, timedelta

import pytest

from app.sourcing.base import ResultatsSource, TenderCriteria, TenderSource
from app.sourcing.schemas import NormalizedTender, Provenance
from app.sourcing.search import TenderSearchService
from tests.test_reorganisation_v2b_espace_partenaire import _methode


def _node(script):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _objet_vue(*noms):
    """Les méthodes nommées de l'application, dans un objet JavaScript."""
    return "({\n" + "\n".join(_methode(n) for n in noms) + "\n})"


def _methode_fonction(nom):
    """Une fonction de premier niveau de app.js (« function nom(…) { … } »), telle quelle."""
    import re as _re
    js = open("app/static/app.js", encoding="utf-8").read()
    m = _re.search(r"\nfunction " + _re.escape(nom) + r"\(", js)
    assert m, nom
    fin = js.index("\n}\n", m.start())
    return js[m.start() + 1:fin + 2]

_FUT = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


def _t(src, ref, objet="Travaux de voirie"):
    t = NormalizedTender(objet=f"{objet} {ref}", acheteur=f"Ville {ref}", date_limite=_FUT, departements=["29"],
                         provenance=Provenance(source=src, source_url=f"https://x.fr/{ref}", official_ref=ref))
    t.dedup_key = ref
    return t


class _Source(TenderSource):
    """Source d'essai : `n` fiches en première page, rien au-delà (comme une source qui n'a que n avis)."""

    def __init__(self, name, n):
        self.name, self.n = name, n

    def search(self, criteria):
        if criteria.offset:
            return []
        return ResultatsSource([_t(self.name, f"{self.name}-{i}") for i in range(self.n)], lignes_lues=self.n)


# ── B1 : les marchés d'une alerte sont marqués « déjà vus » même quand le courriel n'est pas parti ──────────────────

def test_b1_alerte_courriel_non_parti_rien_n_est_marque_deja_vu(client, auth, monkeypatch):
    """send_email rend False (Brevo ou SMTP en panne) : les marchés ne doivent pas être marqués « déjà vus », sinon ils
    ne sont jamais envoyés (la règle des « pièces à renouveler » : « on ne marque que si l'email est parti »)."""
    from app.core.database import SessionLocal
    from app.models import SavedSearch, User
    from app.services import alerts
    r = client.post("/api/saved-searches/", headers=auth["headers"],
                    json={"name": "B1", "query": "voirie", "departements": ["29"], "countries": ["FR"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    class _Deux(TenderSource):
        name = "BOAMP"

        def search(self, criteria):
            return [_t("BOAMP", "26-1"), _t("BOAMP", "26-2")]

    monkeypatch.setattr("app.routers.sourcing._tender_sources", lambda countries: [_Deux()])
    envois = []
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: envois.append(a) or False)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        u.email_verified = True
        db.commit()
        alerts.run_tender_alerts(db)
        s = db.get(SavedSearch, sid)
        assert len(envois) == 1                       # un courriel tenté, non parti
        assert not s.last_seen_refs, s.last_seen_refs  # rien de marqué : ils partiront au prochain passage
        # le passage suivant, courriel parti : les deux marchés partent, puis sont marqués
        monkeypatch.setattr(alerts, "send_email", lambda *a, **k: envois.append(a) or True)
        alerts.run_tender_alerts(db)
        db.refresh(s)
        assert "26-1" in envois[-1][2] and "26-2" in envois[-1][2]
        assert sorted(s.last_seen_refs) == ["BOAMP|26-1", "BOAMP|26-2"]
    finally:
        db.close()


# ── B3 : « Charger plus » proposé alors qu'aucune source n'a rempli sa page ──────────────────────────────────────────

def test_b3_charger_plus_seulement_si_une_source_a_rempli_sa_page():
    """8 lignes BOAMP + 7 lignes TED = 15 : has_more vaut True sur cfe04e1 (somme des lignes), alors que la page
    suivante est vide. Mégalis (3 pages lues d'un coup, rien au-delà) ne doit pas non plus promettre une suite."""
    out = TenderSearchService([_Source("BOAMP", 8), _Source("TED", 7)]).search(TenderCriteria(query="x", limit=15))
    assert out["count"] == 15
    assert out["has_more"] is False
    # une source qui a rempli sa page : la suite est proposée (inchangé)
    out = TenderSearchService([_Source("BOAMP", 15), _Source("TED", 2)]).search(TenderCriteria(query="x", limit=15))
    assert out["has_more"] is True

    class _ToutEnPremierePage(_Source):
        pagine = False              # comme Mégalis (atexo.py) : 3 pages lues d'un coup, rien au-delà

    out = TenderSearchService([_Source("BOAMP", 3), _ToutEnPremierePage("Mégalis", 30)]).search(
        TenderCriteria(query="x", departements=["29"], limit=15))
    assert out["count"] == 33 and out["has_more"] is False
    from app.sourcing.sources.atexo import AtexoSource
    assert AtexoSource.pagine is False


def test_b3_bis_une_page_ted_pleine_dont_des_avis_sont_hors_zone_reste_pleine(monkeypatch):
    """Règle source par source : TED rend le nombre d'avis reçus (comme le BOAMP), pas seulement ceux de la zone
    demandée ; sinon une page pleine dont un avis est hors zone couperait la suite à tort."""
    from app.sourcing import http as shttp
    from app.sourcing.base import lignes_lues
    from app.sourcing.sources import ted

    def _avis(i, pays):
        return {"publication-number": f"{i}-2026", "notice-title": {"fra": f"Travaux {i}"},
                "place-of-performance": [pays], "buyer-name": {"fra": ["Ville"]},
                "deadline-receipt-tender-date-lot": [_FUT + "+02:00"]}

    class _R:
        def raise_for_status(self): pass
        def json(self): return {"notices": [_avis(i, "DEU" if i else "FRA") for i in range(15)]}

    monkeypatch.setattr(shttp, "post_with_retry", lambda url, json=None, **k: _R())
    res = ted.TedSource().search(TenderCriteria(query="travaux", countries=["DE"], limit=15))
    assert len(res) == 14 and lignes_lues(res) == 15


# ── B4 : un rectificatif réel écrit « des offre » (singulier) n'est pas lu : l'avis garde son ancienne date ──────────

def test_b4_rectificatif_reel_26_99040_offre_au_singulier_est_lu():
    """26-99040 (jeu « travaux » du 21/10/2026, rectificatif de 26-89213) : « La date limite de remise des offre est
    prolongée au 30 octobre 2026. » Sur cfe04e1 : « ne concerne pas la date limite », donc l'ancienne date reste,
    contraire à la règle « jamais l'ancienne date »."""
    from app.sourcing.sources import boamp
    d = json.load(open("tests/fixtures/moteur_lot1_relecture/boamp_travaux_2026-10-21.json", encoding="utf-8"))
    r = next(x for q in d["requetes"] for x in q["results"] if x.get("idweb") == "26-99040")
    assert boamp.lire_rectificatif(r) == {"concerne": True, "date": "2026-10-30", "forme": "texte"}
    # les autres écritures au singulier après « des » suivent
    assert boamp._lire_texte("Date limite de réception des pli : 30/10/2026") == (True, "2026-10-30")
    # au singulier aussi, la date limite citée comme repère d'un autre délai ne la change pas
    assert boamp._lire_texte("Questions jusqu'à 10 jours avant la date limite de remise des offre.") == (False, None)


# ── B5 : fins de contrat DECP, plusieurs contrats d'un même acheteur reçoivent la même clé « idweb » ─────────────────

def test_b5_fins_de_contrat_decp_cles_distinctes(monkeypatch):
    """Vraies lignes DECP du 974 : deux contrats du même acheteur → le même idweb (le SIRET), clé des cartes de
    l'écran (:key) et du bouton « Préparer à plusieurs » (spinner et verrou partagés)."""
    from app.services import decp
    rows = json.load(open("tests/fixtures/moteur_lot1_services/decp_dep_974.json", encoding="utf-8"))["results"]
    monkeypatch.setattr(decp, "_fetch", lambda *a, **k: rows)
    monkeypatch.setattr(decp, "_acheteur_name", lambda s: "")
    out = decp.detect_renewals_decp("travaux", ["974"], {})
    ids = [r["idweb"] for r in out["renewals"]]
    assert len(ids) == 2 and len(set(ids)) == 2, ids


# ── B6 : « Ce que je cherche » a plusieurs codes CPV : la DECP n'en lit que le premier ───────────────────────────────

def test_b6_decp_lit_tous_les_codes_cpv_de_ce_que_je_cherche():
    from unittest.mock import patch
    from app.services import decp
    vu = {}

    class _R:
        def json(self): return {"results": []}

    with patch.object(decp, "get_with_retry", lambda url, params=None, **k: vu.update(params or {}) or _R()):
        decp._fetch("travaux", ["29"], cpv="45211000, 45300000", per=10)
    assert 'codecpv like "4521"' in vu["where"] and 'codecpv like "4530"' in vu["where"], vu["where"]


# ── B7 : l'alerte d'un collègue ne lit pas le profil entreprise de l'organisation ────────────────────────────────────

def test_b7_alerte_d_un_collegue_lit_le_profil_entreprise_de_l_organisation(client, auth, monkeypatch):
    """L'écran de recherche lit le profil du propriétaire (data_owner_id) ; l'alerte du collègue, elle, cherche
    Company.user_id == collègue → {} : classement différent de l'écran (zone du code postal absente)."""
    r = client.put("/api/company/", headers=auth["headers"], json={"name": "Test SARL", "postal_code": "29000", "city": "Quimper"})
    assert r.status_code == 200, r.text
    r = client.post("/api/org/invite", headers=auth["headers"], json={"email": "collegue_b7@test.fr", "full_name": "Col"})
    assert r.status_code == 201, r.text
    lr = client.post("/api/auth/login", json={"email": "collegue_b7@test.fr", "password": r.json()["temp_password"]})
    assert lr.status_code == 200, lr.text
    h = {"Authorization": f"Bearer {lr.json()['access_token']}"}
    r = client.post("/api/saved-searches/", headers=h, json={"name": "Col", "query": "voirie", "departements": [], "countries": ["FR"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    class _Une(TenderSource):
        name = "BOAMP"

        def search(self, criteria):
            return [_t("BOAMP", "26-1")]

    monkeypatch.setattr("app.routers.sourcing._tender_sources", lambda countries: [_Une()])
    from app.sourcing import search as search_mod
    vu = {}
    orig = search_mod.TenderSearchService.search

    def _spy(self, crit, company=None, gonogo=None):
        vu["company"] = company
        return orig(self, crit, company, gonogo)
    monkeypatch.setattr(search_mod.TenderSearchService, "search", _spy)
    assert client.post(f"/api/saved-searches/{sid}/run", headers=h).status_code == 200
    assert (vu.get("company") or {}).get("postal_code") == "29000", vu.get("company")


# ── B8 : « Seuil bon potentiel » affiché 75 tant que rien n'est enregistré, verdict calculé avec 65 ─────────────────

def test_b8_seuil_affiche_et_seuil_du_verdict_sont_les_memes(client, auth):
    """Compte neuf : « Ce que je cherche » montre 75 dans le champ (GET /api/criteria/, la valeur que garde le premier
    enregistrement), mais le verdict prenait 65 tant que rien n'était enregistré (_verdict, score_dce, groupement) ;
    un marché noté 70 changeait de verdict au premier enregistrement sans que le seuil ait été touché. Le champ vidé
    (« 75 (défaut) ») revient au défaut au lieu de garder l'ancienne valeur."""
    import re as _re
    from app.core.database import SessionLocal
    from app.models import User
    from app.routers.sourcing import _verdict
    from app.services.dce_scoring import score_dce
    from app.services.groupement_scoring import _thresholds
    from app.services.profile import criteria_dict
    ecran = client.get("/api/criteria/", headers=auth["headers"]).json()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        g = criteria_dict(u.id, db)
    finally:
        db.close()
    assert g == {}                                      # rien d'enregistré
    seuil, bas = ecran["go_threshold"], ecran["nogo_threshold"]
    assert _verdict(seuil, g) == "go" and _verdict(seuil - 1, g) == "a_etudier", (seuil, g)
    assert _verdict(bas, g) == "a_etudier" and _verdict(bas - 1, g) == "no_go"
    d = score_dce({}, {}, g)
    assert (d["threshold"], d["nogo_threshold"]) == (seuil, bas)
    assert _thresholds({}) == {"go": seuil, "nogo": bas}
    # le texte du champ vide dit les mêmes défauts
    html = open("app/static/app.html", encoding="utf-8").read()
    assert _re.search(r'id="crit-go"[^>]*placeholder="%d \(défaut\)"' % seuil, html)
    assert _re.search(r'id="crit-nogo"[^>]*placeholder="%d \(défaut\)"' % bas, html)
    # même marché, même verdict avant et après un premier enregistrement qui ne touche pas au seuil
    avant = _verdict(70, g)
    r = client.put("/api/criteria/", headers=auth["headers"], json={**ecran, "specialites": "voirie"})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert _verdict(70, criteria_dict(u.id, db)) == avant
    finally:
        db.close()
    # seuils réglés puis vidés (l'écran envoie null) : retour au défaut affiché
    assert client.put("/api/criteria/", headers=auth["headers"],
                      json={**ecran, "go_threshold": 85, "nogo_threshold": 30}).json()["go_threshold"] == 85
    r = client.put("/api/criteria/", headers=auth["headers"], json={**ecran, "go_threshold": None, "nogo_threshold": None})
    assert (r.json()["go_threshold"], r.json()["nogo_threshold"]) == (seuil, bas)


# ── B9 : nom et mots d'une alerte trop longs : erreur serveur sur PostgreSQL ─────────────────────────────────────────

def test_b9_alerte_au_nom_trop_long_refusee_proprement(client, auth):
    """L'écran construit le nom « mots · zone (dépts) » sans borne ; la colonne fait 255 caractères (500 pour les mots).
    Sur PostgreSQL (production), cfe04e1 répond 500 (StringDataRightTruncation) ; SQLite accepte. Attendu : 422 ou un
    nom tronqué, jamais une erreur serveur."""
    mots = ("rénovation " * 40).strip()
    r = client.post("/api/saved-searches/", headers=auth["headers"],
                    json={"name": mots + " · France (29)", "query": mots, "departements": ["29"], "countries": ["FR"]})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == (mots + " · France (29)")[:255] and r.json()["query"] == mots
    sid = r.json()["id"]
    # la même règle à la modification
    r = client.put(f"/api/saved-searches/{sid}", headers=auth["headers"], json={"name": "x" * 300})
    assert r.status_code == 200 and len(r.json()["name"]) == 255, r.text
    # des mots-clés plus longs que la colonne : refus lisible, jamais une erreur serveur
    r = client.post("/api/saved-searches/", headers=auth["headers"],
                    json={"name": "Long", "query": "béton " * 100, "departements": [], "countries": ["FR"]})
    assert r.status_code == 422, r.text
    assert "500 caractères au plus" in r.json()["detail"][0]["msg"]
    for champ, valeur in (("frequency", "q" * 21), ("type_marche", "t" * 41)):
        r = client.post("/api/saved-searches/", headers=auth["headers"], json={"name": "N", champ: valeur})
        assert r.status_code == 422, (champ, r.text)


# ── B10 : « Mes alertes » dit « tous métiers » pour une alerte sans mot, qui ne cherche que « travaux » ─────────────

def test_b10_une_alerte_sans_mot_dit_ce_qu_elle_cherche_jamais_tous_metiers(monkeypatch):
    """app.html (Mes alertes) affichait « tous métiers » quand aucun mot n'est saisi ; le BOAMP et TED reçoivent alors
    « travaux » (boamp.py, ted.py) : l'alerte ne couvre pas les services ni les fournitures. Le repli « travaux »
    des sources est une décision laissée à Eliot (docs/MOTEUR_LOT1.md, « Vu en passant, non corrigé ») : l'écran dit
    donc le mot réellement cherché. Si le repli change, ce test le signale (le texte devra changer avec lui)."""
    from app.sourcing.sources import boamp, ted
    vu = {}

    class _R:
        def json(self): return {"results": [], "notices": []}
        def raise_for_status(self): pass

    from app.sourcing import http as shttp
    monkeypatch.setattr(shttp, "get_with_retry", lambda url, params=None, **k: vu.update({"boamp": params["where"]}) or _R())
    monkeypatch.setattr(shttp, "post_with_retry", lambda url, json=None, **k: vu.update({"ted": json["query"]}) or _R())
    boamp.BoampSource().search(TenderCriteria(query="", departements=[]))
    ted.TedSource().search(TenderCriteria(query="", countries=["FR"]))
    assert 'like "trav*"' in vu["boamp"], vu["boamp"]          # « travaux », en préfixe
    assert '(FT~"travaux")' in vu["ted"], vu["ted"]
    html = open("app/static/app.html", encoding="utf-8").read()
    zone = html[html.index('data-test="trouver-alertes"'):]
    zone = zone[:zone.index("<!--")] if "<!--" in zone else zone
    assert "tous métiers" not in zone
    assert "<b>{{ alerteMots(src.query) }}</b>" in zone and "<span>{{ alerteMots(a.query) }}</span>" in zone
    vu = _node("const app = " + _objet_vue("alerteMots") + ";"
               "console.log(JSON.stringify([app.alerteMots(''), app.alerteMots('  '), app.alerteMots(null),"
               " app.alerteMots('voirie')]));")
    sans = "aucun mot saisi (« travaux » est cherché)"
    assert vu == [sans, sans, sans, "voirie"], vu
    # traduit comme les autres libellés (nœud de texte entier : <b> et <span>)
    i18n = open("app/static/i18n.js", encoding="utf-8").read()
    assert i18n.count(json.dumps(sans, ensure_ascii=False)) == 2


# ── B11 : une alerte « Allemagne » garde le département caché de la recherche française ─────────────────────────────

_SCRIPT_B11 = r"""
const journal = [];
const o = {
__METHODES__
};
Object.assign(o, {
  src: { country: "__PAYS__", dept: "974", query: "béton", cpv: "", type_marche: "", _savingAlert: false, alerts: [] },
  countries2: [{ code: "DE", nom: "Allemagne" }, { code: "FR", nom: "France" }],
  loadAlerts() {}, notify(m) { journal.push(["notify", m]); },
  api: async (m, p, body) => { journal.push([m, p, body]); return []; },
});
(async () => {
  await o.srcSaveAlert();
  journal.push(typeof o.alerteZone !== "function" ? ["zone", "absente"] :
               ["zone", o.alerteZone({ countries: ["DE"], departements: ["974"] }),
                o.alerteZone({ countries: ["FR"], departements: ["974"] }), o.alerteZone({ countries: [], departements: [] })]);
  console.log(JSON.stringify(journal));
})();
"""


def _b11(pays):
    import json as _json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    import re as _re
    js = open("app/static/app.js", encoding="utf-8").read()
    metho = [m for m in ("srcSaveAlert", "srcDeps", "srcDepsVisibles", "countryName", "alerteZone")
             if _re.search(r"\n    (?:async )?" + m + r"\(", js)]
    script = _SCRIPT_B11.replace("__METHODES__", "\n".join(_methode(m) for m in metho)).replace("__PAYS__", pays)
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return _json.loads(r.stdout.strip().splitlines()[-1])


def test_b11_une_alerte_sur_un_autre_pays_n_emporte_pas_le_departement_cache():
    """Publiés : le champ « Départements » disparaît dès qu'un autre pays que la France est choisi (app.html,
    v-if="!src.country || src.country==='FR'"), mais srcSaveAlert envoyait quand même srcDeps() : l'alerte s'appelait
    « béton · Allemagne (974) » et la liste disait « dépts 974 » pour une recherche en Allemagne (TED, qui ne filtre
    pas par département). Attendu : aucun département (ni dans le nom, ni dans l'alerte) quand le champ est caché."""
    journal = _b11("DE")
    post = next(j for j in journal if j[0] == "POST")
    assert post[2]["countries"] == ["DE"]
    assert post[2]["departements"] == [], post[2]
    assert post[2]["name"] == "béton · Allemagne", post[2]["name"]
    # la liste : le pays pour une alerte hors de France (même une alerte enregistrée avant, avec le département caché)
    assert journal[-1] == ["zone", "Allemagne", "dépts 974", "tous départements"], journal[-1]
    # France : inchangé
    post = next(j for j in _b11("FR") if j[0] == "POST")
    assert post[2]["departements"] == ["974"] and post[2]["name"] == "béton · France (974)", post[2]
    html = open("app/static/app.html", encoding="utf-8").read()
    assert ('v-if="!src.country || src.country===\'FR\'"' in html
            and "departements: (!src.country || src.country==='FR') ? srcDeps() : [] })" in html
            and "{{ alerteZone(a) }}" in html)


# ── B12 : un département non reconnu (« 29000 ») est ignoré en silence : la recherche part sur toute la France ────

def test_b12_un_departement_non_reconnu_n_elargit_pas_la_recherche_a_toute_la_france(client, auth, monkeypatch):
    """TenderCriteria écarte sans rien dire tout département hors « 2 ou 3 chiffres / 2A / 2B » : « 29000 » (un code
    postal tapé dans le champ « Départements (29, 56…) ») donne departements=[] et le BOAMP est interrogé sans aucun
    département (Arras pour qui a tapé 29000). Attendu : refus (422) ou le département lu (« 29 »), jamais toute la
    France sans le dire."""
    vu = {}

    class _Espion(TenderSource):
        name = "BOAMP"

        def search(self, criteria):
            vu["departements"] = list(criteria.departements)
            return []

    monkeypatch.setattr("app.routers.sourcing._tender_sources", lambda countries: [_Espion()])
    phrase = "« 29000 » n'est pas un numéro de département : indiquez par exemple 29, 56, 2A ou 974."
    r = client.post("/api/sourcing/search", headers=auth["headers"],
                    json={"query": "voirie", "departements": ["29", "29000"], "countries": ["FR"], "limit": 15})
    assert r.status_code == 422, (r.status_code, vu)
    assert vu == {}                                         # aucune source interrogée
    # la phrase telle que l'écran l'affiche (validationMsg retire « Value error, »)
    assert r.json()["detail"][0]["msg"].replace("Value error, ", "") == phrase
    for bon in (["29", "56"], ["6"], ["2a", "974"], [" 29 "], []):
        r = client.post("/api/sourcing/search", headers=auth["headers"],
                        json={"query": "voirie", "departements": bon, "countries": ["FR"], "limit": 15})
        assert r.status_code == 200, (bon, r.text)
    # l'alerte créée depuis la recherche : même refus, rien d'enregistré
    avant = client.get("/api/saved-searches/", headers=auth["headers"]).json()
    r = client.post("/api/saved-searches/", headers=auth["headers"],
                    json={"name": "Voirie · France (29000)", "query": "voirie", "departements": ["29000"],
                          "countries": ["FR"]})
    assert r.status_code == 422 and r.json()["detail"] == phrase, r.text
    assert client.get("/api/saved-searches/", headers=auth["headers"]).json() == avant
    # un autre pays n'a pas de département : le champ caché par l'écran n'empêche pas la recherche
    r = client.post("/api/sourcing/search", headers=auth["headers"],
                    json={"query": "voirie", "departements": ["29000"], "countries": ["DE"], "limit": 15})
    assert r.status_code == 200, r.text


# ── B13 : « Contrats qui arrivent à échéance » montre un contrat dont la fin estimée est déjà passée ───────────────

def test_b13_a_venir_dit_qu_une_fin_de_contrat_est_deja_passee(monkeypatch):
    """Vraies lignes DECP du 974 (jeu du 21/10/2026) : « gros entretien … BOIS D'OLIVE », notifié le 31/03/2026 pour
    6 mois → fin estimée le 29/09/2026. Le 22/10/2026, la fenêtre du serveur (renouvellement entre J-180 et J+550, soit
    une fin entre J-60 et J+670) la garde, et la carte disait « Fin du contrat estimée le 29/09/2026 » sous « Contrats
    qui arrivent à échéance », comme une fin à venir. La fenêtre est gardée (la republication d'un contrat fini depuis
    peu peut être en cours ; la changer déplacerait le repli payant de « À venir ») : la carte le dit."""
    from datetime import date as _date
    from app.services import decp

    class _Jour(_date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 22)

    rows = json.load(open("tests/fixtures/moteur_lot1_services/decp_dep_974.json", encoding="utf-8"))["results"]
    monkeypatch.setattr(decp, "_fetch", lambda *a, **k: rows)
    monkeypatch.setattr(decp, "_acheteur_name", lambda s: "")
    monkeypatch.setattr(decp, "date", _Jour)
    out = decp.detect_renewals_decp("travaux", ["974"], {})
    fins = [r["fin_estimee"] for r in out["renewals"]]
    assert fins == ["2026-10-25", "2026-09-29"], fins
    html = open("app/static/app.html", encoding="utf-8").read()
    radar = html[html.index('data-test="trouver-radar"'):html.index('data-test="trouver-alertes"')]
    assert ('<span v-if="srcRenPassee(r)" class="pill a_etudier avenir-passee" style="font-size:10px">'
            'fin estimée déjà passée</span>') in radar, "la carte ne dit pas que la fin estimée est passée"
    vu = _node(_methode_fonction("finDeContratPassee") + ";"
               "console.log(JSON.stringify([" + ",".join(
                   f"finDeContratPassee({json.dumps(r)}, '2026-10-22')" for r in out["renewals"]) +
               ", finDeContratPassee({fin_estimee: '2026-10-22'}, '2026-10-22'), finDeContratPassee({}, '2026-10-22')]));")
    assert vu == [False, True, False, False], vu
    js = open("app/static/app.js", encoding="utf-8").read()
    assert "srcRenPassee(r) { return finDeContratPassee(r, this.fxAujourdhui()); }," in js
