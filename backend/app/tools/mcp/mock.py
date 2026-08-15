"""A mock MCP server, in-process.

Returns VOW-shaped payloads so nodes are exercised against realistic structures
rather than invented ones. Values are lifted from the documented examples:
Prime Video ROS at 18.22 vs Action at 22.07 (the genre-upsell case in
`VOW_Strategy_Schema_v2.md` section 2.3), deal IDs in VOW's `EXT...` form, and
one provider per inventory tier so the three-tier fork is actually reachable.

Deliberately covers all three tiers, because the interesting behaviour is the
honesty rule: Amazon inventory forecasts, third-party inventory does not.

Test affordances:
    calls            every (tool, arguments) pair, in order
    fail_times       raise MCPTransientError on the first N calls
    unknown_tool     raise MCPToolNotFoundError for an unmapped name (default)
"""

from __future__ import annotations

import logging

from app.core.exceptions import MCPToolNotFoundError, MCPTransientError
from app.tools.mcp import VowTools
from app.tools.mcp.client import MCPClient

logger = logging.getLogger(__name__)


# --- canned data -------------------------------------------------------------

_DEALS = [
    {
        "external_deal_id": "EXTQ5",
        "name": "Prime Video | Run of Service | {market} - 15, 30",
        "provider": "Prime Video",
        "deal_type": "Private Auction",
        "deal_price_amount": "18.22",
        "genre": None,
        "ad_lengths": ["15", "30"],
        "devices": ["TV"],
    },
    {
        "external_deal_id": "EXT7P75718S8MNR",
        "name": "Prime Video | Action | {market} - 15, 30",
        "provider": "Prime Video",
        "deal_type": "Private Auction",
        "deal_price_amount": "22.07",
        "genre": "Action",
        "ad_lengths": ["15", "30"],
        "devices": ["TV"],
    },
    {
        "external_deal_id": "EXTNFLX0012",
        "name": "Netflix | Standard with ads | {market} - 30",
        "provider": "Netflix",
        "deal_type": "Programmatic Guaranteed",
        "deal_price_amount": "31.50",
        "genre": None,
        "ad_lengths": ["30"],
        "devices": ["TV"],
    },
    {
        "external_deal_id": "EXTDSNY0007",
        "name": "Disney+ | Rate card | {market} - 15, 30",
        "provider": "Disney+",
        "deal_type": "Preferred Deals",
        "deal_price_amount": "34.00",
        "genre": None,
        "ad_lengths": ["15", "30"],
        "devices": ["TV"],
    },
]

# See `_deals` - a demo lever so the third-party path is reachable, not a real
# availability fact.
_MARKETS_WITHOUT_AMAZON = {"FR"}

_RATE_CARD = {
    "channels": [
        {
            "name": "Prime Video",
            "durations": [
                {"duration": "15", "cpm": "18.22"},
                {"duration": "30", "cpm": "25.00"},
            ],
        },
        {"name": "Netflix", "durations": [{"duration": "30", "cpm": "31.50"}]},
        {
            "name": "Disney+",
            "durations": [
                {"duration": "15", "cpm": "29.00"},
                {"duration": "30", "cpm": "34.00"},
            ],
        },
    ]
}

# Three profiles, mandatory. Narrow is smaller AND dearer - the fee stacks on
# the deal CPM, which is the point traders most often miss.
_AUDIENCE_SUGGESTIONS = [
    {
        "audience_set_id": "aud-narrow-0001",
        "name": "In-market: premium streaming, high intent",
        "profile": "NARROW",
        "vcpm_fee": "3.50",
        "segment_count": 6,
        "estimated_size": 1_200_000,
    },
    {
        "audience_set_id": "aud-balanced-0001",
        "name": "Lifestyle: entertainment enthusiasts 25-54",
        "profile": "BALANCED",
        "vcpm_fee": "2.00",
        "segment_count": 14,
        "estimated_size": 4_800_000,
    },
    {
        "audience_set_id": "aud-wide-0001",
        "name": "Broad demographic: adults 18+",
        "profile": "WIDE",
        "vcpm_fee": "0.85",
        "segment_count": 31,
        "estimated_size": 15_400_000,
    },
]


