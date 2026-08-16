"""Tests for the deterministic brief parsing in `extract_fields`.

The duration tests exist because of a specific bug: the extraction regex used to
spell out `(10|15|20|30)` while `_VALID_DURATIONS` was derived from
`DurationEnum`. The two agreed, so nothing failed - but adding a length to the
enum would have produced a value the filter accepted and the regex could never
find, and the duration would have vanished silently between the brief and the
state. Silent is the problem: a trader would have seen their 6-second creative
simply not mentioned.

`test_a_duration_added_to_the_enum_becomes_extractable` is the guard. It injects
a wider set rather than adding to `DurationEnum`, because the enum is pinned to
the four the schema document fixes and widening it is a cross-lane change.
"""

from app.agent.nodes.extract_fields import _VALID_DURATIONS, _durations
from app.knowledge.registry.models import DurationEnum, duration_phrase

# --- durations ---------------------------------------------------------------


def test_durations_are_read_from_a_normal_brief() -> None:
    """The unit word travels with the last number only."""
    assert _durations("15 and 30 second creatives") == ["15", "30"]


def test_a_single_duration_with_its_unit_is_read() -> None:
    assert _durations("a 30 second creative") == ["30"]
    assert _durations("30s creative") == ["30"]
    assert _durations("30 sec spot") == ["30"]


def test_bare_numbers_need_a_unit_word_somewhere() -> None:
    """Otherwise "15 and 30" in any sentence would become creative lengths."""
    assert _durations("15 and 30") == []


def test_budgets_and_years_are_not_durations() -> None:
    """Word boundaries do this: neither "50,000" nor "2026" yields a bare match."""
    assert _durations("£50,000 for August 2026, 30 second creatives") == ["30"]


def test_a_length_the_platform_does_not_sell_is_not_extracted() -> None:
    """6 is not in `DurationEnum` today, so it must not reach state."""
    assert _durations("a 6 second creative") == []


def test_a_duration_added_to_the_enum_becomes_extractable() -> None:
    """The property the hardcoded alternation broke.

    Injected rather than added to `DurationEnum`: the enum is transcribed from
    schema v2 section 5 and pinned by tests/contract, so widening it for real is
    a contract change needing all three lanes. This proves the mechanism.
    """
    assert _durations("a 6 second creative", valid=("6", *_VALID_DURATIONS)) == ["6"]


def test_an_injected_duration_works_in_the_bare_number_branch_too() -> None:
    """Both regexes are built from the same set - neither may be left behind."""
    assert _durations("6 and 30 second creatives", valid=("6", *_VALID_DURATIONS)) == ["6", "30"]


def test_durations_come_back_in_numeric_order() -> None:
    """Sorted by int, not lexically - otherwise "10" would precede "6"."""
    assert _durations("30, 15 and 10 second creatives") == ["10", "15", "30"]


def test_the_valid_set_is_the_enum() -> None:
    assert set(_VALID_DURATIONS) == {d.value for d in DurationEnum}


# --- the shared prose --------------------------------------------------------


def test_the_duration_phrase_lists_every_sellable_length() -> None:
    """One builder feeds the gate question, the LLM rules and the validator.

    Written out in three places, whichever was missed on a change would be the
    agent stating something untrue to a trader.
    """
    phrase = duration_phrase()

    for duration in _VALID_DURATIONS:
        assert duration in phrase
    assert phrase == "10, 15, 20 or 30"


def test_the_conjunction_is_settable_for_a_different_sentence() -> None:
    assert duration_phrase("and") == "10, 15, 20 and 30"
