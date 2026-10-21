# Moteur de recherche, lot 1 « Dire juste » : partie serveur

Contrat du lot 1 du moteur de recherche des marchés. Note de décisions : « Projets à venir et moteur de recherche :
les décisions » (21/10/2026), section « La première étape que je lancerais : le lot 1 « Dire juste » », points 1 à 9
(partie serveur) ; les points 10 à 13 (écran) viennent après la vague 2b. Étude de référence : « Le moteur de recherche
d'appels d'offres : étude définitive » (12/10/2026), § 2, § 4.4, § 6.2, § 6.6, § 7, § 8, § 9. Base :
`feat/produit-acheteur-collectivites` = `0afc1ed` (production du 20/10/2026, Postgres).

Décisions d'Eliot du 21/10/2026 : lancer le lot 1 côté serveur (décisions 1 et 2) ; ne plus écarter un marché d'une
alerte à cause de sa note d'avant dossier (décision 11) ; garder le repli payant de l'onglet « À venir », annoncer le
crédit avant le clic (écran, plus tard) et noter chaque repli dans le journal dès maintenant (décision 12) ; la veille
des projets à venir plus tard (seules ses anciennes adresses sont fermées, point 7).

Règles communes à tous les chantiers du lot : aucune date ni aucun fait non lu dans la source n'est inventé ; une forme
jamais observée est traitée prudemment et marquée « non vérifié » ici ; aucun changement de prix ni de quota ; aucune
IA ajoutée ; le robot de Mégalis inchangé (il se nomme, une requête par seconde au plus, jamais de contournement d'un
refus) ; un seul processus ; cloisonnement de la co-traitance intact ; aucun fichier de l'écran touché.

Le lot est mené en chantiers parallèles ; chacun a sa section. Chaque point dit : **avant**, **après**, **preuve**,
**ce qui change pour le client**.

---

## Sources

Points 1 à 4 de la note. Fichiers : `app/sourcing/dates_fr.py` (nouveau), `app/sourcing/sources/atexo.py`,
`app/sourcing/sources/boamp.py`, `app/sourcing/search.py`, `app/sourcing/scoring.py`, `app/sourcing/base.py`
(comparaison des départements, liens des rectificatifs assainis), `app/sourcing/schemas.py` (4 champs de la fiche).
Non touchés, comme demandé : `app/services/decp.py`, `app/services/alerts.py`, `app/routers/sourcing.py`,
`app/routers/amont.py`, et aucun fichier de `app/static`. Aucun changement de base de données.

Tests : `tests/test_moteur_lot1_sources.py` (17 tests, sans réseau). Les 17 échouent sur `0afc1ed`, chacun sur le
défaut qu'il couvre (dates vides, avis annulé affiché, version européenne en double, Guadeloupe gardée pour « 974 »,
faux code « 45 » compté comme métier…) ou sur l'absence de la fonction nouvelle (`lire_rectificatif`, champs de la
fiche) ; le seul test de documentation échoue faute de ce fichier. Un test existant corrigé (§ S.3).

**Jeux d'essai réels**, lus en GET le 21/10/2026 avec l'en-tête du robot (`AdjugoBot/1.0 (+https://adjugo.pro ;
contact@adjugo.pro)`), puis figés dans `tests/fixtures` :
- `megalis_resultats_2026-10-21.html` : les 10 blocs de résultat de la recherche « voirie » sur Mégalis Bretagne,
  tels quels. Deux pages lues en tout (« voirie », « accord-cadre »), à plusieurs minutes d'écart.
- `boamp_suites_2026-10-21.json` : 12 avis (initiaux, rectificatifs et annulations au format européen) et 18 suites
  (rectificatifs et annulations aux formats national et simplifié) de l'API BOAMP (OpenDataSoft). Le corps des
  suites est réduit au bloc « rectificatif » ou « annulation » : les contacts de l'acheteur (`organisme` : nom,
  téléphone, adresse électronique) sont retirés. Aucune donnée personnelle dans les deux fichiers (vérifié).
