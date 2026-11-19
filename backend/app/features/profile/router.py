"""GET/PUT /me/settings. The Android app sends the device's time zone at
login and whenever it changes (ZoneId.systemDefault().id)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.profile import service
from app.features.profile.schemas import UserSettingsRead, UserSettingsWrite

router = APIRouter(prefix="/me/settings", tags=["profile"])


@router.get("", response_model=UserSettingsRead)
async def read_settings(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return await service.get_settings(db, uuid.UUID(user_id))


@router.put("", response_model=UserSettingsRead)
async def update_settings(
    body: UserSettingsWrite,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.set_timezone(db, uuid.UUID(user_id), body.timezone)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
