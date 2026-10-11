"""
Coffre-fort croisé — « pièces à fournir » : formulation et doublons.

Invariants vérifiés ici :
- formulation neutre et correcte : « Kbis à fournir : X » (plus jamais « Kbis manquante », faute
  d'accord pour Kbis, RIB…) ; les alertes d'expiration gardent leur texte ; le code de statut
  `manquant` ne change pas ;
- à côté de `alerts` (textes, inchangé) : `alert_items` typés et `a_fournir` (total, part du membre
  qui regarde, UNE ligne de synthèse) — l'écran du partenaire n'a pas à découper les textes ;
- côté partenaire, sous le tableau : la synthèse + les seules expirations (plus les 15 lignes
  « … à fournir : … » qui répétaient le tableau) ;
- cockpit du chef de file : une ligne « à fournir » par membre, pas une par pièce ;
- « Avant de déposer » : toutes les alertes (le « et N autres » est exact), expirations d'abord ;
- relances par email : « Kbis à fournir », « Kbis a expiré ».
"""
import io
import os
import re
from datetime import date, timedelta

from tests.test_convention_groupement import _db, _invite, _project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
BASE = ["kbis", "fiscale", "sociale", "assurance", "rib"]


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def _upload(client, token, filename, **form):
    r = client.post(f"/api/invite/{token}/contribution/piece",
                    files={"file": (filename, io.BytesIO(PDF), "application/pdf")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


def _groupe(client, h, deadline_days=30, recipients=("", "", "")):
    """3 partenaires : Alpha (URSSAF qui expire avant la date limite), Beta (Kbis expiré),
    Gamma (rien) → 2 expirations et 13 pièces à fournir."""
    pid = _project(client, h, deadline_days=deadline_days)
    toks = {}
    for name, rcpt in zip(("Alpha SARL", "Beta SAS", "Gamma Électricité"), recipients):
        toks[name] = _invite(client, h, pid, name, recipient=rcpt)["token"]
    _upload(client, toks["Alpha SARL"], "attestation_urssaf.pdf", piece_type="sociale",
            expiration_date=(date.today() + timedelta(days=max(1, deadline_days - 2))).isoformat())
    _upload(client, toks["Beta SAS"], "kbis.pdf", piece_type="kbis",
            expiration_date=(date.today() - timedelta(days=2)).isoformat())
    return pid, toks


def test_formulation_a_fournir_et_alertes_typees(client, auth):
    h = auth["headers"]
    pid, toks = _groupe(client, h)
    g = client.get(f"/api/projects/{pid}/coffre-croise", headers=h).json()
    assert [e["key"] for e in g["expected"]] == BASE

    # Plus aucune faute d'accord : « Kbis manquante », « RIB manquante »…
    assert not any("manquante" in a for a in g["alerts"]), g["alerts"]
    assert "Kbis à fournir : Gamma Électricité" in g["alerts"]
    assert "RIB à fournir : Beta SAS" in g["alerts"]
    # Expirations : texte inchangé.
    assert "Attest. sociale (URSSAF) de Alpha SARL expire avant la date limite" in g["alerts"]
    assert "Kbis de Beta SAS a expiré" in g["alerts"]
    # Code de statut côté serveur inchangé.
    gamma = next(m for m in g["members"] if m["company"] == "Gamma Électricité")
    assert gamma["pieces"]["kbis"]["status"] == "manquant"

    # Liste typée, alignée sur les textes (clé `alerts` conservée).
    items = g["alert_items"]
    assert [i["text"] for i in items] == g["alerts"]
    assert {i["kind"] for i in items} == {"a_fournir", "expire", "expire_avant_limite"}
    af = [i for i in items if i["kind"] == "a_fournir"]
    assert len(af) == 13 and all(i["text"] == f"{i['label']} à fournir : {i['company']}" for i in af)
    assert all(i["invite_id"] and i["is_me"] is False for i in items)       # vue chef de file
    assert g["a_fournir"] == {"total": 13, "moi": 0, "resume": "Il reste 13 pièces à fournir."}


def test_partenaire_synthese_sans_repeter_le_tableau(client, auth):
    h = auth["headers"]
    pid, toks = _groupe(client, h)
    gb = client.get(f"/api/invite/{toks['Beta SAS']}/coffre-croise").json()
    # Beta : Kbis expiré + 4 pièces à fournir de son côté.
    assert gb["a_fournir"]["total"] == 13 and gb["a_fournir"]["moi"] == 4
    assert gb["a_fournir"]["resume"] == "Il reste 13 pièces à fournir, dont 4 de votre côté."
    mine = [i for i in gb["alert_items"] if i["is_me"]]
    assert mine and all(i["company"] == "Beta SAS" for i in mine)
    assert all("invite_id" not in i for i in gb["alert_items"])              # jamais côté membre
    # Ce que l'écran affiche sous le tableau : la synthèse + les seules expirations (2 lignes),
    # au lieu des 15 alertes dont 13 répétaient le tableau.
    sous_tableau = [gb["a_fournir"]["resume"]] + [
        i["text"] for i in gb["alert_items"] if i["kind"] != "a_fournir"]
    assert len(gb["alerts"]) == 15 and len(sous_tableau) == 3
    assert not any("à fournir :" in t for t in sous_tableau)


def test_resume_accords():
    from app.routers.invites import _a_fournir_resume as r
    assert r(0, 0) == ""
    assert r(1, 0) == "Il reste 1 pièce à fournir."
    assert r(1, 1) == "Il reste 1 pièce à fournir, de votre côté."
    assert r(5, 5) == "Il reste 5 pièces à fournir, toutes de votre côté."
    assert r(18, 6) == "Il reste 18 pièces à fournir, dont 6 de votre côté."


def test_cockpit_une_ligne_a_fournir_par_membre(client, auth):
    h = auth["headers"]
    pid, _toks = _groupe(client, h)
    miss = client.get(f"/api/projects/{pid}/consortium", headers=h).json()["readiness"]["missing"]
    assert not any(re.search(r" à fournir : ", m) for m in miss), miss      # plus une ligne par pièce
    assert not any("manquante" in m for m in miss)
    assert "Kbis de Beta SAS a expiré" in miss
    assert "Attest. sociale (URSSAF) de Alpha SARL expire avant la date limite" in miss
    assert not any("pièce(s)" in m for m in miss)                          # accordé au nombre
    gamma = [m for m in miss if m.startswith("Gamma Électricité : pièces à fournir")]
    assert gamma == ["Gamma Électricité : pièces à fournir — Kbis, Attest. fiscale, "
                     "Attest. sociale (URSSAF) et 2 autres"]
    assert "Alpha SARL : pièces à fournir — Kbis, Attest. fiscale, Assurance (RC/décennale) et 1 autre" in miss
    for who in ("Alpha SARL", "Beta SAS"):
        assert len([m for m in miss if m.startswith(f"{who} : pièces à fournir")]) == 1


def test_cockpit_part_soumise_sans_pieces_liste_complete(client, auth):
    """Part soumise et complète (lot, prix, mémoire, références) : UNE ligne « à fournir » par
    membre, et elle dit combien il en reste (avant : 3 pièces annoncées, pas un mot sur
    l'assurance ni le RIB). Accord au nombre : une seule pièce → « pièce à fournir »."""
    from tests.test_convention_groupement import _put, _submit
    h = auth["headers"]
    pid = _project(client, h)
    toks = {n: _invite(client, h, pid, n)["token"] for n in ("Delta BTP", "Epsilon Bois")}
    for fname, ptype in (("kbis.pdf", "kbis"), ("fiscale.pdf", "fiscale"), ("urssaf.pdf", "sociale"),
                         ("assurance.pdf", "assurance")):
        _upload(client, toks["Epsilon Bois"], fname, piece_type=ptype)     # tout sauf le RIB
    for i, (name, tok) in enumerate(toks.items()):
        r = _put(client, tok, company_name=name, lot=f"Lot {i + 5}", prix_lot_ht=30000,
                 memoire_paragraph="Équipe de 6 compagnons, 20 ans d'expérience.",
                 references=[{"name": "École de Lorient", "year": 2024}])
        assert r.status_code == 200, r.text
        _submit(client, tok)
    miss = client.get(f"/api/projects/{pid}/consortium", headers=h).json()["readiness"]["missing"]
    assert [m for m in miss if m.startswith("Delta BTP")] == [
        "Delta BTP : pièces à fournir — Kbis, Attest. fiscale, Attest. sociale (URSSAF) et 2 autres"], miss
    assert [m for m in miss if m.startswith("Epsilon Bois")] == ["Epsilon Bois : pièce à fournir — RIB"], miss


def test_ligne_a_fournir_accord_et_reste():
    from app.routers.invites import _ligne_a_fournir
    assert _ligne_a_fournir("X", ["RIB"]) == "X : pièce à fournir — RIB"
    assert _ligne_a_fournir("X", ["Kbis", "RIB"]) == "X : pièces à fournir — Kbis, RIB"
    assert _ligne_a_fournir("X", ["A", "B", "C", "D"]) == "X : pièces à fournir — A, B, C et 1 autre"
    assert _ligne_a_fournir("X", list("ABCDEF")) == "X : pièces à fournir — A, B, C et 3 autres"


def test_avant_de_deposer_compte_exact_expirations_d_abord(client, auth):
    h = auth["headers"]
    pid, _toks = _groupe(client, h)
    p = client.get(f"/api/projects/{pid}/groupement/depot", headers=h).json()["pret"]
    att = [m for m in p["manques"] if " à fournir : " in m or " a expiré" in m
           or "expire avant la date limite" in m]
    assert len(att) == 15                       # avant : plafonné à 8 → « et 5 autres » au lieu de 12
    assert not any("manquante" in m for m in p["manques"])
    first_af = min(i for i, m in enumerate(p["manques"]) if " à fournir : " in m)
    last_exp = max(i for i, m in enumerate(p["manques"]) if " a expiré" in m or "expire avant" in m)
    assert last_exp < first_af


def test_relances_formulation(client, auth, monkeypatch):
    import app.routers.invites as inv_mod
    import app.services.alerts as al
    monkeypatch.setattr(inv_mod, "_send_mails_async", lambda m: None)     # aucun email réel
    h = auth["headers"]
    pid, _toks = _groupe(client, h, deadline_days=5,
                         recipients=("a@alpha.fr", "b@beta.fr", "g@gamma.fr"))
    db = _db()
    try:
        due = [a for a in al._piece_alerts_due(db, date.today()) if a["project"].id == pid]
    finally:
        db.close()
    probs = {a["who"]: a["problems"] for a in due}
    assert "Kbis a expiré" in probs["Beta SAS"] and "RIB à fournir" in probs["Beta SAS"]
    assert "Kbis à fournir" in probs["Gamma Électricité"]
    flat = " ".join(" ".join(v) for v in probs.values())
    assert "manquante" not in flat and "expirée" not in flat


def test_ecrans_libelles_et_sans_doublon():
    app_js, app_html, invite = _read("app.js"), _read("app.html"), _read("invite.html")
    # Libellés des cellules : « à fournir » / « À fournir » (code `manquant` inchangé).
    assert 'manquant: "à fournir"' in app_js and 'manquant: "manquante"' not in app_js
    assert 'manquant: "À fournir"' in invite and 'manquant: "Manquante"' not in invite
    # Partagé avec moi : plus de liste complète des alertes sous le tableau.
    i = app_html.index("Coffre-fort croisé — qui a fourni quoi")
    bloc = app_html[i:app_html.index("Enregistrer le brouillon", i)]
    assert "sharedAo.coffre.alerts" not in bloc
    assert "cxResume(sharedAo.coffre)" in bloc and "cxExpirations(sharedAo.coffre)" in bloc
    assert 'a.kind !== "a_fournir"' in app_js
    # Page du partenaire par lien : idem.
    j = invite.index("async function reloadCoffre()")
    fn = invite[j:invite.index("function renderChecklist", j)]
    assert "g.alerts" not in fn
    assert "g.a_fournir" in fn and 'a.kind !== "a_fournir"' in fn
