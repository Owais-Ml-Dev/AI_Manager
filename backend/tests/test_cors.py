"""CORS (Step 1, item #10): only origins listed in CORS_ORIGINS may call the
API from a browser; default is none. Bearer-token auth, so no credentials."""
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, settings
from app.main import app


def _cors_options(application: FastAPI) -> dict:
    return next(m.kwargs for m in application.user_middleware if m.cls is CORSMiddleware)


async def _preflight(application, origin):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://t") as c:
        return await c.options("/tasks", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        })


def test_origins_come_from_settings_and_never_wildcard():
    options = _cors_options(app)
    assert options["allow_origins"] == settings.cors_origin_list
    assert "*" not in options["allow_origins"]
    assert options["allow_credentials"] is False
    assert "*" not in options["allow_methods"] and "*" not in options["allow_headers"]


def test_origin_list_parsing():
    s = Settings(cors_origins=" http://localhost:5173/ , https://app.example.com,, ")
    assert s.cors_origin_list == ["http://localhost:5173", "https://app.example.com"]
    assert Settings(cors_origins="").cors_origin_list == []


async def test_unlisted_origin_is_refused_by_the_real_app():
    assert "https://evil.example.com" not in settings.cors_origin_list  # holds for any real config
    response = await _preflight(app, "https://evil.example.com")
    assert "access-control-allow-origin" not in response.headers


async def test_listed_origin_is_allowed_with_the_same_settings():
    # Same middleware options as the real app, with one origin configured.
    options = {**_cors_options(app), "allow_origins": ["http://localhost:5173"]}
    probe = FastAPI()
    probe.add_middleware(CORSMiddleware, **options)

    @probe.post("/tasks")
    async def _tasks():  # pragma: no cover - preflight never reaches it
        return {}

    allowed = await _preflight(probe, "http://localhost:5173")
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    refused = await _preflight(probe, "https://evil.example.com")
    assert "access-control-allow-origin" not in refused.headers
