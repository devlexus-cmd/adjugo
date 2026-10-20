"""
Prise en main (réorganisation de l'interface, vague 2b, chantier B1 ; étude « organisation du logiciel », § 7.1 à 7.3).
Contrat : docs/REORGANISATION_V2B.md, section B1.

1. « Vos premiers pas » : la liste d'activation de l'accueil, pendant PREMIERS_PAS_JOURS jours après la création du
   compte. Chaque tâche commence par un verbe et n'a que trois statuts (Pas commencé · En cours · Terminé) ; chacune
   est terminée selon une condition LUE dans les données de l'organisation, jamais cochée à la main ni devinée :

   | Tâche (clé)  | Terminée quand                                                   | En cours quand                        |
   |--------------|------------------------------------------------------------------|---------------------------------------|
   | dire         | métier, zone et montant porté seul dits (un montant, ou « Je ne  | une ou deux des trois réponses         |
   |              | sais pas ») — app/routers/criteria_v2.ce_que_je_cherche_dit       |                                       |
   | suivre       | 3 marchés dans Mes marchés (hors corbeille)                      | 1 ou 2                                |
   | lire         | 1 marché dont le dossier complet a été lu                        | un dossier importé, pas encore lu     |
   | plusieurs    | 1 invitation envoyée, ou le profil publié sur le réseau Adjugo   | un profil enregistré, pas publié       |
   | dossiers     | 3 dossiers de présentation dans Mon savoir-faire                 | 1 ou 2                                |

   L'ancienne étape « Lancez votre première recherche » (validée seulement après une analyse) n'existe plus. La
   tâche « dossiers » vit avec la fonction qui la fait (rédaction, vague 3 : import dans Mon savoir-faire, fiches
   proposées), en ligne. Démonstration : jamais de premiers pas (vitrine en lecture guidée).
2. La carte « Faites-vous trouver pour des groupements » : proposée après l'inscription ou l'acceptation d'une
   invitation, gardée sur le serveur (`users.suggestion_reseau`) pour ne plus se perdre (la page ouverte par le lien
   de confirmation, un autre appareil) ; fermée, elle ne revient qu'à la prochaine proposition.

État gardé SUR LE SERVEUR (migration c5priseenmain) : `users.premiers_pas_replie`, `users.suggestion_reseau`. Rien ne
dépend du navigateur. Aucun accès à la matière d'un partenaire : seulement des comptes de l'organisation elle-même.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

PREMIERS_PAS_JOURS = 30          # durée d'affichage de la liste (étude, § 7.1 [S14]) — sans rapport avec l'essai
SUIVRE_N = 3
DOSSIERS_N = 3
TACHES = ("dire", "suivre", "lire", "plusieurs", "dossiers")
STATUTS = ("pas_commence", "en_cours", "termine")
SUGGESTION_A_MONTRER = "a_montrer"
SUGGESTION_FERMEE = "fermee"
DOSSIER_DU_MARCHE = "DCE"        # dossier rangé du marché (app/services/dossier.py), affiché « Dossier du marché »
KIND_DOSSIER_PRESENTATION = "memoire"   # Mon savoir-faire : « Dossier de présentation » (clé stockée inchangée)


def _statut(fait: int, sur: int) -> str:
    return "termine" if fait >= sur else ("en_cours" if fait > 0 else "pas_commence")


def _utc(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def fin_premiers_pas(user) -> Optional[datetime]:
    """Jusqu'à quand la liste s'affiche : création du compte + PREMIERS_PAS_JOURS jours (None : date inconnue)."""
    c = _utc(getattr(user, "created_at", None))
    return c + timedelta(days=PREMIERS_PAS_JOURS) if c else None


def etat_profil_reseau(db, user, owner: Optional[int] = None) -> str:
    """Le profil partenaire de l'organisation sur le réseau Adjugo : "publie", "en_attente" (de validation par Adjugo),
    "brouillon" (enregistré, pas publié) ou "aucun". Seulement le sien : jamais celui d'une autre entreprise."""
    from app.core.org import data_owner_id
    from app.services.partner_network import VALIDATION_PENDING, own_profile
    prof = own_profile(db, owner if owner is not None else data_owner_id(user, db))
    if prof is None:
        return "aucun"
    if prof.visible:
        return "publie"
    return "en_attente" if (prof.validation_status or "") == VALIDATION_PENDING else "brouillon"


