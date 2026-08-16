"""Tests for the validators the graph will call - steps 1 to 7.

Two things are being checked at once in most of these: that the answer is right,
and that the *message* is something the agent can say out loud. `gates.py` sets
that standard - "requirements are described in the trader's language, not the
schema's, because these strings end up in the question the agent asks" - so a
test asserting only `is_valid` would pass while the agent said "invalid enum
value" to a trader.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import GroundingError
from app.knowledge.registry.ingestion import RegistryIngestor
from app.knowledge.registry.models import ValidationResponse
from app.knowledge.registry.validate import (
    CURATION_FIELDS,
    StepwiseCTVValidator,
    assert_grounded,
    calculate_effective_cpm,
    cheapest_amazon_cpm,
    impressions_for,
)
from app.tools.mcp.mock import MockMCPClient

FUTURE = {"lower": "2099-08-01", "upper": "2099-08-31"}


# --- helpers -----------------------------------------------------------------


async def _validator(markets: list[str] | None = None) -> StepwiseCTVValidator:
    mcp = MockMCPClient(advertiser_id="adv-1")
    snapshot = await RegistryIngestor(mcp).sync(markets=markets or ["GB"])
    return StepwiseCTVValidator(snapshot, mcp)


# --- pricing -----------------------------------------------------------------


def test_effective_cpm_is_the_deal_price_plus_the_audience_fee() -> None:
    """Section 2.4: the fee stacks, so the deal price alone understates the cost."""
    assert calculate_effective_cpm(Decimal("18.22"), Decimal("3.50")) == Decimal("21.72")


def test_effective_cpm_rounds_half_up_rather_than_drifting() -> None:
    assert calculate_effective_cpm(Decimal("18.225"), Decimal("0.00")) == Decimal("18.23")


async def test_the_cpm_basis_is_the_cheapest_amazon_deal() -> None:
    """The trader will optimise toward the cheapest qualifying inventory, so that
    is the honest anchor - not an average across tiers."""
    validator = await _validator()
    deals = validator.data.deals("GB")

    assert cheapest_amazon_cpm(deals) == Decimal("18.22")


async def test_there_is_no_cpm_basis_without_amazon_inventory() -> None:
    """None rather than zero: Amazon audiences do not apply to third-party
    inventory at all, and a zero would read as free."""
    validator = await _validator(markets=["FR"])

    assert cheapest_amazon_cpm(validator.data.deals("FR")) is None


def test_derived_impressions_use_the_documented_formula() -> None:
    """budget / CPM x 1000 - section 3 step 6's honest answer for third-party."""
    assert impressions_for(Decimal("50000"), Decimal("31.50")) == 1_587_301


def test_a_zero_cpm_yields_no_impressions_rather_than_dividing_by_zero() -> None:
    assert impressions_for(Decimal("50000"), Decimal("0")) == 0


# --- step 1: basics ---------------------------------------------------------


async def test_an_ungrounded_market_is_refused_with_the_real_options() -> None:
    validator = await _validator()
    response = validator.validate_target_markets(["US", "China"])

    assert response.blocks
    assert response.code == "market.unknown"
    assert "China" in response.message
    assert response.suggested_options == ["DE", "FR", "GB", "US"]


async def test_uk_is_accepted_as_gb_with_a_note_rather_than_an_error() -> None:
    """The trader is not wrong; the registry just stores GB. Saying so is a
    courtesy, and blocking on it would be obstructive."""
    validator = await _validator()
    response = validator.validate_target_markets(["UK"])

    assert response.is_valid
    assert response.severity == "warning"
    assert response.blocks is False
    assert response.metadata["normalized"] == ["GB"]


async def test_no_market_asks_for_one_in_the_traders_language() -> None:
    validator = await _validator()
    response = validator.validate_target_markets([])

    assert response.blocks
    assert "which country" in response.message.lower()


