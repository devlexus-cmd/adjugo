"""
Rédaction, vague 3 — les ÉCRANS « Mes preuves » (E1, étude § 6.7 ; doctrine § 7 ; décision 8a).

Ce qui est vérifié, sans navigateur ni réseau :
 • menu NON réorganisé : « Mes preuves » est une entrée de plus, SOUS « Mon entreprise », toutes
   les autres gardent leur ordre ; « Mon entreprise » porte deux onglets (profil / preuves) ;
 • l'écran : cinq listes courtes (Références, Qualifications, Équipe, Matériel, Chiffres clés),
   libellé de source avec le lien vers le passage ou le justificatif, date de fin de validité et
   alerte sobre, « à reconfirmer », raison quand une fiche n'est pas utilisée, CV minimal (ni photo,
   ni adresse, ni date de naissance ; jamais envoyé à l'IA), reprise de l'existant cochée ;
 • l'atelier : « Insérer une fiche » (fin de la partie) et « Fiche » dans l'éditeur (au curseur) ;
 • zéro émoji, jamais « vérifié », pas de jargon, boutons typés, bulles (i) bien formées, liens
   protégés, v-html seulement pour l'aperçu rendu par le moteur sûr de l'atelier ;
 • les fonctions pures de l'écran exécutées sous Node ;
 • le parcours de l'écran contre la vraie API : chaque champ lu existe.
"""
import json
import os
import re
import shutil
import subprocess
import uuid

import pytest

from tests.test_redaction_v2_atelier import _creer, _projet
from tests.zones import zone, zones
from tests.test_redaction_v3_mes_preuves import _coffre, _company, _h, _ok, _preuve, _register, _reseau

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


HTML, JS, CSS = _read("app.html"), _read("app.js"), _read("styles.css")


def _between(s, start, end):
    i = s.index(start)
    return s[i:s.index(end, i)]


def _sans_commentaires_html(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _sans_commentaires_js(s):
    return re.sub(r"(^|\s)//[^\n]*", r"\1", s)


# Zones repérées par leur attribut data-test (tests/zones.py, docs/REORGANISATION_V1.md).
VUE = zone(HTML, "vue-preuves")
FENETRES = "\n".join(zones(HTML, "fenetres-preuves"))
ENTREPRISE = zone(HTML, "vue-company")
ATELIER = zone(HTML, "vue-atelier")
JS_PUR = _between(JS, "// ══════════ « Mes preuves » (rédaction, vague 3, E1) — état et listes fermées",
                  "// ══════════ fin « Mes preuves » — fonctions pures")
JS_METH = _between(JS, "    // ══════════ « Mes preuves » (rédaction, vague 3, E1) ══════════", "    // ── Company / Criteria ──")
CSS_PV = _between(CSS, "/* ══════════ « Mes preuves » (rédaction, vague 3, E1)", "/* ══════════ Atelier du dossier")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆✅❌✔✖★☆]")
MENU_AVANT = ["dashboard", "sourcing", "pipeline", "cotraitants", "reseau", "documents", "company", "shared", "amont",
              "kb", "consortiums", "contacts", "invoices", "criteria", "team", "billing", "admin"]


# ═══ 1. Où l'écran s'affiche : sous « Mon entreprise », menu non réorganisé ════════════════

def test_menu_non_reorganise_mes_preuves_sous_mon_entreprise():
    nav = zone(HTML, "menu")
    ordre = re.findall(r"go\('([a-z]+)'\)", nav)
    assert [x for x in ordre if x != "preuves"] == MENU_AVANT        # aucune entrée déplacée
    assert ordre.index("preuves") == ordre.index("company") + 1      # juste sous « Mon entreprise »
    entree = re.search(r'<a class="nav-item nav-sub"[^>]*go\(\'preuves\'\)[^>]*>.*?</a>', nav).group(0)
    assert "Mes preuves" in entree
    # « Mon entreprise » : deux onglets, le profil et « Mes preuves ».
    for bloc in (ENTREPRISE, VUE):
        onglets = _between(bloc, '<nav class="rn-tabs pv-onglets" aria-label="Mon entreprise">', "</nav>")
        assert "Profil de l'entreprise" in onglets and "Mes preuves" in onglets
    assert "go('preuves')" in ENTREPRISE and "go('company')" in VUE
    assert 'titles: { preuves: "Mes preuves",' in JS
    assert 'if (v === "preuves") { this.pvLoad(); this._pvSourcesCharger(); }' in JS
    # Renvoi depuis les collaborateurs du profil : le CV se renseigne dans « Mes preuves ».
    assert "il n'est jamais envoyé à l'IA" in _sans_commentaires_html(ENTREPRISE)


