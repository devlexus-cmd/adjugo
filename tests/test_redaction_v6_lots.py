"""
Rédaction, vague 6 — J « Plusieurs lots, un seul effort » (étude rédaction § 6.10 ; contrat docs/REDACTION_V6.md, J).

Pour un marché alloti auquel l'entreprise répond sur deux lots ou plus :
  • les lots sont repérés SANS IA dans le règlement (lignes, énumération), un lot proposé par l'analyse n'est gardé
    que retrouvé mot pour mot à côté de son numéro, un lot ajouté par l'utilisateur est dit comme tel ;
  • la grille de CHAQUE lot vient de SA phrase du règlement (poids propres au lot, sinon la grille du règlement pour
    tous, et un tableau illisible ne donne jamais de poids deviné) ;
  • des parties COMMUNES (une seule partie, un seul texte, une seule version : modifiée, elle change partout) et des
    parties PROPRES À CHAQUE LOT ; l'utilisateur change la portée d'une partie ;
  • UN EXPORT PAR LOT (Word, PDF), nommé comme le règlement l'exige, sinon avec le numéro et l'intitulé du lot ;
    limites de pages contrôlées par lot ; dérogation par lot ; dossier commun avec un fichier par lot ;
  • en groupement, « Qui écrit quoi » proposé sans IA d'après le lot déclaré par chaque membre ;
  • marché à un seul lot : RIEN ne change.
IA simulée, aucun réseau.
"""
import io
import json
import zipfile

import pytest

from app.services import atelier as at
from app.services import atelier_lots as al
from app.services import atelier_plan as ap
from app.services import grille_notation as gn
from app.services import llm
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _ecrire, _etat
from tests.test_redaction_v2_atelier import _projet as _projet_un_lot

RC = """REGLEMENT DE LA CONSULTATION
Article 1 - Objet et allotissement
Restructuration de l'école maternelle Les Hirondelles.
Le marché est décomposé en 3 lots :
Lot 1 : Désamiantage
Lot 2 : Couverture et zinguerie
Lot 3 : Étanchéité des toitures-terrasses
Article 5 - Contenu de l'offre
Chaque candidat remet un mémoire technique par lot.
Le mémoire technique compte 3 pages au maximum par lot.
Chaque mémoire est remis dans un fichier nommé « Lot X - Mémoire technique - Nom du candidat ».
Article 7 - Jugement des offres
Pour chacun des lots, les offres sont jugées sur les critères suivants :
1. Valeur technique : 60 %
1.1 Méthodologie d'exécution : 30 %
1.2 Moyens humains et matériels affectés au lot : 20 %
1.3 Gestion environnementale du chantier : 10 %
2. Prix : 40 %
"""
CRITERES = [
    {"critere": "Valeur technique", "ponderation": "60 %", "extrait": "1. Valeur technique : 60 %",
     "sous_criteres": [
         {"critere": "Méthodologie d'exécution", "ponderation": "30 %", "extrait": "1.1 Méthodologie d'exécution : 30 %"},
         {"critere": "Moyens humains et matériels affectés au lot", "ponderation": "20 %",
          "extrait": "1.2 Moyens humains et matériels affectés au lot : 20 %"},
         {"critere": "Gestion environnementale du chantier", "ponderation": "10 %",
          "extrait": "1.3 Gestion environnementale du chantier : 10 %"}]},
    {"critere": "Prix", "ponderation": "40 %", "extrait": "2. Prix : 40 %"}]
