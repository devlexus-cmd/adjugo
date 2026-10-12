"""
Adjugo Backend — Configuration centrale
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Adjugo API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Auth
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720  # 12h (plafond absolu d'une session ; + verrou d'inactivité côté front)

    # Démo : endpoints publics sans auth (/api/pipeline/demo/run, /demo).
    # METTRE À False EN PRODUCTION.
    DEMO_MODE: bool = True
    # Emails (séparés par des virgules) promus administrateurs au démarrage (is_admin).
    ADMIN_EMAILS: str = ""

    # CORS : origines autorisées (séparées par des virgules). Restreindre en prod.
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:5173,http://localhost:3000"

    # URL publique de l'app (redirections Stripe, liens emails). Domaine officiel adjugo.pro.
    # Tant que le DNS n'est pas propagé, surcharger via la variable d'env Railway si besoin.
    APP_BASE_URL: str = "https://adjugo.pro"

    # Rate limiting : "memory://" en mono-instance, "redis://host:6379" en multi-workers/prod
    RATELIMIT_STORAGE_URI: str = "memory://"
    # Nb de proxys de confiance devant l'app (Railway edge = 1). Sert à extraire l'IP
    # client réelle = hop le plus à droite de X-Forwarded-For (non spoofable).
    TRUSTED_PROXY_HOPS: int = 1

    # Observabilité
    ENVIRONMENT: str = "development"      # development | staging | production
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""                  # vide = Sentry désactivé
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    # Analytics produit (cookieless, ex. Plausible). Vide = désactivé.
    # ANALYTICS_SRC = URL du script ; ANALYTICS_DOMAIN = domaine déclaré (data-domain).
    ANALYTICS_SRC: str = ""
    ANALYTICS_DOMAIN: str = ""

    # Email (SMTP) — vide = emails désactivés (no-op)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Adjugo <noreply@adjugo.pro>"
    SMTP_TLS: bool = True
    # Clé API Brevo (xkeysib-…). Si renseignée, l'envoi passe par l'API HTTP de Brevo
    # (port 443) au lieu du SMTP — indispensable sur Railway/PaaS qui bloquent les
    # ports SMTP sortants (587/465/2525). Le SMTP reste le repli (dev local).
    BREVO_API_KEY: str = ""

    # Secret pour déclencher les tâches cron (alertes). Défini en prod.
    CRON_SECRET: str = ""

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://adjugo:adjugo_password@localhost:5432/adjugo_db"

    # Moteur IA — fournisseur interchangeable (souveraineté).
    # "auto" (défaut) | "anthropic" | "mistral". L'architecture est découplée du fournisseur :
    # tous les appels passent par app/services/llm.py:messages_create.
    # En "auto" : on bascule sur MISTRAL dès qu'une MISTRAL_API_KEY est présente, sinon Anthropic.
    # → il SUFFIT d'ajouter la clé Mistral dans Railway pour passer au souverain, rien d'autre.
    # Forçable : LLM_PROVIDER=anthropic (rester sur Claude même avec une clé Mistral) ou =mistral.
    # Si "mistral" est demandé sans clé → repli auto sur Anthropic (jamais de panne due à un flag).
    LLM_PROVIDER: str = "auto"

    # Claude (Anthropic)
    ANTHROPIC_API_KEY: str = ""

    # Mistral (souverain, hébergé FR/EU) — sa seule présence suffit à activer Mistral (mode auto)
    MISTRAL_API_KEY: str = ""
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_MODEL: str = "mistral-large-latest"        # raisonnement (analyse, stratégie)
    MISTRAL_MODEL_FAST: str = "mistral-small-latest"   # rédaction rapide (mémoire, Q&A)

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_BUSINESS: str = ""
    # Facturation au-delà du forfait (5 € HT par analyse) : prix « à l'usage » (metered) relié au
    # compteur Stripe ci-dessous. Vide = dépassement compté en base seulement (facturable à la main).
    # DÉCLARÉ ICI : une variable d'environnement non déclarée n'est pas lue par pydantic-settings.
    STRIPE_PRICE_OVERAGE: str = ""
    # Nom de l'événement du compteur Stripe (Billing → Meters) qui reçoit une unité par analyse.
    STRIPE_METER_EVENT_OVERAGE: str = "adjugo_analyse_overage"

    # Connexion Google (OAuth 2.0). Inactive tant que CLIENT_ID/SECRET ne sont pas fournis.
    # REDIRECT_URI doit correspondre EXACTEMENT à celui enregistré dans la Google Cloud Console.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""   # défaut : {APP_BASE_URL}/api/auth/google/callback

    # Stockage des fichiers : "local" (dev) ou "s3" (prod / MinIO / Scaleway)
    STORAGE_BACKEND: str = "local"
    S3_BUCKET: str = "adjugo-documents"
    S3_REGION: str = "eu-west-3"
    S3_ENDPOINT_URL: str = ""  # vide = AWS ; sinon MinIO/Scaleway (https://s3.fr-par.scw.cloud)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # Upload : limites de validation
    # Sauvegarde auto de la base vers le stockage objet (R2). 0 = désactivée.
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_KEEP: int = 14                 # nb de sauvegardes conservées
    # Clé PUBLIQUE (X25519, non secrète) : chiffre chaque sauvegarde avant l'envoi. La clé
    # privée reste hors ligne (scripts/backup_keygen.py). Vide = sauvegarde non chiffrée
    # par l'application (avertissement dans les logs).
    BACKUP_PUBLIC_KEY: str = ""
    # Ancrage quotidien de la tête du journal d'audit (POST /api/admin/run-audit-anchor) :
    # autorité d'horodatage RFC 3161, et adresse optionnelle qui reçoit l'empreinte du jour.
    ANCHOR_TSA_URL: str = "https://freetsa.org/tsr"
    ANCHOR_EMAIL: str = ""
    MAX_UPLOAD_MB: int = 20
    ALLOWED_UPLOAD_EXT: str = ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.odt,.ods,.zip,.txt"

    # Plans — essai gratuit 30j SANS carte, puis payant (logique dans app/core/quota.py).
    # Quotas d'analyses IA inclus / mois. Au-delà : 5 €/analyse (overage, plans payants).
    # Pendant l'essai : accès niveau Pro. Pro 129,99 € · Business 199,99 € · Sur mesure sur devis.
    # 'starter' = palier résiduel : essai actif→niveau Pro, essai expiré→bloqué, historique/démo→Découverte.
    PLAN_LIMITS: dict = {
        "starter": {"analyses": 5, "storage_mb": 500, "members": 2, "questions_jour": 20},
        "pro": {"analyses": 30, "storage_mb": 10240, "members": 10, "questions_jour": 60},
        "business": {"analyses": 100, "storage_mb": 102400, "members": 50, "questions_jour": 150},
    }
    # Questions posées à l'IA sur un dossier (hors quota d'analyses) : plafond PAR ORGANISATION et
    # PAR JOUR (heure de Paris). 0 = valeur du forfait (PLAN_LIMITS[...]["questions_jour"]).
    QUESTIONS_PAR_JOUR: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def _strip_env_whitespace(cls, v):
        """Nettoie les espaces/tabulations/retours-ligne parasites collés dans une
        variable d'environnement (copier-coller). Sans ça, un simple « \\ttrue »
        sur SMTP_TLS empêche TOUTE l'app de démarrer (crash au boot). On strip donc
        toute valeur scalaire de type str avant que pydantic ne tente de la typer."""
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _harden_secret_key(self):
        # Normalise l'environnement (« Production »/« prod » → « production ») pour que les
        # gardes-fous ne dépendent plus d'une chaîne exacte.
        self.ENVIRONMENT = (self.ENVIRONMENT or "").strip().lower()
        # SECRET_KEY FORTE et OBLIGATOIRE, INDÉPENDAMMENT de l'environnement : une clé faible/
        # par défaut avec HS256 = forge de n'importe quel JWT (bypass total de l'auth). En prod
        # → refus de démarrer ; en dev → clé éphémère en mémoire (jamais le défaut codé en dur).
        weak = ((not self.SECRET_KEY) or self.SECRET_KEY == "change-this-in-production"
                or len(self.SECRET_KEY) < 32)
        if weak:
            if self.ENVIRONMENT == "production":
                raise ValueError("SECRET_KEY faible ou par défaut en production : "
                                 "définissez une clé d'au moins 32 caractères.")
            import secrets as _secrets
            self.SECRET_KEY = _secrets.token_hex(32)
        return self

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
