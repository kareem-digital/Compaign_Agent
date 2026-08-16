"""Application settings, loaded from environment variables.

Every configurable value lives here. Nothing is hard-coded elsewhere,
and no secret is ever committed - see .env.example for the shape.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Service ---
    app_name: str = "vow-agent"
    environment: Literal["local", "sandbox", "staging", "production"] = "local"
    debug: bool = False

    # --- Logging ---
    # DEBUG carries full payloads (MCP bodies, LLM prompts, extracted values),
    # so keep production at INFO.
    log_level: str = "INFO"
    # Console only. The file is always JSON, ready for Datadog later.
    log_format: Literal["text", "json"] = "text"
    # Relative paths resolve against backend/. Empty disables file logging.
    log_file: str = "logs/vow-agent.log"
    # Budget for EVERYTHING in logs/ - the active file plus its backups, not
    # per file. Divided evenly, so 10 MB across 5 files is 2 MB each.
    log_total_max_bytes: int = 10_000_000
    log_file_backup_count: int = 4

    # --- API ---
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- VOW OpenID Provider / access-token validation ---
    # `local` bypasses bearer-token validation and is rejected unless the
    # service also runs with ENVIRONMENT=local.
    auth_mode: Literal["oidc", "local"] = "oidc"
    local_auth_subject: str = Field(default="local-development-user", min_length=1)
    local_auth_client_id: str = Field(default="vow-agent-local", min_length=1)
    vow_oidc_issuer: str = "http://localhost:8000/api/identity/oauth2"
    vow_oidc_jwks_url: str = ""
    vow_agent_audience: str = "http://localhost:8001"
    vow_agent_required_scopes: list[str] = Field(default_factory=lambda: ["read"])
    vow_oidc_jwks_cache_seconds: int = Field(default=300, ge=0)
    vow_oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)

    # --- Database (PLT-03 checkpointer, KNW registry) ---
    database_url: str = "postgresql+asyncpg://vowagent:vowagent@localhost:5432/vowagent"
    # --- Checkpointer ---
    # True  = in-memory (no Postgres needed; state lost on restart)
    # False = Postgres (state survives restarts; needs database_url)
    use_memory_checkpointer: bool = True

    # --- Grounded registry (KNW-02) ---
    # Reference data ingested from VOW through MCP, so the flow's valid values
    # come from the platform rather than from constants in our nodes. In-process
    # only for now: the snapshot is derived data, rebuildable in a handful of
    # tool calls, and requiring Postgres for it would make Postgres mandatory
    # for the first time (see use_memory_checkpointer above).
    registry_ttl_seconds: int = 900
    # Markets warmed on first sync. Everything else fills lazily on first use,
    # because deals, rate cards, categories and targeting are all market-scoped
    # and eager-fetching every market costs four calls each.
    registry_eager_markets: list[str] = Field(default_factory=lambda: ["GB"])
    # True turns any degraded source into a hard failure. Worth setting in CI so
    # drift is loud; left False in production so a dropdown's tool going missing
    # cannot take the planning flow down.
    registry_strict_sync: bool = False
    # What to do when incoming data is not backward-compatible with the previous
    # snapshot. "warn" swaps it in and logs loudly - planning against stale
    # prices is worse than an alarming log line.
    registry_on_breaking_change: Literal["accept", "warn", "reject"] = "warn"
    # Above this share of a source's rows failing validation, treat the whole
    # source as failed: the shape changed, rather than one row being bad.
    registry_max_reject_ratio: float = 0.25
    # Empty uses the packaged data/targeting_types.json. Override to hot-patch
    # the targeting types without a release.
    registry_targeting_config_path: str = ""

    # --- VOW platform access via MCP (replaces the REST wrappers) ---
    # The client exposes VOW's APIs as an MCP server, so the agent calls tools
    # rather than endpoints. Transport is swappable; mock is the default until
    # the real server exists.
    use_mock_mcp: bool = True
    mcp_server_url: str = ""
    mcp_timeout_seconds: float = 15.0
    mcp_max_retries: int = 3
    mcp_protocol_version: str = "2026-07-28"
    # Backend-only RFC 8693 credentials. The browser token is exchanged per
    # request for a user-scoped token whose audience is the MCP server.
    mcp_oauth_token_url: str = ""
    mcp_oauth_client_id: str = ""
    mcp_oauth_client_secret: SecretStr = SecretStr("")
    mcp_oauth_resource: str = ""
    mcp_oauth_scopes: list[str] = Field(default_factory=lambda: ["read"])

    # --- VOW platform REST access (legacy, app/tools/base.py) ---
    # Superseded by MCP above. Kept until the REST wrappers are retired in a
    # deliberate, separate change - removing these while `base.py` still reads
    # them breaks it at runtime rather than at import, which is the worst way
    # to find out.
    vow_api_base_url: str = "https://staging.vowmade.dev/api"
    vow_api_timeout_seconds: float = 10.0
    vow_api_max_retries: int = 3

    # --- Governance (AGT) ---
    # Override the policy file, mainly for tests. Empty uses the one shipped in
    # app/governance/policies/. Deliberately NO on/off switch: a guardrail that
    # an environment variable can disable is not a guardrail.
    governance_policy_path: str = ""

    # Emergency stop. The PRESENCE of this file halts every VOW call:
    #   touch KILL_SWITCH   -> agent halted
    #   rm KILL_SWITCH      -> agent resumes
    # Presence rather than contents, so it cannot be ambiguously half-enabled.
    # Relative paths resolve against the process working directory.
    #
    # TMP-19: a file works for a single server. Move to a database flag once
    # there are several instances, or an authenticated endpoint once we have
    # auth (A1). Recorded in docs/PROVISIONAL_DECISIONS.md for that decision.
    kill_switch_path: str = "KILL_SWITCH"

    # Audit trail: the durable record of every allow/deny decision. Distinct
    # from logging - logs are for debugging and expire, this is evidence.
    #
    # TMP-01: a local file for now. A file inside a container dies on every
    # deploy, so this becomes a Postgres sink once we have database access.
    # Empty path = memory only, which is right for tests and useless for
    # compliance; the service warns loudly at startup when unconfigured.
    audit_log_path: str = ""
    # Signs each entry so tampering is detectable. A SECRET: set it in the
    # environment, never commit it. Rotate it and older entries can no longer
    # be verified.
    audit_hmac_key: str = ""

    # --- Multi-tenancy ---
    # Every MCP call is scoped to an advertiser and fails closed without one.
    # This fallback applies in local dev only, so the chat endpoint stays usable
    # before the UI sends the header. Staging and production reject instead.
    dev_advertiser_id: str = "dev-advertiser-0001"

    # --- LLM ---
    # Used to understand briefs and to phrase follow-up questions. VOW already
    # uses OpenAI for audience intelligence, so this keeps one provider.
    # Leave the key empty and the agent falls back to pattern matching - less
    # capable, but it means tests and CI never need a secret.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: str = ""
    llm_model: str = "claude-sonnet-4-5"
    llm_temperature: float = 0.0

    # The turn's latency budget, divided. The browser stops waiting at 30 seconds
    # (`frontend/src/lib/config.ts`), and a turn that overruns it renders as "the
    # agent could not be reached" however well the turn actually went. Extraction
    # may retry because without it there is no turn; voicing may not, because the
    # computed prose is already there to fall back to.
    llm_timeout_seconds: float = 10.0
    llm_max_retries: int = 1

    # Re-voice each turn's deterministic blocks into one reply - see `agent.voice`.
    # Only has an effect when a key is configured, so turning it off is how you get
    # the raw computed prose from a deployment that has one.
    voice_enabled: bool = True
    # Wall clock, not just the HTTP call: `voice.render_turn` enforces it with
    # `asyncio.wait_for`. Generous against the ~6s the call now takes, because a
    # deadline is a backstop and not a target.
    voice_timeout_seconds: float = 12.0
    # Phrasing is not a reasoning task, and on a reasoning model saying so is the
    # difference between 22.6s and 5.5s per turn - measured on gpt-5-mini against
    # a real plan. Applied only to models that accept it (see `llm._build`), so
    # the gpt-4o-mini default is unaffected. Empty disables it.
    voice_reasoning_effort: str = "low"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def resolved_vow_oidc_jwks_url(self) -> str:
        return self.vow_oidc_jwks_url or (
            f"{self.vow_oidc_issuer.rstrip('/')}/.well-known/jwks.json"
        )

    @property
    def resolved_mcp_oauth_token_url(self) -> str:
        return self.mcp_oauth_token_url or f"{self.vow_oidc_issuer.rstrip('/')}/token/"

    @property
    def resolved_mcp_oauth_resource(self) -> str:
        return self.mcp_oauth_resource or self.mcp_server_url

    @model_validator(mode="after")
    def validate_authentication_settings(self) -> "Settings":
        if self.auth_mode == "local" and self.environment != "local":
            raise ValueError("auth_mode='local' is allowed only when environment='local'")
        if not self.vow_agent_required_scopes:
            raise ValueError("vow_agent_required_scopes must not be empty")
        if any(
            not scope or any(char.isspace() for char in scope)
            for scope in self.vow_agent_required_scopes
        ):
            raise ValueError("vow_agent_required_scopes must contain OAuth scope tokens")
        if not self.use_mock_mcp:
            required_mcp_settings = {
                "mcp_server_url": self.mcp_server_url,
                "mcp_oauth_client_id": self.mcp_oauth_client_id,
                "mcp_oauth_client_secret": self.mcp_oauth_client_secret.get_secret_value(),
                "mcp_oauth_resource": self.resolved_mcp_oauth_resource,
            }
            missing = sorted(name for name, value in required_mcp_settings.items() if not value)
            if missing:
                raise ValueError("live MCP requires: " + ", ".join(missing))
            if not self.mcp_oauth_scopes or any(
                not scope or any(char.isspace() for char in scope)
                for scope in self.mcp_oauth_scopes
            ):
                raise ValueError("mcp_oauth_scopes must contain OAuth scope tokens")
        if self.is_production:
            urls = (
                self.vow_oidc_issuer,
                self.resolved_vow_oidc_jwks_url,
                self.vow_agent_audience,
                *(
                    (
                        self.mcp_server_url,
                        self.resolved_mcp_oauth_token_url,
                        self.resolved_mcp_oauth_resource,
                    )
                    if not self.use_mock_mcp
                    else ()
                ),
                *self.cors_origins,
            )
            if any(not value.startswith("https://") for value in urls):
                raise ValueError("production authentication URLs and origins must use HTTPS")
            if "*" in self.cors_origins:
                raise ValueError("production cors_origins must not contain a wildcard")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached so settings are parsed once per process."""
    return Settings()
