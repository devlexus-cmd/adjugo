# Contrôle des bugs du 22/10/2026

Ce document est pour Eliot. Il dit quels bugs ont été corrigés (ce que le client voyait, ce qui change), lesquels
ont été rejetés et pourquoi, ce qui reste à décider, et ce qui a été vérifié à la fin.

**Où.** Branche `worktree-wf_d0e3d8c8-69b-1`, posée sur `cfe04e1` (la version en attente de mise en ligne, avec
l'écran du lot 1 du moteur). Dix commits « wip », un par groupe de bugs, puis celui de ce bilan :

| Groupe | Commit | Bilan détaillé |
|---|---|---|
| Analyse d'un marché | `9ebfdef` | `docs/LECTURE_INTEGRALE.md` § 2.1, 2.6, 2.7 |
| Comptes, équipe, abonnement | `936061d` | `docs/ESSAI_GARDE_FOU.md` § 10 |
| Co-traitance | `e5cf686` | `docs/COTRAITANCE_V2_ARCHITECTURE.md` (« Contrôle des bugs 22/10 ») |
| Marché (devis, export, pièces) | `473e3f1` | `docs/REORGANISATION_V2A.md` § N |
| Recherche de marchés, alertes | `833696e` | `docs/MOTEUR_LOT1.md` § R.1 à R.14 |
| Rédaction en groupement | `8d1950f` | `docs/REDACTION_V4_GROUPEMENT.md` § 22 |
| Écrans (dates, langues, téléphone) | `9521da5` | `docs/REORGANISATION_V2A.md` § O |
| Démo et site public | `a545256` | `docs/REORGANISATION_V2A.md` § P |
| Données (sauvegarde, inscription, attestations) | `f31ebef` | `docs/REORGANISATION_V2A.md` § Q |
| Deuxième passe (régressions, parcours client, cloisonnement, textes) | `0bb450d` | `docs/REORGANISATION_V2A.md` § R |

**Ce qui ne change pas.** Aucun prix, aucun quota, aucune offre. Aucune migration de base de données. Les pages
juridiques (`app/static/legal`, `scripts/build_legal.py`) ne sont pas touchées. Les données de la démo de pitch
(`demo_seed.py`, `demo_groupement.py`, `demo_lots.py`) ne sont pas touchées. Rien n'a été mis en ligne ni poussé.

**En chiffres.** 90 bugs corrigés : 63 à la première passe (9 zones), 27 à la deuxième. Chaque correction a un
test qui échouait avant elle. 4 signalements rejetés, avec leur raison (section 3). 3 signalements de la première
liste n'ont pas de verdict enregistré et se reproduisent encore : ils sont laissés à votre décision (section 4.1).
La suite passe en entier sur SQLite et sur PostgreSQL (section 5).

---

## 1. Corrigés à la première passe (63)

### Analyse d'un marché (6)

1. **Analyse dite « non débitée » alors qu'elle l'était** (majeur). Après une analyse faite tout de suite (petit
   dossier), l'état d'une ancienne lecture en échec restait affiché : « erreur, votre analyse n'a pas été
   débitée ». Maintenant, l'état repart de zéro quand aucune lecture ne tourne.
2. **Tableur mal lu** (mineur). Des cellules sans adresse s'écrasaient toutes dans la première colonne, et la pièce
   était quand même dite « lue en entier ». Elles sont maintenant rangées à leur place.
3. **Dates des tableurs en nombres** (mineur). Une date s'affichait « 46371 ». Elle s'affiche « 15/12/2026 » (ou
   « 15/12/2026 09:30 », « 09:30 »). Les durées et les nombres ordinaires ne changent pas.
4. **Lieu sur plusieurs départements** (mineur). « Rennes (35) et Brest (29) » n'était lu que « 35 » : une
   entreprise du 29 était dite « hors zone ». Le marché est maintenant dans la zone dès qu'un de ses départements y
   est, pour le score seul comme pour le groupement.
5. **Pastille « Seul » de « Trouver des marchés »** (majeur). Elle pouvait dire « Bon potentiel en groupement » à
   côté de « À plusieurs Y % ». Elle donne maintenant le verdict seul.
6. **Lien « · réf » vide** (majeur). Un marché créé à la main puis analysé depuis un dossier importé affichait un
   lien de référence sans source. Il n'apparaît plus.

### Comptes, équipe, abonnement (8)

1. **Transfert de propriété** (majeur). Le forfait, le client Stripe, le paiement à l'usage, les compteurs du mois
   et l'essai restaient chez l'ancien propriétaire : une organisation Pro redevenait gratuite, un essai fini
   rouvrait l'IA. Tout passe maintenant au nouveau propriétaire.
2. **Rôle après le transfert** (majeur). La fenêtre disait « Vous deviendrez simple administrateur », le logiciel le
   mettait « membre » (il ne pouvait plus inviter). Il devient administrateur.
3. **Collègue invité sans fin d'essai** (majeur). Retiré de l'organisation, il gardait 5 analyses par mois sans fin.
   Il reçoit une date de fin d'essai (invitation + 30 jours). Tant qu'il est membre, rien ne change.
4. **Paiement lancé par un collègue** (mineur). Le paiement était rattaché au collègue : l'organisation ne passait
   pas en Pro. Il est rattaché au propriétaire ; un simple membre reçoit un refus lisible.
5. **« Gérer mon abonnement » pour un administrateur** (mineur). Il ouvre maintenant le compte Stripe du
   propriétaire. Un simple membre reçoit un refus lisible.
6. **Nom d'entreprise fait d'espaces à l'inscription** (mineur). Les espaces sont retirés ; trop long, le nom est
   refusé avec une phrase au lieu d'une erreur interne.
7. **Nom du collègue invité** (mineur). Il est nettoyé comme à l'inscription ; vide, on prend le début de son
   adresse.
8. **« Email renvoyé » affiché sans envoi** (majeur). Le message n'apparaît que si le courriel est vraiment parti.
   Sinon l'écran le dit, et l'essai manqué ne compte pas dans le plafond de 5 par jour.

### Co-traitance (11)

1. **« Total prévisionnel » faux** (mineur, n° 30). Il additionnait le prix du sous-traitant et pouvait dire
   47 000 au lieu de 100 000. Il suit maintenant le calcul de la convention et dit d'où vient la part du chef de
   file.
2. **Offre restée figée** (majeur). Une convention modifiée repassait en brouillon mais l'offre commune restait
   figée. Elle est défigée aussi.
3. **Retirer un sous-traitant annulait la convention** (majeur). Les accords sont maintenant gardés. Retirer un
   partenaire du groupement l'annule toujours.
4. et 5. **Lien en lecture seule traité comme un membre** (majeurs). Il bloquait la convention (« n'a pas encore
   soumis sa part »), comptait dans « parts reçues X sur Y » et dans « Prêt à déposer ». Il n'y entre plus.
6. **Invitation du réseau sans réponse** (mineur). Le chef de file voyait « brouillon » et « prix saisi » avant toute
   réponse. Ce n'est plus montré.
7. **Renvoyer un lien expiré** (majeur). Le logiciel disait « Invitation renvoyée » et envoyait un lien mort. Il
   répond maintenant « Ce lien a expiré — créez une nouvelle invitation » et le bouton n'est plus proposé.
8. **Courriels vers un lien expiré** (majeur). Rappels et alertes d'attestations ne partent plus vers un lien
   expiré.
9. **« À deux membres, le total révèle la part de l'autre »** (mineur). L'avertissement compte maintenant les
   membres du groupement, plus les liens.
10. **Total envoyé au sous-traitant** (mineur). Le courriel « offre figée » ne part plus au sous-traitant ni au lien
    en lecture seule, et le prix du sous-traitant n'entre plus dans le total.
11. **« vous propose de intervenir »** (mineur). Le courriel dit « vous propose d'intervenir ».

### Marché : devis, export, pièces (6)

1. **Devis invisibles entre collègues** (majeur, n° 27). Un devis fait par un collègue n'apparaissait pas sur la page
   du marché, et deux collègues pouvaient émettre deux « DEV-2026-001 ». Devis et factures sont maintenant à
   l'échelle de l'entreprise.
2. **Deux pièces de même nom dans le ZIP** (mineur, n° 28). La seconde écrasait la première. Elle devient
   « …_2.pdf ».
3. **« / » dans l'intitulé du marché** (mineur, n° 29). Il créait des sous-dossiers dans le ZIP. Les noms de fichiers
   remplacent ces caractères par « _ » ; l'intitulé reste intact dans le sommaire.
4. **Attestation URSSAF comptée comme attestation fiscale** (majeur). Dans « Pièces à fournir » et « Avant de
   déposer », la catégorie « Fiscal et social » valait les deux. Le nom du document décide maintenant. « RIB » et
   « RGE » ne sont plus reconnus au milieu d'un mot (« Avis d'attribution »).
