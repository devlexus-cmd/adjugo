"""Correctifs urgents d'octobre 2026 (études moteur, organisation, veille, rédaction).

Un test (au moins) par correctif ; chacun échouait avant la correction (vérifié sur a7f48d2). Aucun
réseau réel, IA simulée.
  1. BOAMP : les départements 01 à 09 sont demandés sous les deux formes (« 06 » et « 6 »).
  2. Libellés justes : estimation détaillée (PDF), plus de Chorus Pro au dépôt, « essai gratuit de
     30 jours », verdict en mots et en %, aucun « vérifié » ni « invention » non prouvés.
  3. Plus de « Rattacher » ni d'étapes 3-4 dans la recherche : aucune entreprise tierce dans un DC1/DC2
     sans invitation acceptée ; « Ajouter un sous-traitant (DC4) » explicite.
  4. « Projets à venir » masqué (PROJETS_A_VENIR=0) : menu, accueil, veille automatique, démo.
  5. Atexo : en-tête honnête, rythme borné, PLACE suspendue (PLACE_ACTIF=0), refus sans contournement.
  6. Liste des pièces : signature exigée au dépôt seulement si le règlement l'impose.
  7. Lien de démonstration sans clé : « incomplet », et non « plus valide ».
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"


def _static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


# ═══ 1. BOAMP : « nettoyage » + 06 renvoie des avis ════════════════════════════════════════════

class _Rep:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"results": self._rows}


def _boamp_capture(monkeypatch, rows):
    """Remplace l'appel HTTP du BOAMP : garde la requête construite, rend `rows` si la requête
    demande la forme « 6 » (comme le vrai BOAMP, qui enregistre « 6 » et non « 06 »)."""
    import app.sourcing.http as http
    vues = []

    def fake(url, params=None, timeout=12, **kw):
        vues.append(params)
        where = (params or {}).get("where", "")
        return _Rep(rows if 'code_departement like "6"' in where else [])

    monkeypatch.setattr(http, "get_with_retry", fake)
    return vues


_AVIS_VENCE = {
    "idweb": "26-101010", "objet": "Nettoyage des bâtiments communaux", "nomacheteur": "Ville de Vence",
    "code_departement": ["6"], "dateparution": "2026-10-10", "datelimitereponse": "2099-11-06",
    "descripteur_libelle": ["Nettoyage"], "descripteur_code": ["123"], "type_marche": "SERVICES",
    "procedure_libelle": "Procédure adaptée", "url_avis": "https://www.boamp.fr/avis/detail/26-101010",
}


def test_boamp_departement_06_interroge_les_deux_formes(monkeypatch):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    from app.sourcing.sources.boamp import BoampSource
    vues = _boamp_capture(monkeypatch, [_AVIS_VENCE])
    crit = TenderCriteria(query="nettoyage", departements=["06"], limit=15)
    res = TenderSearchService([BoampSource()]).search(crit, {}, {})
    where = vues[0]["where"]
    assert 'code_departement like "06"' in where and 'code_departement like "6"' in where
    # L'avis remonte, ramené à la forme unique « 06 », et passe le filtre de département.
    assert res["count"] == 1 and res["tenders"][0].acheteur == "Ville de Vence"
    assert res["tenders"][0].departements == ["06"]


def test_boamp_departements_hors_01_09_inchanges(monkeypatch):
    from app.sourcing.base import TenderCriteria
    from app.sourcing.sources.boamp import BoampSource, dept_canonique, formes_boamp
    vues = _boamp_capture(monkeypatch, [])
    BoampSource().search(TenderCriteria(query="voirie", departements=["29", "2A", "974"]))
    where = vues[0]["where"]
    for f in ("29", "2A", "974"):
        assert f'code_departement like "{f}"' in where
    assert 'code_departement like "9"' not in where and 'like "2"' not in where
    assert formes_boamp("06") == ["06", "6"] and formes_boamp("29") == ["29"]
    assert dept_canonique("6") == "06" and dept_canonique("974") == "974" and dept_canonique("2a") == "2A"
    # « 6 » saisi seul est compris comme « 06 ».
    assert TenderCriteria(departements=["6"]).departements == ["06"]


# ═══ 2. Libellés justes ═══════════════════════════════════════════════════════════════════════

def test_libelles_justes_ecrans():
    html, js, inv, land = _static("app.html"), _static("app.js"), _static("invite.html"), _static("landing.html")
    # Le bouton télécharge un PDF : il s'appelle ainsi, et le fichier aussi.
    assert "Tableau de prix (Excel)" not in html and "Estimation détaillée (PDF)" in html
    assert 'a.download = "DPGF.pdf"' not in js and 'a.download = "Estimation-detaillee.pdf"' in js
    # Chorus Pro sert aux factures, jamais au dépôt d'une offre.
    for s in (html, js, inv):
        assert "Chorus" not in s
    # Un essai de 30 jours n'est pas un « compte gratuit ».
    assert "compte gratuit" not in inv and "(gratuit)" not in inv and "Créez le vôtre gratuitement" not in inv
    # Vague 2b (B3) : la durée de l'essai est lue dans la configuration du serveur (/api/public-config), jamais écrite.
    assert "Essai gratuit de ${esc(ESSAI_JOURS)} jours" in inv and "30 jours" not in inv
    # Verdict en mots et en pourcentage, jamais « GO / NO-GO » à l'écran.
    assert "NO-GO" not in land and ">GO</div>" not in land and "Bon potentiel" in land
    assert not re.search(r"\bNo-Go\b|\bNO-GO\b", html + js)
    # Aucun « vérifié » non prouvé, aucune « invention » promise.
    assert "co-traitant vérifié" not in land and "co-traitants fiables" not in land
    assert "partenaires vérifiés</li>" not in html and '<span class="rb-d">vérifiés</span>' not in html
    for name in ("app.html", "landing.html", "invite.html", "acheteur-landing.html", "acheteur.html"):
        s = _static(name)
        assert "Aucune invention" not in s and "donnée jamais inventée" not in s, name
        assert "zéro projet inventé" not in s and "on n'invente rien" not in s.lower(), name


def test_libelles_justes_serveur(client, auth):
    from app.core.demo_guard import demo_message
    from app.services.dpgf import ESTIMATION_NOTE, generate_dpgf_pdf
    from tests.test_redaction_socle0 import _db, _pdf_text
    assert demo_message("inviter un partenaire") == ("La démo est en lecture guidée : commencez votre essai "
                                                     "gratuit de 30 jours pour inviter un partenaire.")
    for mod in ("app/routers/invites.py", "app/routers/org.py", "app/routers/reseau.py", "app/routers/auth.py",
                "app/services/llm.py", "app/services/atelier_groupement.py", "app/core/demo_guard.py"):
        assert "compte gratuit" not in (ROOT / mod).read_text(encoding="utf-8"), mod
    # Le PDF « estimation détaillée » dit ce qu'il est.
    lignes = [{"tache": "Pose", "phase": "Exécution", "jours": 2, "tarif": 400, "montant": 800}]
    txt = " ".join(_pdf_text(generate_dpgf_pdf({"lignes": lignes, "total_ht": 800}, "Breizh", "Toiture")).split())
    assert "Estimation détaillée du prix" in txt and " ".join(ESTIMATION_NOTE.split()[:6]) in txt
    # Et le fichier servi s'appelle « Estimation-detaillee-… .pdf ».
    from app.models import Project
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Toiture école", "client": "Ville"}).json()["id"]
    db = _db()
    try:
        db.get(Project, pid).estimate = {"lignes": lignes, "total_ht": 800}
        db.commit()
    finally:
        db.close()
    r = client.get(f"/api/chiffrage/{pid}/dpgf", headers=h)
    assert r.status_code == 200, r.text
    assert 'filename="Estimation-detaillee-Toiture-cole.pdf"' in r.headers["content-disposition"]


# ═══ 3. Aucune entreprise dans les formulaires officiels sans avoir accepté une invitation ═════════

def _lien(pid, nom, siret, role, invite_id=None):
    from app.models import Project
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        p = db.get(Project, pid)
        ct = Cotraitant(user_id=p.user_id, name=nom, siret=siret, representant_legal="Anne Gérante", city="Brest")
        db.add(ct)
        db.flush()
        lk = ProjectCotraitant(project_id=pid, cotraitant_id=ct.id, role=role, lot="", source="discover",
                               invite_id=invite_id)
        db.add(lk)
        db.commit()
        return lk.id
    finally:
        db.close()


def test_rattacher_partenaire_refuse_sous_traitant_explicite(client, auth):
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Gymnase", "client": "Ville"}).json()["id"]
    societe = {"nom": "Kerjean Menuiserie", "siret": "12345678900029", "ville": "Brest"}
    for role in ("cotraitant", "mandataire"):
        r = client.post(f"/api/cotraitants/project/{pid}", headers=h, json={"company": societe, "role": role})
        assert r.status_code == 422 and "s'invite" in r.json()["detail"], (role, r.text)
    assert client.get(f"/api/cotraitants/project/{pid}", headers=h).json() == []
    r = client.post(f"/api/cotraitants/project/{pid}", headers=h, json={"company": societe, "role": "sous_traitant"})
    assert r.status_code == 200, r.text
    rows = client.get(f"/api/cotraitants/project/{pid}", headers=h).json()
    assert [(x["name"], x["role"], x["formulaires"]) for x in rows] == [("Kerjean Menuiserie", "sous_traitant", True)]


def test_formulaires_sans_entreprise_non_consentante(client, auth, monkeypatch):
    """Un partenaire rattaché sans invitation acceptée, ou une entreprise cochée dans la recherche, n'entre
    ni dans le DC1 ni dans le DC2 ; un sous-traitant déclaré entre dans le DC4 ; après acceptation de
    l'invitation, le partenaire entre dans le DC1."""
    import base64
    from app.models import ProjectInvite, User
    from app.routers import sourcing as sourcing_router
    from tests.test_redaction_socle0 import ANALYSIS, _company, _db, _pdf_text, _set_analysis
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h, json={"name": "Gymnase de Kerlo", "client": "Ville"}).json()["id"]
    _set_analysis(pid, ANALYSIS)
    _lien(pid, "Kerjean Menuiserie", "12345678900029", "cotraitant")          # rattaché, jamais invité
    _lien(pid, "Breizh Désamiantage", "12345678900037", "sous_traitant")      # sous-traitant déclaré

    class _Officiel:                     # l'ancienne étape 3 re-vérifiait le SIRET puis l'imprimait
        nom, siret, naf, naf_label, ville, departement, effectif = ("Intrus SARL", "98765432100011", "4332A",
                                                                    "Menuiserie", "Quimper", "29", 4)

    class _Svc:
        def verify_siret(self, siret):
            return _Officiel()

    monkeypatch.setattr(sourcing_router, "_company_service", lambda: _Svc())
    r = client.post("/api/sourcing/documents", headers=h, json={
        "project_id": pid, "cotraitants": [{"siret": "98765432100011", "nom": "Intrus SARL"}]})
    assert r.status_code == 200, r.text
    out = r.json()
    d = out["dossier"]
    pdfs = {c["id"]: _pdf_text(base64.b64decode(c["content_b64"])) for c in d["cerfas"]}
    for doc in ("dc1", "dc2"):
        assert "Kerjean" not in pdfs[doc] and "Intrus" not in pdfs[doc], doc
    assert "dc4" in pdfs and "Breizh" in pdfs["dc4"]
    assert out["cotraitants_verifies"] == 1 and out["cotraitants_rejetes"] == 1
    assert any("Kerjean Menuiserie" in w and "invitation acceptée" in w for w in d["warnings"]), d["warnings"]
    # Écran : le partenaire non consentant est signalé, avec « Inviter ».
    rows = {x["name"]: x for x in client.get(f"/api/cotraitants/project/{pid}", headers=h).json()}
    assert rows["Kerjean Menuiserie"]["formulaires"] is False and rows["Breizh Désamiantage"]["formulaires"] is True

    # Invité mais pas encore accepté : toujours absent. Accepté (lien réclamé depuis son compte) : présent.
    inv_id = client.post(f"/api/projects/{pid}/invites", headers=h,
                         json={"recipient": "", "company_name": "Accord Électricité"}).json()["id"]
    _lien(pid, "Accord Électricité", "12345678900045", "cotraitant", invite_id=inv_id)
    from app.services.groupement_members import cotraitants_pour_formulaires

    def noms():
        db = _db()
        try:
            return [x["name"] for x in cotraitants_pour_formulaires(db, pid)["lignes"]]
        finally:
            db.close()

    assert "Accord Électricité" not in noms()
    db = _db()
    try:
        inv = db.get(ProjectInvite, inv_id)
        inv.accepted_by_user_id = db.query(User).filter(User.email == auth["email"]).one().id
        db.commit()
    finally:
        db.close()
    assert "Accord Électricité" in noms() and "Kerjean Menuiserie" not in noms()
    d = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid}).json()["dossier"]
    dc1 = _pdf_text(base64.b64decode(next(c for c in d["cerfas"] if c["id"] == "dc1")["content_b64"]))
    assert "Accord" in dc1 and "Kerjean" not in dc1


