"""LangGraph assembly for the remediation orchestration workflow.

This module wires the node functions and conditional routers into a single
compiled ``StateGraph`` and exposes :func:`build_graph`.

Two properties are essential for correctness and are handled here:

1. **Shared checkpointer.** Human-in-the-loop (``interrupt`` /
   ``Command(resume=...)``) and every state-inspection endpoint
   (``aget_state``) only work if all callers share the *same* compiled
   graph and checkpointer. ``build_graph`` therefore returns a
   process-level singleton backed by a single ``MemorySaver``.

2. **Complete topology.** Every node is reachable and every branch
   terminates at ``finalize`` → ``END`` — there are no dangling edges.

Workflow topology::

    START → ingest → identify → retrieve_knowledge → resolve_contract
      resolve_contract ─(proceed)→ plan_remediation
                       └(escalate)→ handle_escalation
      plan_remediation → evaluate_guardrails
      evaluate_guardrails ─(approved)→ evaluate_risk
                          └(rejected)→ increment_retry
      increment_retry ─(retry)→ plan_remediation
                      └(escalate)→ handle_escalation
      evaluate_risk ─(execute)→ execute_actions
                    └(human_approval)→ request_human_approval  [interrupt]
      request_human_approval ─(execute)→ execute_actions
                             └(denied)→ finalize
      execute_actions → validate_postconditions
      validate_postconditions ─(success)→ finalize
                              ├(retry)→ increment_retry
                              └(escalate)→ handle_escalation
      handle_escalation → finalize → END
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.orchestration import nodes, routing
from core.orchestration.state import OrchestratorState

logger = logging.getLogger(__name__)

# Process-level singleton compiled graph. Configured once at startup with the
# real (Postgres) checkpointer; falls back to an in-memory saver for local/test.
_graph: CompiledStateGraph | None = None


def _assemble(checkpointer: Any) -> CompiledStateGraph:
    """Assemble and compile the orchestration StateGraph with a checkpointer."""
    builder = StateGraph(OrchestratorState)

    # --- Register nodes ---
    builder.add_node("ingest_incident", nodes.ingest_incident)
    builder.add_node("identify_service", nodes.identify_service)
    builder.add_node("retrieve_knowledge", nodes.retrieve_knowledge)
    builder.add_node("resolve_contract", nodes.resolve_contract)
    builder.add_node("plan_remediation", nodes.plan_remediation)
    builder.add_node("evaluate_guardrails", nodes.evaluate_guardrails)
    builder.add_node("evaluate_semantics", nodes.evaluate_semantics)
    builder.add_node("increment_retry", nodes.increment_retry)
    builder.add_node("evaluate_risk", nodes.evaluate_risk)
    builder.add_node("request_human_approval", nodes.request_human_approval)
    builder.add_node("execute_actions", nodes.execute_actions)
    builder.add_node("validate_postconditions", nodes.validate_postconditions)
    builder.add_node("handle_escalation", nodes.handle_escalation)
    builder.add_node("finalize", nodes.finalize)

    # --- Linear intake path ---
    builder.add_edge(START, "ingest_incident")
    builder.add_edge("ingest_incident", "identify_service")
    builder.add_edge("identify_service", "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "resolve_contract")

    # --- Contract resolution gate ---
    builder.add_conditional_edges(
        "resolve_contract",
        routing.route_after_contract,
        {"proceed": "plan_remediation", "escalate": "handle_escalation"},
    )

    # --- Plan → guardrails ---
    builder.add_edge("plan_remediation", "evaluate_guardrails")
    builder.add_conditional_edges(
        "evaluate_guardrails",
        routing.route_after_guardrail,
        {"approved": "evaluate_semantics", "rejected": "increment_retry"},
    )
    
    # --- Semantics → risk ---
    builder.add_conditional_edges(
        "evaluate_semantics",
        routing.route_after_guardrail,
        {"approved": "evaluate_risk", "rejected": "increment_retry"},
    )

    # --- Retry / escalation loop ---
    builder.add_conditional_edges(
        "increment_retry",
        routing.route_after_rejection,
        {"retry": "plan_remediation", "escalate": "handle_escalation"},
    )

    # --- Risk → auto-execute or human approval ---
    builder.add_conditional_edges(
        "evaluate_risk",
        routing.route_after_risk,
        {"execute": "execute_actions", "human_approval": "request_human_approval"},
    )
    builder.add_conditional_edges(
        "request_human_approval",
        routing.route_after_human,
        {"execute": "execute_actions", "denied": "finalize"},
    )

    # --- Execution → postconditions ---
    builder.add_edge("execute_actions", "validate_postconditions")
    builder.add_conditional_edges(
        "validate_postconditions",
        routing.route_after_postcondition,
        {
            "success": "finalize",
            "retry": "increment_retry",
            "escalate": "handle_escalation",
        },
    )

    # --- Terminal edges ---
    builder.add_edge("handle_escalation", "finalize")
    builder.add_edge("finalize", END)

    compiled = builder.compile(checkpointer=checkpointer)
    logger.info("Orchestration graph compiled with %d nodes", 14)
    return compiled


def build_graph(checkpointer: Any | None = None) -> CompiledStateGraph:
    """Return the shared, compiled orchestration graph (singleton).

    Call once at startup with the real checkpointer (``build_graph(checkpointer=…)``)
    to (re)configure the process graph; subsequent bare ``build_graph()`` calls
    from routes/tasks return that same instance. All callers must share one
    checkpointer — a prerequisite for HITL resumption and state inspection.

    With no checkpointer configured (bare unit tests / local convenience), an
    in-memory saver is used.
    """
    global _graph
    if checkpointer is not None:
        _graph = _assemble(checkpointer)
        return _graph
    if _graph is None:
        _graph = _assemble(MemorySaver())
    return _graph