5. **Formulaires en double dans le dossier** (majeur). Quand deux collègues préparaient les documents du même
   marché, le dossier gardait deux DC1. Il n'en garde plus qu'un, le dernier.
6. **Devis modifié avec une ligne négative** (mineur). Il était accepté, et des valeurs vides cassaient la liste des
   devis. C'est maintenant refusé avec une phrase.

### Recherche de marchés et alertes (12)

1. **Alertes marquées « déjà vues » sans courriel** (n° 8). Si le courriel ne partait pas, les marchés n'étaient
   jamais envoyés. Ils repartent au passage suivant.
2. **« Charger plus » sans suite** (n° 10). Le bouton apparaissait alors qu'aucune source n'avait d'autres résultats.
   Il ne s'affiche plus que si une source a vraiment une page suivante.
3. **Rectificatif du BOAMP mal lu** (n° 11). Un rectificatif qui écrit « des offre » au singulier n'était pas lu.
   La nouvelle date est reprise (30/10/2026 pour l'avis 26-99040) ; c'est la seule lecture qui change sur les 127
   rectificatifs réels rejoués.
4. **Fins de contrat confondues** (n° 12). Tous les contrats d'un même acheteur avaient la même clé. Chacun a la
   sienne.
5. **Codes CPV mal envoyés** (n° 13). La liste des codes partait comme un seul code. Chaque code part, jusqu'à 5.
6. **Alerte d'un collègue** (n° 14). Elle lisait une fiche entreprise vide. Elle lit celle de l'organisation.
7. **Trois seuils « par défaut » différents** (n° 15). Un seul défaut, 75 et 40, partout. Rien ne change pour un
   compte qui a enregistré ses critères.
8. **Nom d'alerte trop long** (n° 16). Erreur interne sur PostgreSQL. Le nom est coupé, les mots-clés trop longs
   refusés avec une phrase.
9. **« tous métiers »** (n° 17). L'écran disait « tous métiers » alors que « travaux » est cherché. Il le dit.
10. **Alerte sur un autre pays** (n° 18). Elle gardait les départements français cachés. Elle ne garde que ce qui est
    visible, et la liste affiche le pays.
11. **Département non reconnu** (n° 19). « 29000 » était écarté en silence (recherche sur toute la France). Il est
    refusé avec la phrase « « 29000 » n'est pas un numéro de département : indiquez par exemple 29, 56, 2A ou 974. »
12. **Fin de contrat déjà passée** (n° 20). La carte le dit maintenant : « fin estimée déjà passée ».

### Rédaction en groupement (4)

1. **Téléphone, « Qui écrit quoi »** (mineur). Le bouton « Rédiger à sa place » menait à un écran qui ne le
   permet pas. Il n'est plus proposé sur téléphone ; la phrase dit « Depuis un ordinateur, vous pouvez … ».
2. **« Demander les parts » sautait un partenaire sans le dire** (mineur). L'écran nomme maintenant le partenaire
   qui ne peut plus rédiger et pourquoi (« son lien a expiré »).
3. **Carnet de notes d'un marché à lots** (mineur). « Note d'ensemble, lot 2 » devient « Note d'ensemble, partie
   (lot 2) ».
4. **Dossier « sans IA »** (mineur). Le courriel ne promet plus au partenaire l'aide d'Adjugo qu'il ne peut pas
   utiliser.

### Écrans : dates, langues, téléphone (6)

1. **« À faire » compté à l'heure universelle** (mineur, 2 heures de moins qu'à Paris en été). Entre minuit et 2 h
   à Paris, la date limite de la veille apparaissait encore. Le compte se fait sur le jour de l'appareil.
