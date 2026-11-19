"""Queries for device tokens and notifications. Writes only flush; callers commit."""
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.notifications.models import DeviceToken, Notification


async def upsert_device(db: AsyncSession, user_id: uuid.UUID, token: str, platform: str, now: datetime) -> DeviceToken:
    await db.execute(
        pg_insert(DeviceToken)
        .values(user_id=user_id, token=token, platform=platform, created_at=now, last_seen_at=now)
        .on_conflict_do_update(
            index_elements=[DeviceToken.token],
            set_={"user_id": user_id, "platform": platform, "last_seen_at": now},
        )
    )
    await db.flush()
    return (await db.execute(select(DeviceToken).where(DeviceToken.token == token))).scalar_one()


async def list_devices(db: AsyncSession, user_id: uuid.UUID) -> list[DeviceToken]:
    result = await db.execute(select(DeviceToken).where(DeviceToken.user_id == user_id).order_by(DeviceToken.id))
    return list(result.scalars().all())


async def delete_device(db: AsyncSession, user_id: uuid.UUID, token: str) -> int:
    result = await db.execute(delete(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.token == token))
    await db.flush()
    return result.rowcount


async def delete_token(db: AsyncSession, token: str) -> None:
    await db.execute(delete(DeviceToken).where(DeviceToken.token == token))
    await db.flush()


async def create_for_delivery(
    db: AsyncSession, user_id: uuid.UUID, task_id: int, delivery_id: int, title: str, body: str
) -> int | None:
    """Inserts the inbox entry for a delivery; None if it already exists."""
    result = await db.execute(
        pg_insert(Notification)
        .values(user_id=user_id, task_id=task_id, delivery_id=delivery_id, kind="reminder",
                title=title, body=body, push_status="pending")
        .on_conflict_do_nothing(index_elements=[Notification.delivery_id])
        .returning(Notification.id)
    )
    await db.flush()
    return result.scalar_one_or_none()


async def set_push_status(db: AsyncSession, notification_id: int, status: str) -> None:
    await db.execute(update(Notification).where(Notification.id == notification_id).values(push_status=status))
    await db.flush()


async def list_for_user(db: AsyncSession, user_id: uuid.UUID, unread_only: bool, limit: int) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    result = await db.execute(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit))
    return list(result.scalars().all())


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return (await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )).scalar_one()


async def mark_read(db: AsyncSession, user_id: uuid.UUID, now: datetime, notification_id: int | None = None) -> int:
    query = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    result = await db.execute(query.values(read_at=now))
    await db.flush()
    return result.rowcount


async def get(db: AsyncSession, notification_id: int) -> Notification | None:
    return await db.get(Notification, notification_id)
