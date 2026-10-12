"""
Rédaction, vague 1 — corrections de la relecture croisée (trois relecteurs indépendants).

Chaque test rejoue une sonde des relecteurs qui échouait sur 30af2ec :
  • grille : un poids n'est affiché que s'il est RATTACHÉ à son critère (inversion de l'IA dans
    une phrase ou en lignes, poids d'un sous-critère, poids « retrouvé » dans le CCAP) ;
  • ordre : « les offres seront classées par ordre décroissant » n'est pas un ordre de critères ;
  • cadre imposé : une phrase qui dément l'obligation n'impose rien ; visite « : non » ;
  • pièces : une annexe au règlement est l'annexe, « Règlement de voirie » n'est pas le RC ;
  • IA : jamais d'attente de place dans la boucle d'événements ; l'analyse part dans un fil ;
  • noms des salariés des PARTENAIRES jamais envoyés à l'IA ; adresses e-mail masquées ;
  • export Word sans marque de l'outil ; renvois « [S1-S3] » retirés ; scan lu en partie ;
  • messages : fichier imposé rappelé (liste des pièces, génération), partenaire, singulier.
Aucun appel réseau : l'IA est simulée.
"""
import asyncio
import io
import json
import os
import sys
import threading
import time
import types
import uuid

import pytest

from app.services import dce_pieces as dp
from app.services import grille_notation as gn
from app.services import llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n"


def _g(crits, body, head=H):
    det = {"criteres_attribution": [{"critere": n, "ponderation": w, "extrait": ex} for n, w, ex in crits]}
    return gn.build_grille(det, head + body + "\n")


def _ln(g, name):
    return next(x for x in g["criteres"] if x["critere"] == name)


def _static(name):
    with open(os.path.join(ROOT, "app", "static", name), encoding="utf-8") as f:
        return f.read()


# ═══ Grille : poids rattaché à SON critère ═══════════════════════════════════════════════════════

PHRASE = "Les offres seront jugées selon les critères suivants : Prix des prestations 40 % ; Valeur technique 60 %."


@pytest.mark.parametrize("with_extract", [True, False])
def test_inversion_des_poids_dans_une_phrase_jamais_affichee(with_extract):
    ex = PHRASE if with_extract else ""
    g = _g([("Prix des prestations", "60 %", ex), ("Valeur technique", "40 %", ex)], PHRASE)
    for name in ("Prix des prestations", "Valeur technique"):
        ln = _ln(g, name)
        assert ln["statut"] == gn.A_VERIFIER and ln["poids"] == "" and not ln["dans_le_plan"], ln
    assert g["controle_total"]["statut"] != "ok"
    assert "60 %" not in gn.plan_text(g) and "40 %" not in gn.plan_text(g)
    assert "60" not in json.dumps([x["poids"] for x in gn.public_grille(g)["criteres"]])


def test_inversion_en_lignes_jamais_affichee():
    body = "Valeur technique : 60 %\nPrix : 40 %"
    g = _g([("Valeur technique", "40 %", "Valeur technique : 60 %"), ("Prix", "60 %", "Prix : 40 %")], body)
    assert _ln(g, "Valeur technique")["poids"] == "" and _ln(g, "Prix")["poids"] == ""
    assert _ln(g, "Valeur technique")["phrase"] == "Valeur technique : 60 %"   # la vraie phrase, sans le poids annoncé
    assert gn.plan_text(g) == ""


def test_poids_d_un_sous_critere_jamais_pris_pour_celui_du_critere():
    body = ("Valeur technique : 60 %, appréciée au regard de la méthodologie (40 %) et des moyens (20 %).\n"
            "Prix : 40 %.")
    g = _g([("Valeur technique", "40 %", "Valeur technique : 60 %, appréciée au regard de la méthodologie (40 %)"),
            ("Prix", "40 %", "Prix : 40 %.")], body)
    assert _ln(g, "Valeur technique")["statut"] == gn.A_VERIFIER and _ln(g, "Valeur technique")["poids"] == ""
    assert _ln(g, "Prix")["poids"] == "40 %"
    # Sous-critère à la ligne suivante : pas de rattachement par-dessus le retour à la ligne.
    g2 = _g([("Valeur technique", "40 %", ""), ("Prix", "60 %", "")], "Valeur technique\nMéthodologie : 40 %\nPrix : 60 %")
    assert _ln(g2, "Valeur technique")["poids"] == "" and _ln(g2, "Prix")["poids"] == "60 %"


