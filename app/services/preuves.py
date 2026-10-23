"""
« Mes preuves » (rédaction, vague 3) : le SOCLE commun de A (« chaque fait a sa source »), de I
(« partir de vos anciens dossiers ») et de E1 (les écrans « Mes preuves »).

Contrat complet : docs/REDACTION_V3_PREUVES.md. Ce module est le SEUL point d'écriture de la table
`preuves` (app.models.Preuve) ; le router app/routers/preuves.py ne fait que traduire HTTP.

Doctrine (étude « rédaction » § 7) appliquée ici, sans IA :
  1. Un fait ne vient jamais de l'IA. Une preuve a une source TYPÉE :
       documents  « trouvé dans vos documents » : un passage EXACT d'un document de « Mon
                  savoir-faire », retrouvé dans son texte (sinon refus), et dont chaque chiffre,
                  année, nom propre, certification et matériel de la fiche figure dans le passage ;
                  ou un justificatif déposé dans le coffre-fort (« justificatif déposé ») ;
       declare    « déclaré par vous » : saisie de l'utilisateur, sans justificatif ;
       public     « source publique » : URL publique datée (DECP, liste RGE…), références et
                  qualifications seulement ;
       estimation « votre estimation » : chiffres clés prévus (délais, effectifs, quantités).
     Le dossier de l'acheteur n'est JAMAIS une source d'une preuve.
  2. Qui affirme quoi : chaque fait a un propriétaire (l'organisation ; en vague 4 un membre du
     groupement — champ prévu, jamais exposé, jamais lu par le chef de file).
  3. On ne dit jamais « vérifié » : on dit où on a trouvé le fait.
  9. Les CV et les noms des salariés ne partent jamais à l'IA : `texte_ia` ne contient ni nom ni
     CV ; les noms des fiches « Équipe » s'ajoutent aux noms masqués (app/services/pii.py).

Statuts : proposee (I propose, l'utilisateur coche) → acceptee → retiree (et retour). Seules les
preuves ACCEPTÉES, encore valables (date de fin non dépassée) et dont la source existe encore sont
remises à la rédaction : `faits_autorises()`, avec leur identifiant stable « F<numéro> ».
"""
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from app.models import Document, KnowledgeChunk, KnowledgeDoc, Preuve, Project, User

# ── Vocabulaire ───────────────────────────────────────────────────────────────────────

REFERENCE, QUALIFICATION, SALARIE, MATERIEL, CHIFFRE_CLE = (
    "reference", "qualification", "salarie", "materiel", "chiffre_cle")
NATURES = (REFERENCE, QUALIFICATION, SALARIE, MATERIEL, CHIFFRE_CLE)
NATURE_LIBELLES = {REFERENCE: "Référence", QUALIFICATION: "Qualification", SALARIE: "Équipe",
                   MATERIEL: "Matériel", CHIFFRE_CLE: "Chiffre clé"}

DOCUMENTS, DECLARE, PUBLIC, ESTIMATION = "documents", "declare", "public", "estimation"
TYPES_SOURCE = (DOCUMENTS, DECLARE, PUBLIC, ESTIMATION)
TYPE_SOURCE_LIBELLES = {DOCUMENTS: "dans vos documents", DECLARE: "déclaré par vous",
                        PUBLIC: "source publique", ESTIMATION: "votre estimation"}
# Ce qu'une source peut appuyer dans le texte (étude § 6.5, tableau) — pour A.
APPUIE = {DOCUMENTS: "entreprise", DECLARE: "entreprise_declaration",
          PUBLIC: "references_qualifications", ESTIMATION: "estimations"}
NATURES_PAR_SOURCE = {DOCUMENTS: NATURES, DECLARE: NATURES, PUBLIC: (REFERENCE, QUALIFICATION),
                      ESTIMATION: (CHIFFRE_CLE,)}

LIB_TROUVE = "trouvé dans vos documents"
LIB_JUSTIFICATIF = "justificatif déposé"
LIB_DECLARE = "déclaré par vous"
LIB_PUBLIC = "source publique"
LIB_DECP = "marché attribué, source publique DECP"
LIB_ESTIMATION = "votre estimation"

PROPOSEE, ACCEPTEE, RETIREE = "proposee", "acceptee", "retiree"
SUPPRIMEE = "supprimee"          # interne : contenu effacé, numéro réservé, jamais listé
STATUTS = (PROPOSEE, ACCEPTEE, RETIREE)
STATUT_LIBELLES = {PROPOSEE: "Proposée", ACCEPTEE: "Acceptée", RETIREE: "Retirée"}

ORIGINES = ("saisie", "import_document", "import_public", "profil", "chiffrage")

ORGANISATION, INVITATION = "organisation", "invitation"

PREFIXE_REF = "F"                # « F3 » : renvoi stable d'un fait (numérotation de A)
MAX_PREUVES = 2000               # par organisation (garde-fou de stockage)
PASSAGE_MIN, PASSAGE_MAX = 12, 1200
CONTEXTE_PASSAGE = 300           # caractères montrés avant et après le passage
RECONFIRMER_ANS = 3              # document d'origine de plus de 3 ans : « à reconfirmer »

# Raisons pour lesquelles une preuve acceptée n'est pas remise à la rédaction.
EXPIREE = "expiree"
SOURCE_INTROUVABLE = "source_introuvable"
JUSTIFICATIF_INTROUVABLE = "justificatif_introuvable"
RAISONS = {
    PROPOSEE: "Proposée : cochez-la si elle est juste, pour qu'Adjugo puisse s'en servir.",
    RETIREE: "Retirée : Adjugo ne s'en sert plus.",
    EXPIREE: "Date de fin de validité dépassée : Adjugo ne s'en sert plus.",
    SOURCE_INTROUVABLE: ("Le document d'origine n'est plus dans « Mon savoir-faire » : ajoutez une autre "
                         "source ou déclarez-la vous-même."),
    JUSTIFICATIF_INTROUVABLE: ("Le justificatif n'est plus dans vos documents : déposez-le de nouveau ou "
                               "déclarez-la vous-même."),
}

MSG_CV = "Le CV ne contient ni photo, ni adresse, ni date de naissance."


