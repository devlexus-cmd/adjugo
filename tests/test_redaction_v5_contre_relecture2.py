"""
Rédaction, vague 5 — seconde contre-relecture (après d342cd5). Chaque test reproduit une remarque retenue et
échouait sur d342cd5 (sauf mention) : réponse d'un partenaire retirée PENDANT une rédaction par l'IA (R11, chef de
file et partenaire), titre « … des candidatures et des offres » (R3), « facultatif » qui effaçait une liste ou une
phrase entière (R3), élément de liste du CCTP relu avec sa phrase d'annonce (R3), date des questions écrite après le
délai (« soit le ») prise pour la date de remise (R2), « entreprise » / « chantier » hors des mots principaux (R5),
parties tirées du groupement placées au milieu d'un groupe de sous-critères (R25). Contrat : docs/REDACTION_V5.md
(§ R2).

Aucun appel réseau ; l'IA est simulée.
"""
import json

import pytest

from app.services import dce_pieces as dp
from app.services import entretien_chantier as ec
from app.services import faits_sources as fs
from app.services import grille_exigences as ge
from app.services import grille_notation as gn
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v5_entretien import _avec_partenaires, _entretien, _partie, _q, _rediger, _version_db
from tests.test_redaction_v5_contre_relecture import SECRET_PART, _toutes_les_versions

CRIT = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "1. Valeur technique : 60 %"},
        {"critere": "Prix", "ponderation": "40 %", "extrait": "2. Prix : 40 %"}]
NOTATION = ["Article 4 - Critères de jugement des offres", "1. Valeur technique : 60 %", "2. Prix : 40 %"]


def _rc(*lignes):
    return dp.header("01_Reglement_de_la_consultation.txt") + "\n" + "\n".join(
        ["REGLEMENT DE LA CONSULTATION", *lignes]) + "\n"


def _exigences(rc, **details):
    g = gn.build_grille(dict(details, criteres_attribution=CRIT), rc)
    return [(x["texte"], x["origine"]) for x in g["exigences"]["liste"]], g


# ═══ 1. R11 : une réponse retirée pendant la rédaction par l'IA ne reste dans aucun fait ═════════════

def _prep(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import P
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid, st, a, _b = _avec_partenaires(client, h)
    q = _q(_entretien(client, h, pid), "acces_toiture")
    pa = P(client, a["token"])
    r = pa.put(f"/entretien/{q['id']}", {"statut": "repondue", "avertissement_lu": True,
                                         "reponse": f"Accès par {SECRET_PART} et monte-matériaux de 12 mètres."})
    assert r.status_code == 200, r.text
    return h, pid, st, a, q, pa


def _pendant_l_ia(fake_llm, action, texte):
    etat = {"n": 0}

    def ans(kw):
        if etat["n"] == 0:
            etat["n"] = 1
            action()
        return texte, "end_turn"
    fake_llm(ans)
    return etat


def _fait_12(sid):
    return next(x for x in _version_db(sid)["faits"] if x["fait"] == "12 mètres")


def _retirer_reponse(pa, q):
    cur = next(x for x in pa.get().json()["entretien"]["questions"] if x["id"] == q["id"])
    rr = pa.put(f"/entretien/{q['id']}", {"statut": "a_repondre", "lock_version": cur["lock_version"]})
    assert rr.status_code == 200, rr.text


@pytest.mark.parametrize("comment", ["reponse_retiree", "partenaire_retire", "question_reprise"])
def test_reponse_d_un_partenaire_qui_disparait_pendant_la_redaction_du_chef(client, auth, fake_llm, comment):
    h, pid, st, a, q, pa = _prep(client, auth, fake_llm)
    sec = _partie(st, "méthodologie")

    def action():
        if comment == "reponse_retiree":
            _retirer_reponse(pa, q)
        elif comment == "partenaire_retire":
            assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=h).status_code == 200
        else:
            r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h,
                           json={"invite_id": None, "confirmer": True})
            assert r.status_code == 200, r.text
    etat = _pendant_l_ia(fake_llm, action, f"Breizh Couverture accède à la toiture par un monte-matériaux de "
                                           f"12 mètres [{q['ref']}].")
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    assert etat["n"] == 1
    f = _fait_12(sec["id"])
    assert f["statut"] == "a_relire" and not f.get("source"), f
    assert SECRET_PART not in _toutes_les_versions(sec["id"])
    st2 = client.get(f"/api/atelier/{pid}", headers=h).json()
    assert "faits_a_relire" in [x["code"] for x in st2["blocage"]["raisons"]]


