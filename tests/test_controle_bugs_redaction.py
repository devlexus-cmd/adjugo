"""Contrôle des bugs d'octobre 2026, groupe « redaction » (atelier du dossier de présentation, « Qui écrit quoi »,
carnet de notes) : chaque test dit ce que le logiciel DOIT faire d'après ses contrats (docs/REDACTION_V4_GROUPEMENT.md
§ 4 et § 16, docs/REDACTION_V5.md § C2.8, docs/REORGANISATION_V2A.md § A3.5, décision 10) et ses textes affichés ;
tous échouaient sur cfe04e1, chacun sur son défaut.

15. Sur téléphone, « Qui écrit quoi » et l'onglet « Rédaction » ne promettent plus d'écrire la part d'un partenaire
    (« lire et répartir ; écrire depuis un ordinateur ») : pas de bouton « Rédiger à sa place » sans texte à lire,
    phrases « Depuis un ordinateur, … », lien « Voir dans « Qui écrit quoi » ».
16. « Demander les parts » : un partenaire qui ne peut plus rédiger (lien expiré…) est dit dans la réponse avec sa
    raison ; l'écran ne l'annonce plus comme destinataire et ne dit plus « chaque partenaire a envoyé ses parties ».
17. Carnet de notes d'un marché à plusieurs lots : « Note d'ensemble, partie (lot 2) — … » (serveur et écran du chef
    de file), jamais un « lot » nu.
18. Dossier « sans IA » : l'email de « Demander les parts » ne promet plus l'aide d'Adjugo.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_ecrans import HTML, JS, _node, _sans_commentaires_html
from tests.test_redaction_v4_chef_de_file import _email_a, _ligne
from tests.test_redaction_v4_groupement import P, _groupement, _part_a, _section_par
from tests.test_redaction_v6_ensemble import _cle, ia_interdite, mails  # noqa: F401
from tests.test_redaction_v6_lots import RC, _creer_lots, _projet, _tout_ecrire
from tests.zones import zone

REP = _sans_commentaires_html(zone(HTML, "atelier-onglets") + "\n" + zone(HTML, "atelier-repartition"))
ATELIER = _sans_commentaires_html(zone(HTML, "vue-atelier"))
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static")
CARNET_JS = open(os.path.join(STATIC, "carnet-notes.js"), encoding="utf-8").read()


def _expirer(invite_id):
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, invite_id).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()


def _balise(html, texte, nom="button"):
    """La balise ouvrante <nom …> de l'élément qui contient `texte`."""
    i = html.index(texte)
    return html[html.rindex("<" + nom, 0, i):html.index(">", html.rindex("<" + nom, 0, i)) + 1]


# ═══ 15. Sur téléphone : lire et répartir, écrire depuis un ordinateur ════════════════════════════════

def test_telephone_qui_ecrit_quoi_ne_promet_pas_d_ecrire_la_part_d_un_partenaire():
    # Le bouton qui ouvre la part d'un partenaire : sur téléphone, sans texte à lire, il n'est pas proposé
    # (le volet n'aurait rien à lire ni rien à écrire) ; ouvert depuis l'onglet « Rédaction », il reste « Replier ».
    bouton = _balise(REP, "'Rédiger à sa place'")
    assert 'v-if="l.texte_commun || !atlMobile || atl.rep.open===l.section_id"' in bouton, bouton
    # La phrase sous le bouton : sur téléphone, « Depuis un ordinateur ».
    assert ('<template v-if="atlMobile">Partenaire absent ? Depuis un ordinateur, vous pouvez écrire sa partie : il la '
            'validera.</template><template v-else>Partenaire absent ? Vous pouvez écrire sa partie : il la validera.'
            '</template>') in REP
    # Le volet d'une part sans texte : l'écriture se fait depuis un ordinateur.
    assert ("{{ l.redacteur.nom }} n'a rien envoyé. {{ atlMobile ? 'Depuis un ordinateur, vous' : 'Vous' }} pouvez "
            "rédiger sa partie : elle sera marquée « Rédigé par le chef de file, à valider par {{ l.redacteur.nom }} ».") in REP
    assert "n'a rien envoyé. Vous pouvez rédiger sa partie" not in REP
    # Onglet « Rédaction » : le lien vers « Qui écrit quoi » ne promet pas de modifier depuis un téléphone.
    lien = ATELIER[ATELIER.index('@click="atlRepVoir(atlSec().id)"'):]
    lien = lien[:lien.index("</button>")]
    assert "{{ atlMobile ? \"Voir dans « Qui écrit quoi »\" : \"Le modifier ou l'écrire à sa place\" }}" in lien, lien
    # L'éditeur et « Rédiger sa partie » restent réservés à l'ordinateur (inchangé).
    assert "atl.rep.edit.sid===l.section_id && !atlMobile" in REP and '<div v-else-if="!atlMobile"' in REP
    # Décision 16 : les nouveaux libellés ont leur néerlandais et leur espagnol.
    i18n = open(os.path.join(STATIC, "i18n.js"), encoding="utf-8").read()
    d = json.loads(i18n.split("\n", 1)[1][len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))
    for fr in ("Partenaire absent ? Depuis un ordinateur, vous pouvez écrire sa partie : il la validera.",
               "Voir dans « Qui écrit quoi »", "Aucune partie à demander pour l'instant."):
        assert d["nl"].get(fr) and d["es"].get(fr), fr


