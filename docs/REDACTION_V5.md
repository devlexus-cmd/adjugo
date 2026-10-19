# Rédaction, vague 5 — « Coller au chantier et à l'acheteur » : contrat

Étude « rédaction » (`etudes/redaction.md`) § 8 (V5) : l'entretien chantier (D, § 6.9), la liste complète des
exigences et les sous-critères (C2 complet, § 6.3), les références tirées des DECP et les qualifications RGE (E2,
§ 6.7) ; doctrine § 7 ; décisions § 10 (7 à 11).

Base de production : `da9ef0f` (branche `feat/produit-acheteur-collectivites`) au départ des trois chantiers, puis
`b010c59` (documents déposés par le lien, migration `y9z0depotlien`), fusionnée par C2 et D pendant leur travail.
Les trois chantiers sont réunis dans une seule branche (section **I**), au-dessus de `b010c59`.

Décisions appliquées (recommandations de l'étude, validées par Eliot) :
- **D7 (b)** l'import DECP est PROPOSÉ, l'utilisateur coche (E2) ;
- **D8 (a)** CV et noms jamais à l'IA (D : liste « Équipe » ; E2 n'appelle aucune IA) ;
- **D9 (a)** mention « préparé avec assistance IA » dans les propriétés du fichier (déjà en place, inchangée) ;
- **D10 (c)** pas de contrôle de ressemblance entre clients ;
- **D11 (c)** on MESURE combien de dossiers importés imposent leur propre fichier de réponse (agrégat interne
  pour l'administrateur, aucun contenu) ; l'avertissement et le Word dans l'ordre du cadre sont gardés (C2.9).

La doctrine (§ 7) vaut pour tous les chantiers : un fait ne vient jamais de l'IA (« déclaré par vous » pour une
réponse de l'entretien, « source publique » datée pour DECP et RGE, « marché attribué » et jamais « réalisé ») ; on
ne dit jamais « vérifié » ; toute phrase du dossier affichée est retrouvée mot pour mot (`citation_guard`) ; le
cadre de l'acheteur commande ; la matière reste chez son propriétaire (une question posée à un partenaire part
dans SON espace, sa réponse est SA donnée) ; `tenant_scope` et `pii_scope` sur chaque appel d'IA, remboursement si
l'IA tombe ; un seul process ; le maximum se fait sans IA.

Ce contrat est écrit par chantier : chaque chantier a sa section (C2, D, E2), les sections ne se recouvrent pas ;
la section I dit ce que la réunion a ajouté aux jointures et comment le parcours complet est vérifié.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« valider » (jamais « signer »), jamais « consortium », jamais « vérifié ». Zéro émoji, explications dans une
bulle (i), compact, rien collé aux bords, lisible à 375 px. Le menu n'est pas réorganisé.

| Section | Chantier | Migration | IA |
|---|---|---|---|
| C2 | « Comment vous serez noté » complet : sous-critères, exigences, environnement, R2142-21, mode « sans IA », questions à l'acheteur, mesure D11 | aucune | propositions de l'analyse existante, contrôlées |
| D | L'entretien chantier : « n questions sur ce chantier », fiche chantier [R#] | `z1entretienchantier` (après `y9z0depotlien`) | bouton facultatif, 4 questions au plus, remboursé |
| E2 | « Mes preuves » depuis DECP et la liste RGE de l'ADEME ; historique de groupement du réseau | aucune | aucune |
| I | Réunion des trois chantiers, jointures, parcours complet, vérifications | — | — |

---

## C2 — « Comment vous serez noté » complet : ce que le dossier demande

Source de vérité du code :
- sous-critères : `app/services/grille_notation.py` (§ « C2 complet (vague 5) : les sous-critères »,
  `_attacher_sous`, `_sous_reperes`, `_sous_ia`, `_controle_sous`, `relire`) ;
- exigences, règle « traitée », environnement, candidatures multiples, IA, questions, date limite des
  questions : `app/services/grille_exigences.py` (nouveau, fonctions pures : ni IA, ni réseau, ni base) ;
- plan de l'atelier : `app/services/atelier_plan.py` (`parties_du_critere`, `sections_de_sous_criteres`,
  `sous_critere_de`, `est_partie_de_sous_critere`) ;
- atelier : `app/services/atelier.py` (`_rangs`, `parents_affiches`, `sous_criteres_out`, `exigences_out`,
  `mode_sans_ia`, `exiger_ia_permise`, `sans_ia_out`, `definir_options`, `mesure_fichier_impose`) ;
- garde « sans IA » aussi dans `atelier_groupement.lancer_aide` et `atelier_assemblage.lancer_harmonisation` ;
- consigne de rédaction : `app/services/agents/memoire.py` (`_consigne_partie`) ;
- consigne d'analyse : `app/services/analysis.py` (`SYSTEM_PROMPT`, `VERSION_CONSIGNES = "2"`, `_HORS_FAITS`) ;
- routes : `app/routers/sourcing.py` (`/grille/element`, `/grille/exigence`, `/grille/relire`),
  `app/routers/atelier.py` (`sans_ia` dans `POST /{pid}` et `PUT /{pid}/options`) ;
- écrans : `app/static/app.js` (composant `grille-carte`, `aoGrille*`, `atlSansIa*`, `atlEx*`),
  `app/static/app.html` (atelier), `app/static/invite.html` (`renderGrille`), `app/static/redaction-partenaire.js` ;
