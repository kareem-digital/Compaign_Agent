"""The three MCP tools the grounded registry ingests.

Added so Vishal's registry (KNW-02) can be dropped into this branch. `registry.ingestion`
calls these three by name and reads specific keys out of them, so the shapes here are taken
from the KNW-02 lane's own fixtures rather than invented.

**Why the shapes are asserted rather than trusted.** A wrong key would not fail loudly - the
mapper would find nothing, the facet would come back empty, and the registry would ground
nothing at all while reporting success. An empty snapshot that says it worked is worse than a
crash, because every claim built on it looks confident.
"""

from __future__ import annotations

import pytest

from app.tools.mcp import VowTools
from app.tools.mcp.mock import MockMCPClient

REQUIRED = (
    VowTools.DEAL_FILTER_PROPERTIES,
    VowTools.INVENTORY_SOURCES,
    VowTools.PRODUCT_CATEGORIES,
)


@pytest.fixture
def mcp() -> MockMCPClient:
    return MockMCPClient(advertiser_id="adv-registry-sources")


# --- the tools exist and governance lets them through -------------------------


@pytest.mark.parametrize("tool", REQUIRED)
async def test_the_tool_is_advertised(tool, mcp):
    """`list_tools()` is what the real integration will be reconciled against, so a tool the
    client can call but does not advertise is a discrepancy waiting to be found later."""
    assert tool in [t["name"] for t in await mcp.list_tools()]


@pytest.mark.parametrize("tool", REQUIRED)
async def test_the_policy_allows_the_tool(tool, mcp):
    """**All three were denied on their first call** - "No matching rules, using default" -
    because `vow_ctv.yaml` listed only the original four. That is the policy working: a tool
    the agent gains has to be allowed on purpose, never by a wildcard. This pins the decision
    so a policy edit cannot silently drop one."""
    result = await mcp.call_tool(tool, {"market": "GB"})

    assert isinstance(result, dict)


# --- deal filter properties: the registry's Step 1 grounding ------------------


async def test_filter_properties_carries_every_key_the_registry_maps(mcp):
    """`_map_basics` reads exactly these. A missing one silently narrows what a brief may say."""
    payload = await mcp.call_tool(VowTools.DEAL_FILTER_PROPERTIES, {})

    for key in ("markets", "currencies", "formats", "ad_lengths", "goals", "kpis"):
        assert payload.get(key), f"{key} is missing or empty"


async def test_the_advertised_lengths_are_a_superset_of_every_deals(mcp):
    """The registry's integrity check requires each deal's `ad_lengths` to be a SUBSET of the
    catalogue's. 10s is advertised though no mock deal sells it - claiming CTV cannot sell a
    10s ad would contradict schema v2 section 3 step 1."""
    catalogue = set((await mcp.call_tool(VowTools.DEAL_FILTER_PROPERTIES, {}))["ad_lengths"])
    deals = (await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"}))["results"]

    for deal in deals:
        assert set(deal["ad_lengths"]) <= catalogue, deal["name"]


async def test_goals_stay_awareness_only(mcp):
    """CTV is an awareness buy - schema v2 fixes it. A second goal here would be offered to a
    trader and then refused by the validator, which is the "option that gets rejected" bug."""
    payload = await mcp.call_tool(VowTools.DEAL_FILTER_PROPERTIES, {})

    assert payload["goals"] == ["AWARENESS"]


# --- inventory sources: provider to tier --------------------------------------


async def test_inventory_sources_uses_the_results_envelope(mcp):
    """`_map_inventory_sources` reads `payload["results"]`. Any other envelope maps to nothing
    and the registry falls back to the most conservative tier for every provider."""
    payload = await mcp.call_tool(VowTools.INVENTORY_SOURCES, {})

    assert "results" in payload
    assert payload["results"]


async def test_every_source_names_a_provider_and_a_tier(mcp):
    rows = (await mcp.call_tool(VowTools.INVENTORY_SOURCES, {}))["results"]

    for row in rows:
        assert row.get("provider")
        assert row.get("inventory_tier")


async def test_all_three_tiers_are_reachable(mcp):
    """The tier fork is the primary branch in the whole flow - whether reach can be forecast at
    all. With only Amazon providers the honesty path would be untestable end to end."""
    tiers = {r["inventory_tier"] for r in (await mcp.call_tool(VowTools.INVENTORY_SOURCES, {}))["results"]}

    assert tiers == {
        "AMAZON_OWNED",
        "THIRD_PARTY_PRECURATED",
        "THIRD_PARTY_NEEDS_CURATION",
    }


async def test_every_dealt_provider_has_a_tier(mcp):
    """A provider we sell but cannot classify would be assumed the fallback tier, which
    silently turns its reach forecast off."""
    sources = {r["provider"] for r in (await mcp.call_tool(VowTools.INVENTORY_SOURCES, {}))["results"]}
    dealt = {d["provider"] for d in (await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"}))["results"]}

    assert dealt <= sources, f"no tier for {dealt - sources}"


# --- product categories: market-scoped ----------------------------------------


async def test_categories_are_scoped_to_the_market(mcp):
    """`GET /contextual-targeting/{market}/product-categories/` is market-scoped, so the same
    call for two markets must not return the same list."""
    gb = (await mcp.call_tool(VowTools.PRODUCT_CATEGORIES, {"market": "GB"}))["results"]
    fr = (await mcp.call_tool(VowTools.PRODUCT_CATEGORIES, {"market": "FR"}))["results"]

    assert [r["id"] for r in gb] != [r["id"] for r in fr]


async def test_category_ids_are_integers(mcp):
    """Schema v2 section 5 declares `product_categories: list[int]`. Strings here would pass
    ingestion and fail at strategy creation, which is the worst place to find out."""
    rows = (await mcp.call_tool(VowTools.PRODUCT_CATEGORIES, {"market": "GB"}))["results"]

    assert rows
    for row in rows:
        assert isinstance(row["id"], int), row


async def test_a_market_we_do_not_sell_returns_nothing_rather_than_guessing(mcp):
    """An optional facet coming back empty degrades; inventing categories for a market VOW
    does not sell would put them in front of a trader."""
    rows = (await mcp.call_tool(VowTools.PRODUCT_CATEGORIES, {"market": "JP"}))["results"]

    assert rows == []


# --- and the originals still work ---------------------------------------------


@pytest.mark.parametrize(
    "tool", [VowTools.LIST_DEALS, VowTools.CTV_RATE_CARD, VowTools.SUGGEST_AUDIENCES]
)
async def test_the_existing_tools_are_untouched(tool, mcp):
    """Three tools were added to a mock four nodes already depend on. This is the regression
    guard on that."""
    assert await mcp.call_tool(tool, {"market": "GB"})
