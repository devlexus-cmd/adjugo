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

Le lot a été mené en deux chantiers parallèles, « Sources » (points 1 à 4) et « Services » (points 4 bis, 5 à 9), puis
réunis : chacun garde sa section, telle qu'il l'a écrite (les rares compléments de la réunion y sont marqués
*Réunion*), et la réunion a la sienne (vérifications de bout en bout sur des données réelles, deux défauts trouvés en
les faisant, corrigés). Chaque point dit : **avant**, **après**, **preuve**, **ce qui change pour le client**.

## Ce qui change pour le client : la liste complète

*Tout le lot, partie serveur, après la réunion. Entre crochets, la section où le point est détaillé. Rien d'autre ne
change (voir « Ce qui ne change pas », plus bas).*

**Trouver des marchés (recherche)**
1. Mégalis : les cartes montrent leur date limite (avant : « limite non précisée » ; 10 dates vides sur 10 sur la page
   réelle du 21/10/2026). L'ordre des résultats bouge un peu, et le nombre « adéquation N/100 » d'une carte Mégalis
   peut changer (son délai de réponse compte enfin). [S.1]
2. Mégalis et BOAMP : une même consultation peut ne faire qu'une carte (« vu aussi sur »), mais seulement quand
   l'acheteur est écrit de la même façon des deux côtés. Sur les deux cas réels du 21/10/2026, aucun ne fusionne : ces
   consultations restent en deux cartes, comme avant. [S.1, R.4]
3. BOAMP, avis rectifié : la nouvelle date limite ; un avis repoussé reste visible après son ancienne date ; un avis
   européen rectifié n'apparaît plus deux fois. [S.2, R.3]
4. BOAMP, avis annulé ou déclaré sans suite : il disparaît. [S.2, R.3]
5. Un rectificatif dont la nouvelle date ne peut pas être lue sans doute : « limite non précisée » au lieu de
   l'ancienne date. [S.2, R.4]
6. Le lien « Voir l'annonce officielle » reste celui de l'avis initial ; sur un avis rectifié, la date de la carte
   peut différer de celle de cette page (c'est la date du rectificatif). Le lien du rectificatif et « modifiée le … »
   sont dans les données ; l'écran les montrera après la 2b. [S.2]
7. Plus de faux « métier correspondant » sur une carte BOAMP : sa note d'adéquation peut baisser. Une recherche avec
   des codes CPV ne ramène plus d'avis BOAMP sans rapport par ces codes (les mots-clés ne changent pas). [S.3]
8. Outre-mer : une recherche « 971 », « 972 », « 973 », « 974 » ou « 976 » ne montre plus les avis des autres
   départements d'outre-mer, et la zone de la note est juste pour une entreprise d'outre-mer (un avis de la
   Guadeloupe n'est plus « dans votre zone » pour une entreprise de La Réunion). [S.4, R.3]
9. **Corse (ajouté à la réunion)** : une recherche « 2A » ou « 2B » montre enfin les avis du BOAMP, qui écrit la Corse
   « 20A » et « 20B » (19 avis ouverts le 21/10/2026 ; avant : aucun, sur toutes les recherches corses) ; une
   entreprise qui a saisi « 2A » ou « 2B » les voit « dans votre zone ». [R.1]
10. Une recherche fait une ou deux requêtes de plus au BOAMP (entre 0,37 et 0,64 s chacune le 21/10/2026 ; 2,0 s pour
    la recherche complète mesurée par le chantier Sources). [S.2, R.3]

**Onglet « À venir »**
11. Outre-mer : seules les fins de contrat du département demandé ; le département s'affiche « 974 » au lieu de
    « 97 ». « 6 » saisi seul est lu dans la DECP, sans crédit, au lieu de passer par le repli payant. [Services 4 bis]
12. **Corse, repli payant (ajouté à la réunion)** : quand la DECP ne donne rien ou ne répond pas, le repli lit
    désormais les avis d'attribution corses du BOAMP ; avant, il ne trouvait jamais rien en Corse et l'analyse était
    toujours remboursée. Il peut maintenant trouver des fins de contrat, et l'analyse est alors débitée, selon la même
    règle que partout ailleurs (remboursée s'il ne trouve rien). La règle de débit ne change pas. [R.1]
13. Chaque repli payant est noté dans le journal : rien de visible. [Services 8]

**Partenaires**
14. « Chercher » (page du marché) et « Répartition proposée » : des PME seulement ; les grandes entreprises et les
    entreprises de taille intermédiaire n'y sont plus proposées. [Services 5 b]
15. API seulement : `past_wins` vaut `null` au lieu de `0` quand les marchés gagnés n'ont pas pu être lus. [Services 5 a]

**Alertes de marchés**
16. Plus aucun marché écarté par sa note d'avant dossier : les courriels contiennent plus de marchés. Sur l'alerte
    réelle « voirie » dans le 29 (21/10/2026), 7 marchés partent (5 du BOAMP, 2 de Mégalis), tous notés de 60 à 67,
    sous le seuil de 75 de « Ce que je cherche » : avant, cette alerte n'envoyait rien. [Services 6 a, R.3]
17. Au-delà de 10 marchés par alerte, la ligne « … et N autres marchés : relancez cette recherche dans Adjugo pour les
    voir tous. » « Tester » une alerte annonce plus de nouveaux marchés. [Services 6 a]
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

**Ce qui ne change pas** : les prix, les quotas, les débits et les remboursements ; la démo (sa recherche, ses fins de
contrat et l'aperçu de ses alertes sont servis à part, sans réseau ni IA : 194 tests de la démo verts, § R.5) ; aucune
IA ajoutée ; le robot de Mégalis ; un seul processus, aucun nouveau planificateur ; le cloisonnement de la
co-traitance ; aucune base de données modifiée ; les alertes lisent toujours 25 résultats par recherche, et le courriel
ne donne aucune note sur 100.

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
  comme avant (la correspondance 2A/2B par code postal n'est pas ajoutée). *Réunion (§ R.1) : le BOAMP écrit la
  Corse « 20A » / « 20B » ; ses avis sont désormais demandés sous les deux formes et lus « 2A » / « 2B ».*
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
n'est pas concernée.

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
