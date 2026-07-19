"""Operational contract inspection routes.

Read-only viewer over the deterministically-loaded contracts in the
``knowledge/contracts`` directory. Contracts are the machine-readable
autonomy boundaries; the control-plane UI surfaces them so operators can see
exactly what the agent is (and is not) permitted to do per service.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from core.identity.deps import CurrentUser, require_viewer
from core.config import get_settings
from core.contracts import OperationalContract

router = APIRouter(prefix="/api/contracts", tags=["Contracts"])


@router.get("")
async def list_contracts(_: CurrentUser = Depends(require_viewer)):
    """List all operational contracts discovered in the knowledge base."""
    settings = get_settings()
    contracts_dir = settings.knowledge_dir / "contracts"

    contracts = []
    if contracts_dir.exists():
        for path in sorted(contracts_dir.glob("*-contract.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                contract = OperationalContract(**data)
                contracts.append(
                    {
                        "contract_id": contract.contract_id,
                        "service": contract.service,
                        "environment": contract.environment,
                        "version": contract.version,
                        "allowed_actions": contract.allowed_actions,
                        "forbidden_actions": contract.forbidden_actions,
                    }
                )
            except Exception:
                continue

    return {"contracts": contracts, "count": len(contracts)}


@router.get("/{service}")
async def get_contract(
    service: str, environment: str = "production", _: CurrentUser = Depends(require_viewer)
):
    """Get the full operational contract for a service/environment."""
    settings = get_settings()
    contracts_dir = settings.knowledge_dir / "contracts"
    contract_file = contracts_dir / f"{service}-contract.json"

    if not contract_file.exists():
        raise HTTPException(
            status_code=404, detail=f"No contract found for service '{service}'."
        )

    try:
        data = json.loads(contract_file.read_text(encoding="utf-8"))
        contract = OperationalContract(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid contract: {exc}")

    return contract.model_dump(mode="json")
