# Rédaction, vague 5 — « Coller au chantier et à l'acheteur » : contrat

Étude « rédaction » § 8 (V5) : l'entretien chantier (D, § 6.9), la liste complète des exigences et les
sous-critères (C2 complet, § 6.3), les références tirées des DECP et les qualifications RGE (E2, § 6.7).
Chaque chantier a sa section ; la doctrine (§ 7) vaut pour tous : un fait ne vient jamais de l'IA, on ne dit
jamais le mot interdit, le cadre de l'acheteur commande, la matière reste chez son propriétaire.

---

## D — L'entretien chantier : « Adjugo demande au lieu de deviner »

Étude § 6.9, doctrine § 7, décisions **D8 (a)** (CV et noms jamais à l'IA), **D9 (a)** (mention « préparé avec
assistance IA » dans les propriétés du fichier, inchangée : l'entretien ne change pas la règle), **D10 (c)** (aucun
contrôle de ressemblance entre clients), **D11 (c)** (la mesure « fichier de réponse imposé » existe déjà :
`docs/REDACTION_V2_API.md` § 6 ; l'avertissement et le Word dans l'ordre du cadre sont gardés).

Code :
- banque de questions, sans IA : `app/services/entretien_banque.py` (41 questions BTP) ;
- règles (seul point d'écriture) : `app/services/entretien_chantier.py` ;
- routes : `app/routers/entretien.py` ;
- branchements : `app/services/atelier.py` (`Contexte.fiches`, `_executer`, `etat`, `creer_dossier`),
  `app/services/agents/memoire.py` (consigne de la partie), `app/services/atelier_groupement.py` (espace du
  partenaire, son aide de l'IA, RGPD), `app/services/faits_sources.py` (renvoi `R`), `app/services/memoire_export.py`
  et `app/services/faits_a_relire.py` (renvois `[R#]` retirés à l'export, ignorés au repérage) ;
- écrans : `app/static/app.html` + `app/static/app.js` (bloc « n questions sur ce chantier » de l'atelier,
  méthodes `atlEnt…`), `app/static/redaction-partenaire.js` (`renderEntretien`, `repondreQuestion`),
  `app/static/styles.css` (`.atl-ent…`, `.rp-ent…`) ;
- démo : `app/services/demo_entretien.py` (appelé par `demo_redaction.seed_redaction`) ;
- migration : `alembic/versions/z1entretien_entretien_chantier.py` (`z1entretienchantier`, après
  `y9z0depotlien`, la migration du dépôt de documents par le lien) ;
- tests : `tests/test_redaction_v5_entretien.py`.

Vocabulaire à l'écran : « questions sur ce chantier », « fiche chantier », « Passer », « Sans objet », « Posée
à », « groupement / partenaire / chef de file » ; jamais « vérifié », jamais « signer », zéro émoji.

### D.1 Ce que voit l'utilisateur

**Chef de file (atelier, page du marché).** Sous l'en-tête de l'atelier, une carte « 8 questions sur ce
chantier » avec sa bulle (i), une pastille (« 5 à répondre », « Toutes traitées ») et un bouton « Répondre aux
questions ». Elle se déplie d'elle-même à la première ouverture d'un atelier encore sans texte (« avant la
rédaction des parties notées »). Pour chaque question :
- la question, son renvoi (`R3`) et son statut (À répondre, Répondue, Passée, Sans objet) ;
- **la phrase du dossier qui la motive**, telle qu'écrite, et sa pièce (« Clauses techniques (CCTP) ») ; une
  question posée sans phrase (l'environnement, quand le dossier n'en dit rien) le dit : « Question posée pour tout
  chantier : aucune phrase du dossier lu n'en parle. » ;
- la partie concernée et le critère concerné, avec son poids tel qu'écrit ;
- la réponse : un texte court (1 500 caractères au plus) ; pour « Qui sera le chef de chantier ? », la liste
  « Équipe » de « Mes preuves » (nom et fonction, jamais le CV) et, au besoin, une précision écrite ;
- « Enregistrer la réponse », « Passer » (« la partie concernée gardera « [À compléter : chef de chantier] » »),
  « Sans objet » (rien ne sera écrit à ce sujet) ; « Modifier la réponse » ensuite ;
- en groupement (« Qui écrit quoi » préparé) : « Posée à » (Votre entreprise ou un partenaire) ;
- en bas : « Chercher d'autres questions avec Adjugo » (option IA, sur ordinateur), et « Fiche chantier (n) »
  repliée : renvoi, thème, réponse, « déclaré par vous » ou « déclaré par Breizh Couverture ».

Avant « Rédiger avec Adjugo » (une partie ou toutes), la fenêtre de confirmation de l'atelier le dit : « 3
questions sur ce chantier attendent une réponse : sans elle, Adjugo n'écrit rien à ce sujet et laisse « [À
compléter] » si la partie en a besoin… » et « Une question passée : sa partie gardera « [À compléter] ». ».

**Téléphone (375 px).** Répondre, passer, « sans objet » et « Posée à » restent possibles (l'écriture des
parties, elle, reste sur ordinateur) ; la recherche avec l'IA n'est pas proposée.

**Partenaire (son espace : lien + clé, ou « Partagé avec moi »).** Un bloc « 2 questions du chef de file sur ce
chantier » avec sa bulle (i) : la question, la phrase du dossier, la partie concernée, « Envoyer ma réponse »
(fenêtre : « Votre réponse sera lue par le chef de file, qui s'en servira pour rédiger le dossier commun comme un
fait déclaré par votre entreprise. »), « Passer », « Sans objet » ; « Modifier ma réponse » ensuite. La pastille
« n à faire » compte ses questions sans réponse ; la liste « Partagé avec moi » dit « 2 questions sur le chantier »
quand il n'a rien d'autre à faire.

### D.2 La banque et le déclenchement (sans IA)

- **41 questions BTP** (`entretien_banque.BANQUE`), chacune avec : ses déclencheurs (expressions cherchées dans le
  texte replié du dossier), les débuts de mots de ses critères (dans l'ordre), de ses parties et des lots, le
  passage « [À compléter : … ] » qu'elle laisse, sa famille (`environnement`) et son type de réponse (`equipe`
  pour le chef de chantier). Déclencheurs couverts : site occupé, établissement recevant du public, école et
  élèves, personnes fragiles, travaux de nuit ou décalés, amiante, plomb, voirie, co-activité, Architectes des
  Bâtiments de France, phasage, toiture, travail en hauteur, intempéries, dépose et démolition, réseaux,
  continuité de service, poussières, points chauds, levages, accès et livraisons, base vie, déchets, bruit et
  nuisances, réemploi, transports, pollution, arbres, environnement, chef de chantier, sous-traitance, insertion,
  périodes imposées, délai, visite, contrôles et essais, dossier des ouvrages exécutés, matériaux, garantie de
  parfait achèvement, information des riverains, sécurité des compagnons.
- **La pièce lue** : la lecture intégrale rangée (toutes les pièces) ; sinon l'ancienne lecture bornée ; sinon
  l'extrait de l'analyse. Ordre de recherche : cadre de réponse, CCTP, règlement, CCAP, autres pièces, acte
  d'engagement, bordereaux.
- **La phrase qui motive** (`phrase_du_dossier`) : une vraie phrase, de la fin de la précédente à sa propre fin, à
  travers les retours de ligne d'un PDF, sans traverser un intitulé ni une ligne vide ; à défaut une ligne courte
  (un critère : « Moyens humains et encadrement : 10 % »). Elle repasse par `citation_guard` (suite exacte du
  texte de sa pièce) ; une phrase déjà montrée par une question plus prioritaire n'est reprise que si le dossier
  n'en a pas d'autre. **Une phrase qui nie** (« aucune présence d'amiante », « les travaux de nuit ne sont pas
  prévus ») ne déclenche rien ; un intitulé d'un mot (« Article 2 - Amiante ») non plus.
- **Le classement** : le critère concerné est le premier début de mot de la question retrouvé dans un critère
  technique de « Comment vous serez noté » (le plus lourd s'il y en a plusieurs ; sinon le critère unique, ou le
  seul critère « technique ») ; son poids TEL QU'ÉCRIT classe la question. D'abord la meilleure question de chaque
  critère (du plus lourd au plus léger), puis la suivante de chacun, etc. ; une question qu'aucun critère ne
  concerne passe après ; à poids égal, l'ordre de la banque. **8 questions au plus.** L'écran les montre du critère
  le plus lourd au plus léger.
- **L'environnement déclenche toujours une question** : la meilleure question « environnement » déclenchée, sinon
  la question générale sans phrase du dossier (l'écran le dit).
- **La partie concernée** (`partie_concernee`) : celle où se retrouvent le mieux les débuts de mots de la question
  (intitulé, critère, question du cadre, titres parents) ; sinon celle du critère concerné ; sinon la première
  partie de méthode ou d'organisation ; sinon la première partie. Calculée à chaque lecture (le plan peut changer).
- **Préparation** (`preparer`, idempotente, sans IA ni débit) : avec le dossier de présentation (`creer_dossier`),
  puis de nouveau quand le plan est reconstruit (le dossier du marché est relu) et quand « Qui écrit quoi » est
  préparé ; l'écran prépare à la première ouverture un dossier d'avant la vague 5 (`POST /entretien`). Une question
  déjà posée garde son numéro, sa réponse et son destinataire choisi à la main ; une question de la banque qui
  n'est plus proposée (dossier réimporté) et sans réponse est retirée (ligne gardée, numéro réservé) ; la phrase
  d'une question sans réponse suit le dossier actuel ; le destinataire d'une question sans réponse jamais choisi à
  la main suit la répartition.

### D.3 La fiche chantier : des faits « déclaré par vous » pour l'atelier

- Chaque réponse est un fait numéroté **`[R3]`** (numéro STABLE dans le dossier, jamais réutilisé), remis à l'IA
  et au contrôle des faits (A) avec les autres faits autorisés :
  `[R3] (déclaré par vous) Entretien chantier, réponse à « Le site reste occupé… ? » : Accès des compagnons par le
  portail nord…`. Pour le contrôle, la fiche porte le thème et la réponse (le nom de la personne choisie compris) ;
  pour l'IA, la question et la réponse (l'étiquette de la personne, jamais son nom).
- **Chef de chantier (D8 a)** : la personne choisie dans « Mes preuves » (fiche « Équipe » acceptée et utilisable)
  est remise sous son étiquette (`[Cheffe de chantier 1], Cheffe de chantier (sa fiche : [F7])`) : son nom est
  masqué avant l'appel (`pii_scope`), remis en clair sans IA dans le texte rendu ; son CV s'insère tel quel par
  « [CV F7] » (inchangé, `fs.inserer_cv`). Une fiche retirée ou expirée : la réponse ne sert plus (l'écran le dit :
  « La fiche « Équipe » choisie n'est plus utilisable… »), la question laisse « [À compléter] ».
- **Les noms dans une réponse écrite** : repérés sans IA comme les autres faits remis (`equipe_avec_noms_reperes`)
  et masqués avant l'appel.
- **La consigne de la partie** (`memoire._consigne_partie`) : « ENTRETIEN CHANTIER : les réponses [R2], [R5]
  concernent cette partie : sers-t'en ici (avec leur renvoi), sans rien y ajouter. » ; puis les points passés
  (« n'écris AUCUN texte général à leur place ; écris seulement… le passage indiqué tel quel : [À compléter : chef
  de chantier] ») et les questions encore sans réponse (« n'écris aucun fait à leur sujet ; si la partie doit en
  parler, écris le passage indiqué tel quel… »).
- **Une question PASSÉE laisse son « [À compléter : … ] » dans la partie concernée** : consigne de l'IA, puis,
  sans IA, le passage est ajouté en fin de partie s'il manque (`garantir_manques` ; pas de doublon si l'IA l'a
  écrit, même avec un autre libellé du même objet). Il bloque l'export comme tout « [À compléter] » (décision 2b,
  dérogation possible). **Une question encore sans réponse** : l'IA n'écrit aucun fait à son sujet et laisse le
  passage si la partie doit en parler (consigne), l'écran prévient avant de rédiger. **« Sans objet »** : rien.
