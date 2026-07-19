import pytest
from core.orchestration.builder import build_graph
from core.enums import Severity
from examples.incident_commander.domain.models import Incident

@pytest.mark.asyncio
async def test_graph_initialization():
    graph = build_graph()
    
    incident_data = {
        "incident_id": "INC-TEST",
        "service": "test-service",
        "environment": "production",
        "severity": Severity.LOW,
        "metrics": {"error_rate": 1.0, "healthy_pods": 5, "total_pods": 5}
    }
    
    initial_state = {"incident": incident_data}
    config = {"configurable": {"thread_id": "INC-TEST"}}
    
    # We can't easily run the full graph without mocks for LLM and ChromaDB,
    # but we can verify it compiles and we can get state
    state = await graph.aget_state(config)
    assert state is not None
