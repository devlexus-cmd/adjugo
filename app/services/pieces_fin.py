"""
Date de fin des pièces de « Mes documents » (réorganisation de l'interface, vague 2a, chantier A3).

UN SEUL calcul pour tout ce qui parle de la fin d'une pièce : la liste de Mes documents (GET /api/documents/), la
pastille « pièces à renouveler » du menu et l'encart de l'accueil (GET /api/documents/expiring), et le courriel
d'alerte (app.services.alerts.run_document_expiry_alerts). Avant, la liste ne montrait qu'une date, sans dire si la
pièce comptait dans la pastille, et le courriel avait ses propres mots.

- Le jour est celui de Paris (le serveur tourne en UTC : entre minuit et 2 h, « aujourd'hui » n'était pas le même jour
  pour l'entreprise et pour Adjugo).
- Une pièce est « à renouveler » quand sa date de fin est passée, ou tombe dans les ALERTE_JOURS jours (30 : le
  premier courriel part à 30 jours, puis à 7 jours, puis le jour même).
- Aucune date : rien n'est dit, la pièce ne compte nulle part (Adjugo n'invente pas de date de fin).
Contrat : docs/REORGANISATION_V2A.md, section A3.
"""
from datetime import date, datetime
from functools import lru_cache

ALERTE_JOURS = 30


@lru_cache(maxsize=1)
def _tz_paris():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Paris")
    except Exception:          # base des fuseaux absente : repli sur le jour du serveur
        return None


def jour_paris() -> date:
    """Le jour qu'il est à Paris (repli : le jour du serveur)."""
    tz = _tz_paris()
    return datetime.now(tz).date() if tz is not None else date.today()


def jj_mm_aaaa(d) -> str:
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d or "")


def etat_fin(fin, aujourdhui: date = None):
    """État d'une pièce d'après sa date de fin, ou None sans date.
    {"jours": n, "a_renouveler": bool, "code": "expiree" | "bientot" | "valide", "libelle": "…" | ""}
    `libelle` est vide pour une pièce encore valable au-delà de ALERTE_JOURS (la date suffit)."""
    if not fin:
        return None
    aujourdhui = aujourdhui or jour_paris()
    j = (fin - aujourdhui).days
    if j < 0:
        code, libelle = "expiree", f"Expirée le {jj_mm_aaaa(fin)}"
    elif j == 0:
        code, libelle = "bientot", "Expire aujourd'hui"
    elif j == 1:
        code, libelle = "bientot", "Expire demain"
    elif j <= ALERTE_JOURS:
        code, libelle = "bientot", f"Expire dans {j} jours"
    else:
        code, libelle = "valide", ""
    return {"jours": j, "a_renouveler": j <= ALERTE_JOURS, "code": code, "libelle": libelle}
