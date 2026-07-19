"""Health and readiness check routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from core.config import get_settings
from core.events import get_event_bus

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(request: Request, response: Response) -> dict:
    """Readiness probe — verifies real dependency connectivity.

    Checks the database and (when configured) Redis. Returns 503 if any
    required dependency is unreachable so orchestrators don't route traffic to
    an unhealthy replica.
    """
    settings = get_settings()
    checks: dict[str, str] = {}

    db = getattr(request.app.state, "db", None)
    checks["database"] = "ok" if (db is not None and await db.ping()) else "unavailable"

    if settings.use_redis:
        bus = get_event_bus()
        ping = getattr(bus, "ping", None)
        checks["redis"] = "ok" if (ping is not None and await ping()) else "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
