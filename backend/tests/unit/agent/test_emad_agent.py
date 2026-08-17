"""Comprehensive Unit Tests for Emad Agent (Basic Details Agent).

Tests the extraction, snapshot grounding, validation rules, conversational asking,
and state store updates for all basic campaign parameters (market, flight dates,
durations, budget, currency, goal, and product/brand category) per docs/Workflow.jpeg and M1_Planning.txt.
"""

from __future__ import annotations

import pytest

from app.agent.nodes.ask_for_missing import ask_for_missing
from app.agent.nodes.extract_fields import extract_fields
from app.agent.nodes.validate_basics import make_validate_basics
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp.mock import MockMCPClient


@pytest.fixture
def registry() -> AdvertiserRegistry:
    return AdvertiserRegistry(advertiser_id="adv-emad-test", mcp=MockMCPClient("adv-emad-test"))


@pytest.fixture(autouse=True)
def _patch_llm(monkeypatch):
    """Disable LLM in unit tests to test deterministic extraction and grounding rules."""
    monkeypatch.setattr("app.agent.llm.get_llm", lambda: None)
    monkeypatch.setattr("app.agent.llm.get_voice_llm", lambda: None)


# --- 1. Basic Details Extraction Tests ---


@pytest.mark.asyncio
async def test_emad_extracts_complete_brief():
    """Emad agent extracts market, flight dates, durations, and budget from a full brief."""
    state: PlanningAgentState = {
        "messages": [
            {
                "role": "user",
                "content": "CTV campaign in the UK for £50,000 in October 2030, 15 and 30 second creatives.",
            }
        ]
    }

    result = await extract_fields(state)

    assert result["markets"] == ["GB"]
    assert result["durations"] == ["15", "30"]
    assert result["primary_currency"] == "GBP"
    assert result["budget_amount"] == "50000.00"
    assert result["flight_dates"] == {"lower": "2030-10-01", "upper": "2030-10-31", "bounds": "[)"}
    assert result["market_budgets"][0]["budget"] == "50000.00"


@pytest.mark.asyncio
async def test_emad_extracts_partial_brief_and_tracks_gaps():
    """Emad agent extracts provided market and flags remaining missing fields in awaiting."""
    state: PlanningAgentState = {
        "messages": [{"role": "user", "content": "I want to run a campaign in the US."}]
    }

    result = await extract_fields(state)

    assert result["markets"] == ["US"]
    assert result["primary_currency"] == "USD"
    assert "the start and end dates" in result["awaiting"]
    assert "the budget" in result["awaiting"]


# --- 2. Snapshot Grounding & Market Validation ---


@pytest.mark.asyncio
async def test_emad_validates_supported_market_cleanly(registry):
    """Supported market (GB) grounds cleanly without blocking errors."""
    validator_node = make_validate_basics(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "primary_currency": "GBP",
        "market_budgets": [{"market": "GB", "budget": "50000.00"}],
    }

    result = await validator_node(state)
    errors = result.get("validation_errors") or []
    blockers = [e for e in errors if not e.get("is_valid") and e.get("severity") == "error"]

    assert len(blockers) == 0


@pytest.mark.asyncio
async def test_emad_refuses_unsold_market_with_alternatives(registry):
    """Unsold market (CN) is refused with available alternatives (GB, US, DE, FR)."""
    validator_node = make_validate_basics(registry)
    state: PlanningAgentState = {
        "markets": ["CN"],
    }

    result = await validator_node(state)
    errors = result.get("validation_errors") or []
    blockers = [e for e in errors if not e.get("is_valid") and e.get("severity") == "error"]

    assert len(blockers) == 1
    assert blockers[0]["code"] == "market.unknown"
    assert "CN" in blockers[0]["message"]
    # Check that alternatives are suggested
    assert "GB" in blockers[0].get("suggested_options", []) or "US" in blockers[0].get("suggested_options", [])


# --- 3. Flight Dates Validation ---


@pytest.mark.asyncio
async def test_emad_refuses_past_flight_dates(registry):
    """A flight date in the past (e.g. 2020) is refused with flight_dates.in_past error."""
    validator_node = make_validate_basics(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2020-01-01", "upper": "2020-01-31"},
    }

    result = await validator_node(state)
    errors = result.get("validation_errors") or []
    blockers = [e for e in errors if not e.get("is_valid") and e.get("severity") == "error"]

    assert len(blockers) >= 1
    assert any(b["code"] == "flight_dates.in_past" for b in blockers)


@pytest.mark.asyncio
async def test_emad_refuses_inverted_flight_dates(registry):
    """A flight date with end before start is rejected."""
    validator_node = make_validate_basics(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-31", "upper": "2030-10-01"},
    }

    result = await validator_node(state)
    errors = result.get("validation_errors") or []
    blockers = [e for e in errors if not e.get("is_valid") and e.get("severity") == "error"]

    assert len(blockers) >= 1
    assert any("not after" in b["message"] or b["code"] == "flight_dates.inverted" for b in blockers)


# --- 4. Duration Validation ---


@pytest.mark.asyncio
async def test_emad_validates_carried_durations(registry):
    """Valid durations (15s, 30s) pass validation."""
    validator_node = make_validate_basics(registry)
    state: PlanningAgentState = {
        "markets": ["GB"],
        "durations": ["15", "30"],
    }

    result = await validator_node(state)
    errors = result.get("validation_errors") or []
    blockers = [e for e in errors if not e.get("is_valid") and e.get("severity") == "error"]

    assert len(blockers) == 0


# --- 5. Conversational Probing (ask_for_missing) ---


@pytest.mark.asyncio
async def test_emad_asks_targeted_question_for_single_gap():
    """When only budget is missing, ask_for_missing asks specifically for the budget."""
    state: PlanningAgentState = {
        "markets": ["GB"],
        "flight_dates": {"lower": "2030-10-01", "upper": "2030-10-31"},
        "durations": ["30"],
        "awaiting": ["the budget"],
        "validation_errors": [],
    }

    result = await ask_for_missing(state)
    reply = result["messages"][0]["content"]

    assert "budget" in reply.lower()
    assert reply.rstrip().endswith("?")


@pytest.mark.asyncio
async def test_emad_asks_about_validation_conflict_before_gaps():
    """Validation conflict (e.g. unsold market) is asked about before missing gaps."""
    state: PlanningAgentState = {
        "markets": ["CN"],
        "awaiting": ["the start and end dates", "the budget"],
        "validation_errors": [
            {
                "is_valid": False,
                "severity": "error",
                "code": "market.unknown",
                "message": "I cannot plan for CN - VOW does not sell CTV inventory there.",
                "suggested_options": ["GB", "US", "DE", "FR"],
                "stage": "validation",
            }
        ],
    }

    result = await ask_for_missing(state)
    reply = result["messages"][0]["content"]

    assert "CN" in reply
    assert "GB" in reply or "US" in reply
