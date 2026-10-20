"""
Mesure d'usage de l'interface (réorganisation, vague 1, point 1.1 ; décision 17 de l'étude « organisation du
logiciel »).

Un événement par OUVERTURE D'ÉCRAN : l'application signale « l'écran X vient de s'ouvrir » et le serveur ajoute 1
au compteur (jour, écran). C'est tout ce qui est gardé :
  - aucune donnée personnelle : ni compte, ni organisation, ni adresse IP, ni appareil, ni heure précise ;
  - aucun outil tiers (pas de script de mesure d'audience, pas de cookie) ;
  - jamais montré aux clients ; lu par l'administrateur de la plateforme (GET /api/admin/mesures/ecrans) ;
  - la démonstration (session démo) ne compte pas, pour ne pas fausser la mesure pendant les présentations.

Pourquoi : `go()` ne change pas l'adresse de la page, donc une mesure d'audience ne voit qu'une page, /app. Avant et
après chaque vague de la réorganisation, on veut savoir quels écrans sont réellement ouverts (par exemple si
« Mes groupements » l'est jamais). Le jour est celui de Paris (lecture humaine).

Les écrans comptés sont une LISTE FERMÉE (`ECRANS`) : un nom inconnu est ignoré, ce qui borne la table et évite
qu'un appel fabriqué y écrive n'importe quoi. Toute nouvelle vue de l'application doit y être ajoutée
(tests/test_reorganisation_v1_socle.py le vérifie contre app.html). Contrat : docs/REORGANISATION_V1.md, § 1.1.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import MesureEcran

PARIS = ZoneInfo("Europe/Paris")

# Les vues de l'application (clé de `view` dans app.js, ouvertes par go() ou par l'ouverture d'un marché).
# Menu par rubriques (vague 1, 1.3) : « compte » (Réglages › Mon compte) est une vue ; « avenir » et « alertes » sont
# les onglets « À venir » et « Mes alertes » de Trouver des marchés, comptés à chaque affichage (« sourcing » compte
# chaque ouverture de Trouver des marchés, quel que soit l'onglet). Mes marchés en liste filtrable (vague 2a, A2) :
# « bilan » (Mes marchés › Bilan) est une vue ; « shared » et « consortiums » comptent les filtres « Où je suis
# partenaire » et « À plusieurs » de la liste (leurs anciens écrans, pour comparer avant et après). Vague 2a (A3) :
# « tarifs », l'onglet « Tarifs » de Mon entreprise, sorti d'« Identité » (une vue). Vague 2b (B2) : « exemple », le
# marché d'exemple (page à part, lecture seule) : son ouverture est comptée ici comme tout écran, sans compte ni
# organisation, jamais pour la démo — c'est la seule trace qu'il laisse.
ECRANS = frozenset({
    "dashboard", "sourcing", "amont", "pipeline", "aodetail", "atelier", "cotraitants", "reseau", "contacts",
    "documents", "kb", "company", "preuves", "criteria", "invoices", "consortiums", "shared", "sharedao",
    "team", "billing", "admin", "compte", "avenir", "alertes", "bilan", "tarifs", "exemple",
    # Vague 2b (B3) : « Voir ce que verra [partenaire] », sur la page du marché (/app/marches/<id>/apercu-partenaire).
    "apercu",
})

JOURS_MAX = 400          # relevé : au plus ~13 mois d'un coup
JOURS_DEFAUT = 30


def aujourd_hui() -> date:
    return datetime.now(PARIS).date()


def compter(db: Session, ecran: str, jour: date = None) -> bool:
    """Ajoute une ouverture de `ecran` au compteur du jour. Renvoie False (rien n'est écrit) pour un écran hors de
    la liste fermée. Une seule ligne par (jour, écran) : la première ouverture la crée, les suivantes l'augmentent."""
    if not isinstance(ecran, str) or ecran not in ECRANS:
        return False
    jour = jour or aujourd_hui()

    def _augmenter() -> int:
        return (db.query(MesureEcran)
                .filter(MesureEcran.jour == jour, MesureEcran.ecran == ecran)
                .update({MesureEcran.ouvertures: MesureEcran.ouvertures + 1}, synchronize_session=False))

    if _augmenter():
        db.commit()
        return True
    db.add(MesureEcran(jour=jour, ecran=ecran, ouvertures=1))
    try:
        db.commit()
    except IntegrityError:          # créée entre-temps par une autre requête : on augmente celle-là
        db.rollback()
        _augmenter()
        db.commit()
    return True


def releve(db: Session, jours: int = JOURS_DEFAUT, fin: date = None) -> dict:
    """Relevé pour l'administrateur : les `jours` derniers jours (jusqu'à `fin`, aujourd'hui par défaut). Chaque
    écran de la liste apparaît dans le total, même jamais ouvert (0) : c'est souvent ce qu'on cherche."""
    jours = max(1, min(int(jours or JOURS_DEFAUT), JOURS_MAX))
    fin = fin or aujourd_hui()
    debut = fin - timedelta(days=jours - 1)
    lignes = (db.query(MesureEcran)
              .filter(MesureEcran.jour >= debut, MesureEcran.jour <= fin)
              .order_by(MesureEcran.jour.asc(), MesureEcran.ecran.asc())
              .all())
    par_jour, total = {}, {e: 0 for e in ECRANS}
    for ln in lignes:
        j = par_jour.setdefault(ln.jour.isoformat(), {})
        j[ln.ecran] = j.get(ln.ecran, 0) + int(ln.ouvertures or 0)
        total[ln.ecran] = total.get(ln.ecran, 0) + int(ln.ouvertures or 0)
    return {
        "depuis": debut.isoformat(),
        "jusqu_au": fin.isoformat(),
        "jours": [{"jour": k, "ecrans": v, "total": sum(v.values())} for k, v in sorted(par_jour.items())],
        "par_ecran": [{"ecran": e, "ouvertures": n} for e, n in sorted(total.items(), key=lambda x: (-x[1], x[0]))],
        "total": sum(total.values()),
        "explication": ("Nombre d'ouvertures de chaque écran de l'application, par jour (heure de Paris). Aucune "
                        "donnée personnelle n'est gardée : ni compte, ni organisation, ni adresse. La démonstration "
                        "n'est pas comptée. Interne : jamais montré aux clients."),
    }
