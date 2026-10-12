"""
Rédaction, vague 3 — A « Chaque fait a sa source » (étude § 6.5, doctrine § 7), côté serveur.

 • l'IA reçoit les faits autorisés NUMÉROTÉS et TYPÉS ([F3] preuves de « Mes preuves », [P1] profil,
   [E1] équipe masquée, [C1] chiffrage = « votre estimation », [S1] extraits ; le dossier de l'acheteur
   « exigé par l'acheteur ») et cite leur renvoi ; le CV d'une personne n'est JAMAIS remis à l'IA,
   il est inséré tel quel (« [CV F2] ») ;
 • contrôle SANS IA phrase par phrase : de qui parle la phrase, repérage, rapprochement avec un fait
   cité du BON type (le dossier de l'acheteur n'appuie jamais une phrase sur l'entreprise), unités,
   recalcul des pourcentages et des totaux, engagements à confirmer ;
 • CALIBRATION : au moins 50 phrases piégées, ZÉRO présentée comme « trouvé dans vos documents » ;
 • libellés positifs et compteur « Faits avec une source : 7 sur 8 » seulement avec
   ATELIER_LIBELLES_SOURCES=1 (après la mesure des fausses alertes) : sinon l'affichage d'A0 ;
 • renvois retirés à l'export ; « Ajouter une source » (jamais l'IA, jamais le texte modifié) ;
   recontrôle ; une preuve retirée ou expirée rend le fait à relire et bloque l'export ;
 • isolation (404), démo (403), jamais le mot « vérifié » ; outil de mesure des fausses alertes.
Aucun appel réseau : le client IA est simulé. Aucune donnée réelle.
"""
import io
import json
import os
import re
from datetime import date, timedelta

import pytest

from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from app.services import llm
from tests import pieges_sources as ps
from tests.test_redaction_socle0 import _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _ecrire, _etat, _projet


# ═══ 1. Calibration : le jeu de phrases piégées ═════════════════════════════════════════════

def test_le_jeu_compte_au_moins_cinquante_pieges_de_chaque_famille():
    assert len(ps.PIEGES) >= 50
    phrases = [p for p, _m, _s in ps.PIEGES]
    assert len(set(phrases)) == len(phrases)                     # pas de doublon


@pytest.mark.parametrize("phrase,piege,section", ps.PIEGES, ids=[f"piege{i:02d}" for i in range(len(ps.PIEGES))])
def test_aucun_piege_n_est_presente_comme_trouve_dans_vos_documents(phrase, piege, section):
    items = ps.controler(phrase, section)
    hits = ps.fait_de(items, piege)
    assert hits, f"« {piege} » n'est pas relevé dans : {phrase}"
    for x in hits:
        src = x.get("source") or {}
        assert src.get("type") not in (fs.T_DOCUMENTS, fs.T_JUSTIFICATIF), (phrase, x)
        assert x.get("message") != fs.LIB_TROUVE
    assert any(x["statut"] == fs.A_RELIRE for x in hits), (phrase, hits)


def test_bilan_des_pieges_zero_et_zero():
    b = ps.bilan_pieges()
    assert b["pieges"] >= 50 and b["presentes_comme_documents"] == [] and b["non_signales"] == []


@pytest.mark.parametrize("phrase,fait,type_attendu", ps.JUSTES)
def test_les_faits_justes_sont_relies_au_bon_endroit(phrase, fait, type_attendu):
    hits = ps.fait_de(ps.controler(phrase), fait)
    assert any(x["statut"] == fs.AVEC_SOURCE and (x.get("source") or {}).get("type") == type_attendu for x in hits), \
        (phrase, hits)


def test_qui_affirme_quoi_le_dossier_de_l_acheteur_n_appuie_jamais_l_entreprise():
    """« Nous sommes certifiés ISO 14001 » reste à relire même si le règlement l'exige ; la même
    exigence rapportée (« Le règlement exige… ») est une phrase sur le marché, reliée au dossier."""
    sur_nous = ps.controler("Nous sommes certifiés ISO 14001.")
    assert [x["statut"] for x in sur_nous] == [fs.A_RELIRE] and sur_nous[0]["detail"] == fs.DET_ACHETEUR
    marche = ps.controler("Le règlement exige que les entreprises soient certifiées ISO 14001.")
    iso = ps.fait_de(marche, "ISO 14001")[0]
    assert iso["statut"] == fs.AVEC_SOURCE and iso["source"]["type"] == fs.T_ACHETEUR and iso["a_propos"] == fs.MARCHE
    assert iso["source"]["libelle"] == "dans le dossier de l'acheteur" and "ISO 14001" in iso["source"]["extrait"]


