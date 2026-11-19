from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegister(BaseModel):
    # From the Android app: FirebaseMessaging.getInstance().token
    token: str = Field(min_length=20, max_length=4096)
    platform: Literal["android", "ios", "web"] = "android"


class DeviceRead(BaseModel):
    id: int
    platform: str
    token_suffix: str  # last characters only — the full token is never echoed back
    created_at: datetime
    last_seen_at: datetime


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    kind: str
    title: str
    body: str
    push_status: str
    created_at: datetime
    read_at: datetime | None


class UnreadCount(BaseModel):
    unread: int
