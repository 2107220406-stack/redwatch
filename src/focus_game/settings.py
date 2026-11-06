"""Application settings loaded from environment and optional .env files."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./focus-game.db"
    app_timezone: str = "Asia/Shanghai"
    vision_provider: str = "fake"
    vision_model: str = "fake-model"
    vision_endpoint: str | None = None
    vision_api_key: SecretStr | None = None
    vision_timeout_seconds: float = 20.0
    max_image_bytes: int = 5 * 1024 * 1024
    evidence_retention_days: int = 7
    auto_create_schema: bool | None = None
    auth_mode: str | None = None
    auth_secret: SecretStr = SecretStr("development-only-change-me")
    internal_api_token: SecretStr = SecretStr("development-internal-token")
    allow_client_observation: bool | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def effective_auth_mode(self) -> str:
        return self.auth_mode or ("hmac" if self.app_env.lower() == "production" else "header")

    @property
    def client_observation_enabled(self) -> bool:
        if self.effective_auth_mode == "hmac":
            return False
        if self.allow_client_observation is not None:
            return self.allow_client_observation
        return self.effective_auth_mode != "hmac" and self.vision_provider == "fake"

    @property
    def schema_auto_create_enabled(self) -> bool:
        if self.auto_create_schema is not None:
            return self.auto_create_schema
        return self.app_env.lower() != "production"

    def validate_runtime(self) -> None:
        if self.evidence_retention_days < 0:
            raise ValueError("EVIDENCE_RETENTION_DAYS must be non-negative")
        if self.vision_timeout_seconds <= 0:
            raise ValueError("VISION_TIMEOUT_SECONDS must be positive")
        if self.max_image_bytes <= 0:
            raise ValueError("MAX_IMAGE_BYTES must be positive")
        if self.effective_auth_mode not in {"header", "hmac"}:
            raise ValueError("AUTH_MODE must be either header or hmac")
        if self.effective_auth_mode == "hmac" and len(self.auth_secret.get_secret_value()) < 32:
            raise ValueError("AUTH_SECRET must contain at least 32 characters in hmac mode")
        if self.app_env.lower() == "production" and self.vision_provider == "fake":
            raise ValueError("production cannot use the fake vision provider")
        if self.app_env.lower() == "production" and len(
            self.internal_api_token.get_secret_value()
        ) < 32:
            raise ValueError("INTERNAL_API_TOKEN must contain at least 32 characters in production")
        if self.vision_provider in {"http_json", "openai_compatible"} and not self.vision_endpoint:
            raise ValueError("VISION_ENDPOINT is required for the configured vision provider")
        if self.vision_provider == "openai_compatible" and not self.vision_api_key:
            raise ValueError("VISION_API_KEY is required for openai_compatible provider")
