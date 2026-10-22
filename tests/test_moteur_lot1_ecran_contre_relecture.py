"""Contre-relecture de la revue de la partie écran du lot 1 « Dire juste » (docs/MOTEUR_LOT1.md, section « Écran »,
« Contre-relecture » ; bilan docs/MISE_EN_LIGNE_22_10.md, section 5). Chaque test échoue sur 4701fa9 (la revue de la
partie écran), sur le défaut qu'il couvre.

  CR1. La ligne R5 du tableau « Revue » du contrat citait une tâche des premiers pas qui n'existe pas, « Dire ce que
       vous cherchez » ; son titre est « Dire ce que vous faites et où » (PP_TACHES, app.js).
  CR2. Le test du courriel d'invitation échouait au hasard : le jeton du lien (secrets.token_urlsafe(32)) peut contenir
       « AO », « GO » ou « DPGF » entre deux caractères qui ne sont pas des lettres, et la garde des mots bannis le
       lisait comme un mot du courriel. Le jeton est retiré avant la garde ; l'adresse écrite par Adjugo reste lue.

Sans réseau : courriels relevés (rien ne part), registres simulés, aucune IA.
"""
import pathlib
import re
import secrets
import types
import uuid

import pytest

from tests.test_convention_groupement import _invite, _project, _set_company
from tests.test_reorganisation_v2b_courriel_invitation import _assert_courriel_propre, _base, _visible, courriels  # noqa: F401
from tests.test_reseau_partenaires import reg  # noqa: F401  (registres simulés, fixture autouse)
from tests.textes_visibles import mots_bannis
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
JS = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "app.html").read_text(encoding="utf-8")


def _plat(s: str) -> str:
    return " ".join(s.split())


def _taches() -> dict:
    """{clé: titre} des tâches de « Vos premiers pas », lues dans app.js (PP_TACHES)."""
    i = JS.index("const PP_TACHES = {")
    bloc = JS[i:JS.index("\n};", i)]
    return dict(re.findall(r'^\s*(\w+): \{ titre: "([^"]+)"', bloc, re.M))


# ═══ CR1. Le contrat nomme la tâche des premiers pas par son titre ═════════════════════════════════════════════════

