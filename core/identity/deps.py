"""FastAPI auth dependencies: current user resolution and RBAC guards.

Tokens are accepted from the ``Authorization: Bearer`` header, a ``token`` query
parameter (required for the SSE endpoint — ``EventSource`` cannot set headers),
or an ``access_token`` cookie. ``require_role`` enforces the ordered RBAC model.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from core.identity.security import Role, decode_access_token

logger = logging.getLogger(__name__)


class CurrentUser(BaseModel):
    email: str
    role: Role

    @property
    def role_name(self) -> str:
        return self.role.label


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = request.query_params.get("token")
    if token:
        return token
    return request.cookies.get("access_token")


async def get_current_user(request: Request) -> CurrentUser:
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return CurrentUser(email=email, role=Role.from_name(payload.get("role", "viewer")))


def require_role(minimum: Role):
    """Dependency factory enforcing a minimum role."""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role < minimum:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{minimum.label}' or higher (you are '{user.role_name}')",
            )
        return user

    return _guard


# Convenience guards
require_viewer = require_role(Role.VIEWER)
require_operator = require_role(Role.OPERATOR)
require_approver = require_role(Role.APPROVER)
require_admin = require_role(Role.ADMIN)
