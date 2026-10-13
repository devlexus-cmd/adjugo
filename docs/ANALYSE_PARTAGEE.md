# Analyse partagée d'un dossier de consultation

Règle : économiser le coût de l'IA sans jamais baisser la performance. Seules les économies sans risque
de qualité par construction sont faites ici : on ne lit jamais moins, on ne change jamais de modèle, on
ne raccourcit aucune consigne de lecture. On évite seulement de relire à l'identique un dossier déjà lu.

Code : `app/services/analyse_partagee.py` (partage, mesure, purge), `app/services/analysis.py`
(extraction, partie propre à l'entreprise), `app/services/analyse_dossier.py` (dossier lu en entier),
`app/routers/sourcing.py` (routes), migration `alembic/versions/w7x8analysepartagee_analyse_partagee.py`,
tests `tests/test_analyse_partagee.py`.

## 1. En bref

Un même appel d'offres intéresse plusieurs PME. L'analyse d'origine envoie à l'IA le dossier ET le
profil de l'entreprise : chaque import relit tout le dossier, pour chaque entreprise. Le score et le
verdict sont pourtant déjà recalculés sans IA (`dce_scoring.score_dce`).

**Par défaut : mesure seule.** L'analyse reste celle d'origine (un seul appel, profil compris), à
l'identique, et on mesure combien d'imports portent sur un dossier déjà analysé par une autre entreprise,
y compris la clé exacte sous laquelle le partage rangerait l'extraction. Sans doublon, le partage coûte
un peu plus (voir § 7) : il ne s'active que sur décision, quand la mesure montre qu'il fera baisser la
facture (`ANALYSE_PARTAGEE=1`).

Partage activé, l'analyse se fait en deux temps :

1. **Extraction du dossier** (le gros du coût) : l'IA reçoit le dossier seul, jamais le profil ni les
   critères. Elle relève les faits : critères et poids, pièces exigées, contraintes, lots, dates,
   exigences, clauses, points d'attention du dossier, analyse du marché en 3 paragraphes.
2. **Partie propre à l'entreprise** : le score et le verdict (calculés sans IA, comme avant), les
   mots-clés exclus cherchés sans IA dans tout le dossier, puis un appel court qui reçoit l'extraction,
   la compatibilité calculée et le profil (jamais le dossier entier).

L'extraction ne dépend que du dossier : elle est gardée et resservie, sans nouvel appel, quand le même
dossier, exactement, est importé à nouveau, par la même entreprise ou par une autre.

## 2. Ce que l'IA personnalisait, et où c'est fait en deux temps

Recensement fait sur la consigne d'origine (`SYSTEM_PROMPT`) et sur le prompt d'origine
(`build_user_prompt` avec profil et critères, phrase « Utilise ces critères pour ajuster le match_score… »).

| Champ (écran) | Avant | En deux temps |
|---|---|---|
| `match_score`, `go_decision` | demandés à l'IA, puis **remplacés** sans IA | plus demandés à l'IA ; toujours calculés sans IA (`score_dce`), à l'identique |
| `score_breakdown`, `groupement` | sans IA | sans IA, à l'identique |
| `details.recommandation`, 4e paragraphe « stratégie et recommandation finale » | IA, avec le profil | appel court : `strategie`, ajoutée comme dernier paragraphe ; elle connaît la compatibilité affichée et ne la contredit jamais |
| `details.recommandation`, paragraphes 1 à 3 (marché, attentes de l'acheteur, points à maîtriser) | IA | extraction (3 paragraphes, 140 à 280 mots) |
| `details.points_attention` propres à l'entreprise (CA exigé supérieur au sien, qualification absente, seuil dépassé, lieu hors zone) | IA, mêlés aux autres | appel court : `points_attention_entreprise` (4 au plus), ajoutés à ceux du dossier, sans doublon |
| Mots-clés que l'entreprise exclut (« Mots-clés à exclure »), confrontés au dossier | IA : les exclusions et le dossier entier dans le même appel | **sans IA, dans le texte entier du dossier** : chaque mot retrouvé donne un point d'attention avec la phrase exacte et la pièce (« Le dossier mentionne « désamiantage », un mot-clé que vous excluez — CCTP.pdf : « … » »), et il est remis à l'appel court, qui doit en tenir compte dans la stratégie ; une forme très différente (« amiante » pour « désamiantage ») est cherchée par l'appel court dans l'analyse du marché |
| `details.clauses_risque[].niveau` au regard des seuils de l'entreprise (pénalités, garantie, retenue, avance, délai de remise) | IA (« élevé dès qu'un seuil est dépassé ») | extraction : niveau au regard des usages et valeurs exactes du dossier ; appel court : `clauses` (passage au niveau « élevé », jamais abaissé, avec la raison et le seuil) et `clauses_ajoutees` (3 au plus) |
| tous les autres champs (`summary`, `intitule_marche`, `acheteur`, `contact`, critères et extraits, garanties, pénalités, avance, lots, dates, exigences et citations, forme du groupement, pièces exigées, assurances, visite…) | IA, ne dépendaient que du dossier | extraction, même consigne mot pour mot |
| carte « Comment vous serez noté » (`grille_notation`) | sans IA, d'après les critères extraits et le texte | sans IA, à l'identique, d'après le texte de CE dossier et les pièces de CE marché |

Recherche des mots-clés exclus (sans IA) : casse, accents, espaces, tirets et apostrophes indifférents ;
un mot de 6 lettres ou plus est trouvé aussi à l'intérieur d'un mot plus long (« amiante » dans
« désamiantage ») ; plus court, en mot entier, pluriel compris (« bois » jamais dans « boissons ») ; la
phrase citée est vérifiée contre le dossier (`citation_guard`). Dix mots-clés au plus, dans l'ordre saisi.

Garde-fous de la partie propre à l'entreprise : sans seuil fourni par l'entreprise, aucune clause n'est
dite « au-delà de votre seuil » (comme avant) ; une réponse illisible est relancée une fois, puis traitée
comme une panne (quota remboursé, message « Les conseils propres à votre entreprise n'ont pas pu être
rédigés par l'IA. Votre analyse n'a pas été débitée : relancez-la. » ; la relance ne refait pas
l'extraction, déjà rangée) : jamais une analyse en apparence complète mais privée de ses alertes ; une
panne est propagée (le quota est remboursé, comme avant) ; les noms des salariés sont masqués
(`pii_scope`) ; l'appel est fait dans l'espace facturé du client (`tenant_scope`). Elle reçoit aussi
l'activité que le score compare déjà (spécialités, départements, qualifications) : plus d'éléments
qu'avant, jamais moins.

## 3. Le partage de l'extraction (`ANALYSE_PARTAGEE=1`)

- **Clé** : empreinte SHA-256 de tout ce dont l'extraction dépend : version et texte des consignes
  (extraction et lecture des pièces), **tous les textes fixes du prompt** (autour du dossier, consigne de
  langue, prompt de lecture d'une partie, en-têtes, lignes et introduction de la synthèse en deux temps :
  `analyse_dossier.gabarits_lecture`, rendus sur des pièces fictives), plafonds de sortie, route
  effective de l'IA (modèle principal et secours, réglages, fournisseurs disponibles, mode de routage,
  forçage), version de la lecture intégrale (`dce_lecture.VERSION`) et de la lecture des pièces
  (`analyse_dossier.VERSION_LECTURE`), réglages de la lecture en deux temps, langue, mode de lecture,
  budget de contexte, note de lecture, texte assemblé du dossier, et pour chaque pièce : nom, type,
  libellé, état, raison, détail, pages, texte. Même entrée exacte, même extraction : la resservir
  équivaut à la refaire. Un texte modifié change la clé tout seul ; un changement de LOGIQUE de la lecture
  (découpage, vérification des citations) oblige à augmenter `VERSION_LECTURE` ou `dce_lecture.VERSION`.
- **Aucun appel d'extraction** au second import : seule la partie propre à l'entreprise est appelée. Le
  temps de réponse, lui, est masqué la première fois qu'une autre entreprise reçoit l'extraction (§ 4).
- **Ré-analyser** (`/api/sourcing/reanalyze`) refait toujours l'extraction et remplace l'entrée (sa date
  repart).
- **Invalidation automatique** : un rectificatif (contenu différent), un autre nom de fichier, un autre
  modèle, d'autres consignes ou textes du prompt, une autre version de la lecture donnent une autre clé.
- **Jamais gardée** : une réponse illisible ; une extraction pendant laquelle le secours a répondu à la
  place du modèle prévu (bascule pour panne, réponse coupée, JSON illisible, refus ; « fournisseur non
  configuré » est déjà dans la clé) ; une lecture en deux temps avec une partie en panne, illisible ou
  coupée ; une extraction faite sur des parties **reprises** d'une lecture précédente du marché (elles
  n'ont pas été lues sous les yeux de cette analyse : modèle et consigne non garantis), comptée alors au
  client comme sans partage. Un incident passager n'est jamais resservi.
- **Lecture en deux temps** : resservie, aucune pièce n'est relue ; les informations relevées partie par
  partie (faits du dossier et leurs phrases exactes, clé = contenu exact de la partie) sont gardées avec
  l'extraction et rangées avec le marché qui la reçoit, exactement comme après sa propre lecture : un
  « Ré-analyser » ensuite ne relit rien de plus que sans partage (même couverture, mêmes compteurs, même
  progression). Les compteurs de la couverture (appels, parties reprises) sont recalculés pour CE marché.
  Si des parties de ce marché avaient déjà été lues (analyse précédente interrompue), la lecture reprend
  comme avant au lieu de resservir.
- **Deux imports simultanés** du même dossier (deux entreprises, ou deux marchés) : le second attend que
  l'extraction du premier soit rangée, puis la reçoit — une seule extraction payée (un seul process :
  verrou par clé ; au plus `ANALYSE_PARTAGEE_ATTENTE_MAX_S`, 1 800 s, puis extraction propre).

