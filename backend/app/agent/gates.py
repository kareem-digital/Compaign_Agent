"""What each stage needs before the next one may run, and what to ask when it doesn't.

The planning flow is a sequence of gates, not a conveyor belt. If the basics are
incomplete, looking up inventory is premature; if a value the trader gave is not
one VOW sells, planning around it builds a plan that cannot exist; if no
inventory was found, suggesting audiences for it is meaningless.

So a stage records what it is `awaiting` or what failed validation, a router
sends the graph to `ask` instead of onward, the turn ends with **one** question,
the trader answers, and the next turn resumes from the top with the answer merged
in.

Two things here are load-bearing and easy to break:

**Completeness is per field, not truthiness.** `BASICS` entries name every state
key an answer needs, because a flight needs both ends and `{"lower": x}` is
truthy. `missing_basics` asks "is this answered?" rather than "is this set?".

**Validation is recomputed, never accumulated.** `record` replaces the entries a
stage owns rather than appending to them. The graph re-runs from
`extract_fields` every turn, so a stage's outcomes are always current: a
corrected value produces no entry and an uncorrected one re-blocks. That is what
makes "clear the resolved error" and "revalidate before continuing" need no code
of their own - and it is what stops the list growing without bound, which the
old append-per-turn version did.

**A stage does not say what it just said.** That same re-run means every stage
would otherwise restate its whole block on every turn, whatever the trader typed.
A complete brief priced in USD produced a byte-identical 1423-character reply four
turns running: the inventory list, the three audience options and the currency
warning, over and over, with no way forward. `say` compares the message a stage is
about to emit against the last one it emitted and stays quiet on a repeat.

One deliberate exception, and it is the load-bearing half: a stage that is
*asking* always speaks. Repeating an unanswered question is correct - which is why
`ask_for_missing` never suppresses, and why the inventory dead end and the
audience prompt pass `asking=True`. Without it those paths reach END having said
nothing, and `sessions.chat` turns a silent turn into an HTTP 500.

Requirements are described in the trader's language, not the schema's, because
these strings end up in the question the agent asks.
"""

from __future__ import annotations

import hashlib

from app.agent.state import PlanningAgentState
from app.knowledge.registry.models import ValidationResponse, duration_phrase

# The durations the platform sells, named in the question the trader reads.
# Generated rather than written out: this string was "10, 15, 20 or 30 seconds",
# which would have quietly become a lie the day CTV started selling a 6-second
# ad. The enum is the contract (schema v2 section 5), so it is the source.
_DURATIONS_LABEL = f"the creative durations - {duration_phrase()} seconds"

# Everything the flow's first stage must have before inventory lookup. This is
# "Basics" in the confirmed v5 flow.
#
# Each entry is (state keys, label). Several keys because one question can need
# more than one slot filled - "the start and end dates" is one thing to ask and
# two things to store, and an entry counts as answered only when all of its keys
# are present. Keys point at the raw "what the trader said" slots rather than the
# derived `flight_dates` / `market_budgets`, because those are empty until whole
# and would report an answered question as still missing.
#
# Order is the order questions are asked in, so it is the preferred collection
# order rather than an arbitrary list.
BASICS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("markets",), "which country the campaign runs in"),
    (("flight_start", "flight_end"), "the start and end dates"),
    (("durations",), _DURATIONS_LABEL),
    (("budget_amount",), "the budget"),
)

# Noun phrases, because `ask_for_missing._missing_template` wraps each entry as
# "Before I can carry on I need {x}. Could you tell me?" - NO_INVENTORY used to
# be a whole sentence, which produced "I need no CTV inventory matched - a
# different market or set of durations. Could you tell me?"
NO_INVENTORY = "a market or set of durations with inventory available"
NO_AUDIENCE = "an audience to plan against"
NO_TARGETING_DECISION = "a targeting decision (keep default or refine)"
# Distinct from NO_AUDIENCE, which means VOW suggested nothing. This one means the
# options are on screen and the trader has not picked yet - the flow's only
# genuine wait-for-the-human step, and the trigger for delivering the plan.
NO_AUDIENCE_CHOICE = "a choice between the three audience options"


