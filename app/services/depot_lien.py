"""
Documents PRIVÉS déposés par le LIEN d'un partenaire (rédaction, vague 4, décision 5, option a — validée par
Eliot). Contrat : docs/REDACTION_V4_GROUPEMENT.md § 21.

Un partenaire venu par lien magique (sans compte Adjugo) dépose ses propres documents — anciens mémoires,
plaquette, références, attestations — pour que l'aide d'Adjugo rédige SES parties à partir d'eux. Règles tenues
ici (les routes, app/routers/atelier_groupement.py, ne font que contrôler l'accès et traduire les erreurs) :

  • ce qui est déposé est rattaché à SON INVITATION (jamais à l'organisation du chef de file) : tables
    `depots_lien_*`, fichiers rangés sous `invitations/<id>/depots/…` ; `owner_id` (le tenant du marché) ne sert
    qu'à faire partir les lignes avec le marché. Aucun chemin du chef de file ni d'un membre de son organisation
    ne lit ces tables (ni l'atelier, ni « Mes documents », ni le coffre, ni l'export du dossier, ni son export
    RGPD) ; il ne reçoit, avec le texte envoyé, que les compteurs de sources par type (« trouvés dans ses
    documents ») ;
  • au PREMIER dépôt, le partenaire accepte les conditions d'utilisation (page /cgv) et la politique de
    confidentialité (page /confidentialite) EXISTANTES : acceptation horodatée, version et empreinte des deux
    textes enregistrées, inscrite au journal chaîné. Une nouvelle version d'un texte redemande l'accord ;
  • lecture SANS IA : couche texte des PDF, Word (.docx), OpenDocument (.odt), texte (.txt) ; un PDF scanné est lu
    par la reconnaissance de caractères LOCALE (tesseract, comme les dossiers d'acheteurs), jamais par l'IA. Aucune
    lecture ne coûte donc d'IA : rien n'est décompté à la lecture. (Si une lecture par l'IA était un jour ajoutée,
    elle passerait par `atelier_groupement.facturer_aide_partenaire`, la seule fonction de facturation.) ;
  • un document qui ressemble à un CV n'est pas gardé (Adjugo ne l'enverrait jamais à l'IA, même règle que la
    vague 3) ; dans les autres, les passages de CV sont retirés AVANT le découpage : ils ne sont jamais cherchés,
    jamais remis à l'IA. Une pièce du dossier d'un acheteur (règlement, CCAP, CCTP) n'est pas gardée non plus :
    elle ne dit rien de l'entreprise ;
  • ils servent UNIQUEMENT à l'aide de l'IA pour SES parties : recherche BM25 sur SES passages seulement (jamais
    `rag.retrieve_multi`, jamais un autre membre), noms des personnes masqués avant l'appel (pii_scope, posé par
    atelier_groupement._executer) ; les faits retrouvés portent « trouvé dans vos documents » avec le passage
    exact (fiches [S#], comme les extraits du savoir-faire d'un compte) ;
  • limites réglables (nombre et taille des fichiers par invitation, total, dépôts par jour, types acceptés,
    pages de scan lues), contrôles du téléversement existants (lecture bornée, liste blanche d'extensions, type
    servi tiré de l'extension, signature du fichier, archives bornées) ;
  • suppression : par le partenaire (document par document, ses brouillons oublient alors les passages cités) ;
    à l'invitation retirée ou déclinée ; à la réinitialisation de son espace (effacés sans être lus) ; par la
    purge quotidienne : 6 mois après le RÉSULTAT du marché (gagné, perdu, abandonné), à défaut 6 mois après sa
    date limite, à défaut 6 mois après le dernier dépôt ; lien expiré depuis 30 jours ; marché effacé ;
  • un partenaire qui a rattaché son lien à un compte Adjugo utilise les documents et preuves de son compte
    (inchangé) : ce qu'il avait déposé par le lien n'est plus utilisé, il peut seulement le télécharger ou le
    supprimer depuis son compte ;
  • la démo (session et lien partenaire de la démo) ne dépose rien.
"""
import hashlib
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.models import DepotLienDocument, DepotLienEspace, DepotLienMorceau, Project, ProjectInvite, utcnow
from app.services import atelier as at
from app.services import faits_sources as fs

logger = logging.getLogger("adjugo")

AtelierError = at.AtelierError
MB = 1024 * 1024

# Types acceptés (ceux qu'Adjugo lit sans IA) ; DEPOT_LIEN_TYPES peut en retirer, jamais en ajouter.
TYPES_POSSIBLES = {".pdf": "PDF", ".docx": "Word (.docx)", ".odt": "OpenDocument (.odt)", ".txt": "texte (.txt)"}
RESULTATS = ("gagne", "perdu", "abandonne")
PURGE_EXPIRE_JOURS = 30          # lien expiré depuis plus longtemps : effacés (comme les brouillons)
MORCEAUX_MAX = 600               # passages gardés par document (au-delà, le texte est coupé)

LECTURE_TEXTE, LECTURE_SCAN = "texte", "scan"
LECTURES = {LECTURE_TEXTE: "Lu sans IA (texte du document)",
            LECTURE_SCAN: "Lu sans IA (document scanné, reconnaissance de caractères)"}

# ── Phrases à l'écran (françaises, sans jargon) ───────────────────────────────────────
MSG_QUI_VOIT = "Seuls vous et Adjugo les lisez ; le chef de file ne les voit jamais."
MSG_USAGE = ("Adjugo les lit sans IA, puis ne s'en sert que pour rédiger vos parties, en citant le passage exact. "
             "Avant l'IA, il masque les noms de personnes qu'il repère et écarte ce qui ressemble à un CV : retirez "
             "de vos documents les noms que vous ne voulez pas transmettre.")
# La durée de conservation dite au partenaire : la règle de `purger`, mot pour mot (lien expiré compris).
MSG_CONSERVATION = ("Ils sont effacés dès que vous les supprimez, si vous quittez le groupement ou en êtes retiré ; sinon "
                    "automatiquement, à la première de ces dates : {expiration}{mois} mois après le résultat du "
                    "marché (à défaut, après sa date limite ou, sans date limite, après votre dernier dépôt).")
