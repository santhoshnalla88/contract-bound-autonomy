"""Authentication and user-management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core.identity import service
from core.identity.deps import CurrentUser, get_current_user, require_admin
from core.identity.security import Role, create_access_token

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="viewer")


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """Exchange email + password for a JWT access token."""
    db = request.app.state.db
    user = await service.authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(subject=user["email"], role=user["role"])
    return TokenResponse(access_token=token, role=user["role"], email=user["email"])


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return {"email": user.email, "role": user.role_name}


@router.get("/users")
async def list_users(request: Request, _: CurrentUser = Depends(require_admin)):
    """List all users (admin only)."""
    db = request.app.state.db
    return {"users": await db.list_users()}


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest, request: Request, _: CurrentUser = Depends(require_admin)
):
    """Create a user with a role (admin only)."""
    db = request.app.state.db
    try:
        created = await service.create_user(db, str(body.email), body.password, body.role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return created


@router.get("/roles")
async def list_roles(_: CurrentUser = Depends(get_current_user)):
    """Return the RBAC role ladder for UI display."""
    return {"roles": [r.label for r in Role]}
