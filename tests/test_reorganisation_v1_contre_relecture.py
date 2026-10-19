"""
Réorganisation de l'interface — vague 1, CONTRE-RELECTURE de la fin de vague (contrat : docs/REORGANISATION_V1.md, § 4.8).

Chaque test reproduit une remarque qui échouait sur 8adfae0 :
- carte de « Mes marchés » : la note « Seul 34 % » / « À plusieurs 100 % » se coupait sur 2 ou 3 lignes à 1 280 px
  (le « % » seul sur sa ligne) ; elle ne se coupe plus, elle passe entière à la ligne si elle ne tient pas ;
- pièces de réponse de la démo renommées : le PDF déjà rangé (stockage persistant de la production) gardait l'ancien
  titre (« Mémoire technique — … », « DPGF — … ») ; chaque PDF de la démo est maintenant rangé sous une clé liée à son
  titre ;
- la consigne du SIRET et les autres textes qui renvoyaient à l'ancien « profil entreprise » (écran absent du menu)
  disent « Mon entreprise, onglet « Identité » ».

Aucun appel réseau : lecture des sources, routes appelées par le client de test, stockage local des tests.
"""
import hashlib
import re

import pytest

from tests.test_reorganisation_v1_relecture import (CSS, HTML, INV, JS, LANDING, STATIC, _constantes, _db,
                                                    _fichiers_app, _pdf_text)
from tests.textes_visibles import mots_bannis, textes_html, textes_js
from tests.zones import zone


@pytest.fixture(autouse=True)
def _sans_reseau(monkeypatch):
    """Aucun appel réseau : registres simulés absents (comme tests/test_reseau_partenaires.py), et toute connexion
    sortante refusée (GET /api/reseau/profil interroge sinon le registre officiel pour le SIRET de la démo)."""
    import socket
    import app.routers.reseau as R
    import app.services.partner_network as pn
    import app.services.registre as registre

    def refuse(*a, **k):
        raise OSError("réseau coupé pendant ce test")
    monkeypatch.setattr(registre, "lookup_company", lambda q, timeout=12: None)
    monkeypatch.setattr(pn, "_http_get", refuse)
    monkeypatch.setattr(R, "_sirene_fallback", lambda trade, dept, warnings: [])
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    for d in (R._VERIFY_LAST, R._LOOKUP_CACHE):
        d.clear()


# ═══ Carte de « Mes marchés » : la note ne se coupe jamais ═════════════════════════════════════════════════════

def _regle(sel: str) -> dict:
    m = re.search(r"(?m)^" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"règle {sel} absente de styles.css"
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in m.group(1).split(";") if ":" in d)}


def test_la_note_de_la_carte_ne_se_coupe_jamais():
    """Sur 8adfae0, `.kcard .sc` (élément d'une ligne flex, colonnes de 214 px) rétrécissait jusqu'à son mot le plus
    long : « Seul 34 / % », « À / plusieurs / 100 % » (mesuré dans un navigateur, 3 cartes sur 7 de la démo). La note
    reste d'un seul tenant ; la ligne passe à la ligne entre l'acheteur et la note, la note reste alignée à droite."""
    sc, me = _regle(".kcard .sc"), _regle(".kcard .me")
    assert sc.get("white-space") == "nowrap", sc
    assert me.get("display") == "flex" and me.get("flex-wrap") == "wrap", me
    assert sc.get("margin-left") == "auto", sc
    # La note de la carte est bien dans ce conteneur, et c'est le libellé court de la décision 8.
    carte = zone(HTML, "vue-pipeline")
    assert '<div class="me">{{ p.client||\'—\' }}<span v-if="scoreCourt(p)" class="sc"' in carte
    assert carte.count("scoreCourt(p)") == 2


# ═══ Démo : chaque PDF porte le nom de sa pièce, même si le stockage est ancien ════════════════════════════════

# Le stockage de la production avant ce correctif : les deux pièces rangées sous leurs anciennes clés, avec les titres
# du code d'avant 8adfae0 (_put ne réécrit jamais une clé déjà stockée).
ANCIENS_PDF = {"demo/memoire_methodologie.pdf": "Mémoire technique — méthodologie étanchéité",
               "demo/dpgf.pdf": "DPGF — bordereau de décomposition des prix"}


def _pieces_de_la_demo(db, uid):
    from app.models import ContributionPiece, Document
    docs = [(d.name, d.file_key) for d in db.query(Document).filter(Document.user_id == uid).all()]
    docs += [(p.name, p.file_key) for p in db.query(ContributionPiece).filter(ContributionPiece.owner_id == uid).all()]
    return [(n, k) for n, k in docs if (k or "").startswith("demo/") and k.endswith(".pdf")]


