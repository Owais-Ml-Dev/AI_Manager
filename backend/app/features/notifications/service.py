"""Notification service — the last stage of the reminder pipeline
(Task Schedule -> Scheduling Logic -> Reminder Records -> Background Worker ->
Notification Service -> User).

For each due reminder the worker claims:
  1. an in-app inbox entry is saved (always — even with no phone registered
     or push not configured), at most once per delivery;
  2. a push is sent through FCM to every device the user registered;
     tokens FCM reports as dead are removed.
The push outcome is recorded on the inbox entry (push_status).
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError
from app.core import fcm
from app.core.timezones import now_utc, user_zone
from app.features.notifications import repository
from app.features.notifications.models import DeviceToken, Notification

logger = logging.getLogger("notifications")


# --- devices --------------------------------------------------------------------

async def register_device(db: AsyncSession, user_id: uuid.UUID, token: str, platform: str) -> DeviceToken:
    device = await repository.upsert_device(db, user_id, token, platform, now_utc())
    await db.commit()
    return device


async def list_devices(db: AsyncSession, user_id: uuid.UUID) -> list[DeviceToken]:
    return await repository.list_devices(db, user_id)


async def unregister_device(db: AsyncSession, user_id: uuid.UUID, token: str) -> None:
    """Called on logout. Only the caller's own token can be removed."""
    if not await repository.delete_device(db, user_id, token):
        raise NotFoundError("Device not registered")
    await db.commit()


# --- inbox ----------------------------------------------------------------------

async def list_notifications(db: AsyncSession, user_id: uuid.UUID, unread_only: bool, limit: int) -> list[Notification]:
    return await repository.list_for_user(db, user_id, unread_only, limit)


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await repository.unread_count(db, user_id)


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: int) -> Notification:
    notification = await repository.get(db, notification_id)
    if notification is None or notification.user_id != user_id:
        raise NotFoundError(f"Notification {notification_id} not found")
    await repository.mark_read(db, user_id, now_utc(), notification_id)
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    count = await repository.mark_read(db, user_id, now_utc())
    await db.commit()
    return count


# --- delivering a reminder -------------------------------------------------------

async def deliver_reminder(db: AsyncSession, task, delivery) -> str:
    """Inbox entry + push for one claimed delivery. Returns the push status
    ("sent", "no_devices", "failed", "disabled"), or "duplicate" if this
    delivery already has its notification."""
    tz = await user_zone(db, task.user_id)
    local_time = delivery.scheduled_for.astimezone(tz).strftime("%H:%M")
    title, body = task.title, f"Reminder for {local_time}"

    notification_id = await repository.create_for_delivery(db, task.user_id, task.id, delivery.id, title, body)
    if notification_id is None:
        return "duplicate"
    await db.commit()  # the inbox entry is kept whatever happens to the push

    try:
        status = await _push(db, task.user_id, title, body, {
        "type": "reminder",
        "task_id": str(task.id),
        "notification_id": str(notification_id),
            "scheduled_for": delivery.scheduled_for.astimezone(tz).isoformat(),
        })
    except Exception:  # an unexpected push crash must not leave the entry "pending"
        logger.exception("Push for notification %s crashed", notification_id)
        await db.rollback()
        status = "failed"
    await repository.set_push_status(db, notification_id, status)
    await db.commit()
    return status


async def _push(db: AsyncSession, user_id: uuid.UUID, title: str, body: str, data: dict[str, str]) -> str:
    if not fcm.is_configured():
        return "disabled"
    devices = await repository.list_devices(db, user_id)
    if not devices:
        return "no_devices"
    delivered = False
    for device in devices:
        try:
            result = await fcm.send(device.token, title, body, data)
        except fcm.FcmConfigError:
            logger.exception("Push disabled: Firebase credentials problem")
            return "failed"
        if result.outcome == "sent":
            delivered = True
        elif result.outcome == "invalid_token":
            logger.info("Removing dead device token %s (user %s)", device.id, user_id)
            await repository.delete_token(db, device.token)
        else:
            logger.warning("Push to device %s not delivered (%s): %s", device.id, result.outcome, result.detail)
    return "sent" if delivered else "failed"
