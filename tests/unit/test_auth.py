"""Auth primitives + RBAC ordering."""

import pytest

from core.identity.security import (
    Role,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert verify_password("s3cret-pw", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token("user@example.com", "approver")
    payload = decode_access_token(token)
    assert payload["sub"] == "user@example.com"
    assert payload["role"] == "approver"


def test_role_ordering():
    assert Role.ADMIN > Role.APPROVER > Role.OPERATOR > Role.VIEWER
    assert Role.from_name("admin") == Role.ADMIN
    assert Role.from_name("nonsense") == Role.VIEWER
    assert Role.APPROVER.label == "approver"
