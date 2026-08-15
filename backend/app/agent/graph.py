"""The CTV planning graph.

Four of the thirteen stages in the confirmed v5 flow, with a gate between each:

    START -> extract_fields ---(basics complete?)--> select_inventory
                     |  no                                  |
                     v                                      | (inventory found?)
                    ask -> END                               v
                                                    suggest_audiences
                                                              |  (audience chosen?)
                                                              v
                                                        predict_reach -> END

Gated rather than linear, because pressing on with an incomplete plan produces
confident nonsense: inventory for no market, audiences for no inventory, a
forecast against no budget. When a stage cannot proceed it records what it is
`awaiting`, the router diverts to `ask`, and the turn ends with a question.

The next turn resumes from the top with the trader's answer merged into what
was already known - see `extract_fields`, which accumulates rather than
overwrites. Gating and remembering are the same feature; neither works alone.

Where the remaining pieces attach:

  * **Plan approval** - an `interrupt()` after `predict_reach`, before any node
    that creates a strategy. Everything here is costless, so there is nothing
    to gate yet.
  * **Repair loop** - a conditional edge from `predict_reach` back to
    `suggest_audiences` when reach is below the viability floor.
    `predict_reach` already detects it; only the edge is missing.
  * **Tier fork** - conditional edges out of `select_inventory` for the
    curation-capture path.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.agent.gates import route_one_stage
from app.agent.nodes import (
    ask_for_missing,
    make_extract_fields,
    make_predict_reach,
    make_select_inventory,
    make_suggest_audiences,
    plan_ready,
)
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


def build_graph(checkpointer=None, mcp: MCPClient | None = None, registry=None):
    """Compile the planning graph.

    Args:
        checkpointer: LangGraph checkpointer. Without one the graph still runs
            but keeps no history, so a conversation cannot be continued - and
            gating depends on continuing one.
        mcp: The MCP client the VOW-calling nodes use. Required - there is no
            default, because a silently-mocked client in staging would be worse
            than a startup failure.
        registry: The grounded registry accessor (KNW-02), for the same reason and
            with the same rule. `extract_fields` grounds every value the trader
            gives against it, so a graph built without one would accept a market
            VOW does not sell and only find out at approval. Defaults to one
            built on `mcp`, because there is exactly one correct choice.
    """
    if mcp is None:
        raise ValueError(
            "build_graph requires an MCP client. Use create_mcp_client(advertiser_id)."
        )

    if registry is None:
        # Built here rather than demanded from the caller: it needs nothing `mcp` has not
        # already got, and making every call site assemble it invites one of them to pass
        # None and silently lose grounding.
        registry = AdvertiserRegistry(advertiser_id=mcp.advertiser_id, mcp=mcp)

    graph = StateGraph(PlanningAgentState)

    graph.add_node("extract_fields", make_extract_fields(registry))
    graph.add_node("select_inventory", make_select_inventory(mcp))
    graph.add_node("suggest_audiences", make_suggest_audiences(mcp))
    graph.add_node("predict_reach", make_predict_reach(mcp))
    graph.add_node("plan_ready", plan_ready)
    graph.add_node("ask", ask_for_missing)

    # Extraction runs every turn, so a correction anywhere in the conversation
    # is picked up before the router decides what to do next.
    graph.add_edge(START, "extract_fields")

    # ONE stage per turn. The router reads `stage_cursor` to see how far the
    # conversation has come, and dispatches exactly one step.
    graph.add_conditional_edges(
        "extract_fields",
        route_one_stage,
        {
            "ask": "ask",
            "select_inventory": "select_inventory",
            "suggest_audiences": "suggest_audiences",
            "predict_reach": "predict_reach",
            "plan_ready": "plan_ready",
        },
    )

    # Every stage ends the turn. Nothing chains onward - that is what makes the
    # agent show one thing and wait, instead of running the whole plan before it
    # speaks.
    for node in ("ask", "select_inventory", "suggest_audiences", "predict_reach", "plan_ready"):
        graph.add_edge(node, END)

    logger.info("Planning graph compiled: one stage per turn")
    return graph.compile(checkpointer=checkpointer)