def test_le_pdf_de_chaque_piece_de_la_demo_porte_son_nom_meme_si_le_stockage_est_ancien():
    from app.models import User
    from app.services.demo_seed import DEMO_EMAIL, _demo_pdf, ensure_demo
    from app.services.storage import get_storage
    st = get_storage()
    for k, titre in ANCIENS_PDF.items():
        st.save(k, _demo_pdf(titre), "application/pdf")
    db = _db()
    try:
        ensure_demo(db, force=True)
        uid = db.query(User).filter(User.email == DEMO_EMAIL).first().id
        pieces = _pieces_de_la_demo(db, uid)
        noms = {n for n, _k in pieces}
        assert {"Dossier de présentation — méthodologie étanchéité",
                "Tableau de prix — décomposition du prix global et forfaitaire"} <= noms
        # 11 pièces de l'entreprise fictive (le dossier de Toiture devient son .zip, clé liée au contenu), 6 de Breizh.
        assert len(pieces) >= 17 and sum(1 for n, _k in pieces if "Breizh" in n) == 6, pieces
        for nom, cle in pieces:
            texte = " ".join(_pdf_text(st.load(cle)).split())
            assert " ".join(nom[:80].split()) in texte, (nom, cle, texte[:120])
            assert not mots_bannis(texte), (nom, cle, mots_bannis(texte))
    finally:
        db.close()
        for k in ANCIENS_PDF:
            st.delete(k)


def test_la_cle_d_une_piece_de_la_demo_suit_son_titre():
    """Un nom de pièce changé dans demo_seed.py change sa clé : le PDF est rangé de nouveau, avec le nouveau titre.
    Relancer la démo sans rien changer ne range aucun fichier."""
    from app.models import User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    from app.services.storage import get_storage
    db = _db()
    try:
        ensure_demo(db, force=True)
        uid = db.query(User).filter(User.email == DEMO_EMAIL).first().id
        avant = sorted(_pieces_de_la_demo(db, uid))
        cles = set(get_storage().list_keys("demo/"))
        ensure_demo(db, force=True)
        assert sorted(_pieces_de_la_demo(db, uid)) == avant
        assert set(get_storage().list_keys("demo/")) == cles
    finally:
        db.close()
    for nom, cle in avant:
        empreinte = hashlib.sha256((nom + "\0").encode("utf-8")).hexdigest()[:12]
        assert cle.endswith("_" + empreinte + ".pdf"), (nom, cle)
        assert not mots_bannis(cle.replace("_", " ")), cle      # la clé apparaît dans l'adresse d'un téléchargement
    assert not set(ANCIENS_PDF) & {c for _n, c in avant}


# ═══ « Profil entreprise » : l'écran s'appelle « Mon entreprise », onglet « Identité » ═══════════════════════════

_PROFIL = re.compile(r"profil\s+(?:d['’]\s*|de\s+l['’]\s*)?entreprise", re.I)
# (fichier) → raison. Toute nouvelle exception se justifie ici ET au contrat (§ 4.8).
PROFIL_GARDES = {
    "app/services/i18n_data.py": "dictionnaire de traduction indexé sur les anciens libellés",
    "app/services/analysis.py": "consigne envoyée à l'IA (« PROFIL DE L'ENTREPRISE CANDIDATE »), jamais affichée",
}


def test_aucun_profil_entreprise_dans_les_textes_du_serveur():
    """Sur 8adfae0 : « SIRET à 14 chiffres renseigné dans le profil entreprise » (Mon profil partenaire › Publication,
    visible dans la démo), « Renseignez un SIRET … dans votre profil entreprise », « (profil entreprise) », « Complétez
    votre profil entreprise » (formulaires officiels, export), et les messages du réseau quand le SIRET change."""
    fautes = []
    for p in _fichiers_app():
        rel = str(p.relative_to(STATIC.parent.parent))
        if rel in PROFIL_GARDES:
            continue
        for ln, t in _constantes(p.read_text(encoding="utf-8")):
            if _PROFIL.search(t):
                fautes.append(f"{rel}:{ln} {t[:110]!r}")
    assert not fautes, "\n".join(fautes)


