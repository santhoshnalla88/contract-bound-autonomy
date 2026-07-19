"""Redis Streams implementation of the event bus.

Each incident gets a stream ``events:{incident_id}``. Publishing is an ``XADD``;
subscribing tails via blocking ``XREAD``. Because it is Redis-backed, the API
process and the Arq worker process share the same streams — the worker runs the
graph and publishes events; the API's SSE endpoint tails them. Streams are
capped (``MAXLEN``) and expired so history is bounded.
"""

from __future__ import annotations

import collections
import json
import logging

from redis.asyncio import Redis

from core.events.bus import EventBus, Subscription, WorkflowEvent

logger = logging.getLogger(__name__)

_STREAM_MAXLEN = 2000
_STREAM_TTL_SECONDS = 86_400  # 1 day


def _key(incident_id: str) -> str:
    return f"events:{incident_id}"


class _RedisSubscription(Subscription):
    def __init__(self, redis: Redis, incident_id: str, last_id: str) -> None:
        self._redis = redis
        self._key = _key(incident_id)
        self._last_id = last_id
        self._buffer: collections.deque[WorkflowEvent] = collections.deque()

    async def get(self, timeout: float) -> WorkflowEvent | None:
        if self._buffer:
            return self._buffer.popleft()

        block_ms = max(1, int(timeout * 1000))
        result = await self._redis.xread({self._key: self._last_id}, count=100, block=block_ms)
        if not result:
            return None

        for _stream, entries in result:
            for entry_id, fields in entries:
                self._last_id = entry_id
                payload = fields.get("payload") or fields.get(b"payload")
                if payload is None:
                    continue
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                try:
                    self._buffer.append(WorkflowEvent(**json.loads(payload)))
                except Exception:
                    logger.exception("Malformed event payload on %s", self._key)

        return self._buffer.popleft() if self._buffer else None

    async def close(self) -> None:
        return None


class RedisEventBus(EventBus):
    def __init__(self, redis_url: str) -> None:
        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True)

    async def publish(self, event: WorkflowEvent) -> None:
        key = _key(event.incident_id)
        payload = json.dumps(event.model_dump(mode="json"))
        await self._redis.xadd(key, {"payload": payload}, maxlen=_STREAM_MAXLEN, approximate=True)
        await self._redis.expire(key, _STREAM_TTL_SECONDS)

    def subscribe(self, incident_id: str, replay: bool = True) -> Subscription:
        # "0" replays from the start of the stream; "$" delivers only new events.
        last_id = "0" if replay else "$"
        return _RedisSubscription(self._redis, incident_id, last_id)

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            logger.exception("Redis ping failed")
            return False

    async def close(self) -> None:
        await self._redis.aclose()
