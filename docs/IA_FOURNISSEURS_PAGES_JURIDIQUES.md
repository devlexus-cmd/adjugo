# Fournisseurs d'IA et pages juridiques — corrections à valider

Document de travail du 12/10/2026 (chantier R, routage de l'IA par tâche). **Rien de ce qui suit
n'est publié** : les pages `app/static/legal/*.html` et `docs/legal/*.md` n'ont pas été modifiées.
Eliot valide (ou corrige) chaque texte proposé, puis le publie lui-même.

Ce qui a changé dans le code, et qui rend ces corrections nécessaires :

- **Deux fournisseurs d'IA à la fois** dès qu'une clé Mistral est présente
  (`MISTRAL_API_KEY_ADJUGO`, ou `MISTRAL_API_KEY`) :
  - Mistral Large 4 lit et analyse les dossiers (analyse, lecture en deux temps, exigences,
    délibérations de la veille, renouvellements) ;
  - Claude Sonnet 5.5 (Anthropic) répond aux questions, rédige, remplit le questionnaire, chiffre,
    et sert le côté acheteur ;
  - chacun prend le relais de l'autre en cas de panne : un dossier peut donc partir chez l'un ou
    l'autre, quelle que soit la tâche.
- **Le texte injecté dans les pages** (`app/main.py`, `_ai_subprocessor_fragments`) est désormais
  exact. Il disait « Union européenne (France — api.mistral.ai) » et retirait toute mention de
  transfert, ce qui était faux. Il décrit maintenant les deux fournisseurs, le lieu de calcul du
  point d'accès Mistral **réellement utilisé**, les sous-traitants de Mistral et l'état de la
  désinscription de l'entraînement (voir § 6).
- **Restent faux, dans le texte fixe** de `dpa.html` et `securite.html` : « les contenus ne sont
  jamais utilisés pour entraîner un modèle d'IA ». C'est vrai chez Anthropic. C'est faux chez
  Mistral tant que la désinscription n'est pas faite sur le compte d'Adjugo.

---

## 1. Faits vérifiés (sources relues le 12/10/2026)

| Fait | Source |
|---|---|
| Large 4 : identifiant d'API `mistral-large-4`, préversion publique depuis le 06/10/2026, fenêtre de 1 000 000 de tokens. L'alias `mistral-large-latest` n'est pas Large 4. | Journal des modifications de Mistral (docs.mistral.ai/getting-started/changelog), fiche du modèle (docs.mistral.ai/models/mistral-large-4-0) |
| Prix de Large 4 : 1,36 $ en entrée, 4,18 $ en sortie, 0,14 $ en lecture du cache, par million de tokens. Prix de lancement à −50 % « pendant 2 semaines » (0,68 / 2,09 / 0,07). | docs.mistral.ai/inference/pricing, journal des modifications |
| Point d'accès UE : `https://api.eu.mistral.ai/v1`. Calcul dans des centres de données de l'UE et de l'AELE. Tarif : 1,1 × le prix de base. Ni lots, ni fichiers, ni agents. Disponibilité des modèles à vérifier par `models.list` sur ce point d'accès. | docs.mistral.ai/inference/regional-inference |
| Point d'accès UE : les données de fonctionnement du compte (configuration, clés, facturation, statistiques d'usage) peuvent être traitées hors de la zone. | idem |
| Point d'accès mondial `api.mistral.ai` : aucun engagement de lieu pour le calcul ; stockage dans l'UE par défaut. | Comparatif des API, § 5.1 [S16, S21] |
| Entraînement : l'API est concernée tant que la désinscription n'est pas faite. Réglage : console Mistral, menu **Admin > Privacy**, interrupteur **« Anonymous improvement data »**. Seuls les clients Vibe Enterprise sont désinscrits par défaut, et les réglages Vibe et API sont distincts. | help.mistral.ai, article 455207 (mis à jour le 03/09/2026) |
| Conservation : 30 jours. Le « zéro conservation » est à la discrétion de Mistral, sur demande. | DPA de Mistral (en vigueur le 27/07/2026) [S17, S22] |
| Transferts : clauses contractuelles types. Liste des sous-traitants sur trust.mistral.ai/subprocessors, dont Microsoft, CoreWeave et Cloudflare. | DPA de Mistral ; comparatif § 5.1 [S18]. La page des sous-traitants est rendue en JavaScript : **à relire à la main** avant publication. |
| Anthropic, API directe : stockage aux États-Unis, calcul « global ». Aucune option UE. Contenus jamais utilisés pour l'entraînement sans permission. Conservation 30 jours. | Comparatif § 5.1 [S1 à S4] |

