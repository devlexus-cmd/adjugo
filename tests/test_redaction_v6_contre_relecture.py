"""
Rédaction, vague 6 — contre-relecture (contrat docs/REDACTION_V6.md, section « Contre-relecture ») : chaque remarque
retenue des relectures (exactitude juridique, cloisonnement, lots et parcours, écrans) reproduite ici, sur le code
d'avant (901828c) ces tests échouent.

  1. le numéro d'un lot n'est pas un fait SEULEMENT dans un dossier à plusieurs lots, et seulement le numéro (« Pour le
     lot 2, 8 semaines » : 8 semaines reste à relire) ; marché simple : « le lot 12 du collège » reste un fait ;
  2. une note lue par l'IA n'est « retrouvée » que si son extrait est dans UNE ligne du courrier sans couper un nombre
     (2 n'est pas dans 12, 6,5 pas dans 36,5, 10 pas dans 100) ;
  3. la note d'ensemble n'est donnée que si chaque critère du formulaire a sa note (ou chacun de ses sous-critères) ;
  4. « l'offre du groupement » : invitations actives ou groupement retenu, jamais le plan proposé automatiquement ;
  5. le constat dit ce qui est calculé (le plus faible pourcentage), pas « le plus de points perdus » ;
  6. courrier à plusieurs lots : seule une ligne de TITRE change de lot (l'objet vaut jusqu'au premier titre) ;
  7. procédure formalisée : la condition de R2181-4 et l'exception de R2182-2 (marché subséquent) ;
  8. le courrier ne nomme que les critères de « Comment vous serez noté », jamais ceux de l'analyse ;
  9. le courriel de rappel ne part jamais à un ancien membre de l'organisation ;
 10. formulaire des notes d'un marché simple : un critère ajouté n'a pas son titre en double (écran) ;
 11. grille par lot : un poids écrit avant la mention du lot n'est jamais donné à un autre lot ;
 12. relevé de notes par lot : la grille de CE lot ;
 13. sous-critères d'un critère ensemble dans le dossier de chaque lot (ajouter, déplacer, remettre, rendre commune) ;
 14. limites par lot : chaque valeur au lot cité à côté d'elle ;
 15. « Préparer mes documents » ne retire jamais le fichier d'un lot bloqué ;
 16. nom du fichier d'un lot : sans double extension, « [raison sociale] » rempli ;
 17. « Page du fichier : Lot 2 · Lot 3 » : seule la réponse du dernier lot choisi est montrée ;
 18. une ligne vide d'un marché à plusieurs lots est ignorée avant d'exiger son lot (comme l'écran).
IA simulée, aucun réseau.
"""
import io
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta

import pytest

from app.services import atelier_lots as al
from app.services import carnet_notes as cn
from app.services import faits_a_relire as far
from app.services import faits_sources as fs
from app.services import grille_notation as gn
from tests.test_redaction_socle0 import TEAM, _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _ecrire, _etat
from tests.test_redaction_v6_carnet import COURRIER, _get, _h, _marche, _reponse_ia, _set
from tests.test_redaction_v6_lots import _creer_lots, _lot, _par, _projet, _tout_ecrire, _valider

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")


def _a_relire(texte, lots=()):
    return [x["fait"] for x in fs.controler(texte, [], mode="ia", section_entreprise=True, lots=lots)
            if x.get("statut") == fs.A_RELIRE]


# ═══ 1. Le numéro d'un lot, le seul ; jamais le nombre qui le suit ════════════════════════════════

@pytest.mark.parametrize("phrase,attendus", [
    ("Pour le lot 2, 8 semaines de travaux sont prévues.", ["8 semaines"]),
    ("Le lot 3 a 5 semaines de délai d'exécution.", ["5 semaines"]),
    ("Pour le lot 3, 10 jours de préparation sont prévus.", ["10 jours"]),
    ("Lot 3 - 2 chefs d'équipe encadrent le chantier.", ["2 chefs"]),
    ("Sur le lot 3, 4 nacelles et 12 compagnons sont affectés.", ["4 nacelles", "12 compagnons"]),
    ("Pour le lot 2, 15 compagnons seront mobilisés sur le chantier. Nous interviendrons en 6 semaines pour le lot 2 "
     "et 8 semaines pour le lot 3.", ["15 compagnons", "6 semaines", "8 semaines"]),
    ("Sur le lot 3 - 12 compagnons.", ["12 compagnons"]),
    ("Pour les lots 2 et 3, 2 chefs de chantier encadrent nos équipes.", ["2 chefs"]),
    ("Nous répondons aux lots 2 et 3 avec la même équipe.", []),
    ("Les lots 2 et 3 sont réalisés par notre équipe.", []),
])
def test_dossier_a_plusieurs_lots_seul_le_numero_du_lot_echappe_au_controle(phrase, attendus):
    assert _a_relire(phrase, lots=("2", "3")) == attendus
    assert [f["fait"] for f in far.a_relire(phrase, [], section_entreprise=True, lots=("2", "3"))] == attendus


