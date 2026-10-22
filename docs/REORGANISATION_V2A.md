# Réorganisation de l'interface : vague 2a, « un marché, une page, une adresse »

Contrat de la vague 2a. Étude : « Réorganiser l'interface d'Adjugo : étude définitive » (12/10/2026), § 5.3, 7, 8, 9
(vague 2a et « Ensuite »), 10 et 11. Base : `feat/produit-acheteur-collectivites` = `fab9d9a` (production du
20/10/2026 : vagues 0 et 1, contrat `docs/REORGANISATION_V1.md`). Tête Alembic de départ : `b3mesureecrans` ; tête
d'arrivée : `c4montantseul` (`b3mesureecrans` → `c4axeetapes` → `c4montantseul`).

Décisions de la vague (recommandations de l'étude, validées par Eliot) : D7 (un seul axe d'étapes, la clé « envoye »
migre, la barre affiche des statuts dérivés), D10 (« partie (lot n) » partout, tests compris), D11 (une carte de Mes
marchés avant la publication, « Suivre » reste dans Trouver des marchés), D18 (barre basse de 5 sur téléphone) ; D8
et D9 comme en vague 1. La vague 2b (prise en main, marché d'exemple, espace partenaire réduit) vient après : rien ici.

La vague a été menée en trois chantiers parallèles, puis réunis :

| Chantier | Contenu | Section |
|---|---|---|
| **A1** adresses et étapes | Une adresse par écran (précédent sur plusieurs niveaux, liens, rechargement), un seul axe d'étapes (D7, migration `c4axeetapes`), la décision dans l'étape Décider, la carte « À venir » (D11), la barre basse (D18), la cloche et « À faire » | § A1 |
| **A2** Mes marchés et invitations | Mes marchés en liste filtrable (Tous · Je pilote · Où je suis partenaire · À plusieurs), Bilan en onglet, une seule fenêtre d'invitation (3 cas), un seul « Qui me complète ? », une seule liste « Prêt à déposer » (calcul pour l'entreprise seule), un seul « Figer l'offre » | § A2 |
| **A3** entreprise, documents, confirmations, vocabulaire | Mon entreprise en 4 onglets (Tarifs, « Ce que je cherche »), le montant que je porte seul (migration `c4montantseul`), Mes documents (catégorie, date de fin), la fenêtre de confirmation de l'application au lieu des 19 `confirm()` / `prompt()`, « partie (lot n) » (D10) | § A3 |
| **Réunion** | Les trois chantiers sur la production, ce qui se croisait entre eux, vérifications d'ensemble | § R |
| **Relecture** | Les 10 remarques de la relecture, reproduites ; 10 retenues et corrigées (une seule est de la documentation) | § L |
| **Contre-relecture** | Les 3 remarques de la contre-relecture (deux sur la même correction), reproduites et corrigées | § M |

Les sections A1, A2 et A3 décrivent chaque chantier tel qu'il a été fait ; quand la réunion a changé un point, la
section le dit (« Réunion : … ») et le § R le détaille.

---

## A1. Adresses et étapes

Tests : `tests/test_reorganisation_v2a_adresses_etapes.py` (28 tests : routes, chemins sous Node, retour arrière
multi-niveaux sur un navigateur simulé avec les vraies méthodes, courriels, axe, API, migration SQLite, barre et ses
statuts dérivés, décision, barre basse, cloche, « À faire », icônes, traductions, démonstration). Postgres :
`scratchpad/a1/run_pg_axe.py` et `scratchpad/a1/compare_pg.py` de la session (§ A1.6).

### A1.1 Une adresse par écran

**Le serveur.** `GET /app/{chemin:path}` sert la même page que `/app` (`app/main.py`), avec l'en-tête de non-mise en
cache (`Cache-Control: no-store, must-revalidate`, `Pragma: no-cache` : le middleware couvre maintenant `/app/…`) et
les mêmes en-têtes de sécurité. Le serveur ne lit jamais le chemin : rien ne s'ouvre sans session, et chaque donnée
reste protégée par sa route `/api` (un marché d'une autre organisation répond 404, l'écran dit « Ce marché n'est plus
accessible » et ouvre Mes marchés). `/apps` reste 404 ; `/acheteur/app` ne change pas.

**Les chemins** (`ADRESSES`, en tête de `app.js`, fonctions pures `adresseDe` et `etatDeAdresse`) : des mots, sans
accent ni « # ».

| Écran | Adresse |
|---|---|
| Accueil | `/app` |
| Trouver des marchés › Publiés · À venir · Mes alertes | `/app/trouver` · `/app/trouver/a-venir` · `/app/trouver/alertes` |
| Trouver des marchés › Projets à venir (si `PROJETS_A_VENIR=1`) | `/app/trouver/projets-a-venir` |
| Mes marchés › Marchés (filtres Tous · Je pilote · Où je suis partenaire · À plusieurs) | `/app/marches` · `/app/marches/je-pilote` · `/app/marches/partenaire` · `/app/marches/a-plusieurs` (réunion : des filtres de la liste, § R.2) |
| Mes marchés › Devis et factures · Bilan | `/app/marches/devis-et-factures` · `/app/marches/bilan` |
| Un marché · son atelier | `/app/marches/12` · `/app/marches/12/dossier-de-presentation` |
| Un marché où je suis partenaire | `/app/marches/partenaire/34` (l'identifiant du marché, **jamais le jeton d'invitation**) |
| Partenaires › Mes partenaires · Réseau Adjugo · Contacts | `/app/partenaires` · `/app/partenaires/reseau` · `/app/partenaires/contacts` |
| Réseau Adjugo › Annuaire · Historique | `/app/partenaires/reseau/annuaire` · `…/historique` (réunion : `…/invitations` ouvre Mes marchés, filtre « Où je suis partenaire », § R.2) |
| Mes documents › Mes pièces · Mon savoir-faire | `/app/documents` · `/app/documents/savoir-faire` |
| Mon entreprise › Identité · Ce que je cherche · Mes preuves · Tarifs | `/app/entreprise` · `/app/entreprise/ce-que-je-cherche` · `/app/entreprise/preuves` · `/app/entreprise/tarifs` (réunion, § R.2) |
| Réglages › Collègues · Abonnement · Mon compte · Administration | `/app/reglages/collegues` · `…/abonnement` · `…/compte` · `…/administration` |

Un chemin inconnu, un identifiant douteux (0, signe, lettres, plus de 12 chiffres) ou un jeton ouvrent l'accueil et
l'adresse est remise à `/app` ; Administration demande d'être administrateur de la plateforme ; Projets à venir suit
`PROJETS_A_VENIR`.

**L'application.** Une seule source : la propriété calculée `adresseCourante` (vue, onglet de Trouver des marchés,
marché ouvert, dossier partagé ouvert, onglet du Réseau), observée par `_adresseSynchro`. Aucune fonction d'ouverture
d'écran (`go`, `openAo`, `openShared`, `atlOpen`, `ongletGo`, `rnGo`) n'a changé : un nouvel écran ajoute une entrée à
l'historique du navigateur (`history.pushState`, un seul endroit), la position de défilement de l'écran quitté y est
gardée et rendue au retour ; un clic qui change la vue et l'onglet ne fait qu'une entrée. Le titre de l'onglet du
navigateur suit l'écran (« Mes marchés · Adjugo »). Pas de bibliothèque de routage.

