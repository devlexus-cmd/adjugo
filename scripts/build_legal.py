"""
Génère les pages légales HTML (charte Adjugo) à partir des sources Markdown.

Source : docs/legal/*.md  →  Sortie : app/static/legal/*.html (servies par l'app).
Le Markdown reste la source de vérité ; relancer ce script après chaque modification.

Usage : python scripts/build_legal.py
"""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "legal")
OUT = os.path.join(ROOT, "app", "static", "legal")

PAGES = [
    ("mentions-legales.md", "mentions-legales.html", "Mentions légales"),
    ("cgv.md", "cgv.html", "Conditions Générales de Vente"),
    ("politique-confidentialite.md", "confidentialite.html", "Politique de confidentialité"),
]

_LINK_REWRITE = {
    "./mentions-legales.md": "/mentions-legales",
    "./cgv.md": "/cgv",
    "./politique-confidentialite.md": "/confidentialite",
}


def _inline(text: str) -> str:
    """Markdown inline sur du texte DÉJÀ échappé HTML."""
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)

    def _link(m):
        label, url = m.group(1), m.group(2)
        url = _LINK_REWRITE.get(url, url)
        return f'<a href="{html.escape(url)}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)


def _cells(row: str):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _table(rows):
    header = _cells(rows[0])
    body = rows[2:] if len(rows) > 2 else []
    th = "".join(f"<th>{_inline(html.escape(c))}</th>" for c in header)
    trs = "".join(
        "<tr>" + "".join(f"<td>{_inline(html.escape(c))}</td>" for c in _cells(r)) + "</tr>"
        for r in body
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def md_to_html(md: str) -> str:
    lines = md.split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush(); i += 1; continue
        if re.match(r"^---+$", s):
            flush(); out.append("<hr>"); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush(); lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(html.escape(m.group(2)))}</h{lvl}>"); i += 1; continue
        if s.startswith(">"):
            flush(); bq = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                bq.append(re.sub(r"^\s*>\s?", "", lines[i]).strip()); i += 1
            out.append("<blockquote>" + _inline(html.escape(" ".join(bq))) + "</blockquote>")
            continue
        if s.startswith("|"):
            flush(); tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip()); i += 1
            out.append(_table(tbl)); continue
        if re.match(r"^[-*]\s+", s) or re.match(r"^\d+\.\s+", s):
            flush()
            ordered = bool(re.match(r"^\d+\.\s+", s))
            items = []
            while i < len(lines):
                mm = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                items.append("<li>" + _inline(html.escape(mm.group(1))) + "</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>"); continue
        para.append(html.escape(s)); i += 1

    flush()
    return "\n".join(out)


TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<title>{title} — Adjugo</title>
<style>
  :root { --blue:#1B4FFF; --ink:#0A1730; --ink-2:#3D4A63; --muted:#5A6573; --line:#E6E9F0;
    --bg:#FFFFFF; --soft:#F6F7FA; --warn-bg:#FBF6E9; --warn-bd:#E6C870; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    color:var(--ink); background:var(--bg); line-height:1.62; font-size:15.5px; }
  a { color:var(--blue); text-decoration:none; }
  a:hover { text-decoration:underline; }
  a:focus-visible { outline:3px solid var(--blue); outline-offset:2px; border-radius:3px; }
  .lg-top { display:flex; align-items:center; justify-content:space-between; gap:16px;
    max-width:880px; margin:0 auto; padding:20px 24px; border-bottom:1px solid var(--line); }
  .brand { display:inline-flex; align-items:center; font-weight:800; font-size:21px;
    letter-spacing:-.04em; color:var(--blue); }
  .brand svg { width:.92em; height:.92em; margin-left:-.04em; }
  .back { font-size:14px; font-weight:600; color:var(--ink-2); }
  main { max-width:820px; margin:0 auto; padding:32px 24px 64px; }
  h1 { font-size:30px; letter-spacing:-.02em; margin:8px 0 24px; }
  h2 { font-size:21px; letter-spacing:-.01em; margin:38px 0 12px; padding-top:8px; }
  h3 { font-size:17px; margin:26px 0 10px; }
  h4 { font-size:15.5px; margin:20px 0 8px; }
  p { margin:12px 0; color:var(--ink-2); }
  strong { color:var(--ink); }
  ul, ol { color:var(--ink-2); padding-left:22px; }
  li { margin:6px 0; }
  hr { border:0; border-top:1px solid var(--line); margin:32px 0; }
  code { background:var(--soft); padding:1px 6px; border-radius:6px; font-size:13.5px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:#7A4D00; }
  blockquote { background:var(--warn-bg); border:1px solid var(--warn-bd); border-left:4px solid var(--warn-bd);
    border-radius:10px; padding:12px 16px; margin:18px 0; color:#5A4A1A; font-size:14.5px; }
  blockquote strong { color:#3D3000; }
  table { width:100%; border-collapse:collapse; margin:18px 0; font-size:14px; }
  th, td { border:1px solid var(--line); padding:9px 12px; text-align:left; vertical-align:top; }
  th { background:var(--soft); font-weight:700; color:var(--ink); }
  .lg-foot { max-width:820px; margin:0 auto; padding:24px; border-top:1px solid var(--line);
    color:var(--muted); font-size:13.5px; display:flex; gap:18px; flex-wrap:wrap; align-items:center; }
  .lg-foot a { color:var(--ink-2); font-weight:600; }
</style>
</head>
<body>
<header class="lg-top">
  <a class="brand" href="/">adjug<svg viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="21" stroke="currentColor" stroke-opacity=".16" stroke-width="3"/><circle cx="24" cy="24" r="13.5" stroke="currentColor" stroke-opacity=".42" stroke-width="3"/><circle cx="24" cy="24" r="6.5" fill="currentColor"/></svg></a>
  <a class="back" href="/">← Retour à l'accueil</a>
</header>
<main>
{content}
</main>
<footer class="lg-foot">
  <span>© 2026 Adjugo — PADIS (Eliot Viegas)</span>
  <a href="/mentions-legales">Mentions légales</a>
  <a href="/cgv">CGV</a>
  <a href="/confidentialite">Confidentialité</a>
</footer>
</body>
</html>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for src, dst, title in PAGES:
        md = open(os.path.join(SRC, src), encoding="utf-8").read()
        page = TEMPLATE.replace("{title}", title).replace("{content}", md_to_html(md))
        with open(os.path.join(OUT, dst), "w", encoding="utf-8") as f:
            f.write(page)
        print(f"généré : app/static/legal/{dst}  ({len(page)} octets)")


if __name__ == "__main__":
    main()