TEXTE_COMMUN = "Le chantier trie ses déchets sur place et limite les nuisances pour l'école."
TEXTE_COMMUN_2 = "Le chantier trie ses déchets sur place, limite le bruit et protège les abords de l'école."


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def _projet(client, h, rc=RC, criteres=None, name="Restructuration de l'école maternelle", allotissement=""):
    """Un marché alloti, son dossier (règlement) importé et analysé (grille contrôlée sans IA)."""
    r = client.post("/api/projects/", headers=h, json={"name": name, "client": "Ville de Trémorvan"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    from app.models import Project
    from app.services.analysis import extract_dce_text
    from app.services.dossier import save_to_dossier
    db = _db()
    try:
        p = db.get(Project, pid)
        content = _zip({"01_Reglement_de_la_consultation.txt": rc})
        text, pieces = extract_dce_text("DCE.zip", content, max_chars=120000, with_pieces=True)
        det = {"intitule_marche": name, "acheteur": "Ville de Trémorvan",
               "criteres_attribution": criteres if criteres is not None else CRITERES,
               "allotissement": allotissement,
               "pieces_requises": [{"nom": "Mémoire technique", "disponible": False}]}
        det["grille_notation"] = gn.build_grille(det, text, pieces=pieces)
        p.ai_analysis = {"summary": "École", "dce_available": True, "dce_excerpt": text[:30000], "details": det}
        save_to_dossier(db, p.user_id, pid, "DCE", "DCE.zip", content, "application/zip")
        db.commit()
    finally:
        db.close()
    return pid


def _creer_lots(client, h, pid, lots=("2", "3"), **extra):
    r = client.post(f"/api/atelier/{pid}", headers=h, json=dict({"lots": list(lots)}, **extra))
    assert r.status_code == 201, r.text
    return r.json()


def _par(st, intitule, lot):
    return next(s for s in st["sections"] if s["intitule"].startswith(intitule) and s["lot"] == lot)


def _valider(client, h, pid, sec):
    r = client.post(f"/api/atelier/{pid}/sections/{sec['id']}/valider", headers=h,
                    json={"version_id": sec["version_courante"]["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def _docx_texte(data: bytes) -> str:
    from docx import Document
    d = Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs)


def _lot(st, n):
    return next(x for x in st["lots"]["liste"] if x["numero"] == n)


def _tout_ecrire(client, h, pid, st, sauf=()):
    """Un texte simple (sans fait à relire) dans chaque partie, puis chaque partie validée."""
    for s in list(st["sections"]):
        if s["id"] in sauf:
            continue
        txt = TEXTE_COMMUN if s["commune"] else f"Notre méthode pour cette partie du lot {s['lot']} suit le phasage."
        s2 = _ecrire(client, h, pid, s, txt)
        _valider(client, h, pid, s2)
    return _etat(client, h, pid)


# ═══ 1. Les lots du marché, repérés sans IA ═══════════════════════════════════════════════════════

def test_lots_reperes_dans_le_reglement_avec_leur_phrase():
    T = "=== RC.pdf ===\n" + RC
    r = al.reperer(T, {})
    assert r["alloti"] is True and r["annonce"] == 3
    assert [(x["numero"], x["intitule"]) for x in r["lots"]] == [
        ("1", "Désamiantage"), ("2", "Couverture et zinguerie"), ("3", "Étanchéité des toitures-terrasses")]
    assert all(x["origine"] == "reglement" and x["phrase"] and "Règlement" in x["source"] for x in r["lots"])
    from app.services.analysis import citation_guard
    assert all(citation_guard(T, x["phrase"], min_len=4) for x in r["lots"])
    # Énumération dans une phrase (« lot 1, … ; lot 2, … »), intitulés tels qu'écrits.
    K = ("=== 01 - Règlement de la consultation.pdf ===\nRÈGLEMENT DE LA CONSULTATION\nLes travaux sont répartis en "
         "trois lots : lot 1, désamiantage et retrait d'amiante ; lot 2, isolation thermique et rénovation "
         "énergétique ; lot 3, gros œuvre et étanchéité.")
    r = al.reperer(K, {})
    assert [x["intitule"] for x in r["lots"]] == ["Désamiantage et retrait d'amiante",
                                                   "Isolation thermique et rénovation énergétique",
                                                   "Gros œuvre et étanchéité"]
    # Ni un poste de prix, ni une phrase, ni un poids ne sont pris pour un lot.
    D = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nLe lot 1 sera attribué en premier.\nLot 2 : 40 % prix\n"
         "=== DPGF.pdf ===\nDECOMPOSITION DU PRIX GLOBAL\nLot 1 — Installation du chantier\nLot 2 — Retrait\n")
    assert al.reperer(D, {})["lots"] == []


def test_lot_de_l_analyse_garde_seulement_s_il_est_retrouve_mot_pour_mot():
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nLe marché comprend deux lots. Le lot n° 1 porte sur la "
         "charpente bois. Le lot n° 2 porte sur la couverture en ardoise.\n")
    r = al.reperer(T, {"allotissement": "Lot 1 : charpente bois ; Lot 2 : couverture en ardoise ; Lot 3 : peinture"})
    assert [(x["numero"], x["intitule"], x["origine"]) for x in r["lots"]] == [
        ("1", "Charpente bois", "analyse"), ("2", "Couverture en ardoise", "analyse")]       # le lot 3 n'est pas écrit
    u = al.reperer("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nLe marché est passé en lot unique.\n", {})
    assert u["alloti"] is False and "lot unique" in u["unique"] and u["message"] == ""


def test_lots_choisis_controles_et_lot_indique_par_l_utilisateur():
    reperes = al.reperer("=== RC.pdf ===\n" + RC, {})["lots"]
    lots = al.choisir(reperes, ["3", "02"], [{"numero": "4", "intitule": "Peinture intérieure"}])
    assert [(x["numero"], x["origine"]) for x in lots] == [("2", "reglement"), ("3", "reglement"), ("4", "utilisateur")]
    with pytest.raises(al.LotsInvalides):
        al.choisir(reperes, ["9"])
    with pytest.raises(al.LotsInvalides):
        al.choisir(reperes, ["2"], [{"numero": "2", "intitule": "Doublon"}])
    with pytest.raises(al.LotsInvalides):
        al.choisir(reperes, [], [{"numero": "5", "intitule": ""}])


# ═══ 2. La grille de chaque lot, depuis SA phrase ═══════════════════════════════════════════════════

def _grille(T, criteres):
    return gn.build_grille({"criteres_attribution": criteres}, T)


def test_grille_commune_a_tous_les_lots_dit_comme_tel():
    T = "=== RC.pdf ===\n" + RC
    gs = al.grilles_par_lot(_grille(T, CRITERES), T, ["2", "3"])
    for n in ("2", "3"):
        o = al.grille_out(gs[n])
        assert o["mode"] == "commune" and "vaut pour ce lot" in o["message"]
        assert o["phrase"] == "Pour chacun des lots, les offres sont jugées sur les critères suivants :"
        assert [(x["critere"], x["poids"]) for x in o["lignes"]] == [("Valeur technique", "60 %"), ("Prix", "40 %")]
        assert o["controle_total"]["statut"] == "ok"


def test_grille_propre_a_chaque_lot_poids_et_phrase_du_lot():
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\nLes offres sont jugées sur "
         "les critères suivants.\nPour le lot 2 : valeur technique 60 % ; prix 40 %.\n"
         "Pour le lot 3 : valeur technique 40 % ; prix 60 %.\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "valeur technique 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "prix 40 %"}]
    gs = al.grilles_par_lot(_grille(T, crit), T, ["2", "3"])
    o2, o3 = al.grille_out(gs["2"]), al.grille_out(gs["3"])
    assert o2["mode"] == o3["mode"] == "propre"
    assert [(x["critere"], x["poids"]) for x in o2["lignes"]] == [("Valeur technique", "60 %"), ("Prix", "40 %")]
    assert [(x["critere"], x["poids"]) for x in o3["lignes"]] == [("Valeur technique", "40 %"), ("Prix", "60 %")]
    assert o3["lignes"][0]["phrase"] == "Pour le lot 3 : valeur technique 40 % ; prix 60 %."
    from app.services.analysis import citation_guard
    assert citation_guard(T, o3["lignes"][0]["phrase"])
    # Le plan du lot 3 porte SES poids (jamais ceux du lot 2).
    p = al.construire_plan({"details": {"grille_notation": _grille(T, crit)}}, al.choisir(
        [{"numero": "2", "intitule": "Couverture"}, {"numero": "3", "intitule": "Étanchéité"}], ["2", "3"]), T,
        al.pieces_du_texte(T))
    assert {s["lot"]: s["poids"] for s in p["sections"] if s["critere"] == "Valeur technique"
            and s["intitule"] == "Compréhension du besoin"} == {"2": "60 %", "3": "40 %"}


