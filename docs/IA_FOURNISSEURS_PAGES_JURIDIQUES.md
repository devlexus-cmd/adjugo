# Fournisseurs d'IA et pages juridiques — textes publiés

Document de travail du 12/10/2026 (chantier R, routage de l'IA par tâche), mis à jour le même jour.

**Décision d'Eliot du 12/10/2026** : Mistral est activé **juste après la mise en ligne**. Les testeurs
ont été prévenus de longue date, la désinscription de l'entraînement est faite dans la console
Mistral et `MISTRAL_ENTRAINEMENT_DESACTIVE=1` est posé dans Railway. Les corrections des § 2, 3 et 4
sont donc **publiées** (`app/static/legal/dpa.html`, `app/static/legal/securite.html`,
`docs/legal/politique-confidentialite.md` → `python scripts/build_legal.py`).

Elles sont écrites pour être **exactes avant ET après l'activation** : tout ce qui dépend du ou des
fournisseurs réellement sollicités (qui fait quoi, entraînement, conservation, lieu de calcul,
sous-traitants de Mistral AI, transferts) passe par des **repères remplis par le serveur** à chaque
affichage (`app/main.py`, `_ai_subprocessor_fragments`, § 6). Le texte fixe ne nomme jamais Mistral
et ne promet jamais « UE » : tant que Mistral n'est pas activé, les pages ne parlent que d'Anthropic ;
dès qu'il l'est, elles décrivent les deux fournisseurs et le point d'accès Mistral réellement utilisé.

Ce qui a changé dans le code, et qui rend ces corrections nécessaires :

- **Deux fournisseurs d'IA à la fois** dès que Mistral est **activé**, c'est-à-dire avec les
  trois réunis : une clé (`MISTRAL_API_KEY_ADJUGO`, ou `MISTRAL_API_KEY`), `MISTRAL_ACTIF=1` et
  `MISTRAL_ENTRAINEMENT_DESACTIVE=1`. Sans les trois, rien ne part chez Mistral : tout part chez
  Claude Sonnet 5.5, et les pages ne parlent que d'Anthropic.
  - Mistral Large 4 lit et analyse les dossiers (analyse, lecture en deux temps, exigences,
    délibérations de la veille, renouvellements) ;
  - Claude Sonnet 5.5 (Anthropic) répond aux questions, rédige, remplit le questionnaire, chiffre,
    et sert le côté acheteur ;
  - chacun prend le relais de l'autre en cas de panne : un dossier peut donc partir chez l'un ou
    l'autre, quelle que soit la tâche.
- Pour Anthropic, le texte injecté dit, **y compris sans Mistral** : stockage aux États-Unis, calcul
  possiblement hors des États-Unis (l'API est appelée sans `inference_geo`, donc en routage
  « global » : « Inference may run in any available geography », documentation Anthropic sur la
  résidence des données).

---

## 1. Faits vérifiés

| Fait | Source |
|---|---|
| Large 4 : identifiant d'API `mistral-large-4`, préversion publique depuis le 06/10/2026, fenêtre de 1 000 000 de tokens. L'alias `mistral-large-latest` n'est pas Large 4. | Journal des modifications de Mistral (docs.mistral.ai/getting-started/changelog), fiche du modèle (docs.mistral.ai/models/mistral-large-4-0) |
| Prix de Large 4 : 1,36 $ en entrée, 4,18 $ en sortie, 0,14 $ en lecture du cache, par million de tokens. Prix de lancement à −50 % « pendant 2 semaines » (0,68 / 2,09 / 0,07). | docs.mistral.ai/inference/pricing, journal des modifications |
| Point d'accès UE : `https://api.eu.mistral.ai/v1`. Calcul dans des centres de données de l'UE et de l'AELE (« Multiple data centers in EU and EFTA countries ») : jamais « UE » seule. Tarif : 1,1 × le prix de base. Ni lots, ni fichiers, ni agents. Disponibilité des modèles à vérifier par `models.list` sur ce point d'accès. | docs.mistral.ai/inference/regional-inference |
| Point d'accès UE : les données de fonctionnement du compte (configuration, clés, facturation, statistiques d'usage) peuvent être traitées hors de la zone. | idem |
| Point d'accès mondial `api.mistral.ai` : aucun engagement de lieu pour le calcul ; stockage dans l'UE par défaut. Le lieu de calcul dépend donc du point d'accès **réellement utilisé** : les pages le disent d'après le diagnostic du serveur, jamais en dur. | Comparatif des API, § 5.1 [S16, S21] |
| Entraînement chez Mistral AI : **désactivé sur le compte d'Adjugo** (désinscription faite dans la console Mistral, Admin > Privacy, « Anonymous improvement data », faite par Eliot, 12/10/2026). Le code n'envoie rien chez Mistral sans `MISTRAL_ENTRAINEMENT_DESACTIVE=1`. | Console Mistral ; help.mistral.ai, article 455207 (mis à jour le 03/09/2026) |
| Conservation chez Mistral AI (vérifié le 12/10/2026) : requêtes et réponses de l'API conservées **jusqu'à 30 jours glissants** pour la surveillance des abus, sauf si la non-conservation est activée. La non-conservation **n'est pas confirmée** pour le compte d'Adjugo : écrire « jusqu'à 30 jours », jamais « aucune conservation ». | Politique de confidentialité et DPA de Mistral AI [S17, S22] |
| Sous-traitants de Mistral AI : leur **liste n'a pas pu être vérifiée** (12/10/2026). Les pages n'en nomment **aucun** : elles disent que Mistral AI s'appuie sur ses propres sous-traitants techniques, dont la liste à jour est publiée sur son centre de confiance (https://trust.mistral.ai/subprocessors). Transferts : clauses contractuelles types prévues par l'accord de sous-traitance de Mistral AI. | trust.mistral.ai/subprocessors (page rendue en JavaScript, à relire à la main) ; DPA de Mistral [S18] |
| Anthropic, API directe : stockage aux États-Unis (seule zone de stockage proposée) ; calcul « global » par défaut, possiblement hors des États-Unis (« us » seulement avec `inference_geo: "us"`, + 10 %, non utilisé). Aucune option UE. Contenus jamais utilisés pour l'entraînement sans permission. | platform.claude.com/docs/en/manage-claude/data-residency (relue le 12/10/2026) ; comparatif § 5.1 [S1 à S4] |
| Conservation chez Anthropic : entrées et sorties effacées sous 30 jours **en règle générale** ; **jusqu'à 2 ans** pour les contenus signalés pour non-respect de ses règles d'usage (et jusqu'à 7 ans pour les scores de classification de sécurité). | privacy.claude.com, article 7996866 (relu le 12/10/2026) : « We retain inputs and outputs for up to 2 years and trust and safety classification scores for up to 7 years if your chat is flagged » ; comparatif § 5.1 [S2] |

Jamais : « souverain », « IA hébergée en France », « UE » sans « et AELE », « UE » quand le point
d'accès mondial est utilisé.

---

## 2. `dpa.html` (accord de sous-traitance) — publié le 12/10/2026

### 2.1 Annexe 2 — mesures de sécurité, puce « modèle d'IA »

Avant :

> modèle d'IA ({{AI_PROVIDER}}, appelé via une API) : les contenus qui lui sont envoyés ne sont
> jamais utilisés pour entraîner un modèle ; la conservation éventuelle par le fournisseur est
> encadrée par ses conditions ;

Publié (texte fixe, repères remplis par le serveur, § 6) :

> modèles d'IA ({{AI_PROVIDER}}, appelés via une API) : les contenus qui leur sont envoyés ne sont
> pas utilisés pour entraîner un modèle ({{AI_ENTRAINEMENT}}) ; les noms des salariés sont remplacés
> par des étiquettes avant tout envoi ; la conservation est encadrée par les conditions applicables
> à l'API ({{AI_CONSERVATION}}) ;

### 2.2 Annexe 3 — paragraphe sous le tableau des sous-traitants

Avant :

> Fournisseur d'IA : les contenus envoyés au modèle ne sont jamais utilisés pour entraîner un
> modèle d'IA ; leur conservation éventuelle par {{AI_PROVIDER}} est encadrée par ses conditions
> applicables à l'API ({{AI_PRODUCT}}).

Publié :

> Intelligence artificielle : {{AI_ROLES}} Les contenus envoyés ne sont pas utilisés pour entraîner
> un modèle d'IA ({{AI_ENTRAINEMENT}}).{{AI_SOUS_TRAITANTS_MISTRAL}} Les lieux de calcul (et de
> stockage, lorsque le fournisseur s'y engage) figurent dans le tableau ci-dessus. La conservation
> est encadrée par les conditions applicables à l'API ({{AI_CONSERVATION}}).

Le tableau lui-même n'a pas changé : sa ligne « IA » est remplie par le serveur (§ 6). Il donne le
lieu de stockage d'Anthropic (États-Unis) mais pas celui de Mistral AI au point d'accès UE (non
vérifié) : d'où « et de stockage, lorsque le fournisseur s'y engage », et jamais « les lieux de
stockage et de calcul » sans condition. Un lieu de stockage de Mistral AI ne s'ajoute au texte
injecté qu'une fois vérifié pour le point d'accès utilisé.

### 2.3 Article 6 — un nouveau sous-traitant ultérieur

L'article 6 engage l'Éditeur à **informer le Client de tout ajout de sous-traitant ultérieur, avec
un préavis raisonnable**, pour lui permettre d'émettre des objections. Mistral AI est un ajout.
Décision d'Eliot (12/10/2026) : les testeurs ont été prévenus de longue date ; activation juste
après la mise en ligne.

---

## 3. `securite.html` (page « Sécurité ») — publié le 12/10/2026

### 3.1 Encadré « L'essentiel » (haut de page)

Avant :

> … Et vos contenus ne sont **jamais utilisés pour entraîner un modèle d'IA**, ni le nôtre, ni
> celui d'un tiers.

Publié :

> … Et vos contenus ne sont **pas utilisés pour entraîner les modèles d'IA**
> {{AI_ENTRAINEMENT_FOURNISSEURS}}.

### 3.2 Section 3 « Le modèle d'IA et vos données », première puce

Avant :

> **Aucun entraînement sur vos données** : les contenus envoyés au modèle ne sont **jamais utilisés
> pour entraîner un modèle d'IA**. Leur conservation éventuelle par le fournisseur de l'IA est
> encadrée par ses conditions applicables à l'API ; le fournisseur et sa localisation figurent dans
> le DPA (annexe 3).

Publié :

> **Aucun entraînement sur vos données** : les contenus envoyés à l'IA ne sont **pas utilisés pour
> entraîner un modèle d'IA** ({{AI_ENTRAINEMENT}}). {{AI_ROLES}} La conservation est encadrée par
> les conditions applicables à l'API ({{AI_CONSERVATION}}). Fournisseurs, sous-traitants et lieux de
> calcul : voir le DPA (annexe 3).

### 3.3 Section 3, deuxième puce « Strict nécessaire » (publiée le 12/10/2026)

Publiée dans `app/static/legal/securite.html` le 12/10/2026 : elle ne dépend pas de Mistral (lecture
intégrale du dossier).

> **Strict nécessaire** : on transmet à l'IA le dossier du marché que vous analysez (lu en entier,
> pour ne rien manquer) et, pour la rédaction, les extraits utiles de vos documents. Jamais
> l'ensemble de votre espace. Les noms de vos salariés sont remplacés par des étiquettes avant tout
> envoi.

