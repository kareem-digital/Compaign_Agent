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

    return Block(
        text="Here's what I understood - correct anything that's wrong.",
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
        return Block(
            text="When should it run?",
            interaction=Interaction.INPUT_DATE_RANGE,
            layout=Layout.DATE_RANGE_PICKER,
            field=field,
            data={"earliest": "today"},
        )

    if field == "durations":
        return Block(
            text="Which creative lengths?",
            interaction=Interaction.SELECT_MANY,
            layout=Layout.CHIPS,
            field=field,
            # A closed set: VOW sells exactly these, so offer them rather than
            # accept free text and have to reject "45" afterwards.
            data={"options": [{"value": d, "label": f"{d}s"} for d in reference.durations()]},
        )

    if field == "market_budgets":
        # The currency follows the market where we know it, so a US plan is not
        # quoted in pounds.
        chosen = (state.get("markets") or [None])[0]
        currency = reference.currency_for(chosen) or state.get("primary_currency") or "GBP"
        return Block(
            text="What's the budget?",
            interaction=Interaction.INPUT_MONEY,
            layout=Layout.CURRENCY_INPUT,
            field=field,
            data={"currency": currency, "minimum": 1},
        )

    return None


def input_blocks(state: dict) -> list[Block]:
    """One block per field the plan still needs - or the one it cannot accept.

    Asks for everything outstanding at once rather than one field per turn.
    Drip-feeding would be four round trips to start a plan - the wizard
    experience the agent exists to replace.

    **A rejected field is asked for alone.** A trader who named China was given a
    date picker, duration chips and a money input - three controls for a market
    VOW cannot buy, and every answer wasted. While a value is rejected there is
    one useful next move, so it is the only one offered; the gaps return on the
    turn the plan becomes groundable. `rejected_fields` is set by
    `extract_fields._grounding`.
    """
    rejected = [f for f in _ASK_ORDER if f in (state.get("rejected_fields") or [])]
    if rejected:
        return [
            block for field in rejected if (block := _ask_for(field, state)) is not None
        ] or []

    blocks = [
        block
        for field in _ASK_ORDER
        if not state.get(field)
        if (block := _ask_for(field, state)) is not None
    ]

    # The first thing asked is the one to put front and centre, so an interface
    # has an obvious focal point rather than three equal inputs.
    if blocks:
        blocks[0].primary = True

    return blocks


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

    if preferred:
        text = (
            f"Got it - {recap}. You've chosen {', '.join(preferred)}; here are the "
            f"deals available. Say if you'd like to change that."
        )
    else:
        text = f"Got it - {recap}. Here's the CTV inventory available in {market}."

    return Block(
        text=text,
        interaction=Interaction.CONFIRM if preferred else Interaction.SELECT_MANY,
        layout=Layout.TABLE,
        field="selected_deals",
        data={
            # What was chosen, and what else exists. Both empty when nothing was
            # specified, which is how a client tells the two shapes apart.
            "confirming": preferred,
            "alternatives": alternatives,
            "columns": ["Provider", "Genre", "CPM", "Lengths", "Tier"],
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
        text="Three audience options - pick one and I'll forecast against it.",
        interaction=Interaction.SELECT_ONE,
        layout=Layout.CARDS,
        primary=True,
        field="chosen_audience",
        data={
            "selected": chosen,
            "options": [
                {
                    "value": option["profile"],
                    "label": option["profile"].title(),
                    "sublabel": option["name"],
                    "metrics": {
                        "Segments": option["segment_count"],
                        "People": option["estimated_size"],
                        # The number traders miss: the audience fee stacks on
                        # the deal CPM, so narrow is smaller AND dearer.
                        "Effective CPM": option.get("effective_cpm"),
                    },
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


# --- the whole reply ---------------------------------------------------------


# Which builder speaks for each stage. The graph runs one stage per turn, so
# exactly one of these produces the reply.
_STAGE_BLOCK = {
    "inventory": inventory_block,
    "audiences": audience_block,
    "forecast": forecast_block,
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
    asks = input_blocks(state)
    if asks:
        return [summary_block(state), *asks]

    builder = _STAGE_BLOCK.get(state.get("current_stage"))
    block = builder(state) if builder else None

    return [block] if block is not None else []
