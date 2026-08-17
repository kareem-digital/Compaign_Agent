"""Is what the trader said something VOW actually sells?

**Found on the UI.** A trader typed "I want to plan to run a campaign in the China" and got:

    - Markets: CN
    ...
    Before I can carry on I need the start and end dates, the creative durations
    and the budget.

CN accepted, and three more questions asked under a premise that was already false. Whatever
the trader answered next, the plan could never be activated - and they would have found out at
approval, several turns of work later.

The registry had the answer the whole time. `validate_target_markets(["CN"])` returns *"I
cannot plan for CN - VOW does not sell CTV inventory there"* plus the markets it does sell,
read off the snapshot. Nothing called it.

**What was deliberately not built.** The KNW-02 lane solves this with a `validate_basics` node
plus seven helpers in `gates` and five new state fields. Almost none of that is needed here:
`awaiting` already carries a computed sentence verbatim, so a validation error *is* an
`awaiting` entry. No new node, no graph edge, and one new state field rather than five -
`rejected_fields`, which the interface needs to offer valid values instead of an empty input.
Value-rejection also stays in one place rather than two.
"""

from __future__ import annotations

import pytest

from app.agent.gates import BASICS
from app.agent.nodes.validate_basics import make_validate_basics
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp.mock import MockMCPClient

LABELS = [label for _key, label in BASICS]
MARKET_LABEL, FLIGHT_LABEL, DURATIONS_LABEL, BUDGET_LABEL = LABELS


async def _grounding(registry: AdvertiserRegistry, state: dict):
    node = make_validate_basics(registry)
    res = await node(state)
    errors = res.get("validation_errors") or []
    blocking_msgs = [
        e.get("message", "")
        for e in errors
        if not e.get("is_valid") and e.get("severity") == "error"
    ]
    warning_msgs = [
        e.get("message", "")
        for e in errors
        if e.get("is_valid") or e.get("severity") == "warning"
    ]
    return blocking_msgs, warning_msgs, []


@pytest.fixture
def registry() -> AdvertiserRegistry:
    return AdvertiserRegistry(advertiser_id="adv-grounding", mcp=MockMCPClient("adv-grounding"))


def _fields(**extra) -> dict:
    return {
        "markets": ["GB"],
        "durations": ["30"],
        "primary_currency": "GBP",
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "market_budgets": [{"market": "GB", "budget": "15000.00"}],
        "preferred_providers": [],
        **extra,
    }


@pytest.fixture(autouse=True)
def _no_llm_in_unit_tests(monkeypatch):
    monkeypatch.setattr("app.agent.llm.get_llm", lambda: None)


def _turn(text: str, **state) -> dict:
    return {"messages": [{"role": "user", "content": text}], **state}


# --- a market VOW does not sell -----------------------------------------------


async def test_an_unsold_market_is_refused(registry):
    """The case from the bug report."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(markets=["CN"]))

    assert blocking, "CN was accepted"
    assert "CN" in blocking[0]
    assert "does not sell" in blocking[0]


async def test_the_refusal_names_what_can_be_planned_instead(registry):
    """`suggested_options` comes off the snapshot, so the alternatives offered are the markets
    the platform sells today rather than a list written into our code."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(markets=["CN"]))

    for market in ("GB", "US", "DE", "FR"):
        assert market in blocking[0], blocking[0]


async def test_a_sold_market_grounds_silently(registry):
    blocking, notes, _rejected = await _grounding(registry, _fields())

    assert blocking == []
    assert notes == []


# --- the other step-1 values --------------------------------------------------


async def test_a_finished_flight_is_refused(registry):
    """This rule was already written - `check_flight_dates` returns `flight_dates.in_past` -
    and had no caller. The hand-rolled version this replaced also missed two cases the
    registry covers: inverted dates and unparseable ones."""
    blocking, _notes, _rejected = await _grounding(
        registry, _fields(flight_dates={"lower": "2023-10-01", "upper": "2023-10-31"})
    )

    assert blocking and "already passed" in blocking[0]


