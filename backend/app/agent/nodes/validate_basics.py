"""Node 1b - ground everything the trader said before planning against it.

`extract_fields` understands a brief; this decides whether what it understood is
something VOW actually sells. Split into its own node rather than folded into the
extractor for two reasons: grounding needs the registry and a market, neither of
which exists while a brief is still being parsed, and a stage that can stop the
flow deserves its own log line.

**Everything it needs already exists.** `StepwiseCTVValidator` has a method per
step-1 field, each returning a `ValidationResponse` carrying the reason *and* the
alternatives, sourced from the snapshot. Most had no caller. Adding a rule to the
flow is now one line in `_checks` - no routing, rendering or prompt change - which
is what "works for any future validation rule" has to mean to be true.

**Blocks on error, speaks on warning.** A value VOW does not sell stops the turn
and gets asked about, because planning on past it builds a plan that cannot be
activated and the trader would only find out at approval. A warning - "I read UK
as GB", "15s is not on the GB rate card" - is said and the flow carries on,
because the plan is still worth building and stopping to confirm a courtesy would
be its own kind of wizard.

Silent when everything grounds. Safe, because a later stage always speaks, and a
turn that diverts to `ask` is answered there.
"""

from __future__ import annotations

import logging

from app.agent.gates import blocking, digest, record, record_checks, say, stage_notes
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge.registry import AdvertiserRegistry, StepwiseCTVValidator

logger = logging.getLogger(__name__)

STAGE = "validation"


def _checks(validator: StepwiseCTVValidator, state: PlanningAgentState, market: str) -> list:
    """Every step-1 rule whose input the trader has actually given, in ask order.

    Order is the conflict priority: `gates.next_question` asks about the first
    blocker, so this mirrors `gates.BASICS` - market before dates before
    durations - and a trader is never asked to fix a currency on a plan whose
    market is not sold.

    A rule is skipped while its input is absent, rather than run and allowed to
    report `*.missing`. Two reasons. Absence is the `awaiting` gate's business and
    it already phrases the question; and running anyway would mean a value could
    not be checked until every *other* field had arrived, so a trader could give a
    bad date on turn two and only hear about it on turn five - which is the delay
    this whole node exists to remove.
    """
    markets = list(state.get("markets") or [])
    durations = list(state.get("durations") or [])

    checks = [validator.validate_target_markets(markets)]

    if state.get("flight_dates"):
        checks.append(validator.validate_flight_dates(state["flight_dates"]))
    if durations:
        checks.append(validator.validate_durations(durations, market))
    if state.get("primary_currency"):
        checks.append(validator.validate_currency(state["primary_currency"], markets))
    if state.get("goal") and state.get("kpi"):
        checks.append(validator.validate_goal_and_kpi(state["goal"], state["kpi"]))

    return checks