def missing_basics(state: PlanningAgentState) -> list[str]:
    """Labels for whichever basics are still unanswered, in preferred order.

    Answered means every key the entry names is present, so a budget the trader
    gave before naming a market counts - it is held in `budget_amount` whether or
    not `market_budgets` could be keyed yet. Checking either raw or composite slots
    guarantees that an answered question is never reported as still missing.
    """
    missing: list[str] = []

    # 1. Markets
    if not (state.get("markets") or state.get("market")):
        missing.append("which country the campaign runs in")

    # 2. Flight dates (raw start/end or composite flight_dates)
    has_dates = bool(
        (state.get("flight_start") and state.get("flight_end"))
        or (
            state.get("flight_dates")
            and isinstance(state.get("flight_dates"), dict)
            and state.get("flight_dates", {}).get("lower")
            and state.get("flight_dates", {}).get("upper")
        )
    )
    if not has_dates:
        missing.append("the start and end dates")

    # 3. Durations
    if not state.get("durations"):
        missing.append(_DURATIONS_LABEL)

    # 4. Budget (raw amount or market_budgets)
    has_budget = bool(
        state.get("budget_amount")
        or (
            state.get("market_budgets")
            and isinstance(state.get("market_budgets"), list)
            and any(isinstance(b, dict) and b.get("budget") for b in state.get("market_budgets", []))
        )
    )
    if not has_budget:
        missing.append("the budget")

    return missing


# --- validation outcomes ------------------------------------------------------


def record(
    state: PlanningAgentState, stage: str, responses: list[ValidationResponse]
) -> list[dict]:
    """This stage's validation outcomes, replacing whatever it recorded before.

    Replace rather than append. The graph re-runs from the top every turn, so
    what a stage found last turn is not evidence about this one: appending would
    keep a corrected value's error forever and grow the list without bound. Same
    reasoning as `extract_fields._merge` overlaying rather than accumulating.

    Plain passes are dropped; anything worth saying is kept, blocking or not. A
    warning has to be kept because the stage that produced it is the only thing
    that will ever say it - no question carries it.

    Dropped here, and not lost: `record_checks` keeps the same outcomes with the
    passes in, for the UI. Only `stage_notes` needs them gone - it would speak
    "Targeting GB." and "Billing in GBP." on every turn. `blocking`,
    `deliver_plan._summary` and `validate_plan_ready_for_approval` all filter on
    `is_valid` or on `severity == "warning"`, so a pass is already invisible to
    them.
    """
    kept = [
        entry for entry in (state.get("validation_errors") or []) if entry.get("stage") != stage
    ]
    fresh = [
        {**response.model_dump(mode="json"), "stage": stage}
        for response in responses
        # `_ok()` leaves `severity` at its default of "error", so a pass is
        # is_valid *and* severity error. Anything else is worth carrying.
        if not (response.is_valid and response.severity == "error")
    ]
    return kept + fresh


def record_checks(
    state: PlanningAgentState, stage: str, responses: list[ValidationResponse]
) -> list[dict]:
    """Everything this stage checked, passes included, replacing its last answer.

    The sibling of `record`, and the difference between them is the whole reason it
    exists. A pass is the one thing `validation_errors` cannot hold and the one
    thing a UI most needs: `validate_basics._checks` skips a rule whose input the
    trader has not given, so without the passes a panel cannot tell "the GB rate
    card carries 30s" from "no duration was given, so nothing was checked". On a
    clean complete brief `record` keeps zero of five outcomes - the UI's whole view
    of a turn that went right is an empty list.

    Same serialization and the same replace-per-stage rule as `record`, for the
    same reasons. So `validation_errors` is always a subset of this list, which
    `tests/unit/agent/test_gates.py` pins - the one way a sibling function drifts.

    Not a gate. It records what happened; nothing routes on it.
    """
    kept = [
        entry for entry in (state.get("validation_checks") or []) if entry.get("stage") != stage
    ]
    return kept + [{**response.model_dump(mode="json"), "stage": stage} for response in responses]


