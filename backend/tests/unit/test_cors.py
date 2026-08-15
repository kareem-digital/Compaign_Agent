"""The frontend has to be able to reach the backend from either dev port.

**Found on the UI.** The chat panel said "The agent could not be reached. Please try again."
and the Network tab showed two `chat` requests as `(failed)`, 0.0 kB, no status code at all.

The backend was fine. It answered both with **200 OK**. What it did not send back was
`access-control-allow-origin`, because the default allowed only `localhost:3000` and the
frontend was running on `localhost:3001` - `npm run dev:remote`, the Module Federation remote,
which `frontend/package.json` and the frontend README both describe as a normal way to run it.

That failure mode is the dangerous kind: **it is invisible from the server side.** The log
records a successful turn, `turn.end` and all, because from the backend's point of view
nothing went wrong. Only the browser knows it threw the response away. So the default has to
be right rather than left to an `.env` file nobody knows they need.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app

DEV_PORTS = ("http://localhost:3000", "http://localhost:3001")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("origin", DEV_PORTS)
def test_both_frontend_dev_ports_are_allowed(origin):
    """3000 is `npm run dev`, 3001 is `npm run dev:remote`. Both are documented ways to run
    the frontend, so both have to work without extra configuration."""
    assert origin in Settings().cors_origins


@pytest.mark.parametrize("origin", DEV_PORTS)
def test_the_response_carries_the_header_back(origin, client):
    """The setting existing is not the same as the header arriving - the middleware has to be
    wired to it, and that is the half the browser actually reads."""
    response = client.get("/api/v1/health/live", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", DEV_PORTS)
def test_the_preflight_is_answered(origin, client):
    """The chat call sends `Content-Type: application/json` and a custom advertiser header,
    which makes it non-simple: the browser sends OPTIONS first and never sends the POST at all
    if that is refused."""
    response = client.options(
        "/api/v1/sessions/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,vowmade-advertiser-id",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers.get("access-control-allow-origin") == origin


def test_an_origin_nobody_configured_is_still_refused():
    """The fix widens the default by one known port. It is not "allow everything" - an open
    CORS policy on an endpoint that spends money is a different bug."""
    client = TestClient(app)

    response = client.get(
        "/api/v1/health/live", headers={"Origin": "https://not-our-frontend.example"}
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_env_var_still_wins(monkeypatch):
    """Deployments set their own origins - the default is only for a local clone."""
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.vowmade.dev"]')

    assert Settings().cors_origins == ["https://app.vowmade.dev"]
