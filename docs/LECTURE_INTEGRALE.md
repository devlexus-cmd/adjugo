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
  Formats lus : PDF texte (page par page), Word `.docx` et `.docm`, tableurs `.xlsx`, `.xlsm` et
  `.ods`, `.odt`, `.txt`, `.md`, `.csv` ; les pages scannées (dans un PDF texte ou un PDF entièrement
  scanné) et les images `.png/.jpg/.tif` passent par la reconnaissance de caractères (OCR) **en
  tâche de fond**, sous un budget de pages et de temps.
- **Word lu en entier** : le texte de chaque paragraphe vient de tous ses descendants, et non plus
  de `Paragraph.text` de python-docx (qui ne lit que les fragments directs). Sont donc lus : les
  zones de saisie en ligne, dans une cellule ou autour de lignes de tableau (`w:sdt`), les insertions
  d'une modification suivie non acceptée (`w:ins`, `w:moveTo` ; le texte supprimé, `w:del` et
  `w:moveFrom`, ne l'est pas), les champs (`w:fldSimple`, résultat des champs complexes), les liens,
  les tableaux imbriqués et les encadrés ; puis, chacun dans sa rubrique en fin de pièce, les notes de
  bas de page et de fin (appel « (note 1) » à sa place dans le texte), les en-têtes et pieds de page
  (sans doublons) et le texte des schémas SmartArt.
- **PDF** : une page qui partage son flux de contenu avec une autre (PDF optimisé, « `/Fm0 Do` » sur
  chaque page) n'est sautée comme doublon que si ses **ressources** sont aussi les mêmes (même objet,
  ou mêmes références écrites dans la page) ; elle reprend alors le texte et l'état de la page
  identique. Une page **scannée qui porte une ligne tapée** (bandeau « Annexe 2 – document numérisé »,
  tampon de la plateforme) est envoyée à l'OCR : moins de 200 caractères tapés et une image qui couvre
  au moins la moitié de la page (surface calculée pendant la lecture, formulaires compris) ; le texte
  reconnu est précédé du bandeau s'il n'y figure pas déjà. Les numéros de page restent justes quand le
  PDF commence par des pages sans texte. Une pièce coupée par le plafond de caractères le dit
  (« texte trop long »), plus « trop de pages ».
- **Tableurs** (contrôle des bugs, octobre 2026) : une cellule sans adresse (« r », facultative dans le
  format) suit la précédente ; avant, toutes les cellules sans adresse d'une ligne s'écrasaient dans la
  première colonne et la pièce était quand même dite « lue en entier ». Une cellule au format date ou heure
  est écrite « 15/12/2026 », « 15/12/2026 09:30 » ou « 09:30 », et non comme le nombre de jours que le
  tableur enregistre (« 46371 »), d'après les styles du classeur (formats intégrés et personnalisés, base
  1904 comprise) ; une durée cumulée (« [h]:mm »), un nombre sans format date et une date d'avant mars 1900
  restent le nombre enregistré.
- **Pièces nommées par leur chemin** dans l'archive, sans le dossier commun à toutes les pièces :
  dans un dossier rangé par lots, « LOT 02 - Eclairage/CCTP.pdf » et non deux « CCTP.pdf » (en-têtes
  remis à l'IA, sources des réponses, liste des pièces lues) ; dans une archive à plat, le nom du
  fichier. Le type de pièce est toujours reconnu sur le nom du fichier.
- **Fichiers Office protégés** : un `.docx`, `.xlsx`, `.odt` ou `.ods` enregistré avec un mot de
  passe (conteneur chiffré, ou contenu OpenDocument chiffré) est signalé « fichier protégé par un mot
  de passe : demandez à l'acheteur une version sans mot de passe » (et non plus « trop volumineux »
  ou « abîmé »).
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
  en **tâche de fond** (§ 2.7) : la lecture reprend les pièces déjà lues en entier, lit le reste avec
  l'OCR, puis l'analyse. La progression se lit sur `GET /api/sourcing/lecture/{project_id}` (pièces
  lues, pages, parties analysées).

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
| `dce_reglement(project)` | le texte de **tous** les règlements de la consultation (RC, RC modificatif, RC de chaque lot), le modificatif en premier, chacun sous « === nom === » s'il y en a plusieurs |
| `reglements(pieces)` | les pièces « règlement », modificatifs en premier |
| `dce_texte_ou_extrait(project)` | `(texte, "integral")`, ou l'ancien extrait de 30 000 caractères `(texte, "extrait")` |
| `passages(project, question, k, exclude_pieces=…)` | les passages les plus pertinents de toutes les pièces (pièce, page), recherche sans accents, sans casse et sans pluriels (« penalites » retrouve « pénalités ») ; `exclude_pieces` écarte les pièces déjà remises en entier |
| `couverture(project)` | ce qui a été lu, et les pièces non lues avec leur raison |

