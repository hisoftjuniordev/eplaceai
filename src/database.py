from __future__ import annotations

import asyncpg
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from src.config import settings

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(_server: Any) -> AsyncGenerator[None, None]:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_min_pool,
        max_size=settings.db_max_pool,
    )
    try:
        yield
    finally:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised — lifespan not entered")
    return _pool


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    return await pool().fetchrow(query, *args)


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    return await pool().fetch(query, *args)


async def execute(query: str, *args: Any) -> str:
    return await pool().execute(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    return await pool().fetchval(query, *args)
