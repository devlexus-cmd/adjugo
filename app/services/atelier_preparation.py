"""
« Comment ce dossier a été préparé » (rédaction, vague 6 — étude § 6.12 H, décision 9 a).

Contrat : docs/REDACTION_V6.md, section H. À l'export Word ou PDF du dossier de présentation, une case
DÉCOCHÉE par défaut (« Joindre une page "Comment ce dossier a été préparé" ») ajoute, à la fin du fichier, une
page qui dit pour chaque partie :
  • l'entreprise qui l'a rédigée (groupement compris : chaque membre, la partie tirée de la convention ou des
    parts des membres) ;
  • si l'IA a aidé ou non (le drapeau `ia` de la version exportée, celui qui décide la mention « Préparé avec
    assistance IA » des propriétés du fichier : les deux disent toujours la même chose) ;
  • le nombre de faits par type de source, JAMAIS leur contenu ;
  • qui l'a validée, et à quelle date.

Tout est calculé SANS IA, à partir du texte que l'export rend (`atelier.versions_communes` pour le lecteur qui
exporte, faits lus comme l'export les lit : une source perdue rend le fait « sans source »).

Rien de privé n'entre dans la page :
  • ni texte, ni source, ni extrait, ni nom de document, ni phrase d'un fait : des NOMBRES seulement ;
  • pour la partie d'un partenaire : son texte COMMUN (envoyé, ou écrit par le chef de file), ses compteurs de
    sources par type (déjà communs en vague 4), son nom d'entreprise et sa validation — jamais un brouillon, jamais
    ce qu'il a relu lui-même (compte privé, non transmis) ;
  • aucun nom de personne, aucune adresse : « qui a validé » est l'ENTREPRISE (le partenaire valide sa partie,
    le chef de file les siennes ; l'identifiant du compte d'un partenaire n'est jamais gardé) ;
  • aucun nom d'outil (règle 7 : rien d'interne ne part chez l'acheteur), jamais « vérifié » (règle 3).

Seul le chef de file exporte le dossier de présentation (l'atelier) : la page n'entre dans aucun export d'un
partenaire (sa portabilité et son export RGPD restent ceux de la vague 4).
"""
from datetime import datetime, timezone
from typing import Optional

from app.models import DossierSection, DossierSectionVersion, ProjectInvite
from app.services import atelier as at
from app.services import atelier_export as ax
from app.services import faits_a_relire as far
from app.services import faits_sources as fs

TITRE = "Comment ce dossier a été préparé"
LIBELLE_CASE = "Joindre une page « Comment ce dossier a été préparé »"
BULLE = ("Cette page dit, pour chaque partie, l'entreprise qui l'a rédigée, si l'IA a aidé ou non, combien de faits "
         "viennent de chaque type de source (jamais leur contenu) et qui l'a validée, avec la date. Elle s'ajoute à la "
         "fin du fichier. La joindre ou non est votre décision, surtout si le règlement interdit ou encadre l'usage de "
         "l'IA : lisez-le d'abord. « Rédiger sans IA » empêche toute rédaction par l'IA pour ce dossier ; une partie "
         "déjà préparée avec l'IA reste à réécrire vous-même si le règlement l'exige.")
INTRODUCTION = ("Pour chaque partie du dossier, cette page indique l'entreprise qui l'a rédigée, si un outil "
                "d'intelligence artificielle a aidé à la rédaction, le nombre de faits relevés par type de source et "
                "qui l'a validée, avec la date.")
LEGENDE = ("Les faits sont les chiffres, noms, certifications, références, effectifs, matériels et délais relevés dans "
           "le texte de chaque partie. La page dit où chacun est écrit : un document ou une déclaration de l'entreprise "
           "qui a rédigé la partie, une source publique, son estimation, un calcul à partir de ces faits, ou le dossier "
           "de l'acheteur. Elle ne dit pas qu'un fait est exact et ne reproduit aucune source : le candidat reste "
           "responsable de son offre.")
COLONNES = ["Partie", "Rédigée par", "Aide de l'IA", "Faits et sources", "Validée"]

