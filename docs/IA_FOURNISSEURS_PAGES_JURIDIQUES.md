# Fournisseurs d'IA et pages juridiques — corrections à valider

Document de travail du 12/10/2026 (chantier R, routage de l'IA par tâche). **Rien de ce qui suit
n'est publié**, sauf la puce « Strict nécessaire » de la page Sécurité (§ 3.3, publiée le 12/10/2026,
indépendante de Mistral) : les autres textes de `app/static/legal/*.html` et `docs/legal/*.md` n'ont
pas été modifiés par ce chantier.
Eliot valide (ou corrige) chaque texte proposé, puis le publie lui-même.

Ce qui a changé dans le code, et qui rend ces corrections nécessaires :

- **Deux fournisseurs d'IA à la fois** dès que Mistral est **activé**, c'est-à-dire avec les
  trois réunis : une clé (`MISTRAL_API_KEY_ADJUGO`, ou `MISTRAL_API_KEY`), `MISTRAL_ACTIF=1` et
  `MISTRAL_ENTRAINEMENT_DESACTIVE=1`. La clé seule (déjà dans Railway) n'envoie **rien** chez
  Mistral : tout part chez Claude Sonnet 5.5, et les pages ne parlent que d'Anthropic.
  - Mistral Large 4 lit et analyse les dossiers (analyse, lecture en deux temps, exigences,
    délibérations de la veille, renouvellements) ;
  - Claude Sonnet 5.5 (Anthropic) répond aux questions, rédige, remplit le questionnaire, chiffre,
    et sert le côté acheteur ;
  - chacun prend le relais de l'autre en cas de panne : un dossier peut donc partir chez l'un ou
    l'autre, quelle que soit la tâche.
- **Le texte injecté dans les pages** (`app/main.py`, `_ai_subprocessor_fragments`) a changé, et
  part avec le code : **à relire avant de déployer** (§ 6). Il disait « Union européenne (France —
  api.mistral.ai) » et retirait toute mention de transfert, ce qui était faux. Il décrit maintenant
  les deux fournisseurs, le rôle et les relais de chacun **tirés du routage effectif**, le lieu de
  calcul du point d'accès Mistral **réellement utilisé** (UE et AELE), les sous-traitants de Mistral
  et la désinscription de l'entraînement. Pour Anthropic, il dit aussi désormais, **y compris dans
  la configuration actuelle de la production** : stockage aux États-Unis, calcul possiblement hors
  des États-Unis (l'API est appelée sans `inference_geo`, donc en routage « global » : « Inference
  may run in any available geography », documentation Anthropic sur la résidence des données). Il
  disait « États-Unis » seulement, ce qui n'était pas exact.
