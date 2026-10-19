# Réorganisation de l'interface : vagues 0 et 1, le socle

Contrat du socle posé avant de ranger le menu et la page du marché. Étude : « Réorganiser l'interface d'Adjugo :
étude définitive » (12/10/2026), § 1, 5.3, 7, 8, 9, 10 et 11. Base : `feat/produit-acheteur-collectivites` =
`88a4109` (production du 19/10/2026).

Décisions appliquées (recommandations de l'étude, validées par Eliot) : D0 (a), D1 C corrigée, D2 (a), D3
« Partenaires », D6 4 étapes, D8 (a), D9 (a), D16 (a), D17 (mesure). D4 (a) et D5 (a) étaient déjà en production.

Ce socle fait : la vague 0 restante (§ 0), les repères de test (§ 1.0), la mesure d'usage (§ 1.1) et l'inscription
directe depuis l'essai (§ 1.2). Le chantier « page du marché et recherche » fait 1.4 et 1.5 (§ 1.4, § 1.5) ; le menu
et l'accueil sont rangés par un autre chantier (§ 3).

Tests : `tests/test_reorganisation_v1_socle.py` (repères, mesure, inscription, vague 0, traductions),
`tests/test_reorganisation_v1_marche.py` (page du marché en 4 étapes, recherche, décision 8, démonstration),
`tests/zones.py` (découpage par repère), `tests/textes_visibles.py` (textes lus par une personne).

---

## 0. Vague 0 « dire juste »

### 0.1 Le tableau du § 9 de l'étude, ligne par ligne

| Ligne de l'étude | État |
|---|---|
| Page du marché : DC4 = déclaration de sous-traitance | Déjà fait (correctifs urgents `da9ef0f`) : « un sous-traitant se déclare avec le DC4 », « Ajouter un sous-traitant (DC4) » |
| « Estimation détaillée (PDF) » | Déjà fait (`da9ef0f`) |
| Bulle « Aucune invention » | Déjà retirée (`da9ef0f`) |
| Bulle « Dépôt du dossier » | **Fait ici** : la bulle de « parts reçues » renvoyait à une carte « Dépôt du dossier » qui n'existe pas ; elle dit seulement ce que compte le chiffre |
| Aide au dépôt : Chorus Pro retiré | Déjà fait (`da9ef0f`) : aucun « Chorus » dans l'application, la vitrine ni l'espace partenaire |
| Bandeau cookies vers `/confidentialite` | **Fait ici** : le lien menait à `/legal/politique-confidentialite.html`, qui ne répond pas ; il mène à `/confidentialite` (nouvel onglet, `rel="noopener"`) |
| « co-traitants » → « partenaires » (notifications, bulles des rôles) | **Fait ici** : « Aucune activité récente de vos partenaires. », « Partenaire du groupement : il en est membre et signe l'offre… » (profil réseau et fenêtre d'invitation) |
| Libellé « Envoyé » → « Déposé », sans toucher à la clé | **Fait ici** : `statusLabel` affiche « Déposé » pour la clé `envoye` (inchangée en base et dans l'API) ; « Envoyé » reste pour un devis ou une facture (`invStatusLabel`) |
| Accents des pièces (`checklist.py`) | Déjà fait |
| Cartes d'offre : « rédaction IA sourcée », « partenaires vérifiés » | Déjà fait (`da9ef0f`) |
| Cartes d'offre : « CERFA, DUME » | **Fait ici** : « Formulaires officiels pré-remplis, à relire (DC1, DC2, DUME) » (application et vitrine) : c'est ce qu'Adjugo produit (`app/routers/cerfa.py`) |
| Libellé de l'offre Business | Non touché : attend la décision 14 |
| Vitrine : « GO ou NO-GO », « co-traitant vérifié », « co-traitants fiables… en un clic », « 0 donnée jamais inventée » | Déjà fait (`da9ef0f`) |
| Vitrine : « Mistral » | Gardé : Mistral est le fournisseur actif de la lecture des dossiers depuis le 12/10/2026 (`MISTRAL_ACTIF=1`), la phrase est juste |
| Vitrine : autres mots bannis | **Fait ici** : « Co-traitance — votre différence » → « À plusieurs — votre différence » ; « (DC1, DC2, DUME, ATTRI1, mémoire) » → formulaires officiels et dossier de présentation ; pied de page « SIRENE » → « Registre des entreprises » |
| Espace partenaire : « Espace co-traitant », « CRM », « Co-traitant », « Invité » | **Fait ici** : « Espace partenaire » (titre et marque), groupe « Partenaires », avatar « Partenaire », rôle « Partenaire invité » ou « Sous-traitant invité » (« · lecture seule » si besoin) |
| Espace partenaire : « gratuit » → « essai de 30 jours » | Déjà fait (`da9ef0f`) : « essai gratuit de 30 jours » partout |
| Espace partenaire : « Ma DPGF de lot » → « Mon tableau de prix » | **Fait ici**, côté lien (`invite.html`) et côté compte (« Partagé avec moi ») ; bulles, boutons, pastilles (« Déposé », « Pas encore déposé ») et messages du dépôt ; le test qui l'exigeait suit (`test_cotraitance_v4_ecrans.py`) |
| Courriels : « Invitation à co-traiter » | **Fait ici** : « Invitation à répondre ensemble à un marché — [marché] » |
| Courriels : « cockpit du groupement » | **Fait ici** (part soumise, invitation déclinée, attestations des partenaires) : « Ouvrez ce marché dans Adjugo… », « depuis la page de ce marché » ; « Partenaires prêts : 2 sur 3 » (décision 8) |
| Courriels : « fiche du marché » | **Fait ici** (convention validée par tous) : « sur la page du marché, dans Adjugo » ; aussi deux messages à l'écran |
| Serveur : commentaire périmé de `auth.py` | **Fait ici** : il décrit le choix du 24/06 (écran plein « Confirmez votre adresse email », refus serveur des actions coûteuses) |

### 0.2 Les autres mots bannis visibles

Mots bannis (critère de fin de la vague 1) : co-traitant, consortium, AO, mémoire, Maîtres d'ouvrage, agent, Cockpit,
DPGF, CERFA, SIRENE, GO/NO-GO. Remplacements (glossaire de l'étude, § 8) :

| Mot | Devient |
|---|---|
| co-traitant(s), co-traitance, co-traiter | partenaire(s), partenaire du groupement, à plusieurs, groupement |
| AO | marché (« Supprimer ce marché », « Marché lié (facultatif) », « Analyser ce marché », « nouveaux marchés trouvés », « marché attendu ») |
| mémoire (technique) | dossier de présentation ; sa définition en bulle : « la partie technique de votre offre que demande le règlement de la consultation : vos moyens, votre méthode, votre organisation » |
| Maîtres d'ouvrage | clients |
| agent (IA) | retiré : la vue « agent » de juin n'existait plus, ses définitions et ses titres sont supprimés |
| Cockpit (du groupement) | Suivi du groupement |
| DPGF | tableau de prix (clé `dpgf_lot` inchangée) |
| CERFA | formulaires officiels (DC1, DC2…) |
| SIRENE | registre officiel (des entreprises), avec « Insee » quand on nomme la source |

Où : `app.html`, `app.js`, `invite.html`, `landing.html`, `redaction-partenaire.js`, `cotraitance-crypto.js` ; côté
serveur, les textes montrés : liste des pièces (`checklist.py`), messages d'erreur (partenaires, registre, dépôt du
tableau de prix, groupement, réseau), libellés et provenances du réseau (`partner_matching.py`,
`partner_network.py`, `reseau.py`, `groupement_verdict.py`, `scoring.py`), contenu des exports (fiche récapitulative,
liste du dossier de groupement, estimation PDF), refus de la démonstration (`demo_guard.py`), et les textes « à la voix
d'Adjugo » de la démonstration (analyse, points d'attention, leviers).

