import re
from datetime import datetime, timezone
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import select

from app.models import Note, Subject

TITLES = ["成片", "踩点", "前期", "后期", "用光", "姿势"]
ANCHORS = ["finished", "spot", "pre", "post", "lighting", "posing"]
AUTHOR = {"email": "author@skytrace.local", "password": "author-demo-pass"}


def _section(html: str, anchor: str) -> str:
    match = re.search(rf'id="{anchor}"[\s\S]*?(?=<section id=|$)', html)
    assert match, anchor
    return match.group(0)


async def test_huangshan_and_window_portrait_show_six_sections(client: AsyncClient):
    for slug in ("sea-of-clouds-sunrise", "window-light-portrait"):
        response = await client.get(f"/s/{slug}")
        assert response.status_code == 200, response.text
        html = response.text
        assert "私房" not in html
        assert "思想开源" not in html
        for title in TITLES:
            assert title in html
        assert "<details open" not in html
        for anchor in ANCHORS:
            count = _section(html, anchor).count('class="guide-line"')
            assert 2 <= count <= 4, (slug, anchor, count)
    window = (await client.get("/s/window-light-portrait")).text
    head, _, _ = window.partition('id="finished"')
    assert "咖啡馆窗边" not in head
    assert "展示授权" in head
    assert "待核实" in head
    spot = _section(window, "spot")
    assert "西餐厅靠窗座" in spot
    assert "火车/高铁车窗" in spot
    assert "地点例子" in spot
    clouds = (await client.get("/s/sea-of-clouds-sunrise")).text
    assert "黄山" in clouds
    assert "待核实" in clouds
    missing = await client.get("/s/not-a-real-topic")
    assert missing.status_code == 404
    assert (await client.get("/s/unsorted")).status_code == 404
    assert (await client.get("/api/v1/subjects/not-a-real-topic/notes")).status_code == 404


async def test_work_query_redirects_to_its_topic_and_highlights(client: AsyncClient, engine: AsyncEngine):
    await client.post("/api/v1/auth/login", json=AUTHOR)
    author_id = UUID((await client.get("/api/v1/auth/me")).json()["id"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        mountain = (await session.execute(select(Subject).where(Subject.slug == "sea-of-clouds-sunrise"))).scalar_one()
        note = Note(
            author_id=author_id,
            subject_id=mountain.id,
            type="finished",
            title="黄山 清晨云海 光明顶层次",
            body="云海铺开时按亮部曝光，山脊留住纹理。",
            fields={"related_note_ids": []},
            status="approved",
            published_at=datetime.now(timezone.utc),
        )
        session.add(note)
        await session.commit()
        note_id = note.id

    wrong = await client.get(f"/s/window-light-portrait?work={note_id}", follow_redirects=False)
    assert wrong.status_code == 302
    assert wrong.headers["location"] == f"/s/sea-of-clouds-sunrise?work={note_id}"
    via_work = await client.get(f"/w/{note_id}", follow_redirects=False)
    assert via_work.status_code == 302
    assert via_work.headers["location"] == f"/s/sea-of-clouds-sunrise?work={note_id}"
    via_note = await client.get(f"/n/{note_id}", follow_redirects=False)
    assert via_note.status_code == 302
    page = await client.get(f"/s/sea-of-clouds-sunrise?work={note_id}")
    assert page.status_code == 200
    assert "正在看这一张" in page.text
    assert "黄山 清晨云海 光明顶层次" in page.text
    assert f'id="work-{note_id}"' in page.text
    assert "work-on" in page.text
    listed = await client.get("/api/v1/subjects/sea-of-clouds-sunrise/notes", params={"type": "finished"})
    assert listed.status_code == 200
    assert any(item["title"] == "黄山 清晨云海 光明顶层次" for item in listed.json()["items"])
    lighting = await client.get("/api/v1/subjects/sea-of-clouds-sunrise/notes", params={"type": "lighting"})
    assert lighting.json()["items"] == [] or all(item["type"] == "lighting" for item in lighting.json()["items"])
    assert (await client.get("/api/v1/subjects/sea-of-clouds-sunrise/notes", params={"type": "nope"})).status_code == 400
    assert (await client.get("/n/demo")).status_code == 404


async def test_empty_section_says_so(client: AsyncClient, engine: AsyncEngine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        subject = (await session.execute(select(Subject).where(Subject.slug == "mirror-reflection"))).scalar_one()
        original = dict(subject.guide or {})
        subject.guide = {**original, "posing": []}
        await session.commit()
    try:
        page = await client.get("/s/mirror-reflection")
        assert page.status_code == 200
        posing = _section(page.text, "posing")
        assert "还没有这类笔记" in posing
        assert 'class="guide-line"' not in posing
    finally:
        async with factory() as session:
            subject = (await session.execute(select(Subject).where(Subject.slug == "mirror-reflection"))).scalar_one()
            subject.guide = original
            await session.commit()