async def test_the_goal_and_kpi_pair_the_graph_writes_today_is_valid() -> None:
    """`extract_fields` writes {"goal": "AWARENESS", "kpi": "reach"}.

    If this ever fails, wiring the registry into the nodes would start injecting a
    spurious validation error on every turn.
    """
    validator = await _validator()

    assert validator.validate_goal_and_kpi("AWARENESS", "reach").is_valid


async def test_a_down_funnel_kpi_is_refused_by_scope_not_by_enum() -> None:
    """ "invalid enum value" tells a trader nothing. Section 3 step 1 gives the
    actual reason: CTV cannot track down the funnel."""
    validator = await _validator()
    response = validator.validate_goal_and_kpi("AWARENESS", "ctr")

    assert response.blocks
    assert response.code == "kpi.out_of_scope"
    assert "down-funnel" in response.message
    assert sorted(response.suggested_options) == ["frequency", "reach"]


async def test_a_conversion_goal_is_refused_with_the_clients_reasoning() -> None:
    validator = await _validator()
    response = validator.validate_goal_and_kpi("CONVERSION", "reach")

    assert response.blocks
    assert "Awareness" in response.message


async def test_a_duplicate_strategy_name_offers_alternatives() -> None:
    """Section 1: name uniqueness is checked against VOW, not guessed at."""
    validator = await _validator()
    response = await validator.validate_strategy_name("CTV GB 2026-08")

    assert response.blocks
    assert response.code == "strategy_name.duplicate"
    assert response.suggested_options


async def test_a_free_strategy_name_passes() -> None:
    validator = await _validator()
    response = await validator.validate_strategy_name("Autumn CTV push GB")

    assert response.is_valid
    assert response.code == "strategy_name.ok"


async def test_an_over_long_name_is_rejected_without_a_round_trip() -> None:
    """Local rules first, so a 200-character name never costs an MCP call."""
    validator = await _validator()
    before = len(validator.mcp.calls)

    response = await validator.validate_strategy_name("x" * 500)

    assert response.blocks
    assert response.code == "strategy_name.too_long"
    assert len(validator.mcp.calls) == before


async def test_the_same_name_is_only_asked_about_once() -> None:
    """A trader may propose the same name twice in one conversation."""
    validator = await _validator()
    await validator.validate_strategy_name("Autumn CTV push GB")
    before = len(validator.mcp.calls)
    await validator.validate_strategy_name("Autumn CTV push GB")

    assert len(validator.mcp.calls) == before


async def test_a_past_flight_start_is_rejected() -> None:
    """`extract_fields._flight_dates` will read "August" as a month that has gone."""
    validator = await _validator()
    response = validator.validate_flight_dates(
        {"lower": "2020-08-01", "upper": "2020-08-31"}, today=date(2026, 8, 3)
    )

    assert response.blocks
    assert response.code == "flight_dates.in_past"


async def test_an_end_date_before_the_start_is_rejected() -> None:
    validator = await _validator()
    response = validator.validate_flight_dates(
        {"lower": "2026-08-31", "upper": "2026-08-01"}, today=date(2026, 8, 3)
    )

    assert response.blocks
    assert response.code == "flight_dates.inverted"


async def test_a_valid_flight_reports_its_length() -> None:
    validator = await _validator()
    response = validator.validate_flight_dates(FUTURE, today=date(2026, 8, 3))

    assert response.is_valid
    assert response.metadata["days"] == 30


async def test_durations_off_the_rate_card_warn_rather_than_block() -> None:
    """The platform sells 10s; the GB rate card does not price it. That is worth
    saying, and not worth refusing - section 3 step 2 treats the rate card as the
    authority on what a market carries."""
    validator = await _validator()
    response = validator.validate_durations(["10"], market="GB")

    assert response.is_valid
    assert response.severity == "warning"
    assert response.code == "duration.not_on_rate_card"
    assert response.suggested_options == ["15", "30"]


