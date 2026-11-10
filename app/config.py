from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://skytrace:skytrace@localhost:5432/skytrace"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-local-env"
    media_root: str = "var/media"
    media_preview_base_url: str = "/media"
    media_max_bytes: int = 10 * 1024 * 1024
    session_cookie_name: str = "skytrace_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_lifetime_seconds: int = Field(default=1_209_600, ge=60)
    demo_author_email: str = "author@skytrace.local"
    demo_author_password: str = "author-demo-pass"
    demo_author_name: str = "演示作者"
    demo_reviewer_email: str = "reviewer@skytrace.local"
    demo_reviewer_password: str = "reviewer-demo-pass"
    demo_reviewer_name: str = "演示审核员"


@lru_cache
def get_settings() -> Settings:
    return Settings()
