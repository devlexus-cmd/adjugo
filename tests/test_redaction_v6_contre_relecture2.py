"""
Rédaction, vague 6 — seconde contre-relecture (contrat docs/REDACTION_V6.md, section « Seconde contre-relecture ») :
chaque remarque retenue reproduite ici ; sur le code d'avant (ec01cb3) ces tests échouent.

  1. marché subséquent : repéré seulement quand une phrase présente CE marché comme tel, jamais sur une simple mention
     (le règlement d'un accord-cadre cite ses futurs marchés subséquents, et le délai de 11 jours de R2182-1 s'applique
     à l'accord-cadre) ; message sous condition, avec la vraie source ;
  2. un règlement qui parle de marchés subséquents sans nommer la procédure laisse lire la procédure dans l'analyse ;
  3. dossier à plusieurs lots : un nombre écrit juste après « lot » qui compte quelque chose (« à ce lot 3
     compagnons ») reste un fait à relire ;
  4. limites d'une phrase qui cite plusieurs lots : chaque valeur au bon lot (« Lot 2 : 10 pages, lot 3 : 25 000
     caractères ») ; un lot cité sans valeur, ou une construction mêlée : tout « selon le lot » ;
  5. courrier à plusieurs lots : une ligne qui COMMENCE par « Pour / S'agissant du lot N » ouvre ce lot, quelle que
     soit la ponctuation ; une phrase qui parle seule d'un AUTRE lot laisse les lignes suivantes sans lot ;
  6. grille par lot : « …, Prix 40 % - Lot 3 : Valeur technique 40 % » reste lisible (titre de lot en ligne).
IA simulée, aucun réseau.
"""
import json

import pytest

from app.services import atelier_lots as al
from app.services import carnet_notes as cn
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from app.services import grille_notation as gn
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _etat
from tests.test_redaction_v6_carnet import _h, _marche, _reponse_ia, _set
from tests.test_redaction_v6_ensemble import RC_PROC, _cle, _form_avec
from tests.test_redaction_v6_lots import RC, _creer_lots, _lot, _par, _projet, _tout_ecrire


def _analyse(pid):
    from app.models import Project
    db = _db()
    try:
        return json.loads(json.dumps(db.get(Project, pid).ai_analysis))
    finally:
        db.close()


def _projet_proc(dce="", nature=""):
    from types import SimpleNamespace
    return SimpleNamespace(id=0, name="Marché", dce_fichier_impose=None,
                           ai_analysis={"dce_excerpt": dce, "details": {"nature_marche": nature}})


RC_AC = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 1 - Objet\nLa présente consultation porte sur un "
         "accord-cadre multi-attributaire. Il sera exécuté au moyen de marchés subséquents.\nArticle 2 - Divers\n"
         "Les offres sont rédigées en français.\n")


# ═══ 1. Marché subséquent : CE marché, jamais une simple mention ═════════════════════════════════

@pytest.mark.parametrize("nature", [
    "Accord-cadre multi-attributaires passé par appel d'offres ouvert (articles R2124-1 et R2161-2), exécuté par la "
    "conclusion de marchés subséquents.",
    "Accord-cadre multi-attributaire passé selon la procédure d'appel d'offres ouvert ; il donnera lieu à la "
    "conclusion de marchés subséquents.",
    "Accord-cadre passé par appel d'offres ouvert : il ne donnera pas lieu à des marchés subséquents.",
    "Appel d'offres ouvert. Chaque marché subséquent conclu sur le fondement de l'accord-cadre précisera les quantités.",
])
def test_accord_cadre_qui_cite_ses_marches_subsequents_garde_le_delai_de_11_jours(client, auth, nature):
    h = _h(auth)
    pid = _marche(client, h, nature=nature)
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert c["procedure"] == "formalisee"
    assert c["message_delai"] == cn.MSG_DELAI[cn.FORMALISEE] and c["phrase_subsequent"] == ""
    assert "peut donc être signé sans attendre" not in c["message_delai"]
    assert cn.procedure_du_marche(_projet_proc(nature=nature))["subsequent"] == ""


