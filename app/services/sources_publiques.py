"""
Sources publiques de « Mes preuves » (rédaction, vague 5, E2) : ce que les données ouvertes disent
d'une entreprise, PROPOSÉ à l'utilisateur, qui coche ce qui devient une preuve (décision 7 b).

  • DECP — données essentielles de la commande publique (data.economie.gouv.fr, Licence Ouverte) :
    les marchés où le SIREN figure comme titulaire 1, 2 OU 3, avec l'acheteur, l'objet, le montant
    d'attribution, la date et le rôle (seule, en groupement conjoint ou solidaire). Libellé : « marché
    attribué, source publique DECP » : l'attribution ne prouve ni l'exécution ni sa qualité.
  • Liste RGE de l'ADEME (data.ademe.fr, Licence Ouverte) : les qualifications RGE avec leurs dates ;
    une qualification expirée n'est pas proposée, elle est signalée. Qualibat hors RGE n'a pas de
    liste ouverte : sa saisie reste manuelle, avec le certificat.

Règles (étude « rédaction » § 6.7 et § 7) :
  • rien n'est inventé : un champ absent ou illisible reste vide, une valeur bizarre (« CDL »,
    montant de 1 €, date future…) est MONTRÉE TELLE QUELLE avec une alerte, pour que l'utilisateur la
    confirme (ou ne coche pas) ;
  • aucune IA, aucun appel réseau autre que des GET de lecture vers ces API publiques ;
  • un seul point d'entrée HTTP (`_http_get`), simulé dans les tests (les tests n'utilisent JAMAIS
    le réseau) ; délais courts, deux essais au plus ;
  • une panne de l'API = un message honnête (« DECP ne répond pas »), jamais « aucun marché » ;
  • cache en mémoire (un seul process, sans Redis) : 6 heures ; si l'API tombe, la dernière lecture
    de moins de 7 jours est rendue AVEC SA DATE ;
  • la démo (compte et lien partenaire de la vitrine) ne lit jamais le réseau : `exemple_fictif_*`.

Contrat : docs/REDACTION_V5.md, section E2.
"""
import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger("adjugo")

DECP_API = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/decp-2022-marches-valides/records"
DECP_PAGE = "https://data.economie.gouv.fr/explore/dataset/decp-2022-marches-valides/table/?q="
RGE_API = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"
RGE_PAGE = "https://data.ademe.fr/datasets/liste-des-entreprises-rge-2"
SIRENE_API = "https://recherche-entreprises.api.gouv.fr/search"

NOM_DECP = "DECP"
NOM_RGE = "liste RGE de l'ADEME"

HTTP_TIMEOUT = 8.0          # secondes, par appel
ESSAIS = 2                  # un essai, et un second après une micro-coupure
DECP_PAR_PAGE = 100
DECP_PAGES = 3              # au plus 300 lignes (les plus récentes)
RGE_TAILLE = 300
TTL_S = 6 * 3600            # une lecture réussie sert 6 heures
GARDE_S = 7 * 24 * 3600     # API en panne : la dernière lecture de moins de 7 jours est rendue, datée
PANNE_S = 60                # une panne n'est pas relue avant 60 s (pas d'appels en rafale)
CACHE_MAX = 150             # lectures gardées (entreprises), les plus récentes
NOMS_MAX_CACHE = 5000       # noms d'acheteurs gardés
NOMS_PANNE_S = 600          # annuaire en panne : le nom est relu au plus tôt 10 minutes après
NOMS_MAX = 40               # noms d'acheteurs résolus par lecture (le reste : SIRET affiché)
NOMS_BUDGET_S = 6.0
NOMS_TTL_S = 30 * 24 * 3600
FIN_SANS_DATE = 2090        # la liste RGE met « 2099-01-01 » pour une inscription sans date de fin

SELECT_DECP = ("id,objet,montant,datenotification,acheteur_id,nature,codecpv,lieuexecution_code,"
               "titulaire_id_1,titulaire_id_2,titulaire_id_3,typegroupementoperateurs,dureemois,idaccordcadre")
SELECT_RGE = ("siret,nom_entreprise,code_qualification,nom_qualification,nom_certificat,domaine,meta_domaine,"
              "organisme,lien_date_debut,lien_date_fin")

