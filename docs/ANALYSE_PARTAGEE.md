# Analyse partagée d'un dossier de consultation

Règle : économiser le coût de l'IA sans jamais baisser la performance. Seules les économies sans risque
de qualité par construction sont faites ici : on ne lit jamais moins, on ne change jamais de modèle, on
ne raccourcit aucune consigne de lecture. On évite seulement de relire à l'identique un dossier déjà lu.

Code : `app/services/analyse_partagee.py` (partage, mesure, purge), `app/services/analysis.py`
(extraction, partie propre à l'entreprise), `app/services/analyse_dossier.py` (dossier lu en entier),
`app/routers/sourcing.py` (routes), migration `alembic/versions/w7x8analysepartagee_analyse_partagee.py`,
tests `tests/test_analyse_partagee.py`.

## 1. En bref

Un même appel d'offres intéresse plusieurs PME. Avant, l'analyse envoyait à l'IA le dossier ET le
profil de l'entreprise : chaque import relisait tout le dossier, pour chaque entreprise. Le score et le
verdict étaient pourtant déjà recalculés sans IA (`dce_scoring.score_dce`).

Maintenant, l'analyse se fait en deux temps :

1. **Extraction du dossier** (le gros du coût) : l'IA reçoit le dossier seul, jamais le profil ni les
   critères. Elle relève les faits : critères et poids, pièces exigées, contraintes, lots, dates,
   exigences, clauses, points d'attention du dossier, analyse du marché en 3 paragraphes.
2. **Partie propre à l'entreprise** : le score et le verdict (calculés sans IA, comme avant), puis un
   appel court qui reçoit l'extraction, la compatibilité calculée et le profil (jamais le dossier entier).

L'extraction ne dépend que du dossier : elle est gardée et resservie, sans nouvel appel, quand le même
dossier, exactement, est importé à nouveau, par la même entreprise ou par une autre.

## 2. Ce que l'IA personnalisait, et où c'est fait maintenant

Recensement fait sur la consigne d'origine (`SYSTEM_PROMPT`) et sur le prompt d'origine
(`build_user_prompt` avec profil et critères, phrase « Utilise ces critères pour ajuster le match_score… »).

| Champ (écran) | Avant | Maintenant |
|---|---|---|
| `match_score`, `go_decision` | demandés à l'IA, puis **remplacés** sans IA | plus demandés à l'IA ; toujours calculés sans IA (`score_dce`), à l'identique |
| `score_breakdown`, `groupement` | sans IA | sans IA, à l'identique |
| `details.recommandation`, 4e paragraphe « stratégie et recommandation finale » | IA, avec le profil | appel court : `strategie`, ajoutée comme dernier paragraphe ; elle connaît la compatibilité affichée et ne la contredit jamais |
| `details.recommandation`, paragraphes 1 à 3 (marché, attentes de l'acheteur, points à maîtriser) | IA | extraction (3 paragraphes, 140 à 280 mots) |
| `details.points_attention` propres à l'entreprise (CA exigé supérieur au sien, qualification absente, seuil dépassé, lieu hors zone) | IA, mêlés aux autres | appel court : `points_attention_entreprise` (4 au plus), ajoutés à ceux du dossier, sans doublon |
| `details.clauses_risque[].niveau` au regard des seuils de l'entreprise (pénalités, garantie, retenue, avance, délai de remise) | IA (« élevé dès qu'un seuil est dépassé ») | extraction : niveau au regard des usages et valeurs exactes du dossier ; appel court : `clauses` (passage au niveau « élevé », jamais abaissé, avec la raison et le seuil) et `clauses_ajoutees` (3 au plus) |
| tous les autres champs (`summary`, `intitule_marche`, `acheteur`, `contact`, critères et extraits, garanties, pénalités, avance, lots, dates, exigences et citations, forme du groupement, pièces exigées, assurances, visite…) | IA, ne dépendaient que du dossier | extraction, même consigne mot pour mot |
| carte « Comment vous serez noté » (`grille_notation`) | sans IA, d'après les critères extraits et le texte | sans IA, à l'identique, d'après le texte de CE dossier et les pièces de CE marché |

Garde-fous de la partie propre à l'entreprise : sans seuil fourni par l'entreprise, aucune clause n'est
dite « au-delà de votre seuil » (comme avant) ; une réponse illisible est relancée une fois, puis
l'analyse objective reste entière (rien n'est inventé) ; une panne est propagée (le quota est remboursé,
comme avant) ; les noms des salariés sont masqués (`pii_scope`) ; l'appel est fait dans l'espace facturé
du client (`tenant_scope`). Elle reçoit aussi l'activité que le score compare déjà (spécialités,
départements, qualifications) : plus d'éléments qu'avant, jamais moins.

