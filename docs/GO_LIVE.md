# Adjugo — Guide de mise en production (pas à pas)

> Objectif : passer de « ça tourne » à « des vraies PME l'utilisent sans risque ».
> Coche chaque case. Les variables d'environnement se posent dans **Railway → service
> `adjugo-api` → onglet *Variables*** (puis *Deploy*). Noms exacts vérifiés dans le code.
>
> Légende : 🔴 bloquant absolu · 🟠 important · 🟢 optionnel/confort.

---

## 🔴 P0-1 — Stockage des fichiers (SINON les documents sont PERDUS)

**Problème** : par défaut `STORAGE_BACKEND=local` → les fichiers (Kbis, attestations,
DCE, pièces des co-traitants) sont écrits dans le conteneur. Sur Railway le disque est
**éphémère** : **chaque redéploiement efface tout**. Inacceptable pour de vraies PME.

**Solution : Cloudflare R2** (compatible S3, 10 Go gratuits, pas de frais de sortie, et
tu es déjà sur Cloudflare). Le code le supporte déjà.

Étapes :
1. Cloudflare → **R2** → *Create bucket* → nom : `adjugo-documents` → région **EU**.
2. R2 → *Manage R2 API Tokens* → *Create API token* → permission **Object Read & Write**
   sur ce bucket → copie **Access Key ID** + **Secret Access Key** + l'**endpoint S3**
   (forme `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).
3. Dans Railway, pose :

| Variable | Valeur |
|---|---|
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `S3_BUCKET` | `adjugo-documents` |
| `S3_REGION` | `auto` |
| `AWS_ACCESS_KEY_ID` | *(Access Key ID du token R2)* |
| `AWS_SECRET_ACCESS_KEY` | *(Secret Access Key du token R2)* |

4. Redéploie. Test : connecte-toi, **téléverse une pièce dans le coffre-fort**, redéploie,
   vérifie qu'elle est **toujours là**.

- [ ] R2 configuré, fichier persistant après redéploiement.

---

## 🔴 P0-2 — Clé de signature des sessions (SINON tokens forgeables)

Par défaut `SECRET_KEY=change-this-in-production` → n'importe qui peut forger un JWT et
se faire passer pour un autre utilisateur. **À changer absolument.**

1. Génère une clé aléatoire :
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Railway : `SECRET_KEY` = *(la valeur générée)*.

> ⚠️ En la changeant, **toutes les sessions existantes sont invalidées** (les gens se
> reconnectent). Fais-le AVANT d'avoir des utilisateurs.

- [ ] `SECRET_KEY` fort posé.

---

## 🔴 P0-3 — Sauvegardes + région EU de la base

1. Railway → service **Postgres** → *Settings* → active les **backups** (snapshots).
2. Vérifie la **région** du Postgres : si elle n'est pas en **UE**, crée un Postgres EU
   et migre (Railway permet un dump/restore). Important pour le RGPD + les CGV.

- [ ] Backups Postgres activés.
- [ ] Base en région UE (ou transfert documenté).

---

## 🟠 P0-4 — Emails (Brevo) + authentification DNS

Sans SMTP : mot de passe oublié, invitations co-traitants, OTP et alertes restent
**dormants** (codés, mais inactifs). Avec : tout s'active automatiquement.

1. Crée un compte **Brevo** (ex-Sendinblue) — gratuit jusqu'à 300 emails/jour.
2. Brevo → *Senders, Domains & Dedicated IPs* → **Domains** → ajoute `adjugo.pro` →
   Brevo te donne **3 enregistrements DNS** (un **DKIM**, un **SPF/`brevo`**, un code de
   vérification). Ajoute-les **chez Cloudflare** (DNS de `adjugo.pro`).
3. Ajoute aussi un **DMARC** simple (Cloudflare → DNS → *Add record*) :
   - Type `TXT`, Name `_dmarc`, Content `v=DMARC1; p=none; rua=mailto:viegaseliot1@gmail.com`
4. Brevo → *SMTP & API* → **SMTP** → note le **login** et la **clé SMTP**.
5. Railway :

| Variable | Valeur |
|---|---|
| `SMTP_HOST` | `smtp-relay.brevo.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | *(login SMTP Brevo)* |
| `SMTP_PASSWORD` | *(clé SMTP Brevo)* |
| `SMTP_FROM` | `Adjugo <noreply@adjugo.pro>` |
| `SMTP_TLS` | `true` |

6. Test : page de connexion → **« Mot de passe oublié ? »** → tu dois recevoir l'email.

- [ ] DNS Brevo (DKIM + SPF) + DMARC posés et vérifiés (statut vert dans Brevo).
- [ ] SMTP posé dans Railway, email de reset reçu.

---

## 🟠 P0-5 — Mode production & secret du cron

Deux variables se « répondent » (garde-fous du code) :
- `CRON_SECRET` : protège les tâches admin/cron coûteuses. **Pose-la** (valeur aléatoire,
  même commande que SECRET_KEY).
- `ENVIRONMENT` : si tu mets `production`, le code **exige** `CRON_SECRET` **et interdit**
  `DEMO_MODE=true` (le bouton « Voir la démo » sans inscription).

**Décision à prendre :**
- **Tu veux garder la démo publique** (utile pour la vente) → laisse `ENVIRONMENT` tel
  quel, mais pose quand même `CRON_SECRET`, `SECRET_KEY`, storage, SMTP.
- **Tu veux le mode le plus verrouillé** → `ENVIRONMENT=production` + `DEMO_MODE=false`
  + `CRON_SECRET` (la démo publique disparaît alors).

> Recommandation beta : garde la démo (conversion), pose `CRON_SECRET` + `SECRET_KEY`.

- [ ] `CRON_SECRET` posé.
- [ ] Décision ENVIRONMENT/DEMO_MODE prise.

---

## 🟠 P1-1 — Monitoring (Sentry)

1. Crée un projet **Sentry** (gratuit) type *FastAPI/Python* → copie le **DSN**.
2. Railway : `SENTRY_DSN` = *(le DSN)*. (Le code l'active tout seul.)

- [ ] `SENTRY_DSN` posé, une erreur de test remonte dans Sentry.

---

## 🟢 P1-2 — Analytics produit (Plausible, sans cookie) — optionnel

1. Crée un site **Plausible** (~9 €/mois ou auto-hébergé) pour `adjugo.pro`.
2. Railway :

| Variable | Valeur |
|---|---|
| `ANALYTICS_SRC` | `https://plausible.io/js/script.js` |
| `ANALYTICS_DOMAIN` | `adjugo.pro` |

(Cookieless → pas de bandeau de consentement requis ; le code l'injecte via
`/api/public-config`.)

- [ ] (optionnel) Analytics actif.

---

## 💳 Décision — Paiement (Stripe)

- **Beta gratuite (recommandé pour démarrer)** : ne configure **rien** côté Stripe. Les
  comptes restent sur l'offre de base. *(Dis-moi si tu veux que je relève le quota
  d'analyses pour les beta-testeurs — 1 ligne de code.)*
- **Facturation live** (plus tard) : compte Stripe vérifié (KYC) → crée 2 *Prices*
  (Pro, Business) → pose `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (endpoint webhook
  `https://adjugo.pro/api/stripe/webhook`), `STRIPE_PRICE_PRO`, `STRIPE_PRICE_BUSINESS`.

- [ ] Décision Stripe prise (beta gratuite ou live).

---

## ⚖️ P1-3 — Légal (en parallèle, ne bloque pas une beta entre proches)

Fais relire par un juriste : `docs/legal/mentions-legales.md`, `cgv.md`,
`politique-confidentialite.md` (aujourd'hui des modèles avec des `[À COMPLÉTER]`).
Vérifie la cohérence avec la **région EU** des données.

- [ ] Pages légales relues/complétées.

---

## ✅ Récapitulatif — variables Railway à poser

```
# Sécurité (P0)
SECRET_KEY=<48+ caractères aléatoires>
CRON_SECRET=<aléatoire>

# Stockage objet R2 (P0)
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_BUCKET=adjugo-documents
S3_REGION=auto
AWS_ACCESS_KEY_ID=<R2 access key>
AWS_SECRET_ACCESS_KEY=<R2 secret>

# Email Brevo (P0)
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<login SMTP Brevo>
SMTP_PASSWORD=<clé SMTP Brevo>
SMTP_FROM=Adjugo <noreply@adjugo.pro>
SMTP_TLS=true

# Monitoring (P1)
SENTRY_DSN=<DSN Sentry>

# Analytics (optionnel)
ANALYTICS_SRC=https://plausible.io/js/script.js
ANALYTICS_DOMAIN=adjugo.pro

# Déjà posé : ANTHROPIC_API_KEY, APP_BASE_URL=https://adjugo.pro
```

---

## 🔎 Vérification finale (10 min, après config)

1. **Persistance** : upload une pièce → redéploie → la pièce est toujours là. ✅ R2
2. **Email** : « Mot de passe oublié ? » → email reçu → reset fonctionne. ✅ SMTP
3. **Inscription réelle** : crée un compte avec ta vraie adresse → l'onboarding
   « Premiers pas » s'affiche → complète profil/critères → 1ʳᵉ recherche. ✅ Parcours
4. **Erreurs** : provoque une erreur (ex. mauvaise requête) → elle apparaît dans Sentry. ✅
5. **RGPD** : Équipe → *Mes données* → Export (tu récupères un JSON). ✅

Quand ces 5 cases sont vertes : **tu peux mettre Adjugo entre les mains de tes premières
PME.**
