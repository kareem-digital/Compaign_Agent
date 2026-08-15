"""Bringing VOW's reference data in, and keeping it.

The pipeline, in order: **fetch through MCP -> field-map -> normalize -> validate
-> version -> serve**. Every stage is here except normalization, which lives in
the models' field validators so a non-canonical value cannot exist, and
validation, which lives in `validate.SnapshotValidator` because it is the gate
rather than the plumbing.

Three shapes worth understanding before changing anything:

**Two phases.** Core facets (markets, durations, tiers, audience profiles) are
market-independent and sync once. Deals, rate cards, product categories and
targeting are market-scoped, so they fill lazily on first use - eager-fetching
every market costs four calls each, and a plan touches one market.

**Per advertiser, never global.** `MCPClient.call_tool` injects `advertiser_id`
into every call, so deal availability is already tenant-specific. A shared
snapshot would serve one advertiser's commercial data to another, which
`core/logging.py` classifies as a tenant-isolation breach.

**Degrade, do not die.** VOW's real MCP server will not expose all ten tools on
day one. A registry that refused to sync would take the planning flow down over a
tool that only fills a dropdown, so an optional source going missing is recorded
and reported rather than raised. `registry_strict_sync` flips that to fail-fast,
which is what CI should run. Only a facet the flow genuinely cannot work without
raises - see `SnapshotValidator.check_required_facets`.

**There is no startup sync, and it is not an oversight.** `MCPClient.call_tool`
fails closed without an advertiser, and at boot there is no advertiser. Any
sync-at-startup design implicitly asks the registry to pick a tenant, which is
the one thing this codebase refuses to do. Snapshots are built on first use, from
the advertiser on the request.

Deferred: Postgres persistence, behind `RegistryStore`, mirroring
`checkpointer.py`'s memory-vs-Postgres switch (`config.py` names "KNW registry"
against `database_url`). Not now, because the snapshot is derived data
rebuildable in a handful of calls, and `use_memory_checkpointer` defaults to True
- the service runs with no database at all today. Consequence while it is
deferred: with two replicas, `meta.version` is process-local.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.core.exceptions import (
    MCPError,
    RegistrySyncError,
    RegistryValidationError,
)
from app.core.logging import kv
from app.knowledge.registry.models import (
    CTV_FORMATS,
    CTV_GOALS,
    CTV_KPIS,
    MATCHING_MODES,
    REGISTRY_SCHEMA_VERSION,
    AudienceProfileItem,
    BudgetSplitMethodEnum,
    DealItem,
    GroundedRegistryData,
    GroundedRegistrySnapshot,
    InventoryTierEnum,
    MarketTargetingConfig,
    NormalizationError,
    ProductCategory,
    RateCardEntry,
    RegistrySnapshotMeta,
    RejectedItem,
    StrategyNameRules,
    TargetingOption,
    TargetingOptionValue,
    normalize_currency,
    normalize_duration,
    normalize_format,
    normalize_goal,
    normalize_kpi,
    normalize_market,
    normalize_tier,
)
from app.knowledge.registry.targeting import load_targeting_types
from app.knowledge.registry.validate import SnapshotValidator, StepwiseCTVValidator
from app.tools.mcp import MCPClient, VowTools

logger = logging.getLogger(__name__)

# Sources without which the flow cannot plan at all. Everything else degrades.
REQUIRED_SOURCES = frozenset(
    {VowTools.DEAL_FILTER_PROPERTIES, VowTools.LIST_DEALS, VowTools.SUGGEST_AUDIENCES}
)

# The most conservative tier, because it promises the least. Inherited from the
# rule `select_inventory.classify_tier` used to apply, and kept for its reason:
# guessing that something is Amazon-owned would let a reach forecast be attempted
# on inventory that has none. Used only when the server's inventory-sources tool
# is unavailable.
FALLBACK_TIER = InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION


def _raise_first(results: list) -> list:
    """Re-raise the first exception a `gather(return_exceptions=True)` collected.

    The flag is there so one optional source failing does not cancel the others
    mid-flight; anything that still escapes `_call` is a genuine failure and has
    to surface rather than be assigned to a facet.
    """
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results


class SyncReport:
    """What happened during one fetch, accumulated as it goes."""

    def __init__(self) -> None:
        self.degraded: list[str] = []
        self.rejected: list[RejectedItem] = []

    def degrade(self, source: str, reason: str) -> None:
        self.degraded.append(source)
        logger.warning("registry.source_degraded", extra=kv(source=source, reason=reason))

    def reject(self, source: str, reason: str, identifier: str | None = None) -> None:
        self.rejected.append(RejectedItem(source=source, reason=reason, identifier=identifier))

    def merge(self, other: SyncReport) -> None:
        self.degraded += other.degraded
        self.rejected += other.rejected


class RegistryIngestor:
    """Builds a snapshot for one advertiser from one MCP client.

    Takes any `MCPClient`. Mock-versus-live is `create_mcp_client`'s decision via
    `use_mock_mcp`, so nothing here needs to know which it got - which is the
    whole reason there is no separate mock ingestor to keep in step.
    """

    def __init__(self, mcp: MCPClient, settings: Settings | None = None):
        self.mcp = mcp
        self.settings = settings or get_settings()
        self.checks = SnapshotValidator()
        self._tools_reconciled = False
        # Populated by `_sync_core` before any market is fetched, because
        # `_map_deals` resolves each deal's tier against it. Seeded from an
        # existing snapshot when extending one.
        self._tier_by_provider: dict[str, InventoryTierEnum] = {}

    # --- the public entry points ---

    async def sync(
        self,
        markets: list[str] | None = None,
        previous: GroundedRegistrySnapshot | None = None,
    ) -> GroundedRegistrySnapshot:
        """Build a snapshot: core facets plus whichever markets were asked for."""
        started = time.monotonic()
        report = SyncReport()

        await self._reconcile_tools()

        core = await self._sync_core(report)
        # Must be set before any market is fetched: `_map_deals` resolves each
        # deal's tier against this, and an empty map would silently default every
        # provider to needs-curation.
        self._tier_by_provider = core.get("tier_by_provider") or {}

        wanted = markets if markets is not None else list(self.settings.registry_eager_markets)

        per_market: dict[str, dict] = {}
        for market in wanted:
            try:
                code = normalize_market(market)
            except NormalizationError:
                report.degrade("markets", f"{market!r} is not an ISO market code")
                continue
            # A market the platform does not sell is skipped rather than fetched.
            #
            # Not defensive - this is the only thing standing between an unsold
            # market and a hard failure. `_sync` asks for `[market]` when an
            # advertiser is cold, so the market the trader named becomes the *only*
            # per-market facet; VOW's deal list answers for any market string it is
            # given, while `valid_markets` comes from a different tool and does not
            # include it. The snapshot then contradicts itself and
            # `check_referential_integrity` correctly refuses the whole thing -
            # so asking for CN used to raise `RegistryValidationError` from a sync
            # whose own reference data already knew CN was not sold.
            #
            # Skipping keeps the snapshot self-consistent, which lets
            # `validate_target_markets` do its job: the trader gets "VOW does not
            # sell CTV inventory there" and the four markets it does, instead of an
            # opaque 500. Only reachable via the LLM extractor - the pattern path
            # cannot emit a market outside the four it knows.
            if code not in core.get("valid_markets", frozenset()):
                logger.info(
                    "registry.market_not_sold",
                    extra=kv(
                        market=code, action="skipped", valid=sorted(core.get("valid_markets", ()))
                    ),
                )
                continue
            per_market[code] = await self._sync_market(code, report)

        data = self._assemble(core, per_market)
        snapshot = self._finalize(data, report, previous, started)

        return snapshot

    async def sync_market(
        self, snapshot: GroundedRegistrySnapshot, market: str
    ) -> GroundedRegistrySnapshot:
        """Add one market's facets to an existing snapshot.

        Returns a new snapshot rather than mutating: `GroundedRegistryData` is
        frozen, and a consumer holding a half-updated snapshot is exactly the race
        immutability is there to prevent.
        """
        started = time.monotonic()
        code = normalize_market(market)

        if code in snapshot.data.available_deals:
            return snapshot

        # The warm half of the guard in `sync`, and it is not redundant: once an
        # advertiser holds any snapshot, `InMemoryRegistryStore.get` reaches an
        # unsold market through here instead. Guarding only `sync` would leave every
        # advertiser past their first turn still failing.
        if code not in snapshot.data.valid_markets:
            logger.info("registry.market_not_sold", extra=kv(market=code, action="not_extended"))
            return snapshot

        report = SyncReport()
        report.degraded = list(snapshot.meta.degraded_sources)
        report.rejected = list(snapshot.meta.rejected_items)

        # Seeded from the snapshot rather than re-fetched: the tier map is a core
        # facet and extending a snapshot with one market must not re-sync core.
        self._tier_by_provider = dict(snapshot.data.tier_by_provider)

        facets = await self._sync_market(code, report)

        data = snapshot.data.model_copy(
            update={
                "available_deals": {**snapshot.data.available_deals, code: facets["deals"]},
                "rate_cards": {**snapshot.data.rate_cards, code: facets["rate_card"]},
                "product_categories": {
                    **snapshot.data.product_categories,
                    code: facets["categories"],
                },
                "market_targeting_configs": (
                    {**snapshot.data.market_targeting_configs, code: facets["targeting"]}
                    if facets["targeting"]
                    else snapshot.data.market_targeting_configs
                ),
            }
        )

        return self._finalize(data, report, snapshot, started, previous_meta=snapshot.meta)

    # --- drift detection ---

    async def _reconcile_tools(self) -> None:
        """Compare the server's tool surface with what we expect. Once per ingestor.

        `mcp/__init__.py` calls this reconciliation "the whole integration risk of
        moving to MCP", and `client.py` says `list_tools()` is "the cheapest way
        to catch the server's surface drifting from what our nodes expect". When
        the real server lands, this log line is the entire diagnosis.
        """
        if self._tools_reconciled:
            return
        self._tools_reconciled = True

        expected = set(VowTools.all())
        try:
            served = {str(tool["name"]) for tool in await self.mcp.list_tools() if tool.get("name")}
        except MCPError as exc:
            logger.warning("registry.tool_surface_unknown", extra=kv(reason=str(exc)))
            return

        missing = sorted(expected - served)
        extra = sorted(served - expected)

        log = logger.warning if (missing or extra) else logger.info
        log(
            "registry.tool_surface",
            extra=kv(expected=len(expected), served=len(served), missing=missing, extra=extra),
        )

    # --- fetching ---

    async def _call(self, tool: str, args: dict | None, report: SyncReport) -> dict | None:
        """One tool call, with the degrade-or-die decision in one place."""
        try:
            return await self.mcp.call_tool(tool, args or {})
        except MCPError as exc:
            if tool in REQUIRED_SOURCES or self.settings.registry_strict_sync:
                raise RegistrySyncError(
                    f"Cannot build the grounded registry: {tool} is unavailable ({exc})"
                ) from exc
            report.degrade(tool, str(exc))
            return None

    async def _sync_core(self, report: SyncReport) -> dict:
        """Market-independent facets, fetched concurrently.

        Concurrent because they are independent and a cold advertiser should cost
        one round trip rather than three. `return_exceptions=True` so one
        optional source failing does not cancel the others mid-flight.
        """
        basics, sources, audiences = _raise_first(
            await asyncio.gather(
                self._call(VowTools.DEAL_FILTER_PROPERTIES, {}, report),
                self._call(VowTools.INVENTORY_SOURCES, {}, report),
                self._call(VowTools.SUGGEST_AUDIENCES, {}, report),
                return_exceptions=True,
            )
        )

        return {
            **self._map_basics(basics, report),
            "tier_by_provider": self._map_inventory_sources(sources, report),
            "audience_profiles": self._map_audiences(audiences, report),
        }

    async def _sync_market(self, market: str, report: SyncReport) -> dict:
        """One market's facets, fetched concurrently."""
        deals, rate_card, categories, targeting = _raise_first(
            await asyncio.gather(
                self._call(
                    VowTools.LIST_DEALS, {"market": market, "format": "streaming_tv"}, report
                ),
                self._call(VowTools.CTV_RATE_CARD, {"market": market}, report),
                self._call(VowTools.PRODUCT_CATEGORIES, {"market": market}, report),
                self._fetch_targeting(market, report),
                return_exceptions=True,
            )
        )

        return {
            "deals": self._map_deals(deals, market, report),
            "rate_card": self._map_rate_card(rate_card, report),
            "categories": self._map_categories(categories, report),
            "targeting": targeting,
        }

    async def _fetch_targeting(
        self, market: str, report: SyncReport
    ) -> MarketTargetingConfig | None:
        """Fetch one value list per declared targeting type.

        Driven entirely by `data/targeting_types.json`, so adding a targeting
        type needs no change here - which is the config-driven requirement in
        section 3 step 5. A type whose source is unavailable is dropped from this
        market rather than failing the market.
        """
        config = load_targeting_types()

        results = await asyncio.gather(
            *(
                self._call(spec.source.tool, spec.source.resolved_args(market), report)
                for spec in config.types
            ),
            return_exceptions=True,
        )

        options: dict[str, TargetingOption] = {}
        for spec, payload in zip(config.types, results, strict=True):
            if isinstance(payload, BaseException) or payload is None:
                report.degrade(f"targeting:{spec.key}", f"no values for {market}")
                continue

            rows = payload.get(spec.source.values_path) or []
            values = []
            for row in rows:
                identifier = row.get(spec.source.id_field)
                label = row.get(spec.source.label_field) or identifier
                if identifier is None:
                    report.reject(f"targeting:{spec.key}", "row has no id", None)
                    continue
                values.append(TargetingOptionValue(id=str(identifier), label=str(label)))

            if not values:
                continue

            options[spec.key] = TargetingOption(
                key=spec.key,
                label=spec.label,
                cardinality=spec.cardinality,
                required=spec.required,
                values=tuple(values),
            )

        if not options:
            return None
        return MarketTargetingConfig(market=market, options=options)

    # --- mapping: raw payload to normalized facet ---
    #
    # One mapper per source, so a failure is attributable to one payload. Each
    # tolerates a missing payload by falling back to the values the contract
    # fixes, and rejects a bad row rather than the whole source - one malformed
    # deal must not cost the other three.

    def _map_basics(self, payload: dict | None, report: SyncReport) -> dict:
        if payload is None:
            return {
                "valid_markets": frozenset(),
                "valid_currencies": frozenset(c for c in ("EUR", "GBP", "USD")),
                "valid_durations": frozenset(),
                "allowed_goals": CTV_GOALS,
                "allowed_kpis": CTV_KPIS,
                "allowed_formats": CTV_FORMATS,
                "curation_genres": frozenset(),
                "supported_split_methods": frozenset(m.value for m in BudgetSplitMethodEnum),
                "matching_modes": frozenset(MATCHING_MODES),
                "strategy_name_rules": StrategyNameRules(),
            }

        return {
            "valid_markets": self._normalized_set(
                payload.get("markets"), normalize_market, "markets", report
            ),
            # Currencies, split methods and matching modes are fixed by section 5,
            # so they come from the enums. The server narrowing them is honoured;
            # the server widening them is not, because a fourth currency would
            # need a contract change anyway.
            "valid_currencies": self._normalized_set(
                payload.get("currencies") or ["EUR", "GBP", "USD"],
                normalize_currency,
                "currencies",
                report,
            ),
            "valid_durations": self._normalized_set(
                payload.get("ad_lengths"), normalize_duration, "ad_lengths", report
            ),
            "allowed_goals": self._normalized_set(
                payload.get("goals") or sorted(CTV_GOALS), normalize_goal, "goals", report
            ),
            "allowed_kpis": self._normalized_set(
                payload.get("kpis") or sorted(CTV_KPIS), normalize_kpi, "kpis", report
            ),
            "allowed_formats": self._normalized_set(
                payload.get("formats") or sorted(CTV_FORMATS), normalize_format, "formats", report
            ),
            "curation_genres": frozenset(str(g) for g in (payload.get("genres") or []) if g),
            "supported_split_methods": frozenset(m.value for m in BudgetSplitMethodEnum),
            "matching_modes": frozenset(MATCHING_MODES),
            "strategy_name_rules": StrategyNameRules(),
        }

    def _map_inventory_sources(
        self, payload: dict | None, report: SyncReport
    ) -> dict[str, InventoryTierEnum]:
        """Provider to tier, from the server.

        `select_inventory.py` used to carry a hardcoded `_TIER_BY_PROVIDER` with
        a note saying to delete it once VOW's MCP server returned the tier
        itself. This is that: the map is ingested, and the node's copy is gone.
        When the tool is unavailable the fallback is per deal rather than per
        provider - see `_deal_tier`.
        """
        if payload is None:
            return {}

        tiers: dict[str, InventoryTierEnum] = {}
        for row in payload.get("results") or []:
            provider = row.get("provider")
            if not provider:
                report.reject(VowTools.INVENTORY_SOURCES, "row has no provider")
                continue
            try:
                tiers[str(provider)] = InventoryTierEnum(normalize_tier(row.get("inventory_tier")))
            except NormalizationError as exc:
                report.reject(VowTools.INVENTORY_SOURCES, str(exc), str(provider))
        return tiers

    def _map_audiences(
        self, payload: dict | None, report: SyncReport
    ) -> dict[str, AudienceProfileItem]:
        if payload is None:
            return {}

        profiles: dict[str, AudienceProfileItem] = {}
        for row in payload.get("suggestions") or []:
            try:
                item = self.checks.validate_payload(
                    AudienceProfileItem, row, VowTools.SUGGEST_AUDIENCES
                )
            except RegistryValidationError as exc:
                report.reject(VowTools.SUGGEST_AUDIENCES, str(exc), row.get("audience_set_id"))
                continue
            profiles[item.profile.value] = item
        return profiles

    def _map_deals(
        self, payload: dict | None, market: str, report: SyncReport
    ) -> tuple[DealItem, ...]:
        if payload is None:
            return ()

        rows = payload.get("results") or []
        deals: list[DealItem] = []
        for row in rows:
            enriched = {
                **row,
                "market": market,
                "inventory_tier": self._deal_tier(row, report),
            }
            try:
                deals.append(self.checks.validate_payload(DealItem, enriched, VowTools.LIST_DEALS))
            except RegistryValidationError as exc:
                report.reject(VowTools.LIST_DEALS, str(exc), row.get("external_deal_id"))

        self._guard_reject_ratio(VowTools.LIST_DEALS, len(rows), len(deals))
        return tuple(deals)

    def _deal_tier(self, row: dict, report: SyncReport) -> str:
        """The deal's tier: the server's if it says, ours conservatively if not.

        Order matters. A deal carrying its own tier is authoritative. Otherwise
        the provider map answers. Otherwise the most conservative tier, because
        it promises the least - guessing Amazon would unlock a forecast that does
        not exist.
        """
        if row.get("inventory_tier"):
            return str(row["inventory_tier"])

        provider = str(row.get("provider") or "")
        mapped = self._tier_by_provider.get(provider) if self._tier_by_provider else None
        if mapped is not None:
            return mapped.value

        if provider:
            report.reject(
                VowTools.INVENTORY_SOURCES,
                f"no tier for provider {provider!r}; defaulted conservatively",
                provider,
            )
        return FALLBACK_TIER.value

    def _map_rate_card(self, payload: dict | None, report: SyncReport) -> tuple[RateCardEntry, ...]:
        """Flatten `channels[].durations[]` into one row per (provider, duration)."""
        if payload is None:
            return ()

        entries: list[RateCardEntry] = []
        for channel in payload.get("channels") or []:
            provider = channel.get("name")
            for row in channel.get("durations") or []:
                try:
                    entries.append(
                        self.checks.validate_payload(
                            RateCardEntry,
                            {
                                "provider": provider,
                                "duration": row.get("duration"),
                                "cpm": row.get("cpm"),
                            },
                            VowTools.CTV_RATE_CARD,
                        )
                    )
                except RegistryValidationError as exc:
                    report.reject(VowTools.CTV_RATE_CARD, str(exc), str(provider))
        return tuple(entries)

    def _map_categories(
        self, payload: dict | None, report: SyncReport
    ) -> tuple[ProductCategory, ...]:
        if payload is None:
            return ()

        categories: list[ProductCategory] = []
        for row in payload.get("results") or []:
            try:
                categories.append(
                    self.checks.validate_payload(ProductCategory, row, VowTools.PRODUCT_CATEGORIES)
                )
            except RegistryValidationError as exc:
                report.reject(VowTools.PRODUCT_CATEGORIES, str(exc), str(row.get("id")))
        return tuple(categories)

    # --- helpers ---

    def _normalized_set(
        self, values, normalizer, source: str, report: SyncReport
    ) -> frozenset[str]:
        """Normalize a list, rejecting what cannot be mapped rather than guessing."""
        accepted = set()
        for value in values or []:
            try:
                accepted.add(normalizer(value))
            except NormalizationError as exc:
                report.reject(source, str(exc), str(value))
        return frozenset(accepted)

    def _guard_reject_ratio(self, source: str, total: int, accepted: int) -> None:
        """Too many rejections means the shape changed, not that one row is bad."""
        if total == 0:
            return
        ratio = (total - accepted) / total
        if ratio > self.settings.registry_max_reject_ratio:
            raise RegistryValidationError(
                f"{source} returned {total - accepted} of {total} rows this registry "
                f"cannot read - the payload shape has probably changed.",
                violations=[f"{source}: reject ratio {ratio:.0%}"],
            )

    def _assemble(self, core: dict, per_market: dict[str, dict]) -> GroundedRegistryData:
        return GroundedRegistryData(
            **{k: v for k, v in core.items() if k != "tier_by_provider"},
            tier_by_provider=self._tier_by_provider,
            available_deals={m: f["deals"] for m, f in per_market.items()},
            rate_cards={m: f["rate_card"] for m, f in per_market.items()},
            product_categories={m: f["categories"] for m, f in per_market.items()},
            market_targeting_configs={
                m: f["targeting"] for m, f in per_market.items() if f["targeting"]
            },
        )

    def _finalize(
        self,
        data: GroundedRegistryData,
        report: SyncReport,
        previous: GroundedRegistrySnapshot | None,
        started: float,
        previous_meta: RegistrySnapshotMeta | None = None,
    ) -> GroundedRegistrySnapshot:
        """Gate, version and stamp. The last thing before a snapshot is served."""
        warnings = self.checks.gate(data)

        previous_data = previous.data if previous else None
        previous_meta = previous_meta or (previous.meta if previous else None)

        diff = self.checks.diff(previous_data, data)
        compatibility = self.checks.classify_compatibility(previous_data, diff)
        content_hash = data.content_hash()
        version = self.checks.next_version(previous_meta, compatibility, content_hash)

        if compatibility == "BREAKING":
            # Logged at ERROR and swapped in anyway under the default policy:
            # planning against stale prices is worse than a loud log line. The
            # "reject" policy exists for when there is real ops to act on it.
            logger.error(
                "registry.breaking_change",
                extra=kv(
                    removed=list(diff.removed)[:20],
                    type_changed=list(diff.type_changed)[:20],
                    changed=list(diff.changed)[:20],
                    policy=self.settings.registry_on_breaking_change,
                ),
            )
            if self.settings.registry_on_breaking_change == "reject" and previous is not None:
                return previous.model_copy(
                    update={"meta": previous.meta.model_copy(update={"is_stale": True})}
                )

        if report.rejected:
            logger.warning(
                "registry.items_rejected",
                extra=kv(
                    count=len(report.rejected),
                    sources=sorted({r.source for r in report.rejected}),
                ),
            )

        meta = RegistrySnapshotMeta(
            schema_version=REGISTRY_SCHEMA_VERSION,
            version=version,
            content_hash=content_hash,
            synced_at=datetime.now(UTC),
            source="mock" if self.settings.use_mock_mcp else "live",
            compatibility=compatibility,
            diff=diff,
            degraded_sources=tuple(sorted(set(report.degraded))),
            rejected_items=tuple(report.rejected),
            integrity_warnings=tuple(warnings),
            is_complete=not report.degraded,
        )

        # Counts and hashes only, deliberately. Deals and rate cards are the
        # client's commercial data and are never logged - the snapshot contents
        # are reachable through the API, not the log stream.
        logger.info(
            "registry.sync",
            extra=kv(
                advertiser_id=self.mcp.advertiser_id,
                version=version,
                compatibility=compatibility,
                markets=len(data.available_deals),
                deals=sum(len(v) for v in data.available_deals.values()),
                audience_profiles=len(data.audience_profiles),
                degraded=len(meta.degraded_sources),
                rejected=len(meta.rejected_items),
                warnings=len(meta.integrity_warnings),
                duration_ms=round((time.monotonic() - started) * 1000),
            ),
        )
        return GroundedRegistrySnapshot(advertiser_id=self.mcp.advertiser_id, data=data, meta=meta)


