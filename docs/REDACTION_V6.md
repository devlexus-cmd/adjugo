# Rédaction, vague 6 — « Apprendre de ses résultats » : contrat

Étude « rédaction » (`etudes/redaction.md`) § 8 (V6) : le carnet de notes (F, § 6.11), la page « Comment ce dossier a
été préparé » (H, § 6.12), plusieurs lots en un seul effort (J, § 6.10) ; doctrine § 7 ; décisions § 10 (9 a).

Base de production : `a29173a` (branche `feat/produit-acheteur-collectivites`, tête Alembic `z1entretienchantier`).

Ce contrat est écrit par chantier : chaque chantier a sa section, les sections ne se recouvrent pas.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« valider » (jamais « signer »), jamais « consortium », jamais « vérifié ». Zéro émoji, explications dans une bulle
(i), compact, rien collé aux bords, lisible à 375 px. Le menu n'est pas réorganisé.

---

## H — « Comment ce dossier a été préparé »

Source de vérité du code :
- page (contenu, comptes, noms, dates, avertissements) : `app/services/atelier_preparation.py` (nouveau, sans IA) ;
- rendu Word et PDF : `app/services/atelier_export.py` (`_prep_flowables`, `_prep_docx`, appelés à la fin de `to_pdf`
  et `to_docx` quand `ctx["page_preparation"]` est présent) ;
- export : `app/services/atelier.py` (`exporter(…, page_preparation=False)`, `apercu_export` → `page_preparation`) ;
- routes : `app/routers/atelier.py` (`ExportIn.page_preparation`, `GET /api/atelier/{pid}/preparation`) ;
- écran : `app/static/app.html` (bloc de l'export de l'atelier), `app/static/app.js` (`prepJoindre`, `prep`,
  `atlPrepLoad`, `atlPrepVoir`, `atlPrepLigne`), `app/static/styles.css` (`.atl-prep*`) ;
- tests : `tests/test_redaction_v6_preparation.py`.

Aucune migration : le choix n'est jamais enregistré dans les options du dossier ; l'export en garde la trace dans
`dossiers_presentation.dernier_export["page_preparation"]` (JSON existant) et au journal chaîné (`atelier.export`,
`meta.page_preparation`).

### H.1 Décision appliquée

| Décision | Retenu | Effet |
|---|---|---|
| D9 (a) | Mention « Préparé avec assistance IA » dans les propriétés du fichier si l'IA a servi, visible avant l'export, plus la page H facultative | La mention est inchangée. La page dit, partie par partie, si l'IA a aidé, avec le MÊME drapeau (`ia` de la version exportée) : la page et les propriétés du fichier disent toujours la même chose (test). |

### H.2 Ce que voit l'utilisateur

Dans le bloc de l'export de l'atelier (chef de file), sous « Page de garde · Sommaire · Rédiger sans IA » :

- une case **décochée par défaut** : « Joindre une page « Comment ce dossier a été préparé » ». Elle est choisie à
  chaque export : elle n'est jamais enregistrée (ni dans les options du dossier, ni dans le navigateur) et revient
  décochée à chaque ouverture de l'atelier. `PUT /options` l'ignore ;
- une bulle (i) : « Cette page dit, pour chaque partie, l'entreprise qui l'a rédigée, si l'IA a aidé ou non, combien
  de faits viennent de chaque type de source (jamais leur contenu) et qui l'a validée, avec la date. Elle s'ajoute à
  la fin du fichier. La joindre ou non est votre décision, surtout si le règlement interdit ou encadre l'usage de
  l'IA : lisez-le d'abord. « Rédiger sans IA » empêche toute rédaction par l'IA pour ce dossier ; une partie déjà
  préparée avec l'IA reste à réécrire vous-même si le règlement l'exige. » ;
- un lien « Voir la page » : la page telle que l'export la joindrait maintenant (lecture seule, sans IA), en lignes
  compactes (« Rédigée par X · aide de l'IA : oui · validée par X, le 19 octobre 2026 », puis les faits), avec ce que
  l'écran en dit AVANT (rien de cela n'entre dans le fichier) :
  - « 2 parties non validées : la page le dira. Validez-les d'abord si vous voulez joindre la page. » ;
  - « 1 fait sans source retrouvée : la page le dira. » ;
  - « Le règlement limite le dossier à 12 pages : cette page s'ajoute à la fin du fichier et n'entre pas dans le
    compteur. » (seulement si le règlement fixe un nombre de pages).

