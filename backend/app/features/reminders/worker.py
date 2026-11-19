"""The Background Worker from the spec's reminder pipeline
(Task Schedule -> Scheduling Logic -> Reminder Records -> Background Worker ->
Notification Service -> User). Runs in-process via FastAPI's lifespan.

Every REMINDER_SWEEP_INTERVAL_SECONDS it sends/cancels due deliveries — one
capped query, cheap regardless of how many tasks exist. Extending every
task's rolling horizon is expensive (several queries per task), so that runs
only at startup and once per new day; config/time edits regenerate their own
task's deliveries immediately (see reminders.service).

Safe to run in several server processes at once: each delivery is claimed
atomically before it's sent, and generation inserts are idempotent.
"""
import asyncio
import logging
from datetime import date

from app.core.database import AsyncSessionLocal
from app.core.timezones import now_utc
from app.features.reminders.service import generate_all_deliveries, run_reminder_sweep

logger = logging.getLogger("reminders.worker")

REMINDER_SWEEP_INTERVAL_SECONDS = 30


async def reminder_worker_loop() -> None:
    generated_for: date | None = None
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Once per UTC day: extend every task's 90-day horizon (each
                # task is planned in its owner's zone inside generation).
                if generated_for != now_utc().date():
                    await generate_all_deliveries(db)
                    generated_for = now_utc().date()
                processed = await run_reminder_sweep(db)
                if processed:
                    logger.info("Reminder sweep processed %d due deliveries", processed)
        except asyncio.CancelledError:
            raise
        except Exception:  # a bad sweep must not kill the worker
            logger.exception("Reminder sweep failed")
        await asyncio.sleep(REMINDER_SWEEP_INTERVAL_SECONDS)
