"""VOW API authentication.

The interface is fixed; the implementation is swappable via config.
Currently ships StubAuth (returns empty headers) because the client
hasn't confirmed the auth method yet. When they do, implement the
real provider and change VOW_AUTH_METHOD in settings.

See: Open Questions A1.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class VOWAuthProvider(ABC):
    """How the agent identifies itself to VOW's API."""

    @abstractmethod
    async def get_headers(self) -> dict[str, str]:
        """Return auth headers to attach to every outbound call."""


class StubAuth(VOWAuthProvider):
    """Placeholder — returns no auth headers.

    Works against VOW staging if the session is already authenticated
    (e.g. via browser cookie in dev). Replace with the real provider
    once the auth method is confirmed.
    """

    async def get_headers(self) -> dict[str, str]:
        logger.warning(
            "Using StubAuth — no real authentication. Fine for dev, not for staging/prod."
        )
        return {}


class SessionTokenAuth(VOWAuthProvider):
    """Authenticates via VOW's /auth endpoint with a service token.

    Implement when the client confirms the method.
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self._token: str | None = None

    async def get_headers(self) -> dict[str, str]:
        if not self._token:
            await self._authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    async def _authenticate(self):
        # TODO: implement when auth method is confirmed
        raise NotImplementedError("Awaiting client confirmation of auth method")


def create_auth_provider() -> VOWAuthProvider:
    """Factory — returns the configured auth provider."""
    # For now, always return stub. Switch when the client answers.
    # Future: read from settings to pick the implementation.
    return StubAuth()
