"""The audit trail: the durable record of every allow/deny decision.

Distinct from logging. Logs are for debugging and expire; this is evidence, and
must answer "who authorised this, and on what basis?" years later.

The tests read the file on disk rather than the in-memory entries, because the
two are *different shapes* - `FileAuditSink` serialises a subset. Asserting on
the in-memory object would have passed while the persisted record was missing
half its fields, which is exactly the bug found by hand before these existed.
"""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.core.context import bind
from app.core.exceptions import PolicyDeniedError
from app.governance.agt import DEFAULT_POLICY_PATH, PolicyGuard
from app.tools.mcp import VowTools

ADVERTISER = "adv-123"
ACTIVATE_STRATEGY = "vow.activate_strategy"


@pytest.fixture
def audit_path(tmp_path, monkeypatch) -> Path:
    """Configure a signed, file-backed audit trail and return its path."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
    monkeypatch.setenv("AUDIT_HMAC_KEY", "test-key-not-a-secret")
    get_settings.cache_clear()
    return path


def _entries(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _deny_an_activation(guard: PolicyGuard, budget: int = 500_000) -> None:
    with pytest.raises(PolicyDeniedError):
        guard.check(
            ACTIVATE_STRATEGY,
            {"approval_status": "APPROVED", "total_budget": budget},
            agent_id=ADVERTISER,
        )


# --- both outcomes are recorded ---------------------------------------------


def test_an_allowed_decision_is_recorded(audit_path):
    """Easy to record only refusals - and then the trail cannot answer
    "who authorised this?", which is the question actually asked."""
    PolicyGuard(DEFAULT_POLICY_PATH).check(
        VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER
    )

    entry = _entries(audit_path)[0]
    assert entry["outcome"] == "allow"
    assert entry["action"] == VowTools.LIST_DEALS
    assert entry["agent_did"] == ADVERTISER
    assert entry["data"]["rule"] == "allow-planning-tools"


def test_a_refused_decision_is_recorded(audit_path):
    _deny_an_activation(PolicyGuard(DEFAULT_POLICY_PATH))

    entry = _entries(audit_path)[0]
    assert entry["outcome"] == "deny"
    assert entry["action"] == ACTIVATE_STRATEGY


# --- what the record does and does not contain ------------------------------


def test_the_argument_fingerprint_reaches_the_file(audit_path):
    """Regression. The hash was set on the entry and dropped in serialisation,
    because `FileAuditSink` writes only a subset of the fields. Anything that
    must persist has to live in `data`, even where that duplicates a field.
    """
    PolicyGuard(DEFAULT_POLICY_PATH).check(
        VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER
    )

    fingerprint = _entries(audit_path)[0]["data"]["arguments_hash"]
    assert len(fingerprint) == 64, "expected a SHA-256 hex digest"


def test_raw_argument_values_never_reach_the_file(audit_path):
    """A record retained for years must not hold a client's budgets.

    The fingerprint still settles a dispute: hash the claimed figure and
    compare. Proof without retention.
    """
    _deny_an_activation(PolicyGuard(DEFAULT_POLICY_PATH), budget=987_654)

    assert "987654" not in audit_path.read_text(encoding="utf-8")


def test_correlation_ids_are_recorded(audit_path):
    """So a support question - "it refused me at 3pm" - reaches the decision."""
    bind(request_id="req-1", session_id="sess-1")
    PolicyGuard(DEFAULT_POLICY_PATH).check(
        VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER
    )

    entry = _entries(audit_path)[0]
    assert entry["trace_id"] == "req-1"
    assert entry["data"]["session_id"] == "sess-1"


# --- tamper evidence --------------------------------------------------------


def test_entries_are_chained(audit_path):
    """Each record carries the hash of the one before, so deleting or editing a
    record breaks the chain visibly. This is the property a log file cannot
    provide, and the reason this is a separate mechanism.
    """
    guard = PolicyGuard(DEFAULT_POLICY_PATH)
    guard.check(VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER)
    guard.check(VowTools.CTV_RATE_CARD, {"market": "GB"}, agent_id=ADVERTISER)

    first, second = _entries(audit_path)
    assert first["previous_hash"] == "", "the first entry has nothing before it"
    assert second["previous_hash"], "the second entry must link to the first"
    assert first["signature"] and second["signature"], "entries must be signed"


# --- degraded modes ---------------------------------------------------------


def test_an_audit_write_failure_does_not_break_the_call():
    """TMP-02. Today every action is read-only, so losing the record of a price
    lookup must not take the agent down.

    Revisit when create_strategy and activate_strategy exist: for those two,
    no record should mean no action.
    """

    class ExplodingAudit:
        def log(self, **_kwargs):
            raise OSError("disk full")

    guard = PolicyGuard(DEFAULT_POLICY_PATH)
    guard.audit = ExplodingAudit()

    # Must not raise.
    guard.check(VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER)


def test_audit_falls_back_to_memory_when_unconfigured(monkeypatch):
    """Without a path and key, decisions are held in memory and lost on
    restart. Legitimate for tests, useless for compliance - the service warns
    loudly at startup, and TMP-01 tracks moving this to Postgres.
    """
    monkeypatch.delenv("AUDIT_LOG_PATH", raising=False)
    monkeypatch.delenv("AUDIT_HMAC_KEY", raising=False)
    get_settings.cache_clear()

    guard = PolicyGuard(DEFAULT_POLICY_PATH)
    guard.check(VowTools.LIST_DEALS, {"market": "GB"}, agent_id=ADVERTISER)

    assert guard.audit.query(limit=5), "the decision should still be recorded in memory"
