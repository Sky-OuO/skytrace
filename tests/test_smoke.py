import socket
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.domain import NOTE_FIELD_MODELS, note_field_keys
from app.errors import ApiError
from app.main import app
from app.models import Note, Subject
from app.services.storage import resolve_storage_path

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = {"email": "author@skytrace.local", "password": "author-demo-pass"}
REVIEWER = {"email": "reviewer@skytrace.local", "password": "reviewer-demo-pass"}

HERO_SUBJECTS = {"huangshan", "window-portrait", "window-light-studio", "shanghai-bund"}
EXPECTED_TAGS = {
    "indoor",
    "outdoor",
    "mixed",
    "casual",
    "cos",
    "street",
    "travel",
    "spring",
    "summer",
    "autumn",
    "winter",
    "dawn",
    "morning",
    "midday",
    "dusk",
    "night",
    "sunny",
    "cloudy",
    "overcast",
    "rain",
    "snow",
    "fog",
    "window-light",
    "available-light",
    "studio-light",
    "night-light",
    "mixed-light",
}
EXPECTED_FIELD_KEYS = {
    "finished": {"related_note_ids"},
    "spot": {"arrival", "time_window", "focal_length", "exposure", "common_failures", "exif"},
    "pre": {"tickets_permits", "transport_arrival", "season_window", "gear_advice", "safety_tips", "common_failures"},
    "post": {"white_balance_exposure", "crop_advice", "material_color", "common_failures"},
    "lighting": {"key_light", "fill_light", "rim_light", "ambient_light", "common_failures"},
    "posing": {"body_orientation", "contact_points", "light_relationship", "common_failures"},
}
API_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/vocab",
    "/api/v1/channels",
    "/api/v1/subjects",
    "/api/v1/subjects/{slug}",
    "/api/v1/media",
    "/api/v1/notes",
    "/api/v1/notes/{note_id}",
    "/api/v1/notes/{note_id}/submit",
    "/api/v1/me/notes",
    "/api/v1/review/tickets",
    "/api/v1/review/tickets/{ticket_id}/decide",
    "/api/v1/search",
    "/api/v1/search/parse",
    "/api/v1/publish/suggest",
}
PUBLIC_PAGES = ["/", "/c/landscape", "/c/portrait", "/search", "/login", "/s/huangshan", "/s/window-portrait", "/n/demo"]


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncClient:
    del engine
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def test_note_field_keys_match_spec():
    assert set(NOTE_FIELD_MODELS) == set(EXPECTED_FIELD_KEYS)
    for note_type, keys in EXPECTED_FIELD_KEYS.items():
        assert note_field_keys(note_type) == keys


def test_templates_do_not_use_forbidden_word():
    root = ROOT / "app" / "web" / "templates"
    for path in root.rglob("*.html"):
        assert "私房" not in path.read_text(encoding="utf-8")


def test_data_model_mentions_tables_and_field_keys():
    text_value = (ROOT / "DATA_MODEL.md").read_text(encoding="utf-8")
    for name in [
        "users",
        "access_tokens",
        "subjects",
        "notes",
        "media",
        "review_tickets",
        "tags",
        "subject_tags",
        "note_tags",
        "password_hash",
        "condition_axes",
        "portrait_auth_accepted",
        "search_vector",
    ]:
        assert name in text_value
    for keys in EXPECTED_FIELD_KEYS.values():
        for key in keys:
            assert key in text_value


def test_web_process_does_not_enqueue_jobs():
    for path in (ROOT / "app").rglob("*.py"):
        if path.name == "worker.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "enqueue_job" not in source
        assert "create_pool" not in source


def test_storage_rejects_path_escape(tmp_path: Path):
    with pytest.raises(ApiError) as caught:
        resolve_storage_path("../secrets.txt", root=tmp_path)
    assert caught.value.code == "VALIDATION_ERROR"


