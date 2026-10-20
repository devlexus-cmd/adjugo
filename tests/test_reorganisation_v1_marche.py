"""
Réorganisation de l'interface — vague 1, chantiers 1.4 (de la recherche au marché) et 1.5 (la page du marché en
4 étapes). Contrat : docs/REORGANISATION_V1.md, § 1.4 et 1.5 ; étude, § 5.3, 8, 9 ; décisions 0, 6 et 8.

On DÉPLACE les cartes existantes, la logique ne change pas :
  - la page du marché : en tête, « Inviter un partenaire » (le bouton le plus visible, décision 0) ; puis une barre
    d'ancres Lire · Décider · Préparer · Déposer (décision 6), qui remplace sur cette page les étapes 1 à 5 du
    groupement ; chaque carte sous son étape ; le pied de page replié (journal, devis et factures, supprimer) ;
  - un seul « Répartir » ; les cartes des partenaires renommées sans jargon ; « Prêt à déposer » sort de la
    convention, reste réservé au groupement ; le prix est une tâche de Préparer ;
  - décision 8 : le seul pourcentage est le couple « Seul X % · À plusieurs Y % », après le dossier ; « N sur M »
    ailleurs ; aucune note sur un partenaire ;
  - la recherche : plus d'« Étape 1 / Étape 2 », « Ouvrir le marché » juste après l'analyse, qui s'affiche à l'écran.

Sans navigateur ni réseau ; les fonctions pures sous Node, sur les vrais états de la démonstration.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.textes_visibles import mots_bannis, textes_html
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
PAGE = zone(HTML, "vue-aodetail")

# Chaque étape et ses cartes, dans l'ordre de la page (contrat, § 1.0.3).
ETAPES = {
    "marche-lire": ["marche-analyse", "marche-grille", "marche-dossier-fichiers", "marche-client"],
    "marche-decider": ["marche-plusieurs", "marche-qui-me-complete"],
    "marche-preparer": ["marche-prix", "marche-dossier-presentation", "marche-pieces", "marche-taches-plusieurs",
                        "marche-reseau", "marche-partenaires", "marche-convention"],
    # Vague 2a (A2) : la liste à cocher (marche-avant-depot) est entrée dans « Prêt à déposer », une seule liste.
    "marche-deposer": ["marche-pret-a-deposer", "marche-export"],
    "marche-pied": ["marche-devis-suivi", "marche-journal-acces", "marche-actions"],
}
TITRES = {"marche-lire": "Lire", "marche-decider": "Décider", "marche-preparer": "Préparer",
          "marche-deposer": "Déposer"}
REFS = {"marche-lire": "etLire", "marche-decider": "etDecider", "marche-preparer": "etPreparer",
        "marche-deposer": "etDeposer"}


def _sans_commentaires(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _fonction(nom):
    i = JS.index(f"function {nom}(")
    return JS[i:JS.index("\n}\n", i) + 3]


# ═══ 1.5 La page du marché en 4 étapes ══════════════════════════════════════════════════════════════

def test_quatre_etapes_dans_l_ordre_chaque_carte_sous_la_sienne():
    ordre = ["marche-entete", "marche-etapes", "marche-lire", "marche-decider", "marche-preparer", "marche-deposer",
             "marche-pied"]
    pos = [PAGE.index(zone(HTML, n)) for n in ordre]
    assert pos == sorted(pos)
    for etape, cartes in ETAPES.items():
        z = zone(HTML, etape)
        places = [z.index(zone(HTML, c)) for c in cartes]
        assert places == sorted(places), etape
        for autre in set(ETAPES) - {etape}:          # une carte n'est que sous une étape
            for c in cartes:
                assert zone(HTML, c) not in zone(HTML, autre), (c, autre)
    for etape, titre in TITRES.items():
        z = zone(HTML, etape)
        assert z.startswith(f'<section data-test="{etape}" ref="{REFS[etape]}" tabindex="-1"')
        assert f'<h3 id="mk-{etape[7:]}-h">{titre}</h3>' in z and 'class="tip"' in z.split("</div>")[0]
    # Le bilan d'un marché gagné ou perdu (et le carnet de notes) reste en tête : c'est l'étape du moment.
    for n in ("marche-resultat", "marche-carnet"):
        assert zone(HTML, n) in zone(HTML, "marche-entete")
    # Décider sans analyse : un état vide qui dit quoi faire, jamais une étape blanche.
    assert '<p v-if="!ao.project.ai_analysis" class="card pad muted small mk-vide">' in zone(HTML, "marche-decider")
    # Le pied de page est replié (journal, devis et factures, supprimer).
    pied = zone(HTML, "marche-pied")
    assert pied.startswith('<details data-test="marche-pied"') and "Supprimer ce marché" in pied
    assert "aoToggleAudit()" in pied and "aoToggleAudit()" not in zone(HTML, "marche-reseau")


def test_barre_d_ancres_qui_remplace_les_etapes_du_groupement():
    barre = zone(HTML, "marche-etapes")
    boutons = re.findall(r"<button\b[^>]*>", barre)
    assert len(boutons) == 4 and all('type="button"' in b for b in boutons)
    for etape, ref in REFS.items():
        assert f"@click=\"rnScrollTo('{ref}')\"" in barre and f'<span>{TITRES[etape]}</span>' in barre
    assert barre.count(":aria-current=") == 4 and "aoEtape()" in barre
    # Les étapes 1 à 5 du groupement ne sont plus sur cette page (elles deviennent les tâches de Préparer) ;
    # côté partenaire, le stepper reste jusqu'à la vague 2b.
    for motif in ("gstep", "grpSteps(", "grpEtapeNow("):
        assert motif not in PAGE, motif
    assert "grpSteps(sfmState())" in zone(HTML, "vue-sharedao")
    assert "Étape 3" not in HTML
    # À 375 px, la barre tient sur une ligne : 4 colonnes, le numéro au-dessus du mot.
    assert ".mk-etapes { display:grid; grid-template-columns:repeat(4, minmax(0,1fr));" in CSS
    i = CSS.index("@media (max-width:520px) {\n  .mk-etapes")
    assert ".mk-et { flex-direction:column;" in CSS[i:i + 300]


def test_inviter_un_partenaire_en_tete_le_bouton_le_plus_visible():
    entete = zone(HTML, "marche-entete")
    bouton = zone(HTML, "marche-inviter")
    assert bouton in entete and ">Inviter un partenaire</button>" in bouton
    assert 'type="button" class="btn primary"' in bouton and "width:100%" in bouton
    # Avant les 4 chiffres : sur téléphone ils s'empilent et repoussaient le bouton sous la ligne de flottaison.
    assert entete.index(bouton) < entete.index('<div class="cards cols-4"')
    # Le seul bouton pleine largeur de la page. Vague 2a (A2) : il ouvre la fenêtre d'invitation unique (plus de
    # formulaire dans la page) ; le lien à copier y est, après l'envoi.
    assert PAGE.count("width:100%;justify-content:center") == 1
    assert '@click="aoInviter()"' in bouton and "ao.share.lastUrl" not in HTML + JS and "inviteForm" not in HTML + JS
    assert 'v-model="rinv.email"' in zone(HTML, "fenetre-invitation") and "rinv.url" in zone(HTML, "fenetre-invitation")
    # Toutes les entrées d'invitation y mènent : « Inviter {nom} », la carte vide, la recherche.
    grp = JS[JS.index("    aoGrpInvite(m) {"):JS.index("    _grpProfileId(m) {")]
    assert "this.inviterOuvrir(" in grp and "this.rnInviteOpen(" in grp and "reseauCard" not in grp
    assert "aoInviter() { if (this.ao.project) this.inviterOuvrir({ projectId: this.ao.project.id }); }," in JS
    assert "if (inviter) this.aoInviter();" in JS
    assert '@click="aoInviter()"' in zone(HTML, "marche-reseau")
    assert "Inviter un partenaire sur ce marché" not in HTML


def test_un_seul_repartir():
    page = _sans_commentaires(PAGE)
    assert page.count("aoOptimizeGroup()") == 1 and page.count("Répartir entre partenaires") == 1
    plusieurs, membres = zone(HTML, "marche-plusieurs"), zone(HTML, "marche-partenaires")
    assert "aoOptimizeGroup()" in plusieurs and "Composition suggérée" in plusieurs
    assert "aoOptimizeGroup()" not in membres and "Composition suggérée" not in membres
    assert "Utilisez « Ajouter »" not in JS          # le bouton « Ajouter » n'existe pas


def test_cartes_des_partenaires_renommees_sans_jargon():
    for ancien in ("Partenaires pour ce marché", "Partenaires sur ce marché", "Monter le groupement",
                   "Réseau Adjugo — montez le dossier à plusieurs", "Votre client (l'acheteur)",
                   "Vos partenaires sur ce marché", "Contributions des partenaires", "Contribution reçue"):
        assert ancien not in _sans_commentaires(PAGE), ancien
    assert '<h3 id="pm-h">Qui me complète ?</h3>' in zone(HTML, "marche-qui-me-complete")
    assert '<i data-lucide="handshake" style="color:var(--accent-text)"></i><h3>Partenaires invités</h3>' in zone(HTML, "marche-reseau")
    assert "<h3>Membres et sous-traitants</h3>" in zone(HTML, "marche-partenaires")
    assert '<i data-lucide="scroll-text" style="color:var(--accent-text)"></i><h3 id="conv-h">Convention et accords</h3>' in zone(HTML, "marche-convention")
    assert '<i data-lucide="scale" style="color:var(--accent-text)"></i><h3>Répondre à plusieurs ?</h3>' in zone(HTML, "marche-plusieurs")
    # « caduque » : « à revalider », avec la raison (étude, § 8).
    conv = zone(HTML, "marche-convention")
    assert "caduc" not in conv and "Convention à revalider : les accords déjà enregistrés ne comptent plus." in conv
    assert "ao.conv.staleReason" in conv and "caducs" not in JS
    # Les textes du serveur qui citaient la carte citent son nouveau nom.
    for f in ("app/routers/checklist.py", "app/routers/invites.py", "app/services/atelier_assemblage.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "« Monter le groupement »" not in src and "« Convention et accords »" in src, f


def test_pret_a_deposer_hors_de_la_convention_pour_tous():
    pret, deposer = zone(HTML, "marche-pret-a-deposer"), zone(HTML, "marche-deposer")
    assert pret in deposer and pret not in zone(HTML, "marche-convention")
    # Vague 2a (A2) : une seule liste, pour tous ; le serveur a un calcul pour l'entreprise seule (jamais un faux manque
    # de groupement : tests/test_reorganisation_v2a_marches_invitations.py).
    assert pret.startswith('<section data-test="marche-pret-a-deposer" class="conv-pret"')
    assert "if (!st || !this.convVisible()) return false;" not in JS
    assert "Marquer déposé" in pret and 'ref="depotCard"' in pret
    # La liste à cocher avant le dépôt : dans « Prêt à déposer », pour tous ; plus dans les documents de réponse.
    assert "predepotDone }} sur {{ predepotSteps.length }}" in pret and "À vérifier vous-même" in pret
    assert "predepot" not in zone(HTML, "pieces-documents-reponse")
    # Un seul « Exporter le dossier complet » visible à la fois.
    assert 'v-if="!aoExportDansPret()"' in zone(HTML, "marche-export")
    assert "Exporter le dossier complet" not in zone(HTML, "marche-actions")


def test_le_prix_est_une_tache_de_preparer():
    prep = zone(HTML, "marche-preparer")
    assert prep.index(zone(HTML, "marche-prix")) < prep.index('id="atl-card"') < prep.index("Mes documents de réponse")
    sous = prep.index('<div class="mk-sous"><h4>À plusieurs</h4>')
    assert prep.index(zone(HTML, "marche-pieces")) < sous < prep.index(zone(HTML, "marche-taches-plusieurs"))


def test_decision_8_le_seul_pourcentage_est_le_couple_apres_le_dossier():
    page = _sans_commentaires(PAGE)
    assert "/100" not in page and not re.search(r"\}\}\s*/\s*\{\{", page), "« N sur M », jamais « N/M »"
    # Chaque « % » encore affiché : le couple, ou un taux qui n'est pas une note (TVA, frais de déplacement).
    sans_style = re.sub(r'\s:?style="[^"]*"', "", page)
    permis = re.compile(r"Seul|À plusieurs|sg-big|TVA|0 % — je ne facture|>5,5 %<|>10 %<|>20 %<|majoration_pct")
    for ligne in sans_style.split("\n"):
        if "%" in ligne:
            assert permis.search(ligne), ligne.strip()[:160]
    entete = zone(HTML, "marche-entete")
    assert "Seul {{ ao.project.match_score }} %" in entete and "À plusieurs {{ ao.project.groupement_score }} %" in entete
    assert "Compatibilité" not in entete and "{{ ao.project.ai_analysis ? 'Analyse préliminaire' : 'À analyser' }}" in entete
    plusieurs = zone(HTML, "marche-plusieurs")
    for couple in ("Seul {{ ao.grp.sim.score_seul }} % · À plusieurs {{ ao.grp.sim.score_groupement }} %",
                   "Seul {{ h.score_seul }} % · À plusieurs {{ h.score_groupement }} %",
                   "'À plusieurs ' + c.score_avec + ' %'"):
        assert couple in plusieurs, couple
    assert "{{ ao.checklist.stats.ok }} sur {{ ao.checklist.stats.total }}" in zone(HTML, "pieces-a-fournir")
    assert "{{ d.n_accords }} sur {{ d.n_signataires }}" in zone(HTML, "marche-convention")
    # Pas de note sur un partenaire (règle 10 de l'étude moteur) : plus de « score /100 » des entreprises trouvées.
    assert "c.score.total" not in zone(HTML, "marche-partenaires") and "l.candidate.score" not in PAGE
    assert "Détail du score" not in zone(HTML, "marche-partenaires")
    # Le journal du dossier (pied de page) aussi.
    i = JS.index("    aoTimeline() {")
    assert '"seul " + a.match_score + " %"' in JS[i:i + 900] and "/100" not in JS[i:i + 900]


def test_vocabulaire_client_sans_jargon_ni_mot_banni():
    textes = [t for _l, t in textes_html(PAGE)]
    assert not [t for t in textes if mots_bannis(t)]
    assert "Client non précisé" in PAGE and "Acheteur non précisé" not in PAGE
    assert "plateforme acheteur" not in PAGE and "appel d'offres" not in _sans_commentaires(PAGE)
    # Le nom du client, en tête, mène à sa carte.
    assert "@click=\"rnScrollTo('clientCard')\"" in zone(HTML, "marche-entete")
    assert 'ref="clientCard" tabindex="-1"' in zone(HTML, "marche-client")


def test_ouvrir_un_marche_le_montre_en_haut():
    ouvrir = JS[JS.index("    async openAo(p) {"):JS.index("    loadPredepot(pid) {")]
    assert 'const w = document.querySelector(".work"); if (w) w.scrollTop = 0;' in ouvrir


# ═══ 1.4 De la recherche au marché ══════════════════════════════════════════════════════════════════

def test_recherche_ouvrir_le_marche_suit_l_analyse():
    vue, ana = zone(HTML, "vue-sourcing"), zone(HTML, "trouver-analyse")
    assert ">Étape 1<" not in vue and ">Étape 2<" not in vue
    assert ">Rechercher des marchés</b>" in zone(HTML, "trouver-recherche") and ">Analyse du marché</b>" in ana
    # « Ouvrir le marché » vient juste après le résumé et la lecture du dossier, avant le détail.
    ouvrir = ana.index("srcOuvrirMarche(false)")
    assert ana.index("src.analysis.summary") < ouvrir < ana.index("src.analysis.score_breakdown && ")
    assert ouvrir < ana.index("detailRows(src.analysis.details)") and "srcOuvrirMarche(true)" in ana
    # L'analyse s'affiche sous les résultats : l'écran y mène (sinon rien ne semblait se passer).
    assert 'ref="srcAnalyse" tabindex="-1"' in ana
    analyser = JS[JS.index("    async srcAnalyze(t) {"):JS.index("    async srcUploadDce(e) {")]
    assert 'this.rnScrollTo("srcAnalyse");' in analyser
    # Décision 8 sur l'analyse : le couple, « N sur M ».
    assert "À plusieurs {{ src.analysis.groupement_score }} %" in ana and "/100" not in ana
    assert "{{ c.points }} sur {{ c.max_points }}" in ana
    # Correctifs déjà faits, toujours là : plus d'étapes 3 et 4, plus de « Rattacher ».
    assert ">Rattacher</button>" not in HTML and "srcGenerate" not in JS


# ═══ Fonctions pures, sous Node, sur les vrais états de la démonstration ════════════════════════════

def test_etape_du_marche_et_taches_a_plusieurs_sous_node():
    script = _fonction("etapeDuMarche") + _fonction("tachesPlusieurs") + """
