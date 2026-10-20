# Réorganisation de l'interface : vague 2a « un marché, une page, une adresse »

Contrat de la vague 2a. Étude : « Réorganiser l'interface d'Adjugo : étude définitive » (12/10/2026), § 5.3, 7, 8, 9
(vague 2a et « Ensuite »), 10 et 11. Base : `feat/produit-acheteur-collectivites` = `fab9d9a` (production du
20/10/2026, tête Alembic `b3mesureecrans`). Contrat de la vague 1 : `docs/REORGANISATION_V1.md`.

Décisions appliquées (recommandations de l'étude, validées par Eliot) : D7 (un seul axe d'étapes), D10 (« partie
(lot n) » partout, tests compris), D11 (une carte de Mes marchés peut exister avant la publication), D18 (barre basse
de 5 sur téléphone) ; D8 et D9 comme en vague 1. La vague 2b (prise en main, marché d'exemple, espace partenaire
réduit) vient après.

La vague est menée en chantiers parallèles, une section chacun.

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
  `down_revision` de la seconde) pour garder une seule tête.
- **Zones de fichier touchées** : `RUBRIQUES` (rubrique « Mon entreprise » seulement), vues `company`, `criteria`,
  `tarifs`, `documents`, la fenêtre `fenetre-confirmation`, les textes « lot » un peu partout (page du marché,
  atelier, espace partenaire) ; `go()` n'est pas modifiée.
