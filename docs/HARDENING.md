# Durcissement — réponse à l'audit d'architecture (Gemini)

État au 15/06/2026. Réponse point par point au « bilan d'audit » infrastructure.

## 1. Timeouts HTTP / architecture synchrone ✅ CORRIGÉ
Les générations longues (mémoire ~65 s, **mémoire fusionné ~180 s**, war room) étaient
synchrones → risque de timeout et de worker bloqué. **Désormais asynchrone** :
- table `jobs`, traitement en thread (session DB dédiée), résultat persisté en base ;
- endpoints `memoire`, `merged_memoire`, `warroom` renvoient un `job_id` **instantanément**
  (mesuré : 0,29 s) ; le client interroge `GET /api/jobs/{id}` jusqu'au résultat ;
- polling robuste multi-workers (le résultat est en Postgres, partagé).
- Sections de mémoire rédigées **en parallèle** (latence ÷ ~6).

## 2. RAG « naïf » / perte de hiérarchie juridique ✅ CORRIGÉ
Le découpage par caractères cassait la structure contractuelle (Article 4.2 séparé de
son titre). **Nouveau chunker structurel** : détecte Articles / Titres / sous-clauses
numérotées et **préfixe chaque extrait de son fil d'Ariane** (`[ARTICLE 4 › 4.2 Pénalités] …`).
L'IA ne perd plus le contexte. Fallback paragraphe pour les documents non structurés.

## 3. Isolation des données (multi-tenancy) ✅ PROUVÉ
Toute requête sur la base de connaissances est **strictement bornée par `user_id`**.
Le partage inter-entreprises n'existe **que** via un espace co-traitance dont les membres
ont **explicitement rejoint** (invitation acceptée) ; les `user_id` du RAG multi viennent
toujours de la base (jamais de l'entrée client). **Tests de preuve** (`tests/test_isolation.py`) :
B ne peut extraire les données de A ni par recherche, ni par questionnaire IA ; `retrieve()`
vérifié disjoint entre tenants.

## 4. « Wrapper » / business logic ✅ déjà au-delà
Au-delà d'« upload → extraction → texte » : **remplissage déterministe des CERFA**
(DC1/DC2/DC4/ATTRI1, overlay au pixel), **scoring déterministe et explicable**,
**traçabilité** (chaque ligne générée cite sa source ; sources attribuées par entreprise
en co-traitance), **radar des échéances**, **veille amont**, **War Room**. Chaque génération
est historisée (table `jobs`) → pas d'écrasement silencieux.

## ⚠️ Reste à industrialiser (hors code — infra/contrat)
- **Souveraineté / SecNumCloud** : non réalisable en code. L'hébergement actuel (Railway, US)
  doit migrer vers une **région UE** voire un **hébergeur certifié SecNumCloud** pour le secteur
  public/défense. Étapes dans `ops/mise-en-production.md`. Le RAG est déjà souverain (BM25
  pur Python, aucun embedding externe) ; l'IA reste Anthropic (US) → pour une vraie souveraineté
  LLM, prévoir un modèle hébergé UE.
- Parser DCE volumineux (>150 p.) : l'analyse lit aujourd'hui les premiers ~24 k caractères.
  Prochaine étape : chunker structurellement le DCE et récupérer les sections pertinentes par
  exigence (le chunker structurel est déjà en place, reste à le brancher sur l'analyse).
