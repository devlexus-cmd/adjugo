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
| **B2** marché d'exemple | Une page à part, `/app/exemple`, en lecture seule : le parcours d'un marché à plusieurs jusqu'à « Seul 43 % · À plusieurs 100 % », puis l'écran du partenaire (§ 7.5, D13 a) | § B2 |

---

## B2. Le marché d'exemple

Tests : `tests/test_reorganisation_v2b_exemple.py` (15 tests : adresse et rubrique, fichier servi et lu, chiffres
recalculés par le moteur, cohérence des montants, mention sur chaque bloc, noms de la démo seulement, analyse sans
« No-Go » ni injonction, lecture seule sous Node avec les vraies méthodes, rien ne change côté serveur, entrée,
traductions, 375 px et accessibilité, contrat) ; `tests/test_demo_sans_cout.py` (la démo et le lien privé l'ouvrent sans
coût). Aucune migration.

### B2.1 Ce qu'on voit

Une page à part, à l'adresse **`/app/exemple`** (vue `exemple`, titre « Marché d'exemple », sa phrase dans la bulle (i)
de l'en-tête). Elle range les blocs de la page d'un marché, avec les mêmes classes (barre d'étapes, colonnes « Seul /
À plusieurs », manques, tableau de répartition, liste « Avant de déposer ») :

| Bloc (`data-test`) | Contenu |
|---|---|
| `exemple-entete` | Le marché (objet, client, procédure, montant, lieu, délai, 3 parties), les deux entreprises (l'entreprise qui répond, son partenaire), « Lecture seule : rien de cet exemple n'est enregistré dans votre compte. » |
| `exemple-etapes` | Lire · Décider · Préparer · Déposer, en ancres (`rnScrollTo`), puis « Aller à l'écran du partenaire » |
| `exemple-lire` | « Analyse du dossier du marché » réécrite (ce que dit le dossier, sans conseil), « Dossier lu en entier : 4 pièces », trois phrases du règlement avec leur article, « Comment l'offre sera notée » (Prix 50 %, Valeur technique 50 %) |
| `exemple-decider` | « Répondre à plusieurs ? » : l'avertissement (capacités déclarées, à confirmer), **Seul 43 %** (À étudier) et **À plusieurs 100 %** (Bon potentiel en groupement), les 6 critères « seul → à plusieurs » avec « apporté par », les 4 manques avec la phrase du dossier quand il y en a une, « Qui me complète ? » (le partenaire, depuis Mes partenaires), le calcul du chiffre d'affaires cumulé, puis « Seul 43 % · À plusieurs 100 % » et la décision, prise par l'entreprise |
| `exemple-preparer` | L'invitation acceptée, « Parts reçues 1 sur 1 », « Accords des membres 2 sur 2 », la répartition (prix de vente de chacun, total de l'offre commune), « Ce que chacun voit » |
| `exemple-deposer` | « Avant de déposer : 3 contrôles sur 4 », le manque nommé (l'attestation URSSAF du chef de file expire avant la date limite), « Adjugo nomme ce qui manque, sans rien bloquer » |
| `exemple-partenaire` | L'écran du partenaire, dans un cadre : « Votre part dans « … » », chef de file, rôle et partie, « à plusieurs 100 % » et « Vous apportez », son prix (« Le détail de vos postes, vous seul le voyez »), le total commun et l'avertissement « À 2 membres… » ; puis « Il voit » / « Il ne voit pas » (ni le pourcentage seul du chef de file, ni le détail de ses prix, ni ses pièces ni son savoir-faire) |

En bas : « Sur vos marchés, chaque étape se fait depuis la page du marché », « Trouver des marchés » et « Retour ».

**Entièrement fictif, et dit comme tel (D13 a).** Chaque bloc porte la pastille
**« Exemple · entreprises et client fictifs »** (une par carte, test) ; la bulle de l'en-tête dit que tout est inventé et que les pourcentages sont ceux du
calcul d'Adjugo avec les capacités de l'exemple. Les seuls noms sont ceux de la démonstration de pitch, contrôlés contre
le registre des entreprises le 13/10/2026 : **Bâtiment de l'Ouest**, **Breizh Désamiantage**, **Kerhel Agglomération**
(et le marché « Réhabilitation énergétique — Gymnase de Kerhel »). Aucun nom nouveau n'a été nécessaire. Aucune
personne, aucun SIRET ni SIREN, aucune adresse électronique, aucun téléphone, aucun lien ; seuls les départements sont
réels (Loire-Atlantique, Morbihan), comme dans la démo.

**L'analyse réécrite** : celle de Kerhel dans la démo prescrit « La bonne stratégie est claire : répondre en
GROUPEMENT… » et « à étudier sérieusement, mais uniquement en groupement » (étude, § 2.10). L'exemple dit ce que contient
le dossier, ce qui manque seul et ce qu'apporte le partenaire ; la phrase de décision dit que
c'est l'entreprise qui décide. Test : aucun mot banni, aucune injonction (« il faut », « devez », « foncez »,
« recommand… », « à écarter », « ! »…), jamais « vérifié » (décision 9 : rien ici n'est une identité contrôlée au
registre), zéro émoji.

### B2.2 Les données : un fichier statique versionné

`app/static/exemple-marche.json`, servi tel quel au navigateur (`/static/exemple-marche.json`, en-tête de non-mise en
cache comme tout `/static`). Ni base, ni IA, ni réseau. Lu une fois par l'écran (`exempleCharger`, `fetch` du fichier
seul) et contrôlé (`exempleValide`, fonction pure en tête de `app.js`) : s'il manque une partie, la page dit
« L'exemple n'a pas pu être chargé. Réessayez dans un instant. » avec « Réessayer », jamais un exemple à moitié. Textes
rendus en `{{ }}`, jamais `v-html`. Les montants sont des nombres (`eurExemple` les écrit « 280 000 € HT »).

