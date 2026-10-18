# À valider : mentions juridiques pour les documents déposés par le lien d'un partenaire

**Statut : brouillon, rien n'est publié.** Les pages juridiques (`app/static/legal/*.html`, `docs/legal/*.md`,
`scripts/build_legal.py`) ne sont **pas modifiées** par ce chantier. Ce document propose les mentions à ajouter,
pour qu'Eliot les fasse valider avant de les publier (il les reporte ensuite dans `docs/legal/*.md` puis lance
`python scripts/build_legal.py`).

Fonction concernée : « Vos documents pour Adjugo » (rédaction, vague 4, décision 5 option a — contrat
`docs/REDACTION_V4_GROUPEMENT.md` § 21). Un partenaire venu par **lien magique, sans compte Adjugo**, dépose ses
propres documents (anciens mémoires, plaquette, références, attestations) pour que l'aide d'Adjugo rédige SES
parties du dossier de présentation commun. Au premier dépôt, il coche « J'accepte les conditions d'utilisation
(version 1.2) » et « J'accepte la politique de confidentialité (version 1.3) », avec un lien vers `/cgv` et
`/confidentialite` ; Adjugo enregistre l'heure, la version et l'empreinte des deux textes, et l'inscrit au journal.
Une nouvelle version d'un des deux textes redemande l'accord avant le dépôt suivant.

---

## 1. Ce que les textes actuels ne couvrent pas

| Point | Texte actuel | Ce que fait la fonction |
|---|---|---|
| Qui est le cocontractant | CGV, préambule : « toute personne morale ou tout professionnel souscrivant au Service » (le « Client ») | Le partenaire ne souscrit rien : il est invité par un Client (le chef de file), sans compte, sans paiement. Les CGV ne disent pas qu'elles s'appliquent à lui, ni comment. |
| Rôle d'Adjugo | Politique, § 1 : pour les documents téléversés **par le Client**, Adjugo est « pour l'essentiel » **sous-traitant du Client** | Les documents sont déposés par le partenaire, rattachés à SON invitation, **jamais visibles du Client** (le chef de file) ; ils ne servent qu'au partenaire. Adjugo n'agit donc pas sur instruction du Client pour ces documents : le rôle (responsable de traitement pour le partenaire, ou autre qualification) est à arbitrer par le conseil. |
| Catégories de données | Politique, § 3 : « Documents téléversés … téléversées par l'utilisateur » | Couvre le contenu en général ; ne dit pas qu'un partenaire sans compte peut déposer, ni que le nom du fichier est gardé. |
| Durée de conservation | Politique, § 5 : documents « pendant la durée d'utilisation du Service, puis suppression 90 jours après la clôture du compte » | Aucun compte ici. Règle appliquée : supprimé aussitôt que le partenaire le supprime, s'il décline, si le chef de file le retire, ou s'il réinitialise son espace ; sinon automatiquement **6 mois après le résultat du marché** (gagné, perdu, abandonné), à défaut 6 mois après sa date limite, à défaut 6 mois après le dernier dépôt ; 30 jours après l'expiration du lien ; avec le marché quand il est effacé. |
| Destinataires (IA) | Politique, § 6 : le fournisseur d'IA reçoit « données d'entreprise utiles à la rédaction (noms des salariés remplacés par des étiquettes avant tout envoi) » | Juste dans l'esprit ; à préciser : seuls des **passages** des documents déposés partent, noms des personnes masqués, jamais un CV, jamais le nom du fichier. |
| Droits | Politique, § 8 : « Cas des documents téléversés … transmise au Client responsable de traitement » | Ici, ce n'est PAS au Client : le partenaire supprime et télécharge lui-même ses documents, et le chef de file n'y a jamais accès. |

## 2. Texte proposé — Conditions générales (nouvel article, par exemple 2.4)

