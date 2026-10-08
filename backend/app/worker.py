"""arq worker. Run with: uv run arq app.worker.WorkerSettings"""

import uuid

from arq.connections import RedisSettings

from app.config import get_settings
from app.pipeline.run import run_search


async def run_search_job(ctx: dict, search_id: str) -> None:
    await run_search(uuid.UUID(search_id))


class WorkerSettings:
    functions = [run_search_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 60 * 30  # deep tier can take ~20 minutes
    max_jobs = 4
