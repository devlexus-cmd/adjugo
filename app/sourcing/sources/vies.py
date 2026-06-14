"""
Source entreprise paneuropéenne : VIES (VAT Information Exchange System, Commission UE).
https://ec.europa.eu/taxation_customs/vies/ — officiel, gratuit, sans clé.

Vérifie un numéro de TVA intracommunautaire dans n'importe quel État membre et,
quand le pays l'autorise, renvoie le nom et l'adresse. Sert de socle UNIFORME de
vérification d'entreprise pour tous les pays UE (là où il n'y a pas de registre
riche gratuit comme SIRENE en France). On n'affiche que ce que VIES renvoie
réellement : nom/adresse « non communiqués » par certains pays restent vides.
"""
import re
import logging
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger("adjugo")
BASE = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}"

# Préfixes TVA UE (la Grèce utilise « EL », pas « GR »).
VAT_PREFIXES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}


def _split_vat(raw: str):
    s = re.sub(r"\s", "", (raw or "")).upper()
    m = re.match(r"^([A-Z]{2})([0-9A-Z]+)$", s)
    if not m:
        return None, None
    cc, num = m.group(1), m.group(2)
    if cc == "GR":
        cc = "EL"           # VIES attend « EL » pour la Grèce
    return cc, num


def _clean(v: Optional[str]) -> Optional[str]:
    """VIES renvoie « --- » quand l'info n'est pas communiquée → None."""
    if not v:
        return None
    s = str(v).strip()
    return None if (not s or set(s) <= {"-", " "}) else s


def _parse_address(addr: Optional[str]):
    """Sépare une adresse VIES (multi-lignes) en (adresse, code_postal, ville)."""
    if not addr:
        return None, None, None
    lines = [l.strip() for l in addr.splitlines() if l.strip()]
    street = lines[0] if lines else None
    cp, ville = None, None
    if len(lines) > 1:
        tail = lines[-1]
        m = re.match(r"^\s*([0-9][0-9A-Z\- ]{2,9})\s+(.+)$", tail)
        if m:
            cp, ville = m.group(1).strip(), m.group(2).strip()
        else:
            ville = tail
    return street, cp, ville


class VatVerifier:
    name = "VIES"

    def check(self, vat: str, country: str = "") -> Optional[dict]:
        """Vérifie un n° TVA intracommunautaire. Retourne None si entrée invalide
        ou service indisponible (jamais inventé)."""
        if country:
            cc = country.strip().upper()
            num = re.sub(r"[^0-9A-Z]", "", (vat or "").upper())
            if cc == "GR":
                cc = "EL"
        else:
            cc, num = _split_vat(vat)
        if not cc or not num or cc not in VAT_PREFIXES:
            return None
        try:
            with httpx.Client(timeout=12, headers={"User-Agent": "AdjugoBot/1.0"}) as c:
                r = c.get(BASE.format(cc=cc, num=num))
                r.raise_for_status()
                js = r.json()
        except Exception as e:
            logger.info("VIES indisponible (%s%s) : %s", cc, num, e)
            return None

        name = _clean(js.get("name"))
        street, cp, ville = _parse_address(_clean(js.get("address")))
        return {
            "valid": bool(js.get("isValid")),
            "vat": cc + num,
            "country": "GR" if cc == "EL" else cc,
            "name": name,
            "address": street,
            "postal_code": cp,
            "city": ville,
            "name_disclosed": name is not None,
            "source": self.name,
            "source_url": "https://ec.europa.eu/taxation_customs/vies/",
            "fetched_at": date.today().isoformat(),
        }
