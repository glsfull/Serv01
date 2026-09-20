from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SERV01_",
        extra="ignore",
    )

    app_name: str = "Serv01"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+pysqlite:///./serv01.db"
    jwt_secret: str = "development-only-change-me"
    access_token_minutes: int = Field(default=60, ge=5, le=1440)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "default"
    allowed_hosts: str = "example.com,www.iana.org,httpbin.org"
    screenshot_dir: str = "./data/screenshots"
    bot_user_agent: str = "Serv01Bot/0.1 (+contact@example.com)"
    page_timeout_seconds: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret == "development-only-change-me":
            raise ValueError("SERV01_JWT_SECRET must be configured in production")
        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def parsed_allowed_hosts(self) -> set[str]:
        return {
            host.strip().lower().rstrip(".")
            for host in self.allowed_hosts.split(",")
            if host.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
