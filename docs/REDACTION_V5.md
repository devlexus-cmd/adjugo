# Rédaction, vague 5 — coller au chantier et à l'acheteur

Étude : `etudes/redaction.md` § 6.3 (C2 complet), § 6.7 (E2), § 6.9 (D), § 7 (doctrine), § 8 (V5),
§ 10 (décisions 7 à 11). Base de production au départ : `da9ef0f` (branche `feat/produit-acheteur-collectivites`).

Ce contrat est écrit par chantier. Chaque chantier a sa section ; les sections ne se recouvrent pas.

Vocabulaire à l'écran : « groupement », « partenaire », « chef de file », « partie » (le code dit « section »),
« valider » (jamais « signer »), jamais « consortium », jamais « vérifié ». Zéro émoji, explications dans une
bulle (i), compact, rien collé aux bords, lisible à 375 px.

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
  d'exigence, sinon la phrase), jamais écrit par l'IA ; les mêmes exclusions que le repérage s'appliquent ;
- question : au moins une phrase retrouvée mot pour mot, question de 15 à 300 caractères finie par « ? »,
  aucun nombre absent des phrases retrouvées ; sinon écartée.
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
  liste parle de notation (« apprécié selon les éléments suivants : ») ; une liste ouverte par « le mémoire
  comprendra : » est une liste d'EXIGENCES, jamais de sous-critères ;
- lignes pondérées sans marque (un tableau) : seulement si leur somme fait le poids du critère ;
- énumération en ligne après « selon : » dont chaque élément a un poids.
Rattachement : la liste est au critère de sa zone, sauf si ses poids font exactement le poids d'un AUTRE
critère (« Valeur technique 60 % ; Prix 40 %. » puis des sous-critères de 60 points au total), ou si la phrase
qui l'annonce nomme un autre critère.

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
faux). La partie garde le critère, son id et son poids de la grille : « Comment vous serez noté » reste la
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
  ligne séparée par « ; »), avec la phrase d'annonce (`intro`).
Jamais : une pièce administrative ou un prix (DC1, DC2, DUME, Kbis, attestations, assurances, RIB, acte
d'engagement, bordereau, DPGF, DQE, chiffre d'affaires…), le dépôt (plateforme, date limite, format, pli,
signature), la visite, les variantes, ce que fait le candidat retenu ou le titulaire, ce qui est permis
(« peut », « pourra ») ou nié (« n'est pas tenu »), une phrase d'un article sur la candidature
(« Conditions de participation »…), « justifier d'une capacité », « une offre conforme », l'obligation d'utiliser
le cadre (déjà dans « Ce que le dossier impose »), une simple limite de longueur (« au maximum 10 pages » ; mais
« l'encadrement du chantier (2 pages maximum) » est bien une exigence). Une exigence sans mot principal (« un
mémoire technique ») n'est pas gardée. Au plus 40, dans l'ordre du dossier.

Une phrase est l'« unité » qui contient la marque : coupée aux fins de phrase, aux puces, aux titres (ligne
courte sans ponctuation finale, « Article 5 - … ») ; un retour à la ligne de mise en page ne coupe pas.

**La règle « traitée », explicite et testée** (`grille_exigences.traitement`, texte `REGLE_TRAITEE`) :
1. les mots principaux d'une exigence sont les mots de son libellé (sinon de sa phrase), sans mots vides ni
   mots qu'on trouve dans toute exigence (« candidat », « mémoire », « présenter », « préciser », « pages »…),
   réduits à leurs 5 premières lettres (« déchets » ↔ « déchet »), au plus 8 ;
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
`declarer` (« indique s'il a eu recours à… »), sinon `mention` (et alors une question à l'acheteur est
proposée). La phrase est affichée sur la carte, dans l'atelier (avant la création du plan aussi) et chez les
partenaires (message propre : « Le chef de file choisit si le dossier se rédige sans IA »).

**Le mode « sans IA »** (pour CE dossier, choisi par le chef de file, proposé quand le règlement parle d'IA,
toujours possible par la case « Rédiger sans IA ») :
- rangé dans `options_export["sans_ia"] = {actif, le, par}` ; `PUT /api/atelier/{pid}/options {sans_ia}`
  (ou `POST /api/atelier/{pid} {base, sans_ia: true}` à la création) ; inscrit au journal chaîné
  (`atelier.sans_ia`, « mode sans IA activé / retiré ») ; la réponse de `/options` garde `options =
  {page_garde, sommaire}` (contrat de la vague 2) et ajoute `sans_ia` ;
- AUCUN appel d'IA de rédaction : « Rédiger », « Rédiger tout », « Raccourcir » (`at.lancer`), l'aide de l'IA
  du partenaire (`ag.lancer_aide`) et « Harmoniser le ton » (`asm.lancer_harmonisation`) → 409
  `mode_sans_ia` ; les boutons disparaissent (atelier, espace du partenaire) et « J'écris moi-même » devient
  le bouton principal ; « Harmoniser » n'est plus proposé (`harmoniser.jonctions = 0`) ;
- le contrôle des faits (`fs.controler`, sans IA) et la liste des exigences continuent ;
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
Adjugo … : vérifiez-la » ; jamais pour des jours francs ou ouvrés). « Les réponses seront envoyées… » n'est pas
cette date.

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