- démo : `app/services/demo_redaction.py` (`_VERSION = "3"`, trois phrases du règlement, une question proposée) ;
- tests : `tests/test_redaction_v5_c2.py` (et l'inventaire de `tests/test_demo_sans_cout.py`).

Aucune migration : la grille vit dans `projects.ai_analysis.details.grille_notation` (JSON), le mode « sans IA »
dans `dossiers_presentation.options_export["sans_ia"]` (JSON), la mesure de la décision 11 dans les colonnes
de la vague 2 (`projects.dce_importe_le`, `dce_fichier_impose`).

### C2.1 Décisions appliquées

| Décision | Retenu (validé par Eliot) | Effet dans C2 |
|---|---|---|
| D8 (a) | CV et noms jamais à l'IA | Rien de nouveau ne part à l'IA : la vague 5 C2 n'ajoute AUCUN appel. Les sous-critères passés à la consigne de rédaction sont des phrases de l'acheteur. |
| D9 (a) | Mention « préparé avec assistance IA » dans les propriétés du fichier | Inchangée : elle dépend de l'usage réel de l'IA (`v.ia`). Le mode « sans IA » ne la retire pas pour un texte déjà préparé avec l'IA ; l'écran compte ces parties (« réécrivez-les vous-même si le règlement l'exige »). |
| D10 (c) | Pas de contrôle de ressemblance entre clients | Rien de construit. |
| D11 (c) | MESURER, garder l'avertissement et le Word dans l'ordre du cadre | `mesure_fichier_impose` dit en plus si le seuil (un dossier sur cinq) est atteint (§ C2.9). |

### C2.2 Ce qui est déterministe, ce qui relève de l'IA

**Sans IA (tout est calculé sur le texte déjà extrait, chaque phrase repasse par `citation_guard`)** :
sous-critères repérés, exigences repérées, règle « traitée », environnement, candidatures multiples, mention
de l'IA, questions repérées, date limite des questions, contrôle des totaux, relecture d'un marché d'avant
la vague 5 (`/grille/relire`, rien n'est débité).

**L'IA PROPOSE, dans l'appel d'analyse qui existe déjà (aucun appel de plus)** — consigne `SYSTEM_PROMPT`,
reprise mot pour mot par `SYSTEM_EXTRACTION` :
- `criteres_attribution[].sous_criteres` : `[{critere, ponderation, extrait}]`, poids TEL QU'ÉCRIT ;
- `exigences_memoire` : 0 à 10 phrases recopiées littéralement (pas les pièces administratives, ni les prix,
  ni le dépôt) ;
- `questions_acheteur` : 0 à 3 `{question, extraits: [1 ou 2 phrases recopiées]}` ; chaque nombre de la
  question doit être dans ces phrases.

Contrôle de chaque proposition, sans IA :
- sous-critère : phrase retrouvée mot pour mot (`citation_guard`) dans le règlement ou le cadre, et qui parle
  de lui (`_names_ok`) ; sinon il n'est JAMAIS affiché. Poids retenu seulement s'il est écrit dans la phrase
  et rattaché à lui (`_attribute`, comme les critères) ; sinon « poids à vérifier ». Nombre sans unité
  (« Méthodologie (20) ») : retenu tel quel seulement si CHAQUE sous-critère du critère en a un et que leur
  somme fait le poids du critère ;
- exigence : phrase retrouvée mot pour mot ; son libellé est TIRÉ DE LA PHRASE (objet après le verbe
  d'exigence, sinon la phrase), jamais écrit par l'IA ; les mêmes exclusions que le repérage s'appliquent,
  la phrase relue dans son unité du dossier (`_ecartee_comme_au_reperage`) — et, pour un élément de liste, avec la
  phrase qui annonce la liste (« Le candidat joindra à son mémoire technique : ») : niée (« n'est pas tenu de »),
  facultative (« le candidat peut… », une demande « à titre facultatif », § C2.5), sujet suivi d'un mot qui l'exclut
  (« le candidat retenu… »), sous un article sur la candidature (§ C2.5 : « … des candidatures et des offres » n'en
  est pas un), ou tirée du CCTP / CCAP sans parler du candidat, du mémoire ni de l'offre → écartée et comptée comme
  un écart (`llm_qualite`) ;
- question : au moins une phrase retrouvée mot pour mot, question de 15 à 300 caractères finie par « ? »,
  aucun nombre absent des phrases retrouvées (nombres comparés un à un : « 1 » n'est pas dans « 10 ») ; sinon
  écartée.
Chaque citation acceptée ou rejetée est comptée par `llm_qualite.noter_citations` (surveillance par fournisseur).

Coût : la sortie de l'analyse grandit d'environ 300 à 1 700 tokens au plus (plafonds 10 exigences, 3
questions, sous-critères), dans le même appel ; `ANALYSE_MAX_TOKENS` (6 000) inchangé. La partie propre à
l'entreprise (analyse partagée) ne reçoit pas `exigences_memoire` ni `questions_acheteur` (`_HORS_FAITS`).
`VERSION_CONSIGNES = "2"` : l'analyse partagée ne ressert plus une extraction faite avec les anciennes consignes.

### C2.3 Données — la grille, version 2 (`grille_notation.VERSION = 2`)

Ajouts à la grille (tout le reste est celui de la vague 1) :

```
criteres[i].sous_criteres = [{id: "c2.1", critere, poids (tel qu'écrit, ou ""), poids_valeur, poids_unite,
                              phrase, source, statut: retrouve|a_verifier, origine: reperage|ia}]
criteres[i].controle_sous = {statut: ok|ecart|non_verifiable|sans_objet, message, total?, unite?, attendu?}
exigences = {liste: [{id: "e1"|"u1", texte, phrase, intro, source, origine: reperage|ia|utilisateur,
                      choix_utilisateur?: {choix: ecarte|traitee, le}}],
             compteurs: {total, reperees, proposees_ia, ajoutees, retirees, traitees_selon_vous}}
environnement = {dans_la_note, message, lieux: [{type: critere|sous_critere|phrase, libelle, poids, phrase, source}]}
candidatures_multiples = {seul_et_groupement, plusieurs_groupements, mandataire_unique: {phrase, source}|null,
                          messages: [{code, message, phrase, source}]}
ia = {mentionne, nature: interdit|declarer|mention|"", phrases: [{phrase, source, nature}], message, propose_sans_ia}
questions_acheteur = {liste: [{id: "q1", code, sujet, question, motif, origine: reperage|ia,
                               phrases: [{phrase, source}], choix_utilisateur?: {choix: ecarte}}],
                      date_limite: {phrase, source, date, jours_avant, type_jours, date_calculee, message}|null,
                      message, message_vide}
relue_le (après /grille/relire)
```

`public_grille` (vue des partenaires, lecture seule) ajoute : `criteres[].sous_criteres` (critère, poids,
phrase, statut), `criteres[].controle_sous` (statut, message), `exigences` (liste : id, texte, phrase,
retirée), `environnement`, `candidatures_multiples` (code, message, phrase), `ia` (mentionne, nature, message
pour le partenaire, phrases). Jamais de nom de fichier, jamais de date de choix, jamais les questions à
l'acheteur (c'est le chef de file qui les pose).

Reprise : `carry_over` (ré-analyse) et `relire` reprennent les choix (critères confirmés ou retirés, exigences
retirées ou dites traitées, questions retirées) par phrase ; une exigence ajoutée par l'utilisateur ne revient
que si sa phrase est encore dans le nouveau dossier (texte de la lecture intégrale ; sans ce texte, elle ne
revient pas).

### C2.4 Les sous-critères (point 1)

Repérage sans IA dans la zone qui suit chaque critère retrouvé (jusqu'au critère suivant, à un nouvel
« Article » ou à 2 000 caractères) :
- « Sous-critère 1 : … », « sous-critère n° 2 – … » (singulier, avec numéro ou séparateur ; « les sous-critères
  suivants » est une annonce, « sous-critères 1.1 à 1.5 » un renvoi) ;
- « 2.1 … » sous le critère « 2. … » (ou pondéré) ;
- « dont … », puces (« - », « a) », « i) », « 1) »…) pondérées, ou non pondérées quand la phrase qui ouvre la
  liste parle de notation (« apprécié selon les éléments suivants : ») ; des puces qui se suivent (séparées
  seulement par des blancs ou leur ponctuation de fin, « ; » « , » « . ») forment UNE liste, avec l'annonce de la
  première : une liste « a ; b ; c. » donne ses trois sous-critères ; une liste ouverte par « le mémoire
  comprendra : » est une liste d'EXIGENCES, jamais de sous-critères ;
- lignes pondérées sans marque (un tableau) : seulement si leur somme fait le poids du critère ;
- énumération en ligne après « selon : » dont chaque élément a un poids.
Rattachement : la liste est au critère de sa zone, sauf si ses poids font exactement le poids d'un AUTRE
critère (« Valeur technique 60 % ; Prix 40 %. » puis des sous-critères de 60 points au total), ou si la phrase
qui l'annonce nomme un autre critère. Jamais déplacée quand ses éléments portent la numérotation du critère de
la zone (« 1.1 », « 1.2 » sous « 1. Valeur technique ») : leur somme qui tombe sur le poids d'un autre critère
est alors un écart (`controle_sous` « ecart »), et la question `total_sous` est proposée.

Un sous-critère proposé par l'IA dont le poids n'est pas retrouvé reste dans la grille et dans le plan, sans
poids (« poids à vérifier » à l'écran).

Contrôle du total (`controle_sous`) : « ok » si la somme fait le poids du critère, ou 100 % en part du critère ;
« ecart » (même unité) ; « non_verifiable » sinon. Un écart devient une question à l'acheteur (§ C2.8).

À l'écran (carte « Comment vous serez noté ») : les sous-critères sous leur critère, poids tels qu'écrits,
« poids à vérifier » sinon ; leurs phrases dans « Voir les phrases du règlement ».

Dans le plan de l'atelier (plan tiré de la grille) : un critère qui a AU MOINS DEUX sous-critères retrouvés
donne une partie par sous-critère (intitulé et phrase du règlement), rangées sous le titre du critère
(`parents`), numérotées « 1.1, 1.2 » (`_rangs`) ; le fichier Word et le PDF écrivent le titre du critère une
fois au-dessus (`parents_affiches`). Un seul critère technique découpé par le règlement : ses sous-critères
font le plan (message `MSG_GRILLE_UN_CRITERE_SOUS`), ce n'est pas un découpage d'Adjugo (`partie_de_critere`
faux). Les parties des sous-critères d'un critère restent ENSEMBLE, sous un seul titre et un seul numéro :
« Monter / Descendre » une autre partie lui fait passer le groupe entier (`_hors_des_groupes`), une partie
ajoutée « après » l'une d'elles va après le groupe, une partie de sous-critère remise revient dans son groupe ; une
partie de sous-critère change d'ordre parmi les siennes mais n'en sort pas (409 `groupe_sous_criteres`, message
à afficher) ; un ordre ancien interrompu garde un numéro par critère (`_rangs`). La partie garde le critère, son
id et son poids de la grille : « Comment vous serez noté » reste la
seule source du plan, et `changements_grille` continue de comparer les critères. Chaque partie expose
`sous_critere` ({critere, poids, phrase}) ; la partie d'un critère non découpé expose `sous_criteres`.
La consigne de rédaction dit « SOUS-CRITÈRE DE L'ACHETEUR : … (poids écrit dans le règlement : …) » ou
« SOUS-CRITÈRES NOTÉS : … ». Le partenaire les lit dans « Ce que l'acheteur note » de ses parties.

### C2.5 La liste des exigences et la règle « traitée » (point 2)

Repérage sans IA (`grille_exigences._reperer`), dans le règlement, le cadre de réponse et les pièces « autre »
(le CCTP et le CCAP seulement pour une phrase qui parle du candidat, du mémoire ou de l'offre) :
- « le candidat / les candidats / le soumissionnaire » ou « le mémoire / l'offre technique / la note
  méthodologique / le cadre de réponse » + « devra / doit / est tenu de / est invité à … » + verbe, ou un verbe
  au présent ou au futur (« présentera », « précise », « comprendra », « décrira »…) ;
- « il est demandé / attendu / exigé (au candidat) de… », « il appartient au candidat de… », « une attention
  particulière sera portée à… », « … devront figurer dans le mémoire » ;
- dans un cadre de réponse : une question qui commence (début de ligne ou de phrase, après « Question 2 : »,
  « 2.1 » ou une puce) par un impératif ou un infinitif suivi de ce qui est demandé (« Décrivez la méthode… »,
  « Présentez l'encadrement… », « Préciser les moyens… » ; jamais « Décrire ne suffit pas ») ;
- une phrase qui finit par « : » ouvre une liste : une exigence par élément (puces, numéros, ou liste en
  ligne séparée par « ; »), avec la phrase d'annonce (`intro`) ; « … comprendra les éléments ci-dessous. » n'est
  qu'une annonce (jamais une exigence) : la liste qui suit est lue de même, sinon chaque phrase suivante seule.
Jamais : une pièce administrative ou un prix (DC1, DC2, DUME, Kbis, attestations, assurances, RIB, acte
d'engagement, bordereau, DPGF, DQE, chiffre d'affaires…), le dépôt (plateforme, date limite, format, pli,
signature), la visite, les variantes, ce que fait le candidat retenu ou le titulaire, ce qui est permis
(« peut », « pourra ») ou nié (« n'est pas tenu »), une DEMANDE facultative (« à titre facultatif », « de manière
facultative » qui qualifie le sujet ou le verbe — « présentera, à titre facultatif, ses certificats » —, ou tout
l'objet — « … un planning, à titre facultatif. » ; un élément facultatif coordonné à d'autres — « la méthodologie
et, de manière facultative, des photographies » — sort seul du libellé, la phrase citée reste entière ; le mot seul,
« (annexes facultatives) », « la visite est facultative », ne compte pas), une phrase d'un article sur la
candidature (« Conditions de participation »… ; le titre le plus proche décide, lu sur SA ligne : un sous-titre
numéroté « 5.1 Pièces de la candidature » / « 5.2 Contenu de l'offre » avant l'article qui l'englobe, et un titre
qui nomme aussi l'offre ou le mémoire — « Présentation des candidatures et des offres » — n'est pas un article sur la
candidature ; même règle pour l'entretien chantier), « justifier d'une capacité », « une offre conforme », l'obligation d'utiliser
le cadre (déjà dans « Ce que le dossier impose »), une simple limite de longueur (« au maximum 10 pages » ; mais
« l'encadrement du chantier (2 pages maximum) » est bien une exigence). Une exigence sans mot principal (« un
mémoire technique ») n'est pas gardée. Au plus 40, dans l'ordre du dossier.

Une phrase est l'« unité » qui contient la marque : coupée aux fins de phrase, aux puces, aux titres (ligne
courte sans ponctuation finale, « Article 5 - … ») ; un retour à la ligne de mise en page ne coupe pas.

**La règle « traitée », explicite et testée** (`grille_exigences.traitement`, texte `REGLE_TRAITEE`) :
1. les mots principaux d'une exigence sont les mots de son libellé (sinon de sa phrase), sans mots vides ni
   mots qu'on trouve dans toute exigence (« candidat », « mémoire », « présenter », « préciser », « pages »,
   « travaux »…), réduits à leurs 5 premières lettres (« déchets » ↔ « déchet »), au plus 8 ; « chantier » et
   « entreprise », présents dans tout mémoire du BTP, restent des mots de l'exigence (« une présentation de
   l'entreprise », « l'organisation du chantier » sont gardées et gardent leurs deux mots), mais la règle
   « traitée » ne les cherche pas quand il reste au moins deux autres mots principaux (`cles_traitement` : « la
   gestion des déchets du chantier » n'est pas traitée par une partie qui parle du chantier sans nommer les
   déchets ; une exigence n'est jamais ramenée à un seul mot) ;
2. elle est **traitée** quand le texte d'UNE partie, sans ses « [À compléter : …] », en reprend : tous s'il y
   en a un ou deux ; sinon au moins la moitié, et au moins deux (`requis(k)`) ;
3. la partie qui en reprend le plus l'emporte (puis la première du plan) : « traitée dans 3. Démarche
   environnementale » ;
4. l'utilisateur peut la dire traitée lui-même (« traitée, selon vous ») ou la retirer (« ce n'est pas une
   exigence » : hors du compte) ;
5. le texte lu est celui que le lecteur voit (`versions_communes` pour le chef de file, `textes_communs` pour
   un partenaire) : jamais le brouillon d'un autre.
Résultat : « 5 exigences traitées sur 7 » et « Il manque : « … », « … ». » (au-delà de trois : « Il en manque
4 : voir la liste. »), à la place de toute note de conformité. C'est un repérage de mots, pas une relecture,
et l'écran le dit dans la bulle. Il ne bloque pas l'export (information).

À l'écran : carte du marché (« Ce que le dossier demande » : nombre, liste repliée avec phrase et pièce,
« Retirer : ce n'est pas une exigence », « Ajouter une exigence » en collant la phrase, retrouvée mot pour mot
sinon refusée) ; atelier (« 5 exigences traitées sur 7 », « Il manque… », liste : statut, partie qui la traite
avec lien, phrase, « Je la traite déjà », « Retirer », « Annuler mon choix ») ; carte de l'atelier sur la page
du marché (le compte) ; partenaire : la liste et le compte d'après les textes communs (section « Le dossier
assemblé »), et la liste en lecture dans « Comment vous serez noté » (lien).

### C2.6 L'environnement, en information neutre (point 3)

`environnement.dans_la_note` quand un critère ou un sous-critère retenu en parle (nom ou phrase), ou une phrase
de la zone « critères » du règlement qui parle aussi de notation. Message : « L'environnement compte dans la
note : voici où il apparaît dans le règlement. », puis les lieux (critère · poids, phrase). Une clause
d'exécution sur les déchets n'est pas « dans la note ». Aucun conseil, aucune note.

### C2.7 Répondre seul et en groupement, plusieurs groupements (point 4)

Phrases du règlement (ou de l'avis) qui INTERDISENT : répondre à la fois seul et en groupement (R2142-21, 1°),
être membre de plusieurs groupements (2°), être chef de file de plus d'un groupement. Une phrase qui le permet
(« n'interdit pas », « peuvent présenter plusieurs offres ») n'est jamais lue comme une interdiction. Avertissement
dans « Ce que le dossier impose » (chef de file et partenaires), phrase dans « Voir les phrases ».

### C2.8 L'intelligence artificielle dans le règlement et le mode « sans IA » (point 5)

Repérage : « intelligence artificielle », « IA », « ChatGPT », « outil de génération de texte »… dans le
règlement, le cadre ou l'avis, dans une phrase qui parle de l'offre (mémoire, offre, rédaction, réponse, candidat,
dossier, document) : un marché qui ACHÈTE un outil d'IA ne déclenche rien. Nature : `interdit` (« sans recours à… », « ne doit pas être rédigé par… »),
`declarer` (« indique s'il a eu recours à… », ou « n'est pas interdit ; le candidat le signale »), `permis`
(« n'est pas interdit », « est autorisé, sans restriction » : une phrase qui PERMET l'IA n'est jamais lue comme
une interdiction — l'expression qui permet est retirée avant de chercher une interdiction dans la phrase ;
message `MSG_IA_PERMIS` « Le règlement admet l'intelligence artificielle : lisez la phrase. Vous restez libre de
rédiger ce dossier sans IA. », aucune question à l'acheteur), sinon `mention` (et alors une question à l'acheteur
est proposée). La phrase est affichée sur la carte, dans l'atelier (avant la création du plan aussi) et chez les
partenaires (message propre : « Le chef de file choisit si le dossier se rédige sans IA »).

**Le mode « sans IA »** (pour CE dossier, choisi par le chef de file, proposé quand le règlement parle d'IA,
toujours possible par la case « Rédiger sans IA ») — sur la carte du marché, le bouton « Rédiger sans IA » n'est
proposé que sur un ordinateur (écran étroit : « Rédiger sans IA se choisit depuis un ordinateur, dans
l'atelier. ») et tant que le dossier n'est pas déjà « sans IA » (« Ce dossier se rédige sans IA. ») ; une case
des options de l'export refusée (démo, réseau, 409) revient à l'état enregistré :
- rangé dans `options_export["sans_ia"] = {actif, le, par}` ; `PUT /api/atelier/{pid}/options {sans_ia}`
  (ou `POST /api/atelier/{pid} {base, sans_ia: true}` à la création) ; inscrit au journal chaîné
  (`atelier.sans_ia`, « mode sans IA activé / retiré ») ; la réponse de `/options` garde `options =
  {page_garde, sommaire}` (contrat de la vague 2) et ajoute `sans_ia` ;
- AUCUN appel d'IA de rédaction : « Rédiger », « Rédiger tout », « Raccourcir » (`at.lancer`), l'aide de l'IA
  du partenaire (`ag.lancer_aide`) et « Harmoniser le ton » (`asm.lancer_harmonisation`) → 409
  `mode_sans_ia` ; les boutons disparaissent (atelier, espace du partenaire) et « J'écris moi-même » devient
  le bouton principal ; « Harmoniser » n'est plus proposé (`harmoniser.jonctions = 0`) ;
- le contrôle des faits (`fs.controler`, sans IA) et la liste des exigences continuent ; les documents déposés par
  le lien d'un partenaire (décision 5 a) ne servent qu'à l'aide de l'IA : ils restent chez lui, sans effet tant que
  le dossier est « sans IA » ;
- une tâche lancée avant le choix va au bout (elle était déjà engagée) ; la mention IA des propriétés du fichier
  suit l'usage réel (D9) et l'écran compte les parties dont le texte courant a été préparé avec l'IA ;
- `etat.sans_ia = {actif, le, message, parties_ia, reglement: {mentionne, nature, message, phrases}}` ;
  `vue_partenaire.sans_ia = {actif, message}`.

### C2.9 Questions à poser à l'acheteur (point 6) et mesure de la décision 11 (point 7)

Repérées sans IA, chacune avec ses phrases (au plus 8) :

| code | quand | question proposée |
|---|---|---|
| `total_poids` | les poids des critères ne font pas 100 % (ou le total annoncé), TOUS les critères retrouvés avec leur poids écrit, aucune ligne à vérifier, et AUCUN autre poids écrit dans la zone des critères (sinon Adjugo a peut-être manqué un critère : pas de question) | « Les poids … font 90 % au total, et non 100 %. Pouvez-vous confirmer la pondération des critères ? » |
| `total_sous` | `controle_sous.statut == "ecart"` | « Les sous-critères de « … » font 50 points au total, alors que le critère vaut 60 points… » |
| `cadre_absent` | fichier de réponse imposé mais absent des pièces | « … pouvez-vous indiquer où le trouver, ou le transmettre ? » (à poser si on ne le trouve pas sur la plateforme) |
| `limites` | deux limites différentes du même type pour le mémoire entier (sans « annexes », « hors », « compris », « par », « chaque »…) | « … 10 pages et 15 pages. Laquelle s'applique ? » |
| `visite` | visite obligatoire à un endroit, facultative à un autre | « … Pouvez-vous préciser si la visite est obligatoire ? » |
| `date_remise` | deux dates limites de remise DES OFFRES différentes (jamais celle des candidatures), sans pièce modificative ni phrase de report (« initialement fixée… reportée… ») | « … le 12/06/2026 et le 15/06/2026. Laquelle fait foi ? » |
| `ia` | l'IA est évoquée sans règle claire (`mention`) | « Un outil d'aide à la rédaction, dont le candidat relit, corrige et valide chaque phrase, est-il admis ? » |
| `ia_proposee` | proposée par l'IA de l'analyse, contrôlée (§ C2.2) | la question de l'IA |

Date limite des questions (`date_limite_questions`) : une phrase sur les questions des candidats qui dit QUAND
les poser (« au plus tard le 05/06/2026 » : date écrite ; « 6 jours avant la date limite de remise » : le délai,
et une date calculée seulement en jours simples quand une seule date de remise est écrite, dite « calculée par
Adjugo … : vérifiez-la » ; jamais pour des jours francs ou ouvrés). Une date écrite APRÈS le délai est classée
par ce qui l'introduit : « fixée au », « prévue le », « des offres du » (« … 6 jours avant la date limite de remise
des offres, fixée au 15/12/2026 ») donnent la date de la REMISE : le délai est dit, la date est calculée
(09/12/2026, « calculée par Adjugo ») ; la date de remise de la même phrase sert quand aucune autre n'est repérée.
« soit le », « soit jusqu'au », « c'est-à-dire le », « à savoir le » (« … 10 jours avant la date limite de remise
des offres, soit le 05/12/2026 ») donnent la date des QUESTIONS, écrite dans le règlement : rien n'est calculé, et
elle n'est jamais comptée comme une date de remise (pas de fausse question `date_remise`). Sans l'une ni l'autre
introduction : rien n'est calculé, la phrase est montrée. « Les réponses seront envoyées… » n'est pas cette date.

À l'écran (chef de file seulement) : la date limite, « Adjugo n'envoie rien : c'est vous qui posez les questions sur
la plateforme de l'acheteur, avant le … », chaque question avec ses phrases, « Copier la question » (la question
et ses phrases entre guillemets) et « Retirer ». Sans question : « Adjugo n'a repéré ni contradiction ni point
flou sur ce qu'il contrôle (…). Le règlement fait foi. »

Mesure D11 (`mesure_fichier_impose`, route administrateur `GET /api/admin/mesures/redaction` et `/metrics`) :
`{dossiers_importes, fichier_impose, part, seuil_decision: 0.2, atteint, message}` — agrégat seulement, aucun
contenu, posé à chaque import réel (`mesurer_import`, inchangé ; la démo n'y entre pas). On garde
l'avertissement et le fichier Word dans l'ordre du cadre ; `atteint` dit quand passer à la décision 11 (b).

### C2.10 Routes

Authentification `Bearer`, marché de l'organisation (sinon 404). Aucune n'appelle l'IA, aucune ne débite.

| Route | Corps | Effet |
|---|---|---|
| `POST /api/sourcing/grille/element` | `{project_id, type: exigence\|question, element_id, choix}` (`ecarte`, `traitee` — exigence seulement —, `annule`) | `{grille_notation}` ; 422 si l'élément n'existe plus ou le choix ne vaut pas pour ce type ; journal `grille.exigence` / `grille.question` |
| `POST /api/sourcing/grille/exigence` | `{project_id, phrase}` | ajoute une exigence dont la phrase est retrouvée MOT POUR MOT dans le dossier (`citation_guard`), sinon 422 ; journal `grille.exigence` |
| `POST /api/sourcing/grille/relire` | `{project_id}` | relit le dossier (lecture rangée, sinon relecture bornée du fichier) et refait la grille v2 sans IA, choix repris ; 409 `pas_de_dossier` / `dossier_illisible` ; journal `grille.relire` |
| `PUT /api/atelier/{pid}/options` | `{page_garde?, sommaire?, sans_ia?}` | `{options: {page_garde, sommaire}, sans_ia}` |
| `POST /api/atelier/{pid}` | `{base, sans_ia?}` | crée le dossier, « sans IA » dès la création si demandé |
| `GET /api/atelier/{pid}` | — | ajoute `exigences` et `sans_ia` (sans dossier : `sans_ia` avec la phrase du règlement) |

Démo : les trois routes de la grille sont refusées par le garde central (`demo_guard._BLOCKED`, « vitrine »)
et classées dans `tests/test_demo_sans_cout.py` ; `PUT /options` l'était déjà.

### C2.11 La démo (vitrine, sans IA ni réseau)

Le règlement fictif du marché « toiture » gagne trois phrases (`_VERSION = "3"`, nouvelles clés de stockage) :
l'interdiction de répondre seul et en groupement (article 2), « Le mémoire technique indique si le candidat a eu
recours à un outil d'intelligence artificielle pour le rédiger. » (article 5) et la date limite des questions
(18/12/2026, article 9) ; l'extraction rédigée pour la démo propose une question (comme elle propose les
critères), contrôlée sans IA. La vitrine montre : 7 exigences, « 5 exigences traitées sur 7 » et les deux qui
manquent (la phrase sur l'IA, le planning par phase), l'environnement dans la note, l'avertissement R2142-21,
la phrase sur l'IA (« signaler l'usage ») avec « Rédiger ce dossier sans IA » (refusé à la démo : lecture
guidée), une question à poser avant le 18/12/2026. Le plan et les textes de l'atelier ne changent pas.

### C2.12 Limites connues (dites honnêtement)

- La règle « traitée » est un repérage de mots : une partie qui cite les mots sans répondre est comptée
  traitée, une réponse écrite avec d'autres mots ne l'est pas. L'écran le dit et laisse l'utilisateur trancher.
- Les motifs d'exigences ne voient pas tout (« sont à exposer dans l'offre ») : l'IA de l'analyse en propose,
  et l'utilisateur peut en ajouter une en collant sa phrase. Ils peuvent aussi prendre une phrase qui n'est pas
  une exigence du mémoire : « Retirer ».
- Les sous-critères repérés après la création du plan n'y entrent pas d'eux-mêmes (`changements_grille`
  compare les critères) : « Reconstruire le plan » les prend. Un critère confirmé ensuite arrive avec ses
  sous-critères (`appliquer_grille`).
- Les questions repérées couvrent des contradictions précises ; un point flou d'une autre nature n'est vu que si
  l'IA de l'analyse le propose. La date calculée des questions est dite comme telle.
- Un marché analysé avant la vague 5 n'a ni sous-critères ni exigences tant qu'on ne le relit pas (« Relire le
  dossier, sans IA » sur la carte) ; les propositions de l'IA n'existent que pour les analyses faites après.
- La qualité des propositions de l'IA n'a pas été mesurée sur de vrais dossiers (aucun appel réel ici) : la
  surveillance `llm_qualite` compte les citations rejetées par fournisseur.

### C2.13 Choix faits par défaut (à valider par Eliot)

1. Les propositions de l'IA passent dans l'appel d'analyse existant (aucun appel de plus) plutôt qu'un appel
   à part ; `VERSION_CONSIGNES` passe à « 2 ».
2. Le mode « sans IA » est rangé dans les options du dossier (aucune migration) et se règle dans l'atelier ; la
   carte du marché propose « Rédiger sans IA » et ouvre l'atelier sur ce choix.
3. Les questions à l'acheteur restent au chef de file (les partenaires ne les voient pas) ; les exigences et
   les avertissements sont lus par tous les membres.
4. La règle « traitée » ne bloque pas l'export : c'est une information (un repérage de mots ne doit pas empêcher
   de déposer).
5. La démo ajoute trois phrases réalistes à son règlement fictif (aucune contradiction inventée chez l'acheteur).

### C2.14 Tests

Vérifications faites : suite complète verte (1 689 tests sur `da9ef0f` + C2 ; 1 732 après la fusion de `b010c59`),
SRI, `node --check`, gabarits compilés ; aucune migration : un vrai Postgres 16 monté à la tête de production
(`x8y9redactionv4`, puis `y9z0depotlien` après la fusion) fait passer les tests de C2, de l'atelier, de la grille, de la
démo et du groupement (292 puis 321 tests) ; écrans vus à 375 px et sur ordinateur (carte du marché, atelier, espace
du partenaire).

`tests/test_redaction_v5_c2.py` : sous-critères (explicites rattachés par leur somme, numérotés, liste annoncée,
tableau, nombres sans unité, aucun faux positif, propositions de l'IA contrôlées, contrôle du total, vue des
partenaires) ; plan (parties par sous-critère, numéros 1.1, titre au-dessus dans l'export, consigne de
rédaction) ; exigences (repérées avec leur phrase et rien d'autre, propositions de l'IA, choix, ajout, reprise
à la relecture) ; règle « traitée » (explicite) ; environnement ; R2142-21 (interdit, permis) ; IA (trois
natures) ; questions (total, pas de question si un critère a pu manquer, cadre, limites, visite, dates,
modificatif, date limite écrite ou calculée, questions de l'IA contrôlées) ; consigne d'analyse ; routes (sans
IA, organisation, démo refusée) ; atelier (« 3 exigences traitées sur 4 », « traitée selon vous ») ; mode sans
IA (409 partout, partenaire et harmonisation compris, contrôle des faits, journal, création) ; démo ; mesure
D11 ; textes des écrans. Suite complète verte, SRI à jour, `node --check`, gabarits compilés par le compilateur
de Vue.

---

## D — L'entretien chantier : « Adjugo demande au lieu de deviner »

Étude § 6.9, doctrine § 7, décisions **D8 (a)** (CV et noms jamais à l'IA), **D9 (a)** (mention « préparé avec
assistance IA » dans les propriétés du fichier, inchangée : l'entretien ne change pas la règle), **D10 (c)** (aucun
contrôle de ressemblance entre clients), **D11 (c)** (la mesure « fichier de réponse imposé » existe déjà :
`docs/REDACTION_V2_API.md` § 6 ; l'avertissement et le Word dans l'ordre du cadre sont gardés).

Code :
- banque de questions, sans IA : `app/services/entretien_banque.py` (41 questions BTP) ;
- règles (seul point d'écriture) : `app/services/entretien_chantier.py` ;
- routes : `app/routers/entretien.py` ;
- branchements : `app/services/atelier.py` (`Contexte.fiches`, `_executer`, `etat`, `creer_dossier`),
  `app/services/agents/memoire.py` (consigne de la partie), `app/services/atelier_groupement.py` (espace du
  partenaire, son aide de l'IA, RGPD), `app/services/faits_sources.py` (renvoi `R`), `app/services/memoire_export.py`
  et `app/services/faits_a_relire.py` (renvois `[R#]` retirés à l'export, ignorés au repérage) ;
- écrans : `app/static/app.html` + `app/static/app.js` (bloc « n questions sur ce chantier » de l'atelier,
  méthodes `atlEnt…`), `app/static/redaction-partenaire.js` (`renderEntretien`, `repondreQuestion`),
  `app/static/styles.css` (`.atl-ent…`, `.rp-ent…`) ;
- démo : `app/services/demo_entretien.py` (appelé par `demo_redaction.seed_redaction`) ;
- migration : `alembic/versions/z1entretien_entretien_chantier.py` (`z1entretienchantier`, après
  `y9z0depotlien`, la migration du dépôt de documents par le lien) ;
- tests : `tests/test_redaction_v5_entretien.py`.

Vocabulaire à l'écran : « questions sur ce chantier », « fiche chantier », « Passer », « Sans objet », « Posée
à », « groupement / partenaire / chef de file » ; jamais « vérifié », jamais « signer », zéro émoji.

### D.1 Ce que voit l'utilisateur

**Chef de file (atelier, page du marché).** Sous l'en-tête de l'atelier, une carte « 8 questions sur ce
chantier » avec sa bulle (i), une pastille (« 5 à répondre », « Toutes traitées ») et un bouton « Répondre aux
questions ». Elle se déplie d'elle-même à la première ouverture d'un atelier encore sans texte (« avant la
rédaction des parties notées »). Pour chaque question :
- la question, son renvoi (`R3`) et son statut (À répondre, Répondue, Passée, Sans objet) ;
- **la phrase du dossier qui la motive**, telle qu'écrite, et sa pièce (« Clauses techniques (CCTP) ») ; une
  question posée sans phrase (l'environnement, quand le dossier n'en dit rien) le dit : « Question posée pour tout
  chantier : aucune phrase du dossier lu n'en parle. » ;
- la partie concernée et le critère concerné, avec son poids tel qu'écrit ;
- la réponse : un texte court (1 500 caractères au plus) ; pour « Qui sera le chef de chantier ? », la liste
  « Équipe » de « Mes preuves » (nom et fonction, jamais le CV) et, au besoin, une précision écrite ;
- « Enregistrer la réponse », « Passer » (« la partie concernée gardera « [À compléter : chef de chantier] » »),
  « Sans objet » (rien ne sera écrit à ce sujet) ; « Modifier la réponse » ensuite ;
- en groupement (« Qui écrit quoi » préparé) : « Posée à » (Votre entreprise ou un partenaire) ;
- en bas : « Chercher d'autres questions avec Adjugo » (option IA, sur ordinateur), et « Fiche chantier (n) »
  repliée : renvoi, thème, réponse, « déclaré par vous » ou « déclaré par Breizh Couverture ».

Avant « Rédiger avec Adjugo » (une partie ou toutes), la fenêtre de confirmation de l'atelier le dit : « 3
questions sur ce chantier attendent une réponse : sans elle, Adjugo n'écrit rien à ce sujet et laisse « [À
compléter] » si la partie en a besoin… » et « Une question passée : sa partie gardera « [À compléter] ». ».

**Téléphone (375 px).** Répondre, passer, « sans objet » et « Posée à » restent possibles (l'écriture des
parties, elle, reste sur ordinateur) ; la recherche avec l'IA n'est pas proposée.

**Partenaire (son espace : lien + clé, ou « Partagé avec moi »).** Un bloc « 2 questions du chef de file sur ce
chantier » avec sa bulle (i) : la question, la phrase du dossier, la partie concernée, « Envoyer ma réponse »
(fenêtre : « Votre réponse sera lue par le chef de file, qui s'en servira pour rédiger le dossier commun comme un
fait déclaré par votre entreprise. »), « Passer », « Sans objet » ; « Modifier ma réponse » ensuite. La pastille
« n à faire » compte ses questions sans réponse ; la liste « Partagé avec moi » dit « 2 questions sur le chantier »
quand il n'a rien d'autre à faire.

### D.2 La banque et le déclenchement (sans IA)

- **41 questions BTP** (`entretien_banque.BANQUE`), chacune avec : ses déclencheurs (expressions cherchées dans le
  texte replié du dossier), les débuts de mots de ses critères (dans l'ordre), de ses parties et des lots, le
  passage « [À compléter : … ] » qu'elle laisse, sa famille (`environnement`) et son type de réponse (`equipe`
  pour le chef de chantier). Déclencheurs couverts : site occupé, établissement recevant du public, école et
  élèves, personnes fragiles, travaux de nuit ou décalés, amiante, plomb, voirie, co-activité, Architectes des
  Bâtiments de France, phasage, toiture, travail en hauteur, intempéries, dépose et démolition, réseaux,
  continuité de service, poussières, points chauds, levages, accès et livraisons, base vie, déchets, bruit et
  nuisances, réemploi, transports, pollution, arbres, environnement, chef de chantier, sous-traitance, insertion,
  périodes imposées, délai, visite, contrôles et essais, dossier des ouvrages exécutés, matériaux, garantie de
  parfait achèvement, information des riverains, sécurité des compagnons.
- **La pièce lue** : la lecture intégrale rangée (toutes les pièces) ; sinon l'ancienne lecture bornée ; sinon
  l'extrait de l'analyse. Ordre de recherche : cadre de réponse, CCTP, règlement, CCAP, autres pièces, acte
  d'engagement, bordereaux.
- **La phrase qui motive** (`phrase_du_dossier`) : une vraie phrase, de la fin de la précédente à sa propre fin, à
  travers les retours de ligne d'un PDF, sans traverser un intitulé ni une ligne vide ; à défaut une ligne courte
  (un critère : « Moyens humains et encadrement : 10 % »). Elle repasse par `citation_guard` (suite exacte du
  texte de sa pièce) ; une phrase déjà montrée par une question plus prioritaire n'est reprise que si le dossier
  n'en a pas d'autre. **Une phrase qui nie** (« aucune présence d'amiante », « les travaux de nuit ne sont pas
  prévus ») ne déclenche rien ; un intitulé d'un mot (« Article 2 - Amiante ») non plus. Une phrase sous un
  article sur la candidature (« Conditions de participation »…, même règle que la liste des exigences) ne motive
  une question qu'à défaut de toute autre.
- **Le classement** : le critère concerné est le premier début de mot de la question retrouvé dans un critère
  technique de « Comment vous serez noté » (le plus lourd s'il y en a plusieurs ; sinon le critère unique, ou le
  seul critère « technique ») ; son poids TEL QU'ÉCRIT classe la question (un sous-critère sans poids écrit se
  classe sur le poids ÉCRIT de son critère, sans qu'aucun poids lui soit attribué, et ses questions forment un
  groupe avec celles du critère ; l'écran dit « sous-critère : … · critère : Valeur technique (60 %) »). D'abord la meilleure question de chaque
  critère (du plus lourd au plus léger), puis la suivante de chacun, etc. ; une question qu'aucun critère ne
  concerne passe après ; à poids égal, l'ordre de la banque. **8 questions au plus.** L'écran les montre du critère
  le plus lourd au plus léger.
- **L'environnement déclenche toujours une question** : la meilleure question « environnement » déclenchée, sinon
  la question générale sans phrase du dossier (l'écran le dit).
- **La partie concernée** (`partie_concernee`) : celle où se retrouvent le mieux les débuts de mots de la question
  (intitulé, critère, question du cadre, titres parents) ; sinon celle du critère concerné ; sinon la première
  partie de méthode ou d'organisation ; sinon la première partie. Calculée à chaque lecture (le plan peut changer).
- **Préparation** (`preparer`, idempotente, sans IA ni débit) : avec le dossier de présentation (`creer_dossier`),
  puis de nouveau quand le plan est reconstruit (le dossier du marché est relu) et quand « Qui écrit quoi » est
  préparé ; l'écran prépare à la première ouverture un dossier d'avant la vague 5 (`POST /entretien`). Une question
  déjà posée garde son numéro, sa réponse et son destinataire choisi à la main ; une question de la banque qui
  n'est plus proposée (dossier réimporté) et sans réponse est retirée (ligne gardée, numéro réservé) ; la phrase
  d'une question sans réponse suit le dossier actuel ; le destinataire d'une question sans réponse jamais choisi à
  la main suit la répartition.

### D.3 La fiche chantier : des faits « déclaré par vous » pour l'atelier

- Chaque réponse est un fait numéroté **`[R3]`** (numéro STABLE dans le dossier, jamais réutilisé), remis à l'IA
  et au contrôle des faits (A) avec les autres faits autorisés :
  `[R3] (déclaré par vous) Entretien chantier, réponse à « Le site reste occupé… ? » : Accès des compagnons par le
  portail nord…`. Pour le contrôle, la fiche porte le thème FIXE de la banque et la réponse (le nom de la personne
  choisie compris) — jamais le thème d'une question proposée par l'IA, écrit par l'IA : un nombre ou un nom qu'il
  porterait deviendrait « déclaré par vous » ; pour l'IA, la question et la réponse (l'étiquette de la personne,
  jamais son nom).
- **Chef de chantier (D8 a)** : la personne choisie dans « Mes preuves » (fiche « Équipe » acceptée et utilisable)
  est remise sous son étiquette (`[Cheffe de chantier 1], Cheffe de chantier (sa fiche : [F7])`) : son nom est
  masqué avant l'appel (`pii_scope`), remis en clair sans IA dans le texte rendu ; son CV s'insère tel quel par
  « [CV F7] » (inchangé, `fs.inserer_cv`). Une fiche retirée ou expirée : la réponse ne sert plus (l'écran le dit :
  « La fiche « Équipe » choisie n'est plus utilisable… »), la question laisse « [À compléter] ».
- **Les noms dans une réponse écrite** : repérés sans IA comme les autres faits remis (`equipe_avec_noms_reperes`)
  et masqués avant l'appel.
- **La consigne de la partie** (`memoire._consigne_partie`) : « ENTRETIEN CHANTIER : les réponses [R2], [R5]
  concernent cette partie : sers-t'en ici (avec leur renvoi), sans rien y ajouter. » ; puis les points passés
  (« n'écris AUCUN texte général à leur place ; écris seulement… le passage indiqué tel quel : [À compléter : chef
  de chantier] ») et les questions encore sans réponse (« n'écris aucun fait à leur sujet ; si la partie doit en
  parler, écris le passage indiqué tel quel… »).
- **Une question PASSÉE laisse son « [À compléter : … ] » dans la partie concernée** : consigne de l'IA, puis,
  sans IA, le passage est ajouté en fin de partie s'il manque (`garantir_manques` ; pas de doublon si l'IA l'a
  écrit, même avec un autre libellé du même objet). Il bloque l'export comme tout « [À compléter] » (décision 2b,
  dérogation possible). « Raccourcir » le garde aussi : chaque « [À compléter] » du texte de départ reste dans le
  texte raccourci, remis sans IA en fin de partie s'il a disparu (`garder_trous`, chef de file et partenaire).
  **Une question encore sans réponse** : l'IA n'écrit aucun fait à son sujet et laisse le
  passage si la partie doit en parler (consigne), l'écran prévient avant de rédiger. **« Sans objet »** : rien.
- **Contrôle des faits (A)** : un fait de la phrase relié à `[R3]` porte la source `{ref: "R3", type: "declare",
  libelle: "déclaré par vous"}` ; une réponse modifiée après la rédaction est relue au prochain « Recontrôler »
  (comme le profil). Les renvois `[R#]` sont retirés à l'export (`clean_markdown`), montrés comme les autres
  renvois à l'écran (`atlRefs`, `rpTexte`).
- Rien ne change pour un marché sans entretien (aucune question) : aucun fait `[R#]`, aucune consigne.

### D.4 Groupement : la question du lot d'un partenaire, posée dans SON espace

- **Proposition, sans IA** (« Qui écrit quoi » préparé) : le partenaire à qui la partie concernée est confiée ;
  sinon celui dont le lot, et lui seul, correspond à la question (débuts de mots `lots` : « Couverture et
  zinguerie » ↔ accès à la toiture) ; sinon votre entreprise. Le chef de file change le destinataire (« Posée à ») ;
  un choix fait à la main n'est jamais repris par une préparation suivante.
- **Le partenaire la lit et y répond chez lui** : `GET …/redaction` → `entretien` (seulement les questions qui LUI
  sont posées) ; `PUT …/redaction/entretien/{qid}`. Mêmes garde-fous qu'un envoi : clé de l'espace par le lien
  (403 `cle_espace_requise`), avertissement lu (422 `avertissement_requis`, message à afficher), identité prouvée
  quand le lien vise une adresse (403 `identity_unverified`), co-construction ouverte, démo refusée avant tout.
  Comme ses autres écritures (contrat V4 § 21), le verrou de l'invitation est pris D'ABORD, avant celui de la
  question : l'invitation est relue, la clé présentée doit encore ouvrir l'espace (409 `espace_reinitialise`,
  rien d'écrit, l'écran se recharge) et le lien être actif (retiré entre-temps : 404 `question_introuvable`).
  Inscrit au journal chaîné (`entretien.reponse`, son journal : « Vous avez répondu à une question du chef de file
  sur le chantier »). Une réponse envoyée reste quand l'espace privé est réinitialisé (comme un texte envoyé) ;
  ses documents déposés par le lien (« Vos documents pour Adjugo ») ne sont jamais lus par l'entretien.
- **Sa réponse est SA donnée** : le chef de file la lit (« déclaré par Breizh Couverture ») sans pouvoir la
  modifier (403 `question_d_un_partenaire` sur sa propre route) ; dans son atelier elle est un fait
  `T_PARTENAIRE` (« déclaré par votre partenaire ») qui n'appuie qu'une phrase qui nomme ce partenaire (règle
  « qui affirme quoi » de A). Adresser la question à un autre la sort de la fiche chantier (409
  `reponse_a_confirmer`, puis effacée) ; retrait ou déclin de l'invitation : ses réponses sont effacées, ses
  questions reviennent au chef de file, à répondre. Une réponse de partenaire effacée ou changée (retrait, déclin,
  question reprise avec confirmation, réponse retirée, passée ou modifiée par lui) est aussi OUBLIÉE DES FAITS qui
  la citaient (`oublier_reponses`) : dans les versions du dossier du chef de file et dans les brouillons de ce
  partenaire, la copie du passage part et le fait redevient « à relire » (l'export le dit : `faits_a_relire`),
  comme pour un document déposé par le lien. Pendant une rédaction par l'IA (chef de file : « Rédiger »,
  « Raccourcir » ; partenaire : son aide), le texte est rangé sous le verrou des invitations qui ont répondu (pris
  d'abord ; `verrouiller_repondants`, ou celui de SON invitation), avec la fiche chantier RELUE à ce moment
  (`sans_reponses_changees`) : une réponse retirée, changée ou reprise, ou un partenaire retiré pendant l'appel, ne
  laisse ni son passage ni sa source dans la nouvelle version (le fait redevient « à relire ») ; arrivé après, il
  la nettoie (`oublier_reponses`). La reprise d'une question répondue par un partenaire (`adresser`) prend aussi le
  verrou de son invitation d'abord. Invitation coupée autrement (marché mis à la corbeille puis restauré,
  lien expiré) : sa réponse n'est plus montrée ni remise (fiche chantier, carte de la question avec
  `adresse.active = false`, export RGPD du chef de file), le chef de file qui veut répondre lit 403
  `question_partenaire_sans_acces` (« … qui ne peut plus y répondre (raison) : reprenez-la… ») et « Posée à »
  reste proposé ; la purge quotidienne (`ag.purger`) efface ses réponses et rend ses questions comme un retrait.
- **L'IA du partenaire** ne reçoit que SES réponses (« déclaré par vous » pour lui) et ses propres questions
  passées ou sans réponse de SA partie ; jamais les réponses du chef de file ni d'un autre membre. Celle du chef de
  file reçoit les réponses de ses partenaires encore membres.

| | Chef de file | Le partenaire questionné | Les autres membres |
|---|---|---|---|
| Questions posées à son entreprise, leurs réponses | oui | jamais | jamais |
| Question posée à un partenaire, la phrase du dossier | oui | oui | jamais |
| Réponse de ce partenaire | oui (en lecture, « déclaré par » lui) | oui (la sienne) | jamais |
| Liste « Équipe » de « Mes preuves » | oui (la sienne) | jamais | jamais |

### D.5 Option IA : « Chercher d'autres questions avec Adjugo »

- Tâche de fond du chef de file (`atelier_entretien`, dans `atelier.JOB_KINDS` : lue par
  `GET /api/atelier/{pid}/taches/{job_id}`, reprise au redémarrage avec le remboursement de l'atelier).
- **Compte sur le plafond de l'atelier (décision 6a)**, comme « Harmoniser le ton » : une refonte du dossier ; la
  première action de l'IA du dossier compte pour 1 analyse (la première rédaction de chaque partie y est ensuite
  comprise). 409 `debit_a_confirmer` au-delà des refontes gratuites (fenêtre de l'atelier). **Rendu si l'IA tombe ou
  si aucune question n'est retenue.** Garde-fou de l'essai (`budget_ia.verifier`, enveloppe `entretien` : 64 000
  caractères, 1 600 tokens en sortie).
- **Ce qui part à l'IA** : la consigne, les questions déjà posées, le dossier de l'acheteur (CCTP, cadre,
  règlement, CCAP, autres pièces ; jamais les bordereaux de prix ni l'acte d'engagement), 60 000 caractères au plus
  partagés équitablement. Aucun fait de l'entreprise, aucun nom, aucun CV. `tenant_scope` (espace facturé du chef
  de file) et `pii_scope` posés sur l'appel. Tâche du routage : `exigences` (lecture du dossier de l'acheteur,
  Mistral puis Claude en secours — aucune ligne du routage ni des pages juridiques ne change).
- **Contrôle sans IA de chaque question proposée** : sa phrase retrouvée MOT POUR MOT dans le dossier
  (`citation_guard`, 20 caractères au moins) ; aucun nombre de la question absent de la phrase ; son thème
  contrôlé de même (aucun nombre absent de la phrase, ni crochet ni lien ; sinon les mots de la question, sans sa
  tournure interrogative) ; une vraie question
  (12 à 300 caractères, sans renvoi, lien ni adresse) ; ni la même question ni la même phrase qu'une question déjà
  posée. Au plus **4 questions de l'IA** par dossier (`MAX_IA`), ajoutées après celles de la banque, avec
  « Proposée par Adjugo avec l'IA, d'après une phrase du dossier ».

### D.6 Le modèle et la migration

Table **`entretien_questions`** (`EntretienQuestion`) : une ligne par question d'un dossier de présentation.

| colonne | sens |
|---|---|
| `dossier_id` (clé étrangère), `project_id`, `owner_id` | le dossier, le marché, le tenant du chef de file |
| `numero` (unique dans le dossier) | renvoi `R<numero>`, stable, jamais réutilisé |
| `code` (unique dans le dossier), `origine` | code de la banque ou `ia-<empreinte>` ; `banque` ou `ia` |
| `theme`, `question`, `type_reponse` | ce qui manque si on passe ; le texte posé ; `texte` ou `equipe` |
| `motif`, `motif_piece` | la phrase du dossier, telle qu'écrite ; le libellé de sa pièce |
| `ordre`, `retiree_le` | ordre d'affichage ; question plus proposée (gardée) |
| `adresse_kind`, `adresse_invite_id`, `adresse_choix` | `organisation` ou `invitation` ; le partenaire ; `propose` ou `manuel` |
| `statut` | `a_repondre`, `repondue`, `sautee`, `sans_objet` |
| `reponse`, `reponse_preuve_id` | le texte ; la fiche « Équipe » choisie |
| `reponse_kind`, `reponse_invite_id`, `reponse_user_id`, `repondu_le` | qui a répondu (organisation ou invitation), le compte, quand |
| `lock_version` | verrou optimiste (409 `question_modifiee`) |

Migration `z1entretienchantier` (après `y9z0depotlien`, une seule tête Alembic) : idempotente (table créée si elle
manque, colonnes et index ajoutés s'ils manquent), SQLite et Postgres, valeurs par défaut côté base identiques au
modèle ; downgrade réel (table supprimée, rien d'autre). Déploiement sans casse : le code de production précédent
ne lit ni n'écrit la table. (Écrite d'abord après `x8y9redactionv4` ; chaînée après le dépôt par le lien quand la
production l'a reçu, à la fusion de la production dans cette branche.)

### D.7 Routes

Chef de file (portée organisation ; un marché d'une autre organisation → 404 `marche_introuvable`, aucun dossier →
404 `dossier_introuvable`). Erreurs métier : `detail = {code, message}`.

| méthode | route | corps | réponse et erreurs |
|---|---|---|---|
| GET | `/api/atelier/{pid}/entretien` | — | `Entretien` (ci-dessous) ; pas encore préparé : la proposition (`prepare: false`, questions sans `id`) |
| POST | `/api/atelier/{pid}/entretien` | — | `Entretien` + `preparation: {creees, retirees, reproposees}` ; 409 `reessayer` |
| PUT | `/api/atelier/{pid}/entretien/{qid}` | `{statut: repondue\|sautee\|sans_objet\|a_repondre, reponse?, preuve_id?, lock_version?}` | `Entretien` + `question_id` ; 404 `question_introuvable`, 403 `question_d_un_partenaire`, 409 `question_modifiee`, 422 `statut_invalide`, `reponse_vide`, `reponse_trop_longue`, `personne_introuvable`, `personne_inattendue` |
| PUT | `/api/atelier/{pid}/entretien/{qid}/adresse` | `{invite_id: int\|null, confirmer?}` | `Entretien` + `question_id` ; 409 `groupement_non_prepare`, `partenaire_indisponible`, `reponse_a_confirmer` (message à afficher, puis renvoyer avec `confirmer: true`). Aucun email. |
| POST | `/api/atelier/{pid}/entretien/ia` | `{accepte_debit?}` | 202 `{tache, quota}` ; suivre `/api/atelier/{pid}/taches/{job_id}` : `result = {ajoutees, refusees, message}`, `error` si l'IA tombe ; 409 `entretien_ia_en_cours`, `plafond_questions_ia`, `debit_a_confirmer`, `premiere_redaction_en_cours` ; 422 `dossier_absent`, `aucune_partie` ; 402 essai ; 403 démo, `email_non_confirme` |

Partenaire : `PUT /api/invite/{token}/redaction/entretien/{qid}` (lien + `X-Adjugo-Espace`) et
`PUT /api/shared/{pid}/redaction/entretien/{qid}` (compte) ; corps `{statut, reponse?, avertissement_lu, lock_version?}`
→ `entretien` du partenaire. 404 `question_introuvable` (une question qui ne lui est pas posée n'existe pas pour
lui), 403 `cle_espace_requise`, `identity_unverified`, `co_construction_fermee`, `demo` ; 422
`avertissement_requis`, `reponse_vide`, `reponse_trop_longue` ; 409 `question_modifiee`.

`Entretien` (chef de file) : `{prepare, message: "8 questions sur ce chantier", bulle, max: 8, questions:
[Question], compteurs: {prepare, total, repondues, a_repondre, passees, sans_objet, chez_partenaires}, fiche: [{ref,
theme, texte, libelle}], equipe: [{preuve_id, ref, nom, fonction}], dossier_present, groupement: {actif, membres:
[{invite_id, nom, lot}]}, ia: {en_cours: {job_id, statut}|null, proposees, restantes, plafond, bulle, quota},
statuts}`.

`Question` : `{id, numero, ref: "R3", code, origine, origine_libelle, theme, question, type_reponse, aide, motif:
{phrase, piece}|null, motif_message, critere: {critere, poids, poids_source}|null, partie: {section_id, titre,
redacteur}|null, adresse: {type, invite_id, nom, choix}, statut, statut_libelle, reponse: {texte, preuve_id,
personne: {nom, fonction, ref}|null, personne_retiree, par, le, libelle}|null, par, a_completer, peut_repondre,
lock_version}`.

Vue du partenaire (`GET …/redaction` → `entretien`) : `{questions: [{id, numero, theme, question, type_reponse:
"texte", motif, motif_message, partie, statut, statut_libelle, reponse: {texte, le}|null, a_completer,
lock_version}], total, a_repondre, message, avertissement, statuts}`. « Partagé avec moi » : `redaction.questions`
(ses questions sans réponse).

État de l'atelier (`GET /api/atelier/{pid}`) : `entretien` = les compteurs (deux requêtes, sans IA) ; pour un
dossier d'avant la vague 5, `prepare: false` et `proposees` (combien l'entretien poserait, lecture en cache).

### D.8 Démo (vitrine, sans IA ni réseau)

- `demo_entretien.seed_entretien` remplit l'entretien du marché « toiture » avec le VRAI moteur (questions de la
  banque sur le dossier fictif, phrases retrouvées, classement par les poids du règlement fictif) et des réponses
  FICTIVES : « cohabitation avec les occupants » et « tri et filières des déchets » répondues, « chef de chantier »
  = la fiche « Équipe » fictive d'Erwan Le Bris, « planning calé sur les périodes imposées » passée ; les autres à
  répondre. Dans la transaction du seed (aucun commit), effacé à la remise à neuf (`demo_seed`).
- Toutes les routes d'écriture sont classées dans `tests/test_demo_sans_cout.py` (`COUTS` : la recherche avec l'IA ;
  `SANS_COUT` : préparer, répondre, adresser, la réponse du partenaire) et refusées à la démo par le garde central
  ET dans la route (`refuser_demo`) ; le lien partenaire de la démo est refusé avant tout autre contrôle. L'écran
  de la démo lit l'entretien (`POST` refusé → `GET`).