## 4. Confidentialité

- L'entrée partagée (`analyses_partagees`) ne contient que ce que l'IA a lu et relevé dans le dossier
  (réponse de l'extraction, compte rendu de lecture, informations relevées partie par partie, durées de
  lecture). **Aucune colonne d'organisation**, aucun profil, aucun critère, aucun mot-clé exclu, aucun
  choix de client. Testé : prompt de l'extraction et contenu de la ligne en base sans aucune valeur du
  profil (nom, SIRET, ville, CA, email, téléphone, noms des salariés, qualifications, seuils).
- **Aucun indice dans l'API ni à l'écran** : mêmes champs, même déroulé (tâche de fond ou non selon le
  dossier seul), estimation de l'essai calculée comme pour une extraction neuve, compteurs de lecture de
  CE marché, mêmes informations rangées avec le marché (un « Ré-analyser » ensuite est identique). Testé :
  aucune clé ni aucun mot « partage », « cache », « servi », « mutualisé » dans les réponses et l'analyse
  rangée.
- **Délai** : la première fois qu'une entreprise reçoit une extraction faite pour une autre, la réponse
  attend la durée qu'avait prise l'extraction (au plus `ANALYSE_PARTAGEE_MASQUE_MAX_S`, 600 s, tout étant
  alors ramené dans la même proportion), avec une progression rejouée comme une vraie lecture : en deux
  temps, chaque partie annoncée lue à l'instant où elle l'avait été (par paquets, comme les lectures en
  parallèle), puis l'étape « synthèse » pendant la durée de la synthèse ; l'attente d'un import
  simultané en est retirée. Pour la même entreprise (ré-import), la réponse est immédiate.
  `ANALYSE_PARTAGEE_MASQUE=0` : toujours immédiate (plus rapide, mais un temps de réponse très court
  devient un indice). **Décision à prendre (Eliot)** : la consigne demandait une extraction « servie
  instantanément » ET « jamais révéler qu'une autre entreprise a analysé le même dossier » ; les deux
  s'opposent sur le temps de réponse. Le masquage est actif par défaut (la confidentialité l'emporte).