async def test_an_inverted_flight_is_refused(registry):
    """The end before the start. Free with the registry; the hand-rolled check had no idea."""
    blocking, _notes, _rejected = await _grounding(
        registry, _fields(flight_dates={"lower": "2030-10-31", "upper": "2030-10-01"})
    )

    assert blocking and "not after" in blocking[0]


async def test_a_duration_the_platform_does_not_sell_is_refused(registry):
    """**And this is the second silent drop that went with it.** `_merge` filtered durations
    against a hard-coded `("10","15","20","30")`, so a trader asking for 45s had it removed
    without a word and carried on believing it was in the plan. The list now comes from the
    snapshot, and an unsellable length is said out loud."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(durations=["45"]))

    assert blocking, "45s was dropped silently"
    assert "45" in blocking[0]


async def test_a_currency_that_does_not_match_the_market_is_only_a_note(registry):
    """A GBP budget on a US plan is legal and almost always a slip, so it is said rather than
    blocked. Blocking would stop a plan that can genuinely run."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(markets=["US"], primary_currency="GBP"))

    assert blocking == []


# --- absence is the gate's business, not ours ---------------------------------


@pytest.mark.parametrize(
    "missing", [{"flight_dates": None}, {"durations": []}, {"primary_currency": None}]
)
async def test_a_value_not_yet_given_is_not_a_rejection(registry, missing):
    """`missing_basics` already asks for a blank field, and two questions about one blank is
    the stutter the gate exists to prevent."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(**missing))

    assert blocking == []


async def test_no_market_yet_is_not_a_rejection(registry):
    """The very first turn has nothing to ground. `market.missing` is skipped because
    `missing_basics` phrases that question better."""
    blocking, _notes, _rejected = await _grounding(registry, _fields(markets=[]))

    assert blocking == []


# --- and through the node -----------------------------------------------------


async def test_a_rejection_replaces_the_gaps_rather_than_heading_them(registry):
    """**The whole point.** Fixing the market is the only useful next move, so it is the ONLY
    thing asked. Listing it first and then asking for dates, durations and budget as well would
    still be collecting three answers that cannot be used - which is the bug, one line further
    down the message."""
    node = make_extract_fields(registry)

    out = await node(_turn("I want to plan to run a campaign in China"))

    assert len(out["awaiting"]) == 1, out["awaiting"]
    assert "CN" in out["awaiting"][0]
    for label in (FLIGHT_LABEL, DURATIONS_LABEL, BUDGET_LABEL):
        assert label not in out["awaiting"]


async def test_the_rejected_field_is_named_for_the_interface(registry):
    """`awaiting` carries the sentence; this carries the field, so the UI can offer the markets
    that would work instead of a date picker for a market it cannot buy."""
    node = make_extract_fields(registry)

    out = await node(_turn("I want to plan to run a campaign in China"))

    assert out["rejected_fields"] == ["markets"]


async def test_nothing_rejected_leaves_the_field_empty(registry):
    """Written every turn, not only when there is something - left over from a previous turn it
    would go on hiding the inputs after the market was corrected."""
    node = make_extract_fields(registry)

    out = await node(_turn("15000 GBP in the UK, 30 seconds, October 2030"))

    assert out["rejected_fields"] == []


async def test_a_normalization_rides_along_with_the_confirmation(registry):
    """"I read UK as GB" is worth saying and not worth stopping for. It goes into the message,
    never into `awaiting`, because `awaiting` blocks the turn."""
    node = make_extract_fields(registry)

    out = await node(_turn("15000 GBP in the UK, 30 seconds, October 2030"))

    assert out["awaiting"] == [] or all("GB" not in a for a in out["awaiting"])


async def test_a_clean_brief_is_not_blocked(registry):
    """The other side of every check above: grounding must not stand in the way of a plan that
    can actually run."""
    node = make_extract_fields(registry)

    out = await node(_turn("15000 GBP in the UK, 30 seconds, October 2030"))

    assert out["awaiting"] == [], out["awaiting"]
    assert out["markets"] == ["GB"]
