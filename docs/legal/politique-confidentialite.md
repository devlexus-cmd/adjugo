# Politique de confidentialité

> ⚠️ **Avertissement** — Ce document est un **modèle** rédigé à titre informatif. Il doit être **relu et validé par un juriste / DPO** avant toute publication et complété avec les informations réelles de l'éditeur. Les champs marqués `[À COMPLÉTER : ...]` doivent être renseignés avant mise en ligne.

*Version : 1.0 — Dernière mise à jour : 15 juin 2026*

---

La présente Politique de confidentialité décrit la manière dont le service **Adjugo** collecte, utilise, conserve et protège les données à caractère personnel, conformément au **Règlement (UE) 2016/679 (RGPD)** et à la **loi « Informatique et Libertés » n° 78-17 du 6 janvier 1978 modifiée**.

## 1. Responsable du traitement

Le responsable du traitement des données collectées via le Service est :

- **Dénomination** : `[À COMPLÉTER : raison sociale de l'éditeur d'Adjugo]`
- **Adresse** : `[À COMPLÉTER : adresse postale]`
- **SIREN / SIRET** : `[À COMPLÉTER]`
- **Contact** : viegaseliot1@gmail.com

> **Précision sur les rôles.** Pour les données de gestion du compte et de facturation, l'Éditeur agit en qualité de **responsable de traitement**. Pour les données personnelles éventuellement contenues dans les **documents téléversés par le Client** (DCE, pièces d'entreprise, contacts de co-traitants), l'Éditeur agit pour l'essentiel en qualité de **sous-traitant** du Client (au sens de l'article 28 RGPD), le Client demeurant responsable de traitement de ces données. `[À COMPLÉTER : formaliser le cas échéant un accord de sous-traitance (DPA) dédié.]`

## 2. Délégué à la protection des données (DPO) / Contact

Pour toute question relative à vos données personnelles ou pour exercer vos droits :

- **E-mail** : viegaseliot1@gmail.com
- **DPO** : `[À COMPLÉTER : nom/coordonnées d'un DPO si désigné — la désignation n'est pas obligatoire pour toutes les structures mais recommandée ; à défaut, indiquer un point de contact « protection des données »]`
- **Adresse postale** : `[À COMPLÉTER]`

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

> Adjugo applique une **règle stricte de minimisation et d'anti-hallucination** : seules des données réelles et sourcées sont traitées ; aucune donnée personnelle n'est inventée. Le Service n'a pas vocation à collecter de **données sensibles** au sens de l'article 9 du RGPD ; le Client s'engage à ne pas téléverser de telles données sans base légale appropriée.

## 4. Finalités et bases légales

| Finalité | Base légale (art. 6 RGPD) |
|---|---|
| Création et gestion du compte, fourniture du Service | **Exécution du contrat** (art. 6.1.b) |
| Réalisation des analyses, sourcing, génération de documents (CERFA, DUME, mémoire) | **Exécution du contrat** (art. 6.1.b) |
| Vérification des co-traitants (SIRENE/BODACC, signaux de procédure collective) | **Exécution du contrat** + **intérêt légitime** (art. 6.1.f) |
| Facturation et gestion des paiements | **Exécution du contrat** + **obligation légale** (comptable/fiscale) (art. 6.1.c) |
| Sécurité, prévention de la fraude, journalisation technique | **Intérêt légitime** (art. 6.1.f) |
| Réponses aux demandes de support | **Exécution du contrat** / **intérêt légitime** |
| Communications commerciales (le cas échéant) | **Intérêt légitime** ou **consentement** selon le cas (prospection B2B) |
| Respect des obligations légales et réponses aux autorités | **Obligation légale** (art. 6.1.c) |

## 5. Durées de conservation

| Donnée | Durée de conservation |
|---|---|
| Données de compte | pendant la durée de la relation contractuelle, puis suppression ou anonymisation `[À COMPLÉTER : ex. 12 mois]` après la clôture du compte |
| Documents téléversés (DCE, pièces) | pendant la durée d'utilisation du Service, puis suppression `[À COMPLÉTER : ex. 30 à 90 jours]` après la clôture du compte ou sur demande |
| Données de facturation | **10 ans** (obligation comptable et fiscale, art. L.123-22 Code de commerce) |
| Journaux techniques (logs) | `[À COMPLÉTER : ex. 6 à 12 mois]` |
| Données de prospection | `[À COMPLÉTER : ex. 3 ans à compter du dernier contact]` |

À l'expiration de ces durées, les données sont supprimées ou anonymisées de manière irréversible.

## 6. Destinataires et sous-traitants

Les données sont traitées par les équipes habilitées de l'Éditeur et par les **sous-traitants / destinataires** suivants, sélectionnés pour leurs garanties de sécurité et liés par des engagements contractuels conformes à l'article 28 RGPD :

| Prestataire | Rôle | Données concernées | Localisation |
|---|---|---|---|
| **Railway Corporation** | Hébergement de l'infrastructure et de la base de données | l'ensemble des données du Service | **États-Unis** (région actuelle — voir art. 7) |
| **Anthropic** (Claude API) | Fournisseur du modèle d'IA pour l'analyse et la génération de documents | contenus soumis à l'analyse (extraits de DCE, données d'entreprise) | `[À COMPLÉTER : région d'appel API — US / UE]` |
| **Stripe** (Stripe Payments Europe, Ltd. / Stripe, Inc.) | Traitement des paiements | données de facturation et de paiement (l'Éditeur n'accède pas aux numéros de carte) | UE / États-Unis |
| **`[À COMPLÉTER : fournisseur SMTP/e-mail si configuré]`** | Envoi des e-mails transactionnels | adresse e-mail, contenu des notifications | `[À COMPLÉTER]` |
| **`[À COMPLÉTER : Sentry, si activé]`** | Observabilité / suivi des erreurs | journaux techniques, identifiants techniques | `[À COMPLÉTER]` |

