# Lecture intégrale du dossier du marché

Consigne du fondateur : « on ne peut pas avoir que la moitié de l'appel d'offres analysé ».

Ce document a deux parties :

1. le **diagnostic** du chemin d'un dossier de consultation (DCE), de l'import jusqu'à chaque
   usage de l'IA, relevé sur la branche `redaction/v1` (commit `f942a1c`), avec ce qui est perdu
   à chaque étape ;
2. ce qui a été **changé** pour que chaque pièce soit lue en entier, stockée, et donnée en entier
   (ou pièce par pièce) à l'IA, et ce que cela coûte.

---

## 1. Diagnostic (état au commit f942a1c)

Les numéros de ligne renvoient au code de ce commit.

### 1.1 Import

| Étape | Où | Ce qui se passe | Ce qui est perdu |
|---|---|---|---|
| Envoi du fichier | `app/core/uploads.py:15` (`DOSSIER_MAX_BYTES = 50 Mo`) | Lecture bornée à 50 Mo, 413 au-delà. | Rien pour un dossier courant. Au-delà de 50 Mo zippés : refus net (signalé). |
| Analyse d'un dossier importé | `app/routers/sourcing.py:429-508` (`/analyze-upload`) et `:511-574` (`/reanalyze`) | `extract_dce_text(…, max_chars=120000, with_pieces=True)` (l. 450 et 540), dans la requête HTTP. | Tout ce qui dépasse les plafonds ci-dessous. |
| Archivage | `sourcing.py:489-496` (`replace_in_dossier`, dossier « DCE ») | Le fichier d'origine est rangé tel quel dans le dossier du marché. | Rien (mais il est relu à chaque fois avec les mêmes plafonds). |

### 1.2 Extraction du texte (`app/services/analysis.py`)

| Plafond | Où | Effet | Signalé ? |
|---|---|---|---|
| Formats lus dans un ZIP : `.pdf .docx .txt .md .csv` | `analysis.py:1022` (`_ZIP_OKEXT`), `:1062` | Les tableurs (`.xlsx`, `.ods`, souvent le bordereau de prix ou la DPGF), `.odt`, `.doc`, `.xls`, `.rtf`, les images scannées sont **ignorés**. | **Non** : la pièce n'apparaît nulle part. |
| 25 fichiers exploités par archive | `analysis.py:423` (`ZIP_MAX_FILES`), `:1055` | Au-delà de 25 pièces, la lecture s'arrête. Un dossier alloti de 40 pièces perd les 15 dernières (souvent les CCTP de lots, lus en dernier). | **Non**. |
| Plafond de caractères : 120 000 par pièce, 240 000 pour toute l'archive (`read_cap = 2 × max_chars`) | `analysis.py:1044`, `:1055`, `:1079` | Une pièce est coupée à 120 000 caractères (≈ 40 pages) ; l'archive s'arrête à 240 000. | En partie : la pièce coupée est dite « lue en partie », les pièces jamais ouvertes ne sont pas listées. |
| PDF seul : arrêt à `max_chars` | `analysis.py:1126-1140`, `extract_text_from_pdf` `:615-703` | Un CCTP de 300 pages en PDF unique est lu sur ses 40 premières pages. | « lu en partie », sans dire combien de pages manquent. |
| 600 pages par PDF | `analysis.py:428` | Au-delà, pages ignorées. | « lu en partie ». |
| Temps : 25 s pour tout le dossier | `analysis.py:429`, `:448` | Un gros dossier est coupé au bout de 25 s de lecture. | « lu en partie », sans raison. |
| Contenu décompressé des PDF : 12 Mo par dossier, 2 Mo par page | `analysis.py:431-433` | Pages de plans sautées ; au-delà de 12 Mo, toutes les pages suivantes sautées. | « lu en partie », sans raison. |
| Pages sans texte dans un PDF texte (page scannée insérée, annexe signée) | `extract_text_from_pdf` | Lues comme vides. L'OCR n'est tenté que si **tout** le PDF a moins de 30 caractères (`:1091`, `:1131`). | **Non**. |
| OCR : 15 pages par PDF, 30 pour l'archive | `analysis.py:436-437`, `_ocr_pdf` `:750` | Un scan de 40 pages est lu sur 15. | « lu en partie », sans raison. |
| Pièces de moins de 30 caractères | `analysis.py:1101` | Écartées. | Non (normal pour un fichier vide, mais ni le scan illisible ni le fichier protégé ne sont nommés). |
| Fichier trop gros décompressé (40 Mo), ZIP dans un ZIP dans un ZIP, compression bzip2/LZMA | `analysis.py:1065-1072` | Fichier ignoré. | Seulement si **aucune** pièce n'a pu être lue (message d'erreur global). |
| PDF protégé par mot de passe | `extract_text_from_pdf` (exception) | Texte « Erreur extraction PDF », pièce écartée. | **Non**. |
| Word : 20 000 paragraphes ou lignes de tableau | `analysis.py:814`, `:960-971` | Coupé sans le dire. | **Non** (la pièce est dite « lue en entier »). |
| Assemblage | `dce_pieces.compose`, `extract_dce_text` `:1178` | Règlement et cadre de réponse en tête et en entier, partage équitable du reste du plafond de 120 000 caractères. | Ce qui dépasse 120 000 caractères au total. |

