"""Reading a flight out of a message.

**Found on the UI, and it is the worst kind of bug: it looked like success.** A trader typed

    £15,000, running from October 1st to October 31st

and the plan came back carrying `2023-10-01` to `2023-10-31` - three years before the
conversation was happening. Inventory was matched for it, the confirmation card read it back,
and nothing anywhere objected.

This file covers the *reading* half - the prompt and the pattern matcher. The *refusing* half
now belongs to the grounded registry, whose `check_flight_dates` already had the rule and no
caller; see `test_grounding.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.agent.nodes.extract_fields import _flight_dates, _system_prompt

TODAY = date.today()


# --- the prompt has to know what day it is ------------------------------------


def test_the_prompt_carries_todays_date():
    """Without this the model has nothing to resolve "October" against - it reaches for its
    training data instead, which is where 2023 came from."""
    assert f"TODAY IS {TODAY.isoformat()}" in _system_prompt()


def test_the_prompt_resolves_an_ambiguous_month_forward():
    """A month with no year is genuinely ambiguous, so the prompt settles it."""
    prompt = _system_prompt()

    assert "NEXT TIME IT OCCURS" in prompt
    assert "never the one just gone" in prompt


def test_the_prompt_tells_the_model_not_to_sanitise_a_stated_year():
    """**Learned from a failing check, and it is the more important half.**

    The first version of this rule said "never a date in the past", and the model read that as
    permission to correct the trader: sent "October 2023" over a plan already holding October
    2026, it returned 2026 - keeping the old value and dropping what had been typed. The turn
    then moved on to audiences as though nothing had been said.

    Reading and rejecting are different jobs. A stated year comes back exactly as given, and
    the registry refuses it out loud with the dates in the sentence. Sanitising in the prompt
    makes the model take a decision the trader never hears about.
    """
    prompt = _system_prompt()

    assert "RETURN IT EXACTLY AS GIVEN" in prompt
    assert "including a past" in prompt
    assert "do not keep the previous value" in prompt
    # And the instruction that caused it is gone.
    assert "never a date in the past" not in prompt


def test_a_bare_year_over_the_same_month_is_a_known_limit():
    """**Documented rather than pretended away.** Probed against gpt-4o-mini directly:

        "change the flight to October 2023"   ->  2023-10-01   correction applied
        "run it in March 2024"                ->  2024-03-01   correction applied
        "October 2023"                        ->  2026-10-01   NOT applied

    With a plan already holding October, a bare "October 2023" reads to the model as restating
    the month rather than correcting the year, so the old value is carried forward. Every
    phrasing that reads as an instruction works, and the original bug - a month with NO year
    resolving into the past - is gone either way.

    Not worth a stronger prompt rule: "a year in the message always replaces the known year"
    would misfire on "we ran this in October 2023, do the same again", where the year is
    context and not the value. Recorded here so the boundary is a decision rather than a
    surprise to whoever meets it next. There is nothing deterministic to assert about a model,
    so this test holds the note and `test_grounding` holds the behaviour.
    """
    assert "RETURN IT EXACTLY AS GIVEN" in _system_prompt()


def test_the_date_is_not_frozen_at_import(monkeypatch):
    """Built per call on purpose. A server that stays up for a week would otherwise go on
    telling the model it is still the morning it booted.

    `import_module`, not `import ... as`: `nodes/__init__` re-exports names from this module,
    so the dotted path can resolve to a function with no `date` on it to patch.
    """
    from importlib import import_module  # noqa: PLC0415

    node = import_module("app.agent.nodes.extract_fields")

    class _Frozen(date):
        @classmethod
        def today(cls):
            return date(2030, 5, 17)

    monkeypatch.setattr(node, "date", _Frozen)

    assert "TODAY IS 2030-05-17" in _system_prompt()


# --- the pattern path ---------------------------------------------------------


def test_a_month_still_to_come_stays_in_this_year():
    """The month after this one, whatever month it is now."""
    soon = TODAY.replace(day=1) + timedelta(days=32)
    start, _end = _flight_dates(soon.strftime("%B"))

    assert start == f"{soon.year:04d}-{soon.month:02d}-01"


def test_a_month_already_gone_rolls_to_next_year():
    """**The pattern half of the bug.** This read `date.today().year` flat, so a month that had
    already passed produced a flight that had already finished."""
    gone = TODAY.replace(day=1) - timedelta(days=40)
    start, end = _flight_dates(gone.strftime("%B"))

    assert start is not None and end is not None
    assert date.fromisoformat(start) > TODAY, f"{start} is not in the future"


def test_a_stated_year_is_respected_even_when_it_is_past():
    """The trader's own words are never rewritten - "October 2023" means 2023. The registry
    catches it and asks about it, rather than it being silently corrected to a year they did
    not type."""
    assert _flight_dates("October 2023") == ("2023-10-01", "2023-10-31")


def test_the_last_day_of_the_month_is_the_real_last_day():
    assert _flight_dates("February 2028") == ("2028-02-01", "2028-02-29")
    assert _flight_dates("February 2027") == ("2027-02-01", "2027-02-28")
