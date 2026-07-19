"""Event bus abstraction for real-time workflow updates.

Two implementations share one interface so the SSE endpoint is backend-blind:

* :class:`InMemoryEventBus` — single-process; used for local/dev/test.
* ``RedisEventBus`` (see :mod:`core.events.redis_bus`) — Redis Streams, so the
  API and the Arq worker (separate processes/replicas) can publish and tail the
  same incident stream, with durable replay.

A :class:`Subscription` yields events one at a time with a timeout, letting the
SSE generator emit heartbeats and honour client disconnects.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WorkflowEvent(BaseModel):
    """A single real-time event emitted during incident orchestration."""

    incident_id: str
    type: str = Field(..., description="Event category, e.g. 'plan_proposed'")
    message: str = Field(..., description="Human-readable summary for the UI")
    node: str | None = Field(default=None, description="Originating graph node")
    data: dict[str, Any] = Field(default_factory=dict)
    terminal: bool = Field(default=False, description="Final event of a run")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Subscription(abc.ABC):
    """A live (optionally replayed) view of one incident's event stream."""

    @abc.abstractmethod
    async def get(self, timeout: float) -> WorkflowEvent | None:
        """Return the next event, or None if none arrived within ``timeout`` s."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Release any resources held by the subscription."""


class EventBus(abc.ABC):
    """Publish/subscribe bus keyed by incident id."""

    @abc.abstractmethod
    async def publish(self, event: WorkflowEvent) -> None: ...

    @abc.abstractmethod
    def subscribe(self, incident_id: str, replay: bool = True) -> Subscription: ...

    async def close(self) -> None:  # pragma: no cover - optional
        return None


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------
class _InMemorySubscription(Subscription):
    def __init__(self, bus: "InMemoryEventBus", incident_id: str, queue: asyncio.Queue) -> None:
        self._bus = bus
        self._incident_id = incident_id
        self._queue = queue

    async def get(self, timeout: float) -> WorkflowEvent | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        self._bus._unsubscribe(self._incident_id, self._queue)


class InMemoryEventBus(EventBus):
    def __init__(self, history_limit: int = 500) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._history: dict[str, list[WorkflowEvent]] = {}
        self._history_limit = history_limit

    async def publish(self, event: WorkflowEvent) -> None:
        history = self._history.setdefault(event.incident_id, [])
        history.append(event)
        if len(history) > self._history_limit:
            del history[: len(history) - self._history_limit]
        for queue in list(self._subscribers.get(event.incident_id, set())):
            queue.put_nowait(event)

    def subscribe(self, incident_id: str, replay: bool = True) -> Subscription:
        queue: asyncio.Queue = asyncio.Queue()
        # Snapshot + register happen with no await between them, so no event can
        # be lost or duplicated on a single event loop.
        if replay:
            for event in self._history.get(incident_id, []):
                queue.put_nowait(event)
        self._subscribers.setdefault(incident_id, set()).add(queue)
        return _InMemorySubscription(self, incident_id, queue)

    def _unsubscribe(self, incident_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(incident_id)
        if subs:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(incident_id, None)

    def history(self, incident_id: str) -> list[WorkflowEvent]:
        return list(self._history.get(incident_id, []))
