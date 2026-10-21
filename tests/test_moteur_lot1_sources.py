"""Moteur de recherche, lot 1 « Dire juste », chantier Sources (docs/MOTEUR_LOT1.md, § Sources).

  1. Dates Mégalis : une table explicite des mois français, jamais une coupe à quelques lettres.
  2. Rectificatifs et annulations du BOAMP rattachés à leur avis (`annonce_lie`), format européen compris.
  3. Le vocabulaire interne du BOAMP (`descripteur_code`) n'est plus lu comme un code métier européen (CPV).
  4. Outre-mer : départements comparés sur leur code complet ; la Corse « 2A » / « 2B » intacte.

Jeux d'essai RÉELS, lus en GET le 21/10/2026 et figés dans tests/fixtures (aucun réseau pendant les tests) :
  - boamp_suites_2026-10-21.json : avis, rectificatifs et annulations de l'API BOAMP (corps réduit au bloc
    rectificatif/annulation, contacts retirés) ;
  - megalis_resultats_2026-10-21.html : les 10 résultats de la recherche « voirie » sur Mégalis Bretagne.
Les cas CONSTRUITS (formes jamais observées, liens réécrits) le disent. Chaque test échoue sur 0afc1ed.
"""
import json
import logging
import pathlib
import re
from datetime import date

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
JEU = json.loads((FIX / "boamp_suites_2026-10-21.json").read_text(encoding="utf-8"))
AVIS = {r["idweb"]: r for r in JEU["avis"]}
SUITES = {r["idweb"]: r for r in JEU["suites"]}
LE_21_10 = date(2026, 10, 21)          # jour de la lecture : « aujourd'hui » des tests


def _figer(monkeypatch, jour=LE_21_10):
    from app.sourcing import search as search_mod
    from app.sourcing.sources import boamp
    monkeypatch.setattr(boamp, "_aujourdhui", lambda: jour, raising=False)
    monkeypatch.setattr(search_mod, "_aujourdhui", lambda: jour, raising=False)
    search_mod._CB.clear()


class _Rep:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"results": self._rows}


def _api(monkeypatch, avis, suites=(), initiaux=(), panne_suites=False):
    """API BOAMP simulée sur le jeu réel. Requête principale (`datelimitereponse >=`) : `avis`. Requête des
    suites : celles dont `annonce_lie` vise un avis demandé, plus, si la partie « rectificatifs récents » est
    demandée, tous les rectificatifs du jeu (le code doit écarter ceux qui ne visent rien d'affichable).
    Relecture `idweb in (…)` : les `initiaux` demandés et les annulations qui les visent."""
    from app.sourcing import http
    appels = []

    def fake(url, params=None, timeout=12, tries=3, headers=None):
        p = dict(params or {})
        appels.append(p)
        w = p.get("where", "")
        if "datelimitereponse >=" in w:
            return _Rep([dict(r) for r in avis])
        if w.startswith("idweb in"):
            ids = set(re.findall(r'"(\d{2}-\d+)"', w.split(" OR ")[0]))
            rows = [dict(r) for r in initiaux if r["idweb"] in ids]
            rows += [dict(s) for s in suites if s.get("nature") == "ANNULATION" and set(s.get("annonce_lie") or []) & ids]
            return _Rep(rows)
        if panne_suites:
            raise httpx.ConnectError("coupure simulée")
        m = re.search(r"annonce_lie in \(([^)]*)\)", w)
        ids = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
        rows = [dict(s) for s in suites if set(s.get("annonce_lie") or []) & ids]
        if 'nature="RECTIFICATIF" AND dateparution' in w:
            rows += [dict(s) for s in suites if s.get("nature") == "RECTIFICATIF" and not set(s.get("annonce_lie") or []) & ids]
        return _Rep(rows)

    monkeypatch.setattr(http, "get_with_retry", fake)
    return appels


