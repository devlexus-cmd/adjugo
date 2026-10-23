"""
« Mes preuves » (rédaction, vague 3, E1) : REPRISE de ce que l'entreprise a déjà saisi ailleurs
dans Adjugo, pour ne rien ressaisir.

Ce qui est repris (étude § 6.7, E1) :
  • le profil de l'entreprise (« Mon entreprise ») : collaborateurs (→ « Équipe »), références,
    qualifications, effectif et chiffres d'affaires (→ « Chiffres clés ») ;
  • les références de son profil du réseau de partenaires ;
  • les justificatifs rangés en « Qualifications » dans « Mes documents » (coffre-fort).

Règles (doctrine § 7) :
  • rien n'est repris sans l'utilisateur : `candidats()` montre ce qui peut l'être, il coche,
    `reprendre()` crée seulement ce qu'il a coché (« déclaré par vous », ou « justificatif
    déposé » pour un document du coffre-fort) ;
  • AUCUNE PERTE : les données d'origine ne sont jamais modifiées ni supprimées ;
  • AUCUN DOUBLON : un élément déjà présent dans « Mes preuves » — même fiche, même intitulé
    (même après modification des autres champs), ou même justificatif — n'est jamais repris
    deux fois ; deux origines qui disent la même chose (profil et réseau) n'en font qu'une ;
  • le client ne fournit que les CLÉS des éléments cochés : le contenu est toujours relu ici ;
  • aucune IA, aucun appel réseau.
"""
import hashlib
import re
from datetime import date, datetime
from typing import Optional

from app.models import Company, Document, DocCategory, PartnerProfile, Preuve, User
from app.services import preuves as pv

ENTREPRISE, RESEAU, COFFRE = "entreprise", "reseau", "documents"
PROVENANCES = {ENTREPRISE: "Mon entreprise (Identité)", RESEAU: "Mon profil partenaire (Réseau Adjugo)",
               COFFRE: "Mes documents"}

# Le champ qui NOMME la fiche (« même intitulé » = même fiche, quoi qu'en disent les autres champs).
PRINCIPAL = {pv.REFERENCE: "objet", pv.QUALIFICATION: "nom", pv.SALARIE: "nom", pv.MATERIEL: "designation",
             pv.CHIFFRE_CLE: "libelle"}

MSG_FONCTION = "Indiquez sa fonction dans « Mon entreprise » pour la reprendre."


def _fold(s) -> str:
    from app.services.faits_a_relire import fold
    return fold(s)


def cle_souple(nature: str, valeur: dict) -> str:
    return f"{nature}|{_fold((valeur or {}).get(PRINCIPAL.get(nature, '')) or '')}"


def cle_intitule(nature: str, intitule) -> str:
    """La clé « même intitulé » d'un élément du profil, à partir de son seul intitulé."""
    return cle_souple(nature, {PRINCIPAL.get(nature, ""): str(intitule or "").strip()})


# Une fiche RETIRÉE ne fait taire le profil que si c'était la déclaration de l'utilisateur lui-même : il
# a repris l'élément du profil, ou l'a saisi dans « Mes preuves », puis l'a retiré (« ne plus s'en
# servir » : une qualification expirée ne revient pas par le profil). Une proposition d'un ancien dossier
# (I) écartée, acceptée ou non, ne fait jamais taire la déclaration actuelle du profil (« Effectif : 8 »
# d'un mémoire de 2019 retiré : l'effectif de 12 du profil reste remis et reprenable).
ORIGINES_QUI_GOUVERNENT_RETIREES = ("profil", "saisie")


def _gouverne(p: Preuve) -> bool:
    return p.statut == pv.ACCEPTEE or (p.statut == pv.RETIREE and p.origine in ORIGINES_QUI_GOUVERNENT_RETIREES)


def cles_gerees(db, owner_id: int) -> set:
    """Clés « même intitulé » des éléments que « Mes preuves » GOUVERNE désormais (vague 3, ensemble) :
    fiches acceptées (utilisables, expirées ou sans source), et fiches retirées qui reprenaient le
    profil (`ORIGINES_QUI_GOUVERNENT_RETIREES`). Un élément du profil qui a sa fiche n'est plus remis à
    la rédaction depuis le profil : sa fiche décide (remise [F#] si elle est utilisable ; rien si elle
    est retirée, expirée ou sans source). Une fiche seulement PROPOSÉE (lecture d'un ancien dossier, I)
    ne gouverne rien, ni une proposition écartée : la déclaration du profil reste remise."""
    return {cle_souple(p.nature, p.valeur or {})
            for p in pv._q_org(db, owner_id).filter(Preuve.statut.in_([pv.ACCEPTEE, pv.RETIREE])).all()
            if _gouverne(p)}


def _cle(provenance: str, nature: str, valeur: dict, document_id=None) -> str:
    base = f"{provenance}|{cle_souple(nature, valeur)}|{document_id or ''}"
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _date(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v or "").strip()[:10])
    except ValueError:
        return None


