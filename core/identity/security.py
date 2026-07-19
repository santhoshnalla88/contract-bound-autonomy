"""Security primitives: password hashing (bcrypt) and JWT tokens.

Uses the ``bcrypt`` library directly (no passlib shim) to avoid version-probing
incompatibilities, and PyJWT for signed access tokens. The signing secret comes
from settings (mandatory in production, ephemeral in dev).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import IntEnum

import bcrypt
import jwt

from core.config import get_settings

# bcrypt hard-limits passwords to 72 bytes.
_BCRYPT_MAX_BYTES = 72


class Role(IntEnum):
    """Ordered roles — higher value grants a superset of lower-value access."""

    VIEWER = 0
    OPERATOR = 1
    APPROVER = 2
    ADMIN = 3

    @classmethod
    def from_name(cls, name: str) -> "Role":
        try:
            return cls[name.strip().upper()]
        except KeyError:
            return cls.VIEWER

    @property
    def label(self) -> str:
        return self.name.lower()


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
