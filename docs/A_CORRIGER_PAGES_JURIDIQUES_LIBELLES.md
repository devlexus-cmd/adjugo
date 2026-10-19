# À corriger par Eliot : libellés faux dans les pages juridiques

**Statut : à valider par Eliot. Rien n'a été modifié dans ces pages.** Les correctifs urgents d'octobre 2026
ont corrigé ces libellés partout dans l'application (écrans, courriels, vitrine). Les pages juridiques
n'ont pas été touchées, comme convenu. Elles disent encore ce qui suit. Les sources sont dans
`docs/legal/*.md`, puis on régénère avec `python scripts/build_legal.py`. `securite.html` n'a pas de
source Markdown : il faut le modifier à la main.

## 1. « Go/No-Go » : l'écran donne maintenant un verdict en pourcentage

- `docs/legal/cgv.md`, l. 23, et `app/static/legal/cgv.html`, l. 63 (article 1) :
  « **Analyse du DCE et scoring Go/No-Go** ».
  Proposition : « **Analyse du DCE et verdict en pourcentage** : analyse des dossiers de consultation et
  évaluation déterministe (barème maison) ».
- `docs/legal/politique-confidentialite.md`, l. 152, et `app/static/legal/confidentialite.html`, l. 101 :
  « Le scoring **Go/No-Go** repose sur un barème déterministe… ».
  Proposition : « Le **verdict en pourcentage** repose sur un barème déterministe… » (le reste sans
  changement).

## 2. « Co-traitants vérifiés » : rien ne prouve qu'un partenaire est « vérifié »

- `docs/legal/cgv.md`, l. 24, et `cgv.html`, l. 63 : « **Co-traitants vérifiés** : identification et
  vérification de partenaires (sources SIRENE/BODACC…) ».
  Proposition : « **Recherche de partenaires** : identification de partenaires à partir des sources
  SIRENE et BODACC, avec signalement d'une procédure collective publiée ».

## 3. « Veille amont » : la fonction est masquée (PROJETS_A_VENIR=0)

- `docs/legal/cgv.md`, l. 25, et `cgv.html`, l. 63 : « **Veille amont** : détection de projets
  d'investissement dans les délibérations open-data… ».
  Proposition : retirer la ligne tant que la vague 1 de l'étude veille n'est pas livrée, ou écrire
  « (fonction en préparation, non disponible à ce jour) ».

## 4. « Aucune donnée inventée » : promesse que l'IA ne peut pas tenir à la lettre

L'étude rédaction le montre : une phrase inventée peut ressortir avec le badge « sourcé ».

- `docs/legal/cgv.md`, l. 28, et `cgv.html`, l. 64 : « règle anti-hallucination : aucune donnée inventée ».
  Proposition : « chaque information factuelle renvoie à sa source ; une information manquante est
  signalée « inconnu » ou « [À compléter] » ; le Client relit chaque fait avant de l'utiliser ».
- `docs/legal/politique-confidentialite.md`, l. 45, et `confidentialite.html`, l. 68 : « aucune donnée
  personnelle n'est inventée ».
  Proposition : « Adjugo ne crée pas de données personnelles : il ne traite que celles issues de sources
  publiques ou de vos documents ».
- `app/static/legal/securite.html`, l. 103 (titre) : « 5. Données réelles, jamais inventées ».
  Proposition : « 5. Données réelles et sourcées ». Le paragraphe qui suit est déjà prudent (« conçu
  pour ne pas présenter de donnée inventée »).

## 5. Rien à corriger

Dans les pages juridiques, on ne trouve ni « Chorus Pro » pour le dépôt d'une offre, ni « compte
gratuit », ni « Tableau de prix (Excel) ».

## 6. Réorganisation de l'interface, vague 0 (19/10/2026) : les autres mots bannis

**Statut : à valider par Eliot. Rien n'a été modifié dans ces pages ni dans le modèle de convention.** L'application,
la vitrine, l'espace partenaire et les courriels ne disent plus « co-traitant », « AO », « mémoire », « CERFA »,
« DPGF », « SIRENE », « cockpit » (contrat : `docs/REORGANISATION_V1.md`, § 0). Les pages juridiques les emploient
encore. Une page juridique peut garder le terme juridique exact : à vous de trancher, ligne par ligne.

### 6.1 « AO », « CERFA », « mémoire technique »

- `docs/legal/cgv.md`, l. 26 (et `cgv.html`) : « production des formulaires **CERFA** (DC1, DC2, DC4, ATTRI1), du DUME
  et d'un **mémoire technique** ». Proposition : « production des formulaires officiels pré-remplis (DC1, DC2, DC4,
  ATTRI1), du DUME et d'une aide à la rédaction du dossier de présentation (mémoire technique) ».
- `docs/legal/cgv.md`, l. 50 (et `cgv.html`) : « chaque **analyse AO** supplémentaire ». Proposition : « chaque analyse
  de marché supplémentaire ».
- `docs/legal/politique-confidentialite.md`, l. 52 (et `confidentialite.html`) : « génération de documents (**CERFA**,
  DUME, **mémoire**) ». Proposition : « génération de documents (formulaires officiels, DUME, dossier de
  présentation) ».
- `app/static/legal/dpa.html`, l. 119 (finalité) et le paragraphe des traitements : « formulaires **CERFA**, DUME,
  **mémoire technique** ». Même proposition. Sans source Markdown : à modifier à la main.
