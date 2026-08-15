"""Node 4 - forecast reach, and be honest when it cannot be forecast.

This node exists as much to refuse as to answer. Reach forecasting is available
for Amazon inventory only. For Netflix and Disney+ the agent reports rate-card
CPM and derived impressions (budget / CPM x 1000) and states plainly that reach
is unavailable and why.

Two rules that follow, both from `VOW_Strategy_Schema_v2.md` section 3 step 6:

  * **Never invent a reach number.** A plausible fabricated figure is worse than
    an admitted gap, because a trader will commit budget against it.
  * **Never sum reach across providers.** There is no cross-platform
    deduplication, so the numbers are not additive.

The repair loop (too narrow -> widen -> re-forecast) attaches here and applies
to the Amazon portion only. Not built yet; the seam is marked below.
"""

from __future__ import annotations

import logging

from app.agent.nodes.select_inventory import AMAZON_OWNED
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.tools.mcp import MCPClient, VowTools

logger = logging.getLogger(__name__)

STAGE = "forecast"

# Below this, the audience is too small to deliver and the repair loop should
# widen it. Placeholder - real threshold is a guardrail value (open question A3).
MIN_VIABLE_REACH = 100_000


def _total_budget(state: PlanningAgentState) -> float:
    return sum(
        float(entry["budget"])
        for entry in (state.get("market_budgets") or [])
        if entry.get("budget")
    )


def _summary(forecast: dict, budget: float, currency: str) -> str:
    if not forecast.get("is_available"):
        return "\n".join(
            [
                "I cannot forecast reach for this plan.",
                "",
                f"{forecast.get('reason', 'Reach data is unavailable for this inventory.')}",
                "",
                f"What I can tell you: at {forecast.get('indicative_cpm')} CPM, "
                f"{budget:,.0f} {currency} buys roughly "
                f"{forecast.get('estimated_impressions', 0):,} impressions.",
                "",
                "That is impressions, not unique people - I have no way to tell you how "
                "many individuals that reaches, and I will not estimate it.",
            ]
        )

    return "\n".join(
        [
            "Forecast for the Amazon portion:",
            "",
            f"- Impressions: {forecast['estimated_impressions']:,}",
            f"- Unique reach: {forecast['estimated_unique_reach']:,} people",
            f"- Average frequency: {forecast['average_frequency']}",
            f"- Indicative CPM: {forecast['indicative_cpm']}",
        ]
    )


def make_predict_reach(mcp: MCPClient):
    """Build the node with its MCP client bound."""

    async def predict_reach(state: PlanningAgentState) -> dict:
        tier = state.get("inventory_tier")
        chosen = state.get("chosen_audience") or {}
        budget = _total_budget(state)
        currency = state.get("primary_currency", "GBP")

        if not tier or not budget:
            missing = "inventory" if not tier else "budget"
            return {
                "current_stage": STAGE,
                "forecast": None,
                "messages": [
                    {
                        "role": "assistant",
                        "content": f"I need {missing} settled before I can forecast.",
                    }
                ],
            }

        effective_cpm = chosen.get("effective_cpm") or chosen.get("cpm_basis")
        if not effective_cpm:
            # No Amazon inventory to price against, so fall back to the
            # cheapest selected deal - which is exactly the 3P case.
            cpms = [float(d["cpm"]) for d in (state.get("selected_deals") or []) if d.get("cpm")]
            effective_cpm = f"{min(cpms):.2f}" if cpms else None

        forecast = await mcp.call_tool(
            VowTools.REACH_FORECAST,
            {
                "inventory_tier": tier,
                "audience_set_id": chosen.get("audience_set_id"),
                "budget": f"{budget:.2f}",
                "effective_cpm": effective_cpm,
                "flight_dates": state.get("flight_dates"),
            },
        )

        errors = list(state.get("validation_errors") or [])
        reach = forecast.get("estimated_unique_reach")

        # Repair-loop seam: when reach is available but too small, the graph
        # should route back to suggest_audiences to widen, then re-forecast.
        # Amazon portion only - there is nothing to repair against for 3P.
        needs_repair = (
            forecast.get("is_available")
            and tier == AMAZON_OWNED
            and reach is not None
            and reach < MIN_VIABLE_REACH
        )
        if needs_repair:
            logger.warning(
                "forecast.below_viability_floor",
                extra=kv(reach=reach, floor=MIN_VIABLE_REACH, tier=tier),
            )
            errors.append(
                f"forecast reach {reach:,} is below the {MIN_VIABLE_REACH:,} viability floor "
                "- widen the audience and re-forecast"
            )

        logger.info(
            "stage.forecast",
            extra=kv(
                tier=tier,
                available=forecast.get("is_available"),
                reach=reach,
                impressions=forecast.get("estimated_impressions"),
                needs_repair=needs_repair,
            ),
        )
        logger.debug("stage.forecast.result", extra=kv(forecast=forecast))

        return {
            "current_stage": STAGE,
            "stage_cursor": "forecast",
            "forecast": forecast,
            "validation_errors": errors,
            "messages": [{"role": "assistant", "content": _summary(forecast, budget, currency)}],
        }

    return predict_reach