def test_l_ecran_cinq_listes_sources_validite_et_cv_minimal():
    v = _sans_commentaires_html(VUE)
    for lib in ("Références", "Qualifications", "Équipe", "Matériel", "Chiffres clés"):
        assert lib in JS_PUR, lib
    assert 'v-for="n in pvNatures()"' in v
    # Bulle (i) proposée par l'étude.
    assert ("Adjugo relie chaque fait à l'endroit où il l'a trouvé : un passage de vos documents, un "
            "justificatif, une source publique, ou votre déclaration. Il ne sait pas si ce document est à jour : "
            "relisez vos preuves.") in v
    # Chaque fiche : son libellé de source, le lien vers le passage ou le justificatif, la validité,
    # « à reconfirmer », la raison quand Adjugo ne s'en sert pas.
    for attendu in ("{{ p.source_libelle }}", "p.source.lien_passage", "pvPassage(p)", "p.source.lien_justificatif",
                    "pvJustificatif(p)", "pvValidite(p)", "p.a_reconfirmer", "à reconfirmer", "p.raison_message",
                    "safeUrl(p.source.url)"):
        assert attendu in v, attendu
    # Ajout manuel = « déclaré par vous » par défaut ; les autres sources selon la nature.
    assert 'type_source: "declare"' in JS_METH
    assert 'v-for="t in pvTypesSource(pv.form.nature)"' in v
    # CV minimal : ni photo, ni adresse, ni date de naissance ; jamais envoyé à l'IA.
    assert "Le CV ne contient ni photo, ni adresse, ni date de naissance. Il n'est jamais envoyé à l'IA" in v
    champs_cv = re.findall(r'\{ k: "([a-z_]+)"', _between(JS_PUR, "  salarie: [", "  ],"))
    assert champs_cv == ["nom", "fonction", "experience_annees", "diplomes", "qualifications", "chantiers"]
    for interdit in ("photo", "adresse", "naissance", "telephone", "email"):
        assert interdit not in champs_cv
    # Alerte d'échéance sobre (dans l'écran, sans couleur criarde ni compte à rebours permanent).
    assert "pvAlertes()" in v and "à mettre à jour" in v
    # Propositions : l'utilisateur coche ce qui est juste ; reprise de l'existant cochée.
    assert "cochez celles qui sont justes" in v and "pvAccepterCoches(pv.tab)" in v
    assert "Reprendre ce que vous avez déjà saisi" in v and "pvReprendre()" in v
    assert "Rien n'y est modifié ni supprimé, et un élément déjà présent dans « Mes preuves » n'est jamais repris deux fois." in v
    # Suppression définitive : confirmation qui dit ce qu'elle fait.
    assert "Supprimer définitivement" in JS_METH and "CV compris" in JS_METH


def test_atelier_inserer_une_fiche_sans_ia():
    a = _sans_commentaires_html(ATELIER)
    assert '@click="pvAtlOuvrir()"' in a and "Insérer une fiche" in a       # lecture : fin de la partie
    assert re.search(r"atlTool\('tableau'\).*?pvAtlOuvrir\(\)\"><i data-lucide=\"paperclip\"></i>Fiche</button>", a, re.S)
    f = _sans_commentaires_html(FENETRES)
    assert "Insérer une fiche de « Mes preuves »" in f
    assert "La fiche est recopiée telle quelle dans la partie, sans IA" in f
    assert "Un CV n'est jamais envoyé à l'IA" in f
    ins = _between(JS_METH, "    async pvAtlInserer() {", "\n    },\n")
    assert '"/inserer-preuve"' in ins and "pvInsererTexte(a.edit.texte, x.pos, f.bloc)" in ins
    assert '"/rediger"' not in ins and '"/raccourcir"' not in ins


