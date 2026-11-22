"""为每个编辑题材写已通过的成片，并画一张不重复的示例图。

文案只复述种子里的要点和示例名。窗边人像和山岳云海日出各至少三张。
重复执行会先清掉署名账号的旧示例笔记再重写，避免和上一版种子混在一起。
"""

from datetime import datetime, timedelta, timezone

from fastapi_users.password import PasswordHelper
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media, Note, NoteTag, ReviewTicket, Subject, SubjectExample, User
from app.placeholders import render_placeholder
from app.services.storage import resolve_storage_path

BYLINES = (
    ("linxia@skytrace.local", "林夏"),
    ("zhouyu@skytrace.local", "周屿"),
    ("chenheng@skytrace.local", "陈衡"),
    ("desk@skytrace.local", "编辑部"),
)
BYLINE_PASSWORD = "byline-not-for-login"


async def _users(session: AsyncSession, helper: PasswordHelper) -> list[User]:
    users: list[User] = []
    for email, name in BYLINES:
        found = await session.execute(select(User).where(User.email == email))
        user = found.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                hashed_password=helper.hash(BYLINE_PASSWORD),
                display_name=name,
                role="author",
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(user)
            await session.flush()
        else:
            user.display_name = name
        users.append(user)
    return users


HERO_COUNTS = {"window-light-portrait": 3, "sea-of-clouds-sunrise": 3}
GUIDE_ORDER = ("finished_points", "lighting", "posing", "scouting", "pre", "post")


def _guide_lines(subject: Subject) -> list[str]:
    guide = subject.guide or {}
    lines: list[str] = []
    seen: set[str] = set()
    for key in GUIDE_ORDER:
        for raw in guide.get(key) or []:
            text = str(raw).strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
    if not lines:
        lines.append(subject.tagline or subject.name)
    return lines


def _plans(subjects: list[Subject], examples: dict) -> list[dict]:
    by_slug = {subject.slug: subject for subject in subjects}
    plans: list[dict] = []

    def add(subject: Subject, line: str, example_name: str | None, front: int | None) -> None:
        title = f"{subject.name} · {example_name}" if example_name else f"{subject.name} · {line}"
        plans.append(
            {
                "slug": subject.slug,
                "title": title[:120],
                "body": line,
                "example": example_name,
                "front": front,
            }
        )

    window = by_slug.get("window-light-portrait")
    clouds = by_slug.get("sea-of-clouds-sunrise")
    window_examples = [item.name for item in examples.get(window.id, [])] if window else []
    cloud_examples = [item.name for item in examples.get(clouds.id, [])] if clouds else []
    front = 0
    for index in range(3):
        if window:
            names = window_examples or [None]
            add(window, _guide_lines(window)[index % len(_guide_lines(window))], names[index % len(names)], front)
            front += 1
        if clouds:
            line = _guide_lines(clouds)[index % len(_guide_lines(clouds))]
            example_name = cloud_examples[0] if index == 0 and cloud_examples else None
            add(clouds, line, example_name, front)
            front += 1
    portraits = [subject for subject in subjects if subject.primary_channel == "portrait" and subject.slug not in HERO_COUNTS]
    landscapes = [subject for subject in subjects if subject.primary_channel == "landscape" and subject.slug not in HERO_COUNTS]
    portraits.sort(key=lambda item: item.slug)
    landscapes.sort(key=lambda item: item.slug)
    mixed: list[Subject] = []
    for index in range(max(len(portraits), len(landscapes))):
        if index < len(portraits):
            mixed.append(portraits[index])
        if index < len(landscapes):
            mixed.append(landscapes[index])
    for subject in mixed:
        add(subject, _guide_lines(subject)[0], None, None)
    return plans


async def _clear_byline_notes(session: AsyncSession, users: list[User]) -> None:
    author_ids = [user.id for user in users]
    if not author_ids:
        return
    note_ids = list((await session.execute(select(Note.id).where(Note.author_id.in_(author_ids)))).scalars())
    if not note_ids:
        return
    media_ids = list((await session.execute(select(Media.id).where(Media.note_id.in_(note_ids)))).scalars())
    if media_ids:
        await session.execute(update(Subject).where(Subject.cover_media_id.in_(media_ids)).values(cover_media_id=None))
    await session.execute(delete(ReviewTicket).where(ReviewTicket.note_id.in_(note_ids)))
    await session.execute(delete(NoteTag).where(NoteTag.note_id.in_(note_ids)))
    await session.execute(delete(Media).where(Media.note_id.in_(note_ids)))
    await session.execute(delete(Note).where(Note.id.in_(note_ids)))