> **Note** — Les e-mails transactionnels (SMTP) et l'observabilité (Sentry) ne sont pas activés à la date de rédaction. Ce tableau devra être mis à jour dès leur activation.

Les données peuvent également être communiquées aux **autorités administratives ou judiciaires** lorsque la loi l'exige.

Adjugo **ne vend pas** les données personnelles et ne les transmet pas à des tiers à des fins commerciales.

## 7. Transferts de données hors Union européenne

L'infrastructure d'hébergement (Railway) est **actuellement opérée dans une région États-Unis**, ce qui implique un transfert de données vers un pays tiers à l'Union européenne. Certains autres sous-traitants (notamment le fournisseur d'IA et le prestataire de paiement) peuvent également opérer des traitements hors UE.

Ces transferts sont encadrés par des **garanties appropriées** au sens du chapitre V du RGPD, notamment :

- la signature de **clauses contractuelles types** (CCT / SCC) adoptées par la Commission européenne ;
- le cas échéant, l'adhésion du prestataire au **EU-U.S. Data Privacy Framework** `[À COMPLÉTER : à vérifier pour chaque prestataire]` ;
- des mesures techniques et organisationnelles complémentaires (chiffrement, minimisation).

> **Engagement de migration UE.** L'Éditeur s'engage à **migrer l'hébergement vers une région Union européenne** afin de réduire les transferts hors UE, et, dans l'intervalle, à maintenir les garanties contractuelles ci-dessus. `[À COMPLÉTER : échéance cible de migration.]` La présente Politique sera mise à jour à l'issue de la migration.

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

**Exercice des droits.** Vous pouvez exercer ces droits en écrivant à **viegaseliot1@gmail.com**. Une preuve d'identité pourra être demandée. Une réponse vous sera apportée dans un délai d'**un (1) mois** (prorogeable de deux mois en cas de complexité).

> **Cas des documents téléversés.** Lorsqu'une demande porte sur des données personnelles contenues dans des documents téléversés par un Client (Adjugo agissant alors comme sous-traitant), la demande est, le cas échéant, transmise au Client responsable de traitement, ou traitée selon ses instructions.

**Réclamation.** Vous disposez du droit d'introduire une réclamation auprès de la **CNIL** (Commission Nationale de l'Informatique et des Libertés), 3 place de Fontenoy, TSA 80715, 75334 Paris Cedex 07 — www.cnil.fr.

## 9. Sécurité

L'Éditeur met en œuvre des mesures techniques et organisationnelles appropriées pour protéger les données contre la destruction, la perte, l'altération, la divulgation ou l'accès non autorisés, notamment :

- chiffrement des communications (HTTPS/TLS) ;
- hachage des mots de passe ;
- contrôle des accès et habilitations ;
- journalisation et supervision ;
- sauvegardes régulières `[À COMPLÉTER : préciser fréquence et politique de sauvegarde]`.

En cas de **violation de données** présentant un risque pour les droits et libertés des personnes, l'Éditeur notifie la CNIL dans les **72 heures** et, le cas échéant, informe les personnes concernées, conformément aux articles 33 et 34 du RGPD.

## 10. Cookies et traceurs

Le Service utilise un **nombre minimal de cookies / traceurs**, strictement nécessaires à son fonctionnement :

- **Cookies techniques essentiels** : authentification, gestion de session, sécurité. Ces cookies sont **exemptés de consentement** car indispensables à la fourniture du Service expressément demandé par l'utilisateur.
- **Cookies de mesure d'audience / analytiques** : `[À COMPLÉTER : indiquer si utilisés ; s'ils ne sont pas strictement nécessaires, un recueil du consentement via bandeau cookies est requis]`.

À la date de rédaction, le Service **n'utilise pas de cookies publicitaires ni de traceurs tiers à des fins de profilage**. Toute évolution donnera lieu à la mise à jour de la présente Politique et, le cas échéant, à la mise en place d'un mécanisme de recueil du consentement conforme aux recommandations de la CNIL.

## 11. Décisions automatisées

Le scoring **Go/No-Go** repose sur un **barème déterministe** d'aide à la décision. Il fournit une **recommandation** ; il **ne produit pas de décision automatisée produisant des effets juridiques** au sens de l'article 22 du RGPD : la décision de répondre ou non à un marché, et la validation des documents, **relèvent toujours du jugement humain du Client**.

## 12. Modification de la Politique

La présente Politique peut être mise à jour à tout moment, notamment pour refléter des évolutions légales, techniques ou organisationnelles (par exemple la migration de l'hébergement vers l'UE). La version applicable est celle publiée sur le Service. Les modifications substantielles sont portées à la connaissance des utilisateurs par un moyen approprié.

## 13. Contact

Pour toute question relative à la présente Politique ou à la protection de vos données :

- **E-mail** : viegaseliot1@gmail.com
- **Adresse** : `[À COMPLÉTER : adresse postale de l'éditeur]`

---

*Document généré comme modèle. À faire valider par un juriste / DPO avant publication.*
