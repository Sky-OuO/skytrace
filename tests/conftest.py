import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = tempfile.mkdtemp(prefix="skytrace-media-")

os.environ["DATABASE_URL"] = "postgresql+asyncpg://skytrace:skytrace@127.0.0.1:5432/skytrace_test"
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


def _psql(database: str, sql: str) -> None:
    subprocess.run(
        ["psql", "-h", "127.0.0.1", "-U", "skytrace", "-d", database, "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True,
        cwd=ROOT,
        env={**os.environ, "PGPASSWORD": "skytrace"},
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _psql(
        "skytrace",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'skytrace_test' AND pid <> pg_backend_pid();",
    )
    _psql("skytrace", "DROP DATABASE IF EXISTS skytrace_test;")
    _psql("skytrace", "CREATE DATABASE skytrace_test;")
    env = os.environ.copy()
    for args in (
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "app.seed"],
    ):
        subprocess.run(args, check=True, cwd=ROOT, env=env)
    yield