# --- what the grounded registry ingests --------------------------------------
#
# Taken from the KNW-02 lane's own fixtures rather than invented, so the registry ingests the
# shape it was written against. Getting a key wrong here would not fail loudly: a facet would
# come back empty and the registry would quietly ground nothing, which is worse than a crash.

# The catalogue's own shape - `GET /deals/filter-properties/`. This is the registry's
# grounding source for Step 1: the markets, durations, formats and goals a brief may
# legitimately name come from here rather than from constants in our nodes.
#
# `ad_lengths` carries 10s deliberately even though no mock deal sells it. The registry's
# integrity check requires every deal's lengths to be a SUBSET of this, not equal to it -
# and claiming CTV cannot sell a 10s ad would contradict schema v2 section 3 step 1.
_AD_LENGTHS = ["10", "15", "20", "30"]

_FILTER_PROPERTIES = {
    "markets": ["DE", "FR", "GB", "US"],
    "currencies": ["EUR", "GBP", "USD"],
    "formats": ["streaming_tv", "prime_video"],
    "ad_lengths": list(_AD_LENGTHS),
    "genres": sorted({d["genre"] for d in _DEALS if d["genre"]}),
    "goals": ["AWARENESS"],
    "kpis": ["reach", "frequency"],
}

# Provider to tier, from the server rather than from a table in our code. This is what lets
# `select_inventory.classify_tier` stop being a lookup we maintain.
#
# **The tier strings are literals on purpose.** `app.tools` must not import from
# `app.knowledge`, so `InventoryTierEnum` cannot be referenced here; the KNW-02 lane's
# contract test is what asserts these equal the enum.
_INVENTORY_SOURCES = [
    {"provider": "Prime Video", "inventory_tier": "AMAZON_OWNED"},
    {"provider": "Netflix", "inventory_tier": "THIRD_PARTY_PRECURATED"},
    {"provider": "Hulu", "inventory_tier": "THIRD_PARTY_PRECURATED"},
    {"provider": "Disney+", "inventory_tier": "THIRD_PARTY_NEEDS_CURATION"},
]

# Keyed by market, because `GET /contextual-targeting/{market}/product-categories/` is
# market-scoped. IDs are ints - schema v2 section 5 declares `product_categories: list[int]`.
_PRODUCT_CATEGORIES = {
    "GB": [
        {"id": 101, "name": "Automotive"},
        {"id": 102, "name": "Consumer Electronics"},
        {"id": 103, "name": "Financial Services"},
        {"id": 104, "name": "Entertainment & Media"},
        {"id": 105, "name": "Retail & E-commerce"},
        {"id": 106, "name": "Travel & Hospitality"},
    ],
    "US": [
        {"id": 101, "name": "Automotive"},
        {"id": 102, "name": "Consumer Electronics"},
        {"id": 103, "name": "Financial Services"},
        {"id": 105, "name": "Retail & E-commerce"},
        {"id": 107, "name": "Food & Beverage"},
    ],
    "DE": [
        {"id": 101, "name": "Automotive"},
        {"id": 102, "name": "Consumer Electronics"},
        {"id": 106, "name": "Travel & Hospitality"},
    ],
    "FR": [
        {"id": 104, "name": "Entertainment & Media"},
        {"id": 106, "name": "Travel & Hospitality"},
    ],
}

