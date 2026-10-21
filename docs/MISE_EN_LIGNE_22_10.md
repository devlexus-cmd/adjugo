# Mise en ligne du 22/10/2026

Ce document est pour Eliot. Il dit ce que la prochaine mise en ligne change pour les clients, ce qu'elle corrige,
ce qu'il reste à décider avant, comment la faire et la défaire, et ce qui a été vérifié.

**Ce qui part.** Trois chantiers, finis et vérifiés chacun de son côté, sont réunis sur la branche de cette réunion,
au-dessus de la production actuelle (`feat/produit-acheteur-collectivites` = `0afc1ed`, mise en ligne le 20/10) :

| Chantier | Commit | Contrat (le détail) |
|---|---|---|
| Réorganisation de l'interface, vague 2b : prise en main, marché d'exemple, espace du partenaire, courriel d'invitation | `52e0d59` | `docs/REORGANISATION_V2B.md` |
| Moteur de recherche, lot 1 « Dire juste », partie serveur | `723c9cc` | `docs/MOTEUR_LOT1.md` |
| Suite de tests verte sur PostgreSQL (rien ne change pour les clients) | `8b66841` | `docs/TESTS_POSTGRES.md` |

**Ce qui ne part pas.** Les pages annexes du site public (`/plateforme`, `/profils/…`, `/secteurs/…`, `/faq`)
restent hors de cette mise en ligne tant que vous n'avez pas relu leurs textes. Une branche à part,
`reunion-22-10-avec-annexes`, prouve seulement qu'elles s'ajoutent sans rien casser (section 5).

**Rien n'a été mis en ligne ni poussé.** Aucune variable nouvelle sur Railway. Une seule migration de base de
données, `c5priseenmain` (section 4).

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

### Fenêtre du SIRET et « Ce que je cherche »

- Nouvelle question facultative : « Jusqu'à quel montant répondez-vous seul ? », avec la réponse
  « Je ne sais pas ». La même case « Je ne sais pas » existe dans Mon entreprise › Ce que je cherche. Ce montant
  n'entre dans aucun calcul.
- Un montant trop grand est refusé dans la fenêtre, avec un message. Le bandeau des cookies ne passe plus
  par-dessus la fenêtre.

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
  sur 10 sur la page réelle du 21/10). L'ordre et la note d'adéquation d'une carte Mégalis peuvent donc bouger un
  peu.
- **Avis rectifiés du BOAMP** : la carte montre la nouvelle date limite. Un avis repoussé reste visible après son
  ancienne date, et un avis européen rectifié n'apparaît plus deux fois. Si la nouvelle date ne peut pas être lue
  sans doute, la carte affiche « limite non précisée », jamais l'ancienne date.
- **Avis annulés ou déclarés sans suite** : ils disparaissent.
- **Faux « métier correspondant »** : le vocabulaire interne du BOAMP n'est plus lu comme un code métier. La note
  d'adéquation de certaines cartes BOAMP baisse. Une recherche par codes CPV ne ramène plus d'avis sans rapport.
- **Outre-mer** : « 974 » ne montre plus les avis de la Guadeloupe ou de la Martinique, et la zone de la note est
  juste pour une entreprise d'outre-mer.
- **Corse** : « 2A » et « 2B » trouvent enfin les avis du BOAMP, qui écrit « 20A » et « 20B ». Le 21/10, 19 avis
  ouverts étaient concernés ; avant, aucun n'était trouvé.
- Une recherche fait une ou deux requêtes de plus au BOAMP, soit 0,4 à 0,6 seconde chacune.

### Trouver des marchés › À venir (fins de contrat)

- **Outre-mer** : seules les fins de contrat du département demandé, affiché sur 3 chiffres (« 974 »).
- **Corse et outre-mer, repli payant** : quand la base des marchés attribués (DECP) ne donne rien, le repli par le
  BOAMP et l'IA peut désormais trouver des fins de contrat dans ces deux zones. L'analyse est alors **débitée**.
  Avant, il ne trouvait jamais rien, et l'analyse était toujours remboursée. **C'est la décision 1 de la
  section 3.**
