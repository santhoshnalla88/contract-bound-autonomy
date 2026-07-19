"""LangSmith observability configuration.

Configures environment variables for LangSmith tracing so that every
LangChain / LangGraph invocation is automatically traced.  Provides
helpers for attaching structured metadata and tags to traces, enabling
filtering and correlation in the LangSmith dashboard.

Usage::

    from core.observability.langsmith import configure_langsmith

    configure_langsmith()  # call once at startup
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical tag set for all traces emitted by this system
# ---------------------------------------------------------------------------
_TRACE_TAGS: list[str] = [
    "autonomous-remediation",
    "contract-bound",
    "rag",
    "guardrail",
    "mcp",
    "human-in-the-loop",
]


def configure_langsmith() -> None:
    """Set LangSmith environment variables from application settings.

    Reads ``langsmith_tracing``, ``langsmith_api_key``, and
    ``langsmith_project`` from ``Settings`` and propagates them as
    the environment variables that the LangChain/LangGraph SDK reads
    at runtime.

    Should be called **once** during application startup (e.g. in the
    FastAPI ``lifespan`` handler or at the top of a CLI entry-point).
    """
    settings = get_settings()

    tracing_enabled = "true" if settings.langsmith_tracing else "false"

    os.environ["LANGSMITH_TRACING"] = tracing_enabled
    os.environ["LANGCHAIN_TRACING_V2"] = tracing_enabled
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key

    logger.info(
        "LangSmith tracing configured — enabled=%s, project=%s",
        tracing_enabled,
        settings.langsmith_project,
    )


def get_trace_metadata(
    incident_id: str,
    service: str,
    environment: str,
    contract_version: Optional[str] = None,
) -> dict[str, Any]:
    """Build a metadata dict for attaching to LangSmith traces.

    This metadata appears in the LangSmith dashboard and enables
    filtering by incident, service, environment, and contract version.

    Args:
        incident_id: Unique incident identifier (e.g. ``INC-1001``).
        service: Name of the affected service.
        environment: Deployment environment (e.g. ``production``).
        contract_version: Optional semantic version of the governing
            operational contract.

    Returns:
        Dict suitable for passing as ``metadata`` to LangChain
        ``RunnableConfig`` or LangGraph invocation kwargs.
    """
    metadata: dict[str, Any] = {
        "incident_id": incident_id,
        "service": service,
        "environment": environment,
        "system": "contract-bound-autonomy",
    }

    if contract_version is not None:
        metadata["contract_version"] = contract_version

    return metadata


def get_trace_tags() -> list[str]:
    """Return the canonical set of tags for LangSmith traces.

    Tags enable cross-cutting filtering in the LangSmith dashboard
    regardless of project or metadata values.

    Returns:
        List of tag strings:
        ``autonomous-remediation``, ``contract-bound``, ``rag``,
        ``guardrail``, ``mcp``, ``human-in-the-loop``.
    """
    return list(_TRACE_TAGS)
