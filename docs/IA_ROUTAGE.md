# Routage de l'IA par tâche, secours, surveillance (chantier R)

Mise à jour du 12/10/2026. Code : `app/services/llm.py` (table `_TABLE`, `route()`, `messages_create()`)
et `app/services/llm_qualite.py` (surveillance). Pages juridiques : voir
`docs/IA_FOURNISSEURS_PAGES_JURIDIQUES.md`.

## 1. Qui fait quoi

Décisions du fondateur du 12/10/2026, prises sans test préalable :
- Mistral Large 4 lit et extrait les documents ;
- Claude Sonnet 5.5 traite tout le reste.

Règle : « économiser le coût de l'IA sans jamais baisser la performance ».

| Tâche (`tache=`) | Appel | Fournisseur, modèle | Réglages | Secours | Ancien routage |
|---|---|---|---|---|---|
| `analyse` | `analysis.analyze_dce_text` (avis, DCE, lecture intégrale, synthèse en deux temps) | Mistral `mistral-large-4` | JSON (`response_format`) | Sonnet 5.5 (`between_tools`, effort high) si Mistral est absent, en panne, en erreur de modèle, coupé ou si son JSON est illisible | Sonnet 4.6 |
| `lecture_pieces` | `analyse_dossier._appel` (premier temps) | Mistral Large 4 | JSON | Sonnet 5.5 (sauf coupure : la partie est relue en deux moitiés) | Haiku 4.5 (`ANALYSE_MODELE_PIECES` reste lu) |
| `exigences` | `memoire.extract_requirements` | Mistral Large 4 | JSON | Sonnet 5.5 | Sonnet 4.6 |
| `veille` | `amont.detect_from_deliberations` (veille planifiée et manuelle) | Mistral Large 4 | JSON | Sonnet 5.5 (effort medium) | Sonnet 4.6 |
| `deliberation` | `amont.detect_projets` (délibération importée) | Mistral Large 4 | JSON | Sonnet 5.5 | Sonnet 4.6 |
| `renouvellements` | `renewal.detect_renewals` | Mistral Large 4 | JSON | Sonnet 5.5 (effort medium) | Sonnet 4.6 |
| `questions` | `sourcing._ask_integral`, `_ask_legacy` | Claude `claude-sonnet-5-5` | `between_tools`, effort medium, cache 5 min | Mistral Large 4 si Anthropic est absent, en panne, en erreur ou refuse | Haiku 4.5 |
| `redaction` | atelier (`memoire.rediger_partie`), dossier complet (`write_section`), groupement (`_write_merged_section`) | Sonnet 5.5 | réflexion adaptative, effort high, +8 000 tokens de réserve, **cache d'une heure** | Mistral Large 4 | Sonnet 4.6 |
| `raccourcir` | `memoire.raccourcir_partie` | Sonnet 5.5 | `between_tools`, effort high | Mistral Large 4 | Sonnet 4.6 |
| `plan` | `memoire.build_plan` | Sonnet 5.5 | `between_tools`, effort high | Mistral Large 4 | Sonnet 4.6 |
| `controle` | `memoire.conformity_check` | Sonnet 5.5 | adaptative, effort high | Mistral Large 4 | Sonnet 4.6 |
| `questionnaire` | `questionnaire._answer_from_chunks` | Sonnet 5.5 | `between_tools`, effort high | Mistral Large 4 | Sonnet 4.6 |
| `chiffrage` | `chiffrage.propose_tasks` | Sonnet 5.5 | adaptative, effort medium | Mistral Large 4 | Sonnet 4.6 |
| `repartition` | `warroom.propose_allocation` | Sonnet 5.5 | adaptative, effort medium | Mistral Large 4 | Sonnet 4.6 |
| `acheteur_dce` | `dce_redaction._gen_core` | Sonnet 5.5 | adaptative, effort high | Mistral Large 4 | Sonnet 4.6 |
| `acheteur_annexes` | `dce_redaction._gen_admin`, `_gen_cctp` | Sonnet 5.5 | adaptative, effort high | Mistral Large 4 | Haiku 4.5 |
| `acheteur_conseils` | `sourcing_acheteur._generer_conseils` | Sonnet 5.5 | `between_tools`, effort medium | Mistral Large 4 | Sonnet 4.6 |

