"""The grounded registry: where "is this value real?" gets an answer.

`VOW_Strategy_Schema_v2.md` section 1 opens with the Zero-Hallucination Policy -
*"The agent NEVER invents strategy parameters, metrics, targeting criteria, or
deal IDs. It only populates values verified against the VOW database and REST
APIs."* This package is the machinery that makes that enforceable rather than
aspirational.

MCP stays the source of truth. The registry sits between it and everything else:

    MCP server
        |  fetch
    RegistryIngestor        one mapper per source tool
        |  field-map (AliasChoices) + normalize (field validators)
    SnapshotValidator       required fields, types, references, versioning
        |  valid                              |  invalid
    GroundedRegistrySnapshot           RegistryValidationError
        |                                     + meta.integrity_warnings
    StepwiseCTVValidator -> nodes, and eventually the UI

What each module owns:

  * `models`     - the vocabulary. Enums transcribed from schema section 5,
                   normalizers that resolve every naming disagreement, and the
                   frozen snapshot itself.
  * `ingestion`  - fetch, map, cache. Two-phase (core once, markets lazily),
                   per-advertiser, degrade-not-die.
  * `validate`   - the two gates: `SnapshotValidator` at ingest,
                   `StepwiseCTVValidator` during the conversation. Plus the
                   flow's pricing, which has exactly one home here.
  * `targeting`  - the config-driven targeting types, declared in
                   `data/targeting_types.json` because section 3 step 5 requires
                   that adding one not be a code change.

**Layering rule.** `app.knowledge` may import `app.tools.mcp`; nothing in
`app.tools` may import `app.knowledge`. The mock MCP server therefore holds tier
strings as literals rather than importing the enum, and
`tests/contract/test_registry_contract.py` asserts the two agree.

**Not persisted yet.** `config.py` names "KNW registry" against `database_url`,
and `InMemoryRegistryStore` is the seam for it - but a snapshot is derived data
rebuildable in a handful of tool calls, and `use_memory_checkpointer` defaults to
True, so the service runs with no database at all today. Requiring one here would
make Postgres mandatory for the first time in exchange for no current capability.
While that is deferred, `meta.version` is process-local.

**How the graph reaches it.** `build_graph` binds an `AdvertiserRegistry` into the
node factories the way it binds the MCP client. Nodes call
`await registry.snapshot(market)` for facts and `await registry.validator(market)`
for judgements. They are handed the accessor rather than a snapshot because the
market comes out of the conversation, per-market facets load lazily, and a graph
is compiled once per advertiser and then cached for the life of the process.

`predict_reach` still calls MCP directly, and correctly so: a forecast is a
computation about one plan's budget and audience, not reference data. Putting it
behind a cache would be the fastest way to serve a stale reach number.
"""

from app.knowledge.registry.ingestion import (
    AdvertiserRegistry,
    InMemoryRegistryStore,
    RegistryIngestor,
    get_registry,
    get_store,
)
from app.knowledge.registry.models import (
    REGISTRY_SCHEMA_VERSION,
    AudienceProfileEnum,
    AudienceProfileItem,
    BudgetSplitMethodEnum,
    CurrencyEnum,
    DealItem,
    DurationEnum,
    GoalEnum,
    GroundedRegistryData,
    GroundedRegistrySnapshot,
    InventoryTierEnum,
    KPIEnum,
    MarketTargetingConfig,
    NormalizationError,
    ProductCategory,
    RateCardEntry,
    RegistryDiff,
    RegistrySnapshotMeta,
    TargetingOption,
    ValidationResponse,
)
from app.knowledge.registry.validate import (
    SnapshotValidator,
    StepwiseCTVValidator,
    assert_grounded,
    calculate_effective_cpm,
    cheapest_amazon_cpm,
    impressions_for,
)

__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "AdvertiserRegistry",
    "AudienceProfileEnum",
    "AudienceProfileItem",
    "BudgetSplitMethodEnum",
    "CurrencyEnum",
    "DealItem",
    "DurationEnum",
    "GoalEnum",
    "GroundedRegistryData",
    "GroundedRegistrySnapshot",
    "InMemoryRegistryStore",
    "InventoryTierEnum",
    "KPIEnum",
    "MarketTargetingConfig",
    "NormalizationError",
    "ProductCategory",
    "RateCardEntry",
    "RegistryDiff",
    "RegistryIngestor",
    "RegistrySnapshotMeta",
    "SnapshotValidator",
    "StepwiseCTVValidator",
    "TargetingOption",
    "ValidationResponse",
    "assert_grounded",
    "calculate_effective_cpm",
    "cheapest_amazon_cpm",
    "get_registry",
    "get_store",
    "impressions_for",
]
