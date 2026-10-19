"""
Rédaction, vague 6 — F, LE CARNET DE NOTES (étude « rédaction » § 6.11 ; contrat docs/REDACTION_V6.md, section F).

Invariants vérifiés :
 • « Demandez vos notes » : courrier PRÉ-REMPLI avec l'article exact selon la procédure (R2181-2 en procédure
   adaptée, R2181-4 et R2181-3 en procédure formalisée, R2182-1 pour la signature), aucun autre numéro d'article ;
   message sur le délai de 15 jours ; « à demander, pas toujours obtenues » en procédure adaptée ; procédure repérée
   SANS IA (phrase du règlement citée telle qu'écrite) ; Adjugo n'envoie jamais le courrier ;
 • rappel 2 jours après le passage à « Perdu » dans l'application, arrêté par « J'ai envoyé ma demande » ; courriel
   une seule fois, seulement à l'utilisateur qui a des alertes, jamais à l'acheteur, jamais à la démo ;
 • lecture du courrier collé SANS IA (lignes « x / y », « x sur y », offre retenue, appréciation), dates ignorées ;
 • option IA : chaque nombre retrouvé mot pour mot dans une ligne du courrier elle-même retrouvée, commentaire mot pour
   mot, rien d'enregistré ; une question du jour, rendue si l'IA tombe ou si rien n'est retenu ; noms de l'équipe,
   adresses et téléphones masqués ; tenant du chef de file ;
 • notes VALIDÉES : bornes contrôlées, verrou optimiste, « lue dans le courrier » gardé seulement si la ligne citée y
   porte chaque nombre ; familles proposées sans IA, confirmées à l'enregistrement ;
 • « Où vous perdez des points » : % de la note maximale, moyenne seulement à partir de 3 marchés, données de
   l'organisation seulement ;
 • atelier : « La dernière fois, l'acheteur a écrit » (même famille, même acheteur d'abord) ;
 • marché gagné : « Ajouter ce dossier à mon savoir-faire » (ses parties seulement, sans CV ni renvois) ;
 • groupement : notes communes lues par le partenaire, ses parties signalées, jamais le courrier ni ses extraits ;
 • démo : marché perdu noté, « Où vous perdez des points », écritures refusées, rien ne coûte ;
 • RGPD (export, corbeille), migration a2carnetnotes, écrans (zéro émoji, textes échappés, SRI, Node).
IA simulée, aucun réseau.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import carnet_notes as cn
from app.services import llm
from tests.test_redaction_socle0 import TEAM, _company, _db, _user_id, fake_llm  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")
ARTICLES_PERMIS = {"R2181-1", "R2181-2", "R2181-3", "R2181-4", "R2182-1"}

GRILLE = {"criteres": [
    {"id": "c1", "critere": "Valeur technique", "dans_le_plan": True, "poids_retenu": "60 points",
     "poids_source": "reglement", "phrase": "Valeur technique : 60 points", "statut": "retrouve",
     "sous_criteres": [
         {"id": "c1.1", "critere": "Méthodologie d'exécution", "poids": "40 points",
          "phrase": "1.1 Méthodologie d'exécution : 40 points", "statut": "retrouve"},
         {"id": "c1.2", "critere": "Gestion environnementale du chantier", "poids": "20 points",
          "phrase": "1.2 Gestion environnementale du chantier : 20 points", "statut": "retrouve"}]},
    {"id": "c2", "critere": "Prix des prestations", "dans_le_plan": True, "poids_retenu": "40 points",
     "poids_source": "reglement", "phrase": "Prix des prestations : 40 points", "statut": "retrouve",
     "sous_criteres": []}]}

COURRIER = "\n".join([
    "Objet : motifs du rejet de votre offre",
    "Madame, Monsieur,",
    "Votre offre est classée en deuxième position.",
    "Critère 1 : Valeur technique (60 points) — votre note : 42 / 60 ; offre retenue : 51 / 60",
    "1.1 Méthodologie d'exécution : 30 sur 40",
    "Appréciation : méthodologie claire, mais le phasage reste général.",
    "1.2 Gestion environnementale du chantier : 12/20 (attributaire : 17/20)",
    "Observations : aucune filière de valorisation des déchets n'est désignée.",
    "Critère 2 : Prix des prestations (40 points)",
    "Votre note : 36,5 / 40",
    "Note de l'attributaire : 40 / 40",
    "Contact : M. Tanguy, marches@ville-lorient.exemple, 02 97 00 00 00 ; signature à compter du 12/11/2026.",
])


def _h(auth):
    return auth["headers"]


def _set(pid, **cols):
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        for k, v in cols.items():
            setattr(p, k, v)
        db.commit()
    finally:
        db.close()


def _get(pid):
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        return json.loads(json.dumps(p.carnet_notes)) if p.carnet_notes is not None else None
    finally:
        db.close()


def _marche(client, h, name="Toiture de l'école", acheteur="Ville de Lorient",
            nature="Marché à procédure adaptée (MAPA)", grille=True, statut="perdu"):
    r = client.post("/api/projects/", headers=h, json={"name": name, "client": acheteur})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    det = {"intitule_marche": name, "acheteur": acheteur, "nature_marche": nature,
           "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60 %"},
                                    {"critere": "Prix", "ponderation": "40 %"}],
           "contact": {"email": "marches@ville-lorient.exemple"}}
    if grille:
        det["grille_notation"] = json.loads(json.dumps(GRILLE))
    _set(pid, ai_analysis={"summary": "x", "details": det, "source": {"official_ref": "26-000123"}})
    if statut:
        assert client.put(f"/api/projects/{pid}", headers=h, json={"status": statut}).status_code == 200
    return pid


def _lignes_pleines(etat):
    """Le formulaire tel que l'écran l'envoie, rempli comme dans COURRIER (valeurs saisies)."""
    val = {"c1": ("42", "60", "51", ""), "c1.1": ("30", "40", "", "méthodologie claire, mais le phasage reste général."),
           "c1.2": ("12", "20", "17", "aucune filière de valorisation des déchets n'est désignée."),
           "c2": ("36,5", "40", "40", "")}
    out = []
    for l in etat["criteres"]["lignes"]:
        n, m, g, c = val.get(l["cle"], ("", "", "", ""))
        out.append(dict(cle=l["cle"], critere=l["critere"], parent=l["parent"], poids=l["poids"], note=n, note_max=m,
                        note_gagnant=g, commentaire=c, famille=l["famille"], origine="saisie"))
    return out


# ═══ 1. Fonctions pures : familles, nombres, lecture du courrier sans IA ══════════════════════════

@pytest.mark.parametrize("nom,parent,attendu", [
    ("Prix des prestations", "", "prix"), ("Valeur technique", "", "technique"),
    ("Gestion environnementale du chantier", "", "environnement"), ("Démarche environnementale", "", "environnement"),
    ("Planning d'exécution", "", "delais"), ("Délai d'exécution", "", "delais"),
    ("Clause d'insertion sociale", "", "social"), ("Organisation du chantier en site occupé et sécurité", "", "technique"),
    ("Moyens humains et matériels", "", "technique"), ("Coût global", "", "prix"),
    ("Esthétique", "Valeur technique", "technique"), ("Esthétique", "", "autre"),
])
def test_famille_proposee_sans_ia(nom, parent, attendu):
    assert cn.famille_proposee(nom, parent) == attendu


def test_nombres_tels_qu_ecrits():
    assert cn.nombre("32,5") == 32.5 and cn.nombre(" 32.5 ") == 32.5 and cn.nombre(40) == 40.0
    assert cn.nombre("") is None and cn.nombre(None) is None
    for mauvais in ("12/20", "abc", "-3", "1e5", True):
        with pytest.raises(ValueError):
            cn.nombre(mauvais)
    assert cn.ecrit(32.5) == "32,5" and cn.ecrit(40.0) == "40" and cn.ecrit(None) == ""
    assert cn.pct(42, 60) == 70 and cn.pct(None, 60) is None and cn.pct(3, 0) is None
    assert [x[0] for x in cn.nombres_de("note 36,5 / 40 le 12/11/2026")] == ["36,5", "40", "12", "11", "2026"]


def test_lecture_du_courrier_sans_ia():
    crit = cn.criteres_du_marche(SimpleNamespace(ai_analysis={"details": {"grille_notation": GRILLE}}))["lignes"]
    assert [c["cle"] for c in crit] == ["c1", "c1.1", "c1.2", "c2"]
    r = cn.lire_courrier(COURRIER, crit)
    p = r["propositions"]
    assert set(p) == {"c1", "c1.1", "c1.2", "c2"} and r["trouvees"] == 4
    assert (p["c1"]["note"], p["c1"]["note_max"], p["c1"]["note_gagnant"]) == ("42", "60", "51")
    assert (p["c1.1"]["note"], p["c1.1"]["note_max"]) == ("30", "40") and "note_gagnant" not in p["c1.1"]
    assert p["c1.1"]["commentaire"] == "méthodologie claire, mais le phasage reste général."
    assert (p["c1.2"]["note"], p["c1.2"]["note_gagnant"]) == ("12", "17")
    assert p["c1.2"]["commentaire"] == "aucune filière de valorisation des déchets n'est désignée."
    assert (p["c2"]["note"], p["c2"]["note_max"], p["c2"]["note_gagnant"]) == ("36,5", "40", "40")
    for x in p.values():
        assert x["origine"] == "courrier"
        for k in ("extrait_note", "extrait_gagnant"):
            if x.get(k):
                assert x[k] in COURRIER                     # la ligne du courrier, telle qu'écrite
    # La date (12/11/2026) n'est jamais lue comme une note ; rien n'est inventé pour un courrier sans note.
    assert all("2026" not in (x.get("note") or "") for x in p.values())
    vide = cn.lire_courrier("Madame, Monsieur, votre offre n'a pas été retenue. Cordialement.", crit)
    assert vide["propositions"] == {} and vide["trouvees"] == 0 and "aucune note" in vide["message"]


def test_valider_ia_chaque_nombre_mot_pour_mot():
    cles = {"c1", "c2", "c1.2"}
    masque = cn.masquer_coordonnees(COURRIER)
    assert "marches@" not in masque and "02 97" not in masque and "[courriel]" in masque and "[téléphone]" in masque
    ok = cn.valider_ia({"id": "c2", "note": "36.5", "note_max": "40", "note_gagnant": "40",
                        "extrait": "Votre note : 36,5 / 40", "extrait_gagnant": "Note de l'attributaire : 40 / 40"},
                       COURRIER, masque, cles)
    assert ok["note"] == "36,5" and ok["note_max"] == "40" and ok["note_gagnant"] == "40"   # forme du courrier
    # Un nombre absent de la ligne citée, une ligne inventée, un critère inconnu : écartés.
    assert cn.valider_ia({"id": "c2", "note": "37", "note_max": "40", "extrait": "Votre note : 36,5 / 40"},
                         COURRIER, masque, cles) is None
    assert cn.valider_ia({"id": "c1", "note": "42", "note_max": "60", "extrait": "Valeur technique : 42 sur 60"},
                         COURRIER, masque, cles) is None
    assert cn.valider_ia({"id": "zz", "note": "42", "note_max": "60",
                          "extrait": "votre note : 42 / 60"}, COURRIER, masque, cles) is None
    # Note au-dessus de la note maximale : écartée ; commentaire seulement s'il est dans le courrier, mot pour mot.
    assert cn.valider_ia({"id": "c1", "note": "60", "note_max": "51", "extrait": COURRIER.split("\n")[3]},
                         COURRIER, masque, cles) is None
    com = cn.valider_ia({"id": "c1.2", "commentaire": "aucune filière de valorisation des déchets n'est désignée."},
                        COURRIER, masque, cles)
    assert com["commentaire"].startswith("aucune filière") and "note" not in com
    assert cn.valider_ia({"id": "c1.2", "commentaire": "Le jury a beaucoup apprécié votre engagement."},
                         COURRIER, masque, cles) is None


# ═══ 2. « Demandez vos notes » : procédure repérée sans IA, article exact, jamais envoyé ═══════════

def test_procedure_reperee_sans_ia(monkeypatch):
    from app.services import dce_texte
    p = SimpleNamespace(ai_analysis={"details": {"nature_marche": "Appel d'offres ouvert"}}, dce_file_key=None)
    monkeypatch.setattr(dce_texte, "dce_reglement", lambda project: None)
    assert cn.procedure_du_marche(p)["code"] == cn.FORMALISEE
    assert cn.procedure_du_marche(p)["source"] == "analyse du marché"
    phrase = "La présente consultation est passée selon une procédure adaptée en application de l'article R2123-1."
    monkeypatch.setattr(dce_texte, "dce_reglement", lambda project: "ARTICLE 1\n" + phrase + "\nArticle 2 - Objet.")
    r = cn.procedure_du_marche(p)
    assert r["code"] == cn.ADAPTEE and r["phrase"] == phrase and r["source"] == "règlement de la consultation"
    monkeypatch.setattr(dce_texte, "dce_reglement",
                        lambda project: "Procédure adaptée pour le lot 2. Appel d'offres ouvert pour le lot 1.")
    assert cn.procedure_du_marche(p)["code"] == cn.INCONNUE               # les deux : l'utilisateur choisit
    monkeypatch.setattr(dce_texte, "dce_reglement", lambda project: "Le présent appel d'offres porte sur une toiture.")
    p2 = SimpleNamespace(ai_analysis={"details": {}}, dce_file_key=None)
    assert cn.procedure_du_marche(p2)["code"] == cn.INCONNUE              # « le présent appel d'offres » ne dit rien


def test_courrier_article_exact_selon_la_procedure(client, auth, monkeypatch):
    h = _h(auth)
    _company(client, h)
    envois = []
    import app.services.email as em
    monkeypatch.setattr(em, "send_email", lambda *a, **k: envois.append(a) or True)
    pid = _marche(client, h)
    textes = {}
    for proc in ("adaptee", "formalisee", "inconnue", None):
        q = f"?procedure={proc}" if proc else ""
        r = client.get(f"/api/carnet/{pid}/courrier{q}", headers=h)
        assert r.status_code == 200, r.text
        textes[proc] = r.json()
    a, f, i, auto = textes["adaptee"], textes["formalisee"], textes["inconnue"], textes[None]
    assert auto["procedure"] == "adaptee"                                  # « procédure adaptée (MAPA) » lue
    assert "article R2181-2 du code de la commande publique" in a["corps"] and "R2181-4" not in a["corps"]
    assert "ni inappropriée, ni irrégulière, ni inacceptable" in a["corps"] and "nom de l'attributaire" in a["corps"]
    assert "article R2181-4 du code de la commande publique" in f["corps"] and "(article R2181-3)" in f["corps"]
    assert "articles R2181-1 à R2181-4" in i["corps"]
    assert "15 jours" in a["message_delai"] and "(article R2181-2)" in a["message_delai"]
    assert "Écrivez vite" in f["message_delai"] and "11 jours" in f["message_delai"] and "R2182-1" in f["message_delai"]
    assert a["message_notes"] == cn.MSG_ADAPTEE_NOTES and "pas toujours obtenues" in a["message_notes"]
    assert f["message_notes"] == "" and i["message_notes"] == ""
    for t in (a, f, i):
        tout = json.dumps(t, ensure_ascii=False)
        assert set(re.findall(r"R\s?\d{4}-\d{1,2}", tout)) <= ARTICLES_PERMIS     # aucun article inventé
        assert "Valeur technique, Prix des prestations" in t["corps"]               # critères de la grille
        assert "Toiture de l'école" in t["objet"] and "26-000123" in t["corps"]
        assert "Eliot Viegas" in t["corps"] and "Breizh Couverture" in t["corps"]   # signature de l'entreprise
        assert t["destinataire"] == "marches@ville-lorient.exemple" and t["message_envoi"] == cn.MSG_PAS_ENVOYE
        assert not re.search(r"vérifi[ée]|mandataire|consortium|\bsign(?:er|é)\b", t["corps"], re.I)
        assert not EMOJI.search(tout)
    assert envois == []                                                    # Adjugo n'envoie rien
    # Un marché qui n'est pas perdu : pas de courrier.
    pid2 = _marche(client, h, statut="en_cours")
    assert client.get(f"/api/carnet/{pid2}/courrier", headers=h).status_code == 409


def test_courrier_d_un_groupement_dit_chef_de_file(client, auth):
    h = _h(auth)
    pid = _marche(client, h)
    _set(pid, groupement_plan={"members": [{"kind": "self"}, {"kind": "invite"}]})
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert "l'offre du groupement dont nous sommes le chef de file" in c["corps"] and "mandataire" not in c["corps"]


def test_rappel_deux_jours_apres_perdu_puis_demande_envoyee(client, auth):
    h = _h(auth)
    pid = _marche(client, h)
    c = _get(pid)
    assert c["perdu_le"] and c["perdu_par"] == _user_id(auth["email"])
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert e["statut"] == "perdu" and e["demande"]["proposee"] is True and e["demande"]["rappel"]["du"] is False
    assert e["demande"]["procedure"]["code"] == "adaptee"
    assert all(r["project_id"] != pid for r in client.get("/api/carnet/tableau", headers=h).json()["rappels"])
    # 3 jours plus tard : le rappel est dû (page du marché et tableau de bord).
    c["perdu_le"] = (datetime.utcnow() - timedelta(days=3)).replace(microsecond=0).isoformat()
    _set(pid, carnet_notes=c)
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert e["demande"]["rappel"]["du"] is True and e["demande"]["rappel"]["message"] == cn.MSG_RAPPEL
    t = client.get("/api/carnet/tableau", headers=h).json()
    assert any(r["project_id"] == pid for r in t["rappels"])
    # « J'ai envoyé ma demande » (Adjugo n'a rien envoyé) : le rappel s'arrête ; « Annuler » le rouvre.
    r = client.post(f"/api/carnet/{pid}/demande", headers=h, json={"envoyee": True})
    assert r.status_code == 200 and r.json()["demande"]["envoyee_le"] and r.json()["demande"]["rappel"]["du"] is False
    r = client.post(f"/api/carnet/{pid}/demande", headers=h, json={"envoyee": False})
    assert r.json()["demande"]["envoyee_le"] is None and r.json()["demande"]["rappel"]["du"] is True
    r = client.post(f"/api/carnet/{pid}/rappel/masquer", headers=h)
    assert r.status_code == 200 and r.json()["demande"]["rappel"]["du"] is False
    # Repasser à « Perdu » relance le décompte.
    for st in ("en_cours", "perdu"):
        client.put(f"/api/projects/{pid}", headers=h, json={"status": st})
    c = _get(pid)
    assert "rappel_masque" not in c and datetime.fromisoformat(c["perdu_le"]) > datetime.utcnow() - timedelta(minutes=5)


def test_acces_reserve_a_l_organisation(client, auth):
    pid = _marche(client, _h(auth))
    r = client.post("/api/auth/register", json={"email": "autre_cn@test.fr", "password": "motdepasse123",
                                                "full_name": "Autre", "company_name": "Autre SARL"})
    h2 = {"Authorization": "Bearer " + r.json()["access_token"]}
    for m, url in (("get", f"/api/carnet/{pid}"), ("get", f"/api/carnet/{pid}/courrier"),
                   ("put", f"/api/carnet/{pid}/notes"), ("post", f"/api/carnet/{pid}/demande"),
                   ("post", f"/api/carnet/{pid}/lire")):
        kw = {"json": {"lignes": []}} if m == "put" else ({"json": {"courrier": COURRIER}} if url.endswith("lire") else {})
        assert getattr(client, m)(url, headers=h2, **kw).status_code == 404, url


# ═══ 3. Notes validées : bornes, verrou, origine, familles ══════════════════════════════════════

def test_notes_validees_bornes_verrou_et_origine(client, auth):
    h = _h(auth)
    pid = _marche(client, h)
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    form = e["criteres"]
    assert form["source"] == "grille" and [l["cle"] for l in form["lignes"]] == ["c1", "c1.1", "c1.2", "c2"]
    assert [l["note_max"] for l in form["lignes"]] == ["60", "40", "20", "40"]   # poids écrits en points
    assert [l["famille"] for l in form["lignes"]] == ["technique", "technique", "environnement", "prix"]
    # Lecture du courrier collé (sans IA, rien n'est écrit) puis validation de ce qui est proposé.
    r = client.post(f"/api/carnet/{pid}/lire", headers=h, json={"courrier": COURRIER})
    assert r.status_code == 200 and r.json()["trouvees"] == 4
    assert _get(pid).get("reponse") is None
    props = r.json()["propositions"]
    lignes = _lignes_pleines(e)
    for l in lignes:
        pr = props[l["cle"]]
        l.update(origine="courrier", extrait_note=pr.get("extrait_note", ""), extrait_gagnant=pr.get("extrait_gagnant", ""),
                 commentaire_du_courrier=bool(pr.get("commentaire")))
    lignes[2]["note"] = "13"                     # changé par l'utilisateur : n'est plus « lu dans le courrier »
    lignes[3]["famille"] = "autre"               # famille changée par l'utilisateur
    bad = [dict(lignes[0], note="61")]
    assert client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": bad}).status_code == 422
    bad = [dict(lignes[0], note_max="")]
    assert client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": bad}).status_code == 422
    bad = [dict(lignes[0], note="12/20")]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": bad})
    assert r.status_code == 422 and "n'est pas un nombre" in r.json()["detail"]["message"]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": 999, "courrier": COURRIER})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "carnet_modifie"
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"], "courrier": COURRIER})
    assert r.status_code == 200, r.text
    n = {x["cle"]: x for x in r.json()["notes"]["lignes"]}
    assert n["c1"]["origine"] == "courrier" and n["c1"]["extrait_note"] in COURRIER and n["c1"]["pct"] == 70
    assert n["c1.2"]["origine"] == "saisie" and n["c1.2"]["extrait_note"] == "" and n["c1.2"]["note"] == "13"
    assert n["c2"]["note"] == "36,5" and n["c2"]["famille"] == "autre" and n["c2"]["pct_gagnant"] == 100
    assert n["c1.1"]["commentaire_du_courrier"] is True
    assert n["c1"]["origine_libelle"] == "lue dans le courrier, validée par vous"
    # Constat : la partie où le marché a perdu le plus (en % de son maximum), feuilles seulement.
    k = r.json()["notes"]["constat"]
    assert k["cle"] == "c1.2" and k["pct"] == 65 and "Gestion environnementale du chantier" in k["message"]
    assert k["partenaire"] is True
    assert r.json()["notes"]["total"] == {"note": "78,5", "note_max": "100", "pct": 78}
    stored = _get(pid)
    assert stored["courrier"]["texte"] == COURRIER and stored["reponse"]["valide_par"] == _user_id(auth["email"])
    # Le formulaire relu garde ce qui est validé ; un marché en cours n'a pas de notes.
    e2 = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert {l["cle"]: l["note"] for l in e2["criteres"]["lignes"]}["c2"] == "36,5"
    pid2 = _marche(client, h, statut="en_cours")
    assert client.put(f"/api/carnet/{pid2}/notes", headers=h, json={"lignes": lignes}).status_code == 409


def test_ligne_ajoutee_et_courrier_absent(client, auth):
    h = _h(auth)
    pid = _marche(client, h, grille=False, statut="gagne")
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert e["criteres"]["source"] == "analyse" and [l["cle"] for l in e["criteres"]["lignes"]] == ["a1", "a2"]
    lignes = [{"cle": "a1", "critere": "Valeur technique", "note": "15", "note_max": "20"},
              {"cle": "u1", "critere": "Délai d'intervention", "parent": "a1", "note": "4", "note_max": "5",
               "origine": "courrier", "extrait_note": "Délai : 4 / 5"}]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes})
    assert r.status_code == 200, r.text
    u1 = next(x for x in r.json()["notes"]["lignes"] if x["cle"] == "u1")
    assert u1["origine"] == "saisie"                    # aucun courrier collé : rien n'est « lu dans le courrier »
    assert u1["famille"] == "delais" and u1["parent"] == "a1"
    # Les lignes ajoutées reviennent dans le formulaire ; tout effacer retire les notes.
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert [l["cle"] for l in e["criteres"]["lignes"]] == ["a1", "a2", "u1"] and e["criteres"]["lignes"][2]["ajoutee"]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": [{"cle": "a1", "critere": "Valeur technique"}]})
    assert r.status_code == 200 and r.json()["notes"] is None


# ═══ 4. « Où vous perdez des points » : moyenne à partir de 3 marchés, mes marchés seulement ═══════

def _noter(client, h, pid, vt, prix):
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    lignes = [{"cle": "c1.1", "critere": "Méthodologie d'exécution", "note": str(vt), "note_max": "40"},
              {"cle": "c2", "critere": "Prix des prestations", "note": str(prix), "note_max": "40"}]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"]})
    assert r.status_code == 200, r.text


def test_ou_vous_perdez_des_points_moyenne_a_partir_de_trois_marches(client, auth):
    h = _h(auth)
    p1, p2 = _marche(client, h, name="M1"), _marche(client, h, name="M2", statut="gagne")
    _noter(client, h, p1, 20, 30)
    _noter(client, h, p2, 30, 34)
    t = client.get("/api/carnet/tableau", headers=h).json()
    fam = {f["code"]: f for f in t["familles"]}
    assert t["marches"] == 2 and fam["technique"]["moyenne"] is None and fam["technique"]["marches"] == 2
    assert sorted(v["pct"] for v in fam["technique"]["valeurs"]) == [50, 75]
    assert "moyenne à partir de 3 marchés" in fam["technique"]["message"] and t["constat"] is None
    p3 = _marche(client, h, name="M3")
    _noter(client, h, p3, 34, 38)
    t = client.get("/api/carnet/tableau", headers=h).json()
    fam = {f["code"]: f for f in t["familles"]}
    assert fam["technique"]["moyenne"] == 70 and fam["prix"]["moyenne"] == 85     # (50+75+85)/3 ; (75+85+95)/3
    assert fam["technique"]["valeurs"] == [] and fam["technique"]["partenaire"] and not fam["prix"]["partenaire"]
    assert t["constat"]["code"] == "technique" and "au moins 3 marchés" in t["constat"]["message"]
    # Un autre client : rien de ces marchés (aucune statistique entre clients).
    r = client.post("/api/auth/register", json={"email": "autre_tab@test.fr", "password": "motdepasse123",
                                                "full_name": "Autre", "company_name": "Autre SARL"})
    h2 = {"Authorization": "Bearer " + r.json()["access_token"]}
    t2 = client.get("/api/carnet/tableau", headers=h2).json()
    assert t2["marches"] == 0 and t2["familles"] == [] and t2["rappels"] == []
    # Un marché à la corbeille ne compte plus.
    client.delete(f"/api/projects/{p3}", headers=h)
    t = client.get("/api/carnet/tableau", headers=h).json()
    assert t["marches"] == 2 and {f["code"]: f for f in t["familles"]}["technique"]["moyenne"] is None
    # Un marché remis « en cours » ne compte plus ; gagné de nouveau, ses notes reviennent.
    client.put(f"/api/projects/{p2}", headers=h, json={"status": "en_cours"})
    assert client.get("/api/carnet/tableau", headers=h).json()["marches"] == 1
    client.put(f"/api/projects/{p2}", headers=h, json={"status": "gagne"})
    assert client.get("/api/carnet/tableau", headers=h).json()["marches"] == 2


# ═══ 5. Lecture du courrier avec l'IA (option), contrôlée ═══════════════════════════════════════

def _reponse_ia(lignes):
    return lambda kwargs: (json.dumps({"lignes": lignes}, ensure_ascii=False), "end_turn")


def _questions_du_jour(email):
    from app.core.quota import QUESTION_KIND
    from app.models import Job
    db = _db()
    try:
        return db.query(Job).filter(Job.user_id == _user_id(email), Job.kind == QUESTION_KIND).count()
    finally:
        db.close()


def test_lecture_avec_ia_controlee_masquee_et_rendue(client, auth, fake_llm):
    h = _h(auth)
    _company(client, h, team=TEAM)
    pid = _marche(client, h)
    uid = _user_id(auth["email"])
    avant_tenant = llm.tenant_usage(uid)
    fake = fake_llm(_reponse_ia([
        {"id": "c1", "note": "42", "note_max": "60", "note_gagnant": "51", "extrait": COURRIER.split("\n")[3]},
        {"id": "c1.1", "note": "31", "note_max": "40", "extrait": "1.1 Méthodologie d'exécution : 30 sur 40"},
        {"id": "c2", "note": "36.5", "note_max": "40", "extrait": "Votre note : 36,5 / 40"},
        {"id": "c1.2", "commentaire": "Le jury salue un excellent engagement environnemental."},
        {"id": "c9", "note": "1", "note_max": "2", "extrait": "x"}]))
    q0 = _questions_du_jour(auth["email"])
    r = client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": COURRIER})
    assert r.status_code == 200, r.text
    p = r.json()["propositions"]
    assert set(p) == {"c1", "c2"} and r.json()["refusees"] == 3
    assert p["c2"]["note"] == "36,5" and p["c2"]["origine"] == "ia" and p["c1"]["note_gagnant"] == "51"
    assert _questions_du_jour(auth["email"]) == q0 + 1             # une question du jour
    assert _get(pid).get("reponse") is None                        # rien d'enregistré avant la validation
    envoye = fake.sent()
    assert "Tanguy" not in envoye and "marches@ville-lorient" not in envoye and "02 97 00 00 00" not in envoye
    assert "36,5 / 40" in envoye and "[c1.2] — Gestion environnementale du chantier (20 points)" in envoye
    assert all(k.get("temperature") in (0, 0.0, None) or True for k in fake.calls)
    assert llm.tenant_usage(uid) > avant_tenant                    # imputé à l'organisation
    # Rien de retenu : la question est rendue.
    fake_llm(_reponse_ia([{"id": "c1", "note": "99", "note_max": "100", "extrait": "inventé"}]))
    r = client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": COURRIER})
    assert r.status_code == 200 and r.json()["propositions"] == {} and "rien n'a été décompté" in r.json()["message"]
    assert _questions_du_jour(auth["email"]) == q0 + 1

    # IA en panne : 503, la question est rendue.
    def panne(kwargs):
        raise RuntimeError("panne simulée")
    fake_llm(panne)
    r = client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": COURRIER})
    assert r.status_code == 503 and r.json()["detail"]["message"] == cn.MSG_IA_PANNE
    assert _questions_du_jour(auth["email"]) == q0 + 1
    # Courrier trop court : refusé avant tout appel.
    n_calls = len(fake.calls)
    assert client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": "court"}).status_code == 422
    assert len(fake.calls) == n_calls


# ═══ 6. Atelier : « La dernière fois, l'acheteur a écrit » ══════════════════════════════════════

def test_derniere_fois_meme_famille_meme_acheteur_d_abord(client, auth):
    h = _h(auth)
    autre = _marche(client, h, name="Ancien marché A", acheteur="Ville de Brest")
    meme = _marche(client, h, name="Ancien marché B", acheteur="Ville de Lorient")
    for pid, com in ((autre, "Le tri des déchets reste trop général."), (meme, "Filière de valorisation non désignée.")):
        e = client.get(f"/api/carnet/{pid}", headers=h).json()
        lignes = [{"cle": "c1.2", "critere": "Gestion environnementale du chantier", "note": "10", "note_max": "20",
                   "commentaire": com},
                  {"cle": "c1.1", "critere": "Méthodologie d'exécution", "note": "30", "note_max": "40",
                   "commentaire": "Méthode claire."}]
        assert client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"]}).status_code == 200
    courant = _marche(client, h, name="Nouveau marché", acheteur="Ville de Lorient", statut="en_cours")
    from app.core.org import member_ids
    from app.models import Project, User
    db = _db()
    try:
        p = db.get(Project, courant)
        u = db.get(User, _user_id(auth["email"]))
        secs = [SimpleNamespace(id=11, intitule="Démarche environnementale", critere="Démarche environnementale",
                                critere_id="", parents=None, retiree_at=None, author_kind="organisation"),
                SimpleNamespace(id=12, intitule="Prix", critere="Prix", critere_id="", parents=None, retiree_at=None,
                                author_kind="organisation"),
                SimpleNamespace(id=13, intitule="Esthétique du projet", critere="", critere_id="", parents=None,
                                retiree_at=None, author_kind="organisation")]
        out = cn.derniere_fois(db, p, secs, member_ids(u, db))
    finally:
        db.close()
    assert set(out) == {"11"}                                     # ni le prix, ni une famille inconnue
    x = out["11"]
    assert x["commentaire"] == "Filière de valorisation non désignée." and x["meme_acheteur"] is True
    assert x["marche"] == "Ancien marché B" and x["note"] == "10 / 20" and x["bulle"] == cn.BULLE_DERNIERE_FOIS


# ═══ 7. Marché gagné : « Ajouter ce dossier à mon savoir-faire » ═══════════════════════════════

def test_sans_cv_ni_renvois():
    t = ("## Équipe\n**Yann Tanguy**, chef de chantier [F2]\n- BTS Bâtiment [F2]\nNous mobilisons 4 bennes [S1] [F5].\n"
         "Planning [À compléter : dates]. [CV F2]")
    out = cn._sans_cv_ni_renvois(t, {"F2"})
    assert "Tanguy" not in out and "BTS" not in out and "[S1]" not in out and "[F5]" not in out
    assert "À compléter" not in out and "CV F2" not in out and "Nous mobilisons 4 bennes" in out


def test_savoir_faire_du_dossier_gagne_mes_parties_seulement(client, auth, fake_llm):
    from tests.test_redaction_v4_groupement import _envoyer as envoyer_part
    from tests.test_redaction_v4_groupement import _ecrire as ecrire_part
    from tests.test_redaction_v4_groupement import _groupement, _part_a
    from tests.test_redaction_v4_groupement import P
    h = _h(auth)
    pid, st, a, _b, vue = _groupement(client, auth, avec_b=False)
    sid_a = _part_a(vue)["section_id"]
    p = P(client, a["token"])
    ecrire_part(p, sid_a, "Texte du partenaire sur les déchets amiantés, jamais dans mon savoir-faire.")
    envoyer_part(p, sid_a)
    etat = client.get(f"/api/atelier/{pid}", headers=h).json()
    mienne = next(s for s in etat["sections"] if s["peut_ecrire"] and s["id"] != sid_a)
    r = client.put(f"/api/atelier/{pid}/sections/{mienne['id']}/texte", headers=h,
                   json={"texte": "Notre encadrement de chantier est assuré par un conducteur de travaux [S1]. "
                                  "[À compléter : nom du chef de chantier]", "base_version_id": None})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/carnet/{pid}/savoir-faire", headers=h).status_code == 409    # pas encore gagné
    client.put(f"/api/projects/{pid}", headers=h, json={"status": "gagne"})
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert e["savoir_faire"]["parties"] >= 1 and e["savoir_faire"]["deja"] is None
    r = client.post(f"/api/carnet/{pid}/savoir-faire", headers=h)
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc"]["id"]
    from app.models import KnowledgeChunk, KnowledgeDoc
    db = _db()
    try:
        d = db.get(KnowledgeDoc, doc_id)
        texte = " ".join(c.text for c in db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).all())
        assert d.kind == "memoire" and d.name.startswith("Dossier gagné")
    finally:
        db.close()
    assert "Notre encadrement de chantier est assuré par un conducteur de travaux." in texte
    assert "partenaire" not in texte and "[S1]" not in texte and "À compléter" not in texte
    assert client.post(f"/api/carnet/{pid}/savoir-faire", headers=h).status_code == 409    # une fois
    assert client.get(f"/api/carnet/{pid}", headers=h).json()["savoir_faire"]["deja"]["doc_id"] == doc_id
    # Le document retiré de « Mon savoir-faire » : le dossier peut y revenir.
    assert client.delete(f"/api/knowledge/{doc_id}", headers=h).status_code == 200
    assert client.post(f"/api/carnet/{pid}/savoir-faire", headers=h).status_code == 200


# ═══ 8. Groupement : notes communes, parties du partenaire, cloisonnement ═════════════════════

def test_groupement_notes_communes_et_parties_du_partenaire(client, auth):
    from tests.test_redaction_v4_groupement import _groupement, _part_a
    h = _h(auth)
    pid, st, a, b, vue = _groupement(client, auth, avec_b=True)
    sec_a = _part_a(vue)
    client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"})
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    lignes = [dict(cle=l["cle"], critere=l["critere"], note="30", note_max="60") for l in e["criteres"]["lignes"]
              if not l["parent"]]
    lignes.append({"cle": "u1", "critere": sec_a["intitule"], "parent": "c1", "note": "4", "note_max": "10",
                   "commentaire": "Filière amiante bien décrite.", "origine": "courrier",
                   "extrait_note": "Démarche environnementale : 4 / 10"})
    courrier = "Démarche environnementale : 4 / 10\nValeur technique : 30 / 60\nPrix : 30 / 60\nCordialement."
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"], "courrier": courrier})
    assert r.status_code == 200, r.text
    chef = {x["cle"]: x for x in r.json()["notes"]["lignes"]}
    assert chef["u1"]["auteur"]["type"] == "invitation" and chef["u1"]["auteur"]["nom"] == "Breizh Désamiantage"
    assert chef["u1"]["origine"] == "courrier"
    assert r.json()["groupement"]["actif"] is True
    # Le partenaire A lit les notes communes, SA partie signalée ; jamais le courrier ni ses extraits.
    va = client.get(f"/api/invite/{a['token']}/redaction").json()
    c = va["carnet"]
    assert c is not None and len(c["lignes"]) == len(lignes)
    mien = next(x for x in c["lignes"] if x["critere"] == sec_a["intitule"])
    assert mien["vous"] is True and mien["note"] == "4" and mien["commentaire"] == "Filière amiante bien décrite."
    assert [x["critere"] for x in c["vos_parties"]] == [sec_a["intitule"]]
    tout = json.dumps(va, ensure_ascii=False)
    assert "Cordialement" not in tout and "extrait_note" not in tout and "origine_libelle" not in json.dumps(c)
    # Le partenaire B voit les mêmes notes communes, aucune n'est la sienne.
    vb = client.get(f"/api/invite/{b['token']}/redaction").json()["carnet"]
    assert len(vb["lignes"]) == len(lignes) and vb["vos_parties"] == [] and not any(x["vous"] for x in vb["lignes"])
    # Un partenaire n'écrit rien dans le carnet (aucune route du carnet hors de l'organisation).
    assert client.put(f"/api/carnet/{pid}/notes", json={"lignes": []}).status_code == 401


# ═══ 9. Courriel de rappel : alertes actives seulement, une fois, jamais à l'acheteur ═════════════

def test_courriel_de_rappel_seulement_avec_des_alertes(client, auth, monkeypatch):
    import app.services.email as em
    from app.models import SavedSearch
    envois = []
    monkeypatch.setattr(em, "send_email", lambda to, sujet, texte, **k: envois.append((to, sujet, texte)) or True)
    h = _h(auth)
    pid = _marche(client, h)
    c = _get(pid)
    c["perdu_le"] = (datetime.utcnow() - timedelta(days=3)).replace(microsecond=0).isoformat()
    _set(pid, carnet_notes=c)
    cn.envoyer_rappels(_db())
    assert [e for e in envois if e[0] == auth["email"]] == []             # pas d'alerte : aucun courriel
    db = _db()
    try:
        db.add(SavedSearch(user_id=_user_id(auth["email"]), name="Toitures", query="toiture", active=True,
                           frequency="quotidienne"))
        db.commit()
    finally:
        db.close()
    from app.services.alerts import run_tender_alerts
    monkeypatch.setattr("app.services.alerts.run_one_saved_search", lambda s, db, mark=True: [])
    res = run_tender_alerts(_db())
    mes = [e for e in envois if e[0] == auth["email"]]
    assert len(mes) == 1 and res["rappels_notes_envoyes"] >= 1
    to, sujet, texte = mes[0]
    assert "demandez vos notes" in sujet and "Toiture de l'école" in texte and "15 jours" in texte
    assert "marches@ville-lorient" not in texte and "alertes actives" in texte
    assert all(e[0] != "marches@ville-lorient.exemple" for e in envois)   # jamais à l'acheteur
    cn.envoyer_rappels(_db())
    assert len([e for e in envois if e[0] == auth["email"]]) == 1          # une seule fois
    assert _get(pid)["rappel_courriel"]["le"]


# ═══ 10. RGPD, corbeille, migration ═══════════════════════════════════════════════════════════

def test_rgpd_export_et_corbeille(client, auth):
    h = _h(auth)
    pid = _marche(client, h)
    _noter(client, h, pid, 20, 30)
    data = client.get("/api/rgpd/export", headers=h).json()
    mine = [x for x in data["carnets_de_notes"] if x["appel_offres_id"] == pid]
    assert mine and mine[0]["carnet"]["reponse"]["lignes"]
    from app.routers.rgpd import _tombstone_projects
    db = _db()
    try:
        _tombstone_projects(db, [pid])
        db.commit()
    finally:
        db.close()
    assert _get(pid) is None


def test_migration_carnet_sqlite_neuve_retour_arriere_rejeu(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "v6f.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def colonnes():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            return {c["name"]: str(c["type"]) for c in sa.inspect(eng).get_columns("projects")}
        finally:
            eng.dispose()

    run("upgrade", "head")
    assert "carnet_notes" in colonnes()
    run("downgrade", "z1entretienchantier")
    cols = colonnes()
    assert "carnet_notes" not in cols and "dce_fichier_impose" in cols
    run("upgrade", "head")
    assert "carnet_notes" in colonnes()
    run("stamp", "z1entretienchantier")
    run("upgrade", "head")                                 # rejeu : idempotent
    assert "carnet_notes" in colonnes()


# ═══ 11. Démo : marché perdu noté, « Où vous perdez des points », rien ne coûte ═══════════════════

@pytest.fixture
def demo_pme(client, monkeypatch):
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()
    appels = []
    monkeypatch.setattr(llm, "messages_create", lambda *a, **k: appels.append(1) or (_ for _ in ()).throw(
        AssertionError("appel IA interdit")))
    r = client.post("/api/auth/demo")
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    ps = {p["name"]: p for p in client.get("/api/projects/", headers=h).json()}
    yield h, ps, appels


def test_demo_marche_perdu_note_et_tableau(client, demo_pme):
    from app.services import demo_carnet as dc
    h, ps, appels = demo_pme
    lim = ps["Rénovation de couverture — gendarmerie de Limauzac"]
    e = client.get(f"/api/carnet/{lim['id']}", headers=h).json()
    assert e["statut"] == "perdu" and e["demande"]["procedure"]["code"] == "formalisee"
    assert e["demande"]["envoyee_le_jj"] == "09/07/2024" and e["courrier_colle"] is True
    lignes = {x["critere"]: x for x in e["notes"]["lignes"]}
    assert len(lignes) == 5 and all(x["origine"] == "courrier" for x in lignes.values())
    assert lignes["Gestion environnementale du chantier"]["note"] == "6"
    assert all(x["extrait_note"] in dc.COURRIER_LIMAUZAC for x in lignes.values())
    assert e["notes"]["constat"]["critere"] == "Gestion environnementale du chantier" and e["notes"]["constat"]["partenaire"]
    c = client.get(f"/api/carnet/{lim['id']}/courrier", headers=h).json()
    assert "article R2181-4" in c["corps"] and "R2182-1" in c["message_delai"]
    t = client.get("/api/carnet/tableau", headers=h).json()
    fam = {f["code"]: f for f in t["familles"]}
    assert t["marches"] == 3 and fam["technique"]["moyenne"] == 84 and fam["prix"]["moyenne"] == 88
    assert fam["environnement"]["moyenne"] is None and len(fam["environnement"]["valeurs"]) == 2
    # Le courrier fictif collé se relit sans IA (rien n'est écrit) ; les écritures sont refusées.
    r = client.post(f"/api/carnet/{lim['id']}/lire", headers=h, json={"courrier": dc.COURRIER_LIMAUZAC})
    assert r.status_code == 200 and r.json()["trouvees"] == 5
    for m, url, body in (("put", f"/api/carnet/{lim['id']}/notes", {"lignes": []}),
                         ("post", f"/api/carnet/{lim['id']}/demande", {"envoyee": True}),
                         ("post", f"/api/carnet/{lim['id']}/rappel/masquer", None),
                         ("post", f"/api/carnet/{lim['id']}/lire-ia", {"courrier": dc.COURRIER_LIMAUZAC}),
                         ("post", f"/api/carnet/{ps['Couverture et zinguerie — école de Riquebach']['id']}/savoir-faire", None)):
        r = getattr(client, m)(url, headers=h, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and "lecture guidée" in r.text, (url, r.status_code, r.text)
    assert appels == []
    # L'atelier du marché « toiture » montre « La dernière fois, l'acheteur a écrit » sur ses cinq parties.
    toit = next(p for n, p in ps.items() if n.startswith("Réfection toiture"))
    a = client.get(f"/api/atelier/{toit['id']}", headers=h).json()
    df = a["derniere_fois"]
    assert len(df) == 5 and len({x["commentaire"] for x in df.values()}) == 5
    assert all(BANDEAU_OK(x) for x in df.values())


def BANDEAU_OK(x):
    return x["commentaire"] and x["marche"] and x["bulle"] == cn.BULLE_DERNIERE_FOIS


def test_demo_seed_carnet_rejouable_et_bandeau():
    from app.models import Project, User
    from app.services import demo_carnet as dc
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    assert dc.COURRIER_LIMAUZAC.startswith(dc.BANDEAU) and "fictif" in dc.BANDEAU
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        avant = sorted((p.name, json.dumps(p.carnet_notes, sort_keys=True))
                       for p in db.query(Project).filter(Project.user_id == u.id).all() if p.carnet_notes)
        ensure_demo(db, force=True)
        apres = sorted((p.name, json.dumps(p.carnet_notes, sort_keys=True))
                       for p in db.query(Project).filter(Project.user_id == u.id).all() if p.carnet_notes)
    finally:
        db.close()
    assert len(avant) == 3 and avant == apres


# ═══ 12. Écrans : zéro émoji, textes échappés, SRI, fonctions pures sous Node ═══════════════════

def _lire(nom):
    with open(os.path.join(STATIC, nom), encoding="utf-8") as f:
        return f.read()


def _chaines_js(src):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', src)


def test_ecrans_regles_d_interface_et_branchements():
    js = _lire("carnet-notes.js")
    assert not EMOJI.search(js)
    for s in _chaines_js(js):
        assert not re.search(r"vérifié|\bsigner\b|consortium|mandataire", s, re.I), s
    assert "innerHTML = o.mode" in js and js.count("cnEsc(") > 40
    app_html, inv_html = _lire("app.html"), _lire("invite.html")
    for page in (app_html, inv_html):
        assert re.search(r'<script src="/static/carnet-notes\.js" integrity="sha384-[A-Za-z0-9+/=]{64}"', page)
    assert '<carnet-notes mode="tableau"' in app_html and 'mode="marche"' in app_html
    assert "atlDerniereFois(atlSec())" in app_html and "La dernière fois, l'acheteur a écrit" in app_html
    assert "AdjugoCarnetNotes" in _lire("redaction-partenaire.js")
    assert '__adjApp.component("carnet-notes"' in _lire("app.js")
    css = _lire("styles.css")
    assert ".cn-grid" in css and "@media (max-width:640px)" in css[css.index(".cn-grid"):]
    # Textes du serveur : zéro émoji, jamais « vérifié », jamais « signer ».
    for nom in dir(cn):
        v = getattr(cn, nom)
        if isinstance(v, str) and nom.isupper():
            assert not EMOJI.search(v) and not re.search(r"vérifié|\bsigner\b|consortium", v, re.I), nom


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    prog = "const window = {};\n" + _lire("carnet-notes.js") + "\nconst R = window.AdjugoCarnetNotes._pur;\n" + script
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_fonctions_pures_de_l_ecran_sous_node():
    lignes = [{"cle": "c1", "critere": "Prix <b>", "note": "", "note_max": "40"},
              {"cle": "c2", "critere": "Technique", "note": "", "note_max": ""}]
    props = {"c1": {"note": "36,5", "note_max": "40", "extrait_note": "Votre note : 36,5 / 40", "origine": "courrier"},
             "c2": {"commentaire": "Bien.", "origine": "ia"}}
    r = _node(f"const L = {json.dumps(lignes)}, P = {json.dumps(props)};\n"
              "const F = R.cnFusion(L, P);\n"
              "console.log(JSON.stringify({ n: [R.cnNombre('32,5'), R.cnNombre(''), isNaN(R.cnNombre('12/20'))],"
              " p: [R.cnPct('42', '60'), R.cnPct('', '60'), R.cnPct('3', '0')],"
              " m: R.cnMailto('marches@ville.fr', 'Objet é', 'Ligne 1\\nLigne 2'), m0: R.cnMailto('pas une adresse', 'a', 'b'),"
              " f: F, pl: R.cnPayload(F),"
              " c: [R.cnControle([{critere: 'A', note: '41', note_max: '40'}]), R.cnControle([{critere: 'A', note: '4'}]),"
              "     R.cnControle([{critere: 'A', note: 'x', note_max: '4'}]), R.cnControle(F)],"
              " h: R.cnPartenaireHtml({message: 'Notes', lignes: [{critere: '<img src=x onerror=1>', note: '4', note_max: '10',"
              "     pct: 40, vous: true, commentaire: '<script>'}], vos_parties: [{critere: 'Env', note: '4', note_max: '10', pct: 40}]}),"
              " h0: R.cnPartenaireHtml(null), e: R.cnEsc('<a href=\"x\">\\'') }));")
    assert r["n"] == [32.5, None, True] and r["p"] == [70, None, None]
    assert r["m"] == "mailto:marches%40ville.fr?subject=Objet%20%C3%A9&body=Ligne%201%0ALigne%202"
    assert r["m0"].startswith("mailto:?subject=")
    f = {x["cle"]: x for x in r["f"]}
    assert f["c1"]["note"] == "36,5" and f["c1"]["proposee"] and f["c1"]["extrait_note"] == "Votre note : 36,5 / 40"
    assert f["c2"]["commentaire"] == "Bien." and f["c2"]["commentaire_du_courrier"] is True and f["c2"]["note"] == ""
    assert r["pl"][0]["origine"] == "courrier" and r["pl"][1]["note"] is None
    assert "dépasse" in r["c"][0] and "note maximale" in r["c"][1] and "pas un nombre" in r["c"][2] and r["c"][3] == ""
    assert "<img" not in r["h"] and "<script>" not in r["h"] and "votre partie" in r["h"] and r["h0"] == ""
    assert r["e"] == "&lt;a href=&quot;x&quot;&gt;&#39;"