- **Le texte fixe** de `dpa.html` et `securite.html` (« les contenus ne sont jamais utilisés pour
  entraîner un modèle d'IA ») n'est plus faux dans aucune configuration : Mistral ne reçoit rien
  sans la désinscription. Il reste **incomplet** (il ne dit pas que Mistral lit les dossiers, ni
  la durée de conservation) : textes proposés ci-dessous, à publier **le jour de l'activation**
  (§ 5).

---

## 1. Faits vérifiés (sources relues le 12/10/2026)

| Fait | Source |
|---|---|
| Large 4 : identifiant d'API `mistral-large-4`, préversion publique depuis le 06/10/2026, fenêtre de 1 000 000 de tokens. L'alias `mistral-large-latest` n'est pas Large 4. | Journal des modifications de Mistral (docs.mistral.ai/getting-started/changelog), fiche du modèle (docs.mistral.ai/models/mistral-large-4-0) |
| Prix de Large 4 : 1,36 $ en entrée, 4,18 $ en sortie, 0,14 $ en lecture du cache, par million de tokens. Prix de lancement à −50 % « pendant 2 semaines » (0,68 / 2,09 / 0,07). | docs.mistral.ai/inference/pricing, journal des modifications |
| Point d'accès UE : `https://api.eu.mistral.ai/v1`. Calcul dans des centres de données de l'UE et de l'AELE (« Multiple data centers in EU and EFTA countries ») : jamais « UE » seule. Tarif : 1,1 × le prix de base. Ni lots, ni fichiers, ni agents. Disponibilité des modèles à vérifier par `models.list` sur ce point d'accès. | docs.mistral.ai/inference/regional-inference |
| Point d'accès UE : les données de fonctionnement du compte (configuration, clés, facturation, statistiques d'usage) peuvent être traitées hors de la zone. | idem |
| Point d'accès mondial `api.mistral.ai` : aucun engagement de lieu pour le calcul ; stockage dans l'UE par défaut. | Comparatif des API, § 5.1 [S16, S21] |
| Entraînement : l'API est concernée tant que la désinscription n'est pas faite. Réglage : console Mistral, menu **Admin > Privacy**, interrupteur **« Anonymous improvement data »**. Seuls les clients Vibe Enterprise sont désinscrits par défaut, et les réglages Vibe et API sont distincts. | help.mistral.ai, article 455207 (mis à jour le 03/09/2026) |
| Conservation chez Mistral : entrées et sorties gardées le temps de produire la réponse, puis 30 jours glissants pour la détection des abus, pour l'API de conversation qu'utilise Adjugo (sauf « zéro conservation », à la discrétion de Mistral, sur demande). Les API d'agents et de réglage fin gardent plus longtemps (Adjugo ne s'en sert pas). Réserve générale du DPA : sauf obligation légale (§ 3.1 a). | Politique de confidentialité de Mistral (clause citée : « … for thirty (30) rolling days to monitor abuse (unless zero data retention is activated) ») ; DPA de Mistral, § 2.3 et § 3.1 (en vigueur le 27/07/2026) [S17, S22]. **À relire à la main** dans la politique de Mistral avant publication (page non lue en entier automatiquement). |
| Transferts : clauses contractuelles types. Liste des sous-traitants sur trust.mistral.ai/subprocessors, dont Microsoft, CoreWeave et Cloudflare. | DPA de Mistral ; comparatif § 5.1 [S18]. La page des sous-traitants est rendue en JavaScript : **à relire à la main** avant publication. |
| Anthropic, API directe : stockage aux États-Unis (seule zone de stockage proposée) ; calcul « global » par défaut, possiblement hors des États-Unis (« us » seulement avec `inference_geo: "us"`, + 10 %, non utilisé). Aucune option UE. Contenus jamais utilisés pour l'entraînement sans permission. | platform.claude.com/docs/en/manage-claude/data-residency (relue le 12/10/2026) ; comparatif § 5.1 [S1 à S4] |
| Conservation chez Anthropic : entrées et sorties effacées sous 30 jours **en règle générale** ; **jusqu'à 2 ans** pour les contenus signalés pour non-respect de ses règles d'usage (et jusqu'à 7 ans pour les scores de classification de sécurité). | privacy.claude.com, article 7996866 (relu le 12/10/2026) : « We retain inputs and outputs for up to 2 years and trust and safety classification scores for up to 7 years if your chat is flagged » ; comparatif § 5.1 [S2] |

---

## 2. `dpa.html` (accord de sous-traitance)

### 2.1 Annexe 2 — mesures de sécurité, puce « modèle d'IA »

Texte actuel :

> modèle d'IA ({{AI_PROVIDER}}, appelé via une API) : les contenus qui lui sont envoyés ne sont
> jamais utilisés pour entraîner un modèle ; la conservation éventuelle par le fournisseur est
> encadrée par ses conditions ;

Texte proposé (à publier le jour de l'activation de Mistral, § 5, étape 3) :

> modèles d'IA ({{AI_PROVIDER}}, appelés via une API) : les contenus qui leur sont envoyés ne sont
> pas utilisés pour entraîner un modèle (Anthropic : jamais sans autorisation ; Mistral AI :
> utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur) ; les noms
> des salariés sont remplacés par des étiquettes avant tout envoi ; la conservation par chaque
> fournisseur est encadrée par ses conditions applicables à l'API (Anthropic : 30 jours en règle
> générale, jusqu'à 2 ans pour les contenus signalés pour non-respect de ses règles d'usage ;
> Mistral AI : 30 jours glissants, pour la détection des abus) ;

(L'ancienne variante « désinscription en cours » est sans objet : le code n'envoie rien chez
Mistral tant que la désinscription n'est pas confirmée.)

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
- La clé `MISTRAL_API_KEY_ADJUGO` est **déjà dans Railway**, mais elle ne suffit plus : le code
  n'envoie rien chez Mistral sans `MISTRAL_ACTIF=1` **et** `MISTRAL_ENTRAINEMENT_DESACTIVE=1`.
  Déployer ce code tel quel laisse donc tout chez Anthropic (Claude Sonnet 5.5), et les pages ne
  parlent que d'Anthropic. Rien à poser pour déployer.
- `MISTRAL_ACTIF=1` se pose **à la fin du préavis**, le jour où les textes ci-dessous sont publiés
  (§ 5).

Proposition de message aux clients (à adapter, **à envoyer par Eliot**) :

> Objet : Adjugo — nouveau sous-traitant pour la lecture des dossiers (Mistral AI)
>
> Bonjour,
>
> À partir du [date, au moins 30 jours plus tard], Adjugo confiera la lecture et l'analyse des
> dossiers de consultation à Mistral AI (société française), point d'accès européen, avec un calcul
> dans l'Union européenne et l'AELE. Les questions et la rédaction restent chez Anthropic. Chacun
> pourra prendre le relais de l'autre en cas de panne.
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
> un calcul dans l'Union européenne et l'AELE quand son point d'accès européen sert le modèle. Les
> contenus qui leur sont envoyés ne servent pas à entraîner leurs modèles : jamais sans
> autorisation chez Anthropic, et désactivation faite sur notre compte chez Mistral AI. Chacun peut
> prendre le relais de l'autre en cas de panne. Conservation : 30 jours en règle générale chez
> Anthropic (jusqu'à 2 ans pour les contenus signalés pour non-respect de ses règles d'usage),
> 30 jours glissants chez Mistral AI, pour détecter les abus. Fournisseurs, sous-traitants et lieux
> de calcul : voir le DPA (annexe 3).

### 3.3 Section 3, deuxième puce « Strict nécessaire » (publiée le 12/10/2026)

**Publiée** dans `app/static/legal/securite.html` le 12/10/2026 (décision d'Eliot) : elle ne dépend
pas de l'activation de Mistral (lecture intégrale du dossier). Le reste du présent document attend
toujours le jour de l'activation (§ 5).

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
> désactivation faite sur le compte de l'Éditeur chez Mistral AI. Conservation, pour détecter les
> abus : chez Anthropic, 30 jours en règle générale, jusqu'à 2 ans pour les contenus signalés pour
> non-respect de ses règles d'usage ; chez Mistral AI, 30 jours glissants. Mistral AI recourt à
> ses propres sous-traitants, dont Microsoft, CoreWeave et Cloudflare (liste :
> trust.mistral.ai/subprocessors).

(À publier le jour de l'activation de Mistral, § 5, étape 3.)

### 4.3 § 7, liste des garanties appropriées

Ajouter une puce :

> - pour Mistral AI : ses clauses contractuelles types et celles qu'il conclut avec ses propres
>   sous-traitants (accord de sous-traitance de Mistral AI, en vigueur depuis le 27/07/2026).

---

## 5. Ordre des opérations (Eliot)

Déployer ce code ne demande **rien** : sans `MISTRAL_ACTIF=1`, tout part chez Claude Sonnet 5.5 et
les pages ne parlent que d'Anthropic. `LLM_PROVIDER=anthropic` n'est plus nécessaire (sans effet
gênant s'il est déjà posé ; à retirer à l'étape 3).

1. **Console Mistral (admin.mistral.ai)** :
   - désactiver **Admin > Privacy > « Anonymous improvement data »** ;
   - demander l'option **« zéro conservation »** (à la discrétion de Mistral) ;
   - relire trust.mistral.ai/subprocessors (page en JavaScript, non lue automatiquement) ;
   - relire la clause de conservation de la politique de confidentialité de Mistral (§ 1).

   Puis poser **`MISTRAL_ENTRAINEMENT_DESACTIVE=1`** dans Railway. Seule, elle n'active rien.
2. **Prévenir les clients** (§ 2.3), avec une date d'activation au moins 30 jours plus tard.
   Pendant le préavis, ne rien publier des textes ci-dessus : ils disent au présent que Mistral lit
   les dossiers, alors que le serveur injecte encore « Anthropic, PBC » seul.
3. **Le jour de l'activation, en une fois** :
   - publier les corrections du présent document :
     - `dpa.html` et `securite.html` (§ 2, § 3.1 et § 3.2 ci-dessus ; le § 3.3 est déjà publié) :
       directement dans `app/static/legal/` (pas de source Markdown) ;
     - politique de confidentialité (§ 4 ci-dessus) : dans `docs/legal/politique-confidentialite.md`,
       puis `python scripts/build_legal.py` ;
   - poser **`MISTRAL_ACTIF=1`** dans Railway (et retirer `LLM_PROVIDER` s'il est posé), puis
     redémarrer.
4. Ouvrir **`GET /api/admin/ia/diagnostic`** (compte administrateur) et vérifier :
   - `fournisseurs.mistral.variable` = `MISTRAL_API_KEY_ADJUGO` ;
   - `fournisseurs.mistral.etat` = `actif` ;
   - `large4_sur_ue` = `true` ;
   - `point_acces.zone` = `ue` ;
   - aucun message en attente.

   `large4_sur_ue` peut être vérifié **avant** l'étape 3 : la clé suffit pour interroger
   `models.list` sur le point d'accès européen, sans rien envoyer d'autre. S'il vaut `false` (Large 4
   encore absent du point d'accès européen), Mistral passerait par le point d'accès mondial,
   **sans engagement de lieu de calcul**, et les pages le diraient d'elles-mêmes. Pour l'éviter :
   `MISTRAL_POINT_ACCES=ue` (les analyses partent alors chez Claude tant que le modèle n'y est pas
   servi), ou attendre avant l'étape 3 (le message aux clients annonce un calcul dans l'UE et
   l'AELE).

---

## 6. Ce que le serveur injecte désormais (à relire avant de déployer)

Les pages contiennent des repères remplis par le serveur à chaque affichage (`{{AI_PROVIDER}}`,
`{{AI_PRODUCT}}`, `{{AI_LOCATION_FULL}}`, `{{AI_LOCATION_SHORT}}`, `{{AI_TRANSFER_MENTION}}`). Ce
texte part **avec le code** : le relire ici avant de déployer.

| Configuration | Fournisseur(s) | Lieu indiqué | Transferts (§ 7 de la politique) |
|---|---|---|---|
| Mistral non activé (aucune clé, clé seule, clé sans `MISTRAL_ACTIF=1` ou sans `MISTRAL_ENTRAINEMENT_DESACTIVE=1`), ou `LLM_PROVIDER=anthropic` | Anthropic, PBC (Claude API) | États-Unis pour le stockage (API standard api.anthropic.com) ; calcul possiblement hors des États-Unis (routage mondial d'Anthropic) — encadré par CCT. **Change aussi le texte actuel de la production**, qui disait « États-Unis » seulement. | « le fournisseur d'IA (Anthropic, États-Unis ; calcul possiblement dans d'autres pays) pour l'analyse et la génération de documents » |
| Mistral activé, point d'accès UE (Large 4 servi sur l'UE, vérifié par `models.list`) | Anthropic, PBC et Mistral AI | Anthropic : comme ci-dessus ; Mistral AI : calcul dans l'UE et l'AELE (api.eu.mistral.ai), données de fonctionnement du compte possiblement hors zone ; sous-traitants de droit américain (Microsoft, CoreWeave, Cloudflare), CCT ; désinscription faite | Rôles et relais **tirés du routage effectif** : « Anthropic (États-Unis ; calcul possiblement dans d'autres pays) pour les questions sur les dossiers et la rédaction, et en relais pour la lecture et l'analyse des dossiers ; Mistral AI et ses sous-traitants de droit américain […] pour la lecture et l'analyse des dossiers, et en relais pour les questions sur les dossiers et la rédaction — calcul dans l'Union européenne et l'AELE — » |
| Mistral activé, point d'accès mondial | idem | Mistral AI : **sans engagement de lieu de calcul**, possiblement hors UE ; stockage dans l'UE par défaut | idem, « calcul possiblement hors de l'Union européenne » |
| `LLM_PROVIDER=mistral`, Mistral activé | Mistral AI (La Plateforme) | Mistral seul, selon le point d'accès | Mistral AI et ses sous-traitants |

Les rôles suivent aussi les variables `LLM_TACHE_*` : une tâche déplacée chez l'autre fournisseur
change la phrase d'elle-même.

État de la désinscription : avec Mistral activé, la page dit « utilisation des contenus pour
l'amélioration des modèles de Mistral AI désactivée par l'Éditeur sur son compte ». La phrase
« active par défaut […] non encore confirmée » ne peut plus s'afficher (Mistral ne reçoit rien sans
`MISTRAL_ENTRAINEMENT_DESACTIVE=1`) ; elle reste dans le code par prudence.

Le mot « souverain » et l'indicateur `"sovereign": true` ont été retirés : la route publique
`/api/llm/info` renvoie `"sovereign": false`. Formulations honnêtes possibles (comparatif, § 7.3) :

- « calcul de la lecture des dossiers dans l'Union européenne et l'AELE » : seulement avec le point
  d'accès UE, et jamais « UE » seule ;
- « IA hébergée en France » : jamais avec ces deux fournisseurs ;
- l'application elle-même (Railway, Cloudflare R2, Sentry) reste chez des sociétés américaines.