def _propre(nature: str, brut: dict) -> tuple:
    """(valeur nettoyée, message) : un champ invalide (année hors bornes, montant illisible…) est
    écarté plutôt que de bloquer toute la fiche ; un champ obligatoire manquant → (None, raison)."""
    brut = {k: v for k, v in (brut or {}).items() if v not in (None, "")}
    for _ in range(len(brut) + 1):
        try:
            return pv.valider_valeur(nature, brut), ""
        except pv.PreuveError as e:
            champ = e.extra.get("champ")
            if e.code == "champ_invalide" and champ in brut:
                brut.pop(champ)
                continue
            if e.code == "champ_requis":
                return None, (MSG_FONCTION if nature == pv.SALARIE and "fonction" in (e.extra.get("champs") or [])
                              else e.message)
            return None, e.message
    return None, "Fiche illisible."


def _nom_fichier(nom: str) -> str:
    """« Certificat_Qualibat-2025.pdf » → « Certificat Qualibat 2025 » (le nom tel que déposé)."""
    s = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", str(nom or "").strip())
    s = re.sub(r"[_]+|(?<=\w)-(?=\w)", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:200]


def _texte(nature: str, valeur: dict, fin) -> str:
    """Le texte de la fiche (celui de « Mes preuves »), lisible même s'il manque la fonction."""
    t = pv.texte_de(nature, valeur, fin)
    return re.sub(r",\s*$", "", re.sub(r",\s+(?=;)", " ", t))


# ── Ce qui existe déjà ailleurs ──────────────────────────────────────────────────────

def _depuis_entreprise(comp: Optional[Company]) -> list:
    out = []
    if comp is None:
        return out
    for m in (comp.team or []):
        if isinstance(m, dict) and str(m.get("nom") or "").strip():
            out.append((pv.SALARIE, {"nom": m.get("nom"), "fonction": m.get("fonction"),
                                     "qualifications": m.get("qualifications"),
                                     "chantiers": m.get("references") or m.get("chantiers")}, None))
    for r in (comp.references or []):
        if isinstance(r, str):
            r = {"intitule": r}
        if not isinstance(r, dict):
            continue
        objet = r.get("intitule") or r.get("name") or r.get("objet")
        if not str(objet or "").strip():
            continue
        out.append((pv.REFERENCE, {"objet": objet, "acheteur": r.get("client") or r.get("acheteur"),
                                   "lieu": r.get("lieu"), "annee": r.get("annee") or r.get("year"),
                                   "montant_ht": (r.get("montant") if r.get("montant") not in (None, "")
                                                  else r.get("value") if r.get("value") not in (None, "")
                                                  else r.get("montant_ht")),
                                   "description": r.get("description")}, None))
    for q in (comp.qualifications or []):
        fin = None
        if isinstance(q, dict):
            nom, detail, fin = q.get("name") or q.get("nom"), q.get("detail"), _date(q.get("expiration"))
        else:
            nom, detail = q, None
        if str(nom or "").strip():
            out.append((pv.QUALIFICATION, {"nom": nom, "detail": detail}, fin))
    if comp.effectif:
        out.append((pv.CHIFFRE_CLE, {"libelle": "Effectif", "valeur": comp.effectif, "unite": "personnes"}, None))
    for lib, v in (("Chiffre d'affaires N-1", comp.ca_n1), ("Chiffre d'affaires N-2", comp.ca_n2),
                   ("Chiffre d'affaires N-3", comp.ca_n3)):
        if v:
            out.append((pv.CHIFFRE_CLE, {"libelle": lib, "valeur": v, "unite": "€"}, None))
    return out


def _depuis_reseau(prof: Optional[PartnerProfile]) -> list:
    out = []
    for r in ((prof.references_publiques if prof is not None else None) or []):
        if isinstance(r, dict) and str(r.get("intitule") or "").strip():
            out.append((pv.REFERENCE, {"objet": r.get("intitule"), "acheteur": r.get("client"),
                                       "annee": r.get("annee")}, None))
    return out


def _existant(db, owner_id: int) -> tuple:
    """(empreintes, clés souples, justificatifs liés) des preuves de l'organisation (tous statuts), sauf
    une proposition d'un ancien dossier écartée (retirée sans reprendre le profil) : elle ne rend pas
    l'élément du profil « déjà dans vos preuves » (même règle que `cles_gerees`)."""
    emp, souples, docs = set(), set(), set()
    for p in pv._q_org(db, owner_id).all():
        if p.statut == pv.RETIREE and not _gouverne(p):
            continue
        if p.empreinte:
            emp.add(p.empreinte)
        souples.add(cle_souple(p.nature, p.valeur or {}))
        if p.source_document_id:
            docs.add(p.source_document_id)
    return emp, souples, docs


