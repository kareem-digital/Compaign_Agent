"""Tests for the ingest-time gate: integrity, diff, compatibility, versioning.

This is the half of validation that protects the registry from VOW rather than
the trader from a mistake. Its job is to notice when the server's reference data
stops making sense - a deal in a market that does not exist, a duration nobody
sells, a facet that has disappeared since the last sync.

The compatibility classifier carries the load: additive changes swap in quietly,
removals and type changes are breaking, and a moved price is neither, because an
alarm that fires every time a CPM updates is an alarm nobody reads.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import RegistryValidationError
from app.knowledge.registry.models import (
    AudienceProfileItem,
    DealItem,
    GroundedRegistryData,
    MarketTargetingConfig,
    RateCardEntry,
    RegistrySnapshotMeta,
)
from app.knowledge.registry.validate import SnapshotValidator

CHECKS = SnapshotValidator()


# --- helpers -----------------------------------------------------------------


def _deal(deal_id: str = "EXTQ5", **overrides) -> DealItem:
    payload = {
        "external_deal_id": deal_id,
        "name": f"Prime Video | {deal_id}",
        "provider": "Prime Video",
        "deal_price_amount": "18.22",
        "ad_lengths": ["15", "30"],
        "inventory_tier": "AMAZON_OWNED",
        "market": "GB",
        **overrides,
    }
    return DealItem.model_validate(payload)


def _profiles() -> dict[str, AudienceProfileItem]:
    return {
        name: AudienceProfileItem.model_validate(
            {
                "audience_set_id": f"aud-{name.lower()}",
                "name": name.title(),
                "profile": name,
                "vcpm_fee": fee,
            }
        )
        for name, fee in (("NARROW", "3.50"), ("BALANCED", "2.00"), ("WIDE", "0.85"))
    }


def _data(**overrides) -> GroundedRegistryData:
    """A snapshot that passes every check, so a test can break exactly one thing."""
    defaults = {
        "valid_markets": frozenset({"GB"}),
        "valid_currencies": frozenset({"GBP"}),
        "valid_durations": frozenset({"15", "30"}),
        "allowed_goals": frozenset({"AWARENESS"}),
        "allowed_kpis": frozenset({"reach", "frequency"}),
        "audience_profiles": _profiles(),
        "tier_by_provider": {"Prime Video": "AMAZON_OWNED"},
        "available_deals": {"GB": (_deal(),)},
        "rate_cards": {"GB": (RateCardEntry(provider="Prime Video", duration="15", cpm="18.22"),)},
    }
    return GroundedRegistryData(**{**defaults, **overrides})


def _meta(version: int, content_hash: str) -> RegistrySnapshotMeta:
    return RegistrySnapshotMeta(
        version=version, content_hash=content_hash, synced_at=datetime.now(UTC)
    )


# --- required facets ---------------------------------------------------------


def test_a_complete_snapshot_passes_the_gate() -> None:
    assert CHECKS.gate(_data()) == []


def test_no_markets_is_fatal() -> None:
    """Grounding against an empty market set would reject every market named."""
    with pytest.raises(RegistryValidationError, match="integrity"):
        CHECKS.gate(_data(valid_markets=frozenset(), available_deals={}, rate_cards={}))


def test_a_missing_audience_profile_is_fatal() -> None:
    """Section 3 step 4: three options, always. Two is a server-contract problem."""
    profiles = _profiles()
    del profiles["WIDE"]

    with pytest.raises(RegistryValidationError) as excinfo:
        CHECKS.gate(_data(audience_profiles=profiles))

    assert any("WIDE" in v for v in excinfo.value.violations)


# --- referential integrity ---------------------------------------------------


def test_deals_for_an_unknown_market_are_fatal() -> None:
    with pytest.raises(RegistryValidationError) as excinfo:
        CHECKS.gate(_data(available_deals={"US": (_deal(market="US"),)}, rate_cards={}))

    assert any("not a valid market" in v for v in excinfo.value.violations)


def test_duplicate_deal_ids_within_a_market_are_fatal() -> None:
    """Two rows claiming one ID means `deal_by_id` is a coin toss."""
    with pytest.raises(RegistryValidationError) as excinfo:
        CHECKS.gate(_data(available_deals={"GB": (_deal(), _deal())}))

    assert any("duplicate deal ID" in v for v in excinfo.value.violations)


def test_a_deal_offering_an_unsold_duration_is_fatal() -> None:
    with pytest.raises(RegistryValidationError) as excinfo:
        CHECKS.gate(_data(valid_durations=frozenset({"30"})))

    assert any("does not sell" in v for v in excinfo.value.violations)


def test_a_market_with_no_currency_mapping_is_fatal() -> None:
    """Step 1 has to be able to pick a currency for every market it accepts."""
    with pytest.raises(RegistryValidationError) as excinfo:
        CHECKS.gate(
            _data(valid_markets=frozenset({"GB", "JP"}), available_deals={"GB": (_deal(),)})
        )

    assert any("no currency mapping" in v for v in excinfo.value.violations)


def test_an_unmapped_provider_warns_rather_than_failing() -> None:
    """Safe, because the mapper already defaulted the deal to needs-curation.

    Worth saying anyway: a new provider arriving is a commercial fact somebody
    should confirm rather than discover from a plan.
    """
    warnings = CHECKS.gate(_data(tier_by_provider={}))

    assert any("has no tier from the server" in w for w in warnings)
    assert any("THIRD_PARTY_NEEDS_CURATION" in w for w in warnings)


def test_a_kpi_outside_ctv_scope_warns() -> None:
    warnings = CHECKS.gate(_data(allowed_kpis=frozenset({"reach", "ctr"})))
    assert any("outside CTV scope" in w for w in warnings)


def test_targeting_for_an_unknown_market_is_fatal() -> None:
    with pytest.raises(RegistryValidationError):
        CHECKS.gate(_data(market_targeting_configs={"US": MarketTargetingConfig(market="US")}))


# --- diff and compatibility --------------------------------------------------


def test_a_first_snapshot_is_initial_at_version_one() -> None:
    data = _data()
    diff = CHECKS.diff(None, data)

    assert diff.is_empty
    assert CHECKS.classify_compatibility(None, diff) == "INITIAL"
    assert CHECKS.next_version(None, "INITIAL", data.content_hash()) == 1


def test_identical_data_does_not_bump_the_version() -> None:
    """Version counts content changes, not syncs.

    Otherwise the number measures how often the TTL expired, which nobody wants
    to know.
    """
    before, after = _data(), _data()
    diff = CHECKS.diff(before, after)
    compatibility = CHECKS.classify_compatibility(before, diff)

    assert compatibility == "IDENTICAL"
    previous = _meta(7, before.content_hash())
    assert CHECKS.next_version(previous, compatibility, after.content_hash()) == 7


def test_a_new_market_is_additive() -> None:
    before = _data()
    after = _data(valid_markets=frozenset({"GB", "US"}))
    diff = CHECKS.diff(before, after)

    assert CHECKS.classify_compatibility(before, diff) == "ADDITIVE"
    assert (
        CHECKS.next_version(_meta(3, before.content_hash()), "ADDITIVE", after.content_hash()) == 4
    )


def test_a_removed_market_is_breaking() -> None:
    """Something a consumer could already be reading has gone."""
    before = _data(valid_markets=frozenset({"GB", "US"}))
    after = _data()
    diff = CHECKS.diff(before, after)

    assert diff.removed
    assert CHECKS.classify_compatibility(before, diff) == "BREAKING"


def test_a_changed_price_is_additive_not_breaking() -> None:
    """CPMs move. An alarm that fires on every price update is not an alarm."""
    before = _data()
    after = _data(available_deals={"GB": (_deal(deal_price_amount="18.99"),)})
    diff = CHECKS.diff(before, after)

    assert diff.changed
    assert CHECKS.classify_compatibility(before, diff) == "ADDITIVE"


def test_a_changed_vcpm_fee_is_additive() -> None:
    profiles = _profiles()
    profiles["NARROW"] = AudienceProfileItem.model_validate(
        {
            "audience_set_id": "aud-narrow",
            "name": "Narrow",
            "profile": "NARROW",
            "vcpm_fee": "4.50",
        }
    )
    before = _data()
    after = _data(audience_profiles=profiles)

    assert CHECKS.classify_compatibility(before, CHECKS.diff(before, after)) == "ADDITIVE"


def test_a_changed_tier_is_breaking() -> None:
    """A provider moving tier changes what the flow can promise about it."""
    before = _data()
    after = _data(
        tier_by_provider={"Prime Video": "THIRD_PARTY_PRECURATED"},
        available_deals={"GB": (_deal(inventory_tier="THIRD_PARTY_PRECURATED"),)},
    )
    diff = CHECKS.diff(before, after)

    assert CHECKS.classify_compatibility(before, diff) == "BREAKING"


def test_effective_cpm_inputs_survive_a_round_trip_through_the_gate() -> None:
    """The gate must not disturb the money it validates."""
    data = _data()
    CHECKS.gate(data)

    assert data.deals("GB")[0].cpm == Decimal("18.22")
    assert data.audience_profiles["NARROW"].vcpm_fee == Decimal("3.50")