class PreuveError(Exception):
    """Erreur métier affichable telle quelle (status HTTP, code stable, message, détails)."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def detail(self) -> dict:
        return dict(self.extra, code=self.code, message=self.message)


# ── Champs de chaque nature (liste FERMÉE : tout autre champ est refusé) ─────────────────

_ROLES = {"": "", "seul": "réalisé seul", "groupement_conjoint": "en groupement conjoint",
          "groupement_solidaire": "en groupement solidaire", "sous_traitant": "en sous-traitance"}
_POSSESSION = {"": "", "propriete": "en propre", "location": "en location"}

# champ → (genre, borne) ; genre : txt (longueur max), int (min, max), num (min, max), enum (valeurs)
CHAMPS = {
    REFERENCE: {"objet": ("txt", 300), "acheteur": ("txt", 200), "lieu": ("txt", 120),
                "annee": ("int", (1900, 2100)), "montant_ht": ("num", (0, 1e10)),
                "role": ("enum", tuple(_ROLES)), "description": ("txt", 1000)},
    QUALIFICATION: {"nom": ("txt", 200), "organisme": ("txt", 120), "numero": ("txt", 60),
                    "detail": ("txt", 300)},
    SALARIE: {"nom": ("txt", 120), "fonction": ("txt", 120), "experience_annees": ("int", (0, 70)),
              "diplomes": ("txt", 300), "qualifications": ("txt", 300), "chantiers": ("txt", 1000)},
    MATERIEL: {"designation": ("txt", 200), "quantite": ("int", (1, 1_000_000)),
               "caracteristiques": ("txt", 300), "possession": ("enum", tuple(_POSSESSION))},
    CHIFFRE_CLE: {"libelle": ("txt", 120), "valeur": ("num", (-1e12, 1e12)), "unite": ("txt", 40),
                  "annee": ("int", (1900, 2100))},
}
REQUIS = {REFERENCE: ("objet",), QUALIFICATION: ("nom",), SALARIE: ("nom", "fonction"),
          MATERIEL: ("designation",), CHIFFRE_CLE: ("libelle", "valeur")}
# Données d'un CV qu'Adjugo ne garde pas (étude § 6.7, E1) : refusées avec un message clair.
_CV_INTERDITS = {"photo", "image", "adresse", "address", "date_naissance", "naissance", "date_de_naissance",
                 "age", "telephone", "tel", "email", "courriel", "mail", "nationalite", "situation_familiale",
                 "numero_securite_sociale", "securite_sociale", "nir"}
# Champs d'identité recherchés TELS QUELS dans le passage (casse, accents et espaces près).
_CHAMPS_EXACTS = ("acheteur", "lieu", "nom", "numero", "organisme")

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _txt(v, n: int) -> str:
    s = _CTRL.sub("", str(v if v is not None else "")).replace("\r", "")
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:n].strip()


def _err_champ(champ: str, message: str):
    return PreuveError(422, "champ_invalide", message, champ=champ)


def valider_valeur(nature: str, valeur) -> dict:
    """Valeur NETTOYÉE d'une nature (champs vides retirés) ; PreuveError 422 sinon."""
    if nature not in CHAMPS:
        raise PreuveError(422, "nature_invalide", "Type de preuve inconnu : référence, qualification, équipe, "
                                                   "matériel ou chiffre clé.")
    if not isinstance(valeur, dict):
        raise PreuveError(422, "valeur_invalide", "Les champs de la preuve sont attendus sous forme d'objet.")
    champs = CHAMPS[nature]
    interdits = sorted(k for k in valeur if str(k).lower() in _CV_INTERDITS)
    if interdits:
        raise PreuveError(422, "champ_interdit", MSG_CV if nature == SALARIE else
                          "Ce champ ne fait pas partie d'une preuve.", champs=interdits)
    inconnus = sorted(str(k) for k in valeur if k not in champs)
    if inconnus:
        raise PreuveError(422, "champ_inconnu", "Champ inconnu pour ce type de preuve.", champs=inconnus)
    out = {}
    for k, (genre, borne) in champs.items():
        v = valeur.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        if genre == "txt":
            s = _txt(v, borne)
            if s:
                out[k] = s
        elif genre == "enum":
            s = str(v).strip()
            if s not in borne:
                raise _err_champ(k, "Valeur non prévue pour ce champ.")
            if s:
                out[k] = s
        else:
            if isinstance(v, bool):
                raise _err_champ(k, "Un nombre est attendu.")
            try:
                x = float(str(v).replace(",", ".").replace(" ", "").replace(" ", "")) \
                    if isinstance(v, str) else float(v)
            except (TypeError, ValueError):
                raise _err_champ(k, "Un nombre est attendu.")
            if not math.isfinite(x) or not (borne[0] <= x <= borne[1]):
                raise _err_champ(k, "Nombre hors des valeurs possibles.")
            if genre == "int":
                if x != int(x):
                    raise _err_champ(k, "Un nombre entier est attendu.")
                out[k] = int(x)
            else:
                out[k] = int(x) if x == int(x) else round(x, 4)
    manquants = [k for k in REQUIS[nature] if k not in out]
    if manquants:
        raise PreuveError(422, "champ_requis", "Champ à remplir : " + ", ".join(manquants) + ".",
                          champs=manquants)
    return out


# ── Texte de la preuve (déterministe) ─────────────────────────────────────────────────