Liste des pièces : « Dossier de présentation » et « Tableau de prix (bordereau ou décomposition des prix) ». Un
champ `alias` (jamais affiché) garde les noms que le règlement donne à ces pièces (« DPGF », « BPU », « mémoire
technique »…) pour qu'une pièce lue dans le dossier du marché ne s'ajoute pas en double.

Vérification : `test_aucun_mot_banni_dans_les_textes_visibles_du_front` (pages et scripts lus par un client) et
`test_aucun_mot_banni_dans_les_courriels_ni_les_messages_d_erreur` (toutes les fonctions qui envoient un courriel,
tous les messages `HTTPException`).

### 0.3 Ce qui garde un mot banni, et pourquoi

| Texte | Raison |
|---|---|
| Clés, noms de champs, routes (`cotraitant`, `dpgf_lot`, `consortium`, `/api/projects/{id}/consortium`…) | Non visibles ; l'étude demande de les garder |
| Pages juridiques (CGV, confidentialité, DPA, mentions, sécurité) | Non modifiées : relevé et propositions pour Eliot dans `docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 6 |
| Modèle de convention de groupement (« co-traitant (partenaire) ») | Texte juridique figé par empreinte ; même fichier, § 6.4 |
| Pièces du dossier FICTIF de l'acheteur dans la démo (règlement, cadre « mémoire technique », CCTP), noms des pièces exigées, documents de l'entreprise fictive | Ce sont les mots de l'acheteur et les fichiers de l'entreprise, pas le texte du produit |
| Nom que le règlement donne à la pièce (« Dossier de présentation (mémoire justificatif) ») et nom par défaut du fichier exporté (« Mémoire technique ») | Le fichier est remis à l'acheteur : il porte son vocabulaire |
| En-tête « DPGF du lot - prix de vente HT » et nom `DPGF_…csv` du fichier du partenaire | Même raison (fichier remis au chef de file puis à l'acheteur) |
| Question à l'acheteur « deux limites différentes pour le mémoire » (`grille_exigences.py`) | Texte adressé à l'acheteur ; son titre à l'écran est « Longueur du dossier de présentation » |
| Dossier rangé « Mémoire technique » (clé interne ; `folderLabel` affiche « Dossier de présentation ») ; dossier `cerfa/` du ZIP | Clés de rangement, non renommées pour ne rien casser chez les clients |
| « agent de sécurité » (`app/sourcing/groupement.py`) | Un métier, pas un agent d'IA |
| Pages « collectivités » (`acheteur*.html`, « SIRENE », « agents ») | Face acheteur : leur public dit « SIRENE » et « agents » (de la collectivité) ; hors du critère PME |
| Routeur archivé `cospace.py` | Jamais monté (`app/main.py`) |
| Commentaires, docstrings, journaux, consignes de l'IA | Jamais lus par un client |

Les exceptions exactes sont dans `EXCEPTIONS` (`tests/test_reorganisation_v1_socle.py`) : toute nouvelle exception
s'y justifie et s'ajoute ici.

### 0.4 « Vérifié » (décision 9)

« vérifié » reste seulement pour une identité contrôlée dans un registre, avec sa date (« vérifié au registre
officiel le 08/10 », « Vérifié le … » des badges du réseau, adresse email vérifiée par un code). Retirés :
« partenaires vérifiés » (sous-titre du Réseau), « vérifié via VIES » (« contrôlé dans le registre européen VIES »).
La vérification du journal par un membre (« Vérifié le … ») garde son mot : c'est un contrôle qu'il lance, daté.

### 0.5 Traductions (décision 16)

Le dictionnaire `app/static/i18n.js` est indexé sur le texte français exact. Chaque libellé renommé reçoit son
néerlandais et son espagnol ; les libellés du menu actuel qui n'en avaient pas aussi ; et les libellés de
l'architecture C corrigée sont traduits d'avance (Accueil, Partenaires, Réglages, Réseau Adjugo, Collègues, Mon
compte, Courriels, Mes alertes, Publiés, À venir, Où je suis partenaire, À plusieurs, Ce que je cherche, Identité,
Tarifs, Mes pièces, Lire, Décider, Préparer, Déposer, Inviter un partenaire, Préparer seul, Préparer à plusieurs,
Écarter, Qui me complète ?, Prêt à déposer). 302 → 357 clés. Les anciennes clés restent (un ancien libellé peut
encore s'afficher ailleurs).

Outil : `python scripts/i18n_ajouter.py ajouts.json` (`{"Libellé": {"nl": "…", "es": "…"}}`), puis `--check`,
puis `python scripts/sri_update.py`. Test : `test_traductions_des_libelles_renommes_et_du_menu` (chaque libellé
renommé de `RENOMMES` et chaque entrée du menu ont les deux langues).

---

## 1.0 Les repères de test

### 1.0.1 Le principe

Chaque zone de `app.html` porte un attribut `data-test="nom"` sur son élément racine. Les tests la découpent avec
`tests/zones.py` :

- `zone(HTML, "nom")` : l'élément entier, de sa balise ouvrante à sa balise fermante (balises de même nom comptées,
  commentaires ignorés). Échoue si le repère manque ou s'il est posé deux fois ;
- `zones(HTML, "nom")` : toutes les zones d'une famille (même nom sur des fenêtres sœurs) ;
- `sans_reperes(texte)` : le texte sans les attributs `data-test`, pour un test qui compare une balise exacte ;
- `noms(HTML)` : les repères posés.

Une zone se trouve où qu'elle soit : réordonner la page, déplacer une carte sous une autre étape ou renommer un
libellé ne casse plus les tests. Les attributs `data-test` ne changent rien à l'affichage (le gabarit compile sans
avertissement, `test_gabarit_compile_par_le_vue_du_depot`).

Réécrits : `test_reseau_ecrans.py`, `test_reseau_ecrans_v34.py`, `test_redaction_v2_ecrans.py`,
`test_redaction_v4_chef_de_file.py`, `test_redaction_v3_mes_preuves_ecrans.py`, `test_redaction_v3_import.py`,
`test_redaction_v5_entretien.py`, `test_redaction_vague1_ensemble.py`, `test_correctifs_urgents.py`,
`test_coffre_a_fournir.py`, `test_essai_garde_fou.py`, `test_lecture_integrale.py`,
`test_redaction_v6_preparation.py`, `test_redaction_v4_partenaire.py`, `test_redaction_v6_carnet.py`,
`test_corrections_v34_b.py` (pastille « Tableau de prix reçu » dans `marche-suivi-groupement`). Garde-fou :
`test_aucun_test_ne_decoupe_plus_app_html_entre_deux_commentaires`.

`test_cotraitance_v4_ecrans.py` ne découpait pas `app.html` : seul son libellé « Ma DPGF de lot » change (§ 0).

### 1.0.2 Règles de nommage

1. **Minuscules, sans accent, mots reliés par un tiret** : `[a-z0-9]+(-[a-z0-9]+)*`.
2. **Le nom dit ce qu'est la zone, jamais son libellé** : le libellé change (« Cockpit » est devenu « Suivi du
   groupement »), le repère reste. Un repère n'est jamais traduit ni affiché.
3. **Une vue = `vue-<clé>`**, la clé de `view` dans `app.js` (`vue-dashboard`, `vue-aodetail`…), même si la vue est
   renommée à l'écran.
4. **Un préfixe par endroit** : `accueil-`, `marche-` (page du marché), `plusieurs-` (dans « Répondre à
   plusieurs ? »), `convention-` (dans « Convention et accords » ; aucun depuis que « Prêt à déposer » en est
   sorti), `pieces-`, `trouver-`, `atelier-`, `kb-`, `reseau-`, `partage-` (le dossier
   partagé, côté partenaire), `billing-`, `admin-`, `carte-` (au-dessus de toutes les vues), `fenetre-` (une
   fenêtre), `fenetres-` (famille de fenêtres sœurs), `ecran-`, `bandeau-`.
5. **Un repère est unique**, sauf une famille déclarée (`fenetres-atelier` ×5, `fenetres-preuves` ×2).
6. **Sur l'élément racine réel** de la zone ; sur un `<template>` seulement quand rien ne l'enveloppe (onglets du
   Réseau). Sur un `<template>`, l'attribut sert aux tests et n'arrive pas dans la page.
7. **Déplacer une zone, c'est déplacer son élément avec son repère.** Couper une zone : l'ancien nom reste sur la
   partie qui garde la fonction, la nouvelle reçoit un nom. Fusionner : le nom de la zone qui reste.
8. **Tout repère ajouté, renommé ou retiré** se reporte dans ce contrat (§ 1.0.3) ET dans `ZONES`
   (`tests/test_reorganisation_v1_socle.py`), qui échoue sinon.
9. **Aucun test ne découpe `app.html` entre deux commentaires ni entre deux libellés.** Les découpages de `app.js` et
   de `styles.css` par commentaire restent (ces fichiers ne sont pas réordonnés) : ne pas renommer leurs
   commentaires de section (« // ══════════ Réseau de partenaires… », « /* ══════════ Atelier du dossier… »).

### 1.0.3 Les zones de `app.html`

**Cadre**

| Repère | Zone |
|---|---|
| `auth` | Connexion, inscription, mot de passe oublié |
| `menu` | Barre latérale (marque, entrées, « Plus », Mon avis, thème, compte) |
| `entete` | Barre du haut (titre et sous-titre de la vue, notifications, boutons de la vue) |
| `contenu` | Toutes les vues |
| `carte-essai` | Carte de l'essai (forfait, limite d'usage) |
| `carte-suggestion-reseau` | Suggestion « publiez votre profil partenaire » |
| `bandeau-cookies` | Bandeau du stockage local |
| `ecran-confirmation-email` | Écran plein « Confirmez votre adresse email » |

**Accueil (`vue-dashboard`)**

| Repère | Zone |
|---|---|
| `accueil-premiers-pas` | Premiers pas (3 étapes) |
| `accueil-ruban` | Ruban des 4 chiffres |
| `accueil-reseau` | Bloc « Réseau Adjugo — gagnez les gros marchés à plusieurs » (groupements par étape) |
| `accueil-amont` | « Une longueur d'avance » (masqué, `PROJETS_A_VENIR=0`) |
| `accueil-grille` | Grille : flux, rail, bilan, carnet |
| `accueil-flux` | « Vos appels d'offres » (7 derniers marchés) |
| `accueil-rail` | Raccourcis, pièces à renouveler, entonnoir « Mes marchés » |
| `accueil-bilan` | « Où vous gagnez / perdez » |
| `accueil-carnet` | Carnet de notes (« Où vous perdez des points ») |

**Page du marché (`vue-aodetail`)** — rangée en 4 étapes (§ 1.5)

| Repère | Zone |
|---|---|
| `marche-entete` | Titre, client (il mène à `marche-client`), étape, le couple « Seul X % · À plusieurs Y % » ; contient `marche-inviter` (le bouton « Inviter un partenaire », avant les 4 chiffres), `marche-inviter-formulaire` (et le lien à copier), les 4 chiffres, `marche-resultat` (bilan gagné / perdu) et `marche-carnet` |
| `marche-etapes` | La barre d'ancres Lire · Décider · Préparer · Déposer (`<nav>`, 4 boutons) |
| `marche-lire` | Étape Lire : `marche-analyse` (contient `marche-couverture` et `marche-questions`), `marche-grille`, `marche-dossier-fichiers`, `marche-client` |
| `marche-decider` | Étape Décider : `marche-plusieurs` (« Répondre à plusieurs ? », le seul « Répartir entre partenaires » et sa composition suggérée ; contient `plusieurs-manques` et `plusieurs-simulation`), `marche-qui-me-complete` (« Qui me complète ? ») |
| `marche-preparer` | Étape Préparer : `marche-prix`, `marche-dossier-presentation`, `marche-pieces` (`pieces-documents-reponse`, `pieces-a-fournir`) ; puis « À plusieurs » : `marche-taches-plusieurs`, `marche-reseau`, `marche-partenaires`, `marche-convention` |
| `marche-taches-plusieurs` | Les tâches à plusieurs (partenaires invités, parts reçues, convention et accords, offre commune), chacune avec « Voir » |
| `marche-reseau` | « Partenaires invités » ; contient `marche-preparation` (parts reçues, « N sur M »), `marche-commande-groupement` (relancer, assembler), `marche-invitations` (liste), `marche-contributions` (« Parts reçues »), `marche-suivi-groupement` (ex-« Cockpit ») avec `marche-coffre-croise` et `marche-offre-commune` |
| `marche-partenaires` | « Membres et sous-traitants » : les entreprises de vos formulaires officiels, sous-traitant DC4, « Chercher une entreprise » |
| `marche-convention` | « Convention et accords » (forme, pouvoirs, règles, génération, accords) |
| `marche-deposer` | Étape Déposer : `marche-pret-a-deposer` (groupement seulement), `marche-avant-depot`, `marche-export` |
| `marche-pret-a-deposer` | « Prêt à déposer » / « Avant de déposer » (4 contrôles, « Marquer déposé ») ; ex-`convention-pret-a-deposer`, sorti de la convention |
| `marche-avant-depot` | « Avant de déposer sur la plateforme du client » (4 cases, gardées sur l'appareil), ex-liste de « Mes documents de réponse » |
| `marche-export` | « Exporter le dossier complet (ZIP) » (masqué quand « Prêt à déposer » le porte déjà) |
| `marche-pied` | Pied de page replié (`<details>`) : `marche-devis-suivi`, le journal d'accès (`marche-journal-acces`, avec son bouton), `marche-actions` (« Supprimer ce marché ») |
| `marche-prix` | « Estimation du prix » |
| `marche-dossier-presentation` | Carte « Dossier de présentation » (ouvre l'atelier) |
| `marche-pieces` | Deux colonnes : `pieces-documents-reponse` (formulaires officiels, documents générés) et `pieces-a-fournir` (« N sur M ») |
| `marche-client` | « Votre client » (historique de publication) |
| `marche-devis-suivi` | Devis et factures liés, suivi du dossier |
| `marche-dossier-fichiers` | « Dossier du marché » (pièces classées) |
| `marche-actions` | « Supprimer ce marché » (l'export est passé dans `marche-export`) |

**Trouver des marchés (`vue-sourcing`)**

| Repère | Zone |
|---|---|
| `trouver-recherche` | La recherche (« Rechercher des marchés ») |
| `trouver-radar` | Radar des échéances (fins de contrat) |
| `trouver-alertes` | Alertes automatiques |
| `trouver-carte` | Une carte de résultat (élément répété par `v-for`) |
| `trouver-analyse` | L'analyse d'un marché trouvé : « Ouvrir le marché » juste après son résumé (§ 1.4) |

**Autres vues**

| Repère | Zone |
|---|---|
| `vue-amont` | Projets à venir (masqué) |
| `vue-kb` | Mon savoir-faire ; contient `kb-fiches-proposees` |
| `vue-atelier` | Atelier du dossier de présentation ; contient `atelier-page-preparation-case`, `atelier-page-preparation`, `atelier-entretien`, `atelier-onglets`, `atelier-repartition` (« Qui écrit quoi ») |
| `vue-pipeline`, `vue-cotraitants`, `vue-contacts`, `vue-documents`, `vue-invoices`, `vue-company`, `vue-preuves`, `vue-criteria`, `vue-team` | Une vue chacune (Mes marchés, Mes partenaires, Contacts, Mes documents, Devis et factures, Mon entreprise, Mes preuves, Mes critères, Équipe) |
| `vue-billing` | Abonnement ; contient `billing-offres` (les cartes d'offre) |
| `vue-admin` | Administration ; contient `admin-mesure` (écrans ouverts, § 1.1) |
| `vue-consortiums` | Mes groupements |
| `vue-reseau` | Réseau ; contient `reseau-onglets`, `reseau-profil`, `reseau-annuaire`, `reseau-historique`, `reseau-recues` |
| `vue-shared` | Partagé avec moi (liste) |
| `vue-sharedao-attente` | Dossier partagé en chargement ou en erreur |
| `vue-sharedao` | Un dossier partagé, côté partenaire ; contient `partage-entete`, `partage-grille`, `partage-pourquoi`, `partage-convention`, `partage-redaction`, `partage-pieces`, `partage-ma-part` (avec `partage-tableau-prix` et `partage-coffre-croise`), `partage-journal` |

**Fenêtres**

| Repère | Zone |
|---|---|
| `fenetres-atelier` (×5) | Fenêtres de l'atelier (dérogation, débit, vue, lots, plan) |
| `tiroir-projet` | Tiroir d'un marché |
| `fenetre-siret` | Activation par SIRET (1er lancement) |
| `fenetre-confirmation` | Confirmation d'une action de la convention |
| `fenetre-fiche-partenaire` | Fiche d'un partenaire du réseau |
| `fenetre-invitation` | Invitation en un clic (réseau ou registre) |
| `fenetre-formulaire` | Fenêtre générique (formulaires) |
| `fenetres-preuves` (×2) | Fenêtres de Mes preuves |
| `fenetre-decouverte` | Découvrir des partenaires réels |
| `fenetre-avis` | « Mon avis » |

---

## 1.1 La mesure d'usage (décision 17)

- **Un événement par ouverture d'écran** : `go(v)` appelle `_ecranOuvert(v)`, comme les ouvertures hors de `go()`
  (un marché, un dossier partagé, l'atelier, les retours). Appel sans attente (`fetch` dont on n'attend pas la réponse), sans barre
  de progression ni message : une mesure perdue ne gêne jamais l'écran.
- **Route** : `POST /api/mesure/ecran` `{"ecran": "<clé de view>"}` → 204, sans corps. Session exigée (401 sans) mais
  jamais enregistrée. 600 par heure. Un écran hors de la liste fermée `ECRANS` (`app/services/mesure_usage.py`) est
  ignoré, sans erreur ; la démonstration n'est pas comptée.
- **Ce qui est gardé** : table `mesure_ecrans` (jour, écran, ouvertures), clé primaire (jour, écran), jour de Paris.
  **Rien d'autre** : ni compte, ni organisation, ni adresse IP, ni appareil, ni heure. Aucun outil tiers, aucun
  cookie. Le bandeau cookies (« le cas échéant, une mesure d'audience anonyme ») reste juste.
- **Lecture, administrateur de la plateforme seulement** : `GET /api/admin/mesures/ecrans?jours=30` (1 à 400). Chaque
  écran de la liste apparaît, même à 0. Carte « Écrans ouverts, 30 derniers jours » dans Administration
  (`admin-mesure`). Jamais montré aux clients.
- **Migration** `b3mesureecrans` (après `a2carnetnotes`) : crée la table si elle manque, idempotente, retour arrière
  réel. Testée sur SQLite (`test_migration_mesure_ecrans_aller_retour_idempotente`) et sur Postgres 16 (15 contrôles
  verts, script `scratchpad/socle/run_pg_mesure.py` de la session) : base neuve ; base montée par le code de
  production `88a4109` puis code nouveau (une seule table ajoutée, données intactes, rejeu sans effet) ; compteur et
  relevé sur Postgres ; table identique au modèle ; retour arrière et remontée. Reste à refaire au moment de la mise
  en ligne depuis l'état réel de la production, comme pour chaque migration.
- **Route classée** dans `tests/test_demo_sans_cout.py` (sans coût, la démo n'est pas comptée).
- **Toute nouvelle vue** (un onglet de rubrique devenu vue, par exemple) s'ajoute à `ECRANS` :
  `test_chaque_vue_de_l_application_est_mesuree` le vérifie contre `app.html` et `app.js`. Les onglets internes d'une
  vue (onglets du Réseau) ne sont pas comptés à part.

La vague 1 se voulait sans migration (« aucune donnée modifiée ») : celle-ci ajoute une table de compteurs, sans
toucher aux données des clients. C'est le seul moyen de garder un compte par jour d'un redémarrage à l'autre sans
outil tiers.

## 1.2 L'essai mène à l'inscription

- `/app?inscription` ouvre « Créons votre compte » (`auth.mode = "register"`). Déjà connecté, ou lien de
  réinitialisation : rien ne change. Le paramètre est retiré de l'adresse ; les autres (`?shared=`, `?verify=`,
  `#gcode=`) restent tels quels. Fonction pure `inscriptionDemandee(location)` (`app.js`) ; dans `mounted()`, le
  paramètre est retiré tout de suite et le formulaire choisi **après** la relecture de la session stockée : une
  session périmée (verrou d'inactivité) est effacée, et l'on arrive bien sur l'inscription (trouvé dans un vrai
  navigateur : le premier essai montrait « Content de vous revoir »).
