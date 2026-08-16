"""What the planning graph does today, pinned before it is rewired.

These exist because KNW-03 moves the markets, durations, tier map and effective-CPM
arithmetic out of the nodes and into the grounded registry. That changes where every
number in a reply comes from, so the safety net has to be the reply itself: if the
trader sees a different message after the refactor, one of these fails.

Hence the verbatim snapshots below. They are ugly and that is the point - an
assertion on `is_valid` would pass while the agent said something new to a trader.

Component rather than unit, per tests/component/__init__.py: this is one graph's
orchestration and branching, with its collaborators - the MCP server and the LLM -
mocked.

Mocking the LLM is not optional here. `get_llm` returns a real client whenever
OPENAI_API_KEY is set, which it is in a working local .env, and then
`ask_for_missing` rewords the question and `extract_fields` re-reads the brief on
every run. That makes the snapshots below non-deterministic and puts a network
call in the middle of a unit-speed suite. CI has no key and would silently take
the other path, so the two environments would be testing different code. The
fixture forces the deterministic path in both.
"""

from datetime import date
from importlib import import_module

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agent.gates import NO_AUDIENCE_CHOICE
from app.agent.graph import build_graph
from app.api.validation_details import build_validation_details
from app.knowledge.registry.ingestion import get_store
from app.knowledge.registry.models import DurationEnum
from app.tools.mcp.mock import MockMCPClient

# Every brief below is dated against this, not against the wall clock. `August
# 2026` was in the future when these were written and silently became the past on
# 1 August 2026, at which point `validate_basics` started blocking the happy path
# and most of this file failed - a fixture expiring rather than a regression.
# `check_flight_dates` takes an injectable `today` for exactly this reason, but the
# graph does not thread one through, so it is frozen at the source instead.
TODAY = date(2026, 7, 1)

GB_BRIEF = "CTV campaign in the UK for August 2026, £50,000, 15 and 30 second creatives"
# Symbol rather than "50,000 EUR": `extract_fields._BUDGET_PATTERNS` only reads a
# bare number as money when it carries a symbol, a k/m suffix, or the word
# "budget" within twelve characters. An LLM handles "50,000 EUR" fine, but these
# tests run the deterministic path, and a brief the pattern matcher cannot parse
# would stop at the basics gate and never reach the third-party forecast this is
# here to pin.
FR_BRIEF = "CTV campaign in France for August 2026, €50,000, 30 second creatives"


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Force the pattern-matching path in every node that can use a model.

    Patched at each import site rather than at the source, because both nodes did
    `from app.agent.llm import get_llm` and hold their own reference.

    `import_module` rather than a dotted string: `nodes/__init__.py` re-exports
    each node function under its module's name, so `app.agent.nodes.extract_fields`
    resolves to the *function* and setattr would silently miss.
    """
    for name in ("extract_fields", "ask_for_missing"):
        monkeypatch.setattr(import_module(f"app.agent.nodes.{name}"), "get_llm", lambda: None)


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    """Pin `date.today()` so a flight date is future-dated regardless of when this runs.

    Subclassed rather than mocked so `date.fromisoformat` - which
    `check_flight_dates` also calls - keeps working.
    """

    class _Frozen(date):
        @classmethod
        def today(cls) -> date:
            return TODAY

    monkeypatch.setattr("app.knowledge.registry.validate.date", _Frozen)


# --- helpers -----------------------------------------------------------------


async def _run(*messages: str, session: str = "s1") -> dict:
    """One or more turns through a freshly compiled graph, sharing a thread.

    Takes several messages because a complete brief no longer runs to a forecast on
    its own - the audience choice is a real wait-for-the-trader step, so most of
    what used to be a one-turn assertion is now `_run(brief, "Balanced")`.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)
    config = {"configurable": {"thread_id": session}}

    state: dict = {}
    for message in messages:
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )
    return state


def _codes(state: dict, severity: str | None = None) -> list[str]:
    """Recorded validation codes. `validation_errors` holds dicts, not prose."""
    return [
        entry["code"]
        for entry in state.get("validation_errors") or []
        if severity is None or entry["severity"] == severity
    ]


def _assistant_messages(state: dict) -> list[str]:
    """The replies, the way `sessions.chat` reads them off the state."""
    return [
        str(getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else ""))
        for m in state.get("messages", [])
        if getattr(m, "type", None) == "ai"
        or (isinstance(m, dict) and m.get("role") == "assistant")
    ]


# --- the complete-brief path -------------------------------------------------

# The audience choice, which a complete brief now stops for. Appended to a brief
# wherever a test needs the flow to run all the way to a plan.
PICK = "Balanced"


async def test_a_complete_brief_stops_only_for_the_audience_choice() -> None:
    """All four basics present, so nothing is missing - but nobody has picked yet.

    This used to assert a forecast on turn one, which was the bug: the agent chose
    BALANCED itself and forecast against an audience the trader never agreed to.
    """
    state = await _run(GB_BRIEF)

    assert state["current_stage"] == "audiences"
    assert state["awaiting"] == [NO_AUDIENCE_CHOICE]
    assert state["chosen_audience"] is None
    assert state.get("forecast") is None


async def test_naming_an_audience_delivers_the_plan() -> None:
    state = await _run(GB_BRIEF, PICK)

    assert state["current_stage"] == "delivered"
    assert state["awaiting"] == []
    assert state["chosen_audience"]["profile"] == "BALANCED"
    assert state["forecast"]["is_available"] is True


async def test_every_node_speaks_once_per_turn() -> None:
    """`sessions.chat` joins these with a blank line into one HTTP reply.

    Turn one is four sections - confirmation, inventory, options - and the delivery
    turn is one. Change the node count and the transport shape changes with it.
    """
    assert len(_assistant_messages(await _run(GB_BRIEF))) == 3
    assert len(_assistant_messages(await _run(GB_BRIEF, PICK, session="speaks"))) == 4


async def test_the_brief_is_normalized_to_iso_and_the_markets_currency() -> None:
    """UK becomes GB, and GB implies GBP - schema v2 section 7.1."""
    state = await _run(GB_BRIEF)

    assert state["markets"] == ["GB"]
    assert state["primary_currency"] == "GBP"
    assert state["durations"] == ["15", "30"]
    assert state["flight_dates"] == {"lower": "2026-08-01", "upper": "2026-08-31", "bounds": "[)"}
    assert state["market_budgets"] == [{"market": "GB", "budget": "50000.00", "base_bid": None}]


async def test_the_goal_and_kpi_pair_written_into_state() -> None:
    """Upper-case goal, lower-case KPI. The registry's enums mirror this exactly."""
    state = await _run(GB_BRIEF)

    assert state["goal"] == "AWARENESS"
    assert state["kpi"] == "reach"


async def test_deals_are_classified_into_all_three_tiers() -> None:
    state = await _run(GB_BRIEF)

    assert state["inventory_tier"] == "AMAZON_OWNED"
    assert {d["inventory_tier"] for d in state["selected_deals"]} == {
        "AMAZON_OWNED",
        "THIRD_PARTY_PRECURATED",
        "THIRD_PARTY_NEEDS_CURATION",
    }
    assert [d["deal_id"] for d in state["selected_deals"]] == [
        "EXTQ5",
        "EXT7P75718S8MNR",
        "EXTNFLX0012",
        "EXTDSNY0007",
    ]


async def test_effective_cpms_stack_the_audience_fee_on_the_cheapest_amazon_deal() -> None:
    """18.22 + 3.50 / 2.00 / 0.85. The number a trader commits budget against.

    KNW-03 moves this arithmetic to `registry.calculate_effective_cpm` and swaps
    float for Decimal; these values must survive that unchanged.
    """
    state = await _run(GB_BRIEF)

    assert [(o["profile"], o["effective_cpm"]) for o in state["audience_options"]] == [
        ("NARROW", "21.72"),
        ("BALANCED", "20.22"),
        ("WIDE", "19.07"),
    ]
    assert all(o["cpm_basis"] == "18.22" for o in state["audience_options"])
    # Priced, but not chosen - the options are offered, not decided.
    assert state["chosen_audience"] is None


