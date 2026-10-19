"""
LE CARNET DE NOTES (rédaction, vague 6 — F de l'étude, § 6.11) : « Apprendre de ses résultats ».

Contrat : docs/REDACTION_V6.md (section F). Ce module est le SEUL point d'écriture du carnet
(colonne JSON `projects.carnet_notes`, migration `a2carnetnotes`) ; le routeur app/routers/carnet.py ne fait
que contrôler l'accès et traduire les erreurs (`CarnetError`).

Ce que fait le carnet, SANS IA :
  • un marché passe à « Perdu » : la date est notée (`perdu_le`) ; le bouton « Demandez vos notes » ouvre un
    courrier PRÉ-REMPLI, avec l'article du code de la commande publique qui correspond à la procédure
    (R2181-2 en procédure adaptée, R2181-4 et R2181-3 en procédure formalisée, relus sur Légifrance le
    19/10/2026, versions en vigueur depuis le 01/04/2019) et le message sur le délai. Adjugo n'envoie RIEN :
    l'utilisateur copie le courrier ou l'ouvre dans sa messagerie, et c'est lui qui l'envoie ;
  • un rappel 2 jours après le passage à « Perdu », dans l'application (tableau de bord, page du marché) tant
    que la demande n'est pas marquée envoyée ; un courriel seulement si l'utilisateur a des alertes actives
    (veille des marchés), par l'infrastructure d'envoi existante (cron de la veille), une seule fois, et
    toujours à l'utilisateur lui-même (jamais à l'acheteur) ;
  • quand la réponse arrive : un formulaire tiré de « Comment vous serez noté » (critères ET sous-critères) —
    votre note, la note maximale, la note de l'offre retenue si elle est donnée, le commentaire de l'acheteur ;
    le courrier collé est lu SANS IA (lignes « Critère : 12 / 20 ») ; chaque valeur proposée montre la ligne du
    courrier où elle est écrite et l'utilisateur VALIDE ;
  • option IA (bouton) : l'IA propose les notes du courrier collé ; chaque nombre doit être retrouvé MOT POUR
    MOT dans la ligne du courrier qu'elle recopie (elle-même retrouvée dans le courrier), chaque commentaire mot
    pour mot ; rien n'est enregistré avant la validation de l'utilisateur. Compte comme une question du jour
    (quota existant), rendue si l'IA tombe ou si rien n'est retenu ; `tenant_scope` et `pii_scope` posés ; les
    adresses et numéros de téléphone du courrier sont masqués avant l'appel, les noms de l'équipe aussi ;
  • « Où vous perdez des points » (tableau de bord) : chaque note ramenée en pourcentage de la note maximale,
    les critères regroupés par famille (technique, environnement, délais, prix, social) PROPOSÉE sans IA d'après
    le nom du critère puis confirmée par l'utilisateur à l'enregistrement ; une moyenne n'est affichée qu'à
    partir de 3 marchés. Uniquement les marchés de l'organisation : aucune statistique entre clients ;
  • dans l'atelier d'un nouveau dossier, sur la partie concernée : « La dernière fois, l'acheteur a écrit : … »
    (même famille de critère, même acheteur en priorité). Affiché seulement, jamais envoyé à l'IA ;
  • un marché gagné : « Ajouter ce dossier à mon savoir-faire », à l'initiative de l'utilisateur — le texte de
    SES parties seulement (jamais celles d'un partenaire), sans CV ni renvois internes.

Groupement (vague 4, cloisonnement intact) : les notes du marché sont communes aux membres (lues dans l'espace du
partenaire, avec ses parties mises en avant) ; le courrier collé, ses extraits et la demande restent chez le chef
de file. Le lien « Chercher un partenaire qui couvre ce manque » ouvre le réseau : un constat, pas une
recommandation.
"""
import copy
import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models import Company, DossierSection, DossierSectionVersion, Project, User

logger = logging.getLogger("adjugo")

SCHEMA = 1
LIGNES_MAX = 40
CRITERE_MAX = 200
COMMENTAIRE_MAX = 1500
COURRIER_MIN = 40
COURRIER_MAX = 20000
EXTRAIT_MAX = 400
RAPPEL_JOURS = 2                # rappel 2 jours après le passage à « Perdu » (§ 6.11)
RAPPEL_FIN_JOURS = 60           # au-delà, plus de rappel dans l'application
COURRIEL_FIN_JOURS = 14         # au-delà, aucun courriel de rappel (un cron arrêté ne réveille pas un vieux marché)
MOYENNE_MIN = 3                 # une moyenne n'est affichée qu'à partir de 3 marchés (§ 6.11)

PERDU, GAGNE = "perdu", "gagne"
ADAPTEE, FORMALISEE, INCONNUE = "adaptee", "formalisee", ""
SAISIE, COURRIER, IA = "saisie", "courrier", "ia"


class CarnetError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def detail(self) -> dict:
        return dict({"code": self.code, "message": self.message}, **self.extra)


# ── Vocabulaire ───────────────────────────────────────────────────────────────────────

FAMILLES = (("technique", "Technique"), ("environnement", "Environnement"), ("delais", "Délais"),
            ("prix", "Prix"), ("social", "Social et insertion"), ("autre", "Autre"))
FAMILLE_LIB = dict(FAMILLES)

# Familles proposées SANS IA d'après le nom du critère (dans cet ordre : « Démarche environnementale » est de
# l'environnement, « Délai d'exécution » des délais, avant « exécution » qui est technique).
_FAMILLE_RX = (
    ("prix", re.compile(r"\bprix\b|\bmontant|\bcouts?\b|\btarif|financ|economique|\bdevis\b")),
    ("environnement", re.compile(r"environ|ecolog|dechet|carbone|developpement durable|\benergeti|nuisance|biodivers"
                                 r"|\bdurable")),
    ("delais", re.compile(r"\bdelais?\b|planning|calendrier|\bduree\b|reactivit")),
    ("social", re.compile(r"insertion|\bsocia|\bemploi|handicap|apprenti|solidaire")),
    ("technique", re.compile(r"techni|methodo|\bmoyens?\b|organisation|qualit|memoire|referen|competen|materiel"
                             r"|humain|securit|savoir|maintenance|service|assistance|phasage|execution|approche"
                             r"|demarche|valeur|chantier|equipe|encadrement")),
)

PROCEDURES = (
    {"code": ADAPTEE, "libelle": "Procédure adaptée", "article": "R2181-2"},
    {"code": FORMALISEE, "libelle": "Procédure formalisée (appel d'offres, procédure avec négociation…)",
     "article": "R2181-4"},
    {"code": INCONNUE, "libelle": "Je ne sais pas", "article": "R2181-1 à R2181-4"},
)

BULLE = ("Après un marché, l'acheteur peut vous donner vos notes, critère par critère. Adjugo vous prépare le courrier "
         "pour les demander (c'est vous qui l'envoyez), puis vous aide à les saisir. Vos notes ne servent qu'à votre "
         "entreprise : aucune comparaison avec d'autres clients.")
BULLE_TABLEAU = ("Chaque note est ramenée en pourcentage de la note maximale du critère. Les critères sont regroupés "
                 "par famille : Adjugo la propose d'après le nom du critère, sans IA, et vous la confirmez en "
                 "enregistrant les notes. Une moyenne n'apparaît qu'à partir de 3 marchés. Seuls vos marchés comptent.")
BULLE_IA = ("Adjugo demande à l'IA de lire le courrier collé. Une note n'est proposée que si chacun de ses nombres est "
            "retrouvé tel quel dans une ligne du courrier, et un commentaire que s'il y est mot pour mot. Rien n'est "
            "enregistré avant votre validation. Cela compte comme une question du jour ; si rien n'est retenu ou si "
            "l'IA ne répond pas, rien n'est décompté.")
BULLE_LECTURE = ("Adjugo cherche dans le courrier, sans IA, les lignes qui nomment un critère et donnent une note "
                 "(« 12 / 20 », « 12 sur 20 »). Chaque valeur proposée montre la ligne où elle est écrite : vérifiez-la "
                 "avant de valider.")
BULLE_SAVOIR_FAIRE = ("Le texte de vos parties de ce dossier (pas celles de vos partenaires) rejoint « Mon "
                      "savoir-faire » : Adjugo pourra s'en servir pour vos prochains dossiers. Les CV et les renvois "
                      "internes n'y sont pas repris. Vous pouvez le retirer à tout moment.")
BULLE_DERNIERE_FOIS = ("Commentaire que vous avez saisi dans le carnet de notes d'un ancien marché, sur un critère de la "
                       "même famille (le même acheteur d'abord). Il n'est pas envoyé à l'IA.")
MSG_PAS_ENVOYE = ("Adjugo n'envoie rien : c'est vous qui envoyez ce courrier, depuis votre messagerie ou la plateforme "
                  "de l'acheteur.")
