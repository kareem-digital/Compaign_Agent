"""The gate mechanism: what counts as answered, what blocks, and what gets asked.

These are the pure functions behind two behaviours the graph tests exercise end to
end but cannot pin precisely: that a stage's validation outcomes are *replaced*
rather than accumulated, and that one question is chosen from two possible sources
in a defined order.

Unit rather than component, per tests/unit/__init__.py: no graph, no MCP, no
snapshot - `gates` asks nothing of any of them.
"""

import pytest

from app.agent.gates import (
    BASICS,
    NO_AUDIENCE_CHOICE,
    NO_INVENTORY,
    blocking,
    missing_basics,
    next_question,
    record,
    record_checks,
    route_after_audiences,
    route_after_basics,
    route_after_inventory,
    route_after_validation,
    say,
    stage_notes,
)
from app.knowledge.registry.models import ValidationResponse

ANSWERED = {
    "markets": ["GB"],
    "flight_start": "2099-08-01",
    "flight_end": "2099-08-31",
    "durations": ["30"],
    "budget_amount": "50000.00",
}


def _blocker(code: str = "market.unknown", **extra) -> ValidationResponse:
    return ValidationResponse(is_valid=False, message=f"{code} failed", code=code, **extra)


def _warning(code: str = "market.normalized", **extra) -> ValidationResponse:
    return ValidationResponse(
        is_valid=True, severity="warning", message=f"{code} noted", code=code, **extra
    )


def _pass(code: str = "market.ok") -> ValidationResponse:
    return ValidationResponse(is_valid=True, message="fine", code=code)


# --- what counts as answered --------------------------------------------------


def test_a_complete_state_is_missing_nothing() -> None:
    assert missing_basics(ANSWERED) == []


def test_missing_basics_reports_in_declaration_order() -> None:
    """Order is the order questions are asked in, so it is part of the contract."""
    assert missing_basics({}) == [label for _, label in BASICS]


def test_a_flight_needs_both_ends_to_count_as_answered() -> None:
    """The reason `BASICS` entries name several keys.

    A truthiness check on a single `flight_dates` dict would have called
    `{"lower": ..., "upper": None}` answered, and a truthiness check on the
    derived field calls a held half-answer missing. Neither is right.
    """
    half = {**ANSWERED, "flight_end": None}

    assert missing_basics(half) == ["the start and end dates"]


def test_a_budget_without_a_market_still_counts_as_answered() -> None:
    """The bug this exists to prevent: `market_budgets` cannot be keyed without a
    market, so checking it re-asked for a budget the trader had given."""
    state = {"budget_amount": "50000.00", "market_budgets": []}

    assert "the budget" not in missing_basics(state)


# --- recording, not accumulating ----------------------------------------------


def test_record_keeps_what_is_worth_saying_and_drops_passes() -> None:
    recorded = record({}, "validation", [_pass(), _warning(), _blocker()])

    assert [entry["code"] for entry in recorded] == ["market.normalized", "market.unknown"]
    assert {entry["stage"] for entry in recorded} == {"validation"}


def test_record_replaces_only_its_own_stage() -> None:
    existing = record({}, "forecast", [_warning("forecast.below_viability_floor")])

    merged = record({"validation_errors": existing}, "validation", [_blocker()])

    assert [entry["code"] for entry in merged] == [
        "forecast.below_viability_floor",
        "market.unknown",
    ]


def test_a_resolved_error_leaves_nothing_behind() -> None:
    """No clear path exists, and that is the design - the stage simply stops
    re-emitting. Appending is what used to keep a corrected value's error forever."""
    blocked = record({}, "validation", [_blocker()])

    resolved = record({"validation_errors": blocked}, "validation", [_pass()])

    assert resolved == []


def test_repeating_an_unchanged_failure_does_not_grow_the_list() -> None:
    state: dict = {}
    for _ in range(3):
        state = {"validation_errors": record(state, "validation", [_blocker()])}

    assert len(state["validation_errors"]) == 1


# --- and the sibling that keeps the passes ------------------------------------


def test_record_checks_keeps_the_passes_record_drops() -> None:
    """The whole reason it exists.

    `validate_basics._checks` skips a rule whose input is absent, so a pass is the
    only evidence that a rule ran at all. On a clean brief `record` keeps nothing,
    which leaves a UI unable to tell "checked and fine" from "never checked".
    """
    responses = [_pass(), _warning(), _blocker()]

    assert [entry["code"] for entry in record({}, "validation", responses)] == [
        "market.normalized",
        "market.unknown",
    ]
    assert [entry["code"] for entry in record_checks({}, "validation", responses)] == [
        "market.ok",
        "market.normalized",
        "market.unknown",
    ]


def test_record_checks_replaces_only_its_own_stage() -> None:
    existing = record_checks({}, "forecast", [_pass("forecast.ok")])

    merged = record_checks({"validation_checks": existing}, "validation", [_pass()])

    assert [entry["code"] for entry in merged] == ["forecast.ok", "market.ok"]