MSG_CONSERVATION_LIEN = "{jours} jours après l'expiration de ce lien (il expire le {date}), "
MSG_COMPTE = ("Ces documents ont été déposés par votre lien, avant que vous le rattachiez à votre compte Adjugo. "
              "Adjugo ne s'en sert plus : il s'appuie maintenant sur votre savoir-faire et vos preuves. Vous pouvez "
              "les télécharger ou les supprimer.")
MSG_PAR_LE_COMPTE = ("Avec votre compte Adjugo, ajoutez vos documents à « Mon savoir-faire » : Adjugo s'en sert pour "
                     "rédiger vos parties, avec vos seuls droits.")
MSG_CONDITIONS = ("Avant votre premier dépôt, acceptez les conditions d'utilisation et la politique de "
                  "confidentialité d'Adjugo.")
MSG_CONDITIONS_NOUVELLES = ("Les conditions d'utilisation ou la politique de confidentialité ont changé depuis votre "
                            "accord : relisez-les et acceptez-les avant de déposer un autre document.")
MSG_TYPE = "Déposez un fichier {types}."
MSG_VIDE = "Ce fichier est vide."
MSG_TAILLE = "Ce fichier dépasse {mo} Mo : déposez une version plus légère (un PDF exporté sans images, par exemple)."
MSG_NOMBRE = "Vous avez déjà déposé {n} documents, le maximum : supprimez-en un pour en déposer un autre."
MSG_TOTAL = "Vos documents dépasseraient {mo} Mo au total : supprimez-en un pour déposer celui-ci."
MSG_JOUR = "Vous avez déjà déposé {n} documents aujourd'hui : réessayez demain."
MSG_DOUBLON = "Ce document est déjà dans votre espace."
MSG_SIGNATURE = "Ce fichier n'est pas un vrai {type} : enregistrez-le de nouveau depuis votre logiciel, puis déposez-le."
MSG_ILLISIBLE = ("Adjugo n'a trouvé aucun texte lisible dans ce document (scan illisible, fichier protégé ou vide). "
                 "Déposez un PDF qui contient du texte, ou un document Word.")
MSG_CV = ("Ce document ressemble à un CV : Adjugo n'envoie jamais un CV à l'IA, il n'est donc pas gardé. Si ce n'est "
          "pas un CV, retirez-en les CV et déposez-le de nouveau.")
MSG_ACHETEUR = ("Ce document ressemble à une pièce du dossier de l'acheteur (règlement, CCAP, CCTP) : Adjugo la lit "
                "déjà dans le dossier du marché, et elle ne dit rien de votre entreprise. Elle n'est pas gardée.")
MSG_INTROUVABLE = "Document introuvable."
MSG_ESPACE_REINITIALISE = ("Votre espace privé a été réinitialisé pendant le dépôt : le document n'a pas été gardé. "
                           "Ouvrez de nouveau votre espace privé sur cet appareil pour le déposer.")
MSG_STOCKAGE = "Le dépôt n'a pas abouti : réessayez dans quelques minutes."


# ── Réglages ────────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return v if v >= minimum else default
    except ValueError:
        return default


def types_acceptes() -> list:
    """Extensions acceptées : DEPOT_LIEN_TYPES (« .pdf,.docx ») parmi celles qu'Adjugo lit sans IA ; défaut, toutes."""
    brut = os.getenv("DEPOT_LIEN_TYPES", "")
    if not brut.strip():
        return list(TYPES_POSSIBLES)
    voulus = {("." + x.strip().lower().lstrip(".")) for x in brut.split(",") if x.strip()}
    return [t for t in TYPES_POSSIBLES if t in voulus] or list(TYPES_POSSIBLES)


def _types_libelle(types: list) -> str:
    libs = [TYPES_POSSIBLES[t] for t in types]
    return libs[0] if len(libs) == 1 else ", ".join(libs[:-1]) + " ou " + libs[-1]


def limites() -> dict:
    """Limites réglables par invitation (variables d'environnement, défauts entre parenthèses)."""
    types = types_acceptes()
    return {"fichiers": _env_int("DEPOT_LIEN_FICHIERS", 10),            # documents gardés (10)
            "mo_par_fichier": _env_int("DEPOT_LIEN_MO", 10),             # taille d'un fichier (10 Mo)
            "mo_total": _env_int("DEPOT_LIEN_MO_TOTAL", 50),             # total des fichiers gardés (50 Mo)
            "par_jour": _env_int("DEPOT_LIEN_PAR_JOUR", 30),             # dépôts sur 24 h, supprimés compris (30)
            "pages_scan": _env_int("DEPOT_LIEN_PAGES_SCAN", 10),         # pages d'un scan lues sans IA (10)
            "caracteres": _env_int("DEPOT_LIEN_CARACTERES", 200_000),    # texte lu par document (200 000)
            "conservation_mois": _env_int("DEPOT_LIEN_CONSERVATION_MOIS", 6),
            "types": types, "types_libelle": _types_libelle(types)}


# ── Les textes acceptés (pages juridiques EXISTANTES, jamais modifiées ici) ─────────────

TEXTES = (("cgu", "cgv.html", "/cgv", "Conditions générales de vente et d'utilisation"),
          ("confidentialite", "confidentialite.html", "/confidentialite", "Politique de confidentialité"))
_VERSION = re.compile(r"Version\s*:\s*([^<—–]+?)\s*[—–-]\s*Derni(?:è|&egrave;)re\s+mise\s+(?:à|&agrave;)\s+jour\s*:"
                      r"\s*([^<]+?)\s*<", re.IGNORECASE)
_TEXTES_CACHE: dict = {}


def _static_legal(nom: str) -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "legal", nom)


