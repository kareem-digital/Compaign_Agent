"""The registry's vocabulary: enums, normalizers, and the snapshot itself.

Three jobs, in the order data passes through them.

**Enums** carry the values from `VOW_Strategy_Schema_v2.md` section 5 (lines
469-538), which is the cross-lane contract. A change to a *value* is a contract
change and needs all three lanes, so they are not to be tidied. In particular:
`GoalEnum.AWARENESS` is upper-case while `KPIEnum.REACH` is lower-case. That
asymmetry is in the contract and in live state - `extract_fields` already writes
`{"goal": "AWARENESS", "kpi": "reach"}` - so normalising the casing here would
silently break the state contract.
`tests/contract/test_registry_contract.py` holds the documented values as a
literal table and fails if any of them move.

The declarations use `StrEnum` where the document writes `(str, Enum)`. Same
values, and it removes a real hazard: `f"{tier}"` on a `(str, Enum)` member
renders `InventoryTierEnum.AMAZON_OWNED` rather than `AMAZON_OWNED`, and these
values end up in prose the trader reads.

**Normalizers** are the single place every naming conflict is resolved. VOW's
server, the mock, and a trader's brief all spell things differently ("UK" vs
"GB", "Broad" vs "WIDE", "Even by budget" vs "EVEN_BY_BUDGET"). Each normalizer
accepts the variants and returns exactly one canonical value, or raises. It
never guesses: a value nobody recognises is a grounding failure, and guessing is
what the zero-hallucination policy (section 1) forbids.

**Models** carry the normalized values. Two decisions worth knowing:

  * Field mapping is `AliasChoices`, not hand-written rename dicts. The
    `external_deal_id` vs `deal_id` and `deal_price_amount` vs `rate_card_cpm`
    disagreements collapse into one alias tuple per field, checked by pydantic,
    so no renaming code exists to drift.
  * Money is `Decimal`, quantized to 2dp. `18.22 + 3.50` in binary float is not
    `21.72`, and effective CPM (section 2.4) is the number a trader commits
    budget against. It is serialized back to a string at the boundary, because
    the LangGraph checkpointer serializes state and `Decimal` is not JSON-native.

What is deliberately absent: a reach curve. A curve is a function of budget,
audience and flight dates - a forecast, not reference data. `ReachCurvePoint`
exists only as a shape for validating what `vow.reach_forecast` returns.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

# Bumped by hand when a model change is not backward-compatible. Stamped on
# every snapshot so a log line about a rejected payload can name the contract
# that produced it.
REGISTRY_SCHEMA_VERSION = "1"

MONEY = Decimal("0.01")


# --- enums (VOW_Strategy_Schema_v2.md section 5) ------------------------------


class GoalEnum(StrEnum):
    """For CTV M1 only AWARENESS is used - section 3 step 1."""

    AWARENESS = "AWARENESS"
    CONSIDERATION = "CONSIDERATION"
    CONVERSION = "CONVERSION"


class KPIEnum(StrEnum):
    """Values are lower-case. For CTV M1 only reach and frequency are in scope."""

    REACH = "reach"
    FREQUENCY = "frequency"
    CTR = "ctr"
    CPC = "cpc"
    CPA = "cpa"
    CPDPV = "cpdpv"


class CurrencyEnum(StrEnum):
    EUR = "EUR"
    GBP = "GBP"
    USD = "USD"


class DurationEnum(StrEnum):
    """Creative durations in seconds, as strings - `state.durations` is list[str]."""

    TEN = "10"
    FIFTEEN = "15"
    TWENTY = "20"
    THIRTY = "30"


class FormatEnum(StrEnum):
    """For CTV M1 only streaming_tv and prime_video."""

    DISPLAY = "display"
    ONLINE_VIDEO = "online_video"
    STREAMING_TV = "streaming_tv"
    PRIME_VIDEO = "prime_video"


class InventoryTierEnum(StrEnum):
    """The three tiers driving the flow's primary fork - section 2.3."""

    AMAZON_OWNED = "AMAZON_OWNED"
    THIRD_PARTY_PRECURATED = "THIRD_PARTY_PRECURATED"
    THIRD_PARTY_NEEDS_CURATION = "THIRD_PARTY_NEEDS_CURATION"


class AudienceProfileEnum(StrEnum):
    """ "Broad" was renamed Wide in v2 - section 2.4."""

    NARROW = "NARROW"
    BALANCED = "BALANCED"
    WIDE = "WIDE"