### D.9 RGPD et cycle de vie

| événement | effet |
|---|---|
| Effacement du compte du chef de file, corbeille purgée | l'entretien part avec le dossier (`ag.effacer_dossiers` → `ec.effacer_dossiers`) |
| Effacement d'un compte (partenaire ou membre) | ses réponses restent à l'organisation ou à l'invitation qui les a données, sans le compte (`reponse_user_id` vidé) |
| Retrait ou déclin d'une invitation | ses réponses effacées et oubliées des faits qui les citaient (« à relire »), ses questions rendues au chef de file, à répondre |
| Invitation coupée sans retrait (corbeille, lien expiré depuis plus de 30 jours) | réponses cachées tout de suite ; la purge quotidienne les efface comme un retrait |
| Transfert de propriété, membre effacé, dossier réaffecté | les lignes suivent `owner_id` comme l'atelier |
| Export RGPD du chef de file | `entretiens_chantier` (questions, phrases, réponses — celles de ses partenaires comprises) |
| Export RGPD et portabilité du partenaire | `reponses_entretien_chantier` dans sa part : les questions qui lui sont posées et SES réponses |

### D.10 Choix faits par défaut (à valider par Eliot)

1. **L'entretien est préparé avec le dossier de présentation** (sans IA, sans débit), et de nouveau quand le plan
   est reconstruit ou « Qui écrit quoi » préparé : la carte dit tout de suite « 8 questions sur ce chantier », et elle
   se déplie d'elle-même tant qu'aucune partie n'a de texte.
