"""Typed failures map to typed responses.

The mapping is ordered most-specific-first, which is the part worth pinning: a
`RegistryValidationError` must not be answered as a generic sync failure, and
neither must become an untyped 500.
"""

import json

import pytest

from app.api.errors import _describe, handle_vow_agent_error
from app.core.context import bind, clear
from app.core.exceptions import (
    AdvertiserContextMissingError,
    ConfigurationError,
    GroundingError,
    MCPError,
    MCPToolNotFoundError,
    MCPTransientError,
    RegistrySyncError,
    RegistryValidationError,
    VowAgentError,
    VowAuthError,
)


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (AdvertiserContextMissingError("no advertiser"), 400),
        (RegistryValidationError("bad data", ["v1"]), 503),
        (RegistrySyncError("cannot load"), 503),
        (MCPError("down"), 502),
        (MCPTransientError("timeout"), 502),
        (MCPToolNotFoundError("gone"), 502),
        (VowAuthError("denied"), 502),
        (GroundingError("ungrounded id"), 500),
        (ConfigurationError("missing setting"), 500),
        (VowAgentError("something"), 500),
    ],
)
def test_status_mapping(exc, status):
    assert _describe(exc)[0] == status


def test_subclass_beats_parent():
    # RegistryValidationError is a RegistrySyncError; the specific message wins.
    specific = _describe(RegistryValidationError("x", []))[1]
    general = _describe(RegistrySyncError("x"))[1]
    assert specific != general
    assert "validation" in specific


def test_unknown_exception_falls_back_to_500():
    assert _describe(ValueError("not ours")) == (500, "Agent error.")


def test_messages_do_not_name_internals():
    # These strings reach a trader. They may say what happened to the request;
    # they may not name a component, a tool, or a stack frame.
    forbidden = ("registry", "mcp", "graph", "node", "traceback", "sql")
    for exc in (
        RegistryValidationError("x", []),
        RegistrySyncError("x"),
        MCPError("x"),
        GroundingError("x"),
    ):
        message = _describe(exc)[1].lower()
        assert not any(word in message for word in forbidden), message


class _Url:
    path = "/api/v1/sessions/chat"


class _Request:
    """Only what the handler reads - `request.url.path`."""

    url = _Url()


class TestHandlerResponse:
    @pytest.fixture(autouse=True)
    def _ctx(self):
        clear()
        yield
        clear()

    async def test_body_carries_request_id_and_error_type(self, caplog):
        bind(request_id="req-7")
        response = await handle_vow_agent_error(_Request(), MCPError("down", tool="vow.list_deals"))
        body = json.loads(response.body)

        assert response.status_code == 502
        assert body["error"] == "MCPError"
        assert body["request_id"] == "req-7"
        assert body["detail"] == "VOW is unavailable."

    async def test_request_id_omitted_when_unbound(self):
        response = await handle_vow_agent_error(_Request(), MCPError("down"))
        assert "request_id" not in json.loads(response.body)

    async def test_violations_are_logged_not_returned(self, caplog):
        bind(request_id="req-8")
        exc = RegistryValidationError("bad", [f"violation {i}" for i in range(30)])
        with caplog.at_level("ERROR"):
            response = await handle_vow_agent_error(_Request(), exc)

        body = json.loads(response.body)
        # The trader gets a sentence; the reviewer gets the list.
        assert "violation" not in body["detail"]
        record = next(r for r in caplog.records if r.getMessage() == "request.failed")
        assert record.extra_fields["violation_count"] == 30
        assert len(record.extra_fields["violations"]) == 20, "capped so one bad sync cannot flood"

    async def test_tool_is_recorded_when_present(self, caplog):
        with caplog.at_level("ERROR"):
            await handle_vow_agent_error(_Request(), MCPError("x", tool="vow.reach_forecast"))
        record = next(r for r in caplog.records if r.getMessage() == "request.failed")
        assert record.extra_fields["tool"] == "vow.reach_forecast"
