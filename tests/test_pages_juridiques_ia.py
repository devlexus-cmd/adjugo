"""
Pages juridiques et fournisseurs d'IA — textes publiés le 12/10/2026 (docs/IA_FOURNISSEURS_PAGES_JURIDIQUES.md).

Décision d'Eliot : Mistral est activé juste après la mise en ligne. Les pages (DPA, Sécurité,
Confidentialité) doivent donc être EXACTES avant l'activation (Anthropic seul) ET après (Anthropic +
Mistral AI, point d'accès UE ou mondial), ainsi qu'avec un fournisseur forcé (LLM_PROVIDER). Tout ce qui
dépend du fournisseur passe par des repères remplis par le serveur ; les phrases attendues sont écrites
ici en toutes lettres, indépendamment de app/main.py.

Faits vérifiés le 12/10/2026 : Mistral AI conserve jusqu'à 30 jours glissants (jamais « aucune
conservation ») ; entraînement désactivé sur le compte ; la liste de ses sous-traitants n'a PAS pu être
vérifiée (aucun nom, renvoi vers trust.mistral.ai/subprocessors) ; jamais « souverain », jamais
« hébergé en France ».

Aucun appel réseau : Mistral et son models.list sont simulés (tests.test_routage_ia).
"""
import html as _html
import pathlib
import re

import pytest

from app.services import llm
from tests.test_routage_ia import CLE_ANTHROPIC, _mistral, _propre  # noqa: F401  (_propre : autouse)

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ("/dpa", "/securite", "/confidentialite")

# ── Phrases attendues (texte lu par le visiteur, balises retirées) ─────────────────────────────────

ENTR_A = "Anthropic : jamais sans autorisation"
ENTR_M = "Mistral AI : utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur"
CONS_A = ("Anthropic : 30 jours en règle générale, jusqu'à 2 ans pour les contenus signalés pour non-respect "
          "de ses règles d'usage")
CONS_M = "Mistral AI : jusqu'à 30 jours glissants, pour la surveillance des abus"
ST_M = (" Mistral AI s'appuie sur ses propres sous-traitants techniques, dont la liste à jour est publiée sur "
        "son centre de confiance (https://trust.mistral.ai/subprocessors).")
ROLES_A = "Anthropic (Claude API) intervient pour la lecture des dossiers, les questions et la rédaction."
ROLES_AM = ("Anthropic (Claude API) intervient pour les questions sur les dossiers et la rédaction ; Mistral AI "
            "(La Plateforme), pour la lecture et l'analyse des dossiers ; chacun prend le relais de l'autre en "
            "cas de panne ou d'erreur.")
ROLES_M = "Mistral AI (La Plateforme) intervient pour la lecture des dossiers, les questions et la rédaction."


def _attendus(prov, roles, entr, cons, st, cct, essentiel):
    """Les phrases visées par la publication, une fois les repères remplis."""
    return {
        "/dpa": [
            f"modèles d'IA ({prov}, appelés via une API) : les contenus qui leur sont envoyés ne sont pas "
            f"utilisés pour entraîner un modèle ({entr}) ; les noms des salariés sont remplacés par des "
            f"étiquettes avant tout envoi ; la conservation est encadrée par les conditions applicables à "
            f"l'API ({cons}) ;",
            f"Intelligence artificielle : {roles} Les contenus envoyés ne sont pas utilisés pour entraîner un "
            f"modèle d'IA ({entr}).{st} Les lieux de calcul (et de stockage, lorsque le fournisseur s'y "
            f"engage) figurent dans le tableau ci-dessus. La conservation est encadrée par les conditions "
            f"applicables à l'API ({cons}).",
        ],
        "/securite": [
            f"Et vos contenus ne sont pas utilisés pour entraîner les modèles d'IA {essentiel}.",
            f"Aucun entraînement sur vos données : les contenus envoyés à l'IA ne sont pas utilisés pour "
            f"entraîner un modèle d'IA ({entr}). {roles} La conservation est encadrée par les conditions "
            f"applicables à l'API ({cons}). Fournisseurs, sous-traitants et lieux de calcul : voir le DPA "
            f"(annexe 3).",
        ],
        "/confidentialite": [
            "dossiers de consultation analysés (lus en entier), questions posées, données d'entreprise utiles à "
            "la rédaction (noms des salariés remplacés par des étiquettes avant tout envoi)",
            f"Intelligence artificielle. {roles} Les contenus envoyés ne sont pas utilisés pour entraîner un "
            f"modèle d'IA ({entr}). La conservation est encadrée par les conditions applicables à l'API "
            f"({cons}).{st} Lieux de calcul (et de stockage, lorsque le fournisseur s'y engage) : tableau "
            f"ci-dessus.",
            f"la signature de clauses contractuelles types (CCT / SCC) adoptées par la Commission "
            f"européenne{cct} ;",
        ],
    }


