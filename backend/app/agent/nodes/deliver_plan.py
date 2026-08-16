"""Node 5 - the plan, in one piece, and the end of the collecting conversation.

Everything before this speaks as it works: what was understood, what inventory
exists, what the audiences cost, what the forecast says. Useful while the plan is
being assembled, and no use at all as a record - the trader ends up scrolling four
turns of prose to answer "so what did we agree?".

So this node says it once, consolidated, and marks the flow's arrival at a state
rather than a stage: `current_stage` becomes `delivered`, which is the signal the
UI needs and the thing `GET /sessions/{id}` reports.

**It presents; it does not commit.** Nothing here mutates anything in VOW or locks
spend - the first node that can is `create_strategy`, after plan approval, which is
not built. So there is deliberately no `interrupt()` here: an approval gate in
front of an action that does not exist would be theatre.

Outstanding notes are repeated in the summary even though they were said when they
were found. A consolidated plan that quietly omits "10-second is not on the GB rate
card" is precisely the artefact that gets approved by someone who missed it four
turns ago.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.agent.gates import say
from app.agent.state import PlanningAgentState
from app.knowledge.registry.models import TIER_LABELS, InventoryTierEnum

STAGE = "delivered"

# Said instead of the summary when the summary would be word-for-word what it
# already was. Short on purpose: the plan is above, and restating it because
# someone typed "thanks" is the loop this whole change removes.
STANDING_BY = (
    "The plan above is ready. Tell me what to change - market, dates, durations, budget "
    "or audience - and I will re-plan against it."
)


def _money(amount: str | None) -> str | None:
    """A budget as prose: grouped, no trailing pennies.

    `Decimal` rather than float even for display - the state carries strings so
    that money never goes near binary floating point, and quietly reintroducing it
    for a f-string is how that discipline erodes.
    """
    if not amount:
        return None
    try:
        return f"{Decimal(str(amount)):,.0f}"
    except InvalidOperation:
        return str(amount)


def _tier_label(tier: str | None) -> str:
    if not tier:
        return "not determined"
    try:
        return TIER_LABELS[InventoryTierEnum(tier)]
    except (KeyError, ValueError):
        return tier


def _forecast_lines(forecast: dict, budget: str | None, currency: str) -> list[str]:
    """The forecast, or the honest account of why there is not one.

    This is the only place the forecast is stated. `predict_reach` computes it and
    says nothing, because it runs immediately before this node and speaking the
    numbers twice in one reply is noise.

    The unavailable branch carries the wording that matters rather than a shorter
    paraphrase: section 3 step 6 forbids inventing a reach figure, and "impressions,
    not unique people" is the sentence that stops a trader reading one as the other.
    """
    if not forecast:
        return ["- Forecast: not run"]

    if not forecast.get("is_available"):
        spend = f"{_money(budget)} {currency}" if budget else "the budget"
        return [
            "I cannot forecast reach for this plan.",
            "",
            forecast.get("reason", "Reach data is unavailable for this inventory."),
            "",
            f"What I can tell you: at {forecast.get('indicative_cpm')} CPM, {spend} buys "
            f"roughly {forecast.get('estimated_impressions', 0):,} impressions.",
            "",
            "That is impressions, not unique people - I have no way to tell you how many "
            "individuals that reaches, and I will not estimate it.",
        ]

    return [
        "Forecast for the Amazon portion:",
        "",
        f"- Impressions: {forecast['estimated_impressions']:,}",
        f"- Unique reach: {forecast['estimated_unique_reach']:,} people",
        f"- Average frequency: {forecast['average_frequency']}",
        f"- Indicative CPM: {forecast['indicative_cpm']}",
    ]


def _summary(state: PlanningAgentState) -> str:
    dates = state.get("flight_dates") or {}
    budgets = state.get("market_budgets") or []
    deals = state.get("selected_deals") or []
    audience = state.get("chosen_audience") or {}
    currency = state.get("primary_currency") or ""

    lines = [
        f"**{state.get('strategy_name') or 'CTV plan'}** - here is the complete plan.",
        "",
        f"- Market: {', '.join(state.get('markets') or []) or 'not stated'}",
        (
            f"- Flight: {dates['lower']} to {dates['upper']}"
            if dates.get("lower") and dates.get("upper")
            else "- Flight: not stated"
        ),
        f"- Creative durations: {', '.join(state.get('durations') or []) or 'not stated'} seconds",
        (
            f"- Budget: {_money(budgets[0]['budget'])} {currency}"
            if budgets
            else "- Budget: not stated"
        ),
        "- Goal: Awareness, measured on reach (fixed for CTV)",
        "",
        f"- Inventory: {len(deals)} deals, {_tier_label(state.get('inventory_tier'))}",
    ]

    if audience:
        effective = audience.get("effective_cpm")
        priced = (
            f"{effective} effective CPM"
            if effective
            else f"{audience.get('vcpm_fee')} fee, no Amazon inventory to price against"
        )
        lines.append(
            f"- Audience: {audience.get('profile', '').title()} - {audience.get('name')} "
            f"(~{audience.get('estimated_size', 0):,} people, {priced})"
        )
    else:
        lines.append("- Audience: not chosen")

    lines += [
        "",
        *_forecast_lines(
            state.get("forecast") or {},
            budgets[0]["budget"] if budgets else None,
            currency,
        ),
    ]

    # Said when they were found, and said again here - see the module docstring.
    outstanding = [
        entry["message"]
        for entry in state.get("validation_errors") or []
        if entry.get("message") and entry.get("severity") == "warning"
    ]
    if outstanding:
        lines += ["", "Worth knowing:", *[f"- {note}" for note in outstanding]]

    lines += [
        "",
        "Next: say the word and I will create this strategy in VOW, or tell me what to "
        "change and I will re-plan.",
    ]

    return "\n".join(lines)


async def deliver_plan(state: PlanningAgentState) -> dict:
    """Consolidate the plan, or stand by if it has not changed since last turn."""
    # `asking` guarantees a message: this is the last node, so nothing downstream
    # can speak instead and `sessions.chat` turns a silent turn into an HTTP 500.
    # `repeat_with` is what stops that guarantee reprinting the whole plan because
    # someone typed "thanks".
    spoken = say(state, STAGE, _summary(state), asking=True, repeat_with=STANDING_BY)

    return {"current_stage": STAGE, **spoken}
