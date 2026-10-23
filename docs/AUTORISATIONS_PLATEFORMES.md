# Autorisations des plateformes Atexo (Mégalis, PLACE)

Étude « moteur de recherche », décision 4 (a), validée par Eliot.

## Ce que fait Adjugo aujourd'hui

- **En-tête honnête.** Adjugo lit les plateformes sous le nom
  `AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)`. Il ne se fait plus passer pour un
  navigateur (`app/sourcing/sources/atexo.py`).
- **Rythme borné.** Une requête par seconde au plus vers une même plateforme (réglable par
  `ATEXO_INTERVALLE_MIN`), trois pages au plus par recherche, résultats gardés 20 minutes.
  Aucune connexion, aucun dossier téléchargé : seule la liste publique des consultations est lue.
- **PLACE suspendue.** `PLACE_ACTIF=0` par défaut : PLACE n'est plus interrogée (recherche, alertes,
  espace partenaire). L'écran de recherche le dit : « PLACE (État) : non consultée pour le moment ».
  Les avis de l'État publiés au BOAMP restent visibles.
- **Mégalis conservée**, ses conditions n'interdisant rien. Si Mégalis refuse l'en-tête honnête
  (réponse 401, 403, 406, 429 ou page de blocage), Adjugo **ne contourne pas** : la source passe
  « indisponible » pendant une heure, la recherche continue avec BOAMP et TED, et le journal
  l'écrit **une fois par heure au plus** :
  `Atexo Mégalis Bretagne refuse l'en-tête honnête d'Adjugo (…) : source marquée indisponible
  pendant 1 h, SANS contournement`.

## Ce qu'Eliot fait

1. Envoyer les deux courriels ci-dessous (Mégalis, puis l'éditeur de PLACE).
2. Surveiller le journal Railway : si la ligne ci-dessus apparaît, Mégalis bloque le robot honnête.
   C'est le scénario le plus coûteux (environ 7 consultations Mégalis sur 10 absentes du BOAMP,
   mesure indicative du 12/10) : relancer Mégalis sans attendre.
3. À réception d'une autorisation écrite de PLACE (ou d'un avis favorable de l'avocat), mettre
   `PLACE_ACTIF=1` dans Railway. Aucun déploiement n'est nécessaire.
4. Classer les réponses avec ce document (date, auteur, conditions posées).

## Brouillon 1 — Mégalis Bretagne

Destinataire : le contact indiqué sur marches.megalis.bretagne.bzh (page « Contact » ou mentions
légales). Adresse à vérifier avant l'envoi.

> **Objet : Demande d'autorisation de réutiliser la liste publique des consultations**
>
> Madame, Monsieur,
>
> Je dirige Adjugo (https://adjugo.pro), un service français qui aide les TPE et PME à repérer
> les marchés publics et à y répondre, seules ou à plusieurs.
>
> Nous affichons à nos utilisateurs les consultations publiques de votre plateforme (intitulé,
> acheteur, date limite et lien), en renvoyant toujours vers Mégalis pour le dossier et le dépôt.
> Nous lisons la liste sous un nom de robot explicite, AdjugoBot/1.0 (contact@adjugo.pro), au plus
> une requête par seconde, sans connexion ni téléchargement de dossiers.
>
> Pourriez-vous nous confirmer par écrit que cette réutilisation vous convient, et nous indiquer
> vos conditions (rythme, mention de la source, flux ou interface de données si vous en proposez) ?
> Nous suivrons vos indications et cesserons toute lecture sur simple demande.
>
> Je vous remercie par avance de votre réponse.
>
> Bien cordialement,
> Eliot Viegas, Adjugo
> contact@adjugo.pro

## Brouillon 2 — PLACE (marches-publics.gouv.fr)

Destinataire : l'AIFE, comme le prévoit l'étude. Avant l'envoi, vérifier dans les mentions
légales de marches-publics.gouv.fr qui édite aujourd'hui la plateforme (AIFE ou Direction des
achats de l'État) et écrire à l'adresse indiquée.

> **Objet : Demande d'autorisation de réutiliser les avis de consultation publiés sur PLACE**
>
> Madame, Monsieur,
>
> Je dirige Adjugo (https://adjugo.pro), un service français qui aide les TPE et PME à repérer
> les marchés publics et à y répondre, seules ou à plusieurs.
>
> Nous souhaitons afficher à nos utilisateurs les avis de consultation publics de PLACE
> (intitulé, acheteur, date limite et lien), en renvoyant toujours vers PLACE pour le dossier et
> le dépôt. Vos conditions d'utilisation encadrant la reprise du contenu, nous avons suspendu
> toute lecture de PLACE en attendant votre réponse.
>
> Pourriez-vous nous indiquer si cette réutilisation peut être autorisée, et à quelles conditions
> (rythme, mention de la source, flux ou interface de données si vous en proposez) ? Notre lecture
> se ferait sous un nom de robot explicite, AdjugoBot/1.0 (contact@adjugo.pro), au plus une
> requête par seconde, sans connexion ni téléchargement de dossiers.
>
> Je vous remercie par avance de votre réponse.
>
> Bien cordialement,
> Eliot Viegas, Adjugo
> contact@adjugo.pro