2. **« Il vous reste N jours »** (mineur). Même défaut pour le compte à rebours du partenaire, sur ses deux écrans.
   Les deux disent maintenant la même chose, en métropole comme aux Antilles.
3. **Date limite « 2026-10-24 »** (mineur). L'en-tête du marché sans analyse l'écrit « 24/10/2026 ».
4. **Titre de l'onglet resté en français** (mineur). Il suit la langue de l'écran.
5. **Barre basse coupée à 375 px** (mineur). « Mijn aanbes… » en néerlandais. Le libellé tient ; en français rien ne
   change.
6. **Lignes de « À faire » en français** (mineur). Elles sont traduites en néerlandais et en espagnol.

### Démo et site public (5)

1. **Adresse officielle de /acheteur** (mineur). La page se déclarait à l'adresse technique de l'hébergeur. Elle se
   déclare à `https://adjugo.pro/acheteur`.
2. **Liens morts dans le pied de page de /acheteur** (mineur). « API · /docs » et « OpenAPI » répondaient 404 en
   production. La colonne est retirée.
3. **« (ou lancez la démo) »** (mineur). La phrase proposait une démo que le visiteur ne peut plus lancer. Elle dit
   « Connectez-vous pour utiliser cette fonction. »
4. **Premier écran de /acheteur cassé à 1 280 px** (mineur). La carte sortait de l'écran. Elle tient, de 960 à
   1 920 px ; tablette et téléphone ne changent pas.