def test_marche_simple_le_numero_d_un_lot_reste_un_fait():
    # Une référence inventée par l'IA (« le lot 12 du collège ») se relit, comme en production.
    assert _a_relire("Nous avons réalisé en 2023 le lot 12 du collège Jean Moulin, pour 480 000 € HT.") == [
        "2023", "12", "480 000 €", "Jean Moulin"]
    assert _a_relire("Notre équipe a mené les lots 4 et 7 de la réhabilitation du lycée de Brest.") == ["4", "7", "Brest"]
    # Dossier à plusieurs lots : un numéro qui n'est pas un de SES lots reste un fait.
    assert _a_relire("Notre équipe a mené les lots 4 et 7 de la réhabilitation du lycée de Brest.",
                     lots=("2", "3")) == ["4", "7", "Brest"]


def test_redaction_ia_d_une_partie_de_lot_le_delai_reste_a_relire(client, auth, fake_llm):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    fake_llm(lambda kw: ("Pour le lot 3, 10 jours de préparation sont prévus avant la pose de la membrane.",
                         "end_turn"))
    p3 = _par(st, "Méthodologie", "3")
    r = client.post(f"/api/atelier/{pid}/sections/{p3['id']}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    _attendre(client, h, pid, r.json()["tache"]["id"])
    st = _etat(client, h, pid)
    s = next(x for x in st["sections"] if x["id"] == p3["id"])
    v = s["version_courante"]
    faits = [x["fait"] for x in (v.get("faits") or []) if x.get("statut") == fs.A_RELIRE]
    assert faits == ["10 jours"], v.get("faits")                 # « lot 3 » n'en est pas un, « 10 jours » oui
    assert s["faits_a_relire"] == 1


# ═══ 2. L'IA : un nombre n'est retrouvé que s'il est un nombre ENTIER d'une ligne du courrier ═════

def test_valider_ia_refuse_un_morceau_d_un_autre_nombre():
    courrier = ("Madame, Monsieur,\nVoici le détail de la notation de votre offre.\n"
                "Valeur technique : 12 / 20\nPrix : 36,5 / 40\nDélais : 8 / 100\n")
    m = cn.masquer_coordonnees(courrier)
    cles = {"c1", "c2", "c3"}
    for it in ({"id": "c1", "note": "2", "note_max": "20", "extrait": "2 / 20"},
               {"id": "c2", "note": "6,5", "note_max": "40", "extrait": "6,5 / 40"},
               {"id": "c3", "note": "8", "note_max": "10", "extrait": "8 / 10"},
               {"id": "c2", "note": "36,5", "note_max": "4", "extrait": "36,5 / 4"},
               {"id": "c1", "note": "12", "note_max": "20", "extrait": "12 / 20 Prix : 36,5 / 40"}):   # deux lignes
        assert cn.valider_ia(it, courrier, m, cles) is None, it
    ok = cn.valider_ia({"id": "c2", "note": "36.5", "note_max": "40", "extrait": "Prix : 36,5 / 40"}, courrier, m, cles)
    assert ok["note"] == "36,5" and ok["note_max"] == "40"
    ok = cn.valider_ia({"id": "c1", "note": "12", "note_max": "20", "extrait": "12 / 20"}, courrier, m, cles)
    assert ok["note"] == "12"                                     # un morceau d'UNE ligne, sans couper un nombre


def test_ia_nombre_tronque_ni_propose_ni_valide_lu_dans_le_courrier(client, auth, fake_llm):
    h = _h(auth)
    _company(client, h, team=TEAM)
    pid = _marche(client, h)
    fake_llm(_reponse_ia([{"id": "c2", "note": "6,5", "note_max": "40", "extrait": "6,5 / 40"},
                          {"id": "c1.2", "note": "2", "note_max": "20", "extrait": "2/20 (attributaire"}]))
    r = client.post(f"/api/carnet/{pid}/lire-ia", headers=h, json={"courrier": COURRIER})
    assert r.status_code == 200 and r.json()["propositions"] == {}, r.text
    # Le même extrait renvoyé par l'écran à la validation : la note est « saisie par vous », jamais « lue ».
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    lignes = [{"cle": "c2", "critere": "Prix des prestations", "note": "6,5", "note_max": "40", "origine": "ia",
               "extrait_note": "6,5 / 40"},
              {"cle": "c1.2", "critere": "Gestion environnementale du chantier", "note": "2", "note_max": "20",
               "origine": "ia", "extrait_note": "2/20 (attributaire"}]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"], "courrier": COURRIER})
    assert r.status_code == 200, r.text
    assert {x["origine"] for x in r.json()["notes"]["lignes"]} == {"saisie"}


# ═══ 3. La note d'ensemble : chaque critère du formulaire noté ════════════════════════════════════

def test_note_d_ensemble_seulement_quand_chaque_critere_a_sa_note(client, auth):
    h = _h(auth)
    pid = _marche(client, h)          # grille : Valeur technique 60 (1.1 : 40, 1.2 : 20), Prix 40
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    lignes = [{"cle": "c1.1", "critere": "Méthodologie d'exécution", "note": "30", "note_max": "40"},
              {"cle": "c1.2", "critere": "Gestion environnementale du chantier", "note": "12", "note_max": "20"},
              {"cle": "c2", "critere": "Prix des prestations", "note": "36,5", "note_max": "40"}]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"]})
    assert r.status_code == 200, r.text
    # La valeur technique compte par ses sous-critères : 30 + 12 + 36,5 = 78,5 / 100.
    assert r.json()["notes"]["total"] == {"note": "78,5", "note_max": "100", "pct": 78}
    assert r.json()["notes"]["messages_total"] == []
    # La valeur technique laissée vide : aucune note d'ensemble, et on dit pourquoi.
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    r = client.put(f"/api/carnet/{pid}/notes", headers=h,
                   json={"lignes": [{"cle": "c2", "critere": "Prix des prestations", "note": "36,5", "note_max": "40"},
                                    {"cle": "c1", "critere": "Valeur technique", "note": "", "note_max": "60"}],
                         "rev": e["rev"]})
    n = r.json()["notes"]
    assert n["total"] is None and n["messages_total"] == [
        "Note d'ensemble : 1 critère noté sur 2. Elle s'affiche quand chaque critère a sa note (ou chacun de ses "
        "sous-critères)."]
    # Un seul sous-critère noté : toujours rien.
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    r = client.put(f"/api/carnet/{pid}/notes", headers=h,
                   json={"lignes": [lignes[0], lignes[2]], "rev": e["rev"]})
    assert r.json()["notes"]["total"] is None


# ═══ 4. Le courrier ne dit « groupement » que pour un vrai groupement ═════════════════════════════

def test_courrier_groupement_d_apres_le_groupement_reel(client, auth):
    h = _h(auth)
    pid = _marche(client, h)
    # Plan PROPOSÉ automatiquement après l'analyse : des partenaires suggérés, jamais invités.
    _set(pid, groupement_plan={"members": [{"kind": "annuaire", "id": 1, "name": "Couverture Le Gall"},
                                           {"kind": "annuaire", "id": 2, "name": "Zinc d'Armor"}], "auto": True})
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert "groupement" not in c["corps"] and "du rejet de notre offre" in c["corps"]
    # Groupement retenu à deux (chef de file + UN partenaire).
    _set(pid, groupement_plan={"members": [{"kind": "annuaire", "id": 1, "name": "Couverture Le Gall"}], "auto": False})
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert "l'offre du groupement dont nous sommes le chef de file" in c["corps"]
    # Partenaire invité (invitation active), sans plan retenu.
    _set(pid, groupement_plan=None)
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"recipient": "", "company_name": "Zinc d'Armor", "role": "cotraitant"})
    assert r.status_code in (200, 201), r.text
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert "l'offre du groupement dont nous sommes le chef de file" in c["corps"]