- Requêtes faites en tout : 16 au BOAMP (schéma, 4 décomptes, 7 lectures d'avis, 3 pour une recherche réelle de
  bout en bout, 1 vérification de texte), 2 à Mégalis, 0 à la DECP. Le script qui construit les jeux d'essai est
  dans le bloc-notes de la session (`scratchpad/lot1sources/faire_fixtures.py`), pas dans le dépôt.

### S.1 Dates Mégalis : une table explicite des mois

**Avant.** `atexo.py` coupait le mois à ses 4 premières lettres et cherchait le résultat dans une table qui ne
connaissait que « janv », « févr », « mars », « avri », « mai », « juin », « juil », « août », « sept », « octo »,
« nove », « déce ». « Oct. », « Nov. », « Déc. », « Fév. » et « Avr. » ne donnaient rien : sur la page réelle du
21/10/2026, **les 10 dates limites étaient vides** (« limite non précisée » à l'écran). La coupe acceptait aussi
n'importe quel mot commençant comme un mois (« 12 Marseille 2026 » donnait le 12 mars 2026). Et la fusion floue
avec le même avis au BOAMP (objet, acheteur, date limite) échouait faute de date.

**Après.**
- `app/sourcing/dates_fr.py` : une table explicite de chaque forme écrite, en minuscules, sans le point final
  (les majuscules et le point sont acceptés en entrée, l'accent décomposé est recomposé) :

  | Mois | Formes | Observée le 21/10/2026 sur Mégalis |
  |---|---|---|
  | janvier | janvier, janv | non vérifié |
  | février | février, fevrier, févr, fevr, fév, fev | non vérifié (« Fév. » vue sur PLACE le 12/10 selon l'étude, non revue) |
  | mars | mars | non vérifié |
  | avril | avril, avr | non vérifié |
  | mai | mai | non vérifié |
  | juin | juin | non vérifié |
  | juillet | juillet, juil, juill | non vérifié |
  | août | août, aout | non vérifié |
  | septembre | septembre, sept | non vérifié |
  | octobre | octobre, oct | **« Oct. » observée** |
  | novembre | novembre, nov | **« Nov. » observée** |
  | décembre | décembre, decembre, déc, dec | **« Déc. » observée** |

  « Non vérifié » : la forme n'a pas été vue sur une page réelle aujourd'hui (les consultations ouvertes ne
  vont pas au-delà de décembre) ; elle est construite d'après la note (janv, fév/févr, mars, avr/avril, mai, juin,
  juil, août, sept, oct, nov, déc), plus les noms complets et les formes sans accent que l'ancienne table acceptait
  déjà, et « juill. » (abréviation courante). Une forme absente de la table ne donne **aucune date** ; jamais de
  coupe, donc jamais « juin » pris pour « juillet ». Une date impossible (31 novembre) n'est jamais rendue.
- `atexo._parse_page` lit d'abord la **case « clôture »** du résultat (`.cloture-line` : jour, mois, année dans trois
  cases), puis, si elle manque, la dernière date « jour mois année » du bloc comme avant. Si la case est là mais
  illisible (mois inconnu, case incomplète, plusieurs cases), aucune date : on ne se rabat jamais sur une date plus
  haut dans le bloc, qui est la **date de mise en ligne** (« 14 Oct. 2026 »), lisible elle aussi désormais.

**Preuve.** `test_megalis_page_reelle_toutes_les_dates_limites_lues` (page réelle : 10 dates sur 10, 242387 au
07/12/2026, 242491 au 23/11/2026, jamais la date de mise en ligne), `test_megalis_recherche_complete_sur_la_page_reelle`
(la source entière, et la fusion avec un avis BOAMP de même objet, acheteur et date — avis BOAMP construit),
`test_mois_table_explicite_jamais_une_coupe` (chaque forme de la table ; « Marseille », « Juinet », « Octet »,
« Septante », « Novice », « Decathlon », « Avrillé » ne sont pas des mois), `test_megalis_case_cloture_prioritaire_…`
(bloc construit sur le modèle réel).

**Ce qui change pour le client.**
- Les cartes Mégalis montrent leur date limite au lieu de « limite non précisée ».
- Une consultation publiée à la fois sur Mégalis et au BOAMP ne fait plus qu'une carte (avec « vu aussi sur »).
- L'ordre des résultats bouge un peu : le critère « délai de réponse » d'une carte Mégalis compte maintenant
  (il était mis de côté, faute de date) ; le nombre « adéquation N/100 » d'une carte Mégalis peut changer.
- Une consultation Mégalis dont la date lue est passée est retirée comme toutes les autres (en pratique, la page de
  recherche de Mégalis ne liste que les consultations en cours).

### S.2 Rectificatifs et annulations du BOAMP, rattachés à leur avis

**Avant.** Le BOAMP n'était interrogé que pour les avis dont la date limite n'est pas passée, et rien ne lisait
les suites d'un avis. Mesures du 21/10/2026 sur octobre (décomptes de l'API) : 319 rectificatifs aux formats national
et simplifié, 355 rectificatifs au format européen, 14 annulations. Conséquences, toutes reproduites sur le jeu réel :
- un rectificatif national ou simplifié n'a pas de date limite structurée : il n'était jamais vu ; l'avis gardait
  l'**ancienne date** (26-94570 au 29/10 alors que 26-102338 l'a « modifiée au 03/11/2026 »), puis disparaissait
  une fois cette date passée alors qu'il est toujours ouvert (26-90336 : limite du 16/10, repoussée au 06/11 par
  26-96286, le cas de l'étude) ;
