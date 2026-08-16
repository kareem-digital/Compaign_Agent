"""Tests for fetch, map and cache, against the in-process mock MCP server.

Two properties matter more than the mapping itself.

**It degrades rather than dying.** VOW's real server will not expose all ten
tools on day one, and a registry that refused to sync would take the planning
flow down over a tool that fills a dropdown. So an optional source going missing
is recorded on the snapshot; only a facet the flow cannot work without raises.

**It syncs once.** A conversation runs several turns and each turn may ask for the
snapshot. Every test that touches the cache asserts on `MockMCPClient.calls`,
because "did it re-fetch?" is the question a TTL and a lock exist to answer.
"""

import asyncio

import pytest

from app.config import Settings
from app.core.exceptions import (
    MCPToolNotFoundError,
    RegistrySyncError,
    RegistryValidationError,
)
from app.knowledge.registry.ingestion import (
    InMemoryRegistryStore,
    RegistryIngestor,
    SyncReport,
)
from app.knowledge.registry.models import InventoryTierEnum
from app.knowledge.registry.validate import SnapshotValidator
from app.tools.mcp import VowTools
from app.tools.mcp.mock import MockMCPClient

# --- helpers -----------------------------------------------------------------


def _settings(**overrides) -> Settings:
    """Settings with the registry knobs set explicitly, not read from .env."""
    defaults = {
        "registry_eager_markets": ["GB"],
        "registry_strict_sync": False,
        "registry_max_reject_ratio": 0.25,
        "use_mock_mcp": True,
    }
    return Settings(**{**defaults, **overrides})


class _ServerMissing(MockMCPClient):
    """A mock server that has not shipped some tools yet.

    Subclassed rather than monkeypatched so the omission is visible in the test
    that uses it: this is the real-server-on-day-one scenario.
    """

    def __init__(self, *args, missing: set[str], **kwargs):
        super().__init__(*args, **kwargs)
        self._missing = missing

    async def _list_tools_raw(self):
        return [t for t in await super()._list_tools_raw() if t["name"] not in self._missing]

    async def _call_tool_raw(self, name: str, arguments: dict):
        if name in self._missing:
            self.calls.append((name, arguments))
            raise MCPToolNotFoundError(f"not implemented yet: {name}", tool=name)
        return await super()._call_tool_raw(name, arguments)


class _MalformedDeals(MockMCPClient):
    """A server whose deals payload has lost a required field on some rows."""

    def __init__(self, *args, break_count: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self._break_count = break_count

    async def _call_tool_raw(self, name: str, arguments: dict):
        payload = await super()._call_tool_raw(name, arguments)
        if name == VowTools.LIST_DEALS:
            results = [dict(row) for row in payload["results"]]
            for row in results[: self._break_count]:
                del row["deal_price_amount"]
            payload = {**payload, "results": results}
        return payload


# --- the happy path ----------------------------------------------------------


async def test_a_complete_sync_grounds_every_step_one_to_five_facet() -> None:
    """One sync should leave nothing for a validator to be unable to answer."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    snapshot = await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])
    data = snapshot.data

    assert data.valid_markets == frozenset({"DE", "FR", "GB", "US"})
    assert data.valid_durations == frozenset({"10", "15", "20", "30"})
    assert data.allowed_goals == frozenset({"AWARENESS"})
    assert data.allowed_kpis == frozenset({"reach", "frequency"})
    assert len(data.deals("GB")) == 4
    assert len(data.audience_profiles) == 3
    assert data.carried_durations("GB") == frozenset({"15", "30"})
    assert data.targeting("GB") is not None
    assert data.product_categories["GB"]

    assert snapshot.meta.is_complete is True
    assert snapshot.meta.degraded_sources == ()
    assert snapshot.meta.rejected_items == ()
    assert snapshot.meta.compatibility == "INITIAL"
    assert snapshot.meta.source == "mock"


async def test_tiers_come_from_the_server_not_from_a_provider_guess() -> None:
    """`select_inventory.py` asked for this: trust the server's tier when it says.

    Hulu is in the inventory-sources payload but has no deal, which is exactly
    why the map is ingested separately rather than derived from the deal list.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")
    data = (await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])).data

    assert data.tier_by_provider["Prime Video"] is InventoryTierEnum.AMAZON_OWNED
    assert data.tier_by_provider["Disney+"] is InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION
    assert data.tier_by_provider["Hulu"] is InventoryTierEnum.THIRD_PARTY_PRECURATED


