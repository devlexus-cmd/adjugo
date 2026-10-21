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
import os
import re
import threading
import time

from app.sourcing.base import SourceIndisponible, TenderSource, TenderCriteria
from app.sourcing.dates_fr import date_textuelle, derniere_date_textuelle
from app.sourcing.schemas import NormalizedTender, Provenance

logger = logging.getLogger("adjugo")
# En-tête HONNÊTE (étude moteur, décision 4 a) : Adjugo se nomme et donne un contact. On ne se fait
# jamais passer pour un navigateur. Si une plateforme refuse ce robot, on ne contourne pas : elle
# passe « indisponible » (voir _refus) et la recherche continue sur les autres sources.
USER_AGENT = "AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)"
_UA = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
# Rythme BORNÉ : au moins _INTERVALLE_MIN secondes entre deux requêtes vers une même plateforme,
# tous utilisateurs confondus (process unique), en plus du cache de 20 min et des 3 pages au plus.
_INTERVALLE_MIN = float(os.getenv("ATEXO_INTERVALLE_MIN", "1.0"))
_RYTHME: dict = {}
_RYTHME_LOCK = threading.Lock()
# Refus du robot (HTTP 401/403/406/429, ou page de blocage) : la plateforme n'est plus interrogée
# pendant _PAUSE_REFUS secondes, et le journal le dit UNE fois par heure au plus.
_PAUSE_REFUS = 3600.0
_LOG_REFUS = 3600.0
_STATUTS_REFUS = {401, 403, 406, 429}
_PAGE_REFUS = re.compile(r"captcha|access denied|request rejected", re.I)
_REFUS: dict = {}          # nom de la source -> {"jusqua": horloge, "logue": horloge}
_REFUS_LOCK = threading.Lock()
MSG_REFUS = ("la plateforme n'accepte pas pour l'instant la lecture automatique d'Adjugo ; "
             "la recherche continue sur les autres sources")


class PlateformeRefuse(Exception):
    """La plateforme refuse notre robot (aucun contournement)."""


def _attendre_son_tour(base: str) -> None:
    """Réserve le prochain créneau d'envoi vers `base` puis attend son heure."""
    with _RYTHME_LOCK:
        now = time.monotonic()
        creneau = max(now, _RYTHME.get(base, float("-inf")) + _INTERVALLE_MIN)
        _RYTHME[base] = creneau
    attente = creneau - time.monotonic()
    if attente > 0:
        time.sleep(attente)


def _controler(resp) -> None:
    """Lève PlateformeRefuse si la réponse est un refus du robot ; une autre erreur HTTP reste
    une panne ordinaire (raise_for_status)."""
    if resp.status_code in _STATUTS_REFUS:
        raise PlateformeRefuse(f"HTTP {resp.status_code}")
    resp.raise_for_status()
    texte = resp.text or ""
    if "/consultation/" not in texte and _PAGE_REFUS.search(texte[:20000]):
        raise PlateformeRefuse("page de blocage")


def _refusee(name: str) -> bool:
    with _REFUS_LOCK:
        r = _REFUS.get(name)
        return bool(r and r["jusqua"] > time.monotonic())


def _noter_refus(name: str, motif: str) -> None:
    now = time.monotonic()
    with _REFUS_LOCK:
        r = _REFUS.setdefault(name, {"jusqua": 0.0, "logue": float("-inf")})
        r["jusqua"] = now + _PAUSE_REFUS
        loguer = now - r["logue"] >= _LOG_REFUS
        if loguer:
            r["logue"] = now
    if loguer:
        logger.warning("Atexo %s refuse l'en-tête honnête d'Adjugo (%s) : source marquée indisponible "
                       "pendant 1 h, SANS contournement ; la recherche continue avec BOAMP et TED. "
                       "Autorisation à demander : docs/AUTORISATIONS_PLATEFORMES.md.", name, motif)


# Les mois des dates (« 7 Déc. 2026 ») sont lus par la table EXPLICITE de app/sourcing/dates_fr.py : l'ancienne
# coupe à 4 lettres laissait vides les dates d'octobre, novembre, décembre, février et avril (lot 1, point 1).
_MAX_PAGES = 3            # plafond de pages ; le budget ADAPTATIF ci-dessous décide vraiment
_TIME_BUDGET = 6.0       # budget temps (s) : on n'entame une page de plus que si elle y tient
_CACHE = {}              # url -> (expire_ts, [NormalizedTender])
_CACHE_TTL = 1200        # 20 min : partagé entre tous les utilisateurs (process unique)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _parse_date(text):
    """Date limite d'un bloc de résultat lu en TEXTE (repli quand la case « clôture » manque) : la dernière
    date « jour mois année » du bloc, le mois lu dans la table explicite de app/sourcing/dates_fr.py
    (« Oct. », « Nov. », « Déc. », « Fév. », « Avr. » compris). Mois inconnu : None, jamais deviné."""
    return derniere_date_textuelle(text)


