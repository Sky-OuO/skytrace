from uuid import UUID

from app.models import Subject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

AUTHOR = {"email": "author@skytrace.local", "password": "author-demo-pass"}
REVIEWER = {"email": "reviewer@skytrace.local", "password": "reviewer-demo-pass"}


def _png() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (12, 16), (90, 140, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_publish_form_is_short_and_preselects_topic(client):
    await client.post("/login", data={**AUTHOR, "next": "/publish?subject=window-portrait"})
    page = await client.get("/publish?subject=window-portrait")
    assert page.status_code == 200
    assert "一句拍摄说明" in page.text
    assert "窗边人像" in page.text
    assert 'value="window-portrait"' in page.text
    assert "待归类" in page.text
    assert "私房" not in page.text
    picker = await client.get("/partials/topic-picker", params={"q": "西餐厅"})
    assert "窗边人像" in picker.text


async def test_author_submits_and_reviewer_approves_into_feed(client, engine):
    await client.post("/api/v1/auth/login", json=AUTHOR)
    page = await client.post(
        "/publish",
        data={
            "subject_slug": "window-portrait",
            "type": "finished",
            "body": "阴天侧窗，人侧坐，近处暖灯关掉。",
            "portrait_auth": "on",
            "action": "submit",
        },
        files={"image": ("shot.png", _png(), "image/png")},
        follow_redirects=False,
    )
    assert page.status_code == 303, page.text
    assert page.headers["location"].startswith("/me")
    me = await client.get("/me?notice=pending")
    assert "待审" in me.text
    assert "阴天侧窗，人侧坐" in me.text
    feed = (await client.get("/api/v1/feed", params={"channel": "portrait"})).json()
    assert all("阴天侧窗，人侧坐" not in item["title"] + item["tip"] for item in feed["items"])

    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/login", json=REVIEWER)
    tickets = (await client.get("/api/v1/review/tickets")).json()
    mine = next(item for item in tickets["items"] if "阴天侧窗，人侧坐" in item["note"]["title"])
    decision = await client.post(
        f"/api/v1/review/tickets/{mine['id']}/decide",
        json={"decision": "approved"},
    )
    assert decision.status_code == 200, decision.text
    await client.post("/api/v1/auth/logout")
    visible = (await client.get("/api/v1/subjects/window-portrait/notes", params={"type": "finished"})).json()
    assert any("阴天侧窗，人侧坐" in item["title"] for item in visible["items"])
    home = await client.get("/")
    assert "阴天侧窗，人侧坐" in home.text


async def test_unsorted_cannot_be_approved_until_reassigned(client, engine):
    await client.post("/api/v1/auth/login", json=AUTHOR)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        subject = (await session.execute(select(Subject).where(Subject.slug == "unsorted"))).scalar_one()
        subject_id = subject.id
    created = await client.post(
        "/api/v1/notes",
        json={
            "subject_id": str(subject_id),
            "type": "finished",
            "body": "还不知道挂哪一页。",
            "portrait_auth_accepted": True,
        },
    )
    assert created.status_code == 200, created.text
    note_id = created.json()["id"]
    await client.post(
        "/api/v1/media",
        data={"note_id": note_id, "role": "photo"},
        files={"file": ("x.png", _png(), "image/png")},
    )
    submitted = await client.post(f"/api/v1/notes/{note_id}/submit")
    assert submitted.status_code == 200
    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/login", json=REVIEWER)
    tickets = (await client.get("/api/v1/review/tickets")).json()
    ticket = next(item for item in tickets["items"] if item["note"]["id"] == note_id)
    blocked = await client.post(f"/api/v1/review/tickets/{ticket['id']}/decide", json={"decision": "approved"})
    assert blocked.status_code == 422
    async with factory() as session:
        target = (await session.execute(select(Subject).where(Subject.slug == "huangshan"))).scalar_one()
        target_id = target.id
    moved = await client.post(
        f"/api/v1/review/tickets/{ticket['id']}/decide",
        json={"decision": "approved", "subject_id": str(target_id)},
    )
    assert moved.status_code == 200, moved.text
    listed = (await client.get("/api/v1/subjects/huangshan/notes", params={"type": "finished"})).json()
    assert any(item["id"] == note_id for item in listed["items"])
    assert UUID(note_id)