def textes_juridiques() -> list:
    """Les deux textes à accepter, tels qu'ils sont publiés : version et date écrites en tête de la page, empreinte du
    fichier publié (16 premiers caractères du sha256). Relus si le fichier change."""
    out = []
    for cle, fichier, adresse, titre in TEXTES:
        chemin = _static_legal(fichier)
        try:
            mtime = os.path.getmtime(chemin)
        except OSError:
            mtime = None
        c = _TEXTES_CACHE.get(cle)
        if c is None or c[0] != mtime:
            version, maj, empreinte = "", "", ""
            try:
                with open(chemin, "rb") as f:
                    brut = f.read()
                empreinte = hashlib.sha256(brut).hexdigest()[:16]
                m = _VERSION.search(brut.decode("utf-8", "replace"))
                if m:
                    version, maj = m.group(1).strip(), m.group(2).strip()
            except OSError:
                pass
            c = (mtime, {"cle": cle, "titre": titre, "adresse": adresse, "version": version or "non indiquée",
                         "mise_a_jour": maj, "empreinte": empreinte})
            _TEXTES_CACHE[cle] = c
        out.append(dict(c[1]))
    return out


def verrouiller_invitation(db, invite_id: int, frais: bool = False) -> Optional[ProjectInvite]:
    """Le verrou de l'invitation (une ligne, jusqu'à la validation) : déposer, supprimer, réinitialiser l'espace,
    effacer ce qu'elle a déposé et ranger le brouillon d'une aide de l'IA passent l'un après l'autre. `frais` :
    l'invitation relue après le verrou (clé de l'espace, rattachement à jour) — jamais quand l'appelant a modifié
    l'invitation sans valider (la session ne valide pas d'elle-même : ces changements seraient perdus)."""
    q = db.query(ProjectInvite).filter(ProjectInvite.id == int(invite_id)).with_for_update()
    if frais:
        q = q.populate_existing()
    return q.first()


def _espace(db, invite_id: int) -> Optional[DepotLienEspace]:
    return db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == invite_id).first()


def conditions(db, inv: ProjectInvite) -> dict:
    """Où en est l'accord du partenaire : à donner avant le premier dépôt, à redonner quand une version change."""
    textes = textes_juridiques()
    esp = _espace(db, inv.id)
    acc = (esp.consentement if esp is not None and isinstance(esp.consentement, dict) else {}) or {}
    a_jour = bool(acc) and all((acc.get(t["cle"]) or {}).get("version") == t["version"] for t in textes)
    message = "" if a_jour else (MSG_CONDITIONS_NOUVELLES if acc else MSG_CONDITIONS)
    return {"a_accepter": not a_jour, "acceptees_le": acc.get("accepte_le") if acc else None,
            "textes": textes, "message": message}


def _accepter(db, acces, ip: str = "") -> None:
    textes = textes_juridiques()
    esp = _espace(db, acces.inv.id)
    if esp is None:
        esp = DepotLienEspace(invite_id=acces.inv.id, project_id=acces.project.id, owner_id=acces.dossier.owner_id)
        db.add(esp)
    le = utcnow()
    esp.consentement = {t["cle"]: {"version": t["version"], "mise_a_jour": t["mise_a_jour"],
                                   "empreinte": t["empreinte"], "adresse": t["adresse"]} for t in textes}
    esp.consentement["accepte_le"] = le.isoformat()
    esp.accepte_le = le
    db.commit()
    v = {t["cle"]: t["version"] for t in textes}
    _journal(db, acces, "redaction.documents_conditions", ip=ip,
             detail=(f"Conditions d'utilisation (version {v.get('cgu')}) et politique de confidentialité (version "
                     f"{v.get('confidentialite')}) acceptées pour déposer des documents"),
             meta={"versions": v, "empreintes": {t["cle"]: t["empreinte"] for t in textes}})


# ── Journal (jamais un nom de document : le journal du lien se lit avec le lien seul) ──

def _journal(db, acces, action: str, *, detail: str, ip: str = "", meta=None, actor=None, actor_kind="guest") -> None:
    from app.services import audit
    audit.record(db, action=action, owner_id=acces.dossier.owner_id, project_id=acces.project.id,
                 actor=(actor or acces.acteur)[:160], actor_kind=actor_kind, target_type="invite",
                 target_id=acces.inv.id, detail=(detail or "")[:255], ip=ip or "", meta=meta, invite_id=acces.inv.id)


def _journal_invitation(db, inv: ProjectInvite, owner_id: int, action: str, detail: str, *, actor: str = "system",
                        actor_kind: str = "system", ip: str = "", meta=None) -> None:
    from app.services import audit
    audit.record(db, action=action, owner_id=owner_id, project_id=inv.project_id, actor=(actor or "system")[:160],
                 actor_kind=actor_kind, target_type="invite", target_id=inv.id, detail=(detail or "")[:255],
                 ip=ip or "", meta=meta, invite_id=inv.id)


# ── Qui peut déposer, lire, supprimer ─────────────────────────────────────────────────

def utilises(acces) -> bool:
    """Les documents déposés servent-ils à l'aide de l'IA de CET accès ? Par le lien seulement, tant qu'il n'est pas
    rattaché à un compte (un compte utilise ses propres documents et preuves, inchangé)."""
    from app.services.atelier_groupement import par_le_compte
    return acces.mode != "compte" and not par_le_compte(acces.inv)


def _exiger_lecture(acces) -> None:
    """Lire la liste, télécharger, supprimer : la matière privée du partenaire (clé de l'espace par le lien, ou le compte
    qui a rattaché le lien)."""
    from app.services.atelier_groupement import _exiger_espace
    _exiger_espace(acces)


def _exiger_depot(acces) -> None:
    from app.services.atelier_groupement import _exiger_ecriture, _exiger_identite, par_le_compte
    if acces.mode == "compte" or par_le_compte(acces.inv):
        raise AtelierError(403, "depot_par_le_compte", MSG_PAR_LE_COMPTE)
    _exiger_ecriture(acces)          # clé de l'espace, co-construction ouverte, jamais la démo
    # Accepter les conditions et déposer engagent la personne : même exigence d'identité qu'envoyer (adresse prouvée
    # par code quand le lien vise une adresse). Celui qui a seulement réinitialisé l'espace ne dépose rien en son nom.
    _exiger_identite(acces)


