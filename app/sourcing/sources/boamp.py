"""
Source AO : BOAMP (Bulletin Officiel des Annonces de Marchés Publics).
API open data v2.1 — https://www.boamp.fr/api/explore/v2.1
Aucune clé requise. Données réelles, traçables par idweb + url_avis.
"""
import json
import re
import logging
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urljoin

import httpx

from app.sourcing.base import ResultatsSource, TenderSource, TenderCriteria
from app.sourcing.dates_fr import date_iso, date_unique
from app.sourcing.schemas import NormalizedTender, Provenance

logger = logging.getLogger("adjugo")
API = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"
# annonce_lie, nature, etat, contractfolderid : de quoi reconnaître, dans les résultats mêmes, un rectificatif
# ou une annulation au format européen (publiés avec une date limite, donc renvoyés comme des avis ouverts).
SELECT = ("idweb,objet,nomacheteur,code_departement,dateparution,datelimitereponse,"
          "descripteur_libelle,descripteur_code,nature_libelle,famille_libelle,"
          "url_avis,type_marche,procedure_libelle,annonce_lie,nature,etat,contractfolderid")
# Rectificatifs et annulations (lot 1, point 2) : le corps (`donnees`) n'est demandé que pour eux, car la
# nouvelle date d'un rectificatif national ou simplifié n'est écrite que là (`infosRectif`). Rien du corps
# n'est gardé (il contient les contacts de l'acheteur) : seuls la date lue, la date de parution et le lien
# du rectificatif sont retenus.
SELECT_SUITES = ("idweb,annonce_lie,nature,etat,famille,dateparution,datelimitereponse,"
                 "contractfolderid,url_avis,donnees")
# Identifiant d'avis BOAMP (idweb), ex. « 24-123456 » : seul format accepté pour reconstruire
# une URL d'avis côté serveur (jamais d'URL arbitraire venue du client).
_IDWEB = re.compile(r"^\d{2}-\d{1,9}$")
# Lien d'un avis par sa référence : la forme de `url_avis` observée dans les données (« …?q=idweb:26-90336 »).
_URL_AVIS = "https://www.boamp.fr/pages/avis/?q=idweb:{}"
# Rectificatifs récents relus pour retrouver un avis dont seule l'ANCIENNE date limite est passée (repoussée
# depuis) : fenêtre de parution en jours, et nombre de lignes au plus (une page de l'API).
_FENETRE_RECTIFICATIFS = 60
_MAX_SUITES = 100
# Avis initiaux relus par leur référence, au plus (autant que de rectificatifs lus : une page de l'API).
_MAX_RELUS = 100
# Temps laissé aux requêtes complémentaires, compté depuis le début de la recherche BOAMP, sous le délai global
# de la recherche (14 s, app/sourcing/search.py) : au-delà, les avis sont rendus tels que publiés, comme avant.
_BUDGET_SUITES = 9.0


def _aujourdhui() -> date:
    """« Aujourd'hui » du serveur (UTC en production) ; un seul point, que les tests figent."""
    return date.today()


