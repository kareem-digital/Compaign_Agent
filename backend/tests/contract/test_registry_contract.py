"""Agreements between modules that no single module's tests can protect.

Three of them, each guarding a place where two files have to say the same thing
and nothing forces them to:

  * **`VowTools` and the mock's tool surface.** Adding a tool name and forgetting
    the mock is the likeliest regression in this area, and it fails at runtime
    rather than at import. `app/tools/mcp/__init__.py` calls reconciling the tool
    list "the whole integration risk of moving to MCP".
  * **The mock's tier literals and the registry's enum.** `app.tools` must not
    import `app.knowledge` - that would invert the layering - so `mock_data.py`
    holds tier strings as literals. One assertion here is cheaper than a shared
    constants module, and keeps the dependency direction clean.
  * **The enums and the schema document.** The values below are transcribed by
    hand from `VOW_Strategy_Schema_v2.md` section 5 lines 469-538. If someone
    "tidies" `KPIEnum.REACH` from `"reach"` to `"REACH"`, this fails - which is
    the point, because that value is in the cross-lane state contract.
"""

import asyncio

from app.knowledge.registry.models import (
    ApprovalStatusEnum,
    AudienceProfileEnum,
    BudgetSplitMethodEnum,
    CurrencyEnum,
    DurationEnum,
    FormatEnum,
    GoalEnum,
    InventoryTierEnum,
    KPIEnum,
)
from app.tools.mcp import VowTools, mock_data
from app.tools.mcp.mock import MockMCPClient


def _served_tool_names() -> set[str]:
    mock = MockMCPClient(advertiser_id="contract-test")
    return {tool["name"] for tool in asyncio.run(mock.list_tools())}


# --- the tool surface --------------------------------------------------------


def test_every_expected_tool_is_served_by_the_mock() -> None:
    """A tool name with no mock behind it fails at runtime, not at import."""
    missing = sorted(set(VowTools.all()) - _served_tool_names())
    assert missing == [], f"VowTools names with no mock handler: {missing}"


def test_the_mock_serves_no_tool_we_do_not_expect() -> None:
    """The other direction: a mock handler nobody named is dead code."""
    extra = sorted(_served_tool_names() - set(VowTools.all()))
    assert extra == [], f"mock serves tools absent from VowTools: {extra}"


def test_vowtools_all_finds_every_declared_constant() -> None:
    """`all()` is derived so a new constant cannot be left out of the check above."""
    assert VowTools.LIST_DEALS in VowTools.all()
    assert VowTools.TARGETING_OPTIONS in VowTools.all()
    assert len(VowTools.all()) == 10


# --- the mock's literals versus the registry's enums ------------------------


def test_the_mocks_tier_literals_match_the_registry_enum() -> None:
    """`mock_data` cannot import InventoryTierEnum without inverting the layering."""
    served = {row["inventory_tier"] for row in mock_data.INVENTORY_SOURCES}
    known = {tier.value for tier in InventoryTierEnum}

    assert served <= known, f"mock serves tiers the registry does not know: {served - known}"


def test_the_forecast_tools_amazon_literal_matches_the_enum() -> None:
    """`MockMCPClient._forecast` compares against the raw string "AMAZON_OWNED".

    If the enum value ever changes, the mock would silently stop forecasting for
    Amazon inventory and every honesty-rule test would still pass.
    """
    mock = MockMCPClient(advertiser_id="contract-test")
    amazon = asyncio.run(
        mock.call_tool(
            VowTools.REACH_FORECAST,
            {
                "inventory_tier": InventoryTierEnum.AMAZON_OWNED.value,
                "budget": "50000",
                "effective_cpm": "21.72",
            },
        )
    )

    assert amazon["is_available"] is True


def test_the_mocks_audience_profiles_match_the_registry_enum() -> None:
    served = {row["profile"] for row in mock_data.AUDIENCE_SUGGESTIONS}
    assert served == {p.value for p in AudienceProfileEnum}


def test_the_mocks_durations_are_all_durations_the_registry_accepts() -> None:
    known = {d.value for d in DurationEnum}
    assert set(mock_data.AD_LENGTHS) <= known

    for deal in mock_data.DEALS:
        assert set(deal["ad_lengths"]) <= known, deal["external_deal_id"]


def test_every_mock_deal_duration_is_advertised_by_filter_properties() -> None:
    """The registry's integrity check enforces this; the mock must not trip it."""
    advertised = set(mock_data.filter_properties()["ad_lengths"])
    for deal in mock_data.DEALS:
        assert set(deal["ad_lengths"]) <= advertised, deal["external_deal_id"]


def test_every_mock_market_has_a_currency_the_registry_bills_in() -> None:
    """Another integrity check the mock must not trip."""
    from app.knowledge.registry.models import CURRENCY_BY_MARKET

    for market in mock_data.MARKETS:
        assert market in CURRENCY_BY_MARKET
        assert CURRENCY_BY_MARKET[market] in {c.value for c in CurrencyEnum}


# --- the enums versus the schema document -----------------------------------
#
# Transcribed by hand from VOW_Strategy_Schema_v2.md section 5, lines 469-538. A
# change to any of these is a change to the cross-lane contract shared with the
# state-and-graph and adaptive-canvas lanes, so it should fail loudly here.

SCHEMA_V2_SECTION_5 = {
    GoalEnum: {"AWARENESS", "CONSIDERATION", "CONVERSION"},
    KPIEnum: {"reach", "frequency", "ctr", "cpc", "cpa", "cpdpv"},
    CurrencyEnum: {"EUR", "GBP", "USD"},
    DurationEnum: {"10", "15", "20", "30"},
    FormatEnum: {"display", "online_video", "streaming_tv", "prime_video"},
    InventoryTierEnum: {
        "AMAZON_OWNED",
        "THIRD_PARTY_PRECURATED",
        "THIRD_PARTY_NEEDS_CURATION",
    },
    AudienceProfileEnum: {"NARROW", "BALANCED", "WIDE"},
    BudgetSplitMethodEnum: {"EVEN_BY_BUDGET", "EVEN_BY_IMPRESSIONS", "CUSTOM"},
    ApprovalStatusEnum: {"PENDING", "APPROVED", "REJECTED"},
}


def test_every_enum_matches_the_schema_document() -> None:
    for enum, documented in SCHEMA_V2_SECTION_5.items():
        assert {member.value for member in enum} == documented, enum.__name__


def test_the_goal_kpi_casing_asymmetry_is_preserved() -> None:
    """Goal is upper, KPI is lower. It looks like a bug and it is the contract.

    `extract_fields` writes {"goal": "AWARENESS", "kpi": "reach"} into
    `PlanningAgentState`, so normalizing either would break the state contract
    the moment the registry is wired into the nodes.
    """
    assert GoalEnum.AWARENESS.value == "AWARENESS"
    assert KPIEnum.REACH.value == "reach"
    assert KPIEnum.FREQUENCY.value == "frequency"


def test_the_nodes_tier_constants_are_still_re_exports() -> None:
    """`suggest_audiences` and `predict_reach` import these from the node.

    They are the enum's values now rather than copies of them, so this no longer
    guards a divergence - it guards the re-export continuing to exist, since two
    other nodes' imports depend on it.
    """
    from app.agent.nodes import select_inventory

    for tier in InventoryTierEnum:
        assert getattr(select_inventory, tier.name) == tier.value