async def test_the_rate_card_is_flattened_out_of_its_nested_payload() -> None:
    """One row per (provider, duration), so no consumer writes the double loop."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    data = (await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])).data

    rows = {(e.provider, e.duration): e.cpm for e in data.rate_cards["GB"]}
    assert str(rows[("Prime Video", "15")]) == "18.22"
    assert str(rows[("Disney+", "30")]) == "34.00"


async def test_a_market_without_amazon_inventory_is_not_forecastable() -> None:
    """The mock's FR lever, which makes the honesty rule reachable end to end."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    data = (await RegistryIngestor(mcp, _settings()).sync(markets=["FR"])).data

    assert len(data.deals("FR")) == 2
    assert data.amazon_deals("FR") == ()


async def test_targeting_types_come_entirely_from_the_declaration() -> None:
    """Section 3 step 5 requires adding a targeting type to be a config change."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    config = (await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])).data.targeting("GB")

    assert set(config.options) == {
        "location",
        "instream_position",
        "content_category_exclusion",
        "device_type",
        "mobile_environment",
    }
    assert config.options["instream_position"].cardinality == "single"
    assert "PRE_ROLL" in config.options["instream_position"].value_ids()


# --- drift and degradation ---------------------------------------------------


async def test_a_missing_optional_tool_degrades_and_names_itself() -> None:
    """A dropdown's source going missing must not stop a plan."""
    mcp = _ServerMissing(advertiser_id="adv-1", missing={VowTools.PRODUCT_CATEGORIES})
    snapshot = await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])

    assert VowTools.PRODUCT_CATEGORIES in snapshot.meta.degraded_sources
    assert snapshot.meta.is_complete is False
    # Everything else still landed.
    assert len(snapshot.data.deals("GB")) == 4


async def test_strict_sync_turns_any_degradation_into_a_failure() -> None:
    """What CI should run, so reference-data drift fails a build."""
    mcp = _ServerMissing(advertiser_id="adv-1", missing={VowTools.PRODUCT_CATEGORIES})

    with pytest.raises(RegistrySyncError, match="unavailable"):
        await RegistryIngestor(mcp, _settings(registry_strict_sync=True)).sync(markets=["GB"])


async def test_a_missing_required_tool_always_fails() -> None:
    """Without deals there is nothing to plan against - degrading would be a lie."""
    mcp = _ServerMissing(advertiser_id="adv-1", missing={VowTools.LIST_DEALS})

    with pytest.raises(RegistrySyncError):
        await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])


async def test_one_malformed_row_is_dropped_and_the_rest_land() -> None:
    """One bad deal must not cost the other three."""
    mcp = _MalformedDeals(advertiser_id="adv-1", break_count=1)
    snapshot = await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])

    assert len(snapshot.data.deals("GB")) == 3
    assert len(snapshot.meta.rejected_items) == 1
    assert snapshot.meta.rejected_items[0].source == VowTools.LIST_DEALS


async def test_mostly_malformed_rows_fail_the_whole_source() -> None:
    """Three of four rejected means the payload shape changed, not that a row is bad."""
    mcp = _MalformedDeals(advertiser_id="adv-1", break_count=3)

    with pytest.raises(RegistryValidationError, match="shape"):
        await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])


async def test_transient_failures_are_the_clients_problem_not_the_registrys() -> None:
    """`MCPClient._retrying` owns backoff; the registry adds nothing on top."""
    mcp = MockMCPClient(advertiser_id="adv-1", fail_times=2)
    snapshot = await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])

    assert snapshot.meta.is_complete is True


