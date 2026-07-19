import pytest
from core.budget.models import Budget, BudgetType
from core.budget.accountant import ExecutionBudgetAccountant, BudgetExceededError

def test_budget_accountant_records_consumption():
    limits = [Budget(budget_type=BudgetType.TOOL_CALL, limit=5.0)]
    accountant = ExecutionBudgetAccountant(limits)
    
    assert accountant.get_remaining_budget(BudgetType.TOOL_CALL) == 5.0
    
    entry = accountant.record_consumption(
        incident_id="INC-1",
        budget_type=BudgetType.TOOL_CALL,
        amount=2.0
    )
    
    assert accountant.get_remaining_budget(BudgetType.TOOL_CALL) == 3.0
    assert len(accountant.ledger) == 1
    assert accountant.ledger[0].amount == 2.0
    assert accountant.ledger[0].incident_id == "INC-1"

def test_budget_accountant_raises_on_breach():
    limits = [Budget(budget_type=BudgetType.COST, limit=10.0)]
    accountant = ExecutionBudgetAccountant(limits)
    
    with pytest.raises(BudgetExceededError):
        accountant.record_consumption(
            incident_id="INC-2",
            budget_type=BudgetType.COST,
            amount=15.0
        )
        
def test_budget_accountant_no_limit():
    accountant = ExecutionBudgetAccountant([])
    
    # Infinite budget when not specified
    assert accountant.get_remaining_budget(BudgetType.TIME) == float('inf')
    
    # Should not raise
    accountant.record_consumption(
        incident_id="INC-3",
        budget_type=BudgetType.TIME,
        amount=1000.0
    )
    assert accountant.get_remaining_budget(BudgetType.TIME) == float('inf')