# Types de source affichés (dans cet ordre) : le compteur commun de la vague 4 (`atelier_groupement.compteurs`)
# et, pour les parties de l'organisation qui exporte, « déclaré par un membre du groupement » à part.
TYPES = (("documents", "tiré de ses documents", "tirés de ses documents"),
         ("declare", "déclaré par l'entreprise", "déclarés par l'entreprise"),
         ("partenaire", "déclaré par un membre du groupement", "déclarés par un membre du groupement"),
         ("public", "de source publique", "de source publique"),
         ("estimation", "selon son estimation", "selon son estimation"),
         ("calcul", "calculé à partir de ces faits", "calculés à partir de ces faits"),
         ("acheteur", "tiré du dossier de l'acheteur", "tirés du dossier de l'acheteur"))
CLES = tuple(k for k, _u, _p in TYPES)
_TYPE = {fs.T_DOCUMENTS: "documents", fs.T_JUSTIFICATIF: "documents", fs.T_DECLARE: "declare", fs.T_VOUS: "declare",
         fs.T_PARTENAIRE: "partenaire", fs.T_PUBLIC: "public", fs.T_ESTIMATION: "estimation", fs.T_CALCUL: "calcul",
         fs.T_ACHETEUR: "acheteur"}

_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
         "novembre", "décembre")


def case() -> dict:
    """Ce que l'écran montre à l'export : la case, décochée par défaut, et sa bulle (i)."""
    return {"libelle": LIBELLE_CASE, "bulle": BULLE, "par_defaut": False}


# ── Dates, nombres, noms ─────────────────────────────────────────────────────────────

def _jour(dt) -> Optional[datetime]:
    """La date de Paris d'un instant enregistré en UTC (sans fuseau en base)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:       # noqa: BLE001
        return dt


def date_fr(dt) -> str:
    d = _jour(dt)
    if d is None:
        return ""
    return f"{'1er' if d.day == 1 else d.day} {_MOIS[d.month - 1]} {d.year}"


def _iso_jour(dt) -> Optional[str]:
    d = _jour(dt)
    return d.date().isoformat() if d is not None else None


def _n(n: int, un: str, des: str) -> str:
    return f"{n} {un if n <= 1 else des}"


def _et(noms: list) -> str:
    noms = [x for x in noms if x]
    if not noms:
        return ""
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def _nom(s: str, n: int = 160) -> str:
    return at._flat(s)[:n]


# ── Faits : des nombres, jamais leur contenu ─────────────────────────────────────────

def compter(faits) -> dict:
    """{avec_source, par_type: {documents, declare, partenaire, public, estimation, calcul, acheteur}, sans_source,
    relus} d'une liste de faits de l'organisation qui exporte (forme de A). Les engagements à confirmer ne sont pas
    des faits (comme `faits_sources.bilan`)."""
    par = {k: 0 for k in CLES}
    avec, sans, relus = 0, 0, 0
    for x in faits or []:
        if not isinstance(x, dict):
            continue
        if x.get("statut") == fs.AVEC_SOURCE:
            t = _TYPE.get(str((x.get("source") or {}).get("type") or ""))
            if t:
                par[t] += 1
                avec += 1
            continue
        if x.get("type") == fs.ENGAGEMENT:
            continue
        if x.get("statut") == far.RELU:
            relus += 1
        elif x.get("statut") == far.A_RELIRE:
            sans += max(1, int(x.get("nombre") or 1)) if x.get("type") == far.RESTE else 1
    return {"avec_source": avec, "par_type": par, "sans_source": sans, "relus": relus}


def _depuis_compteurs(c: dict) -> dict:
    """Le compteur COMMUN d'un texte de partenaire (vague 4) dans la forme de la page. Ce qu'il a relu lui-même
    n'en fait pas partie (compte privé, jamais transmis)."""
    par = {k: 0 for k in CLES}
    src = c.get("par_type") if isinstance(c.get("par_type"), dict) else {}
    for k in CLES:
        try:
            par[k] = max(0, int(src.get(k) or 0))
        except (TypeError, ValueError):
            par[k] = 0
    try:
        sans = max(0, int(c.get("a_relire") or 0))
    except (TypeError, ValueError):
        sans = 0
    return {"avec_source": sum(par.values()), "par_type": par, "sans_source": sans, "relus": None}