5. **« signalé au réseau le 2026-10-22 »** (mineur). La date s'écrit « 22/10/2026 ».

### Données : sauvegarde, inscription, attestations (5)

1. **Restauration impossible sur PostgreSQL** (majeur, n° 31). La procédure de `docs/GO_LIVE.md` échouait dès la
   première table, et la première inscription après une restauration était refusée. Elle passe, deux fois de suite.
2. **Sauvegarde pas faite d'un seul coup** (majeur, n° 32). Une pièce pouvait y figurer sans son marché. Toutes les
   tables sont lues dans un même instantané.
3. **Double clic sur « Créer mon compte »** (mineur, n° 33). Erreur interne au second envoi. Il reçoit « Cet email est
   déjà utilisé », et l'écran n'envoie plus deux fois.
4. **Alerte d'attestations notée sans être partie** (majeur, n° 35). Si le service d'envoi était en panne, le
   journal disait « Adjugo vous a alerté » et l'alerte ne repartait jamais. Elle n'est notée qu'une fois partie.
5. **Attestation encore « valide » le lendemain de sa fin** (mineur, n° 37), entre minuit et 2 h à Paris, dans
   « Pièces à fournir » et l'état des attestations des partenaires. Le jour de Paris décide maintenant, comme dans
   Mes documents.

---

## 2. Corrigés à la deuxième passe (27)

La deuxième passe a cherché les effets de bord des corrections, puis suivi des parcours de client, le cloisonnement
entre partenaires et les textes. Les 27 signalements vérifiés sont corrigés dans `0bb450d`.

1. **« Total prévisionnel » disparu** (régression de la première passe). Un chef de file sans nom d'entreprise ne
   voyait plus le total, même avec tous les prix. Il le voit ; il ne peut toujours pas générer la convention sans ce
   nom.