def _cherche(crit=None):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources.boamp import BoampSource
    return TenderSearchService([BoampSource()]).search(crit or TenderCriteria(query="travaux", limit=15), {}, {})


def _par_ref(res):
    return {t.provenance.official_ref: t for t in res["tenders"]}


# ═══ 1. Dates Mégalis : la table explicite des mois ═════════════════════════════════════════════════

def test_megalis_page_reelle_toutes_les_dates_limites_lues(monkeypatch):
    """Page réelle du 21/10/2026 : « Oct. », « Nov. », « Déc. ». Avant : les 10 dates limites vides."""
    from app.sourcing.sources import atexo
    html = (FIX / "megalis_resultats_2026-10-21.html").read_text(encoding="utf-8")
    tenders, liens = atexo._parse_page(html, "Mégalis Bretagne", "https://marches.megalis.bretagne.bzh")
    par_cid = {t.provenance.official_ref: t.date_limite for t in tenders}
    assert liens == 10 and len(par_cid) == 10
    assert all(par_cid.values()), par_cid
    assert par_cid["242387"] == "2026-12-07"            # « 7 Déc. 2026 12:00 »
    assert par_cid["242491"] == "2026-11-23"            # « 23 Nov. 2026 12:00 »
    assert par_cid["242258"] == "2026-11-17"
    # La date de mise en ligne du bloc (« 14 Oct. 2026 ») n'est jamais prise pour la date limite.
    assert "2026-10-14" not in par_cid.values()


