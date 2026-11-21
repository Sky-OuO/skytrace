"""一条命令跑起本地演示：SQLite、种子、页面。

不读取已复制的 .env 里的 Postgres 地址，除非进程环境里已经设置了 DATABASE_URL。
"""

import asyncio
import os


def main() -> None:
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///var/skytrace.db"
    from app.config import get_settings

    get_settings.cache_clear()
    asyncio.run(_bootstrap())
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)


async def _bootstrap() -> None:
    from pathlib import Path

    from app.config import get_settings
    from app.db import ensure_schema, make_engine
    from app.seed import seed

    settings = get_settings()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        engine = make_engine(settings.database_url)
        await ensure_schema(engine)
        await engine.dispose()
    else:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
    await seed(prune=True)


if __name__ == "__main__":
    main()