def test_tableau_de_poids_par_lot_illisible_aucun_poids_devine():
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
         "Critère | Lot 1 | Lot 2 | Lot 3\nValeur technique | 60 % | 50 % | 40 %\nPrix | 40 % | 50 % | 60 %\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": ""},
            {"critere": "Prix", "ponderation": "40 %", "extrait": ""}]
    gs = al.grilles_par_lot(_grille(T, crit), T, ["2", "3"])
    for n in ("2", "3"):
        o = al.grille_out(gs[n])
        assert o["mode"] == "illisible" and "sans poids" in o["message"]
        assert all(x["poids"] == "" for x in o["lignes"])
        assert all(x["dans_le_plan"] for x in o["lignes"])


def test_critere_absent_de_la_partie_du_lot_n_entre_pas_dans_son_plan():
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n"
         "Pour le lot 2 : valeur technique 60 % ; délai d'exécution 10 % ; prix 30 %.\n"
         "Pour le lot 3 : valeur technique 50 % ; prix 50 %.\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "valeur technique 60 %"},
            {"critere": "Délai d'exécution", "ponderation": "10 %", "extrait": "délai d'exécution 10 %"},
            {"critere": "Prix", "ponderation": "30 %", "extrait": "prix 30 %"}]
    gs = al.grilles_par_lot(_grille(T, crit), T, ["2", "3"])
    o3 = al.grille_out(gs["3"])
    d = next(x for x in o3["lignes"] if x["critere"] == "Délai d'exécution")
    assert d["statut"] == "a_verifier" and not d["dans_le_plan"] and "propre à ce lot" in d["message"]
    assert next(x for x in al.grille_out(gs["2"])["lignes"] if x["critere"] == "Délai d'exécution")["poids"] == "10 %"


def test_liste_des_lots_dans_la_zone_d_attribution_n_est_pas_une_grille_par_lot():
    """« Le marché est attribué à l'offre économiquement la plus avantageuse » ouvre une zone de critères AVANT la
    liste des lots : ces lignes ne parlent d'aucun critère, la grille reste commune à tous les lots."""
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 1 - Objet\nLe marché est attribué à l'offre "
         "économiquement la plus avantageuse. Il est réparti en lots :\nLot 1 : Désamiantage\nLot 2 : Couverture\n"
         "Lot 3 : Étanchéité\nLot 4 : Portes et fenêtres\nArticle 7 - Jugement des offres\nValeur technique : 60 %\n"
         "Prix : 40 %\n")
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "Valeur technique : 60 %"},
            {"critere": "Prix", "ponderation": "40 %", "extrait": "Prix : 40 %"}]
    assert [x["intitule"] for x in al.reperer(T, {})["lots"]] == ["Désamiantage", "Couverture", "Étanchéité",
                                                                   "Portes et fenêtres"]
    gs = al.grilles_par_lot(_grille(T, crit), T, ["2", "3"])
    assert {n: al.grille_out(g)["mode"] for n, g in gs.items()} == {"2": "commune", "3": "commune"}
    assert [x["poids"] for x in al.grille_out(gs["3"])["lignes"]] == ["60 %", "40 %"]