- **Contrôle des faits (A)** : un fait de la phrase relié à `[R3]` porte la source `{ref: "R3", type: "declare",
  libelle: "déclaré par vous"}` ; une réponse modifiée après la rédaction est relue au prochain « Recontrôler »
  (comme le profil). Les renvois `[R#]` sont retirés à l'export (`clean_markdown`), montrés comme les autres
  renvois à l'écran (`atlRefs`, `rpTexte`).
- Rien ne change pour un marché sans entretien (aucune question) : aucun fait `[R#]`, aucune consigne.

### D.4 Groupement : la question du lot d'un partenaire, posée dans SON espace

- **Proposition, sans IA** (« Qui écrit quoi » préparé) : le partenaire à qui la partie concernée est confiée ;
  sinon celui dont le lot, et lui seul, correspond à la question (débuts de mots `lots` : « Couverture et
  zinguerie » ↔ accès à la toiture) ; sinon votre entreprise. Le chef de file change le destinataire (« Posée à ») ;
  un choix fait à la main n'est jamais repris par une préparation suivante.
- **Le partenaire la lit et y répond chez lui** : `GET …/redaction` → `entretien` (seulement les questions qui LUI
  sont posées) ; `PUT …/redaction/entretien/{qid}`. Mêmes garde-fous qu'un envoi : clé de l'espace par le lien
  (403 `cle_espace_requise`), avertissement lu (422 `avertissement_requis`, message à afficher), identité prouvée
  quand le lien vise une adresse (403 `identity_unverified`), co-construction ouverte, démo refusée avant tout.
  Comme ses autres écritures (contrat V4 § 21), le verrou de l'invitation est pris D'ABORD, avant celui de la
  question : l'invitation est relue, la clé présentée doit encore ouvrir l'espace (409 `espace_reinitialise`,
  rien d'écrit, l'écran se recharge) et le lien être actif (retiré entre-temps : 404 `question_introuvable`).
  Inscrit au journal chaîné (`entretien.reponse`, son journal : « Vous avez répondu à une question du chef de file
  sur le chantier »). Une réponse envoyée reste quand l'espace privé est réinitialisé (comme un texte envoyé) ;
  ses documents déposés par le lien (« Vos documents pour Adjugo ») ne sont jamais lus par l'entretien.