class BoampSource(TenderSource):
    name = "BOAMP"
    supported_filters = {"query", "departements"}

    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        from app.sourcing.http import safe_terms
        # Mots-clés : on découpe en TERMES et on les combine en OU (pas en ET). Taper
        # « musée scénographie expositions » trouve tout ce qui touche À L'UN d'eux, pas
        # seulement les marchés qui contiennent les trois. Et chaque terme d'au moins 5
        # lettres est cherché en PRÉFIXE élargi (« plomb* ») → « plombier » trouve aussi
        # « plomberie ». safe_terms a déjà neutralisé l'injection ODSQL (quotes retirées).
        raw = safe_terms(criteria.query)
        terms = [t for t in raw.split(" ") if len(t) >= 3][:6] or ["travaux"]

        def _kw_clause(term: str) -> str:
            pat = term if len(term) <= 4 else term[:max(4, len(term) - 3)] + "*"
            return f'objet like "{pat}" OR descripteur_libelle like "{pat}"'

        debut = time.monotonic()
        kw = "(" + " OR ".join(f"({_kw_clause(t)})" for t in terms) + ")"
        where = kw
        # Les codes CPV saisis (« Recherche détaillée », « Europe / TED ») ne sont PAS cherchés dans le BOAMP :
        # son `descripteur_code` est un vocabulaire interne (« 45 » = « Cd, DVD »), pas un code européen
        # (lot 1, point 3) ; l'élargissement sur ce champ ramenait des avis sans rapport. TED, lui, les lit.
        deps = ""
        if criteria.departements:
            # Le BOAMP enregistre les départements 01 à 09 SANS zéro (« 6 » pour les
            # Alpes-Maritimes) : on interroge les deux formes, sinon ces départements ne
            # remontaient rien. Les avis sont ensuite ramenés à « 06 » (_normalize).
            formes = [f for d in criteria.departements for f in formes_boamp(d)]
            deps = " OR ".join(f'code_departement like "{f}"' for f in dict.fromkeys(formes))
            where = f"({where}) AND ({deps})"
        if getattr(criteria, "type_marche", "") in ("TRAVAUX", "SERVICES", "FOURNITURES"):
            where = f'({where}) AND type_marche like "{criteria.type_marche}"'
        # On ne remonte que les AO ENCORE OUVERTS (date limite de réponse non passée).
        # Exclut de fait les avis d'attribution / clôturés → crédibilité du sourcing.
        where = f"({where}) AND datelimitereponse >= date'{_aujourdhui().isoformat()}'"
        params = {"limit": min(criteria.limit, 50), "offset": min(getattr(criteria, "offset", 0), 9900),
                  "order_by": "-dateparution", "where": where, "select": SELECT}
        try:
            from app.sourcing.http import get_with_retry
            r = get_with_retry(API, params=params, timeout=12)   # retry + backoff
            rows = r.json().get("results", [])
        except Exception as e:
            logger.warning("BOAMP indisponible : %s", e)
            raise
        # Rectificatifs et annulations rattachés à leur avis (lot 1, point 2). Une erreur ici ne coûte jamais
        # la recherche : les avis sont alors rendus tels que publiés, comme avant, et le journal le dit.
        # Le nombre de lignes reçues accompagne les fiches (ResultatsSource) : « Charger plus » se juge sur lui, car
        # les fiches d'une page peuvent être moins nombreuses (avis annulé retiré, rectificatif européen réuni à son
        # avis) ou plus nombreuses (avis repris par leur rectificatif).
        try:
            return ResultatsSource(self._avec_suites(rows, kw, deps, criteria, debut), lignes_lues=len(rows))
        except Exception as e:      # noqa: BLE001
            logger.warning("BOAMP : rectificatifs et annulations non vérifiés (%s) ; avis rendus tels que "
                           "publiés", type(e).__name__)
            return ResultatsSource([self._normalize(row) for row in rows], lignes_lues=len(rows))

    # ── Rectificatifs et annulations (lot 1 « Dire juste », point 2 ; docs/MOTEUR_LOT1.md § Sources) ──────────
    # Une procédure, une fiche : la fiche garde la référence et le lien de l'avis INITIAL ; un rectificatif
    # rattaché par `annonce_lie` change sa date limite (la nouvelle date lue, sinon « non précisée » : jamais
    # l'ancienne ni une date devinée) et reste consultable par son propre lien ; une annulation retire l'avis.

    def _get_suites(self, where: str, select: str, limit: int, debut: float) -> list:
        """Une requête complémentaire, bornée par le temps restant (un seul essai : jamais de quoi faire
        dépasser le délai global de la recherche). Lève si elle échoue : l'appelant décide."""
        reste = _BUDGET_SUITES - (time.monotonic() - debut)
        if reste < 1.0:
            raise TimeoutError("temps de recherche écoulé")
        from app.sourcing.http import get_with_retry
        params = {"limit": limit, "order_by": "-dateparution", "where": where, "select": select}
        r = get_with_retry(API, params=params, timeout=min(6.0, reste), tries=1)
        return r.json().get("results", []) or []

    def _avec_suites(self, rows: list, kw: str, deps: str, criteria, debut: float) -> list:
        today = _aujourdhui().isoformat()
        premiere_page = not getattr(criteria, "offset", 0)
        affiches = [r for r in rows if not _est_suite(r)]
        suites = {}
        for r in rows:
            if _est_suite(r) and _idweb(r):
                suites.setdefault(_idweb(r), r)

        # 1) Une requête de plus : les rectificatifs et annulations des avis affichés (par `annonce_lie`) ; en
        #    première page, aussi les rectificatifs récents de la même recherche, qui retrouvent un avis dont
        #    seule l'ancienne date est passée (26-90336 : limite du 16/10 repoussée au 06/11 par 26-96286).
        liens = [i for i in dict.fromkeys([_idweb(r) for r in affiches]
                                          + [lien for r in suites.values() for lien in _liens(r)])
                 if _IDWEB.match(i)]
        parties = []
        if liens:
            parties.append('(nature="RECTIFICATIF" OR nature="ANNULATION" OR etat="RECTIFICATIF" '
                           'OR etat="ANNULATION") AND annonce_lie in ('
                           + ", ".join(f'"{i}"' for i in liens) + ")")
        if premiere_page:
            depuis = (_aujourdhui() - timedelta(days=_FENETRE_RECTIFICATIFS)).isoformat()
            partie = f"nature=\"RECTIFICATIF\" AND dateparution >= date'{depuis}' AND {kw}"
            parties.append(f"{partie} AND ({deps})" if deps else partie)
        if parties:
            try:
                complement = self._get_suites(" OR ".join(f"({p})" for p in parties), SELECT_SUITES,
                                              _MAX_SUITES, debut)
                for r in complement:
                    if _est_suite(r) and _idweb(r):
                        suites.setdefault(_idweb(r), r)
                if len(complement) >= _MAX_SUITES:
                    logger.info("BOAMP : %d rectificatifs ou annulations lus, plafond atteint ; les plus anciens "
                                "ne sont pas rattachés", len(complement))
            except Exception as e:      # noqa: BLE001
                logger.warning("BOAMP : rectificatifs et annulations récents non lus (%s) ; seuls ceux renvoyés "
                               "avec les avis sont appliqués", type(e).__name__)

        par_racine, annules, annules_dossier = self._rattacher(affiches, suites)
        par_id = {_idweb(r): r for r in affiches}

        # 2) Un avis initial que seul son rectificatif rend encore ouvert (première page) : relu par sa
        #    référence, avec les annulations qui le visent. Rien n'est repêché sur une date non lue. Seul un avis
        #    dont la date limite PUBLIÉE est déjà passée est repris (`datelimitereponse < aujourd'hui`, dans la
        #    requête et après lecture) : un avis encore ouvert sous son ancienne date est déjà trouvé par la requête
        #    principale, sur sa propre page, avec son rectificatif ; le reprendre ici gonflait la première page
        #    (jusqu'à 50 fiches de plus) et le montrait deux fois en paginant (relecture du lot 1, docs/MOTEUR_LOT1.md).
        a_relire = []
        if premiere_page:
            for racine, rects in par_racine.items():
                if racine in par_id or racine in annules or not _IDWEB.match(racine):
                    continue
                if any(_au_format_europeen(r) for r in rects):
                    continue        # avis européen rectifié : sa version complète est déjà dans les résultats
                fin = _date_finale(rects)
                if fin and fin >= today:
                    a_relire.append(racine)
        repeches = []
        if a_relire:
            if len(a_relire) > _MAX_RELUS:
                # Jamais en silence : le journal dit combien d'avis ne sont pas relus (les plus anciens rectificatifs).
                logger.info("BOAMP : %d avis initiaux de rectificatifs à relire, plafond de %d atteint ; %d non relus",
                            len(a_relire), _MAX_RELUS, len(a_relire) - _MAX_RELUS)
            a_relire = a_relire[:_MAX_RELUS]
            ids = ", ".join(f'"{i}"' for i in a_relire)
            try:
                lignes = self._get_suites(f"(idweb in ({ids}) AND datelimitereponse < date'{today}') OR "
                                          f'((nature="ANNULATION" OR etat="ANNULATION") AND annonce_lie in ({ids}))',
                                          SELECT, _MAX_SUITES, debut)
                if len(lignes) >= _MAX_SUITES:
                    logger.info("BOAMP : %d lignes relues pour les avis initiaux des rectificatifs, plafond atteint",
                                len(lignes))
                for r in lignes:
                    if _est_annulation(r):
                        annules.update(_liens(r))
                        continue
                    publiee = _date_iso_champ(r.get("datelimitereponse"))
                    if (not _est_suite(r) and _idweb(r) in a_relire and _idweb(r) not in par_id
                            and publiee and publiee < today):
                        repeches.append(r)
            except Exception as e:      # noqa: BLE001
                logger.warning("BOAMP : avis initiaux des rectificatifs non relus (%s)", type(e).__name__)
        ids_repeches = {_idweb(r) for r in repeches}

        out, retires, rectifies, non_lues, repris = [], 0, 0, 0, 0
        for r in affiches + repeches:
            i = _idweb(r)
            if i in annules or (_dossier(r) and _dossier(r) in annules_dossier):
                retires += 1
                continue
            t = self._normalize(r)
            if par_racine.get(i):
                self._appliquer(t, par_racine[i])
                rectifies += 1
            if i in ids_repeches:
                if not (t.date_limite and t.date_limite >= today):
                    continue
                repris += 1
            non_lues += int(t.date_limite_rectifiee_non_lue)
            out.append(t)

        # 3) Un rectificatif au format européen renvoyé seul (son avis initial n'est pas dans la page) : c'est une
        #    version complète de l'avis ; il prend la référence et le lien de son avis initial, pour rester la
        #    même fiche (alertes, page suivante, dossier analysé) ; une seule fiche par avis initial.
        vus = set(par_id) | ids_repeches
        for r in rows:
            if not (_est_suite(r) and _au_format_europeen(r)) or _est_annulation(r):
                continue
            racines = self._racines(r, suites, affiches)
            if racines & vus:
                continue
            if racines & annules or (_dossier(r) and _dossier(r) in annules_dossier):
                retires += 1
                continue
            racine = sorted(racines)[0] if racines else ""
            t = self._normalize(r)
            if racine and _IDWEB.match(racine):
                t.provenance = Provenance(source=self.name, source_url=_URL_AVIS.format(racine),
                                          official_ref=racine)
                vus.add(racine)
            self._appliquer(t, par_racine.get(racine) or [r])
            rectifies += 1
            out.append(t)
        if rectifies or retires or repris:
            logger.info("BOAMP : %d avis rectifié(s) (dont %d date(s) non lue(s)), %d annulé(s) retiré(s), "
                        "%d repris par leur rectificatif", rectifies, non_lues, retires, repris)
        return out

    @staticmethod
    def _racines(r: dict, suites: dict, affiches: list) -> set:
        """Avis initiaux visés par une suite : `annonce_lie` (en remontant un rectificatif de rectificatif) ;
        à défaut, l'avis affiché du même dossier européen (`contractfolderid`)."""
        racines = set()
        for lien in _liens(r):
            cur, vus = lien, set()
            while cur in suites and cur not in vus and len(vus) < 5:
                vus.add(cur)
                suivant = _liens(suites[cur])
                if not suivant:
                    break
                cur = suivant[0]
            if cur and cur not in suites:
                racines.add(cur)
        if not racines and _dossier(r):
            racines = {_idweb(a) for a in affiches if _dossier(a) == _dossier(r) and _idweb(a)}
        racines.discard(_idweb(r))
        return racines

    def _rattacher(self, affiches: list, suites: dict):
        """({avis initial: [rectificatifs]}, références annulées, dossiers européens annulés)."""
        par_racine, annules, annules_dossier = defaultdict(list), set(), set()
        for r in suites.values():
            racines = self._racines(r, suites, affiches)
            if _est_annulation(r):
                annules |= racines
                if _dossier(r):
                    annules_dossier.add(_dossier(r))
            else:
                for racine in racines:
                    par_racine[racine].append(r)
        return par_racine, annules, annules_dossier

    def _appliquer(self, t: NormalizedTender, rects: list) -> None:
        """Applique à la fiche `t` ses rectificatifs, du plus ancien au plus récent : le dernier qui parle de la
        date limite la fixe (lue sans doute possible, sinon vide et signalée « non lue »)."""
        rects = sorted(rects, key=_ordre)
        date_avant, date_courante, concerne = t.date_limite, t.date_limite, False
        for r in rects:
            lecture = lire_rectificatif(r)
            if lecture["concerne"]:
                concerne = True
                date_courante = lecture["date"]
        t.rectificatifs = [Provenance(source=self.name, official_ref=_idweb(r),
                                      source_url=(r.get("url_avis") or _URL_AVIS.format(_idweb(r))))
                           for r in rects if _idweb(r)]
        t.rectifie_le = max(((r.get("dateparution") or "")[:10] for r in rects), default="") or None
        if concerne:
            if date_courante != date_avant:
                t.date_limite_initiale = date_avant
                t.date_limite = date_courante
            t.date_limite_rectifiee_non_lue = date_courante is None
        t.confidence = self._confidence(t)
        t.dedup_key = _dedup_key(t)

    def _normalize(self, r: dict) -> NormalizedTender:
        idweb = str(r.get("idweb", "") or "")
        deps = r.get("code_departement") or []
        if not isinstance(deps, list):
            deps = [str(deps)]
        desc = r.get("descripteur_libelle") or []
        url_avis = r.get("url_avis", "") or f"https://www.boamp.fr/avis/detail/{idweb}"

        t = NormalizedTender(
            objet=(r.get("objet") or "").strip()[:400] or "Objet non précisé",
            acheteur=_as_str(r.get("nomacheteur")),
            # Aucun code CPV : `descripteur_code` est le vocabulaire interne du BOAMP (« 45 » = « Cd, DVD »),
            # jamais un code métier européen (lot 1, point 3). Il reste dans `raw`.
            cpv=[],
            date_publication=(r.get("dateparution") or "")[:10] or None,
            date_limite=(r.get("datelimitereponse") or "")[:10] or None,
            lieu=", ".join(desc) if isinstance(desc, list) and desc else None,
            departements=[dept_canonique(d) for d in deps if str(d or "").strip()],
            procedure=_as_str(r.get("procedure_libelle")),
            nature=_as_str(r.get("type_marche")) or _as_str(r.get("nature_libelle")),
            dce_url=None,  # rempli à l'analyse profonde si accessible
            provenance=Provenance(source=self.name, source_url=url_avis, official_ref=idweb),
            raw=r,
        )
        t.confidence = self._confidence(t)
        t.dedup_key = _dedup_key(t)
        return t

    @staticmethod
    def _confidence(t: NormalizedTender) -> float:
        """Confiance = complétude des champs clés (jamais un nombre arbitraire)."""
        # Les descripteurs du BOAMP comptent comme un champ renseigné, comme avant le lot 1 (ils étaient alors
        # rangés à tort dans `cpv`) : la complétude d'un avis ne change pas pour autant.
        descripteurs = (t.raw or {}).get("descripteur_code") or (t.raw or {}).get("descripteur_libelle")
        keys = [t.objet and t.objet != "Objet non précisé", t.acheteur,
                t.date_limite, bool(t.departements), bool(t.cpv) or bool(descripteurs), t.procedure]
        present = sum(1 for k in keys if k)
        return round(present / len(keys), 2)

    def fetch_dce(self, tender: NormalizedTender) -> Optional[str]:
        """Tente de récupérer le texte réel du DCE. Retourne None si inaccessible
        (jamais de DCE inventé en repli)."""
        # ANTI-SSRF : l'objet AO arrive du navigateur (/api/sourcing/analyze) → source_url
        # est une donnée CLIENT. On n'appelle donc QUE des URLs https vers boamp.fr (liste
        # blanche), IP publiques vérifiées après résolution, redirections revalidées à chaque
        # saut, corps borné (app/core/safe_fetch.py). URL hors liste → on la reconstruit
        # depuis l'identifiant officiel BOAMP, sinon rien (jamais de DCE inventé).
        from app.core.safe_fetch import DCE_HOSTS, safe_get
        url = self._safe_avis_url(tender)
        if not url:
            return None
        try:
            with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(10.0, connect=5.0),
                              headers={"User-Agent": "AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)"}) as c:
                resp = safe_get(url, DCE_HOSTS, max_bytes=5 * 1024 * 1024, client=c)
                if resp.status_code != 200:
                    return None
                pdf_links = re.findall(r'href="([^"]+\.pdf[^"]*)"', resp.text, re.I)
                for link in pdf_links[:5]:
                    link = urljoin(resp.url, link)
                    try:
                        p = safe_get(link, DCE_HOSTS, client=c)   # revalide hôte + IP
                        if p.status_code == 200 and "pdf" in p.headers.get("content-type", "").lower():
                            from app.services.analysis import extract_text_from_pdf
                            txt = extract_text_from_pdf(p.content, max_chars=120000)
                            if txt and len(txt) > 300 and not txt.startswith("Erreur"):
                                return txt
                    except Exception:   # URL refusée, trop grosse ou injoignable → lien suivant
                        continue
                # Pas de PDF DCE exploitable → None (l'avis sera analysé à part,
                # honnêtement labellisé « DCE non accessible »). Jamais de DCE inventé.
                return None
        except Exception as e:
            logger.info("DCE BOAMP non récupéré (%s) : %s", url, e)
            return None

    @staticmethod
    def _safe_avis_url(tender: NormalizedTender) -> Optional[str]:
        """URL de l'avis à appeler : la source_url si elle passe la liste blanche (https,
        boamp.fr), sinon l'URL officielle reconstruite depuis l'idweb ; None sinon."""
        from app.core.safe_fetch import DCE_HOSTS, UnsafeURL, validate_url
        url = (tender.provenance.source_url or "").strip()
        try:
            return validate_url(url, DCE_HOSTS, resolve=False)
        except UnsafeURL:
            pass
        ref = (tender.provenance.official_ref or "").strip()
        if _IDWEB.match(ref):
            return f"https://www.boamp.fr/avis/detail/{ref}"
        return None


