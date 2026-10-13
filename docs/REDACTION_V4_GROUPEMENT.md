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
- tests : `tests/test_redaction_v4_groupement.py` ;
- assemblage et validation (chantier 3, § 15) : `app/services/atelier_assemblage.py`,
  `tests/test_redaction_v4_assemblage.py`.

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
              "peut_rediger": true, "raison": ""}],
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
`membres[].peut_rediger: false` avec `raison` (« son lien a expiré », « n'a pas encore accepté
l'invitation », « un sous-traitant n'est pas membre du groupement »…).

### `POST /api/atelier/{pid}/repartition` `{"reproposer": false}`
Prépare « Qui écrit quoi » (idempotent) → même réponse + `preparation: {crees, reproposees}`.
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
(liste, date limite interne, lien). Exige l'adresse confirmée du chef de file ; démo refusée.
→ `{"demandees": [{invite_id, nom, parties, email_parti}], "sans_adresse": [...], "deja_demandees": [...]}`
(anti-rafale : 15 minutes par partenaire).

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
   Construites par le chantier 3 : voir § 15 (`app/services/atelier_assemblage.py`).
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

## 15. Assemblage et validation (chantier 3)

Étude § 6.8 B, parcours points 4 et 5. Code : `app/services/atelier_assemblage.py` (`asm`), DERRIÈRE
`atelier_groupement` (appelé par lui, et par deux crochets de l'atelier : la validation d'une partie tirée du
groupement, et leur rafraîchissement avant toute lecture du texte commun). Tests :
`tests/test_redaction_v4_assemblage.py`. **Aucune migration** : tout tient dans les tables du socle.

### 15.1 Choix faits par défaut (à valider par Eliot)

