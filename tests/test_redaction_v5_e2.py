"""
Rédaction, vague 5 — CHANTIER E2 « Mes preuves » depuis les sources publiques (étude « rédaction » § 6.7,
décision 7 b ; contrat docs/REDACTION_V5.md, section E2).

Invariants vérifiés :
 • « Retrouver mes marchés publics » lit les DECP où l'entreprise est titulaire 1, 2 OU 3 ; pour chaque marché :
   acheteur, objet, montant d'attribution, date, rôle (seule, en groupement conjoint ou solidaire) ; PROPOSÉ,
   l'utilisateur coche ; libellé « marché attribué, source publique DECP » daté ; le texte dit « attribué »,
   jamais « réalisé » ; valeurs bizarres (« CDL », « MQ NC », 1 €, 0 €, date future…) montrées telles quelles,
   avec une alerte, rien d'inventé ;
 • qualifications RGE lues dans la liste de l'ADEME avec leurs dates : proposées, cochées ; une qualification
   expirée exclue et signalée ; Qualibat hors RGE reste manuel ;
 • les champs tirés d'une source publique ne changent pas tant que la fiche garde cette source ;
 • le client n'envoie que des CLÉS : le contenu est relu côté serveur ; une clé inconnue ne crée rien ;
 • panne de l'API : message honnête (jamais « aucun marché »), rien d'inventé ; cache ; lecture précédente
   rendue AVEC SA DATE ;
 • un partenaire (lien ou compte) remplit SES références et qualifications de part depuis ses preuves ou ses
   sources publiques (SIRET de SA part) ; jamais les preuves du chef de file ; verrou de version ;
 • réseau : fetch_decp et wins_by_siren lisent les titulaires 2 et 3 ; l'historique réel de co-traitance
   (« dont N en groupement ») nourrit la confiance du réseau, sans jamais dire le mot interdit ;
 • démo : exemple FICTIF, aucun appel réseau, aucune écriture ;
 • écran : fonctions pures sous Node, textes échappés, zéro émoji, SRI.
AUCUN appel réseau : toutes les sources sont simulées (et le transport HTTP est coupé par sécurité).
"""
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import date, timedelta

import pytest

from app.services import preuves as pv
from app.services import sources_publiques as sp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")

SIREN = "123456782"                     # SIREN fictif de l'entreprise
SIRET = SIREN + "00017"
AUTRE = "98765432100015"                # co-titulaire fictif
ACH1 = "21290232900016"                 # acheteur fictif dont le nom est retrouvé dans l'annuaire
ACH2 = "20000000100018"                 # acheteur fictif dont le nom n'est pas retrouvé
NOM_ACH1 = "COMMUNE DE KERBRAT (FICTIVE)"


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _jour(n=0):
    return (date.today() + timedelta(days=n)).isoformat()


def _rows_decp():
    base = {"nature": "Marché", "titulaire_id_2": "CDL", "titulaire_id_3": "CDL", "lieuexecution_code": "29"}
    return [
        dict(base, id="M-2024-01", objet="Réfection de la toiture de l'école Jules-Ferry", montant=85000.0,
             datenotification="2024-05-10", acheteur_id=ACH1, titulaire_id_1=SIRET,
             typegroupementoperateurs="Pas de groupement"),
        dict(base, id="M-2023-07", objet="RENOVATION ENERGETIQUE DU GYMNASE - LOT 2 COUVERTURE", montant=268900.5,
             datenotification="2023-09-03", acheteur_id=ACH2, titulaire_id_1=AUTRE, titulaire_id_2=SIRET,
             typegroupementoperateurs="Solidaire"),
        dict(base, id="M-2022-03", objet="CDL", montant=12000.0, datenotification="2022-03-01", acheteur_id=ACH1,
             titulaire_id_1=SIRET, typegroupementoperateurs="Pas de groupement"),
        dict(base, id="M-2021-09", objet="Entretien des toitures communales", montant=1.0,
             datenotification=_jour(30), acheteur_id=ACH1, titulaire_id_1=SIRET,
             typegroupementoperateurs="Pas de groupement"),
        dict(base, id="M-2021-02", objet="Zinguerie de la mairie", montant=0, datenotification="2021-02-01",
             acheteur_id="MQ NC", titulaire_id_1=AUTRE, titulaire_id_2="11122233300014", titulaire_id_3=SIRET,
             typegroupementoperateurs="Pas de groupement"),
        dict(base, id="M-2024-01", objet="Réfection de la toiture de l'école Jules-Ferry", montant=85000.0,
             datenotification="2024-05-10", acheteur_id=ACH1, titulaire_id_1=SIRET,
             typegroupementoperateurs="Pas de groupement"),                       # même marché, lu deux fois
        dict(base, id="M-2020-11", objet="Travaux de couverture " + "et de zinguerie des bâtiments communaux " * 12,
             montant=50000.0, datenotification="2020-11-05", acheteur_id=ACH1, titulaire_id_1=SIRET,
             typegroupementoperateurs="Conjoint"),
        # Format réel de DECP (2022) : `nature` vaut « Marché », `techniques` dit « Accord-cadre ». L'accord-cadre
        # lui-même (identifiant d'accord-cadre « CDL »), puis un marché subséquent (qui désigne l'accord-cadre).
        dict(base, id="AC-2019-04", objet="Accord-cadre d'entretien des couvertures", montant=1000000.0,
             datenotification="2019-04-01", acheteur_id=ACH1, titulaire_id_1=SIRET, techniques="Accord-cadre",
             idaccordcadre="CDL", typegroupementoperateurs="Pas de groupement"),
        dict(base, id="MS-2019-09", objet="Marché subséquent n° 1 : école des Tilleuls", montant=38000.0,
             datenotification="2019-09-01", acheteur_id=ACH1, titulaire_id_1=SIRET, techniques="Accord-cadre",
             idaccordcadre="AC-2019-04", typegroupementoperateurs="Pas de groupement"),
    ]


