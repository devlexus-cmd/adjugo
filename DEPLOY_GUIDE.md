# Adjugo — Guide de déploiement pas-à-pas

Ce guide assemble tout ce qui a été préparé (sécurité, Postgres/Alembic, S3, quotas,
rate-limit, observabilité, CSP, alertes email). Suivre dans l'ordre.

---

## 1. Prérequis
- Un serveur (VPS) avec **Docker** + **Docker Compose**, OU une plateforme conteneurs
  (Scaleway, Render, Fly.io, Railway…) + un **PostgreSQL managé**.
- Un nom de domaine (ex. `app.adjugo.fr`).
- Comptes : **Anthropic** (clé API), **Stripe** (mode live), un **bucket S3**
  (AWS / Scaleway / MinIO), un **SMTP** (Brevo, Postmark, SES…).

---

## 2. Configurer les secrets (`.env`)

```bash
cp .env.example .env
# Générer une clé forte :
openssl rand -hex 32      # → coller dans SECRET_KEY
```

Renseigner dans `.env` :

| Variable | Valeur prod |
|---|---|
| `SECRET_KEY` | la clé générée ci-dessus |
| `DEMO_MODE` | `false` |
| `ENVIRONMENT` | `production` |
| `CORS_ORIGINS` | `https://app.adjugo.fr` |
| `DATABASE_URL` | `postgresql+psycopg2://USER:PWD@HOST:5432/adjugo_db` |
| `ANTHROPIC_API_KEY` | votre clé Anthropic (régénérée) |
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET` / `S3_REGION` / `S3_ENDPOINT_URL` | selon le fournisseur |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | clés IAM du bucket |
| `STRIPE_SECRET_KEY` | `sk_live_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` (étape 6) |
| `STRIPE_PRICE_PRO` / `STRIPE_PRICE_BUSINESS` | IDs des prix **live** |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | votre fournisseur d'emails |
| `CRON_SECRET` | une chaîne aléatoire (`openssl rand -hex 16`) |
| `RATELIMIT_STORAGE_URI` | `redis://…` si plusieurs workers, sinon `memory://` |
| `SENTRY_DSN` | (optionnel) votre DSN Sentry |

> ⚠️ `.env` n'est jamais commité (`.gitignore`) ni embarqué dans l'image (`.dockerignore`).

---

## 3. Déploiement — Option A : Docker Compose (tout-en-un)

Le plus simple pour un VPS. La base, les migrations et l'API sont gérées.

```bash
docker compose up -d --build
docker compose logs -f api      # suivre le démarrage
```

Au boot, `entrypoint.sh` lance **`alembic upgrade head`** (avec retry le temps que la
base soit prête) puis `uvicorn` multi-workers. L'API écoute sur `:8000`.

> Pensez à changer `POSTGRES_PASSWORD` dans `docker-compose.yml` **et** `DATABASE_URL`.

## 3 bis. Déploiement — Option B : plateforme + Postgres managé
1. Provisionner un PostgreSQL managé, récupérer son URL → `DATABASE_URL`.
2. Build & push de l'image (`docker build -t adjugo .`) ou déploiement Git.
3. Définir toutes les variables de `.env` dans les secrets de la plateforme.
4. La commande de démarrage est `./entrypoint.sh` (migrations + serveur).
   À défaut, lancer manuellement une fois : `alembic upgrade head`.

---

## 4. Premier compte & données
- L'inscription se fait via l'UI (`/app`) ou `POST /api/auth/register`.
- **Ne pas** lancer `seed_demo.py` en prod (c'est un jeu de démo SQLite).
- Le mode démo (`/demo`, `/api/pipeline/demo/run`) est **désactivé** par `DEMO_MODE=false`.

---

## 5. Reverse proxy + HTTPS

Exemple **Caddy** (TLS automatique Let's Encrypt) — `Caddyfile` :

```
app.adjugo.fr {
    reverse_proxy localhost:8000
}
```
`caddy run` → HTTPS, HSTS déjà émis par l'API (hors debug).
Le rate-limit lit `X-Forwarded-For` : vérifier que le proxy le transmet.
Régler le **timeout proxy ≥ 120 s** (un run pipeline LLM dure ~90 s).

---

## 6. Stripe (mode live)
1. Créer les produits/prix **live** → reporter les IDs dans `STRIPE_PRICE_*`.
2. Créer un endpoint webhook Stripe → `https://app.adjugo.fr/api/stripe/webhook`,
   événements `checkout.session.completed` et `customer.subscription.deleted`.
3. Copier le **signing secret** → `STRIPE_WEBHOOK_SECRET`.
4. Tester un paiement de bout en bout (carte test → live).

---

## 7. Cron quotidien (alertes d'expiration)
Planifier un appel quotidien :

```bash
curl -X POST https://app.adjugo.fr/api/admin/run-alerts \
     -H "X-Cron-Secret: $CRON_SECRET"
```
(cron système, Vercel Cron, GitHub Actions schedule, etc.)

---

## 8. Monitoring
- **Uptime** : surveiller `GET /api/health` (UptimeRobot, Better Stack…).
- **Erreurs** : renseigner `SENTRY_DSN` pour la capture backend.
- **Logs** : structurés sur stdout (`request method=… status=… dur_ms=… id=…`),
  à agréger côté hébergeur.

---

## 9. Vérification post-déploiement
```bash
curl https://app.adjugo.fr/api/health         # {"status":"ok"}
curl -I https://app.adjugo.fr/app             # 200 + en-têtes sécurité + CSP
curl https://app.adjugo.fr/demo               # 404 (démo désactivée) ✓
```
- [ ] Inscription + connexion OK
- [ ] Un pipeline IA tourne et génère un dossier
- [ ] Upload + download d'un document (vérifie S3)
- [ ] Quota : un compte starter est bloqué après 3 analyses (402)
- [ ] Paiement Stripe → plan mis à jour via webhook
- [ ] Email de test reçu (alertes)

---

## 10. Commandes utiles
```bash
# Migrations
alembic upgrade head           # appliquer
alembic revision --autogenerate -m "msg"   # nouvelle migration après changement de modèle

# Tests
python -m pytest

# Logs conteneur
docker compose logs -f api
```

---

## Reste à ta charge (non automatisable ici)
- Révoquer/régénérer la **clé Anthropic** et les **clés Stripe** exposées en dev.
- Sauvegardes PostgreSQL (PITR) côté hébergeur.
- Mentions légales / CGU / CGV / RGPD (DPA avec Anthropic, Stripe, hébergeur).
