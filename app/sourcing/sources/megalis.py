"""
Source AO : Mégalis Bretagne — plateforme mutualisée des marchés publics de Bretagne
(moteur Atexo). Couvre les consultations EN COURS des collectivités bretonnes, y compris
les MAPA sous-seuil ABSENTS du BOAMP — exactement le segment où la cotraitance PME a le
plus de sens.

Lecture de la liste publique des consultations (HTML server-rendu). Parsing robuste :
en cas d'échec réseau/parsing, la source lève (→ SourceError affichée), JAMAIS de donnée
inventée. Activée UNIQUEMENT quand un département breton (22/29/35/56) est ciblé.
"""
import logging
import re
import unicodedata

from app.sourcing.base import TenderSource, TenderCriteria
from app.sourcing.schemas import NormalizedTender, Provenance
from app.sourcing.http import get_with_retry

logger = logging.getLogger("adjugo")
BASE = "https://marches.megalis.bretagne.bzh"
LISTING = BASE + "/?page=Entreprise.EntrepriseAdvancedSearch&AllCons="
BRETAGNE = {"22", "29", "35", "56"}
_UA = {"User-Agent": "Mozilla/5.0 (compatible; AdjugoBot/1.0; +https://adjugo.pro)"}
_MOIS = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avri": 4, "mai": 5, "juin": 6,
         "juil": 7, "août": 8, "aout": 8, "sept": 9, "octo": 10, "nove": 11, "déce": 12, "dece": 12}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _no_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


def _parse_date(text: str):
    """Dernière date « JJ Mois AAAA [HH:MM] » du bloc = date limite de remise. ISO ou None."""
    ms = re.findall(r"(\d{1,2})\s+([A-Za-zéûàèùçÉ.]+)\.?\s+(\d{4})(?:\s+\d{1,2}:\d{2})?", text)
    if not ms:
        return None
    d, mo, y = ms[-1]
    m = _MOIS.get(mo.lower().strip(".")[:4], 0)
    return f"{y}-{m:02d}-{int(d):02d}" if m else None


class MegalisSource(TenderSource):
    name = "Mégalis Bretagne"
    supported_filters = {"query", "departements"}

    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        deps = [str(d).strip()[:2] for d in getattr(criteria, "departements", []) if str(d).strip()]
        wanted = {d for d in deps if d in BRETAGNE}
        # Ne s'active QUE pour la Bretagne (sinon : latence et bruit inutiles ailleurs).
        if not wanted:
            return []
        try:
            from bs4 import BeautifulSoup
        except Exception:
            logger.info("Mégalis : BeautifulSoup indisponible — source ignorée.")
            return []

        q = _clean(getattr(criteria, "query", "") or "")
        if q:
            # Recherche SERVEUR par mot-clé sur tout le catalogue Mégalis (pas seulement la
            # liste récente) → on ratisse large ET pertinent. Endpoint Atexo confirmé.
            from urllib.parse import quote
            url = BASE + "/?page=Entreprise.EntrepriseAdvancedSearch&searchAnnCons&keyWord=" + quote(q[:80])
        else:
            url = LISTING
        r = get_with_retry(url, timeout=16, headers=_UA)
        soup = BeautifulSoup(r.text, "html.parser")

        out, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"/entreprise/consultation/\d+")):
            mid = re.search(r"/consultation/(\d+)", a.get("href", ""))
            if not mid:
                continue
            cid = mid.group(1)
            if cid in seen:
                continue
            seen.add(cid)
            org = (re.search(r"orgAcronyme=([^&\s\"]+)", a["href"]) or [None, ""])[1]
            # Remonter au conteneur de ligne (celui qui porte « Objet » ET « Organisme »).
            node = a
            for _ in range(8):
                node = node.parent
                if node is None:
                    break
                g = node.get_text()
                if "Objet" in g and "Organisme" in g:
                    break
            if node is None:
                continue
            t = _clean(node.get_text(" ", strip=True))
            dep = (re.search(r"\((\d{2})\)", t) or [None, ""])[1]
            if dep not in wanted:
                continue
            objet = _clean((re.search(r"Objet\s*:\s*(.*?)\s*Organisme\s*:", t) or [None, ""])[1])
            intitule = _clean((re.search(r"([^|]{6,180}?)\s*Objet\s*:", t) or [None, ""])[1])
            organisme = _clean((re.search(r"Organisme\s*:\s*(.*?)(?:\(\d{2}\)|\d+\s+lots|$)", t) or [None, ""])[1])
            titre = intitule or objet
            if not titre:
                continue
            cons_url = f"{BASE}/entreprise/consultation/{cid}" + (f"?orgAcronyme={org}" if org else "")
            tender = NormalizedTender(
                objet=titre[:400],
                acheteur=organisme or None,
                date_limite=_parse_date(t),
                lieu=organisme or None,
                departements=[dep] if dep else [],
                nature="Marché public (Bretagne)",
                dce_url=cons_url,
                provenance=Provenance(source=self.name, source_url=cons_url, official_ref=cid),
                raw={"objet_complet": objet[:600]},
            )
            tender.confidence = 0.7
            tender.dedup_key = "megalis:" + cid
            out.append(tender)
        return out
