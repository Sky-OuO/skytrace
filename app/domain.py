"""笔记类型、状态机，以及 notes.fields 的键。

第 1–2 天只把字段和允许的状态迁移定下来。提交校验、审核台和公开发布流程后面再做。
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


# 题材页六个固定区块。guide 的键、笔记 type、界面标题。
TOPIC_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("finished_points", "finished", "成片"),
    ("scouting", "spot", "踩点"),
    ("pre", "pre", "前期"),
    ("post", "post", "后期"),
    ("lighting", "lighting", "用光"),
    ("posing", "posing", "姿势"),
)

GUIDE_KEYS: tuple[str, ...] = tuple(item[0] for item in TOPIC_SECTIONS)
UNSORTED_SLUG = "unsorted"


class SubjectGuide(BaseModel):
    """编辑种子的六段要点。每段 2–4 条短句，不能用空话填。"""

    model_config = ConfigDict(extra="forbid")

    finished_points: list[str] = Field(min_length=2, max_length=4)
    scouting: list[str] = Field(min_length=2, max_length=4)
    pre: list[str] = Field(min_length=2, max_length=4)
    post: list[str] = Field(min_length=2, max_length=4)
    lighting: list[str] = Field(min_length=2, max_length=4)
    posing: list[str] = Field(min_length=2, max_length=4)

    @field_validator("finished_points", "scouting", "pre", "post", "lighting", "posing")
    @classmethod
    def short_lines(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                raise ValueError("要点不能是空行")
            if "私房" in text:
                raise ValueError("公开文案不能出现禁用词")
            cleaned.append(text)
        return cleaned


class SubjectExampleSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    geo_text: str | None = None
    note: str | None = None
    verify_status: Literal["verified", "pending"] = "pending"

    @field_validator("name", "geo_text", "note")
    @classmethod
    def no_forbidden(cls, value: str | None) -> str | None:
        if value and "私房" in value:
            raise ValueError("公开文案不能出现禁用词")
        return value.strip() if isinstance(value, str) else value


class SubjectSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=200)
    channel: Literal["portrait", "landscape"]
    tagline: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    guide: SubjectGuide
    examples: list[SubjectExampleSeed] = Field(default_factory=list)
    geo_text: str | None = None
    safety_notes: str | None = None
    condition_axes: list[str] = Field(default_factory=list)
    type: Literal["location", "scene", "theme"] | None = None

    @field_validator("tagline", "name", "geo_text", "safety_notes")
    @classmethod
    def no_forbidden_text(cls, value: str | None) -> str | None:
        if value and "私房" in value:
            raise ValueError("公开文案不能出现禁用词")
        return value.strip() if isinstance(value, str) else value

    def resolved_type(self) -> str:
        if self.type:
            return self.type
        return "scene" if self.channel == "portrait" else "location"