def test_poids_invente_jamais_retrouve_hors_du_reglement():
    """Le règlement dit « non pondérés » ; le CCAP parle d'acompte à 60 % et de retenue à 40 %."""
    rc = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Jugement des offres\n"
          "Critères de jugement des offres : prix ; valeur technique. Ils ne sont pas pondérés.\n")
    ccap = ("=== CCAP.pdf ===\nCAHIER DES CLAUSES ADMINISTRATIVES PARTICULIERES\n"
            "Article 5. Le prix est payé par acompte à hauteur de 60 % du montant à la commande.\n"
            "Article 6. La valeur technique des ouvrages fait l'objet d'une retenue de 40 % en cas de réserve.\n")
    for ex in (("Prix : 60 %", "Valeur technique : 40 %"),
               ("Le prix est payé par acompte à hauteur de 60 % du montant à la commande.",
                "La valeur technique des ouvrages fait l'objet d'une retenue de 40 % en cas de réserve.")):
        g = gn.build_grille({"criteres_attribution": [
            {"critere": "Prix", "ponderation": "60 %", "extrait": ex[0]},
            {"critere": "Valeur technique", "ponderation": "40 %", "extrait": ex[1]}]}, rc + ccap)
        for ln in g["criteres"]:
            assert ln["poids"] == "" and "CCAP" not in ln["source"], ln
        assert g["controle_total"]["statut"] != "ok"


@pytest.mark.parametrize("body,crits", [
    (PHRASE, [("Prix des prestations", "40 %"), ("Valeur technique", "60 %")]),
    ("Critères : prix des prestations (40 %), valeur technique (60 %).", [("Prix des prestations", "40 %"), ("Valeur technique", "60 %")]),
    ("Les offres seront jugées à 60 % sur la valeur technique et à 40 % sur le prix.", [("Valeur technique", "60 %"), ("Prix", "40 %")]),
    ("Les offres sont notées sur 100 points : valeur technique 60 points, prix 40 points.", [("Valeur technique", "60 points"), ("Prix", "40 points")]),
    ("Critère | Pondération\nValeur technique | 60 %\nPrix | 40 %", [("Valeur technique", "60 %"), ("Prix", "40 %")]),
    ("Valeur technique\n60 %\nPrix\n40 %", [("Valeur technique", "60 %"), ("Prix", "40 %")]),
    ("Valeur technique de l'offre appréciée au vu du mémoire : 60 % ; Prix des prestations : 40 %.", [("Valeur technique", "60 %"), ("Prix", "40 %")]),
    ("Critères : valeur technique 50 %, valeur environnementale 10 %, prix 40 %.",
     [("Valeur technique", "50 %"), ("Valeur environnementale", "10 %"), ("Prix", "40 %")]),
])
@pytest.mark.parametrize("with_extract", [True, False])
def test_poids_justes_toujours_retrouves(body, crits, with_extract):
    g = _g([(n, w, body if with_extract else "") for n, w in crits], body)
    for n, w in crits:
        ln = _ln(g, n)
        assert ln["statut"] == gn.RETROUVE and gn.parse_weight(ln["poids"])["valeur"] == gn.parse_weight(w)["valeur"], ln
    assert g["controle_total"]["statut"] == "ok"


def test_poids_avant_le_nom_ia_qui_inverse():
    body = "Les offres seront jugées à 60 % sur la valeur technique et à 40 % sur le prix."
    g = _g([("Valeur technique", "40 %", body), ("Prix", "60 %", body)], body)
    assert all(ln["poids"] == "" for ln in g["criteres"])


# ═══ Ordre, cadre imposé, visite ═════════════════════════════════════════════════════════════════

