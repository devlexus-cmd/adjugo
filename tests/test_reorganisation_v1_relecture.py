"""
Réorganisation de l'interface — vague 1, RELECTURE de la fin de vague (contrat : docs/REORGANISATION_V1.md, § 4.7).

Chaque test reproduit une remarque des relectures (navigation, vocabulaire et vérité, démo de pitch, tests et UX) qui
échouait sur 6fddf13 :
- anciens noms d'écran encore dits par le SERVEUR (chaînes coupées sur deux lignes, que la recherche textuelle ne
  voyait pas) : « Partagé avec moi », « Profil de l'entreprise », « Monter le groupement », « Réseau > … » ;
- décision 8 côté serveur (« N/M » dans des f-strings, note sur 100 du courriel des alertes), sur l'accueil (taux en
  pourcentage) et sur la vitrine (« Compétences réunies 33 % ») ;
- mots bannis encore visibles : dossier rangé « CERFA », compte-rendu PDF (« Co-traitant »), « AO-0001 » sur les
  pièces remises à l'acheteur, noms des fichiers et dossiers du ZIP, « SIRENE » chez les collectivités, pièces de
  réponse de la démo ;
- « vérifié » pour un constat qui n'est pas une identité (décision 9) ; promesse du courriel sur la vitrine ;
- démo : anciens noms en bulle, « Étape » du statut à côté de la barre d'étapes, accueil et page du marché qui ne
  plaçaient pas un marché à la même étape, « À venir » refusé, nombre nu dans l'anneau ;
- bandeau des cookies sur le groupe « Réglages » ; traductions néerlandaises incohérentes.

Aucun appel réseau : lecture des sources, fonctions exécutées sous Node, routes appelées par le client de test.
"""
import ast
import io
import json
import pathlib
import re
import shutil
import subprocess
import zipfile

import pytest

from tests.test_reseau_ecrans import _method
from tests.textes_visibles import _CLE, _docstrings, _nom_appel, mots_bannis
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
INV = (STATIC / "invite.html").read_text(encoding="utf-8")
LANDING = (STATIC / "landing.html").read_text(encoding="utf-8")


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _obj(*noms):
    return "const o = {\n" + "\n".join(_method(n) for n in noms) + "\n};\n"


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader
    assert pdf[:4] == b"%PDF"
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _exclus(arbre) -> set:
    """Chaînes jamais lues par un client : docstrings, journaux, étiquettes OpenAPI des routeurs (tags, prefix)."""
    exclus = _docstrings(arbre)
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and _nom_appel(n) in ("info", "warning", "error", "exception", "debug"):
            exclus |= {id(x) for x in ast.walk(n)}
        if isinstance(n, ast.keyword) and n.arg in ("tags", "prefix"):
            exclus |= {id(x) for x in ast.walk(n)}
    return exclus


def _constantes(src: str):
    """[(ligne, texte)] des chaînes d'un source Python. L'ast FUSIONNE les littéraux adjacents (« « Partagé "
    "avec moi » » devient une seule chaîne) ; une f-string est rendue avec « {} » à la place de ses valeurs."""
    arbre = ast.parse(src)
    exclus = _exclus(arbre)
    out = []
    for n in ast.walk(arbre):
        if id(n) in exclus:
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append((n.lineno, n.value))
        elif isinstance(n, ast.JoinedStr):
            out.append((n.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)))
    return out