- Y mènent : les 4 « Démarrer l'essai gratuit » de la vitrine ; dans l'espace partenaire, « Créer mon compte
  Adjugo », « Commencer mon essai gratuit de 30 jours » et « Commencez votre essai gratuit de 30 jours ». Les liens
  « Se connecter » et « Me connecter » restent sur `/app`.
- Test : `inscriptionDemandee` exécutée sous Node sur 5 adresses, et l'ordre du branchement dans `mounted()`
  (`test_inscription_lue_par_l_application_sous_node`).

## 1.4 De la recherche au marché

- **Déjà fait** (correctifs urgents `da9ef0f`, vérifié) : plus d'étapes 3 et 4 dans la recherche, plus de « Rattacher » ;
  « Ouvrir le marché » et « Inviter un partenaire » terminent l'analyse ; « Ajouter un sous-traitant (DC4) » pour ce seul
  cas.
- **Fait ici** :
  - « Ouvrir le marché » (et « Inviter un partenaire ») vient juste après le résumé et la lecture du dossier, avant le
    détail du score et des clauses : il suivait toute l'analyse, une page plus bas ;
  - l'analyse s'affiche sous les résultats : après « Analyser ce marché », l'écran y mène (`rnScrollTo("srcAnalyse")`) ;
    avant, rien ne semblait se passer ;
  - un marché s'ouvre en haut de sa page (`openAo` remet le défilement à zéro, comme `go()`) : depuis une recherche
    défilée, il s'ouvrait au milieu ;
  - plus d'« Étape 1 / Étape 2 » dans la recherche (les étapes de la réponse vivent sur la page du marché) :
    « Rechercher des marchés », « Analyse du marché » ;
  - décision 8 sur l'analyse : « Seul » à côté du cadran (« 87 % »), « À plusieurs Y % », « Pourquoi ce score ? » en
    « N sur M » ; « Client non précisé » sur une carte de résultat.