def test_arq_worker_starts_idle():
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.3):
            pass
    except OSError:
        pytest.skip("本机没有 Redis，worker 空转验收跳过")
    completed = subprocess.run(
        [sys.executable, "-m", "arq", "app.worker.WorkerSettings", "--burst"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "reserved_idle" in completed.stderr + completed.stdout


async def test_schema_indexes_and_search_vector(engine: AsyncEngine):
    def columns(sync_conn, table: str) -> set[str]:
        return {column["name"] for column in inspect(sync_conn).get_columns(table)}

    async with engine.connect() as conn:
        subject_columns = await conn.run_sync(columns, "subjects")
        note_columns = await conn.run_sync(columns, "notes")
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    assert {"tagline", "aliases", "guide"} <= subject_columns
    assert "example_id" in note_columns
    assert "subject_examples" in tables
    migration = (ROOT / "alembic" / "versions" / "0002_topics.py").read_text(encoding="utf-8")
    assert "subject_examples" in migration
    assert "ix_subjects_search_vector" in (ROOT / "alembic" / "versions" / "0001_initial.py").read_text(encoding="utf-8")


async def test_public_pages_and_navigation(client: AsyncClient):
    for path in PUBLIC_PAGES:
        response = await client.get(path)
        assert response.status_code == 200, path
        assert "私房" not in response.text
    home = await client.get("/")
    for label in ["首页", "风光", "人像", "搜索", "记一笔", "登录"]:
        assert label in home.text
    assert "思想开源" not in home.text
    assert "人文" not in home.text
    ideas = await client.get("/ideas")
    assert ideas.status_code == 200
    assert "本期后置" in ideas.text
    assert "无功能" in ideas.text
    culture = await client.get("/c/culture")
    assert culture.status_code == 404
    missing = await client.get("/c/not-a-channel")
    assert missing.status_code == 404
    publish = await client.get("/publish", follow_redirects=False)
    assert publish.status_code == 303
    assert publish.headers["location"].startswith("/login")
    review = await client.get("/review")
    assert review.status_code == 403
    assert "审核员" in review.text


async def test_login_logout_and_review_gate(client: AsyncClient):
    bad = await client.post("/api/v1/auth/login", json={"email": AUTHOR["email"], "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "UNAUTHENTICATED"
    anon = await client.get("/api/v1/auth/me")
    assert anon.status_code == 401

    logged_in = await client.post("/api/v1/auth/login", json=AUTHOR)
    assert logged_in.status_code == 200
    body = logged_in.json()
    assert body["display_name"] == "演示作者"
    assert body["role"] == "author"
    assert "skytrace_session" in logged_in.cookies
    me = await client.get("/api/v1/auth/me")
    assert me.json()["role"] == "author"
    author_page = await client.get("/")
    assert "演示作者" in author_page.text
    assert (await client.get("/review")).status_code == 403
    publish = await client.get("/publish")
    assert publish.status_code == 200
    assert "发布表单还没做" in publish.text

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    form_login = await client.post("/login", data={**AUTHOR, "next": "/publish"}, follow_redirects=True)
    assert form_login.status_code == 200
    assert "发布表单还没做" in form_login.text
    await client.post("/logout")

    await client.post("/api/v1/auth/login", json=REVIEWER)
    review = await client.get("/review")
    assert review.status_code == 200
    assert "审核台" in review.text
    tickets = await client.get("/api/v1/review/tickets")
    assert tickets.status_code == 200
    assert tickets.json()["items"] == []
    await client.post("/api/v1/auth/logout")


async def test_vocab_channels_and_subjects(client: AsyncClient):
    vocab = await client.get("/api/v1/vocab")
    assert vocab.status_code == 200
    payload = vocab.json()
    assert [item["code"] for item in payload["facets"]] == [
        "environment",
        "style",
        "season",
        "time_of_day",
        "weather",
        "light",
    ]
    assert {tag["slug"] for tag in payload["tags"]} == EXPECTED_TAGS
    assert "私房" not in vocab.text
    channels = await client.get("/api/v1/channels")
    counts = {item["code"]: item["subject_count"] for item in channels.json()["items"]}
    assert set(counts) == {"landscape", "portrait"}
    assert counts["landscape"] >= 30
    assert counts["portrait"] >= 4
    assert channels.json()["pageSize"] == 20
    subjects = await client.get("/api/v1/subjects", params={"pageSize": 50})
    body = subjects.json()
    assert 30 <= body["total"] <= 50
    slugs = {item["slug"] for item in body["items"]}
    assert HERO_SUBJECTS <= slugs
    assert "unsorted" not in slugs
    assert "cafe-window" not in slugs
    names = {item["slug"]: item["name"] for item in body["items"]}
    assert names["window-portrait"] == "窗边人像"
    assert names["window-light-studio"] == "窗光棚"
    portrait = await client.get("/api/v1/subjects", params={"channel": "portrait", "pageSize": 50})
    assert portrait.json()["total"] == counts["portrait"]
    culture = await client.get("/api/v1/subjects", params={"channel": "culture"})
    assert culture.status_code == 400
    unknown = await client.get("/api/v1/subjects", params={"channel": "studio"})
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "VALIDATION_ERROR"
    detail = await client.get("/api/v1/subjects/huangshan")
    assert detail.json()["condition_axes"] == ["季节", "时段", "天气"]
    assert len(detail.json()["guide"]["finished_points"]) >= 2
    hidden = await client.get("/api/v1/subjects/unsorted")
    assert hidden.status_code == 404
    missing = await client.get("/api/v1/subjects/missing-subject")
    assert missing.status_code == 404
    partial = await client.get("/partials/channel-counts")
    assert f"风光 {counts['landscape']}" in partial.text
    assert f"人像 {counts['portrait']}" in partial.text
    assert "人文" not in partial.text


async def test_stub_write_routes_use_agreed_errors(client: AsyncClient):
    upload = await client.post("/api/v1/media", files={"file": ("a.png", b"not-an-image", "image/png")})
    assert upload.status_code == 401
    assert upload.json()["error"]["code"] == "UNAUTHENTICATED"
    assert (await client.post("/api/v1/notes", json={"title": "x"})).status_code == 401
    assert (await client.get("/api/v1/search")).json()["items"] == []
    parsed = await client.post("/api/v1/search/parse", json={"q": "黄昏的西湖"})
    assert parsed.status_code == 422
    assert parsed.json()["error"]["code"] == "UNPROCESSABLE"
    assert (await client.post("/api/v1/publish/suggest", json={})).status_code == 401
    assert (await client.get("/api/v1/me/notes")).status_code == 401
    assert (await client.get("/api/v1/review/tickets")).status_code == 401

    await client.post("/api/v1/auth/login", json=AUTHOR)
    missing_subject = await client.post("/api/v1/notes", json={"title": "没有对象"})
    assert missing_subject.status_code == 422
    assert "未选对象" in missing_subject.json()["error"]["message"]
    absent = await client.post("/api/v1/notes", json={"subject_id": "00000000-0000-0000-0000-000000000000"})
    assert absent.status_code == 404
    suggest = await client.post("/api/v1/publish/suggest", json={"title": "x"})
    assert suggest.status_code == 422
    assert (await client.get("/api/v1/review/tickets")).status_code == 403
    missing_note = await client.get("/api/v1/notes/00000000-0000-0000-0000-000000000000")
    assert missing_note.status_code == 404
    assert missing_note.json()["error"]["code"] == "NOT_FOUND"
    await client.post("/api/v1/auth/logout")

    schema = (await client.get("/openapi.json")).json()
    assert API_PATHS <= set(schema["paths"])


async def test_media_upload_roundtrip_and_size_limit(client: AsyncClient, tmp_path: Path):
    del tmp_path
    await client.post("/api/v1/auth/login", json=AUTHOR)
    image = _png_bytes()
    uploaded = await client.post("/api/v1/media", files={"file": ("window.png", image, "image/png")}, data={"role": "photo", "alt": "窗边"})
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert set(body) >= {"id", "storage_key", "preview_url"}
    assert body["preview_url"].startswith("/media/")
    assert body["width"] == 8
    assert body["height"] == 6
    fetched = await client.get(body["preview_url"])
    assert fetched.status_code == 200
    assert fetched.content == image
    settings = get_settings()
    previous = settings.media_max_bytes
    settings.media_max_bytes = 32
    try:
        too_big = await client.post("/api/v1/media", files={"file": ("big.png", b"x" * 64, "image/png")})
    finally:
        settings.media_max_bytes = previous
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    await client.post("/api/v1/auth/logout")


async def test_public_note_read_and_submit_guards(client: AsyncClient, engine: AsyncEngine):
    await client.post("/api/v1/auth/login", json=AUTHOR)
    author_id = UUID((await client.get("/api/v1/auth/me")).json()["id"])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        subject = (await session.exec(select(Subject).where(Subject.slug == "window-portrait"))).one()
        mountain = (await session.exec(select(Subject).where(Subject.slug == "huangshan"))).one()
        draft = Note(
            author_id=author_id,
            subject_id=subject.id,
            type="posing",
            title="未授权草稿",
            body="线稿",
            fields={"body_orientation": "侧身"},
            status="draft",
            portrait_auth_accepted=False,
        )
        spot = Note(
            author_id=author_id,
            subject_id=mountain.id,
            type="spot",
            title="山门机位",
            body="到达说明",
            fields={"arrival": "南大门"},
            status="draft",
            portrait_auth_accepted=False,
        )
        approved = Note(
            author_id=author_id,
            subject_id=subject.id,
            type="finished",
            title="已过审窗光",
            body="短说明",
            fields={"related_note_ids": []},
            status="approved",
            portrait_auth_accepted=True,
        )
        session.add(draft)
        session.add(spot)
        session.add(approved)
        await session.commit()
        draft_id, spot_id, approved_id = draft.id, spot.id, approved.id

    hidden = await client.get(f"/api/v1/notes/{draft_id}")
    assert hidden.status_code == 404
    visible = await client.get(f"/api/v1/notes/{approved_id}")
    assert visible.status_code == 200
    assert visible.json()["title"] == "已过审窗光"
    assert visible.json()["author"]["display_name"] == "演示作者"
    portrait = await client.post(f"/api/v1/notes/{draft_id}/submit")
    assert portrait.status_code == 422
    assert "肖像授权" in portrait.json()["error"]["message"]
    postponed = await client.post(f"/api/v1/notes/{spot_id}/submit")
    assert postponed.status_code == 422
    assert "后续天数" in postponed.json()["error"]["message"]
    conflict = await client.post(f"/api/v1/notes/{approved_id}/submit")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"

    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/login", json=REVIEWER)
    forbidden = await client.patch(f"/api/v1/notes/{draft_id}", json={"title": "改别人的稿"})
    assert forbidden.status_code == 403
    await client.post("/api/v1/auth/logout")


def _png_bytes() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), (180, 90, 40)).save(buffer, format="PNG")
    return buffer.getvalue()
