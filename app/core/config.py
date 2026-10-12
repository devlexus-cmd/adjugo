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

    # Moteur IA — ROUTAGE PAR TÂCHE (app/services/llm.py, table _TABLE ; docs/IA_ROUTAGE.md).
    # Lecture et extraction de documents → Mistral Large 4 ; questions, rédaction, questionnaire,
    # chiffrage, côté acheteur → Claude Sonnet 5.5 ; secours croisé si un fournisseur fait défaut.
    # LLM_PROVIDER : "auto" (défaut) = routage par tâche. "anthropic" | "mistral" FORCE toutes les
    # tâches chez un seul fournisseur (le diagnostic d'administration et le journal le disent).
    # La seule présence d'une clé Mistral ne fait plus rien basculer.
    LLM_PROVIDER: str = "auto"
    # LLM_ROUTAGE=ancien : retour en une minute à l'ancien routage (Claude Sonnet 4.6 / Haiku 4.5,
    # réglages d'origine, aucun secours). Défaut : "nouveau".
    LLM_ROUTAGE: str = "nouveau"

    # Claude (Anthropic)
    ANTHROPIC_API_KEY: str = ""

    # Mistral (La Plateforme). Clé lue dans MISTRAL_API_KEY_ADJUGO en priorité, puis MISTRAL_API_KEY
    # (nom historique, accepté par compatibilité) ; aucune des deux ne déclenche de bascule globale.
    MISTRAL_API_KEY_ADJUGO: str = ""
    MISTRAL_API_KEY: str = ""
    # Point d'accès : "auto" (défaut : UE si le modèle y est servi d'après models.list, sinon
    # mondial) | "ue" (api.eu.mistral.ai, +10 %) | "mondial" (api.mistral.ai).
    MISTRAL_POINT_ACCES: str = "auto"
    # Adresse particulière (rare) : seule une valeur différente des deux points d'accès officiels compte.
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    # Mettre à 1 APRÈS avoir désactivé « Anonymous improvement data » dans la console Mistral
    # (Admin > Privacy). Condition nécessaire pour que Mistral reçoive quoi que ce soit (avec
    # MISTRAL_ACTIF) : les pages juridiques disent que les contenus ne servent pas à entraîner.
    MISTRAL_ENTRAINEMENT_DESACTIVE: bool = False
    # Décision explicite d'activer Mistral (lecture des dossiers) : décision d'Eliot du 12/10/2026, juste
    # après la mise en ligne (les pages juridiques, déjà publiées, s'adaptent d'elles-mêmes). Sans elle, la
    # clé seule n'envoie rien chez Mistral : tout part chez Claude.
    MISTRAL_ACTIF: bool = False

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
        "starter": {"analyses": 5, "storage_mb": 500, "members": 2, "questions_jour": 15},
        "pro": {"analyses": 30, "storage_mb": 10240, "members": 10, "questions_jour": 50},
        "business": {"analyses": 100, "storage_mb": 102400, "members": 50, "questions_jour": 120},
    }
    # Questions posées à l'IA sur un dossier (hors quota d'analyses) : plafond PAR ORGANISATION et
    # PAR JOUR (heure de Paris). 0 = valeur du forfait (PLAN_LIMITS[...]["questions_jour"]).
    QUESTIONS_PAR_JOUR: int = 0

    # ── Garde-fou de l'ESSAI GRATUIT (comptes en essai actif SEULEMENT ; app/services/budget_ia.py) ──
    # Les forfaits payants ne sont JAMAIS bridés par ces réglages (alerte interne seulement, plus bas).
    # Analyses comprises dans l'essai, sur TOUTE sa durée (et non par mois civil : un essai à cheval
    # sur deux mois ne donne plus 2 × 30 analyses).
    TRIAL_ANALYSES: int = 30
    # Questions sur un dossier pendant l'essai : par organisation et par jour (heure de Paris).
    TRIAL_QUESTIONS_PAR_JOUR: int = 15
    # Budget IA total de l'essai, en euros, mesuré appel par appel (coût réel au tarif public du
    # fournisseur) et rattaché au compte de facturation. Vérifié AVANT chaque opération (estimation
    # prudente) ; une opération commencée va toujours au bout. Jamais montré au client. 0 = désactivé.
    TRIAL_AI_BUDGET_EUR: float = 15.0
    # Part du budget de l'essai à partir de laquelle l'écran dit « limite d'usage bientôt atteinte ».
    TRIAL_AI_BUDGET_PROCHE: float = 0.8
    # Forfaits payants : ALERTE interne (journal + /api/admin/usage-ia) quand le coût IA du mois d'une
    # organisation dépasse cette part du prix de son forfait. Aucun blocage. 0 = alerte coupée.
    PAID_AI_ALERT_RATIO: float = 0.5
    # Prix mensuel des forfaits (€ HT) : base de l'alerte ci-dessus (un forfait absent de la liste
    # est comparé au plus cher).
    PLAN_PRICES_EUR: dict = {"pro": 129.99, "business": 199.99}
    # Taux de conversion des tarifs publiés en dollars (Anthropic) : 1 $ = AI_USD_EUR €.
    AI_USD_EUR: float = 0.85

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