2. **Une question passée laisse un « [À compléter] » garanti** dans sa partie (ajouté sans IA) ; une question
   encore sans réponse ne force rien : l'IA est prévenue (aucun fait, passage si la partie en a besoin) et l'écran
   prévient avant de rédiger. Raison : ne pas couvrir d'« [À compléter] » les parties de ceux qui rédigent avant
   d'avoir ouvert les questions, sans jamais laisser l'IA remplir le vide.
3. **« Sans objet sur ce chantier »** existe en plus de « Passer » : un mot du dossier peut déclencher une question
   qui ne concerne pas ce chantier ; elle ne laisse alors rien.
4. **Poser une question à un partenaire exige « Qui écrit quoi » préparé** (c'est là qu'il a son espace) ; aucun
   email n'est envoyé (« Demander les parts » reste le seul envoi ; à étendre aux questions si le terrain le
   demande).
5. **Le chef de chantier d'un partenaire s'écrit** (sa liste « Équipe » reste chez lui) ; la liste « Équipe » est
   proposée au chef de file seul.
6. **Option IA : 4 questions de plus au plus par dossier**, tâche du routage `exigences` (lecture du dossier).

### D.11 Limites connues

- Tout repose sur la qualité de la banque (risque de l'étude) : Mathys la valide avec les 7 PME ; elle se modifie
  sans migration. Un déclencheur peut se tromper de sens (« les travaux de nuit sont interdits » déclenche la
  question des travaux de nuit) : la phrase est montrée, « Sans objet » la referme.
- La négation n'est repérée que dans une fenêtre courte autour du mot (« aucune », « sans », « ne … pas ») ; une
  négation lointaine passe.
- Le classement suit le poids du critère (ou, depuis la réunion avec C2, du sous-critère : section I.1, point 3)
  dont le nom contient un début de mot de la question ; une grille aux intitulés inhabituels rattache tout au
  seul critère « technique », ou à aucun.
- Une réponse modifiée après la rédaction n'est relue qu'au prochain « Recontrôler » de la partie (comme le
  profil) ; le texte déjà rédigé n'est jamais réécrit sans geste de l'utilisateur.
- Un nom de personne écrit dans une réponse n'est masqué avant l'IA que s'il est repéré (équipe connue ou forme
  de nom) ; la bulle de « Qui sera le chef de chantier ? » recommande la liste « Équipe ».