- « 6 » saisi seul est lu comme « 06 » dans la DECP, sans crédit. Avant, il passait par le repli payant.
- Une durée de contrat que l'IA n'a pas vraiment lue est affichée « (estimée) », et non plus « (réelle) ».
- Le bouton « Modifier ma zone » met le curseur dans le champ « Départements » de l'onglet, celui qui compte pour
  cette recherche.
- Chaque repli payant laisse une ligne dans le journal du serveur, sans donnée personnelle. Rien n'est visible à
  l'écran.

### Trouver des marchés › Mes alertes, et les courriels d'alerte

- **Plus aucun marché écarté par sa note** d'avant le dossier : les courriels contiennent plus de marchés. Sur
  l'alerte réelle « voirie » du Finistère (21/10), 7 marchés partent au lieu de 0.
- Au-delà de 10 marchés dans une alerte, une ligne dit « … et N autres marchés : relancez cette recherche dans
  Adjugo pour les voir tous ».
- Les dates des consultations Mégalis apparaissent dans le courriel.
- Moins de marchés reçus deux fois. Aucun marché déjà reçu n'est renvoyé au passage à la nouvelle mémoire des
  alertes (vérifié depuis une base remplie par la production, section 5).
- **Un compte dont l'adresse n'est pas confirmée ne reçoit plus d'alerte.** Ses marchés partent au premier
  passage après la confirmation (décision 2 de la section 3).
- **Attention** : la bulle (i) de « Mes alertes » dit encore « au-dessus de votre seuil de compatibilité ». C'est
  faux depuis ce lot (décision 3).

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

Les prix, les forfaits, les quotas et la règle de débit et de remboursement ne changent pas. Seul effet : le repli
payant de l'onglet « À venir » peut désormais trouver, donc débiter, en Corse et en outre-mer. Aucune offre ni
carte d'offre ne change (décision 14, réservée). Les pages juridiques et la vitrine ne bougent pas, et aucune IA
n'est ajoutée. La démo de pitch est identique, à quelques ajouts près (section 5).

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
   un tel compte dans la vérification de cette réunion. (Moteur § V.7)
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

---

## 3. Les décisions qui vous reviennent

### Avant la mise en ligne

1. **Repli payant de l'onglet « À venir » en outre-mer et en Corse.** Il débite désormais là où il remboursait
   toujours (il ne trouvait jamais rien). Deux choix :
   - **(a)** garder ce débit, selon la règle de partout ailleurs : débité s'il trouve, remboursé sinon. C'est ce
     que fait le code aujourd'hui ;
   - **(b)** rembourser le repli dans ces deux zones jusqu'à ce que l'écran annonce le crédit avant le clic
     (partie écran du lot, point 12 de la note du 21/10). Cela demande un petit changement de code, testé avant
     la mise en ligne.

   Effet de bord à connaître : comme la DECP ne mélange plus les DOM entre eux, un département d'outre-mer sans
   fin de contrat déclenche le repli payant, là où la DECP montrait avant (à tort) celles d'un autre DOM.
   (Moteur, points 12 et 12 bis, § R.1 et V.5)
2. **Alertes de marchés refusées aux adresses non confirmées.** C'est en place : aucun courriel, et rien n'est
   marqué « déjà vu », donc les marchés partent au premier passage après la confirmation. Les comptes créés avant
   la vérification des adresses ont été confirmés par la migration de juin et ne sont pas concernés. Garder
   (recommandé : c'est la règle du reste de l'application), ou retirer, ce qui tient en deux lignes. (Moteur
   § V.7)
3. **La bulle (i) de « Mes alertes »** dit encore « au-dessus de votre seuil de compatibilité ». Deux choix :
   - **(a)** la laisser jusqu'à la partie écran du lot ;
   - **(b)** la corriger maintenant, avec ses traductions. Proposition : « Recevez par email les nouveaux marchés
     de cette recherche, 10 au plus par alerte, les autres comptés ».

   (Moteur § V.8)
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

