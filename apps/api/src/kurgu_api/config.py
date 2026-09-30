"""Uygulama ayarları. Değerler yalnızca ortam değişkenlerinden ve `.env` dosyasından okunur."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kurgu_env: Literal["development", "test", "staging", "production"] = "development"
    kurgu_log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://kurgu_app:change-me-app@localhost:5432/kurgu"
    migrations_database_url: str = (
        "postgresql+asyncpg://kurgu_owner:change-me-owner@localhost:5432/kurgu"
    )
    redis_url: str = "redis://localhost:6379/0"

    oidc_issuer: str = "http://keycloak.localhost:8080/realms/kurgu"
    oidc_audience: str = "kurgu-api"
    # Doğrudan JWKS adresi verilirse keşif (discovery) atlanır; testlerde kullanılır.
    oidc_jwks_url: str | None = None
    kurgu_require_mfa: bool = False

    # Tohum dosyalarının klasörü (`make seed`); konteynerde /app/seed.
    kurgu_seed_dir: str = "seed"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
