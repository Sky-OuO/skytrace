"""记一笔和审核。待归类挂在隐藏题材 unsorted 上，通过之前必须改挂。"""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    NOTE_FIELD_MODELS,
    NOTE_TYPE_NAMES,
    NOTE_TYPES,
    UNSORTED_SLUG,
    can_transition,
    note_requires_portrait_auth,
)
from app.errors import ApiError
from app.models import Media, Note, NoteTag, ReviewTicket, Subject, SubjectExample, Tag, User

STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审",
    "approved": "已通过",
    "rejected": "已驳回",
}

TOPIC_TAGS = {
    "window-light-portrait": ("indoor", "window-light"),
    "studio-one-light": ("indoor", "studio-light", "casual"),
    "street-natural-light": ("outdoor", "available-light", "street"),
    "city-night-portrait": ("outdoor", "night-light"),
    "cosplay-event": ("indoor", "mixed-light", "cos"),
}

# 光明顶不在编辑种子里，它是黄山的旧机位名。搜这个词时按黄山去对「山岳云海日出」。
SEARCH_EXPANSIONS = (("光明顶", "黄山"),)

REQUIRED_FIELDS = {
    "lighting": ("key_light",),
    "posing": ("body_orientation", "contact_points", "light_relationship"),
    "post": ("white_balance_exposure",),
}


def clean_fields(note_type: str, fields: dict | None) -> dict:
    if note_type not in NOTE_FIELD_MODELS:
        raise ApiError(422, "UNPROCESSABLE", "请选择笔记类型")
    try:
        parsed = NOTE_FIELD_MODELS[note_type].model_validate(fields or {})
    except ValidationError as exc:
        raise ApiError(400, "VALIDATION_ERROR", "笔记字段不合法") from exc
    return parsed.model_dump(mode="json")


def default_tag_slugs(subject: Subject) -> tuple[str, ...]:
    if subject.slug in TOPIC_TAGS:
        return TOPIC_TAGS[subject.slug]
    if subject.primary_channel == "landscape":
        return ("outdoor", "available-light")
    return ("indoor",)


async def find_topics(
    session: AsyncSession,
    query: str,
    *,
    selected: str | None = None,
    limit: int = 8,
) -> list[Subject]:
    text = query.strip()
    statement = select(Subject).where(Subject.slug != UNSORTED_SLUG)
    if text:
        terms = [text]
        for needle, extra in SEARCH_EXPANSIONS:
            if needle in text and extra not in terms:
                terms.append(extra)
        clauses = []
        for term in terms:
            like = f"%{term}%"
            clauses.append(
                or_(
                    Subject.name.like(like),
                    Subject.tagline.like(like),
                    cast(Subject.aliases, String).like(like),
                    SubjectExample.name.like(like),
                )
            )
        statement = statement.outerjoin(SubjectExample, SubjectExample.subject_id == Subject.id).where(or_(*clauses))
    statement = statement.order_by(Subject.name).limit(max(limit * 5, 80))
    found: list[Subject] = []
    seen: set[UUID] = set()
    for subject in (await session.execute(statement)).scalars():
        if subject.id in seen:
            continue
        seen.add(subject.id)
        found.append(subject)
        if len(found) >= limit:
            break
    if selected and selected != UNSORTED_SLUG and all(item.slug != selected for item in found):
        current = await subject_by_slug(session, selected)
        if current is not None and current.slug != UNSORTED_SLUG:
            found.insert(0, current)
    return found[:limit]


async def subject_by_slug(session: AsyncSession, slug: str) -> Subject | None:
    result = await session.execute(select(Subject).where(Subject.slug == slug))
    return result.scalar_one_or_none()


def note_payload(note: Note, author: User | None = None) -> dict:
    payload = {
        "id": note.id,
        "subject_id": note.subject_id,
        "example_id": note.example_id,
        "type": note.type,
        "type_name": NOTE_TYPE_NAMES.get(note.type, note.type),
        "title": note.title,
        "body": note.body,
        "fields": note.fields,
        "status": note.status,
        "status_label": STATUS_LABELS.get(note.status, note.status),
        "portrait_auth_accepted": note.portrait_auth_accepted,
        "published_at": note.published_at,
        "submitted_at": note.submitted_at,
    }
    if author is not None:
        payload["author"] = {"id": author.id, "display_name": author.display_name}
    return payload