async def test_the_tool_surface_is_reconciled_once_per_ingestor() -> None:
    """`mcp/__init__.py` calls this the whole integration risk of moving to MCP."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    ingestor = RegistryIngestor(mcp, _settings())

    await ingestor.sync(markets=["GB"])
    await ingestor.sync(markets=["US"])

    assert len([c for c in mcp.calls if c[0] == "list_tools"]) == 1


async def test_a_shrunken_tool_surface_is_logged_not_fatal(caplog) -> None:
    mcp = _ServerMissing(advertiser_id="adv-1", missing={VowTools.LOCATIONS})

    with caplog.at_level("WARNING"):
        await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])

    assert any(record.message == "registry.tool_surface" for record in caplog.records)


# --- the cache ---------------------------------------------------------------


async def test_a_second_read_makes_no_mcp_calls() -> None:
    store = InMemoryRegistryStore(ttl_seconds=900)
    mcp = MockMCPClient(advertiser_id="adv-1")

    await store.get("adv-1", mcp, market="GB")
    before = len(mcp.calls)
    await store.get("adv-1", mcp, market="GB")

    assert len(mcp.calls) == before


async def test_a_new_market_extends_the_snapshot_without_resyncing_core() -> None:
    """Deals are market-scoped; markets, durations and tiers are not."""
    store = InMemoryRegistryStore(ttl_seconds=900)
    mcp = MockMCPClient(advertiser_id="adv-1")

    await store.get("adv-1", mcp, market="GB")
    snapshot = await store.get("adv-1", mcp, market="FR")

    assert snapshot.markets_loaded() == ("FR", "GB")
    assert len([c for c in mcp.calls if c[0] == VowTools.DEAL_FILTER_PROPERTIES]) == 1


async def test_an_expired_ttl_resyncs_every_market_it_already_held() -> None:
    """A refresh that fetched only the requested market would silently drop the
    others - and the diff would then read that as a breaking change."""
    store = InMemoryRegistryStore(ttl_seconds=0)
    mcp = MockMCPClient(advertiser_id="adv-1")

    await store.get("adv-1", mcp, market="GB")
    await store.get("adv-1", mcp, market="FR")
    refreshed = await store.get("adv-1", mcp, market="GB")

    assert refreshed.markets_loaded() == ("FR", "GB")
    assert refreshed.meta.compatibility == "IDENTICAL"


async def test_concurrent_cold_reads_sync_once() -> None:
    """Ten first requests must not fan out ten times seven MCP calls."""
    store = InMemoryRegistryStore(ttl_seconds=900)
    mcp = MockMCPClient(advertiser_id="adv-1")

    await asyncio.gather(*(store.get("adv-1", mcp, market="GB") for _ in range(10)))

    assert len([c for c in mcp.calls if c[0] == VowTools.LIST_DEALS]) == 1


async def test_one_advertisers_snapshot_is_never_served_to_another() -> None:
    """Deals and prices are the client's commercial data. A shared snapshot is a
    tenant-isolation breach, which core/logging.py classifies as critical."""
    store = InMemoryRegistryStore(ttl_seconds=900)

    first = await store.get("adv-1", MockMCPClient(advertiser_id="adv-1"), market="GB")
    second = await store.get("adv-2", MockMCPClient(advertiser_id="adv-2"), market="GB")

    assert first.advertiser_id == "adv-1"
    assert second.advertiser_id == "adv-2"
    assert first is not second


async def test_a_failed_refresh_serves_the_previous_snapshot_as_stale() -> None:
    """Reference data twenty minutes stale beats the planning flow going down."""
    store = InMemoryRegistryStore(ttl_seconds=0)
    mcp = MockMCPClient(advertiser_id="adv-1")
    await store.get("adv-1", mcp, market="GB")

    broken = _ServerMissing(advertiser_id="adv-1", missing={VowTools.LIST_DEALS})
    stale = await store.get("adv-1", broken, market="GB")

    assert stale.meta.is_stale is True
    assert len(stale.data.deals("GB")) == 4


async def test_a_cold_advertiser_with_no_fallback_propagates_the_failure() -> None:
    """Grounding against nothing would reject every value the trader named."""
    store = InMemoryRegistryStore(ttl_seconds=900)
    broken = _ServerMissing(advertiser_id="adv-9", missing={VowTools.LIST_DEALS})

    with pytest.raises(RegistrySyncError):
        await store.get("adv-9", broken, market="GB")


async def test_invalidate_forgets_the_lineage_and_force_keeps_it() -> None:
    """Two different intents, deliberately not the same operation."""
    store = InMemoryRegistryStore(ttl_seconds=900)
    mcp = MockMCPClient(advertiser_id="adv-1")

    await store.get("adv-1", mcp, market="GB")
    await store.get("adv-1", mcp, market="FR")

    forced = await store.get("adv-1", mcp, market="GB", force=True)
    assert forced.meta.version == 2

    store.invalidate("adv-1")
    fresh = await store.get("adv-1", mcp, market="GB")
    assert fresh.meta.version == 1
    assert fresh.meta.compatibility == "INITIAL"


# --- logging discipline ------------------------------------------------------


async def test_the_sync_log_carries_counts_not_commercial_data(caplog) -> None:
    """Deal prices are the client's commercial data.

    `core/logging.py` keeps payloads at DEBUG for exactly this reason, and the
    registry handles more of that data than any other module.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")

    with caplog.at_level("INFO"):
        await RegistryIngestor(mcp, _settings()).sync(markets=["GB"])

    sync_records = [r for r in caplog.records if r.message == "registry.sync"]
    assert sync_records

    for record in sync_records:
        rendered = str(record.__dict__)
        assert "18.22" not in rendered
        assert "EXTQ5" not in rendered


