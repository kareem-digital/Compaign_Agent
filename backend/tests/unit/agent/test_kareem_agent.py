"""Comprehensive Unit Tests for Kareem Agent (Targeting Agent).

Tests the 7 targeting dimensions per Strategy Schema v4.0 (Sections 6.8 & 6.10)
and the 6-group UI design from res.png:
1. Default baseline targeting (Nationwide, All Adults, Connected TV).
2. Demographic age cohorts (18-24, 25-34, 35-44, 45-54, 55+).
3. Gender filtering (Female, Male, All).
4. Income / HHI tiers (£35-55k, £55-80k, £80k+).
5. Household composition (Families with children, Couples).
6. Lifestyle & In-market interest affinity tags.
7. Geographic search & replacement rule (London replacing Nationwide).
8. Postal code precision validation (SW1A 1AA).
9. Custom radius proximity minting (20 miles of London).
10. Device rules & Mobile OS guardrails (CONNECTED_TV required for CTV).
"""

from __future__ import annotations

import pytest

from app.agent.nodes.collect_targeting import make_collect_targeting
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp.mock import MockMCPClient


@pytest.fixture
def registry() -> AdvertiserRegistry:
    return AdvertiserRegistry(advertiser_id="adv-kareem-test", mcp=MockMCPClient("adv-kareem-test"))


# --- 1. Default Baseline Targeting Tests ---


@pytest.mark.asyncio
async def test_kareem_applies_baseline_defaults_when_unstated(registry):
    """When no targeting is requested, Kareem applies baseline nationwide targeting with CONNECTED_TV."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Run a CTV campaign in the UK."}],
    }

    result = await node(state)

    assert result["current_stage"] == "targeting"
    assert result["targeting_confirmed"] is True
    # Nationwide default
    assert result["location_include"] == ["GB-NAT"]
    assert any("Nationwide" in g["name"] for g in result["geo_targets"])
    # Connected TV is required for CTV
    assert "CONNECTED_TV" in result["device_types"]
    assert len(result["demographics"]["age_groups"]) > 0


# --- 2. Demographics & Age Cohort Parsing ---


@pytest.mark.asyncio
async def test_kareem_parses_age_cohorts(registry):
    """Kareem normalizes natural language age brackets into structured cohorts."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Target young adults aged 18 to 24 and 25-34."}],
    }

    result = await node(state)

    ages = result["demographics"]["age_groups"]
    assert "18-24" in ages
    assert "25-34" in ages


@pytest.mark.asyncio
async def test_kareem_parses_gender_and_income_tiers(registry):
    """Kareem parses female gender constraint and high household income tiers."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "We want to reach affluent women with high income."}],
    }

    result = await node(state)

    assert result["demographics"]["genders"] == ["Female"]
    assert "£80k+" in result["demographics"]["household_income"]


@pytest.mark.asyncio
async def test_kareem_parses_household_composition(registry):
    """Kareem identifies household composition requirements like families with kids."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Target parents and families with children."}],
    }

    result = await node(state)

    assert "Families with children" in result["demographics"]["household_type"]


@pytest.mark.asyncio
async def test_kareem_parses_lifestyle_and_interest_tags(registry):
    """Kareem extracts interest affinities like runners, health & wellness, and eco-friendly."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [
            {
                "role": "user",
                "content": "Launching our eco-friendly organic running shoe line for health and wellness enthusiasts.",
            }
        ],
    }

    result = await node(state)

    interests = result["demographics"]["interests"]
    assert any("Runners" in i for i in interests)
    assert any("Green" in i or "Environment" in i for i in interests)
    assert any("Health" in i or "Organic" in i for i in interests)


# --- 3. Geographic Engine & The Replacement Rule ---


@pytest.mark.asyncio
async def test_kareem_resolves_city_and_applies_replacement_rule(registry):
    """When a specific city (London) is requested, it replaces the GB Nationwide default."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Target Greater London only."}],
    }

    result = await node(state)

    assert "GB-LND" in result["location_include"]
    assert "GB-NAT" not in result["location_include"]  # Replacement rule in action
    assert any("London" in g["name"] for g in result["geo_targets"])


@pytest.mark.asyncio
async def test_kareem_parses_postcode_precision(registry):
    """Kareem extracts and structures postal code targeting."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Target households in postal codes SW1A 1AA and EC1A."}],
    }

    result = await node(state)

    postcodes = result.get("postcode_targeting")
    assert postcodes is not None
    assert any("SW1A" in p["submitted"] for p in postcodes["resolved"])
    assert any("POST-" in loc for loc in result["location_include"])


@pytest.mark.asyncio
async def test_kareem_parses_custom_radius_proximity(registry):
    """Kareem creates custom radius location structure when distance around a place is requested."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Target people within 20 miles of London."}],
    }

    result = await node(state)

    radius = result.get("custom_radius")
    assert radius is not None
    assert radius["address"] == "London"
    assert radius["radius"] == 20.0
    assert radius["unit"] == "miles"
    assert any("20.0 miles" in g["name"] or "20 miles" in g["name"] for g in result["geo_targets"])


# --- 4. Devices & Brand Safety Exclusions ---


@pytest.mark.asyncio
async def test_kareem_enforces_connected_tv_and_parses_devices(registry):
    """CONNECTED_TV is always included, and Fire TV / Gaming consoles are parsed."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Only run on Smart TVs and Fire TV streaming sticks."}],
    }

    result = await node(state)

    devices = result["device_types"]
    assert "CONNECTED_TV" in devices
    assert "STREAMING_STICK" in devices


@pytest.mark.asyncio
async def test_kareem_parses_brand_safety_rating_exclusions(registry):
    """Kareem captures content exclusions like news, politics, and sensitive content."""
    node = make_collect_targeting(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "messages": [{"role": "user", "content": "Ensure brand safety: exclude news and political content."}],
    }

    result = await node(state)

    exclusions = result["content_rating_exclusions"]
    assert "NEWS_POLITICS" in exclusions
