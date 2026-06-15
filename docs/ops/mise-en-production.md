# Adjugo — Plan de mise en production / durcissement

> Document opérationnel, étape par étape, pour faire passer Adjugo de la démo
> (Railway région US, SQLite/Postgres de démo, Stripe test, SMTP non configuré)
> à une plateforme **vendable** : hébergée en UE, conforme RGPD, observable,
> sauvegardée et facturée en réel.
>
> **État actuel constaté dans le code** (juin 2026) :
> - En ligne sur `https://adjugo-api-production.up.railway.app` (Railway, **région US**).
> - Abstraction de stockage déjà prête : `app/services/storage.py` gère `local` et `s3`
>   (AWS / MinIO / Scaleway via `S3_ENDPOINT_URL`), URLs présignées incluses.
> - Service email SMTP déjà prêt : `app/services/email.py` (no-op tant que `SMTP_HOST` est vide).
> - Sentry déjà câblé : `init_sentry()` dans `app/main.py`, piloté par `SENTRY_DSN` (vide = off).
> - Sécurité déjà active : CSP + HSTS + en-têtes dans le middleware `security_headers` de `app/main.py`.
> - Rate-limiting via `slowapi`, piloté par `RATELIMIT_STORAGE_URI` (par défaut `memory://`).
> - Cron / tâches : `POST /api/admin/run-alerts`, `/run-tender-alerts`, `/run-amont-alerts`
>   protégés par l'en-tête `X-Cron-Secret == CRON_SECRET` (`app/routers/admin.py`).
> - Healthcheck : `GET /api/health` → `{"status":"ok"}`.
>
> Les variables d'environnement citées existent déjà dans `app/core/config.py` et
> `.env.example`. Ce plan dit **quoi régler** et **dans quel ordre**.

> AVERTISSEMENT : les aspects RGPD, mentions légales, DPA/sous-traitance et conformité
> de facturation sont des **modèles à faire valider par un juriste / expert-comptable**
> avant publication ou mise en production commerciale.

---

## 0. Ordre d'exécution recommandé (vue d'ensemble)

1. **Sécurité d'abord** — faire tourner les clés exposées (Anthropic, Stripe, `SECRET_KEY`) : §5.
2. **Hébergement UE** — migrer service + base Postgres en région UE : §1.
3. **Stockage S3 UE** — basculer `STORAGE_BACKEND=s3` sur un bucket UE : §2.
4. **Emails + délivrabilité** — SMTP transactionnel + SPF/DKIM/DMARC : §3.
5. **Observabilité** — Sentry + uptime + logs : §4.
6. **Fiabilité** — sauvegardes Postgres (PITR), lockfile + CI, cache/fallback sources : §6.
7. **Paiement réel** — Stripe live, TVA, facturation conforme : §7.
8. **Checklist finale « prêt à vendre »** : §8.

---

## 1. Hébergement UE / résidence des données

### 1.1 Pourquoi (ne pas sauter cette étape)

- **RGPD (art. 44+)** : Adjugo traite des données d'entreprises clientes (SIREN/SIRET,
  contacts, documents de marché, parfois données personnelles dans les CERFA/DC1-DC4).
  Héberger ces données aux **États-Unis** déclenche le régime des transferts hors UE
  (clauses contractuelles types, analyse de transfert, exposition au *Cloud Act*).
  En restant **dans l'UE**, on supprime ce risque par construction.
- **Crédibilité secteur public** : les acheteurs publics et les PME du BTP/services
  attendent une **résidence des données en UE/France**. C'est un argument commercial
  direct (souvent une exigence dans les clauses RGPD des clients) et un futur point
  d'attention pour une qualification type **SecNumCloud** sur les gros comptes.
- **Latence** : utilisateurs FR/UE → région UE = latence plus faible.

### 1.2 Options (du plus rapide au plus souverain)

| Option | Effort | Résidence | Souveraineté | Commentaire |
|---|---|---|---|---|
| **A. Railway région EU** | Faible | UE (Amsterdam, AWS `eu-*`) | Moyenne (sous-jacent AWS US-corp) | Le plus rapide : on garde le même outillage. |
| **B. Clever Cloud** (FR) | Moyen | France | **Élevée** (acteur FR, Paris/RBX) | PaaS FR, add-on Postgres managé + PITR, Git push. Bon compromis « vendable secteur public ». |
| **C. Scaleway** (FR) | Moyen-élevé | France (Paris) | **Élevée** (acteur FR) | Serverless Containers + Managed Database Postgres + Object Storage UE, même fournisseur que le S3. |
| **D. OVHcloud** (FR/UE) | Élevé | France/UE | **Élevée** (acteur FR, candidat SecNumCloud) | Public Cloud (Managed K8s / instances) + Managed Postgres + Object Storage. Le plus « souverain », le plus de travail. |

