"""How plan state is described to a user interface.

The agent decides what happens next; this decides how to describe it. It lives
in the API layer on purpose - nodes and the graph know nothing about interfaces.

A reply is a list of Blocks. Each carries three things:

    text         What a human reads. Works with no interface at all.
    interaction  What kind of moment this is. AUTHORITATIVE - the frontend must
                 honour it. Never depends on screen size, so the backend can
                 decide it correctly.
    data         The structured content, so a screen can render more than a
                 sentence. You cannot build three cards from a paragraph.

Plus `layout`, which is a SUGGESTION. The backend cannot see the window width,
whether the widget is embedded in a narrow panel, or whether this is a phone,
so it proposes a treatment and the frontend may adapt. Cards on a desktop, a
stacked list on a phone - same underlying select_one either way.

Both vocabularies are CLOSED, so the frontend can implement every value and
every reply is guaranteed renderable. An unknown value must degrade to showing
`text`, never break: backend and frontend deploy at different times.

Nothing here is chosen by the LLM. The model writes prose; code picks the
presentation. A model choosing layouts would render the same data differently
on two runs - users notice, and tests cannot pin it down.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.agent.nodes.select_inventory import AMAZON_OWNED
from app.knowledge import reference


class Interaction(StrEnum):
    """What the user can do with a block. The frontend must honour this."""

    NONE = "none"  # read only
    CONFIRM = "confirm"  # already decided - accept or amend
    SELECT_ONE = "select_one"  # pick exactly one option
    SELECT_MANY = "select_many"  # pick any number of options
    INPUT_DATE_RANGE = "input_date_range"  # a start and an end
    INPUT_MONEY = "input_money"  # an amount in a currency
    INPUT_TEXT = "input_text"  # free text


class Layout(StrEnum):
    """Suggested visual treatment. The frontend may override for context."""

    SUMMARY_LIST = "summary_list"  # label/value pairs
    TABLE = "table"  # columns and rows
    CARDS = "cards"  # comparable options side by side
    CHIPS = "chips"  # a few short values inline
    METRICS = "metrics"  # a row of figures
    DATE_RANGE_PICKER = "date_range_picker"
    CURRENCY_INPUT = "currency_input"


class Block(BaseModel):
    """One renderable piece of a reply."""

    text: str = Field(..., description="What a human reads.")
    interaction: Interaction = Field(..., description="Authoritative.")
    layout: Layout = Field(..., description="Suggested; may be overridden.")
    primary: bool = Field(
        False, description="The main artifact for this step, rather than conversation."
    )
    field: str | None = Field(None, description="Which plan field this block sets, if any.")
    data: dict = Field(default_factory=dict, description="Structured content.")


# --- the summary -------------------------------------------------------------

# Order matters: this is the order a trader reads them in, not the order the
# schema happens to declare them.
_SUMMARY_ROWS = (
    ("brand", "Brand"),
    ("markets", "Markets"),
    ("flight_dates", "Flight"),
    ("durations", "Creative durations"),
    ("market_budgets", "Budget"),
    ("goal", "Goal"),
    ("kpi", "KPI"),
)

NOT_STATED = "not stated"


def _format_value(field: str, state: dict) -> str:
    """One row's value, in the trader's language rather than the schema's.

    Formatting lives here rather than in the browser: one place, testable, and
    consistent across any client that consumes this.
    """
    if field == "brand":
        return state.get("brand") or NOT_STATED

    if field == "markets":
        return ", ".join(state.get("markets") or []) or NOT_STATED

    if field == "flight_dates":
        dates = state.get("flight_dates")
        return f"{dates['lower']} to {dates['upper']}" if dates else NOT_STATED

    if field == "durations":
        durations = state.get("durations") or []
        return ", ".join(f"{d}s" for d in durations) or NOT_STATED

    if field == "market_budgets":
        budgets = state.get("market_budgets") or []
        if not budgets:
            return NOT_STATED
        currency = state.get("primary_currency") or ""
        return f"{budgets[0]['budget']} {currency}".strip()

    # Goal and KPI are fixed for CTV — auto-confirmed, never asked.
    # Label them explicitly so traders understand they're system defaults.
    if field == "goal":
        value = state.get("goal")
        return "Awareness (fixed for CTV)" if value else NOT_STATED

    if field == "kpi":
        value = state.get("kpi")
        return "Unique reach (fixed for CTV)" if value else NOT_STATED

    return str(state.get(field) or NOT_STATED)


def summary_block(state: dict) -> Block:
    """What the agent believes so far.

    Always present, including when almost nothing is known - the schema doc
    calls "did I understand correctly?" the most important trust mechanism in
    the product, and a trader cannot correct what they cannot see. Fields that
    are still unknown say so rather than being hidden.
    """
    rows = [
        {"label": label, "value": _format_value(field, state), "field": field}
        for field, label in _SUMMARY_ROWS
    ]
    known = sum(1 for row in rows if row["value"] != NOT_STATED)

    deals = state.get("selected_deals") or []
    preferred = state.get("preferred_providers") or []
    inv_name = preferred[0] if preferred else (deals[0]["provider"] if deals else None)
    market = (state.get("markets") or [""])[0]
    if inv_name and market:
        intro_text = f"Got it — {inv_name} in {market}. To complete your plan, please provide the remaining details:"
    elif market:
        intro_text = f"Got it — campaign in {market}. To continue, please provide the following details:"
    else:
        intro_text = "To build your campaign plan, please provide the following details:"

    return Block(
        text=intro_text,
        interaction=Interaction.NONE,
        layout=Layout.SUMMARY_LIST,
        data={"rows": rows, "known": known, "total": len(rows)},
    )


# --- asking for what's missing ----------------------------------------------

# What the agent waits for, in the order it should be asked. Markets first
# because everything downstream depends on it: durations are validated against a
# market's rate card, deals are filtered by market, audiences follow the deals.
_ASK_ORDER = ("markets", "flight_dates", "durations", "market_budgets")


def _ask_for(field: str, state: dict) -> Block | None:
    """How to ask for one field.

    Options come from `app.knowledge.reference`, not from literals here, so the
    interface can never offer a market or duration VOW does not sell. Before,
    this list and the governance policy were two hardcoded lists that happened
    to agree - and would have silently diverged the moment A3 landed in one and
    not the other.
    """
    if field == "markets":
        return Block(
            text="Which market?",
            interaction=Interaction.SELECT_MANY,
            layout=Layout.CHIPS,
            field=field,
            data={"options": reference.markets()},
        )

    if field == "flight_dates":
        deals = state.get("selected_deals") or []
        preferred = state.get("preferred_providers") or []
        inv_name = preferred[0] if preferred else (deals[0]["provider"] if deals else None)
        market = (state.get("markets") or ["GB"])[0]
        prefix = f"Got it — {inv_name} in {market}. " if inv_name else (f"Got it — campaign in {market}. " if market else "")
        return Block(
            text=f"{prefix}When should the campaign run?",
            interaction=Interaction.INPUT_DATE_RANGE,
            layout=Layout.DATE_RANGE_PICKER,
            field=field,
            data={"earliest": date.today().isoformat()},
        )

    if field == "durations":
        return Block(
            text="Which creative length would you like to use?",
            interaction=Interaction.SELECT_ONE,
            layout=Layout.CHIPS,
            field=field,
            data={
                "options": [
                    {"value": "15", "label": "15s", "description": "Standard short CTV format"},
                    {"value": "30", "label": "30s", "description": "Standard full CTV format", "badge": "Recommended", "recommended": True},
                    {"value": "10", "label": "10s", "description": "Short bumper format"},
                    {"value": "20", "label": "20s", "description": "Medium format"},
                ]
            },
        )

    if field == "market_budgets":
        chosen = (state.get("markets") or [None])[0]
        currency = reference.currency_for(chosen) or state.get("primary_currency") or "GBP"
        symbol = "£" if currency == "GBP" else ("$" if currency == "USD" else "€")
        return Block(
            text=f"What budget would you like to allocate for this campaign ({currency})?",
            interaction=Interaction.SELECT_ONE,
            layout=Layout.CHIPS,
            field=field,
            data={
                "options": [
                    {"value": f"15000 {currency}", "label": f"{symbol}15,000", "description": f"Standard starting budget ({currency})"},
                    {"value": f"20000 {currency}", "label": f"{symbol}20,000", "description": f"Recommended mid-tier budget ({currency})", "badge": "Recommended", "recommended": True},
                    {"value": f"25000 {currency}", "label": f"{symbol}25,000", "description": f"High reach budget ({currency})"},
                    {"value": f"50000 {currency}", "label": f"{symbol}50,000", "description": f"Scale budget ({currency})"},
                ]
            },
        )

    return None


def input_blocks(state: dict) -> list[Block]:
    """One block per field the plan still needs - or the one it cannot accept."""
    if state.get("current_stage") == "concluded" or state.get("stage_cursor") == "concluded":
        return []

    # When the user's requested inventory is unavailable, surface it before
    # asking for missing basics — the trader needs to redirect first.
    unavailable = state.get("unavailable_requested_channels") or []
    if unavailable:
        channel_names = ", ".join(unavailable)
        return [
            Block(
                text=f"{channel_names} isn't currently available as inventory on this platform, so I can't plan the campaign on it. We hope to support it in the future. Would you like to use an available inventory instead?",
                interaction=Interaction.SELECT_ONE,
                layout=Layout.CHIPS,
                field="inventory_alternatives",
                primary=True,
                data={
                    "options": [
                        {"value": "show_alternatives", "label": "Show available inventory"},
                        {"value": "keep_requested", "label": "No, I'll plan this later"},
                    ]
                },
            )
        ]

    rejected = [f for f in _ASK_ORDER if f in (state.get("rejected_fields") or [])]
    if rejected:
        for field in rejected:
            block = _ask_for(field, state)
            if block is not None:
                block.primary = True
                return [block]

    # Ask for one missing field at a time in the natural conversational order
    for field in _ASK_ORDER:
        if not state.get(field):
            block = _ask_for(field, state)
            if block is not None:
                block.primary = True
                return [block]

    return []


# --- the plan ----------------------------------------------------------------
#
# These format what VOW told us. The values come from the MCP server via the
# nodes and live in plan state; nothing here invents data. When the real server
# replaces the mock (TMP-04), none of this changes - same state fields, real
# numbers instead of canned ones.


def inventory_block(state: dict) -> Block | None:
    """The CTV deals for this market - either offered, or confirmed back.

    Two shapes, depending on whether the trader already named a provider:

      * They did not     -> `select_many`. Here is everything, choose.
      * They named one   -> `confirm`. You chose Prime Video, here it is,
                            change it if you want.

    Asking someone to pick something they already told you is a form, not a
    conversation. `alternatives` carries what else is available, because a
    confirmation with no visible way out is an announcement.
    """
    deals = state.get("selected_deals") or []
    tiers = {t["value"]: t for t in reference.inventory_tiers()}
    market = (state.get("markets") or ["?"])[0]
    preferred = state.get("preferred_providers") or []
    alternatives = state.get("inventory_alternatives") or []

    if not deals:
        # A named provider with nothing available is a dead end unless we offer
        # the way out. The agent already knows the answer - "Netflix and Disney+
        # are available" - so say it as a choice rather than only as prose.
        if preferred and alternatives:
            return Block(
                text=(
                    f"{', '.join(preferred)} isn't available in {market}. "
                    "These are - shall I use one of them instead?"
                ),
                interaction=Interaction.SELECT_MANY,
                layout=Layout.CHIPS,
                primary=True,
                field="preferred_providers",
                data={"options": [{"value": p, "label": p} for p in alternatives]},
            )
        # Genuinely nothing to offer. Nothing structured to render, so nothing
        # is claimed - the explanation stays in the text channel.
        return None

    # Acknowledge what was understood before showing the table. Without it, the
    # first turn is a grid of prices appearing with no confirmation that the
    # brief was read correctly - which is abrupt, and hides a misreading.
    # The structured version of this lives in the always-visible panel; the chat
    # does the human half.
    recap = ", ".join(
        part
        for part in (
            market,
            (state.get("flight_dates") or {}).get("lower", "")[:7] or None,
            ", ".join(f"{d}s" for d in state.get("durations") or []) or None,
            _format_value("market_budgets", state) if state.get("market_budgets") else None,
        )
        if part
    )

    brand = state.get("brand")
    brand_prefix = f" for {brand}" if brand else ""
    if preferred:
        text = f"You've selected {', '.join(preferred)}. Here are the available CTV deals in {market}:"
    else:
        text = f"Got it. Here is the available CTV inventory in {market}{brand_prefix}. Which one would you like to select?"
    options = [
        {
            "value": deal["provider"],
            "label": f"{deal['provider']}{' (' + deal['genre'] + ')' if deal.get('genre') else ''}",
            "description": f"Indicative CPM: £{deal['cpm']} · {', '.join(f'{d}s' for d in deal.get('ad_lengths', []))} · {tiers.get(deal['inventory_tier'], {}).get('label', deal['inventory_tier'])}",
            "badge": "Amazon-owned" if deal.get("inventory_tier") == AMAZON_OWNED else ("Pre-curated" if deal.get("inventory_tier") == "THIRD_PARTY_PRECURATED" else "Rate Card"),
            "recommended": _preselect(deal, preferred),
        }
        for deal in deals
    ]

    return Block(
        text=text,
        interaction=Interaction.CONFIRM if preferred else Interaction.SELECT_ONE,
        layout=Layout.CARDS if not preferred else Layout.TABLE,
        field="preferred_providers",
        data={
            # What was chosen, and what else exists. Both empty when nothing was
            # specified, which is how a client tells the two shapes apart.
            "confirming": preferred,
            "alternatives": alternatives,
            "columns": ["Provider", "Genre", "CPM", "Lengths", "Tier"],
            "options": options,
            "rows": [
                {
                    "value": deal["deal_id"],
                    "provider": deal["provider"],
                    "genre": deal.get("genre") or "Run of service",
                    "cpm": deal["cpm"],
                    "lengths": ", ".join(f"{d}s" for d in deal.get("ad_lengths", [])),
                    "tier": tiers.get(deal["inventory_tier"], {}).get(
                        "label", deal["inventory_tier"]
                    ),
                    # Carried per row so the interface can warn on the row
                    # itself rather than in a footnote nobody reads.
                    "note": tiers.get(deal["inventory_tier"], {}).get("note", ""),
                    "selected": _preselect(deal, preferred),
                }
                for deal in deals
            ],
        },
    )


def _preselect(deal: dict, preferred: list[str]) -> bool:
    """Should this row arrive already ticked?

    **Every row used to arrive ticked, and one of them silently costs the forecast.** The rows
    are the checkboxes that write `selected_deals`, and `select_inventory.dominant_tier` takes
    the most conservative tier across whatever ends up there. So a trader who left Disney+
    ticked - a deal that does not exist yet, rate card only - and pressed continue would push
    the plan's tier to `THIRD_PARTY_NEEDS_CURATION` and turn the reach forecast off. A default
    nobody chose, changing what the plan can promise.

    Two shapes, matching the two the block itself has:

      they named providers   the rows are already filtered to their choice, so every row IS
                             the answer - ticking them is reading their words back
      they named nothing     tick only what can be acted on today. `AMAZON_OWNED` is the one
                             tier with a real deal AND a reach forecast; the others stay
                             visible and unticked, with their `note` saying why

    Not hiding anything and not choosing for anyone: an unticked row is still on screen, still
    selectable, and still carries "No reach forecast" or "Rate card only" next to it.
    """
    if preferred:
        return True
    return deal.get("inventory_tier") == AMAZON_OWNED


def audience_block(state: dict) -> Block | None:
    """The three audience options - the one real decision in the flow so far.

    Cards rather than a table because the point is comparison: three options,
    three prices, three sizes, side by side.
    """
    options = state.get("audience_options") or []
    if not options:
        return None

    chosen = (state.get("chosen_audience") or {}).get("profile")

    return Block(
        text="Here are three audience options. Pick one to forecast reach against:",
        interaction=Interaction.SELECT_ONE,
        layout=Layout.CARDS,
        primary=True,
        field="chosen_audience",
        data={
            "selected": chosen,
            "options": [
                {
                    "value": option["profile"],
                    "label": f"{option['profile'].title()} ({option['name']})",
                    "sublabel": option["name"],
                    "metrics": {
                        "Segments": option["segment_count"],
                        "Audience": f"~{option['estimated_size']:,}",
                        "Effective CPM": f"£{option.get('effective_cpm')}" if option.get("effective_cpm") else None,
                    },
                    "badge": "Recommended" if option["profile"] == "BALANCED" else None,
                    "recommended": option["profile"] == "BALANCED",
                }
                for option in options
            ],
        },
    )


def forecast_block(state: dict) -> Block | None:
    """What the plan is expected to deliver - or an honest refusal.

    Unique reach is None when unavailable, never 0. Zero is a number a trader
    could act on; unavailable is an absence. The interface must show them
    differently, so the data has to keep them apart.

    When no forecast is possible the refusal is written into `text`, so an
    interface that renders nothing but text still carries the honesty.
    """
    forecast = state.get("forecast")
    if not forecast:
        return None

    available = bool(forecast.get("is_available"))

    if available:
        text = "Forecast for the Amazon portion"
    else:
        text = (
            f"{forecast.get('reason', 'Reach data is unavailable for this inventory.')} "
            "The impressions below are real; the number of unique people is not "
            "something I can tell you, and I will not estimate it."
        )

    return Block(
        text=text,
        interaction=Interaction.NONE,
        layout=Layout.METRICS,
        data={
            "available": available,
            "metrics": {
                "Impressions": forecast.get("estimated_impressions"),
                "Unique reach": forecast.get("estimated_unique_reach"),
                "Average frequency": forecast.get("average_frequency"),
                "Indicative CPM": forecast.get("indicative_cpm"),
            },
            "curve": forecast.get("reach_curve"),
        },
    )


def plan_ready_block(state: dict) -> Block | None:
    """Strategy review and approval block when M1 plan is complete."""
    if state.get("strategy_created") or state.get("plan_approved"):
        return None

    return Block(
        text="Your CTV Strategy Plan is ready for review. Would you like to approve and create this strategy?",
        interaction=Interaction.SELECT_ONE,
        layout=Layout.CARDS,
        primary=True,
        field="plan_approved",
        data={
            "options": [
                {
                    "value": "approve",
                    "label": "Approve Strategy Plan",
                    "badge": "Ready",
                    "description": "Approve this plan and create the campaign strategy.",
                    "recommended": True,
                },
                {
                    "value": "modify",
                    "label": "Modify Strategy",
                    "description": "Adjust budget, dates, inventory, or targeting before creating.",
                },
            ]
        },
    )


# --- the whole reply ---------------------------------------------------------


# Which builder speaks for each stage. The graph runs one stage per turn, so
# exactly one of these produces the reply.
_STAGE_BLOCK = {
    "inventory": inventory_block,
    "audiences": audience_block,
    "forecast": forecast_block,
    "plan_ready": plan_ready_block,
}


def build_blocks(state: dict) -> list[Block]:
    """What is NEW this turn - not the whole plan.

    A chat message should carry what changed. Repeating the deals table under
    every later message is the same wall of text arriving two turns late.

    The full picture belongs in a panel that is always visible and fetches its
    own data, so nothing is lost by leaving it out here: the trader sees the
    running plan there rather than in scrollback.

    Two exceptions to "one block":

      * Missing basics produce one input block per outstanding field, because
        asking for four things over four turns is the wizard the agent replaces.
      * The summary appears only while probing, where there is no panel yet and
        the trader needs to see what was understood alongside what is missing.
    """
    if state.get("unavailable_requested_channels"):
        return input_blocks(state)

    stage = state.get("current_stage")
    if stage and stage in _STAGE_BLOCK:
        block = _STAGE_BLOCK[stage](state)
        if block is not None:
            return [block]

    asks = input_blocks(state)
    if asks:
        return asks

    return []
