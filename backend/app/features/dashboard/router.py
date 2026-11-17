"""HTTP endpoints for the main dashboard, per-task analytics, and calendar."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.dashboard import service
from app.features.dashboard.schemas import CalendarRead, CalendarView, DashboardRead, TaskAnalyticsRead
from app.features.occurrences.service import sync_all_occurrences_for_user, sync_occurrences
from app.features.tasks.models import TaskCategory
from app.features.tasks.service import get_task, sync_overdue

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
analytics_router = APIRouter(prefix="/tasks/{task_id}/analytics", tags=["dashboard"])
calendar_router = APIRouter(prefix="/calendar", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
async def get_dashboard(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    await sync_overdue(db)
    await sync_all_occurrences_for_user(db, uuid.UUID(user_id))
    return await service.get_dashboard(db, uuid.UUID(user_id))


@analytics_router.get("", response_model=TaskAnalyticsRead)
async def get_task_analytics(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    uid = uuid.UUID(user_id)
    try:
        await sync_overdue(db)
        task = await get_task(db, task_id, uid)
        if task.category == TaskCategory.RECURRING:
            try:
                await sync_occurrences(db, task_id, uid)
            except NotFoundError:
                pass  # no reminder config yet — analytics returns basic fields only
        return await service.get_task_analytics(db, task_id, uid)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@calendar_router.get("", response_model=CalendarRead)
async def get_calendar(
    view: CalendarView = CalendarView.MONTHLY,
    anchor_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    uid = uuid.UUID(user_id)
    await sync_overdue(db)
    await sync_all_occurrences_for_user(db, uid)
    return await service.get_calendar(db, uid, view, anchor_date or date.today())