async def test_money_reaches_state_as_strings_not_decimals() -> None:
    """The checkpointer serializes state, and Decimal is not JSON-native.

    It would also render as `Decimal('18.22')` inside the summary f-strings. The
    registry works in Decimal internally, so this is the boundary KNW-03 must keep.
    """
    state = await _run(GB_BRIEF)

    for deal in state["selected_deals"]:
        assert isinstance(deal["cpm"], str)
    for option in state["audience_options"]:
        assert isinstance(option["effective_cpm"], str)
        assert isinstance(option["vcpm_fee"], str)


async def test_the_forecast_is_priced_off_the_chosen_audience() -> None:
    """50,000 / 20.22 x 1000, then reach at the mock's 3.2 frequency."""
    forecast = (await _run(GB_BRIEF, PICK))["forecast"]

    assert forecast["estimated_impressions"] == 2_472_799
    assert forecast["estimated_unique_reach"] == 772_749
    assert forecast["average_frequency"] == 3.2
    assert forecast["indicative_cpm"] == "20.22"


# --- the honesty rule --------------------------------------------------------


async def test_third_party_only_inventory_yields_no_reach() -> None:
    """France has no Prime Video in the mock, so the flow must refuse to forecast.

    Schema v2 section 3 step 6: never invent a reach number.
    """
    state = await _run(FR_BRIEF, PICK, session="fr")

    assert state["current_stage"] == "delivered"
    assert state["forecast"]["is_available"] is False
    assert state["forecast"]["estimated_impressions"] == 1_587_301
    assert "estimated_unique_reach" not in state["forecast"]


async def test_the_third_party_reply_never_states_a_reach_figure() -> None:
    """The state is honest; this checks the prose is too."""
    reply = "\n\n".join(_assistant_messages(await _run(FR_BRIEF, PICK, session="fr")))

    assert "I cannot forecast reach for this plan." in reply
    assert "impressions, not unique people" in reply
    assert "Unique reach" not in reply


async def test_audiences_are_unpriced_without_amazon_inventory() -> None:
    """None rather than zero - Amazon audiences do not apply to 3P at all."""
    state = await _run(FR_BRIEF, session="fr")

    assert all(o["effective_cpm"] is None for o in state["audience_options"])
    assert all(o["cpm_basis"] is None for o in state["audience_options"])


# --- the gates ---------------------------------------------------------------


async def test_an_incomplete_brief_asks_for_one_thing_at_a_time() -> None:
    """One question per turn, and it is the first outstanding item in BASICS order.

    This used to assert the opposite - all four at once, on the reasoning that
    drip-feeding is the wizard experience the agent replaces. Reversed
    deliberately: a batched question reads as a form, and the round-trip cost
    falls only on a trader who volunteers nothing, because a full brief still
    answers everything in one message.

    `awaiting` still carries the whole list. Only the question narrows, which is
    what keeps `GET /sessions/{id}` and the `awaiting_count` log field honest.
    """
    state = await _run("I want to run a CTV campaign", session="empty")

    assert state["current_stage"] == "basics"
    assert len(state["awaiting"]) == 4
    assert state.get("selected_deals") is None

    question = _assistant_messages(state)[-1]
    assert "country" in question
    for later in ("start and end dates", "durations", "budget"):
        assert later not in question


async def test_a_partial_brief_asks_only_for_what_is_missing() -> None:
    state = await _run("CTV in the UK, 15 second creatives", session="partial")

    assert state["awaiting"] == ["the start and end dates", "the budget"]


async def test_details_given_out_of_order_are_never_asked_for_again() -> None:
    """The A/C/D case: three of four supplied, so only the fourth is asked about.

    Order in `BASICS` is a preference, not a script - an answer given before its
    turn removes the item rather than being collected twice.
    """
    state = await _run("CTV in the UK, £50,000, 15 and 30 second creatives", session="out-of-order")

    assert state["awaiting"] == ["the start and end dates"]

    question = _assistant_messages(state)[-1]
    assert "start and end dates" in question
    for answered in ("country", "budget", "durations"):
        assert answered not in question


async def test_the_gate_names_every_sellable_duration() -> None:
    """`gates.BASICS` builds this from `duration_phrase()`, not from a literal.

    It used to read "10, 15, 20 or 30 seconds" written out, which would have
    become a lie the day CTV started selling a 6-second ad. Asserted against the
    enum rather than against four numbers, so the day one is added this test
    keeps testing the right thing.

    The brief supplies everything else, because one question per turn means the
    durations question is only reached once nothing earlier is outstanding.
    """
    question = _assistant_messages(
        await _run("CTV in the UK for August 2026, £50,000", session="dur")
    )[-1]

    for duration in (d.value for d in DurationEnum):
        assert duration in question
    assert "seconds" in question


# --- remembering a half-answer -----------------------------------------------
#
# From a reported conversation: the agent asked twice for a budget it had already
# been given. The cause was not question sequencing but `_merge` - a budget cannot
# be keyed into `market_budgets` before a market is named, so it was extracted and
# then dropped, and `missing_basics` truthfully reported it as still absent.
# `_known_summary` read it back out of the same field, so the LLM prompt forgot it
# too. Hence the raw `budget_amount` / `flight_start` / `flight_end` slots.


async def test_a_budget_given_before_a_market_is_not_asked_for_twice() -> None:
    """The reported bug, in two turns."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)
    config = {"configurable": {"thread_id": "budget-first"}}

    first = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "My budget is £50,000"}],
            "advertiser_id": "adv-1",
        },
        config=config,
    )
    # Held even though there is no market to key it to yet.
    assert first["budget_amount"] == "50000.00"
    assert first["market_budgets"] == []
    assert "the budget" not in first["awaiting"]

    second = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "in the UK"}]}, config=config
    )

    assert "the budget" not in second["awaiting"]
    assert second["market_budgets"] == [{"market": "GB", "budget": "50000.00", "base_bid": None}]
    assert "budget" not in _assistant_messages(second)[-1]


async def test_a_half_answered_flight_survives_to_the_next_turn() -> None:
    """`flight_dates` is empty until both ends are known, so the raw slots hold it.

    Driven through the merge rather than the pattern matcher, which always returns
    both ends of a named month - only the LLM path can produce a lone start date.
    """
    from app.agent.nodes.extract_fields import BriefFields, _merge

    partial = _merge({}, BriefFields(flight_start="2099-08-01"))
    assert partial["flight_start"] == "2099-08-01"
    assert partial["flight_dates"] is None

    completed = _merge(partial, BriefFields(flight_end="2099-08-31"))
    assert completed["flight_dates"] == {
        "lower": "2099-08-01",
        "upper": "2099-08-31",
        "bounds": "[)",
    }


async def test_the_llm_is_told_what_is_already_known() -> None:
    """`_known_summary` feeds the prompt, and it used to lose the budget with the
    derived field - so the model asked for it again even on the clever path."""
    from app.agent.nodes.extract_fields import _known_summary

    summary = _known_summary({"budget_amount": "50000.00", "flight_start": "2099-08-01"})

    assert "budget_amount: 50000.00" in summary
    assert "flight_start: 2099-08-01" in summary
    assert "flight_end: unknown" in summary


async def test_a_sparse_opener_converges_one_question_at_a_time() -> None:
    """One question a turn, in BASICS order, and nothing asked about twice."""
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)
    config = {"configurable": {"thread_id": "progressive"}}

    answers = (
        "I want to run a CTV campaign",
        "the UK",
        "August 2026",
        "15 and 30 second creatives",
        "£50,000",
        PICK,
    )

    asked, prior = [], 0
    for message in answers:
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )
        replies = _assistant_messages(state)
        asked.append("\n\n".join(m for m in replies[prior:] if m))
        prior = len(replies)

    # Every turn up to the audience choice ends in exactly one question.
    for reply in asked[:-2]:
        assert reply.count("?") == 1

    # Each item is asked about once across the whole conversation, in order. The
    # duration label carries the dash so it cannot match "- Creative durations:"
    # in the confirmation block.
    transcript = "\n".join(asked)
    positions = [
        transcript.index(label)
        for label in ("country", "start and end dates", "creative durations -", "the budget")
        if transcript.count(label) == 1 or pytest.fail(f"{label!r} not asked exactly once")
    ]
    assert positions == sorted(positions)

    # The last basic completes the brief, which offers the audiences; naming one
    # delivers the plan.
    assert state["current_stage"] == "delivered"
    assert state["awaiting"] == []


# --- the registry's place in a turn ------------------------------------------


async def test_the_registry_is_read_every_turn_but_synced_only_once(caplog) -> None:
    """Grounded data is read every turn; it is fetched from VOW only when stale.

    Written because the absence of a `registry.sync` line on turns 2 and 3 reads
    like the registry not being consulted, and it means the opposite - the
    snapshot was already in hand. Re-ingesting per turn would cost eight MCP
    calls a turn and let prices move under a trader mid-conversation.

    Inventory is observed through the state rather than through a log line: the
    nodes no longer log, so `selected_deals` is the evidence that the registry
    was consulted and the plan was built from it.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    brief = "CTV campaign in the UK for August 2099, £50,000, 30 second creatives"

    syncs, validations, deals = [], [], []
    for turn in range(3):
        caplog.clear()
        with caplog.at_level("INFO"):
            state = await graph.ainvoke(
                {"messages": [{"role": "user", "content": brief}], "advertiser_id": "adv-1"},
                config={"configurable": {"thread_id": f"sync-{turn}"}},
            )
        events = [r.message for r in caplog.records]
        syncs.append(events.count("registry.sync"))
        validations.append(events.count("stage.validation"))
        deals.append(len(state.get("selected_deals") or []))

    # Fetched once, on the cold turn only.
    assert syncs == [1, 0, 0]
    # Consulted on every turn - validation is grounded against the snapshot.
    assert validations == [1, 1, 1]
    # And every turn planned against real inventory, cached or freshly synced.
    assert all(count > 0 for count in deals), deals