def _refuser_demo(acces) -> None:
    from app.routers.invites import _invite_is_demo
    if _invite_is_demo(acces.inv, acces.db):
        raise AtelierError(403, "demo", "La démo est en lecture guidée : créez votre compte gratuit pour co-construire "
                                        "une réponse avec vos partenaires.")


def documents(db, invite_id: int) -> list:
    return (db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == invite_id)
            .order_by(DepotLienDocument.id).all())


def _document(db, acces, doc_id) -> DepotLienDocument:
    try:
        did = int(doc_id)
    except (TypeError, ValueError):
        did = 0
    d = (db.query(DepotLienDocument).filter(DepotLienDocument.id == did,
                                            DepotLienDocument.invite_id == acces.inv.id).first())
    if d is None:
        raise AtelierError(404, "document_introuvable", MSG_INTROUVABLE)
    return d


def _doc_out(d: DepotLienDocument) -> dict:
    return {"id": d.id, "nom": d.nom, "taille": int(d.taille or 0), "depose_le": at._iso(d.created_at),
            "lecture": d.lecture, "lecture_libelle": LECTURES.get(d.lecture or "", ""), "complet": bool(d.complet),
            "caracteres": int(d.caracteres or 0), "passages": int(d.morceaux or 0),
            "passages_cv_retires": int(d.lignes_cv_retirees or 0) > 0}


def resume(db, acces) -> Optional[dict]:
    """Pour la vue du partenaire : combien de documents, et s'ils servent (None sans la matière privée)."""
    if not acces.cle_ok:
        return None
    n = db.query(DepotLienDocument.id).filter(DepotLienDocument.invite_id == acces.inv.id).count()
    return {"nombre": int(n), "utilises": utilises(acces), "possible": utilises(acces)}


def _jour_fr(dt) -> str:
    mois = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
            "novembre", "décembre")
    return f"{dt.day}{'er' if dt.day == 1 else ''} {mois[dt.month - 1]} {dt.year}"


def conservation(inv: ProjectInvite, mois: int) -> str:
    """Combien de temps ses documents sont gardés, tel que `purger` l'applique : le lien qui expire (par défaut
    30 jours après sa création) les fait effacer PURGE_EXPIRE_JOURS jours après son expiration."""
    exp = _naif(getattr(inv, "expires_at", None))
    lien = MSG_CONSERVATION_LIEN.format(jours=PURGE_EXPIRE_JOURS, date=_jour_fr(exp)) if exp is not None else ""
    return MSG_CONSERVATION.format(expiration=lien, mois=mois)


def vue(db, acces) -> dict:
    """« Vos documents pour Adjugo » : la liste, l'accord, les limites et qui voit quoi."""
    _exiger_lecture(acces)
    lim = limites()
    util = utilises(acces)
    return {"documents": [_doc_out(d) for d in documents(db, acces.inv.id)],
            "utilises": util, "peut_deposer": util and bool(getattr(acces.inv, "can_contribute", True)),
            "qui_voit": MSG_QUI_VOIT, "usage": MSG_USAGE,
            "conservation": conservation(acces.inv, lim["conservation_mois"]),
            "message": "" if util else MSG_COMPTE,
            "conditions": conditions(db, acces.inv) if util else None,
            "limites": {k: lim[k] for k in ("fichiers", "mo_par_fichier", "mo_total", "par_jour", "pages_scan",
                                            "types", "types_libelle")}}


# ── Lecture SANS IA ─────────────────────────────────────────────────────────────────

def _ext(nom: str) -> str:
    return os.path.splitext(str(nom or ""))[1].lower()


def _nom_propre(nom: str) -> str:
    n = os.path.basename(str(nom or "").replace("\\", "/")).strip()
    n = re.sub(r"[\x00-\x1f\x7f]", "", n)
    return (n or "document")[:200]


def _verifier_signature(contenu: bytes, ext: str) -> None:
    """Le contenu correspond à l'extension (un texte ou une page web renommés ne passent pas) — même règle que les
    pièces des partenaires (invites._check_dpgf_signature)."""
    ok = True
    if ext == ".pdf":
        ok = b"%PDF-" in contenu[:1024]
    elif ext in (".docx", ".odt"):
        ok = contenu.startswith(b"PK\x03\x04")
    elif ext == ".txt":
        ok = b"\x00" not in contenu[:8192]
    if not ok:
        raise AtelierError(422, "fichier_invalide", MSG_SIGNATURE.format(type=TYPES_POSSIBLES.get(ext, ext)))


def lire(nom: str, contenu: bytes, ext: str) -> tuple:
    """(texte, lecture, lu en entier) — SANS IA : couche texte du PDF (scan : reconnaissance de caractères locale, au
    plus `pages_scan` pages), Word, OpenDocument, texte. Mémoire et temps bornés par les plafonds d'Adjugo
    (app.services.analysis). ("", "", False) si rien n'est lisible."""
    from app.services import analysis as an
    lim = limites()
    maxc = lim["caracteres"]
    if ext == ".pdf":
        info = {}
        t = an.extract_text_from_pdf(contenu, max_chars=maxc, info=info) or ""
        if t.startswith("Erreur"):
            t = ""
        if len(t.strip()) >= 30:
            return t[:maxc], LECTURE_TEXTE, bool(info.get("complet", True)) and len(t) < maxc
        if an.ocr_available():
            oinfo = {}
            o = an._ocr_pdf(contenu, max_pages=lim["pages_scan"], info=oinfo) or ""
            if len(o.strip()) >= 30:
                return o[:maxc], LECTURE_SCAN, bool(oinfo.get("complet", False)) and len(o) < maxc
        return "", "", False
    if ext in (".docx", ".odt"):
        if not an._docx_sizes_ok(contenu):
            return "", "", False
        info = {}
        t = (an._extract_docx(contenu, info=info) if ext == ".docx" else an.extract_odf(contenu, info=info)) or ""
        return t[:maxc], LECTURE_TEXTE, bool(info.get("complet", True)) and len(t) < maxc
    if ext == ".txt":
        brut = contenu[:maxc * 4]
        try:
            t = brut.decode("utf-8")
        except UnicodeDecodeError:
            t = brut.decode("cp1252", errors="replace")
        t = t.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
        return t[:maxc], LECTURE_TEXTE, len(t) < maxc
    return "", "", False


