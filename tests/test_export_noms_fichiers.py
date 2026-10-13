"""Export du dossier (ZIP) : un document dont le nom porte déjà son extension n'est jamais exporté
en « Kbis.pdf.pdf » ; un nom sans extension la reçoit."""
import io
import zipfile

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_extension_jamais_doublee(client, auth):
    h = auth["headers"]
    pid = client.post("/api/projects/", headers=h, json={"name": "Export", "client": "Commune"}).json()["id"]
    for nom in ("Kbis.pdf", "Attestation URSSAF"):
        r = client.post("/api/documents/", headers=h, files={"file": ("f.pdf", io.BytesIO(PDF), "application/pdf")},
                        data={"name": nom, "category": "administratif", "project_id": str(pid)})
        assert r.status_code == 201, r.text
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text[:300]
    noms = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    docs = [n for n in noms if n.startswith("02_Documents/")]
    assert any(n.endswith("/Kbis.pdf") for n in docs), docs
    assert any(n.endswith("/Attestation_URSSAF.pdf") for n in docs), docs
    assert not any(n.endswith(".pdf.pdf") for n in docs), docs
