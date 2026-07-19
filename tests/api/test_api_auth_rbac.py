"""End-to-end API auth + RBAC via TestClient."""

import pytest


def test_health_is_public(app_client):
    assert app_client.get("/health").json() == {"status": "ok"}


def test_protected_requires_auth(app_client):
    assert app_client.get("/api/incidents").status_code == 401
    assert app_client.get("/api/contracts").status_code == 401


def test_login_and_me(app_client, admin_headers):
    me = app_client.get("/api/auth/me", headers=admin_headers).json()
    assert me["email"] == "admin@test.io"
    assert me["role"] == "admin"


def test_bad_credentials_rejected(app_client):
    r = app_client.post("/api/auth/login", json={"email": "admin@test.io", "password": "nope"})
    assert r.status_code == 401


def test_admin_can_read(app_client, admin_headers):
    assert app_client.get("/api/incidents", headers=admin_headers).status_code == 200
    assert app_client.get("/api/contracts", headers=admin_headers).json()["count"] >= 1


def _viewer_headers(app_client, admin_headers):
    app_client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"email": "viewer@example.com", "password": "viewerpass1", "role": "viewer"},
    )
    tok = app_client.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "viewerpass1"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_rbac_viewer_cannot_write(app_client, admin_headers):
    vh = _viewer_headers(app_client, admin_headers)
    # Viewer can read...
    assert app_client.get("/api/incidents", headers=vh).status_code == 200
    # ...but not submit an incident (operator+) or approve (approver+).
    incident = {
        "incident_id": "INC-RBAC",
        "service": "svc",
        "environment": "production",
        "severity": "LOW",
        "metrics": {"error_rate": 1.0, "healthy_pods": 5, "total_pods": 5},
    }
    assert app_client.post("/api/incidents", headers=vh, json=incident).status_code == 403
    assert (
        app_client.post("/api/approvals/INC-RBAC", headers=vh, json={"decision": "APPROVED"}).status_code
        == 403
    )


def test_only_admin_manages_users(app_client, admin_headers):
    vh = _viewer_headers(app_client, admin_headers)
    r = app_client.post(
        "/api/auth/users",
        headers=vh,
        json={"email": "x@example.com", "password": "password1", "role": "viewer"},
    )
    assert r.status_code == 403