# La Corse au BOAMP : « 20A » (Corse-du-Sud) et « 20B » (Haute-Corse), jamais « 2A » / « 2B » ni « 20 » (valeurs
# de code_departement relevées le 21/10/2026 sur les avis parus depuis le 01/09 : 142 « 20A », 112 « 20B », aucun
# « 2A », « 2B » ou « 20 » ; docs/MOTEUR_LOT1.md, réunion des chantiers). Avant, une recherche « 2A » ne ramenait
# aucun avis du BOAMP, et un avis corse portait « 20A », hors de toute zone.
_CORSE_BOAMP = {"20A": "2A", "20B": "2B"}


def dept_canonique(d) -> str:
    """Forme unique d'un département dans Adjugo : deux chiffres (« 6 » → « 06 »), Corse
    « 2A »/« 2B » (« 20A »/« 20B » du BOAMP compris), outre-mer sur trois chiffres (« 974 »). Une valeur
    inattendue est rendue telle quelle (jamais devinée)."""
    s = str(d or "").strip().upper()
    if s in _CORSE_BOAMP:
        return _CORSE_BOAMP[s]
    return s.zfill(2) if (s.isdigit() and len(s) == 1) else s


def formes_boamp(d) -> list:
    """Formes à demander au BOAMP pour un département : « 06 » ET « 6 » (le BOAMP écrit les
    départements 01 à 09 sans zéro) ; « 2A » ET « 20A », « 2B » ET « 20B » (le BOAMP écrit la Corse
    « 20A » / « 20B ») ; sinon la forme demandée seule."""
    s = dept_canonique(d)
    if s in ("2A", "2B"):
        return [s, "20" + s[1]]
    return [s, s[1:]] if (len(s) == 2 and s.isdigit() and s.startswith("0")) else [s]


