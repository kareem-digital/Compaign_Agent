"""The emergency stop.

One rule: while the switch is on, nothing reaches VOW. Not "most things" and not
"the expensive things" - a kill switch with exceptions is one somebody has to
reason about during an incident.

The switch is a FILE, and its presence is the signal:

    touch KILL_SWITCH   -> halted
    rm KILL_SWITCH      -> running

Presence rather than contents, so it cannot be ambiguously half-enabled.
"""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.core.exceptions import KillSwitchEngagedError, PolicyDeniedError
from app.governance.agt import DEFAULT_POLICY_PATH, PolicyGuard
from app.tools.mcp import VowTools

ADVERTISER = "adv-123"
ACTIVATE_STRATEGY = "vow.activate_strategy"


@pytest.fixture
def switch(tmp_path, monkeypatch) -> Path:
    """Point the guard at a switch file that does not exist yet."""
    path = tmp_path / "KILL_SWITCH"
    monkeypatch.setenv("KILL_SWITCH_PATH", str(path))
    get_settings.cache_clear()
    return path


@pytest.fixture
def guard(switch) -> PolicyGuard:
    return PolicyGuard(DEFAULT_POLICY_PATH)


def _call(guard: PolicyGuard, tool: str = VowTools.LIST_DEALS) -> None:
    guard.check(tool, {"market": "GB"}, agent_id=ADVERTISER)


# --- the basic behaviour ----------------------------------------------------


def test_calls_work_when_the_switch_is_absent(guard):
    """Absence of the file is the normal state. No file, no interference."""
    _call(guard)


def test_every_call_is_halted_when_the_switch_is_present(guard, switch):
    switch.touch()

    with pytest.raises(KillSwitchEngagedError):
        _call(guard)


def test_the_switch_halts_calls_the_policy_would_have_allowed(guard, switch):
    """Proves the switch is checked BEFORE the policy.

    Reverse the order and a permitted call would slip through while the agent is
    supposed to be stopped - the one failure that would make the switch a lie.
    """
    _call(guard)  # allowed while off, so the policy is not the thing refusing
    switch.touch()

    with pytest.raises(KillSwitchEngagedError):
        _call(guard)


def test_the_switch_halts_planning_too(guard, switch):
    """Deliberately not selective. If the agent cannot read from VOW it cannot
    plan anyway, so sparing the read-only tools spares nothing."""
    switch.touch()

    for tool in (
        VowTools.LIST_DEALS,
        VowTools.CTV_RATE_CARD,
        VowTools.SUGGEST_AUDIENCES,
        VowTools.REACH_FORECAST,
    ):
        with pytest.raises(KillSwitchEngagedError):
            guard.check(tool, {"market": "GB"}, agent_id=ADVERTISER)


# --- it must take effect immediately ---------------------------------------


def test_flipping_the_switch_takes_effect_without_a_restart(guard, switch):
    """The whole point. The state is read on every call and never cached - a
    cached answer would mean the switch does nothing until something expires.
    """
    _call(guard)  # running

    switch.touch()
    with pytest.raises(KillSwitchEngagedError):
        _call(guard)  # halted, same guard instance

    switch.unlink()
    _call(guard)  # running again, still the same instance


def test_a_halt_is_not_a_policy_refusal(guard, switch):
    """Different types, because they mean different things and map to different
    status codes: 503 "not right now" versus 403 "never"."""
    switch.touch()

    with pytest.raises(KillSwitchEngagedError):
        _call(guard)

    assert not issubclass(KillSwitchEngagedError, PolicyDeniedError)


# --- the incident window must be evidenced ---------------------------------


def test_a_halted_call_is_recorded_in_the_audit_trail(tmp_path, monkeypatch):
    """Without this the audit trail shows a gap during an incident - exactly the
    window someone will later ask about."""
    switch = tmp_path / "KILL_SWITCH"
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("KILL_SWITCH_PATH", str(switch))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit))
    monkeypatch.setenv("AUDIT_HMAC_KEY", "test-key-not-a-secret")
    get_settings.cache_clear()

    guard = PolicyGuard(DEFAULT_POLICY_PATH)
    switch.touch()

    with pytest.raises(KillSwitchEngagedError):
        guard.check(ACTIVATE_STRATEGY, {"total_budget": 500_000}, agent_id=ADVERTISER)

    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert entry["event_type"] == "kill_switch"
    assert entry["outcome"] == "deny"
    assert entry["data"]["rule"] == "kill_switch"
    assert entry["action"] == ACTIVATE_STRATEGY
    assert "500000" not in audit.read_text(encoding="utf-8"), "raw values must not persist"
