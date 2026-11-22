"""题材页的读取。公开内容只含已通过、且没有挂在待归类上的笔记。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NOTE_TYPE_NAMES, TOPIC_SECTIONS, UNSORTED_SLUG
from app.models import Media, Note, Subject, SubjectExample, User
from app.services.storage import preview_url_for

FIELD_LABELS = {
    "arrival": "怎么到达",
    "time_window": "时间窗口",
    "focal_length": "焦段",
    "exposure": "曝光",
    "common_failures": "常见失败",
    "tickets_permits": "预约与许可",
    "transport_arrival": "交通",
    "season_window": "季节窗口",
    "gear_advice": "器材",
    "safety_tips": "安全",
    "white_balance_exposure": "白平衡与曝光",
    "crop_advice": "裁切",
    "material_color": "材质与色彩",
    "key_light": "主光",
    "fill_light": "辅光",
    "rim_light": "轮廓光",
    "ambient_light": "环境光",
    "body_orientation": "身体朝向",
    "contact_points": "接触点",
    "light_relationship": "和光线的关系",
}

VERIFY_LABELS = {"verified": "已核对", "pending": "待核实"}


async def public_subject(session: AsyncSession, slug: str) -> Subject | None:
    result = await session.execute(select(Subject).where(Subject.slug == slug))
    subject = result.scalar_one_or_none()
    if subject is None or subject.slug == UNSORTED_SLUG:
        return None
    return subject


async def approved_note_and_subject(session: AsyncSession, note_id: UUID) -> tuple[Note, Subject] | None:
    note = await session.get(Note, note_id)
    if note is None or note.status != "approved" or note.subject_id is None:
        return None
    subject = await session.get(Subject, note.subject_id)
    if subject is None or subject.slug == UNSORTED_SLUG:
        return None
    return note, subject


def _media_payload(media: Media) -> dict:
    return {
        "id": media.id,
        "preview_url": preview_url_for(media.storage_key),
        "alt": media.alt or "",
        "role": media.role,
        "width": media.width,
        "height": media.height,
    }


def _field_rows(fields: dict | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, label in FIELD_LABELS.items():
        value = (fields or {}).get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        rows.append({"label": label, "value": text})
    return rows


async def notes_for_subject(
    session: AsyncSession,
    subject_id: UUID,
    note_type: str | None = None,
) -> list[dict]:
    statement = (
        select(Note)
        .where(Note.subject_id == subject_id, Note.status == "approved")
        .order_by(Note.published_at.desc(), Note.created_at.desc())
    )
    if note_type is not None:
        statement = statement.where(Note.type == note_type)
    notes = list((await session.execute(statement)).scalars())
    if not notes:
        return []
    author_ids = {note.author_id for note in notes}
    note_ids = [note.id for note in notes]
    authors = {
        user.id: user
        for user in (await session.execute(select(User).where(User.id.in_(author_ids)))).scalars()
    }
    media_by_note: dict[UUID, list[Media]] = {note_id: [] for note_id in note_ids}
    media_rows = (
        await session.execute(select(Media).where(Media.note_id.in_(note_ids)).order_by(Media.created_at))
    ).scalars()
    for media in media_rows:
        if media.note_id is not None:
            media_by_note.setdefault(media.note_id, []).append(media)
    payloads = []
    for note in notes:
        author = authors.get(note.author_id)
        payloads.append(
            {
                "id": note.id,
                "type": note.type,
                "type_name": NOTE_TYPE_NAMES.get(note.type, note.type),
                "title": note.title,
                "body": note.body,
                "fields": note.fields or {},
                "field_rows": _field_rows(note.fields or {}),
                "related_note_ids": list((note.fields or {}).get("related_note_ids") or []),
                "published_at": note.published_at,
                "example_id": note.example_id,
                "author": None
                if author is None
                else {"id": author.id, "display_name": author.display_name},
                "media": [_media_payload(item) for item in media_by_note.get(note.id, [])],
            }
        )
    return payloads


async def topic_context(session: AsyncSession, subject: Subject) -> dict:
    examples = list(
        (
            await session.execute(
                select(SubjectExample)
                .where(SubjectExample.subject_id == subject.id)
                .order_by(SubjectExample.sort_order, SubjectExample.name)
            )
        ).scalars()
    )
    notes = await notes_for_subject(session, subject.id)
    by_type: dict[str, list[dict]] = {}
    for note in notes:
        by_type.setdefault(note["type"], []).append(note)
    guide = subject.guide or {}
    sections = []
    for guide_key, note_type, title in TOPIC_SECTIONS:
        lines = [str(line).strip() for line in (guide.get(guide_key) or []) if str(line).strip()]
        section_notes = by_type.get(note_type, [])
        sections.append(
            {
                "key": guide_key,
                "anchor": note_type,
                "note_type": note_type,
                "title": title,
                "lines": lines,
                "notes": section_notes,
                "empty": not lines and not section_notes,
            }
        )
    return {
        "examples": [
            {
                "id": item.id,
                "name": item.name,
                "geo_text": item.geo_text,
                "note": item.note,
                "verify_status": item.verify_status,
                "verify_label": VERIFY_LABELS.get(item.verify_status, item.verify_status),
            }
            for item in examples
        ],
        "sections": sections,
    }
