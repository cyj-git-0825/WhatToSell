from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from sqlalchemy import text

from app.api import searches
from app.channels.registry import available_channels, get_adapter
from app.config import get_settings
from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    yield
    await app.state.arq.aclose()
    await engine.dispose()


app = FastAPI(title="WhatToSell", lifespan=lifespan)
app.include_router(searches.router)


@app.get("/health")
async def health():
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    await app.state.arq.ping()
    return {"ok": True}


@app.get("/channels")
async def channels():
    return [{"channel": c, "healthy": await get_adapter(c).healthcheck()} for c in available_channels()]