# --- the breaking-change policy ----------------------------------------------


class _ShrunkenMarkets(MockMCPClient):
    """A server that has stopped selling in some markets since the last sync.

    A removed facet is the textbook breaking change: something a consumer could
    already be reading has gone.
    """

    async def _call_tool_raw(self, name: str, arguments: dict):
        payload = await super()._call_tool_raw(name, arguments)
        if name == VowTools.DEAL_FILTER_PROPERTIES:
            payload = {**payload, "markets": ["GB"]}
        return payload


async def _first_then_shrunken(policy: str):
    ingestor = RegistryIngestor(
        MockMCPClient(advertiser_id="adv-1"), _settings(registry_on_breaking_change=policy)
    )
    first = await ingestor.sync(markets=["GB"])

    shrunken = RegistryIngestor(
        _ShrunkenMarkets(advertiser_id="adv-1"), _settings(registry_on_breaking_change=policy)
    )
    return first, await shrunken.sync(markets=["GB"], previous=first)


async def test_a_breaking_change_is_swapped_in_and_logged_by_default(caplog) -> None:
    """Refusing the update would mean planning against stale prices, which is
    worse than a loud log line."""
    with caplog.at_level("ERROR"):
        first, second = await _first_then_shrunken("warn")

    assert first.data.valid_markets == frozenset({"DE", "FR", "GB", "US"})
    assert second.data.valid_markets == frozenset({"GB"})
    assert second.meta.compatibility == "BREAKING"
    assert second.meta.is_stale is False
    assert any(r.message == "registry.breaking_change" for r in caplog.records)


async def test_the_reject_policy_keeps_the_previous_snapshot_and_marks_it_stale() -> None:
    """For when there is real ops to act on the alarm."""
    first, second = await _first_then_shrunken("reject")

    assert second.data.valid_markets == first.data.valid_markets
    assert second.meta.is_stale is True
    assert second.meta.version == first.meta.version


