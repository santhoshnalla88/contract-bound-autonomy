"""Job submission — durable Arq queue in production, inline task locally.

When Redis is configured the API enqueues jobs onto Arq and a separate worker
process runs the workflow (survives API restarts, scales horizontally). Without
Redis the workflow runs as an in-process asyncio task so the app still works
with a single ``uvicorn`` command.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.orchestration.orchestrator import run_workflow
from core.persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


async def _safe_run(db: DatabaseManager, **kwargs: Any) -> None:
    try:
        await run_workflow(db, **kwargs)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Inline workflow task failed for %s", kwargs.get("incident_id"))


async def submit_workflow(
    db: DatabaseManager,
    arq: Any | None,
    incident_id: str,
    incident_data: dict[str, Any] | None = None,
    resume: str | None = None,
    actor: str | None = None,
) -> None:
    """Enqueue (Arq) or launch inline the workflow run/resume."""
    if arq is not None:
        await arq.enqueue_job(
            "run_workflow_job",
            incident_id=incident_id,
            incident_data=incident_data,
            resume=resume,
            actor=actor,
        )
        logger.info("Enqueued workflow job for %s (resume=%s)", incident_id, resume)
    else:
        asyncio.create_task(
            _safe_run(
                db,
                incident_id=incident_id,
                incident_data=incident_data,
                resume=resume,
                actor=actor,
            )
        )