class InMemoryRegistryStore:
    """Per-advertiser snapshot cache with a TTL and single-flight refresh.

    Cache and ingestor live together because they share one invariant: a snapshot
    is only ever whole. Mirrors the `_graphs` dict in `api/sessions.py`, including
    its caveat - fine at this scale, bound it before this serves many tenants.
    """

    def __init__(self, ttl_seconds: int | None = None):
        settings = get_settings()
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.registry_ttl_seconds
        self._snapshots: dict[str, GroundedRegistrySnapshot] = {}
        self._fetched_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(
        self,
        advertiser_id: str,
        mcp: MCPClient,
        *,
        market: str | None = None,
        force: bool = False,
    ) -> GroundedRegistrySnapshot:
        """The advertiser's snapshot, syncing or extending it as needed."""
        lock = self._locks.setdefault(advertiser_id, asyncio.Lock())

        async with lock:
            # Re-checked inside the lock: ten concurrent first requests should
            # produce one sync, not ten. Without this a cold advertiser under
            # load fans out ~7 MCP calls per in-flight request.
            snapshot = self._snapshots.get(advertiser_id)
            expired = self._is_expired(advertiser_id)

            if snapshot is None or force or expired:
                snapshot = await self._sync(advertiser_id, mcp, snapshot, market)

            if market:
                code = normalize_market(market)
                if code not in snapshot.data.available_deals:
                    ingestor = RegistryIngestor(mcp)
                    snapshot = await ingestor.sync_market(snapshot, code)
                    self._store(advertiser_id, snapshot, touch=False)

            return snapshot

    def invalidate(self, advertiser_id: str | None = None) -> None:
        """Forget cached snapshots so the next read re-syncs from scratch.

        Forgets the lineage too, so the next snapshot is version 1 / INITIAL.
        That is the intended meaning of invalidation - use `force=True` on `get`
        to re-fetch while keeping the version history and the diff.
        """
        if advertiser_id is None:
            self._snapshots.clear()
            self._fetched_at.clear()
            return
        self._snapshots.pop(advertiser_id, None)
        self._fetched_at.pop(advertiser_id, None)

    # --- internal ---

    async def _sync(
        self,
        advertiser_id: str,
        mcp: MCPClient,
        previous: GroundedRegistrySnapshot | None,
        market: str | None,
    ) -> GroundedRegistrySnapshot:
        """Sync, and serve the previous snapshot if this one fails.

        Reference data twenty minutes stale beats the planning flow going down,
        so a failed refresh downgrades to stale rather than propagating. A cold
        advertiser has nothing to fall back to, so its failure does propagate -
        grounding against nothing would reject every value the trader named.
        """
        ingestor = RegistryIngestor(mcp, get_settings())

        # A refresh must re-fetch every market the previous snapshot held, not
        # only the one being asked for. Otherwise a refresh silently drops the
        # others - and the diff then reports them as removed, classifying a
        # routine TTL expiry as a breaking change.
        markets = (
            sorted(
                {*(previous.markets_loaded() if previous else ()), *([market] if market else ())}
            )
            or None
        )

        try:
            snapshot = await ingestor.sync(markets=markets, previous=previous)
        except (RegistrySyncError, MCPError) as exc:
            if previous is None:
                raise
            logger.error(
                "registry.refresh_failed",
                extra=kv(
                    advertiser_id=advertiser_id,
                    reason=str(exc),
                    action="serving previous snapshot as stale",
                ),
            )
            stale = previous.model_copy(
                update={"meta": previous.meta.model_copy(update={"is_stale": True})}
            )
            self._store(advertiser_id, stale, touch=True)
            return stale

        self._store(advertiser_id, snapshot, touch=True)
        return snapshot

    def _store(
        self, advertiser_id: str, snapshot: GroundedRegistrySnapshot, *, touch: bool
    ) -> None:
        self._snapshots[advertiser_id] = snapshot
        if touch:
            self._fetched_at[advertiser_id] = time.monotonic()

    def _is_expired(self, advertiser_id: str) -> bool:
        fetched = self._fetched_at.get(advertiser_id)
        if fetched is None:
            return True
        return (time.monotonic() - fetched) > self.ttl_seconds