MSG_PANNE = {
    "decp": "Les données des marchés publics (DECP) ne répondent pas pour le moment : rien n'a été lu, "
            "réessayez plus tard.",
    "rge": "La liste RGE de l'ADEME ne répond pas pour le moment : rien n'a été lu, réessayez plus tard.",
}
MSG_ANCIEN = {
    "decp": "Les données des marchés publics (DECP) ne répondent pas pour le moment : voici la lecture du {d}.",
    "rge": "La liste RGE de l'ADEME ne répond pas pour le moment : voici la lecture du {d}.",
}

# Valeurs de remplissage des DECP (« CDL », « MQ NC »…) : un champ qui les porte est NON RENSEIGNÉ.
_VIDES = {"", "cdl", "mq nc", "mqnc", "mq", "nc", "n/c", "n/a", "na", "nd", "null", "none", "nan", "-", "--",
          "0", "inconnu", "non renseigne", "non communique", "sans objet"}

ROLE_LIBELLES = {"seul": "Seule", "groupement_conjoint": "En groupement conjoint",
                 "groupement_solidaire": "En groupement solidaire"}

ORGANISMES = {"qualibat": "Qualibat", "qualifelec": "Qualifelec", "qualitenr": "Qualit'EnR",
              "qualit'enr": "Qualit'EnR", "certibat": "Certibat", "opqibi": "OPQIBI", "cnoa": "Ordre des architectes",
              "afnor": "AFNOR Certification", "cequami": "Cequami", "cerqual": "Cerqual", "ecocert": "Ecocert",
              "lne": "LNE", "certigaz": "Certigaz", "qualipv": "QualiPV"}


def _fold(s) -> str:
    from app.services.faits_a_relire import fold
    return fold(s)


def clean_siren(v) -> str:
    digits = re.sub(r"\D", "", str(v or ""))
    return digits[:9] if len(digits) in (9, 14) else ""


def vide(v) -> bool:
    """Vrai pour un champ absent ou une valeur de remplissage des DECP (« CDL », « MQ NC »…)."""
    return _fold(str(v if v is not None else "")).strip(" .") in _VIDES


def _id_reel(v) -> bool:
    s = str(v or "").strip()
    return bool(s) and not vide(s) and len(re.sub(r"\W", "", s)) >= 5


def aujourd_hui() -> date:
    from app.services.preuves import aujourd_hui as j
    return j()


