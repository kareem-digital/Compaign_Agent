"""Canned VOW-shaped payloads for the in-process mock MCP server.

Lifted out of `mock.py` so that file stays dispatch-only: the mock now answers
ten tools, and interleaving the data with the routing made both harder to read.

Values come from the documented examples: Prime Video ROS at 18.22 vs Action at
22.07 (the genre-upsell case in `VOW_Strategy_Schema_v2.md` section 2.3), deal
IDs in VOW's `EXT...` form, and one provider per inventory tier so the
three-tier fork is actually reachable.

`DEALS` is the single place deal facts live. Filter properties, inventory
sources and curation genres are *derived* from it below rather than declared
again - a mock that can contradict itself is worse than no mock, because it
teaches the registry's tests to accept an impossible world.
"""

from __future__ import annotations

from typing import Any

# --- inventory ---------------------------------------------------------------

# Annotated because the rows mix strings, lists and None; without it every value
# infers as `object` and nothing downstream can index a deal.
DEALS: list[dict[str, Any]] = [
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

# See `MockMCPClient._deals` - a demo lever so the third-party path is
# reachable, not a real availability fact.
MARKETS_WITHOUT_AMAZON = {"FR"}

# Markets the mock trades in. Matches `extract_fields._MARKET_PATTERNS`, so a
# brief the extractor can parse is a brief the registry can ground.
MARKETS = ["DE", "FR", "GB", "US"]

RATE_CARD = {
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

# Provider to tier, as VOW's `GET /inventory-sources/` is expected to report it.
# The registry ingests this rather than guessing, which is what let the hardcoded
# provider-to-tier map in `select_inventory.py` be deleted. Hulu has no deal here
# on purpose: the map is a fact about providers, not a summary of the deal list.
#
# The literal tier strings are deliberate. `mock_data` cannot import
# `InventoryTierEnum` - `app.tools` must not depend on `app.knowledge` - so
# `tests/contract/test_registry_contract.py` asserts these equal the enum.
INVENTORY_SOURCES = [
    {"provider": "Prime Video", "inventory_tier": "AMAZON_OWNED"},
    {"provider": "Netflix", "inventory_tier": "THIRD_PARTY_PRECURATED"},
    {"provider": "Hulu", "inventory_tier": "THIRD_PARTY_PRECURATED"},
    {"provider": "Disney+", "inventory_tier": "THIRD_PARTY_NEEDS_CURATION"},
]

# --- audiences ---------------------------------------------------------------

# Three profiles, mandatory. Narrow is smaller AND dearer - the fee stacks on
# the deal CPM, which is the point traders most often miss.
AUDIENCE_SUGGESTIONS = [
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

# --- step 1 reference data ---------------------------------------------------

# Strategy names already taken, so the uniqueness check has something to
# refuse. A real server owns this; the mock only needs one collision.
TAKEN_STRATEGY_NAMES = {
    "ctv gb 2026-08",
    "q3 ctv brand awareness us",
    "holiday promo gb 2026",
}

STRATEGY_NAME_RULES = {
    "max_length": 120,
    "allowed_pattern": r"^[\w\s\-|.,()&/]+$",
    "case_sensitive": False,
}

# Keyed by market because `GET /contextual-targeting/{market}/product-categories/`
# is market-scoped. IDs are ints - schema v2 section 5 has
# `product_categories: list[int]`.
PRODUCT_CATEGORIES = {
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
        {"id": 105, "name": "Retail & E-commerce"},
        {"id": 107, "name": "Food & Beverage"},
    ],
}

# --- step 5 targeting --------------------------------------------------------

# Locations per market, as `GET /strategies/locations/{market}/` returns them.
LOCATIONS = {
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

# Keyed by targeting type, matching the `type` argument the targeting-options
# tool takes. Adding a type here plus an entry in
# `knowledge/registry/data/targeting_types.json` is the whole cost of a new
# targeting type - schema v2 section 3 step 5 requires exactly that.
TARGETING_OPTIONS = {
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


# --- derived -----------------------------------------------------------------
#
# Everything below is computed from the data above, so the mock cannot serve a
# genre, provider or duration that no deal has.


def _genres() -> list[str]:
    return sorted({deal["genre"] for deal in DEALS if deal["genre"]})


# NOT derived from `DEALS`. Filter properties describe what the platform sells,
# and the four mock deals happen to carry only 15 and 30 - deriving from them
# would have the mock claim CTV cannot sell a 10s ad, contradicting schema v2
# section 3 step 1 and `extract_fields._VALID_DURATIONS`. The registry's
# integrity check still requires every deal's ad_lengths to be a subset of this.
AD_LENGTHS = ["10", "15", "20", "30"]


def filter_properties() -> dict:
    """What `GET /deals/filter-properties/` reports: the shape of the catalogue.

    This is the registry's grounding source for step 1 - markets, durations and
    formats a brief may legitimately name.
    """
    return {
        "markets": list(MARKETS),
        "currencies": ["EUR", "GBP", "USD"],
        "formats": ["streaming_tv", "prime_video"],
        "ad_lengths": list(AD_LENGTHS),
        "genres": _genres(),
        "goals": ["AWARENESS"],
        "kpis": ["reach", "frequency"],
    }


def deals_for(market: str, durations: list[str] | None = None) -> list[dict[str, Any]]:
    """Deals available in `market`, optionally narrowed to `durations`.

    Scenario lever, NOT a claim about real market availability: with Prime Video
    in every market the dominant tier is always Amazon, so the third-party
    "I cannot forecast reach" path is unreachable end to end. Planning for FR
    returns third-party inventory only, which makes the honesty rule
    demonstrable in a live walkthrough rather than only in a unit test. The real
    server decides this for itself.
    """
    available = (
        [d for d in DEALS if d["provider"] != "Prime Video"]
        if market in MARKETS_WITHOUT_AMAZON
        else DEALS
    )

    results = []
    for deal in available:
        if durations and not set(durations) & set(deal["ad_lengths"]):
            continue
        enriched = dict(deal)
        enriched["name"] = deal["name"].format(market=market)
        results.append(enriched)

    return results