- La convention de groupement (`groupement_convention.dce_text`) lit ce texte intégral.
- Le même fichier garde, pour un dossier lu en deux temps, les **informations relevées par l'IA
  partie par partie** (`analyse_parties`, phrases vérifiées, clé = empreinte du texte de la partie, de
  la consigne et du modèle) : une nouvelle analyse du même dossier ne relit que les parties
  manquantes (§ 2.3). Supprimées avec le texte.
- **Mémoire bornée** (process unique) : le cache des derniers dossiers lus compte le texte à
  2 octets par caractère et l'index de recherche à 11 octets par caractère (mesuré avec `tracemalloc`
  sur 3 millions de caractères au vocabulaire très varié : 10,7 ; construit en ≈ 2 s), dans
  `LECTURE_CACHE_MO` = 200 Mo, et garde au plus 4 index. Le cache des textes normalisés pour la
  vérification des citations est borné à 12 millions de caractères.
- `ai_analysis["lecture"]` garde le résumé de la lecture (sans le texte) ;
  `ai_analysis["dce_excerpt"]` reste rempli (30 000 premiers caractères) pour les anciens usages.
- **Anciennes analyses** (sans texte intégral) : comportement inchangé, l'écran et les réponses
  invitent à ré-analyser ou ré-importer le dossier ; la ré-analyse relit alors le dossier archivé en entier. Une ré-analyse
  du même fichier réutilise le texte déjà rangé (aucune relecture).

### 2.3 Analyse complète (`app/services/analyse_dossier.py`)

**Fenêtre de contexte et budget sûr.** Modèles (routage par tâche du 12/10/2026, `app/services/llm.py`) :
analyse et lecture des pièces par Mistral Large 4 (`mistral-large-4`, fenêtre de **1 000 000 de
tokens**), secours Claude Sonnet 5.5 (`claude-sonnet-5-5`, 1 000 000 de tokens, ≈ +30 % de tokens
pour le même texte). Ancien routage (`LLM_ROUTAGE=ancien`) : Claude Sonnet 4.6
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
  entier dans la synthèse) est lue **séparément** par l'IA (tâche `lecture_pieces` : Mistral Large 4 ;
  ancien routage : Claude Haiku 4.5), découpée en parties de
  40 000 tokens au plus (`ANALYSE_SEGMENT_TOKENS`) : l'IA relève les informations utiles, chacune
  avec la phrase exacte ; une phrase introuvable dans la pièce fait **écarter** l'information
  (`citation_guard`), la page est retrouvée par Adjugo (pas par l'IA). (2) Une synthèse (tâche `analyse` :
  Mistral Large 4 ; ancien routage : Sonnet 4.6,
  même consigne et même format qu'avant) reçoit le règlement et le cadre en entier, puis ce qui a
  été relevé dans toutes les autres pièces. Chaque pièce passe donc par l'IA. Parallélisme : 3 appels
  (`ANALYSE_PARALLELE`), sous le sémaphore IA global ; espace facturé et compteur de coût propagés
  dans les fils (`map_in_context`). Plafond : 80 appels (`ANALYSE_MAX_APPELS`) — au-delà, les
  parties non analysées sont **listées** dans la couverture.
- **Petites pièces regroupées** : les parties voisines sont lues dans un même appel, chacune sous
  « Pièce : nom », jusqu'à 120 000 caractères et 12 pièces (`ANALYSE_GROUPE_MAX_PIECES`) ; chaque
  citation est vérifiée dans la pièce qu'elle nomme (ou les autres pièces de l'appel). Un dossier de
  RC + 12 CCTP + 90 plans d'une page (470 000 caractères) : 10 appels au lieu de 103, plus aucun plan
  « non analysé (plafond technique) ».