# ═══ 16. « Demander les parts » : le partenaire qui ne peut plus rédiger est dit ═════════════════════

def test_demander_les_parts_partenaire_qui_ne_peut_plus_rediger_est_dit(client, auth, monkeypatch):
    h = auth["headers"]
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    pid, st, a, b, vue = _groupement(client, auth)
    _email_a(a["id"], "desamiantage@partenaire.fr")
    _email_a(b["id"], "electricite@partenaire.fr")
    met = _section_par(vue, "méthodologie")
    assert client.put(f"/api/atelier/{pid}/repartition/{met['section_id']}", headers=h,
                      json={"redacteur": "partenaire", "invite_id": b["id"]}).status_code == 200
    assert _part_a(vue)["redacteur"]["invite_id"] == a["id"]
    _expirer(a["id"])                                       # le lien de Breizh Désamiantage expire
    rep = client.get(f"/api/atelier/{pid}/repartition", headers=h).json()
    assert [(m["nom"], m["peut_rediger"], m["raison"]) for m in rep["membres"] if m["invite_id"] == a["id"]] == \
        [("Breizh Désamiantage", False, "son lien a expiré")]
    assert _ligne(client, h, pid, "environnement")["statut"] == "a_rediger"

    r = client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={})
    assert r.status_code == 200, r.text
    d = r.json()
    # Le partenaire disponible est demandé comme avant ; l'autre est dit, avec sa raison (jamais une adresse).
    assert [(x["nom"], x["email_parti"]) for x in d["demandees"]] == [("Le Gall Électricité", True)]
    assert d["indisponibles"] == [{"invite_id": a["id"], "nom": "Breizh Désamiantage", "raison": "son lien a expiré"}]
    assert [x[0] for x in sent] == ["electricite@partenaire.fr"] and "desamiantage" not in json.dumps(d)

    # L'écran : la confirmation n'annonce que ceux qui recevront l'email ; le résultat dit le partenaire non sollicité.
    out = _node("const d = " + json.dumps(rep) + ";\nconst res = " + json.dumps(d) + ";\n"
                "console.log(JSON.stringify({dem: atlRepADemander(d), txt: atlRepDemandeTexte(res),"
                " seul: atlRepADemander({membres: d.membres, sections: d.sections.filter(l => l.redacteur.invite_id === "
                + str(a["id"]) + ")}),"
                " res_seul: atlRepDemandeTexte({demandees: [], sans_adresse: [], deja_demandees: [], plafond_atteint: [],"
                " indisponibles: res.indisponibles})}));")
    assert out["dem"] == [{"invite_id": b["id"], "nom": "Le Gall Électricité", "parties": 1}]
    assert out["txt"] == ["Demande envoyée à Le Gall Électricité.",
                          "Aucune demande à Breizh Désamiantage : son lien a expiré."]
    assert out["seul"] == []
    assert out["res_seul"] == ["Aucune demande à Breizh Désamiantage : son lien a expiré."]
    # Rien à demander parce que la seule part en attente est chez un partenaire qui ne peut plus rédiger : l'écran ne
    # dit pas « chaque partenaire a envoyé ses parties » (la raison du partenaire s'affiche dessous).
    assert ('<div v-if="!atlRepEnvoyerA().length" class="muted small atl-mt4"><template v-if="atlRepEnAttente()">'
            "Aucune partie à demander pour l'instant.</template><template v-else>Aucune partie à demander : chaque "
            "partenaire a envoyé ses parties, ou aucune ne lui est confiée.</template></div>") in REP
    att = _node("const d = " + json.dumps(rep) + ";\n"
                "console.log(JSON.stringify([atlRepADemander(d, true).map(x => x.nom),"
                " atlRepADemander({membres: d.membres, sections: d.sections.filter(l => l.redacteur.invite_id === "
                + str(a["id"]) + ")}, true).map(x => x.nom)]));")
    assert att == [["Breizh Désamiantage", "Le Gall Électricité"], ["Breizh Désamiantage"]]
    assert "atlRepEnAttente() { return atlRepADemander(this.atl.rep.d, true).length > 0; }," in JS


