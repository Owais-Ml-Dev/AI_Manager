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
    # Pinned version, not a "-latest" alias, so Google can't swap the model
    # (and its speed/behavior) underneath us. Chosen by
    # manual/gemini_model_bench.py on 2026-11-19: 31/32 correct, median 1.2s
    # vs 4.5s for gemini-3.5-flash-lite at the same accuracy. Intent
    # extraction is a lightweight task — smallest model that meets the bar (MSI).
    # Override with GEMINI_MODEL in .env.
    gemini_model: str = "gemini-3.1-flash-lite"

    # Supabase project URL, used to fetch its public JWKS for verifying
    # Supabase Auth access tokens. Not a secret.
    supabase_url: str


settings = Settings()