# ═══ 5. Le constat dit ce qui est calculé ═════════════════════════════════════════════════════════

def test_constat_dit_le_plus_faible_pourcentage():
    lignes = [{"cle": "c1", "critere": "Prix", "note": 52.8, "note_max": 60.0, "famille": "prix"},
              {"cle": "c2", "critere": "Gestion environnementale du chantier", "note": 6.0, "note_max": 10.0,
               "famille": "environnement"}]
    m = cn.constat(lignes)["message"]
    assert m == ("C'est sur « Gestion environnementale du chantier » que ce marché a obtenu sa note la plus faible, en "
                 "pourcentage de la note maximale : 6 / 10 (60 %).")
    assert "perdu le plus de points" not in m


@pytest.fixture
def demo(client, monkeypatch):
    from app.services import llm
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()
    monkeypatch.setattr(llm, "messages_create", lambda *a, **k: (_ for _ in ()).throw(AssertionError("IA interdite")))
    r = client.post("/api/auth/demo")
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    ps = {p["name"]: p for p in client.get("/api/projects/", headers=h).json()}
    return h, ps


def test_demo_le_constat_et_le_courrier_sont_exacts(client, demo):
    h, ps = demo
    lim = ps["Rénovation de couverture — gendarmerie de Limauzac"]
    e = client.get(f"/api/carnet/{lim['id']}", headers=h).json()
    assert e["notes"]["constat"]["critere"] == "Gestion environnementale du chantier"
    assert "note la plus faible, en pourcentage de la note maximale : 6 / 10 (60 %)" in e["notes"]["constat"]["message"]
    assert e["notes"]["total"] == {"note": "83,8", "note_max": "100", "pct": 84}
    t = client.get("/api/carnet/tableau", headers=h).json()
    assert "que vos notes sont les plus faibles" in t["constat"]["message"]
    assert "perdez le plus de points" not in t["constat"]["message"]
    # Les critères de la démo viennent de l'analyse : le courrier ne les nomme pas (§ 8 ci-dessous).
    c = client.get(f"/api/carnet/{lim['id']}/courrier", headers=h).json()
    assert "(Prix, Valeur technique)" not in c["corps"] and "pour chaque critère et sous-critère" in c["corps"]
    assert "Si notre offre n'a pas été écartée comme irrégulière" in c["corps"]


