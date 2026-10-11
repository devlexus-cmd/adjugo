"""
Adjugo — Convention de groupement (co-traitance v2, vague 2 « Monter le groupement »).

Un modèle PARAMÉTRÉ et DÉTERMINISTE (0 LLM) : mêmes entrées → même texte → même empreinte
sha256. Le mandataire choisit la forme (« chacun responsable de sa part » = conjoint ;
« tous responsables de tout » = solidaire), l'habilitation (cases) et quelques paramètres à
valeurs par défaut explicites ; Adjugo cite ce que le règlement impose (citation vérifiée
contre le texte du dossier, sinon « non trouvé dans le DCE ») et AVERTIT sans bloquer.

Doctrine de visibilité :
- l'annexe de répartition liste nom, lot, rôle et PRIX DE VENTE du lot (prix_lot_ht) de chaque
  membre actif + le total — JAMAIS detail_chiffre, coûts, marges ;
- en brouillon, un membre ne voit QUE son propre prix (ni ceux des autres, ni le total) ;
- une fois générée, la convention complète (annexe incluse) est la même pour tous : UN seul
  content_hash ;
- le LLM ne reçoit jamais la convention (aucun appel ici, et build_dossier ne la passe qu'au ZIP).

« Figer l'offre » est fusionné avec la génération : groupement_plan.offre (vague 1) reçoit le
total + les parts + convention_id. Toute part / tout prix / toute composition modifiée ensuite
rend la convention caduque (status 'perimee') : explicitement via le défigement de la vague 1
(_unfreeze_offer_if_needed → perimer) et, par sécurité, en recalculant l'empreinte à la lecture.

Ce n'est PAS un conseil juridique : l'avertissement « modèle à faire relire par un conseil »
figure dans le texte, le PDF, l'email et chaque réponse d'API.
"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("adjugo")

# ── Libellés (français simple, jamais « consortium ») ────────────────────────────────

AVERTISSEMENT = ("Modèle à faire relire par un conseil (avocat, juriste, CCI) : "
                 "ce n'est pas un conseil juridique.")
NATURE_ACCORD = ("Votre accord est enregistré par Adjugo (date, empreinte du texte, niveau "
                 "d'identité) : ce n'est pas une signature électronique qualifiée. Les "
                 "formulaires officiels (DC1, ATTRI1) restent à signer au moment du dépôt.")

FORMES = {
    "conjoint": {
        "terme": "Groupement conjoint",
        "phrase": "Chacun est responsable de sa part",
        "explication": ("Chaque entreprise s'engage sur la part qui lui revient dans la répartition, "
                        "et n'en répond devant l'acheteur que pour cette part."),
    },
    "solidaire": {
        "terme": "Groupement solidaire",
        "phrase": "Tous sont responsables de tout",
        "explication": ("Chaque entreprise est engagée devant l'acheteur pour la totalité du marché : "
                        "si l'une fait défaut, les autres doivent assurer sa part."),
    },
}
MANDATAIRE_SOLIDAIRE = {
    "terme": "Mandataire solidaire",
    "phrase": "Le chef de file répond aussi de la part de chaque partenaire",
    "explication": ("Option du groupement conjoint : devant l'acheteur, le chef de file "
                    "garantit la bonne exécution de la part des autres membres."),
}

FORME_IMPOSEE_LABELS = {
    "non_verifie": "Non vérifié : le dossier du marché (DCE) n'a pas encore été analysé.",
    "non_specifie": "Non trouvé dans le DCE (le dossier du marché).",
    "libre": "Le règlement laisse le choix de la forme du groupement.",
    "conjoint": "Le règlement impose un groupement conjoint (chacun responsable de sa part).",
    "solidaire": "Le règlement impose un groupement solidaire (tous responsables de tout).",
}
FORMES_IMPOSEES = tuple(FORME_IMPOSEE_LABELS)

# Habilitation du mandataire (cases). Repris dans l'ATTRI1 (rubrique C2). « representer » est
# la mission même du mandataire : obligatoire (case cochée, non décochable).
HABILITATION = [
    {"key": "representer", "defaut": True, "obligatoire": True,
     "libelle": "Représenter le groupement auprès de l'acheteur et coordonner le travail de tous",
     "terme": "Représenter les membres vis-à-vis de l'acheteur et coordonner l'ensemble des prestations",
     "texte": "représenter le groupement auprès de l'acheteur et coordonner le travail de tous les membres"},
    {"key": "signer_candidature_offre", "defaut": True, "obligatoire": False,
     "libelle": "Signer et déposer la candidature et l'offre au nom de tous",
     "terme": "Signer l'acte d'engagement et les pièces de la candidature et de l'offre au nom et pour le compte des membres",
     "texte": "signer et déposer la candidature et l'offre (acte d'engagement) au nom de tous"},
    {"key": "negocier", "defaut": True, "obligatoire": False,
     "libelle": "Négocier avec l'acheteur au nom de tous (sans changer la part ou le prix d'un membre sans son accord écrit)",
     "terme": "Mener la négociation au nom des membres, dans la limite de l'offre commune",
     "texte": ("négocier avec l'acheteur au nom de tous, sans pouvoir changer la part ou le prix "
               "d'un membre sans son accord écrit")},
    {"key": "signer_modifications", "defaut": False, "obligatoire": False,
     "libelle": "Signer les avenants (modifications du marché) au nom de tous",
     "terme": "Signer les modifications ultérieures du marché au nom et pour le compte des membres",
     "texte": ("signer les avenants (modifications du marché) au nom de tous, après accord écrit "
               "de chaque membre concerné")},
]
HABILITATION_KEYS = [h["key"] for h in HABILITATION]

# Paramètres : valeurs par défaut RAISONNABLES et EXPLICITES (à valider par le fondateur).
PARAMS = [
    {"key": "decision", "type": "choix", "defaut": "unanimite",
     "libelle": "Comment le groupement prend ses décisions communes",
     "choix": [{"value": "unanimite", "libelle": "À l'unanimité : tous les membres doivent être d'accord"},
               {"value": "majorite", "libelle": "À la majorité des membres (une voix par membre)"}]},
    {"key": "delai_reponse_jours", "type": "entier", "defaut": 5, "min": 1, "max": 30, "unite": "jours",
     "libelle": "Délai pour répondre au chef de file (et pour régler une défaillance)"},
    {"key": "defaillance", "type": "choix", "defaut": "remplacement",
     "libelle": "Si un membre ne fait pas sa part",
     "choix": [{"value": "remplacement",
                "libelle": "Les membres proposent ensemble à l'acheteur une entreprise pour reprendre sa part"},
               {"value": "reprise_par_les_autres",
                "libelle": "Les autres membres reprennent sa part, à proportion de leurs propres parts"}]},
    {"key": "sortie_preavis_jours", "type": "entier", "defaut": 15, "min": 0, "max": 90, "unite": "jours",
     "libelle": "Préavis pour quitter le groupement avant la date limite de remise des offres"},
    {"key": "confidentialite_annees", "type": "entier", "defaut": 5, "min": 0, "max": 10, "unite": "ans",
     "libelle": "Durée de confidentialité après la fin du groupement"},
    {"key": "pi", "type": "choix", "defaut": "chacun_garde",
     "libelle": "Propriété de ce qui est créé (propriété intellectuelle)",
     "choix": [{"value": "chacun_garde",
                "libelle": "Chacun reste propriétaire de ce qu'il apporte et de ce qu'il crée"},
               {"value": "copropriete",
                "libelle": "Ce qui est créé ensemble appartient à tous, à proportion des parts"}]},
    {"key": "penalites", "type": "choix", "defaut": "responsable_paie",
     "libelle": "Qui paie les pénalités de l'acheteur",
     "choix": [{"value": "responsable_paie",
                "libelle": "Le membre responsable (à défaut, à proportion des parts)"},
               {"value": "prorata",
                "libelle": "Tous, à proportion des parts (sauf faute prouvée d'un membre)"}]},
    {"key": "assurances_travaux", "type": "oui_non", "defaut": None,
     "libelle": "Assurance décennale exigée de chaque membre (marché de travaux)",
     "aide": "Par défaut : oui si le marché ressemble à des travaux, non sinon."},
    {"key": "litiges", "type": "choix", "defaut": "amiable_puis_tribunal",
     "libelle": "En cas de désaccord entre membres",
     "choix": [{"value": "amiable_puis_tribunal",
                "libelle": "Solution amiable pendant 30 jours, puis le tribunal du siège du chef de file"},
               {"value": "mediation_puis_tribunal",
                "libelle": "Médiation d'abord (60 jours), puis le tribunal du siège du chef de file"}]},
]
PARAM_KEYS = [p["key"] for p in PARAMS]
_PARAM = {p["key"]: p for p in PARAMS}

STATUS_LABELS = {
    "aucune": "Pas encore préparée",
    "draft": "Brouillon",
    "a_signer": "Générée — accords en attente",
    "signee": "Validée par tous les membres",
    "perimee": "Plus à jour — à régénérer",
}
SIGNATURE_LABELS = {
    "pending": "En attente",
    "signed": "Accord enregistré",
    "hors_ligne": "Accord recueilli hors ligne",
    "perimee": "Caduc : la convention doit être régénérée",
}
IDENTITY_LABELS = {
    "compte_verifie": "accord enregistré depuis son compte Adjugo (adresse email vérifiée)",
    "email_verifie": "accord enregistré via le lien, adresse email vérifiée par code",
    "lien_seul": "accord enregistré via le lien (identité non vérifiée)",
    "": "accord recueilli hors ligne, déclaré par le chef de file",
}
ACTIVE = ("a_signer", "signee")


# ── Valeurs dynamiques : texte sûr (Markdown échappé, une seule ligne) ────────────────

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MD_SPECIAL = re.compile(r"([\\*_`#\[\]])")


def _clean(v, max_len: int = 255) -> str:
    """Valeur saisie → une seule ligne, sans caractère de contrôle, bornée."""
    s = _CTRL.sub(" ", str(v if v is not None else ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def md(v, max_len: int = 255) -> str:
    """Valeur dynamique insérée dans le texte : nettoyée puis caractères Markdown échappés
    (« * », « _ », « ` »… restent du TEXTE ; rendu PDF avec markdown_to_pdf(md_escapes=True))."""
    return _MD_SPECIAL.sub(r"\\\1", _clean(v, max_len))


def unescape_md(s: str) -> str:
    """Texte affichable tel quel (aperçu sans rendu Markdown)."""
    return re.sub(r"\\([\\*_`#\[\]])", r"\1", s or "")


def eur(v) -> str:
    """Montant déterministe au format français : « 125 000 € » ou « 125 000,50 € »."""
    try:
        f = round(float(v), 2)
    except (TypeError, ValueError):
        return "—"
    ent = int(abs(f))
    cents = int(round((abs(f) - ent) * 100))
    if cents == 100:
        ent, cents = ent + 1, 0
    txt = f"{ent:,}".replace(",", " ")
    if cents:
        txt += f",{cents:02d}"
    return ("-" if f < 0 else "") + txt + " €"


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── Paramètres : défauts, validation ──────────────────────────────────────────────────

def is_travaux(project) -> bool:
    try:
        from app.routers.checklist import _is_travaux
        return bool(_is_travaux(project))
    except Exception:
        return False


def default_habilitation() -> dict:
    return {h["key"]: bool(h["defaut"]) for h in HABILITATION}


def default_params(project) -> dict:
    out = {p["key"]: p["defaut"] for p in PARAMS}
    out["assurances_travaux"] = is_travaux(project)
    return out


def mandataire_defaults(project) -> dict:
    est = project.estimate if isinstance(getattr(project, "estimate", None), dict) else {}
    part = est.get("total_ht")
    try:
        part = float(part) if part is not None else None
    except (TypeError, ValueError):
        part = None
    return {"part_mandataire_ht": part, "lot_mandataire": "", "mandataire_qualite": ""}


def merged_habilitation(conv) -> dict:
    h = default_habilitation()
    src = conv.habilitation if conv is not None and isinstance(conv.habilitation, dict) else {}
    for k in HABILITATION_KEYS:
        if k in src:
            h[k] = bool(src[k])
    h["representer"] = True        # mission même du mandataire : jamais décochée
    return h


def merged_params(conv, project) -> dict:
    p = default_params(project)
    p.update(mandataire_defaults(project))
    p["membres_hors_ligne"] = []
    p["masquer_repartition"] = False
    src = conv.params if conv is not None and isinstance(conv.params, dict) else {}
    for k, v in src.items():
        if k in p:
            p[k] = v
    return p


class ParamError(ValueError):
    pass


def validate_params(raw: dict) -> dict:
    """Valide les 9 paramètres juridiques (+ part/lot/qualité du mandataire). Lève ParamError."""
    out = {}
    for k, v in (raw or {}).items():
        spec = _PARAM.get(k)
        if spec is None:
            if k in ("part_mandataire_ht",):
                if v is None:
                    out[k] = None
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    raise ParamError("Votre part (€ HT) doit être un montant.")
                if f != f or f < 0 or f > 1e10:
                    raise ParamError("Votre part doit être comprise entre 0 et 10 milliards d'euros HT.")
                out[k] = round(f, 2)
            elif k == "lot_mandataire":
                out[k] = _clean(v, 255)
            elif k == "mandataire_qualite":
                out[k] = _clean(v, 120)
            else:
                raise ParamError(f"Paramètre inconnu : {k}")
            continue
        t = spec["type"]
        if t == "choix":
            allowed = [c["value"] for c in spec["choix"]]
            if v not in allowed:
                raise ParamError(f"Valeur invalide pour « {spec['libelle']} ».")
            out[k] = v
        elif t == "entier":
            if isinstance(v, bool):
                raise ParamError(f"« {spec['libelle']} » doit être un nombre entier.")
            try:
                iv = int(v)
            except (TypeError, ValueError):
                raise ParamError(f"« {spec['libelle']} » doit être un nombre entier.")
            if iv != v and not (isinstance(v, str) and str(iv) == v.strip()):
                if not (isinstance(v, float) and float(iv) == v):
                    raise ParamError(f"« {spec['libelle']} » doit être un nombre entier.")
            if iv < spec["min"] or iv > spec["max"]:
                raise ParamError(f"« {spec['libelle']} » doit être entre {spec['min']} et {spec['max']} {spec['unite']}.")
            out[k] = iv
        elif t == "oui_non":
            if not isinstance(v, bool):
                raise ParamError(f"« {spec['libelle']} » : répondez oui ou non.")
            out[k] = v
    return out


def validate_habilitation(raw: dict) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        if k not in HABILITATION_KEYS:
            raise ParamError(f"Pouvoir inconnu : {k}")
        if not isinstance(v, bool):
            raise ParamError("Chaque pouvoir se coche (oui) ou se décoche (non).")
        out[k] = v
    out["representer"] = True
    return out


# ── Ce que le règlement impose (citation vérifiée, jamais inventée) ───────────────────

_CLAUSE_SPLIT = re.compile(r"(?<=[.;:!?])\s+|\n+")
_CLAUSE_HAS_GROUP = re.compile(r"groupement", re.IGNORECASE)
_CLAUSE_HAS_FORM = re.compile(r"conjoint|solidaire|mandataire|forme", re.IGNORECASE)


def _details(project) -> dict:
    a = project.ai_analysis if isinstance(getattr(project, "ai_analysis", None), dict) else {}
    d = a.get("details")
    return d if isinstance(d, dict) else {}


def clauses_groupement(text: str, limit: int = 3) -> list:
    """Phrases LITTÉRALES du dossier qui parlent de la forme du groupement (0 LLM). Chaque
    phrase repasse par citation_guard : sous-chaîne garantie du texte intégral."""
    from app.services.analysis import citation_guard
    out, seen = [], set()
    for raw in _CLAUSE_SPLIT.split(text or ""):
        s = re.sub(r"\s+", " ", raw).strip()
        if not (20 <= len(s) <= 400):
            continue
        if not (_CLAUSE_HAS_GROUP.search(s) and _CLAUSE_HAS_FORM.search(s)):
            continue
        g = citation_guard(text, s)
        if g and g.lower() not in seen:
            seen.add(g.lower())
            out.append(g)
    # Les phrases qui nomment conjoint/solidaire d'abord.
    out.sort(key=lambda s: 0 if re.search(r"conjoint|solidaire", s, re.IGNORECASE) else 1)
    return out[:limit]


def forme_imposee(project, text_integral: Optional[str] = None) -> dict:
    """Ce que le règlement impose sur la forme du groupement.

    Source : la classification de l'analyse du dossier (forme_groupement.imposee) ACCOMPAGNÉE
    de son extrait, qui doit être une citation vérifiée (citation_guard contre le texte
    INTÉGRAL). Sans citation vérifiable → « non trouvé dans le DCE ». Si le texte intégral est
    fourni (relecture explicite), l'extrait y est re-vérifié et, à défaut de classification,
    les phrases littérales qui parlent de la forme sont proposées « à lire » (sans
    interprétation : forme_imposee reste 'non_verifie').
    Renvoie {forme_imposee, extrait, libelle, clauses:[…], source}."""
    a = project.ai_analysis if isinstance(getattr(project, "ai_analysis", None), dict) else {}
    details = _details(project)
    fg = details.get("forme_groupement")
    fg = fg if isinstance(fg, dict) else {}
    imposee = str(fg.get("imposee") or "").strip().lower()
    extrait = str(fg.get("extrait") or "").strip()

    if text_integral:
        from app.services.analysis import citation_guard
        verified = citation_guard(text_integral, extrait) if extrait else ""
        if imposee in ("libre", "conjoint", "solidaire") and verified:
            return _fi(imposee, verified, "dossier_relu")
        clauses = clauses_groupement(text_integral)
        if clauses:
            return _fi("non_verifie", clauses[0], "dossier_relu", clauses,
                       libelle=("Le dossier du marché parle de la forme du groupement : lisez la phrase "
                                "citée (Adjugo ne l'interprète pas à votre place)."))
        return _fi("non_specifie", "", "dossier_relu")

    analysed = bool(details) and a.get("dce_available") is not False
    if not analysed:
        return _fi("non_verifie", "", "aucune")
    if not fg:
        # Analyse antérieure à la vague 1 (pas d'extraction de la forme) : rien à citer.
        return _fi("non_verifie", "", "analyse_ancienne",
                   libelle=("Non vérifié : ce marché a été analysé avant l'extraction de la forme du "
                            "groupement. Utilisez « Relire le dossier du marché »."))
    verifiees = details.get("exigences_verifiees") if isinstance(details.get("exigences_verifiees"), dict) else {}
    if imposee in ("libre", "conjoint", "solidaire") and extrait and verifiees.get("forme_groupement"):
        # citation_guard a été appliqué contre le texte INTÉGRAL lors de l'analyse.
        return _fi(imposee, extrait, "analyse")
    return _fi("non_specifie", "", "analyse")


def _fi(code, extrait, source, clauses=None, libelle=None) -> dict:
    return {"forme_imposee": code, "extrait": extrait or "", "clauses": list(clauses or ([extrait] if extrait else [])),
            "libelle": libelle or FORME_IMPOSEE_LABELS.get(code, ""), "source": source}


def dce_text(db, project, owner_ids: list) -> Optional[str]:
    """Texte intégral du dossier du marché archivé (dossier « DCE »), extraction BORNÉE
    (mêmes plafonds que /reanalyze). None si aucun dossier importé ou illisible."""
    try:
        from app.models import Document
        from app.services.analysis import extract_dce_text
        from app.services.storage import get_storage
        doc = (db.query(Document)
               .filter(Document.user_id.in_(owner_ids), Document.project_id == project.id,
                       Document.folder == "DCE", Document.deleted_at.is_(None))
               .order_by(Document.created_at.desc()).first())
        if not doc or not doc.file_key:
            return None
        content = get_storage().load(doc.file_key)
        return extract_dce_text(doc.name, content, max_chars=120000) or None
    except Exception as e:
        logger.info("relecture du dossier du marché impossible (projet %s) : %s", project.id, e)
        return None


def has_dce_document(db, project, owner_ids: list) -> bool:
    try:
        from app.models import Document
        return db.query(Document.id).filter(
            Document.user_id.in_(owner_ids), Document.project_id == project.id,
            Document.folder == "DCE", Document.deleted_at.is_(None)).first() is not None
    except Exception:
        return False


# ── Membres de la convention (snapshot) ───────────────────────────────────────────────

def _addr(address, postal_code, city) -> str:
    return _clean(" ".join(x for x in (_clean(address), _clean(postal_code), _clean(city)) if x), 300)


def offline_candidates(db, project) -> list:
    """Partenaires RATTACHÉS au marché sans invitation (candidats « hors ligne ») : le
    mandataire peut les inclure à la convention (accord recueilli hors ligne)."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    owner = db.query(_user_model()).filter(_user_model().id == project.user_id).first()
    from app.core.org import member_ids
    ids = member_ids(owner, db) if owner else [project.user_id]
    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id).order_by(
        ProjectCotraitant.id.asc()).all()
    cts = {c.id: c for c in db.query(Cotraitant).filter(
        Cotraitant.id.in_([lk.cotraitant_id for lk in links] or [0]), Cotraitant.user_id.in_(ids)).all()}
    out = []
    for lk in links:
        ct = cts.get(lk.cotraitant_id)
        if not ct or getattr(lk, "invite_id", None):
            continue
        if str(lk.role or "").strip().lower().replace("-", "_") == "sous_traitant":
            continue
        out.append({"link_id": lk.id, "company": ct.name or "Partenaire", "siret": ct.siret or "",
                    "lot": lk.lot or "", "representant_legal": ct.representant_legal or "",
                    "address": ct.address or "", "postal_code": ct.postal_code or "",
                    "city": ct.city or "", "email": ct.email or "", "phone": ct.phone or "",
                    "forme_juridique": ct.forme_juridique or ""})
    return out


def _user_model():
    from app.models import User
    return User


def _is_sous_traitant(role) -> bool:
    return str(role or "").strip().lower().replace("-", "_") == "sous_traitant"


def collect_members(db, project, conv, company, include_incomplete: bool = False) -> dict:
    """Membres de la convention à partir des FAITS actuels (jamais du client) :
    mandataire (profil entreprise + paramètres) → invitations ACTIVES de rôle co-traitant
    (part SOUMISE, prix de lot) → partenaires hors ligne choisis par le mandataire.
    `include_incomplete` (aperçu de brouillon seulement) : un membre dont la part n'est pas
    encore soumise apparaît quand même, sans prix (il reste listé dans les manques).
    Renvoie {members:[…], manques:[…], sous_traitants:[…]}. Ne lève jamais."""
    from app.services.groupement_members import active_invites, visible_contributions
    params = merged_params(conv, project)
    manques, members, sous_traitants = [], [], []

    comp = company
    lead_name = (comp.name if comp is not None and comp.name else "") or "Le mandataire"
    if comp is None or not (comp.name or "").strip():
        manques.append("Profil entreprise à compléter : nom de votre entreprise (chef de file)")
    part = params.get("part_mandataire_ht")
    if part is None:
        manques.append("Votre part (chef de file) : montant € HT à indiquer")
    members.append({
        "kind": "mandataire", "invite_id": None, "link_id": None,
        "company": lead_name, "siret": (comp.siret if comp is not None else "") or "",
        "address": (comp.address if comp is not None else "") or "",
        "postal_code": (comp.postal_code if comp is not None else "") or "",
        "city": (comp.city if comp is not None else "") or "",
        "forme_juridique": (comp.forme_juridique if comp is not None else "") or "",
        "email": (comp.email if comp is not None else "") or "",
        "phone": (comp.phone if comp is not None else "") or "",
        "representant_legal": (comp.representant_legal if comp is not None else "") or "",
        "signataire_qualite": params.get("mandataire_qualite") or "",
        "role": "mandataire", "lot": params.get("lot_mandataire") or "",
        "prix_lot_ht": (round(float(part), 2) if part is not None else None),
    })

    invites = active_invites(db, project.id)
    # Part d'une invitation du réseau sans réponse : absente (nom de l'invitation, aucun SIRET,
    # adresse ni représentant saisis dans le brouillon) — le chef de file ne la voit pas.
    contribs = visible_contributions(db, project.id, invites)
    n_partners = 0
    for inv in invites:
        c = contribs.get(inv.id)
        name = (c.company_name if c and c.company_name else inv.company_name) or "Partenaire"
        if _is_sous_traitant(inv.role):
            sous_traitants.append(name)
            continue
        n_partners += 1
        complete = True
        if not c or c.status != "submitted":
            manques.append(f"{name} n'a pas encore soumis sa part")
            complete = False
        elif c.prix_lot_ht is None:
            manques.append(f"{name} : prix de lot manquant")
            complete = False
        if not complete and not include_incomplete:
            continue
        contact = c.contact if c is not None and isinstance(c.contact, dict) else {}
        caps = c.capacites if c is not None and isinstance(c.capacites, dict) else {}
        members.append({
            "kind": "invite", "invite_id": inv.id, "link_id": None,
            "company": name, "siret": (c.siret if c else "") or "", "address": (c.address if c else "") or "",
            "postal_code": (c.postal_code if c else "") or "", "city": (c.city if c else "") or "",
            "forme_juridique": (c.forme_juridique if c else "") or "",
            "email": contact.get("email", "") or "", "phone": contact.get("telephone", "") or "",
            "representant_legal": (c.representant_legal if c else "") or "",
            "signataire_qualite": (c.signataire_qualite if c else "") or "",
            "role": "cotraitant", "lot": (c.lot if c else "") or "",
            "prix_lot_ht": (round(float(c.prix_lot_ht), 2) if complete else None),
            "ca_n1": caps.get("ca_n1"), "effectif": caps.get("effectif"),
        })

    cands = {o["link_id"]: o for o in offline_candidates(db, project)}
    for entry in (params.get("membres_hors_ligne") or []):
        if not isinstance(entry, dict):
            continue
        n_partners += 1
        o = cands.get(entry.get("link_id"))
        if not o:
            manques.append("Un partenaire hors ligne choisi n'est plus rattaché à ce marché : retirez-le")
            continue
        prix = entry.get("prix_lot_ht")
        if prix is None:
            manques.append(f"{o['company']} (hors ligne) : prix de lot manquant")
            if not include_incomplete:
                continue
        members.append({
            "kind": "hors_ligne", "invite_id": None, "link_id": o["link_id"],
            "company": o["company"], "siret": o["siret"], "address": o["address"],
            "postal_code": o["postal_code"], "city": o["city"], "forme_juridique": o["forme_juridique"],
            "email": o["email"], "phone": o["phone"],
            "representant_legal": entry.get("representant_legal") or o["representant_legal"],
            "signataire_qualite": entry.get("signataire_qualite") or "",
            "role": "cotraitant", "lot": entry.get("lot") or o["lot"],
            "prix_lot_ht": (round(float(prix), 2) if prix is not None else None),
        })

    if n_partners == 0:
        manques.append("Aucun partenaire : invitez au moins un partenaire (ou ajoutez un partenaire hors ligne)")
    return {"members": members, "manques": manques, "sous_traitants": sous_traitants}


def total_of(members: list) -> Optional[float]:
    try:
        return round(sum(float(m["prix_lot_ht"]) for m in members), 2)
    except (TypeError, ValueError, KeyError):
        return None


# ── Le texte (modèle paramétré, déterministe) ─────────────────────────────────────────

def _member_line(m: dict) -> str:
    who = f"**{md(m.get('company'))}**"
    siret = md(m.get("siret"), 20) or "à préciser"
    adr = md(_addr(m.get("address"), m.get("postal_code"), m.get("city"))) or "adresse à préciser"
    rep = md(m.get("representant_legal")) or "représentant à préciser"
    qual = md(m.get("signataire_qualite"), 120)
    role = ("**mandataire (chef de file)**" if m.get("role") == "mandataire"
            else "**co-traitant (partenaire)**")
    return f"- {who}, SIRET {siret}, {adr}, représentée par {rep}{', ' + qual if qual else ''} — {role} ;"


def _annex_line(m: dict, show_price: bool) -> str:
    role = "mandataire (chef de file)" if m.get("role") == "mandataire" else "co-traitant (partenaire)"
    lot = md(m.get("lot")) or "part à préciser"
    if not show_price:
        prix = "affiché à la génération de la convention"
    elif m.get("prix_lot_ht") is None:
        prix = "pas encore renseigné"
    else:
        prix = eur(m.get("prix_lot_ht")) + " HT"
    return f"- **{md(m.get('company'))}** — {role} — part : {lot} — prix de vente : {prix}"


def render(ctx: dict, mask: str = "none", viewer_invite_id: Optional[int] = None) -> str:
    """Texte de la convention. FONCTION PURE : mêmes entrées → même texte.

    ctx = {version, marche:{objet, acheteur, reference}, forme, mandataire_solidaire,
           habilitation:{…}, params:{…}, members:[…], total_ht, brouillon:bool}
    mask : 'none' (texte complet, celui qu'on fige et qu'on hache) · 'all' (aucun prix,
           aucun total) · 'member' (seul le prix de `viewer_invite_id`, pas de total)."""
    v = ctx.get("version") or 0
    marche = ctx.get("marche") or {}
    forme = ctx.get("forme") or ""
    ms = bool(ctx.get("mandataire_solidaire")) and forme == "conjoint"
    hab = ctx.get("habilitation") or default_habilitation()
    p = ctx.get("params") or {}
    members = ctx.get("members") or []
    lead = next((m for m in members if m.get("role") == "mandataire"), {"company": "Le mandataire"})
    lead_name = md(lead.get("company")) or "Le mandataire"
    delai = int(p.get("delai_reponse_jours") or 5)

    L = ["# Convention de groupement momentané d'entreprises", ""]
    if ctx.get("brouillon"):
        L += ["*Brouillon : ce texte n'est pas encore figé. Il ne vaut pas convention.*", ""]
    else:
        L += [f"Version n°{v} — texte établi par Adjugo à partir des choix du chef de file.", ""]
    L += [f"**Avertissement : {AVERTISSEMENT}**", ""]

    L += ["## Le marché",
          f"- Objet : {md(marche.get('objet'), 500) or 'à préciser'}",
          f"- Acheteur : {md(marche.get('acheteur')) or 'à préciser'}",
          f"- Référence du dossier sur Adjugo : {md(marche.get('reference'), 40)}", ""]

    L += ["## Article 1 — Les membres du groupement",
          "Les entreprises suivantes s'associent pour répondre ensemble à ce marché et, s'il leur est "
          "attribué, pour l'exécuter :"]
    L += [_member_line(m) for m in members]
    L += [""]

    L += ["## Article 2 — Forme du groupement"]
    if forme == "solidaire":
        L += ["Le groupement est **solidaire** : tous sont responsables de tout. Chaque membre est engagé, "
              "devant l'acheteur, pour la totalité du marché. Entre eux, les membres se répartissent les "
              "prestations selon l'annexe de répartition ; celui qui paie à la place d'un autre peut se "
              "faire rembourser par lui."]
    elif forme == "conjoint":
        L += ["Le groupement est **conjoint** : chacun est responsable de sa part. Chaque membre s'engage à "
              "exécuter les prestations qui lui sont attribuées dans l'annexe de répartition et n'en "
              "répond, devant l'acheteur, que pour sa part."]
        if ms:
            L += ["Le mandataire est **solidaire** : le chef de file répond aussi, devant l'acheteur, de la "
                  "bonne exécution de la part de chaque membre. Il peut se faire rembourser par le membre "
                  "concerné tout ce qu'il aurait payé à sa place."]
        else:
            L += ["Le mandataire n'est pas solidaire des autres membres : il ne répond devant l'acheteur "
                  "que de sa propre part et de sa mission de chef de file."]
    else:
        L += ["*Forme à choisir : groupement conjoint (chacun responsable de sa part) ou groupement "
              "solidaire (tous responsables de tout).*"]
    L += [""]

    L += ["## Article 3 — Le mandataire (chef de file)",
          f"**{lead_name}** est désigné mandataire du groupement. Les membres lui donnent pouvoir, en "
          "leur nom et pour leur compte, pour :"]
    L += [f"- {h['texte']} ;" for h in HABILITATION if hab.get(h["key"])]
    L += ["Le mandataire n'a pas d'autre pouvoir que ceux listés ci-dessus. Il informe sans délai les "
          "membres de toute demande de l'acheteur qui les concerne."]
    if not hab.get("signer_candidature_offre"):
        L += ["Chaque membre signe lui-même la candidature et l'offre (acte d'engagement)."]
    L += [""]

    L += ["## Article 4 — Répartition des prestations et des paiements",
          "Chaque membre exécute la part qui lui est attribuée dans l'annexe de répartition, au prix de "
          "vente indiqué. Le total de l'offre commune est la somme de ces prix.",
          "Chaque membre facture sa part et est payé pour celle-ci, sur le compte indiqué dans l'acte "
          "d'engagement.",
          "Les coûts, marges et méthodes de calcul de chaque membre restent confidentiels : ils ne "
          "figurent pas dans cette convention et ne sont communiqués à personne, pas même au mandataire.",
          ""]

    L += ["## Article 5 — Décisions communes"]
    if p.get("decision") == "majorite":
        L += ["Les décisions qui engagent tout le groupement (offre commune, planning commun, réponse à "
              "l'acheteur qui concerne plusieurs membres) sont prises à la majorité des membres, chaque "
              "membre disposant d'une voix."]
    else:
        L += ["Les décisions qui engagent tout le groupement (offre commune, planning commun, réponse à "
              "l'acheteur qui concerne plusieurs membres) sont prises à l'unanimité des membres."]
    L += ["Aucune décision ne peut modifier la part ou le prix d'un membre sans son accord écrit. "
          f"Chaque membre répond aux demandes du mandataire dans un délai de {delai} jours ; le silence "
          "ne vaut pas accord.", ""]

    L += ["## Article 6 — Si un membre ne fait pas sa part (défaillance)",
          f"Le mandataire met le membre concerné en demeure par écrit. Si rien n'est réglé dans un délai "
          f"de {delai} jours :"]
    if p.get("defaillance") == "reprise_par_les_autres":
        L += ["- les autres membres reprennent ensemble cette part, à proportion de leurs propres parts, "
              "sous réserve de l'accord de l'acheteur."]
    else:
        L += ["- les membres proposent ensemble à l'acheteur une entreprise pour reprendre cette part, sous "
              "réserve de son accord."]
    L += ["Les surcoûts causés par la défaillance restent à la charge du membre défaillant.", ""]

    sortie = int(p.get("sortie_preavis_jours") or 0)
    L += ["## Article 7 — Quitter le groupement"]
    if sortie:
        L += [f"Avant la remise de l'offre, un membre peut quitter le groupement en prévenant les autres par "
              f"écrit au moins {sortie} jours avant la date limite de remise des offres."]
    else:
        L += ["Avant la remise de l'offre, un membre peut quitter le groupement en prévenant les autres par "
              "écrit avant la date limite de remise des offres."]
    L += ["Après la remise de l'offre, et pendant toute l'exécution du marché, un membre ne peut quitter "
          "le groupement qu'avec l'accord des autres membres et de l'acheteur.", ""]

    conf = int(p.get("confidentialite_annees") or 0)
    L += ["## Article 8 — Confidentialité",
          "Chaque membre garde confidentielles les informations des autres membres (prix, méthodes, "
          "savoir-faire, documents) pendant toute la durée du groupement"
          + (f" et {conf} an{'s' if conf > 1 else ''} après sa fin." if conf else "."), ""]

    L += ["## Article 9 — Propriété intellectuelle"]
    if p.get("pi") == "copropriete":
        L += ["Ce que les membres créent ensemble pour ce marché leur appartient en commun, à proportion de "
              "leurs parts. Chaque membre reste propriétaire de ce qu'il apporte et de ce qu'il crée seul."]
    else:
        L += ["Chaque membre reste propriétaire de ses savoir-faire, méthodes et documents, qu'ils existent "
              "déjà ou qu'il les crée pour ce marché. Il autorise les autres membres à les utiliser "
              "uniquement pour exécuter ce marché."]
    L += ["Les droits cédés à l'acheteur restent ceux prévus par les documents du marché.", ""]

    L += ["## Article 10 — Pénalités"]
    if p.get("penalites") == "prorata":
        L += ["Les pénalités appliquées par l'acheteur sont réparties entre les membres à proportion de leurs "
              "parts, sauf faute prouvée d'un membre, qui les paie alors seul."]
    else:
        L += ["Les pénalités appliquées par l'acheteur sont payées par le membre qui en est responsable. Si "
              "aucun responsable ne peut être identifié, elles sont réparties à proportion des parts de chacun."]
    L += [""]

    L += ["## Article 11 — Assurances",
          "Chaque membre est assuré en responsabilité civile professionnelle pour sa part pendant toute la "
          "durée du marché et en fournit l'attestation au mandataire."]
    if p.get("assurances_travaux"):
        L += ["Pour les travaux, chaque membre est aussi couvert par une assurance de responsabilité "
              "décennale pour les ouvrages qu'il réalise."]
    L += [""]

    L += ["## Article 12 — Désaccord entre membres"]
    if p.get("litiges") == "mediation_puis_tribunal":
        L += ["En cas de désaccord, les membres font d'abord appel à un médiateur (par exemple le "
              "Médiateur des entreprises). À défaut d'accord dans les 60 jours, le litige est porté devant "
              "le tribunal compétent du lieu du siège du mandataire."]
    else:
        L += ["En cas de désaccord, les membres cherchent d'abord une solution amiable pendant 30 jours. À "
              "défaut, le litige est porté devant le tribunal compétent du lieu du siège du mandataire."]
    L += [""]

    L += ["## Article 13 — Durée",
          "La convention s'applique dès que tous les membres ont enregistré leur accord. Si le marché "
          "n'est pas attribué au groupement, elle prend fin à la réception de la décision de rejet. S'il "
          "est attribué, elle dure jusqu'à la fin de l'exécution du marché et des garanties.", ""]

    L += ["## Article 14 — Cohérence avec les formulaires officiels",
          "La forme du groupement, le mandataire et la répartition décrits ici sont repris à l'identique "
          "dans la lettre de candidature (DC1) et l'acte d'engagement (ATTRI1) du groupement.", ""]

    L += ["## Annexe — Répartition des prestations et des prix"]
    for m in members:
        if mask == "none":
            show = True
        elif mask == "member":
            show = (viewer_invite_id is not None and m.get("invite_id") == viewer_invite_id)
        else:
            show = False
        L.append(_annex_line(m, show))
    if mask == "none" and ctx.get("total_ht") is not None:
        L += ["", f"**Total de l'offre commune : {eur(ctx.get('total_ht'))} HT**"]
    else:
        L += ["", "**Total de l'offre commune : calculé et révélé à tous à la génération de la convention**"]
    L += ["Les prix sont les prix de vente de chaque part. Ils ne comprennent ni le détail des coûts ni les "
          "marges, qui restent confidentiels.", ""]

    L += ["## Accord des membres",
          "Chaque membre donne son accord sur ce texte depuis son espace Adjugo. Cet accord est enregistré "
          "avec la date et l'empreinte du texte : ce n'est pas une signature électronique qualifiée. Les "
          "formulaires officiels (DC1, ATTRI1) restent à signer au moment du dépôt."]
    return "\n".join(L) + "\n"


def build_context(db, project, conv, company, version: Optional[int] = None, brouillon: bool = False) -> dict:
    """Contexte complet (faits actuels) + manques/avertissements pour la génération. En
    brouillon (aperçu), les membres dont la part est incomplète figurent sans prix."""
    col = collect_members(db, project, conv, company, include_incomplete=brouillon)
    members = col["members"]
    complete = not col["manques"]
    params = merged_params(conv, project)
    legal = {k: params.get(k) for k in PARAM_KEYS}
    ctx = {
        "version": (conv.version or 0) + 1 if version is None and conv is not None else (version or 1),
        "marche": {"objet": project.name or "", "acheteur": project.client or "",
                   "reference": f"AO-{project.id:04d}"},
        "forme": (conv.forme if conv is not None else "") or "",
        "mandataire_solidaire": bool(conv.mandataire_solidaire) if conv is not None else False,
        "habilitation": merged_habilitation(conv),
        "params": legal,
        "members": members,
        "total_ht": total_of(members) if complete else None,
        "brouillon": brouillon,
    }
    return {"ctx": ctx, "manques": col["manques"], "sous_traitants": col["sous_traitants"]}


# ── Avertissements (avertir, pas bloquer) ─────────────────────────────────────────────

def warnings_for(conv, project, ctx: dict, fi: dict, sous_traitants: list, db=None) -> list:
    out = []
    forme = ctx.get("forme") or ""
    imp = fi.get("forme_imposee")
    if forme and imp in ("conjoint", "solidaire") and forme != imp:
        out.append(f"Le règlement impose un groupement {imp} (voir la citation) : votre choix « {forme} » "
                   "ne correspond pas. Vérifiez avant de générer.")
    ex = (fi.get("extrait") or "").lower()
    if forme == "conjoint" and not ctx.get("mandataire_solidaire") and "mandataire" in ex and "solidaire" in ex:
        out.append("La phrase citée du règlement demande un chef de file solidaire (« mandataire solidaire ») : "
                   "vérifiez s'il faut cocher l'option « Le chef de file répond aussi de la part de chaque "
                   "partenaire ».")
    members = ctx.get("members") or []
    lots = {}
    for m in members:
        if not str(m.get("lot") or "").strip():
            out.append(f"Part de {m.get('company')} non précisée : indiquez le lot ou les prestations.")
        else:
            lots.setdefault(_clean(m["lot"]).lower(), []).append(m.get("company"))
        if not str(m.get("representant_legal") or "").strip():
            out.append(f"Représentant légal (signataire) manquant pour {m.get('company')}.")
    for k, names in lots.items():
        if len(names) > 1:
            out.append(f"La même part est attribuée à plusieurs membres ({', '.join(names[:3])}) : "
                       "en groupement conjoint, une part n'a qu'un seul titulaire.")
    sirets = {}
    for m in members:
        s = str(m.get("siret") or "").strip()
        if s:
            sirets.setdefault(s, []).append(m.get("company"))
    for s, names in sirets.items():
        if len(names) > 1:
            out.append(f"Le même SIRET apparaît deux fois ({', '.join(names)}) : un partenaire est peut-être "
                       "à la fois invité et ajouté hors ligne.")
    for name in sous_traitants or []:
        out.append(f"{name} est sous-traitant : il ne fait pas partie du groupement, ne signe pas la "
                   "convention et son prix n'est pas ajouté au total (déclaration de sous-traitance DC4).")
    est = project.estimate if isinstance(project.estimate, dict) else {}
    params = merged_params(conv, project)
    if est.get("total_ht") is not None and params.get("part_mandataire_ht") is not None:
        try:
            if abs(float(est["total_ht"]) - float(params["part_mandataire_ht"])) < 0.005:
                out.append("Votre part reprend votre estimation : vérifiez qu'elle ne couvre que VOTRE part "
                           "(sinon les parts des partenaires seraient comptées deux fois).")
        except (TypeError, ValueError):
            pass
    if len(members) == 2:
        out.append("À 2 membres, le total de l'offre révèle à chacun la part de l'autre.")
    if db is not None:
        chosen = {e.get("link_id") for e in (params.get("membres_hors_ligne") or []) if isinstance(e, dict)}
        for o in offline_candidates(db, project):
            if o["link_id"] not in chosen:
                out.append(f"{o['company']} est rattaché à ce marché mais n'est ni invité ni ajouté hors ligne : "
                           "il ne figurera pas dans le groupement.")
    return out


# ── Lecture / écriture de la convention ───────────────────────────────────────────────

def get_convention(db, project_id: int):
    from app.models import GroupementConvention
    return db.query(GroupementConvention).filter(GroupementConvention.project_id == project_id).first()


def signatures_of(db, conv) -> list:
    from app.models import GroupementSignature
    if conv is None:
        return []
    return db.query(GroupementSignature).filter(GroupementSignature.convention_id == conv.id).order_by(
        GroupementSignature.id.asc()).all()


def _company_for(db, project):
    from app.models import Company
    from app.routers.invites import tenant_owner_id
    return db.query(Company).filter(Company.user_id == tenant_owner_id(project, db)).first()


def current_hash(db, project, conv) -> Optional[str]:
    """Empreinte du texte qu'on générerait AUJOURD'HUI avec la même version et les mêmes
    paramètres. Différente de content_hash ⇒ un fait imprimé a changé (part, prix,
    composition, identité…) ⇒ convention caduque. None si une part n'est plus complète."""
    built = build_context(db, project, conv, _company_for(db, project), version=conv.version or 0)
    if built["manques"]:
        return None
    return sha256(render(built["ctx"]))


def is_stale(db, project, conv) -> bool:
    if conv is None or conv.status not in ACTIVE:
        return False
    plan = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
    offre = plan.get("offre") if isinstance(plan.get("offre"), dict) else {}
    if not offre.get("frozen_at") or offre.get("convention_id") != conv.id:
        return True
    try:
        return current_hash(db, project, conv) != conv.content_hash
    except Exception as e:
        logger.warning("contrôle de fraîcheur de la convention en échec (projet %s) : %s", project.id, e)
        return False


def concerns_convention(db, project, invite_id=None) -> bool:
    """Faux seulement si une convention est GÉNÉRÉE et que l'événement vise un SOUS-TRAITANT
    qui n'en est pas signataire : il n'est pas membre du groupement, son prix n'est pas dans
    l'offre commune figée par la convention → rien à défiger, rien de caduc."""
    if not invite_id:
        return True
    try:
        from app.models import GroupementSignature, ProjectInvite
        conv = get_convention(db, project.id)
        if conv is None or conv.status not in ACTIVE:
            return True
        inv = db.query(ProjectInvite).filter(ProjectInvite.id == invite_id).first()
        if inv is None or not _is_sous_traitant(inv.role):
            return True
        signer = db.query(GroupementSignature.id).filter(GroupementSignature.convention_id == conv.id,
                                                          GroupementSignature.invite_id == invite_id).first()
        return signer is not None
    except Exception:
        return True


def perimer(db, project, reason: str, *, actor: str = "system", actor_kind: str = "system",
            ip: str = "", invite_id=None) -> bool:
    """Rend la convention CADUQUE (a_signer / signee → perimee ; accords → perimee) et le
    journalise (convention.perimee, visible des membres). Idempotent. Ne lève jamais."""
    try:
        conv = get_convention(db, project.id)
        if conv is None or conv.status not in ACTIVE:
            return False
        conv.status = "perimee"
        for s in signatures_of(db, conv):
            s.status = "perimee"
        db.commit()
        from app.routers.invites import tenant_owner_id
        from app.services import audit
        audit.record(db, action="convention.perimee", owner_id=tenant_owner_id(project, db),
                     project_id=project.id, actor=actor or "system", actor_kind=actor_kind or "system",
                     target_type="convention", target_id=conv.id, invite_id=invite_id,
                     detail=_clean(reason, 255), ip=ip or "")
        return True
    except Exception as e:
        logger.warning("péremption de la convention en échec (projet %s) : %s", getattr(project, "id", "?"), e)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def refresh(db, project, conv) -> None:
    """Filet de sécurité à la lecture : si le texte figé ne correspond plus aux faits, la
    convention passe en 'perimee' (avec trace)."""
    if conv is not None and conv.status in ACTIVE and is_stale(db, project, conv):
        perimer(db, project, "les parts, les prix ou la composition ont changé depuis la génération")
        db.refresh(conv)


def all_agreed(sigs: list) -> bool:
    return bool(sigs) and all(s.status in ("signed", "hors_ligne") for s in sigs)


def sync_signatures(db, conv, members: list) -> None:
    """Une ligne d'accord par membre (mandataire, invitation, hors ligne), remise à 'pending'
    sur le NOUVEAU texte ; les lignes des anciens membres sont supprimées."""
    from app.models import GroupementSignature
    existing = signatures_of(db, conv)

    def key_of(s):
        if s.invite_id:
            return ("invite", s.invite_id)
        if s.cotraitant_link_id:
            return ("link", s.cotraitant_link_id)
        return ("mandataire", None)

    by_key = {}
    for s in existing:
        if key_of(s) in by_key:          # doublon (création concurrente) : une seule ligne par membre
            db.delete(s)
        else:
            by_key[key_of(s)] = s
    keep = set()
    for m in members:
        k = (("invite", m["invite_id"]) if m["kind"] == "invite" else
             ("link", m["link_id"]) if m["kind"] == "hors_ligne" else ("mandataire", None))
        keep.add(k)
        s = by_key.get(k)
        if s is None:
            s = GroupementSignature(convention_id=conv.id, project_id=conv.project_id, owner_id=conv.owner_id,
                                    invite_id=m.get("invite_id") if m["kind"] == "invite" else None,
                                    cotraitant_link_id=m.get("link_id") if m["kind"] == "hors_ligne" else None)
            db.add(s)
        s.company_name = _clean(m.get("company"), 255)
        s.siret = _clean(m.get("siret"), 20)
        s.signataire_nom = _clean(m.get("representant_legal"), 255)
        s.signataire_qualite = _clean(m.get("signataire_qualite"), 120)
        s.content_hash = conv.content_hash or ""
        s.status = "pending"
        s.identity_level = ""
        s.verified_email = ""
        s.signed_at = None
        s.ip = ""
        s.user_id = None
    for k, s in by_key.items():
        if k not in keep:
            db.delete(s)
    db.flush()


def member_kind(sig) -> str:
    if sig.invite_id:
        return "partenaire"
    if sig.cotraitant_link_id:
        return "hors_ligne"
    return "mandataire"


def serialize_signature(sig, for_owner: bool) -> dict:
    out = {
        "membre": member_kind(sig),
        "company": sig.company_name or "",
        "status": sig.status,
        "status_label": SIGNATURE_LABELS.get(sig.status, sig.status),
        "signed_at": sig.signed_at.isoformat() if sig.signed_at else None,
        "identity_level": sig.identity_level if sig.status in ("signed", "hors_ligne") else None,
        "identity_label": (IDENTITY_LABELS.get(sig.identity_level or "", "")
                           if sig.status in ("signed", "hors_ligne") else None),
        "signataire_nom": (sig.signataire_nom or "") if sig.status in ("signed", "hors_ligne") else "",
        "signataire_qualite": (sig.signataire_qualite or "") if sig.status in ("signed", "hors_ligne") else "",
    }
    if for_owner:
        out["invite_id"] = sig.invite_id
        out["link_id"] = sig.cotraitant_link_id
    return out


# ── PDF ───────────────────────────────────────────────────────────────────────────────

def _fmt_dt(dt) -> str:
    """Date et heure d'un accord, à l'heure de Paris (format partagé avec le journal du membre).
    Réservé à accords_md, HORS empreinte : jamais dans render() ni dans content_hash."""
    from app.services.format import date_heure_fr
    return date_heure_fr(dt)


def accords_md(conv, sigs: list) -> str:
    """Section « Accords enregistrés » ajoutée au PDF (HORS empreinte : elle évolue à chaque
    accord, le texte approuvé, lui, ne change pas). Heures à l'heure de Paris : affichage seul,
    les dates en base (frozen_at, signed_at) restent en UTC."""
    L = ["", "## Accords enregistrés",
         f"Empreinte du texte approuvé (SHA-256) : {conv.content_hash or '—'}",
         f"Version n°{conv.version or 0}, figée le {_fmt_dt(conv.frozen_at)}.", ""]
    for s in sigs:
        who = md(s.company_name) or "Membre"
        role = {"mandataire": "chef de file", "partenaire": "partenaire", "hors_ligne": "partenaire hors ligne"}[member_kind(s)]
        if s.status in ("signed", "hors_ligne"):
            nom = md(s.signataire_nom) or "signataire non précisé"
            qual = md(s.signataire_qualite, 120)
            L.append(f"- {who} ({role}) — {nom}{', ' + qual if qual else ''} — "
                     f"{IDENTITY_LABELS.get(s.identity_level or '', '')} le {_fmt_dt(s.signed_at)}")
        elif s.status == "perimee":
            L.append(f"- {who} ({role}) — " + ("accord donné sur cette version, devenue caduque"
                                              if s.signed_at else "accord non donné, version devenue caduque"))
        else:
            L.append(f"- {who} ({role}) — accord en attente")
    L += ["", NATURE_ACCORD, "", f"*{AVERTISSEMENT}*"]
    return "\n".join(L) + "\n"


def pdf_bytes(content_md: str, title: str = "Convention de groupement") -> bytes:
    from app.services.md_pdf import markdown_to_pdf
    return markdown_to_pdf(content_md, title, md_escapes=True)


def convention_pdf(conv, sigs: list) -> bytes:
    head = ""
    if conv.status == "perimee":
        head = ("**PLUS À JOUR : une part, un prix ou la composition a changé depuis cette version. "
                "Elle doit être régénérée et validée à nouveau par chaque membre.**\n\n")
    return pdf_bytes(head + (conv.content_md or "") + accords_md(conv, sigs))


# ── Données pour les formulaires officiels (DC1, DC2, ATTRI1) ─────────────────────────

def cerfa_groupement(db, project) -> Optional[dict]:
    """Si une convention est GÉNÉRÉE et à jour (a_signer ou signee) : les membres, la forme,
    l'habilitation et les prix QUI Y FIGURENT, pour que DC1/DC2/ATTRI1 disent exactement la
    même chose. None sinon (les formulaires gardent alors leur source habituelle)."""
    try:
        conv = get_convention(db, project.id)
        if conv is None or conv.status not in ACTIVE:
            return None
        refresh(db, project, conv)
        if conv.status not in ACTIVE:
            return None
        plan = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
        parts = (plan.get("offre") or {}).get("parts") or []
        members = [p for p in parts if isinstance(p, dict)]
        lead = next((m for m in members if m.get("role") == "mandataire"), None)
        others = [m for m in members if m.get("role") != "mandataire"]
        sigs = signatures_of(db, conv)
        return {
            "forme": conv.forme, "mandataire_solidaire": bool(conv.mandataire_solidaire),
            "habilitation": merged_habilitation(conv), "total_ht": conv.total_offre_ht,
            "convention_status": conv.status, "convention_version": conv.version,
            "mandataire": lead or {},
            "cotraitants": [{
                "name": m.get("company", ""), "siret": m.get("siret", ""),
                "address": m.get("address", ""), "postal_code": m.get("postal_code", ""),
                "city": m.get("city", ""), "email": m.get("email", ""), "phone": m.get("phone", ""),
                "forme_juridique": m.get("forme_juridique", ""),
                "representant_legal": m.get("representant_legal", ""),
                "signataire_qualite": m.get("signataire_qualite", ""),
                "role": "cotraitant", "lot": m.get("lot", ""), "prix_lot_ht": m.get("prix_lot_ht"),
                "ca_n1": m.get("ca_n1") or 0, "effectif": m.get("effectif") or 0,
            } for m in others],
            "signataires": [{"company": s.company_name, "nom": s.signataire_nom,
                             "qualite": s.signataire_qualite, "membre": member_kind(s),
                             "status": s.status} for s in sigs],
        }
    except Exception as e:
        logger.warning("données de convention pour les formulaires indisponibles (projet %s) : %s",
                       getattr(project, "id", "?"), e)
        return None


def apply_to_cerfa(db, project, company_data: dict, project_data: dict) -> Optional[dict]:
    """Aligne les données des formulaires officiels sur la convention générée (si elle existe
    et est à jour) : membres + lot + prix de vente de chaque part, forme, habilitation,
    signataires, montant de l'acte d'engagement = total de l'offre commune. Les sous-traitants
    déjà présents sont conservés (DC4 : ils ne sont pas membres du groupement).
    Modifie company_data / project_data EN PLACE ; renvoie le bloc groupement ou None."""
    grp = cerfa_groupement(db, project)
    if not grp:
        return None
    subs = [ct for ct in (project_data.get("cotraitants") or []) if _is_sous_traitant((ct or {}).get("role"))]
    project_data["cotraitants"] = list(grp["cotraitants"]) + subs
    project_data["groupement"] = {k: grp.get(k) for k in (
        "forme", "mandataire_solidaire", "habilitation", "total_ht", "mandataire", "signataires",
        "convention_status", "convention_version")}
    if grp.get("total_ht") is not None:
        project_data["budget"] = grp["total_ht"]
    lead = grp.get("mandataire") or {}
    if lead.get("signataire_qualite"):
        company_data["signataire_qualite"] = lead["signataire_qualite"]
    return grp


def mark_cerfa_generated(db, project_id: int, doc_types, convention_version=None) -> None:
    """Horodate les formulaires officiels produits par l'export / le dossier (comme le fait
    le routeur CERFA) : l'état « prêt à déposer » vérifie qu'ils datent d'APRÈS la convention.
    Best-effort, ne lève jamais."""
    try:
        from app.models import GeneratedDoc, utcnow
        now = utcnow()
        for dt in doc_types:
            g = db.query(GeneratedDoc).filter(GeneratedDoc.project_id == project_id,
                                              GeneratedDoc.doc_type == dt).first()
            if g is None:
                g = GeneratedDoc(project_id=project_id, doc_type=dt)
                db.add(g)
            g.status = "pret"
            g.filled_data = {"source": "dossier", "convention_version": convention_version}
            g.updated_at = now
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def active_convention_pdf(db, project) -> Optional[tuple]:
    """(pdf, conv) de la convention générée et à jour, pour le ZIP / le dossier. None sinon."""
    conv = get_convention(db, project.id)
    if conv is None or conv.status not in ACTIVE:
        return None
    refresh(db, project, conv)
    if conv.status not in ACTIVE or not conv.content_md:
        return None
    return convention_pdf(conv, signatures_of(db, conv)), conv


def snapshot_parts(members: list) -> list:
    """Parts figées dans groupement_plan.offre (vue mandataire uniquement) : identité + lot +
    prix de vente. JAMAIS detail_chiffre."""
    keys = ("kind", "invite_id", "link_id", "company", "siret", "role", "lot", "prix_lot_ht",
            "representant_legal", "signataire_qualite", "address", "postal_code", "city",
            "forme_juridique", "email", "phone", "ca_n1", "effectif")
    return [{k: m.get(k) for k in keys} for m in members]


def now_utc():
    return datetime.now(timezone.utc)