MSG_DELAI = {
    ADAPTEE: ("Écrivez vite : l'acheteur doit vous répondre dans les 15 jours qui suivent la réception de votre "
              "demande (article R2181-2), et l'information doit arriver à temps pour pouvoir contester avant la "
              "signature du marché."),
    FORMALISEE: ("Écrivez vite : l'acheteur doit vous répondre dans les 15 jours qui suivent la réception de votre "
                 "demande (article R2181-4), et l'information doit arriver à temps pour pouvoir contester avant la "
                 "signature du marché. En procédure formalisée, le marché peut être signé 11 jours après l'envoi du "
                 "courrier de rejet (16 jours s'il n'a pas été envoyé par voie électronique, article R2182-1)."),
    INCONNUE: ("Écrivez vite : l'acheteur doit vous répondre dans les 15 jours qui suivent la réception de votre "
               "demande, et l'information doit arriver à temps pour pouvoir contester avant la signature du marché. "
               "Choisissez la procédure du marché pour citer le bon article."),
}
MSG_ADAPTEE_NOTES = ("En procédure adaptée, les notes sont à demander, pas toujours obtenues : le code oblige "
                     "l'acheteur à donner les motifs du rejet, pas le détail des notes.")
MSG_RAPPEL = ("Ce marché est passé à « Perdu » il y a plus de 2 jours : demandez vos notes à l'acheteur tant qu'il "
              "est temps de contester.")
MSG_GRILLE = "Critères et sous-critères de « Comment vous serez noté », tels qu'écrits dans le règlement."
MSG_ANALYSE = ("Critères lus par l'analyse du marché : vérifiez-les avec le courrier de l'acheteur, et ajoutez ceux "
               "qui manquent.")
MSG_SANS_CRITERE = "Aucun critère retrouvé pour ce marché : ajoutez ceux du courrier de l'acheteur."
MSG_IA_PANNE = ("La lecture n'a pas abouti : le service d'IA est indisponible pour le moment. Rien n'a été décompté.")


def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fold(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'").replace("‘", "'").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t.lower()).strip()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(microsecond=0).isoformat() if isinstance(dt, datetime) else None


def _date(s) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(s)) if s else None
    except (TypeError, ValueError):
        return None
    if d is not None and d.tzinfo is not None:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


def _jj(s) -> str:
    d = _date(s)
    return d.strftime("%d/%m/%Y") if d else ""


def _statut(project) -> str:
    st = getattr(project, "status", None)
    return st.value if hasattr(st, "value") else str(st or "")


def famille_proposee(nom: str, parent: str = "") -> str:
    """La famille d'un critère d'après son nom, SANS IA ; un sous-critère sans famille reconnue prend celle de son
    critère ; sinon « autre »."""
    f = _fold(nom)
    for code, rx in _FAMILLE_RX:
        if rx.search(f):
            return code
    return famille_proposee(parent) if parent else "autre"


# ── Nombres : tels qu'écrits ─────────────────────────────────────────────────────────

_NB = r"\d{1,4}(?:[.,]\d{1,3})?"
_NB_RX = re.compile(r"(?<![\d.,])" + _NB + r"(?![\d.,]*\d)")


def nombre(v) -> Optional[float]:
    """« 32,5 », « 32.5 », 32.5 → 32.5 ; vide → None ; illisible → ValueError."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("nombre illisible")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip().replace(" ", "").replace(" ", "")
        if not s:
            return None
        if not re.fullmatch(r"\d{1,5}(?:[.,]\d{1,3})?", s):
            raise ValueError("nombre illisible")
        x = float(s.replace(",", "."))
    if x != x or x < 0 or x > 100000:
        raise ValueError("nombre hors bornes")
    return round(x, 3)


def ecrit(x: Optional[float]) -> str:
    """32.5 → « 32,5 » ; 40.0 → « 40 »."""
    if x is None:
        return ""
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def pct(note: Optional[float], note_max: Optional[float]) -> Optional[int]:
    if note is None or not note_max:
        return None
    return int(round(100.0 * note / note_max))


def nombres_de(texte: str) -> list:
    """Les nombres écrits dans un texte, avec leur valeur : [(« 32,5 », 32.5), …]."""
    out = []
    for m in _NB_RX.finditer(str(texte or "")):
        try:
            out.append((m.group(0), float(m.group(0).replace(",", "."))))
        except ValueError:
            continue
    return out


def _retrouve_nombre(valeur: Optional[float], texte: str) -> Optional[str]:
    """Le nombre `valeur` est-il ÉCRIT dans `texte` ? Renvoie sa forme écrite, sinon None."""
    if valeur is None:
        return None
    for lit, v in nombres_de(texte):
        if abs(v - valeur) < 1e-9:
            return lit
    return None


def _dans(courrier: str, extrait: str, min_len: int = 6) -> bool:
    """L'extrait est-il dans le courrier, mot pour mot (casse, accents, espaces et apostrophes tolérés) ?"""
    e = _fold(extrait).strip(" «»\"'")
    return len(e) >= min_len and e in _fold(courrier)


# ── Lecture du carnet ────────────────────────────────────────────────────────────────

def carnet(project) -> dict:
    """Le carnet du marché (copie de travail), normalisé."""
    c = getattr(project, "carnet_notes", None)
    c = copy.deepcopy(c) if isinstance(c, dict) else {}
    c.setdefault("schema", SCHEMA)
    c.setdefault("rev", 0)
    return c


def _ecrire(db, project, c: dict) -> None:
    c["rev"] = int(c.get("rev") or 0) + 1
    project.carnet_notes = c


def _verrouiller(db, project) -> Project:
    """La ligne du marché, prise sous verrou (Postgres) : deux écritures du carnet ne se croisent pas."""
    p = db.query(Project).filter(Project.id == project.id).with_for_update().first()
    return p if p is not None else project


def reponse(project) -> Optional[dict]:
    r = carnet(project).get("reponse")
    return r if isinstance(r, dict) and r.get("lignes") else None


# ── Changement d'étape (appelé par PUT /api/projects/{id}) ───────────────────────────

def apres_changement_d_etape(project, ancien: str, nouveau: str, user_id: Optional[int]) -> None:
    """Passage à « Perdu » : la date est notée (départ du rappel des 2 jours). Sans effet sinon. Ne lève pas."""
    try:
        if nouveau != PERDU or ancien == PERDU:
            return
        c = carnet(project)
        c["perdu_le"] = _iso(_now())
        c["perdu_par"] = int(user_id) if user_id else None
        c.pop("rappel_courriel", None)
        c.pop("rappel_masque", None)
        c["rev"] = int(c.get("rev") or 0) + 1
        project.carnet_notes = c
    except Exception as e:      # noqa: BLE001 — le changement d'étape ne casse jamais pour le carnet
        logger.warning("carnet : passage à « Perdu » non noté (marché %s) : %s", getattr(project, "id", "?"),
                       type(e).__name__)


def rappel_du(project, now: Optional[datetime] = None) -> bool:
    """Le rappel « Demandez vos notes » est-il dû ? Marché perdu depuis 2 jours au moins (et moins de 60), demande
    pas encore marquée envoyée, notes pas encore saisies, rappel pas masqué."""
    if _statut(project) != PERDU:
        return False
    c = carnet(project)
    d = _date(c.get("perdu_le"))
    if d is None or c.get("demande") or c.get("rappel_masque") or reponse(project):
        return False
    now = now or _now()
    return d + timedelta(days=RAPPEL_JOURS) <= now <= d + timedelta(days=RAPPEL_FIN_JOURS)


# ── Les critères du marché (« Comment vous serez noté ») ─────────────────────────────

def _analysis(project) -> dict:
    a = getattr(project, "ai_analysis", None)
    return a if isinstance(a, dict) else {}


def _details(project) -> dict:
    d = _analysis(project).get("details")
    return d if isinstance(d, dict) else {}


def _max_du_poids(poids: str) -> Optional[float]:
    """Un poids écrit en points (« 40 points ») donne la note maximale ; un pourcentage, non (la note peut être
    sur 20 ou sur 100)."""
    try:
        from app.services.grille_notation import parse_weight
        w = parse_weight(poids) if poids else None
    except Exception:       # noqa: BLE001
        w = None
    return float(w["valeur"]) if w and w.get("unite") == "points" else None


def criteres_du_marche(project) -> dict:
    """Les critères (et sous-critères) qui forment le formulaire : ceux de « Comment vous serez noté » (phrase
    retrouvée dans le règlement), sinon ceux de l'analyse (à vérifier), sinon aucun."""
    from app.services import atelier_plan as ap
    out = []
    try:
        lignes = ap._grille_lines(ap._grille(_analysis(project)))
    except Exception:       # noqa: BLE001 — grille illisible : repli sur l'analyse
        lignes = []
    for ln in lignes:
        cle = str(ln.get("id") or "")[:20]
        if not cle:
            continue
        nom = _flat(ln.get("critere"))[:CRITERE_MAX]
        out.append({"cle": cle, "critere": nom, "parent": "", "poids": _flat(ln.get("poids"))[:40], "niveau": 1,
                    "famille_proposee": famille_proposee(nom)})
        for k, sc in enumerate(ln.get("sous_criteres") or [], 1):
            snom = _flat(sc.get("critere"))[:CRITERE_MAX]
            if not snom:
                continue
            scle = (str(sc.get("id") or "") or f"{cle}.{k}")[:20]
            out.append({"cle": scle, "critere": snom, "parent": cle, "poids": _flat(sc.get("poids"))[:40], "niveau": 2,
                        "famille_proposee": famille_proposee(snom, nom)})
    if out:
        return {"source": "grille", "message": MSG_GRILLE, "lignes": out}
    for i, c in enumerate(_details(project).get("criteres_attribution") or []):
        if not isinstance(c, dict):
            continue
        nom = _flat(c.get("critere") or c.get("nom"))[:CRITERE_MAX]
        if nom:
            out.append({"cle": f"a{i + 1}", "critere": nom, "parent": "", "poids": _flat(c.get("ponderation"))[:40],
                        "niveau": 1, "famille_proposee": famille_proposee(nom)})
    if out:
        return {"source": "analyse", "message": MSG_ANALYSE, "lignes": out}
    return {"source": "", "message": MSG_SANS_CRITERE, "lignes": []}


