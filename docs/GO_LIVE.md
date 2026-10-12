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

### Chiffrement des sauvegardes par Adjugo (clé détenue hors de Railway)

La sauvegarde quotidienne vers R2 est un export complet de la base. Sans réglage, elle est
seulement chiffrée « au repos » par Cloudflare : quiconque obtient les identifiants R2 la lit.
Avec `BACKUP_PUBLIC_KEY`, l'application la chiffre **avant l'envoi** (X25519 + AES-256-GCM,
fichier `.json.gz.enc`). Railway ne détient que la clé **publique** : il sait chiffrer, pas
relire. La clé **privée** ne sert qu'à restaurer et reste chez toi, hors ligne.

> Si tu perds la clé privée **ou** son mot de passe, les sauvegardes chiffrées sont
> définitivement illisibles, y compris pour toi. D'où les deux copies hors ligne ci-dessous.

**1. Générer la paire (sur ton Mac, une seule fois)**

```bash
cd ~/ADJUGO/01_Code/adjugo-backend
venv/bin/python scripts/backup_keygen.py            # fichier : ~/adjugo-cle-sauvegardes.txt
```

Le script demande un mot de passe (12 caractères minimum, une phrase de plusieurs mots est
idéale), écrit la clé privée chiffrée par ce mot de passe (droits 600, 4 lignes de texte),
vérifie qu'elle se relit, puis affiche la ligne `BACKUP_PUBLIC_KEY=…` et l'empreinte de la clé.