# Targeting values, market-scoped where the platform's are. `data/targeting_types.json`
# declares which tool supplies each type, so these two serve all five declared types between
# them - `location` reads locations, the other four read targeting options by key.
_LOCATIONS = {
    "GB": [
        {"id": "GB-LND", "name": "Greater London"},
        {"id": "GB-WMD", "name": "West Midlands"},
        {"id": "GB-SCT", "name": "Scotland"},
        {"id": "GB-NAT", "name": "United Kingdom - Nationwide"},
    ],
    "US": [
        {"id": "US-501", "name": "New York DMA"},
        {"id": "US-803", "name": "Los Angeles DMA"},
        {"id": "US-602", "name": "Chicago DMA"},
        {"id": "US-NAT", "name": "United States - Nationwide"},
    ],
    "DE": [
        {"id": "DE-BY", "name": "Bavaria"},
        {"id": "DE-NW", "name": "North Rhine-Westphalia"},
        {"id": "DE-BE", "name": "Berlin"},
        {"id": "DE-NAT", "name": "Germany - Nationwide"},
    ],
    "FR": [
        {"id": "FR-IDF", "name": "Ile-de-France"},
        {"id": "FR-ARA", "name": "Auvergne-Rhone-Alpes"},
        {"id": "FR-NAT", "name": "France - Nationwide"},
    ],
}

_TARGETING_OPTIONS = {
    "instream_position": [
        {"id": "PRE_ROLL", "label": "Pre-roll"},
        {"id": "MID_ROLL", "label": "Mid-roll"},
        {"id": "POST_ROLL", "label": "Post-roll"},
    ],
    "content_category_exclusion": [
        {"id": "NEWS_POLITICS", "label": "News & Politics"},
        {"id": "SENSITIVE", "label": "Sensitive Content"},
        {"id": "VIOLENCE", "label": "Terrorism & Violence"},
        {"id": "GAMBLING", "label": "Gambling"},
    ],
    "device_type": [
        {"id": "CONNECTED_TV", "label": "Connected TV (Smart TV)"},
        {"id": "STREAMING_STICK", "label": "Streaming Stick / Set-Top Box"},
        {"id": "GAMES_CONSOLE", "label": "Games Console"},
    ],
    "mobile_environment": [
        {"id": "IN_APP", "label": "In-App"},
        {"id": "MOBILE_WEB", "label": "Mobile Web"},
    ],
}

# Names already taken, so `registry.validate` can answer "is this strategy name free?"
# without the check being a stub that always says yes.
_TAKEN_STRATEGY_NAMES = {"CTV GB 2026-10", "Autumn Push"}


