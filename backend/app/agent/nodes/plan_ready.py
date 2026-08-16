"""The end of the planning conversation, for now.

Reached once inventory, audiences and the forecast are all settled. Says so
rather than looping back through stages that have already run.

**Not currently wired into the graph.** `deliver_plan` occupies this position and
does strictly more: it consolidates the whole plan, repeats outstanding warnings
and uses `gates.say` to stand by rather than restate itself. This module is kept
as the shorter alternative in case the flow ever wants an acknowledgement without
a full summary; if nothing claims it, delete it rather than leaving two nodes
describing the same moment.

Deliberately honest about where the flow stops: plan approval and creating the
strategy in VOW are the next stages of the v5 flow and neither is built. Saying
"the plan is complete" without that caveat would imply a campaign exists.
"""

from __future__ import annotations

import logging

from app.agent.state import PlanningAgentState
from app.core.logging import kv

logger = logging.getLogger(__name__)

STAGE = "plan_ready"


async def plan_ready(state: PlanningAgentState) -> dict:
    """Confirm the plan is assembled, and name what comes next."""
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
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "The plan is complete - inventory, audience and forecast are all "
                    "settled. Approval and creating it in VOW are the next steps, and "
                    "are not built yet. Tell me if you'd like to change anything."
                ),
            }
        ],
    }
