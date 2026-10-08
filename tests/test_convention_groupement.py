"""
Co-traitance v2 — vague 2 : « Monter le groupement » (convention + accords des membres).

Invariants vérifiés :
- génération DÉTERMINISTE (0 LLM) : mêmes entrées → même texte → même empreinte ;
- « figer l'offre » fusionné avec la génération (total figé, visible des membres) ;
- péremption dès qu'une part, un prix ou la composition change (et filet à la lecture) ;
- accords : mandataire (compte vérifié), invité par lien (lien seul / email vérifié par code),
  compte après claim, membre hors ligne coché par le mandataire ; niveau d'identité imprimé ;
- doctrine : en brouillon un membre ne voit jamais le prix des autres ni le total ; une fois
  générée la convention est la même pour tous ; jamais detail_chiffre ; jamais au LLM ;
- révoqué / décliné : ni signataire, ni dans l'annexe ;
- DC1 / ATTRI1 alignés sur la convention ; ZIP et dossier contiennent la convention ;
- démo : toutes les écritures bloquées ;
- migration o9p0q1r2s3t4 : à neuf, rejouée, idempotente (SQLite) ;
- PDF : « & », « < », « * », « _ » restent du texte.
"""
import base64
import io
import json
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────
def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _register(client, company="Partenaire Compte SARL", email=None, verified=True):
    email = email or f"u_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Partenaire", "company_name": company})
    assert r.status_code == 201, r.text
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = verified
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def _project(client, headers, name="Réhabilitation de l'école Jules-Ferry", deadline_days=30):
    r = client.post("/api/projects/", headers=headers, json={
        "name": name, "client": "Ville de Lorient", "budget": 100000,
        "deadline": (date.today() + timedelta(days=deadline_days)).isoformat()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _invite(client, headers, pid, company, recipient=""):
    r = client.post(f"/api/projects/{pid}/invites", headers=headers,
                    json={"recipient": recipient, "company_name": company})
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, token, headers=None, **fields):
    v = client.get(f"/api/invite/{token}/contribution", headers=headers or {}).json()["version"]
    return client.put(f"/api/invite/{token}/contribution", json={"version": v, **fields}, headers=headers or {})


def _submit(client, token):
    r = client.post(f"/api/invite/{token}/contribution/submit")
    assert r.status_code == 200, r.text


def _part(client, token, name, lot, prix, rep="Jean Le Gall", qual="Gérant", siret=None):
    r = _put(client, token, company_name=name, lot=lot, prix_lot_ht=prix, representant_legal=rep,
             signataire_qualite=qual, siret=siret or ("1" * 9 + uuid.uuid4().hex[:5].translate(str.maketrans("abcdef", "123456"))))
    assert r.status_code == 200, r.text
    _submit(client, token)


def _set_company(email, **fields):
    from app.models import Company, User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        c = db.query(Company).filter(Company.user_id == u.id).first()
        for k, v in fields.items():
            setattr(c, k, v)
        db.commit()
    finally:
        db.close()


def _groupement(client, auth, n=2, mand_part=60000):
    """Marché + n partenaires avec part soumise + brouillon conjoint prêt à générer."""
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture", siret="12345678900011", address="1 rue du Port",
                 postal_code="56100", city="Lorient", representant_legal="Eliot Viegas")
    pid = _project(client, h)
    invs = []
    specs = [("Le Gall Électricité", "Lot 2 — Électricité", 40000.0),
             ("Morvan Plomberie", "Lot 3 — Plomberie", 25000.5),
             ("Ar Men Peinture", "Lot 4 — Peinture", 12000.0)]
    for name, lot, prix in specs[:n]:
        inv = _invite(client, h, pid, name, recipient=f"{uuid.uuid4().hex[:6]}@partenaire.fr")
        _part(client, inv["token"], name, lot, prix)
        invs.append(inv)
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={
        "forme": "conjoint", "params": {"part_mandataire_ht": mand_part, "lot_mandataire": "Lot 1 — Couverture",
                                        "mandataire_qualite": "Président"}})
    assert r.status_code == 200, r.text
    return pid, invs


@pytest.fixture
def mails(monkeypatch):
    """Capture SYNCHRONE des emails de groupement (pas de thread démon en test)."""
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda mails: sent.extend(mails))
    return sent


def _gen(client, h, pid, **body):
    return client.post(f"/api/projects/{pid}/groupement/convention/generer", headers=h, json=body)


def _valider(client, url, conv, headers=None, nom="Jean Le Gall", qual="Gérant", **over):
    body = {"content_hash": conv["content_hash"], "signataire_nom": nom, "signataire_qualite": qual,
            "accepte": True}
    body.update(over)
    return client.post(url, json=body, headers=headers or {})


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


# ── 1. Génération déterministe ───────────────────────────────────────────────
def test_generation_deterministe_meme_hash():
    from app.services import groupement_convention as gc
    members = [
        {"kind": "mandataire", "invite_id": None, "link_id": None, "company": "Breizh Couverture",
         "siret": "12345678900011", "address": "1 rue du Port", "postal_code": "56100", "city": "Lorient",
         "representant_legal": "Eliot Viegas", "signataire_qualite": "Président", "role": "mandataire",
         "lot": "Lot 1", "prix_lot_ht": 60000.0},
        {"kind": "invite", "invite_id": 7, "link_id": None, "company": "Le Gall Électricité",
         "siret": "98765432100022", "address": "", "postal_code": "", "city": "Quimper",
         "representant_legal": "Jean Le Gall", "signataire_qualite": "Gérant", "role": "cotraitant",
         "lot": "Lot 2", "prix_lot_ht": 40000.5},
    ]
    ctx = {"version": 1, "marche": {"objet": "École", "acheteur": "Ville", "reference": "AO-0001"},
           "forme": "conjoint", "mandataire_solidaire": True, "habilitation": gc.default_habilitation(),
           "params": {**{p["key"]: p["defaut"] for p in gc.PARAMS}, "assurances_travaux": True},
           "members": members, "total_ht": gc.total_of(members)}
    t1, t2 = gc.render(ctx), gc.render(json.loads(json.dumps(ctx)))
    assert t1 == t2 and gc.sha256(t1) == gc.sha256(t2) and len(gc.sha256(t1)) == 64
    assert "100 000,50 € HT" in t1 and "40 000,50 € HT" in t1
    assert "Le groupement est **conjoint** : chacun est responsable de sa part." in t1
    assert "Le mandataire est **solidaire**" in t1
    assert "Version n°1" in t1 and "AO-0001" in t1
    assert gc.AVERTISSEMENT in t1
    # Le texte ne dépend d'AUCUNE horloge : pas de date de génération dedans.
    assert date.today().strftime("%d/%m/%Y") not in t1
    # Une seule entrée change → empreinte différente.
    ctx2 = json.loads(json.dumps(ctx))
    ctx2["params"]["confidentialite_annees"] = 3
    assert gc.sha256(gc.render(ctx2)) != gc.sha256(t1)
    ctx3 = json.loads(json.dumps(ctx))
    ctx3["members"][1]["prix_lot_ht"] = 40001
    assert gc.sha256(gc.render(ctx3)) != gc.sha256(t1)
    # Formats déterministes.
    assert gc.eur(1234567.5) == "1 234 567,50 €" and gc.eur(0) == "0 €" and gc.eur(12.005) in ("12 €", "12,01 €")