class MockMCPClient(MCPClient):
    """In-process stand-in for VOW's MCP server."""

    def __init__(self, advertiser_id: str, fail_times: int = 0, **kwargs):
        super().__init__(advertiser_id=advertiser_id, **kwargs)
        self.calls: list[tuple[str, dict]] = []
        self._fail_times = fail_times

    async def _list_tools_raw(self) -> list[dict]:
        self.calls.append(("list_tools", {}))
        return [
            {"name": VowTools.LIST_DEALS, "description": "Available deals for a market and format"},
            {
                "name": VowTools.CTV_RATE_CARD,
                "description": "CTV rate card: channels, durations, CPMs",
            },
            {
                "name": VowTools.SUGGEST_AUDIENCES,
                "description": "Suggest audience sets from a brief",
            },
            {
                "name": VowTools.REACH_FORECAST,
                "description": "Reach forecast (Amazon inventory only)",
            },
            {
                "name": VowTools.DEAL_FILTER_PROPERTIES,
                "description": "The catalogue's own shape: markets, durations, formats, goals",
            },
            {
                "name": VowTools.INVENTORY_SOURCES,
                "description": "Provider to inventory tier",
            },
            {
                "name": VowTools.PRODUCT_CATEGORIES,
                "description": "Contextual product categories for a market",
            },
            {"name": VowTools.LOCATIONS, "description": "Targetable locations for a market"},
            {
                "name": VowTools.TARGETING_OPTIONS,
                "description": "Values for one declared targeting type",
            },
            {
                "name": VowTools.CHECK_STRATEGY_NAME,
                "description": "Is a strategy name still free?",
            },
        ]

    async def _call_tool_raw(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))

        if self._fail_times > 0:
            self._fail_times -= 1
            raise MCPTransientError("mock transient failure", tool=name)

        if name == VowTools.LIST_DEALS:
            return self._deals(arguments)
        if name == VowTools.CTV_RATE_CARD:
            return dict(_RATE_CARD)
        if name == VowTools.SUGGEST_AUDIENCES:
            return {"suggestions": [dict(a) for a in _AUDIENCE_SUGGESTIONS]}
        if name == VowTools.REACH_FORECAST:
            return self._forecast(arguments)
        if name == VowTools.DEAL_FILTER_PROPERTIES:
            return dict(_FILTER_PROPERTIES)
        if name == VowTools.INVENTORY_SOURCES:
            # `results`, because that is the envelope `registry.ingestion._map_inventory_sources`
            # reads - the same list-endpoint shape `LIST_DEALS` returns.
            return {"results": [dict(row) for row in _INVENTORY_SOURCES]}
        if name == VowTools.PRODUCT_CATEGORIES:
            market = arguments.get("market", "GB")
            return {"results": [dict(row) for row in _PRODUCT_CATEGORIES.get(market, [])]}
        if name == VowTools.LOCATIONS:
            market = arguments.get("market", "GB")
            return {"results": [dict(row) for row in _LOCATIONS.get(market, [])]}
        if name == VowTools.TARGETING_OPTIONS:
            # Keyed by targeting type, because `data/targeting_types.json` asks for one type
            # per call. An unknown key returns nothing rather than everything: a type the
            # platform does not serve must not be offered to a trader.
            key = arguments.get("type") or arguments.get("key") or ""
            return {"results": [dict(row) for row in _TARGETING_OPTIONS.get(key, [])]}
        if name == VowTools.CHECK_STRATEGY_NAME:
            candidate = (arguments.get("name") or "").strip()
            return {"is_unique": candidate not in _TAKEN_STRATEGY_NAMES}

        raise MCPToolNotFoundError(f"mock server exposes no tool named {name!r}", tool=name)

    # --- response builders ---

    @staticmethod
    def _deals(arguments: dict) -> dict:
        market = arguments.get("market", "GB")
        durations = arguments.get("durations") or []

        # Scenario lever, NOT a claim about real market availability: with Prime
        # Video in every market the dominant tier is always Amazon, so the
        # third-party "I cannot forecast reach" path is unreachable end to end.
        # Planning for FR returns third-party inventory only, which makes the
        # honesty rule demonstrable in a live walkthrough rather than only in a
        # unit test. The real server decides this for itself.
        available = (
            [d for d in _DEALS if d["provider"] != "Prime Video"]
            if market in _MARKETS_WITHOUT_AMAZON
            else _DEALS
        )

        results = []
        for deal in available:
            if durations and not set(durations) & set(deal["ad_lengths"]):
                continue
            enriched = dict(deal)
            enriched["name"] = deal["name"].format(market=market)
            results.append(enriched)

        return {"count": len(results), "results": results}

    @staticmethod
    def _forecast(arguments: dict) -> dict:
        """Amazon inventory forecasts; third-party does not.

        The mock refuses to invent reach for non-Amazon inventory on purpose -
        if it faked a number, nothing downstream would ever exercise the
        honesty path.
        """
        budget = float(arguments.get("budget") or 0)
        cpm = float(arguments.get("effective_cpm") or 0)
        impressions = int((budget / cpm) * 1000) if cpm else 0

        if arguments.get("inventory_tier") != "AMAZON_OWNED":
            return {
                "is_available": False,
                "reason": "Reach forecasting is available for Amazon inventory only.",
                "estimated_impressions": impressions,
                "indicative_cpm": f"{cpm:.2f}",
            }

        reach = int(impressions / 3.2) if impressions else 0
        return {
            "is_available": True,
            "estimated_impressions": impressions,
            "estimated_unique_reach": reach,
            "average_frequency": 3.2,
            "indicative_cpm": f"{cpm:.2f}",
            "reach_curve": [
                {"budget": round(budget * f, 2), "reach": int(reach * r)}
                for f, r in ((0.25, 0.38), (0.5, 0.64), (0.75, 0.85), (1.0, 1.0))
            ],
        }
