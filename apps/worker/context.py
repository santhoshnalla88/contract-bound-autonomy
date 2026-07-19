"""Shared application context — one place to build every backend.

Both the FastAPI app (lifespan) and the Arq worker (``on_startup``) call
:func:`build_context` so they wire up identical, compatible backends:
database, event bus, and a graph bound to the shared checkpointer. This is what
lets the API tail events and inspect workflow state that the worker produced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.config import Settings, get_settings
from core.events import close_event_bus, configure_event_bus
from core.orchestration.builder import build_graph
from apps.worker.checkpointer import create_checkpointer
from core.observability.langsmith import configure_langsmith
from core.persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: DatabaseManager
    graph: Any
    _close_checkpointer: Callable[[], Awaitable[None]]

    async def aclose(self) -> None:
        await self._close_checkpointer()
        await self.db.dispose()
        await close_event_bus()


async def build_context(settings: Settings | None = None) -> AppContext:
    """Initialise DB, checkpointer, graph, and event bus for this process."""
    settings = settings or get_settings()

    if settings.langsmith_tracing:
        configure_langsmith()

    db = DatabaseManager(settings.effective_database_url)
    await db.initialize()

    checkpointer, close_checkpointer = await create_checkpointer(settings)
    graph = build_graph(checkpointer=checkpointer)

    configure_event_bus(settings.redis_url)

    # Populate the vector store from the knowledge base (idempotent, local embeddings).
    if settings.ingest_on_startup:
        import asyncio

        from core.knowledge.startup import ingest_knowledge

        try:
            await asyncio.to_thread(ingest_knowledge, settings)
        except Exception:
            logger.exception("Knowledge ingestion failed; RAG will fall back to no context")

    # Seed the Neo4j service-dependency graph (best-effort; graceful if unavailable).
    if settings.graph_enabled:
        import asyncio

        from core.knowledge.graph import seed_service_graph

        try:
            await asyncio.to_thread(seed_service_graph, settings)
        except Exception:
            logger.warning("Neo4j graph seed skipped (unavailable) — blast-radius enrichment disabled")

    logger.info("Application context ready (env=%s)", settings.app_env)
    return AppContext(
        settings=settings,
        db=db,
        graph=graph,
        _close_checkpointer=close_checkpointer,
    )
