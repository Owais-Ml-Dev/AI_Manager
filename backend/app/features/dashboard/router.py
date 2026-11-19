"""HTTP endpoints for the main dashboard, per-task analytics, and calendar."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import user_today
from app.common.exceptions import NotFoundError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.dashboard import service
from app.features.dashboard.schemas import CalendarRead, CalendarView, DashboardRead, TaskAnalyticsRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
analytics_router = APIRouter(prefix="/tasks/{task_id}/analytics", tags=["dashboard"])
calendar_router = APIRouter(prefix="/calendar", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
async def get_dashboard(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return await service.get_dashboard(db, uuid.UUID(user_id))


@analytics_router.get("", response_model=TaskAnalyticsRead)
async def get_task_analytics(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    uid = uuid.UUID(user_id)
    try:
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
    return await service.get_calendar(db, uid, view, anchor_date or await user_today(db, uid))
