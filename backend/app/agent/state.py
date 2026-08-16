"""The state carried through the CTV planning graph.

Field names come verbatim from `PlanningAgentState` in
`VOW_Strategy_Schema_v2.md` section 5, which is the cross-lane contract. Only
the fields the current four nodes touch are declared - the remaining ones
(approval, creative, tracking, credit, activation) land with their stages.

Partial by design, not by accident: `scripts/schema_drift.py` reports the gap
so it stays visible rather than being forgotten.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


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

    # How this turn's basics were read: "llm", "patterns", or
    # "patterns_after_llm_failure". Carried so the validation record can say
    # where the values it checked came from - "the model proposed CN and the
    # registry rejected it" is a different audit fact from "a regex read CN".
    # Not in schema v2; it describes how state was produced, not the plan.
    extraction_method: str | None

    # --- Basics (step 1) ---
    strategy_name: str | None
    markets: list[str]  # ISO country codes
    durations: list[str]  # creative durations in seconds, as strings
    primary_currency: str
    goal: str  # fixed AWARENESS for CTV
    kpi: str  # reach or frequency

    # What the trader said, held as said. A budget cannot be keyed to a market
    # before one is known and a flight needs both ends, so the schema-shaped
    # fields below could not hold a half-answer - they dropped it, and the agent
    # then asked for it again. These slots are what makes "already answered"
    # survive across turns.
    # Not in schema v2 yet, same as `awaiting`; the contract should pick all
    # three up at the next revision.
    flight_start: str | None  # ISO YYYY-MM-DD
    flight_end: str | None  # ISO YYYY-MM-DD
    budget_amount: str | None  # decimal string, no symbol

    # Derived from the three above, and only ever whole. Downstream reads these -
    # `predict_reach` sends `flight_dates` to VOW - so a partially filled one
    # must not exist.
    flight_dates: dict | None  # {"lower": "YYYY-MM-DD", "upper": "YYYY-MM-DD"}
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

    # --- Audiences (step 4) ---
    audience_options: list[dict]  # always three: narrow / balanced / wide
    # Which profile the trader picked, as they said it. A raw slot like
    # `budget_amount`: `chosen_audience` is the priced option derived from it, and
    # cannot exist until the options have been fetched. Nothing read a choice at
    # all before this - `suggest_audiences` picked BALANCED itself, so "pick one
    # and I will forecast against it" was a promise the graph could not keep.
    audience_choice: str | None  # NARROW / BALANCED / WIDE
    chosen_audience: dict | None

    # --- Forecast (step 6) ---
    forecast: dict | None  # carries is_available for the honesty rule

    # --- Flow control ---
    # How far down the plan the conversation has got. Distinct from
    # `current_stage`, which `extract_fields` resets every turn: this one only
    # moves forward, and only the stage nodes write it.
    #
    # A record, not a router. Routing is `gates.route_after_*`, which reads
    # `awaiting` and `blocking` - the gated chain re-runs every stage each turn,
    # so nothing needs to remember where it left off to decide what to do next.
    # What the cursor answers is "does the work below this point still describe
    # the current plan?", which is why `extract_fields` rewinds it to None when a
    # value that invalidates downstream work changes. That rewind is the only
    # writer of None, hence the optional type.
    stage_cursor: str | None

    # What the agent is waiting for the trader to supply. Non-empty means the
    # graph stops at the current stage and asks instead of pressing on.
    # Not in schema v2 yet - the adaptive flow needs it, so the contract should
    # pick it up at the next revision.
    awaiting: list[str]

    # Digest of the last thing each stage said, keyed by stage name. The graph
    # re-runs from the top every turn, so without this every stage restates its
    # whole block whatever the trader typed - which is what made the conversation
    # repeat itself verbatim and never progress. See `gates.say`.
    last_said: dict[str, str]

    # What has already been written to the audit log, so a record that would only
    # repeat is suppressed. The same idea and the same shape as `last_said` above,
    # for the same reason - the graph re-runs from the top every turn, so a record
    # emitted unconditionally restates itself whatever the trader typed. Keys and
    # digests, never content, because the checkpointer serializes this.
    #
    #   "constraints" -> the static prompt constraints, emitted once per session
    #   "snapshot"    -> content_hash of the snapshot last stated in full
    #   "input"       -> digest of the last logged (market, durations, missing)
    #   "codes"       -> validation codes as of the last verdict
    #
    # Two nodes write this in one turn, so both must spread rather than replace -
    # LangGraph overwrites a dict value wholesale. See `gates.say`, which has the
    # same constraint on `last_said`.
    # Not in schema v2: it describes what was logged, not the plan.
    audited: dict

    # --- Validation ---
    # Serialized `ValidationResponse`s, each stamped with the `stage` that
    # produced it - not prose. Structured because the conversation has to say
    # what failed, why, and what the registry does support without knowing which
    # field it is looking at; see `gates.record`.
    # Holds warnings as well as blockers, told apart by `severity`.
    validation_errors: list[dict]

    # The same entries with the passes kept: every rule that actually ran, not only
    # the ones with something to say. `validation_errors` cannot hold these -
    # `gates.stage_notes` would speak them - and the UI needs them, because a rule
    # whose input was absent never ran while a rule that passed did, and the two
    # look identical from an empty list. See `gates.record_checks`. Nothing routes
    # on this; `validation_errors` is always a subset of it.
    # Not in schema v2 yet, same as `awaiting` and `last_said`.
    validation_checks: list[dict]

    # --- Grounding provenance ---
    # Which snapshot this turn's grounding was done against: the safe subset of
    # `RegistrySnapshotMeta`, chosen by `GroundedRegistrySnapshot.provenance`.
    # Written by `validate_basics` off the snapshot it is already holding, so it
    # costs no extra MCP call. Absent until a market is named, because the snapshot
    # is market-scoped - and since `extract_fields._merge` never clears `markets`,
    # absence means "nothing has ever been grounded" rather than "not this turn".
    # Not in schema v2 yet.
    registry_provenance: dict | None


# Kept so nothing that imported the old name breaks mid-refactor.
PlanningState = PlanningAgentState