def libelle_faits(f: Optional[dict]) -> str:
    if not f:
        return "—"
    n = int(f.get("avec_source") or 0)
    par = f.get("par_type") or {}
    det = [_n(int(par.get(k) or 0), un, des) for k, un, des in TYPES if int(par.get(k) or 0) > 0]
    relus = f.get("relus")
    if not n and not relus and not int(f.get("sans_source") or 0) and relus is not None:
        # Rien de relevé, et on le sait (partie de l'organisation qui exporte). Pour la partie d'un partenaire, ce
        # qu'il a relu lui-même n'est pas transmis : on ne dit que ce qu'on sait.
        return "Aucun fait relevé"
    out = (_n(n, "fait relié à une source", "faits reliés à une source") + (" : " + ", ".join(det) if det else "")
           if n else "Aucun fait relié à une source")
    if relus:
        out += " ; " + _n(int(relus), "fait relu par l'entreprise, sans autre source",
                          "faits relus par l'entreprise, sans autre source")
    if int(f.get("sans_source") or 0):
        out += " ; " + _n(int(f["sans_source"]), "fait sans source retrouvée", "faits sans source retrouvée")
    return out


# ── Une ligne par partie ──────────────────────────────────────────────────────────────

def _base_ia(db, v: DossierSectionVersion) -> Optional[bool]:
    if not v.base_version_id:
        return None
    b = db.get(DossierSectionVersion, v.base_version_id)
    return bool(b.ia) if b is not None and b.section_id == v.section_id else None


def _ia(db, v: Optional[DossierSectionVersion]) -> tuple:
    if v is None or not (v.texte or "").strip():
        return None, "—"
    if not v.ia:
        return False, "Non"
    if v.origine == at.HARMONISE and _base_ia(db, v) is False:
        return True, "Oui, pour une phrase de transition"
    return True, "Oui"


class _Noms:
    """Noms d'ENTREPRISE (jamais de personne) : le chef de file et chaque partenaire."""

    def __init__(self, db, ctx: dict):
        self.db = db
        self.chef = _nom(ctx.get("entreprise") or "") or "Le candidat"
        self._inv = {}

    def partenaire(self, invite_id: Optional[int]) -> str:
        if not invite_id:
            return "Un partenaire du groupement"
        if invite_id not in self._inv:
            from app.services import atelier_groupement as ag
            inv = self.db.get(ProjectInvite, invite_id)
            nom = ag.nom_partenaire(inv, ag._contribution(self.db, invite_id)) if inv is not None else ""
            self._inv[invite_id] = _nom(nom) or "Un partenaire du groupement"
        return self._inv[invite_id]


def _redigee_par(db, s: DossierSection, v: Optional[DossierSectionVersion], noms: _Noms) -> tuple:
    """(libellé, clé de l'auteur pour le résumé : « chef », « invitation:<id> » ou « groupement »)."""
    if at.est_generee(s):
        lib = ("Le groupement, d'après sa convention" if s.source_plan == at.GEN_ORGANISATION else
               "Le groupement, d'après les parts des membres")
        return lib, "groupement"
    if s.author_kind != at.AUTEUR_INVITATION:
        return noms.chef, "chef"
    nom = noms.partenaire(s.author_invite_id)
    cle = f"invitation:{s.author_invite_id}"
    if v is None or not bool(v.partage):
        return nom, cle
    from app.services import atelier_groupement as ag
    if v.ecrit_par != ag.ECRIT_PAR_CHEF:
        return nom, cle
    if ag._avant(db, s, v) is None:
        # Le chef de file l'a écrite à la place du partenaire : sa contribution réelle.
        return noms.chef, "chef"
    if v.origine == at.HARMONISE:
        return f"{nom} ; phrase de transition ajoutée par {noms.chef}", cle
    return f"{nom} ; modifiée par {noms.chef}", cle


