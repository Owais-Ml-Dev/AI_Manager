"""The actual Background Worker from the spec's reminder pipeline
(Task Schedule -> Scheduling Logic -> Reminder Records -> Background Worker ->
Notification Service -> User). Runs in-process via FastAPI's lifespan — no
separate process/infra needed for this scale.

Every REMINDER_SWEEP_INTERVAL_SECONDS, it (1) generates any newly-eligible
delivery rows for every task with a reminder config, then (2) processes every
delivery whose time has arrived (sends or cancels it).
"""
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.features.reminders.service import generate_all_deliveries, run_reminder_sweep

logger = logging.getLogger("reminders.worker")

REMINDER_SWEEP_INTERVAL_SECONDS = 30


async def _run_one_sweep() -> None:
    async with AsyncSessionLocal() as db:
        await generate_all_deliveries(db)
        processed = await run_reminder_sweep(db)
        if processed:
            logger.info("Reminder sweep processed %d due deliveries", processed)


async def reminder_worker_loop() -> None:
    while True:
        try:
            await _run_one_sweep()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - a bad sweep must not kill the worker
            logger.exception("Reminder sweep failed")
        await asyncio.sleep(REMINDER_SWEEP_INTERVAL_SECONDS)