def test_classement_des_offres_n_est_pas_un_ordre_de_criteres():
    body = ("Les offres seront classées par ordre décroissant de la note obtenue au regard des critères suivants.\n"
            "Valeur technique de l'offre.\nPrix des prestations.")
    g = _g([("Valeur technique de l'offre", "", "Valeur technique de l'offre."),
            ("Prix des prestations", "", "Prix des prestations.")], body)
    assert g["ordre"]["indique"] is not True
    assert g["ponderation"]["message"] == gn.MSG_NON_PONDERES
    assert gn.plan_text(g).startswith("critères non pondérés, sans ordre indiqué : ")
    assert gn.public_grille(g)["ponderation"]["message"] == gn.MSG_NON_PONDERES
    # Un vrai ordre entre critères reste reconnu.
    g2 = _g([("Valeur technique", "", ""), ("Prix", "", "")],
            "Les critères sont classés par ordre décroissant d'importance : 1. Valeur technique ; 2. Prix.",
            head="=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Critères d'attribution\n")
    assert g2["ordre"]["indique"] is True and g2["ponderation"]["message"] == gn.MSG_NON_PONDERES_ORDRE


@pytest.mark.parametrize("phrase,impose", [
    ("Aucun cadre de réponse n'est imposé : le mémoire technique devra obligatoirement comprendre les éléments suivants.", False),
    ("Aucun cadre de réponse n'est obligatoire.", False),
    ("Le candidat n'est pas tenu d'utiliser un cadre de réponse, mais le mémoire devra être présenté en 10 pages au plus.", False),
    ("Le cadre de réponse est joint : le mémoire devra obligatoirement compter 10 pages au plus.", False),
    ("Le cadre de réponse technique devra obligatoirement être complété par le candidat.", True),
    ("Cadre de réponse technique : à compléter obligatoirement.", True),
    ("Les candidats devront, sous peine d'irrecevabilité, utiliser le cadre de réponse joint.", True),
])
def test_cadre_impose_seulement_si_le_reglement_l_impose(phrase, impose):
    c = gn.build_grille({}, "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\n" + phrase + "\n")["contraintes"]
    assert c["fichier_impose"] is impose, phrase
    assert (c["message_fichier"] == gn.MSG_FICHIER_IMPOSE) is impose


@pytest.mark.parametrize("phrase,visite", [
    ("Visite obligatoire : non", False),
    ("Il n'est pas prévu de visite obligatoire des lieux.", False),
    ("Visite obligatoire : sans objet.", False),
    ("La visite des lieux est obligatoire.", True),
    ("Les candidats n'ayant pas effectué la visite obligatoire seront éliminés.", True),
])
def test_visite_obligatoire_sans_faux_positif(phrase, visite):
    c = gn.build_grille({}, "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\n" + phrase + "\n")["contraintes"]
    assert bool(c["visite"]) is visite, phrase


# ═══ Reprise, limites, messages ══════════════════════════════════════════════════════════════════

def test_reprise_d_un_poids_saisi_sur_une_ligne_retrouvee_sans_poids():
    rc = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres\n"
          "1. Valeur technique\n2. Prix\nLa pondération figure en annexe 2.\n")
    det = {"criteres_attribution": [{"critere": "Valeur technique", "ponderation": "", "extrait": "Valeur technique"},
                                    {"critere": "Prix", "ponderation": "", "extrait": "Prix"}]}
    g = gn.build_grille(det, rc)
    vt = _ln(g, "Valeur technique")
    assert vt["statut"] == gn.RETROUVE and vt["poids"] == ""
    g2 = gn.apply_choice(g, vt["id"], "confirme", poids="60 %")
    out = gn.carry_over(g2, gn.build_grille(det, rc))
    assert _ln(out, "Valeur technique")["poids_retenu"] == "60 %"
    assert gn.plan_text(out).startswith("Valeur technique (60 %)")


def test_limites_d_une_partie_dites_comme_telles():
    rc = ("=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\n"
          "Le mémoire technique ne devra pas excéder 20 pages. Les CV des intervenants (2 pages maximum chacun) "
          "seront joints. Les références seront présentées sur une fiche de 1 page maximum par référence.\n"
          "Le mémoire, CV compris, ne dépassera pas 30 pages.\n")
    lim = {(x["valeur"], x["objet"]) for x in gn.build_grille({}, rc)["contraintes"]["limites"]}
    assert lim == {(20, ""), (2, "cv"), (1, "reference"), (30, "")}, lim
    g = gn.build_grille({}, rc)
    assert {x["objet"] for x in gn.public_grille(dict(g, criteres=[]))["contraintes"]["limites"]} == {"", "cv", "reference"}
    # Écrans : accord au singulier, partie visée, pastilles pour le mémoire seulement.
    js, inv = _static("app.js"), _static("invite.html")
    for src in (js, inv):
        assert 'un ? "page" : "pages"' in src and 'reference: "par référence"' in src
        assert "sur une partie du dossier (un CV, une question…) : voir les phrases." in src