def test_un_fait_cite_doit_etre_du_bon_type_et_de_la_bonne_unite():
    # Votre estimation n'appuie que des nombres (délais, effectifs prévus, quantités).
    grue = ps.fait_de(ps.controler("Nous possédons une grue mobile [C4]."), "grue")[0]
    assert grue["statut"] == fs.A_RELIRE and grue["detail"] == fs.DET_ESTIMATION
    duree = ps.fait_de(ps.controler("La location de la grue durera 2 jours [C4]."), "2 jours")[0]
    assert duree["source"]["type"] == fs.T_ESTIMATION and duree["source"]["ref"] == "C4"
    # « 12 m3 de béton et 3 tonnes d'acier » : 12 tonnes n'y est pas (l'unité suit SON nombre).
    assert ps.fait_de(ps.controler("Nous avons livré 12 tonnes de béton [S1]."), "12 tonnes")[0]["statut"] == fs.A_RELIRE
    assert ps.fait_de(ps.controler("Nous avons livré 12 m3 de béton [S1]."), "12 m3")[0]["source"]["ref"] == "S1"
    # 85 k€ = 85 000 € ; 850 k€ non.
    assert ps.fait_de(ps.controler("Ce chantier a coûté 85 k€ [F1]."), "85 k€")[0]["source"]["ref"] == "F1"
    assert ps.fait_de(ps.controler("Ce chantier a coûté 850 k€ [F1]."), "850 k€")[0]["statut"] == fs.A_RELIRE


def test_le_renvoi_cite_passe_avant_un_fait_remis_non_cite():
    x = ps.fait_de(ps.controler("Nous sommes qualifiés Qualibat 3194 [F3]."), "Qualibat 3194")[0]
    assert x["source"]["ref"] == "F3" and x["source"]["cite"] is True and x["source"]["type"] == fs.T_DECLARE
    # Sans renvoi : relié quand même à l'endroit où il est écrit (vos documents d'abord), « non cité ».
    y = ps.fait_de(ps.controler("Nous sommes qualifiés Qualibat 3194."), "Qualibat 3194")[0]
    assert y["source"]["cite"] is False and y["source"]["type"] == fs.T_DOCUMENTS
    # Une durée sans renvoi ne se relie qu'avec un mot commun (pas de hasard « 10 ans » ≠ « 10 ans »).
    assert ps.fait_de(ps.controler("Nous travaillons depuis dix ans avec ce client."), "dix")[0]["statut"] == fs.A_RELIRE
    assert ps.fait_de(ps.controler("La pose du zinc durera 15 jours."), "15 jours")[0]["source"]["ref"] == "C2"


def test_recalcul_des_pourcentages_et_des_totaux():
    ok = ps.fait_de(ps.controler("Nos 6 couvreurs représentent 50 % de nos 12 salariés [S1][P2]."), "50 %")[0]
    assert ok["source"]["type"] == fs.T_CALCUL and ok["source"]["detail"] == "6 sur 12 font 50 %"
    faux = ps.fait_de(ps.controler("Nos 6 couvreurs représentent 60 % de nos 12 salariés [S1][P2]."), "60 %")[0]
    assert faux["statut"] == fs.A_RELIRE
    assert faux["detail"] == "Le calcul ne tombe pas juste : 6 sur 12 font 50 %, pas 60 %."
    tot = ps.fait_de(ps.controler("L'installation (3 jours) et la pose (15 jours) font au total 20 jours [C1][C2]."),
                     "20 jours")[0]
    assert tot["detail"] == "Le total ne tombe pas juste : 3 + 15 font 18, pas 20."
    juste = ps.fait_de(ps.controler("Soit 3 + 15, au total 18 jours [C1][C2]."), "18 jours")[0]
    assert juste["statut"] == fs.AVEC_SOURCE


@pytest.mark.parametrize("phrase,formule", [
    ("Nous garantissons une intervention rapide.", "Nous garantissons"),
    ("Nous nous engageons à nettoyer le site chaque soir.", "nous nous engageons"),
    ("Notre organisation vise zéro accident.", "zéro accident"),
    ("Nous trions 100 % des déchets.", "100 %"),
    ("Nous intervenons sous 24 h.", "sous 24 h"),
    ("Une astreinte 24h/24 est assurée par notre équipe.", "24h/24"),
    ("Nous livrerons au plus tard le 15 juin.", "au plus tard"),
])
def test_engagements_a_confirmer(phrase, formule):
    eng = [x for x in ps.controler(phrase) if x["type"] == fs.ENGAGEMENT]
    assert len(eng) == 1 and far.fold(eng[0]["fait"]) == far.fold(formule)
    assert eng[0]["statut"] == fs.A_RELIRE and eng[0]["message"] == fs.MSG_ENGAGEMENT


@pytest.mark.parametrize("phrase", [
    "Nous balisons la zone afin de garantir la sécurité des usagers.",
    "Notre démarche qualité repose sur des contrôles réguliers.",
    "Nous disposons d'une garantie décennale.",
])
def test_pas_d_engagement_dans_une_phrase_ordinaire(phrase):
    assert not [x for x in ps.controler(phrase) if x["type"] == fs.ENGAGEMENT]


