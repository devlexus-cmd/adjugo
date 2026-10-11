"""
Heure de Paris dans les PDF de co-traitance (au lieu de l'UTC).

Le PDF « journal » d'un partenaire et la section « Accords enregistrés » du PDF de la convention
affichaient l'heure UTC (« 11/10/2026 à 20:28 (UTC) ») alors que l'écran affiche 22:28. Ils
affichent désormais l'heure de Paris. Invariants vérifiés :
- conversion hiver (UTC+1), été (UTC+2), changements d'heure (dernier dimanche de mars et
  d'octobre), datetime naïf (= UTC) ou avec fuseau, passage de jour ;
- repli sans base des fuseaux : l'heure UTC, dite « (UTC) » ; la base vient du paquet tzdata
  (l'image de production n'a pas de base système) ;
- AFFICHAGE SEULEMENT : le JSON du journal garde `at` en UTC (il entre dans les maillons), sa
  vérification hors ligne passe toujours ; le texte de la convention (render, content_hash) ne
  dépend d'aucune heure affichée.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from tests.test_convention_groupement import _db, _gen, _groupement, _pdf_text, _valider
from tests.test_cotraitance_v4 import _scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import app.routers.invites as inv
    monkeypatch.setattr(inv, "_send_mails_async", lambda m: sent.extend(m))
    return sent


@pytest.fixture(autouse=True)
def _fresh():
    from app.services import audit_anchor
    from app.services import format as fmt
    from app.services import journal_membre as jm
    fmt._tz_paris.cache_clear()
    jm.reset_caches()
    audit_anchor.reset_cache()
    yield
    # Jamais un repli « UTC » laissé en cache aux tests suivants.
    getattr(fmt._tz_paris, "cache_clear", lambda: None)()
    jm.reset_caches()
    audit_anchor.reset_cache()


@pytest.fixture
def sans_fuseau(monkeypatch):
    """Base des fuseaux introuvable (ni système, ni tzdata) : ZoneInfo échoue."""
    import zoneinfo
    from app.services import format as fmt

    def boom(key):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")
    monkeypatch.setattr(zoneinfo, "ZoneInfo", boom)
    fmt._tz_paris.cache_clear()
    yield
    fmt._tz_paris.cache_clear()


def _flat(pdf: bytes) -> str:
    return " ".join(_pdf_text(pdf).split())


# ═══ 1. Le formateur partagé ══════════════════════════════════════════════════════════

def test_ete_utc_plus_2_le_cas_signale():
    from app.services.format import date_heure_fr, libelle_fuseau
    # Le cas constaté : 20:28 UTC affiché 22:28 à l'écran.
    assert date_heure_fr(datetime(2026, 10, 11, 20, 28)) == "11/10/2026 à 22:28 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 10, 11, 20, 28), suffixe=False) == "11/10/2026 à 22:28"
    assert libelle_fuseau() == "heure de Paris"


def test_hiver_utc_plus_1():
    from app.services.format import date_heure_fr
    assert date_heure_fr(datetime(2026, 1, 15, 20, 28)) == "15/01/2026 à 21:28 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 12, 1, 8, 5)) == "01/12/2026 à 09:05 (heure de Paris)"


def test_changement_d_heure_octobre_et_mars():
    from app.services.format import date_heure_fr
    # Dernier dimanche d'octobre 2026 = 25/10 : à 01:00 UTC, 03:00 (été) redevient 02:00 (hiver).
    assert date_heure_fr(datetime(2026, 10, 25, 0, 59)) == "25/10/2026 à 02:59 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 10, 25, 1, 0)) == "25/10/2026 à 02:00 (heure de Paris)"
    # La même heure affichée deux fois (02:30) pour deux instants distincts : c'est l'heure légale.
    assert date_heure_fr(datetime(2026, 10, 25, 0, 30)) == date_heure_fr(datetime(2026, 10, 25, 1, 30))
    # Veille et lendemain : décalage d'été puis d'hiver.
    assert date_heure_fr(datetime(2026, 10, 24, 12, 0)) == "24/10/2026 à 14:00 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 10, 26, 12, 0)) == "26/10/2026 à 13:00 (heure de Paris)"
    # Dernier dimanche de mars 2026 = 29/03 : à 01:00 UTC, 02:00 (hiver) devient 03:00 (été).
    assert date_heure_fr(datetime(2026, 3, 29, 0, 59)) == "29/03/2026 à 01:59 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 3, 29, 1, 0)) == "29/03/2026 à 03:00 (heure de Paris)"


def test_naif_egal_utc_et_datetime_avec_fuseau():
    from app.services.format import date_heure_fr
    naif = datetime(2026, 10, 11, 20, 28)
    assert date_heure_fr(naif) == date_heure_fr(naif.replace(tzinfo=timezone.utc))
    # Un datetime d'un autre fuseau est converti, pas réétiqueté.
    plus5 = datetime(2026, 10, 12, 1, 28, tzinfo=timezone(timedelta(hours=5)))       # = 20:28 UTC
    assert date_heure_fr(plus5) == "11/10/2026 à 22:28 (heure de Paris)"
    # Déjà à l'heure de Paris : inchangé.
    assert date_heure_fr(datetime(2026, 10, 11, 22, 28, tzinfo=PARIS)) == "11/10/2026 à 22:28 (heure de Paris)"
    # Passage de jour (et d'année) : la DATE suit l'heure de Paris.
    assert date_heure_fr(datetime(2026, 12, 31, 23, 30)) == "01/01/2027 à 00:30 (heure de Paris)"
    assert date_heure_fr(datetime(2026, 12, 31, 23, 30))[:10] == "01/01/2027"


def test_valeurs_vides_et_inattendues():
    from app.services.format import date_heure_fr
    assert date_heure_fr(None) == "" and date_heure_fr("") == ""
    assert date_heure_fr("pas une date") == "pas une date"          # jamais d'exception


def test_repli_sans_base_des_fuseaux(sans_fuseau):
    from app.services.format import date_heure_fr, libelle_fuseau
    assert libelle_fuseau() == "UTC"
    assert date_heure_fr(datetime(2026, 10, 11, 20, 28)) == "11/10/2026 à 20:28 (UTC)"
    assert date_heure_fr(datetime(2026, 1, 15, 20, 28), suffixe=False) == "15/01/2026 à 20:28"
    aware = datetime(2026, 10, 12, 1, 28, tzinfo=timezone(timedelta(hours=5)))
    assert date_heure_fr(aware) == "11/10/2026 à 20:28 (UTC)"


def _run(code: str, env_extra: dict) -> str:
    env = {**os.environ, **env_extra}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_fuseau_resolu_par_tzdata_sans_base_systeme():
    """L'image de production (python:3.12-slim) n'a pas de base des fuseaux : PYTHONTZPATH vide
    l'imite. Europe/Paris doit se résoudre par le paquet tzdata (requirements.lock)."""
    code = ("import zoneinfo, tzdata; from datetime import datetime;"
            "from app.services.format import date_heure_fr;"
            "assert zoneinfo.TZPATH == (), zoneinfo.TZPATH;"
            "print(date_heure_fr(datetime(2026, 10, 11, 20, 28)))")
    assert _run(code, {"PYTHONTZPATH": ""}) == "11/10/2026 à 22:28 (heure de Paris)"


