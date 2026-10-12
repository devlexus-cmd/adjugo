# Garde-fou de l'essai gratuit (chantier E, 12/10/2026)

Règle du fondateur : « économiser le coût de l'IA sans jamais baisser la performance ». Essai gratuit :
garde-fou de coût. Clients payants : **aucun plafond réduit**, aucun changement de comportement.

## 1. Ce qui change, pour un compte en essai actif SEULEMENT

Un compte est « en essai actif » quand son forfait n'est ni Pro ni Business et que son essai de
30 jours n'est pas terminé (`quota.essai_actif`, même règle qu'avant dans `quota._limit`). Le compte
qui compte est le **compte de facturation** : le propriétaire de l'organisation (`quota._billing_user`).

| Règle | Avant | Maintenant | Réglage |
|---|---|---|---|
| Analyses | 30 par mois civil (un essai à cheval sur deux mois : jusqu'à 60) | **30 au total, sur toute la durée de l'essai** (`users.trial_analyses_used`, jamais remis à zéro) | `TRIAL_ANALYSES` (30) |
| Questions sur un dossier | 50 par jour (niveau Pro) | **15 par jour** et par organisation | `TRIAL_QUESTIONS_PAR_JOUR` (15) ; `QUESTIONS_PAR_JOUR`, s'il est réglé, reste un plafond pour tous |
| Coût de l'IA | non borné | **budget de l'essai** vérifié avant chaque opération | `TRIAL_AI_BUDGET_EUR` (15 € ; 0 = coupé), `TRIAL_AI_BUDGET_PROCHE` (0,8) |

- Analyse remboursée (l'IA est tombée) : rendue au compteur de l'essai, même après un changement de mois.
- Le compteur du mois est un minimum du compteur de l'essai (une analyse du mois est une analyse de
  l'essai) : les comptes déjà en essai à la mise en service repartent de ce qu'ils ont consommé ce mois
  (migration), rien n'est offert en plus.
- Paiement à l'usage : jamais pendant l'essai (rien à facturer), comme avant.

## 2. Mesure du coût (tous usages)

- **Chaque appel facturé** passe par `llm.messages_create` (routage par tâche, docs/IA_ROUTAGE.md).
  Son coût est calculé **une seule fois**, dans `llm._track_usage`, et porté au même montant au
  `cost_meter` (journal) et à `budget_ia.enregistrer_appel` (compte facturé) : tarif public du modèle
  **réellement appelé** (celui que renvoie le fournisseur s'il a un tarif connu, sinon celui de la
  route), point d'accès **réellement utilisé** (Mistral UE : +10 %), cache compris (lecture ; écriture
  de 5 minutes, ou d'une heure pour la rédaction), **secours compris** : une réponse coupée ou au JSON
  illisible puis reprise par l'autre fournisseur est facturée deux fois, et comptée deux fois. Table
  des prix unique : `app/services/tarifs_ia.py`. Sont couverts : analyses (avis et dossier), lecture
  en deux temps, questions, atelier, questionnaire, chiffrage, veille (manuelle et planifiée),
  renouvellements, côté acheteur.
- **Rattachement** : tenant de l'appel (`tenant_scope`) → propriétaire de l'organisation → ligne
  `usage_ia` (`compte = "u<id>"`, mois, essai oui/non). Appel mutualisé (veille planifiée, un appel pour
  tous les abonnés) : `budget_ia.mutualise(...)` → compte `plateforme`, jamais imputé à un essai. Côté
  acheteur : `acheteur:<id>` (compte connecté) ou `acheteur:anonyme` (jamais d'adresse IP en base).
- **Sans ralentir l'appel** : relevé en mémoire pendant l'appel, écrit en base par un fil dédié
  (`adjugo-cout-ia`) quelques instants plus tard ; une base indisponible → réessai, rien n'est perdu
  tant que le process vit. Les lectures (garde-fou, écran, administration) ajoutent ce qui n'est pas
  encore écrit (process unique). Un redémarrage perd au plus les relevés des dernières secondes.
- `cost_meter` (journal d'un traitement) cumule exactement les mêmes montants (vérifié par
  `tests/test_fusion_routage_essai.py` : Mistral au point d'accès UE avec cache, secours après une
  réponse coupée, rédaction avec cache d'une heure).

Tarifs relevés le 12/10/2026 (vérifiés en ligne) :

| Modèle (identifiant exact) | Entrée | Sortie | Cache lu | Cache écrit (5 min / 1 h) | Remarque |
|---|---|---|---|---|---|
| `claude-sonnet-5-5` | 2 $ | 10 $ | 0,10 $ (0,05 ×) | 2,50 $ / 4 $ | découpage ≈ +30 % de tokens |
| `claude-haiku-5-5` | 0,10 $ | 0,50 $ | 0,01 $ | 0,125 $ / 0,20 $ | au-delà de 100 000 tokens d'entrée : 0,50 / 2,50 $ |
| `claude-opus-5-5` | 4 $ | 20 $ | 0,20 $ | 5 $ / 8 $ | |
| `claude-sonnet-4-6` | 3 $ | 15 $ | 0,30 $ | 3,75 $ / 6 $ | ancien routage (`LLM_ROUTAGE=ancien`) |
| `claude-haiku-4-5` | 1 $ | 5 $ | 0,10 $ | 1,25 $ / 2 $ | ancien routage |
| `mistral-large-4` (préversion publique du 06/10/2026), prix normal | 1,36 $ (1,156 €) | 4,18 $ (3,553 €) | 0,14 $ (10 %) | — | `api.eu.mistral.ai` : + 10 % (`MISTRAL_SURCOUT_UE`) |
| `mistral-large-4`, prix de lancement | 0,68 $ | 2,09 $ | 0,07 $ | — | « 50 % off for 2 weeks » (journal des modifications de Mistral, vérifié le 12/10/2026) : jusqu'au `MISTRAL_SOLDE_JUSQU_AU` inclus (2026-10-19) |
| `mistral-large-latest` | compté comme Large 4 | | | | l'alias désigne Large 3 au 12/10/2026 ; jamais utilisé |
| modèle inconnu | prix d'Opus 5.5 (4 / 20 $, cache non remisé) | | | | signalé une fois au journal : jamais sous-estimé |

Conversion : 1 $ = `AI_USD_EUR` € (0,85, rapport des deux affichages de Mistral). Cache de Mistral :
les tokens relus (`usage.prompt_tokens_details.cached_tokens`) sont facturés 10 % du prix d'entrée.
Prix de Mistral réglables sans changer le code : `MISTRAL_PRIX_LARGE4`, `MISTRAL_PRIX_LARGE4_SOLDE`
(« entrée|sortie|cache », en $), `MISTRAL_SOLDE_JUSQU_AU` (`aucun` = prix normal).

## 3. Le garde-fou, avant chaque opération

`budget_ia.verifier(user, db, operation, estimation_eur)` : si le compte de facturation est en essai
et que **coût déjà engagé + estimation prudente de l'opération > budget**, refus **402** avant tout
appel à l'IA et tout débit, `detail = {"code": "essai_limite_usage", "message": …}` :
- budget épuisé (même une question ne passe plus) : « Votre essai gratuit a atteint sa limite
  d'usage : les fonctions d'IA sont en pause. Choisissez un forfait (Pro ou Business) pour continuer.
  Vos marchés, documents et dossiers restent accessibles. »
- opération trop lourde pour ce qui reste : « Cette opération dépasserait la limite d'usage de votre
  essai gratuit. Choisissez un forfait (Pro ou Business) pour la lancer ; les questions sur vos
  dossiers restent possibles. »

**Une opération commencée va toujours au bout** : aucun appel n'est coupé en cours de route (jamais un
dossier à moitié lu, jamais une rédaction interrompue). Le dépassement possible est donc borné par le
coût d'une opération (ou de quelques-unes lancées exactement en même temps).

Points de vérification :

| Opération | Où | Estimation |
|---|---|---|
| Analyse d'un avis | `consume_analysis` (`/api/sourcing/analyze`) | enveloppe « analyse » |
| Import / ré-analyse d'un dossier (y compris lecture en deux temps, reprise des scans) | `_import_and_analyze` → `consume_analysis` | **selon le dossier** : taille, lecture d'un seul tenant ou en deux temps, pages encore à lire (`budget_ia.estimer_import`) |
| Question sur un dossier | `reserve_question` | enveloppe « question » (règlements écrits dans le cache) |
| Atelier : rédiger (une ou plusieurs parties, comprises ou débitées), raccourcir | `atelier.lancer` (avant la tâche) puis `_debiter` | dossier commun écrit une fois dans le cache, relu par les parties suivantes (`estimer_atelier`) |
| Questionnaire | `consume_analysis` | par question × nombre de questions |
| Chiffrage (hors quota) | `/api/chiffrage/{id}/estimate` | enveloppe « chiffrage » |
| Veille manuelle, délibération importée ou collée | `consume_analysis` (amont) | enveloppes « veille », « deliberation » |
| Renouvellements (repli IA) | `consume_analysis` | enveloppe « renouvellements » |

Les enveloppes sont prises sur les plafonds du code et comptées sur la **route de la tâche**
(`budget_ia.estimer_appel`, même table des prix que le coût mesuré) : modèle principal ET secours
s'il est configuré, **le plus cher des deux** (une panne de Mistral fait tout passer chez Sonnet 5.5) ;
plafond de sortie tel qu'il est envoyé (`llm.plafond_sortie` : découpage du modèle, réserve de
réflexion) ; point d'accès de Mistral (UE : +10 %) ; durée du cache de la route (rédaction : une
heure, écrite à 2 × l'entrée). `LLM_PROVIDER`, `LLM_ROUTAGE=ancien` et les variables `LLM_TACHE_*`
sont donc pris en compte. Valeurs au 12/10/2026, les deux fournisseurs configurés (ou
`LLM_PROVIDER=anthropic`), prix normal de Large 4 : analyse 0,15 € ; question 0,08 € ; chiffrage
0,06 € ; atelier 0,50 € pour une partie, 1,70 € pour neuf ; raccourcir 0,08 € ; questionnaire de 40
questions 0,68 € ; veille 0,17 € ; dossier de 50 000 caractères 0,12 €, 600 000 caractères (deux temps)
1,34 €, 6 000 000 caractères 8,72 €. Mistral seul (secours coupé, `LLM_TACHE_<TACHE>_SECOURS=aucun`) :
analyse 0,09 €, dossier de 6 000 000 caractères 5,46 €.

## 4. Écrans (aucun montant, jamais)

- `/api/agent/stats` → `usage` et `/api/stripe/status` : pendant l'essai, `analyses_used` /
  `analyses_limit` / `analyses_remaining` comptent **sur 30, pour toute la durée**, plus
  `quota_scope: "essai"`, `trial_questions_per_day` et `trial_usage` : `ok` | `proche` (80 % du budget,
  ou plus de place pour une analyse) | `atteint` (plus de place pour une question).
- Recherche d'appels d'offres : « 12 analyses restantes sur 30 (essai gratuit) », « Limite d'usage de
  l'essai atteinte ».
- Carte sobre en haut de l'écran (bulle (i), bouton « Voir les forfaits », « Plus tard ») : après tout
  refus 402 (quota, essai terminé, limite d'usage, membres), quand la limite d'usage est proche ou
  atteinte, ou quand il reste 3 analyses ou moins dans l'essai.
- Page « Forfaits », carte « Essai gratuit » : « 30 analyses IA pendant l'essai » (bulle (i)), « 15
  questions par jour sur vos dossiers », analyses restantes sur 30 et, à l'approche de la limite, une
  phrase sobre.

## 5. Forfaits payants : jamais bridés, alerte interne

Pro, Business et tout forfait autre que « starter » : mêmes plafonds qu'avant (30 / 100 analyses par
mois, 50 / 120 questions par jour, paiement à l'usage), aucune vérification de budget. Après chaque
écriture du relevé, si le coût IA du mois d'une organisation payante dépasse `PAID_AI_ALERT_RATIO`
(0,5) × le prix de son forfait (`PLAN_PRICES_EUR` : Pro 129,99 €, Business 199,99 € ; un forfait
absent est comparé au plus cher), **une** alerte par mois au journal (`ALERTE coût IA : organisation du
compte u… (forfait pro) à … € ce mois …`) et la date est gardée (`usage_ia.alerte_le`). Aucun blocage.

## 6. Administration

`GET /api/admin/usage-ia[?periode=AAAA-MM]` (administrateur de la plateforme seulement) : chaque essai
en cours (analyses sur 30, jours restants, coût consommé et budget, état), les organisations payantes du
mois (coût, seuil, alerte), les comptes `plateforme` et acheteurs, le total du mois. Carte « Coût de
l'IA » dans la vue Administration.

## 7. Mise en service

- Migration `u5v6essaigardefou` (après `t4u5redactionv2b`) : colonne `users.trial_analyses_used`
  (reprise du compteur du mois pour les comptes en essai) et table `usage_ia`. Idempotente, retour
  arrière réel. **Attention à la fusion** : si un autre chantier ajoute aussi une révision après
  `t4u5redactionv2b`, rechaîner l'une sur l'autre (une seule tête, sinon `alembic upgrade head`
  échoue).
- Variables (Railway) : rien d'obligatoire, les valeurs par défaut sont celles de la décision.
  À régler au besoin : `TRIAL_AI_BUDGET_EUR`, `TRIAL_ANALYSES`, `TRIAL_QUESTIONS_PAR_JOUR`,
  `TRIAL_AI_BUDGET_PROCHE`, `PAID_AI_ALERT_RATIO`, `PLAN_PRICES_EUR` (JSON), `AI_USD_EUR`.
- Pages juridiques : l'article 3.5 des CGV parle encore de « 30 analyses par mois » pendant l'essai.
  Texte proposé dans `docs/A_VALIDER_CGV_essai_gratuit.md` (non publié).

## 8. Limites connues

- Deux opérations lancées exactement en même temps passent chacune la vérification : le dépassement
  est borné par leur coût (une lecture de dossier à la fois par organisation, de toute façon).
- Un essai expiré garde le comportement d'avant pour les questions (15 par jour, plafond « starter ») :
  hors du périmètre « essai actif ».
- Le relevé `usage_ia` n'est pas effacé avec un compte (aucune donnée personnelle : un identifiant de
  compte, des montants, des nombres de tokens) ; il sert au coût de la plateforme.
- Les tarifs sont codés dans `tarifs_ia.py` : les revoir à chaque changement de prix. Le prix de
  lancement de Mistral Large 4 est compté jusqu'au `MISTRAL_SOLDE_JUSQU_AU` (2026-10-19) : si Mistral
  prolonge ou arrête plus tôt son offre, changer cette date (`aucun` = prix normal).
- Une estimation compte le plus cher du principal et du secours, pas leur somme : une réponse coupée
  puis reprise par le secours (deux appels facturés) peut dépasser l'estimation ; elle est comptée au
  coût réel ensuite.
