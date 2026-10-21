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

---

## Services

*Points 4 bis, 5, 6, 7, 8 et 9 de la note. Fichiers modifiés : `app/services/decp.py`, `app/services/renewal.py`,
`app/routers/sourcing.py`, `app/sourcing/schemas.py` (une ligne), `app/services/alerts.py` (alertes de marchés
seulement), `app/routers/amont.py` ; nouveaux : `scripts/mesure_rappel.py`, `tests/test_moteur_lot1_services.py`,
`tests/fixtures/moteur_lot1_services/` ; tests adaptés : `tests/test_essai_termine.py`, `tests/test_secu_fichiers.py` (point 7) et
`tests/test_reorganisation_v1_relecture.py` (un test qui dépendait de la date, voir « Vérifications »). Aucun fichier de l'écran
(`app/static/*`, traductions), aucun fichier de `app/sourcing/sources/`, ni `app/sourcing/search.py`, ni
`app/sourcing/scoring.py`. Ni prix, ni quota, ni IA ajoutée, ni changement de base de données, ni nouveau
planificateur. Le robot de Mégalis n'est pas touché.*

### Ce qui change pour le client (récapitulatif pour Eliot)

1. Onglet « À venir », outre-mer : seules les fins de contrat du département demandé (974 ne montre plus 971) ; le
   département s'affiche sur 3 chiffres (« 974 »). « 6 » saisi seul est lu dans la DECP (sans crédit) au lieu de passer par le repli payant.
2. Recherches de partenaires « Chercher » (page du marché) et « Répartition proposée » : des PME seulement ; les
   grandes entreprises n'y sont plus proposées.
3. Courriels d'alerte : plus de marchés (plus aucun écarté par la note avant dossier) ; au-delà de 10 par alerte, la
   ligne « … et N autres marchés : relancez cette recherche dans Adjugo pour les voir tous. » ; moins de marchés
   reçus deux fois. « Tester » une alerte annonce plus de nouveaux marchés.