def _rows_rge():
    q = {"nom_certificat": "QUALIBAT-RGE", "organisme": "qualibat", "lien_date_debut": "2024-03-01"}
    return [
        dict(q, siret=SIRET, code_qualification="5112", nom_qualification="Isolation par l'extérieur (5112)",
             domaine="Isolation des murs par l'extérieur", lien_date_fin=_jour(400)),
        dict(q, siret=SIRET, code_qualification="5112", nom_qualification="Isolation par l'extérieur (5112)",
             domaine="Isolation des toitures par l'extérieur", lien_date_fin=_jour(400)),
        dict(q, siret=SIREN + "00025", code_qualification="8611", nom_qualification="Fenêtres de toit (8611)",
             domaine="Fenêtres, volets, portes extérieures", lien_date_debut="2020-01-01", lien_date_fin=_jour(-30)),
        dict(siret=SIRET, code_qualification="QPV", nom_qualification="QualiPV Elec", nom_certificat="QualiPV",
             organisme="qualitenr", domaine="Panneaux photovoltaïques", lien_date_debut="2021-06-01",
             lien_date_fin="2099-01-01"),
        dict(q, siret="99999999900011", code_qualification="1111", nom_qualification="Une autre entreprise",
             domaine="X", lien_date_fin=_jour(100)),
    ]


class FauxSources:
    """Les trois API publiques, simulées : DECP, liste RGE de l'ADEME, annuaire des entreprises."""

    def __init__(self):
        self.calls, self.params, self.fail = [], [], set()
        self.decp, self.rge = _rows_decp(), _rows_rge()

    def __call__(self, url, params, timeout=None):
        if "data.economie.gouv.fr" in url:
            kind = "decp"
        elif "data.ademe.fr" in url:
            kind = "rge"
        elif "recherche-entreprises" in url:
            kind = "sirene"
        else:
            raise AssertionError(f"appel réseau inattendu : {url}")
        self.calls.append(kind)
        self.params.append((kind, dict(params)))
        if kind in self.fail:
            raise RuntimeError("panne simulée")
        if kind == "decp":
            m = re.search(r"\d{9}", params.get("where", ""))
            rows = [r for r in self.decp if any(str(r.get(f"titulaire_id_{i}") or "").startswith(m.group(0))
                                                for i in (1, 2, 3))]
            off, lim = int(params.get("offset") or 0), int(params.get("limit") or 100)
            return {"total_count": len(rows), "results": rows[off:off + lim]}
        if kind == "rge":
            return {"total": len(self.rge), "results": list(self.rge)}
        q = str(params.get("q") or "")
        if q == ACH1[:9]:
            return {"results": [{"siren": q, "nom_complet": NOM_ACH1}]}
        return {"results": []}


@pytest.fixture(autouse=True)
def sources(monkeypatch):
    """Sources simulées, cache vidé ; le transport HTTP réel est coupé : un appel réseau ferait échouer le test."""
    import httpx
    fake = FauxSources()
    monkeypatch.setattr(sp, "_http_get", fake)
    reels = []

    def coupe(self, request):
        reels.append(str(request.url))
        raise httpx.ConnectError("réseau coupé (test)", request=request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", coupe)
    sp.vider_cache()
    yield fake
    sp.vider_cache()
    assert reels == [], f"appel réseau réel : {reels}"


def _org(client, siret=SIRET, company="Couverture Kerbrat (test)"):
    email = f"e2_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": "Dirigeant", "company_name": company})
    assert r.status_code == 201, r.text
    from app.models import Company, User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        c = db.query(Company).filter(Company.user_id == u.id).first()
        c.siret = siret
        db.commit()
        uid = u.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, uid


def _par_id(marches, decp_id):
    return next(m for m in marches if m["decp_id"] == decp_id)


# ═══ 1. Les DECP : titulaires 1, 2 ou 3, valeurs montrées telles quelles ═══════════════════════════