async def test_a_duration_the_platform_does_not_sell_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_durations(["45"])

    assert response.blocks
    assert response.code == "duration.unknown"


async def test_a_currency_mismatched_to_the_market_warns() -> None:
    """Legal, but almost always a slip - so said, not blocked."""
    validator = await _validator(markets=["US"])
    response = validator.validate_currency("GBP", markets=["US"])

    assert response.is_valid
    assert response.severity == "warning"
    assert response.metadata["market_default"] == "USD"


async def test_unknown_product_categories_are_refused_with_the_market_list() -> None:
    validator = await _validator()
    response = validator.validate_product_categories("GB", [101, 999])

    assert response.blocks
    assert response.code == "product_categories.unknown"
    assert "999" in response.message
    assert "Automotive" in response.suggested_options


async def test_product_categories_degrade_when_the_market_has_no_list() -> None:
    """An optional facet going missing must not stop a plan."""
    validator = await _validator()
    response = validator.validate_product_categories("US", [101])

    assert response.is_valid
    assert response.severity == "warning"
    assert response.code == "product_categories.unavailable"


# --- step 2: the tier fork ---------------------------------------------------


async def test_amazon_only_inventory_is_forecastable_and_needs_no_curation() -> None:
    validator = await _validator()
    response = validator.validate_deal_selection("GB", ["EXTQ5"])

    assert response.is_valid
    assert response.metadata["forecastable"] is True
    assert response.metadata["curation_required"] is False
    assert response.metadata["dominant_tier"] == "AMAZON_OWNED"


async def test_selecting_disney_asks_for_what_vow_needs_to_curate_it() -> None:
    """Section 3 step 2: needs-curation inventory is not selectable yet, so the
    agent captures genres, durations, targeting, budget and dates instead."""
    validator = await _validator()
    response = validator.validate_deal_selection("GB", ["EXTDSNY0007"])

    assert response.blocks
    assert response.code == "deal.curation_required"
    assert response.field == "curation_details"
    assert response.metadata["curation_fields"] == list(CURATION_FIELDS)
    assert "Disney+" in response.message


async def test_curation_details_satisfy_the_fork() -> None:
    validator = await _validator()
    response = validator.validate_deal_selection(
        "GB",
        ["EXTDSNY0007"],
        curation={
            "genres": ["Action"],
            "durations": ["30"],
            "budget": "50000.00",
            "flight_dates": FUTURE,
        },
    )

    assert response.is_valid


async def test_a_mixed_selection_reports_amazon_as_dominant_and_still_needs_curation() -> None:
    """Amazon wins the dominant tier because it is the only one that unlocks a
    forecast - but the Disney portion still has to be captured."""
    validator = await _validator()
    response = validator.validate_deal_selection("GB", ["EXTQ5", "EXTNFLX0012", "EXTDSNY0007"])

    assert response.blocks
    assert response.metadata["dominant_tier"] == "AMAZON_OWNED"
    assert response.metadata["forecastable"] is True
    assert set(response.metadata["inventory_summary"]) == {
        "AMAZON_OWNED",
        "THIRD_PARTY_PRECURATED",
        "THIRD_PARTY_NEEDS_CURATION",
    }


async def test_an_invented_deal_id_is_refused_and_the_real_ones_offered() -> None:
    """The zero-hallucination policy, at its most literal."""
    validator = await _validator()
    response = validator.validate_deal_selection("GB", ["D-AMZ-PRIME-01"])

    assert response.blocks
    assert response.code == "deal.unknown"
    assert "EXTQ5" in response.suggested_options
    assert "will not invent" in response.message


async def test_incomplete_curation_details_name_what_is_missing() -> None:
    validator = await _validator()
    response = validator.validate_curation_requirements({"genres": ["Action"]})

    assert response.blocks
    assert "durations" in response.message
    assert "budget" in response.message
    # Targeting preferences are optional per section 3 step 2.
    assert "targeting_preferences" not in response.message