ANTHROPIC_SEUL = _attendus("Anthropic, PBC", ROLES_A, ENTR_A, CONS_A, "", "", "de notre fournisseur, Anthropic")
LES_DEUX = _attendus("Anthropic, PBC et Mistral AI", ROLES_AM, f"{ENTR_A} ; {ENTR_M}", f"{CONS_A} ; {CONS_M}", ST_M,
                     " (pour Mistral AI : celles prévues par son accord de sous-traitance)",
                     "de nos fournisseurs, Anthropic et Mistral AI (chez Mistral AI, nous avons désactivé cette "
                     "utilisation sur notre compte)")
MISTRAL_SEUL = _attendus("Mistral AI", ROLES_M, ENTR_M, CONS_M, ST_M,
                         " (pour Mistral AI : celles prévues par son accord de sous-traitance)",
                         "de notre fournisseur, Mistral AI (nous avons désactivé cette utilisation sur notre compte)")


def _texte(html: str) -> str:
    t = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", _html.unescape(t))


def _configurer(monkeypatch, nom):
    """inactif : clé Mistral seule (la production avant activation) ; ue / mondial : Mistral activé ;
    force_mistral / force_anthropic : LLM_PROVIDER, Mistral activé."""
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", CLE_ANTHROPIC)
    if nom == "inactif":
        _mistral(monkeypatch, actif=False)
    elif nom == "mondial":
        _mistral(monkeypatch, modeles=("mistral-large-2512",))     # Large 4 absent du point d'accès UE
    else:
        _mistral(monkeypatch)
    if nom == "force_mistral":
        monkeypatch.setenv("LLM_PROVIDER", "mistral")
    elif nom == "force_anthropic":
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")


def _pages(client):
    out = {}
    for p in PAGES:
        r = client.get(p)
        assert r.status_code == 200, p
        assert "{{AI_" not in r.text, f"repère non rempli dans {p}"
        out[p] = r.text
    return out


# ── 1. Le texte injecté, exact dans chaque configuration ───────────────────────────────────────────

@pytest.mark.parametrize("nom,attendus", [
    ("inactif", ANTHROPIC_SEUL),
    ("force_anthropic", ANTHROPIC_SEUL),
    ("ue", LES_DEUX),
    ("mondial", LES_DEUX),
    ("force_mistral", MISTRAL_SEUL),
])
def test_phrases_publiees_exactes_dans_chaque_configuration(client, monkeypatch, nom, attendus):
    _configurer(monkeypatch, nom)
    pages = _pages(client)
    for page, phrases in attendus.items():
        texte = _texte(pages[page])
        for phrase in phrases:
            assert phrase in texte, f"{nom} — {page} : {phrase}"
    # Les phrases d'avant ne reviennent jamais.
    for page, h in pages.items():
        t = _texte(h)
        assert "jamais utilisés pour entraîner" not in t, page
        assert "ni le nôtre, ni celui d'un tiers" not in t
        assert "contenus soumis à l'analyse (extraits de DCE" not in t
        assert "conservation éventuelle" not in t


def test_mistral_non_active_les_pages_ne_parlent_que_d_anthropic(client, monkeypatch):
    for nom in ("inactif", "force_anthropic"):
        _configurer(monkeypatch, nom)
        for page, h in _pages(client).items():
            assert "Mistral" not in h and "AELE" not in h and "trust.mistral.ai" not in h, (nom, page)
            assert "Anthropic" in h, (nom, page)


def test_mistral_force_les_pages_ne_parlent_que_de_mistral(client, monkeypatch):
    _configurer(monkeypatch, "force_mistral")
    for page, h in _pages(client).items():
        assert "Anthropic" not in h, page
        assert "Mistral AI" in h, page