# --- the audit trail ----------------------------------------------------------
#
# These pin the records a client is shown as evidence that values are grounded.
# They assert on log output deliberately: the audit trail *is* the deliverable
# here, so a change that silently stops emitting it should fail a test rather
# than be discovered when someone asks for the evidence.


async def test_the_audit_trail_narrates_a_rejected_market_in_order(caplog) -> None:
    """A rejected market leaves a readable, ordered account of why.

    The order matters and is the architecture: constraints are stated before the
    brief is read, and grounding happens after. A trail implying the prompt was
    constrained by the advertiser's snapshot would be untrue - see
    `audit.prompt_constraints`, which records `snapshot_consulted=False` for
    exactly this reason.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))

    # `markets` is seeded rather than written in the brief because the pattern
    # extractor only recognises GB/US/FR/DE - every market it can read is one the
    # mock registry sells, so a message alone cannot produce a rejection. Seeding
    # exercises the real path: `_merge` carries the value forward, and
    # `validate_basics` grounds it against the snapshot like any other.
    with caplog.at_level("INFO"):
        await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": "30 second creatives for August 2026"}],
                "markets": ["CN"],
                "advertiser_id": "adv-1",
            },
            config={"configurable": {"thread_id": "audit-reject"}},
        )

    trail = [
        r.message for r in caplog.records if r.message.startswith(("audit.", "stage.validation"))
    ]
    assert trail == [
        "audit.input_received",
        "audit.registry_lookup",
        "stage.validation",
        "audit.question_asked",
    ], trail

    fields = {r.message: r.extra_fields for r in caplog.records if hasattr(r, "extra_fields")}

    lookup = fields["audit.registry_lookup"]
    assert lookup["valid"] is False
    assert lookup["market"] == "CN"
    # The rejection names what VOW does sell, which is the half a trader can act on.
    assert "US" in lookup["supported_markets"]
    assert "CN" not in lookup["supported_markets"]
    # Which snapshot answered - a verdict without this cannot be re-checked later.
    assert lookup["snapshot_version"] >= 1
    assert lookup["snapshot_hash"]

    verdict = fields["stage.validation"]
    assert verdict["verdict"] == "FAILED"
    # No LLM in this suite, so the trail must not claim one ran.
    assert verdict["source"] == "patterns"
    # `market.unknown` is the validator's code; `registry.market_not_sold` is the
    # ingestion event. Both belong in the trail - one says the snapshot refused to
    # fetch the market, the other says the plan was blocked because of it.
    assert "market.unknown" in verdict["new_warnings"]
    assert "registry.market_not_sold" in [r.message for r in caplog.records]

    # And the narrower half: what the agent is actually asking for right now.
    asked = fields["audit.question_asked"]
    assert asked["kind"] == "conflict"
    assert asked["asked"] == "market.unknown"


async def test_the_audit_trail_states_only_the_constraints_that_exist(caplog) -> None:
    """`audit.prompt_constraints` may not overstate what constrains the prompt.

    Emitted only when a model actually runs, and it claims exactly one
    registry-derived rule - the duration vocabulary. Asserted because the
    temptation to add `allowed_markets` here is real and it would put a false
    statement into a client-facing record: this node runs before a market is
    known, so no snapshot exists to constrain against.
    """
    # The module, not the re-exported function of the same name.
    node = import_module("app.agent.nodes.extract_fields")

    class _FakeLLM:
        def with_structured_output(self, *_args, **_kwargs):
            return self

        async def ainvoke(self, _messages):
            return {"parsed": node.BriefFields(markets=["US"]), "raw": None}

    state = {"messages": [{"role": "user", "content": "US campaign"}]}
    with caplog.at_level("INFO"):
        # Patched at the import site, as the suite's `_no_llm` fixture does.
        original, node.get_llm = node.get_llm, lambda: _FakeLLM()
        try:
            first = await node.extract_fields(state)
            # Second call carries the flag the first one set.
            await node.extract_fields({**state, "audited": first["audited"]})
        finally:
            node.get_llm = original

    records = [r for r in caplog.records if r.message == "audit.prompt_constraints"]
    # Once per session, not once per turn - the payload is a constant.
    assert len(records) == 1, [r.extra_fields for r in records]

    fields = records[0].extra_fields
    assert fields["snapshot_consulted"] is False
    assert fields["constraint_source"] == "registry.models.DurationEnum"
    assert set(fields["allowed_durations"]) == {d.value for d in DurationEnum}
    assert "allowed_markets" not in fields


async def test_no_commercial_value_reaches_the_audit_trail(caplog) -> None:
    """Budgets are proved checked, never quoted.

    `audit.input_received` names which fields were validated; the amount stays
    out of a log that is shared, rotated and read by whoever has the console.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))

    with caplog.at_level("INFO"):
        await graph.ainvoke(
            {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
            config={"configurable": {"thread_id": "audit-money"}},
        )

    rendered = "\n".join(f"{r.message} {getattr(r, 'extra_fields', {})}" for r in caplog.records)
    assert "50000" not in rendered and "50,000" not in rendered, rendered

    received = next(r for r in caplog.records if r.message == "audit.input_received").extra_fields
    # What is still needed, not what has been supplied - the supplied list only
    # ever grows, and "what does the agent still need" is the useful question.
    assert received["missing"] == []
    assert received["market"] == "GB"
    assert "budget_amount" not in received


async def test_a_repeated_turn_adds_nothing_but_the_decision(caplog) -> None:
    """Saying the same thing twice produces the decision and no restated evidence.

    This is the volume fix. `audit.input_received` is digest-guarded on
    (market, durations, missing) and `audit.registry_lookup` on the snapshot's
    content hash, so an unchanged turn emits only the verdict plus a compact
    proof-of-consultation line.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "audit-repeat"}}

    async def turn():
        caplog.clear()
        with caplog.at_level("INFO"):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
                config=config,
            )
        return [r.message for r in caplog.records if r.message.startswith(("audit.", "stage."))]

    first, second = await turn(), await turn()

    assert "audit.input_received" in first
    # Nothing about the input changed, so nothing is restated.
    assert "audit.input_received" not in second, second
    # The decision and the proof of consultation still appear every turn.
    assert "stage.validation" in second
    assert "audit.registry_lookup" in second
    assert len(second) < len(first)


async def test_the_registry_proof_is_stated_in_full_once_then_compactly(caplog) -> None:
    """Consultation is proved every turn; the unchanging metadata is not repeated.

    `supported_markets`, the hash and the loaded-market list are byte-identical
    while the snapshot is, so they are stated on first use and referenced by
    version afterwards. `valid` - the signal that matters - stays on every line.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "audit-compact"}}

    async def lookup():
        caplog.clear()
        with caplog.at_level("INFO"):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
                config=config,
            )
        return next(r.extra_fields for r in caplog.records if r.message == "audit.registry_lookup")

    full, compact = await lookup(), await lookup()

    assert "supported_markets" in full and "snapshot_hash" in full
    assert "supported_markets" not in compact and "snapshot_hash" not in compact
    # The core signal survives compaction - that is the point of keeping the line.
    assert compact["valid"] is True
    assert compact["market"] == "GB"
    assert compact["snapshot_version"] == full["snapshot_version"]