# ═══ 6. Courrier à plusieurs lots : un titre change de lot, une mention dans une phrase non ═══════

def test_courrier_un_lot_cite_dans_une_phrase_ne_change_pas_de_lot():
    lignes = ["Objet : Restructuration de l'école - lot 3 Étanchéité des toitures-terrasses",
              "Madame, Monsieur,", "Votre offre pour le lot 2 fait l'objet d'un courrier séparé.",
              "Valeur technique : 31 / 60", "Prix : 35 / 40"]
    assert cn.lots_des_lignes(lignes, ["2", "3"]) == ["3"] * 5
    crits = [{"cle": f"L{n}-{k}", "critere": c, "parent": "", "lot": n, "lot_libelle": f"Lot {n}"}
             for n in ("2", "3") for k, c in (("c1", "Valeur technique"), ("c2", "Prix"))]
    p = cn.lire_courrier("\n".join(lignes), crits)["propositions"]
    assert set(p) == {"L3-c1", "L3-c2"} and p["L3-c1"]["note"] == "31"
    # Des titres : chacun ouvre la partie de SON lot. Seconde contre-relecture : une ligne qui COMMENCE par « Pour le
    # lot 3, … » ouvre le lot 3, quelle que soit la ponctuation (« S'agissant du lot 2, votre offre a obtenu les notes
    # suivantes. ») ; seule une mention au milieu d'une phrase n'ouvre rien.
    t = ["Pour le lot 2 — Couverture", "Prix : 3/4", "Pour le lot 3, votre offre est irrégulière.", "Prix : 1/4",
         "Lot 3 : Étanchéité", "Prix : 2/4"]
    assert cn.lots_des_lignes(t, ["2", "3"]) == ["2", "2", "3", "3", "3", "3"]


# ═══ 7. Procédure formalisée : R2181-4 sous condition, R2182-2 ═══════════════════════════════════

def test_procedure_formalisee_condition_et_marche_subsequent(client, auth):
    h = _h(auth)
    pid = _marche(client, h, nature="Appel d'offres ouvert (articles R2124-1 et R2161-2)")
    c = client.get(f"/api/carnet/{pid}/courrier?procedure=formalisee", headers=h).json()
    assert c["corps"].count("Si notre offre n'a pas été écartée comme irrégulière, inacceptable ou inappropriée, nous "
                            "vous demandons, en application de l'article R2181-4") == 1
    assert "si votre offre n'a pas été écartée comme irrégulière, inacceptable ou inappropriée" in c["message_delai"]
    assert "au plus tard 15 jours" in c["message_delai"] and "(article R2182-2)" in c["message_delai"]
    assert "ne peut en principe pas être signé moins de 11 jours" in c["message_delai"]
    assert c["phrase_subsequent"] == ""
    # Marché subséquent d'un accord-cadre (lu sans IA) : le délai de 11 jours ne s'applique pas, on le dit.
    a = _get_analysis(pid)
    a["details"]["nature_marche"] = ("Le présent marché subséquent est passé sur le fondement de l'accord-cadre conclu "
                                     "à l'issue d'un appel d'offres ouvert.")
    _set(pid, ai_analysis=a)
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    # (Seconde contre-relecture : la vraie source est dite, et l'exception sous condition.)
    assert c["procedure"] == "formalisee" and c["message_delai"] == cn.message_delai_subsequent("analyse du marché")
    assert "11 jours" in c["message_delai"] and "Si c'est bien le cas" in c["message_delai"]
    assert c["phrase_subsequent"].startswith("Le présent marché subséquent")
    # En procédure adaptée, rien ne change.
    c = client.get(f"/api/carnet/{pid}/courrier?procedure=adaptee", headers=h).json()
    assert c["message_delai"] == cn.MSG_DELAI[cn.ADAPTEE] and c["phrase_subsequent"] == ""


def _get_analysis(pid):
    from app.models import Project
    db = _db()
    try:
        return json.loads(json.dumps(db.get(Project, pid).ai_analysis))
    finally:
        db.close()


# ═══ 8. Le courrier ne nomme que les critères du règlement ════════════════════════════════════════