def test_pas_d_engagement_pour_une_phrase_sur_le_marche_ni_pour_votre_texte():
    assert not [x for x in ps.controler("Le CCTP impose une intervention sous 24 h.") if x["type"] == fs.ENGAGEMENT]
    vous = fs.controler("Nous garantissons une intervention sous 24 h.", ps.fiches(), mode="utilisateur")
    assert not [x for x in vous if x["type"] == fs.ENGAGEMENT]
    # … mais un engagement écrit par l'IA et gardé dans votre texte reste à confirmer.
    ia = ps.controler("Nous garantissons une intervention sous 24 h.")
    garde = fs.controler("Nous garantissons une intervention sous 24 h. Merci.", ps.fiches(), mode="utilisateur",
                         anciens=ia)
    assert [x["type"] for x in garde if x["statut"] == fs.A_RELIRE].count(fs.ENGAGEMENT) == 1


def test_certification_courte_jamais_au_milieu_d_un_mot():
    f = fs.Fiche("C9", fs.T_DECLARE, fs.LIB_DECLARE, "Charge totale : 18 jours ; base de vie installée")
    assert f.index.trouve(far.CERTIFICATION, "rge") is None and f.index.trouve(far.CERTIFICATION, "mase") is None
    g = fs.Fiche("F9", fs.T_DECLARE, fs.LIB_DECLARE, "Qualification : RGE Qualibat ; certification ISO-14001")
    assert g.index.trouve(far.CERTIFICATION, "rge") is not None
    assert g.index.trouve(far.CERTIFICATION, "iso14001") is not None


# ═══ 2. Renvois, phrases, CV, export ════════════════════════════════════════════════════════

def test_renvois_lus_et_rattaches_a_leur_phrase():
    assert fs.refs_de("a [F3, F4] b [P1; 2] [S12]") == ["F3", "F4", "P1", "P2", "S12"]
    ph = fs.phrases("Nous avons 2 nacelles. [F2] Notre équipe compte 12 salariés [P2]. Fin.")
    # (la phrase est celle d'A0 au caractère près : l'espace laissée par le renvoi y reste)
    assert [(p["phrase"], p["refs"]) for p in ph] == [("Nous avons 2 nacelles.", ["F2"]),
                                                      ("Notre équipe compte 12 salariés .", ["P2"]), ("Fin.", [])]
    # Même découpage qu'A0 (les identifiants des faits restent les mêmes).
    texte = "## Moyens\n- Nous avons 2 nacelles [F2].\n| Compagnons | 15 [P2] |\nLe CCTP prévoit 450 m2 [S1]."
    assert [p["phrase"] for p in fs.phrases(texte)] == [p for p, _t, _b in far.phrases(texte)]


def test_les_renvois_ne_sont_jamais_des_faits():
    items = ps.controler("Notre équipe compte 12 salariés [P2] [F3] [E1].")
    assert [x["fait"] for x in items] == ["12 salariés"]


def test_renvois_retires_a_l_export():
    from app.services import atelier_export as ax
    t = ("Nous disposons de 2 nacelles [F2]. Notre équipe [P2][E1] compte 12 salariés.\n"
         "| Moyens | Nombre [C3] |\n[CV F9]\nFin [F3, S2].")
    out = ax.texte_export(t)
    assert not re.search(r"\[(?:[FSPECG]\s*\d|CV)", out), out
    assert "Nous disposons de 2 nacelles." in out and "Fin." in out


def test_cv_insere_tel_quel_sans_ia():
    from app.services import preuves as pv
    val = pv.valider_valeur("salarie", {"nom": "Maëlys Kerbrat", "fonction": "Conductrice de travaux",
                                        "experience_annees": 17, "diplomes": "CAP Couvreur Zingueur",
                                        "chantiers": "École Jules Ferry\nGymnase de Brest"})
    f = fs.Fiche("F2", fs.T_DECLARE, fs.LIB_DECLARE, pv.texte_de("salarie", val), nature="salarie", valeur=val,
                 extra=fs._adjacents("salarie", val))
    t = fs.inserer_cv("Encadrement :\n\n[CV F2]\n\n[CV F8]\n", [f])
    assert "**Maëlys Kerbrat**, conductrice de travaux [F2]" in t and "- Expérience : 17 ans [F2]" in t
    assert "- Chantiers : École Jules Ferry ; Gymnase de Brest [F2]" in t
    assert "[À compléter : CV de la personne]" in t and "[CV" not in t
    items = fs.controler(t, [f], mode="ia")
    cv = [x for x in items if "17" in x["fait"] or "Kerbrat" in x["fait"] or "Jules Ferry" in x["fait"]]
    assert cv and all(x["statut"] == fs.AVEC_SOURCE and x["source"]["ref"] == "F2" for x in cv)
    # Le texte remis à l'IA pour cette fiche : la fonction seule (jamais le nom, jamais le CV).
    f2 =fs.Fiche("F2", fs.T_DECLARE, fs.LIB_DECLARE, pv.texte_de("salarie", val),
                  pv.texte_pour_ia({"nature": "salarie", "valeur": val}), nature="salarie", valeur=val)
    assert "Kerbrat" not in f2.ligne_ia() and "17" not in f2.ligne_ia() and "CAP" not in f2.ligne_ia()
    assert "[CV F2]" in f2.ligne_ia()


