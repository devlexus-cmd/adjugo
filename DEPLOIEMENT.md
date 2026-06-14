# Adjugo — Checklist avant mise en ligne

Légende priorité : 🔴 bloquant · 🟠 important · 🟡 qualité · 🟢 post-lancement

> 📘 **Procédure de mise en prod détaillée : [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)** (Docker Compose / plateforme, reverse proxy, Stripe, cron, vérifs).

---

## 🔴 Sécurité (ne pas déployer sans)

- [ ] **Régénérer TOUS les secrets exposés** ⚠️ À FAIRE PAR TOI : révoquer la clé Anthropic + les clés Stripe (consoles respectives) et en créer de nouvelles — elles ont transité en clair.
- [x] **`SECRET_KEY` JWT** : clé forte générée et posée dans `.env` (placeholder remplacé).
- [x] **`.gitignore`** créé (`.env`, `*.db`, `uploads/`, `venv/`…). _Reste : secrets via gestionnaire de la plateforme en prod, pas de `.env` commité._
- [x] **Endpoints démo protégés** : `/api/pipeline/demo/run` et `/demo` désormais gated par `DEMO_MODE` (404 si off) ; `/api/cotraitants/suggest` exige maintenant l'auth et utilise l'utilisateur connecté.
- [x] **CORS** : piloté par `CORS_ORIGINS` (env), à restreindre au domaine prod.
- [x] **En-têtes de sécurité** : `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS (hors debug) via middleware.
- [x] **Rate limiting** (slowapi) : login 10/min, register 5/min, `pipeline/run` 20/h, `pipeline/demo/run` 10/h, `analysis` 30/h — clé = IP réelle (gère `X-Forwarded-For`). Testé : 429 au-delà du seuil, statics/navigation non impactés. _Prod multi-workers : pointer `RATELIMIT_STORAGE_URI` sur Redis (sinon compteurs par-process)._
- [ ] **Webhook Stripe** : vérification de signature avec le vrai `STRIPE_WEBHOOK_SECRET` live.
- [x] **Upload de documents** : validation type (extensions autorisées) + taille (`MAX_UPLOAD_MB`) en place ; stockage hors webroot via la couche storage.
- [x] **CSP** (Content-Security-Policy) en place : origines verrouillées (`unpkg`, Google Fonts, jsdelivr pour `/docs`), `frame-ancestors`/`base-uri`/`form-action`/`object-src` durcis. `unsafe-eval/inline` requis tant que Vue compile au runtime (sans build). _Reste : HTTPS forcé (reverse proxy)._

## 🔴 Base de données

- [x] **Bascule SQLite (dev) / PostgreSQL (prod)** : `create_all` n'est appelé qu'en SQLite ; en prod c'est Alembic. Il suffit de pointer `DATABASE_URL` sur le Postgres managé (Neon/RDS/Scaleway ou `docker-compose`).
- [x] **Migrations Alembic** en place : `alembic/` + migration initiale `db24559dfd46_initial_schema` couvrant les 10 tables (dont `cotraitants` avec `specialites/codes_cpv/departement` et `matching_criteria_ext`). Testée sur base vierge. Déploiement : `alembic upgrade head` (lancé automatiquement par `entrypoint.sh`).
- [x] **Driver aligné** sur `psycopg2` (config, `docker-compose`, `.env.example`).
- [ ] **Sauvegardes automatiques** + PITR (à configurer côté hébergeur).

## 🔴 Infrastructure & déploiement

- [x] **Dockerfile prod** : multi-workers uvicorn (`WEB_CONCURRENCY`), **sans `--reload`**, utilisateur non-root, migrations au démarrage via `entrypoint.sh`. _(option : passer à gunicorn+UvicornWorker pour le redémarrage gracieux)_
- [x] **Recette reverse proxy + TLS documentée** (Caddy, cf. DEPLOY_GUIDE §5) + `.dockerignore` (exclut `.env`/venv de l'image) + `docker-compose` durci (`env_file`, healthcheck DB, démarrage prod). _Reste : exécuter sur ton serveur + DNS du domaine._
- [x] **Stockage fichiers abstrait (local/S3)** : `app/services/storage.py` — `STORAGE_BACKEND=s3` en prod (AWS/MinIO/Scaleway via `S3_ENDPOINT_URL`), local en dev. Upload **validé** (extension + taille `MAX_UPLOAD_MB`), endpoint **download** ajouté (URL signée S3 / flux local), suppression nettoie le stockage. _Reste : créer le bucket + clés IAM en prod._
- [ ] **Timeouts** : un run pipeline dure ~90 s (3 appels LLM). Régler les timeouts proxy en conséquence **ou** basculer le pipeline en tâche de fond (file/worker) avec suivi de progression.
- [ ] **Healthcheck conteneur** (l'endpoint `/api/health` existe).

## 🟠 Fonctionnel / métier

- [x] **Quotas par plan appliqués** : `app/core/quota.py` compte les analyses IA (reset mensuel auto) et **bloque en 402** sur `/api/pipeline/run` et `/api/analysis/{id}` quand le plan est dépassé — sans déclencher le LLM. Usage exposé via `/api/agent/stats` + barre de progression dans l'UI (vue Agent) + redirection vers l'abonnement.
- [x] **Webhook Stripe fiabilisé** : affectation du plan via `PlanType(...)`, mémorisation du `stripe_customer_id` (pour la résiliation), reset du compteur au passage payant.
- [ ] **Stripe en mode live** ⚠️ À FAIRE : créer les produits/prix en mode **live**, configurer le `STRIPE_WEBHOOK_SECRET` live + l'URL du webhook, tester un cycle complet (souscription → résiliation).
- [x] **Alertes d'expiration par email** : service SMTP (`app/services/email.py`, no-op si non configuré) + scan des documents expirants (escalade 30 j → 7 j → jour J, digest par utilisateur, flags anti-doublon) + endpoint cron sécurisé `POST /api/admin/run-alerts` (`X-Cron-Secret`). Testé. _Reste : configurer le SMTP + planifier le cron quotidien._
- [ ] **Fiabilité pipeline réel** (`/api/pipeline/run`) : gérer les échecs de scraping DCE BOAMP (fallback déjà présent), bornes de tokens/coût par requête.
- [x] **Code mort supprimé** : 10 doublons `.py` top-level (`analysis_v2`, `cerfa_*_v2/v4`, `cotraitants`, `veille`, `checklist`, `criteria_router_v2`…) + 8 `.jsx` non câblés. Import cassé `from app.checklist` corrigé → `app.routers.checklist`. App + tests OK. _Gardés : `seed_demo.py` (seed actif), `grid_tool.py` (calibration CERFA)._ _Cruft à confirmer : dossiers `source/`, `venv$/` (venvs parasites), `myworldcup.fr/` (vide)._

## 🟠 Design / frontend (refonte en cours)

- [x] **Refonte design complète** : design system (tokens clair/sombre, thème système + bascule), **toutes les vues** migrées (sidebar, dashboard, agent, pipeline/drawer, co-traitants+découverte, veille, contacts, documents, factures, entreprise, critères, abonnement). **0 emoji** → 75 icônes Lucide, empty states travaillés, filets 1px, Inter. Vérifié : aucun emoji, aucune variable CSS orpheline.
- [x] **Responsive** : sidebar **off-canvas** sous 860px (bouton menu + backdrop, fermeture auto à la navigation), tables scrollables horizontalement, KPIs 4→2→1 colonnes, drawer plein écran sous 520px, modales adaptées.
- [ ] **Accessibilité WCAG AA** : focus-ring + `aria-label` sur les boutons-icônes faits ; reste audit contrastes complet + navigation clavier des modales.
- [ ] **Épingler les dépendances CDN** : `vue@3` et `lucide@latest` (unpkg) sont en *latest* — figer les versions ou les auto-héberger.
- [ ] **Auto-héberger la police Inter** (Google Fonts = tiers, enjeu RGPD/perf) ou `display=swap` + fallback.
- [ ] **Favicon, titre, meta, OG tags** ; page de connexion soignée.
- [ ] **Page d'accueil / marketing** (`LandingPage.jsx` à câbler ou refaire).

## 🟠 Légal / RGPD (SaaS B2B France)

- [ ] **Mentions légales, CGU, CGV, Politique de confidentialité**.
- [ ] **RGPD** : registre des traitements, bandeau cookies, droit à l'effacement/export, **DPA avec les sous-traitants** (Anthropic, Stripe, hébergeur).
- [ ] **Résidence des données UE** (S3 `eu-west-3` ok ; vérifier les conditions Anthropic pour les données envoyées au LLM).
- [ ] **Attribution des sources publiques** si requis (BOAMP, annuaire-entreprises / SIRENE).

## 🟡 Observabilité & qualité

- [x] **Suivi d'erreurs Sentry** (backend) : activé si `SENTRY_DSN` défini, sinon no-op. _Reste : Sentry côté frontend._
- [x] **Logs structurés** : middleware par requête (méthode/route/statut/durée/request-id) + `X-Request-ID`. _Reste : rétention/agrégation côté hébergeur._
- [ ] **Monitoring uptime** + alertes (UptimeRobot / hébergeur sur `/api/health`).
- [x] **Tests de fumée** (`tests/`, pytest) : 13 tests verts couvrant santé, auth (register/login/me/401), profil, critères, co-traitants CRUD, registre, documents (upload/download/validation), **quota 402**, **rate-limit 429**, mode démo. Lancer : `venv/bin/python -m pytest`. _Reste : couverture pipeline LLM (mock Anthropic) + Stripe._
- [ ] **Test de charge** : pipelines LLM concurrents (latence + coût).
- [ ] **Analytics** respectueux (Plausible/Matomo).

## 🟢 Lancement & post-MEP

- [ ] **Onboarding** : au 1er login, compléter profil entreprise + critères.
- [ ] **Support/contact**, page statut.
- [ ] **Tarification finalisée**, facturation conforme (TVA).
- [ ] **Clés API client** (plan Business) si proposé.
- [ ] **Webhook Stripe en prod** + relances de paiement.
- [ ] **Procédure de restauration** testée (backup → restore).

---

### Top 6 à faire en premier (chemin critique)
1. Régénérer les secrets + vraie `SECRET_KEY`, sortir `.env` du repo.
2. Supprimer les endpoints démo non authentifiés.
3. PostgreSQL + migrations Alembic.
4. S3 pour les documents.
5. Dockerfile prod + TLS + domaine.
6. Quotas par plan + Stripe live + webhook.