const cas = JSON.parse(process.argv[1]);
console.log(JSON.stringify({
  etapes: cas.etapes.map(c => etapeDuMarche(c[0], c[1], c[2])),
  taches: cas.taches.map(st => tachesPlusieurs(st).map(t => [t.key, t.etat, t.statut, t.detail, t.voir])),
}));
"""
    cas = {
        "etapes": [["nouveau", False, 1], ["en_cours", False, 1], ["nouveau", True, 1], ["nouveau", True, 2],
                   ["en_cours", True, 1], ["en_cours", True, 5], ["envoye", True, 1], ["perdu", True, 5],
                   ["gagne", True, 1], ["abandonne", False, 1], [None, False, None]],
        "taches": [None, {"etape": 1}, {"etape": 2, "n_members": 0},
                   {"etape": 2, "n_members": 2, "n_submitted": 1, "n_with_price": 1, "convention_status": "draft"},
                   {"etape": 3, "n_members": 2, "n_submitted": 2, "n_with_price": 1, "convention_status": "aucune"},
                   {"etape": 4, "n_members": 1, "n_submitted": 1, "n_with_price": 1, "convention_status": "a_signer",
                    "convention": {"n_accords": 1, "n_signataires": 2}, "offer_frozen": True},
                   {"etape": 3, "n_members": 1, "n_submitted": 1, "n_with_price": 1, "convention_status": "perimee"}],
    }
    r = _node(script, json.dumps(cas))
    assert r["etapes"] == ["lire", "lire", "decider", "preparer", "preparer", "deposer", "deposer", "", "", "", "lire"]
    t = r["taches"]
    assert t[0] == [] and t[1] == []
    assert t[2] == [["inviter", "a_faire", "Pas commencé", "", "invitations"], ["parts", "a_faire", "Pas commencé", "", "parts"],
                    ["convention", "a_faire", "Pas commencé", "", "convention"], ["offre", "a_faire", "Pas commencé", "", "convention"]]
    assert t[3][0] == ["inviter", "fait", "Terminé", "2 partenaires", "invitations"]
    assert t[3][1] == ["parts", "en_cours", "En cours", "1 sur 2", "parts"]
    assert t[3][2] == ["convention", "en_cours", "En cours", "brouillon", "convention"]
    assert t[4][1][:2] == ["parts", "en_cours"]                       # une part sans prix : pas encore « Terminé »
    assert t[4][2][:2] == ["convention", "a_faire"]                   # « aucune » = pas de convention
    assert t[5][2] == ["convention", "en_cours", "En cours", "accords 1 sur 2", "convention"]
    assert t[5][3] == ["offre", "fait", "Terminé", "figée", "convention"]
    assert t[6][2][1:4] == ["en_cours", "En cours", "à revalider"]


@pytest.fixture(scope="module")
def vitrine(client):
    """La démonstration remise à neuf (comme au démarrage du serveur), avant et après ce module."""
    from app.core.database import SessionLocal
    from app.services.demo_seed import ensure_demo

    def neuf():
        db = SessionLocal()
        try:
            ensure_demo(db, force=True)
        finally:
            db.close()
    neuf()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    yield {"Authorization": "Bearer " + r.json()["access_token"]}
    neuf()


def test_la_page_du_marche_de_la_demo(client, vitrine):
    """Toiture en préparation, Kerhel en groupement validé (Déposer, tâches faites), Limauzac perdu (aucune étape :
    son bilan et son carnet sont en tête) : ce que la barre et les tâches montrent, calculé sur les vrais états."""
    projets = client.get("/api/projects/", headers=vitrine).json()
    projets = projets if isinstance(projets, list) else projets.get("items", projets.get("projects", []))

    def etat(fragment):
        p = next(x for x in projets if fragment in x["name"])
        fiche = client.get(f"/api/projects/{p['id']}", headers=vitrine).json()
        st = client.get(f"/api/projects/{p['id']}/groupement/state", headers=vitrine)
        return {"statut": fiche["status"], "dossier": bool((fiche.get("ai_analysis") or {}).get("dce_available")),
                "state": st.json() if st.status_code == 200 else None}

    cas = {"toiture": etat("Réfection toiture — Groupe scolaire Jean Moulin"),
           "kerhel": etat("Gymnase de Kerhel"), "limauzac": etat("gendarmerie de Limauzac")}
    script = _fonction("etapeDuMarche") + _fonction("tachesPlusieurs") + """