def test_record_checks_does_not_grow_across_turns() -> None:
    """Same replace-per-stage rule as `record`, so the checkpoint stays bounded."""
    state: dict = {}
    for _ in range(3):
        state = {"validation_checks": record_checks(state, "validation", [_pass(), _blocker()])}

    assert len(state["validation_checks"]) == 2


def test_record_checks_reads_its_own_key() -> None:
    """The copy-paste bug a sibling function is most likely to ship with."""
    errors = record({}, "forecast", [_blocker("forecast.fabricated_reach")])

    assert record_checks({"validation_errors": errors}, "validation", [_pass()]) == [
        {**_pass().model_dump(mode="json"), "stage": "validation"}
    ]


@pytest.mark.parametrize(
    "responses",
    [
        [_pass()],
        [_warning()],
        [_blocker()],
        [_pass(), _warning(), _blocker()],
        [],
    ],
)
def test_errors_are_always_a_subset_of_checks(responses: list[ValidationResponse]) -> None:
    """The one way two functions over one list drift.

    `build_validation_details` reports `blocks` from `validation_errors` - what the
    routers acted on - while showing `validation_checks`. That is only honest while
    the second contains the first.
    """
    errors = record({}, "validation", responses)
    checks = record_checks({}, "validation", responses)

    assert all(entry in checks for entry in errors)


# --- blocking agrees with the model it mirrors --------------------------------


@pytest.mark.parametrize(
    "response",
    [
        _blocker(),
        _warning(),
        _pass(),
        ValidationResponse(is_valid=False, severity="warning", message="soft", code="soft"),
    ],
)
def test_blocking_matches_validation_response_blocks(response: ValidationResponse) -> None:
    """`blocking` reads dicts because state is JSON; `.blocks` reads the model.

    Two implementations of one rule, so they are asserted equal rather than
    assumed - the same reason `test_registry_contract.py` exists.
    """
    recorded = record({}, "validation", [response])

    assert bool(blocking({"validation_errors": recorded})) == response.blocks


def test_stage_notes_says_warnings_and_never_blockers() -> None:
    """A blocker is `ask`'s to phrase, with its options. Saying it here too would
    state the problem twice in one reply."""
    recorded = record({}, "validation", [_warning(), _blocker()])

    spoken = stage_notes("validation", recorded)

    assert "market.normalized noted" in spoken
    assert "market.unknown failed" not in spoken


# --- not saying the same thing twice ------------------------------------------
#
# The graph re-runs every stage every turn, so without this a complete brief
# restates its whole block whatever the trader typed - a byte-identical reply four
# turns running, with no way to reach a finished plan.


def _content(fragment: dict) -> str | None:
    messages = fragment.get("messages") or []
    return messages[0]["content"] if messages else None


def test_a_new_message_is_said() -> None:
    fragment = say({}, "inventory", "four deals in GB")

    assert _content(fragment) == "four deals in GB"
    assert fragment["last_said"]["inventory"]


def test_the_same_message_twice_is_said_once() -> None:
    first = say({}, "inventory", "four deals in GB")
    second = say({"last_said": first["last_said"]}, "inventory", "four deals in GB")

    assert _content(second) is None


def test_a_changed_message_is_said_again() -> None:
    first = say({}, "inventory", "four deals in GB")
    second = say({"last_said": first["last_said"]}, "inventory", "two deals in FR")

    assert _content(second) == "two deals in FR"


def test_stages_do_not_silence_each_other() -> None:
    """Per-stage keys, merged by hand - nodes run in sequence and each sees the
    previous one's write, so one stage speaking must not clear another's record."""
    first = say({}, "validation", "using USD for a GB campaign")
    second = say({"last_said": first["last_said"]}, "inventory", "four deals in GB")

    assert set(second["last_said"]) == {"validation", "inventory"}


def test_an_asking_stage_repeats_itself() -> None:
    """A question the trader has not answered has to stay live, and a stage that
    falls silent at END would leave the turn with no reply at all."""
    first = say({}, "audiences", "pick one of three", asking=True)
    second = say({"last_said": first["last_said"]}, "audiences", "pick one of three", asking=True)

    assert _content(second) == "pick one of three"


def test_an_asking_stage_repeats_briefly_when_given_a_short_form() -> None:
    """The question stays open without reprinting twenty lines of options."""
    first = say({}, "audiences", "pick one of three", asking=True, repeat_with="which audience?")
    second = say(
        {"last_said": first["last_said"]},
        "audiences",
        "pick one of three",
        asking=True,
        repeat_with="which audience?",
    )

    assert _content(second) == "which audience?"


def test_falling_silent_is_recorded_so_a_note_can_return() -> None:
    """The bug this caught: the currency note vanished when the market moved to the
    US and never came back on the way to GB, because the stage's digest still held
    the sentence from two turns earlier."""
    said = say({}, "validation", "using USD for a GB campaign")["last_said"]
    quiet = say({"last_said": said}, "validation", "")["last_said"]
    again = say({"last_said": quiet}, "validation", "using USD for a GB campaign")

    assert quiet["validation"] == ""
    assert _content(again) == "using USD for a GB campaign"


# --- choosing the one question ------------------------------------------------