**2. Ranger la clé privée hors ligne (avant d'activer)**

- Gestionnaire de mots de passe : une fiche « Adjugo — clé des sauvegardes » avec le
  **mot de passe** et le **contenu du fichier** (copier-coller des 4 lignes).
- Copie physique rangée à part : impression papier du fichier **ou** clé USB. Le fichier seul
  ne suffit pas à déchiffrer : il faut aussi le mot de passe, qui ne va jamais avec lui.
- Jamais sur Railway, dans R2, dans le dépôt Git, ni dans un email.

**3. Activer**

1. Railway → service de l'API → *Variables* → `BACKUP_PUBLIC_KEY` = la ligne affichée
   (forme une ligne ; la forme PEM est aussi acceptée). Redéploie.
2. Vue Administration → « Sauvegarder maintenant » (ou `POST /api/admin/run-backup`
   connecté en admin) : la sauvegarde la plus récente de la liste se termine par
   `.json.gz.enc` (`GET /api/admin/backups` : le compteur `encrypted` augmente). Dans les logs, l'avertissement « sauvegarde non chiffrée par
   l'application » ne doit plus apparaître.
3. Les anciennes sauvegardes en clair disparaissent seules sous 14 jours (`BACKUP_KEEP`).
   Pour qu'elles disparaissent tout de suite, supprime les `backups/*.json.gz` (sans `.enc`)
   dans le tableau de bord R2.

Sans `BACKUP_PUBLIC_KEY` (ou avec une valeur mal collée), la sauvegarde **continue en clair**
comme avant, avec un avertissement dans les logs et dans la réponse de `run-backup` : elle
n'est jamais bloquée.

**4. Tester la restauration (à faire dès l'activation, puis une fois par trimestre)**

1. Cloudflare → R2 → bucket → dossier `backups/` → télécharge le dernier `.json.gz.enc`.
2. Déchiffre-le (mot de passe demandé au clavier) :
   ```bash
   venv/bin/python scripts/backup_decrypt.py ~/Downloads/adjugo-AAAAMMJJ-HHMMSS.json.gz.enc
   ```
   Attendu : « Contenu relu : sauvegarde du …, N tables, M lignes ». Une autre clé, un mauvais
   mot de passe, un fichier modifié ou tronqué sont refusés, sans fichier partiel.
3. Restauration complète dans une base jetable (jamais la production) :
   ```bash
   DATABASE_URL=sqlite:///./restauration_test.db venv/bin/python -c "
   import app.main
   from app.core.database import SessionLocal
   from app.services.backup import restore_backup
   print(restore_backup(open('$HOME/Downloads/adjugo-AAAAMMJJ-HHMMSS.json.gz','rb').read(), SessionLocal()))"
   ```
   Attendu : `{'ok': True, 'tables': N, 'rows': M}`. Supprime ensuite `restauration_test.db`
   et le `.json.gz` déchiffré (il est en clair).

**Changer de clé** : génère une nouvelle paire (`--sortie` vers un autre fichier), remplace
`BACKUP_PUBLIC_KEY`, et garde l'ancienne clé privée 14 jours de plus (les anciennes
sauvegardes restent chiffrées avec elle ; l'empreinte affichée par le script de
déchiffrement dit laquelle il faut).

- [ ] Paire générée, clé privée + mot de passe dans le gestionnaire, copie papier ou USB.
- [ ] `BACKUP_PUBLIC_KEY` posée, dernière sauvegarde en `.json.gz.enc`.
- [ ] Test de restauration réussi (étape 4).

### Ancrage quotidien du journal d'audit

Le journal d'audit est chaîné par hachage : une entrée modifiée ou retirée au milieu est
détectée. Mais supprimer les **dernières** entrées laisse une chaîne valide. Le cron
`POST /api/admin/run-audit-anchor` relève chaque jour la dernière entrée de chaque chaîne,
en fait une empreinte unique horodatée par une autorité indépendante (RFC 3161, freetsa.org
par défaut), et la dépose dans R2 sous `anchors/AAAA-MM-JJ.json`. Le contrôle d'intégrité
(`GET /api/audit/integrity`, journal des partenaires) compare ensuite le journal au dernier
ancrage : « des entrées antérieures au … ont disparu » si une entrée ancrée manque.
Un effacement de compte (RGPD) et la réinitialisation du compte démo ne sont jamais signalés.

Variables (facultatives) :

| Variable | Rôle |
|---|---|
| `ANCHOR_TSA_URL` | autorité d'horodatage (défaut `https://freetsa.org/tsr`). Vide = ancrage sans horodatage. |
| `ANCHOR_EMAIL` | adresse qui reçoit chaque jour l'empreinte et la date : copie hors de l'infrastructure Adjugo. Recommandé : ta propre adresse, avec un filtre qui classe ces emails. |

Si l'autorité ne répond pas (délai borné à quelques secondes), l'ancrage est enregistré quand
même, sans jeton, avec la raison dans `tsa.error` : le cron ne tombe jamais en échec.

**Vérifier un ancrage hors ligne** (preuve opposable, sans faire confiance au serveur) :

1. Télécharge `anchors/AAAA-MM-JJ.json` (et la veille) depuis R2, et les certificats de
   l'autorité `cacert.pem` et `tsa.crt` depuis https://freetsa.org/files/ (HTTPS).
2. Contrôle de cohérence + chaînage des ancrages + engagement reçu par email :
   ```bash
   venv/bin/python scripts/anchor_verify.py 2026-10-07.json 2026-10-08.json --engagement <reçu par email>
   ```
   Le script écrit le jeton `2026-10-08.tsr` et affiche la commande exacte de vérification :
   ```bash
   openssl ts -verify -digest <engagement> -in 2026-10-08.tsr -CAfile cacert.pem -untrusted tsa.crt
   ```
   Attendu : `Verification: OK`. Une empreinte différente donne `message imprint mismatch`.

**Après une restauration de sauvegarde** : les entrées écrites après la sauvegarde ont
réellement disparu, et le contrôle d'intégrité le signalera (à juste titre). Une fois
l'incident documenté, déplace dans R2 les ancrages postérieurs à la sauvegarde restaurée
vers un dossier `anchors-archive/` (conservés comme preuve, mais plus utilisés pour comparer).

- [ ] Cron quotidien `run-audit-anchor` créé (voir P0-5), premier appel : `"ok": true`,
      `"timestamped": true`.
- [ ] `ANCHOR_EMAIL` posée et premier email reçu.

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

**Tâches planifiées (cron externe : service cron Railway, cron-job.org…)** — chacune est un
`POST` sur l'API avec l'en-tête `X-Cron-Secret: <CRON_SECRET>` (sans lui : 403). La veille
amont et la sauvegarde R2 tournent seules dans l'application ; les autres non :

| Fréquence | Appel | Rôle |
|---|---|---|
| quotidien | `POST /api/admin/run-alerts` | alertes de documents qui expirent |
| quotidien | `POST /api/admin/run-tender-alerts` | veille AO (recherches sauvegardées) |
| quotidien | `POST /api/admin/run-cotraitance-reminders` | relances partenaires J-3 / J-1 |
| quotidien | `POST /api/admin/run-trash-purge` | **vide la corbeille** : documents supprimés depuis plus de 30 jours (ligne + fichier + anciennes versions). Sans ce cron, la corbeille n'est **jamais** purgée (promesse RGPD non tenue). |
| quotidien | `POST /api/admin/run-audit-anchor` | **ancre le journal d'audit** : empreinte du jour horodatée par une autorité indépendante (`anchors/AAAA-MM-JJ.json` dans R2, + email si `ANCHOR_EMAIL`). Sans ce cron, la suppression des dernières entrées du journal reste indétectable. Idempotent dans la journée. |

```bash
curl -fsS -X POST https://adjugo-api-production.up.railway.app/api/admin/run-trash-purge \
  -H "X-Cron-Secret: $CRON_SECRET"
```

- [ ] `CRON_SECRET` posé.
- [ ] Crons quotidiens créés (dont `run-trash-purge`) et un premier appel vérifié (réponse 200).
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

# Chiffrement des sauvegardes (P0-3) — clé PUBLIQUE, affichée par scripts/backup_keygen.py
BACKUP_PUBLIC_KEY=<ligne MCowBQYDK2VuAyEA…>

# Ancrage du journal d'audit (P0-3) — facultatif
ANCHOR_EMAIL=<ton adresse>
# ANCHOR_TSA_URL=https://freetsa.org/tsr   (défaut)

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

# IA : routage par tâche (docs/IA_ROUTAGE.md, docs/IA_FOURNISSEURS_PAGES_JURIDIQUES.md)
# Déjà posée : MISTRAL_API_KEY_ADJUGO. Elle seule n'envoie RIEN chez Mistral : tant que les deux
# variables ci-dessous ne sont pas posées, tout part chez Claude Sonnet 5.5 (rien à poser pour déployer).
# Après la désinscription (console Mistral, Admin > Privacy, « Anonymous improvement data ») :
MISTRAL_ENTRAINEMENT_DESACTIVE=1
# À la fin du préavis donné aux clients (DPA, art. 6), le jour où les textes juridiques sont publiés :
MISTRAL_ACTIF=1                   # Mistral Large 4 lit alors les dossiers
# Retour arrière en une minute, si besoin : LLM_ROUTAGE=ancien (Sonnet 4.6 / Haiku 4.5)

# Essai gratuit : garde-fou de coût (docs/ESSAI_GARDE_FOU.md) — rien d'obligatoire, valeurs par
# défaut = décision du 12/10/2026. Migration u5v6essaigardefou à appliquer (alembic upgrade head).
# Le budget compte le coût réel de chaque appel, calculé par le routage (même table des prix :
# app/services/tarifs_ia.py). À régler au besoin :
# TRIAL_AI_BUDGET_EUR=15  TRIAL_ANALYSES=30  TRIAL_QUESTIONS_PAR_JOUR=15  PAID_AI_ALERT_RATIO=0.5
# MISTRAL_SOLDE_JUSQU_AU=2026-10-19 (fin du prix de lancement de Mistral Large 4 ; « aucun » = prix normal)

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