# ═══ 17. Carnet de notes, plusieurs lots : « partie (lot 2) » ════════════════════════════════════════

def test_carnet_lots_note_d_ensemble_dit_partie_lot(client, auth, mails, ia_interdite):
    h = auth["headers"]
    _company(client, h)
    pid = _projet(client, h, rc=RC)
    st = _creer_lots(client, h, pid, lots=("2", "3"))
    _tout_ecrire(client, h, pid, st)
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    e = client.get(f"/api/carnet/{pid}", headers=h).json()
    m2 = _cle(e, "2", "Méthodologie d'exécution")
    lignes = []
    for l in e["criteres"]["lignes"]:
        ln = dict(cle=l["cle"], critere=l["critere"], parent=l["parent"], poids=l["poids"], note="",
                  note_max=l["note_max"], famille=l["famille"], origine="saisie", lot=l.get("lot") or "")
        if l["cle"] == m2:
            ln.update(note="20", note_max="30")
        lignes.append(ln)
    r = client.put(f"/api/carnet/{pid}/notes", headers=h, json={"lignes": lignes, "rev": e["rev"]})
    assert r.status_code == 200, r.text
    n = r.json()["notes"]
    lib = next(x["lot_libelle"] for x in n["lignes"] if x.get("lot") == "2")
    assert lib.startswith("Lot 2 — ")                         # la donnée garde le mot du règlement
    assert n["messages_total"] and n["messages_total"][0].startswith(
        "Note d'ensemble, partie (lot 2) — " + lib[len("Lot 2 — "):] + " : 0 critère noté sur 2."), n["messages_total"]
    assert not any(re.search(r"(?<![\w(])lot\s+\d", m) for m in n["messages_total"])


def test_carnet_partie_lot_meme_regle_que_l_ecran():
    from app.services import carnet_notes as cn
    cas = ["2", "Lot 2 — Couverture", "lot n° 03 : Étanchéité", "Lot 3", "Démolition", "Lot unique", "", "LOT 12 - Gros œuvre"]
    js = re.search(r"\n  function partieLot\(x, intitule, minuscule\) \{.*?\n  \}\n", CARNET_JS, re.S).group(0)
    attendu = _node(js + "\nconsole.log(JSON.stringify(" + json.dumps(cas) + ".map(x => partieLot(x, true))));")
    assert [cn._partie_lot(x) for x in cas] == attendu
    # L'écran du chef de file : la note d'ensemble de chaque lot passe par partieLot, comme celle du partenaire.
    rendu = CARNET_JS[CARNET_JS.index("function renderNotes(d) {"):CARNET_JS.index("function", CARNET_JS.index(
        "function renderNotes(d) {") + 30)]
    assert ">Note d\\'ensemble, ' + cnEsc(partieLot(t.lot_libelle || \"\", true))" in rendu
    assert "lot_libelle || \"\").charAt(0).toLowerCase()" not in CARNET_JS


# ═══ 18. Dossier « sans IA » : l'email ne promet pas l'aide d'Adjugo ══════════════════════════════════

def test_demander_les_parts_d_un_dossier_sans_ia_ne_promet_pas_l_aide_d_adjugo(client, auth, monkeypatch, fake_llm):
    fake = fake_llm(lambda kw: ("Texte.", "end_turn"))
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj, text)) or True)
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _email_a(a["id"], "desamiantage@partenaire.fr")
    # Témoin : un dossier avec IA garde la phrase d'aujourd'hui.
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).status_code == 200
    assert len(sent) == 1 and "Écrivez-la vous-même ou avec l'aide d'Adjugo, depuis votre lien :" in sent[0][2]
    from app.models import DossierRepartition
    db = _db()
    try:
        for x in db.query(DossierRepartition).all():
            x.demandee_le = None                                # hors anti-rafale, pour la seconde demande
        db.commit()
    finally:
        db.close()
    assert client.put(f"/api/atelier/{pid}/options", headers=h, json={"sans_ia": True}).status_code == 200
    pa = P(client, a["token"])
    sid = _part_a(pa.get().json()["parties"])["section_id"]
    assert pa.post(f"/sections/{sid}/aide", {"action": "rediger"}).status_code == 409   # l'aide lui est refusée
    assert client.post(f"/api/atelier/{pid}/repartition/demander", headers=h, json={}).status_code == 200
    assert len(sent) == 2
    texte = sent[1][2]
    assert "l'aide d'Adjugo" not in texte and "avec l'aide" not in texte
    assert ("Écrivez-la vous-même, depuis votre lien (le chef de file a choisi de rédiger ce dossier sans IA) :\n"
            in texte) and f"/invite/{a['token']}" in texte
    assert fake.calls == []