**Recommandation pragmatique** : commencer par **A (Railway EU)** pour décrocher la
résidence UE en une journée, puis viser **B (Clever Cloud)** ou **C (Scaleway)** quand
le premier gros client public l'exige (argument souveraineté FR + facturation en euros).

### 1.3 Impact à connaître AVANT de migrer

- **Railway ne « déplace » pas une région** : il faut **recréer le service et le volume/Postgres**
  dans la nouvelle région, puis **redéployer**. C'est une **migration de données**, pas un toggle.
- L'URL publique change → mettre à jour `CORS_ORIGINS`, les `success_url`/`cancel_url` Stripe
  (cf. §7), les webhooks Stripe, le DNS de votre domaine, et l'endpoint surveillé en uptime.
- Prévoir une **courte fenêtre de maintenance** (lecture seule) pendant le dump/restore.

### 1.4 Option A — Railway région EU (étapes concrètes)

1. **Créer un nouvel environnement / projet en région EU** dans Railway
   (à la création du service, choisir une région `EU West / Amsterdam`).
2. **Provisionner un nouveau Postgres EU** (plugin Postgres Railway, région EU).
3. **Dump de la base actuelle (US) puis restore vers la base EU** :
   ```bash
   # 1) Récupérer l'URL de la base SOURCE (US) et de la CIBLE (EU) depuis Railway
   #    (variable DATABASE_URL de chaque service — au format postgresql://...)

   # 2) Dump complet (custom format, le plus robuste)
   pg_dump --no-owner --no-privileges -Fc \
     "postgresql://USER:PWD@HOST_US:PORT/railway" \
     -f adjugo_us.dump

   # 3) Restore dans la base EU
   pg_restore --no-owner --no-privileges --clean --if-exists \
     -d "postgresql://USER:PWD@HOST_EU:PORT/railway" \
     adjugo_us.dump

   # 4) Vérifier le nombre de lignes des tables clés
   psql "postgresql://USER:PWD@HOST_EU:PORT/railway" \
     -c "SELECT 'users', count(*) FROM users UNION ALL SELECT 'projects', count(*) FROM projects;"
   ```
   > Le schéma sera de toute façon (re)convergé par `alembic upgrade head` au démarrage
   > (voir `entrypoint.sh`), mais le dump/restore préserve les **données**.
4. **Reporter toutes les variables d'environnement** sur le service EU
   (cf. `.env.example` ; ne **jamais** committer les vraies valeurs). Pointer
   `DATABASE_URL` vers la **base EU**.
