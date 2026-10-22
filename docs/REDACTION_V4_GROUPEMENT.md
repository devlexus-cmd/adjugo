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
- assemblage et validation (chantier 3, § 17) : `app/services/atelier_assemblage.py`,
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
| D5 | **Option (a), validée par Eliot (19/10) : dépôt de documents PRIVÉS par lien magique** (§ 21) | Sans compte : « J'écris moi-même », ou aide de l'IA à partir du dossier de l'acheteur, de sa part déclarée et des documents qu'il dépose dans « Vos documents pour Adjugo » (rattachés à SON invitation, jamais vus du chef de file). Avec un compte : ses preuves et son savoir-faire, avec SES droits (inchangé). `fiches_depot_par_lien` est rempli (§ 21.6). |
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
| Documents déposés par son lien (§ 21) : fichiers, noms, passages | jamais (403 par le lien sans clé, 404 par un compte) | oui (lien + clé ; par le compte qui a rattaché le lien : télécharger, supprimer) | jamais (404) |
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
  références, capacités, présentation) et des passages des documents PRIVÉS qu'il a déposés par son lien `[S#]`
  (« trouvé dans vos documents », § 21) ; avec le compte qui a rattaché le lien, en plus ses preuves `[F#]`,
  son profil, son équipe (noms masqués) et des extraits de SON savoir-faire `[S#]`, lus avec les comptes
  de SON organisation. Le dossier de l'acheteur est « exigé par l'acheteur » (jamais une preuve sur
  l'entreprise), seulement si son lien autorise les pièces (`can_view_docs`).
- **Aucune lecture croisée** : `rag.retrieve_multi` n'est appelé qu'avec les comptes de l'organisation du
  partenaire ; un compte qui appartient (ou appartiendrait plus tard) à l'organisation du chef de file
  n'apporte rien et n'est jamais « le partenaire » (404). Par le lien, ses documents déposés sont cherchés par
  `depot_lien.rechercher` dans SES passages seulement (jamais `retrieve_multi`).
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
- lien rattaché à un compte Adjugo (`accepted_by_user_id`) : AUCUN espace par le lien — `POST /espace` → 403
  `espace_par_le_compte` (réinitialisation comprise), une clé prise avant le rattachement ne vaut plus, et aucun
  brouillon écrit depuis le compte ne se lit ni ne s'utilise par le lien (texte, sources, export, envoi). Le compte
  suffit (« Partagé avec moi ») ; la vue rend `espace.par_le_compte: true` (§ 19) ;
- `POST /api/invite/{token}/redaction/espace` `{}` → `{cle, entete, brouillons_effaces}` à la première
  ouverture ; quand le lien vise une adresse (`code_possible`), la première ouverture exige déjà le code reçu à
  cette adresse (`{code}`, sinon 409 `code_requis`) : celui qui détient seulement le lien n'ouvre rien. La clé
  n'est rendue qu'UNE fois : l'écran la garde dans le navigateur (localStorage) ;
- déjà ouvert → 409 `espace_deja_ouvert` (`code_possible` : un code peut être envoyé à l'adresse de
  l'invitation) ;
- lien sans adresse dont l'espace est déjà ouvert : le RATTACHER à un compte (`POST /api/invite/{token}/claim`) exige
  la clé de cet espace (en-tête `X-Adjugo-Espace`, envoyé par la page du lien et par l'application depuis le
  navigateur qui la garde), sinon 409 `espace_a_prouver` (« ouvrez-le dans le navigateur où vous rédigez votre
  partie… ») : un second compte ouvert par le chef de file ne prend ni les brouillons ni l'espace du partenaire
  (§ 20). Un lien qui vise une adresse se rattache, comme avant, par le compte de cette adresse, prouvée ;
- `{code}` (code reçu par `POST /api/invite/{token}/otp/request`) → nouvelle clé, brouillons GARDÉS,
  adresse prouvée (comme `otp/verify`) ;
- `{reinitialiser: true}` → nouvelle clé, brouillons non envoyés EFFACÉS (celui qui réinitialise ne lit
  jamais rien), adresse de l'invitation à PROUVER DE NOUVEAU (`verified_at` remis à vide : quand le lien
  vise une adresse, envoyer ou valider exige alors le code reçu par le partenaire), inscrit au journal du
  membre (« Votre espace privé de rédaction a été réinitialisé… »).
Relire un fait (« relu par vous ») d'un brouillon qui EST le texte commun vaut pour ce texte (lu par le chef de
file, il bloque l'export) : même exigence d'identité qu'un envoi (403 `identity_unverified` quand le lien vise une
adresse pas encore prouvée), inscrit au journal chaîné (`redaction.fait_relu`, `redaction.fait_a_relire`) ; la
relecture d'un brouillon privé reste privée (ni identité, ni journal).
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
"plafond_atteint": [...], "indisponibles": [{invite_id, nom, raison}]}` (noms seulement, jamais une adresse).
Un partenaire qui ne peut plus rédiger (`peut_rediger` : lien expiré, invitation du réseau sans réponse,
co-construction fermée, plus membre) n'est pas sollicité : il est rendu dans `indisponibles` avec sa raison (contrôle
des bugs du 22/10/2026 ; avant, il était sauté sans trace). Dossier « sans IA » (vague 5, C2.8) : l'email dit
« Écrivez-la vous-même, depuis votre lien (le chef de file a choisi de rédiger ce dossier sans IA) : », jamais l'aide
d'Adjugo, refusée au partenaire.

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
| `POST /espace` (lien seul) | `{code?, reinitialiser?}` | § 3.1 | 409 `espace_deja_ouvert`, `code_requis` ; 403 `espace_par_le_compte` ; 400 `code_absent` / `code_incorrect`, 429 |
| `GET /sections/{sid}` | — | SA partie + `brouillons` (historique, sans textes) | 404 `partie_introuvable` (toute partie qui n'est pas la sienne) |
| `GET /sections/{sid}/brouillons/{bid}` | — | un de SES brouillons précédents, avec son texte (« Reprendre ce texte » ; chantier du partenaire, § 15) | 404 `brouillon_introuvable` / `partie_introuvable`, 403 `cle_espace_requise` |
| `PUT /sections/{sid}/brouillon` | `{texte, base_brouillon_id, base_version_id?}` | « J'écris moi-même » : nouveau brouillon, faits contrôlés sur SES faits (ce qu'il écrit est sa déclaration ; un fait déjà à relire le reste, y compris un fait du texte du chef de file dont il part) ; `base_version_id` : le texte commun que l'écran montrait (null : rien d'envoyé) | 409 `brouillon_modifie`, `texte_modifie_entre_temps` ; 422 `texte_trop_long`, 403 `cle_espace_requise` |
| `POST /sections/{sid}/faits/{fid}` | `{statut: relu_par_vous|a_relire}` | sur son brouillon courant | 404 `fait_introuvable`, 409 `fait_avec_source` |
| `POST /sections/{sid}/aide` | `{action: rediger|raccourcir, cible_mots?}` | 202 `{tache, section_id}` (§ 6) | 409 `aide_en_cours`, `plafond_partie`, `aide_indisponible`, `aide_occupee`, `cv_dans_la_partie` (par le lien comme par le compte) ; 422 `partie_vide`, `deja_assez_court`, `cible_invalide` ; 403 `identity_unverified` |
| `GET /taches/{job_id}` | — | SA tâche : `{id, kind, status, label, result: {sections: [{section_id, ok, brouillon_id, coupe, a_completer, faits_a_relire, extraits_fournis}], echecs, message}, error}` (aucun texte) | 404 `tache_introuvable` |
| `POST /sections/{sid}/envoyer` | `{brouillon_id, avertissement_lu: true, base_version_id?}` | le brouillon courant devient le texte commun (aucune source) ; le chef de file est prévenu. Une modification du chef de file arrivée depuis que l'écran a montré le texte commun (ou, sans `base_version_id`, depuis l'écriture du brouillon) n'est jamais remplacée en silence | 422 `avertissement_requis` (message = l'avertissement à afficher), `partie_vide` ; 409 `brouillon_modifie`, `aide_en_cours`, `texte_modifie_entre_temps` ; 403 `identity_unverified` ; 404 `partie_introuvable` (partie reprise entre-temps) |
| `POST /sections/{sid}/valider` | `{version_id}` | valide le texte commun courant (le sien, ou celui du chef de file : contrôle de SES faits d'abord, brouillon `acceptee`) | 409 `texte_modifie_entre_temps` ; 403 `identity_unverified` |
| `POST /sections/{sid}/retablir` | `{base_version_id, version_id?}` | son texte d'avant redevient le texte commun | 409 `rien_a_retablir`, `texte_modifie_entre_temps` ; 404 `version_introuvable` |
| `POST /dossier/valider` | `{empreinte?}` | valide le dossier assemblé lu (après SES parties) | 409 `parties_a_valider`, `dossier_modifie` |
| `GET /export` | — | portabilité : ses brouillons, ses textes envoyés et `documents_deposes` (liste et accord) (JSON) | 403 `cle_espace_requise` |
| `GET /documents`, `POST /documents` (lien), `GET /documents/{did}/fichier`, `DELETE /documents/{did}` | — | « Vos documents pour Adjugo » : § 21.3 | § 21.3 |

Identité : envoyer, valider, rétablir et lancer l'aide de l'IA exigent l'adresse prouvée par code quand le lien
vise une adresse (`identity_unverified`, mêmes règles que l'envoi de la part), ou le compte vérifié qui a rattaché
le lien.

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
| `fiches_depot_par_lien(db, inv, chunks)` | option (a) de D5 (§ 21.6) : fiches [S#] « trouvé dans vos documents » des passages de SES documents déposés |
| `oublier_document(db, invite_id, depot_id)` | un document déposé supprimé : ses brouillons oublient les passages cités (§ 21.8) |
| `depot_lien.*` (`vue`, `deposer`, `fichier`, `supprimer`, `rechercher`, `extraits_cites`, `fiches`, `sources_reelles`, `effacer_invitation`, `effacer_projets`, `cles_projets`, `exporter`, `purger`, `conditions`, `textes_juridiques`, `limites`) | documents privés déposés par le lien (§ 21) |
| `note_acheteur(project, section)`, `resume_partenaire(db, inv)`, `brouillon_du_partenaire(db, acces, sid, bid)` | chantier du partenaire (§ 15) |

À respecter par les chantiers :
1. Ne jamais lire `dossier_parts_brouillons` hors de `atelier_groupement` ni l'exposer hors de l'accès du
   partenaire auteur.
2. Toute écriture d'un texte commun passe par ce module (jamais `atelier.ajouter_version(partage=True)`
   ailleurs), et appelle `apres_changement_commun`.
3. L'assemblage (chantier 3) : l'ordre suit le cadre de l'acheteur (`sections_actives`) ; « Organisation
   du groupement » vient de la convention ; « Qui fait quoi » montre lots, qualifications (libellé, justifiée
   ou déclarée) et moyens, validée par chaque membre (`valider_dossier`) et **ne liste JAMAIS les manques du
   chef de file** ; « Harmoniser le ton » ne retouche que les transitions et refuse tout fait absent avant.
   Construites par le chantier 3 : voir § 17 (`app/services/atelier_assemblage.py`).
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

Documents déposés par le lien (§ 21) : effacés au retrait ou au déclin de l'invitation, à la réinitialisation de son
espace (sans être lus), avec le marché (compte du chef de file effacé, corbeille), par la purge quotidienne (6 mois
après le résultat du marché, à défaut sa date limite, à défaut le dernier dépôt ; lien expiré depuis 30 jours), ou par
lui ; jamais dans l'export RGPD du chef de file ; dans `documents_deposes` de sa portabilité (liste et accord) et de
l'export RGPD de son compte (liens rattachés). Tableau complet : § 21.8.

Transfert de propriété de l'organisation, effacement d'un membre, réaffectation d'un dossier : les trois
tables suivent `owner_id` comme l'atelier. Purge quotidienne : `POST /api/admin/run-trash-purge`
(`brouillons_partenaires_effaces`, `taches_partenaires_effacees`).

---

## 11. Relances

`POST /api/admin/run-cotraitance-reminders` appelle aussi `relancer_parts` : un email par partenaire dont
une partie n'est pas encore envoyée, à J-2 puis le jour de sa date limite interne (un palier par partie,
jamais deux fois ; rien après dépôt ou clôture ; rien pour la démo). Changer la date limite remet le palier
à zéro. Jamais deux emails dans la même tournée : les parties à relancer d'un partenaire qui reçoit aussi le
rappel de sa part (co-traitance) sont AJOUTÉES à ce rappel (`parts_a_relancer`, résultat `parts_fusionnees`).
« Demander les parts » vaut relance du palier en cours (J-2 ou jour J), et une partie demandée le jour même
n'est pas relancée. Une partie confiée à un autre rédacteur repart de zéro : ni « demandée le », ni palier, ni
aide de l'IA utilisée (le plafond du dossier, lui, reste).

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
- rejoué depuis l'état exact de la production APRÈS la démo par lien privé (`0767372`, même tête
  `w7x8analysepartagee`), script `scratchpad/pgtest/run_v4_chef_depuis_prod.py` : migration, rejeu, code de
  production redémarré, retour arrière et remontée verts ; tests de la vague 4, de « Qui écrit quoi » et de la
  démo verts sur cette base. Deux groupes restent en échec sur Postgres, déjà en échec au socle et propres à
  SQLite (aucun lien avec la vague 4) : `test_secu2_donnees.py` (`PRAGMA foreign_keys`) et
  `test_hotfix_v2_fuites.py::test_fourche_historique_toleree_alteration_detectee` (journal écrit pour un compte
  inexistant, refusé par la clé étrangère de Postgres).

Déploiement sans casse : le code de production ne lit ni n'écrit les nouvelles tables et colonnes ; il crée
toujours ses tâches avec un compte. Retour arrière du CODE après la mise en ligne : une tâche de partenaire
en cours au redémarrage est close par l'ancien code mais son débit n'est pas rendu (il ne connaît pas
`payeur_id`) — cas rare, à rembourser à la main.

---

## 13. Limites connues (dites honnêtement)

- Lien rattaché à un compte : aucun espace par le lien (§ 3.1) — le chef de file qui détient le lien n'ouvre
  rien, ne réinitialise rien et ne lit rien. Lien qui vise une adresse : la première ouverture exige déjà le
  code envoyé à cette adresse. Le chef de file qui détient le lien peut encore RÉINITIALISER un espace déjà
  ouvert : il efface alors les brouillons non envoyés sans jamais les lire, et quand le lien vise une adresse
  il ne peut ensuite ni lancer l'aide de l'IA, ni envoyer, ni valider, ni relire un fait du texte envoyé à sa place
  (le code va au partenaire) ;
  quand le lien ne vise AUCUNE adresse (lien transmis à la main), rien ne distingue le chef de file du
  partenaire qui ouvre l'espace le premier : c'est inscrit au journal du membre (« espace ouvert », « espace
  réinitialisé »), le partenaire qui trouve son espace déjà ouvert le réinitialise (la clé de l'autre ne vaut
  plus), et l'écran recommande le compte (« Partagé avec moi ») ou une invitation avec adresse. Un espace ouvert ne
  se rattache à un compte qu'avec sa clé (§ 3.1) : le chef de file ne le prend pas par un second compte. Un lien sans
  adresse reste un lien au porteur : celui qui le rattache le PREMIER à un compte, avant toute ouverture de l'espace,
  devient le partenaire (comme pour la part de co-traitance depuis la vague 2).
- La clé de l'espace est gardée par le navigateur : un autre appareil la récupère par le code reçu par
  email (si le lien vise une adresse), sinon par réinitialisation.
- Le contrôle des faits dit où un fait est écrit, pas qu'il est vrai ; une phrase générale passe.
- Pré-remplissage : simple rapprochement de mots du lot et de la partie ; le chef de file reste maître.
- Documents déposés par le lien : limites propres à cette fonction au § 21.11.

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
Documents déposés par le lien (§ 21) : `tests/test_redaction_v4_depot_lien.py`.

---

## 15. Chantier du partenaire : l'écran « Mes parties du dossier de présentation » (fait)

Étude § 6.8, parcours point 2. Un SEUL écran pour les deux accès : `app/static/redaction-partenaire.js`
(script servi avec son empreinte SRI dans `invite.html` et `app.html`, styles `.rp-*` dans `styles.css`).

### 15.1 Montage

```js
const h = window.AdjugoRedactionPartenaire.mount(el, {
  base: "/api/invite/<token>/redaction" | "/api/shared/<projet>/redaction",
  mode: "lien" | "compte",
  headers: () => ({Authorization: "Bearer …"}),           // compte
  cleStockage: "adjugo_espace_<token>",                    // lien : la clé de l'espace, dans CE navigateur
  invite: "/api/invite/<token>",                           // lien : demande d'un code par email
  verifyIdentity: (msgEl, {purpose}) => Promise<bool>,     // lien : code reçu par email (identity_unverified)
  onChange: () => {},                                       // après une action (ex. « Mon journal »)
});
h.reload(); h.destroy();
```
- **Lien** (`invite.html`, `renderMonAO`) : monté après la convention, sauf aperçu limité (réseau non accepté)
  et sous-traitant. La clé part dans l'en-tête `X-Adjugo-Espace` de chaque appel, jamais dans une adresse.
- **Compte** (« Partagé avec moi », `app.html`) : composant Vue `<redaction-partenaire :pid :token>` au gabarit
  statique (Vue ne redessine jamais son contenu). La liste « Partagé avec moi » montre une pastille
  « Partie(s) à rédiger » / « à revalider » (`/api/shared` → `redaction: {parties, a_faire, a_revalider}`,
  statuts seulement, `null` si le dossier n'est pas préparé).
- Réponse 403 / 404 / 410 de la vue (dossier pas préparé, sous-traitant, aperçu limité, lien coupé) : l'écran
  reste vide.

### 15.2 Ce que l'écran montre et fait

| élément | données (API) |
|---|---|
| En-tête : « n parties confiées à X · Sections validées k sur n », pastille « n à faire » / « À jour » | `membre`, `parties[].statut`, `dossier.pret` |
| Espace privé (lien) : « Ouvrir mon espace », « Recevoir un code » (si l'invitation vise une adresse), « Réinitialiser mon espace » (confirmation : brouillons non envoyés effacés) | `espace`, `POST /espace`, `POST /api/invite/{token}/otp/request` |
| Une partie (accordéon, la première « à rédiger / en cours / à revalider » ouverte) : titre, statut, longueur conseillée, date limite, mention « Modifié par le chef de file, à revalider par X » | `parties[]` |
| « Ce que l'acheteur note » : critère, poids TEL QU'ÉCRIT et d'où il vient, phrase du règlement retrouvée ; question du cadre ; sans critère (plan du cadre), les critères techniques de la grille et leurs phrases (le prix n'en fait pas partie) ; limites | `note = {critere, poids, poids_source, poids_libelle, phrase, question, source_plan, grille[]}`, `limite` |
| « Rédiger avec Adjugo » / « J'écris moi-même » ; « Partir de mon paragraphe » (mode simple) ; aides restantes dans la bulle (i) ; plafond atteint : phrase neutre | `aide`, `POST /aide`, `mode_simple` |
| Tâche en cours : suivie toutes les 2 s (`GET /taches/{id}`), reprise au rechargement ; échec : le message du serveur (IA en panne : aide rendue, rien débité) | `aide.en_cours` |
| Éditeur : texte, mots / longueur conseillée, « [À compléter] » à remplir, « Enregistrer », « Rédiger / Refaire avec Adjugo », « Raccourcir avec Adjugo » (au-delà de la longueur conseillée), « Envoyer au groupement » / « Envoyer cette version » ; saisie non enregistrée gardée dans l'onglet (sessionStorage) | `brouillon`, `PUT /brouillon` |
| « Vos brouillons précédents » → « Reprendre ce texte » (aucune génération n'écrase un texte sans version qu'on peut reprendre) | `GET /sections/{sid}` (`brouillons`), `GET /sections/{sid}/brouillons/{bid}` |
| À relire : type, phrase (fait surligné), message, « Je l'ai relu » / « Je confirme cet engagement », « Relus par vous » ; libellés de source et « Faits avec une source » seulement si `controle.libelles` (mêmes règles que l'atelier) ; ses extraits cités (privés) | `brouillon.faits`, `controle`, `faits_sources`, `sources`, `POST /faits/{fid}` |
| Envoyer : fenêtre qui affiche « Ce texte sera lu par le chef de file et par les autres membres du groupement. », ce que reçoit le chef de file (texte, faits à relire, compteurs par type ; jamais sources, extraits ni brouillons), les « [À compléter] » restants ; puis `avertissement_lu: true` ; identité prouvée si demandée | `avertissement_envoi`, `identite`, `POST /envoyer` |
| Envoyée : « Valider ma partie » (bulle : une modification ensuite fait repasser « à revalider ») ; Validée : date ; texte commun replié | `texte_commun`, `validation`, `POST /valider` |
| Modifiée par le chef de file : l'avant et l'après côte à côte, mot à mot (retiré / ajouté surlignés, sans IA), « Valider la modification » / « Rétablir ma version » (ou « Valider ce texte » quand il l'a écrit à sa place), « Écrire une autre version », « Partir du texte du chef de file » | `comparaison`, `POST /valider`, `POST /retablir` |
| Le dossier assemblé : « Lire le dossier assemblé » (lecture seule, renvois montrés comme « votre source », « source du partenaire », « source du chef de file »), « Valider le dossier assemblé » (après ses parties, sur l'empreinte lue) | `GET /dossier`, `POST /dossier/valider` |
| Mode simple : le paragraphe de sa part, tel quel (toujours modifiable dans « Ma contribution ») | `mode_simple` |
| « Télécharger mes textes » (portabilité) | `GET /export` |

Champs ajoutés à `GET …/redaction` par ce chantier : `membre {nom, lot}`, `identite {a_prouver, message}`,
`mode_simple {petit_texte, message}`, `parties[].note`, `dossier.pret`.

### 15.3 Démo

Toutes les routes d'écriture V4 sont classées dans `tests/test_demo_sans_cout.py` (aide de l'IA et envois
à coût ; le reste sans coût) et refusées à la démo dans la route, derrière le garde central : compte démo
(`refuser_demo`) et lien partenaire de la démo (`_par_lien(…, ecrire=True)`, refusé AVANT tout autre
contrôle, 403 `demo` « lecture guidée »). La remise à neuf de la vitrine efface aussi brouillons,
répartition et validations (clés étrangères sous Postgres).

### 15.4 Tests

`tests/test_redaction_v4_partenaire.py` : parcours de l'écran contre l'API (lien), « Ce que l'acheteur
note » (grille et cadre), « Partagé avec moi » (pastille, compte, sources du compte réservées au compte),
brouillons précédents (seul leur auteur), aide indisponible neutre (essai terminé, IA en panne : aide
rendue), isolation entre membres et 404, démo (lien et compte, même sans le garde), règles d'interface et
fonctions pures de l'écran sous Node (échappement, renvois, avant / après mot à mot).

## 16. Écran « Qui écrit quoi » du chef de file (chantier 2 — fait)

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
  (envoyée à, sans adresse, déjà demandée, limite du jour atteinte, « Aucune demande à X : son lien a expiré. »).
  La confirmation et le bouton ne comptent que les partenaires qui peuvent rédiger (`membres[].peut_rediger`) ;
  quand la seule part en attente est chez un partenaire qui ne le peut plus : « Aucune partie à demander pour
  l'instant. », sa raison dessous (jamais « chaque partenaire a envoyé ses parties »).
- **Recevoir** : statut de chaque part, « Envoyée le … », et les COMPTEURS : « 5 faits avec une source : 3
  déclarés, 2 trouvés dans ses documents · 1 fait à relire · 1 passage « [À compléter] » ». Jamais une
  source, un extrait ni un nom de document (l'écran ne lit aucun de ces champs).
- **Lire, modifier, écrire à sa place** : texte commun rendu par le moteur sûr de l'atelier
  (`atlMdToHtml(texte, [], {refsPartenaire: true})` : renvois montrés « source du partenaire », sans lien) ;
  « Modifier ce texte » → `PUT …/texte` → « à revalider par X », avant et après côte à côte ; « Rédiger à sa
  place » (rien d'envoyé) → « Rédigé par le chef de file, à valider par X ». Sur téléphone : lire et répartir ;
  écrire depuis un ordinateur : une part sans texte n'a pas de bouton « Rédiger à sa place », la phrase et le volet
  disent « Depuis un ordinateur, vous pouvez … », le lien de l'onglet « Rédaction » dit « Voir dans « Qui écrit
  quoi » » au lieu de « Le modifier ou l'écrire à sa place ».
- **Aucune IA pour la part d'un partenaire** : aucun bouton dans cet écran ; le serveur refuse (403
  `partie_d_un_partenaire`, 404 par « Partagé avec moi », 403 `cle_espace_requise` par le lien sans clé).
- **Dans l'atelier** (onglet « Rédaction »), une partie de partenaire porte `part: {statut, statut_libelle,
  mention}` (`atelier.section_out` → `ag.statut_de`, `ag.mention`) : le plan et la pastille disent « Envoyée »,
  « À revalider »… au lieu du statut de l'atelier ; « Rédigée par X » dans le plan ; ses compteurs à droite ;
  lien « Le modifier ou l'écrire à sa place ».
- **Démo** : chaque route d'écriture du chef de file appelle `refuser_demo` (en plus du garde central) ; le
  lien partenaire de la vitrine est refusé dans la route (`_par_lien(…, ecrire=True)` → 403 `{code: demo}`),
  même sans dossier commun ; « Partagé avec moi » : `refuser_demo`. Toutes les routes de la vague 4 sont
  classées dans `tests/test_demo_sans_cout.py` (`COUTS` : aide de l'IA, demander, texte du chef de file,
  envoyer ; `SANS_COUT` : le reste).

Pas dans ce chantier : la validation du dossier assemblé et « Prêt à déposer » (chantier 3 ; l'écran montre
seulement « Sections validées k sur n » et qui a validé le dossier), l'harmonisation du ton, les écrans du
partenaire (chantier 1).

## 17. Assemblage et validation (chantier 3)

Étude § 6.8 B, parcours points 4 et 5. Code : `app/services/atelier_assemblage.py` (`asm`), DERRIÈRE
`atelier_groupement` (appelé par lui, et par deux crochets de l'atelier : la validation d'une partie tirée du
groupement, et leur rafraîchissement avant toute lecture du texte commun). Tests :
`tests/test_redaction_v4_assemblage.py`. **Aucune migration** : tout tient dans les tables du socle.

### 17.1 Choix faits par défaut (à valider par Eliot)

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
   phrases, plus de 40 mots, titre, liste, renvoi, « [À compléter] », adresse email ou web) ou si elle apporte UN
   fait absent du dossier avant l'harmonisation — nombre (chiffres, lettres, pourcentage, montant, durée, année,
   nombre collé à son unité « 48h », « 1200m² », ordinal « 1er », « 3e », et, par filet, tout nombre écrit en
   chiffres que le dossier ne contient pas), rang (« premier », « leader »), date, période ou fréquence
   (« quotidien », « chaque semaine », « dès la rentrée », « l'an prochain », « la nuit », « le jour même »),
   quantité (« une centaine », « la moitié », « la totalité »), certification ou qualification, nom propre (au fil
   de la phrase, ou en tête quand ce n'est pas un mot d'ouverture connu du dossier), matériel, engagement ou délai,
   même à la troisième personne (« garantit », « une garantie décennale », « en moins d'une heure ») (repérage du
   contrôle A : `faits_a_relire`, `faits_sources.engagement`). Une partie touchée repasse « à revalider » par son auteur (partie
   d'un partenaire : texte commun « écrit par le chef de file », avant / après, valider ou rétablir ; partie du chef
   de file : nouvelle version, origine `harmonise`, ses sources et faits gardés) ; un fait de la phrase absent de
   CETTE partie y est à relire. Débit : une refonte du dossier (décision 6a ; la 1re action de l'IA du dossier
   compte pour 1 analyse), RENDUE si l'IA tombe ou si aucune phrase n'est retenue. Tâche `atelier_harmoniser`
   (même relevé, même remboursement, même reprise au redémarrage que l'atelier). Routage : tâche IA « raccourcir »
   (même modèle, aucune route nouvelle ; estimation du garde-fou de l'essai : enveloppe `harmoniser` tirée de ses
   plafonds). Ce qui part à l'IA : intitulés, fin de la partie précédente et début de la partie (700 caractères),
   auteurs anonymisés (« membre A »), noms des salariés masqués (`pii_scope` : équipe du chef de file, des
   partenaires dont la part est soumise ET de tout partenaire qui a un compte, part soumise ou non), aucun CV (repéré
   sur le texte tel qu'écrit : les blocs en forme de CV sont retirés avant l'extrait ; s'il reste un CV
   reconnaissable, passage non transmis), espace facturé du chef de file.

### 17.2 Routes (nouvelles ou étendues)

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

### 17.3 Journal chaîné

| action | qui | journal du membre |
|---|---|---|
| `redaction.partie_groupement_validee` | membre | événement de groupement (« … a validé « Qui fait quoi » ») |
| `redaction.partie_groupement_a_jour` | Adjugo (system) | événement de groupement (« … a suivi la convention ou la part d'un membre : à revalider ») |
| `redaction.harmonisation` | chef de file | événement de groupement |
| `redaction.transition_ajoutee` | chef de file | le partenaire concerné (« … phrase de transition au début de votre partie : à revalider ») |

### 17.4 Export (D2 étendu)

L'export Word / PDF de l'atelier rend le dossier assemblé COMPLET, dans l'ordre du plan, parties tirées du groupement
comprises (rafraîchies juste avant) ; renvois `[F#]` / `[S#]` retirés ; aucun libellé interne (justifiée, déclarée,
mention de rédaction, note interne), aucun prix dans les parties tirées du groupement. Blocage avec dérogation
journalisée : les « [À compléter] » d'une partie tirée du groupement (convention absente ou périmée, part pas
envoyée, part du chef de file inconnue) bloquent comme ceux d'une part de partenaire (socle) ; non validée :
avertissement `non_valide`.

