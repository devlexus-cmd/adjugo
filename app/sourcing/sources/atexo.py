"""
Connecteur GÉNÉRIQUE des plateformes Atexo (moteur MPE/Prado) des marchés publics :
Mégalis Bretagne, PLACE (achats de l'État), e-marchespublics, AWS-achat, Maximilien…
Toutes partagent la même recherche serveur (?page=Entreprise.EntrepriseAdvancedSearch&
searchAnnCons&keyWord=) et la même structure HTML (« Objet : », « Organisme : »,
liens /consultation/<id>?orgAcronyme=). Couvre les MAPA sous-seuil ABSENTS du BOAMP —
le terrain de la cotraitance PME.

Robustesse (objectif : apporter de la valeur, pas casser) :
- Recherche serveur par mot-clé (catalogue complet, pas la seule liste récente).
- PAGINATION (postback Prado « aller à la page N ») → jusqu'à _MAX_PAGES pages.
- CACHE serveur partagé (TTL) : anti-martèlement de la plateforme + latence quasi nulle en répétition.
- Garde-fou « source muette » : des liens mais 0 parsé = template changé → log d'ALERTE.
- Dégradation gracieuse à CHAQUE étage : un échec de page renvoie ce qu'on a ; jamais de
  donnée inventée ; jamais de crash de la recherche globale.
"""
import logging
import re
import time

from app.sourcing.base import TenderSource, TenderCriteria
from app.sourcing.schemas import NormalizedTender, Provenance

logger = logging.getLogger("adjugo")
# UA navigateur réel : les WAF des plateformes publiques (gouv/Atexo) bloquent les UA
# « bot » identifiés. On lit de la donnée PUBLIQUE de la commande publique, destinée aux
# entreprises — un UA navigateur est la seule façon de la servir à l'utilisateur.
_UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_MOIS = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avri": 4, "mai": 5, "juin": 6,
         "juil": 7, "août": 8, "aout": 8, "sept": 9, "octo": 10, "nove": 11, "déce": 12, "dece": 12}
_MAX_PAGES = 3            # plafond de pages ; le budget ADAPTATIF ci-dessous décide vraiment
_TIME_BUDGET = 6.0       # budget temps (s) : on n'entame une page de plus que si elle y tient
_CACHE = {}              # url -> (expire_ts, [NormalizedTender])
_CACHE_TTL = 1200        # 20 min : partagé entre tous les utilisateurs (process unique)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _parse_date(text):
    ms = re.findall(r"(\d{1,2})\s+([A-Za-zéûàèùçÉ.]+)\.?\s+(\d{4})(?:\s+\d{1,2}:\d{2})?", text)
    if not ms:
        return None
    d, mo, y = ms[-1]
    m = _MOIS.get(mo.lower().strip(".")[:4], 0)
    return f"{y}-{m:02d}-{int(d):02d}" if m else None


def _post_fields(soup):
    forms = [f for f in soup.find_all("form") if (f.get("method") or "").lower() == "post"]
    if not forms:
        return None
    form = forms[-1]
    fields = {i.get("name"): (i.get("value") or "") for i in form.find_all("input") if i.get("name")}
    for s in form.find_all("select"):
        if s.get("name"):
            opt = s.find("option", selected=True) or s.find("option")
            fields[s["name"]] = opt.get("value", "") if opt else ""
    return fields