class _Doc:
    """Ce que les règles de la vague 3 (fiches_import.est_cv, est_piece_acheteur) lisent d'un document."""

    def __init__(self, nom: str, texte: str):
        self.id, self.name, self.text = None, nom, texte
        self.char_count = len(texte or "")


def decouper(texte: str) -> tuple:
    """(passages, lignes de CV retirées) : les lignes de CV (section « CV », paragraphe en forme de CV, avec ses
    voisins) sont vidées AVANT le découpage, puis tout passage qui ressemble encore à un CV est écarté. Ce qui reste
    peut être cherché et remis à l'IA (noms masqués à l'appel)."""
    from app.services import fiches_import as fi
    from app.services import rag
    lignes = str(texte or "").split("\n")
    cv = fi.lignes_privees(texte)["cv"]
    for i in cv:
        lignes[i] = ""
    morceaux = [c for c in rag.chunk_text("\n".join(lignes)) if not fi._bloc_cv(c)]
    return morceaux[:MORCEAUX_MAX], len(cv)


# ── Déposer, télécharger, supprimer ────────────────────────────────────────────────────

def _depots_du_jour(db, invite_id: int) -> int:
    from app.models import AuditLog
    depuis = utcnow() - timedelta(hours=24)
    return (db.query(AuditLog.id).filter(AuditLog.invite_id == invite_id,
                                         AuditLog.action == "redaction.document_depose",
                                         AuditLog.created_at >= depuis).count())


def _limites_du_depot(db, invite_id: int, taille: int, empreinte: str, lim: dict) -> None:
    deja = documents(db, invite_id)
    if len(deja) >= lim["fichiers"]:
        raise AtelierError(409, "trop_de_documents", MSG_NOMBRE.format(n=lim["fichiers"]))
    if sum(int(d.taille or 0) for d in deja) + int(taille) > lim["mo_total"] * MB:
        raise AtelierError(409, "espace_plein", MSG_TOTAL.format(mo=lim["mo_total"]))
    if _depots_du_jour(db, invite_id) >= lim["par_jour"]:
        raise AtelierError(429, "trop_de_depots", MSG_JOUR.format(n=lim["par_jour"]))
    if any(d.empreinte == empreinte for d in deja):
        raise AtelierError(409, "document_deja_depose", MSG_DOUBLON)


def _encore_le_meme_espace(db, acces) -> None:
    """Sous le verrou de l'invitation, relue : la clé présentée ouvre encore l'espace (ni réinitialisé, ni lien
    rattaché à un compte entre-temps), le dépôt est encore permis, et l'accord est encore enregistré et à jour."""
    from app.services.atelier_groupement import cle_valide
    inv = verrouiller_invitation(db, acces.inv.id, frais=True)
    if inv is None:
        raise AtelierError(404, "document_introuvable", MSG_INTROUVABLE)
    acces.inv = inv
    acces.cle_ok = acces.mode == "compte" or cle_valide(inv, getattr(acces, "cle", None))
    if not acces.cle_ok:
        raise AtelierError(409, "espace_reinitialise", MSG_ESPACE_REINITIALISE)
    _exiger_depot(acces)
    cond = conditions(db, inv)
    if cond["a_accepter"]:
        raise AtelierError(409, "conditions_a_accepter", cond["message"], conditions=cond)


def deposer(db, acces, nom_fichier: str, contenu: bytes, *, accepte_cgu: bool = False,
            accepte_confidentialite: bool = False, ip: str = "") -> DepotLienDocument:
    """Un document déposé par le partenaire dans SON espace privé (par le lien) : accord au premier dépôt, contrôles
    du fichier, lecture SANS IA, passages de CV retirés, découpage pour la recherche. Rien n'appelle l'IA."""
    _refuser_demo(acces)
    _exiger_depot(acces)
    inv = acces.inv
    cond = conditions(db, inv)
    if cond["a_accepter"]:
        if not (accepte_cgu and accepte_confidentialite):
            raise AtelierError(409, "conditions_a_accepter", cond["message"], conditions=cond)
        _accepter(db, acces, ip=ip)
    lim = limites()
    nom = _nom_propre(nom_fichier)
    ext = _ext(nom)
    if ext not in lim["types"]:
        raise AtelierError(422, "type_refuse", MSG_TYPE.format(types=lim["types_libelle"]), types=lim["types"])
    if not contenu:
        raise AtelierError(422, "fichier_vide", MSG_VIDE)
    if len(contenu) > lim["mo_par_fichier"] * MB:
        raise AtelierError(413, "fichier_trop_lourd", MSG_TAILLE.format(mo=lim["mo_par_fichier"]))
    empreinte = hashlib.sha256(contenu).hexdigest()
    _limites_du_depot(db, inv.id, len(contenu), empreinte, lim)
    _verifier_signature(contenu, ext)
    texte, lecture, complet = lire(nom, contenu, ext)
    if len((texte or "").strip()) < 40:
        raise AtelierError(422, "document_illisible", MSG_ILLISIBLE)
    from app.services import fiches_import as fi
    d0 = _Doc(nom, texte)
    if fi.est_cv(d0):
        raise AtelierError(422, "document_cv", MSG_CV)
    if fi.est_piece_acheteur(d0):
        raise AtelierError(422, "piece_acheteur", MSG_ACHETEUR)
    morceaux, n_cv = decouper(texte)
    if not morceaux:
        raise AtelierError(422, "document_illisible", MSG_ILLISIBLE)
    # Relu SOUS VERROU (la lecture a pu durer) : deux dépôts simultanés ne dépassent pas les limites, et un espace
    # réinitialisé pendant la lecture (par qui détient le lien) ne reçoit rien — ni fichier ni ligne : la clé
    # présentée doit être encore celle de l'espace, l'accord encore enregistré et à jour.
    _encore_le_meme_espace(db, acces)
    _limites_du_depot(db, inv.id, len(contenu), empreinte, lim)
    from app.core.mime import mime_for
    from app.services.storage import get_storage
    cle = f"invitations/{int(inv.id)}/depots/{uuid.uuid4().hex}{ext}"
    try:
        get_storage().save(cle, contenu, mime_for(cle))
    except Exception as e:      # noqa: BLE001 — rien n'est inscrit : le partenaire réessaie
        logger.warning("dépôt du partenaire (invitation %s) : stockage impossible : %s", inv.id, type(e).__name__)
        raise AtelierError(503, "stockage_indisponible", MSG_STOCKAGE)
    try:
        doc = DepotLienDocument(invite_id=inv.id, project_id=acces.project.id, owner_id=acces.dossier.owner_id,
                                nom=nom, file_key=cle, taille=len(contenu), type_mime=mime_for(cle)[:100],
                                empreinte=empreinte, caracteres=len(texte), lecture=lecture, complet=bool(complet),
                                morceaux=len(morceaux), lignes_cv_retirees=int(n_cv))
        db.add(doc)
        db.flush()
        for i, m in enumerate(morceaux):
            db.add(DepotLienMorceau(document_id=doc.id, invite_id=inv.id, ordinal=i, texte=m))
        db.commit()
    except Exception:
        db.rollback()
        try:
            get_storage().delete(cle)
        except Exception:       # noqa: BLE001
            pass
        raise
    db.refresh(doc)
    # Le journal du marché (lu aussi par le chef de file) dit qu'un document a été déposé, jamais lequel, ni son rang,
    # ni sa taille.
    _journal(db, acces, "redaction.document_depose", ip=ip,
             detail="Document déposé dans l'espace privé du partenaire, lu sans IA",
             meta={"lecture": lecture})
    return doc


