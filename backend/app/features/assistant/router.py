"""HTTP endpoint for the AI assistant. One endpoint, one message in, one
reply out — all state lives server-side (Redis) between calls."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.features.assistant import service
from app.features.assistant.schemas import AssistantMessageRequest, AssistantMessageResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/message", response_model=AssistantMessageResponse)
async def send_message(
    payload: AssistantMessageRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return await service.handle_message(db, uuid.UUID(user_id), payload.message, payload.input)