def test_limites_du_lot_la_limite_propre_remplace_la_generale():
    lims = [{"type": "pages", "valeur": 8, "phrase": "Le mémoire technique compte 8 pages au maximum par lot.", "objet": ""},
            {"type": "pages", "valeur": 5, "phrase": "Pour le lot 3, le mémoire technique compte 5 pages au maximum.",
             "objet": ""},
            {"type": "police", "police": "Arial", "taille": 11, "phrase": "Police Arial 11.", "objet": ""}]
    assert [x["valeur"] for x in al.limites_du_lot(lims, "2", ["2", "3"]) if x["type"] == "pages"] == [8]
    assert [x["valeur"] for x in al.limites_du_lot(lims, "3", ["2", "3"]) if x["type"] == "pages"] == [5]
    assert any(x["type"] == "police" for x in al.limites_du_lot(lims, "3", ["2", "3"]))
    # Une limite propre à un lot hors du dossier (lot 1) ne vaut jamais pour les lots choisis.
    l1 = lims + [{"type": "mots", "valeur": 900, "phrase": "Pour le lot 1, la note compte 900 mots au plus.", "objet": ""}]
    assert not [x for x in al.limites_du_lot(l1, "2", ["2", "3"]) if x["type"] == "mots"]


# ═══ 3. Commune ou propre à chaque lot ; nom des fichiers ═══════════════════════════════════════════

def test_regle_commune_ou_propre_a_chaque_lot():
    communes = ["Présentation de l'entreprise", "Qualité, sécurité et environnement", "Gestion environnementale du chantier",
                "Démarche environnementale", "Présentation du groupement", "Insertion sociale"]
    propres = ["Méthodologie d'exécution", "Moyens humains", "Moyens matériels", "Planning et délais",
               "Organisation du chantier en site occupé et sécurité", "Compréhension du besoin", "Références"]
    assert all(al.est_commune(x) for x in communes), [x for x in communes if not al.est_commune(x)]
    assert not any(al.est_commune(x) for x in propres), [x for x in propres if al.est_commune(x)]


def test_nom_du_fichier_comme_le_reglement_l_exige_sinon_numero_et_intitule():
    regle = al.nommage("=== RC.pdf ===\n" + RC)
    assert regle["modele"] == "Lot X - Mémoire technique - Nom du candidat"
    assert regle["phrase"].startswith("Chaque mémoire est remis dans un fichier nommé")
    lot = {"numero": "2", "intitule": "Couverture et zinguerie"}
    n = al.nom_du_lot(lot, "Mémoire technique", "Bâtiment de l'Ouest", regle)
    assert n["stem"] == "Lot 2 - Mémoire technique - Bâtiment de l'Ouest" and n["selon_reglement"] is True
    assert al.nom_du_lot(lot, "Mémoire technique", "", None)["stem"] == "Mémoire technique - Lot 2 - Couverture et zinguerie"
    z = al.nom_du_lot(lot, "Mémoire technique", "X", {"modele": "MT_LOTxx_[SIRET]", "phrase": "p", "source": "s"})
    assert z["stem"] == "Mémoire technique - Lot 2 - Couverture et zinguerie" and "ne sait pas compléter" in z["message"]
    zz = al.nom_du_lot(lot, "Mémoire technique", "X", {"modele": "MT_LOTxx", "phrase": "p", "source": "s"})
    assert zz["stem"] == "MT_LOT02" and zz["selon_reglement"]
    sans_nom = al.nom_du_lot(lot, "Mémoire technique", "", regle)
    assert sans_nom["selon_reglement"] is False and "nom de votre entreprise" in sans_nom["message"]


# ═══ 4. Deux lots : le dossier, une partie commune, un export par lot ═══════════════════════════════

