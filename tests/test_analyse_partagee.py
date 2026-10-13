"""Analyse PARTAGÉE (docs/ANALYSE_PARTAGEE.md) : moins de coût d'IA, sans rien changer à la qualité.

1. Rien n'est perdu : la consigne de l'extraction garde tous les champs ; mêmes champs à l'écran et
   même carte « Comment vous serez noté » avant / après (analyse d'origine en un appel ↔ analyse en
   deux temps), sur des cas synthétiques et par les vraies routes.
2. Extraction partagée : servie sans appel au second import du même dossier (autre organisation),
   « Ré-analyser » la refait, un rectificatif / un autre modèle / d'autres consignes donnent une autre
   clé, une extraction incomplète, illisible ou faite par le secours n'est jamais gardée.
3. Confidentialité : aucune donnée d'entreprise dans l'extraction (prompt et base), rien dans l'API ni
   à l'écran ne trahit le partage, les choix de chaque client restent à lui, la mesure n'est jamais
   montrée à un client.
4. Coût : quota débité comme d'habitude ; extraction comptée à la plateforme (forfait payant) ou à
   l'essai (extraction neuve), rien pour une extraction resservie.
5. Mesure, /metrics, purge, effacement du compte ; cache de prompt de la lecture des pièces.
"""
import copy
import json
import re
import uuid

import pytest

from app.services import llm
from tests.test_redaction_socle0 import FakeLLM, _Resp, _Usage, _db, _user_id
from tests.test_lecture_integrale import (FAIT, RC_TETE, _petit_dossier, _texte, _wait, _zip, appels_dossier,
                                          appels_entreprise)

ENTREPRISE = "partie PROPRE A CETTE ENTREPRISE"
PIECES = "Tu lis UNE pièce"

# Profil et critères DISTINCTIFS : aucune de ces valeurs ne doit jamais entrer dans l'extraction partagée.
PROFIL_A = {"name": "Zorglub Toitures SARL", "siret": "98765432100017", "city": "Plouzané", "ca_n1": 731_913,
            "effectif": 17, "email": "contact@zorglub-toitures.fr", "phone": "0298765432",
            "team": [{"nom": "Yann Tanguy", "fonction": "Chef de chantier"}],
            "qualifications": [{"name": "Qualibat 3194 ardoise"}]}
CRITERES_A = {"penalty_max": 3.7, "garantie_max": 4.3, "retenue_garantie_max": 2.9, "delai_reponse_min": 23,
              "specialites": "couverture zinc ardoise velux", "departements": "29, 56"}
SECRETS_A = ["Zorglub", "98765432100017", "Plouzané", "731", "zorglub-toitures", "0298765432", "Yann Tanguy",
             "Tanguy", "3194 ardoise", "3.7", "4.3", "2.9", "velux"]

RECO_3 = ("Le marché porte sur la réfection de la couverture du groupe scolaire.\n\n"
          "L'acheteur note la valeur technique à 60 % et le prix à 40 %.\n\n"
          "Les pénalités de retard et la visite obligatoire sont à maîtriser.")