- **Sa réponse est SA donnée** : le chef de file la lit (« déclaré par Breizh Couverture ») sans pouvoir la
  modifier (403 `question_d_un_partenaire` sur sa propre route) ; dans son atelier elle est un fait
  `T_PARTENAIRE` (« déclaré par votre partenaire ») qui n'appuie qu'une phrase qui nomme ce partenaire (règle
  « qui affirme quoi » de A). Adresser la question à un autre la sort de la fiche chantier (409
  `reponse_a_confirmer`, puis effacée) ; retrait ou déclin de l'invitation : ses réponses sont effacées, ses
  questions reviennent au chef de file, à répondre.
- **L'IA du partenaire** ne reçoit que SES réponses (« déclaré par vous » pour lui) et ses propres questions
  passées ou sans réponse de SA partie ; jamais les réponses du chef de file ni d'un autre membre. Celle du chef de
  file reçoit les réponses de ses partenaires encore membres.

| | Chef de file | Le partenaire questionné | Les autres membres |
|---|---|---|---|
| Questions posées à son entreprise, leurs réponses | oui | jamais | jamais |
| Question posée à un partenaire, la phrase du dossier | oui | oui | jamais |
| Réponse de ce partenaire | oui (en lecture, « déclaré par » lui) | oui (la sienne) | jamais |
| Liste « Équipe » de « Mes preuves » | oui (la sienne) | jamais | jamais |

