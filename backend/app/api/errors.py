"""Exception handlers: one place where a typed failure becomes a status code.

Before this existed the mapping lived inline in `sessions.chat` and nowhere
else, so a `RegistryValidationError` raised anywhere - including from a route
that had not thought about it - surfaced as an untyped 500 with the cause
dropped. The trader saw "Agent error"; the log had a traceback and no verdict.

Two rules here:

  * **The cause survives.** Every handler logs the exception with its type
    before translating it, so the log says what actually happened even when the
    response cannot.
  * **The response carries `request_id`.** It is the one thing a trader can
    read off a failure and quote, and the one thing that makes the log
    searchable. Without it "it broke this morning" is unfalsifiable.

Handlers are a safety net, not the primary path. A route that wants a specific
message for a specific failure still catches it itself - `sessions.chat` does,
because "VOW is unavailable" reads better than a generic 502. What changed is
that not catching it is no longer silent.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.context import current
from app.core.exceptions import (
    AdvertiserContextMissingError,
    ConfigurationError,
    GroundingError,
    MCPError,
    RegistrySyncError,
    RegistryValidationError,
    VowAgentError,
    VowApiError,
)
from app.core.logging import kv

logger = logging.getLogger(__name__)

# Ordered most specific first: the first class an exception is an instance of
# wins, so `RegistryValidationError` is not swallowed by `RegistrySyncError`.
#
# The messages are deliberately plain. They go to a trader, so they say what
# happened to their request, never which component failed or why - that is what
# the log line is for.
_MAPPING: tuple[tuple[type[Exception], int, str], ...] = (
    (
        AdvertiserContextMissingError,
        400,
        "Advertiser context is required for this request.",
    ),
    (
        RegistryValidationError,
        503,
        "Reference data from VOW did not pass validation, so planning is paused.",
    ),
    (
        RegistrySyncError,
        503,
        "Reference data from VOW could not be loaded, so planning is paused.",
    ),
    (MCPError, 502, "VOW is unavailable."),
    (VowApiError, 502, "VOW is unavailable."),
    (
        GroundingError,
        500,
        "A value could not be confirmed against VOW and was not used.",
    ),
    (ConfigurationError, 500, "The service is misconfigured."),
    (VowAgentError, 500, "Agent error."),
)


def _describe(exc: Exception) -> tuple[int, str]:
    for kind, status, message in _MAPPING:
        if isinstance(exc, kind):
            return status, message
    return 500, "Agent error."


async def handle_vow_agent_error(request: Request, exc: Exception) -> JSONResponse:
    """Translate any `VowAgentError` into a typed response, logging the cause."""
    status, message = _describe(exc)

    fields = {
        "reason": type(exc).__name__,
        "path": request.url.path,
        "status": status,
    }
    # A registry rejection carries the whole violation list precisely so a
    # reviewer can tell "the server's shape changed" from "one row is bad".
    # Dropping it here would waste the reason it is collected.
    violations = getattr(exc, "violations", None)
    if violations:
        fields["violations"] = violations[:20]
        fields["violation_count"] = len(violations)
    tool = getattr(exc, "tool", None)
    if tool:
        fields["tool"] = tool

    logger.exception("request.failed", extra=kv(**fields))

    body = {"detail": message, "error": type(exc).__name__}
    request_id = current().get("request_id")
    if request_id:
        body["request_id"] = request_id

    return JSONResponse(status_code=status, content=body)


def register_error_handlers(app: FastAPI) -> None:
    """Attach the handlers. Called once from the app factory."""
    app.add_exception_handler(VowAgentError, handle_vow_agent_error)
