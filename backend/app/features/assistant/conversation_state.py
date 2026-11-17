"""Redis-backed conversation state, one slot per user, expiring automatically
so a stale "awaiting confirmation" never lingers forever. The database stays
the source of truth for everything else — this is only in-flight chat state.
"""
import uuid

from app.core.redis import redis_client
from app.features.assistant.schemas import ConversationState, PendingAction

_TTL_SECONDS = 600  # 10 minutes — an abandoned conversation just resets to idle
_KEY_PREFIX = "assistant:state:"


def _key(user_id: uuid.UUID) -> str:
    return f"{_KEY_PREFIX}{user_id}"


async def get_pending(user_id: uuid.UUID) -> PendingAction:
    raw = await redis_client.get(_key(user_id))
    if raw is None:
        return PendingAction(state=ConversationState.IDLE)
    return PendingAction.model_validate_json(raw)


async def set_pending(user_id: uuid.UUID, pending: PendingAction) -> None:
    await redis_client.set(_key(user_id), pending.model_dump_json(), ex=_TTL_SECONDS)


async def clear_pending(user_id: uuid.UUID) -> None:
    await redis_client.delete(_key(user_id))
