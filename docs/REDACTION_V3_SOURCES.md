# Rédaction, vague 3 — A « Chaque fait a sa source » : contrat

Chantier A de la vague 3 (étude « rédaction » § 6.5, doctrine § 7, décisions 2b et 8a). Il s'appuie sur
le socle « Mes preuves » (`docs/REDACTION_V3_PREUVES.md`) et remplace, dans l'atelier, le contrôle A0
(« à relire », `app/services/faits_a_relire.py`, qui reste la base du repérage).

Source de vérité : `app/services/faits_sources.py` (règles, sans IA), `app/services/atelier.py`
(branchement), `app/services/agents/memoire.py` (consigne de l'IA), `app/routers/atelier.py` (routes).
Tests : `tests/test_redaction_v3_sources.py`, jeu de calibration `tests/pieges_sources.py`.
Outil de mesure : `scripts/mesure_fausses_alertes.py`. **Aucune migration** : le résultat du contrôle
est rangé dans la colonne existante `dossier_section_versions.faits` (forme ci-dessous).

Règles tenues : un fait ne vient jamais de l'IA ; le dossier de l'acheteur n'appuie jamais une phrase
sur l'entreprise ; jamais « vérifié » (on dit où le fait est écrit) ; le CV et les noms des salariés ne
partent jamais à l'IA ; `tenant_scope` et `pii_scope` sur chaque appel (inchangés) ; aucun nouvel appel
à l'IA (le contrôle, l'ajout d'une source et le recontrôle sont sans IA et ne débitent rien).

---

## 1. Les faits numérotés et typés remis à l'IA

| renvoi | d'où | type (`source.type`) | libellé | appuie (phrase sur l'entreprise) |
|---|---|---|---|---|
| `[F3]` | preuve utilisable de « Mes preuves » (`pv.faits_autorises`), numéro STABLE | `documents` · `justificatif` · `declare` · `public` · `estimation` | « trouvé dans vos documents », « justificatif déposé », « déclaré par vous », « source publique : … » / « marché attribué, source publique DECP », « votre estimation » | tout fait ; `estimation` : des NOMBRES seulement (délais, effectifs prévus, quantités) |
| `[S2]` | extrait de « Mon savoir-faire » remis pour la partie (6 au plus) | `documents` | « trouvé dans vos documents » | tout fait |
| `[P1]` | une ligne du profil (entreprise, effectif, chiffre d'affaires, qualifications, références) | `declare` | « déclaré par vous » | tout fait |
| `[E1]` | une personne de l'équipe du profil (nom masqué avant l'IA) | `declare` | « déclaré par vous » | tout fait |
| `[C1]` | une ligne du chiffrage du marché (phases, tâches, jours ; aucun prix) | `estimation` | « votre estimation » | des nombres seulement |
| `[G1]` | l'apport ENVOYÉ par un partenaire du groupement | `partenaire` | « déclaré par votre partenaire » | tout fait |
| — | le dossier de l'acheteur (« exigé par l'acheteur ») | `acheteur` | « dans le dossier de l'acheteur » | **jamais** : seulement une phrase sur le marché, l'acheteur ou le chantier |

- Le préfixe `F` est réservé aux preuves enregistrées ; `P`, `E`, `C`, `G` sont construits à chaque
  rédaction (`fs.fiches_contexte`), `S` suit la numérotation des extraits (`[S1]` existant).
