from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime

class ContractResolver(Protocol):
    def resolve_effective_contract(self, case_id: str, context: Dict[str, Any]) -> Any:
        """Resolves the effective contract given current context (Phase B1)."""
        ...

class PolicyEvaluator(Protocol):
    def evaluate_action(self, action: Any, context: Dict[str, Any]) -> Any:
        """Evaluates an action against loaded policy packs (Phase B3)."""
        ...

class RiskScorer(Protocol):
    def score_plan(self, plan: Any) -> Any:
        """Calculates risk score 0-100 for a proposed plan (Phase B4)."""
        ...

class BudgetAccountant(Protocol):
    def check_budget(self, agent_id: str, planned_cost: float) -> bool:
        """Checks if there is enough budget to execute (Phase B2)."""
        ...
        
    def record_cost(self, agent_id: str, cost: float) -> None:
        """Records execution cost."""
        ...

class ExecutionDriver(Protocol):
    def execute(self, action: str, parameters: Dict[str, Any]) -> Any:
        """Executes a tool call and returns the result."""
        ...

class MemoryStore(Protocol):
    def store(self, key: str, value: Any, scope: str) -> None:
        """Stores a value in long or short term memory."""
        ...
        
    def recall(self, key: str, scope: str) -> Optional[Any]:
        """Recalls a value from memory."""
        ...

class AgentRole(Protocol):
    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes the agent role to process the current state."""
        ...
