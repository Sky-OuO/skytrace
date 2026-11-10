"""ARQ worker 骨架。

ARQ 要求至少注册一个函数，否则进程拒绝启动。`reserved_idle` 只为了满足这个约束。
Web 进程不会入队。第 9 天之前不要往队列里投任务。
"""

import logging

from arq.connections import RedisSettings

from app.config import get_settings

logger = logging.getLogger("arq.worker")


async def reserved_idle(ctx) -> None:
    """占位函数。不要投递。"""
    del ctx
    return None


async def startup(ctx) -> None:
    del ctx
    logger.info("SkyTrace ARQ worker 已启动，当前空转；第 9 天之前不投递任务。")


async def shutdown(ctx) -> None:
    del ctx


class WorkerSettings:
    functions = [reserved_idle]
    cron_jobs = []
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "skytrace"
    # 空队列时尽快结束 burst，方便验收 worker 能启动。
    poll_delay = 0.1