# --- a market the platform does not sell -------------------------------------
#
# The failure these prevent: the trader named China, the LLM extracted "CN", and
# the sync raised `RegistryValidationError` - three integrity violations, surfaced
# to the trader as an opaque 500. VOW's deal list answers for any market string it
# is handed, while `valid_markets` comes from a different tool and does not include
# CN, so a snapshot built for CN contradicted itself and `gate` refused it.
#
# Both paths need covering. `_sync` asks for `[market]` while an advertiser is cold
# and reaches `sync`; once any snapshot is cached, `get` reaches `sync_market`
# instead. Guarding one leaves the other failing.


async def test_an_unsold_market_does_not_bring_the_whole_snapshot_down() -> None:
    """The cold path: the requested market is the only one asked for."""
    snapshot = await RegistryIngestor(MockMCPClient(advertiser_id="adv-cn")).sync(markets=["CN"])

    assert snapshot.markets_loaded() == ()
    assert "CN" not in snapshot.data.available_deals
    # Core facets are unaffected, so step 1 can still ground - and reject CN.
    assert snapshot.data.valid_markets == frozenset({"DE", "FR", "GB", "US"})


async def test_an_unsold_market_is_skipped_without_dropping_the_sold_ones() -> None:
    """One bad market in the list must not cost the good ones."""
    snapshot = await RegistryIngestor(MockMCPClient(advertiser_id="adv-mixed")).sync(
        markets=["GB", "CN", "FR"]
    )

    assert snapshot.markets_loaded() == ("FR", "GB")


async def test_an_unsold_market_does_not_extend_a_cached_snapshot() -> None:
    """The warm path, through `sync_market` - where every advertiser past their
    first turn arrives."""
    mcp = MockMCPClient(advertiser_id="adv-warm")
    ingestor = RegistryIngestor(mcp)
    cached = await ingestor.sync(markets=["GB"])

    extended = await ingestor.sync_market(cached, "CN")

    assert extended.markets_loaded() == ("GB",)
    assert extended.meta.version == cached.meta.version


async def test_the_store_serves_an_unsold_market_without_raising() -> None:
    """End to end through the cache, which is how `validate_basics` reaches it."""
    store = InMemoryRegistryStore()
    mcp = MockMCPClient(advertiser_id="adv-store-cn")

    snapshot = await store.get("adv-store-cn", mcp, market="CN")

    assert snapshot.markets_loaded() == ()
    # And asking again is still safe once something is cached - the warm path.
    assert (await store.get("adv-store-cn", mcp, market="CN")).markets_loaded() == ()


async def test_an_unsold_market_costs_no_per_market_calls() -> None:
    """Skipped, not fetched. Four calls per market is the thing being avoided."""
    mcp = MockMCPClient(advertiser_id="adv-cn-calls")
    await RegistryIngestor(mcp).sync(markets=["CN"])

    assert not [name for name, _ in mcp.calls if name == VowTools.LIST_DEALS]


async def test_the_violations_are_logged_and_not_only_counted(caplog) -> None:
    """`sessions.chat` turns this into an opaque 500, so the log line is the only
    place the reason survives. A count alone cannot answer "which checks?"."""
    ingestor = RegistryIngestor(MockMCPClient(advertiser_id="adv-violations"))
    core = await ingestor._sync_core(SyncReport())
    ingestor._tier_by_provider = core.get("tier_by_provider") or {}
    # Assembled by hand, because the guard above now stops `sync` producing one.
    data = ingestor._assemble(core, {"CN": await ingestor._sync_market("CN", SyncReport())})

    with caplog.at_level("ERROR"), pytest.raises(RegistryValidationError) as raised:
        SnapshotValidator().gate(data)

    assert len(raised.value.violations) == 3
    (record,) = [r for r in caplog.records if r.message == "registry.integrity_violation"]
    # `kv` nests under `extra_fields` - see app/core/logging.py.
    logged = record.extra_fields
    assert logged["count"] == 3
    assert "deals returned for CN, which is not a valid market" in logged["violations"]
