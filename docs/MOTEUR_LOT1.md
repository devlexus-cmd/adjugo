# Moteur de recherche, lot 1 « Dire juste » : le contrat

*Partie serveur du lot 1 (note de décisions du 21/10/2026, « La première étape que je lancerais », points 1 à 9).
Code de départ : `0afc1ed` (production). La partie écran (points 10 à 13) viendra après la vague 2b.*

Décisions d'Eliot du 21/10 appliquées ici : lancer le lot 1 côté serveur (décisions 1 et 2) ; ne plus écarter un
marché d'une alerte à cause de sa note calculée avant le dossier (décision 11) ; garder le repli payant de l'onglet
« À venir », le noter dans le journal dès maintenant, annoncer le crédit à l'écran plus tard (décision 12) ; rien
sur la veille des projets à venir, sauf fermer ses anciennes adresses.

---

## Services

*Points 4 bis, 5, 6, 7, 8 et 9 de la note. Fichiers modifiés : `app/services/decp.py`, `app/services/renewal.py`,
`app/routers/sourcing.py`, `app/sourcing/schemas.py` (une ligne), `app/services/alerts.py` (alertes de marchés
seulement), `app/routers/amont.py` ; nouveaux : `scripts/mesure_rappel.py`, `tests/test_moteur_lot1_services.py`,
`tests/fixtures/moteur_lot1_services/` ; tests adaptés : `tests/test_essai_termine.py`, `tests/test_secu_fichiers.py` (point 7) et
`tests/test_reorganisation_v1_relecture.py` (un test qui dépendait de la date, voir « Vérifications »). Aucun fichier de l'écran
(`app/static/*`, traductions), aucun fichier de `app/sourcing/sources/`, ni `app/sourcing/search.py`, ni
`app/sourcing/scoring.py`. Ni prix, ni quota, ni IA ajoutée, ni changement de base de données, ni nouveau
planificateur. Le robot de Mégalis n'est pas touché.*

### Ce qui change pour le client (récapitulatif pour Eliot)

1. Onglet « À venir », outre-mer : seules les fins de contrat du département demandé (974 ne montre plus 971) ; le
   département s'affiche sur 3 chiffres (« 974 »). « 6 » saisi seul est lu dans la DECP (sans crédit) au lieu de passer par le repli payant.
2. Recherches de partenaires « Chercher » (page du marché) et « Répartition proposée » : des PME seulement ; les
   grandes entreprises n'y sont plus proposées.
3. Courriels d'alerte : plus de marchés (plus aucun écarté par la note avant dossier) ; au-delà de 10 par alerte, la
   ligne « … et N autres marchés : relancez cette recherche dans Adjugo pour les voir tous. » ; moins de marchés
   reçus deux fois. « Tester » une alerte annonce plus de nouveaux marchés.
