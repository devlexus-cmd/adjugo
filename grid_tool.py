import os, io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

TEMPLATES_DIR = "templates"

def create_grid(width, height):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.15)
    x = 0
    while x <= width:
        c.line(x, 0, x, height)
        x += 10 * mm
    y = 0
    while y <= height:
        c.line(0, y, width, y)
        y += 10 * mm
    c.setStrokeColor(HexColor("#FF0000"))
    c.setLineWidth(0.3)
    x = 0
    while x <= width:
        c.line(x, 0, x, height)
        c.setFont("Helvetica", 6)
        c.setFillColor(HexColor("#FF0000"))
        c.drawString(x + 1, 5, "x=" + str(int(x)))
        x += 50 * mm
    y = 0
    while y <= height:
        c.line(0, y, width, y)
        c.setFont("Helvetica", 6)
        c.setFillColor(HexColor("#FF0000"))
        c.drawString(3, y + 2, "y=" + str(int(height - y)))
        y += 50 * mm
    c.setFont("Helvetica", 4)
    c.setFillColor(HexColor("#0000FF88"))
    x = 0
    while x <= width:
        y = 0
        while y <= height:
            c.drawString(x + 0.5, y + 0.5, str(int(x)) + "," + str(int(height - y)))
            y += 25 * mm
        x += 25 * mm
    c.save()
    return buf

def process(name):
    inp = os.path.join(TEMPLATES_DIR, name + ".pdf")
    out = os.path.join(TEMPLATES_DIR, "grid_" + name + ".pdf")
    if not os.path.exists(inp):
        print("[SKIP] " + name + ".pdf introuvable")
        return
    reader = PdfReader(inp)
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        grid = PdfReader(create_grid(w, h))
        page.merge_page(grid.pages[0])
        writer.add_page(page)
        print("  Page " + str(i+1) + ": " + str(int(w)) + "x" + str(int(h)))
    with open(out, "wb") as f:
        writer.write(f)
    print("  -> " + out)

print("=== Generation des grilles CERFA ===")
for n in ["dc1", "dc2", "dc4", "attri1"]:
    process(n)
print("\nOuvre les grid_*.pdf dans Apercu.")
print("Les y sont depuis le HAUT (comme dans le code).")