def test_un_seul_critere_ni_pluriel_ni_ordre():
    g = _g([("Prix", "", "")], "Le critère unique de jugement des offres est le prix.")
    assert g["ponderation"]["statut"] == "non_ponderes"
    assert g["ponderation"]["message"] == gn.MSG_CRITERE_UNIQUE == "Un seul critère retrouvé, sans poids indiqué."
    assert gn.plan_text(g) == "un seul critère retrouvé, sans poids indiqué : Prix"
    assert '" · sans poids"' in _static("app.js")


def test_message_du_fichier_impose_adresse_au_partenaire():
    g = gn.build_grille({}, "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\n"
                            "Le cadre de réponse technique devra obligatoirement être complété par le candidat.\n")
    pub = gn.public_grille(dict(g, criteres=[]))
    assert pub["contraintes"]["message_fichier"] == gn.MSG_FICHIER_IMPOSE_PARTENAIRE
    assert "chef de file y recopiera" in pub["contraintes"]["message_fichier"]
    assert "vous devrez" not in json.dumps(pub, ensure_ascii=False)
    # Le fichier imposé n'est pas parmi les pièces : dit, au chef de file comme au partenaire.
    assert "récupérez-le sur la plateforme de l\\'acheteur" in _static("app.js")
    assert "le chef de file doit le récupérer sur la plateforme de l'acheteur" in _static("invite.html")


# ═══ Pièces du dossier ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name,kind", [
    ("Annexe 1 au règlement de la consultation - Cadre de réponse technique.docx", dp.CADRE),
    ("Annexe 2 au reglement de consultation - DPGF.pdf", dp.BORDEREAU),
    ("Annexe_1_RC_DPGF.pdf", dp.BORDEREAU),
    ("Reglement_de_voirie.pdf", dp.AUTRE),
    ("Règlement du PLU zone UA.pdf", dp.AUTRE),
    ("CCAP - règlement des comptes.pdf", dp.CCAP),
    ("01_Reglement.pdf", dp.REGLEMENT),
    ("Reglement_de_consultation_2026.pdf", dp.REGLEMENT),
])
def test_annexe_au_reglement_et_autres_reglements(name, kind):
    assert dp.classify_piece(name, "") == kind


def test_annexe_reconnue_par_son_titre():
    assert dp.classify_piece("Annexe_2.pdf", "ANNEXE 2 AU REGLEMENT DE LA CONSULTATION\n"
                                             "CADRE DE REPONSE TECHNIQUE\nQuestion 1") == dp.CADRE
    assert dp.classify_piece("Annexe 2 au reglement de consultation - DPGF.pdf",
                             "ANNEXE 2 AU REGLEMENT DE LA CONSULTATION") == dp.BORDEREAU
    assert dp.classify_piece("RC.pdf", "REGLEMENT DE LA CONSULTATION\nAnnexe 1 : cadre de reponse") == dp.REGLEMENT


def test_cadre_annexe_au_reglement_compte_comme_fourni():
    t, _ = dp.compose([
        {"nom": "RC.pdf", "texte": "REGLEMENT DE LA CONSULTATION\nLe cadre de réponse technique devra obligatoirement "
                                   "être complété par le candidat."},
        {"nom": "Annexe 1 au règlement de la consultation - Cadre de réponse technique.docx",
         "texte": "Question 1 : Décrivez votre méthodologie."}], 50000, headers=True)
    c = gn.build_grille({}, t)["contraintes"]
    assert c["cadre"]["fourni"] is True and c["fichier_impose"] is True


# ═══ IA : jamais d'attente dans la boucle d'événements ═══════════════════════════════════════════

class _U:
    input_tokens = 1
    output_tokens = 1