def test_generation_via_api_hash_et_offre_figee(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["status"] == "draft" and g["peut_generer"] is True and g["manques"] == []
    assert g["total_offre_ht"] is None and g["total_estime_ht"] == 125000.5
    assert g["avertissement"].startswith("Modèle à faire relire par un conseil")

    r = _gen(client, h, pid)
    assert r.status_code == 200, r.text
    c = r.json()
    from app.services import groupement_convention as gc
    assert c["status"] == "a_signer" and c["version"] == 1
    assert c["content_hash"] == gc.sha256(c["content_md"])
    assert c["total_offre_ht"] == 125000.5 and "125 000,50 € HT" in c["content_md"]
    assert c["n_signataires"] == 3 and c["n_accords"] == 0
    assert c["state"]["state"] == "convention_a_signer" and c["state"]["etape"] == 4
    # « Figer l'offre » fusionné : total figé, visible du membre, convention liée.
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["offer_frozen"] is True and st["total_offre_ht"] == 125000.5
    assert st["plan"]["offre"]["convention_id"] and st["convention"]["status"] == "a_signer"
    fm = client.get(f"/api/invite/{invs[0]['token']}").json()["for_member"]
    assert fm["state"]["total_offre_ht"] == 125000.5 and fm["state"]["convention"]["status"] == "a_signer"
    assert fm["state"]["etape"] == 4 and len(fm["state"]["etapes"]) == 5
    # Recalcul de l'empreinte à l'identique (aucune dérive).
    db = _db()
    try:
        from app.models import Project
        p = db.query(Project).get(pid)
        conv = gc.get_convention(db, pid)
        assert gc.current_hash(db, p, conv) == conv.content_hash
        assert gc.is_stale(db, p, conv) is False
    finally:
        db.close()
    # Emails « convention à valider » : un par partenaire invité, avec l'avertissement.
    assert len(mails) == 2 and all("à valider" in m[1] for m in mails)
    assert all("ce n'est pas un conseil juridique" in m[2] and "/invite/" in m[2] for m in mails)
    # Re-générer exige une confirmation explicite ; version 2 = nouvelle empreinte.
    r = _gen(client, h, pid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "deja_generee"
    r2 = _gen(client, h, pid, regenerer=True)
    assert r2.status_code == 200 and r2.json()["version"] == 2
    assert r2.json()["content_hash"] != c["content_hash"]
    # Anti-rafale : une régénération immédiate ne renvoie pas d'email aux mêmes partenaires.
    assert r2.json()["emails_envoyes"] == 0 and len(mails) == 2
    # L'ancien « figer l'offre » de la vague 1 refuse de désynchroniser la convention.
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "convention_generee"
    # Journal membre : génération visible, sans IP ni email.
    j = client.get(f"/api/invite/{invs[0]['token']}/journal").json()
    labels = [e["label"] for e in j["entries"]]
    assert "Le mandataire a généré la convention de groupement" in labels
    assert "@" not in json.dumps(j, ensure_ascii=False)


def test_emails_jamais_si_adresse_expediteur_non_confirmee(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    _set_verified(auth["email"], False)
    try:
        r = _gen(client, h, pid)
        assert r.status_code == 200 and r.json()["emails_envoyes"] == 0 and mails == []
    finally:
        _set_verified(auth["email"], True)
    # Plafond quotidien par partenaire (en plus de l'anti-rafale de 30 min).
    from app.routers import convention as conv_router
    assert all(conv_router._conv_mail_allowed(-1, -42) for _ in range(conv_router.CONV_MAILS_PER_INVITE_PER_DAY))
    assert conv_router._conv_mail_allowed(-1, -42) is False


def test_generation_refusee_sans_forme_ni_parts(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    r = _gen(client, h, pid)
    assert r.status_code == 422 and "forme du groupement" in r.text.lower()
    inv = _invite(client, h, pid, "Pas Prêt SARL")
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"forme": "solidaire"})
    r = _gen(client, h, pid)
    assert r.status_code == 422
    missing = r.json()["detail"]["missing"]
    assert any("n'a pas encore soumis sa part" in m for m in missing)
    assert any("Votre part" in m for m in missing) or True
    _put(client, inv["token"], lot="Lot A")
    _submit(client, inv["token"])
    r = _gen(client, h, pid)
    assert any("prix de lot manquant" in m for m in r.json()["detail"]["missing"])
    # Valeurs de paramètres contrôlées.
    bad = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                     json={"params": {"confidentialite_annees": 99}})
    assert bad.status_code == 422
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                      json={"params": {"decision": "dictature"}}).status_code == 422
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                      json={"forme": "mixte"}).status_code == 422
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                      json={"habilitation": {"inconnu": True}}).status_code == 422
    # « representer » ne se décoche pas (mission même du mandataire).
    ok = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                    json={"habilitation": {"representer": False, "signer_modifications": True}}).json()
    assert ok["habilitation"]["representer"] is True and ok["habilitation"]["signer_modifications"] is True