### D.5 Option IA : « Chercher d'autres questions avec Adjugo »

- Tâche de fond du chef de file (`atelier_entretien`, dans `atelier.JOB_KINDS` : lue par
  `GET /api/atelier/{pid}/taches/{job_id}`, reprise au redémarrage avec le remboursement de l'atelier).
- **Compte sur le plafond de l'atelier (décision 6a)**, comme « Harmoniser le ton » : une refonte du dossier ; la
  première action de l'IA du dossier compte pour 1 analyse (la première rédaction de chaque partie y est ensuite
  comprise). 409 `debit_a_confirmer` au-delà des refontes gratuites (fenêtre de l'atelier). **Rendu si l'IA tombe ou
  si aucune question n'est retenue.** Garde-fou de l'essai (`budget_ia.verifier`, enveloppe `entretien` : 64 000
  caractères, 1 600 tokens en sortie).
- **Ce qui part à l'IA** : la consigne, les questions déjà posées, le dossier de l'acheteur (CCTP, cadre,
  règlement, CCAP, autres pièces ; jamais les bordereaux de prix ni l'acte d'engagement), 60 000 caractères au plus
  partagés équitablement. Aucun fait de l'entreprise, aucun nom, aucun CV. `tenant_scope` (espace facturé du chef
  de file) et `pii_scope` posés sur l'appel. Tâche du routage : `exigences` (lecture du dossier de l'acheteur,
  Mistral puis Claude en secours — aucune ligne du routage ni des pages juridiques ne change).