2. **RIB au nom collé** (régression). « RIBBNP.pdf », « RIBdupont.pdf », « monrib.pdf » n'étaient plus reconnus. Ils
   le sont ; « attribution », « contribution » et « charges » restent écartés.
3. **Date limite jamais enregistrée** (majeur). Un marché créé par « Analyser ce marché » affichait sa date limite,
   mais ne l'enregistrait pas : courriel d'invitation « pas encore indiquée », aucun rappel J-3 ou J-1, attestations
   vérifiées « à aujourd'hui seulement ». La date de l'avis officiel (sinon celle de l'analyse) est enregistrée,
   jamais par-dessus une date déjà là.
4. **Adresse écrite deux fois** (majeur). Avec « Démarrer avec mon SIRET », DC1, DC2, ATTRI1 et la convention
   écrivaient « 3 rue du Port 29200 Brest 29200 BREST ». L'adresse lue au registre ne garde plus le code postal et
   la ville. Les fiches déjà enregistrées ne sont pas réécrites (section 4.2).
5. **Seuils du partenaire avec compte** (mineur). « CA cumulé suffisant » s'affichait même quand la donnée disait le
   contraire. Le texte suit la donnée, comme sur le lien.
6. **« Ce que le groupement comble »** (mineur, visible dans la démo). Le partenaire lisait « hors de votre zone
   d'intervention » et « à confirmer auprès du partenaire », des phrases écrites pour le chef de file. Il lit des
   libellés neutres (« Lieu d'exécution », « Qualifications exigées »). Vérifié dans la démo (section 5).
7. **Bloc des membres figé après l'envoi** (mineur). Après « Soumettre au chef de file », il disait encore « parts
   reçues 0 sur 1 ». Il se met à jour sans recharger.
8. **« Toutes les parts sont reçues » avec zéro part** (mineur). Quand le seul partenaire avait décliné. La barre dit
   maintenant « Aucune part reçue : invitez un partenaire ». Kerhel ne change pas.
9. **Heures du suivi décalées de 2 heures** (mineur, 1 heure en hiver). « dernière consultation », « Email envoyé » et l'historique des
   simulations s'affichent à l'heure locale.
10. **« À venir » quand les sources ne répondent pas** (mineur). L'écran affirmait « Aucune échéance proche ». Il dit
    quelle source n'a pas répondu. Débit et remboursement inchangés.
11. **Total donné à un lien en lecture seule** (majeur, cloisonnement). Son journal, la vérification du journal et
    les exports lui donnaient le total de l'offre commune. Plus nulle part.
12. **Brouillon d'une invitation du réseau sans réponse chez le chef de file** (majeur, cloisonnement). Ses capacités
    entraient dans « Mes partenaires » et ses dépôts de pièces dans les notifications. Plus avant une vraie réponse.
13. **Un collègue pouvait décliner l'invitation du réseau** (majeur). L'écran disait que seul le propriétaire le
    peut. C'est maintenant vrai : un collègue reçoit un refus avec une phrase ; sans session, l'adresse doit être
    prouvée par code.
14. **Coffre-fort croisé lu par un lien en lecture seule** (mineur). Il recevait l'état des attestations des
    membres. Refusé avec une phrase.
15. **ATTRI1** (majeur). La ville du candidat et la date étaient écrites dans la case de l'acheteur. Cette case reste
    vide.
16. **DC4** (majeur). Lieu et date tombaient dans la zone où signe l'acheteur, avec la ville du titulaire pour le
    sous-traitant. Ils vont sur les bonnes lignes, avec la ville du sous-traitant ou une ligne à remplir.
17. **Documents datés de la veille entre minuit et 2 h** (mineur). Formulaires, estimation, compte-rendu, export ZIP :
    tous datés du jour de Paris.
18. **Courriel « Mes alertes »** (mineur). « clôture 2026-11-21+02:00 » devient « clôture 21/11/2026 » ; « acheteur
    n/d » devient « acheteur non précisé ».
19. **Rappel le jour même de la date limite** (mineur). Il disait « il vous reste 1 jour ». Il dit « C'est le dernier
    jour ».
20. **Journal d'accès en code** (mineur). « atelier.sans_ia », « user:2 », et « Vous » pour une alerte envoyée par
    Adjugo. Chaque ligne a une phrase, l'auteur est nommé, et les actions d'Adjugo portent « Adjugo ».
21. **« 1 jours » dans la convention** (mineur). « 1 jour ». Les conventions déjà générées gardent leur texte et leur
    empreinte (nouveau modèle de texte 3).
22. **Compte-rendu arrondi à l'euro** (mineur). « 125 000 € HT » au lieu de « 125 000,50 € HT ». Au centime, comme la
    convention.
23. **Sous-traitant rangé parmi les « partenaires du groupement »** dans le sommaire du ZIP (mineur). Deux rubriques
    séparées.
24. **Objet du courriel d'invitation d'un sous-traitant** (mineur). Il annonçait « un groupement ». Il dit « vous
    propose d'intervenir comme sous-traitant ».
25. **Refus d'un sous-traitant** (mineur). Le courriel au chef de file et la fenêtre de refus parlaient de
    « rejoindre le groupement ». Ils suivent le rôle.
26. **Invitation d'un collègue par un compte sans nom** (mineur). « vous invite à rejoindre » sans sujet. « Un
    collègue vous invite… ».
27. **« 1 j restants »** (mineur). « Essai gratuit · 1 j restant ».

---

## 3. Rejetés, avec leur raison (4)

1. **Limite de 2 collègues pendant l'essai** (liste « refusés »). Pendant l'essai, l'écran Abonnement promet « Accès
   complet niveau Pro » et les CGV (3.5) « l'ensemble des fonctionnalités au niveau de la formule Pro », mais le
   deuxième collègue est refusé (« Votre offre est limitée à 2 membre(s) »), alors que Pro en permet 10. Le défaut
   est réel, mais le corriger, c'est changer une limite d'offre ou les CGV : **à vous de trancher** (aligner l'essai
   sur Pro, ou écrire la limite de 2 dans l'écran et dans les CGV).
2. **Le compte démo peut créer, mettre en pause et supprimer des alertes** (recherche, n° 9). Ce n'est pas un écart :
   c'est une règle écrite (`tests/test_demo_sans_cout.py` classe ces écritures « sans coût », comme les contacts et
   les devis), la démo se remet à neuf toute seule et ses alertes ne déclenchent jamais de courriel. Bloquer ces
   routes serait une décision produit (`docs/MOTEUR_LOT1.md` R.13).
3. **Un sous-traitant voit le brouillon de la convention** (co-traitance, signalement n° 7). Ce comportement est
   voulu (commit `3686b2a`, bulle écrite exprès pour lui) ; la règle « ni texte, ni annexe, ni total » vise la
   convention générée, et en brouillon les prix des autres restent cachés. À vous de dire s'il faut aussi cacher le
   brouillon. À noter : la bulle « Les prix de vente n'apparaissent pas tant que la convention n'est pas générée »
   lui laisse croire qu'il les verra ensuite, ce qui n'arrivera jamais.
4. **Alertes de marchés marquées « déjà vues » sans courriel** (données, n° 30). Doublon du n° 8 de la recherche,
   déjà corrigé dans `833696e` ; revérifié sur `a545256`.

---

## 4. Ce qui est laissé

### 4.1 Trois signalements sans verdict enregistré

Pour ces trois signalements de la première liste, un dossier de vérification existe, avec sa sonde, mais aucun
verdict n'est arrivé jusqu'à la correction : ils n'ont été ni corrigés, ni rejetés. Je les ai relancés sur la
version finale (sondes des vérificateurs, copie de `0bb450d`) : **les trois se reproduisent encore.** Je ne les ai
pas corrigés dans cette étape de vérification finale ; ils demandent une petite passe à part.

- **Co-traitance, n° 12 (mineur).** Après une part soumise par le lien, l'invitation du réseau reste « À accepter ou
  décliner » dans la liste du partenaire, alors que le chef de file la voit répondue. Point à trancher avant de
  corriger : le bouton « Accepter depuis mon compte » sert aussi à rattacher l'invitation à son compte (« Partagé
  avec moi »), ce que l'envoi de la part ne fait pas. Passer le statut à « Acceptée » ferait disparaître ce bouton.
- **Données, n° 34 (mineur).** Deux premiers enregistrements de « Ce que je cherche » au même instant : le second
  reçoit une erreur interne (500), le premier est bien enregistré. Reproduit : `['500 IntegrityError', 200]`.
- **Données, n° 36 (mineur).** Même défaut pour la première fiche « Mon entreprise » d'un compte qui n'en a pas
  (inscription sans nom d'entreprise, compte Google). Reproduit : `[200, 500]`. Pour ces deux écrans, le bouton
  « Enregistrer » est désactivé pendant l'envoi : le double clic est bloqué, le cas reste possible avec deux onglets
  ouverts.

Deux vérifications de la deuxième passe (n° 13 et 22) ne figurent pas non plus dans la liste confirmée qui m'a été
transmise, et leur verdict n'y est pas. Je ne sais pas ce qu'elles ont conclu.

### 4.2 Choix qui vous reviennent (argent, offre, produit)

- **Transfert de propriété** : si le nouveau propriétaire avait déjà son propre client Stripe (un collègue qui a
  payé avant la correction), celui de l'organisation le remplace, et c'est noté dans le journal
  (`docs/ESSAI_GARDE_FOU.md` § 10).
- **Seuils « bon potentiel » et « peu adapté »** : un seul défaut, 75 et 40 ; les comptes qui ont enregistré leurs
  critères gardent les leurs (`docs/MOTEUR_LOT1.md` R.7).
- **« À venir », fenêtre des fins de contrat** : la fenêtre du serveur n'a pas changé, pour ne pas déplacer le repli
  payant (plus de recherches complémentaires lancées, donc débitées quand elles trouvent) ; seule la carte dit « fin
  estimée déjà passée » (R.12).
- **Devis et factures** : les numéros déjà émis en double par deux collègues ne sont pas renumérotés ; deux devis
  enregistrés à la même seconde peuvent encore avoir le même numéro (l'empêcher demande une migration) ; une liste
  de lignes vide reste acceptée à la modification (`docs/REORGANISATION_V2A.md` N).
- **Adresses déjà doublées** : les fiches enregistrées avant la correction gardent « … 29200 Brest 29200 BREST ».
  Les reprendre est une reprise de données à décider (R).
- **Journal du marché** : il garde le nom de fichier déposé par une invitation du réseau sans réponse (journal de
  l'entreprise, avec adresses IP) : à filtrer ou seulement à dire (R).
- **Invitation ordinaire (hors réseau)** : elle se décline toujours avec le seul lien, que le chef de file détient
  aussi ; le journal attribue alors le refus au partenaire (R).
- **Démo** : un marché créé dans la démo par « Analyser ce marché » porte maintenant la date limite de sa page. Les
  données de la vitrine ne changent pas.

### 4.3 Pages juridiques (signalé seulement)

- **CGV 3.5** : « l'ensemble des fonctionnalités au niveau de la formule Pro » pendant l'essai, alors que le
  logiciel limite l'essai à 2 membres (section 3, point 1). À aligner avec votre décision.

### 4.4 Défauts vus en passant, non corrigés (hors des listes)

- Classement des pièces du partenaire : « rib » et « rge » encore reconnus au milieu d'un mot (« Avis d'attribution
  2025.pdf » compté comme RIB) dans la liste de pièces du partenaire, le coffre-fort croisé et le suivi
  (`docs/REORGANISATION_V2A.md` N.6). La deuxième passe n'a corrigé que « Pièces à fournir ».
- « Demander les parts » : la confirmation dit « Chacun reçoit par email » même pour un partenaire sans adresse.
- Lien du partenaire (invite.html) : aux Antilles, une date limite du 24 s'affiche « 23 octobre » (O.7).
- Écran Abonnement : la carte « API & développeurs » mène à /docs et /openapi.json, fermés en production.
- Récapitulatif du chef de file non renvoyé s'il échoue seul ; partenaire sans adresse compté parmi les
  « prévenus » ; « La date limite du marché est dépassée » et paliers des rappels de co-traitance encore comptés à
  l'heure universelle ; ordre des versions d'une pièce dans une restauration par paquets (lu dans le code, non reproduit) (Q).
- Encadré « Offre commune figée » du suivi : l'écran arrondit à l'euro (125 001 €) quand la convention dit
  125 000,50 €.
- Rappel planifié de la part : « ajouter votre part au groupement de … » même pour un sous-traitant.

---

## 5. Vérifications finales (sur `0bb450d`, tous les commits réunis)

| Contrôle | Résultat |
|---|---|
| Suite complète SQLite (TZ=UTC) | 2 551 sur 2 551, aucun test sauté, sortie 0 |
| Suite complète PostgreSQL 16.2 jetable (`scripts/tests_postgres.py`) | 2 551 sur 2 551, aucun test sauté, sortie 0 (692 s), serveur arrêté et effacé |
| Nombre de tests | 2 428 sur `cfe04e1`, 2 551 maintenant (123 nouveaux, dans 11 fichiers `tests/test_controle_bugs_*.py`) |
| Tests existants modifiés | 5 fichiers, aucune vérification affaiblie (raison dans chaque bilan) |
| Empreintes SRI (`scripts/sri_update.py --check`) | à jour |
| `node --check` | 6 fichiers JS de `app/static` et 9 scripts intégrés aux pages HTML : tous valides |
| Traductions (`scripts/i18n_ajouter.py --check`) | 845 clés, néerlandais et espagnol |
| Gabarit de l'application compilé par Vue | dans la suite (`test_gabarit_compile_par_le_vue_du_depot`) |
| Pages juridiques | aucune ligne changée depuis `cfe04e1` |

**Démo de pitch par le lien privé, dans un vrai Chromium, à 1 280 et 375 px.** Serveur local à base jetable,
démo publique fermée, clé de test générée dans un fichier et jamais affichée, courriels, IA et Stripe coupés, toute
requête vers l'extérieur bloquée (seules les polices de Google ont été demandées, et bloquées). Parcours : page
« /demo » (la clé quitte la barre d'adresse), « Espace entreprises », Accueil, Mes marchés, Trouver des marchés,
Partenaires, Mes documents, Mon entreprise, Abonnement, le marché « toiture », le gymnase de Kerhel, le lien du
partenaire Breizh Désamiantage, puis « Espace collectivités », et une mauvaise clé (« plus valide »). Résultat :
25 écrans, aucun débordement de côté à 375 px, aucune erreur de script, aucun émoji. Kerhel garde « 1 sur 1 part
reçue » et « Toutes les parts sont reçues ». Le lien de Breizh Désamiantage affiche « Ce que le groupement
comble : Métier du marché, Lieu d'exécution, Chiffre d'affaires minimum exigé, Qualifications exigées », sans
« votre activité » ni « auprès du partenaire ». L'heure de la dernière consultation est à l'heure de Paris. Seule
réponse en erreur relevée par le navigateur : la rédaction commune du lien du partenaire (404 « Le chef de file n'a
pas encore préparé le dossier de présentation commun »), attendue pour Kerhel et gérée par la page.

**Environnement de test.** Le nettoyage automatique de /private/tmp a vidé, le 23/10 à minuit, les environnements
Python prévus pour les tests (`venv312lock`, `venvpg`). Je les ai reconstruits : `venv312lock` depuis
`requirements.lock` avec les empreintes (78 paquets, identiques au fichier), `venvpg` avec pgserver 0.1.4. Les
commandes de la consigne marchent de nouveau.
