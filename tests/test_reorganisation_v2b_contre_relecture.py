"""
Réorganisation de l'interface — vague 2b, CONTRE-RELECTURE (contrat : docs/REORGANISATION_V2B.md, section T).

Les remarques de la contre-relecture, chacune reproduite par un test qui échouait sur 47a0983 :

  T1  (remarques 1 et 3) S5 n'était corrigé qu'en partie : la relance planifiée des parties du dossier de présentation
      (relancer_parts, appelée par run_cotraitance_reminders) écrivait encore, avec le lien de l'invitation, au
      partenaire d'un chef de file dont l'adresse n'est pas confirmée — tout par l'API, sans dossier de l'acheteur ni
      part du partenaire ;
  T2  (remarques 2 et 3) « Votre partie est à valider » (_notifier_partenaire), avec le lien, partait aussitôt quand ce
      même compte écrivait la partie du partenaire ; le commentaire d'auth.py le dit maintenant ;
  T3  (remarque 4) S6 : une relecture des pièces à renouveler qui échoue après une première lecture vidait la liste et
      laissait l'accueil et la cloche dire « Rien n'attend de réponse de votre part. ».

Aucun appel réseau réel (courriels capturés) ; les méthodes de app.js sous Node.
"""
import pathlib
import re
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tests.test_reorganisation_v2b_espace_partenaire import _fonction, _methode, _node
from tests.test_reorganisation_v2b_relecture import _compte

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _confirmer(h, verifie=True):
    """Pose l'état de l'adresse du compte de ces en-têtes (comme le lien de confirmation)."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.core.security import decode_token
    uid = int(decode_token(h["Authorization"].split(" ", 1)[1])["sub"])
    db = SessionLocal()
    try:
        db.get(User, uid).email_verified = verifie
        db.commit()
    finally:
        db.close()


def _partie_confiee(client, h):
    """Le parcours le plus court, tout par l'API : marché sans dossier de l'acheteur ni date limite, plan libre, une
    partie, un partenaire invité par adresse (il n'a jamais ouvert le lien), la partie lui est confiée avec une date
    limite interne à J+2."""
    r = client.post("/api/projects/", headers=h, json={"name": "Marché contre-relecture", "client": "Ville Z"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post(f"/api/atelier/{pid}", headers=h, json={"base": "libre"})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/atelier/{pid}/sections", headers=h, json={"intitule": "Gestion des déchets"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    cible = f"tiers_{uuid.uuid4().hex[:6]}@exemple.org"
    r = client.post(f"/api/projects/{pid}/invites", headers=h, json={"company_name": "Tiers SARL", "recipient": cible})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    r = client.post(f"/api/atelier/{pid}/repartition", headers=h, json={})
    assert r.status_code == 200, r.text
    assert sid in [x["section_id"] for x in r.json()["sections"]]
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}", headers=h,
                   json={"redacteur": "partenaire", "invite_id": iid,
                         "date_limite": (date.today() + timedelta(days=2)).isoformat()})
    assert r.status_code == 200, r.text
    return pid, sid, iid, cible


def _capturer_envois(monkeypatch):
    import app.services.alerts as alerts
    from app.services import email as _email
    envoyes = []
    rec = lambda to, subj, text, html=None, **k: envoyes.append((to, subj, text)) or True   # noqa: E731
    monkeypatch.setattr(alerts, "send_email", rec)
    monkeypatch.setattr(_email, "send_email", rec)
    return envoyes


def _relances(db_fn):
    import app.services.alerts as alerts
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return db_fn(alerts, db)
    finally:
        db.close()


# ═══ T1. La relance planifiée des parties ne part que d'un compte confirmé ═════════════════════════════════════════

@pytest.mark.parametrize("verifie", [False, True])
def test_t1_la_relance_des_parties_ne_part_que_d_un_compte_confirme(client, monkeypatch, verifie):
    h = _compte(client, verifie)
    _pid, _sid, _iid, cible = _partie_confiee(client, h)
    envoyes = _capturer_envois(monkeypatch)
    res = _relances(lambda alerts, db: alerts.run_cotraitance_reminders(db))
    au_tiers = [x for x in envoyes if x[0] == cible]
    if verifie:   # le témoin : la relance part, avec le lien (comportement de la production, inchangé)
        assert res["parts_relancees"] == 1
        assert len(au_tiers) == 1 and au_tiers[0][1].startswith("Rappel — votre partie du dossier de présentation")
        assert "/invite/" in au_tiers[0][2]
        return
    # Compte non confirmé : rien vers le tiers, ni par la tournée planifiée ni par un appel direct de la relance.
    assert au_tiers == [] and res["parts_relancees"] == 0
    from app.services import atelier_groupement as ag
    assert _relances(lambda alerts, db: ag.relancer_parts(db, date.today()))["parts_relancees"] == 0
    assert [x for x in envoyes if x[0] == cible] == []
    # « Demander les parts », le geste manuel, est refusé à ce même compte (inchangé).
    assert client.post(f"/api/atelier/{_pid}/repartition/demander", headers=h, json={}).status_code == 403
    # L'adresse confirmée, le palier encore dû part à la tournée suivante (rien n'a été marqué envoyé).
    _confirmer(h)
    res = _relances(lambda alerts, db: alerts.run_cotraitance_reminders(db))
    assert res["parts_relancees"] == 1 and len([x for x in envoyes if x[0] == cible]) == 1


# ═══ T2. « Votre partie est à valider » ne part que d'un compte confirmé ═══════════════════════════════════════════

@pytest.mark.parametrize("verifie", [False, True])
def test_t2_ecrire_la_partie_du_partenaire_ne_lui_envoie_le_lien_que_d_un_compte_confirme(client, monkeypatch,
                                                                                          verifie):
    import app.routers.invites as invmod
    h = _compte(client, verifie)
    pid, sid, _iid, cible = _partie_confiee(client, h)
    envoyes = []
    monkeypatch.setattr(invmod, "_send_mails_async", lambda mails: envoyes.extend(mails))
    r = client.put(f"/api/atelier/{pid}/repartition/{sid}/texte", headers=h,
                   json={"texte": "Les déchets du chantier sont triés et évacués chaque semaine.",
                         "base_version_id": None})
    assert r.status_code == 200, r.text                       # le texte est enregistré dans les deux cas
    au_tiers = [x for x in envoyes if x[0] == cible]
    if verifie:
        assert len(au_tiers) == 1 and au_tiers[0][1].startswith("Votre partie est à valider")
        assert "/invite/" in au_tiers[0][2]
    else:
        assert au_tiers == []


def test_t2_le_compte_qui_agit_et_le_chef_de_file_doivent_avoir_confirme(client, monkeypatch):
    """Les deux appels (« écrire à la place » et l'harmonisation du ton, atelier_assemblage) passent le compte qui agit ;
    le propriétaire de l'invitation compte aussi : un collègue confirmé n'écrit pas pour un chef de file non confirmé."""
    import app.routers.invites as invmod
    from app.core.database import SessionLocal
    from app.models import Project, ProjectInvite
    from app.services import atelier_groupement as ag
    h = _compte(client, True)
    pid, _sid, iid, cible = _partie_confiee(client, h)
    envoyes = []
    monkeypatch.setattr(invmod, "_send_mails_async", lambda mails: envoyes.extend(mails))
    monkeypatch.setattr(invmod, "_notify_allowed", lambda key: True)          # l'anti-rafale n'est pas testé ici
    db = SessionLocal()
    try:
        p, inv = db.get(Project, pid), db.get(ProjectInvite, iid)
        ag._notifier_partenaire(db, p, inv, "Gestion des déchets", True, user=SimpleNamespace(email_verified=False))
        assert envoyes == []
        ag._notifier_partenaire(db, p, inv, "Gestion des déchets", True, user=SimpleNamespace(email_verified=True))
        ag._notifier_partenaire(db, p, inv, "Gestion des déchets", True)
        assert [x[0] for x in envoyes] == [cible, cible]
    finally:
        db.close()
    _confirmer(h, False)
    db = SessionLocal()
    try:
        p, inv = db.get(Project, pid), db.get(ProjectInvite, iid)
        ag._notifier_partenaire(db, p, inv, "Gestion des déchets", True, user=SimpleNamespace(email_verified=True))
        assert len(envoyes) == 2
    finally:
        db.close()
    assert "ag._notifier_partenaire(db, project, db.get(ProjectInvite, s.author_invite_id), titre, True, user=user)" in (
        ROOT / "app" / "services" / "atelier_assemblage.py").read_text(encoding="utf-8")


def test_t2_le_commentaire_d_auth_py_dit_ce_qui_part():
    src = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    i = src.index("    # Email de confirmation. Choix du 24/06, gardé")
    c = re.sub(r"\s*\n\s*#\s*", " ", src[i:src.index("    _send_verification(user)", i)])
    for phrase in ("ni le rappel planifié de la part ni l'alerte d'attestations à ses partenaires",
                   "ni la relance planifiée des parties du dossier de présentation ni « Votre partie est à valider » "
                   "quand il écrit la partie d'un partenaire",
                   "relancer_parts et _notifier_partenaire",
                   "le code qui vérifie l'adresse du partenaire (sans le lien ; 8 par jour au plus pour une "
                   "organisation non confirmée"):
        assert phrase in c, phrase
    from app.routers.invites import OTP_DAILY_CAP_UNVERIFIED
    assert OTP_DAILY_CAP_UNVERIFIED == 8
    a = (ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8")
    assert "relancer_parts(db, today, deja=parts_merged, non_confirmes=non_confirmes)" in a


# ═══ T3. Une relecture qui échoue garde la liste déjà lue ═══════════════════════════════════════════════════════════

def test_t3_une_relecture_en_echec_ne_fait_pas_dire_rien_n_attend_sous_node():
    jours = re.search(r"\nconst A_FAIRE_JOURS = \d+;", JS).group(0)
    script = (jours + "\n" + _fonction(JS, "listeAFaire") + "\nconst o = {\n" + _methode("loadExpiring") + "\n"
              + _methode("aFaire") + "\n" + _methode("aFaireLu") + r"""
};
Object.assign(o, { expiring: [], expiringLu: false, shared: [], projects: [], grpDash: {},
                   reseau: { recues: { loaded: true, list: [] } } });
const urssaf = { id: 1, name: "Attestation URSSAF", expiration_date: "2099-01-01", days_until_expiration: 4 };
let n = 0;
o.api = async () => { n++; if (n === 1) return [urssaf]; throw new Error("réseau"); };
const etat = () => ({ n: o.aFaire().length, lu: o.aFaireLu(), rien: !o.aFaire().length && o.aFaireLu() });
(async () => {
  const res = [];
  await o.loadExpiring(); res.push(etat());          // à l'ouverture : lue
  await o.loadExpiring(); res.push(etat());          // retour sur l'accueil : le réseau manque
  o.api = async () => []; await o.loadExpiring(); res.push(etat());   // relue : plus rien à renouveler
  console.log(JSON.stringify(res));
})();
""")
    r = _node(script)
    assert r[0] == {"n": 1, "lu": True, "rien": False}
    assert r[1] == {"n": 1, "lu": True, "rien": False}           # la pièce reste affichée, jamais « Rien n'attend »
    assert r[2] == {"n": 0, "lu": True, "rien": True}            # une vraie liste vide, lue : la phrase est vraie


# ═══ Le contrat ══════════════════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_section_t_de_la_contre_relecture():
    doc = (ROOT / "docs" / "REORGANISATION_V2B.md").read_text(encoding="utf-8")
    assert doc.index("## S. Relecture") < doc.index("## T. Contre-relecture de la vague 2b")
    t = doc[doc.index("## T. Contre-relecture de la vague 2b"):]
    for n in range(1, 6):
        assert f"### T.{n} " in t, n
    for x in ("test_reorganisation_v2b_contre_relecture.py", "relancer_parts", "_notifier_partenaire", "loadExpiring",
              "Postgres", "Navigateur réel", "47a0983"):
        assert x in t, x
    assert "RESULTATS_A_REPORTER" not in doc
    s5 = doc[doc.index("### S.5 "):doc.index("### S.6 ")]
    assert "§ T.1 et T.2" in s5