### 1.3 Ce qui est stocké

| Quoi | Où | Taille |
|---|---|---|
| Le fichier importé (ZIP, PDF…) | dossier « DCE » du marché (`Document`) | entier |
| Le texte du dossier | `ai_analysis["dce_excerpt"]`, `sourcing.py:468` et `:556` | **30 000 premiers caractères** du texte assemblé |
| Les pièces lues | `ai_analysis.details.grille_notation.lecture.pieces` | nom, type, « lue en entier » ; **30 pièces au plus** (`grille_notation.py:1010`) |

Aucun texte intégral n'est conservé : chaque réutilisation relit le fichier avec les mêmes plafonds
(ré-analyse `sourcing.py:540`, convention de groupement `groupement_convention.py:419`).

### 1.4 Ce que reçoit chaque usage de l'IA

| Usage | Où | Ce que l'IA reçoit | Ce qui est perdu |
|---|---|---|---|
| **Analyse** d'un dossier importé | `analysis.build_user_prompt` `:332`, `select_dce_content` `:146` | Au-delà de 30 000 caractères : règlement + cadre en entier jusqu'à 60 000 caractères (`SELECT_PRIORITY_MAX`, `:142`), puis des **fenêtres de 700 caractères autour de mots sensibles** (pénalités, garanties, critères, délais… `_RISK_TERMS` `:20`) dans les autres pièces, au moins 24 000 caractères (`:143`). Environ **84 000 caractères au plus**. | Tout le reste : le contenu technique des CCTP, les lignes du bordereau, une exigence placée hors des mots repérés. Sur un dossier de 600 000 caractères, l'IA en voit environ 14 %. |
| **Questions-réponses** | `sourcing.py:663-693` | `dce_excerpt[:14000]` (l. 681) : les **14 000 premiers caractères** (en pratique le début du règlement). | Le CCAP, le CCTP, le bordereau, la fin du règlement : l'IA répond « absent du dossier » à tort. Limite : 90 questions par heure **et par adresse IP** (l. 662), rien par organisation. |
| Questionnaire | `agents/questionnaire.py` | Le savoir-faire de l'entreprise seulement (pas le dossier). | Sans objet. |
| Chiffrage | `agents/chiffrage.py:31-60`, `routers/chiffrage.py:76` | Les champs extraits par l'analyse (`details`). | Hérite des pertes de l'analyse. |
| Rédaction rapide (moteur A) | `agents/redaction.py:264` | Les champs de l'analyse et la grille de notation. | Hérite des pertes de l'analyse. |
| Rédaction depuis le savoir-faire (moteur B) | `routers/knowledge.py:131` puis `agents/memoire.py:48` | `extract_dce_text` au plafond par défaut (40 000), puis **24 000 caractères** pour lire les exigences. | Tout au-delà de 24 000 caractères. (Fichier en chantier dans la vague 2 : non modifié ici.) |
| Nom du mémoire | `memoire_export.py:92` | `dce_excerpt` (30 000 caractères). | Le nom n'est retrouvé que s'il est dans le début du dossier. |
| Convention de groupement | `groupement_convention.py:405-422` | Relecture du ZIP, 120 000 caractères. | Une clause de forme imposée au-delà. |
| Veille amont (délibérations) | `routers/amont.py:128`, `agents/amont.py:81` | 40 000 puis 18 000 caractères. | Hors du périmètre du DCE. |

### 1.5 Facturation au-delà du forfait

