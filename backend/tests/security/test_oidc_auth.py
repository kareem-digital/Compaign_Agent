"""OAuth JWT validation at the VOW Agent trust boundary."""

from __future__ import annotations

import json
import time
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError

from app.config import Settings
from app.core.auth import (
    AccessTokenScopeError,
    AccessTokenValidationError,
    AuthenticatedUser,
    JWTAccessTokenVerifier,
    require_authenticated_user,
)
from app.core.context import subject_access_token
from app.main import create_app

ISSUER = "https://vow.example.com/api/identity/oauth2"
AUDIENCE = "https://agent.example.com"
KID = "current-signing-key"


def _settings() -> Settings:
    return Settings(
        debug=False,
        vow_oidc_issuer=ISSUER,
        vow_agent_audience=AUDIENCE,
        vow_agent_required_scopes=["read"],
        log_file="",
    )


def _signing_material() -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return private_key, public_jwk


def _token(private_key: Any, **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "user-123",
        "aud": AUDIENCE,
        "client_id": "vow-agent-mfe",
        "scope": "openid read",
        "iat": now,
        "exp": now + 600,
        "jti": "token-id",
    }
    claims.update(overrides)
    return cast(
        str,
        jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": KID, "typ": "at+jwt"},
        ),
    )


def _verifier(public_jwk: dict[str, Any]) -> tuple[JWTAccessTokenVerifier, list[str]]:
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"keys": [public_jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    return JWTAccessTokenVerifier(_settings(), http_client=client), requests


@pytest.mark.asyncio
async def test_accepts_vow_jwt_for_the_agent_resource_and_caches_jwks():
    private_key, public_jwk = _signing_material()
    verifier, requests = _verifier(public_jwk)

    first = await verifier.verify(_token(private_key))
    second = await verifier.verify(_token(private_key, jti="second-token"))

    assert first.subject == "user-123"
    assert first.client_id == "vow-agent-mfe"
    assert first.scopes == frozenset({"openid", "read"})
    assert second.claims["jti"] == "second-token"
    assert requests == [f"{ISSUER}/.well-known/jwks.json"]


@pytest.mark.asyncio
async def test_authenticated_dependency_binds_raw_token_to_request_context():
    private_key, public_jwk = _signing_material()
    verifier, _ = _verifier(public_jwk)
    raw_token = _token(private_key)
    try:
        user = await require_authenticated_user(
            HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=raw_token,
            ),
            verifier,
        )
    finally:
        await verifier.close()

    assert user.subject == "user-123"
    assert subject_access_token() == raw_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://attacker.example.com"),
        ("aud", "https://another-api.example.com"),
        ("exp", 1),
    ],
)
async def test_rejects_wrong_issuer_audience_and_expiry(claim, value):
    private_key, public_jwk = _signing_material()
    verifier, _ = _verifier(public_jwk)

    with pytest.raises(AccessTokenValidationError):
        await verifier.verify(_token(private_key, **{claim: value}))


@pytest.mark.asyncio
async def test_rejects_id_tokens_and_insufficient_scope():
    private_key, public_jwk = _signing_material()
    verifier, _ = _verifier(public_jwk)
    claims = {
        "iss": ISSUER,
        "sub": "user-123",
        "aud": AUDIENCE,
        "client_id": "vow-agent-mfe",
        "scope": "openid",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
        "jti": "id-token-shaped",
    }
    id_token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": KID, "typ": "JWT"},
    )

    with pytest.raises(AccessTokenValidationError):
        await verifier.verify(id_token)
    with pytest.raises(AccessTokenScopeError):
        await verifier.verify(_token(private_key, scope="openid"))


@pytest.mark.asyncio
async def test_unknown_key_fails_closed_without_bypassing_jwks_cache():
    private_key, public_jwk = _signing_material()
    verifier, requests = _verifier(public_jwk)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "user-123",
            "aud": AUDIENCE,
            "client_id": "vow-agent-mfe",
            "scope": "read",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "jti": "unknown-key",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "unknown", "typ": "at+jwt"},
    )

    with pytest.raises(AccessTokenValidationError):
        await verifier.verify(token)
    assert len(requests) == 1


class _InsufficientScopeVerifier(JWTAccessTokenVerifier):
    def __init__(self) -> None:
        self.settings = _settings()

    async def verify(self, token: str) -> AuthenticatedUser:
        raise AccessTokenScopeError

    async def close(self) -> None:
        return None


def test_health_is_public_but_session_endpoints_require_a_bearer_token():
    app = create_app(
        settings=_settings(),
        access_token_verifier=_InsufficientScopeVerifier(),
    )
    client = TestClient(app)

    assert client.get("/api/v1/health/live").status_code == 200
    response = client.get(
        "/api/v1/sessions/session-1",
        headers={"Vowmade-Advertiser-Id": "advertiser-1"},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


def test_insufficient_scope_returns_rfc6750_challenge():
    app = create_app(
        settings=_settings(),
        access_token_verifier=_InsufficientScopeVerifier(),
    )
    response = TestClient(app).get(
        "/api/v1/sessions/session-1",
        headers={
            "Authorization": "Bearer valid-but-under-scoped",
            "Vowmade-Advertiser-Id": "advertiser-1",
        },
    )

    assert response.status_code == 403
    assert response.headers["WWW-Authenticate"] == (
        'Bearer error="insufficient_scope", scope="read"'
    )


@pytest.mark.asyncio
async def test_local_authentication_synthesizes_a_stable_user_without_a_token():
    settings = Settings(
        environment="local",
        auth_mode="local",
        local_auth_subject="developer-123",
        local_auth_client_id="local-ui",
        vow_agent_required_scopes=["read", "plan"],
        log_file="",
    )
    verifier = JWTAccessTokenVerifier(settings)
    try:
        user = await require_authenticated_user(None, verifier)
    finally:
        await verifier.close()

    assert user == AuthenticatedUser(
        subject="developer-123",
        client_id="local-ui",
        scopes=frozenset({"read", "plan"}),
        claims={
            "sub": "developer-123",
            "client_id": "local-ui",
            "scope": "read plan",
            "auth_mode": "local",
        },
    )
    assert subject_access_token() is None


@pytest.mark.parametrize("environment", ["sandbox", "staging", "production"])
def test_local_authentication_is_rejected_outside_local(environment):
    with pytest.raises(ValidationError, match="allowed only when environment='local'"):
        Settings(environment=environment, auth_mode="local", log_file="")
