"""Centralized configuration loading using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()