def test_courrier_ne_nomme_pas_les_criteres_de_l_analyse(client, auth):
    h = _h(auth)
    pid = _marche(client, h, grille=False)
    c = client.get(f"/api/carnet/{pid}/courrier", headers=h).json()
    assert "(Valeur technique, Prix)" not in c["corps"] and "pour chaque critère et sous-critère de jugement des offres, la" \
        in c["corps"]
    pid2 = _marche(client, h, name="Autre toiture")
    c = client.get(f"/api/carnet/{pid2}/courrier", headers=h).json()
    assert "(Valeur technique, Prix des prestations)" in c["corps"]          # grille du règlement : nommés


# ═══ 9. Le courriel de rappel jamais à un ancien membre ═══════════════════════════════════════════

def test_rappel_jamais_a_un_ancien_membre(client, auth, monkeypatch):
    import app.services.email as em
    from app.models import SavedSearch
    envois = []
    monkeypatch.setattr(em, "send_email", lambda to, sujet, texte, **k: envois.append((to, sujet, texte)) or True)
    h = auth["headers"]
    pid = _marche(client, h, name="Couverture du gymnase de Kervel", acheteur="Commune de Kervel", statut=None)
    email_m = f"membre_{uuid.uuid4().hex[:6]}@test.fr"
    r = client.post("/api/org/invite", headers=h, json={"email": email_m, "full_name": "Membre Test"})
    assert r.status_code in (200, 201), r.text
    mid, mdp = r.json()["id"], r.json()["temp_password"]
    tok = client.post("/api/auth/login", json={"email": email_m, "password": mdp}).json()["access_token"]
    assert client.put(f"/api/projects/{pid}", headers={"Authorization": f"Bearer {tok}"},
                      json={"status": "perdu"}).status_code == 200
    db = _db()
    try:
        for uid in (mid, _user_id(auth["email"])):
            db.add(SavedSearch(user_id=uid, name="Toitures", query="toiture", active=True, frequency="quotidienne"))
        db.commit()
    finally:
        db.close()
    assert client.delete(f"/api/org/members/{mid}", headers=h).status_code == 200
    c = _get(pid)
    c["perdu_le"] = (datetime.utcnow() - timedelta(days=3)).replace(microsecond=0).isoformat()
    _set(pid, carnet_notes=c)
    res = cn.envoyer_rappels(_db())
    rappels = [e for e in envois if "demandez vos notes" in e[1]]
    assert [e for e in rappels if e[0] == email_m] == []                    # l'ancien membre : rien
    assert [e[0] for e in rappels] == [auth["email"]] and res["rappels_notes_envoyes"] == 1   # le titulaire actuel
    assert _get(pid)["rappel_courriel"]["a"] == _user_id(auth["email"])


# ═══ 10. Écran : un critère ajouté d'un marché simple, sans titre en double ═══════════════════════

def _node(prog):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _lire(nom):
    with open(os.path.join(STATIC, nom), encoding="utf-8") as f:
        return f.read()


def test_formulaire_critere_ajoute_sans_titre_en_double_sous_node():
    prog = ("const window = {};\n" + _lire("carnet-notes.js") + "\nconst R = window.AdjugoCarnetNotes._pur;\n"
            "const aj = {cle: 'u1', critere: 'Méthodologie et phasage', poids: '20 points', ajoutee: true};\n"
            "const connu = {cle: 'c1', critere: 'Prix', poids: '40 %'};\n"
            "const lots = [{numero: '2', libelle: 'Lot 2 — Couverture'}];\n"
            "console.log(JSON.stringify({simple: R.cnLigneTete(aj, 'k', []), lots: R.cnLigneTete(aj, 'k', lots),"
            " connu: R.cnLigneTete(connu, 'k', []), connuLots: R.cnLigneTete(connu, 'k', lots)}));")
    r = _node(prog)
    assert 'data-f="critere"' in r["simple"] and "cn-l-h" not in r["simple"] and 'data-f="lot"' not in r["simple"]
    assert 'data-f="critere"' in r["lots"] and 'data-f="lot"' in r["lots"] and "cn-l-h" not in r["lots"]
    assert "cn-l-h" in r["connu"] and 'data-f="critere"' not in r["connu"] and 'data-f="lot"' not in r["connuLots"]
    assert "h += cnLigneTete(l, k, lots);" in _lire("carnet-notes.js")


# ═══ 11. Grille par lot : un poids écrit avant le lot n'est donné à aucun autre lot ═══════════════