- **Les choix de chaque client restent à lui** : critères confirmés ou écartés, poids saisis, questions,
  sont rangés dans son marché (`ai_analysis`), après l'extraction ; jamais dans l'entrée partagée. Testé.
- **La mesure n'est jamais montrée à un client** : `/metrics` (jeton) et `GET /api/admin/analyse-partagee`
  (administrateur de la plateforme) ne donnent que des agrégats, sans organisation, sans empreinte.

## 5. Coût et quota

- **Quota** : débité comme d'habitude, une analyse par import, même servie depuis le partage.
- **Extraction** : comptée à la plateforme (`budget_ia.mutualise`) pour un forfait payant ; l'extraction
  NEUVE déclenchée par un compte en essai gratuit est comptée à son essai (sinon le garde-fou de l'essai ne
  verrait plus l'essentiel du coût) ; servie depuis le partage, elle ne coûte rien à personne. Une
  extraction faite sur des parties reprises (jamais gardée) est comptée au client.
- **Partie propre à l'entreprise** : comptée au client (et à son essai).
- **Estimation avant l'import (essai)** : extraction toujours comptée comme neuve, plus l'appel court ;
  prudente, et identique que l'extraction soit resservie ou non.

## 6. Mesure

Une ligne `analyse_empreintes` par analyse réussie (dossier ou avis), **en mesure seule comme en
partage** : organisation, empreinte normalisée du contenu (empreinte de chaque pièce, NFKC, casse et
blancs réduits, triées : ni le nom ni l'ordre des fichiers, jamais le contenu), clé exacte (en mesure
seule : celle sous laquelle le partage rangerait l'extraction — même plan de lecture, sans profil ; testé :
c'est bien la clé de l'extraction une fois le partage activé), servie ou non, coût évité. Agrégats :

- `doublons_entre_organisations` : analyses d'un contenu déjà analysé par une autre organisation (borne
  haute de ce que le partage peut éviter) ; `..._cle_exacte` et `taux_doublons_entre_organisations_cle_exacte` :
  la même chose à l'identique de ce que l'IA reçoit (ce que le partage peut réellement resservir ; l'écart
  vient des noms de fichiers, de la langue, du mode de lecture) ;
