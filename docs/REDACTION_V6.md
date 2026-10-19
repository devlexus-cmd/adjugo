# Rédaction, vague 6 — « Apprendre de ses résultats » : contrat

Étude « rédaction » (`etudes/redaction.md`) § 8 (V6) : le carnet de notes (F, § 6.11), la page « Comment ce dossier a
été préparé » (H, § 6.12) et « Plusieurs lots, un seul effort » (J, § 6.10) ; doctrine § 7 ; décision 9 (§ 10, 9 a).

Base de production : `a29173a` (branche `feat/produit-acheteur-collectivites`, tête Alembic `z1entretienchantier`).

Ce contrat est écrit par chantier : chaque chantier a sa section (F, H, J), les sections ne se recouvrent pas. La
section « Ensemble » dit comment les trois chantiers se rencontrent une fois réunis ; la section « Contre-relecture »
(à la fin) reprend les remarques des relectures et ce qui a changé (les sections F, J et Ensemble sont tenues à jour).

La doctrine (§ 7) vaut pour tous les chantiers : un fait ne vient jamais de l'IA ; on ne dit jamais « vérifié » ; toute
phrase du dossier affichée est retrouvée mot pour mot ; tout nombre lu par l'IA dans un document doit y être retrouvé
mot pour mot et validé par l'utilisateur ; le cadre de l'acheteur commande ; Adjugo n'envoie jamais de courrier à la
place de la PME (il pré-remplit, elle envoie) ; les données sont strictement propres à chaque client (aucune
statistique entre clients) ; la matière reste chez son propriétaire (cloisonnement de la vague 4 intact) ;
`tenant_scope` et `pii_scope` sur chaque appel d'IA, remboursement si l'IA tombe ; un seul process ; tout ce qui peut
se faire sans IA se fait sans IA.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« lot », « commune » ; « valider », jamais « signer » ; jamais « consortium », jamais « vérifié ». Zéro émoji,
explications dans une bulle (i), compact, rien collé aux bords, lisible à 375 px. Le menu n'est pas réorganisé (une
réorganisation suit).

| Section | Chantier | Migration | IA |
|---|---|---|---|
| F | Le carnet de notes : « Demandez vos notes », notes reçues, « Où vous perdez des points », « La dernière fois, l'acheteur a écrit », dossier gagné vers le savoir-faire | `a2carnetnotes` (après `z1entretienchantier`) | bouton facultatif (lecture du courrier), une question du jour, rendue si rien n'est retenu ou si l'IA tombe |
| H | « Comment ce dossier a été préparé » : page facultative à la fin du fichier Word ou PDF | aucune | aucune |
| J | Plusieurs lots, un seul effort : parties communes et propres, un fichier par lot | aucune | aucune nouvelle (une partie commune est rédigée une fois pour tous les lots) |

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
- l'« extrait » (ligne du courrier recopiée) doit être retrouvé dans UNE ligne du courrier (casse, accents, espaces et
  apostrophes tolérés) sans couper un nombre à ses bords (« 2 / 20 » n'est pas dans « 12 / 20 », ni « 6,5 / 40 » dans
  « 36,5 / 40 », ni « 8 / 10 » dans « 8 / 100 »), sinon la note est écartée ; la même règle vaut à la validation pour
  garder « lue dans le courrier » ;
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
| R2182-2 (LEGIARTI000037729987) | Chapitre II, section 1 : signature | Le délai de R2182-1 n'est pas exigé quand le marché est attribué au seul opérateur qui a participé à la consultation, ni pour les marchés subséquents d'un accord-cadre ou les marchés spécifiques d'un système d'acquisition dynamique. | Message en procédure formalisée (« ce délai ne s'applique pas, notamment, à un marché subséquent d'un accord-cadre ») ; marché subséquent repéré sans IA : message dédié et phrase citée. |

R2181-4 et R2182-2 relus de nouveau sur Légifrance le 19/10/2026 (contre-relecture). Aucun autre numéro d'article
n'apparaît dans le courrier ni dans les messages (test : tout « R…-… » produit est l'un de
ceux-ci). La jurisprudence de l'étude (§ 5.2 : TA Paris 2511568, CE 490697) n'est pas citée dans le courrier : elle
fonde seulement le message « à temps pour pouvoir contester avant la signature » et la demande des notes par critère
et sous-critère.

Messages (constantes `MSG_DELAI`, `MSG_ADAPTEE_NOTES`) :
- adaptée : « Écrivez vite : l'acheteur doit vous répondre dans les 15 jours qui suivent la réception de votre demande
  (article R2181-2), et l'information doit arriver à temps pour pouvoir contester avant la signature du marché. »
  puis « En procédure adaptée, les notes sont à demander, pas toujours obtenues : le code oblige l'acheteur à donner
  les motifs du rejet, pas le détail des notes. » ;
- formalisée : « Écrivez vite : si votre offre n'a pas été écartée comme irrégulière, inacceptable ou inappropriée,
  l'acheteur doit vous répondre au plus tard 15 jours après la réception de votre demande (article R2181-4), et
  l'information doit arriver à temps pour pouvoir contester avant la signature du marché. En procédure formalisée, le
  marché ne peut en principe pas être signé moins de 11 jours après l'envoi du courrier de rejet (16 jours s'il n'a pas
  été envoyé par voie électronique, article R2182-1) ; ce délai ne s'applique pas, notamment, à un marché subséquent
  d'un accord-cadre (article R2182-2). » ; le courrier formalisé reprend la condition (« Si notre offre n'a pas été
  écartée comme irrégulière, inacceptable ou inappropriée, nous vous demandons, en application de l'article
  R2181-4… ») ;
- formalisée, marché subséquent d'un accord-cadre (« marché subséquent » lu sans IA dans le règlement, sinon dans
  l'analyse ; phrase citée sous le message) : `MSG_DELAI_SUBSEQUENT` — la réponse sous 15 jours (R2181-4, même
  condition) et « le délai de 11 jours avant la signature ne s'applique pas à ce marché (article R2182-2) » ;
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
                     extrait_note?, extrait_gagnant?, commentaire_du_courrier?,
                     lot?, lot_libelle?}]} | absent,   # lot : marché alloti, un relevé par lot (section Ensemble)
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
`courrier_trop_court`, `courrier_trop_long`, `aucun_critere`, `ia_indisponible`, `deja_ajoute`, `aucun_texte` ; et,
pour un marché alloti, `lot_requis` — section Ensemble, E.3).

### F.5 « Demandez vos notes » (point 1)

- Marché passé à « Perdu » : la carte « Vos notes sur ce marché » propose « Demandez vos notes » (bulle : Adjugo prépare
  le courrier, c'est vous qui l'envoyez).
- La procédure est repérée SANS IA (`procedure_du_marche`) : dans le règlement lu (« procédure adaptée », « MAPA »,
  « R2123-1 » / « appel d'offres ouvert ou restreint », « procédure formalisée », « R2124-… », « R2161-… »,
  « procédure avec négociation », « dialogue compétitif »), la phrase citée telle qu'écrite ; sinon dans la nature du
  marché lue par l'analyse (« Lu dans l'analyse du marché : vérifiez la procédure ») ; les deux procédures dans le même
  dossier, ou rien : « Je ne sais pas ». « Le présent appel d'offres » ne dit rien (mot courant pour une procédure
  adaptée). L'utilisateur peut toujours changer la procédure (liste : adaptée, formalisée, je ne sais pas).
- Le courrier : objet, texte modifiable dans l'écran, critères nommés SEULEMENT s'ils viennent de « Comment vous serez
  noté » (phrase retrouvée dans le règlement ; ceux de l'analyse, « à vérifier », ne partent pas chez l'acheteur),
  référence de l'avis, signature (représentant légal et entreprise du profil). En groupement : « l'offre du groupement
  dont nous sommes le chef de file » — même règle que l'atelier : des partenaires invités (invitations actives), ou un
  groupement retenu par l'utilisateur (plan « auto » faux, au moins un partenaire) ; jamais le plan proposé
  automatiquement après l'analyse. Actions : « Copier le courrier » (presse-papiers), « Ouvrir dans ma messagerie » (lien `mailto:` avec
  l'adresse de l'acheteur lue dans l'analyse, « vérifiez-la »), « J'ai envoyé ma demande ». Adjugo n'envoie RIEN (test :
  aucun courriel pendant la préparation).