def _jj(d) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(d or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def _euros(x) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if f == int(f):
        return f"{int(f):,}".replace(",", " ") + " €"
    return f"{f:,.2f}".replace(",", " ").replace(".", ",") + " €"


# ── HTTP : un seul point d'entrée (simulé dans les tests) ─────────────────────────────

def _http_get(url: str, params: dict, timeout: float = HTTP_TIMEOUT) -> dict:
    """GET JSON, UN essai. Lève en cas d'erreur (réseau, HTTP ≠ 200, JSON illisible)."""
    import httpx
    r = httpx.get(url, params=params, timeout=timeout,
                  headers={"User-Agent": "Adjugo/1.0 (+https://adjugo.fr)", "Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("réponse inattendue")
    return data


def _get(url: str, params: dict) -> dict:
    """Deux essais au plus (micro-coupure des API publiques) ; une erreur 4xx n'est pas rejouée."""
    last = None
    for i in range(ESSAIS):
        try:
            return _http_get(url, params)
        except Exception as e:      # noqa: BLE001 — la panne est dite plus haut, jamais un « aucun »
            last = e
            sc = getattr(getattr(e, "response", None), "status_code", None)
            if sc is not None and 400 <= int(sc) < 500 and int(sc) not in (408, 429):
                break
            if i < ESSAIS - 1:
                time.sleep(0.3)
    raise last if last else RuntimeError("source indisponible")


# ── Lectures brutes ───────────────────────────────────────────────────────────────────

def lire_decp(siren: str) -> dict:
    """Les lignes DECP où le SIREN est titulaire 1, 2 OU 3 (les plus récentes d'abord)."""
    s = clean_siren(siren)
    if not s:
        raise ValueError("SIREN invalide")
    from app.services.decp import where_titulaire
    where = where_titulaire(s)
    rows, total = [], None
    for page in range(DECP_PAGES):
        data = _get(DECP_API, {"select": SELECT_DECP, "where": where, "order_by": "-datenotification",
                               "limit": DECP_PAR_PAGE, "offset": page * DECP_PAR_PAGE})
        if total is None:
            try:
                total = int(data.get("total_count") or 0)
            except (TypeError, ValueError):
                total = 0
        lot = [r for r in (data.get("results") or []) if isinstance(r, dict)]
        rows += lot
        if len(lot) < DECP_PAR_PAGE or len(rows) >= (total or 0):
            break
    return {"rows": rows, "total": int(total or len(rows))}


def lire_rge(siren: str) -> dict:
    """Les lignes de la liste RGE de l'ADEME pour tous les établissements du SIREN."""
    s = clean_siren(siren)
    if not s:
        raise ValueError("SIREN invalide")
    data = _get(RGE_API, {"qs": f"siret:{s}*", "size": RGE_TAILLE, "select": SELECT_RGE})
    rows = [r for r in (data.get("results") or []) if isinstance(r, dict)
            and str(r.get("siret") or "").startswith(s)]
    try:
        total = int(data.get("total") or len(rows))
    except (TypeError, ValueError):
        total = len(rows)
    return {"rows": rows, "total": total}


_LECTEURS = {"decp": lire_decp, "rge": lire_rge}

# ── Cache en mémoire (un seul process) ────────────────────────────────────────────────

_CACHE: "OrderedDict" = OrderedDict()
_NOMS: dict = {}
_LOCK = threading.Lock()


def vider_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _NOMS.clear()


def consulter(kind: str, siren: str) -> dict:
    """Lecture brute mise en cache : {statut ok|panne, donnees, consulte_le (jour de Paris),
    consulte_a (UTC), ancien (lecture précédente rendue faute de réponse)}."""
    s = clean_siren(siren)
    key = (kind, s)
    now = time.monotonic()
    with _LOCK:
        e = _CACHE.get(key)
        if e is not None:
            _CACHE.move_to_end(key)
    if e is not None:
        if e.get("ok") and now - e["t"] < TTL_S:
            return dict(e["res"], ancien=False)
        if not e.get("ok") and now - e["t"] < PANNE_S:
            prev = e.get("prev")
            return dict(prev["res"], ancien=True) if prev and now - prev["t"] < GARDE_S else {"statut": "panne"}
    prev = e if (e is not None and e.get("ok")) else (e.get("prev") if e is not None else None)
    try:
        donnees = _LECTEURS[kind](s)
    except Exception as ex:     # noqa: BLE001
        logger.info("Source publique %s indisponible (%s) : %s", kind, s, type(ex).__name__)
        with _LOCK:
            _CACHE[key] = {"ok": False, "t": now, "prev": prev}
            _borner()
        if prev is not None and now - prev["t"] < GARDE_S:
            return dict(prev["res"], ancien=True)
        return {"statut": "panne"}
    res = {"statut": "ok", "donnees": donnees, "consulte_le": aujourd_hui().isoformat(),
           "consulte_a": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    with _LOCK:
        _CACHE[key] = {"ok": True, "t": now, "res": res}
        _borner()
    return dict(res, ancien=False)


def _borner() -> None:
    while len(_CACHE) > CACHE_MAX:
        _CACHE.popitem(last=False)


# ── Noms des acheteurs (annuaire des entreprises, par le SIRET donné dans DECP) ───────

def _nom_sirene(siren: str) -> str:
    data = _http_get(SIRENE_API, {"q": siren, "per_page": 1, "page": 1}, timeout=4.0)
    res = data.get("results") or []
    top = res[0] if res and isinstance(res[0], dict) else None
    if not top or re.sub(r"\D", "", str(top.get("siren") or "")) != siren:
        return ""
    return str(top.get("nom_complet") or top.get("nom_raison_sociale") or "").strip()[:200]


def noms_acheteurs(sirets) -> dict:
    """{siret: nom} pour les acheteurs dont le nom est retrouvé dans l'annuaire des entreprises (par
    leur SIREN), dans un budget borné : au plus NOMS_MAX lectures, 4 en parallèle, NOMS_BUDGET_S au
    total. Un nom non retrouvé n'est jamais deviné : le SIRET reste affiché."""
    out, a_lire = {}, []
    now = time.monotonic()
    for siret in dict.fromkeys(str(x or "").strip() for x in (sirets or [])):
        siren = clean_siren(siret)
        if not siren:
            continue
        with _LOCK:
            e = _NOMS.get(siren)
        if e is not None and now - e[1] < NOMS_TTL_S:
            if e[0]:
                out[siret] = e[0]
            continue
        a_lire.append((siret, siren))
    sirens = list(dict.fromkeys(s for _x, s in a_lire))[:NOMS_MAX]
    if sirens:
        ex = ThreadPoolExecutor(max_workers=min(4, len(sirens)))
        try:
            futs = {ex.submit(_nom_sirene, s): s for s in sirens}
            done, _ = wait(futs, timeout=NOMS_BUDGET_S)
            for fut, s in futs.items():
                if fut not in done:
                    continue
                try:
                    nom, t = fut.result(), now
                except Exception:   # noqa: BLE001 — annuaire en panne : SIRET affiché, relu dans 10 minutes
                    nom, t = "", now - NOMS_TTL_S + NOMS_PANNE_S
                with _LOCK:
                    if len(_NOMS) >= NOMS_MAX_CACHE:
                        _NOMS.clear()
                    _NOMS[s] = (nom, t)
        finally:
            ex.shutdown(wait=False)
    for siret, siren in a_lire:
        with _LOCK:
            e = _NOMS.get(siren)
        if e is not None and e[0]:
            out[siret] = e[0]
    return out


# ── DECP : une ligne → une proposition de référence (sans rien inventer) ──────────────

def _cle(*parts) -> str:
    return hashlib.sha256("|".join(str(p or "") for p in parts).encode()).hexdigest()[:20]


def _couper(s: str, n: int) -> str:
    """Les n premiers caractères, coupés à un espace, suivis de « … »."""
    if len(s) <= n:
        return s
    t = s[:n - 1]
    i = t.rfind(" ")
    if i > n * 0.6:
        t = t[:i]
    return t.rstrip(" ,;:-") + "…"


def normaliser_marche(row: dict, siren: str, jour: date, noms: Optional[dict] = None) -> Optional[dict]:
    """Une ligne DECP → la proposition de référence affichée. None si la ligne ne concerne pas ce SIREN.

    {cle, nature: "reference", decp_id, affiche {objet, acheteur, acheteur_siret, montant, date,
     nature_marche, lieu_code, position, cotitulaires, type_groupement, role, role_libelle},
     valeur (champs de la preuve, ce qui sera enregistré), releve (les champs tirés de DECP),
     alertes [str], manque (str : ne peut pas devenir une référence, et pourquoi)}"""
    s = clean_siren(siren)
    ids = [str(row.get(f"titulaire_id_{i}") or "").strip() for i in (1, 2, 3)]
    pos = next((i + 1 for i, t in enumerate(ids) if s and t.startswith(s)), None)
    if pos is None:
        return None
    autres = sum(1 for i, t in enumerate(ids) if i + 1 != pos and _id_reel(t))
    alertes, manque = [], ""
    valeur = {}
    decp_id = str(row.get("id") or "").strip()
    acheteur_siret = str(row.get("acheteur_id") or "").strip()

    # Objet : tel qu'écrit (majuscules comprises) ; trop long → 300 caractères, texte complet en description.
    objet_brut = row.get("objet")
    objet = re.sub(r"\s+", " ", str(objet_brut if objet_brut is not None else "")).strip()
    if vide(objet):
        manque = (f"Objet du marché non renseigné dans DECP (« {objet} ») : cette ligne ne peut pas devenir "
                  "une référence." if objet else "Objet du marché absent dans DECP : cette ligne ne peut pas "
                                                 "devenir une référence.")
    else:
        if len(objet) > 300:
            valeur["objet"] = _couper(objet, 300)
            valeur["description"] = _couper(objet, 1000)
            alertes.append("Objet long : la fiche en garde le début, le texte complet va dans la description.")
        else:
            valeur["objet"] = objet

    # Acheteur : nom retrouvé dans l'annuaire par le SIRET donné dans DECP, sinon le SIRET seul.
    nom_acheteur = (noms or {}).get(acheteur_siret, "") if acheteur_siret else ""
    if vide(acheteur_siret):
        alertes.append("Acheteur non renseigné dans DECP.")
        acheteur_siret = ""
    elif nom_acheteur:
        valeur["acheteur"] = nom_acheteur[:200]

    # Montant d'attribution : montré tel quel ; repris seulement s'il est possible.
    montant = row.get("montant")
    try:
        m = float(montant) if montant is not None and not isinstance(montant, bool) else None
    except (TypeError, ValueError):
        m = None
    if m is None:
        alertes.append("Montant absent dans DECP." if montant in (None, "") else
                       f"Montant illisible dans DECP (« {montant} ») : il n'est pas repris.")
    elif m != m or m <= 0:
        alertes.append(f"Montant de {_euros(m)} dans DECP : il n'est pas repris dans la fiche.")
    elif m > 1e10:
        alertes.append(f"Montant de {_euros(m)} dans DECP : impossible, il n'est pas repris dans la fiche.")
    else:
        valeur["montant_ht"] = int(m) if m == int(m) else round(m, 2)
        if m < 1000 or m > 50_000_000:
            alertes.append(f"Montant inhabituel dans DECP : {_euros(m)} HT. Cochez seulement s'il est juste.")
    nature_marche = str(row.get("nature") or "").strip()
    # Accord-cadre : la nature le dit, ou la ligne est l'accord-cadre lui-même (son identifiant d'accord-cadre est
    # le sien) ; un marché subséquent (autre identifiant) porte, lui, le montant commandé.
    id_ac = str(row.get("idaccordcadre") or "").strip()
    accord = ("accord" in _fold(nature_marche) and "cadre" in _fold(nature_marche)) or \
        (bool(id_ac) and not vide(id_ac) and id_ac == decp_id)
    if accord:
        alertes.append("Accord-cadre : le montant de DECP est un maximum ou une estimation, pas ce qui a été "
                       "commandé.")

    # Date de notification → année de la référence (si elle est plausible).
    dn = str(row.get("datenotification") or "").strip()[:10]
    try:
        d = date.fromisoformat(dn)
    except ValueError:
        d = None
    if d is None:
        alertes.append("Date de notification absente dans DECP." if not dn or vide(dn) else
                       f"Date illisible dans DECP (« {dn} ») : l'année n'est pas reprise.")
    elif d > jour:
        alertes.append(f"Date dans le futur dans DECP ({_jj(dn)}) : l'année n'est pas reprise.")
    elif d.year < 1990:
        alertes.append(f"Date inhabituelle dans DECP ({_jj(dn)}) : l'année n'est pas reprise.")
    else:
        valeur["annee"] = d.year

    # Rôle : seule, en groupement conjoint ou solidaire — seulement quand DECP le dit sans contradiction.
    tg_brut = str(row.get("typegroupementoperateurs") or "").strip()
    tg = _fold(tg_brut)
    role = ""
    if "solidaire" in tg:
        role = "groupement_solidaire"
    elif "conjoint" in tg:
        role = "groupement_conjoint"
    elif "pas de groupement" in tg:
        if autres:
            alertes.append("DECP indique « pas de groupement » et plusieurs titulaires : précisez votre rôle "
                           "après l'ajout.")
        else:
            role = "seul"
    if role:
        valeur["role"] = role
    lib = ROLE_LIBELLES.get(role, "Rôle non précisé dans DECP")
    if role.startswith("groupement") and autres:
        lib += f", avec {autres} autre{'s' if autres > 1 else ''} entreprise{'s' if autres > 1 else ''}"

    releve = dict(valeur)
    return {
        "cle": "decp:" + _cle(decp_id, row.get("acheteur_id"), pos, dn),
        "nature": "reference", "decp_id": decp_id,
        "affiche": {"objet": objet, "acheteur": nom_acheteur, "acheteur_siret": acheteur_siret,
                    "montant": m if m is not None else (montant if montant not in (None, "") else None),
                    "date": dn, "nature_marche": nature_marche,
                    "lieu_code": "" if vide(row.get("lieuexecution_code")) else str(row.get("lieuexecution_code")),
                    "position": pos, "cotitulaires": autres, "type_groupement": tg_brut,
                    "role": role, "role_libelle": lib},
        "valeur": valeur, "releve": releve, "alertes": alertes, "manque": manque,
    }


def source_decp(prop: dict, consulte_le: str) -> dict:
    """La source enregistrée avec la preuve (type « public ») : datée, avec l'identifiant du marché."""
    ident = f"marché {prop.get('decp_id') or '?'}"
    sir = (prop.get("affiche") or {}).get("acheteur_siret") or ""
    if sir:
        ident += f", acheteur {sir}"
    return {"nom": NOM_DECP, "url": DECP_PAGE + quote(str(prop.get("decp_id") or ""), safe=""),
            "consulte_le": consulte_le, "identifiant": ident[:120], "releve": dict(prop.get("releve") or {})}


def marches(siren: str, *, avec_noms: bool = True) -> dict:
    """Les marchés DECP de l'entreprise, proposés (rien n'est enregistré ici).
    {statut ok|panne|siren_invalide, message, consulte_le, ancien, total, lus, tronque, marches: [...]}."""
    s = clean_siren(siren)
    if not s:
        return {"statut": "siren_invalide", "marches": []}
    r = consulter("decp", s)
    if r.get("statut") != "ok":
        return {"statut": "panne", "message": MSG_PANNE["decp"], "marches": []}
    rows = (r.get("donnees") or {}).get("rows") or []
    total = int((r.get("donnees") or {}).get("total") or len(rows))
    noms = noms_acheteurs([x.get("acheteur_id") for x in rows if _id_reel(x.get("acheteur_id"))]) if avec_noms else {}
    jour = aujourd_hui()
    out, vus = [], set()
    for row in rows:
        k = (str(row.get("id") or ""), str(row.get("acheteur_id") or ""))
        if k in vus and k != ("", ""):
            continue                     # même marché lu deux fois (modification publiée) : une seule ligne
        vus.add(k)
        p = normaliser_marche(row, s, jour, noms)
        if p is not None:
            out.append(p)
    res = {"statut": "ok", "consulte_le": r.get("consulte_le"), "ancien": bool(r.get("ancien")),
           "total": total, "lus": len(rows), "tronque": total > len(rows), "marches": out}
    if r.get("ancien"):
        res["message"] = MSG_ANCIEN["decp"].format(d=_jj(r.get("consulte_le")))
    return res


# ── Liste RGE : des lignes (une par domaine) → une qualification proposée ─────────────

def _organisme(code: str) -> str:
    c = _fold(code)
    return ORGANISMES.get(c, str(code or "").strip()[:120])


def _date_iso(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v or "").strip()[:10])
    except ValueError:
        return None


def normaliser_rge(rows: list, jour: date) -> tuple:
    """(valables, expirees). Une qualification = un code, un organisme, un certificat et une fin de
    validité ; ses domaines (une ligne chacun dans la liste) sont regroupés. Une qualification dont la
    fin est dépassée n'est PAS proposée : elle est signalée."""
    groupes = OrderedDict()
    for r in rows or []:
        code = str(r.get("code_qualification") or "").strip()
        nomq = re.sub(r"\s+", " ", str(r.get("nom_qualification") or "")).strip()
        if not nomq and not code:
            continue
        cle = (code, _fold(r.get("organisme")), _fold(r.get("nom_certificat")), str(r.get("lien_date_fin") or "")[:10],
               _fold(nomq))
        g = groupes.setdefault(cle, {"rows": [], "domaines": [], "sirets": []})
        g["rows"].append(r)
        dom = re.sub(r"\s+", " ", str(r.get("domaine") or "")).strip()
        if dom and dom not in g["domaines"]:
            g["domaines"].append(dom)
        sir = str(r.get("siret") or "").strip()
        if sir and sir not in g["sirets"]:
            g["sirets"].append(sir)
    valables, expirees = [], []
    for (code, _org, _cert, fin_s, _n), g in groupes.items():
        r = g["rows"][0]
        nomq = re.sub(r"\s+", " ", str(r.get("nom_qualification") or "")).strip()
        cert = re.sub(r"\s+", " ", str(r.get("nom_certificat") or "")).strip()
        nom = nomq or code
        if cert and _fold(cert) not in _fold(nom):
            nom = f"{cert} : {nom}"
        if len(nom) > 200:
            nom = _couper(nom, 200)
        debut = _date_iso(r.get("lien_date_debut"))
        fin = _date_iso(r.get("lien_date_fin"))
        sans_fin = fin is not None and fin.year >= FIN_SANS_DATE
        valeur = {"nom": nom}
        organisme = _organisme(r.get("organisme"))
        if organisme:
            valeur["organisme"] = organisme
        if code:
            valeur["numero"] = code[:60]
        details = []
        if debut is not None:
            details.append(f"RGE depuis le {debut.strftime('%d/%m/%Y')}")
        if g["domaines"]:
            details.append("domaines : " + " ; ".join(g["domaines"]))
        if details:
            valeur["detail"] = _couper(", ".join(details), 300)
        alertes = []
        if fin is None:
            alertes.append("Date de fin absente dans la liste RGE : une fois la fiche ajoutée, indiquez celle de votre certificat.")
        elif sans_fin:
            alertes.append("Inscrite sans date de fin dans la liste RGE.")
        prop = {
            "cle": "rge:" + _cle(code, r.get("organisme"), cert, fin_s, nomq),
            "nature": "qualification",
            "affiche": {"nom": nom, "organisme": organisme, "code": code, "certificat": cert,
                        "domaines": g["domaines"], "sirets": g["sirets"],
                        "date_debut": debut.isoformat() if debut else None,
                        "date_fin": fin.isoformat() if (fin is not None and not sans_fin) else None},
            "valeur": valeur, "date_fin_validite": fin.isoformat() if (fin is not None and not sans_fin) else None,
            "releve": dict(valeur), "alertes": alertes, "manque": "",
        }
        # La fin de validité est relevée quand la liste la donne (une date, ou « sans date de fin ») ; absente,
        # l'utilisateur la reporte depuis son certificat.
        if fin is not None:
            prop["releve"]["date_fin_validite"] = prop["date_fin_validite"]
        if fin is not None and not sans_fin and fin < jour:
            prop["message"] = (f"Expirée le {fin.strftime('%d/%m/%Y')} selon la liste RGE : Adjugo ne la propose pas. "
                               "Si elle a été renouvelée, ajoutez-la avec son nouveau certificat.")
            expirees.append(prop)
        else:
            valables.append(prop)
    return valables, expirees


def source_rge(prop: dict, consulte_le: str) -> dict:
    a = prop.get("affiche") or {}
    ident = (f"SIRET {a['sirets'][0]}" if a.get("sirets") else "liste RGE")
    if a.get("code"):
        ident += f", qualification {a['code']}"
    return {"nom": NOM_RGE, "url": RGE_PAGE, "consulte_le": consulte_le, "identifiant": ident[:120],
            "releve": dict(prop.get("releve") or {})}


def qualifications_rge(siren: str) -> dict:
    """Les qualifications RGE de l'entreprise, proposées (rien n'est enregistré ici).
    {statut, message, consulte_le, ancien, total, tronque, qualifications: [...], expirees: [...]}."""
    s = clean_siren(siren)
    if not s:
        return {"statut": "siren_invalide", "qualifications": [], "expirees": []}
    r = consulter("rge", s)
    if r.get("statut") != "ok":
        return {"statut": "panne", "message": MSG_PANNE["rge"], "qualifications": [], "expirees": []}
    rows = (r.get("donnees") or {}).get("rows") or []
    total = int((r.get("donnees") or {}).get("total") or len(rows))
    valables, expirees = normaliser_rge(rows, aujourd_hui())
    res = {"statut": "ok", "consulte_le": r.get("consulte_le"), "ancien": bool(r.get("ancien")), "total": total,
           "tronque": total > len(rows), "qualifications": valables, "expirees": expirees}
    if r.get("ancien"):
        res["message"] = MSG_ANCIEN["rge"].format(d=_jj(r.get("consulte_le")))
    return res


# ── Démo : données FICTIVES, jamais le réseau ─────────────────────────────────────────

BANDEAU_FICTIF = ("Exemple fictif de la démonstration : ces marchés et ces qualifications n'existent pas. Avec votre "
                  "compte, Adjugo les lit dans les données publiques à partir de votre SIRET.")
SIREN_FICTIF = "000000000"

_DECP_FICTIF = [
    {"id": "FICTIF-2025-014", "objet": "Exemple fictif - Réfection de la couverture en ardoise de la salle des sports",
     "montant": 142380.5, "datenotification": "2025-06-12", "acheteur_id": "FICTIF-ACHETEUR-1", "nature": "Marché",
     "titulaire_id_1": SIREN_FICTIF + "00011", "titulaire_id_2": "CDL", "titulaire_id_3": "CDL",
     "typegroupementoperateurs": "Pas de groupement", "lieuexecution_code": "29"},
    {"id": "FICTIF-2024-203", "objet": "Exemple fictif - Rénovation énergétique du groupe scolaire, lot 3 : couverture et "
                                       "isolation de la toiture",
     "montant": 268900.0, "datenotification": "2024-09-03", "acheteur_id": "FICTIF-ACHETEUR-2", "nature": "Marché",
     "titulaire_id_1": "11111111100018", "titulaire_id_2": SIREN_FICTIF + "00011", "titulaire_id_3": "CDL",
     "typegroupementoperateurs": "Solidaire", "lieuexecution_code": "56"},
    {"id": "FICTIF-2023-077", "objet": "Exemple fictif - Entretien des toitures des bâtiments communaux",
     "montant": 1.0, "datenotification": "2023-02-20", "acheteur_id": "FICTIF-ACHETEUR-1", "nature": "Accord-cadre",
     "titulaire_id_1": SIREN_FICTIF + "00011", "titulaire_id_2": "CDL", "titulaire_id_3": "CDL",
     "typegroupementoperateurs": "Pas de groupement", "lieuexecution_code": "29"},
]
_NOMS_FICTIFS = {"FICTIF-ACHETEUR-1": "Commune fictive de Marvejac", "FICTIF-ACHETEUR-2": "Communauté fictive de Kerhel"}
_RGE_FICTIF = [
    {"siret": SIREN_FICTIF + "00011", "code_qualification": "FICTIF-5112", "nom_qualification":
        "Exemple fictif - Isolation des toitures par l'extérieur", "nom_certificat": "QUALIBAT-RGE", "organisme": "qualibat",
     "domaine": "Isolation des toitures terrasses ou des toitures par l'extérieur", "lien_date_debut": "2024-03-01",
     "lien_date_fin": "2028-02-29"},
    {"siret": SIREN_FICTIF + "00011", "code_qualification": "FICTIF-5112", "nom_qualification":
        "Exemple fictif - Isolation des toitures par l'extérieur", "nom_certificat": "QUALIBAT-RGE", "organisme": "qualibat",
     "domaine": "Isolation des murs par l'extérieur", "lien_date_debut": "2024-03-01", "lien_date_fin": "2028-02-29"},
    {"siret": SIREN_FICTIF + "00011", "code_qualification": "FICTIF-8611", "nom_qualification":
        "Exemple fictif - Fenêtres de toit", "nom_certificat": "QUALIBAT-RGE", "organisme": "qualibat",
     "domaine": "Fenêtres, volets, portes extérieures", "lien_date_debut": "2021-01-15", "lien_date_fin": "2025-01-14"},
]


def exemple_fictif_marches() -> dict:
    jour = aujourd_hui()
    out = [normaliser_marche(r, SIREN_FICTIF, jour, _NOMS_FICTIFS) for r in _DECP_FICTIF]
    return {"statut": "exemple", "exemple_fictif": True, "message": BANDEAU_FICTIF, "consulte_le": jour.isoformat(),
            "ancien": False, "total": len(out), "lus": len(out), "tronque": False, "marches": [p for p in out if p]}


def exemple_fictif_rge() -> dict:
    jour = aujourd_hui()
    valables, expirees = normaliser_rge(_RGE_FICTIF, jour)
    return {"statut": "exemple", "exemple_fictif": True, "message": BANDEAU_FICTIF, "consulte_le": jour.isoformat(),
            "ancien": False, "total": len(_RGE_FICTIF), "tronque": False, "qualifications": valables,
            "expirees": expirees}
