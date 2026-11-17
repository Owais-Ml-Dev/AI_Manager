"""HTTP endpoint for reading a task's history. Read-only — nothing here writes."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.history import service
from app.features.history.schemas import TaskHistoryEventRead

router = APIRouter(prefix="/tasks/{task_id}/history", tags=["history"])


@router.get("", response_model=list[TaskHistoryEventRead])
async def get_task_history(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.get_history(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