def test_nothing_outstanding_asks_nothing() -> None:
    assert next_question(ANSWERED) is None


def test_the_first_outstanding_basic_is_the_question() -> None:
    question = next_question({"awaiting": ["the start and end dates", "the budget"]})

    assert question == {"kind": "missing", "label": "the start and end dates"}


def test_a_conflict_is_asked_before_a_gap() -> None:
    """An invalid value keeps blocking whatever else is collected, and later
    fields are validated against it - durations against the market's rate card."""
    state = {
        "awaiting": ["the budget"],
        "validation_errors": record({}, "validation", [_blocker()]),
    }

    question = next_question(state)

    assert question["kind"] == "conflict"
    assert question["entry"]["code"] == "market.unknown"


def test_a_warning_alone_asks_nothing() -> None:
    state = {"validation_errors": record({}, "validation", [_warning()])}

    assert next_question(state) is None


def test_the_first_recorded_conflict_wins() -> None:
    """`validate_basics` lists its checks in BASICS order, so the earliest field's
    problem is the one raised - a trader is not asked to fix a currency on a plan
    whose market is not sold."""
    state = {
        "validation_errors": record(
            {}, "validation", [_blocker("market.unknown"), _blocker("currency.unknown")]
        )
    }

    assert next_question(state)["entry"]["code"] == "market.unknown"


# --- routing ------------------------------------------------------------------


def test_basics_route_to_validation_before_inventory() -> None:
    assert route_after_basics(ANSWERED) == "validate_basics"
    assert route_after_basics({"awaiting": ["the budget"]}) == "ask"


def test_validation_blocks_on_an_error_and_passes_a_warning() -> None:
    assert route_after_validation({}) == "select_inventory"
    assert (
        route_after_validation({"validation_errors": record({}, "validation", [_warning()])})
        == "select_inventory"
    )
    assert (
        route_after_validation({"validation_errors": record({}, "validation", [_blocker()])})
        == "ask"
    )


def test_the_inventory_dead_end_still_ends_the_turn() -> None:
    """It asked its own, better question; `ask` would only add a vaguer one."""
    assert route_after_inventory({"awaiting": [NO_INVENTORY]}) == "end"
    assert route_after_inventory({}) == "collect_targeting"
    assert route_after_inventory({"awaiting": ["the budget"]}) == "ask"


def test_a_blocker_overrides_the_dead_end_shortcut() -> None:
    """An unsaid validation failure is worse than a duplicated question."""
    state = {
        "awaiting": [NO_INVENTORY],
        "validation_errors": record({}, "validation", [_blocker()]),
    }

    assert route_after_inventory(state) == "ask"


def test_audiences_route_on_both_conditions() -> None:
    assert route_after_audiences({}) == "predict_reach"
    assert route_after_audiences({"awaiting": ["an audience to plan against"]}) == "ask"
    assert route_after_audiences({"validation_errors": record({}, "validation", [_blocker()])}) == (
        "ask"
    )


def test_waiting_for_the_audience_choice_ends_the_turn() -> None:
    """The node has just listed the three options and asked which to use, so `ask`
    could only append a vaguer duplicate - as with the inventory dead end."""
    assert route_after_audiences({"awaiting": [NO_AUDIENCE_CHOICE]}) == "end"


def test_a_blocker_overrides_the_audience_shortcut() -> None:
    state = {
        "awaiting": [NO_AUDIENCE_CHOICE],
        "validation_errors": record({}, "audiences", [_blocker("audience.unknown_profile")]),
    }

    assert route_after_audiences(state) == "ask"


def test_route_planner_dispatches_properly() -> None:
    from app.agent.gates import route_planner

    # 1. Missing market -> ask
    assert route_planner({}) == "ask"

    # 2. Market present, basics missing -> ask
    assert route_planner({"markets": ["GB"]}) == "ask"

    # 3. All basics present, no inventory -> select_inventory
    basics_done = {
        "markets": ["GB"],
        "flight_start": "2099-08-01",
        "flight_end": "2099-08-31",
        "flight_dates": {"lower": "2099-08-01", "upper": "2099-08-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
    }
    assert route_planner(basics_done) == "select_inventory"

    # 4. Inventory done, targeting unconfirmed -> collect_targeting
    inv_done = {
        **basics_done,
        "selected_deals": [{"deal_id": "D1", "provider": "Prime Video"}],
    }
    assert route_planner(inv_done) == "collect_targeting"

    # 5. Targeting confirmed, no audience -> suggest_audiences
    tgt_done = {
        **inv_done,
        "targeting_confirmed": True,
    }
    assert route_planner(tgt_done) == "suggest_audiences"

    # 6. Audience chosen, no forecast -> predict_reach
    aud_done = {
        **tgt_done,
        "audience_options": [{"profile": "BALANCED"}],
        "chosen_audience": {"profile": "BALANCED"},
    }
    assert route_planner(aud_done) == "predict_reach"

    # 7. Forecast present -> deliver_plan
    delivered = {
        **aud_done,
        "forecast": {"estimated_impressions": 1000000},
    }
    assert route_planner(delivered) == "deliver_plan"

