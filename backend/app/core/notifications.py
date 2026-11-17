"""Notification Service — the last stage of the reminder pipeline
(Task Schedule -> Scheduling Logic -> Reminder Records -> Background Worker ->
Notification Service -> User).

This is a log-based stub: there's no frontend in this project to push browser
notifications to, and no email/SMS provider configured. It exists so the
pipeline is real and testable end-to-end now, with a clear seam to swap in an
actual channel (push, email) later without touching the worker or scheduling
logic — they only know "send" succeeded or raised.
"""
import logging

logger = logging.getLogger("reminders.notifications")


def send_reminder_notification(task_id: int, task_title: str, scheduled_for) -> None:
    logger.info("REMINDER: task %s (%r) due at %s", task_id, task_title, scheduled_for)