@pytest.mark.parametrize("zone", [
    "Prix : 40 % pour le lot 2, 60 % pour le lot 3.\nValeur technique : 60 % pour le lot 2, 40 % pour le lot 3.\n",
    "Valeur technique : 60 % (lot 2) ; 40 % (lot 3).\nPrix : 40 % (lot 2) ; 60 % (lot 3).\n",
    "La valeur technique compte pour 60 % pour le lot 2 et 40 % pour le lot 3 ; le prix compte pour 40 % pour le "
    "lot 2 et 60 % pour le lot 3.\n",
])
def test_grille_par_lot_poids_ecrit_avant_le_lot_jamais_devine(zone):
    T = "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n" + zone
    crit = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": ""},
            {"critere": "Prix", "ponderation": "40 %", "extrait": ""}]
    gs = al.grilles_par_lot(gn.build_grille({"criteres_attribution": crit}, T), T, ["2", "3"])
    for n in ("2", "3"):
        o = al.grille_out(gs[n])
        assert o["mode"] == al.MODE_ILLISIBLE and all(x["poids"] == "" for x in o["lignes"]), (n, o)
    # Des titres par lot restent lus, poids compris.
    T = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\nLot 2 – Couverture :\n"
         "- Valeur technique : 60 %\n- Prix : 40 %\nLot 3 – Étanchéité :\n- Valeur technique : 40 %\n- Prix : 60 %\n")
    gs = al.grilles_par_lot(gn.build_grille({"criteres_attribution": crit}, T), T, ["2", "3"])
    assert [(x["critere"], x["poids"]) for x in al.grille_out(gs["3"])["lignes"]] == [("Valeur technique", "40 %"),
                                                                                     ("Prix", "60 %")]


# ═══ 12. Relevé de notes par lot : la grille de CE lot ════════════════════════════════════════════

RC_GRILLES = """REGLEMENT DE LA CONSULTATION
Article 1 - Objet et allotissement
Restructuration de l'école maternelle Les Hirondelles.
Le marché est décomposé en 3 lots :
Lot 1 : Désamiantage
Lot 2 : Couverture et zinguerie
Lot 3 : Étanchéité des toitures-terrasses
Article 7 - Jugement des offres
Les offres sont jugées sur les critères suivants.
Pour le lot 2 : valeur technique 60 % ; délai d'exécution 10 % ; prix 30 %.
Pour le lot 3 : valeur technique 40 % ; prix 60 %.
"""
CRITERES_GRILLES = [{"critere": "Valeur technique", "ponderation": "60 %", "extrait": "valeur technique 60 %"},
                    {"critere": "Délai d'exécution", "ponderation": "10 %", "extrait": "délai d'exécution 10 %"},
                    {"critere": "Prix", "ponderation": "30 %", "extrait": "prix 30 %"}]


def test_releve_de_notes_d_un_lot_suit_la_grille_de_ce_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h, rc=RC_GRILLES, criteres=CRITERES_GRILLES)
    _creer_lots(client, h, pid)
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    par_lot = {n: [(x["critere"], x["poids"]) for x in e["criteres"]["lignes"] if x.get("lot") == n] for n in ("2", "3")}
    assert par_lot["3"] == [("Valeur technique", "40 %"), ("Prix", "60 %")]
    assert par_lot["2"] == [("Valeur technique", "60 %"), ("Délai d'exécution", "10 %"), ("Prix", "30 %")]


# ═══ 13. Les sous-critères d'un critère ensemble dans le dossier de CHAQUE lot ════════════════════

def _ordre_du_lot(st, n):
    lot = _lot(st, n)
    par_id = {s["id"]: s for s in st["sections"]}
    return [(lot["numeros"][str(i)], par_id[i]["intitule"]) for i in lot["parties"]]


SOUS = ("Méthodologie d'exécution", "Moyens humains et matériels affectés au lot", "Gestion environnementale du chantier")


def _groupe_ensemble(st):
    """Dans le dossier de chaque lot, les trois sous-critères de « Valeur technique » se suivent, dans l'ordre du
    règlement, numérotés sous le même titre."""
    for n in ("2", "3"):
        o = _ordre_du_lot(st, n)
        i = [x[1] for x in o].index(SOUS[0])
        assert tuple(x[1] for x in o[i:i + 3]) == SOUS, (n, o)
        t = o[i][0].split(".")[0]
        assert [x[0] for x in o[i:i + 3]] == [f"{t}.1", f"{t}.2", f"{t}.3"], (n, o)


def test_ajouter_une_partie_apres_un_sous_critere_d_un_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    r = client.post(f"/api/atelier/{pid}/sections", headers=h,
                    json={"intitule": "Références de chantiers similaires", "apres_section_id": _par(st, "Moyens", "2")["id"]})
    assert r.status_code == 201, r.text
    st = _etat(client, h, pid)
    _groupe_ensemble(st)
    assert [x[1] for x in _ordre_du_lot(st, "2")].index("Références de chantiers similaires") == 3
    # Le fichier du lot 2 : « 1. Valeur technique » une seule fois.
    st = _tout_ecrire(client, h, pid, st)
    r = client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": "2"})
    assert r.status_code == 200, r.text
    from docx import Document
    titres = [p.text for p in Document(io.BytesIO(r.content)).paragraphs if p.style.name.startswith("Heading")]
    assert titres.count("1. Valeur technique") == 1, titres