def _as_str(v) -> Optional[str]:
    """Coerce un champ BOAMP (parfois liste) en string, ou None."""
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return ", ".join(parts) or None
    return str(v).strip() or None


# ── Lecture des suites d'un avis (rectificatifs, annulations) ─────────────────────────────────────────────

def _idweb(r: dict) -> str:
    return str((r or {}).get("idweb") or "").strip()


def _liens(r: dict) -> list:
    v = (r or {}).get("annonce_lie") or []
    if not isinstance(v, list):
        v = [v]
    return [str(x).strip() for x in v if str(x or "").strip()]


def _dossier(r: dict) -> str:
    """Identifiant du dossier européen (`contractfolderid`), commun à un avis et à ses versions."""
    return str((r or {}).get("contractfolderid") or "").strip()


def _maj(r: dict, champ: str) -> str:
    return str((r or {}).get(champ) or "").strip().upper()


def _est_annulation(r: dict) -> bool:
    """Annulation d'un avis de marché, sous les deux formes observées : un avis « ANNULATION » (formats national,
    simplifié, divers) ; un avis européen « APPEL_OFFRE » à l'état « ANNULATION » (procédure déclarée sans suite)."""
    return _maj(r, "nature") == "ANNULATION" or (_maj(r, "etat") == "ANNULATION" and _maj(r, "nature") == "APPEL_OFFRE")


