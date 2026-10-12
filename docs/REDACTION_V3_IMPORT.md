# Rédaction, vague 3 — chantier I « Partir de vos anciens dossiers »

Étude « rédaction », § 6.6 (I), doctrine § 7, décisions 7 et 8. Socle : `docs/REDACTION_V3_PREUVES.md`.

La TPE importe ses anciens dossiers de présentation, sa plaquette et ses attestations dans « Mon
savoir-faire ». Pour chaque document, Adjugo **propose** des fiches de preuves (références,
qualifications, matériel, chiffres clés), chacune avec le **passage exact** où il l'a trouvée.
L'utilisateur **coche** ce qu'il garde : les fiches cochées deviennent des preuves « trouvé dans vos
documents » du socle, que la rédaction (A) peut citer.

Code : `app/services/fiches_import.py` (toutes les règles), `app/routers/fiches_import.py` (HTTP),
écran dans `app/static/app.html` (bloc « FICHES PROPOSÉES ») et `app/static/app.js` (méthodes `fx…`).
Tests : `tests/test_redaction_v3_import.py`. Aucune migration : les fiches sont des lignes `preuves`
(statut `proposee`, origine `import_document`) ; la lecture est une ligne `jobs` (kind
`fiches_preuves`, `result.doc_id`).

## 1. Ce que fait l'IA, ce qui se fait sans elle

| Étape | Qui |
|---|---|
| Choisir ce qui part à l'IA (paragraphes porteurs d'un fait, hors passages de CV) | sans IA |
| Masquer les noms (profil, fiches « Équipe », noms repérés dans le document) | sans IA (`pii_scope`) |
| Proposer des fiches avec leur passage | **IA** (tâche `fiches_preuves`) |
| Retrouver le passage tel quel dans le document | sans IA (même tolérance que `citation_guard`) |
| Vérifier que la fiche ne dit rien de plus que son passage | sans IA |
| Accepter une fiche | **l'utilisateur** (il coche) |

Une proposition est **écartée** (comptée, jamais montrée) si :

| code | libellé affiché | règle |
|---|---|---|
| `passage_introuvable` | passage non retrouvé tel quel dans le document | le passage n'est pas une sous-chaîne du texte (casse, accents, espaces, apostrophes près), ou fait moins de 12 caractères |
| `valeur_hors_passage` | fiche qui disait plus que son passage | un champ OBLIGATOIRE (objet, nom, désignation, libellé, valeur) contient un chiffre, une année, un nom propre, une certification, du matériel ou un mot que le passage n'écrit pas |
| `exigence_acheteur` | passage qui rapporte une exigence d'un acheteur | aucune phrase du passage ne parle de l'entreprise (« Le CCTP impose une nacelle de 20 m ») — `faits_a_relire.parle_entreprise` |
| `equipe` | fiche sur une personne | l'IA ne propose jamais de fiche « Équipe » (décision 8) |
| `incomplete`, `passage_trop_long`, `trop_de_fiches` | | champs invalides, passage de plus de 1 200 caractères, plus de 120 fiches par document |

Une fiche est **corrigée** (sans IA, en retirant, jamais en ajoutant) quand un champ FACULTATIF en dit
plus que le passage : il est retiré (année déduite, acheteur reformulé, description paraphrasée…). En
plus :

- le **rôle** (seul, groupement conjoint ou solidaire, sous-traitant) n'est gardé que si le passage
  l'écrit ; la **possession** (en propre, en location) aussi ;
- un **montant HT** n'est jamais gardé quand le passage dit TTC sans HT ;
- une **date de fin de validité** n'est gardée que si elle est écrite dans le passage ;
- le libellé d'un **chiffre clé** admet un mot de catégorie que le passage justifie (« Effectif »
  pour « 12 salariés »), liste fermée : un chiffre n'est jamais rangé sous une autre catégorie.

Le passage enregistré est celui du document (`pv.proposer` le relit et le recontrôle : défense en
profondeur). La date du document (`date_source`) est celle que l'utilisateur confirme avant la
lecture (suggestion : la date la plus récente écrite en première page) ; au-delà de 3 ans, les
fiches sont « à reconfirmer ».

## 2. Ce qui n'est jamais lu, jamais envoyé

- **Un CV** (décision 8) : nom de fichier (« CV_… », « curriculum »), titre en tête, ou texte fait
  surtout de passages de CV → document refusé (`document_cv`), aucun appel. Dans un document lu, les
  **passages qui ressemblent à un CV** (titre « CV », ou deux marques propres à un CV : date de
  naissance, situation familiale, expérience professionnelle, loisirs… ; ou une marque et deux
  rubriques ou coordonnées) sont retirés avant l'envoi.
- **Une pièce du dossier d'un acheteur** (règlement, CCAP, CCTP en titre ou en nom, sans « nous »,
  « notre », « nos » en première page) → refusée (`document_piece_acheteur`) : le dossier de
  l'acheteur n'appuie jamais un fait sur l'entreprise.
- **Les noms** : profil (`Company.team`), fiches « Équipe » (tous statuts) et noms repérés sans IA
  dans ce qui part (« M. Kerjean », « Chef d'équipe : Anne Le Floch », « Yann Tanguy, conducteur de
  travaux », « sous la conduite de … ») sont remplacés par des étiquettes, puis remis en clair dans
  la réponse, sans IA. Limite : un nom isolé, sans civilité, fonction ni tournure de ce type, et
  absent du profil, n'est pas reconnu.
