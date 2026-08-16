"""What the voice layer is allowed to change, and what it is not.

The layer rewrites prose the graph already computed. Everything worth asserting is
therefore about the difference between the two texts: the voice may reorder,
reframe and connect, and it may not introduce a figure, lose a provider or turn a
line into an essay.

Each rejection test is a failure that was worth building a guard for. An invented
CPM is a wrong price in front of someone about to commit budget; a dropped
provider removes an option from a choice; padding is where invented next steps and
softened caveats live. When the guard fires the trader still gets the computed
text, so a bad rewrite costs voice, never facts.
"""

import asyncio
import logging
import time

import pytest

from app.agent import voice
from app.config import get_settings

# Two blocks from a real GB turn - the inventory list and the plan summary. Kept
# verbatim from `tests/component/agent/test_planning_graph.py` so the fixtures the
# guard is tuned against are the prose it actually sees, including the two ways
# the blocks write a budget: "50000.00" and "50,000".
INVENTORY = (
    "CTV inventory available in GB:\n"
    "\n"
    "- Prime Video - 18.22 CPM (15, 30s) - Amazon-owned (reach forecast available)\n"
    "- Netflix - 31.50 CPM (30s) - third-party, pre-curated (no reach forecast)"
)

PLAN = (
    "**CTV GB 2026-08** - here is the complete plan.\n"
    "\n"
    "- Market: GB\n"
    "- Budget: 50,000 GBP\n"
    "- Inventory: 2 deals, Amazon-owned (reach forecast available)"
)

BLOCKS = [INVENTORY, PLAN]
SOURCE = f"{INVENTORY}\n\n{PLAN}"

PROVIDERS = ("Prime Video", "Netflix")


class _StubLLM:
    """A model that returns what the test tells it to, or raises."""

    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self._reply = reply
        self._error = error
        self.calls: list[list[dict]] = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self._error:
            raise self._error
        return type("Response", (), {"content": self._reply})()


