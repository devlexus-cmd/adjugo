# Rédaction, vague 3 — E1 « Mes preuves » : les écrans (sur le socle)

Complète `docs/REDACTION_V3_PREUVES.md` (le socle : modèle, règles, routes `/api/preuves`). Ici : ce
qu'E1 ajoute, et ce que A et I peuvent réutiliser. Aucune IA dans tout E1.

Code : `app/services/preuves_reprise.py` (reprise de l'existant), `app/services/preuves_atelier.py`
(insertion dans l'atelier, aucun CV vers l'IA), `app/routers/preuves_ecrans.py` (routes, montées AVANT
le socle), écrans dans `app/static/app.html` / `app.js` / `styles.css` (blocs « Mes preuves »).
Tests : `tests/test_redaction_v3_mes_preuves.py` (serveur), `tests/test_redaction_v3_mes_preuves_ecrans.py`
(écrans). Aucune migration.

## 1. Où sont les écrans

- Menu : une entrée « Mes preuves » SOUS « Mon entreprise » (`nav-sub`) ; aucune autre entrée déplacée.
- « Mon entreprise » porte deux onglets : « Profil de l'entreprise » et « Mes preuves » (vue `preuves`).
- Cinq listes courtes : Références, Qualifications, Équipe (CV minimal), Matériel, Chiffres clés.
  Chaque fiche montre son libellé de source (`source_libelle`) avec « Voir le passage » ou « Ouvrir le
  justificatif », sa fin de validité (alerte sobre à 60 jours, et un encadré « à mettre à jour »),
  « à reconfirmer », et la raison quand Adjugo ne s'en sert pas. Ajout manuel : « déclaré par vous »
  par défaut ; les autres sources selon la nature (`types_source`).
- Propositions (I, E2) : « Accepter » sur chaque fiche, et « cochez celles qui sont justes » + « Accepter
  (n) » dès qu'il y en a plusieurs.
- Lisible à 375 px (une colonne, onglets en grille), zéro émoji, bulles (i), jamais « vérifié ».

## 2. Reprise de l'existant (sans doublon ni perte)

| méthode | route | réponse |
|---|---|---|
| GET | `/api/preuves/reprise` | `{elements: [élément], deja, a_reprendre}` — rien n'est créé |
| POST | `/api/preuves/reprise` | corps `{cles: [...]}` (500 au plus) → `{creees: [preuve], deja, ignorees: [{texte, message}]}` |

Élément : `{cle, nature, nature_libelle, valeur, texte, type_source, source_libelle, source,
date_fin_validite, provenance (entreprise | reseau | documents), provenance_libelle, deja, manque}`.

- Origines : profil de l'entreprise (`Company.team` → Équipe : `qualifications` et `references` →
  `qualifications` et `chantiers` ; `references` ; `qualifications` texte ou `{name, detail, expiration}` ;
  effectif et CA N-1 à N-3 → Chiffres clés), profil du réseau (`references_publiques`), coffre-fort
  (documents rangés en « Qualifications », hors corbeille, version courante → Qualification
  « justificatif déposé » avec sa date d'expiration).
- Le client n'envoie que les CLÉS cochées : le contenu est relu côté serveur. Créées « acceptées »
  (l'utilisateur vient de les cocher), origine `profil`. Les données d'origine ne changent jamais.
- Jamais deux fois : même fiche (empreinte), même intitulé (objet, nom, désignation, libellé — même si les
  autres champs ont été modifiés ou la fiche retirée), ou même justificatif ; deux origines qui disent la
  même chose (profil et réseau) n'en font qu'une. Verrou sur la ligne du compte (Postgres) : deux clics
  simultanés ne doublent rien.
- Un champ illisible (année hors bornes, montant qui n'est pas un nombre) est écarté, la fiche est gardée ;
  un collaborateur sans fonction n'est pas repris (`manque` le dit).

## 3. Dans l'atelier : insérer une fiche, telle quelle, sans IA

| méthode | route | réponse |
|---|---|---|
| GET | `/api/atelier/{project_id}/preuves` | `{fiches: [{id, nature, nature_libelle, titre, source_libelle, a_reconfirmer, date_fin_validite, bloc}], ecartees: [{id, nature, texte, message}]}` |
| POST | `/api/atelier/{project_id}/sections/{section_id}/inserer-preuve` | corps `{preuve_id, base_version_id}` → la partie (même forme que les autres routes de l'atelier) |

- Fiches = `pv.faits_autorises(owner, project_id=...)` (une estimation d'un autre marché est écartée).
- `bloc` (`preuves_atelier.bloc`) : Markdown de l'atelier (gras, listes), seulement les faits de la fiche —
  ni numéro « F », ni libellé de source, rien d'interne. CV : `**Nom, Fonction**` puis
  « Expérience », « Diplômes », « Qualifications et habilitations », « Chantiers ».
- L'insertion passe par `atelier.enregistrer_texte` (verrou, version de départ, longueur, faits « à
  relire » gardés) : nouvelle version « Écrit ou modifié par vous », jamais d'IA. Erreurs : 404
  `preuve_introuvable`, 409 `preuve_non_utilisable` (+ `raison` : `proposee`, `retiree`, `expiree`,
  `source_introuvable`, `justificatif_introuvable`, `autre_marche`), 409 `texte_modifie_entre_temps`.
- Écran : « Insérer une fiche » (lecture : à la fin de la partie) ; « Fiche » dans l'éditeur (au
  curseur, à enregistrer ensuite) ; aperçu du texte inséré avant de confirmer. Démo : écriture refusée.

## 4. Aucun CV vers l'IA (décision 8a)

- `preuves_atelier.refuser_cv_pour_ia(db, owner_id, texte)` : « Raccourcir » envoie le texte de la partie à
  l'IA ; si une ligne de CV d'une fiche « Équipe » de l'organisation (tous statuts) y figure, la demande est
  refusée AVANT tout appel et tout débit : 409 `cv_dans_la_partie` (appelé dans `atelier.lancer`).
  `preuves_atelier.cv_presents(db, owner_id, texte)` rend les noms concernés (repérage aux accents, à la
  casse, aux espaces et au gras près).
- « Rédiger » n'envoie ni le nom ni le CV d'une fiche « Équipe » (test de non-régression : à garder vert
  quand A remettra les faits numérotés à l'IA, avec `texte_ia`).

## 5. À savoir pour A et I

- Le profil (`Company.team`, ses qualifications et références) n'est jamais modifié. Depuis
  l'assemblage de la vague 3 (`docs/REDACTION_V3_ENSEMBLE.md`), un élément repris (fiche du même intitulé
  acceptée ou retirée) n'est plus remis à l'IA depuis le profil : sa fiche décide. Le reste du profil est
  remis en `[P#]` / `[E#]` (A).
- I crée des fiches `proposee` : l'écran les montre déjà (accepter une à une ou par lot).
- « Mon savoir-faire » : la suppression d'un document prévient quand des fiches perdent leur source
  (`preuves_sans_source`).