async def _upsert_note(
    session: AsyncSession,
    *,
    subject: Subject,
    author: User,
    type_: str,
    title: str,
    body: str,
    fields: dict,
    published_at: datetime,
    example_id,
) -> Note:
    found = await session.execute(
        select(Note).where(Note.subject_id == subject.id, Note.type == type_, Note.title == title)
    )
    note = found.scalar_one_or_none()
    portrait = subject.primary_channel == "portrait" or type_ == "posing"
    if note is None:
        note = Note(
            author_id=author.id,
            subject_id=subject.id,
            example_id=example_id,
            type=type_,
            title=title,
            body=body,
            fields=fields,
            status="approved",
            portrait_auth_accepted=portrait,
            submitted_at=published_at,
            published_at=published_at,
        )
        session.add(note)
        await session.flush()
        return note
    note.body = body
    note.fields = fields
    note.status = "approved"
    note.example_id = example_id
    note.portrait_auth_accepted = portrait or note.portrait_auth_accepted
    note.published_at = published_at
    note.submitted_at = note.submitted_at or published_at
    return note


async def _upsert_photo(
    session: AsyncSession,
    *,
    note: Note,
    subject: Subject,
    author: User,
    index: int,
    caption: str,
) -> Media:
    key = f"seed/{subject.slug}/{index}.png"
    data, width, height = render_placeholder(subject.slug, index, subject.primary_channel, caption)
    path = resolve_storage_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    found = await session.execute(select(Media).where(Media.storage_key == key))
    media = found.scalar_one_or_none()
    if media is None:
        media = Media(
            storage_key=key,
            mime="image/png",
            byte_size=len(data),
            width=width,
            height=height,
            role="photo",
            alt=f"{caption}，示例图",
            note_id=note.id,
            subject_id=subject.id,
            created_by=author.id,
        )
        session.add(media)
        await session.flush()
    else:
        media.byte_size = len(data)
        media.width = width
        media.height = height
        media.alt = f"{caption}，示例图"
        media.note_id = note.id
        media.subject_id = subject.id
        media.mime = "image/png"
    if index == 0 or subject.cover_media_id is None:
        subject.cover_media_id = media.id
    return media


async def seed_works(session: AsyncSession, helper: PasswordHelper) -> int:
    users = await _users(session, helper)
    await _clear_byline_notes(session, users)
    result = await session.execute(select(Subject).where(Subject.slug != "unsorted").order_by(Subject.slug))
    subjects = list(result.scalars())
    by_slug = {subject.slug: subject for subject in subjects}
    example_rows = list((await session.execute(select(SubjectExample).order_by(SubjectExample.sort_order))).scalars())
    grouped: dict = {}
    for example in example_rows:
        grouped.setdefault(example.subject_id, []).append(example)
    plans = _plans(subjects, grouped)
    ordered = sorted(
        plans,
        key=lambda item: (item["front"] is None, item["front"] if item["front"] is not None else 0, item["slug"], item["title"]),
    )
    base = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
    written = 0
    per_slug_index: dict[str, int] = {}
    for offset, plan in enumerate(ordered):
        subject = by_slug.get(plan["slug"])
        if subject is None:
            continue
        example_id = None
        if plan.get("example"):
            found = await session.execute(
                select(SubjectExample).where(
                    SubjectExample.subject_id == subject.id,
                    SubjectExample.name == plan["example"],
                )
            )
            example = found.scalar_one_or_none()
            if example is not None:
                example_id = example.id
        index = per_slug_index.get(subject.slug, 0)
        per_slug_index[subject.slug] = index + 1
        author = users[offset % len(users)]
        published_at = base - timedelta(minutes=offset)
        note = await _upsert_note(
            session,
            subject=subject,
            author=author,
            type_="finished",
            title=plan["title"],
            body=plan["body"],
            fields={"related_note_ids": []},
            published_at=published_at,
            example_id=example_id,
        )
        await _upsert_photo(
            session,
            note=note,
            subject=subject,
            author=author,
            index=index,
            caption=subject.name,
        )
        written += 1
    return written
