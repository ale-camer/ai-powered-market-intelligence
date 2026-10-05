"""Centralized configuration loading using pydantic-settings."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and environment variable definitions."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application Settings
    app_env: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        alias="APP_ENV",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")

    # PostgreSQL / pgvector
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="market_intel", alias="POSTGRES_DB")
    postgres_user: str = Field(default="market_intel_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change-me", alias="POSTGRES_PASSWORD")

    @property
    def async_postgres_url(self) -> str:
        """Return SQLAlchemy async connection string with asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_postgres_url(self) -> str:
        """Return standard sync PostgreSQL connection string."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Apache Airflow
    airflow_executor: str = Field(
        default="LocalExecutor",
        alias="AIRFLOW__CORE__EXECUTOR",
    )
    airflow_db_conn: str = Field(
        default="postgresql+psycopg2://market_intel_user:change-me@localhost:5432/airflow_db",
        alias="AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
    )
    airflow_fernet_key: str = Field(
        default="change-me-fernet-key",
        alias="AIRFLOW__CORE__FERNET_KEY",
    )
    airflow_alert_email: str = Field(
        default="alerts@market-intel.local",
        alias="AIRFLOW_ALERT_EMAIL",
    )
    airflow_dag_sla_hours: float = Field(
        default=2.0,
        alias="AIRFLOW_DAG_SLA_HOURS",
    )

    # Data Source API Keys
    newsapi_api_key: str = Field(default="", alias="NEWSAPI_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        default="market-intel-bot/0.1",
        alias="REDDIT_USER_AGENT",
    )

    # OpenAI / AI Providers
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    # Sentiment Analysis / NLP
    finbert_model_name: str = Field(
        default="ProsusAI/finbert",
        alias="FINBERT_MODEL_NAME",
    )
    sentiment_confidence_threshold: float = Field(
        default=0.65,
        alias="SENTIMENT_CONFIDENCE_THRESHOLD",
    )
    sentiment_min_text_length: int = Field(
        default=30,
        alias="SENTIMENT_MIN_TEXT_LENGTH",
    )
    sentiment_batch_size: int = Field(
        default=32,
        alias="SENTIMENT_BATCH_SIZE",
    )

    # Named Entity Recognition (NER) / SpaCy
    spacy_ner_model: str = Field(
        default="en_core_web_trf",
        alias="SPACY_NER_MODEL",
    )

    # Document Summarization & Vector Embeddings
    openai_summary_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_SUMMARY_MODEL",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )
    openai_embedding_dimensions: int = Field(
        default=1536,
        alias="OPENAI_EMBEDDING_DIMENSIONS",
    )
    openai_max_rpm: int = Field(
        default=500,
        alias="OPENAI_MAX_RPM",
    )
    openai_max_tpm: int = Field(
        default=200000,
        alias="OPENAI_MAX_TPM",
    )

    # Time-Series Anomaly Detection
    anomaly_zscore_threshold: float = Field(
        default=3.0,
        alias="ANOMALY_ZSCORE_THRESHOLD",
    )
    anomaly_iqr_multiplier: float = Field(
        default=1.5,
        alias="ANOMALY_IQR_MULTIPLIER",
    )
    anomaly_iforest_contamination: float = Field(
        default=0.05,
        alias="ANOMALY_IFOREST_CONTAMINATION",
    )

    # SEC EDGAR
    sec_edgar_email: str = Field(
        default="your_email@example.com",
        alias="SEC_EDGAR_EMAIL",
    )

    # Observability
    prometheus_multiproc_dir: str = Field(
        default="/tmp/prometheus_multiproc",
        alias="PROMETHEUS_MULTIPROC_DIR",
    )
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # API & FastAPI Delivery
    api_title: str = Field(
        default="AI-Powered Market Intelligence API",
        alias="API_TITLE",
    )
    api_version: str = Field(
        default="1.0.0",
        alias="API_VERSION",
    )
    api_prefix: str = Field(
        default="",
        alias="API_PREFIX",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        alias="JWT_ALGORITHM",
    )
    jwt_expiration_seconds: int = Field(
        default=3600,
        alias="JWT_EXPIRATION_SECONDS",
    )

    # CORS Security
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"],
        alias="CORS_ALLOWED_ORIGINS",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        alias="CORS_ALLOW_CREDENTIALS",
    )

    # Celery Async Workers & DLQ
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str | None = Field(
        default=None,
        alias="CELERY_RESULT_BACKEND",
    )
    celery_default_queue: str = Field(
        default="celery",
        alias="CELERY_DEFAULT_QUEUE",
    )
    celery_dlq_name: str = Field(
        default="market_intel.dlq",
        alias="CELERY_DLQ_NAME",
    )
    celery_max_retries: int = Field(
        default=3,
        alias="CELERY_MAX_RETRIES",
    )
    celery_retry_base_delay: int = Field(
        default=60,
        alias="CELERY_RETRY_BASE_DELAY",
    )

    @property
    def resolved_celery_result_backend(self) -> str:
        """Return resolved Celery result backend URL (PostgreSQL by default)."""
        if self.celery_result_backend:
            return self.celery_result_backend
        return f"db+{self.sync_postgres_url}"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """Normalize CORS origins from JSON array string, comma-separated string, or iterable."""
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                import json

                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v_trimmed.split(",") if origin.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(item).strip() for item in v if str(item).strip()]
        return ["http://localhost:3000", "http://localhost:8000"]

    @model_validator(mode="after")
    def validate_security_settings(self) -> Self:
        """Validate production secrets and CORS policy hardening."""
        # 1. CORS Hardening: Disallow wildcard origin when credentials are enabled
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError(
                "CORS security violation: Disallowed wildcard '*' origin when "
                "cors_allow_credentials=True."
            )

        # 2. Production Secret Key Hardening
        if self.app_env == "production":
            raw_key = self.secret_key.strip()
            if len(raw_key) < 32:
                raise ValueError(
                    f"Production security error: SECRET_KEY must be at least 32 characters long "
                    f"(got {len(raw_key)} characters)."
                )

            weak_exact_or_substring = (
                "change-me",
                "change-me-in-production",
                "replace-me",
                "your-secret-key",
            )
            weak_exact = (
                "secret",
                "admin",
                "password",
                "12345678",
                "default",
                "test",
            )
            key_lower = raw_key.lower()
            if any(sub in key_lower for sub in weak_exact_or_substring) or key_lower in weak_exact:
                raise ValueError(
                    "Production security error: SECRET_KEY cannot use weak or placeholder defaults."
                )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()
