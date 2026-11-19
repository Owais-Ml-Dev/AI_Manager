"""HTTP endpoints for a recurring task's occurrences.

GET list auto-syncs first (generates any newly-eligible dates, sweeps missed
ones) so the list is always current — no separate "generate" call needed.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.occurrences import service
from app.features.occurrences.models import OccurrenceStatus
from app.features.occurrences.schemas import OccurrenceRead, OccurrenceUpdate

router = APIRouter(prefix="/tasks/{task_id}/occurrences", tags=["occurrences"])


@router.get("", response_model=list[OccurrenceRead])
async def list_occurrences(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.list_occurrences(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{occurrence_id}", response_model=OccurrenceRead)
async def update_occurrence(
    task_id: int,
    occurrence_id: int,
    payload: OccurrenceUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        status = OccurrenceStatus(payload.status.value)
        return await service.update_occurrence(db, task_id, uuid.UUID(user_id), occurrence_id, status)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