def test_regles_d_interface_zero_emoji_jamais_verifie_boutons_bulles():
    for nom, bloc in (("vue", VUE), ("fenêtres", FENETRES), ("js", JS_METH), ("pur", JS_PUR), ("css", CSS_PV)):
        assert not EMOJI.search(bloc), nom
    chaines = " ".join(re.findall(r'"((?:[^"\\\n]|\\.)*)"', _sans_commentaires_js(JS_METH + JS_PUR)))
    for nom, bloc in (("vue", _sans_commentaires_html(VUE)), ("fenêtres", _sans_commentaires_html(FENETRES)),
                      ("js", chaines)):
        low = bloc.lower()
        assert "vérifié" not in low and "verifie" not in low, nom
        for jargon in ("consortium", "mandataire", "workflow", "prompt", "token", "rag", "chunk"):
            assert not re.search(r"\b" + jargon + r"\b", low), (nom, jargon)
    for bloc in (VUE, FENETRES):
        s = _sans_commentaires_html(bloc)
        for m in re.finditer(r"<button\b(?:[^>\"]|\"[^\"]*\")*>", s):
            assert 'type="button"' in m.group(0), m.group(0)[:120]
        assert s.count('class="tip-b" role="tooltip"') == s.count("tip-b")
        assert s.count('<button type="button" class="tip">') == s.count("tip-b")
    # v-html : seulement l'aperçu, rendu par le moteur sûr de l'atelier (tout échappé).
    assert re.findall(r'v-html="([^"]+)"', VUE + FENETRES) == ["pvApercuHtml(f)"]
    assert 'pvApercuHtml(f) { return atlMdToHtml((f && f.bloc) || "", []); }' in JS_METH
    # 375 px : grille d'une colonne et onglets compacts sous 600 px ; pas de largeur fixe.
    mob = CSS_PV[CSS_PV.index("@media (max-width:600px)"):]
    assert ".pv-grid { grid-template-columns:1fr; }" in mob and ".pv-natures { display:grid;" in mob
    assert not re.search(r"(?<![-\w])width:\s*\d{3,}px", CSS_PV)


def test_routes_branchees():
    for route in ('"/api/preuves"', '"/api/preuves/reprise"', '"/passage"', '"/api/preuves/" + p.id + "/" + action',
                  '"/inserer-preuve"', '"/preuves"'):
        assert route in JS_METH, route
    assert '"PATCH", "/api/preuves/" + f.id' in JS_METH and "body.version = f.version" in JS_METH
    assert '"DELETE", "/api/preuves/" + p.id' in JS_METH


# ═══ 2. Fonctions pures, sous Node ════════════════════════════════════════════════════════