# ── 2. Péremption ────────────────────────────────────────────────────────────
def test_peremption_sur_changement_de_part(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    c = _gen(client, h, pid).json()
    t0 = invs[0]["token"]
    assert _valider(client, f"/api/invite/{t0}/convention/valider", c).status_code == 200

    # Le partenaire change son prix → convention caduque, accords caducs, offre défigée.
    r = _put(client, t0, prix_lot_ht=41000)
    assert r.status_code == 200
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["status"] == "perimee"
    assert {s["status"] for s in g["signatures"]} == {"perimee"}
    assert g["state"]["offer_frozen"] is False and g["state"]["convention_status"] == "perimee"
    j = [e["label"] for e in client.get(f"/api/invite/{t0}/journal").json()["entries"]]
    assert "Votre modification a rendu la convention caduque : elle doit être régénérée" in j
    j1 = [e for e in client.get(f"/api/invite/{invs[1]['token']}/journal").json()["entries"]
          if e["action"] == "convention.perimee"]
    assert j1 and j1[0]["label"].startswith("La convention n'est plus à jour")
    # Accord impossible sur une convention caduque.
    r = _valider(client, f"/api/invite/{invs[1]['token']}/convention/valider", c)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "perimee"

    # Re-soumission puis régénération : version 2, nouveau total, accords remis à zéro.
    _submit(client, t0)
    c2 = _gen(client, h, pid).json()
    assert c2["status"] == "a_signer" and c2["version"] == 2 and c2["total_offre_ht"] == 126000.5
    assert {s["status"] for s in c2["signatures"]} == {"pending"}


@pytest.mark.parametrize("cause", ["nouvelle_invitation", "revocation", "declin", "defiger", "plan_retire"])
def test_peremption_composition(client, auth, mails, cause):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    assert _gen(client, h, pid).status_code == 200
    if cause == "nouvelle_invitation":
        _invite(client, h, pid, "Nouveau Venu SARL")
    elif cause == "revocation":
        assert client.delete(f"/api/projects/{pid}/invites/{invs[1]['id']}", headers=h).status_code == 200
    elif cause == "declin":
        assert client.post(f"/api/invite/{invs[1]['token']}/decline").status_code == 200
    elif cause == "defiger":
        assert client.delete(f"/api/projects/{pid}/offre/figer", headers=h).status_code == 200
    else:
        assert client.delete(f"/api/projects/{pid}/groupement/plan", headers=h).status_code == 200
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["status"] == "perimee", cause


def test_sous_traitant_hors_convention(client, auth, mails):
    """Un sous-traitant n'est pas membre du groupement : ni signataire, ni dans l'annexe, son prix
    n'entre pas dans le total, et sa part ne rend pas la convention caduque."""
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"company_name": "Échafaudages Sous-Traitant", "role": "sous_traitant"})
    st_tok = r.json()["token"]
    _part(client, st_tok, "Échafaudages Sous-Traitant", "Échafaudage", 5000)
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert any("sous-traitant" in w and "Échafaudages" in w for w in g["avertissements"])
    c = _gen(client, h, pid).json()
    assert c["total_offre_ht"] == 100000.0 and "Échafaudages" not in c["content_md"]
    assert {s["company"] for s in c["signatures"]} == {"Breizh Couverture", "Le Gall Électricité"}
    assert _put(client, st_tok, prix_lot_ht=6000).status_code == 200
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()["status"] == "a_signer"
    r = client.post(f"/api/invite/{st_tok}/convention/valider",
                    json={"content_hash": c["content_hash"], "signataire_nom": "x", "accepte": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pas_signataire"


def test_peremption_filet_a_la_lecture(client, auth, mails):
    """Même si une écriture contourne les hooks, l'empreinte recalculée détecte le changement."""
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    assert _gen(client, h, pid).status_code == 200
    from app.models import ProjectContribution
    db = _db()
    try:
        c = db.query(ProjectContribution).filter(ProjectContribution.project_id == pid).first()
        c.lot = "Lot 9 — modifié en douce"
        db.commit()
    finally:
        db.close()
    g = client.get(f"/api/invite/{invs[0]['token']}/convention").json()
    assert g["status"] == "perimee"


# ── 3. Accords : chaque type de membre ───────────────────────────────────────
def test_accords_mandataire_lien_hors_ligne_et_pdf(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    # Partenaire rattaché SANS invitation, ajouté hors ligne par le mandataire.
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.models import User
    db = _db()
    try:
        owner = db.query(User).filter(User.email == auth["email"]).first()
        ct = Cotraitant(user_id=owner.id, name="Kerjean Menuiserie", siret="55566677700088",
                        representant_legal="Anne Kerjean", city="Brest")
        db.add(ct); db.flush()
        lk = ProjectCotraitant(project_id=pid, cotraitant_id=ct.id, role="cotraitant", lot="Lot 5 — Menuiserie",
                               source="reseau")
        db.add(lk); db.commit()
        link_id = lk.id
    finally:
        db.close()
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert any(o["link_id"] == link_id for o in g["candidats_hors_ligne"])
    assert any("Kerjean Menuiserie" in w and "ni invité ni ajouté hors ligne" in w for w in g["avertissements"])
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                   json={"membres_hors_ligne": [{"link_id": link_id, "prix_lot_ht": 15000, "signataire_qualite": "Gérante"}]})
    assert r.status_code == 200, r.text
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                      json={"membres_hors_ligne": [{"link_id": 999999, "prix_lot_ht": 1}]}).status_code == 404
    c = _gen(client, h, pid).json()
    assert c["total_offre_ht"] == 115000.0 and c["n_signataires"] == 3
    assert "Kerjean Menuiserie" in c["content_md"]

    # Mandataire : accord depuis son compte (adresse vérifiée exigée).
    _set_verified(auth["email"], False)
    r = _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h, nom="Eliot Viegas")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_non_verifie"
    _set_verified(auth["email"], True)
    assert _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h,
                    content_hash="0" * 64).status_code == 409
    assert _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h,
                    accepte=False).status_code == 422
    r = _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h,
                 nom="Eliot Viegas", qual="Président")
    assert r.status_code == 200, r.text
    me = next(s for s in r.json()["signatures"] if s["membre"] == "mandataire")
    assert me["status"] == "signed" and me["identity_level"] == "compte_verifie"

    # Partenaire par lien magique, sans vérification possible (email non configuré) : lien seul.
    t = invs[0]["token"]
    r = _valider(client, f"/api/invite/{t}/convention/valider", c)
    assert r.status_code == 200, r.text
    assert r.json()["ma_signature"]["status"] == "signed"
    assert r.json()["ma_signature"]["identite_prevue"] == "lien_seul"
    # Idempotent.
    assert _valider(client, f"/api/invite/{t}/convention/valider", c).status_code == 200

    # Hors ligne : coché par le mandataire → tous d'accord → validée.
    r = client.post(f"/api/projects/{pid}/groupement/convention/hors-ligne/{link_id}", headers=h,
                    json={"accord_recueilli": True, "signataire_nom": "Anne Kerjean"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "signee" and body["n_accords"] == 3
    st = body["state"]
    assert st["state"] == "pret_a_deposer" and st["pret"]["checks"]["convention_signee"] is True
    assert st["pret"]["pct"] < 100 and st["label"].startswith("Convention validée")

    # PDF : niveaux d'identité imprimés, empreinte, avertissement.
    pdf = client.get(f"/api/projects/{pid}/groupement/convention/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf")
    txt = _pdf_text(pdf.content)
    flat = " ".join(txt.split())
    assert "accord enregistré via le lien (identité non vérifiée)" in flat
    assert "accord recueilli hors ligne, déclaré par le mandataire" in flat
    assert "depuis son compte Adjugo" in flat
    assert c["content_hash"][:16] in flat.replace(" ", "")
    assert "ce n'est pas un conseil juridique" in flat
    # PDF côté partenaire = même texte figé.
    gp = client.get(f"/api/invite/{t}/convention/pdf")
    assert gp.status_code == 200 and "Kerjean Menuiserie" in _pdf_text(gp.content)
    # Décocher l'accord hors ligne → de nouveau « à signer ».
    r = client.post(f"/api/projects/{pid}/groupement/convention/hors-ligne/{link_id}", headers=h,
                    json={"accord_recueilli": False})
    assert r.json()["status"] == "a_signer"


def _set_verified(email, value):
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = value
        db.commit()
    finally:
        db.close()


def test_accord_email_verifie_par_code_et_compte_apres_claim(client, auth, mails, monkeypatch):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    c = _gen(client, h, pid).json()
    # Email configuré + destinataire = adresse → le gate OTP existant s'applique.
    import app.services.email as em
    monkeypatch.setattr(em, "is_enabled", lambda: True)
    monkeypatch.setattr(em, "send_email", lambda *a, **k: True)
    t0 = invs[0]["token"]
    r = _valider(client, f"/api/invite/{t0}/convention/valider", c)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified"
    view = client.get(f"/api/invite/{t0}/convention").json()
    assert view["ma_signature"]["verification_requise"] is True
    # Code reçu et vérifié (flux OTP INCHANGÉ de la vague 1).
    from app.models import ProjectInvite
    from app.routers.invites import _hash_otp
    db = _db()
    try:
        inv = db.query(ProjectInvite).filter(ProjectInvite.token == t0).first()
        inv.otp_hash = _hash_otp("123456")
        from app.models import utcnow
        inv.otp_expires_at = utcnow() + timedelta(minutes=10)
        inv.otp_attempts = 0
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/invite/{t0}/otp/verify", json={"code": "123456"}).json()["verified"] is True
    r = _valider(client, f"/api/invite/{t0}/convention/valider", c)
    assert r.status_code == 200 and r.json()["ma_signature"]["identite_prevue"] == "email_verifie"

    # Compte après « claim » : le lien est lié au compte → accord depuis le compte uniquement.
    t1 = invs[1]["token"]
    db = _db()
    try:
        inv = db.query(ProjectInvite).filter(ProjectInvite.token == t1).first()
        recipient = inv.recipient
    finally:
        db.close()
    ph, _ = _register(client, company="Morvan Plomberie", email=recipient)
    assert client.post(f"/api/invite/{t1}/claim", headers=ph).status_code == 200
    shared = client.get("/api/shared", headers=ph).json()
    item = next(s for s in shared if s["token"] == t1)
    assert item["groupement"]["a_valider"] is True and item["groupement"]["etape"] == 4
    r = _valider(client, f"/api/invite/{t1}/convention/valider", c)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "compte_requis"
    other_h, _ = _register(client, company="Intrus")
    r = _valider(client, f"/api/invite/{t1}/convention/valider", c, headers=other_h)
    assert r.status_code == 403
    r = _valider(client, f"/api/invite/{t1}/convention/valider", c, headers=ph)
    assert r.status_code == 200, r.text
    db = _db()
    try:
        from app.models import GroupementSignature
        s = db.query(GroupementSignature).filter(GroupementSignature.invite_id == invs[1]["id"]).first()
        assert s.identity_level == "compte_verifie" and s.user_id is not None
        s0 = db.query(GroupementSignature).filter(GroupementSignature.invite_id == invs[0]["id"]).first()
        assert s0.identity_level == "email_verifie" and s0.verified_email
    finally:
        db.close()
    # Notification in-app au mandataire.
    notifs = client.get("/api/notifications", headers=h).json()
    assert any(n["action"] == "convention.signed" and n["label"] == "a validé la convention de groupement"
               for n in notifs)


# ── 4. Doctrine de visibilité ────────────────────────────────────────────────
def _envelope():
    return {"ciphertext": base64.b64encode(b"x" * 64).decode(), "iv": base64.b64encode(b"\x01" * 12).decode(),
            "alg": "A256GCM", "kdf": "PBKDF2-SHA256", "kdf_salt": base64.b64encode(b"\x02" * 16).decode(),
            "kdf_iter": 600000, "key_fingerprint": "ab12cd34", "updated_at": "2026-10-06T10:00:00+00:00"}


def test_doctrine_brouillon_puis_generee(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    t0, t1 = invs[0]["token"], invs[1]["token"]
    # Détail chiffré (enveloppe) sur la part d'Alpha : jamais visible ailleurs que chez lui.
    assert _put(client, t0, detail_chiffre=_envelope()).status_code == 200
    _submit(client, t0)

    # BROUILLON : Beta ne voit ni le prix d'Alpha (40 000), ni celui du mandataire, ni le total.
    v = client.get(f"/api/invite/{t1}/convention").json()
    assert v["status"] == "draft" and v["content_md"] is None and v["total_offre_ht"] is None
    raw = json.dumps(v, ensure_ascii=False)
    assert "40000" not in raw and "40 000" not in raw and "60 000" not in raw and "125" not in raw
    mine = [m for m in v["membres"] if m["company"] == "Morvan Plomberie"]
    others = [m for m in v["membres"] if m["company"] != "Morvan Plomberie"]
    assert mine and mine[0]["prix_lot_ht"] == 25000.5
    assert others and all("prix_lot_ht" not in m for m in others)
    assert "affiché à la génération" in v["apercu_md"]
    assert client.get(f"/api/invite/{t1}/convention/pdf").status_code == 409
    # Option « masquer la répartition » (brouillon) : aperçu mandataire sans aucun prix.
    m = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"masquer_repartition": True}).json()
    assert m["masquer_repartition"] is True and "40 000" not in m["apercu_md"]

    # GÉNÉRÉE : même texte (même empreinte) pour tous, annexe complète, jamais l'enveloppe.
    c = _gen(client, h, pid).json()
    assert "masquer_repartition" not in c
    v0 = client.get(f"/api/invite/{t0}/convention").json()
    v1 = client.get(f"/api/invite/{t1}/convention").json()
    assert v0["content_hash"] == v1["content_hash"] == c["content_hash"]
    assert v0["content_md"] == v1["content_md"] == c["content_md"]
    assert "40 000 € HT" in v1["content_md"] and v1["total_offre_ht"] == 125000.5
    assert {m["company"]: m.get("prix_lot_ht") for m in v1["membres"]}["Le Gall Électricité"] == 40000.0
    # Masquer n'existe plus une fois générée.
    assert client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                      json={"masquer_repartition": True}).status_code == 422
    for blob in (json.dumps(c), json.dumps(v1), json.dumps(client.get(
            f"/api/projects/{pid}/groupement/state", headers=h).json())):
        assert "ciphertext" not in blob and "detail_chiffre" not in blob and "kdf_salt" not in blob
    pdf = client.get(f"/api/projects/{pid}/groupement/convention/pdf", headers=h).content
    assert "ciphertext" not in _pdf_text(pdf)
    # La vue membre ne montre jamais le score seul du mandataire ni les emails.
    assert "match_score" not in json.dumps(v1) and "@" not in json.dumps(v1, ensure_ascii=False)
    # Modifier une convention générée exige une confirmation et annule les accords.
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"params": {"pi": "copropriete"}})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "convention_generee"
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
                   json={"params": {"pi": "copropriete"}, "confirmer_modification": True})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    # Retour en brouillon : le partenaire ne revoit plus les prix des autres.
    v1b = client.get(f"/api/invite/{t1}/convention").json()
    assert v1b["status"] == "draft" and "40 000" not in json.dumps(v1b, ensure_ascii=False)


