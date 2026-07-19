"""LangGraph checkpointer factory.

Production uses ``AsyncPostgresSaver`` (durable, shared between the API and the
worker) via a connection pool kept open for the process lifetime. Local/test
uses an in-memory saver. The returned closer must be awaited on shutdown.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langgraph.checkpoint.memory import MemorySaver

from core.config import Settings

logger = logging.getLogger(__name__)


async def create_checkpointer(settings: Settings) -> tuple[Any, Callable[[], Awaitable[None]]]:
    """Return ``(checkpointer, aclose)`` for the configured backend."""
    if settings.checkpointer_url:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = AsyncConnectionPool(
            conninfo=settings.checkpointer_url,
            max_size=20,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await pool.open()
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # idempotent: creates checkpoint tables if absent
        logger.info("Checkpointer: Postgres (AsyncPostgresSaver)")

        async def _close() -> None:
            await pool.close()

        return saver, _close

    logger.info("Checkpointer: in-memory (MemorySaver)")

    async def _noop() -> None:
        return None

    return MemorySaver(), _noop
