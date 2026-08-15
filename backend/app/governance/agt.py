"""Policy enforcement in front of every VOW call.

The agent decides what it wants to do; this decides whether it may. Ordinary
deterministic code, evaluated before the request leaves the process, so the
LLM's cooperation is not required for the guardrails to hold.

Wired into `MCPClient.call_tool()` - the one method every VOW call passes
through. Nothing reaches VOW without coming past here.

Two implementation notes, both learned the hard way against AGT 4.1.0:

**Why not `govern()`.** AGT's convenience wrapper reads a single `action=`
keyword argument, which would mean reshaping `call_tool(name, arguments)` to
suit the library. Calling the policy engine directly keeps our signature and
costs about ten lines.

**Why `policy.agents = ["*"]`.** A policy that names no agents loads with an
empty agent list and may then never apply - silently permitting everything.
AGT's own wrapper defaults it; so must we.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from agentmesh.governance import AuditLog, FileAuditSink, PolicyEngine

from app.config import get_settings
from app.core.context import current
from app.core.exceptions import (
    ConfigurationError,
    KillSwitchEngagedError,
    PolicyDeniedError,
)
from app.core.logging import kv

logger = logging.getLogger(__name__)

DEFAULT_POLICY_PATH = Path(__file__).parent / "policies" / "vow_ctv.yaml"

# Any matching deny beats any matching allow, whatever the rule order.
CONFLICT_STRATEGY = "deny_overrides"


def _hash_arguments(arguments: dict | None) -> str:
    """Fingerprint the arguments rather than storing them.

    An audit record kept for years must not contain a client's budgets and
    campaign plans. A hash still settles a dispute: if someone later claims the
    request was for 50,000 rather than 500,000, hash 50,000 and compare. Proof
    without retention.
    """
    payload = json.dumps(arguments or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PolicyGuard:
    """Loads the policy once and answers allow/deny for each action."""

    def __init__(self, policy_path: Path):
        self._engine = PolicyEngine(conflict_strategy=CONFLICT_STRATEGY)

        # Fail closed at startup. A service that boots with a broken policy and
        # permits everything is worse than one that refuses to boot.
        try:
            policy = self._engine.load_yaml_file(str(policy_path))
        except Exception as exc:
            raise ConfigurationError(
                f"Governance policy could not be loaded from {policy_path}: {exc}"
            ) from exc

        if not policy.agent and not policy.agents:
            policy.agents = ["*"]

        self.policy_name = policy.name
        self.rule_count = len(getattr(policy, "rules", []) or [])
        logger.info(
            "governance.policy_loaded",
            extra=kv(policy=self.policy_name, rules=self.rule_count, path=str(policy_path)),
        )

        self.audit = self._build_audit()

        # Tracks the switch's last observed state so only the transition is
        # logged at CRITICAL, not every blocked call.
        self._kill_switch_last_seen = False

    def _kill_switch_engaged(self) -> bool:
        """Is the emergency stop on?

        Read from disk on EVERY call and never cached. Caching would mean
        flipping the switch has no effect until something expires, which defeats
        the point of an emergency control. One stat() call, microseconds.
        """
        path = Path(get_settings().kill_switch_path)
        engaged = path.exists()

        if engaged != self._kill_switch_last_seen:
            # The transition is the alarming event and the one worth paging on.
            logger.critical(
                "killswitch.engaged" if engaged else "killswitch.released",
                extra=kv(path=str(path)),
            )
            self._kill_switch_last_seen = engaged
        elif engaged:
            # Steady-state blocking: noteworthy, but logging every one at
            # CRITICAL would bury the moment it was engaged.
            logger.warning("killswitch.blocked", extra=kv(path=str(path)))

        return engaged

    @staticmethod
    def _build_audit() -> AuditLog:
        """The decision record. Persistent when configured, in memory when not.

        TMP-01: a local file is a stopgap. A file inside a container is lost on
        every deploy, so this becomes a Postgres sink once we have database
        access. See docs/PROVISIONAL_DECISIONS.md.
        """
        settings = get_settings()

        if settings.audit_log_path and settings.audit_hmac_key:
            sink = FileAuditSink(
                Path(settings.audit_log_path),
                settings.audit_hmac_key.encode("utf-8"),
            )
            logger.info(
                "governance.audit_persistent",
                extra=kv(path=settings.audit_log_path, signed=True),
            )
            return AuditLog(sink=sink)

        # Loud on purpose. An audit trail nobody configured is not an audit
        # trail, and this is the only moment anyone would notice.
        logger.warning(
            "governance.audit_in_memory",
            extra=kv(
                note="decisions are NOT persisted and are lost on restart",
                fix="set AUDIT_LOG_PATH and AUDIT_HMAC_KEY",
            ),
        )
        return AuditLog()

    def _record(self, tool: str, arguments: dict | None, agent_id: str, decision) -> None:
        """Write the decision to the audit trail.

        TMP-02: never raises. Today every action is read-only, so losing the
        record of a price lookup is not a compliance problem. Once
        create_strategy and activate_strategy exist, those two must refuse to
        proceed when they cannot be recorded.
        """
        arguments_hash = _hash_arguments(arguments)
        try:
            self.audit.log(
                event_type="policy_evaluation",
                agent_did=agent_id,
                action=tool,
                outcome="allow" if decision.allowed else "deny",
                policy_decision=decision.action,
                policy_version=self.policy_name,
                trace_id=current().get("request_id"),
                arguments_hash=arguments_hash,
                # FileAuditSink serialises a SUBSET of the entry: top-level
                # `arguments_hash`, `matched_rule` and `session_id` are all
                # dropped on the way to disk, while `data` survives intact.
                # Anything that must exist in the persisted record goes here,
                # even where it duplicates a field above.
                data={
                    "rule": decision.matched_rule or "default",
                    "reason": decision.reason or "",
                    "session_id": current().get("session_id"),
                    "arguments_hash": arguments_hash,
                },
            )
        except Exception as exc:
            logger.error("governance.audit_write_failed", extra=kv(tool=tool, error=str(exc)))

    def _record_halt(self, tool: str, arguments: dict | None, agent_id: str) -> None:
        """A halted call is a governance decision, so it belongs in the record.

        Without this the audit trail would show a gap during an incident -
        exactly the window someone will later ask about.
        """
        arguments_hash = _hash_arguments(arguments)
        try:
            self.audit.log(
                event_type="kill_switch",
                agent_did=agent_id,
                action=tool,
                outcome="deny",
                policy_decision="halted",
                policy_version=self.policy_name,
                trace_id=current().get("request_id"),
                arguments_hash=arguments_hash,
                data={
                    "rule": "kill_switch",
                    "reason": "emergency stop engaged",
                    "session_id": current().get("session_id"),
                    "arguments_hash": arguments_hash,
                },
            )
        except Exception as exc:
            logger.error("governance.audit_write_failed", extra=kv(tool=tool, error=str(exc)))

    def check(self, tool: str, arguments: dict | None, agent_id: str) -> None:
        """Raise PolicyDeniedError unless the policy permits this call.

        Args:
            tool: MCP tool name, e.g. "vow.activate_strategy".
            arguments: The tool's arguments. Their keys become policy fields,
                so a rule can read `action.total_budget`.
            agent_id: The advertiser this call is scoped to. Lets a policy
                differ per tenant.
        """
        # The emergency stop is checked FIRST, before the policy. Reverse the
        # order and a call the policy happens to permit would slip through while
        # the agent is supposed to be halted.
        if self._kill_switch_engaged():
            self._record_halt(tool, arguments, agent_id)
            raise KillSwitchEngagedError("VOW access is halted by the kill switch.")

        # `type` is written last so an argument called "type" cannot masquerade
        # as the tool name. Arguments can originate from an LLM; the tool name
        # never does.
        action = {**(arguments or {}), "type": tool}

        try:
            decision = self._engine.evaluate(agent_id, {"action": action})
        except Exception as exc:
            # An engine that cannot decide must not be read as consent.
            logger.error("governance.evaluation_failed", extra=kv(tool=tool, error=str(exc)))
            raise PolicyDeniedError(
                f"Policy engine failed evaluating {tool!r}; refusing.", tool=tool
            ) from exc

        # Recorded before acting on the outcome, so an allow and a deny are
        # equally evidenced. An audit trail with only the refusals in it cannot
        # answer "who authorised this?".
        self._record(tool, arguments, agent_id, decision)

        if decision.allowed:
            logger.debug("governance.allowed", extra=kv(tool=tool, rule=decision.matched_rule))
            return

        # A denial is the system working, so WARNING rather than ERROR - but it
        # is always recorded, with the rule that decided it.
        logger.warning(
            "governance.denied",
            extra=kv(
                tool=tool,
                rule=decision.matched_rule or "default",
                reason=decision.reason or "",
                advertiser=agent_id,
            ),
        )
        raise PolicyDeniedError(
            f"Policy refused {tool!r}: {decision.reason or 'no rule permits this action'}",
            tool=tool,
            rule=decision.matched_rule,
        )


@lru_cache
def get_guard() -> PolicyGuard:
    """The process-wide guard. Cached so the policy parses once."""
    settings = get_settings()
    path = (
        Path(settings.governance_policy_path)
        if settings.governance_policy_path
        else DEFAULT_POLICY_PATH
    )
    return PolicyGuard(path)