def make_validate_basics(registry: AdvertiserRegistry):
    """Build the node with its registry bound."""

    async def validate_basics(state: PlanningAgentState) -> dict:
        markets = state.get("markets") or []
        if not markets:
            # Nothing can be grounded without a market to ground it against - the
            # snapshot is market-scoped. `route_after_basics` sends the turn
            # straight to `ask` in that case, so this is defensive only.
            return {"current_stage": STAGE}

        audited = dict(state.get("audited") or {})
        source = state.get("extraction_method") or "unknown"

        # What is about to be checked, and what is still outstanding. `missing`
        # rather than a list of what was supplied: "what does the agent still
        # need" is the question worth answering at a glance, and the supplied list
        # only grows. `awaiting` already holds it - `extract_fields` computed it
        # from `missing_basics` earlier this turn.
        #
        # Field names and the market, never the amounts: a budget is the client's
        # commercial data, and proving the check happened does not require quoting
        # the figure it ran against.
        missing = list(state.get("awaiting") or [])
        input_fingerprint = digest(f"{markets}|{sorted(state.get('durations') or [])}|{missing}")
        if audited.get("input") != input_fingerprint:
            logger.info(
                "audit.input_received",
                extra=kv(
                    market=markets[0],
                    markets_requested=markets,
                    durations=list(state.get("durations") or []),
                    missing=missing,
                    source=source,
                ),
            )
            audited["input"] = input_fingerprint

        validator = await registry.validator(markets[0])

        # Which snapshot answered, and what it says it sells. This is the record
        # that makes the trail auditable rather than merely narrated: a verdict
        # without the version and hash of the data behind it cannot be checked
        # after the fact. `provenance()` is reused rather than reaching into
        # `meta` directly - it is the same enumerated view the UI receives.
        #
        # Stated in full the first time a given snapshot answers, and compactly
        # after that. The proof of consultation stays on every turn - that is the
        # point of the trail - but `supported_markets`, the hash and the loaded
        # market list do not change while the snapshot does not, and they were
        # byte-identical on all nine turns of the sample log.
        #
        # Keyed on `content_hash`, which moves when a market is lazily added, so
        # the full record re-fires exactly when the grounding data actually
        # changed rather than on a timer.
        provenance = validator.snapshot.provenance()
        lookup = {
            "market": markets[0],
            "valid": markets[0] in validator.data.valid_markets,
            "snapshot_version": provenance["version"],
        }
        if audited.get("snapshot") != provenance["content_hash"]:
            lookup |= {
                "supported_markets": sorted(validator.data.valid_markets),
                "snapshot_hash": provenance["content_hash"],
                "markets_loaded": provenance["markets_loaded"],
                "is_stale": provenance["is_stale"],
            }
            audited["snapshot"] = provenance["content_hash"]
        logger.info("audit.registry_lookup", extra=kv(**lookup))

        checks = _checks(validator, state, markets[0])
        errors = record(state, STAGE, checks)

        mine = [entry for entry in errors if entry.get("stage") == STAGE]
        blockers = blocking({"validation_errors": mine})
        spoken = stage_notes(STAGE, errors)

        # The verdict fires every turn - it is the decision, and a turn with no
        # decision record is indistinguishable from a turn that never ran. What
        # does not repeat is the outcome *list*: the same warning re-listed on
        # every turn the trader repeats themselves is the fatigue that buries the
        # turn where something actually changed. So the codes are reported as
        # deltas against the last verdict.
        current: set[str] = {str(code) for entry in mine if (code := entry.get("code"))}
        previous: set[str] = {str(code) for code in audited.get("codes") or []}
        # Set to the current codes, never unioned with the previous ones. A
        # warning that appears, is fixed, and comes back must be reported twice -
        # `gates.say`'s docstring records the same trap for prose, where a note
        # that fell silent got swallowed as a repeat of what it said two turns ago.
        audited["codes"] = sorted(current)

        # `object` rather than the inferred `int | str`: the delta keys below hold
        # lists of codes, and a narrower value type makes those assignments an error.
        verdict: dict[str, object] = {
            "verdict": "FAILED" if blockers else "PASSED",
            # Where the checked values came from. Not "the LLM's output": with no
            # API key, or after a fallback, extraction is pure regex and no model
            # ran at all. See `extract_fields`.
            "source": source,
            "market": markets[0],
            "blocking": len(blockers),
            "warnings": len(mine) - len(blockers),
        }
        # Present only when there is something to say. An empty pair on every
        # quiet turn is the same noise this change set out to remove, and it makes
        # the turn where a warning did appear harder to pick out.
        if appeared := sorted(current - previous):
            verdict["new_warnings"] = appeared
        if gone := sorted(previous - current):
            verdict["resolved"] = gone
        logger.info("stage.validation", extra=kv(**verdict))

        return {
            "current_stage": STAGE,
            # Carries `extract_fields`' keys through as well - `audited` was read
            # as a copy at the top of this node, so the spread already happened.
            "audited": audited,
            "validation_errors": errors,
            # The same outcomes with the passes kept, for the UI. Two calls over one
            # list rather than one call returning both, so `record`'s signature -
            # and everything pinned to it - does not move.
            "validation_checks": record_checks(state, STAGE, checks),
            # Which snapshot the answers above were checked against. Free: the
            # validator is already holding it, so there is no extra sync.
            #
            # Written here and in no other node on purpose. Every snapshot-holding
            # node this turn reads `markets[0]`, and this node is the one that loads
            # it - `select_inventory` and `suggest_audiences` then get the identical
            # object back out of the store, lazy market extension and version bump
            # included. A second writer would add a state write and no information.
            "registry_provenance": validator.snapshot.provenance(),
            # Warnings only. A blocker is not said here - `ask` says it, with the
            # alternatives, as this turn's single question.
            #
            # Through `say`, so a note is made once and not on every later turn.
            # "Using USD for a GB campaign" was repeating forever, including after
            # the trader twice confirmed it was deliberate: the note is recomputed
            # each turn, so it needed suppressing at the point of speech rather
            # than an acknowledgement flag. Change the market and it correctly
            # returns, because the sentence changes.
            **say(state, STAGE, spoken),
        }

    return validate_basics
