"""Application settings, loaded from environment variables / .env.

All secrets (Supabase DB URL, Upstash Redis URL, Gemini API key) live here and
nowhere else, so they never leak into frontend code or logs by accident.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development"

    # Supabase Postgres, via SQLAlchemy async engine (asyncpg driver)
    database_url: str

    # Upstash Redis, used only for short-lived AI conversation state (phase 4+),
    # never as the source of truth for task data.
    redis_url: str

    # Google Gemini API key (used starting phase 4, optional until then)
    gemini_api_key: str = ""
    # Alias (auto-updates to the current recommended lite model) rather than a
    # pinned version — intent extraction is a lightweight task, use the
    # smallest model that meets the bar (MSI).
    gemini_model: str = "gemini-flash-lite-latest"

    # Supabase project URL, used to fetch its public JWKS for verifying
    # Supabase Auth access tokens. Not a secret.
    supabase_url: str


settings = Settings()
