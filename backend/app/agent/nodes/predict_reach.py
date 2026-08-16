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

**It computes; `deliver_plan` states.** This node used to phrase the forecast
itself, and now that `deliver_plan` runs immediately after and presents the whole
plan, doing both put the same figures in one reply twice. The honesty rule moved
with the prose - see `deliver_plan._forecast_lines`, which is now the only place a
forecast is spoken. What stays here is anything this stage *records*, because no
later stage carries a warning.

The repair loop (too narrow -> widen -> re-forecast) attaches here and applies
to the Amazon portion only. Not built yet; the seam is marked below.
"""

from __future__ import annotations

import logging

from app.agent.gates import record, record_checks, say, stage_notes
from app.agent.nodes.select_inventory import AMAZON_OWNED
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge.registry.models import ValidationResponse
from app.knowledge.registry.validate import check_forecast_shape
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


def make_predict_reach(mcp: MCPClient):
    """Build the node with its MCP client bound."""

    async def predict_reach(state: PlanningAgentState) -> dict:
        tier = state.get("inventory_tier")
        chosen = state.get("chosen_audience") or {}
        budget = _total_budget(state)

        if not tier or not budget:
            missing = "inventory" if not tier else "budget"
            # `asking`: this is the turn's only message, and `deliver_plan` stays
            # quiet with no forecast to summarise, so suppressing a repeat here
            # would end the turn in silence.
            return {
                "current_stage": STAGE,
                "forecast": None,
                **say(
                    state,
                    STAGE,
                    f"I need {missing} settled before I can forecast.",
                    asking=True,
                ),
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

        checks = []

        # A forecast that says reach is unavailable and then supplies one is the
        # fabricated-reach failure mode this node exists to prevent. `_summary`
        # would not speak the number, but a silently contradictory payload means
        # the server's contract has moved, and that has to be visible.
        #
        # Recorded as a warning even though the check calls it an error: it is a
        # problem with VOW's payload, so stopping to ask the trader would demand a
        # fix only VOW can make - and a blocking entry would still be in state next
        # turn, diverting a turn that has nothing wrong with it.
        #
        # Recorded either way, which it was not before: on the third-party path the
        # pass is `forecast.unavailable_ok`, carrying `reach_available: False`, and
        # that is the best evidence there is for "why can you not forecast reach?".
        # It used to be computed and dropped. `record` still drops it - a pass is
        # not spoken - so `record_checks` is the only thing that changes.
        shape = check_forecast_shape(forecast)
        if shape.blocks:
            logger.error("forecast.contract_violation", extra=kv(code=shape.code))
            checks.append(shape.model_copy(update={"severity": "warning"}))
        else:
            checks.append(shape)

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
            # A warning, not a blocker: the fix is to widen the audience and
            # re-forecast, and that edge does not exist yet. Blocking would ask a
            # question the graph cannot act on.
            checks.append(
                ValidationResponse(
                    is_valid=True,
                    severity="warning",
                    code="forecast.below_viability_floor",
                    field="forecast",
                    message=(
                        f"That reach is below the {MIN_VIABLE_REACH:,} I would want to see "
                        f"before committing - a wider audience would deliver more reliably."
                    ),
                    metadata={"reach": reach, "floor": MIN_VIABLE_REACH},
                )
            )

        errors = record(state, STAGE, checks)

        # The numbers are not stated here. `deliver_plan` runs immediately after and
        # presents them inside the whole plan, so speaking them twice in one reply
        # is just noise - the forecast is the last thing *computed*, not the last
        # thing said. What this stage still owns is anything it recorded, because
        # nothing downstream carries a warning.
        return {
            "current_stage": STAGE,
            "stage_cursor": "forecast",
            "forecast": forecast,
            "validation_errors": errors,
            # As in `suggest_audiences`: the UI's only source, and the honesty
            # rule's own evidence has to reach it.
            "validation_checks": record_checks(state, STAGE, checks),
            **say(state, STAGE, stage_notes(STAGE, errors)),
        }

    return predict_reach
