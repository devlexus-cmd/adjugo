"""
« Mes preuves » dans l'atelier du dossier de présentation (rédaction, vague 3, E1) : insérer une
référence, une qualification, du matériel, un chiffre clé ou un CV CHOISI dans une partie,
TEL QUEL, sans IA.

  • `bloc()` : le texte inséré, déterministe (Markdown simple de l'atelier : gras, listes), qui
    ne contient que les faits de la fiche — jamais son libellé de source, son numéro « F3 » ni
    rien d'interne (doctrine § 7, règle 7 : rien d'interne ne part chez l'acheteur) ;
  • `inserer()` : une NOUVELLE version de la partie (même chemin que « J'écris moi-même » :
    verrou, version de départ, longueur, faits « à relire » des anciennes versions gardés) ;
    seules les fiches UTILISABLES (acceptées, valables, source présente) s'insèrent ;
  • `refuser_cv_pour_ia()` : « Raccourcir » envoie le texte de la partie à l'IA ; une partie qui
    contient un CV de « Mes preuves » est refusée AVANT tout appel (décision 8a : un CV n'est
    jamais envoyé à l'IA, il est inséré tel quel).
"""
import re
from typing import Optional

from app.services import preuves as pv

_ROLES = {"seul": "Réalisé seul", "groupement_conjoint": "Réalisé en groupement conjoint",
          "groupement_solidaire": "Réalisé en groupement solidaire", "sous_traitant": "Réalisé en sous-traitance"}
_POSSESSION = {"propriete": "En propre", "location": "En location"}

MSG_CV = ("Cette partie contient le CV de {noms}, inséré depuis « Mes preuves » : Adjugo n'envoie jamais un "
          "CV à l'IA. Raccourcissez-la vous-même, ou retirez le CV le temps de raccourcir puis insérez-le de "
          "nouveau.")
MSG_AUTRE_MARCHE = "Cette estimation vaut pour un autre marché : Adjugo ne s'en sert pas ici."


def _ligne(v) -> str:
    """Une valeur sur une ligne : sans saut de ligne ni marque de gras (le gabarit reste lisible)."""
    s = str(v if v is not None else "").replace("**", "")
    parts = [re.sub(r"^[-*•]\s+", "", x.strip()) for x in s.split("\n")]
    s = " ; ".join(x for x in parts if x)
    return re.sub(r"[ \t]+", " ", s).strip(" ;")


def _paragraphes(v) -> list:
    return [x.replace("**", "").strip() for x in str(v or "").split("\n") if x.strip()]


def _date_fr(iso) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def lignes_cv(valeur: dict) -> list:
    """Les lignes « CV » d'une fiche « Équipe » (tout sauf le nom et la fonction)."""
    v = valeur or {}
    out = []
    if v.get("experience_annees") is not None:
        n = int(v["experience_annees"])
        out.append(f"Expérience : {n} an{'s' if n > 1 else ''}")
    if v.get("diplomes"):
        out.append(f"Diplômes : {_ligne(v['diplomes'])}")
    if v.get("qualifications"):
        out.append(f"Qualifications et habilitations : {_ligne(v['qualifications'])}")
    if v.get("chantiers"):
        out.append(f"Chantiers : {_ligne(v['chantiers'])}")
    return out


def bloc(nature: str, valeur: dict, date_fin_validite=None) -> str:
    """Le texte inséré dans la partie (Markdown de l'atelier), sans rien d'interne."""
    v = valeur or {}
    fin = _date_fr(date_fin_validite.isoformat() if hasattr(date_fin_validite, "isoformat") else date_fin_validite)
    tete, items, suite = "", [], []
    if nature == pv.REFERENCE:
        tete = _ligne(v.get("objet"))
        if v.get("acheteur"):
            items.append(f"Acheteur : {_ligne(v['acheteur'])}")
        if v.get("lieu"):
            items.append(f"Lieu : {_ligne(v['lieu'])}")
        if v.get("annee"):
            items.append(f"Année : {v['annee']}")
        if v.get("montant_ht") is not None:
            items.append(f"Montant : {pv._nombre(v['montant_ht'])} € HT")
        if v.get("role") in _ROLES:
            items.append(_ROLES[v["role"]])
        suite = _paragraphes(v.get("description"))
    elif nature == pv.QUALIFICATION:
        tete = _ligne(v.get("nom"))
        if v.get("organisme"):
            items.append(f"Délivrée par : {_ligne(v['organisme'])}")
        if v.get("numero"):
            items.append(f"Numéro : {_ligne(v['numero'])}")
        if fin:
            items.append(f"Valable jusqu'au {fin}")
        suite = _paragraphes(v.get("detail"))
    elif nature == pv.SALARIE:
        tete = f"{_ligne(v.get('nom'))}, {_ligne(v.get('fonction'))}"
        items = lignes_cv(v)
    elif nature == pv.MATERIEL:
        tete = _ligne(v.get("designation"))
        if v.get("quantite") is not None:
            items.append(f"Quantité : {v['quantite']}")
        if v.get("caracteristiques"):
            items.append(f"Caractéristiques : {_ligne(v['caracteristiques'])}")
        if v.get("possession") in _POSSESSION:
            items.append(_POSSESSION[v["possession"]])
    elif nature == pv.CHIFFRE_CLE:
        s = f"{_ligne(v.get('libelle'))} : {pv._nombre(v.get('valeur'))}"
        if v.get("unite"):
            s += f" {_ligne(v['unite'])}"
        if v.get("annee"):
            s += f" ({v['annee']})"
        return s
    out = [f"**{tete}**"] + [f"- {x}" for x in items]
    if suite:
        out += [""] + suite
    return "\n".join(out).strip()