---

## 2. `dpa.html` (accord de sous-traitance)

### 2.1 Annexe 2 — mesures de sécurité, puce « modèle d'IA »

Texte actuel :

> modèle d'IA ({{AI_PROVIDER}}, appelé via une API) : les contenus qui lui sont envoyés ne sont
> jamais utilisés pour entraîner un modèle ; la conservation éventuelle par le fournisseur est
> encadrée par ses conditions ;

Texte proposé (à publier une fois la désinscription faite chez Mistral, § 5, étape 1) :

> modèles d'IA ({{AI_PROVIDER}}, appelés via une API) : les contenus qui leur sont envoyés ne sont
> pas utilisés pour entraîner un modèle (Anthropic : jamais sans autorisation ; Mistral AI :
> utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur) ; les noms
> des salariés sont remplacés par des étiquettes avant tout envoi ; la conservation par chaque
> fournisseur (30 jours au plus, pour la détection des abus) est encadrée par ses conditions
> applicables à l'API ;

Variante, **si la page doit être publiée avant la désinscription** (déconseillé) :

> … ne sont pas utilisés pour entraîner un modèle chez Anthropic ; chez Mistral AI, cette
> utilisation est active par défaut et sa désactivation, à la charge de l'Éditeur, est en cours ; …

### 2.2 Annexe 3 — paragraphe sous le tableau des sous-traitants

Texte actuel :

> Fournisseur d'IA : les contenus envoyés au modèle ne sont jamais utilisés pour entraîner un
> modèle d'IA ; leur conservation éventuelle par {{AI_PROVIDER}} est encadrée par ses conditions
> applicables à l'API ({{AI_PRODUCT}}).

Texte proposé :

> Fournisseurs d'IA : Anthropic (Claude API) répond aux questions et rédige ; Mistral AI
> (La Plateforme) lit et analyse les dossiers ; chacun prend le relais de l'autre en cas de panne.
> Les contenus envoyés ne sont pas utilisés pour entraîner un modèle d'IA (désinscription faite
> chez Mistral AI sur le compte de l'Éditeur). Mistral AI recourt à ses propres sous-traitants, dont
> Microsoft, CoreWeave et Cloudflare, sociétés de droit américain (liste :
> trust.mistral.ai/subprocessors). Le lieu de calcul de Mistral AI est indiqué dans le tableau
> ci-dessus. La conservation par chaque fournisseur est encadrée par ses conditions applicables à
> l'API.

Le tableau lui-même n'a pas à changer : sa ligne « IA » est remplie par le serveur (§ 6).

### 2.3 Article 6 — un nouveau sous-traitant ultérieur

L'article 6 engage l'Éditeur à **informer le Client de tout ajout de sous-traitant ultérieur, avec
un préavis raisonnable**, pour lui permettre d'émettre des objections. Mistral AI est un ajout.

Ce qui en découle :

- **Avant que Mistral reçoive des données de clients**, prévenir les clients existants, puis
  attendre la fin du préavis.
- La clé `MISTRAL_API_KEY_ADJUGO` est **déjà dans Railway**. Déployer ce code tel quel enverrait
  aussitôt les analyses chez Mistral.
- Pour déployer sans attendre, poser d'abord `LLM_PROVIDER=anthropic` : toutes les tâches restent
  chez Anthropic (Claude Sonnet 5.5), sans secours vers Mistral. Retirer la variable à la fin du
  préavis.

Proposition de message aux clients (à adapter, **à envoyer par Eliot**) :

> Objet : Adjugo — nouveau sous-traitant pour la lecture des dossiers (Mistral AI)
>
> Bonjour,
>
> À partir du [date, au moins 30 jours plus tard], Adjugo confiera la lecture et l'analyse des
> dossiers de consultation à Mistral AI (société française), point d'accès européen, avec un calcul
> dans l'Union européenne. Les questions et la rédaction restent chez Anthropic. Chacun pourra
> prendre le relais de l'autre en cas de panne.
>
> Vos contenus ne servent pas à entraîner leurs modèles. Les noms de vos salariés sont remplacés
> par des étiquettes avant tout envoi. La liste à jour des sous-traitants figure dans notre accord
> de sous-traitance : https://adjugo.pro/dpa.
>
> Vous pouvez nous faire part d'une objection d'ici le [date] en répondant à ce message.

---

## 3. `securite.html` (page « Sécurité »)