- **Les paragraphes sans aucun fait** (ni chiffre, ni nom propre, ni certification, ni matériel, ni
  mot comme « référence », « client », « matériel », « qualification », « effectif ») : ils ne
  peuvent donner aucune fiche, ils ne partent pas (économie sans perte de qualité).

## 3. Coût

- **Une lecture par document** : déjà lu ou en cours, la demande rend le résultat gardé, sans IA.
- **Gratuit jusqu'au plafond du mois** par organisation : `FICHES_DOCUMENTS_PAR_MOIS` (défaut 20 ;
  0 = fonction en pause). Au-delà : 429 `plafond_atteint`. Aucune analyse n'est débitée.
- **Essai gratuit** : le budget de l'essai est vérifié AVANT (`budget_ia.verifier`, opération
  `fiches`, estimation prudente par partie de 60 000 caractères) ; essai terminé sans forfait → 402.
  Le coût réel est relevé appel par appel pour le compte facturé (`tenant_scope` posé par la tâche
  de fond), donc compté dans le budget de l'essai.
- **Si l'IA tombe** (panne, réponse illisible) : rien n'est proposé, la lecture passe en échec et
  n'est plus comptée dans le plafond (elle est rendue) ; un redémarrage du serveur pendant la
  lecture fait de même (`_recover_orphan_jobs` ne rembourse aucune analyse : rien n'a été débité).
- Route de l'IA : `fiches_preuves` (lecture et extraction), Mistral Large 4 si Mistral est activé,
  Claude Sonnet 5.5 en secours ; JSON ; réflexion « between_tools », effort moyen ; 8 000 tokens de
  sortie au plus par appel ; une réponse coupée relit la partie en deux moitiés (deux fois au plus).
  Ajoutée à `_TACHES_LECTURE` (`app/main.py`) : les pages juridiques disent toujours « lecture et
  analyse » pour les tâches de Mistral, texte inchangé.

## 4. Routes (`Authorization: Bearer`)

Portée : l'organisation (`data_owner_id`) ; un document d'une autre organisation → **404**
`document_introuvable`. Erreurs : `detail = {code, message}` (afficher `message`). Démo : 403 texte.

| méthode | route | réponse |
|---|---|---|
| GET | `/api/knowledge/fiches` | `{documents: {"<doc_id>": {statut, a_cocher, cochees}}, plafond: {limite, utilises, restants}}` |
| GET | `/api/knowledge/{doc_id}/fiches` | `etat` (ci-dessous) |
| POST | `/api/knowledge/{doc_id}/fiches` | corps `{date_document?: "AAAA-MM-JJ"}` → **202** `etat` (lecture lancée) ou **200** `etat` (déjà lu ou en cours : aucun appel) |

`statut` d'un document : `a_lire`, `en_cours`, `lu`, `echec`, `cv`, `piece_acheteur`, `rien_a_lire`.

```json
{"document": {"id": 4, "nom": "Mémoire 2021.pdf", "statut": "lu", "message": null, "date_suggeree": "2021-03-12"},
 "lecture": {"statut": "lu", "job_id": 12, "date_document": "2021-03-12", "lu_le": "…",
             "proposees": 4, "deja": 0, "ecartees": 3,
             "ecarts": [{"code": "passage_introuvable", "libelle": "passage non retrouvé tel quel dans le document", "nombre": 1}]},
 "fiches": ["preuve_out du socle : id, ref, nature, valeur, texte, source {doc_id, doc_nom, passage, lien_passage}, statut, version, a_reconfirmer…"],
 "plafond": {"limite": 20, "utilises": 1, "restants": 19}}
```

Une lecture en échec : `lecture = {statut: "echec", message}` (relançable). Cocher / décocher : routes
du socle `POST /api/preuves/{id}/accepter` et `/retirer` (`{version}`) ; voir le passage dans son
contexte : `GET /api/preuves/{id}/passage`.

Erreurs du POST : `document_cv`, `document_piece_acheteur`, `document_rien_a_lire`, `date_invalide`
(422) ; `plafond_atteint` (429) ; `essai_limite_usage`, `essai_termine` (402) ; adresse non confirmée
(403 texte) ; démo (403 texte).

## 5. Écran (« Mon savoir-faire »)

Sous chaque document : « Proposer des fiches » (ou « Voir les fiches proposées », « Lecture en
cours », « Pourquoi aucune fiche ») et le résumé « 3 à cocher · 1 cochée(s) ». Le panneau montre la
date du document (suggérée, modifiable), le bouton « Proposer des fiches à partir de ce document », le
plafond restant ; puis la liste des fiches : case à cocher, texte de la fiche, **passage cité**,
libellé de source du serveur (« trouvé dans vos documents : <document> »), « à reconfirmer », bouton
« Voir le passage dans le document » (contexte avant / après, passage surligné) ; et le résumé des
propositions écartées « par Adjugo, sans IA ». Bulles (i) : ce que fait la lecture (une fois, passage
exact, rien sans vous, noms masqués, CV jamais envoyé), la date du document, le sens de « cocher ».
Le menu n'est pas réorganisé. Lisible à 375 px, zéro émoji, jamais « vérifié ».

## 6. Ce qui reste

- Mesurer, sur de vrais documents (accord écrit des PME), la part de fiches proposées justes et la
  part écartées à tort ; ajuster les heuristiques (CV, pièce d'un acheteur, paragraphes sans fait)
  sur ces mesures.
- Vague 4 : un partenaire fait de même depuis son espace, ses fiches restent les siennes
  (`proprietaire_kind = invitation`, prévu dans le socle).
- Fiches « Équipe » proposées sans IA à partir d'un CV (lecture déterministe) : non faites, elles se
  saisissent dans « Mes preuves » (E1).
