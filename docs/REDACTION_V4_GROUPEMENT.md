# Rédaction, vague 4 — le dossier de groupement cloisonné (socle serveur)

Contrat entre le socle (fait) et les trois chantiers suivants (écrans du partenaire, écran « Qui écrit
quoi » du chef de file, assemblage et « Prêt à déposer »). Étude : `etudes/redaction.md` § 6.8 (B),
§ 7 (doctrine), § 8 (V4), § 10 (décisions 1 à 6).

Source de vérité du code :
- règles : `app/services/atelier_groupement.py` (seul point d'écriture de la répartition, des brouillons
  des partenaires, des textes communs de leurs parties et de la validation du dossier assemblé) ;
- routes : `app/routers/atelier_groupement.py` ;
- atelier (V2/V3), adapté : `app/services/atelier.py` (`versions_communes`, `ajouter_version`, `blocage`,
  `_debiter`, `rembourser`, `section_out`, `valider`) ;
- migration : `alembic/versions/x8y9redactionv4_dossier_groupement.py` (après `w7x8analysepartagee`) ;
- tests : `tests/test_redaction_v4_groupement.py`.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit
« section »), « valider » (jamais « signer »), jamais « consortium », jamais « vérifié ». Zéro émoji.

---

## 1. Décisions retenues (à signaler à Eliot)

| Décision | Retenu | Ce que fait le socle |
|---|---|---|
| D1 | B construit en V4 | Les mesures de Mathys restent à faire ; elles diront l'usage réel. |
| D2 | Blocage, dérogation explicite journalisée | Étendu aux parts envoyées : leurs « [À compléter] », leurs faits à relire et les limites bloquent l'export du chef de file comme les siens (§ 8). |
| D3 (a) | Le partenaire lit le dossier assemblé complet, en lecture | `GET …/redaction/dossier`. Avant d'envoyer : « Ce texte sera lu par le chef de file et par les autres membres du groupement. » (exigé par l'API : `avertissement_lu`). La matière reste privée. |
| D4 (a) | Quota du chef de file, plafond par partie, facturation technique séparée | `facturer_aide_partenaire` (§ 6). Portée `inv:<id>`. Message neutre. Le chef de file n'accède jamais au résultat ni aux sources. |
| D5 | Pas de dépôt de documents par lien magique | Sans compte : « J'écris moi-même », ou aide de l'IA à partir du dossier de l'acheteur et de sa part déclarée. Avec un compte : ses preuves et son savoir-faire, avec SES droits. Emplacement prévu : `fiches_depot_par_lien` (vide). |
| D6 (a) | 1 analyse par dossier, refontes gratuites jusqu'à `ATELIER_REGEN_GRATUITES` | Les parties des partenaires y comptent ; plus un plafond par partie (`ATELIER_PARTENAIRE_AIDES_PAR_PARTIE`, défaut 3). |
| — | « Questions chantier » (D) | V5, non construites. |

Choix faits par défaut dans le socle (à valider) :
1. **Clé de l'espace privé du lien** (§ 3) : le lien d'une invitation manuelle est remis au chef de file
   pour qu'il le transmette ; le lien seul ne suffit donc pas à prouver qu'on est le partenaire. Sa matière
   privée et ses actions exigent une clé que seul son navigateur détient.
2. **Plafond par partie : 3 aides de l'IA** (première rédaction + 2 refontes), en plus du plafond du dossier.
3. **Un sous-traitant ne rédige pas** de partie et ne lit pas le dossier assemblé (il n'est pas membre du
   groupement, comme pour la convention).
4. **Retrait ou déclin d'une invitation** : ses brouillons sont effacés, ses parties reviennent au chef de
   file « à rédiger » ; le texte qu'il avait envoyé ne reste que dans l'historique de la partie (§ 10).
5. **Envoyer et valider sont deux gestes** : « envoyée » puis « validée » (après lecture du dossier
   assemblé). L'écran peut les enchaîner.

---

## 2. Le modèle « qui écrit quoi »

### 2.1 Tables

**`dossier_repartitions`** (`DossierRepartition`) — une ligne par partie d'un dossier de présentation en
groupement (`section_id` UNIQUE) :

| colonne | sens |
|---|---|
| `redacteur` | `chef_de_file` ou `partenaire` |
| `invite_id` | le partenaire qui rédige (son invitation) |
| `proposition` | le pré-remplissage SANS IA et sa raison : `{redacteur, invite_id, nom, lot, mots, message}` |
| `choix` | `propose` (pré-rempli) ou `manuel` (choisi par le chef de file) |
| `longueur_mots` | longueur conseillée (défaut : tirée de la limite de la partie) |
| `date_limite` | date limite interne |
| `demandee_le`, `relance_palier` | « Demander les parts » et relance planifiée (1 = J-2, 2 = jour J) |
| `job_id`, `aides_ia` | aide de l'IA du partenaire en cours, nombre d'aides utilisées (plafond par partie). Jamais exposés au chef de file. |
| `lock_version` | verrou optimiste |

La partie elle-même suit le rédacteur : `dossier_sections.author_kind` = `organisation` ou `invitation`,
`author_invite_id`. Toute l'atelier (V2/V3) s'appuie déjà sur ces deux colonnes.

