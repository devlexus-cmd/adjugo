# Rédaction, vague 6 — « Apprendre de ses résultats » : contrat

Étude « rédaction » (`etudes/redaction.md`) § 8 (V6) : le carnet de notes (F, § 6.11), la page « Comment ce dossier
a été préparé » (H, § 6.12) et « Plusieurs lots, un seul effort » (J, § 6.10) ; doctrine § 7 ; décision 9 (§ 10).

Base de production : `a29173a` (branche `feat/produit-acheteur-collectivites`, tête Alembic `z1entretienchantier`).

La doctrine (§ 7) vaut pour tous les chantiers : un fait ne vient jamais de l'IA ; on ne dit jamais « vérifié » ;
toute phrase du dossier affichée est retrouvée mot pour mot ; le cadre de l'acheteur commande ; la matière reste
chez son propriétaire (cloisonnement de la vague 4 intact) ; `tenant_scope` et `pii_scope` sur chaque appel d'IA,
remboursement si l'IA tombe ; un seul process ; tout ce qui peut se faire sans IA se fait sans IA.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« lot », « commune » ; « valider », jamais « signer » ; jamais « vérifié ». Zéro émoji, explications dans une bulle
(i), compact, rien collé aux bords, lisible à 375 px. Le menu n'est pas réorganisé (une réorganisation suit).

Ce contrat est écrit par chantier : chaque chantier a sa section (F, H, J), les sections ne se recouvrent pas.

---

## J — Plusieurs lots, un seul effort

En BTP, on répond souvent à deux ou trois lots d'un même marché, avec un mémoire par lot. Pour un marché alloti
auquel l'entreprise répond sur **deux lots ou plus**, l'atelier distingue :

- des **parties communes** (présentation, qualité, sécurité, environnement…), rédigées une fois : UNE partie, un
  seul texte, une seule chaîne de versions, reprise telle quelle dans le dossier de chaque lot. Une modification
  se répercute donc dans tous les lots par construction (même texte, même version) ;
- des **parties propres à chaque lot** (méthodologie, moyens, planning…), une par lot ;

et l'export produit **un fichier par lot** (Word, PDF) : les parties communes et celles du lot, numérotées pour lui,
ses limites de pages contrôlées pour lui seul, nommé comme le règlement l'exige s'il le dit, sinon avec le numéro
et l'intitulé du lot.

