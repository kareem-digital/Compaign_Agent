"""Application exception hierarchy.

Typed exceptions let the agent graph branch on failure rather than
parsing error strings.
"""


class VowAgentError(Exception):
    """Base for everything this service raises."""


class ConfigurationError(VowAgentError):
    """Something required is missing or malformed at startup."""


class VowApiError(VowAgentError):
    """A call to the VOW platform API failed."""

    def __init__(self, message: str, status_code: int | None = None, endpoint: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class VowAuthError(VowApiError):
    """Authentication or authorisation against the VOW API failed."""


class KillSwitchEngagedError(VowAgentError):
    """All VOW access is halted by the emergency stop.

    Not a permission problem - a deliberate, temporary halt. Maps to 503 rather
    than 403: 403 says "you may never do this", 503 says "not right now". The
    second is true, and more useful to whoever is waiting.
    """


class PolicyDeniedError(VowAgentError):
    """A governance policy refused the action.

    Not a failure - the system working. Distinct from MCPError so the API can
    answer 403 (you may not do this) rather than 502 (VOW is unavailable).
    """

    def __init__(self, message: str, tool: str | None = None, rule: str | None = None):
        super().__init__(message)
        self.tool = tool
        self.rule = rule


class MCPError(VowAgentError):
    """A call to VOW's MCP server failed."""

    def __init__(self, message: str, tool: str | None = None):
        super().__init__(message)
        self.tool = tool


class MCPToolNotFoundError(MCPError):
    """The MCP server does not expose the tool we asked for.

    Usually means the server version and our expectations have diverged -
    worth surfacing loudly rather than treating as a transient failure.
    """


class MCPTransientError(MCPError):
    """A retryable MCP failure: timeout, connection reset, server busy."""


class AdvertiserContextMissingError(VowAgentError):
    """A scoped call was attempted without advertiser context.

    Fail closed: we never default to an advertiser.
    """


class RegistrySyncError(VowAgentError):
    """The grounded registry could not be built from VOW's reference data.

    Raised at ingest time, and only when the snapshot would be unusable. A
    missing optional source degrades instead - see the partial-failure policy in
    `app/knowledge/registry/ingestion.py`.
    """


class RegistryValidationError(RegistrySyncError):
    """Incoming reference data failed the checks that gate a registry update.

    Carries every violation rather than the first, because a reviewer needs the
    whole picture to decide whether the server's shape changed or one row is bad.
    """

    def __init__(self, message: str, violations: list[str] | None = None):
        super().__init__(message)
        self.violations = violations or []


class GroundingError(VowAgentError):
    """An identifier could not be validated against the grounded registry.

    The *hard* half of validation. The soft half is `ValidationResponse`, which
    the agent turns into a question for the trader ("not that - try one of
    these"). This is for code paths where proceeding is unacceptable: anywhere a
    deal ID or audience set ID is about to be sent to VOW. Raised from exactly
    one place, `registry.validate.assert_grounded`.
    """