- **Contrôle sans IA de chaque question proposée** : sa phrase retrouvée MOT POUR MOT dans le dossier
  (`citation_guard`, 20 caractères au moins) ; aucun nombre de la question absent de la phrase ; une vraie question
  (12 à 300 caractères, sans renvoi, lien ni adresse) ; ni la même question ni la même phrase qu'une question déjà
  posée. Au plus **4 questions de l'IA** par dossier (`MAX_IA`), ajoutées après celles de la banque, avec
  « Proposée par Adjugo avec l'IA, d'après une phrase du dossier ».

### D.6 Le modèle et la migration

Table **`entretien_questions`** (`EntretienQuestion`) : une ligne par question d'un dossier de présentation.

| colonne | sens |
|---|---|
| `dossier_id` (clé étrangère), `project_id`, `owner_id` | le dossier, le marché, le tenant du chef de file |
| `numero` (unique dans le dossier) | renvoi `R<numero>`, stable, jamais réutilisé |
| `code` (unique dans le dossier), `origine` | code de la banque ou `ia-<empreinte>` ; `banque` ou `ia` |
| `theme`, `question`, `type_reponse` | ce qui manque si on passe ; le texte posé ; `texte` ou `equipe` |
| `motif`, `motif_piece` | la phrase du dossier, telle qu'écrite ; le libellé de sa pièce |
| `ordre`, `retiree_le` | ordre d'affichage ; question plus proposée (gardée) |
| `adresse_kind`, `adresse_invite_id`, `adresse_choix` | `organisation` ou `invitation` ; le partenaire ; `propose` ou `manuel` |
| `statut` | `a_repondre`, `repondue`, `sautee`, `sans_objet` |
| `reponse`, `reponse_preuve_id` | le texte ; la fiche « Équipe » choisie |
| `reponse_kind`, `reponse_invite_id`, `reponse_user_id`, `repondu_le` | qui a répondu (organisation ou invitation), le compte, quand |
| `lock_version` | verrou optimiste (409 `question_modifiee`) |

