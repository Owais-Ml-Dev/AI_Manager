"""HTTP endpoint for the monthly productivity report."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import user_today
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.occurrences.service import sync_all_occurrences_for_user
from app.features.reports import service
from app.features.reports.schemas import MonthlyReportRead
from app.features.tasks.service import sync_overdue

router = APIRouter(prefix="/reports/monthly", tags=["reports"])


@router.get("", response_model=MonthlyReportRead)
async def get_monthly_report(
    year: int | None = None,
    month: int | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    uid = uuid.UUID(user_id)
    today = await user_today(db, uid)
    await sync_overdue(db)
    await sync_all_occurrences_for_user(db, uid)
    return await service.get_monthly_report(db, uid, year or today.year, month or today.month)