def _au_format_europeen(r: dict) -> bool:
    """Rectificatif publié comme une version COMPLÈTE de l'avis (format européen : nature « APPEL_OFFRE »,
    état « RECTIFICATIF »), avec sa propre date limite structurée."""
    return _maj(r, "etat") == "RECTIFICATIF" and _maj(r, "nature") == "APPEL_OFFRE"


def _est_suite(r: dict) -> bool:
    """Rectificatif ou annulation d'un avis de marché (formats national, simplifié et européen). Le rectificatif
    d'un avis d'attribution, ou d'une autre nature, n'en est pas une : il n'est jamais appliqué à un avis ouvert."""
    return _est_annulation(r) or _maj(r, "nature") == "RECTIFICATIF" or _au_format_europeen(r)


def _ordre(r: dict):
    i = _idweb(r)
    num = int(i.split("-")[1]) if _IDWEB.match(i) else 0
    return ((r.get("dateparution") or "")[:10], i[:2], num)


def _date_finale(rects: list) -> Optional[str]:
    """Date limite qui résulte d'une suite de rectificatifs, sans l'avis initial : None si aucun n'en parle ou
    si le dernier qui en parle n'a pas pu être lu."""
    fin = None
    for r in sorted(rects, key=_ordre):
        lecture = lire_rectificatif(r)
        if lecture["concerne"]:
            fin = lecture["date"]
    return fin


