"""The final stage of strategy planning: review and approval.

Reached once inventory, audiences and the forecast are all settled.
Presents the complete strategy summary and handles user approval (TC-060 to TC-065).
"""

from __future__ import annotations

import logging
import uuid

from app.agent.state import PlanningAgentState
from app.core.logging import kv

logger = logging.getLogger(__name__)

STAGE = "plan_ready"


def _format_summary(state: PlanningAgentState) -> str:
    """Format a clean, beautiful strategy plan summary ready for approval."""
    markets = ", ".join(state.get("markets") or ["GB"])
    dates = state.get("flight_dates") or {}
    flight_str = f"{dates.get('lower', 'TBC')} to {dates.get('upper', 'TBC')}"
    
    budgets = state.get("market_budgets") or []
    currency = state.get("primary_currency", "GBP")
    budget_str = f"{budgets[0]['budget']} {currency}" if budgets else "TBC"
    
    product = state.get("product_context") or state.get("strategy_name") or "CTV Campaign"
    durations = ", ".join(f"{d}s" for d in state.get("durations") or ["30"])
    
    deals = state.get("selected_deals") or []
    providers = ", ".join({d.get("provider", "Prime Video") for d in deals}) or "Prime Video"
    
    chosen_aud = state.get("chosen_audience") or {}
    aud_name = chosen_aud.get("name") or chosen_aud.get("profile", "Balanced")
    
    refinement = state.get("audience_refinement")
    if refinement:
        aud_str = f"{aud_name} ({refinement})"
    else:
        aud_str = f"Default {markets} targeting ({aud_name})"
        
    locations = ", ".join(state.get("locations") or [markets])
    
    forecast = state.get("forecast") or {}
    
    lines = [
        "**Strategy Plan Ready**",
        "",
        f"- **Campaign:** {product}",
        f"- **Market:** {markets} ({locations})",
        f"- **Flight Dates:** {flight_str}",
        f"- **Budget:** {budget_str}",
        f"- **Goal / KPI:** Awareness / Reach",
        f"- **Creative Length:** {durations}",
        f"- **Inventory:** {providers}",
        f"- **Audience:** {aud_str}",
        "",
    ]
    
    if forecast.get("is_available"):
        reach = f"~{forecast.get('estimated_unique_reach', 0):,}"
        imps = f"~{forecast.get('estimated_impressions', 0):,}"
        freq = forecast.get("average_frequency", "3.2")
        cpm = forecast.get("indicative_cpm", "£30.51")
        lines += [
            "**Forecast**",
            f"- Reach: {reach} people",
            f"- Impressions: {imps}",
            f"- Average Frequency: {freq}",
            f"- Indicative CPM: {cpm}",
            "",
        ]
    else:
        imps = f"~{forecast.get('estimated_impressions', 0):,}"
        cpm = forecast.get("indicative_cpm", "31.50")
        lines += [
            "**Forecast (3rd-Party)**",
            f"- Impressions: {imps}",
            f"- Indicative CPM: {cpm}",
            "- Unique Reach: Unavailable for third-party inventory",
            "",
        ]
        
    lines.append("Would you like to approve this plan?")
    return "\n".join(lines)


async def plan_ready(state: PlanningAgentState) -> dict:
    """Present the completed plan or confirm strategy creation upon approval."""
    # Check if user already approved
    if state.get("plan_approved"):
        strategy_id = state.get("strategy_id") or f"strat_{uuid.uuid4().hex[:8]}"
        return {
            "current_stage": "approved",
            "strategy_id": strategy_id,
            "strategy_created": True,
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        f"Great! The plan is approved and your strategy has been created successfully "
                        f"(Strategy ID: **{strategy_id}**). The campaign is staged and ready for activation."
                    ),
                }
            ],
        }

    forecast = state.get("forecast") or {}
    logger.info(
        "stage.plan_ready",
        extra=kv(
            tier=state.get("inventory_tier"),
            forecast_available=forecast.get("is_available"),
        ),
    )

    return {
        "current_stage": STAGE,
        "stage_cursor": "plan_ready",
        "messages": [
            {
                "role": "assistant",
                "content": _format_summary(state),
            }
        ],
    }