- **Laissé, avec sa raison** : « confiance X% » et « adéquation N/100 » des cartes de résultat → des mots (étude, § 8 :
  Moteur V0) ; « pertinence N/100 » du radar (chantier 1.3 puis Veille V1).

## 1.5 La page du marché en 4 étapes

On **déplace** les cartes, la logique ne change pas (mêmes appels, mêmes données). Ordre de la page :

1. **En tête** : titre, client (cliquable, il mène à « Votre client »), étape, le couple « Seul X % · À plusieurs Y % » ;
   **« Inviter un partenaire »** (`user-plus`), le seul bouton pleine largeur de la page, avant les 4 chiffres (sur
   téléphone, ils s'empilent et repoussaient le bouton sous la ligne de flottaison), à toutes les étapes
   (décision 0) ; son formulaire s'ouvre juste dessous. « Inviter {nom} », la recherche, la carte « Partenaires
   invités » vide y mènent (`aoInviter`, `rnScrollTo("inviteForm")`). Le bilan d'un marché gagné ou perdu et son carnet
   de notes restent en tête : c'est l'étape du moment.
2. **La barre** Lire · Décider · Préparer · Déposer (décision 6) : 4 ancres, sans blocage ; l'étape en cours est
   surlignée (`etapeDuMarche`, fonction pure : statut, dossier lu, étape du groupement ; aucune pour un marché gagné,
   perdu ou abandonné). Elle **remplace sur cette page les étapes 1 à 5 du groupement** (les deux steppers sont
   retirés) ; côté partenaire, le stepper reste jusqu'à la vague 2b.
3. **Lire** : l'analyse du dossier (questions à l'IA comprises), « Comment vous serez noté », le dossier du marché,
   votre client.
