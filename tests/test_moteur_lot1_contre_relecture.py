"""Moteur de recherche, lot 1 « Dire juste » : contre-relecture de la partie serveur (docs/MOTEUR_LOT1.md, section
« Contre-relecture »). Une remarque, un test ; chacun échoue sur 0afc1ed (production) et sur f86e510 (relecture).

Jeux d'essai RÉELS, sans réseau pendant les tests : ceux du lot (tests/fixtures/*.json et tests/fixtures/moteur_lot1_*/),
dont l'avis 26-100294 (limite le 23/10/2026) et son seul rectificatif 26-100865, relus le 21/10/2026. Les textes de
rectificatif « … avant la date limite de remise des offres fixée au … » sont CONSTRUITS : cette forme n'a jamais été
observée (contrat, C.1, « non vérifié »).
"""
import glob
import json
import re

from tests.test_moteur_lot1_relecture import QUESTIONS, ROOT, _api, _figer


def _avec_infos(rect, infos):
    """Le rectificatif réel 26-100865, son bloc « rectificatif » remplacé par `infos` (cas construit)."""
    return dict(rect, donnees=json.dumps({"FNSimple": {"suite": {"infosRectif": infos}}}, ensure_ascii=False))


def _fiche(monkeypatch, rect):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource
    _api(monkeypatch, [QUESTIONS["avis"]], [rect], [])
    (t,) = BoampSource().search(TenderCriteria(query="plan de référence", departements=["82"], limit=15))
    return t


# ═══ C.1 La date limite nommée derrière « avant » : un rectificatif qui la change n'est jamais écarté ═════════════

def test_rectificatif_qui_nomme_la_date_limite_derriere_avant_n_est_jamais_ecarte(monkeypatch):
    """« Au lieu de : offres à déposer avant la date limite de remise des offres fixée au 23/10/2026, lire : … fixée au
    05/11/2026 » : f86e510 le lisait « ne concerne pas » (la règle du repère retirait tout le passage) et gardait le
    23/10 ; 0afc1ed ne lit aucun rectificatif. Après : la nouvelle date, lue accolée à la date limite ; une date qui
    n'y est pas accolée n'est jamais prise (« non précisée », jamais l'ancienne ni celle d'un autre délai) ; un texte
    sans aucune date (26-100865) laisse toujours la date de l'avis."""
    _figer(monkeypatch)
    rect = QUESTIONS["rectificatif"]
    assert (QUESTIONS["avis"]["datelimitereponse"] or "")[:10] == "2026-10-23"

    # 1. La forme de la remarque, sur l'avis réel : la nouvelle date, l'ancienne gardée comme « initiale ».
    change = _avec_infos(rect, [
        "Rubrique : Délais, Au lieu de : offres à déposer avant la date limite de remise des offres fixée au "
        "23/10/2026 à 12h00, lire : offres à déposer avant la date limite de remise des offres fixée au 05/11/2026 à 12h00"])
    t = _fiche(monkeypatch, change)
    assert t.date_limite == "2026-11-05"                    # 0afc1ed et f86e510 : le 23/10, l'ancienne date
    assert (t.date_limite_initiale, t.date_limite_rectifiee_non_lue) == ("2026-10-23", False)
    from app.sourcing.sources.boamp import lire_rectificatif
    assert lire_rectificatif(change) == {"concerne": True, "date": "2026-11-05", "forme": "texte"}

    # 2. Une date accolée mais sans année : jamais complétée, et jamais l'ancienne date.
    sans_annee = _avec_infos(rect, [
        "Les offres devront être déposées avant la date limite de réception des offres fixée au 5 novembre à 12h00"])
    t = _fiche(monkeypatch, sans_annee)
    assert (t.date_limite, t.date_limite_initiale, t.date_limite_rectifiee_non_lue) == (None, "2026-10-23", True)

    # 3. Un autre délai qui cite des dates et la date limite comme repère : « non précisée », jamais le 25/10 (la date
    #    des questions) ni le 23/10 gardé en silence.
    questions = _avec_infos(rect, [
        "Au lieu de : questions au plus tard le 13/10/2026, soit 10 jours avant la date limite de réception des offres, "
        "lire : questions au plus tard le 16/10/2026, soit 7 jours avant la date limite de réception des offres"])
    t = _fiche(monkeypatch, questions)
    assert (t.date_limite, t.date_limite_rectifiee_non_lue) == (None, True)
    assert lire_rectificatif(questions) == {"concerne": True, "date": None, "forme": "texte"}

    # 4. Le rectificatif réel 26-100865 (aucune date, un délai compté en jours) : la date de l'avis reste.
    assert lire_rectificatif(rect)["concerne"] is False
    t = _fiche(monkeypatch, rect)
    assert (t.date_limite, t.date_limite_initiale, t.date_limite_rectifiee_non_lue) == ("2026-10-23", None, False)

    # 5. Autres écritures de la même forme (construites).
    def lu(infos):
        x = lire_rectificatif(_avec_infos(rect, infos))
        return x["concerne"], x["date"]
    assert lu(["Les offres devront être déposées avant la date limite de réception des offres fixée au 05/11/2026 à "
               "12h00"]) == (True, "2026-11-05")
    assert lu(["Offres à remettre avant la date et l'heure limites de remise des plis fixées au jeudi 5 novembre 2026 "
               "à 12h00"]) == (True, "2026-11-05")
    # Deux dates accolées différentes sans « au lieu de … lire … » : aucune n'est choisie.
    assert lu(["Avant la date limite de remise des offres fixée au 23/10/2026 ; après la date limite de remise des "
               "offres prévue le 05/11/2026"]) == (True, None)
    # Forme en champs : seule la partie « lire » donne la date.
    assert lu([{"rubrique": "Délais", "auLieuDe": "Offres avant la date limite de remise des offres fixée au 23/10/2026",
                "lire": "Offres avant la date limite de remise des offres fixée au 05/11/2026"}]) == (True, "2026-11-05")
    assert lu([{"rubrique": "Délais", "auLieuDe": "Questions le 13/10/2026, 10 jours avant la date limite de remise des offres",
                "lire": "Questions le 16/10/2026, 7 jours avant la date limite de remise des offres"}]) == (True, None)
    # Un texte qui ne parle d'aucune date limite reste sans effet, même avec des dates.
    assert lu(["Rubrique : Visite des lieux, Au lieu de 22/10/2026, lire 29/10/2026"]) == (False, None)


