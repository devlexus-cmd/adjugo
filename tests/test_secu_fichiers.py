"""Non-régression sécurité — groupe « fichiers » (audit cyber oct. 2026).

Chaque test rejoue l'exploit d'origine (scratchpad cyber/) et vérifie qu'il échoue :
  1. bombe de décompression ZIP (+ DOCX, ZIP imbriqués, bzip2, en-tête menteur) ;
  2. uploads lus en entier avant le contrôle de taille ;
  4. SSRF via la source_url d'un AO (fetch_dce) ;
 14. OCR / extraction PDF : toutes les pages rendues avant plafond.
Aucun réseau réel : DNS et HTTP sont simulés (httpx.MockTransport).
"""
import io
import os
import re
import sys
import types
import zipfile
import tracemalloc

import httpx
import pytest

from app.services import analysis
from app.services.analysis import extract_dce_text

MB = 1024 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Fabriques de fichiers ────────────────────────────────────────────────────

def _text_pdf(text: str, pages: int = 1) -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        y = 800
        for line in (text + f" (page {i + 1})").split("\n"):
            c.drawString(40, y, line)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


def _blank_pdf(pages: int, width: float = 595, height: float = 842) -> bytes:
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _docx(text: str) -> bytes:
    import docx
    d = docx.Document()
    for para in text.split("\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _zip(members: dict, compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _bomb_zip(name: str = "CCTP.txt", size: int = 200 * MB) -> bytes:
    """Exploit d'origine : un membre texte de 200 Mo de « A » (~200 Ko compressé)."""
    buf = io.BytesIO()
    chunk = b"A" * MB
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        with z.open(name, "w", force_zip64=True) as fh:
            for _ in range(size // MB):
                fh.write(chunk)
    return buf.getvalue()


def _peak_mb(fn):
    tracemalloc.start()
    try:
        out = fn()
    except Exception as e:     # noqa: BLE001 — on mesure aussi les refus
        out = e
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return out, peak / MB


RC = "REGLEMENT DE LA CONSULTATION\nCriteres : prix 40 %, valeur technique 60 %.\nDate limite 12/12/2026."
CCAP = "CAHIER DES CLAUSES ADMINISTRATIVES\nPenalites de retard : 1/1000 par jour calendaire."
CCTP = "CAHIER DES CLAUSES TECHNIQUES\nRefection de la toiture du gymnase municipal, zinc."
DPGF = "poste;designation;quantite\n1;Depose couverture;850 m2\n2;Pose zinc;850 m2\n"


# ── Faille 1 : bombe de décompression ZIP ────────────────────────────────────

def test_zipbomb_membre_geant_refuse_sans_decompression():
    bomb = _bomb_zip()
    assert len(bomb) < 2 * MB            # bien sous le plafond d'upload
    out, peak = _peak_mb(lambda: extract_dce_text("dossier.zip", bomb, max_chars=400000))
    assert isinstance(out, ValueError) and "trop volumineux" in str(out)
    assert peak < 30, f"pic mémoire {peak:.0f} Mo (avant correctif : ~600 Mo)"


def test_zipbomb_entete_menteur_borne_quand_meme():
    """Variante : le répertoire central annonce 1 Ko alors que le flux en fait 50 Mo."""
    bomb = bytearray(_bomb_zip(size=50 * MB))
    # Réécrit la taille décompressée déclarée dans le répertoire central.
    i = bomb.find(b"PK\x01\x02")
    bomb[i + 24:i + 28] = (1024).to_bytes(4, "little")   # taille décompressée déclarée
    out, peak = _peak_mb(lambda: extract_dce_text("dossier.zip", bytes(bomb)))
    assert isinstance(out, ValueError)
    assert peak < 30, f"pic mémoire {peak:.0f} Mo"


def test_zip_budget_cumule_et_plafond_par_membre(monkeypatch):
    monkeypatch.setattr(analysis, "ZIP_MEMBER_MAX_BYTES", 1 * MB)
    monkeypatch.setattr(analysis, "ZIP_TOTAL_MAX_BYTES", 3 * MB)
    reads = []
    real = analysis._read_member_limited

    def spy(zf, info, limit):
        data = real(zf, info, limit)
        reads.append(len(data) if data is not None else None)
        return data
    monkeypatch.setattr(analysis, "_read_member_limited", spy)
    # 6 « PDF » de 0,9 Mo illisibles : sans budget, les 6 seraient décompressés.
    members = {f"plan_{i}.pdf": os.urandom(900 * 1024) for i in range(6)}
    members["gros.txt"] = b"B" * (2 * MB)            # > plafond par membre
    with pytest.raises(ValueError):
        extract_dce_text("dce.zip", _zip(members, zipfile.ZIP_STORED))
    lus = sum(r for r in reads if r)
    assert lus <= 3 * MB, f"{lus} octets décompressés malgré un budget de 3 Mo"


def test_zip_imbrique_un_niveau_ok_deux_niveaux_refuse():
    inner = _zip({"CCTP.txt": CCTP})
    ok = extract_dce_text("dce.zip", _zip({"RC.txt": RC, "pieces_techniques.zip": inner}))
    assert "Refection de la toiture" in ok and "REGLEMENT" in ok
    deep = _zip({"niveau1.zip": _zip({"niveau2.zip": _zip({"CCTP.txt": CCTP})})})
    with pytest.raises(ValueError, match="imbriquée"):
        extract_dce_text("dce.zip", deep)


def test_zip_bzip2_refuse():
    """bzip2/LZMA décompressent un bloc entier sans borne de sortie → refusés."""
    z = _zip({"CCTP.txt": CCTP * 50}, zipfile.ZIP_BZIP2)
    with pytest.raises(ValueError):
        extract_dce_text("dce.zip", z)


def test_zip_trop_d_entrees_refuse(monkeypatch):
    monkeypatch.setattr(analysis, "ZIP_MAX_ENTRIES", 50)
    z = _zip({f"f{i}.txt": "x" for i in range(60)})
    with pytest.raises(ValueError, match="trop de fichiers"):
        extract_dce_text("dce.zip", z)


def test_docx_bombe_refuse():
    """Un .docx est une archive : un document.xml géant est refusé avant python-docx."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_docx(CCTP))) as src, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        with dst.open("word/bomb.xml", "w", force_zip64=True) as fh:
            for _ in range(100):
                fh.write(b" " * MB)
    out, peak = _peak_mb(lambda: extract_dce_text("CCTP.docx", buf.getvalue()))
    assert isinstance(out, ValueError) and "Word" in str(out)
    assert peak < 30


def test_vrai_dce_zip_toujours_analyse():
    """Usage légitime : RC + CCAP (PDF) + CCTP (Word) + DPGF (CSV) + plan lourd."""
    dce = _zip({
        "01_RC.pdf": _text_pdf(RC),
        "02_CCAP.pdf": _text_pdf(CCAP, pages=3),
        "03_CCTP.docx": _docx(CCTP),
        "04_DPGF.csv": DPGF,
        "05_plans/plan_masse.pdf": os.urandom(25 * MB),   # plan scanné/incompressible
    })
    assert 25 * MB < len(dce) < 50 * MB
    txt = extract_dce_text("DCE.zip", dce, max_chars=120000)
    for attendu in ("REGLEMENT DE LA CONSULTATION", "Penalites de retard",
                    "Refection de la toiture", "Pose zinc"):
        assert attendu in txt


def test_vrai_dce_30mo_via_route_knowledge(client, auth):
    dce = _zip({"RC.pdf": _text_pdf(RC + "\n" + CCAP), "CCTP.docx": _docx(CCTP),
                "plans.pdf": os.urandom(28 * MB)}, zipfile.ZIP_STORED)
    r = client.post("/api/knowledge/upload", headers=auth["headers"],
                    files={"file": ("DCE.zip", dce, "application/zip")}, data={"kind": "autre"})
    assert r.status_code == 200, r.text


def test_zipbomb_via_route_renvoie_422(client, auth):
    r = client.post("/api/knowledge/upload", headers=auth["headers"],
                    files={"file": ("dossier.zip", _bomb_zip(), "application/zip")})
    assert r.status_code == 422
    assert "trop volumineux" in r.json()["detail"]


# ── Faille 2 : uploads lus en entier avant le contrôle de taille ─────────────

class _CountingFile(io.RawIOBase):
    """Flux « infini » qui compte ce que le serveur lit réellement."""
    def __init__(self, total):
        self.total, self.pos = total, 0

    def readable(self):
        return True

    def readinto(self, b):
        n = min(len(b), self.total - self.pos)
        b[:n] = b"x" * n
        self.pos += n
        return n


def test_lecture_bornee_sync_et_async():
    import asyncio
    from fastapi import HTTPException, UploadFile
    from app.core.uploads import aread_upload_limited, read_upload_limited

    f = _CountingFile(500 * MB)
    with pytest.raises(HTTPException) as e:
        read_upload_limited(UploadFile(file=io.BufferedReader(f)), 2 * MB)
    assert e.value.status_code == 413 and f.pos <= 3 * MB

    g = _CountingFile(500 * MB)
    with pytest.raises(HTTPException) as e:
        asyncio.run(aread_upload_limited(UploadFile(file=io.BufferedReader(g)), 2 * MB))
    assert e.value.status_code == 413 and g.pos <= 3 * MB


def test_aucune_route_ne_lit_un_upload_sans_borne():
    for rel in ("app/routers/documents.py", "app/routers/sourcing.py",
                "app/routers/knowledge.py", "app/routers/amont.py", "app/routers/dce.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert not re.search(r"file\.file\.read\(\)|await file\.read\(\)", src), rel


def test_coffre_fort_413_au_dela_de_la_limite(client, auth):
    from app.core.config import get_settings
    big = b"%PDF-" + b"0" * (get_settings().MAX_UPLOAD_MB * MB + 10)
    r = client.post("/api/documents/", headers=auth["headers"],
                    files={"file": ("gros.pdf", big, "application/pdf")})
    assert r.status_code == 413
    assert "volumineux" in r.json()["detail"]


def test_routes_dossier_413_au_dela_de_50mo(client, auth, monkeypatch):
    big = b"PK" + b"0" * (50 * MB + 10)
    # /api/amont/analyze-upload refuse tout (404, rien lu) tant que « Projets à venir » est éteint (moteur, lot 1,
    # point 7) : la lecture bornée se vérifie veille ouverte.
    monkeypatch.setenv("PROJETS_A_VENIR", "1")
    # (/api/knowledge/memoire-upload ne lit plus de fichier : le dossier se rédige dans l'atelier.)
    for url, data in (("/api/knowledge/upload", {}), ("/api/amont/analyze-upload", {})):
        r = client.post(url, headers=auth["headers"], data=data,
                        files={"file": ("dce.zip", big, "application/zip")})
        assert r.status_code == 413, (url, r.status_code)


# ── Faille 4 : SSRF ──────────────────────────────────────────────────────────

@pytest.fixture
def fake_dns(monkeypatch):
    """DNS simulé (aucune requête réelle) : boamp.fr → IP publique."""
    from app.core import safe_fetch
    table = {"www.boamp.fr": ["51.91.0.10"], "boamp.fr": ["51.91.0.10"]}
    monkeypatch.setattr(safe_fetch, "_resolve", lambda h: table.get(h, ["51.91.0.99"]))
    return table


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1/", "https://[::1]/", "https://localhost/",
    "http://www.boamp.fr/avis/detail/24-1",            # http refusé
    "https://www.boamp.fr.evil.com/x", "https://evilboamp.fr/x",
    "https://user:pw@www.boamp.fr/x", "https://www.boamp.fr:8443/x",
    "file:///etc/passwd", "gopher://www.boamp.fr/", "javascript:alert(1)", "",
])
def test_validate_url_refuse(url, fake_dns):
    from app.core.safe_fetch import UnsafeURL, validate_url
    with pytest.raises(UnsafeURL):
        validate_url(url)


def test_validate_url_refuse_dns_vers_ip_privee(fake_dns):
    from app.core.safe_fetch import UnsafeURL, validate_url
    for ip in ("10.0.0.5", "169.254.169.254", "127.0.0.1", "::ffff:192.168.1.1", "fd00::1"):
        fake_dns["www.boamp.fr"] = [ip]
        with pytest.raises(UnsafeURL):
            validate_url("https://www.boamp.fr/avis/detail/24-1")
    fake_dns["www.boamp.fr"] = ["51.91.0.10"]
    assert validate_url("https://www.boamp.fr/avis/detail/24-1")


def _mock_client(handler, seen):
    def _h(request):
        seen.append(str(request.url))
        return handler(request)
    return httpx.Client(transport=httpx.MockTransport(_h), follow_redirects=False)


def test_safe_get_redirection_vers_interne_bloquee(fake_dns):
    from app.core.safe_fetch import UnsafeURL, safe_get
    seen = []

    def h(req):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    with pytest.raises(UnsafeURL):
        safe_get("https://www.boamp.fr/avis/detail/24-1", client=_mock_client(h, seen))
    assert seen == ["https://www.boamp.fr/avis/detail/24-1"]


def test_safe_get_reponse_bornee(fake_dns):
    from app.core.safe_fetch import ResponseTooLarge, safe_get
    seen = []
    with pytest.raises(ResponseTooLarge):
        safe_get("https://www.boamp.fr/x.pdf", max_bytes=1000,
                 client=_mock_client(lambda r: httpx.Response(200, content=b"x" * 5000), seen))


def _patch_boamp_client(monkeypatch, handler, seen):
    """Remplace httpx.Client DANS boamp uniquement (zéro connexion réelle)."""
    import app.sourcing.sources.boamp as boamp

    def factory(*a, **k):
        seen_flags.append(k.get("follow_redirects"))
        k["transport"] = httpx.MockTransport(lambda r: (seen.append(str(r.url)), handler(r))[1])
        return httpx.Client(*a, **k)
    seen_flags = []
    monkeypatch.setattr(boamp, "httpx", types.SimpleNamespace(Client=factory, Timeout=httpx.Timeout))
    return seen_flags


def test_fetch_dce_ignore_url_attaquant_et_liens_internes(monkeypatch, fake_dns):
    from app.sourcing.schemas import NormalizedTender
    from app.sourcing.sources.boamp import BoampSource
    seen = []
    pdf = _text_pdf("DCE OFFICIEL " + "x" * 400)

    def h(req):
        if req.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(200, text=(
            '<a href="http://169.254.169.254/latest/meta-data/iam/admin.pdf">a</a>'
            '<a href="https://10.0.0.1/secret.pdf">b</a>'
            '<a href="/telechargements/dce.pdf">c</a>'))
    flags = _patch_boamp_client(monkeypatch, h, seen)

    # 1) URL interne + identifiant bidon → aucune requête du tout.
    t = NormalizedTender(objet="x", provenance={"source": "BOAMP", "official_ref": "PWN-1",
                                                "source_url": "http://169.254.169.254/latest/meta-data/"})
    assert BoampSource().fetch_dce(t) is None
    assert seen == []

    # 2) URL interne + vrai idweb → URL officielle reconstruite ; liens internes ignorés.
    t = NormalizedTender(objet="x", provenance={"source": "BOAMP", "official_ref": "24-123456",
                                                "source_url": "http://169.254.169.254/"})
    txt = BoampSource().fetch_dce(t)
    assert txt and "DCE OFFICIEL" in txt
    assert seen == ["https://www.boamp.fr/avis/detail/24-123456",
                    "https://www.boamp.fr/telechargements/dce.pdf"]
    assert not any("169.254" in u or "10.0.0.1" in u for u in seen)
    assert flags and all(f is False for f in flags)     # jamais de redirection automatique


def test_ssrf_route_analyze_ne_touche_pas_l_interne(client, auth, monkeypatch, fake_dns):
    """Rejeu de verify/ssrf_analyze.py via l'API."""
    seen = []
    _patch_boamp_client(monkeypatch, lambda r: httpx.Response(
        200, text='<a href="http://169.254.169.254/latest/meta-data/iam/admin.pdf">x</a>'), seen)
    tender = {"objet": "x", "provenance": {"source": "BOAMP", "official_ref": "PWN-1",
                                           "source_url": "http://169.254.169.254/latest/meta-data/"}}
    client.post("/api/sourcing/analyze", json={"tender": tender}, headers=auth["headers"])
    assert not any("169.254" in u for u in seen), seen


def test_source_url_javascript_non_stockee():
    from app.routers.sourcing import _safe_link
    assert _safe_link("javascript:alert(document.cookie)") is None
    assert _safe_link("data:text/html,x") is None
    assert _safe_link("//evil.com/x") is None
    assert _safe_link("https://www.boamp.fr/avis/detail/24-1") == "https://www.boamp.fr/avis/detail/24-1"
    assert _safe_link("/static/demo/avis-boamp.html") == "/static/demo/avis-boamp.html"


# ── Faille 14 : OCR / extraction PDF bornés ──────────────────────────────────

@pytest.fixture
def fake_ocr(monkeypatch):
    """pdf2image/pytesseract simulés (absents en local) : on enregistre ce que poppler
    aurait rendu."""
    calls = []

    def convert_from_bytes(content, dpi=200, first_page=None, last_page=None, **kw):
        calls.append({"dpi": dpi, "first": first_page, "last": last_page})
        from pypdf import PdfReader
        n = len(PdfReader(io.BytesIO(content)).pages)
        lo, hi = first_page or 1, min(last_page or n, n)
        return [object() for _ in range(max(0, hi - lo + 1))]
    monkeypatch.setitem(sys.modules, "pdf2image", types.SimpleNamespace(convert_from_bytes=convert_from_bytes))
    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace(
        image_to_string=lambda img, lang=None: "Texte reconnu par OCR sur une page scannee du DCE."))
    return calls


def test_ocr_ne_rend_que_les_premieres_pages(fake_ocr):
    pdf = _blank_pdf(3000)          # exploit d'origine : 3000 pages blanches (~0,4 Mo)
    txt = extract_dce_text("scan.pdf", pdf)
    assert "OCR" in txt
    rendered = sum(c["last"] - c["first"] + 1 for c in fake_ocr)
    assert rendered <= analysis.OCR_MAX_PAGES, f"{rendered} pages rendues (avant : 3000)"
    assert all(c["first"] is not None and c["last"] is not None for c in fake_ocr)


def test_ocr_page_geante_resolution_reduite(fake_ocr):
    pdf = _blank_pdf(1, width=14400, height=14400)   # 200 × 200 pouces
    extract_dce_text("plan.pdf", pdf)
    dpi = fake_ocr[0]["dpi"]
    assert 14400 / 72 * dpi <= analysis.OCR_MAX_SIDE_PX


def test_ocr_budget_partage_dans_un_zip(fake_ocr):
    z = _zip({f"scan_{i}.pdf": _blank_pdf(20) for i in range(5)})
    extract_dce_text("dce.zip", z)
    rendered = sum(c["last"] - c["first"] + 1 for c in fake_ocr)
    assert rendered <= analysis.OCR_TOTAL_MAX_PAGES


def test_extraction_pdf_bornee_en_pages_et_en_texte(monkeypatch):
    from pypdf import PageObject
    pdf = _text_pdf("Article " + "lorem ipsum " * 20, pages=700)
    count = {"n": 0}
    real = PageObject.extract_text

    def spy(self, *a, **k):
        count["n"] += 1
        return real(self, *a, **k)
    monkeypatch.setattr(PageObject, "extract_text", spy)
    analysis.extract_text_from_pdf(pdf)
    assert count["n"] <= analysis.PDF_MAX_PAGES
    count["n"] = 0
    out = extract_dce_text("dce.pdf", pdf, max_chars=2000)
    assert len(out) <= 2000 and count["n"] < 30