- `servies_depuis_le_partage`, `taux_servies`, `economie_eur` (tarif public du modèle) ;
- `/metrics` : `adjugo_analyse_partagee_analyses`, `_contenus_distincts`,
  `_doublons_entre_organisations{mesure="contenu"|"exacte"}`, `_servies`, `_economie_eur`, `_entrees`.

## 7. Gains attendus selon le taux de doublons mesuré

Calcul fait avec la table des prix du projet (`tarifs_ia.estimer_eur`, prix normal, point d'accès UE pour
Mistral), sortie réaliste (3 500 tokens pour l'analyse d'origine, 3 300 pour l'extraction, sans 4e
paragraphe ni score ; appel court : 700 tokens de sortie pour environ 20 000 caractères d'entrée, dont
13 900 pour une extraction complète). En deux temps (1 500 000 caractères) : 13 parties lues de 120 000
caractères (identiques avant et après), puis une synthèse de 390 000 caractères. Coût d'une analyse en
euros.

Mistral Large 4 (route de l'analyse) :

| Dossier (caractères lus) | Avant | Extraction neuve + appel court | Extraction resservie | Taux de doublons exacts au-delà duquel on gagne |
|---|---|---|---|---|
| 60 000 (d'un seul tenant) | 0,026 | 0,032 (+25 %) | 0,007 (-73 %) | 26 % |
| 150 000 (d'un seul tenant) | 0,051 | 0,057 (+13 %) | 0,007 (-86 %) | 13 % |
| 390 000 (d'un seul tenant, maximum) | 0,117 | 0,123 (+5,5 %) | 0,007 (-94 %) | 6 % |
| 1 500 000 (en deux temps) | 0,630 | 0,637 (+1 %) | 0,007 (-99 %) | 1 % |

Claude Sonnet 5.5 (secours) : mêmes proportions (+23 %, +13 %, +6 %, +1 % ; resservie -74 % à -99 %).
L'estimation prudente du garde-fou de l'essai (`budget_ia.estimer_appel` : sortie au plafond, modèle le
plus cher) donne des surcoûts du même ordre (+21 %, +11 %, +5 % pour 60 000, 150 000, 390 000 caractères).

Coût moyen par analyse, avec `d` le taux de doublons exacts entre organisations :
`(1 - d) × (extraction + appel court) + d × appel court`. On gagne dès que
`d > (extraction + appel court - avant) / extraction` (dernière colonne). Exemple : 30 % de doublons sur
des dossiers de 150 000 caractères, -17 % sur la facture d'analyse (20 % : -7 % ; 10 % : +3 %) ; sur les gros dossiers (les plus
chers), le partage est rentable dès le premier doublon.

**Décision** : sans aucun doublon, chaque analyse neuve coûte plus (l'appel court, environ 0,7 centime),
d'où la mesure seule par défaut. Après quelques semaines, lire `taux_doublons_entre_organisations_cle_exacte`
sur `/api/admin/analyse-partagee` (et la taille des dossiers importés) : au-delà du seuil de la dernière
colonne, `ANALYSE_PARTAGEE=1` active le partage ; la mesure continue, et `ANALYSE_PARTAGEE=0` revient à
la mesure seule à tout moment.

Délai : une analyse neuve en deux temps fait un appel court de plus (quelques secondes) ; l'extraction est
un peu plus courte (plus de 4e paragraphe ni de score). Ré-import par la même entreprise : seulement
l'appel court.

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
  paragraphes ; points d'attention et clauses gardent ce qui était propre à l'entreprise. Mot-clé exclu
  écrit seulement dans un article du dossier : toujours signalé (point d'attention avec la phrase et la
  pièce, et remis à l'appel court). Toute la suite de tests existante passe, en mesure seule comme avec le
  partage activé.
- Limite honnête : la stratégie, les points et les niveaux propres à l'entreprise sont rédigés par l'IA
  à partir de l'extraction (et non plus du dossier entier). L'extraction contient les valeurs exactes du
  dossier (pénalités, garanties, avance, CA exigé, qualifications, date limite) et la consigne exige les
  valeurs exactes dans chaque clause ; une clause qui dépasse un seuil et manquerait à la liste peut être
  ajoutée ; les mots-clés exclus sont confrontés au dossier entier sans IA (une forme très différente du
  mot saisi, elle, n'est cherchée que dans l'extraction). En contrepartie, la stratégie connaît désormais
  la compatibilité calculée affichée à l'écran (avant, l'IA rédigeait sa recommandation sans la connaître
  et pouvait la contredire).

## 9. Cache de prompt

Vérifié partout où un long texte est relu (rien n'a changé dans ce qui est lu) :

- extraction (consigne de 8 500 caractères) et partie propre à l'entreprise (3 800) : consigne marquée ;
- lecture des pièces en deux temps : la consigne (1 700 caractères, environ 570 tokens) était envoyée en
  texte simple à chaque partie (jusqu'à 80 par dossier) ; elle est maintenant marquée (même texte) ;
- questions sur le dossier : règlement(s) en entier dans un bloc marqué (inchangé) ;
- rédaction du mémoire : dossier de l'acheteur commun dans un bloc marqué pour une heure (inchangé) ;
- autres consignes (veille, questionnaire, rédaction d'une partie) : sous la longueur minimale mise en
  cache (512 tokens sur Sonnet 5.5), le marquage n'y changerait rien. Mistral ignore le marquage (le
  cache y est automatique).

## 10. Données et RGPD

- L'extraction partagée est la lecture du dossier de l'acheteur, sans aucune donnée d'entreprise
  cliente. Ce n'est pas pour autant une donnée sans personne : elle peut contenir des **données
  personnelles publiées par l'acheteur** (nom, email, téléphone de l'agent à contacter, déjà présents dans
  l'analyse de chaque marché) et les **noms de fichiers** du dossier tel qu'il a été importé ; un dossier
  de procédure restreinte n'est pas public. Sa durée est donc **bornée** :
  - effacée quand elle n'a plus servi depuis `ANALYSE_PARTAGEE_JOURS` jours (120) ;
  - effacée quand elle a été faite depuis plus de `ANALYSE_PARTAGEE_DUREE_MAX_JOURS` jours (365), même
    resservie souvent (elle n'est plus resservie au-delà : refaite, sa date repart) ;
  - effacée avec le compte de la **dernière organisation qui l'utilise** (effacement RGPD : toute entrée
    qu'aucune autre organisation n'utilise part avec le compte, dont celles faites sur ses seuls
    fichiers) ;
  - effacée après un jour si aucune analyse réussie ne l'utilise (l'analyse qui l'a faite a échoué
    ensuite et personne ne l'a reçue depuis).
  Purge quotidienne `POST /api/admin/run-trash-purge`.
- Les lignes de mesure (organisation, empreinte, jamais le contenu) sont effacées avec le compte
  (effacement RGPD) et au-delà de `ANALYSE_PARTAGEE_MESURE_JOURS` jours (365). Elles ne figurent pas dans
  l'export RGPD : agrégat interne, sans contenu ; le dossier analysé figure déjà dans l'export (le marché).
- Le texte intégral de chaque marché reste rangé avec le marché et supprimé avec lui (`dce_texte`).
- **À trancher par Eliot (pages juridiques, non modifiées ici)** : le DPA (`dpa.html` : cloisonnement par
  client, suppression des données au terme de la prestation) et la politique de confidentialité ne
  mentionnent pas la mise en commun de l'extraction d'un même dossier entre clients. Avant d'activer
  `ANALYSE_PARTAGEE=1`, les compléter (mise en commun de la seule lecture du dossier de l'acheteur, sans
  aucune donnée du client, durées ci-dessus).

## 11. Réglages

| Variable | Défaut | Effet |
|---|---|---|
| `ANALYSE_PARTAGEE` | `0` (mesure seule) | `1` : analyse en deux temps et partage de l'extraction ; `0` : analyse d'origine en un seul appel, aucun partage (mesure gardée, clé exacte comprise) |
| `ANALYSE_PARTAGEE_MASQUE` | `1` | `0` : extraction resservie à une autre entreprise sans attente |
| `ANALYSE_PARTAGEE_MASQUE_MAX_S` | `600` | attente maximale |
| `ANALYSE_PARTAGEE_ATTENTE_MAX_S` | `1800` | attente maximale d'une extraction du même dossier en cours (import simultané) |
| `ANALYSE_PARTAGEE_JOURS` | `120` | durée de vie d'une extraction qui ne sert plus |
| `ANALYSE_PARTAGEE_DUREE_MAX_JOURS` | `365` | durée de vie maximale d'une extraction, depuis qu'elle a été faite |
| `ANALYSE_PARTAGEE_MESURE_JOURS` | `365` | durée de vie des lignes de mesure |

Changer la consigne de l'extraction : augmenter `analysis.VERSION_CONSIGNES` (le texte entre aussi dans
la clé, comme tous les textes fixes du prompt). Changer la logique de la lecture intégrale : augmenter
`dce_lecture.VERSION` ; de la lecture des pièces : `analyse_dossier.VERSION_LECTURE`.

## 12. Stockage

Révision `w7x8analysepartagee` (après `v6w7preuves`), idempotente : tables `analyses_partagees` (clé
unique, aucune colonne d'organisation ; `parties` et `deroule` pour la lecture en deux temps) et
`analyse_empreintes` (sans clé étrangère, comme `usage_ia`). Testée sur SQLite (chaîne complète, retour
arrière, schéma identique aux modèles) et sur un vrai Postgres depuis l'état exact de la production
(`d6b4d29`, tête `u5v6essaigardefou`) : deux révisions appliquées, aucune donnée perdue, seconde montée
sans effet, rejeu forcé idempotent, valeurs par défaut et unicité côté base, schéma identique à une base
neuve, retour arrière d'une révision puis jusqu'à la production, remontée ; tests rejoués sur cette base.