async def test_the_genre_upsell_reports_facts_and_no_judgement() -> None:
    """Section 3 step 2's example: Prime ROS at 18.22 versus Action at 22.07.

    Whether the brief implies Action is the agent's call, not the registry's, so
    this returns the price difference and stops there.
    """
    validator = await _validator()
    candidates = validator.genre_upsell_candidates("GB", "Prime Video")

    assert len(candidates) == 1
    assert candidates[0]["genre"] == "Action"
    assert candidates[0]["base_cpm"] == "18.22"
    assert candidates[0]["cpm"] == "22.07"
    assert candidates[0]["uplift"] == "3.85"


# --- step 3: budget split ----------------------------------------------------


async def test_the_split_method_carries_its_consequence() -> None:
    """Section 3 step 3 requires the agent to state which it chose and why."""
    validator = await _validator()
    response = validator.validate_split_method("Even by impressions")

    assert response.is_valid
    assert response.metadata["normalized"] == "EVEN_BY_IMPRESSIONS"
    assert "uneven spend" in response.message


async def test_an_unknown_split_method_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_split_method("by vibes")

    assert response.blocks
    assert response.code == "split_method.unknown"


# --- step 4: audiences -------------------------------------------------------


async def test_all_three_profiles_are_priced_against_the_amazon_basis() -> None:
    """Section 3 step 4 wants the effective CPM per option, not just the fee."""
    validator = await _validator()
    options = validator.effective_cpm_options("GB", ["EXTQ5"])

    assert [o["profile"] for o in options] == ["NARROW", "BALANCED", "WIDE"]
    assert [o["effective_cpm"] for o in options] == ["21.72", "20.22", "19.07"]
    assert all(o["cpm_basis"] == "18.22" for o in options)


async def test_a_plan_with_no_amazon_inventory_has_no_effective_cpm() -> None:
    """Not zero. Amazon audiences do not apply to third-party inventory at all."""
    validator = await _validator(markets=["FR"])
    options = validator.effective_cpm_options("FR")

    assert options
    assert all(o["effective_cpm"] is None for o in options)
    assert all(o["cpm_basis"] is None for o in options)


async def test_an_unknown_audience_profile_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_audience_choice("Enormous")

    assert response.blocks
    assert response.code == "audience.unknown_profile"


async def test_broad_is_accepted_as_wide() -> None:
    validator = await _validator()
    response = validator.validate_audience_choice("Broad")

    assert response.is_valid
    assert response.metadata["normalized"] == "WIDE"


async def test_matching_mode_accepts_either_case() -> None:
    validator = await _validator()

    assert validator.validate_matching_mode("similar").metadata["normalized"] == "Similar"
    assert validator.validate_matching_mode("EXACT").metadata["normalized"] == "Exact"


# --- step 5: targeting -------------------------------------------------------


async def test_targeting_options_come_from_the_snapshot() -> None:
    validator = await _validator()
    response = validator.get_targeting_options_for_market("GB")

    assert response.is_valid
    assert "location" in response.metadata["config"]["options"]


async def test_a_market_with_no_targeting_config_says_so_rather_than_raising() -> None:
    """Targeting is optional in section 3 step 5, so its absence must not stop a plan."""
    validator = await _validator()
    response = validator.get_targeting_options_for_market("US")

    assert response.is_valid
    assert response.severity == "warning"
    assert response.code == "targeting.unavailable"


async def test_an_unknown_targeting_type_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_targeting("GB", {"day_parting": ["EVENING"]})

    assert response.blocks
    assert response.code == "targeting.unknown_type"
    assert "location" in response.suggested_options


async def test_an_unknown_targeting_value_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_targeting("GB", {"device_type": ["TOASTER"]})

    assert response.blocks
    assert "TOASTER" in response.message


async def test_a_single_valued_targeting_type_refuses_two_values() -> None:
    validator = await _validator()
    response = validator.validate_targeting("GB", {"instream_position": ["PRE_ROLL", "MID_ROLL"]})

    assert response.blocks
    assert "one value" in response.message


