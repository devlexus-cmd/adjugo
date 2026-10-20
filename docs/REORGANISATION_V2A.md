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
  Abandonné), chaque groupe avec son nombre de marchés. Deux sortes de cartes :
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