def test_cr1_le_contrat_nomme_les_taches_des_premiers_pas_par_leur_titre():
    taches = _taches()
    assert taches["dire"] == "Dire ce que vous faites et où"
    assert taches["suivre"] == "Ajouter 3 marchés à Mes marchés"
    # La tâche « dire » est celle que compte ce_que_je_cherche_dit (spécialités ou codes CPV), comme le dit R5.
    pm = (ROOT / "app" / "services" / "prise_en_main.py").read_text(encoding="utf-8")
    assert "dit = ce_que_je_cherche_dit(db, owner)" in pm and 'out.append({"k": "dire",' in pm
    crit = (ROOT / "app" / "routers" / "criteria_v2.py").read_text(encoding="utf-8")
    assert '"metier": txt(c.specialites) or txt(c.codes_cpv)' in crit

    contrat = _plat((ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8"))
    bilan = _plat((ROOT / "docs" / "MISE_EN_LIGNE_22_10.md").read_text(encoding="utf-8"))
    # Chaque tâche nommée « la tâche « … » » dans ces deux documents existe : par son titre, ou par sa clé.
    for nom, doc in (("MOTEUR_LOT1.md", contrat), ("MISE_EN_LIGNE_22_10.md", bilan)):
        for x in re.findall(r"tâches? « ([^»]+?) »", doc):
            assert x in taches.values() or x in taches, (nom, x)
    r5 = contrat[contrat.index("| **R5** (remarque 5, mineur) |"):]
    r5 = r5[:r5.index("| **R6**")]
    assert "la tâche « Dire ce que vous faites et où » des premiers pas" in r5
    assert "la carte montre la tâche « Ajouter 3 marchés à Mes marchés »" in r5
    # Le nom erroné n'est plus écrit que dans la ligne CR1 de la contre-relecture, qui le cite comme la faute relevée.
    faux = "Dire ce que vous cherchez"
    assert faux not in r5 and faux not in bilan and contrat.count(faux) == 1
    cr1 = contrat[contrat.index("| **CR1** (mineur) |"):]
    assert faux in cr1[:cr1.index("| **CR2**")]

    # Le fond du rejet partiel de R5 reste vrai : sous la demande du métier, la carte rappelle « suivre », pas « dire ».
    trouver = zone(HTML, "vue-sourcing")
    i = trouver.index('class="trouver-manque-metier small"')
    carte = trouver[i:trouver.index("<!-- 0 résultat après recherche", i)]
    assert "ppRappel('suivre')" in carte and "ppRappel('dire')" not in carte

    # Le contrat et le bilan disent la contre-relecture.
    brut = (ROOT / "docs" / "MOTEUR_LOT1.md").read_text(encoding="utf-8")
    assert "### Contre-relecture" in brut[brut.index("## Écran"):]
    ecran = contrat[contrat.index("## Écran"):]
    for x in ("tests/test_moteur_lot1_ecran_contre_relecture.py", "Dire ce que vous faites et où",
              "secrets.token_urlsafe(32)"):
        assert x in ecran, x
    assert "Contre-relecture de la partie écran du lot 1 (22/10/2026)" in bilan
    assert "tests/test_moteur_lot1_ecran_contre_relecture.py" in bilan


# ═══ CR2. Le jeton tiré au hasard du lien d'invitation ═════════════════════════════════════════════════════════════

# Jetons au format de secrets.token_urlsafe(32) (43 caractères de A-Z, a-z, 0-9, « - » et « _ ») qui contiennent un
# mot banni lu par la garde : le premier est celui de la contre-relecture (échec réel de la suite SQLite).
JETONS = ["cbEYD5O-JoWndmWmCHW3r8AO7HS0hwCKypnxKRyZLro",
          "Qx3_GO-a9b8c7d6e5f4g3h2i1j0kLmNoPqRsTuVwXyZ",
          "zz9dpgf1Hk2Lm3Nn4Pq5Rr6St7Uv8Wx9Yz0Ab1Cd2Ef"]


def test_cr2_le_jeton_du_lien_n_est_pas_lu_comme_un_mot_du_courriel():
    from app.services.email_invitation import invitation
    for j in JETONS:
        # Un jeton de la forme de ceux du code, que la garde, sans le retrait du jeton, lit comme un mot banni.
        assert len(j) == len(secrets.token_urlsafe(32)) == 43 and re.fullmatch(r"[A-Za-z0-9_-]{43}", j), j
        u = "https://adjugo.pro/invite/" + j
        assert mots_bannis(u), j
        _assert_courriel_propre(invitation(chef="A SARL", marche="M", url=u), u)


def test_cr2_la_garde_lit_toujours_ce_qu_ecrit_adjugo():
    """Seul le jeton est retiré : un mot banni dans le texte, ou dans la partie fixe du lien, fait toujours échouer."""
    from app.services.email_invitation import invitation
    u = "https://adjugo.pro/invite/" + JETONS[0]
    c = invitation(chef="A SARL", marche="M", url=u)
    _assert_courriel_propre(c, u)
    for champ in ("texte", "objet"):
        faux = dict(c, **{champ: c[champ] + " Votre AO"})
        with pytest.raises(AssertionError, match=r"\['AO'\]"):
            _assert_courriel_propre(faux, u)
    faux = dict(c, html=c["html"].replace("</body>", "<p>Votre consortium</p></body>", 1))
    assert "Votre consortium" in _visible(faux["html"])
    with pytest.raises(AssertionError, match=r"\['consortium'\]"):
        _assert_courriel_propre(faux, u)
    u2 = "https://adjugo.pro/cotraitance/" + JETONS[0]                  # partie fixe du lien : lue
    with pytest.raises(AssertionError, match=r"\['co-traitant'\]"):
        _assert_courriel_propre(invitation(chef="A SARL", marche="M", url=u2), u2)


def test_cr2_invitation_de_bout_en_bout_avec_un_jeton_qui_contient_ao(client, auth, courriels, monkeypatch):  # noqa: F811
    """Le parcours du test d'origine (route, base, courriel relevé), le jeton fixé : il contient « …8AO7… »."""
    from app.routers import invites
    jeton = uuid.uuid4().hex[:20] + "-8AO7_" + uuid.uuid4().hex[:17]  # unique : la colonne token l'est
    assert len(jeton) == 43 and mots_bannis("/invite/" + jeton) == ["AO"]
    monkeypatch.setattr(invites, "secrets", types.SimpleNamespace(token_urlsafe=lambda n=32: jeton,
                                                                  randbelow=secrets.randbelow))
    h = auth["headers"]
    _set_company(auth["email"], name="Breizh Couverture")
    pid = _project(client, h, name=f"Réfection de la toiture {uuid.uuid4().hex[:4]}")
    inv = _invite(client, h, pid, "Breizh Désamiantage", recipient="cr2@desamiantage.example")
    assert inv["token"] == jeton and inv["emailed"] is True
    (c,) = [x for x in courriels if x["to"] == "cr2@desamiantage.example"]
    url = _base() + "/invite/" + jeton
    assert url in c["texte"] and mots_bannis(c["texte"]) == ["AO"]     # sans le retrait, la garde échouait
    _assert_courriel_propre(c, url, interdits=(auth["email"], "cr2@desamiantage.example"))
    assert client.get("/invite/" + jeton).status_code == 200