def test_lieu_de_calcul_point_d_acces_ue(client, monkeypatch):
    _configurer(monkeypatch, "ue")
    p = {k: _texte(v) for k, v in _pages(client).items()}
    assert ("Anthropic : États-Unis pour le stockage, calcul possiblement hors des États-Unis (CCT) ; Mistral AI : "
            "Union européenne et AELE pour le calcul (api.eu.mistral.ai) ; sous-traitants de Mistral AI : liste "
            "publiée sur trust.mistral.ai/subprocessors (CCT)") in p["/dpa"]
    assert ("calcul dans des centres de données de l'Union européenne et de l'AELE (point d'accès régional "
            "api.eu.mistral.ai)") in p["/confidentialite"]
    assert "— calcul dans l'Union européenne et l'AELE —" in p["/confidentialite"]
    assert "sans engagement de lieu de calcul" not in p["/confidentialite"]


def test_lieu_de_calcul_point_d_acces_mondial_aucune_promesse_ue(client, monkeypatch):
    """Point d'accès mondial : aucune phrase (fixe ou injectée) ne promet un calcul dans l'UE."""
    _configurer(monkeypatch, "mondial")
    p = {k: _texte(v) for k, v in _pages(client).items()}
    assert "Mistral AI : lieu de calcul non garanti, possiblement hors Union européenne" in p["/dpa"]
    assert "point d'accès mondial (api.mistral.ai) sans engagement de lieu de calcul" in p["/confidentialite"]
    assert "— calcul possiblement hors de l'Union européenne —" in p["/confidentialite"]
    for page, t in p.items():
        assert "AELE" not in t and "api.eu.mistral.ai" not in t, page
        assert "calcul dans l'Union européenne" not in t, page


@pytest.mark.parametrize("nom", ["inactif", "ue", "mondial", "force_mistral", "force_anthropic"])
def test_stockage_jamais_promis_quand_le_tableau_ne_le_donne_pas(client, monkeypatch, nom):
    """Le tableau donne le lieu de stockage d'Anthropic (États-Unis), pas celui de Mistral AI au point
    d'accès UE (non vérifié) : la phrase fixe sous le tableau ne parle du stockage que « lorsque le
    fournisseur s'y engage », et le texte injecté n'invente aucun lieu de stockage pour Mistral AI."""
    _configurer(monkeypatch, nom)
    p = {k: _texte(v) for k, v in _pages(client).items()}
    for page in ("/dpa", "/confidentialite"):
        assert "lieux de stockage et de calcul" not in p[page].lower(), (nom, page)
        assert "Lieux de calcul (et de stockage, lorsque le fournisseur s'y engage)" in p[page].replace(
            "Les lieux de calcul", "Lieux de calcul"), (nom, page)
        if nom != "force_mistral":
            assert "États-Unis pour le stockage" in p[page], (nom, page)
    if nom in ("ue", "force_mistral", "mondial"):
        # La partie « Mistral AI » de la ligne IA de chaque tableau (jusqu'au renvoi vers ses sous-traitants).
        dpa = p["/dpa"]
        m_dpa = dpa[dpa.index("Modèle d'IA pour l'analyse et la génération de documents"):]
        m_dpa = m_dpa[m_dpa.index("Mistral AI : ") if nom != "force_mistral" else 0:]
        m_dpa = m_dpa[:m_dpa.index("sous-traitants de Mistral AI")]
        conf = p["/confidentialite"]
        m_conf = conf[conf.index("Fournisseur du modèle d'IA pour l'analyse et la génération de documents"):]
        m_conf = m_conf[m_conf.index("Mistral AI ("):]
        m_conf = m_conf[:m_conf.index("sous-traitants de Mistral AI")]
        assert "stockage" not in m_dpa, (nom, m_dpa)
        if nom == "mondial":
            # Seul fait vérifié sur le stockage chez Mistral AI : point d'accès mondial, UE par défaut.
            assert "stockage dans l'Union européenne par défaut" in m_conf, m_conf
        else:
            assert "stockage" not in m_conf, (nom, m_conf)


# ── 2. Faits vérifiés : conservation, sous-traitants, vocabulaire ──────────────────────────────────

@pytest.mark.parametrize("nom", ["ue", "mondial", "force_mistral"])
def test_mistral_actif_conservation_jusqu_a_30_jours_et_renvoi_vers_sa_liste(client, monkeypatch, nom):
    _configurer(monkeypatch, nom)
    pages = _pages(client)
    for page in PAGES:
        t = _texte(pages[page])
        assert "jusqu'à 30 jours glissants, pour la surveillance des abus" in t, page
        assert "aucune conservation" not in t.lower() and "zéro conservation" not in t.lower(), page
    for page in ("/dpa", "/confidentialite"):
        assert '<a href="https://trust.mistral.ai/subprocessors">https://trust.mistral.ai/subprocessors</a>' in pages[page]