def test_megalis_recherche_complete_sur_la_page_reelle(monkeypatch):
    """La source Mégalis entière (requête honnête simulée, page réelle) : chaque consultation a sa date, et un
    même avis publié aussi au BOAMP fusionne enfin (même objet, même acheteur, même date limite)."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources import atexo
    from app.sourcing.sources.boamp import BoampSource, _dedup_key
    _figer(monkeypatch)
    for d in (atexo._REFUS, atexo._CACHE, atexo._RYTHME):
        d.clear()
    monkeypatch.setattr(atexo, "_INTERVALLE_MIN", 0.0)
    html = (FIX / "megalis_resultats_2026-10-21.html").read_text(encoding="utf-8")

    class _R:
        status_code, text, url = 200, html, "https://marches.megalis.bretagne.bzh/"

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **k):
            return _R()

        def post(self, url, **k):
            raise RuntimeError("pas de page 2 dans le jeu d'essai")

    monkeypatch.setattr(httpx, "Client", _Client)
    # Avis BOAMP CONSTRUIT pour l'essai de fusion : mêmes objet, acheteur et date que la consultation 242387.
    boamp = NormalizedTender(objet="TRAVAUX DE RENFORCEMENT 2027-2028 DE LA VOIRIE COMMUNALE",
                             acheteur="COMMUNE DE SAINT SAUVEUR", departements=["29"], date_limite="2026-12-07",
                             provenance=Provenance(source="BOAMP", official_ref="26-1",
                                                   source_url="https://www.boamp.fr/avis/detail/26-1"))
    boamp.dedup_key = _dedup_key(boamp)
    monkeypatch.setattr(BoampSource, "search", lambda self, crit: [boamp.model_copy(deep=True)])
    res = TenderSearchService([BoampSource(), atexo.MEGALIS]).search(
        TenderCriteria(query="voirie", departements=["29"]), {}, {})
    assert res["errors"] == []
    megalis = [t for t in res["tenders"] if t.provenance.source == "Mégalis Bretagne"]
    assert megalis and all(t.date_limite for t in megalis)
    fusion = [t for t in res["tenders"] if "SAINT SAUVEUR" in (t.acheteur or "")]
    assert len(fusion) == 1 and len(fusion[0].also_seen_in) == 1


def test_mois_table_explicite_jamais_une_coupe():
    """Chaque forme de la table (observée ou construite) donne son mois ; une forme absente ne donne rien."""
    from app.sourcing.sources.atexo import _parse_date
    attendus = {
        # observées sur Mégalis le 21/10/2026
        "Oct.": 10, "Nov.": 11, "Déc.": 12,
        # construites (non vérifiées sur une page réelle ; « Fév. » vue sur PLACE le 12/10 selon l'étude)
        "Janv.": 1, "janvier": 1, "Fév.": 2, "Févr.": 2, "fev": 2, "février": 2, "Mars": 3, "Avr.": 4,
        "Avril": 4, "Mai": 5, "Juin": 6, "Juil.": 7, "Juill.": 7, "juillet": 7, "Août": 8, "AOÛT": 8,
        "Aout": 8, "Sept.": 9, "septembre": 9, "OCT.": 10, "octobre": 10, "nov": 11, "DÉC.": 12, "Dec.": 12,
        "décembre": 12,
    }
    for forme, m in attendus.items():
        assert _parse_date(f"S'inscrire 7 {forme} 2026 12:00") == f"2026-{m:02d}-07", forme
    # Jamais une coupe : un mot qui COMMENCE comme un mois n'en est pas un.
    for faux in ("Marseille", "Juinet", "Octet", "Septante", "Novice", "Decathlon", "Janvxyz", "Avrillé"):
        assert _parse_date(f"12 {faux} 2026") is None, faux
    # Date impossible, jamais « corrigée ».
    assert _parse_date("31 Nov. 2026 12:00") is None


def test_megalis_case_cloture_prioritaire_jamais_la_date_de_mise_en_ligne():
    """Bloc construit sur le modèle réel : la case « clôture » est lue (« 7 Déc. 2026 ») ; si son mois est
    inconnu, aucune date, jamais la date de mise en ligne lue plus haut dans le bloc."""
    from app.sourcing.sources import atexo

    def bloc(mois):
        return ('<div class="item_consultation"><div class="cons_ref"><div class="date"><span>14</span>'
                '<span>Oct.</span><span>2026</span></div></div>'
                '<a href="/consultation/999001?orgAcronyme=x">Voirie</a> Objet : Voirie communale Organisme : '
                'COMMUNE DE TEST (29000 - TEST) (29) Finistère'
                '<div class="cloture-line"><div class="date"><div class="day"><span>7</span></div>'
                f'<div class="month-year"><div class="month"><span>{mois}</span></div>'
                '<div class="year"><span>2026</span></div></div></div></div></div>')
    ok, _ = atexo._parse_page(bloc("Déc."), "Mégalis Bretagne", "https://m.test")
    assert ok[0].date_limite == "2026-12-07"
    inconnu, _ = atexo._parse_page(bloc("Xyz."), "Mégalis Bretagne", "https://m.test")
    assert inconnu[0].date_limite is None


# ═══ 2. Rectificatifs et annulations du BOAMP ═══════════════════════════════════════════════════════

def test_lire_rectificatif_sur_les_formes_reelles():
    """Ce que chaque rectificatif réel du 21/10/2026 dit de la date limite (lu, ou « non lu » : jamais deviné)."""
    from app.sourcing.sources.boamp import lire_rectificatif
    attendu = {
        "26-96286": (True, "2026-11-06"),   # simplifié, structuré : lireDate
        "26-102497": (True, "2026-11-09"),  # simplifié, structuré
        "26-102146": (True, "2026-10-30"),
        "26-102300": (True, "2026-11-05"),  # national : « Au lieu de 21/10/2026 à 12h00, lire 05/11/2026 »
        "26-102361": (True, "2026-11-17"),
        "26-102403": (True, "2026-10-27"),
        "26-102230": (True, "2026-11-27"),  # deux rubriques : la date limite et la visite (ignorée)
        "26-102338": (True, "2026-11-03"),  # « … est modifiée au 03/11/2026 à 12h00. »
        "26-102325": (True, "2026-10-29"),  # « … reportée au jeudi 29 octobre 2026 à 14 heures. »
        "26-102494": (True, "2026-11-02"),  # « … : 02 novembre 2026 à 12h00 »
        "26-102254": (True, "2026-11-09"),  # « … est le lundi 09 novembre 2026 à 13h. »
        "26-102090": (True, "2026-10-28"),  # simplifié, texte libre : « … au 28/10/2026 - 12h00. »
        "26-102412": (True, None),          # « … reportée au vendredi 30 octobre à 17h00. » : sans année
        "26-102209": (True, None),          # « … reportée au lundi 9 novembre à 12:00. » : sans année
        "26-101444": (True, None),          # « DLRO initiale : 26 octobre 2026 … mise à jour : 2 novembre 2026 »
        "26-102445": (False, None),         # numéros des lots : la date limite reste celle de l'avis
        "26-100570": (False, None),         # critères d'attribution
    }
    for idweb, (concerne, d) in attendu.items():
        lu = lire_rectificatif(SUITES[idweb])
        assert (lu["concerne"], lu["date"]) == (concerne, d), (idweb, lu)
    # Format européen : la version complète de l'avis porte sa date structurée.
    assert lire_rectificatif(AVIS["26-101544"])["date"] == "2026-11-18"


def test_lire_rectificatif_formes_jamais_observees_prudentes():
    """Cas CONSTRUITS : une forme jamais observée ne donne jamais de date ; une date antérieure à la parution
    du rectificatif n'est pas lue ; la date des questions n'est pas la date limite de réponse."""
    from app.sourcing.sources.boamp import lire_rectificatif

    def rect(infos, parution="2026-10-21"):
        corps = {"FNSimple": {"rectificatif": {"infosRectif": infos}}} if infos is not None else {"FNSimple": {}}
        return {"idweb": "26-1", "nature": "RECTIFICATIF", "etat": "RECTIFICATIF", "dateparution": parution,
                "donnees": json.dumps(corps)}
    assert lire_rectificatif(rect(None)) == {"concerne": True, "date": None, "forme": "non vérifiée"}
    assert lire_rectificatif(rect({"rubDelais": "ReceptionCandidatures", "lireDate": "2026-11-20T12:00:00"}))["date"] is None
    assert lire_rectificatif(rect(42))["date"] is None and lire_rectificatif(rect(42))["concerne"] is True
    # Date antérieure à la parution du rectificatif : impossible, donc non lue.
    assert lire_rectificatif(rect("La date limite de remise des offres est reportée au 03/11/2025."))["date"] is None
    # Questions, visite, ouverture des plis : la date limite de réponse n'est pas touchée.
    for texte in ("La date limite pour poser des questions est reportée au 25/10/2026.",
                  "Rubrique : Visite des lieux, Au lieu de 22/10/2026, lire 29/10/2026",
                  "Date d'ouverture des offres : Au lieu du 10/11/2026, lire 26/11/2026"):
        assert lire_rectificatif(rect(texte))["concerne"] is False, texte
    # Deux dates différentes, sans « au lieu de … lire … » : aucune n'est choisie.
    assert lire_rectificatif(rect("Remise des offres : 05/11/2026 ; ouverture le 06/11/2026"))["date"] is None


def test_boamp_rectificatifs_et_annulations_rattaches(monkeypatch, caplog):
    """La recherche sur le jeu réel du 21/10/2026 : une fiche par procédure, la date du rectificatif, les
    annulations retirées (formats national et européen), et l'avis de 26-90336 repris par son rectificatif."""
    _figer(monkeypatch)
    principaux = [AVIS[i] for i in ("26-101544", "26-101475", "26-101778", "26-95755", "26-90521", "26-94570",
                                    "26-93829", "26-95098", "26-91602", "26-91526")]
    appels = _api(monkeypatch, principaux, suites=list(SUITES.values()), initiaux=[AVIS["26-90336"]])
    with caplog.at_level(logging.INFO, logger="adjugo"):
        res = _cherche()
    t = _par_ref(res)
    # Annulations : la nationale 26-95892 retire 26-95755 ; l'européenne 26-101778 retire 26-91526 et elle-même.
    assert "26-95755" not in t and "26-91526" not in t and "26-101778" not in t
    # Rectificatifs nationaux : la nouvelle date, l'ancienne gardée à part, le lien du rectificatif.
    assert t["26-90521"].date_limite == "2026-11-05" and t["26-90521"].date_limite_initiale == "2026-10-21"
    assert [p.official_ref for p in t["26-90521"].rectificatifs] == ["26-102300"]
    assert t["26-90521"].rectificatifs[0].source_url == "https://www.boamp.fr/pages/avis/?q=idweb:26-102300"
    assert t["26-90521"].rectifie_le == "2026-10-21" and t["26-90521"].date_limite_rectifiee_non_lue is False
    assert t["26-94570"].date_limite == "2026-11-03" and t["26-91602"].date_limite == "2026-11-09"
    # Format européen : la version rectifiée REMPLACE l'avis initial (une seule fiche, sa référence, sa date).
    assert "26-101544" not in t and t["26-93829"].date_limite == "2026-11-18"
    assert t["26-93829"].date_limite_initiale == "2026-11-02"
    assert t["26-93829"].provenance.source_url == "https://www.boamp.fr/pages/avis/?q=idweb:26-93829"
    # Rectificatif européen qui ne change pas la date (montants) : la date reste, le rectificatif est listé.
    assert "26-101475" not in t and t["26-95098"].date_limite == "2026-11-03"
    assert t["26-95098"].date_limite_initiale is None and t["26-95098"].rectifie_le == "2026-10-21"
    # 26-90336 : sa limite du 16/10 est passée, mais 26-96286 l'a repoussée au 06/11 (critère de l'étude).
    assert t["26-90336"].date_limite == "2026-11-06" and t["26-90336"].date_limite_initiale == "2026-10-16"
    assert sorted(t) == ["26-90336", "26-90521", "26-91602", "26-93829", "26-94570", "26-95098"]
    # Trois requêtes : les avis, leurs suites (sans le corps des avis), la relecture de 26-90336.
    assert len(appels) == 3
    assert "donnees" not in appels[0]["select"] and "donnees" in appels[1]["select"]
    w = appels[1]["where"]
    assert "annonce_lie in (" in w and '"26-90521"' in w and '"26-93829"' in w
    assert "nature=\"RECTIFICATIF\" AND dateparution >= date'2026-08-22'" in w     # 60 jours
    assert appels[2]["where"].startswith("idweb in (") and '"26-90336"' in appels[2]["where"].split(" OR ")[0]
    assert any("annulé(s) retiré(s)" in r.getMessage() for r in caplog.records)
    # Le navigateur reçoit les nouveaux champs (sans le corps brut).
    carte = t["26-90521"].model_dump(exclude={"raw"})
    assert carte["rectificatifs"][0]["official_ref"] == "26-102300" and carte["date_limite_initiale"] == "2026-10-21"