def test_reponse_du_partenaire_inchangee_pendant_la_redaction_reste_citee(client, auth, fake_llm):
    """Garde-fou (vert aussi sur d342cd5) : une autre question répondue pendant la rédaction ne touche pas le fait."""
    h, pid, st, a, q, pa = _prep(client, auth, fake_llm)
    sec = _partie(st, "méthodologie")
    autre = next(x for x in _entretien(client, h, pid, preparer=False)["questions"]
                 if x["adresse"]["type"] == "organisation" and x["statut"] == "a_repondre")

    def action():
        r = client.put(f"/api/atelier/{pid}/entretien/{autre['id']}", headers=h, json={"statut": "sautee"})
        assert r.status_code == 200, r.text
    _pendant_l_ia(fake_llm, action, f"Breizh Couverture accède à la toiture par un monte-matériaux de 12 mètres "
                                    f"[{q['ref']}].")
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    f = _fait_12(sec["id"])
    assert f["statut"] == "avec_source" and f["source"]["type"] == fs.T_PARTENAIRE


def test_raccourcir_pendant_que_le_partenaire_retire_sa_reponse(client, auth, fake_llm):
    from tests.test_redaction_v5_entretien import _attendre
    h, pid, st, a, q, pa = _prep(client, auth, fake_llm)
    sec = _partie(st, "méthodologie")
    phrase = f"Breizh Couverture accède à la toiture par un monte-matériaux de 12 mètres [{q['ref']}]."
    fake_llm(lambda kw: (" ".join([phrase] * 6), "end_turn"))
    assert _rediger(client, h, pid, sec["id"])["status"] == "done"
    assert _fait_12(sec["id"])["statut"] == "avec_source"
    _pendant_l_ia(fake_llm, lambda: _retirer_reponse(pa, q), phrase)
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/raccourcir", headers=h, json={"cible_mots": 30})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    f = _fait_12(sec["id"])
    assert f["statut"] == "a_relire" and not f.get("source"), f
    assert SECRET_PART not in _toutes_les_versions(sec["id"])


def test_aide_du_partenaire_pendant_que_le_chef_reprend_la_question(client, auth, fake_llm):
    """Sa réponse est effacée par le chef de file (question reprise) pendant SON aide de l'IA : son brouillon ne la
    garde pas (ni passage ni source)."""
    from app.models import DossierPartBrouillon
    from tests.test_redaction_v4_groupement import _aide
    h, pid, st, a, q, pa = _prep(client, auth, fake_llm)
    met = _partie(st, "méthodologie")["id"]
    r = client.put(f"/api/atelier/{pid}/repartition/{met}", headers=h, json={"redacteur": "partenaire",
                                                                            "invite_id": a["id"]})
    assert r.status_code == 200, r.text

    def action():
        r2 = client.put(f"/api/atelier/{pid}/entretien/{q['id']}/adresse", headers=h,
                        json={"invite_id": None, "confirmer": True})
        assert r2.status_code == 200, r2.text
    etat = _pendant_l_ia(fake_llm, action, f"Nous montons par un monte-matériaux de 12 mètres [{q['ref']}].")
    res, _jid = _aide(pa, met)
    assert res["status"] == "done", res
    assert etat["n"] == 1
    db = _db()
    try:
        rows = db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == a["id"]).all()
        assert rows
        tout = json.dumps([[b.faits, b.sources] for b in rows], ensure_ascii=False)
        f = next(x for x in rows[-1].faits if x["fait"] == "12 mètres")
    finally:
        db.close()
    assert SECRET_PART not in tout
    assert f["statut"] == "a_relire" and not f.get("source"), f


