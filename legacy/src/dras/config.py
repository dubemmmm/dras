from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRAS_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./dras.db"
    storage_dir: Path = Path("./var/storage")
    api_base_url: str = "http://localhost:8000"
    service_token: str = "development-only-token"
    assessor_emails: str = "assessor@example.org"
    openai_api_key: str | None = None
    extraction_model: str = "gpt-6-luna"
    review_model: str = "gpt-6.1-sol"
    review_reasoning: str = "medium"
    redis_url: str = "redis://localhost:6379/0"
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    max_upload_bytes: int = 100 * 1024 * 1024
    max_pages: int = 600
    signed_url_seconds: int = Field(default=300, ge=60, le=900)
    require_malware_scan: bool = False
    require_pdf_render: bool = False

    @field_validator("database_url")
    @classmethod
    def use_psycopg3(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_assessors(self) -> set[str]:
        return {email.strip().lower() for email in self.assessor_emails.split(",") if email.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

