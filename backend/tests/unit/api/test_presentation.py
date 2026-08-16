"""What a turn hands a user interface, as distinct from what it says.

`presentation` arrived from the agent-planning lane, where the graph advanced one
stage per turn and `build_blocks` could assume exactly one stage had anything to
show. The merged graph runs the whole gated chain in a turn and finishes at
`delivered`, so that assumption is gone - and with it, silently, was every block
on every completed turn: `delivered` was not in the stage map, so `blocks` came
back empty for the half of the conversation that matters most.

These pin the two places that adaptation touches. Unit rather than component,
because both are pure functions of plan state - going through the graph to reach
them would test the graph.
"""

from app.api.presentation import Interaction, Layout, build_blocks, input_blocks

DEALS = [
    {
        "deal_id": "EXTQ5",
        "provider": "Prime Video",
        "cpm": "18.22",
        "genre": None,
        "ad_lengths": ["15", "30"],
        "inventory_tier": "AMAZON_OWNED",
    },
    {
        "deal_id": "EXTNFLX0012",
        "provider": "Netflix",
        "cpm": "31.50",
        "genre": None,
        "ad_lengths": ["30"],
        "inventory_tier": "THIRD_PARTY_PRECURATED",
    },
]

AUDIENCES = [
    {
        "profile": "NARROW",
        "name": "In-market: premium",
        "segment_count": 3,
        "estimated_size": 900_000,
        "effective_cpm": "21.22",
    },
    {
        "profile": "BALANCED",
        "name": "In-market: broad",
        "segment_count": 7,
        "estimated_size": 2_400_000,
        "effective_cpm": "20.22",
    },
]

FORECAST = {
    "is_available": True,
    "estimated_impressions": 2_744_000,
    "estimated_unique_reach": 720_000,
    "average_frequency": "3.8",
    "indicative_cpm": "18.22",
}

# A plan with every basic answered, so `input_blocks` is empty and the stage map
# is what decides the reply. The raw slots are here as well as the derived fields
# because that is what `_is_answered` reads - see the budget test below.
COMPLETE = {
    "markets": ["GB"],
    "flight_start": "2026-08-01",
    "flight_end": "2026-08-31",
    "flight_dates": {"lower": "2026-08-01", "upper": "2026-08-31", "bounds": "[)"},
    "durations": ["15", "30"],
    "budget_amount": "50000.00",
    "market_budgets": [{"market": "GB", "budget": "50000.00", "base_bid": None}],
    "primary_currency": "GBP",
    "goal": "AWARENESS",
    "kpi": "reach",
    "selected_deals": DEALS,
    "inventory_tier": "AMAZON_OWNED",
    "audience_options": AUDIENCES,
    "chosen_audience": {"profile": "BALANCED"},
    "forecast": FORECAST,
}


def _layouts(blocks) -> list[str]:
    return [block.layout for block in blocks]


# --- the delivered turn ------------------------------------------------------


def test_a_delivered_turn_carries_the_whole_plan_not_just_the_forecast() -> None:
    """`delivered` is where the gated chain ends, and it must render.

    Before this, `_STAGE_BLOCK` held only inventory/audiences/forecast, so a turn
    that ran the chain to completion produced no blocks at all - the plain-text
    reply was the entire response and `blocks` was an empty list a frontend could
    only interpret as "nothing to show".
    """
    blocks = build_blocks({**COMPLETE, "current_stage": "delivered"})

    assert _layouts(blocks) == [Layout.TABLE, Layout.CARDS, Layout.METRICS]


def test_a_delivered_turn_that_never_forecast_omits_the_block() -> None:
    """A builder with nothing to say is dropped, not emitted empty.

    `blocks` means "what is renderable". A metrics block full of nulls is a
    frontend rendering "Unique reach: -" as though the number were zero, which is
    the one thing the forecast honesty rule exists to prevent.
    """
    blocks = build_blocks({**COMPLETE, "current_stage": "delivered", "forecast": None})

    assert _layouts(blocks) == [Layout.TABLE, Layout.CARDS]


def test_a_gate_stopping_mid_chain_still_shows_that_stage() -> None:
    """The per-stage map still works: a turn that ends at the audience choice
    shows the three options and nothing else."""
    blocks = build_blocks({**COMPLETE, "current_stage": "audiences", "forecast": None})

    assert _layouts(blocks) == [Layout.CARDS]
    assert blocks[0].interaction == Interaction.SELECT_ONE


def test_a_blocked_grounding_turn_claims_nothing() -> None:
    """`validation` stops at the `validation` stage, which has no block.

    The explanation is prose and belongs in the text channel; dressing a refusal
    up as a plan would show the trader inventory for a plan that cannot exist.
    """
    assert build_blocks({**COMPLETE, "current_stage": "validation"}) == []


# --- asking for what is still missing ----------------------------------------


def test_a_budget_given_before_a_market_is_not_asked_for_twice() -> None:
    """The blocks channel must agree with the question the agent asks.

    `market_budgets` cannot be keyed until a market is named, so it stays empty
    while `budget_amount` holds the answer. Reading the derived field here made
    the panel ask for a budget the agent had already accepted and would not ask
    for again - the two channels contradicting each other in the same turn.

    Mirrors `test_planning_graph.py::test_a_budget_given_before_a_market_is_not_asked_for_twice`.
    """
    blocks = input_blocks({"budget_amount": "50000.00", "market_budgets": []})

    assert "market_budgets" not in [block.field for block in blocks]
    assert [block.field for block in blocks] == ["markets", "flight_dates", "durations"]


def test_a_half_given_flight_is_still_outstanding() -> None:
    """One end of a range is not an answer, so the picker stays on screen."""
    blocks = input_blocks({"flight_start": "2026-08-01"})

    assert "flight_dates" in [block.field for block in blocks]


def test_a_whole_flight_in_the_raw_slots_counts_as_answered() -> None:
    """The other half of the same rule: both ends present, nothing to ask."""
    blocks = input_blocks({"flight_start": "2026-08-01", "flight_end": "2026-08-31"})

    assert "flight_dates" not in [block.field for block in blocks]


def test_the_first_outstanding_ask_is_the_focal_point() -> None:
    """Unchanged by the presence check moving to the raw slots."""
    blocks = input_blocks({})

    assert blocks[0].field == "markets"
    assert blocks[0].primary is True
    assert all(block.primary is False for block in blocks[1:])


def test_probing_still_shows_what_was_understood_alongside_what_is_missing() -> None:
    """The summary rides with the asks, and only there."""
    blocks = build_blocks({"markets": ["GB"], "current_stage": "basics"})

    assert blocks[0].layout == Layout.SUMMARY_LIST
    assert [block.field for block in blocks[1:]] == [
        "flight_dates",
        "durations",
        "market_budgets",
    ]