### 17.5 Démo

`POST /repartition/harmoniser` : garde central (`demo_guard`) + `refuser_demo` dans la route. Par le lien du
partenaire de la démo, toute écriture `…/redaction…` est refusée dans la route AVANT tout (« lecture guidée »).
`tests/test_demo_sans_cout.py` classe toutes les routes de la vague 4 (COUTS : harmoniser, aide du partenaire, demander
les parts, modifier la part d'un partenaire, envoyer ; SANS_COUT : les autres).

### 17.6 Limites connues

- « Justifiée » pour la qualification d'un partenaire repose sur le NOM du justificatif joint (rapprochement de mots,
  prudent) : on dit qu'un justificatif existe, jamais qu'il est bon.
- Une part modifiée après son envoi repasse en brouillon (co-traitance v2) : elle disparaît de « Qui fait quoi »
  (« à compléter ») jusqu'à son renvoi — on n'expose jamais un brouillon.
- Le contrôle des transitions refuse tout fait nouveau, pas une phrase creuse ; un mot d'ouverture inconnu du dossier
  en tête de phrase est pris pour un nom (refus prudent).
- « Qui fait quoi » est lue par tous les membres dès sa création (décision 3a : le dossier assemblé se lit en entier) :
  la part, les qualifications et l'effectif que chacun a déclarés dans sa part envoyée, et les qualifications et le
  matériel acceptés dans « Mes preuves » du chef de file, deviennent communs — jamais un document, une source, un
  prix ni un brouillon. Chaque membre valide ce qui est dit de lui avant l'export ; le chef de file peut retirer la
  partie. À dire sur l'écran de la part du partenaire (chantier écrans).
