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

(Complété au fil du chantier : voir la suite de ce document.)
