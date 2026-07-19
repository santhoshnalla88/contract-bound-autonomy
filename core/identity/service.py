"""User service: authentication and admin bootstrap."""

from __future__ import annotations

import logging
import uuid

from core.identity.security import Role, hash_password, verify_password
from core.config import Settings
from core.persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


async def authenticate(db: DatabaseManager, email: str, password: str) -> dict | None:
    """Return the user record if credentials are valid and the account active."""
    user = await db.get_user_by_email(email)
    if not user or not user.get("is_active", True):
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


async def create_user(
    db: DatabaseManager, email: str, password: str, role: str
) -> dict:
    existing = await db.get_user_by_email(email)
    if existing:
        raise ValueError(f"User '{email}' already exists")
    # Normalize/validate role.
    role_name = Role.from_name(role).label
    user_id = uuid.uuid4().hex
    await db.create_user(user_id, email, hash_password(password), role_name)
    logger.info("Created user %s (role=%s)", email, role_name)
    return {"id": user_id, "email": email, "role": role_name}


async def bootstrap_admin(db: DatabaseManager, settings: Settings) -> None:
    """Create the bootstrap admin on first run (when no users exist)."""
    if await db.count_users() > 0:
        return
    if not settings.bootstrap_admin_password:
        logger.warning(
            "No users exist and BOOTSTRAP_ADMIN_PASSWORD is unset — "
            "no admin created. Set it to enable login."
        )
        return
    await create_user(
        db,
        email=settings.bootstrap_admin_email,
        password=settings.bootstrap_admin_password,
        role=Role.ADMIN.label,
    )
    logger.info("Bootstrap admin '%s' created.", settings.bootstrap_admin_email)