**`dossier_parts_brouillons`** (`DossierPartBrouillon`) — les brouillons PRIVÉS d'un partenaire, en ajout
seul : `texte`, `origine` (`ia` · `utilisateur` · `raccourci` · `acceptee` · `retablie`), `ia`, `sources`
(privé), `faits` (privé, avec leur source), `compteurs`, `empreinte`, `base_id`, `base_version_id`,
`auteur_user_id` (compte du partenaire s'il en a un), `job_id`. Rangés à part : AUCUN chemin du chef de file
ne lit cette table.

**`dossier_validations`** (`DossierValidation`) — la validation du dossier assemblé par chaque membre :
`membre_cle` UNIQUE par dossier (`chef_de_file` ou `invitation:<id>`), `empreinte` validée, `statut`
(`valide` · `a_revalider`), `valide_le`, `perime_le`.

### 2.2 Colonnes ajoutées

- `dossier_section_versions.partage` (booléen), `ecrit_par` (`partenaire` · `chef_de_file`),
  `compteurs` : le **texte commun** d'une partie de partenaire. Une version commune ne porte jamais de
  matière privée : `sources` vides, `faits` réduits aux faits à relire SANS leur source (`faits_communs`),
  compteurs de sources par type.
- `jobs.user_id` devient facultatif ; `jobs.portee` (`''` ou `partenaire`), `jobs.invite_id`.
- `project_invites.espace_hash` : empreinte de la clé de l'espace privé du lien (§ 3).

### 2.3 Statut d'une partie (calculé, jamais stocké)

`statut_de(db, section)` — impossible d'être incohérent, comme `groupement_state` :

| code | libellé | partie du chef de file | partie d'un partenaire |
|---|---|---|---|
| `a_rediger` | À rédiger | aucune version | aucun texte commun, aucun brouillon |
| `en_cours` | En cours | brouillon ou relue | brouillon privé, rien d'envoyé |
| `envoyee` | Envoyée | — | texte envoyé par le partenaire, pas encore validé |
| `a_revalider` | À revalider | modifiée après validation | texte écrit ou modifié par le chef de file, ou texte changé après validation |
| `validee` | Validée | validée (empreinte) | l'auteur a validé CE texte (empreinte = `dossier_sections.validated_hash`) |

`mention(db, section, nom)` : « Rédigé par le chef de file, à valider par X » (le chef de file a écrit à la
place d'un partenaire absent) ; « Modifié par le chef de file, à revalider par X » ; puis « … validé par X ».

L'empreinte du texte validé est celle de la partie (`validated_hash`). L'empreinte du **dossier assemblé**
est `empreinte_dossier(db, dossier)` : ordre, intitulé, auteur et empreinte du texte commun de chaque partie.

### 2.4 Pré-remplissage sans IA

`activer()` crée une ligne par partie active. `proposition(section, membres)` :
- une partie dont l'intitulé parle du « groupement » → chef de file ;
- sinon, les mots du **lot** de chaque partenaire (`ProjectContribution.lot`) sont cherchés dans
  l'intitulé, le critère, la question et les titres parents de la partie (même début de mot : 5 lettres,
  ou 4 pour deux mots longs — « couverture » ↔ « couvreur », « plomberie » ↔ « plombier » ; mots
  génériques écartés) ;
- un seul partenaire correspond → il est proposé, avec la raison (« Proposé d'après le lot de X
  (« … ») : « déchets » dans la partie. ») ; aucun ou plusieurs → chef de file, avec la raison.
- Une partie qui a déjà du texte ne change jamais de mains par la proposition (seulement par un choix
  confirmé du chef de file).

---

## 3. Cloisonnement : qui voit quoi

| | Chef de file (son organisation) | Le partenaire auteur | Les autres membres |
|---|---|---|---|
| Brouillons du partenaire (texte, sources, extraits, faits avec source) | jamais | oui (lien + clé, ou compte) | jamais |
| Texte envoyé (version commune) | oui | oui | oui (dossier assemblé) |
| Compteurs de sources par type, nombre de faits à relire | oui | oui | oui |
| Brouillons du chef de file | oui | jamais | jamais |
| Texte validé du chef de file | oui | oui | oui |
| Tâche (Job) du partenaire | jamais (404, y compris `/api/jobs/{id}`) | oui | jamais |
| Forfait, quota, essai, dérogations du chef de file | oui | jamais | jamais |
| Statut « en cours » d'une partie | oui | oui | oui |

Règles fermes appliquées :
- **Un fait ne vient jamais de l'IA.** L'aide de l'IA du partenaire reçoit SES faits seulement
  (`ContextePartenaire`) : sans compte, sa part déclarée (« déclaré par vous » : lot, qualifications,
  références, capacités, présentation) ; avec le compte qui a rattaché le lien, en plus ses preuves `[F#]`,
  son profil, son équipe (noms masqués) et des extraits de SON savoir-faire `[S#]`, lus avec les comptes
  de SON organisation. Le dossier de l'acheteur est « exigé par l'acheteur » (jamais une preuve sur
  l'entreprise), seulement si son lien autorise les pièces (`can_view_docs`).
- **Aucune lecture croisée** : `rag.retrieve_multi` n'est appelé qu'avec les comptes de l'organisation du
  partenaire ; un compte qui appartient (ou appartiendrait plus tard) à l'organisation du chef de file
  n'apporte rien et n'est jamais « le partenaire » (404).
- **Le contrôle des faits (A) tourne chez le partenaire**, sur SES faits (`fs.controler` avec ses
  fiches) ; ce qui part au chef de file : les faits à relire sans leur source (`faits_communs`) et
  `compteurs` = `{par_type: {documents, declare, public, estimation, calcul, acheteur}, avec_source,
  a_relire, engagements}`.
- **Noms et CV des salariés** : `pii_scope` avec l'équipe du partenaire et les noms repérés sans IA ;
  un CV n'est jamais remis à l'IA (`refuser_cv_pour_ia`, `inserer_cv`).
- **C'est le partenaire qui lance son aide de l'IA** : le chef de file reçoit 403
  `partie_d_un_partenaire` sur `/api/atelier/{pid}/sections/{sid}/rediger` (et « Rédiger tout »).
- **Personne ne change la part d'un autre en silence** : l'écriture ordinaire de l'atelier reste refusée
  au chef de file (403) ; il passe par `PUT /repartition/{sid}/texte` (§ 5.2), qui fait passer la partie
  « à revalider par » son auteur.

### 3.1 L'espace privé du lien (clé)

Le chef de file reçoit le lien d'une invitation manuelle (pour le transmettre). Par le lien, la matière
privée (brouillons, sources, résultat des tâches, export) et les actions du partenaire (écrire, traiter un
fait, lancer l'aide, envoyer, valider, rétablir, valider le dossier) exigent l'en-tête
**`X-Adjugo-Espace: <clé>`** :
- `POST /api/invite/{token}/redaction/espace` `{}` → `{cle, entete, brouillons_effaces}` à la première
  ouverture. La clé n'est rendue qu'UNE fois : l'écran la garde dans le navigateur (localStorage) ;
- déjà ouvert → 409 `espace_deja_ouvert` (`code_possible` : un code peut être envoyé à l'adresse de
  l'invitation) ;
- `{code}` (code reçu par `POST /api/invite/{token}/otp/request`) → nouvelle clé, brouillons GARDÉS,
  adresse prouvée (comme `otp/verify`) ;
- `{reinitialiser: true}` → nouvelle clé, brouillons non envoyés EFFACÉS (celui qui réinitialise ne lit
  jamais rien), adresse de l'invitation à PROUVER DE NOUVEAU (`verified_at` remis à vide : quand le lien
  vise une adresse, envoyer ou valider exige alors le code reçu par le partenaire), inscrit au journal du
  membre (« Votre espace privé de rédaction a été réinitialisé… »).
Sans clé valide : 403 `cle_espace_requise` sur les actions ; les lectures rendent ce qui est commun
(`brouillon: null`, `brouillons: []`, `espace.cle_valide: false`). Par le compte (`/api/shared/…`) :
aucune clé, le compte suffit (voie recommandée).

---

## 4. Routes — chef de file

Authentification `Bearer`, portée organisation : un marché d'une autre organisation → 404
`marche_introuvable`. Erreurs métier : `detail = {code, message, …}` ; afficher `message` tel quel.

### `GET /api/atelier/{pid}/repartition`
```json
{"actif": true,
 "membres": [{"invite_id": 7, "nom": "Breizh Désamiantage", "lot": "...", "role": "cotraitant",
              "peut_rediger": true, "raison": "", "par_email": true}],
 "sections": [Ligne],
 "dossier": {"empreinte": "64 hex", "validations": [Validation], "pret": Pret},
 "statuts": {"a_rediger": "À rédiger", ...}, "avertissement_envoi": "...", "plafond_aide_par_partie": 3}
```
`Ligne` :
```json
{"section_id": 41, "numero_affiche": "3", "titre": "3 Démarche environnementale", "intitule": "...",
 "critere": "", "poids": "", "poids_source": "", "question": "...", "source_plan": "cadre", "limite": [],
 "partie_de_critere": false, "enregistre": true,
 "redacteur": {"type": "partenaire", "invite_id": 7, "nom": "Breizh Désamiantage"},
 "proposition": {"redacteur", "invite_id", "nom", "lot", "mots", "message"}, "choix": "propose",
 "longueur_mots": 400, "date_limite": "2026-11-02", "demandee_le": null,
 "statut": "envoyee", "statut_libelle": "Envoyée", "mention": "",
 "envoyee_le": "...", "validation": {"version_id", "empreinte", "le"} | null,
 "texte_commun": {"version_id", "numero", "ecrit_par", "empreinte", "ia", "coupe", "cree_le",
                  "a_completer", "faits_a_relire", "compteurs"} | null,
 "lock_version": 2}
```
`enregistre: false` : partie ajoutée après la préparation (proposition calculée, rien d'enregistré).
`membres[].peut_rediger: false` avec `raison`, une phrase qui se lit seule (« son lien a expiré », « il n'a
pas encore accepté l'invitation », « un sous-traitant n'est pas membre du groupement », « il n'est plus membre
du groupement »…) ; `par_email` : son lien porte une adresse (un booléen, jamais l'adresse).

### `POST /api/atelier/{pid}/repartition` `{"reproposer": false}`
Prépare « Qui écrit quoi » (idempotent) → même réponse + `preparation: {crees, reproposees}`. Un marché sans
partenaire co-traitant (aucun groupement) → 409 `pas_de_groupement`, rien n'est créé.
`reproposer` refait la proposition des lignes jamais choisies à la main et encore sans texte.

### `GET /api/atelier/{pid}/repartition/{sid}`
`Ligne` + `texte_commun` (avec `texte`) + `comparaison: {avant, apres}` (avant = dernier texte du
partenaire, après = texte courant ; textes communs seulement) quand le chef de file a modifié la partie.

### `PUT /api/atelier/{pid}/repartition/{sid}`
`{"redacteur"?: "chef_de_file"|"partenaire", "invite_id"?, "longueur_mots"?, "date_limite"?: "AAAA-MM-JJ"|null,
"confirmer"?: false, "lock_version"?}` → détail de la partie. Erreurs : 404 `partenaire_introuvable` ;
409 `partenaire_indisponible` (sous-traitant, réseau non accepté, lien expiré…), `changement_a_confirmer`
(la partie a du texte : il est mis de côté, reste dans l'historique), `redaction_en_cours`,
`repartition_modifiee`, `partie_retiree` ; 422 `redacteur_invalide`, `longueur_invalide` (30 à 20 000),
`date_invalide`.

### `PUT /api/atelier/{pid}/repartition/{sid}/texte` `{"texte", "base_version_id"}`
Le chef de file modifie la part d'un partenaire, ou l'écrit à sa place (`base_version_id: null` si rien
n'a été envoyé). Nouveau texte commun `ecrit_par: chef_de_file`, aucune IA, **« à revalider par »** le
partenaire. Aucune source du chef de file n'appuie un fait sur le partenaire : ses faits sur l'entreprise
restent à relire tant que le partenaire ne l'a pas validé sur SES faits. Erreurs : 409
`texte_modifie_entre_temps`, `pas_une_part_de_partenaire`, `partie_retiree` ; 422 `partie_vide`,
`texte_trop_long`. Le partenaire est prévenu par email (best-effort).

### `POST /api/atelier/{pid}/repartition/demander` `{"invite_ids"?: [..]}`
« Demander les parts » : un email par partenaire qui a des parties à rédiger, en cours ou à revalider
(liste, date limite interne, « texte du chef de file, à relire et valider » le cas échéant, lien). Mêmes
garde-fous que les relances de la co-traitance : adresse confirmée du chef de file, démo refusée, anti-rafale
de 15 minutes par partenaire, même plafond quotidien que les invitations et leurs renvois
(`invites._daily_invite_count` : `invite.resent` et `redaction.parts_demandees` comptent ensemble). Seul un
email PARTI horodate la demande (`demandee_le`) et s'inscrit au journal : un envoi raté se retente aussitôt.
→ `{"demandees": [{invite_id, nom, parties, email_parti}], "sans_adresse": [...], "deja_demandees": [...],
"plafond_atteint": [...]}` (noms seulement, jamais une adresse).

### `POST /api/atelier/{pid}/repartition/valider-dossier` `{"empreinte"?}`
Le chef de file valide le dossier assemblé, après avoir validé chacune de SES parties.
→ `{"validation", "pret"}`. Erreurs : 409 `parties_a_valider` `{sections}`, `dossier_modifie` `{empreinte}`.

Atelier (V2/V3) pour une partie de partenaire, côté chef de file : `auteur.libelle` = nom du partenaire,
`peut_ecrire: false`, `prive_visible: false`, `version_courante` = son texte commun (`ecrit_par`,
`compteurs`, compteurs « à compléter » et « à relire » ; jamais `sources` ni `faits`) ;
`GET …/versions/{vid}` lit une version commune ; les écritures ordinaires → 403 `partie_d_un_partenaire`.

---

## 5. Routes — partenaire

Deux chemins, mêmes sous-routes :
- **lien** : `/api/invite/{token}/redaction…` (+ en-tête `X-Adjugo-Espace` pour la matière privée et les
  actions) — lien révoqué → 404, décliné ou expiré → 410 ;
- **compte** : `/api/shared/{project_id}/redaction…` (`Bearer`, lien rattaché à CE compte, actif, non
  expiré ; sinon 404).
Communs : invitation du réseau pas encore acceptée → 403 `apercu_minimal` ; sous-traitant, dossier pas
encore préparé → 404 `dossier_commun_introuvable` ; co-construction fermée → 403
`co_construction_fermee` ; démo → 403 `demo`.

### `GET …/redaction`
```json
{"marche": {"id", "nom"}, "mode": "lien|compte",
 "espace": {"cle_valide": true, "ouvert": true, "entete": "X-Adjugo-Espace", "code_possible": false, "message": ""},
 "message_mode": "Sans compte Adjugo, l'aide d'Adjugo s'appuie sur ...", "avertissement_envoi": "...",
 "peut_ecrire": true, "statuts": {...}, "origines": {...},
 "parties": [{"section_id", "numero_affiche", "titre", "intitule", "critere", "poids", "poids_source",
              "question", "source_plan", "limite", "partie_de_critere", "longueur_mots", "date_limite",
              "statut", "statut_libelle", "mention",
              "brouillon": Brouillon | null, "texte_commun": TexteCommun | null,
              "comparaison": {"avant", "apres"} | null, "validation": {...} | null,
              "aide": {"utilisees", "plafond", "restantes", "en_cours": {job_id, action, statut} | null}}],
 "dossier": {"empreinte", "ma_validation": {statut, statut_libelle, empreinte, le, perime_le} | null,
             "peut_valider": false}}
```
`Brouillon` (privé) : `{id, numero, origine, origine_libelle, ia, coupe, empreinte, cree_le,
base_version_id, a_completer, faits_a_relire, faits, controle, compteurs, sources,
sources_depuis_le_compte, texte}` — par le lien, les sources d'un brouillon écrit depuis le compte restent
réservées au compte (`sources_depuis_le_compte: true`).

### `GET …/redaction/dossier` — le dossier assemblé, en lecture (décision 3a)
`{marche, chef_de_file, message, empreinte, parties: [{…base, redacteur: {type, nom, vous}, statut,
statut_libelle, texte | null, a_completer, (partie d'un partenaire envoyée : faits_a_relire, compteurs,
ecrit_par)}], validations, pret}`. `message` = « Le dossier assemblé est en lecture seule… ». Le texte
d'une partie du chef de file n'y est que VALIDÉ ; celui d'un partenaire, que ENVOYÉ.

### Les autres sous-routes
| route | corps | effet | erreurs |
|---|---|---|---|
| `POST /espace` (lien seul) | `{code?, reinitialiser?}` | § 3.1 | 409 `espace_deja_ouvert`, 400 `code_absent` / `code_incorrect`, 429 |
| `GET /sections/{sid}` | — | SA partie + `brouillons` (historique, sans textes) | 404 `partie_introuvable` (toute partie qui n'est pas la sienne) |
| `PUT /sections/{sid}/brouillon` | `{texte, base_brouillon_id}` | « J'écris moi-même » : nouveau brouillon, faits contrôlés sur SES faits (ce qu'il écrit est sa déclaration ; un fait déjà à relire le reste) | 409 `brouillon_modifie`, 422 `texte_trop_long`, 403 `cle_espace_requise` |
| `POST /sections/{sid}/faits/{fid}` | `{statut: relu_par_vous|a_relire}` | sur son brouillon courant | 404 `fait_introuvable`, 409 `fait_avec_source` |
| `POST /sections/{sid}/aide` | `{action: rediger|raccourcir, cible_mots?}` | 202 `{tache, section_id}` (§ 6) | 409 `aide_en_cours`, `plafond_partie`, `aide_indisponible`, `aide_occupee`, `cv_dans_la_partie` ; 422 `partie_vide`, `deja_assez_court`, `cible_invalide` |
| `GET /taches/{job_id}` | — | SA tâche : `{id, kind, status, label, result: {sections: [{section_id, ok, brouillon_id, coupe, a_completer, faits_a_relire, extraits_fournis}], echecs, message}, error}` (aucun texte) | 404 `tache_introuvable` |
| `POST /sections/{sid}/envoyer` | `{brouillon_id, avertissement_lu: true}` | le brouillon courant devient le texte commun (aucune source) ; le chef de file est prévenu | 422 `avertissement_requis` (message = l'avertissement à afficher), `partie_vide` ; 409 `brouillon_modifie`, `aide_en_cours` ; 403 `identity_unverified` |
| `POST /sections/{sid}/valider` | `{version_id}` | valide le texte commun courant (le sien, ou celui du chef de file : contrôle de SES faits d'abord, brouillon `acceptee`) | 409 `texte_modifie_entre_temps` ; 403 `identity_unverified` |
| `POST /sections/{sid}/retablir` | `{base_version_id, version_id?}` | son texte d'avant redevient le texte commun | 409 `rien_a_retablir`, `texte_modifie_entre_temps` ; 404 `version_introuvable` |
| `POST /dossier/valider` | `{empreinte?}` | valide le dossier assemblé lu (après SES parties) | 409 `parties_a_valider`, `dossier_modifie` |
| `GET /export` | — | portabilité : ses brouillons et ses textes envoyés (JSON) | 403 `cle_espace_requise` |

Identité : envoyer et valider exigent l'adresse prouvée par code quand le lien vise une adresse
(`identity_unverified`, mêmes règles que l'envoi de la part), ou le compte vérifié qui a rattaché le lien.

---

## 6. Facturation de l'aide de l'IA du partenaire (D4, D6)

`facturer_aide_partenaire(db, acces, section, job_id, estimation_eur)` — LA fonction, appelée une fois par
tâche, AVANT tout appel :
1. **compte débité** : le compte de facturation du chef de file (`_payeur` = propriétaire de son
   organisation) ;
2. **garde-fou de l'essai** : `budget_ia.verifier(payeur, "atelier", estimation)` (essai : budget de
   l'essai du chef de file ; essai terminé ou forfait inactif : refus) ;
3. **débit** : `atelier._debiter(db, payeur, dossier, [section], accepte_debit=False, …, deja_ia=_deja_ia)` —
   la 1re action de l'IA du dossier = 1 analyse ; la 1re rédaction de chaque partie y est comprise ;
   refaire est gratuit jusqu'à `ATELIER_REGEN_GRATUITES` ; une refonte payante n'est JAMAIS acceptée au nom
   du partenaire ;
4. **plafond par partie** : `plafond_partie()` (`ATELIER_PARTENAIRE_AIDES_PAR_PARTIE`, défaut 3), compté
   dans `dossier_repartitions.aides_ia` (avant la facturation ; rendu si la facturation est refusée ou si
   l'IA tombe) ;
5. **portée de facturation technique** : `tenant_partenaire(invite_id)` = `"inv:<id>"`, posée par
   `run_in_thread` et `rediger_partie` / `raccourcir_partie` : plafonds de tokens et disjoncteurs propres
   à l'invitation ; `budget_ia._compte` range le coût au compte de facturation du chef de file
   (`u<id>`), budget de l'essai compris ; `cost_meter` cumule sur le dossier (`cout_ia`, interne) ;
6. **remboursement si l'IA tombe** : `atelier.rembourser` sur le relevé (`_debit.payeur_id`) ; reprise
   au redémarrage (`app/main._recover_orphan_jobs`) : débit rendu, partie libérée, aide rendue.

Tout refus lié au chef de file (quota, essai terminé, budget de l'essai, forfait, démo, adresse non
confirmée, refonte payante) → 409 **`aide_indisponible`**, message NEUTRE : « L'aide d'Adjugo n'est pas
disponible pour cette partie en ce moment. Vous pouvez l'écrire vous-même : votre texte sera contrôlé de
la même façon. » Une première rédaction du dossier encore en cours → 409 `aide_occupee`. Rien du forfait
du chef de file n'est jamais rendu au partenaire.

La tâche : `Job(user_id=NULL, portee='partenaire', invite_id, kind='partenaire_rediger'|'partenaire_raccourcir')`.
Aucune requête `user_id IN (…)` ne la renvoie ; `/api/jobs/{id}` et `/api/atelier/{pid}/taches/{id}`
filtrent aussi la portée. Son résultat ne contient aucun texte (le texte est dans le brouillon privé). Si
l'invitation est retirée pendant la rédaction, le texte n'est pas gardé (le débit reste : l'IA a servi).

Prompt : identique à celui de l'atelier (`rediger_partie`), plus la ligne « CETTE PARTIE EST RÉDIGÉE PAR
X, MEMBRE DU GROUPEMENT (lot : …) : « nous » désigne cette entreprise seulement… ». Le dossier de l'acheteur
commun reste en tête (cache de prompt d'une heure partagé avec les rédactions du chef de file : moins
cher, sans rien retirer).

---

## 7. Empreintes, validation, péremption, journal

- Une partie de partenaire validée puis modifiée (par le chef de file ou par lui) → `a_revalider`.
- Le dossier assemblé validé par un membre puis modifié (texte commun envoyé, modifié, rétabli, partie du
  chef de file validée, rédacteur changé, partenaire retiré) → sa validation passe `a_revalider` :
  **même mécanisme que la convention périmée** — explicite à chaque changement
  (`apres_changement_commun` → `perimer_validations`, entrée `redaction.dossier_a_revalider`) et filet par
  recalcul de l'empreinte à chaque lecture (`rafraichir_validations`).
- `pret(db, project, dossier)` : `{sections_validees, sections_total, message: "Sections validées 4 sur 5",
  membres: [{membre, invite_id, nom, statut: valide|a_revalider|a_faire}], complet}` (membres attendus :
  le chef de file et les partenaires qui peuvent rédiger).

Journal chaîné (`audit.record`, owner = tenant du chef de file ; `invite_id` = partenaire concerné) :

| action | qui | journal du membre |
|---|---|---|
| `redaction.repartition` | chef de file | consignes de sa partie modifiées |
| `redaction.partie_confiee` / `redaction.partie_reprise` | chef de file | partie confiée / confiée à un autre |
| `redaction.parts_demandees` | chef de file | partie demandée |
| `redaction.part_envoyee` | partenaire | événement de groupement (tous les membres) |
| `redaction.part_modifiee` / `redaction.part_redigee_par_chef` | chef de file | à revalider / à valider |
| `redaction.part_validee`, `redaction.part_retablie` | partenaire | ses actions |
| `redaction.dossier_valide`, `redaction.dossier_a_revalider` | membre | événements de groupement |
| `redaction.parts_reprises` | chef de file ou partenaire (déclin) | parties reprises |
| `redaction.espace_ouvert` / `_rouvert` / `_reinitialise` | lien | ses actions (alerte en cas de réinitialisation) |

`atelier.partie_validee` (V2) reste l'entrée de la validation d'une partie du chef de file. Les nouvelles
actions de groupement entrent dans `journal_membre.GROUP_EVENTS` (actions neuves, sans entrée ancienne :
la version « adjugo-journal-membre-v1 » ne change pas).

---

## 8. Export, dossier commun (D2 étendu)

`versions_communes` rend désormais, pour la partie d'un autre auteur, son texte COMMUN (`partage`) sinon
son texte validé. Conséquences, sans autre changement :
- `blocage` : une partie envoyée apporte ses « [À compléter] », ses faits à relire (sans leur source) et
  ses limites ; une partie sans texte envoyé → `attente_partenaire` ; une partie envoyée non validée →
  avertissement `non_valide` ;
- dérogation explicite (inchangée) : inscrite au journal, valable pour CET état ;
- dossier commun (ZIP) : texte VALIDÉ de préférence (une modification du chef de file en attente de
  revalidation n'y entre pas : « a été modifiée depuis la validation ») ; une partie envoyée jamais validée
  → « BLOQUANT — … non validé » ;
- mention « Préparé avec assistance IA » : due si l'IA a servi au texte envoyé (`ia`).

---

## 9. Fonctions du service (pour les chantiers suivants)

| fonction | usage |
|---|---|
| `membres(db, project)`, `peut_rediger(db, inv)` | qui peut rédiger, avec la raison |
| `proposition(section, membres)` | pré-remplissage sans IA |
| `activer(db, project, dossier, lecteur, reproposer)` | préparer « Qui écrit quoi » |
| `repartir(…)`, `modifier_part(…)`, `comparer(db, section)`, `demander_parts(…)`, `relancer_parts(db, today)` | chef de file |
| `vue_chef`, `detail_chef`, `dossier_assemble`, `vue_partenaire`, `detail_partenaire` | lectures (aucune matière privée hors de chez son auteur) |
| `acces_partenaire(db, inv, project, user, mode, cle)`, `ouvrir_espace`, `cle_valide` | accès du partenaire |
| `enregistrer_brouillon`, `traiter_fait`, `lancer_aide`, `tache`, `envoyer`, `valider_part`, `retablir` | partenaire |
| `facturer_aide_partenaire`, `tenant_partenaire` | facturation (§ 6) |
| `statut_de`, `mention`, `textes_communs`, `empreinte_dossier`, `faits_communs`, `compteurs` | lecture pure |
| `valider_dossier`, `perimer_validations`, `apres_changement_commun`, `rafraichir_validations`, `pret` | validation |
| `retirer_invitation`, `effacer_dossiers`, `effacer_compte`, `exporter_chef`, `exporter_partenaire`, `exporter_invitation`, `purger` | RGPD |
| `fiches_depot_par_lien(db, inv)` | EMPLACEMENT de l'option (a) de D5 (aujourd'hui : rien) |

À respecter par les chantiers :
1. Ne jamais lire `dossier_parts_brouillons` hors de `atelier_groupement` ni l'exposer hors de l'accès du
   partenaire auteur.
2. Toute écriture d'un texte commun passe par ce module (jamais `atelier.ajouter_version(partage=True)`
   ailleurs), et appelle `apres_changement_commun`.
3. L'assemblage (chantier 3) : l'ordre suit le cadre de l'acheteur (`sections_actives`) ; « Organisation
   du groupement » vient de la convention ; « Qui fait quoi » montre lots, qualifications (libellé, justifiée
   ou déclarée) et moyens, validée par chaque membre (`valider_dossier`) et **ne liste JAMAIS les manques du
   chef de file** ; « Harmoniser le ton » ne retouche que les transitions et refuse tout fait absent avant.
   Ces sections ne sont pas construites ici.
4. Un seul process serveur : aucune connexion permanente, aucun temps réel, aucune suggestion façon
   traitement de texte (la revalidation par l'auteur suffit).
5. Retirer du plan une partie confiée à un partenaire : la reprendre d'abord (`PUT /repartition/{sid}`
   `{"redacteur": "chef_de_file", "confirmer": true}`) ; la reconstruction du plan ne retire jamais la
   partie d'un partenaire.
6. Les textes des partenaires sont affichés comme du texte (échappés), jamais interprétés comme du HTML ;
   les renvois `[F3]`, `[S2]`… d'une part envoyée renvoient à SES sources : à montrer comme « source du
   partenaire » (sans lien), retirés à l'export comme les autres.
7. La clé de l'espace (lien) se garde dans le navigateur du partenaire et part dans l'en-tête
   `X-Adjugo-Espace` de chaque appel ; elle n'apparaît jamais dans une URL ni dans un journal.

---

## 10. RGPD

| événement | brouillons privés du partenaire | texte envoyé | répartition, validations, tâches |
|---|---|---|---|
| Effacement du compte du **chef de file** (ou corbeille purgée) | effacés (le marché part) | effacé | effacées (`effacer_dossiers`, tâches des partenaires comprises) |
| Effacement du compte d'un **partenaire** | ceux écrits depuis ce compte effacés (`effacer_compte`) ; ceux écrits par le lien restent à l'invitation | reste : part commune reçue par le groupement | inchangées ; le lien est libéré (`_release_claims`) |
| **Retrait** ou **déclin** de l'invitation | effacés aussitôt (`retirer_invitation`) | ne reste que dans l'historique de la partie (plus courant, plus validé) | parties au chef de file « à rédiger », validation du membre et tâches terminées effacées, journal `redaction.parts_reprises` |
| Lien **expiré** | accès coupé (410) ; effacés par la purge après 30 jours | reste | — |
| Réinitialisation de l'espace | effacés | reste | — |
| Export RGPD du chef de file | jamais | dans `dossiers_de_presentation` | `dossiers_de_groupement` (répartition, validations) |
| Export RGPD d'un partenaire (compte) | `parts_redigees_pour_des_groupements` (liens rattachés) | idem | — |
| Portabilité par le lien | `GET …/redaction/export` (clé requise) | idem | — |

Transfert de propriété de l'organisation, effacement d'un membre, réaffectation d'un dossier : les trois
tables suivent `owner_id` comme l'atelier. Purge quotidienne : `POST /api/admin/run-trash-purge`
(`brouillons_partenaires_effaces`, `taches_partenaires_effacees`).

---

## 11. Relances

`POST /api/admin/run-cotraitance-reminders` appelle aussi `relancer_parts` : un email par partenaire dont
une partie n'est pas encore envoyée, à J-2 puis le jour de sa date limite interne (un palier par partie,
jamais deux fois ; rien après dépôt ou clôture ; rien pour la démo). Changer la date limite remet le palier
à zéro.

---

## 12. Migration `x8y9redactionv4`

Idempotente (table créée si elle manque, colonne et index ajoutés s'ils manquent), SQLite et Postgres.
Testée :
- SQLite (`test_migration_v4_sqlite_neuve_precedente_rejeu_retour_arriere`) : base neuve, retour arrière
  (tables et colonnes retirées, `jobs.user_id` de nouveau obligatoire, tâches sans compte supprimées),
  remontée au même schéma, rejeu ;
- Postgres 16 depuis l'état EXACT de la production (`d6504e4`, `w7x8analysepartagee`), script
  `scratchpad/pgtest/run_v4_depuis_prod.py` : une seule révision appliquée, aucune donnée perdue, valeurs
  par défaut côté base, unicités, seconde montée vide, rejeu forcé, **code de production redémarré sur la
  base montée** (une tâche de partenaire en cours ne le casse pas), schéma identique à une base neuve (hors
  écart déjà admis des tables de l'atelier), retour arrière puis remontée ; puis les vrais tests rejoués sur
  cette base.

Déploiement sans casse : le code de production ne lit ni n'écrit les nouvelles tables et colonnes ; il crée
toujours ses tâches avec un compte. Retour arrière du CODE après la mise en ligne : une tâche de partenaire
en cours au redémarrage est close par l'ancien code mais son débit n'est pas rendu (il ne connaît pas
`payeur_id`) — cas rare, à rembourser à la main.

---

## 13. Limites connues (dites honnêtement)

- Le chef de file qui détient le lien peut RÉINITIALISER l'espace du partenaire : il efface alors ses
  brouillons non envoyés sans jamais les lire ; quand le lien vise une adresse, il ne peut ensuite ni
  envoyer ni valider à sa place (le code va au partenaire) ; quand le lien ne vise AUCUNE adresse (lien
  transmis à la main), rien ne distingue le chef de file du partenaire pour écrire et envoyer : c'est
  inscrit au journal du membre (« espace réinitialisé »), et l'écran doit recommander le compte
  (« Partagé avec moi ») ou une invitation avec adresse.
- La clé de l'espace est gardée par le navigateur : un autre appareil la récupère par le code reçu par
  email (si le lien vise une adresse), sinon par réinitialisation.
- Le contrôle des faits dit où un fait est écrit, pas qu'il est vrai ; une phrase générale passe.
- Pré-remplissage : simple rapprochement de mots du lot et de la partie ; le chef de file reste maître.

## 14. Tests

`tests/test_redaction_v4_groupement.py` (23 tests) : pré-remplissage sans IA ; répartition et garde-fous ;
portée du partenaire ; **le lien seul ne lit jamais la matière privée** ; identité pour envoyer et valider ;
texte envoyé + compteurs, **jamais une source ni un extrait** dans tout ce que lit le chef de file ; IA du
partenaire sur SES faits seulement ; **404 sur `/api/jobs/{id}` pour le chef de file et un membre de son
organisation** ; facturation (quota du chef de file, portée `inv:<id>`, plafond, panne remboursée) ;
raccourcir et reprise au redémarrage ; message neutre (essai terminé) ; modification par le chef de file,
revalidation, rétablissement ; partenaire absent ; validation du dossier assemblé et péremption ;
**isolation entre deux groupements** ; **invitation retirée, déclinée, expirée** ; export bloqué par la part
envoyée ; RGPD (exports, effacement des comptes) ; purge ; demande des parts et relance ; démo ; migration.

---

## 15. Écran « Qui écrit quoi » du chef de file (chantier 2 — fait)

Étude § 6.8, parcours 1 et 3. Fichiers : `app/static/app.html` (bloc « QUI ÉCRIT QUOI » de l'atelier),
`app/static/app.js` (méthodes `atlRep…`, fonctions pures `atlRepCompteurs`, `atlRepADemander`,
`atlRepDemandeTexte`, `atlRepValidationsTexte`, `atlRefsPartHtml`), `app/static/styles.css` (`.atl-rep…`) ;
tests : `tests/test_redaction_v4_chef_de_file.py`.

- **Seulement en groupement.** `GET /api/atelier/{pid}` porte `groupement: {onglet, actif, membres}`
  (`ag.indicateur` : au moins un partenaire co-traitant actif, ou une répartition déjà préparée). Sans
  groupement : tout à faux, aucun onglet, l'atelier est exactement celui d'une seule entreprise.
- **Deux onglets** sous l'en-tête de l'atelier : « Rédaction » (l'atelier V2/V3, inchangé) et « Qui écrit
  quoi ». Le menu de l'application n'est pas réorganisé.
- **Répartir** : par partie, « Rédigée par » (pré-rempli sans IA ; la raison de la proposition dans une bulle
  (i)), son critère et son poids, « Mots conseillés », « Date limite interne » (verrou optimiste
  `lock_version` ; une partie écrite ne change de mains qu'après confirmation, `changement_a_confirmer`).
- **Demander les parts** : confirmation (qui reçoit, combien de parties), puis le résultat en phrases
  (envoyée à, sans adresse, déjà demandée, limite du jour atteinte).
- **Recevoir** : statut de chaque part, « Envoyée le … », et les COMPTEURS : « 5 faits avec une source : 3
  déclarés, 2 trouvés dans ses documents · 1 fait à relire · 1 passage « [À compléter] » ». Jamais une
  source, un extrait ni un nom de document (l'écran ne lit aucun de ces champs).
- **Lire, modifier, écrire à sa place** : texte commun rendu par le moteur sûr de l'atelier
  (`atlMdToHtml(texte, [], {refsPartenaire: true})` : renvois montrés « source du partenaire », sans lien) ;
  « Modifier ce texte » → `PUT …/texte` → « à revalider par X », avant et après côte à côte ; « Rédiger à sa
  place » (rien d'envoyé) → « Rédigé par le chef de file, à valider par X ». Sur téléphone : lire et répartir ;
  écrire depuis un ordinateur.
- **Aucune IA pour la part d'un partenaire** : aucun bouton dans cet écran ; le serveur refuse (403
  `partie_d_un_partenaire`, 404 par « Partagé avec moi », 403 `cle_espace_requise` par le lien sans clé).
- **Dans l'atelier** (onglet « Rédaction »), une partie de partenaire porte `part: {statut, statut_libelle,
  mention}` (`atelier.section_out` → `ag.statut_de`, `ag.mention`) : le plan et la pastille disent « Envoyée »,
  « À revalider »… au lieu du statut de l'atelier ; « Rédigée par X » dans le plan ; ses compteurs à droite ;
  lien « Le modifier ou l'écrire à sa place ».
- **Démo** : chaque route d'écriture du chef de file appelle `refuser_demo` (en plus du garde central) ; le
  lien partenaire de la vitrine est refusé dans la route (`_par_lien(…, ecriture=True)` → 403 `{code: demo}`),
  même sans dossier commun ; « Partagé avec moi » : `refuser_demo`. Toutes les routes de la vague 4 sont
  classées dans `tests/test_demo_sans_cout.py` (`COUTS` : aide de l'IA, demander, texte du chef de file,
  envoyer ; `SANS_COUT` : le reste).

Pas dans ce chantier : la validation du dossier assemblé et « Prêt à déposer » (chantier 3 ; l'écran montre
seulement « Sections validées k sur n » et qui a validé le dossier), l'harmonisation du ton, les écrans du
partenaire (chantier 1).