def titre(nature: str, valeur: dict) -> str:
    v = valeur or {}
    if nature == pv.SALARIE:
        return f"{v.get('nom', '')}, {v.get('fonction', '')}"
    if nature == pv.CHIFFRE_CLE:
        return f"{v.get('libelle', '')} : {pv._nombre(v.get('valeur'))}" + (f" {v['unite']}" if v.get("unite") else "")
    from app.services.preuves_reprise import PRINCIPAL
    return str(v.get(PRINCIPAL.get(nature, ""), ""))


def fiches(db, owner_id: int, project_id: int) -> dict:
    """Ce que l'atelier d'UN marché peut insérer : les preuves utilisables pour ce marché (une
    estimation rattachée à un autre marché est écartée), avec le texte qui sera inséré ; et les
    fiches acceptées écartées, avec la raison (pour le dire)."""
    out = []
    for f in pv.faits_autorises(db, owner_id, project_id=project_id):
        out.append({"id": f["id"], "nature": f["nature"], "nature_libelle": f["nature_libelle"],
                    "titre": titre(f["nature"], f["valeur"]), "source_libelle": f["source_libelle"],
                    "a_reconfirmer": f["a_reconfirmer"], "date_fin_validite": f["date_fin_validite"],
                    "bloc": bloc(f["nature"], f["valeur"], f["date_fin_validite"])})
    ecartees = [{"id": x["id"], "nature": x["nature"], "texte": x["texte"], "message": x["message"]}
                for x in pv.faits_ecartes(db, owner_id)]
    return {"fiches": out, "ecartees": ecartees}


def _fiche_utilisable(db, owner_id: int, project_id: int, preuve_id) -> dict:
    from app.services.atelier import AtelierError
    try:
        pid = int(preuve_id)
    except (TypeError, ValueError):
        pid = None
    fait = next((f for f in pv.faits_autorises(db, owner_id, project_id=project_id) if f["id"] == pid), None)
    if fait is not None:
        return fait
    p = pv.get(db, owner_id, pid) if pid else None
    if p is None:
        raise AtelierError(404, "preuve_introuvable", "Preuve introuvable.")
    raison = pv.raison_non_utilisable(p, pv._Etat(db, owner_id, [p]))
    raise AtelierError(409, "preuve_non_utilisable", pv.RAISONS.get(raison) or MSG_AUTRE_MARCHE,
                       raison=raison or "autre_marche")


def inserer(db, ctx, section, lecteur, owner_id: int, project_id: int, preuve_id, base_version_id):
    """Ajoute la fiche, telle quelle, à la fin du texte de la partie : nouvelle version, sans IA."""
    from app.services import atelier as at
    fait = _fiche_utilisable(db, owner_id, project_id, preuve_id)
    cur = at.version_courante(db, section)
    texte = ((cur.texte or "") if cur is not None else "").rstrip()
    ajout = bloc(fait["nature"], fait["valeur"], fait["date_fin_validite"])
    return at.enregistrer_texte(db, ctx, section, lecteur, (texte + "\n\n" if texte else "") + ajout,
                                base_version_id)


# ── Aucun CV vers l'IA (décision 8a) ─────────────────────────────────────────────────

def _plat(s) -> str:
    from app.services.faits_a_relire import fold
    return re.sub(r"\s+", " ", fold(str(s or "").replace("**", "")).replace(" ;", ";")).strip()


def cv_presents(db, owner_id: int, texte: str) -> list:
    """Noms des personnes dont une ligne de CV (« Expérience : 15 ans », « Diplômes : … ») figure
    dans le texte. Toutes les fiches « Équipe » de l'organisation, quel que soit leur statut."""
    from app.models import Preuve
    plat = _plat(texte)
    if not plat:
        return []
    noms = []
    for p in (db.query(Preuve).filter(Preuve.owner_id == owner_id, Preuve.nature == pv.SALARIE,
                                      Preuve.statut != pv.SUPPRIMEE).order_by(Preuve.numero.asc()).all()):
        v = p.valeur or {}
        if any(len(_plat(x)) >= 10 and _plat(x) in plat for x in lignes_cv(v)):
            nom = str(v.get("nom") or "").strip()
            if nom and nom not in noms:
                noms.append(nom)
    return noms


def refuser_cv_pour_ia(db, owner_id: int, texte: Optional[str]) -> None:
    """Refuse d'envoyer à l'IA un texte qui contient un CV de « Mes preuves » (409)."""
    noms = cv_presents(db, owner_id, texte or "")
    if noms:
        from app.services.atelier import AtelierError
        raise AtelierError(409, "cv_dans_la_partie", MSG_CV.format(noms=", ".join(noms[:3])))