def test_repli_reel_sans_tzdata_ni_base_systeme():
    code = ("import sys; sys.modules['tzdata'] = None;"
            "from datetime import datetime;"
            "from app.services.format import date_heure_fr, libelle_fuseau;"
            "print(date_heure_fr(datetime(2026, 10, 11, 20, 28)) + '|' + libelle_fuseau())")
    assert _run(code, {"PYTHONTZPATH": ""}) == "11/10/2026 à 20:28 (UTC)|UTC"


# ═══ 2. Journal du membre : PDF à l'heure de Paris, JSON inchangé ══════════════════════

def _payload(**over):
    p = {
        "schema": "adjugo-journal-membre-v1", "exporte_le": "2026-10-25T01:30:00Z",
        "marche": "Réhabilitation de l'école", "membre": "Alpha SARL",
        "verdict": {"verdict": "intact", "verdict_label": "Intact", "message": "Journal intact."},
        "integrity_label": "Journal vérifiable", "empreinte": "f" * 64, "limites": [],
        "entrees": [
            {"n": 1, "at": "2026-01-15T20:28:00.000000", "action": "guest.view_project", "qui": "vous",
             "label": "Vous avez consulté le dossier", "detail": "", "sceau": "a" * 64, "maillon": "b" * 64,
             "statut": "verifiee", "rattachement_scelle": True},
            {"n": 2, "at": "2026-10-11T20:28:00.123456", "action": "guest.submit_contribution", "qui": "vous",
             "label": "Vous avez soumis votre part", "detail": "", "sceau": "c" * 64, "maillon": "d" * 64,
             "statut": "verifiee", "rattachement_scelle": True},
        ],
    }
    p.update(over)
    return p