async def test_a_warning_is_logged_when_it_appears_when_it_resolves_and_if_it_returns(
    caplog,
) -> None:
    """Warnings are state-aware, including the case that trips naive suppression.

    Appear -> repeat -> resolve -> reappear. The reappearance is the important
    assertion: suppression that unions the codes it has seen would swallow it, and
    `gates.say`'s docstring records the same trap for prose - a note that fell
    silent got treated as a repeat of what it said two turns ago.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "audit-warning"}}

    async def turn(message):
        caplog.clear()
        with caplog.at_level("INFO"):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
                config=config,
            )
        return next(r.extra_fields for r in caplog.records if r.message == "stage.validation")

    # 10s is on the GB rate card only for some providers; `duration.not_on_rate_card`
    # is raised for a length the market does not carry at all.
    bad = "CTV campaign in the UK for August 2026, £50,000, 20 second creatives"
    good = "make it 30 second creatives"

    appeared = await turn(bad)
    codes = appeared.get("new_warnings")
    assert codes, f"expected a warning from {bad!r}, got {appeared}"

    # Absent, not empty: a quiet turn carries neither key, so the turn where
    # something did change stands out in the stream.
    repeated = await turn(bad)
    assert "new_warnings" not in repeated, repeated
    assert "resolved" not in repeated, repeated

    resolved = await turn(good)
    assert resolved.get("resolved") == codes, resolved
    assert "new_warnings" not in resolved, resolved

    returned = await turn(bad)
    assert returned.get("new_warnings") == codes, returned


async def test_a_second_market_restates_the_registry_proof_in_full(caplog) -> None:
    """Compaction is keyed on the snapshot, so new grounding data re-states itself.

    Lazily loading a second market changes `content_hash`, which is what the
    compaction compares against - so the full record returns exactly when the
    data behind the verdict has moved, rather than on a timer or turn count.
    """
    get_store().invalidate()
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "audit-second-market"}}

    async def lookup(message):
        caplog.clear()
        with caplog.at_level("INFO"):
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
                config=config,
            )
        return next(r.extra_fields for r in caplog.records if r.message == "audit.registry_lookup")

    gb = await lookup(GB_BRIEF)
    assert "snapshot_hash" in gb

    repeat = await lookup(GB_BRIEF)
    assert "snapshot_hash" not in repeat, "unchanged snapshot should stay compact"

    moved = await lookup("actually run it in the US instead")
    assert "snapshot_hash" in moved, "a newly loaded market must restate the proof"
    assert moved["snapshot_hash"] != gb["snapshot_hash"]
    assert moved["market"] == "US"


async def test_a_second_market_syncs_that_market_only() -> None:
    """Per-market facets fill lazily, so a new market costs one fetch, not a rebuild."""
    get_store().invalidate()
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)

    await graph.ainvoke(
        {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
        config={"configurable": {"thread_id": "m1"}},
    )
    core_calls = len([c for c in mcp.calls if c[0] == "vow.get_deal_filter_properties"])

    await graph.ainvoke(
        {"messages": [{"role": "user", "content": FR_BRIEF}], "advertiser_id": "adv-1"},
        config={"configurable": {"thread_id": "m2"}},
    )

    # Core facets are market-independent, so they are not re-fetched.
    assert len([c for c in mcp.calls if c[0] == "vow.get_deal_filter_properties"]) == core_calls
    assert len([c for c in mcp.calls if c[0] == "vow.list_deals"]) == 2


# --- validators recording rather than gating ---------------------------------


async def test_a_flight_starting_in_the_past_is_recorded_but_does_not_block() -> None:
    """Recorded, not gated - and the distinction is deliberate.

    "August 2026" parses perfectly whether or not August 2026 has been, so the
    check has to exist. But a wrong date is a correction, not a missing input:
    blocking would throw away a plan the trader can fix in one word.
    `validate_plan_ready_for_approval` folds `validation_errors` in at the
    approval interrupt, which is where budget locks and so where it must not pass.
    """
    state = await _run(
        "CTV campaign in the UK for August 2020, £50,000, 30 second creatives", session="past"
    )

    assert _codes(state) == ["flight_dates.in_past"]
    assert state["current_stage"] == "validation"
    # Nothing downstream ran: no inventory was looked up against an impossible flight.
    assert not state.get("selected_deals")
    assert "already passed" in "\n\n".join(_assistant_messages(state))


async def test_a_bad_value_is_raised_before_the_remaining_gaps_are_collected() -> None:
    """Checked on the turn it arrives, not once every other field has landed.

    Validation runs as soon as there is a market to ground against, and skips the
    rules whose inputs are still absent. Gating it on complete basics instead meant
    a trader could give a bad date on turn two and hear about it on turn five,
    after answering three unrelated questions.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)
    config = {"configurable": {"thread_id": "early"}}

    for message in ("CTV in the UK", "August 2020"):
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )

    # Durations and budget are still missing, but the date is what gets raised.
    assert set(state["awaiting"]) == {
        "the creative durations - 10, 15, 20 or 30 seconds",
        "the budget",
    }
    assert _codes(state) == ["flight_dates.in_past"]

    question = _assistant_messages(state)[-1]
    assert "already passed" in question
    assert "budget" not in question