def taches(db, user) -> list:
    """Les tâches de la liste d'activation, chacune avec son statut LU dans les données de l'organisation."""
    from app.core.org import data_owner_id, member_ids
    from app.models import Document, KnowledgeDoc, Project, ProjectInvite
    from app.routers.criteria_v2 import ce_que_je_cherche_dit

    owner, ids = data_owner_id(user, db), member_ids(user, db)
    out = []

    dit = ce_que_je_cherche_dit(db, owner)
    n = sum(1 for k in ("metier", "zone", "montant") if dit[k])
    out.append({"k": "dire", "statut": _statut(n, 3), "fait": n, "sur": 3,
                "manque": [k for k in ("metier", "zone", "montant") if not dit[k]]})

    projets = (db.query(Project.id, Project.status, Project.ai_analysis)
               .filter(Project.user_id.in_(ids), Project.deleted_at.is_(None))
               .order_by(Project.created_at.desc(), Project.id.desc()).all())
    out.append({"k": "suivre", "statut": _statut(len(projets), SUIVRE_N), "fait": min(len(projets), SUIVRE_N),
                "sur": SUIVRE_N})

    lu = any(isinstance(a, dict) and a.get("dce_available") for _, _, a in projets)
    if lu:
        st = "termine"
    else:
        importe = bool(projets) and db.query(Document.id).filter(
            Document.project_id.in_([p for p, _, _ in projets]), Document.user_id.in_(ids),
            Document.folder == DOSSIER_DU_MARCHE, Document.deleted_at.is_(None)).first() is not None
        st = "en_cours" if importe else "pas_commence"
    # Le marché à ouvrir : le plus récent dont le dossier n'est pas lu (une carte « À venir » n'a pas encore de dossier).
    a_lire = next((p for p, s, a in projets
                   if not (isinstance(a, dict) and a.get("dce_available")) and getattr(s, "value", s) != "suivi"), None)
    out.append({"k": "lire", "statut": st, "projet": None if lu else a_lire})

    invite = db.query(ProjectInvite.id).filter(ProjectInvite.owner_id.in_(ids)).first() is not None
    profil = etat_profil_reseau(db, user, owner)
    st = "termine" if (invite or profil == "publie") else ("en_cours" if profil != "aucun" else "pas_commence")
    out.append({"k": "plusieurs", "statut": st, "invitation": invite, "profil": profil})

    n = (db.query(KnowledgeDoc.id).filter(KnowledgeDoc.user_id.in_(ids),
                                          KnowledgeDoc.kind == KIND_DOSSIER_PRESENTATION).count())
    out.append({"k": "dossiers", "statut": _statut(n, DOSSIERS_N), "fait": min(n, DOSSIERS_N), "sur": DOSSIERS_N})
    return out


def premiers_pas(db, user, maintenant: Optional[datetime] = None) -> dict:
    """« Vos premiers pas » : visible pendant PREMIERS_PAS_JOURS jours après la création du compte, tant qu'une tâche
    n'est pas terminée ; jamais pour la démonstration. Hors de la période, aucune tâche n'est calculée."""
    from app.services.demo_search import is_demo
    fin = fin_premiers_pas(user)
    maintenant = _utc(maintenant) or datetime.now(timezone.utc)
    base = {"visible": False, "replie": bool(getattr(user, "premiers_pas_replie", False)),
            "jusqu_au": fin.date().isoformat() if fin else None, "taches": [], "n_terminees": 0, "n_total": 0}
    if is_demo(user) or fin is None or maintenant >= fin:
        return base
    t = taches(db, user)
    n_ok = sum(1 for x in t if x["statut"] == "termine")
    return {**base, "visible": n_ok < len(t), "taches": t, "n_terminees": n_ok, "n_total": len(t)}


def replier(db, user, replie: bool) -> None:
    user.premiers_pas_replie = bool(replie)
    db.commit()


# ── La carte « Faites-vous trouver pour des groupements » ────────────────────────────────────────────────────────────

def proposer_suggestion_reseau(db, user) -> Optional[dict]:
    """Après l'inscription ou l'acceptation d'une invitation : la suggestion d'INTERFACE (jamais un courriel), si
    l'organisation n'a pas de profil publié. Elle est notée sur le serveur, pour s'afficher aussi dans un autre onglet
    ou sur un autre appareil, jusqu'à ce qu'on la ferme ou qu'on la suive."""
    from app.services.partner_network import suggest_profile
    s = suggest_profile(db, user)
    if s and getattr(user, "suggestion_reseau", "") != SUGGESTION_A_MONTRER:
        user.suggestion_reseau = SUGGESTION_A_MONTRER
        db.commit()
    return s


def suggestion_reseau(db, user) -> Optional[dict]:
    """La carte à montrer (None : rien). Un profil publié depuis, ou en attente de validation, l'éteint."""
    if (getattr(user, "suggestion_reseau", "") or "") != SUGGESTION_A_MONTRER:
        return None
    from app.services.partner_network import suggest_profile
    return suggest_profile(db, user)


def fermer_suggestion_reseau(db, user) -> None:
    if (getattr(user, "suggestion_reseau", "") or "") != SUGGESTION_FERMEE:
        user.suggestion_reseau = SUGGESTION_FERMEE
        db.commit()


def etat(db, user) -> dict:
    """GET /api/prise-en-main : la liste, la carte à montrer, et l'état du profil réseau de l'organisation (les états
    vides de Mes marchés ne proposent « Publier mon profil » que s'il n'est ni publié ni en attente)."""
    return {"premiers_pas": premiers_pas(db, user), "suggestion_reseau": suggestion_reseau(db, user),
            "profil_reseau": etat_profil_reseau(db, user)}