def test_aucun_profil_entreprise_dans_les_pages_et_scripts_servis():
    """Pages et scripts servis : seul l'ancien nom de l'onglet « Identité » (bulle de transition, `ancien:`) le dit."""
    anciens = set(re.findall(r'ancien: "([^"]+)"', JS))
    assert "Profil de l'entreprise" in anciens
    fautes = []
    sources = {"app.html": textes_html(HTML), "invite.html": textes_html(INV), "landing.html": textes_html(LANDING),
               "app.js": textes_js(JS),
               "redaction-partenaire.js": textes_js((STATIC / "redaction-partenaire.js").read_text(encoding="utf-8"))}
    for f, textes in sources.items():
        for ln, t in textes:
            if _PROFIL.search(t) and t not in anciens:
                fautes.append(f"{f}:{ln} {t.strip()[:110]!r}")
    assert not fautes, "\n".join(fautes)


def test_la_consigne_du_siret_dit_mon_entreprise_onglet_identite(client, auth):
    """De bout en bout, avec un compte dont l'entreprise n'a pas de SIRET : la condition de publication, la
    vérification et la demande de publication disent où le renseigner aujourd'hui."""
    h = auth["headers"]
    ici = "Mon entreprise, onglet « Identité »"
    conds = {c["key"]: c for c in client.get("/api/reseau/profil", headers=h).json()["publication"]["conditions"]}
    assert conds["siret"]["label"] == "SIRET à 14 chiffres renseigné dans " + ici and conds["siret"]["ok"] is False
    r = client.put("/api/reseau/profil", headers=h, json={
        "metiers": ["electricite"], "departements": ["29"], "roles_acceptes": ["cotraitant"],
        "disponibilite": "disponible", "lot_max_eur": 250000, "presentation": "Électricité générale."})
    assert r.status_code == 200, r.text
    r = client.post("/api/reseau/profil/verifier", headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "siret_invalide", r.text
    assert ici in r.json()["detail"]["message"]
    r = client.post("/api/reseau/profil/publier", headers=h, json={"accepte": True})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "siret_invalide", r.text
    assert r.json()["detail"]["message"] == f"Un SIRET à 14 chiffres est requis ({ici})."


def test_la_condition_du_siret_dans_la_demo(client):
    """Partenaires › Réseau Adjugo › Mon profil partenaire › Publication, dans la démo (pitch)."""
    from app.services.demo_seed import ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
    finally:
        db.close()
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    conds = {c["key"]: c for c in client.get("/api/reseau/profil", headers=h).json()["publication"]["conditions"]}
    assert conds["siret"]["label"] == "SIRET à 14 chiffres renseigné dans Mon entreprise, onglet « Identité »"
    assert conds["siret"]["ok"] is True


def test_les_autres_renvois_disent_le_chemin_d_aujourd_hui():
    from app.services import partner_network as pn
    from app.services.dce_scoring import score_dce
    ici = "Mon entreprise, onglet « Identité »"
    # Formulaires officiels et export : sans entreprise renseignée.
    for rel in ("app/routers/cerfa.py", "app/routers/export_dossier.py"):
        assert "Renseignez votre entreprise dans " + ici + "." in [t for _l, t in _constantes(
            (STATIC.parent.parent / rel).read_text(encoding="utf-8"))], rel
    # SIRET changé dans Mon entreprise : le message dit « votre entreprise », sans ancien nom d'écran.
    class P:
        visible, siret, siren, validation_status = True, "11111111100011", "111111111", ""
    for visible, statut in ((True, ""), (False, pn.VALIDATION_PENDING), (False, "")):
        p = P()
        p.visible, p.validation_status = visible, statut
        msg = pn.sync_siret(p, "22222222200022")
        assert msg and msg.startswith("Le SIRET de votre entreprise a changé") and not _PROFIL.search(msg), msg
    # Adéquation métier sans activité renseignée : où l'indiquer.
    bd = score_dce({"intitule_marche": "Travaux"}, {}, {})["breakdown"]
    metier = next(c for c in bd if c["key"] == "metier")
    assert metier["detail"] == "Activité non renseignée (vos spécialités dans Mon entreprise, onglet « Mes critères »)"
    # Onboarding de l'accueil : le jalon dit ce qu'il attend (nom et SIRET), et il est traduit (décision 16).
    assert 'label: "Renseignez le nom et le SIRET de votre entreprise", view: "company"' in JS
    import json
    import subprocess
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", "global.window={}; require(process.argv[1]); "
                        "console.log(JSON.stringify(window.ADJUGO_I18N))", str(STATIC / "i18n.js")],
                       capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout)
    k = "Renseignez le nom et le SIRET de votre entreprise"
    assert d["nl"].get(k) and d["es"].get(k)
