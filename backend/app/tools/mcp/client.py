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

Scoping note: MCP has no request headers, so the advertiser is injected as a
tool *argument* (`advertiser_id`). If VOW's server names it differently, change
`ADVERTISER_ARG` here and nowhere else.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod

from app.config import Settings, get_settings
from app.core.exceptions import (
    AdvertiserContextMissingError,
    MCPError,
    MCPTransientError,
)
from app.core.logging import kv
from app.governance.agt import get_guard

logger = logging.getLogger(__name__)

ADVERTISER_ARG = "advertiser_id"


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
        auth_token: str | None = None,
        settings: Settings | None = None,
    ):
        self.advertiser_id = advertiser_id
        self.settings = settings or get_settings()
        # Auth seam (PLT-05, open question A1). Authenticating to an MCP server
        # is transport-level - a token on the connection, not a header per call -
        # so it is held here and used by whichever transport needs it. Empty
        # until the client confirms the method.
        self.auth_token = auth_token or self.settings.mcp_auth_token

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

    async def _retrying(self, label: str, operation):
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


def create_mcp_client(advertiser_id: str) -> MCPClient:
    """Return the configured client for this advertiser.

    Mock until the client ships the real server; then implement a transport
    over the `mcp` SDK and switch on USE_MOCK_MCP.
    """
    settings = get_settings()

    if settings.use_mock_mcp:
        from app.tools.mcp.mock import MockMCPClient

        logger.info("Using MockMCPClient - canned VOW responses, no server contacted.")
        return MockMCPClient(advertiser_id=advertiser_id)

    raise NotImplementedError(
        "No real MCP transport yet. Implement MCPClient over the `mcp` SDK "
        "(add it to requirements.txt) and wire it here, or set USE_MOCK_MCP=true."
    )
