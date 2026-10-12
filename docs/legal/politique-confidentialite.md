# Politique de confidentialité

*Version : 1.3 — Dernière mise à jour : 8 octobre 2026*

---

La présente Politique de confidentialité décrit la manière dont le service **Adjugo** collecte, utilise, conserve et protège les données à caractère personnel, conformément au **Règlement (UE) 2016/679 (RGPD)** et à la **loi « Informatique et Libertés » n° 78-17 du 6 janvier 1978 modifiée**.

## 1. Responsable du traitement

Le responsable du traitement des données collectées via le Service est :

- **Dénomination** : Eliot VIEGAS, entrepreneur individuel (nom commercial PADIS)
- **Adresse** : 9 rue Saint-Yves, 29000 Quimper, France
- **SIREN / SIRET** : 105 406 813 / 105 406 813 00011
- **Contact** : eviegas@padis-core.com

> **Précision sur les rôles.** Pour les données de gestion du compte et de facturation, l'Éditeur agit en qualité de **responsable de traitement**. Pour les données personnelles éventuellement contenues dans les **documents téléversés par le Client** (DCE, pièces d'entreprise, contacts de co-traitants), l'Éditeur agit pour l'essentiel en qualité de **sous-traitant** du Client (au sens de l'article 28 RGPD), le Client demeurant responsable de traitement de ces données. Un **accord de traitement des données (DPA) conforme à l'article 28 du RGPD** est [publié et consultable ici](/dpa).

> **Service de sourcing destiné aux acheteurs publics (« côté acheteur »).** Adjugo propose, à des acheteurs publics tiers, un outil d'aide à la décision qui exploite exclusivement des **données d'entreprises issues de l'open data public** (SIRENE, DECP, BODACC) à des fins d'information de marché. Pour ce traitement, l'Éditeur agit en qualité de **responsable de traitement autonome et distinct**, indépendamment du logiciel destiné aux PME — les deux faces de la plateforme sont strictement cloisonnées et aucune donnée d'un Client PME n'est utilisée pour ce service.

## 2. Délégué à la protection des données (DPO) / Contact

Pour toute question relative à vos données personnelles ou pour exercer vos droits :

- **E-mail** : eviegas@padis-core.com
- **DPO** : non désigné (désignation non obligatoire pour une structure de cette taille) — point de contact « protection des données » : Eliot Viegas, eviegas@padis-core.com
- **Adresse postale** : 9 rue Saint-Yves, 29000 Quimper, France

## 3. Données collectées

Le Service collecte et traite les catégories de données suivantes :

| Catégorie | Exemples de données | Origine |
|---|---|---|
| **Compte utilisateur** | nom, prénom, adresse e-mail, mot de passe (haché), rôle | fournies par l'utilisateur |
| **Entreprise du Client** | raison sociale, SIREN/SIRET, adresse, secteur, qualifications | fournies par l'utilisateur / sources publiques |
| **Contacts** | personnes de contact de l'entreprise et de co-traitants identifiés | fournies par l'utilisateur / sources publiques (SIRENE, BODACC) |
| **Documents téléversés** | DCE, pièces administratives, documents d'entreprise (pouvant contenir des données personnelles : noms, signatures, coordonnées) | téléversées par l'utilisateur |
| **Données d'usage** | analyses réalisées, quotas consommés, journaux techniques (logs), adresse IP, horodatages | générées par le Service |
| **Données de facturation** | formule souscrite, historique de paiement, identifiants de transaction | générées via Stripe |
| **Demandes d'accès et de démonstration** | nom, prénom, adresse e-mail professionnelle, téléphone (facultatif), entreprise ou collectivité, profil, message | fournies par la personne via le formulaire « Demander un accès » |
| **Données d'entreprises (sourcing acheteur)** | raison sociale, SIREN/SIRET, commune et département, code et libellé d'activité (NAF), catégorie (PME/ETI/GE), effectif, marchés publics remportés, signaux de procédure collective | **open data public** : SIRENE (recherche-entreprises.api.gouv.fr), DECP (data.economie.gouv.fr), BODACC |

> Adjugo applique une **règle stricte de minimisation et d'anti-hallucination** : seules des données réelles et sourcées sont traitées ; aucune donnée personnelle n'est inventée. Le Service n'a pas vocation à collecter de **données sensibles** au sens de l'article 9 du RGPD ; le Client s'engage à ne pas téléverser de telles données sans base légale appropriée.

## 4. Finalités et bases légales

| Finalité | Base légale (art. 6 RGPD) |
|---|---|
| Création et gestion du compte, fourniture du Service | **Exécution du contrat** (art. 6.1.b) |
| Réalisation des analyses, sourcing, génération de documents (CERFA, DUME, mémoire) | **Exécution du contrat** (art. 6.1.b) |
| Vérification des co-traitants (SIRENE/BODACC, signaux de procédure collective) | **Exécution du contrat** + **intérêt légitime** (art. 6.1.f) |
| Sourcing acheteur : information de marché et aide à la décision des acheteurs publics (sourcing préalable au sens de l'art. R2111-1 du Code de la commande publique) | **Intérêt légitime** (art. 6.1.f) — recensement de l'offre économique à partir de données publiques ; le cas échéant, **mission d'intérêt public** (art. 6.1.e) côté acheteur public |
| Facturation et gestion des paiements | **Exécution du contrat** + **obligation légale** (comptable/fiscale) (art. 6.1.c) |
| Sécurité, prévention de la fraude, journalisation technique | **Intérêt légitime** (art. 6.1.f) |
| Réponses aux demandes de support | **Exécution du contrat** / **intérêt légitime** |
| Réponse aux demandes d'accès et de démonstration (formulaire « Demander un accès ») | **Mesures précontractuelles** prises à la demande de la personne (art. 6.1.b) et **intérêt légitime** (art. 6.1.f) |
| Communications commerciales (le cas échéant) | **Intérêt légitime** ou **consentement** selon le cas (prospection B2B) |
| Respect des obligations légales et réponses aux autorités | **Obligation légale** (art. 6.1.c) |

## 5. Durées de conservation

| Donnée | Durée de conservation |
|---|---|
| Données de compte | pendant la durée de la relation contractuelle, puis suppression ou anonymisation **12 mois** après la clôture du compte |
| Documents téléversés (DCE, pièces) | pendant la durée d'utilisation du Service, puis suppression **90 jours** après la clôture du compte, ou immédiatement sur demande |
| Données de facturation | **10 ans** (obligation comptable et fiscale, art. L.123-22 Code de commerce) |
| Journaux techniques (logs) | **6 mois** |
| Données de prospection | **3 ans** à compter du dernier contact |
| Demandes d'accès et de démonstration | **3 ans** à compter du dernier contact. La demande est transmise par e-mail à la messagerie de l'Éditeur ; elle n'est pas enregistrée dans la base de données du Service |
| Données de sourcing acheteur (open data entreprises) | **non conservées durablement** : interrogées en temps réel auprès des sources publiques à chaque requête et restituées à l'écran ; aucune base permanente n'est constituée. Seuls d'éventuels journaux techniques subsistent (**6 mois**) |

À l'expiration de ces durées, les données sont supprimées ou anonymisées de manière irréversible. **Les copies de sauvegarde** contenant ces données sont **purgées au plus tard sous 14 jours** ; une suppression demandée par le Client devient donc définitive, y compris dans les sauvegardes, sous ce délai.

## 6. Destinataires et sous-traitants

Les données sont traitées par les équipes habilitées de l'Éditeur et par les **sous-traitants / destinataires** suivants, sélectionnés pour leurs garanties de sécurité et liés par des engagements contractuels conformes à l'article 28 RGPD :

| Prestataire | Rôle | Données concernées | Localisation |
|---|---|---|---|
| **Railway Corporation** | Hébergement applicatif (calcul) et base de données | l'ensemble des données du Service | **Base de données : Union européenne** ; hébergement applicatif : voir art. 7 |
| **Cloudflare, Inc.** (stockage R2) | Stockage des fichiers téléversés et des sauvegardes | DCE, pièces administratives et documents d'entreprise (données personnelles éventuelles) | **Union européenne** (Europe de l'Ouest — WEUR) |
| **{{AI_PROVIDER}}** ({{AI_PRODUCT}}) | Fournisseur du modèle d'IA pour l'analyse et la génération de documents | dossiers de consultation analysés (lus en entier), questions posées, données d'entreprise utiles à la rédaction (noms des salariés remplacés par des étiquettes avant tout envoi) | {{AI_LOCATION_FULL}} |
| **Brevo** (Sendinblue SAS) | Envoi des e-mails transactionnels | adresse e-mail du destinataire, contenu des notifications | **Union européenne** (France) |
| **Google** (Google Cloud France / Google LLC — Google Workspace) | Messagerie de l'Éditeur (adresses @adjugo.pro) : réception des demandes d'accès et des échanges par e-mail | coordonnées et message des demandes d'accès, correspondance | Union européenne / **États-Unis** (encadré par CCT et EU-U.S. Data Privacy Framework) |
| **Functional Software, Inc.** (Sentry) | Observabilité et suivi technique des erreurs | journaux techniques, identifiants techniques, adresse IP | **États-Unis** (encadré par CCT) |
| **Stripe** (Stripe Payments Europe, Ltd. / Stripe, Inc.) | Traitement des paiements | données de facturation et de paiement (l'Éditeur n'accède pas aux numéros de carte) | UE / États-Unis |

**Intelligence artificielle.** {{AI_ROLES}} Les contenus envoyés ne sont pas utilisés pour entraîner un modèle d'IA ({{AI_ENTRAINEMENT}}). La conservation est encadrée par les conditions applicables à l'API ({{AI_CONSERVATION}}).{{AI_SOUS_TRAITANTS_MISTRAL}} Lieux de stockage et de calcul : tableau ci-dessus.

Les données peuvent également être communiquées aux **autorités administratives ou judiciaires** lorsque la loi l'exige.

Adjugo **ne vend pas** les données personnelles et ne les transmet pas à des tiers à des fins commerciales.

## 7. Transferts de données hors Union européenne

Les **données applicatives du Service — base de données, fichiers téléversés et sauvegardes — sont hébergées en Union européenne** (base de données Railway en région UE ; fichiers et sauvegardes Cloudflare R2 en Europe de l'Ouest).

Des **transferts résiduels vers des pays tiers** subsistent toutefois pour certains traitements techniques : {{AI_TRANSFER_MENTION}}le suivi technique des erreurs (Sentry, États-Unis), la messagerie de l'Éditeur (Google, UE/États-Unis) et le prestataire de paiement (Stripe, UE/États-Unis). Le cas échéant, le calcul applicatif peut également être opéré hors UE.

Ces transferts sont encadrés par des **garanties appropriées** au sens du chapitre V du RGPD, notamment :

- la signature de **clauses contractuelles types** (CCT / SCC) adoptées par la Commission européenne{{AI_CCT_MISTRAL}} ;
- le cas échéant, l'adhésion du prestataire au **EU-U.S. Data Privacy Framework** ;
- des mesures techniques et organisationnelles complémentaires (chiffrement en transit et au repos, minimisation des données transmises).

## 8. Droits des personnes concernées

Conformément aux articles 15 à 22 du RGPD, vous disposez des droits suivants :

- **Droit d'accès** à vos données ;
- **Droit de rectification** des données inexactes ou incomplètes ;
- **Droit à l'effacement** (« droit à l'oubli »), dans les limites des obligations légales de conservation ;
- **Droit à la limitation** du traitement ;
- **Droit à la portabilité** de vos données ;
- **Droit d'opposition** au traitement fondé sur l'intérêt légitime, et à la prospection commerciale ;
- **Droit de définir des directives** relatives au sort de vos données après votre décès ;
- **Droit de retirer votre consentement** à tout moment, lorsque le traitement repose sur le consentement.

**Exercice des droits.** Vous pouvez exercer ces droits en écrivant à **eviegas@padis-core.com**. Une preuve d'identité pourra être demandée. Une réponse vous sera apportée dans un délai d'**un (1) mois** (prorogeable de deux mois en cas de complexité).

> **Cas des documents téléversés.** Lorsqu'une demande porte sur des données personnelles contenues dans des documents téléversés par un Client (Adjugo agissant alors comme sous-traitant), la demande est, le cas échéant, transmise au Client responsable de traitement, ou traitée selon ses instructions.

> **Information des personnes — sourcing acheteur (art. 14 RGPD).** Dans le cadre du service destiné aux acheteurs publics, Adjugo traite des **données d'entreprises issues de registres publics ouverts** (SIRENE, DECP, BODACC) sans les collecter directement auprès des personnes concernées. Conformément à l'**article 14 du RGPD**, les personnes physiques éventuellement identifiables (notamment les dirigeants d'entreprises individuelles) sont informées par la présente Politique de l'existence de ce traitement, de sa finalité (information de marché / sourcing préalable, art. R2111-1 du Code de la commande publique), de sa base légale (**intérêt légitime**, art. 6.1.f) et de la **source des données** (open data public). Elles disposent d'un **droit d'opposition** à ce traitement, ainsi que des droits d'accès, de rectification et d'effacement, exerçables à **eviegas@padis-core.com**. Par **minimisation** (art. 5.1.c RGPD), les fiches présentées à l'acheteur **n'affichent pas le nom des dirigeants** : seules y figurent les données strictement utiles à l'appréciation de l'offre économique (raison sociale, implantation, activité, capacité, santé financière publique).

**Réclamation.** Vous disposez du droit d'introduire une réclamation auprès de la **CNIL** (Commission Nationale de l'Informatique et des Libertés), 3 place de Fontenoy, TSA 80715, 75334 Paris Cedex 07 — www.cnil.fr.

## 9. Sécurité

L'Éditeur met en œuvre des mesures techniques et organisationnelles appropriées pour protéger les données contre la destruction, la perte, l'altération, la divulgation ou l'accès non autorisés, notamment :

- chiffrement des communications (HTTPS/TLS) ;
- hachage des mots de passe ;
- contrôle des accès et habilitations ;
- journalisation et supervision ;
- sauvegardes quotidiennes stockées chiffrées au repos chez notre hébergeur européen (Cloudflare R2, Union européenne), avec une rétention de 14 jours.

En cas de **violation de données** présentant un risque pour les droits et libertés des personnes, l'Éditeur notifie la CNIL dans les **72 heures** et, le cas échéant, informe les personnes concernées, conformément aux articles 33 et 34 du RGPD.

## 10. Cookies et traceurs

Le Service utilise un **nombre minimal de cookies / traceurs**, strictement nécessaires à son fonctionnement :

- **Cookies techniques essentiels** : authentification, gestion de session, sécurité. Ces cookies sont **exemptés de consentement** car indispensables à la fourniture du Service expressément demandé par l'utilisateur.
- **Cookies de mesure d'audience / analytiques** : **non utilisés à ce jour**. En cas d'introduction d'un outil de mesure non strictement nécessaire, un mécanisme de recueil du consentement conforme aux recommandations de la CNIL sera mis en place et la présente Politique mise à jour.

À la date de rédaction, le Service **n'utilise pas de cookies publicitaires ni de traceurs tiers à des fins de profilage**. Toute évolution donnera lieu à la mise à jour de la présente Politique et, le cas échéant, à la mise en place d'un mécanisme de recueil du consentement conforme aux recommandations de la CNIL.

## 11. Décisions automatisées

Le scoring **Go/No-Go** repose sur un **barème déterministe** d'aide à la décision. Il fournit une **recommandation** ; il **ne produit pas de décision automatisée produisant des effets juridiques** au sens de l'article 22 du RGPD : la décision de répondre ou non à un marché, et la validation des documents, **relèvent toujours du jugement humain du Client**.

## 12. Modification de la Politique

La présente Politique peut être mise à jour à tout moment, notamment pour refléter des évolutions légales, techniques ou organisationnelles (par exemple la migration de l'hébergement vers l'UE). La version applicable est celle publiée sur le Service. Les modifications substantielles sont portées à la connaissance des utilisateurs par un moyen approprié.

## 13. Contact

Pour toute question relative à la présente Politique ou à la protection de vos données :

- **E-mail** : eviegas@padis-core.com
- **Adresse** : 9 rue Saint-Yves, 29000 Quimper, France
