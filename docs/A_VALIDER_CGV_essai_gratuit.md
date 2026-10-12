# À valider : corrections des pages juridiques après le garde-fou de l'essai gratuit

**Statut : CGV publiées le 12/10/2026 (décision d'Eliot).** L'article 3.5 de `docs/legal/cgv.md` reprend
la **version détaillée** du § 2 (« limite d'usage », « quinze (15) questions par jour »), suivie d'une
phrase sur la fin de l'essai : les fonctions d'intelligence artificielle ne sont plus accessibles sans
formule payante (un traitement commencé pendant l'essai est mené à son terme). Page `/cgv` régénérée
par `python scripts/build_legal.py`. La politique de confidentialité (§ 4) n'est pas modifiée.

Texte d'origine de la proposition, conservé ci-dessous pour mémoire.

Pourquoi : depuis le chantier E (garde-fou de l'essai), l'essai ne donne plus « 30 analyses par mois »
mais **30 analyses sur toute sa durée**, **15 questions par jour** sur les dossiers, et une **limite
d'usage** de l'IA (budget interne, jamais affiché en euros) au-delà de laquelle les fonctions d'IA
s'arrêtent jusqu'à la souscription. Le texte actuel de l'article 3.5 des CGV (« dont 30 analyses
d'appel d'offres par mois ») ne correspond plus.

---

## 1. CGV, article 3.5 « Essai gratuit » — texte actuel

> Tout nouveau compte bénéficie d'un **essai gratuit de trente (30) jours**, **sans carte bancaire**,
> donnant accès à l'ensemble des fonctionnalités au niveau de la formule **Pro** (dont **30 analyses
> d'appel d'offres par mois**). L'essai est limité à **un (1) par Client**. […]

## 2. Texte proposé (remplace la première phrase ; le reste de l'article est inchangé)

> Tout nouveau compte bénéficie d'un **essai gratuit de trente (30) jours**, **sans carte bancaire**,
> donnant accès à l'ensemble des fonctionnalités au niveau de la formule **Pro**, dans les limites
> suivantes, valables pour **toute la durée de l'essai** : **trente (30) analyses d'appel d'offres au
> total** (et non par mois), **quinze (15) questions par jour** posées sur les dossiers, et une
> **limite d'usage** des fonctions d'intelligence artificielle destinée à protéger le Service. Lorsque
> l'une de ces limites est atteinte, les fonctions concernées sont suspendues jusqu'à la souscription
> d'une formule payante ; un traitement déjà commencé (lecture et analyse d'un dossier, rédaction)
> est toujours mené à son terme. Ces limites ne s'appliquent pas aux formules payantes, régies par
> l'article 3.1.

Variante plus courte, si Eliot préfère ne pas détailler :

> […] au niveau de la formule **Pro**, dans la limite de **trente (30) analyses d'appel d'offres pour
> toute la durée de l'essai**, de **quinze (15) questions par jour** et d'un **usage raisonnable** des
> fonctions d'intelligence artificielle ; au-delà, ces fonctions sont suspendues jusqu'à la
> souscription d'une formule payante.

Points à arbitrer :
- « limite d'usage » (précis, c'est le mot de l'écran) ou « usage raisonnable » (plus courant en CGV) ;
- le chiffre de 15 questions par jour est réglable (`TRIAL_QUESTIONS_PAR_JOUR`) : le citer engage à
  le tenir ; on peut écrire « un nombre de questions par jour indiqué dans l'application » ;
- le montant du budget (15 € par défaut) **ne doit pas** apparaître : il n'est montré nulle part au
  client (décision du fondateur).

## 3. Écrans déjà alignés (aucune action)

- Page « Forfaits » de l'application, carte « Essai gratuit » : « 30 analyses IA pendant l'essai »
  (bulle (i) : 30 analyses sur toute la durée, 15 questions par jour, limite d'usage, une opération
  lancée va au bout, pas de limite avec un forfait) et « 15 questions par jour sur vos dossiers ».
- Page d'accueil publique (`landing.html`) : elle décrit les forfaits Pro et Business
  (« 30 analyses / mois », « 100 analyses / mois »), pas l'essai : inchangée.

## 4. Politique de confidentialité (facultatif)

Le tableau des catégories de données cite déjà les « données d'usage : analyses réalisées, quotas
consommés ». Le relevé du coût de l'IA (table `usage_ia`) ne contient qu'un identifiant de compte, des
montants et des nombres de tokens, sans contenu ni adresse IP (un appel anonyme du côté acheteur est
compté « acheteur:anonyme ») : il entre dans cette catégorie. Ajout possible, pour être complet :

> | **Données d'usage** | analyses réalisées, quotas consommés, **mesure interne de la consommation des
> fonctions d'IA (nombre d'appels et de tokens, coût de traitement)**, journaux techniques (logs),
> adresse IP, horodatages | générées par le Service |
