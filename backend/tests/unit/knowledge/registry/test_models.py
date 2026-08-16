"""Tests for the registry's vocabulary: normalization, field mapping, money.

These pin every naming disagreement the registry exists to absorb. If VOW, the
mock and a trader's brief spell a market three ways, exactly one spelling may
reach a snapshot - and a change that breaks that is a change to the cross-lane
contract, which should fail here rather than surface as a mismatch three layers
away.

The hostile payloads come from tests/fixtures/registry_payloads.py: an earlier
draft schema's spellings, kept as evidence that the normalizers work.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.knowledge.registry.models import (
    AudienceProfileItem,
    DealItem,
    GoalEnum,
    GroundedRegistryData,
    InventoryTierEnum,
    KPIEnum,
    NormalizationError,
    ValidationResponse,
    money_str,
    normalize_currency,
    normalize_duration,
    normalize_goal,
    normalize_kpi,
    normalize_market,
    normalize_matching_mode,
    normalize_profile,
    normalize_split_method,
    normalize_tier,
    to_money,
)
from tests.fixtures.registry_payloads import (
    CANONICAL_AUDIENCE,
    CANONICAL_DEAL,
    HOSTILE_AUDIENCE,
    HOSTILE_DEAL,
)

# --- markets -----------------------------------------------------------------


def test_uk_normalizes_to_gb() -> None:
    """Schema section 7.1: a brief saying "UK" means markets ["GB"]."""
    assert normalize_market("UK") == "GB"
    assert normalize_market("uk") == "GB"
    assert normalize_market(" Uk ") == "GB"


def test_iso_market_passes_through_uppercased() -> None:
    assert normalize_market("gb") == "GB"
    assert normalize_market("US") == "US"


def test_non_iso_market_raises_rather_than_guessing() -> None:
    """Guessing a market is what the zero-hallucination policy forbids."""
    with pytest.raises(NormalizationError, match="ISO-3166"):
        normalize_market("China")


# --- durations ---------------------------------------------------------------


def test_durations_normalize_from_every_spelling() -> None:
    """`30`, `"30"`, `"30s"` and `"30 seconds"` are all the same duration."""
    assert normalize_duration(30) == "30"
    assert normalize_duration("30") == "30"
    assert normalize_duration("30s") == "30"
    assert normalize_duration("30 sec") == "30"
    assert normalize_duration("20 seconds") == "20"


def test_unsupported_duration_raises() -> None:
    with pytest.raises(NormalizationError, match="duration"):
        normalize_duration("45")


# --- audience profiles -------------------------------------------------------


def test_broad_normalizes_to_wide() -> None:
    """Section 2.4 renamed Broad to Wide; section 3 step 4 warns the live
    suggest endpoint may still say broad."""
    assert normalize_profile("Broad") == "WIDE"
    assert normalize_profile("BROAD") == "WIDE"


def test_profile_case_is_absorbed() -> None:
    assert normalize_profile("Narrow") == "NARROW"
    assert normalize_profile("balanced") == "BALANCED"


# --- inventory tiers ---------------------------------------------------------


def test_short_tier_names_normalize_to_the_schema_spelling() -> None:
    """An earlier draft used 3P_*; section 5 names them THIRD_PARTY_*."""
    assert normalize_tier("3P_PRE_CURATED") == "THIRD_PARTY_PRECURATED"
    assert normalize_tier("3P_NEEDS_CURATION") == "THIRD_PARTY_NEEDS_CURATION"
    assert normalize_tier("amazon") == "AMAZON_OWNED"
    assert normalize_tier("AMAZON_OWNED") == "AMAZON_OWNED"


# --- goal and KPI casing -----------------------------------------------------


def test_goal_is_upper_and_kpi_is_lower() -> None:
    """The asymmetry is in the contract and in live state - it is not a bug.

    `extract_fields` writes {"goal": "AWARENESS", "kpi": "reach"}, so normalizing
    both to one case here would break the state contract.
    """
    assert normalize_goal("awareness") == "AWARENESS"
    assert normalize_kpi("REACH") == "reach"
    assert GoalEnum.AWARENESS.value == "AWARENESS"
    assert KPIEnum.REACH.value == "reach"


def test_split_method_accepts_the_display_label() -> None:
    """ "Even by budget" is UI copy; EVEN_BY_BUDGET is the stored value."""
    assert normalize_split_method("Even by budget") == "EVEN_BY_BUDGET"
    assert normalize_split_method("even by impressions") == "EVEN_BY_IMPRESSIONS"


def test_matching_mode_is_title_case() -> None:
    """Section 5 leaves this a bare str defaulting to "Exact" - no enum."""
    assert normalize_matching_mode("similar") == "Similar"
    assert normalize_matching_mode("EXACT") == "Exact"


def test_currency_is_restricted_to_the_three_vow_bills_in() -> None:
    assert normalize_currency("gbp") == "GBP"
    with pytest.raises(NormalizationError):
        normalize_currency("CAD")


# --- field mapping -----------------------------------------------------------


def test_canonical_and_hostile_deal_fields_land_on_the_same_model() -> None:
    """external_deal_id/deal_id and deal_price_amount/rate_card_cpm are aliases.

    The whole field-name conflict collapses into one AliasChoices tuple per
    field, which is what this proves.
    """
    canonical = DealItem.model_validate(CANONICAL_DEAL)
    hostile = DealItem.model_validate(HOSTILE_DEAL)

    assert canonical.deal_id == "EXTQ5"
    assert hostile.deal_id == "D-AMZ-PRIME-01"
    assert canonical.cpm == Decimal("18.22")
    assert hostile.cpm == Decimal("18.50")


def test_hostile_deal_normalizes_market_tier_and_durations() -> None:
    deal = DealItem.model_validate(HOSTILE_DEAL)

    assert deal.market == "GB"
    assert deal.inventory_tier is InventoryTierEnum.THIRD_PARTY_PRECURATED
    assert deal.ad_lengths == ("15", "30")


def test_hostile_audience_maps_broad_to_wide_and_coerces_the_fee() -> None:
    item = AudienceProfileItem.model_validate(HOSTILE_AUDIENCE)

    assert item.profile.value == "WIDE"
    assert item.vcpm_fee == Decimal("1.00")


def test_unmodelled_fields_are_ignored_not_fatal() -> None:
    """The server growing a field must not stop the flow - additive, not breaking."""
    item = AudienceProfileItem.model_validate(HOSTILE_AUDIENCE)
    assert not hasattr(item, "risk_notes")


def test_missing_required_field_is_rejected() -> None:
    """A deal with no price is not a deal we can plan against."""
    payload = {k: v for k, v in CANONICAL_DEAL.items() if k != "deal_price_amount"}
    with pytest.raises(ValidationError, match="cpm"):
        DealItem.model_validate(payload)


# --- money -------------------------------------------------------------------


def test_effective_cpm_arithmetic_is_exact() -> None:
    """18.22 + 3.50 is 21.72, not 21.719999999999999.

    Asserted with == rather than approx on purpose: a trader commits budget
    against this number, and float drift is the reason it is Decimal.
    """
    deal = DealItem.model_validate(CANONICAL_DEAL)
    audience = AudienceProfileItem.model_validate(CANONICAL_AUDIENCE)

    assert deal.cpm + audience.vcpm_fee == Decimal("21.72")
    assert money_str(deal.cpm + audience.vcpm_fee) == "21.72"


def test_money_rounds_half_up_at_two_places() -> None:
    assert to_money("18.225") == Decimal("18.23")
    assert money_str(Decimal("18.2")) == "18.20"


def test_money_from_a_float_does_not_carry_binary_drift() -> None:
    """Goes through str() first - Decimal(18.50) from a float would not."""
    assert to_money(18.50) == Decimal("18.50")


def test_non_numeric_money_raises() -> None:
    with pytest.raises(NormalizationError):
        to_money("free")


# --- the snapshot ------------------------------------------------------------


def test_supports_reach_forecast_is_derived_from_the_tier() -> None:
    """Never stored, so it cannot contradict the tier it depends on."""
    amazon = DealItem.model_validate(CANONICAL_DEAL)
    third_party = DealItem.model_validate({**CANONICAL_DEAL, "inventory_tier": "3P_PRE_CURATED"})

    assert amazon.supports_reach_forecast is True
    assert third_party.supports_reach_forecast is False


def test_snapshot_data_is_frozen() -> None:
    """A snapshot a consumer can edit is not grounded."""
    data = GroundedRegistryData(valid_markets=frozenset({"GB"}))
    with pytest.raises(ValidationError, match="frozen"):
        data.valid_markets = frozenset({"US"})


def test_content_hash_is_stable_across_set_insertion_order() -> None:
    """Sets serialize sorted, so two identical snapshots hash the same.

    Without that, Python's per-process hash randomisation would make every sync
    look like a change and versioning would be pure noise.
    """
    first = GroundedRegistryData(valid_markets=frozenset(["GB", "US", "DE"]))
    second = GroundedRegistryData(valid_markets=frozenset(["DE", "US", "GB"]))

    assert first.content_hash() == second.content_hash()


def test_content_hash_changes_when_content_does() -> None:
    base = GroundedRegistryData(valid_markets=frozenset(["GB"]))
    grown = GroundedRegistryData(valid_markets=frozenset(["GB", "US"]))

    assert base.content_hash() != grown.content_hash()


def test_accessors_normalize_the_market_they_are_given() -> None:
    """`deals("UK")` must find the deals stored under GB."""
    deal = DealItem.model_validate(CANONICAL_DEAL)
    data = GroundedRegistryData(valid_markets=frozenset(["GB"]), available_deals={"GB": (deal,)})

    assert data.deals("UK") == (deal,)
    assert data.deal_by_id("GB", "EXTQ5") is deal
    assert data.amazon_deals("GB") == (deal,)


# --- the validation response -------------------------------------------------


def test_a_warning_does_not_block() -> None:
    """ "I read UK as GB" is worth saying, not worth stopping for."""
    warning = ValidationResponse(is_valid=True, severity="warning", message="I read UK as GB.")
    error = ValidationResponse(is_valid=False, message="No such market.")

    assert warning.blocks is False
    assert error.blocks is True