def test_decp_lit_les_titulaires_1_2_3_et_montre_les_valeurs_telles_quelles(sources):
    r = sp.marches(SIRET)
    assert r["statut"] == "ok" and r["consulte_le"] == pv.aujourd_hui().isoformat()
    kind, params = sources.params[0]
    assert kind == "decp"
    for i in (1, 2, 3):
        assert f'startswith(titulaire_id_{i}, "{SIREN}")' in params["where"]
    ms = r["marches"]
    assert len(ms) == 8                                   # le marché lu deux fois n'apparaît qu'une fois
    m1 = _par_id(ms, "M-2024-01")
    assert m1["affiche"]["acheteur"] == NOM_ACH1 and m1["affiche"]["position"] == 1
    assert m1["valeur"] == {"objet": "Réfection de la toiture de l'école Jules-Ferry", "acheteur": NOM_ACH1,
                            "montant_ht": 85000, "annee": 2024, "role": "seul"}
    assert m1["affiche"]["role_libelle"] == "Seule" and m1["alertes"] == [] and not m1["manque"]
    # Titulaire 2 d'un groupement solidaire : majuscules gardées, acheteur non retrouvé (SIRET seul, rien deviné).
    m2 = _par_id(ms, "M-2023-07")
    assert m2["affiche"]["objet"] == "RENOVATION ENERGETIQUE DU GYMNASE - LOT 2 COUVERTURE"
    assert m2["affiche"]["position"] == 2 and m2["valeur"]["role"] == "groupement_solidaire"
    assert m2["affiche"]["role_libelle"] == "En groupement solidaire, avec 1 autre entreprise"
    assert "acheteur" not in m2["valeur"] and m2["affiche"]["acheteur_siret"] == ACH2
    assert m2["valeur"]["montant_ht"] == 268900.5
    # « CDL » : montré tel quel, ne peut pas devenir une référence.
    m3 = _par_id(ms, "M-2022-03")
    assert m3["affiche"]["objet"] == "CDL" and "« CDL »" in m3["manque"] and "objet" not in m3["valeur"]
    # 1 € : montré et gardé (l'utilisateur confirme en cochant) ; date future : l'année n'est pas reprise.
    m4 = _par_id(ms, "M-2021-09")
    assert m4["valeur"]["montant_ht"] == 1 and "annee" not in m4["valeur"]
    assert any("inhabituel" in a for a in m4["alertes"]) and any("futur" in a for a in m4["alertes"])
    assert not any("Accord-cadre" in a for a in m4["alertes"])
    # Titulaire 3, « pas de groupement » avec d'autres titulaires : rôle non deviné ; « MQ NC » ; montant 0.
    m5 = _par_id(ms, "M-2021-02")
    assert m5["affiche"]["position"] == 3 and "role" not in m5["valeur"]
    assert m5["affiche"]["role_libelle"] == "Rôle non précisé dans DECP"
    assert any("précisez votre rôle" in a for a in m5["alertes"])
    assert any("Acheteur non renseigné" in a for a in m5["alertes"]) and "acheteur" not in m5["valeur"]
    assert "montant_ht" not in m5["valeur"] and any("n'est pas repris" in a for a in m5["alertes"])
    # Objet long : la fiche en garde le début, le texte complet va dans la description.
    m7 = _par_id(ms, "M-2020-11")
    assert len(m7["valeur"]["objet"]) <= 300 and m7["valeur"]["objet"].endswith("…")
    assert m7["valeur"]["description"].startswith("Travaux de couverture et de zinguerie")
    assert m7["valeur"]["role"] == "groupement_conjoint" and m7["affiche"]["role_libelle"] == "En groupement conjoint"
    # L'accord-cadre lui-même : son montant est un maximum (alerte), il n'est pas repris dans la fiche ; le marché
    # subséquent porte ce qui est commandé.
    ac = _par_id(ms, "AC-2019-04")
    assert any("Accord-cadre" in a and "n'est pas repris" in a for a in ac["alertes"])
    assert "montant_ht" not in ac["valeur"] and ac["releve"]["montant_ht"] is None     # vide, et verrouillé
    assert ac["affiche"]["montant"] == 1000000.0             # montré tel quel
    assert _par_id(ms, "MS-2019-09")["alertes"] == [] and _par_id(ms, "MS-2019-09")["valeur"]["montant_ht"] == 38000


def test_panne_message_honnete_cache_et_lecture_precedente_datee(sources, monkeypatch):
    sources.fail = {"decp"}
    r = sp.marches(SIRET)
    assert r["statut"] == "panne" and "ne répondent pas" in r["message"] and r["marches"] == []
    assert "aucun" not in r["message"].lower()
    sources.fail = set()
    n = len(sources.calls)
    monkeypatch.setattr(sp, "PANNE_S", 0)
    r = sp.marches(SIRET)
    assert r["statut"] == "ok" and not r["ancien"]
    appels = len(sources.calls) - n
    assert sp.marches(SIRET)["statut"] == "ok" and len(sources.calls) - n == appels      # servi par le cache
    # Cache échu et API en panne : la lecture précédente est rendue, AVEC SA DATE.
    monkeypatch.setattr(sp, "TTL_S", 0)
    sources.fail = {"decp", "sirene"}
    r = sp.marches(SIRET)
    assert r["statut"] == "ok" and r["ancien"] is True
    assert "voici la lecture du " + pv.aujourd_hui().strftime("%d/%m/%Y") in r["message"]
    assert len(r["marches"]) == 8


