"""Delegated MCP authentication stays within one inbound user request."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.core.context import bind_subject_access_token, clear, current
from app.core.exceptions import MCPError
from app.tools.mcp.client import StreamableHTTPMCPClient
from app.tools.mcp.oauth import (
    ACCESS_TOKEN_TYPE,
    TOKEN_EXCHANGE_GRANT_TYPE,
    DelegatedMCPTokenProvider,
)

TOKEN_URL = "https://vow.example.com/api/identity/oauth2/token/"
MCP_URL = "https://vow.example.com/mcp"


def _settings() -> Settings:
    return Settings(
        log_file="",
        use_mock_mcp=False,
        mcp_server_url=MCP_URL,
        mcp_oauth_token_url=TOKEN_URL,
        mcp_oauth_client_id="vow-agent-backend",
        mcp_oauth_client_secret="backend-secret",
        mcp_oauth_resource=MCP_URL,
        mcp_oauth_scopes=["read"],
    )


@pytest.mark.asyncio
async def test_exchange_is_cached_only_inside_the_current_user_request():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        form = parse_qs(request.content.decode())
        source = form["subject_token"][0]
        return httpx.Response(
            200,
            json={
                "access_token": f"mcp-for-{source}",
                "issued_token_type": ACCESS_TOKEN_TYPE,
                "token_type": "Bearer",
                "expires_in": 60,
                "scope": "read",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    provider = DelegatedMCPTokenProvider(_settings(), http_client=http_client)
    try:
        bind_subject_access_token("alice-agent-token")
        assert await provider.get_token() == "mcp-for-alice-agent-token"
        assert await provider.get_token() == "mcp-for-alice-agent-token"

        bind_subject_access_token("bob-agent-token")
        assert await provider.get_token() == "mcp-for-bob-agent-token"
    finally:
        await http_client.aclose()
        clear()

    assert len(requests) == 2
    expected_basic = base64.b64encode(b"vow-agent-backend:backend-secret").decode()
    for request in requests:
        form = parse_qs(request.content.decode())
        assert request.headers["Authorization"] == f"Basic {expected_basic}"
        assert form["grant_type"] == [TOKEN_EXCHANGE_GRANT_TYPE]
        assert form["subject_token_type"] == [ACCESS_TOKEN_TYPE]
        assert form["requested_token_type"] == [ACCESS_TOKEN_TYPE]
        assert form["resource"] == [MCP_URL]
        assert form["scope"] == ["read"]


@pytest.mark.asyncio
async def test_exchange_fails_closed_without_an_inbound_user_token():
    clear()
    provider = DelegatedMCPTokenProvider(_settings())

    with pytest.raises(MCPError, match="request-scoped user token"):
        await provider.get_token()


@pytest.mark.asyncio
async def test_live_mcp_call_supplies_delegated_token_and_advertiser_header():
    captured: dict[str, object] = {}

    class StubTokenProvider:
        async def get_token(self) -> str:
            return "delegated-user-token"

    def respond(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": captured["payload"]["id"],
                "result": {
                    "structuredContent": {"result": {"results": []}},
                    "isError": False,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    mcp = StreamableHTTPMCPClient(
        "advertiser-123",
        settings=_settings(),
        token_provider=StubTokenProvider(),  # type: ignore[arg-type]
        http_client=http_client,
    )
    try:
        result = await mcp._call_tool_raw(
            "search_audiences",
            {"search": "sports", "advertiser_id": "advertiser-123"},
        )
    finally:
        await http_client.aclose()

    assert result == {"results": []}
    headers = captured["headers"]
    assert isinstance(headers, httpx.Headers)
    assert headers["Authorization"] == "Bearer delegated-user-token"
    assert headers["Vowmade-Advertiser-Id"] == "advertiser-123"
    assert headers["MCP-Protocol-Version"] == "2026-07-28"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["method"] == "tools/call"
    assert payload["params"] == {
        "name": "search_audiences",
        "arguments": {"search": "sports"},
    }


def test_secret_tokens_are_excluded_from_logging_context():
    bind_subject_access_token("do-not-log-me")

    assert "do-not-log-me" not in repr(current())
