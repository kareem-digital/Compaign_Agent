"""What the agent asks for, and in what words - decided here, not by a model.

This node used to send `awaiting` to the LLM to be reworded. Three things were wrong with
that, and they are what these tests hold in place:

    the cost         ~1081 ms average across 12 calls, on top of the extract call, so a
                     blocked turn spent ~2.5 s waiting on two round trips
    the content      given the one-item list "a flight that has not already finished -
                     2023-10-01 to 2023-10-31 is in the past", gpt-4o-mini dropped the reason
                     and asked for the dates, the audience, the budget and the channels.
                     Three requirements invented from a list of one, and the budget was
                     already on the card
    the point        the UI renders these as option cards. Once the elicitation format lands,
                     "10 seconds / 15 seconds / 20 seconds / 30 seconds" are buttons - so the
                     sentence being paid for is one the trader will not read

Now the node is deterministic: the same `awaiting` list produces the same words, which is
what makes the wording testable at all.
"""

from __future__ import annotations

from importlib import import_module

import pytest

from app.agent.gates import BASICS, NO_INVENTORY
from app.agent.nodes.ask_for_missing import ask_for_missing

# The module, not the function `app.agent.nodes` re-exports under the same name.
node = import_module("app.agent.nodes.ask_for_missing")

LABELS = [label for _key, label in BASICS]
MARKET, FLIGHT, DURATIONS, BUDGET = LABELS

# A label computed from the trader's own values, carrying its own clause.
REASON = (
    "a flight that has not already finished - 2023-10-01 to 2023-10-31 is in the past, "
    "and today is 2026-08-14"
)


async def _said(awaiting: list[str]) -> str:
    result = await ask_for_missing({"awaiting": awaiting})
    return result["messages"][0]["content"]


# --- no model, ever -----------------------------------------------------------


def test_the_node_does_not_reach_for_a_model():
    """The saving is the point. If someone wires a call back in, this fails."""
    assert not hasattr(node, "get_llm"), "the model is back in ask_for_missing"
    assert not hasattr(node, "_SYSTEM"), "a prompt is back in ask_for_missing"


async def test_the_same_list_always_produces_the_same_words():
    """Determinism is what makes the wording testable - a generated sentence cannot be
    asserted, only hoped for."""
    first = await _said([FLIGHT, BUDGET])
    second = await _said([FLIGHT, BUDGET])

    assert first == second


# --- one or two gaps read as a sentence ---------------------------------------


async def test_one_gap_is_a_sentence():
    said = await _said([BUDGET])

    assert said == "Before I can carry on I need the budget. Could you tell me?"


async def test_two_gaps_are_joined_with_and():
    said = await _said([FLIGHT, BUDGET])

    assert said == (
        "Before I can carry on I need the start and end dates and the budget. "
        "Could you tell me?"
    )


@pytest.mark.parametrize("label", LABELS + [NO_INVENTORY])
async def test_every_label_the_gate_owns_reads_in_a_sentence(label):
    """The labels are noun clauses in `gates.BASICS` precisely so they slot in. If one is ever
    reworded into a question, this catches the double question mark."""
    said = await _said([label])

    assert said.startswith("Before I can carry on I need ")
    assert said.count("?") == 1, said


# --- three or more become a list ----------------------------------------------


async def test_three_or_more_gaps_become_bullets():
    """Four clauses in one sentence is unreadable, and the UI shows a list better anyway."""
    said = await _said(LABELS)

    assert "a few more details:" in said
    for label in LABELS:
        assert f"- {label}" in said
    # The order is the order they get asked in - `BASICS` sets it deliberately.
    assert said.index(f"- {MARKET}") < said.index(f"- {BUDGET}")


# --- a computed reason gets its own sentence ----------------------------------


async def test_a_reason_is_said_word_for_word():
    """The dates and today's date are what make the message actionable. This is what the model
    used to throw away."""
    said = await _said([REASON])

    assert REASON in said
    assert "2023-10-01" in said and "2026-08-14" in said


async def test_a_reason_on_its_own_still_ends_in_a_question():
    """A message that only states a problem leaves the trader nothing to do."""
    said = await _said([REASON])

    assert said.rstrip().endswith("?")


async def test_a_reason_is_not_joined_into_the_sentence():
    """**The bug this split exists for.** The reason carries its own comma and clause, so
    joining it produced: "...today is 2026-08-14 and the budget. Could you tell me?" """
    said = await _said([REASON, BUDGET])

    assert "2026-08-14 and the budget" not in said
    # Two separate sentences, blank line between them.
    assert said.count("\n\n") == 1
    assert BUDGET in said


async def test_the_reason_comes_before_the_question():
    """A trader who typed a date has to hear what was wrong with it before being asked for
    another. The other order reads as the agent not having listened."""
    said = await _said([BUDGET, REASON])

    assert said.index("2023-10-01") < said.index("Before I can carry on")


# --- nothing to ask -----------------------------------------------------------


async def test_nothing_outstanding_says_nothing():
    """The router should never send us here empty, but a silent turn becomes an HTTP 500 - so
    the node returns no message rather than an empty one."""
    assert await ask_for_missing({"awaiting": []}) == {}
    assert await ask_for_missing({}) == {}
