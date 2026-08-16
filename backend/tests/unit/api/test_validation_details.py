"""The state-to-wire mapping behind "Why this answer?".

These pin the four things a UI would otherwise get wrong, and that no assertion on
the graph would catch because the graph is happy either way:

  * A pass carries `severity="error"` in state, because `_ok()` leaves the default.
    Passed through verbatim, every green check would render red.
  * `grounded` and `is_valid` are different questions. A rejected market is grounded
    *and* invalid - the registry answered, and the answer was no.
  * A stage that did not run this turn keeps last turn's entries, deliberately. A
    panel that shows those as this turn's reasoning is lying quietly.
  * `blocks` has to agree with what the routers acted on, not with a second
    derivation of the rule.

Unit rather than api, per tests/unit/api/__init__.py: no route, no graph, no MCP -
the builder reads a dict.
"""

from importlib import import_module

import pytest

from app.agent.gates import blocking, record, record_checks
from app.api.validation_details import (
    _STAGE_ORDER,
    ValidationCheck,
    build_validation_details,
)
from app.knowledge.registry.models import ValidationResponse

PROVENANCE = {
    "schema_version": "1",
    "version": 3,
    "content_hash": "91b653bd",
    "synced_at": "2026-08-06T09:14:22.481000+00:00",
    "source": "mock",
    "markets_loaded": ["GB"],
    "is_complete": True,
    "is_stale": False,
}


def _pass(code: str = "market.ok", **extra) -> ValidationResponse:
    """A plain pass, severity left at the model's default - as `_ok()` leaves it."""
    return ValidationResponse(is_valid=True, message=f"{code} fine", code=code, **extra)


def _warning(code: str = "market.normalized", **extra) -> ValidationResponse:
    return ValidationResponse(
        is_valid=True, severity="warning", message=f"{code} noted", code=code, **extra
    )


def _blocker(code: str = "market.unknown", **extra) -> ValidationResponse:
    return ValidationResponse(is_valid=False, message=f"{code} failed", code=code, **extra)


def _state(*responses: ValidationResponse, stage: str = "validation", **extra) -> dict:
    """State as the nodes leave it: both lists, written from one set of responses."""
    return {
        "current_stage": stage,
        "validation_errors": record({}, stage, list(responses)),
        "validation_checks": record_checks({}, stage, list(responses)),
        "registry_provenance": PROVENANCE,
        **extra,
    }


# --- nothing checked ----------------------------------------------------------


def test_an_untouched_state_reports_nothing_rather_than_guessing() -> None:
    details = build_validation_details({})

    assert details.grounded is False
    assert details.is_valid is True
    assert details.blocks is False
    assert details.severity is None
    assert details.checks == []
    assert details.awaiting == []
    assert details.changes == []
    assert details.registry is None


def test_nothing_is_grounded_before_a_market_is_named() -> None:
    """The snapshot is market-scoped, so `validate_basics` never ran."""
    details = build_validation_details(
        {"current_stage": "basics", "awaiting": ["which country the campaign runs in"]}
    )

    assert details.grounded is False
    assert details.registry is None
    assert details.awaiting == ["which country the campaign runs in"]


# --- the pass problem, which is the reason this module exists ------------------


def test_a_clean_turn_is_not_reported_as_an_error() -> None:
    """`severity` is "error" on a pass only because `_ok()` leaves the default.

    Read verbatim, a five-pass turn reports `severity="error"` and every check
    renders red. The rollup and each entry both null it.
    """
    details = build_validation_details(_state(_pass("market.ok"), _pass("duration.ok")))

    assert details.severity is None
    assert details.is_valid is True
    assert details.blocks is False
    assert [check.severity for check in details.checks] == [None, None]
    assert [check.blocks for check in details.checks] == [False, False]


def test_the_checks_a_clean_turn_ran_survive_where_the_errors_list_is_empty() -> None:
    """`validation_errors` drops passes, so it is empty exactly when all went well."""
    state = _state(_pass("market.ok"), _pass("currency.ok"))

    assert state["validation_errors"] == []
    assert [check.code for check in build_validation_details(state).checks] == [
        "market.ok",
        "currency.ok",
    ]


# --- grounded is not valid ----------------------------------------------------


def test_a_registry_rejection_is_grounded_and_invalid() -> None:
    """The most informative answer this feature has, and the one a single flag loses.

    The registry was consulted, it answered, and its answer was no.
    """
    details = build_validation_details(
        _state(_blocker("market.unknown", field="target_markets", suggested_options=["GB", "US"]))
    )

    assert details.grounded is True
    assert details.is_valid is False
    assert details.blocks is True
    assert details.severity == "error"

    (check,) = details.checks
    assert check.blocks is True
    assert check.severity == "error"
    assert check.suggested_options == ["GB", "US"]
    assert check.field == "target_markets"


def test_a_warning_is_reported_without_blocking() -> None:
    details = build_validation_details(
        _state(_warning("duration.not_on_rate_card", suggested_options=["15", "30"]))
    )

    assert details.severity == "warning"
    assert details.blocks is False
    assert details.is_valid is True
    assert details.checks[0].suggested_options == ["15", "30"]