- `docs/legal/mentions-legales.md`, l. 51 (et `mentions-legales.html`) : « modèles de formulaires administratifs
  officiels (**CERFA** DC1, DC2, DC4, ATTRI1, DUME) ». Proposition : « (DC1, DC2, DC4, ATTRI1, DUME) ».
- `app/static/legal/securite.html`, l. 93 : « (paragraphe de **mémoire**) ». Proposition : « (paragraphe du dossier de
  présentation) ».

### 6.2 « co-traitant »

- `docs/legal/politique-confidentialite.md`, l. 38 et 53 (et `confidentialite.html`) : « contacts de **co-traitants** »,
  « Vérification des **co-traitants** ». Proposition : « partenaires (co-traitants) » à la première occurrence, puis
  « partenaires ». Terme juridique exact, à garder entre parenthèses si vous le souhaitez.
- `app/static/legal/dpa.html` : « contacts de **co-traitants** », « vérification de **co-traitants** », « dirigeants et
  contacts des **co-traitants** ». Même proposition.
- La ligne « **Co-traitants vérifiés** » des CGV est déjà au § 2.

### 6.3 « SIRENE »

Nom propre d'une source publique (le répertoire de l'Insee). Dans une page juridique, nommer la source est une
information due aux personnes (art. 14 RGPD) : je propose de **garder** « SIRENE » dans la politique de
confidentialité, le DPA et les mentions légales, et d'écrire seulement « répertoire SIRENE de l'Insee » là où le nom
est seul (`confidentialite.html`, sources ; `securite.html`, l. 104 « registre SIRENE »).

### 6.4 Le modèle de convention de groupement (pas une page, un texte juridique)

`app/services/groupement_convention.py`, l. 636 et 641 : chaque membre y est « **co-traitant (partenaire)** » ou
« mandataire (chef de file) ». C'est le terme juridique, déjà accompagné du mot courant. Le texte d'une convention
générée est figé par son empreinte : le changer demande un nouveau numéro de modèle. **Proposition : garder.**

## 7. Réorganisation de l'interface, vague 1 (menu par rubriques, 19/10/2026) : rien à corriger

Le menu change de noms (« Tableau de bord » devient « Accueil », « Partagé avec moi » devient « Où je suis
partenaire », « Mes groupements » devient « À plusieurs », « Équipe » devient « Collègues », « Plus » devient
« Réglages », le radar devient « À venir »). Recherche faite dans `docs/legal/*.md` et `app/static/legal/*.html` :
aucune page juridique ne cite un de ces écrans. Rien à modifier.

## 8. Réorganisation de l'interface, vague 1 (réunion des chantiers, 19/10/2026)

**Libellés : rien à corriger.** La réunion renomme « Mon appel d'offres » (espace partenaire) en « Le marché », le menu
verrouillé de l'espace partenaire en celui de l'application (Accueil, Mes marchés, Partenaires, Mes documents, Mon
entreprise, Réglages › Collègues), « score du groupement » en « à plusieurs », et « SIRENE » en « registre Insee » sur
les pages collectivités. Recherche faite dans `docs/legal/*.md` et `app/static/legal/*.html` : aucune page juridique
ne cite ces écrans ni ces libellés (les « SIRENE » des pages juridiques sont déjà au § 6.3).

**Affichage sur téléphone (375 px), à corriger par Eliot (non modifié, page juridique) :** deux pages juridiques
élargissent l'écran d'un téléphone, ce qui crée un défilement horizontal :

| Page | Largeur à 375 px | Cause |
|---|---|---|
| `/confidentialite` | 533 px | 2 tableaux (catégories de données, finalités et bases légales) |
| `/securite` | 480 px | 1 tableau |

Proposition : dans le gabarit des pages juridiques (`scripts/build_legal.py`, fonction qui fabrique les tableaux),
entourer chaque tableau d'un `<div style="overflow-x:auto">`, puis régénérer les pages (le texte ne change pas).

## 9. Réorganisation de l'interface, vague 1 (relecture de fin de vague, 19/10/2026)

**Pages juridiques : rien à corriger.** La relecture change des chemins d'écran dans des messages et des courriels
(« Partenaires › Réseau Adjugo › Mon profil partenaire », « Mes marchés, onglet « Où je suis partenaire » », « Mon
entreprise, onglet « Identité » »), le compte-rendu PDF du groupement (« Partenaire du groupement »), la référence
imprimée sur la déclaration sur l'honneur et le DUME (celle de l'avis, plus « AO-0001 »). Recherche faite dans
`docs/legal/*.md` et `app/static/legal/*.html` : aucune page juridique ne cite ces écrans ni ces libellés.

**Le modèle de convention de groupement (texte juridique, non modifié).** `app/services/groupement_convention.py`
écrit dans l'article « Le marché » : « Référence du dossier sur Adjugo : AO-0012 » (mot banni « AO », et un numéro
interne présenté dans une pièce que les membres valident). Le texte d'une convention est contrôlé en le recalculant à
partir des faits : changer cette ligne dans le modèle actuel rendrait caduques toutes les conventions déjà générées
(chaque membre devrait revalider), démo comprise. **Proposition :** au prochain numéro de modèle (`MODELE_TEXTE`, les
conventions existantes gardent le leur), écrire « Référence de la consultation : avis BOAMP n° … » (la référence de
l'avis lu, comme les formulaires officiels), ou « dossier Adjugo n° 0012 » si aucun avis n'est connu, avec la
relecture du conseil prévue pour le modèle.
