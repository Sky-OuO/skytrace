"""关键词搜索。中文用 LIKE 做子串匹配，不依赖分词扩展。"""

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import UNSORTED_SLUG
from app.models import Note, Subject, SubjectExample, User
from app.services.publishing import find_topics

PARSE_RULES = (
    ("西湖", "landscape", "西湖"),
    ("黄山", "landscape", "黄山"),
    ("西餐厅", "portrait", "西餐厅"),
    ("火车", "portrait", "火车窗边"),
    ("窗", "portrait", "窗边"),
)


def parse_query(text: str) -> dict:
    query = text.strip()
    for needle, channel, rewritten in PARSE_RULES:
        if needle and needle in query:
            return {"q": rewritten, "channel": channel, "matched": True}
    return {"q": query, "channel": None, "matched": False}


async def search_works(session: AsyncSession, query: str, *, limit: int = 12) -> list[dict]:
    text = query.strip()
    if not text:
        return []
    like = f"%{text}%"
    rows = (
        await session.execute(
            select(Note, Subject, User)
            .join(Subject, Note.subject_id == Subject.id)
            .join(User, Note.author_id == User.id)
            .outerjoin(SubjectExample, Note.example_id == SubjectExample.id)
            .where(
                Note.status == "approved",
                Note.type == "finished",
                Subject.slug != UNSORTED_SLUG,
                or_(
                    Note.title.like(like),
                    Note.body.like(like),
                    Subject.name.like(like),
                    cast(Subject.aliases, String).like(like),
                    SubjectExample.name.like(like),
                ),
            )
            .order_by(Note.published_at.desc())
            .limit(limit)
        )
    ).all()
    items = []
    seen: set = set()
    for note, subject, author in rows:
        if note.id in seen:
            continue
        seen.add(note.id)
        items.append(
            {
                "id": note.id,
                "title": note.title,
                "tip": (note.body or "").strip(),
                "slug": subject.slug,
                "topic": subject.name,
                "author": author.display_name,
            }
        )
    return items


async def search_all(session: AsyncSession, query: str) -> dict:
    text = query.strip()
    if not text:
        return {"topics": [], "works": [], "items": []}
    topics = await find_topics(session, text, limit=12)
    topic_items = [
        {
            "kind": "topic",
            "slug": topic.slug,
            "name": topic.name,
            "tagline": topic.tagline,
            "channel": topic.primary_channel,
        }
        for topic in topics
    ]
    works = await search_works(session, text)
    work_items = [{**item, "kind": "work"} for item in works]
    return {"topics": topic_items, "works": works, "items": topic_items + work_items}
