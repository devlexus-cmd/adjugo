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
