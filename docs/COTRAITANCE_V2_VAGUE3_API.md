# Co-traitance v2 — vague 3 « Vrai réseau de partenaires » : contrat d'API pour le front

> Partie serveur livrée le 08/10/2026 (branche de worktree, non déployée). Ce document suffit pour
> écrire les écrans **sans relire le code serveur**. Code : `app/routers/reseau.py` (routes),
> `app/services/partner_network.py` (profils, vérifications SIRENE / BODACC / DECP, visibilité,
> historique, RGPD, cron), `app/services/partner_matching.py` (classement PUR, déterministe, 0 LLM).
> Migration `p0q1r2s3t4u5`. Tests : `tests/test_reseau_partenaires.py` (24 tests, registres simulés).
> Les JSON ci-dessous sont des réponses **réelles** du serveur (TestClient, registres simulés),
> raccourcies par « … » quand une liste se répète ; seules les adresses email, les jetons et le nom
> d'hôte des liens ont été remplacés par des valeurs lisibles.

## 1. Principes à respecter dans l'interface

- **Un seul pourcentage** à l'écran : le score de groupement (« seul 54 % → avec X 81 % »), obtenu
  par `POST /api/projects/{id}/groupement/simulate`. Le réseau renvoie un **rang** (1, 2, 3…) et des
  **critères** (statut + phrase + source + date) — jamais de note, de total, d'étoile ni de « % ».
  Ne jamais calculer un pourcentage côté front à partir des critères.
- **Confiance vérifiable seulement** : afficher les `badges` et `capacites` tels quels (`label`
  complet, `source`, `date`). Formulations imposées, renvoyées par l'API :
  « Aucun avis de procédure collective trouvé au 08/10 (recherche BODACC) » (jamais « aucune
  procédure »), « Au moins 7 marchés publics publiés dans DECP (au 08/10) », « Inscrite au registre
  RGE (ADEME) au 08/10 — domaine à vérifier », « … : non vérifié » quand le registre n'a pas répondu.
- **Zéro jargon** : « partenaire », « groupement », « chef de file », « présentation en une phrase »
  (jamais « pitch »), jamais « consortium », jamais « réciprocité » ni « matching » à l'écran (dire
  « Publiez votre profil pour voir les partenaires »). Les termes SIREN / SIRET / BODACC / DECP / RGE
  vont dans une bulle (i) avec une phrase simple (ex. « BODACC : le journal officiel où sont publiées
  les procédures collectives »).
- **UI sobre** : zéro émoji (icônes lucide), explications dans une bulle (i) (composant `.tip`
  existant), 16 px entre les blocs, propre à 375 px (aucun débordement horizontal), vrais boutons,
  libellés, focus visible, `aria-live` sur les messages de résultat.
- **Aucune donnée serveur en `v-html` / `innerHTML`** : noms d'entreprise, présentation, intitulés de
  références sont du texte libre saisi par des tiers → `{{ }}` / `textContent` uniquement.
- **Anonymat des recherches** : rien dans l'API ne dit à un profil QUI l'a cherché. L'écran « Mon
  profil » affiche seulement `apparitions_label` (compteur mensuel anonyme).
- **Démo** : aucune écriture (403 « La démo est en lecture guidée : créez votre compte gratuit
  pour … ») et aucun profil réel visible (le compte démo ne peut pas publier).

## 2. Codes et statuts

### Statut du profil (`statut`, `statut_label`)

| Valeur | Libellé (`statut_label`) | Sens |
|---|---|---|
| `aucun` | Pas encore créé | Aucun profil enregistré ; le GET renvoie des valeurs **proposées** (non enregistrées) |
| `brouillon` | Brouillon (non visible dans le réseau) | Enregistré, jamais publié (opt-in : c'est l'état par défaut) |
| `publie` | Publié dans le réseau Adjugo | Visible des entreprises qui ont publié la leur |
| `retire` | Publication retirée (non visible) · *ou* Retiré du réseau : SIRENE indique que l'entreprise a cessé son activité | Retrait volontaire, ou retrait automatique sur réponse positive « cessé » de SIRENE |

### Badges (`badges[]`) et capacités (`capacites[]`)