Le test `tests/test_routage_ia.py::test_tous_les_appels_ia_de_l_application_nomment_leur_tache`
parcourt le code. Il échoue :
- si un appel IA de `app/` ne nomme pas sa tâche ;
- si une tâche de la table n'est plus utilisée.

## 2. Ce que la couche fait pour chaque appel

Quel que soit le fournisseur, **secours compris**, chaque appel passe par les mêmes contrôles :
- noms des salariés masqués avant l'envoi (`pii_scope`, une seule fois, avant le choix du
  fournisseur) ;
- espace facturé (`tenant_scope`) ;
- plafonds de tokens ;
- disjoncteurs, un par fournisseur et un par espace : une panne de Mistral n'arrête pas Anthropic ;
- places limitées (`LLM_MAX_CONCURRENT`) : un secours prend sa propre place, après avoir rendu
  celle de l'appel qui a échoué ;
- coût mesuré (`cost_meter`) ;
- surveillance de la qualité.

La réponse garde toujours la même forme (`resp.content[0].text`, `resp.usage`, `resp.stop_reason`).
Les garde-fous des appelants s'appliquent donc à l'identique :
- citations vérifiées (`citation_guard`) ;
- « [À compléter : …] » ;
- remboursement si l'IA tombe ;
- `AnalyseCoupee`.

**Claude Sonnet 5.5** (documentation Anthropic relue le 12/10/2026) :
- aucune valeur de `temperature`, `top_p` ni `top_k` n'est envoyée : le modèle renverrait une
  erreur 400 ;
- seuls les blocs `text` sont lus ; les blocs `thinking` et `redacted_thinking` sont écartés ;
- réflexion et effort passent par `extra_body` (`thinking`, `output_config.effort`) avec le SDK
  épinglé en 0.34. Vérifié hors réseau : il transmet `extra_body` et la durée du cache tels quels,
  et lit les blocs de réflexion sans erreur ;
- `max_tokens` est multiplié par 1,3 (nouveau découpage), plus une réserve quand la réflexion est
  active, car elle compte dedans ;
- `between_tools` (le réglage le plus bas, sans réflexion préalable) n'est accepté qu'avec un
  effort ≤ high ;
- refus (`stop_reason: "refusal"`) : secours Mistral, sinon `LLMRefus` (sous-classe de
  `LLMUnavailable`) ; l'appelant rembourse ;
- cache d'une heure (`"ttl": "1h"`, sans en-tête bêta) pour la tâche `redaction`. Prix sur
  Sonnet 5.5 : écriture 2 × le prix d'entrée, relecture 0,05 ×. Calcul détaillé :
  `docs/REDACTION_V2_API.md` § 4.4.

**Mistral Large 4** :
- appel HTTP direct (`httpx`) sur `/v1/chat/completions`, avec reprises sur 429, 5xx et coupure
  réseau ;
- `response_format: {"type": "json_object"}` pour les tâches JSON ;
- blocs de raisonnement éventuels écartés ;
- motifs `length` et `model_length` ramenés à « coupé » (`max_tokens`) ;
- point d'accès :
  - `auto` (défaut) : UE si `GET /v1/models` sur `api.eu.mistral.ai` liste le modèle (vérifié au
    plus toutes les 6 h), sinon mondial ;
  - une réponse « modèle inconnu » du point d'accès UE fait passer les appels suivants par le
    mondial ;
  - les pages juridiques suivent ce choix.

