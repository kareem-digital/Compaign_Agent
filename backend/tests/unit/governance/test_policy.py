"""The CTV policy rules, and the traps that must not be reintroduced.

Two kinds of test here. Most check that a rule does what it says. A few check
the *shape* of the policy file, because two of its properties fail silently
rather than loudly: a deny-list rule permits everything it was written to
forbid, and `default_action: allow` turns every gap into a hole. Neither shows
up as an error, so only a test catches them.
"""

import pytest

from app.core.exceptions import ConfigurationError, PolicyDeniedError
from app.governance.agt import DEFAULT_POLICY_PATH, PolicyGuard
from app.tools.mcp import VowTools

ADVERTISER = "adv-123"

# Literal strings, not VowTools constants: these two tools are not implemented
# and deliberately absent from VowTools (TMP-15). The policy guards them
# regardless, so the guardrail exists before the action does.
CREATE_STRATEGY = "vow.create_strategy"
ACTIVATE_STRATEGY = "vow.activate_strategy"

# The cap and market list in the shipped policy. Placeholders pending A3
# (TMP-03) - update both together.
CAP = 100_000

APPROVED_CREATE = {
    "approval_status": "APPROVED",
    "market": "GB",
    "inventory_tier": "AMAZON_OWNED",
}


@pytest.fixture
def guard() -> PolicyGuard:
    """A guard on the real shipped policy, not a fixture policy.

    Testing the actual file is the point: a test that invents its own policy
    proves the engine works and tells you nothing about what we ship.
    """
    return PolicyGuard(DEFAULT_POLICY_PATH)


def allowed(guard: PolicyGuard, tool: str, **arguments) -> bool:
    try:
        guard.check(tool, arguments, agent_id=ADVERTISER)
        return True
    except PolicyDeniedError:
        return False


# --- planning: costless, and must keep working ------------------------------


@pytest.mark.parametrize("tool", VowTools.all())
def test_planning_tools_are_allowed(guard, tool):
    """Every read tool the agent knows how to call must be permitted.

    Parametrized over `VowTools.all()` rather than a list restated here, because
    the failure this catches is a name appearing in one place and not the other.
    Rename a constant, or add one, without editing the policy and the tool
    silently stops being permitted - the agent breaks for a reason nobody would
    guess, since `default_action: deny` gives no hint that a rule is out of date.

    That is not hypothetical: the grounded registry's seven reference-data reads
    were added to `VowTools` in one lane while the policy was written in another,
    and every registry sync was refused until the allow-list caught up. A list
    written out by hand here would have passed throughout.

    `VowTools` holds only reads, so this asserting "all of them" cannot become an
    assertion that spend is permitted. `create_strategy` and `activate_strategy`
    are absent from it on purpose and are covered by their own tests below.
    """
    assert allowed(guard, tool, market="GB")


def test_an_unknown_tool_is_refused(guard):
    """`default_action: deny` means a tool nobody allow-listed cannot be called,
    including one added later by mistake."""
    assert not allowed(guard, "vow.delete_everything")


# --- creating a strategy ----------------------------------------------------


def test_create_is_allowed_when_every_condition_holds(guard):
    assert allowed(guard, CREATE_STRATEGY, **APPROVED_CREATE)


def test_create_is_refused_without_human_approval(guard):
    assert not allowed(guard, CREATE_STRATEGY, **{**APPROVED_CREATE, "approval_status": "PENDING"})


def test_create_is_refused_for_a_market_not_on_the_list(guard):
    assert not allowed(guard, CREATE_STRATEGY, **{**APPROVED_CREATE, "market": "JP"})


def test_create_is_refused_for_an_unrecognised_inventory_tier(guard):
    assert not allowed(guard, CREATE_STRATEGY, **{**APPROVED_CREATE, "inventory_tier": "MADE_UP"})


def test_create_is_refused_when_the_market_is_absent(guard):
    """Fail closed on missing data, not just on wrong data."""
    args = {k: v for k, v in APPROVED_CREATE.items() if k != "market"}
    assert not allowed(guard, CREATE_STRATEGY, **args)


# --- activating: the only action that spends --------------------------------


def test_activate_is_allowed_under_the_cap(guard):
    assert allowed(guard, ACTIVATE_STRATEGY, approval_status="APPROVED", total_budget=50_000)


def test_activate_is_allowed_exactly_at_the_cap(guard):
    """Boundaries are where off-by-one errors live. The cap is inclusive."""
    assert allowed(guard, ACTIVATE_STRATEGY, approval_status="APPROVED", total_budget=CAP)


def test_activate_is_refused_one_pound_over_the_cap(guard):
    assert not allowed(guard, ACTIVATE_STRATEGY, approval_status="APPROVED", total_budget=CAP + 1)


def test_activate_is_refused_when_the_budget_is_absent(guard):
    """The case we got wrong first time.

    A missing field makes a condition evaluate false rather than raise. Under a
    deny-list rule ("refuse if budget > cap") that means an activation carrying
    no budget at all sails past the cap. Under an allow-list rule, nothing
    permits it and it is refused. This test is why the policy is allow-listed.
    """
    assert not allowed(guard, ACTIVATE_STRATEGY, approval_status="APPROVED")


def test_activate_is_refused_without_approval(guard):
    assert not allowed(guard, ACTIVATE_STRATEGY, approval_status="PENDING", total_budget=10)


# --- the traps --------------------------------------------------------------


def _policy_rules_only() -> str:
    """The policy file with comment lines stripped.

    The file's own header discusses `not in` at length, so the structural
    checks below must read the rules rather than the prose.
    """
    text = DEFAULT_POLICY_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def test_the_policy_never_uses_the_not_in_operator():
    """`not in` does not raise in AGT 4.1.0 - it silently never matches.

    So a rule reading `market not in ['GB', 'US']` permits *every* market,
    permanently, with no error and no log line. `not (x in [...])` fails the
    same way. Verified working operators: == != > in and.

    This is the most valuable test in the file: the failure it prevents is
    invisible in review, in the logs, and at runtime.
    """
    rules = _policy_rules_only()
    assert "not in" not in rules, "deny-lists silently permit everything - use an allow-list"
    assert "not (" not in rules, "negated membership fails the same way as `not in`"


def test_the_policy_defaults_to_deny():
    """Flip this to `allow` and every gap in the rules becomes a hole."""
    assert "default_action: deny" in _policy_rules_only()


def test_an_argument_cannot_impersonate_the_tool_name(guard):
    """Arguments can originate from an LLM; the tool name cannot.

    If an argument called `type` could override it, a model could disguise a
    half-million-pound activation as a harmless deals lookup.
    """
    assert not allowed(
        guard,
        ACTIVATE_STRATEGY,
        type=VowTools.LIST_DEALS,
        approval_status="APPROVED",
        total_budget=999_999,
    )


# --- failing closed at startup ---------------------------------------------


def test_a_malformed_policy_refuses_to_load(tmp_path):
    """A service that boots with a broken policy and permits everything is
    worse than one that will not boot."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("this: is: not: valid: yaml: [", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        PolicyGuard(bad)


def test_a_missing_policy_refuses_to_load(tmp_path):
    with pytest.raises(ConfigurationError):
        PolicyGuard(tmp_path / "does-not-exist.yaml")
