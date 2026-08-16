"""Strict RFC 9068 bearer-token validation for VOW Agent."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Annotated, Any, cast

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.core.context import bind_subject_access_token

_bearer = HTTPBearer(auto_error=False)
UNKNOWN_KID_REFRESH_INTERVAL_SECONDS = 5.0


class AccessTokenValidationError(Exception):
    """The bearer token is absent, malformed, unverifiable, or expired."""


class AccessTokenScopeError(Exception):
    """The token is valid but lacks a required OAuth scope."""


@dataclass(frozen=True)
class AuthenticatedUser:
    subject: str
    client_id: str
    scopes: frozenset[str]
    claims: dict[str, Any]


class JWTAccessTokenVerifier:
    """Validate VOW-issued access tokens against the cached VOW JWKS."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client or httpx.AsyncClient(timeout=5.0)
        self._owns_http_client = http_client is None
        self._keys: dict[str, Any] = {}
        self._keys_expires_at = 0.0
        self._keys_refreshed_at = 0.0
        self._keys_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as error:
            raise AccessTokenValidationError("Malformed access token") from error

        if header.get("alg") != "RS256":
            raise AccessTokenValidationError("Unsupported access-token algorithm")
        if header.get("typ") not in {"at+jwt", "application/at+jwt"}:
            raise AccessTokenValidationError("Token is not an OAuth access token")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise AccessTokenValidationError("Access token has no signing key ID")

        signing_key = await self._get_signing_key(key_id)
        try:
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.settings.vow_agent_audience,
                issuer=self.settings.vow_oidc_issuer,
                leeway=self.settings.vow_oidc_clock_skew_seconds,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "client_id",
                        "iat",
                        "exp",
                        "jti",
                    ]
                },
            )
        except jwt.PyJWTError as error:
            raise AccessTokenValidationError("Invalid access token") from error

        scopes = self._parse_scopes(claims.get("scope"))
        required_scopes = set(self.settings.vow_agent_required_scopes)
        if not required_scopes.issubset(scopes):
            raise AccessTokenScopeError("Access token has insufficient scope")

        subject = claims.get("sub")
        client_id = claims.get("client_id")
        if not isinstance(subject, str) or not subject:
            raise AccessTokenValidationError("Access token has no subject")
        if not isinstance(client_id, str) or not client_id:
            raise AccessTokenValidationError("Access token has no client ID")
        return AuthenticatedUser(
            subject=subject,
            client_id=client_id,
            scopes=frozenset(scopes),
            claims=claims,
        )

    async def _get_signing_key(self, key_id: str) -> Any:
        keys = await self._get_keys()
        signing_key = keys.get(key_id)
        if (
            signing_key is None
            and time.monotonic() - self._keys_refreshed_at >= UNKNOWN_KID_REFRESH_INTERVAL_SECONDS
        ):
            keys = await self._get_keys(force_refresh=True)
            signing_key = keys.get(key_id)
        if signing_key is None:
            raise AccessTokenValidationError("Unknown access-token signing key")
        return signing_key

    async def _get_keys(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force_refresh and self._keys and now < self._keys_expires_at:
            return self._keys

        async with self._keys_lock:
            now = time.monotonic()
            if not force_refresh and self._keys and now < self._keys_expires_at:
                return self._keys
            try:
                response = await self._http_client.get(self.settings.resolved_vow_oidc_jwks_url)
                response.raise_for_status()
                document = response.json()
                raw_keys = document.get("keys")
                if not isinstance(raw_keys, list):
                    raise ValueError("JWKS has no keys array")
                parsed_keys = {
                    item["kid"]: jwt.PyJWK.from_dict(item).key
                    for item in raw_keys
                    if isinstance(item, dict)
                    and isinstance(item.get("kid"), str)
                    and item.get("alg") == "RS256"
                    and item.get("use") in {None, "sig"}
                }
            except (httpx.HTTPError, ValueError, jwt.PyJWTError) as error:
                raise AccessTokenValidationError(
                    "Unable to load access-token signing keys"
                ) from error
            if not parsed_keys:
                raise AccessTokenValidationError("JWKS has no usable signing keys")
            self._keys = parsed_keys
            self._keys_refreshed_at = now
            self._keys_expires_at = now + self.settings.vow_oidc_jwks_cache_seconds
            return self._keys

    @staticmethod
    def _parse_scopes(value: object) -> set[str]:
        if isinstance(value, str):
            return set(value.split())
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return set(value)
        return set()


def get_access_token_verifier(request: Request) -> JWTAccessTokenVerifier:
    return cast(JWTAccessTokenVerifier, request.app.state.access_token_verifier)


async def require_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer),
    ],
    verifier: Annotated[
        JWTAccessTokenVerifier,
        Depends(get_access_token_verifier),
    ],
) -> AuthenticatedUser:
    if verifier.settings.auth_mode == "local":
        settings = verifier.settings
        scopes = frozenset(settings.vow_agent_required_scopes)
        return AuthenticatedUser(
            subject=settings.local_auth_subject,
            client_id=settings.local_auth_client_id,
            scopes=scopes,
            claims={
                "sub": settings.local_auth_subject,
                "client_id": settings.local_auth_client_id,
                "scope": " ".join(settings.vow_agent_required_scopes),
                "auth_mode": "local",
            },
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error("A bearer access token is required")
    try:
        user = await verifier.verify(credentials.credentials)
        bind_subject_access_token(credentials.credentials)
        return user
    except AccessTokenScopeError as error:
        required_scope = " ".join(verifier.settings.vow_agent_required_scopes)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient OAuth scope",
            headers={
                "WWW-Authenticate": (f'Bearer error="insufficient_scope", scope="{required_scope}"')
            },
        ) from error
    except AccessTokenValidationError as error:
        raise _authentication_error("Invalid or expired access token") from error


def _authentication_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )
