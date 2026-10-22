# Mise en ligne du 22/10/2026

Ce document est pour Eliot. Il dit ce que la prochaine mise en ligne change pour les clients, ce qu'elle corrige,
ce qu'il reste à décider avant, comment la faire et la défaire, et ce qui a été vérifié.

**Ce qui part.** Trois chantiers, finis et vérifiés chacun de son côté, ont été réunis sur la branche de cette
réunion, au-dessus de la production actuelle (`feat/produit-acheteur-collectivites` = `0afc1ed`, mise en ligne le
20/10), puis la partie écran du lot 1 du moteur posée au-dessus (quatrième ligne) :

| Chantier | Commit | Contrat (le détail) |
|---|---|---|
| Réorganisation de l'interface, vague 2b : prise en main, marché d'exemple, espace du partenaire, courriel d'invitation | `52e0d59` | `docs/REORGANISATION_V2B.md` |
| Moteur de recherche, lot 1 « Dire juste », partie serveur | `723c9cc` | `docs/MOTEUR_LOT1.md` |
| Suite de tests verte sur PostgreSQL (rien ne change pour les clients) | `8b66841` | `docs/TESTS_POSTGRES.md` |
| Moteur de recherche, lot 1 « Dire juste », partie écran (ajoutée le 22/10, au-dessus de `0f8eb32`) | `ba07980`, puis sa revue (le commit qui suit `ba07980`) | `docs/MOTEUR_LOT1.md`, section « Écran » (et « Revue ») |

**Ce qui ne part pas.** Les pages annexes du site public (`/plateforme`, `/profils/…`, `/secteurs/…`, `/faq`)
restent hors de cette mise en ligne tant que vous n'avez pas relu leurs textes. Une branche à part,
`reunion-22-10-avec-annexes`, prouve seulement qu'elles s'ajoutent sans rien casser (section 5).

**Rien n'a été mis en ligne ni poussé.** Aucune variable nouvelle sur Railway. Une seule migration de base de
données, `c5priseenmain` (section 4).

**Vos décisions du 22/10 sont appliquées** (section 3, décisions 1 à 3, et section 5, « Décisions d'Eliot ») : le
repli payant de « À venir » est remboursé en outre-mer et en Corse ; aucun courriel planifié ne part vers une adresse
non confirmée ; la bulle (i) de « Mes alertes » est corrigée.

---

## 1. Ce qui change pour les clients, écran par écran

### Inscription et confirmation de l'adresse

- L'écran « Confirmez votre adresse email » reste bloquant, mais il se met à jour tout seul : il revérifie la
  confirmation toutes les 5 secondes, puis plus lentement, seulement quand l'onglet est visible, et tout de suite
  quand on revient sur l'onglet. Le lien cliqué sur le téléphone ouvre donc l'application sur l'ordinateur sans
  rien faire.
- Il dit la suite : « Une fois confirmé, vous entrez votre SIRET et vous voyez les marchés de votre zone ». Le
  courriel de confirmation dit la même phrase, seulement quand c'est vrai (entreprise sans SIRET).
- Les réponses de « Renvoyer l'email » et de « J'ai cliqué sur le lien » s'affichent enfin dans l'écran. Avant,
  elles passaient dessous et restaient invisibles.
- **Tant que l'adresse n'est pas confirmée, Adjugo ne lui envoie aucun courriel planifié** (décision 2, prise le
  22/10) : ni alerte de marchés, ni « Demandez vos notes », ni récapitulatif « pièces à renouveler ». Rien n'est marqué
  envoyé : ils partent au premier passage après la confirmation, « Demandez vos notes » seulement dans les 14 jours qui
  suivent le passage du marché à « Perdu ». Une exception, rare : le récapitulatif des attestations des partenaires
  d'un marché créé par un collègue non confirmé n'arrive qu'au palier suivant (section 3, décision 2). En production,
  ces trois courriels partaient vers une adresse non confirmée (section 2, point 3) ; avant cette décision, le code
  réuni ne retenait que l'alerte de marchés. Les courriels que le compte demande lui-même (confirmation, mot de passe
  oublié) partent comme avant. Qui n'a pas d'adresse confirmée :
  - **un compte qui change d'adresse** redevient non confirmé ; il ne reçoit plus rien jusqu'à ce qu'il confirme la
    nouvelle. C'est le seul cas où la décision retire des courriels à un client ;
  - **un compte qui vient de s'inscrire**, jusqu'au clic sur le lien reçu ;
  - **un collègue invité depuis Réglages › Collègues** (« Inviter un collègue »). Son compte est créé non confirmé, et
    aucun lien de confirmation ne lui est envoyé, ni à l'invitation (le courriel d'invitation ne porte que son mot de
    passe provisoire), ni à la connexion. À sa première connexion, l'écran « Confirmez votre adresse email » le bloque
    jusqu'à ce qu'il clique « Renvoyer l'email de vérification », puis le lien. C'est ainsi en production, inchangé.

  Comme tout compte non confirmé, un compte qui vient de s'inscrire ou un collègue invité ne peut rien créer depuis
  l'application avant d'avoir confirmé (ni alerte, ni marché, ni pièce) : l'écran couvre tout depuis le 24/06. La
  décision ne lui retire donc aucun courriel, en production il n'en recevait pas non plus. L'écran dit pourtant au
  collègue invité « Un lien de confirmation vous a été envoyé par email », ce qui est faux pour lui (section 3,
  « Plus tard »).

### Fenêtre du SIRET et « Ce que je cherche »

- Nouvelle question facultative : « Jusqu'à quel montant répondez-vous seul ? », avec la réponse
  « Je ne sais pas ». La même case « Je ne sais pas » existe dans Mon entreprise › Ce que je cherche. Ce montant
  n'entre dans aucun calcul.
- Un montant trop grand est refusé dans la fenêtre, avec un message. Le bandeau des cookies ne passe plus
  par-dessus la fenêtre.
- **La zone tirée du code postal suit la règle du serveur** (revue de la réunion) : outre-mer sur 3 chiffres
  (« 97400 » donne « 974 » ; avant, « 97 », qui couvre tout l'outre-mer), Corse « 2A, 2B » (avant, « 20 », qui ne
  trouve aucun avis du BOAMP). La fenêtre du SIRET l'enregistre dans Ce que je cherche. « Chercher » des
  partenaires prend aussi « 974 » ; la Corse y reste « 20 », comme avant.
- **Le champ « Départements » de Trouver des marchés suit la même règle pour toutes les entreprises, inscrites
  avant ou après la mise en ligne** (contre-relecture de la réunion). Il est pré-rempli depuis le code postal de
  Mon entreprise quand on ouvre Trouver ou qu'on clique « Voir les marchés pour mon entreprise », et c'est lui que
  les onglets Publiés et À venir envoient. Une entreprise de La Réunion y lit donc « 974 », une entreprise corse
  « 2A, 2B », dès la mise en ligne. Seule la zone déjà enregistrée dans Ce que je cherche n'est pas réécrite : une
  entreprise inscrite avant y garde « 97 » ou « 20 ». Cette zone sert à la note d'adéquation, jamais au champ de
  Trouver (décision 1).

### Accueil

- **« Vos premiers pas »** remplace « Premiers pas sur Adjugo ». La liste compte cinq tâches, chacune cochée
  d'après ce qui a été fait dans Adjugo, jamais à la main : dire ce que vous faites et où, ajouter 3 marchés à
  Mes marchés, lire le dossier d'un marché, inviter un partenaire ou vous faire trouver, ajouter vos 3 derniers
  dossiers de présentation. Elle reste 30 jours après la création du compte. On peut la replier, et ce choix est
  gardé sur le serveur, donc aussi sur un autre appareil.
- Un compte créé il y a plus de 30 jours ne voit pas la liste. L'ancienne liste disparaît pour tous, y compris
  pour les 7 PME en test.
- « À faire » n'écrit « Rien n'attend de réponse de votre part » qu'après avoir vraiment lu les pièces à
  renouveler et les invitations reçues. Une relecture en panne garde la liste déjà lue.
- La carte « Faites-vous trouver pour des groupements » est gardée sur le serveur : fermée une fois, elle reste
  fermée sur tous les appareils.
- Les écrans vides proposent un chemin direct, par exemple « Voir un exemple » ou le rappel de la tâche à faire.
  Aucun ne promet une fonction qui n'est pas en ligne.

### Trouver des marchés › Publiés (la recherche)

- **Mégalis** : les cartes montrent enfin leur date limite. Avant, elles affichaient « limite non précisée » (10
  sur 10 sur la page réelle du 21/10). L'ordre des cartes Mégalis peut donc bouger un peu : leur note change, mais
  n'est plus affichée (partie écran, plus bas).
- **Avis rectifiés du BOAMP** : la carte montre la nouvelle date limite. Un avis repoussé reste visible après son
  ancienne date, et un avis européen rectifié n'apparaît plus deux fois. Si la nouvelle date ne peut pas être lue
  sans doute, la carte affiche « limite non précisée », jamais l'ancienne date.
- **Avis annulés ou déclarés sans suite** : ils disparaissent.
- **Faux « métier correspondant »** : le vocabulaire interne du BOAMP n'est plus lu comme un code métier.
  Certaines cartes BOAMP descendent dans l'ordre : leur note baisse, mais n'est plus affichée. Une recherche par
  codes CPV ne ramène plus d'avis sans rapport.
- **Outre-mer** : « 974 » ne montre plus les avis de la Guadeloupe ou de la Martinique. C'est ce que cherche
  désormais toute entreprise dont le code postal est à La Réunion, car le champ « Départements » est pré-rempli
  « 974 » (plus haut). La zone de la note est juste pour une entreprise d'outre-mer dont la zone enregistrée dans
  Ce que je cherche est sur 3 chiffres. C'est le cas d'une entreprise inscrite par la fenêtre du SIRET depuis la
  revue de la réunion. « 97 », saisi dans le champ ou enregistré, couvre toujours tout l'outre-mer.
- **Corse** : « 2A » et « 2B » trouvent enfin les avis du BOAMP, qui écrit « 20A » et « 20B ». Le 21/10, 19 avis
  ouverts étaient concernés ; avant, aucun n'était trouvé. Une zone « 20 » ne trouve toujours rien au BOAMP.
- Une recherche fait une ou deux requêtes de plus au BOAMP, soit 0,4 à 0,6 seconde chacune.
- **Partie écran du lot 1 : plus aucun nombre sur la carte.** Ni « confiance N % » (fixée à 70 % pour toute
  consultation Mégalis), ni « adéquation N/100 » : des pourcentages seulement après le dossier (décision 8 de
  l'organisation). L'ordre des cartes ne change pas. Les mots « Bon potentiel », « À étudier », « Peu adapté »
  n'arrivent pas encore : ils attendent le barème corrigé, car aujourd'hui une donnée inconnue avantage le marché.
  Sans métier ni zone dans Ce que je cherche, la carte invite à les dire : « Dites ce que vous cherchez pour un
  classement adapté ».
- **Partie écran : les rectificatifs se voient.** « Date limite repoussée au 06/11/2026 (rectificatif du
  06/10/2026) », le lien mène au rectificatif qui a fixé la date (pas forcément le dernier paru) ; « Date limite non
  précisée (rectificatif du …) », avec une bulle (i), quand sa nouvelle date n'a pas pu être lue, jamais l'ancienne
  (la bulle dit qu'un rectificatif « peut changer » la date limite : le serveur le suppose aussi, par prudence, pour
  des formes jamais observées) ;
  « Avis rectifié (rectificatif du …) » quand la date ne change pas. La date limite s'écrit « 06/11/2026 » (avant,
  « 2026-11-06 »).
- **Partie écran : Mégalis** donne le nom de l'organisme sans « (code postal - ville) » : sur la carte, dans Mes
  marchés pour un marché analysé désormais, et dans le courriel d'alerte. Rien d'autre ne change (fusion avec le BOAMP, note, alertes).
- **Partie écran : « Voir les marchés pour mon entreprise »** cherche le premier métier de Ce que je cherche. Avant,
  il le cherchait dans la fiche Identité, qui ne l'a pas : la recherche partait sans mot, et le BOAMP cherchait
  « travaux » sans le dire. Sans métier, rien n'est cherché : l'écran le demande, avec le bouton « Dire mon métier »,
  qui ouvre Ce que je cherche, le curseur dans « Spécialités ». Avec des codes CPV et aucune spécialité, l'écran dit
  que ces codes seuls ne suffisent pas à ce bouton, qui cherche avec des mots. Les départements sont ceux du champ de
  la recherche, pré-rempli par le code postal et modifiable ; le sous-titre le dit (« … et les départements de la
  recherche ci-dessus »).

### Trouver des marchés › À venir (fins de contrat)

- **Outre-mer** : seules les fins de contrat du département demandé, affiché sur 3 chiffres (« 974 »). L'onglet
  n'envoie que son champ « Départements », pré-rempli ainsi depuis le code postal de Mon entreprise pour toute
  entreprise, déjà inscrite ou non. La zone enregistrée dans Ce que je cherche n'y entre pas : elle ne sert qu'à
  la note des fins de contrat. « 97 » saisi dans le champ garde celles de tout l'outre-mer.
- **Corse et outre-mer, repli payant** : quand la base des marchés attribués (DECP) ne donne rien, le repli par le
  BOAMP et l'IA peut désormais trouver des fins de contrat dans ces deux zones, et l'écran les montre. Dans ces zones,
  l'analyse est **remboursée**, même s'il trouve, jusqu'à ce que l'écran annonce le crédit avant le clic (décision 1,
  prise le 22/10). Avant, il ne trouvait jamais rien, et l'analyse était toujours remboursée : le crédit ne change donc
  pas pour ces entreprises. Une demande qui mêle un département de métropole et un d'outre-mer ou de Corse
  (« 29, 974 ») est remboursée en entier ; en production, elle était débitée si elle trouvait en métropole. Partout
  ailleurs, la règle ne change pas : débité s'il trouve, remboursé sinon.
- « 6 » saisi seul est lu comme « 06 » dans la DECP, sans crédit. Avant, il passait par le repli payant.
- Une durée de contrat que l'IA n'a pas vraiment lue est dite estimée, et non plus « (réelle) » : avec la partie
  écran, « (durée estimée selon le type de contrat) », ou « (durée estimée par défaut, type de contrat inconnu) »
  quand l'IA ne donne pas de type (36 mois).
- Le bouton « Modifier ma zone » met le curseur dans le champ « Départements » de l'onglet, celui qui compte pour
  cette recherche.
- Chaque repli payant laisse une ligne dans le journal du serveur, sans donnée personnelle, que le client ne voit
  pas ; avec la partie écran, l'écran dit après chaque repli si l'analyse a été consommée ou remboursée. En outre-mer et en Corse, elle dit « analyse remboursée (outre-mer ou Corse, jusqu'à l'annonce du crédit à
  l'écran) ».
- **Partie écran : « Fin du contrat estimée le 25/10/2026 (durée publiée) »** au lieu de « Renouvellement ~ … », qui
  montrait une date de republication devinée (la fin moins 120 jours). Au repli payant, la durée est dite « lue dans
  l'intitulé de l'avis », « estimée selon le type de contrat » ou, sans type, « estimée par défaut, type de contrat
  inconnu » (36 mois), et la date est celle de la publication de l'avis d'attribution (« attribution publiée le … »).
- **Partie écran : la bulle (i)** dit la vraie source, « les données publiées des marchés attribués », et, à défaut,
  les avis d'attribution du BOAMP (date de publication de l'avis, durée lue ou estimée) ; elle reste neutre en
  attendant l'avis juridique : « préparez votre réponse et vos partenaires avant la republication » (avant :
  « sources réelles BOAMP » et « positionnez-vous auprès du client »).