- Rappel dans l'application, 2 jours après le passage à « Perdu » et jusqu'à 60 jours : sur la page du marché (bandeau,
  « Ne plus me le rappeler ») et sur le tableau de bord (« Demandez vos notes : <marché> », ouvre le marché), tant que la
  demande n'est pas marquée envoyée et que les notes ne sont pas saisies.
- Courriel de rappel (`envoyer_rappels`, appelé par le cron existant de la veille `POST /api/admin/run-tender-alerts`) :
  une seule fois par marché, entre 2 et 14 jours après le passage à « Perdu », au compte qui l'a passé à « Perdu »
  s'il est ENCORE membre de l'organisation du marché (sinon au titulaire actuel du marché : ses marchés lui ont été
  réassignés au retrait ; jamais à un ancien membre), seulement s'il a au moins une alerte active (recherche sauvegardée active, fréquence autre que « manuelle ») ; jamais
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
  groupement « partie rédigée par <partenaire> »), la note d'ensemble quand CHAQUE critère du formulaire (niveau 1 :
  ceux de « Comment vous serez noté » ou de l'analyse, et les critères ajoutés) a sa note — un critère sans sa note dont
  chaque sous-critère est noté compte pour leur somme ; sinon aucune somme, et « Note d'ensemble : 1 critère noté sur 2.
  Elle s'affiche quand chaque critère a sa note (ou chacun de ses sous-critères). » (`notes.messages_total`) — et le
  CONSTAT, dit tel qu'il est calculé : « C'est sur « X » que ce marché a obtenu sa note la plus faible, en pourcentage
  de la note maximale : 6 / 10 (60 %). » (la feuille au plus faible pourcentage ; un critère dont un sous-critère est
  noté compte par ses sous-critères ; ce n'est pas forcément là que le plus de points ont été perdus).

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
- Constat : « Parmi les familles notées sur au moins 3 marchés, c'est en « Technique » que vos notes sont les plus
  faibles (84 % de la note maximale en moyenne). »
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
- Formulaire : un critère ajouté montre le champ « Critère » (jamais, en plus, son titre en lecture), puis, sur un
  marché à plusieurs lots, le choix de son lot (`cnLigneTete`) ; un critère connu montre son titre et son poids.
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

Dossier à plusieurs lots (J) : `GET …/preparation?lot=2` (la page du fichier de CE lot) et `lot` dans le corps de
l'export ; voir la section Ensemble, E.2.

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

---

## J — Plusieurs lots, un seul effort

En BTP, on répond souvent à deux ou trois lots d'un même marché, avec un mémoire par lot. Pour un marché alloti
auquel l'entreprise répond sur **deux lots ou plus**, l'atelier distingue :

- des **parties communes** (présentation, qualité, sécurité, environnement…), rédigées une fois : UNE partie, un
  seul texte, une seule chaîne de versions, reprise telle quelle dans le dossier de chaque lot. Une modification
  se répercute donc dans tous les lots par construction (même texte, même version) ;
- des **parties propres à chaque lot** (méthodologie, moyens, planning…), une par lot ;

et l'export produit **un fichier par lot** (Word, PDF) : les parties communes et celles du lot, numérotées pour lui,
ses limites de pages contrôlées pour lui seul, nommé comme le règlement l'exige s'il le dit, sinon avec le numéro
et l'intitulé du lot.

**Marché à un seul lot, ou réponse à un seul lot : RIEN ne change** (aucune donnée nouvelle, mêmes écrans, même
export, même empreinte d'état, voir J.13).

### J.0 Source de vérité du code

- règles (repérage, grille par lot, commune ou propre, fusion des plans, nommage, groupement) :
  `app/services/atelier_lots.py` (nouveau ; fonctions pures, ni IA ni réseau ni base, sauf la lecture de
  `plan_meta`) ;
- atelier : `app/services/atelier.py` (`_plan`, `pieces_du_marche`, `texte_pour_lots`, `lots_reperes`,
  `lots_demandes`, `proposition`, `_plan_meta`, `creer_dossier`, `reconstruire_plan`, `changer_lots`,
  `changer_portee`, `ajouter_section`, `remettre_section`, `modifier_section`, `_groupe_sous_critere`, `_rangs`,
  `contexte_rendu`, `_limites_doc`, `compteur`, `evaluer_limites`, `etat_hash`, `blocage`, `derogation_du_lot`,
  `enregistrer_derogation`, `nom_fichier`, `apercu_export`, `lot_a_exporter`, `exporter`, `_archiver`,
  `dossier_commun` / `_dossier_commun_lots`, `section_out`, `_etat_des_lots`, `_blocage_ensemble`, `etat` /
  `_lots_out`, `exigences_out`, `changements_grille` / `_changements_grille_lots`, `appliquer_grille` /
  `_appliquer_grille_lots`, `_executer`) ;
- page de garde : `app/services/atelier_export.py` (`_lignes_garde`) ;
- consigne de rédaction : `app/services/agents/memoire.py` (`_consigne_partie`) ;
- contrôle des faits : `app/services/faits_a_relire.py` (`_LOT_REF`) ;
- groupement : `app/services/atelier_groupement.py` (`proposition`, `_lots_du_dossier`, `_section_base_out`,
  `note_acheteur`) ; entretien chantier : `app/services/entretien_chantier.py` (`pour_parties`) ;
- routes : `app/routers/atelier.py` ; archivage du dossier commun : `app/routers/sourcing.py`
  (`_archive_memoire`) ; garde de la démo : `app/core/demo_guard.py` ;
- écrans : `app/static/app.js` (`atlLots*`, `atlLot*`, `atlPortee`, `atlExport(fmt, lot)`, `atlSectionsVues`,
  `atlNumPart`), `app/static/app.html` (atelier, carte du marché, fenêtre « Lots auxquels vous répondez »),
  `app/static/styles.css` (`.atl-lots*`, `.atl-lot-*`), `app/static/redaction-partenaire.js` (le lot d'une partie) ;
- démo : `app/services/demo_lots.py` (nouveau), appelé par `demo_seed.ensure_demo` dans SA transaction ;
- tests : `tests/test_redaction_v6_lots.py`, `tests/test_demo_plusieurs_lots.py`.

### J.1 Ce que voit l'utilisateur

**Avant de créer le dossier** (plan proposé, rien n'est enregistré), si le règlement répartit le marché en deux lots
ou plus : un encadré « Ce marché est réparti en 3 lots », la question « À quels lots répondez-vous ? », une case par
lot repéré (« Lot 2 — Couverture et zinguerie », bulle (i) « Le règlement dit : « … » (source) »), un champ « Un lot
absent de la liste : son intitulé » (numéro + intitulé, « indiqué par vous »). Deux lots cochés ou plus : le plan
proposé est recalculé aussitôt (aucune IA) — chaque partie porte l'étiquette « Commune » ou « Lot 2 » — et le message
du plan le dit (« Vous répondez à 2 lots : 1 partie commune, rédigée une fois pour tous vos lots, et 4 parties
propres à un lot ; un fichier par lot à l'export »). Un seul lot coché, ou aucun : un seul dossier, comme avant.

**Dans l'atelier** (dossier à plusieurs lots) :
- en-tête : « Vous répondez à 2 lots : Lot 2 — … · Lot 3 — … » (bulle (i) : ce qu'est une partie commune, la
  règle), lien « Changer les lots » (ordinateur) ; les boutons d'export généraux sont remplacés par l'export lot par
  lot ;
- « Un fichier par lot » : pour chaque lot, son état (« Prêt à exporter », « Export avec dérogation », « N parties à
  valider », « Bloqué »), ses parties (« 3 parties, dont 1 commune »), son compteur (« Environ 3 pages · 217 mots »),
  ses limites (« Environ 3 pages pour 6 pages au plus », phrase du règlement en bulle), le nom de son fichier (bulle :
  « Nommé comme le règlement l'exige : « … » » et sa phrase), « Voir pourquoi » (ce qui bloque ce lot, liens vers
  les parties), « Exporter malgré tout… » (dérogation de CE lot), Word et PDF, « Comment vous serez noté pour ce
  lot » (repliable : critères, poids pour ce lot, phrase, contrôle du total), dernier export ;
- plan : filtre « Toutes · Communes · Lot 2 · Lot 3 » (le filtre d'un lot montre son dossier : parties communes et
  les siennes, avec SES numéros), étiquette « Commune » / « Lot 2 » sur chaque partie ; « Nouvelle partie » demande
  « Commune à tous les lots » ou un lot ;
- partie : étiquette « Partie commune à vos lots » ou « Lot 2 — … », bulle (i), lien « La rédiger pour chaque lot » /
  « La rendre commune à tous les lots » (fenêtre de confirmation de l'application) ;
- parties retirées : leur lot.

**Dossier à un seul lot d'un marché alloti** : une ligne discrète « Ce marché est réparti en 3 lots : ce dossier en
prépare un seul. » et le lien « Répondre à plusieurs lots » (ordinateur).

**Carte du marché** : « Un fichier par lot : Lot 2 Prêt à exporter · Lot 3 Bloqué » ; avant la création, « Ce marché
est réparti en 3 lots : dans l'atelier, choisissez ceux auxquels vous répondez (un fichier par lot). »

**Sur téléphone** (375 px) : tout se lit, rien ne déborde ; on valide ; on n'écrit pas et on n'exporte pas (comme
avant). Les cases des lots, le filtre et les étiquettes passent à la ligne.

### J.2 Données : aucune migration

Le modèle de l'atelier prévoit les lots depuis la vague 2 (`dossier_sections.lot`, `String(120)`, « vague 6 (plusieurs
lots), vide aujourd'hui ») ; il suffit :
- `dossier_sections.lot` : `""` = partie commune, sinon le numéro du lot (« 2 ») ;
- `dossiers_presentation.plan_meta["lots"]` (posé à la construction du plan, repris par `appliquer_grille`) :
  `{actif: true, liste: [{numero, intitule, phrase, source, origine}], grilles: {n: grille du lot (J.4)},
  limites: {n: limites du dossier du lot}, sources: {n: cadre|grille|libre}, criteres_hors_dossier: {n: [...]},
  nommage: {modele, phrase, source} | null, regle_commune}` ; absent pour un dossier à un seul lot ;
- par lot, sous la clé `lots` des colonnes JSON existantes : `derogation["lots"][n]` (même forme que la dérogation
  d'un dossier à un seul lot), `dernier_export["lots"][n]` (et le dernier export tous lots confondus à la racine,
  avec `lot`), `compteur["lots"][n]` (cache du compteur du dossier de ce lot).

Rien n'est ajouté au schéma ; le code de production lit sans erreur un dossier écrit par ce code (les clés
inconnues sont ignorées) — vérifié sur Postgres (J.15).

### J.3 Les lots du marché, repérés sans IA (`atelier_lots.reperer`)

Dans les pièces lues du dossier (lecture intégrale rangée, sinon le texte de l'ancienne lecture, sinon l'extrait de
l'analyse — jamais une relecture du fichier) :
1. lignes « Lot n° 2 : Couverture », « LOT 02 – GROS ŒUVRE », « - Lot 3. Étanchéité » (en tête de ligne), dans le
   règlement d'abord, puis l'acte d'engagement, les pièces au nom inconnu, le CCAP, le cadre de réponse — jamais le
   bordereau (« Lot 1 — Installation du chantier » y est un poste de prix) ni le CCTP (ses articles par lot décrivent
   des travaux) ;
2. sinon, énumération dans une phrase qui parle des lots (« … répartis en trois lots : lot 1, désamiantage et retrait
   d'amiante ; lot 2, isolation thermique… ») ;
3. un lot proposé par l'analyse (`details.allotissement`) n'est gardé que si son intitulé est retrouvé mot pour mot
   dans le dossier, dans les 60 caractères qui suivent son numéro (`origine: "analyse"`) ;
4. refusés : une phrase (« Lot 1 : sera attribué… », verbe), un poids ou un montant (« Lot 2 : 40 % »), un intitulé
   qui commence par une conjonction ou un chiffre.

Chaque lot a SA phrase (retrouvée mot pour mot) et sa source (« Règlement de la consultation (RC.pdf) »). `alloti` :
au moins deux lots. `annonce` : le nombre écrit (« en 3 lots ») ; s'il diffère, le message le dit (« Le règlement
annonce 3 lots et Adjugo en a repéré 2 : vérifiez… vous pouvez ajouter un lot »). « Lot unique » (« le marché est
passé en lot unique ») : `unique` = sa phrase, pas d'encadré. Le résultat est gardé en mémoire du process pour un
même dossier lu et une même analyse.

**Lots choisis** (`atelier_lots.choisir`) : les numéros cochés doivent avoir été repérés ; un lot indiqué par
l'utilisateur a un numéro (1 à 99) et un intitulé (2 caractères au moins), `origine: "utilisateur"` (« indiqué par
vous », aucune phrase) ; pas de doublon ; 8 lots au plus par dossier. Erreur : 422 `lots_invalides` (message
affichable). Moins de deux lots : un seul dossier.

### J.4 La grille de chaque lot, depuis SA phrase (`atelier_lots.grilles_par_lot`)

Les critères sont ceux de « Comment vous serez noté » (proposés par l'analyse, contrôlés sans IA) ; pour chaque lot,
on lit dans la zone des critères du règlement (du titre « critères de jugement / jugement des offres… » à l'article
suivant, 6 000 caractères au plus) les mentions de lots (« Pour le lot 2 : … », « Lot 3 – … », « lots 1 et 2 »,
« lots 1 à 3 ») ; un règlement propre à un lot (pièce nommée ou titrée « lot 3 ») est en entier la zone de ce lot.
Quatre cas, dits à l'écran (`grille.mode`, `grille.message`) :

| mode | quand | ce que porte chaque critère |
|---|---|---|
| `commune` | aucune mention de lot dans la zone des critères | la grille du règlement, telle quelle ; la phrase « Pour chacun des lots… » si elle existe |
| `propre` | des critères écrits pour CE lot | le poids rattaché au critère dans la partie du lot (même règle de rattachement que la grille : `_attribute`), sa phrase mot pour mot depuis la mention du lot (« Pour le lot 3 : valeur technique 40 % ; prix 60 %. ») ; un critère absent de la partie du lot : « à vérifier », hors du plan de ce lot, avec la raison ; un sous-critère n'est repris que s'il figure aussi dans la partie du lot |
| `generale` | d'autres lots ont leurs critères, pas celui-ci | la grille générale, et « vérifiez dans le règlement » |
| `illisible` | deux lots cités sur la même ligne sans poids entre eux (tableau « Critère \| Lot 1 \| Lot 2 »), ou un poids écrit JUSTE AVANT la mention d'un lot, sur la même ligne (« 60 % pour le lot 2, 40 % pour le lot 3 », « 60 % (lot 2) ») : la lecture d'une mention à la suivante donnerait ce poids au lot suivant | les critères SANS poids (jamais un poids deviné ni celui d'un autre lot), « vérifiez le poids de chaque critère pour ce lot » |

Le contrôle du total (« Les poids retrouvés font bien 100 % au total ») est refait pour chaque lot. Un choix de
l'utilisateur dans « Comment vous serez noté » vaut pour les lots : un critère écarté l'est partout ; un critère
confirmé entre dans le plan de chaque lot, sans reprendre un poids lu ailleurs.

**Limites par lot** (`limites_du_lot`) : une limite dont la phrase cite un lot (« Pour le lot 3, le mémoire compte 5
pages au maximum ») ne vaut que pour lui et remplace la limite générale du même type ; une limite qui ne cite aucun
lot (« 6 pages au maximum par lot ») vaut pour chacun. La police vaut pour tous. Une phrase qui cite PLUSIEURS lots
(« 6 pages au maximum pour le lot 2 et 3 pages au maximum pour le lot 3 ») : chaque valeur va au lot cité juste après
elle, sinon juste avant (« pour le lot 2, 6 pages ; pour le lot 3, 3 pages »), seulement si toutes les valeurs de la
phrase s'attribuent ainsi et qu'aucun lot n'en reçoit deux du même type ; sinon (« respectivement », valeurs
groupées) aucune n'est imposée : elles sont dites « selon le lot » parmi les limites qu'Adjugo ne compte pas
(`objet: selon_lot`). Dans une liste de lots, un nombre suivi de ce qu'il mesure (« lot 2 et 3 pages ») n'est pas un
lot (`_PAS_UNE_MESURE`).

### J.5 Le plan : parties communes et parties propres à chaque lot

Pour chaque lot, le plan d'un seul dossier est construit comme avant (`atelier_plan.build_plan`) avec SA grille et
SON cadre de réponse (pièce de cadre propre au lot, sinon le cadre commun) ; puis `atelier_lots.fusionner` :
- **commune** : la règle `est_commune` le dit (intitulé : présentation, qualité, sécurité, santé, hygiène,
  environnement, développement durable, RSE, social, insertion, déchets, carbone, groupement — et AUCUN mot de partie
  propre : méthodologie, moyens, humain, matériel, organisation du chantier, planning, délai, phasage, mode
  opératoire, compréhension, exécution, technique, équipe, encadrement, intervention, prestations, ouvrages,
  références…) ET la même partie (même source, même critère, même intitulé, mêmes titres au-dessus ; même numéro pour
  une question du cadre) figure dans le plan de CHAQUE lot ; elle porte le poids de son critère s'il est le même pour
  tous les lots, sinon aucun (chaque lot le dit dans sa grille) ;
- sinon **propre à chaque lot** : une partie par lot qui la note.

Ordre : chaque partie commune une fois, là où elle tombe dans le plan du premier lot ; entre deux parties communes,
les parties propres de chaque lot, lot par lot. Le dossier d'un lot (parties communes + les siennes) suit donc
l'ordre de SON plan. Numérotation : celle du dossier du lot (les sous-critères d'un critère, communs ou propres, sous
le même titre : « 1.1 Méthodologie », « 1.2 Moyens », « 1.3 Gestion environnementale ») ; dans la liste de l'atelier,
chaque partie porte le numéro de son lot (une partie commune : celui du premier lot), et le titre d'une partie
propre dit son lot (« 1.1 Méthodologie d'exécution (lot 3) »). Les sous-critères d'un critère restent ensemble dans
le dossier de chaque lot (`_coupes`, `_place_sans_couper`) : une partie AJOUTÉE après un sous-critère, ou DÉPLACÉE,
passe le groupe dans le dossier de chaque lot concerné (tous pour une partie commune, le sien sinon) ; une partie
REMISE rejoint ses sœurs de chaque lot ; le déplacement d'une partie de sous-critère qui couperait un groupe est
refusé (409 `groupe_sous_criteres`).

Un dossier à plusieurs lots n'est jamais tronqué en silence : plus de 60 parties → 422 `trop_de_parties` avec la
raison. Les parties tirées du groupement (vague 4) sont communes à tous les lots.

**Portée d'une partie** (`changer_portee`, `PUT …/sections/{sid}/portee`) :
- commune → propre : la partie garde son texte et ses versions pour le premier lot ; une partie vide « à écrire » est
  ajoutée pour chacun des autres (même intitulé, critère, poids de chaque lot, limite) ;
- propre → commune : la partie choisie garde son texte et devient commune ; la même partie des autres lots est
  RETIRÉE (jamais supprimée, remettable) — 409 `portee_a_confirmer` si l'une a du texte, puis `remplacer: true` ; la
  partie commune prend, dans le dossier de CHAQUE lot, la place qu'y avait la partie de ce lot (l'ordre du règlement,
  « 1.1 Méthodologie » puis « 1.2 Moyens », ne change dans aucun fichier) ; si les lots ne la rangent pas au même
  endroit : 409 `portee_ordre` (rien n'est changé, le message dit de la placer d'abord au même endroit) ;
- refus : dossier à un seul lot (409 `un_seul_lot`), partie tirée du groupement (409 `partie_du_groupement`), partie
  d'un partenaire, ou dont une sœur est d'un partenaire (403 `partie_d_un_partenaire`), rédaction en cours (409).

**Changer les lots** (`changer_lots`, `PUT …/lots`) : le plan est reconstruit pour les nouveaux lots (ou pour un seul
dossier) ; mêmes règles que « Reconstruire le plan » (parties retirées, jamais supprimées, 409
`plan_remplacement_a_confirmer` si l'une a du texte ; la partie d'un partenaire reste, commune si son lot n'est plus
dans le dossier) ; 409 `rien_a_changer` si les lots sont les mêmes. **Remettre** une partie dont le lot n'est plus
dans le dossier : elle revient commune.

### J.6 Routes (`app/routers/atelier.py`)

| Route | Corps / paramètres | Réponse |
|---|---|---|
| `GET /api/atelier/{pid}` (sans dossier) | `?lots=2,3` (numéros repérés), `?ajoutes=[{"numero","intitule"}]` (JSON) : prévisualisation | `proposition` avec `lots_du_marche` (J.7) et, pour deux lots ou plus, `lots` et une étiquette `lot` sur chaque partie ; 422 `lots_invalides` |
| `POST /api/atelier/{pid}` | `{base, sans_ia, lots: ["2","3"], lots_ajoutes: [{numero, intitule}]}` | 201 + état ; 422 `lots_invalides`, `trop_de_parties` |
| `GET /api/atelier/{pid}/lots` | — | `{du_marche: lots repérés (J.7), dossier: [{numero, libelle}]}` (lecture seule) |
| `PUT /api/atelier/{pid}/lots` | `{lots, lots_ajoutes, remplacer}` | état ; 409 `plan_remplacement_a_confirmer`, `rien_a_changer`, `redaction_en_cours` ; 422 `lots_invalides`, `trop_de_parties` |
| `PUT /api/atelier/{pid}/sections/{sid}/portee` | `{commune: bool, remplacer: bool}` | état ; voir J.5 |
| `POST /api/atelier/{pid}/sections` | `{intitule, apres_section_id, lot}` : `""` commune, sinon un lot du dossier (défaut : le lot de la partie après laquelle on ajoute) | partie ; 422 `lot_inconnu` |
| `POST /api/atelier/{pid}/export` | `{format, etat_hash, lot}` | fichier du lot ; 422 `lot_requis` (avec `lots: [{numero, libelle}]`), `lot_inconnu` (lot hors du dossier, ou lot donné pour un dossier à un seul lot) ; 409 `export_bloque` (raisons du lot), `etat_modifie` |
| `POST /api/atelier/{pid}/derogation` | `{raison, texte, etat_hash, lot}` | `{derogation, blocage (du lot), lot}` ; 422 `lot_requis`, `lot_inconnu` ; erreurs d'avant |

`GET …/compteur` rend l'ensemble (J.7). Toutes les autres routes sont inchangées. Les écritures nouvelles (`PUT
…/lots`, `PUT …/portee`) sont refusées au compte de démonstration par le garde central (403 « La démo est en lecture
guidée… ») et classées dans `tests/test_demo_sans_cout.py` (aucune IA, aucun email, aucun fichier, aucun réseau).

### J.7 L'état (`GET /api/atelier/{pid}`)

Nouveau bloc `lots` :
```json
{"actif": true,
 "liste": [{"numero": "2", "intitule": "Couverture et zinguerie", "libelle": "Lot 2 — Couverture et zinguerie",
            "phrase": "Lot 2 : Couverture et zinguerie", "source": "Règlement de la consultation (RC.pdf)",
            "origine": "reglement", "origine_libelle": "repéré dans le règlement",
            "parties": [41, 42, 45], "parties_propres": 2, "parties_communes": 1, "numeros": {"41": "1.1", "45": "1.3"},
            "compteur": {"total": {"pages": 3, "mots": 217, "...": "..."}, "police": {}, "environ": true, "message": "..."},
            "limites": [Limite (+ "lot")], "blocage": Blocage du lot (+ "lot"), "derogations_possibles": [...],
            "export": Apercu (+ "lot", "nommage": {"selon_reglement", "message", "phrase", "source"}),
            "dernier_export": {"le", "par", "format", "nom", "empreinte", "ia", "derogation", "etat_hash"} | null,
            "grille": {"mode", "message", "phrase", "source", "lignes": [{"id", "critere", "poids", "poids_source",
                       "phrase", "source", "statut", "dans_le_plan", "prix", "message", "sous_criteres"}],
                       "controle_total": {"statut", "message"}},
            "source_plan": "grille", "criteres_hors_dossier": [...]}],
 "du_marche": {"alloti": true, "lots": [{"numero", "intitule", "phrase", "source", "origine", "origine_libelle"}],
               "annonce": 3, "message": "...", "unique": "", "choisis": ["2", "3"], "regle_commune": "..."},
 "regle_commune": "Partie commune quand son intitulé parle de présentation, …",
 "nommage": {"modele", "phrase", "source"} | null}
```
Pour un dossier à un seul lot : `{"actif": false, "liste": [], "du_marche": {...} | null, "regle_commune", "nommage":
null}`.

Chaque partie (`sections[]`) porte `lot` (`""` commune), `lot_libelle`, `commune` (dossier à plusieurs lots seulement),
`portee_modifiable` ; son `titre` dit son lot. `sections_retirees[]` porte `lot_libelle`.

Dossier à plusieurs lots, en tête de l'état : `compteur.total` vaut `null` (le compteur est celui de chaque lot) ;
`limites` réunit les limites du document de chaque lot (« Dossier du lot 2 : … », avec `lot`) et celles des
parties, une fois ; `blocage` est l'**ensemble** (pour la carte du marché) : ses raisons nomment le lot de chaque
partie (« 1.1 Méthodologie (lot 3) »), `peut_exporter` vaut si CHAQUE lot peut être exporté, `derogation` est celle
d'un lot quand tous peuvent l'être et qu'au moins un l'est par dérogation, `etat_hash` est l'empreinte des lots,
`par_lot: true` ; `derogations_possibles` est vide (une dérogation se demande lot par lot) ; `export` est l'aperçu du
premier lot. `exigences` : les titres nomment le lot. `grille` (changements de « Comment vous serez noté » depuis le
plan) : relue pour chaque lot (J.4) seulement si la grille du marché a changé ; « Mettre le plan à jour » ajoute
une partie par critère confirmé depuis dans chaque lot qui le note (commune si la règle le dit et que tous les lots
le notent) et reprend les poids de chaque lot.

### J.8 L'export d'un lot

- **Contenu** : les parties communes (leur texte commun, le même dans chaque fichier) et les parties du lot, dans
  l'ordre du dossier du lot, numérotées pour lui ; page de garde : « Lot : 2 — Couverture et zinguerie » sous
  « Marché » ; mêmes règles qu'avant (aucune marque interne, mention « Préparé avec assistance IA » seulement si
  l'IA a servi pour un texte de CE fichier).
- **Nom** (`atelier_lots.nommage` + `nom_du_lot`) : la règle de nommage du règlement (« Chaque mémoire est remis
  dans un fichier nommé « Lot X - Mémoire technique - Nom du candidat » », repérée sans IA, avec sa phrase) est
  suivie quand Adjugo sait remplir chacun de ses champs — numéro du lot (« X », « XX » → « 02 », « n », « [n° du
  lot] »…), nom du candidat (« Nom du candidat », « [raison sociale] », « NomEntreprise »… → le nom de l'entreprise
  du profil ; « [raison sociale] » seul aussi), intitulé du lot ; une règle sans numéro de lot reçoit « - Lot 2 » (un
  fichier par lot) ; une extension écrite dans la règle (« LOTXX_MT_NomCandidat.pdf ») n'entre pas dans le nom
  (l'export ajoute celle du format choisi) et le message dit « Le règlement demande un fichier « .pdf » : exportez
  dans ce format. ». Un champ
  inconnu (« [SIRET] ») ou un nom d'entreprise absent : nom par défaut et message (« … qu'Adjugo ne sait pas
  compléter : renommez le fichier avant de le déposer », « renseignez le nom de votre entreprise »). Sans règle :
  « Mémoire technique - Lot 2 - Couverture et zinguerie » (le nom du document est celui du règlement, comme avant).
  L'aperçu le dit avant l'export (`export.nommage`).
- **Blocage** : celui du dossier du lot (parties vides, « [À compléter] », faits à relire, partie d'un partenaire
  en attente, limite dépassée de CE lot) ; avertissement « Dossier du lot 2 non validé : N parties à valider ».
- **Dérogation** : pour CE lot et CET état seulement ; inscrite au journal chaîné AVANT d'être retenue (méta `lot`) ;
  une dérogation du lot 2 n'ouvre jamais l'export du lot 3. L'empreinte d'état d'un lot inclut son numéro (celle
  d'un dossier à un seul lot est inchangée, J.13).
- **Après l'export** : `dernier_export["lots"][n]`, fichier rangé dans le dossier du marché (« Mémoire technique »,
  un nom par lot : aucun ne remplace l'autre), liste des pièces mise à jour (jusqu'à 2 × lots + 2 fichiers gardés),
  journal chaîné (`atelier.export`, méta `lot`).
- **Dossier commun** (« Préparer mes documents », ZIP) : un fichier Word et un PDF PAR LOT (clés `docx:2`,
  `pdf:2`), chacun soumis aux règles de l'export de son lot ; un lot bloqué sans dérogation n'est pas joint
  (« BLOQUANT — Lot 2 — … : dossier de présentation non joint : … ») et le fichier de ce lot exporté plus tôt depuis
  l'atelier RESTE dans le dossier du marché (`garder`, comme un dossier à un seul lot bloqué : rien n'est retiré) ;
  versions validées de préférence, comme avant.

### J.9 La rédaction (IA)

- **Économie sans perte** : une partie commune est rédigée UNE fois pour tous les lots (une seule action d'IA, un
  seul texte) ; le dossier compte toujours pour UNE analyse (décision 6a), tous lots compris ; rien d'autre ne
  change dans le débit, le remboursement, `tenant_scope` et `pii_scope`.
- **Consigne** (partie propre au dossier, hors du bloc mis en cache) : « CETTE PARTIE CONCERNE SEULEMENT LE LOT 3
  (Étanchéité des toitures-terrasses) : elle figure dans le dossier de ce lot ; ne parle que des travaux de ce lot. »
  ou « CETTE PARTIE EST COMMUNE À TOUS LES LOTS DU DOSSIER (Lot 2 — … ; Lot 3 — …) : elle figure telle quelle dans le
  dossier de chacun ; n'y parle d'aucun lot en particulier. » ; « Autres parties du dossier » : celles du dossier
  du lot (avec ses numéros), ou les intitulés de toutes (une fois chacun) pour une partie commune. L'intitulé d'un
  lot vient du règlement (public) ; rien de l'entreprise n'est ajouté.
- **Contrôle des faits** : dans un dossier à PLUSIEURS lots seulement, le numéro d'un de SES lots (« lot 2 », « lot n°
  3 », « lots 2 et 3 ») n'est pas un fait à relire (`faits_a_relire._numeros_de_lots`, `lots` passé par
  `Contexte.lots` / `ContextePartenaire.lots` à `faits_sources.controler`) : après « lot » au singulier, le seul numéro
  qui suit ; après « lots », la liste, arrêtée au premier numéro suivi d'autre chose qu'une ponctuation ou un mot de
  liaison. « Pour le lot 2, 8 semaines », « Lot 3 - 2 chefs », « Le lot 3 a 5 semaines » : 8 semaines, 2 chefs et 5
  semaines restent à relire. Marché simple (ou réponse à un seul lot) : rien ne change, « le lot 12 du collège » garde
  son « 12 » à relire. Tout autre nombre reste contrôlé comme avant.

### J.10 L'entretien chantier

La question qui concerne une partie propre à un lot vaut aussi pour la même partie des autres lots (le chantier est
le même) : sa réponse est un fait autorisé [R#] de chacune, et sa question passée y laisse son « [À compléter] »
(`entretien_chantier.pour_parties`). Rien d'autre ne change.

### J.11 Groupement

- **« Qui écrit quoi »** (pré-remplissage sans IA, `atelier_groupement.proposition`) : la partie propre à un lot est
  proposée au membre qui a déclaré CE lot dans sa part (« Lot 3 », « lots 2 et 3 », « lot n° 3 », ou les mots de
  l'intitulé du lot, même début de mot), lui seul — message : « Proposé d'après le lot de X (« Lot 3 : … ») : cette
  partie est celle du lot 3 (« … ») ». Personne : « Proposé au chef de file : aucun partenaire n'a déclaré le lot 2
  (« … »). » ; plusieurs : chef de file, « choisissez qui rédige ». Une partie commune suit la règle d'avant. Le chef
  de file reste maître du choix.
- **Ce que voit un membre** : chaque partie du dossier assemblé et de « Mes parties » porte son lot (`lot`,
  `lot_libelle`, `commune`) — public : le règlement le nomme ; la note « ce que l'acheteur note » d'une partie d'un
  lot cite la phrase du règlement pour CE lot. Rien d'autre : le cloisonnement de la vague 4 est intact (brouillons,
  sources, extraits, tâches, documents déposés jamais chez un autre).

### J.12 Démo (`app/services/demo_lots.py`)

Un marché FICTIF réparti en trois lots, « Restructuration — École maternelle Les Hirondelles (3 lots) », Ville de
Trémorvan (fictive), auquel Bâtiment de l'Ouest répond sur les lots 2 (couverture et zinguerie) et 3 (étanchéité des
toitures-terrasses) : dossier (règlement, deux CCTP de lot, décomposition du prix) mis en PDF puis lu EN ENTIER ;
analyse par `finalize_analysis` ; lots repérés et plan construits par le vrai moteur, sans IA ; une partie commune
(gestion environnementale, validée) et, pour chaque lot, ses parties (lot 2 : validées ; lot 3 : un brouillon et une
partie à écrire) ; textes fictifs, faits contrôlés sans IA (aucun fait à relire) ; entretien chantier préparé. La démo
montre : un fichier par lot nommé comme le règlement l'exige (« Lot 2 - Mémoire technique - Bâtiment de l'Ouest »), le
lot 2 « Prêt à exporter », le lot 3 « Bloqué » (une partie sans texte), la limite de 6 pages contrôlée lot par lot, la
partie commune dans les deux dossiers. Seed rejouable (clés de stockage liées au contenu), isolé dans SA transaction
(un échec laisse les six autres marchés). Le visiteur ne change rien (lots, portée, export, dérogation : 403
« lecture guidée », sans coût). La vitrine compte désormais 7 marchés.

### J.13 Marché à un seul lot : rien ne change

Garanties testées (`tests/test_redaction_v6_lots.py`) : plan identique (aucune étiquette, aucun `lot`), `plan_meta`
sans `lots`, compteur et export d'avant (« Mémoire justificatif.docx »), un lot donné à l'export refusé (422
`lot_inconnu`), empreinte d'état calculée exactement comme avant (une dérogation déjà enregistrée en production reste
valable), réponse à UN lot d'un marché alloti = un seul dossier. Les champs nouveaux de l'état (`lots`, `lot_libelle`,
`commune`, `portee_modifiable`, `lot` d'une limite et d'un blocage) sont vides ou faux.

### J.14 Limites connues, choix à dire à Eliot

- **Repérage des lots** : les lots écrits dans un TABLEAU du règlement sans « Lot n » en tête de ligne, ou seulement
  dans un document scanné non reconnu, ne sont pas repérés : l'utilisateur les ajoute (« indiqué par vous »).
- **Grille par lot en tableau** (colonnes « Lot 1 | Lot 2 ») : jamais lue ligne à ligne ; critères repris sans poids,
  et on le dit (choix : aucun poids deviné plutôt qu'un poids d'un autre lot).
- **Liste des exigences** : elle reste celle du dossier entier (« 11 exigences traitées sur 12 » sur l'ensemble des
  parties), pas lot par lot.
- **Règle commune / propre** : une règle de mots sur l'intitulé, dite dans la bulle ; l'utilisateur change chaque
  partie. « Références » est propre à chaque lot (références de travaux similaires au lot).
- **Plan du cadre** : si un lot a un cadre de réponse imposé et un autre non, le dossier n'est pas « plan du cadre »
  (ordre libre) ; chaque lot garde les numéros de son cadre.

### J.15 Vérifications

- tests : `tests/test_redaction_v6_lots.py` (repérage, grille par lot, règle, nommage, deux lots, partie commune
  modifiée, exports séparés, limites et dérogation par lot, portée, changer les lots, ajouter une partie, dossier
  commun, consigne de l'IA simulée, groupement, marché à un seul lot inchangé, empreinte inchangée),
  `tests/test_demo_plusieurs_lots.py` ; tests de la démo mis à jour (7 marchés, 2 dossiers de présentation) ;
- suite complète verte ; SRI à jour (`scripts/sri_update.py --check`) ; `node --check` ; gabarits Vue compilés ;
- écrans vus dans le navigateur (1 024 px et 375 px, aucun débordement horizontal, aucune erreur de console) ;
- aucune migration ; sur un vrai Postgres, depuis l'état exact de la production (`a29173a`, tête
  `z1entretienchantier`) : données créées par le code de production, puis le code nouveau (plan à plusieurs lots,
  portée, export par lot, dérogation par lot, dossier commun), puis le code de production relancé sur les mêmes
  données ; les tests rejoués sur Postgres, échecs comparés à ceux du code de production à conditions égales.

---

## Ensemble — F, H et J réunis

Les trois chantiers ont été construits séparément sur `a29173a` (F : `5bd4f7e`, H : `3b79c56`, J : `21e40cb`), puis
réunis : avance rapide sur la production, F (avance rapide), H puis J fusionnés bloc par bloc (aucun fichier pris d'un
seul côté ; chaque ligne ajoutée par un côté retrouvée, sauf les lignes réécrites pour réunir les deux). Une seule tête
Alembic : `a2carnetnotes` (F, après `z1entretienchantier`) ; H et J n'ont pas de migration.

Source de vérité : `app/services/atelier_preparation.py` (`apercu(…, lot)`, `page`, `avertissements(…, lot)`),
`app/routers/atelier.py` (`GET …/preparation?lot=`, `ExportIn` : `lot` ET `page_preparation`), `app/services/atelier.py`
(`exporter(…, lot, page_preparation)`), `app/services/carnet_notes.py` (section « Plusieurs lots »), `app/routers/carnet.py`
(`lire`, `LigneIn.lot`), `app/static/carnet-notes.js` (`cnTetes`, `cnPayload`, `cnControle`), `app/static/app.js`
(`atlPrepLoad`, `atlPrepLot`, `atlExport`), `app/static/app.html`, `app/static/styles.css` (`.cn-lot-h`,
`.atl-prep .atl-lot-f`) ; tests : `tests/test_redaction_v6_ensemble.py`.

### E.1 Le parcours vérifié de bout en bout (sans IA ni réseau)

Marché réparti en 3 lots, réponse aux lots 2 et 3 → une partie commune, deux parties propres à chaque lot → export du
lot 2 en Word AVEC la page, du lot 3 en PDF avec la page, du lot 2 sans la page → marché passé à « Perdu » →
« Demandez vos notes » (procédure adaptée lue dans le règlement, article R2181-2, les deux lots cités, rien d'envoyé) →
courrier de l'acheteur collé, lu sans IA lot par lot → notes validées (un relevé par lot) → « Où vous perdez des
points » (3 marchés, moyenne) → nouveau dossier chez le même acheteur : « La dernière fois, l'acheteur a écrit », avec
le lot. Plus : la lecture avec l'IA d'un courrier à plusieurs lots, un groupement (partenaire du lot 3), un marché
simple inchangé, la démo (`tests/test_redaction_v6_ensemble.py`).

### E.2 H × J : la page du fichier de CHAQUE lot

Un dossier à plusieurs lots produit un fichier par lot : la page « Comment ce dossier a été préparé » jointe à un
fichier est celle de CE fichier.
- Elle ne parle que des parties du lot (les communes et les siennes), numérotées comme dans le fichier ; sa mention IA
  est celle du fichier du lot (le même drapeau `ia`, calculé sur ses seules parties).
- Son résumé commence par « Ce fichier répond au lot 2 — Couverture et zinguerie. », suivi de « Les parties communes
  à plusieurs lots y sont reprises telles quelles. » s'il en contient.
- Les avertissements de l'écran lisent les limites de CE lot (« Le règlement limite le dossier à 3 pages… »).
- `GET …/preparation?lot=2` ; sans lot sur un dossier à plusieurs lots : 422 `lot_requis` ; un lot hors du dossier, ou
  un lot sur un dossier à un seul lot : 422 `lot_inconnu` (mêmes règles que l'export). `page.lot = {numero, libelle}`
  (null pour un dossier à un seul lot), `lot` à la racine.
- Écran : dans « Voir la page », « Page du fichier : Lot 2 · Lot 3 » (le premier lot par défaut ; deux lots choisis vite
  l'un après l'autre : seule la réponse du dernier choix est montrée, `atl.prep.seq`) ; la bulle de la case
  ajoute « Un fichier par lot : la case vaut pour chaque fichier exporté, et chaque page ne parle que des parties de
  son lot. » La case vaut pour l'export de chaque lot (`page_preparation` envoyé avec `lot`).
- Journal et dernier export : `dernier_export["lots"][n].page_preparation`, `meta.lot` et `meta.page_preparation`.

### E.3 F × J : un relevé de notes par lot

L'acheteur note chaque lot à part (chaque lot est un marché). Pour un marché dont le dossier de présentation de
l'organisation répond à plusieurs lots (`atelier_lots.actif`) :
- **Formulaire** : les critères et sous-critères sont répétés pour chaque lot, avec la grille de CE lot quand le
  règlement en écrit une (J.4 : celle que le dossier garde, `plan_meta.lots.grilles`, lue par `_lignes_du_lot` —
  critères du plan de ce lot et leurs poids pour lui), sinon celle du marché ; clés propres au lot (`L2-c1`, `L2-c1.1`), titres « Lot 2 — … »
  à l'écran ; message « Vous avez répondu à plusieurs lots : l'acheteur note chaque lot à part, saisissez les notes lot
  par lot. ». Un critère ajouté choisit son lot (422 `lot_requis` sinon ; une ligne vide est ignorée AVANT, comme à
  l'écran) ; le lot d'un critère connu est le sien,
  jamais celui envoyé par l'écran. Au plus 40 lignes par lot.
- **Courrier « Demandez vos notes »** : « … au titre des lots auxquels nous avons répondu : lot 2 — … ; lot 3 — … »
  et « … pour chacun de ces lots et pour chaque critère et sous-critère … » ; message à l'écran : « Vous avez répondu à
  plusieurs lots : le courrier les cite tous. Retirez celui que vous avez remporté, le cas échéant. » Aucun autre
  article (la liste de F.2 est inchangée).
- **Lecture sans IA** : le courrier est découpé par les lignes de TITRE qui citent UN SEUL des lots du dossier : une
  ligne qui commence par le lot (« Lot 2 - Couverture », « 2. LOT N° 03 – Étanchéité »), une annonce (« Pour le lot 3
  — Étanchéité », « Concernant le lot 2 : ») ou une ligne qui annonce la suite (« … : ») ; l'objet du courrier, s'il
  ne cite qu'un lot, vaut jusqu'au premier titre ; une mention dans une phrase (« Votre offre pour le lot 2 fait
  l'objet d'un courrier séparé. ») ne change rien, ni une ligne qui cite plusieurs lots ; sans titre, le courrier parle
  du lot de son objet, sinon du seul lot qu'il cite. Une note n'est rapprochée que des critères de
  SON lot. Aucun lot lisible : aucune proposition, message « Le courrier ne dit pas à quel lot se rapporte chaque note
  (aucune ligne ne cite un seul de vos lots) : saisissez les notes lot par lot. »
- **Lecture avec l'IA** : la liste des critères porte le lot (« [L2-c1.1] (Lot 2 — …) — Méthodologie… ») et la
  consigne ajoute « Ne prends la note d'un critère que dans la partie du courrier qui parle de CE lot » (consigne d'un
  marché à un seul lot inchangée). Contrôle sans IA : l'extrait et le commentaire d'un critère de lot doivent être dans
  la partie du courrier de CE lot, sinon écartés. Courrier sans lot lisible : aucun appel, rien de décompté.
- **Validation** : « lue dans le courrier » n'est gardé que si la ligne citée est dans la partie de SON lot ; les
  lignes sont rangées lot par lot ; chaque ligne garde `lot` et `lot_libelle`.
- **Notes affichées** : titres par lot, « Note d'ensemble, lot 2 — … » pour chaque lot (`notes.totaux`, seulement
  quand chaque critère de CE lot a sa note, F.6), jamais une somme de deux lots (`notes.total` vaut null) ; le constat dit le lot (« … « Méthodologie d'exécution » (lot 2 — …)
  … »).
- **« Où vous perdez des points »** : le marché alloti compte UNE fois (ses lots réunis, par famille) ; la règle des 3
  marchés est inchangée.
- **« La dernière fois, l'acheteur a écrit »** : le lot du commentaire est dit (« Marché … (Lot 2 — …) »).
- **Groupement** : l'auteur d'un critère de lot est cherché dans le dossier de CE lot (ses parties communes et les
  siennes), jamais dans la partie sœur d'un autre lot ; le partenaire du lot 3 voit toutes les notes communes, SES
  parties du lot 3 signalées, la note d'ensemble de chaque lot ; jamais le courrier ni ses extraits (cloisonnement V4
  inchangé).
- **« Ajouter ce dossier à mon savoir-faire »** : le titre d'une partie propre à un lot le dit (« (lot 3) »).
- **Marché simple** (un seul lot, ou une réponse à un seul lot) : rien ne change (mêmes clés `c1`, même message, même
  courrier, même consigne de l'IA, `notes.total` comme avant, `notes.totaux` vide).

### E.4 F : la procédure, aussi dans l'ancienne lecture du dossier

Un marché lu avant la lecture intégrale n'a pas de règlement rangé : la procédure est alors cherchée dans le règlement
du texte de l'ancienne lecture (`dce_excerpt`, découpé en pièces comme pour le repérage des lots), phrase citée telle
qu'écrite, sinon dans l'analyse (inchangé). Jamais une relecture du fichier, jamais d'IA.

### E.5 Démo

Contenu inchangé (aucune donnée ajoutée : les chiffres du pitch, 84 % et 88 %, restent ceux de F.11 ; la vitrine garde
ses 7 marchés). Ce que la réunion apporte : sur le marché à plusieurs lots de Trémorvan, « Voir la page » montre la page
du fichier de chaque lot (lecture seule, sans IA) ; l'export reste refusé, rien n'est écrit (test). Aucune route
nouvelle : l'inventaire de `tests/test_demo_sans_cout.py` est inchangé.

### E.6 Choix à dire à Eliot

1. **Un relevé de notes par lot** (et non un seul par marché) : l'acheteur note chaque lot à part ; le marché alloti
   compte une fois dans « Où vous perdez des points ». Autre choix possible : compter chaque lot comme un marché (la
   moyenne arriverait plus vite, mais un marché à 3 lots pèserait 3 fois).
2. **Le courrier cite tous les lots auxquels l'entreprise a répondu**, même si elle en a gagné un : l'étape du marché
   est une seule (« Perdu ») ; le texte le dit et reste modifiable.
3. **Un courrier sans lot lisible** ne propose rien (ni sans IA ni avec l'IA) plutôt que de deviner le lot.
4. **La page « Comment ce dossier a été préparé » est par fichier** : un lot sans IA a une page qui le dit, même si un
   autre lot a été préparé avec l'IA (la mention du fichier suit la même règle).

### E.7 Vérifications

- Lignes perdues à la fusion : pour chaque branche, chaque ligne ajoutée depuis `a29173a` est retrouvée dans le code
  réuni, sauf les lignes réécrites pour réunir les deux côtés (signature et corps de `exporter`, `ExportIn`, appel de
  l'export, `_atlInit`, corps de l'export à l'écran, en-tête de ce contrat).
- Tests : `tests/test_redaction_v6_ensemble.py` (7 tests : parcours complet, IA lot par lot, groupement du lot 3, marché
  simple inchangé, fonctions pures du découpage, écrans sous Node, démo) ; suite complète : 1 919 tests, tous verts
  (SQLite, `TZ=UTC`, IA simulée, aucun réseau).
- SRI à jour (`scripts/sri_update.py --check`), `node --check` (app.js, carnet-notes.js, redaction-partenaire.js).
- Navigateur (base locale de prévisualisation, compte de test, marché alloti perdu) : relevé par lot, titres « Lot 2 —
  … », « Critères ajoutés » avec le choix du lot, notes d'ensemble par lot, constat avec le lot, courrier qui cite les
  lots ; atelier : « Page du fichier : Lot 2 · Lot 3 » ; à 1 024 px et à 375 px, aucun débordement horizontal ; démo :
  « Où vous perdez des points » inchangé (84 %, 88 %, environnement sans moyenne), page de chaque lot du marché de
  Trémorvan, aucune erreur de console.
- Postgres 16 depuis l'état exact de la production (`a29173a` extrait par `git archive`, base montée par son propre
  code jusqu'à `z1entretienchantier`, données créées par lui ; script `scratchpad/pgtest/run_v6_ensemble_depuis_prod.py`,
  fabriqué depuis celui de F) : 32 contrôles verts — une seule révision appliquée (`a2carnetnotes`), aucune donnée
  perdue, seconde montée et rejeu sans effet ; le code réuni sur la base montée (carnet de F, puis un marché alloti :
  lots 2 et 3, page du lot 3, export du lot 2 avec la page, 422 sans lot, marché perdu, courrier qui cite les lots,
  10 notes lues sans IA lot par lot et validées, notes d'ensemble par lot, tableau) ; le code de production relancé lit
  le marché alloti écrit par le code réuni (200) ; schéma identique à une base neuve ; retour arrière et remontée.
  Tests rejoués sur la base montée : 445 verts et les mêmes 63 échecs propres à SQLite que le code de production sur la
  même liste dans le même ordre (aucun dans un fichier de la vague 6).

---

## Contre-relecture (19/10/2026)

Quatre relectures du code réuni (`901828c`) : exactitude juridique, cloisonnement des données, lots et parcours, écrans.
Production toujours `a29173a` (aucune fusion nécessaire). Chaque remarque a été reproduite (scripts de la revue et tests
par les routes), corrigée, et couverte par un test qui échouait sur `901828c` : `tests/test_redaction_v6_contre_relecture.py`
(37 tests, tous en échec sur `901828c`, tous verts ici). Aucune remarque rejetée ; les doublons sont traités ensemble.

| Remarques | Gravité | Ce qui a changé | Sections |
|---|---|---|---|
| Le numéro d'un lot prenait aussi le nombre qui suit (« lot 2, 8 semaines », « Lot 3 - 2 chefs », « lot 3 a 5 semaines ») ; et toute mention « lot 12 » échappait au contrôle, marché simple compris (trois relectures) | bloquant, majeur | `_LOT_REF` remplacé par `_numeros_de_lots` : numéros des lots de CE dossier seulement (passés par `lots`), un seul numéro après « lot », une liste après « lots » arrêtée au premier nombre suivi d'autre chose qu'une ponctuation ou un mot de liaison ; marché simple : comportement de la production | J.9 |
| Un morceau d'un autre nombre passait pour « retrouvé tel quel » (2 dans 12, 6,5 dans 36,5, 10 dans 100) | majeur | `_dans_ligne` : extrait dans UNE ligne du courrier, sans couper un nombre à ses bords, à la lecture avec l'IA et à la validation | F.1 |
| Note d'ensemble partielle présentée comme celle de l'offre | majeur | somme sur les critères du formulaire, sous-critères comptés pour leur critère ; sinon rien et « k critères notés sur n » ; même règle lot par lot et chez le partenaire | F.6, E.3 |
| « l'offre du groupement » d'après le plan proposé automatiquement ; groupement à deux non reconnu | majeur | invitations actives, ou groupement retenu (« auto » faux, un partenaire au moins) | F.5 |
| « perdu le plus de points » pour le plus faible pourcentage (faux dans la démo) | majeur | constat dit tel qu'il est calculé, au marché et au tableau de bord | F.6, F.7 |
| Courrier : une mention de lot dans une phrase changeait de lot | mineur | seules les lignes de titre (ou l'objet, jusqu'au premier titre) changent de lot | E.3 |
| Procédure formalisée : condition de R2181-4 et exception de R2182-2 absentes | mineur | condition dans le message et le courrier ; « marché subséquent » repéré sans IA ; R2182-2 relu et ajouté au tableau | F.2 |
| Courrier nommant des critères lus par l'analyse | mineur | seuls ceux de « Comment vous serez noté » sont nommés | F.5 |
| Courriel de rappel envoyé à un membre retiré | majeur | destinataire encore membre de l'organisation, sinon le titulaire actuel du marché | F.5 |
| Formulaire d'un marché simple : critère ajouté avec son titre en double (démo) (deux relectures) | majeur | `cnLigneTete` : le champ « Critère » OU le titre, puis le choix du lot à part | F.13 |
| Grille par lot : poids écrit avant la mention du lot donné au lot suivant | majeur | zone lue « illisible » : critères sans poids, jamais le poids d'un autre lot | J.4 |
| Relevé de notes par lot : la grille du marché au lieu de celle du lot | majeur | `_lignes_du_lot` lit la grille gardée par le dossier ; `grille_out` garde l'identifiant des sous-critères | E.3 |
| Partie ajoutée, déplacée ou remise au milieu des sous-critères dans le dossier d'un lot | majeur | `_coupes` / `_place_sans_couper` dans le dossier de chaque lot | J.5 |
| Limites : une phrase qui cite deux lots donnait les deux valeurs à chaque lot | majeur | chaque valeur au lot cité à côté d'elle, sinon « selon le lot » (non contrôlée) ; une liste de lots s'arrête à un nombre suivi de ce qu'il mesure | J.4 |
| « Préparer mes documents » supprimait le fichier d'un lot bloqué | majeur | fichiers du lot non joint gardés (`garder`) | J.8 |
| Partie rendue commune : ordre du règlement changé dans les autres lots | mineur | la partie commune prend la place qu'avait celle de chaque lot ; lots en désaccord : 409 `portee_ordre` | J.5 |
| Nom du fichier : double extension ; « [raison sociale] » non rempli | mineur | extension retirée du modèle (et dite) ; « [raison sociale] » reconnu | J.8 |
| « Page du fichier » : réponse en retard d'un autre lot | mineur | garde de séquence (`atl.prep.seq`) | E.2 |
| `lot_requis` sur une ligne vide (écran et serveur en désaccord) | mineur | la ligne vide est ignorée avant d'exiger son lot | E.3 |

### Choix à dire à Eliot

1. **Poids écrit avant la mention du lot** (« 60 % pour le lot 2, 40 % pour le lot 3 ») : lu comme un tableau, sans
   poids (« vérifiez le poids de chaque critère pour ce lot »), plutôt qu'un rattachement au critère le plus proche
   (même choix qu'en J.14 : aucun poids deviné).
2. **Note d'ensemble** : rien plutôt qu'une somme partielle ; un critère de l'analyse qui n'existe pas dans le courrier
   empêche donc la note d'ensemble (le message dit combien de critères sont notés).
3. **Rappel par courriel** : un membre retiré ne reçoit rien ; le titulaire actuel du marché (le propriétaire, qui a
   repris ses marchés) le reçoit s'il a des alertes.
4. **Juridique** : le message de délai cite maintenant R2182-2 (relu sur Légifrance) ; texte toujours à faire relire
   par un conseil avec les pages juridiques (non touchées).

### Vérifications

- Tests : `tests/test_redaction_v6_contre_relecture.py` (37 tests : les 37 échouent sur `901828c`, extrait par `git
  archive`) ; tests existants mis à jour (R2182-2 permis, groupement retenu, garde de séquence, numéros de lots passés
  au contrôle) ; suite complète : 1 956 tests, tous verts (SQLite, `TZ=UTC`, IA simulée, aucun réseau).
- SRI à jour (`scripts/sri_update.py --check`), `node --check` (app.js, carnet-notes.js, redaction-partenaire.js).
- Navigateur (démo locale, 375 px, aucun débordement, aucune erreur de console) : Limauzac — « Modifier les notes »
  sans titre en double, note d'ensemble 83,8 / 100 (84 %), constat « note la plus faible, en pourcentage », courrier
  formalisé avec la condition de R2181-4 et le message R2182-2, sans liste de critères de l'analyse ; tableau de bord :
  « vos notes sont les plus faibles » (84 %) ; Trémorvan : page du fichier du lot 3, aucun fait à relire, lots
  inchangés.
- Postgres 16 depuis l'état exact de la production (`a29173a` extrait par `git archive`, tête `z1entretienchantier`,
  données créées par son code ; script `scratchpad/pgtest/run_v6_contre_relecture_depuis_prod.py`, copie de celui de
  l'Ensemble) : 32 contrôles verts (une seule révision, aucune donnée perdue, rejeu sans effet, parcours F + H + J sur
  la base montée, code de production relancé avant et après le retour arrière, schéma identique à une base neuve) ;
  tests rejoués sur la base montée : 482 verts (dont les 37 de la contre-relecture) et les mêmes 63 échecs propres à
  SQLite que le code de production, sur la même liste dans le même ordre (aucun dans un fichier de la vague 6 ni de la
  démo).
