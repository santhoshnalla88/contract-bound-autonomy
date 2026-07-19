"""Tests for the payments incident commander running on the core orchestrator."""

import json
import pytest
from core.enums import FinalStatus
from core.models import BaseIncident
from core.orchestration.builder import build_graph
from examples.payments_commander.domain.anomaly import AnomalyGenerator
from examples.payments_commander.drivers.payments import PaymentsDriver
from core.execution.client import _incident_clients, MCPClient
from langchain_core.messages import SystemMessage, HumanMessage
from core.trust.manager import TrustManager
from core.agents.investigation import InvestigationAgent
from core.agents.planner import PlannerAgent
import os

os.environ["OPENAI_API_KEY"] = "dummy"

@pytest.fixture
def payments_incident():
    return AnomalyGenerator.generate_high_decline_rate()

@pytest.fixture
def payments_contract():
    with open("examples/payments_commander/contracts/payments_default.json") as f:
        return json.load(f)

@pytest.mark.asyncio
async def test_payments_incident_resolution(payments_incident, payments_contract):
    """Test that a payments incident can be resolved using the generic core orchestrator."""
    
    # 1. Setup MCP Client for this incident with PaymentsDriver
    driver = PaymentsDriver()
    client = MCPClient(driver=driver)
    _incident_clients[payments_incident.incident_id] = client
    
    # 2. Build the orchestrator graph
    # We use a memory saver for checkpointer
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)
    
    # 3. Initial state
    config = {"configurable": {"thread_id": "test_payments_1"}}
    initial_state = {
        "incident": payments_incident.model_dump(mode="json"),
        "audit_trail": [],
    }
    
    # We will mock ContractLoader to return our payments_contract
    import unittest.mock as mock
    with mock.patch("core.contracts.contracts.ContractLoader.load") as mock_load:
        from core.contracts.contracts import OperationalContract
        mock_load.return_value = OperationalContract(**payments_contract)
        
        # We also need to mock the RAG retrieval in InvestigationAgent so it reads our payments runbook
        with mock.patch("core.agents.investigation.InvestigationAgent.investigate") as mock_investigate:
            mock_investigate.return_value = [
                {
                    "content": "Runbook says: Reroute gateway traffic to backup_gateway. Check PCI compliance.",
                    "metadata": {"source": "payments_runbook"},
                    "relevance_score": 0.99
                }
            ]
            
            # Mock the planner to avoid hitting the actual LLM API during testing
            with mock.patch("core.agents.planner.PlannerAgent.plan") as mock_plan:
                from core.models import RemediationPlan, PlannedAction
                mock_plan.return_value = RemediationPlan(
                    summary="Reroute gateway traffic based on runbook",
                    actions=[
                        PlannedAction(
                            action="reroute_gateway",
                            target="gateway-service",
                            parameters={"gateway": "backup_gateway"},
                            rationale="High decline rate, switching to backup gateway."
                        )
                    ],
                    estimated_impact="Medium",
                    rollback_procedure="Revert to primary gateway"
                )
                
                with mock.patch("core.agents.policy.PolicyAgent.validate", new_callable=mock.AsyncMock) as mock_validate:
                    mock_validate.return_value = (True, "Plan meets semantic requirements.")
                    
                    with mock.patch("core.agents.summary.SummaryAgent.summarize", new_callable=mock.AsyncMock) as mock_summary:
                        mock_summary.return_value = "Incident resolved by rerouting gateway."
                        
                        # Let's run the graph up to the interrupt
                        state = None
                        async for step in graph.astream(initial_state, config=config):
                            state = step
                            # Print progress
                            for node_name, node_state in step.items():
                                print(f"--- Completed: {node_name} ---")

            # Get the current state
            current_state = graph.get_state(config)
            
            # The risk node should auto-approve (if score < 30) or require approval.
            # Rerouting gateway is not approval required in the contract.
            # But high decline rate is Severity.HIGH, which adds 25 points.
            # Rerouting gateway adds 0 complexity points.
            # Trust score defaults to 0.5 (multiplier 1.0)
            # So risk score is 25. LOW risk. Auto-approve!
            
            # Since it's auto-approved, it should run to execution and postcondition.
            # Postcondition checks decline_rate <= 10.0.
            # Our mock PaymentsDriver currently returns decline_rate=5.0 in get_metrics.
            # So postcondition passes. Final status should be SUCCESS.
            
            final_status = current_state.values.get("final_status")
            assert final_status == FinalStatus.SUCCESS
            
            # Check execution history
            execution_history = current_state.values.get("execution_history", [])
            assert len(execution_history) > 0
            assert execution_history[0]["action"] == "reroute_gateway"
            assert execution_history[0]["success"] is True