def test_inviter_un_candidat_rattache_lie_l_invitation(client, auth):
    """« Inviter » sur un candidat déjà rattaché : l'invitation lui est liée ; il reste hors des
    formulaires tant qu'elle n'est pas acceptée (jamais un sous-traitant, jamais un autre marché)."""
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Salle des fêtes", "client": "Ville"}).json()["id"]
    autre = client.post("/api/projects/", headers=h, json={"name": "Autre", "client": "Ville"}).json()["id"]
    lien = _lien(pid, "Le Gall Électricité", "12345678900052", "cotraitant")
    lien_st = _lien(pid, "Sous Traitant SARL", "12345678900060", "sous_traitant")
    for projet, link_id in ((autre, lien), (pid, lien_st)):
        r = client.post(f"/api/projects/{projet}/invites", headers=h,
                        json={"company_name": "X", "link_id": link_id})
        assert r.status_code == 200, r.text
    rows = {x["link_id"]: x for x in client.get(f"/api/cotraitants/project/{pid}", headers=h).json()}
    assert rows[lien]["invite_id"] is None and rows[lien_st]["invite_id"] is None
    inv = client.post(f"/api/projects/{pid}/invites", headers=h,
                      json={"company_name": "Le Gall Électricité", "link_id": lien}).json()
    rows = {x["link_id"]: x for x in client.get(f"/api/cotraitants/project/{pid}", headers=h).json()}
    assert rows[lien]["invite_id"] == inv["id"] and rows[lien]["formulaires"] is False
    js = _static("app.js")
    # Réorganisation, vague 2a (A2) : la fenêtre d'invitation unique porte le candidat (link_id) jusqu'à POST /invites.
    assert "v.link_id ? { link_id: v.link_id } : {}" in js and "cotraitantId: fiche ? fiche.id : \"\", link_id: lid" in js