def _faits(s: DossierSection, v: Optional[DossierSectionVersion], faits_de) -> tuple:
    if at.est_generee(s):
        return None, ("Repris de la convention de groupement" if s.source_plan == at.GEN_ORGANISATION else
                      "Repris des parts déclarées par les membres")
    if v is None or not (v.texte or "").strip():
        return None, "—"
    if bool(getattr(v, "partage", False)):
        from app.services import atelier_groupement as ag
        c = v.compteurs if isinstance(v.compteurs, dict) else ag.compteurs(v.faits or [])
        f = _depuis_compteurs(c)
    else:
        f = compter(faits_de(v) if faits_de else (v.faits or []))
    return f, libelle_faits(f)


def _validee(db, project, dossier, s: DossierSection, v: Optional[DossierSectionVersion], noms: _Noms) -> dict:
    out = {"validee": False, "validee_par": "", "validee_le": None, "validee_libelle": "Non validée"}
    if v is None or s.validated_version_id != v.id or s.statut != at.VALIDE:
        return out
    if at.est_generee(s):
        from app.services import atelier_assemblage as asm
        from app.services import atelier_groupement as ag
        if asm.statut(db, s) != ag.VALIDEE:
            return out
        if s.source_plan == at.GEN_ORGANISATION:
            par = noms.chef
        else:
            vals = asm.qfq_validations(db, project, dossier, s)
            par = _et([noms.chef if x.get("invite_id") is None else noms.partenaire(x.get("invite_id"))
                       for x in vals if x.get("statut") == "valide"]) or noms.chef
    elif s.author_kind == at.AUTEUR_INVITATION:
        par = noms.partenaire(s.author_invite_id)        # le partenaire valide sa partie, lui seul
    else:
        par = noms.chef
    le = date_fr(s.validated_at)
    return {"validee": True, "validee_par": par, "validee_le": _iso_jour(s.validated_at),
            "validee_libelle": f"Par {par}" + (f", le {le}" if le else "")}


def page(db, project, dossier, sections: list, courantes: dict, ctx: dict, faits_de=None) -> dict:
    """La page, telle que l'export l'écrit et que l'écran la montre avant. `courantes` et `ctx` sont ceux de
    l'export (même texte, même mention IA) ; `faits_de` : les faits tels que l'export les lit."""
    noms = _Noms(db, ctx)
    rangs = {x.get("id"): x for x in ctx.get("sections") or []}
    lignes, auteurs = [], {}
    for s in sections:
        x = rangs.get(s.id) or {"numero": "", "intitule": s.intitule}
        v = courantes.get(s.id)
        redigee, cle = _redigee_par(db, s, v, noms)
        ia, ia_lib = _ia(db, v)
        f, f_lib = _faits(s, v, faits_de)
        ligne = {"section_id": s.id, "partie": ax.titre_section(x), "redigee_par": redigee, "ia": ia,
                 "ia_libelle": ia_lib, "faits": f, "faits_libelle": f_lib}
        ligne.update(_validee(db, project, dossier, s, v, noms))
        lignes.append(ligne)
        if cle == "groupement":
            nom_a = "le groupement (convention et parts des membres)"
        elif cle == "chef":
            nom_a = noms.chef
        else:
            nom_a = noms.partenaire(s.author_invite_id)
        auteurs.setdefault(cle, [nom_a, 0])[1] += 1
    avec_texte = [x for x in lignes if x["ia"] is not None]
    n_ia = sum(1 for x in avec_texte if x["ia"])
    resume = [(f"Parties préparées avec l'aide de l'IA : {n_ia} sur {len(lignes)}." if n_ia else
               "Aucune partie n'a été préparée avec l'aide de l'IA.")]
    if ctx.get("ia"):
        resume.append(f"Le fichier porte dans ses propriétés la mention « {ax.IA_MENTION} ».")
    sia = at.mode_sans_ia(dossier)
    if sia:
        le = sia.get("le")
        try:
            jour = date_fr(datetime.fromisoformat(str(le))) if le else ""
        except ValueError:
            jour = ""
        resume.append("L'entreprise a choisi de rédiger ce dossier sans IA" + (f" à partir du {jour}." if jour else "."))
    if len(auteurs) > 1 or any(k != "chef" for k in auteurs):
        # Le chef de file d'abord, puis chaque partenaire (dans l'ordre du plan), puis les parties tirées du groupement.
        ordre = sorted(auteurs, key=lambda k: 0 if k == "chef" else (2 if k == "groupement" else 1))
        resume.append("Parties rédigées : " + " ; ".join(f"{auteurs[k][0]}, {auteurs[k][1]}" for k in ordre) + ".")
    n_val = sum(1 for x in lignes if x["validee"])
    resume.append(f"Parties validées : {n_val} sur {len(lignes)}.")
    return {"titre": TITRE, "introduction": INTRODUCTION, "resume": resume, "colonnes": list(COLONNES),
            "lignes": lignes, "legende": LEGENDE, "parties": len(lignes), "parties_ia": n_ia,
            "parties_validees": n_val, "mention_ia": ax.IA_MENTION if ctx.get("ia") else ""}