def test_boamp_date_rectifiee_illisible_non_precisee_jamais_l_ancienne(monkeypatch):
    """Lien CONSTRUIT : le rectificatif réel 26-102412 (« reportée au vendredi 30 octobre à 17h00 », sans année)
    rattaché à l'avis réel 26-94570. La date devient « non précisée » et l'avis reste affiché ; un doublon d'une
    autre source ne la comble jamais."""
    from app.sourcing.schemas import Provenance
    from app.sourcing.search import _dedup_tenders
    _figer(monkeypatch)
    rect = dict(SUITES["26-102412"], annonce_lie=["26-94570"])
    _api(monkeypatch, [AVIS["26-94570"]], suites=[rect])
    t = _par_ref(_cherche())["26-94570"]
    assert t.date_limite is None and t.date_limite_rectifiee_non_lue is True
    assert t.date_limite_initiale == "2026-10-29" and t.rectifie_le == "2026-10-21"
    autre = t.model_copy(deep=True)
    autre.date_limite, autre.date_limite_rectifiee_non_lue = "2026-10-29", False
    autre.provenance = Provenance(source="Autre", source_url="https://exemple.test/a", official_ref="x")
    fusion = _dedup_tenders([t, autre])
    assert fusion[0].date_limite is None


def test_boamp_rectificatif_hors_date_garde_la_date(monkeypatch):
    """Lien CONSTRUIT : le rectificatif réel 26-102445 (numéros des lots) rattaché à l'avis réel 26-94570 :
    la date limite ne change pas, le rectificatif est listé."""
    _figer(monkeypatch)
    rect = dict(SUITES["26-102445"], annonce_lie=["26-94570"])
    _api(monkeypatch, [AVIS["26-94570"]], suites=[rect])
    t = _par_ref(_cherche())["26-94570"]
    assert t.date_limite == "2026-10-29" and t.date_limite_initiale is None
    assert t.date_limite_rectifiee_non_lue is False and [p.official_ref for p in t.rectificatifs] == ["26-102445"]