- **Réponse coupée** : la consigne demande 40 informations au plus (≈ 5 200 tokens) sous un plafond
  de sortie de 8 000 tokens (`ANALYSE_PIECES_MAX_TOKENS`, payé à l'usage). Si la réponse est quand même
  coupée, l'appel est relu en deux moitiés (jusqu'à trois fois de suite, 12 fois au plus par dossier,
  `ANALYSE_RELANCES_MAX`) ; au-delà, les informations complètes de la réponse coupée sont gardées et la
  partie est dite « exploitée en partie ».
- **Panne** : une réponse illisible ou une panne de l'IA est relancée une fois (après 2 s). Une partie
  qui échoue encore est nommée « non exploitée par l'IA (IA indisponible) » dans son en-tête, dans
  l'introduction de la synthèse (« n'en conclus rien ») et dans la couverture ; l'analyse continue.
  Elle n'échoue (et n'est remboursée) que si plus de la moitié des parties échoue. Pas de découpage
  sur panne : des échecs en rafale ouvriraient le disjoncteur IA de l'espace pour tout le reste.
- **Étiquettes honnêtes** : « lue en entier par l'IA » seulement si toutes les parties de la pièce ont
  été exploitées ; sinon « lue en partie par l'IA (k parties exploitées sur n…) » ou « non exploitée
  par l'IA (raison) ». Une pièce dont le texte n'a été lu qu'en partie (pages abîmées, scan) le dit
  aussi (« texte de la pièce lu en partie (…) »), y compris le règlement et le cadre remis tels quels.
- **Reprise** : les informations relevées sont rangées avec la lecture dès la fin du premier temps ;
  une nouvelle analyse (après une panne de la synthèse, ou « Ré-analyser » après avoir changé ses
  critères) ne relit que les parties manquantes.
- **Places de l'IA** : toutes les lectures en deux temps du serveur se partagent 3 places
  (`ANALYSE_PLACES_IA`, moitié de `LLM_MAX_CONCURRENT`), attribuées dans l'ordre d'arrivée (une place
  rendue passe au premier qui attend). Deux gros dossiers ne prennent donc plus les 6 places du
  process : les questions, analyses et rédactions des autres clients gardent les leurs. Le sémaphore
  global (`llm._llm_slot`) n'est pas modifié.
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

- Recherche des passages pertinents dans **toutes** les pièces (BM25, sans IA ni réseau, index
  compact mis en cache mémoire par dossier) avec une normalisation commune au dossier et à la question
  : minuscules, accents retirés, pluriels et « e » muets (« penalites », « PÉNALITÉ », « pénalités »
  retrouvent la même phrase) ; 8 passages de ≈ 1 400 caractères.