- Ligne remise à l'IA (`Fiche.ligne_ia`) : `[F1] (déclaré par vous) Matériel : Nacelle articulée ;
  quantité : 2 ; en propre`. Une fiche « Équipe » : `[F2] (déclaré par vous) Équipe : [Conductrice de
  travaux 2], Conductrice de travaux — CV : écris « [CV F2] » seul sur une ligne pour l'insérer tel
  quel.` (étiquette du pseudonymiseur de l'appel ; ni nom, ni expérience, ni diplômes, ni chantiers).
- **CV (décision 8a)** : la réponse de l'IA est relue sans IA ; chaque « [CV F2] » est remplacé par le CV
  minimal de la fiche (`fs.inserer_cv`), chaque ligne portant `[F2]` ; un renvoi qui ne désigne pas une
  fiche « Équipe » utilisable devient « [À compléter : CV de la personne] ».
- Budget du bloc (économie d'IA sans perte) : toutes les lignes si elles tiennent en
  `ATELIER_FAITS_MAX_CARACTERES` (12 000 par défaut) ; sinon les preuves les plus proches de la partie
  (mots communs, sans IA) d'abord ; profil, équipe, chiffrage et partenaires toujours. Le bloc commun
  mis en cache (dossier de l'acheteur) est inchangé : le cache de prompt d'une heure joue toujours.
- Consigne (`_ATELIER_SYS`) : citer le renvoi à la fin de chaque phrase qui s'en sert ; tout autre fait
  en « [À compléter : …] » ; recopier les nombres tels quels ; « votre estimation » pour délais,
  effectifs prévus et quantités seulement ; aucun engagement absent des faits ; le CV par « [CV F#] ».
  « Raccourcir » garde tous les renvois.

## 2. Le contrôle, sans IA (`fs.controler`)

Phrase par phrase (découpage d'A0 au caractère près ; un renvoi isolé après le point appartient à la
phrase qui précède) :

1. **De qui parle la phrase** : règle d'A0 (`far.parle_entreprise`) — « nous », « notre », le nom de
   l'entreprise ou d'un partenaire, une partie sur les moyens, les références, la qualité… ; « Le CCTP
   prévoit… », « Le maître d'ouvrage impose… » parlent du marché ; dans le doute, l'entreprise.
2. **Repérage** (A0) : nombres et unités, nombres en lettres, années, certifications, noms propres,
   matériel. Le nom de l'entreprise ou d'un partenaire n'est pas un fait (c'est le sujet).
3. **Rapprochement**, phrase sur l'entreprise : d'abord les faits CITÉS dans la phrase, du bon type ; à
   défaut, un fait remis non cité (l'IA oublie parfois le renvoi : `cite: false`), dans cet ordre :
   vos documents, source publique, déclaré par vous, estimation, partenaire. Un fait non cité qui est
   une durée, un pourcentage ou un nombre sans unité exige un mot commun entre la phrase et la fiche
   (« depuis dix ans » ≠ « 10 ans d'expérience »). Les nombres se rapprochent AVEC leur unité : l'unité
   qui suit le nombre dans la source, ou, si le nombre n'en a pas, le libellé de la même proposition
   (« Effectif : 12 » = « 12 salariés » ; « 12 m3 de béton et 3 tonnes » ≠ « 12 tonnes ») ; « 85 k€ » =
   « 85 000 € » ; les sigles courts (RGE, MASE, PEFC) ne se trouvent jamais au milieu d'un mot.
   Phrase sur le marché : rapprochée du dossier de l'acheteur (toutes les pièces lues).
4. **Recalcul** : un pourcentage ou un total absent tel quel est recalculé à partir des nombres de la
   phrase reliés à une source, puis de ceux des faits cités (jamais une année, jamais un nombre sur
   lui-même) ; juste à l'arrondi écrit près → « calculé à partir de vos faits » (« 6 sur 12 font
   50 % ») ; sinon, si la phrase donne elle-même ses deux nombres : « Le calcul ne tombe pas juste : 6
   sur 12 font 50 %, pas 60 %. » / « Le total ne tombe pas juste : 3 + 15 font 18, pas 20. ».
5. **Engagements** (« nous garantissons », « nous nous engageons », « zéro accident », « 100 % »,
   « sous 24 h », « 24h/24 », « au plus tard », « sans retard ») d'une phrase sur l'entreprise rédigée
   par l'IA : un élément `engagement` « À confirmer : engagement qui vous liera pendant le chantier. »
   (bouton « Je confirme cet engagement » = `relu_par_vous`). Jamais pour une phrase sur le marché, ni
   pour un engagement que vous écrivez vous-même.

Modes : `ia` (rédaction ; un fait non relié est à relire), `raccourci` (un fait garde ce qu'il était
dans la version de départ — sa source, ou « à relire » ; un fait ajouté est à relire : « Raccourcir »
ne blanchit rien), `utilisateur` (« J'écris moi-même » : vos faits sont vos déclarations « déclaré par
vous », un fait déjà à relire le reste même réécrit, un fait relié garde sa source). « Relu par vous »
est repris pour le même fait dans la même phrase (« raccourci » : même fait, même unité).

Messages (jamais « vérifié ») : `message` = « Adjugo ne trouve pas d'où vient ce fait : relisez-le. »
(phrase sur l'entreprise) ou « Adjugo ne retrouve pas ce fait dans le dossier de l'acheteur :
relisez-le. » (phrase sur le marché) ; `detail` facultatif : « Ce fait figure dans le dossier de
l'acheteur : il ne prouve rien sur votre entreprise. », « Ce fait n'apparaît que dans votre
estimation… », « La source de ce fait n'est plus utilisable (preuve retirée ou expirée, document
retiré) : relisez-le ou ajoutez une source. », « Le renvoi F99 ne correspond à aucun fait remis à
Adjugo. », ou le recalcul.

## 3. Ce qui est rangé et ce que l'API rend

Colonne `faits` d'une version (PRIVÉE, auteur seulement) = TOUS les faits relevés :

```json
{"id": "a1b2c3d4e5f6", "fait": "2 nacelles", "type": "chiffre", "phrase": "Nous disposons de 2 nacelles .",
 "statut": "avec_source", "message": "déclaré par vous", "a_propos": "entreprise",
 "source": {"ref": "F1", "type": "declare", "libelle": "déclaré par vous", "cite": true,
            "extrait": "Matériel : Nacelle articulée ; quantité : 2 ; en propre", "preuve_id": 12}}
