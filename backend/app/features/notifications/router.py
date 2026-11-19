"""Device registration (for push) and the in-app notification inbox.

Android app flow (frontend phase): after login, get the FCM token
(FirebaseMessaging.getInstance().token) and POST /devices; on token refresh,
POST again; on logout, DELETE /devices/{token}.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.core.timezones import user_zone
from app.features.notifications import service
from app.features.notifications.schemas import DeviceRead, DeviceRegister, NotificationRead, UnreadCount

devices_router = APIRouter(prefix="/devices", tags=["notifications"])
router = APIRouter(prefix="/notifications", tags=["notifications"])


def _device_read(device) -> DeviceRead:
    return DeviceRead(id=device.id, platform=device.platform, token_suffix=device.token[-8:],
                      created_at=device.created_at, last_seen_at=device.last_seen_at)


@devices_router.post("", response_model=DeviceRead, status_code=201)
async def register_device(
    payload: DeviceRegister, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return _device_read(await service.register_device(db, uuid.UUID(user_id), payload.token, payload.platform))


@devices_router.get("", response_model=list[DeviceRead])
async def list_devices(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return [_device_read(d) for d in await service.list_devices(db, uuid.UUID(user_id))]


@devices_router.delete("/{token}", status_code=204)
async def unregister_device(token: str, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    try:
        await service.unregister_device(db, uuid.UUID(user_id), token)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _localized(db: AsyncSession, user_id: uuid.UUID, notifications) -> list[NotificationRead]:
    """Stored in UTC; shown in the user's zone (same instant, local clock)."""
    tz = await user_zone(db, user_id)
    return [
        NotificationRead.model_validate(n).model_copy(update={
            "created_at": n.created_at.astimezone(tz),
            "read_at": n.read_at.astimezone(tz) if n.read_at else None,
        })
        for n in notifications
    ]


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    uid = uuid.UUID(user_id)
    return await _localized(db, uid, await service.list_notifications(db, uid, unread_only, limit))


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return UnreadCount(unread=await service.unread_count(db, uuid.UUID(user_id)))


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    uid = uuid.UUID(user_id)
    try:
        return (await _localized(db, uid, [await service.mark_read(db, uid, notification_id)]))[0]
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/read-all", response_model=UnreadCount)
async def mark_all_read(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    uid = uuid.UUID(user_id)
    await service.mark_all_read(db, uid)
    return UnreadCount(unread=await service.unread_count(db, uid))