def test_recherche_sans_etapes_3_et_4_ni_rattacher():
    html, js = _static("app.html"), _static("app.js")
    assert ">Rattacher</button>" not in html and "aoAttachFromGroup" not in js + html
    assert "srcGenerate" not in js + html and "src.ct." not in js + html and "Étape 3" not in html
    assert "Ouvrir le marché" in html and "Inviter un partenaire" in html and "srcOuvrirMarche(" in js
    # Réorganisation, vague 2a (A2) : une entreprise trouvée dans le registre s'invite par lien, avec son SIRET (identité
    # relue par le serveur), depuis la recherche de « Qui me complète ? ».
    assert "Ajouter un sous-traitant (DC4)" in html and "rnInviteOpen({ siret: c.siret, name: c.nom, city: c.ville })" in html
    assert '{ company: c, role: "sous_traitant" }' in js
    # Plus de choix « Chef de file / Partenaire » pour une entreprise trouvée dans SIRENE.
    assert '<option value="mandataire">Chef de file</option><option value="cotraitant">Partenaire</option>' not in html


# ═══ 4. « Projets à venir » masqué (PROJETS_A_VENIR=0 par défaut) ═════════════════════════════════

def test_projets_a_venir_masque_par_defaut(client, monkeypatch):
    monkeypatch.delenv("PROJETS_A_VENIR", raising=False)
    assert client.get("/api/public-config").json()["projets_a_venir"] is False
    monkeypatch.setenv("PROJETS_A_VENIR", "1")
    assert client.get("/api/public-config").json()["projets_a_venir"] is True
    from tests.zones import sans_reperes, zone
    brut, js = _static("app.html"), _static("app.js")
    html, nav = sans_reperes(brut), sans_reperes(zone(brut, "menu"))
    # Menu par rubriques (réorganisation, vague 1, 1.3) : « Projets à venir » est un onglet de Trouver des marchés,
    # affiché seulement quand la fonction est activée par le serveur ; aucune entrée du menu.
    assert "amont" not in nav
    assert '{ view: "amont", label: "Projets à venir", ic: "calendar-clock", si: "projets_a_venir" }' in js
    assert '_ongletPermis(t) { return !t.si || (t.si === "admin" ? !!(this.user && this.user.is_admin) : !!this.features[t.si]); },' in js
    assert '<div v-if="features.projets_a_venir" class="card pad dash-block"' in html
    assert "<section v-if=\"view==='amont' && features.projets_a_venir\">" in html
    assert '<button v-if="features.projets_a_venir" class="btn sm ghost" @click="go(\'amont\')">' in html
    assert "features: { projets_a_venir: false }" in js
    assert 'if (!this.features.projets_a_venir) { this.amont.signals = []; return; }' in js
    assert 'if (v === "amont" && !this.features.projets_a_venir) v = "dashboard";' in js