`ANALYSE_PARTAGEE=0` remet l'analyse d'origine en un seul appel, à l'identique (consigne d'origine,
profil et critères dans le prompt). La mesure des doublons continue.

## 3. Le partage de l'extraction

- **Clé** : empreinte SHA-256 de tout ce dont l'extraction dépend : version et texte des consignes
  (extraction et lecture des pièces), plafonds de sortie, route effective de l'IA (modèle principal et
  secours, réglages, fournisseurs disponibles, mode de routage, forçage), version de la lecture intégrale
  (`dce_lecture.VERSION`) et de la lecture des pièces (`analyse_dossier.VERSION_LECTURE`), réglages de la
  lecture en deux temps, langue, mode de lecture, budget de contexte, note de lecture, texte assemblé du
  dossier, et pour chaque pièce : nom, type, libellé, état, raison, détail, pages, texte. Même entrée
  exacte, même extraction : la resservir équivaut à la refaire.
- **Servie instantanément** : au second import, aucun appel n'est fait pour l'extraction ; seule la
  partie propre à l'entreprise est appelée.
- **Ré-analyser** (`/api/sourcing/reanalyze`) refait toujours l'extraction et remplace l'entrée.
- **Invalidation automatique** : un rectificatif (contenu différent), un autre nom de fichier, un autre
  modèle, d'autres consignes, une autre version de la lecture donnent une autre clé.
- **Jamais gardée** : une réponse illisible ; une extraction pendant laquelle le secours a répondu à la
  place du modèle prévu (bascule pour panne, réponse coupée, JSON illisible, refus ; « fournisseur non
  configuré » est déjà dans la clé) ; une lecture en deux temps avec une partie en panne, illisible ou
  coupée. Un incident passager n'est jamais resservi.
- **Lecture en deux temps** : resservie, aucune pièce n'est relue ; les compteurs de la couverture
  (appels, parties reprises) sont recalculés pour CE marché. Si des parties de ce marché avaient déjà été
  lues (analyse précédente interrompue), la lecture reprend comme avant au lieu de resservir.

## 4. Confidentialité