---

## 4. Politique de confidentialité (`docs/legal/politique-confidentialite.md`, § 6 et § 7) — publié le 12/10/2026

### 4.1 Tableau du § 6, ligne « IA », colonne « Données concernées »

Avant : « contenus soumis à l'analyse (extraits de DCE, données d'entreprise) ».

Publié (la lecture intégrale remet tout le dossier du marché) :

> dossiers de consultation analysés (lus en entier), questions posées, données d'entreprise utiles
> à la rédaction (noms des salariés remplacés par des étiquettes avant tout envoi)

### 4.2 Nouveau paragraphe, juste sous le tableau du § 6

> **Intelligence artificielle.** {{AI_ROLES}} Les contenus envoyés ne sont pas utilisés pour
> entraîner un modèle d'IA ({{AI_ENTRAINEMENT}}). La conservation est encadrée par les conditions
> applicables à l'API ({{AI_CONSERVATION}}).{{AI_SOUS_TRAITANTS_MISTRAL}} Lieux de calcul (et de
> stockage, lorsque le fournisseur s'y engage) : tableau ci-dessus.

### 4.3 § 7, liste des garanties appropriées, première puce

> la signature de **clauses contractuelles types** (CCT / SCC) adoptées par la Commission
> européenne{{AI_CCT_MISTRAL}} ;