def test_rge_valables_proposees_expiree_exclue_et_signalee(sources):
    r = sp.qualifications_rge(SIRET)
    assert r["statut"] == "ok"
    assert sources.params[0][1]["qs"] == f"siret:{SIREN}*"
    qs = {q["valeur"]["numero"]: q for q in r["qualifications"]}
    assert set(qs) == {"5112", "QPV"}                      # une autre entreprise jamais reprise
    q = qs["5112"]
    assert q["valeur"]["nom"] == "QUALIBAT-RGE : Isolation par l'extérieur (5112)"
    assert q["valeur"]["organisme"] == "Qualibat"
    assert q["affiche"]["domaines"] == ["Isolation des murs par l'extérieur", "Isolation des toitures par l'extérieur"]
    assert q["date_fin_validite"] == _jour(400) and q["affiche"]["date_debut"] == "2024-03-01"
    assert "RGE depuis le 01/03/2024" in q["valeur"]["detail"]
    sans_fin = qs["QPV"]
    assert sans_fin["date_fin_validite"] is None and any("sans date de fin" in a for a in sans_fin["alertes"])
    assert [x["valeur"]["numero"] for x in r["expirees"]] == ["8611"]
    assert r["expirees"][0]["message"].startswith("Expirée le ")


# ═══ 2. « Mes preuves » : proposé, coché, enregistré avec sa source publique datée ═════════════════