def test_sans_reponses_changees_regles():
    a1 = fs.Fiche("R1", fs.T_PARTENAIRE, fs.LIB_PARTENAIRE, "Breizh — accès : 12 mètres.", proprietaire="Breizh")
    a2 = fs.Fiche("R2", fs.T_DECLARE, fs.LIB_DECLARE, "Entretien chantier, déchets : tri en 5 flux.")
    m2 = fs.Fiche("R2", fs.T_DECLARE, fs.LIB_DECLARE, "Entretien chantier, déchets : tri en 3 flux.")

    def fait(ref, type_, statut="avec_source"):
        return {"id": ref, "fait": "x", "statut": statut, "message": "m", "a_propos": "entreprise",
                "source": {"ref": ref, "type": type_, "extrait": "passage " + ref}}
    faits = [fait("R1", fs.T_PARTENAIRE), fait("R2", fs.T_DECLARE), fait("R9", fs.T_DECLARE), fait("F1", "declare"),
             fait("R7", fs.T_PARTENAIRE)]
    srcs, out = ec.sans_reponses_changees([{"ref": "S1"}], faits, [a1, a2], [m2])
    par = {x["id"]: x for x in out}
    assert par["R1"]["statut"] == "a_relire" and par["R1"]["source"] is None      # partenaire parti
    assert par["R2"]["statut"] == "a_relire" and par["R2"]["source"] is None      # réponse changée
    assert par["R9"]["statut"] == "avec_source"         # réponse du chef jamais remise ici : intouchée
    assert par["F1"]["statut"] == "avec_source"         # pas une réponse de l'entretien
    assert par["R7"]["statut"] == "a_relire"            # réponse d'un partenaire absente de la fiche actuelle
    assert srcs == [{"ref": "S1"}]
    _s, out2 = ec.sans_reponses_changees([], faits[:2], [a1, a2], [a1, a2])
    assert [x["statut"] for x in out2] == ["avec_source", "avec_source"]


# ═══ 2. R3 : « Présentation des candidatures et des offres » n'est pas un article sur la candidature ══════

PH1 = "Le candidat présentera la méthodologie de dépose de la couverture."
PH2 = "Le candidat décrira les mesures prises pour la gestion des déchets."


def test_article_candidatures_et_offres_sous_titre_de_l_offre():
    rc = _rc(*NOTATION, "Article 5 - Présentation des candidatures et des offres",
             "5.1 Pièces de la candidature", "Le candidat produira le formulaire DC1.",
             "Le candidat présentera la liste de ses moyens financiers.",
             "5.2 Contenu de l'offre", "Le mémoire technique comprendra les éléments ci-dessous.", PH1, PH2)
    rep, _g = _exigences(rc)
    assert rep == [("la méthodologie de dépose de la couverture", "reperage"),
                   ("les mesures prises pour la gestion des déchets", "reperage")]
    # Proposées par l'IA (mot pour mot) : gardées aussi ; « 5.1 Pièces de la candidature » reste écarté.
    rep2, _g = _exigences(rc, exigences_memoire=[PH1, PH2, "Le candidat présentera la liste de ses moyens financiers."])
    assert [t for t, _o in rep2] == ["la méthodologie de dépose de la couverture",
                                     "les mesures prises pour la gestion des déchets"]


def test_article_candidatures_et_offres_sans_sous_titre_et_vraie_candidature():
    rc = _rc(*NOTATION, "Article 5 - Présentation des candidatures et des offres",
             "Le mémoire technique présentera la méthodologie de dépose de la couverture.",
             "Le mémoire technique décrira les mesures de sécurité en site occupé.",
             "Article 6 - Conditions de participation",
             "Le candidat devra présenter la liste de ses moyens financiers.",
             "6.1 Délai de validité", "Le candidat devra présenter ses références de chantiers.")
    rep, _g = _exigences(rc)
    assert [t for t, _o in rep] == ["la méthodologie de dépose de la couverture",
                                    "les mesures de sécurité en site occupé"]
    # La même règle pour l'entretien chantier (phrase sous un article de candidature : prise à défaut).
    f = dp.fold(rc)
    assert ec._sous_article_candidature(f, f.index("moyens financiers"))
    assert ec._sous_article_candidature(f, f.index("references de chantiers"))      # sous-titre neutre
    assert not ec._sous_article_candidature(f, f.index("mesures de securite"))


def test_article_de_candidature_sur_sa_ligne_seulement():
    """Garde-fou (vert sur d342cd5) : le titre est lu sur sa ligne, pas dans la phrase qui le suit."""
    rc = _rc(*NOTATION, "Article 2 - Présentation des candidatures",
             "Le candidat devra présenter son offre en un seul exemplaire et la liste de ses moyens financiers.")
    assert _exigences(rc)[0] == []


# ═══ 3. R3 : « facultatif » n'efface que ce qui est facultatif ══════════════════════════════════════════

def test_annonce_de_liste_avec_annexes_facultatives():
    rc = _rc(*NOTATION, "Article 6 - Contenu du mémoire technique",
             "Le mémoire technique (annexes facultatives) comprendra :",
             "- la méthodologie de dépose de la couverture ;", "- la gestion des déchets ;", "- le planning d'exécution.")
    assert [t for t, _o in _exigences(rc)[0]] == ["la méthodologie de dépose de la couverture", "la gestion des déchets",
                                                  "le planning d'exécution"]


