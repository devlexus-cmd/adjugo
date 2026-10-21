# La suite de tests sur PostgreSQL

La production tourne sur PostgreSQL (Railway). La suite (pytest, environ 2 200 tests) tourne sur SQLite par
défaut. Elle passe désormais à 100 % sur les deux moteurs, sans recopier le code ni tolérer d'échecs « connus ».
Jusqu'ici, ces échecs tolérés pouvaient cacher un vrai problème à chaque mise en ligne.

## Lancer

### SQLite (défaut, inchangé)

```sh
TZ=UTC ADJUGO_TEST_DB=ma_suite.db pytest
```

### PostgreSQL jetable : `scripts/tests_postgres.py`

Le script démarre un PostgreSQL 16 jetable avec [pgserver](https://pypi.org/project/pgserver/), lance la suite
(ou les fichiers donnés), puis arrête le serveur et efface ses données. Il se lance avec un Python où pgserver
est installé. `--python` donne l'interpréteur du projet, celui qui lance pytest.

```sh
# Suite complète
venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python

# Fichiers ou tests donnés, options de pytest passées telles quelles
venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python tests/test_secu_rgpd.py -x -rfE

# Ce qui suit « -- » va à pytest
venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python -- -k effacement
```

- Le code de sortie est celui de pytest.
- Le serveur démarre dans un dossier unique et écoute sur un socket local, sans port réseau. Plusieurs suites
  peuvent donc tourner en même temps sur la même machine.
- `--dossier` choisit le dossier parent du serveur (par défaut, le dossier temporaire du système).
- `--garder` garde le serveur arrêté et la base de test, pour les inspecter.
- `--ids-decales` est une vérification facultative, décrite plus bas.

### PostgreSQL existant : `ADJUGO_TEST_PG_URL`

```sh
ADJUGO_TEST_PG_URL=postgresql://postgres@localhost:5432/postgres pytest
```

La variable suffit, avec n'importe quel serveur PostgreSQL 13 ou plus récent dont le rôle peut créer une base
(par exemple, un service PostgreSQL dans une CI). À chaque lancement, `tests/conftest.py`, avec l'aide de
`tests/_base_postgres.py` :

1. crée une base neuve au nom unique, `adjugo_test_<pid>_<hasard>`. La base nommée dans l'URL sert seulement à
   se connecter et n'est jamais modifiée ;
2. y monte le schéma par les migrations (`alembic upgrade head`), comme en production. Sur PostgreSQL,
   `app/main.py` ne crée aucune table ;
3. supprime cette base en fin de session (`DROP DATABASE … WITH (FORCE)`). `ADJUGO_TEST_PG_GARDER=1` la garde.

Chaque lancement part donc d'une base vide, comme le fichier SQLite effacé au lancement. Sans cette base neuve,
une base réutilisée verrait ses données s'accumuler et ses compteurs d'identifiants continuer, car PostgreSQL ne
réutilise jamais un identifiant. L'en-tête de pytest indique le moteur et la base utilisés ; il est masqué par
`-q`, donc visible seulement avec `-o addopts=`.

`pytest.ini` contient déjà `-q`. Un `-q` de plus masque la ligne de total : lancez avec `-o addopts=` ou lisez
le fichier `--junitxml`.

## Ce qui a été corrigé

Aucun défaut du logiciel n'a été trouvé : sur PostgreSQL, tous les échecs venaient des tests. Le code de
l'application, les migrations et les pages juridiques ne changent pas, ni le comportement pour les clients.

Aucune assertion n'a été retirée et aucun test n'a été supprimé ni marqué skip ou xfail. Deux recherches de texte
ne confondent plus une date (point 4) ou un morceau d'identifiant (point 6) avec ce qu'elles cherchent ; tout le
reste est cherché comme avant. Des vérifications ont été ajoutées (points 1 et 3).

1. **Clés étrangères (`fk_on`), dans 4 fichiers.** `test_secu_rgpd.py`, `test_secu2_donnees.py`,
   `test_secu4_final.py` et `test_secu5_sauvegardes_ancrage.py` avaient chacun leur propre fixture `fk_on`, qui
   lançait `PRAGMA foreign_keys=ON`. Cette commande n'existe que sur SQLite. Les 4 copies sont remplacées par une
   seule fixture, dans `tests/conftest.py`, qui vérifie la même garantie sur les deux moteurs :
   - SQLite : PRAGMA sur chaque connexion, le temps du test, et contrôle que le réglage est actif ;
   - PostgreSQL : rien à activer, ce sont les vraies contraintes posées par les migrations ;
   - sur les deux moteurs, avant le test : une ligne orpheline (journal rattaché à un compte qui n'existe pas)
     doit être refusée ;
   - l'écouteur est retiré quoi qu'il arrive (`try/finally`).

   Avant cette correction, le contrôle de `test_secu_rgpd.py` échouait avant le `yield`. L'écouteur restait alors
   branché, et toute connexion suivante échouait. D'où les « 6 échecs et 45 erreurs » et la « contamination » de
   `test_secu_fichiers.py`, `test_smoke.py` et des fichiers lancés ensuite.
2. **Journaux d'un compte inventé, dans 2 tests.** Il s'agit de
   `test_hotfix_v2_fuites.py::test_fourche_historique_toleree_alteration_detectee` et
   `test_secu3_final.py::test_verify_org_chains_prefixe`. Ces tests écrivaient le journal d'un `owner_id` sans
   compte, ce qu'interdit la clé `audit_logs.owner_id → users.id` de la production. `audit.record` avalait le
   refus, rien n'était écrit, et le test échouait. Ils utilisent maintenant un vrai compte, avec les mêmes
   assertions.
3. **Dépendance à l'ordre :
   `test_reseau_partenaires.py::test_cron_borne_et_jamais_de_depublication_sur_erreur`.** Le cron traite au plus
   25 profils, du moins récemment regardé au plus récent (`last_check_at`, à défaut `verified_at`). Or
   « Vérifier », lancé à la publication du profil du test, pose `last_check_at` à maintenant : ce profil était
   donc le dernier de la file. Dès le 1er passage (panne réseau totale), il n'était traité que si au plus 24
   autres profils publiés par les tests précédents avaient été regardés avant lui ; au-delà d'environ 37, il
   sortait aussi du lot au 3e passage. Un passage qui ne le traitait pas réussissait sans rien vérifier : avec 27 profils publiés
   (les 6 fichiers qui en publient, ce test en dernier), un cron qui efface la vérification précédente sur une
   panne passait inaperçu, sur les deux moteurs. Le test remet maintenant ce profil en tête de file avant
   chacun des 4 passages, le 1er compris (la date `verified_at` ancienne qu'il posait ne servait pas au tri).
   Seule la clé de tri (`last_check_at`) change. Après chaque passage, le test vérifie aussi que ce passage a
   bien porté sur ce profil : avant, une absence de traitement passait pour un succès.
4. **Dépendance à la date, dans 3 tests.** Il s'agit de `test_compte_rendu_de_la_demonstration`,
   `test_compte_rendu_du_groupement_dit_juste` et `test_pdf_compte_rendu_balisage_voulu_rendu`. Ils vérifient
   l'absence de « 1/1 », « 1/2 » ou « 2/2 » dans le compte-rendu PDF. Or les dates imprimées en contiennent selon
   le jour : « édité le 21/10/2026 », « figée le 21/10 », « 05/11/2026 », « 05/12/2026 ». La recherche se fait
   maintenant sur le texte privé de ses seules dates, celles qui suivent « le ». Tout autre « N/M » reste trouvé.
   Une sonde l'a vérifié pour chaque jour de 2026 à 2028. *Réunion du 22/10 :* la vague 2b, le moteur (lot 1) et
   les pages annexes avaient corrigé les mêmes contrôles chacun à sa façon ; une seule fonction les remplace,
   `compteur` dans `tests/textes_visibles.py`. Elle retire toutes les dates sur deux chiffres (« 21/10 »,
   « 05/12/2026 », avec ou sans « le » devant), puis cherche le « N/M » tel quel : elle trouve tout ce que
   trouvaient les quatre corrections hors des dates.
5. **Compte administrateur gardé d'un test à l'autre (`_admin_headers`, `test_reseau_partenaires.py`).** Avant de
   réutiliser ce compte, le test vérifie qu'il existe encore et reste administrateur. Sinon, il en recrée un.
   Rien ne repose plus sur un identifiant gardé entre deux tests sans revérification.
6. **Prix cherchés dans un texte qui contient des identifiants, 6 assertions.** Elles sont dans
   `test_convention_groupement.py` (3 tests) et `test_cotraitance_v4.py` (2 tests). Ces tests vérifient qu'un prix
   (« 40000 », « 125000 », « 100000 ») ne fuite pas dans une vue JSON. Ils cherchaient la suite de chiffres
   n'importe où, y compris dans un identifiant : avec des identifiants de production, la référence « AO-40000085 »
   du marché n° 40000085 faisait échouer `test_doctrine_brouillon_puis_generee`. Le constat est venu de
   `--ids-decales`, plus bas. Ils cherchent maintenant ce nombre écrit comme un nombre, avec `_nombre_present` :
   « 40000 », « 40000.5 » ou « : 40000, » sont trouvés ; « AO-40000085 », « 1400000 » et une empreinte « …a40000f… »
   ne le sont pas. Les formes écrites (« 40 000 », « 125 000 ») restent cherchées partout, comme avant.

## Vérifier l'indépendance aux identifiants : `--ids-decales`

Avec `--ids-decales` (ou `ADJUGO_TEST_PG_IDS_DECALES=1`), chaque table numérote à partir d'un point différent
(1 000 007, 2 000 007…) au lieu de 1. Sur une base neuve, le compte n° 5, l'organisation n° 5 et le marché n° 5
coexistent : un identifiant pris pour un autre passe inaperçu. En production, les compteurs ont divergé depuis
longtemps. Avec cette option, une telle confusion fait échouer le test, et aucun test ne peut compter sur un
identifiant précis : par exemple, le compte de démonstration n'a plus le n° 1.

## Résultats de référence (21/10/2026, depuis la production 0afc1ed)

Suite complète, ordre naturel, `TZ=UTC`, venv Python 3.12 installé depuis `requirements.lock` :

| Moteur | Tests | Réussis | Échecs | Erreurs | Ignorés |
|---|---|---|---|---|---|
| SQLite (défaut) | 2 205 | 2 205 | 0 | 0 | 0 |
| PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`) | 2 205 | 2 205 | 0 | 0 | 0 |

Avant ces corrections, sur la même suite : SQLite donnait 1 échec (la date du jour) ; PostgreSQL donnait 20 échecs
et 24 erreurs.

Contrôles d'indépendance, suite complète, tous réussis (2 205 sur 2 205) :

- fichiers en ordre inverse : sur SQLite et sur PostgreSQL ;
- fichiers mélangés : sur SQLite ;
- tous les tests mélangés d'un fichier à l'autre : sur SQLite ;
- tous les tests mélangés d'un fichier à l'autre, avec `--ids-decales` : sur PostgreSQL.

D'autres contrôles ont été faits sur une partie de la suite :

- **Cron :** dans l'ordre de fichiers qui faisait échouer le test du cron, ce test échoue sur le code de production
  (1 échec sur 295) et passe après correction (295 sur 295), sur SQLite comme sur PostgreSQL. Le 1er passage
  a été contrôlé par mutation (le cron efface `verified_sirene` sur une panne de SIRENE), sur les deux moteurs :
  avant la remise en tête du 1er passage, la mutation passait inaperçue dans deux ordres (233 sur 233 pour les 6
  fichiers qui publient des profils, ce test en dernier, 27 profils publiés ; 93 sur 93 pour un ordre de 46
  profils publiés), alors que le test lancé seul la détectait. Après, elle est détectée dans les deux ordres
  (1 échec, sur `verified_sirene`), et le code intact y passe (233 sur 233, 93 sur 93).
- **Clés étrangères :** une fois la clé `audit_logs_owner_id_fkey` retirée de la base de test PostgreSQL, la
  fixture `fk_on` échoue (« DID NOT RAISE »). Son contrôle détecte donc bien des clés étrangères absentes.
- **Dates :** les 3 tests du compte-rendu passent avec 7 dates d'édition simulées (21/10, 05/11, 05/12, 11/01,
  22/02, 11/11 et 12/12).

La première exécution avec `--ids-decales` a révélé l'assertion décrite au point 6.

Deux tests dépendent du temps de calcul, pas du moteur : `test_dpgf_csv_volumineux_borne` et
`test_dpgf_csv_borne_avant_le_travail_sur_les_cellules`. Ils mesurent en secondes un contrôle de CSV, sans aucune
base. Une fois, la machine était très chargée par d'autres suites (charge 25) : ils ont échoué sur PostgreSQL, et
de la même façon sur SQLite (2,05 s mesurées pour une limite de 2 s). À charge normale, ils passent sur les deux
moteurs. Ils n'ont pas été modifiés.