def test_boamp_rectificatif_europeen_seul_prend_la_reference_de_son_avis(monkeypatch):
    """26-101544 renvoyé sans son avis initial : une fiche à la référence et au lien de 26-93829 (mêmes alertes,
    même page suivante), datée du 18/11, le rectificatif listé."""
    _figer(monkeypatch)
    _api(monkeypatch, [AVIS["26-101544"]])
    res = _cherche()
    assert [x.provenance.official_ref for x in res["tenders"]] == ["26-93829"]
    t = res["tenders"][0]
    assert t.provenance.source_url == "https://www.boamp.fr/pages/avis/?q=idweb:26-93829"
    assert t.date_limite == "2026-11-18" and [p.official_ref for p in t.rectificatifs] == ["26-101544"]


def test_boamp_suites_en_panne_la_recherche_continue(monkeypatch, caplog):
    """La requête des suites échoue : la recherche rend ses avis, sans erreur ; ce que la page dit d'elle-même
    (annulation et rectificatif européens) est appliqué ; le journal le dit."""
    _figer(monkeypatch)
    principaux = [AVIS[i] for i in ("26-101544", "26-101778", "26-93829", "26-91526", "26-94570")]
    _api(monkeypatch, principaux, suites=list(SUITES.values()), panne_suites=True)
    with caplog.at_level(logging.WARNING, logger="adjugo"):
        res = _cherche()
    t = _par_ref(res)
    assert res["errors"] == [] and sorted(t) == ["26-93829", "26-94570"]
    assert t["26-93829"].date_limite == "2026-11-18" and t["26-94570"].date_limite == "2026-10-29"
    assert any("rectificatifs et annulations récents non lus" in r.getMessage() for r in caplog.records)