# La date limite de RÉPONSE, et elle seule : jamais la date des questions, de la visite ou de l'ouverture des plis.
_CONCERNE_DELAI = re.compile(
    r"\bDLRO\b"
    r"|(?:remise|r[ée]ception|d[ée]p[ôo]t|transmission)\s+des\s+(?:offres|plis|candidatures|r[ée]ponses|dossiers)"
    r"|date\s+limite\s+de\s+r[ée]ponse", re.I)
# La date limite citée comme REPÈRE d'un autre délai (« … 10 jours calendaires avant la date limite fixée pour la
# réception des offres », « … après la date limite de remise des plis ») ne la change jamais : un tel passage ne
# compte pas comme parlant de la date limite (26-100865, du 16/10/2026, ne change que le délai des questions de
# 26-100294 ; relecture du lot 1, docs/MOTEUR_LOT1.md).
_REPERE_DU_DELAI = re.compile(
    r"\b(?:avant|apr[èe]s)\s+(?:la\s+|le\s+)?"
    r"(?:(?:date|jour)\s+(?:et\s+(?:l['’]\s*)?heure\s+)?limites?\s+(?:fix[ée]e?s?\s+)?(?:pour|de|d['’])\s*(?:la\s+|le\s+)?)?"
    r"(?:remise|r[ée]ception|d[ée]p[ôo]t|transmission)\s+des\s+(?:offres|plis|candidatures|r[ée]ponses|dossiers)"
    r"|\b(?:avant|apr[èe]s)\s+(?:la\s+)?(?:date\s+limite\s+de\s+r[ée]ponse|DLRO)\b", re.I)
