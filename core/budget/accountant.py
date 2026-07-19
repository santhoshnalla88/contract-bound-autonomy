from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Dict, List

from .models import Budget, BudgetLedgerEntry, BudgetType

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """Raised when an operation would exceed an allowed budget."""
    pass

class ExecutionBudgetAccountant:
    """Manages limits and records consumption across a remediation run."""
    
    def __init__(self, limits: List[Budget]) -> None:
        self.limits: Dict[BudgetType, float] = {b.budget_type: b.limit for b in limits}
        self.ledger: List[BudgetLedgerEntry] = []
        self._consumption: Dict[BudgetType, float] = defaultdict(float)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def get_remaining_budget(self, budget_type: BudgetType) -> float:
        """Calculate the remaining budget for a specific type."""
        if budget_type not in self.limits:
            return float('inf') # No limit
        return self.limits[budget_type] - self._consumption[budget_type]

    def record_consumption(
        self,
        incident_id: str,
        budget_type: BudgetType,
        amount: float,
        agent_id: str = "system",
        details: dict[str, str] = None,
    ) -> BudgetLedgerEntry:
        """Record consumption and raise if limit is breached."""
        
        remaining = self.get_remaining_budget(budget_type)
        if remaining < amount:
            msg = (
                f"Budget exceeded for {budget_type.value}. "
                f"Requested: {amount}, Remaining: {remaining}"
            )
            self._logger.warning(msg)
            raise BudgetExceededError(msg)
            
        # Deduct
        self._consumption[budget_type] += amount
        
        entry = BudgetLedgerEntry(
            entry_id=str(uuid.uuid4()),
            incident_id=incident_id,
            budget_type=budget_type,
            amount=amount,
            agent_id=agent_id,
            details=details or {},
        )
        self.ledger.append(entry)
        
        self._logger.debug(
            f"Recorded consumption: {amount} {budget_type.value}. "
            f"Remaining: {self.get_remaining_budget(budget_type)}"
        )
        return entry
