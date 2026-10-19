# Rédaction, vague 6 — « Apprendre de ses résultats » : contrat

Étude « rédaction » (`etudes/redaction.md`) § 8 (V6) : le carnet de notes (F, § 6.11), la page « Comment ce dossier a
été préparé » (H, § 6.12), plusieurs lots en un seul effort (J, § 6.10) ; doctrine § 7 ; décisions § 10 (9 a).

Base de production : `a29173a` (branche `feat/produit-acheteur-collectivites`, tête Alembic `z1entretienchantier`).

Ce contrat est écrit par chantier : chaque chantier a sa section (F, H, J), les sections ne se recouvrent pas.

La doctrine (§ 7) vaut pour tous les chantiers : un fait ne vient jamais de l'IA ; on ne dit jamais « vérifié » ; tout
nombre lu par l'IA dans un document doit y être retrouvé mot pour mot et validé par l'utilisateur ; Adjugo n'envoie
jamais de courrier à la place de la PME (il pré-remplit, elle envoie) ; les données sont strictement propres à chaque
client (aucune statistique entre clients) ; `tenant_scope` et `pii_scope` sur chaque appel d'IA, remboursement si l'IA
tombe ; un seul process ; tout ce qui peut se faire sans IA se fait sans IA. Cloisonnement de la vague 4 intact.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« valider » (jamais « signer »), jamais « consortium », jamais « vérifié ». Zéro émoji, explications dans une bulle
(i), compact, rien collé aux bords, lisible à 375 px. Le menu n'est pas réorganisé.

| Section | Chantier | Migration | IA |
|---|---|---|---|
| F | Le carnet de notes : « Demandez vos notes », notes reçues, « Où vous perdez des points », « La dernière fois, l'acheteur a écrit », dossier gagné vers le savoir-faire | `a2carnetnotes` (après `z1entretienchantier`) | bouton facultatif (lecture du courrier), une question du jour, rendue si rien n'est retenu ou si l'IA tombe |

---

## F — Le carnet de notes