**Secours** : chaque bascule est journalisée et comptée (par tâche, de quel fournisseur vers lequel,
pour quel motif) :
- avertissement dans le journal, sauf « absent » : information, une fois par heure ;
- `bascules_de_secours` dans `cost_meter` ;
- `adjugo_llm_bascules_total` dans `/metrics`.

Une réponse coupée relancée au secours a deux fois plus de place. Si le secours échoue aussi, la
réponse coupée ou au JSON illisible est rendue à l'appelant, qui la traite comme avant.

## 3. Coût (`cost_meter`, journal et `dossiers_presentation.cout_ia`)

Prix en $ par million de tokens, relevés le 12/10/2026 :

| Modèle | Entrée | Sortie | Lecture du cache | Écriture du cache |
|---|---|---|---|---|
| Sonnet 5.5 | 2 | 10 | 0,10 | 2,50 (5 min) / 4 (1 h) |
| Sonnet 4.6 | 3 | 15 | 0,30 | 3,75 / 6 |
| Haiku 4.5 | 1 | 5 | 0,10 | 1,25 / 2 |
| Mistral Large 4, prix normal | 1,36 | 4,18 | 0,14 | — |
| Mistral Large 4, prix soldé | 0,68 | 2,09 | 0,07 | — |

- Mistral au point d'accès UE : +10 % sur tous ses prix.
- Prix soldé de Mistral : appliqué jusqu'au `MISTRAL_SOLDE_JUSQU_AU` (défaut 2026-10-19 : −50 %
  « pendant 2 semaines » à partir du 06/10, d'après le journal des modifications de Mistral), puis
  prix normal.
- Les deux prix de Mistral sont réglables : `MISTRAL_PRIX_LARGE4` et `MISTRAL_PRIX_LARGE4_SOLDE`,
  au format « entrée|sortie|cache ».
- Les tokens comptés sont ceux renvoyés par l'API : le découpage propre à chaque modèle y est déjà.
- `llm.estimer_cout()` applique le facteur 1,3 aux estimations faites à partir de caractères.
- Aucun montant n'est montré au client.

## 4. Surveillance (`/metrics` et `GET /api/admin/ia/qualite`)

Mesures, par fournisseur et par tâche :
- appels réussis, en erreur, refusés ;
- réponses JSON invalides ;
- réponses coupées ;
- citations acceptées et rejetées par la vérification : analyse, grille de notation, lecture des
  pièces, questions ;
- abstentions « pas trouvé dans le dossier » (questions) ;
- bascules ;
- histogramme des délais.

Seuils d'alerte, évalués sur les 50 derniers appels et seulement à partir de 10 :

| Mesure | Seuil | Variable |
|---|---|---|
| erreurs | 10 % | `LLM_ALERTE_ERREURS` |
| JSON invalides | 5 % | `LLM_ALERTE_JSON` |
| réponses coupées | 5 % | `LLM_ALERTE_COUPEES` |
| refus | 2 % | `LLM_ALERTE_REFUS` |
| bascules | 10 % | `LLM_ALERTE_BASCULES` |
| citations rejetées | 25 % | `LLM_ALERTE_CITATIONS_REJETEES` |
| abstentions | 50 % | `LLM_ALERTE_ABSTENTIONS` |
| délai au 95e centile | 120 s | `LLM_ALERTE_DELAI_P95_S` |

Taille de la fenêtre glissante et minimum d'appels : `LLM_ALERTE_FENETRE`, `LLM_ALERTE_MIN_APPELS`.
Un dépassement est journalisé (« Alerte qualité IA — … »), au plus une fois par 30 minutes et par
mesure, **sans jamais bloquer**. Compteurs en mémoire du process, remis à zéro au redémarrage.

## 5. Diagnostic d'administration : `GET /api/admin/ia/diagnostic`

Réservé à un compte administrateur de la plateforme (`is_admin`). **Aucune clé n'y figure** (ni
valeur, ni extrait, ni longueur) : seulement le nom de la variable lue et si elle est présente.