5. **Déployer** le service EU (build Docker, l'`entrypoint.sh` lance les migrations puis `uvicorn`).
6. **Brancher le domaine** sur le service EU, valider `/api/health`, puis
   **décommissionner** l'ancien service US.

### 1.5 Option B/C/D — migration vers un hébergeur FR (canevas commun)

L'application est conteneurisée (`Dockerfile` + `entrypoint.sh`), donc portable :

1. **Provisionner un Postgres managé UE/FR avec PITR** chez la cible
   (Clever Cloud Postgres, Scaleway Managed Database for PostgreSQL, ou OVH Managed Postgres).
2. **Migrer les données** avec le `pg_dump`/`pg_restore` du §1.4 (même procédure).
3. **Déployer le conteneur** :
   - Clever Cloud : application Docker, `git push clever main`, add-on Postgres lié.
   - Scaleway : pousser l'image vers le **Container Registry** puis déployer en
     **Serverless Containers** (port `8000`), base = Managed Database.
   - OVH : Managed Kubernetes ou instance + Docker, base = Managed Postgres.
4. **Variables d'environnement** : recopier celles de `.env.example` côté plateforme.
5. **Stockage** : pointer S3 vers un bucket **UE** (cf. §2).
6. **Domaine + TLS + DNS**, puis bascule et décommission de l'ancien.

> Astuce : garder Railway EU en *staging* et l'hébergeur FR en *production* est un
> schéma sain le temps de stabiliser.

---

## 2. Stockage des fichiers : passer de « local » à S3 (UE)

L'abstraction existe déjà dans `app/services/storage.py` (sélection par `STORAGE_BACKEND`),
avec URLs présignées et compatibilité AWS / MinIO / **Scaleway** (via `S3_ENDPOINT_URL`).
Il ne reste qu'à **configurer** un bucket UE et basculer la variable.

### 2.1 Pourquoi quitter le stockage local

- Le stockage local (`uploads/`) **disparaît à chaque redéploiement** sur un PaaS sans
  volume persistant, et **ne tient pas** en multi-instances. Inacceptable pour des DCE/CERFA clients.
- S3 = durabilité, sauvegarde, URLs présignées (téléchargement direct, sans transiter par l'API).

### 2.2 Option recommandée : Scaleway Object Storage (Paris, FR)

1. Créer un bucket **privé** `adjugo-documents` en région `fr-par`.
2. Créer une **clé API** (Access Key / Secret Key) avec accès à ce bucket uniquement.
3. Régler les variables :
   ```bash
   STORAGE_BACKEND=s3
   S3_BUCKET=adjugo-documents
   S3_REGION=fr-par
   S3_ENDPOINT_URL=https://s3.fr-par.scw.cloud
   AWS_ACCESS_KEY_ID=<scaleway-access-key>
   AWS_SECRET_ACCESS_KEY=<scaleway-secret-key>
   ```

### 2.3 Variante : AWS S3 région Paris (`eu-west-3`)

```bash
STORAGE_BACKEND=s3
S3_BUCKET=adjugo-documents
S3_REGION=eu-west-3
S3_ENDPOINT_URL=            # vide = AWS natif
AWS_ACCESS_KEY_ID=<aws-access-key>
AWS_SECRET_ACCESS_KEY=<aws-secret-key>
```

### 2.4 Réglages bucket obligatoires (les deux cas)

- **Accès public bloqué** (bucket privé) : on sert uniquement par **URL présignée**
  (`S3Storage.url()` génère un lien expirant, 3600 s par défaut).
- **Chiffrement au repos activé** (SSE).
- **Versioning activé** (récupération en cas de suppression/écrasement accidentel).
- **Politique de cycle de vie** : suppression auto des objets orphelins/anciens si besoin
  (et cohérent avec la durée de conservation RGPD à définir avec le juriste).
- **CORS du bucket** limité à l'origine de l'app (`https://app.adjugo.fr`).

> Migration des fichiers déjà uploadés (dossier `uploads/`, ex. `uploads/1/...`, `uploads/7/...`) :
> ```bash
> # Scaleway/AWS : copier l'arborescence locale vers le bucket, en conservant les clés
> aws s3 cp ./uploads/ s3://adjugo-documents/ --recursive \
>   --endpoint-url https://s3.fr-par.scw.cloud   # (retirer --endpoint-url pour AWS natif)
> ```
> Les clés en base (`key`) sont relatives → elles restent valides après copie.

---

## 3. Emails transactionnels & veille : SMTP + délivrabilité

Le service `app/services/email.py` envoie déjà en SMTP (STARTTLS) et est **no-op**
tant que `SMTP_HOST`/`SMTP_USER` sont vides. Il faut un **fournisseur d'emailing** et
**configurer le DNS** du domaine pour que les mails arrivent (alertes veille AO/amont,
expiration de documents, comptes).

### 3.1 Choisir un fournisseur (relais SMTP)

| Fournisseur | Résidence | Note |
|---|---|---|
| **Brevo** (ex-Sendinblue, FR) | UE/FR | Bon choix « souverain », SMTP simple, free tier. |
| **Postmark** | US | Excellente délivrabilité transactionnelle (US — vérifier l'acceptabilité RGPD). |
| **Amazon SES** (`eu-west-3`) | UE | Bon marché à l'échelle, endpoint SMTP UE. |

**Recommandation** : **Brevo** (résidence UE, cohérent avec l'argument souveraineté).

### 3.2 Variables SMTP (exemple Brevo)

```bash
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<identifiant-smtp-brevo>          # souvent l'email/login SMTP fourni
SMTP_PASSWORD=<clé-smtp-brevo>              # clé SMTP, PAS le mot de passe du compte
SMTP_FROM=Adjugo <no-reply@adjugo.fr>
SMTP_TLS=true
```

> Variante **SES (`eu-west-3`)** : `SMTP_HOST=email-smtp.eu-west-3.amazonaws.com`,
> `SMTP_USER`/`SMTP_PASSWORD` = identifiants SMTP SES (≠ clés API IAM), domaine vérifié + sorti du sandbox.

### 3.3 Délivrabilité : SPF / DKIM / DMARC (DNS du domaine `adjugo.fr`)

Sans ces enregistrements, les mails partent en spam ou sont rejetés. **Exemples** —
les valeurs exactes (sélecteur DKIM, host) sont **fournies par votre fournisseur** :

- **SPF** (TXT sur le domaine racine) — autorise le fournisseur à expédier pour vous :
  ```dns
  ; Brevo
  adjugo.fr.   IN TXT  "v=spf1 include:spf.brevo.com mx ~all"
  ; SES (variante)  →  include:amazonses.com
  ; Postmark (variante)  →  include:spf.mtasv.net
  ```
  > Un seul enregistrement SPF par domaine : fusionner les `include:` si plusieurs expéditeurs.

- **DKIM** (CNAME ou TXT, selon le fournisseur — sélecteur fourni par lui) — signe les mails :
  ```dns
  ; Brevo : 2 enregistrements DKIM/Brevo-code fournis dans le panneau (à recopier tels quels)
  brevo1._domainkey.adjugo.fr.  IN CNAME  b1.adjugo-fr.dkim.brevo.com.
  brevo2._domainkey.adjugo.fr.  IN CNAME  b2.adjugo-fr.dkim.brevo.com.

  ; SES (variante) : 3 CNAME du type
  ; <token1>._domainkey.adjugo.fr. IN CNAME <token1>.dkim.amazonses.com.
  ```

- **DMARC** (TXT sur `_dmarc`) — politique + reporting :
  ```dns
  ; Démarrer en p=none (observation) puis durcir vers quarantine, puis reject
  _dmarc.adjugo.fr.  IN TXT  "v=DMARC1; p=none; rua=mailto:dmarc@adjugo.fr; fo=1; adkim=s; aspf=s"
  ; Après ~2 semaines sans incident :
  ; "v=DMARC1; p=quarantine; rua=mailto:dmarc@adjugo.fr; pct=100; adkim=s; aspf=s"
  ; Cible finale : p=reject
  ```

### 3.4 Vérification

```bash
dig +short TXT adjugo.fr               # doit montrer le SPF
dig +short TXT _dmarc.adjugo.fr        # doit montrer le DMARC
dig +short CNAME brevo1._domainkey.adjugo.fr   # DKIM (adapter au sélecteur réel)
```
- Envoyer un mail de test à `check-auth@verifier.port25.com` ou utiliser **mail-tester.com**
  (viser un score 10/10 : SPF=pass, DKIM=pass, DMARC=pass).
- Vérifier dans le panneau du fournisseur que le **domaine est authentifié** avant d'augmenter le volume.

### 3.5 Côté application

- Une fois `SMTP_HOST` rempli, `is_enabled()` passe à `True` et les alertes partent réellement.
- Brancher la planification réelle de la veille via les endpoints cron (§ admin) :
  ```bash
  # Quotidien — expiration de documents, veille AO, veille amont
  curl -fsS -X POST https://api.adjugo.fr/api/admin/run-alerts        -H "X-Cron-Secret: $CRON_SECRET"
  curl -fsS -X POST https://api.adjugo.fr/api/admin/run-tender-alerts -H "X-Cron-Secret: $CRON_SECRET"
  curl -fsS -X POST https://api.adjugo.fr/api/admin/run-amont-alerts  -H "X-Cron-Secret: $CRON_SECRET"
  ```
  Planifier via le cron de l'hébergeur (Railway Cron / Clever Cron / cron système).
  `CRON_SECRET` doit être une vraie valeur aléatoire (`openssl rand -hex 32`).

---

## 4. Observabilité : Sentry, uptime, logs

### 4.1 Sentry (déjà câblé)

`init_sentry()` est appelé au démarrage (`app/main.py`) ; il s'active dès que `SENTRY_DSN`
est renseigné.

```bash
SENTRY_DSN=https://<clé>@<org>.ingest.de.sentry.io/<projet>   # ingest .de = région UE de Sentry
ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1     # 10 % de traces de perf ; monter/baisser selon le volume
LOG_LEVEL=INFO
```
- Choisir l'**organisation Sentry en région UE** (`*.ingest.de.sentry.io`) pour rester cohérent RGPD.
- Vérifier la remontée d'erreurs avec un événement de test après déploiement.

### 4.2 Monitoring uptime

- Surveiller **`GET https://api.adjugo.fr/api/health`** (réponse `{"status":"ok"}`) toutes les 1–5 min
  avec un service externe (UptimeRobot, Better Stack/Better Uptime, Healthchecks.io — privilégier
  un endpoint UE).
- Alerter par email/Slack en cas d'indisponibilité.
- Optionnel : ajouter à terme un `/api/health/ready` qui teste la connexion **DB** et **S3**
  (le `/api/health` actuel est un simple *liveness*, il ne vérifie pas les dépendances).
- Brancher un **monitor cron** (« dead man's switch », ex. Healthchecks.io) sur les jobs
  d'alertes du §3.5 : si le cron quotidien ne « ping » pas, on est prévenu.

### 4.3 Logs

- Les logs sont déjà structurés (`setup_logging()` + middleware `request_logger`).
- En PaaS : conserver/centraliser les logs (rétention de la plateforme, ou export vers
  Better Stack Logs / Loki).
- **Ne jamais logger** de secret ni de contenu sensible de document. Vérifier que les
  réglages Sentry **scrubbent** les données personnelles (PII).

---

## 5. Sécurité : rotation des secrets, variables d'env, en-têtes, rate-limit

### 5.1 Rotation des clés (À FAIRE EN PREMIER — tout secret ayant existé en démo est compromis)

> Un `.env` réel a existé localement et des clés de démo ont pu transiter. **On tourne tout.**

1. **Anthropic** : révoquer la clé existante dans la console Anthropic, en générer une
   nouvelle, la mettre **uniquement** en variable d'env `ANTHROPIC_API_KEY` (jamais en repo).
2. **Stripe** : faire **rouler** (*roll*) la clé secrète depuis le Dashboard Stripe
   (et basculer en clés **live**, cf. §7). Régénérer le `STRIPE_WEBHOOK_SECRET` à la
   (re)création du webhook.
3. **`SECRET_KEY` (JWT)** : régénérer (`openssl rand -hex 32`).
   > Effet de bord : **invalide tous les JWT existants** → tout le monde se reconnecte.
   > C'est voulu lors d'un durcissement.
4. **`CRON_SECRET`** : `openssl rand -hex 32`.
5. **Mot de passe Postgres** : non-trivial (le `adjugo_password` de `docker-compose.yml`
   est un placeholder de démo — **interdit en prod**).
6. **Clés S3/SMTP** : créées neuves, à portée minimale (un bucket / l'envoi seulement).
7. **Purge de l'historique Git** : vérifier qu'aucun secret réel n'est committé.
   ```bash
   git log -p -- .env                 # doit être vide : .env est ignoré (.gitignore)
   git ls-files | grep -E '\.env$'    # ne doit RIEN retourner
   # Si un secret a fui dans l'historique : le révoquer (déjà fait ci-dessus) ET nettoyer
   # l'historique (git filter-repo / BFG) avant de rendre le repo public.
   ```

### 5.2 Secrets en variables d'environnement

- Tous les secrets vivent dans le **gestionnaire de variables de l'hébergeur**
  (Railway Variables / Clever Cloud env / Scaleway secrets), jamais dans le repo.
- `.gitignore` exclut déjà `.env`, `*.db`, `uploads/` — bon. Ne committer que `.env.example`.
- Principe du moindre privilège pour chaque clé (S3 = un bucket, SMTP = envoi seul, etc.).

### 5.3 En-têtes HTTP (déjà actifs — vérifier en prod)

Le middleware `security_headers` envoie déjà **CSP**, **HSTS** (`max-age=31536000; includeSubDomains`,
hors DEBUG), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, anti-cache sur l'app.

- **Vérifier que `DEBUG=false`** en prod (sinon HSTS n'est pas envoyé). `DEBUG` est `False`
  par défaut dans `config.py` — ne pas le passer à `true`.
- **Restreindre `CORS_ORIGINS`** à la (aux) seule(s) origine(s) front réelle(s) :
  ```bash
  CORS_ORIGINS=https://app.adjugo.fr
  ```
- **`DEMO_MODE=false`** en prod (sinon des endpoints publics sans auth restent ouverts,
  et le garde-fou cron se relâche — cf. `app/routers/admin.py`).
- Objectif moyen terme : **build du front** pour retirer `unsafe-inline`/`unsafe-eval`
  de la CSP (commentaire déjà présent dans `app/main.py`).

### 5.4 Rate-limiting (Redis si multi-instances)

`RATELIMIT_STORAGE_URI` vaut `memory://` par défaut. Or `entrypoint.sh` lance
`uvicorn --workers ${WEB_CONCURRENCY:-4}` → **4 workers** : un store `memory://` est
**par-processus**, donc le rate-limit est incohérent (chaque worker compte séparément).

- **Dès qu'il y a >1 worker ou >1 instance**, utiliser **Redis** (UE) :
  ```bash
  RATELIMIT_STORAGE_URI=redis://:<password>@<host-redis-eu>:6379/0
  ```
  (Railway Redis EU, Scaleway/Upstash Redis région UE, ou add-on Redis Clever Cloud.)
- Alternative simple en attendant : forcer `WEB_CONCURRENCY=1` et scaler par instances
  derrière un proxy (moins performant — préférer Redis).

---

## 6. Fiabilité : sauvegardes, lockfile + CI, pannes des sources externes

### 6.1 Sauvegardes Postgres (PITR)

- Utiliser un **Postgres managé avec PITR** (Railway Postgres, Clever Cloud, Scaleway
  Managed Database, OVH Managed Postgres) plutôt que le `docker-compose.yml` de démo
  (qui n'a **aucune sauvegarde**).
- Activer les **backups automatiques quotidiens** + **PITR** (rétention recommandée 7–30 j).
- **Tester une restauration** au moins une fois (un backup non testé n'existe pas).
- Sauvegarde logique de secours, périodique, vers le S3 UE :
  ```bash
  pg_dump --no-owner --no-privileges -Fc "$DATABASE_URL" \
    | aws s3 cp - "s3://adjugo-backups/pg/adjugo-$(date +%F).dump" \
        --endpoint-url https://s3.fr-par.scw.cloud
  ```
  (bucket `adjugo-backups` séparé, privé, chiffré, cycle de vie 30 j).

### 6.2 Lockfile de dépendances + tests en CI

**Problème** : `requirements.txt` est épinglé en version mais **sans hash** (pas de lock
reproductible). Des tests existent (`tests/`, `pytest`) mais **rien ne les exécute en CI**.

1. **Geler les dépendances avec hashes** (reproductibilité + intégrité) via `pip-tools` :
   ```bash
   pip install pip-tools
   # requirements.txt actuel devient l'entrée -> on génère un lock figé
   pip-compile --generate-hashes --output-file=requirements.lock.txt requirements.txt
   ```
   Puis, dans le `Dockerfile`, installer depuis le lock :
   ```dockerfile
   COPY requirements.lock.txt .
   RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt
   ```
2. **GitHub Actions** — lint + tests à chaque push/PR. Créer `.github/workflows/ci.yml` :
   ```yaml
   name: CI
   on:
     push: { branches: [main] }
     pull_request:
   jobs:
     test:
       runs-on: ubuntu-latest
       services:
         postgres:
           image: postgres:16
           env:
             POSTGRES_USER: adjugo
             POSTGRES_PASSWORD: adjugo
             POSTGRES_DB: adjugo_test
           ports: ["5432:5432"]
           options: >-
             --health-cmd "pg_isready -U adjugo" --health-interval 5s
             --health-timeout 3s --health-retries 10
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: { python-version: "3.12" }
         - run: pip install --require-hashes -r requirements.lock.txt
         - name: Tests
           env:
             DATABASE_URL: postgresql+psycopg2://adjugo:adjugo@localhost:5432/adjugo_test
             SECRET_KEY: ci-secret-not-prod
             DEMO_MODE: "false"
           run: pytest -q
         - name: Audit de sécurité des deps
           run: pip install pip-audit && pip-audit -r requirements.lock.txt || true
   ```
   > Les tests actuels tournent sur SQLite (`test_adjugo.db`) ; cette CI ajoute en plus
   > une vérif sur Postgres, proche de la prod.
3. **Branch protection** sur `main` : exiger que la CI passe avant merge.

### 6.3 Pannes des sources externes (BOAMP / TED / SIRENE / BODACC / délibérations)

**Constat** : les clients (`app/sourcing/sources/*.py`) ont des **timeouts** (8–28 s) et
remontent l'erreur, mais **aucun cache ni fallback** → si BOAMP/TED tombe, la recherche
échoue et l'UX se dégrade. La règle anti-hallucination interdit d'inventer : on doit donc
**dégrader proprement**, pas masquer.

À mettre en place :

1. **Cache court à TTL** des réponses externes (par jeu de critères), p. ex. 10–30 min,
   pour absorber les coups de mou et réduire la charge sur les API publiques.
   - Mono-instance : cache mémoire à TTL.
   - Multi-instances : **Redis** (réutiliser le Redis du §5.4) comme cache partagé.
2. **Retry léger avec backoff** sur erreurs réseau/5xx/429 (1–2 tentatives, jitter),
   sans dépasser les budgets de timeout existants.
3. **Dégradation gracieuse par source** : si une source échoue, **renvoyer les résultats
   des autres** + un indicateur « source X indisponible » (au lieu d'une erreur globale).
   Conserver l'invariant : pas de données inventées, on affiche « inconnu / source indisponible ».
4. **Servir le dernier cache valide** (stale-on-error) quand la source est down, en
   **affichant la date** de la donnée (cohérent avec la traçabilité source+date+lien).
5. **Circuit breaker** simple : après N échecs consécutifs d'une source, la court-circuiter
   quelques minutes pour ne pas bloquer les requêtes.
6. **Journaliser** chaque indisponibilité (déjà `logger.warning(...)` dans les clients) et
   la remonter à Sentry pour la suivre.

> Idem pour l'**API Claude** (`app/services/llm.py`) : gérer les `429`/`5xx`/timeouts avec
> retry+backoff et un message d'erreur clair, sans jamais fabriquer de contenu de substitution.

---

## 7. Paiement : passage de Stripe test → live

**Constat** : Stripe fonctionne en **clés test**. Le webhook gère
`checkout.session.completed` et `customer.subscription.deleted` (`app/routers/stripe_pay.py`).
**Bugs/écarts à corriger avant le live** :
- `success_url` / `cancel_url` / `return_url` sont **codés en dur sur `http://localhost:5173`**
  → à remplacer par l'URL de prod **avant** d'activer le live (sinon le client est renvoyé en local).
- Pas de **TVA** configurée (Stripe Tax) ni de **n° de facture conforme**.
- Webhook sans **idempotence** explicite ni vérification de doublon d'event.

### 7.1 Créer les produits / prix en mode **live**

Dans le Dashboard Stripe (bascule **Live**), créer 2 produits avec prix récurrents mensuels TTC/HT
selon votre régime (cf. §7.4) :

- **Adjugo Pro** — `129 €/mois` → récupérer le `price_...` live.
- **Adjugo Business** — `199 €/mois` → récupérer le `price_...` live.
- **Analyse AO supplémentaire** — `5 €` à l'unité (overage, déjà géré côté app via
  `overage_enabled` / `OVERAGE_PRICE`). Modéliser en *metered* ou en facture à l'usage.
- **Enterprise / groupements** : sur-devis → facturation manuelle (Stripe Invoicing).

Renseigner :
```bash
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_PRICE_PRO=price_live_pro_xxx
STRIPE_PRICE_BUSINESS=price_live_business_xxx
```

### 7.2 Corriger les URLs de redirection (code)

Remplacer les `http://localhost:5173` codés en dur dans `app/routers/stripe_pay.py`
par l'URL de prod, idéalement via une variable d'env (ex. `APP_PUBLIC_URL=https://app.adjugo.fr`) :
- `success_url = f"{APP_PUBLIC_URL}/?payment=success"`
- `cancel_url  = f"{APP_PUBLIC_URL}/?payment=cancel"`
- `return_url  = f"{APP_PUBLIC_URL}/"` (portail de facturation)

### 7.3 Webhook live

1. Créer un **endpoint webhook live** : `https://api.adjugo.fr/api/stripe/webhook`,
   événements `checkout.session.completed`, `customer.subscription.deleted`
   (ajouter `customer.subscription.updated`/`invoice.payment_failed` pour gérer
   changements de plan et impayés).
2. Copier le **signing secret** live :
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_live_xxx
   ```
   > Le code rejette déjà le webhook si la signature est absente quand le secret est défini
   > — **ne jamais** laisser `STRIPE_WEBHOOK_SECRET` vide en prod.
3. Ajouter une **idempotence** : stocker l'`event.id` traité et ignorer les rejeux
   (Stripe peut renvoyer le même event).
4. Tester avec le CLI Stripe avant la bascule :
   ```bash
   stripe listen --forward-to https://api.adjugo.fr/api/stripe/webhook
   stripe trigger checkout.session.completed
   ```

### 7.4 TVA & facturation conforme (faire valider par l'expert-comptable)

- **TVA** : activer **Stripe Tax** (ou paramétrer manuellement la TVA FR 20 %).
  Décider HT vs TTC pour l'affichage des prix (129/199 €) selon votre statut.
- **Mentions légales de facture** (obligatoires FR) : raison sociale et adresse de
  l'éditeur, **SIREN/SIRET**, **n° TVA intracommunautaire**, numéro de facture séquentiel,
  date, désignation, montant HT/TVA/TTC, conditions de paiement. Stripe Invoicing gère
  la numérotation et l'archivage.
- **B2B intra-UE** : collecter et **valider le n° de TVA** du client (autoliquidation le cas
  échéant) — l'app a déjà un client **VIES** (`app/sourcing/sources/vies.py`) réutilisable.
- **Éditeur à compléter** : `[À COMPLÉTER : raison sociale / forme juridique]`,
  `[À COMPLÉTER : SIREN/SIRET]`, `[À COMPLÉTER : n° TVA intracommunautaire]`,
  `[À COMPLÉTER : adresse du siège]`. Email contact connu : `viegaseliot1@gmail.com`.
- **CGV / abonnement** : politique de résiliation, remboursement, reconduction —
  **modèle à faire valider par un juriste avant publication**.

---

## 8. Checklist finale « prêt à vendre » (par ordre de priorité)

### P0 — Bloquant (ne pas vendre sans)
- [ ] **Secrets tournés** : Anthropic, Stripe (live), `SECRET_KEY`, `CRON_SECRET`, mot de passe Postgres, clés S3/SMTP (§5.1).
- [ ] **Aucun secret dans Git** : `git ls-files | grep -E '\.env$'` vide ; historique vérifié (§5.1).
- [ ] **`DEMO_MODE=false`** et **`DEBUG=false`** en prod (§5.3).
- [ ] **`CORS_ORIGINS`** restreint à `https://app.adjugo.fr` (§5.3).
- [ ] **Hébergement + base en région UE/FR** ; ancien service US décommissionné (§1).
- [ ] **Stockage S3 UE** (`STORAGE_BACKEND=s3`, bucket privé chiffré versionné) + fichiers migrés (§2).
- [ ] **Postgres managé avec backups + PITR**, restauration **testée** (§6.1).
- [ ] **Stripe en live** : produits 129 €/199 €, prix renseignés, **URLs de redirection corrigées** (plus de `localhost`), webhook live + signature vérifiée (§7).

### P1 — Important (sous quelques jours)
- [ ] **Emails opérationnels** : SMTP configuré + **SPF/DKIM/DMARC** validés (mail-tester ≈ 10/10) (§3).
- [ ] **Crons d'alertes planifiés** (run-alerts / tender / amont) avec `X-Cron-Secret` + dead-man's-switch (§3.5, §4.2).
- [ ] **Sentry actif** (DSN région UE), événement de test reçu (§4.1).
- [ ] **Uptime monitoring** sur `/api/health` avec alerte (§4.2).
- [ ] **Rate-limit en Redis** si >1 worker/instance (`RATELIMIT_STORAGE_URI=redis://…`) (§5.4).
- [ ] **Lockfile à hashes** (`requirements.lock.txt`) + Dockerfile en `--require-hashes` (§6.2).
- [ ] **CI GitHub Actions** (tests + `pip-audit`) verte, **branch protection** sur `main` (§6.2).
- [ ] **TVA + facturation conforme** (Stripe Tax, mentions légales, n° TVA) validées par l'expert-comptable (§7.4).

### P2 — Durcissement / conformité (avant montée en charge)
- [ ] **Cache + retry + fallback** sur sources externes (BOAMP/TED/SIRENE/BODACC/délibérations) + Claude (§6.3).
- [ ] **`/api/health/ready`** vérifiant DB + S3 (§4.2).
- [ ] **CSP durcie** (retirer `unsafe-inline`/`unsafe-eval` via build front) (§5.3).
- [ ] **Idempotence webhook Stripe** + gestion `subscription.updated` / `payment_failed` (§7.3).
- [ ] **Backup logique Postgres vers S3** planifié et testé (§6.1).
- [ ] **Rétention/scrub PII** : logs sans données sensibles, durées de conservation RGPD définies (§4.3, §2.4).
- [ ] **Mentions légales / CGV / Politique de confidentialité / DPA** publiées —
      `[À COMPLÉTER : éditeur]` — **modèles à faire valider par un juriste avant publication**.
- [ ] **Registre des traitements RGPD** + liste des **sous-traitants** (hébergeur UE, Stripe,
      fournisseur email, Anthropic) tenue à jour.

---

### Annexe — Récapitulatif des variables de production à régler

```bash
# — App / sécurité —
SECRET_KEY=<openssl rand -hex 32>
DEMO_MODE=false
DEBUG=false
ENVIRONMENT=production
CORS_ORIGINS=https://app.adjugo.fr
CRON_SECRET=<openssl rand -hex 32>
RATELIMIT_STORAGE_URI=redis://:<pwd>@<redis-eu>:6379/0   # si multi-worker/instance

# — Base de données (Postgres managé UE/FR, PITR) —
DATABASE_URL=postgresql+psycopg2://<user>:<pwd>@<host-eu>:5432/<db>

# — Stockage S3 UE (Scaleway fr-par) —
STORAGE_BACKEND=s3
S3_BUCKET=adjugo-documents
S3_REGION=fr-par
S3_ENDPOINT_URL=https://s3.fr-par.scw.cloud
AWS_ACCESS_KEY_ID=<scw-access-key>
AWS_SECRET_ACCESS_KEY=<scw-secret-key>

# — Email (Brevo UE) + DNS SPF/DKIM/DMARC sur adjugo.fr —
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<login-smtp>
SMTP_PASSWORD=<clé-smtp>
SMTP_FROM=Adjugo <no-reply@adjugo.fr>
SMTP_TLS=true

# — Observabilité —
SENTRY_DSN=https://<clé>@<org>.ingest.de.sentry.io/<projet>
SENTRY_TRACES_SAMPLE_RATE=0.1
LOG_LEVEL=INFO

# — IA —
ANTHROPIC_API_KEY=<clé Anthropic neuve>

# — Stripe (LIVE) —
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_live_xxx
STRIPE_PRICE_PRO=price_live_pro_xxx
STRIPE_PRICE_BUSINESS=price_live_business_xxx
APP_PUBLIC_URL=https://app.adjugo.fr   # (à introduire dans stripe_pay.py en remplacement des URLs localhost)
```

*Document de référence opérationnelle. Les sections juridiques, fiscales et RGPD sont
des modèles à faire valider par un juriste / expert-comptable avant publication.*