# Noms reconstitués pour que ce fichier ne les contienne pas lui-même en toutes lettres.
_NOMS_INTERDITS = ("Core" + "Weave", "Micro" + "soft")


@pytest.mark.parametrize("nom", ["inactif", "ue", "mondial", "force_mistral", "force_anthropic"])
def test_aucun_sous_traitant_de_mistral_nomme_dans_les_pages(client, monkeypatch, nom):
    from app.main import _ai_subprocessor_fragments
    _configurer(monkeypatch, nom)
    injecte = " ".join(_ai_subprocessor_fragments().values())
    for x in _NOMS_INTERDITS + ("Cloudflare", "droit américain", "souverain", "France"):
        assert x not in injecte, (nom, x)
    for page, h in _pages(client).items():
        for x in _NOMS_INTERDITS:
            assert x not in h, (nom, page, x)
        assert "souverain " not in h and "hébergé en France" not in h and "hébergée en France" not in h


def test_aucun_sous_traitant_de_mistral_nomme_dans_le_depot():
    """Pages, sources Markdown, texte injecté (app/), documentation et tests : aucun nom."""
    fichiers = [f for d in ("app", "docs", "scripts", "tests") for f in (ROOT / d).rglob("*")
                if f.is_file() and f.suffix in (".py", ".html", ".md", ".js", ".json", ".txt", ".yml")]
    fichiers += [f for f in ROOT.glob("*.md")]
    assert any(f.name == "main.py" for f in fichiers) and any(f.name == "dpa.html" for f in fichiers)
    for f in fichiers:
        t = f.read_text(encoding="utf-8", errors="ignore")
        for x in _NOMS_INTERDITS:
            assert x not in t, f"{f.relative_to(ROOT)} nomme {x}"


# ── 3. CGV, article 3.5 : deux corrections d'exactitude, rien d'autre ──────────────────────────────

def test_cgv_3_5_questions_reprennent_le_lendemain_et_renvoi_vers_l_article_3(client):
    md = (ROOT / "docs" / "legal" / "cgv.md").read_text(encoding="utf-8")
    art = md[md.index("### 3.5. Essai gratuit"):md.index("## 4. Paiement")]
    assert ("les fonctions concernées sont suspendues jusqu'à la souscription d'une formule payante (ou, pour les "
            "quinze questions par jour, jusqu'au lendemain) ;") in art
    assert "Ces limites ne s'appliquent pas aux formules payantes, régies par l'article 3." in art
    assert "régies par l'article 3.1" not in md
    # Le renvoi est juste : les formules payantes sont décrites en tête de l'article 3 (avant le 3.1,
    # qui ne traite que de la facturation au-delà du quota).
    tete = md[md.index("## 3. Offres, prix et facturation à l'usage"):md.index("### 3.1.")]
    assert "**formules payantes**" in tete and "| **Pro** |" in tete and "| **Business** |" in tete
    html = _texte(client.get("/cgv").text)
    assert "(ou, pour les quinze questions par jour, jusqu'au lendemain)" in html
    assert "aux formules payantes, régies par l'article 3. À la fin de l'essai" in html


def test_cgv_le_reste_inchange_et_structure_des_pages_intacte():
    """Seules les phrases visées ont changé : titres et numérotation des pages juridiques identiques."""
    cgv = (ROOT / "docs" / "legal" / "cgv.md").read_text(encoding="utf-8")
    titres = re.findall(r"^#{1,4} .*$", cgv, re.M)
    assert titres[:3] == ["# Conditions Générales de Vente et d'Utilisation (CGV/CGU)", "## Préambule", "## 1. Objet"]
    assert "### 3.5. Essai gratuit" in titres and "### 3.1. Facturation à l'usage (au-delà du quota)" in titres
    conf = (ROOT / "docs" / "legal" / "politique-confidentialite.md").read_text(encoding="utf-8")
    assert [t for t in re.findall(r"^## (\d+)\.", conf, re.M)] == [str(i) for i in range(1, 14)]
    sec = (ROOT / "app" / "static" / "legal" / "securite.html").read_text(encoding="utf-8")
    assert re.findall(r"<h2>(\d+)\.", sec) == [str(i) for i in range(1, 7)]
    dpa = (ROOT / "app" / "static" / "legal" / "dpa.html").read_text(encoding="utf-8")
    assert "<h2>Annexe 2 — Mesures techniques et organisationnelles de sécurité</h2>" in dpa
    assert "<h2>Annexe 3 — Liste des sous-traitants ultérieurs</h2>" in dpa
