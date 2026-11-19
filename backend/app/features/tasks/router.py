"""HTTP endpoints for tasks (create, list, get, update, delete, pause, resume).
GET endpoints only read; time-driven changes (overdue, missed) are made by the
background worker (app.features.maintenance)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, ValidationError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.tasks import service
from app.features.tasks.models import TaskCategory, TaskStatus
from app.features.tasks.schemas import MatrixRead, QuadrantGroup, TaskCreate, TaskRead, TaskResume, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return await service.create_task(
        db,
        uuid.UUID(user_id),
        payload.title,
        payload.category,
        payload.description,
        payload.urgent,
        payload.important,
        payload.due_date,
        payload.due_time,
    )


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    return await service.list_tasks(db, uuid.UUID(user_id))


@router.get("/matrix", response_model=MatrixRead)
async def get_matrix(
    category: TaskCategory | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    groups = await service.get_matrix(db, uuid.UUID(user_id), category)
    return {
        key: QuadrantGroup(
            total=len(tasks),
            completed=sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            tasks=tasks,
        )
        for key, tasks in groups.items()
    }


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.get_task(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.update_task(
            db, task_id, uuid.UUID(user_id), payload.model_dump(exclude_unset=True)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        await service.delete_task(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await service.pause_task(db, task_id, uuid.UUID(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/resume", response_model=TaskRead)
async def resume_task(
    task_id: int,
    payload: TaskResume | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    body = payload or TaskResume()
    try:
        return await service.resume_task(db, task_id, uuid.UUID(user_id), body.due_date, body.due_time)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.NewDueDateRequired as exc:
        # Machine-readable so the app knows to show a date picker.
        raise HTTPException(status_code=409, detail={"code": "new_due_date_required", "message": str(exc)}) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