async def test_a_valid_targeting_selection_passes() -> None:
    validator = await _validator()
    response = validator.validate_targeting(
        "GB", {"device_type": ["CONNECTED_TV"], "instream_position": ["PRE_ROLL"]}
    )

    assert response.is_valid


# --- step 6: the honesty rule -----------------------------------------------


async def test_forecastability_follows_the_inventory_tier() -> None:
    gb = await _validator()
    fr = await _validator(markets=["FR"])

    assert gb.is_forecastable("GB", ["EXTQ5"]) is True
    assert gb.is_forecastable("GB", ["EXTNFLX0012"]) is False
    assert fr.is_forecastable("FR") is False


async def test_a_forecast_claiming_unavailable_may_not_supply_reach() -> None:
    """Section 3 step 6: "Never invent a reach number."

    A payload that says reach is unavailable and then carries one is the exact
    fabricated-reach failure mode, so it is rejected structurally.
    """
    validator = await _validator()
    response = validator.validate_forecast_shape(
        {
            "is_available": False,
            "estimated_impressions": 1_587_301,
            "estimated_unique_reach": 496_031,
        }
    )

    assert response.blocks
    assert response.code == "forecast.fabricated_reach"
    assert "estimated_unique_reach" in response.metadata["fabricated_fields"]


async def test_an_honest_unavailable_forecast_passes() -> None:
    validator = await _validator()
    response = validator.validate_forecast_shape(
        {
            "is_available": False,
            "reason": "Reach forecasting is available for Amazon inventory only.",
            "estimated_impressions": 1_587_301,
        }
    )

    assert response.is_valid
    assert response.metadata["reach_available"] is False


async def test_a_forecast_claiming_available_must_carry_the_numbers() -> None:
    validator = await _validator()
    response = validator.validate_forecast_shape(
        {"is_available": True, "estimated_impressions": 100}
    )

    assert response.blocks
    assert response.code == "forecast.incomplete"


async def test_a_forecast_with_no_availability_flag_is_refused() -> None:
    validator = await _validator()
    response = validator.validate_forecast_shape({"estimated_impressions": 100})

    assert response.blocks
    assert response.code == "forecast.no_availability_flag"


async def test_the_mocks_real_forecast_payloads_both_validate() -> None:
    """Guards the mock and the validator against drifting apart."""
    from app.tools.mcp import VowTools

    validator = await _validator()
    amazon = await validator.mcp.call_tool(
        VowTools.REACH_FORECAST,
        {"inventory_tier": "AMAZON_OWNED", "budget": "50000", "effective_cpm": "21.72"},
    )
    third_party = await validator.mcp.call_tool(
        VowTools.REACH_FORECAST,
        {"inventory_tier": "THIRD_PARTY_PRECURATED", "budget": "50000", "effective_cpm": "31.50"},
    )

    assert validator.validate_forecast_shape(amazon).is_valid
    assert validator.validate_forecast_shape(third_party).is_valid


# --- step 7: approval readiness ---------------------------------------------


async def test_an_incomplete_plan_lists_every_gap_at_once() -> None:
    """Every reason in one answer, unlike the conversation.

    `ask_for_missing` asks one thing per turn, but approval is not a conversation -
    it is where budget locks, so it reports the whole list rather than the first
    problem.
    """
    validator = await _validator()
    response = validator.validate_plan_ready_for_approval({"markets": ["GB"]})

    assert response.blocks
    violations = response.metadata["violations"]
    assert len(violations) > 3
    assert any("strategy name" in v for v in violations)
    assert any("forecast" in v for v in violations)


