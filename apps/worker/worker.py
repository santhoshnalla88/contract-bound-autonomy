"""Arq worker entry point — runs remediation workflows out-of-process.

Started via ``arq apps.worker.worker.WorkerSettings``. It builds the same
:class:`AppContext` as the API (Postgres checkpointer, Redis event bus), so the
graph state and events it produces are visible to the API. This is what makes
the system durable and horizontally scalable: the API stays responsive while
workers execute (potentially long-running) remediations.
"""

from __future__ import annotations

import logging
from typing import Any

from arq.connections import RedisSettings

from core.config import get_settings
from core.orchestration.orchestrator import run_workflow
from apps.worker.context import build_context

logger = logging.getLogger(__name__)


async def run_workflow_job(
    ctx: dict[str, Any],
    incident_id: str,
    incident_data: dict[str, Any] | None = None,
    resume: str | None = None,
    actor: str | None = None,
) -> None:
    """Arq task: run or resume an incident workflow."""
    appctx = ctx["appctx"]
    await run_workflow(
        appctx.db,
        incident_id=incident_id,
        incident_data=incident_data,
        resume=resume,
        actor=actor,
    )


async def _startup(ctx: dict[str, Any]) -> None:
    logging.basicConfig(level=logging.INFO)
    ctx["appctx"] = await build_context(get_settings())
    logger.info("Arq worker started.")


async def _shutdown(ctx: dict[str, Any]) -> None:
    appctx = ctx.get("appctx")
    if appctx is not None:
        await appctx.aclose()
    logger.info("Arq worker stopped.")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL must be set to run the Arq worker.")
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    """Arq worker configuration."""

    functions = [run_workflow_job]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 900  # seconds — long remediations allowed
