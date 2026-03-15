"""
Application configuration using pydantic-settings.
Loads from environment variables and .env file.
"""
import secrets
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "production"
    APP_NAME: str = "supply-chain-ai"
    APP_VERSION: str = "1.0.0"
    APP_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: List[str] = ["*"]

    # API Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    API_RELOAD: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://supply_chain:password@localhost:5432/supply_chain"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP: str = "supply-chain-consumers"
    KAFKA_TOPIC_ORDERS: str = "supply-chain.orders"
    KAFKA_TOPIC_INVENTORY: str = "supply-chain.inventory"
    KAFKA_TOPIC_ALERTS: str = "supply-chain.alerts"

    # Anthropic Claude
    ANTHROPIC_API_KEY: str = "sk-ant-placeholder"
    CLAUDE_MODEL: str = "claude-opus-4-6"
    CLAUDE_MAX_TOKENS: int = 4096

    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET: str = "supply-chain-artifacts"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "supply-chain-ml"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Slack
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_CHANNEL: str = "#supply-chain-alerts"
    SLACK_BOT_TOKEN: Optional[str] = None

    # JWT
    JWT_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    JAEGER_HOST: str = "localhost"
    JAEGER_PORT: int = 6831
    OTEL_SERVICE_NAME: str = "supply-chain-api"

    # LLM Cost Tracking
    LLM_DAILY_BUDGET_USD: float = 100.0
    LLM_ALERT_THRESHOLD_PERCENT: float = 80.0

    # Feature Flags
    ENABLE_ML_FORECASTING: bool = True
    ENABLE_ANOMALY_DETECTION: bool = True
    ENABLE_AUTO_REORDER: bool = True
    ENABLE_SEMANTIC_CACHE: bool = True

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