def test_boamp_page_suivante_sans_reprise(monkeypatch):
    """« Charger plus » (offset > 0) : les suites des avis affichés seulement, ni rectificatifs récents ni
    relecture d'avis initiaux (sinon les mêmes avis repris reviendraient sur chaque page)."""
    from app.sourcing.base import TenderCriteria
    _figer(monkeypatch)
    appels = _api(monkeypatch, [AVIS["26-90521"]], suites=list(SUITES.values()), initiaux=[AVIS["26-90336"]])
    res = _cherche(TenderCriteria(query="travaux", limit=15, offset=15))
    assert [x.provenance.official_ref for x in res["tenders"]] == ["26-90521"]
    assert len(appels) == 2 and "dateparution >=" not in appels[1]["where"]


# ═══ 3. Le vocabulaire interne du BOAMP n'est pas un code métier européen ═══════════════════════════

def test_boamp_descripteurs_jamais_lus_comme_cpv(monkeypatch):
    """26-90336 a pour descripteurs 310, 91, 197 (« Rivières/ruisseaux », « Digue », « Maîtrise d'oeuvre ») :
    aucun code CPV ; la complétude affichée ne change pas ; les CPV saisis ne sont plus cherchés au BOAMP."""
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource
    _figer(monkeypatch)
    t = BoampSource()._normalize(dict(AVIS["26-90336"]))
    assert t.cpv == [] and t.raw["descripteur_code"] == ["310", "91", "197"]
    assert t.confidence == 1.0
    appels = _api(monkeypatch, [])
    BoampSource().search(TenderCriteria(query="voirie", cpv=["45233140", "45"]))
    assert "descripteur_code" not in appels[0]["where"]


