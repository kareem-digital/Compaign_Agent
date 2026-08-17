"""The chat endpoint's response contract, through real HTTP.

The first test in this repo to exercise `POST /sessions/chat` rather than the graph
state behind it. `tests/component/agent/test_planning_graph.py` reimplements the
route's reply assembly in a helper, so nothing until now asserted that what the
route *returns* matches what the graph *computed* - and the whole point of the
`validation` block is that a frontend can rely on it without reading the prose.

Deliberately not asserting prose: that is pinned verbatim in the component tests,
and duplicating it here would mean two files to update for one wording change. What
is asserted here is the envelope.

Two things this layer has to work around, both module-global:

  * `sessions._graphs` and `sessions._checkpointer` outlive the `client` fixture's
    fresh app, so every test needs its own `session_id` or it resumes another test's
    conversation.
  * `get_store()` caches snapshots per advertiser for the whole process.
"""

import asyncio
from datetime import date
from importlib import import_module

import pytest

from tests.conftest import TEST_ACCESS_TOKEN, TEST_SUBJECT

PREFIX = "/api/v1/sessions"
# The session endpoints require a bearer token; `client` is built against
# `StubAccessTokenVerifier`, which accepts exactly this one.
HEADERS = {
    "Authorization": f"Bearer {TEST_ACCESS_TOKEN}",
    "Vowmade-Advertiser-Id": "api-test-co",
}

GB_BRIEF = "CTV campaign in the UK for August 2026, £50,000, 15 and 30 second creatives"
PAST_BRIEF = "CTV campaign in the UK for August 2020, £50,000, 30 second creatives"


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    """The same two fixtures the component tests use, for the same reasons.

    Without the LLM patch a working local `.env` puts a network call inside a
    unit-speed suite and makes the extracted fields non-deterministic; without the
    frozen date, `August 2026` silently becomes the past and blocks the happy path.

    `app.agent.voice` is patched alongside the two nodes because this file is the
    one place a turn goes through the route, which is where the voice layer runs -
    the component tests never reach it.
    """
    for module in ("app.agent.nodes.extract_fields", "app.agent.nodes.ask_for_missing"):
        monkeypatch.setattr(import_module(module), "get_llm", lambda: None)

    monkeypatch.setattr(import_module("app.agent.voice"), "get_voice_llm", lambda: None)

    class _Frozen(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 7, 1)

    monkeypatch.setattr("app.knowledge.registry.validate.date", _Frozen)


def _thread(session: str) -> str:
    """The checkpointer key for a session, as `sessions.chat` composes it.

    Threads are namespaced by subject and advertiser so two tenants cannot read
    each other's conversation. A test reaching into the checkpointer has to use
    the same key the endpoint wrote under, or it silently reads an empty state.
    """
    from app.config import get_settings

    settings = get_settings()
    subject = settings.local_auth_subject if settings.environment == "local" else TEST_SUBJECT
    return f"{subject}:{HEADERS['Vowmade-Advertiser-Id']}:{session}"