- au format européen, le rectificatif est une version complète de l'avis, avec sa date : il **s'ajoutait** à l'avis
  initial (26-93829 au 02/11 **et** 26-101544 au 18/11, deux cartes pour une procédure) ;
- une annulation n'était jamais lue : l'avis annulé restait affiché (26-95755, annulé par 26-95892 ; 26-91526,
  déclaré sans suite par 26-101778) ; l'annulation au format européen, publiée avec une date limite, s'affichait
  même comme un marché ouvert (26-101778).

**Après** (`app/sourcing/sources/boamp.py`). **Une procédure, une fiche.**
- *Les avis.* La requête principale ne change pas, sauf 4 champs de plus (`annonce_lie`, `nature`, `etat`,
  `contractfolderid`) : de quoi reconnaître dans les résultats mêmes un rectificatif ou une annulation au format
  européen.
- *Une requête de plus* (corps `donnees` demandé pour elle seule) : les rectificatifs et annulations des avis
  affichés, par `annonce_lie` ; et, en première page seulement, les rectificatifs nationaux et simplifiés publiés
  depuis 60 jours qui répondent à la même recherche (mêmes mots, mêmes départements ; pas le type de marché, que ces
  rectificatifs ne portent pas), pour retrouver un avis dont seule l'ancienne date est passée. 100 lignes au plus.
- *Une requête encore*, seulement s'il y a lieu : l'avis initial d'un tel rectificatif, relu par sa référence, avec
  les annulations qui le visent. Il n'est repris que si la nouvelle date est **lue** et pas encore passée.