Source de vérité du code :
- règles et données : `app/services/carnet_notes.py` (SEUL point d'écriture de `projects.carnet_notes`) ;
- routes : `app/routers/carnet.py` (préfixe `/api/carnet`) ; passage à « Perdu » noté par `PUT /api/projects/{id}`
  (`app/routers/projects.py`, `carnet_notes.apres_changement_d_etape`) ;
- atelier : `app/services/atelier.py` (`etat()["derniere_fois"]`, `_derniere_fois`) ;
- groupement : `app/services/atelier_groupement.py` (`vue_partenaire()["carnet"]`, `_carnet_partenaire`) ;
- courriel de rappel : `app/services/alerts.py` (`run_tender_alerts` appelle `carnet_notes.envoyer_rappels`) ;
- RGPD : `app/routers/rgpd.py` (export `carnets_de_notes`, `_tombstone_projects` vide la colonne) ;
- démo : `app/services/demo_carnet.py` (appelé par `demo_seed.ensure_demo`, transaction propre) ;
- garde de la démo : `app/core/demo_guard.py` (écritures du carnet, lecture avec l'IA, ajout au savoir-faire) ;
- écrans : `app/static/carnet-notes.js` (nouveau, monté par le composant `<carnet-notes>` de `app/static/app.js`),
  `app/static/app.html` (page du marché, tableau de bord, atelier), `app/static/redaction-partenaire.js` (espace du
  partenaire), `app/static/styles.css` (classes `cn-*`), `app/static/invite.html` (script chargé, avec son empreinte) ;
- migration : `alembic/versions/a2carnet_carnet_notes.py` ;
- tests : `tests/test_redaction_v6_carnet.py` (et l'inventaire de `tests/test_demo_sans_cout.py`).

### F.1 Ce qui est déterministe, ce qui relève de l'IA

**Sans IA** : la date du passage à « Perdu », la procédure du marché (repérée dans le règlement, sinon dans la nature du
marché lue par l'analyse), le courrier pré-rempli, le rappel, le courriel de rappel, la lecture du courrier collé
(lignes « x / y » ou « x sur y »), la famille de chaque critère, les pourcentages, les moyennes, le constat, « La
dernière fois, l'acheteur a écrit », l'ajout du dossier gagné au savoir-faire (découpage BM25 existant, `rag`).

**L'IA PROPOSE (option, bouton « Lire avec l'IA »)** : les notes et commentaires du courrier collé, pour les critères
connus. Contrôle de chaque proposition, sans IA (`carnet_notes.valider_ia`) :
- l'« extrait » (ligne du courrier recopiée) doit être retrouvé dans le courrier (casse, accents, espaces et apostrophes
  tolérés), sinon la note est écartée ;
- CHAQUE nombre (note, note maximale, note de l'offre retenue) doit être écrit dans son extrait ; il est rendu sous sa
  forme ÉCRITE dans le courrier (« 36.5 » de l'IA devient « 36,5 » s'il est écrit ainsi) ; un nombre absent : écarté ;
- une note au-dessus de sa note maximale : écartée ; un critère inconnu : écarté ;
- un commentaire n'est gardé que s'il est dans le courrier, mot pour mot (15 caractères au moins) ;
- RIEN n'est enregistré : les propositions remplissent le formulaire, marquées « à valider », avec leur ligne du
  courrier ; l'utilisateur VALIDE en enregistrant.
Coût et quota : une question du jour (`quota.reserve_question`, borne existante de l'organisation, essai compris),
rendue (`release_question`) si l'IA tombe ou si rien n'est retenu ; 402 / 403 (démo) avant tout appel. Tâche de routage
`questions` (aucune nouvelle tâche), température 0, 1 800 jetons de sortie au plus, courrier de 20 000 caractères au
plus. `tenant_scope` (espace facturé de l'organisation) et `pii_scope` (noms de l'équipe et des fiches « Équipe »
masqués) ; en plus, adresses électroniques et numéros de téléphone du courrier remplacés par « [courriel] » et
« [téléphone] » avant l'appel. Les citations acceptées et écartées sont comptées (`llm_qualite.noter_citations`).

### F.2 Le droit : les articles exacts (relus sur Légifrance le 19/10/2026)

Code de la commande publique, partie réglementaire, livre Ier, titre VIII, chapitre Ier « Information des candidats et
des soumissionnaires évincés » (articles R2181-1 à R2181-7) et chapitre II « Signature et notification du marché ».
Toutes les versions citées sont en vigueur depuis le 01/04/2019.

| Article | Section | Ce qu'il dit (résumé fidèle) | Usage dans Adjugo |
|---|---|---|---|
| R2181-1 (LEGIARTI000037730011) | — | L'acheteur notifie sans délai à chaque candidat ou soumissionnaire concerné le rejet de sa candidature ou de son offre. | Cité seulement quand la procédure n'est pas connue (« articles R2181-1 à R2181-4 »). |
| R2181-2 (LEGIARTI000037730007) | Section 1 : procédure adaptée | Le candidat ou soumissionnaire écarté peut obtenir les motifs du rejet dans un délai de quinze jours à compter de la réception de sa demande ; si son offre n'était ni inappropriée, ni irrégulière, ni inacceptable, l'acheteur lui communique en outre les caractéristiques et avantages de l'offre retenue et le nom de l'attributaire. | Courrier en procédure adaptée ; délai de 15 jours ; « à demander, pas toujours obtenues » (le code oblige à donner les motifs, pas le détail des notes). |
| R2181-3 (LEGIARTI000038327414) | Section 2 : procédure formalisée | La notification du rejet mentionne ses motifs ; après l'attribution, l'acheteur communique en outre le nom de l'attributaire, les motifs du choix de son offre et la date à partir de laquelle il peut signer le marché (R2182-1). | Courrier en procédure formalisée (« pour comprendre les motifs du rejet de notre offre (article R2181-3) »). |
| R2181-4 (LEGIARTI000037730001) | Section 2 : procédure formalisée | À la demande d'un soumissionnaire dont l'offre n'a pas été rejetée comme irrégulière, inacceptable ou inappropriée, l'acheteur communique dans les meilleurs délais et au plus tard quinze jours après la réception de la demande : l'avancement des négociations ou du dialogue, ou, si le marché est attribué, les caractéristiques et avantages de l'offre retenue. | Courrier en procédure formalisée (demande fondée sur cet article) ; délai de 15 jours. |
| R2182-1 (LEGIARTI000037729989) | Chapitre II, section 1 : signature | En procédure formalisée, un délai minimal de onze jours sépare l'envoi de la notification (R2181-1 et R2181-3) de la signature du marché ; seize jours si la notification n'a pas été transmise par voie électronique. | Message « Écrivez vite » en procédure formalisée. |

Aucun autre numéro d'article n'apparaît dans le courrier ni dans les messages (test : tout « R…-… » produit est l'un de
ceux-ci). La jurisprudence de l'étude (§ 5.2 : TA Paris 2511568, CE 490697) n'est pas citée dans le courrier : elle
fonde seulement le message « à temps pour pouvoir contester avant la signature » et la demande des notes par critère
et sous-critère.

Messages (constantes `MSG_DELAI`, `MSG_ADAPTEE_NOTES`) :
- adaptée : « Écrivez vite : l'acheteur doit vous répondre dans les 15 jours qui suivent la réception de votre demande
  (article R2181-2), et l'information doit arriver à temps pour pouvoir contester avant la signature du marché. »
  puis « En procédure adaptée, les notes sont à demander, pas toujours obtenues : le code oblige l'acheteur à donner
  les motifs du rejet, pas le détail des notes. » ;
- formalisée : même début (article R2181-4), puis « En procédure formalisée, le marché peut être signé 11 jours après
  l'envoi du courrier de rejet (16 jours s'il n'a pas été envoyé par voie électronique, article R2182-1). » ;
- inconnue : même début, sans article, puis « Choisissez la procédure du marché pour citer le bon article. ».

### F.3 Données — `projects.carnet_notes` (JSON, NULL = rien)

```
{schema: 1, rev: n,                                    # rev : verrou optimiste (409 « carnet_modifie »)
 perdu_le, perdu_par,                                  # passage à « Perdu » (UTC naïf ISO), compte
 demande: {envoyee_le, par} | absent,                  # « J'ai envoyé ma demande » (Adjugo n'a rien envoyé)
 rappel_masque: {le, par} | absent,                    # « Ne plus me le rappeler »
 rappel_courriel: {le, a} | absent,                    # courriel de rappel envoyé (une fois)
 courrier: {texte, colle_le, empreinte} | absent,      # courrier de l'acheteur collé (20 000 caractères au plus)
 reponse: {valide_le, valide_par,
           lignes: [{cle, critere, parent, poids, note, note_max, note_gagnant, commentaire,
                     famille, famille_proposee, origine: saisie|courrier|ia,
                     extrait_note?, extrait_gagnant?, commentaire_du_courrier?}]} | absent,
 savoir_faire: {doc_id, le, par} | absent}             # dossier gagné ajouté à « Mon savoir-faire »
```

Clés des lignes : celles de « Comment vous serez noté » (`c1`, `c1.1` pour un sous-critère), sinon celles de l'analyse
(`a1`, `a2` : critères lus par l'analyse, dits « à vérifier »), plus les lignes ajoutées par l'utilisateur (`u1`…).
Nombres rangés en valeur (au plus 3 décimales), rendus « 36,5 ». Le passage à « Perdu » réinitialise le rappel
(nouveau départ des 2 jours, rappel masqué et courriel oubliés) mais garde la demande et les notes.

Migration `a2carnetnotes` (idempotente : la colonne n'est ajoutée que si elle manque ; SQLite et Postgres ; retour
arrière réel : `DROP COLUMN`). Le code de production précédent ne lit ni n'écrit cette colonne.

### F.4 Routes

| Méthode | Chemin | Rôle | Démo |
|---|---|---|---|
| GET | `/api/carnet/tableau` | « Où vous perdez des points » et rappels « Demandez vos notes » (organisation seulement) | ouverte |
| GET | `/api/carnet/{pid}` | état du carnet du marché (`etat`) | ouverte |
| GET | `/api/carnet/{pid}/courrier?procedure=adaptee\|formalisee\|inconnue` | courrier pré-rempli (409 si le marché n'est pas perdu) | ouverte |
| POST | `/api/carnet/{pid}/lire` `{courrier}` | lecture SANS IA du courrier collé ; propositions, rien n'est écrit | ouverte (sans coût) |
| POST | `/api/carnet/{pid}/lire-ia` `{courrier}` | lecture avec l'IA (option), propositions contrôlées, rien n'est écrit | refusée (garde + route) |
| PUT | `/api/carnet/{pid}/notes` `{lignes, rev, courrier?}` | notes VALIDÉES ; renvoie l'état | refusée (garde + route) |
| POST | `/api/carnet/{pid}/demande` `{envoyee}` | « J'ai envoyé ma demande » / « Annuler » | refusée (garde + route) |
| POST | `/api/carnet/{pid}/rappel/masquer` | « Ne plus me le rappeler » | refusée (garde + route) |
| POST | `/api/carnet/{pid}/savoir-faire` | marché gagné : ses parties vers « Mon savoir-faire » | refusée (garde + route) |

Accès : le marché doit appartenir à l'organisation (membres), hors corbeille, sinon 404 `marche_introuvable`. Erreurs :
`detail = {code, message}` (codes : `marche_pas_termine`, `marche_pas_perdu`, `marche_pas_gagne`, `carnet_modifie`,
`nombre_illisible`, `note_max_manquante`, `note_trop_haute`, `critere_vide`, `ligne_en_double`, `lignes_invalides`,
`courrier_trop_court`, `courrier_trop_long`, `aucun_critere`, `ia_indisponible`, `deja_ajoute`, `aucun_texte`).

### F.5 « Demandez vos notes » (point 1)

- Marché passé à « Perdu » : la carte « Vos notes sur ce marché » propose « Demandez vos notes » (bulle : Adjugo prépare
  le courrier, c'est vous qui l'envoyez).
- La procédure est repérée SANS IA (`procedure_du_marche`) : dans le règlement lu (« procédure adaptée », « MAPA »,
  « R2123-1 » / « appel d'offres ouvert ou restreint », « procédure formalisée », « R2124-… », « R2161-… »,
  « procédure avec négociation », « dialogue compétitif »), la phrase citée telle qu'écrite ; sinon dans la nature du
  marché lue par l'analyse (« Lu dans l'analyse du marché : vérifiez la procédure ») ; les deux procédures dans le même
  dossier, ou rien : « Je ne sais pas ». « Le présent appel d'offres » ne dit rien (mot courant pour une procédure
  adaptée). L'utilisateur peut toujours changer la procédure (liste : adaptée, formalisée, je ne sais pas).
- Le courrier : objet, texte modifiable dans l'écran, critères de la grille nommés, référence de l'avis, signature
  (représentant légal et entreprise du profil). En groupement : « l'offre du groupement dont nous sommes le chef de
  file ». Actions : « Copier le courrier » (presse-papiers), « Ouvrir dans ma messagerie » (lien `mailto:` avec
  l'adresse de l'acheteur lue dans l'analyse, « vérifiez-la »), « J'ai envoyé ma demande ». Adjugo n'envoie RIEN (test :
  aucun courriel pendant la préparation).
- Rappel dans l'application, 2 jours après le passage à « Perdu » et jusqu'à 60 jours : sur la page du marché (bandeau,
  « Ne plus me le rappeler ») et sur le tableau de bord (« Demandez vos notes : <marché> », ouvre le marché), tant que la
  demande n'est pas marquée envoyée et que les notes ne sont pas saisies.
- Courriel de rappel (`envoyer_rappels`, appelé par le cron existant de la veille `POST /api/admin/run-tender-alerts`) :
  une seule fois par marché, entre 2 et 14 jours après le passage à « Perdu », au compte qui l'a passé à « Perdu »,
  seulement s'il a au moins une alerte active (recherche sauvegardée active, fréquence autre que « manuelle ») ; jamais
  au compte de démonstration ; jamais à l'acheteur (le courriel ne contient pas son adresse). Noté seulement s'il est
  parti (rejouable une fois l'envoi configuré).

### F.6 Quand la réponse arrive (point 2)

- « Saisir les notes reçues » : un formulaire tiré de « Comment vous serez noté » — chaque critère puis ses
  sous-critères, avec leur poids tel qu'écrit ; « Votre note », « Sur » (pré-rempli seulement quand le poids est écrit
  en points), « Offre retenue (si donnée) », « Famille », « Commentaire de l'acheteur » ; « Ajouter un critère » (ligne
  libre, par exemple un sous-critère que seul le courrier donne ; l'API accepte aussi son critère parent). Sans grille : les critères de l'analyse, dits à vérifier.
- « Coller le courrier de l'acheteur » puis « Lire le courrier » (SANS IA, `lire_courrier`) : une ligne qui nomme un
  critère (ses mots principaux, réduits à 5 lettres, sans mots vides ; un sous-critère l'emporte à égalité) ouvre son
  bloc (jusqu'à la ligne qui nomme un autre critère, ou 8 lignes) ; la première note « x / y » ou « x sur y » du bloc est
  la vôtre ; une note précédée de « attributaire », « offre retenue », « lauréat », « titulaire »… (sans « votre »)
  est celle de l'offre retenue ; une ligne « Appréciation : », « Commentaire : », « Observations : », « Points
  forts / faibles : » donne le commentaire. Une date (« 12/11/2026 ») n'est jamais lue comme une note ; une note plus
  grande que son maximum est ignorée. Chaque valeur proposée montre « Lu dans le courrier : « … » ».
- « Lire avec l'IA » (option, § F.1).
- « Valider les notes » : le serveur contrôle chaque ligne (nombre lisible, note maximale présente dès qu'une note est
  donnée, aucune note au-dessus du maximum, critère nommé, pas de doublon, 40 lignes au plus) et le verrou `rev`. Une
  valeur reste « lue dans le courrier, validée par vous » seulement si sa ligne du courrier est encore dans le courrier
  collé ET y porte chaque nombre validé ; sinon « saisie par vous » (l'utilisateur l'a changée, ou aucun courrier n'est
  collé). La famille de chaque ligne est CONFIRMÉE par cet enregistrement. Inscrit au journal chaîné (`carnet.notes`,
  après le commit). Les lignes vides sont ignorées ; tout vider retire les notes.
- Après validation : chaque ligne (note / maximum, %, offre retenue et son %, commentaire, famille, origine ; en
  groupement « partie rédigée par <partenaire> »), la note d'ensemble quand chaque critère a sa note, et le CONSTAT :
  « C'est sur « X » que ce marché a perdu le plus de points : 6 / 10 (60 %). » (la feuille au plus faible pourcentage ;
  un critère dont un sous-critère est noté compte par ses sous-critères).

### F.7 « Où vous perdez des points » (point 3)

- Tableau de bord, carte large sous « Où vous gagnez / perdez » ; rien ne s'affiche tant qu'aucune note n'est saisie
  et qu'aucun rappel n'est dû.
- Pour chaque marché noté, chaque famille : somme des notes / somme des maximums de ses feuilles, en %.
- Familles PROPOSÉES sans IA d'après le nom du critère (`famille_proposee`, dans cet ordre) : prix (prix, montant,
  coût, tarif, financier, économique), environnement (environnement, écologie, déchets, carbone, développement durable,
  énergétique, nuisances, biodiversité), délais (délai, planning, calendrier, durée, réactivité), social et insertion
  (insertion, social, emploi, handicap, apprentissage, solidaire), technique (technique, méthodologie, moyens,
  organisation, qualité, mémoire, références, compétences, matériel, humains, sécurité, savoir-faire, maintenance,
  service, assistance, phasage, exécution, approche, démarche, valeur, chantier, équipe, encadrement), sinon « autre » ;
  un sous-critère sans famille reconnue prend celle de son critère. Confirmées par l'utilisateur à l'enregistrement.
- Une moyenne n'est affichée qu'à partir de 3 marchés (`MOYENNE_MIN`) ; en dessous : « 2 marchés : moyenne à partir de
  3 marchés » et les valeurs une à une. Même règle pour la moyenne de l'offre retenue (marchés où elle est donnée pour
  toute la famille).
- Constat : « Parmi les familles notées sur au moins 3 marchés, c'est en « Technique » que vous perdez le plus de points
  (84 % de la note maximale en moyenne). »
- « Chercher un partenaire qui couvre ce manque » (hors prix et « autre ») : ouvre l'annuaire du réseau de partenaires ;
  la bulle dit « un constat, pas une recommandation ». Aucun filtre n'est déduit.
- Données de l'organisation seulement (marchés des membres, hors corbeille) : aucune statistique entre clients.

### F.8 Dans l'atelier : « La dernière fois, l'acheteur a écrit » (point 4)

Pour chaque partie d'un dossier (hors parties tirées du groupement), la famille de la partie (nom du sous-critère, sinon
du critère, sinon intitulé) ; les commentaires saisis dans les carnets des AUTRES marchés de l'organisation, de la même
famille (jamais prix ni « autre ») ; classés : même acheteur d'abord, puis le critère qui partage le plus de mots
principaux avec la partie, puis le plus récent. L'atelier montre le commentaire, son critère, la note, le marché et
« même acheteur » ou l'acheteur ; bulle : « Il n'est pas envoyé à l'IA. » (`etat()["derniere_fois"] = {section_id:
{commentaire, critere, note, marche, acheteur, meme_acheteur, le_jj, famille_libelle, project_id, bulle}}`). Seulement
pour l'organisation qui porte le dossier : jamais dans l'espace d'un partenaire (ses anciens marchés ne sont pas les
siens).

### F.9 Marché gagné : « Ajouter ce dossier à mon savoir-faire » (point 5)

Bouton sur la carte du marché gagné, à l'initiative de l'utilisateur. Le texte des parties RÉDIGÉES par l'organisation
(jamais celles d'un partenaire, jamais une partie tirée du groupement), version validée sinon courante, sans lignes de CV
(toute ligne qui renvoie à une fiche « Équipe ») ni renvois internes (`memoire_export.clean_markdown`) ni
« [À compléter] », devient UN document « Dossier gagné — <marché> (<acheteur>) » de « Mon savoir-faire » (genre
« mémoire », découpé sans IA). Une seule fois par marché tant que ce document existe (409 `deja_ajoute`) ; retiré de
« Mon savoir-faire », il peut y revenir. Journal chaîné (`carnet.savoir_faire`).

### F.10 Groupement (point 6)

- Les notes du marché sont COMMUNES : le partenaire les lit dans son espace (« Mes parties du dossier de présentation »,
  par le lien ou « Partagé avec moi ») sous « Les notes du marché » : toutes les lignes (note, %, offre retenue,
  commentaire), SES parties signalées (« votre partie ») et résumées en tête, la note d'ensemble du groupement.
- Jamais pour le partenaire : le courrier collé, les extraits, l'origine, la demande, la procédure, le constat, le lien
  vers le réseau.
- Chaque auteur voit les points de SES parties : la ligne de notes est rattachée à la partie du plan qui la traite
  (identifiant du critère de la grille et intitulé du sous-critère ; sinon nom identique ; sinon la seule partie qui en
  reprend la plupart des mots principaux ; aucune partie sûre : rien n'est attribué). Le chef de file voit « partie
  rédigée par <partenaire> » sur ses lignes.
- Le partenaire n'écrit jamais dans le carnet (aucune route du carnet hors de l'organisation du chef de file).
- Limite : un partenaire n'a cet espace que si le chef de file a ouvert le dossier de groupement de la vague 4 (« Qui
  écrit quoi ») ; sans lui, les notes restent chez le chef de file.

### F.11 Démo

`app/services/demo_carnet.py`, sans IA ni réseau ni fichier, rejouable : les trois marchés décidés de la vitrine
reçoivent des notes FICTIVES.
- « Rénovation de couverture — gendarmerie de Limauzac » (perdu, appel d'offres ouvert donc procédure formalisée) :
  passage à « Perdu » et demande notés (2024), courrier de l'acheteur FICTIF (bandeau en tête) collé et lu par le vrai
  lecteur sans IA : 5 lignes « lues dans le courrier, validées par vous » (Prix, Valeur technique et trois sous-critères
  ajoutés) ; constat sur « Gestion environnementale du chantier » (6 / 10).
- « Réfection de toiture-terrasse — médiathèque d'Anjoumont » et « Couverture et zinguerie — école de Riquebach »
  (gagnés) : notes saisies, commentaires de l'acheteur.
- Ce qu'on voit sans rien coder en dur : « Où vous perdez des points » sur 3 marchés (technique 84 %, prix 88 % en
  moyenne ; environnement sur 2 marchés, sans moyenne ; délais sur 1), « Demandez vos notes » et le courrier (article
  R2181-4), la lecture sans IA du courrier fictif (« Lire le courrier » reste ouvert, rien n'est écrit), et dans
  l'atelier du marché « toiture » « La dernière fois, l'acheteur a écrit » sur ses cinq parties.
- Refusé (garde central ET route) : valider des notes, marquer la demande, masquer le rappel, lire avec l'IA, ajouter au
  savoir-faire. Inventaire : `tests/test_demo_sans_cout.py` (`lire-ia` dans `COUTS`, les autres dans `SANS_COUT`).

### F.12 RGPD et cycle de vie

- Export (`/api/rgpd/export`) : `carnets_de_notes` (tout le carnet de chaque marché du compte, courrier collé compris).
- Marché à la corbeille : ne compte plus nulle part ; purgé (pierre tombale) : `carnet_notes` vidé.
- Effacement du compte : la colonne part avec le marché (solo) ou le suit (membre réassigné) ; rien à ajouter.

### F.13 Écrans

- Page du marché gagné ou perdu : la carte « Vos notes sur ce marché » sous le bilan (composant `<carnet-notes
  mode="marche">`, remonté pour chaque marché, relu à chaque changement d'étape).
- Tableau de bord : `<carnet-notes mode="tableau">` (carte large) ; se masque quand il n'y a rien (`.cn-host:empty`).
- Atelier : bloc « La dernière fois, l'acheteur a écrit : » sous les sous-critères de la partie.
- Espace du partenaire : « Les notes du marché » après « Le dossier assemblé » (gabarit `partenaireHtml` de
  `carnet-notes.js`, chargé par app.html et invite.html avec son empreinte SRI).
- Tout texte passe par `cnEsc` ; bulles (i) sur chaque bouton qui demande une explication ; à 375 px la grille du
  formulaire passe sur deux colonnes et les boutons s'étirent.

### F.14 Vérifications

- `tests/test_redaction_v6_carnet.py` : familles, nombres, lecture sans IA, contrôle des propositions de l'IA, procédure,
  courrier (articles permis seulement, délais, aucun envoi), rappel et demande, accès, notes validées (bornes, verrou,
  origine), lignes ajoutées, moyennes à partir de 3 marchés et isolation, lecture avec l'IA (masquage, tenant, quota
  rendu), « La dernière fois », savoir-faire (ses parties seulement, sans CV ni renvois), groupement (notes communes,
  parties du partenaire, rien de privé), courriel de rappel, RGPD, migration SQLite, démo, écrans (Node).
- Suite complète verte (1 875 tests, SQLite) ; SRI (`scripts/sri_update.py --check`) et `node --check` ; écrans vus
  dans le navigateur à 375 px (aucun défilement horizontal) et sur ordinateur (démo : marché perdu, courrier, formulaire
  avec une lecture sans IA, tableau de bord, atelier).
- Postgres 16 depuis la production `a29173a` (script `scratchpad/f6/run_v6f_depuis_prod.py`, modèle des vagues
  précédentes) : 27 contrôles de migration verts (une seule révision appliquée, aucune donnée perdue, marchés
  intacts, NULL au départ, rejeu sans effet, marché perdu en production lu par le code nouveau, parcours complet du
  carnet sur la base montée, code de production redémarré dessus puis après le retour arrière, schéma identique à une
  base neuve) ; 17 fichiers de tests rejoués sur la base montée : `tests/test_redaction_v6_carnet.py` et les tests de
  la démo entièrement verts, et les 63 échecs restants (propres à SQLite : PRAGMA, compteurs) sont exactement ceux du
  code de production sur la même liste, dans le même ordre.

### F.15 Choix à dire à Eliot

1. **Rangement** : une colonne JSON sur `projects` plutôt qu'une table (un carnet par marché, parti avec lui partout où
   le marché part : corbeille, effacement, démo) ; verrou de la ligne du marché pour chaque écriture.
2. **« Validé par l'utilisateur »** = « Valider les notes » (l'enregistrement du formulaire), pas une case par ligne :
   chaque valeur proposée est marquée « à valider » avec sa ligne du courrier ; les familles sont confirmées au même
   moment. À durcir (case par ligne) si un testeur valide sans lire.
3. **Coût de l'option IA** : une question du jour (même borne que « Poser une question à l'IA »), pas une analyse ni
   une refonte de l'atelier ; rendue si rien n'est retenu ou si l'IA tombe.
4. **Le courriel de rappel** passe par le cron de la veille (`run-tender-alerts`) : « l'utilisateur a des alertes » =
   au moins une recherche sauvegardée active non manuelle. Pas de nouveau cron.
5. **Notes du groupement** : visibles seulement dans l'espace de la vague 4 (dossier de groupement ouvert).
6. **Moyenne de l'offre retenue** : aussi à partir de 3 marchés ; sur un marché gagné, la note de l'offre retenue est
   la vôtre : le formulaire la laisse vide.
7. **Juridique** : le texte du courrier cite les articles relus sur Légifrance (§ F.2) ; il est sobre et modifiable par
   l'utilisateur avant l'envoi. À faire relire par un conseil avec les pages juridiques (non touchées ici).
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
