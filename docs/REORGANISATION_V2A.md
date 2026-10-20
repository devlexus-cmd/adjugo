# Réorganisation de l'interface : vague 2a, « un marché, une page, une adresse »

Contrat de la vague 2a. Étude : « Réorganiser l'interface d'Adjugo : étude définitive » (12/10/2026), § 5.3, 8, 9
(vague 2a et « Ensuite »), 10 et 11. Base : `feat/produit-acheteur-collectivites` = `fab9d9a` (production du
20/10/2026 : vagues 0 et 1, contrat `docs/REORGANISATION_V1.md`). Tête Alembic de départ : `b3mesureecrans`.

Décisions de la vague (recommandations de l'étude, validées par Eliot) : D7 (un seul axe d'étapes, la clé « envoye »
migre, la barre affiche des statuts dérivés), D10 (« partie (lot n) »), D11 (une carte de Mes marchés avant la
publication, « Suivre » reste dans Trouver des marchés), D18 (barre basse de 5 sur téléphone) ; D8 et D9 comme en
vague 1. La vague 2b (prise en main, marché d'exemple, espace partenaire réduit) vient après : rien ici.

Chantiers : **A1** adresses et étapes (ce document, § A1 : D7, D11, D18, une adresse par écran, la cloche et
« À faire »).

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
| Mes marchés › Marchés · Où je suis partenaire · À plusieurs · Devis et factures | `/app/marches` · `/app/marches/partenaire` · `/app/marches/a-plusieurs` · `/app/marches/devis-et-factures` |
| Un marché · son atelier | `/app/marches/12` · `/app/marches/12/dossier-de-presentation` |
| Un marché où je suis partenaire | `/app/marches/partenaire/34` (l'identifiant du marché, **jamais le jeton d'invitation**) |
| Partenaires › Mes partenaires · Réseau Adjugo · Contacts | `/app/partenaires` · `/app/partenaires/reseau` · `/app/partenaires/contacts` |
| Réseau Adjugo › Annuaire · Historique · Invitations reçues | `/app/partenaires/reseau/annuaire` · `…/historique` · `…/invitations` |
| Mes documents › Mes pièces · Mon savoir-faire | `/app/documents` · `/app/documents/savoir-faire` |
| Mon entreprise › Identité · Mes critères · Mes preuves | `/app/entreprise` · `/app/entreprise/criteres` · `/app/entreprise/preuves` |
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
les mêmes mots.

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
choix « Statut » change sous les yeux). **Un marché « À venir » le reste** jusqu'à sa publication : ni la décision ni
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
- **Déploiement** : la migration passe avant le démarrage (`entrypoint.sh`). Le code de production précédent ne connaît
  pas `depose` : pendant la bascule (migration passée, ancienne instance encore en service quelques secondes), un
  marché déposé lu par l'ancienne instance répond en erreur ; la nouvelle prend le relais aussitôt. **Retour au code
  précédent : `alembic downgrade b3mesureecrans` d'abord**, sinon l'ancien code ne lit plus les marchés déposés.
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

- **D10 « partie (lot n) »** : hors de ce chantier (A1 = adresses et étapes).
- **Mes marchés en liste filtrable, une seule fenêtre d'invitation, « Qui me complète ? » unique, « Prêt à déposer »
  pour l'entreprise seule, Mon entreprise en onglets, Mes documents** : autres chantiers de la vague 2a. Mes marchés
  garde ici son tableau par colonnes, une par étape de l'axe.
- **Un menu latéral sans les 4 rubriques de la barre basse sur téléphone** : le menu complet reste derrière « Menu »
  (aucune entrée qui apparaît ou disparaît selon l'écran).
- **Passage automatique « À venir » → « Repéré » à la publication** : il demande de relier une fin de contrat à son
  nouvel avis (Moteur, Veille) ; d'ici là, le choix « Statut ».
- **Le stepper de 5 étapes côté partenaire** (`invite.html`, dossier partagé) : vague 2b.