- *Rattacher.* Une suite vise son avis par `annonce_lie` (un rectificatif de rectificatif remonte jusqu'à l'avis) ;
  à défaut, au format européen, par le dossier commun (`contractfolderid`). Un rectificatif d'avis d'attribution
  (ou d'une autre nature) n'est jamais appliqué à un avis ouvert.
- *Annuler.* Un avis « ANNULATION » (formats national, simplifié, divers) ou un avis européen à l'état
  « ANNULATION » retire l'avis visé, et l'annulation elle-même n'est jamais affichée.
- *Rectifier.* Les rectificatifs sont appliqués du plus ancien au plus récent ; le dernier qui parle de la date limite
  la fixe. La fiche garde la **référence et le lien de l'avis initial** (mêmes alertes, même dossier analysé, même
  page suivante), reçoit la liste des rectificatifs avec leur propre lien, la date de parution du dernier, et
  l'ancienne date à part quand elle a changé. Un rectificatif européen renvoyé sans son avis initial prend la
  référence et le lien de cet avis (une seule fiche par avis initial).
- *Lire la nouvelle date* (`lire_rectificatif`), forme par forme :

  | Forme | Lecture | Observée le 21/10/2026 |
  |---|---|---|
  | Européen : version complète de l'avis | sa date limite structurée (`datelimitereponse`) | oui (26-101544, 26-101475) |
  | Simplifié, structuré `{"rubDelais": "ReceptionOffres", "lireDate": …}` | `lireDate` | oui (26-96286, 26-102497, 26-102146) |
  | National, « Rubrique : Date et heure limites de réception des plis, Au lieu de 21/10/2026 à 12h00, lire 05/11/2026 à 12h00 » | la date qui suit « lire » | oui (26-102300, 26-102361, 26-102403, 26-102230) |
  | Phrase libre qui parle de la date limite de réponse et ne cite qu'**une** date, avec son année (« … modifiée au 03/11/2026 », « … reportée au jeudi 29 octobre 2026 », « … le lundi 09 novembre 2026 », « Prolongation … au 28/10/2026 ») | cette date | oui (26-102338, 26-102325, 26-102494, 26-102254, 26-102090) |
  | Phrase qui cite une date **sans année** (« reportée au vendredi 30 octobre à 17h00 ») | **non lue** : l'année n'est jamais complétée | oui (26-102412, 26-102209) |
  | Phrase qui cite **deux dates** sans « au lieu de … lire … » (« DLRO initiale : 26 octobre 2026 … DLRO mise à jour : 2 novembre 2026 ») | **non lue** : jamais un choix | oui (26-101444) |
  | Rectificatif qui ne parle pas de la date limite de réponse (numéros de lots, critères, visite, questions, ouverture des plis) | la date de l'avis reste | oui (26-102445, 26-100570, rubrique « Visite » de 26-102230) |
  | `rubDelais` autre que « ReceptionOffres » ; bloc `infosRectif` absent ; type inattendu | **non lue** (prudence) | **non vérifié** : jamais observé |
  | Rectificatif d'un format sans `infosRectif` connu (famille DSP, 1 en octobre) | `infosRectif` cherché où qu'il soit ; sinon **non lue** | **non vérifié** |

  « Parle de la date limite de réponse » : remise, réception, dépôt ou transmission **des offres, plis, candidatures,
  réponses ou dossiers**, « DLRO », « date limite de réponse ». Jamais la date des questions, de la visite ou de
  l'ouverture des plis. Une nouvelle date **antérieure à la parution du rectificatif** est impossible : non lue.