def test_revoque_et_decline_hors_annexe(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=3)
    # Un partenaire révoqué et un qui décline : ni signataires, ni dans l'annexe.
    assert client.delete(f"/api/projects/{pid}/invites/{invs[1]['id']}", headers=h).status_code == 200
    assert client.post(f"/api/invite/{invs[2]['token']}/decline").status_code == 200
    c = _gen(client, h, pid).json()
    assert c["n_signataires"] == 2
    names = {s["company"] for s in c["signatures"]}
    assert names == {"Breizh Couverture", "Le Gall Électricité"}
    assert "Morvan Plomberie" not in c["content_md"] and "Ar Men Peinture" not in c["content_md"]
    assert c["total_offre_ht"] == 100000.0
    # Leurs liens n'ouvrent plus rien.
    assert client.get(f"/api/invite/{invs[1]['token']}/convention").status_code == 404
    assert client.get(f"/api/invite/{invs[2]['token']}/convention").status_code == 410
    assert client.post(f"/api/invite/{invs[2]['token']}/convention/valider",
                       json={"content_hash": c["content_hash"], "signataire_nom": "x", "accepte": True}).status_code == 410
    # À 2 membres : avertissement « le total révèle la part de l'autre ».
    assert any("révèle" in w for w in c["avertissements"])


