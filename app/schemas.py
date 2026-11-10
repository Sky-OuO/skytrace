from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("邮箱格式不正确")
        return value


class NoteWriteIn(BaseModel):
    """写入骨架。第 1–2 天不落库，只用来区分缺字段和未开放。"""

    model_config = ConfigDict(extra="allow")

    subject_id: UUID | None = None
    type: str | None = None
    title: str | None = None
    body: str | None = None
    fields: dict[str, Any] | None = None
    portrait_auth_accepted: bool | None = None


class DecideIn(BaseModel):
    decision: str | None = None
    reason: str | None = None