Sur téléphone (écran étroit), l'export se fait depuis un ordinateur (règle de la vague 2) : la case n'est pas
montrée, la page se lit (« Voir la page »).

### H.3 La page (contenu exact)

À la fin du fichier, après la dernière partie, sur une nouvelle page ; jamais dans le sommaire ni dans le compteur.

1. Titre : « Comment ce dossier a été préparé ».
2. Introduction : « Pour chaque partie du dossier, cette page indique l'entreprise qui l'a rédigée, si un outil
   d'intelligence artificielle a aidé à la rédaction, le nombre de faits relevés par type de source et qui l'a
   validée, avec la date. »
3. Résumé (liste) :
   - « Parties préparées avec l'aide de l'IA : 2 sur 4. » ou « Aucune partie n'a été préparée avec l'aide de l'IA. » ;
   - si l'IA a servi : « Le fichier porte dans ses propriétés la mention « Préparé avec assistance IA ». » ;
   - mode « sans IA » de la vague 5 actif : « L'entreprise a choisi de rédiger ce dossier sans IA à partir du
     14 octobre 2026. » ;
   - en groupement (une partie rédigée par un autre que l'organisation qui exporte) : « Parties rédigées : Breizh
     Couverture, 3 ; Breizh Désamiantage, 1 ; le groupement (convention et parts des membres), 2. » (le chef de file,
     puis chaque partenaire dans l'ordre du plan, puis les parties tirées du groupement) ;
   - « Parties validées : 3 sur 4. »
4. Tableau, une ligne par partie active, dans l'ordre du plan (numéros et intitulés de l'export) :

| Colonne | Règle |
|---|---|
| Partie | « 1.2 Équipe d'exécution » (comme le titre de la partie dans le fichier) |
| Rédigée par | Partie de l'organisation : son nom d'entreprise (profil), à défaut « Le candidat ». Partie d'un partenaire : son nom d'entreprise (sa part, sinon son invitation). Texte commun écrit par le chef de file sur la partie d'un partenaire sans texte du partenaire avant : le chef de file (sa contribution réelle). Partie du partenaire modifiée par le chef de file : « Breizh Désamiantage ; modifiée par Breizh Couverture » ; phrase de transition (« Harmoniser le ton ») : « … ; phrase de transition ajoutée par … ». « Organisation du groupement » : « Le groupement, d'après sa convention » ; « Qui fait quoi » : « Le groupement, d'après les parts des membres ». |
| Aide de l'IA | « Oui » / « Non » (drapeau `ia` de la version exportée) ; « Oui, pour une phrase de transition » quand seule la transition vient de l'IA ; « — » sans texte. |
| Faits et sources | « 10 faits reliés à une source : 3 tirés de ses documents, 2 déclarés par l'entreprise, 1 déclaré par un membre du groupement, 1 de source publique, 1 selon son estimation, 1 calculé à partir de ces faits, 1 tiré du dossier de l'acheteur ; 1 fait relu par l'entreprise, sans autre source ; 1 fait sans source retrouvée ». « Aucun fait relevé » quand on sait qu'il n'y en a aucun ; « Aucun fait relié à une source » sinon. Parties tirées du groupement : « Repris de la convention de groupement » / « Repris des parts déclarées par les membres ». « — » sans texte. |
| Validée | « Par Breizh Couverture, le 19 octobre 2026 » (date de Paris) ; « Qui fait quoi » : « Par Breizh Couverture et Breizh Désamiantage, le … » (chaque membre qui l'a validée) ; « Non validée » si le texte exporté n'est pas le texte validé. |

5. Légende : « Les faits sont les chiffres, noms, certifications, références, effectifs, matériels et délais relevés
   dans le texte de chaque partie. La page dit où chacun est écrit : un document ou une déclaration de l'entreprise
   qui a rédigé la partie, une source publique, son estimation, un calcul à partir de ces faits, ou le dossier de
   l'acheteur. Elle ne dit pas qu'un fait est exact et ne reproduit aucune source : le candidat reste responsable de
   son offre. »

Types de source (A, vague 3 → page) : `documents` et `justificatif` → « tiré de ses documents » ; `declare` et `vous`
→ « déclaré par l'entreprise » ; `partenaire` → « déclaré par un membre du groupement » ; `public` → « de source
publique » ; `estimation` → « selon son estimation » ; `calcul` → « calculé à partir de ces faits » ; `acheteur` →
« tiré du dossier de l'acheteur ». Les engagements à confirmer ne sont pas des faits (comme `faits_sources.bilan`) :
non comptés. Un fait relié à une preuve retirée ou expirée, ou à un extrait disparu, compte « sans source
retrouvée » (les faits sont lus comme l'export les lit : `atelier.faits_lus`).

### H.4 Ce qui est déterministe

Tout. Aucun appel d'IA (test : le client d'IA échoue s'il est appelé), aucun réseau. La page est calculée sur le MÊME
texte que l'export (`versions_communes` pour le lecteur qui exporte), après le contrôle du blocage : un export bloqué
reste bloqué (dérogation de la vague 2 inchangée) ; une page impossible à construire refuse l'export demandé avec elle
(503 `page_preparation_indisponible` : « La page « Comment ce dossier a été préparé » n'a pas pu être préparée pour le
moment : réessayez, ou exportez sans elle. ») — jamais un fichier sans la page que le client a demandée.

### H.5 Ce qui ne sort jamais (doctrine § 7, règles 3, 5, 7 et 9)

- Ni texte, ni source, ni extrait, ni nom de document, ni phrase ou contenu d'un fait : des NOMBRES seulement.
- Aucun nom de personne ni adresse : « qui a validé » est l'ENTREPRISE (le partenaire valide sa partie lui-même,
  l'identifiant du compte d'un partenaire n'est jamais gardé — vague 4 —, et le nom d'un salarié n'a rien à faire
  chez l'acheteur).
- Aucun nom d'outil, jamais « vérifié », aucun renvoi `[S1]`, aucun « [À compléter] ».
- Partie d'un partenaire : seulement ce que la vague 4 rend commun — son texte envoyé (ou écrit par le chef de file),
  son drapeau `ia`, ses compteurs de sources par type (`dossier_section_versions.compteurs`), sa validation et son nom
  d'entreprise. Jamais un brouillon (`dossier_parts_brouillons` n'est pas lu), jamais ce qu'il a relu lui-même (compte
  privé, non transmis : `relus` vaut `null` pour sa partie), jamais ses documents déposés.
- La page n'existe que dans l'export du chef de file (l'atelier). Aucun export d'un partenaire ne la contient : sa
  portabilité (`GET …/redaction/export`) et son export RGPD restent ceux de la vague 4 (test). `GET …/preparation` est
  une route de l'atelier : organisation du marché seulement (404 pour un autre compte, comme l'atelier).
- Le dossier commun (ZIP / formulaires) ne joint jamais la page (pas de case à cet endroit).

### H.6 API

| méthode | route | corps | réponse |
|---|---|---|---|
| GET | `/api/atelier/{pid}` | — | `export.page_preparation = {libelle, bulle, par_defaut: false}` (ajouté ; le reste inchangé) |
| GET | `/api/atelier/{pid}/preparation` | — | `{page: {titre, introduction, resume[], colonnes[], lignes[{section_id, partie, redigee_par, ia, ia_libelle, faits: {avec_source, par_type{documents, declare, partenaire, public, estimation, calcul, acheteur}, sans_source, relus} \| null, faits_libelle, validee, validee_par, validee_le (AAAA-MM-JJ), validee_libelle}], legende, parties, parties_ia, parties_validees, mention_ia}, avertissements: [{code: non_validees \| sans_source \| limite_pages, message}], case}` — 404 `marche_introuvable` / `dossier_introuvable`, 503 `page_preparation_indisponible` |
| POST | `/api/atelier/{pid}/export` | `{format, etat_hash?, page_preparation?: false}` | le fichier ; avec `page_preparation: true`, la page à la fin. 503 `page_preparation_indisponible`. Le reste inchangé (409 `export_bloque`, `etat_modifie`). |

`dernier_export.page_preparation` (booléen) et `meta.page_preparation` de l'entrée `atelier.export` du journal chaîné.

### H.7 Démo

- `GET …/preparation` est ouvert à la démo (lecture seule : ni fichier produit, ni export inscrit) : sur la vitrine
  « Réfection toiture — Groupe scolaire Jean Moulin », la page montre 5 parties préparées avec l'IA, 3 validées,
  les faits par type de source (« 7 faits reliés à une source : 5 tirés de ses documents, 2 tirés du dossier de
  l'acheteur »…) et le fait sans source de la partie à finir. Le règlement de la vitrine demande déjà de signaler
  l'usage de l'IA : la case et la bulle s'y lisent naturellement.
- La case se coche (état du navigateur seulement) ; l'export reste refusé à la démo (« lecture guidée », inchangé) :
  rien n'est écrit dans la vitrine (test : `dernier_export` inchangé).
- Aucune nouvelle route d'écriture : l'inventaire de `tests/test_demo_sans_cout.py` est inchangé.

### H.8 Choix à dire à Eliot

1. « Qui l'a validée » dit l'ENTREPRISE, jamais la personne (aucun nom de salarié chez l'acheteur ; le partenaire
   n'a pas d'identifiant de compte gardé). À changer si tu veux le nom du dirigeant.
2. La case n'est jamais enregistrée : décochée à chaque ouverture de l'atelier (plus sûr face à une clause « sans
   IA »). À changer si les testeurs veulent qu'elle reste cochée pour un dossier.
3. Les comptes par type de source sont montrés même si `ATELIER_LIBELLES_SOURCES` est éteint (comme les compteurs
   d'un partenaire au chef de file, vague 4) : la page dit où le fait est écrit, la légende dit qu'elle ne dit pas
   qu'il est exact, et le client la lit avant de la joindre. Variante prudente possible en une ligne : n'afficher
   que « N faits relevés, k sans source retrouvée » tant que la calibration n'est pas faite.
4. Les faits qu'un partenaire a relus lui-même ne sont pas comptés sur sa ligne (compte privé, la vague 4 ne le
   transmet pas) : sa ligne dit « Aucun fait relié à une source » plutôt que « Aucun fait relevé ».
5. La page n'entre pas dans le compteur de pages ni dans le sommaire ; l'écran prévient quand le règlement limite
   le nombre de pages.
6. Pas de page dans le ZIP du dossier commun.

### H.9 Vérifications

- `tests/test_redaction_v6_preparation.py` (8 tests) : case décochée par défaut (état, options inchangées, Word et
  PDF sans la page sans la case, `PUT /options` ne l'enregistre pas), page DERNIÈRE du Word et du PDF avec la case,
  dernier export et journal ; contenu exact partie par partie (tous les types de source, relu, engagement non compté,
  source perdue = sans source, partie non validée, résumé, avertissements dont la limite de pages), sans fuite (noms
  de documents, extraits, phrases et contenus des faits, libellés de source, noms des salariés, représentant légal,
  adresse, email, nom d'outil, « vérifié ») dans la page à l'écran, dans le Word et dans le PDF, Word identique à
  l'écran ; page et mention des propriétés toujours d'accord (aucune IA, une partie de l'IA) ; mode « sans IA » dit ;
  groupement (convention, « Qui fait quoi » validée par chaque membre, part du partenaire, résumé des contributions,
  brouillon privé jamais lu, partie modifiée par le chef de file, rien dans ce que lit le partenaire ni dans sa
  portabilité, 404 pour un autre compte) ; page impossible : 503, aucun fichier rangé, export sans la case possible ;
  démo (page lue, export refusé, rien d'écrit) ; écran (case, bulle, « Voir la page », sans émoji). Aucun appel d'IA.
- Suite complète verte : 1 846 tests (1 838 de la production + 8), SQLite, `TZ=UTC`, IA simulée, aucun réseau. SRI à
  jour (`scripts/sri_update.py --check`), `node --check app/static/app.js`.
- Postgres 16 (aucune migration dans H) : code de production `a29173a` et code nouveau extraits par `git archive`,
  chacun sur une base neuve montée par son propre `alembic upgrade head` (tête `z1entretienchantier` des deux côtés),
  puis atelier V2 (export, écrans), assemblage et chef de file V4, C2 V5, démo sans coût et remise à neuf : production
  289 verts, nouveau 297 verts (les mêmes + les 8 de H), aucun échec de part et d'autre (script
  `scratchpad/h6/run_h6_pg.py`).
- Navigateur : vitrine de la démo à 1 280 px et 375 px (aucun débordement horizontal, page lisible, case et bulle) ;
  dernière page du PDF rendue et relue (tableau à 5 colonnes, légende, numéro de page).