@pytest.fixture(autouse=True)
def _voice_on(monkeypatch):
    """The layer enabled, regardless of the environment the suite runs in.

    Through the setting rather than around it, and the cache is cleared on both
    sides because `get_settings` is process-wide - the same idiom as
    `tests/contract/test_targeting_config.py`.
    """
    monkeypatch.setenv("VOICE_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def _use(monkeypatch, llm) -> None:
    monkeypatch.setattr(voice, "get_voice_llm", lambda: llm)


async def _render(**kwargs) -> str:
    return await voice.render_turn(
        BLOCKS, trader_message="GB, August, 15s and 30s, 50k", providers=PROVIDERS, **kwargs
    )


# --- the layer doing its job -------------------------------------------------


async def test_a_faithful_rewrite_is_what_the_trader_reads(monkeypatch) -> None:
    """Every figure carried, every provider kept, framed as one turn."""
    rewrite = (
        "Got it - GB, August, 15s and 30s against 50,000 GBP.\n"
        "\n"
        "Two deals match: Prime Video at 18.22 CPM and Netflix at 31.50 CPM.\n"
        "Prime Video is Amazon-owned so reach forecasting is available.\n"
        "\n"
        "Shall I forecast against it?"
    )
    _use(monkeypatch, _StubLLM(rewrite))

    assert await _render() == rewrite


async def test_the_trader_and_the_facts_both_reach_the_model(monkeypatch) -> None:
    """The prompt carries the message to mirror and the material to re-voice."""
    stub = _StubLLM("Prime Video 18.22, Netflix 31.50. Next?")
    _use(monkeypatch, stub)

    await _render(stage="inventory")

    system, user = stub.calls[0]
    assert "programmatic media trad" in system["content"]
    assert "ACKNOWLEDGE & MIRROR" in system["content"]
    assert "GB, August, 15s and 30s, 50k" in user["content"]
    assert INVENTORY in user["content"]


async def test_the_stage_name_is_never_handed_to_the_model(monkeypatch) -> None:
    """It leaked. "Plan is at delivered stage" reached a trader in a live run.

    `stage` is a log field and a UI field; in a reply it is jargon about the
    agent's own machinery. Passing it as context and asking for discretion is a
    weaker guarantee than not passing it, so the prompt does not carry it.
    """
    stub = _StubLLM("Prime Video 18.22, Netflix 31.50. Next?")
    _use(monkeypatch, stub)

    await _render(stage="delivered")

    _, user = stub.calls[0]
    assert "delivered" not in user["content"]


@pytest.mark.parametrize("written", ["50000", "50,000", "50000.00"])
async def test_writing_a_budget_the_other_way_is_not_an_invention(monkeypatch, written) -> None:
    """The same money in every form the blocks and the model write it.

    `extract_fields` states "50000.00", `deliver_plan` states "50,000", and a
    model handed either writes whichever reads better. The first live turn was
    rejected for exactly this - "invented_figures:50000" against a source that
    said "50000.00" - so all three forms are pinned rather than the two that
    happened to be in the fixtures.
    """
    _use(monkeypatch, _StubLLM(f"Prime Video 18.22, Netflix 31.50, budget {written} GBP. Next?"))

    assert f"{written} GBP" in await voice.render_turn(
        [INVENTORY, "- Budget: 50000.00 GBP (GB)"],
        trader_message="50k please",
        providers=PROVIDERS,
    )


async def test_rounding_a_cpm_is_still_an_invention(monkeypatch) -> None:
    """The normalisation makes equal values equal - not near ones.

    "18.22" to "18.2" is a different price, and the whole guard would be theatre
    if collapsing trailing zeros also collapsed the digit before them.
    """
    _use(monkeypatch, _StubLLM("Prime Video at 18.2 CPM, Netflix at 31.50. Next?"))

    assert await _render() == SOURCE


async def test_a_numbered_list_is_not_read_as_a_claim(monkeypatch) -> None:
    """List markers are ordinals, not figures.

    Without this the guard rejects good prose for writing "1." - the numbers
    that matter are the ones inside the lines, not the ones counting them.
    """
    rewrite = (
        "Two deals in GB:\n"
        "\n"
        "1. Prime Video - 18.22 CPM\n"
        "2. Netflix - 31.50 CPM\n"
        "\n"
        "Which do you want to lead with?"
    )
    _use(monkeypatch, _StubLLM(rewrite))

    assert await _render() == rewrite


# --- the guard ---------------------------------------------------------------


async def test_an_invented_cpm_never_reaches_the_trader(monkeypatch, caplog) -> None:
    """The failure the whole layer is built around: a price nobody computed."""
    _use(
        monkeypatch,
        _StubLLM("Prime Video 18.22 and Netflix 31.50, blended to 24.86 CPM. Shall I forecast?"),
    )

    with caplog.at_level(logging.WARNING):
        assert await _render() == SOURCE

    # Off the record's structured fields rather than the formatted line: `kv` puts
    # them in `extra_fields`, and the reason is the whole diagnostic value of the
    # event - "it was rejected" without "because it invented 24.86" is unactionable.
    rejection = next(r for r in caplog.records if r.message == "voice.rejected")
    assert rejection.extra_fields["reason"] == "invented_figures:24.86"


async def test_summarising_away_a_provider_is_rejected(monkeypatch) -> None:
    """ "Two options" is not a choice a trader can make."""
    _use(monkeypatch, _StubLLM("I found two CTV deals in GB from 18.22 CPM. Shall I forecast?"))

    assert await _render() == SOURCE


async def test_a_short_message_does_not_come_back_as_an_essay(monkeypatch) -> None:
    """The padding guard, on the one-line repeat that exists to stop a loop.

    `deliver_plan.STANDING_BY` is short deliberately: it is what the trader gets
    instead of the whole plan restated. Re-voicing it into three paragraphs would
    undo exactly the fix it belongs to.
    """
    from app.agent.nodes.deliver_plan import STANDING_BY

    _use(
        monkeypatch,
        _StubLLM(
            "Absolutely, and thank you for confirming! The plan we assembled together "
            "is sitting right there above this message, fully costed and ready for "
            "your review whenever you are ready to proceed. If there is anything at "
            "all you would like to revisit - perhaps the market, the flight dates, "
            "the creative durations, the budget, or indeed the audience selection - "
            "then simply say the word and I will happily re-plan the entire thing "
            "from scratch for you right away."
        ),
    )

    assert (
        await voice.render_turn([STANDING_BY], trader_message="thanks", providers=PROVIDERS)
        == STANDING_BY
    )


async def test_asking_the_same_thing_twice_is_rejected(monkeypatch) -> None:
    """What the first live run against a real model actually produced.

    The blocks each stand alone, so two of them can carry the turn's question. A
    model told to be faithful emits both, and the trader is asked the same thing
    twice in one reply - the form-like reading this layer exists to remove.
    """
    _use(
        monkeypatch,
        _StubLLM(
            "Which audience shall I forecast against?\n"
            "\n"
            "Prime Video 18.22 CPM, Netflix 31.50 CPM.\n"
            "\n"
            "Which audience shall I forecast against?"
        ),
    )

    assert await _render() == SOURCE


async def test_a_line_the_blocks_themselves_repeat_is_not_the_models_fault(monkeypatch) -> None:
    """A caveat stated twice in the source may be stated twice in the rewrite.

    `deliver_plan` deliberately repeats warnings that were said when they were
    found, so a duplication rule that ignored the source would reject the plan
    summary for doing its job.
    """
    twice = "Reach forecasting is available for Amazon inventory only."
    blocks = [f"Prime Video - 18.22 CPM\n{twice}", f"Netflix - 31.50 CPM\n{twice}"]
    _use(monkeypatch, _StubLLM(f"Prime Video 18.22.\n{twice}\nNetflix 31.50.\n{twice}"))

    rendered = await voice.render_turn(
        blocks, trader_message="what have we got?", providers=PROVIDERS
    )

    assert rendered.count(twice) == 2


async def test_an_empty_answer_is_not_a_reply(monkeypatch) -> None:
    _use(monkeypatch, _StubLLM("   "))

    assert await _render() == SOURCE


# --- degrading ---------------------------------------------------------------


async def test_a_slow_model_gives_up_instead_of_spending_the_turn(monkeypatch, caplog) -> None:
    """The outage this budget exists to prevent.

    Phrasing ran 8-25 seconds in production against a browser that stops waiting
    at 30. Added to extraction, turns crossed the ceiling and rendered as "the
    agent could not be reached" - on a backend that had done the work correctly
    and was about to return it.

    So the deadline is asserted twice over: the blocks come back, and they come
    back *promptly*. Waiting for the call and discarding the answer would satisfy
    the first assertion while leaving the bug exactly where it was.
    """
    monkeypatch.setenv("VOICE_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()

    class _Slow:
        async def ainvoke(self, messages):
            await asyncio.sleep(30)
            raise AssertionError("the deadline should have abandoned this call")

    _use(monkeypatch, _Slow())

    started = time.monotonic()
    with caplog.at_level(logging.WARNING):
        assert await _render() == SOURCE
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"waited {elapsed:.1f}s for a call it was supposed to abandon"
    assert [r for r in caplog.records if r.message == "voice.timeout"]


async def test_a_model_outage_costs_voice_and_not_the_plan(monkeypatch, caplog) -> None:
    _use(monkeypatch, _StubLLM(error=RuntimeError("gateway timeout")))

    with caplog.at_level(logging.WARNING):
        assert await _render() == SOURCE

    assert "voice.failed" in caplog.text


async def test_without_a_model_the_computed_blocks_go_out_verbatim(monkeypatch) -> None:
    """The CI configuration, and the contract the pinned conversation tests hold."""
    _use(monkeypatch, None)

    assert await _render() == SOURCE


async def test_the_setting_turns_it_off_even_with_a_model(monkeypatch) -> None:
    """How a deployment with a key gets the raw computed prose back."""
    monkeypatch.setenv("VOICE_ENABLED", "false")
    get_settings.cache_clear()
    _use(monkeypatch, _StubLLM("Anything at all."))

    assert await _render() == SOURCE
