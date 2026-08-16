"""Per-request correlation identifiers.

The problem this solves: a trader says "my session went wrong this morning" and
you need to pull that one conversation out of a shared log stream. Without a
correlating key every line is an orphan.

Held in context variables rather than passed as parameters, because the values
are needed in places that have no business knowing about HTTP - a planning
node, the MCP client, the LLM wrapper. Threading `session_id` through every
signature to reach them would be noise in a dozen files.

Context vars are per-task, so concurrent requests never see each other's values.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_advertiser_id: ContextVar[str | None] = ContextVar("advertiser_id", default=None)
_subject_access_token: ContextVar[str | None] = ContextVar(
    "subject_access_token",
    default=None,
)


@dataclass(frozen=True)
class DelegatedMCPToken:
    value: str
    expires_at: float


_delegated_mcp_token: ContextVar[DelegatedMCPToken | None] = ContextVar(
    "delegated_mcp_token",
    default=None,
)

_VARS = {
    "request_id": _request_id,
    "session_id": _session_id,
    "advertiser_id": _advertiser_id,
}


def bind(
    request_id: str | None = None,
    session_id: str | None = None,
    advertiser_id: str | None = None,
) -> None:
    """Attach identifiers to the current task.

    Only sets what is given, so a caller that learns the session ID later can
    add it without clearing the request ID set earlier.
    """
    if request_id is not None:
        _request_id.set(request_id)
    if session_id is not None:
        _session_id.set(session_id)
    if advertiser_id is not None:
        _advertiser_id.set(advertiser_id)


def current() -> dict[str, str]:
    """Whatever is currently bound, omitting anything unset."""
    values: dict[str, str] = {}
    for name, var in _VARS.items():
        value = var.get()
        if value is not None:
            values[name] = value
    return values


def bind_subject_access_token(token: str) -> None:
    """Bind the incoming user token without exposing it to logging context."""
    _subject_access_token.set(token)
    _delegated_mcp_token.set(None)


def subject_access_token() -> str | None:
    return _subject_access_token.get()


def delegated_mcp_token() -> DelegatedMCPToken | None:
    return _delegated_mcp_token.get()


def bind_delegated_mcp_token(token: DelegatedMCPToken) -> None:
    _delegated_mcp_token.set(token)


def clear() -> None:
    """Reset everything. Mainly for tests - each request gets a fresh context."""
    for var in _VARS.values():
        var.set(None)
    _subject_access_token.set(None)
    _delegated_mcp_token.set(None)
