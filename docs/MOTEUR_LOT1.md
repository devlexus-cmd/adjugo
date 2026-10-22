# Moteur de recherche, lot 1 « Dire juste » : partie serveur

Contrat du lot 1 du moteur de recherche des marchés. Note de décisions : « Projets à venir et moteur de recherche :
les décisions » (21/10/2026), section « La première étape que je lancerais : le lot 1 « Dire juste » », points 1 à 9
(partie serveur) ; les points 10 à 13 (écran) viennent après la vague 2b (section « Écran », à la fin). Étude de référence : « Le moteur de recherche
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

Le lot a été mené en deux chantiers parallèles, « Sources » (points 1 à 4) et « Services » (points 4 bis, 5 à 9), puis
réunis : chacun garde sa section, telle qu'il l'a écrite (les rares compléments de la réunion y sont marqués
*Réunion*), et la réunion a la sienne (vérifications de bout en bout sur des données réelles, deux défauts trouvés en
les faisant, corrigés). Puis une relecture en quatre angles : ses dix remarques, toutes reproduites, ont leur section
(« Relecture ») et sont marquées *Relecture* là où elles changent ce qui était écrit. Enfin une contre-relecture : ses
deux remarques, reproduites, ont la leur (« Contre-relecture », à la fin) et sont marquées *Contre-relecture* là où
elles changent ce qui était écrit. Chaque point dit : **avant**, **après**, **preuve**, **ce qui change pour le
client**.

## Ce qui change pour le client : la liste complète

*Tout le lot, partie serveur, après la réunion. Entre crochets, la section où le point est détaillé. Rien d'autre ne
change (voir « Ce qui ne change pas », plus bas).*

**Trouver des marchés (recherche)**
1. Mégalis : les cartes montrent leur date limite (avant : « limite non précisée » ; 10 dates vides sur 10 sur la page
   réelle du 21/10/2026). L'ordre des résultats bouge un peu, et le nombre « adéquation N/100 » d'une carte Mégalis
   peut changer (son délai de réponse compte enfin). [S.1] *Écran* : ce nombre n'est plus affiché ; seul l'ordre
   bouge.
2. Mégalis et BOAMP : une même consultation peut ne faire qu'une carte (« vu aussi sur »), mais seulement quand
   l'acheteur est écrit de la même façon des deux côtés. Sur les deux cas réels du 21/10/2026, aucun ne fusionne : ces
   consultations restent en deux cartes, comme avant. [S.1, R.4]
3. BOAMP, avis rectifié : la nouvelle date limite ; un avis repoussé reste visible après son ancienne date ; un avis
   européen rectifié n'apparaît plus deux fois. [S.2, R.3]
3 bis. *Relecture* : ces avis repoussés (date publiée passée, nouvelle date lue et pas encore passée) sont repris en
   première page, en plus des 15 lignes de l'écran ou des 25 des alertes : sur la recherche réelle « travaux » du
   21/10/2026 sans département, 16 de plus pour 25 lignes (41 cartes). Un avis encore ouvert sous sa date publiée
   n'est jamais repris ainsi : il reste à sa place dans les pages, avec son rectificatif (avant la relecture : 75
   cartes, dont 35 avis déjà présents plus loin). « Charger plus » reste proposé tant que la source a rempli sa
   page. [V.1, V.2]
4. BOAMP, avis annulé ou déclaré sans suite : il disparaît. [S.2, R.3]
5. Un rectificatif dont la nouvelle date ne peut pas être lue sans doute : « limite non précisée » au lieu de
   l'ancienne date. [S.2, R.4] *Relecture* : un rectificatif qui ne change qu'un autre délai en citant la date
   limite comme repère (« … 10 jours avant la date limite fixée pour la réception des offres ») laisse la date de
   l'avis, comme avant le lot (1 cas sur les 127 rectificatifs réels des jeux d'essai : 26-100865). [V.3]
   *Contre-relecture* : seulement si son texte ne cite aucune date. S'il en cite une, il n'est jamais écarté : la
   nouvelle date si elle est accolée à la date limite (« … avant la date limite de remise des offres fixée au
   05/11/2026 »), sinon « limite non précisée », jamais l'ancienne date (forme jamais observée). [C.1]
6. Le lien « Voir l'annonce officielle » reste celui de l'avis initial ; sur un avis rectifié, la date de la carte
   peut différer de celle de cette page (c'est la date du rectificatif). Le lien du rectificatif et « modifiée le … »
   sont dans les données ; l'écran les montrera après la 2b. [S.2] *Écran* : montrés (« Date limite repoussée au …
   (rectificatif du …) », avec le lien du rectificatif qui fixe la date).
7. Plus de faux « métier correspondant » sur une carte BOAMP : sa note d'adéquation peut baisser (*Écran* : cette
   note n'est plus affichée ; seul l'ordre des cartes bouge). Une recherche avec des codes CPV ne ramène plus d'avis
   BOAMP sans rapport par ces codes (les mots-clés ne changent pas). [S.3]
