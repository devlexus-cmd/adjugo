# Réorganisation de l'interface : vagues 0 et 1, le socle

Contrat du socle posé avant de ranger le menu et la page du marché. Étude : « Réorganiser l'interface d'Adjugo :
étude définitive » (12/10/2026), § 1, 5.3, 7, 8, 9, 10 et 11. Base : `feat/produit-acheteur-collectivites` =
`88a4109` (production du 19/10/2026).

Décisions appliquées (recommandations de l'étude, validées par Eliot) : D0 (a), D1 C corrigée, D2 (a), D3
« Partenaires », D6 4 étapes, D8 (a), D9 (a), D16 (a), D17 (mesure). D4 (a) et D5 (a) étaient déjà en production.

Ce socle fait : la vague 0 restante (§ 0), les repères de test (§ 1.0), la mesure d'usage (§ 1.1) et l'inscription
directe depuis l'essai (§ 1.2). Le chantier « menu et accueil » range ensuite le menu, l'accueil, les sous-titres et
la transition (§ 1.3, 1.6, 1.7, 1.8) ; le chantier « page du marché et recherche » fait 1.4 et 1.5 (§ 1.4, § 1.5).
Les deux chantiers sont réunis sur ce socle ; la réunion et la vérification de fin de la vague 1 sont au § 4.

Tests : `tests/test_reorganisation_v1_socle.py` (repères, mesure, inscription, vague 0, traductions),
`tests/test_reorganisation_v1_menu.py` (menu, onglets, pastilles, accueil, bulles, transition),
`tests/test_reorganisation_v1_marche.py` (page du marché en 4 étapes, recherche, décision 8, démonstration),
`tests/test_reorganisation_v1_reunion.py` (réunion des chantiers : accueil sur la barre du marché, décision 8
partout, menu de l'espace partenaire, pages collectivités, en-tête sur téléphone),
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
| Modèle de convention de groupement (« co-traitant (partenaire) », « Référence du dossier sur Adjugo : AO-0012 ») | Texte juridique figé par empreinte : le changer rendrait caduques toutes les conventions déjà validées (§ 4.7) ; même fichier, § 6.4 et § 9 |
| Pièces du dossier FICTIF de l'acheteur dans la démo (règlement, cadre « mémoire technique », CCTP) et noms des pièces exigées | Ce sont les mots de l'acheteur, pas le texte du produit |
| Document de « Mon savoir-faire » de l'entreprise fictive (« Mémoire technique — Réfection toiture école de Bréhaut (2024) ») | Le nom qu'une entreprise donne à son propre fichier, comme le ferait un vrai client. Ses pièces de réponse rangées sur la page Toiture, elles, sont renommées (§ 4.7) |
| Nom que le règlement donne à la pièce (« Dossier de présentation (mémoire justificatif) ») et nom par défaut du fichier exporté (« Mémoire technique ») | Le fichier est remis à l'acheteur : il porte son vocabulaire |
| En-tête « DPGF du lot - prix de vente HT » et nom `DPGF_…csv` du fichier du partenaire | Même raison (fichier remis au chef de file puis à l'acheteur) |
| Question à l'acheteur « deux limites différentes pour le mémoire » (`grille_exigences.py`) | Texte adressé à l'acheteur ; son titre à l'écran est « Longueur du dossier de présentation » |
| Dossiers rangés « Mémoire technique », « CERFA », « DCE » (clés internes) | Clés de rangement, non renommées pour ne rien casser chez les clients ; `folderLabel` (`nomDossier`, `DOSSIERS_AFFICHES`) les affiche « Dossier de présentation », « Formulaires officiels », « Dossier du marché » (§ 4.7). Les dossiers des ZIP, eux, sont renommés (`01_Formulaires_officiels/`, `formulaires_officiels/`, `pieces_partenaires/`) |
| « N / M » de la note de l'acheteur (carnet de notes, « 32,5 / 40 ») ; barème remis à l'IA (`analysis.py`) ; détail du score de synergie (`app/sourcing/scoring.py`, jamais affiché) | Décision 8 : la note est écrite comme dans le courrier de l'acheteur ; les deux autres ne sont pas lus par un client. Liste exacte : `NM_GARDES` (`tests/test_reorganisation_v1_relecture.py`) |
| « agent de sécurité » (`app/sourcing/groupement.py`) | Un métier, pas un agent d'IA |
| Pages « collectivités » (`acheteur*.html`) | Plus d'exception depuis la réunion (§ 4.3) : « SIRENE » y devient « registre Insee », et ces pages entrent dans le test des mots bannis |
| Routeur archivé `cospace.py` | Jamais monté (`app/main.py`) |
| Commentaires, docstrings, journaux, consignes de l'IA | Jamais lus par un client |

Les exceptions exactes sont dans `EXCEPTIONS` (`tests/test_reorganisation_v1_socle.py`) : toute nouvelle exception
s'y justifie et s'ajoute ici.

### 0.4 « Vérifié » (décision 9)

« vérifié » reste seulement pour une identité contrôlée dans un registre, avec sa date (« vérifié au registre
officiel le 08/10 », « Vérifié le … » des badges du réseau, adresse email vérifiée par un code). Un badge du réseau
de niveau « ok » sur une autre source (aucun avis BODACC, marchés publiés dans DECP) se dit « constaté à la source »
au lecteur d'écran, plus « vérifié » (§ 4.7). Retirés :
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
   fenêtre), `fenetres-` (famille de fenêtres sœurs), `ecran-`, `bandeau-`, `menu-` (une partie de la barre
   latérale), `onglets-` (une barre d'onglets au-dessus des vues).
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
| `menu` | Barre latérale (marque, 6 rubriques, groupe « Réglages », compte) |
| `menu-reglages` | Groupe « Réglages » : Collègues, Abonnement, Mon compte, Administration, Mon avis, thème (§ 1.3) |
| `entete` | Barre du haut (titre de la rubrique ou de la vue et sa bulle (i), notifications, boutons de la vue) |
| `contenu` | Toutes les vues |
| `onglets-rubrique` | Onglets de la rubrique ouverte, au-dessus des vues (§ 1.3) |
| `carte-essai` | Carte de l'essai (forfait, limite d'usage) |
| `carte-suggestion-reseau` | Suggestion « publiez votre profil partenaire » |
| `bandeau-cookies` | Bandeau du stockage local |
| `ecran-confirmation-email` | Écran plein « Confirmez votre adresse email » |

**Accueil (`vue-dashboard`)**

| Repère | Zone |
|---|---|
| `accueil-ce-qui-a-change` | Note « Ce qui a changé » (transition, § 1.8) |
| `accueil-premiers-pas` | Premiers pas (3 étapes) |
| `accueil-reseau` | Bloc « À plusieurs » (groupements par étape, « Préparer à plusieurs ») |
| `accueil-amont` | « Une longueur d'avance » (masqué, `PROJETS_A_VENIR=0`) |
| `accueil-grille` | Grille : flux, rail, bilan, carnet |
| `accueil-flux` | « Vos marchés » (7 derniers marchés) |
| `accueil-rail` | Pièces à renouveler, entonnoir « Mes marchés » (absent s'il n'y a rien à montrer) |
| `accueil-bilan` | « Où vous gagnez / perdez » |
| `accueil-carnet` | Carnet de notes (« Où vous perdez des points ») |

Retiré (§ 1.6) : `accueil-ruban` (ruban des 4 chiffres).

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
| `trouver-recherche` | La recherche, « Rechercher des marchés » (onglet « Publiés ») |
| `trouver-radar` | Onglet « À venir » : contrats qui arrivent à échéance (anciennement le radar des échéances) |
| `trouver-alertes` | Onglet « Mes alertes » (anciennement « Alertes automatiques ») |
| `trouver-carte` | Une carte de résultat (élément répété par `v-for`) |
| `trouver-analyse` | L'analyse d'un marché trouvé : « Ouvrir le marché » juste après son résumé (§ 1.4) |

**Autres vues**

| Repère | Zone |
|---|---|
| `vue-amont` | Projets à venir (masqué) |
| `vue-kb` | Mon savoir-faire ; contient `kb-fiches-proposees` |
| `vue-atelier` | Atelier du dossier de présentation ; contient `atelier-page-preparation-case`, `atelier-page-preparation`, `atelier-entretien`, `atelier-onglets`, `atelier-repartition` (« Qui écrit quoi ») |
| `vue-pipeline`, `vue-cotraitants`, `vue-contacts`, `vue-documents`, `vue-invoices`, `vue-company`, `vue-preuves`, `vue-criteria`, `vue-team` | Une vue chacune (Mes marchés › Marchés, Partenaires › Mes partenaires, Partenaires › Contacts, Mes documents › Mes pièces, Mes marchés › Devis et factures, Mon entreprise › Identité, › Mes preuves, › Mes critères, Réglages › Collègues) |
| `vue-compte` | Réglages › Mon compte : mot de passe, mes données (cartes venues de `vue-team`, § 1.3) |
| `vue-billing` | Abonnement ; contient `billing-offres` (les cartes d'offre) |
| `vue-admin` | Administration ; contient `admin-mesure` (écrans ouverts, § 1.1) |
| `vue-consortiums` | Mes marchés › À plusieurs (anciennement « Mes groupements ») |
| `vue-reseau` | Partenaires › Réseau Adjugo ; contient `reseau-onglets`, `reseau-profil`, `reseau-annuaire`, `reseau-historique`, `reseau-recues` |
| `vue-shared` | Mes marchés › Où je suis partenaire (anciennement « Partagé avec moi », liste) |
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
- **Menu par rubriques (§ 1.3)** : ajoutés à `ECRANS` : `compte` (Réglages › Mon compte, une vue) ; `avenir` et
  `alertes`, les onglets « À venir » et « Mes alertes » de Trouver des marchés, comptés à chaque affichage (savoir
  si l'onglet « À venir » est ouvert sert à la veille). `sourcing` compte chaque ouverture de Trouver des marchés,
  quel que soit l'onglet ; revenir à « Publiés » depuis un autre onglet n'est pas compté. Dans Administration, un
  écran se lit « Rubrique › Onglet » (« Trouver des marchés › À venir », « Mes documents › Mon savoir-faire »).
  Aucune migration : la table garde les mêmes colonnes.

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

## 1.3 Le menu regroupé (décisions 1, 2 a, 3)

### 1.3.1 Ce qu'on voit

| # | Entrée du menu | Icône | Ouvre | Onglets (zone `onglets-rubrique`) | Pastille |
|---|---|---|---|---|---|
| 1 | Accueil | `house` | `dashboard` | aucun | aucune |
| 2 | Trouver des marchés | `search` | `sourcing`, onglet « Publiés » | Publiés · À venir · Mes alertes (· Projets à venir si `PROJETS_A_VENIR=1`) | aucune |
| 3 | Mes marchés | `folder-kanban` | `pipeline` | Marchés · Où je suis partenaire · À plusieurs · Devis et factures | ce qui attend votre action |
| 4 | Partenaires | `handshake` | `cotraitants` | Mes partenaires · Réseau Adjugo (avec ses onglets actuels) · Contacts | aucune |
| 5 | Mes documents | `folder-lock` | `documents` | Mes pièces · Mon savoir-faire | pièces à renouveler |
| 6 | Mon entreprise | `building-2` | `company` | Identité · Mes critères · Mes preuves | aucune |
| — | Réglages (groupe replié, en bas) | `settings` | — | Collègues, Abonnement, Mon compte, Administration (administrateur de la plateforme), Mon avis, thème | aucune |

- **Une seule source** : `RUBRIQUES`, en tête de `app.js` (avec les fonctions pures `rubriqueDe`, `ongletDe`,
  `ancienNom`). Le menu (`app.html`, zone `menu`) en reprend l'ordre, les libellés et les icônes, ce que
  `test_menu_six_rubriques_dans_l_ordre_puis_reglages` vérifie.
- **Chaque ancienne vue est un onglet de sa rubrique, ouverte par `go()` sans changement** : les vues, leurs
  repères `vue-*` et les chargements de `go()` ne bougent pas. Un seul composant d'onglets pour toutes les rubriques
  (`onglets-rubrique`, au style des onglets existants `rn-tab`), affiché seulement sur une vue qui en est un onglet,
  jamais sur une page de détail (le marché, l'atelier, un dossier partagé ont leur bouton de retour).
- **La rubrique reste surlignée**, pages de détail comprises : le marché, l'atelier et un dossier partagé sont dans
  « Mes marchés ». Replié sur un de ses écrans, le titre « Réglages » est surligné.
- **« Plus » n'existe plus.** Le groupe « Réglages » est un vrai bouton (`aria-expanded`), replié par défaut ; son
  état est gardé dans ce navigateur (`adjugo_nav_reglages`, lecture et écriture protégées).
- **Plus d'entrée qui apparaît selon les données** : « Partagé avec moi » (affichée seulement s'il y avait un dossier)
  devient l'onglet « Où je suis partenaire », toujours présent.
- **Pastilles d'action seulement, jamais un total ni zéro** : plus de nombre de marchés, de partenaires, de contacts,
  de documents du savoir-faire ni de groupements. « Mes marchés » (et l'onglet « Où je suis partenaire ») : les
  invitations reçues par le réseau à traiter, plus les marchés d'autres entreprises où votre accord est demandé
  (convention à valider) ou où une partie du dossier de présentation vous attend (`mmActions`). « Mes documents »
  (et « Mes pièces ») : les pièces à renouveler.
- **Invitations reçues par le réseau** : elles se traitent toujours dans Partenaires › Réseau Adjugo › Invitations
  reçues (onglets internes gardés jusqu'à la vague 2a). L'onglet « Où je suis partenaire » les annonce et y mène
  (« Voir les invitations »).
- **Mon compte** : nouvelle vue `compte`. Les cartes « Mon mot de passe » et « Mes données (RGPD) » y sont déplacées
  telles quelles depuis « Équipe » (devenue « Collègues »). Le courriel d'invitation d'un collègue dit où changer
  son mot de passe (« menu Réglages, puis Mon compte »).
- **Trouver des marchés** en trois onglets. Le radar quitte le haut des résultats pour l'onglet « À venir », sous
  son nom de l'étude, « Contrats qui arrivent à échéance » (`calendar-clock`). Il a ses propres champs (métier,
  départements : les mêmes valeurs que la recherche « Publiés ») et le bouton « Chercher les fins de contrat » (plus
  de « mots-clés ci-dessus »). La note « pertinence N/100 » disparaît (décision 8 : pas de note avant le dossier ;
  l'ordre est dit dans la bulle) ; la flèche « ↗ » tapée aussi (règle 6 des icônes). « Mes alertes » dit quelle
  recherche sera enregistrée. « Publiés » : le reste de la vue ne change pas (une seule balise `<template v-if>`
  l'entoure, sans réindentation ; `trouver-recherche`, `trouver-carte` et `trouver-analyse` ne sont pas touchés).
  L'onglet est l'état `trouverOnglet`, hors de `src`.
- **Icônes du § 8** : celles du tableau ci-dessus ; dans les onglets `calendar-clock` (À venir), `bell`, `inbox`,
  `receipt`, `network`, `contact-round`, `library`, `sliders-horizontal`, `award`, `users-round` (Collègues
  seulement), `credit-card`, `circle-user`, `shield`. Aussi : « Mon profil partenaire » passe à `id-card` (il
  portait `building-2`, l'icône de Mon entreprise) et « Annuaire » à `network` ; « à plusieurs » (accueil, Mes
  marchés, notifications) passe de `users-round` à `handshake`.
- **Réseau Adjugo** garde ses onglets internes (exception temporaire de l'étude) : un cran plus petits que ceux de la
  rubrique, pour lire deux niveaux.
- **375 px** : les onglets passent en grille (2 colonnes pour 2 ou 4 onglets, 3 pour 3). Vérifié dans un vrai
  navigateur : aucun défilement horizontal sur les 18 écrans rangés.
- **Traductions (décision 16)** : 62 clés ajoutées (357 → 419) : menu, onglets, titres, bulles de l'en-tête,
  anciens noms, note de transition, nouveaux boutons. « Mes pièces » devient « Mis justificantes » en espagnol
  (« Mis documentos » est déjà la rubrique). Test : `test_traductions_du_menu_des_onglets_des_bulles_et_de_la_note`.

### 1.3.2 Chaque ancienne vue en 2 clics au plus

| Ancienne entrée | Aujourd'hui | Clics |
|---|---|---|
| Tableau de bord | Accueil | 1 |
| Trouver des marchés ; radar ; alertes | Trouver des marchés › Publiés ; › À venir ; › Mes alertes | 1 ; 2 ; 2 |
| Mes marchés ; Partagé avec moi ; Mes groupements ; Devis & factures | Mes marchés › Marchés ; › Où je suis partenaire ; › À plusieurs ; › Devis et factures | 1 ; 2 ; 2 ; 2 |
| Mes partenaires ; Réseau ; Contacts | Partenaires › Mes partenaires ; › Réseau Adjugo ; › Contacts | 1 ; 2 ; 2 |
| Mes documents ; Mon savoir-faire | Mes documents › Mes pièces ; › Mon savoir-faire | 1 ; 2 |
| Mon entreprise ; Mes critères ; Mes preuves | Mon entreprise › Identité ; › Mes critères ; › Mes preuves | 1 ; 2 ; 2 |
| Équipe ; Abonnement ; Administration ; Mon avis | Réglages › Collègues (et Mon compte) ; › Abonnement ; › Administration ; › Mon avis | 2 (1 si le groupe est déjà ouvert) |

`test_chaque_vue_a_sa_rubrique_et_s_atteint_en_deux_clics_au_plus` le vérifie pour chaque écran de `ECRANS` (hors
pages de détail, qui s'ouvrent depuis la liste de leur rubrique).

### 1.3.3 Ce qui n'est pas fait ici, et pourquoi

- **« Courriels » (fréquence du résumé) et « Nos sources et nos chiffres »** ne sont pas dans Réglages : aucun réglage
  de fréquence ni cette page n'existent encore (un seul résumé arrive en vague 2a). Une entrée vide annoncerait une
  fonction qui n'est pas en ligne (§ 6 de l'étude).
- **« Tarifs »** reste dans Identité : en faire un onglet couperait la vue Mon entreprise (un seul formulaire, un seul
  « Enregistrer »). C'est « Mon entreprise en onglets », vague 2a.
- **Contacts** sans filtre par type (vague 2a, avec les listes filtrables).
- **Pastille « parts à relire » côté chef de file** : ces parts ne sont connues que sur la page du marché ; elles
  viendront avec la liste « À faire » (vague 2a).
- **Onglets internes du Réseau** : gardés jusqu'à la vague 2a (Mes partenaires · Réseau Adjugo · Mon profil sur le
  réseau · Contacts).
- **Barre basse sur téléphone** (décision 18) : vague 2a. Sur téléphone, le menu reste derrière le bouton « Menu ».

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
  Moteur V0). La « pertinence N/100 » du radar est retirée par le
  chantier 1.3 (§ 1.3.1).

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

## 1.6 Accueil allégé

- **Retirés** : le ruban des 4 chiffres (« Taux de réussite 0 % » sur un compte neuf), les 3 liens qui doublent le
  menu (Mes partenaires, Mon entreprise, Mes documents) et le 4e raccourci « Trouver des marchés » (le bouton de
  l'en-tête reste). Le rail ne garde que les pièces à renouveler et l'entonnoir « Mes marchés » ; il disparaît
  quand il n'a rien à montrer, et « Vos marchés » prend toute la largeur.
- **Bloc « À plusieurs »** (anciennement « Réseau Adjugo — gagnez les gros marchés à plusieurs », un slogan) : son
  bouton « Monter un groupement » devient **« Préparer à plusieurs »** et mène à **Mes marchés › À plusieurs** (la
  vue des groupements : c'est « Mes marchés filtré sur les marchés à plusieurs », sans réécrire de vue). Icône
  `handshake` : `user-plus` reste réservé à « Inviter un partenaire ». Le bouton « Mes groupements » (état « tous
  déposés ») devient « Voir mes marchés à plusieurs ».
- **Mes marchés › À plusieurs** : « Nouveau groupement » devient « Préparer à plusieurs » (vers Marchés), avec une
  bulle : ouvrir le marché, puis « Inviter un partenaire ».
- « Vos appels d'offres » devient **« Vos marchés »**.
- Déjà masqués (décision 5) : « Une longueur d'avance » et l'écran Projets à venir. Gardés : premiers pas, bilan
  « Où vous gagnez / perdez » et carnet de notes (le bilan rejoint Mes marchés › Bilan en vague 2a).

## 1.7 Sous-titres de vue en bulle

- Plus de ligne de sous-titre sous le titre. Le titre est la rubrique (quand la vue en est un onglet : les onglets
  disent où l'on est dedans) ou le nom de la vue (Le marché, Collègues…). À côté, une bulle (i) : ce que fait
  l'écran, puis son ancien nom (§ 1.8).
- **Retirés** : « Débloquez toute la puissance d'Adjugo » (Abonnement : une promesse), « Vue d'ensemble de votre
  activité » (Accueil : n'apprend rien), « Dossier complet de l'appel d'offres » (Le marché : faux tant que seule
  l'annonce est lue). **Réécrit** : « Sources officielles, traçables — vous validez chaque étape » devient « Les
  marchés publiés sur les sources officielles : chaque résultat renvoie à son annonce. » **Nouveaux** : À venir, Mes
  alertes, Mon compte.
- Sur téléphone, la bulle de l'en-tête s'ouvre sous la barre du haut, sur toute la largeur (le flou de la barre
  piégerait une bulle « fixe » dans la barre).

## 1.8 Transition

- **Note « Ce qui a changé »** sur l'accueil (`accueil-ce-qui-a-change`) : une ligne, puis la liste repliée « Où
  retrouver vos écrans » ; un bouton « Fermer ». Visible une semaine au plus après son premier affichage, état gardé
  dans ce navigateur (`adjugo_reorg_v1`). Seulement pour les comptes créés avant `REORG_V1_DEPUIS` (`app.js`), et
  jamais dans la démonstration (`DEMO_EMAIL_APP`, égal à `demo_seed.DEMO_EMAIL`, vérifié par un test).
  **À régler par Eliot : `REORG_V1_DEPUIS` = le jour de la mise en ligne** (réglé au 20/10/2026 : un compte créé
  avant ce jour voit la note).
- **Anciens noms en bulle** : la bulle de l'en-tête finit par « Anciennement « … ». » pour chaque écran renommé
  (Accueil, À venir, Mes alertes, Où je suis partenaire, À plusieurs, Devis et factures, Réseau Adjugo, Identité,
  Collègues ; Mon compte : « Votre mot de passe et vos données étaient dans « Équipe ». »). **À retirer un mois
  après la mise en ligne** : supprimer les champs `ancien` et `avant` de `RUBRIQUES` (la bulle ne garde que la phrase
  de l'écran), puis la note.
- **Plus d'ancien nom ailleurs** : l'écran de rédaction du partenaire (`redaction-partenaire.js`, 3 messages),
  « Invitation acceptée : le dossier est dans Mes marchés, onglet « Où je suis partenaire ». », le retour d'un
  dossier partagé (« Où je suis partenaire »), le titre de Mes marchés › À plusieurs. Garde-fou :
  `test_les_anciens_noms_ne_restent_que_dans_la_note_et_les_bulles`.
- Pages juridiques : aucune ne cite un écran renommé (`docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 7).

### 1.8.1 Courriel aux 7 PME de test (à envoyer par Eliot)

> **Objet : Adjugo : le menu a été rangé**
>
> Bonjour,
>
> Merci de tester Adjugo avec nous. Nous venons de ranger le menu : vos marchés, vos documents et vos partenaires
> n'ont pas bougé, seule la place des écrans a changé.
>
> Le menu compte maintenant six rubriques :
>
> - **Accueil** (anciennement « Tableau de bord ») ;
> - **Trouver des marchés** : les marchés publiés, les contrats qui arrivent à échéance (onglet « À venir »,
>   anciennement « Radar des échéances ») et vos alertes ;
> - **Mes marchés** : vos marchés, ceux où une autre entreprise vous a invité (onglet « Où je suis partenaire »,
>   anciennement « Partagé avec moi »), vos marchés à plusieurs (onglet « À plusieurs », anciennement « Mes
>   groupements ») et vos devis et factures ;
> - **Partenaires** : vos partenaires, le Réseau Adjugo et vos contacts ;
> - **Mes documents** : vos pièces et votre savoir-faire ;
> - **Mon entreprise** : son identité, vos critères et vos preuves.
>
> En bas du menu, « Plus » devient **Réglages** : vos collègues (anciennement « Équipe »), l'abonnement, votre
> compte (mot de passe et données) et « Mon avis ».
>
> Pendant un mois, l'ancien nom de chaque écran reste écrit dans la bulle (i) à côté de son titre. Sur l'accueil,
> une note « Ce qui a changé » reprend tout cela.
>
> Un écran introuvable, un mot qui ne vous parle pas ? Répondez simplement à ce courriel, ou passez par « Mon avis »
> dans Réglages.
>
> Bonne journée,
> Eliot, pour Adjugo

### 1.8.2 Tests mis à jour par ce chantier

`test_reorganisation_v1_socle.py` (zones `menu-reglages`, `onglets-rubrique`, `accueil-ce-qui-a-change`,
`vue-compte` ; `accueil-ruban` retiré ; libellés du menu), `test_redaction_v3_mes_preuves_ecrans.py` (« Mes preuves »
reste dans Mon entreprise, en onglet), `test_redaction_v2_ecrans.py` (Mon savoir-faire, onglet de Mes documents),
`test_correctifs_urgents.py` (Projets à venir : un onglet conditionnel, plus une entrée du menu),
`test_reseau_ecrans.py` (Réseau Adjugo, onglet de Partenaires). Nouveau : `test_reorganisation_v1_menu.py`.

---

## 2. Démonstration (lien privé, pitchs)

- Tous les tests de la démo restent verts (`tests/test_demo_*.py`), la vitrine est inchangée hors des libellés du
  § 0 (analyse « soigner le dossier de présentation », « Groupement avec un désamianteur certifié SS3 », statut
  « Déposé »).
- La mesure ne compte pas la démo ; sa route est classée sans coût.
- Menu par rubriques (§ 1.3) : la démo s'ouvre sur l'accueil allégé, sans la note « Ce qui a changé » (jamais pour
  le compte démo). Vérifié dans un vrai navigateur (démo locale, thèmes clair et sombre, 375 px) : chaque rubrique,
  chaque onglet, le groupe « Réglages », la bulle de l'en-tête, les pastilles (« Mes documents » : les 2 pièces à
  renouveler de la démo).
- La page du marché de la démo, rangée en 4 étapes, est vérifiée sur ses vrais états
  (`test_la_page_du_marche_de_la_demo` : toiture en Préparer, Kerhel en Déposer avec ses 4 tâches faites, Limauzac
  sans étape) et dans un navigateur (§ 1.5).
- Le dossier fictif de l'acheteur garde ses mots (« mémoire technique » dans son règlement) : c'est un dossier
  d'acheteur crédible.

---

## 3. Ce qui reste aux chantiers suivants

**Vague 1, à faire sur ce socle**

- **1.3 Le menu regroupé** : fait (§ 1.3). Reste pour la vague 2a : Courriels, Tarifs en onglet, filtre des
  Contacts, pastille « parts à relire » du chef de file, onglets internes du Réseau, barre basse (§ 1.3.3).
- **1.4 et 1.5** : faits (§ 1.4, § 1.5). Restent, pour la vague 2a ou un chantier suivant : les actions de
  Décider (« Préparer seul », « Préparer à plusieurs », « Écarter » : elles changent le statut, donc l'axe d'étapes) ;
  la liste de tâches de Préparer pour une entreprise seule (« la prochaine tâche non faite ») ; une seule liste
  « Prêt à déposer » avec un calcul pour l'entreprise seule ; un seul « Figer l'offre » ; les cartes repliées sauf
  l'action principale ; une barre d'étapes collée sous l'en-tête (sa hauteur varie). Les étiquettes du serveur
  « Plus à jour — à régénérer » et « Caduc : la convention doit être régénérée » (`groupement_convention.py`,
  affichées des deux côtés) sont à passer à « à revalider » avec leurs tests.
- **Décision 8 ailleurs** : faite à la réunion (§ 4.3). Restent les pourcentages du carnet de notes (notes reçues de
  l'acheteur, Réd. V6).
- **1.6 Accueil allégé**, **1.7 Sous-titres en bulle**, **1.8 Transition** : faits (§ 1.6 à 1.8).
- **Test d'arborescence** de Mathys (avant et après la vague 1) : hors code.

**Vagues 2a et 2b** (après) : une adresse par écran, un seul axe d'étapes (la clé `envoye` migre alors vers
« Déposé »), Mes marchés filtrable, une seule fenêtre d'invitation, « lot » → « partie (lot n) », barre basse sur
téléphone ; prise en main (premiers pas sur 30 jours, états vides, confirmation d'email vivante, marché d'exemple),
espace partenaire réduit à « Votre part dans [marché] » (dans `invite.html` et dans `vue-sharedao`).

**Pour Eliot**

- Menu par rubriques : régler `REORG_V1_DEPUIS` (`app.js`) au jour de la mise en ligne ; envoyer le courriel aux
  7 PME (§ 1.8.1) ; un mois après, retirer les anciens noms des bulles et la note (§ 1.8).
- Pages juridiques : `docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 6 (AO, CERFA, mémoire, co-traitant, SIRENE ;
  le modèle de convention).
- Mise en ligne : la migration `b3mesureecrans` (une table de compteurs) part avec ce socle ; contrôle Postgres
  depuis l'état réel de la production à refaire au moment de la mise en ligne.

---

## 4. Réunion des chantiers et fin de la vague 1

### 4.1 La réunion

Production `88a4109` (avance rapide), socle `2380489` (avance rapide), menu `ad73cf1` (avance rapide), page du marché
`dffbb1d` (fusion `0f5a9df`). Conflits résolus bloc par bloc, sans prendre un côté entier : `app.html` (Trouver des
marchés garde les onglets du menu et prend le commentaire de la page ; empreintes SRI régénérées), `i18n.js` (fusion
à trois voies des dictionnaires : 419 + 41 → 459 clés ; « Dossier de présentation », traduit des deux côtés, garde la
traduction du menu, cohérente avec les autres clés), `sri-manifest.json` (régénéré), ce contrat. Contrôle ligne à
ligne contre la base commune : aucune ligne ajoutée par un côté n'est perdue (seules les anciennes empreintes SRI
sont remplacées).

### 4.2 Le critère de fin de l'étude (§ 9), ligne par ligne

| Critère | Résultat | Vérification |
|---|---|---|
| Aucun mot banni dans les textes visibles | **0** | Recherche outillée (`tests/textes_visibles.py`) : `app.html` (2 295 textes), `app.js` (1 812), `redaction-partenaire.js` (797), `carnet-notes.js` (398), `sources-publiques.js` (227), `cotraitance-crypto.js` (67), `invite.html` (734), `landing.html` (106), `demo.html` (34), `demande-acces.html` (61), `acheteur.html` (485), `acheteur-landing.html` (141) ; les 285 chaînes des fonctions qui envoient un courriel et les 428 messages d'erreur montrés. Les pages collectivités entrent dans le test (`FRONT_HTML`). Exceptions : `EXCEPTIONS` et § 0.3 (le dossier fictif de l'acheteur dans la démo : une phrase de son règlement dans « Comment vous serez noté » ; les pièces de réponse de l'entreprise fictive, d'abord nommées « Mémoire technique — … » et « DPGF — … », sont renommées au § 4.7). Relecture (§ 4.7) : le serveur (constantes lues par l'ast), les générateurs des PDF et du ZIP, les dossiers rangés entrent aussi dans les garde-fous |
| Chaque ancienne vue en 2 clics au plus | **oui** | Tableau du § 4.4, parcouru dans le navigateur ; `test_chaque_vue_a_sa_rubrique_et_s_atteint_en_deux_clics_au_plus` |
| L'affichage tient sur 375 px | **oui** | Dans le navigateur, largeur de page = 375 px : les 19 écrans de l'application (démo), les 7 pages de marché de la démo, l'espace partenaire, la vitrine, la démo, la demande d'accès, la vitrine collectivités. Deux pages juridiques débordent : relevées pour Eliot (`docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 8) |
| La suite passe, avec les nouveaux repères | **oui** | Suite complète verte : 2 055 tests ; repères `data-test` de `tests/zones.py` |
| Chaque libellé du menu a son néerlandais et son espagnol | **oui** | 465 clés, `scripts/i18n_ajouter.py --check` ; tests de traduction du socle, du menu, de la page et de la réunion |
| Test d'arborescence de Mathys (aucune tâche avec un nouvel échec chez 2 PME sur 7) | **à faire** | Hors code : avant et après la vague 1, auprès des 7 PME |

### 4.3 Corrigé à la réunion (trouvé en parcourant l'application réunie)

- **Accueil « À plusieurs » : un seul découpage.** Il comptait les groupements sur les 5 étapes de juin (« Repérer le
  marché », « Monter le groupement »…, avec des zéros) et marquait chaque marché « Étape 5 sur 5 », alors que la page du
  marché n'a plus que Lire · Décider · Préparer · Déposer. Désormais : étape 1 → Décider, 2 à 4 → Préparer (ses tâches
  « à plusieurs »), 5 → Déposer, seulement les étapes où il y a un marché (`grpDashEtapes`) ; le marché porte le nom de
  son étape. Le compteur « marchés accessibles en groupement » ne s'affiche que s'il y en a (étude, § 5.3 : jamais
  « 0 marchés »). L'étiquette serveur « Monter le groupement » reste côté partenaire (son stepper, vague 2b).
- **Décision 8 hors de la page du marché** : bulles de l'accueil et de Mes marchés, pastille du tiroir d'un marché
  (« Compatibilité 72/100 », « Seul : 43/100 · En groupement : 100/100 ») → « Seul 72 % », « Seul 43 % · À plusieurs
  100 % » ; « 1/1 part reçue » → « parts reçues 1 sur 1 » ; « Avec partenaires : 87 % » → « À plusieurs 87 % » ; tous
  les « N/M » des gabarits (premiers pas, questionnaire, documents, collègues, analyses, Mes marchés › À plusieurs,
  compteurs du profil réseau, accords des membres) et des messages → « N sur M » ; espace partenaire et dossier partagé :
  « 100/100 score du groupement » → « 100 % à plusieurs », « 1/1 parts reçues » → « parts reçues 1 sur 1 », accords
  « 1 sur 2 » ; vitrine : « 22/22 », « 14/14 », « 18/26 » → « 22 sur 22 »… (le cadran « 87 % » suit la phrase « Une
  fois le dossier analysé » : conforme).
- **Espace partenaire** : le menu verrouillé montrait l'ancien menu (Pilotage, Tableau de bord, Gestion, Devis &
  factures, Configuration, Entreprise, Équipe) ; il montre celui de l'application (les six rubriques, puis Réglages ›
  Collègues, Abonnement ; icônes du § 8). « Mon appel d'offres » → « Le marché » ; « Trouvez des appels d'offres
  publics » → « Trouvez des marchés publics » ; l'écran verrouillé promet « vos marchés, vos documents, vos collègues »
  (plus « pipeline, coffre-fort »).
- **Pages collectivités** : « SIRENE » → « registre Insee » (« Annuaire des entreprises » pour le lien vers
  annuaire-entreprises.data.gouv.fr), comme la règle du § 0.2 ; l'exception du § 0.3 est levée.
- **En-tête du marché sur téléphone** : le choix de l'étape passait à côté du titre, écrasé sur un tiers de la
  largeur ; il passe dessous (`.mk-entete`, 520 px et moins).
- **Derniers anciens noms** : « Devis & factures liés » → « Devis et factures liés » (icône `receipt`) ; messages
  « Appel d'offres introuvable / mis à la corbeille », « Cet appel d'offres n'est plus accessible », « Lancez votre
  première recherche d'appel d'offres » → « Marché … », « … de marchés ».
- **375 px hors de l'application** (vu dans le navigateur, déjà en production) : la vitrine s'élargissait à 407 px
  (halo du cadran « Décider ») et sa barre du haut dépassait ; la vitrine collectivités s'élargissait à 495 px (halo du
  haut). Halos coupés au bord de l'écran, barre du haut resserrée sur téléphone.
- Traductions : 6 libellés (459 → 465 clés). Test : `tests/test_reorganisation_v1_reunion.py`.

### 4.4 Chaque ancienne vue en 2 clics au plus (parcouru dans le navigateur)

| Ancienne vue | Chemin aujourd'hui | Clics |
|---|---|---|
| Tableau de bord | Accueil | 1 |
| Trouver des marchés (Sourcing) | Trouver des marchés › Publiés | 1 |
| Radar des échéances | Trouver des marchés › À venir | 2 |
| Alertes automatiques | Trouver des marchés › Mes alertes | 2 |
| Projets à venir (si `PROJETS_A_VENIR=1`) | Trouver des marchés › Projets à venir | 2 |
| Mes marchés (Pipeline) | Mes marchés › Marchés | 1 |
| Partagé avec moi | Mes marchés › Où je suis partenaire | 2 |
| Mes groupements | Mes marchés › À plusieurs | 2 |
| Devis & factures | Mes marchés › Devis et factures | 2 |
| Mes partenaires | Partenaires › Mes partenaires | 1 |
| Réseau | Partenaires › Réseau Adjugo | 2 |
| Contacts | Partenaires › Contacts | 2 |
| Mes documents (coffre-fort) | Mes documents › Mes pièces | 1 |
| Mon savoir-faire | Mes documents › Mon savoir-faire | 2 |
| Mon entreprise (Profil de l'entreprise) | Mon entreprise › Identité | 1 |
| Mes critères | Mon entreprise › Mes critères | 2 |
| Mes preuves | Mon entreprise › Mes preuves | 2 |
| Équipe | Réglages › Collègues | 2 (1 si le groupe est ouvert) |
| Mot de passe, données (dans « Équipe ») | Réglages › Mon compte | 2 (1 si le groupe est ouvert) |
| Abonnement | Réglages › Abonnement | 2 (1 si le groupe est ouvert) |
| Administration | Réglages › Administration (administrateur) | 2 (1 si le groupe est ouvert) |
| Mon avis | Réglages › Mon avis | 2 (1 si le groupe est ouvert) |
| Un marché, son atelier, un dossier partagé | depuis la liste de Mes marchés (pages de détail) | — |

### 4.5 Parcours de bout en bout dans un vrai navigateur (serveur local, base jetable, aucun envoi, aucune IA)

- **Démo par lien privé** (clé jetable de 48 caractères, `DEMO_PUBLIC=0`, comme en production) : choix de l'espace →
  Accueil (sans la note « Ce qui a changé ») → Mes marchés et ses onglets → Kerhel (Déposer surligné, « Seul 43 % · À
  plusieurs 100 % », 4 tâches « Terminé », « Avant de déposer : 3 contrôles sur 4 ») → Réfection toiture (seul,
  Préparer surligné, « Seul 87 % ») → Trouver des marchés › Publiés → « Voir les marchés pour mon entreprise » →
  « Analyser ce marché » (l'écran mène à l'analyse) → « Ouvrir le marché » (la page en haut, Décider surligné).
  1 280 px et 375 px, thème sombre ; aucun mot banni sur les pages de marché (lecture du texte affiché).
- **Espace partenaire** (lien d'invitation de Breizh Désamiantage sur Kerhel) : menu verrouillé réorganisé, « Le
  marché », « 100 % à plusieurs », « parts reçues 1 sur 1 » ; 375 px.
- **Connexion** : déconnexion → vitrine ; `/app?inscription` ouvre « Créons votre compte » ; compte administrateur de
  test créé dans la base jetable (avant la mise en ligne du menu) : note « Ce qui a changé », Réglages ouvert (état
  gardé), Administration › « Écrans ouverts » (la démo n'est pas comptée).

### 4.6 Laissé, avec sa raison

- Le stepper des 5 étapes côté partenaire (`invite.html`, `vue-sharedao`) : vague 2b (« Votre part dans [marché] »).
- Le choix du statut dans l'en-tête du marché : vague 2a (un seul axe d'étapes).
- Le contact nommé de l'acheteur dans l'en-tête : Moteur V0 (règle 7 du moteur).
- « confiance N % » et « adéquation N/100 » des cartes de recherche : Moteur V0 (étude, § 8).
- « appel d'offres » sur la vitrine et les pages collectivités : le mot juste de la procédure, il n'est pas banni.
- Au chargement de l'accueil, les premiers pas et « Aucun marché » s'affichent une fraction de seconde avant les
  données (déjà en production). (Le bandeau des cookies qui couvrait le bas du menu est corrigé au § 4.7.)

### 4.7 Relecture de la fin de vague (quatre relectures : navigation, vocabulaire et vérité, démo de pitch, tests et UX)

26 remarques, chacune reproduite (lecture du code, appel des routes, navigateur réel) avant d'être corrigée. Trois
étaient des doublons (anciens noms en bulle, provenances de « Mes preuves », « N/M » de la liste avant dépôt). Une
seule partie est refusée : la référence imprimée dans la convention de groupement (ci-dessous). Test :
`tests/test_reorganisation_v1_relecture.py` (chaque test échouait sur `6fddf13`).

**Anciens noms d'écran encore dits par le serveur.** La recherche textuelle ne voyait pas les chaînes coupées sur deux
lignes ; le garde-fou lit désormais les constantes Python par l'ast, qui fusionne les littéraux adjacents
(`test_aucun_ancien_nom_d_ecran_dans_les_textes_du_serveur`).
- Partenaire qui a un compte, arrivé par le lien (courriel « Votre partie est à valider ») : « rédigez vos parties
  depuis ce compte, dans Mes marchés, onglet « Où je suis partenaire » » (à l'écran et dans le refus 403), le même texte
  que le repli de `redaction-partenaire.js`.
- Mes preuves : « Indiquez le SIRET … dans Mon entreprise, onglet « Identité » » ; provenances « Mon entreprise
  (Identité) » et « Mon profil partenaire (Réseau Adjugo) ».
- « Préparer mes documents » : « générez-la dans « Convention et accords » (page du marché, étape Préparer) ».
- Chemins de l'ancien menu : « Partenaires › Réseau Adjugo › Mon profil partenaire » (courriel du réseau),
  « … › Invitations reçues » (message au chef de file, bulle de l'espace partenaire), « menu Réglages ›
  Administration › Profils du réseau à valider » (courriel à l'administrateur), « Trouver des marchés, onglet
  « Projets à venir » » (courriel de la veille amont, coupée par `PROJETS_A_VENIR=0`).
- Gardé : « Monter le groupement », étape du stepper côté partenaire (vague 2b, § 4.6) ; le dictionnaire de traduction
  du serveur. Liste exacte : `ANCIENS_GARDES`.

**Décision 8.**
- Serveur : « Générée : accords enregistrés 1 sur 3 », « (accords 1 sur 2) », « (analyses : 30 sur 30 ce mois) »,
  « 1 PME capable(s) sur 4 en procédure collective » (collectivités). Garde-fou par l'ast : aucune f-string de phrase en
  « {N}/{M} » ou « {N}/100 » (`test_aucun_n_sur_m_avec_une_barre_dans_les_phrases_du_serveur`, exceptions `NM_GARDES`
  et § 0.3).
- Courriel des alertes : plus de « [72/100] » ; la liste reste triée du plus adapté au moins adapté. Il dit objet,
  acheteur, date limite et lien, et la vitrine le promet ainsi (« compétences attendues » n'y était pas).
- Accueil, « Où vous gagnez / perdez » : « 3 marchés terminés · 2 gagnés sur 3 », « Dépt 49 : 1 sur 1 », segment
  « Seul ou à plusieurs » (« Seul » / « À plusieurs », clés de l'API inchangées), leçons en « 2 gagnés sur 3 ». Les
  barres gardent leur longueur.
- Accueil et Mes marchés : le nombre de l'anneau est dit avec son libellé, « Seul 97 % · Ville de … » ou
  « À plusieurs 100 % · … » (`scoreCourt`) ; la carte de Mes marchés dit « Seul 87 % ».
- Vitrine : « Compétences réunies 1 sur 3 » (puis 2, puis 3), au lieu de 33, 66 et 100 %.
- Compte-rendu PDF du groupement : « 1 sur 2 parts reçues », colonne « Éléments fournis : 3 sur 5 » (part envoyée, lot
  précisé, références, paragraphe du dossier de présentation, qualifications : les drapeaux du suivi), plus aucun %.

**Mots bannis encore visibles.**
- Dossiers rangés : `nomDossier` (`DOSSIERS_AFFICHES`) affiche « CERFA » → « Formulaires officiels », « DCE » →
  « Dossier du marché », « Mémoire technique » → « Dossier de présentation » ; clés stockées inchangées.
- Compte-rendu PDF : « Partenaire du groupement » (plus « Co-traitant »).
- Pièces remises à l'acheteur (déclaration sur l'honneur, DUME, formulaires nationaux) : la référence est celle de
  l'avis lu (« avis BOAMP n° 26-123456 », `reference_consultation`), sinon « À compléter (référence de la consultation
  donnée par l'acheteur) » ; jamais « AO-0001 ».
- Noms de fichiers : le ZIP téléchargé garde le nom donné par le serveur (« Dossier_[marché]_[date].zip », repli
  « Dossier_marche_[n].zip ») ; dossiers du ZIP `01_Formulaires_officiels/`, `formulaires_officiels/`,
  `pieces_partenaires/` (et l'aperçu du dossier commun) ; ZIP sans intitulé : « Adjugo_Dossier_marche_[n] » ;
  titre du PDF d'estimation « Estimation détaillée du prix » ; avertissement « formulaires officiels indisponibles ».
- Collectivités : « PME identifiées via les données publiques (registre Insee, DECP, BODACC) ».
- Démo, page Toiture : « Dossier de présentation — méthodologie étanchéité », « Tableau de prix — décomposition du prix
  global et forfaitaire » (pièces de réponse de l'entreprise fictive ; le PDF rangé suit le nom depuis le § 4.8) ; la
  raison du § 0.3 est corrigée.
- Garde-fou étendu aux générateurs des PDF et du ZIP, chaînes d'un seul mot comprises quand elles commencent par une
  majuscule (`test_generateurs_de_pdf_et_du_zip_sans_mot_banni`).

**Refusé : « Référence du dossier sur Adjugo : AO-0012 » dans la convention de groupement.** La convention est un
texte juridique figé par son empreinte, et sa fraîcheur se contrôle en recalculant le texte à partir des faits
(`is_stale` compare `current_hash` à l'empreinte enregistrée). Changer cette ligne rendrait caduques TOUTES les
conventions déjà générées, en production comme dans la démo (Kerhel « validée par tous »), et chaque membre devrait
revalider : ce n'est pas « seulement les nouvelles versions ». À décider par Eliot avec un nouveau numéro de modèle
(`docs/A_CORRIGER_PAGES_JURIDIQUES_LIBELLES.md`, § 9).

**Décision 9.** Au lecteur d'écran, un badge du réseau « ok » ne dit « vérifié » que pour l'identité (validée par
Adjugo, registre officiel) ; BODACC et DECP disent « constaté à la source ».

**Démo de pitch.**
- Anciens noms en bulle : seulement pour un compte créé avant `REORG_V1_DEPUIS`, jamais la démo ni un compte neuf
  (`transitionVisible`, la même règle que la note « Ce qui a changé ») ; la bulle (i) de l'Accueil, alors vide,
  disparaît.
- Le choix du statut s'appelle « Statut » (en-tête du marché et tiroir ; « Statut mis à jour »), plus « Étape » à
  côté de la barre Lire · Décider · Préparer · Déposer.
- Accueil « À plusieurs » : chaque marché est placé sur la barre de SA page avec la même règle (`etapeDuMarche` :
  statut, dossier lu, étape du groupement). Le serveur renvoie ces trois faits (`barres`, et chaque marché listé) ;
  « Lire » peut donc apparaître, la grille des étapes passe à 4 colonnes ; un marché accessible dit « À décider »,
  « À lire » ou « À préparer ».
- « Trouver des marchés › À venir » : la démo sert quatre fins de contrat fictives, filtrées par département comme le
  radar (acheteurs fictifs de la démo, sans lien, dates toujours à venir ; deux dans le 44 pré-rempli), sans réseau,
  sans IA, sans quota ; la route n'est plus refusée par le garde.

**Tests et UX.**
- La note « Ce qui a changé » se teste à partir de `REORG_V1_DEPUIS` lue dans `app.js` : Eliot peut régler le jour réel
  de mise en ligne sans rendre la suite rouge.
- Bandeau des cookies : effacé tant que le menu est ouvert sur téléphone, à droite du menu sur ordinateur ; le groupe
  « Réglages » répond au clic avant que le bandeau soit fermé (vu dans le navigateur à 375 et 1 000 px).
- Traductions : « Marché » → « Aanbesteding », « Vos marchés à plusieurs, par étape » → « Uw gezamenlijke
  aanbestedingen, per stap » / « Sus licitaciones en agrupación, por etapa », et les autres libellés affichés qui
  disaient encore « opdracht » ; nouveaux : « Statut mis à jour », « Seul ou à plusieurs », « Formulaires officiels »
  (465 → 468 clés). Test de cohérence : tout libellé affiché qui dit « marché » ou « à plusieurs » est traduit avec le
  même mot.
- Le tableau des repères de l'accueil (§ 1.0.3) est de nouveau d'un seul tenant.
- Trouvé en vérifiant dans le navigateur : deux fonctions du bilan, rangées par erreur dans `computed`, cassaient
  l'accueil ; elles sont dans `methods`, et un test le vérifie.

**Vérifié dans un vrai navigateur** (serveur local, base jetable, démo par lien privé, aucun envoi, aucune IA) :
Accueil 1 280 px (pas de bulle à côté d'« Accueil », « 2 gagnés sur 3 », « Seul 97 % · Ville de Trémorvan »,
Kerhel « Déposer » à l'accueil comme sur sa page), bulles de Mes marchés, Partenaires, Réglages sans ancien nom, Mes
marchés (« Seul 87 % », « À plusieurs 100 % »), Toiture et Kerhel (« Statut », dossiers « Dossier du marché »,
« Dossier de présentation », « Chiffrage »), « À venir » (2 fins de contrat dans le 44 pré-rempli), Mes documents ; 375 px clair et sombre
sans défilement horizontal (accueil, Mes marchés, Trouver des marchés, Mes documents, Kerhel) ; bandeau non fermé à
375 px (Réglages › Mon compte s'ouvre) et à 1 000 px (bandeau à droite du menu) ; vitrine 1 280 et 375 px.

**Vérifications** : suite complète verte (2 080 tests ; les 24 du nouveau fichier échouent sur `6fddf13`), SRI
(`scripts/sri_update.py --check`) et `node --check`, gabarits de `app.html` et des composants compilés par Vue sans
erreur, `scripts/i18n_ajouter.py --check` (468 clés).

### 4.8 Contre-relecture de la fin de vague

Trois remarques, chacune reproduite avant d'être corrigée, aucune rejetée. Test :
`tests/test_reorganisation_v1_contre_relecture.py` (ses 8 tests échouent sur `8adfae0`, chacun pour la raison de la
remarque).

**Carte de Mes marchés : la note se coupait.** Mesuré dans un navigateur sur la démo à 1 280 px : « Seul 34 / % »,
« Seul 97 / % », « À / plusieurs / 100 % » (3 cartes sur 7 ; encore 2 à 1 440 px). La note (`.kcard .sc`) ne se coupe
plus (`white-space: nowrap`) ; la ligne de la carte passe à la ligne (`flex-wrap: wrap`) : si la note ne tient pas à
côté de l'acheteur, elle passe entière en dessous, alignée à droite. Vérifié à 1 000, 1 280, 1 440 et 375 px (et 1 280 px
en clair) : chaque note sur une ligne, rien ne déborde de la carte, pas de défilement horizontal.

**Démo : le PDF d'une pièce renommée gardait son ancien titre.** `_put` ne réécrit jamais une clé déjà stockée ; en
production (stockage S3 persistant), le PDF rangé sous `demo/memoire_methodologie.pdf` et `demo/dpgf.pdf` disait
encore « Mémoire technique — … » et « DPGF — … » (reproduit : anciens PDF posés sous ces clés, puis
`ensure_demo(force=True)`). Chaque PDF de la démo est maintenant rangé sous une clé liée à son titre
(`demo/kbis_<empreinte>.pdf`, comme le dossier du marché et sa lecture) : un nom changé range un nouveau PDF, relancer la
démo sans rien changer n'en range aucun. Les anciens fichiers restent dans le stockage, sans plus servir (une
vingtaine de petits PDF). Vérifié dans le navigateur : les deux pièces de Toiture se téléchargent, titre du PDF égal au
nom affiché.

**« Profil entreprise » : l'écran s'appelle Mon entreprise, onglet « Identité ».** La consigne du SIRET disait encore
« profil entreprise » (Partenaires › Réseau Adjugo › Mon profil partenaire › Publication, visible dans la démo), comme
d'autres textes que le garde-fou du § 4.7 ne voyait pas (il cherchait « Profil de l'entreprise »). Corrigé partout où
une personne le lit :
- serveur : condition « SIRET à 14 chiffres renseigné dans Mon entreprise, onglet « Identité » », refus de la
  vérification et de la publication, formulaires officiels et export (« Renseignez votre entreprise dans Mon
  entreprise, onglet « Identité ». »), champs manquants avant un formulaire, avertissement « BLOQUANT — à renseigner dans
  Mon entreprise, onglet « Identité » », manque de la convention (nom du chef de file), registre introuvable ou SIRET
  manquant, « Le SIRET de votre entreprise a changé », adéquation métier sans activité (« vos spécialités dans Mon
  entreprise, onglet « Mes critères » »), journal (« SIRET de l'entreprise modifié (Mon entreprise) ») ;
- écrans : « Reprendre ce que vous avez déjà saisi » de Mes preuves (« Repris de Mon entreprise (onglet « Identité »),
  de votre profil partenaire (Réseau Adjugo) … »), bulle de l'identité du profil partenaire, « Aucune référence dans
  Mon entreprise », publication refusée, paragraphe du dossier de présentation du partenaire (application et espace
  partenaire), administration (« Déclaré dans Mon entreprise ») ; premier pas de l'accueil « Renseignez le nom et le
  SIRET de votre entreprise » (ce que le jalon vérifie ; traduit, 468 → 469 clés).
- Garde-fous : constantes du serveur lues par l'ast et textes visibles des pages et scripts servis, insensibles à la
  casse (« profil entreprise », « profil d'entreprise », « profil de l'entreprise »). Gardés : le dictionnaire de
  traduction du serveur, la consigne envoyée à l'IA (`PROFIL_GARDES`), l'ancien nom de l'onglet « Identité » dans la
  bulle de transition.

**Vérifications** : suite complète verte, SRI (`scripts/sri_update.py --check`) et `node --check`, gabarit de
`app.html` compilé par Vue sans erreur, `scripts/i18n_ajouter.py --check` (469 clés) ; navigateur réel (serveur local,
base jetable, démo par lien privé, réseau sortant coupé, aucune IA) : Mes marchés à 1 000, 1 280, 1 440 et 375 px en
sombre et à 1 280 px en clair, pièces de Toiture, Publication du profil partenaire. Les tests de ce fichier coupent le réseau
(registre simulé absent, connexions sortantes refusées) : sans cela, `GET /api/reseau/profil` de la démo interrogeait
le registre officiel.