1. **Avant** : prenez les décisions 1 à 4 de la section 3, puis faites une sauvegarde de la base juste avant
   (instantané Railway ou sauvegarde R2).
2. **Mettre la branche de production à jour** : avancez `feat/produit-acheteur-collectivites` de `0afc1ed` au
   commit de cette réunion (avance rapide, sans fusion), puis poussez. Railway construit l'image ;
   `entrypoint.sh` lance `alembic upgrade head` (`c4montantseul` → `c5priseenmain`), puis démarre.
3. **Pendant le démarrage**, l'ancien conteneur sert encore le trafic sur la base déjà migrée. C'est vérifié :
   le code de production y lit et y écrit (critères, marchés, invitations, vue du partenaire, alertes,
   inscription).
4. **Après** :
   - dans le terminal Railway, `alembic current` doit dire `c5priseenmain (head)` ;
   - `/api/health` doit répondre ;
   - ouvrez le lien privé de la démo et un vrai compte (accueil, un marché, « Voir ce que verra votre
     partenaire », `/app/exemple`) ;
   - le lendemain matin, vérifiez le compte rendu de la tournée des alertes : il porte maintenant
     `weekly_not_due`.

### Revenir en arrière

L'ancienne image ne connaît pas `c5priseenmain`. Si elle démarre sur la base migrée, son `entrypoint.sh` s'arrête
sur « Can't locate revision ». Il faut donc **d'abord redescendre la base, depuis la NOUVELLE image, puis
seulement relancer l'ancienne** :

1. dans le terminal Railway du déploiement actuel (nouvelle image) : **`alembic downgrade c4montantseul`**. Cela
   retire les trois colonnes. On perd l'état replié des premiers pas, la carte « Faites-vous trouver » et les
   réponses « Je ne sais pas », rien d'autre ;
2. vérifiez `alembic current` : `c4montantseul (head)` ;
3. redéployez l'image précédente (`0afc1ed`, bouton « Redeploy » du déploiement précédent dans Railway) ;
4. **à savoir** : l'ancien code ne lit pas la nouvelle mémoire des alertes. À sa première tournée, il renverra
   **une fois** les marchés déjà envoyés depuis la mise en ligne qui passent son seuil. Dans la vérification, 3
   marchés sur 7 ont été renvoyés à l'alerte du chef de file. Ensuite, plus rien n'est renvoyé. Si vous remettez
   la nouvelle version, elle relit cette mémoire mêlée sans rien renvoyer (vérifié). Toutes les autres données
   écrites par la nouvelle version restent lisibles par l'ancienne (vérifié).

Ne relancez jamais l'ancienne image avant l'étape 1.

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
| SQLite | 2 381 | 2 381 | 0 | 0 | 0 |
| PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`) | 2 381 | 2 381 | 0 | 0 | 0 |

Le total vaut 2 205 (production) + 126 (vague 2b) + 50 (moteur). La première suite réunie, avant l'alignement du
test cité plus haut, donnait 2 380 sur 2 381.

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

**Fichiers servis :**

- `scripts/sri_update.py --check` : empreintes à jour ;
- `node --check` : 8 fichiers JS servis et 9 scripts intégrés aux pages, 0 erreur ;
- `scripts/i18n_ajouter.py --check` : 789 clés, néerlandais et espagnol ;
- gabarit de l'application compilé par le Vue du dépôt : 3 tests.

**Démo de pitch.** Toutes les réponses de lecture de la démo, plus le lien du partenaire de Kerhel, ont été
relevées avec le code de production puis avec le code réuni, sur une base neuve. Les jetons et les dates sont
neutralisés. Sur **190 réponses, 186 sont identiques** et 2 ne diffèrent que par l'ordre de deux éléments créés
dans la même seconde. Les 4 autres ont seulement des champs ajoutés :

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
