import os

# Point the app at a throwaway database before any app module creates the engine.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://wts:wts@localhost:55432/wts_test"

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402, F401
from app.channels import registry  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _database():
    conn = await asyncpg.connect("postgresql://wts:wts@localhost:55432/wts")
    if not await conn.fetchval("select 1 from pg_database where datname = 'wts_test'"):
        await conn.execute("create database wts_test")
    await conn.close()

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean():
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as c:
        await c.execute(text(f"truncate {tables} cascade"))
    registry._adapters.clear()


@pytest.fixture
async def session():
    async with SessionLocal() as s:
        yield s
