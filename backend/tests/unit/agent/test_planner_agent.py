"""Comprehensive Unit Tests for the Central Planner / Orchestrator Agent.

Validates the Planner Agent's intelligence, state evaluation, routing decisions,
gap detection, conflict resolution, gating, loop-back, and error resilience across all
scenarios defined in docs/Workflow.jpeg and M1_Planning.txt.
"""

from __future__ import annotations

import pytest

from app.agent.nodes.planner import evaluate_state_and_plan, planner_node
from app.agent.state import PlanningAgentState


# --- 1. Basic State & Gap Detection Tests ---


def test_planner_evaluates_empty_state():
    """Empty state should identify missing market as the first prerequisite."""
    state: PlanningAgentState = {}
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "ask"
    assert decision["is_complete"] is False
    assert "Missing target market" in decision["reason"]
    assert len(decision["missing_fields"]) > 0


def test_planner_detects_partial_basics():
    """State with only market should ask for remaining basics (flight dates, durations, budget)."""
    state: PlanningAgentState = {
        "markets": ["GB"],
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "ask"
    assert decision["is_complete"] is False
    assert decision["missing_fields"] is not None


def test_planner_advances_to_validation_when_all_basics_present():
    """When market, flight_dates, durations, and budget are supplied, Planner routes to validate_basics."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "validation_errors": [],
    }
    decision = evaluate_state_and_plan(state)

    # All basics present and no errors -> routes to next step
    assert decision["next_agent"] in ("validate_basics", "select_inventory")
    assert decision["is_complete"] is False


# --- 2. Validation Blockers vs Non-Blocking Warnings ---


def test_planner_halts_on_validation_blocker():
    """A blocking validation error (e.g. past flight dates or unsold market) must route to ask."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2020-01-01", "upper": "2020-01-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "validation_errors": [
            {
                "is_valid": False,
                "severity": "error",
                "code": "flight_dates.in_past",
                "message": "Flight dates are in the past.",
                "stage": "validation",
            }
        ],
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "ask"
    assert decision["is_complete"] is False
    assert len(decision["conflicts"]) == 1
    assert "Flight dates are in the past" in decision["reason"]


def test_planner_does_not_halt_on_non_blocking_warnings():
    """A warning (e.g. currency mismatch) must not block progression to inventory."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "validation_errors": [
            {
                "is_valid": True,
                "severity": "warning",
                "code": "currency.mismatch",
                "message": "Billing in USD for UK market.",
                "stage": "validation",
            }
        ],
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "select_inventory"
    assert decision["is_complete"] is False


# --- 3. Inventory & Dynamic Rate Cards Dispatching ---


def test_planner_dispatches_vishal_for_rate_cards_when_inventory_missing():
    """When basics are valid, Planner dispatches Vishal (select_inventory) for duration-matched rate cards."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["15", "30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "validation_errors": [],
        "selected_deals": [],
        "matched_rate_cards": [],
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "select_inventory"
    assert "Rate Cards" in decision["reason"]
    assert decision["is_complete"] is False


# --- 4. Targeting & Multi-Channel Budget Splitting Dispatching ---


def test_planner_dispatches_kareem_for_targeting_and_budget_split():
    """When rate cards / inventory are ready, Planner dispatches Kareem (collect_targeting)."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "matched_rate_cards": [{"provider": "Prime Video", "cpm": 25.0, "ad_lengths": ["30"]}],
        "targeting_confirmed": False,
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "collect_targeting"
    assert "demographic" in decision["reason"].lower() or "targeting" in decision["reason"].lower()
    assert decision["is_complete"] is False


# --- 5. Audience Suggestion vs Trader Choice Gating ---


def test_planner_dispatches_audience_agent_when_options_missing():
    """When targeting is confirmed, Planner dispatches suggest_audiences to generate 3 options."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "targeting_confirmed": True,
        "audience_options": [],
        "chosen_audience": None,
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "suggest_audiences"
    assert decision["is_complete"] is False


