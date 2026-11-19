"""The background worker: the spec's reminder pipeline (Task Schedule ->
Scheduling Logic -> Reminder Records -> Background Worker -> Notification
Service -> User) plus every time-driven state change. Runs in-process via
FastAPI's lifespan.

Every REMINDER_SWEEP_INTERVAL_SECONDS:
  1. time-driven changes (app.features.maintenance): overdue tasks, missed
     days, paused days skipped — each with its history event. GET requests
     never do this; they only read.
  2. send/cancel due reminder deliveries (one capped query).
Once per UTC day (and at startup): extend every task's 90-day horizon of
deliveries and occurrences (several queries per task, so not every sweep;
schedule edits regenerate their own task immediately).

Safe to run in several server processes at once: deliveries are claimed
atomically before sending, generation inserts are idempotent, and each
maintenance change is a single UPDATE that only one process can win.
"""
import asyncio
import logging
from datetime import date

from app.core.database import AsyncSessionLocal
from app.core.timezones import now_utc
from app.features.maintenance.service import extend_horizons, run_maintenance
from app.features.reminders.service import run_reminder_sweep

logger = logging.getLogger("reminders.worker")

REMINDER_SWEEP_INTERVAL_SECONDS = 30


async def reminder_worker_loop() -> None:
    extended_for: date | None = None
    while True:
        try:
            async with AsyncSessionLocal() as db:
                if extended_for != now_utc().date():
                    await extend_horizons(db)
                    extended_for = now_utc().date()
                changes = await run_maintenance(db)
                if any(changes.values()):
                    logger.info("Time-based changes: %s", changes)
                processed = await run_reminder_sweep(db)
                if processed:
                    logger.info("Reminder sweep processed %d due deliveries", processed)
        except asyncio.CancelledError:
            raise
        except Exception:  # a bad sweep must not kill the worker
            logger.exception("Worker iteration failed")
        await asyncio.sleep(REMINDER_SWEEP_INTERVAL_SECONDS)
