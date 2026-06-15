# Compte rendu — session autonome (15/06/2026)

7 chantiers demandés, tous traités, testés et **déployés en production**
(https://adjugo-api-production.up.railway.app). Détail ci-dessous.

## 1. CERFA — croix et champs corrigés ✅
- Bug racine : le « X » était dessiné sur la ligne de base au sommet de la case → il
  sortait **au-dessus**. Réécriture de `_checkbox` pour **centrer le X** dans la case, à
  partir du **centre réel** de chaque case (relevé sur les templates via PyMuPDF).
- Les 8 cases des 4 formulaires (DC1/DC2/DC4/ATTRI1) recalées ; DC4 visait `y=100` au lieu
  des options à `y~140+` (corrigé). Champs section D de DC4 replacés sous leurs libellés.
  ATTRI1 : on coche « engage la société » (personne morale) + dénomination sur sa ligne.
- Vérifié visuellement (rendus PNG) case par case.

## 2. Revue de code ✅
- Audit multi-agents (5 axes, 62 findings) → `docs/CODE_REVIEW.md`.
- Correctifs P1/P2 appliqués : client Anthropic **lazy** (plus d'instanciation à l'import),
  URLs Stripe depuis `APP_BASE_URL` (plus de `localhost` en prod), `pool_recycle` Postgres,
  refus de démarrer en prod avec `SECRET_KEY` par défaut, logs des erreurs auparavant avalées.

## 3. Parité TenderCrunch ✅ (LIVE & testé)
- **Base de connaissances** (`KnowledgeDoc`/`KnowledgeChunk`) : l'entreprise dépose ses
  documents (import multiple = onboarding « Do It For You ») → indexés.
- **RAG souverain** : récupération **BM25 pur Python** (aucun service d'embedding externe,
  aucune clé tierce) → cohérent avec une exigence de souveraineté.
- **Mémoire multi-agents** : extraction des exigences → plan → rédaction **citant la base**
  → contrôle de conformité. Chaque section porte ses **sources** (doc + extrait).
- **Questionnaire RFP/RFI/DDQ** : auto-complétion cellule par cellule, sources citées,
  « À compléter » honnête si non couvert (anti-hallucination vérifié en prod).
- Nouvel onglet front « Base de connaissances ».

## 4. Veille amont approfondie ✅ (LIVE & testé)
- Détection enrichie : **phase** (idée→imminent), **échéance AO estimée**, **financement**
  (DETR/DSIL…), **maturité 0-100** (probabilité qu'un AO suive), **domaine**.
- **Ciblage par domaine** (bâtiment, VRD, réseaux, énergie…) : priorise la détection et
  booste le scoring. Profondeur source accrue.
- Test prod : « rénovation énergétique » → maturité 88 %, phase « financement voté »,
  AO « S2 2026 », financement « DETR » ; voirie non ciblée → 60 %.

## 5. Poids du site ✅
- Réponses déjà **gzippées** par l'edge ; ajout de `GZipMiddleware` en filet.
- `i18n.js` (176 K, 13 langues) et `app.js` passés en **`defer`** → ne bloquent plus le
  premier rendu. App re-testée (boot OK, 0 erreur console).

## 6. Commercialisation ✅
- **Pricing aligné** (décidé) partout : Découverte 0 € · Pro 129 € · Business 199 € ·
  5 €/analyse au-delà · Enterprise sur devis. Quotas inclus : 3 / 20 / 60 analyses.
- Pack légal (mentions légales, CGV, confidentialité RGPD), kit de prospection, plan de
  mise en production → `docs/`. **Dossier de lancement** : `docs/LANCEMENT.md`.

## 7. Autocritique ✅
- `docs/AUTOCRITIQUE.md` : forces/faiblesses/risques honnêtes + comparaison TenderCrunch.

## Ce qui reste À TA MAIN (je ne peux pas le faire)
- **Souveraineté SecNumCloud** : nécessite un hébergeur certifié (contrat) — non automatisable.
  Le RAG est déjà souverain (pas d'embedding externe) ; l'IA reste Anthropic (US) → pour une
  vraie souveraineté LLM, prévoir un modèle hébergé UE. Détail dans `ops/mise-en-production.md`.
- Validation juridique du pack légal, Stripe en live, hébergement UE, SMTP+SPF/DKIM/DMARC,
  rotation des clés, Sentry, sauvegardes (checklist dans `LANCEMENT.md`).

## Repère technique
- 7 commits (cf. `git log`). Migrations de synchro ajoutées pour les nouvelles tables/colonnes.
- 23 tests passent. Tout est poussé sur GitHub et déployé sur Railway.