class BudgetSplitMethodEnum(StrEnum):
    EVEN_BY_BUDGET = "EVEN_BY_BUDGET"
    EVEN_BY_IMPRESSIONS = "EVEN_BY_IMPRESSIONS"
    CUSTOM = "CUSTOM"


class ApprovalStatusEnum(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# --- static reference data ---------------------------------------------------
#
# Not ingested, because section 5 fixes these as enums. Pretending they need a
# tool call would invent server surface that does not exist. The integrity check
# in `validate.py` asserts every ingested market has a currency here.

# The one market alias worth keeping. `extract_fields._MARKET_PATTERNS` owns the
# linguistic variants ("britain", "u.k.", "england") - those are NLP, not
# reference data, and the registry has no business holding regexes.
MARKET_ALIASES = {"UK": "GB"}

CURRENCY_BY_MARKET = {"GB": "GBP", "US": "USD", "FR": "EUR", "DE": "EUR"}

# Section 3 step 4: "Similar vs Exact". Section 5 line 664 leaves this a bare
# `str` defaulting to "Exact", so there is no enum to mirror - inventing one is
# how lanes drift apart.
MATCHING_MODES = ("Similar", "Exact")

# How a tier is described to a trader. One definition, because both the
# inventory summary the agent speaks and the validator's metadata quote it, and
# two copies would eventually disagree about what a tier promises.
TIER_LABELS = {
    InventoryTierEnum.AMAZON_OWNED: "Amazon-owned (reach forecast available)",
    InventoryTierEnum.THIRD_PARTY_PRECURATED: "third-party, pre-curated (no reach forecast)",
    InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION: "third-party, needs curation (rate card only)",
}

# Amazon first: it is the only tier that unlocks forecasting, so when a plan
# mixes tiers it is the one that decides which capabilities are in play.
TIER_PRECEDENCE = (
    InventoryTierEnum.AMAZON_OWNED,
    InventoryTierEnum.THIRD_PARTY_PRECURATED,
    InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION,
)


def duration_phrase(conjunction: str = "or") -> str:
    """The sellable creative lengths as prose: "10, 15, 20 or 30".

    One builder, because this list is read by a trader in three different places
    - the gate's follow-up question, the LLM's extraction rules, and the
    validator's rejection message. Written out, each would have to be found and
    edited the day CTV starts selling a new length, and whichever was missed
    would be the agent stating something untrue.
    """
    values = [d.value for d in DurationEnum]
    return f"{', '.join(values[:-1])} {conjunction} {values[-1]}"


# Display copy for the split methods. Kept apart from the stored values so
# "Even by budget" can never end up in a payload.
BUDGET_SPLIT_LABELS = {
    BudgetSplitMethodEnum.EVEN_BY_BUDGET: "Even by budget",
    BudgetSplitMethodEnum.EVEN_BY_IMPRESSIONS: "Even by impressions",
    BudgetSplitMethodEnum.CUSTOM: "Custom",
}

# For CTV M1, per section 3 step 1.
CTV_GOALS = frozenset({GoalEnum.AWARENESS.value})
CTV_KPIS = frozenset({KPIEnum.REACH.value, KPIEnum.FREQUENCY.value})
CTV_FORMATS = frozenset({FormatEnum.STREAMING_TV.value, FormatEnum.PRIME_VIDEO.value})


# --- normalizers -------------------------------------------------------------


class NormalizationError(ValueError):
    """A value could not be mapped onto the registry's canonical vocabulary."""


_ISO_MARKET = re.compile(r"^[A-Z]{2}$")


def normalize_market(value: str) -> str:
    """ISO-3166 alpha-2, with `UK` mapped to `GB`.

    Section 7.1 is explicit that a brief saying "UK" becomes `markets: ["GB"]`,
    and `MockMCPClient` defaults to `GB`. Storing both spellings would mean every
    consumer comparing against two.
    """
    candidate = str(value or "").strip().upper()
    candidate = MARKET_ALIASES.get(candidate, candidate)

    if not _ISO_MARKET.match(candidate):
        raise NormalizationError(f"{value!r} is not an ISO-3166 alpha-2 market code")
    return candidate


def normalize_duration(value: str | int) -> str:
    """`30`, `"30"`, `"30s"`, `"30 sec"`, `"30 seconds"` all become `"30"`."""
    digits = re.sub(r"[^\d]", "", str(value or ""))
    if digits not in {d.value for d in DurationEnum}:
        raise NormalizationError(
            f"{value!r} is not a supported creative duration "
            f"({', '.join(d.value for d in DurationEnum)})"
        )
    return digits


def normalize_currency(value: str) -> str:
    candidate = str(value or "").strip().upper()
    if candidate not in {c.value for c in CurrencyEnum}:
        raise NormalizationError(f"{value!r} is not a supported currency")
    return candidate


def normalize_goal(value: str) -> str:
    """Upper-case, matching `GoalEnum`'s values."""
    candidate = str(value or "").strip().upper()
    if candidate not in {g.value for g in GoalEnum}:
        raise NormalizationError(f"{value!r} is not a recognised goal")
    return candidate


def normalize_kpi(value: str) -> str:
    """Lower-case, matching `KPIEnum`'s values and what `extract_fields` writes."""
    candidate = str(value or "").strip().lower()
    if candidate not in {k.value for k in KPIEnum}:
        raise NormalizationError(f"{value!r} is not a recognised KPI")
    return candidate


def normalize_format(value: str) -> str:
    candidate = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if candidate not in {f.value for f in FormatEnum}:
        raise NormalizationError(f"{value!r} is not a recognised format")
    return candidate


# `BROAD` is the one audience alias worth accepting: section 3 step 4 flags the
# live suggest endpoint's response shape as unconfirmed and notes it may return
# `bundles.narrow/balanced/broad`.
_PROFILE_ALIASES = {"BROAD": AudienceProfileEnum.WIDE.value}


def normalize_profile(value: str) -> str:
    candidate = str(value or "").strip().upper()
    candidate = _PROFILE_ALIASES.get(candidate, candidate)
    if candidate not in {p.value for p in AudienceProfileEnum}:
        raise NormalizationError(f"{value!r} is not a recognised audience profile")
    return candidate


# The short forms are what a draft schema used before the tiers were named in
# section 5. Accepted on input so a server using them still works; never stored.
_TIER_ALIASES = {
    "3P_PRE_CURATED": InventoryTierEnum.THIRD_PARTY_PRECURATED.value,
    "3P_PRECURATED": InventoryTierEnum.THIRD_PARTY_PRECURATED.value,
    "3P_NEEDS_CURATION": InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION.value,
    "AMAZON": InventoryTierEnum.AMAZON_OWNED.value,
}


def normalize_tier(value: str) -> str:
    candidate = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    candidate = _TIER_ALIASES.get(candidate, candidate)
    if candidate not in {t.value for t in InventoryTierEnum}:
        raise NormalizationError(f"{value!r} is not a recognised inventory tier")
    return candidate


def normalize_split_method(value: str) -> str:
    """Accepts the display label ("Even by budget") and returns the enum value."""
    candidate = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if candidate not in {m.value for m in BudgetSplitMethodEnum}:
        raise NormalizationError(f"{value!r} is not a recognised budget split method")
    return candidate


def normalize_matching_mode(value: str) -> str:
    """Title-case, matching `MATCHING_MODES`."""
    candidate = str(value or "").strip().title()
    if candidate not in MATCHING_MODES:
        raise NormalizationError(f"{value!r} is not a recognised matching mode")
    return candidate


def to_money(value: Any) -> Decimal:
    """A CPM or fee as a 2dp `Decimal`.

    Goes through `str()` rather than accepting a float directly: `Decimal(18.22)`
    from a float carries the binary approximation into the arithmetic, which is
    the thing this function exists to avoid.
    """
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise NormalizationError(f"{value!r} is not a valid monetary amount") from exc


def money_str(value: Decimal) -> str:
    """Money for the wire and for prose: `"21.72"`.

    Every value crossing out of the registry goes through here, so nothing
    downstream has to know about `Decimal` and no f-string ever renders
    `Decimal('18.22')`.
    """
    return f"{value.quantize(MONEY, rounding=ROUND_HALF_UP):f}"


# --- facet models ------------------------------------------------------------

_FROZEN = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")


class DealItem(BaseModel):
    """One selectable CTV deal, tier resolved.

    `cpm` is this deal's negotiated or floor price, which is NOT the market rate
    card - see `RateCardEntry`. Conflating them would break the genre upsell
    (section 3 step 2: Prime ROS at 18.22 vs Action at 22.07), which compares
    two deal prices.
    """

    model_config = _FROZEN

    deal_id: str = Field(validation_alias=AliasChoices("deal_id", "external_deal_id", "id"))
    name: str
    provider: str
    cpm: Decimal = Field(
        validation_alias=AliasChoices("cpm", "deal_price_amount", "rate_card_cpm", "price")
    )
    deal_type: str = ""
    genre: str | None = None
    ad_lengths: tuple[str, ...] = Field(
        default=(), validation_alias=AliasChoices("ad_lengths", "available_durations", "durations")
    )
    devices: tuple[str, ...] = ()
    inventory_tier: InventoryTierEnum
    market: str

    @field_validator("cpm", mode="before")
    @classmethod
    def _money(cls, value):
        return to_money(value)

    @field_validator("ad_lengths", mode="before")
    @classmethod
    def _durations(cls, value):
        return tuple(normalize_duration(d) for d in (value or ()))

    @field_validator("inventory_tier", mode="before")
    @classmethod
    def _tier(cls, value):
        return normalize_tier(value)

    @field_validator("market", mode="before")
    @classmethod
    def _market(cls, value):
        return normalize_market(value)

    @field_serializer("cpm")
    def _cpm_out(self, value: Decimal) -> str:
        return money_str(value)

    @property
    def supports_reach_forecast(self) -> bool:
        """Derived, never stored.

        A stored flag can contradict the tier, and the flow branches on this in
        two places - section 3 step 6's honesty rule is only honest if there is
        one answer.
        """
        return self.inventory_tier is InventoryTierEnum.AMAZON_OWNED


class RateCardEntry(BaseModel):
    """One (provider, duration, CPM) row of a market's rate card.

    Flattened from VOW's nested `channels[].durations[]` payload on purpose: the
    nested shape forces every consumer into the same double loop that
    `select_inventory` already writes to find which durations a market carries.
    """

    model_config = _FROZEN

    provider: str
    duration: str
    cpm: Decimal

    @field_validator("cpm", mode="before")
    @classmethod
    def _money(cls, value):
        return to_money(value)

    @field_validator("duration", mode="before")
    @classmethod
    def _duration(cls, value):
        return normalize_duration(value)

    @field_serializer("cpm")
    def _cpm_out(self, value: Decimal) -> str:
        return money_str(value)


class AudienceProfileItem(BaseModel):
    """One of the three mandatory audience options - section 3 step 4.

    `vcpm_fee` stacks on top of a deal's CPM. Narrow is both smaller and dearer,
    which is the point traders most often miss, so the fee travels with the
    profile rather than being looked up separately.
    """

    model_config = _FROZEN

    audience_set_id: str
    name: str
    profile: AudienceProfileEnum
    vcpm_fee: Decimal
    segment_count: int = 0
    estimated_size: int = 0

    @field_validator("vcpm_fee", mode="before")
    @classmethod
    def _money(cls, value):
        return to_money(value)

    @field_validator("profile", mode="before")
    @classmethod
    def _profile(cls, value):
        return normalize_profile(value)

    @field_serializer("vcpm_fee")
    def _fee_out(self, value: Decimal) -> str:
        return money_str(value)


class ProductCategory(BaseModel):
    """Contextual product category. `id` is an int - section 5 line 648."""

    model_config = _FROZEN

    id: int
    name: str


class TargetingOptionValue(BaseModel):
    """One pickable value of a targeting type."""

    model_config = _FROZEN

    id: str
    label: str


class TargetingOption(BaseModel):
    """One targeting type and the values available for it in a market.

    Declared in `data/targeting_types.json`, not in this file. Section 3 step 5:
    "This targeting list frequently changes so it should be easy to add new
    targeting types" - so a new type must be data, not a new model field.
    """

    model_config = _FROZEN

    key: str
    label: str
    cardinality: Literal["single", "multi"] = "multi"
    required: bool = False
    values: tuple[TargetingOptionValue, ...] = ()

    def value_ids(self) -> frozenset[str]:
        return frozenset(v.id for v in self.values)


class MarketTargetingConfig(BaseModel):
    """A market's targeting surface, keyed by type.

    An open dict, which is what makes the config-driven requirement achievable -
    five named fields would mean a code change per new targeting type.
    """

    model_config = _FROZEN

    market: str
    options: dict[str, TargetingOption] = Field(default_factory=dict)


class StrategyNameRules(BaseModel):
    """Local checks that save a round trip before asking VOW about uniqueness."""

    model_config = _FROZEN

    max_length: int = 120
    allowed_pattern: str = r"^[\w\s\-|.,()&/]+$"
    case_sensitive: bool = False


class ReachCurvePoint(BaseModel):
    """A point on a forecast reach curve.

    A validation shape only - deliberately NOT part of any snapshot. A curve
    depends on budget, audience and flight dates, so a canned one sitting in
    something called "grounded" is exactly the artefact that eventually gets
    presented to a trader as a forecast. Section 1's zero-hallucination policy
    and `predict_reach`'s refusal to invent reach both depend on it not existing.
    """

    model_config = _FROZEN

    budget: Decimal
    reach: int
    is_indicative: bool = True

    @field_validator("budget", mode="before")
    @classmethod
    def _money(cls, value):
        return to_money(value)

    @field_serializer("budget")
    def _budget_out(self, value: Decimal) -> str:
        return money_str(value)


# --- the snapshot ------------------------------------------------------------


class GroundedRegistryData(BaseModel):
    """Everything steps 1-7 need in order to ground a value, for one advertiser.

    Frozen: a snapshot a consumer can mutate is not grounded. A refresh produces
    a new one rather than editing this.

    Split into core facets (market-independent, synced once) and per-market
    facets (filled lazily on first use), because deals, rate cards, categories
    and targeting are all market-scoped and eager-fetching every market costs
    four calls each.

    Sets are `frozenset` but serialize sorted - see `_sorted_set`. Without that
    the content hash is unstable across processes and every sync looks like a
    change, which would make the whole versioning story noise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- core: step 1 basics ---
    valid_markets: frozenset[str] = frozenset()
    valid_currencies: frozenset[str] = frozenset()
    valid_durations: frozenset[str] = frozenset()
    allowed_goals: frozenset[str] = frozenset()
    allowed_kpis: frozenset[str] = frozenset()
    allowed_formats: frozenset[str] = frozenset()
    strategy_name_rules: StrategyNameRules = Field(default_factory=StrategyNameRules)

    # --- core: step 2 inventory ---
    tier_by_provider: dict[str, InventoryTierEnum] = Field(default_factory=dict)
    curation_genres: frozenset[str] = frozenset()

    # --- core: step 3 budget split ---
    supported_split_methods: frozenset[str] = frozenset()

    # --- core: step 4 audiences ---
    audience_profiles: dict[str, AudienceProfileItem] = Field(default_factory=dict)
    matching_modes: frozenset[str] = frozenset()

    # --- per-market ---
    available_deals: dict[str, tuple[DealItem, ...]] = Field(default_factory=dict)
    rate_cards: dict[str, tuple[RateCardEntry, ...]] = Field(default_factory=dict)
    product_categories: dict[str, tuple[ProductCategory, ...]] = Field(default_factory=dict)
    market_targeting_configs: dict[str, MarketTargetingConfig] = Field(default_factory=dict)

    @field_serializer(
        "valid_markets",
        "valid_currencies",
        "valid_durations",
        "allowed_goals",
        "allowed_kpis",
        "allowed_formats",
        "curation_genres",
        "supported_split_methods",
        "matching_modes",
    )
    def _sorted_set(self, value: frozenset[str]) -> list[str]:
        """Sets serialize sorted, so the content hash is deterministic.

        Python's set iteration order varies with hash randomisation between
        processes. Unsorted, two identical snapshots in two workers would hash
        differently and every sync would classify as a change.
        """
        return sorted(value)

    # --- accessors, so consumers never re-implement these ---

    def deals(self, market: str) -> tuple[DealItem, ...]:
        return self.available_deals.get(normalize_market(market), ())

    def deal_by_id(self, market: str, deal_id: str) -> DealItem | None:
        return next((d for d in self.deals(market) if d.deal_id == deal_id), None)

    def amazon_deals(self, market: str) -> tuple[DealItem, ...]:
        return tuple(d for d in self.deals(market) if d.supports_reach_forecast)

    def carried_durations(self, market: str) -> frozenset[str]:
        """Durations the market's rate card actually sells.

        The rate card is the authority here, not the deal list - a plan asking
        for a duration the market does not carry is a planning error worth
        catching during planning.
        """
        return frozenset(entry.duration for entry in self.rate_cards.get(market, ()))

    def targeting(self, market: str) -> MarketTargetingConfig | None:
        return self.market_targeting_configs.get(normalize_market(market))

    def currency_for(self, market: str) -> str | None:
        return CURRENCY_BY_MARKET.get(normalize_market(market))

    def content_hash(self) -> str:
        """sha256 of the canonical JSON form. Identity, not integrity.

        Used to decide whether a sync actually changed anything, so it must be
        stable across processes - which is what the sorted-set serializer above
        guarantees.
        """
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode()).hexdigest()


# --- provenance --------------------------------------------------------------


class RejectedItem(BaseModel):
    """One row that failed validation, kept so a reviewer can see what and why."""

    model_config = _FROZEN

    source: str
    reason: str
    identifier: str | None = None


class RegistryDiff(BaseModel):
    """What changed between two snapshots, as dotted paths.

    Paths rather than nested structures because the consumer is a log line and a
    reviewer, not code: `available_deals.GB.EXTNFLX0012` reads at a glance.
    """

    model_config = _FROZEN

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    type_changed: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.type_changed)


Compatibility = Literal["INITIAL", "IDENTICAL", "ADDITIVE", "BREAKING"]


class RegistrySnapshotMeta(BaseModel):
    """Where a snapshot came from and what happened on the way in.

    Carried on the snapshot rather than logged only, so nothing has to be
    reconstructed after the fact when someone asks why a market is missing.
    """

    model_config = _FROZEN

    schema_version: str = REGISTRY_SCHEMA_VERSION
    version: int = 1
    content_hash: str = ""
    synced_at: datetime
    source: Literal["mock", "live"] = "mock"
    compatibility: Compatibility = "INITIAL"
    diff: RegistryDiff = Field(default_factory=RegistryDiff)
    degraded_sources: tuple[str, ...] = ()
    rejected_items: tuple[RejectedItem, ...] = ()
    integrity_warnings: tuple[str, ...] = ()
    # False when an optional source degraded: usable, but not the whole picture.
    is_complete: bool = True
    # True when a refresh failed and this is the previous snapshot being served
    # anyway. Reference data twenty minutes stale beats the flow going down.
    is_stale: bool = False


class GroundedRegistrySnapshot(BaseModel):
    """An advertiser's grounded reference data, with its provenance."""

    model_config = ConfigDict(frozen=True)

    advertiser_id: str
    data: GroundedRegistryData
    meta: RegistrySnapshotMeta

    def markets_loaded(self) -> tuple[str, ...]:
        """Markets whose per-market facets have been fetched."""
        return tuple(sorted(self.data.available_deals))

    def provenance(self) -> dict:
        """The part of `meta` a trader may see, JSON-native.

        Enumerated rather than dumped, and that is the whole point. `meta` also
        carries `degraded_sources` (literally MCP tool names, which map 1:1 to
        VOW's internal endpoints), `rejected_items` (whose `reason` is built from
        `str(exc)` on a pydantic error, carrying the failing field path and the raw
        input value), `integrity_warnings` (reliability commentary about VOW's own
        feed) and `diff` (which enumerates deal IDs). All four are operator
        diagnostics, all four are already logged in `_finalize`, and none is an
        answer to anything a trader asked. Enumerating means a field added to
        `RegistrySnapshotMeta` tomorrow cannot leak through this door by default.

        `markets_loaded` rides along because "which snapshot" is not a complete
        answer without "covering what" - a version for a snapshot that never
        fetched FR does not explain an FR answer.

        `synced_at` as a string because this goes onto the graph state, which the
        checkpointer serializes - the same discipline as `select_inventory._as_state`
        keeping money out of `Decimal`.
        """
        return {
            "schema_version": self.meta.schema_version,
            "version": self.meta.version,
            "content_hash": self.meta.content_hash,
            "synced_at": self.meta.synced_at.isoformat(),
            "source": self.meta.source,
            "markets_loaded": list(self.markets_loaded()),
            "is_complete": self.meta.is_complete,
            "is_stale": self.meta.is_stale,
        }


# --- the answer a validator gives -------------------------------------------


class ValidationResponse(BaseModel):
    """One validation outcome, phrased for the trader.

    `message` is prose, not a code, because `gates.py` is explicit that these
    strings end up in the question the agent asks: "requirements are described in
    the trader's language, not the schema's". A node appends it straight onto
    `validation_errors` with no translation layer.

    `code` is the machine-readable half, for the UI. `severity="warning"` lets a
    normalization pass with a note - "I read UK as GB" is worth saying, not worth
    blocking on.
    """

    is_valid: bool
    message: str
    code: str = ""
    severity: Literal["error", "warning"] = "error"
    field: str | None = None
    suggested_options: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @property
    def blocks(self) -> bool:
        """Whether this should stop the flow, as opposed to just being said."""
        return not self.is_valid and self.severity == "error"
