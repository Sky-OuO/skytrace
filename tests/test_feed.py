import hashlib
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain import UNSORTED_SLUG
from app.models import Media, Note, Subject
from app.services.storage import resolve_storage_path


async def test_home_feed_is_two_column_and_mixes_topics(client):
    home = await client.get("/")
    assert home.status_code == 200, home.text
    html = home.text
    assert 'class="masonry"' in html
    assert "<details open" not in html
    assert "筛选" in html
    assert "示例图" in html
    assert "窗边人像" in html
    assert "黄山" in html
    assert "阴天窗光作主光" in html
    assert 'href="/s/window-portrait?work=' in html
    assert "私房" not in html
    assert "思想开源" not in html
    portrait = await client.get("/", params={"channel": "portrait"})
    assert "窗边人像" in portrait.text
    assert "黄山 清晨云海" not in portrait.text


async def test_feed_cursor_channel_and_coverage(client, engine):
    first = (await client.get("/api/v1/feed")).json()
    assert len(first["items"]) == 6
    assert first["nextCursor"]
    assert {item["channel"] for item in first["items"]} == {"portrait", "landscape"}
    assert all(item["image"] for item in first["items"])
    assert all(item["tip"] and item["topic"] for item in first["items"])
    second = (await client.get("/api/v1/feed", params={"cursor": first["nextCursor"]})).json()
    assert set(item["id"] for item in first["items"]).isdisjoint(item["id"] for item in second["items"])
    partial = await client.get("/partials/feed", params={"cursor": first["nextCursor"]})
    assert partial.status_code == 200
    assert first["items"][0]["title"] not in partial.text
    assert (await client.get("/api/v1/feed", params={"cursor": "not-a-cursor"})).status_code == 400
    portrait = (await client.get("/api/v1/feed", params={"channel": "portrait"})).json()
    assert portrait["items"]
    assert {item["channel"] for item in portrait["items"]} == {"portrait"}
    assert (await client.get("/api/v1/feed", params={"channel": "culture"})).status_code == 400

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            await session.execute(
                select(Subject.slug, func.count(Note.id))
                .join(Note, Note.subject_id == Subject.id)
                .where(Note.type == "finished", Note.status == "approved", Subject.slug != UNSORTED_SLUG)
                .group_by(Subject.slug)
            )
        ).all()
        subjects = (
            await session.execute(select(func.count()).select_from(Subject).where(Subject.slug != UNSORTED_SLUG))
        ).scalar_one()
    counts = Counter({slug: count for slug, count in rows})
    assert len(counts) == subjects
    assert min(counts.values()) >= 1
    assert counts["huangshan"] >= 3
    assert counts["window-portrait"] >= 3
    async with factory() as session:
        keys = list(
            (
                await session.execute(select(Media.storage_key).where(Media.storage_key.like("seed/%")))
            ).scalars()
        )
    hashes = set()
    for key in keys:
        hashes.add(hashlib.sha256(resolve_storage_path(key).read_bytes()).hexdigest())
    assert len(keys) >= subjects
    assert len(hashes) == len(keys)