# ═══ 3. Les modes : votre texte, « Raccourcir », une source perdue ═════════════════════════

def test_votre_texte_vos_declarations_et_les_faits_a_relire_restent():
    ia = ps.controler("Nous sommes certifiés MASE. Nous disposons de 2 nacelles articulées [F2].")
    assert [x["fait"] for x in ia if x["statut"] == fs.A_RELIRE] == ["MASE"]
    t2 = "Nous sommes certifiés MASE. Nous disposons de 2 nacelles articulées. Nous avons 4 camions."
    vous = fs.controler(t2, ps.fiches(), mode="utilisateur", anciens=ia, noms_entreprise=ps.NOMS)
    par = {x["fait"]: x for x in vous}
    assert par["MASE"]["statut"] == fs.A_RELIRE                         # reste à relire, même gardé par vous
    assert par["2 nacelles"]["source"]["ref"] == "F2"                     # garde sa source sans le renvoi
    assert par["4 camions"]["source"]["type"] == fs.T_VOUS and par["4 camions"]["message"] == "déclaré par vous"


def test_raccourcir_ne_blanchit_rien_et_garde_les_sources():
    base_t = "Nous sommes certifiés MASE. Nous disposons de 2 nacelles articulées [F2]."
    base = ps.controler(base_t)
    court = fs.controler("Certifiés MASE, nous avons 2 nacelles articulées et 3 camions.", ps.fiches(),
                         mode="raccourci", anciens=base, base_texte=base_t, noms_entreprise=ps.NOMS)
    par = {x["fait"]: x for x in court}
    assert par["MASE"]["statut"] == fs.A_RELIRE
    assert par["2 nacelles"]["statut"] == fs.AVEC_SOURCE and par["2 nacelles"]["source"]["ref"] == "F2"
    assert par["3 camions"]["statut"] == fs.A_RELIRE                    # ajouté par l'IA en raccourcissant


def test_une_source_perdue_rend_le_fait_a_relire():
    items = ps.controler("Nous disposons de 2 nacelles articulées [F2].")
    x = ps.fait_de(items, "2 nacelles")[0]
    assert x["source"]["preuve_id"] == 2
    adj = fs.ajuster(items, {"preuves": {1, 3}, "extraits": set()})
    y = ps.fait_de(adj, "2 nacelles")[0]
    assert y["statut"] == fs.A_RELIRE and y["detail"] == fs.DET_SOURCE_PERDUE and y["id"] == x["id"]
    assert far.non_traites(adj) == 1 and far.non_traites(items) == 0
    # Recontrôlé sans la preuve : relié au document où il est encore écrit…
    sans = [f for f in ps.fiches() if f.ref != "F2"]
    re_ = fs.controler("Nous disposons de 2 nacelles articulées [F2].", sans, mode="ia", anciens=items)
    assert ps.fait_de(re_, "2 nacelles")[0]["source"]["ref"] == "S1"
    # … et sans aucune source : à relire, et la perte est dite (pas « renvoi inconnu »).
    sans = [f for f in ps.fiches() if f.ref not in ("F2", "S1")]
    re_ = fs.controler("Nous disposons de 2 nacelles articulées [F2].", sans, mode="ia", anciens=items)
    z = ps.fait_de(re_, "2 nacelles")[0]
    assert z["statut"] == fs.A_RELIRE and z["detail"] == fs.DET_SOURCE_PERDUE


def test_bilan_compte_les_faits_et_pas_les_engagements():
    items = ps.controler("Nous disposons de 2 nacelles articulées [F2] et nous garantissons 100 % de tri.")
    b = fs.bilan(items)
    assert b["total"] == 2 and b["avec_source"] == 1 and b["engagements"] == 1
    assert b["message"] == "Faits avec une source : 1 sur 2"
    assert fs.bilan([{"id": "x", "fait": "12", "type": "chiffre", "statut": "a_relire"}]) is None   # relevé par A0


# ═══ 4. L'atelier : rédaction, affichage, export ═══════════════════════════════════════════

def _preuve(client, h, **body):
    body.setdefault("type_source", "declare")
    r = client.post("/api/preuves", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _sec(client, h, pid, sid):
    return next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sid)


def _rediger(client, h, pid, sid, texte, fake_llm):
    sent = []

    def ans(kw):
        sent.append(kw)
        return (texte(kw) if callable(texte) else texte), "end_turn"
    fake = fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    return fake