def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    out = subprocess.run([node, "-e", JS_PUR + "\n" + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_corps_envoye_au_serveur_sous_node():
    r = _node("""
      const f = { nature: "reference", v: { objet: "  Toiture  ", acheteur: "", lieu: "Quimper", annee: "2024",
                  montant_ht: "85 000,50", role: "seul", description: "" }, type_source: "documents",
                  doc_id: "4", passage: "En 2024…", date_source: "2021-03-01", document_id: "",
                  pub: { nom: "", url: "", consulte_le: "", identifiant: "" }, est: { project_id: "", detail: "" },
                  date_fin_validite: "2027-01-01" };
      const a = pvCorps(f, false);
      const b = pvCorps(Object.assign({}, f, { type_source: "declare" }), false);
      const c = pvCorps({ nature: "qualification", v: { nom: "Qualibat", organisme: "", numero: "", detail: "" },
                          type_source: "public", pub: { nom: "DECP", url: "https://x.fr", consulte_le: "2026-10-01", identifiant: "" },
                          est: {}, date_fin_validite: "" }, true);
      const d = pvCorps({ nature: "chiffre_cle", v: { libelle: "Délai", valeur: "douze", unite: "", annee: "" },
                          type_source: "estimation", est: { project_id: "7", detail: "" }, pub: {} }, false);
      console.log(JSON.stringify([a, b, c, d]));""")
    a, b, c, d = r
    assert a == {"valeur": {"objet": "Toiture", "lieu": "Quimper", "annee": 2024, "montant_ht": 85000.5, "role": "seul"},
                 "type_source": "documents", "source": {"doc_id": 4, "passage": "En 2024…"}, "date_source": "2021-03-01"}
    assert b["source"] is None and b["date_source"] is None and "date_fin_validite" not in b
    assert c["source"] == {"nom": "DECP", "url": "https://x.fr", "consulte_le": "2026-10-01", "identifiant": ""}
    assert c["date_fin_validite"] is None                      # une date vidée est effacée
    assert d["valeur"]["valeur"] == "douze"                    # pas un nombre : le serveur le refuse proprement
    assert d["source"] == {"project_id": 7, "detail": ""}


def test_insertion_au_curseur_validite_et_alertes_sous_node():
    r = _node("""
      const out = {};
      out.debut = pvInsererTexte("Texte existant.", 0, "**Fiche**");
      out.milieu = pvInsererTexte("Avant.\\n\\nAprès.", 7, "**Fiche**");
      out.fin = pvInsererTexte("Texte.  ", null, "**Fiche**");
      out.vide = pvInsererTexte("", 5, "**Fiche**");
      const p = (o) => Object.assign({ statut: "acceptee", nature: "qualification", valeur: { nom: "Q" } }, o);
      out.v = [pvValidite(p({})), pvValidite(p({ date_fin_validite: "2027-12-31", jours_restants: 400 })),
               pvValidite(p({ date_fin_validite: "2026-11-05", jours_restants: 23 })),
               pvValidite(p({ date_fin_validite: "2026-10-13", jours_restants: 0 })),
               pvValidite(p({ date_fin_validite: "2026-10-09", jours_restants: -4, expiree: true })),
               pvValidite(p({ statut: "retiree", date_fin_validite: "2026-10-09", jours_restants: -4, expiree: true }))];
      out.e = [pvEcheance(p({ date_fin_validite: "2026-10-09", expiree: true })), pvEcheance(p({ date_fin_validite: "2026-11-05", jours_restants: 1 }))];
      out.a = pvAlertes([p({ id: 1, date_fin_validite: "2027-12-31", jours_restants: 400 }),
                         p({ id: 2, date_fin_validite: "2026-11-05", jours_restants: 23 }),
                         p({ id: 3, date_fin_validite: "2026-10-09", jours_restants: -4, expiree: true }),
                         p({ id: 4, statut: "retiree", date_fin_validite: "2026-10-09", expiree: true })]).map(x => x.id);
      out.t = [pvTitre({ nature: "salarie", valeur: { nom: "Yann Tanguy", fonction: "Couvreur" } }),
               pvTitre({ nature: "chiffre_cle", valeur: { libelle: "Effectif", valeur: 14, unite: "personnes" } }),
               pvDetail({ nature: "reference", valeur: { acheteur: "Mairie", annee: 2024, montant_ht: 0, role: "groupement_solidaire" } }),
               pvDetail({ nature: "salarie", valeur: { experience_annees: 1, diplomes: "CAP" } })];
      console.log(JSON.stringify(out));""")
    assert r["debut"] == {"texte": "**Fiche**\n\nTexte existant.", "pos": 11}
    assert r["milieu"]["texte"] == "Avant.\n\n**Fiche**\n\nAprès."
    assert r["fin"]["texte"] == "Texte.\n\n**Fiche**" and r["vide"]["texte"] == "**Fiche**"
    assert r["v"][0] is None and r["v"][1] == {"t": "Valable jusqu'au 31/12/2027", "cls": ""}
    assert r["v"][2] == {"t": "Valable jusqu'au 05/11/2026 (encore 23 jours)", "cls": "pv-warn"}
    assert r["v"][3]["t"] == "Valable jusqu'au 13/10/2026 (dernier jour)"
    assert r["v"][4] == {"t": "Fin de validité dépassée (09/10/2026) : Adjugo ne s'en sert plus", "cls": "pv-ko"}
    assert r["v"][5]["t"] == "Fin de validité dépassée (09/10/2026)"
    assert r["e"] == ["fin de validité dépassée le 09/10/2026", "valable jusqu'au 05/11/2026 (encore 1 jour)"]
    assert r["a"] == [3, 2]                                   # acceptées seulement, la plus proche d'abord
    assert r["t"][0] == "Yann Tanguy, Couvreur" and r["t"][1].startswith("Effectif : 14")
    assert r["t"][2] == "Mairie · 2024 · 0 € HT · en groupement solidaire"
    assert r["t"][3] == "1 an d'expérience · CAP"


# ═══ 3. Le parcours de l'écran contre la vraie API ══════════════════════════════════════════

def test_parcours_de_l_ecran_contre_l_api(client):
    email, h, uid = _register(client)
    _company(client, h)
    _reseau(uid, [{"intitule": "Charpente de la salle des fêtes", "client": "Commune de Rosporden", "annee": 2023}])
    _coffre(uid)
    # « Mes preuves » : ce que la liste lit.
    d = _ok(client.get("/api/preuves", headers=h))
    assert {"preuves", "compteurs", "natures", "types_source"} <= set(d)
    natures_js = re.findall(r'\{ code: "([a-z_]+)", l: ', _between(JS_PUR, "const PV_NATURES = [", "];"))
    assert natures_js == [n["code"] for n in d["natures"]]
    sources_js = re.findall(r'\{ code: "([a-z]+)", l: "[^"]+", natures: ', JS_PUR)
    assert sorted(sources_js) == sorted(t["code"] for t in d["types_source"])
    assert sources_js[0] == "declare"                          # ajout manuel : « déclaré par vous » d'abord
    for t in d["types_source"]:
        js = re.search(r'\{ code: "' + t["code"] + r'", l: "[^"]+", natures: (null|\[[^\]]*\]) \}', JS_PUR).group(1)
        assert (js == "null") == (len(t["natures"]) == 5), t
    # Chaque champ de chaque nature est connu du serveur (liste fermée).
    from app.services import preuves as pv
    for nature, champs in pv.CHAMPS.items():
        bloc = _between(JS_PUR, f"  {nature}: [", "  ],")
        assert sorted(re.findall(r'\{ k: "([a-z_]+)"', bloc)) == sorted(champs), nature
    # La reprise : ce que l'écran lit.
    ap = _ok(client.get("/api/preuves/reprise", headers=h))
    assert {"elements", "deja", "a_reprendre"} <= set(ap)
    for e in ap["elements"]:
        assert {"cle", "nature", "valeur", "manque", "deja", "provenance_libelle", "source_libelle",
                "date_fin_validite"} <= set(e)
    r = _ok(client.post("/api/preuves/reprise", headers=h,
                        json={"cles": [e["cle"] for e in ap["elements"] if not e["manque"]]}))
    assert {"creees", "deja", "ignorees"} <= set(r)
    # Une fiche ajoutée à la main, puis modifiée, retirée, remise, supprimée.
    p = _preuve(client, h, nature="materiel", valeur={"designation": "Nacelle 18 m", "quantite": 2})
    for k in ("id", "nature", "valeur", "type_source", "source_libelle", "source", "date_source", "a_reconfirmer",
              "date_fin_validite", "expiree", "jours_restants", "statut", "statut_libelle", "utilisable", "raison",
              "raison_message", "version", "numero"):
        assert k in p, k
    p = _ok(client.patch(f"/api/preuves/{p['id']}", headers=h, json={"valeur": {"designation": "Nacelle 18 m",
                                                                                   "quantite": 3},
                                                                       "type_source": "declare", "source": None,
                                                                       "date_source": None, "version": p["version"]}))
    assert p["valeur"]["quantite"] == 3
    p = _ok(client.post(f"/api/preuves/{p['id']}/retirer", headers=h, json={"version": p["version"]}))
    assert p["raison"] == "retiree"
    p = _ok(client.post(f"/api/preuves/{p['id']}/accepter", headers=h, json={"version": p["version"]}))
    assert p["utilisable"] is True
    assert client.delete(f"/api/preuves/{p['id']}", headers=h).status_code == 204
    # L'atelier : ce que la fenêtre « Insérer une fiche » lit.
    pid = _projet(client, h, with_dce=False)
    _creer(client, h, pid)
    f = _ok(client.get(f"/api/atelier/{pid}/preuves", headers=h))
    assert {"fiches", "ecartees"} <= set(f) and f["fiches"]
    for x in f["fiches"]:
        assert {"id", "nature", "titre", "bloc", "source_libelle", "a_reconfirmer", "date_fin_validite"} <= set(x)
    _e2, h2, _u2 = _register(client)
    assert client.get(f"/api/atelier/{pid}/preuves", headers=h2).status_code == 404
