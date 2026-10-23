"""
Compte de DÉMONSTRATION — l'entretien chantier (rédaction, vague 5, D), sans IA ni réseau.

seed_entretien(db, user, project, dossier, preuves) remplit l'entretien du marché « toiture » avec le VRAI moteur
déterministe (app/services/entretien_chantier.py : banque de questions, phrase du dossier retrouvée mot pour mot,
classement par le poids des critères), puis quelques réponses FICTIVES, comme un visiteur les aurait données :
  • « cohabitation avec les occupants » : une réponse écrite (déclaré par vous) ;
  • « chef de chantier » : une personne de « Mes preuves » (rubrique Équipe : son nom n'est jamais remis à l'IA) ;
  • « tri et filières des déchets » : une réponse écrite ;
  • « planning calé sur les périodes imposées » : passée — l'écran montre le « [À compléter : … ] » qu'elle laissera ;
les autres restent « à répondre ». Rien n'est écrit dans les textes déjà rédigés de l'atelier. Tout est fictif :
aucune entreprise, aucun lieu ni aucune personne réels. Appelé par demo_redaction.seed_redaction dans SA transaction
(aucun commit ici).
"""
import logging

logger = logging.getLogger("adjugo")

# Réponses fictives (code de la banque → réponse) ; la personne de l'équipe est résolue vers sa fiche réelle.
REPONSES = {
    "site_occupe": ("Zone de chantier clôturée côté cour arrière, séparée des cheminements des élèves ; accès des "
                    "compagnons et des livraisons par le portail technique ; point chaque lundi avec la direction de "
                    "l'école."),
    "dechets": ("Tri sur place en quatre bennes (bitume, métaux, bois, déchets non dangereux) ; évacuation vers la "
                "plateforme de tri de Bréhaut, avec un bordereau de suivi pour chaque enlèvement."),
}
EQUIPE = {"chef_chantier": "chef_equipe"}           # code → clé de la fiche « Équipe » (demo_redaction.seed_preuves)
PASSEES = ("periodes",)


def seed_entretien(db, user, project, dossier, preuves: dict) -> int:
    """Crée l'entretien du marché (questions proposées par la banque, sans IA) et quelques réponses fictives.
    Renvoie le nombre de questions. Idempotent par construction : la remise à neuf de la vitrine efface tout avant."""
    from app.core.org import member_ids
    from app.models import EntretienQuestion
    from app.services import entretien_chantier as ec
    props = ec.proposition(db, project, dossier, member_ids(user, db))
    n = 0
    for i, p in enumerate(props):
        motif = p["motif"] or {}
        r = EntretienQuestion(dossier_id=dossier.id, project_id=project.id, owner_id=dossier.owner_id, numero=i + 1,
                              code=p["code"], origine=ec.BANQUE, theme=p["theme"][:160],
                              question=p["question"][:ec.QUESTION_MAX], type_reponse=p["type_reponse"],
                              motif=(motif.get("phrase") or "")[:ec.MOTIF_MAX] or None,
                              motif_piece=(motif.get("piece") or "")[:200], ordre=i, adresse_kind=ec.ORG,
                              adresse_invite_id=None, adresse_choix=ec.PROPOSE, statut=ec.A_REPONDRE)
        if p["code"] in REPONSES:
            ec._appliquer(r, ec.REPONDUE, REPONSES[p["code"]], None, kind=ec.ORG, invite_id=None, user_id=user.id)
        elif p["code"] in EQUIPE and preuves.get(EQUIPE[p["code"]]) is not None:
            ec._appliquer(r, ec.REPONDUE, None, preuves[EQUIPE[p["code"]]].id, kind=ec.ORG, invite_id=None,
                          user_id=user.id)
        elif p["code"] in PASSEES:
            ec._appliquer(r, ec.SAUTEE, None, None, kind=ec.ORG, invite_id=None, user_id=user.id)
        db.add(r)
        n += 1
    db.flush()
    return n