def _nombre(x) -> str:
    """Nombre à la française : espaces pour les milliers, virgule décimale."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if f == int(f):
        return f"{int(f):,}".replace(",", " ")
    ent, dec = f"{f:.4f}".rstrip("0").split(".")
    return f"{int(ent):,}".replace(",", " ") + "," + dec


def _date_fr(d) -> str:
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else ""


# Une référence tirée des DECP (vague 5, E2) : le marché a été ATTRIBUÉ ; l'attribution ne prouve ni
# l'exécution ni sa qualité. Son texte ne dit donc jamais « réalisé ».
_ROLES_ATTRIBUE = {"": "", "seul": "attribué seul", "groupement_conjoint": "attribué en groupement conjoint",
                   "groupement_solidaire": "attribué en groupement solidaire", "sous_traitant": "en sous-traitance"}


def texte_de(nature: str, valeur: dict, date_fin_validite=None, attribue: bool = False) -> str:
    """Le fait, en une phrase. C'est CE texte que A rapproche des phrases (chiffres, noms,
    certifications) ; il contient donc tout, y compris le nom d'un salarié (jamais remis à l'IA :
    voir texte_ia). `attribue` : référence tirée des DECP (« marché attribué », jamais « réalisé »)."""
    v = valeur or {}
    p = []
    if nature == REFERENCE:
        p.append(v.get("objet", ""))
        if v.get("acheteur"):
            p.append(f"acheteur : {v['acheteur']}")
        if v.get("lieu"):
            p.append(f"lieu : {v['lieu']}")
        if v.get("annee"):
            p.append(f"année {v['annee']}")
        if v.get("montant_ht") is not None:
            lib = "montant d'attribution" if attribue else "montant"
            p.append(f"{lib} {_nombre(v['montant_ht'])} € HT")
        if attribue:
            p.append(_ROLES_ATTRIBUE.get(v.get("role") or "", "") or "marché attribué")
        elif v.get("role"):
            p.append(_ROLES.get(v["role"], ""))
        if v.get("description"):
            p.append(v["description"])
    elif nature == QUALIFICATION:
        p.append(v.get("nom", ""))
        if v.get("organisme"):
            p.append(f"délivrée par {v['organisme']}")
        if v.get("numero"):
            p.append(f"n° {v['numero']}")
        if v.get("detail"):
            p.append(v["detail"])
        if isinstance(date_fin_validite, date):
            p.append(f"valable jusqu'au {_date_fr(date_fin_validite)}")
    elif nature == SALARIE:
        p.append(f"{v.get('nom', '')}, {v.get('fonction', '')}")
        if v.get("experience_annees") is not None:
            p.append(f"{v['experience_annees']} ans d'expérience")
        if v.get("diplomes"):
            p.append(f"diplômes : {v['diplomes']}")
        if v.get("qualifications"):
            p.append(f"qualifications : {v['qualifications']}")
        if v.get("chantiers"):
            p.append(f"chantiers : {v['chantiers']}")
    elif nature == MATERIEL:
        p.append(v.get("designation", ""))
        if v.get("quantite") is not None:
            p.append(f"quantité : {v['quantite']}")
        if v.get("caracteristiques"):
            p.append(v["caracteristiques"])
        if v.get("possession"):
            p.append(_POSSESSION.get(v["possession"], ""))
    elif nature == CHIFFRE_CLE:
        s = f"{v.get('libelle', '')} : {_nombre(v.get('valeur'))}"
        if v.get("unite"):
            s += f" {v['unite']}"
        if v.get("annee"):
            s += f" ({v['annee']})"
        p.append(s)
    corps = " ; ".join(x for x in p if x)
    return f"{NATURE_LIBELLES.get(nature, 'Preuve')} : {corps}"


def texte_pour_ia(fait, pseudonymiseur=None) -> str:
    """Texte d'un fait remis à l'IA. « Équipe » : la FONCTION seule, et l'étiquette de la personne
    si un pseudonymiseur (app.services.pii) la connaît — jamais le nom, jamais le CV (diplômes,
    expérience, chantiers : insérés tels quels, sans IA, par la rédaction). Les autres natures :
    le texte complet (passé de toute façon dans pii_scope par l'appelant)."""
    if isinstance(fait, Preuve):
        nature, valeur, fin = fait.nature, fait.valeur or {}, fait.date_fin_validite
        attribue = est_marche_attribue(fait)
    else:
        nature, valeur, fin = fait.get("nature"), fait.get("valeur") or {}, None
        attribue = fait.get("nature") == REFERENCE and fait.get("source_libelle") == LIB_DECP
        if fait.get("date_fin_validite"):
            try:
                fin = date.fromisoformat(fait["date_fin_validite"])
            except (TypeError, ValueError):
                fin = None
    if nature != SALARIE:
        return texte_de(nature, valeur, fin, attribue=attribue)
    fonction = valeur.get("fonction") or "membre de l'équipe"
    label = ""
    if pseudonymiseur is not None and getattr(pseudonymiseur, "active", False):
        try:
            label = pseudonymiseur.label_of(valeur.get("nom") or "")
        except Exception:
            label = ""
    return f"Équipe : {label}, {fonction}" if label else f"Équipe : une personne de l'équipe, {fonction}"


def empreinte_de(nature: str, valeur: dict) -> str:
    from app.services.faits_a_relire import fold
    norm = {k: (fold(v) if isinstance(v, str) else v) for k, v in sorted((valeur or {}).items())}
    return hashlib.sha256(f"{nature}|{json.dumps(norm, sort_keys=True, ensure_ascii=False)}".encode()).hexdigest()


# ── Portée : l'organisation (tenant) ─────────────────────────────────────────────────

def membres(db, owner_id: int) -> list:
    """Comptes de l'organisation dont `owner_id` porte les données (sans effet de bord)."""
    u = db.get(User, owner_id)
    if u is None or not u.org_id:
        return [owner_id]
    ids = [r[0] for r in db.query(User.id).filter(User.org_id == u.org_id).all()]
    return ids or [owner_id]


def _q_org(db, owner_id: int):
    """Preuves de l'ORGANISATION (jamais celles d'un membre du groupement), hors effacées."""
    return db.query(Preuve).filter(Preuve.owner_id == owner_id, Preuve.proprietaire_invite_id == 0,
                                   Preuve.statut != SUPPRIMEE)


def get(db, owner_id: int, preuve_id) -> Optional[Preuve]:
    try:
        pid = int(preuve_id)
    except (TypeError, ValueError):
        return None
    return _q_org(db, owner_id).filter(Preuve.id == pid).first()


def lister(db, owner_id: int, nature: Optional[str] = None, statut: Optional[str] = None) -> list:
    q = _q_org(db, owner_id)
    if nature:
        q = q.filter(Preuve.nature == nature)
    if statut:
        q = q.filter(Preuve.statut == statut)
    return q.order_by(Preuve.nature.asc(), Preuve.numero.asc()).all()


def aujourd_hui() -> date:
    """Date du jour à Paris (repli UTC) : une validité « jusqu'au 12/10 » vaut toute la journée."""
    from app.services.format import _tz_paris
    tz = _tz_paris()
    return datetime.now(tz if tz is not None else timezone.utc).date()


def _moins_ans(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:            # 29 février
        return d.replace(year=d.year - n, day=28)


# ── Sources : contrôle à l'écriture ──────────────────────────────────────────────────

def _date(v, champ: str) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise _err_champ(champ, "Date attendue au format AAAA-MM-JJ.")


def _norm(s) -> str:
    from app.services.analysis import _norm_citation
    return _norm_citation(s)


def localiser(texte_doc: str, passage: str) -> Optional[tuple]:
    """(début, fin) du passage dans le texte du document, tel qu'il y est ÉCRIT : recherche exacte,
    puis tolérante (casse, accents, espaces, apostrophes — la même que citation_guard). None si le
    passage n'y est pas (ou s'il est trop court pour être un passage)."""
    from app.services.analysis import _norm_cached, _norm_with_map
    texte = str(texte_doc or "")
    ext = str(passage or "").strip()
    nx = _norm(ext)
    if len(nx) < PASSAGE_MIN or not texte:
        return None
    i = texte.find(ext)
    if i >= 0:
        return i, i + len(ext)
    if nx not in _norm_cached(texte):
        return None
    nt, pos = _norm_with_map(texte)
    j = nt.find(nx)
    if j < 0 or j + len(nx) - 1 >= len(pos):
        return None
    return pos[j], pos[j + len(nx) - 1] + 1


# Un nombre précédé de « n° », « numéro », « réf. », « SIRET »… est un numéro, jamais une quantité, un
# montant, une année ni un chiffre clé (« certificat n° 12345 » n'est pas « 12 345 € HT »).
_NUMERO_AVANT = re.compile(r"(?:\bn\s?[°ºo]\.?|\bnum(?:ero)?\.?|\bref(?:erence)?\.?|\bsiret|\bsiren|\bcode|#)\s*:?\s*$")


def _nombres_du_passage(passage: str) -> list:
    """Les nombres du passage, tels que la rédaction les repère (A0) : [{valeur (multiplicateur compris :
    « 85 k€ » = 85 000), unite (clé d'A0 : « nacel », « € », « an », ""), mot (le mot qui suit le
    nombre, replié), mots (clés des mots de sa phrase ou de sa ligne de tableau), numero (précédé de
    « n° »…)}]."""
    from app.services import faits_a_relire as far
    from app.services import faits_sources as fs
    out = []
    for ph, _titre, tableau in far.phrases(passage):
        same = far._fold_same(ph)
        mots = {far._unit_key(w) for w in re.findall(r"[a-z][a-z'\-]{2,}", same)}
        depuis = {}
        for fait, kind, key in far._facts_in(ph, tableau=tableau):
            if kind not in (far.CHIFFRE, far.EN_LETTRES):
                continue
            i = ph.find(fait, depuis.get(fait, 0))
            if i < 0:
                i = ph.find(fait)
            depuis[fait] = i + 1 if i >= 0 else 0
            v, _u = fs.cle_nombre(kind, fait, key)
            suite = same[i + len(fait):] if i >= 0 else ""
            # Le mot compté : l'unité écrite avec le nombre (« 300 m2 »), sinon le mot qui suit.
            mot = re.sub(r"^[\d\s.,  ]+", "", far.fold(fait)) if kind == far.CHIFFRE else ""
            if not mot:
                m = re.match(r"\s*([^\s\d.,;:()|]+)", suite)
                mot = m.group(1) if m else ""
            unite = key[1] if isinstance(key, tuple) else ""
            if unite in ("milli", "milliard") and re.match(r"\s*(?:d['’ ]\s?|de )?(?:euros?|€)", suite):
                unite = "€"                    # « 1,2 million d'euros »
            out.append({"valeur": v, "unite": unite,
                        "mot": mot, "suite": suite[:30], "mots": mots,
                        "numero": i >= 0 and bool(_NUMERO_AVANT.search(same[max(0, i - 14):i]))})
    return out


def _cles(texte) -> set:
    """Clés d'unité (A0) des mots d'un champ : « nacelles articulées » → {nacel, artic} ; « m2 » → {m2}."""
    from app.services import faits_a_relire as far
    return {far._unit_key(w) for w in re.findall(r"[a-z€%²³][a-z0-9€%²³'\-]*", far.fold(texte or ""))
            if len(w) >= 2 or w in ("€", "%")}


def _nombre_a_sa_place(nature: str, champ: str, v, valeur: dict, nombres: list) -> bool:
    """Le nombre du champ figure-t-il dans le passage DANS SON RÔLE (sans IA) ?
      • quantité d'un matériel : le nombre compte la désignation (« 2 nacelles », « Nacelle | 2 ») — jamais
        une dimension (« de 16 m ») ;
      • montant HT : suivi de « € » ou « euros » (« 85 k€ », « 1,2 million d'euros ») ;
      • année : un nombre seul (« en 2024 », « année 2024 ») ;
      • expérience : des années (« 15 ans ») ;
      • chiffre clé : son unité ou son libellé (« 12 salariés », « Effectif : 12 ») — jamais un nombre qui
        compte autre chose (« 300 m2 » n'est pas un effectif) ;
    et jamais un numéro (« certificat n° 12345 »)."""
    from app.services import faits_sources as fs
    try:
        x = float(v)
    except (TypeError, ValueError):
        return False
    for n in nombres:
        if n["valeur"] is None or abs(n["valeur"] - x) > 1e-6 * max(1.0, abs(x)) or n["numero"]:
            continue
        u = n["unite"]
        if nature == MATERIEL and champ == "quantite":
            if u and u in _cles(valeur.get("designation")):
                return True
        elif champ == "montant_ht":
            if u == "€":
                return True
        elif champ == "annee":
            if not u or u == "an":
                return True
        elif champ == "experience_annees":
            if fs._unite(u) == "an":
                return True
        elif nature == CHIFFRE_CLE and champ == "valeur":
            if _chiffre_cle_a_sa_place(valeur, u, n["mot"], n["mots"]):
                return True
        elif not u:
            return True
    return False


def _chiffre_cle_a_sa_place(valeur: dict, u: str, mot: str, mots: set) -> bool:
    """Un chiffre clé : l'unité du nombre est celle de la fiche ou un mot de son libellé (« 12 salariés »
    pour « Effectif »), ou, si le nombre n'a pas d'unité, son libellé est dans la même phrase."""
    from app.services import faits_sources as fs
    from app.services.fiches_import import _CATEGORIES
    permis = _cles(valeur.get("unite")) | _cles(valeur.get("libelle"))
    familles = {fs._unite(k) for k in permis}
    cats = [_CATEGORIES[w] for w in re.findall(r"[a-z]+", fs.far.fold(valeur.get("libelle") or "")) if w in _CATEGORIES]
    if u:
        if u in permis or fs._unite(u) in familles:
            return True
        return any(re.search(c, fs.far.fold(mot)) for c in cats)
    if mots & permis:
        return True
    return any(re.search(c, " ".join(sorted(mots))) for c in cats)


def elements_hors_passage(nature: str, valeur: dict, passage: str, champs: Optional[Iterable] = None) -> list:
    """Éléments de la fiche ABSENTS du passage (sans IA, même repérage que « à relire ») : chaque
    chiffre, année, montant, certification, nom propre et matériel des champs ; l'acheteur, le
    lieu, le nom, le numéro et l'organisme doivent y figurer tels quels. Un nombre d'un champ chiffré
    doit y figurer DANS SON RÔLE (`_nombre_a_sa_place` : « 2 nacelles », « 85 000 € », jamais « de 16 m »
    ni « n° 12345 »). `champs` : les seuls champs à contrôler (les autres servent de contexte, par
    exemple la désignation d'un matériel). Vide = la fiche ne dit rien de plus que le passage."""
    from app.services import faits_a_relire as far
    src = far.Sources([passage])
    low = far.fold(passage)
    manquants, vus = [], set()
    nombres = None
    valeur = valeur or {}
    a_voir = set(champs) if champs is not None else None

    def _ajoute(x):
        k = far.fold(x)
        if k and k not in vus:
            vus.add(k)
            manquants.append(str(x)[:120])

    for champ, (genre, _b) in CHAMPS.get(nature, {}).items():
        v = valeur.get(champ)
        if v is None or genre == "enum" or (a_voir is not None and champ not in a_voir):
            continue
        if genre in ("int", "num"):
            if nombres is None:
                nombres = _nombres_du_passage(passage)
            if not _nombre_a_sa_place(nature, champ, v, valeur, nombres):
                _ajoute(str(v) if genre == "int" else _nombre(v))
            continue
        # Tous les faits du champ, quelle que soit la phrase (même « Le CCTP prévoit… ») : la fiche
        # ne doit rien dire de plus que le passage.
        for ph, _titre, tableau in far.phrases(str(v)):
            for fait, kind, key in far._facts_in(ph, tableau=tableau):
                if not src.has(kind, key):
                    _ajoute(fait)
        if champ in _CHAMPS_EXACTS:
            fv = far.fold(v)
            if fv and re.search(r"(?<!\w)" + re.escape(fv) + r"(?!\w)", low) is None:
                _ajoute(v)
    return manquants


def _source_documents(db, owner_id: int, nature: str, valeur: dict, source: dict) -> tuple:
    """→ (source nettoyée, source_doc_id, source_document_id). Un passage doit être retrouvé TEL
    QUEL dans le document, et couvrir la fiche ; un justificatif doit être un document déposé."""
    mids = membres(db, owner_id)
    out, doc_id, document_id = {}, None, None
    if source.get("doc_id") not in (None, ""):
        try:
            did = int(source.get("doc_id"))
        except (TypeError, ValueError):
            raise PreuveError(422, "document_introuvable", "Document introuvable dans « Mon savoir-faire ».")
        doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == did, KnowledgeDoc.user_id.in_(mids)).first()
        if doc is None:
            raise PreuveError(422, "document_introuvable", "Document introuvable dans « Mon savoir-faire ».")
        passage = _txt(source.get("passage"), PASSAGE_MAX + 1).strip("«»\"“”„ ")
        if len(passage) > PASSAGE_MAX:
            raise PreuveError(422, "passage_trop_long", f"Choisissez un passage plus court ({PASSAGE_MAX} "
                                                        "caractères au plus).")
        loc = localiser(doc.text or "", passage) if passage else None
        if loc is None:
            raise PreuveError(422, "passage_introuvable",
                              "Ce passage n'a pas été retrouvé dans le document : recopiez-le tel qu'il est écrit, "
                              "ou choisissez « déclaré par vous ».")
        debut, fin = loc
        passage = (doc.text or "")[debut:fin]          # le passage tel qu'il est écrit dans le document
        manquants = elements_hors_passage(nature, valeur, passage)
        if manquants:
            raise PreuveError(422, "valeur_hors_passage",
                              "Ces éléments de la fiche ne figurent pas dans le passage : " + ", ".join(manquants)
                              + ". Corrigez-les, choisissez un passage qui les contient, ou choisissez « déclaré "
                                "par vous ».", elements=manquants[:20])
        chunk_id = None
        tete = _norm(passage)[:160]
        for c in (db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id)
                  .order_by(KnowledgeChunk.ordinal.asc()).all()):
            if tete and tete in _norm(c.text):
                chunk_id = c.id
                break
        out.update(doc_id=doc.id, doc_nom=(doc.name or "")[:300], passage=passage, debut=debut, chunk_id=chunk_id)
        doc_id = doc.id
    if source.get("document_id") not in (None, ""):
        try:
            jid = int(source.get("document_id"))
        except (TypeError, ValueError):
            raise PreuveError(422, "justificatif_introuvable", "Justificatif introuvable dans vos documents.")
        jd = db.query(Document).filter(Document.id == jid, Document.user_id.in_(mids),
                                       Document.deleted_at.is_(None)).first()
        if jd is None:
            raise PreuveError(422, "justificatif_introuvable", "Justificatif introuvable dans vos documents.")
        out.update(document_id=jd.id, document_nom=(jd.name or "")[:300])
        document_id = jd.id
    if doc_id is None and document_id is None:
        raise PreuveError(422, "source_requise", "Indiquez le passage du document où se trouve ce fait, ou "
                                                 "un justificatif déposé ; sinon choisissez « déclaré par vous ».")
    return out, doc_id, document_id