Ce qu'il indique :
- le routage (nouveau ou ancien) et un éventuel forçage par `LLM_PROVIDER` ;
- pour chaque fournisseur : clé présente, variable lue, disjoncteur ;
- pour Mistral :
  - le point d'accès utilisé et pourquoi ;
  - le résultat de `models.list` sur le point d'accès UE (`large4_sur_ue`), vérifié en direct sauf
    avec `?verifier=0` ;
  - l'état de la désinscription de l'entraînement ;
- pour chaque tâche : fournisseur, modèle, réglages, secours, et où elle part MAINTENANT, vu les
  clés et les disjoncteurs ;
- la dernière bascule et leurs compteurs ;
- des messages en clair sur ce qu'il reste à faire.

La route publique `GET /api/llm/info` ne donne que la liste des fournisseurs sollicités
(`"sovereign": false`).

## 6. Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Clé Anthropic (déjà posée). |
| `MISTRAL_API_KEY_ADJUGO` | — | Clé Mistral, lue en priorité (déjà posée dans Railway). |
| `MISTRAL_API_KEY` | — | Nom historique, accepté par compatibilité. Ne déclenche plus rien d'autre. |
| `MISTRAL_ENTRAINEMENT_DESACTIVE` | `false` | À mettre à `1` une fois « Anonymous improvement data » désactivé dans la console Mistral : les pages juridiques le disent alors. |
| `MISTRAL_POINT_ACCES` | `auto` | `auto` \| `ue` \| `mondial`. |
| `LLM_ROUTAGE` | `nouveau` | `ancien` : retour en une minute à Sonnet 4.6 / Haiku 4.5, réglages d'origine, aucun secours. |
| `LLM_PROVIDER` | `auto` | `anthropic` \| `mistral` : toutes les tâches chez un seul fournisseur, sans secours. Le diagnostic et le journal le disent. |
| `LLM_SECOURS` | `1` | `0` : aucun secours. |
| `LLM_TACHE_<TACHE>` | — | Fournisseur et modèle d'une tâche, p. ex. `LLM_TACHE_ANALYSE=anthropic:claude-sonnet-5-5`. |
| `LLM_TACHE_<TACHE>_SECOURS` | — | `mistral:mistral-large-4`, ou `aucun`. |
| `LLM_TACHE_<TACHE>_EFFORT` | — | `low` \| `medium` \| `high` \| `xhigh` \| `max` \| `aucun`. |
| `LLM_TACHE_<TACHE>_REFLEXION` | — | `between_tools` \| `adaptive` \| `aucune`. |
| `LLM_TACHE_<TACHE>_CACHE` | — | `5m` \| `1h`. |
| `LLM_TACHE_<TACHE>_RESERVE` | — | Tokens de réserve pour la réflexion. |
| `LLM_MODELE_SONNET` | `claude-sonnet-5-5` | Modèle Claude du routage par tâche. |
| `LLM_MODELE_MISTRAL` | `mistral-large-4` | Modèle Mistral, p. ex. un identifiant daté quand Mistral en publiera un. |
| `MISTRAL_SOLDE_JUSQU_AU` | `2026-10-19` | Fin du prix soldé (`aucun` = prix normal). |
| `MISTRAL_PRIX_LARGE4` | — | Prix normal, « entrée\|sortie\|cache ». |
| `MISTRAL_PRIX_LARGE4_SOLDE` | — | Prix soldé, même format. |
| `MISTRAL_SURCOUT_UE` | `0.10` | Surcoût du point d'accès UE. |

## 7. Retour arrière

- `LLM_ROUTAGE=ancien`, puis redémarrage : tout repasse par Claude Sonnet 4.6 et Haiku 4.5, avec
  les temperatures et plafonds d'origine, le cache de 5 minutes et aucun secours. Rien n'est
  envoyé chez Mistral, même avec une clé.
- Pour ne couper que Mistral, en gardant Sonnet 5.5 : `LLM_PROVIDER=anthropic`.