4. API seulement (rien à l'écran) : `past_wins` vaut `null` quand les marchés gagnés n'ont pas pu être lus ;
   les adresses de la veille masquée répondent 404 (aucun écran n'y mène).
5. Rien d'autre : l'alerte hebdomadaire (aucun client), le journal du repli payant et l'outil de mesure ne se voient
   pas.

### Comment c'est prouvé

- **Tests** : `tests/test_moteur_lot1_services.py`, 13 tests, sans réseau (toute lecture est remplacée par un jeu
  d'essai, l'IA est simulée). Les 13 échouent sur `0afc1ed` : vérifié en copiant ce fichier et ses jeux d'essai dans
  un export de `0afc1ed` (`git archive`), voir « Vérifications » en fin de section.
- **Jeux d'essai** (`tests/fixtures/moteur_lot1_services/`) : de vraies réponses publiques lues le 21/10/2026 par 6
  requêtes GET, avec l'en-tête honnête d'Adjugo (`AdjugoBot/1.0 (+https://adjugo.pro ; contact@adjugo.pro)`), une
  requête par seconde au plus : DECP (un enregistrement complet pour lire les champs, non gardé ; les fins de
  contrat de travaux de La Réunion 974, de la Guadeloupe 971 et de la Corse-du-Sud 2A ; les marchés d'une
  entreprise titulaire en Corse) et BOAMP (avis d'attribution de voirie du Finistère). Les numéros des titulaires
  (entreprises, parfois des entrepreneurs individuels) sont remplacés par des numéros fictifs ; tout le reste est
  tel que lu (objets, acheteurs publics, codes de lieu, dates, procédures, montants). Aucune autre requête réseau.
- **Formes réellement observées** dans la DECP : l'outre-mer arrive en code postal (« 97432 », « 97110 », type
  « Code postal ») ; la Corse en « 2A » (type « Code département ») ou en code postal « 20110 », « 20142 ».

### 4 bis. Outre-mer dans les fins de contrat

| | |
|---|---|
| **Avant** | Les départements étaient coupés à 2 caractères dans la route (`app/routers/sourcing.py:318` de `0afc1ed`), dans la lecture de la DECP (`app/services/decp.py:72`) et dans le filtre des lignes (`:111`). Une recherche « 974 » demandait « 97 » à la DECP et gardait toute l'outre-mer (971 à 976). « 6 » saisi seul était demandé tel quel (`startswith "6"` : départements 60 à 69) puis tout était écarté, ce qui déclenchait le repli payant. La note de zone d'une fin de contrat (`app/services/renewal.py:148`) comparait elle aussi sur 2 caractères. |
| **Après** | Une seule règle, `code_departement` (`app/services/decp.py:28`) : 2 chiffres en métropole (« 6 » → « 06 », « 29232 » → « 29 »), 3 en outre-mer (« 97432 » → « 974 »), Corse « 2A » / « 2B » inchangée, code postal corse « 20… » laissé à « 20 » (il ne dit pas 2A ou 2B : on ne devine pas). Le filtre des lignes répète exactement le filtre envoyé à la DECP (`dans_les_departements`, `:45` : le code du lieu commence par le département voulu). La route (`app/routers/sourcing.py:322`) et la note de zone (`app/services/renewal.py:149`, `_departements_voulus`) suivent la même règle. « 97 » saisi seul garde toute l'outre-mer, comme avant. |
| **Preuve** | `test_fins_de_contrat_sur_le_code_complet_974_ne_voit_plus_971_corse_et_metropole_inchangees` (vraies lignes 974, 971 et 2A) ; `test_onglet_a_venir_demande_le_code_complet_et_note_la_zone_d_outre_mer` (de bout en bout par la route, et la note de zone 974 contre 971). |
| **Pour le client** | Onglet « À venir » d'une entreprise d'outre-mer : seules les fins de contrat de son département ; le département affiché est « 974 » au lieu de « 97 ». « 6 » saisi seul est lu dans la DECP, sans crédit, au lieu de passer par le repli payant. Métropole et Corse : inchangé. |

### 5. Partenaires

**5 a. Une panne de la DECP n'est plus lue « 0 marché »**

| | |
|---|---|
| **Avant** | `wins_by_siren` rendait `{"count": 0}` quand la DECP ne répondait pas (`app/services/decp.py:162-164`), et `past_wins` valait 0 par défaut (`app/sourcing/schemas.py:128`), y compris pour une entreprise jamais consultée (au-delà des 12 premières). La note de synergie de la recherche de partenaires disait alors « Aucun marché public gagné trouvé en source DECP pour ce SIRET. » (`app/sourcing/scoring.py:432`), sans l'avoir lu. Le numéro de l'entreprise était écrit dans le journal à chaque panne. |
| **Après** | Une panne (ou une réponse sans compte lisible) lève `DecpIndisponible` (`app/services/decp.py:23`, `:200`, `:203`) ; le numéro n'est plus écrit dans le journal. `past_wins` vaut `None` tant que rien n'a été lu (« non vérifié », `app/sourcing/schemas.py:129`) : l'enrichissement de `app/sourcing/search.py`, inchangé, laisse alors la valeur inconnue. Sur la route `/api/sourcing/cotraitants`, une entreprise au compte inconnu reçoit la note « Marchés publics gagnés non vérifiés en source DECP pour ce SIRET. » (`app/routers/sourcing.py:1397`, `:1430`). Un vrai zéro lu reste un zéro. |
| **Preuve** | `test_panne_de_la_decp_jamais_lue_zero_marche` (panne, réponse sans compte, zéro lu ; recherche de partenaires ; route). |
| **Pour le client** | Rien de visible à l'écran : la pastille « N gagné(s) » ne s'affiche ni pour 0 ni pour un compte inconnu, et la note de synergie n'est affichée nulle part (`app/static/app.html`, `app.js`). Dans les réponses de l'API, `past_wins` vaut `null` au lieu de `0` quand le compte n'a pas été lu. |

**5 b. « PME seulement » sur les deux recherches de partenaires qui ne l'avaient pas**

| | |
|---|---|
| **Avant** | La recherche « Chercher » de la page du marché (`/api/sourcing/cotraitants`, `app/routers/sourcing.py:1388-1390` de `0afc1ed`) et la répartition proposée partie par partie (`/api/sourcing/groupement`, `:214-215`) interrogeaient le registre sans filtre de taille ; le verdict de groupement, lui, l'avait déjà (`app/services/groupement_verdict.py:300`). |
| **Après** | Les deux passent `pme_only=True` (`app/routers/sourcing.py:217`, `:1418`) : le registre est interrogé avec la catégorie INSEE « PME » (micro-entreprises comprises, `app/sourcing/sources/sirene.py:94-97`, inchangé). |
| **Preuve** | `test_pme_seulement_sur_les_deux_recherches_de_partenaires` (paramètres envoyés au registre, pour les deux routes). |
| **Pour le client** | Les grandes entreprises et les entreprises de taille intermédiaire ne sont plus proposées comme partenaires sur ces deux écrans. Non mesuré : la part d'entreprises sans catégorie calculée par l'INSEE (récentes), que ce filtre écarte aussi, comme déjà dans le verdict de groupement. |

### 6. Alertes de marchés (pas les rappels d'invitation)

**6 a. Plus aucun tri caché par la note avant dossier (décision 11)**

| | |
|---|---|
| **Avant** | Un marché n'était envoyé que si sa note avant dossier atteignait le seuil de l'alerte, ou à défaut le seuil « bon potentiel » de « Ce que je cherche » (`app/services/alerts.py:393-401` de `0afc1ed`). Le reste était écarté sans le dire, sur une note encore faussée. |
| **Après** | Aucun marché n'est écarté à cause de sa note (`run_one_saved_search`, `app/services/alerts.py`). La liste reste triée dans l'ordre de la recherche ; le courriel montre toujours 10 marchés au plus par alerte ; au-delà, une ligne les compte : « … et N autres marchés : relancez cette recherche dans Adjugo pour les voir tous. » (`:531`, règle 8 du moteur : rien n'est caché en silence). Le seuil reviendra en V2, réglable et annoncé. La colonne `min_score` reste en base et dans l'API, mais n'écarte plus rien. |
| **Preuve** | `test_alerte_n_ecarte_plus_un_marche_a_cause_de_sa_note_avant_dossier` (deux marchés notés 90 et 30 sous un seuil de 70 : les deux partent ; « Tester » dit 2) ; `test_courriel_compte_les_marches_au_dela_des_dix_premiers`. |
| **Pour le client** | Les courriels d'alerte peuvent contenir plus de marchés ; une ligne « … et N autres marchés » apparaît au-delà de 10. « Tester » une alerte annonce plus de nouveaux marchés. |

**6 b. « Hebdomadaire » réellement appliqué**

| | |
|---|---|
| **Avant** | Une alerte « hebdomadaire » partait à chaque appel programmé, comme une quotidienne (`app/services/alerts.py:425`). Aucun client ne peut la choisir (l'écran crée des alertes quotidiennes) : précaution. |
| **Après** | Une alerte hebdomadaire déjà servie repart 7 jours de Paris après son dernier passage, quelle que soit l'heure de l'appel (`_hebdomadaire_pas_encore_due`, `:485`, `:510`) ; jamais servie, elle part au premier passage. Le compte rendu de l'appel programmé dit combien attendent (`weekly_not_due`, `:542`). |
| **Preuve** | `test_hebdomadaire_reellement_applique` (2 jours : attend ; 7 jours : part ; quotidienne et hebdomadaire neuve : partent). |
| **Pour le client** | Aucun aujourd'hui (seule la démo, qui n'est pas servie, en a une). |

**6 c. Chaque référence porte le nom de sa source ; les anciennes restent reconnues**

| | |
|---|---|
| **Avant** | La mémoire d'une alerte (`last_seen_refs`) gardait la référence nue de la première source (`app/services/alerts.py:396-397`, `:410-411`). Un même marché vu sur le BOAMP et sur Mégalis était renvoyé le jour où Mégalis le rendait seul (autre référence). Un numéro nu d'une source pouvait masquer le marché d'une autre. La liste repassait par un ensemble avant d'être coupée à 500 : des références étaient retirées au hasard, dont celles de marchés encore ouverts, renvoyés ensuite. |
| **Après** | Une entrée par marché, avec toutes ses références écrites « SOURCE\|référence » (l'avis et chaque source où il a été vu), jointes par « + » (`_refs_du_marche`, `:400` ; `_memoriser`, `:383`). Une entrée ancienne (référence nue, ou clé de fusion nue) est reconnue, puis fusionnée dans l'entrée du marché quand il revient. L'ordre est gardé, le marché vu aujourd'hui passe en fin de liste, et seuls les plus anciens sortent au-delà de 500 marchés (même borne qu'avant, `:372`). « N marché(s) déjà vu(s) » compte toujours des marchés. |
| **Preuve** | `test_references_avec_leur_source_anciennes_reconnues_rien_renvoye_deux_fois` (mémoire ancienne de 41 références ; jour 1 BOAMP + Mégalis ; jour 2 Mégalis seul : rien de renvoyé ; ordre exact ; compte de l'écran) ; `test_memoire_bornee_aux_plus_anciens_jamais_au_hasard`. |
| **Pour le client** | Moins de marchés reçus deux fois. Aucun marché déjà reçu n'est renvoyé au passage à la nouvelle forme. |

### 7. Les adresses de la veille masquée refusent proprement

| | |
|---|---|
| **Avant** | `/api/amont/scan`, `/analyze-upload` et `/analyze-text` répondaient à tout utilisateur connecté, l'interrupteur éteint : un appel direct débitait une analyse et appelait l'IA ; `/auto` pouvait réactiver l'ancienne veille (`app/routers/amont.py:122-213` de `0afc1ed`). |
| **Après** | Tant que `PROJETS_A_VENIR` est éteint, les trois adresses répondent 404 « « Projets à venir » n'est pas encore ouvert : rien n'a été analysé ni décompté. », AVANT toute lecture de fichier, toute recherche, tout appel à l'IA et tout débit (`_exiger_ouverte`, `app/routers/amont.py:37`, appelée `:140`, `:158`, `:181`). L'activation par `/auto` répond 404 avec sa phrase (`:231`). Ce qui reste ouvert, volontairement : la désactivation par `/auto` (retirer son accord aux courriels ne coûte rien et ne doit jamais être bloqué), la lecture de l'état (`GET /auto`), la liste et la suppression des signaux gardés. Interrupteur allumé : comportement inchangé. |
| **Preuve** | `test_adresses_de_la_veille_masquee_refusent_sans_debiter` (aucune lecture, aucun appel à l'IA, aucun débit, abonnement resté éteint ; puis interrupteur allumé : réponses d'avant). `tests/test_essai_termine.py` rallume l'interrupteur dans ses deux tests de la veille, qui vérifient le refus propre à l'essai terminé ; `tests/test_secu_fichiers.py` aussi, pour vérifier la lecture bornée à 50 Mo de `/analyze-upload` veille ouverte (veille fermée, rien n'est lu). |
| **Pour le client** | Rien à l'écran (aucun écran n'y mène tant que la veille est masquée). Un appel direct ne coûte plus d'analyse. |

### 8. Le repli payant de l'onglet « À venir » est noté dans le journal (décision 12)

| | |
|---|---|
| **Avant** | Quand la DECP ne donnait rien ou ne répondait pas, le repli BOAMP + IA débitait une analyse (remboursée s'il ne trouvait rien), sans aucune trace de ce qu'il trouvait (`app/routers/sourcing.py:329-344` de `0afc1ed`). |
| **Après** | Le repli est gardé tel quel (même débit, même remboursement). Chaque repli écrit UNE ligne dans le journal (`_journal_repli_a_venir`, `app/routers/sourcing.py:358`) : son motif (« DECP sans résultat », « DECP indisponible » ou « DECP en erreur »), les départements (codes de 2 ou 3 caractères), le nombre de fins de contrat trouvées, combien ont une durée lue et combien une durée estimée par type de contrat, le nombre d'erreurs de source, le sort de l'analyse (« débitée », « remboursée », ou « remboursée (repli en échec : …) ») et les références publiques des avis d'attribution du BOAMP (10 au plus). **Sans donnée personnelle** : ni utilisateur, ni organisation, ni adresse, ni mots tapés. Exemple : `repli payant « À venir » (BOAMP + IA) : motif=DECP indisponible ; départements=29 ; fins de contrat trouvées=3 (durée lue 1, durée estimée 2) ; erreurs de source=0 ; analyse débitée ; avis BOAMP=25-34232,25-10734,25-8460`. Niveau INFO, écrit en production (`LOG_LEVEL` vaut INFO par défaut, `app/core/config.py:41` ; la valeur posée dans Railway n'est pas vérifiée). |
| **Preuve** | `test_repli_payant_note_dans_le_journal_sans_donnee_personnelle` (vrais avis d'attribution du BOAMP, IA simulée ; repli qui trouve : débité ; repli vide : remboursé). |
| **Pour le client** | Rien. L'annonce du crédit avant le clic est un point de la partie écran (point 12), après la 2b. |

### 9. L'outil rejouable de mesure du rappel

| | |
|---|---|
| **Avant** | Aucun outil (moteur § 4.4, point 1). |
| **Après** | `scripts/mesure_rappel.py`, outil de poste, jamais lancé en production, sans IA. `collecter` lit dans la DECP (en-tête honnête, une requête par seconde) les marchés gagnés depuis 12 mois par chaque PME de la liste de Mathys (titulaire 1, 2 ou 3), les dédoublonne et classe leur publicité d'après la procédure publiée (« avec », « sans », « inconnue » sous le seuil de dispense) ; Mathys vérifie, marché par marché, si l'annonce était dans une source qu'Adjugo lit (colonne `avis_vu`) ; `mesurer` rejoue, sans réseau, les règles du code de ce jour-là (mots : règle de la recherche BOAMP ; zone : `app/services/decp.py` ; type : code CPV) et rend le rappel en fourchette [bas, haut] tant que des lignes ne sont pas vérifiées. Les fichiers restent HORS du dépôt (le script refuse un chemin du dépôt) ; le bilan JSON ne contient que des comptes. Mode d'emploi en tête du script. |
| **Preuve** | `test_mesure_du_rappel_rejouable_sans_reseau` (vrais marchés d'une entreprise de Corse, numéro fictif : fenêtre de 12 mois, doublons, publicité, mesure avant et après vérification, bilan sans objet ni numéro) ; `test_mesure_du_rappel_refuse_le_depot_et_suit_la_regle_de_la_recherche_boamp` (les motifs rejoués sont exactement ceux que `BoampSource` envoie au BOAMP : si la règle change, ce test le signale). |
| **Pour le client** | Rien. Pour la mise en ligne du lot : la liste des numéros d'entreprise des PME en test, par Mathys, puis `collecter` et `mesurer --etiquette avant-lot1` avant la mise en ligne. |
| **Non vérifié** | L'équivalence exacte de la règle des mots avec l'opérateur `like` d'OpenDataSoft (découpage en mots, accents). Le BOAMP lit aussi son vocabulaire interne (descripteur), absent de la DECP : un « mots : non » peut sous-estimer ce que la recherche aurait trouvé, et la raison le dit. Les seuils de dispense (100 000 € HT en travaux, 60 000 € HT sinon, étude moteur § 5.1) sont ceux de 2026 ; pour les marchés notifiés fin 2025, le seuil des fournitures et services était peut-être plus bas : le classement « avec » est donc prudent (un marché classé « inconnue » est vérifié par Mathys). La DECP publie avec retard (32,6 % des lignes plus de 60 jours après la notification, moteur § 5.3) : les derniers mois de la fenêtre sont incomplets, d'où la mesure sur la MÊME liste avant et après. |

### Ce qui ne change pas

- La démo : ses fins de contrat, sa recherche et l'aperçu de ses alertes sont servis à part (`app/services/demo_search.py`, `app/routers/saved_searches.py:95-103`), sans réseau ni IA ; l'aperçu de la démo garde son propre seuil fictif.
- Prix, quotas, débits et remboursements (le repli payant débite et rembourse comme avant).
- Aucune IA ajoutée ; le robot de Mégalis, ses limites et son refus sans contournement ; un seul processus, aucun nouveau planificateur ; aucune nouvelle route de données, cloisonnement de la co-traitance intact.
- Les alertes lisent toujours 25 résultats par recherche ; le courriel ne donne aucune note sur 100.

### Relevé en passant, non corrigé (hors du périmètre de ce chantier)

- La répartition proposée partie par partie (`/api/sourcing/groupement`) tire le département du lieu d'exécution sur 2 chiffres (`app/routers/sourcing.py:191-198`) : outre-mer, elle cherche des partenaires dans « 97 ». Même défaut que le point 4 bis, sur une autre route.
- `app/services/agents/amont.py:_deps` coupe toujours à 2 caractères : c'est la veille, traitée à sa vague 1.
- La note de synergie inconnue est posée par la route (`app/routers/sourcing.py:1430`) parce que `app/sourcing/scoring.py` appartient à l'autre chantier ; `synergy_score` pourra lire `past_wins = None` lui-même quand ce fichier sera repris.

### Vérifications

- **Les 13 nouveaux tests échouent tous sur `0afc1ed`**, chacun sur le défaut qu'il couvre : copiés avec leurs jeux
  d'essai dans un export de `0afc1ed` (`git archive`), ils rendent par exemple `['97'] == ['974']` (route et lecture
  DECP), « DID NOT RAISE » (panne lue « 0 marché »), des paramètres du registre sans `categorie_entreprise`, un seul
  marché sur deux sous le seuil de note, `['26-98235'] == ['BOAMP|26-98235']` (référence sans source), l'alerte
  hebdomadaire rejouée au bout de 2 jours, l'absence de la ligne « … et 2 autres marchés », une réponse 200 de
  `/api/amont/scan` interrupteur éteint, aucune ligne de journal pour le repli payant, et l'outil absent.
- **Suite complète** : verte sur cette branche, 2 218 tests sur 2 218 (2 205 sur `0afc1ed` + les 13 nouveaux). Sur `0afc1ed`, le 21/10/2026, un
  seul échec, sans lien avec ce chantier : `test_compte_rendu_de_la_demonstration`
  (`tests/test_reorganisation_v1_relecture.py`) vérifie qu'aucun « 1/1 » n'apparaît dans le compte-rendu, or la date
  « édité le 21/10/2026 » en contient un. Le test retire désormais les dates (toujours sur 2 chiffres) avant de
  chercher « 1/1 » ; un vrai « 1/1 » reste détecté.
- **Aucun changement de base de données** : la nouvelle forme de la mémoire des alertes tient dans la colonne JSON
  existante (`saved_searches.last_seen_refs`), sans migration ; aucun essai Postgres n'était donc nécessaire.
- Tests lancés avec `ADJUGO_TEST_DB=<nom>.db TZ=UTC`, Python 3.12 depuis `requirements.lock`.