- **Partie écran : le crédit est annoncé avant le clic**, sous les champs : « Une recherche complémentaire peut
  consommer 1 analyse : remboursée si elle ne trouve rien, toujours remboursée en outre-mer et en Corse. », avec une
  bulle (i) qui dit quand elle a lieu et ce qu'il faut pour la lancer : une analyse restante, sinon le paiement à
  l'usage activé (forfaits Pro et Business), qui la facture au tarif à l'usage, remboursée dans les mêmes cas. C'est
  la règle du code, inchangée. Un compte Pro ou Business dont les analyses du mois sont utilisées, paiement à l'usage
  activé, lit en plus avant le clic : « Vos analyses du mois sont utilisées : la recherche complémentaire serait
  facturée 5 € (paiement à l'usage), et remboursée dans les mêmes cas. » (le prix est celui du compteur). Après
  un repli, l'écran dit « 1 analyse consommée » ou « analyse remboursée », et le compteur d'analyses se met à jour. La
  démo de pitch, jamais débitée, ne voit pas cette ligne. Le remboursement en outre-mer et en Corse, posé « jusqu'à
  l'annonce du crédit à l'écran », reste en place : à vous de dire s'il continue (section 3, « Plus tard »).

### Trouver des marchés › Mes alertes, et les courriels d'alerte

- **Plus aucun marché écarté par sa note** d'avant le dossier : les courriels contiennent plus de marchés. Sur
  l'alerte réelle « voirie » du Finistère (21/10), 7 marchés partent au lieu de 0.
- Au-delà de 10 marchés dans une alerte, une ligne dit « … et N autres marchés : relancez cette recherche dans
  Adjugo pour les voir tous ».
- Les dates des consultations Mégalis apparaissent dans le courriel.
- Moins de marchés reçus deux fois. Aucun marché déjà reçu n'est renvoyé au passage à la nouvelle mémoire des
  alertes (vérifié depuis une base remplie par la production, section 5).
- **Un compte dont l'adresse n'est pas confirmée ne reçoit plus d'alerte de marchés**, ni aucun autre courriel
  planifié (plus haut, « Inscription et confirmation de l'adresse »). Ses marchés partent au premier passage après la
  confirmation.
- **La bulle (i) de « Mes alertes »** dit désormais, en français, néerlandais et espagnol : « Recevez par email les
  nouveaux marchés de cette recherche, 10 au plus par alerte, les autres comptés. Chaque envoi lit un nombre limité
  d'avis par source (au BOAMP, les 25 derniers publiés) : une recherche très large peut en avoir d'autres, à voir dans
  Adjugo. La recherche de l'onglet « Publiés » est enregistrée telle quelle. » Avant : « … qui vous correspondent
  (au-dessus de votre seuil de compatibilité) », faux depuis ce lot (décision 3, prise le 22/10).

### Mes marchés et la page d'un marché

- **« Voir ce que verra votre partenaire »**, sous « Inviter un partenaire », dans la liste des invitations (icône
  œil) et dans la fenêtre d'invitation, avant et après l'envoi. L'écran montre, en lecture seule, ce que le
  partenaire voit : son en-tête, sa barre d'étapes, ce qui est attendu de lui, le total commun quand il le
  reçoit. Ce n'est jamais plus que ce qu'il reçoit déjà, et rien n'est compté ni enregistré.
- En bas de « Répondre à plusieurs ? », un lien « voir un exemple » mène au marché d'exemple.
- Deux bulles d'aide nouvelles : « Où récupérer le dossier du marché » (étape Lire) et « Comment Adjugo dit seul
  ou à plusieurs » (étape Décider).
- Fenêtre d'invitation : « Autoriser le téléchargement du dossier du marché », au lieu de « des pièces du
  marché » (voir le cloisonnement plus bas).
- **« Chercher » des partenaires et « Répartition proposée »** ne proposent plus que des PME. Les grandes
  entreprises et les ETI n'y apparaissent plus.
- Au rechargement d'une adresse (par exemple `/app/marches/12`), l'accueil ne s'affiche plus une seconde avant la
  page demandée. Le gabarit brut n'apparaît plus avant le chargement.
- **« Offre commune figée le … »** donne le même jour partout : page du marché, « Voir ce que verra votre
  partenaire », espace du partenaire avec ou sans compte. C'est le jour à l'heure de l'ordinateur, comme « Offre
  figée le … à … ». Avant, les trois premiers écrans prenaient le jour UTC : la veille, pour une offre figée entre
  minuit et 2 h, heure de Paris (revue de la réunion).

### Marché d'exemple (`/app/exemple`, nouveau)

- Une page à part, en lecture seule et entièrement fictive. Chaque bloc porte la mention « Exemple · entreprises
  et client fictifs », avec les noms de la démo de pitch. Elle déroule un marché à plusieurs de Lire à Déposer,
  jusqu'à « Seul 43 % · À plusieurs 100 % », puis l'écran du partenaire.
- Elle n'entre jamais dans Mes marchés, les compteurs, le quota ou les alertes.

### L'espace du partenaire (avec ou sans compte)

- Un seul écran, **« Votre part dans « [marché] » »**, avec la même barre que le chef de file : Accepter · Ma
  part · Donner mon accord · Déposé par le chef de file. Un sous-traitant n'a pas l'étape de l'accord. Un lien en
  lecture seule n'a ni « Ma part » ni « Donner mon accord ».
- Sans compte (lien d'invitation) : le menu latéral, le menu à cadenas et la recherche de marchés disparaissent.
  Il reste un seul encart « Créer mon compte Adjugo », en bas, avec la durée d'essai lue dans la configuration
  (30 jours aujourd'hui), sans aucun prix.
- **Le partenaire ne voit et ne télécharge plus que le dossier de l'acheteur** (dossier « DCE »). C'est un défaut
  de production corrigé (section 2).
- Toutes les fonctions du partenaire restent : sa part, le chiffrage chiffré, les pièces, le tableau de prix, la
  rédaction, la convention, le coffre-fort croisé, le journal, « Décliner ».

### Courriels envoyés aux partenaires

- L'invitation, son renvoi et le rappel J-3 / J-1 partent **en HTML avec leur version texte**. Ils nomment le chef
  de file, le marché, la date limite, le rôle et la partie proposée. Ils disent ce qui est attendu et ce que le
  partenaire verra, et mènent à « Votre part dans « … » » par le bouton « Ouvrir votre part ».
- Ils disent ce que reçoit le chef de file : « Votre chiffrage détaillé (coûts, marges, méthode) reste chez vous :
  [chef de file] reçoit le prix de vente de votre partie et, si vous le déposez, votre tableau de prix de vente ».
- Le rappel planifié donne enfin le lien. Avant, il disait « via votre lien Adjugo » sans le donner.
- L'alerte d'attestations au partenaire donne aussi le lien de sa part.
- **Un compte dont l'adresse n'est pas confirmée ne fait plus écrire Adjugo à ses partenaires** : ni rappel de
  la part, ni alerte d'attestations, ni relance des parties du dossier de présentation, ni « Votre partie est à
  valider ». C'est un défaut de production corrigé. Seule exception, comme avant : le code de vérification que
  le partenaire demande lui-même, sans le lien.

### Mes documents › Mon savoir-faire

- L'écran vide dit : « Vos anciens dossiers servent de source au dossier de présentation », avec le bouton
  d'import. La tâche « dossiers » des premiers pas compte les documents du compte, comme l'écran.

### Analyse d'un marché

- Une analyse faite sur l'annonce seule (dossier non accessible) reçoit « DESCRIPTEURS : non précisé » au lieu de
  numéros sans signification. Le crédit débité ne change pas.

### Ce qui ne change pas

Les prix, les forfaits, les quotas et la règle de débit et de remboursement ne changent pas, à une exception près,
en faveur du client : le repli payant de l'onglet « À venir » est remboursé dès que la demande porte sur l'outre-mer
ou la Corse, même avec un département de métropole (décision 1). Aucune offre ni
carte d'offre ne change (décision 14, réservée). Les pages juridiques et la vitrine ne bougent pas, et aucune IA
n'est ajoutée. La démo de pitch est identique, à quelques ajouts près (section 5) ; la partie écran du lot 1 y
retire les nombres des cartes et y change les fins de contrat comme partout (section 5, « Partie écran du lot 1 du
moteur »).

---

## 2. Les défauts de production corrigés

Chacun a été reproduit sur le code de production avant d'être corrigé (le détail et la preuve sont dans les
contrats).

**Cloisonnement et courriels**

1. **Un partenaire téléchargeait des pièces qui ne lui étaient pas destinées.** Après « Préparer mes documents »,
   un sous-traitant téléchargeait `ATTRI1.pdf`, l'acte d'engagement avec le prix de vente de chaque membre. Tout
   partenaire récupérait aussi `DC2.pdf` (le chiffre d'affaires du chef de file) et le dossier de présentation
   assemblé. Désormais, seul le dossier de l'acheteur part. Une autre pièce répond « introuvable », même en
   devinant son numéro. Revérifié pour cette réunion sur une base remplie par la production. (V2B § S.1)
2. **Un compte non confirmé faisait écrire Adjugo à un tiers avec le lien d'invitation.** Cela passait par le
   rappel planifié, la relance des parties du dossier de présentation et « Votre partie est à valider ». Or
   l'adresse d'un compte jamais confirmé peut être celle de n'importe qui. (V2B § S.5, T.1, T.2)
3. **Les alertes de marchés partaient vers des adresses jamais confirmées.** La production a envoyé 5 marchés à
   un tel compte dans la vérification de cette réunion. (Moteur § V.7) « Demandez vos notes » et le récapitulatif
   « pièces à renouveler » y partaient aussi : ils ne partent plus (décision 2 ; reproduit sur `0afc1ed` et sur
   `130fc9e`, section 5, « Décisions d'Eliot »).
4. **Les adresses de la veille masquée « Projets à venir » répondaient** à un appel direct : elles débitaient
   une analyse et appelaient l'IA. Elles répondent maintenant « introuvable », sans rien débiter.
   (Moteur § 7)

**Recherche et alertes**

5. **Mégalis** : 10 dates limites vides sur 10. (Moteur § S.1)
6. **BOAMP** : les rectificatifs étaient ignorés, ce qui donnait l'ancienne date, des avis annulés encore
   affichés et des avis européens en double. Le vocabulaire interne était lu comme un code métier.
   (Moteur § S.2, S.3)
7. **Outre-mer** : le département était coupé à « 97 », donc tous les DOM étaient mélangés. **Corse** : jamais
   trouvée au BOAMP. (Moteur § S.4, 4 bis, R.1)
8. **Alertes** : un tri caché par une note encore faussée écartait des marchés. La mémoire des marchés déjà vus
   était coupée au hasard, si bien que des marchés encore ouverts étaient renvoyés. « Hebdomadaire » partait
   chaque jour. (Moteur § 6)
9. **Recherche de partenaires** : une panne de la DECP était lue comme « 0 marché gagné ». (Moteur § 5 a)
10. Une durée de contrat non lue par l'IA était affichée « (réelle) ». (Moteur § V.6)

**Écrans**

11. **Au rechargement d'une adresse**, l'accueil s'affichait environ 1 seconde avant la page demandée, et le
    gabarit brut s'affichait avant le chargement. (V2B § B1.7)
12. **L'écran de confirmation d'email** cachait ses propres réponses (« Renvoyer » : invisible depuis
    l'inscription). (V2B § B1.6)
13. **Dossier partagé** : après « Soumettre au chef de file », la page glissait de 121 pixels (bande noire en
    bas). (V2B § B3.1)
14. **Tests** : 20 échecs et 24 erreurs sur PostgreSQL, et un test qui échouait certains jours selon la date. Ils
    venaient tous des tests, pas du logiciel. (TESTS_POSTGRES ; V2B § S.14)
15. **Fenêtre du SIRET et champ « Départements » de Trouver** (pré-rempli à l'ouverture de Trouver et par « Voir les
    marchés pour mon entreprise ») : le département du code postal était coupé à 2 chiffres. Une
    entreprise de La Réunion recevait « 97 », donc les avis et les fins de contrat de tout l'outre-mer « dans votre
    zone ». Une entreprise corse recevait « 20 », qui ne trouve aucun avis du BOAMP. Le champ de Trouver est
    corrigé pour toutes les entreprises, la zone enregistrée dans Ce que je cherche seulement pour les nouvelles
    inscriptions. (Revue et contre-relecture de la réunion, section 5)
16. **« Offre commune figée le … »** prenait le jour UTC sur la page du marché et dans l'espace du partenaire avec
    compte. La page du partenaire sans compte prenait le jour local. (Revue de la réunion, section 5)
17. **« Voir les marchés pour mon entreprise »** lisait le métier là où il n'est pas et cherchait « travaux » sans le
    dire. (Moteur § É.11)
18. **Cartes de recherche** : une « confiance 70 % » constante pour Mégalis et une note sur 100 avant le dossier ;
    les rectificatifs, lus par le serveur, invisibles. **À venir** : une date de republication devinée, une bulle qui
    citait la mauvaise source, et un crédit débité sans être annoncé. (Moteur § É.10, É.12)
19. **Page d'exemple de la démo** : elle disait les délibérations « récupérées automatiquement par Adjugo », alors
    que cette veille est masquée. (Moteur § É.13)

---

## 3. Les décisions qui vous reviennent

### Avant la mise en ligne

Les décisions 1 à 3 ont été prises par Eliot le 22/10 et sont appliquées dans le code (section 5, « Décisions
d'Eliot »). Restent les décisions 4 à 7.

1. **Repli payant de l'onglet « À venir » en outre-mer et en Corse.** **Décidé le 22/10 : (b)**, remboursé en
   outre-mer et en Corse jusqu'à ce que l'écran annonce le crédit avant le clic (partie écran du lot, point 12 de la
   note du 21/10). Le choix (a) gardait le débit de partout ailleurs.

   La règle appliquée (`_repli_rembourse_par_zone`, `app/routers/sourcing.py`) : le repli est remboursé, qu'il trouve
   ou non, dès qu'un des départements demandés est en outre-mer (tout code qui commence par « 97 » ou « 98 » :
   « 974 », « 971 », « 988 »…, ou « 97 » saisi seul) ou en Corse (« 2A », « 2B », ou « 20 », celui d'un code postal
   corse), seul ou avec d'autres départements. Les fins de contrat trouvées sont montrées. Le journal du repli payant
   écrit alors « analyse remboursée (outre-mer ou Corse, jusqu'à l'annonce du crédit à l'écran) », qu'il ait trouvé ou
   non. Sans département (toute la France) ou en métropole seule, la règle ne change pas : débité s'il trouve,
   remboursé sinon. Le crédit reste demandé avant le repli, comme avant : un compte sans analyse restante reçoit le
   même refus, sauf au paiement à l'usage (forfaits Pro et Business), où le repli est facturé hors forfait puis
   remboursé de même (revue de la partie écran, section 5). Ce que cela change par rapport à la production : rien pour une demande qui ne porte que sur ces zones
   (le repli n'y trouvait rien et était toujours remboursé) ; une demande mixte (« 29, 974 ») est remboursée en entier,
   alors que la production la débitait si elle trouvait en métropole. C'est le seul écart, et il est en faveur du
   client. Prouvé par `test_d1_repli_a_venir_rembourse_en_outre_mer_et_en_corse`, qui échouait sur `130fc9e`.

   Effet de bord, inchangé : comme la DECP ne mélange plus les DOM entre eux, un département d'outre-mer sans fin de
   contrat déclenche le repli, là où la DECP montrait avant (à tort) celles d'un autre DOM. Ce repli est remboursé.
   (Moteur, points 12 et 12 bis, § R.1 et V.5)

   Qui est concerné (contre-relecture de la réunion) :
   - **toute entreprise dont le code postal (Mon entreprise) est en outre-mer ou en Corse, inscrite avant ou après
     cette mise en ligne**. Le champ « Départements » de « À venir » est pré-rempli « 974 » (par exemple) ou
     « 2A, 2B » depuis ce code postal (`srcPrefillFromProfile`), et non depuis Ce que je cherche ;
   - toute entreprise qui saisit ces codes dans le champ.

   La zone enregistrée dans Ce que je cherche n'y change rien. L'onglet ne l'envoie pas, et le serveur ne la lit
   que pour la note des fins de contrat, jamais pour choisir les départements ni pour décider du repli. Une
   entreprise déjà inscrite par la fenêtre du SIRET y a « 97 » ou « 20 », mais elle passe sous cette règle dès la
   mise en ligne, comme les nouvelles. La portée est fixée par `tests/test_mise_en_ligne_22_10.py` (`test_cr1_a_venir_part_du_code_postal_pour_toute_entreprise_sous_node`,
   `test_cr1_la_route_a_venir_ne_lit_que_le_champ_de_l_onglet`).
2. **Adresses non confirmées : une seule règle.** **Décidé le 22/10 : (b)**, la règle étendue à tous les courriels
   des tâches planifiées vers le compte lui-même, avec la même fonction (`_comptes_non_confirmes`,
   `app/services/alerts.py`). Les choix (a), garder tel quel, et (c), retirer la règle des alertes, sont écartés.

   La règle appliquée : aucune tâche planifiée n'écrit à une adresse non confirmée, qui peut être celle d'un tiers.
   Vers le compte lui-même :
   - ni alerte de marchés (`run_tender_alerts`, déjà en place depuis le moteur) ;
   - ni « Demandez vos notes » (`carnet_notes.envoyer_rappels`), dont le texte dit « parce que vous avez des alertes
     actives » ;
   - ni récapitulatif « pièces à renouveler » (`run_document_expiry_alerts`) ;
   - ni récapitulatif des attestations de ses partenaires (`_piece_alerts_due`, déjà en place depuis la vague 2b) ;
   - ni veille amont (`run_amont_alerts`). Elle est masquée et n'envoie rien aujourd'hui ; si elle est rallumée, elle
     suit la même règle. Ce point n'était pas dans la décision : cette tâche planifiée écrit, elle aussi, au compte
     lui-même, et sans lui la règle n'aurait pas été la seule.

   Vers un tiers, rien ne change : aucune tâche planifiée n'écrit pour un compte non confirmé (vague 2b, section 2,
   point 2). Rien n'est marqué comme envoyé ni « déjà vu » : l'alerte de marchés, « Demandez vos notes » (seulement
   dans ses 14 jours, `COURRIEL_FIN_JOURS`) et le récapitulatif « pièces à renouveler » (avec les pièces dues ce
   jour-là) partent au premier passage après la confirmation. Deux exceptions (relecture des décisions, section 5) :
   - **le récapitulatif des attestations des partenaires d'un marché créé par un collègue** (un membre de l'équipe)
     dont l'adresse n'est pas confirmée, quand le propriétaire du compte l'est. Le partenaire est prévenu quand même,
     et son alerte est notée pour tout le palier, J-7 ou J-3 (`_piece_alerts_due`). Une fois confirmé, le collègue ne
     reçoit pas le récapitulatif de ce palier, seulement celui du palier suivant (J-3), s'il reste des pièces à
     surveiller ; au palier J-3, il n'en reçoit aucun. Quand c'est le propriétaire du compte qui n'est pas confirmé,
     rien n'est noté : tout part après la confirmation, dans le palier en cours. Cas rare, qui suppose un collègue qui
     change d'adresse pendant un palier. C'est ainsi depuis la vague 2b ; le code ne change pas sans votre décision
     (« Plus tard ») ;
   - **la veille amont, si elle est rallumée** : pour une adresse non confirmée, elle n'enregistre pas non plus les
     projets de « Projets à venir ». Après la confirmation, elle ne reprend que les projets encore présents dans les
     délibérations qu'elle lit à ce passage : un projet lu entre-temps et sorti des délibérations récentes n'est
     jamais ajouté pour ce compte, ni envoyé. À trancher au rallumage (« Plus tard »). Aucun effet à cette mise en
     ligne : avec `PROJETS_A_VENIR=0`, la veille s'arrête avant.

   Les courriels que le compte demande lui-même (confirmation de l'adresse, mot de passe oublié) partent comme avant.
   Le cas réel : un compte confirmé qui change d'adresse redevient non confirmé, et la nouvelle adresse peut être une
   faute de frappe. C'est le seul compte à qui la décision retire des courriels. Un compte qui vient de s'inscrire et
   un collègue invité depuis Réglages › Collègues sont aussi non confirmés. Le collègue invité ne reçoit aucun lien de
   confirmation, ni à l'invitation ni à la connexion : l'écran « Confirmez votre adresse email » le bloque jusqu'à ce
   qu'il clique « Renvoyer l'email de vérification ». Mais ni l'un ni l'autre ne peut rien créer depuis l'application
   avant d'avoir confirmé : aucun de ces courriels ne leur était dû en production non plus (section 1). Les comptes
   créés avant la vérification des adresses ont été confirmés par la migration de juin. Le commentaire
   d'`app/routers/auth.py` et la fonction `_comptes_non_confirmes` disent cette règle et ses deux exceptions.

   Prouvé par `tests/test_mise_en_ligne_22_10.py` (`test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte`,
   `test_r1_la_veille_amont_suit_la_meme_regle`), qui échouaient sur `130fc9e`. Le test de la revue
   (`test_r1_adresse_non_confirmee_ce_qui_part_et_ce_qui_ne_part_pas`) fixait l'ancienne règle : il est remplacé. Les
   exceptions et les collègues invités sont fixés par
   `test_d2_le_recapitulatif_des_attestations_d_un_marche_de_collegue_attend_le_palier_suivant`,
   `test_d2_la_veille_amont_ne_reprend_pas_un_projet_lu_avant_la_confirmation` et
   `test_d2_un_collegue_invite_est_cree_non_confirme_sans_lien_de_confirmation` ; ce texte, par
   `test_d2_le_document_dit_la_decision`.
3. **La bulle (i) de « Mes alertes »** disait encore « au-dessus de votre seuil de compatibilité ». **Décidé le 22/10 :
   (b)**, corrigée maintenant, avec ses traductions. Elle dit :

   « Recevez par email les nouveaux marchés de cette recherche, 10 au plus par alerte, les autres comptés. Chaque
   envoi lit un nombre limité d'avis par source (au BOAMP, les 25 derniers publiés) : une recherche très large peut en
   avoir d'autres, à voir dans Adjugo. La recherche de l'onglet « Publiés » est enregistrée telle quelle. »

   La première phrase est la vôtre. Vérifiée dans le code :
   - « 10 au plus par alerte » est vrai : le courriel liste 10 marchés au plus par alerte (`_MARCHES_PAR_ALERTE`) ;
   - « les autres comptés » n'est vrai que pour les avis que l'envoi lit : au-delà de 10, la ligne « … et N autres
     marchés » les compte. Mais chaque envoi ne demande que 25 avis au BOAMP et à TED (`run_one_saved_search`,
     `limit=25` ; au BOAMP, les 25 derniers publiés) et lit 3 pages au plus de Mégalis. Si une source a plus d'avis
     nouveaux qu'un envoi n'en lit, le reste n'est ni listé ni compté ; au BOAMP, ce sont les plus anciens, et l'envoi
     suivant lit de nouveau les 25 derniers publiés. D'où la deuxième phrase, ajoutée pour que la bulle reste vraie.
     La troisième phrase est celle d'avant, inchangée : l'alerte reprend les mots, les départements, le pays, le
     type de marché et les codes CPV de la recherche de « Publiés » (`srcSaveAlert`).

   Néerlandais et espagnol ajoutés (`scripts/i18n_ajouter.py`, 790 clés). Prouvé par
   `test_d3_la_bulle_de_mes_alertes_dit_ce_que_fait_le_courriel` (échouait sur `130fc9e`) et
   `test_d3_ce_que_dit_la_bulle_est_vrai` (13 marchés : 10 listés, « … et 3 autres marchés » ; 25 avis demandés ; le
   BOAMP trié du plus récent au plus ancien). (Moteur § V.8)
4. **Mesure du rappel avant le lot.** Pour mesurer ce que le lot change, il faut une mesure « avant » prise avant
   la mise en ligne. Il faut pour cela la liste des numéros d'entreprise (SIREN) des PME en test, que fournit
   Mathys. On lance ensuite sur votre poste `scripts/mesure_rappel.py collecter`, puis
   `mesurer --etiquette avant-lot1`. Ce n'est jamais lancé en production. Sans elle, il n'y aura pas de point de
   départ. (Moteur § 9)
5. **Brevo** : vérifiez que le suivi des ouvertures et des clics est coupé (Transactionnel › Paramètres). Le
   nouveau courriel d'invitation n'a ni image ni pixel, mais Brevo peut en ajouter et réécrire les liens au
   niveau du compte. (V2B § B4.9)
6. **Railway, `LOG_LEVEL`** : la ligne de journal du repli payant est au niveau INFO. Si `LOG_LEVEL` est réglé
   plus haut dans Railway, elle n'apparaîtra pas. (Moteur § 8)
7. **Railway, `ANALYSE_PARTAGEE`** : si elle vaut 1, une annonce déjà analysée « sur l'annonce seule » sera
   réanalysée une fois, car son empreinte change. Par défaut, rien. (Moteur, point 21)

### Plus tard (rien ne bloque la mise en ligne)

- **Démo de pitch** : l'analyse de Kerhel garde « La bonne stratégie est claire : répondre en GROUPEMENT… », une
  injonction. À revoir avec le pitch. (V2B § B2.8, R.5)
- **Un lien en lecture seule « partenaire du groupement » bloque la génération de la convention** (« … n'a pas
  encore soumis sa part »). C'est un défaut de production laissé tel quel, car il relève d'une règle de la
  convention. En attendant, le chef de file révoque ce lien ou le remplace. (V2B § S.4)
- **Rectificatifs** : trois écritures réelles ne sont pas lues (« initialement prévue le X … reportée au Y »,
  rectificatif européen sans date structurée, « Lire X au lieu de Y »). Chacune demande une règle à mesurer.
  Il faut aussi décider d'une règle de fusion Mégalis + BOAMP par le nom de l'acheteur : aujourd'hui, les deux
  cas réels restent en deux cartes. (Moteur § R.4)
- **Ancienne route de recherche du partenaire** (`POST /api/invite/{jeton}/search`) : gardée pour les pages
  ouvertes avant la mise en ligne, à retirer ensuite. (V2B § B3.10)
- **Pages annexes du site** : à relire, puis à mettre en ligne à part (section 5).
- **Récapitulatif des attestations d'un marché créé par un collègue non confirmé** (décision 2, première exception) :
  le collègue, une fois confirmé, ne reçoit le récapitulatif qu'au palier suivant, et aucun si c'était déjà J-3. Pour
  qu'il parte au premier passage après la confirmation, comme les autres courriels de la décision 2, il faut noter
  le récapitulatif à part de l'alerte du partenaire (une entrée de journal propre), avec un test. À vous de dire si
  ce cas rare le mérite. (Relecture des décisions, section 5)
- **Veille amont, au moment de la rallumer** (décision 2, deuxième exception) : pour une adresse non confirmée, elle
  n'enregistre aucun projet, et un projet lu entre-temps puis sorti des délibérations récentes n'est jamais ajouté.
  Autre choix : enregistrer les projets et garder le courriel pour après la confirmation, ce qui demande un repère
  « non envoyé ». (Relecture des décisions, section 5)
- **Repli payant de « À venir », outre-mer et Corse, après l'annonce du crédit** (partie écran du lot 1). La décision 1
  remboursait ces zones « jusqu'à l'annonce du crédit à l'écran ». L'écran l'annonce maintenant, et dit « toujours
  remboursée en outre-mer et en Corse », ce que fait le code : rien n'a changé dans le débit sans vous. Deux choix :
  (a) garder ce remboursement, et seule la ligne du journal (« … jusqu'à l'annonce du crédit à l'écran ») est à
  reformuler ; (b) l'arrêter, et la fin de la phrase de l'écran, sa bulle et leurs traductions changent dans le même
  geste. (Moteur, section « Écran »)
- **Recherche sans mot** : « Rechercher » (Publiés) et « Chercher les fins de contrat » (À venir), lancés sans mot,
  cherchent toujours « travaux » sans le dire. Seul « Voir les marchés pour mon entreprise » était dans le lot.
  (Moteur, section « Écran »)
- **Collègue invité : aucun lien de confirmation** (production, inchangé) : ni l'invitation ni la connexion n'en
  envoient, et l'écran « Confirmez votre adresse email » lui dit pourtant « Un lien de confirmation vous a été envoyé
  par email ». Il doit cliquer « Renvoyer l'email de vérification ». Deux remèdes possibles : envoyer le lien avec le
  courriel d'invitation, ou dire à l'écran, quand aucun lien n'est parti, de cliquer ce bouton. (Relecture des
  décisions, section 5)

---

## 4. Procédure de mise en ligne et de retour arrière

### La migration

Une seule migration, **`c5priseenmain`**, qui suit `c4montantseul` (la tête de la production). L'ordre complet de
la fin de chaîne est : `a2carnetnotes` → `b3mesureecrans` → `c4axeetapes` → `c4montantseul` → **`c5priseenmain`**
(seule tête). Elle **ajoute** trois colonnes, avec leur valeur par défaut posée par la base :

- `users.premiers_pas_replie` (liste repliée, faux par défaut) ;
- `users.suggestion_reseau` (carte « Faites-vous trouver », vide par défaut) ;
- `matching_criteria_ext.montant_porte_seul_inconnu` (« Je ne sais pas », faux par défaut).

Elle ne retire rien et ne modifie aucune ligne existante. On peut la rejouer sans effet. Le moteur (lot 1) et les
tests PostgreSQL ne touchent pas la base. La mémoire des alertes change de forme, mais dans la même colonne et
sans migration.

### Mettre en ligne

1. **Avant** : les décisions 1 à 3 de la section 3 sont prises et appliquées ; prenez la décision 4 (la mesure
   « avant »), puis faites une sauvegarde de la base juste avant (instantané Railway ou sauvegarde R2).
2. **Mettre la branche de production à jour, en local** : avancez `feat/produit-acheteur-collectivites` de
   `0afc1ed` au commit de cette réunion (la tête de la branche `worktree-wf_08701d74-77f-1`), par avance rapide
   (`git merge --ff-only <commit>`), sans fusion. Ne
   poussez pas pour mettre en ligne : la production ne part pas de GitHub. `origin/feat/produit-acheteur-collectivites`
   est resté au 29/06 (`e483f0c`), 287 commits avant `0afc1ed`, et `github.com/devlexus-cmd/adjugo` était noté
   public en juin. Pousser est un geste à part, à votre choix, qui ne met rien en ligne.
3. **Mettre en ligne par `railway up`**, comme les mises en ligne d'octobre. Railway construit l'image avec les
   fichiers du dossier d'où part la commande, tels qu'ils sont sur le disque, modifications non commitées
   comprises. Deux façons :
   - **(recommandé)** une copie propre : `git worktree add <dossier> -b deploy/reunion-22-10 <commit>`, puis, depuis
     ce dossier, `npx -y @railway/cli@latest up -c -p <projet « adjugo »> -e production -s adjugo-api`.
     L'identifiant du projet est dans `~/.railway/config.json` ;
   - ou `cd /Users/eliot/Downloads/adjugo-backend && npx -y @railway/cli@latest up -c -s adjugo-api`, seulement si
     la copie principale est sur ce commit et sans aucune modification (`git status` vide). Ce dossier est un lien
     vers `/Users/eliot/ADJUGO/01_Code/adjugo-backend`, qui a aujourd'hui des modifications (`.gitignore`,
     `.claude/launch.json`) et des fichiers non suivis. Ils partiraient avec l'image.

   Attention au dossier : lancé depuis un dossier non lié au projet, `railway up` a déjà créé un projet parasite
   (07/10). `entrypoint.sh` lance ensuite `alembic upgrade head` (`c4montantseul` → `c5priseenmain`), puis démarre.
4. **Pendant le démarrage**, l'ancien conteneur sert encore le trafic sur la base déjà migrée. C'est vérifié :
   le code de production y lit et y écrit (critères, marchés, invitations, vue du partenaire, alertes,
   inscription).
5. **Après** :
   - dans le terminal Railway, `alembic current` doit dire `c5priseenmain (head)` ;
   - `/api/health` doit répondre ;
   - ouvrez le lien privé de la démo et un vrai compte (accueil, un marché, « Voir ce que verra votre
     partenaire », `/app/exemple`) ;
   - le lendemain matin, vérifiez le compte rendu de la tournée des alertes : il porte maintenant
     `weekly_not_due`.

### Revenir en arrière

L'ancienne image ne connaît pas `c5priseenmain`. Si elle démarre sur une base notée `c5priseenmain`, son
`entrypoint.sh` s'arrête sur « Can't locate revision » (vérifié), et rien n'est remis en arrière. Il faut donc
**d'abord changer la version notée dans la base, depuis la NOUVELLE image, puis seulement relancer l'ancienne**.
La façon recommandée n'a ni coupure ni perte :

1. dans le terminal Railway du déploiement actuel (nouvelle image) : **`alembic stamp c4montantseul`**. Seule la
   version notée change. Les trois colonnes restent, avec l'état replié des premiers pas, la carte « Faites-vous
   trouver » et les réponses « Je ne sais pas ». La nouvelle image continue de servir normalement (vérifié :
   connexion, inscription, pages d'un utilisateur connecté) ;
2. vérifiez `alembic current` : il affiche `c4montantseul`, **sans « (head) »**, car la tête de la nouvelle image
   est `c5priseenmain`. L'ancienne image, une fois relancée, affichera `c4montantseul (head)` ;
3. redéployez l'image précédente (`0afc1ed`, bouton « Redeploy » du déploiement précédent dans Railway). Son
   `alembic upgrade head` n'a rien à faire. Elle lit et écrit sur une base qui a ces colonnes, comme pendant la
   mise en ligne (vérifié) ; les lignes qu'elle crée prennent les valeurs par défaut ;
4. **à savoir** : l'ancien code ne lit pas la nouvelle mémoire des alertes. À sa première tournée, il renverra
   **une fois tous les marchés que la nouvelle version a revus et qui passent son seuil, même ceux envoyés avant
   la mise en ligne**. Dans la vérification, 3 marchés ont été renvoyés à l'alerte du chef de file, dont 2 envoyés
   avant la mise en ligne. Ce renvoi n'est pas plafonné à 25 marchés par alerte (contre-relecture de la réunion).
   L'ancien code demande 25 avis à chaque source qui suit cette limite (BOAMP et TED, soit 50 au plus). Pour une
   alerte sur la Bretagne, il y ajoute tous ceux de Mégalis, qui ne la suit pas (jusqu'à 3 pages de résultats), et
   il ne coupe jamais la liste réunie. Le courriel en affiche 10 par alerte, avec leur nombre, et son objet donne
   le total. Ensuite, plus rien n'est renvoyé. Toutes les autres données écrites par la nouvelle
   version restent lisibles par l'ancienne (vérifié) ;
5. pour remettre la nouvelle version ensuite, redéployez-la : `alembic upgrade head` rejoue `c5priseenmain` sans
   effet (les colonnes sont là), et tout est retrouvé. Elle relit la mémoire mêlée des alertes sans rien renvoyer
   (vérifié). Un seul cas reste : une entreprise qui avait coché « Je ne sais pas », puis saisi un montant sous
   l'ancienne version, garde la case cochée jusqu'à son prochain enregistrement, où le montant l'emporte.

Ne relancez jamais l'ancienne image avant l'étape 1.

**Pour retirer aussi les trois colonnes**, remplacez `stamp` par **`alembic downgrade c4montantseul`** à
l'étape 1. On perd alors l'état replié des premiers pas, la carte « Faites-vous trouver » et les réponses « Je ne
sais pas », rien d'autre. `alembic current` affiche de même `c4montantseul` sans « (head) » dans la nouvelle image.
**Ce choix coupe le service** : de cette commande jusqu'à ce que l'ancienne image serve (étape 3), la nouvelle image
encore en service répond « erreur 500 » à toute connexion, à toute inscription et à toute page d'un utilisateur
connecté, car elle lit ces colonnes. `/api/health` reste à 200, donc Railway ne voit rien (vérifié). La coupure
dure le temps que Railway démarre l'ancienne image ; au dernier démarrage réel, le démarrage de l'application seul
prenait environ 11 secondes.

---

## 5. Les vérifications faites (22/10/2026)

**Réunion des branches.** `0afc1ed`, puis la vague 2b, les tests PostgreSQL et le moteur, chacun fusionné par
`git merge`. Les conflits ont été résolus bloc par bloc, jamais un fichier pris d'un seul côté. Un script compare,
ligne par ligne, chaque ligne ajoutée par un chantier au résultat : **91 fichiers, 22 291 lignes ajoutées
contrôlées**. Juste après les fusions, les seules absentes étaient les 7 lignes des deux blocs en conflit. Elles
étaient la même correction écrite trois fois, différemment, pour le test du compte rendu qui échouait selon la
date. Sur l'état final, 28 lignes ne sont plus telles quelles, toutes remplacées volontairement :

- les 7 lignes en conflit ;
- 14 lignes des fonctions de test remplacées par la fonction unique ;
- 3 lignes de la requête des alertes remplacées par la fonction unique des comptes non confirmés ;
- 3 lignes de commentaire ou de documentation complétées ;
- 1 assertion renforcée.

Aucune ligne n'est perdue sans raison. Une seule notion par sujet :

- une seule fonction des comptes non confirmés (`_comptes_non_confirmes`), utilisée aussi par les alertes de
  marchés ;
- une seule fonction de test pour « pas de N/M hors des dates » (`tests/textes_visibles.compteur`), qui trouve
  tout ce que trouvaient les corrections qu'elle remplace (sonde : 9 864 contrôles sur chaque jour de 2026 à
  2028).

Un test de la vague 2b comptait 2 appels à la fonction des comptes non confirmés. Il vérifie maintenant les 3
appels, chacun à sa place. Aucun test n'a été affaibli ni retiré, et une seule tête Alembic existe
(`c5priseenmain`).

**Suites de tests complètes, `TZ=UTC`, Python 3.12 installé depuis `requirements.lock`, sans réseau :**

| Moteur | Tests | Réussis | Échecs | Erreurs | Ignorés |
|---|---|---|---|---|---|
| SQLite | 2 404 | 2 404 | 0 | 0 | 0 |
| PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`) | 2 404 | 2 404 | 0 | 0 | 0 |

Le total vaut 2 205 (production) + 126 (vague 2b) + 50 (moteur) + 10 (revue de la réunion, plus bas) + 3
(contre-relecture de la réunion, plus bas) + 5 (décisions d'Eliot, plus bas : le test R1 de la revue remplacé par
deux, et quatre nouveaux) + 5 (relecture des décisions, plus bas). La première suite réunie, avant l'alignement du test cité plus haut, donnait 2 380 sur
2 381. Avant la revue : 2 381 sur 2 381 sur les deux moteurs. Avant la contre-relecture : 2 391 sur 2 391 sur les
deux moteurs. Avant les décisions d'Eliot : 2 394 sur 2 394 sur les deux moteurs. Avant leur relecture : 2 399 sur
2 399 sur les deux moteurs.

**Migration depuis l'état exact de la production, PostgreSQL 16.2 : 38 contrôles sur 38.** Le code `0afc1ed` a
été extrait par `git archive`. La base a été montée par ce code (tête `c4montantseul`) et remplie par lui :

- chef de file confirmé avec critères et montant porté seul ;
- un marché avec le dossier de l'acheteur, un partenaire qui soumet 283 456 €, un sous-traitant, la convention
  générée et « Préparer mes documents » ;
- un marché à J+2 avec une invitation en attente et un lien en lecture seule ;
- un compte non confirmé avec une invitation vers un tiers et une alerte ;
- un compte de 40 jours ;
- une alerte servie par la production, qui laisse la mémoire à l'ancienne forme.

Les défauts 1 et 3 de la section 2 ont été constatés avec le code de production. Ensuite :

- **Montée vers `c5priseenmain`** : une seule tête, les valeurs par défaut posées, rien d'autre ne bouge
  (comptes, marchés, invitations, pièces, alertes). Le schéma est identique à celui d'une base neuve.
- **Le nouveau code lit et écrit** :
  - vague 2b : premiers pas lus dans ces données, état replié et « Je ne sais pas » écrits puis relus ; aperçu du
    partenaire sans donnée interdite, sans compteur ni journal ; le partenaire et le sous-traitant ne listent et
    ne téléchargent que le dossier de l'acheteur ; rappel en HTML au seul partenaire du chef confirmé, rien vers
    le tiers ; renvoi en HTML avec le même jeton ; carte « Faites-vous trouver » ; marché d'exemple servi ;
  - moteur : la mémoire écrite par la production est reconnue (rien n'est renvoyé), le marché noté 50 part
    aussi, rien ne part vers l'adresse non confirmée, la nouvelle mémoire est écrite et un second passage ne
    renvoie rien ; la veille masquée répond 404.
- **Le code de production relancé sur la base migrée lit et écrit** (fenêtre de mise en ligne).
- **Retour arrière réel** (`alembic downgrade c4montantseul`) : les trois colonnes sont retirées et la production
  lit et écrit. Sa tournée d'alertes renvoie une fois 3 marchés (section 4). La remontée puis le rejeu forcé
  sont sans effet, et le nouveau code relit la mémoire mêlée sans rien renvoyer.
- **Revue de la réunion, rejouée sur le code corrigé : 53 contrôles sur 53** (les 38 ci-dessus et 15 de plus,
  section « Revue de la réunion » plus bas).

**Fichiers servis :**

- `scripts/sri_update.py --check` : empreintes à jour ;
- `node --check` : 8 fichiers JS servis et 9 scripts intégrés aux pages, 0 erreur ;
- `scripts/i18n_ajouter.py --check` : 789 clés, néerlandais et espagnol (790 depuis les décisions d'Eliot, plus bas) ;
- gabarit de l'application compilé par le Vue du dépôt : 3 tests.

**Démo de pitch.** Toutes les réponses de lecture de la démo, plus le lien du partenaire de Kerhel, ont été
relevées avec le code de production puis avec le code réuni, sur une base neuve. Les jetons et les dates sont
neutralisés. Sur **190 réponses, 184 sont identiques**, 2 ne diffèrent que par l'ordre de deux éléments créés
dans la même seconde, et les 4 autres ont seulement des champs ajoutés (184 + 2 + 4 = 190) :

- `montant_porte_seul_inconnu` dans les critères et dans l'export RGPD ;
- `essai_jours` dans la configuration publique ;
- les empreintes des scripts, qui ont changé.

Il y a 2 routes de lecture nouvelles (premiers pas, aperçu du partenaire), soit 3 réponses de plus. `tests/test_demo_*.py` et `test_demo_sans_cout.py`
sont verts.

**Navigateur réel (Chromium).** Un serveur local tournait sur le code réuni, avec une base jetable. L'IA, les
courriels et le réseau sortant étaient coupés. La démo était ouverte par **lien privé**, avec une clé de test
locale écrite dans un fichier, jamais affichée, et `DEMO_PUBLIC=0`. Pages vues :

- espace entreprises : accueil (« À faire » avec 2 pièces à renouveler, « À plusieurs », sans premiers pas),
  marché de Kerhel, « Voir ce que verra votre partenaire » (barre « Déposé par le chef de file : En cours »,
  total commun, dossier du marché seul), `/app/exemple` (6 mentions « Exemple · entreprises et client fictifs »,
  « Seul 43 % ») et une recherche de marchés ;
- espace collectivités.

À **1 280 px et à 375 px**, les adresses ont été rechargées directement. Il n'y a aucun défilement horizontal
(largeur du document égale à celle de la fenêtre), aucune erreur de script en console, et aucun courriel n'a été
tenté.

**Pages annexes** (branche `reunion-22-10-avec-annexes`, pas dans cette mise en ligne) : voir le dernier commit
de cette branche pour ses résultats.

### Revue de la réunion (22/10/2026)

Une revue de la réunion (`85e5809`) a fait 8 remarques : 3 majeures et 5 mineures. Toutes ont été reproduites, et
aucune n'est rejetée. Six portaient sur ce document, deux sur le code. Les tests de
`tests/test_mise_en_ligne_22_10.py` (10 tests) échouaient tous sur `85e5809` et passent sur le code corrigé.

| | Remarque | Reproduction | Correction |
|---|---|---|---|
| R1 | La décision 2 disait que refuser les alertes aux adresses non confirmées était « la règle du reste de l'application ». | Sur `85e5809`, une adresse non confirmée ne reçoit pas l'alerte de marchés, mais la même tournée lui envoie « Demandez vos notes ». Le récapitulatif « pièces à renouveler » part aussi vers elle. | Décision 2 récrite, avec trois choix. Le code ne change pas : le test fixe la règle telle qu'elle est. Depuis la décision 2 (b) du 22/10, le test fixe la règle unique (plus bas, « Décisions d'Eliot »). |
| R2 | « puis poussez » : la production ne part pas d'un push. | `origin` est à `e483f0c` (29/06), 287 commits avant `0afc1ed`. Les mises en ligne d'octobre sont parties par `railway up`. | Section 4 : la vraie procédure, le bon dossier, et le push présenté comme un geste à part. |
| R3 | Le retour arrière ne renvoie pas que les marchés « envoyés depuis la mise en ligne ». | PostgreSQL : 26-900001, 26-900002 et 26-900007 renvoyés, dont les 2 premiers envoyés avant la mise en ligne. | Section 4, étape 4, et un test du mécanisme de la mémoire. |
| R4 | Le downgrade coupait le service sans le dire. | PostgreSQL, application en service pendant le downgrade : connexion 500, inscription 500, pages d'un utilisateur connecté 500, santé 200. | `alembic stamp c4montantseul` recommandé, sans coupure ni perte (vérifié) ; le downgrade reste possible, avec la coupure annoncée. |
| R5 | `alembic current` n'affiche pas « (head) » dans la nouvelle image. | `c4montantseul` dans la nouvelle image, `c4montantseul (head)` dans l'ancienne, après `stamp` comme après `downgrade`. | Section 4, étape 2. |
| R6 | 186 + 2 + 4 faisait 192. | Le comparateur relancé donne 184 identiques, 2 dans un autre ordre et 4 avec des champs ajoutés. | Chiffres corrigés. |
| R7 | La fenêtre du SIRET coupait le département à 2 chiffres (« 97 », « 20 »). | Avec le code postal 97400, un avis de la Guadeloupe passait « dans votre zone ». Une recherche « 20 » demande « 20 » au BOAMP, qui n'écrit que « 20A » et « 20B ». | `depDuCodePostal` reprend la règle du serveur, et `zoneDuCodePostal` donne « 2A, 2B » pour la Corse. Corrigé dans la fenêtre du SIRET, « Voir les marchés pour mon entreprise » et « Chercher » des partenaires. |
| R8 | L'aperçu datait l'offre figée en UTC. | Navigateur (Chromium, Paris), offre figée le 21/10 à 23:41 UTC : l'aperçu affichait « 21/10/2026 », la page du partenaire « 22/10/2026 ». | Un seul formateur, `convJour` (jour local), pour les trois « Offre commune figée le ». Après correction, les trois écrans affichent « 22/10/2026 ». |

Vérifications des corrections :

- **PostgreSQL 16.2 depuis l'état exact de la production, 53 contrôles sur 53**
  (`scratchpad/corr2210/run_corr_pg.py`, sur le code corrigé). Ce sont les 38 contrôles de la réunion, plus :
  - l'ancienne image s'arrête sur une base notée `c5priseenmain` ;
  - le retour par `stamp` : la nouvelle image continue de servir pendant le changement, les colonnes restent,
    l'ancienne image démarre, lit et écrit, et les lignes qu'elle crée prennent les valeurs par défaut ;
  - le renvoi de 3 marchés, dont 2 envoyés avant la mise en ligne, avec `stamp` comme avec `downgrade` ;
  - la remontée après `stamp`, sans effet, avec un schéma identique à une base neuve. L'état replié, les « Je ne
    sais pas » et la carte sont retrouvés, le montant saisi sous l'ancienne version l'emporte au prochain
    enregistrement, et rien n'est renvoyé ;
  - la coupure du `downgrade`, mesurée l'application en service ;
  - ce qu'affiche `alembic current` dans chaque image.
- **Navigateur réel (Chromium sans fenêtre, fuseau Europe/Paris)**, démo par lien privé (clé de test locale dans un
  fichier, jamais affichée, `DEMO_PUBLIC=0`). Vu à 1 280 et 375 px, en clair et en sombre : accueil, Mes marchés,
  marché de Kerhel, « Voir ce que verra votre partenaire », `/app/exemple`, Trouver (Publiés, À venir),
  Partenaires, Mes documents, Ce que je cherche, `/app/marches/partenaire` et la page du partenaire sans
  compte. Il n'y a aucun défilement horizontal ni aucune erreur de script, et aucun courriel n'a été tenté. L'offre
  de Kerhel a été figée le 21/10 à 23:41 UTC. Sur `85e5809`, l'aperçu affichait « 21/10/2026 » et la page du
  partenaire « 22/10/2026 ». Sur le code corrigé, les trois écrans affichent « 22/10/2026 ».
- **Démo de pitch relevée de nouveau**, production et code corrigé le même jour : sur 190 réponses, 185 sont
  identiques, 1 ne diffère que par l'ordre et 4 ont les mêmes champs ajoutés. Le nombre de réponses dans un autre
  ordre change d'un relevé à l'autre.
- `scripts/sri_update.py --check`, `node --check` (8 fichiers et 9 scripts intégrés, 0 erreur) et
  `scripts/i18n_ajouter.py --check` (789 clés) : verts. Aucune phrase nouvelle à traduire.

Vu en passant, non corrigé : le rapport PDF du groupement (`app/services/consortium_report.py`) date lui aussi l'offre
figée par le jour UTC (« Offre commune figée le 21/10 »). C'est un document à part, inchangé depuis la production.

### Contre-relecture de la réunion (22/10/2026)

Une contre-relecture de la revue (`002e2bb`) a fait 2 remarques : 1 majeure et 1 mineure. Les deux ont été
reproduites, et aucune n'est rejetée. Elles portaient sur ce document : le code ne change pas. Trois tests s'ajoutent
à `tests/test_mise_en_ligne_22_10.py`. Les tests CR1 (onglet) et CR2 échouaient sur `002e2bb`, sur les phrases du
document ; le test de la route, qui fixe un comportement inchangé, y passait déjà. Les tests R3 et R7, qui citaient
les deux phrases fausses, citent les phrases corrigées et vérifient que les anciennes ont disparu.

| | Remarque | Reproduction | Correction |
|---|---|---|---|
| CR1 | Décision 1, « Qui est concerné » : une entreprise déjà inscrite ne garde pas l'ancien comportement de « À venir ». | Sous Node, avec les vraies méthodes `srcPrefillFromProfile`, `srcDeps` et `srcRenewals` : une entreprise déjà inscrite, zone enregistrée « 97 » (code postal 97400) ou « 20 » (20000), envoie `["97"]` et `["20"]` sur `85e5809`, `["974"]` et `["2A", "2B"]` sur `002e2bb`. La route `POST /api/sourcing/renewals` ne prend ses départements que dans la requête, pour la DECP comme pour le repli ; la zone enregistrée ne sert qu'à la note. | Décision 1 récrite : toute entreprise dont le code postal est en outre-mer ou en Corse, inscrite avant ou après, et toute entreprise qui saisit ces codes. Section 1 : le pré-remplissage du champ de Trouver (Publiés et À venir) vaut pour tous les comptes, seule la zone enregistrée n'est pas réécrite. Section 2, point 15, précisé. Deux tests fixent cette portée (l'onglet sous Node, la route). |
| CR2 | Retour arrière, étape 4 : le plafond de « 25 marchés » par alerte n'existe pas dans le code de production. | Code `0afc1ed` extrait par `git archive`, `run_one_saved_search` réel, sources simulées sans réseau : BOAMP et TED en rendent 25 chacun, Mégalis 30 (il ne lit pas la limite), et la liste réunie n'est jamais coupée. Une alerte bretonne renvoie 80 marchés. | Étape 4 : 25 par source qui suit la limite (BOAMP et TED), plus tous ceux de Mégalis, liste jamais coupée ; 10 affichés par alerte avec leur nombre, et le total dans l'objet. Un test rejoue ce renvoi sur le code de production. |

Vérifications : suites complètes SQLite et PostgreSQL 16.2 à 2 394 sur 2 394 chacune (tableau plus haut). Aucun
fichier servi ne change : `scripts/sri_update.py --check`, `node --check` (8 fichiers et 9 scripts intégrés) et
`scripts/i18n_ajouter.py --check` (789 clés) restent verts.

Vu en passant, non corrigé : une première suite SQLite, lancée en même temps que celle de PostgreSQL, a vu échouer
une fois `tests/test_lecture_integrale.py::test_scan_sans_ocr_signale_et_rembourse_si_rien_n_est_lisible`. C'est
une course entre le test et la tâche de fond : `lecture_taches.lancer` écrit l'état « erreur » avant de rembourser
l'analyse, et le test relit le compteur dès qu'il voit « erreur ». Le remboursement a bien lieu. Ce fichier relancé
seul trois fois, puis la suite complète relancée seule, sont verts. Ce code n'a pas changé depuis la production.

### Décisions d'Eliot (22/10/2026)

Les décisions 1 à 3 de la section 3 ont été prises par Eliot le 22/10, toutes trois sur le choix (b). Elles sont
appliquées sur `130fc9e`. Chaque changement a un test qui échouait sur `130fc9e` (code exporté par `git archive`, tests
nouveaux copiés) et passe désormais. Un seul manque, vu par la relecture des décisions (plus bas) : les vérifications
du document sur la décision 2 étaient parties avec l'ancien test R1, sans remplaçant ;
`test_d2_le_document_dit_la_decision` les rétablit.

| | Décision | Ce qui change dans le code | Preuve (`tests/test_mise_en_ligne_22_10.py`) |
|---|---|---|---|
| D1 | Repli payant de « À venir » remboursé en outre-mer et en Corse, jusqu'à l'annonce du crédit à l'écran | `app/routers/sourcing.py` : `_repli_rembourse_par_zone`, et le journal écrit `REMBOURSE_PAR_ZONE` | `test_d1_repli_a_venir_rembourse_en_outre_mer_et_en_corse` : 12 demandes, dont « 974 », « 2A, 2B », « 20200 » et « 29, 974 » remboursées, « 29 », « 6 » et toute la France débitées ; sur `130fc9e`, « 974 » est débité. `test_d1_le_document_dit_la_decision`. |
| D2 | Une seule règle pour les courriels planifiés vers le compte lui-même | `app/services/carnet_notes.py` (« Demandez vos notes ») et `app/services/alerts.py` (« pièces à renouveler », veille amont) lisent `_comptes_non_confirmes` ; commentaire d'`app/routers/auth.py` et docstring de la fonction | `test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte` : rien ne part ni n'est marqué, puis les trois partent après la confirmation, sauf « Demandez vos notes » d'un marché perdu il y a 15 jours ; sur `130fc9e`, « Demandez vos notes » et le récapitulatif partaient. `test_r1_la_veille_amont_suit_la_meme_regle` ; sur `130fc9e`, la veille rallumée écrivait à l'adresse. |
| D3 | Bulle (i) de « Mes alertes » corrigée, avec ses traductions | `app/static/app.html`, `app/static/i18n.js` (néerlandais, espagnol), empreintes SRI | `test_d3_la_bulle_de_mes_alertes_dit_ce_que_fait_le_courriel` ; sur `130fc9e`, l'ancienne bulle. `test_d3_ce_que_dit_la_bulle_est_vrai` (passait déjà : il fixe ce que la bulle affirme). |

Tests adaptés, et pourquoi :

- `test_r1_adresse_non_confirmee_ce_qui_part_et_ce_qui_ne_part_pas` (revue) fixait l'ancienne règle, celle que la
  décision 2 change : il est remplacé par les deux tests R1 ci-dessus, qui vérifient davantage le code (rien de marqué,
  envoi après la confirmation, la limite des 14 jours, la veille amont). Ils ne lisaient plus le document : ses
  vérifications de la décision 2 sont rétablies par `test_d2_le_document_dit_la_decision` (relecture des décisions).
- `tests/test_reorganisation_v2b_relecture.py::test_s5_le_commentaire_d_auth_py_reste_vrai` comptait 3 appels à
  `_comptes_non_confirmes` dans `alerts.py`. Il en compte 5, chacun à sa tâche planifiée, plus celui de
  `carnet_notes.envoyer_rappels`, et vérifie la phrase nouvelle du commentaire d'`auth.py`.

Constaté sur le code de production (`0afc1ed`, exporté par `git archive`), même tournée et même compte non confirmé :
l'adresse recevait les trois courriels, « Adjugo — 1 nouvel(s) appel(s) d'offres », « Adjugo — 1 pièce à renouveler »
et « Adjugo — demandez vos notes : Toiture de l'école ».

Vu en appliquant la décision 3 : « les autres comptés » n'est vrai que pour les avis que chaque envoi lit (25 demandés
au BOAMP et à TED, 3 pages au plus de Mégalis). La bulle le dit dans une deuxième phrase (section 3, décision 3).

Vérifications, sur le code des décisions :

- suites complètes, `TZ=UTC`, Python 3.12 installé depuis `requirements.lock`, sans réseau : SQLite, 2 399 sur
  2 399 ; PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`), 2 399 sur 2 399 (2 404 depuis la relecture des
  décisions, tableau plus haut) ;
- `scripts/sri_update.py`, puis `--check` : empreintes à jour (`app.html`, `sri-manifest.json`) ;
- `node --check` : 8 fichiers JS servis et 9 scripts intégrés aux pages, 0 erreur ;
- `scripts/i18n_ajouter.py --check` : 790 clés, néerlandais et espagnol (789 avant, une phrase nouvelle) ;
- gabarit de l'application compilé par le Vue du dépôt : ses 3 tests sont dans la suite.

Aucune migration nouvelle, aucune variable Railway, rien n'a été mis en ligne ni poussé.

### Relecture des décisions d'Eliot (22/10/2026)

Une relecture des décisions (`baf68de`) a fait 7 remarques, dont deux en double : 5 remarques distinctes, 1 majeure
et 4 mineures. Toutes ont été reproduites. Une est en partie rejetée (RD4, plus bas). Le code des courriels ne change
pas : les corrections portent sur ce document, sur `docs/MOTEUR_LOT1.md` et sur les commentaires d'`auth.py` et
d'`alerts.py`, qui disaient autre chose que le code. Cinq tests s'ajoutent à `tests/test_mise_en_ligne_22_10.py` ;
chacun échouait sur `baf68de`, par le document ou par un commentaire. Les comportements qu'ils fixent y étaient déjà.

| | Remarque | Reproduction | Correction |
|---|---|---|---|
| RD1 (remarques 1 et 6) | Plus aucun test ne lisait la décision 2 de ce document : les vérifications de l'ancien test R1 étaient parties avec lui. | Sur une copie de `baf68de`, la décision 2 réécrite en « (a), garder tel quel », et la phrase de la section 1 changée en « Adjugo lui envoie encore « Demandez vos notes » » : les tests de ce document et de la relecture de la vague 2b restent verts (37 réussis, 1 ignoré hors dépôt). | `test_d2_le_document_dit_la_decision` rétablit ces vérifications (décision prise, fonction unique, les quatre courriels, les 14 jours, les noms des tests) et vérifie que l'affirmation sans exception a disparu. Section 5, « Décisions d'Eliot » : le manque est dit. |
| RD2 (remarques 2 et 5) | « Rien n'est marqué : tout part au premier passage après la confirmation » est faux pour le récapitulatif des attestations d'un marché créé par un collègue non confirmé. | Propriétaire confirmé, marché d'un collègue qui a changé d'adresse : au palier J-7, le partenaire est prévenu et son alerte notée, rien au collègue ; confirmé, le même jour, toujours rien ; au palier J-3, le récapitulatif lui part. Témoin : propriétaire non confirmé, rien n'est noté ; confirmé, tout part dans le palier en cours. Ainsi depuis la vague 2b. | L'exception est dite ici (sections 1 et 3), dans le commentaire d'`auth.py`, la docstring de `_comptes_non_confirmes` et `_piece_alerts_due`. Le code ne change pas : choix laissé à Eliot (section 3, « Plus tard »). `test_d2_le_recapitulatif_des_attestations_d_un_marche_de_collegue_attend_le_palier_suivant`. |
| RD3 (remarque 3) | La veille amont, rallumée, n'enregistre aucun projet pour une adresse non confirmée, et un projet lu entre-temps n'est jamais repris. | Deux abonnés, l'un non confirmé : le projet A, lu pendant ce temps, est enregistré et envoyé pour l'autre seul ; après la confirmation, seul le projet B est lu, et ce compte n'a que B. | Section 3, décision 2 (deuxième exception) et « Plus tard » ; commentaires d'`auth.py` et de `run_amont_alerts`, docstring ; `docs/MOTEUR_LOT1.md`, point 16 bis. Sans effet à cette mise en ligne (`PROJETS_A_VENIR=0`). `test_d2_la_veille_amont_ne_reprend_pas_un_projet_lu_avant_la_confirmation`. |
| RD4 (remarque 4) | Le bilan ne disait pas qu'un collègue invité est créé non confirmé, sans lien de confirmation. | Reproduit : `POST /api/org/invite` crée le compte non confirmé ; seul le courriel d'invitation part (mot de passe provisoire, sans lien) ; la connexion n'envoie rien ; « Renvoyer l'email de vérification » envoie le lien. **En partie rejetée** : la remarque dit qu'il « ne recevra plus » des courriels « qu'il recevait en production ». Depuis le 24/06 (`36418a4`), l'écran plein « Confirmez votre adresse email » bloque tout compte non confirmé dès sa connexion, sans condition de rôle : depuis l'application, il ne peut créer ni alerte, ni marché, ni pièce avant de confirmer. La sonde de la remarque crée la pièce directement dans la base. La décision ne lui retire donc rien ; le seul compte qui perd des courriels reste celui qui change d'adresse. | Sections 1 et 3 : qui est non confirmé, et pourquoi la décision ne retire rien au collègue invité. « Plus tard » : le lien absent et la phrase de l'écran « Un lien de confirmation vous a été envoyé par email », fausse pour lui (production, inchangée). `test_d2_un_collegue_invite_est_cree_non_confirme_sans_lien_de_confirmation`. |
| RD5 (remarque 7) | `docs/MOTEUR_LOT1.md` : « Chaque test cité échouait sur `130fc9e` ». | Les tests cités, lancés sur une extraction `git archive` de `130fc9e` avec les tests de `baf68de` : 4 échouent, `test_d3_ce_que_dit_la_bulle_est_vrai` passe. | Phrase corrigée : ce test passait déjà, il fixe ce que la bulle affirme. `test_d3_le_contrat_du_moteur_dit_quel_test_passait_deja`. |

Vérifications, sur le code de la relecture :

- suites complètes, `TZ=UTC`, Python 3.12 installé depuis `requirements.lock`, sans réseau : SQLite, 2 404 sur 2 404 ;
  PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`), 2 404 sur 2 404 (tableau plus haut) ;
- les cinq tests nouveaux, lancés sur une extraction `git archive` de `baf68de` : 5 échecs ;
- aucun fichier servi ne change : `scripts/sri_update.py --check`, `node --check` (8 fichiers et 9 scripts intégrés)
  et `scripts/i18n_ajouter.py --check` (790 clés) restent verts ; gabarit compilé dans la suite.

Aucune migration nouvelle, aucune variable Railway, rien n'a été mis en ligne ni poussé.

### Partie écran du lot 1 du moteur (22/10/2026)

Posée au-dessus de `0f8eb32` : points 10 à 13 de la note du 21/10 (contrat : `docs/MOTEUR_LOT1.md`, section
« Écran » ; ce qui change pour les clients : section 1, lignes « Partie écran »). La bulle de « Mes alertes », déjà
corrigée, n'est pas touchée. Treize tests nouveaux (`tests/test_moteur_lot1_ecran.py`) : sur une extraction
`git archive` de `0f8eb32`, les 13 échouent, chacun sur le défaut qu'il couvre. Un test existant est adapté :
`test_cr1_a_venir_part_du_code_postal_pour_toute_entreprise_sous_node` donnait à la fiche Identité une spécialité
fictive, que le pré-remplissage ne lit plus ; ce qu'il vérifie ne change pas.

Côté serveur, trois ajouts, sans rien changer à ce qui est trouvé ni débité : le nom de l'organisme Mégalis nettoyé
(`atexo.nom_organisme` ; la clé de fusion et le lieu lisent toujours le texte de la page), le rectificatif qui fixe la
date sur la fiche (`date_limite_rectificatif`, `date_limite_rectificatif_le`), et la source et le sort de l'analyse
dans la réponse du repli payant (`source`, `analyse`). Ni prix, ni quota, ni règle de débit, ni IA, ni migration.

Vérifications :

- suites complètes, `TZ=UTC`, Python 3.12 installé depuis `requirements.lock`, sans réseau : SQLite, 2 417 sur
  2 417 ; PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`), 2 417 sur 2 417 (2 404 + 13) ;
- `scripts/sri_update.py`, puis `--check` : empreintes à jour (`app.html`, `sri-manifest.json`) ;
- `node --check` : `app.js` et `i18n.js`, 0 erreur ; gabarit de l'application compilé par le Vue du dépôt (dans la
  suite) ;
- `scripts/i18n_ajouter.py --check` : 815 clés, néerlandais et espagnol (25 phrases nouvelles) ;
- **navigateur réel**, serveur local sur ce code, base jetable, réseau sortant coupé (seule la boucle locale), BOAMP,
  Mégalis et DECP servis depuis les jeux d'essai réels du dépôt, IA simulée. Démo ouverte par **lien privé**, clé de
  test locale écrite dans un fichier, jamais affichée, `DEMO_PUBLIC` absent. Vu à 1 280 et à 375 px, en clair et en
  sombre : Publiés (six avis rectifiés du BOAMP : quatre « Date limite repoussée au … », dont « 06/11/2026 (rectificatif du
  06/10/2026) », un « Avis rectifié » et un « Date limite non précisée » avec sa bulle ; les consultations Mégalis au nom nettoyé ; l'invitation « classement adapté ») ; « Voir les
  marchés pour mon entreprise » avec et sans métier, « Dire mon métier », puis retour arrière vers Trouver, la
  demande disparue, la recherche partie sur le métier saisi ; À venir sur la DECP (974, « durée publiée ») et au repli
  payant (29, « 1 analyse consommée », compteur relu) ; la bulle du crédit dans la fenêtre à 375 px ; la démo
  (Publiés, À venir sans la ligne du crédit, « durée publiée ») et sa page d'exemple d'une délibération. Aucun
  défilement horizontal à 375 px (largeur du document égale à celle de la fenêtre), aucune erreur de script.

Ce qui change dans la démo de pitch : les cartes de recherche perdent « confiance » et « adéquation » ; après « Voir
les marchés pour mon entreprise », le champ des mots montre son premier métier (« toiture ») ; ses fins de contrat
disent « Fin du contrat estimée le … (durée publiée) ». Côté serveur, sa recherche et ses fins de contrat restent
servies à part : ses cartes de recherche gagnent seulement les deux champs vides `date_limite_rectificatif` et
`date_limite_rectificatif_le`, et ses fins de contrat ne changent pas. `tests/test_demo_*.py` et
`test_demo_sans_cout.py` restent verts.

Aucune migration nouvelle, aucune variable Railway, rien n'a été mis en ligne ni poussé.

### Revue de la partie écran du lot 1 (22/10/2026)

Douze remarques sur `ba07980`, neuf distinctes (trois écrites deux fois). Chacune reproduite sur `ba07980`, toutes
réelles ; une seule en partie (un détail de lieu inexact, la contradiction réelle). Le détail, avant, après et
preuves : `docs/MOTEUR_LOT1.md`, section « Écran », « Revue ». Ce qui change pour les clients est dans la section 1
ci-dessus (lignes « Partie écran ») :

- **le crédit de « À venir » dit vrai au paiement à l'usage** : la bulle disait « Il faut une analyse disponible pour
  la lancer », faux pour un forfait Pro ou Business au paiement à l'usage, où le repli part sans analyse restante et
  est facturé hors forfait. Elle dit la règle du code ; et ce compte, ses analyses du mois utilisées, lit avant le
  clic qu'une recherche complémentaire serait facturée, au prix du compteur (5 €), et remboursée dans les mêmes cas ;
- la bulle d'en-tête de « À venir » dit aussi le repli (date de publication de l'avis d'attribution du BOAMP, durée
  lue ou estimée) ; une durée estimée sans type de contrat est dite « par défaut » (36 mois) ;
- la bulle de « Date limite non précisée » dit qu'un rectificatif « peut changer » la date limite ;
- « Voir les marchés pour mon entreprise » : avec des codes CPV et aucune spécialité, l'écran dit que ces codes ne
  suffisent pas à ce bouton ; le sous-titre dit les départements de la recherche, plus le code postal ;
- ce bilan et le contrat : plus de « (estimée) », de « rien de visible », de note d'adéquation que le client verrait
  bouger, ni de « trois chantiers » en tête.

Sept tests nouveaux (`tests/test_moteur_lot1_ecran_revue.py`) : sur une extraction `git archive` de `ba07980` (tests
copiés), les 7 échouent, chacun sur le défaut qu'il couvre. Les tests de `tests/test_moteur_lot1_ecran.py` qui
fixaient les anciens textes les suivent. Ni prix, ni quota, ni règle de débit, ni IA, ni migration ; côté serveur, un
commentaire seulement (`schemas.py`). La démo de pitch : sa bulle d'en-tête de « À venir » gagne la phrase du repli ;
elle ne voit ni la ligne du crédit ni celle du paiement à l'usage ; ses fins de contrat disent toujours « (durée
publiée) ».

Vérifications :

- suites complètes, `TZ=UTC`, Python 3.12 installé depuis `requirements.lock`, sans réseau : SQLite, 2 424 sur
  2 424 ; PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`), 2 424 sur 2 424 (2 417 + 7) ;
- `scripts/sri_update.py`, puis `--check` : empreintes à jour ;
- `node --check` : `app.js` et `i18n.js`, 0 erreur ; gabarit de l'application compilé par le Vue du dépôt (dans la
  suite) ;
- `scripts/i18n_ajouter.py --check` : 823 clés, néerlandais et espagnol (8 phrases nouvelles) ;
- **navigateur réel**, serveur local sur ce code, base jetable, réseau sortant coupé (seule la boucle locale), BOAMP,
  Mégalis et DECP servis depuis les jeux d'essai réels du dépôt, IA simulée, Stripe jamais appelé ; démo ouverte par
  **lien privé**, clé de test locale écrite dans un fichier, jamais affichée. Vu à 1 280 et à 375 px, en clair et en
  sombre, en français, néerlandais et espagnol : « À venir » d'un compte Pro au paiement à l'usage, 30 analyses sur
  30 (la ligne « … serait facturée 5 € (paiement à l'usage) … » avant le clic ; repli sur le 29 : « 1 analyse
  consommée », 31 utilisées, 1 hors forfait ; une carte « (durée estimée par défaut, type de contrat inconnu) ») ; le
  même onglet pour un compte à l'essai (pas de ligne) ; la bulle de « Date limite non précisée » ; « Voir les marchés
  pour mon entreprise » avec des codes CPV seuls (la demande nouvelle, curseur sur « Dire mon métier », puis retour
  arrière vers Trouver) et avec le champ « Départements » vidé (recherche sur toute la France, comme le dit le
  sous-titre) ; la démo (Publiés, À venir sans ligne de crédit ni de paiement à l'usage, sa page d'exemple d'une
  délibération). Aucun défilement horizontal à 375 px, aucune erreur de script.

Aucune migration nouvelle, aucune variable Railway, rien n'a été mis en ligne ni poussé.
