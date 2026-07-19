"""Shared test fixtures.

Configures an isolated environment (temp SQLite DB, in-memory event bus, mock
execution driver, JWT secret, bootstrap admin) BEFORE the app is imported, so
the whole suite runs without Postgres/Redis/Kubernetes.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# --- Configure environment before importing the app / settings ---
_TMP = Path(tempfile.mkdtemp(prefix="gaap_test_"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}",
        "CHECKPOINTER_URL": "",
        "REDIS_URL": "",
        "EXECUTION_BACKEND": "mock",
        "ANTHROPIC_API_KEY": "sk-ant-dummy-for-tests",
        "GOOGLE_API_KEY": "dummy-for-tests",
        "GRAPH_ENABLED": "false",
        "INGEST_ON_STARTUP": "false",
        "JWT_SECRET": "test-secret-0123456789-abcdefghijklmnop",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@test.io",
        "BOOTSTRAP_ADMIN_PASSWORD": "adminpass123",
        "LANGSMITH_TRACING": "false",
        "ALLOWED_ORIGINS": "*",
    }
)

from core.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def app_client():
    """A TestClient with lifespan run (DB init + bootstrap admin)."""
    from fastapi.testclient import TestClient

    from apps.api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def admin_token(app_client):
    res = app_client.post(
        "/api/auth/login", json={"email": "admin@test.io", "password": "adminpass123"}
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
