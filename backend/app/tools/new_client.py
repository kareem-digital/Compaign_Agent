"""How the agent reaches VOW: an MCP client with the policy baked in.

VOW exposes its platform APIs as an MCP server, so the agent calls *tools*
rather than REST endpoints. This replaces the httpx wrapper framework, but
keeps the three policies that framework got right:

  * **Fail closed on advertiser context.** No advertiser, no call. We never
    default to one - a wrong tenant is worse than an error.
  * **Retry only what is retryable.** Transient failures retry with backoff;
    a missing tool or a bad argument does not.
  * **Typed exceptions.** The graph branches on exception type rather than
    parsing error strings.

The policy lives in `MCPClient.call_tool`. Transports implement only the two
`_raw` methods, so a new transport cannot accidentally skip a policy.

The VOW transport carries advertiser context in `Vowmade-Advertiser-Id`. The
argument is still added before governance checks so existing policy rules and
the in-process mock see the complete scoped action; the HTTP transport removes
that internal-only argument before sending the MCP tool payload.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from app.config import Settings, get_settings
from app.core.exceptions import (
    AdvertiserContextMissingError,
    MCPError,
    MCPToolNotFoundError,
    MCPTransientError,
)
from app.core.logging import kv
from app.governance.agt import get_guard
from app.tools.mcp.oauth import DelegatedMCPTokenProvider

logger = logging.getLogger(__name__)

ADVERTISER_ARG = "advertiser_id"
ResultT = TypeVar("ResultT")


def _size_of(result) -> int | None:
    """Row count where there is one - the cheapest signal that a call worked."""
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        for key in ("results", "suggestions", "channels"):
            if isinstance(result.get(key), list):
                return len(result[key])
    return None


class MCPClient(ABC):
    """Transport-agnostic MCP client. Subclass and implement the `_raw` methods."""

    def __init__(
        self,
        advertiser_id: str,
        settings: Settings | None = None,
    ):
        self.advertiser_id = advertiser_id
        self.settings = settings or get_settings()

    # --- what transports implement ---

    @abstractmethod
    async def _list_tools_raw(self) -> list[dict]:
        """Return the server's tool descriptors."""

    @abstractmethod
    async def _call_tool_raw(self, name: str, arguments: dict) -> dict:
        """Invoke one tool. Raise MCPTransientError for retryable failures."""

    # --- the policy every call goes through ---

    async def list_tools(self) -> list[dict]:
        """Discover what the server offers.

        Worth calling at startup and logging: it is the cheapest way to catch
        the server's surface drifting from what our nodes expect.
        """
        return await self._retrying("list_tools", self._list_tools_raw)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Invoke an MCP tool, scoped to this session's advertiser."""
        if not self.advertiser_id:
            raise AdvertiserContextMissingError(
                f"Refusing to call {name!r} without an advertiser context - fail closed."
            )

        args = dict(arguments or {})
        args.setdefault(ADVERTISER_ARG, self.advertiser_id)

        # Governance. Deterministic policy check before anything leaves the
        # process. Raises PolicyDeniedError if the policy refuses.
        #
        # Placed AFTER scoping so a rule can read the advertiser, and BEFORE
        # _retrying so a refusal happens once - retrying a denial is pointless,
        # the answer cannot change.
        #
        # Field NAMES are logged, not values: the usual failure is "the policy
        # could not see total_budget", and this shows at a glance whether the
        # key was even present. Values are client-commercial and stay out.
        logger.debug(
            "governance.check",
            extra=kv(tool=name, fields=sorted(args), advertiser=self.advertiser_id),
        )
        get_guard().check(name, args, agent_id=self.advertiser_id)

        return await self._retrying(name, lambda: self._call_tool_raw(name, args))

    # --- shared retry / timing / logging ---

    async def _retrying(
        self,
        label: str,
        operation: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        attempts = max(1, self.settings.mcp_max_retries)
        last: Exception | None = None

        for attempt in range(1, attempts + 1):
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    operation(), timeout=self.settings.mcp_timeout_seconds
                )
                logger.info(
                    "mcp.call",
                    extra=kv(
                        tool=label,
                        duration_ms=round((time.monotonic() - start) * 1000),
                        attempt=attempt,
                        result_count=_size_of(result),
                    ),
                )
                # Full payloads only when debugging - they are large and they
                # carry client commercial data.
                logger.debug("mcp.response", extra=kv(tool=label, body=result))
                return result

            except TimeoutError:
                last = MCPTransientError(
                    f"timed out after {self.settings.mcp_timeout_seconds}s", tool=label
                )
            except MCPTransientError as exc:
                last = exc
            except MCPError:
                # Not retryable - a missing tool or bad argument will fail
                # identically next time.
                raise

            if attempt < attempts:
                backoff = 0.25 * (2 ** (attempt - 1))
                logger.warning(
                    "mcp.retry",
                    extra=kv(
                        tool=label,
                        attempt=attempt,
                        of=attempts,
                        backoff_s=backoff,
                        reason=str(last),
                    ),
                )
                await asyncio.sleep(backoff)

        logger.error("mcp.exhausted", extra=kv(tool=label, attempts=attempts, reason=str(last)))
        raise last or MCPError("failed after retries", tool=label)


