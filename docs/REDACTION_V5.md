# Rédaction, vague 5 — « Coller au chantier et à l'acheteur » : contrat

Étude « rédaction » § 8 (V5) : l'entretien chantier (D, § 6.9), la liste complète des exigences et les
sous-critères (C2 complet, § 6.3), les références tirées des DECP et les qualifications RGE (E2, § 6.7).
Chaque chantier a sa section ; la doctrine (§ 7) vaut pour tous : un fait ne vient jamais de l'IA, on ne dit
jamais le mot interdit, le cadre de l'acheteur commande, la matière reste chez son propriétaire.

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
| DECP (`data.economie.gouv.fr`, jeu `decp-2022-marches-valides`) | `startswith(titulaire_id_1, "<SIREN>") or …_2 or …_3`, du plus récent au plus ancien, 100 lignes par page, 3 pages au plus | `id`, `objet`, `montant` (attribution, HT), `datenotification`, `acheteur_id`, `nature`, `titulaire_id_1..3`, `typegroupementoperateurs`, `idaccordcadre`, `lieuexecution_code` |
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
  relu au plus tôt 10 minutes après ;
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
| `montant_ht` | gardé tel quel ; < 1 000 € ou > 50 M€ → alerte « Montant inhabituel… Cochez seulement s'il est juste. » ; 0, négatif ou illisible → non repris (alerte) ; accord-cadre (la nature le dit, ou `idaccordcadre` est l'identifiant de la ligne elle-même) → alerte « le montant de DECP est un maximum ou une estimation, pas ce qui a été commandé » ; un marché subséquent n'en porte pas |
| `annee` | année de notification ; date absente, illisible, future ou avant 1990 → non reprise (alerte) |
| `role` | « Solidaire » → `groupement_solidaire` ; « Conjoint » → `groupement_conjoint` ; « Pas de groupement » sans autre titulaire → `seul` ; « Pas de groupement » avec d'autres titulaires → aucun rôle, alerte « précisez votre rôle après l'ajout » |

Le texte d'une référence DECP dit **« attribué »**, jamais « réalisé » : `texte_de(…, attribue=True)` →
« …; montant d'attribution 85 000 € HT ; attribué seul » ; dans l'atelier, la fiche insérée porte « Marché
attribué à l'entreprise seule » et « Montant d'attribution » (`preuves_atelier.bloc(…, attribue=True)`) ;
`texte_ia` aussi. Le lieu d'exécution (un code) est montré, pas enregistré.

### E2.3 Liste RGE → une qualification PROPOSÉE ; une expirée exclue et signalée

Les lignes de la liste (une par domaine et par établissement) sont regroupées par code, organisme,
certificat et fin de validité. Une qualification proposée :
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
  la liste, puis cochez de nouveau. » ; une ligne `manque` → `ignorees` avec sa raison ; une ligne déjà dans
  « Mes preuves » (même identifiant DECP, même fiche ou même intitulé) → `deja`.
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
- Rien n'est retiré ni réécrit ; un élément déjà dans la part (même intitulé) n'est pas doublé ; 50
  références et 50 qualifications au plus.
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
de Kerhel ») dont un en groupement solidaire et un montant inhabituel (1 €, accord-cadre) montré avec son
alerte ; une qualification RGE valable et une expirée signalée. Bandeau : « Exemple fictif de la
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