def avertissements(dossier, p: dict) -> list:
    """Ce que l'écran dit AVANT de joindre la page (rien de tout cela n'entre dans le fichier)."""
    out = []
    nv = p["parties"] - p["parties_validees"]
    if nv:
        out.append({"code": "non_validees",
                    "message": (f"{nv} partie{'s' if nv > 1 else ''} non validée{'s' if nv > 1 else ''} : la page "
                                "le dira. Validez-les d'abord si vous voulez joindre la page.")})
    sans = sum(int((x.get("faits") or {}).get("sans_source") or 0) for x in p["lignes"])
    if sans:
        out.append({"code": "sans_source",
                    "message": (f"{sans} fait{'s' if sans > 1 else ''} sans source retrouvée : la page le dira.")})
    lims = at._limites_doc(dossier)
    pages = [x for x in (lims.get("document") or []) if isinstance(x, dict) and x.get("type") == "pages"
             and isinstance(x.get("valeur"), (int, float))]
    if pages:
        v = pages[0]["valeur"]
        v = int(v) if float(v).is_integer() else v
        out.append({"code": "limite_pages",
                    "message": (f"Le règlement limite le dossier à {at._fmt(v)} page{'s' if v > 1 else ''} : cette "
                                "page s'ajoute à la fin du fichier et n'entre pas dans le compteur.")})
    return out


MSG_INDISPONIBLE = ("La page « Comment ce dossier a été préparé » n'a pas pu être préparée pour le moment : "
                    "réessayez, ou exportez sans elle.")


def page_ou_erreur(db, project, dossier, sections: list, courantes: dict, ctx: dict, faits_de=None) -> dict:
    """La page, ou 503 : jamais un fichier exporté SANS la page que le client a demandée."""
    try:
        return page(db, project, dossier, sections, courantes, ctx, faits_de=faits_de)
    except at.AtelierError:
        raise
    except Exception as e:      # noqa: BLE001
        at.logger.warning("atelier : page « Comment ce dossier a été préparé » impossible (dossier %s) : %s",
                          getattr(dossier, "id", "?"), type(e).__name__)
        raise at.AtelierError(503, "page_preparation_indisponible", MSG_INDISPONIBLE)


def apercu(db, project, dossier, lecteur) -> dict:
    """GET …/preparation : la page telle que l'export l'écrirait maintenant (même texte commun, mêmes faits lus,
    sans IA), ce que l'écran en dit, et la case."""
    at._rafraichir_groupement(db, project, dossier)
    sections = at.sections_actives(db, dossier)
    cour = at.versions_communes(db, sections, lecteur)          # jamais le brouillon d'un autre auteur
    ctx = at.contexte_rendu(db, project, dossier, sections, cour, avec_logo=False)
    p = page_ou_erreur(db, project, dossier, sections, cour, ctx, faits_de=at.faits_lus(db, dossier, project, cour))
    return {"page": p, "avertissements": avertissements(dossier, p), "case": case()}