Migration `z1entretienchantier` (après `y9z0depotlien`, une seule tête Alembic) : idempotente (table créée si elle
manque, colonnes et index ajoutés s'ils manquent), SQLite et Postgres, valeurs par défaut côté base identiques au
modèle ; downgrade réel (table supprimée, rien d'autre). Déploiement sans casse : le code de production précédent
ne lit ni n'écrit la table. (Écrite d'abord après `x8y9redactionv4` ; chaînée après le dépôt par le lien quand la
production l'a reçu, à la fusion de la production dans cette branche.)

### D.7 Routes

Chef de file (portée organisation ; un marché d'une autre organisation → 404 `marche_introuvable`, aucun dossier →
404 `dossier_introuvable`). Erreurs métier : `detail = {code, message}`.

| méthode | route | corps | réponse et erreurs |
|---|---|---|---|
| GET | `/api/atelier/{pid}/entretien` | — | `Entretien` (ci-dessous) ; pas encore préparé : la proposition (`prepare: false`, questions sans `id`) |
| POST | `/api/atelier/{pid}/entretien` | — | `Entretien` + `preparation: {creees, retirees, reproposees}` ; 409 `reessayer` |
| PUT | `/api/atelier/{pid}/entretien/{qid}` | `{statut: repondue\|sautee\|sans_objet\|a_repondre, reponse?, preuve_id?, lock_version?}` | `Entretien` + `question_id` ; 404 `question_introuvable`, 403 `question_d_un_partenaire`, 409 `question_modifiee`, 422 `statut_invalide`, `reponse_vide`, `reponse_trop_longue`, `personne_introuvable`, `personne_inattendue` |
| PUT | `/api/atelier/{pid}/entretien/{qid}/adresse` | `{invite_id: int\|null, confirmer?}` | `Entretien` + `question_id` ; 409 `groupement_non_prepare`, `partenaire_indisponible`, `reponse_a_confirmer` (message à afficher, puis renvoyer avec `confirmer: true`). Aucun email. |
| POST | `/api/atelier/{pid}/entretien/ia` | `{accepte_debit?}` | 202 `{tache, quota}` ; suivre `/api/atelier/{pid}/taches/{job_id}` : `result = {ajoutees, refusees, message}`, `error` si l'IA tombe ; 409 `entretien_ia_en_cours`, `plafond_questions_ia`, `debit_a_confirmer`, `premiere_redaction_en_cours` ; 422 `dossier_absent`, `aucune_partie` ; 402 essai ; 403 démo, `email_non_confirme` |

Partenaire : `PUT /api/invite/{token}/redaction/entretien/{qid}` (lien + `X-Adjugo-Espace`) et
`PUT /api/shared/{pid}/redaction/entretien/{qid}` (compte) ; corps `{statut, reponse?, avertissement_lu, lock_version?}`
→ `entretien` du partenaire. 404 `question_introuvable` (une question qui ne lui est pas posée n'existe pas pour
lui), 403 `cle_espace_requise`, `identity_unverified`, `co_construction_fermee`, `demo` ; 422
`avertissement_requis`, `reponse_vide`, `reponse_trop_longue` ; 409 `question_modifiee`.

`Entretien` (chef de file) : `{prepare, message: "8 questions sur ce chantier", bulle, max: 8, questions:
[Question], compteurs: {prepare, total, repondues, a_repondre, passees, sans_objet, chez_partenaires}, fiche: [{ref,
theme, texte, libelle}], equipe: [{preuve_id, ref, nom, fonction}], dossier_present, groupement: {actif, membres:
[{invite_id, nom, lot}]}, ia: {en_cours: {job_id, statut}|null, proposees, restantes, plafond, bulle, quota},
statuts}`.

`Question` : `{id, numero, ref: "R3", code, origine, origine_libelle, theme, question, type_reponse, aide, motif:
{phrase, piece}|null, motif_message, critere: {critere, poids, poids_source}|null, partie: {section_id, titre,
redacteur}|null, adresse: {type, invite_id, nom, choix}, statut, statut_libelle, reponse: {texte, preuve_id,
personne: {nom, fonction, ref}|null, personne_retiree, par, le, libelle}|null, par, a_completer, peut_repondre,
lock_version}`.

Vue du partenaire (`GET …/redaction` → `entretien`) : `{questions: [{id, numero, theme, question, type_reponse:
"texte", motif, motif_message, partie, statut, statut_libelle, reponse: {texte, le}|null, a_completer,
lock_version}], total, a_repondre, message, avertissement, statuts}`. « Partagé avec moi » : `redaction.questions`
(ses questions sans réponse).

État de l'atelier (`GET /api/atelier/{pid}`) : `entretien` = les compteurs (deux requêtes, sans IA) ; pour un
dossier d'avant la vague 5, `prepare: false` et `proposees` (combien l'entretien poserait, lecture en cache).

### D.8 Démo (vitrine, sans IA ni réseau)

- `demo_entretien.seed_entretien` remplit l'entretien du marché « toiture » avec le VRAI moteur (questions de la
  banque sur le dossier fictif, phrases retrouvées, classement par les poids du règlement fictif) et des réponses
  FICTIVES : « cohabitation avec les occupants » et « tri et filières des déchets » répondues, « chef de chantier »
  = la fiche « Équipe » fictive d'Erwan Le Bris, « planning calé sur les périodes imposées » passée ; les autres à
  répondre. Dans la transaction du seed (aucun commit), effacé à la remise à neuf (`demo_seed`).