def fichier(db, acces, doc_id) -> tuple:
    """(contenu, nom, clé) d'un document du partenaire, pour SON téléchargement (jamais une adresse signée : la clé
    de l'espace ne voyage que dans l'en-tête)."""
    _exiger_lecture(acces)
    d = _document(db, acces, doc_id)
    from app.services.storage import get_storage
    try:
        contenu = get_storage().load(d.file_key)
    except FileNotFoundError:
        raise AtelierError(410, "fichier_absent", "Ce fichier n'est plus disponible.")
    return contenu, d.nom, d.file_key


def supprimer(db, acces, doc_id, ip: str = "") -> int:
    """Le partenaire supprime UN de ses documents (toujours possible, même co-construction fermée) : passages,
    fichier, et, dans ses brouillons, les extraits cités de ce document (leurs faits redeviennent « à relire »)."""
    _refuser_demo(acces)
    _exiger_lecture(acces)
    # Sous le verrou de l'invitation : une aide de l'IA en cours range son brouillon avant (ses extraits de ce
    # document sont alors retirés ici) ou après (elle ne garde que les passages encore présents).
    verrouiller_invitation(db, acces.inv.id)
    d = _document(db, acces, doc_id)
    cle = d.file_key
    from app.services.atelier_groupement import oublier_document
    oublier_document(db, acces.inv.id, d.id)
    db.query(DepotLienMorceau).filter(DepotLienMorceau.document_id == d.id).delete(synchronize_session=False)
    db.delete(d)
    db.commit()
    _supprimer_fichiers([cle])
    _journal(db, acces, "redaction.document_supprime", ip=ip,
             detail="Document supprimé de l'espace privé par le partenaire")
    return 1


def _supprimer_fichiers(cles) -> int:
    from app.services.storage import get_storage
    n = 0
    for k in [c for c in dict.fromkeys(cles or []) if c]:
        try:
            get_storage().delete(k)
            n += 1
        except Exception as e:      # noqa: BLE001 — la ligne est partie : le fichier orphelin est sans accès
            logger.warning("dépôt du partenaire : fichier %s non supprimé : %s", k, type(e).__name__)
    return n


def effacer_invitation(db, invite_id: int, *, commit: bool = True) -> tuple:
    """Tout ce qu'une invitation a déposé (documents, passages, accord), et ce que ses brouillons en ont recopié
    (nom du document et passage des sources ; les faits reliés redeviennent « à relire ») : (nombre de documents,
    clés des fichiers). Sous le verrou de l'invitation (une aide de l'IA en cours range son brouillon avant ou
    après, jamais entre les deux). Sans `commit`, l'appelant valide puis supprime les fichiers
    (`supprimer_fichiers`)."""
    from app.services.atelier_groupement import oublier_documents
    verrouiller_invitation(db, invite_id)
    docs = documents(db, invite_id)
    cles = [d.file_key for d in docs]
    oublier_documents(db, invite_id)
    db.query(DepotLienMorceau).filter(DepotLienMorceau.invite_id == invite_id).delete(synchronize_session=False)
    db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == invite_id).delete(synchronize_session=False)
    db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == invite_id).delete(synchronize_session=False)
    if commit:
        db.commit()
        _supprimer_fichiers(cles)
    return len(docs), cles


def supprimer_fichiers(cles) -> int:
    return _supprimer_fichiers(cles)


def cles_projets(db, project_ids: list) -> list:
    """Clés des fichiers déposés sur ces marchés (effacement du compte du chef de file, corbeille des marchés)."""
    if not project_ids:
        return []
    return [r[0] for r in db.query(DepotLienDocument.file_key).filter(DepotLienDocument.project_id.in_(project_ids))]


