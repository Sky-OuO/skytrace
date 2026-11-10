"""笔记类型、状态机，以及 notes.fields 的键。

第 1–2 天只把字段和允许的状态迁移定下来。提交校验、审核台和公开发布流程后面再做。
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NOTE_TYPES = ("finished", "spot", "pre", "post", "lighting", "posing")
NOTE_TYPE_NAMES = {
    "finished": "成片分享",
    "spot": "机位示意",
    "pre": "前期技巧",
    "post": "后期思路",
    "lighting": "灯光思路",
    "posing": "动作思路",
}

NOTE_STATUSES = ("draft", "pending_review", "approved", "rejected")

# 驳回后可以改回草稿，也可以直接再提交。已过审笔记不再从这里往回走。
NOTE_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending_review"}),
    "pending_review": frozenset({"approved", "rejected"}),
    "rejected": frozenset({"draft", "pending_review"}),
    "approved": frozenset(),
}

TICKET_STATUSES = ("pending", "approved", "rejected")

# 工单 status=pending 对应笔记 status=pending_review。同步逻辑后续实现。
TICKET_TO_NOTE_STATUS = {
    "pending": "pending_review",
    "approved": "approved",
    "rejected": "rejected",
}


def can_transition(current: str, target: str) -> bool:
    return target in NOTE_TRANSITIONS.get(current, frozenset())


def note_requires_portrait_auth(note_type: str, primary_channel: str) -> bool:
    """人像频道或动作思路在提交前必须勾选肖像授权。"""
    return note_type == "posing" or primary_channel == "portrait"


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinishedFields(_Fields):
    related_note_ids: list[UUID] = Field(default_factory=list)


class SpotFields(_Fields):
    arrival: str | None = None
    time_window: str | None = None
    focal_length: str | None = None
    exposure: str | None = None
    common_failures: str | None = None
    exif: dict[str, Any] | None = None


class PreFields(_Fields):
    tickets_permits: str | None = None
    transport_arrival: str | None = None
    season_window: str | None = None
    gear_advice: str | None = None
    safety_tips: str | None = None
    common_failures: str | None = None


class PostFields(_Fields):
    white_balance_exposure: str | None = None
    crop_advice: str | None = None
    material_color: str | None = None
    common_failures: str | None = None


class LightingFields(_Fields):
    key_light: str | None = None
    fill_light: str | None = None
    rim_light: str | None = None
    ambient_light: str | None = None
    common_failures: str | None = None


class PosingFields(_Fields):
    body_orientation: str | None = None
    contact_points: str | None = None
    light_relationship: str | None = None
    common_failures: str | None = None


NOTE_FIELD_MODELS: dict[str, type[_Fields]] = {
    "finished": FinishedFields,
    "spot": SpotFields,
    "pre": PreFields,
    "post": PostFields,
    "lighting": LightingFields,
    "posing": PosingFields,
}


def note_field_keys(note_type: str) -> set[str]:
    model = NOTE_FIELD_MODELS[note_type]
    return set(model.model_fields)