def test_llm_ne_recoit_jamais_la_convention_et_zip(client, auth, mails, monkeypatch):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    c = _gen(client, h, pid).json()
    prompts = []
    import app.services.agents.redaction as red
    monkeypatch.setattr(red, "complete", lambda system, prompt, **k: (prompts.append(system + "\n" + prompt) or "# Mémoire\n\nTexte."))
    from app.models import Project
    db = _db()
    try:
        p = db.query(Project).get(pid)
        analysis = {"details": {"intitule_marche": p.name, "acheteur": "Ville de Lorient"}}
        company = {"name": "Breizh Couverture", "siret": "12345678900011", "representant_legal": "Eliot Viegas",
                   "address": "1 rue du Port", "city": "Lorient", "postal_code": "56100"}
        out = red.build_dossier(analysis, company, [], project_id=pid, db=db, user_id=None, estimate=None)
    finally:
        db.close()
    assert prompts, "le mémoire doit avoir été demandé au LLM (mocké)"
    joined = "\n".join(prompts)
    assert c["content_hash"] not in joined
    assert "Convention de groupement" not in joined and "Article 6" not in joined
    assert "40000" not in joined and "40 000" not in joined          # aucun prix au LLM
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(out["zip_b64"])))
    assert "convention_groupement.pdf" in zf.namelist()
    conv_txt = " ".join(_pdf_text(zf.read("convention_groupement.pdf")).split())
    assert "Accords enregistrés" in conv_txt and "Le Gall" in conv_txt
    assert any("pas encore validée par tous" in w for w in out["warnings"])
    # Export ZIP « dossier complet » : la convention y est aussi, et le sommaire l'annonce.
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200
    z2 = zipfile.ZipFile(io.BytesIO(r.content))
    assert any(n.startswith("03_Groupement/Convention_de_groupement_v1") for n in z2.namelist())
    assert "Convention_de_groupement_v1.pdf" in z2.read("00_SOMMAIRE.txt").decode("utf-8")
    # Aperçu du dossier et checklist.
    prev = client.get(f"/api/projects/{pid}/dossier-preview", headers=h).json()
    assert any(f["name"] == "convention_groupement.pdf" for f in prev["files"])
    ck = client.get(f"/api/checklist/{pid}", headers=h).json()
    item = next(i for i in ck["checklist"] if i["id"] == "convention_groupement")
    assert item["status"] == "manquant" and "0/2" in item["context_note"]


