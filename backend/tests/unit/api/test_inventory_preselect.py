"""Which inventory rows arrive already ticked.

**Found in a real network response.** Every row came back `"selected": true`, including two
that cannot be bought:

    Netflix   note: "No reach forecast"
    Disney+   note: "Rate card only"        <- the deal does not exist yet

The rows are the checkboxes that write `selected_deals`, and
`select_inventory.dominant_tier` takes the **most conservative** tier across whatever ends up
there. So a trader who left Disney+ ticked and pressed continue would push the plan's tier to
`THIRD_PARTY_NEEDS_CURATION` and switch the reach forecast off - a default nobody chose,
changing what the plan is able to promise.

It was invisible only because the frontend reads `message.content` and ignores `blocks`
entirely today. The moment the elicitation format lands it becomes real behaviour, which is
why it is worth fixing before that and not after.
"""

from __future__ import annotations

import pytest

from app.agent.nodes.select_inventory import (
    AMAZON_OWNED,
    THIRD_PARTY_NEEDS_CURATION,
    THIRD_PARTY_PRECURATED,
)
from app.api.presentation import inventory_block

PRIME = {
    "deal_id": "EXTQ5",
    "provider": "Prime Video",
    "cpm": "18.22",
    "ad_lengths": ["15", "30"],
    "inventory_tier": AMAZON_OWNED,
    "genre": None,
}
PRIME_ACTION = {**PRIME, "deal_id": "EXT7P", "cpm": "22.07", "genre": "Action"}
NETFLIX = {
    "deal_id": "EXTNFLX0012",
    "provider": "Netflix",
    "cpm": "31.50",
    "ad_lengths": ["30"],
    "inventory_tier": THIRD_PARTY_PRECURATED,
    "genre": None,
}
DISNEY = {
    "deal_id": "EXTDSNY0007",
    "provider": "Disney+",
    "cpm": "34.00",
    "ad_lengths": ["15", "30"],
    "inventory_tier": THIRD_PARTY_NEEDS_CURATION,
    "genre": None,
}

ALL_FOUR = [PRIME, PRIME_ACTION, NETFLIX, DISNEY]


def _state(**extra) -> dict:
    return {
        "markets": ["GB"],
        "durations": ["30"],
        "flight_dates": {"lower": "2026-10-01", "upper": "2026-10-31"},
        "market_budgets": [{"market": "GB", "budget": "15000.00"}],
        "primary_currency": "GBP",
        "selected_deals": ALL_FOUR,
        "preferred_providers": [],
        "inventory_alternatives": [],
        **extra,
    }


def _rows(state: dict) -> list[dict]:
    block = inventory_block(state)
    assert block is not None
    return block.data["rows"]


def _ticked(state: dict) -> list[str]:
    return [row["provider"] for row in _rows(state) if row["selected"]]


# --- nothing named: only what can be acted on today ---------------------------


def test_only_amazon_inventory_arrives_ticked():
    """The exact payload from the bug report - all four rows, nothing named by the trader."""
    assert _ticked(_state()) == ["Prime Video", "Prime Video"]


@pytest.mark.parametrize("deal", [NETFLIX, DISNEY])
def test_inventory_that_cannot_be_bought_is_never_pre_ticked(deal):
    ticked = [row for row in _rows(_state()) if row["value"] == deal["deal_id"]]

    assert ticked and ticked[0]["selected"] is False, deal["provider"]


def test_the_unticked_rows_are_still_on_screen_with_their_reason():
    """Not hiding them - an option that is not offered cannot be chosen, and the note is what
    makes the trade-off visible rather than a footnote."""
    rows = {row["provider"]: row for row in _rows(_state())}

    assert set(rows) == {"Prime Video", "Netflix", "Disney+"}
    assert rows["Netflix"]["note"] == "No reach forecast"
    assert rows["Disney+"]["note"] == "Rate card only"


def test_a_market_with_no_amazon_inventory_ticks_nothing():
    """Then the trader genuinely has to choose, and the notes tell them what each choice
    costs. Guessing on their behalf here is what the whole fix is against."""
    assert _ticked(_state(selected_deals=[NETFLIX, DISNEY])) == []


# --- they named providers: the rows are their own answer -----------------------


def test_a_named_provider_arrives_ticked_whatever_its_tier():
    """`select_inventory` has already filtered to what they asked for, so every row IS the
    answer. Un-ticking it would ask them to say it twice."""
    state = _state(selected_deals=[NETFLIX], preferred_providers=["Netflix"])

    assert _ticked(state) == ["Netflix"]


def test_naming_a_provider_switches_the_block_to_confirm():
    """The shape follows from the same fact: a choice already made is confirmed, not asked."""
    block = inventory_block(_state(selected_deals=[PRIME], preferred_providers=["Prime Video"]))

    assert block is not None
    assert block.interaction == "confirm"
    assert block.data["confirming"] == ["Prime Video"]


def test_no_deals_at_all_renders_nothing_structured():
    """Nothing to tick, and nothing claimed - the explanation stays in the text channel."""
    assert inventory_block(_state(selected_deals=[])) is None
