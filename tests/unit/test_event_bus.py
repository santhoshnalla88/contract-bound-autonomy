"""In-memory event bus: replay + live delivery."""

import pytest

from core.events.bus import InMemoryEventBus, WorkflowEvent


@pytest.mark.asyncio
async def test_replay_then_live():
    bus = InMemoryEventBus()
    await bus.publish(WorkflowEvent(incident_id="INC-1", type="a", message="first"))

    sub = bus.subscribe("INC-1", replay=True)
    # Replayed historical event arrives first.
    e1 = await sub.get(timeout=1.0)
    assert e1 and e1.type == "a"

    await bus.publish(WorkflowEvent(incident_id="INC-1", type="b", message="second", terminal=True))
    e2 = await sub.get(timeout=1.0)
    assert e2 and e2.type == "b" and e2.terminal

    # Nothing left → timeout returns None.
    assert await sub.get(timeout=0.1) is None
    await sub.close()


@pytest.mark.asyncio
async def test_isolation_between_incidents():
    bus = InMemoryEventBus()
    await bus.publish(WorkflowEvent(incident_id="INC-1", type="x", message="m"))
    sub = bus.subscribe("INC-2", replay=True)
    assert await sub.get(timeout=0.1) is None
    await sub.close()
