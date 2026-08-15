"""Health endpoint tests.

These are deliberately the first tests in the repo: they prove the whole
chain works - app builds, routes register, settings load, responses validate.
"""

from fastapi.testclient import TestClient


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "vow-agent"


def test_readiness_returns_ready(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_health_response_has_version(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.json()["version"] == "0.1.0"


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
