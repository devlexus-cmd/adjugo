"""
Adjugo Backend — Configuration centrale
"""
from pydantic_settings import BaseSettings
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

    # CORS : origines autorisées (séparées par des virgules). Restreindre en prod.
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:5173,http://localhost:3000"

    # URL publique de l'app (redirections Stripe, liens emails). À régler en prod.
    APP_BASE_URL: str = "https://adjugo-api-production.up.railway.app"

    # Rate limiting : "memory://" en mono-instance, "redis://host:6379" en multi-workers/prod
    RATELIMIT_STORAGE_URI: str = "memory://"

    # Observabilité
    ENVIRONMENT: str = "development"      # development | staging | production
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""                  # vide = Sentry désactivé
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Email (SMTP) — vide = emails désactivés (no-op)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Adjugo <noreply@adjugo.fr>"
    SMTP_TLS: bool = True

    # Secret pour déclencher les tâches cron (alertes). Défini en prod.
    CRON_SECRET: str = ""

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://adjugo:adjugo_password@localhost:5432/adjugo_db"

    # Claude
    ANTHROPIC_API_KEY: str = ""

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
    MAX_UPLOAD_MB: int = 20
    ALLOWED_UPLOAD_EXT: str = ".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.odt,.ods"

    # Plans
    PLAN_LIMITS: dict = {
        "starter": {"analyses": 3, "storage_mb": 500},
        "pro": {"analyses": 50, "storage_mb": 10240},
        "business": {"analyses": 999999, "storage_mb": 102400},
    }

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