`billing_usage.py:17` lit `STRIPE_PRICE_OVERAGE` avec `getattr`, mais ce champ n'est pas déclaré
dans `Settings` (`app/core/config.py`) : une variable d'environnement non déclarée n'est pas lue
par pydantic-settings. Le dépassement est compté en base (`overage_count`) mais **jamais envoyé à
Stripe**. De plus :

- l'abonnement créé au paiement (`stripe_pay.py:33-41`) ne contient que le prix du forfait : même
  envoyés, les événements d'usage ne seraient rattachés à aucun prix facturé ;
- un remboursement (l'IA tombe après le débit, `quota.refund_analysis`) décrémente le compteur
  en base mais n'annule rien chez Stripe ;
- la détection du forfait (`stripe_pay.py:81` et `:227`) lit le **premier** élément de
  l'abonnement : avec un second prix (à l'usage), elle pouvait se tromper de forfait.

---

## 2. Ce qui change

### 2.1 Lecture de chaque pièce en entier (`app/services/dce_lecture.py`)

- **Toutes les pièces** d'une archive sont parcourues, règlement et cadre de réponse d'abord.
  Formats lus : PDF texte (page par page), Word `.docx` (tableaux, tableaux imbriqués, zones de
  saisie, encadrés), tableurs `.xlsx` et `.ods`, `.odt`, `.txt`, `.md`, `.csv` ; les pages
  scannées (dans un PDF texte ou un PDF entièrement scanné) et les images `.png/.jpg/.tif` passent
  par la reconnaissance de caractères (OCR) **en tâche de fond**, sous un budget de pages et de temps.
- **Rien n'est ignoré en silence.** Chaque pièce a un statut : *lue en entier*, *lue en partie*
  ou *non lue*, avec sa raison en clair : format non pris en charge (avec un conseil : « ancien format
  Word : enregistrez-le en .docx ou en PDF »), fichier protégé par un mot de passe, fichier abîmé,
  scan sans texte reconnu, pages de plan trop lourdes, temps de lecture écoulé, plafond technique
  atteint. Une pièce lue en partie dit combien de pages manquent et pourquoi
  (« 1 page sur 3 non lue : scan : aucun texte reconnu »). Les fichiers système d'une archive
  (`__MACOSX`, fichiers cachés) ne sont pas des pièces.
- **Plafonds techniques**, larges, réglables par variable d'environnement, et qui protègent le
  process unique (mémoire, temps, bombes de décompression : mêmes primitives bornées qu'avant) :

| Variable | Défaut | Rôle |
|---|---|---|
| `LECTURE_MAX_FICHIERS` | 400 | pièces lues dans une archive (avant : 25) |
| `LECTURE_MAX_MO_FICHIER` | 80 | Mo d'une pièce décompressée (avant : 40) |
| `LECTURE_MAX_MO_TOTAL` | 400 | Mo décompressés lus dans l'archive (avant : 160) |
| `LECTURE_MAX_CARACTERES_PIECE` | 3 000 000 | caractères d'une pièce (≈ 1 000 pages ; avant : 120 000) |
| `LECTURE_MAX_CARACTERES` | 6 000 000 | caractères du dossier (avant : 240 000) |
| `LECTURE_MAX_PAGES_PDF` | 5 000 | pages d'un PDF (avant : 600) |
| `LECTURE_MAX_MO_CONTENU_PDF` | 600 | Mo de contenu de pages décompressé (avant : 12) |
| `LECTURE_TEMPS_DIRECT_S` | 20 | secondes de lecture pendant la requête, sans OCR |
| `LECTURE_TEMPS_FOND_S` | 1 200 | secondes de lecture en tâche de fond, OCR compris |
| `LECTURE_OCR_MAX_PAGES` | 300 | pages en image lues par OCR (avant : 15 par PDF, 30 par archive) |

- **Deux temps.** La requête d'import lit le dossier sans OCR (20 s au plus). Si des pages en image
  restent à lire, si le temps est écoulé, ou si le dossier se lit en deux temps (§ 2.3), la suite part
  en **tâche de fond** (pool borné existant, `app/services/jobs.py`, non modifié) : la lecture
  reprend les pièces déjà lues en entier, lit le reste avec l'OCR, puis l'analyse. La progression se
  lit sur `GET /api/sourcing/lecture/{project_id}` (pièces lues, pages, parties analysées).

L'ancienne fonction `extract_dce_text` (plafonnée) reste pour les usages hors marché (savoir-faire,
délibérations) ; elle lit désormais aussi les `.xlsx`, `.ods`, `.odt` et les encadrés Word.

### 2.2 Texte intégral rangé avec le dossier (`app/services/dce_texte.py`)

