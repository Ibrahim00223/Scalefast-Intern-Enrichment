from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/intern_enrichment"
    LOOKUP_FUZZY_THRESHOLD: float = 0.55
    ADMIN_ALLOWED_DOMAIN: str = "scalefast.fr"
    ADMIN_BOOTSTRAP_EMAIL: str | None = None

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