const cas = JSON.parse(process.argv[1]), out = {};
for (const k in cas) { const c = cas[k], st = c.state;
  out[k] = { etape: etapeDuMarche(c.statut, c.dossier, st && st.etape), taches: tachesPlusieurs(st).map(t => [t.key, t.statut, t.detail]) }; }
console.log(JSON.stringify(out));
"""
    r = _node(script, json.dumps(cas))
    assert r["toiture"]["etape"] == "preparer" and r["toiture"]["taches"] == []
    assert r["limauzac"]["etape"] == ""
    assert r["kerhel"]["etape"] == "deposer"
    assert r["kerhel"]["taches"] == [["inviter", "Terminé", "1 partenaire"], ["parts", "Terminé", "1 sur 1"],
                                     ["convention", "Terminé", "validée par tous"], ["offre", "Terminé", "figée"]]


# ═══ Décision 16 : les libellés renommés ou nouveaux ont leur néerlandais et leur espagnol ═════════════

NOUVEAUX = ["Convention et accords", "Chercher des partenaires", "Membres et sous-traitants", "Partenaires invités",
            "Votre client", "Client non précisé", "Analyse préliminaire", "Journal, devis et factures, supprimer",
            "Poser une question à l'IA sur ce marché", "Parts reçues",
            "Part reçue", "Aucune part reçue pour l'instant.", "Calculer le score à plusieurs", "Rechercher des marchés",
            "Analyse du marché", "Terminé", "Pas commencé", "Voir", "Offre commune", "Seul",
            "Aucun partenaire invité sur ce marché.", "Ancienne version : à revalider",
            "Convention à revalider : les accords déjà enregistrés ne comptent plus.",
            "Déjà ajoutés à ce marché",
            "Lire", "Décider", "Préparer", "Déposer", "À plusieurs", "Inviter un partenaire", "Qui me complète ?"]


def test_traductions_des_libelles_de_la_page_du_marche():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    for k in NOUVEAUX:
        assert d["nl"].get(k) and d["es"].get(k), f"« {k} » sans traduction (scripts/i18n_ajouter.py)"
        assert k in HTML or k in JS, f"« {k} » n'est plus affiché : retirez-le de NOUVEAUX"
