"""The state carried through the CTV planning graph.

Field names come verbatim from `PlanningAgentState` in
`VOW_Strategy_Schema_v2.md` section 5, which is the cross-lane contract. Only
the fields the current four nodes touch are declared - the remaining ones
(approval, creative, tracking, credit, activation) land with their stages.

Partial by design, not by accident: `scripts/schema_drift.py` reports the gap
so it stays visible rather than being forgotten.
"""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class PlanningAgentState(TypedDict, total=False):
    """State for the CTV planning flow.

    `total=False` because nodes fill this progressively - a state part-way
    through the graph is legitimately incomplete, and every node returns only
    the keys it owns for LangGraph to merge.
    """

    # --- Conversation ---
    messages: Annotated[list, add_messages]

    # --- Session context ---
    advertiser_id: str
    session_id: str
    current_stage: str

    # --- Basics (step 1) ---
    strategy_name: str | None
    brand: str | None           # user-stated brand/advertiser name, e.g. "Mega Toothpaste"
    flight_dates: dict | None  # {"lower": "YYYY-MM-DD", "upper": "YYYY-MM-DD"}
    markets: list[str]  # ISO country codes
    durations: list[str]  # creative durations in seconds, as strings
    primary_currency: str
    goal: str  # fixed AWARENESS for CTV
    kpi: str  # reach or frequency
    market_budgets: list[dict]  # [{market, budget, base_bid}]

    # --- Inventory (step 2) ---
    # Providers the trader named, anywhere in the conversation. Empty means no
    # preference expressed, so the inventory stage should offer a choice rather
    # than confirm one.
    preferred_providers: list[str]
    inventory_tier: str | None  # dominant tier, drives downstream branching
    selected_deals: list[dict]
    # Providers available in this market that the trader did NOT choose, so a
    # confirmation can show the way out.
    inventory_alternatives: list[str]

    # --- Audiences & Targeting (step 4 & 5) ---
    audience_options: list[dict]  # always three: narrow / balanced / wide
    chosen_audience: dict | None
    audience_refinement: str | None  # e.g. "runners 25-44", "fitness enthusiasts"
    location_type: str | None  # "market_wide", "city", "postcodes", "radius"
    locations: list[str]  # e.g. ["GB"], ["London"]
    postcodes: list[str]  # list of validated postcodes
    radius_targeting: dict | None  # {"location": "London", "distance": 10, "unit": "miles"}

    # --- Budget split (when multiple deals selected) ---
    budget_split: list[dict] | None  # [{"deal_id": "...", "provider": "...", "budget": "..."}]

    # --- Forecast (step 6) ---
    forecast: dict | None  # carries is_available for the honesty rule
    forecast_acceptable: bool | None
    audience_extended: bool | None  # repair loop tracking

    # --- Approval & Strategy creation (step 7 & 8) ---
    plan_approved: bool | None
    strategy_id: str | None
    strategy_created: bool | None
    product_context: str | None  # e.g. "New running shoe line"

    # --- UI presentation blocks ---
    blocks: list[dict]

    # --- Flow control ---
    stage_cursor: str
    rejected_fields: list[str]
    awaiting: list[str]
    awaiting_choice: str | None       # blocks re-triggering TC-014 after shown once
    validation_errors: list[str]
    # Provider names the trader requested that the platform doesn't carry (TC-014)
    unavailable_requested_channels: list[str]



# Kept so nothing that imported the old name breaks mid-refactor.
PlanningState = PlanningAgentState