EXTRACTION = {
    "summary": "Réfection de la couverture d'un groupe scolaire, procédure adaptée.",
    "details": {
        "intitule_marche": "Réfection de la couverture du groupe scolaire",
        "acheteur": "Commune de Plomodiern",
        "contact": {"nom": "", "fonction": "", "email": "", "telephone": ""},
        "type_marche": "Travaux", "nature_marche": "MAPA", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "180 000 EUR HT", "date_limite": "31/12/2099 a 12h00",
        "delai_execution": "4 mois", "lieu_execution": "Plomodiern (29)", "allotissement": "Lot unique",
        "criteres_attribution": [
            {"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}],
        "garanties_exigees": "Retenue de garantie 5 %", "avance": "Non specifie dans le DCE",
        "penalites": "1/1000 du montant HT par jour de retard, plafonnees a 10 %",
        "sous_traitance": "Autorisee", "variantes": "Non autorisees", "critere_rse": "Non",
        "ca_minimum_requis": "CA > 400 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3194"],
        "references_requises": "Non specifie dans le DCE", "effectif_minimum_requis": "Non specifie dans le DCE",
        "capacites_groupement": "Non specifie dans le DCE",
        "forme_groupement": {"imposee": "non_specifie", "extrait": ""},
        "exigences_sources": {"ca_minimum_requis": "", "qualifications_requises": "", "references_requises": "",
                              "effectif_minimum_requis": "", "capacites_groupement": ""},
        "assurances_requises": ["Decennale"], "visite_obligatoire": "Oui",
        "pieces_requises": [{"nom": "DC1 - Lettre de candidature", "disponible": True},
                            {"nom": "Memoire technique", "disponible": False}],
        "points_attention": ["Visite obligatoire avant la remise des offres",
                             "Pénalités plafonnées à 10 % du montant"],
        "recommandation": RECO_3,
        "clauses_risque": [{"clause": "Penalites de retard", "niveau": "moyen",
                            "pourquoi": "1/1000 du HT par jour, plafonnees a 10 % du montant du marche",
                            "levier_negociation": "Demander un plafond a 5 %"}],
    },
}
STRATEGIE = "STRATEGIE-PROPRE : y aller en groupement, compatibilité à étudier."
POINT_ENT = "CA exigé (400 000 EUR) supérieur à votre CA N-1"
POURQUOI_ENT = "Au-delà de votre seuil de pénalités de retard."


def _entreprise_json(user: str) -> dict:
    m = re.search(r"Denomination : (.+)", user)
    nom = m.group(1).strip() if m else "?"
    return {"strategie": f"{STRATEGIE} Pour {nom}.", "points_attention_entreprise": [POINT_ENT],
            "clauses": [{"index": 0, "niveau": "eleve", "pourquoi_entreprise": POURQUOI_ENT}],
            "clauses_ajoutees": []}


def _repondre(kw, extraction=None):
    from tests.test_lecture_integrale import _answer
    system = llm._flatten_content(kw.get("system"))
    user = llm._flatten_content(kw["messages"][0]["content"])
    if PIECES in system:
        return _answer(kw)
    if ENTREPRISE in system:
        return json.dumps(_entreprise_json(user), ensure_ascii=False), "end_turn"
    return json.dumps(extraction or EXTRACTION, ensure_ascii=False), "end_turn"


class _Fake(FakeLLM):
    """Faux fournisseur : coût d'une extraction (gros) bien distinct de celui de la partie propre à
    l'entreprise (petit), pour vérifier à qui chaque coût est compté."""

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop = self._answer(kwargs)
        system = llm._flatten_content(kwargs.get("system"))
        usage = _Usage(1_000, 100) if ENTREPRISE in system else _Usage(200_000, 4_000)
        return _Resp(text, stop, usage=usage)


@pytest.fixture
def ia(monkeypatch):
    def install(answer=_repondre):
        fake = _Fake(answer)
        monkeypatch.setattr(llm, "client", lambda: fake)
        monkeypatch.setattr(llm, "_use_mistral", lambda: False)
        llm._CB.update(fails=0, open_until=0.0)
        llm._TENANT_CB.clear()
        return fake
    return install


@pytest.fixture
def attentes(monkeypatch):
    """Délai de l'analyse partagée relevé (sans attendre pour de vrai)."""
    from app.services import analyse_partagee as ap
    vus = []
    monkeypatch.setattr(ap, "attendre", lambda d, progress=None, etapes=None: vus.append((d, list(etapes or []))))
    return vus


def _compte(client, plan=None, profil=None, criteres=None):
    from app.models import User
    email = f"ap_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                               "full_name": "Test", "company_name": (profil or {}).get("name") or "PME"})
    assert r.status_code == 201, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        if plan:
            u.plan = plan
        db.commit()
    finally:
        db.close()
    if profil:
        r = client.put("/api/company/", headers=h, json=profil)
        assert r.status_code == 200, r.text
    if criteres:
        r = client.put("/api/criteria/", headers=h, json=criteres)
        assert r.status_code == 200, r.text
    return {"headers": h, "email": email, "id": _user_id(email)}


def _projet(client, h, nom="Couverture"):
    r = client.post("/api/projects/", headers=h, json={"name": nom, "client": "Commune"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _importer(client, compte, contenu=None, nom="DCE.zip", attendu=200):
    pid = _projet(client, compte["headers"])
    r = client.post("/api/sourcing/analyze-upload", headers=compte["headers"], data={"project_id": str(pid)},
                    files={"file": (nom, contenu or _petit_dossier(), "application/zip")})
    assert r.status_code == attendu, r.text
    return pid, r


def _lignes_partagees():
    from app.models import AnalysePartagee
    db = _db()
    try:
        return [{c.name: getattr(x, c.name) for c in AnalysePartagee.__table__.columns}
                for x in db.query(AnalysePartagee).all()]
    finally:
        db.close()


def _mesures():
    from app.models import AnalyseEmpreinte
    db = _db()
    try:
        return [{c.name: getattr(x, c.name) for c in AnalyseEmpreinte.__table__.columns}
                for x in db.query(AnalyseEmpreinte).order_by(AnalyseEmpreinte.id).all()]
    finally:
        db.close()


def _used(email):
    from app.models import User
    db = _db()
    try:
        return db.query(User).filter(User.email == email).first().analyses_used_this_month or 0
    finally:
        db.close()


def _cles_analyse(r: dict) -> set:
    """Clés d'une réponse, hors verdict de groupement (calculé pour CHAQUE entreprise, d'après son
    profil, par le routeur : il diffère d'une entreprise à l'autre, partage ou non)."""
    return {k for k in _cles(r) if not k.startswith((".groupement", ".project_id"))}


def _cles(x, prefix=""):
    """Toutes les clés (chemin) d'une structure JSON, listes comprises (indices remplacés par [])."""
    out = set()
    if isinstance(x, dict):
        for k, v in x.items():
            out.add(prefix + "." + str(k))
            out |= _cles(v, prefix + "." + str(k))
    elif isinstance(x, list):
        for v in x:
            out |= _cles(v, prefix + "[]")
    return out


# ═══ 1. Rien n'est perdu ═════════════════════════════════════════════════════════════════════════

def _exemple_json(consigne: str) -> dict:
    """Le format JSON attendu, tel que la consigne le donne à l'IA."""
    debut = consigne.index("{\n")
    obj, _ = json.JSONDecoder().raw_decode(consigne[debut:])
    return obj


def test_consigne_d_extraction_garde_tous_les_champs_et_toutes_les_regles():
    from app.services import analysis as an
    avant, apres = _exemple_json(an.SYSTEM_PROMPT), _exemple_json(an.SYSTEM_EXTRACTION)
    # Mêmes champs à extraire, au détail près ; seuls le score et le verdict (recalculés sans IA,
    # jamais gardés depuis l'IA) ne sont plus demandés.
    assert set(avant) - set(apres) == {"match_score", "go_decision"} and set(apres) <= set(avant)
    assert _cles(avant["details"]) == _cles(apres["details"])
    # Toutes les règles d'origine restent, mot pour mot, sauf les passages listés (et vérifiés à l'import).
    zones = []
    for a, _b in an._EXTRACTION_REMPLACEMENTS:
        i = an.SYSTEM_PROMPT.index(a)
        zones.append((i, i + len(a)))
    pos, gardees = 0, 0
    for ligne in an.SYSTEM_PROMPT.split("\n"):
        debut, fin = pos, pos + len(ligne)
        pos = fin + 1
        if ligne.strip() and not any(debut < z1 and z0 < fin for z0, z1 in zones):
            assert ligne in an.SYSTEM_EXTRACTION, ligne
            gardees += 1
    assert gardees >= 60                                       # l'essentiel de la consigne, mot pour mot
    # Plus aucune instruction qui suppose le profil de l'entreprise.
    assert "seuils de l'entreprise fournis" not in an.SYSTEM_EXTRACTION
    assert "Tu ne connais pas l'entreprise candidate" in an.SYSTEM_EXTRACTION
    # La partie propre à l'entreprise prend le relais de ce qui était personnalisé.
    for mot in ("strategie", "points_attention_entreprise", "pourquoi_entreprise", "clauses_ajoutees"):
        assert mot in an.SYSTEM_ENTREPRISE


def _original(user_prompt_vu=None):
    """Réponse de l'analyse d'ORIGINE (un appel, profil compris) pour le même dossier : les mêmes faits,
    plus ce que l'IA personnalisait (4e paragraphe, point propre à l'entreprise, seuil dépassé)."""
    o = copy.deepcopy(EXTRACTION)
    o["match_score"], o["go_decision"] = 80, "go"
    d = o["details"]
    d["recommandation"] = RECO_3 + "\n\n" + STRATEGIE + " Pour Zorglub Toitures SARL."
    d["points_attention"] = d["points_attention"] + [POINT_ENT]
    d["clauses_risque"][0]["niveau"] = "eleve"
    d["clauses_risque"][0]["pourquoi"] += " " + POURQUOI_ENT
    return o


def _texte_dce():
    return (RC_TETE + "Le CA minimum est de 400 000 EUR sur trois ans. Qualification Qualibat 3194 exigée.\n"
            + "MARQUEUR-DOSSIER-7781 " + _texte("RC", 4000, 3))


def test_avant_apres_memes_champs_a_l_ecran_et_meme_grille(ia, monkeypatch):
    """Même dossier, même profil : analyse d'origine (un appel) ↔ analyse en deux temps. L'écran reçoit
    les mêmes champs ; la carte « Comment vous serez noté », le score, le verdict, le détail du score,
    l'opportunité de groupement et les citations vérifiées sont identiques ; la recommandation garde
    ses 4 paragraphes, les points d'attention et les clauses gardent ce qui était propre à l'entreprise."""
    from app.services import analysis as an
    texte = _texte_dce()
    profil = dict(PROFIL_A)
    monkeypatch.setenv("ANALYSE_PARTAGEE", "0")
    fake = ia(lambda kw: (json.dumps(_original(), ensure_ascii=False), "end_turn"))
    with llm.tenant_scope(990001):
        avant = an.analyze_dce_text(texte, profil, CRITERES_A, lang_name="français", integral=True)
    assert len(fake.calls) == 1 and "Zorglub" in llm._flatten_content(fake.calls[0]["messages"][0]["content"])

    monkeypatch.setenv("ANALYSE_PARTAGEE", "1")
    fake = ia()
    with llm.tenant_scope(990001):
        apres = an.analyze_dce_text(texte, profil, CRITERES_A, lang_name="français", integral=True)
    assert len(appels_dossier(fake.calls)) == 1 and len(appels_entreprise(fake.calls)) == 1

    assert set(avant) == set(apres)
    assert set(avant["details"]) == set(apres["details"])
    assert _cles(avant) == _cles(apres)
    for k in ("match_score", "go_decision", "score_breakdown", "groupement", "score_deterministe"):
        assert avant[k] == apres[k], k
    for k in ("grille_notation", "exigences_sources", "forme_groupement", "exigences_verifiees",
              "criteres_attribution", "pieces_requises", "intitule_marche", "penalites"):
        assert avant["details"][k] == apres["details"][k], k
    assert apres["details"]["recommandation"] == avant["details"]["recommandation"]
    assert apres["details"]["recommandation"].count("\n\n") == 3            # 4 paragraphes
    assert apres["details"]["points_attention"] == avant["details"]["points_attention"]
    assert apres["details"]["clauses_risque"] == avant["details"]["clauses_risque"]
    assert apres["summary"] == avant["summary"]
    # La partie propre à l'entreprise ne reçoit jamais le dossier entier.
    ent = llm._flatten_content(appels_entreprise(fake.calls)[0]["messages"][0]["content"])
    assert "MARQUEUR-DOSSIER-7781" not in ent and "DEBUT-PIECE-RC" not in ent
    assert "MARQUEUR-DOSSIER-7781" in llm._flatten_content(appels_dossier(fake.calls)[0]["messages"][0]["content"])


def test_avant_apres_par_les_routes_meme_ecran_et_meme_carte(client, ia, monkeypatch):
    """Par la vraie route d'import : mêmes clés dans la réponse et dans l'analyse rangée, même carte
    « Comment vous serez noté », même couverture, avec ANALYSE_PARTAGEE=0 puis 1."""
    a = _compte(client, profil=PROFIL_A, criteres=CRITERES_A)
    monkeypatch.setenv("ANALYSE_PARTAGEE", "0")
    ia(lambda kw: (json.dumps(_original(), ensure_ascii=False), "end_turn"))
    pid0, r0 = _importer(client, a)
    monkeypatch.setenv("ANALYSE_PARTAGEE", "1")
    ia()
    pid1, r1 = _importer(client, a)
    assert _cles(r0.json()) - {".project_id"} == _cles(r1.json()) - {".project_id"}
    p0 = client.get(f"/api/projects/{pid0}", headers=a["headers"]).json()["ai_analysis"]
    p1 = client.get(f"/api/projects/{pid1}", headers=a["headers"]).json()["ai_analysis"]
    assert _cles(p0) == _cles(p1)
    g0, g1 = p0["details"]["grille_notation"], p1["details"]["grille_notation"]
    assert g0 == g1 and g1["criteres"]                     # carte « Comment vous serez noté » identique
    assert {k: v for k, v in p0["couverture"].items()} == p1["couverture"]
    for k in ("score_breakdown", "match_score", "go_decision", "groupement"):
        assert p0[k] == p1[k], k
    assert p1["details"]["recommandation"] == p0["details"]["recommandation"]
    assert p1["details"]["points_attention"] == p0["details"]["points_attention"]


def test_sans_seuil_aucune_clause_marquee_au_dela_d_un_seuil(ia):
    """Comme l'analyse d'origine : une clause n'est « au-delà de votre seuil » que si l'entreprise a
    donné ce seuil ; sans seuil, la partie propre à l'entreprise ne touche à aucune clause."""
    from app.services import analysis as an
    ia()
    r = an.analyze_dce_text(_texte_dce(), {"name": "Sans Seuil"}, {"specialites": "toiture"}, integral=True)
    cl = r["details"]["clauses_risque"][0]
    assert cl["niveau"] == "moyen" and POURQUOI_ENT not in cl["pourquoi"]
    assert r["details"]["recommandation"].endswith("Pour Sans Seuil.")       # stratégie quand même


def test_partie_entreprise_illisible_analyse_objective_entiere(ia):
    """Réponse illisible deux fois : l'analyse objective reste entière (rien d'inventé), jamais un
    échec facturé ni un faux verdict."""
    from app.services import analysis as an

    def ans(kw):
        if ENTREPRISE in llm._flatten_content(kw.get("system")):
            return "pas du json", "end_turn"
        return _repondre(kw)
    fake = ia(ans)
    r = an.analyze_dce_text(_texte_dce(), dict(PROFIL_A), CRITERES_A, integral=True)
    assert len(appels_entreprise(fake.calls)) == 2                          # relancée une fois
    assert r["details"]["recommandation"] == RECO_3 and r["score_deterministe"] is True
    assert r["details"]["grille_notation"]["criteres"]


# ═══ 2. Extraction partagée ═══════════════════════════════════════════════════════════════════════

def test_second_import_autre_organisation_servi_sans_extraction(client, ia, attentes):
    fake = ia()
    a = _compte(client, profil=PROFIL_A, criteres=CRITERES_A)
    b = _compte(client, profil={"name": "Bretagne Couverture", "ca_n1": 2_000_000}, criteres={"penalty_max": 12})
    ua, ub = _used(a["email"]), _used(b["email"])
    pa, ra = _importer(client, a)
    assert len(appels_dossier(fake.calls)) == 1 and len(appels_entreprise(fake.calls)) == 1
    assert len(_lignes_partagees()) == 1 and attentes == []
    n = len(fake.calls)
    pb, rb = _importer(client, b)
    neufs = fake.calls[n:]
    # Aucun appel pour l'extraction : seule la partie propre à B (avec SON profil, sans le dossier).
    assert appels_dossier(neufs) == [] and len(appels_entreprise(neufs)) == 1
    ent = llm._flatten_content(appels_entreprise(neufs)[0]["messages"][0]["content"])
    assert "Bretagne Couverture" in ent and "Zorglub" not in ent and "DEBUT-PIECE-" not in ent
    # Quota débité comme d'habitude, pour les deux.
    assert _used(a["email"]) == ua + 1 and _used(b["email"]) == ub + 1
    # Même écran pour B, avec ce qui est propre à B.
    da, db_ = ra.json()["details"], rb.json()["details"]
    assert _cles_analyse(ra.json()) == _cles_analyse(rb.json())
    assert db_["recommandation"].endswith("Pour Bretagne Couverture.") and "Zorglub" not in json.dumps(rb.json())
    assert db_["grille_notation"] == da["grille_notation"]
    # La rapidité ne trahit rien : la première fois, B attend la durée de l'extraction ; ensuite, non.
    assert len(attentes) == 1
    _importer(client, b)
    assert len(attentes) == 1
    # A, qui a fait l'extraction, n'attend jamais.
    _importer(client, a)
    assert len(attentes) == 1
    m = _mesures()
    assert [x["servi_du_cache"] for x in m] == [False, True, True, True]
    assert len({x["empreinte"] for x in m}) == 1 and len({x["cle"] for x in m}) == 1


def test_reanalyser_force_une_nouvelle_extraction(client, ia, attentes):
    fake = ia()
    a = _compte(client)
    b = _compte(client)
    _importer(client, a)
    pb, _ = _importer(client, b)
    assert len(appels_dossier(fake.calls)) == 1
    avant = _lignes_partagees()[0]
    n = len(fake.calls)
    r = client.post("/api/sourcing/reanalyze", headers=b["headers"], data={"project_id": str(pb)})
    assert r.status_code == 200, r.text
    assert len(appels_dossier(fake.calls[n:])) == 1 and len(appels_entreprise(fake.calls[n:])) == 1
    apres = _lignes_partagees()
    assert len(apres) == 1 and apres[0]["cle"] == avant["cle"] and apres[0]["utilise_le"] >= avant["utilise_le"]
    assert _mesures()[-1]["servi_du_cache"] is False


def test_rectificatif_contenu_different_autre_cle(client, ia, attentes):
    fake = ia()
    a, b = _compte(client), _compte(client)
    _importer(client, a)
    rectif = _zip({"RC.txt": (RC_TETE + "Rectificatif : date limite reportée.\n" + _texte("RC", 3000, 21)).encode()})
    n = len(fake.calls)
    _importer(client, b, rectif)
    assert len(appels_dossier(fake.calls[n:])) == 1                          # nouvelle extraction
    assert len(_lignes_partagees()) == 2 and attentes == []


def test_nom_de_fichier_different_autre_cle_jamais_le_nom_d_un_autre(client, ia, attentes):
    """Le nom d'un fichier envoyé seul fait partie de ce que l'IA reçoit : un autre nom donne une autre
    clé (le nom choisi par une entreprise n'est jamais resservi à une autre)."""
    fake = ia()
    a, b = _compte(client), _compte(client)
    rc = (RC_TETE + _texte("RC", 3000, 21)).encode()
    pa = _projet(client, a["headers"])
    r = client.post("/api/sourcing/analyze-upload", headers=a["headers"], data={"project_id": str(pa)},
                    files={"file": ("RC Zorglub Toitures.txt", rc, "text/plain")})
    assert r.status_code == 200, r.text
    n = len(fake.calls)
    pb = _projet(client, b["headers"])
    r = client.post("/api/sourcing/analyze-upload", headers=b["headers"], data={"project_id": str(pb)},
                    files={"file": ("RC.txt", rc, "text/plain")})
    assert r.status_code == 200, r.text
    assert len(appels_dossier(fake.calls[n:])) == 1 and "Zorglub" not in r.text
    m = _mesures()
    assert m[0]["empreinte"] == m[1]["empreinte"] and m[0]["cle"] != m[1]["cle"]   # même contenu, autre clé


def test_cle_change_avec_le_modele_les_consignes_la_lecture_et_la_langue(monkeypatch):
    from app.services import analyse_dossier as ad, analyse_partagee as ap, analysis as an, dce_lecture as lec
    monkeypatch.setattr(llm, "_use_mistral", lambda: True)
    lecture = lec.lire_dossier("DCE.zip", _petit_dossier())
    texte, _m = lec.texte_integral(lecture)
    note = lec.note_pour_ia(lecture)

    def cle(lang="français"):
        return ap.cle_dossier(lecture, texte, note, lang, ad.plan(lecture, None, None, lang))
    base = cle()
    assert cle() == base                                                      # stable
    assert cle("English") != base                                             # autre langue
    monkeypatch.setenv("LLM_TACHE_ANALYSE", "anthropic:claude-sonnet-4-6")  # autre modèle
    assert cle() != base
    monkeypatch.delenv("LLM_TACHE_ANALYSE")
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)                  # fournisseur retiré : autre modèle
    assert cle() != base
    monkeypatch.setattr(llm, "_use_mistral", lambda: True)
    monkeypatch.setattr(an, "VERSION_CONSIGNES", "999")                      # autres consignes
    assert cle() != base
    monkeypatch.setattr(an, "VERSION_CONSIGNES", "1")
    monkeypatch.setattr(an, "SYSTEM_EXTRACTION", an.SYSTEM_EXTRACTION + " ")  # texte des consignes changé
    assert cle() != base
    monkeypatch.undo()
    monkeypatch.setattr(llm, "_use_mistral", lambda: True)
    monkeypatch.setattr(lec, "VERSION", 2)                                   # lecture intégrale changée
    assert cle() != base
    monkeypatch.setattr(lec, "VERSION", 1)
    monkeypatch.setattr(ad, "VERSION_LECTURE", "3")                          # lecture des pièces changée
    assert cle() != base
    monkeypatch.setattr(ad, "VERSION_LECTURE", "2")
    assert cle() == base


def test_deux_temps_servi_sans_aucune_lecture_compteurs_recalcules(ia, attentes, monkeypatch):
    """Dossier lu en deux temps : la seconde organisation ne fait AUCUN appel de lecture ni de synthèse ;
    même couverture, mêmes compteurs (recalculés pour son marché), progression rejouée."""
    from app.services import analyse_dossier as ad, analyse_partagee as ap
    from tests.test_lecture_integrale_relecture import _lecture_deux_temps
    monkeypatch.setattr(ad, "BUDGET_TOKENS", 12_000)
    fake = ia()
    lecture = _lecture_deux_temps()
    with llm.tenant_scope(990101):
        a = ad.analyser(copy.deepcopy(lecture), {"name": "A"}, {}, lang_name="français",
                        partage=ap.partage(990101))
    lus = [k for k in fake.calls if PIECES in llm._flatten_content(k.get("system"))]
    assert a["mode_lecture"] == "deux_temps" and lus and len(_lignes_partagees()) == 1
    n = len(fake.calls)
    prog = []
    with llm.tenant_scope(990102):
        b = ad.analyser(copy.deepcopy(lecture), {"name": "B"}, {}, lang_name="français", progress=prog.append,
                        partage=ap.partage(990102))
    neufs = fake.calls[n:]
    assert [k for k in neufs if PIECES in llm._flatten_content(k.get("system"))] == []
    assert appels_dossier(neufs) == [] and len(appels_entreprise(neufs)) == 1
    assert b["couverture"] == a["couverture"] and b["lecture"]["pieces"] == a["lecture"]["pieces"]
    assert b["details"]["grille_notation"] == a["details"]["grille_notation"]
    assert b["couverture"]["analyse"]["appels_ia"] == a["couverture"]["analyse"]["appels_ia"]
    assert len(attentes) == 1 and len(attentes[0][1]) == a["couverture"]["analyse"]["appels_ia"]
    assert prog and prog[-1] == {"etape": "synthese"}


def test_lecture_incomplete_jamais_gardee(ia, attentes, monkeypatch):
    from app.services import analyse_dossier as ad, analyse_partagee as ap
    from tests.test_lecture_integrale_relecture import _lecture_deux_temps, _lecteur
    monkeypatch.setattr(ad, "BUDGET_TOKENS", 12_000)
    monkeypatch.setattr(ad, "PAUSE_RELANCE_S", 0.0)
    lecteur = _lecteur(panne_toujours=("DEBUT-PIECE-CCTP3",))

    def ans(kw):
        system = llm._flatten_content(kw.get("system"))
        return lecteur(kw) if PIECES in system else _repondre(kw)
    ia(ans)
    with llm.tenant_scope(990201):
        a = ad.analyser(_lecture_deux_temps(), {"name": "A"}, {}, lang_name="français", partage=ap.partage(990201))
    assert a["couverture"]["complet"] is False and _lignes_partagees() == []   # partie en panne : rien de gardé


def test_reponse_illisible_jamais_gardee(client, ia, attentes):
    def ans(kw):
        system = llm._flatten_content(kw.get("system"))
        return ("pas du json", "end_turn") if ENTREPRISE not in system else _repondre(kw)
    ia(ans)
    a = _compte(client)
    pid, r = _importer(client, a)
    assert r.json()["decision"] is not None and _lignes_partagees() == []


def test_bascule_de_secours_jamais_gardee(ia, monkeypatch):
    """Une extraction produite par le SECOURS (panne du modèle prévu) n'est jamais resservie : la clé
    dit quel modèle répond."""
    from app.services import analyse_partagee as ap, analysis as an
    ia()
    vrai = an._appel_analyse

    def avec_bascule(consigne, user_prompt, max_tokens):
        if consigne == an.SYSTEM_EXTRACTION:
            ap.noter_reponse(type("R", (), {"bascule": "panne"})())
        return vrai(consigne, user_prompt, max_tokens)
    monkeypatch.setattr(an, "_appel_analyse", avec_bascule)
    r = ap.analyser_texte(_texte_dce(), {"name": "A"}, {}, lang_name="français", p=ap.partage(990301))
    assert r["details"]["intitule_marche"] and _lignes_partagees() == []
    # « Fournisseur non configuré » est déjà dans la clé : l'extraction est gardée.
    monkeypatch.setattr(an, "_appel_analyse", vrai)
    ap.analyser_texte(_texte_dce(), {"name": "A"}, {}, lang_name="français", p=ap.partage(990301))
    assert len(_lignes_partagees()) == 1


def test_avis_partage_par_la_route_analyze(client, ia, attentes, monkeypatch):
    from app.sourcing.sources.boamp import BoampSource
    monkeypatch.setattr(BoampSource, "fetch_dce", lambda self, t: "")
    fake = ia()
    tender = {"objet": "Réfection de la couverture du groupe scolaire Jules Ferry", "acheteur": "Commune de Plomodiern",
              "departements": ["29"], "cpv": ["45261000"], "procedure": "MAPA", "date_limite": "2099-12-31",
              "provenance": {"source": "BOAMP", "source_url": "https://www.boamp.fr/avis/detail/26-1",
                             "official_ref": "26-1"}}
    a, b = _compte(client, profil=PROFIL_A), _compte(client, profil={"name": "Bretagne Couverture"})
    r = client.post("/api/sourcing/analyze", headers=a["headers"], json={"tender": tender})
    assert r.status_code == 200, r.text
    n = len(fake.calls)
    rb = client.post("/api/sourcing/analyze", headers=b["headers"], json={"tender": tender})
    assert rb.status_code == 200, rb.text
    assert appels_dossier(fake.calls[n:]) == [] and len(appels_entreprise(fake.calls[n:])) == 1
    assert r.json()["score"] is None and rb.json()["score"] is None          # avis seul : aucune compatibilité
    ent = llm._flatten_content(appels_entreprise(fake.calls[n:])[0]["messages"][0]["content"])
    assert "ANNONCE SEULE" in ent
    assert [x["nature"] for x in _mesures()] == ["avis", "avis"]


def test_analyse_partagee_coupee_analyse_d_origine_a_l_identique(client, ia, monkeypatch):
    """ANALYSE_PARTAGEE=0 : un seul appel, profil compris (analyse d'origine) ; rien n'est gardé ; la
    mesure des doublons continue."""
    monkeypatch.setenv("ANALYSE_PARTAGEE", "0")
    fake = ia(lambda kw: (json.dumps(_original(), ensure_ascii=False), "end_turn"))
    a = _compte(client, profil=PROFIL_A)
    _importer(client, a)
    assert len(fake.calls) == 1 and "Zorglub" in llm._flatten_content(fake.calls[0]["messages"][0]["content"])
    from app.services import analysis as an
    assert llm._flatten_content(fake.calls[0]["system"]) == an.SYSTEM_PROMPT
    assert _lignes_partagees() == [] and len(_mesures()) == 1 and _mesures()[0]["cle"] is None


# ═══ 3. Confidentialité ═══════════════════════════════════════════════════════════════════════════

def test_extraction_partagee_sans_aucune_donnee_d_entreprise(client, ia, attentes):
    """L'extraction ne reçoit AUCUNE donnée d'entreprise (prompt vérifié) et l'entrée partagée n'en
    contient aucune (toutes les colonnes) ; la table n'a aucune colonne d'organisation."""
    from app.models import AnalysePartagee
    fake = ia()
    a = _compte(client, profil=PROFIL_A, criteres=CRITERES_A)
    _importer(client, a)
    ext = appels_dossier(fake.calls)[0]
    envoye = llm._flatten_content(ext.get("system")) + "\n" + llm._flatten_content(ext["messages"][0]["content"])
    for s in SECRETS_A + [a["email"]]:
        assert s not in envoye, s
    assert "PROFIL DE L'ENTREPRISE" not in envoye and "CRITERES GO/NO-GO" not in envoye
    # La partie propre à l'entreprise reçoit bien le profil… sans les noms des salariés (masqués).
    ent = llm._flatten_content(appels_entreprise(fake.calls)[0]["messages"][0]["content"])
    assert "Zorglub Toitures SARL" in ent and "3.7" in ent and "Yann Tanguy" not in ent
    lignes = _lignes_partagees()
    assert len(lignes) == 1
    stocke = json.dumps(lignes[0], default=str, ensure_ascii=False)
    for s in SECRETS_A + [a["email"], str(a["id"]) + ","]:
        assert s not in stocke, s
    cols = {c.name for c in AnalysePartagee.__table__.columns}
    assert not {c for c in cols if "owner" in c or "user" in c or "org" in c or "project" in c}


def test_rien_ne_trahit_le_partage_dans_l_api_ni_a_l_ecran(client, ia, attentes):
    ia()
    a = _compte(client, profil=PROFIL_A)
    b = _compte(client, profil={"name": "Bretagne Couverture"})
    pa, ra = _importer(client, a)
    pb, rb = _importer(client, b)
    for r in (rb.json(), client.get(f"/api/projects/{pb}", headers=b["headers"]).json(),
              client.get(f"/api/sourcing/lecture/{pb}", headers=b["headers"]).json()):
        txt = json.dumps(r, ensure_ascii=False).lower()
        for mot in ("partag", "cache", "servi", "mutualis", "autre entreprise", "autre organisation", "deja analyse"):
            assert mot not in txt, mot
    assert _cles_analyse(ra.json()) == _cles_analyse(rb.json())
    la = client.get(f"/api/sourcing/lecture/{pa}", headers=a["headers"]).json()
    lb = client.get(f"/api/sourcing/lecture/{pb}", headers=b["headers"]).json()
    assert set(la) == set(lb) and la["couverture"] == lb["couverture"]
    # L'écran ne contient aucun texte sur le partage.
    import pathlib
    html = (pathlib.Path("app/static/app.html").read_text() + pathlib.Path("app/static/app.js").read_text()).lower()
    assert "analyse partagée" not in html and "analyse-partagee" not in html


def test_choix_de_chaque_client_restent_a_lui(client, ia, attentes):
    ia()
    a, b = _compte(client), _compte(client)
    pa, ra = _importer(client, a)
    g = ra.json()["details"]["grille_notation"]
    cid = g["criteres"][0]["id"]
    r = client.post("/api/sourcing/grille/choix", headers=a["headers"],
                    json={"project_id": pa, "critere_id": cid, "choix": "ecarte"})
    assert r.status_code == 200, r.text
    assert r.json()["grille_notation"]["criteres"][0]["choix_utilisateur"]["choix"] == "ecarte"
    pb, rb = _importer(client, b)
    gb = rb.json()["details"]["grille_notation"]
    assert all(not c.get("choix_utilisateur") for c in gb["criteres"])          # le choix de A n'est pas chez B
    assert "choix_utilisateur" not in json.dumps(_lignes_partagees(), default=str, ensure_ascii=False)
    # A ré-analyse : son choix lui reste (reprise des choix du marché).
    r = client.post("/api/sourcing/reanalyze", headers=a["headers"], data={"project_id": str(pa)})
    assert r.status_code == 200, r.text
    ga = r.json()["details"]["grille_notation"]
    assert next(c for c in ga["criteres"] if c["id"] == cid)["choix_utilisateur"]["choix"] == "ecarte"


def test_mesure_jamais_montree_a_un_client_et_comptee_pour_l_administrateur(client, ia, attentes):
    from app.models import User
    ia()
    a, b = _compte(client), _compte(client)
    _importer(client, a)
    _importer(client, b)
    _importer(client, b)
    assert client.get("/api/admin/analyse-partagee", headers=a["headers"]).status_code == 403
    db = _db()
    try:
        u = db.get(User, a["id"])
        u.is_admin = True
        db.commit()
    finally:
        db.close()
    m = client.get("/api/admin/analyse-partagee", headers=a["headers"]).json()["par_nature"]["dossier"]
    assert m["analyses"] == 3 and m["contenus_distincts"] == 1 and m["contenus_vus_par_plusieurs_organisations"] == 1
    assert m["doublons_entre_organisations"] == 1 and m["doublons_meme_organisation"] == 1
    assert m["doublons_entre_organisations_cle_exacte"] == 1 and m["servies_depuis_le_partage"] == 2
    assert m["economie_eur"] > 0
    txt = client.get("/api/admin/analyse-partagee", headers=a["headers"]).text
    assert b["email"] not in txt and "owner" not in txt and "org_id" not in txt
    # Agrégats seulement : aucune empreinte, aucune clé, aucune organisation.
    assert not re.search(r"[0-9a-f]{64}", txt)
    out = client.get("/metrics").text
    assert 'adjugo_analyse_partagee_doublons_entre_organisations{nature="dossier",mesure="contenu"} 1' in out
    assert 'adjugo_analyse_partagee_servies{nature="dossier"} 2' in out
    assert not re.search(r"adjugo_analyse_partagee\w*\{[^}]*(owner|org|cle|empreinte)", out)


def test_empreinte_normalisee_contenu_seul():
    from app.services import analyse_partagee as ap
    l1 = {"pieces": [{"nom": "RC.pdf", "texte": "Règlement  de la\nconsultation"}, {"nom": "CCTP.pdf", "texte": "Lot 1"}]}
    l2 = {"pieces": [{"nom": "cctp.PDF", "texte": "lot 1"}, {"nom": "reglement.pdf", "texte": "RÈGLEMENT de la consultation"}]}
    l3 = {"pieces": [{"nom": "RC.pdf", "texte": "Règlement de la consultation modifié"}, {"nom": "CCTP.pdf", "texte": "Lot 1"}]}
    assert ap.empreinte_dossier(l1) == ap.empreinte_dossier(l2) != ap.empreinte_dossier(l3)
    assert "consultation" not in ap.empreinte_dossier(l1) and len(ap.empreinte_dossier(l1)) == 64


# ═══ 4. Coût ══════════════════════════════════════════════════════════════════════════════════════

def _couts():
    from app.models import UsageIA
    from app.services import budget_ia
    assert budget_ia.vider()
    db = _db()
    try:
        return {(x.compte, x.essai): (x.cout_eur, x.appels) for x in db.query(UsageIA).all()}
    finally:
        db.close()


def test_cout_extraction_mutualisee_forfait_payant_et_rien_pour_une_extraction_resservie(client, ia, attentes):
    ia()
    a = _compte(client, plan="pro")
    b = _compte(client, plan="pro")
    avant = _couts()
    _importer(client, a)
    apres_a = _couts()
    plat = apres_a.get(("plateforme", False), (0, 0))[0] - avant.get(("plateforme", False), (0, 0))[0]
    ca = apres_a.get((f"u{a['id']}", False), (0, 0))
    assert ca[1] == 1 and 0 < ca[0] and plat > 20 * ca[0]      # extraction → plateforme ; A : l'appel court
    _importer(client, b)
    apres_b = _couts()
    assert apres_b.get(("plateforme", False)) == apres_a.get(("plateforme", False))   # resservie : rien
    cb = apres_b.get((f"u{b['id']}", False), (0, 0))
    assert cb[1] == 1 and 0 < cb[0] and plat > 20 * cb[0]


def test_essai_extraction_neuve_comptee_a_l_essai_servie_jamais(client, ia, attentes):
    from app.models import User
    from app.services import budget_ia
    ia()
    a, b = _compte(client), _compte(client)              # comptes neufs : essai gratuit en cours
    db = _db()
    try:
        assert budget_ia.essai_actif(db.get(User, a["id"])) and budget_ia.essai_actif(db.get(User, b["id"]))
    finally:
        db.close()
    plat0 = _couts().get(("plateforme", False), (0, 0))[0]
    _importer(client, a)
    c = _couts()
    cout_a = c[(f"u{a['id']}", True)]
    assert cout_a[1] == 2                                     # extraction neuve : comptée à l'essai de A
    assert c.get(("plateforme", False), (0, 0))[0] == plat0
    _importer(client, b)
    c2 = _couts()
    cout_b = c2[(f"u{b['id']}", True)]
    assert cout_b[1] == 1 and cout_a[0] > 20 * cout_b[0]      # resservie : seul l'appel court
    db = _db()
    try:
        assert budget_ia.cout_essai_eur(db, db.get(User, b["id"])) == pytest.approx(cout_b[0])
    finally:
        db.close()


def test_estimation_de_l_essai_identique_resservie_ou_non(client, ia):
    """L'estimation qui protège l'essai ne dépend jamais du partage (prudente : extraction neuve, plus
    la partie propre à l'entreprise)."""
    from app.services import analyse_dossier as ad, budget_ia, dce_lecture as lec
    ia()
    lecture = lec.lire_dossier("DCE.zip", _petit_dossier())
    e1 = budget_ia.estimer_import(lecture, ad.plan(lecture))
    a = _compte(client)
    _importer(client, a)
    assert _lignes_partagees()
    assert budget_ia.estimer_import(lecture, ad.plan(lecture)) == e1
    assert e1 > budget_ia.estimer_appel("analyse", 40_000, 2000)


# ═══ 5. Purge, effacement, cache de prompt ════════════════════════════════════════════════════════

def test_purge_et_effacement_du_compte(client, ia, attentes):
    from datetime import datetime, timedelta
    from app.models import AnalyseEmpreinte, AnalysePartagee
    from app.services import analyse_partagee as ap
    ia()
    a, b = _compte(client), _compte(client)
    _importer(client, a)
    _importer(client, b)
    # Effacement du compte de A (propriétaire seul) : ses lignes de mesure partent ; l'extraction partagée
    # (document public, à personne) reste.
    r = client.post("/api/rgpd/delete-account", headers=a["headers"],
                    json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    m = _mesures()
    assert {x["owner_id"] for x in m} == {b["id"]} and len(_lignes_partagees()) == 1
    # Purge : extraction plus resservie depuis ANALYSE_PARTAGEE_JOURS jours, mesures trop anciennes.
    db = _db()
    try:
        vieux = datetime.utcnow() - timedelta(days=ap.jours_cache() + 1)
        db.query(AnalysePartagee).update({AnalysePartagee.utilise_le: vieux}, synchronize_session=False)
        db.query(AnalyseEmpreinte).update({AnalyseEmpreinte.created_at: datetime.utcnow()
                                           - timedelta(days=ap.jours_mesure() + 1)}, synchronize_session=False)
        db.commit()
        out = ap.purger(db)
    finally:
        db.close()
    assert out == {"analyses_partagees_purgees": 1, "mesures_purgees": 1}
    assert _lignes_partagees() == [] and _mesures() == []


def test_cron_de_purge_inclut_l_analyse_partagee(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "CRON_SECRET", "secret-de-test")
    r = client.post("/api/admin/run-trash-purge", headers={"X-Cron-Secret": "secret-de-test"})
    assert r.status_code == 200, r.text
    assert "analyses_partagees_purgees" in r.json() and "mesures_purgees" in r.json()


def test_cache_de_prompt_sur_chaque_long_texte_relu(ia, monkeypatch):
    """Consignes marquées pour le cache de prompt : lecture des pièces (relue par chaque partie),
    extraction et partie propre à l'entreprise. Le texte lu est inchangé."""
    from app.services import analyse_dossier as ad
    from tests.test_lecture_integrale_relecture import _lecture_deux_temps
    monkeypatch.setattr(ad, "BUDGET_TOKENS", 12_000)
    fake = ia()
    with llm.tenant_scope(990401):
        ad.analyser(_lecture_deux_temps(), {"name": "A"}, {}, lang_name="français")
    lus = [k for k in fake.calls if PIECES in llm._flatten_content(k.get("system"))]
    assert len(lus) >= 2
    for k in fake.calls:
        assert k["system"][0].get("cache_control") == {"type": "ephemeral"}, llm._flatten_content(k["system"])[:60]
    assert llm._flatten_content(lus[0]["system"]) == ad.PIECE_SYSTEM