- **Tous les règlements** (RC, RC modificatif, RC de chaque lot) sont **toujours** remis, le
  modificatif en premier (repères [R1], [R2]… ; « un règlement modificatif l'emporte »), en entier
  dans la limite de 60 000 caractères au total (en cache de prompt) ; seuls les règlements remis EN
  ENTIER sont écartés de la recherche (par pièce, et non plus par type) : un règlement qui n'a pas
  tenu reste cherché comme les autres pièces.
- La réponse cite la pièce et la page ; chaque phrase citée est vérifiée contre le texte
  (`citation_guard`) : une phrase non retrouvée n'est jamais montrée comme une citation, et l'écran le
  dit. Si l'information n'est pas dans les extraits remis, la réponse dit **ce qui a été consulté**
  (« Pas trouvé dans les extraits consultés (le règlement de la consultation ; les 8 passages du
  dossier les plus proches de la question). Reformulez la question avec les mots du dossier… ») et
  nomme les pièces non lues — jamais « cette information ne figure pas dans le dossier ».
- **Borne hors quota** par organisation et par jour (heure de Paris) : 15 (essai en cours —
  `TRIAL_QUESTIONS_PAR_JOUR`, cf. `docs/ESSAI_GARDE_FOU.md` —, essai expiré, historique), 50 (Pro),
  120 (Business) ; réglable (`PLAN_LIMITS[…]["questions_jour"]`,
  ou `QUESTIONS_PAR_JOUR` pour tous). Compteur **persistant** dans la table `jobs` existante
  (une ligne `question_dossier` par question, sans le texte de la question, purgée après 7 jours) ;
  une question dont l'IA n'a pas répondu ne compte pas. La limite par adresse IP reste.

### 2.5 Facturation du dépassement

- `STRIPE_PRICE_OVERAGE` et `STRIPE_METER_EVENT_OVERAGE` (défaut `adjugo_analyse_overage`) sont
  **déclarés** dans `Settings` : la variable d'environnement est lue.
- Chemin vérifié et testé (Stripe simulé) : analyse au-delà du forfait, paiement à l'usage activé et
  facturable → `overage_count` + 1 → `stripe.billing.MeterEvent.create` avec un identifiant unique ;
  remboursement → `MeterEventAdjustment` d'annulation de cette unité.
- **Hors de la boucle d'événements** : à l'import, le débit et le remboursement (qui appellent Stripe
  au-delà du forfait, jusqu'à 80 s de délai par défaut) passent par `run_in_threadpool` ; un appel lent
  ne fige plus le serveur (testé : l'appel simulé à Stripe vérifie qu'aucune boucle ne tourne dans son
  fil).
- **Annulable après un redémarrage** : l'identifiant de chaque unité envoyée est rangé en base (une
  ligne `jobs` de type `unite_depassement`, sans autre donnée, gardée 62 jours), écrite AVANT l'envoi.
  Une longue lecture interrompue par un déploiement est remboursée au démarrage et son unité annulée
  (dans les 24 h permises par Stripe).
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
  revient sur le marché. Le voile « lecture en cours » et les boutons bloqués ne concernent que le
  marché lu : un autre marché ouvert pendant la lecture reste utilisable, et c'est le marché lu (pas
  celui affiché) qui est rechargé à la fin.
- Les parties que l'IA n'a pas pu exploiter (plafond, panne, réponse coupée) sont **listées** avec
  leur raison sous le message de couverture (« voir la liste » renvoie enfin à une liste), et « Pièces
  lues » marque la pièce « non exploitée par l'IA (…) » au lieu de « lue en entier ».
- Champs d'import : `.docm` et `.xlsm` acceptés.
- Carte d'analyse de « Trouver des marchés » (contrôle des bugs, octobre 2026) : la pastille « Seul » dit
  le verdict seul (`decision_seul` des réponses de `/analyze`, `/analyze-upload` et `/reanalyze`) ;
  `decision` devient « go_groupement » quand un groupement est recommandé, et la pastille disait alors
  « Bon potentiel en groupement » à côté de « À plusieurs Y % ».
- En-tête d'un marché créé à la main puis analysé depuis un dossier importé : aucun avis derrière ce
  marché, le bloc `source` de l'analyse est vide ; aucun lien « BOAMP · réf … » n'est affiché (avant, un
  lien « · réf » sans source ni référence).

### 2.7 Lectures en tâche de fond (`app/services/lecture_taches.py`)

- **Exécuteur à part** (`LECTURE_TACHES` = 2 fils) : une lecture de plusieurs dizaines de minutes
  n'occupe plus le pool commun (4 fils) des mémoires et questionnaires de tous les clients.
