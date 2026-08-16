"""What the backend checked, in the shape a UI renders.

`sessions.chat` reads the whole merged graph state and returns three fields of it.
Everything the registry established on the way - which rules ran, which values VOW
does not sell, what it sells instead, and which snapshot said so - is sitting in
that state and is dropped at the HTTP boundary. A frontend that cannot see it has
to re-derive it from prose, which means reimplementing the registry's rules in
TypeScript against a message the backend is free to reword.

There is no other DTO layer in this service and this is not the start of one. It is
four models and one function, and it is deliberately thin:

**It reads; it never re-validates.** Every field below is already in state, put
there by the stage that computed it. Asking a validator again here would put a
second question to the registry in the same turn, and it could answer differently
from what the trader was just told.

**The vocabulary is `ValidationResponse`'s.** `is_valid`, `severity`, `code`,
`field`, `message`, `suggested_options`, `metadata`, `blocks` mean exactly what they
mean on one outcome; the rollup aggregates them and invents no third word for
"failed". `test_validation_details.py` pins the field set against the model, so the
day a field is added there this fails rather than silently omitting it.

**Nothing new is exposed.** `checks` is `state["validation_checks"]`, which holds
serialized `ValidationResponse`s and nothing else. `registry` is the subset
`GroundedRegistrySnapshot.provenance` allows, which excludes MCP tool names,
ingest-time exception text and VOW's own data-quality commentary. Deals, prices,
audiences and the forecast are the *plan*, not the validation of it, and are not
here.

Two things to know before building on this:

  * **Grounded is not valid.** `grounded` says the registry was consulted;
    `is_valid` says what it answered. `grounded: true, blocks: true` is the normal
    shape of "the registry was asked, and it does not sell that" - the most
    informative answer this feature has, and the one a single boolean would lose.
  * **A check is current, not necessarily fresh.** `gates.record` replaces only the
    entries the running stage owns, so a stage that did not run this turn keeps what
    it recorded last turn - which is exactly why an audience blocker still blocks a
    turn that never reached the audience stage. `checked_this_turn` says which is
    which, so a panel can show a carried-over warning as carried over instead of
    attributing it to this answer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agent.gates import blocking
from app.agent.state import PlanningAgentState

# Stage names in the order the graph runs them, which is the order `current_stage`
# advances through. Every conditional edge in `graph.py` only ever moves forward, so
# a stage at or before `current_stage` ran this turn and one after it did not - which
# is how `checked_this_turn` is derived without another state key to keep in step.
# `ask` is absent on purpose: it writes no `current_stage`, so a turn that diverts to
# it correctly reports whichever stage last spoke.
#
# These are the `STAGE` constants from `app/agent/nodes/`, restated rather than
# imported so `app.api` does not reach into the graph's internals for a tuple of
# strings. `test_validation_details.py` asserts the two agree.
_STAGE_ORDER: tuple[str, ...] = (
    "basics",
    "validation",
    "inventory",
    "audiences",
    "forecast",
    "delivered",
)


def _is_pass(entry: dict) -> bool:
    """A plain pass: the rule ran and the registry had nothing to say.

    `gates.record`'s own predicate, because there must be one definition of it.
    `_ok()` leaves `severity` at the model's default of `"error"`, so a pass is
    `is_valid` *and* severity error - which is why reading `severity` alone across
    every entry would report a clean turn as a failure.
    """
    return bool(entry.get("is_valid")) and entry.get("severity") == "error"


class ValidationCheck(BaseModel):
    """One recorded outcome: the registry's own answer, plus where it came from.

    The seven `ValidationResponse` fields, `stage` as `gates.record` stamps it, and
    three things derived here so no client re-derives them.
    """

    is_valid: bool
    message: str
    code: str = ""
    severity: Literal["error", "warning"] | None = Field(
        None,
        description="Null on a pass. It is 'error' in state only because `_ok()` "
        "leaves the default, and on the wire that reads as a contradiction.",
    )
    field: str | None = Field(
        None,
        description="Absent on several passes (currency.ok, goal_kpi.ok, "
        "flight_dates.ok). Group by `code`, not by this.",
    )
    suggested_options: list[str] = Field(
        default_factory=list, description="What the registry does allow. Its own values."
    )
    metadata: dict = Field(
        default_factory=dict, description="Registry-derived evidence for this outcome."
    )
    stage: str = Field(..., description="The stage that recorded it, e.g. 'validation'.")
    blocks: bool = Field(
        ..., description="Whether this stopped the flow. `ValidationResponse.blocks`."
    )
    checked_this_turn: bool = Field(
        ..., description="False when carried over from an earlier turn."
    )

    @classmethod
    def from_entry(cls, entry: dict, *, current_stage: str | None) -> ValidationCheck:
        """One entry of `state["validation_checks"]`, as the wire carries it."""
        stage = str(entry.get("stage") or "")
        return cls(
            is_valid=bool(entry.get("is_valid")),
            message=str(entry.get("message") or ""),
            code=str(entry.get("code") or ""),
            # Nulled *after* `blocks` is taken, which is the whole reason this is a
            # classmethod rather than a validator: `blocks` is defined in terms of
            # the severity the validator actually set.
            severity=None if _is_pass(entry) else entry.get("severity"),
            field=entry.get("field"),
            suggested_options=list(entry.get("suggested_options") or []),
            metadata=dict(entry.get("metadata") or {}),
            stage=stage,
            blocks=not entry.get("is_valid") and entry.get("severity") == "error",
            checked_this_turn=_ran_this_turn(stage, current_stage),
        )


class RegistryProvenance(BaseModel):
    """Which grounded snapshot this turn's answers were checked against.

    The subset of `RegistrySnapshotMeta` a trader may see.
    `GroundedRegistrySnapshot.provenance` decides what that subset is and says why.

    Scoped to the registry-grounded checks. The forecast does not come from here -
    `predict_reach` calls VOW live, because a cached reach number is a stale one.
    """

    schema_version: str
    version: int
    content_hash: str
    synced_at: str
    source: Literal["mock", "live"]
    markets_loaded: list[str]
    is_complete: bool = Field(
        ..., description="False when an optional source degraded: usable, not the whole picture."
    )
    is_stale: bool = Field(
        ..., description="True when a refresh failed and this is the last good one."
    )


class FieldChange(BaseModel):
    """A value the agent changed, and what it was before.

    Today the only source is `metadata["renamed"]` on `market.normalized` - "I read
    UK as GB" - and even that is rare, because `extract_fields` already emits ISO
    codes. It is here because it is the honest projection of the one before/after
    pair the validators produce, and because the forecast repair loop
    (`graph.py` "Repair loop", detected at `predict_reach.py` and not yet wired to an
    edge) lands in the same shape: the panel does not change when it does.
    """

    field: str
    code: str
    before: str
    after: str


class ValidationDetails(BaseModel):
    """Everything the backend established about the values the trader gave."""

    grounded: bool = Field(
        ...,
        description="The registry was consulted. Independent of whether it approved: "
        "a rejected market is grounded and invalid.",
    )
    is_valid: bool = Field(..., description="Nothing recorded failed, at any severity.")
    blocks: bool = Field(..., description="Something recorded stopped the flow.")
    severity: Literal["error", "warning"] | None = Field(
        None, description="Worst severity present, passes excluded. Null when clean."
    )
    checks: list[ValidationCheck] = Field(default_factory=list)
    awaiting: list[str] = Field(
        default_factory=list,
        description="What the agent is waiting for, in the trader's own words.",
    )
    changes: list[FieldChange] = Field(default_factory=list)
    registry: RegistryProvenance | None = Field(
        None, description="Null until a market is named - the snapshot is market-scoped."
    )


def _ran_this_turn(stage: str, current_stage: str | None) -> bool:
    """Whether `stage` ran on the turn that ended at `current_stage`."""
    if not current_stage or stage not in _STAGE_ORDER or current_stage not in _STAGE_ORDER:
        return False
    return _STAGE_ORDER.index(stage) <= _STAGE_ORDER.index(current_stage)


def _changes(checks: list[ValidationCheck]) -> list[FieldChange]:
    """Before/after pairs, read off the metadata the validators already set."""
    return [
        FieldChange(field=check.field or "", code=check.code, before=str(was), after=str(now))
        for check in checks
        for was, now in (check.metadata.get("renamed") or {}).items()
    ]


def build_validation_details(state: PlanningAgentState) -> ValidationDetails:
    """Read the recorded outcomes off the state. No re-validation, no MCP call."""
    current_stage = state.get("current_stage")
    checks = [
        ValidationCheck.from_entry(entry, current_stage=current_stage)
        for entry in (state.get("validation_checks") or [])
    ]

    # `gates.blocking` rather than `any(c.blocks)`, so this reports the same answer
    # the routers acted on - they read `validation_errors`. A panel saying "blocked"
    # about a turn that ran on, or the reverse, is worse than saying nothing.
    # `validation_errors` is a subset of `validation_checks`, so the two agree;
    # `tests/unit/agent/test_gates.py` pins that.
    blockers = blocking(state)

    # Only what is worth flagging counts: a failure of any strength, or an explicit
    # warning. A pass is excluded because its `severity` is a default, not a verdict.
    notable = [check for check in checks if not check.is_valid or check.severity == "warning"]
    provenance = state.get("registry_provenance")

    return ValidationDetails(
        grounded=provenance is not None,
        is_valid=all(check.is_valid for check in checks),
        blocks=bool(blockers),
        severity=(
            "error"
            if any(check.severity == "error" for check in notable)
            else ("warning" if notable else None)
        ),
        checks=checks,
        awaiting=list(state.get("awaiting") or []),
        changes=_changes(checks),
        registry=RegistryProvenance(**provenance) if provenance else None,
    )