@pytest.mark.parametrize("phrase,attendu", [
    ("Le candidat présentera la méthodologie d'exécution et, de manière facultative, des photographies de chantiers "
     "similaires.", "la méthodologie d'exécution"),
    ("Le mémoire technique présentera la méthodologie de dépose, les moyens humains affectés et, de façon "
     "facultative, un reportage photographique.", "la méthodologie de dépose, les moyens humains affectés"),
])
def test_element_facultatif_coordonne_seul_retire_du_libelle(phrase, attendu):
    rc = _rc(*NOTATION, "Article 6 - Contenu du mémoire technique", phrase)
    rep, g = _exigences(rc)
    assert rep == [(attendu, "reperage")]
    assert g["exigences"]["liste"][0]["phrase"] == phrase            # la phrase citée reste entière
    # Proposée par l'IA : gardée, même libellé.
    rc2 = _rc(*NOTATION, "Article 6 - Pièces", phrase)
    assert [t for t, _o in _exigences(rc2, exigences_memoire=[phrase])[0]] == [attendu]
    t = ge.traitement(g, [{"id": 1, "titre": "M", "texte": "Notre méthodologie de dépose et d'exécution, nos moyens "
                                                           "humains affectés."}])
    assert t["liste"][0]["statut"] == ge.TRAITEE


@pytest.mark.parametrize("phrase", [
    "Le candidat présentera, à titre facultatif, ses certificats de formation.",
    "À titre facultatif, le candidat présentera ses certificats de formation.",
    "Le candidat présentera ses certificats de formation, à titre facultatif.",
])
def test_demande_facultative_toujours_ecartee(phrase):
    rc = _rc(*NOTATION, "Article 6 - Contenu du mémoire technique", phrase,
             "Le mémoire technique comprendra :", "- la méthodologie de dépose ;",
             "- à titre facultatif, un reportage photographique.")
    assert [t for t, _o in _exigences(rc, exigences_memoire=[phrase])[0]] == ["la méthodologie de dépose"]


# ═══ 4. R3 : un élément de liste du CCTP proposé par l'IA est relu avec sa phrase d'annonce ═════════════

def test_element_de_liste_du_cctp_relu_avec_son_annonce():
    rc = _rc("Article 1 - Objet", "Réfection de la toiture.")
    cctp = (dp.header("03_CCTP.txt") + "\nCAHIER DES CLAUSES TECHNIQUES PARTICULIERES\nArticle 3 - Documents à remettre\n"
            "Le candidat joindra à son mémoire technique :\n- les fiches techniques des matériaux proposés ;\n"
            "- le plan d'installation de chantier.\nArticle 4 - Essais\nLe titulaire n'est pas tenu de fournir :\n"
            "- les procès-verbaux d'essais des matériaux.\n")
    g = gn.build_grille({"criteres_attribution": [], "exigences_memoire": [
        "les fiches techniques des matériaux proposés", "le plan d'installation de chantier",
        "les procès-verbaux d'essais des matériaux"]}, rc + cctp)
    assert [(x["texte"], x["origine"]) for x in g["exigences"]["liste"]] == [
        ("les fiches techniques des matériaux proposés", "ia"), ("le plan d'installation de chantier", "ia")]


# ═══ 5. R2 : la date écrite après le délai et introduite par « soit le » est celle des questions ═════════

@pytest.mark.parametrize("phrase", [
    "Les candidats peuvent poser leurs questions au plus tard 10 jours avant la date limite de remise des offres, "
    "soit le 05/12/2026.",
    "Les questions doivent parvenir au plus tard 10 jours avant la date limite de réception des offres, soit jusqu'au "
    "05/12/2026.",
    "Les candidats peuvent poser leurs questions jusqu'à 10 jours avant la date limite de remise des offres, "
    "c'est-à-dire le 05/12/2026.",
    "Les demandes de renseignements complémentaires doivent parvenir au plus tard 10 jours avant la date limite de "
    "remise des offres, à savoir le 05/12/2026.",
])
@pytest.mark.parametrize("avec_remise", [False, True])
def test_date_des_questions_apres_le_delai_avec_soit_le(phrase, avec_remise):
    extra = ["Article 3 - Date limite", "La date limite de remise des offres est fixée au 15/12/2026 à 12h00."] \
        if avec_remise else []
    g = gn.build_grille({"criteres_attribution": CRIT}, _rc(*extra, *NOTATION, "Article 9 - Questions", phrase))
    dl = g["questions_acheteur"]["date_limite"]
    assert dl["date"] == "2026-12-05" and dl["date_calculee"] is None
    assert dl["message"] == "Date limite pour poser vos questions : 05/12/2026, écrite dans le règlement."
    assert "date_remise" not in [x["code"] for x in g["questions_acheteur"]["liste"]]   # une seule date de remise