- *Une date non lue* : la fiche n'affiche **jamais l'ancienne date** ni une date devinée ; sa date limite reste vide
  (« non précisée » à l'écran), l'ancienne est gardée à part, et la fiche le signale
  (`date_limite_rectifiee_non_lue`). Elle reste affichée (elle n'est pas « clôturée »), et un doublon d'une autre
  source ne comble jamais cette date (`search._dedup_tenders`).
- *Pannes.* La requête des suites a un seul essai, bornée par le temps restant (9 s depuis le début de la recherche
  BOAMP, sous les 14 s de la recherche) : en cas d'échec, les avis sont rendus tels que publiés, comme avant, avec ce
  que la page dit d'elle-même (annulation et rectificatif européens), et le journal le dit. Le BOAMP n'est jamais
  marqué en panne pour autant. Une ligne de journal résume chaque recherche concernée (« N avis rectifié(s) (dont N
  date(s) non lue(s)), N annulé(s) retiré(s), N repris par leur rectificatif »).
- *Fiche* (`app/sourcing/schemas.py`) : 4 champs, envoyés au navigateur (le corps brut ne l'est jamais) :
  `rectificatifs` (liste de sources : BOAMP, lien, référence), `rectifie_le`, `date_limite_initiale`,
  `date_limite_rectifiee_non_lue`. Les liens des rectificatifs passent par la même garde que les autres liens
  (`base.sanitize_tender_links`).

**Preuve.**
- `test_lire_rectificatif_sur_les_formes_reelles` : les 17 rectificatifs réels du jeu, un par un, avec la date que
  dit leur texte.
- `test_lire_rectificatif_formes_jamais_observees_prudentes` (cas construits) : bloc absent, autre délai, type
  inattendu, date antérieure à la parution, questions, visite, ouverture des plis, deux dates.
- `test_boamp_rectificatifs_et_annulations_rattaches` : la recherche sur le jeu réel (API simulée) donne 6 fiches,
  dont 26-90336 au 06/11 (critère de sortie de l'étude), 26-90521 au 05/11, 26-94570 au 03/11, 26-91602 au 09/11,
  26-93829 au 18/11 sans 26-101544, 26-95098 sans 26-101475 ; ni 26-95755, ni 26-91526, ni 26-101778 ; 3 requêtes.
- `test_boamp_date_rectifiee_illisible_…`, `test_boamp_rectificatif_hors_date_garde_la_date` (liens construits sur
  des textes réels), `test_boamp_rectificatif_europeen_seul_…`, `test_boamp_suites_en_panne_…`,
  `test_boamp_page_suivante_sans_reprise`.
- Une recherche réelle de bout en bout, le 21/10/2026 (« endiguement », sans département) : 3 requêtes, 2,0 s pour le
  BOAMP ; 7 avis, dont 26-90336 repris au 06/11 (ancienne date 16/10), 26-91865 du 23/10 au 06/11 (« Report de la
  date limite de remise des offres au 6 novembre 2026 à 13h00 », 26-101577) et 26-91161 du 02/11 au 06/11
  (« Au lieu de 02/11/2026 à 12h00, lire 06/11/2026 à 10h00 », 26-102546) ; les deux textes ont été relus à la
  source. Les 5 contrôles de l'étude (§ 6.2) restent à rejouer à la sortie du lot sur des avis encore ouverts ce
  jour-là.

**Ce qui change pour le client.**
- Un avis rectifié montre la nouvelle date limite ; un avis repoussé reste visible après son ancienne date ; un avis
  annulé ou déclaré sans suite disparaît ; un avis européen rectifié n'apparaît plus deux fois.
- Quand la nouvelle date ne peut pas être lue sans doute, la carte dit « limite non précisée » au lieu de l'ancienne
  date.
- Le lien « Voir l'annonce officielle » reste celui de l'avis initial ; le lien du rectificatif et la date
  « modifiée le … » sont dans les données, l'écran les montrera plus tard (après la 2b). En attendant, sur un avis
  rectifié, la date de la carte peut différer de celle de la page de l'avis initial : c'est la date du rectificatif.
- Les alertes : un avis rectifié garde sa référence, il n'est donc pas renvoyé comme un nouveau marché ; un avis
  repris par son rectificatif ne l'est pas non plus s'il avait déjà été envoyé ; un avis annulé n'est plus envoyé.
  Une seule fois, à la mise en ligne : un avis européen rectifié déjà envoyé sous la référence de son rectificatif
  (avant ce lot) peut être renvoyé sous celle de son avis initial. Le format des références d'alerte lui-même relève
  du chantier des alertes (`app/services/alerts.py`, non touché ici).
- Une recherche fait 1 ou 2 appels de plus au BOAMP (mesuré : 2,0 s pour les 3 appels de la recherche réelle).

### S.3 Le vocabulaire interne du BOAMP n'est plus un code métier européen

**Avant.** Les codes `descripteur_code` du BOAMP (son vocabulaire interne : « 310 » = « Rivières/ruisseaux »,
« 45 » = « Cd, DVD » selon l'étude) étaient rangés dans le champ `cpv` de la fiche, puis :
- comparés aux codes CPV de l'entreprise par leurs premiers chiffres : un avis « 45 » devenait un « métier
  correspondant » pour toute entreprise du bâtiment (CPV 45…) ;
- ajoutés à la recherche : un code CPV saisi dans « Recherche détaillée » élargissait le BOAMP à
  `descripteur_code like "4526"` (« 45 » saisi : `like "45"`, soit « Cd, DVD »).

**Après.**
- `boamp._normalize` : `cpv` vide pour un avis du BOAMP (les descripteurs restent dans `raw`, pour la traçabilité).
  La complétude affichée (« confiance N % ») ne change pas : les descripteurs comptent toujours comme un champ
  renseigné.
- La recherche BOAMP n'utilise plus les codes CPV saisis (le champ dit « Europe / TED » ; TED les lit toujours).
- `scoring.score_tender` ne compare plus que de **vrais codes CPV** (8 chiffres, clé de contrôle facultative :
  « 45261000 », « 45261000-7 »), d'où qu'ils viennent, y compris d'un ancien avis renvoyé par le navigateur.
- Test corrigé, avec sa raison : `tests/test_hardening_audit.py`, l'avis d'essai qui porte de vrais CPV à 8 chiffres
  est un avis **TED** et non BOAMP (le BOAMP n'en publie aucun dans les champs lus) ; les tests du barème sont
  inchangés et passent.

**Preuve.** `test_boamp_descripteurs_jamais_lus_comme_cpv` (26-90336 réel : `cpv` vide, descripteurs 310, 91, 197
gardés, complétude 1,0 ; aucune clause `descripteur_code` dans la requête), `test_score_pas_de_metier_correspondant_…`
(« 45 » : 0 point ; avant : 12 points ; un vrai CPV, avec ou sans clé, correspond toujours).

**Ce qui change pour le client.**
- Plus de faux « métier correspondant » sur une carte BOAMP ; la note d'adéquation de ces cartes peut baisser.
- Une recherche avec des codes CPV ne ramène plus d'avis BOAMP sans rapport par ces codes (les mots-clés, eux, ne
  changent pas).
- L'analyse sur l'annonce seule (repli quand le dossier n'est pas accessible) reçoit « DESCRIPTEURS : non précisé »
  au lieu de numéros sans signification (`routers/sourcing._tender_as_text`, non touché). Effet de bord à connaître :
  l'empreinte de l'analyse partagée d'une telle annonce change une fois (par défaut, mesure seule : seule la mesure des
  doublons voit une clé neuve ; si `ANALYSE_PARTAGEE=1`, une annonce déjà analysée avant la mise en ligne est
  réanalysée une fois). Le crédit débité au client ne change pas.

### S.4 Outre-mer : le code complet ; la Corse intacte

**Avant.** Le filet de sécurité de la recherche ne gardait que 2 caractères du département : 971 à 976 devenaient
tous « 97 » (une recherche « 974 » laissait passer la Guadeloupe). La zone de la note faisait de même, et lisait le
département du code postal sur 2 chiffres (« 97400 » → « 97 ») : pour une entreprise de La Réunion, un avis de la
Guadeloupe était « dans votre zone » ; et un avis du 974 était « hors zone » pour qui avait saisi « 974 » sans code
postal. La zone de la note comparait aussi en minuscules (« 2a » ≠ « 2A ») : la Corse saisie n'était jamais
« dans votre zone ».

**Après.**
- `base.dept_cle` et `base.dans_departements` : comparaison sur le code complet, en majuscules, « 6 » → « 06 ». Seule
  tolérance, gardée telle qu'avant : « 97 » ou « 98 » saisis sur deux chiffres couvrent tout leur outre-mer.
- `search.py` (filet de sécurité) et `scoring.py` (zone de la note) s'en servent ; le code postal donne le
  département sur 3 chiffres pour l'outre-mer (« 97400 » → « 974 »).
- La Corse : « 2A » reste « 2A », « 2B » reste « 2B », jamais coupés ni confondus ; un code postal corse donne « 20 »
  comme avant (la correspondance 2A/2B par code postal n'est pas ajoutée).
- Hors chantier (autre chantier du lot) : les fins de contrat (`app/services/decp.py`, `app/routers/sourcing.py`).

**Preuve.** `test_recherche_departements_outre_mer_code_complet` (« 974 » ne garde plus le 971 ; « 2A », « 2B »
séparés ; « 97 » garde tout l'outre-mer ; « 6 » trouve « 06 »), `test_score_zone_outre_mer_et_corse`.

**Ce qui change pour le client.**
- Outre-mer : une recherche « 971 », « 972 », « 973 », « 974 » ou « 976 » ne montre plus les avis des autres
  départements d'outre-mer ; la zone de la note est juste pour une entreprise d'outre-mer.
- Corse : une entreprise qui a saisi « 2A » ou « 2B » dans « Ce que je cherche » voit les avis de son département
  « dans votre zone » (la note de ces avis monte). La recherche corse ne change pas.

### S.5 Vérifications

- Suite complète sur `0afc1ed` le 21/10/2026 (copie propre, `TZ=UTC`) : **1 échec**, sans lien avec le lot :
  `tests/test_reorganisation_v1_relecture.py::test_compte_rendu_de_la_demonstration` refusait « 1/1 » dans le PDF du
  compte-rendu, or la date d'édition « 21/10/2026 » le contient (le test échoue chaque jour en 1 d'octobre à décembre).
  Corrigé dans le test seul : « 1/1 » est cherché comme fraction (ni chiffre ni « / » autour) ; le PDF ne change pas.
- Suite complète sur ce chantier, le 21/10/2026 (`TZ=UTC`, base SQLite d'essai) : **2 222 tests, tous verts** (les 2 205
  de la production, dont le test daté corrigé, et les 17 nouveaux). Les 17 nouveaux, posés sur une copie propre de
  `0afc1ed` : 17 échecs, chacun sur le défaut qu'il couvre.
- Aucun changement de base de données : rien à vérifier sur Postgres.

### S.6 Ce qui reste, et ce que j'ai vu en passant

- **À rejouer à la sortie du lot** : les 5 contrôles de l'étude (§ 6.2), sur des avis ouverts ce jour-là.
- **Non vérifié** : les mois de janvier à septembre sur une page Mégalis réelle (à revoir quand des consultations
  en montreront) ; PLACE (suspendue, jamais lue) ; les formes de rectificatif marquées « non vérifié » ci-dessus.
- **Limite connue** : un avis dont l'ancienne date est passée et dont le rectificatif est illisible n'est pas repris
  (comme avant) : on ne montre pas un marché peut-être clos sur une date qu'on n'a pas pu lire.
- **Limite connue** : un rectificatif européen dont l'objet ne répond plus aux mots de la recherche n'est pas vu ;
  l'avis initial garde alors son ancienne date (au plus jusqu'à cette date).
- **Vu, hors chantier** : la fiche BOAMP range ses descripteurs (« Toiture, Couverture ») dans `lieu` (`boamp.py`,
  inchangé : la note s'en sert pour les mots du métier) ; `scoring.synergy_score` coupe aussi les départements à
  2 chiffres pour les partenaires (outre-mer) ; `routers/sourcing._tender_as_text` pourrait donner les libellés des
  descripteurs à l'analyse de repli.
