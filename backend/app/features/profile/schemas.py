from pydantic import BaseModel, Field, field_validator

from app.core.timezones import is_valid_zone


class UserSettingsRead(BaseModel):
    timezone: str
    # True while the user has never sent a zone (server default in use).
    is_default: bool


class UserSettingsWrite(BaseModel):
    # IANA name from the device, e.g. Android ZoneId.systemDefault().id.
    timezone: str = Field(max_length=64)

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        if not is_valid_zone(value):
            raise ValueError("timezone must be an IANA zone name such as 'Asia/Kolkata'")
        return value