- Toutes les routes d'écriture sont classées dans `tests/test_demo_sans_cout.py` (`COUTS` : la recherche avec l'IA ;
  `SANS_COUT` : préparer, répondre, adresser, la réponse du partenaire) et refusées à la démo par le garde central
  ET dans la route (`refuser_demo`) ; le lien partenaire de la démo est refusé avant tout autre contrôle. L'écran
  de la démo lit l'entretien (`POST` refusé → `GET`).

### D.9 RGPD et cycle de vie

| événement | effet |
|---|---|
| Effacement du compte du chef de file, corbeille purgée | l'entretien part avec le dossier (`ag.effacer_dossiers` → `ec.effacer_dossiers`) |
| Effacement d'un compte (partenaire ou membre) | ses réponses restent à l'organisation ou à l'invitation qui les a données, sans le compte (`reponse_user_id` vidé) |
| Retrait ou déclin d'une invitation | ses réponses effacées, ses questions rendues au chef de file, à répondre |
| Transfert de propriété, membre effacé, dossier réaffecté | les lignes suivent `owner_id` comme l'atelier |
| Export RGPD du chef de file | `entretiens_chantier` (questions, phrases, réponses — celles de ses partenaires comprises) |
| Export RGPD et portabilité du partenaire | `reponses_entretien_chantier` dans sa part : les questions qui lui sont posées et SES réponses |

### D.10 Choix faits par défaut (à valider par Eliot)

1. **L'entretien est préparé avec le dossier de présentation** (sans IA, sans débit), et de nouveau quand le plan
   est reconstruit ou « Qui écrit quoi » préparé : la carte dit tout de suite « 8 questions sur ce chantier », et elle
   se déplie d'elle-même tant qu'aucune partie n'a de texte.
2. **Une question passée laisse un « [À compléter] » garanti** dans sa partie (ajouté sans IA) ; une question
   encore sans réponse ne force rien : l'IA est prévenue (aucun fait, passage si la partie en a besoin) et l'écran
   prévient avant de rédiger. Raison : ne pas couvrir d'« [À compléter] » les parties de ceux qui rédigent avant
   d'avoir ouvert les questions, sans jamais laisser l'IA remplir le vide.
3. **« Sans objet sur ce chantier »** existe en plus de « Passer » : un mot du dossier peut déclencher une question
   qui ne concerne pas ce chantier ; elle ne laisse alors rien.
4. **Poser une question à un partenaire exige « Qui écrit quoi » préparé** (c'est là qu'il a son espace) ; aucun
   email n'est envoyé (« Demander les parts » reste le seul envoi ; à étendre aux questions si le terrain le
   demande).
5. **Le chef de chantier d'un partenaire s'écrit** (sa liste « Équipe » reste chez lui) ; la liste « Équipe » est
   proposée au chef de file seul.