def test_a_soft_failure_neither_blocks_nor_reads_as_clean() -> None:
    """`is_valid=False, severity="warning"` - what `predict_reach` downgrades a
    forecast contract violation to, so it is said without stopping the turn."""
    soft = ValidationResponse(
        is_valid=False, severity="warning", message="soft", code="forecast.fabricated_reach"
    )

    details = build_validation_details(_state(soft, stage="forecast"))

    assert details.is_valid is False
    assert details.blocks is False
    assert details.severity == "warning"


def test_a_blocker_outranks_a_warning_in_the_rollup() -> None:
    details = build_validation_details(_state(_warning(), _blocker(), _pass()))

    assert details.severity == "error"
    assert details.blocks is True


# --- agreeing with what the flow actually did ---------------------------------


@pytest.mark.parametrize(
    "response",
    [
        _pass(),
        _warning(),
        _blocker(),
        ValidationResponse(is_valid=False, severity="warning", message="s", code="s"),
    ],
)
def test_blocks_agrees_with_the_gate_the_routers_used(response: ValidationResponse) -> None:
    """The routers read `validation_errors`. A panel saying "blocked" about a turn
    that ran on - or the reverse - is worse than saying nothing."""
    state = _state(response)

    assert build_validation_details(state).blocks == bool(blocking(state))


def test_the_wire_shape_carries_every_field_of_the_model_it_serializes() -> None:
    """Fails the day `ValidationResponse` gains a field, rather than dropping it.

    Restated rather than subclassed so `severity` can be nulled on a pass, which a
    subclass could not do without breaking `blocks` - so the field sets need pinning.
    """
    assert set(ValidationResponse.model_fields) <= set(ValidationCheck.model_fields)


def test_every_stage_the_graph_can_report_is_in_the_stage_order() -> None:
    """`checked_this_turn` is derived from `current_stage`'s position, so a stage
    missing from the tuple would silently mark its checks stale forever."""
    stages = {
        import_module(f"app.agent.nodes.{name}").STAGE
        for name in (
            "extract_fields",
            "validate_basics",
            "select_inventory",
            "suggest_audiences",
            "predict_reach",
            "deliver_plan",
        )
    }

    assert stages <= set(_STAGE_ORDER)


# --- current, but not necessarily this turn's --------------------------------


def test_an_earlier_stage_that_ran_this_turn_is_marked_checked() -> None:
    details = build_validation_details(_state(_pass(), stage="delivered"))

    assert details.checks[0].checked_this_turn is True


def test_a_carried_over_entry_is_not_attributed_to_this_turn() -> None:
    """`gates.record` replaces only the running stage's entries, so an audience
    blocker survives a turn that stopped at validation - and still blocks it. The
    panel has to show that as carried over rather than as this turn's reasoning."""
    state = {
        "current_stage": "validation",
        "validation_errors": record({}, "audiences", [_blocker("audience.unknown_profile")]),
        "validation_checks": record_checks({}, "audiences", [_blocker("audience.unknown_profile")]),
        "registry_provenance": PROVENANCE,
    }

    details = build_validation_details(state)

    assert details.checks[0].checked_this_turn is False
    # Still blocking, because it still is.
    assert details.blocks is True


def test_a_turn_that_reported_no_stage_marks_nothing_as_checked() -> None:
    details = build_validation_details(
        {"validation_checks": record_checks({}, "validation", [_pass()])}
    )

    assert details.checks[0].checked_this_turn is False


# --- provenance ---------------------------------------------------------------


def test_provenance_names_the_snapshot_the_answers_were_checked_against() -> None:
    registry = build_validation_details(_state(_pass())).registry

    assert registry is not None
    assert registry.version == 3
    assert registry.source == "mock"
    assert registry.markets_loaded == ["GB"]
    assert registry.is_stale is False
    assert registry.synced_at == "2026-08-06T09:14:22.481000+00:00"


def test_provenance_exposes_no_operator_diagnostics() -> None:
    """The allowlist guard. `degraded_sources` is MCP tool names, `rejected_items`
    carries ingest-time pydantic error text with the raw input value in it, and
    `diff` enumerates deal IDs. None of them is an answer to a trader's question."""
    wire = build_validation_details(_state(_pass())).registry.model_dump()

    for leaked in (
        "degraded_sources",
        "rejected_items",
        "integrity_warnings",
        "diff",
        "compatibility",
    ):
        assert leaked not in wire


# --- before and after --------------------------------------------------------


def test_a_normalized_value_is_reported_as_a_change() -> None:
    """Read off `metadata["renamed"]`, which is where the validator already puts it."""
    renamed = _warning(
        "market.normalized", field="target_markets", metadata={"renamed": {"UK": "GB"}}
    )

    (change,) = build_validation_details(_state(renamed)).changes

    assert (change.field, change.code, change.before, change.after) == (
        "target_markets",
        "market.normalized",
        "UK",
        "GB",
    )


def test_a_turn_that_changed_nothing_reports_no_changes() -> None:
    assert build_validation_details(_state(_pass(), _blocker())).changes == []