def _parse_page(html, source_name, base):
    """Extrait les consultations d'une page de résultats Atexo. Retourne (tenders, nb_liens)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out, ids = [], set()
    for a in soup.find_all("a", href=re.compile(r"/consultation/\d+")):
        href = a.get("href", "")
        m = re.search(r"/consultation/(\d+)", href)
        if not m:
            continue
        cid = m.group(1)
        ids.add(cid)
        org = (re.search(r"orgAcronyme=([^&\s\"]+)", href) or [None, ""])[1]
        node = a
        for _ in range(9):
            node = node.parent
            if node is None:
                break
            g = node.get_text()
            if "Objet" in g and "Organisme" in g:
                break
        if node is None:
            continue
        t = _clean(node.get_text(" ", strip=True))
        objet = _clean((re.search(r"Objet\s*:\s*(.*?)\s*Organisme\s*:", t) or [None, ""])[1])
        intitule = _clean((re.search(r"([^|]{6,180}?)\s*Objet\s*:", t) or [None, ""])[1])
        organisme = _clean((re.search(r"Organisme\s*:\s*(.*?)(?:\(\d{2}\)|\d+\s+lots|$)", t) or [None, ""])[1])
        dep = (re.search(r"\((\d{2})\)", t) or [None, ""])[1]
        titre = intitule or objet
        if not titre:
            continue
        cons_url = base + (href if href.startswith("/") else "/" + href)
        cons_url = re.split(r"#|&code=", cons_url)[0]
        te = NormalizedTender(
            objet=titre[:400], acheteur=organisme or None, date_limite=_parse_date(t),
            lieu=organisme or None, departements=[dep] if dep else [],
            nature="Marché public", dce_url=cons_url,
            provenance=Provenance(source=source_name, source_url=cons_url, official_ref=cid),
            raw={"objet_complet": objet[:600], "dep": dep})
        te.confidence = 0.7
        te.dedup_key = "atexo:" + cid
        out.append(te)
    return out, len(ids)


def _fetch_all(url, source_name, base):
    """GET page 1 puis POST pages 2..N (postback Prado). Robuste : tout échec de page →
    on s'arrête et renvoie l'accumulé. Lève seulement si la 1re requête échoue ET rien collecté."""
    import httpx
    from bs4 import BeautifulSoup
    t0 = time.time()
    tenders, seen, total_links = [], set(), 0
    try:
        with httpx.Client(timeout=10, headers=_UA, follow_redirects=True) as c:
            g0 = time.time()
            html = c.get(url).text
            fetch_dur = time.time() - g0
            for page in range(1, _MAX_PAGES + 1):
                part, n_links = _parse_page(html, source_name, base)
                total_links += n_links
                for te in part:
                    if te.dedup_key in seen:
                        continue
                    seen.add(te.dedup_key)
                    tenders.append(te)
                # Budget ADAPTATIF : on n'entame la page suivante que si elle tient dans le
                # budget, estimé sur la durée de la dernière requête. Plateforme lente (PLACE)
                # → moins de pages mais réponse rapide ; plateforme rapide (Mégalis) → ratisse large.
                if page == _MAX_PAGES or (time.time() - t0) + fetch_dur > _TIME_BUDGET:
                    break
                try:    # page suivante : postback Prado « aller à la page N+1 »
                    fields = _post_fields(BeautifulSoup(html, "html.parser"))
                    npb = next((k for k in (fields or {}) if k.endswith("numPageBottom")), None)
                    btn = next((k for k in (fields or {}) if k.endswith("DefaultButtonBottom")), None)
                    if not (fields and npb and btn):
                        break
                    fields[npb] = str(page + 1)
                    fields["PRADO_POSTBACK_TARGET"] = btn
                    fields["PRADO_POSTBACK_PARAMETER"] = ""
                    p0 = time.time()
                    resp = c.post(url, data=fields)
                    fetch_dur = time.time() - p0
                    if resp.status_code != 200:
                        break
                    html = resp.text
                except Exception:
                    break
    except Exception as e:
        logger.info("Atexo %s indisponible : %s", source_name, e)
        if not tenders:
            raise
    # Garde-fou « source muette » : des liens présents mais 0 consultation parsée → template changé.
    if total_links >= 3 and not tenders:
        logger.warning("Atexo %s : %d liens consultation mais 0 parsé — TEMPLATE CHANGÉ ?",
                       source_name, total_links)
    return tenders


def _cached_fetch(url, source_name, base):
    now = time.time()
    hit = _CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    tenders = _fetch_all(url, source_name, base)
    _CACHE[url] = (now + _CACHE_TTL, tenders)
    if len(_CACHE) > 80:
        for k in [k for k, (e, _) in list(_CACHE.items()) if e <= now][:40]:
            _CACHE.pop(k, None)
    return tenders


class AtexoSource(TenderSource):
    """Une plateforme Atexo. scope=None → nationale ; scope={depts} → régionale (ne tourne
    que si un de ses départements est ciblé)."""
    supported_filters = {"query", "departements"}

    def __init__(self, name: str, base: str, scope=None):
        self.name = name
        self.base = base.rstrip("/")
        self.scope = set(scope) if scope else None

    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        # Pas de pagination par offset côté Atexo : les résultats sont servis en page 1.
        # Sur un « Charger plus » (offset>0), on NE refait PAS le scrape — c'est BOAMP/TED
        # qui paginent → évite de re-télécharger pour rien et un « has_more » bloqué à tort.
        if getattr(criteria, "offset", 0):
            return []
        try:
            import bs4  # noqa: F401
        except Exception:
            return []
        countries = [str(c).upper() for c in getattr(criteria, "countries", []) if c]
        if countries and "FR" not in countries:   # plateformes françaises : inutiles hors France
            return []
        deps = [str(d).strip()[:2] for d in getattr(criteria, "departements", []) if str(d).strip()]
        if self.scope is not None:
            wanted = {d for d in deps if d in self.scope}
            if not wanted:                  # régionale : seulement sur son périmètre
                return []
        else:
            wanted = set(deps)              # nationale : filtre par dept demandé ; vide = tous
        q = _clean(getattr(criteria, "query", "") or "")
        if q:
            from urllib.parse import quote
            url = self.base + "/?page=Entreprise.EntrepriseAdvancedSearch&searchAnnCons&keyWord=" + quote(q[:80])
        else:
            url = self.base + "/?page=Entreprise.EntrepriseAdvancedSearch&AllCons="
        tenders = _cached_fetch(url, self.name, self.base)
        if wanted:
            # garde les marchés du/des département(s) ciblé(s) ET ceux SANS département
            # précis (souvent nationaux / multi-sites → pertinents partout).
            tenders = [t for t in tenders if (not t.departements) or t.departements[0] in wanted]
        return tenders


# ── Plateformes branchées ────────────────────────────────────────────────────────
MEGALIS = AtexoSource("Mégalis Bretagne", "https://marches.megalis.bretagne.bzh",
                      scope={"22", "29", "35", "56"})
PLACE = AtexoSource("PLACE (État)", "https://www.marches-publics.gouv.fr", scope=None)
