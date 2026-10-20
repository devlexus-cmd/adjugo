# Réorganisation de l'interface : vague 2b, « prise en main et partenaire »

Contrat de la vague 2b. Étude : « Réorganiser l'interface d'Adjugo : étude définitive » (12/10/2026), § 6, 7, 9
(vague 2b), 10 et 11. Base : `feat/produit-acheteur-collectivites` = `0afc1ed` (production du 20/10/2026 : vagues 0,
1 et 2a, contrats `docs/REORGANISATION_V1.md` et `docs/REORGANISATION_V2A.md`). Tête Alembic : `c4montantseul`.

Décisions de la vague (recommandations de l'étude) : D12 (a) garder le blocage tant que l'email n'est pas confirmé et
le rendre vivant ; D13 (a) un marché d'exemple entièrement fictif et dit comme tel ; D15 (a) l'espace du partenaire sans
compte réduit à sa part, avec un seul encart « Créer mon compte ». D14 (offres, tarifs) est réservée à Eliot : aucun
contrôle d'offre, aucun prix, aucune carte d'offre ni la vitrine ne changent.

Convention commune aux chantiers : le marché d'exemple vit à l'adresse `/app/exemple` (écran « exemple », ouvert par
`go('exemple')` ou un lien vers `/app/exemple`) ; l'aperçu « Voir ce que verra [partenaire] » vit sur la page du marché
(`/app/marches/<id>/apercu-partenaire`). Les chantiers qui ne les construisent pas y renvoient seulement par ces adresses.

| Chantier | Contenu | Section |
|---|---|---|
| **B3** espace partenaire | L'espace du partenaire réduit à « Votre part dans [marché] », avec la même barre d'étapes, dans ses deux mises en œuvre (dossier partagé de l'application, `invite.html`) ; un seul encart « Créer mon compte » ; « Voir ce que verra [partenaire] » sur la page du marché (§ 6, § 7.6, D15 a) | § B3 |

---

## B3. L'espace du partenaire

Étude : § 6 (lignes « Avant d'inviter » et « Le partenaire reçoit l'invitation »), § 7.6 (côté partenaire), § 9 (vague
2b, deux dernières lignes), § 11 (décision 15 a). Tests : `tests/test_reorganisation_v2b_espace_partenaire.py` (20
tests). Postgres : `scratchpad/b3/run_b3_pg.py` de la session (§ B3.7). **Aucune migration** ; **une route nouvelle, en
lecture** : `GET /api/projects/{id}/apercu-partenaire` (§ B3.4) ; `GET /api/public-config` gagne `essai_jours`.

### B3.1 « Votre part dans [marché] », dans les deux mises en œuvre

Le partenaire a le même écran, qu'il ait un compte (vue `sharedao` de l'application, `/app/marches/partenaire/<id>`) ou
non (`invite.html`, `/invite/<jeton>`) :

| | Avant | Après |
|---|---|---|
| En-tête | « Partagé par [chef de file] », nom du marché | « Chef de file : [nom] » puis le titre « Votre part dans « [marché] » » (titre de l'onglet du navigateur dans `invite.html`), l'acheteur, le compte à rebours et les faits du marché |
| Étapes | Le stepper des 5 étapes du groupement (« Étape 2 sur 5 · … ») | **La même barre que la page du marché du chef de file** (`.mk-etapes`), avec les tâches du partenaire : **Accepter · Ma part · Donner mon accord · Déposé par le chef de file** |
| Titre de l'écran (application) | « Dossier partagé » | « Votre part » ; bulle : « Le marché d'une autre entreprise, où vous apportez votre part » |
| Ordre (les deux) | — | en-tête et faits · barre · « Comment vous serez noté » · « Pourquoi vous dans ce groupement » · convention · rédaction · pièces partagées · ma part · tableau de prix · coffre-fort croisé · journal · décliner |

**La barre** : une seule fonction pure, `barrePartenaire(d)`, **mot pour mot la même** dans `app.js` et dans
`invite.html` (vérifié par les tests). Trois statuts, comme la barre du chef de file : Terminé · En cours · À faire.
Elle ne lit que ce que l'écran du partenaire a déjà reçu :

| Étape | Terminée quand | Absente |
|---|---|---|
| Accepter | l'invitation n'est pas en aperçu limité (réseau accepté depuis le compte, ou lien direct) | — |
| Ma part | sa part est soumise (la barre suit chaque enregistrement) | lien en lecture seule (aucune part demandée) |
| Donner mon accord | convention validée par tous, ou à valider avec son accord donné (en ligne ou hors ligne) ; une convention périmée la remet « En cours » | sous-traitant (il ne valide pas la convention) |
| Déposé par le chef de file | le chef de file a marqué le dépôt (étape « depose » du groupement) : tout passe à « Terminé » | — |

Un clic sur une étape amène à son bloc et y met le focus (l'en-tête, « Ma contribution », la convention) : des ancres,
sans blocage, comme chez le chef de file. Les libellés du partenaire étant plus longs, chaque étape est en colonne
(numéro, mot, statut) à toutes les largeurs ; 3 colonnes quand il y a 3 étapes. Le stepper des 5 étapes du groupement
quitte ses deux dernières places (`grpSteps`, `grpEtapeNow`, `renderEtapes`, `SOON_STEPS`, `.cv-steps`).

**Toutes les fonctions du partenaire restent** et marchent comme avant (vérifié dans le navigateur, § B3.7) : la part
(entreprise, partie, identité pour les formulaires, références, qualifications, prix de vente de sa partie), le détail du
chiffrage chiffré dans son navigateur avec le code de vérification et le code de récupération, les pièces
administratives (dépôt privé), le tableau de prix, la rédaction de ses parties du dossier de présentation et l'entretien
(`redaction-partenaire.js`, monté tel quel), la convention et son accord, le coffre-fort croisé, le journal vérifiable,
« Accepter depuis mon compte » et « Ouvrir dans mon Adjugo », « Décliner l'invitation ».

**Dans `invite.html`**, « Pourquoi vous dans ce groupement » et les membres du groupement passent dans leur propre carte,
sous la barre (ils étaient dans l'en-tête, avant les faits du marché) ; contenu inchangé.

**Constaté dans le navigateur et corrigé** : dans le dossier partagé de l'application, après « Soumettre au chef de
file », la page entière glissait de 121 px vers le haut (une bande noire en bas) : un texte pour lecteur d'écran
positionné hors de la zone qui défile allongeait la page (déjà vrai en production). Les deux écrans de ce chantier
contiennent maintenant leurs éléments positionnés (`.pa-vue { position:relative; }`) : la page ne déborde plus.

### B3.2 `invite.html` : un seul écran, un seul encart (décision 15 a)

**Retirés** : le menu latéral et ses groupes (« Votre invitation », « Avec un compte Adjugo », « Réglages »), le menu
fermé à cadenas (`renderBlocked`, « « … » est réservé aux membres »), l'entrée « Projets à venir », qui affichait en
fait la recherche de marchés (étude, § 7.6), la recherche de marchés elle-même (`renderSourcing`, son bandeau « Analyser
ce marché »), le bouton « Créer mon compte Adjugo » de l'en-tête et la bulle « débloquer tout l'espace ».

**L'en-tête** : la marque et « Espace partenaire », à droite l'entreprise invitée et son rôle (« Partenaire invité »,
« Sous-traitant invité », « … · lecture seule »). Marge de 16 px sur téléphone.

**Un seul encart « Créer mon compte Adjugo »** (`renderCompte`), en bas de la page, après la part et le journal :

> Votre part à ce marché ne demande pas de compte. Avec un compte, vous cherchez aussi les marchés publiés, vous
> préparez vos propres réponses, seul ou à plusieurs, et vous gardez vos pièces au même endroit.
> **Essai gratuit de N jours, sans carte bancaire.** — bouton « Créer mon compte » (`/app?inscription`, nouvel onglet)

- **N est lu dans le code**, jamais écrit dans la page : `GET /api/public-config` renvoie `essai_jours`
  (`app/core/quota.py`, `TRIAL_DAYS`, 30 aujourd'hui). Sans réponse du serveur, la ligne de l'essai n'apparaît pas.
- Bulle (i) : « À la fin de l'essai, les fonctions d'IA se mettent en pause tant qu'aucun forfait n'est choisi. Vos
  marchés, vos documents et vos dossiers restent accessibles. » (la règle de `quota.MSG_ESSAI_TERMINE`).
- Pas d'encart pour une invitation du réseau en aperçu limité (elle est envoyée à un compte Adjugo, qui l'accepte depuis
  son compte) ni quand un compte Adjugo est ouvert dans ce navigateur (« Ouvrir dans mon Adjugo » est proposé).
- Un seul lien vers l'inscription dans toute la page ; aucune offre, aucun prix (D14 réservée).

### B3.3 « Voir ce que verra [partenaire] » (étude, § 6, « Avant d'inviter »)

**Les entrées**, avant et après l'invitation :

| Où | Libellé | Ouvre |
|---|---|---|
| Page du marché, sous « Inviter un partenaire » | « Voir ce que verra votre partenaire » | l'invitation encore ouverte la plus récente, sinon un partenaire pas encore invité |
| Page du marché, liste des invitations | icône œil, « Voir ce que voit [entreprise] » (sauf révoquée ou déclinée) | cette invitation |
| Fenêtre d'invitation, avant l'envoi | « Voir ce que verra [nom saisi] » | un partenaire pas encore invité, **avec les choix de la fenêtre** (rôle, réseau Adjugo, pièces du marché, part) ; « Revenir à l'invitation » rouvre la fenêtre telle qu'on l'a laissée |
| Fenêtre d'invitation, invitation créée | « Voir ce que voit [nom] » | l'invitation créée |

**Les adresses** : `/app/marches/<id>/apercu-partenaire` (pas encore invité) et
`/app/marches/<id>/apercu-partenaire/<n° de l'invitation>` (jamais son jeton). Un écran de la rubrique Mes marchés (titre
« Ce que verra votre partenaire »), compté par la mesure d'usage (`apercu`). « Retour au marché » fait comme le bouton du
navigateur ; ouvert par un lien, il ouvre la page du marché. Le choix « Aperçu pour » (un partenaire pas encore invité,
ou une invitation du marché) change l'adresse sans nouvelle entrée d'historique ; pour un partenaire pas encore invité,
on choisit : partenaire du groupement ou sous-traitant, invité par le réseau Adjugo, pièces du marché téléchargeables.

**L'écran**, dans un cadre « Son écran, en lecture » : son en-tête (« Chef de file : … », « Votre part dans « … » »,
l'acheteur), l'aperçu limité d'une invitation du réseau pas encore acceptée, le compte à rebours, les faits du marché, sa
barre (une liste en lecture seule, sans bouton), la grille « Comment vous serez noté », **« Ce qui est attendu de
vous »** (accepter depuis son compte pour le réseau ; sa part : le prix de vente de sa partie, ses références et son
paragraphe ; ses pièces administratives, la liste de son coffre-fort croisé ; son accord sur la convention, ou « Vous
intervenez en sous-traitance : vous n'avez pas à valider la convention de groupement »), **le total de l'offre commune
quand il le voit**, les pièces partagées (leurs noms) et une note sur sa part (« le détail de son chiffrage est chiffré
dans son navigateur : ni vous, ni Adjugo, ni l'IA ne pouvez le lire »). Une seule bulle (i). Une invitation révoquée,
déclinée ou expirée : « [entreprise] ne voit plus ce marché » et la raison, rien d'autre.

### B3.4 Le cloisonnement : rien de plus que ce que reçoit le partenaire

`GET /api/projects/{id}/apercu-partenaire?invite_id=<n°>`, ou, pour un partenaire pas encore invité,
`?role=cotraitant|sous_traitant&reseau=…&can_view_docs=…&can_contribute=…&nom=…`.

- **Réservée à l'organisation du marché** (`_owned_project`, comme la liste des invitations) : le partenaire, un tiers
  reçoivent 404 ; une invitation d'un autre marché, 404 ; sans session, 401.
- **Tirée de la vue du partenaire** : la même fonction que `GET /api/invite/{jeton}` (`_invite_public`, avec les mêmes
  pièces, `_documents_partages`), puis une **liste fermée** de champs (`_apercu_de`) :

| Champ | Ce que c'est |
|---|---|
| `project` : `name`, `client`, `deadline`, `source_url`, `analysis` | le marché tel que le partenaire le voit (aperçu limité : ni acheteur, ni lien de l'avis, ni grille) |
| `mandataire` | le nom du chef de file |
| `invited` : `company`, `role` | l'entreprise invitée et son rôle (le chef de file les a saisis) — **jamais son adresse** |
| `can_view_docs`, `can_contribute`, `apercu_minimal`, `apercu_message` | les droits du lien, l'aperçu limité |
| `documents` : `name`, `folder` | les pièces du marché qu'il peut télécharger, nommées — ni identifiant ni lien |
| `for_member.state` : `state`, `offer_frozen`, `total_offre_ht`, `frozen_at` ; `warning_two_members` | l'étape du groupement et **le total de l'offre commune, seulement quand le partenaire le reçoit** (membre du groupement, signataire de la convention générée ; jamais un sous-traitant) |
| `etat` : `part`, `convention`, `signature` | l'état de SA part (une part du réseau sans réponse reste cachée, `_owner_hides_part`), le statut de la convention et son accord : ce que le chef de file voit déjà |
| `pieces_attendues` | la liste des pièces de son coffre-fort croisé (`_pieces_attendues`, la même fonction que `coffre_croise`) |

- **Jamais** : la décomposition du prix du chef de file (chiffrage, lignes, part du chef de file), la matière d'un
  autre membre (composition du groupement, parts, prix, capacités, score commun, apports), ni une donnée du partenaire
  que le chef de file ne voit pas déjà (son adresse, son brouillon pendant l'aperçu limité, son prix et ses capacités ne
  sont pas repris), ni aucun jeton.
- **Lecture seule** : ni compteur de vues, ni journal, ni invitation créée (une invitation pas encore envoyée est
  calculée sur un objet jamais ajouté à la session). Une invitation neuve n'a ni part ni accord et défige une offre :
  l'aperçu ne montre alors aucun total.
- **L'écran ne lit que cette réponse** : le gabarit ne lit rien de la page du marché du chef de file (vérifié sur ses
  expressions) ; la seule autre route lue est la liste des invitations du marché (le choix « Aperçu pour »).

### B3.5 Le code

- `app/routers/invites.py` : `apercu_partenaire` (route), `_apercu_de`, `_APERCU_PROJET`, `_pieces_attendues`,
  `_raison_sans_acces`, `_documents_partages` (extraite de `guest_view`, inchangée) ; `coffre_croise` lit
  `_pieces_attendues`.
- `app/main.py` : `essai_jours` dans `/api/public-config`.
- `app/services/mesure_usage.py` : écran `apercu`.
- `app/static/app.js` : `barrePartenaire` (fonction pure), `ADRESSE_APERCU`, `adresseDe` / `etatDeAdresse`,
  `adresseCourante`, `_appliquerAdresse` (écran `apercu`, retour à la page du marché sans tout recharger), `_apercuInit`,
  `apercuOuvrir`, `apercuDepuisMarche`, `apercuInvitation`, `rinvApercu`, `apercuCharger`, `_apercuInvitations`,
  `apercuChoisir`, `apercuOption`, `apercuRetour`, `apercuReprendre`, `apercuBarre`, `apercuPieces`, `apercuTotal`,
  `apercuRaison`, `paJours`, `paDelai`, `sharedBarre`, `sharedBarreAller` ; `rinv.inviteId` ; titres et bulles ;
  `grpSteps` et `grpEtapeNow` retirés.
- `app/static/app.html` : en-tête et barre du dossier partagé (`partage-barre`), lien de l'en-tête du marché
  (`marche-apercu`), œil de la liste des invitations, deux liens de la fenêtre d'invitation, écran de l'aperçu
  (`vue-apercu-partenaire`, `apercu-choix`, `apercu-ecran`, `apercu-attendu`, `apercu-offre`, `apercu-sans-acces`).
- `app/static/invite.html` : un seul écran (`renderMonAO`), `barrePartenaire`, `renderBarre`, `barreAller`,
  `renderCompte`, `ESSAI_JOURS` ; « Pourquoi vous » dans sa carte ; menu, `renderBlocked`, `renderSourcing`, `nav`,
  `setActive`, `renderEtapes` retirés.
- `app/static/styles.css` : bloc « L'espace du partenaire » (`.pa-*`, `.mk-apercu`, `.rinv-apercu`).
- `app/static/i18n.js` : 636 → 687 clés (néerlandais et espagnol) ; `sri-manifest.json` et empreintes de `app.html`.

### B3.6 Tests

Nouveau : `tests/test_reorganisation_v2b_espace_partenaire.py` (20 tests) — aperçu d'une invitation inclus valeur pour
valeur dans la vue du partenaire, avant et après sa part, sans compteur ni journal ni création ; avant l'invitation
(partenaire, sous-traitant, réseau), puis comparé à la vue de l'invitation réellement créée ; réseau : ni adresse ni
brouillon pendant l'aperçu limité, puis dossier complet une fois accepté ; total de l'offre commune seulement quand le
partenaire le voit ; réservé au chef de file, lien révoqué ou décliné ; démonstration (Kerhel) ; le gabarit de l'aperçu
ne lit que la réponse de l'aperçu ; les entrées ; la fenêtre d'invitation passe ses choix (sous Node) ; adresses et
retour (sous Node) ; même barre dans les deux espaces, ses états (sous Node) ; dossier partagé réduit à « Votre part »
avec toutes ses fonctions ; `invite.html` réduit à sa part avec un seul encart, même ordre que l'application ; durée de
l'essai du serveur ; vocabulaire, mots bannis, zéro émoji, « vérifié » absent ; traductions ; 375 px et accessibilité ;
repères.

Mis à jour, chacun avec sa raison en commentaire : `test_reorganisation_v1_reunion.py` (le test du menu fermé à
cadenas devient « espace partenaire sans menu, réduit à sa part »), `test_reorganisation_v1_socle.py` (repères de B3 ;
un seul lien vers l'inscription ; plus de menu), `test_reorganisation_v1_menu.py` (écran `apercu`, page de détail du
marché ; titre « Votre part »), `test_reorganisation_v1_marche.py` (le stepper a quitté aussi le dossier partagé),
`test_reorganisation_v2a_adresses_etapes.py` (adresse de l'aperçu), `test_correctifs_urgents.py` (durée de l'essai lue
dans la configuration ; plus d'entrée « Projets à venir »), `test_secu_cotraitance.py` (la recherche, troisième lien
construit depuis une donnée, a quitté la page : tout lien passe par `safeUrl` ou est un chemin interne fixe).

### B3.7 Vérifications

- **Suite complète** verte (SQLite, `TZ=UTC`) : 2 225 tests ; `scripts/sri_update.py --check` ; `node --check` de `app.js` et du script
  d'`invite.html` ; gabarit Vue compilé (test existant) ; `scripts/i18n_ajouter.py --check` (687 clés).
- **Les nouveaux tests sur le code de production `0afc1ed`** (copie par `git archive`) : le fichier ne se charge pas
  (le repère de l'écran de l'aperçu n'existe pas) ; ses 20 tests échouent donc tous.
- **Postgres 16.2 depuis l'état exact de la production** (`scratchpad/b3/run_b3_pg.py`) : base montée par le code
  `0afc1ed` (tête `c4montantseul`) et remplie par lui (chef de file, partenaire avec compte, deux marchés, une pièce du
  marché, un chiffrage détaillé du chef de file, invitations d'un partenaire, d'un sous-traitant et d'un lien en lecture
  seule, deux parts soumises, offre commune figée) ; code nouveau : une seule tête, « upgrade head » ne change rien,
  schéma identique ; sur ces données : chaque aperçu inclus valeur pour valeur dans la vue du partenaire, aucune clé ni
  valeur interdite, pièces attendues = son coffre-fort croisé, total pour le partenaire et pas pour le sous-traitant,
  aperçus « pas encore invité » (partenaire, sous-traitant sans pièces, réseau limité sans acheteur), aucun compteur ni
  journal ni invitation créés, 404 au partenaire et pour une invitation d'un autre marché, `essai_jours` = 30, page du
  partenaire servie sans menu ; le code de production relancé lit et écrit ; tests communs sur Postgres : mêmes échecs
  avec le code de production et le code nouveau ; le fichier du chantier, sur une base à part. **29 contrôles sur 29** ;
  16 fichiers communs : mêmes échecs des deux côtés (15 contre 15, tous dans `test_secu_rgpd.py` : son
  `PRAGMA foreign_keys=ON` propre à SQLite, déjà noté en vague 2a et en B4) ; le fichier du chantier : 20 sur 20.
- **Navigateur réel** (serveur local sur le code du chantier, base jetable, réseau sortant, courriels et IA coupés,
  comptes de test locaux créés par un script, jetons jamais affichés ; démonstration par lien privé avec une clé jetable
  de 48 caractères écrite dans un fichier, `DEMO_PUBLIC=0`) :
  - chef de file : « Voir ce que verra votre partenaire » depuis la page du marché, « Aperçu pour » (sous-traitant :
    3 étapes et pas de pièces ; partenaire sans compte : pièces partagées ; pas encore invité, puis « Invité par le
    réseau Adjugo » : aperçu limité), « Retour au marché », fenêtre d'invitation « Un partenaire que je connais » →
    « Voir ce que verra Menuiserie… » → « Revenir à l'invitation » (choix retrouvés) → « Créer le lien » → « Voir ce
    que voit … », précédent du navigateur, ouverture directe par l'adresse `/apercu-partenaire/<n°>` ;
  - partenaire avec compte : Mes marchés › Où je suis partenaire › « Votre part dans … », barre, « Donner mon accord »
    mène à la convention, saisie du prix et « Soumettre au chef de file » : la barre passe « Ma part » à Terminé et
    « Donner mon accord » à En cours ; la page ne glisse plus (§ B3.1) ;
  - partenaire sans compte (`invite.html`) : un seul écran, la barre, « Ma part » mène à sa part, « Enregistrer le
    brouillon », l'encart « Créer mon compte » en bas avec « Essai gratuit de 30 jours » lu du serveur, un seul lien
    vers l'inscription, aucun appel à la recherche de marchés ; sous-traitant : 3 étapes ;
  - démonstration (vitrine) : « Espace entreprises », page de Kerhel, « Voir ce que verra votre partenaire » (Breizh
    Désamiantage : 4 étapes, 3 terminées, offre commune figée 1 250 000 € HT, pièce du marché), sans erreur de script ;
  - 1 024, 1 280 et 375 px (aucun défilement horizontal, la page ne déborde pas), sombre et clair.

### B3.8 Pour la réunion des chantiers

- **B4 (courriel d'invitation)** : le courriel mène à « Votre part dans « [marché] » » (titre retenu ici, inchangé) ; sa
  liste « Ce que vous verrez » (« le résumé du marché, les pièces que [chef de file] partage avec vous et votre part ») dit
  la même chose que l'écran et que l'aperçu.
- **B2 (marché d'exemple)** : l'écran du partenaire de l'exemple peut reprendre la même structure (« Votre part dans … »,
  `barrePartenaire`, « Ce qui est attendu de vous »), sans appeler la route de l'aperçu (l'exemple n'a pas de marché en
  base).
- **Zones communes à fusionner bloc par bloc** : `RUBRIQUES` (liste `vues` de Mes marchés : `apercu`), `titles` et
  `subtitles`, `ECRANS` de `mesure_usage.py`, `adresseDe` / `etatDeAdresse` / `_appliquerAdresse` (écran `apercu` à côté
  d'`exemple`), `/api/public-config` (`essai_jours`, peut-être aussi lu par la confirmation d'email), `i18n.js` (une
  seule ligne : réunir les clés, puis `scripts/i18n_ajouter.py --check`), `sri-manifest.json` et les empreintes
  d'`app.html` (à recalculer après la réunion), `styles.css` (bloc en fin de fichier).

### B3.9 Pour Eliot

Rien à régler : pas de variable, pas de migration. La durée d'essai affichée au partenaire suit `TRIAL_DAYS` ; si elle
change, l'encart suit.

### B3.10 Laissé, avec sa raison

- **`POST /api/invite/{jeton}/search`** (la recherche de l'ancien menu) : gardée côté serveur. Une page de partenaire
  ouverte avant la mise en ligne l'appelle encore jusqu'à son rechargement ; l'inventaire de `test_demo_sans_cout.py` la
  liste. À retirer dans un second temps, avec son test.
- **Le prix du partenaire dans l'aperçu** : l'étude (§ 6) évoque « son prix chez lui » ; la consigne du chantier limite
  l'aperçu au marché, au chef de file, à la date limite, à ce qui est attendu et au total commun. Le chef de file voit
  déjà ce prix dans la carte des parts ; l'aperçu ne l'ajoute pas.
- **Le compte à rebours** (« Il vous reste N jours pour soumettre votre part ») reste affiché une fois la part soumise,
  comme sur l'écran du partenaire depuis la co-traitance v2 : l'aperçu montre ce que voit le partenaire, sans le
  corriger ici.
- **« Chargement du dossier partagé… » / « Dossier inaccessible »** (attente et erreur de la vue `sharedao`) : libellés
  inchangés.
