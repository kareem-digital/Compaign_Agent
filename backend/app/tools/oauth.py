"""Request-scoped RFC 8693 exchange for delegated MCP access tokens."""

from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.core.context import (
    DelegatedMCPToken,
    bind_delegated_mcp_token,
    delegated_mcp_token,
    subject_access_token,
)
from app.core.exceptions import MCPError, MCPTransientError

TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
EXPIRY_SAFETY_MARGIN_SECONDS = 5


class DelegatedMCPTokenProvider:
    """Exchange the current request's Agent token, never graph-cached identity."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client

    async def get_token(self) -> str:
        source_token = subject_access_token()
        if not source_token:
            raise MCPError("No request-scoped user token is available for MCP")

        cached = delegated_mcp_token()
        if cached is not None and time.monotonic() < cached.expires_at:
            return cached.value

        data = {
            "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
            "subject_token": source_token,
            "subject_token_type": ACCESS_TOKEN_TYPE,
            "requested_token_type": ACCESS_TOKEN_TYPE,
            "resource": self.settings.resolved_mcp_oauth_resource,
            "scope": " ".join(self.settings.mcp_oauth_scopes),
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    self.settings.resolved_mcp_oauth_token_url,
                    data=data,
                    auth=httpx.BasicAuth(
                        self.settings.mcp_oauth_client_id,
                        self.settings.mcp_oauth_client_secret.get_secret_value(),
                    ),
                )
            else:
                async with httpx.AsyncClient(timeout=self.settings.mcp_timeout_seconds) as client:
                    response = await client.post(
                        self.settings.resolved_mcp_oauth_token_url,
                        data=data,
                        auth=httpx.BasicAuth(
                            self.settings.mcp_oauth_client_id,
                            self.settings.mcp_oauth_client_secret.get_secret_value(),
                        ),
                    )
        except httpx.HTTPError as error:
            raise MCPTransientError("OAuth token exchange is unavailable") from error

        if response.status_code in {408, 429} or response.status_code >= 500:
            raise MCPTransientError("OAuth token exchange is temporarily unavailable")
        if response.status_code != 200:
            raise MCPError("OAuth token exchange was rejected")

        try:
            payload = response.json()
            token = payload["access_token"]
            token_type = payload["token_type"]
            issued_token_type = payload["issued_token_type"]
            expires_in = int(payload["expires_in"])
        except (KeyError, TypeError, ValueError) as error:
            raise MCPError("OAuth token exchange returned an invalid response") from error

        if (
            not isinstance(token, str)
            or not token
            or not isinstance(token_type, str)
            or token_type.lower() != "bearer"
            or issued_token_type != ACCESS_TOKEN_TYPE
            or expires_in <= 0
        ):
            raise MCPError("OAuth token exchange returned an invalid response")

        cached_token = DelegatedMCPToken(
            value=token,
            expires_at=time.monotonic() + max(0, expires_in - EXPIRY_SAFETY_MARGIN_SECONDS),
        )
        bind_delegated_mcp_token(cached_token)
        return token
