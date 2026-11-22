"""首页信息流。只收录已通过的成片，按发布时间倒序做游标分页。"""

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import CHANNEL_CODES
from app.domain import UNSORTED_SLUG
from app.errors import ApiError
from app.models import Media, Note, Subject, User
from app.services.storage import preview_url_for


def encode_cursor(published_at: datetime, note_id: UUID) -> str:
    raw = f"{published_at.isoformat()}|{note_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    padded = value + "=" * (-len(value) % 4)
    try:
        text = base64.urlsafe_b64decode(padded.encode()).decode()
        stamp, note_id = text.split("|", 1)
        return datetime.fromisoformat(stamp), UUID(note_id)
    except (ValueError, UnicodeError) as exc:
        raise ApiError(400, "VALIDATION_ERROR", "分页游标不合法") from exc


async def load_feed(
    session: AsyncSession,
    *,
    channel: str | None = None,
    cursor: str | None = None,
    limit: int = 6,
) -> dict:
    if channel is not None and channel not in CHANNEL_CODES:
        raise ApiError(400, "VALIDATION_ERROR", "未知频道")
    statement = (
        select(Note, Subject, User)
        .join(Subject, Note.subject_id == Subject.id)
        .join(User, Note.author_id == User.id)
        .where(
            Note.status == "approved",
            Note.type == "finished",
            Subject.slug != UNSORTED_SLUG,
            Note.published_at.is_not(None),
        )
        .order_by(Note.published_at.desc(), Note.id.desc())
    )
    if channel is not None:
        statement = statement.where(Subject.primary_channel == channel)
    if cursor:
        published_at, note_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                Note.published_at < published_at,
                and_(Note.published_at == published_at, Note.id < note_id),
            )
        )
    rows = list((await session.execute(statement.limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    note_ids = [note.id for note, _, _ in rows]
    media_by_note: dict[UUID, Media] = {}
    if note_ids:
        media_rows = (
            await session.execute(
                select(Media).where(Media.note_id.in_(note_ids), Media.role == "photo").order_by(Media.created_at)
            )
        ).scalars()
        for media in media_rows:
            if media.note_id is not None and media.note_id not in media_by_note:
                media_by_note[media.note_id] = media
    items = []
    for note, subject, author in rows:
        media = media_by_note.get(note.id)
        items.append(
            {
                "id": note.id,
                "title": note.title,
                "tip": (note.body or "").strip(),
                "slug": subject.slug,
                "topic": subject.name,
                "channel": subject.primary_channel,
                "author": author.display_name,
                "image": None if media is None else preview_url_for(media.storage_key),
                "width": None if media is None else media.width,
                "height": None if media is None else media.height,
                "alt": note.title if media is None or not media.alt else media.alt,
                "published_at": note.published_at,
            }
        )
    next_cursor = None
    if has_more and rows:
        last_note = rows[-1][0]
        if last_note.published_at is not None:
            next_cursor = encode_cursor(last_note.published_at, last_note.id)
    return {"items": items, "next_cursor": next_cursor}