> **2.4. Partenaire invité par un lien.** Un Client peut inviter un partenaire (co-traitant d'un groupement) à
> rédiger sa part d'un dossier commun au moyen d'un lien personnel, sans compte ni abonnement. Le partenaire qui
> dépose des documents dans son espace privé accepte les présentes conditions pour cet usage, gratuit et limité à
> la rédaction de ses parties du dossier. Il garantit disposer des droits nécessaires sur les documents déposés et
> s'engage à ne pas y inclure de données sensibles au sens de l'article 9 du RGPD ni de curriculum vitae. Ces
> documents ne sont accessibles ni au Client qui l'a invité, ni aux autres membres du groupement ; ils servent
> uniquement à l'aide à la rédaction de ses parties. Le partenaire reste seul responsable des textes qu'il envoie
> au groupement. Adjugo peut limiter le nombre et la taille des documents déposés.

Variante courte, si Eliot préfère un renvoi :

> Les présentes conditions s'appliquent aussi, pour le seul dépôt de documents dans son espace privé, au partenaire
> invité par un lien personnel ; les règles de ce dépôt figurent dans la Politique de confidentialité.

## 3. Texte proposé — Politique de confidentialité

**§ 1, après « Précision sur les rôles »** (rôle à confirmer par le conseil) :

> **Partenaire invité par un lien.** Lorsqu'un partenaire invité par un Client dépose, depuis son lien personnel,
> des documents dans son espace privé (fonction « Vos documents pour Adjugo »), ces documents ne sont accessibles
> ni au Client ni aux autres membres du groupement, et ne servent qu'à l'aide à la rédaction des parties de ce
> partenaire. Pour ce traitement, l'Éditeur agit en qualité de responsable de traitement.

**§ 3, tableau, ligne ajoutée :**

> | Documents d'un partenaire invité | documents déposés par le partenaire dans son espace privé (anciens mémoires,
> plaquette, références, attestations : nom du fichier, contenu pouvant contenir des noms et coordonnées), date et
> version de son accord aux conditions | déposés par le partenaire depuis son lien personnel |

**§ 4, tableau, ligne ajoutée** (base à confirmer) :

> | Aide à la rédaction des parties d'un partenaire invité, à partir de ses propres documents | Exécution des
> conditions acceptées par le partenaire (art. 6.1.b) |

**§ 5, tableau, ligne ajoutée :**

> | Documents d'un partenaire invité | supprimés dès que le partenaire les supprime, s'il quitte le groupement
> (invitation déclinée ou retirée) ou réinitialise son espace privé ; à défaut, automatiquement **six (6) mois
> après le résultat du marché** (gagné, perdu ou abandonné), ou six mois après sa date limite si aucun résultat
> n'est enregistré ; trente (30) jours après l'expiration du lien ; avec le marché lorsqu'il est supprimé |

**§ 6, ligne du fournisseur d'IA, colonne « Données concernées » :**

> …, données d'entreprise utiles à la rédaction, **passages des documents déposés par un partenaire pour ses
> propres parties** (noms des personnes remplacés par des étiquettes avant tout envoi ; jamais un curriculum
> vitae ni le nom d'un fichier)

**§ 8, après « Cas des documents téléversés » :**

> **Documents d'un partenaire invité.** Le partenaire supprime et télécharge lui-même ses documents depuis son
> espace privé, et obtient dans un fichier la liste de ce qu'il a déposé et de son accord (portabilité). Ses
> autres demandes sont adressées à l'Éditeur ; elles ne sont pas transmises au Client qui l'a invité.

## 4. Points à arbitrer

1. **Rôle d'Adjugo** pour ces documents (responsable de traitement, ou autre qualification) : c'est l'avis que la
   version précédente du contrat attendait du conseil. La fonction est construite pour que le chef de file n'y ait
   jamais accès, ce qui plaide pour « responsable de traitement ».
2. **Base légale** : exécution des conditions acceptées par le partenaire (6.1.b) — il coche les deux cases — ou
   consentement (6.1.a). La case actuelle dit « J'accepte les conditions d'utilisation » et « J'accepte la
   politique de confidentialité » : elle vaut acceptation des conditions, pas un consentement au sens de
   l'article 7 (retrait = suppression des documents, déjà possible à tout moment).
3. **Durée de 6 mois** après le résultat (réglable : `DEPOT_LIEN_CONSERVATION_MOIS`) et les deux replis (date
   limite, dernier dépôt) : à confirmer, puis à recopier tels quels.
4. **Faut-il une version propre** au partenaire invité (conditions d'utilisation distinctes des CGV) ? La fonction
   enregistre déjà la version et l'empreinte de chaque page acceptée : une nouvelle page, ou une nouvelle version,
   redemande l'accord sans autre changement (les pages sont lues par `app/services/depot_lien.textes_juridiques`,
   qui y lit « Version : … — Dernière mise à jour : … »).
5. **Mentions d'information** sur la page du lien : la bulle (i) de « Vos documents pour Adjugo » dit déjà qui voit
   quoi (« Seuls vous et Adjugo les lisez ; le chef de file ne les voit jamais »), à quoi ils servent, et combien de
   temps ils sont gardés. À relire avec le conseil.