def test_reglement_d_accord_cadre_procedure_choisie_formalisee_garde_r2182_1(client, auth):
    h = _h(auth)
    pid = _marche(client, h, nature="")
    a = _analyse(pid)
    a["dce_excerpt"] = RC_AC
    _set(pid, ai_analysis=a)
    c = client.get(f"/api/carnet/{pid}/courrier?procedure=formalisee", headers=h).json()
    assert c["message_delai"] == cn.MSG_DELAI[cn.FORMALISEE] and c["phrase_subsequent"] == ""
    assert "article R2182-1" in c["message_delai"]


@pytest.mark.parametrize("dce,nature,source,phrase", [
    (RC_AC.replace("La présente consultation porte sur un accord-cadre multi-attributaire. Il sera exécuté au moyen de "
                   "marchés subséquents.", "Le présent marché subséquent est passé sur le fondement de l'accord-cadre "
                                           "de couverture des bâtiments communaux."),
     "Appel d'offres ouvert", "règlement de la consultation", "Le présent marché subséquent"),
    ("", "Marché subséquent n° 3 de l'accord-cadre de travaux de couverture (appel d'offres ouvert).",
     "analyse du marché", "Marché subséquent n° 3"),
])
def test_ce_marche_est_un_marche_subsequent_message_sous_condition_et_vraie_source(client, auth, dce, nature, source,
                                                                                  phrase):
    h = _h(auth)
    pid = _marche(client, h, nature=nature)
    a = _analyse(pid)
    a["dce_excerpt"] = dce
    _set(pid, ai_analysis=a)
    c = client.get(f"/api/carnet/{pid}/courrier?procedure=formalisee", headers=h).json()
    assert c["message_delai"] == cn.message_delai_subsequent(source)
    assert c["phrase_subsequent"].startswith(phrase)
    qui = "Le règlement de la consultation" if source.startswith("règlement") else "L'analyse du marché"
    assert f"{qui} présente ce marché comme un marché subséquent" in c["message_delai"]
    assert "Si c'est bien le cas, l'acheteur n'est pas tenu d'attendre 11 jours" in c["message_delai"]
    assert "(article R2182-2)" in c["message_delai"] and "(16 jours" in c["message_delai"]
    assert "Le règlement parle" not in c["message_delai"]


# ═══ 2. Règlement sans procédure : la procédure lue dans l'analyse ═══════════════════════════════

def test_reglement_qui_parle_de_marches_subsequents_sans_procedure_lit_l_analyse(client, auth):
    p = cn.procedure_du_marche(_projet_proc(dce=RC_AC, nature="Appel d'offres ouvert (R2124-2)"))
    assert p["code"] == cn.FORMALISEE and p["source"] == "analyse du marché" and p["subsequent"] == ""
    h = _h(auth)
    pid = _marche(client, h, nature="Appel d'offres ouvert (R2124-2)")
    a = _analyse(pid)
    a["dce_excerpt"] = RC_AC
    _set(pid, ai_analysis=a)
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert c["procedure"] == cn.FORMALISEE and "article R2181-4" in c["corps"]
    assert c["message_delai"] == cn.MSG_DELAI[cn.FORMALISEE]


# ═══ 3. « à ce lot 3 compagnons » : le nombre reste un fait ═══════════════════════════════════════

def _a_relire(texte, lots=()):
    return [x["fait"] for x in fs.controler(texte, [], mode="ia", section_entreprise=True, lots=lots,
                                            noms_entreprise=["Notre entreprise"]) if x.get("statut") == fs.A_RELIRE]


@pytest.mark.parametrize("phrase,attendus", [
    ("Notre entreprise affecte à ce lot 3 compagnons qualifiés.", ["3 compagnons"]),
    ("Notre équipe dédiée à ce lot 2 chefs de chantier encadre les travaux.", ["2 chefs"]),
    ("Nous affectons au lot 3 couvreurs et 2 apprentis.", ["3 couvreurs", "2 apprentis"]),
    ("Nous ajoutons aux lots 2 compagnons qualifiés.", ["2 compagnons"]),
    # Le numéro du lot, lui, n'est toujours pas un fait.
    ("Le CCTP du lot 2 prévoit une couverture en ardoise naturelle.", []),
    ("Le lot 3 a 5 semaines de délai d'exécution.", ["5 semaines"]),
    ("Pour le lot 2, 8 semaines de travaux sont prévues.", ["8 semaines"]),
    ("Le lot 2 compris dans notre offre est réalisé par notre équipe.", []),
])
def test_un_nombre_qui_compte_apres_lot_reste_a_relire(phrase, attendus):
    assert _a_relire(phrase, lots=("2", "3")) == attendus
    assert [f["fait"] for f in far.a_relire(phrase, [], section_entreprise=True, lots=("2", "3"))
            if f["type"] == far.CHIFFRE] == attendus


