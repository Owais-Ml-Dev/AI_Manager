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
    # Model fallback chain, in priority order (comma-separated; override with
    # GEMINI_MODELS in .env). Each model has its own free-tier quota; when one
    # runs out, app.core.gemini_quota remembers it and requests go straight to
    # the next until Google's reset time. Pinned versions, not "-latest"
    # aliases, so Google can't swap a model underneath us.
    # Benchmarked 2026-11-19 (manual/gemini_model_bench.py) on the real prompt:
    #   gemini-3.1-flash-lite  31/32 correct, median 1.2s  (primary)
    #   gemini-3.5-flash-lite  30/32 correct, median 4.5s  (backup, slower)
    #   gemini-3.8-flash       free tier only 20 requests/day (last resort)
    gemini_models: str = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.8-flash"

    @property
    def gemini_model_chain(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    # Time zone for users who haven't set one yet (IANA name). The app sends
    # the device's zone at login via PUT /me/settings.
    default_timezone: str = "Asia/Kolkata"

    # Browser origins allowed to call this API (comma-separated), e.g.
    # "http://localhost:5173,https://app.example.com". Empty = no browser
    # origin allowed. Only browsers enforce CORS — the Android app, curl and
    # tests are unaffected — so this matters once a web frontend exists.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    # Supabase project URL, used to fetch its public JWKS for verifying
    # Supabase Auth access tokens. Not a secret.
    supabase_url: str


settings = Settings()