```

- `statut` : `a_relire` · `relu_par_vous` (forme d'A0, bloquent l'export tant qu'à relire) ·
  `avec_source` (relié : n'est jamais compté « à relire »). `type` : ceux d'A0 + `engagement`.
- `source` : `ref`, `type`, `libelle`, `cite`, et selon le type `lien` (preuve documentée :
  `/api/preuves/{id}/passage` ; justificatif : `/api/documents/{id}/download` ; source publique : son
  URL), `doc_nom`, `extrait` (passage autour du fait), `preuve_id`, `chunk_id`, `detail` (calcul),
  `partenaire`. Une version relevée par A0 (avant la vague 3) n'a pas de clé `source` : pas de compteur.
- À la LECTURE (état, partie, blocage, export, dossier commun), un fait relié à une preuve retirée,
  expirée ou dont le document a disparu (ou à un extrait retiré) redevient À RELIRE (même `id`, `detail`
  « source plus utilisable ») : il bloque l'export, change `etat_hash` (une dérogation ne vaut plus), et
  « Je l'ai relu » s'applique. « Recontrôler » l'enregistre.

API (dans `Partie.version_courante`, pour l'auteur) :
- `faits` : les éléments à relire ou relus (forme d'A0, + `detail`, `a_propos`) — inchangé pour l'écran
  d'A0 ; `faits_a_relire` les compte.
- `controle` : `{"libelles": false}` par défaut ; avec les libellés : `{"libelles": true, "total",
  "avec_source", "sans_source", "engagements", "message": "Faits avec une source : 7 sur 8"}` (aussi
  au niveau de la partie : `Partie.controle`).
- `faits_sources` : les faits reliés (seulement avec les libellés).
- État de l'atelier : `sources_faits` = `{"libelles", "bulle", "preuves_ecartees": [{ref, id, nature,
  raison, message}]}` (preuves acceptées qu'Adjugo n'utilise pas : expirée, document retiré).

**Libellés positifs et compteur : `ATELIER_LIBELLES_SOURCES=1`, désactivés par défaut.** Étude § 6.5,
calibration : le jeu de phrases piégées passe (60 pièges, zéro présenté comme « trouvé dans vos
documents », test en CI) ; la mesure des fausses alertes sur les 20 mémoires réels (accord écrit des PME)
reste à faire par Mathys (§ 6) ; jusque-là l'atelier garde l'affichage d'A0 (« à relire » seulement).
Le contrôle, lui, est celui de A dès maintenant (renvois, unités, recalcul, engagements).

## 4. Routes (`/api/atelier/{pid}/sections/{sid}`)

| méthode | route | corps | réponse |
|---|---|---|---|
| POST | `/controle` | — | Partie. Relit les sources de la version courante, sans IA, sans nouvelle version (une preuve ajoutée relie le fait qu'elle contient ; retirée ou expirée : à relire). 409 `redaction_en_cours`, 422 `partie_vide`. |
| GET | `/faits/{fid}/sources` | — | `{fait, preuves: [{ref, id, nature, texte, source_libelle}], proposition: {natures, nature, valeur}, natures: [{code, libelle, champs, requis}]}` — les preuves utilisables qui CONTIENNENT ce fait, et la fiche « déclaré par vous » proposée (« 15 compagnons » → chiffre clé `{libelle: "Compagnons", valeur: 15}`). |
| POST | `/faits/{fid}/source` | `{preuve_id}` ou `{nature, valeur}` | `{fait, section}`. Relie à la preuve (422 `preuve_sans_ce_fait` si elle ne contient pas le fait ; 404 `preuve_introuvable` si elle n'est plus utilisable), ou crée la preuve « déclaré par vous » dans « Mes preuves » puis recontrôle — la fiche doit dire le fait tel qu'il est écrit (même nombre, même unité), sinon 422 `fiche_sans_ce_fait` et RIEN n'est créé ; erreurs du socle (`champ_*`) telles quelles. 409 `engagement` (un engagement se confirme, il ne se prouve pas par une fiche). Le texte n'est jamais modifié. |
| POST | `/faits/{fid}` | `{statut}` | inchangé ; 409 `fait_avec_source` pour un fait relié (sauf si sa source n'est plus utilisable). |

Isolation : 404 pour un autre compte (marché, partie, fait). Démo : 403 sur les deux POST (liste
`app/core/demo_guard.py`). Export : `clean_markdown` retire `[F3]`, `[P1]`, `[E2]`, `[C4]`, `[G1]`,
`[F3, S2]` et tout « [CV F#] » resté.

## 5. Écran (atelier, colonne de droite, privée)

- Toujours : « À relire » (A0) avec, par élément, le type (« Engagement » compris), la phrase, le
  message, le `detail`, et **Corriger** / **Retirer** (l'utilisateur modifie le texte), **Ajouter une
  source** (pas pour un engagement), « Je l'ai relu » / « Je confirme cet engagement » ; bouton
  **Recontrôler** ; les preuves de « Mes preuves » qui ne servent pas (et pourquoi).
- « Ajouter une source » : « Relier à une de vos preuves » (celles qui contiennent le fait) et « Le
  déclarer vous-même » (type de fiche, champs principaux pré-remplis, « Enregistrer dans « Mes
  preuves » ») ; bulle (i) : la fiche doit dire le fait tel qu'il est écrit ; pour un passage de vos
  documents ou un justificatif, passer par « Mes preuves », puis « Recontrôler ». Jamais l'IA.
- Avec les libellés : en tête « Faits avec une source : 7 sur 8 » + bulle (i) « Adjugo relie chaque
  chiffre, nom, certification et engagement à l'endroit où il l'a trouvé. Il ne sait pas si ce document
  est à jour, et il ne juge pas les phrases générales : relisez-les. » (aussi, discret, sous le titre de
  la partie) ; « Faits avec une source (n) » replié : le fait, son renvoi, son libellé, le document,
  « Voir le passage » (passage exact, avant et après) ou « Voir le justificatif ».
- Dans le texte, chaque renvoi est une petite étiquette (`F3`, `S1`…) : un clic montre la source.
- 375 px : la colonne passe sous le texte, les boutons se replient ; sur téléphone, lire, confirmer,
  ajouter une source et recontrôler restent possibles (pas d'édition du texte).

## 6. Calibration et mesure (étude § 6.5, § 8)

- **Jeu de pièges** (`tests/pieges_sources.py`, 60 phrases, sources et dossier inventés) : copies
  d'exigences en « nous », objectifs du dossier repris, paraphrases, calculs faux, unités écrites
  autrement, nombres en lettres, matériel, certifications et noms absents, renvois faux, mauvais type de
  source, phrase sur l'entreprise déguisée, phrase sur le marché mal recopiée, tableaux. Exigé : ZÉRO
  piège présenté comme « trouvé dans vos documents » (ni « justificatif déposé »), et chacun à relire ;
  plus 10 faits justes reliés au bon endroit. `python scripts/mesure_fausses_alertes.py pieges`.
- **Fausses alertes sur 20 vrais mémoires** (Mathys, avec l'accord écrit de chaque PME, anonymisés,
  durée limitée — un mémoire sans `accord.json` valable est ignoré) :
  `python scripts/mesure_fausses_alertes.py preparer calibration/ --sortie mesure/`, annoter la colonne
  « verdict » (`vraie` / `fausse`), puis `… bilan mesure/` → fausses alertes par page (objectif < 1),
  inventions ou oublis détectés, part des faits avec une source ; `bilan.json` ne contient aucun texte
  (protocole « omissions et inventions » publiable). Objectif atteint sur 20 mémoires →
  `ATELIER_LIBELLES_SOURCES=1`. Sinon on garde l'affichage d'A0, sans assouplir en silence.

## 7. Limites assumées

- Une invention sans chiffre, nom, certification ni matériel passe (la bulle le dit).
- Un fait relié est ÉCRIT dans la source ; il n'est pas pour autant vrai ni à jour.
- Un fait non cité peut être relié à une fiche qui contient la même valeur avec la même unité pour une
  autre raison (« 12 salariés » formés ≠ effectif de 12) : jamais un libellé « vérifié », et le libellé
  dit d'où vient la valeur.
- Les faits construits à la volée (profil, équipe, chiffrage, partenaires) sont relus à chaque contrôle,
  pas à chaque lecture : un profil modifié depuis ne change le libellé qu'au prochain « Recontrôler ».
- Vague 4 : les preuves d'un partenaire (`proprietaire_invite_id`) ne sont jamais remises ici ; le
  compteur « 6 faits trouvés dans les documents du couvreur » côté chef de file reste à faire.
