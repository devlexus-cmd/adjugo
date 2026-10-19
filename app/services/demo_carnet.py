"""
Compte de DÉMONSTRATION — le carnet de notes (rédaction, vague 6, F), sans IA ni réseau.

Les trois marchés déjà décidés de la vitrine (app/services/demo_seed.py, « Historique d'AO décidés ») reçoivent leurs
notes, FICTIVES et dites telles :
  • « Rénovation de couverture — gendarmerie de Limauzac » (PERDU, appel d'offres ouvert, donc procédure
    formalisée) : passage à « Perdu » noté, demande des notes marquée envoyée, courrier de l'acheteur FICTIF collé
    (bandeau en tête) et lu SANS IA par le vrai lecteur (app/services/carnet_notes.lire_courrier) : chaque note est
    « lue dans le courrier, validée par vous », avec sa ligne du courrier ; sous-critères ajoutés par l'utilisateur ;
  • « Réfection de toiture-terrasse — médiathèque d'Anjoumont » et « Couverture et zinguerie — école de Riquebach »
    (GAGNÉS, procédure adaptée) : notes saisies, sans note de l'offre retenue.
Ce qui en sort, sans rien coder en dur : « Où vous perdez des points » sur 3 marchés (moyenne en technique et en
prix ; l'environnement sur 2 marchés seulement, donc sans moyenne), le constat du marché perdu et, dans l'atelier du
marché « toiture », « La dernière fois, l'acheteur a écrit : … » sur ses parties.

Chaque ligne passe par la validation du carnet (`carnet_notes._ligne_in`) : un nombre qui ne serait pas dans sa ligne
du courrier serait gardé comme « saisi ». Appelé par demo_seed.ensure_demo dans sa propre transaction.
"""
import hashlib
import logging

logger = logging.getLogger("adjugo")

BANDEAU = ("Courrier fictif de démonstration : l'acheteur, le marché et les notes ne correspondent à aucune "
           "consultation réelle.")

COURRIER_LIMAUZAC = "\n".join([
    BANDEAU,
    "Objet : Rénovation de la couverture de la caserne de gendarmerie — motifs du rejet de votre offre",
    "Madame, Monsieur,",
    "Suite à votre demande, nous vous communiquons les notes obtenues par votre offre, classée en deuxième position.",
    "Critère 1 : Prix des prestations (60 %)",
    "Votre note : 52,8 / 60",
    "Note de l'offre retenue : 60 / 60",
    "Critère 2 : Valeur technique (40 %)",
    "Votre note : 31 / 40 — note de l'offre retenue : 30 / 40",
    "Sous-critère 2.1 Méthodologie et phasage en site sensible : 17 / 20 (offre retenue : 15 / 20)",
    "Appréciation : phasage précis, adapté aux contrôles d'accès du site.",
    "Sous-critère 2.2 Moyens humains et matériels : 8 / 10 (offre retenue : 8 / 10)",
    "Sous-critère 2.3 Gestion environnementale du chantier : 6 / 10 (offre retenue : 7 / 10)",
    "Appréciation : le tri des déchets est annoncé sans filière de valorisation ni taux visé.",
    "Nous vous prions d'agréer, Madame, Monsieur, nos salutations distinguées.",
])