### D.12 Vérifications

- Fusion de la production (dépôt de documents par le lien, b010c59) dans cette branche : conflits résolus à la main
  (listes du transfert, de l'effacement et du journal : les deux ajouts gardés ; espace du partenaire : ses
  questions puis ses documents ; export de sa part : ses documents ET ses réponses ; empreintes SRI recalculées) ;
  migration chaînée après `y9z0depotlien` (une seule tête) ; la réponse du partenaire suit la règle du verrou de
  l'invitation d'abord (test `test_reponse_du_partenaire_espace_reinitialise_ou_lien_retire_entre_temps`).
- Suite complète SQLite (`TZ=UTC`, IA et emails simulés, aucun réseau) : 1 711 tests, tous verts, dont les 17 de
  `tests/test_redaction_v5_entretien.py` (déclenchement sans IA, ordre, phrase du dossier, question passée →
  « [À compléter] », réponses → faits « déclaré par vous » [R#], choix dans « Équipe » sans nom ni CV à l'IA, question
  posée dans l'espace du partenaire, espace réinitialisé ou lien retiré pendant sa réponse, option IA (phrase
  retrouvée mot pour mot, débit, remboursement), isolation, RGPD, démo, migration, écrans compilés sous Node).
- Empreintes SRI à jour (`scripts/sri_update.py --check`), `node --check` de `app.js` et `redaction-partenaire.js`,
  gabarit de l'application compilé par Vue sous Node (aucune erreur).
- Navigateur réel (serveur local, IA coupée) : chef de file à 1 280 px et 375 px (aucun défilement horizontal),
  lien du partenaire (espace ouvert, réponse avec l'avertissement ; après la fusion, ses questions et « Vos
  documents pour Adjugo » l'un sous l'autre à 375 px, sans défilement horizontal), vitrine de la démo
  (8 questions, 3 réponses, 1 passée, chef de chantier choisi dans « Équipe »).
- Postgres 16 depuis l'état exact de la production, deux fois : da9ef0f (tête `x8y9redactionv4`, avant la fusion)
  puis b010c59 (tête `y9z0depotlien`, après) ; données créées par le code de production ; une seule révision
  appliquée, aucune donnée perdue, seconde montée et rejeu forcé sans effet, entretien préparé et répondu sur la
  base montée (chef de file et partenaire), code de production redémarré sur la base montée (lectures et
  écritures 200), schéma identique à une base neuve, retour arrière (table retirée, rien d'autre ne bouge) puis
  remontée : 19 contrôles sur 19 ; vrais tests rejoués sur la base montée : 1 027 verts, et exactement les 37
  échecs de la vérification de la production elle-même (b010c59 : tests propres à SQLite, PRAGMA, `sqlite3`, base
  partagée), aucun dans la rédaction.

---

## E2 — « Mes preuves » depuis les sources publiques (DECP, liste RGE de l'ADEME)

Décisions appliquées : **D7 (b)** l'import DECP est PROPOSÉ, l'utilisateur coche ; **D8 (a)** CV et noms
jamais à l'IA (E2 n'appelle aucune IA) ; **D10 (c)** pas de contrôle de ressemblance entre clients.

Code : `app/services/sources_publiques.py` (lectures publiques, cache, normalisation, exemple fictif de la
démo), `app/services/preuves_publiques.py` (« Mes preuves » et part du partenaire), routes
`app/routers/preuves_publiques.py`, écran `app/static/sources-publiques.js` (un seul écran pour les trois
accès), réseau `app/services/partner_network.py` (`fetch_decp`), `app/services/partner_matching.py`
(libellé, capacités, classement), `app/services/decp.py` (`where_titulaire`, `wins_by_siren`).
Tests : `tests/test_redaction_v5_e2.py`. **Aucune migration** : les preuves gardent leur table (origine
`import_public`, type de source `public`), la part du partenaire ses colonnes JSON.

### E2.1 Les sources lues (GET de lecture seulement, sans clé, Licence Ouverte)