class _R:
    def __init__(self, t="ok"):
        self.content = [types.SimpleNamespace(type="text", text=t)]
        self.usage = _U()
        self.stop_reason = "end_turn"


def test_pas_d_attente_de_place_ia_dans_la_boucle(monkeypatch):
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    monkeypatch.setattr(llm, "client", lambda: types.SimpleNamespace(
        messages=types.SimpleNamespace(create=lambda **kw: _R())))
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    held = 0
    try:
        while llm._SLOTS.acquire(blocking=False):
            held += 1
        assert held == llm._MAX_CONCURRENT

        async def _route():
            t0 = time.monotonic()
            with pytest.raises(llm.LLMUnavailable):
                llm.messages_create(model=llm.MODEL_FAST, max_tokens=5, messages=[{"role": "user", "content": "x"}])
            return time.monotonic() - t0
        assert asyncio.run(_route()) < 1.0          # refus immédiat, la boucle n'est jamais figée
    finally:
        for _ in range(held):
            llm._SLOTS.release()
    assert llm.concurrency_snapshot()["now"] == 0


def test_analyse_d_un_dossier_importe_hors_de_la_boucle(client, auth, monkeypatch):
    import app.services.analysis as an
    seen = {}

    def _fake(text, company=None, criteria=None, lang_name=None, pieces=None):
        try:
            asyncio.get_running_loop()
            seen["loop"] = True
        except RuntimeError:
            seen["loop"] = False
        seen["tenant"] = llm._CURRENT_TENANT.get()
        seen["thread"] = threading.current_thread().name
        return {"summary": "s", "details": {"intitule_marche": "T"}, "match_score": 50}
    monkeypatch.setattr(an, "analyze_dce_text", _fake)
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Couverture"}).json()["id"]
    body = ("REGLEMENT DE LA CONSULTATION\nArticle 7 - Critères de jugement des offres : prix 100 %.\n" * 3).encode()
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("RC.txt", body, "text/plain")})
    assert r.status_code == 200, r.text
    assert seen["loop"] is False and seen["tenant"] is not None
    rr = client.post("/api/sourcing/reanalyze", headers=h, data={"project_id": str(pid)})
    assert rr.status_code == 200, rr.text
    assert seen["loop"] is False and seen["tenant"] is not None


# ═══ Noms des salariés : partenaires et adresses e-mail ══════════════════════════════════════════

class _Fake:
    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if "architecte d'un groupement" in llm._flatten_content(kw.get("system")):
            return _R("Synthèse des moyens du groupement.")
        return _R("# Mémoire technique\n\nTexte.")

    def sent(self):
        return "\n".join(llm._flatten_content(k.get("system")) + " "
                         + " ".join(llm._flatten_content(m.get("content")) for m in k.get("messages") or [])
                         for k in self.calls)


def test_noms_de_l_equipe_d_un_partenaire_jamais_envoyes_a_l_ia(client, auth, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import ProjectInvite, User
    fake = _Fake()
    monkeypatch.setattr(llm, "client", lambda: fake)
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    h = auth["headers"]
    assert client.put("/api/company/", headers=h, json={
        "name": "Breizh Couverture", "siret": "12345678900011", "representant_legal": "Eliot Viegas",
        "address": "1 rue du Port", "city": "Lorient", "postal_code": "56100",
        "team": [{"nom": "Yann Tanguy", "fonction": "Chef de chantier"}]}).status_code == 200
    pid = client.post("/api/projects/", headers=h, json={"name": "Groupe scolaire"}).json()["id"]
    # Le partenaire a un compte Adjugo, avec son équipe dans son profil entreprise.
    email = f"p_{uuid.uuid4().hex[:8]}@test.fr"
    reg = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                  "full_name": "Partenaire", "company_name": "Elec Ouest"})
    ph = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert client.put("/api/company/", headers=ph, json={
        "name": "Elec Ouest", "team": [{"nom": "Paul Durand", "fonction": "Chef d'équipe électricité"}]}).status_code == 200
    inv = client.post(f"/api/projects/{pid}/invites", headers=h, json={"recipient": "", "company_name": "Elec Ouest"}).json()
    db = SessionLocal()
    try:
        from app.models import Project
        db.get(Project, pid).ai_analysis = {"summary": "s", "details": {"intitule_marche": "Groupe scolaire"}}
        row = db.query(ProjectInvite).filter(ProjectInvite.token == inv["token"]).first()
        row.accepted_by_user_id = db.query(User).filter(User.email == email).first().id
        db.commit()
    finally:
        db.close()
    v = client.get(f"/api/invite/{inv['token']}/contribution").json()["version"]
    r = client.put(f"/api/invite/{inv['token']}/contribution", json={
        "version": v, "lot": "Lot 2 Électricité",
        "memoire_paragraph": "Notre chef d'équipe Paul Durand (paul.durand@elec-ouest.fr), habilité B2V, "
                             "encadrera le lot 2 avec Yann Tanguy."})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/invite/{inv['token']}/contribution/submit").status_code == 200
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    sent = fake.sent()
    assert any("architecte d'un groupement" in llm._flatten_content(k.get("system")) for k in fake.calls)
    for nom in ("Paul Durand", "Durand", "paul.durand", "Yann Tanguy", "Tanguy"):
        assert nom not in sent, f"« {nom} » est parti à l'IA"
    assert "[Chef de chantier 1]" in sent and "[Chef d'équipe électricité 1]" in sent