def _chat(client, message: str, session: str) -> dict:
    response = client.post(
        f"{PREFIX}/chat",
        json={"message": message, "session_id": session},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_reply_still_carries_the_whole_conversation(client) -> None:
    """`validation` is additive. Nothing that worked before it moved."""
    body = _chat(client, GB_BRIEF, "api-reply")

    assert body["session_id"] == "api-reply"
    assert body["stage"] == "audiences"
    assert "Here is what I understood" in body["reply"]


def test_a_clean_turn_reports_the_rules_it_ran(client) -> None:
    """The turn a UI has the least to show without this: nothing failed, so
    `validation_errors` is empty, and the passes are the only evidence anything was
    checked at all."""
    validation = _chat(client, GB_BRIEF, "api-clean")["validation"]

    assert validation["grounded"] is True
    assert validation["is_valid"] is True
    assert validation["blocks"] is False
    assert validation["severity"] is None
    assert "market.ok" in [check["code"] for check in validation["checks"]]
    assert validation["registry"]["source"] == "mock"


def test_every_check_carries_what_the_ui_renders(client) -> None:
    """The wire shape, once, so a frontend type can be written against it."""
    checks = _chat(client, GB_BRIEF, "api-shape")["validation"]["checks"]

    assert checks
    for check in checks:
        assert set(check) == {
            "is_valid",
            "message",
            "code",
            "severity",
            "field",
            "suggested_options",
            "metadata",
            "stage",
            "blocks",
            "checked_this_turn",
        }


@pytest.mark.parametrize("brief,session", [(GB_BRIEF, "api-sev-ok"), (PAST_BRIEF, "api-sev-bad")])
def test_no_check_ever_says_valid_and_error_at_once(client, brief: str, session: str) -> None:
    """`_ok()` leaves `severity` at the model's default of "error", so in state a
    pass is `is_valid` *and* error. On the wire that reads as a contradiction, and
    any `severity === "error" -> red` frontend would paint every green check red.

    Asserted as the invariant rather than as "passes are null", because a warning is
    also `is_valid` - it is the *combination* that must never appear.
    """
    checks = _chat(client, brief, session)["validation"]["checks"]

    assert checks
    assert not [c for c in checks if c["is_valid"] and c["severity"] == "error"]
    assert {c["severity"] for c in checks} <= {None, "warning", "error"}


def test_a_rejected_value_is_grounded_and_invalid(client) -> None:
    """The registry was consulted and said no. Not a grounding failure - which is
    why these are two fields and not one."""
    validation = _chat(client, PAST_BRIEF, "api-blocked")["validation"]

    assert validation["grounded"] is True
    assert validation["is_valid"] is False
    assert validation["blocks"] is True
    assert validation["severity"] == "error"

    (blocker,) = [check for check in validation["checks"] if check["blocks"]]
    assert blocker["code"] == "flight_dates.in_past"
    assert blocker["stage"] == "validation"


def test_nothing_is_grounded_before_a_market_is_named(client) -> None:
    validation = _chat(client, "I want to run a CTV campaign", "api-nomarket")["validation"]

    assert validation["grounded"] is False
    assert validation["registry"] is None
    assert validation["checks"] == []
    assert validation["awaiting"]


def test_the_voice_changes_the_reply_and_not_the_record(client, monkeypatch) -> None:
    """The seam the whole voice layer rests on.

    `gates.say` suppresses a repeat by fingerprinting the message a stage is about
    to emit, so model prose in `state["messages"]` would mean no digest ever
    matches and nothing is ever suppressed - the loop commit 09a613e removed.

    So the rewrite is allowed to reach `reply` and must never reach state. Asserted
    together in one test because separately they are both satisfied by doing
    nothing at all.
    """
    # Keeps every provider the turn matched: the guard rejects a rewrite that
    # summarises them away, and a stub that fell foul of it would pass this test
    # for the wrong reason - by never reaching `reply` at all.
    rewrite = (
        "Locked in - GB, August, 15s and 30s. Prime Video, Netflix and Disney+ all "
        "match. Which audience shall I forecast against?"
    )

    class _Stub:
        async def ainvoke(self, messages):
            return type("Response", (), {"content": rewrite})()

    monkeypatch.setattr(import_module("app.agent.voice"), "get_voice_llm", _Stub)

    body = _chat(client, GB_BRIEF, "api-voice")

    assert body["reply"] == rewrite

    graph = import_module("app.api.sessions")._graphs["api-test-co"]
    state = asyncio.run(graph.aget_state({"configurable": {"thread_id": _thread("api-voice")}}))
    recorded = "\n\n".join(
        m.content for m in state.values["messages"] if getattr(m, "type", None) == "ai"
    )

    assert "Here is what I understood" in recorded
    assert "CTV inventory available in GB:" in recorded
    assert rewrite not in recorded


def test_reopening_a_session_restores_the_panel(client) -> None:
    """`GET /sessions/{id}` returns the same block, so a reload does not blank it."""
    _chat(client, GB_BRIEF, "api-reopen")

    response = client.get(f"{PREFIX}/api-reopen", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "audiences"
    assert body["validation"]["grounded"] is True
    assert body["validation"]["registry"]["source"] == "mock"


def test_both_structured_channels_arrive_together(client) -> None:
    """`validation` and `blocks` are additive and independent.

    They came from the two lanes this branch merges and describe different halves
    of the same turn - what the backend *checked*, and what the turn *shows*. A
    client may consume either, so neither may depend on the other being read, and
    a turn that populates one must populate the other.

    The specific regression this guards: `build_blocks` keyed off `current_stage`
    and had no entry for `delivered`, so a completed plan returned a full
    `validation` block beside an empty `blocks` array.
    """
    body = _chat(client, GB_BRIEF, "api-both-channels")

    assert body["validation"]["grounded"] is True
    assert body["blocks"], "a turn that reached inventory rendered nothing"
    # Still the plain-text equivalent, unchanged by either.
    assert body["reply"]


def test_a_completed_plan_renders_the_whole_plan(client) -> None:
    """The delivered turn is the one a trader acts on, so it must carry blocks."""
    _chat(client, GB_BRIEF, "api-delivered-blocks")
    body = _chat(client, "Balanced", "api-delivered-blocks")

    assert body["stage"] == "delivered"
    assert [block["layout"] for block in body["blocks"]] == ["table", "cards", "metrics"]


def test_an_incomplete_brief_asks_through_both_channels(client) -> None:
    """Probing shows what was understood beside what is still needed."""
    body = _chat(client, "I want to run a CTV campaign in the UK", "api-probing-blocks")

    layouts = [block["layout"] for block in body["blocks"]]
    assert layouts[0] == "summary_list"
    fields = [block["field"] for block in body["blocks"] if block["field"]]
    assert fields == ["flight_dates", "durations", "market_budgets"]