### 3.1 Encadré « L'essentiel » (haut de page)

Texte actuel :

> … Et vos contenus ne sont **jamais utilisés pour entraîner un modèle d'IA**, ni le nôtre, ni
> celui d'un tiers.

Texte proposé :

> … Et vos contenus ne sont **pas utilisés pour entraîner les modèles d'IA** de nos fournisseurs
> (Anthropic, et Mistral AI pour la lecture des dossiers, chez qui nous avons désactivé cette
> utilisation).

### 3.2 Section 3 « Le modèle d'IA et vos données », première puce

Texte actuel :

> **Aucun entraînement sur vos données** : les contenus envoyés au modèle ne sont **jamais utilisés
> pour entraîner un modèle d'IA**. Leur conservation éventuelle par le fournisseur de l'IA est
> encadrée par ses conditions applicables à l'API ; le fournisseur et sa localisation figurent dans
> le DPA (annexe 3).

Texte proposé :

> **Aucun entraînement sur vos données** : deux fournisseurs d'IA travaillent pour Adjugo.
> Anthropic (Claude) répond aux questions et rédige. Mistral AI lit et analyse les dossiers, avec
> un calcul dans l'Union européenne quand son point d'accès européen sert le modèle. Les contenus
> qui leur sont envoyés ne servent pas à entraîner leurs modèles : jamais sans autorisation chez
> Anthropic, et désactivation faite sur notre compte chez Mistral AI. Chacun peut prendre le relais
> de l'autre en cas de panne. Les deux conservent les contenus 30 jours au plus. Fournisseurs,
> sous-traitants et lieux de calcul : voir le DPA (annexe 3).

### 3.3 Section 3, deuxième puce « Strict nécessaire » (à revoir aussi)

Texte actuel :

> **Strict nécessaire** : on ne transmet au modèle que les extraits utiles à l'analyse demandée, pas
> l'ensemble de votre espace.

Avec la lecture intégrale, **tout le dossier du marché** est remis à l'IA : d'un seul tenant, ou
pièce par pièce, et ses règlements et cadres de réponse en entier pour la rédaction. La première
moitié de la phrase n'est plus exacte. Texte proposé :

> **Strict nécessaire** : on transmet à l'IA le dossier du marché que vous analysez (lu en entier,
> pour ne rien manquer) et, pour la rédaction, les extraits utiles de vos documents. Jamais
> l'ensemble de votre espace. Les noms de vos salariés sont remplacés par des étiquettes avant tout
> envoi.

---

## 4. Politique de confidentialité (`docs/legal/politique-confidentialite.md`, § 6 et § 7)

La ligne « IA » du tableau des sous-traitants (fournisseur, produit, localisation) et la phrase sur
les transferts (§ 7) sont remplies par le serveur, et désormais exactes (§ 6 du présent document).
Restent à corriger dans le texte fixe :

### 4.1 Tableau du § 6, ligne « IA », colonne « Données concernées »

Texte actuel :

> contenus soumis à l'analyse (extraits de DCE, données d'entreprise)

Texte proposé (la lecture intégrale remet tout le dossier du marché) :

> dossiers de consultation analysés (lus en entier), questions posées, données d'entreprise utiles
> à la rédaction (noms des salariés remplacés par des étiquettes avant tout envoi)

### 4.2 Nouveau paragraphe, juste sous le tableau du § 6

> **Fournisseurs d'IA.** La lecture et l'analyse des dossiers sont confiées à Mistral AI ; les
> questions et la rédaction à Anthropic ; chacun peut prendre le relais de l'autre en cas de panne
> (fournisseurs effectivement sollicités et lieux de calcul : tableau ci-dessus). Les contenus
> envoyés ne servent pas à entraîner leurs modèles : jamais sans autorisation chez Anthropic, et
> désactivation faite sur le compte de l'Éditeur chez Mistral AI. Chaque fournisseur conserve les
> contenus 30 jours au plus, pour détecter les abus. Mistral AI recourt à ses propres
> sous-traitants, dont Microsoft, CoreWeave et Cloudflare (liste : trust.mistral.ai/subprocessors).

(À publier seulement après la désinscription chez Mistral, § 5, étape 1.)

### 4.3 § 7, liste des garanties appropriées

Ajouter une puce :

> - pour Mistral AI : ses clauses contractuelles types et celles qu'il conclut avec ses propres
>   sous-traitants (accord de sous-traitance de Mistral AI, en vigueur depuis le 27/07/2026).

---

## 5. Ordre des opérations (Eliot)