def test_redaction_faits_numerotes_types_cv_jamais_a_l_ia_et_controle(client, auth, fake_llm, monkeypatch):
    monkeypatch.delenv("ATELIER_LIBELLES_SOURCES", raising=False)
    h = auth["headers"]
    _company(client, h)
    nac = _preuve(client, h, nature="materiel", valeur={"designation": "Nacelle articulée", "quantite": 2})
    cv = _preuve(client, h, nature="salarie", valeur={"nom": "Maëlys Kerbrat", "fonction": "Conductrice de travaux",
                                                      "experience_annees": 17, "diplomes": "CAP Couvreur Zingueur"})
    assert (nac["ref"], cv["ref"]) == ("F1", "F2")
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    texte = ("Nous disposons de 2 nacelles articulées [F1]. Notre équipe compte 12 salariés [P2]. "
             "Nous sommes certifiés ISO 14001. Nous garantissons une intervention sous 24 h.\n\n[CV F2]\n")
    fake = _rediger(client, h, pid, sid, texte, fake_llm)
    sent = fake.sent()
    # Faits numérotés et typés ; l'équipe par sa fonction et son étiquette ; ni nom ni CV.
    assert "[F1] (déclaré par vous) Matériel : Nacelle articulée ; quantité : 2" in sent
    assert "[P2] (déclaré par vous) Effectif : 12" in sent
    assert "[F2] (déclaré par vous) Équipe : [Conductrice de travaux 2], Conductrice de travaux" in sent
    assert "[CV F2]" in sent and "« exigé par l'acheteur »" in sent
    for interdit in ("Kerbrat", "Maëlys", "CAP Couvreur", "17 ans", "Tanguy"):
        assert interdit not in sent, interdit
    s = _sec(client, h, pid, sid)
    v = s["version_courante"]
    # Le CV est inséré tel quel, sans IA, et ses faits sont reliés à sa fiche.
    assert "**Maëlys Kerbrat**, conductrice de travaux [F2]" in v["texte"] and "- Expérience : 17 ans [F2]" in v["texte"]
    a_relire = {(f["type"], f["fait"]) for f in v["faits"]}
    assert ("certification", "ISO 14001") in a_relire and ("engagement", "Nous garantissons") in a_relire
    assert all(f["statut"] in ("a_relire", "relu_par_vous") for f in v["faits"])
    assert not any("17" in f["fait"] or "Kerbrat" in f["fait"] or f["fait"].startswith("2 nac") for f in v["faits"])
    iso = next(f for f in v["faits"] if f["fait"] == "ISO 14001")
    assert iso["message"] == far.MESSAGE and iso["detail"] == fs.DET_ACHETEUR
    # Libellés éteints par défaut : seul l'affichage d'A0.
    assert v["controle"] == {"libelles": False} and "faits_sources" not in v and s["controle"] == {"libelles": False}
    assert _etat(client, h, pid)["sources_faits"]["libelles"] is False
    # Libellés allumés (après la calibration) : chaque fait dit où il a été trouvé, et le compteur.
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    st = _etat(client, h, pid)
    s = next(x for x in st["sections"] if x["id"] == sid)
    v = s["version_courante"]
    srcs = {f["fait"]: f["source"] for f in v["faits_sources"]}
    assert srcs["2 nacelles"]["ref"] == "F1" and srcs["2 nacelles"]["libelle"] == "déclaré par vous"
    assert srcs["12 salariés"]["ref"] == "P2" and srcs["17 ans"]["ref"] == "F2"
    c = v["controle"]
    assert c["libelles"] is True and c["total"] == c["avec_source"] + 2 and c["engagements"] == 1
    assert c["message"] == f"Faits avec une source : {c['avec_source']} sur {c['total']}"
    assert s["controle"] == c and st["sources_faits"]["bulle"] == fs.BULLE