# Process-wide store. One per process is right while the cache is in-process;
# when Postgres persistence lands this becomes the place the backend is chosen,
# the way `create_checkpointer` does it.
_store: InMemoryRegistryStore | None = None


def get_store() -> InMemoryRegistryStore:
    global _store
    if _store is None:
        _store = InMemoryRegistryStore()
    return _store


async def get_registry(
    advertiser_id: str,
    mcp: MCPClient,
    *,
    market: str | None = None,
    force: bool = False,
) -> GroundedRegistrySnapshot:
    """The grounded snapshot for this advertiser, built on first use.

    The entry point every consumer should use. Pass `market` when a market is
    known, so its facets are loaded in the same call rather than on a later one.
    """
    return await get_store().get(advertiser_id, mcp, market=market, force=force)


class AdvertiserRegistry:
    """What a graph node holds: advertiser and MCP client already bound.

    A node cannot be handed a materialized snapshot at graph-build time. The
    market comes out of the conversation, per-market facets load lazily, and the
    graph is compiled once per advertiser and then cached for the life of the
    process - so a snapshot bound at build time would be both market-less and
    permanently stale. Binding the *accessor* instead keeps the TTL, the
    single-flight lock and the lazy market fill all working.

    Mirrors how `mcp` is bound into the node factories, and is the object
    `build_graph(registry=...)` expects.
    """

    def __init__(
        self, advertiser_id: str, mcp: MCPClient, store: InMemoryRegistryStore | None = None
    ):
        self.advertiser_id = advertiser_id
        self.mcp = mcp
        self._store = store or get_store()

    async def snapshot(self, market: str | None = None) -> GroundedRegistrySnapshot:
        """Grounded reference data, with `market`'s facets loaded if named.

        **A read, not a sync.** Every call returns a snapshot; a *fetch* happens
        only on a cache miss, a TTL expiry, or the first time a market is asked
        for. So a `registry.sync` log line appears on the first turn of a
        conversation and usually on no other, while every turn still reads
        grounded data before it plans. Reviewers have read the absence of that
        line as the registry not being consulted - it means the opposite.

        Re-ingesting per turn would cost eight MCP calls a turn and, worse, let
        deal prices move underneath a trader mid-conversation, so that a plan
        summarised on turn two no longer matched the one forecast on turn four.
        `tests/component/agent/test_planning_graph.py` pins the behaviour.
        """
        return await self._store.get(self.advertiser_id, self.mcp, market=market)

    async def validator(self, market: str | None = None) -> StepwiseCTVValidator:
        """A validator bound to the current snapshot.

        Built per call rather than cached: it holds a snapshot, and a validator
        outliving the snapshot it grounds against would validate today's plan
        against last week's rate card.
        """
        return StepwiseCTVValidator(await self.snapshot(market), self.mcp)
