"""The CTV planning graph.

Five of the thirteen stages in the confirmed v5 flow, with a gate between each and
a grounding check before any of them:

  START -> extract_fields --(a market yet?)--> validate_basics --(grounded & complete?)--> select_inventory
                  |  no                               |  no                                     |
                  v                                   v                          (inventory found?)
                 ask -> END                          ask -> END                                  v
                                                                                   suggest_audiences
                                                          (audience chosen?)  no  /        |  yes
                                                                            END <-         v
                                                                                     predict_reach
                                                                                             |
                                                                                             v
                                                                                     deliver_plan -> END

Gated rather than linear, because pressing on with an incomplete or ungrounded
plan produces confident nonsense: inventory for no market, audiences for no
inventory, a forecast against no budget - or a whole plan built on a duration VOW
does not sell, which only fails at approval. When a stage cannot proceed it
records what it is `awaiting` or what failed validation, the router diverts to
`ask`, and the turn ends with **one** question.

The next turn resumes from the top with the trader's answer merged into what
was already known - see `extract_fields`, which accumulates rather than
overwrites. Gating and remembering are the same feature; neither works alone.

That re-run is also why validation needs no bookkeeping: every stage recomputes
its own outcomes each turn (`gates.record`), so a corrected value stops blocking
because nothing re-emits its error, not because anything cleared it.

It is also why every stage speaks through `gates.say`. Re-running the whole graph
per turn means a stage that speaks unconditionally restates its block whatever the
trader typed, and the conversation loops: a complete brief once produced a
byte-identical reply four turns running, with no way to reach a finished plan.
`say` keeps a stage quiet when it would only repeat itself - except when the stage
*is* asking, because an unanswered question has to be asked again.

The one genuine wait-for-the-human step is the audience choice. `suggest_audiences`
lists the three options and stops; `extract_fields` reads the pick on the next turn;
and only then does the flow forecast and deliver. Everything up to that point is
inference the trader can correct, so nothing else needs their say-so.

Where the remaining pieces attach:

  * **Plan approval** - an `interrupt()` in `deliver_plan`, before any node that
    creates a strategy. Everything here is costless, so there is nothing to gate
    yet - a gate in front of an action that does not exist would be theatre.
  * **Repair loop** - a conditional edge from `predict_reach` back to
    `suggest_audiences` when reach is below the viability floor.
    `predict_reach` already detects it; only the edge is missing, and it is
    cheaper now that the audience is a real input to re-ask for.
  * **Tier fork** - conditional edges out of `select_inventory` for the
    curation-capture path. Three pieces, in this order: a
    `curation_requirements` slot on the state (schema v2 section 5, line 749), a
    `capture_curation_requirements` node to fill it (section 6, line 799), and
    only then the registry's `validate_deal_selection` as the gate that routes
    to it. Wiring the gate first would stop every plan carrying Disney+
    inventory at a question nothing can answer.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.gates import (
    route_after_audiences,
    route_after_basics,
    route_after_inventory,
    route_after_targeting,
    route_after_validation,
)
from app.agent.nodes import (
    ask_for_missing,
    deliver_plan,
    extract_fields,
    make_collect_targeting,
    make_predict_reach,
    make_select_inventory,
    make_suggest_audiences,
    make_validate_basics,
    planner_node,
)
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp import MCPClient


def build_graph(
    checkpointer=None,
    mcp: MCPClient | None = None,
    registry: AdvertiserRegistry | None = None,
):
    """Compile the planning graph.

    Args:
        checkpointer: LangGraph checkpointer. Without one the graph still runs
            but keeps no history, so a conversation cannot be continued - and
            gating depends on continuing one.
        mcp: The MCP client the forecast node uses. Required - there is no
            default, because a silently-mocked client in staging would be worse
            than a startup failure.
        registry: Grounded reference data, advertiser-bound. Defaults to one
            built on `mcp` rather than being required, because the two are
            always the same advertiser and making every caller construct both
            invites them to diverge. Pass it explicitly to share a store.
    """
    if mcp is None:
        raise ValueError(
            "build_graph requires an MCP client. Use create_mcp_client(advertiser_id)."
        )

    # Deals, prices and audience profiles now come from here rather than from raw
    # payloads read inside the nodes, so the values the agent states are grounded
    # in one validated snapshot instead of four independent reads.
    registry = registry or AdvertiserRegistry(mcp.advertiser_id, mcp)

    graph = StateGraph(PlanningAgentState)

    graph.add_node("extract_fields", extract_fields)
    graph.add_node("planner", planner_node)
    graph.add_node("validate_basics", make_validate_basics(registry))
    graph.add_node("select_inventory", make_select_inventory(registry))
    graph.add_node("collect_targeting", make_collect_targeting(registry, mcp))
    graph.add_node("suggest_audiences", make_suggest_audiences(registry))
    graph.add_node("predict_reach", make_predict_reach(mcp))
    graph.add_node("deliver_plan", deliver_plan)
    graph.add_node("ask", ask_for_missing)

    # Extraction runs every turn, so a correction anywhere in the conversation
    # is picked up before the router decides what to do next.
    graph.add_edge(START, "extract_fields")

    graph.add_conditional_edges(
        "extract_fields", route_after_basics, {"ask": "ask", "validate_basics": "validate_basics"}
    )
    # Grounding runs as soon as there is a market to ground against, not once the
    # basics are complete - a value is checked on the turn it arrives, and this
    # node skips the rules whose inputs have not. Everything past this edge plans
    # against values VOW has confirmed it sells.
    graph.add_conditional_edges(
        "validate_basics",
        route_after_validation,
        {"ask": "ask", "select_inventory": "select_inventory"},
    )
    graph.add_conditional_edges(
        "select_inventory",
        route_after_inventory,
        {"ask": "ask", "collect_targeting": "collect_targeting", "end": END},
    )
    graph.add_conditional_edges(
        "collect_targeting",
        route_after_targeting,
        {"ask": "ask", "suggest_audiences": "suggest_audiences", "end": END},
    )
    graph.add_conditional_edges(
        "suggest_audiences",
        route_after_audiences,
        # "end" is the waiting-for-a-choice path, and it is the flow's one real
        # pause for the trader. The node has just listed the three options and
        # asked which to use, so `ask` would only append a vaguer duplicate - the
        # same reasoning as the inventory dead end above.
        {"ask": "ask", "predict_reach": "predict_reach", "end": END},
    )

    # A forecast is the last thing computed, not the last thing said. `deliver_plan`
    # consolidates it so the agreed plan is one message rather than four turns of
    # scrollback.
    graph.add_edge("predict_reach", "deliver_plan")
    graph.add_edge("deliver_plan", END)
    graph.add_edge("ask", END)

    return graph.compile(checkpointer=checkpointer)
