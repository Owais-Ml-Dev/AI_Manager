"""
Unit tests for recurring scheduler behavior.

No real background thread is started.
"""

from src.modules.tasks.recurring import scheduler


def test_recurring_lifecycle_job_success(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "sync_all_recurring_tasks_lifecycle",
        lambda: {
            "checked": 5,
            "ended": 2
        }
    )

    # Should run without raising.
    scheduler.recurring_lifecycle_job()


def test_recurring_lifecycle_job_handles_exception(monkeypatch):
    def boom():
        raise RuntimeError("test scheduler error")

    monkeypatch.setattr(
        scheduler,
        "sync_all_recurring_tasks_lifecycle",
        boom
    )

    # The scheduler job intentionally catches errors
    # instead of crashing the process.
    scheduler.recurring_lifecycle_job()


def test_start_scheduler_returns_when_already_running(monkeypatch):
    class FakeScheduler:
        running = True

    monkeypatch.setattr(
        scheduler,
        "scheduler",
        FakeScheduler()
    )

    # Existing running scheduler should exit early.
    scheduler.start_recurring_scheduler()


def test_start_scheduler_registers_and_starts(monkeypatch):
    calls = {
        "add_job": 0,
        "start": 0
    }

    class FakeScheduler:
        running = False

        def add_job(self, *args, **kwargs):
            calls["add_job"] += 1

            assert kwargs["id"] == "recurring_lifecycle_job"
            assert kwargs["replace_existing"] is True
            assert kwargs["coalesce"] is True
            assert kwargs["max_instances"] == 1

        def start(self):
            calls["start"] += 1

    monkeypatch.setattr(
        scheduler,
        "scheduler",
        FakeScheduler()
    )

    scheduler.start_recurring_scheduler()

    assert calls["add_job"] == 1
    assert calls["start"] == 1