# ── La procédure (l'article à citer) ─────────────────────────────────────────────────

_RX_ADAPTEE = re.compile(r"procedure adaptee|\bmapa\b|r\.? ?2123-1\b|r\.? ?2123-4\b|r\.? ?2123-5\b")
_RX_FORMALISEE = re.compile(r"appel d'offres? (?:ouvert|restreint)|procedure formalisee|r\.? ?2124-[1-6]\b"
                            r"|r\.? ?2161-[2-9]\b|procedure (?:concurrentielle )?avec negociation"
                            r"|dialogue competitif")


def _phrases(texte: str) -> list:
    """Les phrases d'un texte (coupées aux fins de phrase et de ligne), telles qu'écrites."""
    out = []
    for ln in str(texte or "").split("\n"):
        for ph in re.split(r"(?<=[.;!?])\s+", ln):
            ph = _flat(ph)
            if ph:
                out.append(ph)
    return out


def procedure_du_marche(project) -> dict:
    """La procédure du marché, repérée SANS IA : dans le règlement lu (phrase citée telle qu'écrite), sinon dans la
    nature du marché lue par l'analyse (à vérifier). Les deux procédures à la fois, ou rien : « je ne sais pas »,
    l'utilisateur choisit."""
    sources = []
    try:
        from app.services import dce_texte
        rc = dce_texte.dce_reglement(project)
        if rc:
            sources.append(("règlement de la consultation", rc[:200000]))
    except Exception:       # noqa: BLE001 — lecture rangée absente : l'analyse suffit
        pass
    nature = _flat(_details(project).get("nature_marche"))
    if nature:
        sources.append(("analyse du marché", nature))
    for src, texte in sources:
        trouve = {}
        for ph in _phrases(texte):
            f = _fold(ph)
            if ADAPTEE not in trouve and _RX_ADAPTEE.search(f):
                trouve[ADAPTEE] = ph
            if FORMALISEE not in trouve and _RX_FORMALISEE.search(f):
                trouve[FORMALISEE] = ph
        if len(trouve) == 2:
            return {"code": INCONNUE, "phrase": "", "source": src,
                    "message": "Le dossier parle à la fois de procédure adaptée et de procédure formalisée : "
                               "choisissez celle du marché."}
        if trouve:
            code, phrase = next(iter(trouve.items()))
            return {"code": code, "phrase": phrase[:300], "source": src,
                    "message": ("Lu dans le règlement de la consultation : vérifiez la procédure avant d'envoyer."
                                if src.startswith("règlement") else
                                "Lu dans l'analyse du marché : vérifiez la procédure avant d'envoyer.")}
    return {"code": INCONNUE, "phrase": "", "source": "",
            "message": "Adjugo n'a pas repéré la procédure du marché : choisissez-la pour citer le bon article."}


# ── Le courrier « Demandez vos notes » ───────────────────────────────────────────────

def _entreprise(db, project) -> tuple:
    from app.routers.invites import tenant_owner_id
    owner = tenant_owner_id(project, db) or project.user_id
    comp = db.query(Company).filter(Company.user_id == owner).first()
    nom = _flat(comp.name if comp else "")[:200]
    rep = _flat(comp.representant_legal if comp else "")[:200]
    return nom, rep


def _en_groupement(project) -> bool:
    plan = getattr(project, "groupement_plan", None)
    membres = (plan or {}).get("members") if isinstance(plan, dict) else None
    return isinstance(membres, list) and len(membres) >= 2


def courrier(db, project, procedure: Optional[str] = None) -> dict:
    """Le courrier pré-rempli (objet, texte, destinataire lu dans l'analyse). Adjugo ne l'envoie jamais."""
    det = _details(project)
    proc = procedure if procedure in (ADAPTEE, FORMALISEE, INCONNUE) else procedure_du_marche(project)["code"]
    intitule = _flat(det.get("intitule_marche") or project.name)[:300]
    ref = _flat((_analysis(project).get("source") or {}).get("official_ref")
                if isinstance(_analysis(project).get("source"), dict) else "")[:60]
    nom, rep = _entreprise(db, project)
    sujet = "l'offre du groupement dont nous sommes le chef de file" if _en_groupement(project) else "notre offre"
    crits = [x["critere"] for x in criteres_du_marche(project)["lignes"] if x["niveau"] == 1][:8]
    liste = (" (" + ", ".join(crits) + ")") if crits else ""
    p = ["Madame, Monsieur,",
         f"Vous nous avez informés du rejet de {sujet} pour le marché « {intitule} »"
         + (f" (référence {ref})" if ref else "") + "."]
    if proc == ADAPTEE:
        p.append("En application de l'article R2181-2 du code de la commande publique, nous vous demandons de nous "
                 "communiquer les motifs de ce rejet. Si notre offre n'était ni inappropriée, ni irrégulière, ni "
                 "inacceptable, nous vous demandons également les caractéristiques et avantages de l'offre retenue "
                 "ainsi que le nom de l'attributaire du marché.")
        lien = "Pour comprendre ces motifs"
    elif proc == FORMALISEE:
        p.append("En application de l'article R2181-4 du code de la commande publique, nous vous demandons de nous "
                 "communiquer les caractéristiques et les avantages de l'offre retenue.")
        lien = "Pour comprendre les motifs du rejet de notre offre (article R2181-3)"
    else:
        p.append("En application des articles R2181-1 à R2181-4 du code de la commande publique, nous vous demandons "
                 "de nous communiquer les motifs du rejet de notre offre, ainsi que les caractéristiques et avantages "
                 "de l'offre retenue.")
        lien = "Pour comprendre ces motifs"
    p.append(f"{lien}, nous vous serions reconnaissants de nous indiquer, pour chaque critère et sous-critère de "
             f"jugement des offres{liste}, la note obtenue par notre offre, la note maximale, la note de l'offre "
             "retenue et l'appréciation qui la justifie, ainsi que notre classement.")
    p.append("Nous vous remercions par avance de votre réponse.")
    p.append("Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées.")
    signe = "\n".join(x for x in (rep, nom) if x)
    if signe:
        p.append(signe)
    objet = f"Demande des motifs du rejet de notre offre — {intitule}"[:250]
    contact = det.get("contact") if isinstance(det.get("contact"), dict) else {}
    dest = _flat(contact.get("email"))[:200]
    if not re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[A-Za-z]{2,24}", dest or ""):
        dest = ""
    art = next(x["article"] for x in PROCEDURES if x["code"] == proc)
    return {"procedure": proc, "article": art, "objet": objet, "corps": "\n\n".join(p),
            "destinataire": dest,
            "destinataire_message": ("Adresse lue dans l'analyse du marché : vérifiez-la." if dest else
                                     "Aucune adresse de l'acheteur dans l'analyse : ajoutez-la dans votre messagerie."),
            "message_delai": MSG_DELAI[proc], "message_notes": MSG_ADAPTEE_NOTES if proc == ADAPTEE else "",
            "message_envoi": MSG_PAS_ENVOYE}


# ── Lecture du courrier, SANS IA ─────────────────────────────────────────────────────

_STOP = {"critere", "criteres", "sous", "note", "notes", "notee", "offre", "offres", "candidat", "points", "point",
         "valeur", "appreciee", "apprecie", "jugement", "ponderation", "selon", "pour", "dans", "avec", "des", "les",
         "aux", "sur", "par", "une", "cette", "leur", "leurs", "elle", "elles", "ainsi", "entre", "chaque"}
_PAIRE = re.compile(r"(?<![\d.,/])(" + _NB + r")\s*(?:points?|pts?)?\s*(?:/|sur)\s*(" + _NB + r")(?![\d.,]|\s*/\s*\d)")
_GAGNANT = re.compile(r"attributaire|offre retenue|\bretenue?s?\b|laureat|titulaire|gagnant|mieux[- ]disant"
                      r"|meilleure (?:offre|note)")
_VOUS = re.compile(r"\bvotre\b|\bvous\b|\bnotre\b|obtenu|\bvos\b")
_COMMENT = re.compile(r"^\s*(?:[-•*]\s*)?(?:appreciations?|commentaires?|observations?|motifs?|justifications?|analyse"
                      r"|points? forts?|points? faibles?|points? a ameliorer)\b[^:]{0,40}:\s*(\S.*)$")


def _stems(nom: str) -> list:
    out = []
    for w in re.findall(r"[a-z0-9']+", _fold(nom)):
        w = w.split("'")[-1]
        if len(w) >= 4 and w not in _STOP:
            s = w[:5]
            if s not in out:
                out.append(s)
    return out[:8]


def _requis(n: int) -> int:
    return 1 if n <= 2 else 2


def _mentions(ligne_f: str, crit: list) -> Optional[dict]:
    """Le critère que nomme une ligne du courrier (le plus de mots principaux retrouvés ; un sous-critère l'emporte
    à égalité), ou None."""
    best, best_k = None, None
    for c in crit:
        st = c["_stems"]
        if not st:
            continue
        hits = sum(1 for s in st if re.search(r"(?<![a-z0-9])" + re.escape(s), ligne_f))
        if hits < _requis(len(st)):
            continue
        k = (hits / len(st), hits, 1 if c.get("parent") else 0)
        if best_k is None or k > best_k:
            best, best_k = c, k
    return best