def blocking(state: PlanningAgentState) -> list[dict]:
    """Recorded outcomes that must stop the flow.

    The dict form of `ValidationResponse.blocks`, kept in step with it by
    `tests/unit/agent/test_gates.py`.
    """
    return [
        entry
        for entry in (state.get("validation_errors") or [])
        if not entry.get("is_valid") and entry.get("severity") == "error"
    ]


def notes(entries: list[dict]) -> str:
    """Prose for non-blocking outcomes, for the stage that found them to say.

    Warnings never reach `ask` - the flow carries on past them - so a stage that
    does not speak its own warnings swallows them, which is the whole failure
    this exists to prevent.
    """
    return "\n".join(entry["message"] for entry in entries if entry.get("message"))


def stage_notes(stage: str, errors: list[dict]) -> str:
    """The speakable part of what `stage` just recorded."""
    return notes(
        [
            entry
            for entry in errors
            if entry.get("stage") == stage
            and not (not entry.get("is_valid") and entry.get("severity") == "error")
        ]
    )


# --- speaking -----------------------------------------------------------------


def digest(message: str) -> str:
    """A short stable fingerprint of a string.

    Public because the audit records use it for the same purpose `say` does -
    deciding whether something has already been reported - and two hashing
    helpers that must agree is one too many.
    """
    return hashlib.sha256(message.encode()).hexdigest()[:16]


def say(
    state: PlanningAgentState,
    stage: str,
    message: str,
    *,
    asking: bool = False,
    repeat_with: str | None = None,
) -> dict:
    """A state fragment carrying `message`, or `{}` when it would only repeat.

    The whole graph re-runs every turn, so a stage that speaks unconditionally
    restates its block whatever the trader typed. Comparing against what this
    stage last said - rather than against its inputs - means the rule is about
    what the trader actually reads, and a stage added later gets it for free.

    Three outcomes, not two:

      * new message            -> say it
      * repeat, not asking     -> say nothing
      * repeat, still asking   -> say `repeat_with`, or the message again if the
                                  caller gave no short form

    That third case is the whole reason `repeat_with` exists. A stage whose
    message *is* the turn's question cannot fall silent - the turn would end
    saying nothing, and `sessions.chat` returns HTTP 500 for that. But restating
    twenty lines of audience options because the trader replied about something
    else is the wall of repeated text this is meant to end. So the question stays
    live in one line instead.

    A digest rather than the text, so the checkpointer is not storing the
    transcript a second time. Saying nothing is recorded too, as the empty digest -
    a stage that fell silent and then has something to say again must not have that
    swallowed as a repeat of what it said two turns ago. The currency note
    disappearing when the market moved to the US and never coming back on the way
    to GB was exactly that.
    """
    said = state.get("last_said") or {}
    fingerprint = digest(message) if message else ""

    if not message:
        return {"last_said": {**said, stage: ""}}

    repeated = said.get(stage) == fingerprint
    if repeated and not asking:
        return {"last_said": {**said, stage: fingerprint}}
    if repeated:
        message = repeat_with or message

    return {
        "messages": [{"role": "assistant", "content": message}],
        "last_said": {**said, stage: fingerprint},
    }


# --- what to ask --------------------------------------------------------------


