# Adjugo — Dossier de lancement / commercialisation

> État au 15/06/2026. Document de pilotage du go-to-market. Voir aussi :
> [prospection](go-to-market/prospection.md), [mise en production](ops/mise-en-production.md),
> [autocritique](AUTOCRITIQUE.md), [revue de code](CODE_REVIEW.md), pack légal (`docs/legal/`).

## 1. Positionnement
Adjugo aide les **indépendants, TPE et PME** (BTP & services) à **gagner plus de marchés
publics** : détection des bons AO, analyse Go/No-Go, **veille amont** (projets détectés
avant l'AO), co-traitants vérifiés, et **rédaction sourcée** des réponses (mémoire +
questionnaires) à partir du savoir-faire de l'entreprise. Données réelles, traçables,
zéro invention.

**Différenciateurs** : (1) veille amont sur les délibérations — personne ne le fait ;
(2) RAG à traçabilité absolue (chaque phrase cite sa source) ; (3) scoring déterministe
et explicable, défendable devant un acheteur public ; (4) chaîne complète de la détection
au dossier déposé.

## 2. Offre & prix (validés)
| Palier | Cible | Prix | Inclus |
|---|---|---|---|
| Starter | tous | **0 €** | veille + 2 analyses IA/mois |
| Pro | indé · TPE/PME | **129 €/mo** | 30 analyses/mois, base de connaissances, mémoire IA, CERFA |
| Business | PME · équipes | **199 €/mo** | 100 analyses/mois, multi-utilisateurs, multi-domaines/pays, API |
| À la carte | tous | **5 €/analyse** | au-delà du quota mensuel |
| Enterprise | groupements / grands comptes | **sur devis** | — |

Annuel : 2 mois offerts (cash + rétention). Marge brute par analyse ≈ 90 %.

## 3. Ce qui est construit et EN LIGNE
- ✅ Plateforme live : https://adjugo-api-production.up.railway.app (FastAPI + Vue + Postgres, Railway).
- ✅ 4 agents : sourcing (BOAMP/TED), analyse DCE Go/No-Go, co-traitants (SIRENE/BODACC), veille amont.
- ✅ **Veille amont approfondie** : phase, échéance AO estimée, financement, **maturité (probabilité d'AO)**, ciblage par domaine.
- ✅ **Base de connaissances + RAG sourcé** : mémoire multi-agents (extraction → plan → rédaction citée → conformité) + auto-complétion de questionnaires (RFP/RFI/DDQ).
- ✅ Génération CERFA (DC1/DC2/DC4/ATTRI1) corrigée (croix centrées), DUME, formulaires nationaux.
- ✅ Pricing aligné (landing + quotas), pack légal rédigé, sécurité de base (JWT, CSP, HSTS, rate-limit, gzip).

## 4. À FAIRE avant de facturer (ordre de priorité)
1. **Juridique** : faire valider par un juriste mentions légales / CGV / confidentialité (`docs/legal/`) puis les publier ; compléter les `[À COMPLÉTER]` (SIREN, adresse…).
2. **Hébergement UE / souveraineté** : migrer service + Postgres en région UE (cf. `ops/mise-en-production.md`) — argument décisif pour le secteur public.
3. **Stripe en live** : créer les prix 129 €/199 €, le webhook, la facturation TVA ; tester un paiement bout en bout.
4. **Emails** : SMTP (Brevo/Postmark) + SPF/DKIM/DMARC (sinon les digests partent en spam).
5. **Rotation des clés** exposées (Anthropic/Stripe) + secrets en variables d'env uniquement.
6. **Observabilité** : activer Sentry (SENTRY_DSN) + monitoring `/api/health`.
7. **Sauvegardes** Postgres (PITR) + lockfile de dépendances + tests en CI.

## 5. Go-to-market (résumé — détail dans prospection.md)
- **Canaux** : fédérations (FFB, CAPEB, FNTP), CCI/CMA, réseaux de groupements, experts-comptables, bouche-à-oreille. Pas de PLG pur (cible peu présente sur LinkedIn).
- **Accroche** : mener avec la **veille amont** (« sachez des mois avant vos concurrents ») puis le taux de réussite.
- **Preuves** : décrocher **2-3 pilotes gratuits** pour fabriquer des témoignages avant la prospection à froid.
- **Objectif 30/60/90 j** : pilotes → premiers payants Pro → process de vente répétable.

## 6. Risques à surveiller (cf. AUTOCRITIQUE.md)
- Couverture des données (AO hors BOAMP/TED, DCE derrière plateformes) → être transparent.
- Qualité du mémoire IA (un mémoire générique nuit) → positionner « brouillon accélérateur », l'humain valide.
- Dépendance aux APIs publiques (cache/fallback nécessaires).
- RGPD / hébergement souverain (en cours d'industrialisation).