async def test_correcting_a_blocked_value_clears_it_and_resumes() -> None:
    """The round trip the whole change exists for.

    Nothing clears the error explicitly - the graph re-runs from `extract_fields`
    every turn and `gates.record` replaces what the stage owns, so a corrected
    value simply produces no entry. That is why "revalidate before continuing"
    needs no code of its own.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)
    config = {"configurable": {"thread_id": "corrected"}}

    blocked = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "CTV in the UK for August 2020, £50,000, 30 second creatives",
                }
            ],
            "advertiser_id": "adv-1",
        },
        config=config,
    )
    assert _codes(blocked) == ["flight_dates.in_past"]

    resumed = await graph.ainvoke(
        {"messages": [{"role": "user", "content": f"make it August 2099 instead, {PICK}"}]},
        config=config,
    )

    assert _codes(resumed) == []
    assert resumed["current_stage"] == "delivered"
    assert resumed["flight_dates"]["lower"] == "2099-08-01"


async def test_a_future_flight_records_nothing() -> None:
    state = await _run(
        "CTV campaign in the UK for August 2099, £50,000, 30 second creatives", session="future"
    )

    assert _codes(state) == []


async def test_a_forecast_that_contradicts_itself_is_recorded_and_said() -> None:
    """Section 3 step 6: never invent a reach number.

    A payload claiming reach is unavailable while carrying one means the server's
    contract has moved. `_summary` would not speak the number, but silence would
    leave the drift invisible.

    Recorded as a *warning* rather than a blocker: it is VOW's payload that is
    wrong, so stopping to ask the trader would demand a fix only VOW can make -
    and a blocking entry would still be in state next turn, diverting a turn with
    nothing wrong with it.
    """

    class _DishonestForecast(MockMCPClient):
        async def _call_tool_raw(self, name: str, arguments: dict):
            payload = await super()._call_tool_raw(name, arguments)
            if name.endswith("reach_forecast"):
                payload = {**payload, "is_available": False, "estimated_unique_reach": 999_999}
            return payload

    graph = build_graph(checkpointer=MemorySaver(), mcp=_DishonestForecast(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "dishonest"}}
    for message in (GB_BRIEF, PICK):
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )

    assert _codes(state, severity="warning") == ["forecast.fabricated_reach"]
    assert state["current_stage"] == "delivered"

    reply = "\n\n".join(_assistant_messages(state))
    # Said out loud now, not only filed. The fabricated number still never appears.
    assert "will not report that as reach" in reply
    assert "999,999" not in reply


# --- explaining a dead end ---------------------------------------------------
#
# From a reported conversation: a 10-second GB brief produced "I could not find
# CTV inventory for GB. Shall I widen the market or the durations?" followed by
# "Before I can carry on I need no CTV inventory matched - a different market or
# set of durations. Could you tell me?" - two questions, one ungrammatical, and
# neither saying that GB simply does not sell 10s. The node had computed exactly
# that and left it in `validation_errors`, which nothing reads.

TEN_SECOND_GB = "CTV in the UK for August 2099, £50,000, 10 second creatives"


async def test_an_unsellable_duration_is_explained_not_reported_as_no_inventory() -> None:
    """The reason, in the trader's terms, from the rate card.

    The diagnosis now arrives from `validate_basics` via the registry's
    `validate_durations` rather than from a string the node built itself - which
    was a second implementation of the same check. `_dead_end` drops its own lead
    sentence when validation has already given it, so the trader is not told twice.
    """
    reply = "\n\n".join(_assistant_messages(await _run(TEN_SECOND_GB, session="dead")))

    assert "10-second is not on the GB rate card" in reply
    assert "I could not find CTV inventory" not in reply
    # Said once, not twice: the node's own phrasing of the same fact is suppressed.
    assert "GB does not sell 10s CTV" not in reply


async def test_the_dead_end_offers_grounded_alternatives() -> None:
    """Both ways out, with real numbers - 4 GB deals, cheapest at 18.22."""
    reply = "\n\n".join(_assistant_messages(await _run(TEN_SECOND_GB, session="dead2")))

    assert "plan GB with 15s or 30s - 4 deals, from 18.22 CPM" in reply
    assert "keep 10s" in reply


async def test_the_dead_end_asks_exactly_one_question() -> None:
    """Two questions in a turn is worse than one - the trader has to pick which
    to answer, and the second was the vaguer of the two."""
    reply = "\n\n".join(_assistant_messages(await _run(TEN_SECOND_GB, session="dead3")))

    assert reply.count("?") == 1
    assert "Could you tell me?" not in reply


async def test_the_mangled_sentinel_no_longer_reaches_the_trader() -> None:
    """`NO_INVENTORY` was a sentence inside a list of noun phrases."""
    reply = "\n\n".join(_assistant_messages(await _run(TEN_SECOND_GB, session="dead4")))

    assert "I need no CTV inventory matched" not in reply
    assert "no CTV inventory matched" not in reply


async def test_the_diagnosis_is_still_recorded_for_approval() -> None:
    """Saying it out loud does not mean dropping it from state.

    It rides along structured now - code, field and the rate card's own options -
    so the UI can render it and `validate_plan_ready_for_approval` can decide
    whether it blocks. This one does not: an off-rate-card duration is a warning,
    and the plan is still worth building around what the market does carry.
    """
    state = await _run(TEN_SECOND_GB, session="dead5")

    (entry,) = state["validation_errors"]
    assert entry["code"] == "duration.not_on_rate_card"
    assert entry["field"] == "durations"
    assert entry["severity"] == "warning"
    assert entry["suggested_options"] == ["15", "30"]
    assert entry["stage"] == "validation"
    assert state["awaiting"] == ["a market or set of durations with inventory available"]


async def test_a_market_with_no_inventory_at_all_reads_differently() -> None:
    """Two dead ends the old message conflated, needing opposite answers: the
    market sells nothing, or it sells nothing at this length."""

    class _EmptyMarket(MockMCPClient):
        async def _call_tool_raw(self, name: str, arguments: dict):
            payload = await super()._call_tool_raw(name, arguments)
            if name == "vow.list_deals":
                payload = {"count": 0, "results": []}
            return payload

    # Its own advertiser, because the registry store is process-wide and every
    # other test in this file has already cached a GB snapshot with four deals.
    get_store().invalidate("empty-co")
    graph = build_graph(checkpointer=MemorySaver(), mcp=_EmptyMarket(advertiser_id="empty-co"))
    state = await graph.ainvoke(
        {"messages": [{"role": "user", "content": TEN_SECOND_GB}], "advertiser_id": "empty-co"},
        config={"configurable": {"thread_id": "empty-market"}},
    )
    reply = "\n\n".join(_assistant_messages(state))

    assert "no CTV inventory at all for GB" in reply
    assert "does not sell" not in reply


# --- confirming only what changed --------------------------------------------


async def test_the_first_turn_confirms_what_was_understood() -> None:
    """Schema v2 section 7.3 calls this the most important trust mechanism."""
    reply = "\n\n".join(_assistant_messages(await _run(GB_BRIEF, session="c1")))

    assert "Here is what I understood" in reply


async def test_a_turn_that_changes_nothing_does_not_re_confirm() -> None:
    """Reprinting the whole block after "i dont know" reads as the agent having
    lost its place and started over."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "c2"}}

    first = await graph.ainvoke(
        {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
        config=config,
    )
    before = len(_assistant_messages(first))
    state = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "i dont know"}], "advertiser_id": "adv-1"},
        config=config,
    )

    new = _assistant_messages(state)[before:]
    assert new, "a turn must always produce at least one reply"
    assert not any("Here is what I understood" in m for m in new)