def test_preuve_documentee_lien_vers_le_passage(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    h = auth["headers"]
    r = client.post("/api/knowledge/text", headers=h, json={"name": "Mémoire 2024", "kind": "memoire",
                                                            "text": ps.DOC})
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc"]["id"]
    p = _preuve(client, h, nature="materiel", valeur={"designation": "nacelles articulées", "quantite": 2},
                type_source="documents", source={"doc_id": doc_id, "passage": "Nous disposons de 2 nacelles articulées"})
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    _rediger(client, h, pid, sid, f"Nous disposons de 2 nacelles articulées [{p['ref']}].", fake_llm)
    v = _sec(client, h, pid, sid)["version_courante"]
    src = next(f["source"] for f in v["faits_sources"] if f["fait"] == "2 nacelles")
    assert src["type"] == fs.T_DOCUMENTS and src["libelle"] == "trouvé dans vos documents"
    assert src["lien"] == f"/api/preuves/{p['id']}/passage" and "2 nacelles articulées" in src["extrait"]
    assert client.get(src["lien"], headers=h).status_code == 200


def test_export_sans_aucun_renvoi(client, auth):
    import docx
    h = auth["headers"]
    _company(client, h)
    _preuve(client, h, nature="materiel", valeur={"designation": "Nacelle articulée", "quantite": 2})
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    for s in st["sections"]:
        s2 = _ecrire(client, h, pid, s, "Nous disposons de 2 nacelles articulées [F1]. Notre équipe compte 12 "
                                          "salariés [P2][E1].")
        assert s2["faits_a_relire"] == 0
        r = client.post(f"/api/atelier/{pid}/sections/{s['id']}/valider", headers=h,
                        json={"version_id": s2["version_courante"]["id"]})
        assert r.status_code == 200, r.text
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 200, r.text
    full = "\n".join(p.text for p in docx.Document(io.BytesIO(r.content)).paragraphs)
    assert "Nous disposons de 2 nacelles articulées. Notre équipe compte 12 salariés." in full
    assert not re.search(r"\[[FSPECG]\d", full)


# ═══ 5. « Ajouter une source », recontrôle, preuve retirée ou expirée ══════════════════════

def test_ajouter_une_source_en_declarant_le_fait_sans_toucher_au_texte(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    _rediger(client, h, pid, sid, "Nous mobilisons 15 compagnons sur le chantier. Nous garantissons un nettoyage "
                                  "quotidien.", fake_llm)
    s = _sec(client, h, pid, sid)
    v = s["version_courante"]
    f15 = next(f for f in v["faits"] if f["fait"] == "15 compagnons")
    eng = next(f for f in v["faits"] if f["type"] == "engagement")
    url = f"/api/atelier/{pid}/sections/{sid}/faits/{f15['id']}"
    r = client.get(url + "/sources", headers=h)
    assert r.status_code == 200, r.text
    prop = r.json()["proposition"]
    assert prop["nature"] == "chiffre_cle" and prop["valeur"] == {"libelle": "Compagnons", "valeur": 15}
    assert r.json()["preuves"] == [] and r.json()["natures"][0]["code"] == "chiffre_cle"
    # Une fiche qui ne contient pas le fait tel qu'il est écrit est refusée : rien n'est créé.
    r = client.post(url + "/source", headers=h, json={"nature": "chiffre_cle",
                                                      "valeur": {"libelle": "Compagnons", "valeur": 14}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "fiche_sans_ce_fait"
    assert client.get("/api/preuves", headers=h).json()["preuves"] == []
    r = client.post(url + "/source", headers=h, json={"nature": "chiffre_cle", "valeur": {"libelle": "Moyens",
                                                                                          "couleur": "x"}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "champ_inconnu"
    # Déclaré : une preuve « déclaré par vous » dans « Mes preuves », le fait relié, le texte intact.
    r = client.post(url + "/source", headers=h, json=dict(prop))
    assert r.status_code == 200, r.text
    assert r.json()["fait"]["statut"] == fs.AVEC_SOURCE and r.json()["fait"]["source"]["ref"] == "F1"
    s2 = r.json()["section"]
    assert s2["version_courante"]["id"] == v["id"] and s2["version_courante"]["texte"] == v["texte"]
    assert s2["faits_a_relire"] == 1                                          # reste l'engagement
    pr = client.get("/api/preuves", headers=h).json()["preuves"]
    assert [(p["nature"], p["type_source"], p["statut"]) for p in pr] == [("chiffre_cle", "declare", "acceptee")]
    # Un engagement ne se prouve pas par une fiche : on le confirme (ou on le corrige).
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/faits/{eng['id']}/source", headers=h, json=dict(prop))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "engagement"
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/faits/{eng['id']}", headers=h, json={"statut": "relu_par_vous"})
    assert r.status_code == 200 and r.json()["section"]["faits_a_relire"] == 0
    # Un fait relié ne se « relit » pas.
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/faits/{f15['id']}", headers=h, json={"statut": "relu_par_vous"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "fait_avec_source"


def test_relier_une_preuve_ajoutee_depuis_et_recontroler(client, auth, fake_llm):
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    _rediger(client, h, pid, sid, "Nous sommes qualifiés Qualibat 3194. Nous disposons d'une nacelle.", fake_llm)
    v = _sec(client, h, pid, sid)["version_courante"]
    assert {f["fait"] for f in v["faits"]} == {"Qualibat 3194", "nacelle"}
    q = _preuve(client, h, nature="qualification", valeur={"nom": "Qualibat 3194"},
                date_fin_validite=(date.today() + timedelta(days=300)).isoformat())
    fq = next(f for f in v["faits"] if f["fait"] == "Qualibat 3194")
    r = client.get(f"/api/atelier/{pid}/sections/{sid}/faits/{fq['id']}/sources", headers=h)
    assert [x["ref"] for x in r.json()["preuves"]] == [q["ref"]]
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/faits/{fq['id']}/source", headers=h,
                    json={"preuve_id": q["id"]})
    assert r.status_code == 200 and r.json()["section"]["faits_a_relire"] == 1
    # Une preuve qui ne contient pas le fait ne le relie pas.
    fn = next(f for f in v["faits"] if f["fait"] == "nacelle")
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/faits/{fn['id']}/source", headers=h,
                    json={"preuve_id": q["id"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "preuve_sans_ce_fait"
    # Une nacelle ajoutée dans « Mes preuves », puis « Recontrôler » : reliée, sans IA ni nouvelle version.
    _preuve(client, h, nature="materiel", valeur={"designation": "Nacelle"})
    r = client.post(f"/api/atelier/{pid}/sections/{sid}/controle", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["faits_a_relire"] == 0 and r.json()["version_courante"]["id"] == v["id"]


def test_preuve_retiree_ou_expiree_le_fait_redevient_a_relire_et_bloque_l_export(client, auth, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    h = auth["headers"]
    nac = _preuve(client, h, nature="materiel", valeur={"designation": "Nacelle articulée", "quantite": 2})
    qual = _preuve(client, h, nature="qualification", valeur={"nom": "Qualibat 3194"},
                   date_fin_validite=(date.today() + timedelta(days=30)).isoformat())
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sec = st["sections"][0]
    s = _ecrire(client, h, pid, sec, "Nous disposons de 2 nacelles articulées [F1]. Nous sommes qualifiés "
                                     "Qualibat 3194 [F2].")
    assert s["faits_a_relire"] == 0 and s["version_courante"]["controle"]["avec_source"] == 2
    st = _etat(client, h, pid)
    assert not any(r["code"] == "faits_a_relire" for r in st["blocage"]["raisons"])
    h0 = st["blocage"]["etat_hash"]
    # La preuve est retirée : à la lecture, le fait redevient à relire (sans rien réécrire) et bloque.
    assert client.post(f"/api/preuves/{nac['id']}/retirer", headers=h, json={}).status_code == 200
    st = _etat(client, h, pid)
    s = next(x for x in st["sections"] if x["id"] == sec["id"])
    f = next(x for x in s["version_courante"]["faits"] if x["fait"] == "2 nacelles")
    assert f["statut"] == "a_relire" and f["detail"] == fs.DET_SOURCE_PERDUE and s["faits_a_relire"] == 1
    assert any(r["code"] == "faits_a_relire" for r in st["blocage"]["raisons"]) and st["blocage"]["etat_hash"] != h0
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "export_bloque"
    # « Je l'ai relu » marche sur ce fait (il n'est plus relié à rien).
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/faits/{f['id']}", headers=h,
                    json={"statut": "relu_par_vous"})
    assert r.status_code == 200 and r.json()["section"]["faits_a_relire"] == 0
    # La qualification expire : même chose, et le recontrôle le garde.
    from app.models import Preuve
    db = _db()
    try:
        p = db.get(Preuve, qual["id"])
        p.date_fin_validite = date.today() - timedelta(days=2)
        db.commit()
    finally:
        db.close()
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == sec["id"])
    assert any(x["fait"] == "Qualibat 3194" and x["detail"] == fs.DET_SOURCE_PERDUE for x in s["version_courante"]["faits"])
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/controle", headers=h)
    assert r.status_code == 200 and r.json()["faits_a_relire"] == 1
    q = next(x for x in r.json()["version_courante"]["faits"] if x["fait"] == "Qualibat 3194")
    assert q["detail"] == fs.DET_SOURCE_PERDUE
    assert any(x.get("raison") == "expiree" for x in _etat(client, h, pid)["sources_faits"]["preuves_ecartees"])


# ═══ 6. Isolation, démo, vocabulaire ═══════════════════════════════════════════════════════

def test_un_autre_compte_recoit_404_et_la_demo_403(client, auth, fake_llm):
    h = auth["headers"]
    pid = _projet(client, h)
    st = _creer(client, h, pid)
    sid = st["sections"][0]["id"]
    _rediger(client, h, pid, sid, "Nous sommes certifiés MASE.", fake_llm)
    fid = _sec(client, h, pid, sid)["version_courante"]["faits"][0]["id"]
    import uuid
    r = client.post("/api/auth/register", json={"email": f"autre_{uuid.uuid4().hex[:8]}@test.fr",
                                                "password": "motdepasse123", "full_name": "Autre",
                                                "company_name": "Autre SARL"})
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    base = f"/api/atelier/{pid}/sections/{sid}"
    assert client.get(base + f"/faits/{fid}/sources", headers=h2).status_code == 404
    assert client.post(base + f"/faits/{fid}/source", headers=h2, json={"nature": "qualification",
                                                                       "valeur": {"nom": "MASE"}}).status_code == 404
    assert client.post(base + "/controle", headers=h2).status_code == 404
    r = client.post("/api/auth/demo")
    hd = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for url, body in ((base + f"/faits/{fid}/source", {"nature": "qualification", "valeur": {"nom": "MASE"}}),
                      (base + "/controle", None)):
        r = client.post(url, headers=hd, json=body)
        assert r.status_code == 403, (url, r.text)


def test_jamais_le_mot_verifie():
    import ast
    import inspect
    arbre = ast.parse(inspect.getsource(fs))
    textes = [n.value for n in ast.walk(arbre) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    textes += [fs.BULLE, fs.MSG_ENGAGEMENT, fs.MSG_MARCHE, fs.DET_ACHETEUR, fs.DET_ESTIMATION, fs.DET_SOURCE_PERDUE]
    for t in textes:
        low = t.lower()
        if "jamais « vérifié »" in low or "jamais \"vérifié\"" in low or "jamais « vérifié »" in t:
            continue
        assert "vérifi" not in low or "jamais" in low, t
    for t in (fs.BULLE, fs.MSG_ENGAGEMENT, fs.MSG_MARCHE, fs.DET_ACHETEUR, fs.DET_ESTIMATION, fs.DET_SOURCE_PERDUE,
              fs.LIB_TROUVE, fs.LIB_DECLARE, fs.LIB_ACHETEUR, fs.LIB_CALCUL, fs.LIB_ESTIMATION, fs.LIB_PARTENAIRE):
        assert "vérifi" not in t.lower() and "certifié par" not in t.lower(), t


def test_les_libelles_ne_s_allument_qu_avec_le_reglage(monkeypatch):
    monkeypatch.delenv("ATELIER_LIBELLES_SOURCES", raising=False)
    assert fs.libelles_actifs() is False
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "0")
    assert fs.libelles_actifs() is False
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    assert fs.libelles_actifs() is True


# ═══ 7. L'outil de mesure des fausses alertes (sans données réelles) ════════════════════════

def _memoire(tmp, nom, accord=True, fin_accord=None, texte=None):
    d = tmp / nom
    (d / "sources").mkdir(parents=True)
    (d / "dce").mkdir()
    (d / "memoire.md").write_text(texte or ("# Moyens humains\nNotre équipe compte 12 salariés. Nous disposons de "
                                            "2 nacelles articulées.\n# Qualité\nNous sommes certifiés ISO 14001. Nous "
                                            "sommes qualifiés Qualibat 3194.\n"), encoding="utf-8")
    (d / "sources" / "plaquette.txt").write_text(ps.DOC, encoding="utf-8")
    (d / "dce" / "rc.txt").write_text(ps.DCE, encoding="utf-8")
    (d / "profil.json").write_text(json.dumps({"nom": "PME fictive", "effectif": 12}), encoding="utf-8")
    if accord:
        (d / "accord.json").write_text(json.dumps({
            "accord_ecrit_le": (date.today() - timedelta(days=10)).isoformat(),
            "valable_jusqu_au": (fin_accord or (date.today() + timedelta(days=90))).isoformat(),
            "anonymise": True}), encoding="utf-8")
    return d


def test_outil_de_mesure_exige_l_accord_ecrit_puis_compte_les_fausses_alertes(tmp_path):
    import csv
    import importlib.util
    spec = importlib.util.spec_from_file_location("mesure", os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts", "mesure_fausses_alertes.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    racine = tmp_path / "calibration"
    _memoire(racine, "pme01")
    _memoire(racine, "pme02", accord=False)
    _memoire(racine, "pme03", fin_accord=date.today() - timedelta(days=1))
    sortie = tmp_path / "mesure"
    r = m.preparer(str(racine), str(sortie))
    assert r["memoires"] == 1 and {x["memoire"] for x in r["ignores"]} == {"pme02", "pme03"}
    lignes = list(csv.DictReader(open(sortie / "alertes.csv", encoding="utf-8")))
    assert [x["fait"] for x in lignes] == ["ISO 14001"]                    # le reste est dans les sources
    assert lignes[0]["detail"] == fs.DET_ACHETEUR
    mems = list(csv.DictReader(open(sortie / "memoires.csv", encoding="utf-8")))
    assert mems[0]["faits"] == "4" and mems[0]["avec_source"] == "3" and mems[0]["alertes"] == "1"
    # Mathys annote : une vraie alerte (le fait n'est pas dans les sources).
    lignes[0]["verdict"] = "vraie"
    with open(sortie / "alertes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=m.COLONNES_ALERTES)
        w.writeheader()
        w.writerows(lignes)
    b = m.bilan(str(sortie))
    assert b["fausses_alertes"] == 0 and b["inventions_ou_oublis_detectes"] == 1
    assert b["part_des_faits_avec_une_source"] == 0.75 and b["objectif_atteint"] is False   # moins de 20 mémoires
    assert "provisoire" in m._decision(b)
    bilan_json = (sortie / "bilan.json").read_text(encoding="utf-8")
    assert "ISO 14001" not in bilan_json and "salariés" not in bilan_json          # aucun texte des mémoires
    assert m.main(["pieges"]) == 0