- **Bornes** : une lecture en attente ou en cours par organisation, `LECTURE_FILE_MAX` = 6 pour tout
  le serveur ; au-delà, refus immédiat **avant tout débit** (429 : « Votre dossier est bien importé :
  relancez « Ré-analyser » … Rien n'a été débité. »).
- **Mémoire** : le fichier importé n'est plus gardé dans la file ; la tâche le relit depuis le dossier
  « DCE » du marché (`storage.py`) quand elle démarre (repli : le fichier reçu, si l'archivage a échoué).
- **Fin honnête** : un échec passe le marché en « erreur » (l'écran cesse d'en suivre la progression
  à chaque ouverture ; après un redémarrage, `GET /lecture` le fait au premier passage) et rembourse
  l'analyse ; « terminé » n'est dit qu'une fois le résultat du job enregistré. Une analyse faite
  ensuite pendant la requête (petit dossier, ou « Ré-analyser » après une tâche morte) repart d'un état
  vide (« termine », sans tâche ni erreur) : `GET /lecture` ne dit plus « La lecture ou l'analyse du
  dossier a échoué. Réessayez : votre analyse n'a pas été débitée. » d'une analyse réussie et débitée
  (contrôle des bugs, octobre 2026).
- **Ré-analyser complète une lecture inachevée** : si des pièces n'ont pas été lues pour une raison
  passagère (temps écoulé, pages en image pas encore lues, plafond de pages lues par OCR dans une
  tâche, ou lecture des images indisponible alors qu'elle l'est maintenant), la ré-analyse relit en
  tâche de fond en reprenant les pièces lues en entier ET, page par page, les pages déjà reconnues :
  un scan de 500 pages avance de 300 pages à chaque passage au lieu de recommencer.

---

## 3. Coût de l'IA (tarifs publics, 3,3 caractères par token en moyenne)

Sonnet 4.6 : 3 $ / 15 $ par million de tokens (entrée / sortie) ; Haiku 4.5 : 1 $ / 5 $ ; lecture
du cache 0,1 ×, **écriture 1,25 ×** (cache de 5 minutes). Les sorties « courantes » sont estimées
(≈ 3 500 tokens pour l'analyse, ≈ 1 500 par partie lue, ≈ 300 par réponse) ; les pires cas prennent
la sortie **maximale** permise. Les relevés de `cost_meter` remplaceront ces estimations.
1 $ ≈ 0,86 €.

**Une analyse (une seule débitée au quota)**

| Dossier | Mode | Calcul | Coût |
|---|---|---|---|
| ZIP courant, 50 000 caractères | d'un seul tenant | (10 400 + 50 000) / 3,3 = 18 300 tokens × 3 $ + 3 500 × 15 $ | ≈ 0,11 $ |
| 150 000 caractères | d'un seul tenant | 48 600 × 3 $ + 3 500 × 15 $ | ≈ 0,20 $ |
| ≈ 390 000 caractères (limite) | d'un seul tenant | 121 000 × 3 $ + 6 000 × 15 $ (sortie maximale) | ≈ 0,45 $ |
| 600 000 caractères, 12 pièces | deux temps | Haiku : 179 000 × 1 $ + 15 000 × 5 $ = 0,25 $ ; synthèse : 35 000 × 3 $ + 3 500 × 15 $ = 0,16 $ | ≈ 0,41 $ |
| 2 000 000 caractères | deux temps (≈ 17 appels) | Haiku : 0,74 $ ; synthèse : 0,21 $ | ≈ 0,95 $ |
| 6 000 000 caractères (plafond technique), sortie courante | deux temps (≈ 50 appels) | Haiku : 1 870 000 × 1 $ + 50 × 1 500 × 5 $ = 2,25 $ ; synthèse : 150 000 × 3 $ + 6 000 × 15 $ = 0,54 $ | ≈ 2,8 $ (2,4 €) |
| 6 000 000 caractères, chaque appel à 40 informations | deux temps | Haiku : 1,87 $ + 50 × 5 200 × 5 $ = 3,17 $ ; synthèse 0,54 $ | ≈ 3,7 $ (3,2 €) |
| 6 000 000 caractères, pire théorique (chaque sortie au plafond de 8 000 tokens, 12 appels relus en deux) | deux temps | Haiku : 1,87 $ + relectures 0,44 $ + 74 × 8 000 × 5 $ = 5,27 $ ; synthèse 0,54 $ | ≈ 5,8 $ (5,0 €) |
| Ré-analyse du même gros dossier (parties déjà relevées) | deux temps | synthèse seule | ≈ 0,54 $ |

Avant : au plus 0,15 $ (84 600 caractères), mais l'IA ne voyait qu'une partie du dossier. Une
analyse courante reste très en dessous du prix d'une analyse du forfait Pro (129,99 € / 30 = 4,33 €)
et du dépassement (5 € HT). **Au plafond technique** (≈ 2 000 pages de texte), le pire cas réaliste
(3,2 €) reste dessous ; le pire théorique (5,0 €) l'atteint — il suppose que l'IA ignore la consigne
de 40 informations sur chacun des 50 appels.

**Une question**

| Cas | Calcul | Coût |
|---|---|---|
| Règlement de 20 000 caractères + 8 passages, cache froid | 6 100 × 1,25 + 3 900 = 11 500 tokens × 1 $ + 300 × 5 $ | ≈ 0,013 $ |
| Même chose, question suivante dans les 5 minutes (règlement lu dans le cache) | 6 100 × 0,1 + 3 900 = 4 500 × 1 $ + 300 × 5 $ | ≈ 0,006 $ |
| Règlements de 60 000 caractères au total, cache froid, sortie maximale | 18 200 × 1,25 + 3 900 = 26 650 × 1 $ + 1 200 × 5 $ | ≈ 0,033 $ |

Haiku 4.5 ne met en cache qu'un bloc d'au moins 4 096 tokens (≈ 13 500 caractères) : en dessous, pas
de cache, donc pas de surcoût d'écriture. Avant : 0,0063 $ pour les 14 000 premiers caractères
seulement.

**Borne par jour, pire cas** (règlements de 60 000 caractères, cache froid, sortie maximale, tous les
jours du mois — la borne s'applique chaque jour du calendrier) : Pro 50 × 31 × 0,033 $ ≈ 51 $ (44 €)
par mois et par organisation ; Business 120 × 31 × 0,033 $ ≈ 123 $ (106 €) ; essai expiré 15 × 31 ×
0,033 $ ≈ 15 $ (13 €). Usage courant (cache, ≈ 10 questions par jour) ≈ 1,3 $ par mois. Avant, seule
l'adresse IP limitait : ≈ 84 € par mois et par adresse.

**Routage par tâche du 12/10/2026 (`app/services/llm.py`, docs/IA_ROUTAGE.md) : coûts recalculés.**
Les tableaux ci-dessus restent ceux de l'ancien routage (`LLM_ROUTAGE=ancien`).

Hypothèses du nouveau routage :
- lecture des pièces et synthèse : Mistral Large 4, point d'accès UE, **prix normal** (1,36 $ / 4,18 $
  par million, +10 % pour l'UE ; le prix de lancement à −50 % divise ces montants par deux) ;
- découpage de Mistral pour le français : non publié, pris égal à celui de Sonnet 4.6 (hypothèse) ;
- plafonds de sortie relevés de 30 % (payés à l'usage) : une partie lue a droit à 10 400 tokens ;
- questions : Claude Sonnet 5.5 (2 $ / 10 $ ; ≈ +30 % de tokens ; cache de 5 minutes écrit à 1,25 ×,
  relu à 0,05 ×), sans réflexion préalable (`between_tools`), effort `medium`.

| Cas | Nouveau routage | Ancien |
|---|---|---|
| Analyse, ZIP de 50 000 caractères | 0,043 $ (secours Sonnet 5.5 : 0,093 $) | 0,11 $ |
| Analyse, 150 000 caractères | 0,089 $ (secours : 0,17 $) | 0,20 $ |
| Analyse, ≈ 390 000 caractères, sortie maximale | 0,22 $ (secours : 0,39 $) | 0,45 $ |
| Analyse, 600 000 caractères, deux temps | 0,41 $ | 0,41 $ |
| Analyse, 6 M caractères, sortie courante | 3,39 $ (2,9 €) | 2,8 $ |
| Analyse, 6 M caractères, 40 informations par appel | 4,25 $ (3,6 €) | 3,7 $ |
| Analyse, 6 M caractères, pire théorique (plafond de 10 400 tokens) | 7,26 $ (6,2 €) | 5,8 $ |
| Question, règlement de 20 000 caractères, cache froid | 0,034 $ | 0,013 $ |
| Question suivante dans les 5 minutes | 0,015 $ | 0,006 $ |
| Question, 60 000 caractères, cache froid, sortie maximale | 0,085 $ | 0,033 $ |
| Borne par jour, pire cas, Pro (50 × 31) | 132 $ (113 €) par mois et par organisation | 51 $ |
| Borne par jour, pire cas, Business (120 × 31) | 316 $ (272 €) | 123 $ |
| Borne par jour, pire cas, essai expiré (15 × 31) | 39 $ (34 €) | 15 $ |

Ce qu'il faut retenir :
- Les analyses d'un seul tenant coûtent environ deux fois moins cher.
- Les très gros dossiers en deux temps coûtent un peu plus : l'entrée de Mistral au point d'accès UE
  (1,50 $) est plus chère que celle de Haiku 4.5 (1 $).
- **Les questions coûtent ≈ 2,6 fois plus** (Sonnet 5.5 au lieu de Haiku 4.5) : décision du fondateur,
  pour la fidélité des réponses.
- La borne par jour du pire cas d'un Business passe à 272 € par mois et par organisation. Clients payants :
  aucun plafond réduit (décision du fondateur). Garde-fou de coût : sur l'essai seulement.
- À suivre sur `cost_meter` et `GET /api/admin/ia/qualite`.
- Essai gratuit en cours : 15 questions par jour, et surtout le budget de l'essai (15 € par défaut),
  qui compte le coût réel de chaque appel calculé par ce routage (même table des prix,
  `app/services/tarifs_ia.py` ; secours et cache compris) : la borne d'un compte d'essai est ce budget,
  pas les lignes ci-dessus (docs/ESSAI_GARDE_FOU.md).

**Essai gratuit — décidé le 12/10/2026 (chantier E, `docs/ESSAI_GARDE_FOU.md`) : 30 analyses sur
toute la durée de l'essai, 15 questions par jour, budget IA de l'essai vérifié avant chaque opération
(une lecture commencée va toujours au bout). Constat d'origine :** Pendant l'essai (30 jours, sans carte), `quota._limit` donne 30
analyses (niveau Pro) et 50 questions par jour. Pire cas réaliste d'un compte d'essai qui n'importerait
que des dossiers au plafond technique : 30 × 3,7 $ + 50 × 30 × 0,033 $ ≈ 160 $ (≈ 140 €), contre
≈ 4,5 $ d'analyses avant (0,15 $ au plus chacune, mais sur une partie du dossier seulement). Un dossier courant (moins de 400 000 caractères) coûte
moins de 0,50 $. Rien n'est bridé ici (la consigne est de ne jamais analyser une moitié de dossier) ;
pistes si besoin : compter un dossier de plus de 2 millions de caractères comme plusieurs analyses
pendant l'essai, ou réduire le nombre d'analyses d'essai.

## 4. Points restants

- **Fusion avec la vague 2 (atelier de rédaction) : FAITE** (branche de mise en ligne commune).
  1. `mesurer_import(project, analysis)` est appelé dans `_finish_analysis`, après
     `project.ai_analysis = analysis` : l'analyse pendant la requête ET en tâche de fond sont mesurées
     (testé : `tests/test_redaction_v2_lecture_integrale.py`, analyse forcée en tâche de fond).
  2. Le moteur de l'atelier (`app/services/atelier.py`, `agents/memoire.py`) lit le dossier par
     l'accès commun : `dce_texte.pieces_remises(payload, ATELIER_DOSSIER_MAX_CARACTERES)` remet TOUS
     les règlements (modificatif en premier) et TOUS les cadres de réponse en entier, précédés de
     `dce_texte.note_remise(…, pour_acheteur=True)` (ce qui est remis en entier, par passages, non
     lu ; jamais « dossier lu en entier », jamais de remarque sur la lecture dans le texte rendu à
     l'acheteur — `dce_lecture.note_pour_ia` reste celle de l'analyse et des questions), dans un bloc
     commun mis en cache de prompt (la première partie de « Rédiger tout » part seule, les suivantes
     relisent le cache) ; puis,
     pour chaque partie, `dce_texte.passages(project, partie, k=ATELIER_PASSAGES, exclude_pieces=…)`
     dans toutes les autres pièces. La lecture rangée n'est prise que si elle est celle du fichier
     importé le plus récent (même empreinte) ; sinon (ancienne analyse, lecture en cours) l'ancienne
     lecture bornée reste, et l'écran le dit avec le moyen d'obtenir la lecture intégrale
     (« Ré-analyser »). « Pièces du dossier de l'acheteur lues par Adjugo » montre la couverture
     honnête (lue en entier, en partie, non lue et pourquoi, et ce qui est remis à l'IA). Le texte
     intégral n'est jamais recopié dans `dossiers_presentation.dce_lu`, ni celui des cadres de
     réponse : seul `cadre_decoupable` y est gardé, le plan relit le cadre depuis la lecture rangée.
     « Lecture en cours » n'est dit que si la tâche de lecture tourne vraiment (une lecture morte au
     redémarrage du serveur n'est plus dite « pas encore terminée »). Coût IA de l'atelier avec la
     lecture intégrale : `docs/REDACTION_V2_API.md` § 4.4.
     `routers/knowledge.py:131` (ancien `memoire-upload`) ne rédige plus (410, vague 2) : plus aucun
     plafond à y retirer ; les 24 000 caractères de `agents/memoire.py` (exigences du mémoire de
     groupement, routeur archivé) passent par `texte_pour_exigences` : lecture intégrale du marché
     quand elle est rangée (règlements et cadres en entier, passages sur critères, moyens, délais,
     pénalités), sinon le texte fourni composé règlement et cadre en tête (120 000 caractères).
  3. `app/services/jobs.py` : inchangé par la lecture intégrale (exécuteur à part pour les lectures).
  4. SRI, `node --check`, suite complète verte ; migrations et tests de l'atelier, de la lecture
     intégrale, de la rédaction V1 et de la co-traitance rejoués sur Postgres depuis l'état exact de
     la production.
- **Stripe** : créer le compteur et le prix à l'usage, puis renseigner `STRIPE_PRICE_OVERAGE`
  (§ 2.5).
- **Progression** d'une lecture en tâche de fond : gardée en mémoire du process (process unique) ;
  après un redémarrage, le job est passé en erreur, l'analyse remboursée et l'unité Stripe annulée.
- **Images insérées dans un Word** (une annexe scannée collée dans un `.docx`) : non lues par OCR ;
  la pièce est dite lue en entier si son texte l'est. À traiter si cela se rencontre (extraire les
  images de `word/media` et les passer à l'OCR en tâche de fond).
- **Sémaphore IA global** (`llm._llm_slot`) : non rendu équitable (fichier partagé, tests existants
  qui le remplacent) ; les lectures en deux temps sont bornées à part (§ 2.3), ce qui suffit à garder
  des places aux autres clients.
- **Audit d'accessibilité** (`scripts/a11y_audit.cjs`, Playwright) : non lancé en local (pas de
  navigateur installable sans réseau) ; les ajouts suivent les motifs existants (bulle (i) avec
  libellé lu par les lecteurs d'écran, progression annoncée par `aria-live`).
- **Modèles 5.5** : non migrés (chantier séparé). Le budget de contexte et les prix de `cost_meter`
  sont à revoir à cette occasion (découpage en tokens × 1,3).