- Le texte de chaque pièce (nom, type reconnu, statut, raison, caractères, pages, position de
  chaque page, texte) est rangé en **un fichier compressé** dans le stockage des fichiers du dossier
  (`storage.py`, clé `{propriétaire}/lecture/{uuid}.json.gz`), référencé par `Project.dce_file_key`
  (colonne existante : aucune migration, aucune nouvelle table).
- **Supprimé avec le marché** : `dce_file_key` est déjà traité par la purge de la corbeille des
  marchés (`rgpd._purge_trashed_projects`, `_tombstone_projects`), l'effacement du compte
  (`rgpd._erase_solo`) et le contrôle des références avant destruction (`rgpd._purge_files`). Un
  ré-import remplace le fichier précédent.
- **Export RGPD** : rubrique `texte_lu_des_dossiers` (pièce par pièce : nom, statut, caractères,
  pages, taille du fichier), comme les autres fichiers du dossier (métadonnées, sans recopier le texte).
- **Accès commun** pour tous les usages de l'IA (et pour l'atelier de rédaction à la fusion) :

| Fonction | Rend |
|---|---|
| `dce_pieces_text(project)` | les pièces avec leur texte intégral, statut, raison, pages (`page_starts`) |
| `dce_fulltext(project, max_chars=None)` | le texte complet « === nom === », règlement et cadre en tête |
| `dce_reglement(project)` | le texte du règlement de la consultation |
| `dce_texte_ou_extrait(project)` | `(texte, "integral")`, ou l'ancien extrait de 30 000 caractères `(texte, "extrait")` |
| `passages(project, question, k)` | les passages les plus pertinents de toutes les pièces (pièce, page) |
| `couverture(project)` | ce qui a été lu, et les pièces non lues avec leur raison |

- La convention de groupement (`groupement_convention.dce_text`) lit ce texte intégral.
- `ai_analysis["lecture"]` garde le résumé de la lecture (sans le texte) ;
  `ai_analysis["dce_excerpt"]` reste rempli (30 000 premiers caractères) pour les anciens usages.
- **Anciennes analyses** (sans texte intégral) : comportement inchangé, l'écran et les réponses
  invitent à ré-analyser ; la ré-analyse relit alors le dossier archivé en entier. Une ré-analyse
  du même fichier réutilise le texte déjà rangé (aucune relecture).

### 2.3 Analyse complète (`app/services/analyse_dossier.py`)

**Fenêtre de contexte et budget sûr.** Modèles actuels (non migrés) : Claude Sonnet 4.6
(`claude-sonnet-4-6`), fenêtre documentée de **1 000 000 de tokens**, 128 000 en sortie ;
Claude Haiku 4.5 (`claude-haiku-4-5`), **200 000 tokens**, 64 000 en sortie. On ne remplit pas la
fenêtre : le budget d'entrée sûr de l'analyse est `ANALYSE_BUDGET_TOKENS = 150 000` tokens (coût,
temps de réponse sous `LLM_TIMEOUT = 180 s`, fiabilité des très longs contextes, et marge × 6 sur la
fenêtre), dont on retire une marge de 10 % (`ANALYSE_MARGE`), la consigne, le profil et les
critères, avec une conversion **prudente** de 3,0 caractères par token (`ANALYSE_CARACTERES_PAR_TOKEN` ;
le français chiffré varie de 3,0 à 3,6) :

    caractères de dossier = (min(150 000, fenêtre − 6 000 de sortie) × 0,90 − consigne/3,0) × 3,0
                          ≈ (135 000 − 4 000) × 3,0 ≈ 390 000 caractères

- **Dossier ≤ ≈ 390 000 caractères : lecture d'un seul tenant.** L'IA reçoit le dossier ENTIER,
  pièce par pièce (« === nom === »), règlement et cadre en tête, précédé de la liste des pièces non
  lues (« si une information n'est pas dans le texte fourni, écris qu'elle n'a pas été trouvée dans
  les pièces lues — jamais qu'elle n'existe pas »). Toutes les citations sont vérifiées contre le
  texte intégral (`citation_guard`), comme avant.