| source | requête | ce qui est lu |
|---|---|---|
| DECP (`data.economie.gouv.fr`, jeu `decp-2022-marches-valides`) | `startswith(titulaire_id_1, "<SIREN>") or …_2 or …_3`, du plus récent au plus ancien, 100 lignes par page, 3 pages au plus | `id`, `objet`, `montant` (attribution, HT), `datenotification`, `acheteur_id`, `nature`, `techniques`, `titulaire_id_1..3`, `typegroupementoperateurs`, `idaccordcadre`, `lieuexecution_code` |
| Liste RGE de l'ADEME (`data.ademe.fr`, jeu `liste-des-entreprises-rge-2`) | `qs=siret:<SIREN>*` (tous les établissements), 300 lignes | `siret`, `code_qualification`, `nom_qualification`, `nom_certificat`, `organisme`, `domaine`, `lien_date_debut`, `lien_date_fin` |
| Annuaire des entreprises (`recherche-entreprises.api.gouv.fr`) | le SIREN de l'acheteur donné par DECP | `nom_complet` de l'acheteur (40 noms au plus par lecture, 4 en parallèle, 6 s au total) |

Le SIRET est celui du **profil de l'entreprise** (« Mes preuves ») ou celui de la **part** du partenaire
(jamais un SIRET saisi dans l'adresse). Sans SIRET : `statut: "siret_manquant"` et un message, aucune
lecture.

Robustesse (un seul process, sans Redis) :

- un seul point d'entrée HTTP (`sources_publiques._http_get`), délai 8 s, deux essais (une erreur 4xx n'est
  pas rejouée) ;
- cache en mémoire : une lecture réussie sert **6 heures** ; une panne n'est pas relue avant 60 s ; si la
  source tombe, la dernière lecture de **moins de 7 jours** est rendue avec `ancien: true` et le message
  « … ne répondent pas pour le moment : voici la lecture du JJ/MM/AAAA. » ; 150 entreprises gardées au plus ;
- panne sans lecture précédente : `statut: "panne"` et « Les données des marchés publics (DECP) ne répondent
  pas pour le moment : rien n'a été lu, réessayez plus tard. » — jamais « aucun marché » ;
- noms d'acheteurs : un nom non retrouvé n'est jamais deviné (le SIRET reste affiché) ; annuaire en panne :
  relu au plus tôt 10 minutes après ; un seul exécuteur pour le process (4 lectures en même temps) : une lecture
  finie après le budget de 6 s range quand même son nom, une lecture pas commencée est annulée, une lecture en
  cours n'est jamais relancée ; la relecture faite pendant qu'une part est verrouillée ne lit que les noms déjà en
  cache (`noms_en_cache`, aucun appel réseau) ;
- couverture : le jeu lu contient surtout des marchés notifiés depuis 2024 (environ 86 % des lignes au 19/10/2026) ;
  l'écran le dit dans la bulle (i) et sous « Aucun marché trouvé » : « Les données publiques lues couvrent surtout
  les marchés notifiés depuis 2024 : un marché plus ancien peut manquer, ajoutez-le vous-même. » ;
- la date de lecture (`consulte_le`) est le jour de Paris ; elle est enregistrée avec chaque fiche.

### E2.2 Une ligne DECP → une référence PROPOSÉE (rien d'inventé)

Une ligne par marché (même `id` et même acheteur lus deux fois : une seule ligne). Pour chacune :
`{cle, nature: "reference", decp_id, affiche, valeur, alertes, manque, deja, deja_message, texte,
source_libelle: "marché attribué, source publique DECP", source}`.

- `affiche` : ce que dit la source, tel quel (objet en majuscules compris, « CDL », 1 €…), avec la
  **position** du titulaire (1, 2 ou 3), le nombre de co-titulaires, le rôle et son libellé : « Seule »,
  « En groupement conjoint / solidaire, avec N autre(s) entreprise(s) », « Rôle non précisé dans DECP » ;
- `valeur` : les champs de la fiche « Référence » qui seront enregistrés, seulement s'ils sont possibles :

| champ | règle |
|---|---|
| `objet` | tel qu'écrit ; vide ou valeur de remplissage (« CDL », « MQ NC », « NC »…) → `manque` (la ligne ne peut pas devenir une référence) ; plus de 300 caractères → coupé à un espace avec « … », le texte complet en `description` (alerte) |
| `acheteur` | nom retrouvé dans l'annuaire par le SIRET de DECP ; sinon absent (le SIRET est montré) ; « MQ NC » → alerte « Acheteur non renseigné dans DECP. » |
| `montant_ht` | gardé tel quel ; < 1 000 € ou > 50 M€ → alerte « Montant inhabituel… Cochez seulement s'il est juste. » ; 0, négatif ou illisible → non repris (alerte) ; **accord-cadre** — dans le format réel de DECP, `nature` vaut « Marché » et c'est `techniques` qui dit « Accord-cadre » (environ 37 % des lignes) : la ligne est l'accord-cadre lui-même quand `idaccordcadre` est vide (« CDL ») ou son propre identifiant (ou, ancien format, quand `nature` le dit) → montant **non repris** (ni dans la fiche ni dans le relevé), alerte « Accord-cadre : le montant de DECP (… € HT) est un maximum ou une estimation, pas ce qui a été commandé : il n'est pas repris dans la fiche. » ; un marché subséquent (`idaccordcadre` désigne une autre ligne) garde son montant, sans alerte |
| `annee` | année de notification ; date absente, illisible, future ou avant 1990 → non reprise (alerte) |
| `role` | « Solidaire » → `groupement_solidaire` ; « Conjoint » → `groupement_conjoint` ; « Pas de groupement » sans autre titulaire → `seul` ; « Pas de groupement » avec d'autres titulaires → aucun rôle, alerte « précisez votre rôle après l'ajout » |

