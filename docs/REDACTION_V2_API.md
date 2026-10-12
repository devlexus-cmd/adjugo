# Rédaction, vague 2 — contrat d'API de l'atelier du dossier de présentation

Ce document est le contrat entre le serveur (fait) et les écrans (à faire). Il décrit les routes,
les états, les erreurs et ce que l'écran doit afficher. Source de vérité du code :
`app/routers/atelier.py` (routes) et `app/services/atelier.py` (règles). Étude :
`etudes/redaction.md` §6.4 (G + A0), §7 (doctrine), décisions 2b, 6a, 9a, 11.

Vocabulaire à l'écran : « dossier de présentation » (bulle (i) : « le mémoire technique demandé par
l'acheteur »), « partie » (pas « section »), « Rédiger avec Adjugo », « Raccourcir », « J'écris
moi-même ». Jamais « vérifié », jamais de libellé positif sur un fait. Zéro émoji.

---

## 1. Où l'atelier s'affiche

- Page du marché, carte « Dossier de présentation » (juste avant « Mes documents de réponse »),
  avec UN bouton qui ouvre l'atelier (ne pas réorganiser le menu). La carte lit `GET /api/atelier/{project_id}` :
  `dossier == null` → « Préparer le dossier de présentation » (montre `proposition.message`) ;
  sinon → nombre de parties par statut + bouton « Ouvrir ».
- Atelier : à gauche le plan (parties), au centre le texte, à droite les sources de la partie
  (privées), en haut le compteur et l'état de l'export. Sur mobile (375 px) : lire et valider
  seulement (pas d'édition de texte, pas de rédaction).
- « Mon savoir-faire » reste une bibliothèque de documents : son ancien bouton « rédiger » est
  remplacé par un lien vers la page du marché (les routes `/api/knowledge/memoire` et
  `/api/knowledge/memoire-upload` répondent **410** avec ce message).

## 2. Conventions

- Authentification : `Authorization: Bearer <jeton>` (comme le reste de l'API).
- Toutes les routes sont préfixées par `/api/atelier/{project_id}` ; `project_id` est l'id du marché.
- **Isolation** : un marché qui n'appartient pas à l'organisation de l'utilisateur → **404**
  (`marche_introuvable`), y compris pour toutes les sous-routes ; une partie d'un autre dossier →
  404 (`partie_introuvable`). Jamais de 403 qui révélerait l'existence.
- **Erreurs métier** : `detail` est un OBJET `{"code": "...", "message": "...", ...}`. Afficher
  `message` tel quel (français, sans jargon). Exceptions : le quota (`402`, `403` démo / email non
  confirmé) renvoie `detail` en texte, comme le reste de l'application.
- Dates : ISO 8601 UTC (`2026-10-12T09:30:00+00:00`) ; afficher à l'heure de Paris.
- Compte démo (vitrine partagée) : lecture seule. Toute écriture de l'atelier répond **403**
  `detail` texte « La démo est en lecture guidée : créez votre compte gratuit pour préparer votre
  dossier de présentation » (ou « … pour rédiger avec Adjugo »). Seul `GET` reste ouvert.
- Les montants, coûts IA et relevés de débit ne sont jamais renvoyés.

## 3. États

### Statut d'une partie (`statut`, libellé dans `statut_libelle`)

| code | libellé | quand |
|---|---|---|
| `a_ecrire` | À écrire | aucune version |
| `brouillon` | Brouillon | nouvelle version (IA ou utilisateur) jamais validée |
| `relu` | Relue | l'utilisateur a marqué cette version comme relue |
| `valide` | Validée | l'utilisateur a validé CETTE version (qui, quand, empreinte) |
| `a_revalider` | À revalider | une partie validée a changé de texte (toute nouvelle version) |

Remettre exactement le texte validé (même empreinte) redonne `valide`.

### Origine d'une version (`origine`, libellé dans `origine_libelle`)

`ia` (Rédigé avec Adjugo), `utilisateur` (Écrit ou modifié par vous), `raccourci` (Raccourci avec
Adjugo). `ia: true` signifie que l'IA a servi pour ce texte (texte de l'IA, ou texte de
l'utilisateur qui reprend au moins 8 mots d'affilée d'un texte de l'IA de cette partie).

### Source du plan (`dossier.plan_source`, `source_plan` d'une partie)

`cadre` (questions du cadre de réponse, ordre, numéros et intitulés du cadre — ni l'intitulé ni
l'ordre ne se modifient ; une question retirée puis remise reprend SA place), `grille` (critères
retenus dans « Comment vous serez noté », poids tel qu'écrit ou tel que lu par l'utilisateur, avec
sa provenance `poids_source` ; intitulé non modifiable), `libre` (plan simple proposé par Adjugo, sans IA, modifiable),
`utilisateur` (partie ajoutée par l'utilisateur).

### Fait « à relire » (A0)

`{id, fait, type, phrase, message, statut}` — `type` : `chiffre`, `nombre_en_lettres`,
`certification`, `nom_propre`, `materiel` ; `message` : « Adjugo ne trouve pas d'où vient ce
fait : relisez-le. » ; `statut` : `a_relire` ou `relu_par_vous` (+ `relu_par`, `relu_le`).
Un élément `{"id": "reste", "type": "reste", "nombre": n, "message": "Et n autres faits à relire,
non détaillés…"}` compte les faits au-delà de 2 000 (garde-fou de stockage) : il bloque l'export
comme les autres et ne se marque jamais « relu ».
Qui parle de quoi : une phrase avec « nous », « notre » ou le nom de l'entreprise parle de
l'entreprise ; une phrase qui RAPPORTE une exigence d'une pièce ou de l'acheteur (« Le CCTP
prévoit… », « Selon le règlement, … ») parle du marché, même dans une partie sur les moyens ;
hors de ces parties, une phrase qui DÉCRIT le lieu ou l'opération (« Le site comprend… ») aussi ;
tout le reste — « Le marché sera exécuté par 15 compagnons », « Commune de Quimperlé : 2021 » —
parle de l'entreprise. Une ligne de tableau est contrôlée en entier (un nombre seul prend le
libellé de sa ligne pour unité) ; un nom propre en tête de phrase (deux mots à majuscule) ou après
« M. » est contrôlé. « Raccourcir » ne blanchit jamais un fait à relire réécrit (« quinze » →
« 15 », « ISO 14001 » → « ISO14001 »).
Surligner le fait (orange) dans SA phrase seulement (jamais les autres occurrences de la même
valeur). AUCUN libellé positif : on ne montre que les faits à
relire. Bulle (i) : « Adjugo signale les chiffres, certifications, noms et matériels qu'il ne
retrouve pas dans vos documents, votre profil, votre équipe ou votre chiffrage. Le dossier de
l'acheteur ne compte jamais comme source pour une phrase sur votre entreprise. Il ne juge pas les
phrases générales : relisez-les. »

