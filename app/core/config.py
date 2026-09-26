"""One configuration source: environment > .env > defaults."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)
    APP_NAME: str = "World Cup Prediction Agent"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATABASE_URL: str = "sqlite:///./worldcup.db"
    ENVIRONMENT: str = "development"
    ADMIN_API_KEY: str = ""
    ALLOWED_ORIGINS: str = ""
    ALLOW_DEMO_DATA: bool = False
    MODEL_BUNDLE_DIR: str | None = (
        "models/production-v2" if Path("models/production-v2/manifest.json").exists() else None
    )
    SEED_RELEASE: bool = True
    COMPUTE_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=600)
    MAX_REQUEST_BYTES: int = Field(default=8_000_000, ge=1024, le=32_000_000)
    LLM_PROVIDER: str = "openai_compatible"
    LLM_API_KEY: str = Field(
        default="", validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY")
    )
    LLM_BASE_URL: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    LLM_MODEL: str = Field(
        default="glm-4-flash", validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL")
    )
    FOOTBALL_DATA_API: str = ""
    FOOTBALL_DATA_API_KEY: str = ""
    API_FOOTBALL: str = ""
    API_FOOTBALL_KEY: str = ""
    APISPORTS_KEY: str = ""
    API_FOOTBALL_MAX_DAILY_CALLS: int = Field(default=100, ge=0, le=100000)
    AUTO_REFRESH_DATA: bool = False
    DATA_REFRESH_INTERVAL_SECONDS: int = Field(default=3600, ge=300)
    LLM_MAX_DAILY_CALLS: int = Field(default=200, ge=0, le=100000)
    DATA_DIR: str = "data"
    MODEL_PATH: str = "models/feature_network_v2_latest.pth"
    PREDICTION_MODEL_PATH: str = "models"
    ENABLE_SCHEDULER: bool = False
    USE_LOCAL_MODEL: bool = False
    LOCAL_MODEL_URL: str = "http://localhost:11434"
    LOCAL_MODEL_NAME: str = "llama2"

    @property
    def api_football_key(self):
        return self.API_FOOTBALL or self.API_FOOTBALL_KEY or self.APISPORTS_KEY

    @property
    def football_data_api_key(self):
        return self.FOOTBALL_DATA_API or self.FOOTBALL_DATA_API_KEY

    @property
    def OPENAI_API_KEY(self):
        return self.LLM_API_KEY

    @property
    def OPENAI_BASE_URL(self):
        return self.LLM_BASE_URL

    @property
    def OPENAI_MODEL(self):
        return self.LLM_MODEL


@lru_cache
def get_settings():
    return Settings()


def validate_settings(settings):
    if settings.ENVIRONMENT in ("production", "prod"):
        if settings.ADMIN_API_KEY and len(settings.ADMIN_API_KEY) < 24:
            raise ValueError("Production ADMIN_API_KEY must contain at least 24 characters")
        if settings.ALLOW_DEMO_DATA:
            raise ValueError("Demo data cannot be enabled in production")
    if "*" in settings.ALLOWED_ORIGINS.split(","):
        raise ValueError("Configure explicit browser origins; wildcard CORS is disabled")