def next_question(state: PlanningAgentState) -> dict | None:
    """The single item this turn asks about, or None when nothing is outstanding.

    One at a time, in preferred order, and never something already answered -
    `awaiting` and `blocking` are both derived from current state, so an answer
    given out of order simply removes an item rather than being asked for again.

    Conflicts before gaps. An invalid value is already in state and will keep
    blocking whatever else is collected, and later fields are validated against
    it - durations are checked against the chosen market's rate card - so
    gathering more detail first gathers it for a plan that cannot exist.

    `awaiting` still holds the whole list in state; only the *question* narrows.
    That keeps `GET /sessions/{id}`, the `awaiting_count` log field and
    `route_after_inventory`'s exact-match on `[NO_INVENTORY]` working.
    """
    conflicts = blocking(state)
    if conflicts:
        return {"kind": "conflict", "entry": conflicts[0]}

    awaiting = state.get("awaiting") or []
    return {"kind": "missing", "label": awaiting[0]} if awaiting else None


# --- routers ---------------------------------------------------------------
#
# LangGraph routers may read state but not write it, so the nodes set `awaiting`
# and record validation outcomes, and these only decide where to go next.


def route_planner(state: PlanningAgentState) -> str:
    """Orchestrator dispatch router based on Planner Agent evaluation."""
    from app.agent.nodes.planner import evaluate_state_and_plan

    decision = evaluate_state_and_plan(state)
    return decision["next_agent"]



def route_after_basics(state: PlanningAgentState) -> str:
    """Validate as soon as there is a market to validate against, gaps or not.

    Not gated on the basics being complete. Waiting would mean a value could only
    be checked once every *other* field had arrived - a bad flight date given on
    turn two going unmentioned until turn five - and `validate_basics` skips the
    rules whose inputs are still absent, so there is nothing to gain by waiting.

    Without a market nothing can be grounded at all, because the snapshot is
    market-scoped; that turn goes straight to the question.
    """
    return "validate_basics" if state.get("markets") else "ask"


def route_after_validation(state: PlanningAgentState) -> str:
    """Onward only when everything given grounds and nothing is still missing.

    Warnings do not stop anything: `validate_basics` has already spoken them and
    the plan is still worth building. A blocker does, because planning past a
    value VOW does not sell produces a plan that cannot be activated - which the
    trader would otherwise discover at approval.

    `awaiting` is checked here rather than earlier so that a turn holding both an
    unsupported value and a gap raises the value first - see `next_question`.
    """
    return "ask" if blocking(state) or state.get("awaiting") else "select_inventory"


def route_after_inventory(state: PlanningAgentState) -> str:
    """Onward to targeting, or stop - but do not ask twice.

    The inventory stage explains its own dead end and asks its own question, so
    routing to `ask` would append a second, vaguer one immediately underneath.
    Two questions in a turn is worse than one: the trader has to work out which
    to answer. So that path ends the turn instead.
    """
    awaiting = state.get("awaiting") or []
    conflicts = blocking(state)

    if not awaiting and not conflicts:
        return "collect_targeting"
    if awaiting == [NO_INVENTORY] and not conflicts:
        return "end"
    return "ask"


def route_after_targeting(state: PlanningAgentState) -> str:
    """Onward to audiences once targeting is settled."""
    awaiting = state.get("awaiting") or []
    conflicts = blocking(state)

    if not awaiting and not conflicts:
        return "suggest_audiences"
    if awaiting == [NO_TARGETING_DECISION] and not conflicts:
        return "end"
    return "ask"


def route_after_audiences(state: PlanningAgentState) -> str:
    """Forecast once an audience is chosen; otherwise wait for the choice.

    Waiting ends the turn rather than routing to `ask`, because the node has just
    listed the three options and closed with "pick one and I will forecast against
    it". That *is* the question, and `ask` could only append a vaguer duplicate -
    the same reasoning as the inventory dead end in `route_after_inventory`.
    """
    awaiting = state.get("awaiting") or []
    conflicts = blocking(state)

    if not awaiting and not conflicts:
        return "predict_reach"
    if awaiting == [NO_AUDIENCE_CHOICE] and not conflicts:
        return "end"
    return "ask"