def test_intitule_du_lot_apres_le_numero_n_est_pas_une_quantite():
    faits = far.a_relire("Pour le lot 2 Couverture, nous posons une ardoise naturelle.", [], section_entreprise=True,
                         lots=("2", "3"))
    assert [f["fait"] for f in faits if f["type"] == far.CHIFFRE] == []


def test_redaction_ia_a_ce_lot_3_compagnons_reste_a_relire(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    fake_llm(lambda kw: ("Nous affectons à ce lot 3 compagnons qualifiés et un chef de chantier.", "end_turn"))
    p3 = _par(st, "Méthodologie", "3")
    r = client.post(f"/api/atelier/{pid}/sections/{p3['id']}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    _attendre(client, h, pid, r.json()["tache"]["id"])
    s = next(x for x in _etat(client, h, pid)["sections"] if x["id"] == p3["id"])
    faits = [x["fait"] for x in (s["version_courante"].get("faits") or []) if x.get("statut") == fs.A_RELIRE]
    assert "3 compagnons" in faits, faits


# ═══ 4. Limites d'une phrase qui cite plusieurs lots ═════════════════════════════════════════════

def _par_lot(ph):
    L = gn.limites_texte(ph)
    return {n: sorted((x["type"], x["valeur"], x.get("objet") or "") for x in al.limites_du_lot(L, n, ["2", "3"]))
            for n in ("2", "3")}


@pytest.mark.parametrize("phrase,lot2,lot3", [
    ("Pour le lot 2, le mémoire fera 10 pages au maximum, et pour le lot 3 au plus 30 000 caractères.",
     [("pages", 10, "")], [("caracteres", 30000, "")]),
    ("Pour le lot 2, le mémoire fera 10 pages au maximum, pour le lot 3, au plus 20 000 caractères.",
     [("pages", 10, "")], [("caracteres", 20000, "")]),
    ("Lot 2 : mémoire de 10 pages au maximum, lot 3 : 25 000 caractères au maximum.",
     [("pages", 10, "")], [("caracteres", 25000, "")]),
    # Construction « valeur, lot » (première contre-relecture) : inchangée.
    ("Le mémoire technique compte 6 pages au maximum pour le lot 2 et 3 pages au maximum pour le lot 3.",
     [("pages", 6, "")], [("pages", 3, "")]),
    ("Le mémoire compte 6 pages au maximum pour le lot 2 et 6 pages au maximum pour le lot 3.",
     [("pages", 6, "")], [("pages", 6, "")]),
    # Un lot cité sans valeur, ou un nombre de pages que le repérage n'a pas relevé : on ne sait pas.
    ("Pour le lot 2 le mémoire est limité à 10 pages, pour le lot 3 à 20 000 caractères.",
     [("pages", 10, al.OBJET_SELON_LOT)], [("pages", 10, al.OBJET_SELON_LOT)]),
    ("Le mémoire compte 6 pages et 3 pages au maximum pour les lots 2 et 3.",
     [("pages", 3, al.OBJET_SELON_LOT)], [("pages", 3, al.OBJET_SELON_LOT)]),
])
def test_limites_chaque_valeur_au_bon_lot(phrase, lot2, lot3):
    assert _par_lot(phrase) == {"2": lot2, "3": lot3}


def test_limite_lot_2_lot_3_par_les_routes(client, auth):
    h = auth["headers"]
    _company(client, h)
    rc = RC.replace("Le mémoire technique compte 3 pages au maximum par lot.",
                    "Lot 2 : mémoire de 10 pages au maximum, lot 3 : 25 000 caractères au maximum.")
    assert rc != RC
    pid = _projet(client, h, rc=rc)
    st = _creer_lots(client, h, pid)
    lim = {n: sorted((x["type"], x["valeur"]) for x in _lot(st, n)["limites"] if x.get("type") != "police")
           for n in ("2", "3")}
    assert lim == {"2": [("pages", 10)], "3": [("caracteres", 25000)]}, lim


# ═══ 5. Courrier à plusieurs lots ════════════════════════════════════════════════════════════════

S_AGISSANT = ["Objet : rejet de vos offres - lots 2 et 3", "Madame, Monsieur,",
              "S'agissant du lot 2, votre offre a obtenu les notes suivantes.", "Valeur technique : 30 / 60",
              "Prix : 35 / 40", "S'agissant du lot 3, votre offre a obtenu les notes suivantes.",
              "Valeur technique : 40 / 60", "Prix : 38 / 40"]
AUTRE_LOT = ["Objet : rejet de votre offre pour le lot 2 Couverture", "Madame, Monsieur,",
             "Votre offre pour le lot 2 a été jugée irrégulière et n'a pas été notée.",
             "Pour le lot 3, vous trouverez ci-dessous vos notes.", "Valeur technique : 40 / 60", "Prix : 30 / 40"]
TITRE_PUIS_AUTRE = ["Objet : rejet de vos offres", "Lot 2 – Couverture", "Votre offre a été jugée irrégulière.",
                    "Pour le lot 3, vos notes sont les suivantes.", "Valeur technique : 40 / 60", "Prix : 30 / 40"]
PHRASE_AUTRE_LOT = ["Objet : rejet de votre offre pour le lot 2", "Madame, Monsieur,",
                    "Votre offre pour le lot 3 a été classée en deuxième position.", "Valeur technique : 40 / 60",
                    "Prix : 30 / 40"]
CRITS = [{"cle": f"L{n}-{k}", "critere": c, "parent": "", "lot": n, "lot_libelle": f"Lot {n}"}
         for n in ("2", "3") for k, c in (("c1", "Valeur technique"), ("c2", "Prix"))]


def _notes(lignes):
    return {k: v["note"] for k, v in cn.lire_courrier("\n".join(lignes), CRITS)["propositions"].items()}


def test_courrier_annonce_en_debut_de_ligne_ouvre_le_lot():
    assert cn.lots_des_lignes(S_AGISSANT, ["2", "3"]) == [None, None, "2", "2", "2", "3", "3", "3"]
    assert _notes(S_AGISSANT) == {"L2-c1": "30", "L2-c2": "35", "L3-c1": "40", "L3-c2": "38"}
    assert cn.lots_des_lignes(AUTRE_LOT, ["2", "3"]) == ["2", "2", "2", "3", "3", "3"]
    assert _notes(AUTRE_LOT) == {"L3-c1": "40", "L3-c2": "30"}
    assert cn.lots_des_lignes(TITRE_PUIS_AUTRE, ["2", "3"]) == [None, "2", "2", "3", "3", "3"]
    assert _notes(TITRE_PUIS_AUTRE) == {"L3-c1": "40", "L3-c2": "30"}


def test_courrier_une_phrase_sur_un_autre_lot_laisse_la_suite_sans_lot():
    assert cn.lots_des_lignes(PHRASE_AUTRE_LOT, ["2", "3"]) == ["2", "2", None, None, None]
    assert _notes(PHRASE_AUTRE_LOT) == {}
    segs = cn.segments_par_lot("\n".join(PHRASE_AUTRE_LOT), ["2", "3"])
    assert "Valeur technique : 40 / 60" not in segs.get("2", "") and "3" not in segs
    # Un extrait de l'IA pris hors de la partie de SON lot est refusé.
    t = "\n".join(PHRASE_AUTRE_LOT)
    v = cn.valider_ia({"id": "L2-c1", "note": "40", "note_max": "60", "extrait": "Valeur technique : 40 / 60"},
                      t, cn.masquer_coordonnees(t), {"L2-c1"}, lot_de={"L2-c1": "2"},
                      segments=(cn.segments_par_lot(t, ["2", "3"]),
                                cn.segments_par_lot(cn.masquer_coordonnees(t), ["2", "3"])))
    assert not v or not v.get("note"), v
    # Et toujours : un autre lot renvoyé à un autre courrier ne change rien (première contre-relecture).
    lignes = ["Objet : Restructuration de l'école - lot 3 Étanchéité des toitures-terrasses", "Madame, Monsieur,",
              "Votre offre pour le lot 2 fait l'objet d'un courrier séparé.", "Valeur technique : 31 / 60",
              "Prix : 35 / 40"]
    assert cn.lots_des_lignes(lignes, ["2", "3"]) == ["3"] * 5
    # « Par ailleurs » n'est pas un renvoi à un autre courrier : la note du lot 3 n'est jamais rangée sous le lot 2.
    lignes = ["Objet : rejet de votre offre pour le lot 2", "Valeur technique : 30 / 60",
              "Par ailleurs, votre offre pour le lot 3 a obtenu Valeur technique : 40 / 60"]
    assert cn.lots_des_lignes(lignes, ["2", "3"]) == ["2", "2", None]
    assert _notes(lignes) == {"L2-c1": "30"}


def test_message_lot_inconnu_ne_dit_pas_qu_aucune_ligne_ne_cite_un_lot():
    assert "aucune ligne ne cite" not in cn.MSG_LOT_INCONNU
    assert "« Lot 2 : … »" in cn.MSG_LOT_INCONNU and "« Pour le lot 2, … »" in cn.MSG_LOT_INCONNU


def test_courrier_s_agissant_du_lot_par_les_routes(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h, rc=RC_PROC)
    _tout_ecrire(client, h, pid, _creer_lots(client, h, pid))
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    courrier = "\n".join(S_AGISSANT)
    props = client.post(f"/api/carnet/{pid}/lire", headers=h, json={"courrier": courrier}).json()["propositions"]
    vt2, px2 = _cle(e, "2", "Valeur technique"), _cle(e, "2", "Prix")
    vt3, px3 = _cle(e, "3", "Valeur technique"), _cle(e, "3", "Prix")
    assert {k: v["note"] for k, v in props.items()} == {vt2: "30", px2: "35", vt3: "40", px3: "38"}
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": _form_avec(e, props), "rev": e["rev"],
                                                                "courrier": courrier})
    assert r.status_code == 200, r.text
    lues = {x["cle"]: x["origine"] for x in r.json()["notes"]["lignes"] if x["cle"] in (vt2, px2, vt3, px3)}
    assert lues == {vt2: "courrier", px2: "courrier", vt3: "courrier", px3: "courrier"}
    # La lecture avec l'IA part (le courrier dit à quel lot se rapporte chaque note) et reste contrôlée lot par lot.
    fake = fake_llm(_reponse_ia([{"id": vt3, "note": "40", "note_max": "60", "extrait": "Valeur technique : 40 / 60"},
                                 {"id": vt2, "note": "40", "note_max": "60", "extrait": "Valeur technique : 40 / 60"}]))
    r = client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": courrier})
    assert r.status_code == 200, r.text
    assert len(fake.calls) == 1 and set(r.json()["propositions"]) == {vt3} and r.json()["refusees"] == 1