1. **Console Mistral (admin.mistral.ai)** :
   - désactiver **Admin > Privacy > « Anonymous improvement data »** ;
   - demander l'option **« zéro conservation »** (à la discrétion de Mistral) ;
   - relire trust.mistral.ai/subprocessors (page en JavaScript, non lue automatiquement).
2. **Prévenir les clients** (§ 2.3). Jusqu'à la fin du préavis, laisser `LLM_PROVIDER=anthropic`
   dans Railway.
3. **Publier les corrections** du présent document :
   - `dpa.html` et `securite.html` (§ 2 et § 3 ci-dessus) : directement dans `app/static/legal/`
     (pas de source Markdown) ;
   - politique de confidentialité (§ 4 ci-dessus) : dans `docs/legal/politique-confidentialite.md`,
     puis `python scripts/build_legal.py`.
4. Poser **`MISTRAL_ENTRAINEMENT_DESACTIVE=1`** dans Railway. Les pages disent alors
   « désactivée par l'Éditeur sur son compte » (§ 6 ci-dessous).
5. **Retirer `LLM_PROVIDER`** (ou la mettre à `auto`) à la fin du préavis, puis redémarrer.
6. Ouvrir **`GET /api/admin/ia/diagnostic`** (compte administrateur) et vérifier :
   - `fournisseurs.mistral.variable` = `MISTRAL_API_KEY_ADJUGO` ;
   - `large4_sur_ue` = `true` ;
   - `point_acces.zone` = `ue` ;
   - aucun message en attente.

   Si `large4_sur_ue` vaut `false` (Large 4 encore absent du point d'accès européen), Mistral passe
   par le point d'accès mondial, **sans engagement de lieu de calcul**. Les pages le disent alors
   d'elles-mêmes. Pour l'éviter : `MISTRAL_POINT_ACCES=ue` (les analyses partent alors chez Claude
   tant que le modèle n'y est pas servi), ou attendre.

---

## 6. Ce que le serveur injecte désormais (pour mémoire)

Les pages contiennent des repères remplis par le serveur à chaque affichage (`{{AI_PROVIDER}}`,
`{{AI_PRODUCT}}`, `{{AI_LOCATION_FULL}}`, `{{AI_LOCATION_SHORT}}`, `{{AI_TRANSFER_MENTION}}`) :

| Configuration | Fournisseur(s) | Lieu indiqué | Transferts |
|---|---|---|---|
| Sans clé Mistral, ou `LLM_PROVIDER=anthropic` | Anthropic, PBC (Claude API) | États-Unis (API standard api.anthropic.com — encadré par CCT) | Anthropic, États-Unis |
| Clé Mistral, point d'accès UE (Large 4 servi sur l'UE, vérifié par `models.list`) | Anthropic, PBC et Mistral AI | Anthropic : États-Unis (CCT) ; Mistral AI : calcul dans l'UE et l'AELE (api.eu.mistral.ai), données de fonctionnement du compte possiblement hors zone ; sous-traitants de droit américain (Microsoft, CoreWeave, Cloudflare), CCT ; état de la désinscription | Anthropic (États-Unis) ; Mistral AI et ses sous-traitants de droit américain (calcul dans l'UE) |
| Clé Mistral, point d'accès mondial | idem | Mistral AI : **sans engagement de lieu de calcul**, possiblement hors UE ; stockage dans l'UE par défaut | idem, « calcul possiblement hors de l'Union européenne » |
| `LLM_PROVIDER=mistral` | Mistral AI (La Plateforme) | Mistral seul, selon le point d'accès | Mistral AI et ses sous-traitants |

État de la désinscription :

- sans `MISTRAL_ENTRAINEMENT_DESACTIVE=1` : « utilisation des contenus pour l'amélioration des
  modèles de Mistral AI : active par défaut chez ce fournisseur, sa désactivation étant à la
  charge du titulaire du compte (l'Éditeur), non encore confirmée » ;
- avec cette variable : « … désactivée par l'Éditeur sur son compte ».

Le mot « souverain » et l'indicateur `"sovereign": true` ont été retirés : la route publique
`/api/llm/info` renvoie `"sovereign": false`. Formulations honnêtes possibles (comparatif, § 7.3) :

- « calcul de la lecture des dossiers dans l'Union européenne » : seulement avec le point d'accès UE ;
- « IA hébergée en France » : jamais avec ces deux fournisseurs ;
- l'application elle-même (Railway, Cloudflare R2, Sentry) reste chez des sociétés américaines.
