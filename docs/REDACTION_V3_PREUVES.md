# Rédaction, vague 3 — socle « Mes preuves » : contrat pour A, I et E1

Ce document est le contrat du SOCLE commun aux trois chantiers de la vague 3 :

- **A** « Chaque fait a sa source » (étude § 6.5) : numérote les faits remis à l'IA (`[F3]`) et
  contrôle chaque phrase sans IA ;
- **I** « Partir de vos anciens dossiers » (§ 6.6) : propose des fiches à partir des documents
  importés, l'utilisateur coche ;
- **E1** « Mes preuves » (§ 6.7) : les écrans (Références, Qualifications, Équipe, Matériel, et
  les chiffres clés).

Source de vérité du code : `app/models/__init__.py` (`Preuve`), `app/services/preuves.py` (toutes
les règles, seul point d'écriture), `app/routers/preuves.py` (HTTP), migration
`alembic/versions/v6w7preuves_mes_preuves.py` (révision `v6w7preuves`, après
`u5v6essaigardefou`). Tests : `tests/test_redaction_v3_preuves.py`.

Comment A, I et E1 se branchent ensemble (parcours complet, règles d'assemblage) :
`docs/REDACTION_V3_ENSEMBLE.md`.

Règles fermes (doctrine § 7) que le socle garantit et que A, I et E1 ne doivent jamais
contourner :

1. **Un fait ne vient jamais de l'IA.** Une preuve a une source typée ; l'IA peut PROPOSER une
   fiche (I), jamais la valider. Une fiche « dans vos documents » n'est enregistrée que si son
   passage est retrouvé tel quel dans le document ET que chaque chiffre, année, montant, nom propre,
   certification et matériel de la fiche y figure (sans IA).
2. **Qui affirme quoi.** Le dossier de l'acheteur n'est JAMAIS une source de preuve (aucun type de
   source ne le permet). Chaque preuve a un propriétaire (l'organisation ; en vague 4 un membre du
   groupement — champ prévu, jamais exposé).
3. **On ne dit jamais « vérifié ».** Les libellés disent où le fait a été trouvé (liste fermée
   ci-dessous). Un test interdit le mot dans tout le module et dans les réponses.
4. **Aucune bibliothèque partagée entre clients.** Tout est cloisonné par organisation ; une
   preuve d'un autre compte répond 404.
5. **CV et noms des salariés jamais envoyés à l'IA.** `texte_ia` ne contient ni nom ni CV ; les
   noms des fiches « Équipe » sont ajoutés aux noms masqués avant chaque appel (`pii_scope`).

---

## 1. Le modèle (`preuves`)

| colonne | sens |
|---|---|
| `id` | identifiant technique |
| `owner_id` | tenant : `data_owner_id` de l'organisation (FK `users.id`), comme l'atelier |
| `proprietaire_kind` / `proprietaire_invite_id` | qui DÉTIENT le fait : `organisation` / `0` aujourd'hui ; vague 4 : `invitation` / id de l'invitation. **Jamais exposé par l'API**, jamais lu par le chef de file |
| `numero` | identifiant STABLE dans la portée (`owner_id`, `proprietaire_invite_id`) : renvoi `F<numero>` ; jamais réutilisé |
| `nature` | `reference` · `qualification` · `salarie` · `materiel` · `chiffre_cle` |
| `valeur` | champs structurés de la nature (liste fermée, § 2) |
| `type_source` | `documents` · `declare` · `public` · `estimation` (§ 3) |
| `source` | détail de la source (passage exact, URL datée…) |
| `source_doc_id` | document de « Mon savoir-faire » (`knowledge_docs.id`), SANS clé étrangère |
| `source_document_id` | justificatif du coffre-fort (`documents.id`), SANS clé étrangère |
| `date_source` | date du document d'origine (I) ou de consultation de la source publique |
| `date_fin_validite` | fin de validité (qualification, attestation…) |
| `statut` | `proposee` · `acceptee` · `retiree` ; `supprimee` = interne (contenu effacé, numéro réservé, jamais listé) |
| `origine` | `saisie` · `import_document` (I) · `import_public` (E2) · `profil` · `chiffrage` |
| `empreinte` | sha256 de la nature et des champs repliés (doublons) |
| `cree_par`, `accepte_par`, `accepte_le`, `retire_le`, `version`, `created_at`, `updated_at` | traçabilité, verrou optimiste |

Contrainte : `UNIQUE(owner_id, proprietaire_invite_id, numero)`. Les liens vers les documents n'ont
pas de clé étrangère : supprimer un document ne doit jamais échouer ; l'existence de la source est
contrôlée à chaque lecture (une preuve dont le document a disparu n'est plus remise à la rédaction).

## 2. Natures et champs (liste fermée)

Tout champ hors liste → 422 `champ_inconnu`. Les champs vides sont retirés.

| nature | libellé | champs (obligatoires en gras) |
|---|---|---|
| `reference` | Référence | **objet** (300), acheteur (200), lieu (120), annee (1900–2100), montant_ht (€, ≥ 0), role (`seul` · `groupement_conjoint` · `groupement_solidaire` · `sous_traitant`), description (1000) |
| `qualification` | Qualification | **nom** (200, ex. « Qualibat 3194 »), organisme (120), numero (60), detail (300) ; la validité est `date_fin_validite` |
| `salarie` | Équipe | **nom** (120), **fonction** (120), experience_annees (0–70), diplomes (300), qualifications (300), chantiers (1000) |
| `materiel` | Matériel | **designation** (200), quantite (≥ 1), caracteristiques (300), possession (`propriete` · `location`) |
| `chiffre_cle` | Chiffre clé | **libelle** (120), **valeur** (nombre), unite (40), annee |

**CV minimal** : ni photo, ni adresse, ni date de naissance (ni téléphone, courriel, nationalité,
situation familiale, numéro de sécurité sociale) → 422 `champ_interdit`, message « Le CV ne contient
ni photo, ni adresse, ni date de naissance. »

Texte d'une preuve (`texte`, déterministe, `pv.texte_de`) :
`Référence : Réfection de la toiture de l'école Jules Ferry ; acheteur : Mairie de Quimper ; année
2024 ; montant 85 000 € HT ; réalisé seul`. C'est CE texte que A rapproche des phrases.

## 3. Types de source

| `type_source` | libellé affiché (`source_libelle`) | natures permises | `appuie` (pour A) | `source` attendue à l'écriture |
|---|---|---|---|---|
| `documents` (passage) | « trouvé dans vos documents » + lien vers le passage | toutes | `entreprise` | `{doc_id, passage}` : passage d'un document de « Mon savoir-faire » de l'organisation, 12 à 1 200 caractères |
| `documents` (justificatif) | « justificatif déposé » + lien vers le fichier | toutes | `entreprise` | `{document_id}` : document du coffre-fort de l'organisation, hors corbeille |
| `declare` | « déclaré par vous » | toutes | `entreprise_declaration` (phrase présentée comme une déclaration) | rien |
| `public` | « source publique : <nom> » ; référence DECP : « marché attribué, source publique DECP » | `reference`, `qualification` | `references_qualifications` | `{nom, url (https), consulte_le (AAAA-MM-JJ, pas dans le futur), identifiant?}` |
| `estimation` | « votre estimation » | `chiffre_cle` | `estimations` (délais, effectifs prévus, quantités) | `{project_id?, detail?}` ; rattachée à un marché, elle ne vaut que pour lui |

Contrôle du passage (sans IA, `pv.localiser` puis `pv.elements_hors_passage`) :

- le passage est cherché tel quel, puis à la casse, aux accents, aux espaces et aux apostrophes près
  (même tolérance que `citation_guard`) ; introuvable → 422 `passage_introuvable` ;
- le passage ENREGISTRÉ est celui du document (tel qu'il y est écrit), avec sa position (`debut`)
  et le morceau d'index qui le contient (`chunk_id`) ;
- chaque chiffre, année, montant, certification, nom propre et matériel des champs doit figurer dans
  le passage (même repérage que « à relire ») ; l'acheteur, le lieu, le nom, le numéro et
  l'organisme doivent y figurer tels quels ; sinon 422 `valeur_hors_passage` avec
  `elements: [...]` (« Ces éléments de la fiche ne figurent pas dans le passage : … Corrigez-les,
  choisissez un passage qui les contient, ou choisissez « déclaré par vous ». »).

Un document d'origine de plus de 3 ans (`date_source`) : `a_reconfirmer: true` (I l'affiche « à
reconfirmer »). La preuve reste utilisable si l'utilisateur l'accepte.

## 4. Statuts et ce qui est remis à la rédaction

`proposee` (I, E2 : l'utilisateur coche) → `acceptee` → `retiree` (et retour par « accepter »).
Une preuve saisie par l'utilisateur est créée `acceptee` (c'est sa déclaration).

Une preuve est **utilisable** (remise à la rédaction) si et seulement si : statut `acceptee`, de
l'organisation (`proprietaire_invite_id = 0`), date de fin de validité non dépassée (jour de Paris),
et, pour `documents`, document encore présent dans l'organisation. Sinon `raison` :

| `raison` | `raison_message` |
|---|---|
| `proposee` | Proposée : cochez-la si elle est juste, pour qu'Adjugo puisse s'en servir. |
| `retiree` | Retirée : Adjugo ne s'en sert plus. |
| `expiree` | Date de fin de validité dépassée : Adjugo ne s'en sert plus. |
| `source_introuvable` | Le document d'origine n'est plus dans « Mon savoir-faire » : ajoutez une autre source ou déclarez-la vous-même. |
| `justificatif_introuvable` | Le justificatif n'est plus dans vos documents : déposez-le de nouveau ou déclarez-la vous-même. |

**Numéros stables.** `F<numero>` ne change jamais pour une preuve et n'est jamais réutilisé : une
suppression efface le contenu (CV compris) mais garde la ligne vide pour réserver le numéro. Un
ancien renvoi `[F3]` dans une version de texte ne peut donc jamais désigner un autre fait. Les
numéros suivent l'organisation au transfert de propriété.

## 5. API Python (ce que A, I et E1 appellent)

```python
from app.services import preuves as pv
```

### Pour A — la fonction unique

```python
pv.faits_autorises(db, owner_id, *, natures=None, project_id=None, jour=None) -> list[dict]
```

`owner_id` = `data_owner_id(user, db)` (le `owner_id` de l'atelier). Rend les preuves UTILISABLES
(§ 4), dans l'ordre des numéros ; une estimation rattachée à un autre marché est écartée. Chaque fait :

```python
{"ref": "F3", "id": 12, "numero": 3,
 "nature": "reference", "nature_libelle": "Référence",
 "type_source": "documents", "source_libelle": "trouvé dans vos documents",
 "appuie": "entreprise",            # entreprise | entreprise_declaration | references_qualifications | estimations
 "texte": "Référence : …",          # pour le RAPPROCHEMENT (nom d'un salarié compris) — jamais à l'IA tel quel pour « Équipe »
 "texte_ia": "Référence : …",       # à remettre à l'IA : « Équipe » = fonction seule, ni nom ni CV
 "valeur": {...},                   # champs (CV compris pour « Équipe ») — jamais à l'IA
 "source": {"doc_id": 4, "doc_nom": "Mémoire 2024", "passage": "…", "chunk_id": 51,
            "lien_passage": "/api/preuves/12/passage"},
 "date_source": "2024-03-01", "a_reconfirmer": False, "date_fin_validite": None,
 "proprietaire": {"kind": "organisation", "invite_id": None}}   # interne (vague 4)
```

- `pv.texte_pour_ia(fait, pseudonymiseur)` : pour « Équipe », met l'étiquette de la personne
  (« Équipe : [Conducteur de travaux 1], Conducteur de travaux ») si le pseudonymiseur de l'appel la
  connaît ; sans pseudonymiseur : « Équipe : une personne de l'équipe, Conducteur de travaux ».
  Les autres natures : le texte complet (l'appel reste dans `pii_scope`).
- Les noms des fiches « Équipe » sont DÉJÀ ajoutés aux noms masqués : `pii.team_of_users()` (tous
  les appels qui l'utilisent) et `atelier.Contexte.pseudonymiseur()` les incluent (tous statuts).
- `pv.faits_ecartes(db, owner_id)` : preuves acceptées non utilisées, avec `raison` et `message`
  (expirée, source introuvable) — pour le dire dans l'atelier.
- `pv.elements_hors_passage(nature, valeur, passage)` et `pv.localiser(texte, passage)` sont
  réutilisables pour le rapprochement.
- Les CV sont insérés tels quels, sans IA (décision 8a) : A lit `valeur` des faits `salarie`.
- Le préfixe `F` est RÉSERVÉ aux preuves enregistrées : un fait construit à la volée par A (chiffrage
  du marché, profil de l'entreprise pas encore repris en preuves) prend un autre préfixe, pour qu'un
  `[F3]` désigne toujours la même preuve, d'une version de texte à l'autre.
- Le profil existant (`Company.references`, `qualifications`, `team`) n'est pas repris
  automatiquement : l'origine `profil` est prévue pour qu'E1 (ou A) le PROPOSE en preuves
  « déclaré par vous » que l'utilisateur coche (`pv.proposer(..., type_source="declare",
  origine="profil")`).

Ce que A doit faire de son côté (hors socle) : numéroter les faits `[F3]` avec `ref`, écrire
« [À compléter : …] » pour tout autre fait, contrôler chaque phrase sans IA (de qui parle la
phrase, repérage, rapprochement avec le `texte` des faits CITÉS et du bon `appuie`, recalcul,
engagements), retirer les marques `[F…]` à l'export. Calibration : le jeu d'au moins 50 phrases
piégées doit passer avec ZÉRO piège présenté comme « trouvé dans vos documents » AVANT tout libellé
positif ; la mesure du taux de fausses alertes sur 20 mémoires réels (accord écrit des PME) reste à
faire par Mathys — A fournit l'outil de mesure (script) sans les données. Jusque-là, A0 (« à
relire ») reste le seul affichage.

### Pour I — proposer, l'utilisateur coche

```python
preuve, creee = pv.proposer(db, owner_id, nature="reference", valeur={...},
                            type_source="documents",
                            source={"doc_id": doc.id, "passage": "<passage proposé par l'IA>"},
                            date_source=date_du_document, origine="import_document", user=user,
                            commit=True)
```

- statut `proposee` ; une fiche identique déjà présente (même nature, mêmes champs aux accents et à
  la casse près, quel que soit son statut) n'est pas recréée : `(existante, False)` ;
- **toute proposition qui ne respecte pas les règles lève `pv.PreuveError`** (`passage_introuvable`,
  `valeur_hors_passage`, `champ_*`…) : elle est rejetée, sans IA. Avec `commit=False` (lot), faire
  `db.rollback()` du lot ou appeler une proposition à la fois ;
- l'appel IA qui lit les documents se fait dans `tenant_scope(owner_id)` et
  `pii_scope(from_team(team_of_users(db, [owner_id])))` — les noms déjà connus (profil, fiches
  « Équipe ») sont masqués ; un CV importé ne doit PAS être envoyé à l'IA (décision 8) : les fiches
  « Équipe » se proposent sans IA ou se saisissent ;
- coût : économiser l'IA sans baisser la qualité (une lecture par document, résultats gardés) ;
  remboursement si l'IA tombe (mécanisme existant des tâches).

### Pour E1 — les écrans

Routes HTTP du § 6. `pv.preuve_out()` donne tout ce que l'écran affiche.

### Écritures (communes)

| fonction | effet |
|---|---|
| `pv.creer(db, owner_id, *, nature, valeur, type_source="declare", source=None, date_source=None, date_fin_validite=None, statut="acceptee", origine="saisie", user=None, commit=True)` | crée (numéro suivant, verrou sur la ligne du compte en Postgres) |
| `pv.modifier(db, p, *, user, valeur=…, type_source=…, source=…, date_source=…, date_fin_validite=…, version=None)` | seuls les arguments passés changent ; source recontrôlée dès que les champs ou la source changent ; la nature ne change pas |
| `pv.accepter(db, p, user, version=None)` | `acceptee` ; 409 si la source a disparu |
| `pv.retirer(db, p, user, version=None)` | `retiree` |
| `pv.supprimer(db, p, user)` | efface le contenu, réserve le numéro |
| `pv.get(db, owner_id, id)` / `pv.lister(db, owner_id, nature=None, statut=None)` | lecture, organisation seulement |

Erreurs : `pv.PreuveError(status, code, message, **extra)` ; `e.detail()` = `{code, message, …}`.

## 6. Routes HTTP (`/api/preuves`)

Authentification `Authorization: Bearer <jeton>`. Erreurs métier : `detail` = `{code, message, …}`
(afficher `message` tel quel). Une preuve d'une autre organisation, ou détenue par un membre du
groupement, ou supprimée → **404** `preuve_introuvable` (jamais 403). Les membres d'une même
organisation partagent les mêmes preuves. Compte démo : lecture seule, toute écriture → **403**
`detail` texte « La démo est en lecture guidée : créez votre compte gratuit pour renseigner vos
preuves. »

| méthode | route | corps | réponse |
|---|---|---|---|
| GET | `/api/preuves?nature=&statut=` | — | `{preuves: [preuve], compteurs: {nature: {proposee, acceptee, retiree}}, natures: [{code, libelle}], types_source: [{code, libelle, natures}]}` |
| POST | `/api/preuves` | `{nature, valeur, type_source?, source?, date_source?, date_fin_validite?, statut? ("acceptee" par défaut, ou "proposee")}` | 201 `preuve` |
| GET | `/api/preuves/{id}` | — | `preuve` |
| PATCH | `/api/preuves/{id}` | champs ENVOYÉS seulement : `valeur`, `type_source`, `source`, `date_source`, `date_fin_validite` (null efface une date), `version?` | `preuve` |
| POST | `/api/preuves/{id}/accepter` | `{version?}` | `preuve` |
| POST | `/api/preuves/{id}/retirer` | `{version?}` | `preuve` |
| DELETE | `/api/preuves/{id}` | — | 204 (définitif) |
| GET | `/api/preuves/{id}/passage` | — | `{doc_id, doc_nom, passage, avant, apres, debut}` (300 caractères avant et après) |

`preuve` :

```json
{"id": 12, "ref": "F3", "numero": 3, "nature": "reference", "nature_libelle": "Référence",
 "valeur": {"objet": "…", "acheteur": "Mairie de Quimper", "annee": 2024, "montant_ht": 85000, "role": "seul"},
 "texte": "Référence : …",
 "type_source": "documents", "source_libelle": "trouvé dans vos documents",
 "source": {"doc_id": 4, "doc_nom": "Mémoire 2024", "passage": "…", "chunk_id": 51,
            "lien_passage": "/api/preuves/12/passage"},
 "date_source": "2024-03-01", "a_reconfirmer": false,
 "date_fin_validite": null, "expiree": false, "jours_restants": null,
 "statut": "acceptee", "statut_libelle": "Acceptée", "origine": "saisie",
 "utilisable": true, "raison": null, "raison_message": null,
 "cree_le": "2026-10-12T21:00:00+00:00", "modifie_le": "…", "accepte_le": "…", "version": 0}
```

Source affichée selon le type : justificatif `{document_id, document_nom, lien_justificatif:
"/api/documents/<id>/download"}` ; publique `{nom, url, consulte_le, identifiant?}` ; estimation
`{project_id?, detail?}` ; déclarée `{}`.

Codes d'erreur : `nature_invalide`, `valeur_invalide`, `champ_inconnu`, `champ_interdit`,
`champ_requis`, `champ_invalide` (+ `champ`), `statut_invalide`, `origine_invalide`,
`type_source_invalide`, `source_non_permise`, `source_requise`, `document_introuvable`,
`passage_trop_long`, `passage_introuvable`, `valeur_hors_passage` (+ `elements`),
`justificatif_introuvable`, `url_invalide`, `date_requise`, `marche_introuvable` (422) ;
`modifiee_ailleurs` (+ `version`), `trop_de_preuves` (2 000 par organisation), `source_introuvable`
(accepter) (409) ; `preuve_introuvable` (404).

« Mon savoir-faire » : `DELETE /api/knowledge/{doc_id}` renvoie en plus `preuves_sans_source` (nombre
de preuves proposées ou acceptées dont le passage venait de ce document) : E1 peut prévenir avant et
après la suppression.

### Écrans E1 (rappel de l'étude, à respecter)

- Dans « Mon entreprise », un onglet « Mes preuves » ajouté SANS déplacer les entrées existantes du
  menu (restructuration reportée) ; quatre listes courtes : Références, Qualifications, Équipe (CV
  minimal), Matériel (+ chiffres clés) ; compact, lisible à 375 px, zéro émoji, zéro jargon.
- Chaque élément : son libellé de source (`source_libelle`, avec le lien vers le passage ou le
  fichier), sa date de fin de validité, « à reconfirmer » si `a_reconfirmer`, et `raison_message`
  s'il n'est pas `utilisable`.
- Bulle (i) proposée : « Adjugo relie chaque fait à l'endroit où il l'a trouvé : un passage de vos
  documents, un justificatif, une source publique, ou votre déclaration. Il ne sait pas si ce
  document est à jour : relisez vos preuves. »
- Le mot « vérifié » n'apparaît nulle part.

## 7. RGPD

- **Export** (`GET /api/rgpd/export`) : `mes_preuves` = toutes les preuves de l'organisation du
  compte propriétaire (CV compris, source et passage compris), hors lignes supprimées.
- **Effacement du compte** : propriétaire seul → toutes ses preuves (organisation, membres du
  groupement, lignes réservées) ; membre → ses éventuelles lignes passent au propriétaire, sans
  jamais heurter un numéro de l'organisation (`transferer(…, numeros="destination")`).
- **Transfert de propriété** : les preuves suivent le nouveau propriétaire avec leurs numéros
  (`transferer(…, numeros="source")`).
- **Suppression d'une preuve** : définitive pour son contenu (CV compris) ; seul le numéro reste.
- Les noms des fiches « Équipe » ne partent jamais à l'IA (masqués, § 5) ; le CV jamais.

## 8. Vague 4 (prévu, non exposé)

`proprietaire_kind = "invitation"` et `proprietaire_invite_id = <id de l'invitation>` : les preuves
d'un partenaire venu par lien magique, rangées chez le chef de file (décision 5a) mais jamais lues
par lui. Aujourd'hui aucune route n'en crée ; toutes les lectures (`get`, `lister`, `compteurs`,
`faits_autorises`, `exporter`) les excluent, et leurs noms sont quand même masqués avant l'IA. À la
vague 4 : ajouter des fonctions portées par l'invitation (même numérotation, portée propre) et le
compteur « 6 faits trouvés dans les documents du couvreur » côté chef de file, sans contenu.

## 9. Limites assumées

- Un document de « Mon savoir-faire » ne change jamais de texte après son import : le passage
  contrôlé à l'écriture fait foi tant que le document existe (son existence est relue à chaque
  lecture, pas son texte).
- Le passage prouve que le fait est ÉCRIT dans le document, pas qu'il est vrai ni à jour : c'est ce
  que disent les libellés (« trouvé dans vos documents »), jamais « vérifié ».
- Un justificatif déposé n'est pas lu : il est lié, et le libellé le dit (« justificatif déposé »).
- Le « jour » de la validité est celui de Paris (une validité « jusqu'au 12/10 » vaut tout le 12/10).