**Marché à un seul lot, ou réponse à un seul lot : RIEN ne change** (aucune donnée nouvelle, mêmes écrans, même
export, même empreinte d'état, voir J.13).

### J.0 Source de vérité du code

- règles (repérage, grille par lot, commune ou propre, fusion des plans, nommage, groupement) :
  `app/services/atelier_lots.py` (nouveau ; fonctions pures, ni IA ni réseau ni base, sauf la lecture de
  `plan_meta`) ;
- atelier : `app/services/atelier.py` (`_plan`, `pieces_du_marche`, `texte_pour_lots`, `lots_reperes`,
  `lots_demandes`, `proposition`, `_plan_meta`, `creer_dossier`, `reconstruire_plan`, `changer_lots`,
  `changer_portee`, `ajouter_section`, `remettre_section`, `modifier_section`, `_groupe_sous_critere`, `_rangs`,
  `contexte_rendu`, `_limites_doc`, `compteur`, `evaluer_limites`, `etat_hash`, `blocage`, `derogation_du_lot`,
  `enregistrer_derogation`, `nom_fichier`, `apercu_export`, `lot_a_exporter`, `exporter`, `_archiver`,
  `dossier_commun` / `_dossier_commun_lots`, `section_out`, `_etat_des_lots`, `_blocage_ensemble`, `etat` /
  `_lots_out`, `exigences_out`, `changements_grille` / `_changements_grille_lots`, `appliquer_grille` /
  `_appliquer_grille_lots`, `_executer`) ;
- page de garde : `app/services/atelier_export.py` (`_lignes_garde`) ;
- consigne de rédaction : `app/services/agents/memoire.py` (`_consigne_partie`) ;
- contrôle des faits : `app/services/faits_a_relire.py` (`_LOT_REF`) ;
- groupement : `app/services/atelier_groupement.py` (`proposition`, `_lots_du_dossier`, `_section_base_out`,
  `note_acheteur`) ; entretien chantier : `app/services/entretien_chantier.py` (`pour_parties`) ;
- routes : `app/routers/atelier.py` ; archivage du dossier commun : `app/routers/sourcing.py`
  (`_archive_memoire`) ; garde de la démo : `app/core/demo_guard.py` ;
- écrans : `app/static/app.js` (`atlLots*`, `atlLot*`, `atlPortee`, `atlExport(fmt, lot)`, `atlSectionsVues`,
  `atlNumPart`), `app/static/app.html` (atelier, carte du marché, fenêtre « Lots auxquels vous répondez »),
  `app/static/styles.css` (`.atl-lots*`, `.atl-lot-*`), `app/static/redaction-partenaire.js` (le lot d'une partie) ;
- démo : `app/services/demo_lots.py` (nouveau), appelé par `demo_seed.ensure_demo` dans SA transaction ;
- tests : `tests/test_redaction_v6_lots.py`, `tests/test_demo_plusieurs_lots.py`.

### J.1 Ce que voit l'utilisateur

**Avant de créer le dossier** (plan proposé, rien n'est enregistré), si le règlement répartit le marché en deux lots
ou plus : un encadré « Ce marché est réparti en 3 lots », la question « À quels lots répondez-vous ? », une case par
lot repéré (« Lot 2 — Couverture et zinguerie », bulle (i) « Le règlement dit : « … » (source) »), un champ « Un lot
absent de la liste : son intitulé » (numéro + intitulé, « indiqué par vous »). Deux lots cochés ou plus : le plan
proposé est recalculé aussitôt (aucune IA) — chaque partie porte l'étiquette « Commune » ou « Lot 2 » — et le message
du plan le dit (« Vous répondez à 2 lots : 1 partie commune, rédigée une fois pour tous vos lots, et 4 parties
propres à un lot ; un fichier par lot à l'export »). Un seul lot coché, ou aucun : un seul dossier, comme avant.

**Dans l'atelier** (dossier à plusieurs lots) :
- en-tête : « Vous répondez à 2 lots : Lot 2 — … · Lot 3 — … » (bulle (i) : ce qu'est une partie commune, la
  règle), lien « Changer les lots » (ordinateur) ; les boutons d'export généraux sont remplacés par l'export lot par
  lot ;
- « Un fichier par lot » : pour chaque lot, son état (« Prêt à exporter », « Export avec dérogation », « N parties à
  valider », « Bloqué »), ses parties (« 3 parties, dont 1 commune »), son compteur (« Environ 3 pages · 217 mots »),
  ses limites (« Environ 3 pages pour 6 pages au plus », phrase du règlement en bulle), le nom de son fichier (bulle :
  « Nommé comme le règlement l'exige : « … » » et sa phrase), « Voir pourquoi » (ce qui bloque ce lot, liens vers
  les parties), « Exporter malgré tout… » (dérogation de CE lot), Word et PDF, « Comment vous serez noté pour ce
  lot » (repliable : critères, poids pour ce lot, phrase, contrôle du total), dernier export ;
- plan : filtre « Toutes · Communes · Lot 2 · Lot 3 » (le filtre d'un lot montre son dossier : parties communes et
  les siennes, avec SES numéros), étiquette « Commune » / « Lot 2 » sur chaque partie ; « Nouvelle partie » demande
  « Commune à tous les lots » ou un lot ;
- partie : étiquette « Partie commune à vos lots » ou « Lot 2 — … », bulle (i), lien « La rédiger pour chaque lot » /
  « La rendre commune à tous les lots » (fenêtre de confirmation de l'application) ;
- parties retirées : leur lot.

**Dossier à un seul lot d'un marché alloti** : une ligne discrète « Ce marché est réparti en 3 lots : ce dossier en
prépare un seul. » et le lien « Répondre à plusieurs lots » (ordinateur).

**Carte du marché** : « Un fichier par lot : Lot 2 Prêt à exporter · Lot 3 Bloqué » ; avant la création, « Ce marché
est réparti en 3 lots : dans l'atelier, choisissez ceux auxquels vous répondez (un fichier par lot). »

**Sur téléphone** (375 px) : tout se lit, rien ne déborde ; on valide ; on n'écrit pas et on n'exporte pas (comme
avant). Les cases des lots, le filtre et les étiquettes passent à la ligne.

### J.2 Données : aucune migration

Le modèle de l'atelier prévoit les lots depuis la vague 2 (`dossier_sections.lot`, `String(120)`, « vague 6 (plusieurs
lots), vide aujourd'hui ») ; il suffit :
- `dossier_sections.lot` : `""` = partie commune, sinon le numéro du lot (« 2 ») ;
- `dossiers_presentation.plan_meta["lots"]` (posé à la construction du plan, repris par `appliquer_grille`) :
  `{actif: true, liste: [{numero, intitule, phrase, source, origine}], grilles: {n: grille du lot (J.4)},
  limites: {n: limites du dossier du lot}, sources: {n: cadre|grille|libre}, criteres_hors_dossier: {n: [...]},
  nommage: {modele, phrase, source} | null, regle_commune}` ; absent pour un dossier à un seul lot ;
- par lot, sous la clé `lots` des colonnes JSON existantes : `derogation["lots"][n]` (même forme que la dérogation
  d'un dossier à un seul lot), `dernier_export["lots"][n]` (et le dernier export tous lots confondus à la racine,
  avec `lot`), `compteur["lots"][n]` (cache du compteur du dossier de ce lot).

Rien n'est ajouté au schéma ; le code de production lit sans erreur un dossier écrit par ce code (les clés
inconnues sont ignorées) — vérifié sur Postgres (J.15).

### J.3 Les lots du marché, repérés sans IA (`atelier_lots.reperer`)

Dans les pièces lues du dossier (lecture intégrale rangée, sinon le texte de l'ancienne lecture, sinon l'extrait de
l'analyse — jamais une relecture du fichier) :
1. lignes « Lot n° 2 : Couverture », « LOT 02 – GROS ŒUVRE », « - Lot 3. Étanchéité » (en tête de ligne), dans le
   règlement d'abord, puis l'acte d'engagement, les pièces au nom inconnu, le CCAP, le cadre de réponse — jamais le
   bordereau (« Lot 1 — Installation du chantier » y est un poste de prix) ni le CCTP (ses articles par lot décrivent
   des travaux) ;
2. sinon, énumération dans une phrase qui parle des lots (« … répartis en trois lots : lot 1, désamiantage et retrait
   d'amiante ; lot 2, isolation thermique… ») ;
3. un lot proposé par l'analyse (`details.allotissement`) n'est gardé que si son intitulé est retrouvé mot pour mot
   dans le dossier, dans les 60 caractères qui suivent son numéro (`origine: "analyse"`) ;
4. refusés : une phrase (« Lot 1 : sera attribué… », verbe), un poids ou un montant (« Lot 2 : 40 % »), un intitulé
   qui commence par une conjonction ou un chiffre.

Chaque lot a SA phrase (retrouvée mot pour mot) et sa source (« Règlement de la consultation (RC.pdf) »). `alloti` :
au moins deux lots. `annonce` : le nombre écrit (« en 3 lots ») ; s'il diffère, le message le dit (« Le règlement
annonce 3 lots et Adjugo en a repéré 2 : vérifiez… vous pouvez ajouter un lot »). « Lot unique » (« le marché est
passé en lot unique ») : `unique` = sa phrase, pas d'encadré. Le résultat est gardé en mémoire du process pour un
même dossier lu et une même analyse.

**Lots choisis** (`atelier_lots.choisir`) : les numéros cochés doivent avoir été repérés ; un lot indiqué par
l'utilisateur a un numéro (1 à 99) et un intitulé (2 caractères au moins), `origine: "utilisateur"` (« indiqué par
vous », aucune phrase) ; pas de doublon ; 8 lots au plus par dossier. Erreur : 422 `lots_invalides` (message
affichable). Moins de deux lots : un seul dossier.

### J.4 La grille de chaque lot, depuis SA phrase (`atelier_lots.grilles_par_lot`)

Les critères sont ceux de « Comment vous serez noté » (proposés par l'analyse, contrôlés sans IA) ; pour chaque lot,
on lit dans la zone des critères du règlement (du titre « critères de jugement / jugement des offres… » à l'article
suivant, 6 000 caractères au plus) les mentions de lots (« Pour le lot 2 : … », « Lot 3 – … », « lots 1 et 2 »,
« lots 1 à 3 ») ; un règlement propre à un lot (pièce nommée ou titrée « lot 3 ») est en entier la zone de ce lot.
Quatre cas, dits à l'écran (`grille.mode`, `grille.message`) :

| mode | quand | ce que porte chaque critère |
|---|---|---|
| `commune` | aucune mention de lot dans la zone des critères | la grille du règlement, telle quelle ; la phrase « Pour chacun des lots… » si elle existe |
| `propre` | des critères écrits pour CE lot | le poids rattaché au critère dans la partie du lot (même règle de rattachement que la grille : `_attribute`), sa phrase mot pour mot depuis la mention du lot (« Pour le lot 3 : valeur technique 40 % ; prix 60 %. ») ; un critère absent de la partie du lot : « à vérifier », hors du plan de ce lot, avec la raison ; un sous-critère n'est repris que s'il figure aussi dans la partie du lot |
| `generale` | d'autres lots ont leurs critères, pas celui-ci | la grille générale, et « vérifiez dans le règlement » |
| `illisible` | deux lots cités sur la même ligne sans poids entre eux (tableau « Critère \| Lot 1 \| Lot 2 ») | les critères SANS poids (jamais un poids deviné), « vérifiez le poids de chaque critère pour ce lot » |

Le contrôle du total (« Les poids retrouvés font bien 100 % au total ») est refait pour chaque lot. Un choix de
l'utilisateur dans « Comment vous serez noté » vaut pour les lots : un critère écarté l'est partout ; un critère
confirmé entre dans le plan de chaque lot, sans reprendre un poids lu ailleurs.

**Limites par lot** (`limites_du_lot`) : une limite dont la phrase cite un lot (« Pour le lot 3, le mémoire compte 5
pages au maximum ») ne vaut que pour lui et remplace la limite générale du même type ; une limite qui ne cite aucun
lot (« 6 pages au maximum par lot ») vaut pour chacun. La police vaut pour tous.

### J.5 Le plan : parties communes et parties propres à chaque lot

Pour chaque lot, le plan d'un seul dossier est construit comme avant (`atelier_plan.build_plan`) avec SA grille et
SON cadre de réponse (pièce de cadre propre au lot, sinon le cadre commun) ; puis `atelier_lots.fusionner` :
- **commune** : la règle `est_commune` le dit (intitulé : présentation, qualité, sécurité, santé, hygiène,
  environnement, développement durable, RSE, social, insertion, déchets, carbone, groupement — et AUCUN mot de partie
  propre : méthodologie, moyens, humain, matériel, organisation du chantier, planning, délai, phasage, mode
  opératoire, compréhension, exécution, technique, équipe, encadrement, intervention, prestations, ouvrages,
  références…) ET la même partie (même source, même critère, même intitulé, mêmes titres au-dessus ; même numéro pour
  une question du cadre) figure dans le plan de CHAQUE lot ; elle porte le poids de son critère s'il est le même pour
  tous les lots, sinon aucun (chaque lot le dit dans sa grille) ;
- sinon **propre à chaque lot** : une partie par lot qui la note.

Ordre : chaque partie commune une fois, là où elle tombe dans le plan du premier lot ; entre deux parties communes,
les parties propres de chaque lot, lot par lot. Le dossier d'un lot (parties communes + les siennes) suit donc
l'ordre de SON plan. Numérotation : celle du dossier du lot (les sous-critères d'un critère, communs ou propres, sous
le même titre : « 1.1 Méthodologie », « 1.2 Moyens », « 1.3 Gestion environnementale ») ; dans la liste de l'atelier,
chaque partie porte le numéro de son lot (une partie commune : celui du premier lot), et le titre d'une partie
propre dit son lot (« 1.1 Méthodologie d'exécution (lot 3) »). Les sous-critères d'un critère restent ensemble dans
le dossier de chaque lot (un déplacement qui les séparerait est refusé : 409 `groupe_sous_criteres`).

Un dossier à plusieurs lots n'est jamais tronqué en silence : plus de 60 parties → 422 `trop_de_parties` avec la
raison. Les parties tirées du groupement (vague 4) sont communes à tous les lots.

**Portée d'une partie** (`changer_portee`, `PUT …/sections/{sid}/portee`) :
- commune → propre : la partie garde son texte et ses versions pour le premier lot ; une partie vide « à écrire » est
  ajoutée pour chacun des autres (même intitulé, critère, poids de chaque lot, limite) ;
- propre → commune : la partie choisie garde son texte et devient commune ; la même partie des autres lots est
  RETIRÉE (jamais supprimée, remettable) — 409 `portee_a_confirmer` si l'une a du texte, puis `remplacer: true` ;
- refus : dossier à un seul lot (409 `un_seul_lot`), partie tirée du groupement (409 `partie_du_groupement`), partie
  d'un partenaire, ou dont une sœur est d'un partenaire (403 `partie_d_un_partenaire`), rédaction en cours (409).

**Changer les lots** (`changer_lots`, `PUT …/lots`) : le plan est reconstruit pour les nouveaux lots (ou pour un seul
dossier) ; mêmes règles que « Reconstruire le plan » (parties retirées, jamais supprimées, 409
`plan_remplacement_a_confirmer` si l'une a du texte ; la partie d'un partenaire reste, commune si son lot n'est plus
dans le dossier) ; 409 `rien_a_changer` si les lots sont les mêmes. **Remettre** une partie dont le lot n'est plus
dans le dossier : elle revient commune.

### J.6 Routes (`app/routers/atelier.py`)

| Route | Corps / paramètres | Réponse |
|---|---|---|
| `GET /api/atelier/{pid}` (sans dossier) | `?lots=2,3` (numéros repérés), `?ajoutes=[{"numero","intitule"}]` (JSON) : prévisualisation | `proposition` avec `lots_du_marche` (J.7) et, pour deux lots ou plus, `lots` et une étiquette `lot` sur chaque partie ; 422 `lots_invalides` |
| `POST /api/atelier/{pid}` | `{base, sans_ia, lots: ["2","3"], lots_ajoutes: [{numero, intitule}]}` | 201 + état ; 422 `lots_invalides`, `trop_de_parties` |
| `GET /api/atelier/{pid}/lots` | — | `{du_marche: lots repérés (J.7), dossier: [{numero, libelle}]}` (lecture seule) |
| `PUT /api/atelier/{pid}/lots` | `{lots, lots_ajoutes, remplacer}` | état ; 409 `plan_remplacement_a_confirmer`, `rien_a_changer`, `redaction_en_cours` ; 422 `lots_invalides`, `trop_de_parties` |
| `PUT /api/atelier/{pid}/sections/{sid}/portee` | `{commune: bool, remplacer: bool}` | état ; voir J.5 |
| `POST /api/atelier/{pid}/sections` | `{intitule, apres_section_id, lot}` : `""` commune, sinon un lot du dossier (défaut : le lot de la partie après laquelle on ajoute) | partie ; 422 `lot_inconnu` |
| `POST /api/atelier/{pid}/export` | `{format, etat_hash, lot}` | fichier du lot ; 422 `lot_requis` (avec `lots: [{numero, libelle}]`), `lot_inconnu` (lot hors du dossier, ou lot donné pour un dossier à un seul lot) ; 409 `export_bloque` (raisons du lot), `etat_modifie` |
| `POST /api/atelier/{pid}/derogation` | `{raison, texte, etat_hash, lot}` | `{derogation, blocage (du lot), lot}` ; 422 `lot_requis`, `lot_inconnu` ; erreurs d'avant |

`GET …/compteur` rend l'ensemble (J.7). Toutes les autres routes sont inchangées. Les écritures nouvelles (`PUT
…/lots`, `PUT …/portee`) sont refusées au compte de démonstration par le garde central (403 « La démo est en lecture
guidée… ») et classées dans `tests/test_demo_sans_cout.py` (aucune IA, aucun email, aucun fichier, aucun réseau).

### J.7 L'état (`GET /api/atelier/{pid}`)

Nouveau bloc `lots` :
```json
{"actif": true,
 "liste": [{"numero": "2", "intitule": "Couverture et zinguerie", "libelle": "Lot 2 — Couverture et zinguerie",
            "phrase": "Lot 2 : Couverture et zinguerie", "source": "Règlement de la consultation (RC.pdf)",
            "origine": "reglement", "origine_libelle": "repéré dans le règlement",
            "parties": [41, 42, 45], "parties_propres": 2, "parties_communes": 1, "numeros": {"41": "1.1", "45": "1.3"},
            "compteur": {"total": {"pages": 3, "mots": 217, "...": "..."}, "police": {}, "environ": true, "message": "..."},
            "limites": [Limite (+ "lot")], "blocage": Blocage du lot (+ "lot"), "derogations_possibles": [...],
            "export": Apercu (+ "lot", "nommage": {"selon_reglement", "message", "phrase", "source"}),
            "dernier_export": {"le", "par", "format", "nom", "empreinte", "ia", "derogation", "etat_hash"} | null,
            "grille": {"mode", "message", "phrase", "source", "lignes": [{"id", "critere", "poids", "poids_source",
                       "phrase", "source", "statut", "dans_le_plan", "prix", "message", "sous_criteres"}],
                       "controle_total": {"statut", "message"}},
            "source_plan": "grille", "criteres_hors_dossier": [...]}],
 "du_marche": {"alloti": true, "lots": [{"numero", "intitule", "phrase", "source", "origine", "origine_libelle"}],
               "annonce": 3, "message": "...", "unique": "", "choisis": ["2", "3"], "regle_commune": "..."},
 "regle_commune": "Partie commune quand son intitulé parle de présentation, …",
 "nommage": {"modele", "phrase", "source"} | null}
```
Pour un dossier à un seul lot : `{"actif": false, "liste": [], "du_marche": {...} | null, "regle_commune", "nommage":
null}`.

Chaque partie (`sections[]`) porte `lot` (`""` commune), `lot_libelle`, `commune` (dossier à plusieurs lots seulement),
`portee_modifiable` ; son `titre` dit son lot. `sections_retirees[]` porte `lot_libelle`.

Dossier à plusieurs lots, en tête de l'état : `compteur.total` vaut `null` (le compteur est celui de chaque lot) ;
`limites` réunit les limites du document de chaque lot (« Dossier du lot 2 : … », avec `lot`) et celles des
parties, une fois ; `blocage` est l'**ensemble** (pour la carte du marché) : ses raisons nomment le lot de chaque
partie (« 1.1 Méthodologie (lot 3) »), `peut_exporter` vaut si CHAQUE lot peut être exporté, `derogation` est celle
d'un lot quand tous peuvent l'être et qu'au moins un l'est par dérogation, `etat_hash` est l'empreinte des lots,
`par_lot: true` ; `derogations_possibles` est vide (une dérogation se demande lot par lot) ; `export` est l'aperçu du
premier lot. `exigences` : les titres nomment le lot. `grille` (changements de « Comment vous serez noté » depuis le
plan) : relue pour chaque lot (J.4) seulement si la grille du marché a changé ; « Mettre le plan à jour » ajoute
une partie par critère confirmé depuis dans chaque lot qui le note (commune si la règle le dit et que tous les lots
le notent) et reprend les poids de chaque lot.

### J.8 L'export d'un lot

- **Contenu** : les parties communes (leur texte commun, le même dans chaque fichier) et les parties du lot, dans
  l'ordre du dossier du lot, numérotées pour lui ; page de garde : « Lot : 2 — Couverture et zinguerie » sous
  « Marché » ; mêmes règles qu'avant (aucune marque interne, mention « Préparé avec assistance IA » seulement si
  l'IA a servi pour un texte de CE fichier).
- **Nom** (`atelier_lots.nommage` + `nom_du_lot`) : la règle de nommage du règlement (« Chaque mémoire est remis
  dans un fichier nommé « Lot X - Mémoire technique - Nom du candidat » », repérée sans IA, avec sa phrase) est
  suivie quand Adjugo sait remplir chacun de ses champs — numéro du lot (« X », « XX » → « 02 », « n », « [n° du
  lot] »…), nom du candidat (« Nom du candidat », « [raison sociale] », « NomEntreprise »… → le nom de l'entreprise
  du profil), intitulé du lot ; une règle sans numéro de lot reçoit « - Lot 2 » (un fichier par lot). Un champ
  inconnu (« [SIRET] ») ou un nom d'entreprise absent : nom par défaut et message (« … qu'Adjugo ne sait pas
  compléter : renommez le fichier avant de le déposer », « renseignez le nom de votre entreprise »). Sans règle :
  « Mémoire technique - Lot 2 - Couverture et zinguerie » (le nom du document est celui du règlement, comme avant).
  L'aperçu le dit avant l'export (`export.nommage`).
- **Blocage** : celui du dossier du lot (parties vides, « [À compléter] », faits à relire, partie d'un partenaire
  en attente, limite dépassée de CE lot) ; avertissement « Dossier du lot 2 non validé : N parties à valider ».
- **Dérogation** : pour CE lot et CET état seulement ; inscrite au journal chaîné AVANT d'être retenue (méta `lot`) ;
  une dérogation du lot 2 n'ouvre jamais l'export du lot 3. L'empreinte d'état d'un lot inclut son numéro (celle
  d'un dossier à un seul lot est inchangée, J.13).
- **Après l'export** : `dernier_export["lots"][n]`, fichier rangé dans le dossier du marché (« Mémoire technique »,
  un nom par lot : aucun ne remplace l'autre), liste des pièces mise à jour (jusqu'à 2 × lots + 2 fichiers gardés),
  journal chaîné (`atelier.export`, méta `lot`).
- **Dossier commun** (« Préparer mes documents », ZIP) : un fichier Word et un PDF PAR LOT (clés `docx:2`,
  `pdf:2`), chacun soumis aux règles de l'export de son lot ; un lot bloqué sans dérogation n'est pas joint
  (« BLOQUANT — Lot 2 — … : dossier de présentation non joint : … ») ; versions validées de préférence, comme avant.

### J.9 La rédaction (IA)

- **Économie sans perte** : une partie commune est rédigée UNE fois pour tous les lots (une seule action d'IA, un
  seul texte) ; le dossier compte toujours pour UNE analyse (décision 6a), tous lots compris ; rien d'autre ne
  change dans le débit, le remboursement, `tenant_scope` et `pii_scope`.
- **Consigne** (partie propre au dossier, hors du bloc mis en cache) : « CETTE PARTIE CONCERNE SEULEMENT LE LOT 3
  (Étanchéité des toitures-terrasses) : elle figure dans le dossier de ce lot ; ne parle que des travaux de ce lot. »
  ou « CETTE PARTIE EST COMMUNE À TOUS LES LOTS DU DOSSIER (Lot 2 — … ; Lot 3 — …) : elle figure telle quelle dans le
  dossier de chacun ; n'y parle d'aucun lot en particulier. » ; « Autres parties du dossier » : celles du dossier
  du lot (avec ses numéros), ou les intitulés de toutes (une fois chacun) pour une partie commune. L'intitulé d'un
  lot vient du règlement (public) ; rien de l'entreprise n'est ajouté.
- **Contrôle des faits** : « lot 2 », « lots 2 et 3 », « lot n° 3 » désignent un lot du marché, jamais une quantité :
  ce numéro n'est pas un fait à relire (`faits_a_relire._LOT_REF`). Tout autre nombre reste contrôlé comme avant.

### J.10 L'entretien chantier

La question qui concerne une partie propre à un lot vaut aussi pour la même partie des autres lots (le chantier est
le même) : sa réponse est un fait autorisé [R#] de chacune, et sa question passée y laisse son « [À compléter] »
(`entretien_chantier.pour_parties`). Rien d'autre ne change.

### J.11 Groupement

- **« Qui écrit quoi »** (pré-remplissage sans IA, `atelier_groupement.proposition`) : la partie propre à un lot est
  proposée au membre qui a déclaré CE lot dans sa part (« Lot 3 », « lots 2 et 3 », « lot n° 3 », ou les mots de
  l'intitulé du lot, même début de mot), lui seul — message : « Proposé d'après le lot de X (« Lot 3 : … ») : cette
  partie est celle du lot 3 (« … ») ». Personne : « Proposé au chef de file : aucun partenaire n'a déclaré le lot 2
  (« … »). » ; plusieurs : chef de file, « choisissez qui rédige ». Une partie commune suit la règle d'avant. Le chef
  de file reste maître du choix.
- **Ce que voit un membre** : chaque partie du dossier assemblé et de « Mes parties » porte son lot (`lot`,
  `lot_libelle`, `commune`) — public : le règlement le nomme ; la note « ce que l'acheteur note » d'une partie d'un
  lot cite la phrase du règlement pour CE lot. Rien d'autre : le cloisonnement de la vague 4 est intact (brouillons,
  sources, extraits, tâches, documents déposés jamais chez un autre).

### J.12 Démo (`app/services/demo_lots.py`)

Un marché FICTIF réparti en trois lots, « Restructuration — École maternelle Les Hirondelles (3 lots) », Ville de
Trémorvan (fictive), auquel Bâtiment de l'Ouest répond sur les lots 2 (couverture et zinguerie) et 3 (étanchéité des
toitures-terrasses) : dossier (règlement, deux CCTP de lot, décomposition du prix) mis en PDF puis lu EN ENTIER ;
analyse par `finalize_analysis` ; lots repérés et plan construits par le vrai moteur, sans IA ; une partie commune
(gestion environnementale, validée) et, pour chaque lot, ses parties (lot 2 : validées ; lot 3 : un brouillon et une
partie à écrire) ; textes fictifs, faits contrôlés sans IA (aucun fait à relire) ; entretien chantier préparé. La démo
montre : un fichier par lot nommé comme le règlement l'exige (« Lot 2 - Mémoire technique - Bâtiment de l'Ouest »), le
lot 2 « Prêt à exporter », le lot 3 « Bloqué » (une partie sans texte), la limite de 6 pages contrôlée lot par lot, la
partie commune dans les deux dossiers. Seed rejouable (clés de stockage liées au contenu), isolé dans SA transaction
(un échec laisse les six autres marchés). Le visiteur ne change rien (lots, portée, export, dérogation : 403
« lecture guidée », sans coût). La vitrine compte désormais 7 marchés.

### J.13 Marché à un seul lot : rien ne change

Garanties testées (`tests/test_redaction_v6_lots.py`) : plan identique (aucune étiquette, aucun `lot`), `plan_meta`
sans `lots`, compteur et export d'avant (« Mémoire justificatif.docx »), un lot donné à l'export refusé (422
`lot_inconnu`), empreinte d'état calculée exactement comme avant (une dérogation déjà enregistrée en production reste
valable), réponse à UN lot d'un marché alloti = un seul dossier. Les champs nouveaux de l'état (`lots`, `lot_libelle`,
`commune`, `portee_modifiable`, `lot` d'une limite et d'un blocage) sont vides ou faux.

### J.14 Limites connues, choix à dire à Eliot

- **Repérage des lots** : les lots écrits dans un TABLEAU du règlement sans « Lot n » en tête de ligne, ou seulement
  dans un document scanné non reconnu, ne sont pas repérés : l'utilisateur les ajoute (« indiqué par vous »).
- **Grille par lot en tableau** (colonnes « Lot 1 | Lot 2 ») : jamais lue ligne à ligne ; critères repris sans poids,
  et on le dit (choix : aucun poids deviné plutôt qu'un poids d'un autre lot).
- **Liste des exigences** : elle reste celle du dossier entier (« 11 exigences traitées sur 12 » sur l'ensemble des
  parties), pas lot par lot.
- **Règle commune / propre** : une règle de mots sur l'intitulé, dite dans la bulle ; l'utilisateur change chaque
  partie. « Références » est propre à chaque lot (références de travaux similaires au lot).
- **Plan du cadre** : si un lot a un cadre de réponse imposé et un autre non, le dossier n'est pas « plan du cadre »
  (ordre libre) ; chaque lot garde les numéros de son cadre.

### J.15 Vérifications

- tests : `tests/test_redaction_v6_lots.py` (repérage, grille par lot, règle, nommage, deux lots, partie commune
  modifiée, exports séparés, limites et dérogation par lot, portée, changer les lots, ajouter une partie, dossier
  commun, consigne de l'IA simulée, groupement, marché à un seul lot inchangé, empreinte inchangée),
  `tests/test_demo_plusieurs_lots.py` ; tests de la démo mis à jour (7 marchés, 2 dossiers de présentation) ;
- suite complète verte ; SRI à jour (`scripts/sri_update.py --check`) ; `node --check` ; gabarits Vue compilés ;
- écrans vus dans le navigateur (1 024 px et 375 px, aucun débordement horizontal, aucune erreur de console) ;
- aucune migration ; sur un vrai Postgres, depuis l'état exact de la production (`a29173a`, tête
  `z1entretienchantier`) : données créées par le code de production, puis le code nouveau (plan à plusieurs lots,
  portée, export par lot, dérogation par lot, dossier commun), puis le code de production relancé sur les mêmes
  données ; les tests rejoués sur Postgres, échecs comparés à ceux du code de production à conditions égales.