async def create_note(
    session: AsyncSession,
    user: User,
    *,
    subject_id: UUID | None,
    note_type: str | None,
    title: str | None,
    body: str | None,
    fields: dict | None,
    portrait_auth_accepted: bool,
    example_id: UUID | None = None,
) -> Note:
    if subject_id is None:
        raise ApiError(422, "UNPROCESSABLE", "未选对象")
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "对象不存在")
    if note_type not in NOTE_TYPES:
        raise ApiError(422, "UNPROCESSABLE", "请选择笔记类型")
    clean = clean_fields(note_type, fields)
    note = Note(
        author_id=user.id,
        subject_id=subject.id,
        example_id=example_id,
        type=note_type,
        title=(title or "").strip() or _auto_title(subject, note_type, body),
        body=(body or "").strip(),
        fields=clean,
        status="draft",
        portrait_auth_accepted=portrait_auth_accepted,
    )
    session.add(note)
    await session.flush()
    return note


async def update_note(
    session: AsyncSession,
    user: User,
    note_id: UUID,
    *,
    subject_id: UUID | None = None,
    note_type: str | None = None,
    title: str | None = None,
    body: str | None = None,
    fields: dict | None = None,
    portrait_auth_accepted: bool | None = None,
) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在")
    if note.author_id != user.id:
        raise ApiError(403, "FORBIDDEN", "只能修改自己的笔记")
    if note.status == "approved":
        raise ApiError(409, "CONFLICT", "已过审笔记不能直接修改")
    if subject_id is not None:
        subject = await session.get(Subject, subject_id)
        if subject is None:
            raise ApiError(404, "NOT_FOUND", "对象不存在")
        note.subject_id = subject.id
    if note_type is not None:
        if note_type not in NOTE_TYPES:
            raise ApiError(422, "UNPROCESSABLE", "请选择笔记类型")
        note.type = note_type
    if fields is not None or note_type is not None:
        note.fields = clean_fields(note.type, fields if fields is not None else note.fields)
    if title is not None and title.strip():
        note.title = title.strip()
    if body is not None:
        note.body = body.strip()
    if portrait_auth_accepted is not None:
        note.portrait_auth_accepted = portrait_auth_accepted
    note.updated_at = datetime.now(timezone.utc)
    return note