def _py(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _fichiers_app():
    return sorted(p for p in (ROOT / "app").rglob("*.py") if str(p.relative_to(ROOT)) != "app/routers/cospace.py")


# ═══ Anciens noms d'écran : plus aucun dans ce que dit le serveur ═════════════════════════════════════════════

ANCIENS_NOMS = ("Partagé avec moi", "Profil de l'entreprise", "Profil du réseau de partenaires", "Monter le groupement",
                "Mes groupements", "Radar des échéances", "Alertes automatiques", "Réseau >", "Réseau &gt;",
                "Adjugo > Administration", "onglet Veille amont")
# (fichier, ancien nom) → raison. Toute nouvelle exception se justifie ici ET au contrat (§ 4.7).
ANCIENS_GARDES = {
    ("app/services/groupement_members.py", "Monter le groupement"):
        "étape du stepper côté partenaire, gardée jusqu'à la vague 2b (« Votre part dans [marché] », § 4.6)",
    ("app/services/i18n_data.py", "Tableau de bord"): "dictionnaire de traduction indexé sur les anciens libellés",
}


def test_aucun_ancien_nom_d_ecran_dans_les_textes_du_serveur():
    fautes = []
    for p in _fichiers_app():
        rel = str(p.relative_to(ROOT))
        for ln, t in _constantes(p.read_text(encoding="utf-8")):
            for a in ANCIENS_NOMS:
                if a in t and (rel, a) not in ANCIENS_GARDES:
                    fautes.append(f"{rel}:{ln} [{a}] {t[:100]!r}")
    assert not fautes, "\n".join(fautes)
    # Les pages et scripts servis non plus (chemins de navigation de l'ancien menu).
    for f in ("app.html", "app.js", "invite.html", "redaction-partenaire.js", "landing.html"):
        src = (STATIC / f).read_text(encoding="utf-8")
        for a in ("Réseau >", "Réseau &gt;", "Adjugo > Administration"):
            assert a not in src, (f, a)


def test_les_messages_corriges_disent_le_chemin_d_aujourd_hui():
    from app.services import atelier_groupement as ag
    from app.services import preuves_publiques as pp
    from app.services import preuves_reprise as pr
    # Vague 2a (A2) : « Où je suis partenaire » est un filtre de Mes marchés (plus un onglet).
    assert "dans Mes marchés, filtre « Où je suis partenaire »" in ag.MSG_ESPACE_COMPTE
    assert "Partagé" not in ag.MSG_ESPACE_COMPTE
    # Le même texte que le repli de l'écran du partenaire (redaction-partenaire.js), qui ne servait jamais.
    rp = (STATIC / "redaction-partenaire.js").read_text(encoding="utf-8")
    assert ag.MSG_ESPACE_COMPTE.split(". Vos")[0] in rp
    assert "dans Mon entreprise, onglet « Identité »" in pp.MSG_SIRET
    assert pr.PROVENANCES == {pr.ENTREPRISE: "Mon entreprise (Identité)",
                              pr.RESEAU: "Mon profil partenaire (Réseau Adjugo)", pr.COFFRE: "Mes documents"}
    red = _py("app/services/agents/redaction.py")
    assert "générez-la dans « Convention et \"\n                                        \"accords » (page du marché, étape Préparer)" in red
    res = _py("app/routers/reseau.py")
    # Vague 2b (B4, docs/REORGANISATION_V2B.md) : le courriel du réseau est composé par app/services/email_invitation.py.
    from app.services import email_invitation as ei
    assert ei.CHEMIN_PROFIL_RESEAU == "Partenaires › Réseau Adjugo › Mon profil partenaire"
    assert f"depuis {ei.CHEMIN_PROFIL_RESEAU}." in ei.invitation(chef="A", marche="M", url="u", reseau=True)["texte"]
    # Vague 2a (A2) : les invitations reçues se traitent dans Mes marchés, filtre « Où je suis partenaire ».
    assert "(Mes marchés, filtre \"\n                    \"« Où je suis partenaire »)" in res
    assert "<b>Mes marchés</b>, filtre « Où je suis partenaire »" in INV and "Invitations reçues" not in INV
    assert "menu Réglages › Administration › Profils du réseau à valider" in _py("app/services/partner_network.py")
    # Ces chemins existent bien dans l'application.
    assert ">Mon profil partenaire</button>" in HTML and "Invitations à traiter" in zone(HTML, "mes-marches-invitations")
    assert "Profils du réseau à valider" in zone(HTML, "vue-admin")


def test_le_partenaire_qui_a_un_compte_est_renvoye_vers_ou_je_suis_partenaire(client, auth):
    """De bout en bout : le lien rattaché à un compte (le courriel « Votre partie est à valider » mène à /invite/…)
    dit où rédiger aujourd'hui, à l'écran et dans le refus d'ouvrir l'espace par le lien."""
    from tests.test_redaction_v4_corrections import _partenaire_par_compte
    from tests.test_redaction_v4_groupement import _groupement
    _pid, _st, a, _b, _vue = _groupement(client, auth, avec_b=False)
    _partenaire_par_compte(client, a["token"])
    v = client.get(f"/api/invite/{a['token']}/redaction")
    assert v.status_code == 200, v.text
    msg = v.json()["espace"]["message"]
    assert "Mes marchés, filtre « Où je suis partenaire »" in msg and "Partagé avec moi" not in msg
    r = client.post(f"/api/invite/{a['token']}/redaction/espace", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "espace_par_le_compte"
    assert "Où je suis partenaire" in json.dumps(r.json(), ensure_ascii=False)


# ═══ Décision 8 côté serveur : « N sur M », jamais « N/M » ni une note sur 100 ═══════════════════════════════

# (fichier) → raison : une « N / M » qui n'est pas un texte du produit.
NM_GARDES = {
    "app/services/analysis.py": "consigne remise à l'IA (barème), jamais affichée",
    "app/services/carnet_notes.py": "note de l'acheteur (« 32,5 / 40 »), écrite comme dans son courrier (Réd. V6, § 3)",
    "app/sourcing/scoring.py": "détail du score de synergie entre entreprises, jamais affiché (ni app.html ni acheteur.html)",
}


def _n_sur_m_du_serveur():
    fautes = []
    for p in _fichiers_app():
        rel = str(p.relative_to(ROOT))
        if rel in NM_GARDES:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.JoinedStr):
                continue
            v = n.values
            phrase = any(isinstance(x, ast.Constant) and " " in x.value for x in v)
            for i in range(len(v) - 1):
                a, b = v[i], v[i + 1]
                if not (isinstance(a, ast.FormattedValue) and isinstance(b, ast.Constant)):
                    continue
                n_m = (re.fullmatch(r"\s*/\s*", b.value) and i + 2 < len(v) and isinstance(v[i + 2], ast.FormattedValue))
                sur_100 = re.match(r"\s*/\s*100\b", b.value)
                if phrase and (n_m or sur_100):
                    fautes.append(f"{rel}:{n.lineno} {ast.unparse(n)[:110]}")
    return fautes


def test_aucun_n_sur_m_avec_une_barre_dans_les_phrases_du_serveur():
    assert not _n_sur_m_du_serveur(), "\n".join(_n_sur_m_du_serveur())
    # Les trois messages de la remarque, et le détail du risque côté collectivités.
    assert 'f"Générée : accords enregistrés {n_ok} sur {len(sigs)}. ' in _py("app/routers/checklist.py")
    assert 'f" sur {len(_sigs)}).")' in _py("app/services/agents/redaction.py")
    assert "(analyses : {used} sur {lim} ce mois)" in _py("app/core/quota.py")
    assert "PME capable(s) sur {nb_capables} en procédure collective" in _py("app/services/infructuosite_scoring.py")
    # Le détail du score de synergie n'est affiché nulle part (raison de son exception).
    for f in ("app.html", "app.js", "acheteur.html"):
        assert "synergy" not in (STATIC / f).read_text(encoding="utf-8"), f


def test_courriels_des_alertes_sans_note_sur_100():
    al = _py("app/services/alerts.py")
    assert "/100]" not in al
    assert "lines.append(f\"   • {t['objet'][:90]} — {t.get('acheteur') or 'acheteur n/d'}{ech}\\n     {t['url']}\")" in al
    # Ce que promet la vitrine, exactement : objet, acheteur, date limite et lien vers l'annonce.
    assert "avec un mail récap : objet, acheteur, date limite et lien vers l'annonce." in LANDING
    assert "compétences attendues" not in LANDING


# (De bout en bout, la ligne « Convention de groupement » de la liste avant dépôt : test_convention_groupement.py,
# « accords enregistrés 0 sur 2 ».)


# ═══ Décision 8 : l'accueil, Mes marchés, la vitrine ══════════════════════════════════════════════════════════

def test_bilan_de_mes_marches_en_n_sur_m_et_seul_ou_a_plusieurs():
    b = zone(HTML, "bilan-gagne-perdu")       # vague 2a (A2) : « Où vous gagnez / perdez » est dans Mes marchés › Bilan
    assert "win_rate }}%" not in b and "win_rate||0 }}%" not in b and "taux global" not in b
    assert not re.search(r"\}\}\s*%", b), "plus aucun pourcentage affiché dans le bilan"
    assert "{{ gagnesSur(stats.by_status && stats.by_status.gagne, stats.decided) }}" in b
    assert '<div class="sectitle">Seul ou à plusieurs</div>' in b and "Groupement vs solo" not in b
    assert "{{ segmentSeul(g.key) }}" in b and "{{ g.won }} sur {{ g.total }}" in b
    assert "{{ z.won }} sur {{ z.total }}" in b and "{{ pt.won }} sur {{ pt.total }}" in b and "{{ ty.won }} sur {{ ty.total }}" in b
    r = _node(_obj("gagnesSur", "segmentSeul", "winInsights") + """
o.stats = { decided: 5, segments: {
  by_zone: [{ key: "49", won: 3, total: 3, win_rate: 100 }], by_type: [{ key: "Travaux", won: 2, total: 2, win_rate: 100 }],
  by_groupement: [{ key: "Groupement", won: 2, total: 2, win_rate: 100 }, { key: "Solo", won: 1, total: 3, win_rate: 33 }],
  by_partner: [{ key: "Breizh", won: 2, total: 2, win_rate: 100 }], loss_reasons: [] } };
console.log(JSON.stringify({ g: [o.gagnesSur(2, 3), o.gagnesSur(1, 1), o.gagnesSur(0, 2), o.gagnesSur(undefined, undefined)],
  s: [o.segmentSeul("Solo"), o.segmentSeul("Groupement"), o.segmentSeul("Autre")], i: o.winInsights() }));
""")
    assert r["g"] == ["2 gagnés sur 3", "1 gagné sur 1", "0 gagné sur 2", "0 gagné sur 0"]
    assert r["s"] == ["Seul", "À plusieurs", "Autre"]
    assert r["i"] and all("%" not in t for t in r["i"]), r["i"]
    assert any("(3 gagnés sur 3)" in t for t in r["i"]) and any("<b>à plusieurs</b> (2 gagnés sur 2) que seul (1 gagné sur 3)" in t
                                                               for t in r["i"])


def test_bilan_de_la_demonstration_sans_pourcentage(client, vitrine):
    """Ce que voit le pitch : « 2 gagnés sur 3 », « Dépt 87 : 0 sur 1 », jamais « taux global 67% »."""
    s = client.get("/api/agent/stats", headers=vitrine).json()
    r = _node(_obj("gagnesSur", "segmentSeul", "winInsights") + """
o.stats = JSON.parse(process.argv[1]);
const seg = o.stats.segments;
console.log(JSON.stringify({ tete: o.gagnesSur(o.stats.by_status.gagne, o.stats.decided),
  zones: seg.by_zone.map(z => z.won + " sur " + z.total), seul: (seg.by_groupement || []).map(g => o.segmentSeul(g.key)),
  lecons: o.winInsights() }));
""", json.dumps(s))
    assert r["tete"] == f"{s['by_status'].get('gagne', 0)} gagnés sur {s['decided']}" or r["tete"].endswith(f"sur {s['decided']}")
    assert all(re.fullmatch(r"\d+ sur \d+", z) for z in r["zones"]), r["zones"]
    assert set(r["seul"]) <= {"Seul", "À plusieurs"}
    assert all("%" not in t for t in r["lecons"])


def test_anneau_et_carte_disent_seul_ou_a_plusieurs():
    flux = zone(HTML, "accueil-flux")
    assert ('<div class="ao-c"><template v-if="scoreCourt(p)"><span class="ao-sc">{{ scoreCourt(p) }}</span> · '
            "</template>{{ p.client||'Acheteur non précisé' }}</div>") in flux
    kanban = zone(HTML, "vue-pipeline")
    assert '<span v-if="scoreCourt(p)" class="sc"' in kanban and "{{ scoreCourt(p) }}</span>" in kanban
    assert "kanbanScore(p)" not in HTML and "    kanbanScore(p) {" not in JS
    r = _node(_obj("scoreCourt") + """
console.log(JSON.stringify([{ match_score: 87 }, { match_score: 43, groupement_score: 100, go_decision: "go_groupement" },
  { groupement_score: 80, go_decision: "go_groupement" }, { match_score: 43, groupement_score: 100, go_decision: "go" }, {}]
  .map(p => o.scoreCourt(p))));
""")
    assert r == ["Seul 87 %", "À plusieurs 100 %", "À plusieurs 80 %", "Seul 43 %", ""]
    assert ".ao-c .ao-sc {" in CSS


def test_les_fonctions_appelees_par_le_gabarit_sont_des_methodes():
    """Le gabarit les appelle avec des parenthèses (« gagnesSur(…) ») : rangées dans `computed`, elles cassaient le
    rendu de l'accueil (« gagnesSur is not a function », vu dans un vrai navigateur pendant cette relecture)."""
    ic = JS.index("\n  computed: {")
    im = JS.index("\n  methods: {", ic)
    for n in ("gagnesSur(won, total)", "segmentSeul(k)", "scoreCourt(p)", "grpDashEtape(x)", "grpDashEtapes()",
              "enteteAncien()", "folderLabel(f)"):
        i = JS.index("\n    " + n)
        assert i > im, f"{n} doit être dans methods"
    assert ic < JS.index("\n    winInsights()") < im                     # propriété calculée (winInsights.length)


def test_vitrine_competences_reunies_en_n_sur_m():
    assert '<span class="pc"><span id="cappc">1</span> sur 3</span>' in LANDING
    assert "coPc.textContent=st>=2?3:st>=1?2:1;" in LANDING
    assert "33</span> %" not in LANDING and "?100:st>=1?66:33" not in LANDING


# ═══ Mots bannis : dossiers rangés, fichiers et PDF ═══════════════════════════════════════════════════════════

def test_chaque_dossier_range_s_affiche_sans_mot_banni():
    from app.services.dossier import FOLDERS
    i = JS.index("const DOSSIERS_AFFICHES = {")
    pur = JS[i:JS.index("\n", JS.index("function nomDossier(")) + 1]
    r = _node(pur + "console.log(JSON.stringify(JSON.parse(process.argv[1]).map(nomDossier)));",
              json.dumps(FOLDERS + ["Chiffrage", "", None]))
    assert r[:3] == ["Dossier du marché", "Formulaires officiels", "Dossier de présentation"]
    assert all(not mots_bannis(x or "") for x in r), r
    assert "    folderLabel(f) { return nomDossier(f); }," in JS
    for z in ("marche-dossier-fichiers", "vue-documents"):
        assert "folderLabel(" in zone(HTML, z), z
    from tests.test_reorganisation_v1_socle import _dico
    d = _dico()
    for lib in ("Formulaires officiels", "Dossier du marché", "Dossier de présentation"):
        assert d["nl"].get(lib) and d["es"].get(lib), lib


# Générateurs des PDF et du ZIP remis au client ou à l'acheteur (le test du socle ne lit que les courriels, les
# messages d'erreur et les pages) : une chaîne d'un seul mot compte quand elle commence par une majuscule
# (« Co-traitant », « DPGF »), une clé en minuscules (« cotraitants ») non.
GENERATEURS = ("app/services/consortium_report.py", "app/services/dpgf.py", "app/services/cerfa.py",
               "app/services/national_forms.py", "app/services/md_pdf.py", "app/routers/export_dossier.py",
               "app/routers/cerfa.py", "app/services/agents/redaction.py")
# Fonction entière gardée (modèle juridique, contrat § 0.3) et textes exacts gardés.
GENERATEURS_GARDES_FONCTIONS = {("app/services/agents/redaction.py", "_groupement_convention"):
                                "ancien modèle de convention (texte juridique, § 0.3 et pages juridiques § 6.4)"}


def test_generateurs_de_pdf_et_du_zip_sans_mot_banni():
    fautes = []
    for rel in GENERATEURS:
        arbre = ast.parse(_py(rel))
        exclus = _exclus(arbre)
        for fn in ast.walk(arbre):
            if isinstance(fn, ast.FunctionDef) and (rel, fn.name) in GENERATEURS_GARDES_FONCTIONS:
                exclus |= {id(x) for x in ast.walk(fn)}
        for n in ast.walk(arbre):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in exclus:
                t = n.value
                if _CLE.fullmatch(t) and not t[:1].isupper():
                    continue
                if mots_bannis(t):
                    fautes.append(f"{rel}:{n.lineno} {mots_bannis(t)} {t[:100]!r}")
    assert not fautes, "\n".join(fautes)


def test_compte_rendu_du_groupement_dit_juste():
    from app.services.consortium_report import ELEMENTS, elements_fournis, generate_consortium_report_pdf
    parts = [{"company": "Breizh Désamiantage", "role": "cotraitant", "status": "submitted", "lot": "Désamiantage",
              "has_references": True, "has_memoire": True, "qualifications_count": 1, "pieces_count": 3},
             {"company": "Le Gall Électricité", "role": "sous_traitant", "status": "invited", "lot": "",
              "has_references": False, "has_memoire": False, "qualifications_count": 0}]
    assert [elements_fournis(p) for p in parts] == [5, 0] and len(ELEMENTS) == 5
    txt = " ".join(_pdf_text(generate_consortium_report_pdf(
        "Gymnase", "Breizh Couverture", {"readiness": {"pct": 64, "submitted": 1, "invited": 2, "lots": 1},
                                         "partners": parts, "lots": []}, [])).split())
    assert "Partenaire du groupement" in txt and "Sous-traitant" in txt
    assert not mots_bannis(txt), mots_bannis(txt)
    assert "%" not in txt and "1/2" not in txt and "64" not in txt
    assert "1 sur 2" in txt and "5 sur 5" in txt and "0 sur 5" in txt


def test_compte_rendu_de_la_demonstration(client, vitrine):
    """Le PDF qu'on télécharge en pitch (Mes marchés › À plusieurs › « Compte-rendu interne ») : Kerhel."""
    projets = client.get("/api/projects/", headers=vitrine).json()
    projets = projets.get("projects", projets) if isinstance(projets, dict) else projets
    kerhel = next(p for p in projets if "Kerhel" in (p.get("name") or ""))
    r = client.get(f"/api/projects/{kerhel['id']}/consortium/report", headers=vitrine)
    assert r.status_code == 200, r.text
    txt = " ".join(_pdf_text(r.content).split())
    assert not mots_bannis(txt) and "%" not in txt and "1/1" not in txt, txt[:400]
    assert "1 sur 1" in txt and "Partenaire du groupement" in txt


def _ai(pid, analyse):
    from app.models import Project
    db = _db()
    try:
        p = db.get(Project, pid)
        p.ai_analysis = analyse
        db.commit()
    finally:
        db.close()


def test_reference_de_la_consultation_jamais_le_numero_interne(client, auth):
    from app.services.cerfa import (REFERENCE_A_COMPLETER, generate_attestation_honneur, generate_dume,
                                    reference_consultation)
    assert reference_consultation({"source": {"source": "BOAMP", "official_ref": "26-123456"}}) == "avis BOAMP n° 26-123456"
    assert reference_consultation({"source": {"official_ref": " 2026-TRX-04 "}}) == "2026-TRX-04"
    assert reference_consultation({}) is None and reference_consultation(None) is None
    company = {"name": "Breizh Couverture", "siret": "12345678900011"}
    for gen in (generate_attestation_honneur, generate_dume):
        txt = " ".join(_pdf_text(gen(company, {"name": "École", "client": "Ville", "reference": None})).split())
        assert REFERENCE_A_COMPLETER in txt and "AO-" not in txt, gen.__name__
    for rel in ("app/routers/export_dossier.py", "app/routers/cerfa.py", "app/services/agents/redaction.py"):
        assert "AO-{" not in _py(rel) and '"AO-' not in _py(rel), rel
    # De bout en bout : le dossier exporté (ZIP) d'un marché lu sur le BOAMP.
    h = auth["headers"]
    assert client.put("/api/company/", headers=h, json={"name": "Breizh Couverture", "city": "Quimper"}).status_code == 200
    pid = client.post("/api/projects/", headers=h, json={"name": "Réfection toiture"}).json()["id"]
    _ai(pid, {"source": {"source": "BOAMP", "official_ref": "26-123456", "source_url": ""}, "details": {}})
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    noms = z.namelist()
    assert all("CERFA" not in n and "AO_" not in n for n in noms), noms
    assert any(n.startswith("01_Formulaires_officiels/HONNEUR_") for n in noms), noms
    sommaire = z.read("00_SOMMAIRE.txt").decode("utf-8")
    assert "01_Formulaires_officiels/" in sommaire and "CERFA" not in sommaire
    for n in noms:
        if n.startswith("01_Formulaires_officiels/") and ("HONNEUR" in n or "DUME" in n):
            txt = " ".join(_pdf_text(z.read(n)).split())
            assert "avis BOAMP n° 26-123456" in txt and "AO-" not in txt, n
    assert "Dossier_" in r.headers.get("content-disposition", "")


def test_noms_de_fichiers_et_aperçu_du_dossier_sans_mot_banni(client, auth):
    assert "Dossier_AO_" not in JS
    assert JS.count('atlNomFichier(r.headers.get("content-disposition"), "Dossier_marche_"') == 2
    red = _py("app/services/agents/redaction.py")
    assert 'DOSSIER_FORMULAIRES = "formulaires_officiels"' in red and 'DOSSIER_PIECES_PARTENAIRES = "pieces_partenaires"' in red
    assert "pieces_cotraitants" not in red and 'f"cerfa/' not in red and '"AO"' not in red
    from app.services.dpgf import generate_dpgf_pdf
    from pypdf import PdfReader
    pdf = generate_dpgf_pdf({"lignes": [], "total_ht": 0}, "Breizh", "École")
    assert PdfReader(io.BytesIO(pdf)).metadata.title == "Estimation détaillée du prix"
    # L'aperçu du dossier commun (Mes marchés › À plusieurs), de bout en bout.
    from tests.test_cotraitance_v2_doctrine import _invite, _project
    h = auth["headers"]
    pid = _project(client, h)
    _invite(client, h, pid)
    r = client.get(f"/api/projects/{pid}/dossier-preview", headers=h)
    assert r.status_code == 200, r.text
    from app.services.memoire_export import DEFAULT_LABEL
    for f in r.json()["files"]:
        if f["name"].startswith(DEFAULT_LABEL + "."):
            continue          # nom par défaut du fichier remis à l'acheteur : son vocabulaire (contrat, § 0.3)
        assert not mots_bannis(f["name"]) and not mots_bannis(f["kind"]), f
    assert any(f["name"] == "formulaires_officiels/DC1.pdf" for f in r.json()["files"])


def test_pieces_de_reponse_de_la_demo_sans_mot_banni(client, vitrine):
    """La carte « Dossier du marché » de la page Toiture (pitch) : noms des fichiers et des dossiers affichés."""
    projets = client.get("/api/projects/", headers=vitrine).json()
    projets = projets.get("projects", projets) if isinstance(projets, dict) else projets
    toiture = next(p for p in projets if "toiture" in (p.get("name") or "").lower() and "Jean Moulin" in (p.get("name") or ""))
    dossiers = client.get(f"/api/projects/{toiture['id']}/documents", headers=vitrine).json()["folders"]
    i = JS.index("const DOSSIERS_AFFICHES = {")
    pur = JS[i:JS.index("\n", JS.index("function nomDossier(")) + 1]
    affiches = _node(pur + "console.log(JSON.stringify(JSON.parse(process.argv[1]).map(nomDossier)));",
                     json.dumps([g["folder"] for g in dossiers]))
    noms = [d["name"] for g in dossiers for d in g["documents"]]
    assert "Dossier de présentation — méthodologie étanchéité" in noms
    assert "Tableau de prix — décomposition du prix global et forfaitaire" in noms
    for t in noms + affiches:
        assert not mots_bannis(t), t


def test_collectivites_sans_sirene_dans_la_note_des_donnees_publiques():
    from app.services.agents import sourcing_acheteur as sa
    assert not mots_bannis(sa._DISCLAIMER) and "registre Insee" in sa._DISCLAIMER
    # Les textes que le module renvoie à l'écran (hors consigne de l'IA) : aucun mot banni.
    arbre = ast.parse(_py("app/services/agents/sourcing_acheteur.py"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_DISCLAIMER" for t in n.targets):
            assert isinstance(n.value, ast.Constant) and not mots_bannis(n.value.value)


# ═══ « Vérifié » : seulement pour une identité contrôlée dans un registre (décision 9) ═══════════════════════

def test_badges_du_reseau_verifie_seulement_pour_l_identite():
    r = _node("const o = {\n" + _method("nv") + "\n};\n" + """
console.log(JSON.stringify([{ key: "identite", niveau: "ok" }, { key: "sirene", niveau: "ok" }, { key: "bodacc", niveau: "ok" },
  { key: "decp", niveau: "ok" }, { key: "rge", niveau: "info" }, { key: "sirene", niveau: "alerte" },
  { key: "bodacc", niveau: "non_verifie" }, null].map(b => o.nv(b))));
""")
    assert r == ["vérifié", "vérifié", "constaté à la source", "constaté à la source", "information", "point d'attention",
                 "non vérifié", "non vérifié"]
    assert "<span class=\"sr-only\"> ({{ nv(b) }})</span>" in JS
    from app.services.partner_matching import badges
    out = {b["key"]: b for b in badges({"verified_bodacc": {"found": False, "checked_at": "2026-10-01"},
                                        "verified_decp": {"count": 3, "checked_at": "2026-10-01"}})}
    assert out["bodacc"]["niveau"] == "ok" and out["decp"]["niveau"] == "ok"   # c'est bien le cas que la règle couvre


# ═══ Démonstration (pitch) ═══════════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def vitrine(client):
    """La démonstration remise à neuf (comme au démarrage du serveur), avant et après ce module."""
    from app.services.demo_seed import ensure_demo

    def neuf():
        db = _db()
        try:
            ensure_demo(db, force=True)
        finally:
            db.close()
    neuf()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    yield {"Authorization": "Bearer " + r.json()["access_token"]}
    neuf()


def test_a_venir_en_demo_sert_des_fins_de_contrat_fictives(client, vitrine, monkeypatch):
    """« Trouver des marchés › À venir » : plus un refus « analyse IA » ; des contrats fictifs, sans réseau ni IA."""
    from app.core.demo_guard import blocked_action
    from app.services import decp, renewal

    def interdit(*a, **k):
        raise AssertionError("la démo ne doit ni lire DECP ni appeler l'IA")
    monkeypatch.setattr(decp, "detect_renewals_decp", interdit)
    monkeypatch.setattr(renewal, "detect_renewals", interdit)
    assert blocked_action("POST", "/api/sourcing/renewals") is None
    r = client.post("/api/sourcing/renewals", headers=vitrine, json={"query": "toiture", "departements": ["44"]})
    assert r.status_code == 200, r.text
    # Filtrées par département, comme le radar (la démo pré-remplit le 44) ; sans département, toutes.
    assert {x["dept"] for x in r.json()["renewals"]} == {"44"} and r.json()["count"] == 2
    r = client.post("/api/sourcing/renewals", headers=vitrine, json={"query": "toiture"})
    d = r.json()
    assert d["count"] == len(d["renewals"]) == 4 and d["errors"] == []
    from datetime import date
    for x in d["renewals"]:
        assert x["idweb"].startswith("DEMO-R") and x["url"] == "" and x["acheteur"].startswith("Ville de ")
        assert x["duree_estimee"] is False and x["fin_estimee"] > date.today().isoformat()
        assert x["date_attribution"] < date.today().isoformat() < x["renouvellement_estime"] < x["fin_estimee"]
    # Les acheteurs sont ceux, fictifs, de la démo (recherche et marché à plusieurs lots).
    from app.services.demo_lots import CLIENT
    from app.services.demo_search import _TENDERS
    fictifs = {t["details"]["acheteur"] for t in _TENDERS} | {CLIENT}
    assert {x["acheteur"] for x in d["renewals"]} <= fictifs


def test_statut_et_non_etape_a_cote_de_la_barre_d_etapes():
    tete = zone(HTML, "marche-entete")
    assert "<label>Statut</label>" in tete and "<label>Étape</label>" not in tete
    assert "<label>Statut</label>" in zone(HTML, "tiroir-projet")
    assert "<label>Étape</label>" not in HTML
    assert JS.count('this.notify("Statut mis à jour")') == 2 and "Étape mise à jour" not in JS
    from tests.test_reorganisation_v1_socle import _dico
    d = _dico()
    assert d["nl"]["Statut"] and d["es"]["Statut"] and d["nl"]["Statut mis à jour"] and d["es"]["Statut mis à jour"]


# ═══ Bandeau des cookies : jamais sur le menu ════════════════════════════════════════════════════════════════

def test_bandeau_des_cookies_jamais_sur_le_groupe_reglages():
    b = zone(HTML, "bandeau-cookies")
    # Vague 2b (B1, étude § 7.1) : il s'efface aussi tant que la fenêtre du SIRET est ouverte (il passait par-dessus).
    assert b.startswith('<div data-test="bandeau-cookies" v-if="!cookiesOk && !mobileNav && !(token && showWelcome)" '
                        "class=\"bandeau-cookies\" :class=\"{'avec-menu':!!token}\">")
    assert "position:fixed" not in b                                   # placé par la feuille de style
    i = CSS.index(".bandeau-cookies {")
    assert "position:fixed; left:12px; right:12px; bottom:12px; z-index:70;" in CSS[i:i + 200]
    assert "@media (min-width:861px) { .bandeau-cookies.avec-menu { left:calc(248px + 12px); } }" in CSS
    assert ".app { display:grid; grid-template-columns:248px 1fr;" in CSS   # la largeur du menu que le bandeau évite
    assert 'data-test="menu-reglages"' in zone(HTML, "menu")


# ═══ Traductions (décision 16) : un seul mot pour « marché » et pour « à plusieurs » ═════════════════════════

def test_traductions_coherentes_marche_et_a_plusieurs():
    from tests.test_reorganisation_v1_socle import _dico
    d = _dico()
    lus = HTML + JS
    fautes = []
    for k in d["nl"]:
        if k not in lus:
            continue                                 # clé ancienne, plus affichée
        nl, es = d["nl"][k], d["es"][k]
        if re.search(r"\bmarch[ée]s?\b", k, re.I) and not (re.search("aanbested", nl, re.I) and re.search("licitaci", es, re.I)):
            fautes.append((k, nl, es))
        if re.search(r"\bplusieurs\b", k, re.I) and not (re.search("samen|gezamenlijk", nl, re.I)
                                                          and re.search("agrupaci", es, re.I)):
            fautes.append((k, nl, es))
    assert not fautes, fautes
    assert d["nl"]["Marché"] == "Aanbesteding"
    assert d["nl"]["Vos marchés à plusieurs, par étape"] == "Uw gezamenlijke aanbestedingen, per stap"
    assert d["es"]["Vos marchés à plusieurs, par étape"] == "Sus licitaciones en agrupación, por etapa"
    for lib in ("Seul ou à plusieurs", "Formulaires officiels", "Statut mis à jour"):
        assert d["nl"].get(lib) and d["es"].get(lib), lib


# ═══ Contrat ═════════════════════════════════════════════════════════════════════════════════════════════════

def test_contrat_tableau_des_reperes_de_l_accueil_d_un_seul_tenant():
    doc = (ROOT / "docs" / "REORGANISATION_V1.md").read_text(encoding="utf-8")
    i = doc.index("**Accueil (`vue-dashboard`)**")
    bloc = doc[i:doc.index("**Page du marché", i)]
    lignes = [ln for ln in bloc.splitlines() if ln.strip()]
    table = [ln for ln in lignes if ln.startswith("|")]
    debut = lignes.index(table[0])
    assert lignes[debut:debut + len(table)] == table, "le tableau des repères de l'accueil est coupé"
    assert any("`accueil-bilan`" in ln for ln in table) and any("`accueil-carnet`" in ln for ln in table)
    assert "Retiré (§ 1.6) : `accueil-ruban`" in lignes[debut + len(table)]
    assert "### 4.7" in doc