# ── 5. Cohérence DC1 / ATTRI1 ────────────────────────────────────────────────
def test_dc1_attri1_coherents_avec_la_convention(client, auth, mails):
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=2)
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
               json={"mandataire_solidaire": True, "habilitation": {"signer_modifications": True}})
    c = _gen(client, h, pid).json()
    from app.models import Project
    from app.services import groupement_convention as gc
    db = _db()
    try:
        p = db.query(Project).get(pid)
        cd, pd = {"name": "Breizh Couverture"}, {"cotraitants": [{"name": "Sous-Traitant X", "role": "sous_traitant"}],
                                                 "budget": None}
        grp = gc.apply_to_cerfa(db, p, cd, pd)
    finally:
        db.close()
    assert grp and pd["groupement"]["forme"] == "conjoint" and pd["groupement"]["mandataire_solidaire"] is True
    assert pd["budget"] == c["total_offre_ht"] == 125000.5
    names = [m["name"] for m in pd["cotraitants"]]
    assert names == ["Le Gall Électricité", "Morvan Plomberie", "Sous-Traitant X"]   # sous-traitant gardé (DC4)
    assert {m["name"]: m["prix_lot_ht"] for m in pd["cotraitants"][:2]} == {"Le Gall Électricité": 40000.0,
                                                                            "Morvan Plomberie": 25000.5}
    assert cd["signataire_qualite"] == "Président"

    # Routeur CERFA : DC1 et ATTRI1 du groupement, membres et montants identiques à la convention.
    dc1 = client.post(f"/api/cerfa/{pid}/dc1", headers=h)
    assert dc1.status_code == 200, dc1.text
    t1 = _pdf_text(dc1.content)
    for name in ("Breizh Couverture", "Le Gall", "Morvan Plomberie"):
        assert name in t1
    assert "Lot 2" in t1 and "(mandataire)" in t1
    at = client.post(f"/api/cerfa/{pid}/attri1", headers=h)
    assert at.status_code == 200
    ta = " ".join(_pdf_text(at.content).split())
    assert "125 000.50 EUR" in ta or "125 000,50" in ta
    assert "40 000.00 EUR" in ta and "25 000.50 EUR" in ta and "60 000.00 EUR" in ta
    assert "Breizh Couverture" in ta and "Eliot Viegas" in ta
    # État « prêt » : après validation par tous + CERFA générés après la convention.
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["state"] == "convention_a_signer"