def test_pdf_journal_heures_de_paris():
    from app.services import journal_membre as jm
    flat = _flat(jm.export_pdf(_payload()))
    assert "Date (heure de Paris)" in flat and "Date (UTC)" not in flat
    assert "15/01/2026 à 21:28" in flat and "15/01/2026 à 20:28" not in flat      # hiver
    assert "11/10/2026 à 22:28" in flat and "11/10/2026 à 20:28" not in flat      # été
    # Export fait la nuit du changement d'heure (01:30 UTC = 02:30 heure d'hiver).
    assert "Exporté le 25/10/2026 à 02:30 (heure de Paris)" in flat
    # La phrase d'explication dit où sont les heures UTC (le fichier JSON, pour la vérification).
    assert "le fichier JSON les garde en temps universel (UTC) pour la vérification" in flat


def test_pdf_journal_repli_utc(sans_fuseau):
    from app.services import journal_membre as jm
    flat = _flat(jm.export_pdf(_payload()))
    assert "Date (UTC)" in flat and "heure de Paris" not in flat
    assert "11/10/2026 à 20:28" in flat and "Exporté le 25/10/2026 à 01:30 (UTC)" in flat
    assert "temps universel (UTC), comme le fichier JSON" in flat


def test_message_d_alteration_a_l_heure_de_paris():
    from app.services import journal_membre as jm
    msg = jm._message("altere", "vos_entrees", 3, 2, 0,
                      {"n": 2, "at": "2026-10-11T20:28:00", "label": "Vous avez soumis votre part"},
                      False, None)
    assert "(entrée du 11/10/2026 à 22:28, heure de Paris : « Vous avez soumis votre part »)" in msg