Le texte d'une référence DECP dit **« attribué »**, jamais « réalisé » : `texte_de(…, attribue=True)` →
« …; montant d'attribution 85 000 € HT ; attribué seul » ; dans l'atelier, la fiche insérée porte « Marché
attribué à l'entreprise seule » et « Montant d'attribution » (`preuves_atelier.bloc(…, attribue=True)`) ;
`texte_ia` aussi ; dans « Mes preuves » (`pvDetail`, liste et « Insérer une fiche » de l'atelier) : « attribué
seul », « attribué en groupement conjoint / solidaire » ; le champ du formulaire s'appelle « Rôle » et la bulle
des Références dit « Vos marchés réalisés ou attribués ». Le lieu d'exécution (un code) est montré, pas enregistré.

### E2.3 Liste RGE → une qualification PROPOSÉE ; une expirée exclue et signalée

Les lignes de la liste (une par domaine et par établissement) sont regroupées par qualification, organisme,
certificat et fin de validité. La liste met le domaine dans le code et dans le nom (« 2111D111 », « Maçonnerie et
ouvrage en béton armé (2111D111) ») : la qualification est le code sans son suffixe de domaine (« 2111 », motif
`NNNNDnnn`), son nom sans « (code) ». Une qualification proposée :
`valeur = {nom: "<certificat> : <qualification>" (200 car.), organisme (Qualibat, Qualit'EnR…), numero
(code), detail: "RGE depuis le JJ/MM/AAAA, domaines : …"}`, `date_fin_validite` = fin de la liste
(« 2099-01-01 » = sans date de fin : aucune date, alerte « Inscrite sans date de fin dans la liste RGE. ») ;
`source_libelle: "source publique : liste RGE de l'ADEME"`.

Fin dépassée (jour de Paris) : la qualification n'est **pas proposée** (aucune clé) ; elle est rendue dans
`expirees: [{nom, organisme, date_fin, message}]` : « Expirée le JJ/MM/AAAA selon la liste RGE : Adjugo ne la
propose pas. Si elle a été renouvelée, ajoutez-la avec son nouveau certificat. » **Qualibat hors RGE** n'a
pas de liste ouverte : l'écran le dit, la saisie reste manuelle avec le certificat (justificatif).

### E2.4 « Mes preuves » : routes

Authentification `Bearer`. Portée : l'organisation (`data_owner_id`).

| méthode | route | réponse |
|---|---|---|
| GET | `/api/preuves/publiques/marches` | `{statut: ok\|panne\|siret_manquant\|exemple, message?, siren, consulte_le, ancien, total, lus, tronque, a_cocher, marches: [proposition]}` |
| GET | `/api/preuves/publiques/rge` | `{statut, message?, siren, consulte_le, ancien, total, tronque, a_cocher, qualifications: [proposition], expirees: [...]}` |
| POST | `/api/preuves/publiques` `{cles: [...]}` (300 au plus) | `{creees: [preuve], deja, ignorees: [{cle, texte, message}], pannes: [...]}` ; 503 `source_indisponible` si rien n'a pu être relu |

- **Le client n'envoie que des clés** : le contenu est relu côté serveur dans la lecture en cache (ou relu à
  la source). Une clé inconnue → `ignorees` « Cette ligne n'est plus dans la dernière lecture : rechargez
  la liste, puis cochez de nouveau. » ; une clé d'une source en panne → `ignorees` avec le message de la panne
  (jamais en silence ; l'écran le dit en alerte, une fois) ; une ligne `manque` → `ignorees` avec sa raison ; une
  ligne déjà dans « Mes preuves » (même identifiant public — marché et acheteur —, même fiche, ou même intitulé
  qu'une fiche qui N'EST PAS tirée d'une source publique) → `deja`. Deux marchés DECP distincts au même objet
  (« Rénovation du terrain de football ») sont deux références.
- Cocher, c'est accepter : la fiche est créée **acceptée**, `origine: "import_public"`, `type_source:
  "public"`, `source = {nom: "DECP" | "liste RGE de l'ADEME", url (page publique), consulte_le, identifiant
  ("marché <id>, acheteur <SIRET>" ou "SIRET <siret>, qualification <code>"), releve}`, `date_source =
  consulte_le`. Rien n'est créé sans case cochée (D7 b) ; la vérification des valeurs est celle du socle
  (`pv.creer`).
- Lignes de l'écran : les cases ne sont **jamais cochées d'office** ; « Cocher les lignes sans alerte » ne
  coche jamais une ligne qui porte une alerte.

### E2.5 Le relevé : les champs de la source ne changent pas tant que la fiche la garde

`source.releve` = les champs de la fiche tels que la source les donne (et la fin de validité quand la liste
RGE la donne). Le socle (`preuves._controler_releve`) refuse, à la création comme à la modification, une
fiche « source publique » dont un champ relevé diffère : 422 `valeur_source_publique` + `champs`, message
« Ces champs viennent de la source publique (DECP) : ils ne changent pas tant que la fiche garde cette
source. Pour les corriger, choisissez « Déclaré par vous ». » Une fiche qui garde sa source garde aussi sa
source (nom, adresse, date : ce que l'écran renvoie est ignoré). Un champ non relevé (une description, un
lieu) se complète librement. Passée en « déclaré par vous », la fiche se corrige et le libellé le dit.
`preuve_out` expose `champs_source_publique` (l'écran grise ces champs et le dit).

### E2.6 Le partenaire d'un groupement : SES preuves et SES sources, dans SA part

La part (`ProjectContribution.references` / `qualifications`) est la donnée du partenaire : il la remplit
lui-même ; rien n'est lu ni écrit chez le chef de file.

| méthode | route | qui |
|---|---|---|
| GET | `/api/invite/{token}/contribution/publiques/marches` · `…/rge` | le lien (ou le compte) : lus avec le SIRET de **sa part** |
| POST | `/api/invite/{token}/contribution/reprendre` `{publiques: [...], version}` | le lien : marchés publics et qualifications RGE cochés |
| GET | `/api/invite/{token}/contribution/preuves` | le **compte** qui a rattaché le lien (`Bearer`) : ses références et qualifications **utilisables** de « Mes preuves » (403 sinon ; 403 si le compte appartient à l'organisation du chef de file) |
| POST | `/api/invite/{token}/contribution/reprendre-preuves` `{preuves: [ids], publiques: [...], version}` | le compte : ses preuves cochées (relues dans SON organisation ; un identifiant d'ailleurs → `ignorees`) |

Réponse : `{contribution, ajoutees: {references, qualifications}, deja, ignorees, pannes}`.

- Même verrou que l'enregistrement de la part : `version` exigée (428), version périmée → 409. Les
  sources publiques sont lues **avant** de réserver la version (aucun appel réseau pendant que la ligne est
  verrouillée). Rien à ajouter → rien n'est écrit, la version ne bouge pas.
- Rien n'est retiré ni réécrit ; un élément déjà dans la part n'est pas doublé (une qualification : même nom ;
  une référence de DECP : même identifiant public, ou même intitulé qu'une référence saisie ; une référence saisie
  ou de « Mes preuves » : même intitulé) ; 50 références et 50 qualifications au plus. Une clé d'une source en
  panne est dans `ignorees` avec le message de la panne.
- **La provenance n'est jamais prise du navigateur** : à l'enregistrement de la part (PUT), `provenance`,
  `consulte_le` et `identifiant` ne restent que sur une référence identique (intitulé, acheteur, montant, année,
  rôle, provenance) à une référence déjà enregistrée par « Reprendre » (`references_relues`) ; une référence
  modifiée ou nouvelle devient une simple saisie (jamais « marché attribué »).
- Référence ajoutée : `{intitule, client?, montant?, annee?, role?, provenance: "decp" | "mes_preuves",
  consulte_le?, identifiant?}` (les lecteurs existants lisent `intitule`, `client`, `montant`, `annee`) ;
  qualification ajoutée : son **nom**, comme une saisie (la liste reste une liste de textes, lue telle
  quelle par la convention, les formulaires et « Qui fait quoi »). Une référence `provenance: "decp"` est
  dite « marché attribué » dans ce que l'IA reçoit (aide du partenaire, apports au chef de file).
- Une part soumise repasse en brouillon (comme toute modification) : offre figée et convention suivent la
  règle existante ; journal : `guest.contribution_reprise` (« Vous avez ajouté des références ou des
  qualifications à votre part »).
- Écran : par le lien (`invite.html`) et par le compte (« Partagé avec moi »), la saisie en cours est
  d'abord enregistrée, puis le serveur ajoute ce qui est coché. La zone « Références (une par ligne) »
  garde la version complète d'une ligne dont l'intitulé n'a pas changé (`spFusionRefs`) : enregistrer la
  part ne perd ni l'acheteur, ni le montant, ni la provenance ; sous la zone : « Dont N marchés attribués,
  source publique DECP (lus le JJ/MM/AAAA). »
- Démo : le lien partenaire de la vitrine lit l'exemple fictif ; toute écriture est refusée dans la route.

### E2.7 Réseau : l'historique réel de co-traitance (titulaires 2 et 3)

- `partner_network.fetch_decp` et `decp.wins_by_siren` lisent les titulaires 1, 2 **et** 3
  (`decp.where_titulaire`).
- `verified_decp.groupements` = marchés distincts attribués **en groupement selon DECP** (type déclaré
  conjoint ou solidaire ; plusieurs titulaires sur une ligne « pas de groupement » — accord-cadre à
  plusieurs attributaires, saisie contradictoire — ne comptent pas).
- Libellé (badge et critère « Expérience ») : « Au moins 3 marchés publics publiés dans DECP (au 05/10),
  dont 2 en groupement » ; une lecture d'avant la vague 5 (sans `groupements`) garde son libellé. Capacité :
  « Marchés publics attribués en groupement (DECP) : au moins N ». Classement : l'historique DECP en
  groupement compte comme les groupements déposés sur Adjugo (3 points au plus, plafond inchangé).
  Jamais le mot interdit : on dit où on l'a trouvé (DECP) et à quelle date.

### E2.8 Démo (vitrine)

`sources_publiques.exemple_fictif_marches()` / `exemple_fictif_rge()` : trois marchés **clairement
fictifs** (objets « Exemple fictif - … », acheteurs « Commune fictive de Marvejac », « Communauté fictive
de Kerhel ») dont un en groupement solidaire et un accord-cadre au format réel de DECP (`nature` « Marché »,
`techniques` « Accord-cadre », montant de 1 € montré et non repris, avec son alerte) ; une qualification RGE valable et une expirée signalée. Bandeau : « Exemple fictif de la
démonstration : ces marchés et ces qualifications n'existent pas. Avec votre compte, Adjugo les lit dans les
données publiques à partir de votre SIRET. » Servi au compte démo et au lien partenaire de la vitrine,
**sans aucun appel réseau** ; la vitrine ne change pas (aucune ligne écrite, seed inchangé). Écritures :
`POST /api/preuves/publiques` bloquée par le garde central (`demo_guard`) et dans la route
(`refuser_demo`) ; `POST …/contribution/reprendre` et `…/reprendre-preuves` refusées dans la route
(`_refuse_if_demo_invite`). Classement des routes : `tests/test_demo_sans_cout.py` (`SANS_COUT`).

### E2.9 Limites assumées

- DECP ne donne ni notes, ni critères, ni preuve d'exécution : la fiche le dit (« marché attribué »).
- Le SIRET du profil est déclaré par l'utilisateur : Adjugo lit ce que la source publique dit **de ce
  SIRET** ; le candidat reste responsable de son offre.
- Les 300 lignes DECP les plus récentes seulement (`tronque` le dit) ; la liste RGE est lue jusqu'à 300
  lignes.
- Le nom de l'acheteur vient de l'annuaire des entreprises (par le SIRET de DECP) ; non retrouvé, il reste à
  compléter.
- Le cache est en mémoire : un redémarrage relit les sources (c'est voulu : un seul process).

---

## I — Réunion des trois chantiers et parcours complet

Branche d'intégration au-dessus de la production `b010c59` (`feat/produit-acheteur-collectivites` n'a pas
bougé depuis : aucune autre fusion de la production n'a été nécessaire). Ordre des fusions : D (`d158262`, qui
contient déjà `b010c59`) comme base, puis C2 complet (`8146889`), puis E2 (`5bf6ae8`). Chaque conflit a été résolu
bloc par bloc, en gardant les deux intentions ; un contrôle ligne à ligne (toute ligne ajoutée par un côté
présente dans la fusion) ne laisse de côté que des lignes remplacées à dessein : empreintes SRI recalculées,
appel de la partie à l'IA qui reçoit à la fois l'entretien (`fiches=…`) et les sous-critères (`analysis=…`), état
de l'atelier initialisé avec l'entretien ET le mode « sans IA » (`ent`, `sansIaPropose`, `exOpen`), en-têtes de
ce contrat réunis en un seul. Une seule tête Alembic : `z1entretienchantier` (D), après `y9z0depotlien`.

### I.1 Les jointures ajoutées par la réunion

1. **Mode « sans IA » (C2) × entretien chantier (D).** Un dossier « sans IA » ne demande aucune question à l'IA :
   `POST /api/atelier/{pid}/entretien/ia` répond 409 `mode_sans_ia` (contrôle `atelier.exiger_ia_permise` en tête de
   `entretien_chantier.lancer_ia`, avant toute préparation et tout débit). L'état de l'entretien porte
   `ia.permise` (faux en mode « sans IA ») et l'écran ne montre plus « Chercher d'autres questions avec
   Adjugo ». Les questions de la banque, elles, continuent (elles sont sans IA) : on peut encore répondre,
   passer, dire « sans objet » et poser une question à un partenaire. Le message du mode et sa bulle le disent
   (« ni question proposée par l'IA » ; « les questions sur ce chantier continuent, sans IA »).
2. **Source publique datée (E2) × contrôle des faits de l'atelier.** Une fiche de « Mes preuves » de type
   `public` (marché DECP, qualification RGE) garde sa date de lecture (`source.consulte_le`, sinon
   `date_source`) ; la source d'un fait relié la porte (`source.date`). La liste « Faits avec une source » de
   l'atelier et celle de l'espace du partenaire disent « marché attribué, source publique DECP, consultée le
   JJ/MM/AAAA » (`atlSrcLib`, `rpSrcLib`) ; le nom de document n'y est pas répété. Rien de cela ne part dans le
   Word (doctrine § 7.7).
3. **Sous-critères (C2) × entretien (D).** Un critère découpé en sous-critères dans le plan (deux au moins, une
   partie chacun, comme `atelier_plan.parties_du_critere`) donne à l'entretien une ligne par sous-critère, avec
   SON poids tel qu'écrit (`entretien_chantier.lignes_grille`) : un sous-critère sans poids écrit pèse 0, rien
   n'est déduit. Une question dont un début de mot se retrouve dans un sous-critère s'y rattache (il l'emporte sur
   son propre critère, plus général) ; sinon elle reste au critère, ou au seul critère « technique » (repli
   inchangé, qui ne regarde que les critères). Les questions se classent par ce poids : « Méthodologie d'exécution
   en site occupé (40 %) » avant « Moyens humains et encadrement (20 %) » avant « Démarche environnementale
   (10 %) », au lieu des 70 % de « Valeur technique » pour toutes. La partie concernée est celle du sous-critère
   (même critère, même intitulé) quand aucun début de mot ne désigne mieux une partie. L'écran dit « Partie
   concernée : Démarche environnementale (10 %) », ou « · sous-critère : … » quand la partie est une autre
   (champ `critere.sous`). La consigne de rédaction d'une partie reçoit à la fois son sous-critère et les réponses
   de l'entretien qui la concernent. Une question qui ne concerne que le critère (« Valeur technique ») garde son
   poids (70 %) et passe donc avant celles de ses sous-critères : c'est le poids tel qu'écrit, aucun n'est déduit.
   Un entretien déjà préparé garde son ordre (enregistré) ; seul l'affichage du critère suit la grille.
4. **Espace du partenaire (V4) × C2 × D × E2.** Il montre, chez lui : ses questions sur le chantier, le mode
   « sans IA » choisi par le chef de file (son aide de l'IA est alors refusée), les exigences de ses parties, et
   « Retrouver mes marchés publics » pour SA part (SIRET de sa part). Les questions à poser à l'acheteur restent
   au chef de file seul.

### I.2 Le parcours complet, vérifié par un test

`tests/test_redaction_v5_parcours.py::test_parcours_complet_vague_5`, un seul dossier, IA et sources publiques
simulées, **aucun appel réseau** (le transport HTTP réel est coupé ; un appel ferait échouer le test) :

1. dossier de l'acheteur **importé** par la route réelle (`/api/sourcing/analyze-upload`, règlement + CCTP) ; la
   mesure D11 compte l'import (agrégat, aucun contenu) ;
2. « Comment vous serez noté » : critères et **sous-critères** tels qu'écrits (40 %, 20 %, 10 % sous 70 %, total
   contrôlé), **liste des exigences** (4 repérées sans IA + 1 proposée par l'IA et retrouvée ; une exigence
   inventée par l'IA, « 95 % », écartée), environnement dans la note, R2142-21 (« seul et en groupement »),
   phrase du règlement qui interdit l'IA, **questions à l'acheteur** (deux limites de pages contradictoires ; la
   question de l'IA avec un nombre absent de la phrase, rejetée) et date limite écrite (05/12/2026) ; chaque
   phrase affichée passe `citation_guard` ;
3. atelier : une partie par sous-critère (1.1, 1.2, 1.3) sous le titre « 1 Valeur technique » ; « 0 exigence
   traitée sur 5 » ;
4. un partenaire (lien, sans compte), « Qui écrit quoi » préparé ;
5. « Mes preuves » : un marché DECP **proposé** (rien de coché d'office ; la ligne « CDL » montrée, non
   cochable), coché, enregistré « marché attribué, source publique DECP », daté du jour ; le partenaire reprend
   SES marchés publics (SIRET de sa part) dans SA part ;
6. **entretien chantier** : chaque question rattachée à son sous-critère (40 %, 20 %, 10 %) et à sa partie, et
   classée par ce poids ; une réponse « déclaré par vous », une question **passée** (chef de chantier), une
   question **adressée au partenaire** (accès à la toiture, proposée d'après son lot) : le chef de file ne peut pas
   y répondre (403), le partenaire ne voit que SA question et aucune réponse du chef de file, il répond **dans son
   espace** (lien + clé, avertissement lu) ; la fiche chantier dit « déclaré par vous » et « déclaré par Kerbrat
   Zinguerie » ;
7. **atelier (IA simulée)** : l'IA reçoit les faits [R#] « déclaré par vous », [R#] « déclaré par votre
   partenaire » et [F#] « marché attribué, source publique DECP », le sous-critère, aucun nom en clair ; le
   contrôle des faits relie « 11 h » à la réponse de l'entretien, « échafaudage » au partenaire, « 85 000 € » à la
   fiche DECP (datée) ; aucun fait sans source ; la question passée laisse **un** « [À compléter : chef de
   chantier] » dans « 1.2 » ; « **2 exigences traitées sur 5** » avec le nom des trois qui manquent ;
8. **mode « sans IA »**, que le règlement demande : rédaction d'une partie, de tout le dossier, recherche de
   questions par l'IA et raccourci refusés (409 `mode_sans_ia`), « deux parties à réécrire soi-même », le
   partenaire le lit chez lui ; le chef de chantier est donné, les parties réécrites à la main : « Les 5 exigences
   repérées sont traitées », le contrôle des faits continue, **aucun appel d'IA** ;
9. **questions à l'acheteur** : toujours lisibles avec leur phrase et leur date limite, retirées puis remises
   sans IA ; jamais dans la vue du partenaire ;
10. **export Word** : titres « 1. Valeur technique » / « 1.1 … », aucune mention IA (aucun texte de l'IA
    restant, D9), et aucune marque interne : ni renvoi [R#] / [F#], ni « [À compléter] », ni « déclaré par »,
    ni « source publique », ni « DECP », ni « Entretien chantier », ni « Adjugo », ni « python-docx ».

`test_vitrine_de_la_demo_montre_les_trois_nouveautes_sans_ia_ni_reseau` : la vitrine (marché toiture) montre
« 5 exigences traitées sur 7 », la phrase du règlement sur l'IA, l'entretien (3 réponses au moins, 1 passée,
fiche chantier), des marchés publics proposés à partir d'un exemple **clairement fictif** ; toute écriture et tout
appel d'IA sont refusés (« lecture guidée ») ; aucune ligne écrite, aucun appel d'IA, aucun appel réseau.

`test_ecrans_sans_ia_entretien_et_source_publique_datee` : les jointures côté écran (bouton de l'IA masqué en
mode « sans IA », « sous-critère : … » dans la question, source publique datée, `rpSrcLib` exécuté sous Node).

`test_entretien_rattache_une_question_a_son_sous_critere_sans_poids_deduit` : la règle de rattachement, sans IA ni
base (sous-critère sans poids écrit à 0, sous-critère plus précis que son critère, repli sur le critère
technique, partie du sous-critère, critère à un seul sous-critère gardé en une ligne).

### I.3 Choix faits par défaut à la réunion (à valider par Eliot)

1. En mode « sans IA », **les questions de l'entretien restent** (banque sans IA) ; seule la recherche de
   questions par l'IA est refusée. Raison : l'entretien est du « maximum sans IA ».
2. La date d'une source publique se lit **« consultée le JJ/MM/AAAA »** dans les listes de faits (atelier et
   espace du partenaire), jamais dans le fichier exporté.
3. L'entretien se classe par le poids du **sous-critère** quand la question en concerne un (I.1, point 3) ; une
   question qui ne concerne que le critère garde le poids du critère (il est écrit), même s'il dépasse celui de
   ses sous-critères. Contre-relecture : un sous-critère SANS poids écrit se classe sur le poids écrit de son
   critère (il passait à 0, après un critère de 10 %), et ses questions font un groupe avec celles du critère.

### I.4 Vérifications

- Suite complète SQLite (`TZ=UTC`, IA, emails et sources publiques simulés, aucun réseau) : **1 771 tests, tous
  verts**, dont `tests/test_demo_*.py` et les quatre tests de `tests/test_redaction_v5_parcours.py`.
- Contrôle des fusions ligne à ligne (`d158262`, `aaa6909`, `431ba32`) : aucune ligne d'un côté perdue en dehors
  des remplacements voulus listés en tête de cette section.
- Empreintes SRI à jour (`scripts/sri_update.py --check`) ; `node --check` de tous les scripts servis.
- Navigateur réel (serveur local, IA coupée, base neuve), vitrine de la démo à 375 px : carte « Comment vous serez
  noté » (« 6 critères · 7 exigences », questions à l'acheteur avec la date limite du 18/12/2026, phrase sur l'IA,
  R2142-21), atelier (« 5 exigences traitées sur 7 », « 8 questions sur ce chantier », 3 réponses et 1 passée,
  chaque question avec sa phrase du dossier et sa partie concernée) ; aucun défilement horizontal.
- Postgres 16 depuis l'état exact de la production (`b010c59`, tête `y9z0depotlien`, code extrait par
  `git archive`, données créées par le code de production : compte, marché analysé, atelier, partie écrite,
  invitation, part du partenaire, « Qui écrit quoi », espace du lien, brouillon privé, tâche) : 24 contrôles sur 24
  — une seule révision appliquée (`y9z0depotlien → z1entretienchantier`), aucune donnée perdue, seconde montée
  et rejeu forcé (stamp puis upgrade) sans effet ; sur la base montée, le code nouveau relit sans IA la grille d'un
  marché analysé en production (version 2, « 0 exigence traitée sur 4 »), prépare l'entretien (6 questions),
  le chef de file et le partenaire (chez lui) répondent, un marché DECP est proposé puis coché, le mode « sans
  IA » refuse la rédaction et la recherche de questions (409) ; code de production redémarré sur la base montée
  (lectures et écritures 200, options comprises) ; schéma identique à une base neuve (0 écart de colonne ou
  d'index) ; retour arrière (table de l'entretien retirée, rien d'autre ne bouge, code de production relancé) puis
  remontée (schéma identique). Vrais tests rejoués sur la base montée (41 fichiers, dont les quatre tests du
  parcours, C2, D, E2, la démo, l'atelier, le groupement, la sécurité) : 1 124 verts et 37 échecs, **les mêmes 37**
  que le code de production sur la même liste, dans le même ordre (tests propres à SQLite : PRAGMA, `sqlite3`, base
  partagée) ; à conditions égales sur une base neuve (fichiers en échec seulement), 21 échecs de part et d'autre,
  identiques ; aucun dans la rédaction.

---

## R — Contre-relecture de la vague 5 (19/10/2026)

27 remarques des relectures (anti-invention, cloisonnement et coûts, données externes, exactitude et écran),
chacune reproduite avant d'être corrigée. Tests : `tests/test_redaction_v5_contre_relecture.py` (38 tests ; 37
échouaient sur la tête d'intégration `0277857`, le dernier garde le rattachement par la somme, qui doit rester).
La production n'a pas bougé (`feat/produit-acheteur-collectivites` = `b010c59`, déjà fusionnée) ; aucune migration.

| # | remarque | correction |
|---|---|---|
| 1 | le thème d'une question de l'IA entrait dans la fiche [R#] « déclaré par vous » | thème contrôlé comme la question (sinon les mots de la question) et JAMAIS dans le texte que le contrôle rapproche (§ D.3, D.5) |
| 2 | date limite des questions = date de remise quand la phrase donne un délai | la date écrite après le délai est celle de la remise : délai dit, date calculée (§ C2.9) |
| 3 | exigence de l'IA niée ou facultative gardée | mêmes exclusions que le repérage, relue dans son unité ; « à titre facultatif » écarté aussi au repérage ; « dans l'offre » vaut mention de l'offre au CCTP (§ C2.2, C2.5) |
| 4 | « 1 » trouvé dans « 10 » (question de l'IA à l'acheteur) | nombres comparés un à un (§ C2.2) |
| 5 | « chantier » mot principal d'une exigence | « chantier(s) », « entreprise(s) » ajoutés aux mots génériques (§ C2.5) |
| 6 | liste de sous-critères « a ; b ; c. » : seuls les deux premiers | des puces qui se suivent gardent l'annonce de la première (§ C2.4) |
| 7 | « Raccourcir » perdait le « [À compléter] » d'une question passée | `garder_trous`, chef de file et partenaire (§ D.3) |
| 8 | sous-critères « 1.1 / 1.2 » déplacés vers « Prix » | jamais déplacés quand ils portent la numérotation de leur critère ; écart et question `total_sous` (§ C2.4) |
| 9 | « n'est pas interdit » lu comme une interdiction | nature `permis` (ou `declarer`), jamais `interdit`, aucune question `ia` (§ C2.8) |
| 10, 21 | sous-critère sans poids écrit classé à 0 | classé sur le poids écrit de son critère, groupe commun, écran « critère : … (60 %) » (§ D.2, I.3) |
| 11 | réponse d'un partenaire effacée mais copiée dans les faits du chef de file | `oublier_reponses` : passage retiré, fait « à relire » (retrait, déclin, reprise, réponse retirée ou changée) (§ D.4) |
| 12 | invitation coupée par la corbeille : réponse jamais effacée, montrée | cachée tout de suite (fiche, carte, export RGPD), refus qui le dit, purge quotidienne qui l'efface (§ D.4, D.9) |
| 13 | accords-cadres réels (`techniques`) jamais reconnus | `techniques` lu ; montant d'un accord-cadre non repris et verrouillé vide ; données de test et de démo au format réel (§ E2.2, E2.8) |
| 14 | deux marchés au même objet traités comme un seul | « déjà » par l'identifiant public ; l'intitulé seulement face à une saisie (§ E2.4, E2.6) |
| 15 | domaines RGE jamais regroupés (« 2111D111 ») | code sans suffixe de domaine, nom sans « (code) » (§ E2.3) |
| 16 | lectures de noms continuées en arrière-plan, perdues, relancées | un exécuteur de 4 pour le process, nom rangé même après le budget, lecture pas commencée annulée (§ E2.1) |
| 17 | annuaire rappelé pendant que la part est verrouillée | relecture sous verrou avec les noms du cache seulement (§ E2.1) |
| 18 | ligne cochée perdue en silence quand une source tombe | dans `ignorees` avec la panne ; l'écran le dit en alerte (§ E2.4, E2.6) |
| 19 | provenance « decp » prise du navigateur | `references_relues` (§ E2.6) |
| 20 | DECP lu couvre surtout 2024 et après, sans le dire | phrase dans la bulle et sous « Aucun marché trouvé » (§ E2.1) |
| 22 | DECP dit « réalisé seul » dans « Mes preuves » | « attribué seul », champ « Rôle », bulle des Références (§ E2.2) |
| 23 | « Rédiger sans IA » sans effet au téléphone, montré en mode déjà « sans IA » | la carte le dit au lieu du bouton (§ C2.8) |
| 24 | case « Rédiger sans IA » restée cochée après un refus | la case revient à l'état enregistré (aussi « Page de garde », « Sommaire ») (§ C2.8) |
| 25 | « 1.1 / 1.2 » cassé par « Monter / Descendre » | groupes des sous-critères gardés ensemble ; 409 `groupe_sous_criteres` ; remise dans le groupe (§ C2.4) |
| 26 | démo : la question des périodes motivée par une phrase des conditions de participation | une phrase sous un article de candidature n'est prise qu'à défaut (§ D.2) ; la vitrine montre l'article du délai |
| 27 | (antérieure à la vague 5) page du marché à 375 px : défilement horizontal | en-tête de l'estimation du prix qui passe à la ligne |

### R.1 Choix faits par défaut (à valider par Eliot)

1. « équipe » n'est PAS ajouté aux mots génériques de la règle « traitée » (remarque 5) : une exigence peut ne
   porter que sur l'équipe (« Le candidat présentera son équipe »), elle n'aurait plus de mot principal.
2. Accord-cadre : son montant n'est pas repris, et il reste vide tant que la fiche garde la source DECP (un montant
   écrit à la main serait dit « montant d'attribution, source publique DECP ») ; l'alerte dit de choisir
   « Déclaré par vous » pour indiquer le montant commandé. Un marché subséquent garde son montant, sans alerte.
3. Une phrase qui permet l'IA (« est autorisé ») donne un message neutre et laisse le choix « sans IA » ; aucune
   question à l'acheteur.
4. Invitation coupée sans retrait : la réponse est cachée tout de suite et effacée par la purge quotidienne
   (comme les brouillons), pas au moment de la corbeille (un marché restauré garde ses invitations coupées).

### R.2 Vérifications

- Suite complète SQLite (`TZ=UTC`, IA, emails et sources publiques simulés, aucun réseau) : **1 809 tests, tous
  verts** (1 771 + les 38 de la contre-relecture), dont `tests/test_demo_*.py`.
- Les 38 tests de `tests/test_redaction_v5_contre_relecture.py` rejoués sur le code de `0277857` (extrait par
  `git archive`) : 37 échecs, 1 vert (le rattachement par la somme, gardé).
- Empreintes SRI à jour (`scripts/sri_update.py --check`) ; `node --check` de tous les scripts servis.
- Navigateur réel (serveur local, IA coupée, base neuve), vitrine de la démo : page du marché « toiture » à 375 px
  sans défilement horizontal (704 px avant ; en-tête de l'estimation sur deux lignes), carte « Comment vous serez
  noté » qui dit « Rédiger sans IA se choisit depuis un ordinateur, dans l'atelier. » au lieu du bouton ; atelier à
  375 px sans défilement ; question des périodes (R8) motivée par l'article du délai ; à 1 280 px, la case « Rédiger
  sans IA » revient décochée après le refus de la démo, le bouton de la carte est proposé.
- Postgres 16 depuis l'état exact de la production (`b010c59`, tête `y9z0depotlien`, code extrait par
  `git archive`, données créées par le code de production) : les 24 contrôles de migration verts (une seule
  révision, aucune donnée perdue, rejeu, code de production redémarré, schéma identique, retour arrière,
  remontée) ; vrais tests rejoués sur la base montée (42 fichiers, dont celui de la contre-relecture, tout vert) :
  1 162 verts et 37 échecs, **les mêmes 37** que le code de production sur la même liste, dans le même ordre (tests
  propres à SQLite) ; à conditions égales, 21 échecs de part et d'autre, identiques.


## R2 — Seconde contre-relecture de la vague 5 (19/10/2026, après `d342cd5`)

11 remarques (2 lectures : sources et cloisonnement, exactitude), toutes reproduites (scripts de la relecture
rejoués sur `0277857`, `d342cd5` et le correctif) puis corrigées ; aucune rejetée. Plusieurs remarques décrivaient
le même défaut vu par les deux lectures. Tests : `tests/test_redaction_v5_contre_relecture2.py` (29 tests ; 26
échouaient sur `d342cd5`, les 3 autres sont des garde-fous nommés comme tels). Aucune migration, aucun écran changé
(empreintes SRI inchangées).

| remarque | défaut | correction |
|---|---|---|
| R11 (majeur) | une réponse de partenaire retirée, reprise, ou un partenaire retiré PENDANT « Rédiger » restait dans la nouvelle version (« déclaré par votre partenaire », passage copié), jamais nettoyée | au rangement, verrou des invitations qui ont répondu pris d'abord (`ec.verrouiller_repondants`), fiche chantier RELUE et `ec.sans_reponses_changees` : réponse disparue ou changée → fait « à relire », ni passage ni source. Aussi « Raccourcir », l'aide du partenaire (sous le verrou de SON invitation) et `adresser` (verrou de l'invitation du répondant d'abord) (§ D.4) |
| R3 (majeur, ×2) | « Article 5 - Présentation des candidatures et des offres » pris pour un article sur la candidature : exigences de l'IA (et du repérage) écartées | `sous_titre_candidature` : titre lu sur SA ligne, le plus proche décide (sous-titre « 5.2 Contenu de l'offre » avant l'article), un titre qui nomme l'offre ou le mémoire n'est pas « candidature » ; même règle pour l'entretien ; « … comprendra les éléments ci-dessous. » n'est qu'une annonce (§ C2.5) |
| R3 (majeur et mineur) | « facultatif » n'importe où écartait toute la phrase ou toute la liste (« (annexes facultatives) », « … et, de manière facultative, … ») | `_demande_facultative` : seulement une DEMANDE facultative (sujet, verbe, ou tout l'objet) ; l'élément facultatif coordonné sort seul du libellé (`_sans_le_facultatif`), la phrase citée reste entière ; un élément de liste « - à titre facultatif, … » écarté (§ C2.5) |
| R3 (mineur) | élément de liste du CCTP proposé par l'IA relu sans sa phrase d'annonce (« Le candidat joindra à son mémoire technique : ») | `_annonce` : l'élément est relu avec la phrase qui annonce la liste (mention du candidat, négation, faculté) (§ C2.2) |
| R2 (majeur, ×2) | « … 10 jours avant la date limite de remise des offres, soit le 05/12/2026 » : date des questions prise pour la date de remise (date fausse calculée, ou date perdue et fausse question `date_remise`) | `_dates_apres_le_delai` : « soit le / soit jusqu'au / c'est-à-dire le / à savoir le » → date des questions écrite ; « fixée au / prévue le / des offres du » → date de remise ; sinon rien de calculé ; `dates_remise` n'y prend plus la date des questions (§ C2.9) |
| R5 (mineur et majeur) | « entreprise » et « chantier » dans les mots génériques : « une présentation de l'entreprise » disparaissait, « l'organisation du chantier » traitée sur le seul mot « organisation » | retirés des mots génériques ; `cles_traitement` ne les ignore que pour la règle « traitée » et s'il reste au moins deux autres mots (§ C2.5) |
| R25 (mineur) | parties tirées du groupement placées au milieu d'un groupe de sous-critères (1.1, 1.2, 2, 3, 1.3) | `_ancre` passe tout le groupe (`at._hors_des_groupes`) |

### R2.1 Choix faits par défaut (à valider par Eliot)

1. Une réponse de l'entretien CHANGÉE pendant la rédaction (même ref, autre texte) rend le fait « à relire » plutôt
   que de le rapprocher de la nouvelle réponse : prudence (l'IA a écrit d'après l'ancienne).
2. « (facultatif) » ou « facultative » seul, sans « à titre » ni « de manière », ne rend pas une demande facultative
   (comme avant la contre-relecture précédente) : le mot qualifie souvent une pièce annexe, pas la demande.
3. Un titre qui nomme à la fois les candidatures et l'offre (ou les plis) n'est pas un article sur la candidature :
   ce qu'il demande peut entrer dans la liste ; les pièces administratives restent écartées par leur propre règle.

### R2.2 Vérifications

- Suite complète SQLite (`TZ=UTC`, IA, emails et sources publiques simulés, aucun réseau) : **1 838 tests, tous
  verts** (1 809 + les 29 de cette contre-relecture), dont `tests/test_demo_*.py` ; la grille de la vitrine
  (7 exigences, date des questions, aucune question à l'acheteur) est identique à celle de `d342cd5`.
- Les 29 tests rejoués sur le code de `d342cd5` (extrait par `git archive`) : 26 échecs, 3 garde-fous verts.
- Empreintes SRI à jour (`scripts/sri_update.py --check`) ; `node --check` des 5 scripts servis.
- Postgres 16 depuis l'état exact de la production (`b010c59`, tête `y9z0depotlien`) : les 23 contrôles de migration
  verts (27 contrôles en tout, aucun échec) ; course réelle : le retrait d'une réponse par le partenaire ATTEND le rangement d'un texte rédigé par l'IA
  (verrou de son invitation) puis le nettoie ; témoin sans le verrou : le retrait passe et la copie reste (le défaut
  corrigé) ; vrais tests sur la base montée (43 fichiers, dont les deux contre-relectures, tout vert) : 1 191 verts
  et 37 échecs, **les mêmes 37** que le code de production sur la même liste, dans le même ordre (tests propres à
  SQLite) ; à conditions égales, 21 échecs de part et d'autre, identiques.