# « Au lieu de 21/10/2026 à 12h00, lire 05/11/2026 à 12h00 » : la date qui suit « lire ».
_AU_LIEU_LIRE = re.compile(r"\bau\s+lieu\s+d(?:e|u|es)\b(.*?)\blire\b(.*?)(?=\bau\s+lieu\s+d(?:e|u|es)\b|$)",
                           re.I | re.S)


def _lire_texte(texte: str):
    """(concerne, date) d'un texte de rectificatif. Concerne : il parle de la date limite de réponse. Date :
    celle qui suit « lire » dans « Au lieu de …, lire … », sinon la seule date citée (même jour, même mois,
    avec son année). Plusieurs dates différentes ou une date sans année : None, jamais un choix."""
    texte = str(texte or "")
    if not _CONCERNE_DELAI.search(_REPERE_DU_DELAI.sub(" ", texte)):
        return False, None
    paires = _AU_LIEU_LIRE.findall(texte)
    if paires:
        dates = {date_unique(apres) for _, apres in paires}
        return True, (dates.pop() if len(dates) == 1 else None)
    return True, date_unique(texte)


def _date_iso_champ(v) -> Optional[str]:
    """« 2026-11-06T15:00:00Z » → « 2026-11-06 » si la date existe au calendrier, sinon None."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(v or "").strip())
    return date_iso(m.group(3), m.group(2), m.group(1)) if m else None


def _infos_rectif(donnees):
    """Le bloc `infosRectif` du corps d'un rectificatif (observé dans les formats national « FNSimple » et
    simplifié « MAPA »), où qu'il soit rangé ; None s'il manque ou si le corps est illisible."""
    if isinstance(donnees, str):
        try:
            donnees = json.loads(donnees)
        except ValueError:
            return None
    pile = [donnees]
    while pile:
        n = pile.pop()
        if isinstance(n, dict):
            if "infosRectif" in n:
                return n["infosRectif"]
            pile.extend(n.values())
        elif isinstance(n, list):
            pile.extend(n)
    return None


def _lire_element(e):
    """(concerne, date, forme) d'un élément de `infosRectif`."""
    if isinstance(e, str):
        c, d = _lire_texte(e)
        return c, d, "texte"
    if isinstance(e, dict):
        if "rubDelais" in e:
            # Forme structurée du format simplifié : {"rubDelais": "ReceptionOffres", "auLieuDeDate", "lireDate"}.
            if str(e.get("rubDelais") or "") == "ReceptionOffres":
                return True, _date_iso_champ(e.get("lireDate")), "structurée"
            return True, None, "structurée, délai non vérifié"      # autre délai : jamais observé
        textes = " ".join(str(v) for v in e.values() if isinstance(v, str))
        c, d = _lire_texte(textes)
        if c and isinstance(e.get("lire"), str):
            d = date_unique(e["lire"])
        return c, d, "texte"
    return True, None, "non vérifiée"


