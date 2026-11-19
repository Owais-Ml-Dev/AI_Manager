"""FastAPI entry point."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core import gemini_quota
from app.core.config import settings
from app.core.database import engine
from app.core.redis import redis_client
from app.features.assistant.router import router as assistant_router
from app.features.dashboard.router import analytics_router, calendar_router, router as dashboard_router
from app.features.history.router import router as history_router
from app.features.occurrences.router import router as occurrences_router
from app.features.reminders.router import router as reminders_router
from app.features.reminders.worker import reminder_worker_loop
from app.features.reports.router import router as reports_router
from app.features.tasks.router import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(reminder_worker_loop())
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="AI Task Manager", lifespan=lifespan)

# Local-dev-only test frontend runs on a different origin (static file server).
# Permissive on purpose — this backend isn't deployed anywhere, no real
# production CORS boundary exists yet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(reminders_router)
app.include_router(occurrences_router)
app.include_router(history_router)
app.include_router(dashboard_router)
app.include_router(analytics_router)
app.include_router(calendar_router)
app.include_router(reports_router)
app.include_router(assistant_router)


@app.get("/health")
async def health() -> dict:
    """Confirms the API process is up and can reach Supabase (Postgres) and Upstash (Redis)."""
    checks = {"database": "unknown", "redis": "unknown"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - reported, not swallowed
        checks["database"] = f"error: {exc}"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - reported, not swallowed
        checks["redis"] = f"error: {exc}"

    # Which Gemini models are usable right now (fallback chain, in priority
    # order) — "exhausted" ones are being skipped until their quota resets.
    checks["gemini_models"] = await gemini_quota.status(settings.gemini_model_chain)

    return {"status": "ok", "checks": checks}
