"""Raw payloads the grounded registry has to read.

`CANONICAL_*` are shaped the way `MockMCPClient` serves them today - VOW's own
field names, straight off the documented examples.

`HOSTILE_*` are the same facts spelled the way an earlier draft schema spelled
them: `rate_card_cpm` instead of `deal_price_amount`, `"UK"` instead of `"GB"`,
`"3P_PRE_CURATED"` instead of `THIRD_PARTY_PRECURATED`, `"Narrow"` instead of
`NARROW`, `"REACH"` instead of `"reach"`. Keeping them here rather than in
production code is the point: the registry's normalizers and `AliasChoices` are
supposed to absorb exactly this, so these payloads are the proof rather than a
second dataset to maintain. If the real MCP server turns out to use any of these
spellings, nothing needs changing.
"""

# --- canonical (as MockMCPClient serves them) --------------------------------

CANONICAL_DEAL = {
    "external_deal_id": "EXTQ5",
    "name": "Prime Video | Run of Service | GB - 15, 30",
    "provider": "Prime Video",
    "deal_type": "Private Auction",
    "deal_price_amount": "18.22",
    "genre": None,
    "ad_lengths": ["15", "30"],
    "devices": ["TV"],
    "inventory_tier": "AMAZON_OWNED",
    "market": "GB",
}

CANONICAL_AUDIENCE = {
    "audience_set_id": "aud-narrow-0001",
    "name": "In-market: premium streaming, high intent",
    "profile": "NARROW",
    "vcpm_fee": "3.50",
    "segment_count": 6,
    "estimated_size": 1_200_000,
}

CANONICAL_FILTER_PROPERTIES = {
    "markets": ["GB", "US"],
    "currencies": ["GBP", "USD"],
    "ad_lengths": ["15", "30"],
    "formats": ["streaming_tv"],
    "genres": ["Action"],
    "goals": ["AWARENESS"],
    "kpis": ["reach", "frequency"],
}


# --- hostile (an earlier draft's spellings) ----------------------------------

HOSTILE_DEAL = {
    # deal_id rather than external_deal_id
    "deal_id": "D-AMZ-PRIME-01",
    "deal_name": "Prime Video Premium Video Ads",
    "name": "Prime Video Premium Video Ads",
    "provider": "Prime Video",
    # rate_card_cpm rather than deal_price_amount, and a float rather than a
    # decimal string
    "rate_card_cpm": 18.50,
    "tier": "3P_PRE_CURATED",
    "inventory_tier": "3P_PRE_CURATED",
    # available_durations rather than ad_lengths
    "available_durations": ["15s", "30 sec"],
    "supports_reach_forecast": True,
    "market": "UK",
}

HOSTILE_AUDIENCE = {
    "audience_set_id": "aud-broad-9999",
    "name": "Broad reach targeting wide demographic clusters",
    # "Broad" was the pre-v2 name for WIDE, and section 3 step 4 flags the live
    # suggest response as possibly still using it
    "profile": "Broad",
    "vcpm_fee": 1.0,
    "segment_count": 31,
    "estimated_size": 15_400_000,
    # a field the registry does not model, which must warn rather than fail
    "risk_notes": "Lower audience fee, maximal potential reach.",
}

HOSTILE_FILTER_PROPERTIES = {
    "markets": ["UK", "US", "DE"],
    "currencies": ["GBP", "USD", "EUR"],
    "ad_lengths": [10, "15s", "20 seconds", 30],
    "formats": ["streaming-tv"],
    "genres": ["Action & Adventure", "Comedy"],
    "goals": ["Awareness"],
    "kpis": ["REACH", "FREQUENCY"],
}

# The split methods and matching modes an earlier draft used as display prose.
HOSTILE_SPLIT_METHODS = ["Even by budget", "Even by impressions"]
HOSTILE_MATCHING_MODES = ["Exact", "Similar"]
