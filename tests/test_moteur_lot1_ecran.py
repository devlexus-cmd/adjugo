"""Moteur de recherche, lot 1 « Dire juste », PARTIE ÉCRAN (docs/MOTEUR_LOT1.md, section « Écran » ; note de décisions
du 21/10/2026, points 10 à 13). Chaque test échoue sur 0f8eb32 (partie serveur du lot, vague 2b, tests PostgreSQL).

  10. Cartes de « Publiés » : plus de « confiance N % » ni d'« adéquation N/100 » (décision 8 : des pourcentages
      seulement après le dossier) ; pas encore les mots « Bon potentiel / À étudier / Peu adapté » (ils attendent le
      barème corrigé de la V1) ; le nom de l'organisme Mégalis sans « (code postal - ville) » ; les rectificatifs
      visibles : « Date limite repoussée au … (rectificatif du …) », avec le lien du rectificatif QUI FIXE la date,
      « Date limite non précisée » quand sa nouvelle date n'a pas pu être lue (jamais l'ancienne date).
  11. « Voir les marchés pour mon entreprise » lit le métier dans « Ce que je cherche » ; sans métier, l'écran le
      demande, avec le chemin, au lieu de chercher « travaux » sans le dire.
  12. Onglet « À venir » : « Fin du contrat estimée le … (durée publiée) » au lieu de « Renouvellement ~ » ; une bulle
      juste (« données publiées des marchés attribués ») et neutre (« préparez votre réponse et vos partenaires avant
      la republication ») ; le crédit du repli payant annoncé AVANT le clic, vrai dans le code (1 analyse, remboursée
      si rien n'est trouvé, toujours remboursée en outre-mer et en Corse, une analyse disponible exigée), et dit après.
  13. La page d'exemple de la démo ne dit plus que les délibérations sont « récupérées automatiquement par Adjugo ».

Sans réseau : jeux d'essai réels du dépôt (tests/fixtures), IA simulée, fonctions de app.js sous Node.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.textes_visibles import mots_bannis
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
FIX = ROOT / "tests" / "fixtures"

CARTE = zone(HTML, "trouver-carte")
RADAR = zone(HTML, "trouver-radar")
TROUVER = zone(HTML, "vue-sourcing")

BULLE_A_VENIR = ("Marchés déjà attribués dont le contrat arrive à terme : préparez votre réponse et vos partenaires "
                 "avant la republication. La fin du contrat est estimée d'après les données publiées des marchés "
                 "attribués : la date de notification et la durée publiée. Classés selon votre métier, votre zone et la "
                 "date de fin estimée.")
CREDIT = ("Une recherche complémentaire peut consommer 1 analyse : remboursée si elle ne trouve rien, toujours "
          "remboursée en outre-mer et en Corse.")
BULLE_CREDIT = ("La recherche dans les données publiées des marchés attribués ne consomme aucune analyse. Si elle ne "
                "donne rien, ou si ces données ne répondent pas, Adjugo cherche aussi dans les avis d'attribution du "
                "BOAMP, lus par l'IA : cette recherche complémentaire consomme 1 analyse, remboursée si elle ne trouve "
                "aucune fin de contrat, et toujours remboursée dès qu'un des départements demandés est en outre-mer ou "
                "en Corse. Il faut une analyse disponible pour la lancer. Ses durées de contrat sont lues dans "
                "l'intitulé de l'avis ou estimées selon le type de contrat.")
APRES_DEBIT = "Recherche complémentaire dans les avis d'attribution du BOAMP : 1 analyse consommée."
APRES_REMB = "Recherche complémentaire dans les avis d'attribution du BOAMP : analyse remboursée."
BULLE_NON_LUE = ("Un rectificatif de cet avis porte sur sa date limite, mais Adjugo n'a pas pu lire la nouvelle date "
                 "avec certitude : lisez-la sur le rectificatif. L'ancienne date n'est pas montrée : elle peut ne plus "
                 "être la bonne.")
SOUS_TITRE = ("D'après votre premier métier, dans « Ce que je cherche », et le département de votre code postal.")
MANQUE_METIER = ("Dites d'abord votre métier : la recherche part de la première spécialité de « Ce que je cherche ».")
FIT = "Dites ce que vous cherchez pour un classement adapté"
FIT_TITRE = "Renseignez vos spécialités et votre zone pour un classement adapté à votre entreprise"
# Les libellés nouveaux de l'écran, chacun un nœud de texte entier (translateDOM ne traduit qu'un nœud entier).
LIBELLES = [BULLE_A_VENIR, CREDIT, BULLE_CREDIT, APRES_DEBIT, APRES_REMB, BULLE_NON_LUE, SOUS_TITRE, MANQUE_METIER,
            "Fin du contrat estimée le", "(durée publiée)", "(durée lue dans l'intitulé de l'avis)",
            "(durée estimée selon le type de contrat)", "attribution publiée le", "notifié le",
            "Voir la fiche acheteur", "Voir l'avis d'attribution",
            FIT, FIT_TITRE,
            "Date limite non précisée", "Avis rectifié", "Date limite repoussée au", "Date limite avancée au",
            "rectificatif du", "voir le rectificatif", "Dire mon métier"]


def _plat(s: str) -> str:
    return " ".join(s.split())


def _sans_commentaires(s: str) -> str:
    """Ce que le gabarit affiche ou calcule : les commentaires HTML (qui citent l'ancien comportement) retirés."""
    return re.sub(r"<!--.*?-->", " ", s, flags=re.S)


def _dico():
    tete, corps = (STATIC / "i18n.js").read_text(encoding="utf-8").split("\n", 1)
    return json.loads(corps[len("window.ADJUGO_I18N = "):].rstrip().rstrip(";"))


def _fonction(nom):
    from tests.test_reorganisation_v2b_espace_partenaire import _fonction as f
    return f(JS, nom)


def _methode(nom):
    from tests.test_reorganisation_v2b_espace_partenaire import _methode as m
    return m(nom)


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ═══ 10. Les cartes de « Publiés » ═════════════════════════════════════════════════════════════════════════════════

def test_e10_carte_sans_nombre_avant_le_dossier_ni_mot_de_verdict():
    """Décision 8 : aucun nombre sur la carte avant le dossier. Sur 0f8eb32 : « confiance {{ … }}% » (constante 70 % pour
    Mégalis) et « adéquation {{ t.score.total }}/100 »."""
    texte = _plat(_sans_commentaires(CARTE))
    for interdit in ("confiance", "adéquation", "/100", "t.confidence", "confClass", "t.score.total", "score adapté"):
        assert interdit not in texte, interdit
    # Les mots de verdict n'arrivent pas encore : une donnée inconnue avantage le marché (scoring.py), une carte « Bon
    # potentiel » pourrait devenir « Peu adapté » une fois le dossier lu.
    for mot in ("Bon potentiel", "À étudier", "Peu adapté", "decLabel"):
        assert mot not in texte, mot
    # Sans métier ni zone, l'invitation reste, en bouton (accessible au clavier), et parle du classement.
    m = re.search(r'<button v-if="t\.score && t\.score\.fit_assessable===false" type="button" class="pill a_etudier '
                  r'trouver-fit" @click="go\(\'criteria\'\)" title="([^"]+)">.*?<span>([^<]+)</span></button>', CARTE)
    assert m and m.group(1) == FIT_TITRE and m.group(2) == FIT, m
    assert "confClass(" not in JS and "rgba(234,179,8,.12);color:#92400e" not in CARTE
    # Les cartes restent rangées par la note avant le dossier, sans la montrer (« classement adapté » dit vrai).
    src = (ROOT / "app" / "sourcing" / "search.py").read_text(encoding="utf-8")
    assert "deduped.sort(key=lambda t: (t.score.total if t.score else 0), reverse=True)" in src


def test_e10_nom_de_l_organisme_megalis_nettoye_sans_rien_changer_d_autre():
    """Page réelle de Mégalis du 21/10/2026 : « COMMUNE DE SAINT SAUVEUR (29400 - SAINT-SAUVEUR) » devient « COMMUNE DE
    SAINT SAUVEUR » sur la carte (et dans Mes marchés, le courriel d'alerte). La clé de fusion et le lieu lisent toujours
    le texte de la page : la fusion avec le BOAMP, la note et la mémoire des alertes ne changent pas."""
    from app.sourcing.sources import atexo
    html = (FIX / "megalis_resultats_2026-10-21.html").read_text(encoding="utf-8")
    tenders, _ = atexo._parse_page(html, "Mégalis Bretagne", "https://marches.megalis.bretagne.bzh")
    par_cid = {t.provenance.official_ref: t for t in tenders}
    assert len(par_cid) == 10
    assert all("(" not in t.acheteur and not re.search(r"\d{5}", t.acheteur) for t in par_cid.values())
    assert par_cid["242387"].acheteur == "COMMUNE DE SAINT SAUVEUR"
    assert par_cid["242491"].acheteur == "SPL BRETAGNE PLAISANCE"          # le sigle est gardé, rien n'est deviné
    assert par_cid["241593"].acheteur == "RENNES METROPOLE"
    # Inchangés : le lieu (la note lit l'objet et le lieu) et la clé de fusion, calculés sur le texte de la page.
    assert par_cid["241593"].lieu == "RENNES METROPOLE (35000 - Rennes )"
    assert par_cid["241593"].dedup_key.split("|")[1] == "rennesmetropole35000"
    assert par_cid["242387"].dedup_key == "travauxderenforcement20272028delavoiriec|communedesaintsauveu|2026-12-07"
    # Forme coupée par la page (étude moteur, § 6.2 point 3), et ce qui n'est pas « (5 chiffres - ville) » : intact.
    assert atexo.nom_organisme("COMMUNE DE LOCTUDY (29750 - LO") == "COMMUNE DE LOCTUDY"
    assert atexo.nom_organisme("SIVU (Syndicat des eaux)") == "SIVU (Syndicat des eaux)"
    assert atexo.nom_organisme("(29750 - LOCTUDY)") == "(29750 - LOCTUDY)"     # rien d'autre : le texte tel quel
    assert atexo.nom_organisme("  Région  Bretagne ") == "Région Bretagne"


def _avis_rectifies(monkeypatch):
    """Les avis réels du jeu du 21/10/2026, passés par la vraie recherche BOAMP (API simulée), avec deux liens
    CONSTRUITS comme dans tests/test_moteur_lot1_sources.py : un rectificatif réel qui ne parle que des lots
    (26-102445, du 21/10) ajouté après celui qui repousse 26-90336 (26-96286, du 06/10) ; le rectificatif réel sans
    année (26-102412) rattaché à 26-94570, dont la date ne peut donc pas être lue."""
    from tests.test_moteur_lot1_sources import AVIS, SUITES, _api, _cherche, _figer, _par_ref
    _figer(monkeypatch)
    suites = [SUITES["26-96286"], dict(SUITES["26-102445"], annonce_lie=["26-90336"]), SUITES["26-102300"],
              dict(SUITES["26-102412"], annonce_lie=["26-94570"]), SUITES["26-102254"]]
    principaux = [AVIS[i] for i in ("26-90521", "26-94570", "26-91602", "26-101475", "26-95098")]
    _api(monkeypatch, principaux, suites=suites, initiaux=[AVIS["26-90336"]])
    return _par_ref(_cherche())


def test_e10_le_rectificatif_cite_est_celui_qui_fixe_la_date(monkeypatch):
    """« (rectificatif du …) » cite le rectificatif qui fixe la date, pas le dernier paru : 26-90336, repoussé au 06/11
    par 26-96286 (06/10), puis rectifié le 21/10 sur ses lots (26-102445). Sur 0f8eb32, la fiche ne portait que la date
    du dernier rectificatif (rectifie_le, 21/10) : l'écran aurait dit « rectificatif du 21/10/2026 », faux."""
    from app.sourcing.base import sanitize_tender_links
    from app.sourcing.search import _dedup_tenders
    t = _avis_rectifies(monkeypatch)
    a = t["26-90336"]
    assert a.date_limite == "2026-11-06" and a.date_limite_initiale == "2026-10-16" and a.rectifie_le == "2026-10-21"
    assert a.date_limite_rectificatif.official_ref == "26-96286" and a.date_limite_rectificatif_le == "2026-10-06"
    assert [p.official_ref for p in a.rectificatifs] == ["26-96286", "26-102445"]
    # Date non lue : le rectificatif qui la rend « non précisée » est cité ; jamais l'ancienne date à la place.
    b = t["26-94570"]
    assert b.date_limite is None and b.date_limite_rectifiee_non_lue is True
    assert b.date_limite_rectificatif.official_ref == "26-102412" and b.date_limite_rectificatif_le == "2026-10-21"
    # Un rectificatif européen (version complète de l'avis) qui ne change que les montants : il redit la même date,
    # l'avis garde la sienne (pas de date initiale à part) ; l'écran dira « Avis rectifié ».
    c = t["26-95098"]
    assert c.date_limite == "2026-11-03" and c.date_limite_initiale is None
    assert c.date_limite_rectificatif.official_ref == "26-101475" and [p.official_ref for p in c.rectificatifs] == ["26-101475"]
    # Un rectificatif qui ne parle pas de la date limite (lots) n'en fixe aucune.
    assert t["26-90521"].date_limite_rectificatif.official_ref == "26-102300"
    # Envoyé au navigateur ; la garde des liens le couvre ; un doublon d'une autre source le reçoit s'il ne l'a pas.
    carte = a.model_dump(exclude={"raw"})
    assert carte["date_limite_rectificatif"]["source_url"] == "https://www.boamp.fr/pages/avis/?q=idweb:26-96286"
    piege = a.model_copy(deep=True)
    piege.date_limite_rectificatif.source_url = "javascript:alert(1)"
    assert sanitize_tender_links(piege).date_limite_rectificatif.source_url == ""
    autre = a.model_copy(deep=True)
    autre.provenance = autre.provenance.model_copy(update={"source": "Autre", "official_ref": "x"})
    autre.date_limite_rectificatif, autre.date_limite_rectificatif_le, autre.rectificatifs = None, None, []
    fusion = _dedup_tenders([autre, a])
    assert fusion[0].date_limite_rectificatif.official_ref == "26-96286" and fusion[0].date_limite_rectificatif_le == "2026-10-06"


_SCRIPT_RECTIF = r"""
const o = {
__METHODES__
};
const out = {};
const cartes = JSON.parse(process.argv[1]);
for (const k in cartes) out[k] = o.srcRectif(cartes[k]);
console.log(JSON.stringify(out));
"""


def test_e10_ligne_du_rectificatif_sur_les_avis_reels_sous_node(monkeypatch):
    """La ligne que l'écran tire de la fiche (rectifDeCarte, srcRectif), sur les fiches réelles : « Date limite repoussée
    au 06/11/2026 (rectificatif du 06/10/2026) » avec le lien de 26-96286 ; « Date limite non précisée » sans aucune
    date de l'avis initial ; « Avis rectifié » quand la date ne change pas ; rien pour un avis sans rectificatif."""
    t = _avis_rectifies(monkeypatch)
    cartes = {k: v.model_dump(exclude={"raw"}) for k, v in t.items()}
    cartes["avance"] = dict(cartes["26-90521"], date_limite="2026-10-28", date_limite_initiale="2026-11-05")
    cartes["simple"] = {"objet": "x", "rectificatifs": [], "date_limite": "2026-11-30"}
    cartes["ancien_serveur"] = {k: v for k, v in cartes["26-90521"].items() if not k.startswith("date_limite_rectificatif")}
    script = (_fonction("rectifDeCarte") + "\n" + _SCRIPT_RECTIF.replace(
        "__METHODES__", "\n".join(_methode(m) for m in ("fmtDate", "srcRectif"))))
    r = _node(script, json.dumps(cartes))
    assert r["26-90336"] == {"etat": "repoussee", "date": "06/11/2026", "le": "06/10/2026",
                             "lien": "https://www.boamp.fr/pages/avis/?q=idweb:26-96286"}
    assert r["26-90521"] == {"etat": "repoussee", "date": "05/11/2026", "le": "21/10/2026",
                             "lien": "https://www.boamp.fr/pages/avis/?q=idweb:26-102300"}
    assert r["26-94570"] == {"etat": "non_lue", "date": "", "le": "21/10/2026",
                             "lien": "https://www.boamp.fr/pages/avis/?q=idweb:26-102412"}
    assert "29/10/2026" not in json.dumps(r["26-94570"])              # l'ancienne date, jamais présentée
    assert r["26-95098"]["etat"] == "rectifie" and r["26-95098"]["le"] == "21/10/2026"
    assert r["26-95098"]["lien"].endswith("26-101475")
    assert r["avance"]["etat"] == "avancee" and r["avance"]["date"] == "28/10/2026"
    assert r["simple"] is None
    assert r["ancien_serveur"]["etat"] == "repoussee" and r["ancien_serveur"]["le"] == "21/10/2026"
    # Le gabarit : un vrai lien (la balise <a :href>), la date que fixe le rectificatif, « non précisée » avec sa bulle,
    # et la date de l'avis retirée de la ligne grise quand le rectificatif la change.
    for x in ('<a :href="safeUrl(srcRectif(t).lien)" target="_blank" rel="noopener">',
              "{{ srcRectif(t).etat==='avancee' ? 'Date limite avancée au' : 'Date limite repoussée au' }}",
              "<b>{{ srcRectif(t).date }}</b>", "<b>Date limite non précisée</b>", "<span>Avis rectifié</span>",
              "{{ srcRectif(t).le ? 'rectificatif du' : 'voir le rectificatif' }}", BULLE_NON_LUE,
              """<template v-if="!srcRectif(t) || srcRectif(t).etat==='rectifie'"> · limite {{ t.date_limite ? fmtDate(t.date_limite) : 'non précisée' }}</template>"""):
        assert x in CARTE, x
    assert "date_limite_initiale" not in CARTE


# ═══ 11. « Voir les marchés pour mon entreprise » ══════════════════════════════════════════════════════════════════

_SCRIPT_MINE = r"""
global.document = { getElementById(id) { return { focus() { journal.push("focus#" + id); } }; } };
const journal = [];
const o = {
__METHODES__
};
async function cas(c) {
  journal.length = 0;
  Object.assign(o, { company: c.company, criteria: JSON.parse(JSON.stringify(c.criteria)),
    src: { query: c.query || "", dept: "", prefilled: false, searched: false, manqueMetier: false },
    $refs: { srcDireMetier: { focus() { journal.push("focus:Dire mon métier"); } } },
    $nextTick(f) { f(); }, notify(m) { journal.push("notify:" + m); }, go(v) { journal.push("go:" + v); },
    srcSearch() { journal.push("search:" + o.src.query + "|" + o.src.dept); },
    api: async (m, p) => { journal.push(m + " " + p); return c.serveur; } });
  await o.srcSearchMine();
  return { journal: journal.slice(), query: o.src.query, manque: o.src.manqueMetier, metier: o.srcMetier() };
}
(async () => {
  const out = {};
  const cass = JSON.parse(process.argv[1]);
  for (const k in cass) out[k] = await cas(cass[k]);
  journal.length = 0; o.srcDireMetier(); out.chemin = journal.slice();
  console.log(JSON.stringify(out));
})();
"""


def test_e11_voir_les_marches_lit_le_metier_de_ce_que_je_cherche_sous_node():
    """Sur 0f8eb32, le bouton lisait `specialites` dans la fiche Identité, qui n'a pas ce champ (app/schemas,
    CompanyOut) : la recherche partait sans mot (le BOAMP cherche alors « travaux ») dès que le code postal donnait
    un département. Désormais : la première spécialité de « Ce que je cherche » ; sans elle, rien n'est cherché, l'écran
    la demande et met le curseur sur « Dire mon métier »."""
    borne = JS[JS.index("const MONTANT_SEUL_MAX = "):JS.index("// Confirmation d'email vivante (décision 12 (a))")]
    script = borne + _SCRIPT_MINE.replace("__METHODES__", "\n".join(_methode(m) for m in (
        "srcPrefillFromProfile", "srcMetier", "srcSearchMine", "srcDireMetier")))
    cas = {
        "metier": {"company": {"postal_code": "29200"}, "criteria": {"specialites": "Voirie, Réseaux divers"}},
        "metier_tape_ailleurs": {"company": {"postal_code": "29200"}, "criteria": {"specialites": "Plomberie"},
                                 "query": "gros œuvre"},
        "sans_metier": {"company": {"postal_code": "29200", "specialites": "Ancien champ fictif"},
                        "criteria": {"specialites": ""}, "serveur": {"specialites": ""}},
        "enregistre_ailleurs": {"company": {"postal_code": "97400"}, "criteria": {"specialites": "", "departements": "x"},
                                "serveur": {"specialites": "Électricité ; Courants faibles"}},
        "serveur_en_panne": {"company": {"postal_code": "29200"}, "criteria": {}, "serveur": None},
    }
    r = _node(script, json.dumps(cas))
    assert r["metier"]["journal"] == ["search:Voirie|29"] and r["metier"]["manque"] is False
    # « pour mon entreprise » : le métier de l'entreprise, même si d'autres mots étaient tapés.
    assert r["metier_tape_ailleurs"]["journal"] == ["search:Plomberie|29"]
    # Sans métier : aucune recherche (ni « travaux », ni rien), la demande, le curseur sur le chemin direct.
    assert r["sans_metier"]["journal"] == ["GET /api/criteria/", "focus:Dire mon métier"], r["sans_metier"]
    assert r["sans_metier"]["manque"] is True and r["sans_metier"]["query"] == ""
    assert r["serveur_en_panne"]["journal"] == ["GET /api/criteria/", "focus:Dire mon métier"]
    # Un métier enregistré depuis (par un collègue) est relu, sans écraser le reste de « Ce que je cherche ».
    assert r["enregistre_ailleurs"]["journal"] == ["GET /api/criteria/", "search:Électricité|974"]
    assert r["chemin"] == ["go:criteria", "focus#crit-spec"]
    # Le gabarit : la demande ne s'affiche que tant qu'il manque le métier ; le sous-titre dit d'où viennent les mots.
    assert '<div v-if="src.manqueMetier && !srcMetier()" class="trouver-manque-metier small" role="status">' in TROUVER
    assert f"<span>{MANQUE_METIER}</span>" in TROUVER
    assert ('<button ref="srcDireMetier" type="button" class="btn sm" @click="srcDireMetier()"><i '
            'data-lucide="pencil"></i>Dire mon métier</button>') in TROUVER
    assert f'<div class="muted small" style="margin-top:6px">{SOUS_TITRE}</div>' in TROUVER
    assert "D'après vos spécialités et votre département." not in HTML
    assert '<input id="crit-spec" v-model="criteria.specialites"' in HTML        # le champ où mène le chemin
    # La fiche Identité n'a pas de spécialités : le pré-remplissage ne les y cherche plus.
    from app.schemas import CompanyOut
    assert "specialites" not in CompanyOut.model_fields and "(c.specialites" not in JS


# ═══ 12. L'onglet « À venir » ══════════════════════════════════════════════════════════════════════════════════════

def test_e12_a_venir_fin_du_contrat_bulle_juste_et_neutre():
    """Sur 0f8eb32 : « Renouvellement ~ [fin − 120 jours] » (une date de republication devinée), une bulle « sources
    réelles BOAMP » (la source principale est la DECP) et « positionnez-vous auprès du client »."""
    texte = _plat(_sans_commentaires(RADAR))
    for interdit in ("Renouvellement", "renouvellement_estime", "sources réelles", "positionnez-vous",
                     "auprès du client", "(réelle)"):
        assert interdit not in texte, interdit
    m = re.search(r'<b style="font-size:13\.5px">Contrats qui arrivent à échéance</b><button type="button" '
                  r'class="tip">.*?<span class="tip-b" role="tooltip">([^<]*)</span>', RADAR)
    assert m and m.group(1) == BULLE_A_VENIR                       # un seul nœud de texte : traduit entier
    assert ('<span class="pill go avenir-fin"><span>Fin du contrat estimée le</span><span>{{ fmtDate(r.fin_estimee) '
            '}}</span><span>{{ srcRenDuree(r) }}</span></span>') in RADAR
    assert "<span>{{ src.renewals.source==='BOAMP' ? 'attribution publiée le' : 'notifié le' }}</span>" in RADAR
    assert "{{ src.renewals.source==='BOAMP' ? 'Voir l\\'avis d\\'attribution' : 'Voir la fiche acheteur' }}" in RADAR
    # Le département, jamais les descripteurs que le repli range dans `lieu` (« Toiture, Couverture »).
    assert '<span v-if="r.dept"> · dépt {{ r.dept }}</span>' in RADAR and "r.lieu" not in RADAR
    # Ce que la bulle affirme, dans le code : la DECP calcule la fin sur la date de notification et la durée publiée.
    from app.services import decp
    src = pathlib.Path(decp.__file__).read_text(encoding="utf-8")
    assert "fin = notif + timedelta(days=int(duree * 30.4))" in src and 'duree = row.get("dureemois")' in src
    assert 'notif = _parse(row.get("datenotification"))' in src


def test_e12_la_duree_dite_avec_sa_source_sous_node():
    script = (_fonction("dureeFinDeContrat") + "\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(c => "
              "dureeFinDeContrat(c[0], c[1]))));")
    cas = [[{"duree_estimee": False}, "DECP"], [{"duree_estimee": False}, "BOAMP"], [{"duree_estimee": True}, "BOAMP"],
           [{"duree_estimee": True}, "DECP"], [{}, ""]]
    assert _node(script, json.dumps(cas)) == [
        "(durée publiée)", "(durée lue dans l'intitulé de l'avis)", "(durée estimée selon le type de contrat)",
        "(durée estimée selon le type de contrat)", "(durée publiée)"]


def _compteurs(uid):
    from app.models import User
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        u = db.get(User, uid)
        return (u.trial_analyses_used or 0, u.analyses_used_this_month or 0)
    finally:
        db.close()


def _maj(uid, **cols):
    from app.models import User
    from tests.test_redaction_socle0 import _db
    db = _db()
    try:
        u = db.get(User, uid)
        for k, v in cols.items():
            setattr(u, k, v)
        db.commit()
    finally:
        db.close()


def test_e12_le_credit_annonce_avant_le_clic_est_celui_du_code(client, auth, monkeypatch):
    """La ligne sous les champs, avant « Chercher les fins de contrat », et sa bulle, vérifiées sur la route : la DECP ne
    consomme rien ; le repli (BOAMP + IA) consomme 1 analyse s'il trouve, la rend s'il ne trouve rien, la rend toujours
    en outre-mer et en Corse (seul ou avec la métropole) ; il faut une analyse disponible, même là. La réponse dit
    ensuite à l'écran d'où viennent les fins de contrat et ce qu'est devenue l'analyse. Sur 0f8eb32 : aucune ligne,
    et la réponse du repli ne disait ni sa source ni le sort de l'analyse."""
    from app.services import decp, renewal
    from tests.test_redaction_socle0 import _user_id
    # Avant le clic : la ligne et sa bulle, entre les champs et les résultats, sauf pour la démo (jamais débitée).
    i_bouton, i_ligne, i_liste = (RADAR.index("Chercher les fins de contrat</button>"), RADAR.index(CREDIT),
                                  RADAR.index('v-for="r in src.renewals.list"'))
    assert i_bouton < i_ligne < i_liste
    assert ('<p v-if="!estDemo()" id="avenir-credit" class="avenir-credit small muted"><i data-lucide="coins" '
            f'aria-hidden="true"></i><span>{CREDIT}</span><button type="button" class="tip tip-l">') in RADAR
    assert f'<span class="tip-b" role="tooltip">{BULLE_CREDIT}</span>' in RADAR
    assert ":aria-describedby=\"estDemo() ? null : 'avenir-credit'\"" in RADAR
    assert f"{{{{ src.renewals.analyse==='debitee' ? \"{APRES_DEBIT}\" : \"{APRES_REMB}\" }}}}" in RADAR

    uid = _user_id(auth["email"])
    fin = {"idweb": "25-34232", "objet": "Voirie", "acheteur": "Ville", "lieu": "Voirie", "dept": "29",
           "date_attribution": "2025-01-30", "duree_mois": 36, "duree_estimee": True, "type_contrat": "",
           "fin_estimee": "2028-01-29", "renouvellement_estime": "2027-10-01", "score": 70, "url": "https://x.invalid"}
    decp_rend, repli_rend = {"v": []}, {"v": []}
    monkeypatch.setattr(decp, "detect_renewals_decp", lambda *a, **k: {"count": len(decp_rend["v"]),
                                                                      "renewals": list(decp_rend["v"]), "errors": [],
                                                                      "source": "DECP"})
    monkeypatch.setattr(renewal, "detect_renewals", lambda *a, **k: {"count": len(repli_rend["v"]),
                                                                    "renewals": list(repli_rend["v"]), "errors": []})

    def demande(deps):
        _maj(uid, trial_analyses_used=0, analyses_used_this_month=0)
        r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie", "departements": deps})
        return r, _compteurs(uid)

    try:
        # « La recherche dans les données publiées des marchés attribués ne consomme aucune analyse. »
        decp_rend["v"], repli_rend["v"] = [dict(fin, duree_estimee=False)], [dict(fin)]
        r, c = demande(["29"])
        assert r.status_code == 200 and c == (0, 0) and r.json()["source"] == "DECP" and "analyse" not in r.json()
        # « Si elle ne donne rien … consomme 1 analyse » ; l'écran le dit ensuite.
        decp_rend["v"] = []
        r, c = demande(["29"])
        assert c == (1, 1) and r.json()["source"] == "BOAMP" and r.json()["analyse"] == "debitee"
        assert [f["idweb"] for f in r.json()["renewals"]] == ["25-34232"]
        # « remboursée si elle ne trouve aucune fin de contrat »
        repli_rend["v"] = []
        r, c = demande(["29"])
        assert c == (0, 0) and r.json()["analyse"] == "remboursee" and r.json()["source"] == "BOAMP"
        # « toujours remboursée dès qu'un des départements demandés est en outre-mer ou en Corse », même s'il trouve.
        repli_rend["v"] = [dict(fin)]
        for deps in (["974"], ["971"], ["988"], ["2A", "2B"], ["20"], ["29", "974"], ["2B", "56"]):
            r, c = demande(deps)
            assert r.status_code == 200 and c == (0, 0) and r.json()["analyse"] == "remboursee", deps
        # « Il faut une analyse disponible pour la lancer », même en outre-mer.
        _maj(uid, trial_analyses_used=10 ** 6, analyses_used_this_month=0)
        r = client.post("/api/sourcing/renewals", headers=auth["headers"], json={"query": "voirie", "departements": ["974"]})
        assert r.status_code == 402, r.text
    finally:
        _maj(uid, trial_analyses_used=0, analyses_used_this_month=0)


_SCRIPT_RENEWALS = r"""
const o = {
__METHODES__
};
async function cas(rep) {
  const vus = [];
  Object.assign(o, { src: { query: "", dept: "29", renewals: { list: [], loading: false, done: false, source: "x", analyse: "x" } },
    notify(m) { vus.push("notify:" + m); }, go() {}, loadStats() { vus.push("loadStats"); },
    api: async () => rep });
  await o.srcRenewals();
  return { source: o.src.renewals.source, analyse: o.src.renewals.analyse, vus,
           duree: o.src.renewals.list.map(r => o.srcRenDuree(r)) };
}
(async () => {
  const out = {};
  const reps = JSON.parse(process.argv[1]);
  for (const k in reps) out[k] = await cas(reps[k]);
  out.demo = [estCompteDemo({ email: " Demo@Adjugo.fr " }), estCompteDemo({ email: "pme@test.fr" }), estCompteDemo(null)];
  console.log(JSON.stringify(out));
})();
"""


def test_e12_apres_le_repli_l_ecran_dit_ce_qu_est_devenue_l_analyse_sous_node():
    from app.services.demo_search import is_demo
    from types import SimpleNamespace
    pur = (re.search(r"^const DEMO_EMAIL_APP = .*$", JS, re.M).group(0) + "\n" + _fonction("estCompteDemo") + "\n"
           + _fonction("dureeFinDeContrat") + "\n")
    script = pur + _SCRIPT_RENEWALS.replace("__METHODES__", "\n".join(_methode(m) for m in (
        "srcDeps", "srcRenDuree", "srcRenewals")))
    fin = {"idweb": "1", "duree_estimee": False}
    reps = {"decp": {"count": 1, "renewals": [fin], "errors": [], "source": "DECP"},
            "debitee": {"count": 1, "renewals": [fin], "errors": [], "source": "BOAMP", "analyse": "debitee"},
            "remboursee": {"count": 0, "renewals": [], "errors": [], "source": "BOAMP", "analyse": "remboursee"},
            "demo": {"count": 1, "renewals": [fin], "errors": [], "source": "DECP"}}
    r = _node(script, json.dumps(reps))
    assert r["decp"]["source"] == "DECP" and r["decp"]["analyse"] == "" and "loadStats" not in r["decp"]["vus"]
    assert r["decp"]["duree"] == ["(durée publiée)"]
    assert r["debitee"]["analyse"] == "debitee" and "loadStats" in r["debitee"]["vus"]    # le compteur est relu
    assert r["debitee"]["duree"] == ["(durée lue dans l'intitulé de l'avis)"]
    assert r["remboursee"]["analyse"] == "remboursee" and "loadStats" in r["remboursee"]["vus"]
    # La démo de pitch : la même règle que le serveur (demo_search.is_demo), qui ne débite jamais son « À venir ».
    assert r["demo"] == [True, False, False]
    assert is_demo(SimpleNamespace(email=" Demo@Adjugo.fr ")) and not is_demo(SimpleNamespace(email="pme@test.fr"))


def test_e12_la_demo_de_pitch_garde_ses_fins_de_contrat_sans_credit():
    """La démo (son « À venir » est servi à part, sans réseau, IA ni analyse) : ses fins de contrat portent une durée
    publiée et la source « DECP », donc « (durée publiée) » et « notifié le » à l'écran ; jamais d'« analyse » dans la
    réponse. Son compte ne voit pas la ligne du crédit (estDemo)."""
    from app.services.demo_search import renewals_results
    res = renewals_results(["44"])
    assert res["source"] == "DECP" and "analyse" not in res and res["renewals"]
    assert all(f["duree_estimee"] is False and f["dept"] == "44" for f in res["renewals"])
    assert '<p v-if="!estDemo()" id="avenir-credit"' in RADAR


# ═══ 13. La page d'exemple de la démo ══════════════════════════════════════════════════════════════════════════════

def test_e13_la_page_d_exemple_de_la_demo_dit_vrai():
    """« … récupérées automatiquement par Adjugo » et « Sur un compte réel, ce lien ouvre la vraie délibération » :
    faux, la veille des projets à venir est masquée (PROJETS_A_VENIR éteint par défaut ; ses adresses répondent 404)."""
    from app.core.interrupteurs import projets_a_venir_actif
    page = (STATIC / "demo" / "deliberation.html").read_text(encoding="utf-8")
    assert "récupérées automatiquement" not in page and "Sur un compte réel, ce lien ouvre" not in page
    assert ("La veille des projets votés en conseil, « Projets à venir », n'est pas encore ouverte : Adjugo ne lit pas "
            "aujourd'hui ces délibérations.") in page
    assert "Document fictif, à titre d'illustration : une délibération réelle se lit sur le site de la collectivité" in page
    assert not mots_bannis(re.sub(r"<[^>]+>", " ", page))
    import os
    if not os.environ.get("PROJETS_A_VENIR"):
        assert projets_a_venir_actif() is False


# ═══ Textes : traductions, mots bannis, contrat ═══════════════════════════════════════════════════════════════════

def test_ecran_lot1_textes_traduits_sans_mot_banni_ni_emoji():
    d = _dico()
    for fr in LIBELLES:
        assert fr in HTML or fr.replace("'", "\\'") in HTML or fr in JS, fr      # chaque libellé est bien à l'écran
        assert d["nl"].get(fr) and d["es"].get(fr), fr
        assert not mots_bannis(fr), fr
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", fr), fr
    assert "remboursée" not in d["nl"][CREDIT] and "Corsica" in d["nl"][CREDIT] and "Córcega" in d["es"][CREDIT]
    assert "vérifié" not in _plat(_sans_commentaires(CARTE + RADAR)).lower()


def test_ecran_lot1_contrat_et_bilan_de_mise_en_ligne():
    contrat = _plat((ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8"))
    assert "## Écran" in (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    ecran = contrat[contrat.index("## Écran"):]
    for x in ("tests/test_moteur_lot1_ecran.py", "Fin du contrat estimée le", "(rectificatif du", "Dire mon métier",
              "date_limite_rectificatif", "nom_organisme", CREDIT, "récupérées automatiquement",
              "jusqu'à l'annonce du crédit à l'écran"):
        assert x in ecran, x
    bilan = _plat((ROOT / "docs" / "MISE_EN_LIGNE_22_10.md").read_text(encoding="utf-8"))
    for x in ("Fin du contrat estimée le", "Date limite repoussée au", "Dire mon métier", CREDIT,
              "confiance", "test_moteur_lot1_ecran.py"):
        assert x in bilan, x