def effacer_projets(db, project_ids: list) -> int:
    """Lignes déposées sur ces marchés (sans valider : l'appelant valide, puis supprime les fichiers)."""
    if not project_ids:
        return 0
    dids = [r[0] for r in db.query(DepotLienDocument.id).filter(DepotLienDocument.project_id.in_(project_ids))]
    if dids:
        db.query(DepotLienMorceau).filter(DepotLienMorceau.document_id.in_(dids)).delete(synchronize_session=False)
        db.query(DepotLienDocument).filter(DepotLienDocument.id.in_(dids)).delete(synchronize_session=False)
    db.query(DepotLienEspace).filter(DepotLienEspace.project_id.in_(project_ids)).delete(synchronize_session=False)
    return len(dids)


def exporter(db, invite_id: int) -> dict:
    """Portabilité : ce qu'il a déposé (le fichier se télécharge document par document) et son accord."""
    esp = _espace(db, invite_id)
    return {"documents": [dict(_doc_out(d), telecharger=f"documents/{d.id}/fichier") for d in documents(db, invite_id)],
            "conditions_acceptees": (esp.consentement if esp is not None else None)}


# ── La recherche pour l'aide de l'IA (SES passages seulement) ───────────────────────────

class FicheDepot(fs.Fiche):
    """Un passage d'un document déposé : [S#] « trouvé dans vos documents », avec le passage exact. La source garde
    le document et le passage (privés, chez le partenaire seulement), pour relire le brouillon plus tard."""

    def __init__(self, ref: str, texte: str, doc_nom: str, depot_id: int, depot_chunk_id: int):
        super().__init__(ref, fs.T_DOCUMENTS, fs.LIB_TROUVE, texte, doc_nom=doc_nom)
        self.depot_id, self.depot_chunk_id = depot_id, depot_chunk_id

    def source(self, pos=None, cite: bool = True) -> dict:
        out = super().source(pos, cite)
        out["depot_id"], out["depot_chunk_id"] = self.depot_id, self.depot_chunk_id
        return out


def fiches(chunks: list) -> list:
    out = []
    for i, c in enumerate(chunks or [], start=1):
        if not isinstance(c, dict) or not c.get("depot_chunk_id"):
            continue
        out.append(FicheDepot(str(c.get("ref") or f"{fs.EXTRAIT}{i}"), c.get("text") or "", c.get("doc_nom") or "",
                              int(c.get("depot_id") or 0), int(c["depot_chunk_id"])))
    return out


def _libelles(docs: list) -> dict:
    """Ce que l'IA lit du nom d'un document : « Votre document 2 » (le nom réel, qui peut nommer une personne, ne part
    jamais)."""
    return {d.id: f"Votre document {i}" for i, d in enumerate(docs, start=1)}


def rechercher(db, invite_id: int, requete: str, k: int = 6) -> list:
    """Les passages de SES documents les plus proches de la partie (BM25 sans IA, filtre de pertinence comme le
    savoir-faire), jamais un passage de CV. Chaque passage porte son document (nom réel pour l'écran du partenaire,
    libellé neutre pour l'IA)."""
    from app.services import fiches_import as fi
    from app.services import rag
    docs = documents(db, invite_id)
    if not docs:
        return []
    noms = {d.id: d.nom for d in docs}
    libs = _libelles(docs)
    rows = db.query(DepotLienMorceau).filter(DepotLienMorceau.invite_id == invite_id).all()

    class _R:
        __slots__ = ("id", "doc_id", "doc_name", "ordinal", "user_id", "text")

        def __init__(self, r):
            self.id, self.doc_id, self.doc_name = r.id, r.document_id, noms.get(r.document_id, "")
            self.ordinal, self.user_id, self.text = r.ordinal, 0, r.texte or ""
    corpus = [_R(r) for r in rows if r.document_id in noms]
    if not corpus:
        return []
    out = []
    for score, t in rag._bm25_indexed(rag._build_index(corpus), requete or "", k * 2, relevance=True):
        if fi._bloc_cv(t[5]):
            continue
        out.append({"chunk_id": None, "depot_chunk_id": t[0], "depot_id": t[1], "doc_name": libs.get(t[1], "Votre document"),
                    "doc_nom": t[2], "text": t[5], "score": round(score, 3)})
        if len(out) >= k:
            break
    return out


def extraits_cites(db, invite_id: int, b) -> list:
    """Les passages de SES documents qu'un brouillon cite (ses sources et ses faits reliés à un passage), relus pour
    contrôler de nouveau ce brouillon. Un document supprimé n'apporte plus rien."""
    refs = {}
    for x in list((b.sources if b is not None else None) or []):
        if isinstance(x, dict) and x.get("depot_chunk_id") and str(x.get("ref") or "").startswith(fs.EXTRAIT):
            refs.setdefault(str(x["ref"]), x["depot_chunk_id"])
    for f in fs.avec_source((b.faits if b is not None else None) or []):
        src = f.get("source") or {}
        if src.get("depot_chunk_id") and str(src.get("ref") or "").startswith(fs.EXTRAIT):
            refs.setdefault(str(src["ref"]), src["depot_chunk_id"])
    ids = []
    for v in refs.values():
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            pass
    if not ids:
        return []
    rows = {m.id: m for m in db.query(DepotLienMorceau).filter(DepotLienMorceau.id.in_(ids),
                                                               DepotLienMorceau.invite_id == invite_id).all()}
    noms = {d.id: d.nom for d in documents(db, invite_id)}
    out = []
    for ref, cid in sorted(refs.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0):
        try:
            m = rows.get(int(cid))
        except (TypeError, ValueError):
            m = None
        if m is not None and m.document_id in noms:
            out.append({"ref": ref, "depot_chunk_id": m.id, "depot_id": m.document_id, "doc_nom": noms[m.document_id],
                        "text": m.texte or ""})
    return out