def candidats(db, owner_id: int) -> list:
    """Ce qui peut être repris, dans l'ordre : profil de l'entreprise, profil du réseau, coffre-fort.
    Chaque élément : {cle, nature, nature_libelle, valeur, texte, type_source, source_libelle,
    date_fin_validite, provenance, provenance_libelle, deja, manque}. `deja` : déjà dans « Mes
    preuves » ; `manque` : ne peut pas être repris tel quel (et pourquoi)."""
    comp = db.query(Company).filter(Company.user_id == owner_id).first()
    prof = db.query(PartnerProfile).filter(PartnerProfile.user_id == owner_id).first()
    emp, souples, docs_lies = _existant(db, owner_id)
    out, vus = [], set()

    def _ajoute(provenance, nature, brut, fin, type_source=pv.DECLARE, source=None, document_id=None):
        valeur, manque = _propre(nature, brut)
        affiche = valeur if valeur is not None else {k: v for k, v in brut.items() if v not in (None, "")}
        souple = cle_souple(nature, affiche)
        if souple in vus:                      # deux origines qui disent la même chose : une seule fiche
            return
        vus.add(souple)
        deja = (souple in souples or (valeur is not None and pv.empreinte_de(nature, valeur) in emp)
                or (document_id is not None and document_id in docs_lies))
        lib = pv.LIB_JUSTIFICATIF if type_source == pv.DOCUMENTS else pv.LIB_DECLARE
        out.append({"cle": _cle(provenance, nature, affiche, document_id), "nature": nature,
                    "nature_libelle": pv.NATURE_LIBELLES[nature], "valeur": affiche,
                    "texte": _texte(nature, affiche, fin), "type_source": type_source, "source_libelle": lib,
                    "source": dict(source or {}), "date_fin_validite": fin.isoformat() if fin else None,
                    "provenance": provenance, "provenance_libelle": PROVENANCES[provenance],
                    "deja": bool(deja), "manque": "" if deja else manque,
                    "_valeur": valeur})

    for nature, brut, fin in _depuis_entreprise(comp):
        _ajoute(ENTREPRISE, nature, brut, fin)
    for nature, brut, fin in _depuis_reseau(prof):
        _ajoute(RESEAU, nature, brut, fin)
    mids = pv.membres(db, owner_id)
    for d in (db.query(Document).filter(Document.user_id.in_(mids), Document.category == DocCategory.qualifications,
                                        Document.deleted_at.is_(None), Document.parent_id.is_(None))
              .order_by(Document.created_at.asc(), Document.id.asc()).all()):
        nom = _nom_fichier(d.name)
        if nom:
            _ajoute(COFFRE, pv.QUALIFICATION, {"nom": nom}, d.expiration_date, type_source=pv.DOCUMENTS,
                    source={"document_id": d.id, "document_nom": d.name or ""}, document_id=d.id)
    return out


def apercu(db, owner_id: int) -> dict:
    """Pour l'écran : les éléments à reprendre (jamais ceux déjà présents), et combien le sont déjà."""
    cs = candidats(db, owner_id)
    return {"elements": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cs if not c["deja"]],
            "deja": sum(1 for c in cs if c["deja"]),
            "a_reprendre": sum(1 for c in cs if not c["deja"] and not c["manque"])}


def reprendre(db, owner_id: int, cles, user=None) -> dict:
    """Crée les preuves cochées (statut « acceptée » : l'utilisateur vient de les cocher, origine
    « profil »). Le contenu est relu ici, jamais pris du client. Un élément déjà présent (ou devenu
    présent entre l'aperçu et le clic) n'est pas recréé. Une seule transaction : la ligne du compte
    qui porte les données est verrouillée (Postgres), deux clics simultanés ne doublent rien."""
    voulues = {str(c) for c in (cles or []) if c}
    db.query(User.id).filter(User.id == owner_id).with_for_update().first()
    creees, deja, ignorees = [], 0, []
    for c in candidats(db, owner_id):
        if c["cle"] not in voulues:
            continue
        if c["deja"]:
            deja += 1
            continue
        if c["manque"] or c["_valeur"] is None:
            ignorees.append({"texte": c["texte"], "message": c["manque"] or "Fiche illisible."})
            continue
        source = {"document_id": c["source"]["document_id"]} if c["type_source"] == pv.DOCUMENTS else None
        try:
            p = pv.creer(db, owner_id, nature=c["nature"], valeur=c["_valeur"], type_source=c["type_source"],
                         source=source, date_fin_validite=c["date_fin_validite"], statut=pv.ACCEPTEE,
                         origine="profil", user=user, commit=False)
        except pv.PreuveError as e:
            if e.code == "trop_de_preuves":
                ignorees.append({"texte": c["texte"], "message": e.message})
                break
            ignorees.append({"texte": c["texte"], "message": e.message})
            continue
        creees.append(p)
    db.commit()
    for p in creees:
        db.refresh(p)
    return {"creees": creees, "deja": deja, "ignorees": ignorees}