4. API seulement (rien à l'écran) : `past_wins` vaut `null` quand les marchés gagnés n'ont pas pu être lus ;
   les adresses de la veille masquée répondent 404 (aucun écran n'y mène).
5. Rien d'autre : l'alerte hebdomadaire (aucun client), le journal du repli payant et l'outil de mesure ne se voient
   pas.

### Comment c'est prouvé

- **Tests** : `tests/test_moteur_lot1_services.py`, 13 tests, sans réseau (toute lecture est remplacée par un jeu
  d'essai, l'IA est simulée). Les 13 échouent sur `0afc1ed` : vérifié en copiant ce fichier et ses jeux d'essai dans
  un export de `0afc1ed` (`git archive`), voir « Vérifications » en fin de section.
- **Jeux d'essai** (`tests/fixtures/moteur_lot1_services/`) : de vraies réponses publiques lues le 21/10/2026 par 6
  requêtes GET, avec l'en-tête honnête d'Adjugo (`AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)`), une
  requête par seconde au plus : DECP (un enregistrement complet pour lire les champs, non gardé ; les fins de
  contrat de travaux de La Réunion 974, de la Guadeloupe 971 et de la Corse-du-Sud 2A ; les marchés d'une
  entreprise titulaire en Corse) et BOAMP (avis d'attribution de voirie du Finistère). Les numéros des titulaires
  (entreprises, parfois des entrepreneurs individuels) sont remplacés par des numéros fictifs ; tout le reste est
  tel que lu (objets, acheteurs publics, codes de lieu, dates, procédures, montants). Aucune autre requête réseau.
- **Formes réellement observées** dans la DECP : l'outre-mer arrive en code postal (« 97432 », « 97110 », type
  « Code postal ») ; la Corse en « 2A » (type « Code département ») ou en code postal « 20110 », « 20142 ».

### 4 bis. Outre-mer dans les fins de contrat

| | |
|---|---|
| **Avant** | Les départements étaient coupés à 2 caractères dans la route (`app/routers/sourcing.py:318` de `0afc1ed`), dans la lecture de la DECP (`app/services/decp.py:72`) et dans le filtre des lignes (`:111`). Une recherche « 974 » demandait « 97 » à la DECP et gardait toute l'outre-mer (971 à 976). « 6 » saisi seul était demandé tel quel (`startswith "6"` : départements 60 à 69) puis tout était écarté, ce qui déclenchait le repli payant. La note de zone d'une fin de contrat (`app/services/renewal.py:148`) comparait elle aussi sur 2 caractères. |
| **Après** | Une seule règle, `code_departement` (`app/services/decp.py:28`) : 2 chiffres en métropole (« 6 » → « 06 », « 29232 » → « 29 »), 3 en outre-mer (« 97432 » → « 974 »), Corse « 2A » / « 2B » inchangée, code postal corse « 20… » laissé à « 20 » (il ne dit pas 2A ou 2B : on ne devine pas). Le filtre des lignes répète exactement le filtre envoyé à la DECP (`dans_les_departements`, `:45` : le code du lieu commence par le département voulu). La route (`app/routers/sourcing.py:322`) et la note de zone (`app/services/renewal.py:149`, `_departements_voulus`) suivent la même règle. « 97 » saisi seul garde toute l'outre-mer, comme avant. |
| **Preuve** | `test_fins_de_contrat_sur_le_code_complet_974_ne_voit_plus_971_corse_et_metropole_inchangees` (vraies lignes 974, 971 et 2A) ; `test_onglet_a_venir_demande_le_code_complet_et_note_la_zone_d_outre_mer` (de bout en bout par la route, et la note de zone 974 contre 971). |
| **Pour le client** | Onglet « À venir » d'une entreprise d'outre-mer : seules les fins de contrat de son département ; le département affiché est « 974 » au lieu de « 97 ». « 6 » saisi seul est lu dans la DECP, sans crédit, au lieu de passer par le repli payant. Métropole et Corse : inchangé. |

### 5. Partenaires

**5 a. Une panne de la DECP n'est plus lue « 0 marché »**

| | |
|---|---|
| **Avant** | `wins_by_siren` rendait `{"count": 0}` quand la DECP ne répondait pas (`app/services/decp.py:162-164`), et `past_wins` valait 0 par défaut (`app/sourcing/schemas.py:128`), y compris pour une entreprise jamais consultée (au-delà des 12 premières). La note de synergie de la recherche de partenaires disait alors « Aucun marché public gagné trouvé en source DECP pour ce SIRET. » (`app/sourcing/scoring.py:432`), sans l'avoir lu. Le numéro de l'entreprise était écrit dans le journal à chaque panne. |
| **Après** | Une panne (ou une réponse sans compte lisible) lève `DecpIndisponible` (`app/services/decp.py:23`, `:200`, `:203`) ; le numéro n'est plus écrit dans le journal. `past_wins` vaut `None` tant que rien n'a été lu (« non vérifié », `app/sourcing/schemas.py:129`) : l'enrichissement de `app/sourcing/search.py`, inchangé, laisse alors la valeur inconnue. Sur la route `/api/sourcing/cotraitants`, une entreprise au compte inconnu reçoit la note « Marchés publics gagnés non vérifiés en source DECP pour ce SIRET. » (`app/routers/sourcing.py:1397`, `:1430`). Un vrai zéro lu reste un zéro. |
| **Preuve** | `test_panne_de_la_decp_jamais_lue_zero_marche` (panne, réponse sans compte, zéro lu ; recherche de partenaires ; route). |
| **Pour le client** | Rien de visible à l'écran : la pastille « N gagné(s) » ne s'affiche ni pour 0 ni pour un compte inconnu, et la note de synergie n'est affichée nulle part (`app/static/app.html`, `app.js`). Dans les réponses de l'API, `past_wins` vaut `null` au lieu de `0` quand le compte n'a pas été lu. |

**5 b. « PME seulement » sur les deux recherches de partenaires qui ne l'avaient pas**

| | |
|---|---|
| **Avant** | La recherche « Chercher » de la page du marché (`/api/sourcing/cotraitants`, `app/routers/sourcing.py:1388-1390` de `0afc1ed`) et la répartition proposée partie par partie (`/api/sourcing/groupement`, `:214-215`) interrogeaient le registre sans filtre de taille ; le verdict de groupement, lui, l'avait déjà (`app/services/groupement_verdict.py:300`). |
| **Après** | Les deux passent `pme_only=True` (`app/routers/sourcing.py:217`, `:1418`) : le registre est interrogé avec la catégorie INSEE « PME » (micro-entreprises comprises, `app/sourcing/sources/sirene.py:94-97`, inchangé). |
| **Preuve** | `test_pme_seulement_sur_les_deux_recherches_de_partenaires` (paramètres envoyés au registre, pour les deux routes). |
| **Pour le client** | Les grandes entreprises et les entreprises de taille intermédiaire ne sont plus proposées comme partenaires sur ces deux écrans. Non mesuré : la part d'entreprises sans catégorie calculée par l'INSEE (récentes), que ce filtre écarte aussi, comme déjà dans le verdict de groupement. |

### 6. Alertes de marchés (pas les rappels d'invitation)

**6 a. Plus aucun tri caché par la note avant dossier (décision 11)**

| | |
|---|---|
| **Avant** | Un marché n'était envoyé que si sa note avant dossier atteignait le seuil de l'alerte, ou à défaut le seuil « bon potentiel » de « Ce que je cherche » (`app/services/alerts.py:393-401` de `0afc1ed`). Le reste était écarté sans le dire, sur une note encore faussée. |
| **Après** | Aucun marché n'est écarté à cause de sa note (`run_one_saved_search`, `app/services/alerts.py`). La liste reste triée dans l'ordre de la recherche ; le courriel montre toujours 10 marchés au plus par alerte ; au-delà, une ligne les compte : « … et N autres marchés : relancez cette recherche dans Adjugo pour les voir tous. » (`:531`, règle 8 du moteur : rien n'est caché en silence). Le seuil reviendra en V2, réglable et annoncé. La colonne `min_score` reste en base et dans l'API, mais n'écarte plus rien. |
| **Preuve** | `test_alerte_n_ecarte_plus_un_marche_a_cause_de_sa_note_avant_dossier` (deux marchés notés 90 et 30 sous un seuil de 70 : les deux partent ; « Tester » dit 2) ; `test_courriel_compte_les_marches_au_dela_des_dix_premiers`. |
| **Pour le client** | Les courriels d'alerte peuvent contenir plus de marchés ; une ligne « … et N autres marchés » apparaît au-delà de 10. « Tester » une alerte annonce plus de nouveaux marchés. |

**6 b. « Hebdomadaire » réellement appliqué**

| | |
|---|---|
| **Avant** | Une alerte « hebdomadaire » partait à chaque appel programmé, comme une quotidienne (`app/services/alerts.py:425`). Aucun client ne peut la choisir (l'écran crée des alertes quotidiennes) : précaution. |
| **Après** | Une alerte hebdomadaire déjà servie repart 7 jours de Paris après son dernier passage, quelle que soit l'heure de l'appel (`_hebdomadaire_pas_encore_due`, `:485`, `:510`) ; jamais servie, elle part au premier passage. Le compte rendu de l'appel programmé dit combien attendent (`weekly_not_due`, `:542`). |
| **Preuve** | `test_hebdomadaire_reellement_applique` (2 jours : attend ; 7 jours : part ; quotidienne et hebdomadaire neuve : partent). |
| **Pour le client** | Aucun aujourd'hui (seule la démo, qui n'est pas servie, en a une). |

**6 c. Chaque référence porte le nom de sa source ; les anciennes restent reconnues**

| | |
|---|---|
| **Avant** | La mémoire d'une alerte (`last_seen_refs`) gardait la référence nue de la première source (`app/services/alerts.py:396-397`, `:410-411`). Un même marché vu sur le BOAMP et sur Mégalis était renvoyé le jour où Mégalis le rendait seul (autre référence). Un numéro nu d'une source pouvait masquer le marché d'une autre. La liste repassait par un ensemble avant d'être coupée à 500 : des références étaient retirées au hasard, dont celles de marchés encore ouverts, renvoyés ensuite. |
| **Après** | Une entrée par marché, avec toutes ses références écrites « SOURCE\|référence » (l'avis et chaque source où il a été vu), jointes par « + » (`_refs_du_marche`, `:400` ; `_memoriser`, `:383`). Une entrée ancienne (référence nue, ou clé de fusion nue) est reconnue, puis fusionnée dans l'entrée du marché quand il revient. L'ordre est gardé, le marché vu aujourd'hui passe en fin de liste, et seuls les plus anciens sortent au-delà de 500 marchés (même borne qu'avant, `:372`). « N marché(s) déjà vu(s) » compte toujours des marchés. |
| **Preuve** | `test_references_avec_leur_source_anciennes_reconnues_rien_renvoye_deux_fois` (mémoire ancienne de 41 références ; jour 1 BOAMP + Mégalis ; jour 2 Mégalis seul : rien de renvoyé ; ordre exact ; compte de l'écran) ; `test_memoire_bornee_aux_plus_anciens_jamais_au_hasard`. |
| **Pour le client** | Moins de marchés reçus deux fois. Aucun marché déjà reçu n'est renvoyé au passage à la nouvelle forme. |

### 7. Les adresses de la veille masquée refusent proprement

| | |
|---|---|
| **Avant** | `/api/amont/scan`, `/analyze-upload` et `/analyze-text` répondaient à tout utilisateur connecté, l'interrupteur éteint : un appel direct débitait une analyse et appelait l'IA ; `/auto` pouvait réactiver l'ancienne veille (`app/routers/amont.py:122-213` de `0afc1ed`). |
| **Après** | Tant que `PROJETS_A_VENIR` est éteint, les trois adresses répondent 404 « « Projets à venir » n'est pas encore ouvert : rien n'a été analysé ni décompté. », AVANT toute lecture de fichier, toute recherche, tout appel à l'IA et tout débit (`_exiger_ouverte`, `app/routers/amont.py:37`, appelée `:140`, `:158`, `:181`). L'activation par `/auto` répond 404 avec sa phrase (`:231`). Ce qui reste ouvert, volontairement : la désactivation par `/auto` (retirer son accord aux courriels ne coûte rien et ne doit jamais être bloqué), la lecture de l'état (`GET /auto`), la liste et la suppression des signaux gardés. Interrupteur allumé : comportement inchangé. |
| **Preuve** | `test_adresses_de_la_veille_masquee_refusent_sans_debiter` (aucune lecture, aucun appel à l'IA, aucun débit, abonnement resté éteint ; puis interrupteur allumé : réponses d'avant). `tests/test_essai_termine.py` rallume l'interrupteur dans ses deux tests de la veille, qui vérifient le refus propre à l'essai terminé ; `tests/test_secu_fichiers.py` aussi, pour vérifier la lecture bornée à 50 Mo de `/analyze-upload` veille ouverte (veille fermée, rien n'est lu). |
| **Pour le client** | Rien à l'écran (aucun écran n'y mène tant que la veille est masquée). Un appel direct ne coûte plus d'analyse. |

### 8. Le repli payant de l'onglet « À venir » est noté dans le journal (décision 12)

| | |
|---|---|
| **Avant** | Quand la DECP ne donnait rien ou ne répondait pas, le repli BOAMP + IA débitait une analyse (remboursée s'il ne trouvait rien), sans aucune trace de ce qu'il trouvait (`app/routers/sourcing.py:329-344` de `0afc1ed`). |
| **Après** | Le repli est gardé tel quel (même débit, même remboursement). Chaque repli écrit UNE ligne dans le journal (`_journal_repli_a_venir`, `app/routers/sourcing.py:358`) : son motif (« DECP sans résultat », « DECP indisponible » ou « DECP en erreur »), les départements (codes de 2 ou 3 caractères), le nombre de fins de contrat trouvées, combien ont une durée lue et combien une durée estimée par type de contrat, le nombre d'erreurs de source, le sort de l'analyse (« débitée », « remboursée », ou « remboursée (repli en échec : …) ») et les références publiques des avis d'attribution du BOAMP (10 au plus). **Sans donnée personnelle** : ni utilisateur, ni organisation, ni adresse, ni mots tapés. Exemple : `repli payant « À venir » (BOAMP + IA) : motif=DECP indisponible ; départements=29 ; fins de contrat trouvées=3 (durée lue 1, durée estimée 2) ; erreurs de source=0 ; analyse débitée ; avis BOAMP=25-34232,25-10734,25-8460`. Niveau INFO, écrit en production (`LOG_LEVEL` vaut INFO par défaut, `app/core/config.py:41` ; la valeur posée dans Railway n'est pas vérifiée). |
| **Preuve** | `test_repli_payant_note_dans_le_journal_sans_donnee_personnelle` (vrais avis d'attribution du BOAMP, IA simulée ; repli qui trouve : débité ; repli vide : remboursé). |
| **Pour le client** | Rien. L'annonce du crédit avant le clic est un point de la partie écran (point 12), après la 2b. |

### 9. L'outil rejouable de mesure du rappel

| | |
|---|---|
| **Avant** | Aucun outil (moteur § 4.4, point 1). |
| **Après** | `scripts/mesure_rappel.py`, outil de poste, jamais lancé en production, sans IA. `collecter` lit dans la DECP (en-tête honnête, une requête par seconde) les marchés gagnés depuis 12 mois par chaque PME de la liste de Mathys (titulaire 1, 2 ou 3), les dédoublonne et classe leur publicité d'après la procédure publiée (« avec », « sans », « inconnue » sous le seuil de dispense) ; Mathys vérifie, marché par marché, si l'annonce était dans une source qu'Adjugo lit (colonne `avis_vu`) ; `mesurer` rejoue, sans réseau, les règles du code de ce jour-là (mots : règle de la recherche BOAMP ; zone : `app/services/decp.py` ; type : code CPV) et rend le rappel en fourchette [bas, haut] tant que des lignes ne sont pas vérifiées. Les fichiers restent HORS du dépôt (le script refuse un chemin du dépôt) ; le bilan JSON ne contient que des comptes. Mode d'emploi en tête du script. |
| **Preuve** | `test_mesure_du_rappel_rejouable_sans_reseau` (vrais marchés d'une entreprise de Corse, numéro fictif : fenêtre de 12 mois, doublons, publicité, mesure avant et après vérification, bilan sans objet ni numéro) ; `test_mesure_du_rappel_refuse_le_depot_et_suit_la_regle_de_la_recherche_boamp` (les motifs rejoués sont exactement ceux que `BoampSource` envoie au BOAMP : si la règle change, ce test le signale). |
| **Pour le client** | Rien. Pour la mise en ligne du lot : la liste des numéros d'entreprise des PME en test, par Mathys, puis `collecter` et `mesurer --etiquette avant-lot1` avant la mise en ligne. |
| **Non vérifié** | L'équivalence exacte de la règle des mots avec l'opérateur `like` d'OpenDataSoft (découpage en mots, accents). Le BOAMP lit aussi son vocabulaire interne (descripteur), absent de la DECP : un « mots : non » peut sous-estimer ce que la recherche aurait trouvé, et la raison le dit. Les seuils de dispense (100 000 € HT en travaux, 60 000 € HT sinon, étude moteur § 5.1) sont ceux de 2026 ; pour les marchés notifiés fin 2025, le seuil des fournitures et services était peut-être plus bas : le classement « avec » est donc prudent (un marché classé « inconnue » est vérifié par Mathys). La DECP publie avec retard (32,6 % des lignes plus de 60 jours après la notification, moteur § 5.3) : les derniers mois de la fenêtre sont incomplets, d'où la mesure sur la MÊME liste avant et après. |

### Ce qui ne change pas

- La démo : ses fins de contrat, sa recherche et l'aperçu de ses alertes sont servis à part (`app/services/demo_search.py`, `app/routers/saved_searches.py:95-103`), sans réseau ni IA ; l'aperçu de la démo garde son propre seuil fictif.
- Prix, quotas, débits et remboursements (le repli payant débite et rembourse comme avant).
- Aucune IA ajoutée ; le robot de Mégalis, ses limites et son refus sans contournement ; un seul processus, aucun nouveau planificateur ; aucune nouvelle route de données, cloisonnement de la co-traitance intact.
- Les alertes lisent toujours 25 résultats par recherche ; le courriel ne donne aucune note sur 100.

### Relevé en passant, non corrigé (hors du périmètre de ce chantier)

- La répartition proposée partie par partie (`/api/sourcing/groupement`) tire le département du lieu d'exécution sur 2 chiffres (`app/routers/sourcing.py:191-198`) : outre-mer, elle cherche des partenaires dans « 97 ». Même défaut que le point 4 bis, sur une autre route.
- `app/services/agents/amont.py:_deps` coupe toujours à 2 caractères : c'est la veille, traitée à sa vague 1.
- La note de synergie inconnue est posée par la route (`app/routers/sourcing.py:1430`) parce que `app/sourcing/scoring.py` appartient à l'autre chantier ; `synergy_score` pourra lire `past_wins = None` lui-même quand ce fichier sera repris.

### Vérifications

- **Les 13 nouveaux tests échouent tous sur `0afc1ed`**, chacun sur le défaut qu'il couvre : copiés avec leurs jeux
  d'essai dans un export de `0afc1ed` (`git archive`), ils rendent par exemple `['97'] == ['974']` (route et lecture
  DECP), « DID NOT RAISE » (panne lue « 0 marché »), des paramètres du registre sans `categorie_entreprise`, un seul
  marché sur deux sous le seuil de note, `['26-98235'] == ['BOAMP|26-98235']` (référence sans source), l'alerte
  hebdomadaire rejouée au bout de 2 jours, l'absence de la ligne « … et 2 autres marchés », une réponse 200 de
  `/api/amont/scan` interrupteur éteint, aucune ligne de journal pour le repli payant, et l'outil absent.
- **Suite complète** : verte sur cette branche, 2 218 tests sur 2 218 (2 205 sur `0afc1ed` + les 13 nouveaux). Sur `0afc1ed`, le 21/10/2026, un
  seul échec, sans lien avec ce chantier : `test_compte_rendu_de_la_demonstration`
  (`tests/test_reorganisation_v1_relecture.py`) vérifie qu'aucun « 1/1 » n'apparaît dans le compte-rendu, or la date
  « édité le 21/10/2026 » en contient un. Le test retire désormais les dates (toujours sur 2 chiffres) avant de
  chercher « 1/1 » ; un vrai « 1/1 » reste détecté.
- **Aucun changement de base de données** : la nouvelle forme de la mémoire des alertes tient dans la colonne JSON
  existante (`saved_searches.last_seen_refs`), sans migration ; aucun essai Postgres n'était donc nécessaire.
- Tests lancés avec `ADJUGO_TEST_DB=<nom>.db TZ=UTC`, Python 3.12 depuis `requirements.lock`.