4. **Décider** : « Répondre à plusieurs ? » (le couple, les manques cités du règlement, « Qui l'a ? », la simulation),
   puis « Qui me complète ? ». **Un seul « Répartir entre partenaires »**, dans cette carte, avec sa composition
   suggérée (il était aussi dans « Partenaires sur ce marché »). Sans analyse : une phrase dit quoi faire.
5. **Préparer** : le prix d'abord (**le prix est une tâche de Préparer**), le dossier de présentation, les formulaires
   officiels et les pièces ; puis **« À plusieurs »** : les tâches (`tachesPlusieurs`, fonction pure : des faits lus
   dans l'état du serveur — partenaires invités, parts reçues avec leur prix, convention et accords, offre figée ;
   trois statuts : Pas commencé · En cours · Terminé ; visibles dès l'étape 2 du groupement), « Partenaires invités »,
   « Membres et sous-traitants », « Convention et accords ».
6. **Déposer** : **« Prêt à déposer » sort de la carte de la convention** mais **reste réservé au groupement**
   (`depotShown()` exige un groupement : `depot_readiness` ne vérifie que des points de groupement et signalerait de
   faux manques à une entreprise seule) ; la liste « Avant de déposer sur la plateforme du client », pour tous (elle
   n'apparaissait qu'après « Préparer mes documents », dans la même visite) ; « Exporter le dossier complet (ZIP) ».
7. **Pied de page, replié** : devis et factures liés, suivi du dossier, journal d'accès (son bouton a quitté la carte
   des partenaires), « Supprimer ce marché ».

**Cartes renommées** (étude, § 8)

| Avant | Après | Icône |
|---|---|---|
| Partenaires pour ce marché (bouton « Qui me complète ? ») | Qui me complète ? (bouton « Chercher des partenaires ») | `puzzle` |
| Réseau Adjugo — montez le dossier à plusieurs | Partenaires invités | `handshake` |
| Partenaires sur ce marché | Membres et sous-traitants (les entreprises de vos formulaires officiels) | `handshake` |
| Monter le groupement | Convention et accords | `scroll-text` (au lieu de `file-signature`) |
| Répondre à plusieurs ? | inchangé | `scale` (au lieu de `users-round`) |
| Votre client (l'acheteur) | Votre client (« acheteur » en bulle) | inchangée |
| Contributions, Contribution reçue | Parts reçues, Part reçue | inchangées |
| Inviter un partenaire sur ce marché | Inviter un partenaire | `user-plus` |
| « les accords enregistrés sont caducs » | « Convention à revalider : les accords déjà enregistrés ne comptent plus », avec la raison | — |
| Partenaires rattachés, Déjà rattachés à ce marché | Entreprises ajoutées, Déjà ajoutés à ce marché | — |

La carte « Partenaires sur ce marché » ne devient pas « Partenaires invités » (étude, § 8) : les invitations sont dans la
carte du réseau, qui prend ce nom ; celle-ci liste les entreprises de vos formulaires officiels, sous-traitants
compris. Les textes qui citaient la carte citent son nouveau nom : l'aide de la pièce « Convention de groupement »
(`checklist.py`), le refus « l'offre se fige en générant la convention » (`invites.py`), les « [À compléter] » du dossier
assemblé (`atelier_assemblage.py`), le message « Répartir » (`app.js`). L'étiquette de l'étape serveur « Monter le
groupement » (`groupement_members.py`, testée) reste : elle ne s'affiche plus sur cette page.

**Décision 8 sur la page** : plus aucun « /100 » ni « N/M ». Le seul pourcentage est le couple « Seul X % · À
plusieurs Y % » (en-tête, « Répondre à plusieurs ? », simulation, historique, chaque candidat de « Qui l'a ? » : « À
plusieurs Y % »), et seulement après le dossier (`match_score` n'est posé qu'à partir d'un vrai dossier) ; avant :
« Analyse préliminaire » ou « À analyser ». « N sur M » : pièces à fournir, parts reçues, accords des membres, liste
avant dépôt, détail du score, journal du dossier (« seul X % »). Plus de note sur une entreprise (règle 10 de l'étude
moteur) : le « score /100 » et le « Détail du score » des entreprises trouvées, le « score /100 » de la composition
suggérée sont retirés. Restent des taux qui ne sont pas des notes : TVA, frais de déplacement.

**Traductions** (décision 16) : 41 libellés de la page et de la recherche (357 → 398 clés), vérifiés par
`test_traductions_des_libelles_de_la_page_du_marche`.

**Vérifié dans un vrai navigateur** (démonstration par lien privé, serveur local, 1 280 et 375 px, thème clair et
sombre) : toiture (Préparer surligné, « Seul 87 % »), Kerhel (Déposer surligné, « Seul 43 % · À plusieurs 100 % »,
4 tâches « Terminé », « Avant de déposer : 3 contrôles sur 4 » avec l'attestation URSSAF), Limauzac perdu (aucune
étape surlignée, bilan et carnet de notes en tête) ; aucun débordement horizontal à 375 px ; la barre tient sur une
ligne ; recherche → « Analyser ce marché » → l'analyse à l'écran → « Ouvrir le marché » → la page en haut.

---

## 2. Démonstration (lien privé, pitchs)

- Tous les tests de la démo restent verts (`tests/test_demo_*.py`), la vitrine est inchangée hors des libellés du
  § 0 (analyse « soigner le dossier de présentation », « Groupement avec un désamianteur certifié SS3 », statut
  « Déposé »).
- La mesure ne compte pas la démo ; sa route est classée sans coût.
- La page du marché de la démo, rangée en 4 étapes, est vérifiée sur ses vrais états
  (`test_la_page_du_marche_de_la_demo` : toiture en Préparer, Kerhel en Déposer avec ses 4 tâches faites, Limauzac
  sans étape) et dans un navigateur (§ 1.5).
- Le dossier fictif de l'acheteur garde ses mots (« mémoire technique » dans son règlement) : c'est un dossier
  d'acheteur crédible.

---

## 3. Ce qui reste aux chantiers suivants

**Vague 1, à faire sur ce socle**

- **1.3 Le menu regroupé** (Accueil, Trouver des marchés, Mes marchés, Partenaires, Mes documents, Mon entreprise,
  groupe « Réglages » replié, état gardé ; plus de « Plus »). Les vues restent, ouvertes par `go()` sans changement :
  les repères `vue-*` ne bougent pas. À mettre à jour : `test_menu_non_reorganise_mes_preuves_sous_mon_entreprise`
  (ordre exact du menu, `MENU_AVANT`), `test_carte_du_marche_compacte_un_seul_bouton_et_menu_inchange` (entrées
  attendues dans `menu`), `test_projets_a_venir_masque_par_defaut` (entrée « Projets à venir » du menu), et le test
  des traductions qui exigera chaque nouveau libellé (déjà traduits d'avance, § 0.5). Icônes Lucide du § 8 de
  l'étude (`house`, `folder-kanban`, `handshake`, `building-2`, `settings`…). Le radar quitte le haut des résultats
  pour l'onglet À venir.
- **1.4 et 1.5** : faits (§ 1.4, § 1.5). Restent, pour la vague 2a ou un chantier suivant : les actions de
  Décider (« Préparer seul », « Préparer à plusieurs », « Écarter » : elles changent le statut, donc l'axe d'étapes) ;
  la liste de tâches de Préparer pour une entreprise seule (« la prochaine tâche non faite ») ; une seule liste
  « Prêt à déposer » avec un calcul pour l'entreprise seule ; un seul « Figer l'offre » ; les cartes repliées sauf
  l'action principale ; une barre d'étapes collée sous l'en-tête (sa hauteur varie). Les étiquettes du serveur
  « Plus à jour — à régénérer » et « Caduc : la convention doit être régénérée » (`groupement_convention.py`,
  affichées des deux côtés) sont à passer à « à revalider » avec leurs tests.
- **Décision 8 ailleurs** : « Compatibilité N/100 » et « Seul : N/100 · En groupement : N/100 » des bulles de
  l'accueil et de Mes marchés (`feedScoreTitle`, `kanbanScoreTitle` : chantiers 1.6 et 2a) ; les pourcentages du
  carnet de notes (notes reçues de l'acheteur, Réd. V6) ; sur la vitrine, le cadran « 87 % » de la section
  « Décider » montre un pourcentage avant tout dossier.
- **Sous-titres** (1.7) : celui de la page du marché dit encore « Dossier complet de l'appel d'offres » (`subtitles`
  de `app.js`).
- **1.6 Accueil allégé** (`accueil-ruban`, les liens doublons de `accueil-rail`, « Monter un groupement » →
  « Préparer à plusieurs »). **1.7 Sous-titres en bulle** (`titles` / `subtitles` de `app.js`, déjà sans mot banni).
  **1.8 Transition** (« Ce qui a changé », anciens noms en bulle, courriel aux 7 PME).
- **Test d'arborescence** de Mathys (avant et après la vague 1) : hors code.

**Vagues 2a et 2b** (après) : une adresse par écran, un seul axe d'étapes (la clé `envoye` migre alors vers
« Déposé »), Mes marchés filtrable, une seule fenêtre d'invitation, « lot » → « partie (lot n) », barre basse sur
téléphone ; prise en main (premiers pas sur 30 jours, états vides, confirmation d'email vivante, marché d'exemple),
espace partenaire réduit à « Votre part dans [marché] » (dans `invite.html` et dans `vue-sharedao`).

**Pour Eliot**

- Pages juridiques : `docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 6 (AO, CERFA, mémoire, co-traitant, SIRENE ;
  le modèle de convention).
- Mise en ligne : la migration `b3mesureecrans` (une table de compteurs) part avec ce socle ; contrôle Postgres
  depuis l'état réel de la production à refaire au moment de la mise en ligne.