async def test_a_correction_is_still_confirmed() -> None:
    """The mechanism only earns its noise if a changed value is echoed back."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "c3"}}

    first = await graph.ainvoke(
        {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"},
        config=config,
    )
    before = len(_assistant_messages(first))
    state = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "make it France instead"}],
            "advertiser_id": "adv-1",
        },
        config=config,
    )

    new = "\n\n".join(_assistant_messages(state)[before:])
    assert "Here is what I understood" in new
    assert "Markets: FR" in new


async def test_every_turn_still_produces_a_reply(caplog) -> None:
    """`sessions.chat` raises a 500 when a turn says nothing at all.

    Every stage can now stay quiet - that is the point of `gates.say` - so a turn
    saying nothing is the one way this design fails, and it is worth pinning across
    the paths where the graph says least.
    """
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))

    for label, messages in (
        ("incomplete", ["plan a CTV campaign", "i dont know", "hmm", "not sure"]),
        ("awaiting-choice", [GB_BRIEF, "ok", "i dont know", "sure"]),
        ("delivered", [GB_BRIEF, PICK, "thanks", "ok", "great"]),
        ("dead-end", [TEN_SECOND_GB, "ok", "hmm"]),
    ):
        config = {"configurable": {"thread_id": f"reply-{label}"}}
        seen = 0
        for message in messages:
            state = await graph.ainvoke(
                {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
                config=config,
            )
            produced = _assistant_messages(state)
            assert len(produced) > seen, f"{label!r} said nothing to {message!r}"
            seen = len(produced)


# --- never saying the same thing twice ---------------------------------------
#
# From a reported conversation: a complete GB brief priced in USD returned a
# byte-identical 1423-character reply on four consecutive turns - the inventory
# list, the three audience options and the currency warning, over and over, with no
# way to reach a finished plan. Three causes: nothing checked whether a stage would
# repeat itself, the audience choice was not an input at all, and there was no state
# after a forecast.

# `$50,000` rather than `50,000 USD` for the reason FR_BRIEF gives: the pattern
# matcher only reads a bare number as money with a symbol, a k/m suffix, or the word
# "budget" nearby, and these tests run the deterministic path. The symbol is also
# what makes the currency USD, which is the mismatch this scenario needs.
USD_ON_GB = "CTV campaign in the UK for August 2026, $50,000, 15 and 30 second creatives"


async def _transcript(graph, config, messages: list[str]) -> list[str]:
    """What the trader reads each turn, the way `sessions.chat` assembles it."""
    turns, seen = [], 0
    for message in messages:
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )
        replies = _assistant_messages(state)
        turns.append("\n\n".join(m for m in replies[seen:] if m))
        seen = len(replies)
    return turns


async def test_the_reported_loop_is_gone() -> None:
    """The whole defect, as one assertion set."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    turns = await _transcript(
        graph,
        {"configurable": {"thread_id": "loop"}},
        [USD_ON_GB, "Using USD is deliberate", "Yes, deliberate - proceed", PICK, "Proceed"],
    )

    # AC4: no *block* is ever shown twice in a row. Two consecutive short
    # re-prompts are allowed and correct - the audience question is still open, and
    # a live question has to stay live. What must never repeat is the wall of text.
    blocks = [turn for turn in turns if len(turn) > 200]
    assert all(a != b for a, b in zip(blocks, blocks[1:], strict=False))
    assert len(set(blocks)) == len(blocks)

    # AC2: the note is made once while collecting, however many times the trader
    # says it was deliberate. It appears once more in the delivered plan, on purpose
    # - a consolidated record that omits a known caveat is what gets approved by
    # someone who missed it four turns earlier.
    collecting = "\n\n".join(turns[:-2])
    assert collecting.count("GBP is the usual currency there") == 1
    assert turns[-2].count("GBP is the usual currency there") == 1

    # The inventory list and the options block are each presented once.
    whole = "\n\n".join(turns)
    assert whole.count("CTV inventory available in GB") == 1
    assert whole.count("**Narrow** - In-market") == 1


async def test_a_reply_about_something_else_does_not_restate_the_options() -> None:
    """The choice is still outstanding, so the question has to stay live - but in a
    line, not by reprinting twenty."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    first, second = await _transcript(
        graph, {"configurable": {"thread_id": "reask"}}, [GB_BRIEF, "Using GBP is deliberate"]
    )

    assert "**Narrow** - In-market" in first
    assert "**Narrow** - In-market" not in second
    assert second.strip() == (
        "Still need an audience before I can forecast - Narrow, Balanced or Wide?"
    )


async def test_a_stated_currency_survives_a_market_change() -> None:
    """Inference is a fallback for the unknown, not an answer that outranks the trader.

    `_extract_with_patterns` used to fill the currency from the market on every
    turn, so any message naming a market restated one - and "back to the UK" turned
    a deliberately-USD budget into GBP without a word. Same family as the dropped
    budget: a derived value overwriting a stated one.
    """
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "sticky-currency"}}

    for message in (USD_ON_GB, "make it the US instead", "back to the UK please"):
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "advertiser_id": "adv-1"},
            config=config,
        )

    assert state["markets"] == ["GB"]
    assert state["primary_currency"] == "USD"


async def test_a_currency_with_no_symbol_still_defaults_from_the_market() -> None:
    """The fallback that has to keep working: nothing stated, so derive it."""
    state = await _run(GB_BRIEF, session="derived-currency")

    assert state["primary_currency"] == "GBP"


async def test_the_currency_note_returns_when_the_market_changes() -> None:
    """Suppression is derived, not a dismissed flag.

    A stored `currency_warning_dismissed` would stay dismissed after the trader
    moved the campaign to a market where USD *is* the default and then back again.
    Comparing what was last said gets this right for free.
    """
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    gb, us, back = await _transcript(
        graph,
        {"configurable": {"thread_id": "currency"}},
        [USD_ON_GB, "make it the US instead", "back to the UK please"],
    )

    assert "GBP is the usual currency there" in gb
    assert "usual currency" not in us  # USD is right for the US - nothing to note
    assert "GBP is the usual currency there" in back


# --- delivering the plan ------------------------------------------------------


async def test_the_delivered_plan_synthesises_every_input() -> None:
    """AC3: one consolidated record, not four turns of scrollback."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    _, delivered = await _transcript(
        graph, {"configurable": {"thread_id": "deliver"}}, [GB_BRIEF, PICK]
    )

    for fact in (
        "CTV GB 2026-08",
        "Market: GB",
        "2026-08-01 to 2026-08-31",
        "15, 30 seconds",
        "50,000 GBP",
        "4 deals",
        "Balanced",
        "20.22 effective CPM",
        "2,472,799",
        "772,749",
    ):
        assert fact in delivered, fact

    # AC3: it stops presenting the lists it was looping on.
    assert "CTV inventory available in GB" not in delivered
    assert "**Wide** - Broad demographic" not in delivered


async def test_a_no_op_turn_after_delivery_acknowledges_rather_than_restating() -> None:
    """AC4, the other half: "thanks" must not reprint the plan."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    _, delivered, after = await _transcript(
        graph, {"configurable": {"thread_id": "ack"}}, [GB_BRIEF, PICK, "thanks, proceed"]
    )

    assert "here is the complete plan" in delivered
    assert "here is the complete plan" not in after
    assert "Tell me what to change" in after
    assert len(after) < len(delivered) / 4


async def test_a_change_after_delivery_re_plans() -> None:
    """ "Restart" and "go back" need no intent classifier - a change is a change."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    turns = await _transcript(
        graph,
        {"configurable": {"thread_id": "replan"}},
        [GB_BRIEF, PICK, "make the budget £80,000"],
    )

    assert "80,000 GBP" in turns[-1]
    assert "3,956,478" in turns[-1]  # 80,000 / 20.22 x 1000


async def test_a_word_that_names_no_option_is_asked_about_again() -> None:
    """ "Aggressive" is not one of the three, and the patterns do not match it, so
    nothing is extracted and the question stays open. Guessing a profile from an
    unrecognised adjective would commit budget against an audience nobody picked."""
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    turns = await _transcript(
        graph, {"configurable": {"thread_id": "bad-word"}}, [GB_BRIEF, "use the aggressive one"]
    )

    assert "Still need an audience" in turns[-1]
    assert turns[-1].count("?") == 1


async def test_a_profile_the_server_did_not_offer_is_a_conflict() -> None:
    """Not silence, and not a guess - the registry supplies the three real names.

    `audience_choice` is seeded directly rather than typed: `_audience_profile` only
    matches the three words it knows, so the deterministic path cannot produce an
    ungrounded profile. The LLM path can, and this is what happens when it does.
    """
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="adv-1"))
    config = {"configurable": {"thread_id": "bad-profile"}}

    await graph.ainvoke(
        {"messages": [{"role": "user", "content": GB_BRIEF}], "advertiser_id": "adv-1"}, config
    )
    state = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "that one"}],
            "audience_choice": "AGGRESSIVE",
        },
        config,
    )

    assert _codes(state) == ["audience.unknown_profile"]
    assert state["chosen_audience"] is None

    question = _assistant_messages(state)[-1]
    assert "not one of the three audience options" in question
    assert "BALANCED, NARROW, WIDE" in question


# --- the reply as a whole ----------------------------------------------------