def encore_presents(db, invite_id: int, chunks: list) -> list:
    """Les passages remis à l'IA, relus après l'appel : un passage dont le document a été supprimé (ou effacé)
    entre-temps devient {"retire": True} À SA PLACE (les renvois [S#] des autres ne bougent pas) ; il ne donne
    alors ni fiche, ni source, ni nom de document."""
    ids = []
    for c in chunks or []:
        try:
            if isinstance(c, dict) and c.get("depot_chunk_id"):
                ids.append(int(c["depot_chunk_id"]))
        except (TypeError, ValueError):
            pass
    ok = set()
    if ids:
        ok = {r[0] for r in db.query(DepotLienMorceau.id).filter(DepotLienMorceau.id.in_(ids),
                                                                DepotLienMorceau.invite_id == invite_id)}
    out = []
    for c in chunks or []:
        if not (isinstance(c, dict) and c.get("depot_chunk_id")):
            out.append(c)
            continue
        try:
            garde = int(c["depot_chunk_id"]) in ok
        except (TypeError, ValueError):
            garde = False
        out.append(c if garde else {"retire": True})
    return out


def sources_reelles(sources: list, chunks: list) -> list:
    """Les extraits cités par l'IA ([S#]), avec le nom réel du document et le passage déposé (privés : chez le
    partenaire seulement). L'IA n'a lu qu'un libellé neutre (« Votre document 2 »). Un passage retiré
    (`encore_presents` : document supprimé pendant l'appel) ne laisse aucune source."""
    par_ref = {str(c.get("ref") or f"{fs.EXTRAIT}{i}") if isinstance(c, dict) else f"{fs.EXTRAIT}{i}": c
               for i, c in enumerate(chunks or [], start=1)}
    out = []
    for s in sources or []:
        c = par_ref.get(str((s or {}).get("ref") or "")) if isinstance(s, dict) else None
        if isinstance(c, dict) and c.get("retire"):
            continue
        if c is None or not c.get("depot_chunk_id"):
            out.append(s)
            continue
        out.append({"ref": s["ref"], "doc_name": c.get("doc_nom") or "", "extrait": s.get("extrait") or "",
                    "depot_id": c.get("depot_id"), "depot_chunk_id": c.get("depot_chunk_id")})
    return out


# ── Purge quotidienne (POST /api/admin/run-trash-purge) ─────────────────────────────────

def _naif(dt) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt
    if isinstance(dt, date):
        return datetime(dt.year, dt.month, dt.day)
    return None


def plus_mois(dt: datetime, mois: int) -> datetime:
    """La même date `mois` mois plus tard (dernier jour du mois si elle n'existe pas : 31 août + 6 mois = 28 février)."""
    import calendar
    m = dt.month - 1 + int(mois)
    y, m = dt.year + m // 12, m % 12 + 1
    return dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))


def _statut(p: Project) -> str:
    s = getattr(p, "status", None)
    return str(getattr(s, "value", s) or "")


def purger(db, maintenant: Optional[datetime] = None) -> dict:
    """Efface ce qu'ont déposé les partenaires : invitation retirée ou déclinée (filet), lien expiré depuis plus de
    30 jours, marché effacé ; sinon `conservation_mois` mois après le RÉSULTAT du marché (gagné, perdu, abandonné :
    date du résultat constatée par la purge, à défaut celle de la dernière modification du marché), à défaut
    après sa date limite, à défaut après le dernier dépôt. Un résultat retiré (marché repassé « envoyé ») remet
    le compteur à zéro. Inscrit au journal du partenaire (sans aucun nom de document)."""
    now = _naif(maintenant or utcnow())
    mois = limites()["conservation_mois"]
    iids = ({r[0] for r in db.query(DepotLienEspace.invite_id)}
            | {r[0] for r in db.query(DepotLienDocument.invite_id)})
    a_effacer = []
    for iid in sorted(iids):
        inv = db.get(ProjectInvite, iid)
        raison = None
        if inv is None or inv.revoked or getattr(inv, "declined_at", None):
            raison = "invitation retirée ou déclinée"
        elif inv.expires_at is not None and _naif(inv.expires_at) < now - timedelta(days=PURGE_EXPIRE_JOURS):
            raison = f"lien expiré depuis plus de {PURGE_EXPIRE_JOURS} jours"
        else:
            p = db.get(Project, inv.project_id)
            esp = _espace(db, iid)
            if p is None:
                raison = "marché effacé"
            elif _statut(p) in RESULTATS:
                if esp is not None and esp.resultat_le is None:
                    esp.resultat_le = min(_naif(p.updated_at) or now, now)
                quand = _naif(esp.resultat_le) if esp is not None else (_naif(p.updated_at) or now)
                if plus_mois(quand, mois) <= now:
                    raison = f"{mois} mois après le résultat du marché"
            else:
                if esp is not None and esp.resultat_le is not None:
                    esp.resultat_le = None
                if p.deadline is not None:
                    if plus_mois(_naif(p.deadline), mois) <= now:
                        raison = f"{mois} mois après la date limite du marché"
                else:
                    dernier = max([_naif(d.created_at) for d in documents(db, iid) if d.created_at] or [None],
                                  key=lambda x: x or datetime.min)
                    if dernier is not None and plus_mois(dernier, mois) <= now:
                        raison = f"{mois} mois après le dernier dépôt (marché sans date limite ni résultat)"
        if raison:
            a_effacer.append((iid, inv, raison))
    db.commit()
    n_docs, cles, journal = 0, [], []
    for iid, inv, raison in a_effacer:
        n, k = effacer_invitation(db, iid, commit=False)
        n_docs += n
        cles += k
        if inv is not None and n:
            from app.services.atelier_groupement import dossier_du_marche
            p = db.get(Project, inv.project_id)
            d = dossier_du_marche(db, p, inv.owner_id) if p is not None else None
            journal.append((inv, d.owner_id if d is not None else inv.owner_id, n, raison))
    db.commit()
    _supprimer_fichiers(cles)
    for inv, owner, n, raison in journal:
        _journal_invitation(db, inv, owner, "redaction.documents_effaces",
                            f"{n} document{'s' if n > 1 else ''} déposé{'s' if n > 1 else ''} effacé{'s' if n > 1 else ''} "
                            f"automatiquement : {raison}", meta={"documents": n})
    return {"documents_partenaires_effaces": n_docs, "espaces_documents_effaces": len(a_effacer)}