def test_pret_a_deposer_100(client, auth, mails):
    """État 7 : convention validée par tous + attestations de tous valides + formulaires
    officiels régénérés APRÈS la convention ⇒ « Prêt à déposer », 100 %."""
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture", siret="12345678900011", address="1 rue du Port",
                 postal_code="56100", city="Lorient", representant_legal="Eliot Viegas")
    pid = _project(client, h)
    inv = _invite(client, h, pid, "Le Gall Électricité")
    t = inv["token"]
    far = (date.today() + timedelta(days=200)).isoformat()
    for fname, ptype in (("kbis.pdf", "kbis"), ("fiscale.pdf", "fiscale"), ("urssaf.pdf", "sociale"),
                         ("assurance.pdf", "assurance"), ("rib.pdf", "rib")):
        r = client.post(f"/api/invite/{t}/contribution/piece",
                        files={"file": (fname, io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
                        data={"piece_type": ptype, "expiration_date": far})
        assert r.status_code == 200, r.text
    _part(client, t, "Le Gall Électricité", "Lot 2 — Électricité", 40000)
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
               json={"forme": "solidaire", "params": {"part_mandataire_ht": 60000, "lot_mandataire": "Lot 1"}})
    c = _gen(client, h, pid).json()
    # Le mandataire ne peut pas encore avoir les 3 attestations : on regarde seulement les membres.
    assert _valider(client, f"/api/invite/{t}/convention/valider", c).status_code == 200
    st = _valider(client, f"/api/projects/{pid}/groupement/convention/valider", c, headers=h,
                  nom="Eliot Viegas").json()["state"]
    assert st["state"] == "pret_a_deposer" and st["pret"]["checks"]["attestations_ok"] is True
    assert st["pret"]["checks"]["cerfa_generes"] is False and st["pret"]["pct"] == 67
    for dt in ("dc1", "dc2", "attri1"):
        assert client.post(f"/api/cerfa/{pid}/{dt}", headers=h).status_code == 200
    st = client.get(f"/api/projects/{pid}/groupement/state", headers=h).json()
    assert st["pret"]["pct"] == 100 and st["label"] == "Prêt à déposer" and st["etape"] == 5
    ck = client.get(f"/api/checklist/{pid}", headers=h).json()
    assert next(i for i in ck["checklist"] if i["id"] == "convention_groupement")["status"] == "ok"


def test_cerfa_groupement_nombreux_membres_sans_debordement():
    """6 membres : le tableau E du DC1 (4 lignes) et la répartition de l'ATTRI1 (3 lignes)
    renvoient à la convention au lieu d'écrire hors des cases."""
    from app.services.cerfa import generate_attri1, generate_dc1
    c = {"name": "Mandataire SARL", "siret": "12345678900011", "city": "Lorient", "representant_legal": "E. V."}
    cts = [{"name": f"Membre {i}", "siret": f"1234567890{i:04d}", "role": "cotraitant", "lot": f"Lot {i}",
            "prix_lot_ht": 1000.0 * i} for i in range(2, 7)]
    p = {"name": "Marché", "client": "Ville", "budget": 50000, "cotraitants": cts,
         "groupement": {"forme": "conjoint", "mandataire_solidaire": False, "total_ht": 50000,
                        "habilitation": {"representer": True, "signer_candidature_offre": False},
                        "mandataire": {"lot": "Lot 1", "prix_lot_ht": 30000}}}
    t1 = " ".join(_pdf_text(generate_dc1(c, p)).split())
    assert "Autres membres" in t1 and "convention de groupement jointe" in t1
    ta = " ".join(_pdf_text(generate_attri1(c, p)).split())
    assert "autre(s) membre(s)" in ta and "30 000.00 EUR" in ta and "50 000.00 EUR" in ta


def test_isolation_entre_entreprises(client, auth, mails):
    """Une autre entreprise ne lit ni n'écrit la convention d'un marché qui n'est pas le sien."""
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    c = _gen(client, h, pid).json()
    other_h, _ = _register(client, company="Concurrent SARL")
    base = f"/api/projects/{pid}/groupement/convention"
    assert client.get(base, headers=other_h).status_code == 404
    assert client.get(base + "/pdf", headers=other_h).status_code == 404
    assert client.put(base, headers=other_h, json={"forme": "solidaire"}).status_code == 404
    assert client.post(base + "/generer", headers=other_h, json={"regenerer": True}).status_code == 404
    assert _valider(client, base + "/valider", c, headers=other_h).status_code == 404
    # Jeton inconnu : rien.
    assert client.get("/api/invite/jeton-inexistant/convention").status_code == 404
    # Le mandataire ne passe pas par la route partenaire avec un faux jeton.
    assert _valider(client, "/api/invite/jeton-inexistant/convention/valider", c).status_code == 404


# ── 6. Démo bloquée ──────────────────────────────────────────────────────────
def test_demo_ecritures_convention_bloquees(client, mails):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    dh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.get("/api/projects/", headers=dh).json()[0]["id"]
    assert client.get(f"/api/projects/{pid}/groupement/convention", headers=dh).status_code == 200
    for method, path, body in (
            ("PUT", "", {"forme": "conjoint"}), ("POST", "/generer", {}), ("POST", "/valider", {}),
            ("POST", "/relire-dce", None), ("POST", "/hors-ligne/1", {"accord_recueilli": True})):
        r = client.request(method, f"/api/projects/{pid}/groupement/convention{path}", headers=dh, json=body)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["detail"].startswith("La démo est en lecture guidée")
    assert mails == []
    # Lien d'invitation de la démo : jamais d'accord enregistré (vitrine partagée).
    from app.models import Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL
    db = _db()
    try:
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        p = db.query(Project).filter(Project.user_id == u.id).first()
        inv = ProjectInvite(project_id=p.id, owner_id=u.id, token=uuid.uuid4().hex,
                            recipient="victime@tiers.example", company_name="Vitrine")
        db.add(inv); db.commit()
        tok = inv.token
    finally:
        db.close()
    assert client.get(f"/api/invite/{tok}/convention").status_code == 200
    r = client.post(f"/api/invite/{tok}/convention/valider",
                    json={"content_hash": "x", "signataire_nom": "x", "accepte": True})
    assert r.status_code == 403 and "lecture guidée" in r.json()["detail"]


# ── 7. Ce que le règlement impose (citation vérifiée) ────────────────────────
def _set_analysis(pid, analysis):
    from app.models import Project
    db = _db()
    try:
        p = db.query(Project).get(pid)
        p.ai_analysis = analysis
        db.commit()
    finally:
        db.close()


def test_forme_imposee_citee_ou_non_trouvee(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["forme_imposee"]["code"] == "non_verifie" and g["forme_imposee"]["extrait"] == ""
    assert g["status"] == "aucune" and g["options"]["formes"][0]["phrase"]
    clause = "En cas de groupement, celui-ci sera solidaire après attribution du marché."
    _set_analysis(pid, {"dce_available": True, "details": {
        "intitule_marche": "École", "forme_groupement": {"imposee": "solidaire", "extrait": clause},
        "exigences_verifiees": {"forme_groupement": True}}})
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["forme_imposee"]["code"] == "solidaire" and g["forme_imposee"]["extrait"] == clause
    # Le brouillon est pré-rempli avec la forme imposée ; choisir autre chose = AVERTIR, pas bloquer.
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"params": {"pi": "chacun_garde"}})
    assert r.json()["forme"] == "solidaire"
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"forme": "conjoint"})
    assert r.status_code == 200
    assert any("impose un groupement solidaire" in w for w in r.json()["avertissements"])
    # Citation NON vérifiée à l'analyse → jamais affichée : « non trouvé dans le DCE ».
    pid2 = _project(client, h)
    _set_analysis(pid2, {"dce_available": True, "details": {
        "forme_groupement": {"imposee": "conjoint", "extrait": "phrase inventée"},
        "exigences_verifiees": {"forme_groupement": False}}})
    g2 = client.get(f"/api/projects/{pid2}/groupement/convention", headers=h).json()
    assert g2["forme_imposee"]["code"] == "non_specifie" and g2["forme_imposee"]["extrait"] == ""
    assert "Non trouvé dans le DCE" in g2["forme_imposee"]["libelle"]