---

## 5. Ordre des opérations (Eliot)

Les pages étant déjà publiées et exactes dans toutes les configurations, l'activation ne demande
plus de publication le même jour.

1. **Console Mistral (admin.mistral.ai)** : désinscription de l'entraînement **faite**
   (Admin > Privacy > « Anonymous improvement data »). `MISTRAL_ENTRAINEMENT_DESACTIVE=1` **posé**
   dans Railway. Restent, sans urgence :
   - demander l'option **« zéro conservation »** (à la discrétion de Mistral). Tant qu'elle n'est pas
     confirmée, les pages disent « jusqu'à 30 jours glissants » ;
   - relire trust.mistral.ai/subprocessors (page en JavaScript, non lue automatiquement). Les pages
     n'en nomment aucun et renvoient vers cette liste.
2. **Mise en ligne** du code (rien à poser : sans `MISTRAL_ACTIF=1`, tout part chez Claude Sonnet 5.5
   et les pages ne parlent que d'Anthropic).
3. **Juste après** : poser **`MISTRAL_ACTIF=1`** dans Railway (et retirer `LLM_PROVIDER` s'il est
   posé), puis redémarrer. Les pages décrivent alors d'elles-mêmes les deux fournisseurs.
4. Ouvrir **`GET /api/admin/ia/diagnostic`** (compte administrateur) et vérifier :
   - `fournisseurs.mistral.variable` = `MISTRAL_API_KEY_ADJUGO` ;
   - `fournisseurs.mistral.etat` = `actif` ;
   - `large4_sur_ue` = `true` ;
   - `point_acces.zone` = `ue` ;
   - aucun message en attente.

   Puis relire `/dpa`, `/securite` et `/confidentialite`. Si `large4_sur_ue` vaut `false` (Large 4
   encore absent du point d'accès européen), Mistral passe par le point d'accès mondial, **sans
   engagement de lieu de calcul**, et les pages le disent d'elles-mêmes. Pour l'éviter :
   `MISTRAL_POINT_ACCES=ue` (les analyses partent alors chez Claude tant que le modèle n'y est pas
   servi).

---

## 6. Ce que le serveur injecte (à relire avant de déployer)

Les pages contiennent des repères remplis par le serveur à chaque affichage. Ce texte part **avec le
code**. Les rôles suivent le routage effectif (y compris les variables `LLM_TACHE_*` : une tâche
déplacée chez l'autre fournisseur change la phrase d'elle-même). Testé dans les quatre
configurations par `tests/test_pages_juridiques_ia.py`.

| Repère | Pages | Mistral non activé (ou `LLM_PROVIDER=anthropic`) | Mistral activé (Anthropic + Mistral AI) | `LLM_PROVIDER=mistral`, Mistral activé |
|---|---|---|---|---|
| `{{AI_PROVIDER}}` / `{{AI_PRODUCT}}` | DPA, confidentialité | Anthropic, PBC / Claude API | Anthropic, PBC et Mistral AI / Claude API ; La Plateforme de Mistral AI | Mistral AI / La Plateforme |
| `{{AI_ROLES}}` | DPA, sécurité, confidentialité | « Anthropic (Claude API) intervient pour la lecture des dossiers, les questions et la rédaction. » | « Anthropic (Claude API) intervient pour les questions sur les dossiers et la rédaction ; Mistral AI (La Plateforme), pour la lecture et l'analyse des dossiers ; chacun prend le relais de l'autre en cas de panne ou d'erreur. » | « Mistral AI (La Plateforme) intervient pour la lecture des dossiers, les questions et la rédaction. » |
| `{{AI_ENTRAINEMENT}}` | DPA, sécurité, confidentialité | « Anthropic : jamais sans autorisation » | « Anthropic : jamais sans autorisation ; Mistral AI : utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur » | « Mistral AI : utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur » |
| `{{AI_ENTRAINEMENT_FOURNISSEURS}}` | sécurité (« L'essentiel ») | « de notre fournisseur, Anthropic » | « de nos fournisseurs, Anthropic et Mistral AI (chez Mistral AI, nous avons désactivé cette utilisation sur notre compte) » | « de notre fournisseur, Mistral AI (nous avons désactivé cette utilisation sur notre compte) » |
| `{{AI_CONSERVATION}}` | DPA, sécurité, confidentialité | « Anthropic : 30 jours en règle générale, jusqu'à 2 ans pour les contenus signalés pour non-respect de ses règles d'usage » | idem « ; Mistral AI : jusqu'à 30 jours glissants, pour la surveillance des abus » | « Mistral AI : jusqu'à 30 jours glissants, pour la surveillance des abus » |
| `{{AI_SOUS_TRAITANTS_MISTRAL}}` | DPA, confidentialité | (vide) | « Mistral AI s'appuie sur ses propres sous-traitants techniques, dont la liste à jour est publiée sur son centre de confiance (https://trust.mistral.ai/subprocessors). » | idem |
| `{{AI_CCT_MISTRAL}}` | confidentialité (§ 7) | (vide) | « (pour Mistral AI : celles prévues par son accord de sous-traitance) » | idem |
| `{{AI_LOCATION_FULL}}` | confidentialité (tableau) | États-Unis pour le stockage (API standard api.anthropic.com) ; calcul possiblement hors des États-Unis (routage mondial d'Anthropic) — encadré par CCT | Anthropic : comme à gauche. Mistral AI, **point d'accès UE** : calcul dans des centres de données de l'Union européenne et de l'AELE (api.eu.mistral.ai), données de fonctionnement du compte possiblement hors de cette zone. **Point d'accès mondial** : sans engagement de lieu de calcul, possiblement hors de l'Union européenne ; stockage dans l'Union européenne par défaut. Puis : sous-traitants propres de Mistral AI (renvoi vers sa liste, aucun nom), CCT, désinscription faite | Mistral AI seul, selon le point d'accès |
| `{{AI_LOCATION_SHORT}}` | DPA (tableau) | États-Unis pour le stockage, calcul possiblement hors des États-Unis (CCT) | « Anthropic : … ; Mistral AI : Union européenne et AELE pour le calcul (api.eu.mistral.ai) » ou « lieu de calcul non garanti, possiblement hors Union européenne », puis « ; sous-traitants de Mistral AI : liste publiée sur trust.mistral.ai/subprocessors (CCT) » | Mistral AI seul, selon le point d'accès |
| `{{AI_TRANSFER_MENTION}}` | confidentialité (§ 7) | « le fournisseur d'IA (Anthropic, États-Unis ; calcul possiblement dans d'autres pays) pour l'analyse et la génération de documents, » | « le fournisseur d'IA Anthropic (…) pour …, et en relais pour …, le fournisseur d'IA Mistral AI et ses propres sous-traitants techniques pour …, et en relais pour … — calcul dans l'Union européenne et l'AELE — » (ou « — calcul possiblement hors de l'Union européenne — ») | Mistral AI et ses propres sous-traitants techniques, selon le point d'accès |

État de la désinscription : la phrase « active par défaut […] non encore confirmée » ne peut plus
s'afficher (Mistral ne reçoit rien sans `MISTRAL_ENTRAINEMENT_DESACTIVE=1`) ; elle reste dans le code
par prudence.

Le mot « souverain » et l'indicateur `"sovereign": true` ont été retirés : la route publique
`/api/llm/info` renvoie `"sovereign": false`. Formulations honnêtes possibles (comparatif, § 7.3) :

- « calcul de la lecture des dossiers dans l'Union européenne et l'AELE » : seulement avec le point
  d'accès UE, et jamais « UE » seule ;
- « IA hébergée en France » : jamais avec ces deux fournisseurs ;
- l'application elle-même (Railway, Cloudflare R2, Sentry) reste chez des sociétés américaines.

Reste à décider par Eliot (hors du périmètre de cette publication) : le titre de la page Sécurité
(« Sécurité & souveraineté des données ») et la phrase d'introduction de sa section 3 (« Adjugo
s'appuie sur un modèle d'IA ») n'ont pas été touchés.
