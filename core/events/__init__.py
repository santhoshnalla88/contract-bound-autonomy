"""Real-time workflow event streaming package.

The process-wide event bus is configured once at startup (API lifespan or Arq
worker startup) via :func:`configure_event_bus`, then retrieved anywhere with
:func:`get_event_bus`. If never configured (e.g. a bare unit test), an
in-memory bus is created lazily.
"""

from __future__ import annotations

import logging

from core.events.bus import EventBus, InMemoryEventBus, Subscription, WorkflowEvent

logger = logging.getLogger(__name__)

_bus: EventBus | None = None


def configure_event_bus(redis_url: str = "") -> EventBus:
    """Create and install the process event bus (Redis if a URL is given)."""
    global _bus
    if redis_url:
        from core.events.redis_bus import RedisEventBus

        _bus = RedisEventBus(redis_url)
        logger.info("Event bus: Redis Streams")
    else:
        _bus = InMemoryEventBus()
        logger.info("Event bus: in-memory")
    return _bus


def get_event_bus() -> EventBus:
    """Return the configured event bus, defaulting to in-memory."""
    global _bus
    if _bus is None:
        _bus = InMemoryEventBus()
    return _bus


async def close_event_bus() -> None:
    global _bus
    if _bus is not None:
        await _bus.close()
        _bus = None


__all__ = [
    "EventBus",
    "Subscription",
    "WorkflowEvent",
    "configure_event_bus",
    "get_event_bus",
    "close_event_bus",
]