`badge = {key, label, source, date, niveau}` — `key ∈ sirene | rge | qualiopi | bodacc | decp | adjugo`,
`niveau ∈ ok | info | alerte | non_verifie` (couleur discrète : `ok` vert, `info` neutre, `alerte`
orange, `non_verifie` gris ; jamais d'icône étoile). Afficher `label` tel quel, `source` + `date`
dans la bulle (i). `capacite = {key, label, valeur, source, date}` — `source` vaut « déclaré par
l'entreprise » (date = dernière mise à jour déclarée) ou le registre public.

### Critères du classement (`criteres[]`, toujours dans cet ordre)

`{key, label, statut, detail, source, date}` — `statut ∈ ok | partiel | non | alerte`.

| `key` | `label` | Ce qui est regardé (poids interne, jamais affiché) |
|---|---|---|
| `metier` | Métier du lot | métier déclaré = métier du lot (35) ; à défaut famille CPV proche (20) |
| `zone` | Zone d'intervention | département d'exécution dans les zones déclarées ou siège (25) |
| `fiabilite` | Fiabilité vérifiée (registres publics) | SIRENE actif vérifié < 90 j (8) + aucun avis BODACC trouvé (7) |
| `experience` | Expérience des marchés publics | DECP « au moins N » (≥ 5 : 12, ≥ 1 : 8) + groupements déposés via Adjugo (3) |
| `capacite` | Capacité et disponibilité pour ce lot | rôle accepté (4) + disponibilité (3) + taille de lot (3) |

Seuls les profils dont le critère `metier` n'est pas `non` sont classés. Égalité → ordre alphabétique.
Afficher : rang, puis la liste des critères (`label` en gras, `detail` en texte, icône lucide par
`statut` : `check` / `minus` / `x` / `alert-triangle`), `source` + `date` dans la bulle (i).
Phrase d'explication (bulle (i) à côté du titre) : champ `explication` de la réponse.

### Invitations (`GET /api/projects/{id}/invites` et réponses de création)

Nouveaux champs : `source ∈ manuel | reseau_adjugo | sirene` et `recipient_masque`.

| Source | `token` / `path` | `recipient` | Email |
|---|---|---|---|
| `manuel` | renvoyés (lien à copier) | l'adresse saisie | si adresse + expéditeur confirmé (inchangé) |
| `reseau_adjugo` | **toujours `null`** (le lien n'est jamais remis au chef de file) | `""` + `recipient_masque: true` **tant que le partenaire n'a pas répondu** ; l'adresse apparaît quand il a accepté depuis son compte, prouvé son adresse par code ou soumis sa part | envoyé par Adjugo |
| `sirene` | renvoyés (lien à transmettre) | `""` (Adjugo ne connaît pas l'adresse) | aucun |

Décliner n'est pas répondre : l'adresse d'un partenaire réseau qui a décliné reste masquée.
Libellé UI : « Adresse visible quand le partenaire aura accepté ». Pas de bouton « Copier le lien »
pour `reseau_adjugo` (le bouton « Relancer » existant fonctionne, même texte réseau). La relance
refait les contrôles de l'envoi : chef de file toujours publié (sinon 409 `profil_non_publie`, « Votre
profil partenaire n'est plus publié… »), profil du partenaire publié et paire non masquée (sinon 409
`plus_sollicitable`, motif jamais dit), plafond de sollicitations du profil (429).

## 3. Mon profil partenaire

Authentification `Authorization: Bearer <jwt>`. Profil **par organisation** (un seul, porté par le
propriétaire). Lecture : tous les membres. Écritures (PUT, DELETE, vérifier, publier, retirer) :
**administrateur de l'organisation** seulement → sinon 403 « Seul un administrateur de votre
organisation peut modifier ou publier le profil partenaire. » Limites : GET 120/h, PUT 60/h,
vérifier 10/h (+ 1 vérification / 10 min / profil), publier/retirer 20/h, DELETE 10/h.

### 3.1 `GET /api/reseau/profil`

Sans profil : `exists: false`, valeurs **proposées** depuis le profil entreprise, les critères et le
registre SIRENE (`lookup_company`, délai 5 s, cache 10 min) — rien n'est enregistré.

```json
{
  "exists": false, "profile_id": null, "visible": false,
  "statut": "aucun", "statut_label": "Pas encore créé",
  "identite": {"name": "Le Gall Électricité", "siren": "552100554", "siret": "55210055400012",
               "city": "Quimper", "postal_code": "29000", "departement": "29", "nom_officiel": false},
  "declare": {"metiers": ["electricite"], "codes_cpv": [], "departements": ["29"], "roles_acceptes": ["cotraitant"],
              "disponibilite": "", "dispo_jusqua": null, "lot_max_eur": null, "presentation": "",
              "references_publiques": [], "declared_at": null},
  "hidden_from_sirens": [],
  "verifications": {"sirene": {"label": "SIRENE : non vérifié", "etat": null, "checked_at": null},
                    "bodacc": {"label": "BODACC : non vérifié", "found": null, "checked_at": null},
                    "decp": {"label": "DECP : non vérifié", "count": null, "checked_at": null},
                    "verified_at": null, "age_jours": null},
  "badges": [], "apercu_fiche": null,
  "publication": {"peut_publier": false, "published_at": null, "conditions": [
    {"key": "siret", "label": "SIRET à 14 chiffres renseigné dans le profil entreprise", "ok": true},
    {"key": "verification", "label": "Entreprise vérifiée active dans SIRENE il y a moins de 30 jours", "ok": false},
    {"key": "metiers", "label": "Au moins un métier", "ok": false},
    {"key": "zones", "label": "Au moins un département d'intervention", "ok": false},
    {"key": "unique", "label": "Aucun autre profil publié pour la même entreprise (SIREN)", "ok": true}]},
  "apparitions_ce_mois": 0,
  "apparitions_label": "Votre profil est apparu dans 0 recherche ce mois-ci. Vous ne savez pas qui a cherché, et personne ne sait qui vous a vu.",
  "groupements_deposes": 0,
  "peut_modifier": true,
  "options": {"metiers": [{"key": "electricite", "label": "Électricité"}, "…19 métiers"],
              "roles": [{"value": "cotraitant", "label": "Partenaire du groupement (co-traitant)"},
                        {"value": "sous_traitant", "label": "Sous-traitant"}, {"value": "mandataire", "label": "Chef de file"}],
              "disponibilites": [{"value": "disponible", "label": "Disponible pour de nouveaux marchés"},
                                 {"value": "limitee", "label": "Disponibilité limitée"},
                                 {"value": "complet", "label": "Plan de charge complet"}],
              "presentation_max": 300, "references_max": 5},
  "references_disponibles": [],
  "prefill_sources": ["profil entreprise"],
  "suggestion": {"code": "publier_profil_reseau", "titre": "Faites-vous trouver pour des groupements",
                 "message": "Publiez votre profil partenaire : les entreprises qui cherchent un partenaire pour un marché pourront vous trouver et vous inviter. Gratuit, vous choisissez ce qui est visible et pouvez le retirer à tout moment.",
                 "cible": "reseau.profil"}
}
```

- `identite` vient du profil entreprise puis du registre : **non modifiable ici**. Après la
  vérification, `name` devient le **nom officiel SIRENE** (`nom_officiel: true`). Pour changer de
  SIRET : profil entreprise (le profil réseau perd alors ses vérifications et sa publication).
- `references_disponibles` = références du profil entreprise, pour cocher celles à rendre publiques.
- `apercu_fiche` = **exactement** ce que verront les autres (même forme que l'annuaire, § 4).
- `suggestion` : `null` si l'organisation a déjà publié, ou pour le compte démo.

Avec profil : mêmes champs, `exists: true`, `profile_id` (identifiant opaque, 32 caractères hexa),
`badges`, `apercu_fiche`, `verifications` datées (cf. 3.4).

### 3.2 `PUT /api/reseau/profil` — enregistrer (crée le profil au premier appel)

Mise à jour partielle : n'envoyer que les champs modifiés. Le premier PUT crée le profil **non
publié** (`visible: false`) à partir des valeurs proposées.

```json
{"metiers": ["electricite"], "departements": ["29", "56"], "roles_acceptes": ["cotraitant", "sous_traitant"],
 "disponibilite": "disponible", "dispo_jusqua": null, "lot_max_eur": 250000, "codes_cpv": ["45310000"],
 "presentation": "Électricité générale et courants faibles, bâtiments publics.",
 "references_publiques": [{"intitule": "Groupe scolaire Jean-Moulin — lot électricité", "client": "Ville de Brest", "annee": 2025}],
 "hidden_from_sirens": ["732829320"]}
```

Réponse : même forme que le GET (+ `message` éventuel). Erreurs 422 (`detail` texte) :
« Métier inconnu : … » · « Un code CPV comporte 8 chiffres (ex. 45310000). » · « Département
invalide : indiquez un numéro (ex. 29, 2A, 974). » · « Au plus 30 départements. » · « Rôle inconnu :
cotraitant, sous_traitant ou mandataire. » · « Disponibilité inconnue : disponible, limitee ou
complet. » · « Taille de lot maximale invalide (montant HT positif). » · « Présentation en une
phrase : 300 caractères au plus. » · « Chaque référence publique doit avoir un intitulé. » ·
« Année de référence invalide. » · « Au plus 5 références publiques. » · « SIREN invalide dans la
liste de masquage (9 chiffres, ou SIRET à 14 chiffres). » · « Au plus 100 entreprises masquées. »
409 « Le profil a été modifié en même temps ailleurs : rechargez la page. »

- `hidden_from_sirens` : SIREN (ou SIRET, ramené au SIREN) des entreprises à qui **masquer** le
  profil. **Dans les deux sens** : elles ne vous voient pas, vous ne les voyez pas. UI : « Masquer mon
  profil à ces entreprises » + bulle (i) « Utile pour un concurrent : il ne vous verra pas dans le
  réseau, et vous ne le verrez pas non plus. »
- `references_publiques` : seulement ce que l'entreprise **choisit** de montrer (pas de montant).
- Si un profil publié perd son dernier métier ou département : publication retirée, `message`
  « Un profil publié doit garder au moins un métier et un département : publication retirée. »

### 3.3 `DELETE /api/reseau/profil` — effacer le profil

`{"ok": true, "message": "Profil partenaire effacé."}` — la fiche disparaît et l'adresse du compte
est retirée des invitations réseau déjà reçues (RGPD). 404 « Aucun profil partenaire à effacer. »
Confirmation UI : « Effacer votre profil partenaire ? Il disparaît du réseau. »

### 3.4 `POST /api/reseau/profil/verifier` — vérifier dans les registres publics

Sans corps. SIRENE, BODACC et DECP en parallèle (5 s chacun, 8 s au total). Réponse : vue du profil
+ `verification` (résultat de CET appel) :

```json
{
  "identite": {"name": "LE GALL ELECTRICITE", "siren": "552100554", "siret": "55210055400012", "city": "Quimper",
               "postal_code": "29000", "departement": "29", "nom_officiel": true},
  "verifications": {
    "sirene": {"label": "Entreprise active (SIRENE au 08/10)", "etat": "actif", "checked_at": "2026-10-08T10:24:48"},
    "bodacc": {"label": "Aucun avis de procédure collective trouvé au 08/10 (recherche BODACC)", "found": false, "checked_at": "2026-10-08T10:24:48"},
    "decp": {"label": "Au moins 7 marchés publics publiés dans DECP (au 08/10)", "count": 7, "checked_at": "2026-10-08T10:24:48"},
    "verified_at": "2026-10-08T10:24:48.499617", "age_jours": 0},
  "badges": [
    {"key": "sirene", "label": "Entreprise active (SIRENE au 08/10)", "source": "SIRENE (recherche-entreprises.api.gouv.fr)", "date": "2026-10-08", "niveau": "ok"},
    {"key": "rge", "label": "Inscrite au registre RGE (ADEME) au 08/10 — domaine à vérifier", "source": "registre RGE (ADEME), via SIRENE", "date": "2026-10-08", "niveau": "info"},
    {"key": "bodacc", "label": "Aucun avis de procédure collective trouvé au 08/10 (recherche BODACC)", "source": "BODACC (annonces commerciales officielles)", "date": "2026-10-08", "niveau": "ok"},
    {"key": "decp", "label": "Au moins 7 marchés publics publiés dans DECP (au 08/10)", "source": "DECP (données essentielles de la commande publique)", "date": "2026-10-08", "niveau": "ok"}],
  "publication": {"peut_publier": true, "conditions": ["…toutes ok"]},
  "verification": {"sirene": {"statut": "ok", "label": "Entreprise active (SIRENE au 08/10)"},
                   "bodacc": {"statut": "ok", "label": "Aucun avis de procédure collective trouvé au 08/10 (recherche BODACC)"},
                   "decp": {"statut": "ok", "label": "Au moins 7 marchés publics publiés dans DECP (au 08/10)"}},
  "…": "reste de la vue profil"
}
```

- Registre injoignable : `verification.<registre> = {"statut": "erreur", "label": "… : non vérifié",
  "message": "BODACC momentanément indisponible : non vérifié."}` — ou, s'il existait une
  vérification réussie, elle est **conservée avec sa date** (« … la vérification du 01/10 est
  conservée. »). Afficher `message` dans un bandeau neutre `aria-live="polite"`.
- `statut` SIRENE `introuvable` : « SIREN introuvable dans SIRENE : vérifiez le SIRET du profil
  entreprise. » ; `siren_invalide` : « SIRET à 14 chiffres manquant dans le profil entreprise. »
- SIRENE répond « cessé » sur un profil publié → publication retirée + `message`.
- Erreurs : 404 « Créez d'abord votre profil partenaire (enregistrez-le une première fois). » ;
  422 `{"code": "siret_invalide", "message": "Renseignez un SIRET à 14 chiffres dans votre profil
  entreprise avant la vérification."}` ; 429 « Vérification déjà lancée il y a moins de 10 minutes :
  réessayez dans 10 min. »

### 3.5 `POST /api/reseau/profil/publier` — publier (opt-in explicite)

Corps : `{"accepte": true}` (case « J'accepte que la fiche ci-dessus soit visible des entreprises
qui ont publié la leur »). Réponse : vue du profil, `visible: true`, `statut: "publie"`,
`message: "Profil publié dans le réseau Adjugo."`. Erreurs (dans l'ordre des contrôles) :

| HTTP | `detail` | Écran |
|---|---|---|
| 404 | « Créez d'abord votre profil partenaire. » | — |
| 422 | `{"code": "consentement_requis", "message": "Cochez « J'accepte que la fiche ci-dessus soit visible des entreprises qui ont publié la leur » pour publier."}` | case à cocher en erreur |
| 422 | `{"code": "siret_invalide", "message": "Un SIRET à 14 chiffres est requis (profil entreprise)."}` | lien vers le profil entreprise |
| 409 | `{"code": "entreprise_inactive", "message": "SIRENE indique que l'entreprise a cessé son activité : publication impossible."}` | — |
| 409 | `{"code": "verification_requise", "message": "Vérifiez votre entreprise (vérification de moins de 30 jours) avant de publier."}` | bouton « Vérifier mon entreprise » |
| 422 | `{"code": "profil_incomplet", "message": "Profil incomplet.", "missing": ["Au moins un métier"]}` | liste `missing` |
| 409 | `{"code": "siren_deja_publie", "message": "Un profil est déjà publié pour cette entreprise (même SIREN). Contactez-nous si ce n'est pas vous."}` | — |

### 3.6 `DELETE /api/reseau/profil/publier` — retirer la publication

Réponse : vue du profil, `visible: false`, `statut: "retire"`, `message: "Publication retirée :
votre fiche n'apparaît plus dans le réseau."` (les invitations en cours restent).

## 4. Annuaire du réseau

**Réciprocité** : sans profil publié, l'annuaire renvoie seulement un compteur et un message. Les
profils démo, le vôtre, ceux de votre entreprise (même SIREN) et les paires masquées n'apparaissent
jamais. Limites : 60/h par IP + 300/jour par organisation (429 « Limite quotidienne de recherches
dans l'annuaire atteinte : réessayez demain. »).

### 4.1 `GET /api/reseau/annuaire?metier=&departement=&role=&cpv=&q=&page=1&par_page=20`

Filtres : `metier` (clé de `options.metiers`), `departement` (filtre strict : zones déclarées ou
siège), `role` (`cotraitant|sous_traitant|mandataire`), `cpv` (codes à 8 chiffres séparés par des
virgules), `q` (nom), `par_page` ≤ 50. Avec `metier` ou `cpv` : profils **classés** (`rang`,
`criteres`) ; sinon ordre alphabétique sans critères. Erreurs 422 « Métier inconnu. »,
« Département invalide. », « Rôle inconnu. »

Non publié :

```json
{"filtres": {"metier": "electricite", "departement": "29", "role": "", "cpv": [], "q": ""},
 "explication": "Classement par métier du lot, zone d'intervention, fiabilité vérifiée dans les registres publics (SIRENE, BODACC), expérience des marchés publics (DECP, dépôts sur Adjugo), puis capacité et disponibilité. Ce n'est pas une note : le seul pourcentage affiché reste le score de groupement, calculé quand vous simulez le groupement.",
 "visible": false, "total": 1, "message": "Publiez votre profil pour voir le partenaire correspondant.",
 "profils": [], "page": 1, "par_page": 20}
```

(`message` : « Publiez votre profil pour voir les N partenaires correspondants. » ; à 0 : « Aucun
partenaire du réseau Adjugo ne correspond encore à cette recherche. ») → afficher le message et un
bouton « Publier mon profil » (vers 3.5).

Publié :

```json
{"visible": true, "total": 1, "page": 1, "par_page": 20, "filtres": {"…": "…"}, "explication": "…",
 "profils": [{
   "profile_id": "4d93b011750d4287997380e522653dc9",
   "name": "LE GALL ELECTRICITE", "siren": "552100554",
   "lien_annuaire": "https://annuaire-entreprises.data.gouv.fr/entreprise/552100554",
   "city": "Quimper", "departement": "29",
   "metiers": [{"key": "electricite", "label": "Électricité"}], "departements": ["29", "56"],
   "roles_acceptes": [{"value": "cotraitant", "label": "Partenaire du groupement (co-traitant)"},
                      {"value": "sous_traitant", "label": "Sous-traitant"}],
   "disponibilite": {"value": "disponible", "label": "Disponible pour de nouveaux marchés", "jusqua": null},
   "lot_max_eur": 250000.0,
   "presentation": "Électricité générale et courants faibles, bâtiments publics.",
   "codes_cpv": [], "declare_le": "2026-10-08",
   "badges": ["…cf. 3.4"],
   "capacites": [
     {"key": "metiers", "label": "Métiers", "valeur": "Électricité", "source": "déclaré par l'entreprise", "date": "2026-10-08"},
     {"key": "zones", "label": "Zones d'intervention (départements)", "valeur": "29, 56", "source": "déclaré par l'entreprise", "date": "2026-10-08"},
     {"key": "lot_max", "label": "Taille de lot maximale acceptée", "valeur": "250 000 € HT", "source": "déclaré par l'entreprise", "date": "2026-10-08"},
     {"key": "categorie", "label": "Catégorie d'entreprise", "valeur": "PME", "source": "SIRENE (recherche-entreprises.api.gouv.fr)", "date": "2026-10-08"},
     {"key": "rge", "label": "Registre RGE (ADEME)", "valeur": "inscrite — domaine à vérifier", "source": "registre RGE (ADEME), via SIRENE", "date": "2026-10-08"},
     {"key": "marches_publics", "label": "Marchés publics publiés (DECP)", "valeur": "au moins 7", "source": "DECP (données essentielles de la commande publique)", "date": "2026-10-08"},
     "…"],
   "references": [{"intitule": "Groupe scolaire Jean-Moulin — lot électricité", "client": "Ville de Brest",
                   "annee": 2025, "source": "choisie et rendue publique par l'entreprise"}],
   "rang": 1,
   "criteres": [
     {"key": "metier", "label": "Métier du lot", "statut": "ok", "detail": "Métier « Électricité » déclaré par l'entreprise le 08/10", "source": "déclaré par l'entreprise", "date": "2026-10-08"},
     {"key": "zone", "label": "Zone d'intervention", "statut": "ok", "detail": "Intervient dans le 29 (déclaré par l'entreprise le 08/10)", "source": "déclaré par l'entreprise", "date": "2026-10-08"},
     "…fiabilite, experience, capacite"],
   "deja_partenaire": false}]}
```

- `references` est **absent** quand l'entreprise n'en a choisi aucune : ne rien afficher (pas de
  « 0 référence »).
- `deja_partenaire` : déjà dans « Mes partenaires » (même SIREN) → pastille « Déjà dans vos
  partenaires ».

### 4.2 `GET /api/reseau/annuaire/{profile_id}` — fiche d'un partenaire

Même objet qu'un élément de la liste (sans `rang`/`criteres`) + `historique_avec_vous` :

```json
{"profile_id": "4d93…", "name": "LE GALL ELECTRICITE", "…": "…",
 "deja_partenaire": false,
 "historique_avec_vous": {"invitations_actives": 0, "parts_soumises": 0, "marches_deposes": 0, "gagnes": 0, "perdus": 0}}
```

403 `{"code": "profil_non_publie", "message": "Publiez votre profil partenaire pour voir les fiches et
inviter les entreprises du réseau."}` ; 404 « Partenaire introuvable dans le réseau. » (non publié,
masqué, démo, retiré ou identifiant invalide — volontairement indistinguables). Limite 120/h.

## 5. « Qui me complète ? » sur un marché

### 5.1 `GET /api/projects/{id}/partner-matches[?lot=<num>]`

Lots du dossier du marché (allotissement → métier par mots-clés, déterministe) que votre entreprise
ne couvre pas ; marché non alloti → métiers des manques. Pour chaque lot : profils du réseau classés
(5 au plus, si vous avez publié), puis **repli SIRENE** si moins de 3 profils (≤ 3 lots SIRENE par
appel, cache 10 min). `?lot=5` : ce lot seul (lance sa recherche SIRENE). Montant d'un lot : inconnu
(jamais réparti au hasard). Limites : 60/h + 200/jour par organisation. 404 « Projet introuvable »
hors de votre organisation ; 404 « Lot introuvable parmi les lots à compléter. »

```json
{
  "project_id": 7, "reseau_visible": true, "message": null, "n_correspondants": 1,
  "lots": [
    {"num": "2", "label": "Électricité", "metier": "electricite", "metier_label": "Électricité", "departement": "29",
     "n_correspondants": 1,
     "reseau": [{"profile_id": "4d93b011750d4287997380e522653dc9", "name": "LE GALL ELECTRICITE", "…": "fiche § 4.1",
                 "rang": 1, "criteres": ["…5 critères"],
                 "deja_invite": false, "deja_partenaire": false,
                 "simulation": {"kind": "reseau", "profile_id": "4d93b011750d4287997380e522653dc9"}}],
     "sirene": [], "sirene_cherche": true},
    {"num": "3", "label": "Plomberie", "metier": "plomberie", "metier_label": "Plomberie / CVC", "departement": "29",
     "n_correspondants": 0, "reseau": [],
     "sirene": [{"name": "PLOMBERIE DU FINISTERE", "siret": "55544433300011", "siren": "555444333", "city": "BREST",
                 "departement": "29", "activite": "Plomberie / CVC",
                 "badges": [{"key": "sirene", "label": "Entreprise active (SIRENE au 08/10)", "source": "SIRENE (recherche-entreprises.api.gouv.fr)", "date": "2026-10-08", "niveau": "ok"}],
                 "statut_reseau": "Hors réseau Adjugo — à inviter par lien",
                 "deja_invite": false, "deja_partenaire": false,
                 "simulation": {"kind": "sirene", "siret": "55544433300011"}}],
     "sirene_cherche": true},
    {"num": "5", "label": "Menuiserie", "…": "…", "sirene_cherche": false,
     "sirene_message": "Recherche dans le registre SIRENE limitée à 3 lots par requête : affichez ce lot seul pour la lancer."}],
  "lots_couverts": [{"num": "1", "label": "Couverture", "metier": "couverture", "metier_label": "Couverture / Toiture"}],
  "lots_non_reconnus": [],
  "explication": "Classement par métier du lot, zone d'intervention, … calculé quand vous simulez le groupement.",
  "warnings": []
}
```

Sans profil publié : `reseau_visible: false`, `reseau: []` partout, `message` global (« Publiez votre
profil pour voir le partenaire correspondant. » / « … les N partenaires correspondants. » / à 0 :
« Aucun partenaire du réseau Adjugo ne correspond encore à ces lots. ») et `message` par lot (« … à ce
lot. »). Le repli SIRENE reste disponible. Une entreprise publiée sur le réseau n'est jamais listée
comme « Hors réseau ».

Boutons par carte : « Simuler le groupement » → 5.2 avec `simulation` ; « Inviter » → 6.1 (réseau)
ou 6.2 (SIRENE). Désactiver « Inviter » si `deja_invite` (libellé « Déjà invité »).

### 5.2 Simulation avec un profil du réseau (route existante, nouveau `kind`)

`POST /api/projects/{id}/groupement/simulate` accepte
`{"members": [{"kind": "reseau", "profile_id": "4d93…"}], "save": true}`. Le serveur relit le profil
**publié et visible pour vous** : toute capacité envoyée dans le corps est ignorée ; CA et effectif
restent inconnus (jamais affichés sur le réseau). Membre renvoyé :

```json
{"kind": "reseau", "profile_id": "4d93b011750d4287997380e522653dc9", "name": "LE GALL ELECTRICITE",
 "siret": "55210055400012", "ca_n1": null, "effectif": null, "qualifications": ["RGE (registre ADEME)"],
 "specialites": "Électricité", "departements": ["29", "56"],
 "references": [{"name": "Groupe scolaire Jean-Moulin — lot électricité", "client": "Ville de Brest", "year": 2025}],
 "source": "reseau", "as_of": "2026-10-08", "verified": false}
```

`warnings` contient « CA de LE GALL ELECTRICITE non affiché sur le réseau Adjugo — à demander au
partenaire ». Étiquette de provenance (`proof_label`) : « déclaré par l'entreprise sur son profil
Adjugo le 08/10 ». Erreurs : 403 `{"code": "profil_non_publie", …}` ; 404 « Partenaire introuvable
dans le réseau. ». « Retenir » (`/retenir`, inchangé) rattache le partenaire à « Mes partenaires »
(capacités étiquetées `reseau`, sans email) s'il est toujours visible, sinon avertissement
« X n'est plus visible dans le réseau Adjugo — non rattaché. »

### 5.3 `GET /api/projects/{id}/groupement/besoins` (existante)

`candidats` gagne une clé `reseau` (liste vide si vous n'avez pas publié) : candidats du réseau pour
les métiers des manques, **dans l'ordre du classement** (champ `rang`), chacun avec `profile_id`,
`score_avec` (le pourcentage de groupement « avec lui », seul % autorisé), `proof_label`,
`capacites` (`ca_n1`/`effectif` à `null`).

## 6. Mise en relation en 1 clic

Mêmes règles anti-spam que les invitations existantes : jamais depuis la démo (403), plafond
quotidien de l'organisation (30 / 24 h, renvois compris → 429 « Vous avez atteint la limite de 30
invitations par jour. Réessayez demain. »), 30/h par IP.

### 6.1 `POST /api/projects/{id}/reseau/invitations` — inviter un profil du réseau

```json
{"profile_id": "4d93b011750d4287997380e522653dc9", "role": "cotraitant", "lot": "Lot 2 — Électricité",
 "can_view_docs": true, "expires_days": 30}
```

Réponse :

```json
{"invitation": {"id": 2, "token": null, "path": null, "recipient": "", "recipient_masque": true,
                "company_name": "LE GALL ELECTRICITE", "role": "cotraitant", "can_view_docs": true, "can_contribute": true,
                "revoked": false, "declined_at": null, "source": "reseau_adjugo", "state": "sent",
                "expires_at": "2026-11-07T10:24:48.694791", "view_count": 0, "last_viewed_at": null,
                "created_at": "2026-10-08T10:24:48.695726", "emailed_at": "2026-10-08T10:24:48.699046",
                "contribution_status": null, "has_price": false},
 "emailed": true,
 "annuaire": {"cotraitant_id": 4, "link_id": 4},
 "message": "Invitation envoyée par Adjugo. L'adresse du partenaire vous sera visible quand il aura accepté ; il retrouve aussi l'invitation dans son espace Adjugo."}
```

Si l'email n'a pas pu partir : `emailed: false`, `message` « Invitation créée : le partenaire la
retrouve dans son espace Adjugo (Réseau > Invitations reçues). L'email n'a pas pu partir pour le
moment. » Le partenaire est rattaché à « Mes partenaires » (source « Réseau Adjugo », lot proposé).

| HTTP | `detail` |
|---|---|
| 403 | « La démo est en lecture guidée : créez votre compte gratuit pour inviter un partenaire. » |
| 403 | « Confirmez d'abord votre adresse email (lien reçu à l'inscription) pour inviter un partenaire du réseau. » (expéditeur non confirmé : pas de repli « copiez le lien », le lien réseau n'est jamais remis au chef de file) |
| 404 | « Projet introuvable » · « Partenaire introuvable dans le réseau. » |
| 403 | `{"code": "profil_non_publie", "message": "Publiez votre profil partenaire pour voir les fiches et inviter les entreprises du réseau."}` |
| 422 | « Rôle invalide : cotraitant ou sous_traitant. » · « Ce partenaire n'accepte pas le rôle « Partenaire du groupement (co-traitant) ». » |
| 409 | `{"code": "deja_invite", "message": "Ce partenaire a déjà une invitation active sur ce marché."}` |
| 409 | `{"code": "injoignable", "message": "Ce partenaire ne peut pas être contacté pour le moment."}` |
| 429 | plafond de l'organisation · « Ce partenaire a reçu beaucoup d'invitations aujourd'hui : réessayez demain. » (10 sollicitations / 24 h par profil : invitations créées et relances, même compteur à l'envoi et à la relance) |

Email envoyé au partenaire (par Adjugo) : objet « Une entreprise vous propose un groupement — … »,
nom du chef de file, marché, part proposée, lien, « Votre adresse n'est pas communiquée au chef de
file tant que vous n'avez pas accepté », et comment retirer sa publication.

### 6.2 `POST /api/projects/{id}/reseau/invitations-sirene` — entreprise hors réseau

`{"siret": "44306184100015", "role": "cotraitant", "lot": "Lot 4 — Peinture"}` — identité relue dans
SIRENE côté serveur (le nom saisi n'est jamais utilisé). Aucun email : **lien à transmettre**.

```json
{"invitation": {"id": 3, "token": "JnobnTyR47…", "path": "/invite/JnobnTyR47…", "recipient": "", "recipient_masque": false,
                "company_name": "PEINTURES DE L'ODET", "source": "sirene", "state": "sent", "emailed_at": null,
                "url": "https://adjugo.pro/invite/JnobnTyR47…", "…": "…"},
 "emailed": false, "annuaire": {"cotraitant_id": 5, "link_id": 5},
 "url": "https://adjugo.pro/invite/JnobnTyR47…",
 "message": "Lien créé : transmettez-le à l'entreprise (Adjugo ne connaît pas son adresse et n'envoie rien)."}
```

Erreurs : 422 « Un SIRET à 14 chiffres est requis. » · « C'est votre propre entreprise. » · « Cette
entreprise n'est pas active selon SIRENE : invitation impossible. » ; 404 « Entreprise introuvable
dans SIRENE pour ce SIRET. » ; 503 « Le registre SIRENE est momentanément indisponible : réessayez
dans un instant. » ; 409 `{"code": "deja_invite", …}` ; 409 (si vous avez publié et que l'entreprise
est sur le réseau) `{"code": "sur_le_reseau", "profile_id": "4d93…", "message": "Cette entreprise est
sur le réseau Adjugo : invitez-la depuis sa fiche (Adjugo lui transmet l'invitation)."}` → proposer
le bouton « Inviter via le réseau » (6.1 avec ce `profile_id`).

### 6.3 Côté partenaire invité par le réseau

**`GET /api/reseau/invitations`** (compte du partenaire, tous les membres de son organisation) :

```json
{"invitations": [{"token": "VCapVLf9…", "path": "/invite/VCapVLf9…", "project": "Rénovation de l'école Jules-Ferry",
                  "mandataire": "Breizh Couverture", "role": "cotraitant", "lot_propose": "Lot 2 — Électricité",
                  "deadline": "2026-11-07", "recue_le": "2026-10-08T10:24:48.695726",
                  "statut": "a_repondre", "statut_label": "À accepter ou décliner"}]}
```

(`statut: "acceptee"` après acceptation ; sans profil : `{"invitations": [], "suggestion": {…}}`.)
Boutons : « Accepter depuis mon compte » → `POST /api/invite/{token}/claim` (existante ; seul le
compte destinataire, adresse confirmée, peut accepter) ; « Décliner » → `POST /api/invite/{token}/decline`
(existante) ; « Voir l'invitation » → `/invite/{token}`.

**Aperçu minimal avant acceptation** — `GET /api/invite/{token}` (existante) pour une invitation
réseau ni acceptée, ni vérifiée par code, ni soumise :

```json
{"project": {"name": "Rénovation de l'école Jules-Ferry", "client": null, "deadline": "2026-11-07", "source_url": null,
             "analysis": {"objet": "Rénovation de l'école Jules-Ferry", "lieu": "Quimper (29)",
                          "allotissement": "Lot 1 : Couverture ; Lot 2 : Électricité ; …"}},
 "mandataire": "Breizh Couverture",
 "invited": {"recipient": "contact@legall-elec.fr", "company": "LE GALL ELECTRICITE", "role": "cotraitant"},
 "can_view_docs": false, "can_contribute": true, "documents": [], "shared_at": "2026-10-08T10:24:48.695726",
 "for_member": null,
 "apercu_minimal": true,
 "apercu_message": "Aperçu limité : acceptez l'invitation depuis votre compte Adjugo pour voir le dossier complet (acheteur, pièces du marché)."}
```

Tant que `apercu_minimal` : ni acheteur, ni lien de l'avis, ni pièces (`/doc/{id}` → 403 « Acceptez
d'abord l'invitation depuis votre compte Adjugo pour télécharger les pièces du marché. »), ni
composition du groupement (`for_member: null`, `/coffre-croise` → 403), journal limité à ses propres
entrées. Afficher `apercu_message` dans une bulle (i) + bouton « Accepter depuis mon compte ».
Après acceptation : vue complète habituelle (`apercu_minimal: false`).

**Claim** (`POST /api/invite/{token}/claim`) : réponse existante + `suggest_profile` (`null` si
l'organisation a déjà publié, sinon l'objet `suggestion` de 3.1).

## 7. `GET /api/reseau/historique[?profile_id=…]` — historique réel

COUNT réels, **dans les deux sens** (marché compté « déposé » s'il porte au moins une part soumise
d'un membre actif et que son statut est envoyé, gagné ou perdu). Jamais de nom de marché, d'adresse
ni d'identifiant. `?profile_id=` (profil publié requis, sinon 403 ; 404 si invisible) ajoute `avec`.

```json
{"comme_chef_de_file": {"invitations_actives": 2, "parts_recues": 1, "marches_deposes": 1, "gagnes": 0, "perdus": 0},
 "comme_partenaire": {"invitations_actives": 0, "parts_soumises": 0, "marches_deposes": 0, "gagnes": 0, "perdus": 0},
 "groupements_deposes": 1,
 "source": "Comptes réels sur Adjugo : invitations actives, parts soumises et statut du marché (envoyé, gagné, perdu) renseigné par le chef de file.",
 "avertissement": "Compteur en construction : un marché n'est compté comme déposé que si le chef de file a mis à jour son statut dans Adjugo.",
 "avec": {"partenaire": "LE GALL ELECTRICITE", "invitations_actives": 1, "parts_soumises": 1, "marches_deposes": 1, "gagnes": 0, "perdus": 0}}
```

`groupements_deposes` est recalculé (jamais saisi) ; > 0, il donne sur la fiche le badge « 1
groupement déposé via Adjugo ». Afficher `source` et `avertissement` dans la bulle (i). Limite 60/h.

## 8. Inscription : suggestion d'interface

`POST /api/auth/register` renvoie `{"access_token": "…", "token_type": "bearer", "suggest_profile":
{"code": "publier_profil_reseau", "titre": "Faites-vous trouver pour des groupements", "message":
"…", "cible": "reseau.profil"}}`. Afficher une carte discrète (fermable) menant à « Mon profil
partenaire ». **Aucun email n'est envoyé pour ça.** `/api/auth/login` est inchangé.

## 9. Exploitation : cron hebdomadaire

`POST /api/admin/run-partner-network` avec l'en-tête `X-Cron-Secret` (comme les autres crons ; 403
sinon ; 12/h). Re-vérifie les 25 profils publiés vérifiés le plus anciennement (timeouts 5 s, budget
90 s). Dépublie **uniquement** sur une réponse positive « cessé » de SIRENE pour le SIREN exact —
jamais sur une erreur réseau, un SIREN introuvable ou un avis BODACC (affiché, pas bloquant).
Réponse : `{"checked": 2, "sirene_ok": 2, "errors": 0, "unpublished": 0, "skipped_budget": 0}`.
À ajouter dans Railway (cron hebdomadaire), comme `run-cotraitance-reminders`.

## 10. RGPD

- **Export** (`GET /api/rgpd/export`) : clé `profil_partenaire_reseau` (tout le profil, y compris la
  liste de masquage et le compteur anonyme ; jamais qui a cherché : ce n'est pas stocké).
- **Effacement du compte** et `DELETE /api/reseau/profil` : profil effacé ; dans les invitations
  réseau reçues (tenant des chefs de file) : `recipient = ''`, `verified_email = ''`, lien vers le
  profil retiré.
- **Transfert de propriété** de l'organisation : le profil suit le nouveau propriétaire.
- Journal `network.*` (recherches, consultations de fiche, invitations) : écrit **uniquement** sur
  le tenant de l'entreprise qui cherche.

## 11. Parcours, écran par écran

**Navigation « Réseau »** (3 onglets) : Mon profil partenaire · Annuaire · Mon historique (+ pastille
« Invitations reçues » si `GET /api/reseau/invitations` n'est pas vide).

1. **Mon profil partenaire** — `GET /api/reseau/profil`.
   - Bandeau de statut (`statut_label`) ; si `suggestion` : carte « Faites-vous trouver… ».
   - Bloc « Identité » (lecture seule, `identite`) + badge « nom officiel SIRENE » si `nom_officiel`.
   - Formulaire (si `peut_modifier`, sinon lecture seule + phrase « Seul un administrateur… ») :
     métiers (cases, `options.metiers`), départements d'intervention (saisie de numéros), rôles
     acceptés, disponibilité (+ date), taille de lot maximale (€ HT), « Présentation en une phrase »
     (compteur /300), références à rendre publiques (cases sur `references_disponibles`, 5 max),
     « Masquer mon profil à ces entreprises » (SIREN). Bouton « Enregistrer » → PUT.
   - Bloc « Vérification » : 3 lignes `verifications.*.label` + date ; bouton « Vérifier mon
     entreprise » → POST verifier (désactivé pendant l'appel, `aria-busy`) ; `verification.*.message`
     en bandeau `aria-live`.
   - Bloc « Ce que les autres verront » : rendu de `apercu_fiche` (même composant que l'annuaire).
   - Bloc « Publication » : liste `publication.conditions` (icône `check`/`x`), case de consentement,
     bouton « Publier mon profil » (actif si `peut_publier`) ; si publié : « Retirer la publication » ;
     lien discret « Effacer mon profil ».
   - Phrase `apparitions_label` dans une bulle (i).
2. **Annuaire** — filtres (métier, département, rôle, nom) → `GET /api/reseau/annuaire`. Si
   `visible: false` : `message` + bouton « Publier mon profil ». Sinon cartes : nom, ville, métiers,
   zones, disponibilité, badges ; rang + critères repliables si la liste est classée ; bouton « Voir la
   fiche ».
3. **Fiche partenaire** — `GET /api/reseau/annuaire/{id}` : présentation, capacités (valeur + source
   + date), badges, références choisies (si présentes), « Historique avec vous » (compteurs), lien
   « Vérifier sur l'annuaire des entreprises » (`lien_annuaire`).
4. **Fiche du marché → panneau « Qui me complète ? »** — `GET …/partner-matches` : un bloc par lot
   (`label`, `metier_label`), cartes réseau (rang + critères + badges + « Simuler » + « Inviter »),
   puis « Entreprises du registre SIRENE » (`statut_reseau`, « Simuler », « Inviter par lien ») ;
   `sirene_message` → bouton « Chercher pour ce lot » (`?lot=`). Lots couverts en gris. `message` global
   si `reseau_visible: false`.
5. **Modale d'invitation** — rôle (cotraitant / sous-traitant selon `roles_acceptes`), part proposée
   (`lot`), accès aux pièces ; texte : « Adjugo envoie l'invitation : vous verrez l'adresse du
   partenaire quand il aura accepté. » → 6.1. Pour SIRENE : « Adjugo ne connaît pas son adresse :
   copiez le lien et envoyez-le-lui. » → 6.2 puis bouton « Copier le lien » (`url`).
6. **Liste des partenaires invités** (cockpit existant) : `source` → « Réseau Adjugo » / « Registre
   SIRENE » / rien ; `recipient_masque` → « Adresse visible quand le partenaire aura accepté » ; pas
   de « Copier le lien » pour `reseau_adjugo` ; statut « a décliné » existant.
7. **Invitations reçues** (partenaire) — `GET /api/reseau/invitations` : marché, chef de file, part
   proposée, échéance ; « Accepter depuis mon compte » / « Décliner ».
8. **Mon historique** — `GET /api/reseau/historique` : deux colonnes « Comme chef de file » / « Comme
   partenaire » (compteurs), `groupements_deposes`, `source` + `avertissement` en bulle (i).

## 12. Ce que chaque écran affiche / n'affiche JAMAIS

| Écran | Affiche | N'affiche jamais |
|---|---|---|
| Mon profil | tout son profil, sa liste de masquage, l'aperçu exact de sa fiche, le compteur anonyme d'apparitions | qui l'a cherché ou consulté (non stocké) |
| Annuaire / fiche | nom officiel, SIREN, ville, métiers, zones, rôles, disponibilité, taille de lot, présentation, badges et capacités datés et sourcés, références **choisies** | email, téléphone, CA, effectif exact, documents, résultats de marchés, liste de masquage, compteur d'apparitions, profils démo, profils masqués, une note ou un « % » |
| « Qui me complète ? » | rang, critères (statut + phrase + source + date), badges, entreprises SIRENE « Hors réseau » | un score, un total, un « % » (le seul % est celui de la simulation) |
| Simulation | le score de groupement (seul %), CA / effectif « non affiché sur le réseau — à demander » | des capacités envoyées par le navigateur pour un profil réseau |
| Invitations (chef de file) | statut, source, nom d'entreprise, adresse **après** acceptation | l'adresse d'un partenaire réseau avant sa réponse, le lien d'une invitation réseau |
| Invitation reçue (aperçu minimal) | objet, lots, lieu, échéance, chef de file, part proposée | acheteur, lien de l'avis, pièces, composition du groupement, score commun |
| Historique | compteurs réels dans les deux sens, avertissement « compteur en construction » | noms de marchés, adresses, identifiants |
| Journal (chef de file) | invitations réseau envoyées (nom d'entreprise) | adresse (même masquée) du partenaire réseau dans les entrées de code de vérification |

Rappels : 0 LLM dans toute la vague ; aucun profil de démonstration n'existe ni n'est créé ; le
compte démo ne publie rien, n'invite personne du réseau et ne voit aucun profil réel.

## 13. Écrans livrés (front, 08/10/2026)

Fichiers : `app/static/app.html`, `app.js`, `styles.css`, `invite.html` (aucune dépendance ajoutée).
Garde-fous automatiques : `tests/test_reseau_ecrans.py` (pas de v-html / innerHTML, pas de « % », pas
d'émoji ni de jargon, adresse jamais affichée dans la modale, mise à jour partielle du profil, syntaxe).

| Écran | Où | Méthodes (`app.js`) |
|---|---|---|
| Entrée « Réseau » + pastille « invitations à traiter » | barre latérale, sous « Mes partenaires » | `go('reseau')`, `rnGo(tab)`, `rnRecuesCount()` |
| Mon profil partenaire (identité, ce que vous proposez, vérification, aperçu exact, publication, effacement) | vue `reseau`, onglet `profil` | `rnLoadProfil`, `rnSave` (PUT partiel `_rnBody`), `rnVerify`, `rnPublish` (enregistre d'abord les modifications), `rnUnpublish`, `rnDelete` |
| Annuaire (filtres métier / département / rôle / nom, rang + « Pourquoi ce rang », fiche) | onglet `annuaire`, modale fiche | `rnLoadAnnuaire`, `rnOpenFiche`, `rnInviteFromFiche` |
| Mon historique (deux colonnes, source + avertissement en bulle) | onglet `historique` | `rnLoadHistorique`, `rnHistRows` |
| Invitations reçues (accepter depuis mon compte, voir, décliner → « Vous avez décliné ») | onglet `recues` (visible si non vide) | `rnLoadRecues`, `rnAccept`, `rnDecline` |
| Partenaires pour ce marché — « Qui me complète ? » | fiche du marché, sous « Répondre à plusieurs ? » | `aoPmLoad`, `aoPmLot` (`?lot=`), `aoPmSimulate` (ajoute à la simulation existante) |
| Modale d'invitation en 1 clic (réseau / lien SIRENE, choix du marché depuis l'annuaire) | globale | `rnInviteOpen`, `rinvSend`, `rinvViaReseau` (409 `sur_le_reseau`) |
| Liste des invitations du marché | carte « Réseau Adjugo » de la fiche | `inviteSourceLabel`, `inviteIsNetwork`, `inviteRelancable` |
| « A décliné » (cartes, composition retenue, candidats « Qui l'a ? ») | fiche du marché | `inviteDeclinedFor(nom)`, `declinedLabel` |
| Suggestion « publiez votre profil » (fermable) | haut de page, hors vue Réseau | `_rnSuggest` (inscription, claim, ou `sessionStorage` posé par `invite.html`) |
| Aperçu minimal + « Accepter depuis mon compte » | `invite.html`, carte du dossier | `claimAndOpen`, `keepSuggestion` |

Choix d'écran à valider : le panneau se lance au clic (« Qui me complète ? ») et non à l'ouverture du
marché (quota et repli SIRENE) ; « Simuler le groupement » ajoute l'entreprise à la simulation de
« Répondre à plusieurs ? » et calcule tout de suite ; le statut « a décliné » est rapproché par nom
d'entreprise (comme « déjà invité » dans la composition retenue) et autorise « Inviter à nouveau » ;
publier enregistre d'abord les modifications en cours (la fiche publiée est celle de l'aperçu) ;
l'adresse d'un partenaire réseau apparaît dans la liste seulement quand le serveur la renvoie
(après acceptation).