**Les chiffres ne sont pas inventés** : le bloc `calcul` du fichier (non affiché) porte les données de l'exemple
(exigences du marché, capacités des deux entreprises, critères) ; le test les passe au moteur d'Adjugo
(`groupement_scoring.score_groupement`, le délai de réponse compté à 60 jours) et retrouve exactement ce que la page
affiche : 43 et 100, les verdicts, les points de chacun des 6 critères, « apporté par », les 4 manques seul (tous
comblés à plusieurs), le chiffre d'affaires cumulé (3 350 000 €) et l'avertissement « capacités déclarées ». Les trois
phrases citées sont celles du règlement fictif de la démo (`demo_groupement.EXIGENCE_CA`, `EXIGENCE_QUALIFICATIONS`,
`EXIGENCE_CAPACITES`), mot pour mot. Les montants s'additionnent (970 000 + 280 000 = 1 250 000 € HT, le total que
voit aussi le partenaire), « N sur M » partout ailleurs (décision 8).

### B2.3 Il ne se mélange jamais aux vraies données

- **Aucune écriture, aucun appel à l'API** : ni `this.api()`, ni `openAo`, ni `this.projects` dans les méthodes de la
  page ; aucun champ, aucun `v-model`, aucun formulaire ; les seuls gestes sont « Retour », les ancres, « Réessayer » et
  « Trouver des marchés » (test). Sous Node, avec les vraies méthodes `go` et `exempleCharger` : ouvrir l'exemple lit
  le seul fichier statique, n'appelle aucun chargement de l'API ni `openAo`, et Mes marchés reste tel quel.
- **Jamais dans Mes marchés** : il n'a ni identifiant ni statut ; il n'entre dans aucune liste, aucun filtre, aucune
  pastille, aucune ligne « À faire ».
- **Exclu des compteurs, des alertes, du quota, des statistiques et de l'historique du réseau** : contrôlé côté
  serveur (Mes marchés, statistiques, compte et quota, abonnement, notifications, tableau de bord des groupements,
  groupements, « Où je suis partenaire », pièces à renouveler, historique du réseau, alertes : identiques avant et après
  l'ouverture de l'exemple).
- **Mesure d'usage** : comme chaque écran, son ouverture est comptée par la mesure ANONYME de la vague 1
  (`ECRANS` reçoit `exemple` : jour, écran, nombre ; ni compte, ni organisation ; jamais la démo). C'est la seule trace
  qu'il laisse, et aucune mesure nominative n'existe.

### B2.4 Adresse, rubrique, entrée

- **Adresse** : `ADRESSES.exemple = "exemple"` → `/app/exemple` (lien, favori, rechargement, précédent et suivant,
  comme tout écran de la vague 2a) ; « Retour » fait comme le bouton précédent quand on vient d'un écran de
  l'application, sinon il ouvre l'accueil (`exempleRetour`).
- **Rubrique** : la page est rangée sous l'Accueil (`RUBRIQUES`, sans onglet ni entrée de menu : étude, § 10), qui reste
  surligné, menu latéral et barre basse ; l'en-tête dit « Marché d'exemple » (`enteteTitre`), pas « Accueil ».
- **Entrée posée par ce chantier** : en bas de « Répondre à plusieurs ? » (étape Décider de chaque marché, démo
  comprise), « Le parcours en entier sur un marché fictif : voir un exemple » (un vrai lien vers `/app/exemple`). Les
  autres entrées (états vides de l'accueil et de Mes marchés, premiers pas : étude § 7.3) sont celles du chantier B1,
  par la même adresse.

### B2.5 La démonstration de pitch ne change pas

Aucun fichier de la démo n'est modifié (`demo_seed.py`, `demo_redaction.py`, `demo_groupement.py`, `demo_carnet.py`,
`acheteur_demo_seed.py`). Comparé par script (`scratchpad/b2/demo_avant_apres.py` de la session) : base neuve, démo
recréée comme au démarrage, toutes les routes de lecture `GET /api/…` appelées par la session démo (PME et
collectivités, marchés « toiture » et Kerhel), plus le lien du partenaire de Kerhel ; textes des PDF lus page par page ;
jetons, empreintes et horodatages neutralisés. Code de production `0afc1ed` puis code de ce chantier : **189 réponses
sur 190 identiques** ; la seule différence est le manifeste public des empreintes des scripts (`app.js` et `i18n.js`
ont changé). À l'écran, la démo gagne seulement la ligne « voir un exemple » en bas de « Répondre à plusieurs ? ».