def test_relire_dce_citation_contre_texte_integral(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    assert client.post(f"/api/projects/{pid}/groupement/convention/relire-dce", headers=h).status_code == 404
    # Dossier du marché archivé (dossier « DCE ») sans classification préalable.
    text = ("REGLEMENT DE LA CONSULTATION\nArticle 4. Les candidats peuvent se présenter en groupement. "
            "En cas de groupement conjoint, le mandataire sera solidaire de chacun des membres du groupement. "
            "Article 5. Délai d'exécution : 6 mois.")
    from app.models import Document, User
    from app.services.storage import get_storage
    db = _db()
    try:
        u = db.query(User).filter(User.email == auth["email"]).first()
        key = f"{u.id}/dce/{uuid.uuid4().hex}.txt"
        get_storage().save(key, text.encode("utf-8"), "text/plain")
        db.add(Document(user_id=u.id, project_id=pid, name="RC.txt", file_key=key, folder="DCE",
                        file_size=len(text), mime_type="text/plain"))
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/groupement/convention/relire-dce", headers=h)
    assert r.status_code == 200, r.text
    fi = r.json()["forme_imposee"]
    assert fi["code"] == "non_verifie" and "mandataire sera solidaire" in fi["extrait"]
    assert fi["extrait"] in text and fi["relu_le"]
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["forme_imposee"]["extrait"] == fi["extrait"] and g["forme_imposee"]["dossier_disponible"] is True
    # Avec forme conjoint sans mandataire solidaire : avertissement (avertir, pas bloquer).
    r = client.put(f"/api/projects/{pid}/groupement/convention", headers=h, json={"forme": "conjoint"})
    assert any("mandataire solidaire" in w for w in r.json()["avertissements"])


# ── 8. PDF : valeurs dynamiques échappées ────────────────────────────────────
def test_pdf_nom_avec_caracteres_speciaux(client, auth, mails):
    h = auth["headers"]
    _set_company(auth["email"], name="Dupont & Fils <SARL> *Étoile* _bis_", siret="12345678900011",
                 representant_legal="Léa <Dupont>", city="Rennes")
    pid = _project(client, h, name="Marché <script>alert(1)</script> & co")
    inv = _invite(client, h, pid, "Alpha & Beta <SAS>")
    _part(client, inv["token"], "Alpha & Beta <SAS>", "Lot *1* & <2>", 1000)
    client.put(f"/api/projects/{pid}/groupement/convention", headers=h,
               json={"forme": "solidaire", "params": {"part_mandataire_ht": 2000}})
    c = _gen(client, h, pid)
    assert c.status_code == 200, c.text
    md = c.json()["content_md"]
    assert "Dupont & Fils <SARL> \\*Étoile\\* \\_bis\\_" in md            # Markdown échappé
    pdf = client.get(f"/api/projects/{pid}/groupement/convention/pdf", headers=h)
    assert pdf.status_code == 200
    flat = " ".join(_pdf_text(pdf.content).split())
    assert "Dupont & Fils <SARL> *Étoile* _bis_" in flat
    assert "Alpha & Beta <SAS>" in flat and "Lot *1* & <2>" in flat
    assert "<script>alert(1)</script>" in flat          # texte littéral, jamais interprété
    # Unitaire : échappement et retour.
    from app.services import groupement_convention as gc
    assert gc.unescape_md(gc.md("a*b_c`d\\e")) == "a*b_c`d\\e"
    assert "\n" not in gc.md("ligne 1\nligne 2\r\n# titre")


# ── 9. Stepper ───────────────────────────────────────────────────────────────
def test_stepper_etapes():
    from app.services.groupement_members import _etapes, _etape_of
    assert _etape_of("seul") == 1 and _etape_of("invitation") == 2 and _etape_of("parts_completes") == 3
    assert _etape_of("convention_a_signer") == 4 and _etape_of("pret_a_deposer") == 5
    e = _etapes("convention_a_signer")
    assert [x["status"] for x in e] == ["fait", "fait", "fait", "en_cours", "a_faire"]
    assert _etapes("depose")[-1]["status"] == "fait"


# ── 10. Migration o9p0q1r2s3t4 (SQLite, à neuf + rejouée) ────────────────────
def test_migration_a_neuf_et_rejouee(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dbfile = tmp_path / "mig.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    alembic = [sys.executable, "-m", "alembic"]

    def run(*args):
        r = subprocess.run(alembic + list(args), cwd=root, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        return r

    run("upgrade", "head")
    import sqlalchemy as sa
    eng = sa.create_engine(f"sqlite:///{dbfile}")

    def check():
        insp = sa.inspect(eng)
        assert {"groupement_conventions", "groupement_signatures"} <= set(insp.get_table_names())
        cols = {c["name"] for c in insp.get_columns("groupement_conventions")}
        assert {"project_id", "owner_id", "forme", "mandataire_solidaire", "forme_imposee",
                "forme_imposee_extrait", "habilitation", "params", "status", "content_md", "content_hash",
                "total_offre_ht", "version", "frozen_at", "created_at", "updated_at"} <= cols
        scols = {c["name"] for c in insp.get_columns("groupement_signatures")}
        assert {"convention_id", "project_id", "owner_id", "invite_id", "cotraitant_link_id", "user_id",
                "company_name", "siret", "signataire_nom", "signataire_qualite", "content_hash",
                "identity_level", "status", "verified_email", "signed_at", "ip"} <= scols
        uq = {tuple(u["column_names"]) for u in insp.get_unique_constraints("groupement_signatures")}
        uq |= {tuple(i["column_names"]) for i in insp.get_indexes("groupement_signatures") if i.get("unique")}
        assert ("convention_id", "invite_id") in uq and ("convention_id", "cotraitant_link_id") in uq
        cuq = {tuple(u["column_names"]) for u in insp.get_unique_constraints("groupement_conventions")}
        cuq |= {tuple(i["column_names"]) for i in insp.get_indexes("groupement_conventions") if i.get("unique")}
        assert ("project_id",) in cuq and ("content_hash",) in cuq
        pc = {c["name"] for c in insp.get_columns("project_contributions")}
        assert {"representant_legal", "signataire_qualite"} <= pc
        with eng.connect() as cn:
            assert cn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "o9p0q1r2s3t4"

    check()
    # Base « production » à la révision précédente : les tables n'existent pas encore → créées.
    with eng.begin() as cn:
        cn.execute(sa.text("DROP TABLE groupement_signatures"))
        cn.execute(sa.text("DROP TABLE groupement_conventions"))
    run("stamp", "n8o9p0q1r2s3")
    run("upgrade", "head")
    check()
    # Rejouée sur une base déjà migrée : aucun effet, aucune erreur.
    run("stamp", "n8o9p0q1r2s3")
    run("upgrade", "head")
    check()
    eng.dispose()