def test_date_de_remise_apres_le_delai_toujours_calculee():
    """Garde-fou (vert sur d342cd5) : « fixée au » et « des offres du » donnent la date de remise."""
    for phrase, attendue in (
            ("Les questions sont posées au plus tard 6 jours avant la date limite de remise des offres, fixée au "
             "15/12/2026.", "2026-12-09"),
            ("Les questions des candidats doivent parvenir au plus tard 10 jours avant la date limite de réception "
             "des offres du 15 décembre 2026.", "2026-12-05")):
        g = gn.build_grille({"criteres_attribution": CRIT}, _rc(*NOTATION, "Article 9 - Questions", phrase))
        dl = g["questions_acheteur"]["date_limite"]
        assert dl["date"] is None and dl["date_calculee"] == attendue


# ═══ 6. R5 : « entreprise » et « chantier » restent des mots de l'exigence ═════════════════════════════

def test_presentation_de_l_entreprise_reste_une_exigence():
    rc = _rc(*NOTATION, "Article 8 - Contenu du mémoire technique", "Le candidat présentera son entreprise.",
             "Le mémoire technique comprendra :", "- une présentation de l'entreprise ;",
             "- les moyens humains affectés au chantier ;", "- la gestion des déchets.")
    assert [t for t, _o in _exigences(rc)[0]] == ["son entreprise", "une présentation de l'entreprise",
                                                  "les moyens humains affectés au chantier", "la gestion des déchets"]


def test_un_seul_mot_restant_jamais_traite_par_le_mot_chantier_seul():
    g = {"exigences": {"liste": [
        {"id": "e1", "texte": "l'organisation du chantier", "phrase": "x", "origine": "reperage"},
        {"id": "e2", "texte": "l'installation de chantier", "phrase": "y", "origine": "reperage"},
        {"id": "e3", "texte": "la gestion des déchets du chantier", "phrase": "z", "origine": "reperage"}]}}
    t = ge.traitement(g, [{"id": 1, "titre": "Organisation du groupement", "texte": "L'organisation du groupement "
                           "repose sur un mandataire solidaire et une installation commune."}])
    assert [x["statut"] for x in t["liste"]] == [ge.A_TRAITER, ge.A_TRAITER, ge.A_TRAITER]
    t2 = ge.traitement(g, [{"id": 1, "titre": "Organisation", "texte": "L'organisation du chantier, l'installation "
                            "de chantier ; les déchets sont triés, leur gestion suivie."}])
    assert [x["statut"] for x in t2["liste"]] == [ge.TRAITEE, ge.TRAITEE, ge.TRAITEE]


# ═══ 7. R25 : les parties tirées du groupement passent après tout le groupe de sous-critères ═══════════

def test_parties_du_groupement_apres_le_groupe_de_sous_criteres(client, auth, fake_llm):
    from app.models import Project
    from tests.test_convention_groupement import _invite, _put
    from tests.test_redaction_v2_atelier import _creer, _projet
    fake_llm(lambda kw: ("x", "end_turn"))
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n1. Valeur technique : 60 %\n"
          "1.1 Méthodologie d'intervention : 30 %\n1.2 Organisation du groupement et répartition des tâches : 20 %\n"
          "1.3 Démarche environnementale : 10 %\n2. Prix : 40 %\n")
    db = _db()
    try:
        p = db.get(Project, pid)
        det = {"intitule_marche": "Toiture", "criteres_attribution": CRIT}
        det["grille_notation"] = gn.build_grille(det, rc)
        p.ai_analysis = {"summary": "x", "dce_available": True, "details": det}
        db.commit()
    finally:
        db.close()
    _creer(client, h, pid, base="grille")
    a = _invite(client, h, pid, "Breizh Couverture")
    assert _put(client, a["token"], company_name="Breizh Couverture", lot="Couverture").status_code == 200
    assert client.post(f"/api/atelier/{pid}/repartition", headers=h, json={}).status_code == 200
    st = client.get(f"/api/atelier/{pid}", headers=h).json()
    ordre = [(s["numero_affiche"], s["intitule"]) for s in st["sections"]]
    assert [n for n, _i in ordre][:3] == ["1.1", "1.2", "1.3"], ordre
    assert [i for _n, i in ordre][3:] == ["Organisation du groupement", "Qui fait quoi dans le groupement"], ordre
