"""What each stage needs before the next one may run.

The planning flow is a sequence of gates, not a conveyor belt. If the basics
are incomplete, looking up inventory is premature; if no inventory was found,
suggesting audiences for it is meaningless; if no audience was chosen, there is
nothing to forecast against.

So each gated node records what it is `awaiting`, and a router sends the graph
to `ask` instead of onward. The turn ends there, the trader answers, and the
next turn resumes from the top with the answer merged in.

Requirements are described in the trader's language, not the schema's, because
these strings end up in the question the agent asks.
"""

from __future__ import annotations

from app.agent.state import PlanningAgentState

# Named, because `extract_fields` has to recognise this exact label to swap it out: a flight
# that was dropped for being in the past is missing, so the gate reports it - but reporting it
# as "the start and end dates" asks the trader for dates they know they just gave. Two copies
# of the string would disagree the first time one was reworded.
FLIGHT = "the start and end dates"

# Everything the flow's first stage must have before inventory lookup. This is
# "Basics" in the confirmed v5 flow, and the flow treats it as all-or-nothing.
BASICS = (
    ("markets", "which country the campaign runs in"),
    ("flight_dates", FLIGHT),
    ("durations", "the creative durations - 10, 15, 20 or 30 seconds"),
    ("market_budgets", "the budget"),
)

NO_INVENTORY = "no CTV inventory matched - a different market or set of durations"
NO_AUDIENCE = "an audience to plan against"


def missing_basics(state: PlanningAgentState) -> list[str]:
    """Human-readable labels for whichever basics are still absent."""
    return [label for key, label in BASICS if not state.get(key)]


# --- routers ---------------------------------------------------------------
#
# LangGraph routers may read state but not write it, so the nodes set
# `awaiting` and these only decide where to go next.


def route_after_basics(state: PlanningAgentState) -> str:
    return "ask" if state.get("awaiting") else "select_inventory"


def route_after_inventory(state: PlanningAgentState) -> str:
    return "ask" if state.get("awaiting") else "suggest_audiences"


def route_after_audiences(state: PlanningAgentState) -> str:
    return "ask" if state.get("awaiting") else "predict_reach"


# --- one stage per turn ------------------------------------------------------

# Where to go next, given where the conversation has already reached. `None`
# means no stage has run yet, so the basics were just completed.
_NEXT_STAGE = {
    None: "select_inventory",
    "basics": "select_inventory",
    "inventory": "suggest_audiences",
    "audiences": "predict_reach",
    "forecast": "plan_ready",
    "concluded": "ask",
}


def route_one_stage(state: PlanningAgentState) -> str:
    """One stage per turn.

    The agent shows the trader something new each turn and waits, rather than
    fetching inventory, generating audiences and forecasting before it says
    anything. Each turn is a step they can react to.

    Anything still outstanding in the basics takes priority: there is no point
    looking up inventory for a market we do not have.
    """
    if state.get("awaiting"):
        return "ask"
    return _NEXT_STAGE.get(state.get("stage_cursor"), "plan_ready")