def test_adresse_e_mail_avec_le_nom_masquee_et_remise_en_clair():
    from app.services.pii import from_team
    pz = from_team([{"nom": "Yann Tanguy", "fonction": "Chef de chantier"}])
    t = "CV de Yann Tanguy - yann.tanguy@btp-breizh.fr - YTANGUY29@gmail.com ; mairie : accueil@quimper.fr"
    m = pz.mask(t)
    assert "tanguy" not in m.lower() and "accueil@quimper.fr" in m and "[Courriel 1]" in m
    assert pz.unmask(m) == t
    # Les écrans disent la vérité : nom complet, e-mail, ce qui n'est pas masqué.
    html = _static("app.html")
    assert "Votre nom complet, tel qu'il est enregistré dans l'équipe, ne lui est pas envoyé" in html
    assert "Une adresse e-mail qui contient votre nom est remplacée de la même façon." in html
    assert "nous retirons vos informations quand vous quittez l'entreprise" not in html
    assert "les dossiers déjà préparés qui vous citent restent conservés avec le marché concerné" in html
    assert "Évitez d'y écrire le nom de vos salariés" in html and "Évitez d'y écrire le nom de vos salariés" in _static("invite.html")


# ═══ Export, lecture des pièces, chiffrage ═══════════════════════════════════════════════════════

def test_export_word_sans_marque_de_l_outil_ni_renvoi_en_plage():
    import docx
    from app.services import memoire_export as me
    st = me.finalize("# Mémoire\n\nPlage [S1-S3]. Tiret [S1–S3]. Liste [S1, S2]. Reste [S 2 p.4].\n")
    assert "[S" not in st["markdown"]
    cp = docx.Document(io.BytesIO(me.to_docx(st["markdown"], "Mémoire technique"))).core_properties
    assert cp.author == "" and cp.comments == "" and cp.last_modified_by == "" and cp.title == "Mémoire technique"
    assert "python-docx" not in json.dumps([cp.author, cp.comments, cp.keywords, cp.subject, cp.category])
    assert cp.created.year >= 2026


def _pdf_pages(n):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def fake_ocr(monkeypatch):
    def convert_from_bytes(content, dpi=200, first_page=None, last_page=None, **kw):
        from pypdf import PdfReader
        n = len(PdfReader(io.BytesIO(content)).pages)
        lo, hi = first_page or 1, min(last_page or n, n)
        return [object() for _ in range(max(0, hi - lo + 1))]
    monkeypatch.setitem(sys.modules, "pdf2image", types.SimpleNamespace(convert_from_bytes=convert_from_bytes))
    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace(
        image_to_string=lambda img, lang=None: "REGLEMENT DE LA CONSULTATION page scannee lue par OCR."))


