import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = tempfile.mkdtemp(prefix="skytrace-media-")
DB_PATH = tempfile.NamedTemporaryFile(prefix="skytrace-", suffix=".db", delete=False).name

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["MEDIA_ROOT"] = MEDIA_ROOT
os.environ["MEDIA_PREVIEW_BASE_URL"] = "/media"
os.environ["MEDIA_MAX_BYTES"] = "10485760"
os.environ["SESSION_COOKIE_NAME"] = "skytrace_session"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SESSION_COOKIE_SAMESITE"] = "lax"
os.environ["DEMO_AUTHOR_EMAIL"] = "author@skytrace.local"
os.environ["DEMO_AUTHOR_PASSWORD"] = "author-demo-pass"
os.environ["DEMO_AUTHOR_NAME"] = "演示作者"
os.environ["DEMO_REVIEWER_EMAIL"] = "reviewer@skytrace.local"
os.environ["DEMO_REVIEWER_PASSWORD"] = "reviewer-demo-pass"
os.environ["DEMO_REVIEWER_NAME"] = "演示审核员"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
async def engine():
    from app.db import make_engine, make_session_factory
    from app.main import app

    db_engine = make_engine()
    app.state.engine = db_engine
    app.state.session_factory = make_session_factory(db_engine)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
async def client(engine):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    from app.db import ensure_schema, make_engine
    from app.seed import seed

    async def prepare() -> None:
        engine = make_engine()
        await ensure_schema(engine)
        await engine.dispose()
        await seed(prune=True)

    asyncio.run(prepare())
    yield
