# Réorganisation de l'interface : vague 2b, « prise en main et partenaire »

Contrat de la vague 2b. Étude : « Réorganiser l'interface d'Adjugo : étude définitive », § 6, 7, 9 (vague 2b), 10 et
11. Base : `feat/produit-acheteur-collectivites` = `0afc1ed` (production : vagues 0, 1 et 2a, contrats
`docs/REORGANISATION_V1.md` et `docs/REORGANISATION_V2A.md`). Tête Alembic de départ : `c4montantseul`.

Décisions de la vague (recommandations de l'étude, retenues) : D12 (a) garder le blocage tant que l'adresse email n'est
pas confirmée, et le rendre vivant ; D13 (a) un marché d'exemple entièrement fictif et dit comme tel ; D15 (a) l'espace
du partenaire sans compte réduit à sa part, avec un seul encart « Créer mon compte ». D14 (offres, tarifs) est réservée
à Eliot : aucun contrôle d'offre, aucun prix, aucune carte d'offre ni la vitrine ne changent.

---

## B1. Prise en main

Étude, § 7.1 à 7.4 et 7.7. Base `0afc1ed` ; tête d'arrivée `c5priseenmain` (`c4montantseul` → `c5priseenmain`).
Tests : `tests/test_reorganisation_v2b_prise_en_main.py` (39 tests, sans navigateur ni réseau ; les fonctions de
`app.js` sont exécutées sous Node). Tests existants mis à jour, chacun avec sa raison en commentaire :
`test_reorganisation_v1_contre_relecture` (le jalon « Renseignez le nom et le SIRET… » remplacé par la tâche « Dire ce
que vous faites et où »), `test_demo_lien_prive` (la revérification transmet aussi le détail d'un 401 : 3 appels au
lieu de 2), `test_reorganisation_v1_relecture` (bandeau des cookies et fenêtre du SIRET),
`test_reorganisation_v2a_adresses_etapes` (phrase de l'état vide de « À faire »), `test_reorganisation_v2a_reunion`
(une seule tête, chaîne vérifiée), `test_reorganisation_v1_socle` (repère `ecran-attente`), `test_demo_sans_cout` (les
deux écritures nouvelles). Postgres : `scratchpad/b1/run_b1_pg.py` de la session (§ B1.9).

### B1.1 « Vos premiers pas » sur l'accueil, état gardé sur le serveur

- **Quand** : pendant `PREMIERS_PAS_JOURS` = 30 jours à compter de la création du compte (`users.created_at`, en UTC),
  tant qu'une tâche n'est pas terminée. Tout terminé : le bloc quitte l'accueil. Hors de la période, le serveur ne
  calcule aucune tâche. Jamais pour la démonstration (vitrine en lecture guidée). La date de fin vient du serveur
  (`jusqu_au`) et n'est dite que dans la bulle (« Cette liste reste sur l'accueil jusqu'au 19/11/2026. ») : l'écran
  n'écrit jamais « 30 jours » en dur.
- **Où** : en tête de l'accueil, à la place de l'ancien « Premiers pas sur Adjugo » (3 jalons calculés dans le
  navigateur, masqués par la clé `adjugo_onboarding_done` du navigateur : la liste, `onboarding`, `showOnboarding`,
  `dismissOnboarding` et la clé ont disparu).
- **Repliable**, et l'état est **sur le serveur** (`users.premiers_pas_replie`) : un autre onglet, un autre appareil,
  la page ouverte par le lien de confirmation le retrouvent. Bouton « Replier » / « Déplier » (`aria-expanded`,
  `aria-controls`) ; le compte « N sur M » reste visible replié (décision 8 : jamais un pourcentage).
- **Une bulle (i)**, à côté du titre (§ 7.4) : chaque tâche se coche d'elle-même d'après ce qui a été fait dans Adjugo ;
  comment un marché entre dans Mes marchés (analysé, ou préparé à plusieurs depuis une fin de contrat : ce sont les
  seuls chemins de l'écran) ; la date de fin.
- **Routes** (`app/routers/prise_en_main.py`, règles dans `app/services/prise_en_main.py`) :

| Route | Effet |
|---|---|
| `GET /api/prise-en-main` | `premiers_pas` (`visible`, `replie`, `jusqu_au`, `taches`, `n_terminees`, `n_total`), `suggestion_reseau` (la carte à montrer, ou `null`), `profil_reseau` (`publie` · `en_attente` · `brouillon` · `aucun`) |
| `PUT /api/prise-en-main` | `{replie: bool}` : replier ou déplier ; rend l'état ; 120/heure ; démonstration : 403 |
| `POST /api/prise-en-main/suggestion-reseau/fermer` | la carte « Faites-vous trouver » est fermée (ou suivie) ; 120/heure ; démonstration : 403 |

  Lecture seule pour le reste : seulement des **comptes** des données de l'organisation (`data_owner_id`,
  `member_ids`), jamais un contenu, aucune IA, aucun courriel. Un compte dont l'adresse n'est pas confirmée peut lire
  cet état et replier la liste ou fermer la carte (ses seules préférences d'affichage, sans coût) ; B1 ne lui ouvre
  rien d'autre.
- **Lu** au démarrage (`boot`), en revenant à l'accueil (`go('dashboard')`), après « Ce que je cherche »
  (`saveCriteria`), après la fenêtre du SIRET (`welcomeStart`) et à la confirmation de l'adresse. Une erreur de lecture
  n'affiche rien plutôt qu'un état faux.

### B1.2 La liste d'activation (§ 7.2)

Chaque tâche commence par un verbe, n'a que trois statuts (**Pas commencé · En cours · Terminé**) et se termine selon
une condition **lue dans les données** de l'organisation par le serveur (`taches`), jamais cochée à la main ni devinée.
L'écran (`tachePremiersPas`, fonction pure en tête de `app.js`) ne fait que dire les mots ; une clé que le serveur ne
connaît pas n'est pas affichée.

| Tâche (clé) | Terminée quand | En cours quand | Chemin direct |
|---|---|---|---|
| **Dire ce que vous faites et où** (`dire`) | métier (spécialités ou codes CPV), zone (départements) **et** montant porté seul dits : un montant, **ou « Je ne sais pas » coché** (`criteria_v2.ce_que_je_cherche_dit`) | une ou deux des trois réponses ; la ligne dit ce qui reste (« Reste à dire : votre zone, le montant que vous portez seul (ou « Je ne sais pas ») ») | « Renseigner » → Mon entreprise › Ce que je cherche |
| **Suivre 3 marchés** (`suivre`) | 3 marchés dans Mes marchés (hors corbeille), « 3 sur 3 » | 1 ou 2 | « Trouver des marchés » |
| **Lire le dossier d'un marché** (`lire`) | un marché dont le dossier complet a été lu (`ai_analysis.dce_available`) | un dossier du marché importé (pièce rangée « DCE »), pas encore lu | « Ouvrir le marché » (le plus récent dont le dossier n'est pas lu, jamais une carte « À venir ») ou « Trouver des marchés » |
| **Inviter un partenaire, ou vous faire trouver** (`plusieurs`) | une invitation créée sur un marché (toutes passent par `_create_invite` : partenaire connu, membre du réseau, entreprise du registre), **ou** le profil publié sur le réseau Adjugo | un profil partenaire enregistré pas publié, ou en attente de validation | « Inviter un partenaire » (seulement s'il y a un marché sur lequel inviter) ; « Publier mon profil » ou « Voir ma demande de publication » |
| **Ajouter vos 3 derniers dossiers de présentation** (`dossiers`) | 3 documents « Dossier de présentation » (`knowledge_docs.kind = "memoire"`) dans Mon savoir-faire | 1 ou 2 | « Importer » → Mes documents › Mon savoir-faire |

- **La tâche des dossiers** (« Mes preuves » dans l'étude, « après Réd. V3 ») est affichée parce que sa fonction est en
  ligne : l'import dans Mon savoir-faire (`POST /api/knowledge/upload`, type « Dossier de présentation » par défaut) et
  les fiches qu'Adjugo propose ensuite à partir du document (rédaction, vague 3 : `app/routers/fiches_import.py`), qui
  rejoignent Mes preuves. L'import vit dans Mon savoir-faire : c'est là que mène la tâche.
- **L'étape « Lancez votre première recherche »**, validée seulement après une analyse, **a disparu** (test).
- **Une tâche terminée** n'a plus de bouton ; le titre passe en gris. Pastilles : `neutral` (Pas commencé),
  `a_etudier` (En cours), `go` (Terminé). La ligne d'état dit ce qui est lu, sans plus : « Partenaire invité sur un
  marché. » (une invitation peut être un lien à copier : « envoyée » n'est pas vérifiable), « Profil publié sur le réseau
  Adjugo. », « 1 sur 3 dans Mes marchés. »…
- **375 px** : l'icône et le texte sur la première ligne (le texte passe à la ligne dans sa colonne), le statut puis les
  boutons en dessous, alignés sur le texte ; aucun défilement de côté (vérifié dans le navigateur).
- **Cloisonnement** : un partenaire invité ne compte que ses propres marchés, invitations, dossiers et profil ; la
  réponse ne porte ni le nom ni le marché du chef de file (test
  `test_cloisonnement_rien_du_chef_de_file_dans_les_premiers_pas_du_partenaire`).
- **Chaque tâche revient dans l'état vide de son écran** (§ 7.2, [S12]) : un rappel « Vos premiers pas : [tâche]
  [statut] » (`ppRappel(k)`, `.pp-rappel`), seulement tant que la liste est affichée et que la tâche n'est pas
  terminée. Où : `dire` en tête de Ce que je cherche (avec ce qui reste à dire) ; `suivre` dans Trouver des marchés
  (premier lancement) et dans Mes marchés vide ; `lire` sous « Le dossier complet du marché est indispensable » (étape
  Lire) ; `plusieurs` dans « À plusieurs » de l'accueil, dans « Où je suis partenaire » vide et dans le Réseau Adjugo
  tant que le profil n'est pas publié ; `dossiers` dans Mon savoir-faire vide.

### B1.3 « Je ne sais pas » au montant porté seul (§ 7.1, point 3)

- **Une réponse, distincte d'un champ vide** : `matching_criteria_ext.montant_porte_seul_inconnu` (BOOLEAN, faux par
  défaut). Vide et faux : jamais répondu. Jamais vrai en même temps qu'un montant : `PUT /api/criteria/` avec un
  montant le remet à faux ; avec « Je ne sais pas » (sans montant dans la même requête) il efface le montant ; absent
  de la requête (une page plus ancienne), il est gardé. `GET` le rend toujours en booléen. Mes données (RGPD) l'exporte.
- **N'entre dans aucun calcul**, comme le montant (vague 2a, A3.2) : seul `app/routers/criteria_v2.py` le nomme ; la
  liste d'activation lit seulement qu'une réponse a été donnée (test).
- **Fenêtre du SIRET** : la question « Jusqu'à quel montant répondez-vous seul ? » (facultatif), un montant en € HT ou
  « Je ne sais pas » ; sans réponse, rien n'est enregistré ni déduit (test sous Node : trois cas). La bulle dit « Seul
  le SIRET est demandé » (plus « Un seul champ suffit ») ; le bouton porte `building-2`, plus `sparkles` (réservé à
  l'IA, § 8). Le bandeau des cookies ne passe plus par-dessus : il s'efface tant que la fenêtre est ouverte et revient
  ensuite.
- **Ce que je cherche** : une case « Je ne sais pas » sous le champ ; cochée, elle efface et grise le montant ; la bulle
  dit « Si vous ne savez pas, cochez « Je ne sais pas » ».

### B1.4 Les états vides (§ 7.3)

Chacun dit l'état du système et propose un chemin direct ; **aucun ne promet une fonction qui n'est pas en ligne**.

| Écran | Message | Action |
|---|---|---|
| Accueil › À faire (et la cloche) | « Rien n'attend de réponse de votre part. » (le bloc est toujours là ; jamais « 0 ») | — |
| Accueil › À plusieurs | « Aucun groupement en cours. Pour répondre avec une autre entreprise, ouvrez un marché et invitez-la. » | Voir un exemple ; rappel `plusieurs` |
| Trouver › Publiés, zéro résultat | la carte d'élargissement, inchangée | Élargir… |
| Trouver › À venir | « Contrats de votre zone qui arrivent à échéance. » avant une recherche ; « Aucune échéance proche sur ce périmètre. » après | Modifier ma zone (→ Ce que je cherche) |
| Mes marchés | « Les marchés que vous suivez ou analysez arrivent ici. » | Trouver des marchés · Voir un exemple ; rappel `suivre` |
| Mes marchés › Où je suis partenaire | phrase de la vague 2a (le marché apparaît quand une entreprise vous invite et que vous acceptez depuis votre compte) | Publier mon profil sur le réseau (seulement s'il n'est ni publié ni en attente) ; rappel `plusieurs` |
| Partenaires › Réseau Adjugo, profil non publié | « L'annuaire s'ouvre quand votre profil est publié : c'est la règle pour tous. » ; une demande en attente garde le message du serveur | Compléter mon profil (ou « Voir ma demande de publication ») |
| Mes documents › Mes pièces | « Ajoutez vos attestations avec leur date de fin : Adjugo vous prévient avant qu'elles expirent. » (vague 2a, A3.3 : la saisie de la catégorie et de la date existe) | Ajouter un document |
| Mon savoir-faire | « Vos anciens dossiers servent de source au dossier de présentation. » (au lieu de « Aucun document. Importez les vôtres pour que l'IA rédige… ») | Importer, dans l'état vide lui-même (le même import que la carte du dessus, type choisi au-dessus) ; rappel `dossiers` |

- **« Voir un exemple »** (3 boutons : premiers pas, À plusieurs, Mes marchés) mène au marché d'exemple, `go('exemple')`,
  adresse `/app/exemple` (convention commune des chantiers). Il ne s'affiche **que si cette adresse ouvre vraiment
  l'écran « exemple »** (`exempleEnLigne()` : `etatDeAdresse("/app/exemple").view === "exemple"`) : tant que le
  chantier du marché d'exemple n'est pas réuni, aucun bouton ne mène à un écran absent (test sous Node : faux puis vrai
  quand `ADRESSES.exemple` existe). Sous le bouton des premiers pas : « Entreprises et client fictifs ».
- **« Les projets votés en conseil arriveront ici. »** (phrase de l'étude pour À venir) n'est pas affichée : Veille V1
  n'est pas en ligne (règle du § 7.3, test).
- **« Sur chaque marché, Adjugo indique si vous pouvez répondre seul… »** n'est pas affichée (après Moteur V1 et l'avis
  du conseil, § 7.3).

### B1.5 L'aide en bulles (§ 7.4)

- Les **deux bulles qui manquaient** :
  - « **Où récupérer le dossier du marché** », sur l'avertissement de l'étape Lire : sur la plateforme où le client l'a
    publié, que l'avis donne en général ; ce que contient le dossier complet et ce qu'il apporte. **Le lien de l'avis
    est à côté** (« Ouvrir l'avis du marché », seulement si le marché a une adresse d'avis), jamais dans la bulle
    (aucune action dans une bulle : test sur les bulles des zones touchées).
  - « **Comment Adjugo dit seul ou à plusieurs** », à côté du titre « Répondre à plusieurs ? » : la comparaison du
    dossier à ce que l'entreprise a dit d'elle, sur les six critères du calcul (métier, zone, montant, capacité
    financière, qualifications, délai de réponse : `dce_scoring.py`), puis le même calcul sur les capacités réunies
    des partenaires choisis (`groupement_scoring.py`) ; « Une capacité inconnue ne compte jamais en plus. »
- La troisième, « ce que voit votre partenaire », devient un écran réel (chantier B3, « Voir ce que verra
  [partenaire] ») : rien ici.
- **Compte** (`role="tooltip"` dans `app.html`) : 184 en production, 186 après B1 (+1 premiers pas, +1 « Comment Adjugo
  dit seul ou à plusieurs » ; « Où récupérer… » remplace la bulle existante de l'avertissement). Une seule bulle
  d'explication sur la carte nouvelle (test). Pas de visite guidée.

### B1.6 Confirmation d'email vivante (décision 12 (a)) et carte « Faites-vous trouver »

- **Le blocage est gardé** : écran plein `ecran-confirmation-email` tant que `user.email_verified` est faux (tous modes
  de connexion). Il devient vivant :
  - il **revérifie seul** (`confirmationSuivre`, `confirmationVerifier`) : `GET /api/auth/me` (sans cache, sans la
    barre de progression) toutes les 5 s pendant 2 minutes, toutes les 15 s jusqu'à 15 minutes, puis chaque minute
    (`delaiReverification`) ; **seulement quand l'onglet est visible** (onglet caché : plus aucune minuterie) ; **tout
    de suite quand on revient sur l'onglet** (`visibilitychange`, `focus` ; les deux ensemble ne font qu'un appel :
    2 s d'écart minimum) ; le compte à rebours repart à chaque retour. Une minuterie au plus à la fois.
  - dès que le serveur dit « confirmée » (lien cliqué ici, sur le téléphone ou dans un autre onglet), l'écran s'ouvre
    (« Adresse email confirmée »), les premiers pas sont relus, la fenêtre du SIRET suit. La revérification s'arrête
    (observateur `user.email_verified`), et à la déconnexion. 401 : la session perdue est traitée comme ailleurs.
  - « J'ai cliqué sur le lien » : une vérification tout de suite ; pas encore confirmée : « Pas encore confirmée :
    cliquez sur le lien du courriel, puis revenez ici. »
  - **les réponses s'affichent dans l'écran** (`confirmation.message`, `role="status"`) : le message habituel, en bas
    de page (z-index 200), passait SOUS cet écran plein (300) ; la réponse de « Renvoyer l'email de vérification »
    (envoyé, déjà confirmée, trop d'envois) était donc invisible depuis l'inscription (vu dans le navigateur, corrigé :
    `confirmationRenvoyer`). « Adresse email confirmée » reste un message habituel : l'écran plein a disparu.
  - **il dit la suite** : « Une fois confirmé, vous entrez votre SIRET et vous voyez les marchés de votre zone. »,
    seulement quand l'entreprise n'a pas encore de SIRET (compte neuf) ; et « Dès que vous cliquez sur le lien, ici ou
    sur votre téléphone, cette page s'ouvre d'elle-même. » (`role="status"`). Fenêtre accessible (`role="dialog"`,
    `aria-modal`, titre et description liés).
- **Le courriel de confirmation dit la même phrase** (`APRES_CONFIRMATION`, `app/routers/auth.py` ; texte et HTML :
  `verify_email_html(link, name, suite)`), **seulement quand elle est vraie** : l'entreprise de l'organisation n'a pas
  encore de SIRET (`_suite_apres_confirmation`). Un collègue d'une entreprise déjà renseignée ou un renvoi après le
  SIRET ne la reçoivent pas. Sans `suite`, le courriel HTML est identique à celui d'avant.
- **Le serveur refuse toujours ce qu'il refusait** : aucun refus ajouté ni retiré. Le commentaire d'`auth.py`
  (inscription) qui décrivait ce blocage est corrigé et dit ce qui est vrai dans le code : sans adresse confirmée,
  refus de toute analyse d'un marché (`consume_analysis`, 403), des rédactions de l'atelier, de l'entretien et des
  fiches de Mon savoir-faire (403 `email_non_confirme`, `adresse_a_confirmer`), de l'invitation d'un membre du réseau,
  de la demande de publication du profil, de l'accord sur une convention, de l'acceptation d'un lien nominatif (403) ;
  aucun courriel au nom d'Adjugo vers un tiers (le lien d'invitation reste à copier) ; ce qui ne lit **pas** l'adresse
  (appels qui passent seulement par `exiger_ia` : questions sur un marché déjà analysé, estimation du prix, veille),
  borné par le garde-fou de l'essai. Chaque refus cité est vérifié dans le code par un test.
- **La carte « Faites-vous trouver pour des groupements »** (suggestion d'interface, jamais un courriel) est **gardée
  sur le serveur** (`users.suggestion_reseau` : `""` jamais proposée, `"a_montrer"`, `"fermee"`) : proposée après
  l'inscription (mot de passe et Google) et après l'acceptation d'une invitation (`proposer_suggestion_reseau`, si
  l'organisation n'a pas de profil publié ni en attente) ; elle s'affiche aussi dans l'onglet ouvert par le lien de
  confirmation et sur un autre appareil (`GET /api/prise-en-main`) ; « Fermer » ou la suivre la ferme sur le serveur
  (`_rnSuggestFermer`) ; un profil publié depuis l'éteint ; une nouvelle proposition la remontre, comme avant.

### B1.7 Au rechargement d'une adresse, aucun écran avant qu'elle soit résolue

- **Le défaut** (signalé en production, reproduit avec le code `0afc1ed` dans un navigateur réel, § B1.9) : au
  rechargement de `/app/marches/1`, l'accueil s'affichait environ une seconde (le temps des chargements de `boot`), puis
  la page du marché.
- **Maintenant** : `view` est vide au départ et `ecranPret` faux ; la zone de contenu est cachée (`v-show`) et une
  attente s'affiche à sa place (`ecran-attente`, `role="status"`, « Chargement de l'écran » pour le lecteur d'écran).
  `ecranPret` passe à vrai quand `boot` a ouvert l'écran de l'adresse ; pour un marché qui n'est pas encore dans la
  liste, à la réponse de `GET /api/projects/{id}` (marché ouvert, ou Mes marchés avec « Ce marché n'est plus
  accessible »). `boot` attend ses chargements avec `Promise.allSettled` : un chargement en échec n'empêche plus
  d'ouvrir l'écran. La fenêtre du SIRET attend aussi `ecranPret` (plus d'éclair de la fenêtre avant la fiche de
  l'entreprise).
- `/api/auth/me` en échec au démarrage (hors 401, déjà traité) : l'attente cesse et la zone reste vide, plutôt qu'un
  accueil qui dirait « rien n'attend de réponse » sans l'avoir lu.
- **Avant le montage de Vue**, le gabarit brut de `app.html` (tous les écrans à la fois, avec leurs `{{ … }}`) était
  rendu le temps de charger `app.js` (vu dans le navigateur : son texte était affiché, l'accueil brut en tête). La
  feuille de style, chargée dans `<head>`, le cache désormais : `#app:not([data-v-app]) { display:none; }` (Vue pose
  `data-v-app` sur `#app` au montage ; vérifié dans `vue-3.5.38.prod.js`). Seule `app.html` a un `#app`.
- Adresses et retour arrière de la vague 2a inchangés (test sous Node : rien d'affiché pendant l'appel, le marché à la
  réponse, Mes marchés au refus). Repère ajouté : `ecran-attente` (`ZONES` du socle, `vague2b_b1`).

### B1.8 Migration `c5priseenmain` (après `c4montantseul`)

- Ajoute, **chacune seulement si elle manque** (idempotente) : `users.premiers_pas_replie` (BOOLEAN, défaut faux),
  `users.suggestion_reseau` (VARCHAR(12), défaut `''`), `matching_criteria_ext.montant_porte_seul_inconnu` (BOOLEAN,
  défaut faux). NULL permis et valeur par défaut posée par la base : exactement ce que pose la réconciliation
  `b7d9e1f3a2c4` (`sync_models`) sur une base neuve à partir du modèle ; une base de production migrée et une base
  neuve ont le même schéma (vérifié sur Postgres). Le code lit NULL comme la valeur par défaut.
- Lignes existantes : rien de replié, aucune carte proposée, aucun « Je ne sais pas » inventé.
- **Déploiement sans casse** : le code de production précédent ne déclare pas ces colonnes ; ses écritures les omettent
  et la base pose la valeur par défaut, ses lectures les ignorent (vérifié sur Postgres : inscription, critères).
- **Retour arrière réel** : les trois colonnes sont retirées (l'état replié, la carte et les « Je ne sais pas » sont
  perdus, rien d'autre).
- Une seule tête : `c5priseenmain` (le test de la réunion de la vague 2a ne fige plus la tête, il vérifie la chaîne).

### B1.9 Vérifications

- **Suite complète SQLite** (TZ=UTC) : **2 244 réussis sur 2 244** (2 205 en production + les 39 du chantier) ;
  `tests/test_demo_*.py` et
  `tests/test_demo_sans_cout.py` verts (les deux écritures nouvelles y sont déclarées sans coût : aucune IA, aucun
  courriel, aucun fichier, refusées à la démonstration dans la route).
- `scripts/sri_update.py --check`, `node --check` sur tous les fichiers JS servis, `scripts/i18n_ajouter.py --check`
  (636 → 689 clés, néerlandais et espagnol ; « marché » = aanbesteding / licitación, « à plusieurs » = samen /
  agrupación, comme en vague 1) ; gabarit de l'application compilé par le Vue du dépôt (tests existants).
- **Postgres 16.2** depuis l'état exact de la production (`0afc1ed` extrait par `git archive`, tête `c4montantseul`,
  données créées par ce code : comptes confirmé et non confirmé, critères avec montant, 3 marchés, une invitation, un
  dossier rangé, un marché lu, un compte de 40 jours) : `scratchpad/b1/run_b1_pg.py`. Migration, valeurs par défaut,
  données inchangées, schéma égal à celui d'une base neuve ; premiers pas lus dans ces données, replié gardé, « Je ne
  sais pas », carte gardée et fermée, analyse toujours refusée sans adresse confirmée ; code de production relancé sur
  la base migrée (lecture, écriture, inscription) ; retour arrière réel, remontée, rejeu forcé : **29 contrôles sur
  29**. 15 fichiers de tests communs (authentification, isolement, réseau, Mon entreprise, adresses, réunion, garde-fou
  de l'essai, données, démonstration, RGPD) : code de production et code nouveau, chacun 393 réussis, 11 échecs et
  9 erreurs, **les mêmes** (`test_secu_rgpd.py`, son `PRAGMA` propre à SQLite, et 5 de `test_secu2_donnees.py`, déjà
  en échec avec la production) ; le fichier du chantier sur une base à part : 39 sur 39.
- **Navigateur réel** (serveurs locaux du worktree et du code de production `0afc1ed`, bases à part, IA, courriels et
  réseau sortant coupés ; scripts `scratchpad/b1/srv/` de la session) :
  - **rechargement de `/app/marches/8`**, chaque état du DOM noté par un observateur de mutations dans un iframe du même
    domaine (le panneau du navigateur étant caché, les images y sont ralenties) — production : page brute, puis
    **l'accueil (`vue-dashboard`) affiché 1,1 s**, puis le marché ; code nouveau : page brute cachée, attente, puis le
    marché, **jamais l'accueil** ; `/app/marches/99999` : attente, puis Mes marchés avec « Ce marché n'est plus
    accessible » ; même résultat dans la démonstration (`/app/marches/15`). Avec `app.js` retardé de 4 s (serveur
    statique lent), avant le montage : `#app` caché, aucun texte affiché ;
  - **confirmation vivante** (compte de test créé par le formulaire d'inscription) : `GET /api/auth/me` toutes les 5 s ;
    onglet caché 12 s : aucun appel ; retour sur l'onglet (visibilité et focus ensemble) : un seul appel, tout de suite ;
    lien de confirmation ouvert dans un autre onglet : l'écran s'ouvre seul à l'appel suivant, puis plus aucun appel ;
    adresse confirmée en base pendant que l'écran est ouvert : ouvert en 1 s ; « J'ai cliqué sur le lien » et
    « Renvoyer » répondent dans l'écran ;
  - **premiers pas** : bulle, compte « 0 sur 5 », replié gardé après rechargement (serveur), carte « Faites-vous
    trouver » fermée par « Plus tard » et absente après rechargement ; « Je ne sais pas » coché dans Ce que je cherche
    puis enregistré : la tâche « Dire » passe à Terminé et son rappel disparaît ; fenêtre du SIRET avec la question,
    bandeau des cookies effacé tant qu'elle est ouverte, revenu après ;
  - thème sombre : accueil, écran de confirmation et fenêtre du SIRET à **1 280 et 375 px** ; À plusieurs et Ce que je
    cherche à 375 px ; aucun défilement de côté (largeur du document = 375) ;
  - **démonstration par lien privé** (clé jetable écrite dans un fichier, jamais affichée ; page d'ouverture servie en
    local) : ni premiers pas ni carte « Faites-vous trouver », « À faire » (2 pièces à renouveler) et « À plusieurs »
    affichés, aucune erreur de script, marché de la vitrine rechargé sans l'accueil, 1 280 et 375 px ; aucun courriel
    tenté (journal du serveur).

### B1.10 Pour la réunion des chantiers

- **Marché d'exemple (B2)** : il suffit que `ADRESSES.exemple = "exemple"` et la vue « exemple » existent pour que les
  3 boutons « Voir un exemple » apparaissent (`exempleEnLigne`) ; le test
  `test_aucune_promesse_d_une_fonction_qui_n_est_pas_en_ligne` en compte 3, tous gardés et menant à `go('exemple')`.
- **Courriel d'invitation (B4)** : `app/services/email_templates.py` — B1 ajoute le paramètre `suite` à
  `verify_email_html` ; B4 ajoute `pied` à `_shell`. Les deux se cumulent. `app/routers/invites.py` : B1 ne touche que
  `claim_invite` (la suggestion passe par `proposer_suggestion_reseau`).
- **Espace partenaire (B3)** : l'acceptation d'une invitation (`claim_invite`) propose la carte comme avant ; rien
  d'autre en commun.
- **Alembic** : une autre migration de la vague se place après `c5priseenmain`.
- **Traductions** : 53 clés ajoutées par B1 ; `--check` après la fusion de `i18n.js`.

### B1.11 Laissé, avec sa raison

- **« Je remplirai plus tard »** (fenêtre du SIRET) reste gardé dans le navigateur (`adjugo_welcome_done`) : la
  fenêtre revient sur un autre appareil tant que le SIRET manque. Le chantier ne demandait que la carte « Faites-vous
  trouver » côté serveur ; la fenêtre, elle, se ferme définitivement avec le SIRET (donnée du serveur).
- **Note « Ce qui a changé »** (vague 1, § 7.7) : inchangée, gardée dans le navigateur. Pour les 7 PME : un compte
  créé il y a plus de 30 jours ne voit pas « Vos premiers pas » ; l'ancienne liste « Premiers pas sur Adjugo »
  disparaît pour tous. Aucun écran n'est renommé par B1 (pas d'ancien nom en bulle).
- **Pas de poussée du serveur** pour la confirmation (ni WebSocket ni SSE : un seul serveur, sans file) : une
  revérification espacée, seulement onglet visible, suffit.
- **Trouver › À venir** : la seconde phrase de l'étude attend Veille V1 (§ B1.4).
