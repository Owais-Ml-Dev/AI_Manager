from apscheduler.schedulers.background import BackgroundScheduler

from src.modules.tasks.recurring.service import (
    sync_all_recurring_tasks_lifecycle
)


# =========================================================
# GLOBAL SCHEDULER
# =========================================================

# BackgroundScheduler runs jobs in the background
# while the Flask application is running.
scheduler = BackgroundScheduler(
    timezone="UTC"
)


# =========================================================
# RECURRING LIFECYCLE JOB
# =========================================================

def recurring_lifecycle_job():
    """
    Periodic background job for recurring tasks.

    Responsibilities:
        1. Find all active recurring tasks.
        2. Mark old pending occurrences as missed.
        3. Mark expired recurring parent tasks as ended.

    This allows recurring lifecycle updates to happen
    even when no API endpoint is being called.
    """

    try:

        result = (
            sync_all_recurring_tasks_lifecycle()
        )

        print(
            "[Recurring Scheduler] "
            f"Checked {result['checked']} tasks, "
            f"ended {result['ended']} tasks."
        )

    except Exception as error:

        # The scheduler should not crash the Flask server
        # if one lifecycle execution fails.
        print(
            "[Recurring Scheduler] "
            f"Lifecycle job failed: {error}"
        )


# =========================================================
# START SCHEDULER
# =========================================================

def start_recurring_scheduler():
    """
    Start the recurring-task background scheduler.

    The lifecycle job runs once every hour.

    replace_existing=True prevents duplicate jobs from
    being registered on the same scheduler instance.
    """

    # Avoid starting the same scheduler twice.
    if scheduler.running:
        return

    scheduler.add_job(
        func=recurring_lifecycle_job,

        # Run repeatedly.
        trigger="interval",

        # Check recurring lifecycle every hour.
        hours=1,

        id="recurring_lifecycle_job",

        replace_existing=True,

        # If a run was missed temporarily, do not execute
        # many old copies of the job at once.
        coalesce=True,

        # Prevent overlapping executions of the same job.
        max_instances=1
    )

    scheduler.start()

    print(
        "[Recurring Scheduler] Started successfully."
    )