def test_score_pas_de_metier_correspondant_sur_un_faux_code():
    """« 45 » (vocabulaire BOAMP : « Cd, DVD ») ne correspond plus au CPV 45261000 ; un vrai CPV, avec ou sans
    sa clé de contrôle, correspond toujours."""
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.scoring import score_tender

    def metier(cpv):
        t = NormalizedTender(objet="Fourniture de supports", cpv=cpv, departements=["29"],
                             provenance=Provenance(source="BOAMP", source_url="https://www.boamp.fr/x"))
        return next(c for c in score_tender(t, {}, {"codes_cpv": ["45261000"]}).breakdown if c.key == "cpv")
    assert metier(["45"]).points == 0 and metier(["345", "4"]).points == 0
    assert metier(["45261000-7"]).points > 0 and metier(["45261210"]).points > 0


# ═══ 4. Outre-mer : le code complet ; la Corse intacte ══════════════════════════════════════════════

def test_recherche_departements_outre_mer_code_complet(monkeypatch):
    from app.sourcing.base import TenderCriteria, TenderSource
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.search import TenderSearchService
    _figer(monkeypatch)
    deps = [["971"], ["974"], ["2A"], ["2B"], ["29"], ["06"], []]

    class _Source(TenderSource):
        name = "Essai"

        def search(self, criteria):
            return [NormalizedTender(objet=f"Avis {i}", departements=d, dedup_key=f"k{i}",
                                     provenance=Provenance(source="Essai", source_url="https://e.test",
                                                           official_ref=str(i)))
                    for i, d in enumerate(deps)]

    def garde(*voulus):
        res = TenderSearchService([_Source()]).search(TenderCriteria(departements=list(voulus)), {}, {})
        return sorted(tuple(t.departements) for t in res["tenders"])
    assert garde("974") == [(), ("974",)]                       # avant : la Guadeloupe (971) passait aussi
    assert garde("971", "29") == [(), ("29",), ("971",)]
    assert garde("2A") == [(), ("2A",)] and garde("2B") == [(), ("2B",)]
    assert garde("97") == [(), ("971",), ("974",)]              # « 97 » saisi : tout l'outre-mer, comme avant
    assert garde("6") == [(), ("06",)]


def test_score_zone_outre_mer_et_corse():
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.scoring import score_tender

    def zone(dep, crit=None, cp=""):
        t = NormalizedTender(objet="Avis", departements=[dep],
                             provenance=Provenance(source="BOAMP", source_url="https://www.boamp.fr/x"))
        return next(c for c in score_tender(t, {"postal_code": cp}, crit or {}).breakdown if c.key == "zone").status
    assert zone("974", {"departements": ["974"]}) == "ok"          # avant : « hors zone »
    assert zone("971", {"departements": ["974"]}) == "partiel"
    assert zone("974", cp="97400") == "ok" and zone("971", cp="97400") == "partiel"   # avant : 971 « dans la zone »
    assert zone("2A", {"departements": ["2A"]}) == "ok" and zone("2B", {"departements": ["2A"]}) == "partiel"
    assert zone("29", cp="29200") == "ok" and zone("2A", cp="20000") == "partiel"     # Corse par code postal : inchangé


# ═══ Contrat ════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_section_sources():
    doc = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    assert "## Sources" in doc
    for mot in ("annonce_lie", "non vérifié", "26-90336", "descripteur_code", "2A", "Ce qui change pour le client"):
        assert mot in doc, mot