def lire_courrier(texte: str, criteres: list) -> dict:
    """Propose, SANS IA, les notes écrites dans le courrier collé : pour chaque critère nommé sur une ligne, la
    première note « x / y » (ou « x sur y ») qui suit = votre note ; une note sur une ligne qui parle de l'offre
    retenue (attributaire, lauréat…) = la note de l'offre retenue ; une ligne « Appréciation : … » = le
    commentaire. Chaque valeur garde la ligne du courrier où elle est écrite."""
    lignes = [ln for ln in str(texte or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    crit = [dict(c, _stems=_stems(c.get("critere"))) for c in criteres or [] if c.get("cle")]
    props, courant, depuis = {}, None, 0
    for i, brut in enumerate(lignes):
        ln = _flat(brut)
        if not ln:
            continue
        f = _fold(ln)
        m = _mentions(f, crit)
        if m is not None:
            courant, depuis = m, 0
        elif courant is not None:
            depuis += 1
            if depuis > 8:
                courant = None
        if courant is None:
            continue
        p = props.setdefault(courant["cle"], {"cle": courant["cle"]})
        cm = _COMMENT.match(f)
        if cm and not _PAIRE.search(f):
            debut = len(ln) - len(cm.group(1)) if len(cm.group(1)) <= len(ln) else 0
            com = ln if re.match(r"\s*(?:[-•*]\s*)?points?\b", f) else ln[debut:].strip()
            if com and len(com) >= 8:
                p["commentaire"] = ((p.get("commentaire") + " ") if p.get("commentaire") else "") + com
                p["commentaire"] = p["commentaire"][:COMMENTAIRE_MAX]
            continue
        pos = 0
        for pm in _PAIRE.finditer(f):
            avant = f[pos:pm.start()]
            pos = pm.end()
            n, mx = pm.group(1), pm.group(2)
            try:
                vn, vm = float(n.replace(",", ".")), float(mx.replace(",", "."))
            except ValueError:
                continue
            if vm <= 0 or vn > vm:
                continue
            extrait = ln[:EXTRAIT_MAX]
            if _GAGNANT.search(avant) and not _VOUS.search(avant):
                if "note_gagnant" not in p:
                    p.update(note_gagnant=n, note_gagnant_max=mx, extrait_gagnant=extrait)
            elif "note" not in p:
                p.update(note=n, note_max=mx, extrait_note=extrait)
            elif "note_gagnant" not in p and _GAGNANT.search(f):
                p.update(note_gagnant=n, note_gagnant_max=mx, extrait_gagnant=extrait)
    out = {}
    for cle, p in props.items():
        if not any(k in p for k in ("note", "note_gagnant", "commentaire")):
            continue
        if "commentaire" in p and not _dans(texte, p["commentaire"], 8):
            p.pop("commentaire")
        p["origine"] = COURRIER
        out[cle] = p
    n = sum(1 for p in out.values() if p.get("note"))
    return {"propositions": out, "trouvees": n,
            "message": (f"{n} note{'s' if n > 1 else ''} repérée{'s' if n > 1 else ''} dans le courrier, sans IA : "
                        "vérifiez chaque ligne avant de valider.") if n else
            "Adjugo n'a repéré aucune note écrite « x / y » dans ce courrier : saisissez-les, ou essayez la lecture "
            "avec l'IA.", "bulle": BULLE_LECTURE}


# ── Lecture du courrier AVEC l'IA (option) ───────────────────────────────────────────

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
_TEL = re.compile(r"(?<!\d)(?:\+33\s?|0)[1-9](?:[\s.\-]?\d{2}){4}(?!\d)")

_SYS_IA = (
    "Tu lis le courrier d'un acheteur public qui donne à une entreprise ses notes après un marché. Tu RECOPIES, tu "
    "n'inventes rien, tu ne calcules rien, tu ne convertis rien.\n"
    "Pour chaque critère de la liste (identifiant entre crochets) dont le courrier donne une note : recopie la note "
    "de l'entreprise (« note »), la note maximale (« note_max ») et la note de l'offre retenue si elle est donnée "
    "(« note_gagnant »), EXACTEMENT comme elles sont écrites (mêmes chiffres, même virgule) ; recopie mot pour mot la "
    "ligne du courrier où tu lis la note (« extrait ») et, si la note de l'offre retenue est sur une autre ligne, "
    "cette ligne (« extrait_gagnant »). Si le courrier donne l'appréciation de l'acheteur sur ce critère, recopie-la "
    "mot pour mot (« commentaire »). Une valeur qui n'est pas écrite reste vide. Un critère dont le courrier ne parle "
    "pas n'apparaît pas.\n"
    "Réponds UNIQUEMENT en JSON : {\"lignes\": [{\"id\": \"c1\", \"note\": \"\", \"note_max\": \"\", "
    "\"note_gagnant\": \"\", \"extrait\": \"\", \"extrait_gagnant\": \"\", \"commentaire\": \"\"}]}"
)


def masquer_coordonnees(texte: str) -> str:
    """Adresses électroniques et numéros de téléphone retirés avant l'IA (inutiles pour lire des notes)."""
    return _TEL.sub("[téléphone]", _EMAIL.sub("[courriel]", str(texte or "")))


def valider_ia(item, courrier_txt: str, masque: str, cles: set) -> Optional[dict]:
    """Une ligne proposée par l'IA, contrôlée SANS IA : l'extrait retrouvé dans le courrier, chaque nombre écrit
    dans son extrait (forme du courrier gardée), le commentaire mot pour mot ; sinon la valeur est écartée."""
    if not isinstance(item, dict):
        return None
    cle = str(item.get("id") or "").strip()[:20]
    if cle not in cles:
        return None

    def trouve(ex: str) -> str:
        ex = _flat(ex).strip(" «»\"")[:EXTRAIT_MAX]
        return ex if ex and (_dans(courrier_txt, ex) or _dans(masque, ex)) else ""

    out = {"cle": cle, "origine": IA}
    ex = trouve(item.get("extrait"))
    try:
        n, mx = nombre(item.get("note")), nombre(item.get("note_max"))
    except ValueError:
        n, mx = None, None
    if ex and n is not None:
        ln, lm = _retrouve_nombre(n, ex), (_retrouve_nombre(mx, ex) if mx is not None else None)
        if ln is not None and (mx is None or lm is not None) and (mx is None or (mx > 0 and n <= mx)):
            out.update(note=ln, extrait_note=ex)
            if lm is not None:
                out["note_max"] = lm
    try:
        g = nombre(item.get("note_gagnant"))
    except ValueError:
        g = None
    if g is not None:
        exg = trouve(item.get("extrait_gagnant")) or ex
        lg = _retrouve_nombre(g, exg) if exg else None
        if lg is not None:
            out.update(note_gagnant=lg, extrait_gagnant=exg)
    com = _flat(item.get("commentaire"))[:COMMENTAIRE_MAX]
    if com and len(com) >= 15 and (_dans(courrier_txt, com, 15) or _dans(masque, com, 15)):
        out["commentaire"] = com
    return out if any(k in out for k in ("note", "note_gagnant", "commentaire")) else None


def _appel_ia(criteres: list, masque: str, billing_id) -> dict:
    from app.services.llm import complete_ex, parse_json, tenant_scope
    liste = "\n".join(f"[{c['cle']}] " + ("— " if c.get("parent") else "") + c["critere"]
                      + (f" ({c['poids']})" if c.get("poids") else "") for c in criteres)
    user = f"CRITÈRES :\n{liste or '(aucun critère connu)'}\n\nCOURRIER DE L'ACHETEUR :\n{masque}"
    with tenant_scope(billing_id):
        content, _stop = complete_ex(_SYS_IA, user, max_tokens=1800, temperature=0.0, tache="questions",
                                     json_attendu=True)
    data = parse_json(content)
    items = data.get("lignes") if isinstance(data, dict) else None
    return {"lignes": items if isinstance(items, list) else []}


def lire_courrier_ia(db, user: User, project, texte: str, member_ids: list) -> dict:
    """« Lire avec l'IA » : propositions contrôlées, jamais enregistrées. Une question du jour, rendue si l'IA
    tombe ou si rien n'est retenu."""
    from app.core.quota import release_question, reserve_question
    from app.core.org import data_owner_id
    from app.services import pii
    from app.services.llm import LLMUnavailable, pii_scope
    texte = _texte_courrier(texte)
    crits = criteres_du_marche(project)["lignes"] + [
        {"cle": x["cle"], "critere": x["critere"], "parent": x.get("parent") or "", "poids": x.get("poids") or ""}
        for x in ((reponse(project) or {}).get("lignes") or []) if str(x.get("cle") or "").startswith("u")]
    if not crits:
        raise CarnetError(422, "aucun_critere", MSG_SANS_CRITERE)
    slot = reserve_question(user, db)          # 402 / 403 (démo) / 429 avant tout appel
    masque = masquer_coordonnees(texte)
    try:
        pz = pii.Pseudonymizer(pii.team_of_users(db, member_ids))
        with pii_scope(pz):
            res = _appel_ia(crits, masque, data_owner_id(user, db))
    except LLMUnavailable:
        release_question(db, slot)
        raise CarnetError(503, "ia_indisponible", MSG_IA_PANNE)
    except Exception as e:      # noqa: BLE001
        release_question(db, slot)
        logger.warning("carnet : lecture du courrier par l'IA en échec (marché %s) : %s", project.id, type(e).__name__)
        raise CarnetError(503, "ia_indisponible", MSG_IA_PANNE)
    cles = {c["cle"] for c in crits}
    props, refusees = {}, 0
    for item in res.get("lignes") or []:
        v = valider_ia(item, texte, masque, cles)
        if v is None:
            refusees += 1
            continue
        if v["cle"] not in props:
            props[v["cle"]] = v
    try:
        from app.services import llm_qualite as q
        q.noter_citations(len(props), refusees, tache="questions")
    except Exception:       # noqa: BLE001
        pass
    if not props:
        release_question(db, slot)
    n = sum(1 for p in props.values() if p.get("note"))
    return {"propositions": props, "trouvees": n, "refusees": refusees,
            "message": (f"L'IA a proposé {len(props)} ligne{'s' if len(props) > 1 else ''}, chaque nombre retrouvé "
                        "dans le courrier : vérifiez-les puis validez.") if props else
            "L'IA n'a rien proposé qui soit retrouvé tel quel dans le courrier : rien n'a été décompté.",
            "bulle": BULLE_IA}


def _texte_courrier(texte) -> str:
    t = str(texte or "").replace("\x00", "")
    t = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", t).strip()
    if len(t) < COURRIER_MIN:
        raise CarnetError(422, "courrier_trop_court", "Collez le courrier de l'acheteur (au moins quelques lignes).")
    if len(t) > COURRIER_MAX:
        raise CarnetError(422, "courrier_trop_long", f"Le courrier dépasse {COURRIER_MAX} caractères : collez seulement "
                                                     "la partie qui donne les notes.")
    return t


# ── Enregistrer les notes (validation par l'utilisateur) ─────────────────────────────

def _ligne_in(x: dict, i: int, connus: dict, courrier_txt: str) -> Optional[dict]:
    if not isinstance(x, dict):
        raise CarnetError(422, "ligne_invalide", "Ligne de notes illisible.")
    cle = re.sub(r"[^A-Za-z0-9._/\-]", "", str(x.get("cle") or ""))[:20] or f"u{i + 1}"
    base = connus.get(cle)
    critere = _flat(x.get("critere"))[:CRITERE_MAX] or (base or {}).get("critere", "")
    if not critere:
        raise CarnetError(422, "critere_vide", "Chaque ligne nomme son critère.")
    parent = (base or {}).get("parent", "") if base else re.sub(r"[^A-Za-z0-9._/\-]", "", str(x.get("parent") or ""))[:20]
    try:
        note, nmax, gagn = nombre(x.get("note")), nombre(x.get("note_max")), nombre(x.get("note_gagnant"))
    except ValueError:
        raise CarnetError(422, "nombre_illisible", f"« {critere[:60]} » : une note n'est pas un nombre (exemple : 12,5).")
    commentaire = _flat(x.get("commentaire"))[:COMMENTAIRE_MAX]
    if note is None and gagn is None and not commentaire:
        return None
    if (note is not None or gagn is not None) and not nmax:
        raise CarnetError(422, "note_max_manquante", f"« {critere[:60]} » : indiquez la note maximale.")
    if note is not None and note > nmax:
        raise CarnetError(422, "note_trop_haute", f"« {critere[:60]} » : la note dépasse la note maximale.")
    if gagn is not None and gagn > nmax:
        raise CarnetError(422, "note_trop_haute", f"« {critere[:60]} » : la note de l'offre retenue dépasse la note "
                                                  "maximale.")
    fam = str(x.get("famille") or "")
    prop = famille_proposee(critere, (connus.get(parent) or {}).get("critere", "") if parent else "")
    if fam not in FAMILLE_LIB:
        fam = prop
    origine = str(x.get("origine") or SAISIE)
    out = {"cle": cle, "critere": critere, "parent": parent, "poids": _flat(x.get("poids"))[:40]
           or (base or {}).get("poids", ""), "note": note, "note_max": nmax, "note_gagnant": gagn,
           "commentaire": commentaire, "famille": fam, "famille_proposee": prop, "origine": SAISIE}
    # « Lu dans le courrier » : seulement si la ligne citée est encore dans le courrier et y porte CHAQUE nombre
    # validé (forme écrite) ; sinon la valeur compte comme saisie par vous.
    if origine in (COURRIER, IA) and courrier_txt:
        ex = _flat(x.get("extrait_note"))[:EXTRAIT_MAX]
        exg = _flat(x.get("extrait_gagnant"))[:EXTRAIT_MAX]
        ok_n = note is None or (ex and _dans(courrier_txt, ex) and _retrouve_nombre(note, ex) is not None
                                and _retrouve_nombre(nmax, ex) is not None)
        ok_g = gagn is None or (bool(exg or ex) and _dans(courrier_txt, exg or ex)
                                and _retrouve_nombre(gagn, exg or ex) is not None)
        if ok_n and ok_g and (note is not None or gagn is not None):
            out["origine"] = origine
            if note is not None:
                out["extrait_note"] = ex
            if gagn is not None:
                out["extrait_gagnant"] = exg or ex
    if commentaire and courrier_txt and bool(x.get("commentaire_du_courrier")) and _dans(courrier_txt, commentaire, 8):
        out["commentaire_du_courrier"] = True
    return out


def enregistrer(db, project, user: User, lignes_in: list, rev=None, courrier_txt=None) -> dict:
    """Les notes VALIDÉES par l'utilisateur (le formulaire entier) ; la famille de chaque critère est confirmée
    par cet enregistrement."""
    if _statut(project) not in (PERDU, GAGNE):
        raise CarnetError(409, "marche_pas_termine", "Les notes se saisissent quand le marché est gagné ou perdu.")
    if not isinstance(lignes_in, list) or len(lignes_in) > LIGNES_MAX:
        raise CarnetError(422, "lignes_invalides", f"Au plus {LIGNES_MAX} lignes de notes.")
    project = _verrouiller(db, project)
    c = carnet(project)
    if rev is not None and int(rev) != int(c.get("rev") or 0):
        raise CarnetError(409, "carnet_modifie", "Les notes de ce marché ont changé depuis votre ouverture : rechargez "
                                                 "la page avant de valider.")
    txt = None
    if courrier_txt:
        txt = _texte_courrier(courrier_txt)
        c["courrier"] = {"texte": txt, "colle_le": _iso(_now()),
                         "empreinte": hashlib.sha256(txt.encode("utf-8")).hexdigest()}
    elif isinstance(c.get("courrier"), dict):
        txt = c["courrier"].get("texte") or None
    connus = {x["cle"]: x for x in criteres_du_marche(project)["lignes"]}
    for x in (reponse(project) or {}).get("lignes") or []:
        connus.setdefault(x.get("cle"), {"cle": x.get("cle"), "critere": x.get("critere", ""),
                                         "parent": x.get("parent", ""), "poids": x.get("poids", "")})
    out, vus = [], set()
    for i, x in enumerate(lignes_in):
        ln = _ligne_in(x, i, connus, txt or "")
        if ln is None:
            continue
        if ln["cle"] in vus:
            raise CarnetError(422, "ligne_en_double", f"« {ln['critere'][:60]} » apparaît deux fois.")
        vus.add(ln["cle"])
        out.append(ln)
    if not out:
        c.pop("reponse", None)
    else:
        c["reponse"] = {"lignes": out, "valide_le": _iso(_now()), "valide_par": user.id}
    _ecrire(db, project, c)
    db.commit()
    _journal(db, project, user, "carnet.notes", f"{len(out)} ligne(s) de notes validées")
    return c


def marquer_demande(db, project, user: User, envoyee: bool = True) -> dict:
    if _statut(project) != PERDU:
        raise CarnetError(409, "marche_pas_perdu", "La demande de notes se fait pour un marché perdu.")
    project = _verrouiller(db, project)
    c = carnet(project)
    if envoyee:
        c["demande"] = {"envoyee_le": _iso(_now()), "par": user.id}
    else:
        c.pop("demande", None)
    _ecrire(db, project, c)
    db.commit()
    _journal(db, project, user, "carnet.demande", "demande de notes marquée envoyée" if envoyee else "demande retirée")
    return c


def masquer_rappel(db, project, user: User) -> dict:
    project = _verrouiller(db, project)
    c = carnet(project)
    c["rappel_masque"] = {"le": _iso(_now()), "par": user.id}
    _ecrire(db, project, c)
    db.commit()
    return c


def _journal(db, project, user, action: str, detail: str) -> None:
    """Inscrit l'action au journal chaîné, APRÈS le commit de l'écriture (une panne du journal n'annule jamais
    les notes enregistrées)."""
    try:
        from app.services import audit
        from app.core.org import data_owner_id
        audit.record(db, action=action, owner_id=data_owner_id(user, db), project_id=project.id,
                     actor=f"user:{user.id}", actor_kind="owner", target_type="project", target_id=project.id,
                     detail=detail[:200])
    except Exception:       # noqa: BLE001 — le journal ne bloque jamais
        pass


# ── Vue du chef de file (ou d'une entreprise seule) ──────────────────────────────────

def _auteurs(db, project, owner_id: int, lignes=None) -> dict:
    """{cle de critère: {type, invite_id, nom, titre}} d'après le dossier de présentation : qui a rédigé la partie
    qui traite ce critère (ou sous-critère). `lignes` : les lignes de notes (critères ajoutés compris)."""
    from app.services import atelier as at
    from app.services import atelier_plan as ap
    d = at.get_dossier(db, project.id, owner_id)
    if d is None:
        return {}
    secs = [s for s in at.sections_actives(db, d) if not at.est_generee(s)]
    rangs = at._rangs(d, secs)
    noms = at._noms_auteurs(db, secs)
    crits = list(criteres_du_marche(project)["lignes"])
    vus = {c["cle"] for c in crits}
    for x in lignes or []:
        if x.get("cle") and x["cle"] not in vus:
            crits.append({"cle": x["cle"], "critere": x.get("critere", ""), "parent": x.get("parent") or ""})
            vus.add(x["cle"])
    par_cle = {}
    for c in crits:
        s = _section_du_critere(c, secs, ap)
        if s is None:
            continue
        titre = ((rangs.get(s.id, "") + " ") if rangs.get(s.id) else "") + (s.intitule or "")
        par_cle[c["cle"]] = {"type": s.author_kind or at.AUTEUR_ORG, "invite_id": s.author_invite_id,
                             "nom": noms.get(s.author_invite_id, "") if s.author_invite_id else "",
                             "titre": titre.strip(), "section_id": s.id}
    return par_cle


def _section_du_critere(c: dict, secs: list, ap):
    """La partie du plan qui traite un critère noté : par l'identifiant du critère de la grille (et, pour un
    sous-critère, l'intitulé de sa partie) ; sinon par le nom, tel quel ; sinon la seule partie qui en reprend la
    plupart des mots principaux. Aucune partie sûre : None (rien n'est attribué au hasard)."""
    cle, nom = c.get("cle") or "", _fold(c.get("critere"))
    par_id = [s for s in secs if s.critere_id and s.critere_id == (c.get("parent") or cle)]
    if par_id:
        if c.get("parent"):
            hit = next((s for s in par_id if ap.est_partie_de_sous_critere(s) and _fold(s.intitule) == nom), None)
            if hit is not None:
                return hit
        else:
            entiers = [s for s in par_id if not ap.est_partie_de_sous_critere(s)]
            if len(entiers) == 1:
                return entiers[0]
    for s in secs:
        if nom and nom in (_fold(s.intitule), _fold(s.critere)):
            return s
    mots = set(_stems(c.get("critere")))
    if not mots:
        return None
    scores = []
    for s in secs:
        commun = len(mots & set(_stems(f"{s.intitule} {s.critere or ''}")))
        if commun >= max(1, -(-len(mots) * 6 // 10)):
            scores.append((commun, s))
    scores.sort(key=lambda t: t[0], reverse=True)
    if scores and (len(scores) == 1 or scores[0][0] > scores[1][0]):
        return scores[0][1]
    return None


def _feuilles(lignes: list) -> list:
    """Les lignes qui comptent dans un total : un critère dont un sous-critère a une note compte par ses
    sous-critères ; sinon, lui-même."""
    notees = [x for x in lignes if x.get("note") is not None and x.get("note_max")]
    parents_detailles = {x.get("parent") for x in notees if x.get("parent")}
    return [x for x in notees if x["cle"] not in parents_detailles]


def _ligne_out(x: dict, auteur: Optional[dict] = None) -> dict:
    p = pct(x.get("note"), x.get("note_max"))
    pg = pct(x.get("note_gagnant"), x.get("note_max"))
    lib = {SAISIE: "saisie par vous", COURRIER: "lue dans le courrier, validée par vous",
           IA: "lue dans le courrier avec l'IA, validée par vous"}.get(x.get("origine"), "saisie par vous")
    out = {"cle": x.get("cle"), "critere": x.get("critere", ""), "parent": x.get("parent") or "",
           "poids": x.get("poids") or "", "note": ecrit(x.get("note")), "note_max": ecrit(x.get("note_max")),
           "note_gagnant": ecrit(x.get("note_gagnant")), "pct": p, "pct_gagnant": pg,
           "commentaire": x.get("commentaire") or "", "famille": x.get("famille") or "autre",
           "famille_libelle": FAMILLE_LIB.get(x.get("famille") or "autre", "Autre"),
           "origine": x.get("origine") or SAISIE, "origine_libelle": lib,
           "extrait_note": x.get("extrait_note") or "", "extrait_gagnant": x.get("extrait_gagnant") or "",
           "commentaire_du_courrier": bool(x.get("commentaire_du_courrier"))}
    if auteur:
        out["auteur"] = {"type": auteur.get("type"), "nom": auteur.get("nom") or "", "titre": auteur.get("titre") or ""}
    return out


def constat(lignes: list) -> Optional[dict]:
    """Le critère où ce marché a perdu le plus de points (en pourcentage de sa note maximale) : un constat. Le lien
    vers le réseau n'est proposé que hors prix (un partenaire ne couvre pas un prix)."""
    feuilles = [x for x in _feuilles(lignes)]
    if not feuilles:
        return None
    x = min(feuilles, key=lambda y: (y["note"] / y["note_max"], -y["note_max"]))
    p = pct(x["note"], x["note_max"])
    if p is None or p >= 100:
        return None
    fam = x.get("famille") or "autre"
    return {"cle": x["cle"], "critere": x["critere"], "pct": p,
            "message": f"C'est sur « {x['critere']} » que ce marché a perdu le plus de points : "
                       f"{ecrit(x['note'])} / {ecrit(x['note_max'])} ({p} %).",
            "partenaire": fam not in ("prix", "autre")}


def etat(db, project, user: User, member_ids: list) -> dict:
    from app.core.org import data_owner_id
    st = _statut(project)
    c = carnet(project)
    crits = criteres_du_marche(project)
    rep = reponse(project)
    try:
        auteurs = _auteurs(db, project, data_owner_id(user, db), (rep or {}).get("lignes"))
    except Exception as e:      # noqa: BLE001 — le carnet se lit sans le dossier de présentation
        logger.warning("carnet : auteurs des parties illisibles (marché %s) : %s", project.id, type(e).__name__)
        auteurs = {}
    grp = any((a.get("type") or "") != "organisation" for a in auteurs.values())
    sauvees = {x.get("cle"): x for x in (rep or {}).get("lignes") or []}
    form = []
    for x in crits["lignes"]:
        s = sauvees.get(x["cle"]) or {}
        form.append(dict(x, famille=s.get("famille") or x["famille_proposee"], note=ecrit(s.get("note")),
                         note_max=ecrit(s.get("note_max")) or ecrit(_max_du_poids(x["poids"])),
                         note_gagnant=ecrit(s.get("note_gagnant")), commentaire=s.get("commentaire") or "",
                         origine=s.get("origine") or SAISIE, extrait_note=s.get("extrait_note") or "",
                         extrait_gagnant=s.get("extrait_gagnant") or "",
                         commentaire_du_courrier=bool(s.get("commentaire_du_courrier")), ajoutee=False,
                         auteur=_auteur_out(auteurs.get(x["cle"]))))
    connues = {x["cle"] for x in crits["lignes"]}
    for cle, s in sauvees.items():
        if cle not in connues:
            form.append({"cle": cle, "critere": s.get("critere", ""), "parent": s.get("parent") or "",
                         "poids": s.get("poids") or "", "niveau": 2 if s.get("parent") else 1,
                         "famille_proposee": s.get("famille_proposee") or famille_proposee(s.get("critere", "")),
                         "famille": s.get("famille") or "autre", "note": ecrit(s.get("note")),
                         "note_max": ecrit(s.get("note_max")), "note_gagnant": ecrit(s.get("note_gagnant")),
                         "commentaire": s.get("commentaire") or "", "origine": s.get("origine") or SAISIE,
                         "extrait_note": s.get("extrait_note") or "", "extrait_gagnant": s.get("extrait_gagnant") or "",
                         "commentaire_du_courrier": bool(s.get("commentaire_du_courrier")), "ajoutee": True,
                         "auteur": _auteur_out(auteurs.get(cle))})
    notes = None
    if rep:
        lignes = rep["lignes"]
        notes = {"lignes": [_ligne_out(x, auteurs.get(x.get("cle"))) for x in lignes],
                 "valide_le": rep.get("valide_le"), "valide_le_jj": _jj(rep.get("valide_le")),
                 "constat": constat(lignes), "total": _total(lignes)}
    # La procédure ne sert qu'au courrier d'un marché perdu (lecture du règlement rangé : rien à lire sinon).
    proc = procedure_du_marche(project) if st == PERDU else {"code": INCONNUE, "phrase": "", "source": "", "message": ""}
    perdu_le = c.get("perdu_le")
    demande = c.get("demande") if isinstance(c.get("demande"), dict) else None
    return {
        "projet": {"id": project.id, "nom": project.name, "acheteur": _flat(_details(project).get("acheteur")
                                                                              or project.client)[:200]},
        "statut": st, "ouvert": st in (PERDU, GAGNE), "rev": int(c.get("rev") or 0), "bulle": BULLE,
        "demande": {"proposee": st == PERDU, "perdu_le": perdu_le, "perdu_le_jj": _jj(perdu_le),
                    "envoyee_le": (demande or {}).get("envoyee_le"), "envoyee_le_jj": _jj((demande or {}).get("envoyee_le")),
                    "procedure": proc, "procedures": list(PROCEDURES),
                    "rappel": {"du": rappel_du(project), "message": MSG_RAPPEL if rappel_du(project) else ""}},
        "criteres": {"source": crits["source"], "message": crits["message"], "lignes": form},
        "familles": [{"code": k, "libelle": v} for k, v in FAMILLES],
        "notes": notes, "courrier_colle": bool((c.get("courrier") or {}).get("texte")) if isinstance(c.get("courrier"), dict) else False,
        "ia": {"bulle": BULLE_IA}, "bulle_lecture": BULLE_LECTURE,
        "savoir_faire": _savoir_faire_out(db, project, c, user) if st == GAGNE else None,
        "groupement": {"actif": grp},
    }


def _auteur_out(a: Optional[dict]) -> Optional[dict]:
    if not a:
        return None
    return {"type": a.get("type") or "organisation", "nom": a.get("nom") or "", "titre": a.get("titre") or ""}


def _total(lignes: list) -> Optional[dict]:
    """La note d'ensemble, quand chaque critère (niveau 1) a sa note : la somme, telle quelle."""
    hauts = [x for x in lignes if not x.get("parent")]
    if not hauts or any(x.get("note") is None or not x.get("note_max") for x in hauts):
        return None
    n, m = sum(x["note"] for x in hauts), sum(x["note_max"] for x in hauts)
    return {"note": ecrit(round(n, 3)), "note_max": ecrit(round(m, 3)), "pct": pct(n, m)}


# ── « Où vous perdez des points » (tableau de bord) ──────────────────────────────────

def _projets_org(db, member_ids: list) -> list:
    """Les marchés GAGNÉS ou PERDUS de l'organisation (hors corbeille) qui ont un carnet : la colonne du carnet seule
    est lue pour choisir, puis les marchés retenus (500 au plus, les plus récents). Un marché remis « en cours » ne
    compte plus (ses notes restent, et reviennent s'il est de nouveau gagné ou perdu)."""
    from app.models import ProjectStatus
    ids = [pid for pid, c in db.query(Project.id, Project.carnet_notes)
           .filter(Project.user_id.in_(list(member_ids)), Project.deleted_at.is_(None),
                   Project.status.in_([ProjectStatus.gagne, ProjectStatus.perdu])).all()
           if isinstance(c, dict) and c]
    if not ids:
        return []
    return (db.query(Project).filter(Project.id.in_(ids)).order_by(Project.created_at.desc(), Project.id.desc())
            .limit(500).all())


def tableau(db, user: User, member_ids: list) -> dict:
    """Par famille de critère, la note en % de la note maximale ; une moyenne à partir de 3 marchés seulement.
    Les marchés de l'organisation seulement."""
    par_famille, marches, rappels = {}, 0, []
    for p in _projets_org(db, member_ids):
        if rappel_du(p):
            c = carnet(p)
            rappels.append({"project_id": p.id, "nom": p.name, "perdu_le": c.get("perdu_le"),
                            "perdu_le_jj": _jj(c.get("perdu_le")), "message": MSG_RAPPEL})
        rep = reponse(p)
        if not rep:
            continue
        feuilles = _feuilles(rep["lignes"])
        if not feuilles:
            continue
        marches += 1
        groupes = {}
        for x in feuilles:
            groupes.setdefault(x.get("famille") or "autre", []).append(x)
        for fam, xs in groupes.items():
            n, m = sum(x["note"] for x in xs), sum(x["note_max"] for x in xs)
            g = [x for x in xs if x.get("note_gagnant") is not None]
            pg = pct(sum(x["note_gagnant"] for x in g), sum(x["note_max"] for x in g)) if len(g) == len(xs) else None
            par_famille.setdefault(fam, []).append({"project_id": p.id, "nom": p.name, "pct": pct(n, m),
                                                    "pct_gagnant": pg})
    familles = []
    for code, lib in FAMILLES:
        vals = par_famille.get(code) or []
        if not vals:
            continue
        moy = int(round(sum(v["pct"] for v in vals) / len(vals))) if len(vals) >= MOYENNE_MIN else None
        gs = [v["pct_gagnant"] for v in vals if v["pct_gagnant"] is not None]
        moy_g = int(round(sum(gs) / len(gs))) if len(gs) >= MOYENNE_MIN else None
        familles.append({"code": code, "libelle": lib, "marches": len(vals), "moyenne": moy, "moyenne_gagnant": moy_g,
                         "valeurs": vals[:5] if moy is None else [],
                         "message": (f"{moy} % de la note maximale en moyenne, sur {len(vals)} marchés" if moy is not None
                                     else f"{len(vals)} marché{'s' if len(vals) > 1 else ''} : moyenne à partir de "
                                          f"{MOYENNE_MIN} marchés"),
                         "partenaire": code not in ("prix", "autre")})
    familles.sort(key=lambda f: (f["moyenne"] is None, f["moyenne"] if f["moyenne"] is not None else 0))
    avec_moy = [f for f in familles if f["moyenne"] is not None]
    pire = min(avec_moy, key=lambda f: f["moyenne"]) if avec_moy else None
    return {"marches": marches, "familles": familles, "rappels": rappels[:10], "bulle": BULLE_TABLEAU,
            "constat": ({"code": pire["code"], "partenaire": pire["partenaire"],
                         "message": f"Parmi les familles notées sur au moins {MOYENNE_MIN} marchés, c'est en "
                                    f"« {pire['libelle']} » que vous perdez le plus de points ({pire['moyenne']} % de la "
                                    "note maximale en moyenne)."} if pire and pire["moyenne"] < 100 else None),
            "message": "" if marches else "Saisissez les notes de vos marchés gagnés ou perdus pour voir où vous perdez "
                                          "des points."}


# ── « La dernière fois, l'acheteur a écrit » (atelier) ───────────────────────────────

def _cle_acheteur(project) -> str:
    return _fold(_details(project).get("acheteur") or getattr(project, "client", "") or "")


def derniere_fois(db, project, sections: list, member_ids: list) -> dict:
    """{section_id: {...}} : pour chaque partie du dossier, le dernier commentaire d'acheteur saisi sur un critère
    de la même famille, dans un AUTRE marché de l'organisation (le même acheteur d'abord, puis le plus récent).
    Rien n'est envoyé à l'IA."""
    from app.services import atelier as at
    commentaires = []
    for p in _projets_org(db, member_ids):
        if p.id == project.id:
            continue
        rep = reponse(p)
        if not rep:
            continue
        for x in rep["lignes"]:
            if x.get("commentaire"):
                commentaires.append((p, x, rep.get("valide_le") or ""))
    if not commentaires:
        return {}
    moi = _cle_acheteur(project)
    out = {}
    for s in sections:
        if at.est_generee(s) or s.retiree_at is not None:
            continue
        parent = ""
        for pa in s.parents or []:
            if isinstance(pa, dict) and pa.get("intitule"):
                parent = pa["intitule"]
        nom = s.intitule if (s.parents and s.critere_id) else (s.critere or s.intitule)
        fam = famille_proposee(nom or "", parent or s.critere or "")
        if fam in ("autre", "prix"):
            continue
        cands = [(p, x, le) for p, x, le in commentaires if (x.get("famille") or "autre") == fam]
        if not cands:
            continue
        mots = set(_stems(nom))
        # Le même acheteur d'abord ; puis le critère qui partage le plus de mots avec la partie ; puis le plus récent.
        cands.sort(key=lambda t: (bool(moi) and _cle_acheteur(t[0]) == moi, len(mots & set(_stems(t[1].get("critere")))),
                                  t[2]), reverse=True)
        p, x, le = cands[0]
        out[str(s.id)] = {"commentaire": x["commentaire"][:600], "critere": x.get("critere", ""),
                          "marche": p.name, "acheteur": _flat(_details(p).get("acheteur") or p.client)[:200],
                          "meme_acheteur": bool(moi) and _cle_acheteur(p) == moi, "le_jj": _jj(le),
                          "note": (f"{ecrit(x.get('note'))} / {ecrit(x.get('note_max'))}" if x.get("note") is not None
                                   and x.get("note_max") else ""),
                          "famille_libelle": FAMILLE_LIB.get(fam, ""), "project_id": p.id,
                          "bulle": BULLE_DERNIERE_FOIS}
    return out


# ── Marché gagné : « Ajouter ce dossier à mon savoir-faire » ─────────────────────────

def _textes_de_l_organisation(db, project, owner_id: int) -> list:
    """[(titre, texte)] des parties RÉDIGÉES par l'organisation (jamais celles d'un partenaire, jamais une partie
    tirée du groupement) : la version validée, sinon la version courante."""
    from app.services import atelier as at
    d = at.get_dossier(db, project.id, owner_id)
    if d is None:
        return []
    secs = at.sections_actives(db, d)
    rangs = at._rangs(d, secs)
    out = []
    for s in secs:
        if at.est_generee(s) or (s.author_kind or at.AUTEUR_ORG) != at.AUTEUR_ORG:
            continue
        vid = s.validated_version_id or s.current_version_id
        v = db.get(DossierSectionVersion, vid) if vid else None
        if v is None or v.section_id != s.id or not (v.texte or "").strip():
            continue
        titre = ((rangs.get(s.id, "") + " ") if rangs.get(s.id) else "") + (s.intitule or "")
        out.append((titre.strip(), v.texte))
    return out


def _sans_cv_ni_renvois(texte: str, refs_equipe: set) -> str:
    """Le texte d'une partie sans CV (lignes qui renvoient à une fiche « Équipe »), sans « [À compléter] » et sans
    renvois internes (comme l'export remis à l'acheteur)."""
    from app.services import memoire_export as me
    lignes = []
    for ln in str(texte or "").split("\n"):
        refs = set(re.findall(r"\[\s*(F\d{1,4})\s*\]", ln))
        if refs & refs_equipe:
            continue
        lignes.append(ln)
    t = me.clean_markdown("\n".join(lignes))
    t = me._TODO.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _refs_equipe(db, owner_id: int) -> set:
    try:
        from app.models import Preuve
        return {f"F{n}" for (n,) in db.query(Preuve.numero).filter(Preuve.owner_id == owner_id,
                                                                    Preuve.nature == "salarie").all()}
    except Exception:       # noqa: BLE001
        return set()


def _savoir_faire_out(db, project, c: dict, user: User) -> dict:
    from app.core.org import data_owner_id
    from app.models import KnowledgeDoc
    deja = c.get("savoir_faire") if isinstance(c.get("savoir_faire"), dict) else None
    doc = db.get(KnowledgeDoc, deja.get("doc_id")) if deja and deja.get("doc_id") else None
    try:
        n = len(_textes_de_l_organisation(db, project, data_owner_id(user, db)))
    except Exception:       # noqa: BLE001
        n = 0
    return {"parties": n, "bulle": BULLE_SAVOIR_FAIRE,
            "deja": ({"doc_id": doc.id, "nom": doc.name, "le_jj": _jj(deja.get("le"))} if doc is not None else None),
            "message": "" if n else "Aucune partie rédigée par vous dans le dossier de présentation de ce marché."}


def ajouter_au_savoir_faire(db, project, user: User) -> dict:
    """À l'initiative de l'utilisateur : le texte de SES parties du dossier gagné rejoint « Mon savoir-faire »
    (un document, découpé sans IA). Une seule fois par marché (tant que le document existe)."""
    from app.core.org import data_owner_id
    from app.models import KnowledgeDoc
    from app.services import rag
    if _statut(project) != GAGNE:
        raise CarnetError(409, "marche_pas_gagne", "Seul un marché gagné peut rejoindre « Mon savoir-faire ».")
    owner = data_owner_id(user, db)
    project = _verrouiller(db, project)
    c = carnet(project)
    deja = c.get("savoir_faire") if isinstance(c.get("savoir_faire"), dict) else None
    if deja and deja.get("doc_id") and db.get(KnowledgeDoc, deja["doc_id"]) is not None:
        raise CarnetError(409, "deja_ajoute", "Ce dossier est déjà dans « Mon savoir-faire ».")
    refs = _refs_equipe(db, owner)
    parts = []
    for titre, texte in _textes_de_l_organisation(db, project, owner):
        t = _sans_cv_ni_renvois(texte, refs)
        if t:
            parts.append(f"## {titre}\n\n{t}")
    if not parts:
        raise CarnetError(422, "aucun_texte", "Aucune partie rédigée par vous dans le dossier de présentation de ce "
                                              "marché : rien à ajouter.")
    det = _details(project)
    acheteur = _flat(det.get("acheteur") or project.client)[:120]
    nom = f"Dossier gagné — {project.name[:150]}" + (f" ({acheteur})" if acheteur else "")
    entete = f"Dossier de présentation du marché « {_flat(det.get('intitule_marche') or project.name)[:300]} »" \
             + (f", {acheteur}" if acheteur else "") + " : marché gagné."
    doc = rag.index_document(db, user.id, nom[:250], entete + "\n\n" + "\n\n".join(parts), kind="memoire")
    project = _verrouiller(db, project)
    c = carnet(project)
    c["savoir_faire"] = {"doc_id": doc.id, "le": _iso(_now()), "par": user.id}
    _ecrire(db, project, c)
    db.commit()
    _journal(db, project, user, "carnet.savoir_faire", "dossier gagné ajouté à « Mon savoir-faire »")
    return {"doc": {"id": doc.id, "name": doc.name, "n_chunks": doc.n_chunks}, "parties": len(parts),
            "message": f"{len(parts)} partie{'s' if len(parts) > 1 else ''} ajoutée{'s' if len(parts) > 1 else ''} à "
                       "« Mon savoir-faire »."}


# ── Groupement : la vue du partenaire ────────────────────────────────────────────────

def vue_partenaire(db, acces) -> Optional[dict]:
    """Les notes COMMUNES du marché, lues par un partenaire (toutes les lignes), avec SES parties mises en avant.
    Jamais le courrier collé ni ses extraits, jamais la demande du chef de file."""
    project = acces.project
    rep = reponse(project)
    if not rep or _statut(project) not in (PERDU, GAGNE):
        return None
    try:
        auteurs = _auteurs(db, project, acces.dossier.owner_id, rep["lignes"])
    except Exception:       # noqa: BLE001
        auteurs = {}
    lignes, vos = [], []
    for x in rep["lignes"]:
        a = auteurs.get(x.get("cle")) or {}
        vous = a.get("type") == "invitation" and a.get("invite_id") == acces.invite_id
        ln = _ligne_out(x)
        for k in ("extrait_note", "extrait_gagnant", "origine", "origine_libelle", "commentaire_du_courrier"):
            ln.pop(k, None)
        ln["vous"] = vous
        ln["partie"] = a.get("titre") or ""
        lignes.append(ln)
        if vous:
            vos.append(ln)
    return {"statut": _statut(project), "lignes": lignes, "vos_parties": vos, "total": _total(rep["lignes"]),
            "message": ("Les notes données par l'acheteur pour l'offre du groupement, saisies par le chef de file. Vos "
                        "parties sont signalées.")}


# ── Courriel de rappel (cron de la veille) ───────────────────────────────────────────

def _a_des_alertes(db, uid: int) -> bool:
    from app.models import SavedSearch
    return db.query(SavedSearch.id).filter(SavedSearch.user_id == uid, SavedSearch.active.is_(True),
                                           SavedSearch.frequency != "manuelle").first() is not None


def envoyer_rappels(db, now: Optional[datetime] = None) -> dict:
    """Un courriel « Demandez vos notes », une seule fois par marché, à l'utilisateur qui l'a passé à « Perdu »,
    seulement s'il a des alertes actives. Jamais à l'acheteur, jamais au compte de démonstration."""
    from app.core.config import get_settings
    from app.models import ProjectStatus
    from app.services.alerts import _demo_user_ids
    from app.services.email import send_email
    now = now or _now()
    envoyes, examines = 0, 0
    demo = _demo_user_ids(db)
    base = (get_settings().APP_BASE_URL or "https://adjugo.pro").rstrip("/")
    ids = [pid for pid, c in db.query(Project.id, Project.carnet_notes)
           .filter(Project.status == ProjectStatus.perdu, Project.deleted_at.is_(None)).all()
           if isinstance(c, dict) and c.get("perdu_le") and not c.get("rappel_courriel")]
    for p in (db.query(Project).filter(Project.id.in_(ids)).all() if ids else []):
        c = carnet(p) if isinstance(p.carnet_notes, dict) else None
        if not c or not rappel_du(p, now) or c.get("rappel_courriel"):
            continue
        d = _date(c.get("perdu_le"))
        if d is None or now > d + timedelta(days=COURRIEL_FIN_JOURS):
            continue
        examines += 1
        uid = c.get("perdu_par") or p.user_id
        u = db.get(User, uid) if uid else None
        if u is None or not u.email or u.id in demo or p.user_id in demo or not getattr(u, "is_active", True):
            continue
        if not _a_des_alertes(db, u.id):
            continue
        acheteur = _flat(_details(p).get("acheteur") or p.client)[:120]
        texte = ("Bonjour,\n\n"
                 f"Le marché « {_flat(p.name)[:200]} »" + (f" ({acheteur})" if acheteur else "")
                 + f" est passé à « Perdu » le {_jj(c.get('perdu_le'))}. Vous pouvez demander à l'acheteur les motifs "
                 "du rejet et vos notes, critère par critère : Adjugo vous prépare le courrier, c'est vous qui "
                 "l'envoyez.\n\n" + MSG_DELAI[INCONNUE].split(" Choisissez")[0] + "\n\n"
                 f"Ouvrir Adjugo : {base}/app\n\n"
                 "Vous recevez ce message parce que vous avez des alertes actives dans Adjugo.\n\n— Adjugo")
        try:
            ok = send_email(u.email, f"Adjugo — demandez vos notes : {_flat(p.name)[:70]}", texte)
        except Exception:       # noqa: BLE001
            ok = False
        if ok:
            p2 = _verrouiller(db, p)
            c2 = carnet(p2)
            c2["rappel_courriel"] = {"le": _iso(now), "a": u.id}
            _ecrire(db, p2, c2)
            db.commit()
            envoyes += 1
    return {"rappels_notes_examines": examines, "rappels_notes_envoyes": envoyes}


# ── RGPD ─────────────────────────────────────────────────────────────────────────────

def exporter(db, user_ids: list) -> list:
    """Les carnets de notes des marchés du compte (portabilité) : tout leur contenu, courrier collé compris."""
    rows = db.query(Project).filter(Project.user_id.in_(list(user_ids))).all() if user_ids else []
    return [{"appel_offres_id": p.id, "marche": p.name, "carnet": copy.deepcopy(p.carnet_notes)}
            for p in rows if isinstance(p.carnet_notes, dict) and p.carnet_notes]
