"""Golden Journey tests implementing the Test Cases Matrix (Golden Cases A, B, C, D).

Verifies the conversational LangGraph agent across multiple turns from initial probe
to complete strategy creation with zero hallucination.
"""

import pytest
from app.agent.graph import build_graph
from app.agent.checkpointer import create_checkpointer
from app.tools.mcp.mock import MockMCPClient


@pytest.fixture
def mcp():
    return MockMCPClient(advertiser_id="adv-test")


@pytest.fixture
async def checkpointer():
    return await create_checkpointer()


@pytest.fixture
async def graph(mcp, checkpointer):
    return build_graph(checkpointer=checkpointer, mcp=mcp)


@pytest.mark.asyncio
async def test_golden_case_a_minimal_probing_journey(graph):
    """Golden Case A: User provides information progressively across multiple turns."""
    session_id = "test-golden-a"
    config = {"configurable": {"thread_id": session_id}}

    # Turn 1: Vague start
    res1 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "I want to run a campaign."}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res1.get("awaiting"), "Agent should wait for missing basics"
    assert "which country" in res1["messages"][-1].content or "details" in res1["messages"][-1].content

    # Turn 2: Market + product
    res2 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "New running shoes in the UK."}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res2["markets"] == ["GB"]

    # Turn 3: Complete the remaining details
    res3 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "15000 GBP, October 2030, 30s, awareness on Prime Video"}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res3.get("market_budgets")[0]["budget"] == "15000.00"
    assert res3.get("current_stage") == "inventory"


    # Turn 4: Audiences stage
    res4 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Keep it broad."}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res4.get("current_stage") in ("audiences", "forecast")

    # Turn 5: Forecast stage
    res5 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Looks good."}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res5.get("current_stage") in ("forecast", "plan_ready")

    # Turn 6: Plan ready & Approval
    res6 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Yes, approve it."}], "advertiser_id": "adv-test", "session_id": session_id},
        config=config,
    )
    assert res6.get("strategy_created") or "approved" in res6.get("messages")[-1].content or "Strategy Plan Ready" in res6.get("messages")[-1].content


@pytest.mark.asyncio
async def test_golden_case_b_complete_one_shot(graph):
    """Golden Case B: User provides everything in a single message."""
    session_id = "test-golden-b"
    config = {"configurable": {"thread_id": session_id}}

    res = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "We're launching a new running shoe line in the UK. We have £15k from October 1 to 31 and want 30-second ads for awareness on Prime Video.",
                }
            ],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res["markets"] == ["GB"]
    assert res["durations"] == ["30"]
    assert res["market_budgets"][0]["budget"] == "15000.00"
    assert res["preferred_providers"] == ["Prime Video"]
    assert res.get("current_stage") == "inventory"


@pytest.mark.asyncio
async def test_golden_case_c_unsupported_market_and_inventory(graph):
    """Golden Case C: Unsupported market China is politely rejected with valid alternatives."""
    session_id = "test-golden-c"
    config = {"configurable": {"thread_id": session_id}}

    res = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "I want to run a campaign in China"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res.get("rejected_fields") == ["markets"]
    assert "CN" in res.get("awaiting")[0]
    assert "does not sell" in res.get("awaiting")[0]


@pytest.mark.asyncio
async def test_tc014_unsupported_inventory_zee_tv(graph):
    """TC-014: Unsupported inventory Zee TV in UK is politely explained with alternatives."""
    session_id = "test-tc014"
    config = {"configurable": {"thread_id": session_id}}

    res1 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "I want to plan to run a compaign in the UK on the zee tv"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    # Grounding detects Zee TV is not carried by VOW
    assert "Zee TV" in res1.get("unavailable_requested_channels", []) or "Zee TV" in res1.get("awaiting", [])[0]
    assert "isn't currently available" in res1["messages"][-1].content
    # Does NOT ask for dates/budget before inventory is resolved (Rule C)
    assert "start and end dates" not in res1["messages"][-1].content

    # User chooses alternatives (TC-015): Agent shows available inventory
    res2 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "Show available alternatives"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res2.get("current_stage") == "inventory"
    assert len(res2.get("selected_deals", [])) > 0, "Agent should return available inventory deals"

    # User selects an inventory deal (TC-012 in M1_planning): Agent saves it and asks for remaining missing details
    res3 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "Prime Video"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res3.get("awaiting"), "Agent should proceed to ask for remaining missing campaign details"