async def test_the_gb_reply_is_unchanged() -> None:
    """The verbatim contract, over the two turns a plan now takes.

    Deliberately one assertion over the joined text rather than several over
    fragments - the seams between node messages are part of what the trader sees,
    and so is the fact that the options block appears once and the plan once.
    """
    reply = "\n\n".join(_assistant_messages(await _run(GB_BRIEF, PICK)))

    assert reply == (
        "Here is what I understood - correct anything that is wrong before I continue.\n"
        "\n"
        "- Markets: GB\n"
        "- Flight: 2026-08-01 to 2026-08-31\n"
        "- Creative durations: 15, 30\n"
        "- Currency: GBP\n"
        "- Budget: 50000.00 GBP (GB)\n"
        "- Goal: Awareness, measured on reach (fixed for CTV)\n"
        "\n"
        "CTV inventory available in GB:\n"
        "\n"
        "- Prime Video - 18.22 CPM (15, 30s) - Amazon-owned (reach forecast available)\n"
        "- Prime Video | Action - 22.07 CPM (15, 30s) - Amazon-owned (reach forecast available)\n"
        "- Netflix - 31.50 CPM (30s) - third-party, pre-curated (no reach forecast)\n"
        "- Disney+ - 34.00 CPM (15, 30s) - third-party, needs curation (rate card only)\n"
        "\n"
        "Prime Video run-of-service is 18.22; Action is 22.07. If the brief implies Action, the higher CPM usually buys a better match.\n"
        "\n"
        "Three audience options - tell me which to use and I will forecast against it. Balanced is the usual recommendation.\n"
        "\n"
        "**Narrow** - In-market: premium streaming, high intent\n"
        "  6 segments, ~1,200,000 people\n"
        "  18.22 + 3.50 fee = 21.72 effective CPM\n"
        "  highest intent, smallest pool, highest fee - underdelivery risk\n"
        "\n"
        "**Balanced** - Lifestyle: entertainment enthusiasts 25-54\n"
        "  14 segments, ~4,800,000 people\n"
        "  18.22 + 2.00 fee = 20.22 effective CPM\n"
        "  the usual recommendation\n"
        "\n"
        "**Wide** - Broad demographic: adults 18+\n"
        "  31 segments, ~15,400,000 people\n"
        "  18.22 + 0.85 fee = 19.07 effective CPM\n"
        "  widest reach, lowest fee, least precision\n"
        "\n"
        "Amazon audiences apply to the Prime Video portion only. Netflix and Disney+ use their own targeting, which adds their own CPM.\n"
        "\n"
        "**CTV GB 2026-08** - here is the complete plan.\n"
        "\n"
        "- Market: GB\n"
        "- Flight: 2026-08-01 to 2026-08-31\n"
        "- Creative durations: 15, 30 seconds\n"
        "- Budget: 50,000 GBP\n"
        "- Goal: Awareness, measured on reach (fixed for CTV)\n"
        "\n"
        "- Inventory: 4 deals, Amazon-owned (reach forecast available)\n"
        "- Audience: Balanced - Lifestyle: entertainment enthusiasts 25-54 (~4,800,000 people, 20.22 effective CPM)\n"
        "\n"
        "Forecast for the Amazon portion:\n"
        "\n"
        "- Impressions: 2,472,799\n"
        "- Unique reach: 772,749 people\n"
        "- Average frequency: 3.2\n"
        "- Indicative CPM: 20.22\n"
        "\n"
        "Next: say the word and I will create this strategy in VOW, or tell me what to change and I will re-plan."
    )


async def test_the_fr_reply_is_unchanged() -> None:
    """The third-party path, verbatim - the honesty rule is prose, not just a flag."""
    reply = "\n\n".join(_assistant_messages(await _run(FR_BRIEF, PICK, session="fr")))

    assert reply == (
        "Here is what I understood - correct anything that is wrong before I continue.\n"
        "\n"
        "- Markets: FR\n"
        "- Flight: 2026-08-01 to 2026-08-31\n"
        "- Creative durations: 30\n"
        "- Currency: EUR\n"
        "- Budget: 50000.00 EUR (FR)\n"
        "- Goal: Awareness, measured on reach (fixed for CTV)\n"
        "\n"
        "CTV inventory available in FR:\n"
        "\n"
        "- Netflix - 31.50 CPM (30s) - third-party, pre-curated (no reach forecast)\n"
        "- Disney+ - 34.00 CPM (15, 30s) - third-party, needs curation (rate card only)\n"
        "\n"
        "Three audience options - tell me which to use and I will forecast against it. Balanced is the usual recommendation.\n"
        "\n"
        "**Narrow** - In-market: premium streaming, high intent\n"
        "  6 segments, ~1,200,000 people\n"
        "  3.50 fee (no Amazon inventory to price against)\n"
        "  highest intent, smallest pool, highest fee - underdelivery risk\n"
        "\n"
        "**Balanced** - Lifestyle: entertainment enthusiasts 25-54\n"
        "  14 segments, ~4,800,000 people\n"
        "  2.00 fee (no Amazon inventory to price against)\n"
        "  the usual recommendation\n"
        "\n"
        "**Wide** - Broad demographic: adults 18+\n"
        "  31 segments, ~15,400,000 people\n"
        "  0.85 fee (no Amazon inventory to price against)\n"
        "  widest reach, lowest fee, least precision\n"
        "\n"
        "Note: this plan has no Amazon inventory, so Amazon audiences do not apply at all - the providers' own targeting governs.\n"
        "\n"
        "**CTV FR 2026-08** - here is the complete plan.\n"
        "\n"
        "- Market: FR\n"
        "- Flight: 2026-08-01 to 2026-08-31\n"
        "- Creative durations: 30 seconds\n"
        "- Budget: 50,000 EUR\n"
        "- Goal: Awareness, measured on reach (fixed for CTV)\n"
        "\n"
        "- Inventory: 2 deals, third-party, pre-curated (no reach forecast)\n"
        "- Audience: Balanced - Lifestyle: entertainment enthusiasts 25-54 (~4,800,000 people, 2.00 fee, no Amazon inventory to price against)\n"
        "\n"
        "I cannot forecast reach for this plan.\n"
        "\n"
        "Reach forecasting is available for Amazon inventory only.\n"
        "\n"
        "What I can tell you: at 31.50 CPM, 50,000 EUR buys roughly 1,587,301 impressions.\n"
        "\n"
        "That is impressions, not unique people - I have no way to tell you how many individuals that reaches, and I will not estimate it.\n"
        "\n"
        "Next: say the word and I will create this strategy in VOW, or tell me what to change and I will re-plan."
    )


# --- what the UI is given ----------------------------------------------------
#
# The graph's structured output, as `sessions.chat` serializes it. Pinned here
# rather than only in tests/unit/api because the interesting cases are the ones
# only a real registry produces: which rules ran on a clean brief, and the
# forecast honesty rule's own evidence.


def _check_codes(state: dict) -> list[str]:
    """Every rule that ran, passes included - `validation_checks`, not `_errors`."""
    return [entry["code"] for entry in state.get("validation_checks") or []]


async def test_a_clean_brief_records_the_rules_that_passed() -> None:
    """`validation_errors` is empty exactly when everything grounded, which leaves a
    UI unable to tell that from nothing having been checked. The passes are the
    evidence, and `_checks` skips a rule whose input is absent - so this list is
    also the record of which inputs the trader actually gave."""
    state = await _run(GB_BRIEF, PICK, session="ui1")

    assert state["validation_errors"] == []
    assert _check_codes(state) == [
        "market.ok",
        "flight_dates.ok",
        "duration.ok",
        "currency.ok",
        "goal_kpi.ok",
        "audience.ok",
        "forecast.ok",
    ]


async def test_the_third_party_path_records_why_reach_is_unavailable() -> None:
    """`forecast.unavailable_ok` carries `reach_available: False` off VOW's own
    payload. It used to be computed and dropped, which left the honesty rule stated
    in prose and unsupported by anything structured."""
    state = await _run(FR_BRIEF, PICK, session="ui2")

    assert "forecast.unavailable_ok" in _check_codes(state)
    (forecast,) = [
        entry for entry in state["validation_checks"] if entry["code"] == "forecast.unavailable_ok"
    ]
    assert forecast["metadata"] == {"reach_available": False}
    # A pass, so it is not spoken and does not block.
    assert state["validation_errors"] == []