- **Au-delà : lecture en deux temps.** (1) Chaque pièce (sauf règlement et cadre s'ils tiennent en
  entier dans la synthèse) est lue **séparément** par Claude Haiku 4.5, découpée en parties de
  40 000 tokens au plus (`ANALYSE_SEGMENT_TOKENS`) : l'IA relève les informations utiles, chacune
  avec la phrase exacte ; une phrase introuvable dans la pièce fait **écarter** l'information
  (`citation_guard`), la page est retrouvée par Adjugo (pas par l'IA). (2) Une synthèse (Sonnet 4.6,
  même consigne et même format qu'avant) reçoit le règlement et le cadre en entier, puis ce qui a
  été relevé dans toutes les autres pièces. Chaque pièce passe donc par l'IA. Parallélisme : 3 appels
  (`ANALYSE_PARALLELE`), sous le sémaphore IA global ; espace facturé et compteur de coût propagés
  dans les fils (`map_in_context`). Plafond : 80 parties (`ANALYSE_MAX_APPELS`) — au-delà, les
  parties non analysées sont **listées** dans la couverture.
- **Couverture dans l'analyse** : `ai_analysis["couverture"]` = « Dossier lu en entier : N pièces,
  P pages. », ou « Dossier lu en partie : … » avec la liste des pièces non lues ou lues en partie et
  leur raison ; en deux temps, les parties que l'IA n'a pas pu exploiter.
- **Quota** : toujours **une** analyse par import, quel que soit le nombre d'appels ; remboursée si
  l'IA tombe (y compris une réponse coupée par le plafond de sortie, auparavant facturée comme un
  verdict « à étudier »).
- **Coût mesuré** : `cost_meter("analyse du dossier (mode, N pièces, C caractères)")` journalise
  appels, tokens (cache compris) et coût estimé.

**Cache de prompt.** Le SDK épinglé (`anthropic==0.34.0`) transmet tel quel un bloc
`{"type": "text", "text": …, "cache_control": {"type": "ephemeral"}}` (clé conservée, vérifié dans
`anthropic/_utils/_transform.py`) ; le cache est disponible sans en-tête bêta côté API ; le type
`Usage` du SDK accepte les champs supplémentaires `cache_read_input_tokens` /
`cache_creation_input_tokens` (lus par `llm._track_usage` et comptés par `cost_meter`).
Utilisé : la consigne de l'analyse (identique pour tous les clients, ≈ 2 600 tokens ≥ minimum de
1 024 pour Sonnet 4.6) et le règlement dans les questions-réponses (préfixe identique d'une question
à l'autre ; minimum 4 096 tokens pour Haiku 4.5, en dessous rien n'est mis en cache, sans erreur).
**Non utilisé** sur le dossier lui-même dans l'analyse : écrire le cache coûte 1,25 × et une
ré-analyse dans les 5 minutes est rare. Coupure : `LLM_PROMPT_CACHE=0`. Mistral ignore le marquage.

### 2.4 Questions-réponses sur tout le dossier (`/api/sourcing/ask`)

- Recherche des passages pertinents dans **toutes** les pièces (BM25 de `app/services/rag.py`, sans
  IA ni réseau, index mis en cache mémoire par dossier), 8 passages de ≈ 1 400 caractères ; le
  règlement est **toujours** remis (en entier jusqu'à 60 000 caractères, en cache de prompt).
- La réponse cite la pièce et la page ; chaque phrase citée est vérifiée contre le texte
  (`citation_guard`) : une phrase non retrouvée n'est jamais montrée comme une citation, et l'écran le
  dit. Si l'information n'est pas dans le dossier, la réponse le dit et nomme les pièces non lues.
- **Borne hors quota** par organisation et par jour (heure de Paris) : 15 (essai expiré,
  historique), 50 (Pro et essai), 120 (Business) ; réglable (`PLAN_LIMITS[…]["questions_jour"]`,
  ou `QUESTIONS_PAR_JOUR` pour tous). Compteur **persistant** dans la table `jobs` existante
  (une ligne `question_dossier` par question, sans le texte de la question, purgée après 7 jours) ;
  une question dont l'IA n'a pas répondu ne compte pas. La limite par adresse IP reste.

### 2.5 Facturation du dépassement

- `STRIPE_PRICE_OVERAGE` et `STRIPE_METER_EVENT_OVERAGE` (défaut `adjugo_analyse_overage`) sont
  **déclarés** dans `Settings` : la variable d'environnement est lue.
- Chemin vérifié et testé (Stripe simulé) : analyse au-delà du forfait, paiement à l'usage activé et
  facturable → `overage_count` + 1 → `stripe.billing.MeterEvent.create` avec un identifiant unique ;
  remboursement → `MeterEventAdjustment` d'annulation de cette unité.
- Le paiement d'un forfait ajoute le prix à l'usage à l'abonnement ; l'activation du paiement à
  l'usage l'ajoute à un abonnement plus ancien (sinon refus clair) ; la détection du forfait ignore
  le prix à l'usage, quel que soit son rang.
- À faire par Eliot dans Stripe : créer le compteur (événement `adjugo_analyse_overage`, agrégation
  somme) et le prix à l'usage de 5 € HT rattaché, puis renseigner `STRIPE_PRICE_OVERAGE`.

### 2.6 Écrans

- Carte d'analyse : la couverture (« Dossier lu en entier : 12 pièces, 418 pages. » ou les pièces
  non lues et pourquoi), bulle (i) d'explication ; une ancienne analyse invite à ré-analyser.