async def submit_note(session: AsyncSession, user: User, note_id: UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在")
    if note.author_id != user.id:
        raise ApiError(403, "FORBIDDEN", "只能提交自己的笔记")
    if not can_transition(note.status, "pending_review"):
        raise ApiError(409, "CONFLICT", "当前状态不能提交")
    subject = await session.get(Subject, note.subject_id)
    channel = subject.primary_channel if subject is not None else ""
    if note_requires_portrait_auth(note.type, channel) and not note.portrait_auth_accepted:
        raise ApiError(422, "UNPROCESSABLE", "人像笔记提交前需要确认肖像授权")
    await assert_finished_has_photo(session, note)
    _require_submit_content(note)
    clean_fields(note.type, note.fields)
    now = datetime.now(timezone.utc)
    note.status = "pending_review"
    note.submitted_at = now
    note.updated_at = now
    session.add(
        ReviewTicket(
            note_id=note.id,
            status="pending",
            submitter_id=user.id,
            submitted_at=now,
        )
    )
    await session.flush()
    return note


def _require_submit_content(note: Note) -> None:
    fields = note.fields or {}
    if note.type == "finished":
        if not (note.body or "").strip():
            raise ApiError(422, "UNPROCESSABLE", "成片需要一句拍摄说明")
        return
    for key in REQUIRED_FIELDS.get(note.type, ()):
        if not str(fields.get(key) or "").strip():
            raise ApiError(422, "UNPROCESSABLE", "还有必填的拍摄字段没写")


async def assert_finished_has_photo(session: AsyncSession, note: Note) -> None:
    if note.type != "finished":
        return
    count = await session.scalar(
        select(func.count()).select_from(Media).where(Media.note_id == note.id, Media.role == "photo")
    )
    if not count:
        raise ApiError(422, "UNPROCESSABLE", "成片至少上传一张图片")


async def replace_tags(session: AsyncSession, note: Note, slugs: list[str]) -> None:
    from sqlalchemy import delete

    await session.execute(delete(NoteTag).where(NoteTag.note_id == note.id))
    if not slugs:
        return
    tags = list((await session.execute(select(Tag).where(Tag.slug.in_(slugs)))).scalars())
    for tag in tags:
        session.add(NoteTag(note_id=note.id, tag_id=tag.id))


async def decide_ticket(
    session: AsyncSession,
    reviewer: User,
    ticket_id: UUID,
    *,
    decision: str | None,
    reason: str | None = None,
    subject_id: UUID | None = None,
) -> ReviewTicket:
    if decision not in {"approved", "rejected"}:
        raise ApiError(400, "VALIDATION_ERROR", "审核决定只能是通过或驳回")
    ticket = await session.get(ReviewTicket, ticket_id)
    if ticket is None:
        raise ApiError(404, "NOT_FOUND", "审核工单不存在")
    if ticket.status != "pending":
        raise ApiError(409, "CONFLICT", "这张工单已经处理过")
    note = await session.get(Note, ticket.note_id)
    if note is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在")
    if not can_transition(note.status, "approved" if decision == "approved" else "rejected"):
        raise ApiError(409, "CONFLICT", "当前状态不能审核")
    now = datetime.now(timezone.utc)
    if subject_id is not None:
        subject = await session.get(Subject, subject_id)
        if subject is None or subject.slug == UNSORTED_SLUG:
            raise ApiError(422, "UNPROCESSABLE", "请改挂到一个公开题材")
        note.subject_id = subject.id
        note.example_id = None
    if decision == "approved":
        subject = await session.get(Subject, note.subject_id)
        if subject is None or subject.slug == UNSORTED_SLUG:
            raise ApiError(422, "UNPROCESSABLE", "先把这篇归到一个题材，再通过")
        if note_requires_portrait_auth(note.type, subject.primary_channel) and not note.portrait_auth_accepted:
            raise ApiError(422, "UNPROCESSABLE", "人像笔记还没有肖像授权，不能通过")
        note.status = "approved"
        note.published_at = now
        ticket.status = "approved"
    else:
        note.status = "rejected"
        ticket.status = "rejected"
        ticket.reason = (reason or "").strip() or "请修改后再提交"
    note.updated_at = now
    ticket.reviewer_id = reviewer.id
    ticket.decided_at = now
    return ticket


async def pending_tickets(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(ReviewTicket, Note, User, Subject)
            .join(Note, ReviewTicket.note_id == Note.id)
            .join(User, ReviewTicket.submitter_id == User.id)
            .join(Subject, Note.subject_id == Subject.id)
            .where(ReviewTicket.status == "pending")
            .order_by(ReviewTicket.submitted_at)
        )
    ).all()
    items = []
    for ticket, note, author, subject in rows:
        items.append(
            {
                "id": ticket.id,
                "status": ticket.status,
                "submitted_at": ticket.submitted_at,
                "note": note_payload(note, author),
                "subject": {"id": subject.id, "slug": subject.slug, "name": subject.name},
                "unsorted": subject.slug == UNSORTED_SLUG,
            }
        )
    return items


async def my_notes(session: AsyncSession, user: User) -> list[dict]:
    rows = (
        await session.execute(
            select(Note, Subject)
            .join(Subject, Note.subject_id == Subject.id)
            .where(Note.author_id == user.id)
            .order_by(Note.updated_at.desc())
        )
    ).all()
    items = []
    for note, subject in rows:
        payload = note_payload(note, user)
        payload["subject"] = {"id": subject.id, "slug": subject.slug, "name": subject.name}
        payload["unsorted"] = subject.slug == UNSORTED_SLUG
        items.append(payload)
    return items


def _auto_title(subject: Subject, note_type: str, body: str | None) -> str:
    kind = NOTE_TYPE_NAMES.get(note_type, "笔记")
    sentence = (body or "").strip().replace("\n", " ")
    if sentence:
        return f"{subject.name} {sentence}"[:80]
    return f"{subject.name} {kind}"