def test_export_reel_pdf_paris_json_utc_inchange(client, auth, mails, monkeypatch):
    from app.models import AuditLog
    from app.services import audit
    from app.services import format as fmt
    from app.services import journal_membre as jm
    pid, a, b = _scenario(client, auth)
    ta = a["token"]

    # JSON : `at` = horodatage UTC canonique de la base (le même que celui haché dans les maillons).
    doc = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    assert jm.verify_export(doc)["ok"] is True and doc["exporte_le"].endswith("Z")
    db = _db()
    try:
        utc_ts = {audit._ts(r.created_at) for r in db.query(AuditLog).filter(AuditLog.project_id == pid).all()}
    finally:
        db.close()
    assert doc["entrees"] and all(e["at"] in utc_ts for e in doc["entrees"])
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}", e["at"]) for e in doc["entrees"])
    assert "heure de Paris" not in json.dumps(doc["entrees"], ensure_ascii=False)

    # PDF : chaque heure est celle de Paris (calculée ici indépendamment du code testé).
    pdf = client.get(f"/api/invite/{ta}/journal/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    flat = _flat(pdf.content)
    assert "Date (heure de Paris)" in flat and "Date (UTC)" not in flat
    assert "le fichier JSON les garde en temps universel (UTC)" in flat
    for e in doc["entrees"]:
        dt = datetime.fromisoformat(e["at"]).replace(tzinfo=timezone.utc)
        paris = dt.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M")
        utc = dt.strftime("%d/%m/%Y à %H:%M")
        assert paris in flat, (paris, flat[:400])
        assert utc not in flat

    # L'affichage n'entre pas dans la preuve : même export JSON avec ou sans base des fuseaux.
    with_paris = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    monkeypatch.setattr(fmt, "_tz_paris", lambda: None)
    jm.reset_caches()
    without = client.get(f"/api/invite/{ta}/journal/export?format=json").json()
    assert jm.verify_export(without)["ok"] is True
    assert jm.prolonge(doc, with_paris) is True and jm.prolonge(with_paris, without) is True
    keys = ("n", "at", "action", "qui", "sceau", "maillon")
    assert [{k: x[k] for k in keys} for x in with_paris["entrees"]] == \
           [{k: x[k] for k in keys} for x in without["entrees"][:len(with_paris["entrees"])]]
    v = client.get(f"/api/invite/{ta}/journal/integrity").json()
    assert v["verdict"] == "intact", v["message"]


# ═══ 3. Convention : « Accords enregistrés » à l'heure de Paris, texte scellé intact ═════

def _sig(company, signed_at, invite_id=1, link_id=None, status="signed"):
    return SimpleNamespace(company_name=company, invite_id=invite_id, cotraitant_link_id=link_id,
                           status=status, signataire_nom="Jean Le Gall", signataire_qualite="Gérant",
                           identity_level="lien_seul", signed_at=signed_at)


def test_accords_md_heures_de_paris():
    from app.services import groupement_convention as gc
    conv = SimpleNamespace(content_hash="e" * 64, version=2, frozen_at=datetime(2026, 10, 11, 20, 28))
    sigs = [_sig("Le Gall Électricité", datetime(2026, 1, 15, 20, 28)),
            _sig("Kerjean Menuiserie", datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc),
                 invite_id=None, link_id=4, status="hors_ligne")]
    md = gc.accords_md(conv, sigs)
    assert "figée le 11/10/2026 à 22:28 (heure de Paris)." in md
    assert "le 15/01/2026 à 21:28 (heure de Paris)" in md
    assert "le 25/10/2026 à 02:30 (heure de Paris)" in md
    assert "(UTC)" not in md
    # La ligne d'empreinte ne bouge pas.
    assert f"Empreinte du texte approuvé (SHA-256) : {'e' * 64}" in md


def test_texte_de_la_convention_independant_de_l_heure_affichee(monkeypatch):
    """render() (texte approuvé, content_hash) ne dépend d'aucune heure affichée : identique avec
    la base des fuseaux ou en repli UTC."""
    from app.services import format as fmt
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
    t1 = gc.render(json.loads(json.dumps(ctx)))
    monkeypatch.setattr(fmt, "_tz_paris", lambda: None)
    t2 = gc.render(json.loads(json.dumps(ctx)))
    assert t1 == t2 and gc.sha256(t1) == gc.sha256(t2)
    assert "heure de Paris" not in t1 and "(UTC)" not in t1


def test_pdf_convention_accords_heure_de_paris_empreinte_intacte(client, auth, mails):
    from app.services import groupement_convention as gc
    h = auth["headers"]
    pid, invs = _groupement(client, auth, n=1)
    c = _gen(client, h, pid).json()
    assert _valider(client, f"/api/invite/{invs[0]['token']}/convention/valider", c).status_code == 200
    db = _db()
    try:
        conv = gc.get_convention(db, pid)
        assert conv.content_hash == c["content_hash"] == gc.sha256(conv.content_md)
        assert "heure de Paris" not in conv.content_md
        frozen = conv.frozen_at
        signed = [s.signed_at for s in gc.signatures_of(db, conv) if s.signed_at]
    finally:
        db.close()
    assert signed

    def paris(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M")

    for url, headers in ((f"/api/projects/{pid}/groupement/convention/pdf", h),
                         (f"/api/invite/{invs[0]['token']}/convention/pdf", {})):
        r = client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        flat = _flat(r.content)
        assert "Accords enregistrés" in flat and "(UTC)" not in flat
        assert f"figée le {paris(frozen)} (heure de Paris)" in flat
        assert all(f"le {paris(s)} (heure de Paris)" in flat for s in signed)
    # L'accord enregistré reste lié à la même empreinte (rien de haché n'a bougé).
    g = client.get(f"/api/projects/{pid}/groupement/convention", headers=h).json()
    assert g["content_hash"] == c["content_hash"]