# ═══ C.2 La comparaison de V.3, rejouable depuis le dépôt ════════════════════════════════════════════════════════

def _suites_des_jeux_d_essai():
    """Toutes les lignes de rectificatif (hors annulations) des jeux d'essai du dépôt : (lignes, distinctes)."""
    from app.sourcing.sources import boamp

    def lignes(o):
        if isinstance(o, dict):
            if "idweb" in o and ("nature" in o or "etat" in o):
                yield o
            for v in o.values():
                yield from lignes(v)
        elif isinstance(o, list):
            for v in o:
                yield from lignes(v)

    toutes, distinctes = [], {}
    for f in sorted(glob.glob(str(ROOT / "tests" / "fixtures" / "**" / "*.json"), recursive=True)):
        for r in lignes(json.loads(open(f, encoding="utf-8").read())):
            if boamp._est_suite(r) and not boamp._est_annulation(r):
                toutes.append(r)
                distinctes.setdefault(boamp._idweb(r), r)
    return toutes, distinctes


def test_comparaison_rejouable_sur_les_rectificatifs_reels_des_jeux_d_essai(monkeypatch):
    """V.3 citait « 173 rectificatifs réels », introuvables dans les jeux d'essai. Rejoué ici : 144 lignes, 127
    rectificatifs distincts, dont 119 avec un corps `infosRectif` (136 éléments) et 8 au format européen ; sans la
    règle du repère, seule la lecture de 26-100865 change ; la règle de C.1 (repère et date) ne sert à aucun d'eux."""
    from app.sourcing.sources import boamp
    toutes, distinctes = _suites_des_jeux_d_essai()
    corps = {i: r for i, r in distinctes.items() if boamp._infos_rectif(r.get("donnees")) is not None}
    elements = sum(len(x) if isinstance(x, list) else 1 for x in (boamp._infos_rectif(r.get("donnees")) for r in corps.values()))
    europeens = [i for i, r in distinctes.items() if boamp._au_format_europeen(r)]
    assert (len(toutes), len(distinctes), len(corps), elements, len(europeens)) == (144, 127, 119, 136, 8)

    appels = []
    vraie = boamp._dates_accolees
    monkeypatch.setattr(boamp, "_dates_accolees", lambda texte: appels.append(texte) or vraie(texte))
    avec = {i: boamp.lire_rectificatif(r) for i, r in distinctes.items()}
    assert appels == []                                           # aucun rectificatif réel n'emprunte C.1
    monkeypatch.setattr(boamp, "_REPERE_DU_DELAI", re.compile(r"(?!x)x"))
    sans = {i: boamp.lire_rectificatif(r) for i, r in distinctes.items()}
    assert [i for i in distinctes if avec[i] != sans[i]] == ["26-100865"]

    # Le contrat cite ce nombre rejouable, au point 5 de la liste et dans la preuve de V.3 (« 173 » n'y est plus qu'en
    # rappel de l'ancien texte, entre guillemets).
    doc = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    liste = doc[doc.index("## Ce qui change pour le client"):doc.index("## Sources")]
    v3 = doc[doc.index("### V.3"):doc.index("### V.4")]
    for texte in (liste, v3):
        assert "173 rectificatifs" not in texte and "127 rectificatifs réels" in texte
    assert "119" in v3 and "test_comparaison_rejouable" in v3


# ═══ Contrat ═════════════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_section_contre_relecture():
    doc = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    assert "## Contre-relecture" in doc
    section = doc[doc.index("## Contre-relecture"):]
    for mot in ("### C.1", "### C.2", "fixée au", "Non vérifié", "26-100865", "f86e510", "127 rectificatifs"):
        assert mot in section, mot
    v3 = doc[doc.index("### V.3"):doc.index("### V.4")]
    assert "Non vérifié" in v3