# ═══ 6. Grille par lot : un titre de lot en ligne après un tiret ═════════════════════════════════

CRIT = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": ""},
        {"critere": "Prix", "ponderation": "40 %", "extrait": ""}]


def _grilles(zone):
    T = "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n" + zone
    gs = al.grilles_par_lot(gn.build_grille({"criteres_attribution": CRIT}, T), T, ["2", "3"])
    return {n: (al.grille_out(gs[n])["mode"], [(x["critere"], x["poids"]) for x in al.grille_out(gs[n])["lignes"]])
            for n in ("2", "3")}


@pytest.mark.parametrize("zone", [
    "Lot 2 : Valeur technique 60 %, Prix 40 % - Lot 3 : Valeur technique 40 %, Prix 60 %.\n",
    "Lot 2 – Couverture : Valeur technique 60 %, Prix 40 % – Lot 3 – Étanchéité : Valeur technique 40 %, Prix 60 %.\n",
])
def test_grille_titre_de_lot_en_ligne_apres_un_tiret_reste_lue(zone):
    assert _grilles(zone) == {"2": (al.MODE_PROPRE, [("Valeur technique", "60 %"), ("Prix", "40 %")]),
                              "3": (al.MODE_PROPRE, [("Valeur technique", "40 %"), ("Prix", "60 %")])}


def test_grille_poids_avant_le_lot_avec_un_tiret_reste_illisible():
    g = _grilles("Valeur technique : 60 % - lot 2 ; 40 % - lot 3.\nPrix : 40 % - lot 2 ; 60 % - lot 3.\n")
    for n in ("2", "3"):
        assert g[n][0] == al.MODE_ILLISIBLE and all(p == "" for _c, p in g[n][1]), g