def _date_cloture(node):
    """(case trouvée, date) : la case « clôture » d'un résultat Atexo (jour, mois, année dans trois cases,
    ex. « 7 » « Déc. » « 2026 »). Plusieurs cases dans le même bloc ou une case incomplète : aucune date
    (jamais celle d'une autre consultation, jamais devinée)."""
    try:
        cases = node.select(".cloture-line")
    except Exception:
        return False, None
    if not cases:
        return False, None
    if len(cases) != 1:
        return True, None
    j, mo, a = (cases[0].select_one(sel) for sel in (".day", ".month", ".year"))
    if not (j and mo and a):
        return True, None
    return True, date_textuelle(j.get_text(strip=True), mo.get_text(strip=True), a.get_text(strip=True))


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
        trouvee, cloture = _date_cloture(node)
        te = NormalizedTender(
            objet=titre[:400], acheteur=organisme or None,
            date_limite=cloture if trouvee else _parse_date(t),
            lieu=organisme or None, departements=[dep] if dep else [],
            nature="Marché public", dce_url=cons_url,
            provenance=Provenance(source=source_name, source_url=cons_url, official_ref=cid),
            raw={"objet_complet": objet[:600], "dep": dep})
        te.confidence = 0.7
        # Clé de dédup FLOUE (objet+acheteur+échéance), identique à BOAMP/TED : un même MAPA
        # publié aussi sur BOAMP fusionne (concordance) au lieu d'apparaître en double. La dédup
        # INTRA-Atexo, elle, se fait sur le cid exact (cf. _fetch_all) — pas de faux positif.
        base = re.sub(r"[^a-z0-9]", "", (titre or "").lower())[:40]
        ach = re.sub(r"[^a-z0-9]", "", (organisme or "").lower())[:20]
        te.dedup_key = f"{base}|{ach}|{te.date_limite or ''}"
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
            _attendre_son_tour(base)
            g0 = time.time()
            first = c.get(url)
            fetch_dur = time.time() - g0
            _controler(first)
            html = first.text
            for page in range(1, _MAX_PAGES + 1):
                part, n_links = _parse_page(html, source_name, base)
                total_links += n_links
                for te in part:
                    # Dédup intra-Atexo sur le cid EXACT (official_ref) : la clé floue peut
                    # coïncider entre deux consultations proches, pas le cid.
                    cid = te.provenance.official_ref
                    if cid in seen:
                        continue
                    seen.add(cid)
                    tenders.append(te)
                # Budget ADAPTATIF : on n'entame la page suivante que si elle tient dans le
                # budget, estimé sur la durée de la dernière requête. Plateforme lente (PLACE)
                # → moins de pages mais réponse rapide ; plateforme rapide (Mégalis) → ratisse large.
                if page == _MAX_PAGES or (time.time() - t0) + fetch_dur + _INTERVALLE_MIN > _TIME_BUDGET:
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
                    _attendre_son_tour(base)
                    p0 = time.time()
                    resp = c.post(url, data=fields)
                    fetch_dur = time.time() - p0
                    if resp.status_code in _STATUTS_REFUS:
                        raise PlateformeRefuse(f"HTTP {resp.status_code} (page {page + 1})")
                    if resp.status_code != 200:
                        break
                    html = resp.text
                except PlateformeRefuse:
                    raise
                except Exception:
                    break
    except PlateformeRefuse:
        # Refus du robot : jamais de contournement. Ce qui a été lu honnêtement (page 1) est gardé.
        if not tenders:
            raise
        _noter_refus(source_name, "pages suivantes refusées")
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
        # Plateforme qui a refusé notre robot dans l'heure : plus aucune requête (ni contournement).
        if _refusee(self.name):
            raise SourceIndisponible(MSG_REFUS)
        try:
            tenders = _cached_fetch(url, self.name, self.base)
        except PlateformeRefuse as e:
            _noter_refus(self.name, str(e))
            raise SourceIndisponible(MSG_REFUS) from None
        if wanted:
            # garde les marchés du/des département(s) ciblé(s) ET ceux SANS département
            # précis (souvent nationaux / multi-sites → pertinents partout).
            tenders = [t for t in tenders if (not t.departements) or t.departements[0] in wanted]
        return tenders


# ── Plateformes branchées ────────────────────────────────────────────────────────
MEGALIS = AtexoSource("Mégalis Bretagne", "https://marches.megalis.bretagne.bzh",
                      scope={"22", "29", "35", "56"})
# PLACE : SUSPENDUE par défaut (PLACE_ACTIF=0, app/core/interrupteurs.py). Ses conditions
# d'utilisation interdisent la reprise des avis : elle n'est plus interrogée tant que l'AIFE n'a pas
# donné son autorisation écrite. L'objet reste défini (le routeur sait la nommer « non consultée »).
PLACE = AtexoSource("PLACE (État)", "https://www.marches-publics.gouv.fr", scope=None)
PLACE_NON_CONSULTEE = ("non consultée pour le moment : Adjugo attend l'autorisation écrite de la "
                       "plateforme pour réutiliser ses avis. Les avis de l'État publiés au BOAMP "
                       "restent visibles.")