async def test_the_dead_end_diagnosis_reaches_the_wire_unflattened() -> None:
    """The rate card's own options, not the sentence they were phrased into."""
    details = build_validation_details(await _run(TEN_SECOND_GB, session="ui3"))

    (off_card,) = [c for c in details.checks if c.code == "duration.not_on_rate_card"]
    assert off_card.suggested_options == ["15", "30"]
    assert off_card.severity == "warning"
    assert off_card.blocks is False
    assert details.blocks is False
    assert details.severity == "warning"
    # Grounded and valid: the registry answered, and an off-rate-card duration is
    # worth saying rather than worth refusing.
    assert details.grounded is True
    assert details.is_valid is True


async def test_provenance_names_the_snapshot_the_turn_was_grounded_against() -> None:
    details = build_validation_details(await _run(GB_BRIEF, PICK, session="ui4"))

    assert details.registry is not None
    # Contains rather than equals: the registry store is process-wide and every test
    # in this file shares `adv-1`, so whichever markets earlier tests planned against
    # are already loaded into this snapshot. That accumulation is the point of the
    # field - "which snapshot" is not an answer without "covering what".
    assert "GB" in details.registry.markets_loaded
    assert details.registry.source == "mock"
    assert details.registry.is_stale is False
    assert details.registry.is_complete is True
    assert details.registry.version >= 1
    assert details.registry.content_hash


async def test_provenance_leaks_no_operator_diagnostics() -> None:
    """The allowlist guard, against a real snapshot rather than a fixture. A field
    added to `RegistrySnapshotMeta` must not reach a trader by default."""
    state = await _run(GB_BRIEF, session="ui5")

    for leaked in ("degraded_sources", "rejected_items", "integrity_warnings", "diff"):
        assert leaked not in state["registry_provenance"]


async def test_nothing_is_grounded_until_a_market_is_named() -> None:
    """`validate_basics` is skipped without a market - the snapshot is market-scoped -
    so there is no snapshot to name, and the panel says so rather than implying one."""
    details = build_validation_details(await _run("I want to run a CTV campaign", session="ui6"))

    assert details.grounded is False
    assert details.registry is None
    assert details.checks == []
    assert details.awaiting


async def test_a_blocked_turn_is_grounded_and_invalid() -> None:
    """The distinction the whole feature rests on: the registry was consulted, and
    what it said was no. Not a grounding failure."""
    details = build_validation_details(
        await _run("CTV in the UK for August 2020, £50,000, 30 second creatives", session="ui7")
    )

    assert details.grounded is True
    assert details.is_valid is False
    assert details.blocks is True
    assert details.severity == "error"
    assert [c.code for c in details.checks if c.blocks] == ["flight_dates.in_past"]


# --- a market the platform does not sell -------------------------------------


async def test_an_unsold_market_is_refused_rather_than_crashing_the_turn() -> None:
    """The regression: "a CTV campaign in China" used to return an opaque 500.

    `validate_basics` has to build a validator - and therefore a snapshot for
    `markets[0]` - before `validate_target_markets` can reject the market. VOW's
    deal list answers for any market string, so the snapshot contradicted its own
    `valid_markets` and `gate` refused the lot, raising `RegistryValidationError`
    out of a sync whose reference data already knew CN was not sold.

    `markets` is seeded directly because that is what the LLM extractor produces
    from "China"; `_MARKET_PATTERNS` only knows the four markets VOW sells, so the
    deterministic path this suite runs on cannot reach the bug at all. That is why
    nothing caught it.
    """
    get_store().invalidate("china-co")
    graph = build_graph(checkpointer=MemorySaver(), mcp=MockMCPClient(advertiser_id="china-co"))

    state = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "CTV in China, September 2026, $20k, 10s"}],
            "advertiser_id": "china-co",
            "markets": ["CN"],
        },
        config={"configurable": {"thread_id": "china"}},
    )

    assert _codes(state) == ["market.unknown"]
    details = build_validation_details(state)
    # Grounded: the registry was consulted and answered. Just not with a yes.
    assert details.grounded is True
    assert details.blocks is True
    (refusal,) = [check for check in details.checks if check.blocks]
    assert refusal.suggested_options == ["DE", "FR", "GB", "US"]
    # And the trader is told, with the alternatives, rather than seeing an error.
    reply = "\n\n".join(_assistant_messages(state))
    assert "does not sell CTV inventory there" in reply


# --- a named provider narrows the plan ---------------------------------------
#
# Arrived with the agent-planning lane. The point is that a brief which already
# names a provider is a decision, not a hint: re-offering everything would make
# the agent a form the trader has to fill in twice.


PRIME_BRIEF = (
    "CTV campaign in the UK for August 2026, £50,000, 15 and 30 second creatives on Prime Video"
)


async def test_a_named_provider_is_honoured_rather_than_re_asked() -> None:
    """Only the chosen provider's deals, and the reply confirms rather than offers."""
    state = await _run(PRIME_BRIEF, session="provider-named")

    assert state["preferred_providers"] == ["Prime Video"]
    assert {deal["provider"] for deal in state["selected_deals"]} == {"Prime Video"}

    reply = "\n\n".join(_assistant_messages(state))
    assert "You've chosen Prime Video" in reply
    # The way out, in the same breath as the confirmation.
    assert "say if you'd like to change that" in reply.lower()


async def test_the_alternatives_are_recorded_so_a_ui_can_offer_the_way_out() -> None:
    """What this market carries that the trader did not name.

    Off the snapshot rather than a constant, so what a panel offers is inventory
    that exists - `presentation.inventory_block` renders this as the chips beside
    a confirmation.
    """
    state = await _run(PRIME_BRIEF, session="provider-alternatives")

    assert state["inventory_alternatives"] == ["Disney+", "Netflix"]


async def test_the_tier_follows_the_traders_choice_not_the_market() -> None:
    """The fork the whole flow branches on is decided by what they picked.

    GB carries Prime Video, so the market's dominant tier is AMAZON_OWNED and reach
    is forecastable. Choosing Netflix takes that away - and it must, because
    forecasting against inventory the plan does not hold is the fabricated number
    this codebase exists to refuse. Filtering after `dominant_tier` rather than
    before would have reported the market's tier and quietly restored the forecast.
    """
    netflix = (
        "CTV campaign in the UK for August 2026, £50,000, 15 and 30 second creatives on Netflix"
    )
    state = await _run(netflix, session="provider-tier")

    assert {deal["provider"] for deal in state["selected_deals"]} == {"Netflix"}
    assert state["inventory_tier"] == "THIRD_PARTY_PRECURATED"


async def test_a_provider_this_market_does_not_carry_is_named_precisely() -> None:
    """Naming the provider beats "no inventory found", which reads as a fault.

    Hulu is a provider VOW knows (`reference_data.yaml`) with no GB deal in the
    mock, which is the exact shape this branch exists for: the request was
    understood, and the answer is that this market does not sell it.
    """
    hulu = "CTV campaign in the UK for August 2026, £50,000, 15 and 30 second creatives on Hulu"
    state = await _run(hulu, session="provider-absent")

    assert state["selected_deals"] == []

    reply = "\n\n".join(_assistant_messages(state))
    assert "Hulu isn't available in GB" in reply
    assert "Disney+, Netflix, Prime Video are" in reply
    # Not the market-wide dead end, which would be false - GB sells plenty.
    assert "no CTV inventory at all" not in reply


async def test_an_unknown_provider_never_reaches_the_plan() -> None:
    """A name VOW does not carry is dropped rather than planned around.

    The pattern path cannot produce one, so this seeds it the way the LLM path
    would. Without the filter in `_merge`, "Peacock" would narrow the deal list to
    nothing and the trader would be told GB has no inventory.
    """
    mcp = MockMCPClient(advertiser_id="adv-1")
    graph = build_graph(checkpointer=MemorySaver(), mcp=mcp)

    state = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": GB_BRIEF}],
            "advertiser_id": "adv-1",
            "preferred_providers": ["Peacock"],
        },
        config={"configurable": {"thread_id": "provider-unknown"}},
    )

    assert state["preferred_providers"] == []
    assert len(state["selected_deals"]) == 4