# (début du nom du marché, statut attendu, dates, lignes saisies). « a1 », « a2 » : les critères lus par l'analyse
# du marché (details.criteres_attribution) ; « u1 »… : sous-critères ajoutés par l'utilisateur d'après le courrier.
_MARCHES = [
    ("Rénovation de couverture — gendarmerie de Limauzac", "perdu",
     {"perdu_le": "2024-07-08T09:30:00", "demande": "2024-07-09T08:15:00", "valide_le": "2024-07-16T14:05:00"},
     [{"cle": "a1", "critere": "Prix", "note": "52,8", "note_max": "60", "note_gagnant": "60"},
      {"cle": "a2", "critere": "Valeur technique", "note": "31", "note_max": "40", "note_gagnant": "30"},
      {"cle": "u1", "critere": "Méthodologie et phasage en site sensible", "parent": "a2", "poids": "20 points"},
      {"cle": "u2", "critere": "Moyens humains et matériels", "parent": "a2", "poids": "10 points"},
      {"cle": "u3", "critere": "Gestion environnementale du chantier", "parent": "a2", "poids": "10 points"}]),
    ("Réfection de toiture-terrasse — médiathèque d'Anjoumont", "gagne",
     {"valide_le": "2024-03-20T10:00:00"},
     [{"cle": "a1", "critere": "Valeur technique", "note": "51", "note_max": "60"},
      {"cle": "u1", "critere": "Méthodologie d'étanchéité et traitement des relevés", "parent": "a1",
       "note": "27", "note_max": "30", "commentaire": "Complexe d'étanchéité et relevés décrits avec précision."},
      {"cle": "u2", "critere": "Organisation du chantier en site occupé", "parent": "a1", "note": "18",
       "note_max": "20"},
      {"cle": "u3", "critere": "Gestion des déchets de chantier", "parent": "a1", "note": "6", "note_max": "10",
       "commentaire": "La valorisation des déchets est annoncée, sans filière désignée."},
      {"cle": "a2", "critere": "Prix", "note": "34", "note_max": "40"}]),
    ("Couverture et zinguerie — école de Riquebach", "gagne",
     {"valide_le": "2024-06-25T16:40:00"},
     [{"cle": "a1", "critere": "Valeur technique", "note": "41", "note_max": "50"},
      {"cle": "u1", "critere": "Méthodologie de couverture et de zinguerie", "parent": "a1", "note": "21",
       "note_max": "25"},
      {"cle": "u2", "critere": "Planning d'exécution hors période scolaire", "parent": "a1", "note": "13",
       "note_max": "15", "commentaire": "Planning crédible, calé sur les vacances scolaires."},
      {"cle": "u3", "critere": "Moyens humains et matériels affectés", "parent": "a1", "note": "7", "note_max": "10",
       "commentaire": "Encadrement bien décrit ; le matériel affecté est peu détaillé."},
      {"cle": "a2", "critere": "Prix", "note": "46", "note_max": "50"}]),
]


def seed_carnet(db, user) -> int:
    """Notes FICTIVES des trois marchés décidés de la vitrine ; renvoie le nombre de carnets écrits. Sans IA, sans
    réseau, sans fichier ; rejouable (le carnet est réécrit à l'identique)."""
    from app.models import Project
    from app.services import carnet_notes as cn
    projets = {p.name: p for p in db.query(Project).filter(Project.user_id == user.id).all()}
    n = 0
    for nom, statut, dates, lignes in _MARCHES:
        p = projets.get(nom)
        if p is None or cn._statut(p) != statut:
            continue
        courrier = COURRIER_LIMAUZAC if statut == "perdu" else ""
        props = cn.lire_courrier(courrier, [dict(x, critere=x["critere"]) for x in lignes])["propositions"] \
            if courrier else {}
        connus = {x["cle"]: x for x in cn.criteres_du_marche(p)["lignes"]}
        for x in lignes:
            connus.setdefault(x["cle"], {"cle": x["cle"], "critere": x["critere"], "parent": x.get("parent", ""),
                                         "poids": x.get("poids", "")})
        sortie = []
        for i, x in enumerate(lignes):
            entree = dict(x)
            pr = props.get(x["cle"])
            if pr:
                # Les valeurs du courrier, telles qu'écrites, avec leur ligne : « lue dans le courrier, validée par vous ».
                entree.update({k: pr[k] for k in ("note", "note_max", "note_gagnant", "extrait_note", "extrait_gagnant",
                                                  "commentaire") if pr.get(k)})
                entree["origine"] = cn.COURRIER
                entree["commentaire_du_courrier"] = bool(pr.get("commentaire"))
            ln = cn._ligne_in(entree, i, connus, courrier)
            if ln is not None:
                sortie.append(ln)
        c = {"schema": cn.SCHEMA, "rev": 1,
             "reponse": {"lignes": sortie, "valide_le": dates["valide_le"], "valide_par": user.id}}
        if statut == "perdu":
            c.update(perdu_le=dates["perdu_le"], perdu_par=user.id,
                     demande={"envoyee_le": dates["demande"], "par": user.id},
                     courrier={"texte": courrier, "colle_le": dates["valide_le"],
                               "empreinte": hashlib.sha256(courrier.encode("utf-8")).hexdigest()})
        p.carnet_notes = c
        n += 1
    db.commit()
    return n