- Écrans : l'atelier montre une bulle (i) et « Valider » pour une partie tirée du groupement ; « Prêt à déposer »,
  « Harmoniser le ton » et « Qui fait quoi » côté partenaire sont branchés à l'intégration (§ 18).

### 17.7 Vérifications

- `tests/test_redaction_v4_assemblage.py` (13 tests) : ordre du cadre et place des parties tirées du groupement (cadre
  imposé, plan simple, retrait, remise, plan reconstruit, quota) ; « Organisation » tirée de la convention (en attente
  d'accords, validée par tous, sans prix) ; convention absente, en brouillon, périmée (« à compléter », export bloqué,
  « à revalider », historique) ; « Qui fait quoi » sans manque, libellés à l'écran seulement, note interne au chef de
  file seul, validation par chaque membre, part modifiée ; part non envoyée ; 28 transitions refusées, de 8 genres de
  faits et de formes variées (chiffre, nombre en lettres, pourcentage, année, date, mois, saison, fréquence, montant,
  décimal, ISO, Qualibat, RGE, MASE, « certifiées », noms propres en tête ou au fil de la phrase, matériel,
  engagements, quantités), les formes refusées et des transitions acceptées ; harmonisation de bout en bout (texte des membres intact,
  « à revalider », débit, noms masqués, rétablir, transition remplacée) ; panne et rien de retenu : rien n'est
  décompté ; compteur « Sections validées k sur n », ce qui manque, revalidation ; export Word et PDF propre et bloqué
  (dérogation journalisée) ; démo.
- Le test du socle `test_validation_du_dossier_assemble_puis_a_revalider` suit l'assemblage : parts envoyées, convention
  validée par tous, « Organisation » et « Qui fait quoi » validées, « Sections validées 6 sur 6 ».
- Postgres 16 depuis l'état EXACT de la production (`0767372`, `w7x8analysepartagee`), script
  `scratchpad/pgtest/run_v4_assemblage_depuis_prod.py` : une seule révision appliquée (`x8y9redactionv4`, aucune pour
  l'assemblage), aucune donnée perdue, rejeu, code de production redémarré sur la base montée, schéma identique,
  retour arrière et remontée ; tests rejoués sur cette base : assemblage 13, socle 23, démo (sans coût, lien privé,
  Kerhel, remise à neuf) 186, atelier 105, V3 227, essai et routage 87, analyse partagée 40, journal et vocabulaire 30 —
  verts ; seuls échecs, les mêmes qu'au passage du socle et sans lien avec la vague 4 : 6 tests propres à SQLite
  (`PRAGMA foreign_keys`, clés étrangères non contrôlées : `test_secu2_donnees.py`, `test_hotfix_v2_fuites.py`).

## 18. Intégration des trois chantiers (fait)

Fusions, dans l'ordre : socle, partenaire (§ 15), chef de file (§ 16), assemblage (§ 17). Conflits résolus en gardant
les deux intentions : vue du partenaire (`membre`, `identite`, `mode_simple`, `dossier.pret` du chantier partenaire, plus
`qui_fait_quoi` et `peut_valider` qui tient compte de « Qui fait quoi » de l'assemblage) ; atelier (bloc d'une partie tirée
du groupement, puis ligne d'une part de partenaire avec sa mention) ; `tests/test_demo_sans_cout.py` (chaque route de la
vague 4 classée UNE fois : aide de l'IA et « Harmoniser le ton » dans `COUTS`, refus du lien de la démo « avant tout
autre contrôle ») ; contrat renuméroté (assemblage en § 17). Aucune migration ajoutée : une seule révision,
`x8y9redactionv4`.

### 18.1 Écrans branchés sur l'assemblage

| écran | ajout |
|---|---|
| Partenaire (`redaction-partenaire.js`) | Bloc « Qui fait quoi dans le groupement » sous le dossier assemblé : bulle (i) (écrite par Adjugo sans IA, ce que chacun apporte, jamais ce qui manque, chacun la valide), sa validation, « Lire ce que dit cette partie » (texte, puis « Qualifications citées » avec « justifiée » / « déclarée » et leur bulle : à l'écran seulement), « Valider cette partie » (désactivé tant qu'il reste un « [À compléter] »). Dossier assemblé : une partie tirée du groupement dit « Écrite par Adjugo à partir de la convention et des parts des membres ». Rappel : « Validez d'abord chacune de vos parties et « Qui fait quoi… » ». |
| Partenaire, « Ma contribution » (`invite.html`) | Bulle (i) à côté de « Soumettre au chef de file » (co-traitant seulement) : sa part soumise est reprise dans « Qui fait quoi », lue par tous les membres ; ni pièces, ni prix, ni détail chiffré (§ 17.6). |
| Chef de file, « Qui écrit quoi » (`app.html`, `app.js`) | En-tête : « Prêt à déposer » quand `pret.complet`, sinon « Ce qui reste avant de déposer (n) » (`pret.manques`) ; « Valider le dossier assemblé » (confirmation, empreinte lue ; désactivé tant que SES parties, « Organisation » ou « Qui fait quoi » attendent un geste de lui) ; « Harmoniser le ton » (seulement s'il y a des parts de membres différents à relier, `harmoniser.jonctions` ; jamais sur téléphone ; confirmation, débit confirmé par la fenêtre de l'atelier, tâche suivie toutes les 2 s, message de fin). Partie tirée du groupement : ni « Rédigée par », ni longueur, ni date ; « Écrite par Adjugo, sans IA » et sa bulle ; qui a validé « Qui fait quoi » ; « Lire cette partie » (texte, qualifications citées, note interne pour lui seul) ; « La valider dans l'onglet « Rédaction » ». |

Ajout à `GET /api/atelier/{pid}/repartition` : `harmoniser: {message, jonctions}`.

### 18.2 Correction trouvée par le parcours complet

Quand le partenaire valide un texte écrit ou modifié par le chef de file, le contrôle des faits tourne chez lui, sur ses
faits, et ce qu'il ne peut pas sourcer reste à relire (rien n'est blanchi). Sa relecture (« Je l'ai relu ») portait sur
son brouillon seulement : le texte commun gardait le fait « à relire » et l'export du chef de file restait bloqué sans
recours (sauf dérogation). Désormais `traiter_fait` reporte la relecture sur le texte commun quand son brouillon EST ce
texte (même empreinte) : faits à relire SANS source et compteurs mis à jour, texte, empreinte et validations inchangés.
L'écran du partenaire garde ces faits à relire sous ses yeux quand l'éditeur est replié.

### 18.3 Vérifications

- `tests/test_redaction_v4_parcours_complet.py` : le parcours de bout en bout par l'API — répartir, demander les parts
  (email au partenaire qui a une adresse, « transmettez-lui son lien » sinon), A par son lien SANS compte (aide de
  l'IA sur sa part déclarée et le dossier de l'acheteur, portée `inv:<id>`, rien du chef de file ni de B ; une partie
  écrite lui-même, un brouillon privé jamais lu du chef de file), envoi avec l'avertissement exigé, compteurs sans
  extrait, part modifiée par le chef de file puis revalidée (avant / après, fait relu par A), B par son COMPTE (ses
  preuves et son savoir-faire, rien de A ni du chef de file), 404 sur `/api/jobs/{id}` et `/taches/{id}` pour un membre
  de l'organisation du chef de file, partie du chef de file, assemblage (ordre du cadre, parties tirées du groupement
  en tête, note interne au chef seul, « Qui fait quoi » sans manque ni mention), « Qui fait quoi » validée par chacun,
  « Sections validées 6 sur 6 », dossier validé par chaque membre, « Prêt à déposer », export Word complet sans renvoi,
  libellé interne, prix, secret ni « Adjugo », journal chaîné ; marché sans groupement inchangé (aucun onglet, aucune
  partie tirée du groupement, rien à assembler ni à harmoniser, aucune ligne de répartition).
- Écrans : tests d'interface et fonctions pures sous Node (partenaire et chef de file) ; aperçu local à 375 px et
  1 024 px (lien du partenaire, « Qui écrit quoi ») : aucun défilement horizontal.
- Deux tests rendus insensibles aux empreintes tirées au hasard (« 402 » dans une empreinte ; dix chiffres de suite
  pris pour un numéro de téléphone).