def test_planner_pauses_and_asks_for_audience_selection():
    """When 3 audience options exist but trader has not chosen, Planner pauses and asks trader."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "targeting_confirmed": True,
        "audience_options": [
            {"id": "opt_narrow", "name": "Narrow"},
            {"id": "opt_balanced", "name": "Balanced"},
            {"id": "opt_wide", "name": "Wide"},
        ],
        "chosen_audience": None,
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "ask"
    assert "audience" in decision["reason"].lower()
    assert decision["is_complete"] is False


# --- 6. Forecast & Reach/Frequency Calculation ---


def test_planner_dispatches_forecast_when_audience_is_chosen():
    """When audience profile is selected, Planner dispatches predict_reach."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "targeting_confirmed": True,
        "audience_options": [
            {"id": "opt_narrow", "name": "Narrow"},
            {"id": "opt_balanced", "name": "Balanced"},
        ],
        "chosen_audience": "BALANCED",
        "forecast": None,
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "predict_reach"
    assert "Reach & Frequency" in decision["reason"] or "forecast" in decision["reason"].lower()
    assert decision["is_complete"] is False


# --- 7. Final Plan Delivery ---


def test_planner_delivers_plan_when_all_stages_are_complete():
    """When all fields, inventory, targeting, audience, and forecast are present, Planner delivers the plan."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "targeting_confirmed": True,
        "chosen_audience": "BALANCED",
        "forecast": {
            "reach": 1_250_000,
            "frequency": 1.6,
            "impressions": 2_000_000,
            "cpm": 25.0,
        },
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "deliver_plan"
    assert decision["is_complete"] is True
    assert "verified" in decision["reason"].lower() or "complete" in decision["reason"].lower()


# --- 8. Loop-Back and Trader Correction Scenarios ---


def test_planner_loops_back_when_trader_changes_budget():
    """If a previously completed plan has its forecast invalidated (budget changed), Planner recalculates forecast."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "75000.00",  # Updated budget
        "market_budgets": [{"market": "GB", "budget": "75000.00"}],
        "selected_deals": [{"id": "deal-pv-30s", "provider": "Prime Video", "cpm": 25.0}],
        "targeting_confirmed": True,
        "chosen_audience": "BALANCED",
        "forecast": None,  # Reset by budget update
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "predict_reach"
    assert decision["is_complete"] is False


def test_planner_loops_back_when_trader_resets_inventory():
    """If inventory is reset (e.g. trader switched from Prime Video to Netflix), Planner re-runs select_inventory."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
        "preferred_providers": ["Netflix"],
        "selected_deals": [],  # Reset for new provider
        "matched_rate_cards": [],
    }
    decision = evaluate_state_and_plan(state)

    assert decision["next_agent"] == "select_inventory"
    assert decision["is_complete"] is False


# --- 9. Resilience & Robustness with Malformed or Missing Keys ---


@pytest.mark.parametrize(
    "corrupt_field,value",
    [
        ("markets", None),
        ("market_budgets", []),
        ("market_budgets", None),
        ("durations", None),
        ("flight_dates", None),
        ("validation_errors", None),
        ("selected_deals", None),
        ("audience_options", None),
    ],
)
def test_planner_node_handles_corrupt_or_none_fields_without_raising(corrupt_field, value):
    """Planner must never throw an unhandled AttributeError or KeyError on corrupt/None fields."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "budget_amount": "50000.00",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
    }
    state[corrupt_field] = value

    # Must execute cleanly without exception
    decision = evaluate_state_and_plan(state)
    assert isinstance(decision, dict)
    assert "next_agent" in decision
    assert "reason" in decision


@pytest.mark.asyncio
async def test_planner_node_execution():
    """planner_node async entry point updates stage to 'planner'."""
    state: PlanningAgentState = {
        "markets": ["GB"],
    }
    result = await planner_node(state)

    assert result["current_stage"] == "planner"