8. Outre-mer : une recherche « 971 », « 972 », « 973 », « 974 » ou « 976 » ne montre plus les avis des autres
   départements d'outre-mer, et la zone de la note est juste pour une entreprise d'outre-mer (un avis de la
   Guadeloupe n'est plus « dans votre zone » pour une entreprise de La Réunion). [S.4, R.3]
9. **Corse (ajouté à la réunion)** : une recherche « 2A » ou « 2B » montre enfin les avis du BOAMP, qui écrit la Corse
   « 20A » et « 20B » (19 avis ouverts le 21/10/2026 ; avant : aucun, sur toutes les recherches corses) ; une
   entreprise qui a saisi « 2A » ou « 2B » les voit « dans votre zone ». [R.1] *Relecture* : une entreprise au code
   postal corse (« 20… ») qui n'a saisi aucun département voit, comme avant, tous les avis corses « dans votre
   zone » (le code postal donne « 20 », qui couvre 2A et 2B ; avant la relecture : « Hors zone (2A) », 33 points de
   moins). [V.4]
10. Une recherche fait une ou deux requêtes de plus au BOAMP (entre 0,37 et 0,64 s chacune le 21/10/2026 ; 2,0 s pour
    la recherche complète mesurée par le chantier Sources). [S.2, R.3]

**Onglet « À venir »**
11. Outre-mer : seules les fins de contrat du département demandé ; le département s'affiche « 974 » au lieu de
    « 97 ». « 6 » saisi seul est lu dans la DECP, sans crédit, au lieu de passer par le repli payant. [Services 4 bis]
12. **Corse, repli payant (ajouté à la réunion)** : quand la DECP ne donne rien ou ne répond pas, le repli lit
    désormais les avis d'attribution corses du BOAMP ; avant, il ne trouvait jamais rien en Corse et l'analyse était
    toujours remboursée. Il peut maintenant trouver des fins de contrat, et l'analyse est alors débitée, selon la même
    règle que partout ailleurs (remboursée s'il ne trouve rien). La règle de débit ne change pas. [R.1]
    *Décidé par Eliot le 22/10 (b)* : en Corse et en outre-mer, le repli est remboursé, même s'il trouve, jusqu'à
    l'annonce du crédit à l'écran (§ « Décisions d'Eliot », plus bas).
12 bis. **Outre-mer, repli payant (relevé à la relecture)** : avant, le repli demandait « 97 » au BOAMP, qui n'écrit
    jamais l'outre-mer ainsi : il ne trouvait rien et l'analyse était toujours remboursée. Désormais il demande « 974 »
    (ou 971, 972, 973, 976), peut trouver des fins de contrat, et l'analyse est alors débitée, selon la règle
    habituelle. Et la DECP ne rend plus les fins de contrat des autres départements d'outre-mer (point 11) : quand le
    département demandé n'en a aucune, le repli payant part là où, avant, la DECP montrait celles d'un autre
    département, sans crédit. Code inchangé (la recherche sur « 974 » est juste). **À valider par Eliot**, comme la
    Corse (point 12). [V.5] *Décidé le 22/10 (b)* : remboursé, comme la Corse (point 12).
12 ter. *Relecture* : une durée que l'IA n'a pas vraiment rendue (0, « 36 » en texte) est remplacée par la durée par
    défaut du type de contrat ET dite estimée (avant la partie écran, la carte disait « (estimée) » au lieu de
    « (réelle) »), et le journal du repli la compte en « durée estimée ». Défaut antérieur au lot. [V.6] *Écran* : la
    carte dit « (durée estimée selon le type de contrat) », ou « (durée estimée par défaut, type de contrat inconnu) »
    quand l'IA ne donne pas de type (36 mois).
13. Chaque repli payant est noté dans le journal, que le client ne voit pas. [Services 8] *Écran* : cette ligne reste
    invisible, mais l'écran dit maintenant, après chaque repli, si l'analyse a été consommée ou remboursée.

**Partenaires**
14. « Chercher » (page du marché) et « Répartition proposée » : des PME seulement ; les grandes entreprises et les
    entreprises de taille intermédiaire n'y sont plus proposées. [Services 5 b]
15. API seulement : `past_wins` vaut `null` au lieu de `0` quand les marchés gagnés n'ont pas pu être lus. [Services 5 a]

**Alertes de marchés**
16. Plus aucun marché écarté par sa note d'avant dossier : les courriels contiennent plus de marchés. Sur l'alerte
    réelle « voirie » dans le 29 (21/10/2026), 7 marchés partent (5 du BOAMP, 2 de Mégalis), tous notés de 60 à 67,
    sous le seuil de 75 de « Ce que je cherche » : avant, cette alerte n'envoyait rien. [Services 6 a, R.3]
16 bis. **Adresse non confirmée (relevé à la relecture)** : un compte dont l'adresse n'est pas confirmée ne reçoit
    plus de courriel d'alerte de marchés (une adresse jamais prouvée peut être celle d'un tiers, et le point 16 en
    multipliait les envois : sur l'alerte réelle « voirie » 29, 0 courriel avant le lot, 1 de 7 marchés après). Ses
    marchés ne sont pas marqués « déjà vus » : ils partent au premier passage après la confirmation. Les comptes
    créés avant la vérification des adresses sont confirmés (migration de juin) : non concernés. **À valider par
    Eliot.** [V.7] *Décidé le 22/10 (b)* : la règle vaut pour tous les courriels planifiés vers le compte lui-même
    (« Demandez vos notes », « pièces à renouveler », veille amont compris), § « Décisions d'Eliot ».
17. Au-delà de 10 marchés par alerte, la ligne « … et N autres marchés : relancez cette recherche dans Adjugo pour les
    voir tous. » « Tester » une alerte annonce plus de nouveaux marchés ; la référence qu'il rend dans l'API reste
    celle de l'avis (« 26-98235 »), comme avant (*Relecture*). [Services 6 a, V.10]
17 bis. *Relecture*, partie écran : la bulle de « Mes alertes » dit « … qui vous correspondent (au-dessus de votre
    seuil de compatibilité) » ; aucun seuil n'écarte plus rien. Elle est à corriger avec la partie écran du lot, après
    la 2b (proposition : « Recevez par email les nouveaux marchés de cette recherche, 10 au plus par alerte, les autres
    comptés »). Jusque-là, elle dit le contraire du comportement. [V.8] *Décidé le 22/10 (b)* : corrigée dès cette mise
    en ligne, avec une phrase de plus pour rester vraie (§ « Décisions d'Eliot »).
18. Les dates des consultations Mégalis apparaissent dans le courriel (« — clôture 2026-12-07 »). [S.1, R.3]
19. Moins de marchés reçus deux fois. Aucun marché déjà reçu n'est renvoyé au passage à la nouvelle forme de mémoire ;
    un avis rectifié garde sa référence ; un avis repris par son rectificatif n'est pas renvoyé s'il avait déjà été
    envoyé ; un avis annulé n'est plus envoyé ; un avis européen rectifié déjà reçu sous la référence de son
    rectificatif n'est pas renvoyé sous celle de son avis initial (réglé à la réunion). [S.2, Services 6 c, R.2]
20. « Hebdomadaire » réellement appliqué : aucun client aujourd'hui (l'écran ne crée que des alertes quotidiennes).
    [Services 6 b]

**Analyse d'un marché**
21. L'analyse sur l'annonce seule (dossier non accessible) reçoit « DESCRIPTEURS : non précisé » au lieu de numéros
    sans signification. Effet de bord : l'empreinte de l'analyse partagée d'une telle annonce change une fois (par
    défaut, mesure seule ; si `ANALYSE_PARTAGEE=1`, une annonce déjà analysée est réanalysée une fois). Le crédit
    débité ne change pas. [S.3]

**Veille des projets à venir (masquée)**
22. Rien à l'écran ; un appel direct à ses anciennes adresses répond 404 et ne coûte plus d'analyse. [Services 7]

**Ce qui ne change pas** : les prix, les quotas, la règle de débit et de remboursement (le repli payant peut
désormais trouver, donc débiter, en Corse et en outre-mer : points 12 et 12 bis) ; la démo (sa recherche, ses fins de
contrat et l'aperçu de ses alertes sont servis à part, sans réseau ni IA : 194 tests de la démo verts, § R.5) ; aucune
IA ajoutée ; le robot de Mégalis ; un seul processus, aucun nouveau planificateur ; le cloisonnement de la
co-traitance ; aucune base de données modifiée ; les alertes lisent toujours 25 lignes par source et par recherche
(plus, au BOAMP, les avis repris par leur rectificatif : point 3 bis), et le courriel ne donne aucune note sur 100.

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
  *Réunion (§ R.4) : seulement quand l'acheteur est écrit de la même façon des deux côtés ; sur les deux cas réels
  du 21/10/2026, aucun ne fusionne.*
- L'ordre des résultats bouge un peu : le critère « délai de réponse » d'une carte Mégalis compte maintenant
  (il était mis de côté, faute de date) ; le nombre « adéquation N/100 » d'une carte Mégalis peut changer. *Écran* :
  ce nombre n'est plus affiché ; seul l'ordre bouge.
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
  *Relecture (§ V.1)* : et seulement si sa date limite publiée est déjà passée (`datelimitereponse < aujourd'hui`,
  dans la requête et après lecture) ; tous les avis visés sont demandés (100 au plus, une ligne de journal au-delà),
  et non plus les 50 premiers en silence.
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
  | *Relecture* : date limite nommée seulement comme repère d'un autre délai (« … 10 jours calendaires avant la date limite fixée pour la réception des offres »), texte **sans aucune date** | la date de l'avis reste | oui (26-100865) |
  | *Contre-relecture* : date limite nommée seulement derrière « avant / après », texte qui cite une date (« … offres à déposer avant la date limite de remise des offres fixée au 05/11/2026 ») | la date **accolée** à la date limite (« fixée / prévue / reportée … au / le » + date), dans la partie « lire » s'il y en a une ; sinon **non lue** | **non vérifié** : jamais observé (C.1) |

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
  du chantier des alertes (`app/services/alerts.py`, non touché ici). *Réunion (§ R.2) : réglé, plus aucun
  renvoi.*
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
- Plus de faux « métier correspondant » sur une carte BOAMP ; la note d'adéquation de ces cartes peut baisser
  (*Écran* : elle n'est plus affichée ; seul l'ordre bouge).
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
  comme avant (la correspondance 2A/2B par code postal n'est pas ajoutée). *Réunion (§ R.1) : le BOAMP écrit la
  Corse « 20A » / « 20B » ; ses avis sont désormais demandés sous les deux formes et lus « 2A » / « 2B ».*
  *Relecture (§ V.4) : « comme avant » n'était plus vrai pour la zone de la note (« 2A » ≠ « 20 ») ; « 20 » couvre
  désormais 2A et 2B dans `dans_departements`, comme « 97 » couvre l'outre-mer.*
- Hors chantier (autre chantier du lot) : les fins de contrat (`app/services/decp.py`, `app/routers/sourcing.py`).

**Preuve.** `test_recherche_departements_outre_mer_code_complet` (« 974 » ne garde plus le 971 ; « 2A », « 2B »
séparés ; « 97 » garde tout l'outre-mer ; « 6 » trouve « 06 »), `test_score_zone_outre_mer_et_corse`.

**Ce qui change pour le client.**
- Outre-mer : une recherche « 971 », « 972 », « 973 », « 974 » ou « 976 » ne montre plus les avis des autres
  départements d'outre-mer ; la zone de la note est juste pour une entreprise d'outre-mer.
- Corse : une entreprise qui a saisi « 2A » ou « 2B » dans « Ce que je cherche » voit les avis de son département
  « dans votre zone » (la note de ces avis monte). La recherche corse ne change pas. *Réunion (§ R.1) : vrai
  seulement après la réunion pour les avis du BOAMP (ils portaient « 20A » / « 20B ») ; et la recherche corse
  change : elle trouve enfin ces avis.*

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
| **Après** | Le repli est gardé tel quel (même débit, même remboursement). Chaque repli écrit UNE ligne dans le journal (`_journal_repli_a_venir`, `app/routers/sourcing.py:358`) : son motif (« DECP sans résultat », « DECP indisponible » ou « DECP en erreur »), les départements (codes de 2 ou 3 caractères), le nombre de fins de contrat trouvées, combien ont une durée lue et combien une durée estimée par type de contrat (*Relecture*, § V.6 : « lue » = un nombre de mois strictement positif rendu par l'IA, qui la lit dans l'objet de l'avis, non revérifié), le nombre d'erreurs de source, le sort de l'analyse (« débitée », « remboursée », ou « remboursée (repli en échec : …) ») et les références publiques des avis d'attribution du BOAMP (10 au plus). **Sans donnée personnelle** : ni utilisateur, ni organisation, ni adresse, ni mots tapés. Exemple : `repli payant « À venir » (BOAMP + IA) : motif=DECP indisponible ; départements=29 ; fins de contrat trouvées=3 (durée lue 1, durée estimée 2) ; erreurs de source=0 ; analyse débitée ; avis BOAMP=25-34232,25-10734,25-8460`. Niveau INFO, écrit en production (`LOG_LEVEL` vaut INFO par défaut, `app/core/config.py:41` ; la valeur posée dans Railway n'est pas vérifiée). |
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
- Prix, quotas, et la règle de débit et de remboursement du repli payant (débité s'il trouve, remboursé sinon). *Relecture
  (§ V.5)* : en outre-mer, il peut désormais trouver, donc débiter (avant : toujours remboursé) ; point 12 bis.
- Aucune IA ajoutée ; le robot de Mégalis, ses limites et son refus sans contournement ; un seul processus, aucun nouveau planificateur ; aucune nouvelle route de données, cloisonnement de la co-traitance intact.
- Les alertes lisent toujours 25 lignes par source et par recherche (*Relecture* : plus, au BOAMP, les avis repris par
  leur rectificatif, § V.1) ; le courriel ne donne aucune note sur 100.

### Relevé en passant, non corrigé (hors du périmètre de ce chantier)

- La répartition proposée partie par partie (`/api/sourcing/groupement`) tire le département du lieu d'exécution sur 2 chiffres (`app/routers/sourcing.py:191-198`) : outre-mer, elle cherche des partenaires dans « 97 ». Même défaut que le point 4 bis, sur une autre route.
- `app/services/agents/amont.py:_deps` coupe toujours à 2 caractères : c'est la veille, traitée à sa vague 1.
- La note de synergie inconnue est posée par la route (`app/routers/sourcing.py:1430`) parce que `app/sourcing/scoring.py` appartient à l'autre chantier ; `synergy_score` pourra lire `past_wins = None` lui-même quand ce fichier sera repris. *Réunion : toujours vrai, non
  repris (`synergy_score` sert aussi le produit acheteur ; § R.6).*

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

---

## Réunion des chantiers

Le chantier Sources (`29738fa`) et le chantier Services (`23ca5a7`), tous deux posés sur `0afc1ed`, réunis puis vérifiés
de bout en bout sur des données réelles. Fichiers touchés par la réunion : `app/sourcing/sources/boamp.py` (deux
fonctions, § R.1), `app/services/alerts.py` (une ligne de `_refs_du_marche`, § R.2), le contrat (ce fichier), le test
daté réuni (§ R.0), et les nouveaux `tests/test_moteur_lot1_reunion.py` et `tests/fixtures/moteur_lot1_reunion/`.
Aucun fichier de l'écran, aucun changement de base de données, aucune IA, aucun prix ni quota, robot de Mégalis
inchangé.

### R.0 La fusion

- `feat/produit-acheteur-collectivites` = `0afc1ed` (avance rapide), puis Sources (avance rapide, `29738fa`), puis
  Services (commit de fusion `5c6be5e`). Deux conflits, résolus bloc par bloc :
  - `tests/test_reorganisation_v1_relecture.py` : les deux chantiers avaient corrigé le même test daté
    (`test_compte_rendu_de_la_demonstration`, « 1/1 » trouvé dans la date « 21/10/2026 »), chacun à sa façon. Les deux
    corrections sont gardées ensemble : les dates sont retirées, puis « 1/1 » est cherché comme fraction isolée. Un
    vrai « 1/1 » reste détecté.
  - `docs/MOTEUR_LOT1.md` : les deux sections réunies telles quelles ; seuls le titre et l'introduction du chantier
    Services (7 lignes, les mêmes décisions que l'introduction commune) ne sont pas repris. Contrôle « aucune ligne
    perdue » : 0 ligne de la section Sources absente, 7 de Services (cette introduction).
- `app/sourcing/schemas.py`, touché par les deux chantiers, s'est fusionné sans conflit (4 champs de la fiche ;
  `past_wins` facultatif).
- Suite complète sur l'état fusionné, avant toute correction de la réunion : 2 235 tests, tous verts.

### R.1 La Corse au BOAMP : « 20A » et « 20B »

**Avant.** La note de décisions et les deux chantiers tenaient que la Corse « n'est pas touchée : « 2A » reste
« 2A » ». Vérifié sur l'API du BOAMP le 21/10/2026 (valeurs de `code_departement` des avis parus depuis le 01/09) :
le BOAMP écrit la Corse **« 20A »** (142 avis) et **« 20B »** (112 avis), jamais « 2A », « 2B » ni « 20 ». Donc, sur
`0afc1ed` comme après les deux chantiers :
- une recherche « 2A » ou « 2B » demandait `code_departement like "2A"` au BOAMP : **aucun avis**, toujours ;
- un avis corse portait « 20A » sur sa fiche : jamais « dans votre zone », et écarté par le filet de sécurité de toute
  recherche corse ;
- le repli payant de l'onglet « À venir » (avis d'attribution du BOAMP) ne trouvait rien en Corse.

**Après** (`app/sourcing/sources/boamp.py`). `formes_boamp` demande « 2A » **et** « 20A » (« 2B » et « 20B »), comme
il demandait déjà « 06 » et « 6 » ; `dept_canonique` ramène « 20A » / « 20B » à « 2A » / « 2B », la forme unique
d'Adjugo. Rien d'autre : « 20 » saisi seul ne couvre pas la Corse (il n'est pas une forme d'Adjugo, comme avant), un
code postal corse donne toujours « 20 » (on ne devine pas 2A ou 2B), et la DECP (fins de contrat), qui écrit « 2A »,
n'est pas concernée. *Relecture (§ V.4) : dans la zone de la note, « 20 » (le code postal) couvre 2A et 2B, comme
avant ; la requête au BOAMP d'une recherche « 20 » ne change pas.*

**Preuve.** `test_corse_les_avis_du_boamp_enfin_trouves_sous_2A_et_2B`, sur la recherche réelle du 21/10/2026 faite par
le code de la réunion (19 avis ouverts) : « 2A » rend les 13 fiches de Corse-du-Sud (dont 26-88364, rectifié par sa
version européenne 26-91505), « 2B » celles de Haute-Corse, chacune sous « 2A » ou « 2B », jamais « 20A » ; le
rectificatif de 26-95985 (« Au lieu de 30/10/2026 à 12h00, lire 02/11/2026 à 12h00 ») est lu ; la zone de la note est
« ok » pour qui cherche en « 2A » ; la requête du repli payant contient « 20B ». Sur `0afc1ed` : aucune carte. Sur la
fusion des deux chantiers sans cette correction : aucune carte non plus.

**Ce qui change pour le client.** Points 9 et 12 de la liste complète : les recherches corses montrent enfin les avis
du BOAMP ; le repli payant peut trouver des fins de contrat corses (et l'analyse est alors débitée, selon la règle
habituelle). *Ajouté à la réunion* : ce défaut n'était pas dans la note ; il a été trouvé en vérifiant « une recherche
en Corse » sur des données réelles. À valider par Eliot.

### R.2 Alertes : un rectificatif européen déjà envoyé n'est jamais renvoyé

**Avant (après les deux chantiers).** Le chantier Sources rattache un rectificatif au format européen à son avis
initial (une fiche, la référence de l'avis initial) ; le chantier Services écrit chaque référence avec sa source. Mais
la mémoire d'une alerte ne connaissait pas les références des rectificatifs : une alerte qui avait envoyé, avant le
lot, la carte du rectificatif européen (sous sa propre référence, par exemple 26-101544) aurait renvoyé, une fois, la
même procédure sous la référence de son avis initial (26-93829). Le chantier Sources l'avait relevé et renvoyé au
chantier des alertes (S.2).

**Après** (`app/services/alerts.py`, `_refs_du_marche`). Les références des rectificatifs rattachés à un avis sont
des références du même marché, comme celles des autres sources où il a été vu : « BOAMP|26-101544 » rejoint
« BOAMP|26-93829 » dans l'entrée du marché, et la forme nue d'avant le lot (« 26-101544 ») est reconnue. L'ordre de la
mémoire, sa borne de 500 marchés et la référence affichée (celle de l'avis) ne changent pas.

**Preuve.** `test_alerte_un_rectificatif_europeen_deja_envoye_n_est_jamais_renvoye` (avis réel 26-101544 du jeu du
chantier Sources, rendu seul par la recherche ; mémoire d'avant le lot `["26-101544"]`) : rien n'est renvoyé, et la
mémoire devient `["BOAMP|26-93829 + BOAMP|26-101544 + 26-101544"]`. Sur la fusion des deux chantiers sans cette
correction : le marché est renvoyé. Sur `0afc1ed` : la mémoire reste `["26-101544"]`.

**Ce qui change pour le client.** Point 19 : le renvoi « une seule fois, à la mise en ligne » annoncé en S.2 n'a plus
lieu.

### R.3 Vérifications de bout en bout, sur des données réelles

Toutes sans réseau pendant les tests. Données réelles lues en GET le 21/10/2026, avec l'en-tête honnête d'Adjugo, une
requête toutes les 1,2 s au plus : **17 requêtes, toutes à l'API publique du BOAMP** (OpenDataSoft) ; aucune à Mégalis
(sa page réelle du 21/10 vient du chantier Sources), aucune à la DECP (ses réponses réelles viennent du chantier
Services). Détail : 7 requêtes envoyées **par le code de la réunion lui-même** (`BoampSource.search`, trois recherches :
« voirie » dans le 29, « 971 » et « 974 », « 2A » et « 2B »), gardées telles quelles avec leurs réponses ; 10 lectures
ciblées (annulations parues depuis le 01/09 et rectificatifs qui visent les mêmes avis, l'avis 26-83249 et ses suites,
les avis de voirie en Bretagne, l'outre-mer et la Corse, les valeurs de `code_departement`). Les jeux d'essai
(`tests/fixtures/moteur_lot1_reunion/`) ne gardent du corps d'un rectificatif ou d'une annulation que son bloc
« rectificatif » ou « annulation » (contacts de l'acheteur retirés) ; le corps eForms des avis européens, qui porte des
contacts et que le code ne lit pas, est retiré. Contrôle : aucune adresse électronique ni aucun numéro de téléphone dans
ces fichiers.

| Demandé | Résultat | Preuve |
|---|---|---|
| Recherche Mégalis avec une date d'octobre à décembre | Les 10 consultations de la page réelle ont leur date (« Oct. », « Nov. », « Déc. ») ; dans l'alerte « voirie » 29, les deux consultations finistériennes partent avec « clôture 2026-12-07 » (242387) et « clôture 2026-11-19 » (242908) | `test_megalis_page_reelle_toutes_les_dates_limites_lues`, `test_megalis_recherche_complete_sur_la_page_reelle` (Sources) ; `test_alerte_reelle_contient_les_marches_que_sa_note_cachait` |
| Un avis BOAMP rectifié puis annulé | 26-83249 (collège de Baie-Mahault, 971), limite le 16/09/2026 : le 01/09, affiché avec son rectificatif 26-84145 (28/08) rattaché et sa date inchangée (le rectificatif ne parle pas de la date limite) ; le 15/09, jour de son annulation 26-89465, retiré ; témoin : sans l'annulation, le même jour, il serait affiché. Sur `0afc1ed` : rectificatif jamais rattaché, avis annulé affiché | `test_avis_rectifie_reste_affiche_avec_son_rectificatif`, `test_avis_rectifie_puis_annule_retire` (par la route `/api/sourcing/search`) |
| Une recherche en outre-mer (974 ≠ 971) | Recherche réelle « 971 » et « 974 » (43 avis) pour une entreprise de La Réunion (97400) : 974 « dans votre zone », 971 hors zone (avant : tout l'outre-mer dans la zone) ; « 974 » seul ne rend que des avis du 974 ; le filet de sécurité, sur ces avis réels, garde le 974 et écarte 971, 972, 973. Les suites sur les mêmes avis : 26-99092 (Mayotte et La Réunion) annulé le 14/10 par 26-99478, retiré (sa relance 26-101552 reste) ; 26-92595 repoussé du 23/10 au 30/10 ; 26-82275 repoussé deux fois (30/09, 07/10, 21/10) et repris ; 26-76317 repris par sa version européenne 26-94574 | `test_outre_mer_974_n_est_plus_971_sur_la_recherche_reelle` ; fins de contrat : `test_fins_de_contrat_sur_le_code_complet_974_ne_voit_plus_971_corse_et_metropole_inchangees`, `test_onglet_a_venir_demande_le_code_complet_et_note_la_zone_d_outre_mer` (Services, vraies lignes DECP) |
| Une recherche en Corse | § R.1 : 19 avis du BOAMP trouvés (avant : 0) ; fins de contrat corses (DECP, « 2A ») inchangées | `test_corse_les_avis_du_boamp_enfin_trouves_sous_2A_et_2B` ; Services, test ci-dessus |
| Une alerte qui contient maintenant un marché qu'elle cachait | Alerte « Voirie Finistère » telle que l'écran la crée, entreprise qui a enregistré « Ce que je cherche » (seuil 75) : 7 marchés réels (5 BOAMP, 2 Mégalis) notés de 60 à 67 ; avant, le courriel n'était pas envoyé du tout ; après, un courriel de 7 marchés, chaque référence avec sa source | `test_alerte_reelle_contient_les_marches_que_sa_note_cachait` (par l'appel programmé `run_tender_alerts`, courriel intercepté) |
| Une adresse de la veille refusée sans débit | `/api/amont/scan`, `/analyze-upload`, `/analyze-text`, activation `/auto` : 404, ni lecture, ni IA, ni débit ; rejoué sur l'état réuni | `test_adresses_de_la_veille_masquee_refusent_sans_debiter` (Services) |
| Un repli noté | Une ligne de journal par repli, sans donnée personnelle (avis d'attribution réels du BOAMP, IA simulée) ; rejoué sur l'état réuni. La requête du repli corse demande désormais « 20A » / « 20B » (§ R.1) | `test_repli_payant_note_dans_le_journal_sans_donnee_personnelle` (Services) ; `test_corse_les_avis_du_boamp_enfin_trouves_sous_2A_et_2B` |
| L'outil de mesure sur une liste d'essai | Rejoué sur l'état réuni ; et lancé à la main comme Mathys le fera, hors du dépôt : collecte sur la réponse réelle de la DECP figée par Services (titulaire au numéro fictif, 8 marchés sur 12 mois), puis `python scripts/mesure_rappel.py mesurer <dossier> --etiquette essai-reunion` : « Rappel entre 0 % et 62 % sur 8 marchés : 5 restent à vérifier » ; un dossier dans le dépôt est refusé | `test_mesure_du_rappel_rejouable_sans_reseau`, `test_mesure_du_rappel_refuse_le_depot_et_suit_la_regle_de_la_recherche_boamp` (Services) |
| Démo inchangée | 194 tests de la démo verts (`tests/test_demo_*.py`, dont `test_demo_sans_cout.py`) | § R.5 |

### R.4 Ce que les données réelles ont montré en plus

Formes de rectificatif **observées à la réunion** (21/10/2026), en plus de celles du chantier Sources (S.2) :

| Forme réelle | Lecture du code | Avis |
|---|---|---|
| « La date limite de remise des offres est fixée au 30 octobre 2026 à 12H00. » | 30/10/2026 (une seule date, avec son année) | 26-99887 (de 26-92595, 971) |
| « La date limite de réception des plis (candidatures et offres) est reportée et fixée au 08 octobre 2026. » | 08/10/2026 | 26-91985 |
| « … la date limite de remise des offres est reportée au lundi 05 octobre 2026 … » | 05/10/2026 | 26-92160 |
| Deux rubriques qui donnent la même nouvelle date (« Date et heure limites de réception des plis » et « date limite de remise des offres ») | 28/09/2026 | 26-90393 |
| « La date limite de réception des offres, initialement prévue le 2 novembre 2026 à 12h00, est reportée au 16 novembre 2026 à 12h00. » | **non lue** (deux dates sans « au lieu de … lire … ») : « limite non précisée » | 26-102208 (de 26-93488, 2A) |
| « … date limite de remise des offres … reportée au 28 septembre 2026 … une visite du site est organisée le 15 septembre 2026 … » | **non lue** (deux dates) ; le rectificatif suivant (26-92160, « reportée au lundi 05 octobre 2026 ») fixe la date | 26-89432 |
| Rectificatif européen (eForms) **sans** date limite structurée ; son corps dit « Remise des offres : Au lieu du 21/10/2026 à 12h00 … Lire 04/11/2026 à 12h00 » | **non lue** : « limite non précisée » (le corps eForms n'est pas lu) | 26-101691 (de 26-95108, 971) |
| « Lire 28/06/2024 à 12h00 au lieu de 28/06/2202 » (ordre inversé, sans dire de quelle date il s'agit) | **non lu** : l'avis garde sa date du 28/06/2202 | 24-65513 (de 24-61932, 971) |
| « … Le marché est annulé » écrit dans un **rectificatif** | pas une annulation : l'avis reste affiché jusqu'à l'avis d'annulation (26-89465) | 26-84145 (de 26-83249) |
| Rectificatif de la durée et des variantes | ne parle pas de la date limite : la date reste | 26-86829 |

« Non lue » suit la règle du lot : jamais l'ancienne date, jamais une date devinée. Trois de ces formes pourraient
être lues sans deviner, chacune par une règle nouvelle, à mesurer d'abord (je ne les ai pas ajoutées : ce ne sont pas
des défauts du lot, et chacune demande une décision) :
- « initialement prévue le X … reportée au Y » : lire Y ;
- le rectificatif européen sans date structurée : lire son « ChangeDescription » avec la règle « Au lieu de … lire … »
  déjà en place ; sans cela, 26-95108, ouvert jusqu'au 04/11, sort de la recherche dès le 22/10 (comme avant le lot :
  la recherche ne voit l'avis initial que jusqu'à son ancienne date) ;
- « Lire X au lieu de Y » quand Y est la date limite de l'avis : 24-61932, avis de 2024 dont la date du BOAMP est
  « 28/06/2202 » (faute de frappe à la source), s'affiche comme ouvert dans toute recherche « travaux » en Guadeloupe,
  avant comme après le lot.

**La fusion Mégalis et BOAMP, vérifiée sur deux cas réels** (le chantier Sources l'avait vérifiée sur un avis BOAMP
construit). Le 21/10/2026, deux consultations de la page Mégalis « voirie » sont aussi au BOAMP, avec le même objet et
la même date limite : « Antenne voirie des Boëdriers - Restructuration du site » (Mégalis 241593, BOAMP 26-95384) et
« Port à sec de Saint-Malo – Longrines et travaux de VRD » (Mégalis 242491, BOAMP 26-99992). **Aucune ne fusionne** :
l'acheteur n'est pas écrit de la même façon (« RENNES METROPOLE (35000 - Rennes ) » contre « Rennes Métropole » ;
« SPL BRETAGNE PLAISANCE (35400 - SAINT-MALO) » contre « BRETAGNE PLAISANCE »). Elles restent deux cartes, comme
avant le lot. Le nettoyage du nom de l'organisme Mégalis est le point 10 de la note (avec la partie écran) ; il ne
suffira pas seul (accents, « SPL ») : une règle de fusion sur l'acheteur est à décider, avec son risque de fausse
fusion. La phrase du point 2 de la liste complète le dit.

### R.5 Vérifications

- **Nouveaux tests** : `tests/test_moteur_lot1_reunion.py`, 8 tests, sans réseau. **Les 8 échouent sur `0afc1ed`**
  (export `git archive`, nouveaux tests et jeux d'essai copiés), chacun sur le défaut qu'il couvre : aucune carte en
  Corse ; 971 « ok » pour une entreprise de La Réunion ; rectificatif de 26-83249 jamais rattaché ; 26-83249 affiché le
  jour de son annulation ; aucun courriel pour l'alerte « voirie » ; mémoire restée `["26-101544"]` ; fonctions de
  département absentes ; contrat absent. **Sur la fusion des deux chantiers sans les corrections de la réunion**
  (`5c6be5e`), 4 échouent : la Corse (aucune carte), le rectificatif européen (renvoyé), la règle des départements
  (« 20A ») et le contrat ; les 4 autres passent (ces défauts étaient déjà corrigés par les chantiers).
- **Suite complète** sur l'état réuni (`TZ=UTC`, base SQLite d'essai, Python 3.12 depuis `requirements.lock`) :
  **2 243 tests, tous verts** (2 205 de la production, 17 Sources, 13 Services, 8 réunion).
- **Démo** : 194 tests (`tests/test_demo_*.py`, dont `test_demo_sans_cout.py`), tous verts.
- **Aucun changement de base de données** dans tout le lot : rien à vérifier sur Postgres (la nouvelle mémoire des
  alertes tient dans la colonne JSON existante).

### R.6 Ce qui reste, et ce que j'ai vu en passant

- **À rejouer à la sortie du lot** : les 5 contrôles de l'étude (§ 6.2), sur des avis encore ouverts ce jour-là ; et la
  mesure de départ du rappel, avant la mise en ligne, avec la liste de Mathys (`collecter`, puis
  `mesurer --etiquette avant-lot1`).
- **À valider par Eliot** : la correction corse (§ R.1), ajoutée à la réunion.
- **Formes non lues, à décider** : les trois du § R.4 ; la fusion Mégalis et BOAMP par l'acheteur.
- **Non vérifié** (inchangé) : les mois de janvier à septembre sur une page Mégalis réelle ; PLACE ; les formes de
  rectificatif marquées « non vérifié » en S.2.
- **Vu, hors du lot** : le produit acheteur lit un `past_wins` inconnu comme 0 (« capacité prouvée » fausse, pas
  « inconnue » : `app/services/agents/sourcing_acheteur.py:89-90`, `:140`) ; `scoring.synergy_score` dit encore
  « Aucun marché public gagné trouvé » pour un compte inconnu, hors de la route `/api/sourcing/cotraitants` (seul le
  produit acheteur l'appelle aussi) ; la répartition proposée (`/api/sourcing/groupement`) et la note de synergie
  coupent encore les départements à 2 chiffres (outre-mer) ; Mégalis aussi (`atexo.py`, sans effet : seuls 22, 29, 35
  et 56 y sont cherchés) ; un département tapé « 20A » est ignoré par la recherche (seuls « 2A » et « 2B » sont
  des formes d'Adjugo) ; l'historique d'un acheteur (`app/sourcing/sources/buyer.py`, ses « zones ») montre les codes
  du BOAMP tels quels (« 20A », « 6 »).

---

## Relecture

Quatre relectures de l'état réuni (`ef5c096`) : lecture des sources, alertes et services, suite et production, plus
une remarque sur l'écran. **Dix remarques, toutes reproduites, aucune rejetée** : sept corrigées dans le code (V.1 à
V.4, V.6, V.7, V.10), une dans un test (V.9), deux dans ce contrat seulement (V.5, code juste ; V.8, fichier de
l'écran, après la 2b). Base : `feat/produit-acheteur-collectivites` toujours à `0afc1ed` (rien à fusionner).

Fichiers touchés : `app/sourcing/sources/boamp.py` (relecture des avis initiaux, lecture des rectificatifs, nombre de
lignes lues), `app/sourcing/base.py` (`ResultatsSource`, `lignes_lues`, Corse « 20 »), `app/sourcing/search.py`
(« Charger plus »), `app/services/renewal.py` (durée lue), `app/services/alerts.py` (adresse confirmée, référence de
« Tester ») ; tests : nouveau `tests/test_moteur_lot1_relecture.py` (9 tests) et `tests/fixtures/moteur_lot1_relecture/`,
simulations de l'API adaptées à la nouvelle relecture dans `tests/test_moteur_lot1_sources.py` et
`tests/test_moteur_lot1_reunion.py`, trois assertions de la référence et le test hebdomadaire dans
`tests/test_moteur_lot1_services.py`, une assertion corse dans `tests/test_moteur_lot1_sources.py`. Aucun fichier de
l'écran, aucun changement de base de données, aucune IA, aucun prix ni quota, robot de Mégalis inchangé.

**Jeux d'essai** (réels, sans réseau pendant les tests) : la recherche « travaux » du 21/10/2026 faite par le code de
la réunion (3 requêtes à l'API du BOAMP, en-tête AdjugoBot, lues par la relecture ; un nom et une adresse électronique
de contact d'un rectificatif retirés, corps réduit au bloc « rectificatif ») ; l'avis 26-100294 et son rectificatif
26-100865, relus en **une** requête GET au BOAMP le 21/10/2026 (en-tête AdjugoBot ; contacts de l'acheteur retirés).
Aucune autre requête réseau.

### V.1 La relecture des avis initiaux ne reprend que ceux dont la date publiée est passée

| | |
|---|---|
| **Avant** | La relecture (S.2, « Une requête encore ») relisait tout avis rectifié dont la nouvelle date n'est pas passée, même encore ouvert sous sa date publiée : il était déjà trouvé par la requête principale, sur sa propre page. Recherche réelle « travaux » sans département : 64 avis à relire, 50 relus (`a_relire[:50]`, sans ligne de journal), dont 35 encore ouverts sous leur ancienne date ; **75 cartes pour une limite de 25** (alertes ; 0afc1ed : 25), 65 pour 15 (écran). Les 14 non relus comptaient au moins 6 avis dont la date publiée est passée, exactement ceux que le point 2 doit reprendre, dont 26-82275 (30/09, repoussé au 07/10 puis au 21/10). Le contrat disait le contraire (S.2 : « pour retrouver un avis dont seule l'ancienne date est passée » ; « les alertes lisent toujours 25 résultats »). |
| **Après** | `boamp._avec_suites` : la relecture demande `(idweb in (…) AND datelimitereponse < date'aujourd'hui') OR (annulations qui les visent)`, et écarte après lecture toute ligne encore ouverte (même si l'API ne bornait pas) ; tous les avis visés sont demandés, 100 au plus (`_MAX_RELUS`, autant que de rectificatifs lus) ; au-delà, une ligne de journal dit combien ne sont pas relus ; une autre si la réponse atteint son plafond. Même recherche : **41 cartes** pour 25 lignes (25 + 16 repris, dont 26-82275 au 21/10), aucune des 35. |
| **Preuve** | `test_relecture_ne_reprend_que_les_avis_dont_la_date_publiee_est_passee` (réponses réelles ; la ligne réelle de 26-82275 vient du jeu de la réunion) ; `test_relecture_plafonnee_jamais_en_silence` (120 avis visés, construits : 100 demandés, « 20 non relus » au journal). Les deux échouent sur `0afc1ed` (aucune relecture) et sur `ef5c096` (les 35 repris ; 50 demandés). Les simulations des tests Sources et réunion acceptent la nouvelle forme ; `test_outre_mer_974_n_est_plus_971_sur_la_recherche_reelle` vérifie que la requête est celle du 21/10, bornée. |
| **Pour le client** | Point 3 bis de la liste. Première page : les seuls avis repris sont ceux qu'aucune page ne montrerait ; plus de doublon d'une page à l'autre. Alertes : 25 lignes, plus ces avis repris. Une recherche très large peut compter plus de 100 avis à relire : les plus anciens rectificatifs ne sont alors pas relus (dit au journal), comme une page de résultats plus loin. |
| **Non vérifié** | L'opérateur `<` sur `datelimitereponse` avec `date'…'` n'a pas été envoyé au BOAMP réel (aucune requête de plus) ; `>=` sur ce champ l'est à chaque recherche. Si l'API l'ignorait, le filtre après lecture rend le même résultat ; si elle refusait la requête, la relecture est perdue (journal « avis initiaux des rectificatifs non relus »), la recherche non. |

### V.2 « Charger plus » se juge sur les lignes reçues, pas sur les fiches

| | |
|---|---|
| **Avant** | `search.py` calculait `has_more` sur le nombre de fiches rendues par les sources, après le rattachement des suites : une page du BOAMP qui perd un avis annulé ou qui réunit un avis et son rectificatif européen n'était plus « pleine ». Recherche réelle 971 + 974 (BOAMP seul), 15 par page, par la route de l'écran : `0afc1ed` (15, oui) (15, oui) (13, non), avec l'avis annulé 26-99092 ; `ef5c096` (16, oui) (14, **non**) : les 13 avis ouverts de la page 3 n'étaient plus atteignables. Aucune ligne du contrat n'en parlait. |
| **Après** | `BoampSource.search` rend un `ResultatsSource` (liste de fiches + `lignes_lues`, le nombre de lignes reçues de l'API pour la page) ; `search.py` additionne `base.lignes_lues(…)` des sources (une autre source : son nombre de fiches, inchangé). La garde des liens assainit la liste en place, pour garder ce nombre. Même recherche : (16, oui) (14, oui) (13, non), 26-99092 retiré, aucun avis montré deux fois. |
| **Preuve** | `test_charger_plus_reste_propose_quand_une_page_perd_un_avis_annule` (route `/api/sourcing/search`, offsets 0, 15, 30) ; échoue sur `0afc1ed` (26-99092 affiché) et sur `ef5c096` (page 2 sans suite). |
| **Pour le client** | Rien de nouveau par rapport à la production : « Charger plus » reste proposé tant que la source a rempli sa page. |

### V.3 Un rectificatif qui cite la date limite comme repère ne la change pas

| | |
|---|---|
| **Avant** | `_CONCERNE_DELAI` était cherché dans tout le texte : 26-100865 (16/10/2026), seul rectificatif de 26-100294 (limite le 23/10/2026), ne change que le délai des questions (« … 10 jours calendaires avant la date limite fixée pour la réception des offres », lire « 7 jours ») ; il était lu « concerne la date, date non lue » : « limite non précisée » au lieu du 23/10. Régression par rapport à la production, contraire à la table de S.2 (« questions … la date de l'avis reste »). |
| **Après** | `_REPERE_DU_DELAI` : un passage « avant / après la date limite (fixée pour / de) la remise, réception, dépôt ou transmission des offres, plis… » (ou « avant la DLRO ») est retiré du texte avant de chercher s'il parle de la date limite. Une rubrique qui change la date ET cite ce repère pour un autre délai donne toujours la nouvelle date. La règle « Rubrique : X » seule, proposée par la relecture, n'est pas prise : 26-102243 porte une rubrique « Section 3 - Procédure » qui change la date dans son corps ; la lire sur l'intitulé seul garderait l'ancienne date. |
| **Preuve** | `test_rectificatif_du_delai_des_questions_garde_la_date_de_l_avis` (les deux lignes réelles : date du 23/10, rectificatif listé, rien de « non lu » ; cas construit sur ces textes : la nouvelle date reste lue). *Contre-relecture* : comparaison sur les **127 rectificatifs réels** distincts des jeux d'essai du dépôt (144 lignes de `tests/fixtures/**/*.json`, hors annulations, dont les 100 suites de la recherche « travaux » de la relecture ; 119 avec un corps `infosRectif`, 136 éléments ; 8 au format européen) : sans la règle du repère, une seule lecture change, celle de 26-100865. Rejouable : `test_comparaison_rejouable_sur_les_rectificatifs_reels_des_jeux_d_essai` (`tests/test_moteur_lot1_contre_relecture.py`). Le nombre « 173 » écrit ici auparavant ne se retrouvait pas dans le dépôt (C.2). |
| **Non vérifié** | *Contre-relecture* : un texte qui nomme la date limite seulement derrière « avant / après » et cite une date (« … offres à déposer avant la date limite de remise des offres fixée au 05/11/2026 ») ; jamais observé sur les 127. Il n'est plus écarté par cette règle : C.1. |
| **Pour le client** | Point 5 de la liste : la carte garde sa date (comme en production), le rectificatif est listé dans les données. |

### V.4 Corse : un code postal « 20… » couvre 2A et 2B

| | |
|---|---|
| **Avant** | Pour une entreprise au code postal corse sans département saisi, les avis corses du BOAMP passaient de « dans votre zone » (`0afc1ed` : « 20A »[:2] == « 20 ») à « Hors zone (2A) », 33 points de moins (26-101468, 26-101638, 26-100536 ; codes postaux 20090 et 20200). S.4 et R.1 disaient « comme avant ». |
| **Après** | `base.dans_departements` : « 20 » couvre « 2A » et « 2B », comme « 97 » couvre l'outre-mer. On ne devine toujours pas 2A ou 2B ; « 2A » saisi reste distinct de « 2B » ; la requête au BOAMP d'une recherche « 20 » ne change pas. Le test Sources qui disait « 2A » hors zone pour le code postal 20000 est corrigé : il décrivait un avis écrit « 2A », que seul le lot produit. |
| **Preuve** | `test_corse_entreprise_au_code_postal_corse_voit_les_avis_corses_dans_sa_zone` (avis réels) ; échoue sur `0afc1ed` (l'avis garde « 20A ») et sur `ef5c096` (« partiel »). |
| **Pour le client** | Comme en production (point 9 de la liste). |

### V.5 Outre-mer : le repli payant peut désormais trouver, donc débiter

| | |
|---|---|
| **Avant** | `0afc1ed` coupait le département à 2 caractères : le repli demandait `code_departement like "97"` au BOAMP. Lu par la relecture le 21/10/2026 (avis d'attribution, fenêtre du repli) : « 97 » rend 0 avis, « 974 » en rend 2 042. Le repli ne trouvait donc jamais rien en outre-mer, et l'analyse était toujours remboursée. Le contrat disait « le repli payant débite et rembourse comme avant ». |
| **Après** | Code inchangé (la recherche sur « 974 » est juste, point 4 bis). Rejoué sans réseau sur 8 avis réels du 974 (DECP sans résultat, IA simulée), par `/api/sourcing/renewals` : `0afc1ed` demande `["97"]`, 0 fin de contrat, rien de débité ; après le lot, `["974"]`, 8 fins de contrat, analyse débitée. Second effet : la DECP ne rend plus les fins de contrat des autres départements d'outre-mer ; quand le département demandé n'en a aucune, le repli payant part. |
| **Preuve** | Reproduction de la relecture, rejouée ici sur `0afc1ed` et sur cet état (`DEPARTEMENTS_DEMANDES_AU_BOAMP = [['97']] … ANALYSES_DEBITEES = 0` contre `[['974']] … FINS_DE_CONTRAT = 8`, débit). Pas de test : rien n'est corrigé. |
| **Pour le client** | Point 12 bis de la liste. **À valider par Eliot**, avec la Corse (point 12) : garder ce débit, ou rembourser le repli en Corse et en outre-mer jusqu'à l'annonce du crédit avant le clic (partie écran, point 12 de la note). |

### V.6 « Durée lue » : seulement un nombre de mois rendu par l'IA

| | |
|---|---|
| **Avant** | `renewal.detect_renewals` posait `estimated = duree is None`, puis remplaçait par la durée par défaut toute durée qui n'est pas un nombre positif, sans la dire estimée : une IA qui répond 0 ou « 36 » donnait « durée 36 mois (réelle) » à l'écran et « durée lue » au journal du repli (point 8), la mesure que la décision 12 doit trancher. Défaut antérieur au lot. |
| **Après** | Une durée n'est lue que si l'IA rend un nombre strictement positif (pas un booléen) ; sinon la durée par défaut du type de contrat, **estimée**. Une durée lue reste celle que l'IA dit lire dans l'objet de l'avis (non revérifiée). |
| **Preuve** | `test_duree_lue_seulement_si_l_ia_rend_un_nombre_de_mois` (vrais avis d'attribution du 29 ; réponses 0, « 36 », null, 24, et un booléen) ; échoue sur `0afc1ed` et `ef5c096` (`[False, False, True]`). |
| **Pour le client** | Point 12 ter : dite estimée au lieu de « (réelle) » dans ces cas. *Écran* : « (durée estimée selon le type de contrat) », ou « (durée estimée par défaut, type de contrat inconnu) » sans type (36 mois). |

### V.7 Alertes : jamais vers une adresse non confirmée, rien de perdu

| | |
|---|---|
| **Avant** | `run_tender_alerts` servait tout compte qui a une adresse, confirmée ou non. Antérieur au lot, mais la décision 11 multipliait ces envois : alerte réelle « voirie » 29, compte non confirmé : `0afc1ed` 0 courriel (marchés sous le seuil, mais marqués « déjà vus », donc jamais envoyés ensuite), `ef5c096` 1 courriel de 7 marchés vers l'adresse non prouvée. La vague 2b applique déjà la règle « un compte non confirmé ne fait pas écrire Adjugo à un tiers » aux invitations. |
| **Après** | Joignable = adresse **confirmée** (`User.email_verified`), dans le choix des alertes qui marquent « déjà vu » et à l'envoi. Un compte non confirmé n'est pas servi, et ses marchés ne sont pas marqués : ils partent au premier passage après la confirmation. Comptes d'avant la vérification des adresses : confirmés par la migration `j4k5l6m7n8o9`. Un membre d'équipe créé par son administrateur confirme son adresse comme tout compte (sans quoi il ne peut déjà pas lancer d'analyse). « Tester » une alerte n'envoie rien : inchangé. |
| **Preuve** | `test_alerte_jamais_vers_une_adresse_non_confirmee_rien_de_perdu` (marchés réels ; non confirmé : 0 courriel, mémoire vide ; confirmé : 1 courriel de 7 marchés) ; échoue sur `0afc1ed` (mémoire marquée) et sur `ef5c096` (courriel envoyé). |
| **Pour le client** | Point 16 bis. **À valider par Eliot** (la relecture proposait de lui soumettre la règle ; elle est en place, son retrait tient en deux lignes de `alerts.py`). |

### V.8 La bulle « Mes alertes » parle encore d'un seuil

| | |
|---|---|
| **Avant** | `app/static/app.html` (1576 sur `0afc1ed`, 1615 sur la 2b) : « Recevez par email les nouveaux marchés qui vous correspondent (au-dessus de votre seuil de compatibilité) », traduite dans `i18n.js`. Après la décision 11, aucun seuil n'écarte plus rien ; ni la liste du client ni les points 10 à 13 ne le prévoyaient. |
| **Après** | Rien dans le code (fichier de l'écran, vague 2b en cours). Ajouté à la partie écran du lot, après la 2b : bulle à corriger (proposition : « Recevez par email les nouveaux marchés de cette recherche, 10 au plus par alerte, les autres comptés »), traductions comprises. |
| **Preuve** | Lu dans `app.html` de `0afc1ed` et de `deploy/reorga-v2b` (`52e0d59`). |
| **Pour le client** | Point 17 bis : jusqu'à la partie écran, la bulle dit le contraire du comportement. |

### V.9 Le test hebdomadaire ne dépend plus du changement d'heure

| | |
|---|---|
| **Avant** | `test_hebdomadaire_reellement_applique` posait `last_run = maintenant - 7 jours` en temps absolu, alors que la règle compte en jours de Paris : chaque automne, du 25/10 au 01/11 entre 22 h et 23 h UTC, 7 × 24 h ne font que 6 jours de Paris, et le test échouait. |
| **Après** | Le test pose `last_run` à midi, heure de Paris, 2, 1 et 7 jours de Paris avant `jour_paris()` ; le code de l'alerte ne change pas (la règle « 7 jours de Paris » est juste). |
| **Preuve** | Instant figé (greffon de la relecture) : ancien test, 26/10/2026 22:30 UTC : échec ; 21/10 10:00 : vert. Nouveau test vert le 26/10 22:30, le 25/10 22:30, le 01/11 22:45, le 29/03 22:30 (passage à l'heure d'été) et le 21/10 10:00. |
| **Pour le client** | Rien. |

### V.10 « Tester » une alerte rend la référence de l'avis, comme avant

| | |
|---|---|
| **Avant** | Depuis le point 6 c, `fresh[].ref` valait « BOAMP\|26-… » (ou « Mégalis Bretagne\|242387 ») : `POST /api/saved-searches/{id}/run` le rendait tel quel, changement d'API non listé (l'écran ne lit que `new_matches`). |
| **Après** | `ref` = la référence de l'avis (ou sa clé de fusion), comme avant ; la forme « SOURCE\|référence » ne sert qu'à la mémoire `last_seen_refs`. Les trois tests Services qui lisaient `ref` lisent `(source, ref)`. |
| **Preuve** | `test_tester_une_alerte_rend_la_reference_nue` (deux marchés, dont un sous le seuil : les deux, références nues) ; échoue sur `0afc1ed` (un seul marché) et sur `ef5c096` (« BOAMP\|26-90336 »). |
| **Pour le client** | Rien (API inchangée par rapport à la production). |

### V.11 Vérifications

- **Les 9 nouveaux tests** (`tests/test_moteur_lot1_relecture.py`) échouent tous sur `0afc1ed` et sur `ef5c096` (exports
  `git archive`, nouveaux tests et jeux d'essai copiés, réseau coupé par un greffon), chacun sur le défaut qu'il couvre :
  voir les preuves ci-dessus ; le test du contrat échoue faute de cette section.
- **Suite complète** sur cet état (`TZ=UTC`, base SQLite d'essai, Python 3.12 depuis `requirements.lock`) : **2 252
  tests, tous verts** (2 243 de la réunion, dont 5 adaptés, et les 9 nouveaux).
- **Aucun changement de base de données** : rien à vérifier sur Postgres (`users.email_verified` existe depuis juin).
- **Fusion à venir avec la 2b** : `app/services/alerts.py` est touché des deux côtés (la 2b : rappels d'invitation et
  `_comptes_non_confirmes` ; ici : `run_tender_alerts` et `run_one_saved_search`) ; à résoudre bloc par bloc.

### V.12 Ce qui reste, et ce que j'ai vu en passant

- **À valider par Eliot** : V.5 (outre-mer, repli payant) avec R.1 (Corse) ; V.7 (alertes et adresse non confirmée).
  *Décidé le 22/10 : (b) pour les deux (§ « Décisions d'Eliot »).*
- **Partie écran, après la 2b** : la bulle « Mes alertes » (V.8), en plus des points 10 à 13 de la note. *La bulle est
  corrigée dès le 22/10 (§ « Décisions d'Eliot ») ; les points 10 à 13 restent à la partie écran.*
- **Vu, non corrigé** : une recherche « 20 » (forme que le formulaire accepte) demande « 20 » au BOAMP, qui n'écrit
  la Corse que « 20A » / « 20B » : elle ne trouve rien, comme en production ; la relecture des avis initiaux ne porte
  pas le type de marché (un avis SERVICES peut être relu pour une recherche TRAVAUX ; le filet de `search.py` le retire,
  rien ne s'affiche).

---

## Contre-relecture

Une contre-relecture de l'état relu (`f86e510`). **Deux remarques mineures, toutes deux reproduites, aucune
rejetée** : une corrigée dans le code (C.1), une dans ce contrat, avec un test qui la rend rejouable (C.2). Base :
`feat/produit-acheteur-collectivites` toujours à `0afc1ed` (rien à fusionner).

Fichiers touchés : `app/sourcing/sources/boamp.py` (lecture du texte d'un rectificatif : `_lire_texte`,
`_DATE_ACCOLEE`, `_dates_accolees`, `_lire_element`) ; nouveau `tests/test_moteur_lot1_contre_relecture.py`
(3 tests) ; ce contrat (introduction, point 5 de la liste, table de S.2, V.3). Aucun jeu d'essai ajouté, aucune
requête réseau ; aucun fichier de l'écran, aucun changement de base de données, aucune IA, aucun prix ni quota, robot
de Mégalis inchangé.

### C.1 La date limite nommée derrière « avant » : un rectificatif qui la change n'est jamais écarté

| | |
|---|---|
| **Avant** | La règle du repère de V.3 (`_REPERE_DU_DELAI`) retirait du texte tout passage « avant / après la date limite de remise des offres… » avant de chercher s'il parle de la date limite. Un rectificatif qui change la date en ne la nommant que dans un tel passage était lu « ne concerne pas » : la carte gardait l'**ancienne** date. Reproduit sur `f86e510` : « Rubrique : Délais, Au lieu de : offres à déposer avant la date limite de remise des offres fixée au 21/10/2026 à 12h00, lire : … fixée au 05/11/2026 à 12h00 » → `{"concerne": False, "date": None}` ; « Les offres devront être déposées avant la date limite de réception des offres fixée au 05/11/2026 à 12h00 » → `(False, None)`. Règle neutralisée (`ef5c096`) : `(True, "2026-11-05")`. Pas une régression par rapport à la production (`0afc1ed` ne lit aucun rectificatif), mais contraire à « jamais l'ancienne date » pour une forme jamais observée. |
| **Après** | La règle du repère n'écarte plus un rectificatif que si son texte ne cite **aucune date** (26-100865 : un autre délai, compté en jours). Si la date limite n'y est nommée que comme repère et que le texte cite une date, il **concerne** la date limite. La date n'est lue que si elle est **accolée** à la date limite (« … des offres fixée / prévue / reportée / repoussée / arrêtée / portée au / le [jour] 05/11/2026 » ou « 5 novembre 2026 »), dans la partie « lire » s'il y en a une (« Au lieu de … lire … », ou le champ `lire`) : une seule date accolée, avec son année, sinon « non précisée ». Jamais l'ancienne date, jamais la date d'un autre délai : « questions au plus tard le 16/10/2026, soit 7 jours avant la date limite de réception des offres » donne « non précisée », pas le 16/10. Un texte qui nomme la date limite hors d'un repère est lu exactement comme avant. |
| **Preuve** | `test_rectificatif_qui_nomme_la_date_limite_derriere_avant_n_est_jamais_ecarte`, sur l'avis réel 26-100294 (limite le 23/10/2026) et des textes construits à la place de son rectificatif : forme de la remarque → 05/11, 23/10 gardée comme date initiale ; date accolée sans année → « non précisée », jamais le 23/10 ; délai des questions daté → « non précisée », ni le 16/10 ni le 23/10 ; le rectificatif réel 26-100865 → date de l'avis ; écritures voisines (« date et heure limites … fixées au jeudi 5 novembre 2026 », deux dates accolées, forme en champs, visite). Échoue sur `0afc1ed` (`'2026-10-23' == '2026-11-05'` : aucun rectificatif lu) et sur `f86e510` (même échec : rectificatif lu « ne concerne pas »). Sur les 127 rectificatifs réels des jeux d'essai, les lectures de `f86e510` et de cet état sont **identiques** (aucun n'emprunte la nouvelle règle : C.2). |
| **Non vérifié** | Toute la forme : jamais observée. Les verbes reconnus (fixée, prévue, reportée, repoussée, arrêtée, portée, suivis de « au » ou « le ») sont choisis, pas relevés ; derrière « avant / après », une autre écriture accolée (« … avant la date limite de remise des offres du 05/11/2026 », « … des offres : 05/11/2026 ») donne « non précisée » (prudence). Un texte qui ne change qu'un autre délai, cite une date et la date limite comme repère donne aussi « non précisée » alors que la date de l'avis reste juste : c'est le prix de « jamais l'ancienne date ». |
| **Pour le client** | Aucun changement sur les rectificatifs observés. Sur cette forme, s'il en paraît : la nouvelle date (accolée), ou « limite non précisée », au lieu de l'ancienne date (point 5 de la liste). |

### C.2 La comparaison de V.3, rejouable depuis le dépôt

| | |
|---|---|
| **Avant** | La preuve de V.3 et le point 5 de la liste citaient « 173 rectificatifs réels ». Recompté sur `f86e510` : les jeux d'essai `tests/fixtures/**/*.json` contiennent 144 lignes de rectificatif hors annulations, **127 rectificatifs distincts**, dont 119 avec un corps `infosRectif` (136 éléments) et 8 au format européen. Aucun compte ne donne 173. Les seules suites enregistrées en plus de celles des chantiers sont les 100 de la recherche « travaux » de la relecture (parues du 06/10 au 21/10/2026), comprises dans ces 127 ; si la relecture en a lu d'autres (« 100 rectificatifs parus du 12/10 au 21/10 »), elles ne sont pas dans le dépôt et ne sont plus citées. La conclusion, elle, se vérifie sur les 127 : seule la lecture de 26-100865 change. |
| **Après** | Le contrat cite le nombre rejouable (127 rectificatifs, dont 119 avec corps) et dit comment rejouer la comparaison. Aucun jeu d'essai ajouté. |
| **Preuve** | `test_comparaison_rejouable_sur_les_rectificatifs_reels_des_jeux_d_essai` : parcourt tous les jeux d'essai, vérifie les comptes (144, 127, 119, 136, 8), lit chaque rectificatif avec et sans la règle du repère (une seule différence : 26-100865), vérifie qu'aucun n'emprunte la règle de C.1, et que le contrat cite ce nombre. Échoue sur `0afc1ed` (aucune lecture de rectificatif : `_est_suite` introuvable) et sur `f86e510` (règle de C.1 absente : `_dates_accolees` introuvable ; son contrat cite encore « 173 rectificatifs » au point 5 et en V.3). |
| **Pour le client** | Rien. |

### C.3 Vérifications

- **Les 3 nouveaux tests** (`tests/test_moteur_lot1_contre_relecture.py`) échouent sur `0afc1ed` et sur `f86e510`
  (exports `git archive`, nouveaux tests et jeux d'essai copiés, réseau coupé par un greffon), chacun sur le défaut
  qu'il couvre : voir les preuves ci-dessus ; le test du contrat échoue faute de cette section.
- **Suite complète** sur cet état (`TZ=UTC`, base SQLite d'essai, Python 3.12 depuis `requirements.lock`) : **2 255
  tests, tous verts** (les 2 252 de la relecture, aucun adapté, et les 3 nouveaux).
- **Lectures des rectificatifs réels inchangées** : les 127 des jeux d'essai, lus par `lire_rectificatif` de `f86e510`
  et de cet état, donnent les mêmes résultats (aucune différence).
- **Aucun changement de base de données** : rien à vérifier sur Postgres.

---

## Décisions d'Eliot (22/10/2026)

Prises sur le bilan de la mise en ligne (`docs/MISE_EN_LIGNE_22_10.md`, section 3, décisions 1 à 3), appliquées sur
`130fc9e`. Chaque test cité passe désormais (`tests/test_mise_en_ligne_22_10.py`).
`test_d3_ce_que_dit_la_bulle_est_vrai` passait déjà sur `130fc9e` : il fixe ce que la bulle affirme. Les autres tests
cités échouaient sur `130fc9e` (vérifié sur une extraction `git archive` de `130fc9e` avec ces tests, relecture des
décisions).

**Points 12 et 12 bis, V.5 : (b), le repli payant remboursé en outre-mer et en Corse.** `app/routers/sourcing.py`,
`_repli_rembourse_par_zone` : dès qu'un des départements demandés commence par « 97 » ou « 98 », ou vaut « 2A », « 2B »
ou « 20 », seul ou avec d'autres, le repli est remboursé, qu'il trouve ou non ; les fins de contrat trouvées sont
montrées. Le journal du repli écrit « analyse remboursée (outre-mer ou Corse, jusqu'à l'annonce du crédit à l'écran) »
(`REMBOURSE_PAR_ZONE`). Ailleurs, la règle habituelle. Le crédit reste demandé avant le repli. Seul écart avec la
production, en faveur du client : une demande mixte (« 29, 974 ») est remboursée en entier, alors que `0afc1ed` la
débitait si elle trouvait en métropole. Preuve : `test_d1_repli_a_venir_rembourse_en_outre_mer_et_en_corse` (sur
`130fc9e`, « 974 » débité).

**Point 16 bis, V.7 : (b), une seule règle pour les courriels planifiés vers le compte lui-même.** La fonction
`alerts._comptes_non_confirmes` sert aussi à `carnet_notes.envoyer_rappels` (« Demandez vos notes »),
`alerts.run_document_expiry_alerts` (« pièces à renouveler ») et `alerts.run_amont_alerts` (veille amont, masquée ;
ajoutée pour que la règle soit la seule). Rien n'est marqué : ils partent au premier passage après la confirmation,
« Demandez vos notes » seulement dans ses 14 jours ; la veille amont, rallumée, n'enregistre aucun projet pour une
adresse non confirmée et ne reprend ensuite que ceux des délibérations qu'elle lit alors (relecture des décisions,
`docs/MISE_EN_LIGNE_22_10.md`, section 3, décision 2, avec l'exception du récapitulatif des attestations d'un marché
créé par un collègue non confirmé). Preuve : `test_r1_adresse_non_confirmee_aucun_courriel_planifie_vers_le_compte`,
`test_r1_la_veille_amont_suit_la_meme_regle` ; constaté aussi sur `0afc1ed` : l'adresse non confirmée y recevait
l'alerte de marchés, « Demandez vos notes » et « pièces à renouveler ».

**Point 17 bis, V.8 : (b), la bulle de « Mes alertes » corrigée.** Elle dit : « Recevez par email les nouveaux marchés
de cette recherche, 10 au plus par alerte, les autres comptés. Chaque envoi lit un nombre limité d'avis par source (au
BOAMP, les 25 derniers publiés) : une recherche très large peut en avoir d'autres, à voir dans Adjugo. La recherche de
l'onglet « Publiés » est enregistrée telle quelle. » « 10 au plus » est vrai (`_MARCHES_PAR_ALERTE`) ; « les autres
comptés » ne l'est que pour les avis que l'envoi lit (25 demandés au BOAMP et à TED, 3 pages au plus de Mégalis) : la
deuxième phrase le dit. Néerlandais et espagnol ajoutés (790 clés). Preuve :
`test_d3_la_bulle_de_mes_alertes_dit_ce_que_fait_le_courriel`, `test_d3_ce_que_dit_la_bulle_est_vrai`.

---

## Écran

*Partie écran du lot : points 10 à 13 de la note du 21/10/2026, posés sur `0f8eb32` (partie serveur, vague 2b, tests
PostgreSQL). La bulle de « Mes alertes » était déjà corrigée (décision 3 du 22/10) : elle n'est pas touchée.*

Fichiers : `app/static/app.html` (cartes de « Publiés », état vide, onglet « À venir »), `app/static/app.js` (quatre
fonctions pures et leurs méthodes : `metierCherche`, `dureeFinDeContrat`, `rectifDeCarte`, `estCompteDemo` ;
`srcSearchMine`, `srcPrefillFromProfile`, `srcRenewals`), `app/static/styles.css`, `app/static/i18n.js` (25 phrases
en néerlandais et en espagnol, 815 clés ; 8 de plus à la revue, 823 clés, et une cinquième fonction pure,
`cpvSeulsCherche`, avec la méthode `srcRenHorsForfait` : § « Revue », plus bas), `app/static/demo/deliberation.html`, empreintes SRI. Trois ajouts au serveur,
sans changer ce qu'il trouve ni ce qu'il débite : `atexo.nom_organisme` (nom de l'organisme Mégalis),
`date_limite_rectificatif` et `date_limite_rectificatif_le` sur la fiche (`boamp._appliquer`, `schemas.py`, avec la
garde des liens de `base.py` et la fusion de `search.py`), `source` et `analyse` dans la réponse du repli payant
(`sourcing.renewals`). Tests : `tests/test_moteur_lot1_ecran.py` (13 tests, sans réseau), qui échouent tous sur
`0f8eb32` ; un test existant adapté (plus bas). Ni prix, ni quota, ni règle de débit, ni IA, ni changement de base de
données ; le robot de Mégalis inchangé ; la démo de pitch garde sa recherche et ses fins de contrat servies à part,
sans réseau, IA ni analyse (ce que son écran change : `docs/MISE_EN_LIGNE_22_10.md`, section 5).

### Ce qui change pour le client

**Trouver des marchés › Publiés**
1. Plus aucun nombre sur la carte : ni « confiance N % » (fixée à 70 % pour toute consultation Mégalis), ni « adéquation
   N/100 » (décision 8 de l'organisation : des pourcentages seulement après le dossier). Les cartes restent rangées par
   la même note, sans la montrer. Les mots « Bon potentiel », « À étudier », « Peu adapté » n'arrivent pas : ils
   attendent le barème corrigé de la V1, car aujourd'hui une donnée inconnue avantage le marché (`scoring.py`). Sans
   métier ni zone dans « Ce que je cherche », l'invitation reste : « Dites ce que vous cherchez pour un classement
   adapté » (avant : « … pour un score adapté »), en vrai bouton.
2. Mégalis : le nom de l'organisme sans « (code postal - ville) » (« COMMUNE DE SAINT SAUVEUR » au lieu de « COMMUNE
   DE SAINT SAUVEUR (29400 - SAINT-SAUVEUR) »), sur la carte, dans Mes marchés pour un marché analysé désormais et dans
   le courriel d'alerte. Rien d'autre n'est réécrit (majuscules et sigles gardés).
3. Avis rectifiés du BOAMP : « Date limite repoussée au 06/11/2026 (rectificatif du 06/10/2026) », le lien mène au
   rectificatif ; « avancée » si la nouvelle date précède l'ancienne ; « Date limite non précisée (rectificatif du …) »
   avec une bulle (i) quand la nouvelle date n'a pas pu être lue, jamais l'ancienne date (*Revue* : la bulle dit
   qu'un rectificatif « peut changer » la date limite, vrai aussi quand le serveur le suppose par prudence) ; « Avis
   rectifié
   (rectificatif du …) » quand la date ne change pas. La date limite de la carte s'écrit « 06/11/2026 » (avant :
   « 2026-11-06 »).
4. « Voir les marchés pour mon entreprise » cherche le premier métier de « Ce que je cherche » ; sans métier, rien
   n'est cherché : « Dites d'abord votre métier … » et le bouton « Dire mon métier », qui ouvre « Ce que je cherche »,
   le curseur dans « Spécialités ». *Revue* : avec des codes CPV et aucune spécialité, la demande dit « Ajoutez votre
   métier en mots dans « Spécialités » … Vos codes CPV seuls ne suffisent pas à ce bouton. » ; le sous-titre dit
   « … et les départements de la recherche ci-dessus » (le champ, pré-rempli par le code postal et modifiable).

**Trouver des marchés › À venir**
5. « Fin du contrat estimée le 25/10/2026 (durée publiée) » au lieu de « Renouvellement ~ [fin moins 120 jours] ». Au
   repli payant : « (durée lue dans l'intitulé de l'avis) », « (durée estimée selon le type de contrat) » ou, sans
   type (*Revue*), « (durée estimée par défaut, type de contrat inconnu) », et « attribution publiée le … » au lieu de
   « notifié le … ». Le département affiché est celui de l'avis (avant, au
   repli : ses descripteurs, « dépt Voirie »).
6. La bulle dit la vraie source et reste neutre : « … préparez votre réponse et vos partenaires avant la
   republication. La fin du contrat est estimée d'après les données publiées des marchés attribués … ». *Revue* : elle
   dit aussi le repli, « À défaut, d'après les avis d'attribution du BOAMP : la date de publication de l'avis et une
   durée lue dans son intitulé, ou estimée. »
7. Le crédit, avant le clic, sous les champs : « Une recherche complémentaire peut consommer 1 analyse : remboursée si
   elle ne trouve rien, toujours remboursée en outre-mer et en Corse. », avec sa bulle (i). Après un repli : « …
   1 analyse consommée. » ou « … analyse remboursée. », et le compteur d'analyses est relu. La démo ne voit pas la
   ligne (elle n'est jamais débitée). *Revue* : la bulle dit la règle sans analyse restante, « … elle n'est lancée
   qu'avec le paiement à l'usage activé (forfaits Pro et Business) : elle est alors facturée au tarif à l'usage, et
   remboursée dans les mêmes cas » ; et un compte Pro ou Business dont les analyses du mois sont utilisées, paiement à
   l'usage activé, lit avant le clic « Vos analyses du mois sont utilisées : la recherche complémentaire serait
   facturée 5 € (paiement à l'usage), et remboursée dans les mêmes cas. » (prix lu dans le compteur).

**Démo**
8. La page d'exemple d'une délibération ne dit plus « récupérées automatiquement par Adjugo » ni « Sur un compte réel,
   ce lien ouvre la vraie délibération ».

### É.10 Les cartes de « Publiés »

| | |
|---|---|
| **Avant** | `app.html` : « confiance {{ … }}% » (`atexo.py` : 0.7 pour toute consultation Mégalis) et « adéquation {{ t.score.total }}/100 », contraires à la décision 8 ; « limite 2026-11-06 » ; « COMMUNE DE … (29400 - …) » ; les champs du rectificatif envoyés par le serveur (§ S.2) mais jamais affichés. La fiche ne portait que la date du **dernier** rectificatif paru (`rectifie_le`) : sur 26-90336, repoussé au 06/11 par 26-96286 (06/10) puis rectifié sur ses lots le 21/10 (lien construit avec le rectificatif réel 26-102445), l'écran aurait écrit « rectificatif du 21/10/2026 », faux. |
| **Après** | Plus de pastilles de nombre ni de `confClass`. La ligne du rectificatif vient de `rectifDeCarte` (`app.js`) : états `repoussee`, `avancee`, `non_lue`, `rectifie`. Le serveur dit maintenant quel rectificatif fixe la date : `date_limite_rectificatif` (son lien, sa référence) et `date_limite_rectificatif_le` (sa parution), posés par `boamp._appliquer` sur le dernier rectificatif qui parle de la date limite ; un rectificatif européen qui redit la même date en est un (26-101475 pour 26-95098 : « Avis rectifié »). Le lien passe la garde des liens (`base.sanitize_tender_links`) ; un doublon d'une autre source le reçoit s'il ne l'a pas (`search._dedup_tenders`). Sans ces champs (réponse d'avant), l'écran cite le dernier rectificatif. `atexo.nom_organisme` retire « (5 chiffres - ville) » en fin de nom, même coupé ; le lieu et la clé de fusion lisent toujours le texte de la page, donc la note, la fusion avec le BOAMP et la mémoire des alertes ne changent pas. |
| **Preuve** | `test_e10_carte_sans_nombre_avant_le_dossier_ni_mot_de_verdict`, `test_e10_nom_de_l_organisme_megalis_nettoye_sans_rien_changer_d_autre` (page réelle de Mégalis du 21/10), `test_e10_le_rectificatif_cite_est_celui_qui_fixe_la_date`, `test_e10_ligne_du_rectificatif_sur_les_avis_reels_sous_node` (avis réels du jeu du 21/10 passés par la vraie recherche BOAMP : 26-90336 « repoussée au 06/11/2026 (rectificatif du 06/10/2026) », 26-94570 « non précisée » sans la date du 29/10, 26-95098 « Avis rectifié »). |
| **Pour le client** | Points 1 à 3 de la liste. |

### É.11 « Voir les marchés pour mon entreprise »

| | |
|---|---|
| **Avant** | `srcPrefillFromProfile` lisait `specialites` dans la fiche Identité, qui n'a pas ce champ (`CompanyOut`) : la recherche partait sans mot dès que le code postal donnait un département, et le BOAMP cherchait alors « travaux » sans le dire (`boamp.py`). Sans code postal ni mot, l'écran renvoyait vers Mon entreprise. |
| **Après** | `srcSearchMine` prend `metierCherche(criteria)`, la première spécialité de « Ce que je cherche » (`criteria_v2.specialites`, coupée aux virgules et points-virgules), relue au serveur si elle manque à l'écran (sans écraser une saisie non enregistrée). Elle remplace les mots du champ : le bouton dit « pour mon entreprise ». Sans métier, aucune recherche : `src.manqueMetier`, la phrase et le bouton « Dire mon métier » (`srcDireMetier` : `go("criteria")`, curseur dans `#crit-spec`), le curseur posé sur ce bouton ; la phrase disparaît dès qu'un métier est saisi. Les départements ne changent pas : ceux du champ de la recherche, pré-rempli une fois par le code postal (`srcPrefillFromProfile`, `zoneDuCodePostal`), que le client peut modifier ou vider (toute la France). `srcPrefillFromProfile` ne lit plus que le code postal. Le sous-titre dit d'où viennent les mots et les départements (*Revue* : il promettait « le département de votre code postal »). *Revue* : des codes CPV sans spécialité (`cpvSeulsCherche`, à l'écran ou relus au serveur) : `src.cpvSeuls`, et la demande dit que ces codes ne suffisent pas à ce bouton, qui cherche avec des mots. |
| **Preuve** | `test_e11_voir_les_marches_lit_le_metier_de_ce_que_je_cherche_sous_node` (vraies méthodes sous Node : métier présent, mots tapés ailleurs, aucun métier, métier enregistré par un collègue, serveur en panne ; le chemin direct) ; *Revue* : `test_r5_des_codes_cpv_sans_specialite_l_ecran_dit_ce_qui_manque`, `test_r6_le_sous_titre_dit_les_departements_de_la_recherche`. |
| **Pour le client** | Point 4. |

### É.12 L'onglet « À venir »

| | |
|---|---|
| **Avant** | « Renouvellement ~ » montrait `renouvellement_estime`, la fin moins 120 jours : une date de republication devinée. La bulle disait « sources réelles BOAMP » (la source principale est la DECP) et « positionnez-vous auprès du client avant la republication ». Rien n'annonçait le crédit du repli payant (décision 12). « notifié le » et « (réelle) » aussi sur les fins de contrat du repli, dont la date est celle de la parution de l'avis d'attribution et la durée lue par l'IA. |
| **Après** | Pastille « Fin du contrat estimée le … » + `dureeFinDeContrat` : « (durée publiée) » pour la DECP (fin = date de notification + `dureemois`, `decp.py`), « (durée lue dans l'intitulé de l'avis) », « (durée estimée selon le type de contrat) » ou, sans type, « (durée estimée par défaut, type de contrat inconnu) » (*Revue* : 36 mois, `_DEFAULT_DUREE`) au repli. `renouvellement_estime` ne sert plus qu'au tri et à la fenêtre du serveur. La réponse du repli dit `"source": "BOAMP"` et `"analyse": "debitee"` ou `"remboursee"` (même débit, même remboursement qu'avant) ; l'écran l'affiche et relit le compteur. La ligne du crédit et sa bulle disent la règle de `sourcing.renewals` telle qu'elle est (lue dans le code) : la DECP ne consomme rien ; le repli consomme 1 analyse (`consume_analysis`), la rend s'il ne trouve rien ou échoue, et toujours dès qu'un des départements demandés commence par « 97 » ou « 98 » ou vaut « 2A », « 2B » ou « 20 » (`_repli_rembourse_par_zone`, décision 1 du 22/10), seul ou avec d'autres ; sans analyse restante, le repli n'est lancé qu'avec le paiement à l'usage activé et facturable (forfait Pro ou Business, client Stripe : `quota.overage_billable`), qui le facture hors forfait (`overage_count`, `report_overage`) et l'annule dans les mêmes cas de remboursement (`refund_analysis`, `cancel_overage`) ; sinon refus (402), même là (*Revue* : la bulle disait « Il faut une analyse disponible pour la lancer », faux au paiement à l'usage). Le compte dans ce cas (analyses du mois utilisées, paiement à l'usage activé, forfait Pro ou Business : `srcRenHorsForfait`, lu dans `stats.usage`) voit en plus, avant le clic, le prix lu dans le compteur (`overage_price`, `quota.OVERAGE_PRICE`). La ligne n'est pas montrée à la démo (`estCompteDemo`, même règle que `demo_search.is_demo`), dont les fins de contrat ne coûtent rien. La carte passe le bouton « Préparer à plusieurs » sous le texte à 375 px. |
| **Preuve** | `test_e12_a_venir_fin_du_contrat_bulle_juste_et_neutre`, `test_e12_la_duree_dite_avec_sa_source_sous_node`, `test_e12_le_credit_annonce_avant_le_clic_est_celui_du_code` (par la route : DECP sans débit ; repli débité ; repli vide remboursé ; « 974 », « 971 », « 988 », « 2A, 2B », « 20 », « 29, 974 », « 2B, 56 » remboursés même s'ils trouvent ; 402 en outre-mer sans analyse disponible à l'essai), `test_e12_apres_le_repli_l_ecran_dit_ce_qu_est_devenue_l_analyse_sous_node`, `test_e12_la_demo_de_pitch_garde_ses_fins_de_contrat_sans_credit` ; *Revue* : `test_r1_le_credit_dit_vrai_au_paiement_a_l_usage`, `test_r2_la_bulle_d_a_venir_dit_les_deux_sources`, `test_r3_duree_par_defaut_sans_type_de_contrat`. |
| **Pour le client** | Points 5 à 7. |

### É.13 La page d'exemple de la démo

| | |
|---|---|
| **Avant** | `app/static/demo/deliberation.html` : « Les délibérations réelles sont publiées par les collectivités et récupérées automatiquement par Adjugo » et, en bandeau, « Sur un compte réel, ce lien ouvre la vraie délibération ». Faux : la veille des projets à venir est masquée (`PROJETS_A_VENIR` éteint, adresses en 404, § 7). |
| **Après** | Bandeau : « Document fictif, à titre d'illustration : une délibération réelle se lit sur le site de la collectivité qui la publie. » Pied : « … La veille des projets votés en conseil, « Projets à venir », n'est pas encore ouverte : Adjugo ne lit pas aujourd'hui ces délibérations. » À réécrire au rallumage de la veille (vague 1), qui relie de nouveau cette page aux projets de la démo (`demo_seed.py`). |
| **Preuve** | `test_e13_la_page_d_exemple_de_la_demo_dit_vrai`. |
| **Pour le client** | Point 8 (page reliée à rien tant que la veille est masquée). |

### Textes et contrat

`test_ecran_lot1_textes_traduits_sans_mot_banni_ni_emoji` (25 libellés, chacun un nœud de texte entier, traduits en
néerlandais et en espagnol, sans mot banni ni émoji, « vérifié » absent) ; `test_ecran_lot1_contrat_et_bilan_de_mise_en_ligne`.

Test existant adapté, avec sa raison : `tests/test_mise_en_ligne_22_10.py::test_cr1_a_venir_part_du_code_postal_pour_toute_entreprise_sous_node`
donnait à la fiche Identité une spécialité fictive (« Voirie »), que `srcPrefillFromProfile` recopiait dans les mots.
La fiche n'a pas ce champ ; le pré-remplissage ne la lit plus. « Voirie » est maintenant tapé dans le champ des mots de
l'onglet ; ce que le test vérifie (le département pris du code postal, la zone de « Ce que je cherche » jamais lue ni
réécrite) ne change pas.

### À décider par Eliot

- **Remboursement en outre-mer et en Corse.** La décision 1 du 22/10 le posait « jusqu'à l'annonce du crédit à
  l'écran ». L'écran l'annonce désormais. Le code le garde (aucun changement de débit sans vous) et l'écran dit donc
  « toujours remboursée en outre-mer et en Corse », ce qui est vrai. Deux choix : (a) le garder, et seule la ligne de
  journal `REMBOURSE_PAR_ZONE` (« … jusqu'à l'annonce du crédit à l'écran ») est à reformuler ; (b) le retirer
  (`_repli_rembourse_par_zone`), et la fin de la phrase de l'écran, sa bulle et leurs traductions partent avec, dans le
  même changement.

### Vu en passant, non corrigé

- « Rechercher » (Publiés) sans mot et « Chercher les fins de contrat » (À venir) sans mot cherchent toujours
  « travaux » sans le dire (`boamp.py`, `srcRenewals` dans `app.js`, `decp.py`) ; seul le bouton « Voir les marchés
  pour mon entreprise » était dans le point 11.
- Des noms d'acheteur du BOAMP arrivent avec une entité HTML (« Centre hospitalier d&#039;Argenteuil », jeu réel du
  21/10) : la carte l'affiche telle quelle, comme en production.
- Le repli payant ne filtre pas les départements après la lecture : une demande « 29 » peut montrer un avis que le
  BOAMP range d'abord en « 44 » (jeu réel), comme en production.

### Revue

*Douze remarques de la revue de la partie écran (`ba07980`), neuf distinctes (trois en double, écrites par deux
relecteurs). Chacune reproduite sur `ba07980` ; toutes réelles, une en partie seulement (R5). Corrigées dans l'écran
(textes, une ligne, une fonction pure, une méthode), ses traductions et ces deux documents ; côté serveur, un
commentaire seulement (`schemas.py`). Ni prix, ni quota, ni règle de débit, ni IA, ni changement de base de données.
Tests : `tests/test_moteur_lot1_ecran_revue.py` (7 tests, sans réseau), qui échouent tous sur `ba07980` ; les tests de
`tests/test_moteur_lot1_ecran.py` qui fixaient les anciens textes suivent.*

| | Avant (`ba07980`) | Après | Preuve |
|---|---|---|---|
| **R1** (remarques 1 et 6, majeur) | La bulle du crédit : « Il faut une analyse disponible pour la lancer. » Faux au paiement à l'usage : à 0 analyse restante, `quota.consume_analysis` laisse partir le repli et le facture hors forfait (forfait Pro ou Business, client Stripe, paiement à l'usage activé) ; rien ne le disait avant le clic. Le contrat (É.12) et le bilan (sections 1 et 3) répétaient la règle. | La bulle dit la règle du code (« Sans analyse restante, elle n'est lancée qu'avec le paiement à l'usage activé (forfaits Pro et Business) : elle est alors facturée au tarif à l'usage, et remboursée dans les mêmes cas. ») ; une ligne de plus, avant le clic, pour ce compte seulement (`srcRenHorsForfait` : forfait Pro ou Business, hors essai, paiement à l'usage activé, 0 analyse restante) : « Vos analyses du mois sont utilisées : la recherche complémentaire serait facturée 5 € (paiement à l'usage), et remboursée dans les mêmes cas. », le prix lu dans `stats.usage.overage_price` ; décrite par le bouton (`aria-describedby`) ; cachée à la démo. | `test_r1_le_credit_dit_vrai_au_paiement_a_l_usage` : par la route, Pro, client Stripe, paiement à l'usage activé, 30 sur 30 : 200, « debitee », 31 utilisées, 1 hors forfait déclarée ; repli vide : remboursé, déclaration annulée ; « 974 » : remboursé ; paiement à l'usage coupé : 402, rien de débité ; `GET /api/agent/stats` et la vraie méthode sous Node (la ligne pour ce compte, pas pour un compte qui a des analyses, l'essai, un compte Starter, ni sans compteur). |
| **R2** (remarques 2 et 7) | La bulle d'en-tête : « … d'après les données publiées des marchés attribués : la date de notification et la durée publiée », pour toutes les fins de contrat. Au repli, la date est la parution de l'avis d'attribution du BOAMP (`renewal._fetch_attributions`, `dateparution`) et la durée est lue par l'IA ou fixée par défaut ; la carte dit « attribution publiée le » : l'écran se contredisait. | Une phrase de plus, vraie pour les deux sources : « À défaut, d'après les avis d'attribution du BOAMP : la date de publication de l'avis et une durée lue dans son intitulé, ou estimée. » La bulle du crédit le dit aussi (« Ses fins de contrat partent de la date de publication de l'avis d'attribution … »). | `test_r2_la_bulle_d_a_venir_dit_les_deux_sources` (la phrase, et le calcul de `renewal.py` qu'elle décrit). |
| **R3** (remarques 3 et 8) | « (durée estimée selon le type de contrat) » aussi sans type : la durée est alors 36 mois par défaut (`_DEFAULT_DUREE[None]`), et toutes le sont quand l'IA ne rend rien (`enrich = {}`). | `dureeFinDeContrat` : « selon le type de contrat » seulement si `type_contrat` est renseigné, sinon « (durée estimée par défaut, type de contrat inconnu) » ; la bulle du crédit dit « (36 mois quand il est inconnu) ». | `test_r3_duree_par_defaut_sans_type_de_contrat` (le vrai `detect_renewals`, IA en panne puis types rendus : 36, 48, 30 mois ; l'écran sous Node). |
| **R4** (remarque 4) | La bulle de « Date limite non précisée » : « Un rectificatif de cet avis porte sur sa date limite ». Le serveur pose aussi cet état, par prudence, sur des formes dont il ne sait pas s'ils en parlent (bloc `infosRectif` absent, autre délai : `boamp.lire_rectificatif`, `_lire_element`) ; jamais observées dans les jeux réels, mais chemins réels du code. | « Un rectificatif de cet avis peut changer sa date limite, et Adjugo n'a pas pu la lire avec certitude : lisez-la sur le rectificatif. L'ancienne date n'est pas montrée : elle peut ne plus être la bonne. » | `test_r4_la_bulle_non_precisee_reste_vraie_quand_le_serveur_est_prudent` (les deux formes passées par `_appliquer`, puis `rectifDeCarte` sous Node). |
| **R5** (remarque 5, mineur) | Des codes CPV dans « Mes métiers » sans aucune spécialité : « Dites d'abord votre métier », alors que le produit tient ce métier pour dit (`criteria_v2.ce_que_je_cherche_dit` : « spécialités ou codes CPV », la tâche « Dire ce que vous cherchez » des premiers pas). En partie rejetée : ces premiers pas ne sont pas « affichés juste en dessous dans la même carte » (la carte montre la tâche « Ajouter 3 marchés à Mes marchés ») ; la contradiction, elle, est réelle. | La demande dit ce qui manque : « Ajoutez votre métier en mots dans « Spécialités » : la recherche part de la première spécialité de « Ce que je cherche ». Vos codes CPV seuls ne suffisent pas à ce bouton. » (`cpvSeulsCherche`, `src.cpvSeuls`). La recherche n'est pas lancée sur les codes : le BOAMP ne les lit pas (§ S.3) et chercherait « travaux » sans le dire, le défaut que le point 11 retire. | `test_r5_des_codes_cpv_sans_specialite_l_ecran_dit_ce_qui_manque` (la route enregistre des codes CPV seuls, le métier est « dit » ; sous Node : codes à l'écran, codes relus au serveur, rien, serveur en panne, métier et codes). |
| **R6** (remarque 9) | Le sous-titre promettait « le département de votre code postal ». Le bouton cherche dans le champ « Départements » de la recherche, pré-rempli une fois par le code postal : vidé, toute la France ; « 56 » tapé, le 56. | Le comportement ne change pas (un champ que le client a changé n'est pas réécrit) ; le sous-titre dit « D'après votre premier métier, dans « Ce que je cherche », et les départements de la recherche ci-dessus. » | `test_r6_le_sous_titre_dit_les_departements_de_la_recherche` (sous Node : pré-rempli, vidé, autre département). |
| **R7** (remarques 10, 11 et 12) | Le bilan et ce contrat disaient encore « (estimée) » (point 12 ter, V.6), « rien de visible » (point 13), une note d'adéquation que le client verrait bouger (deux puces de « Publiés » dans le bilan ; point 7, § S.1 et S.3 ici), et « Trois chantiers » en tête du bilan, au-dessus d'un tableau de quatre lignes. | Notes *Écran* ajoutées ou phrases reprises ; « Trois chantiers … ont été réunis …, puis la partie écran du lot 1 posée au-dessus ». | `test_r7_contrat_et_bilan_disent_l_ecran_d_apres_la_revue`. |

Rien n'est rejeté en entier. À noter pour R1 : un compte dont le paiement à l'usage est resté activé après le retour
à un forfait sans abonnement (rétrogradé par Stripe) ne voit pas la ligne, et le repli lui est refusé (402,
`overage_billable`) : la ligne ne s'affiche que là où elle est vraie.

### Vérifications

- Les 13 tests nouveaux, sur une extraction `git archive` de `0f8eb32` (tests copiés) : 13 échecs, chacun sur le
  défaut qu'il couvre (« confiance » dans la carte, organisme avec sa parenthèse, champ du rectificatif absent,
  fonctions de l'écran absentes, « Renouvellement », ligne du crédit absente, page de la démo, traductions, ce contrat).
- Suites complètes, navigateur et fichiers servis : `docs/MISE_EN_LIGNE_22_10.md`, section 5, « Partie écran du lot 1
  du moteur » ; pour la revue, « Revue de la partie écran du lot 1 ».