6. **Option IA : 4 questions de plus au plus par dossier**, tâche du routage `exigences` (lecture du dossier).

### D.11 Limites connues

- Tout repose sur la qualité de la banque (risque de l'étude) : Mathys la valide avec les 7 PME ; elle se modifie
  sans migration. Un déclencheur peut se tromper de sens (« les travaux de nuit sont interdits » déclenche la
  question des travaux de nuit) : la phrase est montrée, « Sans objet » la referme.
- La négation n'est repérée que dans une fenêtre courte autour du mot (« aucune », « sans », « ne … pas ») ; une
  négation lointaine passe.
- Le classement suit le poids du critère dont le nom contient un début de mot de la question ; une grille aux
  intitulés inhabituels rattache tout au seul critère « technique », ou à aucun.
- Une réponse modifiée après la rédaction n'est relue qu'au prochain « Recontrôler » de la partie (comme le
  profil) ; le texte déjà rédigé n'est jamais réécrit sans geste de l'utilisateur.
- Un nom de personne écrit dans une réponse n'est masqué avant l'IA que s'il est repéré (équipe connue ou forme
  de nom) ; la bulle de « Qui sera le chef de chantier ? » recommande la liste « Équipe ».

### D.12 Vérifications

- Fusion de la production (dépôt de documents par le lien, b010c59) dans cette branche : conflits résolus à la main
  (listes du transfert, de l'effacement et du journal : les deux ajouts gardés ; espace du partenaire : ses
  questions puis ses documents ; export de sa part : ses documents ET ses réponses ; empreintes SRI recalculées) ;
  migration chaînée après `y9z0depotlien` (une seule tête) ; la réponse du partenaire suit la règle du verrou de
  l'invitation d'abord (test `test_reponse_du_partenaire_espace_reinitialise_ou_lien_retire_entre_temps`).
- Suite complète SQLite (`TZ=UTC`, IA et emails simulés, aucun réseau) : 1 711 tests, tous verts, dont les 17 de
  `tests/test_redaction_v5_entretien.py` (déclenchement sans IA, ordre, phrase du dossier, question passée →
  « [À compléter] », réponses → faits « déclaré par vous » [R#], choix dans « Équipe » sans nom ni CV à l'IA, question
  posée dans l'espace du partenaire, espace réinitialisé ou lien retiré pendant sa réponse, option IA (phrase
  retrouvée mot pour mot, débit, remboursement), isolation, RGPD, démo, migration, écrans compilés sous Node).
- Empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check` de `app.js` et `redaction-partenaire.js`,
  gabarit de l'application compilé par Vue sous Node (aucune erreur).
- Navigateur réel (serveur local, IA coupée) : chef de file à 1 280 px et 375 px (aucun défilement horizontal),
  lien du partenaire (espace ouvert, réponse avec l'avertissement ; après la fusion, ses questions et « Vos
  documents pour Adjugo » l'un sous l'autre à 375 px, sans défilement horizontal), vitrine de la démo
  (8 questions, 3 réponses, 1 passée, chef de chantier choisi dans « Équipe »).
- Postgres 16 depuis l'état exact de la production, deux fois : da9ef0f (tête `x8y9redactionv4`, avant la fusion)
  puis b010c59 (tête `y9z0depotlien`, après) ; données créées par le code de production ; une seule révision
  appliquée, aucune donnée perdue, seconde montée et rejeu forcé sans effet, entretien préparé et répondu sur la
  base montée (chef de file et partenaire), code de production redémarré sur la base montée (lectures et
  écritures 200), schéma identique à une base neuve, retour arrière (table retirée, rien d'autre ne bouge) puis
  remontée : 19 contrôles sur 19 ; vrais tests rejoués sur la base montée : 1 027 verts, et exactement les 37
  échecs de la vérification de la production elle-même (b010c59 : tests propres à SQLite, PRAGMA, `sqlite3`, base
  partagée), aucun dans la rédaction.