def lire_rectificatif(r: dict) -> dict:
    """Ce qu'un rectificatif dit de la date limite de réponse : {"concerne", "date", "forme"}.

    - Format européen (version complète de l'avis) : sa date limite structurée.
    - Formats national et simplifié : `infosRectif` (texte « Au lieu de …, lire … », phrase libre, ou forme
      structurée « ReceptionOffres »). Un rectificatif qui ne parle pas de la date limite la laisse intacte.
    - Une forme jamais observée (bloc absent, autre délai, type inattendu) : « concerne », sans date ; la fiche
      affiche alors une date « non précisée », jamais l'ancienne (prudence ; docs/MOTEUR_LOT1.md, § Sources).
    - Une nouvelle date antérieure à la parution du rectificatif est impossible : elle n'est pas lue."""
    if _au_format_europeen(r):
        out = {"concerne": True, "date": _date_iso_champ(r.get("datelimitereponse")), "forme": "européen"}
    else:
        infos = _infos_rectif((r or {}).get("donnees"))
        elements = (infos if isinstance(infos, list) else [infos]) if infos is not None else []
        lectures = [_lire_element(e) for e in elements] or [(True, None, "non vérifiée")]
        parle = [x for x in lectures if x[0]]
        if not parle:
            out = {"concerne": False, "date": None, "forme": lectures[0][2]}
        else:
            dates = {x[1] for x in parle}
            out = {"concerne": True, "date": dates.pop() if len(dates) == 1 else None, "forme": parle[-1][2]}
    parution = _date_iso_champ((r or {}).get("dateparution"))
    if out["date"] and parution and out["date"] < parution:
        out["date"] = None
    return out


def _dedup_key(t: NormalizedTender) -> str:
    base = re.sub(r"[^a-z0-9]", "", (t.objet or "").lower())[:40]
    ach = re.sub(r"[^a-z0-9]", "", (t.acheteur or "").lower())[:20]
    return f"{base}|{ach}|{t.date_limite or ''}"