def test_projets_a_venir_aucune_veille_ni_courriel(monkeypatch):
    import app.sourcing.sources.deliberations as deliberations
    from app.services import alerts
    from tests.test_redaction_socle0 import _db
    monkeypatch.delenv("PROJETS_A_VENIR", raising=False)

    def interdit(*a, **k):
        raise AssertionError("aucune délibération ne doit être lue quand « Projets à venir » est masqué")

    monkeypatch.setattr(deliberations.DeliberationSource, "fetch_recent", interdit)
    db = _db()
    try:
        assert alerts.run_amont_alerts(db)["desactive"] is True
    finally:
        db.close()


def test_projets_a_venir_absents_de_la_demo(client, monkeypatch):
    from app.models import Signal, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    from tests.test_redaction_socle0 import _db

    def signaux():
        db = _db()
        try:
            uid = db.query(User).filter(User.email == DEMO_EMAIL).one().id
            return db.query(Signal).filter(Signal.user_id == uid).count()
        finally:
            db.close()

    db = _db()
    try:
        monkeypatch.setenv("PROJETS_A_VENIR", "1")
        ensure_demo(db, force=True)
        assert signaux() == 3                       # les exemples restent prêts pour la refonte
        monkeypatch.delenv("PROJETS_A_VENIR", raising=False)
        ensure_demo(db, force=True)
        assert signaux() == 0                       # par défaut, la vitrine ne les montre plus
    finally:
        db.close()


# ═══ 5. Plateformes Atexo : en-tête honnête, rythme borné, PLACE suspendue, refus sans contournement ═

def _atexo_propre(monkeypatch):
    from app.sourcing import search as search_mod
    from app.sourcing.sources import atexo
    for d in (atexo._REFUS, atexo._CACHE, atexo._RYTHME):
        d.clear()
    monkeypatch.setattr(atexo, "_INTERVALLE_MIN", 0.0)
    search_mod._CB.clear()
    return atexo


def test_atexo_en_tete_honnete_et_rythme_borne(monkeypatch):
    import time
    atexo = _atexo_propre(monkeypatch)
    assert atexo._UA["User-Agent"] == "AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)"
    assert "Mozilla" not in (ROOT / "app/sourcing/sources/atexo.py").read_text(encoding="utf-8")
    monkeypatch.setattr(atexo, "_INTERVALLE_MIN", 0.05)
    t0 = time.monotonic()
    for _ in range(3):
        atexo._attendre_son_tour("https://exemple.test")
    assert time.monotonic() - t0 >= 0.1          # 3 requêtes vers une même plateforme : 2 intervalles


