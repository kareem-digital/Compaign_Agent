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
    # `default=` by keyword, not positionally: without the pydantic mypy plugin
    # these models are read under PEP 681, which only treats a field as optional
    # when the field specifier names `default`. Positionally they read as
    # required and every construction site that omits them fails type-check.
    primary: bool = Field(
        default=False, description="The main artifact for this step, rather than conversation."
    )
    field: str | None = Field(default=None, description="Which plan field this block sets, if any.")
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

# Which state keys count as having answered each ask. The same keys
# `gates.BASICS` uses, and for the same reason: `flight_dates` and
# `market_budgets` are derived and stay empty until whole, so reading them here
# would re-ask for something the trader already gave. A budget named before a
# market lives in `budget_amount` and cannot be keyed to a market yet - asking
# for it again is the exact bug
# `test_a_budget_given_before_a_market_is_not_asked_for_twice` exists to catch.
#
# The dict key is still the plan field a client sets, so the wire contract is
# unchanged; only the "do we have it?" test moved to the raw slots.
_ANSWERED_BY = {
    "markets": ("markets",),
    "flight_dates": ("flight_start", "flight_end"),
    "durations": ("durations",),
    "market_budgets": ("budget_amount",),
}


def _is_answered(field: str, state: dict) -> bool:
    """Whether the plan already holds an answer for one ask.

    Answered means every key the field needs is present, so a half-given flight
    still counts as outstanding - a date range with one end is not an answer.
    """
    return all(state.get(key) for key in _ANSWERED_BY[field])


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
    """One block per field the plan still needs.

    Asks for everything outstanding at once rather than one field per turn.
    Drip-feeding would be four round trips to start a plan - the wizard
    experience the agent exists to replace.
    """
    blocks = [
        block
        for field in _ASK_ORDER
        if not _is_answered(field, state)
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
                    "selected": True,
                }
                for deal in deals
            ],
        },
    )


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


# Which builders speak for the stage the turn ended on. A gate can stop the graph
# at any one of these, and `deliver_plan` reaches `delivered` having run all of
# them - so a stage maps to a *list*, not a single builder.
#
# `validation` is absent deliberately: a turn that stops there has a blocking
# grounding failure and nothing new to render, so the explanation stays in the
# text channel rather than being dressed up as a plan.
_STAGE_BLOCKS = {
    "inventory": (inventory_block,),
    "audiences": (audience_block,),
    "forecast": (forecast_block,),
    # The structured mirror of what `deliver_plan` consolidates in prose. The
    # graph runs the whole gated chain in one turn once the basics are complete,
    # so by `delivered` all three have something to say - and a client that got
    # only the forecast would be rendering the answer without the plan.
    "delivered": (inventory_block, audience_block, forecast_block),
}


def build_blocks(state: dict) -> list[Block]:
    """What this turn has to show - not the running plan in full.

    A chat message should carry what the turn produced. Repeating the deals table
    under every later message is the same wall of text arriving two turns late,
    which is why nothing here reaches back for state an earlier turn already
    rendered: the always-visible panel fetches its own data and is where the
    trader watches the plan accumulate.

    Two exceptions to "one block":

      * Missing basics produce one input block per outstanding field, because
        asking for four things over four turns is the wizard the agent replaces.
      * The summary appears only while probing, where there is no panel yet and
        the trader needs to see what was understood alongside what is missing.

    A builder returning None is dropped rather than emitted empty - `blocks` is
    "what is renderable", so an absent forecast must be an absent block and not a
    block claiming an absent forecast.
    """
    asks = input_blocks(state)
    if asks:
        return [summary_block(state), *asks]

    builders = _STAGE_BLOCKS.get(state.get("current_stage") or "", ())
    return [block for builder in builders if (block := builder(state)) is not None]
