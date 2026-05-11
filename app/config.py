from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/intern_enrichment"
    LOOKUP_FUZZY_THRESHOLD: float = 0.55
    ADMIN_ALLOWED_DOMAIN: str = "scalefast.fr"
    ADMIN_BOOTSTRAP_EMAIL: str | None = None
    APP_BASE_URL: str = "http://127.0.0.1:8000"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def coerce_asyncpg_url(cls, v: str) -> str:
        # Railway (and most providers) supply postgresql:// — asyncpg needs postgresql+asyncpg://
        if v.startswith("postgresql://") or v.startswith("postgres://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        return v


settings = Settings()
