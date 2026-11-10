"""SQLModel 表。列名与 Alembic 迁移一致，搜索向量由数据库触发器维护。"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamptz() -> Column:
    return Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"))


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('author', 'reviewer')", name="ck_users_role"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(max_length=320, nullable=False)
    hashed_password: str = Field(sa_column=Column("password_hash", String(1024), nullable=False))
    is_active: bool = Field(default=True, nullable=False)
    is_superuser: bool = Field(default=False, nullable=False)
    is_verified: bool = Field(default=False, nullable=False)
    display_name: str = Field(max_length=100, nullable=False)
    role: str = Field(default="author", max_length=32, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())


class AccessToken(SQLModel, table=True):
    """FastAPI-Users 数据库会话。Cookie 里只放 token，不放 JWT。"""

    __tablename__ = "access_tokens"

    token: str = Field(primary_key=True, max_length=64)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True, default=utcnow, server_default=text("now()")),
    )


class Subject(SQLModel, table=True):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_subjects_slug"),
        CheckConstraint("type IN ('location', 'scene', 'theme')", name="ck_subjects_type"),
        CheckConstraint(
            "primary_channel IN ('landscape', 'culture', 'portrait')",
            name="ck_subjects_primary_channel",
        ),
        Index("ix_subjects_primary_channel_type", "primary_channel", "type"),
        Index("ix_subjects_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(max_length=160, nullable=False)
    name: str = Field(max_length=200, nullable=False)
    type: str = Field(max_length=32, nullable=False)
    primary_channel: str = Field(max_length=32, nullable=False)
    condition_axes: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    geo_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    safety_notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cover_media_id: UUID | None = Field(default=None, foreign_key="media.id", nullable=True)
    guide_summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by: UUID | None = Field(default=None, foreign_key="users.id", nullable=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())
    search_vector: str | None = Field(default=None, sa_column=Column(TSVECTOR, nullable=True))


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "type IN ('finished', 'spot', 'pre', 'post', 'lighting', 'posing')",
            name="ck_notes_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'rejected')",
            name="ck_notes_status",
        ),
        Index("ix_notes_subject_id_type_status", "subject_id", "type", "status"),
        Index(
            "ix_notes_approved",
            "subject_id",
            "type",
            "published_at",
            postgresql_where=text("status = 'approved'"),
        ),
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    author_id: UUID = Field(foreign_key="users.id", nullable=False)
    subject_id: UUID = Field(foreign_key="subjects.id", nullable=False)
    type: str = Field(max_length=32, nullable=False)
    title: str = Field(max_length=300, nullable=False)
    body: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=text("''")))
    fields: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    status: str = Field(default="draft", max_length=32, nullable=False)
    portrait_auth_accepted: bool = Field(default=False, nullable=False)
    submitted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())
    search_vector: str | None = Field(default=None, sa_column=Column(TSVECTOR, nullable=True))


class Media(SQLModel, table=True):
    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_media_storage_key"),
        CheckConstraint("role IN ('cover', 'annotation', 'photo')", name="ck_media_role"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    storage_key: str = Field(max_length=500, nullable=False)
    mime: str = Field(max_length=100, nullable=False)
    byte_size: int = Field(sa_column=Column(Integer, nullable=False))
    width: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    height: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    role: str = Field(default="photo", max_length=32, nullable=False)
    alt: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    note_id: UUID | None = Field(default=None, foreign_key="notes.id", nullable=True)
    subject_id: UUID | None = Field(default=None, foreign_key="subjects.id", nullable=True)
    created_by: UUID | None = Field(default=None, foreign_key="users.id", nullable=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())


class ReviewTicket(SQLModel, table=True):
    __tablename__ = "review_tickets"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_review_tickets_status"),
        Index("ix_review_tickets_status_submitted_at", "status", "submitted_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    note_id: UUID = Field(foreign_key="notes.id", nullable=False)
    status: str = Field(max_length=32, nullable=False)
    submitter_id: UUID = Field(foreign_key="users.id", nullable=False)
    reviewer_id: UUID | None = Field(default=None, foreign_key="users.id", nullable=True)
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    submitted_at: datetime = Field(default_factory=utcnow, sa_column=_timestamptz())
    decided_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tags_slug"),
        CheckConstraint(
            "facet IN ('environment', 'style', 'season', 'time_of_day', 'weather', 'light')",
            name="ck_tags_facet",
        ),
        Index("ix_tags_facet", "facet"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(max_length=80, nullable=False)
    name: str = Field(max_length=80, nullable=False)
    facet: str = Field(max_length=32, nullable=False)


class SubjectTag(SQLModel, table=True):
    __tablename__ = "subject_tags"

    subject_id: UUID = Field(foreign_key="subjects.id", primary_key=True)
    tag_id: UUID = Field(foreign_key="tags.id", primary_key=True)


class NoteTag(SQLModel, table=True):
    __tablename__ = "note_tags"

    note_id: UUID = Field(foreign_key="notes.id", primary_key=True)
    tag_id: UUID = Field(foreign_key="tags.id", primary_key=True)