def test_mes_preuves_marches_publics_coches_deviennent_des_references(client, sources):
    h, uid = _org(client)
    r = client.get("/api/preuves/publiques/marches", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["statut"] == "ok" and d["siren"] == SIREN and d["a_cocher"] == 7
    assert all("releve" not in m for m in d["marches"])
    assert "vérifié" not in json.dumps(d, ensure_ascii=False).lower()
    m1, m2 = _par_id(d["marches"], "M-2024-01"), _par_id(d["marches"], "M-2023-07")
    assert m1["source_libelle"] == "marché attribué, source publique DECP" and not m1["deja"]
    assert "attribué seul" in m1["texte"] and "réalisé" not in m1["texte"]
    m3 = _par_id(d["marches"], "M-2022-03")
    # Le client n'envoie que des clés : une clé inconnue et une ligne sans objet ne créent rien.
    r = client.post("/api/preuves/publiques", headers=h,
                    json={"cles": [m1["cle"], m2["cle"], m3["cle"], "decp:inventee"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["creees"]) == 2 and out["deja"] == 0
    assert {i["message"] for i in out["ignorees"]} == {m3["manque"], "Cette ligne n'est plus dans la dernière "
                                                                     "lecture : rechargez la liste, puis cochez de nouveau."}
    p1 = next(p for p in out["creees"] if p["valeur"]["objet"].startswith("Réfection"))
    assert p1["statut"] == "acceptee" and p1["utilisable"] and p1["origine"] == "import_public"
    assert p1["type_source"] == "public" and p1["source_libelle"] == "marché attribué, source publique DECP"
    assert p1["source"]["consulte_le"] == pv.aujourd_hui().isoformat() and p1["source"]["nom"] == "DECP"
    assert p1["source"]["url"].startswith("https://data.economie.gouv.fr/") and "M-2024-01" in p1["source"]["identifiant"]
    assert p1["valeur"] == m1["valeur"] and p1["date_source"] == pv.aujourd_hui().isoformat()
    assert sorted(p1["champs_source_publique"]) == ["acheteur", "annee", "montant_ht", "objet", "role"]
    assert "montant d'attribution 85 000 € HT" in p1["texte"] and "réalisé" not in p1["texte"]
    # Une seconde lecture les dit « déjà dans vos preuves » ; recocher ne double rien.
    d2 = client.get("/api/preuves/publiques/marches", headers=h).json()
    assert _par_id(d2["marches"], "M-2024-01")["deja"] is True and d2["a_cocher"] == 5
    again = client.post("/api/preuves/publiques", headers=h, json={"cles": [m1["cle"]]}).json()
    assert again["creees"] == [] and again["deja"] == 1
    # La rédaction reçoit un fait « marché attribué », jamais « réalisé ».
    db = _db()
    try:
        faits = [f for f in pv.faits_autorises(db, uid) if f["id"] == p1["id"]]
        assert faits and faits[0]["appuie"] == "references_qualifications"
        assert "attribué seul" in faits[0]["texte_ia"] and "réalisé" not in faits[0]["texte_ia"]
    finally:
        db.close()
    from app.services import preuves_atelier as pa
    bloc = pa.bloc("reference", p1["valeur"], None, attribue=True)
    assert "Marché attribué à l'entreprise seule" in bloc and "Montant d'attribution : 85 000 € HT" in bloc
    assert "Réalisé" not in bloc


def test_champs_de_la_source_publique_ne_changent_pas_tant_qu_elle_la_garde(client, sources):
    h, _ = _org(client)
    d = client.get("/api/preuves/publiques/marches", headers=h).json()
    m1 = _par_id(d["marches"], "M-2024-01")
    p = client.post("/api/preuves/publiques", headers=h, json={"cles": [m1["cle"]]}).json()["creees"][0]
    src = p["source"]
    pub = {"nom": src["nom"], "url": src["url"], "consulte_le": src["consulte_le"], "identifiant": src["identifiant"]}
    # Montant modifié en gardant la source publique : refusé, les champs sont nommés.
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={
        "valeur": dict(p["valeur"], montant_ht=90000), "type_source": "public", "source": pub, "version": p["version"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "valeur_source_publique"
    assert r.json()["detail"]["champs"] == ["montant_ht"] and "Déclaré par vous" in r.json()["detail"]["message"]
    # Une source publique modifiée par l'écran (date, adresse) n'est pas reprise : la fiche garde la sienne.
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={
        "valeur": dict(p["valeur"], description="Couverture en ardoise naturelle"), "type_source": "public",
        "source": dict(pub, consulte_le="2020-01-01"), "version": p["version"]})
    assert r.status_code == 200, r.text
    p2 = r.json()
    assert p2["valeur"]["description"] == "Couverture en ardoise naturelle"
    assert p2["source"]["consulte_le"] == src["consulte_le"] and p2["source_libelle"] == "marché attribué, source publique DECP"
    # « Déclaré par vous » : les champs se corrigent, et le libellé le dit.
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={
        "valeur": dict(p2["valeur"], montant_ht=90000), "type_source": "declare", "version": p2["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["source_libelle"] == "déclaré par vous" and r.json()["champs_source_publique"] == []
    assert "attribué" not in r.json()["texte"]


def test_mes_preuves_qualifications_rge(client, sources):
    h, _ = _org(client)
    d = client.get("/api/preuves/publiques/rge", headers=h).json()
    assert d["statut"] == "ok" and [x["nom"] for x in d["expirees"]] == ["QUALIBAT-RGE : Fenêtres de toit (8611)"]
    q = next(x for x in d["qualifications"] if x["valeur"]["numero"] == "5112")
    assert q["source_libelle"] == "source publique : liste RGE de l'ADEME"
    out = client.post("/api/preuves/publiques", headers=h, json={"cles": [q["cle"]]}).json()
    p = out["creees"][0]
    assert p["nature"] == "qualification" and p["date_fin_validite"] == _jour(400) and p["utilisable"]
    assert p["source_libelle"] == "source publique : liste RGE de l'ADEME" and p["valeur"]["organisme"] == "Qualibat"
    assert "date_fin_validite" in p["champs_source_publique"]
    r = client.patch(f"/api/preuves/{p['id']}", headers=h, json={"date_fin_validite": _jour(800), "version": p["version"]})
    assert r.status_code == 422 and r.json()["detail"]["champs"] == ["date_fin_validite"]
    # Une expirée n'a pas de clé à cocher : rien ne la crée.
    assert all("cle" not in x for x in d["expirees"])


def test_sans_siret_un_message_et_aucune_lecture(client, sources):
    h, _ = _org(client, siret="")
    for route in ("/api/preuves/publiques/marches", "/api/preuves/publiques/rge"):
        d = client.get(route, headers=h).json()
        assert d["statut"] == "siret_manquant" and "Mon entreprise, onglet « Identité »" in d["message"]
    assert sources.calls == []


def test_import_pendant_une_panne_ne_cree_rien_et_le_dit(client, sources):
    h, uid = _org(client)
    d = client.get("/api/preuves/publiques/marches", headers=h).json()
    cle = _par_id(d["marches"], "M-2024-01")["cle"]
    sp.vider_cache()
    sources.fail = {"decp"}
    r = client.post("/api/preuves/publiques", headers=h, json={"cles": [cle]})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "source_indisponible"
    assert "ne répondent pas" in r.json()["detail"]["message"]
    db = _db()
    try:
        assert pv.lister(db, uid, nature="reference") == []
    finally:
        db.close()


def test_une_autre_organisation_ne_voit_rien_et_rien_ne_fuit(client, sources):
    h, uid = _org(client)
    d = client.get("/api/preuves/publiques/marches", headers=h).json()
    client.post("/api/preuves/publiques", headers=h, json={"cles": [_par_id(d["marches"], "M-2024-01")["cle"]]})
    h2, uid2 = _org(client, siret="11122233300014", company="Autre entreprise (test)")
    d2 = client.get("/api/preuves/publiques/marches", headers=h2).json()
    assert d2["siren"] == "111222333" and all(not m["deja"] for m in d2["marches"])
    db = _db()
    try:
        assert pv.lister(db, uid2) == [] and len(pv.lister(db, uid)) == 1
    finally:
        db.close()


# ═══ 3. Le partenaire : SES preuves et SES sources publiques, dans SA part ═══════════════════════

def _groupement_simple(client, auth):
    from tests.test_convention_groupement import _invite, _project
    h = auth["headers"]
    pid = _project(client, h, name=f"Toiture de la salle des sports {uuid.uuid4().hex[:4]}")
    inv = _invite(client, h, pid, "Couverture Kerbrat (test)")
    return h, pid, inv["token"]


def _version(client, token, headers=None):
    return client.get(f"/api/invite/{token}/contribution", headers=headers or {}).json()["version"]


def test_partenaire_par_le_lien_reprend_ses_marches_publics_dans_sa_part(client, auth, sources):
    from tests.test_convention_groupement import _put
    h, pid, token = _groupement_simple(client, auth)
    # Sans SIRET dans la part : un message, aucune lecture.
    d = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    assert d["statut"] == "siret_manquant" and "votre part" in d["message"] and sources.calls == []
    assert _put(client, token, company_name="Couverture Kerbrat (test)", siret=SIRET,
                references=[{"intitule": "Charpente de la halle"}]).status_code == 200
    dm = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    dr = client.get(f"/api/invite/{token}/contribution/publiques/rge").json()
    assert dm["statut"] == "ok" and dr["statut"] == "ok"
    m1 = _par_id(dm["marches"], "M-2024-01")
    q = next(x for x in dr["qualifications"] if x["valeur"]["numero"] == "5112")
    url = f"/api/invite/{token}/contribution/reprendre"
    assert client.post(url, json={"publiques": [m1["cle"]]}).status_code == 428
    assert client.post(url, json={"publiques": [m1["cle"]], "version": 999}).status_code == 409
    v = _version(client, token)
    r = client.post(url, json={"publiques": [m1["cle"], q["cle"]], "version": v})
    assert r.status_code == 200, r.text
    c = r.json()["contribution"]
    assert c["version"] == v + 1
    ref = next(x for x in c["references"] if x["intitule"].startswith("Réfection"))
    assert ref == {"intitule": "Réfection de la toiture de l'école Jules-Ferry", "client": NOM_ACH1, "montant": 85000,
                   "annee": 2024, "role": "seul", "provenance": "decp", "consulte_le": pv.aujourd_hui().isoformat(),
                   "identifiant": f"marché M-2024-01, acheteur {ACH1}"}
    assert {"intitule": "Charpente de la halle"} in c["references"]          # rien n'est retiré
    assert "QUALIBAT-RGE : Isolation par l'extérieur (5112)" in c["qualifications"]
    # Recocher : déjà dans la part, rien n'est doublé ni réécrit (la version ne bouge pas).
    r2 = client.post(url, json={"publiques": [m1["cle"]], "version": c["version"]}).json()
    assert r2["deja"] == 1 and r2["ajoutees"] == {"references": [], "qualifications": []}
    assert r2["contribution"]["version"] == c["version"]
    d2 = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    assert _par_id(d2["marches"], "M-2024-01")["deja"] is True
    # Le journal du partenaire le dit en français.
    from app.services.journal_membre import LABELS_ME
    assert LABELS_ME["guest.contribution_reprise"].startswith("Vous avez ajouté")
    # Une part soumise repasse en brouillon quand elle change (comme toute modification).
    assert client.post(f"/api/invite/{token}/contribution/submit").status_code == 200
    m2 = _par_id(d2["marches"], "M-2023-07")
    r3 = client.post(url, json={"publiques": [m2["cle"]], "version": _version(client, token)})
    assert r3.status_code == 200 and r3.json()["contribution"]["status"] == "draft"
    ref2 = next(x for x in r3.json()["contribution"]["references"] if x["intitule"].startswith("RENOVATION"))
    assert ref2["role"] == "groupement_solidaire" and "client" not in ref2


def test_partenaire_par_son_compte_reprend_ses_preuves_jamais_celles_du_chef(client, auth, sources):
    from tests.test_convention_groupement import _register
    h, pid, token = _groupement_simple(client, auth)
    # Une preuve du chef de file : jamais proposée au partenaire.
    chef = client.post("/api/preuves", headers=h, json={"nature": "reference", "valeur": {"objet": "Référence du chef"}})
    assert chef.status_code == 201, chef.text
    hp, _ = _register(client, company="Couverture Kerbrat (compte)")
    ref = client.post("/api/preuves", headers=hp, json={"nature": "reference",
                                                         "valeur": {"objet": "Réfection de la couverture du lavoir",
                                                                    "acheteur": "Commune de Kerbrat", "annee": 2023,
                                                                    "montant_ht": 42000}}).json()
    qual = client.post("/api/preuves", headers=hp, json={"nature": "qualification", "valeur": {"nom": "Qualibat 3194"},
                                                          "date_fin_validite": _jour(200)}).json()
    client.post("/api/preuves", headers=hp, json={"nature": "salarie", "valeur": {"nom": "Yann Fictif", "fonction": "Chef de chantier"}})
    url = f"/api/invite/{token}/contribution/preuves"
    assert client.get(url, headers=hp).status_code == 403                    # lien pas encore rattaché
    assert client.post(f"/api/invite/{token}/claim", headers=hp).status_code == 200
    assert client.get(url, headers=h).status_code == 403                     # le chef de file n'y a pas accès
    ps = client.get(url, headers=hp).json()["preuves"]
    assert sorted(p["titre"] for p in ps) == ["Qualibat 3194", "Réfection de la couverture du lavoir"]
    assert "Référence du chef" not in json.dumps(ps, ensure_ascii=False)
    r = client.post(f"/api/invite/{token}/contribution/reprendre-preuves", headers=hp, json={
        "preuves": [ref["id"], qual["id"], chef.json()["id"]], "version": _version(client, token, hp)})
    assert r.status_code == 200, r.text
    c = r.json()["contribution"]
    assert {"intitule": "Réfection de la couverture du lavoir", "client": "Commune de Kerbrat", "montant": 42000,
            "annee": 2023, "provenance": "mes_preuves"} in c["references"]
    assert c["qualifications"] == ["Qualibat 3194"]
    assert "Référence du chef" not in json.dumps(c, ensure_ascii=False)
    assert len(r.json()["ignorees"]) == 1                                     # la preuve du chef : introuvable
    # Ce que voit le chef de file : la part (sa donnée envoyée), jamais la liste de ses preuves.
    vue = client.get(f"/api/projects/{pid}/contributions", headers=h).json()
    assert "Yann Fictif" not in json.dumps(vue, ensure_ascii=False)
    # Par le lien seul, ses preuves ne se reprennent pas.
    r = client.post(f"/api/invite/{token}/contribution/reprendre", json={"publiques": [], "version": c["version"]})
    assert r.status_code == 200 and r.json()["ajoutees"] == {"references": [], "qualifications": []}


# ═══ 4. Réseau : l'historique réel de co-traitance (titulaires 2 et 3) ═════════════════════════════

def test_reseau_fetch_decp_lit_les_titulaires_2_3_et_compte_les_groupements(monkeypatch):
    import app.services.partner_network as pn
    from app.services import partner_matching as pm
    vus = []

    def fake(url, params, timeout=5.0):
        vus.append(params)
        return {"results": [
            {"objet": "Lot 1", "datenotification": "2026-05-01", "acheteur_id": ACH1, "titulaire_id_1": AUTRE,
             "titulaire_id_2": SIRET, "typegroupementoperateurs": "Solidaire"},
            {"objet": "Lot 1", "datenotification": "2026-05-01", "acheteur_id": ACH1, "titulaire_id_1": AUTRE,
             "titulaire_id_2": SIRET, "typegroupementoperateurs": "Solidaire"},
            {"objet": "Lot 2", "datenotification": "2025-01-01", "acheteur_id": ACH1, "titulaire_id_1": SIRET,
             "titulaire_id_2": AUTRE, "typegroupementoperateurs": "Conjoint"},
            {"objet": "Lot 3", "datenotification": "2024-01-01", "acheteur_id": ACH2, "titulaire_id_1": SIRET,
             "titulaire_id_2": "CDL", "typegroupementoperateurs": "Pas de groupement"}]}
    monkeypatch.setattr(pn, "_http_get", fake)
    r = pn.fetch_decp(SIREN)
    for i in (1, 2, 3):
        assert f'startswith(titulaire_id_{i}, "{SIREN}")' in vus[0]["where"]
    assert r["statut"] == "ok" and r["count"] == 3 and r["groupements"] == 2
    vd = dict(r, checked_at="2026-10-05T09:00:00")
    assert pm.decp_label(vd) == "Au moins 3 marchés publics publiés dans DECP (au 05/10), dont 2 en groupement"
    assert pm.decp_label({"count": 3, "checked_at": "2026-10-08"}) == \
        "Au moins 3 marchés publics publiés dans DECP (au 08/10)"            # lecture d'avant : rien d'ajouté
    p = {"verified_decp": vd, "metiers": [], "declared_at": None}
    caps = {c["key"]: c for c in pm.capacites(p)}
    assert caps["marches_groupement"]["valeur"] == "au moins 2" and caps["marches_groupement"]["date"] == "2026-10-05"
    crit = {c["key"]: c for c in pm.score_lot({}, p, date(2026, 10, 19))[1]}
    assert "dont 2 en groupement" in crit["experience"]["detail"]
    total_avec = pm.score_lot({}, p, date(2026, 10, 19))[0]
    total_sans = pm.score_lot({}, dict(p, verified_decp=dict(vd, groupements=0)), date(2026, 10, 19))[0]
    assert total_avec == total_sans + 3
    tout = json.dumps([pm.badges(p), pm.capacites(p)], ensure_ascii=False).lower()
    assert "vérifié" not in tout.replace("non vérifié", "")


def test_wins_by_siren_lit_les_titulaires_1_2_3(monkeypatch):
    from app.services import decp
    vus = []

    class R:
        def json(self):
            return {"total_count": 2, "results": [{"codecpv": "45261210", "datenotification": "2026-01-01"}]}

    monkeypatch.setattr(decp, "get_with_retry", lambda url, params=None, timeout=8: vus.append(params) or R())
    w = decp.wins_by_siren(SIRET)
    assert w == {"count": 2, "last_date": "2026-01-01", "domains": ["45"]}
    for i in (1, 2, 3):
        assert f'startswith(titulaire_id_{i}, "{SIREN}")' in vus[0]["where"]


# ═══ 5. Démo : exemple fictif, aucun réseau, aucune écriture ═════════════════════════════════════

def test_demo_exemple_fictif_sans_reseau_ni_ecriture(client, sources):
    from app.core.demo_guard import blocked_action
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        lorient = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        token = db.query(ProjectInvite).filter(ProjectInvite.project_id == lorient.id).first().token
    finally:
        db.close()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    hd = {"Authorization": f"Bearer {r.json()['access_token']}"}
    dm = client.get("/api/preuves/publiques/marches", headers=hd).json()
    dr = client.get("/api/preuves/publiques/rge", headers=hd).json()
    assert dm["exemple_fictif"] is True and dm["statut"] == "exemple" and "fictif" in dm["message"]
    assert len(dm["marches"]) == 3 and all("fictif" in m["affiche"]["objet"].lower() for m in dm["marches"])
    assert all("fictive" in m["affiche"]["acheteur"].lower() for m in dm["marches"])
    assert any(m["alertes"] for m in dm["marches"])                     # une valeur inhabituelle, montrée
    assert any(m["affiche"]["role"] == "groupement_solidaire" for m in dm["marches"])
    assert dr["exemple_fictif"] is True and len(dr["qualifications"]) == 1 and len(dr["expirees"]) == 1
    # Le lien partenaire de la vitrine : le même exemple, rien d'écrit.
    dl = client.get(f"/api/invite/{token}/contribution/publiques/marches").json()
    assert dl["exemple_fictif"] is True
    cle = dm["marches"][0]["cle"]
    r = client.post("/api/preuves/publiques", headers=hd, json={"cles": [cle]})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    assert blocked_action("POST", "/api/preuves/publiques")
    r = client.post(f"/api/invite/{token}/contribution/reprendre", json={"publiques": [cle], "version": 0})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]
    assert sources.calls == []
    textes = json.dumps([dm, dr], ensure_ascii=False)
    assert not EMOJI.search(textes)
    for mot in ("consortium", "mandataire", "vérifié", "réalisé"):
        assert mot not in textes.lower(), mot


# ═══ 6. L'écran : fonctions pures sous Node, textes échappés, hygiène ═══════════════════════════

JS = _read("sources-publiques.js")


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    prog = "const window = {};\n" + JS + "\nconst S = window.AdjugoSourcesPubliques._pur;\n" + script
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_fonctions_pures_de_l_ecran_sous_node():
    riches = [{"intitule": "Réfection de la toiture", "client": NOM_ACH1, "montant": 85000, "provenance": "decp",
               "consulte_le": "2026-10-19"}, {"intitule": "Charpente"}]
    r = _node("const riches = " + json.dumps(riches, ensure_ascii=False) + ";\n"
              "console.log(JSON.stringify({"
              " f: S.spFusionRefs('Réfection de la toiture\\n  Nouvelle référence \\n\\nCharpente', riches),"
              " lib: S.spLibRefs(S.spFusionRefs('Réfection de la toiture', riches)), lib0: S.spLibRefs([{intitule: 'x'}]),"
              " e: [S.spEuros(142380.5), S.spEuros(1), S.spEuros(85000), S.spEuros('abc')],"
              " m: S.spMeta({affiche: {acheteur_siret: '20000000100018', date: '2023-09-03', montant: 0, role_libelle: 'Seule'}}),"
              " esc: S.spEsc('<img src=x onerror=alert(1)>'),"
              " res: [S.spResume({creees: [1, 2], deja: 1}, 'preuves'), S.spResume({ajoutees: {references: [1], qualifications: [1, 2]}}, 'part')]}));")
    assert r["f"] == [dict(riches[0]), {"intitule": "Nouvelle référence"}, {"intitule": "Charpente"}]
    assert r["lib"] == "Dont 1 marché attribué, source publique DECP (lu le 19/10/2026)." and r["lib0"] == ""
    assert r["e"] == ["142 380,50 €", "1 €", "85 000 €", "abc"]
    assert r["m"] == "acheteur : SIRET 20000000100018 (nom non retrouvé) · notifié le 03/09/2023 · 0 € HT · Seule"
    assert r["esc"] == "&lt;img src=x onerror=alert(1)&gt;"
    assert r["res"] == ["2 fiches ajoutées à « Mes preuves » ; 1 était déjà dans vos preuves.",
                        "1 référence et 2 qualifications ajoutées à votre part."]


def test_ecran_hygiene_et_branchement():
    chaines = " ".join(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', JS))
    assert not EMOJI.search(JS)
    low = chaines.lower()
    for mot in ("vérifié", "signer", "signature", "consortium", "mandataire", "token", "workflow"):
        assert mot not in low, mot
    assert "marché attribué, source publique DECP" in JS
    for b in re.findall(r"<button\b[^>]*>", JS):
        assert 'type="button"' in b, b
    # Le script est servi avec son empreinte (SRI) dans les deux pages, et branché aux trois accès.
    from app.core import sri
    rep = sri.stale_report()
    assert not rep["pages"] and rep["manifeste_a_jour"]
    for page in ("app.html", "invite.html"):
        assert re.search(r'<script src="/static/sources-publiques\.js" integrity="sha384-[^"]+"', _read(page)), page
    html = _read("app.html")
    assert html.count("<sources-publiques ") == 3
    assert 'mode="part"' in html and ":kinds=\"['rge']\"" in html
    inv = _read("invite.html")
    assert "/reprendre\"" in inv and "spFusionRefs(refs.value, curRefs)" in inv
    app_js = _read("app.js")
    assert "_spFusionRefs(k.refs, this.sharedAo.refsRiches)" in app_js
    css = _read("styles.css")
    assert ".sp-panel" in css and "@media (max-width:600px)" in css[css.index(".sp-panel"):]