def test_scan_lu_en_partie_jamais_dit_lu_en_entier(fake_ocr):
    from app.services.analysis import OCR_MAX_PAGES, extract_dce_text
    _t, meta = extract_dce_text("RC_scan.pdf", _pdf_pages(OCR_MAX_PAGES + 25), with_pieces=True)
    assert meta[0]["lu_en_entier"] is False
    _t, meta = extract_dce_text("RC_scan.pdf", _pdf_pages(3), with_pieces=True)
    assert meta[0]["lu_en_entier"] is True
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("RC_scan.pdf", _pdf_pages(OCR_MAX_PAGES + 5))
    _t, meta = extract_dce_text("dce.zip", buf.getvalue(), with_pieces=True)
    assert meta[0]["lu_en_entier"] is False


def test_chiffrage_ne_recoit_que_le_plan_controle(monkeypatch):
    from app.services.agents import chiffrage
    seen = []
    monkeypatch.setattr(chiffrage, "complete_json", lambda system, user, **k: seen.append(user) or {"taches": []})
    g = _g([("Valeur technique", "70 %", "Valeur technique : 60 %"), ("Prix", "40 %", "Prix : 40 %")],
           "Valeur technique : 60 %\nPrix : 40 %")
    chiffrage.propose_tasks({"intitule_marche": "X", "grille_notation": g, "criteres_attribution": [
        {"critere": "Valeur technique", "ponderation": "70 %", "extrait": "Valeur technique : 60 %"}]}, [])
    assert "70" not in seen[0] and "extrait" not in seen[0] and "Prix (40 %)" in seen[0]


# ═══ Fichier imposé rappelé au bon moment ════════════════════════════════════════════════════════

def test_fichier_impose_rappele_dans_la_liste_des_pieces_et_a_la_generation(client, auth, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import Project
    fake = _Fake()
    monkeypatch.setattr(llm, "client", lambda: fake)
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Couverture"}).json()["id"]
    g = gn.build_grille({}, "=== RC.pdf ===\nREGLEMENT DE LA CONSULTATION\n"
                            "Le cadre de réponse technique devra obligatoirement être complété par le candidat.\n")
    db = SessionLocal()
    try:
        p = db.get(Project, pid)
        p.ai_analysis = {"summary": "s", "details": {"intitule_marche": "Couverture", "grille_notation": g}}
        db.commit()
    finally:
        db.close()
    item = next(x for x in client.get(f"/api/checklist/{pid}", headers=h).json()["checklist"]
                if x["id"] == "memoire_technique")
    assert "impose son propre cadre de réponse" in (item["context_note"] or "")
    r = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid, "cotraitants": []})
    assert r.status_code == 200, r.text
    ws = r.json()["dossier"]["warnings"]
    assert any("impose son propre cadre de réponse" in w and not w.startswith("BLOQUANT") for w in ws), ws


def test_note_a_terminer_accordee():
    src = open(os.path.join(ROOT, "app", "routers", "checklist.py"), encoding="utf-8").read()
    assert "(surligné dans le fichier Word)." not in src
    assert "passages surlignés dans le fichier Word et le PDF" in src and "passage surligné dans le fichier Word et le PDF" in src


# ═══ Écrans : messages justes, couleurs existantes, promesses ════════════════════════════════════

def test_ecrans_messages_et_promesses():
    js, html, landing = _static("app.js"), _static("app.html"), _static("landing.html")
    # Plus de succès affiché quand le dossier a un point à traiter ; avertissements gardés sur la carte.
    assert 'this.notify("Dossier commun assemblé et téléchargé")' not in js
    assert 'this.notify("Documents générés et archivés dans le dossier")' not in js
    assert "dossierToast(" in js and "cexportWarn[pid] = (r.dossier.warnings || []).slice();" in js
    assert "cexportWarn[cs.project_id]" in html and "'aw'+i" in html
    # Le message suit l'état d'avant (une ligne déjà dans le plan n'y est pas « ajoutée »).
    assert '"Poids enregistré"' in js and '"Critère confirmé"' in js
    # Aucune couleur indéfinie.
    assert "var(--warn)" not in html and "var(--warn)" not in js
    # Promesses ramenées au réel, partout.
    assert "Votre savoir-faire, indexé et traçable" not in html
    assert "IA sourcée" not in landing and "donnée jamais inventée" not in landing
    assert "Aide à la rédaction &amp; veille amont" in landing