def test_place_suspendue_par_defaut(client, auth, monkeypatch):
    from app.routers import sourcing as sourcing_router
    from app.sourcing.sources.atexo import AtexoSource
    from app.sourcing.sources.boamp import BoampSource
    from app.sourcing.sources.ted import TedSource
    monkeypatch.delenv("PLACE_ACTIF", raising=False)
    noms = [s.name for s in sourcing_router._tender_sources([])]
    assert "PLACE (État)" not in noms and "Mégalis Bretagne" in noms and "BOAMP" in noms
    appels = []
    for cls in (BoampSource, TedSource, AtexoSource):
        monkeypatch.setattr(cls, "search", lambda self, crit: appels.append(self.name) or [])
    r = client.post("/api/sourcing/search", headers=auth["headers"], json={"query": "voirie", "departements": ["29"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "PLACE (État)" not in appels and "PLACE (État)" not in body["sources_queried"]
    assert body["sources_non_consultees"][0]["source"] == "PLACE (État)"
    assert "non consultée" in body["sources_non_consultees"][0]["message"]
    html = _static("app.html")
    assert "{{ n.source }} : non consultée pour le moment" in html and "(BOAMP, TED, PLACE, Mégalis)" not in html
    monkeypatch.setenv("PLACE_ACTIF", "1")
    assert "PLACE (État)" in [s.name for s in sourcing_router._tender_sources([])]
    assert sourcing_router._sources_non_consultees([]) == []


class _RepAtexo:
    def __init__(self, status, text=""):
        self.status_code, self.text, self.url = status, text, "https://marches.megalis.bretagne.bzh/"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_megalis_refuse_le_robot_sans_contournement(monkeypatch, caplog):
    import logging
    import httpx
    from app.sourcing.base import TenderCriteria
    from app.sourcing.schemas import NormalizedTender, Provenance
    from app.sourcing.search import _CB, TenderSearchService
    from app.sourcing.sources.atexo import MEGALIS
    from app.sourcing.sources.boamp import BoampSource
    _atexo_propre(monkeypatch)
    requetes = []

    class _Client:
        def __init__(self, *a, headers=None, **k):
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **k):
            requetes.append(self.headers.get("User-Agent"))
            return _RepAtexo(403, "Forbidden")

        post = get

    monkeypatch.setattr(httpx, "Client", _Client)
    avis = NormalizedTender(objet="Voirie communale", acheteur="Commune de Plouzané", departements=["29"],
                            date_limite="2099-01-01",
                            provenance=Provenance(source="BOAMP", official_ref="26-1",
                                                  source_url="https://www.boamp.fr/avis/detail/26-1"))
    avis.dedup_key = "voirie|plouzane|2099-01-01"
    monkeypatch.setattr(BoampSource, "search", lambda self, crit: [avis])
    service = TenderSearchService([BoampSource(), MEGALIS])
    crit = TenderCriteria(query="voirie", departements=["29"])
    with caplog.at_level(logging.WARNING, logger="adjugo"):
        resultats = [service.search(crit, {}, {}) for _ in range(4)]
    for res in resultats:                                        # la recherche continue avec BOAMP
        assert [t.acheteur for t in res["tenders"]] == ["Commune de Plouzané"]
        err = next(e for e in res["errors"] if e.source == "Mégalis Bretagne")
        assert "n'accepte pas" in err.message
    assert requetes == ["AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)"]   # une seule requête, honnête
    alertes = [r for r in caplog.records if "refuse l'en-tête honnête" in r.getMessage()]
    assert len(alertes) == 1                                     # un seul avertissement dans l'heure
    assert not _CB.get("Mégalis Bretagne") or _CB["Mégalis Bretagne"]["fails"] == 0
    assert not [r for r in caplog.records if "Disjoncteur sourcing ouvert" in r.getMessage()]


def test_doc_autorisations_plateformes():
    doc = (ROOT / "docs" / "AUTORISATIONS_PLATEFORMES.md").read_text(encoding="utf-8")
    assert "Brouillon 1 — Mégalis Bretagne" in doc and "Brouillon 2 — PLACE" in doc and "AIFE" in doc
    assert "AdjugoBot/1.0" in doc and "PLACE_ACTIF=1" in doc and "consortium" not in doc.lower()


# ═══ 6. Liste des pièces : la signature n'est exigée au dépôt que si le règlement l'impose ═════════

def test_liste_des_pieces_signature_juste(client, auth):
    from app.routers.checklist import PIECES_STANDARD, SIGNATURE_AIDE
    aide = {p["id"]: p["help"] for p in PIECES_STANDARD}
    assert SIGNATURE_AIDE == "À signer si le règlement l'exige ; sinon, signature à l'attribution."
    for pid in ("dc1", "dc2", "honneur"):
        assert SIGNATURE_AIDE in aide[pid] and "dater et signer" not in aide[pid] and "et signer." not in aide[pid]
    assert "à l'attribution" in aide["attri1"] and "avant signature" not in aide["attri1"]
    h = auth["headers"]
    projet = client.post("/api/projects/", headers=h, json={"name": "École", "client": "Ville"}).json()["id"]
    items = {i["id"]: i for i in client.get(f"/api/checklist/{projet}", headers=h).json()["checklist"]}
    assert SIGNATURE_AIDE in items["dc1"]["help"]
    js = _static("app.js")
    assert "et <b>signez</b> (acte d'engagement + déclaration sur l'honneur)" not in js
    assert "<b>Signez-le si le règlement l'exige</b>" in js


# ═══ 7. Lien de démonstration sans clé : « incomplet », pas « plus valide » ═════════════════════════

def test_lien_demo_incomplet(tmp_path):
    from tests.test_demo_lien_prive import _page_demo
    page = _static("demo.html")
    carte = re.search(r'<section id="incomplet".*?</section>', page, re.S).group(0).replace("&nbsp;", " ")
    assert "Ce lien est incomplet : il manque la clé après le signe #." in carte
    assert "Copiez le lien en entier depuis le message reçu." in carte
    r = _page_demo(tmp_path, "", None)                      # adresse sans « # »
    assert r["visibles"] == ["incomplet"] and r["appels"] == []
    r = _page_demo(tmp_path, "", "perime")                  # clé changée : refusée par le serveur
    assert r["visibles"] == ["invalide"]
    assert "Ce lien de démonstration n'est plus valide." in page


# ═══ Relecture des correctifs (remarques reproduites, chacune échouait avant la correction) ═══════════

def _accepter(inv_id, email, part=None):
    """L'invité accepte depuis son compte ; `part` (dict) : il soumet aussi sa part."""
    from app.models import ProjectContribution, ProjectInvite, User
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        inv = db.get(ProjectInvite, inv_id)
        inv.accepted_by_user_id = db.query(User).filter(User.email == email).one().id
        if part is not None:
            db.add(ProjectContribution(invite_id=inv_id, project_id=inv.project_id, owner_id=inv.owner_id,
                                       role="cotraitant", status="submitted", **part))
        db.commit()
    finally:
        db.close()


def _carte(client, h, pid):
    return {x["name"]: x for x in client.get(f"/api/cotraitants/project/{pid}", headers=h).json()}


def _formulaires(pid):
    from app.services.groupement_members import cotraitants_pour_formulaires
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        r = cotraitants_pour_formulaires(db, pid)
        return [x["name"] for x in r["lignes"]], r["ecartes"], r["hors_ligne_en_attente"]
    finally:
        db.close()


def test_composition_retenue_puis_inviter_relie_le_candidat(client, auth):
    """« Retenir cette composition » crée le rattachement ; « Inviter X » sur la carte de simulation part
    sans link_id : le serveur relie l'invitation au candidat de même nom. Accepté avec sa part : X est
    dans le DC1 du formulaire seul ET du dossier, sans avertissement faux."""
    import base64
    from tests.test_redaction_socle0 import ANALYSIS, _company, _pdf_text, _set_analysis
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h, json={"name": "Mairie", "client": "Ville"}).json()["id"]
    _set_analysis(pid, ANALYSIS)
    r = client.post(f"/api/projects/{pid}/groupement/simulate", headers=h, json={"members": [
        {"kind": "saisi", "name": "Kervern Charpente", "siret": "12345678900094", "ca_n1": 400000, "effectif": 5}]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/projects/{pid}/groupement/retenir", headers=h,
                    json={"simulation_id": r.json()["simulation_id"]})
    assert r.status_code == 200, r.text
    lien = next(m["link_id"] for m in r.json()["plan"]["members"] if m["name"] == "Kervern Charpente")
    carte = _carte(client, h, pid)["Kervern Charpente"]
    assert (carte["link_id"], carte["invite_id"], carte["formulaires"]) == (lien, None, False)
    # « Inviter Kervern Charpente » sur la carte de simulation : membre de simulation, sans link_id.
    inv = client.post(f"/api/projects/{pid}/invites", headers=h,
                      json={"recipient": "", "company_name": "KERVERN  charpente"}).json()
    carte = _carte(client, h, pid)["Kervern Charpente"]
    assert carte["link_id"] == lien and carte["invite_id"] == inv["id"]
    assert carte["invitation"] == "envoyee" and carte["formulaires"] is False
    _accepter(inv["id"], auth["email"], {"company_name": "Kervern Charpente", "siret": "12345678900094"})
    assert _carte(client, h, pid)["Kervern Charpente"]["formulaires"] is True
    assert _formulaires(pid) == (["Kervern Charpente"], [], [])
    r = client.post(f"/api/cerfa/{pid}/dc1", headers=h)
    assert r.status_code == 200 and "Kervern" in _pdf_text(r.content)
    assert "X-Adjugo-Avertissements" not in r.headers
    d = client.post("/api/sourcing/documents", headers=h, json={"project_id": pid}).json()["dossier"]
    dc1 = _pdf_text(base64.b64decode(next(c for c in d["cerfas"] if c["id"] == "dc1")["content_b64"]))
    assert "Kervern" in dc1 and not [w for w in d["warnings"] if "invitation acceptée" in w]
    # L'écran passe aussi le rattachement du plan aux boutons « Inviter » de la composition retenue.
    assert "(plan.members || []).find(x => x && x.link_id" in _static("app.js")


def test_invitation_d_avant_la_correction_reconnue_par_nom_ou_siret(client, auth):
    """Production : invitation créée sans lien (avant cette correction), puis acceptée. Le rattachement de
    la même entreprise (même nom donné par le chef de file, ou même SIRET dans la part) entre dans les
    formulaires ; un homonyme partiel, non, ni une entreprise qui n'a accepté qu'en sous-traitant."""
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Halle", "client": "Ville"}).json()["id"]
    i1 = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Le Bihan Maçonnerie"}).json()
    i2 = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Nom libre"}).json()
    i3 = client.post(f"/api/projects/{pid}/invites", headers=h,                # accepté en SOUS-TRAITANT
                     json={"company_name": "Le Bihan", "role": "sous_traitant"}).json()
    _lien(pid, "Le Bihan Maçonnerie", "12345678900102", "cotraitant")
    _lien(pid, "Tanguy Couverture SAS", "12345678900110", "cotraitant")
    _lien(pid, "Le Bihan", "12345678900128", "cotraitant")
    _accepter(i1["id"], auth["email"])
    _accepter(i2["id"], auth["email"], {"company_name": "Tanguy", "siret": "12345678900110"})
    _accepter(i3["id"], auth["email"])
    lignes, ecartes, _ = _formulaires(pid)
    assert lignes == ["Le Bihan Maçonnerie", "Tanguy Couverture SAS"] and ecartes == ["Le Bihan"]


def test_refus_ou_retrait_puis_nouvelle_invitation(client, auth):
    """Après un refus ou un retrait, la carte le dit et propose « Inviter à nouveau » ; la nouvelle
    invitation est reliée au candidat, qui entre dans les formulaires quand il l'accepte."""
    from app.models import ProjectInvite, utcnow
    from tests.test_redaction_socle0 import _db
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Stade", "client": "Ville"}).json()["id"]
    lien = _lien(pid, "Le Goff Plomberie", "12345678900086", "cotraitant")
    inv1 = client.post(f"/api/projects/{pid}/invites", headers=h,
                       json={"company_name": "Le Goff Plomberie", "link_id": lien}).json()["id"]
    db = _db()
    try:
        db.get(ProjectInvite, inv1).declined_at = utcnow()
        db.commit()
    finally:
        db.close()
    c = _carte(client, h, pid)["Le Goff Plomberie"]
    assert (c["invitation"], c["formulaires"]) == ("declinee", False)
    inv2 = client.post(f"/api/projects/{pid}/invites", headers=h,
                       json={"company_name": "Le Goff Plomberie", "link_id": lien}).json()["id"]
    c = _carte(client, h, pid)["Le Goff Plomberie"]
    assert (c["invite_id"], c["invitation"]) == (inv2, "envoyee")
    # Une invitation encore active n'est jamais remplacée par une autre.
    inv_bis = client.post(f"/api/projects/{pid}/invites", headers=h,
                          json={"company_name": "Le Goff Plomberie", "link_id": lien}).json()["id"]
    assert _carte(client, h, pid)["Le Goff Plomberie"]["invite_id"] == inv2
    assert client.delete(f"/api/projects/{pid}/invites/{inv_bis}", headers=h).status_code == 200
    assert client.delete(f"/api/projects/{pid}/invites/{inv2}", headers=h).status_code == 200
    c = _carte(client, h, pid)["Le Goff Plomberie"]
    assert (c["invitation"], c["formulaires"]) == ("retiree", False)
    inv3 = client.post(f"/api/projects/{pid}/invites", headers=h,          # sans link_id : par le nom
                       json={"company_name": "Le Goff Plomberie"}).json()["id"]
    assert _carte(client, h, pid)["Le Goff Plomberie"]["invite_id"] == inv3
    _accepter(inv3, auth["email"])
    assert _formulaires(pid)[0] == ["Le Goff Plomberie"]
    html = _static("app.html")
    assert "c.invitation==='envoyee'" in html and "\"A décliné l'invitation\" : 'Invitation retirée'" in html
    assert "{{ c.invitation ? 'Inviter à nouveau' : 'Inviter' }}" in html


def test_sous_traitant_qui_decline_sort_du_dc4(client, auth):
    from app.models import ProjectInvite, utcnow
    from tests.test_redaction_socle0 import _db
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Piscine", "client": "Ville"}).json()["id"]
    inv_id = client.post(f"/api/projects/{pid}/invites", headers=h,
                         json={"company_name": "Refus SARL", "role": "sous_traitant"}).json()["id"]
    _lien(pid, "Refus SARL", "12345678900078", "sous_traitant", invite_id=inv_id)
    _lien(pid, "Déclaré SARL", "12345678900136", "sous_traitant")            # ajouté directement (DC4)
    assert _formulaires(pid)[0] == ["Refus SARL", "Déclaré SARL"]            # invitation encore active
    db = _db()
    try:
        db.get(ProjectInvite, inv_id).declined_at = utcnow()
        db.commit()
    finally:
        db.close()
    lignes, ecartes, _ = _formulaires(pid)
    assert lignes == ["Déclaré SARL"] and ecartes == ["Refus SARL"]


def test_partenaire_hors_ligne_dans_les_formulaires_apres_son_accord_seulement(client, auth):
    """Membre « hors ligne » (sans invitation) inscrit à la convention : absent du DC1 tant que le chef de
    file n'a pas coché son accord, et l'écran le dit ; présent une fois l'accord déclaré."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.models import User
    from tests.test_convention_groupement import _db, _gen, _groupement, _pdf_text
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    db = _db()
    try:
        owner = db.query(User).filter(User.email == auth["email"]).first()
        ct = Cotraitant(user_id=owner.id, name="Kerjean Menuiserie", siret="55566677700088",
                        representant_legal="Anne Kerjean", city="Brest")
        db.add(ct); db.flush()
        lk = ProjectCotraitant(project_id=pid, cotraitant_id=ct.id, role="cotraitant", lot="Lot 5", source="reseau")
        db.add(lk); db.commit()
        link_id = lk.id
    finally:
        db.close()
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={
        "membres_hors_ligne": [{"link_id": link_id, "prix_lot_ht": 15000}]}).status_code == 200
    c = _gen(client, h, pid).json()
    assert "Kerjean Menuiserie" in c["content_md"]
    r = client.post(f"/api/cerfa/{pid}/dc1", headers=h)
    assert r.status_code == 200, r.text
    assert "Kerjean" not in _pdf_text(r.content) and "Le Gall" in _pdf_text(r.content)
    from urllib.parse import unquote
    assert "Kerjean Menuiserie : accord hors ligne pas encore déclaré" in unquote(r.headers["X-Adjugo-Avertissements"])
    carte = _carte(client, h, pid)["Kerjean Menuiserie"]
    assert carte["hors_ligne_en_attente"] is True and carte["formulaires"] is False
    r = client.post(f"/api/projects/{pid}/groupement/convention/hors-ligne/{link_id}", headers=h,
                    json={"accord_recueilli": True, "signataire_nom": "Anne Kerjean"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/cerfa/{pid}/dc1", headers=h)
    assert "Kerjean" in _pdf_text(r.content) and "X-Adjugo-Avertissements" not in r.headers
    carte = _carte(client, h, pid)["Kerjean Menuiserie"]
    assert carte["accord_hors_ligne"] is True and carte["formulaires"] is True
    html = _static("app.html")
    assert "Le plus simple est de les inviter" in html
    assert 'aoGrpInvite({ name: c.company, link_id: c.link_id })' in html


def test_inviter_un_membre_hors_ligne_le_fait_compter_comme_invite(client, auth):
    """Un partenaire choisi hors ligne puis invité compte comme invité : plus de « n'est plus rattaché »."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.models import User
    from tests.test_convention_groupement import _db, _groupement
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    db = _db()
    try:
        owner = db.query(User).filter(User.email == auth["email"]).first()
        ct = Cotraitant(user_id=owner.id, name="Kerjean Menuiserie", siret="55566677700088", city="Brest")
        db.add(ct); db.flush()
        lk = ProjectCotraitant(project_id=pid, cotraitant_id=ct.id, role="cotraitant", lot="Lot 5", source="reseau")
        db.add(lk); db.commit()
        link_id = lk.id
    finally:
        db.close()
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
               json={"membres_hors_ligne": [{"link_id": link_id, "prix_lot_ht": 15000}]})
    client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Kerjean Menuiserie", "link_id": link_id})
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert not [m for m in g["manques"] if "n'est plus rattaché" in m]
    assert [m for m in g["manques"] if m.startswith("Kerjean Menuiserie n'a pas encore soumis sa part")]


def test_export_zip_et_formulaire_seul_disent_qui_manque(client, auth):
    import io
    import zipfile
    from urllib.parse import unquote
    from tests.test_redaction_socle0 import _company
    h = auth["headers"]
    _company(client, h)
    pid = client.post("/api/projects/", headers=h, json={"name": "Gymnase", "client": "Ville"}).json()["id"]
    _lien(pid, "Kerjean Menuiserie", "12345678900029", "cotraitant")         # ancien « Rattacher »
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text
    av = unquote(r.headers["X-Adjugo-Avertissements"])
    assert av.startswith("Kerjean Menuiserie : pas encore d'invitation acceptée")
    sommaire = zipfile.ZipFile(io.BytesIO(r.content)).read("00_SOMMAIRE.txt").decode("utf-8")
    assert "A VERIFIER AVANT DEPOT" in sommaire and "Kerjean Menuiserie : pas encore d'invitation" in sommaire
    r = client.post(f"/api/cerfa/{pid}/dc2", headers=h)
    assert r.status_code == 200 and "Kerjean" in unquote(r.headers["X-Adjugo-Avertissements"])
    js = _static("app.js")
    assert js.count("this.avertissementsFichier(r)") == 2 and 'r.headers.get("X-Adjugo-Avertissements")' in js


def test_signature_dans_les_documents_produits(client, auth):
    """Déclaration sur l'honneur et convention : signature au dépôt seulement si le règlement l'exige. Une
    convention déjà figée garde son texte (modèle 1) : pas rendue caduque par la correction."""
    from app.services import groupement_convention as gc
    from app.services.cerfa import GENERATORS
    from tests.test_convention_groupement import _db, _gen, _groupement, _pdf_text
    txt = " ".join(_pdf_text(GENERATORS["honneur"]({"name": "Breizh", "city": "Lorient",
                                                     "representant_legal": "Eliot"}, {"name": "École"})).split())
    assert "signez avant dépôt" not in txt and "À signer si le règlement de la consultation l'exige" in txt
    assert "sauf si le règlement demande de le signer dès le dépôt" in gc.NATURE_ACCORD
    h = auth["headers"]
    pid, _invs = _groupement(client, auth, n=1)
    c = _gen(client, h, pid).json()
    assert "restent à signer au moment du dépôt" not in c["content_md"]
    assert "se signent au dépôt si le règlement de la consultation l'exige" in c["content_md"]
    from app.models import GroupementConvention, Project
    db = _db()
    try:
        conv = db.query(GroupementConvention).filter(GroupementConvention.project_id == pid).one()
        project = db.get(Project, pid)
        # Modèle courant (3 depuis le contrôle des bugs, deuxième passe : « 1 jour » ; même phrase de signature que le 2).
        assert conv.params["modele_texte"] == gc.MODELE_TEXTE == 3 and not gc.is_stale(db, project, conv)
        # Convention figée AVANT la correction : modèle 1, même empreinte qu'à sa génération.
        ancien = gc.build_context(db, project, conv, gc._company_for(db, project), version=conv.version)["ctx"]
        ancien["modele"] = 1
        texte = gc.render(ancien)
        assert "restent à signer au moment du dépôt" in texte
        params = dict(conv.params)
        params.pop("modele_texte")
        conv.params, conv.content_md, conv.content_hash = params, texte, gc.sha256(texte)
        db.commit()
        assert gc.modele_de(conv) == 1 and not gc.is_stale(db, project, conv)
    finally:
        db.close()


def test_projets_a_venir_ni_espace_partenaire_ni_vitrine():
    inv, land = _static("invite.html"), _static("landing.html")
    # Vague 2b (B3, étude § 7.6) : l'entrée « Projets à venir » de l'espace partenaire, qui affichait en fait la recherche
    # de marchés, est retirée avec le menu (l'espace se réduit à la part du partenaire).
    assert "nav-amont" not in inv and "></i>Projets à venir<" not in inv and "projets_a_venir" not in inv
    assert "veille amont" not in land.lower() and "fins de contrat à suivre" in land


def test_aucune_promesse_d_invention_restante():
    for name in ("app.html", "app.js", "redaction-partenaire.js", "invite.html", "landing.html",
                 "demo/avis-boamp.html", "demo/deliberation.html"):
        s = _static(name)
        for f in ("n'invente aucun", "Il n'en invente aucune", "rien n'est inventé", "Aucune donnée n'est inventée",
                  "jamais de contenu inventé"):
            assert f not in s, (name, f)
    assert "relisez chaque fait avant d'envoyer" in _static("redaction-partenaire.js")


def test_radar_fins_de_contrat_departements_01_a_09(monkeypatch):
    from app.services import renewal
    vues = _boamp_capture(monkeypatch, [{"idweb": "21-1", "objet": "Nettoyage", "nomacheteur": "Vence",
                                         "code_departement": ["6"], "dateparution": "2024-01-10"}])
    rows = renewal._fetch_attributions("nettoyage", ["06", "29"])
    where = vues[0]["where"]
    for f in ("06", "6", "29"):
        assert f'code_departement like "{f}"' in where
    assert 'like "9"' not in where and rows[0]["dept"] == "06"


def test_demo_aucun_partenaire_rattache_sans_accord(client):
    from app.models import Project, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    from app.services.groupement_members import etat_des_liens
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        ensure_demo(db, force=True)
        uid = db.query(User).filter(User.email == DEMO_EMAIL).one().id
        etats = {}
        for p in db.query(Project).filter(Project.user_id == uid).all():
            etats.update({(p.name, k): v["formulaires"] for k, v in etat_des_liens(db, p.id).items()})
    finally:
        db.close()
    assert etats and all(etats.values()), etats


def test_note_pages_juridiques_pour_eliot():
    doc = (ROOT / "docs" / "A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md").read_text(encoding="utf-8")
    for lieu in ("cgv.md`, l. 23", "politique-confidentialite.md`, l. 152", "securite.html`, l. 103",
                 "Co-traitants vérifiés", "Veille amont", "aucune donnée inventée"):
        assert lieu in doc, lieu
    assert "consortium" not in doc.lower()