Dans la démo (et par le lien privé), l'exemple s'ouvre sans coût : page et fichier servis, aucune IA, aucun courriel,
aucun fichier rangé, aucun appel réseau, l'ouverture n'est pas comptée, Mes marchés identique
(`test_marche_d_exemple_ouvert_a_la_demo_sans_cout`, et `_exemple_dans_la_demo` rejoué par
`test_lien_prive_de_bout_en_bout`).

### B2.6 Repères, textes, traductions

| Repère | Zone |
|---|---|
| `vue-exemple` | La page (section de vue, dans `contenu`) |
| `exemple-entete`, `exemple-etapes`, `exemple-lire`, `exemple-decider`, `exemple-preparer`, `exemple-deposer`, `exemple-partenaire` | Ses blocs (dans `vue-exemple`) |

`ZONES` du socle (`tests/test_reorganisation_v1_socle.py`, groupe `vague2b_exemple`) suit. Tests mis à jour, chacun
avec sa raison en commentaire : `test_reorganisation_v1_menu.py` (« chaque écran en 2 clics au plus » : l'exemple est
une page à part, sans entrée de menu), `test_reorganisation_v1_socle.py` (les repères), `test_demo_sans_cout.py`
(l'exemple dans la démo et par le lien privé).

Décision 16 : 35 libellés traduits (636 → 671 clés, `scripts/i18n_ajouter.py --check`) : le titre et sa bulle, la
mention, les titres et étiquettes de la page, le message d'erreur, « Réessayer », l'entrée « voir un exemple ». Le
contenu du fichier (le marché fictif, en français) n'est pas traduit, comme les données de la démo.

Styles : un bloc `.ex` à la fin de `styles.css` (la mention, les deux entreprises, le cadre de l'écran du partenaire,
« Il voit / Il ne voit pas ») ; une colonne à 640 px et moins. Pas de refonte graphique : couleurs, police et classes
de la page du marché.

### B2.7 Vérifications

- Suite complète verte (SQLite, TZ=UTC) ; `scripts/sri_update.py --check` ; `node --check` de `app.js` et `i18n.js` ;
  gabarit de `app.html` compilé par le Vue du dépôt ; `scripts/i18n_ajouter.py --check` (671 clés) ; garde des mots
  bannis verte.
- Aucune migration, aucune route nouvelle : rien à passer sur Postgres (la seule écriture est le compteur anonyme
  existant, déjà testé sur Postgres en vague 1).
- **Navigateur réel** (serveur local sur le code de ce chantier, base jetable, démo par **lien privé** avec une clé
  jetable écrite dans un fichier de la session et jamais affichée, `DEMO_PUBLIC=0`, réseau sortant coupé, courriels et
  IA coupés) : démo → Kerhel → « voir un exemple » → la page (1 280 px, clair) : en-tête, Lire, Décider (43 % / 100 %,
  critères, manques, « Qui me complète ? », cumul), Préparer (répartition, total), Déposer (3 sur 4), écran du
  partenaire ; « Retour » rend Kerhel (`/app/marches/2`), suivant rouvre `/app/exemple` ; une seule requête, le
  fichier statique ; Mes marchés garde ses 7 marchés. Rechargement de `/app/exemple` à 375 px en sombre : aucun
  défilement horizontal, barre basse sur « Accueil », bloc par bloc lisible (tableau de répartition en lignes, écran du
  partenaire). Compte de test local (créé par la route d'inscription, adresse confirmée en base) : `/app/exemple`
  s'ouvre, ancres et « Aller à l'écran du partenaire » mènent à leur bloc, néerlandais (libellés traduits). Console
  sans erreur de script.

### B2.8 Laissé, avec sa raison

- **Les entrées depuis les états vides et les premiers pas** : chantier B1 (même adresse, `go('exemple')`).
- **Un exemple qui suit les écrans réels quand ils changent** (espace partenaire réduit de B3, « Voir ce que verra… ») :
  l'écran du partenaire de l'exemple est une image fixe, décrite par les données ; à reprendre si B3 change ce que voit
  le partenaire.
- **La date limite** n'est pas affichée : une date fixe deviendrait une échéance passée ; le délai de réponse du calcul
  est compté à 60 jours.
- **`demo_seed.py` n'est pas réécrit** (étude, § 9 : « réécriture de `demo_seed.py` ») : la démo de pitch reste
  identique ; son analyse de Kerhel garde « La bonne stratégie est claire : répondre en GROUPEMENT… » (une injonction,
  étude § 2.10). À décider à part (Eliot), avec le pitch.