- Suite complète verte (SQLite) ; Postgres depuis l'état EXACT de la production (`0767372`, `w7x8analysepartagee`),
  script `scratchpad/pgtest/run_v4_integration_depuis_prod.py` : une seule révision appliquée, aucune donnée perdue,
  seconde montée sans effet, rejeu forcé, code de production redémarré sur la base montée, schéma identique à une base
  neuve, retour arrière et remontée ; tests rejoués sur cette base (parcours complet 2, partenaire 9, chef de file 25,
  assemblage 13, socle 23, démo 186, atelier 105, V3 227, essai et routage 87, analyse partagée 40, journal 30) verts ;
  seuls échecs, les 6 tests propres à SQLite déjà connus (`PRAGMA foreign_keys` : `test_secu2_donnees.py`,
  `test_hotfix_v2_fuites.py`).


## 19. Corrections après les cinq relectures (cloisonnement, anti-invention, parcours, coûts et RGPD, interface)

29 remarques (2 bloquantes, 14 majeures, 13 mineures), toutes reproduites par un test qui échouait avant la correction
(`tests/test_redaction_v4_corrections.py`, 28 tests ; deux remarques étaient en double). Aucune rejetée, aucune
migration.

### 19.1 Cloisonnement

| constat | correction |
|---|---|
| Bloquant : le chef de file, qui détient le lien, ouvrait l'espace du lien (première ouverture libre) d'un partenaire qui travaille par son compte, et lisait ses brouillons privés (texte de l'IA, extraits et noms de documents recopiés par un réenregistrement) | Lien rattaché à un compte : aucun espace par le lien (`par_le_compte`, 403 `espace_par_le_compte`, réinitialisation comprise) ; une clé prise avant le rattachement ne vaut plus ; un brouillon écrit depuis le compte ne se lit ni ne s'utilise jamais par le lien (vue, historique, `brouillons/{bid}`, export, enregistrer, envoyer, raccourcir) |
| Le chef de file agissait au nom du partenaire (aide de l'IA ; envoi et validation quand l'adresse était déjà prouvée) | Lien qui vise une adresse : code exigé dès la PREMIÈRE ouverture (409 `code_requis`) ; `lancer_aide` exige l'identité comme envoyer et valider |
| CV écrit dans la part envoyée d'un partenaire envoyé à l'IA par « Harmoniser le ton » (CV repéré sur l'extrait aplati) | CV repéré sur le texte tel qu'écrit (`preuves_atelier.retirer_cv_par_forme`, puis `cv_presents` avec les fiches « Équipe » de l'auteur) |
| « Raccourcir » par le lien envoyait un CV à l'IA | `refuser_cv_pour_ia` par le lien comme par le compte (la forme suffit) |
| Nom d'un salarié d'un partenaire envoyé en clair par l'harmonisation (part de co-traitance non soumise) | Équipes de tous les partenaires qui ont un compte ajoutées au masquage (rien n'est montré) |
| Un membre retiré de l'organisation du partenaire relisait les extraits et documents de son ancienne organisation | `_matiere_visible` : depuis le compte, seuls les extraits et preuves de l'organisation actuelle du compte (vue, historique, export) |

### 19.2 Anti-invention

| constat | correction |
|---|---|
| Contrôle A aveugle aux nombres collés (« 1200m² », « 30t », « 15km », « 48h », « 3j »), aux ordinaux (« 1er », « 3e ») et à « neuf » | `faits_a_relire._NUMBER` : unité collée et ordinal (`unite_de`), « neuf » devant un nom compté (« dix-neuf » compris) ; « un bâtiment neuf », « CACES R486 », « A320 » restent sans nombre ; une source écrite collée appuie le même fait écrit avec une espace |
| 20 transitions piégées passaient (chiffres collés, rang, totalité, périodes, engagements à la troisième personne, matériel hors liste) | `controle_transition` : rangs, périodes relatives, totalité, engagements et délais, filet sur tout nombre en chiffres absent du dossier ; matériel du contrôle A complété (aspirateur, robot, marteau-piqueur…) ; les 20 pièges ajoutés aux tests |
| « Partir du texte du chef de file » blanchissait ses faits à relire | Les faits à relire du texte commun écrit par le chef de file restent à relire chez le partenaire |
| Revalider après une retouche faisait repasser à relire les propres déclarations du partenaire | `_garder_ses_declarations` : ses phrases inchangées gardent « déclaré par vous » |

### 19.3 Parcours et états

| constat | correction |
|---|---|
| Une nouvelle version envoyée après la validation : aucun bouton pour la revalider | « Valider cette nouvelle version » (écran) |
| Co-traitant sans partie : jamais « peut valider » le dossier assemblé (« Prêt à déposer » inatteignable) | `peut_valider` sans `bool(parties)` ; message propre (« Validez d'abord « Qui fait quoi… » ») |
| Un envoi du partenaire remplaçait en silence une modification du chef de file arrivée entre-temps | Verrou optimiste sur le texte commun (`base_version_id` dans `PUT …/brouillon` et `POST …/envoyer`, 409 `texte_modifie_entre_temps`) ; sans lui, un brouillon écrit avant la modification ne la remplace pas ; l'écran recharge et montre l'avant et l'après |
| Envoi pendant la reprise de la partie par le chef de file : son texte devenait celui de la partie du chef de file | `_toujours_sienne` : partie et répartition relues sous verrou avant toute écriture (envoyer, enregistrer, valider, rétablir, aide) |
| « Organisation du groupement » redevenait « Validée » seule après une régénération de la convention au même texte | La validation retient la convention validée (`plan_meta.orga_validation`) : autre version, accords en attente ou convention périmée → « à revalider » (`synchroniser_orga`) |
| Partie envoyée affichée « À jour » et absente de « Partagé avec moi » | Comptée « à faire » à l'écran ; `resume_partenaire.a_valider` et « Partie à valider » dans la liste |
| Partie confiée à un autre partenaire : « demandée le » et relance du précédent gardés, plafond d'aide hérité | `_changer_auteur` remet à zéro `demandee_le`, `relance_palier`, `aides_ia` |
| Deux rappels au même partenaire dans une tournée ; relance juste après « Demander les parts » | § 11 |

### 19.4 Coûts, interface, code

| constat | correction |
|---|---|
| Bloquant : `lucide.createIcons()` sur tout le document figeait les écrans Vue de « Partagé avec moi » | Icônes de l'écran du partenaire et de sa fenêtre seulement (`createIcons({root})`) |
| Harmonisation sans rien à faire : tâche illisible (404), message jamais montré | Le relevé reste dans le résultat (rien n'est décompté) |
| Estimation de l'essai sous-estimée pour « Harmoniser le ton » | Enveloppe `harmoniser` (60 000 caractères, 4 000 en sortie) |
| Onglet « Rédaction » : parties tirées du groupement en « Brouillon », bouton « Valider » encore là après sa validation, « envoyée par Tirée de la convention… », phrase « restent chez son auteur » | `section_out.part` (statut de « Qui écrit quoi », `a_valider_par_vous`, « Validée par vous ; à valider par X ») ; origine et panneau propres aux parties écrites par Adjugo ; trouvé en vérifiant à l'écran : l'en-tête « 1 validée sur 6 · 2 brouillons » compte désormais chaque partie de groupement selon sa pastille (« 2 à valider ») |
| « Partagé avec moi » : pas d'avertissement avant de soumettre sa part (reprise dans « Qui fait quoi ») | La même bulle que par le lien (co-traitant seulement) |
| Compteurs au pluriel (« 1 déclarés ») | Singulier et pluriel |
| Code mort (`_fold_mots`, `est_validation_qfq`) | Retiré |

### 19.5 À dire à Eliot (choix faits par défaut)

1. Un partenaire qui a rattaché son lien à un compte rédige seulement depuis ce compte (le lien ne lui ouvre plus
   d'espace) : c'est ce qui garantit que le chef de file, qui a le lien, ne lit rien.
2. Une invitation avec adresse : le partenaire reçoit un code pour ouvrir son espace dès la première fois (une étape
   de plus pour lui, aucune possibilité pour le chef de file d'ouvrir à sa place).
3. Une partie confiée à un autre partenaire lui rend ses 3 aides de l'IA (le plafond du dossier, lui, ne bouge pas).
4. « Organisation du groupement » se revalide après chaque nouvelle convention, même si son texte ne change pas.
5. Le contrôle A repère désormais les nombres collés à leur unité et les ordinaux partout (atelier compris) : un peu
   plus de faits « à relire », jamais un fait inventé qui passe.

### 19.6 Vérifications

- `tests/test_redaction_v4_corrections.py` (28 tests) : chacun échouait avant la correction (reproduction de la
  remarque), passe après. Tests existants adaptés au nouveau comportement voulu (et non affaiblis) : espace par le
  lien refusé après le rattachement (`test_texte_envoye_compteurs…`, `test_rgpd_export…`, `test_partage_avec_moi…`),
  « Demander les parts » vaut relance du palier (`test_demander_les_parts…`), `par_le_compte` et `a_valider` dans
  les réponses, compteurs au singulier.
- Suite complète verte (SQLite) : 1 608 tests ; empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check`
  sur `app.js` et `redaction-partenaire.js`.
- Écrans sous Node (faux DOM minimal) : icônes limitées à l'écran (`createIcons({root})`), « Valider cette nouvelle
  version », partie envoyée « à faire », message d'un co-traitant sans partie, compteurs au singulier.
- Navigateur réel, aperçu local (`adjugo-v4corr-verif`, base de travail remplie par `scratchpad/v4corr/seed_live.py`) :
  lien rattaché à un compte (« Ouvrir mon compte », rien à ouvrir) ; « Partagé avec moi » : 44 icônes gérées par Vue
  restées `<i>` hors de l'écran du partenaire (13 `<svg>` dedans seulement), roue d'attente qui apparaît et disparaît,
  aucune erreur de rendu, bulle avant « Soumettre au chef de file », « Valider cette nouvelle version » → « Partie
  validée. » ; co-traitant sans partie par le lien : « Validez d'abord « Qui fait quoi… » » ; chef de file : pastilles
  « À valider », pied « Tiré de la convention et des parts des membres, sans IA », en-tête « 1 validée sur 6 · 2 à
  valider · 3 à écrire » ; 375 px sans défilement horizontal.
- Postgres 16 depuis l'état EXACT de la production — `d6504e4` puis `0767372` (démo par lien privé, même tête
  `w7x8analysepartagee`) — script `scratchpad/pgtest/run_v4_corrections_depuis_prod.py` (TZ=UTC) : données créées
  par le code de production, une seule révision appliquée (`x8y9redactionv4`), aucune donnée perdue, seconde montée
  sans effet, rejeu forcé sans effet, code de production redémarré sur la base montée avec une tâche de partenaire
  en cours, schéma identique à une base neuve (0 écart de colonnes, 0 d'index), retour arrière (tables retirées,
  seules les tâches sans compte supprimées) et remontée. Tests rejoués sur la base montée depuis `0767372` : 748, dont
  747 verts ; seul échec, déjà connu et propre à SQLite : `test_hotfix_v2_fuites.py::test_fourche_historique_toleree_
  alteration_detectee` (journal écrit pour un compte inexistant, refusé par la clé étrangère de Postgres).


## 20. Contre-relecture des corrections (cloisonnement, anti-invention)

Six remarques (4 majeures, 2 mineures), toutes reproduites par un test qui échouait sur `6a040d2`
(`tests/test_redaction_v4_contre_relecture.py`, 11 tests dont 10 échouaient avant ; le onzième garde le
rattachement libre d'un lien jamais ouvert). Aucune rejetée, aucune migration.

### 20.1 Cloisonnement

| constat | correction |
|---|---|
| Lien sans adresse : un second compte (celui du chef de file, au nom d'une autre entreprise) rattachait le lien alors que le partenaire y rédigeait déjà ; il lisait ses brouillons privés, lançait l'aide de l'IA, envoyait à sa place, et le partenaire perdait son espace sans recours (clé morte, réinitialisation refusée) | Espace du lien ouvert : `POST /api/invite/{token}/claim` exige la clé de l'espace (`X-Adjugo-Espace`), sinon 409 `espace_a_prouver` (« ouvrez-le dans le navigateur où vous rédigez votre partie… ») ; la page du lien et l'application joignent la clé gardée par le navigateur ; le journal note « clé présentée ». Le partenaire garde son espace ; il rattache son lien depuis son navigateur (ses brouillons suivent son compte) |
| Lien qui vise une adresse : après une réinitialisation, le chef de file recopiait le texte commun dans un brouillon et marquait chaque fait « relu » ; la relecture passait au texte commun, l'export n'était plus bloqué, sans trace au journal | Relire un fait d'un brouillon qui EST le texte commun exige l'identité comme un envoi (403 `identity_unverified`, l'écran demande le code) et s'inscrit au journal chaîné (`redaction.fait_relu`, `redaction.fait_a_relire`, journal du membre) ; un brouillon privé reste privé (ni identité, ni journal) |
| Export RGPD (`/api/rgpd/export`) d'un membre retiré de l'organisation du partenaire : extraits et noms de documents de son ancienne organisation | `exporter_partenaire` filtre comme la route d'export (`_matiere_du_compte` : extraits et preuves de l'organisation ACTUELLE du compte) ; ses brouillons et ses textes envoyés restent |

### 20.2 Anti-invention

| constat | correction |
|---|---|
| Unités courtes et ordinaux (« 3e », « 30t », « 48h ») : clé d'une lettre cherchée en début de mot ; tout mot en « e », « t », « h » près du même nombre appuyait le fait (« 3 électriciens » appuyait « la 3e intervention », y compris en mode « raccourci », présenté comme « repris du texte de départ ») | `faits_a_relire._unit_key` : t → tonne, h → heure, j → jour, min/mn → minute ; un ordinal a sa clé (`ORDINAL`) et n'est appuyé que par un ordinal (« 3e », « troisième », « 1er », « premier ») ; une clé courte ne vaut qu'en mot entier ; le nombre et son unité se rapprochent dans la MÊME phrase de la même source (la fenêtre ne traverse plus une fin de phrase ni une autre source : « 30 tuiles par heure. » puis « 48 habitants » n'appuient plus « 48h ») |
| Transitions : superlatifs et exclusivité (« le seul », « l'unique », « le meilleur »), périodes (« vacances scolaires », « avant l'été », « période estivale », « dès la signature du marché »), « sans aucune sous-traitance », « en horaires décalés », « en astreinte » passaient | `controle_transition` : superlatifs, exclusivité et renommée (seul, unique, meilleur, la référence, le plus/la plus…, spécialiste, reconnu…), périodes de l'année et délais comptés depuis un acte du marché, totalité et constance (aucun, entièrement, toujours, jamais…), organisation du travail (astreinte, permanence, horaires décalés, sous-traitance, délais) ; consigne de l'harmonisation précisée (moins de phrases payées puis jetées) |
| Les locutions « dans un second temps », « en premier lieu », « le premier volet » étaient refusées comme des rangs (phrases payées puis jetées) | Retirées avant la recherche d'un rang (`_CONNECTEURS_RANG` : lieu, temps, volet, point, axe, aspect, chapitre, partie, section…) ; « le premier désamianteur » reste refusé ; une liste de bonnes transitions doit passer (tests) |

Suggestion non retenue : inverser la règle des transitions (refuser tout mot absent du dossier hors d'une courte liste
de connecteurs). Le vocabulaire d'une transition est ouvert (« s'agissant », « retenue », « précise », « détaille ») :
la plupart des bonnes phrases seraient refusées, donc payées puis jetées, contre la règle d'Eliot (économiser l'IA sans
baisser la qualité). La liste des mots qui portent un fait est élargie à la place, et chaque partie touchée reste « à
revalider » par son auteur.

### 20.3 À dire à Eliot (choix faits par défaut)

1. Un partenaire qui a commencé à rédiger par son lien (sans adresse) et veut passer à son compte le fait depuis le
   même navigateur ; sinon il réinitialise d'abord son espace sur l'autre appareil (ses brouillons non envoyés sont
   effacés). C'est ce qui empêche le chef de file, qui a le lien, de prendre l'espace par un second compte.
2. Relire un fait de la partie envoyée demande le code reçu par email (lien qui vise une adresse), comme envoyer.
3. Les transitions refusent davantage de mots (superlatifs, périodes, organisation du travail) ; les locutions qui ne
   classent rien passent.

### 20.4 Vérifications

- `tests/test_redaction_v4_contre_relecture.py` : 10 tests sur 11 échouaient sur `6a040d2` (reproduction de chaque
  remarque), tous passent. Trois tests existants suivent la nouvelle règle sans être affaiblis : le rattachement se
  fait depuis le navigateur qui a la clé (`test_isolation_entre_deux_groupements`,
  `test_harmoniser_ne_transmet_jamais_le_cv…`) ; « clé prise avant le rattachement » joué sur un lien qui vise
  l'adresse du compte (`test_cle_prise_avant_le_rattachement_ne_vaut_plus`).
- Suite complète verte (SQLite) : 1 619 tests ; empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check`
  sur `app.js`, `redaction-partenaire.js` et le script de `invite.html`.
- Postgres 16 depuis l'état EXACT de la production — `d6504e4` puis `0767372` (même tête `w7x8analysepartagee`) —
  script `scratchpad/pgtest/run_v4_contre_relecture_depuis_prod.py` (TZ=UTC) : données créées par le code de
  production, une seule révision appliquée (`x8y9redactionv4`), aucune donnée perdue, seconde montée et rejeu forcé
  sans effet, code de production redémarré sur la base montée, schéma identique à une base neuve, retour arrière et
  remontée : tous verts. Tests rejoués sur la base montée depuis `0767372` : 974, dont 972 verts ; les deux échecs
  existent à l'identique sur `6a040d2` (même liste, même base) et ne touchent pas ce chantier :
  `test_hotfix_v2_fuites.py::test_fourche_historique_toleree_alteration_detectee` (déjà connu, propre à SQLite) et
  `test_reseau_partenaires.py::test_cron_borne_et_jamais_de_depublication_sur_erreur` (dépend de l'ordre quand toute la
  liste partage une base Postgres ; le fichier seul passe en entier, 24 tests sur 24).


## 21. Documents privés déposés par le lien (décision 5, option a — validée par Eliot)

Un partenaire venu par **lien magique, sans compte**, dépose ses propres documents (anciens mémoires, plaquette,
références, attestations…) pour que l'aide d'Adjugo rédige SES parties à partir d'eux. Code : `app/services/depot_lien.py`
(seul point d'écriture de ces tables), branché dans `atelier_groupement` (`ContextePartenaire`, `fiches_depot_par_lien`,
`oublier_document`, retrait, réinitialisation, effacement, export) ; routes : `app/routers/atelier_groupement.py` ; écran :
`app/static/redaction-partenaire.js` (« Vos documents pour Adjugo », styles `.rp-docs`) ; migration
`alembic/versions/y9z0depotlien_documents_par_lien.py` ; tests : `tests/test_redaction_v4_depot_lien.py` ; mention
juridique à faire valider : `docs/A_VALIDER_depot_documents_par_lien.md` (les pages juridiques ne sont pas modifiées).

### 21.1 Modèle (migration `y9z0depotlien`, aucune clé étrangère : effacement explicite et ordonné)

| table | une ligne par | colonnes |
|---|---|---|
| `depots_lien_espaces` (`DepotLienEspace`) | invitation (`invite_id` UNIQUE) | `consentement` `{cgu: {version, mise_a_jour, empreinte, adresse}, confidentialite: {…}, accepte_le}`, `accepte_le`, `resultat_le` (résultat du marché constaté par la purge), `project_id`, `owner_id` |
| `depots_lien_documents` (`DepotLienDocument`) | document déposé | `invite_id`, `project_id`, `owner_id`, `nom`, `file_key`, `taille`, `type_mime`, `empreinte` (sha256 du fichier), `caracteres`, `lecture` (`texte` · `scan`), `complet`, `morceaux`, `lignes_cv_retirees` |
| `depots_lien_morceaux` (`DepotLienMorceau`) | passage cherchable | `document_id`, `invite_id`, `ordinal`, `texte` |

- Rattachés à **l'invitation**, jamais à l'organisation du chef de file. `owner_id` (tenant du marché) ne sert qu'à faire
  partir les lignes avec le marché (et suit l'organisation : membre effacé, transfert de propriété) ; il ne donne aucun
  droit de lecture.
- Fichier : `invitations/<invite_id>/depots/<uuid><ext>` (jamais sous le préfixe du chef de file), type servi tiré de
  l'extension (`app.core.mime`), téléchargé en pièce jointe, `nosniff`, `no-store`, par l'API (jamais une adresse signée :
  la clé de l'espace ne voyage que dans l'en-tête).
- Le texte lu n'est pas gardé en entier : seulement ses passages, CV retirés (minimisation).

### 21.2 Qui voit quoi

| | Le partenaire (lien + clé) | Le compte qui a rattaché le lien | Le chef de file et son organisation | Les autres membres | Démo |
|---|---|---|---|---|---|
| Liste, fichiers, noms, passages | oui | télécharger, supprimer (plus utilisés) | jamais : 403 `cle_espace_requise` par le lien sans clé, 404 par un compte | jamais : 404 `document_introuvable` | rien à déposer (403 `demo`) |
| Faits « trouvés dans vos documents » avec le passage exact | oui (son brouillon) | oui (ses brouillons écrits par le lien) | compteurs par type seulement (`par_type.documents`) | compteurs, dans le dossier assemblé | — |
| Journal | ses actions, sans nom de document | idem | les mêmes entrées : qu'un document a été déposé ou supprimé, que les conditions ont été acceptées (heure, adresse IP) — jamais le nom, le rang, la taille ni le contenu d'un document (§ 21.14) | — | — |

Jamais dans : l'atelier, « Qui écrit quoi », le dossier assemblé, l'export Word/PDF, « Mes documents », le coffre croisé,
l'aperçu et l'export ZIP du dossier, l'export RGPD du chef de file, le journal (le journal du lien se lit avec le lien
seul : aucune entrée ne porte un nom de document).

### 21.3 Routes

Lien : `/api/invite/{token}/redaction/documents…` (clé `X-Adjugo-Espace` exigée) ; compte : `/api/shared/{pid}/redaction/
documents…` (lecture, téléchargement, suppression ; aucun dépôt : 405). Erreurs : `detail = {code, message, …}`.

| route | effet | erreurs |
|---|---|---|
| `GET /documents` | `{documents: [{id, nom, taille, depose_le, lecture, lecture_libelle, complet, caracteres, passages, passages_cv_retires}], utilises, peut_deposer, qui_voit, usage, conservation, message, conditions: {a_accepter, acceptees_le, textes: [{cle, titre, adresse, version, mise_a_jour, empreinte}], message} \| null, limites}` | 403 `cle_espace_requise` |
| `POST /documents` (lien) multipart `file`, `accepte_cgu`, `accepte_confidentialite` | 201 : la même vue + `depose` | 409 `conditions_a_accepter` (`conditions`), 403 `identity_unverified`, `depot_par_le_compte`, `co_construction_fermee`, `demo` ; 422 `type_refuse`, `fichier_vide`, `fichier_invalide` (signature), `document_illisible`, `document_cv`, `piece_acheteur` ; 413 `fichier_trop_lourd` ; 409 `trop_de_documents`, `espace_plein`, `document_deja_depose` ; 429 `trop_de_depots` ; 503 `stockage_indisponible` |
| `GET /documents/{did}/fichier` | le fichier tel qu'il a été déposé | 404 `document_introuvable`, 410 `fichier_absent` |
| `DELETE /documents/{did}` | supprimé (toujours possible, même co-construction fermée) ; vue rendue | 404, 403 `demo` |

`GET …/redaction` porte `documents: {nombre, utilises, possible}` (null sans la clé). `message_mode` (lien) dit que
l'aide s'appuie aussi sur « Vos documents pour Adjugo ».

### 21.4 Accord au premier dépôt

- Les deux textes EXISTANTS : `/cgv` (« Conditions générales de vente et d'utilisation ») et `/confidentialite`. Leur
  version et leur date sont lues dans la page publiée (« Version : 1.2 — Dernière mise à jour : … »), avec l'empreinte
  du fichier (16 caractères du sha256) : `depot_lien.textes_juridiques`.
- Premier dépôt sans les deux cases : 409 `conditions_a_accepter`, rien n'est gardé. Avec : `consentement` horodaté
  (versions, dates, empreintes, adresses) et entrée chaînée `redaction.documents_conditions` (« … version 1.2 … version
  1.3 … »). Une nouvelle version de l'un des textes redemande l'accord avant le dépôt suivant
  (`MSG_CONDITIONS_NOUVELLES`).
- Accepter et déposer engagent la personne : même exigence d'identité qu'envoyer (`identity_unverified` quand le lien
  vise une adresse pas encore prouvée). Celui qui a seulement réinitialisé l'espace ne dépose rien au nom du partenaire.
- Réinitialiser l'espace efface l'accord avec les documents : le nouvel espace redonne son accord.

### 21.5 Lecture sans IA ; jamais un CV ; jamais une pièce de l'acheteur

- Couche texte des PDF, Word (.docx), OpenDocument (.odt), texte (.txt), avec les plafonds d'Adjugo (temps, pages,
  archives bornées : `app.services.analysis`). Un PDF scanné est lu par la reconnaissance de caractères **locale**
  (tesseract, comme les dossiers d'acheteurs), sur ses `DEPOT_LIEN_PAGES_SCAN` premières pages. **Aucune lecture n'appelle
  l'IA** : rien à décompter (si une lecture par l'IA était un jour ajoutée, elle passerait par `facturer_aide_partenaire`,
  la seule fonction de facturation, avec le remboursement en cas d'échec).
- Un document qui ressemble à un CV (nom, titre, contenu : `fiches_import.est_cv`) **n'est pas gardé** (422
  `document_cv`) : Adjugo ne l'enverrait jamais à l'IA. Dans un autre document, les lignes de CV (`lignes_privees`) sont
  vidées AVANT le découpage, et tout passage qui ressemble encore à un CV est écarté (au découpage puis à la recherche).
  Un CV écrit sans le mot « CV » est reconnu à sa forme (`_cv_sans_titre`, § 21.14) : un nom seul sur sa ligne, puis des
  rubriques de CV écrites seules sur leur ligne (« EXPÉRIENCE », « FORMATION », « COMPÉTENCES », « Parcours »,
  « Atouts »…), proches les unes des autres. Une plaquette écrite avec « nous », « notre », « nos » n'en est jamais un,
  même sous un nom qui commence par un prénom ou suivi de son métier (§ 21.15).
- Une pièce du dossier d'un acheteur (règlement, CCAP, CCTP : `est_piece_acheteur`) n'est pas gardée (422
  `piece_acheteur`) : elle ne dit rien de l'entreprise.

### 21.6 L'aide de l'IA de SES parties

- `ContextePartenaire.depots` (`depot_lien.utilises`) : vrai par le lien tant qu'il n'est pas rattaché à un compte. Alors
  `extraits()` = `depot_lien.rechercher` : BM25 sans IA sur SES passages seulement, avec le filtre de pertinence du
  savoir-faire ; jamais `rag.retrieve_multi`, jamais un passage d'un autre membre ni du chef de file.
- Ce que l'IA lit d'un document : le passage, sous un libellé neutre (« Votre document 2 ») — le nom réel, qui peut nommer
  une personne, ne part jamais ; les noms des personnes repérés dans les passages sont masqués (`pii_scope`, déjà posé par
  `_executer`). Par le lien, aucune équipe n'est connue : le repérage est ÉLARGI (`noms_probables(etendu=True)`) à tout
  « Prénom Nom » dont le prénom est courant (`fiches_import._PRENOMS`, français et bretons), jamais derrière un mot de
  lieu ou d'établissement (« école Jules Ferry », « rue Victor Hugo ») ; pour tous les parcours, une fonction suivie du
  nom sans ponctuation (« Notre gérant Pierre Martin »), « X, notre gérant », « assuré / réalisé / fondée (en 2009) /
  créée par X et Y ». Un repérage sans IA ne trouve pas tout : l'écran le dit (« il masque les noms de personnes qu'il
  repère … retirez de vos documents les noms que vous ne voulez pas transmettre »).
- `fiches_depot_par_lien(db, inv, chunks)` → `FicheDepot` `[S#]` : `documents` / « trouvé dans vos documents », passage
  exact autour du fait ; la source garde `doc_nom`, `extrait`, `depot_id`, `depot_chunk_id` (privés). `sources_reelles`
  remet le nom réel et le passage dans les extraits cités du brouillon ; `fiches_de_brouillon` relit les passages cités
  (sources et faits) pour contrôler de nouveau un brouillon (« J'écris moi-même », valider un texte du chef de file).
- Le chef de file reçoit, avec le texte envoyé, les compteurs par type (`documents`), jamais une source.
- Coût : la rédaction reste facturée par `facturer_aide_partenaire` (quota du chef de file, portée `inv:<id>`, plafond par
  partie, remboursée si l'IA tombe) ; le dépôt et la lecture ne coûtent rien.
- Lien rattaché à un compte : son compte utilise ses propres documents et preuves (inchangé) ; ce qu'il avait déposé par
  le lien n'est plus utilisé (`utilises: false`, `MSG_COMPTE`), il peut le télécharger ou le supprimer depuis son compte.

### 21.7 Limites réglables (variables d'environnement, défauts)

| variable | défaut | sens |
|---|---|---|
| `DEPOT_LIEN_FICHIERS` | 10 | documents gardés par invitation |
| `DEPOT_LIEN_MO` | 10 | taille d'un fichier (lecture bornée : jamais plus que la limite + 1 octet en mémoire) |
| `DEPOT_LIEN_MO_TOTAL` | 50 | total des fichiers gardés par invitation |
| `DEPOT_LIEN_PAR_JOUR` | 30 | dépôts sur 24 h glissantes, supprimés compris (anti-abus ; plus 30/heure par adresse IP sur la route) |
| `DEPOT_LIEN_TYPES` | `.pdf,.docx,.odt,.txt` | types acceptés : on peut en retirer, jamais en ajouter un qu'Adjugo ne lit pas sans IA |
| `DEPOT_LIEN_PAGES_SCAN` | 10 | pages d'un scan lues (reconnaissance locale) |
| `DEPOT_LIEN_CARACTERES` | 200 000 | texte lu par document |
| `DEPOT_LIEN_CONSERVATION_MOIS` | 6 | conservation après le résultat du marché (ou les replis, § 21.8) |

Contrôles du fichier : extension en liste blanche, signature (`%PDF-`, archive `PK` pour .docx/.odt, aucun octet nul
pour .txt), archives bornées avant lecture, doublon refusé (empreinte), limites relues sous verrou de l'invitation avant
l'écriture. Il n'y a pas d'antivirus dans Adjugo aujourd'hui (aucun contrôle de ce type à réutiliser) : le fichier n'est
jamais exécuté, jamais servi en ligne, seulement rendu à son déposant en pièce jointe.

### 21.8 Suppression et conservation

| événement | effet |
|---|---|
| Le partenaire supprime un document | fichier, passages et ligne ; dans ses brouillons, les extraits cités de ce document sont retirés et leurs faits redeviennent « à relire » (`oublier_document`) ; le texte envoyé ne change pas ; journal `redaction.document_supprime` |
| Invitation retirée par le chef de file, ou déclinée | tout est effacé (`retirer_invitation`), journal `redaction.documents_effaces` |
| Réinitialisation de son espace | tout est effacé SANS être lu, accord compris ; `documents_effaces` dans la réponse, compté dans le journal ; l'écran et les messages le disent avant (« vos brouillons non envoyés et vos documents déposés pour Adjugo seront effacés ») |
| Dans TOUS ces cas et à la purge | `effacer_invitation` retire aussi des brouillons ce qu'ils ont recopié de ces documents (`oublier_documents` : nom du document et passage des sources ; faits reliés « à relire ») : rien ne survit au document |
| Purge quotidienne (`POST /api/admin/run-trash-purge`, `depot_lien.purger`) | **6 mois après le RÉSULTAT du marché** (gagné, perdu, abandonné : date constatée par la purge, celle de la dernière modification du marché, `resultat_le`) ; un résultat retiré remet le compteur à zéro ; à défaut, 6 mois après la date limite ; à défaut, 6 mois après le dernier dépôt ; lien expiré depuis 30 jours ; invitation retirée ou déclinée (filet) ; marché disparu. Journal `redaction.documents_effaces` (« … automatiquement : 6 mois après le résultat du marché ») |
| Compte du chef de file effacé, corbeille des marchés purgée | lignes et fichiers partent avec le marché (`effacer_dossiers` → `effacer_projets`, clés relevées par `cles_projets` avant) |
| Compte du partenaire effacé | ce qu'il a déposé par le lien reste à l'invitation (comme ses brouillons écrits par le lien), purgé par les règles ci-dessus |
| Export RGPD du chef de file | jamais |
| Portabilité (lien ou compte) et export RGPD de son compte | `documents_deposes` : la liste (nom, taille, date, lecture) et l'accord ; chaque fichier se télécharge par `GET /documents/{did}/fichier` |

Journal du membre (`journal_membre`, entrées propres à l'invitation, hors `GROUP_EVENTS` : la version
« adjugo-journal-membre-v1 » ne change pas) : « Vous avez accepté les conditions d'utilisation et la politique de
confidentialité pour déposer vos documents », « Vous avez déposé un document dans votre espace privé », « Vous avez
supprimé un document de votre espace privé », « Vos documents déposés pour Adjugo ont été effacés » (avec la raison).

### 21.9 Démo

Le lien partenaire de la démo est refusé dans la route AVANT tout (`_par_lien(…, ecrire=True)`, 403 `demo`) pour déposer
et supprimer ; le service le refuse aussi (`_invite_is_demo`). Garde central : `POST /api/invite/{token}/redaction/documents`,
`DELETE /api/invite/{token}/redaction/documents/{did}` et `DELETE /api/shared/{pid}/redaction/documents/{did}` (une session
démo), plus `refuser_demo` dans la route du compte. `tests/test_demo_sans_cout.py` : le dépôt dans `COUTS` (fichier, lien
de la démo, refusé, aucun fichier rangé), les deux suppressions dans `SANS_COUT`.

### 21.10 Écran « Vos documents pour Adjugo »

Dans la carte « Mes parties du dossier de présentation », sous l'espace privé, seulement avec la clé valide (par le compte :
seulement s'il reste des documents déposés par le lien). Titre et bulle (i) : « Seuls vous et Adjugo les lisez ; le chef de
file ne les voit jamais. », ce que reçoit le chef de file (le nombre de faits « trouvés dans vos documents »), lecture sans
IA, passage exact, noms de personnes repérés masqués et ce qui ressemble à un CV écarté (avec le conseil de retirer les noms
à ne pas transmettre), durée de conservation (texte du serveur, date d'expiration du lien comprise). Liste : nom (échappé), taille,
date, « Lu sans IA (texte du document) » ou « (document scanné, reconnaissance de caractères) », « Lu en partie »,
« passages en forme de CV retirés » ; « Télécharger » (fichier reçu avec la clé en en-tête, jamais une adresse) et
« Supprimer » (confirmation : passages cités retirés des brouillons, faits « à relire », textes envoyés inchangés). Dépôt :
au premier, deux cases « J'accepte les conditions d'utilisation (version 1.2) » et « J'accepte la politique de
confidentialité (version 1.3) », liens vers `/cgv` et `/confidentialite` (nouvel onglet) ; sélecteur de fichier limité aux
types du serveur ; limites dites en clair ; code par email si l'invitation vise une adresse (même parcours que l'envoi).
« Télécharger mes textes » dit que l'export contient aussi la liste des documents et l'accord. 375 px : une colonne, boutons
pleine largeur (règles `.rp-acts` existantes).

### 21.11 Limites connues (dites honnêtement)

- Lien sans adresse : celui qui ouvre l'espace le premier est « le partenaire » (§ 13) ; il peut déposer et accepter les
  conditions. Le vrai partenaire qui réinitialise l'espace efface tout sans le lire ; c'est inscrit au journal.
- La date du résultat n'est pas enregistrée par Adjugo au moment où le statut change : la purge la constate (première
  fois qu'elle voit le marché gagné, perdu ou abandonné) en prenant la date de la dernière modification du marché, au plus
  tard le jour où elle passe. Une modification du marché faite entre le résultat et ce passage décale un peu le départ des
  6 mois (vers plus tard, jamais plus tôt).
- Les liens d'invitation expirent par défaut après 30 jours : les documents partent alors 30 jours après l'expiration,
  souvent avant les 6 mois après le résultat (le partenaire n'y a plus accès de toute façon). L'écran le dit, avec la
  date d'expiration du lien (`depot_lien.conservation`).
- Le repérage des noms et des CV est sans IA : un nom écrit d'une façon inhabituelle (prénom rare, initiale) ou un CV
  sans nom en tête ni rubriques écrites seules sur leur ligne peut lui échapper (un prénom rare sous lequel ne viennent
  que deux rubriques, sans coordonnées ni ligne de parcours, aussi). L'écran ne promet pas plus (§ 21.6).
- Reconnaissance de caractères locale : un scan de mauvaise qualité peut être mal lu, ou refusé (« aucun texte lisible ») ;
  seules les premières pages d'un long scan sont lues (« Lu en partie »).
- Le repérage d'un CV ou d'une pièce de l'acheteur est celui de la vague 3 (sans IA) : un mémoire fait surtout de CV peut
  être refusé ; il se redépose sans ses CV.
- Supprimer un document ne change pas les textes déjà envoyés : leurs compteurs disent ce qui était vrai à l'envoi.
- Après un retour arrière de la migration, les fichiers restent dans le stockage sans plus aucun accès (à supprimer à la
  main sous `invitations/*/depots/` si le retour arrière est définitif).
- Les noms des fichiers sont gardés (le partenaire les voit) ; ils ne sont jamais montrés au chef de file ni à l'IA.

### 21.12 À dire à Eliot (choix faits par défaut)

1. **Un CV n'est pas gardé** (refusé au dépôt) plutôt que gardé sans être envoyé : il ne servirait à rien ici, et c'est
   une donnée d'un salarié (minimisation). Une pièce du dossier de l'acheteur n'est pas gardée non plus.
2. **Limites** : 10 documents, 10 Mo chacun, 50 Mo au total, 30 dépôts par jour, PDF / Word / OpenDocument / texte, scans
   lus sur 10 pages — toutes réglables sans code.
3. **Troisième repli de conservation** : ni résultat ni date limite → 6 mois après le dernier dépôt (sinon la durée
   n'aurait aucune borne).
4. **Lien rattaché à un compte** : les documents déposés par le lien ne servent plus (le compte utilise son savoir-faire,
   inchangé) ; il peut les télécharger et les supprimer depuis son compte ; ils partent avec les règles ci-dessus.
5. **Accord redemandé** dès qu'une version de l'un des deux textes change ; **code par email** avant le premier dépôt quand
   l'invitation vise une adresse (comme pour envoyer).
6. La phrase de la bulle est écrite « Seuls vous et Adjugo les lisez » (accord du pluriel).
7. **Pages juridiques** : elles ne couvrent pas ce cas (le partenaire n'est pas un « Client » ; rôle d'Adjugo, durée de
   conservation) : brouillon des mentions à ajouter dans `docs/A_VALIDER_depot_documents_par_lien.md`, à faire valider.
8. **Aucune IA à la lecture** : la reconnaissance de caractères est locale ; rien n'est décompté au partenaire ni au chef de
   file pour un dépôt.

### 21.13 Vérifications

- `tests/test_redaction_v4_depot_lien.py` (15 tests) : accord exigé au premier dépôt (versions 1.2 et 1.3, empreintes,
  horodatage, journal chaîné), puis lecture sans IA d'un texte, d'un Word et d'un PDF (aucun appel à l'IA, rien de
  décompté) ; aide de l'IA sur SES passages seulement (`rag.retrieve_multi` jamais appelé), nom réel du document et noms
  des personnes jamais envoyés, fait « trouvé dans vos documents » avec le passage exact, gardé quand il réécrit son
  texte ; chef de file : compteurs seulement ; cloisonnement (chef de file avec le lien sans clé : 403 ; chef de file et
  membre de son organisation par leur compte, même rattaché : 404 ; autre partenaire : 404 ; rien dans l'atelier, « Qui
  écrit quoi », le dossier assemblé, « Mes documents », le coffre croisé, l'aperçu et le ZIP du dossier, l'export RGPD, le
  journal) ; démo (lien et session, avec et sans le garde central) ; CV refusé (par le nom, par le contenu), passages de
  CV retirés d'un mémoire et jamais envoyés, pièce de l'acheteur refusée ; IA en panne : aide rendue, rien débité ;
  limites (types, vide, signature, illisible, doublon, taille, total, nombre, par jour supprimés compris, types réglables
  sans jamais en ajouter) ; accord redemandé à une nouvelle version, code exigé quand le lien vise une adresse ;
  télécharger (octets identiques, pièce jointe, `nosniff`, `no-store`), portabilité, supprimer (brouillons nettoyés, fait
  « à relire ») ; effacés au retrait, au déclin, à la réinitialisation (sans être lus, accord compris) ; purge : 6 mois
  après le résultat (horloge simulée : rien la veille, tout le lendemain ; résultat retiré : compteur remis à zéro), date
  limite (par la route du cron, secret exigé), dernier dépôt, lien expiré depuis 30 jours (pas avant), corbeille des
  marchés, compte du chef de file effacé ; lien rattaché à un compte (plus utilisés, téléchargeables, supprimables, aucun
  dépôt) ; migration SQLite (base neuve, valeurs par défaut, retour arrière, remontée, rejeu) ; écran (règles, fonctions
  pures sous Node).
- Suite complète verte (SQLite) : 1 635 tests (1 619 + 16) ; `tests/test_demo_sans_cout.py` classe les trois routes
  d'écriture ; empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check` sur `redaction-partenaire.js`,
  `app.js` et le script de `invite.html`.
- Navigateur réel (aperçu local, base de travail remplie par `scratchpad/depot/seed_live.py`), 375 px : la carte « Vos
  documents pour Adjugo » dans l'espace privé, aucun défilement horizontal ; bulle (i) complète ; cases et liens vers `/cgv`
  et `/confidentialite` ; « Déposer » sans fichier : message sur place ; dépôt depuis le navigateur (clé en en-tête,
  formulaire) : « Document déposé et lu sans IA… », cases disparues ; « Supprimer » : fenêtre de confirmation, « Document
  supprimé. » ; aucune erreur dans la console.
- Postgres 16 depuis l'état EXACT de la production (`a7f48d2`, tête `x8y9redactionv4`), script
  `scratchpad/pgtest/run_depot_lien_depuis_prod.py` (TZ=UTC) : données créées par le code de production (atelier, « Qui
  écrit quoi », espace du lien ouvert, brouillon privé du partenaire, tâche), une seule révision appliquée
  (`y9z0depotlien`), aucune donnée perdue, seconde montée et rejeu forcé sans effet, dépôt par le lien avec le code nouveau
  sur la base montée, code de production redémarré sur la base montée (lectures et écriture : 200), schéma identique à une
  base neuve (0 écart de colonnes, 0 d'index), retour arrière (trois tables retirées, rien d'autre ne bouge, code de
  production toujours vert) et remontée. Tests rejoués sur la base montée : les 15 tests des documents déposés verts ;
  les seuls échecs sont dans des fichiers propres à SQLite (`PRAGMA foreign_keys` : `test_secu_rgpd.py`,
  `test_secu2_donnees.py`, et leurs suites dans le même processus) et les deux déjà connus (§ 20.4). Contre-épreuve,
  `scratchpad/pgtest/compare_prod_depot_lien.py` (base neuve par code) : ces fichiers donnent exactement les mêmes échecs
  avec le code de production ; et 20 fichiers (vague 4, démo, atelier, preuves, co-traitance, convention, fichiers,
  durcissement, réseau) : 574 verts sur 575 avec le code nouveau, 573 sur 574 avec la production, le même seul échec
  (`test_hotfix_v2_fuites.py::test_fourche_historique_toleree_alteration_detectee`, déjà connu).

### 21.14 Contre-relecture du dépôt par lien

Douze remarques des relectures (cloisonnement et RGPD, IA et coûts, exactitude de l'écran), chacune reproduite sur
`1a9f2f4` puis corrigée avec un test qui échouait avant (`tests/test_redaction_v4_depot_lien_relecture.py`). Le premier
correcteur a été coupé par une limite d'utilisation (son travail en cours : `7459fed`) ; la reprise a relu ce travail,
l'a gardé, l'a rejoué (15 tests sur 17 en échec sur `1a9f2f4`, tous verts ensuite ; les deux autres verrouillent ce qui
était déjà juste : réinitialisation et retrait sans reste, espace rouvert avec le code pendant l'aide) et l'a complété
(3 tests de plus et 2 tests renforcés, en échec sur `7459fed` : CV au prénom rare, plaquette et mémoire jamais pris pour
un CV, lieu derrière un article élidé, phrase de conservation, message des nouvelles conditions). 20 tests en tout.

**Constats et corrections**

1. *La purge laissait dans les brouillons le nom réel et le passage exact* (deux remarques, cloisonnement et IA : lien
   sans expiration ou valable longtemps, aucune autre règle n'efface les brouillons d'une invitation active ; le fait
   restait « trouvé dans vos documents » sans document). `effacer_invitation` — appelé par la purge, le retrait, le
   déclin et la réinitialisation — appelle désormais `oublier_documents` (tous les documents de l'invitation) : nom et
   passage retirés des sources, faits reliés « à relire ». Test : purge à 6 mois du résultat, aucun reste dans aucune
   table ni dans le stockage, le fait repassé « à relire » à l'écran.
2. *Réinitialisation pendant l'aide de l'IA* : la tâche rangeait son brouillon (nom et passages des documents que la
   réinitialisation venait d'effacer « sans être lus ») dans le nouvel espace. La réinitialisation marque, sous le
   verrou de l'invitation, les tâches en cours de l'invitation (`ESPACE_REINITIALISE` dans leur résultat interne,
   jamais montré : les clés « _… » ne sortent pas) ; la tâche relit la sienne sous le même verrou avant de ranger :
   marquée, elle ne range rien (« Votre espace privé a été réinitialisé pendant la rédaction : le texte n'a pas été
   gardé. », partie libérée). Marquée avant de démarrer, elle n'appelle pas l'IA : aide rendue, rien débité. Rouvrir
   l'espace avec le code reçu par email (brouillons gardés, même partenaire) ne marque rien : le brouillon est rangé et
   se lit avec la nouvelle clé. (Garder l'empreinte de l'espace dans la tâche, autre voie proposée, aurait aussi arrêté
   ce cas légitime.)
3. *Réinitialisation pendant la lecture d'un dépôt* : le document était rangé et lisible avec la nouvelle clé, sans
   accord. Après la lecture, sous le verrou de l'invitation relue, la clé présentée (gardée dans `Acces.cle`) doit encore
   ouvrir l'espace, le dépôt être permis et l'accord être enregistré et à jour ; sinon 409 `espace_reinitialise`, ni
   fichier ni ligne.
4. *Document supprimé pendant l'aide* : le brouillon gardait son nom et son passage. Après l'IA, `encore_presents` ne
   garde que les passages encore présents (un passage disparu devient « retiré » à sa place : les renvois [S#] des
   autres ne bougent pas, `fiches_depot_par_lien` numérote par la place) ; `sources_reelles` n'en fait aucune source.
5. *Ordre des écritures* : déposer, supprimer, réinitialiser, retirer, effacer et ranger le brouillon d'une aide prennent
   d'abord le verrou de l'invitation (`depot_lien.verrouiller_invitation`, une ligne) : sur Postgres, l'un passe après
   l'autre et voit son effet (pas d'interblocage : chacun le prend en premier, aucun ne le demande en tenant déjà le
   verrou d'une partie ou d'une répartition).
6. *Journal du marché* : le rang (« 2 sur 10 ») et la taille ne sont plus écrits ; reste « Document déposé dans l'espace
   privé du partenaire, lu sans IA ». Le reste de la remarque est un choix laissé à Eliot (ci-dessous).
7. *Noms des personnes envoyés à l'IA par le lien* (« Notre gérant Pierre Martin », « assuré par Gwenola Riou et Loïc
   Cadiou », « Fondée en 2009 par… », « Jean-Marc Riou pilote… ») : repérage élargi (§ 21.6), un mot d'ouverture pris
   avec le nom (« Avec Thomas Le Bihan ») n'est plus masqué avec lui, et (reprise) un article élidé devant un lieu
   (« l'espace Pierre Loti », « l'école Anne Frank ») le laisse lu comme un lieu, devant une personne (« l'aide d'Anne
   Le Floch ») la laisse masquée. Le texte qui n'est pas un nom part toujours (vérifié dans le test).
8. *L'écran promettait un masquage complet* (bulle, `MSG_USAGE`, brouillon juridique) : il dit maintenant « Avant l'IA,
   il masque les noms de personnes qu'il repère et écarte ce qui ressemble à un CV : retirez de vos documents les noms
   que vous ne voulez pas transmettre. » ; le brouillon juridique est nuancé de même (et signale que la phrase publiée du
   § 6 de la politique est aussi trop absolue pour les Clients).
9. *Un CV classique sans le mot « CV » était gardé et envoyé* : `fiches_import._cv_sans_titre` (dans `lignes_privees`,
   donc aussi pour le savoir-faire d'un compte) reconnaît un nom seul sur sa ligne suivi, à moins de 8 lignes, de
   rubriques de CV écrites seules sur leur ligne, chacune à moins de 15 lignes de la précédente, jamais au-delà d'un
   titre numéroté (« 2. Moyens matériels ») : nom d'une PERSONNE (prénom courant, ou nom suivi de sa fonction) avec deux
   sortes de rubriques ; autre nom propre (prénom rare : « Gwenhaël KERJEAN », reprise) avec trois sortes, ou deux plus
   des coordonnées sous le nom et une ligne de parcours (« 2015 - 2024 … »), et jamais à la première personne du pluriel.
   Un document fait surtout de cela est refusé (422 `document_cv`, PDF, Word ou texte, nom de fichier neutre) ; inséré
   dans un mémoire, il en est retiré. Ni une plaquette (« Breizh Désamiantage », « Compétences », « Formations » ; ou
   trois rubriques écrites avec « nous », « nos »), ni le corps d'un mémoire entre deux rubriques éloignées ne sont
   retirés (reprise : la première version allait jusqu'à 80 lignes plus loin chercher la seconde rubrique).
10. *Réinitialiser ne disait pas que les documents partent* : la fenêtre de confirmation, le paragraphe de l'espace,
    `MSG_ESPACE_OUVERT` et `MSG_RATTACHER_ESPACE` le disent (et la fenêtre dit que l'accord part aussi).
11. *Durée de conservation incomplète* : `conservation(inv, mois)` dit les règles de la purge, l'expiration du lien
    comprise, avec sa date : « Ils sont effacés dès que vous les supprimez, si votre espace privé est réinitialisé, si
    vous quittez le groupement ou en êtes retiré ; sinon automatiquement à la première de ces deux dates : 30 jours après
    l'expiration de ce lien (il expire le 18 novembre 2026), ou 6 mois après le résultat du marché (à défaut, après sa
    date limite ou, sans date limite, après votre dernier dépôt). » ; sans expiration, seulement la seconde règle.
12. *Nouvelles conditions publiées page ouverte* : le 409 `conditions_a_accepter` porte déjà `conditions` ; l'écran les
    recopie et redessine la carte : les deux cases apparaissent, avec « Cochez les deux cases, choisissez de nouveau
    votre document, puis déposez-le. » (la carte redessinée a perdu le fichier choisi).

**Rien de rejeté** : les douze remarques étaient fondées (deux décrivent le même reste de la purge). Ce qu'une relecture
donnait déjà pour juste l'est toujours : la suppression d'un document par le partenaire ne laisse rien.

**À dire à Eliot (choix faits)**

- *Journal* : le chef de file lit toujours, dans le journal du marché, qu'un document a été déposé ou supprimé et que les
  conditions ont été acceptées (heure, adresse IP, comme pour toute action du partenaire), sans nom, rang, taille ni
  contenu. Réserver ces entrées au seul partenaire, ou les regrouper sans heure, est un choix produit (le journal chaîné
  est la trace commune du groupement) : à trancher.
- *Aide perdue par une réinitialisation* : non remboursée et non rendue (l'IA a travaillé), comme une partie retirée
  pendant l'aide ; la rendre permettrait de faire travailler l'IA sans limite en réinitialisant à chaque aide.
- *Repérage des noms élargi au seul lien* (aucune équipe connue) ; les tournures contextuelles (fonction, « par … »)
  valent pour tous les parcours. Un lieu au prénom courant non précédé d'un mot de lieu (« Projet Victor Hugo ») peut
  être masqué par erreur : il est remis en clair dans le texte rédigé, l'IA lit seulement une étiquette à sa place.

**Vérifications**

- `tests/test_redaction_v4_depot_lien_relecture.py` : 20 tests, 15 en échec sur `1a9f2f4` et 5 sur `7459fed` (le
  travail coupé), tous verts. Les fichiers rangés y sont comparés avant / après (le dossier `uploads/` est partagé entre
  les suites lancées depuis le même dossier, et une base neuve reprend les mêmes numéros d'invitation : un fichier
  laissé par une autre suite faisait échouer à tort le contrôle « aucun fichier »).
- Suite complète verte (SQLite, TZ=UTC) : 1 655 tests (1 635 + 20), sur une copie propre des fichiers suivis.
- Empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check` sur `redaction-partenaire.js`, `app.js` et le
  script de `invite.html` ; aucune migration nouvelle (tête `y9z0depotlien`, celle du dépôt par lien).
- Navigateur réel, 375 px (aperçu local, base remplie par une copie de `scratchpad/depot/seed_live.py`) : bulle (i) de
  « Vos documents pour Adjugo » lisible en entier dans l'écran (durée de conservation avec la date d'expiration du lien) ;
  paragraphe et fenêtre « Réinitialiser votre espace privé ? » qui disent que les documents déposés et l'accord partent ;
  réponse 409 `conditions_a_accepter` simulée au dépôt : les deux cases apparaissent (« version 9.9 »), message
  « Cochez les deux cases, choisissez de nouveau votre document, puis déposez-le. » ; aucun défilement horizontal, aucune
  erreur dans la console.
- Postgres 16 depuis l'état EXACT de la production (`a7f48d2`, tête `x8y9redactionv4`), script
  `scratchpad/pgtest/run_depot_relecture2_depuis_prod.py` (copie de `run_depot_lien_depuis_prod.py`, TZ=UTC) : tous les
  contrôles de migration verts (données créées par le code de production, une seule révision `y9z0depotlien`, aucune
  donnée perdue, seconde montée et rejeu sans effet, dépôt par le lien sur la base montée, code de production redémarré :
  200 partout, schéma identique à une base neuve, retour arrière puis remontée) ; 38 fichiers de tests rejoués sur la base
  montée : 1 043 verts, et exactement les mêmes 37 échecs que sur `1a9f2f4` (fichiers propres à SQLite et les deux déjà
  connus, § 21.13). Base neuve, verrous `FOR UPDATE` réels (`scratchpad/pgtest/run_depot_relecture2_pg.py`) : 445 tests
  verts sur 445 avec le code nouveau (les 20 de la contre-relecture compris), 425 sur 425 avec `1a9f2f4`, aucun échec
  propre au code nouveau.

### 21.15 Contre-relecture de la reprise

Deux remarques, reproduites sur `31d384b` puis corrigées, avec 7 tests qui échouaient avant
(`tests/test_redaction_v4_depot_lien_contre_relecture.py`, en échec sur `31d384b` sous SQLite comme sous Postgres).

**Constats et corrections**

1. *Une plaquette prise pour un CV* (régression du § 21.14, point 9, qui touchait aussi les comptes : un document de
   « Mon savoir-faire » marqué « cv » est écarté en entier de l'aide de l'IA et montré comme un CV). « Simon Frères »
   (le nom commence par un prénom courant) ou « Breizh Toit » suivi de « Couvreur zingueur à Quimper depuis 1990 » (pris
   pour une fonction) passaient pour des noms de personne ; deux rubriques suffisaient alors, et la règle « une plaquette
   en nous / nos n'est jamais un CV » ne jouait pas. Corrections dans `fiches_import._cv_sans_titre` :
   - la voix de l'entreprise (« nous », « notre », « nos ») est cherchée dans le passage lui-même, du nom à la fin de la
     dernière rubrique (avant : jusqu'à trois lignes après la dernière rubrique, qui pouvaient être la suite d'un
     mémoire et faire manquer un CV), **quel que soit le nom** : une ligne suffit sous un nom propre quelconque, deux sous
     un nom de personne sûr (prénom courant ou intitulé de fonction) ;
   - sous un nom, une fonction n'est plus qu'un intitulé (`_intitule_de_fonction`) : au plus 6 mots, sans chiffre, lieu
     ni durée (« à », « au », « depuis », « dans », « sur », « pour », « chez ») ;
   - mots d'organisme ajoutés (un nom qui en contient un n'est ni une personne en tête d'un CV, ni un nom à masquer) :
     « Frères », « Fils », « Atelier(s) » et des métiers qui ne sont pas des noms de famille (toiture, isolation,
     façade, ravalement, carrelage, chauffage, climatisation, terrassement, paysage, élagage, nettoyage, étanchéité,
     démolition, désamiantage, dépollution, métallerie, serrurerie, assainissement, voirie, toit).
   Tests : trois plaquettes (« Simon Frères », « Breizh Toit », « Tanguy Kervella » en « nous ») déposées par le lien
   (201, aucun passage retiré) et lues pour un compte (`statut_document` sans « cv », aucune ligne retirée) ; deux vrais
   CV toujours refusés (un salarié présenté par son entreprise avec une seule ligne « chez nous », un intitulé de
   fonction sous un prénom rare).
2. *Une écriture du partenaire pendant une réinitialisation ou une suppression* (cloisonnement). « J'écris moi-même »
   (`enregistrer_brouillon`) et « Valider » le texte du chef de file (`valider_part`, brouillon « Texte du chef de file
   accepté par vous ») recopiaient les sources et les faits reliés lus avant une réinitialisation de l'espace ou la
   suppression d'un document survenue pendant la requête : avec la nouvelle clé, qui détient le lien lisait le nom et
   le passage d'un document privé ; un document supprimé restait cité. Trouvé en plus : « Relu par vous » sur un fait
   (`traiter_fait`) réécrivait ses faits lus avant la suppression, et remettait la source effacée. Corrections :
   - ces trois écritures prennent d'abord le verrou de l'invitation (`_verrou_du_lien`), avant ceux de la répartition et
     de la partie (même ordre que le § 21.14, point 5 : aucun interblocage) ; l'invitation relue doit être active et la
     clé présentée ouvrir encore l'espace ; sous Postgres, la réinitialisation ou la suppression attend la fin de
     l'écriture, puis efface ce qu'elle a rangé ;
   - juste avant d'écrire, le même contrôle est refait (une base sans verrou de ligne, comme SQLite, passe aussi par là)
     : clé qui n'ouvre plus l'espace → 409 `espace_reinitialise`, « Votre espace privé a été réinitialisé entre-temps
     (sur un autre appareil, par exemple) : rien n'a été enregistré. Ouvrez de nouveau votre espace privé sur cet
     appareil. » (l'écran garde la saisie et affiche le message, comme les autres refus) ; puis les sources et les faits
     à ranger ne gardent que les passages encore présents (`_sans_depots_disparus` : un fait relié à un passage disparu
     redevient « à relire », comme `oublier_documents`, dont la transformation est partagée).
   Tests (les courses lancent l'autre requête dans un autre fil, au milieu du contrôle des faits ou de la relecture, et
   l'attendent au plus 2 s : sous SQLite elle passe tout de suite et l'écriture la voit ; sous Postgres elle attend le
   verrou, environ 2,3 s par test) : réinitialisation pendant « Enregistrer » et pendant « Valider » (rien du document,
   ni pour la nouvelle clé, ni dans aucune table) ; suppression pendant « Enregistrer », « Valider » et « Relu par vous »
   (ni nom ni passage dans le brouillon, aucun reste dans aucune table).

**Rien de rejeté** : les deux remarques étaient fondées. La seconde existait déjà sur `1a9f2f4` (elle n'a pas été
introduite par la reprise, qui ne l'avait fermée que pour l'aide de l'IA et le dépôt).

**À dire à Eliot (choix faits)**

- *Plaquette sous un nom de personne* : il faut deux lignes en « nous / notre / nos » pour qu'un passage sous un nom de
  personne sûr (« Thomas Kervella », « Yann Tanguy » / « Conducteur de travaux ») soit lu comme une plaquette. Une
  plaquette d'entreprise individuelle qui ne dit « nous » qu'une fois reste prise pour un CV (écartée : perte de qualité,
  jamais de fuite) ; la règle inverse (une seule ligne) laisserait partir à l'IA la présentation d'un salarié écrite
  par son entreprise (« chez nous depuis 2012 »). Un CV n'est jamais envoyé à l'IA : le doute va au CV.

**Vérifications**

- `tests/test_redaction_v4_depot_lien_contre_relecture.py` : 7 tests, tous en échec sur `31d384b` (SQLite et Postgres),
  tous verts ; les tests de la relecture (dans le bac à sable, hors du dépôt) passent aussi.
- Suite complète verte (SQLite, TZ=UTC) : 1 662 tests (1 655 + 7).
- Empreintes SRI à jour (`scripts/sri_update.py --check`) et `node --check` : aucun fichier servi modifié ; aucune
  migration nouvelle (tête `y9z0depotlien`).
- Postgres 16, base neuve, verrous `FOR UPDATE` réels (`scratchpad/pgtest/run_depot_contre3_pg.py`) : 452 tests verts
  sur 452 avec le code nouveau, 445 sur 445 avec `31d384b`, aucun échec propre au code nouveau ; le nouveau fichier avec
  le code d'avant : 7 échecs. Durées des courses avec le code nouveau (`run_contre3_durees.py`) : 2,3 s chacune, l'autre
  requête attend le verrou de l'invitation (aucun blocage).
- Postgres 16 depuis l'état EXACT de la production (`a7f48d2`, tête `x8y9redactionv4`), script
  `scratchpad/pgtest/run_depot_contre3_depuis_prod.py` (copie de `run_depot_relecture2_depuis_prod.py` avec le nouveau
  fichier, TZ=UTC) : tous les contrôles de migration verts (une seule révision `y9z0depotlien`, aucune donnée perdue,
  seconde montée et rejeu sans effet, dépôt par le lien sur la base montée, code de production redémarré : 200 partout,
  schéma identique à une base neuve, retour arrière puis remontée) ; 39 fichiers de tests rejoués sur la base montée :
  1 050 verts (1 043 + 7) et exactement les mêmes 37 échecs qu'au § 21.14 (fichiers propres à SQLite, déjà connus).

## 22. Contrôle des bugs (22/10/2026), groupe « redaction »

Quatre signalements vérifiés réels (n° 15, 16, 17 et 18 de la liste « à vérifier »), reproduits sur `cfe04e1` et
corrigés ; aucun rejeté. Tests : `tests/test_controle_bugs_redaction.py`, 5 tests, tous en échec sur `cfe04e1`,
chacun sur son défaut.

- **(15, mineur) Téléphone, « Qui écrit quoi »** : le contrat (§ 16) dit « lire et répartir ; écrire depuis un
  ordinateur », mais l'écran montrait « Rédiger à sa place » et « Partenaire absent ? Vous pouvez écrire sa partie »
  pour une part sans texte, puis un volet sans aucun moyen d'écrire. Désormais, sur téléphone : pas de bouton pour
  une part sans texte (il reste « Replier » si le volet a été ouvert depuis l'onglet « Rédaction ») ; la phrase et le
  volet disent « Depuis un ordinateur, vous pouvez … » ; le lien de l'onglet « Rédaction » dit « Voir dans « Qui
  écrit quoi » ». Sur ordinateur, rien ne change. Trois libellés traduits en néerlandais et en espagnol
  (décision 16 ; 826 → 829 clés).
- **(16, mineur) « Demander les parts » et un partenaire qui ne peut plus rédiger** (lien expiré, invitation du
  réseau sans réponse, co-construction fermée, plus membre) : `demander_parts` le sautait sans trace ; la
  confirmation l'annonçait comme destinataire et le résultat disait « chaque partenaire a envoyé ses parties ». La
  réponse porte maintenant `indisponibles: [{invite_id, nom, raison}]` (jamais une adresse) ; l'écran ne compte que
  les partenaires qui peuvent rédiger (`atlRepADemander` lit `membres[].peut_rediger`), dit « Aucune demande à X :
  son lien a expiré. », et, quand la seule part en attente est chez un tel partenaire, « Aucune partie à demander
  pour l'instant. » (sa raison s'affiche dessous, comme avant). Un partenaire disponible est demandé comme avant.
- **(17, mineur) Carnet de notes, marché à plusieurs lots** : « Note d'ensemble, lot 2 — … » (message du serveur
  quand un critère du lot n'a pas sa note, et ligne de la note d'ensemble de chaque lot chez le chef de file)
  devient « Note d'ensemble, partie (lot 2) — … » (décision 10). Serveur : `carnet_notes._partie_lot`, même règle
  que `partieLot(x, true)` des écrans (vérifié sous Node sur les mêmes cas) ; écran : `partieLot`, comme la ligne du
  partenaire. La donnée `lot_libelle` garde « Lot 2 — … ». Un intitulé libre qui ne commence pas par « Lot » s'écrit
  désormais tel quel (avant : sa première lettre passait en minuscule), comme chez le partenaire.
- **(18, mineur) Dossier « sans IA »** : l'email de « Demander les parts » ne dit plus « ou avec l'aide d'Adjugo »
  (aide refusée au partenaire, C2.8) mais « Écrivez-la vous-même, depuis votre lien (le chef de file a choisi de
  rédiger ce dossier sans IA) : ». Sans ce mode, le texte est inchangé. La relance planifiée ne parle pas de l'aide.

Ni prix, ni quota, ni offre, ni page juridique, ni démo touchés ; aucune IA, aucune migration.

**Signalé, non corrigé (hors de la liste du groupe)** : la confirmation de « Demander les parts » finit par
« Chacun reçoit par email la liste de ses parties… » même quand un des partenaires n'a pas d'adresse sur son lien
(il est alors dit, au résultat, « Aucune adresse email sur le lien de X »).

**Vérifications** : voir le message du commit (suites SQLite et PostgreSQL, SRI, `node --check`, i18n). Le rendu
dans un navigateur à 375 px n'a pas été rejoué : le gabarit est vérifié par sa compilation dans la suite
(`test_gabarit_compile_par_le_vue_du_depot`) et par les tests statiques et sous Node du fichier ci-dessus.