def test_deux_lots_parties_communes_et_propres(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    prop = client.get(f"/api/atelier/{pid}", headers=h).json()["proposition"]
    lm = prop["lots_du_marche"]
    assert lm["alloti"] is True and [x["numero"] for x in lm["lots"]] == ["1", "2", "3"]
    assert "un fichier par lot" in lm["message"] and lm["choisis"] == []
    assert all("lot" not in s or not s.get("lot") for s in prop["sections"])          # un seul dossier par défaut
    # Prévisualisation, rien n'est enregistré.
    pr = client.get(f"/api/atelier/{pid}?lots=2,3", headers=h).json()["proposition"]
    assert [(s["lot"], s["intitule"]) for s in pr["sections"]] == [
        ("2", "Méthodologie d'exécution"), ("2", "Moyens humains et matériels affectés au lot"),
        ("3", "Méthodologie d'exécution"), ("3", "Moyens humains et matériels affectés au lot"),
        ("", "Gestion environnementale du chantier")]
    assert "1 partie commune" in pr["message"] and pr["lots_du_marche"]["choisis"] == ["2", "3"]
    st = _creer_lots(client, h, pid)
    assert st["lots"]["actif"] is True and [x["numero"] for x in st["lots"]["liste"]] == ["2", "3"]
    assert [(s["lot"], s["numero_affiche"], s["commune"]) for s in st["sections"]] == [
        ("2", "1.1", False), ("2", "1.2", False), ("3", "1.1", False), ("3", "1.2", False), ("", "1.3", True)]
    assert _par(st, "Méthodologie", "3")["lot_libelle"] == "Lot 3 — Étanchéité des toitures-terrasses"
    assert _par(st, "Méthodologie", "3")["titre"] == "1.1 Méthodologie d'exécution (lot 3)"
    l2 = _lot(st, "2")
    assert l2["parties_communes"] == 1 and l2["parties_propres"] == 2
    assert l2["export"]["nom_fichier_docx"] == "Lot 2 - Mémoire technique - Breizh Couverture.docx"
    assert l2["export"]["nommage"]["selon_reglement"] is True
    assert l2["grille"]["mode"] == "commune" and l2["grille"]["lignes"][0]["poids"] == "60 %"
    assert [(x["type"], x["valeur"], x["lot"]) for x in l2["limites"] if x["portee"] == "document"] == [("pages", 3, "2")]
    # Les mauvais lots sont refusés à la création.
    pid2 = _projet(client, h)
    r = client.post(f"/api/atelier/{pid2}", headers=h, json={"lots": ["2", "9"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lots_invalides"


def test_partie_commune_modifiee_se_repercute_dans_tous_les_lots(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _tout_ecrire(client, h, pid, _creer_lots(client, h, pid))
    com = next(s for s in st["sections"] if s["commune"])
    v1 = com["version_courante"]["id"]
    textes = {}
    for n in ("2", "3"):
        r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": n})
        assert r.status_code == 200, r.text
        textes[n] = _docx_texte(r.content)
        assert TEXTE_COMMUN in textes[n]
        assert f"Lot : {n} — " in textes[n]                             # la page de garde dit le lot
    assert "du lot 3" not in textes["2"] and "du lot 2" not in textes["3"]   # jamais la partie d'un autre lot
    # Une seule modification de la partie commune : même texte, même version dans les deux fichiers.
    com = _ecrire(client, h, pid, com, TEXTE_COMMUN_2)
    v2 = com["version_courante"]["id"]
    assert v2 != v1 and com["statut"] == "a_revalider"
    st = _etat(client, h, pid)
    for n in ("2", "3"):
        nv = [w for w in _lot(st, n)["blocage"]["avertissements"] if w["code"] == "non_valide"]
        assert nv and nv[0]["sections"][0]["section_id"] == com["id"]   # à revalider pour CHAQUE lot
    _valider(client, h, pid, com)
    for n in ("2", "3"):
        r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": n})
        t = _docx_texte(r.content)
        assert TEXTE_COMMUN_2 in t and TEXTE_COMMUN not in t
    from app.models import DossierSection, DossierSectionVersion
    db = _db()
    try:
        assert db.query(DossierSection).filter(DossierSection.dossier_id == st["dossier"]["id"],
                                               DossierSection.intitule.like("Gestion environnementale%")).count() == 1
        assert db.query(DossierSectionVersion).filter(DossierSectionVersion.section_id == com["id"]).count() == 2
    finally:
        db.close()


def test_un_export_par_lot_nom_archive_et_lot_obligatoire(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _tout_ecrire(client, h, pid, _creer_lots(client, h, pid))
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_requis"
    assert [x["numero"] for x in r.json()["detail"]["lots"]] == ["2", "3"]
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "1"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_inconnu"
    noms = []
    for n, fmt in (("2", "docx"), ("2", "pdf"), ("3", "docx")):
        r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": fmt, "lot": n})
        assert r.status_code == 200, r.text
        assert f"Lot {n} - M" in r.headers["content-disposition"] or "Lot%20" in r.headers["content-disposition"]
        noms.append(f"Lot {n} - Mémoire technique - Breizh Couverture.{fmt}")
    st = _etat(client, h, pid)
    assert _lot(st, "2")["dernier_export"]["nom"] == noms[1] and _lot(st, "3")["dernier_export"]["nom"] == noms[2]
    from app.models import Document
    db = _db()
    try:
        ranges = {d.name for d in db.query(Document).filter(Document.project_id == pid,
                                                            Document.folder == "Mémoire technique",
                                                            Document.deleted_at.is_(None)).all()}
    finally:
        db.close()
    assert set(noms) <= ranges


def test_limites_de_pages_controlees_par_lot_et_derogation_par_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    long_ = _par(st, "Méthodologie", "2")
    st = _tout_ecrire(client, h, pid, st, sauf=(long_["id"],))
    long_ = _ecrire(client, h, pid, long_, "\n\n".join(["Notre méthode suit le phasage de la couverture, zone par "
                                                        "zone, avec un contrôle avant chaque fermeture."] * 60))
    _valider(client, h, pid, long_)
    st = _etat(client, h, pid)
    b2, b3 = _lot(st, "2")["blocage"], _lot(st, "3")["blocage"]
    assert [r["code"] for r in b2["raisons"]] == ["limite_depassee"] and b2["peut_exporter"] is False
    assert b2["raisons"][0]["limites"][0]["titre"] == "Dossier du lot 2"
    assert b3["raisons"] == [] and b3["peut_exporter"] is True
    assert st["blocage"]["peut_exporter"] is False and st["blocage"]["par_lot"] is True
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "2"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "export_bloque"
    assert client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "3"}).status_code == 200
    # Dérogation : pour le lot 2 seulement, inscrite au journal.
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h, json={
        "raison": "reduirai_dans_word", "texte": "Je réduis dans Word.", "etat_hash": b2["etat_hash"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_requis"
    r = client.post(f"/api/atelier/{pid}/derogation", headers=h, json={
        "raison": "reduirai_dans_word", "texte": "Je réduis dans Word.", "etat_hash": b2["etat_hash"], "lot": "2"})
    assert r.status_code == 200, r.text
    assert r.json()["blocage"]["derogation"]["avertissement"] == at.MSG_IRREGULIERE and r.json()["lot"] == "2"
    st = _etat(client, h, pid)
    assert _lot(st, "2")["blocage"]["peut_exporter"] is True and _lot(st, "3")["blocage"]["derogation"] is None
    assert client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "2"}).status_code == 200
    from app.models import AuditLog
    db = _db()
    try:
        a = db.query(AuditLog).filter(AuditLog.project_id == pid, AuditLog.action == "atelier.derogation_export").one()
        assert a.meta["lot"] == "2"
    finally:
        db.close()


def test_portee_d_une_partie_commune_ou_propre_a_chaque_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    com = next(s for s in st["sections"] if s["commune"])
    com = _ecrire(client, h, pid, com, TEXTE_COMMUN)
    # Commune → propre à chaque lot : elle garde son texte pour le premier lot, une partie vide pour l'autre.
    r = client.put(f"/api/atelier/{pid}/sections/{com['id']}/portee", headers=h, json={"commune": False})
    assert r.status_code == 200, r.text
    st = r.json()
    env = [s for s in st["sections"] if s["intitule"].startswith("Gestion environnementale")]
    assert [(s["lot"], bool(s["version_courante"])) for s in env] == [("2", True), ("3", False)]
    assert [s["numero_affiche"] for s in env] == ["1.3", "1.3"]
    # Propre → commune : celle-ci garde son texte ; celle de l'autre lot, avec du texte, demande confirmation.
    e3 = _ecrire(client, h, pid, env[1], "Texte écrit pour l'environnement du lot trois.")
    r = client.put(f"/api/atelier/{pid}/sections/{env[0]['id']}/portee", headers=h, json={"commune": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "portee_a_confirmer"
    r = client.put(f"/api/atelier/{pid}/sections/{env[0]['id']}/portee", headers=h,
                   json={"commune": True, "remplacer": True})
    assert r.status_code == 200, r.text
    st = r.json()
    env = [s for s in st["sections"] if s["intitule"].startswith("Gestion environnementale")]
    assert [(s["lot"], s["commune"]) for s in env] == [("", True)]
    assert env[0]["version_courante"]["texte"] == TEXTE_COMMUN
    retiree = next(x for x in st["sections_retirees"] if x["id"] == e3["id"])
    assert retiree["lot_libelle"] == "Lot 3 — Étanchéité des toitures-terrasses"       # remettable, rien de perdu
    r = client.post(f"/api/atelier/{pid}/sections/{e3['id']}/remettre", headers=h)
    assert r.status_code == 200 and r.json()["lot"] == "3"
    # Un dossier à un seul lot : la portée ne se change pas.
    pid1 = _projet_un_lot(client, h)
    s1 = _creer(client, h, pid1)["sections"][0]
    r = client.put(f"/api/atelier/{pid1}/sections/{s1['id']}/portee", headers=h, json={"commune": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "un_seul_lot"


def test_changer_les_lots_du_dossier_avec_confirmation(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    _ecrire(client, h, pid, st["sections"][0], "Un texte écrit.")
    r = client.put(f"/api/atelier/{pid}/lots", headers=h, json={"lots": ["1", "2", "3"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "plan_remplacement_a_confirmer"
    r = client.put(f"/api/atelier/{pid}/lots", headers=h, json={"lots": ["1", "2", "3"], "remplacer": True})
    assert r.status_code == 200, r.text
    st = r.json()
    assert [x["numero"] for x in st["lots"]["liste"]] == ["1", "2", "3"]
    assert sorted({s["lot"] for s in st["sections"]}) == ["", "1", "2", "3"]
    assert st["sections_retirees"]                                       # rien n'est supprimé
    r = client.put(f"/api/atelier/{pid}/lots", headers=h, json={"lots": ["1", "2", "3"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "rien_a_changer"
    # Retour à un seul dossier (un seul lot choisi) : plus aucune partie de lot.
    r = client.put(f"/api/atelier/{pid}/lots", headers=h, json={"lots": [], "remplacer": True})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["lots"]["actif"] is False and all(s["lot"] == "" for s in st["sections"])
    assert client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "2"}).json()[
        "detail"]["code"] == "lot_inconnu"


def test_ajouter_une_partie_a_un_lot_ou_commune(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Références du lot", "lot": "3"})
    assert r.status_code == 201 and r.json()["lot"] == "3"
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Présentation de l'entreprise",
                                                                    "lot": ""})
    assert r.status_code == 201 and r.json()["lot"] == "" and r.json()["commune"] is True
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Hors dossier", "lot": "1"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_inconnu"
    st = _etat(client, h, pid)
    assert _lot(st, "2")["parties_communes"] == 2 and _lot(st, "3")["parties_propres"] == 3


def test_dossier_commun_un_fichier_par_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    long_ = _par(st, "Méthodologie", "2")
    _tout_ecrire(client, h, pid, st, sauf=(long_["id"],))
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        out = at.dossier_commun(db, p, p.user_id)
    finally:
        db.close()
    assert sorted(n for n, _b in out["files"].values()) == [
        "Lot 3 - Mémoire technique - Breizh Couverture.docx", "Lot 3 - Mémoire technique - Breizh Couverture.pdf"]
    assert any(w.startswith("BLOQUANT — Lot 2 — Couverture et zinguerie : dossier de présentation non joint")
               for w in out["warnings"])
    assert "# Lot 2 — Couverture et zinguerie" in out["markdown"] and "# Lot 3 —" in out["markdown"]


# ═══ 5. La rédaction : la partie d'un lot, la partie commune (IA simulée) ═══════════════════════════

def test_redaction_dit_a_l_ia_le_lot_de_la_partie_ou_qu_elle_est_commune(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    fake = fake_llm(lambda kw: ("Notre méthode suit le phasage du chantier.", "end_turn"))
    p3 = _par(st, "Méthodologie", "3")
    com = next(s for s in st["sections"] if s["commune"])
    for s in (p3, com):
        r = client.post(f"/api/atelier/{pid}/sections/{s['id']}/rediger", headers=h, json={})
        assert r.status_code == 202, r.text
        _attendre(client, h, pid, r.json()["tache"]["id"])
    envoye = [llm._flatten_content(m.get("content")) for k in fake.calls for m in k.get("messages") or []]
    lot3 = next(x for x in envoye if "Méthodologie d'exécution" in x and "PARTIE À RÉDIGER" in x)
    assert "CETTE PARTIE CONCERNE SEULEMENT LE LOT 3 (Étanchéité des toitures-terrasses)" in lot3
    assert "Moyens humains et matériels affectés au lot" in lot3                 # les parties de SON lot
    commune = next(x for x in envoye if "PARTIE À RÉDIGER : Gestion environnementale" in x)
    assert "CETTE PARTIE EST COMMUNE À TOUS LES LOTS DU DOSSIER" in commune
    # Une seule analyse pour tout le dossier, tous lots compris.
    st = _etat(client, h, pid)
    assert st["quota"]["analyse_debitee"] is True and st["quota"]["regenerations_utilisees"] == 0


# ═══ 6. Groupement : « Qui écrit quoi » d'après les lots ════════════════════════════════════════════

def test_groupement_repartition_proposee_d_apres_le_lot_de_chaque_membre(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"recipient": "", "company_name": "Étanche Ouest"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    v = client.get(f"/api/invite/{tok}/contribution").json()["version"]
    r = client.put(f"/api/invite/{tok}/contribution", json={"version": v, "company_name": "Étanche Ouest",
                                                           "lot": "Lot 3 : étanchéité des toitures-terrasses",
                                                           "siret": "55566677700012"})
    assert r.status_code == 200, r.text
    st = _creer_lots(client, h, pid)
    r = client.post(f"/api/atelier/{pid}/repartition", headers=h, json={})
    assert r.status_code == 200, r.text
    rep = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    lignes = {(x["intitule"], x.get("lot")): x for x in rep["sections"] if not x.get("genere")}
    m3 = lignes[("Méthodologie d'exécution", "3")]
    assert m3["proposition"]["redacteur"] == "partenaire" and m3["proposition"]["nom"] == "Étanche Ouest"
    assert "celle du lot 3" in m3["proposition"]["message"] and m3["redacteur"]["nom"] == "Étanche Ouest"
    m2 = lignes[("Méthodologie d'exécution", "2")]
    assert m2["proposition"]["redacteur"] == "chef_de_file" and "aucun partenaire n'a déclaré le lot 2" in \
        m2["proposition"]["message"]
    assert lignes[("Gestion environnementale du chantier", "")]["redacteur"]["type"] == "chef_de_file"
    assert m3["lot_libelle"] == "Lot 3 — Étanchéité des toitures-terrasses" and m3["commune"] is False
    # Le partenaire voit le lot de SES parties (public : le règlement le nomme), rien de plus.
    r = client.post(f"/api/invite/{tok}/redaction/espace", json={})
    hk = {"X-Adjugo-Espace": r.json()["cle"]}
    vue = client.get(f"/api/invite/{tok}/redaction", headers=hk).json()
    assert {(p["intitule"], p["lot"]) for p in vue["parties"]} == {("Méthodologie d'exécution", "3"),
                                                                   ("Moyens humains et matériels affectés au lot", "3")}


# ═══ 7. Marché à un seul lot : rien ne change ═══════════════════════════════════════════════════════

def test_marche_a_un_seul_lot_rien_ne_change(client, auth):
    h = auth["headers"]
    pid = _projet_un_lot(client, h)
    prop = client.get(f"/api/atelier/{pid}", headers=h).json()["proposition"]
    assert prop["lots_du_marche"]["alloti"] is False and "lots" not in prop
    st = _creer(client, h, pid)
    assert st["lots"]["actif"] is False and st["lots"]["liste"] == []
    assert all(s["lot"] == "" and s["commune"] is False and s["lot_libelle"] == "" for s in st["sections"])
    assert [s["titre"] for s in st["sections"]] == ["1.1 Encadrement du chantier", "1.2 Équipe d'exécution",
                                                    "2. Méthodologie", "3. Démarche environnementale"]
    assert st["compteur"]["total"] is not None and st["export"]["nom_fichier_docx"] == "Mémoire justificatif.docx"
    from app.models import DossierPresentation
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).one()
        assert "lots" not in (d.plan_meta or {})
        assert "lots" not in (d.compteur or {})
    finally:
        db.close()
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "2"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_inconnu"
    # Répondre à UN seul lot d'un marché alloti : un seul dossier, comme aujourd'hui.
    pid2 = _projet(client, h)
    st2 = client.post(f"/api/atelier/{pid2}", headers=h, json={"lots": ["2"]}).json()
    assert st2["lots"]["actif"] is False and all(s["lot"] == "" for s in st2["sections"])


def test_l_empreinte_d_un_dossier_a_un_seul_lot_ne_change_pas():
    """Une dérogation déjà enregistrée en production (empreinte d'un état) reste valable : l'empreinte d'un dossier
    à un seul lot est calculée exactement comme avant la vague 6."""
    import hashlib

    class D:
        options_export = {"page_garde": True, "sommaire": True}

    class S:
        id, ordre, intitule = 1, 0, "Méthodologie"

    lims = [{"portee": "document", "section_id": None, "type": "pages", "valeur": 8, "mesure": 3, "lot": ""}]
    avant = {"o": {"page_garde": True, "sommaire": True}, "l": [("document", None, "pages", 8, 3)],
             "s": [(1, 0, "Méthodologie", "", [])]}
    attendu = hashlib.sha256(json.dumps(avant, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    assert at.etat_hash(D(), [S()], {}, lims) == attendu
    assert at.etat_hash(D(), [S()], {}, lims, lot="2") != attendu


# ═══ 8. Isolation, contrôle des faits, entretien chantier ═══════════════════════════════════════════

def test_isolation_les_routes_des_lots_d_un_autre_compte_repondent_404(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    sid = st["sections"][0]["id"]
    r = client.post("/api/auth/register", json={"email": f"autre_lots_{pid}@test.fr", "password": "motdepasse123",
                                                "full_name": "Autre", "company_name": "Autre SARL"})
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for m, url, body in (("get", f"/api/atelier/{pid}/lots", None),
                         ("put", f"/api/atelier/{pid}/lots", {"lots": ["1", "2"]}),
                         ("put", f"/api/atelier/{pid}/sections/{sid}/portee", {"commune": True}),
                         ("post", f"/api/atelier/{pid}/export", {"format": "docx", "lot": "2"}),
                         ("get", f"/api/atelier/{pid}?lots=2,3", None)):
        r = getattr(client, m)(url, headers=h2, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (url, r.status_code, r.text)


def test_le_numero_d_un_lot_n_est_jamais_un_fait_a_relire():
    from app.services import faits_a_relire as far
    for ph in ("Le CCTP du lot 2 prévoit une couverture en ardoise naturelle.",
               "Nous répondons aux lots 2 et 3 avec la même équipe.", "Pour le lot n° 3, nous posons la membrane."):
        assert far.a_relire(ph, [], section_entreprise=True) == [], ph
    # Une quantité reste un fait, même à côté d'un lot.
    faits = far.a_relire("Pour le lot 2, nous mobilisons 2 nacelles.", [], section_entreprise=True)
    assert [f["fait"] for f in faits if f["type"] == "chiffre"] == ["2 nacelles"]


def test_la_reponse_de_l_entretien_sert_aux_parties_soeurs_des_autres_lots(client, auth):
    from app.models import DossierPresentation, DossierSection, Project
    from app.services import entretien_chantier as ec
    h = auth["headers"]
    _company(client, h)
    rc = RC.replace("Restructuration de l'école maternelle Les Hirondelles.",
                    "Restructuration de l'école maternelle Les Hirondelles. L'école reste en activité pendant les "
                    "travaux : les zones de chantier sont séparées des cheminements des enfants.")
    pid = _projet(client, h, rc=rc)
    _creer_lots(client, h, pid)
    e = client.post(f"/api/atelier/{pid}/entretien", headers=h)
    assert e.status_code == 200, e.text
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).one()
        secs = at.sections_actives(db, d)
        lg = ec.lignes_grille(db.get(Project, pid))
        cible = None
        for q in e.json()["questions"]:
            dd = ec._def(db.get(ec.EntretienQuestion, q["id"]))
            part = ec.partie_concernee(dd.get("parties") or [], secs, ec._critere_de(dd.get("criteres") or [], lg))
            if part is not None and part.lot:
                cible = (q, part.id)
                break
        assert cible is not None, "une question doit viser une partie propre à un lot"
        q, part_id = cible
    finally:
        db.close()
    r = client.put(f"/api/atelier/{pid}/entretien/{q['id']}", headers=h,
                   json={"statut": "repondue", "reponse": "Zone de chantier clôturée côté cour, accès par le portail."})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).one()
        secs = at.sections_actives(db, d)
        part = db.get(DossierSection, part_id)
        soeurs = al.freres(secs, part)
        assert soeurs and all(s.lot != part.lot for s in soeurs)
        out = ec.pour_parties(db, db.get(Project, pid), d, secs)
        for s in [part] + soeurs:
            assert out.get(s.id) and out[s.id]["refs"], (s.lot, out.get(s.id))
        assert out[part.id]["refs"] == out[soeurs[0].id]["refs"]
    finally:
        db.close()