class StreamableHTTPMCPClient(MCPClient):
    """Stateless Streamable HTTP MCP transport with per-call delegated auth."""

    def __init__(
        self,
        advertiser_id: str,
        *,
        settings: Settings | None = None,
        token_provider: DelegatedMCPTokenProvider | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(advertiser_id=advertiser_id, settings=settings)
        self._token_provider = token_provider or DelegatedMCPTokenProvider(self.settings)
        self._http_client = http_client

    async def _list_tools_raw(self) -> list[dict]:
        result = await self._request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
            raise MCPError("MCP tools/list returned an invalid response")
        return tools

    async def _call_tool_raw(self, name: str, arguments: dict) -> dict:
        external_arguments = dict(arguments)
        external_arguments.pop(ADVERTISER_ARG, None)
        result = await self._request(
            "tools/call",
            {"name": name, "arguments": external_arguments},
            tool=name,
        )
        if result.get("isError") is True:
            raise MCPError("The MCP tool rejected the request", tool=name)

        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            value = structured.get("result", structured)
            if isinstance(value, dict):
                return value

        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    try:
                        value = json.loads(item["text"])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        return value
        raise MCPError("The MCP tool returned an invalid response", tool=name)

    async def _request(
        self,
        method: str,
        params: dict,
        *,
        tool: str | None = None,
    ) -> dict:
        token = await self._token_provider.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Vowmade-Advertiser-Id": self.advertiser_id,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.settings.mcp_protocol_version,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    self.settings.mcp_server_url,
                    headers=headers,
                    json=payload,
                )
            else:
                async with httpx.AsyncClient(timeout=self.settings.mcp_timeout_seconds) as client:
                    response = await client.post(
                        self.settings.mcp_server_url,
                        headers=headers,
                        json=payload,
                    )
        except httpx.HTTPError as error:
            raise MCPTransientError("The MCP server is unavailable", tool=tool) from error

        if response.status_code in {408, 429} or response.status_code >= 500:
            raise MCPTransientError("The MCP server is temporarily unavailable", tool=tool)
        if response.status_code in {401, 403}:
            raise MCPError("MCP authentication or advertiser access was denied", tool=tool)
        if response.status_code >= 400:
            raise MCPError(f"MCP request failed with HTTP {response.status_code}", tool=tool)

        message = _decode_mcp_response(response)
        rpc_error = message.get("error")
        if isinstance(rpc_error, dict):
            if rpc_error.get("code") == -32601:
                raise MCPToolNotFoundError("The MCP tool is not available", tool=tool)
            raise MCPError("The MCP server rejected the request", tool=tool)
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPError("The MCP server returned an invalid response", tool=tool)
        return result


def _decode_mcp_response(response: httpx.Response) -> dict:
    content_type = response.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            message = response.json()
        else:
            data_lines = [
                line.removeprefix("data:").strip()
                for line in response.text.splitlines()
                if line.startswith("data:")
            ]
            message = json.loads("\n".join(data_lines))
    except (json.JSONDecodeError, ValueError) as error:
        raise MCPError("The MCP server returned malformed JSON-RPC") from error
    if not isinstance(message, dict):
        raise MCPError("The MCP server returned malformed JSON-RPC")
    return message


def create_mcp_client(advertiser_id: str) -> MCPClient:
    """Return the configured advertiser-scoped client."""
    settings = get_settings()

    if settings.use_mock_mcp:
        from app.tools.mcp.mock import MockMCPClient

        logger.info("Using MockMCPClient - canned VOW responses, no server contacted.")
        return MockMCPClient(advertiser_id=advertiser_id)

    return StreamableHTTPMCPClient(
        advertiser_id=advertiser_id,
        settings=settings,
        token_provider=DelegatedMCPTokenProvider(settings),
    )