async def test_a_complete_plan_is_ready() -> None:
    validator = await _validator()
    response = validator.validate_plan_ready_for_approval(
        {
            "strategy_name": "Autumn CTV push GB",
            "flight_dates": FUTURE,
            "markets": ["GB"],
            "durations": ["15", "30"],
            "market_budgets": [{"market": "GB", "budget": "50000.00"}],
            "selected_deals": [{"deal_id": "EXTQ5"}],
            "chosen_audience": {"profile": "BALANCED"},
            "forecast": {
                "is_available": True,
                "estimated_impressions": 2_302_000,
                "estimated_unique_reach": 719_375,
                "average_frequency": 3.2,
            },
            "goal": "AWARENESS",
            "kpi": "reach",
        }
    )

    assert response.is_valid
    assert response.code == "plan.ready"


async def test_a_fabricated_forecast_blocks_approval() -> None:
    validator = await _validator()
    response = validator.validate_plan_ready_for_approval(
        {
            "strategy_name": "Autumn CTV push GB",
            "flight_dates": FUTURE,
            "markets": ["GB"],
            "durations": ["30"],
            "market_budgets": [{"market": "GB", "budget": "50000.00"}],
            "selected_deals": [{"deal_id": "EXTNFLX0012"}],
            "chosen_audience": {"profile": "BALANCED"},
            "forecast": {"is_available": False, "estimated_unique_reach": 496_031},
            "goal": "AWARENESS",
            "kpi": "reach",
        }
    )

    assert response.blocks
    assert any("will not report that as reach" in v for v in response.metadata["violations"])


READY_PLAN = {
    "strategy_name": "Autumn CTV push GB",
    "flight_dates": FUTURE,
    "markets": ["GB"],
    "durations": ["15", "30"],
    "market_budgets": [{"market": "GB", "budget": "50000.00"}],
    "selected_deals": [{"deal_id": "EXTQ5"}],
    "chosen_audience": {"profile": "BALANCED"},
    "forecast": {
        "is_available": True,
        "estimated_impressions": 2_302_000,
        "estimated_unique_reach": 719_375,
        "average_frequency": 3.2,
    },
    "goal": "AWARENESS",
    "kpi": "reach",
}


async def test_a_recorded_blocker_still_blocks_approval() -> None:
    """`validation_errors` holds serialized `ValidationResponse`s now, not prose
    (see `agent/gates.record`), so this reads `message` off the dict."""
    validator = await _validator()
    response = validator.validate_plan_ready_for_approval(
        {
            **READY_PLAN,
            "validation_errors": [
                {
                    "is_valid": False,
                    "severity": "error",
                    "code": "market.unknown",
                    "message": "I cannot plan for ES - VOW does not sell CTV inventory there.",
                    "stage": "validation",
                }
            ],
        }
    )

    assert response.blocks
    assert any("cannot plan for ES" in v for v in response.metadata["violations"])


async def test_a_recorded_warning_does_not_block_approval() -> None:
    """The agent already said it and the trader carried on, so folding it in here
    would let an acknowledged note refuse a finished plan."""
    validator = await _validator()
    response = validator.validate_plan_ready_for_approval(
        {
            **READY_PLAN,
            "validation_errors": [
                {
                    "is_valid": True,
                    "severity": "warning",
                    "code": "duration.not_on_rate_card",
                    "message": "10-second is not on the GB rate card.",
                    "stage": "validation",
                }
            ],
        }
    )

    assert response.is_valid
    assert response.code == "plan.ready"


# --- the hard backstop -------------------------------------------------------


def test_assert_grounded_raises_only_on_a_blocking_response() -> None:
    """The one place in the codebase that raises GroundingError.

    Warnings pass through: "I read UK as GB" must not stop a plan.
    """
    assert_grounded(ValidationResponse(is_valid=True, message="fine"))
    assert_grounded(
        ValidationResponse(is_valid=True, severity="warning", message="I read UK as GB.")
    )

    with pytest.raises(GroundingError, match="not grounded"):
        assert_grounded(
            ValidationResponse(is_valid=False, field="selected_deals", message="No such deal.")
        )