- L'entrée partagée (`analyses_partagees`) ne contient que la réponse de l'IA sur le dossier (document
  public de l'acheteur) et le compte rendu de lecture. **Aucune colonne d'organisation**, aucun profil,
  aucun critère, aucun choix de client. Testé : prompt de l'extraction et ligne en base sans aucune valeur
  du profil (nom, SIRET, ville, CA, email, téléphone, noms des salariés, qualifications, seuils).
- **Aucun indice dans l'API ni à l'écran** : mêmes champs, même déroulé (tâche de fond ou non selon le
  dossier seul), estimation de l'essai calculée comme pour une extraction neuve, compteurs de lecture de
  CE marché. Testé : aucune clé ni aucun mot « partage », « cache », « servi », « mutualisé » dans les
  réponses et l'analyse rangée.
- **Délai** : la première fois qu'une entreprise reçoit une extraction faite pour une autre, la réponse
  attend la durée qu'avait prise l'extraction (progression rejouée, au plus
  `ANALYSE_PARTAGEE_MASQUE_MAX_S`, 600 s), pour que la rapidité ne révèle pas qu'un autre a déjà analysé
  ce dossier. Pour la même entreprise (ré-import), la réponse est immédiate. `ANALYSE_PARTAGEE_MASQUE=0` :
  toujours immédiate (plus rapide, mais un temps de réponse très court devient un indice).
- **Les choix de chaque client restent à lui** : critères confirmés ou écartés, poids saisis, questions,
  sont rangés dans son marché (`ai_analysis`), après l'extraction ; jamais dans l'entrée partagée. Testé.
- **La mesure n'est jamais montrée à un client** : `/metrics` (jeton) et `GET /api/admin/analyse-partagee`
  (administrateur de la plateforme) ne donnent que des agrégats, sans organisation, sans empreinte.

## 5. Coût et quota

- **Quota** : débité comme d'habitude, une analyse par import, même servie depuis le partage.
- **Extraction** : comptée à la plateforme (`budget_ia.mutualise`) pour un forfait payant ; l'extraction
  NEUVE déclenchée par un compte en essai gratuit est comptée à son essai (sinon le garde-fou de l'essai ne
  verrait plus l'essentiel du coût) ; servie depuis le partage, elle ne coûte rien à personne.
- **Partie propre à l'entreprise** : comptée au client (et à son essai).
- **Estimation avant l'import (essai)** : extraction toujours comptée comme neuve, plus l'appel court ;
  prudente, et identique que l'extraction soit resservie ou non.

## 6. Mesure

Une ligne `analyse_empreintes` par analyse réussie (dossier ou avis) : organisation, empreinte normalisée
du contenu (empreinte de chaque pièce, NFKC, casse et blancs réduits, triées : ni le nom ni l'ordre des
fichiers, jamais le contenu), clé exacte, servie ou non, coût évité. Agrégats :

- `doublons_entre_organisations` : analyses d'un contenu déjà analysé par une autre organisation (borne
  haute de ce que le partage peut éviter) ; `..._cle_exacte` : la même chose à l'identique de ce que l'IA
  reçoit (ce que le partage peut réellement resservir ; l'écart vient des noms de fichiers, de la langue,
  du mode de lecture) ;
- `servies_depuis_le_partage`, `taux_servies`, `economie_eur` (tarif public du modèle) ;
- `/metrics` : `adjugo_analyse_partagee_analyses`, `_contenus_distincts`,
  `_doublons_entre_organisations{mesure="contenu"|"exacte"}`, `_servies`, `_economie_eur`, `_entrees`.

## 7. Gains attendus selon le taux de doublons mesuré

Calcul fait avec la table des prix du projet (`app/services/tarifs_ia.py`, prix normal, point d'accès UE
pour Mistral), sortie réaliste (3 500 tokens pour l'extraction, 700 pour l'appel court, dont la taille
réelle mesurée est d'environ 13 900 caractères pour une extraction complète). Coût d'une analyse en euros.

Mistral Large 4 (route de l'analyse) :

| Dossier (caractères lus) | Avant | Extraction neuve + appel court | Extraction resservie | Taux de doublons au-delà duquel on gagne |
|---|---|---|---|---|
| 60 000 (d'un seul tenant) | 0,059 | 0,068 (+15 %) | 0,011 (-81 %) | 15 % |
| 150 000 (d'un seul tenant) | 0,109 | 0,117 (+8 %) | 0,011 (-90 %) | 8 % |
| 390 000 (d'un seul tenant, maximum) | 0,241 | 0,249 (+4 %) | 0,011 (-95 %) | 4 % |
| 1 500 000 (en deux temps) | 1,411 | 1,420 (+0,6 %) | 0,011 (-99 %) | 0,6 % |

Claude Sonnet 5.5 (secours) : mêmes ordres de grandeur (+13 %, +8 %, +4 %, +0,6 % ; resservie -81 % à
-99 %).

Coût moyen par analyse, avec `d` le taux de doublons exacts entre organisations :
`(1 - d) × (extraction + appel court) + d × appel court`. On gagne dès que
`d > (extraction + appel court - avant) / extraction` (dernière colonne). Exemple : 20 % de doublons sur
des dossiers de 150 000 caractères, -10 % sur la facture d'analyse ; sur les gros dossiers (les plus
chers), le partage est rentable dès le premier doublon.

Ce que cela veut dire : sans aucun doublon, chaque analyse neuve coûte un peu plus (l'appel court, environ
un centime). La décision se prend sur la mesure : après quelques semaines, lire
`doublons_entre_organisations_cle_exacte` et `taux_servies` sur `/api/admin/analyse-partagee`. Si le taux
reste sous le seuil de la dernière colonne pour la taille des dossiers importés, `ANALYSE_PARTAGEE=0`
remet l'analyse d'origine (un seul appel) et la mesure continue.

Délai : une analyse neuve fait un appel court de plus (quelques secondes) ; l'extraction est un peu plus
courte (plus de 4e paragraphe ni de score). Ré-import par la même entreprise : seulement l'appel court.

## 8. Qualité : preuves que rien n'est perdu

- Consigne : `SYSTEM_EXTRACTION` est `SYSTEM_PROMPT` dont seuls 7 passages (listés dans
  `analysis._EXTRACTION_REMPLACEMENTS`, chacun vérifié au chargement du module) sont retirés ou ramenés
  au dossier. Testé : mêmes champs à extraire, au détail près (seuls `match_score` et `go_decision`, que
  le calcul sans IA remplaçait déjà, ne sont plus demandés) ; toutes les autres lignes, mot pour mot.
- Dossier remis : identique (même lecture intégrale, même sélection, même note de lecture). Le mode de
  lecture ne dépend plus du profil : la place que prenait le profil revient au dossier.
- Même modèle, mêmes réglages, même plafond de sortie (tâche « analyse »).
- Avant / après sur des cas synthétiques et par la vraie route d'import : mêmes clés dans la réponse et
  dans l'analyse rangée, même carte « Comment vous serez noté », même couverture, même score, même
  verdict, même détail du score, même groupement, mêmes citations vérifiées ; recommandation en 4
  paragraphes ; points d'attention et clauses gardent ce qui était propre à l'entreprise. Toute la suite
  de tests existante passe.
- Limite honnête : la stratégie, les points et les niveaux propres à l'entreprise sont rédigés par l'IA
  à partir de l'extraction (et non plus du dossier entier). L'extraction contient les valeurs exactes du
  dossier (pénalités, garanties, avance, CA exigé, qualifications, date limite) et la consigne exige les
  valeurs exactes dans chaque clause ; une clause qui dépasse un seuil et manquerait à la liste peut être
  ajoutée. En contrepartie, la stratégie connaît désormais la compatibilité calculée affichée à l'écran
  (avant, l'IA rédigeait sa recommandation sans la connaître et pouvait la contredire).

## 9. Cache de prompt

Vérifié partout où un long texte est relu (rien n'a changé dans ce qui est lu) :

- extraction (consigne de 8 500 caractères) et partie propre à l'entreprise (3 200) : consigne marquée ;
- lecture des pièces en deux temps : la consigne (1 700 caractères, environ 570 tokens) était envoyée en
  texte simple à chaque partie (jusqu'à 80 par dossier) ; elle est maintenant marquée (même texte) ;
- questions sur le dossier : règlement(s) en entier dans un bloc marqué (inchangé) ;
- rédaction du mémoire : dossier de l'acheteur commun dans un bloc marqué pour une heure (inchangé) ;
- autres consignes (veille, questionnaire, rédaction d'une partie) : sous la longueur minimale mise en
  cache (512 tokens sur Sonnet 5.5), le marquage n'y changerait rien. Mistral ignore le marquage (le
  cache y est automatique).

## 10. Données et RGPD

- L'extraction partagée n'est pas une donnée personnelle d'un client : c'est la lecture du document
  public de l'acheteur, sans aucune donnée d'entreprise. Elle peut contenir le contact de l'acheteur tel
  qu'il est publié dans le dossier (déjà présent dans l'analyse de chaque marché). Effacée quand elle n'a
  plus servi depuis `ANALYSE_PARTAGEE_JOURS` jours (120) : purge quotidienne
  `POST /api/admin/run-trash-purge`.
- Les lignes de mesure (organisation, empreinte, jamais le contenu) sont effacées avec le compte
  (effacement RGPD) et au-delà de `ANALYSE_PARTAGEE_MESURE_JOURS` jours (365). Elles ne figurent pas dans
  l'export RGPD : agrégat interne, sans contenu ; le dossier analysé figure déjà dans l'export (le marché).
- Le texte intégral de chaque marché reste rangé avec le marché et supprimé avec lui (`dce_texte`).

## 11. Réglages

| Variable | Défaut | Effet |
|---|---|---|
| `ANALYSE_PARTAGEE` | `1` | `0` : analyse d'origine en un seul appel, aucun partage (mesure gardée) |
| `ANALYSE_PARTAGEE_MASQUE` | `1` | `0` : extraction resservie à une autre entreprise sans attente |
| `ANALYSE_PARTAGEE_MASQUE_MAX_S` | `600` | attente maximale |
| `ANALYSE_PARTAGEE_JOURS` | `120` | durée de vie d'une extraction qui ne sert plus |
| `ANALYSE_PARTAGEE_MESURE_JOURS` | `365` | durée de vie des lignes de mesure |

Changer la consigne de l'extraction : augmenter `analysis.VERSION_CONSIGNES` (le texte entre aussi dans
la clé). Changer la lecture intégrale : augmenter `dce_lecture.VERSION`.

## 12. Stockage

Révision `w7x8analysepartagee` (après `v6w7preuves`), idempotente : tables `analyses_partagees` (clé
unique, aucune colonne d'organisation) et `analyse_empreintes` (sans clé étrangère, comme `usage_ia`).
Testée sur SQLite (chaîne complète, retour arrière, schéma identique aux modèles) et sur un vrai Postgres
depuis l'état exact de la production (`d6b4d29`, tête `u5v6essaigardefou`) : deux révisions appliquées,
aucune donnée perdue, seconde montée sans effet, rejeu forcé idempotent, valeurs par défaut et unicité
côté base, schéma identique à une base neuve, retour arrière d'une révision puis jusqu'à la production,
remontée ; tests rejoués sur cette base.
