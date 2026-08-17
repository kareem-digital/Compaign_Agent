"""Planner / Orchestrator Agent Node (Node 1 - Central Entry & Control Center).

As defined in `docs/Workflow.jpeg` and `M1_Planning.txt`:
- Planner Agent is the entry point for every customer turn.
- Planner understands customer query, loads/evaluates the shared state store.
- Planner decides:
  1. What is missing?
  2. Which specialized agent needs to be called (Emad, Vishal, Kareem, Execution)?
  3. When to ask probing questions vs when to advance.
  4. Loops back after each specialized agent execution to verify completeness.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.gates import (
    NO_AUDIENCE_CHOICE,
    NO_INVENTORY,
    NO_TARGETING_DECISION,
    blocking,
    missing_basics,
)
from app.agent.state import PlanningAgentState
from app.core.logging import kv

logger = logging.getLogger(__name__)

STAGE = "planner"


def evaluate_state_and_plan(state: PlanningAgentState) -> dict[str, Any]:
    """Analyze the shared state store and determine orchestration decisions.

    Returns a decision dict with:
    - `next_agent`: The next node/agent to execute
    - `missing_fields`: Unfulfilled basic requirements
    - `conflicts`: Blocking validation failures
    - `is_complete`: Whether all requirements are met for campaign delivery
    """
    conflicts = blocking(state)
    missing = missing_basics(state)
    awaiting = state.get("awaiting") or []
    
    markets = state.get("markets") or []
    flight_dates = state.get("flight_dates")
    durations = state.get("durations") or []
    budget = state.get("budget_amount") or (state.get("market_budgets") and state.get("market_budgets")[0].get("budget"))
    
    basics_complete = bool(markets and flight_dates and durations and budget and not missing and not conflicts)
    
    selected_deals = state.get("selected_deals") or []
    matched_rate_cards = state.get("matched_rate_cards") or []
    inventory_complete = bool(selected_deals or matched_rate_cards)
    
    targeting_confirmed = bool(state.get("targeting_confirmed", False))
    chosen_audience = state.get("chosen_audience") or state.get("audience_choice")
    forecast = state.get("forecast")
    
    # 1. Check if Basic Details are complete (Emad Agent)
    if not basics_complete:
        if not markets:
            # Need market first to ground against registry
            return {
                "next_agent": "ask",
                "reason": "Missing target market for registry grounding",
                "missing_fields": missing,
                "conflicts": conflicts,
                "is_complete": False,
            }
        if conflicts:
            # Validation blocker needs user resolution
            return {
                "next_agent": "ask",
                "reason": f"Validation blocker detected: {conflicts[0].get('message')}",
                "missing_fields": missing,
                "conflicts": conflicts,
                "is_complete": False,
            }
        if missing or awaiting:
            return {
                "next_agent": "ask",
                "reason": "Basic campaign parameters incomplete",
                "missing_fields": missing or awaiting,
                "conflicts": conflicts,
                "is_complete": False,
            }
        return {
            "next_agent": "validate_basics",
            "reason": "Validate basic details against registry snapshot",
            "missing_fields": [],
            "conflicts": [],
            "is_complete": False,
        }

    # 2. Check if CTV Inventory / Rate Cards are required & complete (Vishal Agent)
    if not inventory_complete:
        return {
            "next_agent": "select_inventory",
            "reason": "Fetch duration-matched Rate Cards and CTV inventory",
            "missing_fields": [],
            "conflicts": [],
            "is_complete": False,
        }

    # 3. Check if Targeting is needed & complete (Kareem Agent)
    if not targeting_confirmed:
        return {
            "next_agent": "collect_targeting",
            "reason": "Collect demographic targeting, geos, and dynamic budget split",
            "missing_fields": [],
            "conflicts": [],
            "is_complete": False,
        }

    # 4. Check Audience Selection
    if not chosen_audience:
        if not state.get("audience_options"):
            return {
                "next_agent": "suggest_audiences",
                "reason": "Suggest audience profiles (Narrow, Balanced, Wide)",
                "missing_fields": [],
                "conflicts": [],
                "is_complete": False,
            }
        return {
            "next_agent": "ask",
            "reason": "Waiting for user audience profile choice",
            "missing_fields": [NO_AUDIENCE_CHOICE],
            "conflicts": [],
            "is_complete": False,
        }

    # 5. Check Reach & Frequency Forecast
    if not forecast:
        return {
            "next_agent": "predict_reach",
            "reason": "Compute projected Reach & Frequency based on duration rate and budget",
            "missing_fields": [],
            "conflicts": [],
            "is_complete": False,
        }

    # 6. Everything Complete -> Deliver Plan / Campaign Setup
    return {
        "next_agent": "deliver_plan",
        "reason": "All required campaign parameters collected and verified",
        "missing_fields": [],
        "conflicts": [],
        "is_complete": True,
    }


async def planner_node(state: PlanningAgentState) -> dict[str, Any]:
    """Planner Agent execution node.

    Orchestrates the workflow by evaluating state completeness and setting
    orchestration metadata.
    """
    decision = evaluate_state_and_plan(state)
    
    logger.info(
        "planner.decision",
        extra=kv(
            next_agent=decision["next_agent"],
            reason=decision["reason"],
            is_complete=decision["is_complete"],
            missing_count=len(decision["missing_fields"]),
            conflict_count=len(decision["conflicts"]),
        ),
    )
    
    return {
        "current_stage": STAGE,
    }
