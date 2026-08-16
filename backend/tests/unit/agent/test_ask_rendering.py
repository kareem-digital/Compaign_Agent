"""How the ask node phrases one question - and that it never looks at which field.

The requirement behind this file is "the same behaviour should work for any current
or future validation rule, without field-specific conversational handling". That is
only true if the renderer reads `ValidationResponse` fields and nothing else, so it
is asserted with a code and field that do not exist anywhere in the codebase: if
`ask_for_missing` grows a branch on field name, the first test here fails.

Mirrors `tests/contract/test_targeting_config.py`'s
`test_a_new_targeting_type_needs_no_python` - a requirement written as a test
rather than as a comment.
"""

from importlib import import_module

import pytest

from app.agent.gates import record
from app.agent.nodes.ask_for_missing import ask_for_missing
from app.knowledge.registry.models import ValidationResponse


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """The template path, so the assertions are about content and not phrasing.

    `import_module` rather than a dotted string: `nodes/__init__.py` re-exports
    `ask_for_missing` under its module's name, so
    `"app.agent.nodes.ask_for_missing.get_llm"` resolves to an attribute of the
    *function* and raises.
    """
    monkeypatch.setattr(import_module("app.agent.nodes.ask_for_missing"), "get_llm", lambda: None)


def _state(*responses: ValidationResponse, awaiting: list[str] | None = None) -> dict:
    return {
        "awaiting": awaiting or [],
        "validation_errors": record({}, "some_stage", list(responses)),
    }


async def _reply(state: dict) -> str:
    return (await ask_for_missing(state))["messages"][0]["content"]


async def test_a_rule_the_node_has_never_heard_of_still_reaches_the_trader() -> None:
    """A novel code, field and option set, rendered with no change to the node."""
    invented = ValidationResponse(
        is_valid=False,
        code="frobnicator.unsupported",
        field="frobnicator_mode",
        message="VOW does not support 'turbo' frobnication in GB.",
        suggested_options=["gentle", "standard"],
    )

    reply = await _reply(_state(invented))

    assert "does not support 'turbo' frobnication" in reply
    assert "gentle, standard" in reply
    assert reply.rstrip().endswith("?")


async def test_a_failure_with_no_alternatives_does_not_imply_there_are_some() -> None:
    """A date in the past has nothing to offer instead.

    The LLM path once wrote "Available options: none listed. Please choose one of
    the available options" - it repeats whatever scaffolding it is handed - so
    neither the template nor the prompt mentions options when there are none.
    """
    reply = await _reply(
        _state(
            ValidationResponse(
                is_valid=False,
                code="flight_dates.in_past",
                field="flight_dates",
                message="the flight starts 2020-08-01, which has already passed",
            )
        )
    )

    assert "already passed" in reply
    assert "option" not in reply.lower()
    assert "none" not in reply.lower()
    assert "change it to?" in reply


async def test_a_gap_is_asked_for_one_at_a_time() -> None:
    reply = await _reply(_state(awaiting=["the budget", "the start and end dates"]))

    assert reply == "Before I can carry on I need the budget. Could you tell me?"
    assert "start and end dates" not in reply


async def test_a_conflict_is_phrased_instead_of_a_gap() -> None:
    reply = await _reply(
        _state(
            ValidationResponse(
                is_valid=False,
                code="market.unknown",
                field="target_markets",
                message="I cannot plan for ES - VOW does not sell CTV inventory there.",
                suggested_options=["DE", "FR", "GB", "US"],
            ),
            awaiting=["the budget"],
        )
    )

    assert "cannot plan for ES" in reply
    assert "DE, FR, GB, US" in reply
    assert "the budget" not in reply


async def test_a_warning_is_not_phrased_as_a_question() -> None:
    """Warnings are said by the stage that found them, not asked about here."""
    state = _state(
        ValidationResponse(
            is_valid=True,
            severity="warning",
            code="market.normalized",
            field="target_markets",
            message="Noted - I read UK as GB.",
        )
    )

    assert await ask_for_missing(state) == {}


async def test_nothing_outstanding_says_nothing() -> None:
    """Defensive: the router should never route here with an empty state."""
    assert await ask_for_missing({}) == {}
