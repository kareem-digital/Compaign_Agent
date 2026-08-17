"""Golden Journey tests implementing the Test Cases Matrix (Golden Cases A, B, C).

Verifies the conversational LangGraph agent across multiple turns from initial probe
to complete strategy plan delivery with zero hallucination.
"""

import pytest

from app.agent.checkpointer import create_checkpointer
from app.agent.graph import build_graph
from app.tools.mcp.mock import MockMCPClient


@pytest.fixture
def mcp():
    return MockMCPClient(advertiser_id="adv-test")


@pytest.fixture
async def checkpointer():
    return await create_checkpointer()


@pytest.fixture(autouse=True)
def _patch_llm(monkeypatch):
    """Keep golden journey tests deterministic and independent of network LLM availability."""
    monkeypatch.setattr("app.agent.llm.get_llm", lambda: None)
    monkeypatch.setattr("app.agent.llm.get_voice_llm", lambda: None)




@pytest.fixture
async def graph(mcp, checkpointer):
    return build_graph(checkpointer=checkpointer, mcp=mcp)


@pytest.mark.asyncio
async def test_golden_case_a_minimal_probing_journey(graph):
    """Golden Case A: User provides information progressively across multiple turns."""
    session_id = "test-golden-a"
    config = {"configurable": {"thread_id": f"test-user:adv-test:{session_id}"}}

    # Turn 1: Vague start -> Planner & Ask detect missing basics
    res1 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "I want to run a campaign."}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res1.get("awaiting"), "Agent should wait for missing basics"
    last_msg = res1["messages"][-1].content
    assert "country" in last_msg or "market" in last_msg or "Before I can carry on" in last_msg

    # Turn 2: Market + product
    res2 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "New running shoes in the UK."}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res2["markets"] == ["GB"]
    assert res2.get("awaiting"), "Should still ask for remaining dates/budget/durations"

    # Turn 3: Complete remaining details -> Advances to audience options
    res3 = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "15000 GBP, October 2030, 30s, awareness on Prime Video",
                }
            ],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res3.get("market_budgets")[0]["budget"] == "15000.00"
    assert res3.get("current_stage") in ("audiences", "delivered", "inventory")
    assert len(res3.get("audience_options") or []) == 3

    # Turn 4: Pick audience -> Forecasts and delivers plan
    res4 = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "BALANCED"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    assert res4.get("current_stage") in ("delivered", "forecast")
    assert res4.get("forecast") is not None


@pytest.mark.asyncio
async def test_golden_case_b_complete_one_shot(graph):
    """Golden Case B: User provides everything in a single message."""
    session_id = "test-golden-b"
    config = {"configurable": {"thread_id": f"test-user:adv-test:{session_id}"}}

    res = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "We're launching a new running shoe line in the UK. We have £15k from October 1 to 31 2030 and want 30-second ads for awareness on Prime Video.",
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
    # Reaches audiences prompt pause
    assert res.get("current_stage") in ("audiences", "delivered")
    assert len(res.get("audience_options") or []) == 3


@pytest.mark.asyncio
async def test_golden_case_c_unsupported_market_and_inventory(graph):
    """Golden Case C: Unsupported market China is politely rejected with valid alternatives."""
    session_id = "test-golden-c"
    config = {"configurable": {"thread_id": f"test-user:adv-test:{session_id}"}}

    res = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "I want to run a campaign in China"}],
            "advertiser_id": "adv-test",
            "session_id": session_id,
        },
        config=config,
    )
    # Validation errors should contain the unsupported market error
    errors = res.get("validation_errors") or []
    assert any(e.get("code") == "market.unknown" or "CN" in e.get("message", "") for e in errors)
    last_msg = res["messages"][-1].content
    assert "CN" in last_msg or "China" in last_msg or "does not sell" in last_msg