1. **Deux parties TIRÉES DU GROUPEMENT**, de vraies parties du dossier (`dossier_sections.author_kind =
   'groupement'`, `source_plan = 'grp_orga' | 'grp_qfq'`), écrites par Adjugo SANS IA, jamais à la main :
   « Organisation du groupement » et « Qui fait quoi dans le groupement ». Créées à la préparation de « Qui
   écrit quoi » (`POST /repartition`, idempotent), placées en tête du dossier, ou juste après la partie du plan
   dont l'intitulé parle du groupement (« Présentation du groupement » du plan simple) ; l'ordre et les numéros
   du cadre de l'acheteur ne bougent pas (dans un cadre imposé, elles n'ont pas de numéro, comme une partie
   ajoutée). Le chef de file peut les retirer et les remettre (elles reprennent leur place) ; une partie retirée
   n'est jamais recréée. Leur texte suit les faits à CHAQUE lecture (convention régénérée ou périmée, part d'un
   membre modifiée) : nouvelle version (l'historique reste entier), « à revalider » si elle était validée,
   validations du dossier assemblé périmées (`apres_changement_commun`), journal `redaction.partie_groupement_a_jour`.
2. **« Organisation du groupement »** : tirée de la convention EN VIGUEUR (générée — `a_signer` ou `signee` — et à
   jour : `groupement_convention.refresh`) : forme (conjoint, solidaire, mandataire solidaire), chef de file et
   les pouvoirs que les membres lui donnent, répartition des parts (« X, co-traitant : lot »). **Jamais un prix**
   (le dossier de présentation n'est pas l'offre de prix). Pas de convention, convention en brouillon ou
   périmée : le texte le DIT (« [À compléter : la convention de groupement n'est pas encore préparée…] »), ce qui
   bloque l'export (décision 2b) ; rien n'est inventé. Validée par le CHEF DE FILE seul, une fois la convention
   validée par tous les membres (sinon 409 `convention_a_valider`, qui nomme les accords en attente).
3. **« Qui fait quoi dans le groupement »** : ce que chaque membre APPORTE — sa part, ses qualifications, ses
   moyens — et JAMAIS ce qui lui manque (aucune ligne « aucune qualification », aucun écart de « Répondre à
   plusieurs ? ») :
   - chef de file : sa part = `lot_mandataire` de la convention (brouillon compris) ; qualifications de « Mes
     preuves » (acceptées, valables : **justifiée** si trouvée dans ses documents ou une source publique,
     **déclarée** sinon) puis de son profil (déclarées, non périmées) ; moyens : effectif du profil, matériel de
     « Mes preuves » ;
   - partenaire (co-traitant actif ; jamais un sous-traitant ni une invitation du réseau sans réponse) : sa part
     ENVOYÉE seulement (jamais un brouillon : sinon « [À compléter : la part de X n'est pas encore envoyée…] ») ;
     qualifications déclarées dans sa part, **justifiée** quand il a joint un justificatif de type qualification,
     valable, dont le nom porte tous les mots distinctifs (« Qualibat 1552 » ↔ « Qualibat_1552_2026.pdf »),
     **déclarée** sinon ; moyens : effectif déclaré ;
   - partenaire hors ligne de la convention : sa part seulement.
   Les libellés « justifiée » / « déclarée » sont rendus À L'ÉCRAN (`membres[].qualifications[].statut_libelle`),
   jamais écrits dans le texte (le fichier de l'acheteur). La justification du groupement au sens de la décision
   09-D-18 (« pourquoi répondre à plusieurs » : scores et écarts comblés de la composition retenue) est une
   **note interne** (`note_interne`) rendue au chef de file SEUL : jamais exportée, jamais montrée aux
   partenaires. Validée par CHAQUE membre attendu (les mêmes que pour le dossier assemblé : le chef de file et
   les partenaires qui peuvent rédiger) : `dossier_validations` avec `membre_cle = 'qfq:chef_de_file' |
   'qfq:invitation:<id>'` ; la partie est VALIDÉE quand tous ont validé son texte courant (empreinte). Ces lignes
   ne comptent jamais comme validation du dossier assemblé (`validations_out`, `pret`, `perimer_validations` les
   écartent).
4. **Valider le dossier assemblé** exige d'avoir validé « Qui fait quoi » (et, pour le chef de file,
   « Organisation du groupement ») : 409 `parties_a_valider` les liste.
5. **« Harmoniser le ton »** (option, IA) : jonctions entre deux parties qui se suivent, écrites par des membres
   DIFFÉRENTS (parties tirées du groupement mises à part) ; l'IA propose UNE phrase de transition par partie, placée
   au début de la partie, en paragraphe séparé ; le corps du membre n'est jamais réécrit ; une transition d'une
   harmonisation précédente est remplacée, jamais empilée (`dossiers_presentation.plan_meta.transitions`). Chaque
   phrase est contrôlée SANS IA (`asm.controle_transition`) : refusée si elle n'est pas une transition (plusieurs
   phrases, plus de 40 mots, titre, liste, renvoi, « [À compléter] ») ou si elle apporte UN fait absent du dossier
   avant l'harmonisation — nombre (chiffres, lettres, pourcentage, montant, durée, année), date ou période,
   quantité (« une centaine », « la moitié »), certification ou qualification, nom propre (au fil de la phrase, ou
   en tête quand ce n'est pas un mot d'ouverture connu du dossier), matériel, engagement (repérage du contrôle A :
   `faits_a_relire`, `faits_sources.engagement`). Une partie touchée repasse « à revalider » par son auteur (partie
   d'un partenaire : texte commun « écrit par le chef de file », avant / après, valider ou rétablir ; partie du chef
   de file : nouvelle version, origine `harmonise`, ses sources et faits gardés) ; un fait de la phrase absent de
   CETTE partie y est à relire. Débit : une refonte du dossier (décision 6a ; la 1re action de l'IA du dossier
   compte pour 1 analyse), RENDUE si l'IA tombe ou si aucune phrase n'est retenue. Tâche `atelier_harmoniser`
   (même relevé, même remboursement, même reprise au redémarrage que l'atelier). Routage : tâche IA « raccourcir »
   (même modèle, aucune route nouvelle). Ce qui part à l'IA : intitulés, fin de la partie précédente et début de la
   partie (700 caractères), auteurs anonymisés (« membre A »), noms des salariés masqués (`pii_scope`), aucun CV
   (passage non transmis), espace facturé du chef de file.

### 15.2 Routes (nouvelles ou étendues)

| route | effet |
|---|---|
| `GET /api/atelier/{pid}/repartition/dossier` | Le dossier assemblé du chef de file (ordre du cadre, parties tirées du groupement), `pret` (avec `manques`), `note_interne`, `harmoniser: {message, jonctions}`. 404 `groupement_non_prepare`. |
| `POST /api/atelier/{pid}/repartition/harmoniser` `{accepte_debit?}` | 202 `{tache, quota}` ; suivre `GET /api/atelier/{pid}/taches/{job_id}` : `result = {transitions: [{section_id, ok, texte, raison?, faits?: [{fait, type}], version_id?}], ajoutees, refusees, message}`. 409 `groupement_non_prepare`, `harmonisation_en_cours`, `debit_a_confirmer`, `premiere_redaction_en_cours`, `redaction_en_cours` ; 422 `rien_a_harmoniser` ; 402 essai ; 403 démo, `email_non_confirme`. |
| `POST /api/atelier/{pid}/sections/{sid}/valider` `{version_id}` | Partie tirée du groupement : validation du chef de file (« Qui fait quoi » : SA validation). 409 `convention_a_valider`, `partie_incomplete`, `texte_modifie_entre_temps`. |
| `GET /api/atelier/{pid}/repartition/{sid}` | Partie tirée du groupement : la ligne + `texte_commun` (avec texte), `message`, `convention` ou `membres` (qualifications avec `statut_libelle`), `validations`, `ma_validation`, `note_interne` (« Qui fait quoi »). |
| `GET …/redaction` (partenaire) | + `qui_fait_quoi` (bloc ci-dessous) ; `dossier.peut_valider` tient compte de SA validation de « Qui fait quoi ». |
| `GET …/redaction/sections/{qfq}` · `POST …/redaction/sections/{qfq}/valider` `{version_id}` | Le bloc « Qui fait quoi » et sa validation par le partenaire (mêmes exigences d'identité qu'envoyer). 403 `membre_non_attendu`, 409 `partie_incomplete`, `texte_modifie_entre_temps`. |
| écritures ordinaires d'une partie tirée du groupement | 403 `partie_du_groupement` (texte, rédiger, raccourcir, faits, restaurer, relu, contrôle, source) ; 409 `intitule_impose` (intitulé) ; 409 `partie_du_groupement` sur `PUT /repartition/{sid}` et `/texte`. |

Bloc d'une partie tirée du groupement (`asm.detail`) : `{section_id, genere: grp_orga|grp_qfq, intitule, statut
(a_valider · a_revalider · validee), statut_libelle, texte_commun: {version_id, numero, empreinte, cree_le,
a_completer, texte}, message, …}` — Organisation : `convention: {statut, libelle, version, toutes_validees,
en_vigueur, accords_en_attente}`, `membres: [{nom, role, lot}]`, `validation` ; Qui fait quoi : `membres: [{nom,
role, lot, qualifications: [{libelle, justifiee, statut_libelle}], effectif, materiel, part_envoyee}]`,
`validations: [{membre, invite_id, nom, statut valide|a_revalider|a_faire, statut_libelle, le}]`, `ma_validation`.

Ligne de « Qui écrit quoi » : `enregistre: false`, `redacteur: {type: "groupement", nom}`, `choix: "genere"`,
`genere`, `message`, `validations` (« Qui fait quoi »). Dossier assemblé : `genere`, `redacteur.type =
"groupement"`, `validations` + `membres` (« Qui fait quoi ») ou `convention` (Organisation). Atelier
(`section_out`) : `genere`, `auteur.type = "groupement"`, `peut_ecrire: false` ; le statut `STATUTS["a_valider"] =
"À valider"`.

`pret` gagne `manques: [{section_id | null, titre, statut, statut_libelle, qui: [noms], message}]` : « « 3. Démarche
environnementale » : à valider par Breizh Désamiantage », « « Qui fait quoi dans le groupement » : à valider par le
chef de file et Breizh Désamiantage », « Dossier assemblé : à revalider par le chef de file ». Jamais ce qui manque
au chef de file comme entreprise : seulement les gestes de rédaction et de validation.

### 15.3 Journal chaîné

| action | qui | journal du membre |
|---|---|---|
| `redaction.partie_groupement_validee` | membre | événement de groupement (« … a validé « Qui fait quoi » ») |
| `redaction.partie_groupement_a_jour` | Adjugo (system) | événement de groupement (« … a suivi la convention ou la part d'un membre : à revalider ») |
| `redaction.harmonisation` | chef de file | événement de groupement |
| `redaction.transition_ajoutee` | chef de file | le partenaire concerné (« … phrase de transition au début de votre partie : à revalider ») |

### 15.4 Export (D2 étendu)

L'export Word / PDF de l'atelier rend le dossier assemblé COMPLET, dans l'ordre du plan, parties tirées du groupement
comprises (rafraîchies juste avant) ; renvois `[F#]` / `[S#]` retirés ; aucun libellé interne (justifiée, déclarée,
mention de rédaction, note interne), aucun prix dans les parties tirées du groupement. Blocage avec dérogation
journalisée : les « [À compléter] » d'une partie tirée du groupement (convention absente ou périmée, part pas
envoyée, part du chef de file inconnue) bloquent comme ceux d'une part de partenaire (socle) ; non validée :
avertissement `non_valide`.

### 15.5 Démo

`POST /repartition/harmoniser` : garde central (`demo_guard`) + `refuser_demo` dans la route. Par le lien du
partenaire de la démo, toute écriture `…/redaction…` est refusée dans la route AVANT tout (« lecture guidée »).
`tests/test_demo_sans_cout.py` classe toutes les routes de la vague 4 (COUTS : harmoniser, aide du partenaire, demander
les parts, modifier la part d'un partenaire, envoyer ; SANS_COUT : les autres).

### 15.6 Limites connues

- « Justifiée » pour la qualification d'un partenaire repose sur le NOM du justificatif joint (rapprochement de mots,
  prudent) : on dit qu'un justificatif existe, jamais qu'il est bon.
- Une part modifiée après son envoi repasse en brouillon (co-traitance v2) : elle disparaît de « Qui fait quoi »
  (« à compléter ») jusqu'à son renvoi — on n'expose jamais un brouillon.
- Le contrôle des transitions refuse tout fait nouveau, pas une phrase creuse ; un mot d'ouverture inconnu du dossier
  en tête de phrase est pris pour un nom (refus prudent).
- Écrans : l'atelier montre une bulle (i) et « Valider » pour une partie tirée du groupement ; les écrans complets
  (« Prêt à déposer », « Harmoniser le ton », « Qui fait quoi » côté partenaire) sont ceux des chantiers écrans, sur
  ce contrat.
