"""Comprehensive Unit Tests for Vishal Agent (CTV Inventory Agent).

Tests the dynamic duration rate card matching, platform filtering, inventory tier
determination, alternatives discovery, and dead-end guidance per docs/Workflow.jpeg and M1_Planning.txt.
"""

from __future__ import annotations

import pytest

from app.agent.gates import NO_INVENTORY
from app.agent.nodes.select_inventory import (
    AMAZON_OWNED,
    THIRD_PARTY_PRECURATED,
    make_select_inventory,
)
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp.mock import MockMCPClient


@pytest.fixture
def registry() -> AdvertiserRegistry:
    return AdvertiserRegistry(advertiser_id="adv-vishal-test", mcp=MockMCPClient("adv-vishal-test"))


# --- 1. Dynamic Duration Rate Card Matching Tests ---


@pytest.mark.asyncio
async def test_vishal_matches_duration_rate_cards(registry):
    """Vishal agent matches rate cards compatible with requested 30s creative length."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["30"],
        "primary_currency": "GBP",
    }

    result = await node(state)

    assert result["current_stage"] == "inventory"
    assert result["inventory_type"] == "RATE_CARD"
    assert len(result["matched_rate_cards"]) > 0
    # Verify all matched rate cards support 30s duration
    for rc in result["matched_rate_cards"]:
        assert "30" in rc["ad_lengths"]
        assert "30" in rc["matched_durations"]


@pytest.mark.asyncio
async def test_vishal_matches_multiple_durations(registry):
    """Vishal agent matches rate cards when multiple durations (15s and 30s) are specified."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["15", "30"],
    }

    result = await node(state)

    assert len(result["selected_deals"]) > 0
    for deal in result["selected_deals"]:
        assert any(d in deal["ad_lengths"] for d in ["15", "30"])


# --- 2. Platform Filtering & Tier Classification ---


@pytest.mark.asyncio
async def test_vishal_filters_to_prime_video_and_classifies_amazon_tier(registry):
    """When Prime Video is requested, Vishal narrows inventory to Prime Video with AMAZON_OWNED tier."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["30"],
        "preferred_providers": ["Prime Video"],
    }

    result = await node(state)

    assert len(result["selected_deals"]) > 0
    for deal in result["selected_deals"]:
        assert deal["provider"] == "Prime Video"
    assert result["inventory_tier"] == AMAZON_OWNED
    # Verify alternatives are populated with other UK CTV providers
    assert len(result["inventory_alternatives"]) > 0
    assert any("Netflix" in p or "Disney" in p for p in result["inventory_alternatives"])


@pytest.mark.asyncio
async def test_vishal_returns_all_platforms_when_unspecified(registry):
    """When no provider is preferred, Vishal returns deals across all carried platforms in that market."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["30"],
        "preferred_providers": [],
    }

    result = await node(state)

    providers = {d["provider"] for d in result["selected_deals"]}
    assert len(providers) >= 2


# --- 3. Alternatives & Dead-End Handling ---


@pytest.mark.asyncio
async def test_vishal_handles_unsupported_provider_in_market(registry):
    """When a provider is not carried in the market, Vishal gives clear alternatives."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["30"],
        "preferred_providers": ["Hulu"],  # Hulu is US only in mock
    }

    result = await node(state)

    assert len(result["selected_deals"]) == 0
    assert result.get("awaiting") == [NO_INVENTORY]
    message = result["messages"][0]["content"]
    assert "Hulu" in message or "not carry" in message or "Available" in message


@pytest.mark.asyncio
async def test_vishal_handles_missing_market_defensively(registry):
    """When market is missing, Vishal stops defensively and asks for basics."""
    node = make_select_inventory(registry)
    state: PlanningAgentState = {
        "markets": [],
        "durations": ["30"],
    }

    result = await node(state)

    assert result["selected_deals"] == []
    assert len(result.get("awaiting", [])) > 0