- « Pièces lues » (carte « Comment vous serez noté ») : lue en entier (avec le nombre de pages), lue
  en partie ou non lue, avec la raison.
- Réponse d'une question : la phrase du dossier, sa pièce et sa page.
- Gros dossier : la progression de la lecture (« Lecture du dossier : 7 pièces lues sur 18,
  412 pages… », puis « Analyse : 3 parties lues par l'IA sur 12… ») ; le suivi reprend si l'on
  revient sur le marché.

---

## 3. Coût de l'IA (tarifs publics, 3,3 caractères par token en moyenne)

Sonnet 4.6 : 3 $ / 15 $ par million de tokens (entrée / sortie) ; Haiku 4.5 : 1 $ / 5 $ ; lecture
du cache 0,1 ×, écriture 1,25 ×. Les sorties sont estimées (≈ 3 500 tokens pour l'analyse,
≈ 1 500 par partie lue, ≈ 300 par réponse) ; les relevés de `cost_meter` les remplaceront.

**Une analyse (une seule débitée au quota)**

| Dossier | Mode | Calcul | Coût |
|---|---|---|---|
| ZIP courant, 50 000 caractères | d'un seul tenant | (10 400 + 50 000) / 3,3 = 18 300 tokens × 3 $ + 3 500 × 15 $ | ≈ 0,11 $ |
| 150 000 caractères | d'un seul tenant | 48 600 × 3 $ + 3 500 × 15 $ | ≈ 0,20 $ |
| ≈ 390 000 caractères (limite) | d'un seul tenant | 121 000 × 3 $ + 3 500 × 15 $ | ≈ 0,42 $ (pire cas ≈ 0,50 $) |
| 600 000 caractères, 12 pièces (dossier du test) | deux temps | Haiku : 179 000 × 1 $ + 15 000 × 5 $ = 0,25 $ ; synthèse : 35 000 × 3 $ + 3 500 × 15 $ = 0,16 $ | ≈ 0,41 $ |
| 2 000 000 caractères | deux temps (17 parties) | Haiku : 0,74 $ ; synthèse : 0,21 $ | ≈ 0,95 $ |
| 6 000 000 caractères (plafond technique) | deux temps (50 parties) | Haiku : 2,22 $ ; synthèse : 0,41 $ | ≈ 2,6 $ (2,2 €) |

Avant : au plus 0,15 $ (84 600 caractères), mais l'IA ne voyait qu'une partie du dossier. Même au
plafond technique, une analyse reste sous le prix d'une analyse du forfait Pro (129,99 € / 30 =
4,33 €) et sous le prix du dépassement (5 € HT).

**Une question**

| Cas | Calcul | Coût |
|---|---|---|
| Règlement de 20 000 caractères + 8 passages, sans cache | 10 000 tokens × 1 $ + 300 × 5 $ | ≈ 0,012 $ |
| Même chose, question suivante dans les 5 minutes (règlement lu dans le cache) | 6 100 × 0,1 $ + 3 900 × 1 $ + 300 × 5 $ | ≈ 0,006 $ |
| Règlement de 60 000 caractères, sans cache | 22 000 × 1 $ + 300 × 5 $ | ≈ 0,024 $ |

Avant : 0,0063 $ pour les 14 000 premiers caractères seulement. Borne par jour, pire cas (règlement
de 60 000 caractères, sans cache, 22 jours ouvrés) : Pro 50 × 0,024 $ × 22 ≈ 26 $ (22 €) par mois et
par organisation ; Business 120 × … ≈ 63 $ (54 €) ; usage courant (cache, ≈ 10 questions par jour)
≈ 1,3 $ par mois. Avant, seule l'adresse IP limitait : ≈ 84 € par mois et par adresse.
