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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

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
    # "anthropic" (défaut) ou "mistral" (Mistral Large, hébergé FR/EU).
    # L'architecture est découplée du fournisseur : tous les appels passent par
    # app/services/llm.py:messages_create. Basculer = changer LLM_PROVIDER (+ clé),
    # sans toucher une ligne des agents. Si la clé Mistral manque, repli auto sur
    # Anthropic (jamais de panne due à un flag mal réglé).
    LLM_PROVIDER: str = "anthropic"

    # Claude (Anthropic)
    ANTHROPIC_API_KEY: str = ""

    # Mistral (souverain) — utilisé uniquement si LLM_PROVIDER=mistral
    MISTRAL_API_KEY: str = ""
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_MODEL: str = "mistral-large-latest"        # raisonnement (analyse, stratégie)
    MISTRAL_MODEL_FAST: str = "mistral-small-latest"   # rédaction rapide (mémoire, Q&A)

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_BUSINESS: str = ""

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
    MAX_UPLOAD_MB: int = 20
    ALLOWED_UPLOAD_EXT: str = ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.odt,.ods,.zip,.txt"

    # Plans
    # Quotas d'analyses IA inclus / mois. Au-delà : 5 €/analyse (overage).
    # Découverte 0 € · Pro 129 € · Business 199 € · Enterprise sur-devis.
    PLAN_LIMITS: dict = {
        "starter": {"analyses": 2, "storage_mb": 500, "members": 2},
        "pro": {"analyses": 30, "storage_mb": 10240, "members": 10},
        "business": {"analyses": 100, "storage_mb": 102400, "members": 50},
    }

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
