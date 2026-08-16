"""Node 3 - always offer three audience options: narrow, balanced, wide.

Audiences are mandatory and suggestion-driven. Nobody browses VOW's ~3,400
segments by hand, so the agent asks the server to suggest and then presents
exactly three shapes.

The number that matters is the **effective CPM** - deal CPM plus the audience
VCPM fee. A narrow audience is both smaller and dearer per impression, so
showing the deal price alone understates what precision costs. Surfacing the
combined figure per option is the whole point of this node.

That arithmetic lives in the registry, not here. It is the figure a trader
commits budget against, so it has one implementation, in `Decimal` rather than
float - `18.22 + 3.50` in binary float is not `21.72`. This node asks for the
priced options and decides how to say them.

Amazon audiences apply only to Amazon-owned inventory; for third-party the
provider's own targeting applies and adds its own CPM. That is stated rather
than silently ignored - and an unpriced option comes back as `None`, never
zero, because a zero would read as free.

**The trader picks; this node does not.** It used to set `chosen_audience` to
BALANCED itself, which made "pick one and I will forecast against it" a promise
nothing could keep: naming a profile changed nothing, and the plan ran through to
a forecast against an audience nobody had agreed to. Now the choice is a real
input - `extract_fields` reads it into `audience_choice` and this node prices it -
and its absence is the flow's one genuine wait-for-the-human step.

BALANCED is still the recommendation, but it is recommended in the prose rather
than assumed in the state. A default nobody was asked about is not a choice.
"""

from __future__ import annotations

from app.agent.gates import (
    NO_AUDIENCE,
    NO_AUDIENCE_CHOICE,
    record,
    record_checks,
    say,
    stage_notes,
)
from app.agent.nodes.select_inventory import AMAZON_OWNED
from app.agent.state import PlanningAgentState
from app.knowledge.registry import AdvertiserRegistry, ValidationResponse

STAGE = "audiences"

_PROFILE_ORDER = ("NARROW", "BALANCED", "WIDE")

_PROFILE_NOTE = {
    "NARROW": "highest intent, smallest pool, highest fee - underdelivery risk",
    "BALANCED": "the usual recommendation",
    "WIDE": "widest reach, lowest fee, least precision",
}

# Said instead of the full options block when the choice is still outstanding and
# the trader's last message was about something else. The options are still on
# screen a message or two up; restating them is what made this conversation loop.
_RE_ASK = "Still need an audience before I can forecast - Narrow, Balanced or Wide?"


def _summary(options: list[dict], has_amazon: bool, has_third_party: bool) -> str:
    lines = [
        "Three audience options - tell me which to use and I will forecast against it. "
        "Balanced is the usual recommendation.",
        "",
    ]

    for option in options:
        effective = option.get("effective_cpm")
        price = (
            f"{option['cpm_basis']} + {option['vcpm_fee']} fee = {effective} effective CPM"
            if effective
            else f"{option['vcpm_fee']} fee (no Amazon inventory to price against)"
        )
        lines += [
            f"**{option['profile'].title()}** - {option['name']}",
            f"  {option['segment_count']} segments, ~{option['estimated_size']:,} people",
            f"  {price}",
            f"  {_PROFILE_NOTE[option['profile']]}",
            "",
        ]

    if has_third_party:
        note = (
            "Amazon audiences apply to the Prime Video portion only. "
            "Netflix and Disney+ use their own targeting, which adds their own CPM."
        )
        lines.append(
            note
            if has_amazon
            else "Note: this plan has no Amazon inventory, so Amazon audiences do not "
            "apply at all - the providers' own targeting governs."
        )

    return "\n".join(lines).rstrip()


def make_suggest_audiences(registry: AdvertiserRegistry):
    """Build the node with its registry bound."""

    async def suggest_audiences(state: PlanningAgentState) -> dict:
        deals = state.get("selected_deals") or []
        markets = state.get("markets") or []
        market = markets[0] if markets else None

        # The registry prices all three profiles against the selected inventory,
        # in Decimal, and returns strings. That is the same calculation this node
        # used to do in float - moved rather than copied, because effective CPM
        # is the number a trader commits budget against and it should have one
        # implementation. See `registry.calculate_effective_cpm`.
        validator = await registry.validator(market)
        options = (
            validator.effective_cpm_options(market, [d["deal_id"] for d in deals]) if market else []
        )

        found = {option["profile"] for option in options}
        missing = [p for p in _PROFILE_ORDER if p not in found]

        # Three options are mandatory; fewer is a server-contract problem, so this
        # points at VOW rather than at the plan. Recorded as a *warning* rather
        # than a blocker on purpose: blocking would stop the turn and ask the
        # trader to fix something only VOW can. So it is said, and the flow goes on
        # with whatever profiles did arrive.
        checks = []
        if missing:
            checks.append(
                ValidationResponse(
                    is_valid=True,
                    severity="warning",
                    code="audience.incomplete_profiles",
                    field="audience_options",
                    message=(
                        f"VOW suggested no {', '.join(p.lower() for p in missing)} audience for "
                        f"this brief, so I can only price the ones it returned."
                    ),
                    metadata={"missing": missing, "returned": sorted(found)},
                )
            )
        # The trader's pick, grounded against what VOW actually returned. An
        # unrecognised profile becomes a blocker carrying the three real options,
        # so `ask` phrases it with no audience-specific code - see
        # `validate_audience_choice`.
        choice = state.get("audience_choice")
        chosen = next((o for o in options if o["profile"] == choice), None) if choice else None

        if choice and options:
            # Grounded whether or not it matched, which the earlier version skipped.
            # A match returns `audience.ok`, which `record` drops - so the
            # conversation is byte-identical - while `record_checks` keeps it, and
            # the panel can show the pick was checked against what VOW returned
            # rather than leaving an agreed audience with no evidence behind it.
            checks.append(validator.validate_audience_choice(choice))

        errors = record(state, STAGE, checks)

        tiers = {deal.get("inventory_tier") for deal in deals}
        summary = _summary(
            options,
            has_amazon=AMAZON_OWNED in tiers,
            has_third_party=bool(tiers - {AMAZON_OWNED}),
        )
        spoken = stage_notes(STAGE, errors)
        message = f"{summary}\n\n{spoken}" if spoken else summary

        if not options:
            awaiting = [NO_AUDIENCE]
        elif chosen is None:
            awaiting = [NO_AUDIENCE_CHOICE]
        else:
            awaiting = []

        return {
            "current_stage": STAGE,
            "stage_cursor": "audiences",
            "audience_options": options,
            "awaiting": awaiting,
            "chosen_audience": chosen,
            "validation_errors": errors,
            # The UI's only source, so a stage that skipped it would have its
            # warnings spoken in the conversation and missing from the panel.
            "validation_checks": record_checks(state, STAGE, checks),
            # `asking` while the choice is outstanding: the summary above ends by
            # asking for it and the router sends that straight to END, so falling
            # silent would end the turn saying nothing. But a trader who replied
            # about something else should not get twenty lines of options again,
            # so the second time it is one line. Once a choice is in, the block is
            # suppressed outright - it is the text that was repeating every turn.
            **say(state, STAGE, message, asking=chosen is None, repeat_with=_RE_ASK),
        }

    return suggest_audiences
