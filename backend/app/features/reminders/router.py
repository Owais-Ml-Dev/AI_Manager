"""HTTP endpoints for a task's reminder config."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.reminders import service
from app.features.reminders.schemas import (
    ReminderConfigRead,
    ReminderConfigWrite,
    ReminderDeliveryRead,
    ReminderTimeRead,
    ReminderTimeWrite,
)

router = APIRouter(prefix="/tasks/{task_id}/reminder-config", tags=["reminders"])


@router.put("", response_model=ReminderConfigRead)
async def set_reminder_config(
    task_id: int,
    payload: ReminderConfigWrite,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.set_reminder_config(db, task_id, uuid.UUID(user_id), payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=ReminderConfigRead)
async def get_reminder_config(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.get_reminder_config(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reminder-times", response_model=ReminderTimeRead, status_code=201)
async def add_reminder_time(
    task_id: int,
    payload: ReminderTimeWrite,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.add_reminder_time(
            db, task_id, uuid.UUID(user_id), payload.time_of_day
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reminder-times", response_model=list[ReminderTimeRead])
async def list_reminder_times(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.list_reminder_times(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/reminder-times/{time_id}", response_model=ReminderTimeRead)
async def update_reminder_time(
    task_id: int,
    time_id: int,
    payload: ReminderTimeWrite,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.update_reminder_time(
            db, task_id, uuid.UUID(user_id), time_id, payload.time_of_day
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/reminder-times/{time_id}", status_code=204)
async def delete_reminder_time(
    task_id: int,
    time_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        await service.delete_reminder_time(db, task_id, uuid.UUID(user_id), time_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/deliveries", response_model=list[ReminderDeliveryRead])
async def list_deliveries(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.list_deliveries(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