**Précédent / suivant** (`popstate` → `_ouvrirAdresse`) : l'écran de l'adresse se rouvre sans nouvelle entrée, sur
plusieurs niveaux ; de l'atelier, un texte non enregistré est gardé sur l'appareil (`_atlQuitter`, comme « Retour au
marché ») ; un marché revient à sa page sans tout recharger. **Les boutons « Retour »** d'une page de détail (le marché,
l'atelier, un dossier partagé) font comme le bouton du navigateur quand on vient d'un écran de l'application
(`_retourHistorique`, profondeur gardée dans l'entrée) ; ouverts par un lien, ils mènent à la liste, comme avant.

**Liens, favoris, rechargement** : au démarrage, `boot()` ouvre l'écran de l'adresse (`_ouvrirAdresse`) au lieu de
l'accueil. Un marché absent de la liste (créé dans un autre onglet) est demandé à l'API ; l'adresse ne bouge pas en
attendant. Déconnecté, l'écran de connexion s'affiche sur l'adresse demandée et l'ouvre après la connexion. Connexion
Google : l'adresse est gardée le temps de l'aller-retour (`sessionStorage.adjugo_adresse`, seulement un chemin de
l'application, validé par `etatDeAdresse`), puisque le retour arrive sur `/app#gcode=…`.

**Préservé** (tests) : `?verify=`, `?reset=`, `#gcode=`, `?gerror=` et `?inscription` sont lus au montage, avant le
démarrage, sans changement (routage par chemin : le fragment reste au code Google) ; `?shared=<jeton>` (lien
« ouvert dans mon Adjugo » de l'espace partenaire) ouvre le dossier partagé et le jeton quitte l'adresse ; `?payment=`
de Stripe arrive sur `/app`, inchangé. **Tous les liens des courriels déjà envoyés** (`/app`, `/app?verify=…`,
`/app?reset=…`, `/invite/…`) répondent comme avant : aucune redirection n'est nécessaire.

**Courriels nouveaux** : ceux qui parlent d'un marché au chef de file mènent à sa page — part soumise
(`invites.py`, `/app/marches/{id}`), convention validée par tous (`convention.py`), partie envoyée par un partenaire
(`atelier_groupement.py`, `/app/marches/{id}/dossier-de-presentation`, onglet « Qui écrit quoi »), rappel « demandez
vos notes » (`carnet_notes.py`, « Ouvrir ce marché dans Adjugo »). Les liens vers l'espace partenaire (`/invite/…`)
ne changent pas.

**Mesure d'usage** : aucune vue nouvelle, `ECRANS` inchangé ; une adresse ne compte pas une ouverture de plus (la
mesure reste dans les ouvertures d'écran).

### A1.2 Un seul axe d'étapes (décision 7)

**L'axe**, dans l'ordre, sous ses clés stockées (`app.models.ProjectStatus`, `AXE_ETAPES` côté serveur et côté
écran, mêmes libellés : `STATUTS_LIBELLES`) :

| Clé | Libellé | Quand |
|---|---|---|
| `suivi` | À venir | Une carte de Mes marchés avant la publication (décision 11) |
| `nouveau` | Repéré | Le marché est dans Mes marchés (défaut d'une création) |
| `decide` | Décidé | « Préparer seul » ou « Préparer à plusieurs » (étape Décider) |
| `en_cours` | En préparation | Un geste de Préparer, ou le choix « Statut » |
| `depose` | Déposé | « Marquer déposé », ou le choix « Statut » (**ancienne clé `envoye`**) |
| `gagne` · `perdu` | Gagné · Perdu | « Statut », bilan |
| `abandonne` | Abandonné | « Écarter » (étape Décider), réversible (« Remettre ») |

Familles lues par le serveur, définies une fois (`app.models`) : `STATUTS_DEPOSES` (`depose`, `gagne`, `perdu` :
groupement déposé, compteurs du réseau, tableau de bord) et `STATUTS_CLOS` (plus `abandonne` : plus de relance ni de
rappel de date limite). `statut_normalise()` ramène une valeur reçue à sa clé.

**La clé `envoye` migrée** : données (migration, § A1.6), code (`groupement.py` « Marquer déposé » et son annulation,
`agent.py` statistiques, `alerts.py`, `groupement_members.py`, `partner_network.py`, `atelier_groupement.py`), écran
(`app.js`, `app.html` : plus aucun statut « envoye » ; `.st-envoye` reste un style « information » de pastilles et
`.st-depose` le reprend), tests (les 10 tests qui posaient ou attendaient `envoye`), démo (aucun marché de la démo
n'était « envoye »), traductions. **Restent, à dessein** : `InvoiceStatus.envoye` (un devis s'envoie, il ne se dépose
pas) ; la lecture d'une ancienne clé reçue (`ProjectStatus._missing_` : une page ouverte avant la mise en ligne, une
entrée ancienne) ; le journal d'audit, jamais réécrit (entrées chaînées par empreinte). Garde-fou :
`test_la_cle_envoye_n_existe_plus_pour_un_marche` (constantes Python lues par l'ast, textes de l'écran).

**L'API** : `POST /api/projects/` accepte `status` (`suivi` pour une carte avant publication ; absent : `nouveau`) ;
`PUT` ramène la valeur à sa clé (`envoye` → `depose`), refuse une valeur hors de l'axe par un 422 lisible (« Statut
inconnu : choisissez À venir, Repéré, … ») au lieu d'un 500, et ignore `status: null` ; `GET /api/projects/?status=`
lit l'ancienne clé et ne trouve rien pour une clé inconnue (sur Postgres, la comparer au type énuméré échouait).
**Statistiques** : `by_status` vient dans l'ordre de l'axe (l'entonnoir de l'accueil le lit ainsi) ; le taux de
réussite compte les marchés déposés, gagnés ou perdus.

**L'écran** : le choix « Statut » de la page du marché et du tiroir propose les 8 étapes ; Mes marchés a une colonne
par étape (`kanbanColonnes` : « À venir » et « Abandonné » seulement s'il y en a) ; l'entonnoir et les pastilles disent
les mêmes mots. Réunion : Mes marchés est la liste filtrable de A2, un groupe par étape dans l'ordre de l'axe, un
groupe seulement s'il a des marchés ; `kanbanColonnes` est retirée (§ R.1).

**La barre affiche des statuts dérivés.** `barreDuMarche` (fonction pure) donne, pour Lire · Décider · Préparer ·
Déposer, « Terminé », « En cours » ou « À faire », lus dans le statut, le dossier lu et l'étape du groupement ; rien
n'est stocké. Lire est « Terminé » dès que le dossier est lu ; une étape avant l'étape en cours est « Terminé » ; un
marché déposé, gagné ou perdu a ses 4 étapes faites ; un marché écarté n'en a aucune en cours. `etapeDuMarche` suit
l'axe : un marché Décidé ou En préparation est à l'étape Préparer, dossier lu ou non (Lire dit alors « À faire » ;
c'était « Lire » en vague 1, test mis à jour). Chaque statut est lu par un lecteur d'écran (« Lire : Terminé »).

**L'étape Décider décide** (`marche-decision`, en tête de l'étape, jamais en arrière, `statutApresDecision`) :
« Préparer seul » (`user`) et « Préparer à plusieurs » (`handshake`, puis le formulaire « Inviter un partenaire ») font
passer un marché Repéré (ou écarté) à Décidé ; « Écarter » (`archive`) se confirme (« Il passe à l'étape
« Abandonné » : plus de rappel de date limite ni de relance ») et se défait par « Remettre » (`archive-restore`, retour à
Repéré). **Un geste de Préparer** (estimer le prix, préparer les formulaires, inviter un partenaire, ouvrir le dossier
de présentation) fait passer un marché Repéré ou Décidé à En préparation (`statutEnPreparation`, sans message : le
choix « Statut » change sous les yeux). Réunion : inviter passe par la fenêtre unique de A2 (`rinvSend` →
`_marcheEnPreparation`), sur la page du marché comme depuis Mes partenaires (§ R.3). **Un marché « À venir » le reste** jusqu'à sa publication : ni la décision ni
un geste ne le font avancer (on peut y inviter ses partenaires), seul le choix « Statut » le change.

**Une carte avant la publication (décision 11)** : sur chaque fin de contrat de Trouver des marchés › À venir,
« Préparer à plusieurs » (`trouver-preparer-a-venir`, le premier geste de travail) crée la carte dans Mes marchés à
l'étape « À venir » (objet, client, lien de l'avis d'attribution ; aucun montant : celui du contrat qui finit n'est pas
celui du suivant) et ouvre sa page sur « Inviter un partenaire » ; une carte déjà créée pour ce contrat est rouverte,
jamais recréée. Rien ne la crée tant qu'on ne fait que regarder ; « Suivre » (Moteur V1, Veille V1) restera dans
Trouver des marchés.

### A1.3 Barre basse sur téléphone ; la cloche fondue avec « À faire »

**Barre basse** (`menu-bas`, décision 18) : partout où le menu latéral se replie (860 px et moins), 5 boutons —
Accueil (`house`), Trouver (`search`), Mes marchés (`folder-kanban`), Partenaires (`handshake`), Menu (`menu`, qui ouvre
le menu complet : Mes documents, Mon entreprise, Réglages). Le bouton surligné est la rubrique de l'écran
(`aria-current="page"`) ; « Menu » l'est sur un écran qu'il range ou quand il est ouvert (`menuBasMenu`). Pastilles :
celles du menu (Mes marchés : ce qui attend votre action ; Menu : les pièces à renouveler), jamais un total ni zéro.
Le bouton « Menu » de l'en-tête disparaît sur téléphone ; le contenu, les messages et le bandeau des cookies passent
au-dessus de la barre ; la zone de sécurité de l'écran (`safe-area-inset-bottom`) est comptée. 375 px : les 5 mots
tiennent, aucun défilement horizontal.

**La cloche** (`fenetre-notifications`) : deux onglets, « À faire » (ce qui attend votre action) et « Activité » (ce
que font vos partenaires, la liste d'avant). Elle s'ouvre sur « À faire » quand il y a quelque chose à faire ; sa
pastille ne compte que ce qui est à faire (plus l'activité non lue : un point, sans nombre, sur l'onglet « Activité »,
marquée vue quand on l'affiche). Sur téléphone, elle s'ouvre sous la barre du haut, sur toute la largeur.

**« À faire »** : une seule liste (`listeAFaire`, fonction pure), lue par la cloche et par le bloc de l'accueil
(`accueil-a-faire`, après les premiers pas ; absent quand il n'y a rien). Des faits que l'écran connaît déjà, dans cet
ordre : votre accord demandé et une partie du dossier de présentation qui vous attend (marchés où vous êtes partenaire),
une invitation reçue par le réseau, une date limite de vos marchés dans les 7 jours (aujourd'hui, demain, dans N jours ;
marchés ni déposés ni clos), des parts de partenaires encore attendues (« Parts reçues 1 sur 3 », décision 8), les
pièces à renouveler (une ligne). Chaque ligne dit son action et ouvre son écran. Le rail de l'accueil ne redit plus
« N pièces à renouveler » : ce n'est plus qu'une fois, dans « À faire » (`accueil-rail` ne porte plus que l'entonnoir).
Côté serveur, le tableau de bord des groupements ajoute à chaque groupement en cours `n_parts` (parts reçues), un
compte déjà affiché sur la page du marché.

### A1.4 Cloisonnement de la co-traitance

Rien de plus n'est exposé : aucune nouvelle route de données ; l'adresse d'un dossier partagé porte l'identifiant du
marché (déjà connu du partenaire), jamais le jeton ; « À faire » ne lit que des statuts déjà envoyés à l'écran ;
`n_parts` est un compte de l'organisation du chef de file, sans nom ni prix ; le serveur ne lit pas le chemin. Un
membre n'obtient aucun nouvel accès à la matière d'un autre.

### A1.5 Repères de test ajoutés (`tests/zones.py`, `ZONES` du socle)

Ces repères complètent le tableau du § 1.0.3 de `docs/REORGANISATION_V1.md` (mêmes règles) :

| Repère | Zone |
|---|---|
| `menu-bas` | Barre basse sur téléphone (5 boutons), dans `.app`, hors du menu latéral et des vues |
| `fenetre-notifications` | La cloche ouverte : onglets « À faire » et « Activité » (dans `entete`) |
| `accueil-a-faire` | Bloc « À faire » de l'accueil (après `accueil-premiers-pas`, avant `accueil-reseau`) |
| `marche-decision` | La décision de l'étape Décider (en tête de `marche-decider`) |
| `trouver-preparer-a-venir` | « Préparer à plusieurs » d'une fin de contrat (élément répété, dans `trouver-radar`) |

Changé : `accueil-rail` ne porte plus les pièces à renouveler (bloc « À faire »).

### A1.6 Migration `c4axeetapes` (après `b3mesureecrans`)

- **Postgres** : `ALTER TYPE projectstatus RENAME VALUE 'envoye' TO 'depose'` (instantané, aucune ligne réécrite,
  transactionnel) ; `ADD VALUE IF NOT EXISTS 'suivi' BEFORE 'nouveau'` et `'decide' AFTER 'nouveau'`, dans un bloc hors
  transaction. Le type a alors l'ordre de l'axe, le même que celui que crée le modèle. **SQLite** : `UPDATE`. Les devis
  (`invoicestatus`) ne sont pas touchés ; le journal d'audit non plus.
- **Idempotente** : chaque étape lit l'état réel (étiquettes, lignes) ; rejeu, ou révision interrompue entre deux
  étapes, se terminent sans erreur.
- **Retour arrière réel** : `depose` → `envoye`, `suivi` → `nouveau`, `decide` → `en_cours` (les étapes les plus
  proches du code précédent). Sur Postgres, les étiquettes `suivi` et `decide` restent dans le type (Postgres ne retire
  pas une valeur) : aucune ligne ne les porte, le code précédent les ignore, une remontée ne les ajoute pas deux fois.
- **Base SQLite déjà créée** (dev, démo locale) : `ensure_sqlite_statuts` (`app/core/dbsync.py`) fait la même
  normalisation au démarrage.
- **Testée sur SQLite** (`test_migration_axe_etapes_aller_retour_idempotente`) et **sur Postgres 16.2**
  (`run_pg_axe.py`, 26 contrôles verts) : base neuve (tête unique, ordre de l'axe, identique au modèle) ; base montée par
  le **code de production `fab9d9a`** (git archive, tête `b3mesureecrans`) avec ses données — 7 marchés dont 2
  « envoye », un devis « envoye », une entrée « déposé » au journal — puis code nouveau : une révision, `envoye` →
  `depose` sur les seuls marchés, mêmes identifiants, chaque table garde ses lignes, devis et journal intacts, le code
  nouveau lit et écrit les 8 étapes ; rejeu et rejeu forcé (stamp puis upgrade) sans effet ; révision interrompue
  (renommage fait, version non posée) qui se termine ; retour arrière, après lequel **le code de production relit tous
  les marchés** ; remontée ; l'API du code nouveau sur Postgres (création « suivi », `envoye` reçu → `depose`, 422,
  filtre, statistiques). **Échecs comparés** (`compare_pg.py`) : 10 fichiers de tests touchés par l'axe, sur Postgres,
  avec le code de production puis le code nouveau : 294 réussis et le même échec des deux côtés
  (`test_cron_borne_et_jamais_de_depublication_sur_erreur`, propre à Postgres, déjà en production) ; le fichier de la
  vague 2a passe en entier sur Postgres (28 sur 28).
- **Déploiement** (relecture : étendue mesurée, § L.4) : la migration passe avant le démarrage (`entrypoint.sh`). Le
  code de production précédent ne sait pas lire `depose` : tant qu'il sert sur une base migrée, toute organisation qui
  a un marché déposé voit **toutes ses listes** répondre en erreur (Mes marchés, statistiques, tableau de bord des
  groupements, groupements, la page d'un marché déposé et le changement de son étape), et ses partenaires d'autres
  organisations aussi (« Où je suis partenaire », `/api/shared`, et l'historique du réseau). Si la nouvelle instance ne
  passe pas son contrôle de santé, Railway garde l'ancienne sur la base migrée : la panne dure jusqu'au retour arrière.
  Déployer à une heure creuse, suivre le passage au vert de la nouvelle instance, et si elle ne démarre pas, **lancer
  tout de suite `alembic downgrade b3mesureecrans`** ; c'est aussi la première commande de tout retour au code
  précédent.
- À refaire au moment de la mise en ligne depuis l'état réel de la production, comme pour chaque migration.

### A1.7 Vérifications

- Suite complète verte (SQLite, 2 116 tests) ; `scripts/sri_update.py --check`, `node --check app/static/app.js` ; gabarit de
  `app.html` compilé par Vue sans erreur ni avertissement (`test_gabarit_compile_par_le_vue_du_depot`) ;
  `scripts/i18n_ajouter.py --check` (469 → 500 clés : les étapes de l'axe, la cloche, « À faire », la décision, la barre
  basse, la carte « À venir ») ; garde des mots bannis (`tests/textes_visibles.py`) verte.
- Postgres 16.2 : `run_pg_axe.py` 26 contrôles sur 26 ; `compare_pg.py` : échecs identiques au code de production.
- **Navigateur réel** (serveur local, base jetable, démo par **lien privé** avec une clé jetable, `DEMO_PUBLIC=0`, réseau
  sortant coupé, aucune IA) : Accueil (bloc « À faire », entonnoir dans l'ordre de l'axe), Mes marchés → Kerhel →
  précédent, précédent, suivant, suivant, « Retour » (adresses et écrans justes à chaque pas, titres de l'onglet) ;
  rechargement de `/app/marches/2` (Kerhel rouvert : « Lire Terminé · Décider Terminé · Préparer Terminé · Déposer En
  cours ») ; Infogérance SI (Repéré) : « Préparer seul » → Décidé, barre « Préparer En cours » ; « Écarter » (fenêtre de
  confirmation) → « Marché écarté », « Remettre » → Repéré ; la cloche (« À faire », « Activité » et son point) ;
  `/app/partenaires/reseau/invitations` (onglet du Réseau), Annuaire, précédent ; `/app/reglages/compte` ;
  `/app/marches/1/dossier-de-presentation` (atelier rouvert), « Retour au marché », précédent ; `/app/trouver/a-venir`,
  « Chercher les fins de contrat », « Préparer à plusieurs » → carte « À venir » créée, sa page sur « Inviter un
  partenaire », précédent (la recherche est toujours là), second clic (la même carte rouverte) ; colonnes de Mes marchés
  (« À venir » apparaît) ; déconnecté, `/app/marches/2?inscription` → « Créons votre compte » sur la même adresse.
  375 px, clair et sombre : barre basse (les 5 mots entiers), « Menu » ouvre le menu, navigation et précédent,
  page du marché (barre et statuts sur une ligne), cloche pleine largeur, bandeau des cookies au-dessus de la barre ;
  aucun défilement horizontal. Console sans erreur.

### A1.8 Laissé, avec sa raison

- **D10 « partie (lot n) »** : hors de ce chantier (A1 = adresses et étapes) ; fait par A3.
- **Mes marchés en liste filtrable, une seule fenêtre d'invitation, « Qui me complète ? » unique, « Prêt à déposer »
  pour l'entreprise seule, Mon entreprise en onglets, Mes documents** : autres chantiers de la vague 2a (A2, A3),
  réunis au § R.
- **Un menu latéral sans les 4 rubriques de la barre basse sur téléphone** : le menu complet reste derrière « Menu »
  (aucune entrée qui apparaît ou disparaît selon l'écran).
- **Passage automatique « À venir » → « Repéré » à la publication** : il demande de relier une fin de contrat à son
  nouvel avis (Moteur, Veille) ; d'ici là, le choix « Statut ».
- **Le stepper de 5 étapes côté partenaire** (`invite.html`, dossier partagé) : vague 2b.

---

## A2. Mes marchés et invitations

Ce chantier fait trois choses, sans migration ni nouvelle route :

1. **Mes marchés en liste filtrable** (Tous · Je pilote · Où je suis partenaire · À plusieurs), groupée par statut. Les
   vues « shared » et « consortiums » et l'onglet « Invitations reçues » du Réseau y fondent, sans rien montrer de plus
   que ce que chaque vue montrait. « Devis et factures » et « Bilan » sont des onglets.
2. **Une seule fenêtre d'invitation**, trois cas : membre du réseau (Adjugo envoie, l'adresse reste masquée), partenaire
   connu avec son email (Adjugo envoie), entreprise du registre (la PME copie le lien). **Un seul composant « Qui me
   complète ? »**.
3. **Une seule liste « Prêt à déposer »**, avec un calcul pour l'entreprise seule (jamais un faux manque de groupement),
   et **un seul « Figer l'offre »**.

Tests : `tests/test_reorganisation_v2a_marches_invitations.py` (25 tests) ; les tests de la vague 1 qui décrivaient
l'ancien rangement sont mis à jour (§ A2.8).

### A2.1 Mes marchés : une liste filtrable

**Ce qu'on voit** (rubrique Mes marchés, onglet « Marchés », vue `pipeline`) :

- En haut, quatre filtres (`mes-marches-filtres`, boutons `aria-pressed`) : **Tous**, **Je pilote**, **Où je suis
  partenaire**, **À plusieurs**. Seul « Où je suis partenaire » porte une pastille : ce qui attend votre action
  (`mmActions()` : invitations du réseau à traiter, convention à valider, parties du dossier à rédiger), jamais un
  total. À 375 px, les filtres passent sur 2 colonnes.
- Sous « À plusieurs », la ligne de l'ancienne vue des groupements (« 3 en cours · 4 partenaires · 2 parts reçues »),
  avec sa bulle (i).
- **Invitations à traiter** (`mes-marches-invitations`, dans Tous et Où je suis partenaire) : les invitations reçues par
  le réseau Adjugo, avec les mêmes boutons qu'avant (Accepter depuis mon compte, Voir l'invitation, Décliner ; réservées
  au compte à qui Adjugo les a envoyées). Ce bloc remplace l'onglet « Invitations reçues » du Réseau Adjugo.
- **La liste**, groupée par statut dans l'ordre des statuts (`statuses2` : Nouveau, En cours, Déposé, Gagné, Perdu,
  Abandonné), chaque groupe avec son nombre de marchés. Réunion : l'ordre est celui de l'axe de A1 (À venir, Repéré,
  Décidé, En préparation, Déposé, Gagné, Perdu, Abandonné ; § R.1). Deux sortes de cartes :
  - un marché que je pilote (`kcard`, la carte de l'ancien tableau) ; s'il a au moins un partenaire invité, la ligne
    « parts reçues N sur M · pièces · limite » et « Compte-rendu » (`mes-marches-plusieurs`), qui déplie le
    compte-rendu de l'ancienne vue « À plusieurs » : lots couverts, partenaires et pièces, manques, « Exporter le
    dossier commun », « Aperçu du dossier », « Compte-rendu interne (PDF) » ;
  - un marché où une autre entreprise m'a invité (`mes-marches-partenaire`) : chef de file, mon rôle, date limite,
    « Convention à valider », mes parties du dossier de présentation, l'état de ma part. Statuts seulement.
- États vides : un par filtre, qui dit quoi faire.

**Filtres** (fonction pure `listeMesMarches`, en tête de `app.js`, testée sous Node) :

| Filtre | Ce qu'il montre |
|---|---|
| Tous | Mes marchés et ceux où je suis partenaire, et les invitations à traiter |
| Je pilote | Mes marchés (ceux de mon organisation) |
| Où je suis partenaire | Les marchés d'autres entreprises que j'ai acceptés, et les invitations à traiter |
| À plusieurs | Mes marchés avec au moins une invitation active (comme l'ancienne vue des groupements), et ceux où je suis partenaire |

Un marché où je suis partenaire n'a pas de statut à lui (je ne vois pas celui du chef de file) : il est « Déposé »
quand le groupement est à l'état « déposé » (ce que son espace lui montrait déjà), « En cours » sinon
(`statutPartenaire`). Un filtre inconnu vaut « Tous ».

**Rien de plus qu'avant** (cloisonnement de la co-traitance intact). La liste lit les mêmes réponses, sans changement :
`GET /api/projects/` (mes marchés), `GET /api/shared` (marchés où je suis partenaire), `GET /api/consortiums` (mes
groupements), `GET /api/reseau/invitations` (invitations reçues). Aucune route n'est ajoutée ni élargie. Le gabarit ne
lit, sur une carte de partenaire, que les champs que lisait « Où je suis partenaire » (`token`, `project`,
`mandataire`, `role`, `deadline`, `groupement`, `redaction`, `contribution_status`), sur une carte « À plusieurs » que
ceux de « Mes groupements » (`submitted`, `partners`, `pieces`, `deadline`), sur une invitation que ceux de l'ancien
onglet. Vérifié par `test_la_liste_ne_lit_que_ce_que_lisaient_les_anciennes_vues` et, de bout en bout, par
`test_le_partenaire_et_le_chef_de_file_ne_recoivent_rien_de_plus` (mêmes champs qu'avant ; un partenaire n'atteint ni
le dépôt, ni « Qui me complète ? », ni les invitations, ni le groupement du chef de file ; une troisième entreprise ne
voit rien).

**Les anciennes vues** : `go("shared")` ouvre la liste sur « Où je suis partenaire », `go("consortiums")` sur « À
plusieurs » (accueil « Préparer à plusieurs », retour d'un dossier partagé, anciens appels). Entrer dans la liste par le
menu la remet sur « Tous » ; revenir d'un marché garde le filtre. `openReseau("recues")` et `rnGo("recues")` mènent au
filtre « Où je suis partenaire ». Les vues `shared` et `consortiums` restent dans `RUBRIQUES` (rubrique surlignée).

**Mesure d'usage** : `go("pipeline")` compte « pipeline » ; choisir « Où je suis partenaire » ou « À plusieurs »
compte aussi l'ancien écran (`shared`, `consortiums`), pour comparer avant et après. `bilan` entre dans `ECRANS`
(`app/services/mesure_usage.py`).

**Onglets de Mes marchés** : Marchés · Devis et factures · **Bilan** (`chart-column`). La bulle de « Marchés » dit,
pendant la transition, que « Où je suis partenaire » et « À plusieurs » sont des filtres ; celle du Bilan, que « Où vous
gagnez / perdez » était sur l'accueil.

**Bilan** (vue `bilan`) : « Où vous gagnez / perdez » (`bilan-gagne-perdu`, l'ancien bloc de l'accueil, décision 8
tenue : « N sur M ») et le carnet de notes « Où vous perdez des points » (`bilan-carnet`, mode « tableau »). L'accueil
garde une ligne (`accueil-bilan` : « Bilan · 3 marchés terminés · 2 gagnés sur 3 », « Voir le bilan ») et, du carnet,
les seuls rappels « Demandez vos notes » (`accueil-carnet`, nouveau mode « rappels » de `carnet-notes.js`, rien quand
il n'y en a pas).

**Mes partenaires** : chaque fiche a « Inviter sur un marché » (la fenêtre unique, cas « partenaire connu », qui demande
le marché).

### A2.2 Une seule fenêtre d'invitation

Le formulaire d'invitation de la page du marché (`marche-inviter-formulaire`) et son lien à copier disparaissent :
« Inviter un partenaire » (en tête de chaque marché, décision 0) ouvre la fenêtre `fenetre-invitation`, qui gère trois
cas. Ouverte sans entreprise, elle demande d'abord « qui invitez-vous ? ».

| Cas | Qui envoie | Route (inchangée) | Ce que voit la PME |
|---|---|---|---|
| Une entreprise du **réseau Adjugo** | Adjugo | `POST /api/projects/{id}/reseau/invitations` | « Adjugo envoie l'invitation : vous verrez l'adresse du partenaire quand il aura accepté. » Aucune adresse (le serveur ne la renvoie pas), aucun lien |
| Un **partenaire connu** (Mes partenaires ou une autre entreprise), avec son email | Adjugo, à l'email que la PME donne ; sans email, personne | `POST /api/projects/{id}/invites` | « Invitation envoyée par Adjugo à … » et le lien (au cas où) ; sans email, le lien à copier |
| Une entreprise du **registre officiel** | Personne : la PME copie le lien | `POST /api/projects/{id}/reseau/invitations-sirene` | Le lien à copier ; identité relue par le serveur dans le registre |

- Rôle (partenaire du groupement ou sous-traitant), part proposée (réseau, registre), téléchargement des pièces,
  « apporter sa part » et durée du lien (partenaire connu), marché à choisir (hors de la page d'un marché).
- Erreurs gérées : « déjà invité » (voir les invitations du marché), « sur le réseau » (inviter via le réseau),
  « profil non publié » (publier mon profil), registre indisponible (« Inviter sans passer par le registre » : le même
  nom, comme un partenaire connu). Contrôles avant envoi : nom de l'entreprise, email bien formé, SIRET à 14 chiffres.
- Toutes les entrées y mènent : en tête du marché (`aoInviter`), « Inviter {nom} » de la composition et de la
  simulation, « Membres et sous-traitants », « Convention et accords » (membre hors ligne), les cartes de « Qui me
  complète ? », la fiche d'un partenaire du réseau, Mes partenaires. `aoGrpInvite(m)` choisit le cas : profil du
  réseau connu → réseau ; entreprise du registre (SIRET) absente de Mes partenaires → registre ; sinon partenaire connu,
  avec l'email de la fiche Mes partenaires (rapprochée par identifiant, SIRET, puis nom) et le candidat déjà ajouté au
  marché (`link_id`), qui porte l'invitation comme avant.
- **Cloisonnement, quotas, anti-spam** : les trois routes sont celles d'avant, avec leurs contrôles (`invites.py` et
  `reseau.py` ne changent pas sur ce point) : propriété du marché, refus de la démo, expéditeur confirmé pour un
  email, plafond quotidien de l'organisation (`DAILY_INVITE_CAP`), plafond de sollicitations d'un profil du réseau
  (`NETWORK_INVITES_PER_PROFILE_DAY`), verrou « déjà invité », adresse réseau jamais montrée. Le champ email n'existe que
  dans le cas « partenaire connu » : c'est l'adresse que la PME saisit (ou celle de sa propre fiche Mes partenaires) ;
  le gabarit ne lit jamais une adresse renvoyée par le serveur (`test_invitation_reseau_adresse_jamais_affichee`).
- Accessibilité : `role="dialog"`, `aria-modal`, titre et description reliés, focus sur le premier champ, Échap ferme,
  le focus revient au bouton d'origine ; vrais boutons, libellés visibles.

### A2.3 Un seul « Qui me complète ? »

Le composant (`marche-qui-me-complete`, étape Décider) est le seul endroit de la page où l'on cherche une entreprise.
Partie par partie, trois réservoirs dans le même ordre, chacun avec son compte :

1. **Réseau Adjugo** (`complete-reseau`) : les profils classés (un rang et ses raisons, jamais une note), comme avant ;
   pour un compte non publié, l'invitation à publier (rien de plus : pas d'oracle d'appartenance) ;
2. **Mes partenaires** (`complete-mes-partenaires`) : **nouveau**, les fiches de l'annuaire de l'organisation dont le
   métier correspond à la partie (mêmes mots-clés que les lots du dossier, `own_trades`) ; « Simuler le groupement »
   (le serveur relit la fiche) et « Inviter » (cas « partenaire connu », avec l'email de la fiche) ;
3. **Entreprises de la zone** (`complete-zone`) : le registre officiel, comme avant (« Inviter par lien »).

Puis **« Chercher une entreprise de la zone »** (`complete-recherche`) : la recherche libre par métier et département
qui était dans « Membres et sous-traitants » (mêmes résultats : identité vérifiée datée, RGE, Qualiopi, marchés gagnés
DECP, alertes), avec « Inviter par lien » (le SIRET, identité relue par le serveur) et « Ajouter un sous-traitant
(DC4) », le seul ajout direct. « Membres et sous-traitants » garde son bouton « Chercher une entreprise », qui mène à
cette recherche. « Chercher autrement » sur une partie la pré-remplit (métier et département de la partie). Le composant
s'affiche même sans analyse (la recherche dans la zone marche sans dossier).

**Serveur** (`GET /api/projects/{id}/partner-matches`, `reseau.py`) : chaque partie reçoit `mes_partenaires` (au plus 5
fiches : `cotraitant_id`, `name`, `siret`, `siren`, `city`, `departement`, `specialites`, `email`, `reseau`,
`deja_invite`) et `n_mes_partenaires`. Seulement les fiches de l'organisation (`member_ids`) : jamais celles d'une autre
entreprise, rien du réseau. L'email est celui que l'organisation a saisi sur sa fiche (l'annuaire ne copie jamais
l'adresse d'un profil du réseau). Une entreprise déjà montrée par le réseau pour la partie n'est pas répétée (on
l'invite par le réseau, adresse masquée) ; le repli du registre ne répète pas une fiche déjà montrée.
`test_qui_me_complete_propose_mon_annuaire_et_jamais_celui_d_un_autre`,
`test_une_entreprise_du_reseau_n_est_pas_repetee_dans_mes_partenaires`.

Le 4e réservoir de l'étude (« Déjà retenus sur des marchés publics ») viendra avec le moteur (V3) : un réservoir vide
annoncerait une fonction qui n'est pas en ligne. « Découvrir des partenaires réels » (Partenaires › Mes partenaires)
reste : c'est l'ajout d'une entreprise à l'annuaire, hors d'un marché. « Qui l'a ? » (simulation de « Répondre à
plusieurs ? ») reste aussi : c'est le choix des membres d'une simulation, ses « Inviter » passent par la fenêtre unique.

### A2.4 Une seule liste « Prêt à déposer »

**Pour tous les marchés.** La carte « Prêt à déposer » (`marche-pret-a-deposer`, étape Déposer) n'est plus réservée au
groupement ; la liste à cocher « Avant de déposer sur la plateforme du client » (`marche-avant-depot`) y entre. Le
serveur choisit le calcul (`GET /api/projects/{id}/groupement/depot`, route inchangée) :

- **à plusieurs** (au moins une invitation active, ou une convention) : les 4 contrôles d'avant, inchangés (parts,
  attestations de tous les membres, convention validée, formulaires préparés après elle) ;
- **seul** (`depot_readiness_seul`, `groupement_members.py`) : ce qu'Adjugo vérifie lui-même, rien qui suppose un
  groupement.

| Contrôle (entreprise seule) | Fait quand | L'action sur la page |
|---|---|---|
| Votre prix estimé | Une estimation est enregistrée sur le marché (`estimate.total_ht`) | « Estimer mon prix » |
| Dossier de présentation prêt, sans passage à compléter | La pièce « Dossier de présentation » de la liste des pièces est « disponible » ; contrôle absent si la liste ne l'exige pas | « Ouvrir l'atelier » |
| Formulaires officiels préparés | DC1, DC2 et acte d'engagement (ATTRI1) préparés par Adjugo ; le DUME hors de France | « Préparer mes documents » |
| Pièces demandées réunies | Chaque pièce exigée de la carte « Pièces à fournir » (formulaires et dossier de présentation à part) est présente et pas expirée — la même liste, une seule vérité (`checklist_du_marche`) | « Voir les pièces » |
| Vos attestations valides à la date limite | Aucune attestation de votre coffre-fort n'expire avant la date limite (une attestation absente est dans « Pièces ») | « Mes pièces » |

Même forme de réponse que pour un groupement (`checks`, `libelles`, `pret`, `n_ok`, `n_total`, `pct`, `manques`,
`avertissements`), plus deux champs, pour les deux calculs : `pour` (« seul » ou « groupement ») et
`manques_par_controle` (chaque manque sous son contrôle ; l'écran ne devine plus par le début de la phrase). La liste
s'allonge quand le dossier du marché est lu (ses pièces exigées entrent dans « Pièces »). Avertissements : date limite
inconnue ou dépassée.

- **Formulaires horodatés pour l'entreprise seule** : « Préparer mes documents » horodatait DC1, DC2 et ATTRI1
  seulement pour un groupement à convention ; il les horodate toujours (et le DUME), `redaction.build_dossier`. Pour un
  groupement, rien ne change : le contrôle compare toujours l'horodatage à la génération de la convention.
- **À vérifier vous-même** : ce qu'Adjugo ne peut pas vérifier, dans la même carte (2 cases, gardées sur cet appareil,
  par marché) : relire et signer les formulaires si le règlement l'exige ; vérifier la TVA et les montants de l'acte
  d'engagement. Les deux autres points de l'ancienne liste sont devenus des contrôles (les pièces) et la phrase du dépôt
  (« Déposez le dossier avant la date limite… »). L'ancien enregistrement à 4 cases garde ses 2 premières.
- **« Marquer déposé »** : pour tous (`POST /groupement/deposer`, inchangé : avertir, pas bloquer ; 409 `pas_pret` avec
  la liste de l'entreprise seule, puis « Marquer déposé quand même »). Les phrases qui parlent des partenaires (journal,
  relances) ne s'affichent que pour un groupement.
- `test_pret_a_deposer_d_une_entreprise_seule_sans_faux_manque_de_groupement`,
  `test_pret_a_deposer_d_un_groupement_inchange`,
  `test_le_dossier_prepare_horodate_les_formulaires_aussi_pour_une_entreprise_seule`.

### A2.5 Un seul « Figer l'offre »

« Figer l'offre » ne reste que dans « Convention et accords » (« Figer l'offre et générer la convention »). L'offre
commune (`marche-offre-commune`) montre le total prévisionnel et mène à la convention (« Aller à « Convention et
accords » ») ; « Défiger » reste à côté du total figé. Le champ « Votre part » de l'ancien repli disparaît (la convention
porte la part du chef de file). La route `POST /api/projects/{id}/offre/figer` reste (API, tests), sans bouton.

### A2.6 Textes et traductions

- « Où je suis partenaire » est un **filtre** de Mes marchés : « dans Mes marchés, filtre « Où je suis partenaire » »
  (refus et message de l'espace privé du partenaire, `atelier_groupement.py` ; écran de rédaction du partenaire,
  `redaction-partenaire.js`, 3 messages ; « Invitation acceptée… »). Les invitations reçues se traitent là : message de
  `reseau.py` quand l'email n'est pas parti, bulle de l'espace partenaire (`invite.html`).
- La note « Ce qui a changé » de l'accueil dit le rangement d'aujourd'hui (filtres, onglets Devis et factures et Bilan).
- Vocabulaire : « partie » dans les textes nouveaux de « Qui me complète ? » (décision 10) ; aucun mot banni, zéro
  émoji ; explications en bulle (i).
- Décision 16 : 83 libellés traduits (469 → 552 clés, `scripts/i18n_ajouter.py --check`), vérifiés par
  `test_traductions_des_libelles_de_mes_marches_et_des_invitations` et le test de cohérence de la vague 1 (« marché » →
  aanbesteding / licitación, « à plusieurs » → samen / agrupación).

### A2.7 Les repères (`data-test`)

| Repère | Changement |
|---|---|
| `vue-shared`, `vue-consortiums`, `reseau-recues` | **Retirés** : fondus dans la liste de Mes marchés |
| `mes-marches-filtres`, `mes-marches-invitations`, `mes-marches-liste`, `mes-marches-plusieurs`, `mes-marches-partenaire` | **Ajoutés** (dans `vue-pipeline`) : les filtres, les invitations à traiter, un groupe, la ligne « À plusieurs » d'une carte, une carte de partenaire |
| `vue-bilan`, `bilan-gagne-perdu`, `bilan-carnet` | **Ajoutés** : Mes marchés › Bilan ; `bilan-gagne-perdu` est l'ancien contenu de `accueil-bilan` |
| `accueil-bilan` | Garde son nom : la ligne de l'accueil qui mène au bilan |
| `accueil-carnet` | Garde son nom : les rappels « Demandez vos notes » (mode « rappels ») |
| `marche-inviter-formulaire` | **Retiré** : la fenêtre `fenetre-invitation` |
| `marche-avant-depot` | **Retiré** : entré dans `marche-pret-a-deposer` |
| `complete-reseau`, `complete-mes-partenaires`, `complete-zone`, `complete-recherche` | **Ajoutés** (dans `marche-qui-me-complete`) : les trois réservoirs, la recherche dans la zone |

Nouveau préfixe : `mes-marches-` (la liste de Mes marchés ; `marche-` reste la page d'un marché), `bilan-` (Mes marchés
› Bilan), `complete-` (dans « Qui me complète ? »). `ZONES` (`tests/test_reorganisation_v1_socle.py`) suit.

### A2.8 Tests

Nouveau : `tests/test_reorganisation_v2a_marches_invitations.py` (liste et filtres sous Node, anciennes vues et mesure,
champs lus, cloisonnement de bout en bout, bilan, fenêtre unique et son routage sous Node, partenaire connu par email ou
lien, réservoirs, annuaire de l'organisation seul, réseau non répété, « Prêt à déposer » seul et à plusieurs, formulaires
horodatés, contrôles et leur action sous Node, ancien format de la liste à cocher, un seul « Figer », textes, mots
bannis et émojis, 375 px, démonstration, traductions).

Mis à jour, chacun avec sa raison en commentaire : `test_reorganisation_v1_socle.py` (zones, `RENOMMES` :
« Entreprises du registre officiel » → « Entreprises de la zone »), `test_reorganisation_v1_menu.py` (onglets de Mes
marchés, filtres, pastille sur « Marchés », bulles, chargements de la liste), `test_reorganisation_v1_marche.py` (la
fenêtre au lieu du formulaire, « Prêt à déposer » pour tous), `test_reorganisation_v1_relecture.py` (« filtre », chemins
des invitations, bilan dans Mes marchés), `test_reorganisation_v1_reunion.py` (« N sur M » de la carte « À
plusieurs »), `test_reseau_ecrans.py` et `test_reseau_ecrans_v34.py` (invitations reçues dans Mes marchés, le champ email
du seul cas « partenaire connu », la recherche dans la zone), `test_correctifs_urgents.py` (le candidat porté par la
fenêtre, l'entreprise du registre invitée par son SIRET), `test_redaction_vague1_relecture.py` (avertissements de
l'export du dossier commun, dans la liste).

### A2.9 Migrations

Aucune : ni table, ni colonne, ni donnée modifiée ; la tête reste `b3mesureecrans`. Le code nouveau tourne sur une base
montée par le code de production (Postgres, § A2.10).

### A2.10 Vérifications

- **Suite complète** verte (dont les 25 tests du nouveau fichier) ; SRI à jour (`scripts/sri_update.py --check`) ;
  `node --check` des scripts servis modifiés (`app.js`, `carnet-notes.js`, `redaction-partenaire.js`, `i18n.js`) ;
  gabarit de `app.html` compilé par le Vue du dépôt (`test_gabarit_compile_par_le_vue_du_depot`) ;
  `scripts/i18n_ajouter.py --check` (552 clés).
- **Postgres 16 depuis l'état exact de la production** (script de la session `scratchpad/a2/run_a2_pg.py`) : production
  `fab9d9a` montée par son propre code (tête `b3mesureecrans`), données créées par ce code (chef de file et partenaire,
  annuaire, un marché seul avec prix et formulaires, un autre sans, un marché à plusieurs, un marché au statut
  « envoye » avec son partenaire) ; code nouveau : aucune révision appliquée, aucune donnée touchée ; « Prêt à déposer »
  seul (prix et formulaires faits par la production lus, aucun manque de groupement), à plusieurs (les 4 contrôles),
  marché « envoye » déposé ; Mes marchés : mêmes champs qu'avec la production ; « Qui me complète ? » (mon annuaire,
  « déjà invité ») ; « Préparer mes documents » horodate les formulaires d'un marché seul ; « Marquer déposé » seul puis
  retrait ; cloisonnement (le partenaire n'atteint ni le dépôt ni « Qui me complète ? » du chef de file) ; code de
  production relancé sur la base (lectures et écriture 200) ; schéma identique à une base neuve ; 577 tests (23 fichiers,
  dont le nouveau) rejoués sur la base montée : tous verts.
- **Navigateur réel** (serveur local, base jetable, démonstration par lien privé avec une clé jetable de 48 caractères,
  `DEMO_PUBLIC=0`, réseau sortant coupé, aucune IA) : accueil (« Bilan · 3 marchés terminés · 2 gagnés sur 3 »), Mes
  marchés (Tous, groupé Nouveau · En cours · Gagné · Perdu ; compte-rendu de Kerhel déplié sur toute la largeur ; « À
  plusieurs » : Kerhel et sa ligne « 1 en cours · 1 partenaire · 1 part reçue » ; « Où je suis partenaire » : l'état
  vide), Bilan (« Où vous gagnez / perdez », « Où vous perdez des points »), Réfection toiture seule (« Avant de
  déposer : 3 contrôles sur 5 » : prix, dossier et formulaires faits, « Planning prévisionnel : à ajouter dans Mes
  documents », l'attestation URSSAF qui expire avant la date limite, « À vérifier vous-même : 0 sur 2 », « Voir les
  pièces » mène à la carte), Kerhel (« 3 contrôles sur 4 », inchangé ; « Qui me complète ? » : Réseau Adjugo « Visibles
  quand votre profil partenaire est publié », Mes partenaires 1, Breizh Désamiantage « Déjà invité »), la fenêtre
  « Inviter un partenaire » (« qui invitez-vous ? », partenaire connu pris dans Mes partenaires avec son email, le refus
  de la démonstration affiché et amené à l'écran, SIRET trop court refusé), Mes partenaires › « Inviter sur un marché »
  (le choix du marché) ; 1 280 px en sombre et en clair, 375 px (aucun débordement horizontal : Mes marchés, la page de
  Kerhel, la fenêtre ; filtres sur 2 colonnes). Le bandeau du stockage local n'a pas été fermé.

### A2.11 Pour la réunion des chantiers

- **Fait à la réunion (§ R)** pour chacun des points ci-dessous.
- **Axe d'étapes (D7)** : la liste se groupe par `statuses2` et `statusLabel` ; un marché où je suis partenaire prend
  la clé `envoye` quand le groupement est déposé (`statutPartenaire`, seul endroit nouveau qui écrit cette clé). Quand
  la clé migre et que la barre affiche des statuts dérivés, ces deux fonctions suivent ; `listeMesMarches` prend l'ordre
  qu'on lui donne.
- **Adresse par écran** : le filtre de la liste est `mmFiltre` (pas dans l'adresse) ; `go("shared")` et
  `go("consortiums")` restent les raccourcis vers les filtres (liens et retours).
- **« partie (lot n) » (D10)** : `pmLotTitle` et `pmLotPart` disent encore « Lot N — … » (titre de chaque partie de « Qui
  me complète ? », part proposée) ; les textes nouveaux disent déjà « partie ».
- **Barre basse, cloche « À faire »** : non touchées.

### A2.12 Pour Eliot

- Rien à régler : pas de variable, pas de migration. Le courriel aux 7 PME de la vague 1 reste juste ; s'il part après
  cette vague, remplacer « (onglet « Où je suis partenaire », anciennement « Partagé avec moi »), vos marchés à plusieurs
  (onglet « À plusieurs »…) » par « les filtres « Où je suis partenaire » et « À plusieurs » de la liste », et ajouter
  « le Bilan (anciennement sur l'accueil) ».

---

## A3. Entreprise, documents, confirmations, vocabulaire

Tests : `tests/test_reorganisation_v2a_entreprise.py` (24 tests ; sans navigateur ni réseau, fonctions pures et
fenêtre de confirmation exécutées sous Node). Migration : `c4montantseul` (après `b3mesureecrans`).

### A3.1 Mon entreprise en 4 onglets

| # | Onglet | Vue | Icône | Ce qu'on y trouve |
|---|---|---|---|---|
| 1 | Identité | `company` | `building-2` | Pays, registre officiel, identité, chiffre d'affaires, collaborateurs ; un renvoi « Vos prix de journée et vos frais de déplacement se renseignent dans l'onglet « Tarifs » » |
| 2 | Ce que je cherche | `criteria` | `sliders-horizontal` | Mes métiers (spécialités, codes CPV, qualifications, mots exclus) · Ma zone · Montants (fourchette, montant que je porte seul) · Seuils de recommandation |
| 3 | Mes preuves | `preuves` | `award` | Inchangé (rédaction, vague 3) |
| 4 | Tarifs | `tarifs` (nouvelle vue) | `calculator` | Mes prix de journée, frais de déplacement ; son propre « Enregistrer » |

- **Une seule source** : `RUBRIQUES` (`app.js`) ; la rubrique a 4 vues, ses onglets s'affichent par le composant
  commun `onglets-rubrique`. Ordre de l'étude (§ 5.3) : Identité · Ce que je cherche · Mes preuves · Tarifs.
- **« Mes critères » devient « Ce que je cherche »** : titre de la vue, onglet, premier pas de l'accueil (« Dites ce
  que vous cherchez : vos métiers ou votre zone », ce que le jalon vérifie), bulle « Anciennement « Mes critères ». »
  (comptes d'avant la vague 1 seulement, comme les autres anciens noms), note « Ce qui a changé », fenêtre d'avant
  une analyse (§ A3.4), carte de recherche (« Dites ce que vous cherchez pour un score adapté »), messages du serveur
  (« … dans Mon entreprise, onglet « Ce que je cherche » », `dce_scoring.py`, `sourcing/scoring.py`).
- **Tarifs** : la même fiche de l'entreprise (`PUT /api/company/`), sortie de l'onglet « Identité » qui ne
  faisait qu'un formulaire. Chaque onglet a son bouton ; `saveCompany('tarifs')` dit « Tarifs enregistrés », et si
  la dénomination manque : « Renseignez d'abord le nom de votre entreprise, dans l'onglet « Identité » ». La bulle
  dit à quoi servent les tarifs : « Estimer mon prix » sur la page d'un marché (`app/routers/chiffrage.py`).
  Ancien emplacement dit en bulle : « Vos tarifs étaient dans l'onglet « Identité ». ». Mesure d'usage : `tarifs`
  ajouté à `ECRANS` (`app/services/mesure_usage.py`), lu « Mon entreprise › Tarifs » dans Administration.
- **Ce que je cherche** : les blocs existants sont rangés dans l'ordre de la question (quoi, où, combien), les
  libellés disent ce qu'ils sont (« Marchés à partir de (€ HT) », « Jusqu'à (€ HT) » au lieu de « Budget min / max »),
  chaque champ a son libellé lié (`for` / `id`). La bulle « Montants » dit ce que fait la fourchette, vérifié dans le
  code (`sourcing/scoring.py`, `dce_scoring.py`) : elle entre dans le classement des marchés trouvés et dans
  l'analyse, et ne masque aucun marché.
- **Repères** : `vue-tarifs` ajouté (`ZONES` de `tests/test_reorganisation_v1_socle.py` et `REORGANISATION_V1.md`,
  § 1.0.3).
- **Laissé, avec sa raison** : les « Collaborateurs » restent dans « Identité », avec leur renvoi vers Mes preuves.
  L'étude les fait rejoindre « Mes preuves › Équipe » avec la rédaction (Réd. V3) : ce sont deux données distinctes
  (`companies.team`, lue par la rédaction et pseudonymisée avant l'IA ; les fiches « salarié » de Mes preuves, avec
  CV) ; les réunir est un changement de données de la rédaction, pas un rangement d'écran.

### A3.2 Le montant que je porte seul

- **Champ nouveau, vide par défaut** : `matching_criteria_ext.montant_porte_seul` (FLOAT, NULL), dans « Ce que je
  cherche », sous la fourchette. **Jamais déduit** de `budget_max` (500 000 € par défaut, une préférence) ni d'un
  autre champ (étude, § 7.1) : un compte qui n'y a jamais touché n'« a indiqué pouvoir porter seul » aucun montant.
  La démonstration n'en invente pas (test).
- **Utilisé seulement là où l'étude le prévoit** : l'innovation A du moteur (« la partie dépasse ce que vous portez
  seul », une raison objective de répondre à plusieurs), derrière un interrupteur jusqu'à l'avis d'un conseil, pas
  encore construite. Il n'entre donc **dans aucun calcul** : ni classement, ni note, ni filtre, ni consigne de l'IA
  (« le montant que je porte seul ne masque plus, il signale » : étude moteur, § 6.4). Garde-fou :
  `test_montant_porte_seul_n_entre_dans_aucun_calcul` (seule `app/routers/criteria_v2.py` le nomme ; le classement
  d'un marché est identique avec ou sans lui).
- **Bulle** : ce qu'il est (« le plus gros marché, ou la plus grosse partie (lot) d'un marché, que votre entreprise
  réalise seule »), « Laissez vide si vous ne savez pas : Adjugo ne le déduit d'aucun autre champ. Il ne masque aucun
  marché et ne change aucune note. » Aucune promesse d'une fonction qui n'est pas en ligne (étude, § 6).
- **API** : `GET /api/criteria/` le rend (`null` sans valeur) ; `PUT` : une valeur le remplace, `null` ou `""`
  l'efface, **absent de la requête il est gardé** (une page plus ancienne, encore en cache, ne l'efface jamais :
  `model_fields_set`) ; négatif ou au-delà de 10 milliards : 400 « Le montant que vous portez seul est un montant
  positif, en euros HT. ».
- **Mes données (RGPD)** : l'export lit désormais les critères que la page enregistre (`matching_criteria_ext`, tous
  les champs de `CriteriaUpdate`, montant compris) ; il lisait l'ancienne table `matching_criteria`, que plus aucun
  écran n'écrit (repli gardé si la ligne étendue manque).
- **Migration `c4montantseul`** : ajoute la colonne si elle manque (idempotente), aucune valeur par défaut, aucune
  donnée touchée ; retour arrière réel (la colonne est retirée). Le code de production précédent ne la déclare pas :
  il lit et enregistre ses critères sans la toucher (vérifié sur Postgres, § A3.6).
- **Laissé à la vague 2b** : la question « Jusqu'à quel montant répondez-vous seul ? » dans la fenêtre SIRET, avec la
  réponse « Je ne sais pas », et la tâche d'activation « Dire ce que vous faites et où » (étude, § 7.1 et 7.2) ; cette
  réponse demandera de distinguer « vide » et « je ne sais pas ». La « plus grosse partie acceptée » du profil réseau
  (`lot_max_eur`) reste une donnée distincte (une préférence de partenaire, publique) : elle n'alimente pas ce champ.

### A3.3 Mes documents : catégorie, date de fin, alertes cohérentes

- **Visibles et modifiables dans la liste** : la catégorie (Administratif, Fiscal et social, Assurances,
  Qualifications, Autre : les clés de `DocCategory`, libellés `CATEGORIES_DOC` dans `app.js`) et la date de fin
  (calendrier ; vide : sans date), enregistrées au changement (`docModifier` → `PATCH /api/documents/{id}`). Avant,
  toute pièce déposée arrivait « autre », sans date, et aucun écran ne permettait d'en mettre une : la pastille et
  les alertes de fin ne pouvaient servir qu'aux pièces des démonstrations.
- **Un seul calcul de la fin** : `app/services/pieces_fin.py` (`etat_fin`, `ALERTE_JOURS = 30`, `jour_paris`), lu
  par la liste (`fin` : « Expirée le 17/10/2026 », « Expire aujourd'hui », « Expire demain », « Expire dans 12
  jours », rien au-delà de 30 jours), par la pastille « pièces à renouveler » du menu et l'encart de l'accueil
  (`GET /api/documents/expiring`, 30 jours par défaut) et par le courriel d'alerte. Une pièce est « à renouveler »
  dans la liste exactement quand elle compte dans la pastille (test). **Jour de Paris** partout (le serveur tourne en
  UTC : entre minuit et 2 h, « aujourd'hui » n'était pas le même jour pour l'entreprise et pour Adjugo).
- **Une date changée a ses propres alertes** : le `PATCH` remet à zéro les drapeaux des alertes déjà envoyées
  (30 jours, 7 jours, jour même) quand la date change, pas quand seule la catégorie ou le nom change. Avant, une
  attestation renouvelée par sa date n'aurait plus jamais été signalée (le remplacement d'un fichier, lui, créait
  déjà une nouvelle version sans drapeaux).
- **`PATCH /api/documents/{id}`** : nom, catégorie et date de fin, chacun seulement s'il est présent ; refus avec une
  phrase : catégorie inconnue, date illisible ou improbable (année hors 2000-2100), nom vide, requête sans aucun de
  ces champs. Démonstration : refusé, comme avant (garde de la démo).
- **Courriel d'alerte** : « Adjugo — 1 pièce à renouveler » (« N pièces à renouveler ») ; chaque ligne avec le
  libellé de la liste (« • Kbis.pdf : expire dans 5 jours (date de fin : 25/10/2026) ») ; « Mes documents » au lieu
  de « coffre-fort » ; « marchés » au lieu d'« appels d'offres ».
- **Écran** : une ligne d'aide (« 30 jours avant sa fin, elle est signalée ici et comptée parmi les pièces à
  renouveler du menu ») ; l'état vide de l'étude (§ 7.3) : « Ajoutez vos attestations avec leur date de fin : Adjugo
  vous prévient avant qu'elles expirent. » (vrai à l'écran : pastille et accueil, 30 jours avant). Recherche et tri
  par catégorie lisent le libellé ; colonne « Date de fin » (plus « Expiration ») ; les boutons d'une ligne nomment
  la pièce au lecteur d'écran. **375 px** : une pièce par bloc, chaque valeur sous son nom, plus de défilement de côté
  dans le tableau.
- **Pour Eliot** : le courriel d'alerte part avec la tâche planifiée `POST /api/admin/run-alerts` (une fois par jour) ;
  l'écran ne le promet pas tant qu'elle n'est pas confirmée en production.

### A3.4 La fenêtre de confirmation de l'application

Les **19 `confirm()` et `prompt()`** du navigateur de `app.js` (étude, § 9) passent par la fenêtre de l'application,
`fenetre-confirmation`, déjà utilisée par la convention, Mes preuves, le réseau et l'atelier. Il n'en reste aucun
dans l'espace des entreprises (`app.js`, `app.html`, `invite.html`, `redaction-partenaire.js`, `carnet-notes.js`,
`sources-publiques.js`, `cotraitance-crypto.js` : test, commentaires exclus).

| Fonction | Fenêtre |
|---|---|
| `rgpdDelete` (2 `prompt`) | Une seule fenêtre : mot de passe (`type="password"`, gardé tel quel, espaces compris) et « Tapez SUPPRIMER pour confirmer » ; « Supprimer définitivement » inactif tant que le mot n'est pas tapé |
| `orgRemove`, `orgTransfer` | « Retirer … de vos collègues ? », « Transférer la propriété de l'organisation ? » |
| `convertInvoice` | « Créer la facture ? » |
| `gateCriteria` | « Dire d'abord ce que vous cherchez ? » : « Renseigner ce que je cherche » ou « Analyser quand même » ; **Échap ou Annuler n'analyse pas** (une analyse coûte un crédit ; avant, « Annuler » lançait l'analyse) |
| `sharedLostCode`, `sharedDecline`, `aoRevokeInvite` | Effacer l'ancien détail du chiffrage, décliner l'invitation, révoquer un lien |
| `sharedEnsureVerified` (repli du `prompt`) | « Vérifiez votre identité » : code à 6 chiffres (`inputmode="numeric"`, `autocomplete="one-time-code"`, valide seulement à 6 chiffres) |
| `aoGrpCancelPlan` | « Annuler la composition retenue ? » (bouton de sortie « Garder la composition ») |
| `aoFreezeOffer`, `aoUnfreezeOffer` | Figer et défiger l'offre commune ; « caduque » devient « à revalider », avec la raison (règle de la vague 1) |
| `delProject`, `delCotraitant`, `delContact`, `srcDelAlert`, `kbDelete` | Suppressions (bouton rouge) ; retirer un partenaire dit qu'il quitte aussi les marchés où il a été ajouté et qu'une convention qui le cite sera à revalider (`cotraitants.py`) |
| `renameDoc` (`prompt`) | « Renommer le document » : champ prérempli |

- **Une API** : `demander(cfg)` rend une promesse (les valeurs des champs si l'on confirme, `{ autre: true }` pour le
  second choix, `null` si l'on annule ou ferme) ; `confirmer(cfg)` rend vrai ou faux ; `_convAsk(cfg)` (avec `run`)
  reste pour les fenêtres existantes. `cfg` : `title`, `lines` (texte ou `{ t, warn }`), `ok`, `annuler`, `autre`,
  `danger`, `fields` (`key`, `label`, `value`, `type`, `requis`, `attendu`, `motif`, `max`, `inputmode`,
  `autocomplete`, `placeholder`, `aide`). Une seule fenêtre à la fois : en ouvrir une annule la précédente.
  Validation : `champsValides` (fonction pure, testée sous Node).
- **Accessible et au clavier** : `role="dialog"` (avec des champs) ou `alertdialog`, `aria-modal`, nommée par son
  titre et décrite par ses lignes ; focus sur « Annuler » ou sur le premier champ ; **focus gardé dans la fenêtre**
  (Tab et Maj+Tab bouclent, `cdlgTab`) ; Échap ferme ; Entrée dans un champ confirme si c'est valable ; le focus
  revient où il était ; champ requis dit au lecteur d'écran (`aria-required`), aide liée (`aria-describedby`) ;
  bouton de confirmation inactif tant que les champs ne sont pas valables.
- **375 px** : à 480 px et moins, les boutons s'empilent sur toute la largeur, l'action principale en haut.
- **Trouvé dans un vrai navigateur** : la passe d'accessibilité globale de `app.js` (qui pose `role="dialog"` sur chaque
  `.modal`) écrasait l'`alertdialog` d'une confirmation sans champ ; elle le garde désormais (test).
- **Hors périmètre** : `acheteur.html` (l'espace des collectivités, sa propre page en JavaScript simple, avec ses
  propres `confirm()`, `prompt()` et `alert()`), à traiter avec son propre chantier.

### A3.5 « lot » devient « partie (lot n) » (décision 10)

- **La règle** : à l'écran, une subdivision d'un marché est une **partie** ; quand on en désigne une, le numéro du
  règlement suit entre parenthèses : « Partie (lot 2) — Couverture », « partie (lot 2) » au fil d'une phrase,
  « parties (lots) » à la première mention. Dans l'atelier, où « partie » désigne déjà une partie du dossier de
  présentation, on écrit **« partie du marché »** pour le lot (« Un fichier par partie du marché », « Parties communes
  et parties propres à une partie du marché »). Un **« lot » lu à l'écran est toujours entre parenthèses**.
- **Un seul affichage** : `partieLot(x, intitule, minuscule)` (`app.js`), la même fonction dans
  `redaction-partenaire.js` et `carnet-notes.js` (chargés aussi par `invite.html`, sans `app.js` ; test : même texte,
  même résultat). Elle lit un numéro (« 2 ») ou un libellé du serveur (« Lot 2 — Couverture ») ; un texte libre
  (« Démolition », le périmètre saisi par un partenaire) reste tel quel.
- **Gardent « lot »** (le mot du règlement) :
  - les **données** : les libellés que le serveur range et renvoie (`atelier_lots.libelle`, `lot_libelle` du carnet
    de notes et de « Qui écrit quoi », la « Part » d'un membre saisie ou proposée, `pmLotPart`), parce qu'elles
    entrent dans la convention, les formulaires officiels et les fichiers remis au client ; l'écran les affiche par
    `partieLot` ;
  - les **fichiers exportés** : noms des fichiers d'un dossier à plusieurs lots (« Lot 2 - Mémoire technique - … »),
    contenu du dossier exporté et du ZIP, page de préparation du fichier (`atelier_preparation.py`), compte-rendu PDF
    du groupement (`consortium_report.py`), en-tête et ligne « Lot » du tableau de prix du partenaire
    (`cotraitance-crypto.js`), courrier de demande des notes à l'acheteur (`carnet_notes.py`) ;
  - les **citations du règlement**, entre guillemets « … » (« Pour chacun des lots, … », « 60 % pour le lot 2 »), et le
    fait lu « allotissement » (« Lot unique », « Lot 1 : Désamiantage ; … ») ;
  - le **dossier fictif de l'acheteur** dans la démonstration (règlement, CCTP, tableau de prix) ;
  - l'**espace acheteur** (collectivités : `acheteur*.html`, `routers/acheteur.py`, `routers/dce.py`, `dce_*.py`,
    `infructuosite_scoring.py`) : l'acheteur rédige son règlement, « lot » y est le mot juste (allotissement,
    art. L2113-10) ;
  - les **consignes de l'IA** (jamais lues) et les **expressions régulières** de lecture des règlements ;
  - le **modèle de convention** et son empreinte (vague 1, § 4.7) : rien n'y change, aucune convention validée ne
    devient « à revalider ».
- **Ce qui change** (une centaine de textes de l'interface, une soixantaine du serveur, tests compris) : page du
  marché (« Qui me complète ? » partie par partie, composition suggérée, parties couvertes, prix de vente de sa partie, offre commune,
  convention « Partie (lot) ou prestations »), atelier (choix des parties du marché, un fichier par partie du marché,
  portée commune ou propre, grille et limites par partie, dérogation), carnet de notes, espace partenaire
  (`invite.html`, « Où je suis partenaire » : « Partie (lot) / périmètre », « Prix de vente de votre partie »), profil
  réseau (« Plus grosse partie (lot) acceptée »), fiche partenaire et classement (`partner_matching.py`), messages du
  serveur (invitations, convention, réseau, atelier, carnet de notes, « Qui écrit quoi », entretien chantier), vitrine
  (« 3 parties (lots) »), textes de la démonstration à la voix d'Adjugo (résumés, recommandations, points
  d'attention). Le libellé « Allotissement » des faits lus devient « Parties (lots) ».
- **Garde-fous** : `test_aucun_lot_nu_dans_les_textes_lus_a_l_ecran` (pages et scripts servis, attributs techniques
  et citations « … » exclus ; deux textes gardés, `LOT_GARDES`, avec leur raison),
  `test_aucun_lot_nu_dans_les_messages_du_serveur` (erreurs, `message` / `detail` / `label` / `libelle` / `titre`,
  constantes `MSG_*`, courriels ; modules hors écran listés dans `HORS_ECRAN`),
  `test_textes_de_la_demo_a_la_voix_d_adjugo_disent_partie`,
  `test_les_fichiers_exportes_et_les_donnees_gardent_le_mot_du_reglement`.
- **Tests mis à jour** : `test_convention_groupement.py`, `test_cotraitance_v2_doctrine.py` (« prix de sa partie
  manquant »), `test_redaction_v6_lots.py` (grille, critère absent, message du règlement, « Dossier de la partie (lot
  2) », proposition de rédacteur), `test_redaction_v6_ensemble.py` (titres du carnet « Partie (lot 2) — … »),
  `test_redaction_v6_contre_relecture.py` (« selon la partie du marché »), `test_redaction_v4_chef_de_file.py` et
  `test_redaction_v4_groupement.py` (« Proposé d'après la partie déclarée par … »). Les valeurs du serveur testées
  (« Lot 3 — Étanchéité… », noms de fichiers) ne changent pas. Pour Mon entreprise : `test_reorganisation_v1_menu.py`
  (4 onglets, traductions), `test_reorganisation_v1_socle.py` (repère `vue-tarifs`),
  `test_redaction_v3_mes_preuves_ecrans.py` (ordre des onglets), `test_reorganisation_v1_contre_relecture.py`
  (« onglet « Ce que je cherche » »).
- **Laissé, avec sa raison** : les textes écrits par l'IA (analyse d'un vrai marché) peuvent dire « lot » ; changer la
  consigne toucherait la qualité, ce qui demande un test mesuré (règle d'Eliot) ; ils ne sont pas des libellés du
  produit.

### A3.6 Vérifications

- **Tests** : les 24 tests du nouveau fichier échouent tous sur `fab9d9a` (code de production extrait, même fichier) ;
  suite complète verte (2 112 tests, 2 088 avant) ; SRI (`scripts/sri_update.py --check`), `node --check` de chaque script servi, gabarit de
  `app.html` compilé par le Vue du dépôt (`test_gabarit_compile_par_le_vue_du_depot`), `scripts/i18n_ajouter.py
  --check` (469 → 519 clés : onglets, champs, bulles, catégories, la note « Ce qui a changé », les libellés renommés en
  « partie (lot) » ; règle de la vague 1 tenue : « marché » se dit « aanbesteding » et « licitación »).
- **Postgres 16** (`scratchpad/a3/run_a3_pg_depuis_prod.py` de la session, 31 contrôles verts, aucun en échec) :
  code de production `fab9d9a` extrait par `git archive`, base montée par son propre code (tête `b3mesureecrans`), données créées par ce
  code (critères avec une fourchette de 800 000 €, marchés dont un au statut « envoye », pièces avec et sans date de
  fin) ; code nouveau : une seule révision appliquée (`b3mesureecrans → c4montantseul`), aucune donnée perdue
  (critères, pièces, marchés identiques), montant vide sur les lignes existantes, seconde montée et rejeu forcé sans
  effet ; parcours du code nouveau sur la base montée (critères lus, montant enregistré puis gardé, état de la fin
  d'une pièce de production, catégorie et date changées, pastille, statuts inchangés, export RGPD) ; code de
  production redémarré (lectures et écritures 200, il n'efface pas le montant en enregistrant ses critères) ;
  schéma identique à une base neuve ; retour arrière (colonne retirée, rien d'autre ne bouge, code de production
  relancé) et remontée. Tests rejoués sur la base montée (15 fichiers, 423 tests) : 408 verts ; les 15 échecs sont
  tous dans `test_secu_rgpd.py` (une instruction propre à SQLite, `PRAGMA foreign_keys`) et identiques avec le code
  de production.
- **Navigateur réel** (serveur local, base jetable, démonstration par lien privé avec une clé jetable de 48
  caractères, aucun envoi, aucune IA), 1 280 px et 375 px, sombre et clair : Mon entreprise et ses 4 onglets ;
  Tarifs ; Ce que je cherche (montant « Non renseigné ») ; Mes documents (catégories, dates, « Expire dans 26 jours »
  et « Expire dans 22 jours » pour les 2 pièces de la pastille ; refus de la démonstration affiché et ancienne valeur
  revenue ; à 375 px une pièce par bloc, aucun défilement de côté) ; fenêtre « Renommer le document » (focus sur le
  champ, Tab et Maj+Tab bouclent dans la fenêtre, Échap ferme et rend le focus au bouton) et « Supprimer ce marché ? »
  (`alertdialog`, focus sur « Annuler », boutons empilés à 375 px) ; marché à plusieurs parties de la démo (page du
  marché et atelier : « Partie (lot 2) — Couverture et zinguerie », « Un fichier par partie du marché », « Dossier de la
  partie (lot 3) non validé ») ; espace partenaire (« Partie (lot) / périmètre », « Prix de vente de votre partie ») ;
  vitrine (« 3 parties (lots) », 375 px sans débordement).

### A3.7 Pour la réunion des chantiers

- **Migration** : `c4montantseul` a pour parent `b3mesureecrans`. Si un autre chantier de la vague 2a ajoute une
  révision sur le même parent (la clé `envoye` qui migre, décision 7), chaîner l'une après l'autre (changer
  `down_revision` de la seconde) pour garder une seule tête. Réunion : fait, `c4montantseul` suit `c4axeetapes` (§ R.4).
- **Zones de fichier touchées** : `RUBRIQUES` (rubrique « Mon entreprise » seulement), vues `company`, `criteria`,
  `tarifs`, `documents`, la fenêtre `fenetre-confirmation`, les textes « lot » un peu partout (page du marché,
  atelier, espace partenaire) ; `go()` n'est pas modifiée.

---

## R. Réunion des chantiers

Tests : `tests/test_reorganisation_v2a_reunion.py` (10 tests : ce qui se croise entre les chantiers ; 2 échouent sur la
fusion brute, les 8 autres décrivent ce que les commits de fusion ont déjà corrigé). Postgres :
`scratchpad/a4/run_reunion_pg.py` de la session (§ R.6).

### R.0 Ordre et méthode

Sur la production (`feat/produit-acheteur-collectivites` = `fab9d9a`, avance rapide), A1 (`0134174`, avance rapide),
puis A2 (`93c674c`, fusion `6a3d7ad`), puis A3 (`c0c952f`, fusion `8bc89b3`), puis les corrections de la réunion.
Conflits résolus bloc par bloc, jamais un fichier entier d'un seul côté : `app.js` 4 puis 6 blocs, `app.html` 4 puis
11, `styles.css` 2, `mesure_usage.py` 2, `test_reorganisation_v1_socle.py` 1, ce contrat. `i18n.js` : fusion à trois
clé par clé (469 + 31 de A1 + 83 de A2 + 50 de A3 − 1 en commun = 632 clés : « Chercher pour cette partie »,
ajoutée par A2 et par A3 avec la même traduction ; aucune clé changée différemment des deux côtés). Empreintes SRI régénérées (`sri-manifest.json`,
`app.html`, `invite.html`).

### R.1 Axe d'étapes (A1) et Mes marchés (A2)

- Mes marchés est la **liste filtrable de A2** ; les colonnes de A1 (`kanbanColonnes`) sont retirées. La liste se
  groupe dans l'ordre de l'axe (`statuses2` = `AXE_ETAPES`) : « À venir » en tête quand il y a une carte avant
  publication (D11), un groupe seulement s'il a des marchés (comme les colonnes « À venir » et « Abandonné » de A1).
- **Plus aucune clé `envoye` écrite** : `statutPartenaire` (A2) rend `depose` pour un marché où je suis partenaire et
  dont le groupement est déposé ; les tests de A2 suivent l'axe à 8 étapes ; « Prêt à déposer » (pastille et
  « Retirer le marquage ») lit `depose`.

### R.2 Une adresse par écran (A1), filtres de Mes marchés (A2), onglets de Mon entreprise (A3)

| Écran | Adresse |
|---|---|
| Mes marchés › Marchés, filtre Tous · Je pilote · Où je suis partenaire · À plusieurs | `/app/marches` · `/app/marches/je-pilote` · `/app/marches/partenaire` · `/app/marches/a-plusieurs` |
| Mes marchés › Bilan | `/app/marches/bilan` |
| Mon entreprise › Ce que je cherche · Tarifs | `/app/entreprise/ce-que-je-cherche` · `/app/entreprise/tarifs` |
| `/app/partenaires/reseau/invitations` (onglet retiré par A2) | ouvre Mes marchés, filtre « Où je suis partenaire » (là où les invitations se traitent), l'adresse devient `/app/marches/partenaire` |

- `adresseCourante` lit aussi le filtre (`mmFiltre`) ; un filtre choisi est une entrée de l'historique (précédent :
  le filtre d'avant). `_appliquerAdresse` ouvre la liste puis pose le filtre comme un clic (`mmFiltrer` : chargements et
  mesure de l'ancien écran compris). `ADRESSES_MES_MARCHES` en tête de `app.js`.
- `?shared=<jeton>` sans dossier trouvé, `go("shared")`, `go("consortiums")` et « Retour » d'un dossier partagé mènent
  au filtre, à son adresse ; « À faire » (invitation reçue) aussi (cible `{ view: "shared" }`).
- Le chemin `/app/entreprise/criteres` de A1 (jamais en production) devient `/app/entreprise/ce-que-je-cherche`, le nom
  de l'onglet de A3.

### R.3 Gestes de Préparer (A1) et fenêtre d'invitation unique (A2)

A2 a retiré le formulaire d'invitation et `aoCreateInvite`, où A1 faisait passer le marché « En préparation ». Une
invitation réussie dans la fenêtre unique (`rinvSend`, les trois cas) appelle `_marcheEnPreparation(pid)` : sur la page
du marché, `aoAvancer` (A1) ; ailleurs (« Inviter sur un marché » de Mes partenaires), le marché choisi passe de Repéré
ou Décidé à En préparation par la même route (`PUT /api/projects/{id}`) ; « À venir », « En préparation » et au-delà ne
bougent pas. Une invitation refusée (démonstration, registre indisponible) ne change rien. « Préparer à plusieurs »
(étape Décider, et carte « À venir » de D11) ouvre la fenêtre unique sur « qui invitez-vous ? ».

### R.4 Migrations : une seule tête

`b3mesureecrans` → `c4axeetapes` (A1) → `c4montantseul` (A3, `down_revision` changé ; les deux révisions sont
indépendantes : un type énuméré d'un côté, une colonne de l'autre). Le retour au code de production est
`alembic downgrade b3mesureecrans` (les deux révisions redescendent). Les tests de migration de A1 et de A3 passent
tels quels.

### R.5 Textes : « partie (lot n) » (A3) dans les vues de A2, et un nom d'écran

- Structure de A2, textes de A3 : « Qui me complète ? » et la fenêtre d'invitation (déjà « partie ») gardés ; reportés
  sur eux : « Parties (lots) dont le métier n'a pas été reconnu », « selon la partie (lot) », « par partie (lot) », « ex.
  Électricité (lot 2) » ; dans le compte-rendu de la liste : « Parties couvertes ».
- Les libellés de parties venus des données (`l.lot` du compte-rendu et des parties couvertes, `c.lot`, `p.lot`,
  `m.lot`, `r.lot_libelle`, `inv.lot_propose`) s'affichent par `partieLot` : « Lot 1 — Désamiantage… » se lit « Partie
  (lot 1) — Désamiantage… » ; un texte libre reste tel quel ; les données ne changent pas (A3).
- « Prêt à déposer », désormais vu par toute entreprise (A2) : « Votre Attest. sociale (URSSAF), dans Mes documents,
  expire avant la date limite » (l'ancien nom « coffre-fort » ; deux tests suivent).
- Le second « Figer l'offre » et son `confirm()` restent retirés (A2) ; le test des confirmations de A3 le dit.
- Mesure d'usage : `bilan` (A2) et `tarifs` (A3) dans `ECRANS` ; titres et bulles des deux vues.

### R.6 Vérifications

- **Suite complète** verte (SQLite, TZ=UTC) : 2 175 tests ; `scripts/sri_update.py --check` ; `node --check` des scripts
  servis ; gabarit de `app.html` compilé par le Vue du dépôt ; `scripts/i18n_ajouter.py --check` (632 clés) ; garde des
  mots bannis verte.
- **Postgres 16.2 depuis l'état exact de la production** (`run_reunion_pg.py`, 44 contrôles sur 44) : base neuve
  du code réuni (une seule tête `c4montantseul`, étiquettes de l'axe dans l'ordre, identiques au modèle, colonne du
  montant `FLOAT NULL` sans défaut) ; code de production `fab9d9a` extrait par `git archive`, base montée par son propre
  code (tête `b3mesureecrans`) et données créées par lui (chef de file et partenaire, annuaire, critères avec une
  fourchette de 800 000 €, pièces avec et sans date de fin, un marché seul avec prix et formulaires, un second seul, un
  marché à plusieurs, un marché marqué déposé par la production — clé « envoye » —, gagné, perdu, abandonné, un devis
  « envoye », le journal, et la démonstration qu'elle crée au démarrage) ; code réuni : **deux révisions, dans l'ordre**
  (`b3mesureecrans → c4axeetapes → c4montantseul`), « envoye » → « depose » sur les seuls marchés, devis et factures,
  journal chaîné, critères et pièces intacts, chaque table garde ses lignes, montant vide, schéma identique à une base
  neuve, seconde montée et rejeu forcé sans effet, révision interrompue qui se termine ; le code réuni sur la base
  montée (axe et 422, « Prêt à déposer » seul et à plusieurs, marché déposé lu « depose », Mes marchés avec les mêmes
  champs qu'avec la production, « Qui me complète ? », formulaires horodatés pour un marché seul, « Marquer déposé »
  seul puis retrait, inviter puis « En préparation », critères et montant, pièces, pastille, export RGPD, adresses
  servies) ; cloisonnement (le partenaire : 404 sur le marché, le dépôt, « Qui me complète ? » du chef de file) ; retour
  arrière à `b3mesureecrans` (statuts rendus à l'ancienne clé, colonne retirée, rien d'autre), **code de production
  relancé : lectures et écritures 200** ; remontée (schéma identique). Vrais tests sur Postgres, bases neuves montées
  par chaque code : 28 fichiers communs, **mêmes résultats avec la production et avec le code réuni** (596 réussis,
  6 échecs et 45 erreurs des deux côtés, tous dus à l'instruction propre à SQLite `PRAGMA foreign_keys` de
  `test_secu_rgpd.py` et à ce qu'elle laisse dans la session de test) ; les 4 fichiers de la vague 2a : 87 sur 87.
- **Navigateur réel** (serveur local, base jetable, démonstration par lien privé avec une clé jetable de 48 caractères,
  `DEMO_PUBLIC=0`, réseau sortant, courriels et IA coupés), 1 280 px et 375 px :
  - adresses : chaque écran visité a la sienne et son titre d'onglet ; Mes marchés › À plusieurs, Où je suis
    partenaire, Je pilote, puis un marché, puis précédent cinq fois et suivant deux fois (écran et filtre justes à chaque
    pas) ; rechargement de `/app/marches/a-plusieurs` (filtre rouvert) ; liens profonds `/app/marches/1` et `/2` ;
    `/app/partenaires/reseau/invitations` → `/app/marches/partenaire` ; `/app/n-importe-quoi/12` → `/app` ;
    `/app/marches/9999` → Mes marchés ; `?shared=` inconnu → filtre « Où je suis partenaire », jeton retiré ;
  - liens des courriels : `?verify=` (lu, adresse nettoyée), `?reset=` (« Choisissez un nouveau mot de passe »),
    `#gcode=` invalide (message, adresse `/app`), `/invite/…` (espace partenaire) ; déconnecté,
    `/app/marches/9?inscription` → « Créons votre compte » sur la même adresse, puis connexion → le marché 9 ;
  - Mes marchés : groupes dans l'ordre de l'axe (« À venir » en tête après une carte D11), filtres, compte-rendu de
    Kerhel déplié (« Partie (lot 1) — Désamiantage et retrait d'amiante (SS3) »), Bilan, Devis et factures ;
  - invitation, avec deux comptes de test locaux (chef de file et partenaire) : partenaire connu avec email (« Lien
    créé. L'email n'a pas pu partir… », le marché passe de Repéré à En préparation), registre (SIRET → « Le registre
    officiel est momentanément indisponible », « Inviter sans passer par le registre », le marché ne bouge pas), réseau
    (le cas, sa phrase « Adjugo envoie l'invitation… », le renvoi vers « Qui me complète ? ») ; dans la démonstration,
    le refus « La démo est en lecture guidée… » ; le partenaire ouvre le lien, « Ouvrir dans mon Adjugo » →
    `/app/marches/partenaire/9` (l'identifiant, jamais le jeton), puis « Où je suis partenaire » (sa carte, statuts
    seulement) ; cloisonnement vérifié depuis son compte (marché, dépôt, « Qui me complète ? », invitations,
    état du groupement du chef de file : 404) ;
  - « Prêt à déposer » seul (« 1 contrôle sur 5 », aucun manque de groupement ; démo, Réfection toiture : « 3 contrôles
    sur 5 ») et en groupement (Kerhel : « 3 contrôles sur 4 » ; le compte de test, une fois l'invitation faite :
    les 4 contrôles du groupement) ;
  - décision : Infogérance SI « Préparer à plusieurs » → Décidé et la fenêtre ; « Écarter » (fenêtre `alertdialog`) →
    Abandonné ; « Remettre » → Repéré ; carte « À venir » créée depuis une fin de contrat, sa page, précédent (la
    recherche est encore là) ;
  - Mon entreprise : 4 onglets, chacun son adresse ; Tarifs ; Ce que je cherche (montant « Non renseigné ») ; Mes
    documents (catégorie et date de fin) ; « Renommer le document » (`dialog`, focus dans le champ, Échap, focus rendu) ;
  - 375 px : barre basse (5 mots entiers, « Mes marchés » puis « Menu » surlignés), menu complet, Mes marchés
    (filtres sur 2 colonnes), page de Kerhel, Mes documents (une pièce par bloc), Mon entreprise (onglets sur 2
    lignes) : aucun défilement horizontal ;
  - cloche (« À faire », « Activité ») ; accueil (« À faire », « Bilan · 3 marchés terminés · 2 gagnés sur 3 ») ;
  - espace partenaire (`/invite/…` de Kerhel et du compte de test) et espace collectivités (`/acheteur/app` par la
    démonstration) : intacts ;
  - démonstration complète (pitch), après redémarrage sur une base neuve : accueil, Trouver des marchés (recherche),
    Mes marchés, Kerhel (Lire, Décider, Préparer, Déposer), atelier (« Partie (lot 1) — … », « Retour au marché » =
    précédent), Partenaires (Mes partenaires, Réseau Adjugo sans l'onglet des invitations reçues), sans erreur de script
    (seules erreurs de console : les refus attendus, 403 de la démonstration, 404 du cloisonnement, 503 du registre
    coupé, 400 des liens invalides).

### R.7 Laissé, avec sa raison

- **« coffre-fort » ailleurs** (espace partenaire : « Joindre depuis mon coffre-fort », messages de `invites.py`) :
  textes de l'espace partenaire, réduit en vague 2b ; seul le message que A2 montre maintenant à toute entreprise a
  été changé.
- **La table des membres de la convention** (« Lots 2 et 3 — … ») et le fait lu « allotissement » gardent « lot » : la
  convention et les citations du règlement le gardent (A3).
- **Cartes de recherche « adéquation 100/100 »** : déjà en production, zone du Moteur V0 (étude, § 9 « Ensuite »).
- **Le titre de la fenêtre d'invitation** garde le nom saisi quand on change de cas (« Inviter Atelier Fictif SARL »
  sur le cas « registre ») : comportement de A2, sans effet sur l'envoi (le registre relit l'identité par le SIRET).

### R.8 Pour Eliot

- **Déploiement** : deux migrations passent avant le démarrage (`c4axeetapes`, `c4montantseul`). Le code précédent ne
  lit pas `depose` : sur une base migrée, toute organisation qui a un marché déposé voit **toutes ses listes** répondre
  en erreur, et ses partenaires « Où je suis partenaire » (`/api/shared`) et l'historique du réseau (mesuré, § L.4). Donc : déployer à une heure creuse ; suivre le passage au vert de la nouvelle instance ; si elle ne démarre
  pas (Railway garde alors l'ancienne sur la base migrée), lancer tout de suite `alembic downgrade b3mesureecrans`.
  Tout retour au code précédent commence par `alembic downgrade b3mesureecrans` (A1.6). À refaire au moment de la mise
  en ligne depuis l'état réel de la production.
- **Décision prise par A1, à confirmer** : un marché « À venir » le reste jusqu'à sa publication (ni la décision ni un
  geste de préparation ne le font avancer ; on change son statut à la main).
- **Courriel aux 7 PME** : remplacer les noms d'onglets par les filtres « Où je suis partenaire » et « À plusieurs » de
  Mes marchés, ajouter le Bilan (anciennement sur l'accueil), Mon entreprise › Tarifs et « Ce que je cherche »
  (anciennement « Mes critères ») ; les adresses de chaque écran se partagent et se mettent en favori.
- **Alertes des pièces** : le courriel part avec la tâche planifiée `POST /api/admin/run-alerts` (A3.3).

---

## L. Relecture de la vague 2a

Dix remarques (cinq lentilles : adresses et liens, données et étapes, cloisonnement et invitations, démonstration et
suite). Chacune a été **reproduite** avant d'être corrigée ; **aucune n'est rejetée**. Tests :
`tests/test_reorganisation_v2a_relecture.py` (20 tests : 19 échouent sur `e66ed55`, le 20e garde le calcul d'un
groupement inchangé). Postgres : `scratchpad/rel2a/run_relecture_pg.py` de la session (§ L.11).

### L.1 Précédent du navigateur avec une fenêtre ouverte (remarques 1 et 9)

**Reproduit** : le gestionnaire `popstate` (A1) changeait l'écran sans fermer les fenêtres de l'application (A3 : la
confirmation ; A2 : l'invitation) ; confirmer « Écarter » agissait alors sur le marché de l'écran suivant (la
production n'avait ni `popstate` ni ces fenêtres : `confirm()` bloquait la page). **Corrigé** :

- `_surRetourNavigateur` (le gestionnaire) ferme d'abord toute fenêtre ouverte (`_fermerFenetres` : confirmation, qui
  répond « Annuler » ; invitation ; fiche d'un partenaire ; formulaire ; tiroir ; cloche ; découverte ; avis ;
  fenêtres de l'atelier et de Mes preuves). **Précédent avec une fenêtre ouverte ne fait QUE la fermer** (le geste
  retour d'Android) : l'écran reste, son adresse revient dans l'historique (le seul `pushState`, dans
  `_adresseSynchro`, sans réécrire la position de défilement de l'entrée d'avant), le focus revient au bouton
  d'origine. Suivant avec une fenêtre ouverte : elle se ferme et l'écran suit l'adresse. Le sens est lu dans la
  profondeur gardée dans l'entrée (`n`, `_nIci`).
- Défense en profondeur : la fenêtre de confirmation retient l'écran où elle s'ouvre (vue, marché, dossier partagé :
  `_cdlgEcran`) ; si l'écran a changé sous elle, « Confirmer » et le second choix valent « Annuler ». Une seule règle
  pour tous les appels (`demander`, `confirmer`, `_convAsk`) au lieu de figer chaque cible.
- Vu dans un vrai navigateur : la cloche ouverte, l'« Écarter ce marché ? » d'Infogérance SI, la fenêtre d'invitation :
  précédent les ferme, l'adresse et le marché restent (le statut du marché ne bouge pas) ; ensuite précédent et
  suivant changent d'écran comme avant.

### L.2 Deux invitations acceptées sur le même marché (remarque 2)

**Reproduit** (sur l'API : deux invitations, partenaire du groupement et sous-traitant, acceptées par le même compte ;
`/api/shared` les rend toutes deux avec le même `project_id`) : `?shared=` et l'adresse ouvraient la première du marché
(pour `?shared=`, une régression : la production ouvrait celle du jeton). **Corrigé**, sans changer l'API :

- l'adresse d'un dossier partagé porte, après l'identifiant du marché, un **repère de l'invitation** : une empreinte
  courte de son jeton (`clePartage`, FNV-1a 32 bits, 7 caractères), dont on ne retrouve pas le jeton —
  `/app/marches/partenaire/34/k3j9x2a` ; **le jeton ne va toujours jamais dans l'adresse** ; `/api/shared` garde
  exactement ses champs (aucun identifiant ajouté : le test du cloisonnement de A2 reste tel quel) ;
- `trouverPartage` (fonction pure) : le dossier du repère ; sans repère (adresse tapée), le plus ancien du marché ;
  repère inconnu : aucun (« Ce dossier n'est plus accessible ») ;
- `?shared=<jeton>` ouvre l'invitation de ce jeton ; « À faire » garde le jeton en mémoire (`cible.jeton`, jamais dans
  l'adresse) et ouvre le bon dossier ; ses lignes ont des clés distinctes ;
- vu dans un vrai navigateur (deux comptes de test locaux) : `?shared=` du partenaire du groupement → son dossier (le
  sous-traitant venait avant) ; rechargement de chaque adresse → chacun le sien ; depuis le dossier du sous-traitant,
  Mes marchés puis le dossier du partenaire du groupement, puis précédent deux fois → la liste, puis le dossier du
  sous-traitant, chaque fois le bon rôle.

### L.3 Un geste ne fait jamais reculer un marché (remarque 3)

**Reproduit** : « Marquer déposé » ne mettait à jour que la page ; la liste de Mes marchés gardait « Repéré » ; inviter
depuis Mes partenaires envoyait alors `PUT {status: "en_cours"}`, accepté : le marché déposé repassait « En
préparation » sans entrée au journal (relances reprises). Même cause depuis une page ou une liste ouverte avant le
« Marquer déposé » d'un collègue. **Corrigé** côté serveur, là où un client périmé ne peut plus rien :

- `PUT /api/projects/{id}` accepte `si_statut` (les étapes d'où part un GESTE) : l'étape ne change que si le marché y
  est encore, dans la même instruction (`UPDATE … WHERE status IN …`, sûr sur Postgres comme sur SQLite) ; sinon rien ne
  change et l'étape réelle est renvoyée (200). Valeurs lues comme `status` (« envoye » → « depose », inconnue : 422).
  Le choix « Statut » (sans `si_statut`) reste libre ; la démonstration garde son seul geste permis (l'étape).
- L'écran envoie les étapes de départ de chaque geste (`DEPARTS_GESTE`, testées contre `statutApresDecision` et
  `statutEnPreparation`) : « Préparer seul / à plusieurs », « Écarter », « Remettre », les gestes de Préparer, l'invitation
  (page du marché et Mes partenaires) ; il reprend l'étape renvoyée, page et liste ; une décision qui ne change rien le
  dit (« Ce marché a changé d'étape entre-temps : il est à l'étape « Déposé » »).
- « Marquer déposé », son retrait et le choix « Statut » mettent aussi à jour la carte de Mes marchés (`_listeSuitStatut`).
- Vu dans un vrai navigateur : « Marquer déposé quand même » (la carte passe « Déposé ») ; liste rendue périmée (comme
  celle d'un collègue), Partenaires › « Inviter sur un marché » › « Créer le lien » : le marché reste « Déposé » côté
  serveur et la liste se corrige. Postgres : le marché déposé par la production ne recule pas.

### L.4 Bascule de la migration `c4axeetapes` (remarque 4)

**Reproduit et mesuré** (code de production `fab9d9a` sur la base migrée, Postgres 16.2) : répondent 500, pour le chef
de file qui a un marché déposé, Mes marchés, les statistiques, le tableau de bord des groupements, ses groupements, la
page du marché déposé et le changement de son étape ; pour son partenaire d'une autre organisation (sans marché déposé
à lui), « Où je suis partenaire » (`/api/shared`) et l'historique du réseau. Répondent 200 : un marché non déposé (lu et
écrit), les notifications, les marchés du partenaire. **Corrigé** (documentation : le code de production ne peut pas
changer) : docstring de la migration, A1.6 et R.8 disent l'étendue réelle et la procédure — heure creuse, suivre le
passage au vert de la nouvelle instance, `alembic downgrade b3mesureecrans` tout de suite si elle ne démarre pas
(Railway garderait l'ancienne sur la base migrée).

### L.5 « Prêt à déposer » : un sous-traitant seul, une convention restée en brouillon (remarque 5)

**Reproduit** : une invitation de sous-traitant seule, ou une convention en brouillon après le déclin du seul
partenaire, donnaient les 4 contrôles du groupement, dont 2 impossibles (« Aucun partenaire » à la génération).
**Corrigé** : `a_un_groupement` (même idée que `has_members` de l'état du groupement) — un groupement a un membre : une
invitation active d'un partenaire (pas d'un sous-traitant, qui relève du DC4), ou une convention générée (à valider,
validée, à revalider) ou en brouillon avec des partenaires hors ligne. Sinon, le calcul « seul », avec, pour un
sous-traitant, l'avertissement DC4 (jamais un manque). La liste des pièces dit la même chose : un sous-traitant seul
n'ajoute ni le pouvoir du chef de file ni la convention (le DC4 « à prévoir ») ; une convention restée en brouillon
sans partenaire n'ajoute plus sa ligne. Un groupement réel garde ses 4 contrôles (test). Démonstration : inchangée
(Kerhel « 3 contrôles sur 4 », Réfection toiture « 3 contrôles sur 5 »).

### L.6 Une pièce exigée reconnue sous son nom (remarque 6)

**Reproduit** : « Attestation de visite obligatoire », « Certificat ISO 27001 » (et même « ISO 27001 » déposé sous ce nom
exact) restaient « à ajouter » : `match_document` ne comparait que les mots-clés des pièces standard. **Corrigé** : un
document est aussi reconnu quand son nom porte **tous** les mots significatifs de la pièce (sans accents ni casse,
chiffres séparés des lettres, pluriel ôté, mots vides et génériques — « attestation », « certificat », « obligatoire »,
« en cours de validité »… — écartés) : « Visite obligatoire », « attestation visite », « ISO 27001 », « iso27001 ».
Jamais sur un seul mot commun : « … régularité fiscale » ne reconnaît pas « … régularité sociale », « ISO 27001 » pas
« ISO 9001 ». Les mots-clés des pièces standard ne changent pas. *Contre-relecture (§ M.1) : ce n'était pas tenu pour un
chiffre ou une lettre seuls (« DC 4 » était reconnu par DC1.pdf) ni pour le dossier de l'acheteur ; la règle exacte est
« tous les mots significatifs de la pièce, chiffres compris ».*

### L.7 Formulaires rangés par la production (remarque 7)

**Reproduit** (code de production : « Préparer mes documents » d'une entreprise seule range DC1, DC2, ATTRI1 dans
« Formulaires officiels » sans les horodater) : après la mise en ligne, « Formulaire … à préparer ». **Corrigé** : pour
une entreprise seule, un formulaire rangé dans le dossier du marché (`DC1.pdf`, `DC2.pdf`, `ATTRI1.pdf`, `DUME.pdf`,
hors corbeille, de l'organisation) compte comme préparé (`_formulaires_ranges`). Pour un groupement, rien ne change
(l'horodatage après la convention reste exigé). Aucune migration de données.

### L.8 Atelier ouvert directement (remarque 8)

**Reproduit** : depuis `/app/marches/7/dossier-de-presentation` (courriel « … a envoyé sa partie », favori), « Retour au
marché » ajoutait une entrée, puis « Retour » ramenait à l'atelier, sans fin. **Corrigé** : sans écran d'avant dans
l'application, la page du marché prend la place de l'atelier dans l'historique (`_sansHistorique`) ; son « Retour »
mène à Mes marchés. Vu dans un vrai navigateur (démonstration).

### L.9 La page d'une carte « À venir » (remarque 10)

**Reproduit** : pastille « Annonce seule », bandeau « Le dossier complet du marché est indispensable » et « Aucune
analyse encore » sur un marché pas encore publié. **Corrigé** (`aoPasPublie`, repère `marche-pas-publie`) : pastille
« Pas encore publié », phrase « Marché pas encore publié — Le dossier sera à importer à sa publication. Vous pouvez déjà
inviter vos partenaires. », l'explication dans la bulle (i), l'import discret (bouton secondaire). Dès qu'un dossier est
importé, la page redevient celle d'un marché publié. Vu à 1 280 et 375 px, sombre et clair.

### L.10 Repère et traductions

| Repère | Zone |
|---|---|
| `marche-pas-publie` | La phrase d'un marché « À venir », dans `marche-analyse` (à la place du bandeau « indispensable ») |

Décision 16 : 4 libellés traduits (632 → 636 clés : « Pas encore publié », « Marché pas encore publié », la phrase et la
bulle). Tests mis à jour, chacun avec sa raison en commentaire : `test_reorganisation_v1_socle.py` (le repère),
`test_reorganisation_v2a_adresses_etapes.py` (`?shared=` porte le repère ; `_aoChangerStatut` reçoit `depuis`),
`test_reorganisation_v2a_entreprise.py` (`_cdlgEcran` dans la fenêtre sous Node).

### L.11 Vérifications

- **Suite complète** verte (SQLite, TZ=UTC) : 2 195 tests ; `scripts/sri_update.py --check` ; `node --check` de `app.js` et
  `i18n.js` ; gabarit de `app.html` compilé par le Vue du dépôt ; `scripts/i18n_ajouter.py --check` (636 clés) ; garde des
  mots bannis verte.
- **Les nouveaux tests sur `e66ed55`** (copie par `git archive`) : 19 sur 20 échouent, chacun sur la remarque qu'il
  décrit ; le 20e (`…d_un_groupement_inchange…`) passe des deux côtés.
- **Postgres 16.2 depuis l'état exact de la production** (`run_relecture_pg.py`, 27 contrôles sur 27) : code `fab9d9a` (git archive), base
  montée par lui (tête `b3mesureecrans`), données créées par lui (marché seul passé par « Préparer mes documents »,
  marché « envoye », sous-traitant seul, partenaire qui décline après le choix de la forme, deux invitations du même
  partenaire sur un marché, pièce « Attestation de visite obligatoire » déposée sous son nom) ; code relu : deux
  révisions dans l'ordre, schéma identique à une base neuve ; le geste conditionnel sur le type énuméré de Postgres (le
  marché déposé ne recule pas, un marché Repéré avance, ancienne clé lue, 422) ; formulaires de la production comptés ;
  calcul « seul » pour le sous-traitant seul et la convention restée en brouillon ; la pièce reconnue ; `/api/shared`
  identique à la production ; cloisonnement (404) ; la bascule mesurée (§ L.4) ; retour arrière puis code de production
  relancé (lectures et écritures 200) ; remontée. Vrais tests : fichiers communs, mêmes échecs qu'avec la production
  (les 51 dus à `PRAGMA foreign_keys` de `test_secu_rgpd.py`, déjà notés au § R.6) ; les 5 fichiers de la vague 2a,
  relecture comprise : 107 sur 107.
- **Navigateur réel** (serveur local, base jetable, démonstration par lien privé avec une clé jetable, `DEMO_PUBLIC=0`,
  réseau sortant, courriels et IA coupés ; deux comptes de test locaux pour le cas des deux invitations) : L.1, L.2,
  L.3, L.8 et L.9 comme décrit plus haut ; Kerhel (« Lire : Terminé … Déposer : En cours », « 3 contrôles sur 4 ») ; 375 px
  sans défilement horizontal ; console sans erreur de script.

### L.12 Laissé, avec sa raison

- **Les routes `/api/shared/{marché}/…` du partenaire connecté** (rédaction, entretien, journal) désignent le dossier par
  le marché et prennent l'invitation la plus récente du compte sur ce marché. C'est déjà le cas en production
  (`journal_membre._shared_invite`), sans lien avec la vague 2a ; dans le seul cas de deux invitations du même compte
  sur le même marché, ces blocs montrent ceux de la plus récente. Rien n'est exposé d'un autre membre (les deux
  invitations sont au même compte). Les corriger demande de désigner l'invitation dans ces routes et dans
  `redaction-partenaire.js` : chantier à part, proposé à Eliot.
- **Précédent qui ne fait que fermer une fenêtre** : l'entrée « suivante » de l'historique est remplacée par l'écran
  resté affiché (le prix d'un comportement sûr et sans course entre deux mouvements d'historique).

---

## M. Contre-relecture de la vague 2a

Trois remarques (deux lentilles : cloisonnement et liens ; données, démonstration et suite), dont deux sur la même
correction (R6 de la relecture). Chacune a été **reproduite** avant d'être corrigée ; **aucune n'est rejetée**. Tests :
`tests/test_reorganisation_v2a_contre_relecture.py` (10 tests : les 10 échouent sur `238f6e0`). Postgres :
`scratchpad/cr2a/run_contre_relecture_pg.py` de la session (§ M.3).

### M.1 Une pièce reconnue sous son nom, jamais sous celui d'une autre (remarques 1 et 3)

**Reproduit** (appel direct de `match_document`, puis par l'API sur une entreprise seule) : `_mots_significatifs`
écartait tout mot d'un seul caractère, chiffres compris. « DC 4 » (→ dc) était reconnu par DC1.pdf, « ATTRI2 » par
ATTRI1.pdf (que « Préparer mes documents » range lui-même dans le dossier du marché), « Annexe 4 » par « Annexe 1 »,
« Annexe 1 - Cadre de réponse technique » par « Annexe 2 - … », « Attestation de visite n° 2 » par « … n° 1 » ; et le
repli lisait aussi le dossier « DCE » du marché (le dossier de l'acheteur, importé par l'entreprise) : « CCAP signé »
était reconnu par le CCAP.pdf de l'acheteur. La carte « Pièces à fournir » les cochait « ok » et « Prêt à déposer »
d'une entreprise seule ne les listait plus. Sur `e66ed55` (avant la relecture), ces pièces restaient « à ajouter » :
régression de la correction R6. **Corrigé** (`app/routers/checklist.py`, le repli par les mots seulement) :

- un chiffre est toujours un mot significatif, même seul : tous les chiffres de la pièce doivent être dans le nom du
  document (« Annexe 1 » ne reconnaît ni « Annexe 2 » ni « Annexe 12 ») ;
- une lettre seule n'est un mot que derrière un mot de repère (annexe, lot, partie, tranche, pièce, formulaire, cadre,
  modèle, volet, phase, chapitre, article, section, titre), et liée à lui (« Annexe A » → annexe, annexe:a) : « Annexe
  A » ne reconnaît ni « Annexe B », ni « Annexe B à compléter », ni « Annexe » ; « à », les élisions (« d' », « l' »…)
  et le « n » de « n° » n'en sont jamais (« Pièce d'identité » reconnaît « Pièce identité ») ; « no », « num »,
  « numéro » sont des mots vides ;
- le repli ne lit jamais les fichiers du dossier « DCE » : le même nom déposé dans Mes documents ou dans un autre
  dossier du marché est reconnu.

Le prix, assumé : une pièce sans mot-clé qui cite une durée (« Liste des services des 3 dernières années ») n'est
reconnue que par un nom qui porte ce chiffre. C'est un manque de trop, que l'entreprise voit et lève en nommant son
document ; jamais une pièce cochée à tort.

Les mots-clés des pièces standard (comportement de la production) ne changent pas. Démonstration : listes de pièces et
« Prêt à déposer » de tous les marchés de la démo identiques avant et après (`scratchpad/cr2a/demo_pieces.py`, code
`238f6e0` puis code corrigé, mêmes sorties) ; Kerhel « 3 contrôles sur 4 », Réfection toiture « 3 contrôles sur 5 ».

### M.2 Précédent du navigateur : le menu du téléphone et les fenêtres hors de Vue (remarque 2)

**Reproduit** (harnais Node des tests, gestionnaire `popstate` réel) : « Menu » de la barre basse ouvert
(`mobileNav`), précédent changeait l'écran et le menu restait ouvert. Les fenêtres que deux fichiers ajoutent à la page
hors de Vue restaient ouvertes sur l'écran suivant : `cotraitance-crypto.js` (« Vérifiez votre identité », code de
récupération) et `redaction-partenaire.js` (ses confirmations, « Envoyer votre partie au groupement ? »…, liées au
dossier quitté). **Vu dans le code puis reproduit sous Node avec les méthodes réelles** : un dossier partagé A quitté
pour un dossier B (suivant du navigateur) pendant que la fenêtre du code était ouverte — la part de A (nom, prix,
détail chiffré avec la clé de A) partait vers l'invitation de B (`PUT /api/invite/B/contribution`) ; avec « Vérifiez
votre identité », la vérification portait sur A et la soumission sur B ; « Déverrouiller » rangeait la clé de A sous
l'espace de B et affichait le détail de A sur B ; « Code perdu » rendait le nouveau code de A à B. Les deux dossiers
sont ceux du même compte (rien d'un autre membre n'était lu), mais la part d'un dossier pouvait partir vers un autre
chef de file. La production n'avait ni `popstate` ni ces adresses : précédent quittait l'application. **Corrigé** :

- `_fermerFenetres` ferme aussi le menu du téléphone (`mobileNav`) et les fenêtres hors de Vue : chacun des deux
  fichiers tient la liste de ses fenêtres ouvertes et l'expose (`fenetresOuvertes`, `fermerFenetres`, réponse
  « Annuler ») ; précédent les ferme et l'écran reste ; suivant les ferme et l'écran suit l'adresse ;
- défense en profondeur : les gestes d'un dossier partagé retiennent leur dossier et s'arrêtent si un autre est à
  l'écran après une fenêtre ou un appel (`_sharedPut`, `_sharedEncrypt`, `sharedSubmit`, `sharedEnsureVerified`,
  `sharedUnlock`, `sharedLostCode`, `sharedAvantReprise`) ; la réponse d'un enregistrement met à jour son dossier,
  jamais celui de l'écran suivant ;
- garde des tests étendue : tout fichier servi qui ajoute une fenêtre à la page (`document.body.appendChild`) expose
  `fermerFenetres` et `_fermerFenetres` l'appelle ; `_fermerFenetres` connaît `mobileNav`.

`invite.html` (le lien sans compte) n'a pas de routage : rien n'y change, à part les empreintes SRI des deux fichiers.

### M.3 Vérifications

- **Suite complète** verte (SQLite, TZ=UTC) : 2 205 tests ; `scripts/sri_update.py --check` ; `node --check` de
  `app.js`, `cotraitance-crypto.js` et `redaction-partenaire.js` ; gabarit de `app.html` compilé par le Vue du dépôt ;
  garde des mots bannis verte.
- **Les nouveaux tests sur `238f6e0`** : les 10 échouent, chacun sur la remarque qu'il décrit.
- **Postgres 16.2 depuis l'état exact de la production** (`run_contre_relecture_pg.py`, 30 contrôles) : le
  script de la relecture (§ L.11), plus un marché créé par le code de production (`fab9d9a`, tête `b3mesureecrans`) dont
  le dossier exige « ATTRI2 », « Annexe 4 » et « CCAP signé », passé par « Préparer mes documents » (ATTRI1.pdf rangé),
  avec « Annexe 1 » déposée et le CCAP.pdf de l'acheteur dans le dossier « DCE » : sur la base migrée, le code corrigé
  laisse les trois pièces « à ajouter » (carte et « Prêt à déposer ») et coche toujours « Attestation de visite
  obligatoire » déposée sous son nom ; le reste comme au § L.11 (geste conditionnel, formulaires de la production,
  sous-traitant seul, `/api/shared`, cloisonnement 404, bascule mesurée, retour arrière, remontée). Vrais tests : fichiers
  communs, mêmes échecs qu'avec la production (51 contre 51, les mêmes) ; 29 contrôles sur 30 au premier passage — le
  seul échec, le test du contrat, venait de la copie du code faite avant l'écriture de cette section ; relancés sur le
  code final (`run_v2a_pg_seul.py`), les 6 fichiers de la vague 2a : 117 sur 117.
- **Navigateur réel** (serveur local sur le code corrigé, base jetable, démonstration par lien privé avec une clé
  jetable, `DEMO_PUBLIC=0`, réseau sortant, courriels et IA coupés), à 375 px : Mes marchés → Infogérance SI → Mes
  marchés → Kerhel → précédent → Mes marchés ; « Menu » de la barre basse ouvert, précédent : le menu se ferme
  (`aside.side` sans `open`, plus de toile de fond), l'adresse reste `/app/marches` ; précédent suivant : Infogérance SI.
  Sur la page d'Infogérance SI, une fenêtre « Vérifiez votre identité » de `cotraitance-crypto.js`, puis une
  confirmation de `redaction-partenaire.js` : précédent ferme chacune (réponse « Annuler »), l'écran et l'adresse
  restent. 375 px sans défilement horizontal ; Kerhel « 3 contrôles sur 4 », Réfection toiture « 3 contrôles sur 5 » ;
  console sans erreur de script.

### M.4 Laissé, avec sa raison

- **Les mots-clés des pièces standard ne lisent pas les repères** (comportement de la production, inchangé) : une pièce
  lue dans le dossier qui contient un mot-clé (« Lot A - Planning », « Annexe à l'acte d'engagement n° 3 ») est
  reconnue par tout document de la famille (« Planning.pdf », ATTRI1.pdf), et ces mots-clés lisent aussi le dossier
  « DCE ». Ce n'est pas la correction R6 ; resserrer les mots-clés changerait ce que la production coche aujourd'hui
  (« Kbis de moins de 3 mois » ne doit pas exiger un « 3 » dans le nom du Kbis) : proposé à Eliot, avec des cas réels.
- **Le précédent ne ferme pas l'écran d'accueil du SIRET** (« Bienvenue sur Adjugo ») : un premier pas, pas une
  fenêtre (déjà exclu par la garde de la relecture).


## N. Contrôle des bugs (22/10/2026), groupe « marché »

Six défauts de la page du marché, de « Pièces à fournir », de « Avant de déposer », des formulaires officiels, de
l'export du dossier et des devis et factures. Chacun a été **reproduit** sur `cfe04e1` avant d'être corrigé ; aucun
n'est rejeté. Tests : `tests/test_controle_bugs_marche.py` (9 tests, tous en échec sur `cfe04e1`, chacun sur son
défaut). Aucun prix, quota ni offre ne change ; les pages juridiques ne sont pas touchées.

### N.1 Devis et factures : ceux de l'organisation, numérotés par entreprise

**Reproduit** : un devis créé par un collègue depuis la page du marché (« il sera rattaché à ce marché ») était
invisible au propriétaire (« Aucun devis ni facture lié », rien dans Mes marchés › Devis et factures, « Facturer »
répondait 404), et deux collègues obtenaient chacun « DEV-2026-001 » puis « FAC-2026-001 ». **Corrigé**
(`app/routers/invoices.py`) : la liste, la modification et « Facturer » lisent les devis et factures de
l'organisation (`member_ids`), comme Mes marchés et Mes documents ; le numéro suivant est compté sur toute
l'organisation. L'unicité en base reste (compte, numéro) : un collègue retiré laisse ses devis au propriétaire
(`org._reassign_member_data`) sans heurter un numéro. Une autre organisation ne voit rien (404) et garde sa propre
numérotation. Pour Eliot : les numéros déjà émis en double par deux collègues d'une même entreprise restent en base
(le code ne les renumérote pas) ; deux collègues qui enregistrent un devis à la même seconde peuvent encore obtenir
le même numéro (la base ne porte pas l'organisation sur la facture, il faudrait une migration).

### N.2 Export du dossier (ZIP) : une entrée par pièce, des noms et jamais des chemins

**Reproduit** : deux pièces de même nom dans Mes documents (une attestation déposée deux fois) écrivaient deux
entrées du même chemin, et l'une écrasait l'autre à l'extraction ; un intitulé « Travaux de voirie 2026/2027 »
rangeait chaque formulaire dans un sous-dossier (« DC1_Travaux_de_voirie_2026/2027_….pdf », chemin repris par le
sommaire), et le nom du formulaire téléchargé portait le « / ». **Corrigé** (`app/routers/export_dossier.py`,
`app/core/http.py`) : la seconde pièce devient « …_2.pdf » (à la casse près, comme la comparent Windows et macOS) ;
séparateurs de chemin et caractères interdits deviennent « _ » dans les noms du ZIP, du sommaire et du nom UTF-8 de
tout fichier téléchargé, comme le nom ASCII de repli le faisait déjà. L'intitulé du marché reste tel quel dans le
sommaire.

### N.3 « Pièces à fournir » : ni une catégorie partagée, ni un bout de mot

**Reproduit** (entreprise seule) : « Attestation de vigilance URSSAF.pdf » rangée dans « Fiscal et social » cochait
« Attestation de régularité fiscale » (la catégorie, clé `fiscal`, était lue comme le mot-clé) ; « Avis d'attribution
2025.pdf » cochait le RIB (« rib » dans « attribution ») ; la carte disait « Disponible » et « Avant de déposer » ne
réclamait ni l'une ni l'autre. **Corrigé** (`app/routers/checklist.py`) :

- la catégorie « Fiscal et social » ne vaut l'attestation fiscale que si le nom du document ne dit pas l'attestation
  sociale (urssaf, vigilance, cotisation, social), la règle des attestations du chef de file
  (`invites.vault_doc_type`) ; un nom sans indice dans cette catégorie vaut toujours l'attestation fiscale ;
- les mots-clés de trois lettres que l'on trouve dans des mots courants, « rib » (attribution, contribution) et
  « rge » (charges, décharge), ne comptent que comme un mot entier, côté document comme côté pièce demandée ; un
  changement de casse sépare deux mots (« MonRIB.pdf », « RibEntreprise.pdf » restent reconnus).

Ce n'est pas le point laissé en M.4 (les repères) : les autres mots-clés se lisent comme avant. Démonstration :
listes des pièces et « Prêt à déposer » de tous les marchés de la démo identiques avant et après (script de la
contre-relecture, `scratchpad/cr2a/demo_pieces.py`).

### N.4 « Préparer mes documents » par deux collègues : un seul jeu de formulaires

**Reproduit** : le propriétaire, puis un collègue, puis le propriétaire lancent « Préparer mes documents » sur le
même marché : le dossier « Formulaires officiels » gardait deux DC1.pdf, DC2.pdf, ATTRI1.pdf, HONNEUR.pdf (l'ancien
jeu, périmé, à côté du nouveau), et le ZIP les portait deux fois. **Corrigé** (`app/services/dossier.py`) : une pièce
rangée remplace celle du même nom dans le même dossier du marché, quel que soit le collègue de l'organisation qui
l'avait rangée ; jamais celle d'une autre organisation. Même règle pour le dossier de présentation exporté par
l'atelier et pour le dossier de l'acheteur ré-importé.

### N.5 Modifier un devis (`PUT /api/invoices/{id}`) : mêmes refus qu'à la création

**Reproduit** (l'écran n'appelle pas cette route ; appel direct) : une ligne à quantité négative était enregistrée
(total TTC négatif), un statut inconnu faisait échouer l'écriture ou la relecture (réponse 500, puis la liste des
devis et factures ne se lisait plus), de même qu'un statut, des lignes ou un taux de TVA envoyés vides. **Corrigé**
(`app/schemas/__init__.py`) : refus lisible (422) dans chacun de ces cas, avec le message de la création pour les
lignes ; un statut connu est enregistré. Laissé : une liste de lignes vide reste acceptée à la modification (total
à 0, pas d'erreur) ; la création, elle, la refuse.

### N.6 Laissé, avec sa raison

- **Le même bout de mot dans les pièces d'un partenaire** : `invites._classify_piece_type` (type d'une pièce déposée
  par un partenaire sans type choisi : sa liste de pièces, le coffre-fort croisé, le suivi du groupement du chef de
  file) range encore « Avis d'attribution 2025.pdf » et « Contribution.pdf » en RIB, « Cahier des charges.pdf » en
  qualification (constaté par appel direct). C'est la co-traitance, hors de ce groupe : signalé, non corrigé ici.