def test_deplacer_une_partie_commune_entre_les_lots(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _creer_lots(client, h, pid)
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Présentation de l'entreprise", "lot": ""})
    assert r.status_code == 201, r.text
    r = client.patch(f"/api/atelier/{pid}/sections/{r.json()['id']}", headers=h, json={"position": 2})
    assert r.status_code == 200, r.text                          # la partie passe le groupe, rien n'est refusé
    _groupe_ensemble(_etat(client, h, pid))


def test_remettre_la_partie_commune_d_un_sous_critere(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    com = next(s for s in st["sections"] if s["commune"])          # « 1.3 Gestion environnementale » (commune)
    assert client.delete(f"/api/atelier/{pid}/sections/{com['id']}", headers=h).status_code in (200, 204)
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Références du lot 2", "lot": "2"})
    assert r.status_code == 201, r.text
    assert client.post(f"/api/atelier/{pid}/sections/{com['id']}/remettre", headers=h).status_code == 200
    _groupe_ensemble(_etat(client, h, pid))


def test_rendre_commune_garde_l_ordre_du_reglement_dans_chaque_lot(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    st = _creer_lots(client, h, pid)
    r = client.put(f"/api/atelier/{pid}/sections/{_par(st, 'Moyens', '2')['id']}/portee", headers=h,
                   json={"commune": True})
    assert r.status_code == 200, r.text
    st = _etat(client, h, pid)
    for n in ("2", "3"):
        o = [x[1] for x in _ordre_du_lot(st, n)]
        assert o[:3] == ["Méthodologie d'exécution", "Moyens humains et matériels affectés au lot",
                         "Gestion environnementale du chantier"], (n, o)


# ═══ 14. Limites par lot : chaque valeur au lot cité à côté d'elle ════════════════════════════════

def test_limites_d_une_phrase_qui_cite_deux_lots():
    ph = "Le mémoire technique compte 6 pages au maximum pour le lot 2 et 3 pages au maximum pour le lot 3."
    L = [{"type": "pages", "valeur": 6, "texte": "6 pages", "phrase": ph, "objet": ""},
         {"type": "pages", "valeur": 3, "texte": "3 pages", "phrase": ph, "objet": ""}]
    assert [x["valeur"] for x in al.limites_du_lot(L, "2", ["2", "3"])] == [6]
    assert [x["valeur"] for x in al.limites_du_lot(L, "3", ["2", "3"])] == [3]
    ph = "Pour le lot 2, 6 pages au maximum ; pour le lot 3, 3 pages au maximum."
    L = [dict(x, phrase=ph) for x in L]
    assert [x["valeur"] for x in al.limites_du_lot(L, "2", ["2", "3"])] == [6]
    assert [x["valeur"] for x in al.limites_du_lot(L, "3", ["2", "3"])] == [3]
    # Une valeur qu'on ne sait pas attribuer : imposée à aucun lot, dite « selon le lot » (jamais contrôlée).
    for ph in ("Le lot 2 et le lot 3 sont limités respectivement à 6 pages et 3 pages au maximum.",
               "Le mémoire compte 6 pages et 3 pages au maximum pour les lots 2 et 3."):
        L = [dict(x, phrase=ph) for x in L]
        for n in ("2", "3"):
            assert {x["objet"] for x in al.limites_du_lot(L, n, ["2", "3"])} == {al.OBJET_SELON_LOT}, (ph, n)
    out = al.limites_du_lot(L, "2", ["2", "3"])
    from app.services import atelier_plan as ap
    d = ap.limites_du_dossier({"contraintes": {"limites": out}})
    assert d["document"] == [] and len(d["non_controlees"]) == 2
    assert 'selon_lot: "selon la partie du marché"' in _lire("app.js")   # vague 2a (D10)


def test_limite_d_un_autre_lot_ne_bloque_pas_l_export(client, auth):
    h = auth["headers"]
    _company(client, h)
    from tests.test_redaction_v6_lots import RC
    rc = RC.replace("Le mémoire technique compte 3 pages au maximum par lot.",
                    "Le mémoire technique compte 6 pages au maximum pour le lot 2 et 3 pages au maximum pour le lot 3.")
    pid = _projet(client, h, rc=rc)
    st = _creer_lots(client, h, pid)
    lim2 = [x["valeur"] for x in _lot(st, "2")["limites"] if x.get("type") == "pages"]
    lim3 = [x["valeur"] for x in _lot(st, "3")["limites"] if x.get("type") == "pages"]
    assert lim2 == [6] and lim3 == [3]


# ═══ 15. « Préparer mes documents » ne retire jamais le fichier d'un lot bloqué ═══════════════════

def _memoires(pid):
    from app.models import Document
    db = _db()
    try:
        return sorted(d.name for d in db.query(Document).filter(Document.project_id == pid,
                                                                  Document.folder == "Mémoire technique").all())
    finally:
        db.close()


def test_dossier_commun_garde_le_fichier_du_lot_bloque(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _tout_ecrire(client, h, pid, _creer_lots(client, h, pid))
    for n in ("2", "3"):
        assert client.post(f"/api/atelier/{pid}/export", headers=h, json={"format": "docx", "lot": n}).status_code == 200
    lot3 = "Lot 3 - Mémoire technique - Breizh Couverture.docx"
    assert lot3 in _memoires(pid)
    assert client.post(f"/api/atelier/{pid}/sections", headers=h,
                       json={"intitule": "Références du lot 3", "lot": "3"}).status_code == 201
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    assert any(w.startswith("BLOQUANT — Lot 3") for w in r.json()["dossier"]["warnings"])
    apres = _memoires(pid)
    assert lot3 in apres and "Lot 2 - Mémoire technique - Breizh Couverture.pdf" in apres, apres
    from app.models import Project
    db = _db()
    try:
        assert lot3 in db.get(Project, pid).workflow["dossier_presentation"]["fichiers"]
    finally:
        db.close()


# ═══ 16. Le nom du fichier d'un lot ════════════════════════════════════════════════════════════════

def test_nom_du_fichier_sans_double_extension_et_raison_sociale():
    lot = {"numero": "2", "intitule": "Couverture et zinguerie"}
    n = al.nom_du_lot(lot, "Mémoire technique", "Bâtiment de l'Ouest",
                      {"modele": "LOTXX_MT_NomCandidat.pdf", "phrase": "p", "source": "s"})
    assert n["stem"] == "LOT02_MT_Bâtiment de l'Ouest" and n["selon_reglement"] is True
    assert "« LOTXX_MT_NomCandidat.pdf »" in n["message"] and "« .pdf »" in n["message"]
    for modele, attendu in (("Lot X - Mémoire technique - [raison sociale]", "Lot 2 - Mémoire technique - Bâtiment de l'Ouest"),
                            ("Lot n° X – Mémoire technique – [raison sociale].docx",
                             "Lot n° 2 – Mémoire technique – Bâtiment de l'Ouest")):
        n = al.nom_du_lot(lot, "Mémoire technique", "Bâtiment de l'Ouest", {"modele": modele, "phrase": "p", "source": "s"})
        assert n["stem"] == attendu and n["selon_reglement"] is True, n


# ═══ 17. « Page du fichier » : la réponse du dernier lot choisi seulement ══════════════════════════

def test_page_du_fichier_reponse_en_retard_ignoree_sous_node():
    src = _lire("app.js")
    m = re.search(r"    async atlPrepLoad\(\) \{\n(.*?)\n    \},\n    atlPrepVoir", src, re.S)
    assert m, "atlPrepLoad introuvable"
    prog = ("const f = async function () {\n" + m.group(1) + "\n};\n"
            "const vm = { atl: { pid: 7, prep: { open: true, loading: false, d: null, err: '', lot: '2', seq: 0 } },\n"
            "  atlLots: () => true, atlLotsListe: () => [{ numero: '2' }, { numero: '3' }], _atlUrl: (u) => u,\n"
            "  api: (m, u) => new Promise(res => setTimeout(() => res({ lot: /lot=2/.test(u) ? '2' : '3' }),"
            " /lot=2/.test(u) ? 60 : 5)) };\n"
            "(async () => { const a = f.call(vm); vm.atl.prep.lot = '3'; const b = f.call(vm); await Promise.all([a, b]);\n"
            "  console.log(JSON.stringify({ lot: vm.atl.prep.lot, d: vm.atl.prep.d.lot, loading: vm.atl.prep.loading })); })();")
    r = _node(prog)
    assert r == {"lot": "3", "d": "3", "loading": False}


# ═══ 18. Une ligne vide d'un marché à plusieurs lots est ignorée, avant son lot ════════════════════

def test_ligne_vide_ajoutee_sans_lot_ignoree_comme_a_l_ecran(client, auth):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h)
    _creer_lots(client, h, pid)
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    assert [x["numero"] for x in e["lots"]] == ["2", "3"]
    lignes = [{"cle": "u1", "critere": "Visite du site", "note": "", "note_max": "", "commentaire": "", "lot": ""},
              {"cle": "L2-c2", "critere": "Prix", "note": "36", "note_max": "40"}]
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"]})
    assert r.status_code == 200, r.text
    assert [x["cle"] for x in r.json()["notes"]["lignes"]] == ["L2-c2"]
    # Une ligne ajoutée AVEC une note et sans lot : toujours refusée.
    lignes[0]["note"], lignes[0]["note_max"] = "3", "5"
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": r.json()["rev"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "lot_requis"