_URL = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d{1,5})?(?:[/?#][^\s<>\"']*)?$")


# Le RELEVÉ d'une source publique (vague 5, E2) : les champs de la fiche tels que la source les donne
# (DECP, liste RGE). Tant que la fiche garde cette source, ils ne changent pas : sinon le libellé
# « source publique » couvrirait une valeur qui n'est plus celle de la source. Pour les corriger,
# l'utilisateur choisit « déclaré par vous ».
CHAMP_FIN = "date_fin_validite"
MSG_RELEVE = ("Ces champs viennent de la source publique ({nom}) : ils ne changent pas tant que la fiche garde "
              "cette source. Pour les corriger, choisissez « Déclaré par vous ».")


def _releve_propre(nature: str, releve) -> Optional[dict]:
    """Le relevé nettoyé (champs de la nature et fin de validité, valeurs simples), ou None."""
    if releve in (None, {}, ""):
        return None
    if not isinstance(releve, dict) or len(releve) > 20:
        raise PreuveError(422, "releve_invalide", "Relevé de la source publique illisible.")
    out = {}
    for k, v in releve.items():
        if k not in CHAMPS.get(nature, {}) and k != CHAMP_FIN:
            raise PreuveError(422, "releve_invalide", "Relevé de la source publique illisible.")
        if isinstance(v, bool) or (v is not None and not isinstance(v, (str, int, float))):
            raise PreuveError(422, "releve_invalide", "Relevé de la source publique illisible.")
        out[k] = v
    return out or None


def _valeur_comparable(v):
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def _controler_releve(p: Preuve) -> None:
    """Les champs relevés de la source publique sont ceux de la fiche (création et modification)."""
    rel = (p.source or {}).get("releve") if p.type_source == PUBLIC else None
    if not rel:
        return
    v = p.valeur or {}
    fin = p.date_fin_validite.isoformat() if isinstance(p.date_fin_validite, date) else None
    ecarts = []
    for k, attendu in rel.items():
        actuel = fin if k == CHAMP_FIN else v.get(k)
        if _valeur_comparable(actuel) != _valeur_comparable(attendu):
            ecarts.append(k)
    if ecarts:
        raise PreuveError(422, "valeur_source_publique",
                          MSG_RELEVE.format(nom=(p.source or {}).get("nom") or "source publique"), champs=sorted(ecarts))


def champs_source_publique(p: Preuve) -> list:
    """Les champs d'une fiche tirés de sa source publique (verrouillés tant qu'elle la garde)."""
    rel = (p.source or {}).get("releve") if p.type_source == PUBLIC else None
    return sorted(rel) if isinstance(rel, dict) else []


def _source_publique(source: dict, nature: str = "") -> tuple:
    nom = _txt(source.get("nom"), 120)
    url = str(source.get("url") or "").strip()
    if not nom:
        raise PreuveError(422, "source_requise", "Indiquez le nom de la source publique (par exemple DECP).")
    if len(url) > 500 or not _URL.match(url):
        raise PreuveError(422, "url_invalide", "Indiquez l'adresse de la page publique (https://…).")
    consulte = _date(source.get("consulte_le"), "consulte_le")
    if consulte is None:
        raise PreuveError(422, "date_requise", "Indiquez la date à laquelle la source a été consultée.")
    if consulte > aujourd_hui() + timedelta(days=1):
        raise _err_champ("consulte_le", "La date de consultation ne peut pas être dans le futur.")
    out = {"nom": nom, "url": url, "consulte_le": consulte.isoformat()}
    ident = _txt(source.get("identifiant"), 120)
    if ident:
        out["identifiant"] = ident
    rel = _releve_propre(nature, source.get("releve"))
    if rel:
        out["releve"] = rel
    return out, consulte


def _source_estimation(db, owner_id: int, source: dict) -> dict:
    out = {}
    if source.get("project_id") not in (None, ""):
        try:
            pid = int(source.get("project_id"))
        except (TypeError, ValueError):
            pid = None
        p = (db.query(Project).filter(Project.id == pid, Project.user_id.in_(membres(db, owner_id))).first()
             if pid else None)
        if p is None:
            raise PreuveError(422, "marche_introuvable", "Marché introuvable.")
        out["project_id"] = p.id
    detail = _txt(source.get("detail"), 300)
    if detail:
        out["detail"] = detail
    return out


def _appliquer_source(db, owner_id: int, p: Preuve, nature: str, valeur: dict, type_source: str, source,
                      date_source) -> None:
    if type_source not in TYPES_SOURCE:
        raise PreuveError(422, "type_source_invalide", "Source inconnue : dans vos documents, déclaré par vous, "
                                                       "source publique ou votre estimation.")
    if nature not in NATURES_PAR_SOURCE[type_source]:
        raise PreuveError(422, "source_non_permise",
                          "Une source publique n'appuie qu'une référence ou une qualification ; votre estimation, "
                          "qu'un chiffre clé." if type_source in (PUBLIC, ESTIMATION) else "Source non permise.")
    source = source if isinstance(source, dict) else {}
    ds = _date(date_source, "date_source")
    if ds is not None and ds > aujourd_hui() + timedelta(days=1):
        raise _err_champ("date_source", "La date du document ne peut pas être dans le futur.")
    # Tout est contrôlé AVANT de toucher à la preuve : une erreur ne laisse rien à moitié changé.
    doc_id = document_id = None
    if type_source == DOCUMENTS:
        src, doc_id, document_id = _source_documents(db, owner_id, nature, valeur, source)
    elif type_source == PUBLIC:
        src, ds = _source_publique(source, nature)
    elif type_source == ESTIMATION:
        src = _source_estimation(db, owner_id, source)
    else:
        src = {}
    p.source, p.source_doc_id, p.source_document_id = src, doc_id, document_id
    p.type_source = type_source
    p.date_source = ds


# ── Écritures ─────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prochain_numero(db, owner_id: int, invite_id: int) -> int:
    from sqlalchemy import func
    m = db.query(func.max(Preuve.numero)).filter(Preuve.owner_id == owner_id,
                                                  Preuve.proprietaire_invite_id == invite_id).scalar()
    return int(m or 0) + 1


def creer(db, owner_id: int, *, nature: str, valeur, type_source: str = DECLARE, source=None, date_source=None,
          date_fin_validite=None, statut: str = ACCEPTEE, origine: str = "saisie", user=None,
          commit: bool = True) -> Preuve:
    """Crée une preuve de l'ORGANISATION `owner_id` (data_owner_id). Toutes les règles sont ici :
    champs de la nature, source typée contrôlée (passage retrouvé et qui couvre la fiche), statut.
    `statut` : 'acceptee' (saisie par l'utilisateur) ou 'proposee' (I, E2 : l'utilisateur coche)."""
    if statut not in (PROPOSEE, ACCEPTEE):
        raise PreuveError(422, "statut_invalide", "Une nouvelle preuve est proposée ou acceptée.")
    if origine not in ORIGINES:
        raise PreuveError(422, "origine_invalide", "Origine inconnue.")
    propre = valider_valeur(nature, valeur)
    if _q_org(db, owner_id).count() >= MAX_PREUVES:
        raise PreuveError(409, "trop_de_preuves", f"Vous avez atteint {MAX_PREUVES} preuves : retirez-en avant "
                                                  "d'en ajouter.")
    p = Preuve(owner_id=owner_id, proprietaire_kind=ORGANISATION, proprietaire_invite_id=0, nature=nature,
               valeur=propre, statut=statut, origine=origine, cree_par=getattr(user, "id", None), version=0)
    _appliquer_source(db, owner_id, p, nature, propre, type_source, source, date_source)
    p.date_fin_validite = _date(date_fin_validite, "date_fin_validite")
    _controler_releve(p)
    p.empreinte = empreinte_de(nature, propre)
    if statut == ACCEPTEE:
        p.accepte_par, p.accepte_le = getattr(user, "id", None), _now()
    # Numéro suivant, sans doublon : la ligne du compte qui porte les données est verrouillée
    # (Postgres) le temps de la transaction ; deux créations simultanées se suivent.
    db.query(User.id).filter(User.id == owner_id).with_for_update().first()
    p.numero = _prochain_numero(db, owner_id, 0)
    db.add(p)
    db.flush()
    if commit:
        db.commit()
        db.refresh(p)
    return p


def proposer(db, owner_id: int, *, nature: str, valeur, type_source: str, source=None, date_source=None,
             date_fin_validite=None, origine: str = "import_document", user=None, commit: bool = True):
    """Proposition (I, E2) : statut 'proposee'. Une fiche identique (même nature, mêmes champs) déjà
    présente — proposée, acceptée ou retirée — n'est pas proposée deux fois : renvoie (preuve, False).
    Sinon (preuve créée, True). Toute règle non respectée (passage introuvable…) lève PreuveError :
    la proposition est rejetée."""
    propre = valider_valeur(nature, valeur)
    emp = empreinte_de(nature, propre)
    deja = _q_org(db, owner_id).filter(Preuve.nature == nature, Preuve.empreinte == emp).first()
    if deja is not None:
        return deja, False
    return creer(db, owner_id, nature=nature, valeur=propre, type_source=type_source, source=source,
                 date_source=date_source, date_fin_validite=date_fin_validite, statut=PROPOSEE, origine=origine,
                 user=user, commit=commit), True


_ABSENT = object()


def _verifier_version(p: Preuve, version) -> None:
    if version is not None and int(version) != int(p.version or 0):
        raise PreuveError(409, "modifiee_ailleurs", "Cette preuve vient d'être modifiée par ailleurs : rechargez-la.",
                          version=int(p.version or 0))


def modifier(db, p: Preuve, *, user=None, valeur=_ABSENT, type_source=_ABSENT, source=_ABSENT,
             date_source=_ABSENT, date_fin_validite=_ABSENT, version=None) -> Preuve:
    """Modifie les champs, la source ou les dates (la nature ne change pas). La source est
    recontrôlée dès que les champs ou la source changent. Une preuve acceptée reste acceptée (c'est
    l'utilisateur qui la modifie) ; une proposition reste à cocher."""
    if p.statut == SUPPRIMEE:
        raise PreuveError(404, "preuve_introuvable", "Preuve introuvable.")
    _verifier_version(p, version)
    propre = valider_valeur(p.nature, valeur) if valeur is not _ABSENT else dict(p.valeur or {})
    ts = type_source if type_source is not _ABSENT else p.type_source
    garde_releve = ts == PUBLIC and p.type_source == PUBLIC and bool((p.source or {}).get("releve"))
    if garde_releve:
        # Fiche tirée d'une source publique (DECP, liste RGE) qui la garde : sa source ne change pas
        # (l'écran renvoie nom, adresse et date tels quels) ; ses champs relevés non plus (contrôle plus bas).
        src = _source_brute(p)
    elif source is not _ABSENT:
        src = source
    elif ts == p.type_source:
        src = _source_brute(p)
    else:
        src = None
    ds = p.date_source if garde_releve else (date_source if date_source is not _ABSENT else p.date_source)
    fin = _date(date_fin_validite, "date_fin_validite") if date_fin_validite is not _ABSENT else p.date_fin_validite
    if valeur is not _ABSENT or type_source is not _ABSENT or source is not _ABSENT or date_source is not _ABSENT:
        _appliquer_source(db, p.owner_id, p, p.nature, propre, ts, src, ds)
    p.valeur = propre
    p.date_fin_validite = fin
    _controler_releve(p)
    p.empreinte = empreinte_de(p.nature, propre)
    if p.statut == ACCEPTEE:
        p.accepte_par, p.accepte_le = getattr(user, "id", None) or p.accepte_par, _now()
    p.version = int(p.version or 0) + 1
    db.commit()
    db.refresh(p)
    return p


def _source_brute(p: Preuve) -> dict:
    """Ce qu'il faut redonner à _appliquer_source pour recontrôler la source actuelle."""
    s = dict(p.source or {})
    if p.type_source == DOCUMENTS:
        return {k: s.get(k) for k in ("doc_id", "passage", "document_id") if s.get(k) not in (None, "")}
    return s


def accepter(db, p: Preuve, user=None, version=None) -> Preuve:
    """Cocher une proposition (ou reprendre une preuve retirée). La source doit exister encore."""
    if p.statut == SUPPRIMEE:
        raise PreuveError(404, "preuve_introuvable", "Preuve introuvable.")
    _verifier_version(p, version)
    raison = _Etat(db, p.owner_id).raison_source(p)
    if raison:
        raise PreuveError(409, raison, RAISONS[raison])
    if p.statut != ACCEPTEE:
        p.statut = ACCEPTEE
        p.accepte_par, p.accepte_le, p.retire_le = getattr(user, "id", None), _now(), None
        p.version = int(p.version or 0) + 1
        db.commit()
        db.refresh(p)
    return p


def retirer(db, p: Preuve, user=None, version=None) -> Preuve:
    if p.statut == SUPPRIMEE:
        raise PreuveError(404, "preuve_introuvable", "Preuve introuvable.")
    _verifier_version(p, version)
    if p.statut != RETIREE:
        p.statut = RETIREE
        p.retire_le = _now()
        p.version = int(p.version or 0) + 1
        db.commit()
        db.refresh(p)
    return p


def _effacer_contenu(p: Preuve) -> None:
    p.valeur, p.source, p.source_doc_id, p.source_document_id = None, None, None, None
    p.date_source = p.date_fin_validite = None
    p.empreinte = ""
    p.cree_par = p.accepte_par = None
    p.accepte_le = p.retire_le = None


def supprimer(db, p: Preuve, user=None) -> None:
    """Suppression définitive du CONTENU (CV compris). La ligne reste, vide, pour réserver son
    numéro : un ancien renvoi « F3 » ne désignera jamais un autre fait."""
    _effacer_contenu(p)
    p.statut = SUPPRIMEE
    p.version = int(p.version or 0) + 1
    db.commit()


# ── Lecture : ce qui est remis à la rédaction ────────────────────────────────────────

class _Etat:
    """Existence des sources (KnowledgeDoc, Document), lue une fois pour un lot de preuves de la
    même organisation ; une preuve hors du lot est chargée à la demande."""

    def __init__(self, db, owner_id: int, preuves: Optional[Iterable] = None):
        self.db = db
        self.mids = membres(db, owner_id)
        self._docs, self._documents = {}, {}
        self._vus_docs, self._vus_documents = set(), set()
        self._charger(list(preuves or []))

    def _charger(self, ps: list) -> None:
        doc_ids = {x.source_doc_id for x in ps if x.source_doc_id} - self._vus_docs
        document_ids = {x.source_document_id for x in ps if x.source_document_id} - self._vus_documents
        if doc_ids:
            self._docs.update({r[0]: r[1] for r in self.db.query(KnowledgeDoc.id, KnowledgeDoc.name).filter(
                KnowledgeDoc.id.in_(list(doc_ids)), KnowledgeDoc.user_id.in_(self.mids)).all()})
            self._vus_docs |= doc_ids
        if document_ids:
            self._documents.update({r[0]: r[1] for r in self.db.query(Document.id, Document.name).filter(
                Document.id.in_(list(document_ids)), Document.user_id.in_(self.mids),
                Document.deleted_at.is_(None)).all()})
            self._vus_documents |= document_ids

    def raison_source(self, p: Preuve) -> Optional[str]:
        """None si la source d'une preuve « dans vos documents » existe encore dans l'organisation."""
        if p.type_source != DOCUMENTS:
            return None
        self._charger([p])
        if p.source_doc_id:
            # Le passage (retrouvé à l'écriture dans un texte qui ne change plus) fait foi tant que
            # son document est là ; un justificatif en plus n'est qu'un lien.
            return None if p.source_doc_id in self._docs else SOURCE_INTROUVABLE
        if p.source_document_id:
            return None if p.source_document_id in self._documents else JUSTIFICATIF_INTROUVABLE
        return SOURCE_INTROUVABLE


def ref_de(p: Preuve) -> str:
    return f"{PREFIXE_REF}{p.numero}"


def source_libelle(p: Preuve) -> str:
    """Où le fait a été trouvé (jamais « vérifié »)."""
    if p.type_source == DOCUMENTS:
        return LIB_TROUVE if (p.source or {}).get("passage") else LIB_JUSTIFICATIF
    if p.type_source == PUBLIC:
        nom = (p.source or {}).get("nom") or ""
        from app.services.faits_a_relire import fold
        if p.nature == REFERENCE and re.search(r"(?<![a-z])decp(?![a-z])", fold(nom)):
            return LIB_DECP
        return f"{LIB_PUBLIC} : {nom}" if nom else LIB_PUBLIC
    if p.type_source == ESTIMATION:
        return LIB_ESTIMATION
    return LIB_DECLARE


def est_marche_attribue(p: Preuve) -> bool:
    """Référence tirée des DECP : un marché ATTRIBUÉ (jamais « réalisé » : l'attribution ne prouve ni
    l'exécution ni sa qualité)."""
    return p.nature == REFERENCE and p.type_source == PUBLIC and source_libelle(p) == LIB_DECP


def _source_out(p: Preuve) -> dict:
    s = dict(p.source or {})
    out = {}
    if p.type_source == DOCUMENTS:
        if s.get("doc_id"):
            out.update(doc_id=s.get("doc_id"), doc_nom=s.get("doc_nom", ""), passage=s.get("passage", ""),
                       chunk_id=s.get("chunk_id"), lien_passage=f"/api/preuves/{p.id}/passage")
        if s.get("document_id"):
            out.update(document_id=s.get("document_id"), document_nom=s.get("document_nom", ""),
                       lien_justificatif=f"/api/documents/{s.get('document_id')}/download")
    elif p.type_source == PUBLIC:
        out.update({k: s.get(k) for k in ("nom", "url", "consulte_le", "identifiant") if s.get(k)})
    elif p.type_source == ESTIMATION:
        out.update({k: s.get(k) for k in ("project_id", "detail") if s.get(k)})
    return out


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.replace(microsecond=0).isoformat()
    return dt.isoformat()


def _a_reconfirmer(p: Preuve, jour: date) -> bool:
    return p.type_source == DOCUMENTS and isinstance(p.date_source, date) and \
        p.date_source < _moins_ans(jour, RECONFIRMER_ANS)


def raison_non_utilisable(p: Preuve, etat: _Etat, jour: Optional[date] = None) -> Optional[str]:
    """None si la preuve est remise à la rédaction ; sinon le code de la raison (RAISONS)."""
    if p.statut in (PROPOSEE, RETIREE):
        return p.statut
    if p.statut != ACCEPTEE:
        return RETIREE
    r = etat.raison_source(p)
    if r:
        return r
    jour = jour or aujourd_hui()
    if isinstance(p.date_fin_validite, date) and p.date_fin_validite < jour:
        return EXPIREE
    return None


def preuve_out(db, p: Preuve, etat: Optional[_Etat] = None, jour: Optional[date] = None) -> dict:
    """Une preuve pour l'écran « Mes preuves » (le propriétaire vague 4 n'est jamais exposé)."""
    etat = etat or _Etat(db, p.owner_id, [p])
    jour = jour or aujourd_hui()
    raison = raison_non_utilisable(p, etat, jour)
    fin = p.date_fin_validite
    return {
        "id": p.id, "ref": ref_de(p), "numero": p.numero,
        "nature": p.nature, "nature_libelle": NATURE_LIBELLES.get(p.nature, ""),
        "valeur": dict(p.valeur or {}), "texte": texte_de(p.nature, p.valeur or {}, fin, attribue=est_marche_attribue(p)),
        "type_source": p.type_source, "source_libelle": source_libelle(p), "source": _source_out(p),
        "date_source": _iso(p.date_source), "a_reconfirmer": _a_reconfirmer(p, jour),
        "date_fin_validite": _iso(fin), "expiree": bool(isinstance(fin, date) and fin < jour),
        "jours_restants": (fin - jour).days if isinstance(fin, date) else None,
        "statut": p.statut, "statut_libelle": STATUT_LIBELLES.get(p.statut, ""),
        "origine": p.origine,
        "utilisable": raison is None, "raison": raison, "raison_message": RAISONS.get(raison) if raison else None,
        "cree_le": _iso(p.created_at), "modifie_le": _iso(p.updated_at), "accepte_le": _iso(p.accepte_le),
        "version": int(p.version or 0),
        # Vague 5 (E2) : champs tirés de la source publique, qui ne changent pas tant qu'elle la garde.
        "champs_source_publique": champs_source_publique(p),
    }


def _fait(p: Preuve, jour: date) -> dict:
    fin = p.date_fin_validite
    return {
        "ref": ref_de(p), "id": p.id, "numero": p.numero,
        "nature": p.nature, "nature_libelle": NATURE_LIBELLES.get(p.nature, ""),
        "type_source": p.type_source, "source_libelle": source_libelle(p), "appuie": APPUIE[p.type_source],
        "texte": texte_de(p.nature, p.valeur or {}, fin, attribue=est_marche_attribue(p)), "texte_ia": texte_pour_ia(p),
        "valeur": dict(p.valeur or {}), "source": _source_out(p),
        "date_source": _iso(p.date_source), "a_reconfirmer": _a_reconfirmer(p, jour),
        "date_fin_validite": _iso(fin),
        "proprietaire": {"kind": p.proprietaire_kind or ORGANISATION,
                         "invite_id": (p.proprietaire_invite_id or None)},
    }


def faits_autorises(db, owner_id: int, *, natures: Optional[Iterable] = None, project_id: Optional[int] = None,
                    jour: Optional[date] = None) -> list:
    """LA fonction de A : les faits que la rédaction PEUT utiliser pour l'organisation `owner_id`
    (data_owner_id), dans l'ordre de leur numéro. Seulement les preuves ACCEPTÉES de
    l'organisation (jamais celles d'un membre du groupement), encore valables (date de fin non
    dépassée), dont la source existe encore ; une estimation rattachée à un marché ne vaut que
    pour ce marché (`project_id`).

    Chaque fait : {ref « F3 » (stable, jamais réutilisé), id, numero, nature, nature_libelle,
    type_source, source_libelle, appuie, texte (pour le rapprochement, nom compris), texte_ia (à
    remettre à l'IA : sans nom ni CV), valeur, source, date_source, a_reconfirmer,
    date_fin_validite, proprietaire {kind, invite_id}}."""
    jour = jour or aujourd_hui()
    q = _q_org(db, owner_id).filter(Preuve.statut == ACCEPTEE)
    if natures:
        q = q.filter(Preuve.nature.in_(list(natures)))
    ps = q.order_by(Preuve.numero.asc()).all()
    etat = _Etat(db, owner_id, ps)
    out = []
    for p in ps:
        if raison_non_utilisable(p, etat, jour):
            continue
        if p.type_source == ESTIMATION:
            pid = (p.source or {}).get("project_id")
            if pid and pid != project_id:
                continue
        out.append(_fait(p, jour))
    return out


def faits_ecartes(db, owner_id: int, *, jour: Optional[date] = None) -> list:
    """Preuves ACCEPTÉES que la rédaction n'utilise pas, avec la raison (expirée, source
    introuvable) : [{ref, id, nature, texte, raison, message}]. Pour le dire à l'utilisateur."""
    jour = jour or aujourd_hui()
    ps = _q_org(db, owner_id).filter(Preuve.statut == ACCEPTEE).order_by(Preuve.numero.asc()).all()
    etat = _Etat(db, owner_id, ps)
    out = []
    for p in ps:
        r = raison_non_utilisable(p, etat, jour)
        if r:
            out.append({"ref": ref_de(p), "id": p.id, "nature": p.nature,
                        "texte": texte_de(p.nature, p.valeur or {}, p.date_fin_validite, attribue=est_marche_attribue(p)),
                        "titre": titre_court(p.nature, p.valeur or {}),
                        "raison": r, "message": RAISONS[r], "raison_courte": RAISONS_COURTES.get(r, "")})
    return out


# La raison en quelques mots, pour une ligne « Qualibat RGE : date de fin de validité dépassée ».
RAISONS_COURTES = {
    EXPIREE: "date de fin de validité dépassée",
    SOURCE_INTROUVABLE: "document d'origine retiré de « Mon savoir-faire »",
    JUSTIFICATIF_INTROUVABLE: "justificatif retiré de vos documents",
    RETIREE: "retirée", PROPOSEE: "pas encore cochée",
}


def titre_court(nature: str, valeur: dict) -> str:
    """Le titre d'une fiche tel que « Mes preuves » l'affiche (jamais son numéro « F6 ») ; pour une
    personne, sa fonction seule."""
    v = valeur or {}
    if nature == SALARIE:
        return str(v.get("fonction") or "Une personne de l'équipe")[:120]
    if nature == CHIFFRE_CLE:
        s = f"{v.get('libelle', '')} : {_nombre(v.get('valeur'))}" + (f" {v['unite']}" if v.get("unite") else "")
        return s[:120]
    principal = {REFERENCE: "objet", QUALIFICATION: "nom", MATERIEL: "designation"}.get(nature, "")
    return str(v.get(principal) or NATURE_LIBELLES.get(nature, "Preuve"))[:120]


def compteurs(db, owner_id: int) -> dict:
    """{nature: {proposee, acceptee, retiree}} de l'organisation."""
    from sqlalchemy import func
    out = {n: {s: 0 for s in STATUTS} for n in NATURES}
    for nature, statut, n in (db.query(Preuve.nature, Preuve.statut, func.count(Preuve.id))
                              .filter(Preuve.owner_id == owner_id, Preuve.proprietaire_invite_id == 0,
                                      Preuve.statut != SUPPRIMEE)
                              .group_by(Preuve.nature, Preuve.statut).all()):
        if nature in out and statut in out[nature]:
            out[nature][statut] = int(n)
    return out


def passage(db, p: Preuve) -> dict:
    """Le passage exact dans son document (« lien vers le passage ») : texte avant / après."""
    s = dict(p.source or {})
    if p.type_source != DOCUMENTS or not s.get("doc_id"):
        raise PreuveError(404, "passage_introuvable", "Cette preuve n'a pas de passage dans vos documents.")
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == s.get("doc_id"),
                                        KnowledgeDoc.user_id.in_(membres(db, p.owner_id))).first()
    if doc is None:
        raise PreuveError(404, SOURCE_INTROUVABLE, RAISONS[SOURCE_INTROUVABLE])
    texte = doc.text or ""
    ext = s.get("passage") or ""
    debut = s.get("debut")
    if not (isinstance(debut, int) and texte[debut:debut + len(ext)] == ext):
        loc = localiser(texte, ext)
        debut = loc[0] if loc else None
    if debut is None:
        return {"doc_id": doc.id, "doc_nom": doc.name, "passage": ext, "avant": "", "apres": "", "debut": None}
    fin = min(len(texte), debut + len(ext))
    return {"doc_id": doc.id, "doc_nom": doc.name, "passage": texte[debut:fin] or ext,
            "avant": texte[max(0, debut - CONTEXTE_PASSAGE):debut], "apres": texte[fin:fin + CONTEXTE_PASSAGE],
            "debut": debut}


def preuves_du_document(db, owner_id: int, doc_id: int) -> int:
    """Preuves acceptées ou proposées dont le passage vient de ce document de « Mon savoir-faire »
    (pour prévenir : elles perdront leur source si le document est retiré)."""
    return _q_org(db, owner_id).filter(Preuve.source_doc_id == doc_id,
                                       Preuve.statut.in_([PROPOSEE, ACCEPTEE])).count()


# ── Noms à masquer (doctrine § 7, règle 9) ───────────────────────────────────────────

def personnes(db, owner_ids: Iterable) -> list:
    """[{nom, fonction}] des fiches « Équipe » de ces organisations (tous statuts, y compris les
    fiches d'un membre du groupement) : ajoutés aux noms masqués avant tout appel à l'IA."""
    ids = [o for o in set(owner_ids or []) if o]
    if not ids:
        return []
    out = []
    for p in db.query(Preuve).filter(Preuve.owner_id.in_(ids), Preuve.nature == SALARIE,
                                     Preuve.statut != SUPPRIMEE).order_by(Preuve.id.asc()).all():
        v = p.valeur or {}
        if v.get("nom"):
            out.append({"nom": v.get("nom"), "fonction": v.get("fonction") or ""})
    return out


# ── RGPD : export, effacement, transfert ─────────────────────────────────────────────

def exporter(db, owner_id: int) -> list:
    """Export RGPD (art. 15 et 20) : toutes les preuves de l'organisation, CV compris."""
    out = []
    for p in lister(db, owner_id):
        out.append({
            "ref": ref_de(p), "nature": p.nature, "valeur": dict(p.valeur or {}),
            "texte": texte_de(p.nature, p.valeur or {}, p.date_fin_validite, attribue=est_marche_attribue(p)),
            "type_source": p.type_source, "source_libelle": source_libelle(p), "source": dict(p.source or {}),
            "date_source": _iso(p.date_source), "date_fin_validite": _iso(p.date_fin_validite),
            "statut": p.statut, "origine": p.origine, "cree_le": _iso(p.created_at),
            "modifie_le": _iso(p.updated_at), "accepte_le": _iso(p.accepte_le), "retire_le": _iso(p.retire_le),
        })
    return out


def effacer_tout(db, owner_id: int) -> int:
    """Effacement du compte propriétaire : TOUTES ses preuves (organisation et membres du
    groupement), lignes réservées comprises. Pas de commit (transaction de l'appelant)."""
    return db.query(Preuve).filter(Preuve.owner_id == owner_id).delete(synchronize_session=False)


def transferer(db, old_id: int, new_id: int, *, numeros: str = "source") -> int:
    """Les preuves de `old_id` passent à `new_id` (pas de commit). Les numéros ne se heurtent jamais :
      • numeros='source' (transfert de propriété : les preuves qui partent SONT celles de
        l'organisation) : elles gardent leurs numéros ; une ligne déjà portée par `new_id` (cas
        théorique) est renumérotée au-delà ;
      • numeros='destination' (compte d'un membre effacé : l'organisation est chez `new_id`) : les
        preuves de l'organisation gardent leurs numéros ; une ligne du membre qui en heurte une est
        renumérotée au-delà."""
    if not old_id or not new_id or old_id == new_id:
        return 0
    from sqlalchemy import func
    garde, deplace = (old_id, new_id) if numeros == "source" else (new_id, old_id)
    scopes = {r[0] for r in db.query(Preuve.proprietaire_invite_id).filter(Preuve.owner_id == old_id).distinct()}
    for inv in scopes:
        pris = {r[0] for r in db.query(Preuve.numero).filter(Preuve.owner_id == garde,
                                                              Preuve.proprietaire_invite_id == inv)}
        heurts = sorted((x for x in db.query(Preuve).filter(Preuve.owner_id == deplace,
                                                             Preuve.proprietaire_invite_id == inv)
                         if x.numero in pris), key=lambda x: x.numero)
        if not heurts:
            continue
        # Deux temps (numéros négatifs, puis définitifs) : aucune étape ne heurte la contrainte
        # d'unicité, quel que soit l'ordre des mises à jour.
        for i, h in enumerate(heurts, start=1):
            h.numero = -i
        db.flush()
        base = max(pris | {int(db.query(func.max(Preuve.numero)).filter(
            Preuve.owner_id == deplace, Preuve.proprietaire_invite_id == inv).scalar() or 0)})
        for i, h in enumerate(heurts, start=1):
            h.numero = base + i
        db.flush()
    n = db.query(Preuve).filter(Preuve.owner_id == old_id).update({Preuve.owner_id: new_id},
                                                                  synchronize_session=False)
    db.flush()
    return n