## 4. Routes

### 4.1 Le dossier

**`GET /api/atelier/{pid}`** — état complet (ou proposition sans rien enregistrer).

Sans dossier :
```json
{"dossier": null, "projet": {"id": 12, "nom": "..."},
 "proposition": {"source": "cadre", "message": "Plan construit sur le cadre de réponse imposé...",
   "fichier_impose": true, "message_fichier": "Ce marché impose son propre fichier de réponse : ...",
   "avertissement_fichier": "Ce marché impose son propre fichier de réponse. Le fichier Word d'Adjugo suit l'ordre, les numéros et les intitulés de ce cadre : recopiez-en le texte dans le fichier de l'acheteur.",
   "criteres_en_attente": 0, "message_en_attente": "", "dossier_present": true,
   "bases": {"auto": true, "cadre": true, "grille": true, "libre": true},
   "grille": [["c1", "Valeur technique", "60 %", "reglement"]],
   "cadre_non_decoupe": false, "criteres_hors_dossier": [{"critere": "Prix", "poids": "40 %", "raison": "..."}],
   "limites": {"document": [...], "chaque_question": [...], "police": {...}, "non_controlees": [...]},
   "sections": [{"numero": "1.1", "intitule": "Encadrement du chantier", "niveau": 2,
                 "parents": [{"numero": "1", "intitule": "Moyens humains"}], "question": "...",
                 "source_plan": "cadre", "critere": "", "poids": "", "partie_de_critere": false,
                 "limite": [{"type": "pages", "valeur": 2, "phrase": "...", "source": "...", "portee": "section"}]}]},
 "quota": {...}}
```
Query facultative `?base=auto|grille|cadre|libre` pour prévisualiser un autre plan. N'offrir que
les bases disponibles (`bases`), les autres désactivées avec leur raison. `avertissement_fichier` :
UNE phrase par cas (plan du cadre, ou autre plan), à afficher telle quelle. `dossier_present:
false` : aucun dossier du marché importé — le message le dit, montrer le chemin vers l'import.
`message_en_attente` : des lignes de « Comment vous serez noté » restent à vérifier (jamais « le
règlement ne donne qu'un critère » dans ce cas).

Avec dossier (forme complète, voir aussi §5) :
```json
{"projet": {"id": 12, "nom": "..."},
 "dossier": {"id": 3, "plan_source": "cadre", "version": 0, "cree_le": "...", "maj_le": "...",
   "plan": {"source", "message", "fichier_impose", "message_fichier", "avertissement_fichier",
            "cadre_non_decoupe", "criteres_hors_dossier", "limites", "base_demandee", "construit_le",
            "bases", "criteres_en_attente", "message_en_attente"},
   "dernier_export": {"le", "par", "format", "nom", "empreinte", "ia", "derogation", "etat_hash"} | null},
 "sections": [Partie, ...],
 "sections_retirees": [{"id", "intitule", "retiree_le", "nb_versions"}],
 "compteur": {"total": {"mots", "caracteres", "caracteres_sans_espaces", "lignes_estimees", "pages",
              "pages_contenu", "page_garde", "pages_sommaire"},
              "police": {"famille", "taille", "connue", "phrase"}, "environ": true, "message": "..."},
 "limites": [Limite, ...],
 "blocage": Blocage,
 "quota": Quota,
 "export": Apercu,
 "dossier_acheteur": {"source": "fichier|extrait|aucun", "present": true, "nom_fichier",
                      "integral": true, "couverture": {"complet": false, "message": "Dossier lu en partie : …"} | null,
                      "message_lecture": "",
                      "pieces": [{"nom", "libelle", "type", "lu_en_entier", "statut", "raison", "pages",
                                  "pages_lues", "remise", "remise_libelle"}],
                      "a_change": false, "message": "", "message_absent": ""},
 "grille": {"nouveaux": [{"id", "critere", "poids", "poids_source"}], "poids": [{"section_id", "critere",
            "ancien", "nouveau", "poids_source"}], "plus_retenus": [{"section_id", "critere"}],
            "message": "...", "peut_appliquer": true} | null,
 "savoir_faire": {"vide": false, "message": ""},
 "statuts": {"a_ecrire": "À écrire", ...},
 "derogations_possibles": [{"code", "libelle"}]}
```
`dossier_acheteur.a_change = true` : le dossier du marché a été réimporté depuis la construction du
plan (comparé à la clé lue POUR LE PLAN, pas à la lecture que le moteur rafraîchit) → proposer
« Reconstruire le plan » (message fourni). `present: false` : aucun dossier du marché importé →
`message_absent` (« Aucun dossier du marché importé : Adjugo rédige sans le règlement ni le cadre
de réponse… ») et le chemin vers l'import ; la bulle de « Rédiger avec Adjugo » le dit aussi.

« Pièces du dossier de l'acheteur lues par Adjugo » (lecture intégrale, `docs/LECTURE_INTEGRALE.md`) :
la couverture HONNÊTE de ce que lit le moteur, toujours celle du dossier actuel (relue si le fichier
a changé ou si une nouvelle lecture intégrale a été rangée depuis). `integral: true` : chaque pièce a
son `statut` de lecture — `lu_en_entier` (avec `pages`), `lu_en_partie` ou `non_lu` — et sa `raison`
en clair (« format non pris en charge (ancien format Word : enregistrez-le en .docx ou en PDF) »,
« scan : aucun texte reconnu »…) ; `remise` dit ce que le moteur en remet à l'IA : `entiere`
(règlements et cadres de réponse, « remise en entier à chaque partie »), `debut` (règlement ou cadre
trop long : son début, le reste cherché par passages), `passages` (« passages choisis pour chaque
partie »), vide (pièce non lue). `couverture.message` : « Dossier lu en entier : N pièces, P pages. »
ou « Dossier lu en partie : … (voir la liste) » — à afficher HORS de la liste repliée quand
`complet` est faux. `integral: false` : `message_lecture` dit pourquoi et comment obtenir la
lecture intégrale — ancienne analyse (« … relancez « Ré-analyser » sur la page du marché (compte
pour une analyse) »), lecture en tâche de fond pas encore terminée, ou seul l'extrait de l'analyse
disponible ; `statut` y vaut `lu_en_entier` ou `lu_en_partie` (= remis en entier ou seulement son
début). Le texte d'une lecture intégrale n'est jamais recopié dans la base du dossier, ni celui de
ses cadres de réponse (il reste dans le stockage du marché, supprimé avec lui ; le plan le relit de
là) : seul « le cadre se découpe en questions » y est gardé. « Pas encore terminée » n'est dit que
si la tâche de lecture tourne vraiment (une lecture interrompue par un redémarrage ne l'est plus).
L'écran recharge l'atelier ouvert sur ce marché à la fin d'une lecture (terminée ou en échec).
`grille` non nul : « Comment vous serez noté » a changé depuis le plan (critère confirmé, poids
saisi ou modifié, critère écarté) → `message` et, si `peut_appliquer`, « Mettre le plan à jour »
(`POST /plan/grille`), sans reconstruire. `savoir_faire.vide` : « Mon savoir-faire » est vide →
le dire avant « Rédiger avec Adjugo » (lien vers « Mon savoir-faire ») et confirmer avant la
première analyse.

**`POST /api/atelier/{pid}`** `{"base": "auto"}` → **201** + état complet. `base` : `auto` (cadre
imposé > grille > plan simple), `cadre`, `grille`, `libre`. Erreurs : 409 `dossier_existe`,
422 `base_invalide`.

**`POST /api/atelier/{pid}/plan`** `{"base": "libre", "remplacer": false}` → état complet.
Reconstruit le plan ; les parties actuelles sont RETIRÉES (jamais supprimées, remettables) — sauf
la partie d'un partenaire (vague 4), jamais retirée par un autre que son auteur. 409
`plan_remplacement_a_confirmer` si une partie a du texte et `remplacer` est faux → demander
confirmation (« Reconstruire le plan retire les parties actuelles ; leurs textes restent dans
l'historique ») puis renvoyer avec `remplacer: true`. 409 `redaction_en_cours` si une rédaction
tourne.

**`POST /api/atelier/{pid}/plan/grille`** → état complet + `"application": {"ajoutees", "poids_mis_a_jour"}`.
Met le plan à jour d'après « Comment vous serez noté » SANS rien retirer : une partie de plus par
critère confirmé depuis la construction du plan (à la fin, déplaçable), le poids et sa provenance
repris pour les parties existantes. Aucune IA, aucun débit. 409 `plan_du_cadre` (le cadre
commande), 409 `rien_a_appliquer`.

**`PUT /api/atelier/{pid}/options`** `{"page_garde": bool?, "sommaire": bool?}` → `{"options": {...}}`.
Options de l'export (défaut : les deux vrais). Le compteur de pages en tient compte.

**`GET /api/atelier/{pid}/compteur`** → `{"compteur", "sections": [{"id", "titre", "compteur"}], "limites", "blocage"}`.

### 4.2 Les parties

`Partie` :
```json
{"id": 41, "ordre": 0, "numero": "1.1", "numero_affiche": "1.1", "intitule": "Encadrement du chantier",
 "titre": "1.1 Encadrement du chantier", "niveau": 2, "parents": [{"numero": "1", "intitule": "Moyens humains"}],
 "question": "Encadrement du chantier Présentez l'encadrement du chantier (2 pages maximum).",
 "source_plan": "cadre", "critere": "", "critere_id": "", "poids": "", "poids_source": "",
 "partie_de_critere": false, "lot": "",
 "limite": [{"type": "pages", "valeur": 2, "phrase": "...", "source": "...", "portee": "section"}],
 "auteur": {"type": "organisation", "invite_id": null, "libelle": "Votre entreprise"},
 "statut": "brouillon", "statut_libelle": "Brouillon", "intitule_modifiable": false,
 "peut_ecrire": true, "prive_visible": true,
 "redaction_en_cours": {"job_id": 77, "action": "rediger", "statut": "running"} | null,
 "validation": {"version_id", "empreinte", "le", "par"} | null,
 "lock_version": 3, "retiree": false,
 "version_courante": Version | null, "nb_versions": 2,
 "a_completer": 1, "faits_a_relire": 2,
 "compteur": {"mots", "caracteres", "pages_estimees", "lignes_estimees"} | null}
```
`Version` : `{"id", "numero", "origine", "origine_libelle", "ia", "empreinte", "coupe", "cree_le",
"auteur_user_id", "restaure_de", "a_completer", "faits_a_relire", "texte", "sources": [{"ref",
"doc_name", "chunk_id", "extrait"}], "faits": [Fait]}` — `sources` et `faits` sont PRIVÉS (présents
seulement si `prive_visible`). `coupe: true` : l'IA a été interrompue ; le texte finit par
« [À compléter : la rédaction a été interrompue ici…] ».

Le poids d'un critère s'affiche tel quel (`poids`, chaîne) avec sa provenance : `poids_source =
reglement` → « poids écrit dans le règlement : 60 % » ; `utilisateur` → « poids lu par vous :
40 % » (saisi en confirmant la ligne dans « Comment vous serez noté », dit aussi à l'IA) ; vide =
« aucun poids écrit dans le règlement » (ne rien supposer). `partie_de_critere: true` : bulle (i) « Découpage proposé par
Adjugo : il n'est pas imposé par l'acheteur ».

Routes :
- `POST /sections` `{"intitule", "apres_section_id"?}` → **201** Partie (`source_plan: utilisateur`).
- `PATCH /sections/{sid}` `{"intitule"?, "position"?}` → Partie. 409 `intitule_impose` (partie du
  cadre ou de la grille), 409 `ordre_impose` (plan du cadre), 422 `intitule_invalide`.
- `DELETE /sections/{sid}` → `{"ok": true, "section_id", "retiree": true}` (retirée, versions gardées).
- `POST /sections/{sid}/remettre` → Partie.
- `GET /sections/{sid}` → Partie + `"versions": [Version sans texte, la plus récente d'abord]`.
- `GET /sections/{sid}/versions/{vid}` → Version (avec texte). 404 `version_introuvable`.
- `PUT /sections/{sid}/texte` `{"texte", "base_version_id"}` → Partie. « J'écris moi-même » ou
  modification : nouvelle version, aucune IA. `base_version_id` = id de la version courante que
  l'utilisateur a modifiée (`null` si la partie était vide). 409 `texte_modifie_entre_temps` si
  elle a changé entre-temps (rechargez sans perdre le texte saisi à l'écran : proposer de le
  copier), 409 `redaction_en_cours`, 409 `partie_retiree`, 422 `texte_trop_long` (60 000
  caractères), 403 `partie_d_un_partenaire`. Envoyer un texte identique ne crée pas de version.
- `POST /sections/{sid}/restaurer` `{"version_id", "base_version_id"}` → Partie (copie en
  nouvelle version, `restaure_de`).
- `POST /sections/{sid}/relu` `{"version_id"}` → Partie (statut `relu`).
- `POST /sections/{sid}/valider` `{"version_id"}` → Partie (statut `valide`, inscrit au journal
  chaîné). 409 `texte_modifie_entre_temps`, 422 `partie_vide`. Valider est permis même avec des
  points ouverts : l'export les bloque.
- `POST /sections/{sid}/faits/{fait_id}` `{"statut": "relu_par_vous" | "a_relire"}` →
  `{"fait", "section": Partie}`. 404 `fait_introuvable`, 422 `statut_invalide`. Les autres
  traitements (corriger, retirer) se font en modifiant le texte.

### 4.3 Le moteur (tâches de fond)

- `POST /sections/{sid}/rediger` `{"accepte_debit": false}` → **202** `{"tache": Tache, "quota": Quota, "section_ids": [sid]}`.
- `POST /sections/{sid}/raccourcir` `{"cible_mots"?, "accepte_debit": false}` → **202** idem.
  Cible par défaut : la limite de la partie (mots, caractères, lignes ou pages converties), sinon
  70 % de la longueur actuelle. 422 `partie_vide`, `deja_assez_court`, `cible_invalide` (< 30 mots).
- `POST /rediger` `{"section_ids"?: [..], "accepte_debit": false}` → **202** idem. Sans liste :
  toutes les parties « à écrire ». 422 `aucune_partie`.
- `GET /taches/{job_id}` → `Tache` : `{"id", "kind": "atelier_rediger|atelier_raccourcir",
  "status": "pending|running|done|error", "label", "result", "error", "created_at"}`. Interroger
  toutes les 2 s. `result` (si `done`) : `{"sections": [{"section_id", "ok", "version_id",
  "statut", "coupe", "a_completer", "faits_a_relire", "extraits_fournis"}], "echecs": n,
  "message"}` (`message` non vide si des parties ont échoué : rien n'a été débité pour elles).
  `error` (si `error`) : message à afficher tel quel (« La rédaction n'a pas abouti : le service
  d'IA est indisponible pour le moment. Rien n'a été débité… »).
- Erreurs au lancement : 409 `redaction_en_cours` (une rédaction tourne déjà sur la partie),
  409 `premiere_redaction_en_cours` `{job_id}` (la première rédaction du dossier, celle qui porte
  l'analyse, tourne encore : attendre sa fin), 409 `reessayer` (dossier modifié au même instant),
  409 `debit_a_confirmer` `{cout}` (voir quota), 409 `partie_retiree`, 403
  `partie_d_un_partenaire`, 403 `email_non_confirme`, 402 (quota atteint, `detail` texte),
  403 démo (« La démo est en lecture guidée… »).
- Pendant une rédaction, la partie est verrouillée (`redaction_en_cours` non nul) : désactiver
  l'édition et les boutons de cette partie.
- Échec (`status: error`, ou une partie `ok: false` dans `result.sections`) : en plus du message
  éphémère, le message reste affiché DANS la partie concernée jusqu'à la prochaine action sur elle
  (rédiger, raccourcir, écrire, enregistrer, marquer relue, valider, traiter un fait, revenir à une
  version, retirer).
- Confirmations (nouvelle version, « Mon savoir-faire » vide, abandon d'une modification, valider
  avec des points ouverts, revenir à une version, retirer une partie) : la fenêtre de confirmation
  de l'application (comme « Marquer déposé »), jamais celle du navigateur ; une seule fenêtre réunit
  tout ce qu'il faut savoir avant de lancer.

Ce que fait le moteur (à dire dans une bulle (i) près de « Rédiger avec Adjugo ») : avec la lecture
intégrale du dossier du marché (`dossier_acheteur.integral`), il lit TOUS les règlements et TOUS les
cadres de réponse en entier (jusqu'à `ATELIER_DOSSIER_MAX_CARACTERES` = 240 000 caractères, ≈ 80 000
tokens ; au-delà, le début de la pièce et le reste par passages), puis, pour chaque partie, les
passages des autres pièces les plus proches de la partie (`ATELIER_PASSAGES` = 8 passages
d'≈ 1 400 caractères, recherche sans IA dans toutes les pièces lues, pièces remises en entier
écartées), avec une note qui dit ce qui est remis en entier, par passages et non lu (pour l'IA
seulement : n'affirmer jamais qu'une exigence est absente, n'écrire jamais de remarque sur la
lecture du dossier dans le texte, qui va à l'acheteur).
Le bloc commun (règlements et cadres) vient en tête et est mis en cache de prompt (5 minutes) : le
premier appel l'ÉCRIT (1,25 × le prix d'entrée), les appels suivants dans les 5 minutes le RELISENT
(0,1 ×). « Rédiger tout » rédige donc la première partie seule, puis les autres en parallèle (3 à la
fois) : une seule écriture. Une partie rédigée seule, plus de 5 minutes après la précédente, paie
l'écriture sans relecture (voir le coût au § 4.4). Sans lecture intégrale (ancienne analyse, lecture en cours) :
règlement et cadre en tête et en entier, le reste borné (le début des autres pièces) ; sans dossier
du marché importé, il le dit. Il s'appuie seulement sur vos documents, votre profil, votre équipe
(noms remplacés par des étiquettes avant l'envoi), votre chiffrage et les parts envoyées par vos
partenaires ; tout fait absent est écrit « [À compléter : …] ». Le dossier de l'acheteur, passages
compris, ne prouve jamais rien sur l'entreprise (un chiffre qu'il contient reste « à relire » dans
une phrase sur l'entreprise). Le texte précédent est gardé dans l'historique.

### 4.4 Quota (décision 6a)

`Quota` : `{"analyse_debitee", "regenerations_gratuites", "regenerations_utilisees",
"regenerations_restantes", "regenerations_payantes", "message", "prochaine_refonte_coute",
"premieres_incluses", "premieres_restantes"}`.
- La première action de l'IA sur le dossier compte pour 1 analyse (une seule fois pour tout le
  dossier). Elle comprend la PREMIÈRE rédaction de chaque partie du plan, au plus autant que de
  parties actives (`premieres_incluses`). Afficher `message` avant le premier clic.
- Une refonte : refaire une partie déjà rédigée par l'IA (rédiger ou raccourcir), ou rédiger une
  partie de plus que celles comprises (plan reconstruit, partie ajoutée puis retirée…) : le
  plafond ne se contourne pas. Gratuite jusqu'à `regenerations_gratuites` fois par dossier (10 par
  défaut, variable `ATELIER_REGEN_GRATUITES`).
- Tant que la tâche qui porte l'analyse du dossier tourne, aucune autre action de l'IA ne démarre
  (409 `premiere_redaction_en_cours`) : jamais deux analyses pour un dossier, jamais une rédaction
  gratuite si la première tombe en panne. L'analyse n'est jamais rendue si l'IA a déjà produit un
  texte pour ce dossier.
- Au-delà : 409 `debit_a_confirmer` `{"cout": n, "message"}` → afficher le message et un bouton
  « Confirmer » qui renvoie la même requête avec `"accepte_debit": true`.
- Panne de l'IA : tout est rendu (analyse comprise si c'était la première action) ; échec partiel :
  seules les parties en échec sont rendues.

**Coût IA d'un dossier avec la lecture intégrale (recalculé le 12/10/2026, interne).** Hypothèses :
Sonnet à 3 $ / 15 $ par million de tokens (entrée / sortie), cache écrit à 1,25 ×, relu à 0,1 ×,
3,3 caractères par token, 1 100 tokens de sortie par partie, ≈ 23 400 caractères propres à chaque
partie (consigne, faits, extraits, 8 passages) ; messages construits par le vrai code. Le dossier
garde le coût mesuré dans `dossiers_presentation.cout_ia` (`tokens_entree` hors cache,
`tokens_cache_ecrits`, `tokens_cache_lus`, `cout_estime_usd`).

| Dossier | Bloc en cache | Écriture | Relecture | 20 parties : « Rédiger tout » + 10 refontes isolées | 20 parties une à une (> 5 min) + 10 refontes |
|---|---|---|---|---|---|
| Courant (RC 40 000 + cadre 15 000 car.) | ≈ 57 000 car. | 0,10 $ | 0,04 $ | 1,95 $ (≈ 1,7 €) | 3,08 $ (≈ 2,6 €) |
| Plusieurs lots (RC 60 000 + modificatif 30 000 + 4 cadres de 25 000) | ≈ 192 000 car. | 0,26 $ | 0,06 $ | 3,87 $ (≈ 3,3 €) | 7,68 $ (≈ 6,6 €) |
| Plafond (`ATELIER_DOSSIER_MAX_CARACTERES` = 240 000) | ≈ 242 000 car. | 0,31 $ | 0,06 $ | 4,58 $ (≈ 3,9 €) | 9,39 $ (≈ 8,1 €) |

Au plafond avec 60 parties : « Rédiger tout » + 10 refontes ≈ 6,97 $ (≈ 6,0 €). Avant la fusion
(dossier borné à 80 000 caractères, sans cache) : ≈ 0,10 $ par appel, 3,0 $ pour 20 parties + 10
refontes. Avant le correctif « première partie seule », « Rédiger tout » écrivait le cache 3 fois
(+ 0,4 à 0,5 $ par dossier à plusieurs lots). Repère de la décision 6a : une analyse hors forfait
vaut 5 € HT. Un dossier courant reste nettement en dessous ; un dossier à plusieurs lots ou au
plafond le dépasse si l'utilisateur rédige partie par partie à plus de 5 minutes d'intervalle. À
trancher sur le coût MESURÉ (`cout_ia`) : ramener `ATELIER_REGEN_GRATUITES` à 5, abaisser
`ATELIER_DOSSIER_MAX_CARACTERES` (≈ 120 000 : environ 0,17 $ l'écriture), ou ne remettre en entier
que le règlement et le cadre du lot visé.

### 4.5 Limites, blocage, dérogation, export

`Limite` : `{"portee": "document|section", "section_id", "titre", "type": "pages|mots|caracteres|lignes",
"valeur", "mesure", "environ", "depassee", "phrase", "source", "message", "avertissement"}`.
`message` est prêt à afficher (« Dossier de présentation : environ 9 pages pour 8 au plus (page de
garde et sommaire compris). »). Afficher la `phrase` du règlement en bulle (i). Les pages sont
celles du PDF produit avec la police du règlement (sinon Arial 11) : toujours dire « environ ».

`Blocage` :
```json
{"bloque": true, "peut_exporter": false, "etat_hash": "64 hex",
 "raisons": [
   {"code": "parties_vides", "nombre": 1, "sections": [{"section_id", "titre"}], "message": "1 partie sans texte."},
   {"code": "attente_partenaire", "nombre": 1, "sections": [{"section_id", "titre"}], "message": "1 partie en attente du partenaire qui la rédige."},
   {"code": "a_completer", "nombre": 3, "sections": [{"section_id", "titre", "nombre"}], "message": "Il reste 3 passages « À compléter »."},
   {"code": "faits_a_relire", "nombre": 2, "sections": [...], "message": "2 faits à relire n’ont pas été traités."},
   {"code": "limite_depassee", "nombre": 1, "limites": [Limite], "message": "...", "avertissement": "L'acheteur peut juger votre offre irrégulière."},
   {"code": "dossier_vide", "sections": [], "message": "Le dossier de présentation n'a aucune partie."}],
 "derogation": {"raison", "raison_libelle", "texte", "raisons", "le", "avertissement"} | null,
 "avertissements": [
   {"code": "fichier_impose", "message": "Ce marché impose son propre fichier de réponse. Le fichier Word d'Adjugo suit l'ordre, les numéros et les intitulés de ce cadre : recopiez-en le texte dans le fichier de l'acheteur."},
   {"code": "non_valide", "nombre": 2, "sections": [{"section_id", "titre", "statut"}], "message": "Dossier de présentation non validé : 2 parties à valider."}]}
```
- `peut_exporter` : aucune raison, ou une dérogation valable pour CET état (`etat_hash`). La carte
  du marché ne dit « Prêt à exporter » que sans dérogation et sans partie à valider ; sinon
  « Export avec dérogation » (et ce qui reste ouvert) ou « N parties à valider ».
- Au moindre changement (texte, fait traité, option, limite), `etat_hash` change et la dérogation
  ne vaut plus : l'écran le dit (« Le dossier a changé depuis votre dérogation »).

**`POST /derogation`** `{"raison", "texte", "etat_hash"}` → `{"derogation", "blocage"}`.
`raison` ∈ `derogations_possibles` : seulement celles qui répondent à CE qui bloque —
`completerai_dans_word` (passages « À compléter »), `relu_moi_meme` (faits à relire),
`reduirai_dans_word` (limite dépassée), `redigerai_dans_word` (parties vides),
`partenaire_dans_word` (partie en attente d'un partenaire) — plus toujours `depot_en_l_etat`
(« Je dépose en l'état, en connaissance de cause. ») et `autre`. `texte` : 3 à 300 caractères, obligatoire.
Inscrite au journal chaîné AVANT d'être retenue. Pour une limite dépassée, la réponse porte
`avertissement` = « L'acheteur peut juger votre offre irrégulière. » : l'afficher dans la boîte de
dérogation, avant la confirmation. Erreurs : 422 `raison_invalide`, `texte_invalide` ; 409
`etat_modifie` (`etat_hash` fourni), `rien_a_deroger`, `dossier_vide` ; 503 `journal_indisponible`.

**`POST /export`** `{"format": "docx|pdf", "etat_hash"?}` → **200** octets du fichier
(`Content-Disposition` avec le nom du règlement, ex. `Mémoire justificatif.docx`), ou :
- 409 `export_bloque` `{"raisons": [...], "etat_hash", "derogations_possibles": [{"code", "libelle"}]}` ;
- 409 `etat_modifie` si `etat_hash` est fourni et ne correspond plus (recommandé : l'envoyer) ;
- 422 `format_invalide`.
Le fichier est aussi rangé dans le dossier du marché (« Mémoire technique ») et compte pour la
liste des pièces ; l'export est inscrit au journal.

`Apercu` (`etat.export`, à montrer AVANT l'export — décision 9a) :
```json
{"nom_fichier_docx": "Mémoire justificatif.docx", "nom_fichier_pdf": "Mémoire justificatif.pdf",
 "titre": "Mémoire justificatif", "ia_utilisee": true, "mention_ia": "Préparé avec assistance IA",
 "proprietes": {"titre": "Mémoire justificatif", "auteur": "", "sujet": "Préparé avec assistance IA", "mots_cles": "assistance IA"},
 "message_ia": "Des textes ont été préparés avec l'aide d'Adjugo : le fichier le dira dans ses propriétés (« Préparé avec assistance IA »).",
 "police": {"famille": "Arial", "taille": 11, "connue": true, "phrase": "..."},
 "options": {"page_garde": true, "sommaire": true}, "fichier_impose": true, "plan_du_cadre": true, "logo": false}
```
Sans IA : `ia_utilisee: false`, `mention_ia: ""`, propriétés sans mention.

Le fichier : page de garde sobre (logo de l'entreprise s'il existe : document du coffre-fort dont
le nom contient « logo », PNG ou JPEG < 2 Mo ; titre du règlement ; marché ; acheteur ; candidat ;
mois), sommaire, titres (numéros et intitulés du cadre quand il est imposé, titres du cadre
au-dessus des questions), listes, tableaux simples ; aucun renvoi [S1], aucune marque interne,
propriétés sans auteur ni outil.

### 4.6 Dossier commun (ZIP, formulaires)

`POST /api/sourcing/documents` n'appelle plus l'IA : le dossier de présentation vient de
l'atelier, avec la version VALIDÉE de chaque partie de préférence (sinon son texte courant ; pour
la partie d'un partenaire, seulement son texte envoyé).
Avertissements possibles dans `dossier.warnings` :
- « BLOQUANT — Dossier de présentation non rédigé : préparez-le dans l'atelier (sur la page du
  marché, carte « Dossier de présentation »)… » (pas de dossier) ; l'écran met à côté le bouton
  « Ouvrir l'atelier du dossier de présentation » (page du marché comme parcours « Trouver des
  marchés ») ;
- « BLOQUANT — Dossier de présentation non joint : … » (export bloqué sans dérogation : aucun
  fichier joint) ;
- « BLOQUANT — Dossier de présentation non validé : N parties à valider… » (parties jamais
  validées ; fichiers joints avec leur texte courant) ;
- « Dossier de présentation : « 2. Méthodologie » a été modifiée depuis la validation : le dossier
  joint le texte VALIDÉ… » ;
- « Dossier de présentation joint avec une dérogation enregistrée : … ».
`dossier.memoire_fichiers` liste les fichiers joints (vide si non joint).

## 5. Préparation de la vague 4 (groupement)

Chaque partie a un auteur : `auteur.type` = `organisation` (aujourd'hui) ou `invitation` (un
partenaire, demain). Pour une partie dont l'utilisateur n'est pas l'auteur : `prive_visible:
false`, `peut_ecrire: false`, `version_courante` = seulement le texte VALIDÉ (envoyé) sans sources
ni faits, `versions: []`, et toute écriture → 403 `partie_d_un_partenaire`. Les écrans doivent
déjà respecter ces drapeaux (ne jamais supposer qu'une partie est éditable).

Côté serveur, UN seul accès au texte commun (`atelier.versions_communes`) : la version courante de
SES parties, la version validée (envoyée) de celle d'un autre auteur, sinon rien. Il sert à
l'export, au compteur, au blocage (`attente_partenaire`), aux limites, à la mention IA, au dossier
commun et à l'export RGPD : un brouillon non envoyé ne sort jamais de chez son auteur. La
reconstruction du plan ne retire jamais la partie d'un autre.

## 6. Mesure « fichier de réponse imposé » (décision 11)

À chaque import réel du dossier du marché, `projects.dce_importe_le` et `dce_fichier_impose` sont
posés — dans `sourcing._finish_analysis`, commun à l'analyse pendant la requête ET en tâche de fond
(gros dossier lu en deux temps) : aucun dossier analysé n'échappe à la mesure. Agrégats seulement : `/metrics` (`adjugo_dossiers_importes`,
`adjugo_dossiers_fichier_impose`) et `GET /api/admin/mesures/redaction` (administrateur de la
plateforme) → `{"dossiers_importes", "fichier_impose", "part", "seuil_decision": 0.2}`. On passe au
remplissage du fichier de l'acheteur dès qu'un dossier sur cinq l'impose.

## 7. Exemple de parcours

1. `GET /api/atelier/12` → `dossier: null`, proposition (cadre imposé, 4 questions).
2. `POST /api/atelier/12 {}` → 201, 4 parties `a_ecrire`.
3. `POST /api/atelier/12/rediger {}` → 202, tâche 77 ; `quota.analyse_debitee = true`.
4. `GET /api/atelier/12/taches/77` jusqu'à `done` ; recharger l'état.
5. La partie 1.1 a 2 faits à relire : l'utilisateur corrige le texte (`PUT /texte`) ou marque
   `relu_par_vous` ; il remplit « [À compléter : …] ».
6. `POST /sections/41/valider {"version_id": 102}` pour chaque partie.
7. `GET /api/atelier/12` → `blocage.peut_exporter = true`, `export.mention_ia = "Préparé avec assistance IA"`.
8. `POST /api/atelier/12/export {"format": "docx", "etat_hash": "..."}` → fichier.
